const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const base=fs.readFileSync(__dirname+'/baseline-template.html','utf8');
const collision=base.slice(base.indexOf('function intersects('),base.indexOf('function annotationClear('));
const source=fs.readFileSync(__dirname+'/story.js','utf8');
const states=['VERIFIED','LANDED','SPECIFIED','RETIRED'];
const fontStack=[];const ctx={font:'400 11px Inter',save(){fontStack.push(this.font);},restore(){this.font=fontStack.pop();},measureText(text){const size=Number(this.font.match(/(\d+)px/)[1]);return {width:Array.from(text).length*size*.52};}};
const context={ctx,C:{body:'Inter'},fmt:n=>n.toLocaleString('en-US'),W:1000,H:800,Intl,ST:states,R:{test:[0,0,1000,800]},nodes:{test:{children:[]}},shift:0};
vm.createContext(context);vm.runInContext(collision+'\n'+source+'\nthis.choose=chooseStory;this.compact=compactStoryGroups;this.layout=storyLayout;this.describe=storyDescription;this.seedAnchors=(id,points)=>storyAnchorSets.set(id,points);this.toS=(x,y)=>[x+shift,y];',context);
const models=JSON.parse(fs.readFileSync(__dirname+'/chart-model.json','utf8'));
for(const m of Object.values(models)){
 const groups=context.compact(m);assert(groups.length<=3);
 assert.equal(groups.reduce((sum,g)=>sum+g.total,0),m.total);
 for(const st of states)assert.equal(groups.reduce((sum,g)=>sum+g.counts[st],0),m.groups.reduce((sum,g)=>sum+g.counts[st],0));
 for(const g of groups)assert.equal(Object.values(g.counts).reduce((sum,n)=>sum+n,0),g.total);
}
const data=models.webui,bounds=[0,0,1000,800];
const first=context.choose('test',data,bounds,[],[]);assert(first&&first.kind==='comparison');
const blocked=context.choose('test',data,bounds,[first.rect],[]);assert.equal(blocked,null,'must defer instead of jumping to another available gap');
context.shift=30;const moved=context.choose('test',data,bounds,[],[]);assert.equal(moved.index,first.index);assert.equal(moved.rect[0]-first.rect[0],30,'must move with original world anchor');
const segment=[[[moved.rect[0],moved.rect[1]],[moved.rect[0]+moved.rect[2],moved.rect[1]+moved.rect[3]]]];
assert.equal(context.choose('test',data,bounds,[],segment),null);
console.log('PASS: 598-node counts; compact denominators; stable anchor under native transform; collision defers without roaming');

function assertLayout(layout){
 assert(layout);const text=layout.ops.filter(op=>op.type==='text');
 for(const op of text){assert(op.x>=0&&op.x+op.width<=layout.width+.01);assert(op.y>=0&&op.y+op.height<=layout.height);assert(op.size>=11);}
 for(let i=0;i<text.length;i++)for(let j=i+1;j<text.length;j++){
  const a=text[i],b=text[j];assert(!(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y),'text rectangles overlap: '+a.text+' / '+b.text);
 }
}
for(const id of ['webui','arbora','eg.decide']){
 const m=models[id];assertLayout(context.layout('comparison',m,context.compact(m)));assertLayout(context.layout('concentration',m,context.compact(m)));
}
const single={total:9000,familyCount:1,takeaway:null,groups:[{key:'repo:uniform',label:'Uniform family',total:9000,counts:{VERIFIED:9000,LANDED:0,SPECIFIED:0,RETIRED:0}}]};
assert.equal(context.layout('concentration',single,single.groups),null);assertLayout(context.layout('comparison',single,single.groups));
const huge={total:8e12,familyCount:1,takeaway:{family:'repo:large',count:2e12,total:2e12},groups:[{key:'repo:large',label:'👩‍💻'.repeat(50),total:8e12,counts:{VERIFIED:2e12,LANDED:2e12,SPECIFIED:2e12,RETIRED:2e12}}]};
const hugeLayout=context.layout('comparison',huge,huge.groups);if(hugeLayout){assertLayout(hugeLayout);const labels=hugeLayout.ops.filter(o=>o.type==='text').map(o=>o.text).join(' ');for(const abbreviation of ['V','L','S','R'])assert(labels.includes('2,000,000,000,000 '+abbreviation));} // Otherwise safe deferral, never truncated numeric/legend text.
const description=context.describe({placement:'canvas',kind:'concentration',takeaway:{family:'repo:one',count:3,total:5},groups:[],total:10});assert(description.includes('3 of 5'));assert(!description.includes('Equal bands'));assert(!description.includes('10 unique'));
context.shift=0;const otherTier=context.choose('test',data,[0,0,2200,800],[],[]);assert(otherTier);const returnTier=context.choose('test',data,bounds,[],[]);assert.equal(returnTier.index,first.index);
console.log('PASS: kind-specific aria; measured no-overlap text; uniform/zero specified; large complete numbers or deferral; long Unicode; tier return');

context.W=357;context.H=600;context.seedAnchors('rightOnly',[{x:304,y:100,score:1}]);
const right=context.choose('rightOnly',data,[0,0,1000,800],[],[]);assert(right);assert.equal(right.align,'right');assert.equal(right.rect[0],24);
assert.equal(context.choose('rightOnly',data,[0,0,1000,800],[right.rect],[]),null,'pinned right edge must defer on collision');
console.log('PASS: stable right-edge anchor reveals in narrow viewport; collision still defers');
