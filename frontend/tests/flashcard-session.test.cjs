const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const F = require('../scripts/flashcard-session.js');
const deck = () => [
  {id: 'network', front: 'Network?', back: 'All host bits zero.', kind: 'concept', unit_id: 'unit-1', version: 1, memory: 'new'},
  {id: 'broadcast', front: 'Broadcast?', back: 'All host bits one.', kind: 'concept', unit_id: 'unit-1', version: 2, memory: 'known'},
  {id: 'hosts', front: 'Usable hosts in /26?', back: '62.', kind: 'formula', unit_id: 'unit-2', version: 1, memory: 'unknown'}
];
const serialized = value => JSON.parse(JSON.stringify(value));

test('starts with independent pinned snapshots, and exposes the browser API without CommonJS', () => {
  const cards = deck(), session = F.start(cards, {context: 'course-1:r2'});
  cards[0].front = 'Changed outside';
  assert.equal(F.current(session).front, 'Network?');
  assert.equal(Object.isFrozen(session.cards[0]), true);
  assert.equal(session.revealed, false);
  assert.deepEqual(F.summary(session), {total: 3, reviewed: 0, remembered: 0, notYet: 0, remaining: 3, completed: false});
  const browser = {window: {}}; vm.createContext(browser);
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../scripts/flashcard-session.js'), 'utf8'), browser);
  assert.equal(typeof browser.window.FLASHCARD_SESSION.start, 'function');
});

test('requires a visible answer and a boolean self report, then advances with the next front hidden', () => {
  const front = F.start(deck());
  assert.throws(() => F.rate(front, true), /Reveal/);
  const back = F.flip(front);
  assert.equal(back.revealed, true);
  for (const bad of ['known', 1, null, undefined]) assert.throws(() => F.rate(back, bad), /boolean/);
  assert.equal(F.flip(back).revealed, false);
  const next = F.rate(back, false);
  assert.equal(F.current(next).id, 'broadcast');
  assert.equal(next.revealed, false);
  assert.deepEqual(next.results, [{cardId: 'network', remembered: false}]);
  assert.throws(() => F.rate(next, false), /Reveal/);
  assert.equal(front.results.length, 0);
});

test('a completed round counts each card once and reports recall separately from an accuracy score', () => {
  let session = F.start(deck());
  for (const remembered of [true, false, true]) session = F.rate(F.flip(session), remembered);
  assert.equal(F.current(session), null);
  assert.deepEqual(F.summary(session), {total: 3, reviewed: 3, remembered: 2, notYet: 1, remaining: 0, completed: true});
  assert.throws(() => F.rate(session, true), /complete/);
  assert.throws(() => F.flip(session), /complete/);
  assert.equal('score' in F.summary(session), false);
  assert.equal('accuracy' in F.summary(session), false);
});

test('JSON resume preserves the exact card, side, results and once-shuffled order', () => {
  let calls = 0;
  let session = F.start(deck(), {context: 'course-1:r2/unit-1', shuffle: true, random: () => { calls++; return 0; }});
  assert.equal(calls, 2);
  assert.deepEqual(session.order, ['broadcast', 'hosts', 'network']);
  session = F.flip(F.rate(F.flip(session), false));
  const resumed = F.restore(serialized(session), [...deck()].reverse(), 'course-1:r2/unit-1');
  assert.deepEqual(resumed, session);
  assert.equal(F.current(resumed).id, 'hosts');
  assert.equal(resumed.revealed, true);
  assert.equal(calls, 2);
  assert.equal(F.restore(serialized(session), deck(), 'course-2:r2/unit-1'), null);
});

test('resume rejects stale content, version, membership and duplicate IDs; memory updates are not content edits', () => {
  const session = F.start(deck(), {context: 'deck'});
  for (const field of ['front', 'back', 'version', 'kind', 'unit_id']) {
    const cards = deck(); cards[0][field] = field === 'version' ? 2 : 'Different';
    assert.equal(F.restore(session, cards, 'deck'), null, field);
  }
  assert.equal(F.restore(session, deck().slice(1), 'deck'), null);
  assert.equal(F.restore(session, [...deck(), deck()[0]], 'deck'), null);
  const cards = deck(); cards[0].memory = 'known';
  assert.ok(F.restore(session, cards, 'deck'));
  const collision = deck(); collision[0].back = '<b>All host bits zero.</b>';
  assert.equal(F.restore(session, collision, 'deck'), null);
});

test('corrupt or structurally tampered stored sessions cannot resume as another review position', () => {
  const valid = serialized(F.rate(F.flip(F.start(deck(), {context: 'deck'})), true));
  const mutations = [
    s => { s.schema = 9; }, s => { s.index = 2; }, s => { s.index = -1; },
    s => { s.completed = true; }, s => { s.revealed = 'yes'; },
    s => { s.order = ['network', 'network', 'hosts']; }, s => { s.order[0] = 'missing'; },
    s => { s.results[0].cardId = 'hosts'; }, s => { s.results[0].remembered = 1; },
    s => { s.results.push(s.results[0]); }, s => { s.cards[0].back = 'Tampered'; },
    s => { s.deckFingerprint = 'pretend matching content'; }
  ];
  for (const mutate of mutations) {
    const bad = serialized(valid); mutate(bad);
    assert.equal(F.restore(bad, deck(), 'deck'), null);
  }
  for (const corrupt of [undefined, null, 'broken JSON', {}, []]) assert.equal(F.restore(corrupt, deck(), 'deck'), null);
  // A rewritten fingerprint still cannot make different pinned content match the live deck.
  const tampered = F.start([{...deck()[0], back: 'Tampered'}], {context: 'deck'});
  assert.equal(F.restore(tampered, deck().slice(0, 1), 'deck'), null);
});

test('an empty deck is a completed empty round, and invalid inputs fail instead of silently dropping cards', () => {
  const empty = F.start([]);
  assert.equal(F.current(empty), null);
  assert.deepEqual(F.summary(empty), {total: 0, reviewed: 0, remembered: 0, notYet: 0, remaining: 0, completed: true});
  assert.ok(F.restore(serialized(empty), [], ''));
  for (const cards of [null, {}, [...deck(), deck()[0]], [{id: 'empty', front: '', back: 'A'}]]) assert.throws(() => F.start(cards));
  assert.throws(() => F.start(deck(), {context: 7}));
  for (const value of [1, -0.1, NaN, '0']) assert.throws(() => F.start(deck(), {shuffle: true, random: () => value}), /random/);
});
