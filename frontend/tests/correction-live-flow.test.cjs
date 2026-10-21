const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const read=name=>fs.readFileSync(require.resolve('../scripts/'+name),'utf8');
const pause=()=>new Promise(r=>setImmediate(r));
const job=(status='succeeded',result={continuation_required:true,chapter_context:{complete:false}})=>({id:'j',task:'correction',status,result,
 context:{course_id:'c',unit_id:'u',expected_revision:2,target:'question',index:0,request:'Giữ tình huống; sửa giải thích.'},
 partial:{correction_scope:{sha256:'bound'},chapter_context:{complete:false}},progress:{}});
async function boot(snapshot,saved={}){
 const calls=[],listeners={};let stored=JSON.stringify({stage:'course',courseId:'c',unitId:'u',job:{id:'j',kind:'correction'},...saved});
 const document={visibilityState:'visible',addEventListener:(type,fn)=>(listeners[type]||=[]).push(fn),querySelectorAll:()=>[],querySelector:()=>null};
 const dialog={open:false,querySelector:()=>null,querySelectorAll:()=>[]};
 const course={id:'c',revision:2,plan_id:null,access_role:'creator',content:{title:'Course',units:[{id:'u',title:'Lesson',objective:'Understand',data:{},unlocked:true}]}};
 const c={window:{addEventListener:()=>{}},document,location:{port:'8770',hash:'#live'},setInterval:()=>{},FormData:class{},crypto:{randomUUID:()=> 'intent-once'},
  localStorage:{getItem:()=>stored,setItem:(k,v)=>stored=v},
  fetch:async(path,options={})=>{
   const method=options.method||'GET',body=options.body?JSON.parse(options.body):undefined;calls.push({method,path,body});let value;
   if(path==='/api/health')value={backend:true};
   else if(path==='/api/session')value={id:'qa'};
   else if(path==='/api/courses/c')value=course;
   else if(path==='/api/courses/c/chapter-context?unit_id=u')value={complete:false};
   else if(path==='/api/jobs/j')value=snapshot;
   else if(path==='/api/jobs/new')value={...job('succeeded',{proposal_id:'p'}),id:'new'};
   else if(path==='/api/courses/c/proposals'){assert.equal(method,'POST');value={job_id:'new'};}
   else if(path==='/api/proposals/p')value={id:'p',status:'preview'};
   else if(['/api/courses','/api/resume','/api/courses/c/source-fragments'].includes(path))value=[];
   else if(['/api/source-limits','/api/activity/check-in'].includes(path))value={};
   else throw Error('Unexpected request '+path);
   return {ok:true,status:200,json:async()=>value};
  }};
 const w=c.window;w.FLASHCARD_UI={init:()=>{},setOwner:()=>{},invalidate:()=>{}};w.LIVE_HELP={create:()=>({})};
 w.SOURCE_BROWSER={createLibrary:()=>({state:{items:[]},refresh:async()=>{}}),createScope:()=>({})};
 w.LIVE_WAITING={chapterLabel:()=>'',paint:()=>{}};
 w.LIVE_JOBS={observe:async(id,{api,onUpdate})=>{const j=await api('/jobs/'+id);onUpdate(j);return j;}};
 vm.createContext(c);vm.runInContext(read('correction-state.js'),c);vm.runInContext(read('live.js'),c);
 await w.LIVE_STUDY.init({dialog,render:()=>{},go:()=>{}});
 return {calls,saved:()=>JSON.parse(stored),click(action){const button={dataset:{live:action}};for(const f of listeners.click)f({target:{closest:()=>button}});}};
}
test('reconnecting an intermediate correction observes only and never fetches an undefined proposal',async()=>{
 const app=await boot(job());assert.equal(app.saved().stage,'course');assert.equal(app.saved().pendingCorrectionJob.id,'j');
 assert.ok(app.calls.some(x=>x.path==='/api/jobs/j'));assert.ok(!app.calls.some(x=>x.path.includes('/proposals/')));
 assert.deepEqual(app.calls.filter(x=>x.method==='POST').map(x=>x.path),['/api/session']);
 assert.ok(!JSON.stringify(app.saved().pendingCorrectionJob).includes('Giữ tình huống'));
});
test('a completed correction opens its preview and clears the pending handle without applying it',async()=>{
 const app=await boot(job('succeeded',{proposal_id:'p'}));assert.equal(app.saved().stage,'proposal');assert.equal(app.saved().proposalId,'p');
 assert.equal(app.saved().pendingCorrectionJob,null);assert.ok(app.calls.some(x=>x.path==='/api/proposals/p'));
 assert.ok(!app.calls.some(x=>x.path.endsWith('/apply')));
});
test('failed correction is recovered on reload without starting a second job',async()=>{
 const app=await boot(job('failed',null),{job:null,pendingCorrectionJob:{id:'j',courseId:'c',unitId:'u',revision:2}});
 assert.equal(app.saved().pendingCorrectionJob.id,'j');assert.ok(app.calls.some(x=>x.path==='/api/jobs/j'));
 assert.deepEqual(app.calls.filter(x=>x.method==='POST').map(x=>x.path),['/api/session']);
});
test('only an explicit continuation posts the exact pinned request then opens a preview',async()=>{
 const app=await boot(job());app.click('resume-correction');
 for(let i=0;i<15&&app.saved().stage!=='proposal';i++)await pause();
 const writes=app.calls.filter(x=>x.path==='/api/courses/c/proposals');assert.equal(writes.length,1);
 assert.deepEqual(writes[0].body,{unit_id:'u',expected_revision:2,target:'question',index:0,request:'Giữ tình huống; sửa giải thích.',resume_job_id:'j'});
 assert.equal(app.saved().proposalId,'p');assert.ok(!app.calls.some(x=>x.path.endsWith('/apply')));
});
