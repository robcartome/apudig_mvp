// Run with: node --test apps/purchases/tests/test_payment_terms_js.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.resolve(__dirname, '../../../static/js/purchases/payment-terms.js'), 'utf8');

function mount({condition = '', due = ''} = {}) {
  const field = value => ({value, events: {}, addEventListener(name, fn) { this.events[name] = fn; }});
  const payment = field(condition);
  const issue = field('2026-11-27');
  const date = field(due);
  const labelClasses = new Set();
  const wrapper = {querySelector: () => ({classList: {
    toggle(name, enabled) { enabled ? labelClasses.add(name) : labelClasses.delete(name); },
  }})};
  const help = {};
  const elements = {
    id_payment_method: payment, id_issue_date: issue, id_due_date: date,
    'due-date-field': wrapper, 'payment-workflow-help': help,
    'purchase-payment-methods': {textContent: JSON.stringify([
      {id: 'credit', requires_due_date: true},
      {id: 'immediate', requires_due_date: false},
    ])},
  };
  vm.runInNewContext(source, {document: {getElementById: id => elements[id]}});
  const change = (element, value) => {
    element.value = value;
    element.events.change({target: element});
  };
  return {payment, issue, date, wrapper, help, labelClasses, change};
}

test('new unclassified document hides and disables the date', () => {
  const ui = mount();
  assert.equal(ui.wrapper.hidden, true);
  assert.equal(ui.date.disabled, true);
  assert.equal(ui.date.required, false);
});

test('selecting credit requires an editable date no earlier than issue', () => {
  const ui = mount();
  ui.change(ui.payment, 'credit');
  assert.equal(ui.wrapper.hidden, false);
  assert.equal(ui.date.disabled, false);
  assert.equal(ui.date.readOnly, false);
  assert.equal(ui.date.required, true);
  assert.equal(ui.date.min, '2026-11-27');
  assert.equal(ui.labelClasses.has('required'), true);
  ui.change(ui.issue, '2026-11-28');
  assert.equal(ui.date.min, '2026-11-28');
});

test('existing credit date remains editable on initial render', () => {
  const ui = mount({condition: 'credit', due: '2026-12-27'});
  assert.equal(ui.date.value, '2026-12-27');
  assert.equal(ui.date.required, true);
  assert.equal(ui.date.readOnly, false);
});

test('immediate payment clears hidden credit date and changing back needs a new date', () => {
  const ui = mount({condition: 'credit', due: '2026-12-27'});
  ui.change(ui.payment, 'immediate');
  assert.equal(ui.wrapper.hidden, true);
  assert.equal(ui.date.disabled, true);
  assert.equal(ui.date.required, false);
  assert.equal(ui.date.value, '');
  assert.equal(ui.labelClasses.has('required'), false);
  ui.change(ui.payment, 'credit');
  assert.equal(ui.date.value, '');
  assert.equal(ui.date.required, true);
});

test('legacy date without condition is visible with guidance until classified', () => {
  const ui = mount({due: '2026-12-27'});
  assert.equal(ui.wrapper.hidden, false);
  assert.equal(ui.date.disabled, false);
  assert.equal(ui.date.readOnly, true);
  assert.match(ui.help.textContent, /sin condición/);
  ui.change(ui.issue, '2026-11-28');
  assert.equal(ui.date.value, '2026-12-27');
  assert.equal(ui.wrapper.hidden, false);
  ui.change(ui.payment, 'credit');
  assert.equal(ui.date.readOnly, false);
  assert.equal(ui.date.value, '2026-12-27');
});

test('removing a condition clears the old maturity rather than submitting an orphan date', () => {
  const ui = mount({condition: 'credit', due: '2026-12-27'});
  ui.change(ui.payment, '');
  assert.equal(ui.date.value, '');
  assert.equal(ui.wrapper.hidden, true);
  assert.equal(ui.date.disabled, true);
});

test('script is harmless on pages without the purchase payment controls', () => {
  assert.doesNotThrow(() => vm.runInNewContext(source, {
    document: {getElementById: () => null},
  }));
});
