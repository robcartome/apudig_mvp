(function () {
  'use strict';
  const body = document.getElementById('expense-lines-body');
  const totalForms = document.getElementById('id_lines-TOTAL_FORMS');
  if (!body || !totalForms) return;

  const number = value => Number(String(value || '0').replace(',', '.')) || 0;
  const format = value => Number(value || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});

  function calculate() {
    let subtotalSummary = 0;
    let igvSummary = 0;
    body.querySelectorAll('.expense-line-row:not([hidden])').forEach(row => {
      const quantity = number(row.querySelector('[name*="-quantity"]')?.value);
      const unitValue = number(row.querySelector('[name*="-unit_price"]')?.value);
      const discount = number(row.querySelector('[name*="-discount_amount"]')?.value);
      const rate = number(row.querySelector('[name*="-igv_rate"]')?.value);
      const taxable = row.querySelector('[name*="-tax_type"]')?.value === '10';
      const subtotal = Math.max(0, quantity * unitValue - discount);
      const igv = taxable ? subtotal * rate / 100 : 0;
      row.querySelector('.line-subtotal').textContent = format(subtotal);
      row.querySelector('.line-igv').textContent = format(igv);
      row.querySelector('.line-total').textContent = format(subtotal + igv);
      subtotalSummary += subtotal;
      igvSummary += igv;
    });
    document.getElementById('expense-summary-subtotal').textContent = format(subtotalSummary);
    document.getElementById('expense-summary-igv').textContent = format(igvSummary);
    document.getElementById('expense-summary-total').textContent = format(subtotalSummary + igvSummary);
  }

  body.addEventListener('input', calculate);
  body.addEventListener('change', calculate);
  body.addEventListener('click', event => {
    const button = event.target.closest('.remove-expense-line');
    if (!button || body.querySelectorAll('.expense-line-row:not([hidden])').length <= 1) return;
    const row = button.closest('.expense-line-row');
    const deletion = row.querySelector('[name*="-DELETE"]');
    if (deletion) deletion.checked = true;
    row.hidden = true;
    calculate();
  });
  document.getElementById('add-expense-line')?.addEventListener('click', () => {
    const index = Number(totalForms.value);
    const template = document.getElementById('expense-empty-row');
    const wrapper = document.createElement('tbody');
    wrapper.innerHTML = template.innerHTML.replaceAll('__prefix__', index).replace('__number__', index + 1);
    body.appendChild(wrapper.firstElementChild);
    totalForms.value = index + 1;
    calculate();
  });
  calculate();
}());
