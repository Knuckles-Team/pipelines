/* Test-only wall-clock CDP capture. Keep the page's double-RAF paint/camera probe
 * intact; CLI virtual-time completion does not guarantee that probe has run.
 * Only Node built-ins and the already installed runner browser are used.
 */
const {spawn}=require('node:child_process');
const {mkdtempSync,writeFileSync,rmSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join}=require('node:path');
const [chrome,url,viewport,screenshot]=process.argv.slice(2);
const [width,height]=viewport.split(',').map(Number);
if(!chrome||!url||!screenshot||![width,height].every(n=>Number.isFinite(n)&&n>0))throw Error('Expected browser, URL, width,height, screenshot path');
const profile=mkdtempSync(join(tmpdir(),'architecture-count-'));
const browser=spawn(chrome,['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-pipe',`--user-data-dir=${profile}`,`--window-size=${width},${height}`,'about:blank'],{stdio:['ignore','ignore','pipe','pipe','pipe']});
let serial=0,buffer='',closed=false;
const pending=new Map();
const rejectPending=error=>{for(const request of pending.values()){clearTimeout(request.timer);request.reject(error);}pending.clear();};
const exited=new Promise(resolve=>browser.once('close',(code,signal)=>{closed=true;rejectPending(Error(`Chrome exited: ${code ?? signal}`));resolve();}));
const pipeError=error=>{closed=true;rejectPending(error);};
browser.on('error',pipeError);browser.stdio[3].on('error',pipeError);browser.stdio[4].on('error',pipeError);
browser.stderr.on('data',data=>process.stderr.write(data));
browser.stdio[4].on('data',data=>{
  buffer+=data.toString();let end;
  while((end=buffer.indexOf('\0'))>=0){const raw=buffer.slice(0,end);buffer=buffer.slice(end+1);if(!raw)continue;
    const message=JSON.parse(raw);if(message.method==='Runtime.exceptionThrown')process.stderr.write('BROWSER_EXCEPTION '+JSON.stringify(message.params)+'\n');
    const request=pending.get(message.id);if(!request)continue;
    pending.delete(message.id);clearTimeout(request.timer);
    message.error?request.reject(Error(JSON.stringify(message.error))):request.resolve(message.result);
  }
});
function call(method,params={},sessionId){return new Promise((resolve,reject)=>{
  if(closed){reject(Error('Chrome pipe is closed'));return;}
  const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout: ${method}`));},10000);
  pending.set(id,{resolve,reject,timer});browser.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');
});}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
  const {targetId}=await call('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
  const command=(method,params)=>call(method,params,sessionId);
  const evaluate=async expression=>{const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await command('Page.enable');await command('Runtime.enable');
  // Preserve the previous CLI window sizing; do not replace the camera's viewport
  // with an emulated device while repairing only the frame scheduling mechanism.
  await call('Target.activateTarget',{targetId});await command('Page.bringToFront');
  await command('Page.navigate',{url});
  const start=Date.now();let completed=false;
  while(Date.now()-start<20000){
    if(await evaluate("!!document.getElementById('count-track-result')")){completed=true;break;}
    await delay(100);
  }
  const state=await evaluate("({hidden:document.hidden,mode:document.compatMode,charset:document.characterSet,result:document.getElementById('count-track-result')?.textContent||null})");
  const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  writeFileSync(screenshot,Buffer.from(shot.data,'base64'));
  process.stdout.write(await evaluate("'<!doctype html>\\n'+document.documentElement.outerHTML"));
  process.stderr.write('\nCOUNT_CAPTURE '+JSON.stringify({kind:'real wall-clock CDP; original double-RAF probe unchanged',elapsed_ms:Date.now()-start,...state})+'\n');
  if(!completed)throw Error('Count result missing after 20 seconds of real frame scheduling');
  if(state.hidden||state.mode!=='CSS1Compat'||state.charset!=='UTF-8')throw Error('Count capture was not visible UTF-8 standards mode');
  // PASS versus the expected old-formula FAIL is asserted by the owning Python test.
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  try{await call('Browser.close');}catch{}
  const killTimer=setTimeout(()=>browser.kill('SIGKILL'),2000);
  await exited;clearTimeout(killTimer);rmSync(profile,{recursive:true,force:true});
});
