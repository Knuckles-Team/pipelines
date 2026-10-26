// Preview extension: no layout, camera, DOM controls or input handlers are changed.
const STORY = /*__STORY__*/null;
let storyEvidence={placement:'deferred',reason:'initial'};
const storyCap=(text,max)=>{
  const chars=typeof Intl.Segmenter==='function'?[...new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text)].map(x=>x.segment):Array.from(text);
  return chars.length<=max?text:chars.slice(0,max-1).join('')+'…';
};
function storySlot(bounds,obstacles,segments,width,height){
  // Fixed CSS-pixel legibility, finite search. Never shrink the existing diagram.
  const left=Math.max(12,bounds[0]+12),top=Math.max(12,bounds[1]+12);
  const right=Math.min(W-12,bounds[0]+bounds[2]-12),bottom=Math.min(H-12,bounds[1]+bounds[3]-12);
  if(right-left<width||bottom-top<height)return null;
  const cols=Math.max(1,Math.floor((right-left-width)/28)+1);
  const rows=Math.max(1,Math.floor((bottom-top-height)/28)+1);
  // Evenly sample the whole free area instead of favouring a top-left dashboard.
  const count=Math.min(160,cols*rows);
  for(let i=0;i<count;i++){
    const index=count===1?0:Math.floor(i*(cols*rows-1)/(count-1));
    const x=left+(index%cols)*28,y=top+Math.floor(index/cols)*28;
    const r=[x,y,width,height],p=[x-8,y-8,width+16,height+16];
    if(!obstacles.some(b=>intersects(p,b))&&!segments.some(([a,b])=>segmentHitsRect(a,b,p)))return r;
  }
  return null;
}
function compactStoryGroups(data){
  const groups=data.groups;
  if(groups.length<=3)return groups;
  const rest=groups.slice(2),counts=Object.fromEntries(ST.map(state=>[state,rest.reduce((sum,g)=>sum+g.counts[state],0)]));
  return [...groups.slice(0,2),{key:(data.familyCount-2)+' other families',label:(data.familyCount-2)+' other families',total:rest.reduce((sum,g)=>sum+g.total,0),counts}];
}
function drawStory(){
  const id=focusAt(),n=nodes[id],data=STORY[id];
  storyEvidence={owner:id,placement:'deferred',reason:'scale-or-no-empty-space'};
  if(anim||!n||id==='root'||!n.layout||!data||data.total===0)return;
  const world=R[id],xy=toS(world[0],world[1]),bounds=[...xy,world[2]*cam.k,world[3]*cam.k];
  if(openness(n,bounds[2])<.995)return;
  const labels=annotationEvidence.filter(a=>a.placement==='canvas').map(a=>[a.rect[0]-4,a.rect[1]-4,a.rect[2]+8,a.rect[3]+8]);
  const obstacles=[...annotationRects,...labels];
  let groups=data.groups,compact=false,height=136+groups.length*52;
  let slot=storySlot(bounds,obstacles,annotationSegments,462,height);
  if(!slot){
    compact=true;
    groups=compactStoryGroups(data);
    height=150+groups.length*72;
    slot=storySlot(bounds,obstacles,annotationSegments,280,height);
  }
  if(!slot)return;
  const width=compact?280:462;
  const [x,y]=slot;
  ctx.save();ctx.globalAlpha=1;ctx.textAlign='left';ctx.textBaseline='top';
  ctx.font='600 14px '+C.display;ctx.fillStyle=C.fg;ctx.fillText('Requirement evidence by family',x,y);
  ctx.font='400 11px '+C.body;ctx.fillStyle=C.muted;
  ctx.fillText(fmt(data.total)+' unique requirements · area = count',x,y+21);
  const labelsShort=['Verified','Landed','Specified','Retired'];
  ctx.font='500 11px '+C.body;
  ST.forEach((s,i)=>{ctx.fillStyle=C.fg;ctx.textAlign='center';ctx.fillText(labelsShort[i],x+(compact?35+i*70:245+i*60),y+44);});
  const max=Math.max(1,...groups.flatMap(g=>ST.map(s=>g.counts[s])));
  groups.forEach((g,row)=>{
    const cy=y+(compact?104+row*72:80+row*52);
    ctx.textAlign='left';ctx.font='500 12px '+C.body;ctx.fillStyle=C.fg;
    ctx.fillText(fitText(storyCap(g.label,28),compact?280:207),x,cy-(compact?29:6));
    ctx.font='400 11px '+C.body;ctx.fillStyle=C.muted;
    if(!compact)ctx.fillText(fmt(g.total)+' requirements',x,cy+9);
    ST.forEach((s,col)=>{
      const count=g.counts[s],cx=x+(compact?35+col*70:245+col*60);
      if(count){ctx.beginPath();ctx.arc(cx,cy,Math.sqrt(count/max)*12,0,Math.PI*2);ctx.fillStyle=C.st[s];ctx.fill();}
      ctx.font='500 11px '+C.body;ctx.textAlign='center';ctx.fillStyle=C.fg;ctx.fillText(fmt(count),cx,cy+16);
    });
  });
  ctx.textAlign='left';ctx.fillStyle=C.muted;ctx.font='400 11px '+C.body;
  ctx.fillText(compact?'Largest circle = '+fmt(max)+' rows (common scale).':'Common area scale: largest circle = '+fmt(max)+' requirements.',x,y+height-(compact?69:47));
  const takeaway=data.takeaway;
  const note=takeaway?fmt(takeaway.count)+' of '+fmt(takeaway.total)+' specified rows: '+takeaway.family.split(':').slice(1).join(':').replaceAll('-',' '):'No SPECIFIED rows in this recorded snapshot.';
  ctx.fillStyle=C.fg;
  if(compact)wrapText(storyCap(note,86),width,2).forEach((line,i)=>ctx.fillText(line,x,y+height-52+i*14));
  else ctx.fillText(fitText(storyCap(note,86),width),x,y+height-31);
  ctx.fillStyle=C.muted;ctx.fillText(compact?'Spec evidence, not health or completion.':'Spec states, not runtime health or completion.',x,y+height-15);
  ctx.restore();
  storyEvidence={owner:id,placement:'canvas',rect:slot,compact,groups,total:data.total,takeaway:data.takeaway,obstacles:obstacles.map(r=>r.slice()),segments:annotationSegments,scale:cam.k};
}

function paintStories(){
  drawStory();
  const s=storyEvidence;
  const description=s.placement==='canvas'?'Supplementary requirement evidence by family. '+s.total+' unique requirements. Circle area means count, not runtime health or completion. '+(s.takeaway?'Largest specified concentration: '+s.takeaway.family+', '+s.takeaway.count+' of '+s.takeaway.total+' specified rows. ':'')+s.groups.map(g=>g.key+': '+ST.map(state=>state+' '+g.counts[state]).join(', ')).join('; '):'';
  if(cv.getAttribute('aria-description')!==description)cv.setAttribute('aria-description',description);
}
