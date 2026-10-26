const STORY = /*__STORY__*/null;
const SOURCE_VIEW = /*__SOURCE_VIEW__*/null;
// LOCAL candidate only. Native geometry/camera/controls are not modified.
const storyAnchorSets=new Map(),storyAnchorChoices=new Map();
let storyEvidence={placement:'deferred',reason:'initial'};
const storyCap=(s,n)=>{const a=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(s)].map(x=>x.segment):Array.from(s);return a.length<=n?s:a.slice(0,n-1).join('')+'…';};
function storyFit(text,width){
  const chars=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text)].map(x=>x.segment):Array.from(text);
  if(ctx.measureText(text).width<=width)return text;
  while(chars.length&&ctx.measureText(chars.join('')+'…').width>width)chars.pop();
  return chars.length?chars.join('')+'…':'';
}
function compactStoryGroups(data){
  if(data.groups.length<=3)return data.groups;
  const rest=data.groups.slice(2);
  return [...data.groups.slice(0,2),{key:(data.familyCount-2)+' other families',label:(data.familyCount-2)+' other families',total:rest.reduce((n,g)=>n+g.total,0),counts:Object.fromEntries(ST.map(s=>[s,rest.reduce((n,g)=>n+g.counts[s],0)]))}];
}
function nodeStoryAnchors(id){
  if(storyAnchorSets.has(id))return storyAnchorSets.get(id);
  const r=R[id],children=nodes[id].children.map(c=>R[c.id]).filter(Boolean);
  const left=r[0]+r[2]*.015,top=r[1]+r[3]*.105,right=r[0]+r[2]*.985,bottom=r[1]+r[3]*.985;
  const gridX=Array.from({length:20},(_,i)=>(i+1)/21).map(f=>r[0]+r[2]*f),gridY=Array.from({length:20},(_,i)=>(i+1)/21).map(f=>r[1]+r[3]*f);
  const xs=[left,...gridX,...children.map(c=>c[0]+c[2]+r[2]*.012)].filter(x=>x<right);
  const ys=[top,...gridY,...children.map(c=>c[1]+c[3]+r[3]*.018)].filter(y=>y<bottom);
  const points=[],seen=new Set();
  for(const y of ys)for(const x of xs){
    const key=x+':'+y;if(seen.has(key))continue;seen.add(key);
    if(children.some(c=>x>=c[0]&&x<=c[0]+c[2]&&y>=c[1]&&y<=c[1]+c[3]))continue;
    let w=right-x,h=bottom-y;
    for(const c of children){if(c[0]>=x&&c[1]<=y&&c[1]+c[3]>=y)w=Math.min(w,c[0]-x);if(c[1]>=y&&c[0]<=x&&c[0]+c[2]>=x)h=Math.min(h,c[1]-y);}
    points.push({x,y,score:w*h,grid:gridX.includes(x)&&gridY.includes(y)});
  }
  points.sort((a,b)=>b.score-a.score||a.y-b.y||a.x-b.x);
  const interior=points.filter(p=>p.grid),other=points.filter(p=>!p.grid);
  const anchors=[...interior,...other.slice(0,512-interior.length)].sort((a,b)=>b.score-a.score||a.y-b.y||a.x-b.x);storyAnchorSets.set(id,anchors);return anchors;
}
function clearStoryRect(rect,bounds,obstacles,segments,spare=0){
  const [x,y,w,h]=rect,p=[x-8-spare,y-8-spare,w+16+2*spare,h+16+2*spare];
  return x>=Math.max(12,bounds[0]+8)&&y>=Math.max(12,bounds[1]+8)&&x+w<=Math.min(W-12,bounds[0]+bounds[2]-8)&&y+h<=Math.min(H-12,bounds[1]+bounds[3]-8)&&!obstacles.some(b=>intersects(p,b))&&!segments.some(([a,b])=>segmentHitsRect(a,b,p));
}
function chooseStory(id,data,bounds,obstacles,segments){
  const groups=compactStoryGroups(data),tier=Math.floor(Math.log2(Math.max(1,bounds[2]/640)));
  const key=id+':'+tier,anchors=nodeStoryAnchors(id),prior=storyAnchorChoices.get(key);
  const layouts=Object.fromEntries(['comparison','concentration'].map(kind=>[kind,storyLayout(kind,data,groups)]));
  const rectFor=choice=>{const p=toS(anchors[choice.index].x,anchors[choice.index].y);return [p[0]-(choice.align==='right'?280:0),p[1],280,layouts[choice.kind].height];};
  if(prior){if(!layouts[prior.kind])return null;const rect=rectFor(prior);return clearStoryRect(rect,bounds,obstacles,segments)?{...prior,rect,groups,tier,layout:layouts[prior.kind]}:null;}
  for(const kind of ['comparison','concentration']){
    if(!layouts[kind])continue;
    for(let index=0;index<anchors.length;index++)for(const align of ['left','right']){
      const choice={index,kind,align},rect=rectFor(choice);
      if(clearStoryRect(rect,bounds,obstacles,segments,12)){storyAnchorChoices.set(key,choice);return {...choice,rect,groups,tier,layout:layouts[kind]};}
    }
  }
  return null;
}
function storyLayout(kind,data,groups){
  const width=280,ops=[];let y=0,invalid=false;
  ctx.save();try{
    const line=(text,x,top,size=11,weight=400)=>{
      ctx.font=weight+' '+size+'px '+C.body;const measured=ctx.measureText(text).width;
      if(x<0||x+measured>width+.01)invalid=true;
      ops.push({type:'text',text,x,y:top,size,weight,width:measured,height:size+2});
    };
    const wrap=(items,separator,maxLines=2)=>{
      ctx.font='400 11px '+C.body;const lines=[];let current='';
      for(const item of items){if(ctx.measureText(item).width>width)return null;const next=current?current+separator+item:item;if(ctx.measureText(next).width>width){lines.push(current);current=item;}else current=next;}
      if(current)lines.push(current);return lines.length<=maxLines?lines:null;
    };
    const paragraph=(text,maxLines=2)=>{const lines=wrap(text.split(' '),' ',maxLines);if(!lines){invalid=true;return;}for(const value of lines){line(value,0,y);y+=14;}};
    if(kind==='concentration'){
      if(!data.takeaway)return null;const t=data.takeaway;
      line('Specified-row concentration',0,y,13,600);y+=22;
      paragraph(fmt(t.count)+' of '+fmt(t.total)+' specified rows');y+=5;
      ops.push({type:'band',x:0,y,width,height:6,segments:[{state:'SPECIFIED',fraction:t.count/t.total}],track:true});y+=17;
      ctx.font='500 12px '+C.body;line(storyFit(storyCap(t.family.split(':').slice(1).join(':').replaceAll('-',' '),42),width),0,y,12,500);y+=20;
      paragraph('Spec evidence, not completion.');
    }else{
      line('Family evidence · '+fmt(data.total),0,y,13,600);y+=21;
      paragraph('Unique requirements; bands show within-family proportions.');y+=3;
      const legend=wrap(['V Verified','L Landed','S Specified','R Retired'],' · ');if(!legend)return null;for(const value of legend){line(value,0,y);y+=14;}y+=9;
      for(const g of groups){
        const contribution=fmt(g.total)+' / '+fmt(data.total);ctx.font='500 11px '+C.body;const numberWidth=ctx.measureText(contribution).width,labelWidth=width-numberWidth-12;
        if(labelWidth<72)return null;
        ctx.font='500 12px '+C.body;const label=storyFit(storyCap(g.label,28),labelWidth);
        line(label,0,y,12,500);line(contribution,width-numberWidth,y,11,500);y+=19;
        ops.push({type:'band',x:0,y,width,height:6,segments:ST.filter(state=>g.counts[state]).map(state=>({state,fraction:g.counts[state]/g.total}))});y+=12;
        const counts=wrap(ST.filter(state=>g.counts[state]).map(state=>fmt(g.counts[state])+' '+state[0]),' · ');if(!counts)return null;
        for(const value of counts){line(value,0,y);y+=14;}y+=9;
      }
      if(data.takeaway){const t=data.takeaway;paragraph(fmt(t.count)+' / '+fmt(t.total)+' specified rows belong to');paragraph(storyCap(t.family.split(':').slice(1).join(':').replaceAll('-',' '),42));}
      paragraph('Evidence state, not health or completion.');
    }
    if(invalid)return null;
    return {kind,width,height:y+2,ops};
  }finally{ctx.restore();}
}
function drawComposition(choice){
  const [x,y]=choice.rect;ctx.save();try{
    ctx.globalAlpha=1;ctx.textAlign='left';ctx.textBaseline='top';
    for(const op of choice.layout.ops){
      if(op.type==='text'){ctx.font=op.weight+' '+op.size+'px '+C.body;ctx.fillStyle=C.fg;ctx.fillText(op.text,x+op.x,y+op.y);}
      else{if(op.track){ctx.fillStyle=C.line;ctx.fillRect(x+op.x,y+op.y,op.width,op.height);}let offset=0;for(const part of op.segments){const size=op.width*part.fraction;ctx.fillStyle=C.st[part.state];ctx.fillRect(x+op.x+offset,y+op.y,size,op.height);offset+=size;}}
    }
  }finally{ctx.restore();}
}
function storyDescription(s){
  if(s.placement!=='canvas')return '';
  if(s.kind==='concentration'){const t=s.takeaway;return 'Specified-row concentration: '+t.count+' of '+t.total+' specified requirements belong to '+t.family+'. The bar uses all specified requirements in this focused node as denominator; it is not completion or priority.';}
  return 'Family evidence: '+s.total+' unique requirements in this focused node. '+s.groups.map(g=>g.key+' contributes '+g.total+' of '+s.total+' requirements; within this family: '+ST.filter(st=>g.counts[st]).map(st=>g.counts[st]+' '+st).join(', ')).join('; ')+'. Equal bands use each family total as denominator, not family size or completion.';
}
function paintStories(){
  const id=focusAt(),n=nodes[id],data=STORY[id];storyEvidence={owner:id,placement:'deferred',reason:'no-safe-stable-anchor'};
  if(!anim&&document.fonts.check('12px Inter')&&n?.layout&&id!=='root'&&data?.total){
    const world=R[id],p=toS(world[0],world[1]),bounds=[...p,world[2]*cam.k,world[3]*cam.k];
    if(openness(n,bounds[2])>=.995){
      const labels=annotationEvidence.filter(a=>a.placement==='canvas').map(a=>[a.rect[0]-4,a.rect[1]-4,a.rect[2]+8,a.rect[3]+8]);
      const obstacles=[...annotationRects,...labels],choice=chooseStory(id,data,bounds,obstacles,annotationSegments);
      if(choice){drawComposition(choice);storyEvidence={owner:id,placement:'canvas',...choice,total:data.total,takeaway:data.takeaway,obstacles,segments:annotationSegments};}else storyEvidence={...storyEvidence,bounds,anchorCandidates:nodeStoryAnchors(id).map(a=>toS(a.x,a.y)),obstacles,segments:annotationSegments};
    }
  }
  const s=storyEvidence;
  const summary=describeRichStory(s);
  if(cv.getAttribute('aria-description')!==summary)cv.setAttribute('aria-description',summary);
}

// LOCAL pure layout builder. Native canvas painting and hit geometry remain separate.
function richLayout(kind,view,width,measure){
  const ops=[];let y=0,invalid=false;
  const line=(text,x,top,size=11,weight=400)=>{const w=measure(text,size,weight);if(x<0||x+w>width+.01)invalid=true;ops.push({type:'text',text,x,y:top,size,weight,width:w,height:size+2});};
  const para=(text,size=11,weight=400,maxLines=4)=>{let current='',lines=[];for(const word of text.split(' ')){if(measure(word,size,weight)>width){invalid=true;return;}const next=current?current+' '+word:word;if(measure(next,size,weight)>width){lines.push(current);current=word;}else current=next;}if(current)lines.push(current);if(lines.length>maxLines){invalid=true;return;}for(const t of lines){line(t,0,y,size,weight);y+=size+4;}};
  const scope=()=>{para(view.scopeLabel);para('Frozen 26 Oct 02:31 UTC · not whole-node ranking');y+=6;};
  if(kind==='frontier'){
    para('Ready versus blocked',13,600);scope();
    for(const f of view.families){
      para(f.label,12,500);
      const eligible=f.ready+f.blocked;
      para(f.ready+' ready · '+f.blocked+' blocked · '+eligible+' eligible');
      if(eligible)ops.push({type:'band',x:0,y,width,height:7,segments:[{state:'VERIFIED',fraction:f.ready/eligible},{state:'SPECIFIED',fraction:f.blocked/eligible}]});
      y+=18;
    }
    para('Readiness excludes rollups and non-open rows.');
  }else if(kind==='priority'){
    para('Priority and frontier',13,600);scope();
    para('Scope score · shared 0–'+view.priorityScale+' scale');y+=4;
    for(const row of view.priorities){
      const title=row.title;para(title,12,500,2);
      const state=row.readiness==='ready'?'Ready':row.readiness==='blocked'?'Blocked':'Not actionable';
      const label=row.id+' · '+state;para(label);y+=2;
      ops.push({type:'rule',x:0,y,width,height:1});
      ops.push({type:'band',x:0,y:y-2,width:width*.68,height:5,segments:[{state:row.readiness==='ready'?'VERIFIED':'SPECIFIED',fraction:row.priority.value/view.priorityScale}]});
      line(String(row.priority.value)+' score',width*.72,y-5,11,600);y+=19;
    }
    para(view.priorityCounts.zeroScore+' scored non-rollup rows have score 0.');
    para('Rollups excluded; score is not effort or completion.');
  }else if(kind==='dependencies'){
    if(!view.graph)return null;
    para('Recorded prerequisite paths',13,600);scope();
    para('Arrows: dependent → required row');y+=7;
    const rows=view.graph.nodes,edges=view.graph.edges;
    // Complete connected graph when wide; bounded ego of highest-scored blocked row when narrow.
    const narrow=width<420;
    const focal=rows.filter(r=>r.readiness==='blocked').sort((a,b)=>(b.priority?.value||0)-(a.priority?.value||0)||a.key.localeCompare(b.key))[0];
    const shownEdges=narrow?edges.filter(e=>e.source===focal?.key):edges;
    const shownKeys=new Set(shownEdges.flatMap(e=>[e.source,e.target]));
    const shownRows=rows.filter(r=>shownKeys.has(r.key));
    if(!shownRows.length)return null;
    const ranks=new Map(shownRows.map(r=>[r.key,0]));
    for(let i=0;i<shownRows.length;i++){let changed=false;for(const e of shownEdges)if(ranks.get(e.target)<=ranks.get(e.source)){ranks.set(e.target,ranks.get(e.source)+1);changed=true;}if(!changed)break;if(i===shownRows.length-1)return null;}
    const maxRank=Math.max(...ranks.values()),positions=new Map(),baseY=y;
    const cellW=narrow?width-32:130,cellH=98,gap=26;
    if(narrow){
      // Vertical native-space graph; no map inset or custom camera.
      shownRows.sort((a,b)=>ranks.get(a.key)-ranks.get(b.key)||a.key.localeCompare(b.key)).forEach((r,i)=>positions.set(r.key,{x:32,y:baseY+i*(cellH+gap),w:cellW,h:cellH}));
    }else{
      for(let rank=0;rank<=maxRank;rank++){
        const layer=shownRows.filter(r=>ranks.get(r.key)===rank).sort((a,b)=>a.key.localeCompare(b.key));
        layer.forEach((r,i)=>positions.set(r.key,{x:rank*(width-cellW)/maxRank,y:baseY+i*(cellH+gap),w:cellW,h:cellH}));
      }
    }
    for(const e of shownEdges){const a=positions.get(e.source),b=positions.get(e.target);ops.push({type:'edge',source:e.source,target:e.target,points:narrow?[[a.x-6,a.y+a.h/2],[8,a.y+a.h/2],[8,b.y+b.h/2],[b.x-6,b.y+b.h/2]]:[[a.x+a.w,a.y+a.h/2],[b.x-6,b.y+b.h/2]]});}
    // Source titles wrap; no white cards or panel backgrounds.
    for(const row of shownRows){
      const p=positions.get(row.key);let cy=p.y;const full=row.title;
      const words=full.split(' ');let text='',parts=[];for(const word of words){const next=text?text+' '+word:word;if(measure(next,11,500)>p.w){parts.push(text);text=word;}else text=next;}if(text)parts.push(text);
      if(parts.length>4||parts.some(t=>measure(t,11,500)>p.w))return null;
      for(const t of parts){line(t,p.x,cy,11,500);cy+=14;}
      const short=row.id.replace(/^WEBUI-/,'').replace(/^ARBORA-/,'');
      if(measure(short,11,400)>p.w)return null;line(short,p.x,p.y+62);
      const meaning=row.rollup?'Rollup evidence':row.readiness==='ready'?'Ready':row.readiness==='blocked'?'Blocked':row.status.toLowerCase();line(meaning,p.x,p.y+78);
    }
    y=Math.max(...[...positions.values()].map(p=>p.y+p.h))+10;
    para(shownRows.length+' of '+rows.length+' connected rows · '+shownEdges.length+' of '+edges.length+' recorded edges');
    if(narrow)para('Highest-scored blocked row and its direct prerequisites.');
    para('Source requirements, not runtime traffic.');
  }else return null;
  if(invalid)return null;
  const detail=kind==='frontier'?view.families.map(f=>f.key+': '+f.ready+' ready and '+f.blocked+' blocked; denominator '+(f.ready+f.blocked)+' eligible non-rollup open rows').join('. '):kind==='priority'?view.priorities.map(r=>r.id+': '+r.title+'; score '+r.priority.value+'; '+r.readiness).join('. '):ops.filter(o=>o.type==='edge').map(e=>view.refs[e.source].id+' requires '+view.refs[e.target].id).join('. ');
  const visibleKeys=kind==='dependencies'?[...new Set(ops.filter(o=>o.type==='edge').flatMap(e=>[e.source,e.target]))]:kind==='priority'?view.priorities.map(r=>r.key):view.families.map(f=>Object.values(view.refs).find(r=>r.key.startsWith(f.key.split(':')[0]+':')&&r.provenance.path==='specs/'+f.key.split(':')[1]+'/requirements.md').key);
  const sources=visibleKeys.map(key=>{const r=view.refs[key],children=r.rollupOf.map(k=>{const child=view.refs[k]||view.evidenceOnly[k];return child.id+' ('+(view.evidenceOnly[k]?'unscored evidence only':'scored scope')+') at '+child.url;});return r.id+': '+r.title+'. Immutable source file '+r.url+'; locate row '+r.provenance.fragment+(children.length?'. Rollup evidence: '+children.join('; '):'');}).join('. ');
  return {kind,width,height:y+2,ops,scope:view.scope,accessibility:view.accessibility+' '+detail+'. '+sources};
}
if(typeof module!=='undefined')module.exports={richLayout};

// LOCAL extension seam only. No geometry, input handler, control or camera writes.
function storyContext(id){
  const children=nodes[id].children,visible=[];
  for(const ch of children){const r=R[ch.id],p=toS(r[0],r[1]);const w=Math.max(0,Math.min(W,p[0]+r[2]*cam.k)-Math.max(0,p[0])),h=Math.max(0,Math.min(H,p[1]+r[3]*cam.k)-Math.max(0,p[1]));if(w>=40&&h>=24)visible.push({id:ch.id,width:w,height:h});}
  return {applicable:children.length>0,visibleChildren:visible,retained:!children.length||visible.length>0};
}
function availableRichLayouts(id,data,bounds){
  const compact={kind:'context',width:80,height:40,ops:[]};
  ctx.save();try{
    ctx.font='600 20px '+C.body;const text=fmt(data.familyCount),size=ctx.measureText(text).width;
    if(size<=80){compact.ops.push({type:'text',text,x:0,y:0,size:20,weight:600,width:size,height:22});ctx.font='400 11px '+C.body;const label='spec families',w=ctx.measureText(label).width;if(w<=80)compact.ops.push({type:'text',text:label,x:0,y:25,size:11,weight:400,width:w,height:13});}
  }finally{ctx.restore();}
  const layouts=[];
  if(id==='webui'){
    const width=W>=510?460:280,measure=(t,s,w)=>{ctx.font=w+' '+s+'px '+C.body;return ctx.measureText(t).width;};
    ctx.save();try{
      const kinds=bounds[2]>=2560?['dependencies','priority','frontier']:bounds[2]>=1280?['priority','frontier']:['frontier'];
      for(const kind of kinds){const layout=richLayout(kind,SOURCE_VIEW,width,measure);if(layout)layouts.push(layout);}
    }finally{ctx.restore();}
  }
  const family=storyLayout('comparison',data,compactStoryGroups(data));if(family)layouts.push(family);
  if(compact.ops.length===2)layouts.push(compact);
  return layouts;
}
function chooseStory(id,data,bounds,obstacles,segments){
  const tier=Math.floor(Math.log2(Math.max(1,bounds[2]/640))),key=id+':'+tier,anchors=nodeStoryAnchors(id),prior=storyAnchorChoices.get(key),context=storyContext(id);
  const layouts=availableRichLayouts(id,data,bounds),byKind=new Map(layouts.map(l=>[l.kind,l]));
  const rectFor=(choice,layout)=>{const p=toS(anchors[choice.index].x,anchors[choice.index].y);return [p[0]-(choice.align==='right'?layout.width:0),p[1],layout.width,layout.height];};
  if(!context.retained)return null;
  if(prior){const layout=byKind.get(prior.kind);if(!layout)return null;const rect=rectFor(prior,layout);return clearStoryRect(rect,bounds,obstacles,segments)?{...prior,rect,tier,layout,groups:compactStoryGroups(data),context}:null;}
  for(const layout of layouts)for(let index=0;index<anchors.length;index++)for(const align of ['left','right']){
    const choice={index,kind:layout.kind,align},rect=rectFor(choice,layout);
    // Small summaries cannot afford the old large-chart entry moat; the invariant 8px collision halo is retained.
    if(clearStoryRect(rect,bounds,obstacles,segments,layout.kind==='context'?0:12)){storyAnchorChoices.set(key,choice);return {...choice,rect,tier,layout,groups:compactStoryGroups(data),context};}
  }
  return null;
}
function drawComposition(choice){
  const [x,y]=choice.rect;ctx.save();try{
    ctx.globalAlpha=1;ctx.textAlign='left';ctx.textBaseline='top';
    for(const op of choice.layout.ops){
      if(op.type==='text'){ctx.font=op.weight+' '+op.size+'px '+C.body;ctx.fillStyle=C.fg;ctx.fillText(op.text,x+op.x,y+op.y);}
      else if(op.type==='edge'){
        ctx.strokeStyle=C.fg;ctx.fillStyle=C.fg;ctx.lineWidth=1.3;ctx.beginPath();op.points.forEach((p,i)=>i?ctx.lineTo(x+p[0],y+p[1]):ctx.moveTo(x+p[0],y+p[1]));ctx.stroke();
        const b=op.points.at(-1),a=op.points.at(-2),angle=Math.atan2(b[1]-a[1],b[0]-a[0]);ctx.beginPath();ctx.moveTo(x+b[0],y+b[1]);ctx.lineTo(x+b[0]-5*Math.cos(angle-.5),y+b[1]-5*Math.sin(angle-.5));ctx.lineTo(x+b[0]-5*Math.cos(angle+.5),y+b[1]-5*Math.sin(angle+.5));ctx.closePath();ctx.fill();
      }else if(op.type==='rule'){ctx.fillStyle=C.line;ctx.fillRect(x+op.x,y+op.y,op.width,op.height);}
      else{if(op.track){ctx.fillStyle=C.line;ctx.fillRect(x+op.x,y+op.y,op.width,op.height);}let offset=0;for(const part of op.segments){const w=op.width*part.fraction;ctx.fillStyle=C.st[part.state];ctx.fillRect(x+op.x+offset,y+op.y,w,op.height);offset+=w;}}
    }
  }finally{ctx.restore();}
}
const describeFamilyStory=storyDescription;
function describeRichStory(s){
  if(s.placement!=='canvas')return '';
  if(s.kind==='context')return STORY[s.owner].familyCount+' distinct specification families in this focused node. This is a count, not a completion or health measure.';
  return s.layout.accessibility||describeFamilyStory(s);
}
// paintStories' sole accessible description call is redirected during local assembly.
