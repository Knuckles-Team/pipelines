'use strict';
// LOCAL source-scoped adapter. No architecture ownership or fleet completeness claim.
const STATES=['VERIFIED','LANDED','SPECIFIED','RETIRED'];
function insist(ok,message){if(!ok)throw new Error(message);}
function sourceURL(p){
  insist(p&&/^Knuckles-Team\/[a-z0-9-]+$/i.test(p.repository)&&/^[a-f0-9]{40}$/.test(p.commit),'immutable source required');
  insist(p.path?.startsWith('specs/')&&!p.path.includes('..')&&p.fragment,'source path required');
  return 'https://github.com/'+p.repository+'/blob/'+p.commit+'/'+p.path;
}
function buildSourceView(input,baselineRows){
  insist(input.schema==='architecture-source-chart/1','unsupported source schema');
  const s=input.scope;
  insist(s.kind==='selected-family-prerequisite-closure'&&s.fleetComplete===false,'explicit selected-family scope required');
  const rows=input.rows,keys=Object.keys(rows),selected=new Set(s.selectedRowKeys),closure=new Set(s.prerequisiteClosureRowKeys.filter(k=>!selected.has(k)));
  insist(keys.length===s.scoreRowCount&&selected.size===s.selectedRowKeys.length,'score count mismatch');
  insist(keys.length===selected.size+closure.size&&new Set(s.prerequisiteClosureRowKeys).size===keys.length&&s.prerequisiteClosureRowKeys.every(k=>rows[k]),'scope partition mismatch');
  const byRepo=new Map(s.repositories.map(r=>[r.repositoryId,r]));
  const edges=[],refs={};
  for(const [key,row] of Object.entries(rows)){
    insist(key===row.key&&key===row.repositoryId+':'+row.id,'row identity mismatch');
    const repo=byRepo.get(row.repositoryId);
    insist(repo&&row.provenance.commit===repo.commit&&row.provenance.repository===repo.fullName,'source freeze mismatch');
    const old=baselineRows.get(repo.fullName.split('/')[1]+':'+row.id);
    insist(old&&old.status===row.status&&old.family===row.family&&old.title===row.title,'baseline parity mismatch: '+row.id);
    insist(STATES.includes(row.status),'unknown evidence state');
    refs[key]={key,id:row.id,title:row.title,status:row.status,rollup:row.rollup,readiness:row.readiness,url:sourceURL(row.provenance),provenance:{...row.provenance},rollupOf:[...row.sourceEvidence.rollupOf],external:!selected.has(key)};
    insist(['scored','not_applicable'].includes(row.priority.state),'unqualified priority');
    if(row.priority.state==='scored'){
      insist(Number.isFinite(row.priority.value)&&row.priority.value>=0&&row.priority.formulaVersion==='goal-weighted/1','invalid score');
      insist(Number.isInteger(row.priority.inputs.openDependents)&&Array.isArray(row.priority.inputs.competencyQuestions),'score inputs missing');
      refs[key].priority={...row.priority};
    }
    for(const target of row.dependencies.keys){insist(rows[target],'dependency closure incomplete');edges.push({source:key,target,url:sourceURL(row.dependencies.provenance)});}
  }
  insist(new Set(edges.map(e=>e.source+'>'+e.target)).size===edges.length,'duplicate edge');
  const covered=new Set();
  const families=input.families.map(f=>{
    const counts=Object.fromEntries(STATES.map(st=>[st,0]));
    for(const key of f.rowKeys){insist(selected.has(key)&&!covered.has(key),'family partition mismatch');covered.add(key);counts[rows[key].status]++;insist(f.key===rows[key].repositoryId+':'+rows[key].family,'family identity mismatch');}
    for(const st of STATES)insist(counts[st]===f.statusCounts[st],'family state count mismatch');
    const ready=f.rowKeys.filter(k=>rows[k].readiness==='ready'),blocked=f.rowKeys.filter(k=>rows[k].readiness==='blocked');
    insist(JSON.stringify([...ready].sort())===JSON.stringify([...f.readyRowKeys].sort()),'ready count mismatch');
    insist(JSON.stringify([...blocked].sort())===JSON.stringify([...f.blockedRowKeys].sort()),'blocked count mismatch');
    return {key:f.key,label:f.key.split(':')[1].replaceAll('-',' '),total:f.rowKeys.length,counts,ready:ready.length,blocked:blocked.length,other:f.rowKeys.length-ready.length-blocked.length};
  });
  insist(covered.size===selected.size,'selected families incomplete');
  const evidenceOnly={};
  for(const [key,row] of Object.entries(input.evidenceRows||{})){
    insist(!rows[key]&&row.scopeRole==='rollup_evidence_only_not_scored'&&!row.priority&&!row.readiness,'unscored evidence boundary');
    evidenceOnly[key]={...row,url:sourceURL(row.provenance)};
  }
  for(const row of Object.values(refs))for(const child of row.rollupOf)insist(refs[child]||evidenceOnly[child],'rollup evidence omitted');
  const scored=Object.values(refs).filter(r=>r.priority),ranked=scored.filter(r=>!r.rollup).sort((a,b)=>b.priority.value-a.priority.value||a.key.localeCompare(b.key));
  const graphKeys=[...new Set(edges.flatMap(e=>[e.source,e.target]))].sort();
  // This bounded view is complete only when all connected rows fit. No silent graph truncation.
  const graph=graphKeys.length<=8&&edges.length<=10?{nodes:graphKeys.map(k=>refs[k]),edges}:null;
  return {
    schema:'architecture-source-view/1',scope:{kind:s.kind,selectedRows:selected.size,closureRows:closure.size,scoreRows:keys.length,familyCount:families.length,freeze:'2026-10-26T02:31:30Z',fleetComplete:false,modelMapping:input.modelMapping.state,excludedGapCount:s.excludedDependencyGaps.length},
    title:'Selected Overstory families',scopeLabel:families.length+' families · '+selected.size+' rows + '+closure.size+' prerequisites',
    families,graph,graphDeferredReason:graph?null:'complete connected graph exceeds readable budget',
    priorities:ranked.filter(r=>r.priority.value>0).slice(0,5),priorityScale:Math.max(0,...ranked.map(r=>r.priority.value)),
    priorityCounts:{scoredNonRollup:ranked.length,zeroScore:ranked.filter(r=>r.priority.value===0).length,positiveOmitted:Math.max(0,ranked.filter(r=>r.priority.value>0).length-5),rollupExcluded:scored.filter(r=>r.rollup).length,notApplicable:keys.length-scored.length},
    refs,evidenceOnly,activity:null,accessibility:'Frozen source scope: '+selected.size+' selected requirements and '+closure.size+' prerequisite rows; not whole-node or fleet ranking. Dependency arrows point from dependent to prerequisite. Readiness excludes rollups. Scores use goal-weighted/1 within this scope; not effort, health or completion.'
  };
}
module.exports={buildSourceView,sourceURL};
