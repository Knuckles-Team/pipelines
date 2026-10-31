/* Real wall-clock Chrome capture, using only Node built-ins and the runner's browser.
 * Unforced motion proof never seeks. Separately labeled palette diagnostics sample
 * paused native timelines; no synthetic frames, browser download or network service.
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
  await command('Page.enable');await command('Runtime.enable');await command('Page.bringToFront');
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:pathToFileURL(join(output,`${theme}.html`)).href+'#node=webui'});
  // Wait for real page load, fonts and camera settling, without modifying animation clocks.
  for(let i=0;i<50;i++){if(await evaluate("document.readyState==='complete' && !!document.querySelector('#visual-evidence')"))break;await delay(100);}
  await evaluate('document.fonts.ready.then(()=>true)');await delay(2000);
  const frames=[],origin=Date.now();
  for(let i=0;i<3;i++){
    if(i)await delay(2000);
    const evidence=await evaluate(`(()=>({theme:document.documentElement.dataset.theme,state:document.documentElement.dataset.oceanMotion,hidden:document.hidden,compat:document.compatMode,charset:document.characterSet,waves:[...document.querySelectorAll('.ocean-wave')].map(w=>{const a=w.getAnimations()[0],m=new DOMMatrixReadOnly(getComputedStyle(w).transform);const tide=w.getAnimations().find(a=>a.animationName==='ocean-tide');return {time:a.currentTime,playState:a.playState,x:m.m41,y:m.m42,opacity:Number(getComputedStyle(w).opacity),tide:tide?{time:tide.currentTime,playState:tide.playState}:null};})}))()`);
    if(evidence.theme!==theme||evidence.state!=='running'||evidence.hidden||evidence.compat!=='CSS1Compat'||evidence.charset!=='UTF-8'||evidence.waves.length!==3)throw Error('Motion capture page state invalid: '+JSON.stringify(evidence));
    const screenshot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    const bytes=Buffer.from(screenshot.data,'base64'),name=`${theme}-continuous-motion-${i}.png`;
    writeFileSync(join(output,name),bytes);frames.push({file:name,wall_ms:Date.now()-origin,sha256:createHash('sha256').update(bytes).digest('hex'),...evidence});
  }
  for(let i=1;i<frames.length;i++){
    if(frames[i].wall_ms-frames[i-1].wall_ms<1800||frames[i].sha256===frames[i-1].sha256)throw Error('No actual elapsed/pixel progression');
    if(!frames[i].waves.every((w,j)=>w.playState==='running'&&w.time>frames[i-1].waves[j].time+1500&&Math.abs(w.x-frames[i-1].waves[j].x)>8))throw Error('Ocean motion not visibly progressing');
  }
  if(!frames.every(f=>f.waves.every(w=>w.tide?.playState==='running'))||!frames[2].waves.some((w,i)=>Math.abs(w.opacity-frames[0].waves[i].opacity)>.001))throw Error('Slow backdrop palette fade did not progress');
  writeFileSync(join(output,`${theme}-continuous-motion.json`),JSON.stringify({kind:'Unforced real wall-clock browser frames; no animation seeking or virtual time',frames},null,2)+'\n');
  // Camera-synced background: one real flight, sampled on every animation frame. The ocean scene's
  // pan and tint properties must change on the camera's frames, and must not move under reduced motion.
  const sampleFlight=target=>evaluate(`(async()=>{
    const a=window.__arch,scene=document.querySelector('.ocean-scene'),rows=[];
    a.go('${target}');
    await new Promise(done=>{const t0=performance.now();const tick=()=>{
      const cs=getComputedStyle(scene);
      rows.push({camX:a.cam.x,camY:a.cam.y,camK:a.cam.k,w:document.getElementById('cv').getBoundingClientRect().width,h:document.getElementById('cv').getBoundingClientRect().height,root:a.rect('root'),panX:scene.style.getPropertyValue('--ocean-pan-x'),panY:scene.style.getPropertyValue('--ocean-pan-y'),tint:scene.style.getPropertyValue('--ocean-tint'),flight:document.documentElement.dataset.oceanFlight||'',wave:getComputedStyle(document.querySelector('.ocean-wave')).translate});
      if(performance.now()-t0>2500)done();else requestAnimationFrame(tick);};requestAnimationFrame(tick);});
    return rows;
  })()`);
  const flight=await sampleFlight('root');
  // Frame count depends on the runner; the contract is per frame: the background pan equals the pan computed
  // from the camera of that same frame, and at least two different camera frames were observed.
  const expected=r=>{const k=r.camK,cx=r.camX+r.w/(2*k),cy=r.camY+r.h/(2*k);return [-((cx-(r.root[0]+r.root[2]/2))/r.root[2])*120,-((cy-(r.root[1]+r.root[3]/2))/r.root[3])*60];};
  for(const r of flight){const [ex,ey]=expected(r);if(Math.abs(parseFloat(r.panX)-ex)>.01||Math.abs(parseFloat(r.panY)-ey)>.01)throw Error('Ocean pan is not the camera of the same frame: '+JSON.stringify(r));}
  if(new Set(flight.map(r=>r.camX)).size<2||new Set(flight.map(r=>r.panX)).size<2||new Set(flight.map(r=>r.wave)).size<2)throw Error('Ocean parallax did not change across the flight frames');
  if(!flight.some(r=>r.flight==='on'))throw Error('Ocean flight state never started with the camera');
  if(flight[flight.length-1].flight!=='')throw Error('Ocean flight state did not end with the camera');
  await evaluate("window.__arch.go('webui',{instant:true});true");await delay(300);
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});await delay(300);
  const calm=await sampleFlight('root');
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});await delay(300);
  if(new Set(calm.map(r=>r.panX)).size!==1||new Set(calm.map(r=>r.wave)).size!==1||calm.some(r=>r.flight==='on'))throw Error('Ocean moved under prefers-reduced-motion');
  writeFileSync(join(output,`${theme}-camera-synced-background.json`),JSON.stringify({kind:'Real camera flight, per-frame ocean scene properties',flight,reduced:calm},null,2)+'\n');
  await evaluate("window.__arch.go('webui',{instant:true});true");await delay(500);
  // Diagnostic only: sample the unchanged 48/56/64-second alternating palette
  // timelines while paused. These are actual browser pixels, NOT elapsed video.
  // The unforced wall-clock frames above remain untouched and separately labeled.
  const paletteClip=await evaluate("(()=>{const r=document.getElementById('cv').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,scale:1};})()");
  const palette={kind:'Paused native palette timeline diagnostics; canvas-only browser captures, not real-time video',theme,clip:paletteClip,samples:[]};
  const paletteSetup=await evaluate(`(()=>{
    window.__paletteSaved=[...document.querySelectorAll('.ocean-wave')].flatMap(w=>w.getAnimations()).map(a=>({a,time:a.currentTime,state:a.playState}));
    window.__paletteSaved.forEach(s=>s.a.pause());
    const waves=[...document.querySelectorAll('.ocean-wave')],times=new Set([0,64000,128000]);
    const metadata=waves.map(w=>{const a=w.getAnimations().find(a=>a.animationName==='ocean-tide'),timing=a.effect.getTiming();
      for(const phase of [0,.5,1,1.5,2]){const t=timing.delay+timing.duration*phase;if(t>=0&&t<=128000)times.add(t);}
      return {duration:timing.duration,delay:timing.delay,direction:timing.direction,keyframes:a.effect.getKeyframes(),maxOpacity:Number(getComputedStyle(w).getPropertyValue('--wave-opacity')),background:getComputedStyle(w).backgroundImage};});
    return {metadata,times:[...times].sort((a,b)=>a-b)};
  })()`);
  palette.keyframes=paletteSetup.metadata;
  try{
    for(const time of paletteSetup.times){
      const state=await evaluate(`(async()=>{
        const waves=[...document.querySelectorAll('.ocean-wave')];waves.forEach(w=>w.getAnimations().find(a=>a.animationName==='ocean-tide').currentTime=${time});
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        return {theme:document.documentElement.dataset.theme,waves:waves.map(w=>{const a=w.getAnimations().find(a=>a.animationName==='ocean-tide');return {opacity:Number(getComputedStyle(w).opacity),time:a.currentTime,playState:a.playState,progress:a.effect.getComputedTiming().progress};})};
      })()`);
      if(state.theme!==theme||state.waves.some(w=>w.playState!=='paused'))throw Error('Palette diagnostic did not freeze native timeline');
      const sample={timeline_ms:time,...state};
      if([0,64000,128000].includes(time)){
        const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,clip:paletteClip});
        const bytes=Buffer.from(shot.data,'base64'),file=`${theme}-palette-timeline-${time/1000}s.png`;
        writeFileSync(join(output,file),bytes);sample.screenshot={file,sha256:createHash('sha256').update(bytes).digest('hex')};
      }
      palette.samples.push(sample);
    }
    for(let i=0;i<3;i++){
      const values=palette.samples.map(s=>s.waves[i].opacity),cap=palette.keyframes[i].maxOpacity;
      if(Math.abs(Math.min(...values)-cap*.55)>.0001||Math.abs(Math.max(...values)-cap)>.0001)throw Error('Full palette opacity extrema not sampled');
    }
    palette.passed=true;
  }finally{
    await evaluate("window.__paletteSaved.forEach(s=>{s.a.currentTime=s.time;if(s.state==='running')s.a.play();});delete window.__paletteSaved;true");
    writeFileSync(join(output,`${theme}-palette-timeline.json`),JSON.stringify(palette,null,2)+'\n');
  }
  // Semantic caption proof uses only the existing controls after the untouched motion frames.
  const navigation={kind:'Real native zoom input, unchanged world geometry, and actual caption paint',theme,steps:[]};
  const key=async(key,code,virtual)=>{
    const text=key==='Enter'?'\r':key.length===1?key:undefined;
    await command('Input.dispatchKeyEvent',{type:'keyDown',key,code,text,unmodifiedText:text,windowsVirtualKeyCode:virtual,nativeVirtualKeyCode:virtual});
    await command('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:virtual,nativeVirtualKeyCode:virtual});
  };
  const screenshot=async(name)=>{
    const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    const bytes=Buffer.from(shot.data,'base64'),file=`${theme}-native-caption-${name}.png`;
    writeFileSync(join(output,file),bytes);return {file,sha256:createHash('sha256').update(bytes).digest('hex')};
  };
  const state=()=>evaluate(`(()=>{const a=window.__arch,c=document.getElementById('cv'),r=c.getBoundingClientRect();return {cam:{...a.cam},selected:a.selected,hash:location.hash,canvas:{x:r.x,y:r.y,w:r.width,h:r.height},labels:a.annotations().labels,paint:window.__nativeCaptionPaint,geometryUnchanged:JSON.stringify(window.__nativeIds.map(id=>[id,a.rect(id)]))===window.__nativeGeometry,active:document.activeElement.id,focusVisible:document.activeElement.matches(':focus-visible'),fullscreen:document.fullscreenElement?.id||null,events:window.__nativeEvents};})()`);
  const identity=a=>[a.owner,a.kind,a.fullText].join('|');
  const actualCaption=(label,paint)=>label.placement==='canvas'&&paint.some(p=>p.text===label.text&&Math.abs(p.x-(label.rect[0]+(label.marker?12:0)))<.01&&Math.abs(p.y-label.rect[1])<.01);
  const assertGeometry=s=>{if(!s.geometryUnchanged)throw Error('Native zoom changed original node positions/sizes');};
  const assertZoom=(before,after,factor,sx,sy)=>{
    const k=Math.max(.02,Math.min(before.cam.k*factor,4e6));
    const expected={k,x:before.cam.x+sx/before.cam.k-sx/k,y:before.cam.y+sy/before.cam.k-sy/k};
    for(const p of ['x','y','k'])if(Math.abs(after.cam[p]-expected[p])>1e-6*Math.max(1,Math.abs(expected[p])))throw Error('Existing zoomAt camera formula changed: '+JSON.stringify({before:before.cam,after:after.cam,expected}));
    assertGeometry(after);return expected;
  };
  try{
    navigation.geometry=await evaluate(`(()=>{
      if(document.querySelector('#annotations,#annotation-list,#annotation-jump,dialog,[role=dialog]'))throw Error('Unexpected caption controls/rail/popup');
      window.__nativeIds=[];(function visit(n){window.__nativeIds.push(n.id);n.children.forEach(visit);})(PAYLOAD.tree);
      window.__nativeGeometry=JSON.stringify(window.__nativeIds.map(id=>[id,window.__arch.rect(id)]));window.__nativeEvents=[];window.__nativeCaptionPaint=[];
      const prototype=CanvasRenderingContext2D.prototype,fill=prototype.fillText,clear=prototype.clearRect;
      prototype.clearRect=function(...args){window.__nativeCaptionPaint=[];return clear.apply(this,args);};
      prototype.fillText=function(text,x,y,...args){const m=this.measureText(text);window.__nativeCaptionPaint.push({text:String(text),x,y,font:this.font,ink:[x-m.actualBoundingBoxLeft,y-m.actualBoundingBoxAscent,m.actualBoundingBoxLeft+m.actualBoundingBoxRight,m.actualBoundingBoxAscent+m.actualBoundingBoxDescent]});return fill.call(this,text,x,y,...args);};
      for(const type of ['keydown','wheel','click'])document.addEventListener(type,e=>window.__nativeEvents.push({type:e.type,key:e.key||null,trusted:e.isTrusted,target:e.target.id,offsetX:e.offsetX,offsetY:e.offsetY,deltaY:e.deltaY,ctrlKey:e.ctrlKey}),true);
      return JSON.parse(window.__nativeGeometry);
    })()`);
    await evaluate("window.__arch.go('root',{instant:true});window.scrollTo(0,0);true");await delay(700);
    const low=await state();assertGeometry(low);
    const deferred=low.labels.filter(a=>['flow','zone','loop'].includes(a.kind)&&a.placement==='deferred'&&a.reason==='scale');
    if(!deferred.length)throw Error('No low-scale deferred caption coverage');
    navigation.low={...low,screenshot:await screenshot('low')};
    await evaluate("document.getElementById('zin').focus();true");
    await key('Enter','Enter',13);await delay(350);
    let current=await state();
    const buttonStep={input:'existing zoom-in button via trusted Enter',after:current};navigation.steps.push(buttonStep);
    buttonStep.expected=assertZoom(low,current,1.6,low.canvas.w/2,low.canvas.h/2);
    await evaluate("document.getElementById('cv').focus();true");
    const keyboardBefore=await state();
    await key('+','Equal',187);await delay(350);
    current=await state();
    navigation.steps.push({input:'existing focused-canvas keyboard +',expected:assertZoom(keyboardBefore,current,1.4,keyboardBefore.canvas.w/2,keyboardBefore.canvas.h/2),after:current});
    if(current.active!=='cv'||!current.focusVisible)throw Error('Canvas keyboard focus not retained/visible');
    let appeared=current.labels.find(a=>deferred.some(d=>identity(d)===identity(a))&&actualCaption(a,current.paint));
    // If a center zoom moved the relevant caption out of view, try at most six
    // visible low-scale anchors using ordinary wheel input, never rewriting the camera.
    const anchors=deferred.filter(a=>Number.isFinite(a.x)&&Number.isFinite(a.y)&&a.x>=0&&a.x<=low.canvas.w&&a.y>=0&&a.y<=low.canvas.h).slice(0,6);
    for(const anchor of anchors){
      if(appeared)break;
      await evaluate("window.__arch.go('root',{instant:true});true");await delay(350);
      for(let step=0;step<3&&!appeared;step++){
        const before=await state(),sx=Math.max(10,Math.min(before.canvas.w-10,anchor.x)),sy=Math.max(10,Math.min(before.canvas.h-10,anchor.y));
        const deltaY=-Math.log(1.8)/.0016;
        await command('Input.dispatchMouseEvent',{type:'mouseWheel',x:before.canvas.x+sx,y:before.canvas.y+sy,deltaX:0,deltaY});await delay(350);
        current=await state();
        const wheel=current.events.slice(before.events.length).find(e=>e.type==='wheel'&&e.trusted&&e.target==='cv');
        if(!wheel)throw Error('Trusted wheel did not reach the canvas');
        navigation.steps.push({input:'trusted native wheel',anchor:identity(anchor),wheel,expected:assertZoom(before,current,Math.exp(-wheel.deltaY*(wheel.ctrlKey?.01:.0016)),wheel.offsetX,wheel.offsetY),after:current});
        appeared=current.labels.find(a=>deferred.some(d=>identity(d)===identity(a))&&actualCaption(a,current.paint));
      }
    }
    if(!appeared)throw Error('No initially deferred caption became genuinely painted through bounded native zoom');
    if(appeared.fs<9||appeared.fs<=deferred.find(d=>identity(d)===identity(appeared)).fs)throw Error('Caption appearance did not follow native scale increase');
    navigation.appearance={caption:appeared,before:deferred.find(d=>identity(d)===identity(appeared)),paint:current.paint.filter(p=>p.text===appeared.text),screenshot:await screenshot('revealed')};
    if(!current.events.some(e=>e.type==='keydown'&&e.key==='Enter'&&e.trusted)||!current.events.some(e=>e.type==='keydown'&&e.key==='+'&&e.trusted))throw Error('Trusted native zoom input evidence missing');
    // Existing F control still enters/exits real browser fullscreen, with no caption UI.
    await evaluate("document.getElementById('cv').focus();true");await key('f','KeyF',70);await delay(700);
    const fullscreen=await state();assertGeometry(fullscreen);
    if(fullscreen.fullscreen!=='wrap')throw Error('Existing F control did not enter real fullscreen');
    await key('f','KeyF',70);await delay(700);
    const normal=await state();assertGeometry(normal);
    if(normal.fullscreen)throw Error('Existing F control did not exit fullscreen');
    navigation.fullscreen={entered:fullscreen.fullscreen,exited:normal.fullscreen,geometryUnchanged:normal.geometryUnchanged};navigation.passed=true;
  }catch(error){navigation.passed=false;navigation.error=String(error);throw error;}
  finally{writeFileSync(join(output,`${theme}-native-caption-zoom.json`),JSON.stringify(navigation,null,2)+'\n');}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  writeFileSync(join(output,`${theme}-continuous-motion.log`),logs);
  try{await call('Browser.close');}catch{}
  const killTimer=setTimeout(()=>browser.kill('SIGKILL'),3000);
  await exited;clearTimeout(killTimer);rmSync(profile,{recursive:true,force:true});
});
