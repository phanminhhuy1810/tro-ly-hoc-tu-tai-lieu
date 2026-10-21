'use strict';
/* One review turn, shared by the local demo and the saved-document workspace. */
window.FLASHCARD_UI = (() => {
  const F=window.FLASHCARD_SESSION;
  let bridge,ctx,real=false,owner='demo',storeKey='',saved={},cards=[],courses=[],loaded=false,loading=false,working=false,error='',notice='',selected='',embedded=null,epoch=0,focusRequested='';
  const progressWrites=new Map(),positions=new Map();
  const defaults=()=>({rounds:{},selected:'',filter:'all',shuffle:false,help:{},drafts:{}});
  const E=x=>String(x??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  const T=(vi,en)=>ctx?.state.uiLanguage==='en'?en:vi;
  const icon=name=>ctx?.icon(name)||'';
  const keyOf=c=>JSON.stringify([c.id,c.version,c.front,c.back]);
  const normal=c=>({id:c.id,front:c.front,back:c.back,kind:c.kind,course_id:c.course_id??null,unit_id:c.unit_id??null,version:c.version||1,source_refs:c.source_refs||[]});
  function scope(next){
    if(owner===next&&storeKey)return;
    epoch++;loading=false;working=false;courses=[];embedded=null;notice='';positions.clear();owner=next;storeKey='study-card-rounds-v1:'+next;saved=defaults();
    try{const value=JSON.parse(localStorage.getItem(storeKey)||'{}');saved={...saved,...value,rounds:value.rounds||{},help:value.help||{},drafts:value.drafts||{}};}catch(_){ }
    selected=saved.selected||'';cards=[];loaded=false;error='';
  }
  function persist(){
    const rounds=Object.entries(saved.rounds).slice(-20),help=Object.entries(saved.help).slice(-20);
    saved.rounds=Object.fromEntries(rounds);saved.help=Object.fromEntries(help);
    try{localStorage.setItem(storeKey,JSON.stringify({...saved,selected}));}catch(_){ }
  }
  function redraw(focus){persist();bridge?.render(focus?{focus}:{});}
  function button(action,label,style='secondary',extra=''){return `<button type="button" class="${style}" data-fc="${action}" ${extra} ${working?'disabled':''}>${label}</button>`;}
  function init(value){bridge=value;scope('demo');}
  function setOwner(id){scope(id);}
  async function load(force=false){
    if(!real||loading||loaded&&!force)return;
    loading=true;error='';const token=epoch;
    try{const result=await Promise.all([bridge.api('/cards'),bridge.api('/courses')]);if(token!==epoch)return;[cards,courses]=result;loaded=true;}
    catch(e){if(token===epoch)error=e.message;}
    finally{if(token===epoch){loading=false;redraw();}}
  }
  function setDemo(c){
    scope('demo');real=false;ctx=c;
    cards=[...c.D.cards,...c.state.personalCards].map(card=>({...normal({...card,kind:card.id.startsWith('personal-')?'personal':'generated',course_id:'demo-network',unit_id:card.id.startsWith('personal-')?null:'unit-1',source_refs:card.sourceRefs||[],version:card.revision||1}),memory:{remembered:c.state.cardMemory[card.id]==='known'?true:c.state.cardMemory[card.id]==='unknown'?false:null,version:0}}));
    courses=[{id:'demo-network',revision:1,content:{title:T('Mạng máy tính · bộ thẻ mẫu','Computer networks · sample deck'),units:[{id:'unit-1',title:T('IP và subnet mask','IP and subnet masks'),unlocked:true,data:{}}]}}];loaded=true;
  }
  function decks(){
    const result=[];
    for(const course of courses){
      for(const unit of course.content.units){const list=cards.filter(c=>c.course_id===course.id&&c.unit_id===unit.id&&c.kind==='generated');if(list.length)result.push({id:course.id+'|'+unit.id,course,unit,title:unit.title,subtitle:course.content.title,cards:list});}
      const own=cards.filter(c=>c.course_id===course.id&&c.kind==='personal');if(own.length)result.push({id:course.id+'|personal',course,title:T('Thẻ cá nhân','Personal cards'),subtitle:course.content.title,cards:own});
    }
    const accessible=new Set(courses.map(c=>c.id));const own=cards.filter(c=>c.kind==='personal'&&(!c.course_id||!accessible.has(c.course_id)));if(own.length)result.push({id:'personal',title:T('Thẻ tự tạo','Your own cards'),subtitle:T('Không gắn khóa học','Not linked to a course'),cards:own});
    return result;
  }
  const active=()=>decks().find(d=>d.id===selected);
  function pool(deck){return deck.cards.filter(c=>saved.filter==='new'?c.memory.remembered===null:saved.filter==='unknown'?c.memory.remembered===false:true);}
  function round(deck){
    const entry=saved.rounds[deck.id];if(!entry)return null;
    if(!Array.isArray(entry.ids)||!entry.session){delete saved.rounds[deck.id];notice=T('Lượt lưu không hợp lệ. Hãy bắt đầu lại.','The saved round is invalid. Start a new one.');return null;}
    const list=entry.ids.map(id=>deck.cards.find(c=>c.id===id)).filter(Boolean).map(normal);
    const restored=F.restore(entry.session,list,deck.id);
    if(!restored){delete saved.rounds[deck.id];notice=T('Bộ thẻ đã thay đổi. Chọn một lượt mới để ôn đúng nội dung hiện tại.','The deck changed. Start a new round with the current content.');persist();return null;}
    entry.session=restored;return restored;
  }
  function alerts(){return `${error?`<p class="fc-error" role="alert">${E(error)} ${button('reload',T('Tải lại dữ liệu','Reload data'),'text-button')}</p>`:''}${notice?`<p class="fc-status" role="status">${icon('info')}${E(notice)}</p>`:''}${saved.deleted?`<p class="fc-status">${T('Đã xóa thẻ cá nhân.','Personal card removed.')} ${button('restore',T('Hoàn tác','Undo'),'text-button')}</p>`:''}`;}
  function heading(title,subtitle,level=1){return `<header class="fc-heading"><div><span class="fc-eyebrow">${T('BỘ THẺ','FLASHCARDS')}</span><h${level} data-user-content>${E(title)}</h${level}><p class="fc-subtitle" data-user-content>${E(subtitle)}</p></div>${button('new',icon('plus')+T('Tạo thẻ','New card'),'secondary')}</header>`;}
  function overview(){
    return `${heading('Flashcard',T('Chọn bộ thẻ để bắt đầu ôn.','Choose a deck to review.'))}${alerts()}${!loaded?`<p role="status">${T('Đang mở bộ thẻ đã lưu…','Opening your saved cards…')}</p>`:`<div class="fc-deck-grid">${decks().map(deck=>{const recall=deck.cards.filter(c=>c.memory.remembered===true).length,pending=saved.rounds[deck.id]?.session;return `<button class="fc-deck-tile" data-fc="open" data-deck="${E(deck.id)}"><span class="fc-deck-icon">${icon('cards')}</span><span><strong data-user-content>${E(deck.title)}</strong><p data-user-content>${E(deck.subtitle)}</p><span class="fc-deck-meta"><span>${deck.cards.length} ${T('thẻ','cards')}</span><span>${recall} ${T('đã nhớ','remembered')}</span>${pending&&!pending.completed?`<span>${T('Đang ôn','In progress')} ${pending.index}/${pending.cards.length}</span>`:''}</span></span>${icon('chevron')}</button>`;}).join('')}</div>${!cards.length?`<div class="fc-empty">${icon('cards')}<h2>${T('Chưa có thẻ để ôn.','No cards to review yet.')}</h2><p>${T('Tạo thẻ của riêng bạn, hoặc thêm tài liệu rồi chọn Flashcard.','Make your own cards, or add material and choose Flashcards.')}</p>${button('new',T('Tạo thẻ đầu tiên','Create your first card'),'primary')}</div>`:''}`}`;
  }
  function chooser(deck){
    const list=pool(deck),position=positions.get(deck.course?.id),resumeId=position?.mode_positions?.cards?.card_id||position?.card_id;
    const resume=deck.cards.some(c=>c.id===resumeId)&&!saved.rounds[deck.id];
    return `<div class="fc-toolbar"><label>${T('Thẻ muốn ôn','Review scope')}<select id="fc-filter">${[['all','Tất cả thẻ','All cards'],['new','Chưa ôn lần nào','Not reviewed yet'],['unknown','Đã đánh dấu chưa nhớ','Marked not yet remembered']].map(([id,vi,en])=>`<option value="${id}" ${saved.filter===id?'selected':''}>${T(vi,en)}</option>`).join('')}</select></label><label><input id="fc-shuffle" type="checkbox" ${saved.shuffle?'checked':''}>${T('Trộn thứ tự','Shuffle')}</label></div><div class="fc-empty">${icon('cards')}<h2>${list.length} ${T('thẻ trong lượt này','cards in this round')}</h2><p>${T('Bạn tự đánh giá sau khi lật thẻ. Không có đồng hồ đếm ngược.','Rate your own recall after revealing each answer. Take your time.')}</p>${resume?`<p class="fc-status">${T('Có vị trí ôn đã lưu trên máy chủ. Lượt mới sẽ bắt đầu từ thẻ đó.','A saved server position is available. A new round can begin at that card.')}</p>${button('server-resume',T('Tiếp tục từ thẻ đã lưu','Continue from saved card'),'secondary')}`:''}${button('start',T('Bắt đầu ôn','Start review')+icon('arrow'),'primary',list.length?'':'disabled')}</div><details class="fc-browse"><summary>${T('Xem và sửa nội dung thẻ','Browse and edit cards')} · ${deck.cards.length}</summary><div class="fc-card-list">${deck.cards.map(card=>`<article class="fc-card-row"><div><h3 data-user-content>${E(card.front)}</h3><p data-user-content>${E(card.back)}</p><small>${card.kind==='personal'?T('Thẻ của bạn','Your own card'):T('Từ tài liệu đã duyệt','From an approved source')}</small></div><div class="fc-row-actions">${button('review-one',T('Ôn thẻ này','Review this card'),'text-button',`data-card="${E(card.id)}"`)}${button('edit',T('Sửa','Edit'),'text-button',`data-card="${E(card.id)}"`)}</div></article>`).join('')}</div></details>`;
  }
  function summary(deck,session){
    const total=F.summary(session);
    return `<section class="fc-summary" aria-labelledby="fc-summary-title"><span class="fc-summary-icon">${icon('check')}</span><h2 id="fc-summary-title" tabindex="-1">${T('Đã ôn xong','Review complete')}</h2><p>${T('Đây là mức độ nhớ do bạn tự đánh giá, không phải điểm kiểm tra.','These are your own recall ratings, not an assessment score.')}</p><div class="fc-summary-stats">${[[total.reviewed,'Đã ôn','Reviewed'],[total.remembered,'Đã nhớ','Remembered'],[total.notYet,'Cần ôn lại','Revisit']].map(([n,vi,en])=>`<div class="fc-summary-stat"><strong>${n}</strong>${T(vi,en)}</div>`).join('')}</div><div class="fc-response">${total.notYet?button('retry',T('Ôn lại thẻ chưa nhớ','Review not-yet cards'),'primary'):button('restart',T('Ôn lại cả nhóm','Review the whole deck'),'primary')}${button('groups',T('Chọn nhóm khác','Choose another deck'),'secondary')}</div>${embedded?`<div class="fc-response">${button('learn',T('Về bài học','Back to lesson'),'text-button')}</div>`:''}</section>`;
  }
  function linkedUnit(card,deck){return deck.course?.content.units.find(u=>u.unlocked&&u.data&&(card.unit_id?u.id===card.unit_id:(card.source_refs||[]).some(ref=>u.source_refs?.includes(ref))));}
  function helpMarkup(card){
    const key=keyOf(card),help=saved.help[key];
    if(!help?.open)return '';
    return `<section class="fc-help"><header><strong>${T('Hỏi về đúng thẻ này','Help with this card')}</strong>${button('hide-help',T('Thu gọn','Collapse'),'text-button')}</header><p class="fc-subtitle" data-user-content>${E(card.front)}</p>${help.error?`<p class="fc-error" role="alert">${E(help.error)}</p>`:''}${help.reply?`<div class="fc-help-reply"><small>${T('AI · cần đối chiếu nguồn','AI · check against the source')}</small><p data-user-content>${E(help.reply.text)}</p>${help.reply.source_refs?.length?button('reply-source',T('Đối chiếu nguồn trả lời','Check reply sources'),'text-button'):''}</div>`:''}${help.pending?`<div data-fc-stream="${E(help.jobId)}"><small>${T('AI đang soạn · chưa kiểm tra nguồn','AI draft · sources not yet checked')}</small><p data-user-content>${E(help.preview||T('Đang đọc nguồn cho thẻ này… Bạn có thể tiếp tục ôn.','Reading the source for this card… You can keep reviewing.'))}</p></div>`:`<form id="fc-ask"><label>${T('Điều bạn muốn hiểu thêm','What would you like to understand?')}<textarea name="question" rows="3" maxlength="2000" required placeholder="${T('Ví dụ: Khi nào mình dùng khái niệm này?','Example: When would I use this concept?')}">${E(help.draft||'')}</textarea></label><button class="secondary" ${bridge?.isWorking()?'disabled':''}>${T('Gửi câu hỏi','Ask question')}</button></form>`}<p class="fc-help-note">${T('Trả lời gắn với thẻ đang hỏi. Lịch sử chat chung lưu theo khóa học; lượt AI mới cần xác nhận Coin.','Replies stay attached to the card you asked about. General chat history is course-wide; new AI requests need Coin confirmation.')}</p></section>`;
  }
  function study(deck,session){
    if(session.completed)return summary(deck,session);
    const card=F.current(session),stats=F.summary(session),canAsk=real&&linkedUnit(card,deck);
    return `<div class="fc-progress"><span>${session.index+1} / ${stats.total}</span><span class="fc-track" role="progressbar" aria-label="${T('Tiến trình lượt ôn','Review round progress')}" aria-valuemin="0" aria-valuemax="${stats.total}" aria-valuenow="${stats.reviewed}"><span style="width:${100*stats.reviewed/stats.total}%"></span></span><strong>${stats.reviewed} ${T('đã ôn','reviewed')}</strong></div><div class="fc-study" data-card="${E(card.id)}"><button type="button" id="fc-active-card" class="fc-card ${session.revealed?'is-flipped':''}" data-fc="flip" aria-label="${T(session.revealed?'Lật về câu hỏi':'Lật thẻ xem đáp án',session.revealed?'Return to question':'Reveal card answer')}" aria-pressed="${session.revealed}" ${working?'disabled':''}><span class="fc-face-label">${icon(session.revealed?'check':'cards')}${T(session.revealed?'ĐỐI CHIẾU ĐÁP ÁN':'TỰ NHỚ TRƯỚC',session.revealed?'CHECK THE ANSWER':'RECALL FIRST')}</span><span class="${session.revealed?'fc-answer':'fc-question'}" data-user-content>${E(session.revealed?card.back:card.front)}</span><span class="fc-card-footer">${T(session.revealed?'Bấm để xem lại câu hỏi':'Nghĩ câu trả lời, rồi bấm để lật',session.revealed?'Tap to return to the question':'Think of an answer, then tap to reveal')}</span></button><div class="fc-response">${session.revealed?`${button('rate',icon('back')+T('Chưa nhớ','Not yet'),'secondary fc-again','data-memory="false"')}${button('rate',icon('check')+T('Đã nhớ','Remembered'),'primary fc-remember','data-memory="true"')}`:button('flip',T('Lật thẻ','Reveal answer'),'primary fc-reveal')}</div><div class="fc-utility">${card.source_refs.length?button('source',icon('file')+T('Đối chiếu nguồn','Check source'),'text-button'):''}${canAsk?button('help',icon('chat')+T('Hỏi về thẻ này','Ask about this card'),'text-button'):''}${button('edit',T(card.kind==='personal'?'Chỉnh thẻ':'Sửa thành bản riêng',card.kind==='personal'?'Edit card':'Edit a personal copy'),'text-button')}${real&&card.kind==='generated'&&deck.course?.access_role==='creator'?button('ai-edit',T('Đề xuất sửa AI','AI correction proposal'),'text-button'):''}</div><p class="fc-keyboard"><span><kbd>Space</kbd>${T('lật thẻ','reveal')}</span><span><kbd>1</kbd>${T('chưa nhớ','not yet')}</span><span><kbd>2</kbd>${T('đã nhớ','remembered')}</span></p>${helpMarkup(card)}</div>`;
  }
  function renderDeck(deck){
    const session=round(deck);
    return `${button('groups',icon('back')+T('Các nhóm thẻ','All decks'),'text-button fc-back')}${heading(deck.title,deck.subtitle,embedded?2:1)}${alerts()}${session&&!saved.rounds[deck.id]?.paused?study(deck,session):`${session?`<p class="fc-status">${T('Lượt đang dở vẫn được giữ.','Your review round is saved.')} ${button('resume',T('Tiếp tục lượt đang dở','Resume this round'),'secondary')}</p>`:''}${chooser(deck)}`}${session?`<div class="fc-round-controls">${button('pause',T(session.completed?'Xem nội dung và chọn lượt mới':'Tạm dừng · xem nhóm thẻ',session.completed?'Browse cards and start a new round':'Pause · browse this deck'),'text-button')}</div>`:''}`;
  }
  function renderLibrary(c,serverCourses){
    ctx=c;real=true;embedded=null;if(serverCourses?.length)courses=serverCourses;if(!loaded&&!loading&&!error)load();
    const deck=active();if(selected&&!deck&&loaded)selected='';
    return `<main id="main" class="product-page flashcards-page"><section class="fc-shell">${deck?renderDeck(deck):overview()}<p class="fc-footnote">${T('Nhớ/chưa nhớ được lưu trên máy chủ. Chưa áp dụng lịch ôn giãn cách.','Recall is saved on the server. Spaced repetition is not enabled.')}</p></section></main>`;
  }
  function renderUnit(c,course,unit){
    ctx=c;real=true;const changed=!embedded||embedded.course.id!==course.id||embedded.unit.id!==unit.id;embedded={course,unit};if(changed)selected=course.id+'|'+unit.id;if(!loaded&&!loading&&!error)load();
    if(!selected||!selected.startsWith(course.id+'|')){selected=course.id+'|'+unit.id;}
    const deck=active();if(deck&&!positions.has(deck.course?.id)){positions.set(deck.course?.id,null);readPosition(deck).then(()=>redraw());}
    return `<section class="fc-shell">${loaded?(deck?renderDeck(deck):`<div class="fc-empty"><h2>${T('Bài này chưa có thẻ.','This lesson has no cards yet.')}</h2><p>${T('Bạn có thể tạo thẻ riêng hoặc chọn nhóm thẻ khác.','Create your own cards or choose another deck.')}</p>${button('new',T('Tạo thẻ','New card'),'primary')}${button('groups',T('Chọn nhóm khác','Choose another deck'),'secondary')}</div>`):`<p role="status">${T('Đang mở bộ thẻ…','Opening cards…')}</p>`}</section>`;
  }
  function renderDemo(c){setDemo(c);embedded=null;if(focusRequested){const d=decks().find(d=>d.cards.some(c=>c.id===focusRequested));if(d){selected=d.id;const card=d.cards.find(c=>c.id===focusRequested);saved.rounds[d.id]={session:F.start([normal(card)],{context:d.id}),ids:[card.id]};}focusRequested='';}const deck=active();return `<main id="main" class="product-page flashcards-page"><section class="fc-shell">${deck?renderDeck(deck):overview()}<p class="fc-footnote">${T('Bộ thẻ mẫu và thẻ bạn tự tạo trên trình duyệt. Chưa áp dụng lịch ôn giãn cách.','Sample cards and your own browser cards. Spaced repetition is not enabled.')}</p></section></main>`;}
  function savePosition(deck,card){
    if(!real||!deck.course)return Promise.resolve();
    const u=linkedUnit(card,deck)||deck.course.content.units.find(u=>u.unlocked&&u.data);if(!u)return Promise.resolve();
    const id=deck.course.id,revision=deck.course.revision,token=epoch;
    const chain=(progressWrites.get(id)||Promise.resolve()).catch(()=>{}).then(async()=>{
      if(token!==epoch)return;
      const p=await bridge.api('/courses/'+id+'/progress');
      const result=await bridge.api('/courses/'+id+'/progress',{expected_version:p.version,expected_revision:revision,mode:'cards',unit_id:u.id,card_id:card.id},'PUT');
      positions.set(id,{...result,mode_positions:{...p.mode_positions,cards:result}});
    }).catch(e=>{if(token===epoch)notice=T('Chưa đồng bộ được vị trí ôn: ','Review position did not sync: ')+e.message;});
    progressWrites.set(id,chain);return chain;
  }
  async function readPosition(deck){
    if(!real||!deck?.course)return;
    const token=epoch;try{const value=await bridge.api('/courses/'+deck.course.id+'/progress');if(token===epoch)positions.set(deck.course.id,value);}catch(_){ }
  }
  async function start(deck,ids){
    const list=ids?ids.map(id=>deck.cards.find(c=>c.id===id)).filter(Boolean):pool(deck);
    if(!list.length)return;
    for(const card of list){const h=saved.help[keyOf(card)];if(h)h.open=false;}
    const session=F.start(list.map(normal),{context:deck.id,shuffle:!!saved.shuffle});saved.rounds[deck.id]={session,ids:list.map(c=>c.id)};error='';notice='';persist();redraw('#fc-active-card');await savePosition(deck,F.current(session));
  }
  async function rate(value){
    const deck=active(),session=deck&&round(deck);if(!session||!session.revealed||working)return;
    const pinned=F.current(session),card=cards.find(c=>c.id===pinned.id);if(!card)return;
    working=true;error='';const token=epoch;redraw();
    try{
      if(real){const result=await bridge.api('/cards/'+encodeURIComponent(card.id)+'/memory',{course_id:deck.course?card.course_id:null,expected_revision:deck.course?.revision,expected_version:card.memory.version,remembered:value},'PUT');if(token!==epoch)return;card.memory={remembered:value,version:result.version};}
      else{ctx.state.cardMemory[card.id]=value?'known':'unknown';card.memory.remembered=value;bridge.save();}
      const next=F.rate(session,value);saved.rounds[deck.id].session=next;persist();
      await savePosition(deck,F.current(next)||pinned);
    }catch(e){if(token===epoch)error=e.message;}
    finally{if(token===epoch){working=false;const s=saved.rounds[deck.id]?.session;redraw(s?.completed?'#fc-summary-title':'#fc-active-card');}}
  }
  async function source(card,deck){
    const dialog=bridge.dialog;
    let fragments;
    if(real)fragments=deck.course?await bridge.api('/courses/'+deck.course.id+'/source-fragments'):[];
    else fragments=ctx.D.sourceLines.map(x=>({...x,locator:{label:x.locator}}));
    const matches=fragments.filter(f=>card.source_refs.includes(f.id));
    dialog.className='live-source-dialog';dialog.innerHTML=`<h2>${T('Nguồn của thẻ đang xem','Source for this card')}</h2>${matches.map(f=>`<section><small>${E(f.locator.label||(f.locator.page?T('Trang','Page')+' '+f.locator.page:f.locator.slide?'Slide '+f.locator.slide:f.locator.paragraph?T('Đoạn','Paragraph')+' '+f.locator.paragraph:T('Dòng','Line')+' '+(f.locator.line||'')))}</small><p class="live-text">${E(f.text)}</p></section>`).join('')||`<p>${T('Đoạn nguồn này thuộc bản cũ hoặc chưa được chia sẻ quyền xem. Thẻ vẫn giữ nguyên nội dung đã lưu.','This excerpt belongs to an older revision or is not shared with you. The saved card is unchanged.')}</p>`}${button('close',T('Đóng','Close'),'secondary')}`;dialog.showModal();
  }
  function editor(card){
    const deck=active(),draftKey=card?keyOf(card):'new:'+(deck?.course?.id||''),draft=saved.drafts[draftKey]||card||{},dialog=bridge.dialog;
    dialog.className='fc-editor-dialog';dialog.innerHTML=`<form id="fc-editor" data-card="${E(card?.id||'')}" data-draft="${E(draftKey)}" data-version="${card?.version||0}"><h2>${T(card?.kind==='generated'?'Sửa thành thẻ của riêng bạn':card?'Chỉnh thẻ cá nhân':'Tạo một thẻ mới',card?.kind==='generated'?'Edit as your own card':card?'Edit personal card':'Create a card')}</h2><p>${card?.course_id&&!courses.some(c=>c.id===card.course_id)?T('Khóa cũ không còn quyền truy cập. Khi lưu, bản riêng sẽ tách khỏi khóa và nguồn cũ. ','The previous course is inaccessible. Saving will detach your private copy from that course and source. '):''}${T(card?.kind==='generated'?'Nội dung khóa giữ nguyên. Bản sửa được lưu vào nhóm Thẻ cá nhân.':'Mặt trước hỏi một ý; mặt sau trả lời ngắn và rõ.',card?.kind==='generated'?'The shared course stays unchanged. Your copy goes into Personal cards.':'Ask one thing on the front; keep the answer clear and concise.')}</p><label>${T('Mặt trước','Front')}<textarea name="front" rows="3" required maxlength="1000">${E(draft.front||'')}</textarea></label><label>${T('Mặt sau','Back')}<textarea name="back" rows="5" required maxlength="3000">${E(draft.back||'')}</textarea></label><p class="fc-editor-error" role="alert"></p><div class="dialog-actions"><button class="primary">${T('Lưu thẻ','Save card')}</button>${button('close',T('Để sau','Later'),'secondary')}</div>${card?.kind==='personal'?button('delete',T('Xóa thẻ này','Delete this card'),'text-button',`data-card="${E(card.id)}"`):''}</form>`;dialog.showModal();dialog.querySelector('textarea').focus();
  }
  async function saveEditor(form){
    if(working)return;const fields=new FormData(form),old=cards.find(c=>c.id===form.dataset.card),deck=active(),draftKey=form.dataset.draft;
    const accessible=old?.course_id?courses.some(c=>c.id===old.course_id):true;
    const body={front:String(fields.get('front')).trim(),back:String(fields.get('back')).trim(),course_id:accessible?(old?.course_id||deck?.course?.id||null):null,source_refs:accessible?(old?.source_refs||[]):[]};
    if(!body.front||!body.back)return;const token=epoch;working=true;form.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{
      let id;
      if(real){const result=await bridge.api(old?.kind==='personal'?'/cards/'+old.id:'/cards',old?.kind==='personal'?{...body,expected_version:Number(form.dataset.version)}:body,old?.kind==='personal'?'PUT':'POST');id=result.id;if(token!==epoch)return;}
      else{const list=ctx.state.personalCards,previous=old?.kind==='personal'?list.find(c=>c.id===old.id):null;id=previous?.id||'personal-'+crypto.randomUUID();const value={id,front:body.front,back:body.back,sourceRefs:body.source_refs,revision:(previous?.revision||0)+1};if(previous)Object.assign(previous,value);else list.push(value);delete ctx.state.cardMemory[id];bridge.save();}
      delete saved.drafts[draftKey];if(deck&&old?.kind==='personal')delete saved.rounds[deck.id];selected=body.course_id?body.course_id+'|personal':'personal';bridge.dialog.close();notice=T('Đã lưu thẻ riêng. Nội dung mới cần được ôn lại.','Personal card saved. Review the updated content again.');if(real)await load(true);
    }catch(e){if(token===epoch)form.querySelector('.fc-editor-error').textContent=e.message;}
    finally{if(token!==epoch)return;working=false;if(form.isConnected)form.querySelectorAll('button').forEach(b=>b.disabled=false);redraw();}
  }
  function currentCard(){const deck=active(),session=deck&&round(deck);return session&&!session.completed?F.current(session):null;}
  async function receiveChat(jobId,result){
    const entry=Object.values(saved.help).find(h=>h.jobId===jobId);if(!entry)return;
    entry.reply=result;entry.pending=false;entry.draft='';entry.preview='';
    redraw();
  }
  async function handle(action,b){
    if(action==='close'){bridge.dialog.close();return;}
    if(working)return;
    const deck=active(),card=b.dataset.card?cards.find(c=>c.id===b.dataset.card):currentCard();
    if(action==='open'){selected=b.dataset.deck;notice='';error='';redraw();await readPosition(active());redraw();return;}
    if(action==='groups'){embedded=null;selected='';notice='';error='';bridge.go('flashcards');redraw();return;}
    if(action==='learn'){bridge.learn();return;}
    if(action==='reload'){loaded=false;await load(true);return;}
    if(action==='review-one'){if(card)await start(deck,[card.id]);return;}
    if(action==='new'){editor();return;}
    if(action==='edit'){if(card)editor(card);return;}
    if(action==='server-resume'){const p=positions.get(deck.course?.id),id=p?.mode_positions?.cards?.card_id||p?.card_id,index=deck.cards.findIndex(c=>c.id===id);if(index>=0){const list=[...deck.cards.slice(index),...deck.cards.slice(0,index)].map(c=>c.id);await start(deck,list);}return;}
    if(action==='restart'){await start(deck,deck.cards.map(c=>c.id));return;}
    if(action==='start'){await start(deck);return;}
    if(action==='retry'){const ids=saved.rounds[deck.id].session.results.filter(r=>!r.remembered).map(r=>r.cardId);await start(deck,ids);return;}
    if(action==='pause'){saved.paused=deck.id;const entry=saved.rounds[deck.id];if(entry?.session.completed)delete saved.rounds[deck.id];else entry.paused=true;redraw();return;}
    if(action==='resume'){delete saved.rounds[deck.id].paused;redraw('#fc-active-card');return;}
    if(action==='flip'){const session=round(deck);if(session&&!session.completed){saved.rounds[deck.id].session=F.flip(session);redraw('#fc-active-card');}return;}
    if(action==='rate'){await rate(b.dataset.memory==='true');return;}
    if(action==='source'){await source(card,deck);return;}
    if(action==='help'){const key=keyOf(card);saved.help[key]={...saved.help[key],open:true};redraw('#fc-ask textarea');return;}
    if(action==='hide-help'){saved.help[keyOf(card)].open=false;redraw('#fc-active-card');return;}
    if(action==='reply-source'){await source({...card,source_refs:saved.help[keyOf(card)].reply.source_refs},deck);return;}
    if(action==='ai-edit'){await bridge.correctCard(card);return;}
    if(action==='delete'){
      if(real)await bridge.api('/cards/'+card.id,{},'DELETE');else{ctx.state.personalCards=ctx.state.personalCards.filter(c=>c.id!==card.id);bridge.save();}
      saved.deleted=real?{id:card.id}:null;if(deck)delete saved.rounds[deck.id];bridge.dialog.close();if(real)await load(true);redraw();return;
    }
    if(action==='restore'){await bridge.api('/cards/'+saved.deleted.id+'/restore',{});saved.deleted=null;await load(true);return;}
  }
  document.addEventListener('click',event=>{const b=event.target.closest('[data-fc]');if(!b||b.disabled)return;handle(b.dataset.fc,b).catch(e=>{error=e.message;redraw();});});
  document.addEventListener('change',event=>{if(event.target.id==='fc-filter'){saved.filter=event.target.value;redraw();}if(event.target.id==='fc-shuffle'){saved.shuffle=event.target.checked;persist();}});
  document.addEventListener('input',event=>{
    const editor=event.target.closest('#fc-editor');if(editor){saved.drafts[editor.dataset.draft]={front:editor.querySelector('[name=front]').value,back:editor.querySelector('[name=back]').value};persist();}
    if(event.target.closest('#fc-ask')){const card=currentCard();if(card){saved.help[keyOf(card)].draft=event.target.value;persist();}}
  });
  document.addEventListener('submit',event=>{
    const form=event.target;if(form.id==='fc-editor'){event.preventDefault();saveEditor(form);}
    if(form.id==='fc-ask'){
      event.preventDefault();const card=currentCard(),deck=active(),u=card&&linkedUnit(card,deck),help=card&&saved.help[keyOf(card)];if(!u||!help||help.pending||bridge.isWorking())return;
      const question=String(new FormData(form).get('question')).trim();if(!question)return;
      help.pending=true;help.error='';help.courseId=card.course_id;persist();redraw();
      bridge.askCard(card,question,u.id,job=>{help.jobId=job.job_id;persist();}).catch(e=>{help.error=e.message;}).finally(()=>{help.pending=false;redraw();});
    }
  });
  document.addEventListener('keydown',event=>{
    if(!document.querySelector('.fc-study')||document.querySelector('dialog[open]')||event.repeat||event.ctrlKey||event.metaKey||event.altKey||event.target.matches('input,textarea,select,[contenteditable=true]')||event.target.closest('button,a')&&event.target.id!=='fc-active-card')return;
    const card=currentCard();if(!card||working)return;
    if(event.code==='Space'){event.preventDefault();handle('flip',{dataset:{}});}
    if(['1','2'].includes(event.key)&&round(active()).revealed){event.preventDefault();rate(event.key==='2');}
  });
  return {init,setOwner,focusCard(id){focusRequested=id;},renderLibrary,renderUnit,renderDemo,receiveChat,receiveProgress(jobId,progress){const entry=Object.values(saved.help).find(h=>h.jobId===jobId);if(entry){entry.preview=progress?.preview?.text||'';const node=document.querySelector('[data-fc-stream="'+jobId+'"] p');if(node)node.textContent=entry.preview||T('Đang kiểm tra câu trả lời…','Checking the response…');}},receiveFailure(jobId,message){const entry=Object.values(saved.help).find(h=>h.jobId===jobId);if(entry){entry.pending=false;entry.error=message;entry.preview='';redraw();}},invalidate(){loaded=false;},load};
})();
