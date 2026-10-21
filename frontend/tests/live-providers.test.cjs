const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

async function picker(){
  const events={},windowEvents={},calls=[];
  const catalogue={selected_model_id:'local',selection_revision:7,models:[
    {id:'local',label:'Local',provider:'local',external:false,selectable:true},
    {id:'gemini',label:'Gemini',provider:'gemini_api',external:true,selectable:true},
    {id:'kaggle',label:'Kaggle',provider:'kaggle',external:true,selectable:true}
  ]};
  const location={hash:'#settings'};
  const document={addEventListener:(name,fn)=>events[name]=fn,getElementById:()=>({focus(){}})};
  const window={addEventListener:(name,fn)=>windowEvents[name]=fn};
  class FormData {constructor(form){this.values=form.values;}get(name){return this.values[name]??null;}}
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../scripts/live-providers.js'),'utf8'),{window,document,location,FormData});
  let html='',modelChanges=0;
  const host={render(){html=window.LIVE_MODELS.panel({state:{uiLanguage:'vi'}});},modelChanged(){modelChanges++;},async api(url,body,method){
    calls.push({url,body,method});
    if(url==='/ai/models')return structuredClone(catalogue);
    if(url==='/ai/selection'){catalogue.selected_model_id=body.model_id;catalogue.selection_revision++;return {model_id:body.model_id,revision:catalogue.selection_revision};}
    throw Error('Unexpected API request');
  }};
  window.LIVE_MODELS.init(host);
  await new Promise(resolve=>setImmediate(resolve));
  const consentChecked=()=>/name="allow_external"[^>]*\bchecked\b/.test(html);
  return {events,windowEvents,location,calls,host,consentChecked,get html(){return html;},get modelChanges(){return modelChanges;},
    select(value){events.change({target:{id:'ai-model-id',value}});},
    consent(checked){events.change({target:{name:'allow_external',checked,closest:selector=>selector==='#ai-model-selection'?{}:null}});},
    submit(){return events.submit({target:{id:'ai-model-selection',values:{allow_external:consentChecked()?'on':null}},preventDefault(){}});}
  };
}

test('explicit provider consent survives unrelated renders and catalogue refresh',async()=>{
  const ui=await picker();
  ui.select('gemini');assert.equal(ui.consentChecked(),false);
  ui.consent(true);ui.host.render();
  assert.equal(ui.consentChecked(),true);
  ui.events.click({target:{closest:()=>true},preventDefault(){}});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(ui.consentChecked(),true);
  assert.equal(ui.calls.some(call=>call.method==='PUT'),false);
});

test('changing provider or re-entering settings requires fresh explicit consent',async()=>{
  const ui=await picker();
  ui.select('gemini');ui.consent(true);ui.host.render();assert.equal(ui.consentChecked(),true);
  ui.select('kaggle');assert.equal(ui.consentChecked(),false);
  ui.select('gemini');assert.equal(ui.consentChecked(),false);
  ui.consent(true);ui.host.render();
  ui.windowEvents.hashchange();
  await new Promise(resolve=>setImmediate(resolve));
  ui.select('gemini');assert.equal(ui.consentChecked(),false);
});

test('confirmed save reports the committed model and sends the current revision',async()=>{
  const ui=await picker();
  ui.select('gemini');ui.consent(true);ui.host.render();await ui.submit();
  const call=ui.calls.find(call=>call.method==='PUT');
  assert.deepEqual(JSON.parse(JSON.stringify(call)),{url:'/ai/selection',body:{model_id:'gemini',expected_revision:7,allow_external:true},method:'PUT'});
  assert.equal(ui.modelChanges,1);
  assert.match(ui.html,/Đã lưu model cho những lượt AI tiếp theo/);
  assert.match(ui.html,/<option value="gemini" selected/);
});
