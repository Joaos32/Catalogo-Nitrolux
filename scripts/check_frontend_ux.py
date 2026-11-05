"""Browser regression checks using synthetic APIs; never reads credentials.

Run npm.cmd run dev in frontend, then python scripts/check_frontend_ux.py.
Requires httpx, websockets (included with uvicorn[standard]) and Microsoft Edge
on Windows. Uses an isolated headless profile and stores results in .codex-tmp.
"""
import asyncio
import base64
import json
import socket
import subprocess
import uuid
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:5173"
INIT = r"""(() => {
  window.__ux = {requests: [], errors: [], exports: 0, dialogs: [], accept: false};
  window.addEventListener('unhandledrejection', e => window.__ux.errors.push(String(e.reason)));
  window.confirm = text => { window.__ux.dialogs.push(text); return window.__ux.accept; };
  const products = Array.from({length:100}, (_, i) => ({Codigo:String(1000+i),
    Nome:['Lâmpada LED bulbo 9W','Painel LED quadrado 24W','Refletor externo 50W'][i%3],
    Categoria:['Lâmpadas LED','Painéis LED','Refletores'][i%3],
    Descricao:'Produto de teste para avaliação de layout e navegação.',
    Especificacoes:'Bivolt | 6500K', CODMARCA:i<70?1:2}));
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const u = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (u.protocol==='data:') { await new Promise(r=>setTimeout(r,250)); return window.__ux.photoFail ? new Response('',{status:503}) : original(input,init); }
    if (!u.pathname.startsWith('/catalog/') && !u.pathname.startsWith('/auth/')) return original(input, init);
    window.__ux.requests.push({path:u.pathname,method:init?.method||'GET'});
    let payload = {};
    let status = 200;
    if (u.pathname==='/auth/representative/session') payload={protection_enabled:true,authenticated:sessionStorage.getItem('ux-login')!=='true',user:{name:'Representante de teste',email:'teste@example.com'}};
    else if (u.pathname==='/auth/representative/login') { status=403; payload={detail:'invalid representative credentials'}; }
    else if (u.pathname==='/auth/representative/reset-password') { payload={success:true}; }
    else if (u.pathname==='/auth/session') payload={protection_enabled:true,authenticated:true,password_login_available:true};
    else if (u.pathname==='/catalog/local/produtos') payload=products;
    else if (u.pathname==='/catalog/export') {
      await new Promise(r=>setTimeout(r,300));
      if (!window.__ux.exportOk) { status=503; payload={detail:'Falha simulada'}; }
      else return new Response('mock file',{status:200,headers:{'Content-Type':'application/pdf','Content-Disposition':'attachment; filename=test.pdf'}});
    }
    else if (u.pathname.endsWith('/imagens')) payload={codigo:u.pathname.split('/')[3],imagens:[{name:'Fundo branco',url:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aU1cAAAAASUVORK5CYII='}]};
    else if (u.pathname==='/catalog/erp/status') payload={enabled:true,exists:true,products_loaded:100,source_name:'teste.json'};
    else if (u.pathname==='/catalog/erp/files') payload={files:[]};
    else if (u.pathname==='/catalog/erp/products') payload={products,products_loaded:100};
    else if (u.pathname.startsWith('/catalog/erp/products/')) payload={product:JSON.parse(init.body),created:false};
    else if (u.pathname==='/catalog/representatives') payload={users:[],total_users:0,managed_users:0,environment_users:0,admin_users:0,representative_users:0};
    return new Response(JSON.stringify(payload),{status,headers:{'Content-Type':'application/json'}});
  };
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function() { if (this.download) window.__ux.exports++; else click.call(this); };
})()"""

async def run(port):
    checks = []
    async with httpx.AsyncClient(timeout=1) as client:
        for _ in range(25):
            try:
                targets = (await client.get(f'http://127.0.0.1:{port}/json')).json()
                target = next(t for t in targets if t.get('type')=='page')
                break
            except Exception:
                await asyncio.sleep(.1)
        else:
            raise RuntimeError('Headless browser unavailable')
    async with websockets.connect(target['webSocketDebuggerUrl'], max_size=20_000_000) as ws:
        seq = 0
        async def call(method, params=None):
            nonlocal seq
            seq += 1
            ident = seq
            await ws.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(),30))
                if msg.get('id')==ident:
                    if 'error' in msg: raise RuntimeError(str(msg['error']))
                    return msg.get('result',{})
        async def evaluate(expression):
            result = await call('Runtime.evaluate',{'expression':expression,'awaitPromise':True,'returnByValue':True})
            if result.get('exceptionDetails'): raise RuntimeError(str(result['exceptionDetails']))
            return result.get('result',{}).get('value')
        async def wait(expression):
            for _ in range(120):
                if await evaluate(expression): return
                await asyncio.sleep(.05)
            raise AssertionError('Timed out: '+expression)
        async def check(name, expression):
            result = await evaluate(expression)
            assert result, name
            checks.append(name)
            print('PASS:',name,flush=True)
        async def navigate(path):
            await call('Page.navigate',{'url':BASE+path})
            await wait("Boolean(document.querySelector('main'))")
        async def click(selector):
            await evaluate(f'document.querySelector({json.dumps(selector)}).click()')
            await asyncio.sleep(.12)
        async def fill(selector, value):
            await evaluate(f"(() => {{ const e=document.querySelector({json.dumps(selector)}); Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,{json.dumps(value)}); e.dispatchEvent(new Event('input',{{bubbles:true}})); }})()")
            await asyncio.sleep(.1)
        async def screenshot(name):
            await evaluate('window.scrollTo(0,0)')
            await asyncio.sleep(.9)
            result = await call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
            (ROOT/'.codex-tmp'/name).write_bytes(base64.b64decode(result['data']))

        await call('Page.enable')
        await call('Page.addScriptToEvaluateOnNewDocument',{'source':INIT})
        await call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
        await navigate('/?brand=nitrolux')
        await wait("document.querySelectorAll('.product-card').length===15")
        await check('desktop list has progressive loading',"Boolean(document.querySelector('.load-more-button'))")
        while await evaluate("Boolean(document.querySelector('.load-more-button'))"):
            await click('.load-more-button')
        await check('all 70 products reachable without filters',"document.querySelectorAll('.product-card').length===70")
        await fill('input[type=search]','lampada')
        await check('accent-insensitive search stored in URL',"new URLSearchParams(location.search).get('q')==='lampada' && document.querySelectorAll('.product-card').length===15 && document.querySelector('.result-summary').textContent.includes('24')")
        await navigate('/?brand=pienza&q=painel')
        await wait("document.querySelectorAll('.product-card').length===10")
        await check('shared URL restores brand and search',"document.querySelector('input[type=search]').value==='painel' && document.querySelector('.brand-theme-pienza')!==null")
        await screenshot('frontend-after-desktop.png')

        await call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
        await navigate('/?brand=nitrolux')
        await wait("document.querySelectorAll('.product-card').length===6")
        await check('mobile first product visible in first screen',"document.querySelector('.product-card').getBoundingClientRect().top < 550")
        await check('no horizontal overflow at 390px',"document.documentElement.scrollWidth<=innerWidth")
        mobile_first_product = await evaluate("document.querySelector('.product-card').getBoundingClientRect().top")
        await screenshot('frontend-after-mobile.png')
        await click('.export-menu summary')
        await check('download disclosure fits viewport',"(() => {const r=document.querySelector('.export-menu .export-panel').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})()")
        await evaluate("[...document.querySelectorAll('.export-menu button')].find(e=>e.textContent==='PDF').click()")
        await wait("[...document.querySelectorAll('.export-menu button')].every(e=>e.disabled)")
        await check('downloads locked during pending request',"[...document.querySelectorAll('.export-menu button')].every(e=>e.disabled)")
        await wait("document.querySelector('.download-feedback')?.textContent.includes('Não foi possível')")
        await check('download failure visible and handled',"window.__ux.errors.length===0 && [...document.querySelectorAll('.export-menu button')].every(e=>!e.disabled)")
        await evaluate("window.__ux.exportOk=true;[...document.querySelectorAll('.export-menu button')].find(e=>e.textContent==='PDF').click()")
        await wait('window.__ux.exports===1')
        await check('successful export starts browser download',"document.querySelector('.download-feedback').textContent.includes('iniciado')")
        await click('.export-menu summary')
        await click('.load-more-button')
        await click('.load-more-button')
        await evaluate("window.scrollTo(0,1500); window.__returnScroll=scrollY; document.querySelectorAll('.card-hitbox')[4].click()")
        await wait("Boolean(document.querySelector('.detail-panel'))")
        await check('detail receives focus and scroll starts at top',"document.activeElement.tagName==='H2' && scrollY===0")
        await check('native product links preserve filters and count',"new URLSearchParams(location.search).get('limit')==='18' && document.querySelector('.detail-back').tagName==='A'")
        await wait("!document.querySelector('.detail-gallery-actions button').disabled")
        await evaluate("window.__ux.photoFail=true;document.querySelector('.detail-gallery-actions button').click()")
        await wait("document.querySelector('.detail-panel .download-feedback')?.textContent.includes('Não foi possível')")
        await check('photo download failure visible and handled',"window.__ux.errors.length===0 && !document.querySelector('.detail-gallery-actions button').disabled")
        await evaluate("window.__ux.photoFail=false;document.querySelector('.detail-gallery-actions button').click()")
        await wait('window.__ux.exports===2')
        await check('selected photo download succeeds after retry',"document.querySelector('.detail-panel .download-feedback').textContent.includes('iniciado')")
        await click('.detail-back')
        await wait("document.activeElement.classList.contains('card-hitbox')")
        await check('return restores loaded count and scroll',"document.querySelectorAll('.product-card').length===18 && Math.abs(scrollY-window.__returnScroll)<20")
        await evaluate("document.querySelectorAll('.card-hitbox')[4].click()")
        await wait("Boolean(document.querySelector('.detail-panel'))")
        await evaluate('history.back()')
        await wait("document.activeElement.classList.contains('card-hitbox')")
        await check('browser Back also restores product focus',"document.querySelectorAll('.product-card').length===18")

        await evaluate("sessionStorage.setItem('ux-login','true')")
        await navigate('/login')
        await wait("Boolean(document.querySelector('.auth-panel form'))")
        await fill('input[type=email]','email-invalido')
        await fill('input[type=password]','senha-de-teste')
        await click('button[type=submit]')
        await check('invalid email stays local and focuses field',"document.activeElement.type==='email' && !window.__ux.requests.some(r=>r.path==='/auth/representative/login')")
        await fill('input[type=email]','teste@example.com')
        await fill('input[type=password]','senha-de-teste')
        await evaluate("document.querySelector('input[type=password]').focus()")
        await call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r','unmodifiedText':'\r'})
        await call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
        await wait("window.__ux.requests.some(r=>r.path==='/auth/representative/login')")
        await check('Enter submits login and error is accessible',"document.querySelector('[role=alert]')?.textContent.includes('E-mail ou senha incorretos') && document.activeElement.getAttribute('role')==='alert'")
        await check('login has primary heading and native constraints',"Boolean(document.querySelector('h1')) && document.querySelector('input[type=email]').required")
        await click('.auth-fields button.is-secondary')
        await fill('input[name=resetCode]','CODIGO-TESTE')
        await fill('input[name=newPassword]','nova-senha-de-teste')
        await fill('input[name=confirmPassword]','outra-senha-de-teste')
        await click('button[type=submit]')
        await check('password confirmation error focuses field',"document.activeElement.name==='confirmPassword' && document.querySelector('#confirmation-error')!==null")

        await fill('input[name=confirmPassword]','nova-senha-de-teste')
        await click('button[type=submit]')
        await wait("Boolean(document.querySelector('input[name=password]'))")
        await check('successful password reset returns to login',"document.querySelector('.banner').textContent.includes('Senha alterada') && document.querySelector('input[name=password]').value===''")

        await navigate('/erp')
        await wait("Boolean(document.querySelector('.admin-workspace-tabs'))")
        await evaluate("[...document.querySelectorAll('.admin-workspace-tabs button')].find(e=>e.textContent.includes('Produtos')).click()")
        await wait("document.querySelectorAll('.admin-product-item').length===50")
        await check('admin initial product list is bounded',"document.querySelectorAll('.admin-product-item').length===50")
        await click('.admin-product-item')
        name_selector = '.admin-grid-products .admin-form-panel input[placeholder="Nome comercial do produto"]'
        await fill(name_selector,'Nome alterado sem salvar')
        await wait("Boolean(document.querySelector('.unsaved-notice'))")
        await evaluate("document.querySelectorAll('.admin-product-item')[1].click()")
        await check('cancel switching product keeps draft',"document.querySelector('.admin-form-panel input[placeholder=\"Nome comercial do produto\"]').value==='Nome alterado sem salvar' && window.__ux.dialogs.length===1")
        await click('.hero-link-button')
        await wait('window.__ux.dialogs.length===2')
        await check('cancel route navigation keeps admin and draft',"location.pathname==='/erp' && document.querySelector('.unsaved-notice')!==null")
        await check('closing tab with dirty draft triggers native protection',"!window.dispatchEvent(new Event('beforeunload',{cancelable:true}))")
        await evaluate("[...document.querySelectorAll('.admin-grid-products .admin-inline-actions button')].find(e=>e.textContent.includes('Salvar')).click()")
        await wait("!document.querySelector('.unsaved-notice')")
        await check('successful save clears dirty state',"document.querySelector('.admin-form-panel input[placeholder=\"Nome comercial do produto\"]').value==='Nome alterado sem salvar'")
        await fill(name_selector,'Outra alteração não salva')
        await evaluate("[...document.querySelectorAll('.admin-grid-products .admin-inline-actions button')].find(e=>e.textContent.includes('Limpar')).click()")
        await check('cancel clearing editor keeps draft',"document.querySelector('.admin-form-panel input[placeholder=\"Nome comercial do produto\"]').value==='Outra alteração não salva'")
        await evaluate('window.__ux.accept=true')
        await click('.hero-link-button')
        await wait("location.pathname!=='/erp'")
        checks.append('confirmed route navigation leaves admin')
        print('PASS: confirmed route navigation leaves admin',flush=True)
        await evaluate("sessionStorage.removeItem('ux-login')")
        for width in [320,768,1024]:
            await call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<768})
            await navigate('/?brand=pienza')
            await wait("Boolean(document.querySelector('.product-card'))")
            await check(f'Pienza layout fits {width}px',"document.documentElement.scrollWidth<=innerWidth && document.querySelector('.product-card').getBoundingClientRect().top<600")
        result={'mobile_first_product_y':mobile_first_product,'passed':len(checks),'checks':checks,'api':'synthetic','viewports':['1440x900','390x844','320x900','768x900','1024x900']}
        (ROOT/'.codex-tmp/frontend-ux-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'passed':len(checks)}),flush=True)


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    profile=ROOT/'.codex-tmp'/('frontend-ux-browser-'+uuid.uuid4().hex[:8])
    browser=subprocess.Popen([r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe','--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',f'--remote-debugging-port={port}',f'--user-data-dir={profile}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        asyncio.run(run(port))
    finally:
        browser.terminate()
        try: browser.wait(timeout=10)
        except subprocess.TimeoutExpired: browser.kill()

if __name__=='__main__':
    main()
