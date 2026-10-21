'use strict';
window.LIVE_WAITING=(()=>{
  function chapterLabel(chapter,T){
    if(!chapter||chapter.complete)return '';
    return (chapter.status==='synthesizing'?T('Đang tổng hợp toàn chương · ','Connecting the whole chapter · '):T('Đang đọc toàn chương · ','Reading the whole chapter · '))+chapter.read_parts+'/'+chapter.total_parts+T(' phần đã đọc',' parts read');
  }
  function chapterNotice({s,unit,T,E,B}){
    const c=s.chapterProgress;
    if(!c||c.courseId!==s.courseId||c.unitId!==unit.id||!c.saved_stages||c.complete)return '';
    return `<section class="live-notice" role="status"><strong>${T('Đang đọc toàn bộ phạm vi chương đã duyệt','Reading the entire approved chapter scope')}</strong><p>${E(c.read_parts)}/${E(c.total_parts)} ${T('phần đã đọc','parts read')} · ${E(c.covered_fragments)}/${E(c.total_fragments)} ${T('đoạn được đọc đủ','excerpts fully read')}. ${T('Chưa tạo câu hỏi mới. Bấm tiếp tục để đọc/tổng hợp phần còn lại; các phần đã đọc được dùng lại.','New questions have not been generated. Continue to read and connect the remaining parts; saved analysis is reused.')}</p>${unit.data?B('complete-questions',T('Tiếp tục đọc và bổ sung câu','Continue reading and complete questions')):''}</section>`;
  }
  function render({s,T,E,B,label}){
    if(!s.busy&&!s.job)return '';
    const uploading=s.busy&&s.uploadWork,progress=s.jobProgress;
    const total=uploading?s.uploadWork.total:progress?.planned_stages;
    const done=uploading?s.uploadWork.done:progress?.saved_stages;
    const message=uploading?T('Đang gửi và đọc tài liệu: ','Uploading and reading: ')+s.uploadWork.name:label;
    return `<section class="live-working live-wait-card" aria-busy="true"><span class="live-paper-loader" aria-hidden="true"><i></i><i></i><i></i></span><div class="live-wait-copy"><strong data-live-job-status role="status">${E(message)}</strong><p>${uploading?T('File đọc xong sẽ được giữ ngay; bước tiếp theo là kiểm tra nội dung.','Each extracted file is saved; next you can review its contents.'):s.job?T('Phần đã hoàn tất được lưu. Bạn có thể dừng lượt này và tiếp tục sau.','Completed stages are saved. You can stop this request and continue later.'):T('Đang chờ máy chủ xác nhận.','Waiting for the server to confirm.')}</p><progress data-live-work-progress aria-label="${T('Phần đã hoàn tất','Completed stages')}" ${total?`max="${total}" value="${done||0}"`:''}></progress><small data-live-work-count>${total?`${done||0}/${total} ${T(uploading?'tài liệu đã đọc':'phần đã lưu',uploading?'files extracted':'stages saved')}`:T('Chưa có phần trăm chính xác','An exact percentage is not available')}</small></div><div class="live-wait-actions">${s.job?B('cancel-job',T('Dừng lượt này','Stop this request'),`data-job="${E(s.job.id)}"`):''}${s.job&&!s.observingJob?B('resume-job',T('Đọc lại trạng thái','Check status')):''}</div></section>`;
  }
  function error({s,T,E}){
    if(!s.error)return '';
    const ai=/AI trả|AI.*cấu trúc|AI chưa chọn được đáp án|Cloze|câu điền khuyết|INVALID_OUTPUT|không hợp lệ ở question/.test(s.error);
    if(!ai)return `<p class="live-error" role="alert">${E(s.error)}</p>`;
    return `<section class="live-error" role="alert"><strong>${T(/Cloze/.test(s.error)?'AI chưa tạo được câu điền khuyết hợp lệ.':'AI trả nội dung chưa hợp lệ.',/Cloze/.test(s.error)?'AI could not produce a valid fill-in-the-blank question.':'The AI response did not pass validation.')}</strong><p>${T('Đây là lỗi tạo nội dung, không phải lỗi định dạng file vừa tải. Tài liệu gốc vẫn được giữ.','This is a content-generation error, not an upload-format error. Your original document is retained.')}</p>${s.partialReading?`<p>${T('Bài đọc và những câu hợp lệ đã được lưu; tiếp tục sẽ dùng lại các phần đó.','The reading and valid questions are saved; continuing reuses those stages.')}</p>`:''}<details><summary>${T('Chi tiết lỗi','Error details')}</summary><p>${E(s.error)}</p></details></section>`;
  }
  function paint(root,p){
    const bar=root.querySelector('[data-live-work-progress]'),count=root.querySelector('[data-live-work-count]');
    if(bar&&p?.planned_stages){bar.max=p.planned_stages;bar.value=p.saved_stages||0;}
    if(count&&p?.planned_stages)count.textContent=(p.saved_stages||0)+'/'+p.planned_stages;
  }
  function coverage({unit,T,E,B,canEdit=false}){
    const c=unit?.generation?.question_coverage;
    if(!unit?.data||!c||c.complete)return '';
    const names={mcq:T('Trắc nghiệm','Multiple choice'),cloze:T('Điền khuyết','Fill in the blank'),matching:T('Ghép cặp','Matching'),ordering:T('Sắp xếp','Ordering'),short_answer:T('Tự luận ngắn','Short answer')};
    return `<section class="live-notice live-question-coverage" role="status"><strong>${T('Bài đã sẵn sàng · ','Lesson ready · ')}${E(c.generated_count)}/${E(c.requested_count)} ${T('câu được tạo','questions created')}</strong><p>${T('Bạn có thể học và luyện những câu đã tạo. Các câu chưa đối chiếu được với nguồn được giữ lại lý do bên dưới.','You can study and practise the created questions. Reasons for the missing questions are listed below.')}</p><details><summary>${T('Xem phần chưa tạo','View missing questions')}</summary><ul>${(c.uncreated||[]).map(q=>`<li><strong>${E(names[q.kind]||q.kind)}</strong>: ${E(q.reason)}</li>`).join('')}</ul></details>${canEdit&&B?B('complete-questions',T('Bổ sung câu còn thiếu','Complete missing questions')):''}</section>`;
  }
  return {render,error,paint,coverage,chapterLabel,chapterNotice};
})();
