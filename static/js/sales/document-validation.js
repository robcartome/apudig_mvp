(function () {
  'use strict';
  const form = document.getElementById('sales-form');
  if (!form) return;
  const creditIds = JSON.parse(document.getElementById('sales-credit-payment-ids').textContent);
  const payment = document.getElementById('id_payment_method');
  const due = document.getElementById('id_due_date');
  const label = document.getElementById('due-date-label');
  const dueError = document.getElementById('due-date-client-error');

  function visibleControl(field) {
    if (field.type === 'hidden') {
      if (field.id === 'id_customer') return document.getElementById('id_customer-picker');
      const cell = field.closest('td');
      if (cell) return cell.querySelector('.product-select, input:not([type="hidden"]), select');
    }
    return field;
  }
  function mark(field) {
    const control = visibleControl(field);
    if (!control) return null;
    control.classList.add('is-invalid');
    control.setAttribute('aria-invalid', 'true');
    const select2 = control.nextElementSibling;
    if (select2 && select2.classList.contains('select2-container')) select2.classList.add('is-invalid');
    function clear() {
      control.classList.remove('is-invalid');
      control.removeAttribute('aria-invalid');
      if (select2) select2.classList.remove('is-invalid');
    }
    control.addEventListener('input', clear, { once: true });
    control.addEventListener('change', clear, { once: true });
    if (window.jQuery && control.classList.contains('select2-hidden-accessible')) {
      window.jQuery(control).one('select2:select', clear);
    }
    return select2 && select2.classList.contains('select2-container') ? select2 : control;
  }
  function focusError(element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const target = element.matches('.select2-container') ? element.querySelector('.select2-selection') : element;
    if (target) target.focus({ preventScroll: true });
  }
  function updateDue() {
    const credit = creditIds.includes(payment.value);
    due.required = credit;
    label.classList.toggle('required', credit);
    if (!credit || due.value) dueError.hidden = true;
  }
  payment.addEventListener('change', updateDue);
  due.addEventListener('input', updateDue);
  updateDue();
  form.addEventListener('submit', function (event) {
    updateDue();
    if (due.required && !due.value) {
      event.preventDefault();
      dueError.hidden = false;
      focusError(mark(due));
    }
  });
}());
