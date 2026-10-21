'use strict';
/* Read-only search/paging. Selection remains a revision-bound preferences draft. */
window.SOURCE_BROWSER=(()=>{
  const clean=value=>String(value??'').trim().replace(/\s+/g,' ');
  const queryString=value=>new URLSearchParams(Object.entries(value).filter(([,v])=>v!==null&&v!==undefined&&v!=='')).toString();

  function mergeVisible(allIds,selected,visible,checked){
    const valid=new Set(allIds),result=new Set((selected||[]).filter(id=>valid.has(id))),on=new Set(checked);
    for(const id of visible)if(valid.has(id)){if(on.has(id))result.add(id);else result.delete(id);}
    return allIds.filter(id=>result.has(id));
  }

  function createLibrary({api,changed=()=>{},saved={}}){
    const state={query:clean(saved.query),draft:String(saved.draft??saved.query??''),
      currentCursor:typeof saved.currentCursor==='string'?saved.currentCursor:null,
      back:Array.isArray(saved.back)?saved.back.filter(v=>typeof v==='string'):[],page:Math.max(1,Math.floor(Number(saved.page)||1)),
      items:[],total:0,libraryTotal:0,nextCursor:null,loaded:false,loading:false,error:'',invalidated:false};
    let serial=0,pending;
    function exportState(){return {query:state.query,draft:state.draft,currentCursor:state.currentCursor,back:state.back,page:state.page};}
    async function load({query=state.query,cursor=state.currentCursor,back=state.back,page=state.page}={}){
      const request=++serial;state.loading=true;state.error='';changed();
      try{
        const value=await api('/source-library?'+queryString({q:query,cursor,limit:20}));
        if(request!==serial)return false;
        Object.assign(state,{query:value.query,items:value.items,total:value.total,libraryTotal:value.library_total,
          currentCursor:value.current_cursor,nextCursor:value.next_cursor,back:[...back],page,loaded:true,loading:false,invalidated:false});
        changed();return true;
      }catch(error){if(request===serial){state.error=error.message;state.loading=false;changed();}return false;}
    }
    function run(options){pending=load(options);return pending;}
    return {state,exportState,
      setDraft(value){state.draft=String(value);},
      search(value=state.draft){state.draft=String(value);return run({query:clean(value),cursor:null,back:[],page:1});},
      refresh(){if(state.loading)return pending;return run(state.invalidated?{cursor:null,back:[],page:1}:{});},
      reload(){return run({cursor:null,back:[],page:1});},
      invalidate(){state.invalidated=true;},
      next(){if(!state.loading&&state.nextCursor)return run({cursor:state.nextCursor,back:[...state.back,state.currentCursor],page:state.page+1});return Promise.resolve(false);},
      previous(){if(!state.loading&&state.back.length)return run({cursor:state.back.at(-1),back:state.back.slice(0,-1),page:Math.max(1,state.page-1)});return Promise.resolve(false);}
    };
  }

  function normalFilters(value){
    const kind=['page','slide','frame','line','paragraph'].includes(value.location_kind)?value.location_kind:'';
    const position=value.position===''||value.position===null||value.position===undefined?null:Number(value.position);
    if(position!==null&&(!Number.isInteger(position)||position<1||position>1000000))throw Error('Vị trí phải là số nguyên dương.');
    return {q:clean(value.q),location_kind:kind,position,component_id:String(value.component_id||'')};
  }
  const sameFilters=(a,b)=>JSON.stringify(normalFilters(a))===JSON.stringify(normalFilters(b));

  function createScope({api,changed=()=>{},saved={}}){
    const state={sourceId:null,revision:null,draft:{q:'',location_kind:'',position:'',component_id:''},
      filters:{q:'',location_kind:'',position:null,component_id:''},offset:0,items:[],total:0,
      loaded:false,loading:false,error:'',latestRevision:null,reviewed:false,open:false};
    let serial=0;
    function exportState(){return {sourceId:state.sourceId,revision:state.revision,draft:{...state.draft},filters:{...state.filters},offset:state.offset,open:state.open};}
    function bind(source){
      if(state.sourceId===source.id&&state.revision===source.revision)return false;
      ++serial;
      const restore=saved.sourceId===source.id&&saved.revision===source.revision?saved:{};
      let filters;try{filters=normalFilters(restore.filters||{});}catch(_){filters=normalFilters({});}
      Object.assign(state,{sourceId:source.id,revision:source.revision,filters,
        draft:{q:filters.q,location_kind:filters.location_kind,position:filters.position??'',component_id:filters.component_id,...restore.draft},
        offset:Math.max(0,Math.min(1980,Math.floor((Number(restore.offset)||0)/20)*20)),items:[],total:0,loaded:false,loading:false,error:'',
        latestRevision:source.revision,reviewed:source.reviewed,open:!!restore.open});
      return true;
    }
    async function load(filters=state.filters,offset=state.offset){
      let normalized;
      try{normalized=normalFilters(filters);}catch(error){state.error=error.message;changed();return false;}
      const request=++serial,sourceId=state.sourceId,revision=state.revision;
      if(!sourceId)return false;
      state.loading=true;state.error='';changed();
      try{
        const value=await api('/sources/'+sourceId+'/fragments?'+queryString({revision,...normalized,offset,limit:20}));
        if(request!==serial||state.sourceId!==sourceId||state.revision!==revision)return false;
        Object.assign(state,{filters:normalized,offset,items:value.items,total:value.matched_fragments,
          latestRevision:value.latest_revision,reviewed:value.reviewed,loading:false,loaded:true});
        changed();return true;
      }catch(error){if(request===serial){state.error=error.message;state.loading=false;changed();}return false;}
    }
    function dirty(){try{return !sameFilters(state.draft,state.filters);}catch(_){return true;}}
    async function select(current,mode){
      if(state.loading||dirty()||!state.loaded)throw Error('Tìm trích đoạn trước khi chọn kết quả.');
      const request=serial,sourceId=state.sourceId,revision=state.revision;
      const value=await api('/sources/'+sourceId+'/fragment-selection?'+queryString({revision,...state.filters}));
      if(request!==serial||sourceId!==state.sourceId||revision!==state.revision)return null;
      state.latestRevision=value.latest_revision;
      if(value.latest_revision!==revision){state.error='Bản trích đã thay đổi. Tải lại nguồn trước khi chọn phạm vi.';changed();return null;}
      return mode==='replace'?[...value.fragment_ids]:[...new Set([...current,...value.fragment_ids])];
    }
    return {state,exportState,bind,load,dirty,select,
      setDraft(key,value){if(Object.hasOwn(state.draft,key))state.draft[key]=value;},
      search(){return load(state.draft,0);},
      clear(){state.draft={q:'',location_kind:'',position:'',component_id:''};return load(state.draft,0);},
      next(){return !state.loading&&state.offset+state.items.length<state.total?load(state.filters,state.offset+20):Promise.resolve(false);},
      previous(){return !state.loading&&state.offset?load(state.filters,Math.max(0,state.offset-20)):Promise.resolve(false);}
    };
  }

  function scopePanel({controller,source,selected,T,E,B,locationText}){
    const v=controller.state,selectedSet=new Set(selected),stale=v.latestRevision!==source.revision;
    const filterDirty=controller.dirty(),cantSelect=v.loading||filterDirty||!v.loaded||!v.total||stale;
    const disabled=value=>value?'disabled':'';
    return `<details class="live-source-scope" data-scope-panel ${v.open?'open':''}><summary>${T('Phạm vi khóa học','Course scope')} · <span data-scope-count>${selected.length}/${source.fragments.length}</span> ${T('đoạn được chọn','excerpts selected')}</summary>
      <p>${T('Tìm đoạn rồi tick hoặc chọn kết quả. Các lựa chọn được giữ khi đổi trang hoặc đổi từ khóa.','Find excerpts, then tick or select matching results. Choices are retained across pages and searches.')}</p>
      <div class="live-source-filters" role="group" aria-label="${T('Tìm trích đoạn','Find excerpts')}">
        <label>${T('Từ khóa trong nguồn','Keywords in source')}<input type="search" data-scope-field="q" value="${E(v.draft.q)}" maxlength="120" placeholder="${T('Ví dụ: subnet, địa chỉ…','Example: subnet, address…')}"></label>
        <label>${T('Loại vị trí','Location type')}<select data-scope-field="location_kind">${[['','Bất kỳ','Any'],['page','Trang','Page'],['slide','Slide','Slide'],['frame','Khung ảnh','Image frame'],['line','Dòng','Line'],['paragraph','Đoạn Word','Word paragraph']].map(([id,vi,en])=>`<option value="${id}" ${v.draft.location_kind===id?'selected':''}>${T(vi,en)}</option>`).join('')}</select></label>
        <label>${T('Vị trí (tùy chọn)','Position (optional)')}<input type="number" data-scope-field="position" value="${E(v.draft.position)}" min="1" max="1000000"></label>
        ${source.metadata.components?`<label>${T('Tài liệu trong bộ','Document in collection')}<select data-scope-field="component_id"><option value="">${T('Tất cả tài liệu','All documents')}</option>${source.metadata.components.map(c=>`<option value="${E(c.source_id)}" ${v.draft.component_id===c.source_id?'selected':''}>${E(c.name)}</option>`).join('')}</select></label>`:''}
      </div>
      <div class="live-source-actions">${B('scope-search',T('Tìm trích đoạn','Find excerpts'),disabled(v.loading))}${B('scope-clear',T('Xem toàn bộ','Show all'),disabled(v.loading))}</div>
      ${v.error?`<p role="alert" class="live-error">${E(v.error)}</p>`:''}
      ${stale?`<p role="alert" class="live-notice">${T('Nguồn có bản trích mới. Tải lại trang để chọn lại phạm vi; nhu cầu đang nhập vẫn được giữ.','A newer extraction is available. Reload to choose its scope; your preferences draft is retained.')} <a href="#live" onclick="location.reload()">${T('Tải lại','Reload')}</a></p>`:''}
      <p role="status">${v.loading?T('Đang tìm…','Searching…'):v.loaded?`${v.total} ${T('đoạn phù hợp','matching excerpts')}`:T('Đang mở bản trích…','Opening excerpts…')}</p>
      <div class="live-source-actions">${B('scope-replace',T('Chỉ học kết quả này','Use only these results'),disabled(cantSelect))}${B('scope-add',T('Thêm kết quả vào phạm vi','Add results to scope'),disabled(cantSelect))}${B('scope-none',T('Bỏ chọn tất cả','Deselect all'))}</div>
      <nav aria-label="${T('Trang kết quả trích đoạn','Excerpt result pages')}">${B('scope-previous',T('Trước','Previous'),disabled(v.loading||!v.offset))} <span>${v.total?`${v.offset+1}–${Math.min(v.total,v.offset+v.items.length)}/${v.total}`:'0/0'}</span> ${B('scope-next',T('Tiếp','Next'),disabled(v.loading||v.offset+v.items.length>=v.total))}</nav>
      <fieldset aria-label="${T('Chọn trích đoạn','Select excerpts')}">${v.items.map(f=>`<section class="live-scope-fragment"><label class="live-source-choice"><input type="checkbox" name="fragment_ids" value="${E(f.id)}" ${selectedSet.has(f.id)?'checked':''}><span><strong>${E(locationText(f.locator))}</strong><br>${E(f.snippet)}</span></label><details><summary>${T('Đọc cả đoạn','Read full excerpt')}</summary><p class="live-text">${E(f.text)}</p></details></section>`).join('')}</fieldset>
    </details>`;
  }
  return {createLibrary,createScope,mergeVisible,scopePanel};
})();
