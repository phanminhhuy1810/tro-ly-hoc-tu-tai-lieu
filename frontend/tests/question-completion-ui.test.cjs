const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function ui(){const c={window:{}};vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/question-completion-ui.js'),'utf8'),c);return c.window.QUESTION_COMPLETION_UI;}
const T=(a,b)=>a,E=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),B=(a,l)=>`<button data-live="${a}">${l}</button>`;
const base={course_id:'c',unit_id:'unit-1',base_revision:2,existing_count:3,requested_count:5,available_slots:5,missing:[{stage:'cloze',kind:'cloze',can_generate:true,reason:'Try a different literal answer.'},{stage:'ordering',kind:'ordering',can_generate:false,reason:'No sequence <found>.'}]};
test('only source-eligible slots are selectable and the result is clearly a preview',()=>{
 const html=ui().dialog({info:base,T,E,B});assert.match(html,/value="cloze" checked/);assert.match(html,/value="ordering" disabled/);assert.match(html,/No sequence &lt;found>/);assert.match(html,/3\/5/);assert.match(html,/data-revision="2"/);assert.match(html,/xem trước khi áp dụng/);
});
test('empty or blocked scope offers no generate action and does not imply AI was called',()=>{
 const blocked=ui().dialog({info:{...base,missing:[base.missing[1]]},T,E,B});assert.match(blocked,/<button class="primary" disabled>/);assert.match(blocked,/Chưa gọi AI hoặc trừ Coin/);
 const complete=ui().dialog({info:{...base,missing:[],existing_count:5},T,E,B});assert.match(complete,/Bài đã đủ số câu/);assert.match(complete,/<button class="primary" disabled>/);
});
test('resume belongs to the same course unit and base revision only',()=>{
 const pending={courseId:'c',unitId:'unit-1',revision:2,stages:['cloze']};
 assert.match(ui().dialog({info:base,pending,T,E,B}),/resume-question-completion/);
 for(const change of [{courseId:'other'},{unitId:'unit-2'},{revision:3}])assert.doesNotMatch(ui().dialog({info:base,pending:{...pending,...change},T,E,B}),/resume-question-completion/);
});
test('preview shows the actual added question and retained question count before apply',()=>{
 const old=[{prompt:'Old one'},{prompt:'Old two'}],added={prompt:'New source-backed question'};
 const html=ui().preview({proposal:{base_revision:2,before:{questions:old},after:{questions:[...old,added],question_coverage:{uncreated:[{reason:'Missing <steps>'}]}}},T,E,renderQuestion:q=>`<p>${E(q.prompt)}</p>`});
 assert.match(html,/2 câu được giữ nguyên/);assert.match(html,/Thêm 1 câu · tổng cộng 3/);
 assert.match(html,/Câu mới 3/);assert.match(html,/New source-backed question/);assert.match(html,/Old one/);assert.match(html,/Missing &lt;steps>/);
 assert.equal(html.match(/New source-backed question/g).length,1);
});
