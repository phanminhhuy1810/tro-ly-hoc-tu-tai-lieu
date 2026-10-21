'use strict';
/* Inline help stays with its question/section. General chat is independent. */
window.LIVE_HELP = {
  create({api,waitJob,redraw,T,E,beforeHelp}) {
    const entries=new Map();let nextId=0;
    const keyOf=t=>t.kind==='question'?`question:${t.sessionId}:${t.itemId}`:`${t.kind==='mindmap'?'mindmap':'section'}:${t.courseId}:${t.revision}:${t.unitId}:${t.index}`;
    function entry(target){const key=keyOf(target);if(!entries.has(key))entries.set(key,{key,target,id:++nextId,opened:false,busy:false,draft:'',savedDraft:'',version:0,dirty:false});return entries.get(key);}
    const button=(x,action,label)=>`<button type="button" class="secondary" data-inline-action="${action}" data-inline-key="${E(x.key)}" ${x.busy&&!['close','open','cancel-job'].includes(action)?'disabled':''}>${label}</button>`;
    function reference(value,context){
      const q=context?.question;
      if(!Array.isArray(value))return String(value);
      return value.map((j,i)=>q?.kind==='matching'?`${q.left[i]} → ${q.options[j]}`:q?.options[j]??j).join(' → ');
    }
    function message(m,context,x){
      const v=m.content,q=context?.question;
      return `<article class="live-inline-message ${m.role}"><small>${m.role==='user'?T('Bạn','You'):T(v.ai_generated?'AI · theo câu/đoạn này':'Trợ giúp đã lưu',v.ai_generated?'AI · this question/section':'Saved assistance')}</small><p class="live-text">${E(v.text||'')}</p>${v.reference_warning?`<p class="live-notice">${T('Đáp án tham khảo đang cần xem lại.','The reference answer is under review.')}</p>`:''}${v.reference!==undefined?`<p><strong>${T('Tham khảo','Reference')}:</strong> ${E(reference(v.reference,context))}</p>`:''}${v.eliminated_option_ids?`<p>${T('Có thể loại','Can eliminate')}: ${v.eliminated_option_ids.map(id=>E(q?.payload?.options.find(o=>o.id===id)?.text||q?.options[Number(id.split('-')[1])]||id)).join(' · ')}</p>`:''}${v.prefix?`<p>${T('Bắt đầu bằng','Starts with')}: <strong>${E(v.prefix)}</strong>…</p>`:''}${v.ordered_option_ids?`<ol>${v.ordered_option_ids.map(id=>`<li>${E(q?.options[Number(id.split('-')[1])]||id)}</li>`).join('')}</ol>`:''}${v.pairs?`<ul>${Object.entries(v.pairs).map(([left,right])=>`<li>${E(q?.left[Number(left.split('-')[1])])} → ${E(q?.options[Number(right.split('-')[1])])}</li>`).join('')}</ul>`:''}${(v.criteria||v.rubric)?.length?`<ul>${(v.criteria||v.rubric).map(text=>`<li>${E(text)}</li>`).join('')}</ul>`:''}${m.role==='assistant'?button(x,'save-note:'+m.id,T('Lưu vào sổ tay','Save to notebook')):''}</article>`;
    }
    function render(target){
      const x=entry(target),question=target.kind==='question',mindmap=target.kind==='mindmap';
      const toolbar=question?button(x,'hint',T('Gợi ý','Hint'))+button(x,'reveal',T('Hiện đáp án','Reveal answer'))+button(x,'explain',T('Giải thích','Explain')):button(x,'explain',T(mindmap?'Giải thích ý này':'Giải thích đoạn này',mindmap?'Explain this idea':'Explain this section'));
      return `<section class="live-inline-help"><div class="live-inline-actions">${toolbar}${button(x,'open',T('Hỏi tiếp','Ask a question'))}</div>${x.opened?`<div class="live-inline-content"><header><strong>${T(question?'Trợ giúp cho câu này':mindmap?'Trợ giúp cho ý mindmap này':'Trợ giúp cho đoạn này',question?'Help for this question':mindmap?'Help for this mindmap idea':'Help for this section')}</strong>${button(x,'close',T('Thu gọn','Collapse'))}</header>${x.snapshot?.reference_warning?`<p class="live-notice">${E(x.snapshot.reference_warning.reason)}</p>`:''}${x.snapshot?.messages.map(m=>message(m,x.snapshot.context,x)).join('')||`<p>${T('Bạn muốn hỏi gì về phần này?','What would you like to ask about this part?')}</p>`}${x.snapshot?.source_excerpts?.length?`<details class="live-inline-sources"><summary>${T('Đối chiếu nguồn của phần này','Sources for this part')}</summary>${x.snapshot.source_excerpts.map(f=>`<p class="live-text"><strong>${E(Object.entries(f.locator||{}).map(([k,v])=>k+': '+v).join(' · '))}</strong><br>${E(f.text)}</p>`).join('')}</details>`:''}${x.busy?`<div class="live-inline-message assistant"><small>${T('AI đang soạn · chưa kiểm tra nguồn','AI draft · sources not yet checked')}</small><p class="live-text" data-inline-stream="${x.id}">${E(x.progress?.preview?.text||T('Đang đọc câu hỏi…','Reading your question…'))}</p>${x.jobId?button(x,'cancel-job',T('Dừng lượt này','Stop this request')):''}</div>`:''}${x.jobId&&!x.busy?button(x,'check-job',T('Đọc lại trạng thái','Check status')):''}${x.error?`<p role="alert" class="live-error">${E(x.error)}</p>`:''}<div class="live-inline-actions">${button(x,'simpler',T('Dễ hiểu hơn','Simpler'))}${button(x,'detail',T('Thêm chi tiết','More detail'))}${question?button(x,'save-card',T('Lưu câu khó thành thẻ','Save question as card')):''}</div>${x.notice?`<p role="status">${E(x.notice)}</p>`:''}<form data-inline-form="${E(x.key)}"><label for="inline-input-${x.id}">${T('Hỏi tiếp về phần này','Ask about this part')}<textarea id="inline-input-${x.id}" data-inline-input="${E(x.key)}" rows="3" maxlength="2000" required>${E(x.draft)}</textarea></label><button class="primary" ${x.busy?'disabled':''}>${T('Gửi câu hỏi','Send question')}</button></form></div>`:''}</section>`;
    }
    async function load(x){
      if(!x.threadId){const t=x.target;const path=t.kind==='question'?`/sessions/${t.sessionId}/items/${t.itemId}/help`:`/courses/${t.courseId}/units/${t.unitId}/${t.kind==='mindmap'?'mindmap':'sections'}/${t.index}/help`;const value=await api(path,t.kind==='question'?{}:{expected_revision:t.revision});x.threadId=value.thread_id;}
      x.snapshot=await api('/help/threads/'+x.threadId);
      if(!x.dirty){x.draft=x.savedDraft=x.snapshot.draft.text;x.version=x.snapshot.draft.version;}
    }
    function flush(x){
      clearTimeout(x.timer);
      x.saveChain=(x.saveChain||Promise.resolve()).catch(()=>{}).then(async()=>{
        if(!x.threadId||x.draft===x.savedDraft)return;
        const text=x.draft;
        const result=await api('/help/threads/'+x.threadId+'/draft',{text,expected_version:x.version},'PUT');
        x.version=result.version;x.savedDraft=text;x.dirty=x.draft!==text;
      });
      return x.saveChain;
    }
    async function watch(x,id){
      x.jobId=id;redraw();
      try{
        await waitJob({job_id:id},'inline_help',value=>{
          x.progress=value.progress;
          const node=document.querySelector('[data-inline-stream="'+x.id+'"]');
          if(node)node.textContent=value.progress?.preview?.text||T('Đang kiểm tra câu trả lời…','Checking the response…');
        });
        x.jobId=null;
      }catch(error){if(!error.jobRetained)x.jobId=null;throw error;}
      finally{x.progress=null;}
      await load(x);
    }
    async function run(x,action,text=''){
      if(action==='cancel-job'&&x.jobId){try{await api('/jobs/'+x.jobId+'/cancel',{});}catch(error){x.error=error.message;redraw();}return;}
      if(action==='close'){x.opened=false;redraw();return;}
      if(x.busy){if(action==='open'){x.opened=true;redraw();}return;}x.opened=true;x.error='';x.notice='';
      x.busy=true;
      try{
        await beforeHelp?.(x.target);redraw();await load(x);
        const pending=x.jobId||x.snapshot.pending_jobs?.[0];
        if(pending&&!action.startsWith('save-')){await watch(x,pending);return;}
        if(action.startsWith('save-note:')){await api('/help/threads/'+x.threadId+'/notebook',{message_id:action.slice(10)});x.notice=T('Đã lưu lời trợ giúp vào sổ tay riêng.','Assistance saved to your private notebook.');}
        else if(action==='save-card'){await api('/cards/from-question',{session_id:x.target.sessionId,item_id:x.target.itemId});window.FLASHCARD_UI?.invalidate();x.notice=T('Đã lưu vào thẻ cá nhân.','Saved to your personal cards.');}
        else if(action!=='open'){
          await flush(x);
          const result=await api('/help/threads/'+x.threadId+'/actions',{action,message:text});
          if(result.job_id)await watch(x,result.job_id);
          await load(x);
        }
      }catch(error){x.error=error.message;}
      finally{x.busy=false;redraw();}
    }
    document.addEventListener('click',event=>{const b=event.target.closest('[data-inline-action]');if(!b||b.disabled)return;const x=entries.get(b.dataset.inlineKey);if(x)run(x,b.dataset.inlineAction);});
    document.addEventListener('input',event=>{
      const key=event.target.dataset.inlineInput;if(!key)return;const x=entries.get(key);if(!x)return;
      x.draft=event.target.value;x.dirty=true;clearTimeout(x.timer);
      x.timer=setTimeout(()=>flush(x).catch(error=>{x.error=error.message;}),500);
    });
    document.addEventListener('submit',event=>{const key=event.target.dataset.inlineForm;if(!key)return;event.preventDefault();const x=entries.get(key);if(x?.draft.trim())run(x,'ask',x.draft.trim());});
    return {render};
  }
};
