const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function controllers(){const context={window:{},URLSearchParams};vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/source-browser.js'),'utf8'),context);return context.window.SOURCE_BROWSER;}
const plain=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const page=(ids,cursor,next=null,total=115,query='')=>({items:ids.map(id=>({id})),current_cursor:cursor,next_cursor:next,total,library_total:115,query});
const source=(id='s1',revision=2)=>({id,revision,reviewed:true});
const excerpts=(revision=2,offset=0,total=45)=>({revision,latest_revision:revision,reviewed:true,items:Array.from({length:Math.min(20,total-offset)},(_,i)=>({id:'f'+(i+offset)})),matched_fragments:total});

test('checking visible excerpts retains hidden selections and explicit empty selection',()=>{
  const {mergeVisible}=controllers(),all=['a','b','c','d'];
  assert.deepEqual(plain(mergeVisible(all,['a','c'],['a','b'],['b'])),['b','c']);
  assert.deepEqual(plain(mergeVisible(all,[],['c','d'],['d'])),['d']);
  assert.deepEqual(plain(mergeVisible(all,['foreign'],['foreign'],['foreign'])),[]);
  assert.deepEqual(plain(mergeVisible(all,['a'],[],[])),['a']);
});

test('source library reaches pages beyond 100 and Back retains first-page window',async()=>{
  const calls=[],api=async path=>{calls.push(path);const cursor=new URLSearchParams(path.split('?')[1]).get('cursor');if(!cursor||cursor==='c0')return page(['0'],'c0','c1');const n=Number(cursor.slice(1));return page([String(n)],cursor,n<5?'c'+(n+1):null);};
  const library=controllers().createLibrary({api});await library.refresh();
  for(let i=0;i<5;i++)await library.next();
  assert.equal(library.state.page,6);assert.equal(library.state.items[0].id,'5');
  for(let i=0;i<5;i++)await library.previous();
  assert.equal(library.state.page,1);assert.equal(new URLSearchParams(calls.at(-1).split('?')[1]).get('cursor'),'c0');
  assert.ok(calls.every(path=>path.startsWith('/source-library?')));
});

test('search failures preserve displayed rows and paging, while query draft can be retried',async()=>{
  let fail=false;const library=controllers().createLibrary({api:async()=>{if(fail)throw Error('offline');return page(['saved'],'first','next');}});
  await library.refresh();fail=true;await library.search('Mạng');
  assert.equal(library.state.items[0].id,'saved');assert.equal(library.state.currentCursor,'first');
  assert.equal(library.state.page,1);assert.equal(library.state.draft,'Mạng');assert.equal(library.state.error,'offline');
});

test('later search wins even if an earlier HTTP response arrives last',async()=>{
  const requests=[];const library=controllers().createLibrary({api:path=>{const d=deferred();requests.push({path,...d});return d.promise;}});
  const first=library.search('old'),second=library.search('new');
  requests[1].resolve(page(['new'],'new-window',null,1,'new'));await second;
  requests[0].resolve(page(['old'],'old-window',null,1,'old'));await first;
  assert.equal(library.state.items[0].id,'new');assert.equal(library.state.query,'new');assert.equal(library.state.loading,false);
});

test('restored page keeps its cursor; invalidation after upload explicitly returns to newest page',async()=>{
  const calls=[];let library=controllers().createLibrary({api:async path=>{calls.push(path);return page(['page2'],'c1','c2');},saved:{query:'math',draft:'math',currentCursor:'c1',back:['c0'],page:2}});
  await library.refresh();assert.equal(library.state.page,2);assert.match(calls[0],/cursor=c1/);
  const restored=controllers().createLibrary({api:async path=>{calls.push(path);return page(['newest'],'fresh',null);},saved:library.exportState()});
  restored.invalidate();await restored.refresh();assert.equal(restored.state.page,1);assert.equal(restored.state.back.length,0);assert.ok(!calls.at(-1).includes('cursor='));
});

test('scope search can select all matches across pages without changing external choices',async()=>{
  const calls=[];const all=Array.from({length:45},(_,i)=>'f'+i);
  const scope=controllers().createScope({api:async(path,body)=>{assert.equal(body,undefined);calls.push(path);return path.includes('/fragment-selection?')?{latest_revision:2,fragment_ids:all}:excerpts(2,Number(new URLSearchParams(path.split('?')[1]).get('offset')),45);}});
  scope.bind(source());await scope.load();scope.setDraft('q','địa chỉ');assert.equal(scope.dirty(),true);
  await assert.rejects(scope.select(['old'],'replace'),/Tìm trích đoạn/);
  await scope.search();assert.equal(scope.dirty(),false);const selected=['old'];
  assert.deepEqual(plain(await scope.select(selected,'replace')),all);assert.deepEqual(selected,['old']);
  assert.deepEqual(plain(await scope.select(selected,'add')),['old',...all]);
  await scope.next();assert.equal(scope.state.offset,20);assert.equal(scope.state.items[0].id,'f20');
  await scope.next();assert.equal(scope.state.items.length,5);await scope.previous();assert.equal(scope.state.offset,20);
  assert.ok(calls.every(path=>path.startsWith('/sources/s1/')&&path.includes('revision=2')));
});

test('new source or revision invalidates late search and late bulk-selection replies',async()=>{
  const requests=[];const scope=controllers().createScope({api:path=>{const d=deferred();requests.push({path,...d});return d.promise;}});
  scope.bind(source());const old=scope.load();scope.bind(source('s2',3));const fresh=scope.load();
  requests[1].resolve(excerpts(3));await fresh;requests[0].resolve(excerpts(2));await old;
  assert.equal(scope.state.sourceId,'s2');assert.equal(scope.state.latestRevision,3);
  const selection=scope.select(['keep'],'replace');scope.bind(source('s2',4));requests[2].resolve({latest_revision:3,fragment_ids:['stale']});
  assert.equal(await selection,null);assert.equal(scope.state.revision,4);assert.equal(scope.state.loaded,false);
});

test('bulk selection reports changed extraction without applying its old IDs',async()=>{
  const scope=controllers().createScope({api:async path=>path.includes('/fragment-selection?')?{latest_revision:3,fragment_ids:['old-revision']}:excerpts()});
  scope.bind(source());await scope.load();const selected=['kept'];assert.equal(await scope.select(selected,'replace'),null);
  assert.equal(scope.state.latestRevision,3);assert.match(scope.state.error,/thay đổi/);assert.deepEqual(selected,['kept']);
});

test('reload restores filter draft/page only for the same source revision, not the next revision',async()=>{
  const saved={sourceId:'s1',revision:2,filters:{q:'ip'},draft:{q:'subnet'},offset:40,open:true};
  const scope=controllers().createScope({api:async()=>excerpts(2,40),saved});scope.bind(source());await scope.load();
  assert.equal(scope.state.offset,40);assert.equal(scope.state.draft.q,'subnet');assert.equal(scope.dirty(),true);assert.equal(scope.state.open,true);
  scope.bind(source('s1',3));assert.equal(scope.state.offset,0);assert.equal(scope.state.draft.q,'');assert.equal(scope.state.open,false);
});

test('invalid location number stays a draft and does not issue a read or AI request',async()=>{
  let calls=0;const scope=controllers().createScope({api:async()=>{calls++;return excerpts();}});scope.bind(source());
  scope.setDraft('position','1.5');assert.equal(await scope.search(),false);assert.equal(calls,0);assert.equal(scope.state.draft.position,'1.5');
  assert.match(scope.state.error,/số nguyên/);
});
