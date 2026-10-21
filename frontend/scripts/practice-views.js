'use strict';
/* Local fixture practice. Fixed answers use IDs; short answers are explicitly
   self-reviewed, never presented as an AI grade. */
window.PRACTICE_VIEWS = (() => {
  const labels = {
    mcq:['Trắc nghiệm · một đáp án','Multiple choice · one answer'],
    cloze:['Điền khuyết','Fill in the blank'],
    matching:['Ghép cặp','Matching'],
    ordering:['Sắp xếp thứ tự','Ordering'],
    short_answer:['Tự luận ngắn','Short answer']
  };
  const L=(s,vi,en)=>s.uiLanguage==='en'?en:vi;
  function init(s,D){
    // A two-question attempt already in progress keeps its original scope.
    if(!Array.isArray(s.practiceQuestionIds)){
      const legacy=Object.keys(s.checked||{}).length&&['practice','result'].includes(s.tab);
      s.practiceQuestionIds=(legacy?D.questions.slice(0,2):D.questions).map(q=>q.id);
    }
    s.practiceQuestionIds=s.practiceQuestionIds.filter(id=>D.questions.some(q=>q.id===id));
    if(!s.practiceQuestionIds.length)s.practiceQuestionIds=D.questions.map(q=>q.id);
    s.qIndex=Math.max(0,Math.min(Number(s.qIndex)||0,questions(s,D).length-1));
    if(!s.selfReview||typeof s.selfReview!=='object'||Array.isArray(s.selfReview))s.selfReview={};
    if(typeof s.practiceAttemptId!=='string'){
      const prior=s.attemptHistory?.at(-1);
      s.practiceAttemptId=s.tab==='result'&&(prior?.total??2)===questions(s,D).length?prior?.id||'attempt-'+Date.now():'attempt-'+Date.now();
    }
  }
  function questions(s,D){return (s.practiceQuestionIds||D.questions.map(q=>q.id)).map(id=>D.questions.find(q=>q.id===id)).filter(Boolean);}
  const typeLabel=(q,s)=>L(s,...labels[q.type]);
  const answerFor=(q,s)=>s.answers[q.id]??(q.type==='ordering'?q.initialOrder:undefined);
  function canCheck(q,a){
    if(q.type==='mcq')return q.options.some(x=>x.id===a);
    if(q.type==='cloze'||q.type==='short_answer')return typeof a==='string'&&a.trim().length>0;
    if(q.type==='matching')return Boolean(a&&typeof a==='object'&&!Array.isArray(a)&&q.left.every(x=>q.right.some(r=>r.id===a[x.id]))&&new Set(q.left.map(x=>a[x.id])).size===q.left.length);
    if(q.type==='ordering')return Array.isArray(a)&&a.length===q.items.length&&new Set(a).size===q.items.length&&a.every(id=>q.items.some(x=>x.id===id));
    return false;
  }
  function isCorrect(q,a){
    if(q.type==='short_answer')return null;
    if(!canCheck(q,a))return false;
    if(q.type==='mcq')return a===q.correctOptionId;
    if(q.type==='cloze')return q.acceptedAnswers.includes(a.normalize('NFC').trim());
    if(q.type==='matching')return q.left.every(x=>a[x.id]===q.correctPairs[x.id]);
    if(q.type==='ordering')return a.every((id,i)=>id===q.correctOrder[i]);
    return false;
  }
  function answerText(q){
    if(q.type==='mcq')return q.options.find(x=>x.id===q.correctOptionId).text;
    if(q.type==='cloze')return q.answerDisplay;
    if(q.type==='matching')return q.left.map(x=>x.text+' → '+q.right.find(r=>r.id===q.correctPairs[x.id]).text).join('\n');
    if(q.type==='ordering')return q.correctOrder.map((id,i)=>(i+1)+'. '+q.items.find(x=>x.id===id).text).join('\n');
    return q.referenceAnswer;
  }
  function questionCardButton(q,c){
    const saved=c.state.personalCards?.some(x=>x.originQuestion===q.id&&x.questionRevision===c.D.practiceRevision);
    return `<button class="text-button" data-action="${saved?'view-question-card':'save-question-card'}" data-question="${q.id}">${c.icon('cards')}${L(c.state,saved?'Đã lưu · mở thẻ':'Lưu câu này thành thẻ',saved?'Saved · open card':'Save question as a card')}</button>`;
  }
  function inputs(q,a,checked,c){
    const {state:s,e,icon}=c;
    if(q.type==='mcq')return `<div class="answers" role="group" aria-label="${L(s,'Chọn một đáp án','Choose one answer')}">${q.options.map((o,i)=>`<button class="answer ${a===o.id?'selected':''} ${checked&&o.id===q.correctOptionId?'correct':''} ${checked&&a===o.id&&a!==q.correctOptionId?'incorrect':''}" data-action="answer" data-answer="${o.id}" aria-pressed="${a===o.id}" ${checked?'disabled':''}><span class="letter">${String.fromCharCode(65+i)}</span>${e(o.text)}${checked&&o.id===q.correctOptionId?icon('check'):!checked&&a===o.id?`<span class="answer-selection" aria-hidden="true">${icon('check')}</span>`:''}</button>`).join('')}</div>`;
    if(q.type==='cloze')return `<label class="field">${L(s,'Số host dùng được','Usable host count')}<input class="cloze-input" id="cloze" inputmode="numeric" autocomplete="off" value="${e(a||'')}" ${checked?'disabled':''} placeholder="…"></label>`;
    if(q.type==='short_answer')return `<label class="field">${L(s,'Cách giải thích của bạn','Your explanation')}<textarea class="short-answer-input" id="short-answer" rows="4" maxlength="1500" ${checked?'disabled':''} placeholder="${L(s,'Viết theo cách bạn hiểu…','Explain in your own words…')}">${e(a||'')}</textarea></label><p class="question-helper">${L(s,'Tự đối chiếu với lời giải sau khi gửi. Chưa chấm bằng AI.','Compare with the reference after submitting. AI grading is not connected.')}</p>`;
    if(q.type==='matching')return `<div class="matching-list">${q.left.map(x=>`<label class="matching-row ${a?.[x.id]?'is-picked':''} ${checked?(a?.[x.id]===q.correctPairs[x.id]?'is-correct':'is-incorrect'):''}"><span>${e(x.text)}</span><select id="match-${x.id}" data-match="${x.id}" ${checked?'disabled':''} aria-label="${L(s,'Ghép','Match')} ${e(x.text)}"><option value="">${L(s,'Chọn địa chỉ…','Choose address…')}</option>${q.right.map(r=>`<option value="${r.id}" ${a?.[x.id]===r.id?'selected':''}>${e(r.text)}</option>`).join('')}</select><span class="pair-state" aria-hidden="true">${a?.[x.id]?icon(checked&&a[x.id]!==q.correctPairs[x.id]?'info':'check'):''}</span></label>`).join('')}</div><p class="question-helper" role="status">${L(s,'Mỗi địa chỉ dùng một lần. Chọn đủ ba cặp để kiểm tra.','Use each address once. Choose all three pairs to check.')}${a&&Object.values(a).filter(Boolean).length>new Set(Object.values(a).filter(Boolean)).size?` <strong>${L(s,'Có địa chỉ đang được chọn hai lần.','An address is selected twice.')}</strong>`:''}</p>`;
    const order=canCheck(q,a)?a:q.initialOrder;
    return `<p class="question-helper">${L(s,'Dùng nút lên/xuống để đổi thứ tự. Có thể thao tác bằng bàn phím.','Use the up/down buttons to reorder. Keyboard controls are supported.')}</p><ol class="ordering-list">${order.map((id,i)=>`<li class="ordering-item" data-order-item="${id}"><span class="order-number">${i+1}</span><strong>${e(q.items.find(x=>x.id===id).text)}</strong><div class="order-controls"><button data-action="order-move" data-item="${id}" data-direction="up" ${checked||i===0?'disabled':''} aria-label="${L(s,'Đưa lên','Move up')}: ${e(q.items.find(x=>x.id===id).text)}">${icon('up')}</button><button data-action="order-move" data-item="${id}" data-direction="down" ${checked||i===order.length-1?'disabled':''} aria-label="${L(s,'Đưa xuống','Move down')}: ${e(q.items.find(x=>x.id===id).text)}">${icon('down')}</button></div></li>`).join('')}</ol>`;
  }
  function feedback(q,a,c){
    const {state:s,e,icon,sourceLink}=c;const correct=isCorrect(q,a);
    if(q.type==='short_answer')return `<div class="feedback self-review" role="status"><strong>${icon('book')}${L(s,'Lời giải tham khảo · tự đối chiếu','Reference answer · self review')}</strong><p>${e(q.referenceAnswer)}</p><ul>${q.rubric.map(x=>`<li>${e(x)}</li>`).join('')}</ul><p>${e(q.explanation)}</p>${sourceLink(q.sourceRefs)}<div class="self-review-options" role="group" aria-label="${L(s,'Tự đánh giá phần đã hiểu','Review your understanding')}">${[['understood','Đã hiểu các ý chính','I understand the key ideas'],['review','Cần ôn lại','Needs review']].map(([id,vi,en])=>`<button class="secondary ${s.selfReview[q.id]===id?'selected':''}" data-action="self-review" data-review="${id}" aria-pressed="${s.selfReview[q.id]===id}">${L(s,vi,en)}</button>`).join('')}</div>${questionCardButton(q,c)}</div>`;
    return `<div class="feedback ${correct?'':'incorrect'}" role="status"><strong>${icon(correct?'check':'info')}${L(s,correct?'Chính xác.':'Chưa chính xác.',correct?'Correct.':'Not correct yet.')}</strong><p>${e(q.explanation)}</p>${['matching','ordering'].includes(q.type)?`<details class="answer-reference"><summary>${L(s,'Xem đáp án chuẩn','Show reference answer')}</summary><p class="answer-lines">${e(answerText(q))}</p></details>`:''}${sourceLink(q.sourceRefs)}${questionCardButton(q,c)}</div>`;
  }
  function render(c){
    const {state:s,e,icon}=c;if(s.tab==='result')return completion(c);
    const list=questions(s,c.D),q=list[s.qIndex],a=answerFor(q,s),checked=Boolean(s.checked[q.id]);
    return `${list.length!==c.D.questions.length?`<p class="legacy-attempt">${L(s,'Bạn đang tiếp tục lượt hai câu trước. Lượt mới có đủ năm dạng câu.','You are continuing the previous two-question session. New sessions include all five types.')} <button class="text-button" data-action="start-practice">${L(s,'Mở lượt mới','Start a new session')}</button></p>`:''}<div class="practice-header"><span>${L(s,'Lượt luyện của bài · câu','Lesson practice · question')} ${s.qIndex+1}/${list.length}</span><div class="thin-progress"><span style="width:${(s.qIndex+1)/list.length*100}%"></span></div></div><section class="question-card"><span class="tag mint">${typeLabel(q,s)}</span><h2>${e(q.prompt)}</h2>${inputs(q,a,checked,c)}${checked?feedback(q,a,c):''}<div class="practice-actions"><button class="text-button" data-action="hint">${icon('chat')}${L(s,'Gợi ý từng bước','Step-by-step hint')}</button>${checked?`<button class="primary" data-action="next">${L(s,s.qIndex===list.length-1?'Hoàn thành lượt luyện':'Câu tiếp theo',s.qIndex===list.length-1?'Finish practice':'Next question')}${icon('arrow')}</button>`:`<button class="primary" data-action="check" ${canCheck(q,a)?'':'disabled'}>${L(s,q.type==='short_answer'?'Gửi & tự đối chiếu':'Kiểm tra',q.type==='short_answer'?'Submit & review':'Check')}${icon('check')}</button>`}</div><div class="question-report"><button class="text-button muted" data-action="report">${L(s,'Báo câu có vấn đề','Report a question issue')}</button></div></section>`;
  }
  function summary(s,D){
    const list=questions(s,D),fixed=list.filter(q=>q.type!=='short_answer');
    return {total:list.length,autoTotal:fixed.length,correct:fixed.filter(q=>isCorrect(q,answerFor(q,s))).length,shortCount:list.length-fixed.length};
  }
  function attempt(s,D){
    const stats=summary(s,D);
    return {id:s.practiceAttemptId,revision:stats.total===2?'illustration-v1':D.practiceRevision,...stats,questionIds:questions(s,D).map(q=>q.id),answers:JSON.parse(JSON.stringify(s.answers)),selfReview:{...s.selfReview}};
  }
  function completion(c){
    const {state:s,D,icon,e}=c,stats=summary(s,D),list=questions(s,D);
    return `<section class="completion"><div class="completion-title"><img src="assets/fox-celebrate-v2.png" alt="${L(s,'Milo ăn mừng','Milo celebrating')}"><div><div class="eyebrow">${L(s,'Lượt luyện đã hoàn thành','Practice completed')}</div><h2>${L(s,'Kết quả lượt luyện','Practice results')}</h2></div></div><div class="score-row"><div><strong>${stats.correct}/${stats.autoTotal}</strong><small>${L(s,'Câu đúng · chấm cố định','Correct · fixed-answer grading')}</small></div><div><strong>${stats.total}</strong><small>${L(s,'Câu đã gửi','Questions submitted')}</small></div></div>${stats.shortCount?`<p>${L(s,'Tự luận được tự đối chiếu, không cộng vào điểm chấm cố định.','Short answers are self-reviewed and excluded from the fixed-answer score.')}</p>`:''}<p>${L(s,'Hoàn thành lượt luyện mở bài tiếp, không có điểm tối thiểu.','Completing practice unlocks the next lesson, with no minimum score.')}</p><div class="completion-actions"><button class="primary" data-action="open-course" data-course="network">${L(s,'Về cây tiến trình','Back to progress tree')}${icon('arrow')}</button><button class="secondary" data-action="retry">${L(s,'Luyện lại lượt này','Retry this session')}</button></div><section class="result-question-list" aria-label="${L(s,'Xem lại từng câu','Review each question')}">${list.map(q=>`<article><div><span>${q.type==='short_answer'?L(s,s.selfReview[q.id]==='review'?'Cần ôn · tự đánh giá':s.selfReview[q.id]==='understood'?'Đã hiểu · tự đánh giá':'Đã gửi · chưa tự đánh giá',s.selfReview[q.id]==='review'?'Needs review · self-reported':s.selfReview[q.id]==='understood'?'Understood · self-reported':'Submitted · not self-reviewed'):L(s,isCorrect(q,answerFor(q,s))?'Đúng':'Cần ôn',isCorrect(q,answerFor(q,s))?'Correct':'Needs review')}</span><strong>${e(q.prompt)}</strong></div>${questionCardButton(q,c)}</article>`).join('')}</section><button class="text-button" data-action="tab" data-tab="reading">${L(s,'Quay lại bài học','Return to lesson')}</button></section>`;
  }
  return {init,questions,typeLabel,answerFor,canCheck,isCorrect,answerText,render,summary,attempt};
})();
