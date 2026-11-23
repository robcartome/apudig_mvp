(function () {
  'use strict';
  document.querySelectorAll('form').forEach(form => {
    const type = form.querySelector('[name="source_type"]');
    const fund = form.querySelector('[name="cash_fund"]');
    const account = form.querySelector('[name="bank_account"]');
    if (!type || !fund || !account) return;
    function update() {
      [[fund, 'CASH'], [account, 'BANK']].forEach(([field, value]) => {
        const enabled = type.value === value;
        field.disabled = !enabled;
        field.required = enabled;
        const wrapper = field.closest('[data-payment-source]');
        if (wrapper) wrapper.hidden = !enabled;
      });
    }
    type.addEventListener('change', update);
    update();
  });
})();
