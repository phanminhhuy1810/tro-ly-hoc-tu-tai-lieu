/* A local review turn records the learner's own recall, never an accuracy score. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.FLASHCARD_SESSION = api;
})(typeof window === 'object' ? window : null, function () {
  'use strict';
  const SCHEMA = 1;

  function invalid(message) { throw new TypeError(message); }
  function plain(value) {
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (Array.isArray(value)) return value.map(plain);
    if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
      const result = {};
      for (const key of Object.keys(value)) {
        if (value[key] !== undefined) Object.defineProperty(result, key, {value: plain(value[key]), enumerable: true, writable: true, configurable: true});
      }
      return result;
    }
    return invalid('Review data must be JSON-safe plain values.');
  }
  function stable(value) {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}';
    return JSON.stringify(value);
  }
  function snapshots(cards) {
    if (!Array.isArray(cards)) return invalid('A review needs a card array.');
    const copy = plain(cards), ids = new Set();
    for (const card of copy) {
      if (!card || typeof card !== 'object' || Array.isArray(card) || typeof card.id !== 'string' || !card.id.trim() ||
          typeof card.front !== 'string' || !card.front.trim() || typeof card.back !== 'string' || !card.back.trim()) {
        return invalid('Each card needs a nonempty id, front and back.');
      }
      if (ids.has(card.id)) return invalid('Duplicate card ids cannot be reviewed.');
      ids.add(card.id);
    }
    return copy;
  }
  function fingerprint(cards) {
    // Memory can be updated by this review. It is not part of the learning content.
    const content = cards.map(card => { const copy = {...card}; delete copy.memory; return copy; });
    content.sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    // Keep the complete canonical value: no short hash collisions can resume a different deck.
    return stable(content);
  }
  function validContext(context) {
    if (typeof context !== 'string') return invalid('Review context must be a string.');
    return context;
  }
  function validate(session) {
    if (!session || typeof session !== 'object' || Array.isArray(session) || session.schema !== SCHEMA) return invalid('Invalid review schema.');
    validContext(session.context);
    const cards = snapshots(session.cards), ids = new Set(cards.map(card => card.id));
    if (session.deckFingerprint !== fingerprint(cards)) return invalid('The pinned card content has changed.');
    if (!Array.isArray(session.order) || session.order.length !== cards.length || new Set(session.order).size !== cards.length || session.order.some(id => !ids.has(id))) {
      return invalid('Review order must contain every card exactly once.');
    }
    if (!Number.isInteger(session.index) || session.index < 0 || session.index > cards.length ||
        typeof session.revealed !== 'boolean' || typeof session.completed !== 'boolean' || session.completed !== (session.index === cards.length) ||
        (session.completed && session.revealed)) return invalid('Invalid review position.');
    if (!Array.isArray(session.results) || session.results.length !== session.index || session.results.some((result, index) =>
      !result || typeof result !== 'object' || Array.isArray(result) || result.cardId !== session.order[index] || typeof result.remembered !== 'boolean')) {
      return invalid('Review results must match the completed cards in order.');
    }
    return session;
  }
  function freeze(value) {
    if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
    return value;
  }
  function safeCopy(value) { return freeze(plain(value)); }

  function start(cards, options = {}) {
    if (!options || typeof options !== 'object' || Array.isArray(options)) return invalid('Invalid review options.');
    const {context = '', shuffle = false, random = Math.random} = options;
    validContext(context);
    if (typeof shuffle !== 'boolean' || typeof random !== 'function') return invalid('Invalid shuffle options.');
    const pinned = snapshots(cards), order = pinned.map(card => card.id);
    if (shuffle) {
      for (let index = order.length - 1; index > 0; index--) {
        const value = random();
        if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value >= 1) return invalid('Shuffle random values must be between zero and one.');
        const target = Math.floor(value * (index + 1));
        [order[index], order[target]] = [order[target], order[index]];
      }
    }
    return safeCopy({schema: SCHEMA, context, deckFingerprint: fingerprint(pinned), cards: pinned, order,
      index: 0, revealed: false, results: [], completed: pinned.length === 0});
  }
  function current(session) {
    validate(session);
    if (session.completed) return null;
    return safeCopy(session.cards.find(card => card.id === session.order[session.index]));
  }
  function flip(session) {
    validate(session);
    if (session.completed) return invalid('This review is already complete.');
    return safeCopy({...session, revealed: !session.revealed});
  }
  function rate(session, remembered) {
    validate(session);
    if (typeof remembered !== 'boolean') return invalid('Recall must be reported as a boolean.');
    if (session.completed) return invalid('This review is already complete.');
    if (!session.revealed) return invalid('Reveal the answer before recording recall.');
    const index = session.index + 1;
    return safeCopy({...session, index, revealed: false, completed: index === session.cards.length,
      results: [...session.results, {cardId: session.order[session.index], remembered}]});
  }
  function restore(saved, cards, context = '') {
    try {
      validContext(context);
      const copy = plain(saved);
      validate(copy);
      if (copy.context !== context || copy.deckFingerprint !== fingerprint(snapshots(cards))) return null;
      return safeCopy(copy);
    } catch (_) { return null; }
  }
  function summary(session) {
    validate(session);
    const reviewed = session.results.length, remembered = session.results.filter(result => result.remembered).length;
    return {total: session.cards.length, reviewed, remembered, notYet: reviewed - remembered,
      remaining: session.cards.length - reviewed, completed: session.completed};
  }
  return Object.freeze({start, flip, current, rate, restore, summary});
});
