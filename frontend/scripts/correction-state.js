'use strict';
/* Recover an owned request from GET /jobs; reconnect never submits AI work. */
window.CORRECTION_STATE=(()=>{
  const targets=new Set(['lesson','question','card']);
  function recover(job){
    const c=job?.context;
    const resumable=['failed','cancelled'].includes(job?.status)||job?.status==='succeeded'&&job.result?.continuation_required===true&&!job.result?.proposal_id;
    if(job?.task!=='correction'||job.feedback_deferred||!resumable||!job.partial?.correction_scope?.sha256||!job.partial?.chapter_context||
       typeof job.id!=='string'||!job.id||typeof c?.course_id!=='string'||!c.course_id||typeof c.unit_id!=='string'||!c.unit_id||
       !Number.isInteger(c.expected_revision)||c.expected_revision<1||!targets.has(c.target)||!Number.isInteger(c.index)||c.index<0||c.index>20||
       typeof c.request!=='string'||!c.request.length||c.request.length>2000)return null;
    return {id:job.id,courseId:c.course_id,unitId:c.unit_id,revision:c.expected_revision,target:c.target,index:c.index,request:c.request};
  }
  function matches(p,courseId,unitId,revision){
    return !!p&&p.courseId===courseId&&p.unitId===unitId&&p.revision===revision&&typeof p.request==='string';
  }
  function body(p,courseId,unitId,revision){
    if(!matches(p,courseId,unitId,revision))throw Error('Yêu cầu sửa không khớp bài hoặc phiên bản đang xem.');
    return {unit_id:p.unitId,expected_revision:p.revision,target:p.target,index:p.index,request:p.request,resume_job_id:p.id};
  }
  function handle(p){
    if(!p)return null;
    // No request text, AI replacement or answer in localStorage.
    return {id:p.id,courseId:p.courseId,unitId:p.unitId,revision:p.revision};
  }
  function notice({pending,courseId,unitId,revision,T,B}){
    if(!matches(pending,courseId,unitId,revision))return '';
    return `<div class="live-notice" role="status"><p>${T('Yêu cầu sửa đã được lưu. Tiếp tục sẽ dùng lại phần đọc chương đã xong và giữ nguyên phạm vi sửa. Bạn vẫn xem trước rồi mới áp dụng.','Your correction request is saved. Continuing reuses completed chapter reading and keeps the same scope. Review the preview before applying it.')}</p>${B('resume-correction',T('Tiếp tục yêu cầu sửa','Continue saved correction'))}</div>`;
  }
  return {recover,matches,body,handle,notice};
})();
