const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function ui(){const c={window:{}};vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/source-scope-review-ui.js'),'utf8'),c);return c.window.SOURCE_SCOPE_REVIEW_UI;}
const plain=v=>JSON.parse(JSON.stringify(v));
const E=v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),T=(vi,en)=>en,B=(a,l,attrs='')=>`<button data-live="${a}" ${attrs}>${l}</button>`;
test('exclusion removes only explicitly suggested selected IDs and undo cannot add unknown IDs',()=>{
 const u=ui(),all=['a','b','c','d'];const r=u.exclude(all,['a','c','d'],['a','b','foreign']);assert.deepEqual(plain(r),{selected:['c','d'],removed:['a']});
 assert.deepEqual(plain(u.restore(all,['d'],[...r.removed,'foreign'])),['a','d']);assert.deepEqual(plain(u.exclude(all,[],['a'])),{selected:[],removed:[]});
});
test('advanced preferences survive a scope adjustment without leaking server-only metadata',()=>{
 const extra=ui().preferencesExtras({difficulty:'applied',question_types:['mcq'],question_count:2,card_count:3,teacher_notes:'Use chapter3',terms_to_keep:['LAN'],extraction_revision:9,unknown:'ignore',source_id:'s'});
 assert.deepEqual(plain(extra),{difficulty:'applied',question_types:['mcq'],question_count:2,card_count:3,teacher_notes:'Use chapter3',terms_to_keep:['LAN']});
});
function options(n=25){const ids=Array.from({length:n},(_,i)=>'f'+i);return {source:{id:'s',revision:2,fragments:ids.map((id,i)=>({id,text:'Cover <script> '+i,locator:{slide:1}}))},assessment:{source_id:'s',revision:2,candidate_ids:ids,groups:[{title_vi:'Bìa',title_en:'Cover',fragment_ids:ids}]},selected:ids,undoIds:[],page:0,open:true,T,E,B,locationText:()=> 'Slide1'};}
test('review pages show 20 excerpts but explicitly disclose an all-results exclusion count',()=>{
 const html=ui().panel(options());assert.equal((html.match(/class="live-intro-item"/g)||[]).length,20);assert.match(html,/Exclude all 25 selected suggestions/);assert.match(html,/1\/2/);assert.match(html,/leaves no study content/);assert.doesNotMatch(html,/<script>/);
 const second=ui().panel({...options(),page:1});assert.equal((second.match(/class="live-intro-item"/g)||[]).length,5);assert.match(second,/2\/2/);
});
test('stale or foreign assessment does not expose an exclusion control',()=>{
 const o=options();assert.equal(ui().panel({...o,assessment:{...o.assessment,revision:1}}),'');assert.equal(ui().panel({...o,assessment:{...o.assessment,source_id:'other'}}),'');
});
test('outline requires returning to preferences instead of altering an existing plan silently',()=>{
 const html=ui().panel({...options(),outline:true});assert.match(html,/data-live="edit-preferences"/);assert.doesNotMatch(html,/data-live="intro-exclude"/);
 const excluded=ui().panel({...options(2),selected:[],undoIds:['f0']});assert.match(excluded,/outside the study scope/);assert.match(excluded,/Restore 1 excluded excerpts/);
});
