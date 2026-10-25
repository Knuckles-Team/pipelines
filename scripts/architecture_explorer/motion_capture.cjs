/* Real wall-clock Chrome capture, using only Node built-ins and the runner's browser.
 * No virtual time, animation seeking, synthetic frames, browser download or network service.
 */
const {spawn}=require('node:child_process');
const {mkdtempSync,writeFileSync,rmSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join,resolve}=require('node:path');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');
const [chrome,directory,theme]=process.argv.slice(2), output=resolve(directory);
const profile=mkdtempSync(join(tmpdir(),'architecture-motion-'));
const browser=spawn(chrome,['--headless=new','--no-sandbox','--disable-dev-shm-usage','--remote-debugging-pipe',`--user-data-dir=${profile}`,'--window-size=1440,1000','about:blank'],{stdio:['ignore','ignore','pipe','pipe','pipe']});
let serial=0,buffer='',logs='',pending=new Map(),closed=false;
const rejectPending=error=>{for(const request of pending.values()){clearTimeout(request.timer);request.reject(error);}pending.clear();};
const exited=new Promise(resolve=>browser.once('close',(code,signal)=>{closed=true;rejectPending(Error(`Chrome exited: ${code ?? signal}`));resolve();}));
const pipeError=error=>{closed=true;logs+=String(error)+'\n';rejectPending(error);};
browser.on('error',pipeError);
browser.stdio[3].on('error',pipeError);browser.stdio[4].on('error',pipeError);
browser.stderr.on('data',b=>{logs+=b.toString();});
browser.stdio[4].on('data',b=>{
  buffer+=b.toString();let end;
  while((end=buffer.indexOf('\0'))>=0){const raw=buffer.slice(0,end);buffer=buffer.slice(end+1);if(!raw)continue;
    const message=JSON.parse(raw),request=pending.get(message.id);if(!request)continue;
    pending.delete(message.id);clearTimeout(request.timer);
    message.error?request.reject(Error(JSON.stringify(message.error))):request.resolve(message.result);
  }
});
function call(method,params={},sessionId){return new Promise((resolve,reject)=>{
  if(closed){reject(Error('Chrome pipe is closed'));return;}
  const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout: ${method}`));},30000);
  pending.set(id,{resolve,reject,timer});browser.stdio[3].write(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');
});}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
  const {targetId}=await call('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
  const command=(method,params)=>call(method,params,sessionId);
  const evaluate=async expression=>{const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  await command('Page.enable');await command('Runtime.enable');
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:pathToFileURL(join(output,`${theme}.html`)).href+'#node=webui'});
  // Wait for real page load, fonts and camera settling, without modifying animation clocks.
  for(let i=0;i<50;i++){if(await evaluate("document.readyState==='complete' && !!document.querySelector('#visual-evidence')"))break;await delay(100);}
  await evaluate('document.fonts.ready.then(()=>true)');await delay(2000);
  const frames=[],origin=Date.now();
  for(let i=0;i<3;i++){
    if(i)await delay(2000);
    const evidence=await evaluate(`(()=>({theme:document.documentElement.dataset.theme,state:document.documentElement.dataset.oceanMotion,hidden:document.hidden,compat:document.compatMode,charset:document.characterSet,waves:[...document.querySelectorAll('.ocean-wave')].map(w=>{const a=w.getAnimations()[0],m=new DOMMatrixReadOnly(getComputedStyle(w).transform);return {time:a.currentTime,playState:a.playState,x:m.m41,y:m.m42};})}))()`);
    if(evidence.theme!==theme||evidence.state!=='running'||evidence.hidden||evidence.compat!=='CSS1Compat'||evidence.charset!=='UTF-8'||evidence.waves.length!==3)throw Error('Motion capture page state invalid: '+JSON.stringify(evidence));
    const screenshot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    const bytes=Buffer.from(screenshot.data,'base64'),name=`${theme}-continuous-motion-${i}.png`;
    writeFileSync(join(output,name),bytes);frames.push({file:name,wall_ms:Date.now()-origin,sha256:createHash('sha256').update(bytes).digest('hex'),...evidence});
  }
  for(let i=1;i<frames.length;i++){
    if(frames[i].wall_ms-frames[i-1].wall_ms<1800||frames[i].sha256===frames[i-1].sha256)throw Error('No actual elapsed/pixel progression');
    if(!frames[i].waves.every((w,j)=>w.playState==='running'&&w.time>frames[i-1].waves[j].time+1500&&Math.abs(w.x-frames[i-1].waves[j].x)>8))throw Error('Ocean motion not visibly progressing');
  }
  writeFileSync(join(output,`${theme}-continuous-motion.json`),JSON.stringify({kind:'Unforced real wall-clock browser frames; no animation seeking or virtual time',frames},null,2)+'\n');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  writeFileSync(join(output,`${theme}-continuous-motion.log`),logs);
  try{await call('Browser.close');}catch{}
  const killTimer=setTimeout(()=>browser.kill('SIGKILL'),3000);
  await exited;clearTimeout(killTimer);rmSync(profile,{recursive:true,force:true});
});
