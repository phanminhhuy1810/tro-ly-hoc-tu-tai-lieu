'use strict';
/* Motion follows an actual UI change. It never delays grading, persistence or
   focus, and does not replay selections on unrelated full-template renders. */
window.STUDY_MOTION = (() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const active = new Set();
  const ease = 'cubic-bezier(.2,.75,.25,1)';
  let last = null;
  let preference = 'system';
  let pendingPress = null;
  let pendingField = null;
  const tabGroups = ['.lesson-tabs','.assist-switch'];
  const selected = 'button.selected,button[aria-pressed="true"],button[aria-selected="true"],.lesson-tab.active,.assist-switch button.active,.note-list-item.selected';
  const controlSelector='button:not(:disabled),a[href],[role="button"]:not([aria-disabled="true"]),summary';
  const rect = el => {
    if(!el)return null;
    const r=el.getBoundingClientRect();
    return {left:r.left,top:r.top,width:r.width,height:r.height};
  };
  const key = el => {
    const data=Object.entries(el.dataset).filter(([k])=>!k.startsWith('motion')).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>k+'='+v).join('|');
    if(data||el.id)return el.tagName+'|'+data+'|'+(el.id||'');
    const form=el.closest('form');
    return [el.tagName,el.getAttribute('name')||'',el.getAttribute('href')||'',form?.id||'',el.getAttribute('aria-label')||'',el.textContent.trim()].join('|');
  };
  const text=el=>el?.textContent.trim()||'';
  function detailKey(el,index){return key(el)+'|'+el.className+'|'+index;}
  function captureUI(app){
    const study=app.querySelector('.fc-study'),card=study?.querySelector('.fc-card'),progress=app.querySelector('.fc-track>span');
    const helpers=new Map([...app.querySelectorAll('.live-inline-help')].map(el=>{
      const content=el.querySelector('.live-inline-content');
      return [el.querySelector('[data-inline-key]')?.dataset.inlineKey,{open:!!content,tail:text(content?.querySelector('.live-inline-message:last-of-type'))}];
    }));
    return {
      scope:[text(app.querySelector('#main h1')),app.querySelector('.live-node.selected')?.dataset.unit||''].join('|'),
      details:[...app.querySelectorAll('details')].map((el,i)=>({key:detailKey(el,i),open:el.open})),
      fc:{present:!!app.querySelector('.fc-shell'),id:study?.dataset.card,flipped:card?.getAttribute('aria-pressed')==='true',summary:!!app.querySelector('.fc-summary'),progress:progress?getComputedStyle(progress).width:null,help:!!study?.querySelector('.fc-help'),reply:text(study?.querySelector('.fc-help-reply')),choice:!!app.querySelector('.fc-empty'),decks:!!app.querySelector('.fc-deck-grid')},
      helpers,
      liveMode:app.querySelector('.live-mode-select [aria-pressed="true"]')?.dataset.mode,
      liveQuestion:app.querySelector('#live-answer')?.dataset.question,
      liveFeedback:text(app.querySelector('.live-feedback,.live-practice-feedback')),
      sourceMethod:app.querySelector('.studio-method-tabs [aria-pressed="true"]')?.dataset.method,
      liveOrder:new Map([...app.querySelectorAll('.live-order>li')].map(el=>[text(el.querySelector(':scope>span')),rect(el)]))
    };
  }
  const enabled = () => preference!=='off'&&!reduce.matches;
  function syncPreference(value){
    preference=value==='off'?'off':'system';
    document.documentElement.dataset.motion=enabled()?'on':'off';
    if(!enabled())for(const animation of active)animation.cancel();
  }
  reduce.addEventListener('change',()=>syncPreference(preference));
  function animate(el,frames,duration=200,extra={}){
    if(!el||!enabled()||!el.animate)return null;
    const animation=el.animate(frames,{duration,easing:ease,...extra});
    active.add(animation);
    animation.finished.catch(()=>{}).finally(()=>active.delete(animation));
    return animation;
  }
  function exitCopy(el){
    if(!el||!enabled())return null;
    const clone=el.cloneNode(true),r=rect(el);
    clone.removeAttribute('id');clone.removeAttribute('role');clone.removeAttribute('aria-modal');
    clone.querySelectorAll('[id]').forEach(x=>x.removeAttribute('id'));
    clone.setAttribute('aria-hidden','true');clone.inert=true;
    clone.classList.add('motion-exit-copy');
    Object.assign(clone.style,{position:'fixed',inset:'auto',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px',maxHeight:'none',pointerEvents:'none',margin:'0',zIndex:'74'});
    return clone;
  }
  function beforeRender(app,c){
    syncPreference(c.state.motionPreference);
    const nav=app.querySelector('.ref-sidebar-nav');
    const oldCard=app.querySelector('.flashcard-rotator');
    return {
      selections:new Set([...app.querySelectorAll(selected)].map(key)),
      ui:captureUI(app),
      nav:rect(app.querySelector('.motion-nav-highlight')||nav?.querySelector('.active')),
      navPage:nav?.querySelector('.active')?.dataset.page,
      navScrollLeft:nav?.scrollLeft||0,navScrollTop:nav?.scrollTop||0,
      assist:rect(app.querySelector('.product-assist')),
      closing:!c.panelOpen?exitCopy(app.querySelector('.product-assist')):null,
      closingMenu:!c.assistantMenuOpen?exitCopy(app.querySelector('.assistant-mode-menu')):null,
      cardExit:last?.route===c.route&&c.route==='flashcards'&&last.card!==c.cards?.[c.state.cardIndex]?.id?exitCopy(app.querySelector('.study-flashcard')):null,
      openManagement:Boolean(app.querySelector('.course-management[open]')),
      openExcerpts:[...app.querySelectorAll('.extraction-fragment[open]')].map(x=>x.id),
      order:Object.fromEntries([...app.querySelectorAll('.ordering-item')].map(x=>[x.dataset.orderItem,rect(x)])),
      tabs:Object.fromEntries(tabGroups.map(selector=>{const group=app.querySelector(selector),button=group?.querySelector('button.active');return [selector,{box:rect(group?.querySelector('.motion-tab-highlight')||button),key:button?key(button):null}];})),
      flipped:oldCard?.classList.contains('is-flipped'),
      flipTransform:oldCard?getComputedStyle(oldCard).transform:null,
      bars:[...app.querySelectorAll('.thin-progress>span')].map(x=>getComputedStyle(x).width)
    };
  }
  function stagger(nodes,gap=35){
    [...nodes].forEach((node,i)=>animate(node,[{opacity:.25,transform:'translateY(9px)'},{opacity:1,transform:'none'}],250,{delay:Math.min(i*gap,150),fill:'backwards'}));
  }
  function enterPage(app,route){
    const selectors={
      home:'.product-head,.product-resume,.home-course-layout>section,.home-bottom-note',
      dashboard:'.product-head,.timeline-card,.streak-card,.learning-progress',
      library:'.product-head,.product-toolbar,.personal-course,.source-library',
      course:'.product-head,.course-mode-row,.course-path,.course-details,.community-preview,.outline-topics',
      community:'.product-head,.product-toolbar,.community-course',
      missions:'.product-head,.mission-card,.achievement-card',
      notebook:'.product-head,.notebook-list,.note-editor',
      review:'.product-head,.review-options,.review-grid>.product-card,.practice-history',
      rooms:'.product-head,.room-entry-grid>.product-card',
      settings:'.product-head,.settings-card,.settings-data'
    };
    const parts=selectors[route]?app.querySelectorAll(selectors[route]):[];
    if(parts.length)stagger(parts);else animate(app.querySelector('#main'),[{opacity:.35,transform:'translateY(7px)'},{opacity:1,transform:'none'}],220);
    if(route==='course'){
      animate(app.querySelector('.winding-line'),[{clipPath:'inset(0 0 100% 0)'},{clipPath:'inset(0 0 0% 0)'}],450);
      app.querySelectorAll('.path-circle').forEach((node,i)=>animate(node,[{opacity:.25,transform:'scale(.94)'},{opacity:1,transform:'scale(1)'}],260,{delay:i*70,fill:'backwards'}));
    }
    if(route==='lesson')enterStudyVisuals(app);
    for(const circle of app.querySelectorAll('.motion-ring-value')){
      const end=getComputedStyle(circle).strokeDashoffset;
      animate(circle,[{strokeDashoffset:119.38},{strokeDashoffset:end}],380,{delay:80,fill:'backwards'});
    }
  }
  function enterStudyVisuals(app){
    stagger(app.querySelectorAll('.octet'),30);
    animate(app.querySelector('.map-trunk'),[{transform:'scaleY(0)'},{transform:'scaleY(1)'}],240);
    stagger(app.querySelectorAll('.map-node'),45);
  }
  function tabHighlights(app,old){
    for(const selector of tabGroups){
      const group=app.querySelector(selector),button=group?.querySelector('button.active');if(!button)continue;
      const pill=document.createElement('span');pill.className='motion-tab-highlight';pill.setAttribute('aria-hidden','true');
      group.classList.add('motion-tab-ready');
      Object.assign(pill.style,{left:button.offsetLeft+'px',top:button.offsetTop+'px',width:button.offsetWidth+'px',height:button.offsetHeight+'px'});
      group.append(pill);
      const before=old.tabs[selector],now=rect(pill);
      if(before.box&&before.key!==key(button))animate(pill,[{transform:`translate(${before.box.left-now.left}px,${before.box.top-now.top}px) scale(${before.box.width/now.width},${before.box.height/now.height})`},{transform:'none'}],220);
    }
  }
  function pressWave(button,point={x:.5,y:.5}){
    if(!enabled()||!button?.matches(controlSelector)||button.matches('.fc-card,.study-flashcard'))return;
    button.querySelectorAll('.motion-press-wave').forEach(x=>x.remove());
    button.classList.add('motion-ink-ready');
    const wave=document.createElement('span');wave.className='motion-press-wave';wave.setAttribute('aria-hidden','true');
    Object.assign(wave.style,{left:point.x*button.clientWidth+'px',top:point.y*button.clientHeight+'px'});button.append(wave);
    const a=animate(wave,[{opacity:.15,transform:'translate(-50%,-50%) scale(.1)'},{opacity:0,transform:'translate(-50%,-50%) scale(1)'}],280);
    if(a)a.finished.catch(()=>{}).finally(()=>wave.remove());else wave.remove();
  }
  document.addEventListener('click',ev=>{
    const button=ev.target.closest?.(controlSelector);if(!button||!enabled()||button.closest('[inert]'))return;
    const r=button.getBoundingClientRect();
    const point=ev.detail?{x:Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(ev.clientY-r.top)/r.height))}:{x:.5,y:.5};
    pendingPress={key:key(button),point};pressWave(button,point);
    queueMicrotask(()=>{pendingPress=null;});
  },true);
  document.addEventListener('toggle',ev=>{
    const details=ev.target;if(!details.matches?.('details')||!details.open)return;
    if(details.dataset.motionRestored){delete details.dataset.motionRestored;return;}
    if(enabled())stagger([...details.children].filter(x=>x.tagName!=='SUMMARY'),30);
  },true);
  document.addEventListener('change',ev=>{
    const field=ev.target;
    if(!enabled()||!field.matches?.('select,input[type="checkbox"],input[type="radio"]')||field.disabled)return;
    // The native value changes first; this feedback never dispatches another event.
    pendingField=key(field);fieldFeedback(field);
    queueMicrotask(()=>{pendingField=null;});
  },true);
  function fieldFeedback(field){
    const visual=field.matches('select')?field:field.closest('label')||field;
    animate(visual,[{boxShadow:'0 0 0 0 #91aa6b00'},{boxShadow:'0 0 0 3px #91aa6b35',offset:.35},{boxShadow:'0 0 0 0 #91aa6b00'}],280);
  }
  function signal(type){
    if(!enabled())return;
    if(type==='note-saved'){
      const panel=document.querySelector('#app .note-editor');
      animate(panel,[{boxShadow:'0 0 0 0px #b3c99000'},{boxShadow:'0 0 0 3px #b3c99045',offset:.3},{boxShadow:'0 0 0 0px #b3c99000'}],420);
      const path=panel?.querySelector('[data-action="save-note"] svg path');
      if(path){const n=path.getTotalLength();animate(path,[{strokeDasharray:n,strokeDashoffset:n},{strokeDasharray:n,strokeDashoffset:0}],230);}
    }else if(type==='card-known'||type==='card-unknown'){
      animate(document.querySelector('.flashcard-status>span:last-child'),[{transform:'scale(.95)',opacity:.5},{transform:'scale(1)',opacity:1}],230);
    }
  }
  function drawCheck(el){
    for(const path of el.querySelectorAll('.ref-selection svg path,.answer-selection svg path,.correct>svg path,.feedback strong svg path')){
      const length=path.getTotalLength();
      animate(path,[{strokeDasharray:length,strokeDashoffset:length},{strokeDasharray:length,strokeDashoffset:0}],190);
    }
  }
  function navHighlight(app,old){
    const nav=app.querySelector('.ref-sidebar-nav'),button=nav?.querySelector('button.active');
    if(!button)return;
    nav.scrollLeft=old.navScrollLeft;nav.scrollTop=old.navScrollTop;
    const pill=document.createElement('span');pill.className='motion-nav-highlight';pill.setAttribute('aria-hidden','true');
    nav.classList.add('motion-nav-ready');
    Object.assign(pill.style,{left:button.offsetLeft+'px',top:button.offsetTop+'px',width:button.offsetWidth+'px',height:button.offsetHeight+'px'});
    nav.append(pill);
    if(old.nav&&old.navPage!==button.dataset.page){
      const now=rect(pill);
      animate(pill,[{transform:`translate(${old.nav.left-now.left}px,${old.nav.top-now.top}px) scale(${old.nav.width/now.width},${old.nav.height/now.height})`},{transform:'none'}],210);
    }
  }
  function closeCopies(old){
    for(const copy of [old.closing,old.closingMenu]){
      if(!copy)continue;
      document.body.append(copy);
      const a=animate(copy,[{opacity:1,transform:'none'},{opacity:0,transform:'translateY(7px) scale(.99)'}],130,{easing:'ease-out'});
      if(a)a.finished.catch(()=>{}).finally(()=>copy.remove());else copy.remove();
    }
  }
  function animateCurrentUI(app,old,next){
    const before=old.ui,now=next;
    if(!before)return;
    // A full-template refresh can happen while saving or waiting for AI. Animate
    // semantic changes, never merely the fact that a new DOM node was created.
    const sameScope=before.scope===now.scope;
    if(sameScope&&before.liveMode!==now.liveMode&&now.liveMode){
      animate(app.querySelector('.live-lesson>.live-reading,.live-lesson>.fc-shell,.live-lesson>#live-answer,.live-lesson>.live-result,.live-lesson>.live-feedback'),[{opacity:.4,transform:'translateY(6px)'},{opacity:1,transform:'none'}],180);
    }
    if(sameScope&&before.sourceMethod!==now.sourceMethod&&now.sourceMethod){
      animate(app.querySelector('.studio-source-form'),[{opacity:.35,transform:'translateY(6px)'},{opacity:1,transform:'none'}],180);
    }
    if(sameScope&&before.liveQuestion!==now.liveQuestion&&now.liveQuestion){
      animate(app.querySelector('#live-answer'),[{opacity:.3,transform:'translateX(12px)'},{opacity:1,transform:'none'}],200);
    }
    if(sameScope&&before.liveFeedback!==now.liveFeedback&&now.liveFeedback){
      const feedback=app.querySelector('.live-feedback,.live-practice-feedback');
      animate(feedback,[{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],200);
      if(feedback)drawCheck(feedback);
    }
    if(sameScope&&before.liveQuestion===now.liveQuestion&&now.liveQuestion){
      for(const el of app.querySelectorAll('.live-order>li')){
        const was=before.liveOrder.get(text(el.querySelector(':scope>span'))),to=rect(el);
        if(was&&was.top!==to.top)animate(el,[{transform:`translateY(${was.top-to.top}px)`},{transform:'none'}],200);
      }
    }
    for(const el of app.querySelectorAll('.live-inline-help')){
      const id=el.querySelector('[data-inline-key]')?.dataset.inlineKey,was=before.helpers.get(id),content=el.querySelector('.live-inline-content');
      if(!content)continue;
      if(!was?.open)animate(content,[{opacity:.2,transform:'translateY(7px)'},{opacity:1,transform:'none'}],200);
      else if(was.tail!==text(content.querySelector('.live-inline-message:last-of-type')))animate(content.querySelector('.live-inline-message:last-of-type'),[{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],190);
    }
    const previous=before.fc,current=now.fc;
    if(!current.present)return;
    const card=app.querySelector('.fc-card'),sameCard=previous.id&&previous.id===current.id;
    if(card&&sameCard&&previous.flipped!==current.flipped){
      animate(card,[{opacity:.4,transform:`rotateY(${current.flipped?-64:64}deg) scale(.985)`},{opacity:1,transform:'rotateY(0deg) scale(1)'}],260);
      animate(app.querySelector('.fc-response'),[{opacity:.25,transform:'translateY(5px)'},{opacity:1,transform:'none'}],180);
    }else if(card&&(!previous.id||previous.id!==current.id)){
      animate(card,[{opacity:.3,transform:'translateX(18px) rotate(.6deg)'},{opacity:1,transform:'none'}],230);
    }
    if(current.summary&&!previous.summary){
      animate(app.querySelector('.fc-summary'),[{opacity:.3,transform:'translateY(9px)'},{opacity:1,transform:'none'}],230);
      animate(app.querySelector('.fc-summary-icon'),[{transform:'rotate(-11deg) scale(.8)'},{transform:'rotate(-3deg) scale(1.06)',offset:.7},{transform:'rotate(-5deg) scale(1)'}],330);
    }
    if(previous.progress&&current.progress&&previous.progress!==current.progress)animate(app.querySelector('.fc-track>span'),[{width:previous.progress},{width:current.progress}],240);
    if(card&&current.help&&!previous.help)animate(app.querySelector('.fc-help'),[{opacity:.25,transform:'translateY(7px)'},{opacity:1,transform:'none'}],200);
    else if(sameCard&&current.reply&&previous.reply!==current.reply)animate(app.querySelector('.fc-help-reply'),[{opacity:.2,transform:'translateY(6px)'},{opacity:1,transform:'none'}],200);
    if(!card&&!current.summary&&previous.id)animate(app.querySelector('.fc-toolbar,.fc-deck-grid'),[{opacity:.3,transform:'translateY(6px)'},{opacity:1,transform:'none'}],190);
  }
  function restoreDisclosures(app,old,current){
    if(old.ui?.scope!==current.scope||last?.route!==current.route)return;
    const opened=new Set(old.ui.details.filter(x=>x.open).map(x=>x.key));
    for(const [index,details] of [...app.querySelectorAll('details')].entries()){
      if(!details.open&&opened.has(detailKey(details,index))){details.dataset.motionRestored='true';details.open=true;}
    }
  }
  function afterRender(app,c,old){
    const {state:s,route}=c;
    const next={route,course:s.courseId,step:s.setupStep,tab:s.tab,question:c.questions?.[s.qIndex]?.id,card:c.cards?.[s.cardIndex]?.id,cardIndex:s.cardIndex,flipped:s.cardFlipped,order:JSON.stringify(s.answers[c.questions?.[s.qIndex]?.id]),panel:c.panel,panelOpen:c.panelOpen,size:s.assistantMode,menu:c.assistantMenuOpen,language:s.uiLanguage,checked:JSON.stringify(s.checked),completed:s.completed,chatTail:s.chat.at(-1)};
    const press=pendingPress;pendingPress=null;
    const currentUI=captureUI(app);
    restoreDisclosures(app,old,{...currentUI,route});
    navHighlight(app,old);tabHighlights(app,old);closeCopies(old);
    if(old.openManagement&&last?.route===route&&last.course===next.course){const details=app.querySelector('.course-management');if(details){details.dataset.motionRestored='true';details.open=true;}}
    if(last?.route===route&&last.step===next.step)for(const id of old.openExcerpts){const details=app.querySelector('#'+CSS.escape(id));if(details)details.open=true;}
    if(!enabled()){last=next;return;}
    // UI-language changes update immediately, without replaying content motion.
    const sameLanguage=!last||last.language===next.language;
    const newPage=!last||last.route!==route||(route==='setup'&&last.step!==next.step);
    if(sameLanguage&&newPage){
      enterPage(app,route);
    }else if(sameLanguage&&route==='lesson'&&last&&(last.tab!==next.tab||last.question!==next.question)){
      animate(app.querySelector('#lesson-content'),[{opacity:0,transform:'translateY(5px)'},{opacity:1,transform:'none'}],170);
      if(last.tab!==next.tab)enterStudyVisuals(app);
    }
    if(sameLanguage){
      animateCurrentUI(app,old,currentUI);
      for(const el of app.querySelectorAll(selected)){
        if(old.selections.has(key(el)))continue;
        if(el.matches('.lesson-tab,.assist-switch button,.ref-sidebar-nav button,.fc-card'))continue;
        animate(el,[{transform:'scale(.985)'},{transform:'scale(1)'}],190);
        const tick=el.querySelector('.ref-selection,.answer-selection');
        animate(tick,[{opacity:0,transform:'scale(.65)'},{opacity:1,transform:'scale(1)'}],170);
        drawCheck(el);
      }
    }
    if(route==='lesson'&&last&&last.checked!==next.checked){
      const feedback=app.querySelector('.feedback');
      animate(feedback,[{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],210);
      if(feedback)drawCheck(feedback);
    }
    const card=app.querySelector('.flashcard-rotator');
    if(card&&last&&last.route===route&&last.card===next.card&&old.flipped!==next.flipped){
      animate(card,[{transform:old.flipTransform||`rotateY(${old.flipped?180:0}deg)`},{transform:`rotateY(${next.flipped?180:0}deg)`}],320);
      if(next.flipped)animate(app.querySelector('.card-memory-controls'),[{opacity:0,transform:'translateY(4px)'},{opacity:1,transform:'none'}],190);
    }else if(card&&last?.route===route&&last.card!==next.card){
      const direction=next.cardIndex>last.cardIndex?1:-1;
      for(const ghost of document.querySelectorAll('.motion-card-exit')){ghost.getAnimations().forEach(a=>a.cancel());ghost.remove();}
      if(old.cardExit){
        old.cardExit.classList.add('motion-card-exit');old.cardExit.style.zIndex='35';document.body.append(old.cardExit);
        const inner=old.cardExit.querySelector('.flashcard-rotator');if(inner&&old.flipTransform)inner.style.transform=old.flipTransform;
        const out=animate(old.cardExit,[{opacity:1,transform:'none'},{opacity:0,transform:`translateX(${-direction*18}px)`}],140);
        if(out)out.finished.catch(()=>{}).finally(()=>old.cardExit.remove());else old.cardExit.remove();
      }
      animate(app.querySelector('.study-flashcard'),[{opacity:.25,transform:`translateX(${direction*18}px)`},{opacity:1,transform:'none'}],240);
    }
    if(route==='lesson'&&last?.question===next.question&&last.order!==next.order){
      for(const node of app.querySelectorAll('.ordering-item')){const before=old.order[node.dataset.orderItem];if(before){const now=rect(node);animate(node,[{transform:`translateY(${before.top-now.top}px)`},{transform:'none'}],210);}}
    }
    const assist=app.querySelector('.product-assist');
    if(assist&&!old.assist){
      animate(assist,[{opacity:0,transform:'translateY(12px) scale(.985)'},{opacity:1,transform:'none'}],220);
    }else if(assist&&last?.size!==next.size){
      const now=rect(assist),from=old.assist;
      if(from&&now.width&&now.height)animate(assist,[{transform:`translate(${from.left-now.left}px,${from.top-now.top}px) scale(${from.width/now.width},${from.height/now.height})`},{transform:'none'}],240);
    }
    if(assist&&last?.panel!==next.panel){
      animate(assist.querySelector('.assist-content'),[{opacity:0,transform:'translateY(4px)'},{opacity:1,transform:'none'}],150);
    }
    const messages=app.querySelectorAll('.product-assist .message-row');
    if(old.assist&&last?.panel==='chat'&&next.panel==='chat'&&last.chatTail!==next.chatTail){
      for(const message of [...messages].slice(-2))animate(message,[{opacity:0,transform:'translateY(7px)'},{opacity:1,transform:'none'}],190);
    }
    if(c.assistantMenuOpen&&!last?.menu)animate(app.querySelector('.assistant-mode-menu'),[{opacity:0,transform:'translateY(7px) scale(.98)'},{opacity:1,transform:'none'}],170);
    if(last?.route===route&&route==='lesson'&&last.question!==next.question){
      app.querySelectorAll('.thin-progress>span').forEach((bar,i)=>{if(old.bars[i])animate(bar,[{width:old.bars[i]},{width:getComputedStyle(bar).width}],260);});
    }
    if(next.completed&&!last?.completed){animate(app.querySelector('.completion-title'),[{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],220);animate(app.querySelector('.completion'),[{boxShadow:'0 0 0 0 #c5d6ad00'},{boxShadow:'0 0 0 4px #c5d6ad45',offset:.4},{boxShadow:'0 0 0 0 #c5d6ad00'}],450);}
    if(press){const button=[...app.querySelectorAll(controlSelector)].find(x=>key(x)===press.key);pressWave(button,press.point);}
    if(pendingField){const field=[...app.querySelectorAll('select,input[type="checkbox"],input[type="radio"]')].find(x=>key(x)===pendingField);if(field)fieldFeedback(field);pendingField=null;}
    last=next;
  }
  return {beforeRender,afterRender,signal};
})();
