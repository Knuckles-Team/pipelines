const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const template=fs.readFileSync(__dirname+'/baseline-template.html','utf8');
const collision=template.slice(template.indexOf('function intersects('),template.indexOf('function annotationClear('));
const extension=fs.readFileSync(__dirname+'/story.js','utf8').split('function drawStory(){')[0].replace('/*__STORY__*/null','null');
const context={W:1440,H:1000,Intl,ST:["VERIFIED","LANDED","SPECIFIED","RETIRED"]};vm.createContext(context);
vm.runInContext(collision+'\n'+extension+'\nthis.slot=storySlot;this.cap=storyCap;this.compact=compactStoryGroups;',context);
assert(context.slot([0,0,1440,1000],[],[],402,280));
assert.equal(context.slot([0,0,390,844],[],[],402,280),null);
assert.equal(context.slot([0,0,1440,1000],[[0,0,1440,1000]],[],402,280),null);
const r=context.slot([0,0,1440,1000],[[0,0,800,1000]],[],402,280);
assert(r&&r[0]>=808);
const lineResult=context.slot([0,0,450,400],[],[[[0,180],[450,180]]],402,280);
assert.equal(lineResult,null);
assert.equal(context.cap('👩‍💻👩‍💻👩‍💻',2),'👩‍💻…');
console.log('PASS: free/occupied/narrow slots, padding, routed obstruction, grapheme cap');

const models=JSON.parse(fs.readFileSync(__dirname+'/chart-model.json','utf8'));
for(const model of Object.values(models)){
 const groups=context.compact(model);assert(groups.length<=3);
 assert.equal(groups.reduce((n,g)=>n+g.total,0),model.total);
 for(const state of context.ST)assert.equal(groups.reduce((n,g)=>n+g.counts[state],0),model.groups.reduce((n,g)=>n+g.counts[state],0));
}
assert(context.slot([0,0,350,600],[],[],280,366));
console.log('PASS: compact aggregation conserves every state on 598 nodes; 280px slot fits 350px canvas');
