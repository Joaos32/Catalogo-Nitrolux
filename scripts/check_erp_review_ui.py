"""Browser regression checks using synthetic APIs; never reads credentials.

Run the frontend dev server, then python scripts/check_erp_review_ui.py.
Use CATALOG_QA_URL to point to a local compiled frontend preview.
Requires httpx, websockets (included with uvicorn[standard]) and Microsoft Edge
on Windows. Uses an isolated headless profile and stores results in .codex-tmp.
"""
import asyncio
import os
import base64
import json
import socket
import subprocess
import uuid
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("CATALOG_QA_URL", "http://127.0.0.1:5173")
ARTIFACT_PREFIX = os.getenv("CATALOG_QA_ARTIFACT_PREFIX", "erp-review-counts")
INIT = ""

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
        init=r"""(() => {
          const original=window.fetch.bind(window);
          const active='vercel-blob://catalogo/erp_products.json';
          const staged='erp-inbox://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/novo.json';
          let uploaded=false;
          const historyMode=new URLSearchParams(location.search).get('qa')==='history';
          const pendingOnLoad=historyMode||new URLSearchParams(location.search).get('qa')==='pending';
          const diagnostic='reports/erp-review-counts-browser-evidence-2026-10-29.json';
          window.__review={requests:[],errors:[],mode:"mixed",previewDelay:200,staleList:true};
          window.addEventListener('unhandledrejection',e=>window.__review.errors.push(String(e.reason)));
          window.addEventListener('error',e=>window.__review.errors.push(e.message));
          const summary={added_count:7,updated_count:5,removed_count:2,unchanged_count:100,compared_to_name:'ativo.json',compared_to_path:active,changes:[{change_type:'added',code:'2001',name:'Produto novo',category:'TARTARUGA',changed_fields:[]},{change_type:'updated',code:'1001',name:'Produto atualizado',category:'TARTARUGA',previous_name:'Nome anterior',changed_fields:['Nome']},{change_type:'removed',code:'1002',name:'Produto removido',category:'TARTARUGA',changed_fields:[]}]};
          const preview=path=>({path,name:path===staged?'novo.json':'ativo.json',size_bytes:200,updated_at:'2026-10-29T13:00:00Z',is_active:path===active,is_deployed_source:false,products_loaded:112,records_detected:112,ignored_records:0,categories:[],sample_products:[],change_summary:path===staged&&window.__review.mode==='missing'?null:path===staged&&window.__review.mode==='mixed'?summary:{...summary,added_count:0,updated_count:0,removed_count:0,unchanged_count:107,changes:[]}});
          window.fetch=async (input, options)=>{
            const url=new URL(typeof input==='string'?input:input.url,location.href);
            if(!url.pathname.startsWith('/catalog/')&&!url.pathname.startsWith('/auth/'))return original(input,options);
            window.__review.requests.push({path:url.pathname,file:url.searchParams.get('file_path'),method:options?.method||'GET'});
            let payload={};
            if(url.pathname==='/auth/session')payload={authenticated:true,protection_enabled:true};
            else if(url.pathname==='/auth/representative/session')payload={authenticated:false,protection_enabled:false};
            else if(url.pathname==='/catalog/erp/status')payload={exists:true,enabled:true,products_loaded:107,path:active,source_name:'ativo.json'};
            else if(url.pathname==='/catalog/erp/products')payload={products:[],products_loaded:107};
            else if(url.pathname==='/catalog/representatives')payload={users:[],total_users:0};
            else if(url.pathname==='/catalog/erp/stage-file'){uploaded=true;payload={...preview(staged),staged:true};}
            else if(url.pathname==='/catalog/erp/files'){
              if(uploaded)await new Promise(r=>setTimeout(r,600));
              const omit=uploaded&&window.__review.staleList; if(uploaded)window.__review.staleList=false;payload={files:[{path:diagnostic,name:'erp-review-counts-browser-evidence-2026-10-29.json',is_active:false,is_review:false},{path:'reports/catalog_runtime.json',name:'catalog_runtime.json',is_active:false,is_review:false},{path:active,name:'ativo.json',is_active:true,is_review:false},...((uploaded&&!omit)||pendingOnLoad?[{path:staged,name:'novo.json',is_active:false,is_review:true,is_deployed_source:historyMode},...(historyMode?[{path:'erp-inbox://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/antigo.json',name:'antigo.json',is_review:true,is_active:false,is_deployed_source:false}]:[])]:[])]};
            }
            else if(url.pathname==='/catalog/erp/files/preview'){
              if(url.searchParams.get('file_path')===diagnostic)return new Response(JSON.stringify({error:'invalid ERP payload: expected array or object with product list'}),{status:400,headers:{'Content-Type':'application/json'}});
              if(url.searchParams.get('file_path')===staged)await new Promise(r=>setTimeout(r,window.__review.previewDelay));
              payload=preview(url.searchParams.get('file_path'));
            }
            return new Response(JSON.stringify(payload),{status:200,headers:{'Content-Type':'application/json'}});
          };
        })()"""
        await call('Page.addScriptToEvaluateOnNewDocument',{'source':init})

        scenarios=[]
        upload_js="""(() => {const input=document.querySelector('input[type=file]');const transfer=new DataTransfer();transfer.items.add(new File(['{}'],'novo.json',{type:'application/json'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()"""
        counts_js="Object.fromEntries([...document.querySelectorAll('.admin-preview-panel [data-change-kind]')].map(e=>[e.dataset.changeKind,Number(e.querySelector('strong').textContent)]))"
        expected={'added':7,'updated':5,'removed':2,'unchanged':100}
        refresh_js="[...document.querySelectorAll('button')].find(e=>e.textContent==='Atualizar dados').click()"
        busy_js="Boolean(document.querySelector('.admin-preview-panel [role=status]'))"
        for width in [390,1440]:
            await call('Emulation.setDeviceMetricsOverride',{'width':width,'height':1000,'deviceScaleFactor':1,'mobile':width<768})
            await navigate('/erp')
            await wait("Boolean(document.querySelector('.admin-preview-panel .admin-change-section'))")
            assert await evaluate("document.querySelector('.admin-preview-panel h2').textContent")=='ativo.json'
            assert not await evaluate("window.__review.requests.some(r=>r.file?.includes('browser-evidence'))")
            scenarios.append({'width':width,'scenario':'technical and bundled files are not selected as pending reviews','selected':'ativo.json'})
            await evaluate(upload_js)
            await wait("document.querySelector('.banner-success')?.textContent.includes('enviado')")
            await wait('!'+busy_js)
            assert await evaluate("document.querySelector('.admin-preview-panel h2').textContent")=='novo.json'
            assert await evaluate(counts_js)==expected
            assert await evaluate("document.querySelector('.banner-success').textContent.includes('7 novos, 5 atualizados e 2 removidos')")
            # The first file-list refresh deliberately omits the new review.
            scenarios.append({'width':width,'scenario':'upload with stale file list','selected':'novo.json','counts':await evaluate(counts_js)})
            await evaluate("document.querySelector('.admin-preview-panel').scrollIntoView({block:'start'})")
            await asyncio.sleep(.3)
            assert await evaluate('document.documentElement.scrollWidth<=innerWidth')
            shot=await call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
            (ROOT/f'reports/{ARTIFACT_PREFIX}-{width}-2026-10-29.png').write_bytes(base64.b64decode(shot['data']))
            await evaluate('window.__review.previewDelay=900')
            await evaluate(refresh_js)
            await wait(busy_js)
            assert await evaluate(counts_js)==expected
            assert await evaluate("document.querySelector('.admin-preview-panel .admin-inline-actions button').disabled")
            scenarios.append({'width':width,'scenario':'counts retained while refreshing','counts':await evaluate(counts_js),'activation_disabled':True})
            await wait('!'+busy_js)
            await evaluate("window.__review.mode='zero';window.__review.previewDelay=200")
            await evaluate(refresh_js)
            await wait(busy_js)
            await wait('!'+busy_js)
            assert await evaluate(counts_js)=={'added':0,'updated':0,'removed':0,'unchanged':107}
            scenarios.append({'width':width,'scenario':'explicit zero counts','counts':await evaluate(counts_js)})
            await evaluate("window.__review.mode='missing'")
            await evaluate(refresh_js)
            await wait(busy_js)
            await wait('!'+busy_js)
            assert await evaluate("document.querySelector('.admin-preview-panel').textContent.includes('Comparação indisponível')")
            assert await evaluate(counts_js)=={}
            assert await evaluate("document.querySelector('.admin-preview-panel .admin-inline-actions button').disabled")
            scenarios.append({'width':width,'scenario':'missing summary has retry and no invented zero counts','activation_disabled':True})
            await evaluate("window.__review.mode='mixed';[...document.querySelectorAll('.admin-preview-panel button')].find(e=>e.textContent==='Atualizar comparação').click()")
            await wait(busy_js)
            await wait('!'+busy_js)
            assert await evaluate(counts_js)==expected
            assert await evaluate("document.querySelector('.admin-preview-panel h2').textContent")=='novo.json'
            scenarios.append({'width':width,'scenario':'retry restores selected review counts','counts':await evaluate(counts_js)})
            assert not await evaluate("window.__review.requests.some(r=>r.path==='/catalog/erp/import-file')")
            assert await evaluate("window.__review.errors")==[]
            await navigate('/erp?qa=pending')
            await wait("Boolean(document.querySelector('.admin-preview-panel .admin-change-section'))")
            await wait('!'+busy_js)
            assert await evaluate("document.querySelector('.admin-preview-panel h2').textContent")=='novo.json'
            assert await evaluate(counts_js)==expected
            assert not await evaluate("window.__review.requests.some(r=>r.file?.includes('browser-evidence'))")
            assert await evaluate("window.__review.errors")==[]
            scenarios.append({'width':width,'scenario':'pending uploaded review is preferred on initial load','selected':'novo.json','counts':await evaluate(counts_js)})
            await navigate('/erp?qa=history')
            await wait("Boolean(document.querySelector('.admin-preview-panel .admin-change-section'))")
            await wait('!'+busy_js)
            assert await evaluate("document.querySelector('.admin-preview-panel h2').textContent")=='novo.json'
            scenarios.append({'width':width,'scenario':'latest uploaded JSON preferred over an older undeployed review','selected':'novo.json'})
            print('PASS:',width,'upload selection, counts, refresh, zero, missing summary and retry',flush=True)
        (ROOT/f'reports/{ARTIFACT_PREFIX}-browser-evidence-2026-10-29.json').write_text(json.dumps({'scope':'Local compiled frontend with synthetic authenticated API fixtures, stale file-list responses and delayed comparisons. No production requests or catalog activation.','scenarios':scenarios},ensure_ascii=False,indent=2),encoding='utf-8')


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
