const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..','scripts');
function fixture(){
  const sandbox={window:{},document:{addEventListener(){}},Date,Set};vm.createContext(sandbox);
  for(const file of ['data.js','practice-views.js','product-views.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),sandbox);
  return {D:sandbox.window.DEMO_DATA,V:sandbox.window.PRACTICE_VIEWS,P:sandbox.window.PRODUCT_VIEWS};
}
const plain=x=>JSON.parse(JSON.stringify(x));
test('MCQ IDs and normalized numeric answers reject distractors and partial answers',()=>{
  const {D,V}=fixture();
  assert.equal(V.isCorrect(D.questions[0],'q-network-opt-64'),true);
  for(const bad of ['B','192.168.1.64','q-network-opt-70',undefined])assert.equal(V.isCorrect(D.questions[0],bad),false);
  assert.equal(V.isCorrect(D.questions[1],' 62 '),true);
  for(const bad of ['64','62 host','6',''])assert.equal(V.isCorrect(D.questions[1],bad),false);
});
test('Matching uses pair IDs, rejects duplicate targets and survives display reordering',()=>{
  const {D,V}=fixture(),q=D.questions[2],answer={network:'addr-64',broadcast:'addr-127','first-host':'addr-65'};
  assert.equal(V.isCorrect(q,answer),true);
  assert.equal(V.isCorrect({...q,left:[...q.left].reverse(),right:[...q.right].reverse()},answer),true);
  assert.equal(V.canCheck(q,{network:'addr-64',broadcast:'addr-64','first-host':'addr-65'}),false);
  assert.equal(V.canCheck(q,{network:'addr-64'}),false);
  assert.equal(V.isCorrect(q,{...answer,network:'addr-127',broadcast:'addr-64'}),false);
});
test('Ordering requires a complete permutation and the order supported by source §5',()=>{
  const {D,V}=fixture(),q=D.questions[3];
  assert.equal(V.isCorrect(q,q.correctOrder),true);
  assert.equal(V.isCorrect(q,q.initialOrder),false);
  assert.equal(V.canCheck(q,['read-prefix','read-prefix','find-block','boundaries','usable']),false);
  assert.equal(V.canCheck(q,q.correctOrder.slice(0,4)),false);
});
test('Short answers are ungraded; self review does not inflate the fixed-answer score',()=>{
  const {D,V}=fixture(),s={answers:{},checked:{},tab:'reading',selfReview:{}};V.init(s,D);
  s.answers[D.questions[0].id]=D.questions[0].correctOptionId;s.answers[D.questions[1].id]='62';
  s.answers[D.questions[2].id]={...D.questions[2].correctPairs};s.answers[D.questions[3].id]=[...D.questions[3].correctOrder];
  s.answers[D.questions[4].id]='An explanation';s.selfReview[D.questions[4].id]='understood';
  assert.equal(V.isCorrect(D.questions[4],s.answers[D.questions[4].id]),null);
  assert.deepEqual(plain(V.summary(s,D)),{total:5,autoTotal:4,correct:4,shortCount:1});
});
test('Legacy two-question scope and stored attempt snapshots remain independent of later edits',()=>{
  const {D,V}=fixture(),s={tab:'result',answers:{[D.questions[0].id]:'q-network-opt-64',[D.questions[1].id]:'62'},checked:{[D.questions[0].id]:true,[D.questions[1].id]:true}};
  V.init(s,D);assert.equal(V.questions(s,D).length,2);
  const old=V.attempt(s,D);assert.equal(old.total,2);assert.equal(old.revision,'illustration-v1');
  s.answers[D.questions[0].id]='q-network-opt-zero';
  assert.equal(old.answers[D.questions[0].id],'q-network-opt-64');
  s.practiceQuestionIds=D.questions.map(q=>q.id);s.answers[D.questions[3].id]=[...D.questions[3].correctOrder];
  const next=V.attempt(s,D);s.answers[D.questions[3].id].reverse();
  assert.deepEqual(plain(next.answers[D.questions[3].id]),plain(D.questions[3].correctOrder));
  assert.equal(old.correct,2);
});
test('Saving a question creates one personal card; editing it preserves fixtures and attempt history',()=>{
  const {D,V,P}=fixture(),s={uiLanguage:'vi',answers:{},checked:{},attemptHistory:[{correct:0,revision:'illustration-v1'}]},source=JSON.stringify(D.cards);
  P.init(s);const c={state:s,D},events=[],api={save(){},render(){},toast(){},go(x){events.push(x)},dialog:{close(){}}};
  const b={dataset:{question:D.questions[3].id}};
  P.handle('save-question-card',b,c,api);P.handle('save-question-card',b,c,api);
  assert.equal(s.personalCards.length,1);assert.equal(events[0],'flashcards');
  assert.equal(s.personalCards[0].back.includes('1. Đọc prefix'),true);
  const old=s.personalCards[0],history=JSON.stringify(s.attemptHistory);s.cardMemory[old.id]='known';
  s.cardDraft={id:old.id,front:'Own question',back:'Own answer',sourceRefs:old.sourceRefs};P.saveCard(c,api);
  assert.equal(s.personalCards[0].revision,2);assert.equal(s.personalCards[0].previous[0].front,old.front);
  assert.equal(s.cardMemory[old.id],undefined);assert.equal(JSON.stringify(D.cards),source);assert.equal(JSON.stringify(s.attemptHistory),history);
});
