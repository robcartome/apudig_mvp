(function () {
  'use strict';
  const body = document.getElementById('purchase-lines-body');
  const config = document.getElementById('purchase-form-config');
  if (!body || !config) return;
  const warehouse = document.getElementById('id_warehouse');
  const supplier = document.getElementById('id_supplier');
  const orderMode = config.dataset.orderMode === 'true';
  const editValue = config.dataset.editValue !== 'false';
  const editPrice = config.dataset.editPrice !== 'false';
  const editTotal = config.dataset.editTotal === 'true';
  const configuredPriceDecimals = Number(config.dataset.priceDecimals);
  const priceDecimals = Number.isInteger(configuredPriceDecimals)
    ? Math.min(6, Math.max(0, configuredPriceDecimals)) : 2;
  const defaultIgvRate = Number(config.dataset.igvRate || 18);
  const priceStep = priceDecimals === 0 ? '1' : `0.${'0'.repeat(priceDecimals - 1)}1`;
  const priceZero = (0).toFixed(priceDecimals);
  const totalForms = () => document.getElementById('id_lines-TOTAL_FORMS');
  let memoInput = null;

  const currency = document.getElementById('id_currency');
  const exchangeRate = document.getElementById('id_exchange_rate');
  const exchangeRateField = document.getElementById('exchange-rate-field');
  const paymentMethod = document.getElementById('id_payment_method');
  const issueDate = document.getElementById('id_issue_date');
  const dueDate = document.getElementById('id_due_date');
  const dueDateField = document.getElementById('due-date-field');
  const paymentWorkflowHelp = document.getElementById('payment-workflow-help');
  const paymentMethods = JSON.parse(document.getElementById('purchase-payment-methods')?.textContent || '[]');

  function updateCurrencyFields() {
    const foreignCurrency = currency?.value !== 'PEN';
    if (exchangeRateField) exchangeRateField.classList.toggle('opacity-50', !foreignCurrency);
    if (exchangeRate) {
      if (!foreignCurrency) exchangeRate.value = '1';
      exchangeRate.readOnly = !foreignCurrency;
    }
  }

  function updatePaymentTerms() {
    const selected = paymentMethods.find(item => String(item.id) === String(paymentMethod?.value));
    const isCash = selected?.is_cash === true;
    if (isCash && dueDate && issueDate?.value) dueDate.value = issueDate.value;
    if (dueDate) dueDate.readOnly = isCash;
    if (dueDateField) dueDateField.classList.toggle('opacity-75', isCash);
    if (paymentWorkflowHelp) {
      paymentWorkflowHelp.textContent = isCash
        ? 'Compra al contado: al registrar el documento se habilitara Registrar pago. El estado cambiara a Pagado cuando se confirme el pago.'
        : 'Compra a credito: al registrar el documento se generara el saldo por pagar. Puedes aplicar uno o varios adelantos desde el listado.';
    }
  }

  currency?.addEventListener('change', updateCurrencyFields);
  paymentMethod?.addEventListener('change', updatePaymentTerms);
  issueDate?.addEventListener('change', updatePaymentTerms);
  updateCurrencyFields();
  updatePaymentTerms();

  ProductPicker.configure({
    searchUrl: config.dataset.searchUrl,
    createUrl: config.dataset.createUrl,
    getWarehouse: () => warehouse?.value || '',
    getSupplier: () => supplier?.value || '',
    priceDecimals,
  });

  function setUnits(row, product) {
    const select = row.querySelector('.product-unit-select');
    const units = product.units || [];
    row.dataset.baseUnitId = product.unit_id || '';
    row.dataset.baseUnitCode = product.unit || '';
    select.innerHTML = units.map(unit => `<option value="${unit.id}" data-factor="${unit.factor}" data-code="${unit.code}" data-price="${unit.purchase_price ?? ''}">${unit.code} - ${unit.name}</option>`).join('');
    const preferred = units.find(unit => String(unit.id) === String(product.unit_id)) || units[0];
    if (preferred) select.value = preferred.id;
    select.disabled = false;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function updateUnit(row) {
    const select = row.querySelector('.product-unit-select');
    const option = select?.selectedOptions[0];
    const hidden = row.querySelector('input[name*="-unit"]');
    if (hidden) hidden.value = option?.value || '';
    const factor = Number(option?.dataset.factor || 1);
    const quantity = parseAmount(row.querySelector('input[name*="-quantity"]')?.value);
    const hint = row.querySelector('.unit-equivalence');
    if (hint) hint.textContent = factor !== 1 ? `1 ${option?.dataset.code || ''} = ${factor} ${row.dataset.baseUnitCode || ''} · Total ${quantity * factor}` : '';
  }

  function formatAmount(value) {
    return Number(value || 0).toLocaleString('es-PE', {
      minimumFractionDigits: priceDecimals,
      maximumFractionDigits: priceDecimals,
    });
  }

  function parseAmount(value) {
    return Number(String(value || '0').replace(',', '.')) || 0;
  }

  function prepareRowInputs(row) {
    const quantity = row.querySelector('input[name*="-quantity"]');
    if (quantity) {
      quantity.type = 'text';
      quantity.inputMode = 'decimal';
      quantity.autocomplete = 'off';
      quantity.maxLength = 15;
      quantity.classList.add('form-control-sm', 'text-end', 'quantity-input');
    }
    const valueInput = row.querySelector('input[name*="-unit_price"]');
    if (valueInput) {
      valueInput.classList.add('text-end', 'value-unit-input');
      valueInput.readOnly = !editValue;
    }
    const priceInput = row.querySelector('.price-unit-input');
    if (priceInput) priceInput.readOnly = !editPrice;
    row.querySelectorAll('.line-price-unit, .line-subtotal, .line-igv, .line-total').forEach(cell => {
      cell.classList.add('num-cell', 'readonly-cell');
    });
  }

  function applyCompanyNumberSettings(row, isNew = false) {
    row.querySelectorAll('.price-unit-input, .value-unit-input, .line-total-input').forEach(input => {
      input.step = priceStep;
    });
    if (isNew) {
      const igvInput = row.querySelector('input[name*="-igv_rate"]');
      if (igvInput) igvInput.value = defaultIgvRate;
      const priceInput = row.querySelector('.price-unit-input');
      if (priceInput) priceInput.value = priceZero;
      row.querySelectorAll('.line-subtotal, .line-igv, .line-total').forEach(element => {
        element.textContent = priceZero;
      });
    }
  }

  function updateSummary() {
    const totals = { discount: 0, taxable: 0, exempt: 0, unaffected: 0, igv: 0, total: 0 };
    body.querySelectorAll('.line-row:not([hidden])').forEach(row => {
      const quantity = parseAmount(row.querySelector('input[name*="-quantity"]')?.value);
      const valueUnit = parseAmount(row.querySelector('input[name*="-unit_price"]')?.value);
      const discount = parseAmount(row.querySelector('input[name*="-discount_amount"]')?.value);
      const taxType = row.querySelector('select[name*="-tax_type"]')?.value;
      const rate = parseAmount(row.querySelector('input[name*="-igv_rate"]')?.value);
      const subtotal = Math.max(0, quantity * valueUnit - discount);
      const igv = taxType === '10' ? subtotal * rate / 100 : 0;
      totals.discount += discount;
      if (taxType === '10') totals.taxable += subtotal;
      else if (taxType === '20') totals.exempt += subtotal;
      else totals.unaffected += subtotal;
      totals.igv += igv;
      totals.total += subtotal + igv;
    });
    Object.entries(totals).forEach(([key, value]) => {
      const element = document.getElementById(`summary-${key}`);
      if (element) element.textContent = formatAmount(value);
    });
  }

  function updateLineTotals(row, source) {
    const quantity = parseAmount(row.querySelector('input[name*="-quantity"]')?.value);
    const valueInput = row.querySelector('input[name*="-unit_price"]');
    const priceInput = row.querySelector('.price-unit-input');
    const totalInput = row.querySelector('.line-total-input');
    const discount = parseAmount(row.querySelector('input[name*="-discount_amount"]')?.value);
    const taxType = row.querySelector('select[name*="-tax_type"]')?.value;
    const rate = parseAmount(row.querySelector('input[name*="-igv_rate"]')?.value);
    const taxFactor = taxType === '10' ? 1 + rate / 100 : 1;
    let valueUnit = parseAmount(valueInput?.value);
    if (source === 'price' && priceInput) {
      valueUnit = parseAmount(priceInput.value) / taxFactor;
      // El valor unitario se guarda sin IGV. Conservamos precisión de cálculo
      // para que el total provenga del Precio Unit. visible (p. ej. 1.69 × 10).
      valueInput.value = valueUnit.toFixed(6);
    } else if (source === 'total' && totalInput && quantity > 0) {
      valueUnit = Math.max(0, (parseAmount(totalInput.value) / taxFactor + discount) / quantity);
      valueInput.value = valueUnit.toFixed(6);
    }
    const subtotal = Math.max(0, quantity * valueUnit - discount);
    const igv = taxType === '10' ? subtotal * rate / 100 : 0;
    const priceUnit = valueUnit * taxFactor;
    const values = {
      '.line-subtotal': subtotal,
      '.line-igv': igv,
      '.line-total': subtotal + igv,
    };
    if (priceInput && source !== 'price') priceInput.value = priceUnit.toFixed(priceDecimals);
    if (totalInput && source !== 'total') totalInput.value = (subtotal + igv).toFixed(priceDecimals);
    Object.entries(values).forEach(([selector, value]) => {
      const element = row.querySelector(selector);
      if (element) element.textContent = formatAmount(value);
    });
    updateSummary();
  }

  function buildRow(index) {
    const row = document.createElement('tr');
    row.className = 'line-row';
    if (orderMode) {
      row.innerHTML = `<td class="line-num text-muted">${index + 1}<input type="hidden" name="lines-${index}-DELETE" value=""></td><td><input type="hidden" name="lines-${index}-product"><select class="product-select w-100"></select><input type="hidden" name="lines-${index}-description"><input type="hidden" name="lines-${index}-memo"></td><td><input type="hidden" name="lines-${index}-unit"><select class="form-select form-select-sm product-unit-select"><option value="">-</option></select><div class="unit-equivalence text-muted small"></div></td><td><div class="input-group input-group-sm"><input type="number" class="form-control form-control-sm" name="lines-${index}-quantity" step="0.0001" min="0.0001"><button type="button" class="btn btn-outline-secondary stock-info-btn" title="Ver existencias por almacén" disabled><i class="ti ti-building-warehouse"></i></button></div></td><td><input type="number" class="form-control form-control-sm" name="lines-${index}-unit_price" step="0.000001" min="0"></td><td><input type="number" class="form-control form-control-sm" name="lines-${index}-discount_amount" step="0.01" min="0" value="0"></td><td><select class="form-select form-select-sm" name="lines-${index}-tax_type"><option value="10">Gravado IGV</option><option value="20">Exonerado</option><option value="30">Inafecto</option><option value="40">Importación</option></select></td><td><input type="number" class="form-control form-control-sm" name="lines-${index}-igv_rate" value="18" step="0.01"></td><td><input type="checkbox" class="d-none" name="lines-${index}-update_purchase_price"><div class="d-flex gap-1"><button type="button" class="btn btn-sm btn-outline-secondary memo-btn"><i class="ti ti-note"></i></button><button type="button" class="btn btn-sm btn-outline-danger remove-line"><i class="ti ti-x"></i></button></div></td>`;
      applyCompanyNumberSettings(row, true);
      prepareRowInputs(row);
      return row;
    }
    row.innerHTML = `<td class="line-num text-muted">${index + 1}<input type="hidden" name="lines-${index}-DELETE" value=""></td><td><input type="hidden" name="lines-${index}-product"><select class="product-select w-100"></select><input type="hidden" name="lines-${index}-description"><input type="hidden" name="lines-${index}-memo"></td><td><input type="hidden" name="lines-${index}-unit"><select class="form-select form-select-sm product-unit-select"><option value="">-</option></select><div class="unit-equivalence text-muted small"></div></td><td><div class="input-group input-group-sm"><input type="number" class="form-control form-control-sm" name="lines-${index}-quantity" step="0.0001" min="0.0001"><button type="button" class="btn btn-outline-secondary stock-info-btn" title="Ver existencias por almacén" disabled><i class="ti ti-building-warehouse"></i></button></div></td><td><select class="form-select form-select-sm" name="lines-${index}-tax_type"><option value="10">Gravado IGV</option><option value="20">Exonerado</option><option value="30">Inafecto</option><option value="40">Importación</option></select><input type="hidden" name="lines-${index}-igv_rate" value="18"><input type="hidden" name="lines-${index}-discount_amount" value="0"></td><td><input type="number" class="form-control form-control-sm value-unit-input" name="lines-${index}-unit_price" step="0.000001" min="0"></td><td><input type="text" class="form-control form-control-sm text-end price-unit-input" inputmode="decimal" value="0.00"></td><td class="text-end line-subtotal">0.00</td><td class="text-end line-igv">0.00</td><td>${editTotal ? '<input type="text" class="form-control form-control-sm text-end fw-semibold line-total-input" inputmode="decimal" value="0.00">' : '<span class="d-block text-end fw-semibold line-total">0.00</span>'}</td><td class="d-none"><input type="checkbox" name="lines-${index}-update_purchase_price" checked></td><td><div class="d-flex gap-1"><button type="button" class="btn btn-sm btn-outline-secondary memo-btn" title="Memo de línea"><i class="ti ti-note"></i></button><button type="button" class="btn btn-sm btn-outline-danger remove-line"><i class="ti ti-x"></i></button></div></td>`;
    applyCompanyNumberSettings(row, true);
    prepareRowInputs(row);
    return row;
  }

  body.addEventListener('product-picker:selected', event => {
    const row = event.target.closest('.line-row');
    const product = event.detail;
    setUnits(row, product);
    row.querySelector('.stock-info-btn').disabled = false;
    const description = row.querySelector('input[name*="-description"]');
    if (description && !description.value) description.value = product.name || product.text || '';
    const price = row.querySelector('input[name*="-unit_price"]');
    const priceUnitInput = row.querySelector('.price-unit-input');
    const configuredUnitPrice = row.querySelector('.product-unit-select')?.selectedOptions[0]?.dataset.price;
    const suggested = product.supplier_purchase_price
      ?? (configuredUnitPrice !== undefined && configuredUnitPrice !== '' ? Number(configuredUnitPrice) : null)
      ?? product.price_purchase
      ?? 0;
    row.dataset.basePurchasePrice = suggested;
    if (priceUnitInput) {
      priceUnitInput.step = priceStep;
      priceUnitInput.value = Number(suggested).toFixed(priceDecimals);
      updateLineTotals(row, 'price');
    } else {
      updateLineTotals(row);
    }
  });
  body.addEventListener('change', event => {
    const row = event.target.closest('.line-row');
    if (event.target.matches('.product-unit-select')) {
      updateUnit(row);
      const option = event.target.selectedOptions[0];
      const configuredPrice = option?.dataset.price;
      const factor = Number(option?.dataset.factor || 1);
      const priceInput = row.querySelector('.price-unit-input');
      const price = configuredPrice !== undefined && configuredPrice !== ''
        ? Number(configuredPrice)
        : Number(row.dataset.basePurchasePrice || 0) * factor;
      if (priceInput) priceInput.value = price.toFixed(priceDecimals);
      updateLineTotals(row, 'price');
      return;
    }
    updateLineTotals(row);
  });
  body.addEventListener('input', event => {
    const row = event.target.closest('.line-row');
    if (!row) return;
    if (event.target.matches('input[name*="-quantity"]')) {
      updateUnit(row);
      updateLineTotals(row);
      return;
    }
    if (event.target.matches('.price-unit-input')) updateLineTotals(row, 'price');
    else if (event.target.matches('.line-total-input')) updateLineTotals(row, 'total');
    else if (event.target.matches('input[name*="-unit_price"], input[name*="-discount_amount"], input[name*="-igv_rate"]')) updateLineTotals(row, 'value');
  });
  body.addEventListener('click', event => {
    const memoButton = event.target.closest('.memo-btn');
    if (memoButton) {
      memoInput = memoButton.closest('.line-row').querySelector('input[name*="-memo"]');
      document.getElementById('purchase-memo-text').value = memoInput?.value || '';
      bootstrap.Modal.getOrCreateInstance(document.getElementById('purchaseMemoModal')).show();
      return;
    }
    const button = event.target.closest('.remove-line');
    if (!button || body.querySelectorAll('.line-row:not([hidden])').length <= 1) return;
    const row = button.closest('.line-row');
    const deleteInput = row.querySelector('input[name*="-DELETE"]');
    if (deleteInput) deleteInput.value = 'on';
    ProductPicker.destroy(row);
    row.hidden = true;
    updateSummary();
  });
  document.getElementById('purchase-memo-save')?.addEventListener('click', () => {
    if (memoInput) memoInput.value = document.getElementById('purchase-memo-text').value;
    bootstrap.Modal.getInstance(document.getElementById('purchaseMemoModal'))?.hide();
  });
  document.getElementById('add-purchase-line')?.addEventListener('click', () => {
    const row = buildRow(Number(totalForms().value));
    body.appendChild(row);
    totalForms().value = Number(totalForms().value) + 1;
    ProductPicker.init(row);
    ProductPicker.open(row);
  });
  body.querySelectorAll('.line-row').forEach(row => {
    applyCompanyNumberSettings(row);
    prepareRowInputs(row);
    ProductPicker.init(row);
    updateUnit(row);
    updateLineTotals(row);
  });
}());
