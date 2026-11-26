/* Drive the built Canopy page in a headless Chrome over the DevTools pipe and print one JSON result.
 * Usage: node canopy_drive.cjs <chrome> <url> <script-file>. The script is an async function body that returns
 * a JSON-serialisable value. With CANOPY_NO_SCRIPT set, scripting is switched off and the parsed document is returned. Page errors are returned beside the result; only Node built-ins are used.
 */
const {spawn}=require('node:child_process');
const {mkdtempSync,readFileSync,rmSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join}=require('node:path');
const [chrome,url,scriptFile]=process.argv.slice(2);
const profile=mkdtempSync(join(tmpdir(),'canopy-drive-'));
const browser=spawn(chrome,['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-pipe',`--user-data-dir=${profile}`,'--window-size=1500,950','about:blank'],{stdio:['ignore','ignore','ignore','pipe','pipe']});
let serial=0,buffer='';const pending=new Map(),errors=[];
browser.stdio[4].on('data',b=>{buffer+=b.toString();let end;
  while((end=buffer.indexOf('\0'))>=0){const raw=buffer.slice(0,end);buffer=buffer.slice(end+1);if(!raw)continue;
    const m=JSON.parse(raw);
    if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);
    const r=pending.get(m.id);if(r){pending.delete(m.id);m.error?r.reject(Error(JSON.stringify(m.error))):r.resolve(m.result);}}});
const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const id=++serial;
  const t=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);
  pending.set(id,{resolve:v=>{clearTimeout(t);resolve(v);},reject});
  browser.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{let code=0;
  try{
    const {targetInfos}=await call('Target.getTargets');const page=targetInfos.find(t=>t.type==='page');
    const {sessionId}=await call('Target.attachToTarget',{targetId:page.targetId,flatten:true});
    await call('Runtime.enable',{},sessionId);await call('Page.enable',{},sessionId);
    if(process.env.CANOPY_NO_SCRIPT){ // a browser with scripting off: return the parsed document instead of evaluating a script
      await call('Emulation.setScriptExecutionDisabled',{value:true},sessionId);
      await call('Page.navigate',{url},sessionId);await sleep(1500);
      const {root}=await call('DOM.getDocument',{depth:-1},sessionId);
      const {outerHTML}=await call('DOM.getOuterHTML',{nodeId:root.nodeId},sessionId);
      browser.kill();rmSync(profile,{recursive:true,force:true});process.stdout.write(JSON.stringify({result:outerHTML,errors})+'\n',()=>process.exit(0));return;
    }
    await call('Page.navigate',{url},sessionId);await sleep(2500);
    const body=readFileSync(scriptFile,'utf8');
    const out=await call('Runtime.evaluate',{expression:`(async()=>{${body}})()`,awaitPromise:true,returnByValue:true},sessionId);
    if(out.exceptionDetails)throw Error(out.exceptionDetails.exception?.description||out.exceptionDetails.text);
    process.stdout.write(JSON.stringify({result:out.result.value,errors})+'\n');
  }catch(e){console.log(JSON.stringify({failure:String(e),errors}));code=1;}
  browser.kill();rmSync(profile,{recursive:true,force:true});process.exit(code);
})();
