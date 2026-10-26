/* Real wall-clock Chrome capture, using only Node built-ins and the runner's browser.
 * No virtual time, animation seeking, synthetic frames, browser download or network service.
 */
const {spawn}=require('node:child_process');
const {mkdtempSync,writeFileSync,rmSync,readFileSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join,resolve}=require('node:path');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');
const [chrome,directory]=process.argv.slice(2), output=resolve(directory);
const profile=mkdtempSync(join(tmpdir(),'architecture-story-'));
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
const results=[];
(async()=>{
 for(const device of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}])for(const node of ['arbora','webui','eg.decide'])for(const route of ['center','left-gap']){
  if(route==='left-gap'&&results.some(r=>r.device===device.name&&r.node===node&&r.story?.owner===node&&r.story?.placement==='canvas'))continue;
  const pages=[];let fullPageCaptured=false;
  try{
   for(const variant of ['baseline','preview']){
    const {targetId}=await call('Target.createTarget',{url:'about:blank'});
    const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
    const command=(method,params)=>call(method,params,sessionId);
    const evaluate=async expression=>{const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
    await command('Page.enable');await command('Runtime.enable');
    await command('Emulation.setDeviceMetricsOverride',{width:device.width,height:device.height,deviceScaleFactor:1,mobile:false});
    await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    await command('Page.navigate',{url:pathToFileURL(join(output,variant+'.html')).href+'#node='+node});
    for(let i=0;i<100;i++){if(await evaluate('!!window.__arch && document.readyState==="complete"'))break;await delay(50);}
    await evaluate('document.fonts.ready.then(()=>true)');await delay(700);
    pages.push({targetId,variant,command,evaluate});
   }
   for(let step=0;step<12;step++){
    const states=[];
    for(const page of pages){
     await page.command('Page.bringToFront');
     await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))');
     await delay(150);
     {
      const fraction=route==='center'?.5:.2;
      const p=await page.evaluate(`(()=>{const r=document.querySelector("#cv").getBoundingClientRect();return {x:r.x+r.width*${fraction},y:r.y+r.height/2}})()`);
      const before=await page.evaluate('({...__arch.cam})'),delta=step?-160:-1;
      await page.command('Input.dispatchMouseEvent',{type:'mouseWheel',...p,deltaX:0,deltaY:delta});
      const expected=Math.max(.02,Math.min(before.k*Math.exp(-delta*.0016),4e6));
      let matched=false;
      for(let tick=0;tick<30;tick++){await delay(100);const actual=await page.evaluate('__arch.cam.k');if(Math.abs(actual-expected)<=Math.max(1,expected)*1e-12){matched=true;break;}}
      if(!matched){writeFileSync(join(output,'wheel-failure.json'),JSON.stringify({device,node,route,step,variant:page.variant,before,expected,actual:await page.evaluate('({...__arch.cam})')}));throw Error('Trusted wheel camera formula did not settle');}
      await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))');await delay(450);
     }
     states.push(await page.evaluate(`(()=>{const ids=[];const walk=n=>{ids.push(n.id);n.children.forEach(walk)};walk(PAYLOAD.tree);const r=document.querySelector('#cv').getBoundingClientRect();return {cam:{...__arch.cam},focus:__arch.focus,rects:ids.map(id=>[id,__arch.rect(id)]),canvas:[r.x,r.y,r.width,r.height],controls:[...document.querySelectorAll('button,input,select')].map(e=>[e.tagName,e.id,e.textContent]),story:window.__storyQA?__storyQA():null}})()`));
    }
    for(const field of ['cam','rects','canvas','controls'])if(JSON.stringify(states[0][field])!==JSON.stringify(states[1][field])){writeFileSync(join(output,'invariant-failure.json'),JSON.stringify({device,node,route,step,field,states},null,2));throw Error('Native invariant changed: '+field);}
    const story=states[1].story,mask=story?.placement==='canvas'?story.rect:null,hashes=[];
    if(mask){
     const prior=results.filter(r=>r.device===device.name&&r.node===node&&r.route===route&&r.story?.placement==='canvas'&&r.story.owner===story.owner&&r.story.tier===story.tier).at(-1);
     if(prior&&(prior.story.index!==story.index||prior.story.kind!==story.kind||prior.story.align!==story.align))throw Error('Story anchor jumped inside native zoom tier');
     const text=story.layout.ops.filter(op=>op.type==='text');
     for(const op of text)if(op.x<0||op.x+op.width>story.rect[2]+.01||op.y<0||op.y+op.height>story.rect[3]||op.size<11)throw Error('Unreadable or out-of-bounds story text');
     for(let i=0;i<text.length;i++)for(let j=i+1;j<text.length;j++){const a=text[i],b=text[j];if(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y)throw Error('Story labels overlap');}
    }
    if(mask){
     const clear=await pages[1].evaluate(`(()=>{const s=__storyQA(),r=s.rect,p=[r[0]-8,r[1]-8,r[2]+16,r[3]+16];const hit=(a,b)=>a[0]<b[0]+b[2]&&a[0]+a[2]>b[0]&&a[1]<b[1]+b[3]&&a[1]+a[3]>b[1];return !s.obstacles.some(b=>hit(p,b))})()`);
     if(!clear)throw Error('Story overlaps reserved geometry');
    }
    for(const page of pages){
     await page.command('Page.bringToFront');
     await page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))');
     await delay(150);
     hashes.push(await page.evaluate(`(()=>{const c=document.querySelector('#cv'),a=c.getContext('2d').getImageData(0,0,c.width,c.height).data,r=${JSON.stringify(mask)},ratio=c.width/c.getBoundingClientRect().width;let h=2166136261;for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){if(r&&x>=(r[0]-2)*ratio&&x<=(r[0]+r[2]+2)*ratio&&y>=(r[1]-2)*ratio&&y<=(r[1]+r[3]+2)*ratio)continue;const i=(y*c.width+x)*4;for(let k=0;k<4;k++)h=Math.imul(h^a[i+k],16777619)}return h>>>0})()`));
     const shot=await page.command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});writeFileSync(join(output,`${device.name}-${node}-${route}-${step}-${page.variant}.png`),Buffer.from(shot.data,'base64'));
     if(device.name==='mobile'&&mask&&!fullPageCaptured){
      const beforeScroll=await page.evaluate('({cam:{...__arch.cam},scrollY,rect:(()=>{const r=document.querySelector("#cv").getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()})');
      await page.command('Input.dispatchMouseEvent',{type:'mouseWheel',x:20,y:20,deltaX:0,deltaY:350});await delay(600);
      const scrolled=await page.evaluate('({cam:{...__arch.cam},scrollY,rect:(()=>{const r=document.querySelector("#cv").getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()})');
      const sameCam=JSON.stringify(scrolled.cam)===JSON.stringify(beforeScroll.cam),sameSize=JSON.stringify(scrolled.rect.slice(2))===JSON.stringify(beforeScroll.rect.slice(2));
      const wholePlot=scrolled.rect[1]+mask[1]>=0&&scrolled.rect[1]+mask[1]+mask[3]<=device.height;
      writeFileSync(join(output,`${device.name}-${node}-${route}-${step}-${page.variant}-scroll.json`),JSON.stringify({beforeScroll,scrolled,sameCam,sameSize,wholePlot},null,2));
      if(!sameCam||!sameSize||!wholePlot)throw Error('Native document scroll changed map geometry or did not expose complete chart');
      const full=await page.command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      writeFileSync(join(output,`${device.name}-${node}-${route}-${step}-${page.variant}-footer.png`),Buffer.from(full.data,'base64'));
      await page.command('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home',windowsVirtualKeyCode:36});
      await page.command('Input.dispatchKeyEvent',{type:'keyUp',key:'Home',code:'Home',windowsVirtualKeyCode:36});await delay(600);
      const restored=await page.evaluate('({cam:{...__arch.cam},scrollY,rect:(()=>{const r=document.querySelector("#cv").getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()})');
      if(JSON.stringify(restored)!==JSON.stringify(beforeScroll)){writeFileSync(join(output,'scroll-restore-failure.json'),JSON.stringify({beforeScroll,restored}));throw Error('Native Home did not restore exact map bounds');}
     }
    }
    if(device.name==='mobile'&&mask)fullPageCaptured=true;
    if(hashes[0]!==hashes[1])throw Error('Existing canvas pixels changed outside chart bounds');
    results.push({device:device.name,node,route,step,camera:states[1].cam,focus:states[1].focus,story,geometryEqual:true,outsideChartPixelHash:hashes[0]});
    writeFileSync(join(output,'native-proof.json'),JSON.stringify(results,null,2));
   }
  }finally{for(const page of pages)await call('Target.closeTarget',{targetId:page.targetId});}
 }
 for(const device of ['desktop','mobile'])for(const node of ['arbora','webui','eg.decide'])if(!results.some(r=>r.device===device&&r.node===node&&r.story?.owner===node&&r.story?.placement==='canvas'))throw Error('No trusted mouse-wheel chart reveal on '+device+' / '+node+'; not visual proof');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  writeFileSync(join(output,'browser.log'),logs);
  try{await call('Browser.close');}catch{}
  const killTimer=setTimeout(()=>browser.kill('SIGKILL'),3000);await exited;clearTimeout(killTimer);rmSync(profile,{recursive:true,force:true});
});
