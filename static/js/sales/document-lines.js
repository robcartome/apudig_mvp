/**
 * document-lines.js — Shared behavior for sales document line forms.
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

  const configEl  = document.getElementById('sales-form-config');
  let IGV_RATE = parseFloat(document.getElementById('id_igv_rate_default')?.value)
               || parseFloat(configEl.dataset.igvRate) || 18;
  let IGV_MULT = 1 + IGV_RATE / 100;             // e.g. 1.18
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  // Build the price-list API URL template (replace the placeholder UUID)
  const PRICE_LIST_URL_TPL = configEl.dataset.priceListUrl;
  const DEFAULT_PRICE_LIST_ID = configEl.dataset.defaultPriceListId || '';

  // TAX_TYPE_CHOICES (must match sales/models.py)
  const TAX_TYPES = [
    ['10', 'Gravado IGV'],
    ['20', 'Exonerado'],
    ['30', 'Inafecto'],
    ['40', 'Exportación'],
    ['11', 'IGV retiro'],
  ];

  const TAXED = new Set(['10']);

  // ── IGV rate header select ────────────────────────────────────────────────
  document.getElementById('id_igv_rate_default')?.addEventListener('change', function () {
    IGV_RATE = parseFloat(this.value) || 18;
    IGV_MULT = 1 + IGV_RATE / 100;
    configEl.dataset.igvRate = IGV_RATE;
    linesBody.querySelectorAll('input[name*="-igv_rate"]').forEach(el => { el.value = IGV_RATE; });
    updateSummary(); // recalcula todas las filas, incl. valor-unit-display
  });

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

  // ── Flatpickr date pickers (no usado — se usa datetime-local nativo) ──────────────────
  // Los campos de fecha usan type="datetime-local" con el picker nativo del navegador.

  // ── Helpers ────────────────────────────────────────────────────────────────
  function setUnitSelect(row, unitId, unitLabel) {
    const sel = row.querySelector('.product-unit-select');
    if (!sel) return;
    sel.innerHTML = `<option value="${unitId || ''}">${unitLabel || '—'}</option>`;
  }

  function fmt(n) { return isFinite(n) ? n.toFixed(2) : '0.00'; }
  function priceListSelect() {
    return document.getElementById('id_price_list') || document.getElementById('price-list-select');
  }

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

    // Actualizar Valor Unit. (precio ex-IGV)
    const valorCell = row.querySelector('.valor-unit-display');
    if (valorCell) valorCell.value = fmt(unitPriceEx);

    return { subtotal, igvAmt, lineTotal, discount, taxType };
  }

  // ── Grand totals ───────────────────────────────────────────────────────────
  function updateSummary() {
    let sumSub = 0, sumDisc = 0, sumBase = 0, sumExempt = 0;
    let sumUnaffected = 0, sumExport = 0, sumFree = 0, sumIgv = 0, sumTotal = 0;

    linesBody.querySelectorAll('.line-row').forEach(row => {
      if (row.style.opacity === '0.3') return;          // deleted rows
      const { subtotal, igvAmt, lineTotal, discount, taxType } = calcRow(row);
      sumSub   += subtotal;
      sumDisc  += discount;
      if (taxType === '10') sumBase += subtotal;
      if (taxType === '20') sumExempt += subtotal;
      if (taxType === '30') sumUnaffected += subtotal;
      if (taxType === '40') sumExport += subtotal;
      if (taxType === '11') sumFree += subtotal;
      if (taxType !== '11') {
        sumIgv += igvAmt;
        sumTotal += lineTotal;
      }
    });

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = fmt(val); };
    set('summary-subtotal', sumSub);
    set('summary-discount', sumDisc);
    set('summary-base',     sumBase);
    set('summary-exempt',   sumExempt);
    set('summary-unaffected', sumUnaffected);
    set('summary-export',   sumExport);
    set('summary-free',     sumFree);
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
        <input type="text" class="form-control form-control-sm valor-unit-display text-end"
               value="0.00" disabled readonly tabindex="-1" title="Precio sin IGV">
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

      <td class="text-center" style="white-space:nowrap">
        <input type="hidden" name="lines-${index}-id" value="">
        <button type="button" class="btn btn-sm btn-outline-secondary memo-btn" title="Agregar memo">
          <i class="ti ti-notes"></i>
        </button>
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

    // Auto-apply selected price list price (overrides price_sale if found)
    const plId = priceListSelect()?.value;
    if (plId && PRICE_LIST_URL_TPL && product.id) {
      const url = PRICE_LIST_URL_TPL.replace('00000000-0000-0000-0000-000000000000', plId)
                  + '?products=' + product.id;
      window.ApiService.get(url).then(data => {
        const price = (data.prices || {})[product.id];
        if (price && priceInput) {
          priceInput.value = parseFloat(price).toFixed(2);
          calcRow(row);
          updateSummary();
        }
      }).catch(() => {});
    }
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
      // Fill address display
      const addressDisplay = document.getElementById('customer-address-display');
      if (addressDisplay) addressDisplay.value = e.params.data.address || '';
    });
    $(el).on('select2:unselect select2:clear', function () {
      const hidden = document.getElementById(hiddenId);
      if (hidden) hidden.value = '';
    });
  });

  // ── Price list ─────────────────────────────────────────────────────────────
  let pendingPriceListId = null;

  // Pre-select default price list if none already chosen
  const plSelect = priceListSelect();
  if (plSelect && !plSelect.value && DEFAULT_PRICE_LIST_ID) {
    plSelect.value = DEFAULT_PRICE_LIST_ID;
    pendingPriceListId = DEFAULT_PRICE_LIST_ID;
  }

  plSelect?.addEventListener('change', function () {
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
    if (plSelect) plSelect.value = '';
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

  // ── Barcode search ──────────────────────────────────────────────────────────
  function searchByBarcode() {
    const barcode = document.getElementById('barcode-search')?.value?.trim();
    if (!barcode) return;
    window.ApiService.get(configEl.dataset.searchUrl + '?q=' + encodeURIComponent(barcode))
      .then(function (data) {
        const results = data.results || [];
        if (!results.length) {
          alert('No se encontró producto con código: ' + barcode);
          return;
        }
        const product = results[0];
        const index   = parseInt(totalForms().value, 10);
        const row     = buildRow(index);
        linesBody.appendChild(row);
        totalForms().value = index + 1;
        renumber();
        ProductPicker.init(row);

        const productHidden = row.querySelector('input[name*="-product"]');
        if (productHidden) productHidden.value = product.id;

        const productSelect = row.querySelector('.product-select');
        if (productSelect) {
          $(productSelect).append(new Option(product.text || product.name, product.id, true, true)).trigger('change');
        }

        row.dispatchEvent(new CustomEvent('product-picker:selected', {
          detail: product,
          bubbles: true,
        }));

        document.getElementById('barcode-search').value = '';
      })
      .catch(function (err) { console.error('Barcode search error', err); });
  }

  document.getElementById('barcode-btn')?.addEventListener('click', searchByBarcode);
  document.getElementById('barcode-search')?.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); searchByBarcode(); }
  });

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
    updateMemoBtnStyle(row);
  }

  linesBody.querySelectorAll('.line-row').forEach(initRow);
  updateSummary();
  renumber();

  // Auto-agregar primera fila en formularios nuevos (extra=0 no renderiza filas vacías)
  if (linesBody.querySelectorAll('.line-row').length === 0) {
    document.getElementById('add-line')?.click();
  }

  // ── Memo modal ─────────────────────────────────────────────────────────────
  let _memoRow = null;
  const memoModal = new bootstrap.Modal(document.getElementById('memoModal'));

  function updateMemoBtnStyle(row) {
    const memoInput = row.querySelector('input[name*="-memo"]');
    const btn       = row.querySelector('.memo-btn');
    if (!btn) return;
    const hasMemo = memoInput && memoInput.value.trim().length > 0;
    btn.classList.toggle('btn-secondary',         hasMemo);
    btn.classList.toggle('btn-outline-secondary', !hasMemo);
    const icon = btn.querySelector('i');
    if (icon) {
      icon.classList.toggle('ti-notes-off', false);
    }
  }

  linesBody.addEventListener('click', function (e) {
    const btn = e.target.closest('.memo-btn');
    if (!btn) return;
    _memoRow = btn.closest('.line-row');
    const memoInput = _memoRow?.querySelector('input[name*="-memo"]');
    document.getElementById('memo-modal-text').value = memoInput?.value || '';
    memoModal.show();
  });

  document.getElementById('memo-modal-save')?.addEventListener('click', function () {
    if (!_memoRow) return;
    const memoInput = _memoRow.querySelector('input[name*="-memo"]');
    const text      = document.getElementById('memo-modal-text').value.trim().slice(0, 1000);
    if (memoInput) memoInput.value = text;
    updateMemoBtnStyle(_memoRow);
    memoModal.hide();
    _memoRow = null;
  });

  // ── Número preview ────────────────────────────────────────────────────────
  const SERIES_NUMBER_URL_TPL = configEl.dataset.seriesNumberUrl || '';

  async function refreshSeriesNumber() {
    const seriesEl = document.querySelector('select[name="series"]');
    const seriesId = seriesEl?.value;
    if (!seriesId || !SERIES_NUMBER_URL_TPL) return;
    const url = SERIES_NUMBER_URL_TPL.replace('00000000-0000-0000-0000-000000000000', seriesId);
    try {
      const data = await window.ApiService.get(url);
      const preview = document.getElementById('series-number-preview');
      if (preview) preview.value = data.formatted || data.next_number || '';
      document.getElementById('series-number-conflict')?.classList.add('d-none');
    } catch (err) {
      console.error('Error al obtener número de serie', err);
    }
  }

  document.querySelector('select[name="series"]')?.addEventListener('change', refreshSeriesNumber);
  document.getElementById('refresh-number-btn')?.addEventListener('click', refreshSeriesNumber);

  // Cargar al iniciar si ya hay una serie seleccionada
  if (document.querySelector('select[name="series"]')?.value) refreshSeriesNumber();

}());
