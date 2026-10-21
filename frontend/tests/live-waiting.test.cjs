const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function ui(){const c={window:{}};vm.runInNewContext(fs.readFileSync(require.resolve('../scripts/live-waiting.js'),'utf8'),c);return c.window.LIVE_WAITING;}
const T=(a,b)=>a,E=s=>String(s).replaceAll('<','&lt;'),B=(action,label)=>`<button data-live="${action}">${label}</button>`;
test('waiting shows actual saved counts and an indeterminate state when total is unknown',()=>{
 const u=ui();assert.equal(u.render({s:{},T,E,B,label:''}),'');
 const known=u.render({s:{busy:true,job:{id:'j'},jobProgress:{planned_stages:6,saved_stages:2}},T,E,B,label:'Đang tạo câu'});
 assert.match(known,/max="6" value="2"/);assert.match(known,/2\/6/);assert.match(known,/cancel-job/);assert.match(known,/aria-hidden="true"/);
 const unknown=u.render({s:{busy:true},T,E,B,label:'Đang gửi'});assert.match(unknown,/Chưa có phần trăm chính xác/);assert.doesNotMatch(unknown,/value="\d+"/);
});
test('upload progress names the file and never invents a completion percentage',()=>{
 const html=ui().render({s:{busy:true,uploadWork:{done:2,total:5,name:'file<txt>'}},T,E,B,label:''});assert.match(html,/file&lt;txt>/);assert.match(html,/2\/5 tài liệu đã đọc/);assert.doesNotMatch(html,/100%|ước tính.*giây/);
});
test('AI-format errors are distinguished from upload errors and saved reading remains disclosed',()=>{
 const u=ui(),html=u.error({s:{error:'AI trả cấu trúc Cloze requires exactly one blank',partialReading:{}},T,E});
 assert.match(html,/không phải lỗi định dạng file/);assert.match(html,/Bài đọc và những câu hợp lệ đã được lưu/);assert.match(html,/<details>/);
 assert.match(u.error({s:{error:'File PDF hỏng'},T,E}),/File PDF hỏng/);
 assert.match(u.error({s:{error:'AI chưa chọn được đáp án khớp duy nhất trong một câu nguồn rõ ràng',partialReading:{}},T,E}),/Bài đọc và những câu hợp lệ đã được lưu/);
});
test('a partial question set is usable but never presented as complete and reasons are escaped',()=>{
 const u=ui(),unit={data:{},generation:{question_coverage:{complete:false,generated_count:4,requested_count:5,uncreated:[{kind:'cloze',reason:'Nguồn <khó đọc>'}]}}};
 const html=u.coverage({unit,T,E});assert.match(html,/Bài đã sẵn sàng/);assert.match(html,/4\/5/);assert.match(html,/Điền khuyết/);assert.match(html,/Nguồn &lt;khó đọc>/);assert.match(html,/<details>/);
 assert.doesNotMatch(html,/complete-questions/);assert.match(u.coverage({unit,T,E,B,canEdit:true}),/complete-questions/);
 unit.generation.question_coverage.complete=true;assert.equal(u.coverage({unit,T,E}),'');assert.equal(u.coverage({unit:{},T,E}),'');
});
test('whole-chapter waiting distinguishes reading from synthesis and never calls partial coverage ready',()=>{
 const u=ui(),chapter={read_parts:2,total_parts:5,status:'reading',complete:false};
 assert.match(u.chapterLabel(chapter,T),/Đang đọc toàn chương.*2\/5/);
 assert.match(u.chapterLabel({...chapter,read_parts:5,status:'synthesizing'},T),/Đang tổng hợp toàn chương.*5\/5/);
 assert.equal(u.chapterLabel({...chapter,complete:true},T),'');
 const s={courseId:'c',chapterProgress:{courseId:'c',unitId:'u',saved_stages:2,...chapter,covered_fragments:8,total_fragments:20}};
 const html=u.chapterNotice({s,unit:{id:'u'},T,E,B});assert.match(html,/Chưa tạo câu hỏi mới/);assert.match(html,/8\/20/);assert.doesNotMatch(html,/100%|đã hiểu|complete-questions/);
 assert.equal(u.chapterNotice({s,unit:{id:'another'},T,E,B}),'');
 assert.equal(u.chapterNotice({s:{...s,courseId:'another'},unit:{id:'u'},T,E,B}),'');
 assert.match(u.chapterNotice({s,unit:{id:'u',data:{}},T,E,B}),/complete-questions/);
 assert.equal(u.chapterNotice({s:{...s,chapterProgress:{...s.chapterProgress,complete:true}},unit:{id:'u'},T,E,B}),'');
});
