'use strict';
(() => {
  const D = window.DEMO_DATA;
  const P = window.PRODUCT_VIEWS;
  const V = window.PRACTICE_VIEWS;
  const Q = () => V.questions(state,D);
  const KEY = 'study-ui-prototype-v1';
  const defaults = {mode:'learn',setupStep:1,subject:'Mạng máy tính',goal:'Hiểu từ đầu',notes:'',scope:'ip',language:'vi',approved:false,completed:false,tab:'reading',qIndex:0,answers:{},checked:{},chat:[],chatDraft:'',uiLanguage:'vi',hint:0};
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (_) { /* Mẫu vẫn dùng được khi storage không sẵn. */ }
  let state = {...defaults,...stored};
  if (!state.answers || typeof state.answers !== 'object') state.answers = {};
  if (!state.checked || typeof state.checked !== 'object') state.checked = {};
  if (!Array.isArray(state.chat)) state.chat = [];
  if (typeof state.chatDraft !== 'string') state.chatDraft = '';
  if(!['vi','en'].includes(state.uiLanguage))state.uiLanguage='vi';
  V.init(state,D);
  state.setupStep=Math.max(1,Math.min(4,Number(state.setupStep)||1));
  P.init(state);
  let route = P.routes.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home';
  let panel = 'chat', panelOpen = false, sourceFocus = '', chatContext = 'IP và subnet mask';
  let assistantMenuOpen=false;
  let toastTimer;
  const app = document.getElementById('app');
  const dialog = document.getElementById('dialog');
  const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const paths = {
    notebook:'M5 3h14v18H5z M3 7h4 M3 12h4 M3 17h4 M10 8h5 M10 12h5',
    globe:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18 M12 3c-5 5-5 13 0 18',
    home:'M3 10l9-7 9 7 M5 9v12h14V9 M9 21v-8h6v8',
    book:'M4 4h5a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H4z M20 4h-5a3 3 0 0 0-3 3v14a3 3 0 0 1 3-3h5z',
    cards:'M6 6h13v15H6z M3 17V3h13 M10 10h5 M10 14h4',
    target:'M21 12a9 9 0 1 1-9-9 M17 12a5 5 0 1 1-5-5 M12 12l9-9 M17 3h4v4',
    arrow:'M5 12h14 M13 6l6 6-6 6', back:'M19 12H5 M11 6l-6 6 6 6',
    plus:'M12 5v14 M5 12h14', up:'M6 14l6-6 6 6', down:'M6 10l6 6 6-6', check:'M5 12l4 4L19 6', close:'M6 6l12 12 M18 6L6 18',
    search:'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
    file:'M14 2H5v20h14V7z M14 2v5h5 M8 12h8 M8 16h6',
    network:'M12 3v5 M5 16v-4h14v4 M12 12v4 M9 3h6v5H9z M2 16h6v5H2z M9 16h6v5H9z M16 16h6v5h-6z',
    chat:'M21 11a9 9 0 0 1-9 9H4l-2 2V11a9 9 0 1 1 19 0z M7 10h10 M7 14h6',
    spark:'M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
    lock:'M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4',
    map:'M12 4v5 M12 9H4v5 M12 9h8v5 M9 2h6v4H9z M1 14h6v6H1z M17 14h6v6h-6z',
    chevron:'M9 5l7 7-7 7', send:'M22 2L9 15 M22 2l-5 20-8-7-7-5z',
    flag:'M5 21V3 M5 3h14l-4 4 4 4H5', trophy:'M7 3h10v6a5 5 0 0 1-10 0z M7 5H3v3a4 4 0 0 0 4 4 M17 5h4v3a4 4 0 0 1-4 4 M12 14v6 M8 21h8',
    clock:'M12 8v4l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0', info:'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0'
  };
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name]||paths.book}"/></svg>`;
  const localize = root => {if(window.UI_I18N)window.UI_I18N.translate(root,state.uiLanguage);};
  const save = () => { try {localStorage.setItem(KEY,JSON.stringify(state));} catch (_) {toast('Trình duyệt chưa lưu được bản mẫu. Giữ tab này để tiếp tục.');} };
  function toast(message){const t=document.getElementById('toast');t.textContent=message;localize(t);t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.hidden=true,5000);}
  function go(next){if(!P.routes.includes(next))return;if(next==='setup'){state.setupStep=1;save();}route=next;location.hash=next;panelOpen=false;assistantMenuOpen=false;render({focus:'#main'});window.scrollTo(0,0);}
  function setPreference(field,value){
    if(state[field]===value)return;
    state[field]=value;
    state.approved=false;
    save();
  }
  function updatePlanPreview(){
    const current=app.querySelector('.plan-card');
    if(!current)return;
    const holder=document.createElement('div');
    holder.innerHTML=setup();
    const fresh=holder.querySelector('.plan-card');
    // Keep the existing approval button: a text field blur must not remove a pending click.
    for(const selector of ['h2','p:not(.plan-disclaimer)','.plan-list','.plan-summary']){
      current.querySelector(selector).innerHTML=fresh.querySelector(selector).innerHTML;
    }
    localize(current);
  }
  function modal(title,content,action='',label=''){
    dialog.className='';
    dialog.innerHTML=`<h2>${e(title)}</h2><p>${e(content)}</p><div class="dialog-actions">${action?`<button class="primary" data-action="${action}">${e(label)}</button>`:''}<button class="secondary" data-action="close-dialog">Đóng</button></div>`;
    localize(dialog);dialog.showModal();
  }
  function viewContext(){return {state,D,e,icon,route,panel,panelOpen,assistantMenuOpen,sourceFocus,chatContext,sourceLink,practice,reading,mindmap,assistant,setup,questions:Q(),cards:P.deck(state,D),isCorrect:V.isCorrect};}
  function top(){return P.top(viewContext());}
  function setup(){return window.REFERENCE_VIEWS.setup(viewContext());}
  const sourceLink = refs => `<button class="text-button" data-action="source" data-source="${refs[0]}">${icon('file')} Đối chiếu nguồn minh họa</button>`;
  function reading(){return window.STUDY_VIEWS.reading(viewContext());}
  function mindmap(){return window.STUDY_VIEWS.mindmap(viewContext());}
  function practice(){return V.render(viewContext());}
  function assistant(){return window.STUDY_VIEWS.assistant(viewContext());}
  function lesson(){return window.STUDY_VIEWS.lesson(viewContext());}
  function importModal(kind=''){
    const methods=[['file','Tải tài liệu','PDF · Word · PPT · ảnh','source-file'],['text','Dán văn bản','Ghi chú, trích đoạn','source-text'],['link','Link bài viết','Nguồn công khai','source-link']];
    const selected=methods.find(x=>x[0]===kind);
    dialog.className='input-modal';
    dialog.innerHTML=`<h2>${selected?selected[1]:'Bắt đầu từ tài liệu'}</h2><p>Chọn nguồn bạn muốn học, rồi chọn cách học phù hợp.</p><div class="import-methods" role="group" aria-label="Chọn nguồn tài liệu">${methods.map(([id,title,note,art])=>`<button class="import-method ${kind===id?'selected':''}" data-action="import-select" data-kind="${id}" aria-pressed="${kind===id}"><img src="assets/scenes/${art}.svg" alt="" width="90" height="55"><strong>${title}</strong><small>${note}</small></button>`).join('')}</div><div class="sample-note">Bạn đang xem form mẫu. Các bước tiếp theo dùng ghi chú IP/subnet minh họa; chưa nhận hoặc đọc tài liệu thật.</div><div class="dialog-actions"><button class="secondary" data-action="close-dialog">Để sau</button><button class="primary" data-action="use-sample">Dùng tài liệu minh họa ${icon('arrow')}</button></div>`;
    localize(dialog);if(!dialog.open)dialog.showModal();
  }
  function scopeModal(){
    dialog.className='scope-modal';
    const t=(vi,en)=>P.L(state,vi,en);
    if(window.LIVE_STUDY?.available){
      dialog.innerHTML=`<h2>${t('Phạm vi bản local','Local version scope')}</h2><p>${t('Tài liệu của bạn là luồng đầu tiên đã nối backend và Ollama trên máy này.','Your documents is the first flow connected to the backend and Ollama on this computer.')}</p><ul><li>${t('Đọc TXT, Word, PDF có chữ và PowerPoint; đối chiếu/sửa bản trích trước khi tạo','Read TXT, Word, text PDFs and PowerPoint; review/correct extraction before generation')}</li><li>${t('Duyệt lộ trình, tạo từng bài, luyện và lưu lịch sử theo phiên bản','Approve outlines, generate individual lessons, practice and keep versioned history')}</li><li>${t('Sửa tay hoặc nhờ AI đề xuất → xem trước → áp dụng/giữ cũ; chat nhỏ/toàn màn hình','Manual or AI correction → preview → apply/keep current; compact/full-screen chat')}</li></ul><p>${t('Đã có OCR ảnh/scan, link công khai và API chia sẻ; công thức vẫn cần đối chiếu. Dashboard, Nhiệm vụ và Coin đã dùng dữ liệu server, mức thưởng còn là đề xuất. Trang cộng đồng và phòng còn là mẫu; phòng thật, đổi nguồn AI và benchmark cuối chưa hoàn tất.','Image/scan OCR, public links, and sharing APIs are implemented; formulas still need review. Dashboard, Missions, and Coin use server data with proposed rates. Community and room pages are still prototypes. Live rooms, provider switching, and final benchmarks are incomplete.')}</p><div class="dialog-actions"><button class="primary" data-action="close-dialog">${t('Đóng','Close')}</button></div>`;
      dialog.showModal();return;
    }
    dialog.innerHTML=`<h2>${t('Phạm vi bản mẫu','Prototype scope')}</h2><p>${t('Giao diện local để duyệt bố cục; chưa phải MVP tích hợp.','Local interface for design review; not an integrated MVP.')}</p><section><h3>${t('Tương tác trên trình duyệt','Browser interactions')}</h3><ul><li>${t('Home cá nhân/cộng đồng, Dashboard ba khối và menu mở từng trang','Personal/community Home, three-widget Dashboard and navigable pages')}</li><li>${t('Duyệt trích đoạn → Học/mindmap/năm dạng câu; thẻ cá nhân','Review excerpts → Learn/mindmap/five question types; personal cards')}</li><li>${t('Sổ tay lưu trên máy, lịch sử lượt luyện; chat nhỏ/toàn màn hình, VI/EN','Local notebook and practice history; small/full chat, VI/EN')}</li></ul></section><section><h3>${t('Dữ liệu hoặc bản xem trước','Illustrations and previews')}</h3><ul><li>${t('Timeline, streak tuần và khóa cộng đồng dùng dữ liệu minh họa','Timeline, weekly streak and community courses use illustrative data')}</li><li>${t('Phòng đố vui, Coin, chia sẻ, sửa/phiên bản và tạo từng phần chưa nối backend','Quiz rooms, Coin, sharing, revisions and incremental generation have no backend')}</li></ul></section><section><h3>${t('Chưa tích hợp','Not integrated')}</h3><ul><li>${t('Đọc/OCR nguồn thật, AI, tài khoản/quyền và đồng bộ nhiều người','Real source parsing/OCR, AI, accounts/access and multiplayer synchronization')}</li><li>${t('AI chấm tự luận, lượt kiểm tra riêng và bài 02 chi tiết','AI short-answer grading, separate test attempts and detailed lesson 02')}</li></ul></section><div class="dialog-actions"><button class="primary" data-action="close-dialog">${t('Đóng','Close')}</button></div>`;
    localize(dialog);dialog.showModal();
  }
  function captureFocus(){
    const active=document.activeElement;
    if(!active||!app.contains(active))return null;
    let selector='';
    if(active.id)selector='#'+CSS.escape(active.id);
    else if(active.dataset.field)selector='[data-field="'+CSS.escape(active.dataset.field)+'"]';
    else if(active.dataset.action||active.dataset.live||active.dataset.fc)selector=Object.entries(active.dataset).map(([key,value])=>
      '[data-'+key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())+'="'+CSS.escape(value)+'"]'
    ).join('');
    if(!selector)return null;
    return {selector,start:active.selectionStart,end:active.selectionEnd};
  }
  function render(options={}){
    const previous=captureFocus();
    const motion=window.STUDY_MOTION;
    const motionFrame=motion?.beforeRender(app,viewContext());
    app.className=route==='lesson'&&state.approved?'focus-study':'workspace';
    const body=route==='live'?window.LIVE_STUDY.render(viewContext()):window.LIVE_STUDY?.renderRemote(viewContext())||P.renderRoute(viewContext())||(route==='setup'?setup():lesson());
    app.innerHTML=top()+body+(route==='live'?'':assistant()+P.launcher(viewContext()));
    localize(app);
    app.querySelectorAll('.user-message .bubble-label').forEach(el=>{el.textContent=state.uiLanguage==='en'?'You':'Bạn';});
    document.documentElement.lang=state.uiLanguage;
    document.querySelector('.skip-link').textContent=state.uiLanguage==='en'?'Skip to main content':'Đến nội dung chính';
    document.title=state.uiLanguage==='en'?'Folio · Learn from your notes':'Folio · Học từ tài liệu';
    const bar=document.querySelector('.prototype-bar');
    bar.innerHTML='<span class="status-dot"></span> '+P.L(state,'Bản xem giao diện · nội dung mẫu','Design preview · sample content');
    if(location.port==='8770'&&!window.LIVE_STUDY.available)bar.textContent=P.L(state,'Bản trên máy · đang kiểm tra kết nối','Local app · checking connection');
    if(window.LIVE_STUDY.available)bar.textContent=window.LIVE_STUDY.isServerRoute(route)||route==='live'?P.L(state,'Bản dùng thử trên máy · dữ liệu của bạn được lưu tại đây','Local preview · your saved study space'):P.L(state,'Đang xem nội dung mẫu','Viewing sample content');
    localize(bar);
    const panelModal=panelOpen&&(state.assistantMode==='full'||matchMedia('(max-width:760px)').matches);
    app.querySelectorAll('.ref-sidebar,#main,.product-launcher').forEach(el=>{el.inert=panelModal;});
    const assist=app.querySelector('.assist');
    if(assist&&panelModal){assist.setAttribute('role','dialog');assist.setAttribute('aria-modal','true');}
    document.body.style.overflow=panelModal?'hidden':'';
    const target=app.querySelector(options.focus||(previous&&previous.selector)||'body');
    if(target&&!target.disabled){
      if(!target.matches('button,input,select,textarea,a,[tabindex]'))target.tabIndex=-1;
      target.focus({preventScroll:true});
      if(previous&&target.matches('input,textarea')&&typeof previous.start==='number'){
        try{target.setSelectionRange(previous.start,previous.end);}catch(_){/* Numeric inputs do not expose a selection. */}
      }
    }
    if((options.focus||previous)&&(!target||document.activeElement!==target)){
      const main=document.getElementById('main');
      if(main){main.tabIndex=-1;main.focus({preventScroll:true});}
    }
    if(motion)motion.afterRender(app,viewContext(),motionFrame);
  }
  function showSource(id){sourceFocus=id;panel='source';panelOpen=true;assistantMenuOpen=false;render({focus:'#assist-tab-source'});const target=document.getElementById(id);if(target)target.scrollIntoView({block:'nearest'});}
  function addChat(user,reply,source){state.chat.push({role:'user',text:user},{role:'assistant',text:reply,source});state.chat=state.chat.slice(-12);panel='chat';panelOpen=true;assistantMenuOpen=false;save();render({focus:'#chat-input'});const c=app.querySelector('.assist-content');if(c)c.scrollTop=c.scrollHeight;}
  function hint(){
    const q=Q()[state.qIndex];chatContext=`Câu ${state.qIndex+1} · ${V.typeLabel(q,state)}`;
    const hints={
      mcq:['/26 để lại bao nhiêu bit host? Hãy lấy 32 − 26.','Tìm block rộng 64 chứa số 70.'],
      cloze:['Tính tổng địa chỉ từ 6 bit host trước.','Network và broadcast được dành riêng trong ví dụ này.'],
      matching:['Tìm hai biên của block chứa 70.','Network ở đầu block; broadcast ở cuối. Host đầu tiên ở ngay sau network.'],
      ordering:['Nguồn §5 bắt đầu với việc đọc prefix.','Cần biết số bit host để tìm block, rồi xác định hai biên trước khi đếm host.'],
      short_answer:['Mask/prefix cho biết điều gì về network và host?','Hãy nghĩ đến cùng một IP được đi kèm hai mask khác nhau.']
    }[q.type];
    addChat(P.L(state,'Cho mình một gợi ý nhỏ.','Give me a small hint.'),hints[Math.min(state.hint,1)],q.sourceRefs[0]);state.hint=Math.min(state.hint+1,2);save();
  }
  document.addEventListener('click',ev=>{
    const b=ev.target.closest('[data-action]');if(!b)return;
    const action=b.dataset.action;
    if(b.closest('summary'))ev.preventDefault();
    if(action==='studio-art'){
      if(!b.classList.contains('is-playing')){b.classList.add('is-playing');setTimeout(()=>b.classList.remove('is-playing'),1250);}
      return;
    }
    if(P.handle(action,b,viewContext(),{go,render,save,toast,modal,dialog}))return;
    if(action==='assistant-menu'){if(panelOpen){panelOpen=false;assistantMenuOpen=false;}else assistantMenuOpen=!assistantMenuOpen;render({focus:assistantMenuOpen?'[data-action="assistant-open"]':'#chat-launcher'});return;}
    if(action==='assistant-open'){state.assistantMode=b.dataset.size;assistantMenuOpen=false;panelOpen=true;panel='chat';save();render({focus:'#chat-input'});return;}
    if(action==='assistant-resize'){state.assistantMode=state.assistantMode==='full'?'small':'full';save();render({focus:panel==='chat'?'#chat-input':'#assist-tab-source'});return;}
    if(action==='ui-language'){state.uiLanguage=b.dataset.lang;save();render({focus:'#ui-lang-'+state.uiLanguage});return;}
    if(action==='close-dialog'){dialog.close();return;}
    if(action==='home')go('home');
    else if(action==='library')go('library');
    else if(action==='setup')go('setup');
    else if(action==='continue'){state.mode=b.dataset.mode||'learn';state.courseId='network';save();go(state.approved?'lesson':'setup');}
    else if(action==='import'){if(window.LIVE_STUDY?.available){window.LIVE_STUDY.newSource();go('live');}else importModal(b.dataset.kind||'');}
    else if(action==='import-select')importModal(b.dataset.kind);
    else if(action==='use-sample'){dialog.close();go('setup');}
    else if(action==='fixture')modal('Nguồn của bài mẫu',D.document.sourceNotice+' Ghi chú gồm 5 mục, có vị trí trích đoạn rõ. Bạn có thể mở file từ panel Nguồn trong bài Học.','open-fixture','Mở ghi chú minh họa');
    else if(action==='open-fixture'){dialog.close();window.open(D.document.sourcePath,'_blank','noopener');}
    else if(action==='course'){setPreference('mode',b.dataset.mode);go('setup');}
    else if(action==='mode'){setPreference('mode',b.dataset.mode);render();}
    else if(action==='setup-next'){if(state.setupStep===3&&!state.subject.trim()){toast('Hãy xác nhận hoặc sửa môn trước khi duyệt.');document.getElementById('subject')?.focus();return;}if(state.setupStep===2)state.extractionReviewed=true;state.setupStep=Math.min(4,state.setupStep+1);save();render({focus:'#main'});window.scrollTo(0,0);}
    else if(action==='setup-prev'){state.setupStep=Math.max(1,state.setupStep-1);save();render({focus:'#main'});window.scrollTo(0,0);}
    else if(action==='goal'){setPreference('goal',b.dataset.goal);render();}
    else if(action==='approve'){
      if(!state.subject.trim()){toast('Hãy xác nhận hoặc sửa môn trước khi duyệt.');return;}
      if(!state.extractionReviewed){state.setupStep=2;save();render({focus:'#main'});toast(P.L(state,'Đối chiếu trích đoạn mẫu trước khi duyệt.','Review the sample excerpts before approval.'));return;}
      state.approved=true;state.tab='reading';save();
      state.courseId='network';save();go({learn:'lesson',flashcard:'flashcards',practice:'review'}[state.mode]);
    }
    else if(action==='open-learn'){dialog.close();go('lesson');}
    else if(action==='tab'){state.tab=b.dataset.tab==='practice'&&Q().every(q=>state.checked[q.id])?'result':b.dataset.tab;chatContext=state.tab==='practice'?`Câu ${state.qIndex+1} · luyện bài IP/mask`:'IP và subnet mask';save();render();}
    else if(action==='panel-toggle'){panelOpen=!panelOpen;if(panelOpen){panel='chat';render({focus:'#chat-input'});}else render({focus:'#chat-launcher'});}
    else if(action==='panel'){panel=b.dataset.panel;panelOpen=true;assistantMenuOpen=false;render({focus:panel==='chat'?'#chat-input':'#assist-tab-source'});}
    else if(action==='panel-close'){panelOpen=false;assistantMenuOpen=false;render({focus:'#chat-launcher'});}
    else if(action==='source')showSource(b.dataset.source);
    else if(action==='map-help'){const x=D.lesson.mindmap.find(x=>x.id===b.dataset.map);if(x){chatContext=x.label;addChat('Giải thích ý: '+x.label,x.description,x.sourceRefs[0]);}}
    else if(action==='answer'){const q=Q()[state.qIndex];if(!state.checked[q.id]){state.answers[q.id]=b.dataset.answer;save();render();}}
    else if(action==='order-move'){
      const q=Q()[state.qIndex];if(q.type!=='ordering'||state.checked[q.id])return;
      const order=[...V.answerFor(q,state)],i=order.indexOf(b.dataset.item),j=i+(b.dataset.direction==='up'?-1:1);
      if(i<0||j<0||j>=order.length)return;
      [order[i],order[j]]=[order[j],order[i]];state.answers[q.id]=order;save();
      const direction=j===0?'down':j===order.length-1?'up':b.dataset.direction;
      render({focus:`[data-action="order-move"][data-item="${b.dataset.item}"][data-direction="${direction}"]`});
    }
    else if(action==='self-review'){const q=Q()[state.qIndex];if(q.type==='short_answer'&&state.checked[q.id]){state.selfReview[q.id]=b.dataset.review;save();render();}}
    else if(action==='check'){const q=Q()[state.qIndex],a=V.answerFor(q,state);if(V.canCheck(q,a)&&!state.checked[q.id]){state.answers[q.id]=a;state.checked[q.id]=true;save();render({focus:'[data-action="next"]'});}}
    else if(action==='next'){
      if(!state.checked[Q()[state.qIndex].id]||state.tab==='result')return;
      if(state.qIndex<Q().length-1){state.qIndex++;state.hint=0;chatContext=`Câu ${state.qIndex+1} · ${V.typeLabel(Q()[state.qIndex],state)}`;}
      else{state.completed=true;state.tab='result';if(!state.attemptHistory.some(x=>x.id===state.practiceAttemptId))state.attemptHistory.push(V.attempt(state,D));state.attemptHistory=state.attemptHistory.slice(-30);}
      save();render({focus:state.tab==='result'?'#lesson-content':'.question-card'});
    }
    else if(action==='retry'){state.qIndex=0;state.answers={};state.checked={};state.selfReview={};state.practiceAttemptId='attempt-'+Date.now();state.hint=0;state.tab='practice';save();render({focus:'.answer'});}
    else if(action==='unit'){
      if(b.dataset.unit==='0'){state.tab='reading';save();render();}
      else if(b.dataset.unit==='1'&&state.completed)modal('Bước tiếp đã mở','Network và broadcast: giải thích hai địa chỉ biên bằng các bit host. Trong mẫu này đây mới là phác thảo, chưa có bài chi tiết. Lượt luyện được hoàn thành nên bước này đã mở, bất kể số câu đúng.');
      else toast(b.dataset.unit==='1'?'Hoàn thành lượt luyện để mở phác thảo bài tiếp. Không cần điểm tối thiểu.':'Phần này chưa được dựng trong mẫu ba màn.');
    }
    else if(action==='hint'){if(route==='flashcards'){const card=P.deck(state,D)[state.cardIndex];if(card)addChat(P.L(state,'Gợi ý cho thẻ này.','A hint for this card.'),P.L(state,'Đối chiếu mặt sau và nguồn của thẻ để tự kiểm tra. Bản mẫu chưa có AI tạo gợi ý mới.','Compare the back and source of this card. AI-generated hints are not connected.'),card.sourceRefs[0]);}else hint();}
    else if(action==='chat-mask')addChat('Vì sao IP cần subnet mask?',D.sourceLines[0].text,'src-ip-and-mask');
    else if(action==='chat-host')addChat('Vì sao trừ 2?',D.sourceLines[5].text,'src-usable-hosts');
    else if(action==='report')modal('Đối chiếu câu hỏi','Bản mẫu chưa gửi báo lỗi cho người tạo. Hãy xem đoạn nguồn và lời giải để đánh giá câu này; mẫu không mặc định đáp án lưu luôn đúng.','report-source','Xem nguồn câu này');
    else if(action==='report-source'){dialog.close();showSource(Q()[state.qIndex].sourceRefs[0]);}
    else if(action==='about')scopeModal();
    else if(action==='reset-prompt')modal('Đặt lại bản mẫu','Chỉ xóa tiến trình và lựa chọn trong mẫu giao diện này trên trình duyệt. File nguồn của dự án được giữ nguyên.','reset','Đặt lại bản mẫu');
    else if(action==='reset'){dialog.close();state={...defaults,answers:{},checked:{},chat:[]};V.init(state,D);P.init(state);save();go('library');toast('Đã đặt lại dữ liệu bản mẫu.');}
  });
  document.addEventListener('input',ev=>{
    if(P.onInput(ev.target,viewContext(),{save,render}))return;
    if(ev.target.id==='search'){const list=document.getElementById('course-grid');list.innerHTML=libraryCards(ev.target.value);localize(list);}
    if(ev.target.id==='cloze'||ev.target.id==='short-answer'){const q=Q()[state.qIndex];if(state.checked[q.id])return;state.answers[q.id]=ev.target.value;save();const b=app.querySelector('[data-action="check"]');if(b)b.disabled=!V.canCheck(q,ev.target.value);}
    if(ev.target.dataset.match){const q=Q()[state.qIndex];if(q.type!=='matching'||state.checked[q.id])return;state.answers[q.id]={...state.answers[q.id],[ev.target.dataset.match]:ev.target.value};save();render({focus:'#'+ev.target.id});}
    if(ev.target.id==='chat-input'){state.chatDraft=ev.target.value;save();}
    if(ev.target.dataset.field){setPreference(ev.target.dataset.field,ev.target.value);updatePlanPreview();}
  });
  document.addEventListener('change',ev=>{if(P.onInput(ev.target,viewContext(),{save,render}))return;if(ev.target.dataset.field){setPreference(ev.target.dataset.field,ev.target.value);updatePlanPreview();}});
  document.addEventListener('submit',ev=>{
    if(ev.target.id==='card-edit-form'){ev.preventDefault();P.saveCard(viewContext(),{render,save,toast,dialog});return;}
    if(ev.target.id!=='chat-form')return;ev.preventDefault();const input=document.getElementById('chat-input').value.trim();if(!input)return;
    state.chatDraft='';
    const inContext=['lesson','flashcards','review'].includes(route)||(route==='course'&&state.courseId==='network');
    if(!inContext){addChat(input,P.L(state,'Bản mẫu chưa nối AI. Mở một khóa học để chọn ngữ cảnh; ghi chú IP/subnet có các giải thích mẫu để thử.','AI is not connected in this prototype. Open a course to select the context; the sample IP/subnet notes have explanations to try.'));return;}
    const low=input.toLowerCase();
    if(low.includes('mask'))addChat(input,D.sourceLines[0].text,'src-ip-and-mask');
    else if(low.includes('trừ 2')||low.includes('subtract 2')||low.includes('62'))addChat(input,D.sourceLines[5].text,'src-usable-hosts');
    else if(low.includes('/26')||low.includes('bit'))addChat(input,D.sourceLines[1].text,'src-prefix-26');
    else addChat(input,'Bản mẫu chưa có AI để trả lời câu mới này. Bạn có thể thử “Vì sao IP cần mask?”, “Vì sao trừ 2?” hoặc gợi ý từng bước. Câu bạn vừa nhập chỉ lưu ở trình duyệt.');
  });
  document.addEventListener('keydown',ev=>{
    if(ev.key==='Escape'&&assistantMenuOpen){ev.preventDefault();assistantMenuOpen=false;render({focus:'#chat-launcher'});return;}
    if(dialog.open||!panelOpen)return;
    const assist=app.querySelector('.assist.mobile-open');if(!assist)return;
    if(ev.key==='Escape'){ev.preventDefault();panelOpen=false;render({focus:'#chat-launcher'});}
    else if(ev.key==='Tab'&&(state.assistantMode==='full'||matchMedia('(max-width:760px)').matches)){
      const list=Array.from(assist.querySelectorAll('button:not(:disabled),a[href],input,textarea,[tabindex="0"]')).filter(el=>el.getClientRects().length);
      if(!list.length)return;
      const first=list[0],last=list[list.length-1];
      if(ev.shiftKey&&document.activeElement===first){ev.preventDefault();last.focus();}
      else if(!ev.shiftKey&&document.activeElement===last){ev.preventDefault();first.focus();}
    }
  });
  matchMedia('(max-width:760px)').addEventListener('change',()=>{render();});
  window.addEventListener('hashchange',()=>{const hash=location.hash.slice(1);if(P.routes.includes(hash)&&route!==hash){route=hash;panelOpen=false;assistantMenuOpen=false;render();}});
  render();
  window.LIVE_STUDY?.init({render,go,toast,dialog,save});
})();
