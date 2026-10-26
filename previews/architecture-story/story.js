const STORY = /*__STORY__*/null;
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
  const gridX=[.03,.15,.2,.225,.25,.3,.35,.4,.5,.65,.8].map(f=>r[0]+r[2]*f),gridY=[.14,.25,.4,.45,.5,.55,.7].map(f=>r[1]+r[3]*f);
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
  const anchors=[...interior,...other.slice(0,96-interior.length)].sort((a,b)=>b.score-a.score||a.y-b.y||a.x-b.x);storyAnchorSets.set(id,anchors);return anchors;
}
function clearStoryRect(rect,bounds,obstacles,segments,spare=0){
  const [x,y,w,h]=rect,p=[x-8-spare,y-8-spare,w+16+2*spare,h+16+2*spare];
  return x>=Math.max(12,bounds[0]+8)&&y>=Math.max(12,bounds[1]+8)&&x+w<=Math.min(W-12,bounds[0]+bounds[2]-8)&&y+h<=Math.min(H-12,bounds[1]+bounds[3]-8)&&!obstacles.some(b=>intersects(p,b))&&!segments.some(([a,b])=>segmentHitsRect(a,b,p));
}
function chooseStory(id,data,bounds,obstacles,segments){
  const groups=compactStoryGroups(data),tier=Math.floor(Math.log2(Math.max(1,bounds[2]/640)));
  const key=id+':'+tier,anchors=nodeStoryAnchors(id),prior=storyAnchorChoices.get(key);
  const layouts=Object.fromEntries(['comparison','concentration'].map(kind=>[kind,storyLayout(kind,data,groups)]));
  const rectFor=choice=>{const p=toS(anchors[choice.index].x,anchors[choice.index].y);return [p[0],p[1],280,layouts[choice.kind].height];};
  if(prior){if(!layouts[prior.kind])return null;const rect=rectFor(prior);return clearStoryRect(rect,bounds,obstacles,segments)?{...prior,rect,groups,tier,layout:layouts[prior.kind]}:null;}
  for(const kind of ['comparison','concentration']){
    if(!layouts[kind])continue;
    for(let index=0;index<anchors.length;index++){
      const choice={index,kind},rect=rectFor(choice);
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
  const summary=storyDescription(s);
  if(cv.getAttribute('aria-description')!==summary)cv.setAttribute('aria-description',summary);
}
