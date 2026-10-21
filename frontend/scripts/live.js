'use strict';
/* Same-origin backend workspace. The static design prototype stays separate. */
window.LIVE_STUDY = (() => {
  const KEY='study-live-workspace-v1';
  let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(_){ }
  const s={stage:'import',mode:'learn',unitId:'unit-1',...saved,busy:false,error:'',source:null,plan:null,course:null,courses:[],sources:[],chat:[],chatDraft:saved.chatDraft||'',chatSize:'small'};
  let ctx,apiHost,inlineHelp,sourceLibrary,sourceScope,available=false,menu=false,portalLoading=false,statistics=null,statisticsLoading=false,statisticsError='',pulseLease=null,pulsing=false;
  const E=x=>String(x??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  const T=(vi,en)=>ctx?.state.uiLanguage==='en'?en:vi;
  const B=(action,label,attrs='',primary=false)=>{
    const busyDisabled=s.busy&&!['close','chat-menu','chat-resize','chat-small','chat-full','source','cancel-job','resume-job'].includes(action)&&!/(^|\s)disabled(?:\s|=|$)/.test(attrs);
    return `<button type="button" class="${primary?'primary':'secondary'}" data-live="${action}" ${attrs} ${busyDisabled?'disabled data-live-busy-disabled':''}>${label}</button>`;
  };
  const save=()=>{try{localStorage.setItem(KEY,JSON.stringify({stage:s.stage,sourceId:s.sourceId,planId:s.planId,courseId:s.courseId,unitId:s.unitId,mode:s.mode,job:s.job,prefs:s.prefs,chatDraft:s.chatDraft,attemptId:s.attemptId,proposalId:s.proposalId,extractionDraft:s.extractionDraft,outlineDraft:s.outlineDraft,textName:s.textName,textDraft:s.textDraft,pendingLessonJob:s.pendingLessonJob,pendingQuestionJob:s.pendingQuestionJob,pendingCorrectionJob:window.CORRECTION_STATE.handle(s.pendingCorrectionJob),pendingWrites:s.pendingWrites,sourceProposalId:s.sourceProposalId,officeDrafts:s.officeDrafts,sourceProposalDraft:s.sourceProposalDraft,sourceMethod:s.sourceMethod,portalTab:s.portalTab,urlDraft:s.urlDraft,uploadBatch:s.uploadBatch,sourcePage:s.sourcePage,ocrBatchId:s.ocrBatchId,libraryState:s.libraryState,scopeBrowserState:s.scopeBrowserState,scopeNotice:s.scopeNotice,scopeReviewUndo:s.scopeReviewUndo,introReviewOpen:s.introReviewOpen,introReviewPage:s.introReviewPage}));}catch(_){ }};
  function resetWorkspace(){s.scopeReview=null;s.scopeReviewUndo=null;s.introReviewOpen=false;s.introReviewPage=0;s.scopeNotice=false;s.stage='import';s.sourceId=s.planId=s.courseId=s.attemptId=s.proposalId=s.pendingLessonJob=s.pendingQuestionJob=s.pendingCorrectionJob=null;s.source=s.plan=s.course=s.attempt=s.proposal=s.partialReading=null;s.courseFragments=[];s.prefs=s.feedback=s.extractionDraft=s.outlineDraft=s.sourceProposal=s.sourceProposalId=s.subjectAnalysis=s.ocrStatus=s.ocrBatch=s.ocrBatchId=null;menu=false;}
  function preparePreferences(){
    if(!s.source)return;
    const ids=s.source.fragments.map(f=>f.id),previous=s.prefs;
    if(!previous)s.prefs={source_id:s.sourceId,initial_mode:s.mode,expected_extraction_revision:s.source.revision,fragment_ids:ids};
    else if(previous.source_id!==s.sourceId||previous.expected_extraction_revision!==s.source.revision){
      s.prefs={...previous,source_id:s.sourceId,initial_mode:s.mode,expected_extraction_revision:s.source.revision,fragment_ids:[]};
      s.scopeNotice=true;
    }else if(!Array.isArray(previous.fragment_ids))s.prefs.fragment_ids=ids;
    sourceScope?.bind(s.source);
  }
  async function loadScopeReview(){
    if(!s.source)return;
    if(s.scopeReview?.source_id===s.source.id&&s.scopeReview?.revision===s.source.revision)return;
    try{s.scopeReview=await api('/sources/'+s.source.id+'/scope-review?revision='+s.source.revision);s.scopeReviewError='';}
    catch(error){s.scopeReview=null;s.scopeReviewError=error.message;}
  }
  async function openPreferences(){preparePreferences();await Promise.all([sourceScope&&!sourceScope.state.loaded?sourceScope.load():Promise.resolve(),loadScopeReview()]);save();}
  function introReview(outline=false){return window.SOURCE_SCOPE_REVIEW_UI.panel({source:s.source,assessment:s.scopeReview,selected:outline?s.plan.preferences.fragment_ids:s.prefs.fragment_ids,undoIds:s.scopeReviewUndo?.sourceId===s.sourceId&&s.scopeReviewUndo.revision===s.source.revision?s.scopeReviewUndo.ids:[],page:s.introReviewPage,open:s.introReviewOpen,outline,T,E,B,locationText});}
  function syncExcluded(){s.prefs.excluded_fragment_ids=s.source.fragments.map(f=>f.id).filter(id=>!s.prefs.fragment_ids.includes(id));}
  function capturePreferences(form){
    if(!form||!s.source)return;preparePreferences();const d=new FormData(form);
    const visible=[...form.querySelectorAll('[name=fragment_ids]')].map(input=>input.value);
    const fragment_ids=window.SOURCE_BROWSER.mergeVisible(s.source.fragments.map(f=>f.id),s.prefs.fragment_ids,visible,d.getAll('fragment_ids'));
    s.prefs={...window.SOURCE_SCOPE_REVIEW_UI.preferencesExtras(s.prefs),source_id:s.sourceId,initial_mode:s.mode,expected_extraction_revision:s.source.revision,subject:d.get('subject'),goal:d.get('goal'),instructions:d.get('instructions'),language:d.get('language'),unlock_policy:d.get('unlock_policy'),fragment_ids};
    syncExcluded();save();updateScopeControls();
  }
  function updateScopeControls(){
    const panel=document.querySelector('[data-scope-panel]');if(!panel||!sourceScope)return;
    const v=sourceScope.state,count=panel.querySelector('[data-scope-count]');if(count)count.textContent=s.prefs.fragment_ids.length+'/'+s.source.fragments.length;
    for(const button of panel.querySelectorAll('[data-live=scope-add],[data-live=scope-replace]'))button.disabled=s.busy||v.loading||sourceScope.dirty()||!v.loaded||!v.total||v.latestRevision!==s.source.revision;
    const submit=document.querySelector('#live-preferences [data-preferences-submit]');if(submit)submit.disabled=s.busy||!s.prefs.fragment_ids.length||v.latestRevision!==s.source.revision||!s.source.reviewed;
  }
  function captureOutline(form){if(!s.plan)return;const d=new FormData(form);s.plan.outline.title=d.get('title');s.plan.outline.units.forEach((u,i)=>{u.title=d.get('unit-title-'+i);u.objective=d.get('unit-objective-'+i);u.source_refs=d.getAll('unit-refs-'+i);});s.outlineDraft={planId:s.planId,version:s.plan.outline.version,outline:structuredClone(s.plan.outline)};save();}
  const redraw=()=>{save();apiHost?.render();};
  function confirmCoin(quote){
    return new Promise(resolve=>{
      const dialog=document.createElement('dialog');dialog.className='live-history-dialog';
      dialog.setAttribute('aria-label',T('Xác nhận dùng Coin','Confirm Coin use'));
      dialog.innerHTML=`<h2>${T('Lượt trợ giúp này cần','This request costs')} ${E(quote.amount)} Coin</h2><p>${E(quote.message)}</p><p>${T('Khả dụng','Available')}: ${E(quote.wallet.available)} Coin · ${T('Model','Model')}: ${E(quote.model)}</p><p>${T('Lỗi hoặc hủy sẽ nhả Coin đang giữ. Mức tiêu hiện là đề xuất; không có thanh toán tiền thật.','Failure or cancellation releases the hold. Rates are proposed; no cash payment is enabled.')}</p><div class="dialog-actions"><button type="button" class="primary" data-coin-confirm ${quote.insufficient_coin?'disabled':''}>${T('Dùng','Use')} ${E(quote.amount)} Coin</button><button type="button" class="secondary" data-coin-cancel>${T('Giữ yêu cầu, chưa gửi','Keep draft, do not send')}</button></div>${quote.insufficient_coin?`<p>${T('Chưa đủ Coin. Bạn vẫn học, xem lời giải đã có, ôn thẻ và sửa tay được.','Insufficient Coin. Saved lessons, solutions, card review, and manual edits remain available.')}</p>`:''}`;
      const done=accepted=>{dialog.close();dialog.remove();resolve(accepted);};
      dialog.querySelector('[data-coin-confirm]').addEventListener('click',()=>done(true),{once:true});
      dialog.querySelector('[data-coin-cancel]').addEventListener('click',()=>done(false),{once:true});
      dialog.addEventListener('cancel',event=>{event.preventDefault();done(false);},{once:true});
      document.body.append(dialog);dialog.showModal();
    });
  }
  async function api(path,body,method='POST'){
    const options={method:body===undefined?'GET':method,credentials:'same-origin'};
    const nativeIntent=path.endsWith('/ocr-batches')||/^\/ocr-batches\/[^/]+\/resume$/.test(path);
    const createIntent=body!==undefined&&method==='POST'&&(nativeIntent||path==='/plans'||/\/(generate|question-completion|chat|proposals|sessions|vision-review|analyze|short-feedback|actions)$/.test(path));
    let intent;
    if(createIntent){s.pendingWrites ||= {};const digest=JSON.stringify(body);intent=s.pendingWrites[path];if(!intent||intent.digest!==digest)intent=s.pendingWrites[path]={digest,key:crypto.randomUUID()};options.headers={'Idempotency-Key':intent.key};save();}
    if(body instanceof FormData)options.body=body;
    else if(body!==undefined){options.headers={...options.headers,'Content-Type':'application/json'};options.body=JSON.stringify(body);}
    let response=await fetch('/api'+path,options);let value;try{value=await response.json();}catch(_){throw Error(T('Backend chưa chạy ở địa chỉ này.','Backend is unavailable at this address.'));}
    if(response.status===402&&value.detail?.code==='COIN_CONFIRMATION_REQUIRED'){
      if(!createIntent||!await confirmCoin(value.detail))throw Error(T('Đã giữ yêu cầu, chưa gọi AI hoặc trừ Coin.','Request kept; AI was not called and Coin was not spent.'));
      options.headers={...options.headers,'Coin-Quote-Id':value.detail.quote_id};
      response=await fetch('/api'+path,options);value=await response.json();
    }
    if(!response.ok){if(value.detail?.source_id){s.sourceId=value.detail.source_id;s.source=await api('/sources/'+s.sourceId);s.stage='source';}throw Error(typeof value.detail==='string'?value.detail:value.detail?.message||JSON.stringify(value.detail));}
    if(body!==undefined&&path!=='/activity/ping')s.statisticsStale=true;
    if(body!==undefined&&/^\/(sources|source-proposals|ocr-batches)(\/|$)/.test(path))sourceLibrary?.invalidate();
    if(createIntent){if(value.job_id)s.job={id:value.job_id,kind:nativeIntent?'source_ocr':path==='/plans'?'plan':path.endsWith('/generate')?'lesson':path.endsWith('/question-completion')?'question_completion':path.endsWith('/chat')?'chat':path.endsWith('/vision-review')?'source_vision':path.endsWith('/analyze')?'subject_analysis':path.endsWith('/actions')?'inline_help':'correction'};if(path.endsWith('/sessions')&&value.id){s.attemptId=value.id;s.attempt=value;}delete s.pendingWrites[path];save();}
    return value;
  }
  async function refreshStatistics(){
    if(!available||statisticsLoading)return;
    statisticsLoading=true;statisticsError='';s.statisticsStale=false;
    try{const [dashboard,missions,achievements,wallet,history,checkIn]=await Promise.all(['/dashboard','/missions','/achievements','/wallet','/wallet/history','/activity/check-in'].map(path=>api(path)));statistics={dashboard,missions,achievements,wallet,history,checkIn};s.checkIn=checkIn;}
    catch(error){statistics=null;statisticsError=error.message;}
    finally{statisticsLoading=false;if(isServerRoute(location.hash.slice(1)))redraw();}
  }
  const portalRoutes=['home','library'];
  function isServerRoute(route){return available&&(portalRoutes.includes(route)||route==='flashcards'||route==='settings'||window.LIVE_ACTIVITY?.routes.includes(route));}
  async function refreshPortal(){
    if(!available||portalLoading)return;portalLoading=true;
    try{[s.courses,,s.resume,s.checkIn]=await Promise.all([api('/courses'),sourceLibrary.refresh(),api('/resume'),api('/activity/check-in')]);}
    catch(error){s.error=error.message;}
    finally{portalLoading=false;if(portalRoutes.includes(location.hash.slice(1)))redraw();}
  }
  function renderRemote(c){
    ctx=c;
    if((portalRoutes.includes(c.route)||c.route==='flashcards')&&location.port==='8770'){
      if(!available)return `<main id="main" class="product-page studio-home"><h1>${T('Không gian học của bạn','Your study space')}</h1><p role="status">${E(s.connectionError||T('Đang mở các khóa đã lưu…','Opening your saved courses…'))}</p>${s.connectionError?`<a class="secondary" href="/">${T('Thử kết nối lại','Try again')}</a>`:''}</main>`;
      if(c.route==='flashcards')return window.FLASHCARD_UI.renderLibrary(c,s.courses);
      const byRecency=new Map((s.resume||[]).map((item,index)=>[item.course_id,index]));
      const courses=[...s.courses].sort((a,b)=>(byRecency.get(a.id)??Infinity)-(byRecency.get(b.id)??Infinity)).map(course=>({id:course.id,title:course.content.title,total:course.content.units.length,ready:course.content.units.filter(u=>u.data).length,completed:course.content.units.filter(u=>u.completed).length,role:course.access_role}));
      const data={courses,checkIn:s.checkIn,sources:s.sources,sourceBrowser:sourceLibrary?.state,tab:s.portalTab||'courses',live:true,error:s.error};
      return window.STUDIO_VIEWS[c.route](c,data);
    }
    if(c.route==='settings'&&available)return window.PRODUCT_VIEWS.renderRoute(c);
    if(!isServerRoute(c.route))return '';
    if(!statisticsLoading&&((!statistics&&!statisticsError)||s.statisticsStale))refreshStatistics();
    return window.LIVE_ACTIVITY.render(c,statistics,statisticsError);
  }
  async function activityPulse(){
    const current=s.course?.content.units.find(u=>u.id===s.unitId);
    if(!available||pulsing||document.visibilityState!=='visible'||location.hash!=='#live'||s.stage!=='course'||!current?.data||!current.unlocked){pulseLease=null;return;}
    const body={course_id:s.courseId,unit_id:s.unitId,expected_revision:s.course.revision,mode:s.mode};
    const context=JSON.stringify(body);pulsing=true;
    try{const result=await api('/activity/ping',{...body,...(pulseLease?.context===context?{lease_id:pulseLease.lease_id,expected_sequence:pulseLease.sequence}:{})});pulseLease=document.visibilityState==='visible'?{...result,context}:null;}
    catch(_){pulseLease=null;}
    finally{pulsing=false;}
  }
  document.addEventListener('visibilitychange',()=>{pulseLease=null;});
  window.addEventListener('hashchange',()=>{pulseLease=null;const route=location.hash.slice(1);if(route==='flashcards'){window.FLASHCARD_UI.invalidate();}else if(portalRoutes.includes(route))refreshPortal();else if(isServerRoute(route))refreshStatistics();});
  setInterval(activityPulse,20000);
  async function act(fn){if(s.busy)return;s.busy=true;s.error='';redraw();renderChat();try{await fn();}catch(error){s.error=error.message;}finally{s.busy=false;s.uploadWork=null;redraw();renderChat();apiHost?.dialog.querySelectorAll('[data-live-busy-disabled]').forEach(button=>{button.disabled=false;button.removeAttribute('data-live-busy-disabled');});}}
  async function refreshCourse(){
    window.FLASHCARD_UI?.invalidate();
    s.course=await api('/courses/'+s.courseId);s.planId=s.course.plan_id;
    if(s.planId){s.plan=await api('/plans/'+s.planId);s.sourceId=s.plan.source_id;s.source=await api('/sources/'+s.sourceId+'?revision='+s.plan.preferences.extraction_revision);}
    else{s.plan=null;s.sourceId=null;s.source={fragments:await api('/courses/'+s.courseId+'/source-fragments'),metadata:{warnings:[]}};}
    // A course may keep old lessons and new drafts on different sources.
    // This lookup is for course citations; source review keeps its own document.
    s.courseFragments=await api('/courses/'+s.courseId+'/source-fragments');
    s.courses=await api('/courses');
    if(s.course.access_role==='creator'&&unit())s.chapterProgress={courseId:s.courseId,unitId:unit().id,...await api('/courses/'+s.courseId+'/chapter-context?unit_id='+encodeURIComponent(unit().id))};
    else s.chapterProgress=null;
  }
  function progressLabel(value){
    const p=value?.progress;
    if(value?.task==='source_ocr'||s.job?.kind==='source_ocr')return T('OCR trên máy · đã xử lý ','On-device OCR · processed ')+(p?.saved_stages||0)+'/'+(p?.planned_stages||'…')+T(' phần',' items');
    const chapterLabel=window.LIVE_WAITING.chapterLabel(p?.chapter_context,T);
    if(chapterLabel)return chapterLabel;
    if(p?.planned_stages)return T('Đã xử lý ','Processed ')+p.saved_stages+'/'+p.planned_stages+T(' phần · đang tạo tiếp',' stages · continuing');
    return T(p?.phase==='validating'?'Đang kiểm tra câu trả lời…':'AI đang soạn…',p?.phase==='validating'?'Checking the response…':'AI is drafting…');
  }
  function paintJob(value){
    if(s.job?.id!==value.id)return;
    s.jobProgress=value.progress;s.job.context=value.context;window.LIVE_WAITING.paint(document,value.progress);
    if(s.job.kind==='source_ocr'&&value.context?.ocr_batch_id){s.ocrBatchId=value.context.ocr_batch_id;save();}
    document.querySelectorAll('[data-live-job-status]').forEach(node=>node.textContent=progressLabel(value));
    if(s.job.kind==='card_chat')window.FLASHCARD_UI.receiveProgress?.(value.id,value.progress);
    const dialog=apiHost.dialog,target=dialog.querySelector('.live-chat-messages');
    if(!dialog.open||!dialog.className.includes('live-chat')||!target||s.job.kind!=='chat')return;
    if(value.context?.course_id&&value.context.course_id!==s.courseId)return;
    let node=target.querySelector('[data-live-stream]');
    if(!node){node=document.createElement('article');node.className='live-message assistant live-stream-draft';node.dataset.liveStream='';node.innerHTML='<small></small><p class="live-text"></p>'+B('cancel-job',T('Dừng lượt này','Stop this request'),`data-job="${E(value.id)}"`);target.append(node);}
    const nearBottom=target.scrollHeight-target.scrollTop-target.clientHeight<100;
    node.querySelector('small').textContent=T('AI đang soạn · chưa kiểm tra nguồn','AI draft · sources not yet checked');
    node.querySelector('p').textContent=value.progress?.preview?.text||progressLabel(value);
    if(nearBottom)target.scrollTop=target.scrollHeight;
  }
  async function waitJob(job,kind,onProgress){
    s.job={id:job.job_id,kind};s.jobProgress=null;s.observingJob=job.job_id;save();redraw();renderChat();
    let j;
    try{j=await window.LIVE_JOBS.observe(job.job_id,{api,onUpdate:value=>{paintJob(value);onProgress?.(value);}});}
    catch(error){if(kind==='card_chat')window.FLASHCARD_UI.receiveFailure(job.job_id,error.message);throw error;}
    finally{if(s.observingJob===job.job_id)s.observingJob=null;}
    if(kind==='source_ocr'&&(j.result?.ocr_batch_id||j.context?.ocr_batch_id)){s.ocrBatchId=j.result?.ocr_batch_id||j.context.ocr_batch_id;s.ocrBatch=await api('/ocr-batches/'+s.ocrBatchId);s.stage='source';}
    if(j.status==='failed'||j.status==='cancelled'){
      if(kind==='card_chat')window.FLASHCARD_UI.receiveFailure(job.job_id,j.error?.message||T('Lượt hỏi đã dừng; câu hỏi vẫn được giữ.','The request stopped; your question is kept.'));
      s.job=null;s.jobProgress=null;
      if(kind==='question_completion'){s.pendingQuestionJob={id:j.id,courseId:j.context?.course_id||s.courseId,unitId:j.context?.unit_id||s.unitId,revision:j.context?.expected_revision,stages:j.partial?.requested_stages||[]};}
      if(kind==='correction'){s.pendingCorrectionJob=window.CORRECTION_STATE.recover(j);if(s.pendingCorrectionJob){s.stage='course';s.chapterProgress={courseId:s.pendingCorrectionJob.courseId,unitId:s.pendingCorrectionJob.unitId,...j.partial.chapter_context};}}
      if(kind==='lesson'&&(j.partial?.reading||j.partial?.chapter_context)){s.pendingLessonJob={id:j.id,courseId:j.context?.course_id||s.courseId,unitId:j.context?.unit_id||s.unitId};s.partialReading=j.partial.reading;s.chapterProgress={courseId:s.courseId,unitId:j.context?.unit_id||s.unitId,...j.partial.chapter_context};}
      save();throw Error(j.error?.message||(kind==='source_ocr'?T('OCR đã dừng; phần đã xong vẫn được giữ để xem trước hoặc tiếp tục.','OCR stopped; completed items are retained for preview or resume.'):T('Lượt tạo dừng; nguồn vẫn được giữ.','Generation stopped; your source is retained.')));
    }
    s.job=null;s.jobProgress=null;
    if(kind==='correction'&&j.result?.continuation_required){
      await refreshCourse();s.stage='course';s.pendingCorrectionJob=window.CORRECTION_STATE.recover(j);
      s.chapterProgress={courseId:s.courseId,unitId:j.context?.unit_id||s.unitId,...j.result.chapter_context};
      save();return j.result;
    }
    if(j.result?.continuation_required&&['lesson','question_completion'].includes(kind)){
      await refreshCourse();s.stage='course';s.pendingLessonJob=null;s.pendingQuestionJob=null;s.partialReading=null;
      s.chapterProgress={courseId:s.courseId,unitId:j.context?.unit_id||s.unitId,...j.result.chapter_context};
      save();return j.result;
    }
    if(kind==='plan'){s.planId=j.result.plan_id;s.plan=await api('/plans/'+s.planId);s.outlineDraft=null;s.stage='outline';await loadScopeReview();}
    if(kind==='lesson'){await refreshCourse();s.stage='course';s.pendingLessonJob=null;s.partialReading=null;}
    if(kind==='correction'||kind==='question_completion'){if(kind==='question_completion')s.pendingQuestionJob=null;else s.pendingCorrectionJob=null;s.proposalId=j.result.proposal_id;s.proposal=await api('/proposals/'+s.proposalId);s.stage='proposal';}
    if(kind==='subject_analysis'){s.source=await api('/sources/'+s.sourceId);s.subjectAnalysis=await api('/sources/'+s.sourceId+'/analysis');s.stage='preferences';await openPreferences();}
    if(kind==='source_vision'){s.sourceProposalId=j.result.source_proposal_id;s.sourceProposal=await api('/source-proposals/'+s.sourceProposalId);s.stage='source';}
    if(kind==='card_chat')await window.FLASHCARD_UI.receiveChat(job.job_id,j.result);
    if(kind==='chat'){if(!j.context?.course_id||j.context.course_id===s.courseId)s.chat=await api('/courses/'+s.courseId+'/chat');renderChat();}
    save();return j.result;
  }
  async function init(host){
    apiHost=host;
    window.FLASHCARD_UI.init({api,render:host.render,go:host.go,save:host.save,dialog:host.dialog,isWorking:()=>s.busy||!!s.job,
      learn(){s.mode='learn';host.go('live');redraw();},
      async askCard(card,message,unitId,onStart){
        if(s.busy)throw Error(T('Lượt AI khác đang chạy.','Another AI request is running.'));
        s.busy=true;redraw();
        try{const job=await api('/courses/'+card.course_id+'/chat',{unit_id:unitId,card_id:card.id,message});onStart(job);await waitJob(job,'card_chat');}
        finally{s.busy=false;redraw();}
      },
      async correctCard(card){
        s.courseId=card.course_id;s.unitId=card.unit_id;s.mode='cards';await refreshCourse();
        const editor=await api('/courses/'+s.courseId+'/editor');s.editorLesson=editor.content.units.find(u=>u.id===card.unit_id).data;
        const index=s.editorLesson.cards.findIndex(c=>c.front===card.front&&c.back===card.back);if(index<0)throw Error(T('Thẻ đã thay đổi. Tải lại bộ thẻ.','This card changed. Reload the deck.'));
        s.stage='course';host.go('live');correctionDialog();host.dialog.querySelector('[name=scope]').value='card:'+index;
      }
    });
    inlineHelp=window.LIVE_HELP.create({api,waitJob,redraw,T,E,beforeHelp:saveCurrentAnswerDraft});
    if(location.port!=='8770')return;
    try{
      let response=await fetch('/api/health');if(response.status===404)response=await fetch('/api/status');if(!response.ok)throw Error('Backend unavailable');
      s.status=await response.json();if(!s.status.backend)throw Error('Backend unavailable');
      s.profile=await api('/session',{});window.FLASHCARD_UI.setOwner(s.profile.id);available=true;s.limits=await api('/source-limits');
      window.LIVE_MODELS?.init({api,render:host.render,modelChanged(){s.pendingWrites={};save();}});
      sourceLibrary=window.SOURCE_BROWSER.createLibrary({api,saved:s.libraryState,changed(){s.sources=sourceLibrary.state.items;s.libraryState=sourceLibrary.exportState();save();if(location.hash==='#library')redraw();}});
      sourceScope=window.SOURCE_BROWSER.createScope({api,saved:s.scopeBrowserState,changed(){s.scopeBrowserState=sourceScope.exportState();save();if(location.hash==='#live'&&s.stage==='preferences')redraw();}});
      [s.courses,,s.resume,s.checkIn]=await Promise.all([api('/courses'),sourceLibrary.refresh(),api('/resume'),api('/activity/check-in')]);
      if(s.sourceId)s.source=await api('/sources/'+s.sourceId);
      if(s.planId)s.plan=await api('/plans/'+s.planId);
      if(s.plan&&s.stage==='outline'){s.sourceId=s.plan.source_id;s.source=await api('/sources/'+s.sourceId+'?revision='+s.plan.preferences.extraction_revision);await loadScopeReview();}
      if(s.courseId)await refreshCourse();
      if(s.source&&s.stage==='source'&&s.extractionDraft?.sourceId===s.source.id&&s.extractionDraft.revision===s.source.revision)s.source.fragments.forEach((f,i)=>f.text=s.extractionDraft.texts[i]??f.text);
      if(s.plan&&s.stage==='outline'&&s.outlineDraft?.planId===s.plan.id&&s.outlineDraft.version===s.plan.outline.version&&s.plan.status==='preview')s.plan.outline=s.outlineDraft.outline;
      if(s.proposalId&&s.stage==='proposal'){s.proposal=await api('/proposals/'+s.proposalId);if(s.proposal.status!=='preview'){s.stage='course';s.proposal=null;s.proposalId=null;}}
      if(s.ocrBatchId&&s.stage==='source'){const batch=await api('/ocr-batches/'+s.ocrBatchId);if(batch.source_id===s.sourceId)s.ocrBatch=batch;}
      if(s.sourceProposalId&&s.stage==='source'){s.sourceProposal=await api('/source-proposals/'+s.sourceProposalId);if(s.sourceProposal.status!=='preview')s.sourceProposal=s.sourceProposalId=null;}
      if(s.attemptId)s.attempt=await api('/sessions/'+s.attemptId);
      if(s.source&&s.stage==='preferences')await openPreferences();
      if(s.pendingLessonJob&&s.pendingLessonJob.courseId===s.courseId){const previous=await api('/jobs/'+s.pendingLessonJob.id);s.partialReading=previous.partial?.reading;}
      if(s.pendingCorrectionJob?.id){const previous=await api('/jobs/'+s.pendingCorrectionJob.id);s.pendingCorrectionJob=window.CORRECTION_STATE.recover(previous);}
      if(s.job){s.busy=true;await waitJob({job_id:s.job.id},s.job.kind);s.busy=false;}
    }catch(error){s.error=error.message;s.connectionError=T('Chưa kết nối được dữ liệu đã lưu. Mở lại server rồi thử lại.','Saved data is unavailable. Start the server and try again.');s.busy=false;}
    redraw();
  }
  function sourceFragment(id){return s.course&&['course','proposal'].includes(s.stage)?(s.courseFragments||[]).find(f=>f.id===id)||s.source?.fragments.find(f=>f.id===id):s.source?.fragments.find(f=>f.id===id);}
  function refs(ids){if(!s.source)return '';return `<div class="live-refs">${ids.map(id=>{const f=sourceFragment(id);return f?B('source',E(locationText(f.locator)),`data-ref="${E(id)}"`):'';}).join('')}</div>`;}
  function locationText(l){if(l.component_name)return l.component_name+' · '+locationText({...l,component_name:null});if(l.type==='vision_page')return (l.page?T('Trang','Page')+' '+l.page:T('Ảnh','Image')+' '+l.frame)+' · '+T('AI đọc lại','AI transcription');if(l.type==='user_transcription')return T('Bản chép tay · vị trí cần đối chiếu','Manual transcription · verify location');if(l.frame)return T('Ảnh','Image')+' '+l.frame+' · OCR';return l.page?`${T('Trang','Page')} ${l.page}`:l.slide?`Slide ${l.slide}${l.row?` · ${T('hàng','row')} ${l.row}`:''}`:l.paragraph?`${T('Đoạn','Paragraph')} ${l.paragraph}`:l.table?`${T('Bảng','Table')} ${l.table}, ${T('hàng','row')} ${l.row}`:`${T('Dòng','Line')} ${l.line}`;}
  function modePicker(){return `<section class="studio-mode-picker"><div class="studio-section-head"><h2>${T('Bạn muốn học thế nào?','How would you like to study?')}</h2></div><div class="studio-study-modes">${[['learn','book','Học','Learn','Hiểu từng phần, rồi luyện thử','Understand each part, then practise'],['cards','cards','Flashcard','Flashcards','Lật thẻ và ghi nhớ ý chính','Flip cards and recall the key ideas'],['practice','target','Ôn luyện','Practice','Làm câu hỏi để tự kiểm tra','Test yourself with questions']].map(([id,icon,vi,en,subVi,subEn])=>`<button type="button" class="mode-button ${s.mode===id?'selected':''}" data-live="mode" data-mode="${id}" aria-pressed="${s.mode===id}">${ctx.icon(icon)}<strong>${T(vi,en)}</strong><small>${T(subVi,subEn)}</small>${s.mode===id?'<span class="studio-mode-check">✓</span>':''}</button>`).join('')}</div></section>`;}
  function uploadBatchView(){
    if(!s.uploadBatch?.length)return '';
    return `<section class="product-card" aria-live="polite"><h3>${T('Tài liệu trong lượt này','Files in this batch')}</h3>${s.uploadBatch.map(row=>`<p><strong>${E(row.name)}</strong> · ${E(row.error||row.status)} ${row.source_id?B('open-source',T('Mở để kiểm tra/sửa','Open to review/correct'),`data-source="${E(row.source_id)}"`):''}</p>`).join('')}<p>${T('File lỗi được giữ nếu đã nhận; sửa file đó hoặc tiếp tục chỉ với các file đã đọc được. Không tự dùng nội dung chưa đọc.','Received originals are retained on reading failures. Correct them or continue with readable files only. Unread content is not silently included.')}</p>${B('combine-batch',T('Tiếp tục với tài liệu đã đọc được','Continue with readable files'),s.busy?'disabled':'')}</section>`;
  }
  async function useSourceCollection(sources){
    const value=sources.length===1?sources[0]:await api('/sources/collection',{name:T('Bộ tài liệu khóa học','Course source collection'),sources:sources.map(source=>({source_id:source.id,expected_revision:source.revision}))});
    resetWorkspace();s.uploadBatch=null;s.source=value;s.sourceId=value.id;s.sourcePage=0;s.stage='source';
  }
  async function combineBatch(){
    const sources=[];
    for(const row of s.uploadBatch||[])if(row.source_id){const source=await api('/sources/'+row.source_id);if(source.fragments.length)sources.push(source);}
    if(!sources.length)throw Error(T('Chưa có nội dung đã đọc. Mở file để sửa/bổ sung bản chép tay trước.','No readable extraction yet. Open a file to correct or transcribe it first.'));
    await useSourceCollection(sources);
  }
  async function uploadFiles(files){
    const maxFiles=s.limits?.files_per_collection||20,maxBytes=s.limits?.upload_bytes_per_file||52428800;
    if(files.length>maxFiles)throw Error(T('Mỗi lượt chọn tối đa '+maxFiles+' tài liệu; tài liệu đã lưu vẫn còn.','Select up to '+maxFiles+' files in one batch. Saved documents are retained.'));
    resetWorkspace();s.uploadBatch=files.map(file=>({name:file.name,status:T('Đang chờ','Queued')}));s.stage='import';
    const sources=[];
    for(let i=0;i<files.length;i++){
      const row=s.uploadBatch[i],file=files[i];s.uploadWork={name:file.name,total:files.length,done:s.uploadBatch.filter(x=>x.status===T('Đã đọc · cần kiểm tra','Extracted · review required')).length};row.status=T('Đang đọc','Reading');redraw();
      if(file.size>maxBytes){row.error=T('Vượt 50 MiB/file; chưa tải file này.','Over 50 MiB per file; this file has not been uploaded.');continue;}
      try{const form=new FormData();form.append('file',file);const source=await api('/sources/upload',form);row.source_id=source.id;row.status=T('Đã đọc · cần kiểm tra','Extracted · review required');sources.push(source);}
      catch(error){row.error=error.message;if(s.source?.metadata.name===file.name)row.source_id=s.sourceId;s.stage='import';}
      save();redraw();
    }
    if(sources.length===files.length)await useSourceCollection(sources);
  }
  function collectionView(){
    if(s.source.metadata.kind!=='collection')return uploadBatchView();
    return `<section class="product-card"><h3>${T('Tài liệu trong khóa','Course documents')}</h3>${s.source.metadata.components.map(c=>`<p>${E(c.name)} · ${T('Bản trích','Extraction revision')} ${c.extraction_revision} <a class="text-button" href="/api/sources/${c.source_id}/original">${T('Mở file gốc','Open original')}</a> ${B('open-source',T('Sửa nguồn thành phần','Correct component source'),`data-source="${c.source_id}"`)}</p>`).join('')}<p>${T('Sửa nguồn thành phần không tự đổi bộ nguồn này. Nút bên dưới tạo snapshot mới; bản cũ và lịch sử được giữ. Bản sửa tay riêng ở bộ cũ không được tự chép sang.','Editing a component does not update this collection automatically. Create a new snapshot below; the existing version and history are retained. Edits made only in the old collection are not copied automatically.')}</p>${B('refresh-collection',T('Tạo bộ nguồn mới từ các bản trích hiện tại','Create collection from current component revisions'))}</section>`;
  }
  async function loadOCR(){s.ocrStatus=await api('/sources/'+s.sourceId+'/ocr-status');if(s.ocrStatus.revision!==s.source.revision&&!s.extractionDraft)s.source=await api('/sources/'+s.sourceId);if(s.ocrBatchId){const batch=await api('/ocr-batches/'+s.ocrBatchId);if(batch.source_id===s.sourceId)s.ocrBatch=batch;}}
  async function readOCR(items,retryNoText=false){
    if(s.extractionDraft?.sourceId===s.sourceId)throw Error(T('Lưu bản sửa trước khi đọc tiếp.','Save your corrections before continuing.'));
    const body={expected_revision:s.source.revision,...(items?{items}:{}),retry_no_text:retryNoText};
    await waitJob(await api('/sources/'+s.sourceId+'/ocr-batches',body),'source_ocr');await loadOCR();
  }
  const ocrAction=()=>({expected_revision:s.source.revision,expected_batch_version:s.ocrBatch.version});
  function officeAssetsView(){
    if(!/\.(docx|pptx)$/i.test(s.source.metadata.name))return '';
    const list=s.officeAssets?.sourceId===s.sourceId?s.officeAssets.assets:null;
    if(!list)return `<section class="product-card"><h3>${T('Hình trong tài liệu','Images in the document')}</h3>${B('load-office-assets',T('Xem các hình nhúng','List embedded images'))}</section>`;
    if(!list.length)return `<section class="product-card"><p>${T('Chưa tìm thấy hình nhúng trong phần nội dung hỗ trợ. Xem file gốc nếu phần cần học còn thiếu.','No embedded images found in the supported content. Check the original if needed content is missing.')}</p></section>`;
    const drafts=s.officeDrafts?.sourceId===s.sourceId?s.officeDrafts:{sourceId:s.sourceId,texts:{}};
    const selected=list.find(a=>a.id===drafts.selectedId)||list[0];
    const title=a=>a.locator.slide?T('Slide ','Slide ')+a.locator.slide+' · '+T('hình ','image ')+a.locator.image_occurrence:T('Hình ','Image ')+a.locator.image_occurrence+' · '+(a.locator.table?T('bảng ','table ')+a.locator.table+' · '+T('hàng ','row ')+a.locator.row:T('đoạn ','paragraph ')+a.locator.paragraph);
    return `<section class="product-card"><h3>${T('Đối chiếu hình nhúng','Review embedded images')}</h3><label>${T('Chọn hình','Choose image')}<select data-office-asset>${list.map(a=>`<option value="${E(a.id)}" ${a.id===selected.id?'selected':''}>${E(title(a))}${a.embedded?'':' · '+T('liên kết ngoài','external link')}</option>`).join('')}</select></label>${selected.raster_review_supported?`<img class="live-source-preview" src="/api/sources/${s.sourceId}/assets/${selected.id}/image" alt="${E(title(selected))}">`:`<p>${E(selected.warning||T('Chưa có bản ảnh xem được. Có thể mở file gốc và chép tay.','No supported image preview. You can read the original and transcribe it.'))}</p>`}<p>${T('Xem riêng hình đã crop, không phải toàn trang hoặc slide.','This shows the cropped image, not the entire page or slide.')}</p><form id="live-vision-form"><input type="hidden" name="asset_id" value="${E(selected.id)}"><button class="secondary" ${s.busy||!selected.raster_review_supported?'disabled':''}>${T('Nhờ AI đọc hình → xem đề xuất','Read image with AI → preview')}</button></form><details><summary>${T('Chép hoặc sửa tay · không dùng Coin','Transcribe or correct manually · no Coin')}</summary><form id="live-asset-manual"><input type="hidden" name="asset_id" value="${E(selected.id)}"><label>${T('Nội dung của hình đã chọn','Content of the chosen image')}<textarea name="text" data-office-manual="${E(selected.id)}" rows="5" maxlength="20000" required>${E(drafts.texts[selected.id]||'')}</textarea></label><button class="secondary" ${s.busy?'disabled':''}>${T('Xem trước bản chép tay','Preview manual transcription')}</button></form></details></section>`;
  }
  function sourceReview(){const pages=Math.max(1,Math.ceil(s.source.fragments.length/20));s.sourcePage=Math.min(s.sourcePage||0,pages-1);return `${modePicker()}${collectionView()}${window.SOURCE_OCR_UI.render({s,T,E,B,locationText})}<form id="live-source-review"><div class="live-step-title"><h2>${T('Kiểm tra nội dung đã đọc','Review extracted content')}</h2><p>${T('Đối chiếu file gốc; sửa chỗ bị lệch trước khi tạo nội dung.','Compare the original and correct extraction before generation.')}</p><a class="text-button" href="/api/sources/${s.source.id}/original">${s.source.metadata.kind==='collection'?T('Tải danh sách tài liệu','Download source manifest'):T('Mở file gốc','Open original file')}</a></div>${s.source.metadata.warnings.length?`<details class="live-source-warnings"><summary>${T('Lưu ý khi đối chiếu nguồn','Source-review notices')} · ${s.source.metadata.warnings.length}</summary>${s.source.metadata.warnings.map(x=>`<p class="live-notice">${E(x)}</p>`).join('')}</details>`:''}<nav aria-label="${T('Phần bản trích','Extraction pages')}">${B('source-page',T('Trước','Previous'),`data-page="${s.sourcePage-1}" ${s.sourcePage===0?'disabled':''}`)} <span>${T('Phần','Part')} ${s.sourcePage+1}/${pages} · ${s.source.fragments.length} ${T('đoạn','excerpts')}</span> ${B('source-page',T('Tiếp','Next'),`data-page="${s.sourcePage+1}" ${s.sourcePage===pages-1?'disabled':''}`)}</nav>${s.source.fragments.map((f,i)=>({f,i})).slice(s.sourcePage*20,s.sourcePage*20+20).map(({f,i})=>`<section class="live-fragment"><header><strong>${E(locationText(f.locator))}</strong><span>${i+1}/${s.source.fragments.length}</span></header><div class="live-compare"><div><small>${s.source.metadata.kind==='collection'?T('Snapshot nguồn thành phần khi gộp','Component snapshot at collection creation'):T('Bản máy đọc · chưa sửa tay','Reader output · before manual edits')}</small><p class="live-text">${E(f.original_text)}</p></div><label>${T('Bản dùng để học','Text used for study')}<textarea data-extraction="${i}" maxlength="5000" rows="4" required>${E(f.text)}</textarea></label></div></section>`).join('')}<button class="primary" ${s.busy||!s.source.fragments.length?'disabled':''}>${T('Xác nhận nguồn → Nhu cầu','Confirm source → Preferences')}</button></form><details class="product-card"><summary>${T('Đọc lại hoặc bổ sung bản chép tay','Read again or provide a manual transcription')}</summary><p>${T('Giữ nguyên file gốc; tạo bản trích mới để duyệt. Bản chép tay chưa xác minh vị trí trong file.','The original stays unchanged. A new extraction must be reviewed. A manual transcription does not verify its original location.')}</p>${s.source.metadata.kind==='collection'?'':B('retry-source',T('Đọc lại file đã lưu','Read saved original again'))}<form id="live-transcription"><label>${T('Bản chép tay thay bản trích hiện tại','Manual transcription replacing the current extraction')}<textarea name="text" rows="5" required maxlength="1000000"></textarea></label><button class="primary" ${s.busy?'disabled':''}>${T('Lưu bản trích để duyệt','Save extraction for review')}</button></form></details>${/\.(pdf|png|jpe?g|webp|tiff?|bmp|heic)$/i.test(s.source.metadata.name)?`<section class="product-card"><h3>${T('Đối chiếu ảnh hoặc công thức','Check an image or formula')}</h3><p>${T('Nhờ AI đọc lại một trang, xem đề xuất trước khi thay. AI có thể chép sai.','Ask the selected AI to reread one page. Preview before replacing. AI can transcribe incorrectly.')}</p><form id="live-vision-form"><label>${T('Trang PDF / khung ảnh','PDF page / image frame')}<input name="page" type="number" min="1" max="${/\.pdf$/i.test(s.source.metadata.name)?1000:1000}" value="1" required></label><button class="secondary" ${s.busy?'disabled':''}>${T('Đọc lại bằng AI → xem đề xuất','Reread with AI → preview')}</button></form></section>`:''}${officeAssetsView()}${s.sourceProposal?`<section class="product-card"><h3>${T('Đề xuất đọc lại · chưa áp dụng','Rereading proposal · not applied')}</h3><img class="live-source-preview" src="${s.sourceProposal.asset_id?`/api/sources/${s.source.id}/assets/${s.sourceProposal.asset_id}/image`:`/api/sources/${s.source.id}/page-image?page=${s.sourceProposal.page}`}" alt="${T('Trang gốc để đối chiếu','Original page for comparison')}"><div class="live-compare"><div><small>${T('Bản trích trước','Previous extraction')}</small><p class="live-text">${E(s.sourceProposal.before.map(f=>f.text).join('\n'))}</p></div><div><small>${T('Bản đọc đề xuất','Proposed transcription')}</small><p class="live-text">${E(s.sourceProposal.text)}</p></div></div><p class="live-notice">${E(s.sourceProposal.warning)}</p>${s.sourceProposal.uncertain_spans.map(x=>`<p>${E(x)}</p>`).join('')}<details><summary>${T('Sửa bản đọc trước khi áp dụng · không dùng Coin','Edit transcription before applying · no Coin')}</summary><form id="live-source-proposal-edit"><label>${T('Bản sửa tay','Manual correction')}<textarea name="text" data-source-proposal-edit rows="6" maxlength="20000" required>${E(s.sourceProposalDraft?.id===s.sourceProposalId?s.sourceProposalDraft.text:s.sourceProposal.text)}</textarea></label><button class="secondary" ${s.busy?'disabled':''}>${T('Xem trước bản đã sửa','Preview correction')}</button></form></details><form id="live-vision-apply"><button class="primary" ${s.busy?'disabled':''}>${T('Dùng bản đề xuất → duyệt lại nguồn','Use proposal → review source again')}</button>${B('discard-source-proposal',T('Bỏ đề xuất','Discard proposal'))}</form></section>`:''}`;}
  function preferences(){preparePreferences();const p=s.prefs||{};return `<form id="live-preferences"><h2>${T('Bạn muốn học thế nào?','How would you like to study?')}</h2>${B('analyze-source',T('Gợi ý môn từ một phần nguồn · dùng AI','Suggest subject from a source sample · uses AI'))}${s.subjectAnalysis?.status==='suggested'?`<p class="live-notice">${T('Môn là gợi ý từ nguồn; bạn được đổi.','The subject is a source-based suggestion; you can change it.')} ${E(s.subjectAnalysis.reason)} ${E(s.subjectAnalysis.uncertainty)}</p>`:''}<div class="live-form-grid"><label>${T('Môn học · bạn được sửa','Subject · editable')}<input name="subject" value="${E(p.subject||s.source.metadata.subject_suggestion)}" maxlength="200" required></label><label>${T('Mục tiêu','Goal')}<input name="goal" value="${E(p.goal||'Hiểu từ đầu, luyện các ý quan trọng')}" maxlength="1000" required></label><label>${T('Ngôn ngữ nội dung','Content language')}<select name="language"><option value="vi" ${p.language!=='en'?'selected':''}>${T('Tiếng Việt · giữ thuật ngữ Anh','Vietnamese · preserve English terms')}</option><option value="en" ${p.language==='en'?'selected':''}>English</option></select></label><label>${T('Cách mở bài','Unlock policy')}<select name="unlock_policy"><option value="locked">${T('Hoàn thành lượt luyện để mở bài tiếp','Complete practice to unlock the next lesson')}</option><option value="open" ${p.unlock_policy==='open'?'selected':''}>${T('Mở tự do','Open access')}</option></select></label><label class="live-wide">${T('Lưu ý hoặc phần cần ưu tiên','Instructions or priorities')}<textarea name="instructions" rows="3" maxlength="2000">${E(p.instructions||'')}</textarea></label></div>${s.scopeNotice?`<p class="live-notice" role="status">${T('Bản trích đã đổi. Hãy chọn lại phạm vi cho bản mới; môn, mục tiêu và lưu ý vẫn được giữ.','The extraction changed. Choose the scope for this revision; your subject, goal and instructions are retained.')}</p>`:''}${introReview()}${window.SOURCE_BROWSER.scopePanel({controller:sourceScope,source:s.source,selected:p.fragment_ids,T,E,B,locationText})}<button class="primary" data-preferences-submit ${s.busy||!p.fragment_ids.length||!s.source.reviewed||sourceScope.state.latestRevision!==s.source.revision?'disabled':''}>${T('Tạo phác thảo để duyệt','Generate outline for review')}</button></form>`;}
  function outline(){return `<form id="live-outline"><h2>${T('Duyệt lộ trình trước khi tạo bài','Approve the outline before generating lessons')}</h2>${introReview(true)}${s.plan.outline.method==='source_sections_not_ai'?`<p class="live-notice"><strong>${s.plan.preferences.fragment_ids.length} ${T('đoạn nguồn','excerpts')} → ${s.plan.outline.units.length} ${T('bài','lessons')}</strong><br>${T('Lộ trình được chia theo vị trí trong nguồn, chưa phải nội dung AI đã đọc/sinh. Toàn bộ đoạn đã chọn đều được phân bổ; AI chỉ tạo từng bài sau khi bạn duyệt. Bạn được sửa tên, mục tiêu và nguồn của bài.','This roadmap groups source sections; it is not an AI reading of the entire collection. Every selected excerpt is assigned. AI generates lessons individually after your approval; titles, objectives and assignments are editable.')}</p>`:''}<label>${T('Tên khóa','Course title')}<input name="title" value="${E(s.plan.outline.title)}" required maxlength="200"></label>${s.plan.outline.units.map((u,i)=>`<section class="live-outline-unit"><span class="live-number">${i+1}</span><div><label>${T('Tên bài','Lesson title')}<input name="unit-title-${i}" value="${E(u.title)}" required maxlength="200"></label><label>${T('Mục tiêu bài này','Lesson objective')}<textarea name="unit-objective-${i}" rows="2" required maxlength="1000">${E(u.objective)}</textarea></label><details class="live-outline-sources"><summary>${T('Phân bổ nguồn cho bài','Assign sources to this lesson')} · ${u.source_refs.length}</summary>${s.source.fragments.filter(f=>s.plan.outline.method==='source_sections_not_ai'?u.source_refs.includes(f.id):s.plan.preferences.fragment_ids.includes(f.id)).map(f=>`<label class="live-source-choice"><input type="checkbox" name="unit-refs-${i}" value="${E(f.id)}" ${u.source_refs.includes(f.id)?'checked':''}><span>${E(locationText(f.locator))} · ${E(f.text.slice(0,100))}</span></label>`).join('')}${B('edit-unit-scope',T('Đổi phân bổ nguồn','Change source assignment'),`data-index="${i}"`)}</details>${refs(u.source_refs)}${i>0?B('merge-unit',T('Gộp với bài trước','Merge with previous lesson'),`data-index="${i}"`):''}</div></section>`).join('')}<p class="live-notice">${T('Bạn có thể sửa tên, mục tiêu, phân bổ nguồn hoặc gộp các bài trước khi duyệt. Chỉ tạo từng bài sau khi duyệt; nội dung AI cần đối chiếu nguồn.','Edit titles, objectives and source assignments, or merge lessons before approval. Lessons are generated individually after approval; review AI content against its sources.')}</p><button class="primary" ${s.busy?'disabled':''}>${T('Duyệt và tạo bài đầu','Approve and generate the first lesson')}</button></form>`;}
  function importView(){
    const method=s.sourceMethod||'file';
    const options=[['file','file','Tải tài liệu','Upload a file','PDF, Word, slide hoặc ảnh','PDF, Word, slides or images'],['text','notebook','Dán ghi chú','Paste notes','Nội dung bạn đã chép lại','Text you have already copied'],['link','globe','Dùng đường link','Use a link','Một bài viết công khai','A public article']];
    const fields=method==='file'?`<label class="live-upload studio-upload">${ctx.icon('file')}<strong>${T('Chọn tài liệu từ máy','Choose a file')}</strong><span>PDF · DOCX · PPTX · TXT · PNG · JPG</span><input id="live-file" type="file" multiple accept=".txt,.md,.docx,.pdf,.pptx,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp,.heic" ${s.busy?'disabled':''}><small>${T('Chọn tối đa 20 tài liệu cùng lúc, mỗi file tối đa 50 MiB. Kiểm tra bản đọc trước khi tạo bài.','Select up to 20 files at once, up to 50 MiB each. Review extraction before generating lessons.')}</small></label>`:method==='text'?`<form id="live-text"><label>${T('Tên tài liệu','Document title')}<input name="name" value="${E(s.textName||'')}" placeholder="${T('Ví dụ: Chương 2 — Địa chỉ IP','Example: Chapter 2 — IP addresses')}" required maxlength="200"></label><label>${T('Nội dung cần học','Study material')}<textarea name="text" rows="7" required maxlength="1000000" placeholder="${T('Dán ghi chú hoặc đoạn tài liệu vào đây…','Paste your notes or an excerpt here…')}">${E(s.textDraft||'')}</textarea></label><button class="primary">${T('Đọc nội dung','Read material')}${ctx.icon('arrow')}</button></form>`:`<form id="live-url"><label>${T('Link bài viết công khai','Public article link')}<input name="url" type="url" value="${E(s.urlDraft||'')}" required maxlength="3000" placeholder="https://…"></label><p class="studio-helper">${T('Dùng bài viết mở được mà không cần đăng nhập.','Use an article that can be read without signing in.')}</p><button class="primary">${T('Đọc bài viết','Read article')}${ctx.icon('arrow')}</button></form>`;
    return `<section class="studio-import"><div class="studio-method-tabs" role="group" aria-label="${T('Cách đưa tài liệu vào','Source method')}">${options.map(([id,icon,vi,en,noteVi,noteEn])=>`<button class="mode-button ${method===id?'selected':''}" data-live="source-method" data-method="${id}" aria-pressed="${method===id}">${ctx.icon(icon)}<span><strong>${T(vi,en)}</strong><small>${T(noteVi,noteEn)}</small></span>${method===id?ctx.icon('check'):''}</button>`).join('')}</div><div class="product-card studio-source-form">${fields}${uploadBatchView()}</div><p class="studio-helper">${ctx.icon('info')}${T('Sau khi thêm tài liệu, chọn Học, Flashcard hoặc Ôn luyện. Ảnh và công thức cần được đối chiếu lại.','After adding material, choose Learn, Flashcards or Practice. Review images and formulas against the original.')}</p></section>`;
  }
  function render(c){ctx=c;let body;
    if(!available&&location.port==='8770')body=`<section class="product-card"><p role="status">${E(s.connectionError||T('Đang kết nối không gian học đã lưu…','Connecting to your saved study space…'))}</p>${s.connectionError?`<a class="secondary" href="#live" onclick="location.reload()">${T('Thử kết nối lại','Try connection again')}</a>`:''}</section>`;
    else if(!available)body=`<section class="product-card"><h2>${T('Mở bản có backend','Open the backend version')}</h2><p>${T('Bản đang xem là giao diện tĩnh. Backend local chạy ở cổng 8770.','This is the static interface. The local backend runs on port 8770.')}</p><a class="primary" href="http://127.0.0.1:8770/#live">${T('Mở luồng tài liệu thật','Open the real-source flow')}</a></section>`;
    else body=s.stage==='source'&&s.source?sourceReview():s.stage==='preferences'&&s.source?preferences():s.stage==='outline'&&s.plan?outline():s.stage==='proposal'&&s.proposal?proposalView():s.stage==='course'&&s.course?courseView():importView();
    const titles={import:T('Thêm tài liệu','Add document'),source:T('Kiểm tra tài liệu','Review your document'),preferences:T('Chọn cách học phù hợp','Make it yours'),outline:T('Duyệt lộ trình','Review the outline'),proposal:T('Xem thay đổi trước khi lưu','Review your changes'),course:s.course?.content.title};
    const index=['import','source','preferences','outline'].indexOf(s.stage);
    const steps=index>=0?`<ol class="studio-stepper" aria-label="${T('Các bước tạo khóa','Create course steps')}">${[['Tài liệu','Source'],['Kiểm tra','Review'],['Cách học','Preferences'],['Lộ trình','Outline']].map(([vi,en],i)=>`<li class="${i===index?'current':i<index?'done':''}" ${i===index?'aria-current="step"':''}><span>${i<index?'✓':i+1}</span>${T(vi,en)}</li>`).join('')}</ol>`:'';
    return `<main id="main" class="product-page live-page studio-live" data-user-content><header class="product-head"><div><button class="text-button studio-back" data-action="page" data-page="library">${ctx.icon('back')}${T('Khóa học của bạn','Your courses')}</button><h1>${E(titles[s.stage]||titles.import)}</h1><p>${T(s.stage==='import'?'Bắt đầu bằng tài liệu bạn muốn hiểu.':'Nguồn và phần đã làm được lưu trong không gian của bạn.',s.stage==='import'?'Start with something you want to understand.':'Your source and saved work stay in your workspace.')}</p></div></header>${steps}${window.LIVE_WAITING.render({s,T,E,B,label:s.job?progressLabel({progress:s.jobProgress}):T('Đang xử lý yêu cầu…','Processing your request…')})}${window.LIVE_WAITING.error({s,T,E})}${body}</main>${s.stage==='course'&&s.course?launcher():''}`;
  }
  const unit=()=>s.course?.content.units.find(x=>x.id===s.unitId)||s.course?.content.units[0];
  const answerDrafts=new Map();
  function answerFromForm(form,q){
    const data=new FormData(form);
    return q.kind==='matching'?Object.fromEntries(q.left.map((_,i)=>[q.payload?.left[i]?.id??`left-${i}`,data.get('pair-'+i)||''])):q.kind==='ordering'?s.order.map(i=>q.payload?.options[i]?.id??i):data.get('answer')??'';
  }
  function captureAnswerDraft(){
    const form=document.getElementById('live-answer'),attempt=s.attempt;
    if(!form||!attempt)return;
    const q=attempt.questions.find(q=>q.id===form.dataset.question);if(!q)return;
    const answer=answerFromForm(form,q),key=attempt.id+':'+q.id;
    attempt.drafts ||= {};const current=attempt.drafts[q.id]||{version:0};
    current.answer=answer;attempt.drafts[q.id]=current;
    let entry=answerDrafts.get(key);
    if(!entry){entry={sessionId:attempt.id,itemId:q.id,version:current.version,saved:undefined};answerDrafts.set(key,entry);}
    entry.answer=answer;clearTimeout(entry.timer);
    entry.timer=setTimeout(()=>flushAnswerDraft(entry).catch(error=>{s.error=error.message;}),450);
    return entry;
  }
  function flushAnswerDraft(entry){
    clearTimeout(entry.timer);
    entry.chain=(entry.chain||Promise.resolve()).catch(()=>{}).then(async()=>{
      const answer=structuredClone(entry.answer),digest=JSON.stringify(answer);if(digest===entry.saved)return;
      const result=await api('/sessions/'+entry.sessionId+'/draft',{item_id:entry.itemId,answer,expected_version:entry.version},'PUT');
      entry.version=result.version;entry.saved=digest;
      if(s.attemptId===entry.sessionId&&s.attempt?.drafts?.[entry.itemId])s.attempt.drafts[entry.itemId].version=result.version;
    });return entry.chain;
  }
  async function saveCurrentAnswerDraft(target){
    captureAnswerDraft();
    if(target.kind==='section')return;
    const entry=answerDrafts.get(target.sessionId+':'+target.itemId);if(entry)await flushAnswerDraft(entry);
  }
  document.addEventListener('input',event=>{if(event.target.closest('#live-answer'))captureAnswerDraft();});
  const questionHelp=itemId=>inlineHelp&&itemId?inlineHelp.render({kind:'question',sessionId:s.attemptId,itemId}):'';
  function chapterNotice(u){
    return window.LIVE_WAITING.chapterNotice({s,unit:u,T,E,B});
  }
  function courseView(){const u=unit(),d=u?.data;if(!u)return '';
    const modes=[['learn','Học','Learn'],['cards','Flashcard','Flashcards'],['practice','Ôn luyện','Practice']];
    return `${window.CORRECTION_STATE.notice({pending:s.pendingCorrectionJob,courseId:s.courseId,unitId:u.id,revision:s.course.revision,T,B})}${chapterNotice(u)}<div class="live-course-layout"><aside class="product-card live-tree"><h2>${E(s.course.content.title)}</h2><p>${T('Cây tiến trình','Learning path')}</p>${s.course.content.units.map((x,i)=>`<button type="button" data-live="unit" data-unit="${x.id}" class="live-node ${x.id===u.id?'selected':''} ${x.completed?'completed':''}" ${!x.unlocked||s.busy?'disabled':''}><span class="live-number">${x.completed?'✓':!x.unlocked?'⌑':i+1}</span><span><strong>${E(x.title)}</strong><small>${T(x.completed?'Đã hoàn thành lượt luyện':x.data?'Có bài học':x.unlocked?'Sẵn sàng tạo':'Chưa mở',x.completed?'Practice completed':x.data?'Lesson ready':x.unlocked?'Ready to generate':'Locked')}</small></span></button>`).join('')}${B('history',T('Lịch sử lượt luyện','Practice history'))}</aside><section class="product-card live-lesson"><div class="live-lesson-head"><div><small>${T('Bản','Version')} ${s.course.revision}</small><h2>${E(d?.title||u.title)}</h2><p>${E(u.objective)}</p></div>${d&&s.course.access_role==='creator'?B('correct',T('Sửa nội dung','Correct content')):''}</div><div class="live-mode-select">${modes.map(([id,vi,en])=>B('mode',T(vi,en),`data-mode="${id}" aria-pressed="${s.mode===id}"`,s.mode===id)).join('')}</div>${window.LIVE_WAITING.coverage({unit:u,T,E,B,canEdit:s.course.access_role==='creator'})}${!d?pendingReading(u):s.mode==='cards'?window.FLASHCARD_UI.renderUnit(ctx,s.course,u):s.mode==='practice'?practiceView(d):`<div class="live-reading">${d.sections.map((x,i)=>`<section><span class="live-section-index">${String(i+1).padStart(2,'0')}</span><h3>${E(x.title)}</h3><p class="live-text">${E(x.text)}</p>${refs(x.source_refs)}${inlineHelp.render({kind:'section',courseId:s.courseId,unitId:u.id,revision:s.course.revision,index:i})}</section>`).join('')}<details class="live-map"><summary>${T('Mindmap · các ý chính','Mind map · key ideas')}</summary>${d.mindmap.map((x,i)=>`<div><h3>${E(x.title)}</h3><p>${E(x.text)}</p>${refs(x.source_refs)}${inlineHelp.render({kind:'mindmap',courseId:s.courseId,unitId:u.id,revision:s.course.revision,index:i})}</div>`).join('')}</details>${B('practice',T('Luyện ngay bài này','Practice this lesson'),'',true)}</div>`}</section></div>`;
  }
  function pendingReading(u){
    if(s.course.access_role==='learner')return `<p>${T('Phần này đang chờ người tạo cập nhật. Bạn có thể học nội dung đã có.','This part is awaiting its creator. You can continue with ready content.')}</p>`;
    const partial=s.pendingLessonJob?.courseId===s.courseId&&s.pendingLessonJob?.unitId===u.id&&s.partialReading;
    if(partial)return `${chapterNotice(u)}<p class="live-notice">${T('Bài đọc và các câu hợp lệ đã lưu sẽ được dùng lại khi tiếp tục.','Saved reading and valid questions will be reused when you continue.')}</p><details><summary>${T('Xem phần đã tạo','View saved reading')}</summary>${showValue(partial)}</details>${B('generate',T('Tiếp tục tạo bài','Continue generation'),'',true)}`;
    return `${chapterNotice(u)}<p class="live-notice">${T('AI đọc toàn bộ phạm vi chương đã duyệt, nối các ý chính rồi mới tạo bài và câu hỏi hiểu/vận dụng. Phần đã đọc được lưu để các bài sau dùng lại.','AI reads the entire approved chapter scope and connects its ideas before creating the lesson and understanding/application questions. Saved analysis is reused by later lessons.')}</p>${B('generate',T(s.chapterProgress?.saved_stages?'Tiếp tục đọc và tạo bài':'Đọc chương và tạo bài',s.chapterProgress?.saved_stages?'Continue reading and generate':'Read chapter and generate'),'',true)}`;
  }
  function practiceView(){
    if(!s.attempt||s.attempt.scope?.unit_id!==unit().id)return `<p>${T('Bắt đầu lượt luyện; các câu có đáp án cố định được chấm trên server. Tự luận có lời giải/rubric để đối chiếu.','Start a practice session. Fixed questions are graded on the server; short answers use reference/rubric review.')}</p>${B('start-practice',T('Bắt đầu lượt luyện','Start practice'),'',true)}`;
    const a=s.attempt;
    if(a.result)return `${a.reference_warnings?.length?`<p class="live-notice">${T('Lượt cũ có đáp án đang được xem lại; điểm giữ theo bản đã học, chưa phải kết quả đã kiểm chứng.','This old attempt contains an answer key under review. Its stored score is unchanged and is not a verified assessment.')}</p>`:''}<div class="live-result"><span class="live-number">✓</span><h3>${a.result.score}/${a.result.fixed_total} ${T('câu cố định','fixed questions')}</h3><p>${a.result.self_review_count} ${T('tự luận tự đối chiếu · lịch sử giữ bản','short answer for self-review · history pinned to version')} ${a.revision}</p>${B('tree',T('Về cây tiến trình','Return to learning path'),'',true)} ${B('start-practice',T('Luyện lượt mới','Start another session'))}</div>`;
    if(s.feedback)return `<section class="live-feedback"><h3>${E(s.lastPrompt)}</h3><strong>${s.feedback.correct===null?T('Tự đối chiếu · chưa AI chấm','Self-review · not AI graded'):s.feedback.correct?T('Đúng','Correct'):T('Cần xem lại','Review this answer')}</strong><p class="live-text">${E(s.feedback.explanation)}</p><p>${T('Tham khảo','Reference')}: ${E(Array.isArray(s.feedback.reference)?s.feedback.reference.map((j,i)=>s.lastKind==='matching'?`${s.lastLeft[i]} → ${s.lastOptions[j]}`:s.lastOptions?.[j]??j).join(' · '):s.feedback.reference)}</p>${s.feedback.rubric?.length?`<ul>${s.feedback.rubric.map(x=>`<li>${E(x)}</li>`).join('')}</ul>`:''}${refs(s.feedback.source_refs)}${B('next-question',T('Tiếp tục','Continue'),'',true)}</section>${questionHelp(s.lastQuestionId)}`;
    const q=a.questions.find(x=>!a.answers?.[x.id]);
    const draft=a.drafts?.[q?.id]?.answer;
    if(!q)return `${B('finish',T('Hoàn thành lượt luyện','Complete practice'),'',true)}`;
    let input;
    if(q.kind==='mcq')input=q.options.map((x,i)=>`<label class="live-option"><input type="radio" name="answer" value="${E(q.payload?.options[i]?.id??x)}" ${draft===(q.payload?.options[i]?.id??x)?'checked':''} required><span>${E(x)}</span></label>`).join('');
    else if(q.kind==='matching')input=q.left.map((x,i)=>`<label class="live-match">${E(x)}<select name="pair-${i}" required><option value="">${T('Chọn','Select')}</option>${q.options.map((y,j)=>`<option value="${E(q.payload?.options[j]?.id??String(j))}" ${draft?.[q.payload?.left[i]?.id??`left-${i}`]===(q.payload?.options[j]?.id??String(j))?'selected':''}>${E(y)}</option>`).join('')}</select></label>`).join('');
    else if(q.kind==='ordering'){if(s.orderQuestion!==q.id){s.order=Array.isArray(draft)?draft.map(id=>q.payload?.options.findIndex(x=>x.id===id)??Number(id)):q.options.map((_,i)=>i).reverse();s.orderQuestion=q.id;}input=`<ol class="live-order">${s.order.map((idx,i)=>`<li><span>${E(q.options[idx])}</span>${B('order','↑',`data-index="${i}" data-direction="-1" ${i===0?'disabled':''}`)}${B('order','↓',`data-index="${i}" data-direction="1" ${i===s.order.length-1?'disabled':''}`)}</li>`).join('')}</ol>`;}
    else input=`<label>${T('Câu trả lời','Your answer')}<textarea name="answer" required maxlength="3000" rows="3">${E(draft||'')}</textarea></label>`;
    return `<form id="live-answer" data-question="${q.id}" data-kind="${q.kind}"><p>${Object.keys(a.answers||{}).length+1}/${a.questions.length} · ${T({mcq:'Trắc nghiệm',cloze:'Điền khuyết',matching:'Ghép cặp',ordering:'Sắp xếp',short_answer:'Tự luận ngắn'}[q.kind]||q.kind,{mcq:'Multiple choice',cloze:'Fill in the blank',matching:'Matching',ordering:'Ordering',short_answer:'Short answer'}[q.kind]||q.kind)}</p><h3>${E(q.prompt)}</h3>${input}<button class="primary" ${s.busy?'disabled':''}>${T(q.kind==='short_answer'?'Gửi và đối chiếu':'Kiểm tra',q.kind==='short_answer'?'Submit and review':'Check answer')}</button></form>${questionHelp(q.id)}`;
  }
  function showValue(x){return `<h3>${E(x.title||x.prompt||x.front)}</h3>${x.sections?x.sections.map(z=>`<h4>${E(z.title)}</h4><p class="live-text">${E(z.text)}</p>${refs(z.source_refs)}`).join('')+[['questions','Câu hỏi','Questions'],['cards','Flashcard','Flashcards'],['mindmap','Mindmap','Mind map']].map(([key,vi,en])=>x[key]?.length?`<details class="live-preview-parts"><summary>${T(vi,en)} · ${x[key].length}</summary>${x[key].map(showValue).join('')}</details>`:'').join(''):`<p class="live-text">${E(x.back||x.text||x.explanation||'')}</p>${x.left?.length?`<p>${x.left.map(E).join(' · ')}</p>`:''}${x.options?.length?`<p>${x.options.map(E).join(' · ')}</p>`:''}${x.answer!==undefined?`<p>${T('Đáp án tham khảo','Reference')}: ${E(Array.isArray(x.answer)?x.answer.map((j,i)=>x.kind==='matching'?`${x.left[i]} → ${x.options[j]}`:x.options[j]).join(' · '):x.answer)}</p>`:''}${refs(x.source_refs||[])}`}`;}
  function proposalView(){
    const p=s.proposal,completion=p.scope.target==='question_completion';
    const scope={lesson:T('Bài học','Lesson'),question:T('Câu hỏi','Question'),card:T('Flashcard','Flashcard'),question_completion:T('Câu còn thiếu','Missing questions')}[p.scope.target]||p.scope.target;
    const comparison=completion?window.QUESTION_COMPLETION_UI.preview({proposal:p,T,E,renderQuestion:showValue}):`<div class="live-compare"><section><small>${T('Bản đang học','Current version')} ${p.base_revision}</small>${showValue(p.before)}</section><section><small>${T('Bản đề xuất · chưa áp dụng','Proposed · not applied yet')}</small>${showValue(p.after)}</section></div>`;
    return `<section class="product-card"><h2>${completion?T('Xem trước câu bổ sung','Preview additional questions'):T('Xem trước bản sửa','Preview the correction')}</h2><p>${E(p.request)} · ${T('Phạm vi','Scope')}: ${E(scope)}</p>${comparison}<p class="live-notice">${T('Áp dụng tạo phiên bản mới. Kết quả đã học giữ nguyên theo bản cũ.','Applying creates a new version. Previous attempts stay pinned to their original version.')}</p>${B('apply',T('Áp dụng bản sửa','Apply correction'),'',true)} ${B('discard',T('Giữ bản cũ','Keep current version'))}</section>`;
  }
  function correctionDialog(){const d=s.editorLesson;apiHost.dialog.className='live-correction-dialog';apiHost.dialog.innerHTML=`<form id="live-correction"><h2>${T('Sửa khi nội dung bị lệch','Correct content that misses your goal')}</h2><label>${T('Chọn đúng phần cần sửa','Choose the correction scope')}<select name="scope" id="live-correction-scope"><option value="lesson:0">${T('Bài này và nội dung đi kèm','This lesson and its related content')}</option>${d.questions.map((q,i)=>`<option value="question:${i}">${T('Câu','Question')} ${i+1}: ${E(q.prompt.slice(0,80))}</option>`).join('')}${d.cards.map((x,i)=>`<option value="card:${i}">${T('Thẻ','Card')} ${i+1}: ${E(x.front.slice(0,80))}</option>`).join('')}</select></label><label>${T('Điểm bị lệch và yêu cầu sửa','What missed your goal and how to correct it')}<textarea name="request" rows="4" required maxlength="2000" placeholder="${T('Ví dụ: bài cần theo ví dụ trong tài liệu, phần này đang lan sang chương khác…','Example: follow the source example; this part has drifted into another chapter…')}"></textarea></label><label>${T('Cách sửa','Correction method')}<select name="method" id="live-correction-method"><option value="ai">${T('Nhờ AI đề xuất','Ask AI for a proposal')}</option><option value="manual">${T('Chỉnh tay · luôn dùng được','Edit manually · always available')}</option></select></label><div id="live-manual-fields" hidden></div><p>${B('complete-questions',T('Kiểm tra câu còn thiếu','Check missing questions'))}</p><p class="live-notice">${T('Bước tiếp theo là xem trước, chưa thay bài đang học. Lượt đã làm giữ đúng bản cũ.','Next comes a preview. Current content is unchanged until you apply it, and past attempts keep their original version.')}</p><div class="dialog-actions"><button class="primary">${T('Xem bản đề xuất','Preview proposal')}</button>${B('close',T('Đóng','Close'))}</div></form>`;apiHost.dialog.showModal();}
  function manualKeyFields(x){
    return `<fieldset><legend>${T('Nội dung lựa chọn','Choice text')}</legend>${x.options.map((option,i)=>`<label>${T('Lựa chọn ','Choice ')+(i+1)}<input name="option-${i}" value="${E(option)}" required maxlength="1000"></label>`).join('')}</fieldset><fieldset><legend>${T('Đáp án đúng để chấm bằng chương trình','Fixed answer key')}</legend>${x.answer.map((selected,i)=>`<label>${E(x.kind==='matching'?x.left[i]:T('Vị trí ','Position ')+(i+1))}<select name="key-${i}">${x.options.map((option,j)=>`<option value="${j}" ${selected===j?'selected':''}>${E(option)}</option>`).join('')}</select></label>`).join('')}</fieldset>${B('report-question',T('Tạm ngừng dùng câu này để xem lại','Pause this question for review'))}${x.kind==='ordering'?`<details><summary>${T('Đối chiếu quy trình nguồn','Check source procedure')}</summary>${(x.source_refs||[]).map(id=>`<p class="live-text">${E(sourceFragment(id)?.text||'')}</p>`).join('')}</details>`:''}`;
  }
  function manualFields(){const f=document.getElementById('live-correction');if(!f)return;const [target,idx]=f.elements.scope.value.split(':');const d=s.editorLesson,x=target==='lesson'?d:d[target==='card'?'cards':'questions'][Number(idx)];const box=document.getElementById('live-manual-fields');box.hidden=f.elements.method.value!=='manual';if(box.hidden)return;
    box.innerHTML=target==='lesson'?x.sections.map((z,i)=>`<label>${E(z.title)}<textarea name="section-${i}" rows="4" maxlength="5000" required>${E(z.text)}</textarea></label>`).join(''):target==='card'?`<label>${T('Mặt trước','Front')}<textarea name="front" required maxlength="1000">${E(x.front)}</textarea></label><label>${T('Mặt sau','Back')}<textarea name="back" required maxlength="3000">${E(x.back)}</textarea></label>`:`<label>${T('Đề bài','Question')}<textarea name="prompt" required maxlength="2000">${E(x.prompt)}</textarea></label><label>${T('Giải thích','Explanation')}<textarea name="explanation" required maxlength="3000">${E(x.explanation)}</textarea></label>${typeof x.answer==='string'?`<label>${T('Đáp án tham khảo','Reference answer')}${x.kind==='mcq'?`<select name="answer">${x.options.map(y=>`<option ${y===x.answer?'selected':''} value="${E(y)}">${E(y)}</option>`).join('')}</select>`:`<textarea name="answer" required>${E(x.answer)}</textarea>`}</label>`:manualKeyFields(x)}`;
  }
  function launcher(){return `${menu?`<div class="assistant-mode-menu live-chat-menu"><span>${T('Chọn cách mở Milo','Choose how to open Milo')}</span>${B('chat-small',T('Cửa sổ nhỏ · hỏi nhanh','Small window · quick help'))}${B('chat-full',T('Toàn màn hình · đối chiếu rộng','Full screen · more room'))}</div>`:''}<button type="button" class="milo-launcher product-launcher" data-live="chat-menu" aria-expanded="${menu}" aria-label="${T('Chat · chọn cửa sổ nhỏ hoặc toàn màn hình','Chat · choose small window or full screen')}">${ctx.icon('chat')}<span>Milo</span></button>`;}
  function renderChat(){const dialog=apiHost.dialog;if(!dialog.open||!dialog.className.includes('live-chat'))return;const target=dialog.querySelector('.live-chat-messages');if(target){target.innerHTML=s.chat.map(m=>`<div class="live-message ${m.role}"><small>${m.role==='assistant'?'Milo':T('Bạn','You')} · ${T('Bản','Version')} ${m.revision}</small><p class="live-text">${E(m.text)}</p>${refs(m.source_refs||[])}</div>`).join('');if(s.job?.kind==='chat'){target.innerHTML+=`<article class="live-message assistant live-stream-draft" data-live-stream><small>${T('AI đang soạn · chưa kiểm tra nguồn','AI draft · sources not yet checked')}</small><p class="live-text">${E(s.jobProgress?.preview?.text||T('Đang đọc nguồn…','Reading sources…'))}</p>${B('cancel-job',T('Dừng lượt này','Stop this request'),`data-job="${E(s.job.id)}"`)}</article>`;}target.scrollTop=target.scrollHeight;}const sendButton=dialog.querySelector('#live-chat-form button');if(sendButton)sendButton.disabled=s.busy||!!s.job;const input=dialog.querySelector('#live-chat-input');if(input)input.value=s.chatDraft;}
  async function openChat(size){menu=false;s.chatSize=size;if(apiHost.dialog.open)apiHost.dialog.close();s.chat=await api('/courses/'+s.courseId+'/chat');const dialog=apiHost.dialog;dialog.className='live-chat-dialog '+size;dialog.innerHTML=`<header class="live-chat-head"><div><strong>Milo</strong><small>${E(unit().title)} · ${T('Hỏi thuật ngữ và nội dung chung','Terms and general questions')}</small></div><div>${B('chat-resize',size==='full'?T('Thu nhỏ','Compact'):T('Toàn màn hình','Full screen'))}${B('close','×','aria-label="Close chat"')}</div></header><div class="live-chat-messages"></div><p id="live-chat-error" role="alert"></p><form id="live-chat-form"><label class="sr-only" for="live-chat-input">${T('Câu hỏi','Question')}</label><textarea id="live-chat-input" rows="3" maxlength="2000" required placeholder="${T('Hỏi thuật ngữ hoặc ý muốn tìm hiểu…','Ask about a term or topic…')}">${E(s.chatDraft)}</textarea><button class="primary">${T('Gửi','Send')}</button></form>`;if(size==='full')dialog.showModal();else dialog.show();renderChat();dialog.querySelector('#live-chat-input').focus();redraw();}
  document.addEventListener('change',event=>{if(event.target.matches('[data-scope-field]')){sourceScope?.setDraft(event.target.dataset.scopeField,event.target.value);s.scopeBrowserState=sourceScope?.exportState();save();}if(event.target.closest('#live-preferences'))capturePreferences(event.target.form);if(event.target.closest('#live-outline'))captureOutline(event.target.form);if(event.target.id==='live-correction-method'||event.target.id==='live-correction-scope')manualFields();if(event.target.id==='live-file'&&event.target.files.length){const files=[...event.target.files];act(()=>uploadFiles(files));}});
  document.addEventListener('toggle',event=>{if(event.target.matches('[data-intro-review-panel]')){s.introReviewOpen=event.target.open;save();}if(event.target.matches('[data-scope-panel]')&&sourceScope){sourceScope.state.open=event.target.open;s.scopeBrowserState=sourceScope.exportState();save();}},true);
  document.addEventListener('input',event=>{
    if(event.target.matches('[data-source-library-query]')){sourceLibrary?.setDraft(event.target.value);s.libraryState=sourceLibrary?.exportState();save();}
    if(event.target.matches('[data-scope-field]')){sourceScope?.setDraft(event.target.dataset.scopeField,event.target.value);s.scopeBrowserState=sourceScope?.exportState();save();updateScopeControls();}
  });
  document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches('[data-scope-field]')){event.preventDefault();capturePreferences(event.target.form);sourceScope.search();}});
  document.addEventListener('change',event=>{if(event.target.matches('[data-office-asset]')){s.officeDrafts=s.officeDrafts?.sourceId===s.sourceId?s.officeDrafts:{sourceId:s.sourceId,texts:{}};s.officeDrafts.selectedId=event.target.value;redraw();}});
  document.addEventListener('input',event=>{if(event.target.matches('[data-office-manual]')){s.officeDrafts=s.officeDrafts?.sourceId===s.sourceId?s.officeDrafts:{sourceId:s.sourceId,texts:{}};s.officeDrafts.selectedId=event.target.dataset.officeManual;s.officeDrafts.texts[event.target.dataset.officeManual]=event.target.value;save();}if(event.target.matches('[data-source-proposal-edit]')){s.sourceProposalDraft={id:s.sourceProposalId,text:event.target.value};save();}if(event.target.closest('#live-preferences'))capturePreferences(event.target.form);if(event.target.closest('#live-outline'))captureOutline(event.target.form);if(event.target.id==='live-chat-input'){s.chatDraft=event.target.value;save();}if(event.target.dataset.extraction!==undefined&&s.source){const alreadyDirty=s.extractionDraft?.sourceId===s.sourceId;s.source.fragments[Number(event.target.dataset.extraction)].text=event.target.value;s.extractionDraft={sourceId:s.source.id,revision:s.source.revision,texts:s.source.fragments.map(f=>f.text)};save();if(!alreadyDirty){const panel=document.querySelector('.live-native-ocr');if(panel)panel.outerHTML=window.SOURCE_OCR_UI.render({s,T,E,B,locationText});}}if(event.target.closest('#live-url')){s.urlDraft=event.target.value;save();}if(event.target.closest('#live-text')){s.textName=document.querySelector('#live-text [name=name]').value;s.textDraft=document.querySelector('#live-text [name=text]').value;save();}});
  document.addEventListener('click',event=>{
    const b=event.target.closest('[data-live]');if(!b||b.disabled)return;const action=b.dataset.live;
    if(action==='cancel-job'){const id=b.dataset.job||s.job?.id;if(id&&id===s.job?.id){b.disabled=true;api('/jobs/'+id+'/cancel',{}).catch(error=>{s.error=error.message;b.disabled=false;redraw();});}return;}
    if(action==='resume-job'){if(s.job&&!s.observingJob)act(()=>waitJob({job_id:s.job.id},s.job.kind));return;}
    if(action==='refresh-statistics'){refreshStatistics();return;}
    if(action==='check-in'){act(async()=>{s.checkIn=await api('/activity/check-in',{});if(statistics)statistics.checkIn=s.checkIn;apiHost.toast(T(s.checkIn.newly_checked?'Đã lưu điểm danh hôm nay.':'Hôm nay đã điểm danh rồi.',s.checkIn.newly_checked?'Today’s check-in is saved.':'Already checked in today.'));});return;}
    if(action==='portal-tab'){s.portalTab=b.dataset.tab;redraw();return;}
    if(action==='library-next'){sourceLibrary.next();return;}
    if(action==='library-previous'){sourceLibrary.previous();return;}
    if(action==='library-reload'){sourceLibrary.reload();return;}
    if(action==='library-clear'){sourceLibrary.search('');return;}
    if(action.startsWith('scope-')){
      capturePreferences(document.getElementById('live-preferences'));
      if(action==='scope-search')sourceScope.search();
      if(action==='scope-clear')sourceScope.clear();
      if(action==='scope-next')sourceScope.next();
      if(action==='scope-previous')sourceScope.previous();
      if(action==='scope-none'){s.prefs.fragment_ids=[];s.scopeNotice=false;redraw();}
      if(action==='scope-replace'||action==='scope-add')act(async()=>{
        const ids=await sourceScope.select(s.prefs.fragment_ids,action==='scope-replace'?'replace':'add');
        if(ids){const selected=new Set(ids);s.prefs.fragment_ids=s.source.fragments.map(f=>f.id).filter(id=>selected.has(id));s.scopeNotice=false;}
      });
      return;
    }
    if(action==='intro-page'){capturePreferences(document.getElementById('live-preferences'));s.introReviewPage=Number(b.dataset.page);redraw();return;}
    if(action==='intro-exclude'||action==='intro-undo'){
      capturePreferences(document.getElementById('live-preferences'));
      if(!s.scopeReview||s.scopeReview.source_id!==s.sourceId||s.scopeReview.revision!==s.source.revision)return;
      const all=s.source.fragments.map(f=>f.id),same=s.scopeReviewUndo?.sourceId===s.sourceId&&s.scopeReviewUndo.revision===s.source.revision;
      if(action==='intro-exclude'){
        const result=window.SOURCE_SCOPE_REVIEW_UI.exclude(all,s.prefs.fragment_ids,s.scopeReview.candidate_ids);
        s.scopeReviewUndo={sourceId:s.sourceId,revision:s.source.revision,ids:[...new Set([...(same?s.scopeReviewUndo.ids:[]),...result.removed])]};s.prefs.fragment_ids=result.selected;
      }else if(same){s.prefs.fragment_ids=window.SOURCE_SCOPE_REVIEW_UI.restore(all,s.prefs.fragment_ids,s.scopeReviewUndo.ids);s.scopeReviewUndo=null;}
      syncExcluded();redraw();return;
    }
    if(action==='edit-preferences'){act(async()=>{const p=s.plan.preferences;s.prefs={...window.SOURCE_SCOPE_REVIEW_UI.preferencesExtras(p),source_id:s.plan.source_id,expected_extraction_revision:p.extraction_revision,initial_mode:p.initial_mode,subject:p.subject,goal:p.goal,instructions:p.instructions,language:p.language,unlock_policy:p.unlock_policy,fragment_ids:[...p.fragment_ids]};s.sourceId=s.plan.source_id;s.source=await api('/sources/'+s.sourceId);s.stage=s.source.reviewed?'preferences':'source';if(s.stage==='preferences')await openPreferences();});return;}
    if(action==='source-method'){s.sourceMethod=b.dataset.method;redraw();return;}
    if(action==='open-portal-source'){act(async()=>{resetWorkspace();s.sourceId=b.dataset.source;s.source=await api('/sources/'+s.sourceId);s.stage='source';apiHost.go('live');});return;}
    if(action==='open-portal-course'){
      act(async()=>{
        const oldAttempt=s.courseId===b.dataset.course?s.attempt:null;
        s.courseId=b.dataset.course;await refreshCourse();s.resume=await api('/resume');
        const position=s.resume.find(x=>x.course_id===s.courseId)?.position;
        const chosen=s.course.content.units.find(u=>u.id===position?.unit_id&&u.unlocked)||s.course.content.units.find(u=>u.unlocked&&u.data)||s.course.content.units[0];
        s.unitId=chosen.id;s.mode=['learn','cards','practice'].includes(position?.mode)?position.mode:'learn';s.stage='course';s.feedback=null;
        const attempt=position?.session_id?await api('/sessions/'+position.session_id):oldAttempt;
        s.attempt=attempt?.scope?.unit_id===chosen.id&&attempt.status!=='cancelled'?attempt:null;
        s.attemptId=s.attempt?.id||null;apiHost.go('live');
      });return;
    }

    if(action==='open-stat-course'){act(async()=>{s.courseId=b.dataset.course;await refreshCourse();s.stage='course';s.unitId=s.course.content.units[0].id;s.attempt=s.attemptId=null;apiHost.go('live');});return;}
    if(action==='close'){apiHost.dialog.close();return;}
    if(action==='chat-menu'){menu=!menu;redraw();return;}
    if(action==='chat-resize'||action==='chat-small'||action==='chat-full'){openChat(action==='chat-resize'?(s.chatSize==='full'?'small':'full'):action==='chat-full'?'full':'small').catch(e=>{s.error=e.message;redraw();});return;}
    if(action==='mode'){s.mode=b.dataset.mode;redraw();return;}
    if(action==='unit'){s.unitId=b.dataset.unit;s.feedback=null;redraw();return;}
    if(action==='complete-questions'){act(async()=>{const info=await api('/courses/'+s.courseId+'/question-completion?unit_id='+encodeURIComponent(unit().id));apiHost.dialog.className='live-correction-dialog';apiHost.dialog.innerHTML=window.QUESTION_COMPLETION_UI.dialog({info,pending:s.pendingQuestionJob,T,E,B});apiHost.dialog.showModal();});return;}
    if(action==='resume-question-completion'){act(async()=>{const pending=s.pendingQuestionJob;if(!pending||pending.courseId!==s.courseId||pending.unitId!==unit().id||pending.revision!==s.course.revision)throw Error(T('Bài đã đổi; mở lại phần bổ sung.','The lesson changed; reopen question completion.'));const result=await api('/courses/'+s.courseId+'/question-completion',{unit_id:pending.unitId,expected_revision:pending.revision,stages:pending.stages,resume_job_id:pending.id});apiHost.dialog.close();await waitJob(result,'question_completion');});return;}
    if(action==='correct'){act(async()=>{const editor=await api('/courses/'+s.courseId+'/editor');s.editorLesson=editor.content.units.find(u=>u.id===unit().id).data;correctionDialog();});return;}
    if(action==='resume-correction'){act(async()=>{
      const previous=s.pendingCorrectionJob;if(!previous)throw Error(T('Mở lại bài để kiểm tra yêu cầu sửa đã lưu.','Reopen the lesson to recover its saved correction.'));
      const current=window.CORRECTION_STATE.recover(await api('/jobs/'+previous.id));
      if(!window.CORRECTION_STATE.matches(current,s.courseId,unit().id,s.course.revision))throw Error(T('Bài đã đổi hoặc đang kiểm tra; chưa tiếp tục yêu cầu sửa cũ.','The lesson changed or a test is active; this correction cannot continue yet.'));
      s.pendingCorrectionJob=current;
      await waitJob(await api('/courses/'+s.courseId+'/proposals',window.CORRECTION_STATE.body(current,s.courseId,unit().id,s.course.revision)),'correction');
    });return;}
    if(action==='merge-unit'){captureOutline(document.getElementById('live-outline'));const i=Number(b.dataset.index),prev=s.plan.outline.units[i-1],current=s.plan.outline.units[i];if(new Set([...prev.source_refs,...current.source_refs]).size>12){s.error=T('Hai phần này quá dài cho một bài. Giữ thành hai bài để AI đọc đủ nguồn.','These sections are too long for one lesson. Keep them separate so the source can be read in full.');redraw();return;}prev.objective=(prev.objective+' '+current.objective).slice(0,1000);prev.source_refs=[...new Set([...prev.source_refs,...current.source_refs])];s.plan.outline.units.splice(i,1);s.outlineDraft={planId:s.planId,version:s.plan.outline.version,outline:structuredClone(s.plan.outline)};redraw();return;}
    if(action==='next-question'){s.feedback=null;redraw();return;}
    if(action==='order'){const i=Number(b.dataset.index),j=i+Number(b.dataset.direction);[s.order[i],s.order[j]]=[s.order[j],s.order[i]];captureAnswerDraft();redraw();return;}
    if(action==='source'){const f=sourceFragment(b.dataset.ref);if(f){apiHost.dialog.className='live-source-dialog';if(apiHost.dialog.open)apiHost.dialog.close();apiHost.dialog.innerHTML=`<h2>${E(locationText(f.locator))}</h2><p class="live-text">${E(f.text)}</p>${f.edited_by_user?`<h3>${T('Nguyên văn bản trích gốc','Original extracted text')}</h3><p class="live-text">${E(f.original_text)}</p>`:''}${B('close',T('Đóng','Close'))}`;apiHost.dialog.showModal();}return;}
    act(async()=>{
      if(action==='report-question'){
        const form=document.getElementById('live-correction');const [target,index]=form.elements.scope.value.split(':');
        if(target!=='question')return;
        await api('/courses/'+s.courseId+'/question-reports',{expected_revision:s.course.revision,unit_id:unit().id,item_id:unit().id+':q'+index,reason:form.elements.request.value||T('Đang đối chiếu lại đáp án với nguồn.','Checking the answer key against its source.')});
        apiHost.toast(T('Đã tạm ngừng câu này trong lượt mới. Lịch sử cũ giữ nguyên.','Paused in new sessions. Existing attempts are preserved.'));
      }
      if(action==='new'){if(apiHost.dialog.open)apiHost.dialog.close();resetWorkspace();await sourceLibrary.refresh();s.courses=await api('/courses');}
      if(action==='discard-source-proposal'){await api('/source-proposals/'+s.sourceProposalId+'/discard',{});s.sourceProposal=s.sourceProposalId=null;}
      if(action==='ocr-status')await loadOCR();
      if(action==='save-source-draft'){s.source=await api('/sources/'+s.sourceId+'/save-draft',{expected_revision:s.source.revision,texts:s.source.fragments.map(f=>f.text)});s.extractionDraft=null;await loadOCR();}
      if(action==='ocr-next')await readOCR();
      if(action==='ocr-retry-empty')await readOCR(s.ocrStatus.items.filter(item=>item.state==='no_text_detected').slice(0,20).map(item=>item.key),true);
      if(action==='ocr-open'){s.ocrBatchId=b.dataset.batch;s.ocrBatch=await api('/ocr-batches/'+s.ocrBatchId);if(['queued','running'].includes(s.ocrBatch.job_status))await waitJob({job_id:s.ocrBatch.job_id},'source_ocr');await loadOCR();}
      if(action==='ocr-resume'){await waitJob(await api('/ocr-batches/'+s.ocrBatchId+'/resume',ocrAction()),'source_ocr');await loadOCR();}
      if(action==='ocr-apply'){const batchId=s.ocrBatchId;await api('/ocr-batches/'+batchId+'/apply',ocrAction());s.source=await api('/sources/'+s.sourceId);s.extractionDraft=null;const first=s.source.fragments.findIndex(f=>f.provenance?.batch_id===batchId);if(first>=0)s.sourcePage=Math.floor(first/20);await loadOCR();}
      if(action==='ocr-rebase'){s.ocrBatch=await api('/ocr-batches/'+s.ocrBatchId+'/rebase-preview',ocrAction());s.ocrBatchId=s.ocrBatch.id;await loadOCR();}
      if(action==='ocr-discard'){await api('/ocr-batches/'+s.ocrBatchId+'/discard',ocrAction());s.ocrBatch=s.ocrBatchId=null;await loadOCR();}
      if(action==='source-page')s.sourcePage=Math.max(0,Number(b.dataset.page));
      if(action==='combine-batch')await combineBatch();
      if(action==='refresh-collection'){const components=s.source.metadata.components;await useSourceCollection(await Promise.all(components.map(c=>api('/sources/'+c.source_id))));}
      if(action==='analyze-source'){const selected=s.source.fragments.filter(f=>!f.locator.unreadable_math).slice(0,16);if(!selected.length)throw Error(T('Sửa phần chưa đọc được trước.','Correct unreadable source content first.'));await waitJob(await api('/sources/'+s.sourceId+'/analyze',{expected_revision:s.source.revision,fragment_ids:selected.map(f=>f.id)}),'subject_analysis');}
      if(action==='edit-unit-scope'){const i=Number(b.dataset.index),u=s.plan.outline.units[i];apiHost.dialog.innerHTML=`<h2>${T('Nguồn cho bài','Lesson sources')} ${i+1}</h2><form id="live-unit-scope" data-index="${i}"><p>${T('Tối đa 12 đoạn cho một bài; mọi đoạn của khóa phải được phân bổ trước khi duyệt.','Up to 12 excerpts per lesson; assign every selected excerpt before approval.')}</p>${s.source.fragments.filter(f=>s.plan.preferences.fragment_ids.includes(f.id)).map(f=>`<label class="live-source-choice"><input type="checkbox" name="refs" value="${E(f.id)}" ${u.source_refs.includes(f.id)?'checked':''}><span>${E(locationText(f.locator))} · ${E(f.text.slice(0,100))}</span></label>`).join('')}<button class="primary">${T('Lưu phân bổ vào bản nháp','Save draft assignment')}</button>${B('close',T('Đóng','Close'))}</form>`;apiHost.dialog.showModal();}
      if(action==='load-office-assets'){const value=await api('/sources/'+s.sourceId+'/assets');s.officeAssets={sourceId:s.sourceId,assets:value.assets};}
      if(action==='retry-source'){s.source=await api('/sources/'+s.sourceId+'/retry-extraction',{expected_revision:s.source.revision});s.extractionDraft=null;s.stage='source';}
      if(action==='open-source'){const batch=s.uploadBatch;resetWorkspace();s.uploadBatch=batch;s.sourceId=b.dataset.source;s.source=await api('/sources/'+s.sourceId);s.stage='source';}
      if(action==='open-course'){s.courseId=b.dataset.course;await refreshCourse();s.stage='course';s.unitId=s.course.content.units[0].id;s.attemptId=null;s.attempt=null;}
      if(action==='generate')await waitJob(await api('/courses/'+s.courseId+'/generate',{unit_id:unit().id,expected_revision:s.course.revision,...(s.pendingLessonJob?.courseId===s.courseId&&s.pendingLessonJob?.unitId===unit().id?{resume_job_id:s.pendingLessonJob.id}:{})}),'lesson');
      if(action==='practice'){s.mode='practice';s.feedback=null;}
      if(action==='start-practice'){s.attempt=await api('/courses/'+s.courseId+'/sessions',{unit_id:unit().id,expected_revision:s.course.revision});s.attempt.scope={unit_id:unit().id};s.attemptId=s.attempt.id;s.feedback=null;}
      if(action==='finish'){s.attempt.result=await api('/sessions/'+s.attemptId+'/complete',{});await refreshCourse();}
      if(action==='tree'){s.mode='learn';await refreshCourse();}
      if(action==='apply'){await api('/proposals/'+s.proposal.id+'/apply',{expected_revision:s.proposal.base_revision});await refreshCourse();if(s.attemptId)s.attempt=await api('/sessions/'+s.attemptId);s.stage='course';s.proposal=null;s.proposalId=null;}
      if(action==='discard'){await api('/proposals/'+s.proposal.id+'/discard',{});s.stage='course';s.proposal=null;s.proposalId=null;}
      if(action==='ask'){s.chatDraft=T('Giải thích ý: ','Explain: ')+b.dataset.question;await openChat('small');}
      if(action==='history'){const h=await api('/courses/'+s.courseId+'/history');apiHost.dialog.className='live-history-dialog';apiHost.dialog.innerHTML=`<h2>${T('Lịch sử theo phiên bản','History by version')}</h2>${h.map(x=>`<p>${E(new Date(x.created_at).toLocaleString())} · ${T('Bản','Version')} ${x.revision} · ${x.result?`${x.result.score}/${x.result.fixed_total}`:T('Đang làm','In progress')}</p>`).join('')||`<p>${T('Chưa có lượt luyện.','No practice sessions yet.')}</p>`}${B('close',T('Đóng','Close'))}`;apiHost.dialog.showModal();}
    });
  });
  document.addEventListener('submit',event=>{
    const form=event.target;if(!form.id.startsWith('live-'))return;event.preventDefault();
    if(form.id==='live-source-library-search'){sourceLibrary.search();return;}
    if(form.id==='live-chat-form'){
      if(s.busy||s.job)return;const message=s.chatDraft.trim();if(!message)return;
      const submit=form.querySelector('button');submit.disabled=true;
      act(async()=>{try{const job=await api('/courses/'+s.courseId+'/chat',{unit_id:unit().id,message});s.chatDraft='';s.chat=await api('/courses/'+s.courseId+'/chat');await waitJob(job,'chat');}catch(error){s.chatDraft=s.chatDraft||message;const errorBox=document.getElementById('live-chat-error');if(errorBox)errorBox.textContent=error.message;throw error;}finally{submit.disabled=false;renderChat();}});return;
    }
    const data=new FormData(form);
    if(form.id==='live-preferences')capturePreferences(form);
    const preferencesSnapshot=form.id==='live-preferences'?structuredClone(s.prefs):null;
    // Snapshot the fields before the busy render replaces their DOM nodes.
    act(async()=>{
      if(form.id==='live-ocr-select'){const items=data.getAll('items');if(!items.length||items.length>20)throw Error(T('Chọn từ 1 đến 20 phần.','Choose 1–20 items.'));await readOCR(items,true);}
      if(form.id==='live-unit-scope'){const refs=data.getAll('refs');if(!refs.length||refs.length>12)throw Error(T('Chọn từ 1 đến 12 đoạn cho bài.','Choose 1–12 excerpts for this lesson.'));s.plan.outline.units[Number(form.dataset.index)].source_refs=refs;s.outlineDraft={planId:s.planId,version:s.plan.outline.version,outline:structuredClone(s.plan.outline)};apiHost.dialog.close();}
      if(form.id==='live-vision-form'){await waitJob(await api('/sources/'+s.sourceId+'/vision-review',{expected_revision:s.source.revision,...(data.get('asset_id')?{asset_id:data.get('asset_id')}:{page:Number(data.get('page'))})}),'source_vision');}
      if(form.id==='live-asset-manual'){s.sourceProposal=await api('/sources/'+s.sourceId+'/assets/'+data.get('asset_id')+'/transcription-preview',{expected_revision:s.source.revision,text:data.get('text')});s.sourceProposalId=s.sourceProposal.id;s.sourceProposalDraft=null;}
      if(form.id==='live-source-proposal-edit'){s.sourceProposal=await api('/source-proposals/'+s.sourceProposalId+'/edit-preview',{expected_revision:s.sourceProposal.base_revision,text:data.get('text')});s.sourceProposalId=s.sourceProposal.id;s.sourceProposalDraft=null;}
      if(form.id==='live-vision-apply'){s.source=await api('/source-proposals/'+s.sourceProposalId+'/apply',{expected_revision:s.sourceProposal.base_revision});s.sourceProposal=s.sourceProposalId=s.extractionDraft=null;s.stage='source';}
      if(form.id==='live-url'){const source=await api('/sources/url',{url:data.get('url')});resetWorkspace();s.source=source;s.sourceId=source.id;s.stage='source';}
      if(form.id==='live-transcription'){s.source=await api('/sources/'+s.sourceId+'/transcription',{expected_revision:s.source.revision,text:data.get('text')});s.extractionDraft=null;s.stage='source';}
      if(form.id==='live-text'){const source=await api('/sources/text',{name:data.get('name'),text:data.get('text')});resetWorkspace();s.source=source;s.sourceId=source.id;s.stage='source';}
      if(form.id==='live-source-review'){s.source=await api('/sources/'+s.sourceId+'/review',{expected_revision:s.source.revision,texts:s.source.fragments.map(x=>x.text)});s.stage='preferences';s.extractionDraft=null;await openPreferences();}
      if(form.id==='live-preferences'){s.prefs=preferencesSnapshot;const strategy=await api('/plans/strategy',s.prefs);if(strategy.method==='source_sections_not_ai'){s.plan=await api('/plans/from-source-sections',s.prefs);s.planId=s.plan.id;s.stage='outline';await loadScopeReview();}else await waitJob(await api('/plans',s.prefs),'plan');}
      if(form.id==='live-outline'){
        const outline={title:data.get('title'),units:s.plan.outline.units.map((u,i)=>({...u,title:data.get('unit-title-'+i),objective:data.get('unit-objective-'+i),source_refs:data.getAll('unit-refs-'+i)}))};
        s.plan=await api('/plans/'+s.planId,{expected_version:s.plan.outline.version,outline},'PUT');
        const approved=await api('/plans/'+s.planId+'/approve',{expected_revision:s.plan.outline.version});s.courseId=approved.course_id;s.outlineDraft=null;await refreshCourse();s.unitId=s.course.content.units[0].id;s.stage='course';
        await waitJob(await api('/courses/'+s.courseId+'/generate',{unit_id:s.unitId,expected_revision:s.course.revision}),'lesson');
      }
      if(form.id==='live-answer'){
        const q=s.attempt.questions.find(x=>x.id===form.dataset.question);
        await saveCurrentAnswerDraft({sessionId:s.attemptId,itemId:q.id});
        const answer=answerFromForm(form,q);
        s.feedback=await api('/sessions/'+s.attemptId+'/answers',{item_id:q.id,answer});s.lastQuestionId=q.id;s.lastPrompt=q.prompt;s.lastOptions=q.options;s.lastLeft=q.left;s.lastKind=q.kind;s.attempt=await api('/sessions/'+s.attemptId);
      }
      if(form.id==='live-question-completion'){
        const stages=data.getAll('stages');if(!stages.length)throw Error(T('Chọn ít nhất một câu có thể tạo.','Select at least one available question.'));
        const result=await api('/courses/'+form.dataset.course+'/question-completion',{unit_id:form.dataset.unit,expected_revision:Number(form.dataset.revision),stages});apiHost.dialog.close();await waitJob(result,'question_completion');
      }
      if(form.id==='live-correction'){
        const [target,indexText]=data.get('scope').split(':');const index=Number(indexText),d=s.editorLesson;
        const payload={unit_id:unit().id,expected_revision:s.course.revision,target,index,request:data.get('request')};
        if(data.get('method')==='manual'){
          const replacement=structuredClone(target==='lesson'?d:d[target==='card'?'cards':'questions'][index]);
          if(target==='lesson')replacement.sections.forEach((x,i)=>x.text=data.get('section-'+i));
          if(target==='card'){replacement.front=data.get('front');replacement.back=data.get('back');}
          if(target==='question'){replacement.prompt=data.get('prompt');replacement.explanation=data.get('explanation');if(typeof replacement.answer==='string')replacement.answer=data.get('answer');else{replacement.answer=replacement.answer.map((_,i)=>Number(data.get('key-'+i)));replacement.options=replacement.options.map((_,i)=>data.get('option-'+i));}}
          payload.replacement=replacement;
        }
        const result=await api('/courses/'+s.courseId+'/proposals',payload);apiHost.dialog.close();
        if(result.job_id)await waitJob(result,'correction');else{s.proposalId=result.proposal_id;s.proposal=await api('/proposals/'+s.proposalId);s.stage='proposal';}
      }
    });
  });
  return {init,render,renderRemote,isServerRoute,get available(){return available;},newSource(){resetWorkspace();save();}};
})();
