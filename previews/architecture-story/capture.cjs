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
const geometry=`(()=>{const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};const overlap=(a,b)=>Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x)>1&&Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y)>1;const problems=[];for(const selector of ['.part','.family-clusters button','.tile','.ports button,.spine','.scene-children button','.scene-ports button','.region-label','.actual-child>rect']){const rs=[...document.querySelectorAll(selector)].map(rect);for(let i=0;i<rs.length;i++)for(let j=i+1;j<rs.length;j++)if(overlap(rs[i],rs[j]))problems.push(selector+':'+i+'/'+j)}for(const e of document.querySelectorAll('.part,.family-clusters button,.ports button,.spine,.scene-children button,.scene-ports button,.region-label'))if(e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1)problems.push('clipped:'+e.textContent);const box=document.querySelector('.focused-scene')?.getBoundingClientRect();const outside=[];if(box)for(const e of document.querySelectorAll('.scene-heading,.scene-core,.scene-field-heading,.family-field,.scene-evidence-tools,.scene-bottom')){const r=e.getBoundingClientRect();if(r.width&&r.height&&(r.left<box.left-1||r.right>box.right+1||r.top<box.top-1||r.bottom>box.bottom+1))outside.push(e.className)}for(const t of document.querySelectorAll('.actual-child text')){const r=t.getBoundingClientRect();if(!r.width||!r.height)continue;const b=t.parentElement.querySelector('rect').getBoundingClientRect();if(r.left<b.left-1||r.right>b.right+1||r.top<b.top-1||r.bottom>b.bottom+1)problems.push('node label outside rectangle');const px=parseFloat(getComputedStyle(t).fontSize)*Math.abs(t.getScreenCTM().a);if(px<11.9)problems.push('unreadable node label')}return {outsideNodeBox:outside,overlaps:problems,overflow:document.documentElement.scrollWidth>innerWidth+1,tiles:document.querySelectorAll('.tile').length,families:document.querySelectorAll('[data-cluster]').length,mosaicRegions:document.querySelectorAll('.family-field svg>rect[fill="none"]').length,font:getComputedStyle(document.body).fontFamily,inter:document.fonts.check('15px Inter'),animations:document.getAnimations().filter(a=>a.playState==='running').length,selected:decodeURIComponent(location.hash.slice(1))};})()`;
(async()=>{
  for(const node of ['arbora','webui','eg.decide','webui.api.gen'])for(const scenario of [
    {name:'desktop',width:1440,height:1000,theme:'light'},
    {name:'mobile',width:390,height:844,theme:'light'},
    {name:'dark-reduced',width:1440,height:1000,theme:'dark'},
    {name:'layout-200pct',width:1440,height:1000,theme:'light',zoom:2}
  ]){
    const receipt={node,scenario:scenario.name,passed:false,zoomEvidence:scenario.zoom?'CSS 200% layout stress; NOT native browser zoom proof':'none'};
    const {targetId}=await call('Target.createTarget',{url:'about:blank'});
    try{
      const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
      const command=(method,params)=>call(method,params,sessionId);
      const evaluate=async expression=>{const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
      await command('Page.enable');await command('Runtime.enable');
      await command('Emulation.setDeviceMetricsOverride',{width:scenario.width,height:scenario.height,deviceScaleFactor:1,mobile:false});
      await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:scenario.theme},{name:'prefers-reduced-motion',value:'reduce'}]});
      await command('Page.navigate',{url:pathToFileURL(join(output,'prototype.html')).href+'#'+node});
      for(let i=0;i<100;i++){if(await evaluate("document.readyState==='complete'&&!!document.querySelector('h1')"))break;await delay(50);}
      await evaluate('document.fonts.ready.then(()=>true)');
      if(scenario.zoom)await evaluate('document.documentElement.style.zoom="2";true');
      await delay(150);
      receipt.geometry=await evaluate(geometry);
      const viewport=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      writeFileSync(join(output,`${node}-${scenario.name}-viewport.png`),Buffer.from(viewport.data,'base64'));
      await evaluate("(document.querySelector('.family-field')||[...document.querySelectorAll('h2')].find(e=>e.textContent==='Requirement mosaic'))?.scrollIntoView();true");await delay(100);
      const mosaicView=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      writeFileSync(join(output,`${node}-${scenario.name}-mosaic-viewport.png`),Buffer.from(mosaicView.data,'base64'));
      await evaluate('window.scrollTo(0,0);true');await delay(100);
      const metrics=await command('Page.getLayoutMetrics');
      const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:metrics.cssContentSize.width,height:metrics.cssContentSize.height,scale:1}});
      const name=`${node}-${scenario.name}.png`;const bytes=Buffer.from(shot.data,'base64');writeFileSync(join(output,name),bytes);receipt.screenshot={file:name,sha256:createHash('sha256').update(bytes).digest('hex')};
      const g=receipt.geometry;if(g.outsideNodeBox.length||g.overlaps.length||g.overflow||g.tiles>64||g.families>12||g.mosaicRegions>12||g.animations||!g.inter||!g.font.includes('Inter')||g.selected!==node)throw Error('Geometry/font/budget failure: '+JSON.stringify(g));
      receipt.sourceLinks=await evaluate(`(()=>{const links=[...document.querySelectorAll('.tile')];return {count:links.length,valid:links.every(e=>e.href.startsWith('https://github.com/Knuckles-Team/')&&e.href.includes('/requirements.md')&&!!e.getAttribute('aria-label')&&e.rel.includes('noopener'))}})()`);
      if(!receipt.sourceLinks.valid)throw Error('Invalid evidence anchor');
      receipt.svgNavigation=[];
      if(await evaluate("!!document.querySelector('.actual-child')")){
        const beforeLabels=await evaluate("[...document.querySelectorAll('.actual-child text')].filter(e=>getComputedStyle(e).display!=='none').length");
        await evaluate("document.querySelector('#inbox-graph-zoom').focus();true");
        await command('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End',windowsVirtualKeyCode:35,nativeVirtualKeyCode:35});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'End',code:'End',windowsVirtualKeyCode:35,nativeVirtualKeyCode:35});await delay(100);
        receipt.boundedZoom=await evaluate("({value:document.querySelector('#inbox-graph-zoom').value,visibleLabels:[...document.querySelectorAll('.actual-child text')].filter(e=>getComputedStyle(e).display!=='none').length,kind:'bounded SVG zoom, not infinite canvas zoom'})");
        if(receipt.boundedZoom.value!=='4'||receipt.boundedZoom.visibleLabels<beforeLabels)throw Error('Readable labels failed to reappear at bounded zoom');
        const child=await evaluate("document.querySelector('.actual-child').dataset.go");
        for(const key of ['Enter',' ']){
          await evaluate(`(()=>{const g=[...document.querySelectorAll('.actual-child')].find(e=>e.dataset.go===${JSON.stringify(child)});g.focus();window.__svgKeys=[];g.addEventListener('keydown',e=>window.__svgKeys.push({key:e.key,trusted:e.isTrusted}));return true;})()`);
          const keyCode=key==='Enter'?13:32;const code=key==='Enter'?'Enter':'Space';
          await command('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:keyCode,nativeVirtualKeyCode:keyCode,text:key==='Enter'?'\r':' ',unmodifiedText:key==='Enter'?'\r':' '});await command('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:keyCode,nativeVirtualKeyCode:keyCode});await delay(100);
          const opened=await evaluate("({hash:decodeURIComponent(location.hash.slice(1)),active:document.activeElement.tagName,events:window.__svgKeys})");
          if(opened.hash!==child||opened.active!=='H1'||!opened.events.some(e=>e.key===key&&e.trusted))throw Error('SVG exact-child activation failed for '+key);
          await evaluate('history.back();true');await delay(120);
          const restored=await evaluate("({hash:decodeURIComponent(location.hash.slice(1)),active:document.activeElement.dataset.go,tag:document.activeElement.tagName})");
          if(restored.hash!==node||restored.active!==child||restored.tag.toLowerCase()!=='g')throw Error('SVG Back focus restoration failed');
          receipt.svgNavigation.push({key,child,opened,restored});
        }
      }
      // The primary scene is captured before entering its accessible inspection route.
      await evaluate("document.querySelector('#open-inspection').focus();true");
      await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await delay(100);
      receipt.inspection=await evaluate("({present:!!document.querySelector('#tile-list'),active:document.activeElement.tagName,tiles:document.querySelectorAll('.tile').length,families:document.querySelectorAll('[data-cluster]').length})");
      if(!receipt.inspection.present||receipt.inspection.active!=='H1'||receipt.inspection.tiles>64||receipt.inspection.families>12)throw Error('Inspection/focus/budget failed');
      receipt.sourceLinks=await evaluate(`(()=>{const links=[...document.querySelectorAll('.tile')];return {count:links.length,valid:links.every(e=>e.href.startsWith('https://github.com/Knuckles-Team/')&&e.href.includes('/requirements.md')&&!!e.getAttribute('aria-label')&&e.rel.includes('noopener'))}})()`);
      if(!receipt.sourceLinks.count||!receipt.sourceLinks.valid)throw Error('Invalid inspection evidence anchors');
      // Real CDP key events activate native disclosure; no synthetic key dispatch.
      if(await evaluate("!!document.querySelector('#tile-list')")){
        await evaluate("document.querySelector('#tile-list summary').focus();window.__trustedKeys=[];document.addEventListener('keydown',e=>window.__trustedKeys.push({key:e.key,trusted:e.isTrusted}));true");
        await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await delay(50);
        receipt.keyboard=await evaluate("({open:document.querySelector('#tile-list').open,rows:document.querySelectorAll('#tile-list li').length,events:window.__trustedKeys,active:document.activeElement.tagName})");
        if(!receipt.keyboard.open||receipt.keyboard.rows>64||!receipt.keyboard.events.some(e=>e.key==='Enter'&&e.trusted))throw Error('Trusted keyboard disclosure failed');
      }
      const target=node==='webui.api.gen'?'arbora':'webui.api.gen';
      await evaluate(`document.querySelector('[data-example="${target}"]').focus();true`);
      await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await delay(100);
      receipt.navigation=await evaluate("({hash:location.hash,active:document.activeElement.tagName})");
      if(receipt.navigation.hash!=='#'+target||receipt.navigation.active!=='H1')throw Error('Example navigation/focus failed');
      await evaluate('history.back();true');await delay(100);
      if(await evaluate('location.hash')!=='#'+node)throw Error('Back failed to restore node');
      receipt.passed=true;
    }catch(error){receipt.error=String(error);process.exitCode=1;}
    finally{results.push(receipt);writeFileSync(join(output,'browser-checks.json'),JSON.stringify({kind:'Exact study browser captures; no canonical deployment',results},null,2));await call('Target.closeTarget',{targetId});}
  }
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  writeFileSync(join(output,'browser.log'),logs);
  try{await call('Browser.close');}catch{}
  const killTimer=setTimeout(()=>browser.kill('SIGKILL'),3000);await exited;clearTimeout(killTimer);rmSync(profile,{recursive:true,force:true});
});
