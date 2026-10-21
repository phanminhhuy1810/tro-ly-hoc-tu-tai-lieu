'use strict';
/* Observe an accepted job. This module never submits or retries AI work. */
(function(root){
  function observe(jobId,{api,onUpdate=()=>{},EventSourceClass=root.EventSource,timeoutMs=210000,pollMs=1200}={}){
    return new Promise((resolve,reject)=>{
      let stream=null,timer=null,done=false,polling=false,fallback=!EventSourceClass,lastVersion=-1,lastStatus='',lastDeferred=false;
      const error=(message,code)=>Object.assign(new Error(message),{code,jobId,jobRetained:true});
      const close=()=>{stream?.close();clearTimeout(timer);clearTimeout(deadline);};
      const fail=e=>{if(done)return;done=true;close();e.jobId=jobId;e.jobRetained=true;reject(e);};
      const accept=value=>{
        if(done||value.id!==jobId)return;
        const version=value.progress?.version??0;
        if(version<lastVersion)return;
        if(version!==lastVersion||value.status!==lastStatus||!!value.feedback_deferred!==lastDeferred){
          lastVersion=version;lastStatus=value.status;lastDeferred=!!value.feedback_deferred;
          onUpdate(value);
        }
        if(value.feedback_deferred){fail(error('Kết thúc hoặc hủy lượt kiểm tra trước khi xem phản hồi AI.','FEEDBACK_DEFERRED'));return;}
        if(['succeeded','failed','cancelled'].includes(value.status)){done=true;close();resolve(value);}
      };
      const poll=async()=>{
        if(done||polling)return;polling=true;
        try{accept(await api('/jobs/'+jobId));}
        catch(e){fail(e);}
        finally{polling=false;if(!done&&fallback)timer=setTimeout(poll,pollMs);}
      };
      const deadline=setTimeout(()=>fail(error('Job vẫn ở server. Đọc lại trạng thái để tiếp tục theo dõi; chưa gửi lại AI.','OBSERVATION_TIMEOUT')),timeoutMs);
      if(EventSourceClass){
        try{
          stream=new EventSourceClass('/api/jobs/'+encodeURIComponent(jobId)+'/events');
          stream.addEventListener('snapshot',event=>{try{accept(JSON.parse(event.data));}catch(e){fail(e);}});
          stream.addEventListener('session_expired',()=>fail(error('Phiên đã hết hạn; job và phần đã lưu vẫn ở server.','SESSION_EXPIRED')));
          stream.addEventListener('access_changed',()=>fail(error('Chưa truy cập được job; dữ liệu vẫn được giữ.','ACCESS_CHANGED')));
          stream.onerror=()=>{stream?.close();fallback=true;clearTimeout(timer);if(!done)poll();};
        }catch(_){fallback=true;}
      }
      poll();
    });
  }
  root.LIVE_JOBS={observe};
  if(typeof module==='object'&&module.exports)module.exports={observe};
})(globalThis);
