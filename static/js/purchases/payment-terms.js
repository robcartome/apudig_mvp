(function () {
  'use strict';
  const paymentMethod = document.getElementById('id_payment_method');
  const issueDate = document.getElementById('id_issue_date');
  const dueDate = document.getElementById('id_due_date');
  const dueDateField = document.getElementById('due-date-field');
  const config = document.getElementById('purchase-payment-methods');
  const help = document.getElementById('payment-workflow-help');
  if (!paymentMethod || !dueDate || !dueDateField || !config) return;
  const conditions = JSON.parse(config.textContent || '[]');

  function update(event) {
    const selected = conditions.find(item => String(item.id) === paymentMethod.value);
    const deferred = selected?.requires_due_date === true;
    const changedCondition = event?.target === paymentMethod;
    // Keep a legacy date visible on edit/error so the user can classify it.
    const unclassifiedDate = !selected && Boolean(dueDate.value) && !changedCondition;
    dueDateField.hidden = !deferred && !unclassifiedDate;
    dueDate.disabled = !deferred && !unclassifiedDate;
    dueDate.required = deferred;
    dueDate.readOnly = unclassifiedDate;
    dueDate.min = issueDate?.value || '';
    dueDateField.querySelector('label')?.classList.toggle('required', deferred);
    // The server sets cash maturity to the issue date. Do not carry that hidden
    // date into a later credit selection: the user must choose its deadline.
    if (selected && !deferred) dueDate.value = '';
    if (!selected && changedCondition) dueDate.value = '';
    if (!help) return;
    if (unclassifiedDate) {
      help.textContent = 'Este documento tiene vencimiento sin condición de pago. Selecciona una condición para conservar y editar esa fecha.';
    } else if (!selected) {
      help.textContent = 'Selecciona una condición de pago para definir el vencimiento. Guardar o registrar el documento no confirma su pago.';
    } else if (deferred) {
      help.textContent = 'Pago a crédito: indica la fecha límite para pagar esta factura. El saldo se reduce al registrar los pagos y genera avisos cuando se aproxima o supera el vencimiento.';
    } else {
      help.textContent = 'Pago inmediato: vence en la fecha de emisión. El estado cambia a Pagado solo al confirmar el pago; seleccionar esta condición no registra un pago.';
    }
  }

  paymentMethod.addEventListener('change', update);
  issueDate?.addEventListener('change', update);
  update();
}());
