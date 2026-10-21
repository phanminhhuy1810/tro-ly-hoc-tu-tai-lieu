const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const settle = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); };
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; }
function harness({failLoad = false, memoryGate, failMemory = false} = {}) {
  const handlers = {}, storage = new Map(), calls = [], h = {lastHTML: '', redraws: 0};
  const sandbox = {
    window: {}, document: {addEventListener(name, callback) { handlers[name] = callback; }, querySelector() { return null; }},
    localStorage: {getItem(key) { return storage.get(key) || null; }, setItem(key, value) { storage.set(key, value); }},
    crypto: {randomUUID: () => 'test-card'}
  };
  vm.createContext(sandbox);
  for (const file of ['flashcard-session.js', 'flashcard-views.js']) vm.runInContext(fs.readFileSync(path.resolve(__dirname, '..', 'scripts', file), 'utf8'), sandbox, {filename: file});
  const data = vm.runInContext(`({
    ctx: {state: {uiLanguage: 'en', cardMemory: {}, personalCards: []}, icon: () => ''},
    cards: [
      {id:'a1',front:'First concept?',back:'First answer.',kind:'generated',course_id:'course-a',unit_id:'u1',version:1,source_refs:[],memory:{remembered:null,version:0}},
      {id:'a2',front:'Second concept?',back:'Second answer.',kind:'generated',course_id:'course-a',unit_id:'u1',version:1,source_refs:[],memory:{remembered:null,version:0}},
      {id:'b1',front:'Different unit concept?',back:'Different answer.',kind:'generated',course_id:'course-a',unit_id:'u2',version:1,source_refs:[],memory:{remembered:null,version:0}}
    ],
    courses: [{id:'course-a', revision:3, access_role:'creator', content:{title:'Networks',units:[
      {id:'u1',title:'Unit One',unlocked:true,data:{}},
      {id:'u2',title:'Unit Two',unlocked:true,data:{}}
    ]}}]
  })`, sandbox);
  const ui = sandbox.window.FLASHCARD_UI;
  h.renderFn = () => ui.renderLibrary(data.ctx);
  h.render = () => (h.lastHTML = h.renderFn());
  let progressVersion = 0;
  const bridge = {
    async api(url, body, method = 'GET') {
      calls.push({url, body, method});
      if (url === '/cards') { if (failLoad) throw new Error('Offline for this test'); return data.cards; }
      if (url === '/courses') return data.courses;
      if (/\/cards\/.+\/memory$/.test(url)) {
        if (memoryGate) await memoryGate.promise;
        if (failMemory) throw new Error('409: card revision changed; reload before rating');
        return {version: (body.expected_version || 0) + 1};
      }
      if (url === '/courses/course-a/progress') {
        if (method === 'PUT') return {...body, version: ++progressVersion};
        return {version: progressVersion, mode_positions: {}};
      }
      throw new Error('Unexpected API route: ' + method + ' ' + url);
    },
    render() {
      h.redraws++;
      // A broken automatic retry is observable without letting the test spin forever.
      if (h.redraws < (failLoad ? 8 : 100)) h.render();
    },
    save() {}, go() {}, isWorking() { return false; }, dialog: {close() {}}
  };
  ui.init(bridge); ui.setOwner('owner-a');
  h.click = (action, dataset = {}) => {
    const button = {dataset: {fc: action, ...dataset}, disabled: false};
    handlers.click({target: {closest: selector => selector === '[data-fc]' ? button : null}});
  };
  h.saved = (owner = 'owner-a') => JSON.parse(storage.get('study-card-rounds-v1:' + owner) || '{}');
  h.round = (owner = 'owner-a', deck = 'course-a|u1') => h.saved(owner).rounds?.[deck]?.session;
  h.memoryWrites = () => calls.filter(call => /\/cards\/.+\/memory$/.test(call.url));
  return Object.assign(h, {ui, data, calls, storage});
}

async function openRound(h, deck = 'course-a|u1') {
  h.render(); await settle();
  h.click('open', {deck}); await settle();
  h.click('start'); await settle();
}

test('a failed initial API load stays visible without a render-triggered request loop', async () => {
  const h = harness({failLoad: true});
  h.render(); await settle();
  assert.match(h.lastHTML, /Offline for this test/);
  for (let i = 0; i < 5; i++) h.render();
  await settle();
  assert.equal(h.calls.filter(call => call.url === '/cards').length, 1);
  assert.equal(h.calls.filter(call => call.url === '/courses').length, 1);
  assert.equal(h.redraws, 1);
  h.click('reload'); await settle();
  assert.equal(h.calls.filter(call => call.url === '/cards').length, 2, 'retry requires an explicit action');
});

test('recall cannot be written before reveal; repeated marks write once and advance only after the server resolves', async () => {
  const gate = deferred(), h = harness({memoryGate: gate});
  await openRound(h);
  h.click('rate', {memory: 'true'}); await settle();
  assert.equal(h.memoryWrites().length, 0);
  assert.equal(h.round().index, 0);
  h.click('flip'); await settle();
  assert.equal(h.round().revealed, true);
  h.click('rate', {memory: 'true'});
  h.click('rate', {memory: 'false'});
  await settle();
  assert.equal(h.memoryWrites().length, 1, 'second click must not start a concurrent write');
  assert.equal(h.round().index, 0, 'pending server write must not advance local review');
  assert.equal(h.round().revealed, true);
  assert.match(h.lastHTML, /First answer\./);
  gate.resolve(); await settle();
  assert.equal(h.round().index, 1);
  assert.equal(h.round().revealed, false);
  assert.equal(h.round().results.length, 1);
  assert.equal(h.round().results[0].remembered, true);
  assert.match(h.lastHTML, /Second concept\?/);
  assert.equal(h.memoryWrites()[0].body.expected_revision, 3);
  assert.equal(h.memoryWrites()[0].body.expected_version, 0);
});

test('an API revision conflict keeps the revealed card and pending recall unrecorded', async () => {
  const h = harness({failMemory: true}); await openRound(h);
  h.click('flip'); await settle();
  h.click('rate', {memory: 'false'}); await settle();
  assert.equal(h.memoryWrites().length, 1);
  assert.equal(h.round().index, 0);
  assert.equal(h.round().revealed, true);
  assert.equal(h.round().results.length, 0);
  assert.equal(h.data.cards[0].memory.remembered, null);
  assert.match(h.lastHTML, /409: card revision changed/);
  assert.match(h.lastHTML, /First answer\./);
});

test('round selection, revealed side and progress are stored separately for each signed-in owner', async () => {
  const h = harness(); await openRound(h);
  h.click('flip'); await settle();
  h.click('rate', {memory: 'true'}); await settle();
  assert.equal(h.round('owner-a').index, 1);
  h.ui.setOwner('owner-b'); h.render(); await settle();
  assert.equal(h.round('owner-b'), undefined);
  assert.equal(h.saved('owner-b').selected, '');
  h.click('open', {deck: 'course-a|u1'}); await settle();
  h.click('start'); await settle();
  h.click('flip'); await settle();
  assert.equal(h.round('owner-b').index, 0);
  assert.equal(h.round('owner-b').revealed, true);
  h.ui.setOwner('owner-a'); h.render(); await settle();
  assert.equal(h.round('owner-a').index, 1);
  assert.equal(h.round('owner-a').revealed, false);
  assert.match(h.lastHTML, /Second concept\?/);
  assert.equal(h.round('owner-b').index, 0);
});

test('an old owner\'s pending memory response cannot advance a newly signed-in owner\'s round', async () => {
  const gate = deferred(), h = harness({memoryGate: gate}); await openRound(h);
  h.click('flip'); await settle();
  h.click('rate', {memory: 'true'}); await settle();
  assert.equal(h.memoryWrites().length, 1);
  h.ui.setOwner('owner-b'); h.render(); await settle();
  h.click('open', {deck: 'course-a|u1'}); await settle();
  h.click('start'); await settle();
  assert.equal(h.round('owner-b').index, 0);
  gate.resolve(); await settle();
  assert.equal(h.round('owner-b').index, 0);
  assert.equal(h.round('owner-b').revealed, false);
  assert.equal(h.round('owner-b').results.length, 0);
  assert.match(h.lastHTML, /First concept\?/);
  assert.equal(h.round('owner-a').index, 0, 'the old local round stays pending until its owner reloads');
});

test('entering and changing an embedded unit always renders that unit rather than a previously browsed deck', async () => {
  const h = harness(); await openRound(h, 'course-a|u1');
  h.renderFn = () => h.ui.renderUnit(h.data.ctx, h.data.courses[0], h.data.courses[0].content.units[1]);
  h.render();
  assert.match(h.lastHTML, /<h2 data-user-content>Unit Two<\/h2>/);
  assert.match(h.lastHTML, /Different unit concept\?/);
  assert.doesNotMatch(h.lastHTML, /First concept\?/);
  h.click('start'); await settle();
  assert.match(h.lastHTML, /Different unit concept\?/);
  h.renderFn = () => h.ui.renderUnit(h.data.ctx, h.data.courses[0], h.data.courses[0].content.units[0]);
  h.render();
  assert.match(h.lastHTML, /<h2 data-user-content>Unit One<\/h2>/);
  assert.match(h.lastHTML, /First concept\?/);
});
