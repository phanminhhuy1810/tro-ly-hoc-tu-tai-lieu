const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness() {
  const handlers = {}, windowHandlers = {}, dialogs = [], h = {focusCount:0};
  const sandbox = {
    window: {addEventListener(name,fn){windowHandlers[name]=fn;}},
    document: {
      addEventListener(name,fn){handlers[name]=fn;},
      body:{append(dialog){dialogs.push(dialog);}},
      createElement(tag){
        assert.equal(tag,'dialog');
        return {attributes:{},events:{},open:false,removed:false,
          setAttribute(name,value){this.attributes[name]=value;},
          addEventListener(name,fn){this.events[name]=fn;},
          showModal(){this.open=true;},close(){this.open=false;},remove(){this.removed=true;},
          querySelector(){return {focus(){h.focusCount++;}};}
        };
      }
    },
    fetch(){throw Error('Opening a badge must never request AI or a reward');}
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.resolve(__dirname,'..','scripts','live-activity.js'),'utf8'),sandbox,{filename:'live-activity.js'});
  const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  h.ctx={state:{uiLanguage:'en',completed:false,cardMemory:{},notebook:[]},D:{cards:[{id:'a'},{id:'b'}]},e:escape,icon:name=>`<svg aria-hidden="true" data-icon="${name}"><path d="M0 0"/></svg>`,route:'missions'};
  h.data={dashboard:{timezone:'UTC',weekly_streak:{longest:2},learning_progress:[{course_id:'course-a',title:'Networks <unsafe>',completed:1,total:3}]},missions:{utc_day:'2026-10-16',daily:[{code:'practice',title:'Practice',progress:0,target:1,coin_awarded:0},{code:'cards',title:'Cards',progress:2,target:5,coin_awarded:0}]},achievements:{earned:[],next:['first_session','study_day_3','study_day_7','five_units']}};
  h.ui=sandbox.window.LIVE_ACTIVITY;
  h.render=()=>h.ui.render(h.ctx,h.data);
  h.click=(id)=>{
    const tile={disabled:false,dataset:{achievement:id},isConnected:true,focus(){h.focusCount++;}};
    handlers.click({target:{closest(selector){return selector==='[data-achievement]'?tile:null;}}});
    return dialogs.at(-1);
  };
  h.close=()=>handlers.click({target:{closest(selector){return selector.includes('[data-achievement-close]')?{}:null;}}});
  h.follow=()=>handlers.click({target:{closest(selector){return selector.includes('[data-achievement-go]')?{}:null;}}});
  return Object.assign(h,{dialogs,windowHandlers});
}

test('pending badges remain inspectable and display actual progress without treating the target as an earned record',()=>{
  const h=harness();h.data.dashboard.weekly_streak.longest=3;
  const before=JSON.stringify(h.data),html=h.render();
  assert.match(html,/button[^>]*data-achievement="study_day_3"[^>]*aria-label="Three days in a row · Not yet earned · 3\/3"/);
  assert.doesNotMatch(html,/data-achievement="study_day_3"[^>]*disabled/);
  const dialog=h.click('study_day_3');
  assert.equal(dialog.open,true);
  assert.equal(dialog.attributes['aria-labelledby'],'achievement-detail-title');
  assert.match(dialog.innerHTML,/Study on three consecutive days/);
  assert.match(dialog.innerHTML,/progress max="3" value="3"/);
  assert.match(dialog.innerHTML,/href="#dashboard"/);
  assert.match(dialog.innerHTML,/opening a badge does not award it again/);
  assert.equal(JSON.stringify(h.data),before,'inspection must not award, complete, or alter activity');
});

test('earned details use the backend record date and retain the achievement after an inactive period',()=>{
  const h=harness();h.data.dashboard.weekly_streak.longest=1;
  h.data.achievements.earned=[{code:'study_day_7',earned_at:'2026-10-15T13:20:00+00:00'}];
  const html=h.render();
  assert.match(html,/aria-label="A full week · Earned · 7\/7"/);
  const dialog=h.click('study_day_7');
  assert.match(dialog.className,/is-earned/);
  assert.match(dialog.innerHTML,/15\/10\/2026/);
  assert.match(dialog.innerHTML,/Activity saved on the server/);
  assert.doesNotMatch(dialog.innerHTML,/Claim|Nhận thưởng|fetch/);
});

test('course achievement actions point to the exact available course and escape imported titles',()=>{
  const h=harness(),html=h.render();
  assert.match(html,/Networks &lt;unsafe&gt;/);
  assert.doesNotMatch(html,/Networks <unsafe>/);
  const dialog=h.click('course_complete:course-a');
  assert.match(dialog.innerHTML,/data-live="open-stat-course" data-course="course-a"/);
  assert.match(dialog.innerHTML,/including lessons that are still outlines/);
  assert.match(dialog.innerHTML,/progress max="3" value="1"/);
  h.follow();assert.equal(dialog.open,false);assert.equal(dialog.removed,true);
});

test('native dialog cancellation restores the opener and route changes remove stale details',()=>{
  const h=harness();h.render();let prevented=false;
  const first=h.click('five_units');
  const initialFocus=h.focusCount;
  first.events.cancel({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);assert.equal(first.open,false);assert.equal(first.removed,true);
  assert.equal(h.focusCount,initialFocus+1,'keyboard cancellation must restore the badge focus');
  const second=h.click('first_session');h.windowHandlers.hashchange();
  assert.equal(second.open,false);assert.equal(second.removed,true);
  h.click('missing-code');assert.equal(h.dialogs.length,2,'unknown badge codes cannot open stale content');
});

test('static milestones are computed from local actions and never invent earned dates or server rewards',()=>{
  const h=harness();h.ctx.state.completed=true;h.ctx.state.cardMemory={a:'known',b:'unknown'};
  const html=h.ui.renderDemo(h.ctx);
  assert.match(html,/aria-label="First practice · Earned · 1\/1"/);
  assert.match(html,/aria-label="Two remembered cards · Not yet earned · 1\/2"/);
  const dialog=h.click('demo-first');
  assert.match(dialog.innerHTML,/Time not recorded/);
  assert.match(dialog.innerHTML,/Prototype data in this browser. No Coin is awarded/);
  assert.match(dialog.innerHTML,/data-action="start-practice"/);
  assert.doesNotMatch(dialog.innerHTML,/Activity saved on the server/);
});
