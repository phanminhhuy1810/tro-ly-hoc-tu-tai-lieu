const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function state(){const c={window:{}};vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/correction-state.js'),'utf8'),c);return c.window.CORRECTION_STATE;}
function snapshot(status='failed'){return {id:'j',task:'correction',status,context:{course_id:'c',unit_id:'u',expected_revision:2,target:'question',index:3,request:'Giữ tình huống; sửa giải thích.'},partial:{chapter_context:{complete:true},correction_scope:{sha256:'binding'},replacement:{answer:'private'}},error:{code:'CONNECTION_FAILED'}};}
test('failure, cancellation and bounded continuation recover the exact intent without copying the answer',()=>{
 const u=state();
 for(const j of [snapshot(),snapshot('cancelled'),{...snapshot('succeeded'),result:{continuation_required:true}}]){
   const p=u.recover(j),body=u.body(p,'c','u',2);
   assert.equal(p.request,j.context.request);assert.equal(body.target,'question');assert.equal(body.index,3);assert.equal(body.resume_job_id,'j');
   assert.equal(body.expected_revision,2);assert.doesNotMatch(JSON.stringify(p),/private|answer|replacement/);
 }
});
test('completed proposals, hidden exam feedback and missing bindings cannot be resumed',()=>{
 const u=state();
 for(const j of [snapshot('running'),snapshot('succeeded'),{...snapshot('succeeded'),result:{continuation_required:true,proposal_id:'done'}},
   {...snapshot(),feedback_deferred:true},{...snapshot(),partial:{}},{...snapshot(),task:'lesson'},
   {...snapshot(),context:{...snapshot().context,target:'other'}},{...snapshot(),context:{...snapshot().context,index:-1}}])assert.equal(u.recover(j),null);
});
test('different course, unit or revision cannot submit a saved intent',()=>{
 const u=state(),p=u.recover(snapshot());
 for(const scope of [['other','u',2],['c','other',2],['c','u',3]]){
   assert.equal(u.matches(p,...scope),false);assert.throws(()=>u.body(p,...scope));
 }
});
test('reload stores only a handle and needs a fresh owned GET before resume',()=>{
 const u=state(),p=u.recover(snapshot()),stored=JSON.parse(JSON.stringify(u.handle(p)));
 assert.deepEqual(stored,{id:'j',courseId:'c',unitId:'u',revision:2});
 assert.equal(u.matches(stored,'c','u',2),false);
 assert.equal(u.matches(u.recover(snapshot()),'c','u',2),true);
 assert.equal(u.handle(null),null);
});
test('notice offers an explicit continuation and preview for the current scope only',()=>{
 const u=state(),p=u.recover(snapshot()),render=(revision=2)=>u.notice({pending:p,courseId:'c',unitId:'u',revision,T:a=>a,B:(a,l)=>`<button data-live="${a}">${l}</button>`});
 assert.match(render(),/resume-correction/);assert.match(render(),/xem trước rồi mới áp dụng/);
 assert.doesNotMatch(render(),/Giữ tình huống|private/);assert.equal(render(3),'');
});
