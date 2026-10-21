'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

// The production render hooks see old/new DOM, not application model internals.
// This small DOM double keeps those observations explicit and records only
// Web Animation calls, so background renders and preference cancellation matter.
function harness(){
  const handlers={},animations=[],microtasks=[];
  const media={matches:false,addEventListener(_,fn){this.change=fn;}};
  class Element{
    constructor(tag='DIV',options={}){Object.assign(this,{tagName:tag,dataset:{},id:'',className:'',textContent:'',children:[],style:{},attrs:{},clientWidth:100,clientHeight:40,open:false},options);this.classList={add:(name)=>{this.className+=' '+name;},contains:name=>this.className.split(' ').includes(name)};}
    getAttribute(name){return this.attrs[name]??null;}
    setAttribute(name,value){this.attrs[name]=value;}
    removeAttribute(name){delete this.attrs[name];}
    getBoundingClientRect(){return {left:0,top:this.top||0,width:100,height:40};}
    closest(selector){if(selector==='[inert]')return null;if(selector==='label')return this.label||null;if(selector==='form')return this.form||null;return this;}
    matches(selector){
      if(selector==='details')return this.tagName==='DETAILS';
      if(selector==='select')return this.tagName==='SELECT';
      if(selector==='.fc-card,.study-flashcard')return /\b(fc-card|study-flashcard)\b/.test(this.className);
      if(selector.includes('checkbox'))return this.tagName==='SELECT'||this.tagName==='INPUT'&&['checkbox','radio'].includes(this.type);
      if(selector.includes('button:not(:disabled)'))return ['BUTTON','A','SUMMARY'].includes(this.tagName)||this.attrs.role==='button';
      return false;
    }
    querySelector(selector){return this.nodes?.[selector]||null;}
    querySelectorAll(selector){if(selector==='.motion-press-wave')return this.children.filter(x=>x.className==='motion-press-wave');return [];}
    append(el){this.children.push(el);el.parent=this;}
    remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
    animate(frames,options){let resolve;const animation={target:this,frames,options,cancelled:false,finished:new Promise(yes=>resolve=yes),cancel(){this.cancelled=true;resolve();}};animations.push(animation);return animation;}
  }
  const document={documentElement:{dataset:{}},body:new Element(),createElement:tag=>new Element(tag.toUpperCase()),querySelector:()=>null,querySelectorAll:()=>[],addEventListener(type,fn,capture){(handlers[type]??=[]).push({fn,capture});}};
  const sandbox={window:{},document,matchMedia:()=>media,getComputedStyle:el=>({width:el.width||'0px',transform:'none'}),queueMicrotask:fn=>microtasks.push(fn),CSS:{escape:x=>x},Map,Set};
  vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../scripts/motion.js'),'utf8'),sandbox);
  const c={route:'flashcards',panelOpen:false,assistantMenuOpen:false,state:{motionPreference:'system',answers:{},chat:[],uiLanguage:'en'}};
  const app={view:{},querySelector(selector){return this.view[selector]||null;},querySelectorAll(selector){return this.view[selector]||[];}};
  function card(id,flipped=false,width='0px'){
    const face=new Element('BUTTON',{className:'fc-card'+(flipped?' is-flipped':''),attrs:{'aria-pressed':String(flipped)},dataset:{fc:'flip'}}),study=new Element('DIV',{dataset:{card:id},nodes:{'.fc-card':face}}),progress=new Element('SPAN',{width});
    return {'.fc-shell':new Element(),'.fc-study':study,'.fc-card':face,'.fc-track>span':progress,'.fc-response':new Element()};
  }
  function render(view){const old=sandbox.window.STUDY_MOTION.beforeRender(app,c);app.view={'#main h1':new Element('H1',{textContent:'Networks'}),...view};sandbox.window.STUDY_MOTION.afterRender(app,c,old);}
  function event(type,target,more={}){const e={target,detail:1,clientX:30,clientY:20,...more};for(const h of handlers[type]||[])h.fn(e);}
  return {Element,animations,document,c,media,app,render,card,event,handlers,microtasks};
}

test('current Flashcards animate real flips, card advances and summary once; background renders do not replay them',()=>{
  const h=harness();let view=h.card('card-1');h.render(view);assert.equal(h.animations.filter(a=>a.target===view['.fc-card']).length,1);
  view=h.card('card-1');h.render(view);assert.equal(h.animations.filter(a=>a.target===view['.fc-card']).length,0,'save/poll rerender must remain still');
  view=h.card('card-1',true);h.render(view);const flip=h.animations.find(a=>a.target===view['.fc-card']);assert.match(flip.frames[0].transform,/rotateY\(-64deg\)/);
  view=h.card('card-1',true);h.render(view);assert.equal(h.animations.filter(a=>a.target===view['.fc-card']).length,0,'an already revealed card does not flip on incoming help');
  view=h.card('card-2',false,'50px');h.render(view);assert.match(h.animations.find(a=>a.target===view['.fc-card']).frames[0].transform,/translateX/);assert.equal(h.animations.filter(a=>a.target===view['.fc-track>span']).length,1);
  const summary=new h.Element(),icon=new h.Element();h.render({'.fc-shell':new h.Element(),'.fc-summary':summary,'.fc-summary-icon':icon});assert.equal(h.animations.filter(a=>a.target===summary).length,1);assert.equal(h.animations.filter(a=>a.target===icon).length,1);
  const sameSummary=new h.Element();h.render({'.fc-shell':new h.Element(),'.fc-summary':sameSummary});assert.equal(h.animations.filter(a=>a.target===sameSummary).length,0);
});

test('native data-fc, data-live, inline, Coin, text/icon buttons, links and disclosures get feedback without synthetic actions',()=>{
  const h=harness();
  for(const options of [{dataset:{fc:'help'}},{dataset:{live:'history'}},{dataset:{inlineAction:'hint',inlineKey:'q:1'}},{dataset:{coinConfirm:''}},{className:'text-button'},{className:'icon-button'}]){
    const el=new h.Element('BUTTON',options);let intercepted=false;h.event('click',el,{preventDefault(){intercepted=true;}});assert.equal(el.children.length,1);assert.equal(intercepted,false);
  }
  for(const tag of ['A','SUMMARY']){const el=new h.Element(tag,{attrs:tag==='A'?{href:'#library'}:{}});h.event('click',el);assert.equal(el.children.length,1);}
  assert.equal(h.handlers.click[0].capture,true,'capture runs before data-fc handlers replace the rendered button');
  const activeCard=new h.Element('BUTTON',{className:'fc-card',dataset:{fc:'flip'}});h.event('click',activeCard);assert.equal(activeCard.children.length,0,'card uses its flip instead of a clipped ink overlay');
});

test('motion off and reduced-motion cancel running Web Animations and prevent new movement',()=>{
  for(const preference of ['off','reduced']){
    const h=harness(),first=h.card('one');h.render(first);assert.ok(h.animations.length);
    if(preference==='off')h.c.state.motionPreference='off';else {h.media.matches=true;h.media.change();}
    h.render(h.card('one',true));assert.ok(h.animations.every(a=>a.cancelled));assert.equal(h.document.documentElement.dataset.motion,'off');
    const before=h.animations.length;h.event('click',new h.Element('BUTTON',{dataset:{live:'ask'}}));h.render(h.card('two'));assert.equal(h.animations.length,before);
  }
});

test('open sections survive a same-context background render without replaying the disclosure entrance',()=>{
  const h=harness(),old=new h.Element('DETAILS',{open:true,className:'fc-browse',textContent:'Browse cards'});h.render({details:[old]});
  const replacement=new h.Element('DETAILS',{open:false,className:'fc-browse',textContent:'Browse cards'});h.render({details:[replacement]});assert.equal(replacement.open,true);
  const content=new h.Element();replacement.children.push(new h.Element('SUMMARY'),content);const count=h.animations.length;h.event('toggle',replacement);assert.equal(h.animations.length,count,'restoring open state is not an actual user expansion');
  replacement.open=false;h.event('toggle',replacement);replacement.open=true;h.event('toggle',replacement);assert.equal(h.animations.filter(a=>a.target===content).length,1,'user reopening still animates once');
});

test('checkbox and select feedback keeps native values and does not dispatch duplicate input',()=>{
  const h=harness(),label=new h.Element('LABEL'),check=new h.Element('INPUT',{id:'shuffle',type:'checkbox',checked:true,label}),select=new h.Element('SELECT',{id:'scope',value:'unknown'});
  h.event('change',check);h.event('change',select);assert.equal(check.checked,true);assert.equal(select.value,'unknown');assert.equal(h.animations.filter(a=>a.target===label).length,1);assert.equal(h.animations.filter(a=>a.target===select).length,1);
});
