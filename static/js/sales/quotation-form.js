/**
 * quotation-form.js — Sales quotation form behavior.
 *
 * Column layout: # | Producto | UND | Cantidad | Tipo IGV | Valor Unit.(%) | Precio Unit. | SubTotal | Impuesto | Total | [x]
 *
 * Price logic:
 *   precio_unit (inc-IGV) = what user enters  →  stored visually
 *   unit_price  (ex-IGV)  = precio_unit / (1 + igv_rate/100)  →  Django hidden field, submitted to backend
 *   subtotal              = unit_price × quantity
 *   igv_amount            = subtotal × igv_rate/100  (only for tax_type 10 or 11)
 *   line_total            = subtotal + igv_amount  =  precio_unit × quantity  (when no discount)
 */
(function () {
  'use strict';

  const linesBody = document.getElementById('lines-body');
  if (!linesBody) return;

  const configEl  = document.getElementById('quot-form-config');
  const IGV_RATE  = parseFloat(configEl.dataset.igvRate) || 18;
  const IGV_MULT  = 1 + IGV_RATE / 100;          // e.g. 1.18
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  // Build the price-list API URL template (replace the placeholder UUID)
  const PRICE_LIST_URL_TPL = configEl.dataset.priceListUrl;

  // TAX_TYPE_CHOICES (must match sales/models.py)
  const TAX_TYPES = [
    ['10', 'Gravado IGV'],
    ['20', 'Exonerado'],
    ['30', 'Inafecto'],
    ['40', 'Exportación'],
    ['11', 'IGV retiro'],
  ];

  const TAXED = new Set(['10', '11']);

  // ── ProductPicker ──────────────────────────────────────────────────────────
  ProductPicker.configure({
    searchUrl: configEl.dataset.searchUrl,
    createUrl: configEl.dataset.createUrl,
    csrfToken,
    getWarehouse: () => '',
    modalId: 'quickCreateModal',
    errorId: 'qc-error',
    nameId: 'qc-name',
    skuId: 'qc-sku',
    unitId: 'qc-unit',
    saveButtonId: 'qc-btn-save',
  });

  // ── Flatpickr date pickers ────────────────────────────────────────────────
  if (typeof flatpickr !== 'undefined') {
    flatpickr.localize(flatpickr.l10ns.es);
    document.querySelectorAll('input[type=date]').forEach(function (el) {
      flatpickr(el, {
        dateFormat: 'Y-m-d',
        allowInput: true,
      });
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  function setUnitSelect(row, unitId, unitLabel) {
    const sel = row.querySelector('.product-unit-select');
    if (!sel) return;
    sel.innerHTML = `<option value="${unitId || ''}">${unitLabel || '—'}</option>`;
  }

  function fmt(n) { return isFinite(n) ? n.toFixed(2) : '0.00'; }

  // ── Per-row calculation ────────────────────────────────────────────────────
  function calcRow(row) {
    const priceIncInput = row.querySelector('.price-unit-input');
    const unitPriceHidden = row.querySelector('input[name*="-unit_price"]');
    const qtyInput  = row.querySelector('input[name*="-quantity"]');
    const taxSel    = row.querySelector('select[name*="-tax_type"]');
    const igvHidden = row.querySelector('input[name*="-igv_rate"]');
    const discHidden = row.querySelector('input[name*="-discount_amount"]');

    const priceInc = parseFloat(priceIncInput?.value) || 0;
    const qty      = parseFloat(qtyInput?.value)  || 0;
    const taxType  = taxSel?.value || '10';
    const igvRate  = parseFloat(igvHidden?.value) || IGV_RATE;
    const discount = parseFloat(discHidden?.value) || 0;
    const mult     = 1 + igvRate / 100;

    // ex-tax unit price (what backend stores as unit_price)
    const unitPriceEx = priceInc / mult;
    if (unitPriceHidden) unitPriceHidden.value = unitPriceEx.toFixed(6);

    const subtotal  = Math.max(unitPriceEx * qty - discount, 0);
    const igvAmt    = TAXED.has(taxType) ? subtotal * igvRate / 100 : 0;
    const lineTotal = subtotal + igvAmt;

    // Update display cells
    const subCell  = row.querySelector('.line-subtotal');
    const igvCell  = row.querySelector('.line-igv');
    const totCell  = row.querySelector('.line-total');

    if (subCell)  subCell.textContent  = fmt(subtotal);
    if (igvCell)  igvCell.textContent  = fmt(igvAmt);
    if (totCell)  totCell.textContent  = fmt(lineTotal);

    return { subtotal, igvAmt, lineTotal, discount };
  }

  // ── Grand totals ───────────────────────────────────────────────────────────
  function updateSummary() {
    let sumSub = 0, sumDisc = 0, sumBase = 0, sumIgv = 0, sumTotal = 0;

    linesBody.querySelectorAll('.line-row').forEach(row => {
      if (row.style.opacity === '0.3') return;          // deleted rows
      const { subtotal, igvAmt, lineTotal, discount } = calcRow(row);
      sumSub   += subtotal;
      sumDisc  += discount;
      sumBase  += (igvAmt > 0 ? subtotal : 0);         // taxable base
      sumIgv   += igvAmt;
      sumTotal += lineTotal;
    });

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = fmt(val); };
    set('summary-subtotal', sumSub);
    set('summary-discount', sumDisc);
    set('summary-base',     sumBase);
    set('summary-igv',      sumIgv);
    set('summary-total',    sumTotal);
  }

  // ── Formset management ─────────────────────────────────────────────────────
  function totalForms() { return document.getElementById('id_lines-TOTAL_FORMS'); }

  function renumber() {
    linesBody.querySelectorAll('.line-row').forEach((row, i) => {
      const num = row.querySelector('.line-num');
      if (num) num.textContent = i + 1;
    });
  }

  function reindex() {
    linesBody.querySelectorAll('.line-row').forEach((row, i) => {
      row.querySelectorAll('[name]').forEach(el => { el.name = el.name.replace(/-\d+-/, `-${i}-`); });
      row.querySelectorAll('[id]').forEach(el => { if (el.id) el.id = el.id.replace(/-\d+-/, `-${i}-`); });
    });
    totalForms().value = linesBody.querySelectorAll('.line-row').length;
    renumber();
  }

  function buildTaxOptions(selected) {
    return TAX_TYPES.map(([v, l]) =>
      `<option value="${v}"${v === selected ? ' selected' : ''}>${l}</option>`
    ).join('');
  }

  function buildRow(index) {
    const row = document.createElement('tr');
    row.className = 'line-row';
    row.innerHTML = `
      <td class="text-center text-muted line-num">${index + 1}</td>

      <td style="min-width:220px">
        <input type="hidden" name="lines-${index}-product" id="id_lines-${index}-product" value="">
        <input type="hidden" name="lines-${index}-description" id="id_lines-${index}-description" value="">
        <select class="product-select w-100"></select>
      </td>

      <td>
        <select class="form-select form-select-sm product-unit-select" disabled>
          <option value="">—</option>
        </select>
      </td>

      <td>
        <input type="number" name="lines-${index}-quantity" id="id_lines-${index}-quantity"
               class="form-control form-control-sm" step="0.0001" min="0.0001" value="1">
      </td>

      <td>
        <select name="lines-${index}-tax_type" id="id_lines-${index}-tax_type"
                class="form-select form-select-sm">
          ${buildTaxOptions('10')}
        </select>
      </td>

      <td class="num-cell">
        <input type="hidden" name="lines-${index}-igv_rate" id="id_lines-${index}-igv_rate"
               value="${IGV_RATE}">
        <div class="input-group input-group-sm">
          <span class="input-group-text">%</span>
          <input type="text" class="form-control form-control-sm igv-rate-display text-end"
                 value="${IGV_RATE}" disabled readonly tabindex="-1">
        </div>
      </td>

      <td>
        <input type="hidden" name="lines-${index}-unit_price" id="id_lines-${index}-unit_price"
               value="">
        <input type="hidden" name="lines-${index}-discount_amount"
               id="id_lines-${index}-discount_amount" value="0">
        <input type="hidden" name="lines-${index}-memo" id="id_lines-${index}-memo" value="">
        <input type="number" class="form-control form-control-sm price-unit-input text-end"
               step="0.01" min="0" value="" placeholder="0.00">
      </td>

      <td class="num-cell readonly-cell line-subtotal text-end">0.00</td>
      <td class="num-cell readonly-cell line-igv text-end">0.00</td>
      <td class="num-cell readonly-cell line-total fw-semibold text-end">0.00</td>

      <td class="text-center">
        <input type="hidden" name="lines-${index}-id" value="">
        <button type="button" class="btn btn-sm btn-outline-danger remove-line" title="Eliminar">
          <i class="ti ti-x"></i>
        </button>
      </td>`;
    return row;
  }

  // ── Product selected event ─────────────────────────────────────────────────
  linesBody.addEventListener('product-picker:selected', event => {
    const row     = event.target.closest('.line-row');
    const product = event.detail;

    setUnitSelect(row, product.unit_id, product.unit);

    // Fill description hidden field
    const descHidden = row.querySelector('input[name*="-description"]');
    if (descHidden) descHidden.value = product.name || '';

    // Fill precio_unitario (inc-IGV) from price_sale
    const priceInput = row.querySelector('.price-unit-input');
    if (priceInput && parseFloat(product.price_sale) > 0) {
      priceInput.value = parseFloat(product.price_sale).toFixed(2);
    }

    calcRow(row);
    updateSummary();
  });

  linesBody.addEventListener('product-picker:cleared', event => {
    const row = event.target.closest('.line-row');
    setUnitSelect(row, '', '—');
    const priceInput = row.querySelector('.price-unit-input');
    if (priceInput) priceInput.value = '';
    const unitPriceHidden = row.querySelector('input[name*="-unit_price"]');
    if (unitPriceHidden) unitPriceHidden.value = '';
    updateSummary();
  });

  // ── Input events for recalculation ────────────────────────────────────────
  linesBody.addEventListener('input', event => {
    if (event.target.matches('.price-unit-input, input[name*="-quantity"]')) {
      const row = event.target.closest('.line-row');
      if (row) { calcRow(row); updateSummary(); }
    }
  });

  linesBody.addEventListener('change', event => {
    if (event.target.matches('select[name*="-tax_type"]')) {
      const row = event.target.closest('.line-row');
      if (row) { calcRow(row); updateSummary(); }
    }
  });

  // ── Add / Remove lines ─────────────────────────────────────────────────────
  document.getElementById('add-line').addEventListener('click', () => {
    const index = parseInt(totalForms().value, 10);
    const row   = buildRow(index);
    linesBody.appendChild(row);
    totalForms().value = index + 1;
    renumber();
    ProductPicker.init(row);
    ProductPicker.open(row);
  });

  linesBody.addEventListener('click', event => {
    const btn = event.target.closest('.remove-line');
    if (!btn) return;

    const row      = btn.closest('.line-row');
    const delCheck = row.querySelector('input[type=checkbox][name$="-DELETE"]');

    if (linesBody.querySelectorAll('.line-row:not([style*="opacity"])').length <= 1) return;

    if (delCheck) {
      delCheck.checked = true;
      row.style.opacity    = '0.3';
      row.style.pointerEvents = 'none';
    } else {
      ProductPicker.destroy(row);
      row.remove();
      reindex();
    }
    updateSummary();
  });

  // ── Customer AJAX Select2 ──────────────────────────────────────────────────
  document.querySelectorAll('.partner-select').forEach(function (el) {
    const searchUrl   = el.dataset.partnerUrl;
    const hiddenId    = el.dataset.hiddenId;
    const placeholder = el.dataset.placeholder || 'Buscar…';

    $(el).select2({
      theme: 'bootstrap-5',
      width: '100%',
      dropdownParent: $('body'),
      placeholder,
      allowClear: true,
      minimumInputLength: 0,
      ajax: {
        transport(params, success, failure) {
          window.ApiService.get(searchUrl + '?q=' + encodeURIComponent(params.data.term || ''))
            .then(success).catch(failure);
        },
        processResults(data) { return { results: data.results || [] }; },
        delay: 250,
      },
    });

    $(el).on('select2:select', function (e) {
      const hidden = document.getElementById(hiddenId);
      if (hidden) hidden.value = e.params.data.id || '';
    });
    $(el).on('select2:unselect select2:clear', function () {
      const hidden = document.getElementById(hiddenId);
      if (hidden) hidden.value = '';
    });
  });

  // ── Price list ─────────────────────────────────────────────────────────────
  let pendingPriceListId = null;

  document.getElementById('price-list-select')?.addEventListener('change', function () {
    const plId = this.value;
    if (!plId) { pendingPriceListId = null; hidePriceAlert(); return; }

    // Check if any product is already selected
    const hasProducts = !!linesBody.querySelector('input[name*="-product"][value]:not([value=""])');
    if (!hasProducts) {
      // No products yet — apply silently when products are added
      pendingPriceListId = plId;
      return;
    }

    pendingPriceListId = plId;
    document.getElementById('price-list-alert')?.classList.remove('d-none');
  });

  function hidePriceAlert() {
    document.getElementById('price-list-alert')?.classList.add('d-none');
  }

  document.getElementById('price-list-cancel')?.addEventListener('click', function () {
    pendingPriceListId = null;
    document.getElementById('price-list-select').value = '';
    hidePriceAlert();
  });

  document.getElementById('price-list-confirm')?.addEventListener('click', async function () {
    hidePriceAlert();
    if (!pendingPriceListId) return;
    await applyPriceList(pendingPriceListId);
  });

  async function applyPriceList(plId) {
    const productIds = [];
    linesBody.querySelectorAll('input[name*="-product"]').forEach(el => {
      if (el.value) productIds.push(el.value);
    });
    if (!productIds.length) return;

    const url = PRICE_LIST_URL_TPL.replace('00000000-0000-0000-0000-000000000000', plId)
                + '?products=' + productIds.join(',');
    try {
      const data = await window.ApiService.get(url);
      const prices = data.prices || {};

      linesBody.querySelectorAll('.line-row').forEach(row => {
        const productId = row.querySelector('input[name*="-product"]')?.value;
        if (!productId || !(productId in prices)) return;

        const priceInput = row.querySelector('.price-unit-input');
        if (priceInput) priceInput.value = parseFloat(prices[productId]).toFixed(2);
        calcRow(row);
      });
      updateSummary();
    } catch (e) {
      console.error('Error applying price list', e);
    }
  }

  // ── Init existing rows (edit / copy) ──────────────────────────────────────
  function initRow(row) {
    const unitLabel = row.dataset.initUnit   || '—';
    const unitId    = row.dataset.initUnitId || '';
    setUnitSelect(row, unitId, unitLabel);
    ProductPicker.init(row);

    // If unit_price (ex-tax) is set but price-unit-input is empty, compute inc-tax
    const priceInput = row.querySelector('.price-unit-input');
    const unitHidden = row.querySelector('input[name*="-unit_price"]');
    if (priceInput && !priceInput.value && unitHidden?.value) {
      priceInput.value = (parseFloat(unitHidden.value) * IGV_MULT).toFixed(2);
    }

    // Sync igv_rate hidden → igv display
    const igvHidden  = row.querySelector('input[name*="-igv_rate"]');
    const igvDisplay = row.querySelector('.igv-rate-display');
    if (igvHidden && igvDisplay && igvHidden.value) {
      igvDisplay.value = igvHidden.value;
    }

    calcRow(row);
  }

  linesBody.querySelectorAll('.line-row').forEach(initRow);
  updateSummary();
  renumber();

}());
