const test=require('node:test');
const assert=require('node:assert/strict');
const {observe}=require('../scripts/live-jobs.js');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function source(){
  class Events{
    constructor(url){this.url=url;this.listeners={};Events.instances.push(this);}
    addEventListener(name,fn){this.listeners[name]=fn;}
    emit(name,value){this.listeners[name]?.({data:JSON.stringify(value)});}
    close(){this.closed=true;}
  }
  Events.instances=[];return Events;
}
const snapshot=(version,status='running')=>({id:'job-1',status,feedback_deferred:false,progress:{version,preview:{text:'draft',validated:false}}});

test('observe ignores stale snapshots and never submits model work',async()=>{
  const Events=source(),seen=[],calls=[];
  const promise=observe('job-1',{EventSourceClass:Events,api:async path=>{calls.push(path);return snapshot(2);},onUpdate:value=>seen.push(value.progress.version)});
  await pause(0);
  Events.instances[0].emit('snapshot',snapshot(1));
  Events.instances[0].emit('snapshot',snapshot(3,'succeeded'));
  const result=await promise;
  assert.equal(result.status,'succeeded');assert.deepEqual(seen,[2,3]);assert.deepEqual(calls,['/jobs/job-1']);
  assert.equal(Events.instances[0].closed,true);
});

test('SSE disconnect falls back to reading the same job without recreating it',async()=>{
  const Events=source(),calls=[];let count=0;
  const promise=observe('job-1',{EventSourceClass:Events,pollMs:2,api:async path=>{calls.push(path);return snapshot(++count,count>2?'succeeded':'running');}});
  await pause(0);Events.instances[0].onerror();
  assert.equal((await promise).status,'succeeded');assert.equal(count,3);
  assert.ok(calls.every(path=>path==='/jobs/job-1'));
});

test('without EventSource, completed state is recovered by authenticated GET',async()=>{
  let count=0;
  const result=await observe('job-1',{EventSourceClass:null,pollMs:2,api:async()=>snapshot(++count,count===2?'cancelled':'running')});
  assert.equal(result.status,'cancelled');assert.equal(count,2);
});

test('session expiry closes observation and preserves the job handle',async()=>{
  const Events=source();
  const promise=observe('job-1',{EventSourceClass:Events,api:async()=>snapshot(1)});
  await pause(0);Events.instances[0].emit('session_expired',{});
  await assert.rejects(promise,error=>error.code==='SESSION_EXPIRED'&&error.jobRetained&&error.jobId==='job-1');
  assert.equal(Events.instances[0].closed,true);
});

test('deferred feedback is not treated as a successful answer',async()=>{
  const value={...snapshot(2,'succeeded'),result:null,feedback_deferred:true,progress:{version:2,preview:null}};
  await assert.rejects(observe('job-1',{EventSourceClass:null,api:async()=>value}),error=>error.code==='FEEDBACK_DEFERRED'&&error.jobRetained);
});

test('observation timeout keeps a handle and sends no retry/cancel request',async()=>{
  const calls=[];
  await assert.rejects(observe('job-1',{EventSourceClass:source(),timeoutMs:10,api:async path=>{calls.push(path);return snapshot(1);}}),error=>error.code==='OBSERVATION_TIMEOUT'&&error.jobRetained);
  assert.deepEqual(calls,['/jobs/job-1']);
});
