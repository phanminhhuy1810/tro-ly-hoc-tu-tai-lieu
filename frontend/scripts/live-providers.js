'use strict';
/* Small control for the backend model catalogue; contains no provider key. */
window.LIVE_MODELS = (() => {
  let host, request, active=false, catalog=null, loading=false, saving=false, error='', notice='', pending='', externalConsentFor='';
  const E=x=>String(x??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  let language='vi';
  const T=(vi,en)=>language==='en'?en:vi;
  async function load(){
    if(!active||loading)return;
    loading=true;
    try{catalog=await request('/ai/models');error='';if(!pending)pending=catalog.selected_model_id;}
    catch(e){error=e.message;}
    finally{loading=false;if(location.hash==='#settings')host.render();}
  }
  function panel(c){
    language=c.state.uiLanguage;
    if(!active)return `<span class="fixture-label">${T('Chưa kết nối backend','Backend not connected')}</span>`;
    if(!catalog&&!loading&&!error)load();
    if(!catalog)return `<div class="ai-model-settings"><p role="status">${E(error||T('Đang kiểm tra model…','Checking models…'))}</p><button type="button" class="secondary" data-ai-refresh>${T('Kiểm tra lại','Refresh')}</button></div>`;
    const model=catalog.models.find(m=>m.id===(pending||catalog.selected_model_id));
    return `<form id="ai-model-selection" class="ai-model-settings"><label>${T('Model dùng cho lượt AI tiếp theo','Model for the next AI request')}<select id="ai-model-id" name="model_id" ${saving||loading?'disabled':''}>${!catalog.models.some(m=>m.id===catalog.selected_model_id)?`<option value="${E(catalog.selected_model_id)}">${T('Model cũ không còn cấu hình','Previous model is no longer configured')}</option>`:''}${catalog.models.map(m=>`<option value="${E(m.id)}" ${m.id===(pending||catalog.selected_model_id)?'selected':''} ${!m.selectable&&m.id!==catalog.selected_model_id?'disabled':''}>${E(m.label)}${!m.selectable?' · '+T('chưa sẵn sàng','unavailable'):''}</option>`).join('')}</select></label><p>${model?.external?T('Trích đoạn được gửi tới nguồn AI ngoài máy. File gốc và lịch sử vẫn lưu ở backend của nhóm.','Selected excerpts go to an external AI provider. Originals and history stay on the group backend.'):T('AI chạy trên máy đang phục vụ ứng dụng.','AI runs on the machine serving this app.')}</p>${model?.provider==='gemini_api'?`<p>${T('Dùng key của nhóm. Hạn mức Gemini tách biệt Coin; không tự mua hoặc bật billing.','Uses the group’s key. Gemini limits are separate from Coin; billing is never enabled automatically.')}</p>`:''}${model?.external?`<label><input type="checkbox" name="allow_external" required ${externalConsentFor===model.id?'checked':''} ${saving?'disabled':''}> ${T('Đồng ý gửi trích đoạn đã chọn tới nguồn AI này','Allow selected excerpts to be sent to this provider')}</label>`:''}<div class="dialog-actions"><button class="primary" ${saving||loading||!pending||pending===catalog.selected_model_id||!model?.selectable?'disabled':''}>${saving?T('Đang lưu…','Saving…'):T('Dùng model này','Use this model')}</button><button type="button" class="secondary" data-ai-refresh ${saving||loading?'disabled':''}>${T('Kiểm tra lại','Refresh')}</button></div><p role="status">${E(error||notice||T('Đổi model giữ nguyên khóa học và lịch sử. Job đang chạy tiếp tục với model ban đầu.','Switching preserves courses and history. Running jobs keep their original model.'))}</p></form>`;
  }
  document.addEventListener('change',event=>{
    if(event.target.name==='allow_external'&&event.target.closest('#ai-model-selection')){
      externalConsentFor=event.target.checked?pending:'';return;
    }
    if(event.target.id!=='ai-model-id')return;
    externalConsentFor='';pending=event.target.value;error=notice='';host.render();
    document.getElementById('ai-model-id')?.focus();
  });
  document.addEventListener('click',event=>{
    if(event.target.closest('[data-ai-refresh]')){event.preventDefault();load();}
  });
  document.addEventListener('submit',async event=>{
    if(event.target.id!=='ai-model-selection')return;
    event.preventDefault();if(saving||loading||!pending||pending===catalog.selected_model_id)return;
    const body={model_id:pending,expected_revision:catalog.selection_revision,allow_external:new FormData(event.target).get('allow_external')==='on'};
    saving=true;error=notice='';host.render();
    try{const result=await request('/ai/selection',body,'PUT');host.modelChanged();catalog.selected_model_id=result.model_id;catalog.selection_revision=result.revision;pending=result.model_id;notice=T('Đã lưu model cho những lượt AI tiếp theo.','Model saved for subsequent AI requests.');}
    catch(e){error=e.message;}
    finally{saving=false;host.render();}
  });
  window.addEventListener('hashchange',()=>{if(active&&location.hash==='#settings'){externalConsentFor='';pending='';load();}});
  return {panel,init(options){host=options;request=options.api;active=true;if(location.hash==='#settings')load();}};
})();
