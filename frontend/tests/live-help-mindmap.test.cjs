const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const pause=()=>new Promise(r=>setImmediate(r));
async function settle(){for(let i=0;i<12;i++)await pause();}
const target=kind=>({kind,courseId:'c',unitId:'u',revision:2,index:0});
function setup({revision=2}={}){
 const listeners={},calls=[],threads=new Map(),watched=[],prepared=[];
 const c={window:{},setTimeout:()=>0,clearTimeout:()=>{},document:{addEventListener:(t,f)=>(listeners[t]||=[]).push(f),querySelector:()=>null}};
 vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/live-help.js'),'utf8'),c);
 const api=async(path,body,method)=>{
  calls.push({path,body:body===undefined?undefined:JSON.parse(JSON.stringify(body)),method:body===undefined?'GET':method||'POST'});
  const open=path.match(/^\/courses\/c\/units\/u\/(mindmap|sections)\/(\d+)\/help$/);
  if(open||path==='/sessions/s/items/q/help'){
   if(open&&body.expected_revision!==revision)throw Error('Stale revision; reload before opening.');
   const kind=open?.[1]==='mindmap'?'mindmap':open?'section':'question',id=kind+'-'+(open?.[2]||'q');
   if(!threads.has(id))threads.set(id,{id,context:{kind,section:{title:kind+' title',text:kind+' content'},node_index:0},
    source_excerpts:[{id:'ref',text:kind+' source only',locator:{line:1}}],messages:[],pending_jobs:[],draft:{text:'',version:0}});
   return {thread_id:id};
  }
  const match=path.match(/^\/help\/threads\/([^/]+)(?:\/(draft|actions))?$/);
  if(!match)throw Error('Unexpected route '+path);
  const x=threads.get(match[1]);assert.ok(x);
  if(match[2]==='draft'){x.draft={text:body.text,version:x.draft.version+1};return x.draft;}
  if(match[2]==='actions'){x.messages=[{id:'m',role:'assistant',content:{text:x.context.kind+' reply',ai_generated:true}}];return {job_id:'j'};}
  return JSON.parse(JSON.stringify(x));
 };
 const helper=c.window.LIVE_HELP.create({api,redraw:()=>{},T:a=>a,E:s=>String(s??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),
  beforeHelp:async t=>prepared.push(t),waitJob:async(id,kind,onUpdate)=>{watched.push({id,kind});onUpdate?.({progress:{phase:'validating'}});}});
 const key=t=>helper.render(t).match(/data-inline-key="([^"]+)"/)[1];
 return {helper,calls,watched,prepared,key,
  click(t,action){const b={disabled:false,dataset:{inlineKey:key(t),inlineAction:action}};for(const f of listeners.click)f({target:{closest:()=>b}});},
  input(t,text){for(const f of listeners.input)f({target:{dataset:{inlineInput:key(t)},value:text}});}};
}
test('same-index mindmap and reading sections open distinct scoped threads and retain separate drafts',async()=>{
 const s=setup(),m=target('mindmap'),r=target('section');assert.notEqual(s.key(m),s.key(r));
 s.click(m,'open');await settle();s.input(m,'Mindmap-only draft');s.click(r,'open');await settle();
 assert.deepEqual(s.calls.filter(x=>x.method==='POST').map(x=>x.path),['/courses/c/units/u/mindmap/0/help','/courses/c/units/u/sections/0/help']);
 const html=s.helper.render(m);assert.match(html,/Trợ giúp cho ý mindmap này/);assert.match(html,/Mindmap-only draft/);assert.match(html,/mindmap source only/);
 assert.doesNotMatch(s.helper.render(r),/Mindmap-only draft/);assert.equal(s.watched.length,0);
});
test('mindmap explanation observes one inline job then stays at the same node and source',async()=>{
 const s=setup(),m=target('mindmap');s.click(m,'explain');await settle();
 const post=s.calls.find(x=>x.path.endsWith('/mindmap/0/help'));assert.deepEqual(post.body,{expected_revision:2});
 assert.equal(s.watched.length,1);assert.equal(s.watched[0].id.job_id,'j');assert.equal(s.watched[0].kind,'inline_help');
 assert.ok(s.calls.some(x=>x.path==='/help/threads/mindmap-0/actions'&&x.body.action==='explain'));
 assert.match(s.helper.render(m),/mindmap reply/);assert.ok(!s.calls.some(x=>x.path.includes('/chat')));
});
test('a stale node reports its error and never silently retries with a newer revision',async()=>{
 const s=setup({revision:3}),m=target('mindmap');s.click(m,'open');await settle();
 assert.match(s.helper.render(m),/Stale revision/);assert.equal(s.calls.length,1);assert.equal(s.calls[0].body.expected_revision,2);
 s.click({...m,revision:3},'open');await settle();assert.equal(s.calls.filter(x=>x.method==='POST').length,2);
 assert.equal(s.calls[1].body.expected_revision,3);assert.notEqual(s.key(m),s.key({...m,revision:3}));
});
test('question help retains the existing session/item route and separate identity',async()=>{
 const s=setup(),q={kind:'question',sessionId:'s',itemId:'q'};s.click(q,'open');await settle();
 assert.equal(s.calls[0].path,'/sessions/s/items/q/help');assert.deepEqual(s.calls[0].body,{});
 assert.notEqual(s.key(q),s.key(target('mindmap')));assert.match(s.helper.render(q),/Trợ giúp cho câu này/);
});
