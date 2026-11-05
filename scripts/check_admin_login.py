"""Check real admin UI session confirmation with synthetic API responses."""
import asyncio
import json
import socket
import subprocess
import uuid
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
INIT = r"""(() => {
  window.__adminTest = {mode:'declined',authenticated:false};
  const original = window.fetch.bind(window);
  const session = () => ({authenticated:window.__adminTest.authenticated,password_login_available:true,password_login_requires_email:true,azure_login_available:false,protection_enabled:true});
  window.fetch = async (input, options) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!url.pathname.startsWith('/auth/') && !url.pathname.startsWith('/catalog/')) return original(input, options);
    let value = {};
    if (url.pathname === '/auth/session') value = session();
    else if (url.pathname === '/auth/admin/login') {
      window.__adminTest.authenticated = window.__adminTest.mode === 'success';
      value = {...session(),authenticated:window.__adminTest.mode !== 'declined'};
    }
    else if (url.pathname === '/auth/representative/session') value = {authenticated:false,protection_enabled:false};
    else if (url.pathname === '/catalog/erp/status') value = {enabled:true,exists:true,products_loaded:1};
    else if (url.pathname === '/catalog/erp/files') value = {files:[]};
    else if (url.pathname === '/catalog/erp/products') value = {products:[{Codigo:'1001',Nome:'Produto de teste',Categoria:'Teste'}],products_loaded:1};
    else if (url.pathname === '/catalog/representatives') value = {users:[],total_users:0};
    return new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
  };
})();"""

async def run(port):
    async with httpx.AsyncClient(timeout=2) as client:
        for _ in range(40):
            try:
                pages=(await client.get(f'http://127.0.0.1:{port}/json')).json()
                page=next(item for item in pages if item.get('type')=='page')
                break
            except Exception:
                await asyncio.sleep(.1)
        else:
            raise RuntimeError('Browser unavailable')
    async with websockets.connect(page['webSocketDebuggerUrl']) as ws:
        seq=0
        async def call(method,params=None):
            nonlocal seq
            seq+=1
            await ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
            while True:
                reply=json.loads(await asyncio.wait_for(ws.recv(),15))
                if reply.get('id')==seq:
                    if 'error' in reply:raise RuntimeError(reply['error'])
                    return reply.get('result',{})
        async def evaluate(expression):
            reply=await call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
            if reply.get('exceptionDetails'):raise RuntimeError(reply['exceptionDetails'])
            return reply.get('result',{}).get('value')
        async def wait(expression):
            for _ in range(100):
                if await evaluate(expression):return
                await asyncio.sleep(.1)
            print(await evaluate("JSON.stringify({url:location.href,body:document.body?.innerText.slice(0,1200)})"),flush=True)
            raise AssertionError('Timed out: '+expression)
        async def fill(selector,value):
            await evaluate(f"(() => {{ const input=document.querySelector({json.dumps(selector)}); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,{json.dumps(value)}); input.dispatchEvent(new Event('input',{{bubbles:true}})); }})()")
            await asyncio.sleep(.1)
        async def login():
            await fill('input[type=email]','synthetic@example.test')
            await fill('input[type=password]','synthetic-password')
            await evaluate("[...document.querySelectorAll('button')].find(e=>e.textContent==='Entrar com senha').click()")
            await wait("!document.body.textContent.includes('Entrando...')")
        print('Browser connected',flush=True)
        await call('Page.enable')
        await call('Page.addScriptToEvaluateOnNewDocument',{'source':INIT})
        await call('Page.navigate',{'url':'http://127.0.0.1:5174/erp'})
        await wait("Boolean(document.querySelector('input[type=password]'))")
        await login()
        await wait("document.body.textContent.includes('Não foi possível confirmar sua sessão')")
        assert not await evaluate("document.body.textContent.includes('Login realizado com sucesso')")
        assert await evaluate("document.querySelector('input[type=email]').value==='synthetic@example.test'")
        print('PASS: rejected session does not display success or erase inputs',flush=True)
        await evaluate("window.__adminTest.mode='no-cookie'")
        await login()
        await wait("document.body.textContent.includes('Sua sessão não foi mantida')")
        assert not await evaluate("document.body.textContent.includes('Login realizado com sucesso')")
        print('PASS: missing browser session is reported without false success',flush=True)
        await evaluate("window.__adminTest.mode='success'")
        await login()
        await wait("document.body.textContent.includes('Painel administrativo')")
        assert not await evaluate("Boolean(document.querySelector('input[type=password]'))")
        assert await evaluate("document.body.textContent.includes('Login realizado com sucesso')")
        print('PASS: verified login opens the administrative panel',flush=True)


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    profile=ROOT/'.codex-tmp'/('admin-login-browser-'+uuid.uuid4().hex[:8])
    browser=subprocess.Popen([r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe','--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',f'--remote-debugging-port={port}',f'--user-data-dir={profile}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        asyncio.run(run(port))
    finally:
        browser.terminate()
        try:browser.wait(timeout=5)
        except subprocess.TimeoutExpired:browser.kill()

if __name__=='__main__':main()
