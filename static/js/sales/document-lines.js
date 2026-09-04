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
  const editValue = configEl.dataset.editValue === 'true';
  const editPrice = configEl.dataset.editPrice !== 'false';
  const editTotal = configEl.dataset.editTotal === 'true';
  const configuredPriceDecimals = Number(configEl.dataset.priceDecimals);
  const PRICE_DECIMALS = Number.isInteger(configuredPriceDecimals)
    ? Math.min(6, Math.max(0, configuredPriceDecimals)) : 2;
  const PRICE_ZERO = (0).toFixed(PRICE_DECIMALS);
  const PRICE_STEP = PRICE_DECIMALS === 0 ? '1' : `0.${'0'.repeat(PRICE_DECIMALS - 1)}1`;
  const headerIgvRate = parseFloat(document.getElementById('id_igv_rate_default')?.value);
  const configuredIgvRate = parseFloat(configEl.dataset.igvRate);
  let IGV_RATE = Number.isFinite(headerIgvRate)
    ? headerIgvRate : (Number.isFinite(configuredIgvRate) ? configuredIgvRate : 18);
  let IGV_MULT = 1 + IGV_RATE / 100;             // e.g. 1.18
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
    const rate = parseFloat(this.value);
    IGV_RATE = Number.isFinite(rate) ? rate : 18;
    IGV_MULT = 1 + IGV_RATE / 100;
    configEl.dataset.igvRate = IGV_RATE;
    linesBody.querySelectorAll('input[name*="-igv_rate"]').forEach(el => { el.value = IGV_RATE; });
    updateSummary(); // recalcula todas las filas, incl. valor-unit-display
  });

  // ── ProductPicker ──────────────────────────────────────────────────────────
  ProductPicker.configure({
    searchUrl: configEl.dataset.searchUrl,
    createUrl: configEl.dataset.createUrl,
    getWarehouse: () => '',
    modalId: 'quickCreateModal',
    errorId: 'qc-error',
    nameId: 'qc-name',
    skuId: 'qc-sku',
    unitId: 'qc-unit',
    saveButtonId: 'qc-btn-save',
    priceDecimals: PRICE_DECIMALS,
  });

  // ── Flatpickr date pickers (no usado — se usa datetime-local nativo) ──────────────────
  // Los campos de fecha usan type="datetime-local" con el picker nativo del navegador.

  // ── Helpers ────────────────────────────────────────────────────────────────
  function setUnitSelect(row, unitId, unitLabel) {
    const sel = row.querySelector('.product-unit-select');
    if (!sel) return;
    const existing = Array.from(sel.options).find(option => option.value === String(unitId || ''));
    if (existing) {
      sel.value = existing.value;
    } else {
      sel.innerHTML = `<option value="${unitId || ''}">${unitLabel || '—'}</option>`;
    }
    const hidden = row.querySelector('input[name*="-unit"]');
    if (hidden) hidden.value = unitId || '';
  }

  function setProductUnits(row, product) {
    const select = row.querySelector('.product-unit-select');
    if (!select) return;
    const units = product.units || [];
    row.dataset.baseUnitId = product.unit_id || '';
    row.dataset.baseUnitCode = product.unit || '';
    const selected = units.find(unit => unit.id === product.unit_id) || units[0];
    select.innerHTML = units.map(unit =>
      `<option value="${unit.id}" data-code="${unit.code}" data-factor="${unit.factor}" data-price="${unit.sale_price ?? ''}">${unit.code} - ${unit.name}</option>`
    ).join('');
    if (selected) select.value = selected.id;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function updateUnitEquivalence(row) {
    const hint = row.querySelector('.unit-equivalence');
    const option = row.querySelector('.product-unit-select')?.selectedOptions[0];
    if (!hint || !option || option.value === row.dataset.baseUnitId) {
      if (hint) hint.textContent = '';
      return;
    }
    const factor = Number(option.dataset.factor || 1);
    const formatQuantity = value => Number(value.toFixed(6)).toString();
    const unitCode = option.dataset.code || option.textContent.split(' - ')[0].trim();
    const quantity = Number(row.querySelector('input[name*="-quantity"]')?.value || 0);
    const total = quantity > 0 ? ` · Total: ${formatQuantity(quantity * factor)} ${row.dataset.baseUnitCode || ''}` : '';
    hint.textContent = `1 ${unitCode} = ${formatQuantity(factor)} ${row.dataset.baseUnitCode || ''}${total}`;
  }

  function fmt(n) { return isFinite(n) ? n.toFixed(PRICE_DECIMALS) : PRICE_ZERO; }
  function normalizeQuantityInput(input) {
    let value = input.value.replace(',', '.').replace(/[^\d.]/g, '');
    const separator = value.indexOf('.');
    if (separator !== -1) {
      value = value.slice(0, separator + 1)
        + value.slice(separator + 1).replace(/\./g, '').slice(0, 2);
    }
    input.value = value;
  }
  function priceForSelectedUnit(row, basePrice) {
    const option = row.querySelector('.product-unit-select')?.selectedOptions[0];
    if (option && option.dataset.price !== undefined && option.dataset.price !== '') {
      return Number(option.dataset.price);
    }
    return Number(basePrice || 0) * Number(option?.dataset.factor || 1);
  }
  function priceListSelect() {
    return document.getElementById('id_price_list') || document.getElementById('price-list-select');
  }

  // ── Per-row calculation ────────────────────────────────────────────────────
  function calcRow(row) {
    const priceIncInput = row.querySelector('input.price-unit-input');
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
        <input type="hidden" name="lines-${index}-unit" id="id_lines-${index}-unit" value="">
        <select class="form-select form-select-sm product-unit-select">
          <option value="">—</option>
        </select>
        <div class="unit-equivalence text-muted mt-1" style="font-size:.7rem"></div>
      </td>

      <td>
        <div class="input-group input-group-sm">
          <input type="text" name="lines-${index}-quantity" id="id_lines-${index}-quantity"
                 class="form-control form-control-sm text-end quantity-input"
                 inputmode="decimal" autocomplete="off" maxlength="15" value="1">
          <button type="button" class="btn btn-outline-secondary stock-info-btn" title="Ver stock por almacén" aria-label="Ver stock por almacén">
            <i class="ti ti-info-circle"></i>
          </button>
        </div>
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
               value="${PRICE_ZERO}" disabled readonly tabindex="-1" title="Precio sin IGV">
      </td>

      <td>
        <input type="hidden" name="lines-${index}-unit_price" id="id_lines-${index}-unit_price"
               value="">
        <input type="hidden" name="lines-${index}-discount_amount"
               id="id_lines-${index}-discount_amount" value="0">
        <input type="hidden" name="lines-${index}-memo" id="id_lines-${index}-memo" value="">
        <input type="number" class="form-control form-control-sm price-unit-input text-end"
               step="${PRICE_STEP}" min="0" value="" placeholder="${PRICE_ZERO}">
      </td>

      <td class="num-cell readonly-cell line-subtotal text-end">${PRICE_ZERO}</td>
      <td class="num-cell readonly-cell line-igv text-end">${PRICE_ZERO}</td>
      <td class="num-cell readonly-cell line-total fw-semibold text-end">${PRICE_ZERO}</td>

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

    row.dataset.basePrice = product.price_sale ?? 0;
    setProductUnits(row, product);

    // Fill description hidden field
    const descHidden = row.querySelector('input[name*="-description"]');
    if (descHidden) descHidden.value = product.name || '';

    // Fill precio_unitario (inc-IGV) from price_sale
    const priceInput = row.querySelector('input.price-unit-input');
    if (priceInput && product.price_sale !== null && product.price_sale !== undefined) {
      priceInput.value = priceForSelectedUnit(row, product.price_sale).toFixed(PRICE_DECIMALS);
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
          row.dataset.basePrice = price;
          priceInput.value = priceForSelectedUnit(row, price).toFixed(PRICE_DECIMALS);
          calcRow(row);
          updateSummary();
        }
      }).catch(() => {});
    }
  });

  linesBody.addEventListener('product-picker:cleared', event => {
    const row = event.target.closest('.line-row');
    setUnitSelect(row, '', '—');
    delete row.dataset.baseUnitId;
    delete row.dataset.baseUnitCode;
    updateUnitEquivalence(row);
    const priceInput = row.querySelector('input.price-unit-input');
    if (priceInput) priceInput.value = '';
    const unitPriceHidden = row.querySelector('input[name*="-unit_price"]');
    if (unitPriceHidden) unitPriceHidden.value = '';
    updateSummary();
  });

  // ── Input events for recalculation ────────────────────────────────────────
  linesBody.addEventListener('input', event => {
    if (event.target.matches('.line-total') && editTotal) {
      const row = event.target.closest('.line-row');
      const qty = parseFloat(row?.querySelector('input[name*="-quantity"]')?.value) || 0;
      const discount = parseFloat(row?.querySelector('input[name*="-discount_amount"]')?.value) || 0;
      const rate = parseFloat(row?.querySelector('input[name*="-igv_rate"]')?.value) || IGV_RATE;
      const taxType = row?.querySelector('select[name*="-tax_type"]')?.value || '10';
      const factor = TAXED.has(taxType) ? 1 + rate / 100 : 1;
      const requestedTotal = parseFloat(event.target.textContent.replace(',', '.')) || 0;
      const priceInput = row?.querySelector('input.price-unit-input');
      if (priceInput && qty > 0) priceInput.value = (((requestedTotal / factor + discount) / qty) * factor).toFixed(PRICE_DECIMALS);
      updateSummary();
    } else if (event.target.matches('input.valor-unit-display')) {
      const row = event.target.closest('.line-row');
      const rate = parseFloat(row?.querySelector('input[name*="-igv_rate"]')?.value) || IGV_RATE;
      const taxType = row?.querySelector('select[name*="-tax_type"]')?.value || '10';
      const factor = TAXED.has(taxType) ? 1 + rate / 100 : 1;
      const priceInput = row?.querySelector('input.price-unit-input');
      if (priceInput) priceInput.value = ((parseFloat(event.target.value) || 0) * factor).toFixed(PRICE_DECIMALS);
      updateSummary();
    } else if (event.target.matches('input.price-unit-input, input[name*="-quantity"]')) {
      const row = event.target.closest('.line-row');
      if (row) {
        if (event.target.matches('input[name*="-quantity"]')) {
          normalizeQuantityInput(event.target);
          updateUnitEquivalence(row);
        }
        calcRow(row);
        updateSummary();
      }
    }
  });

  linesBody.querySelectorAll('.line-row').forEach(row => {
    const valueInput = row.querySelector('.valor-unit-display');
    const priceInput = row.querySelector('.price-unit-input');
    const totalCell = row.querySelector('.line-total');
    if (valueInput) valueInput.readOnly = !editValue;
    if (priceInput) priceInput.readOnly = !editPrice;
    if (totalCell && editTotal) {
      totalCell.contentEditable = 'true';
      totalCell.setAttribute('role', 'textbox');
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

        const priceInput = row.querySelector('input.price-unit-input');
        row.dataset.basePrice = prices[productId];
        if (priceInput) priceInput.value = priceForSelectedUnit(row, prices[productId]).toFixed(PRICE_DECIMALS);
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
    updateUnitEquivalence(row);
    ProductPicker.init(row);

    // If unit_price (ex-tax) is set but price-unit-input is empty, compute inc-tax
    const priceInput = row.querySelector('input.price-unit-input');
    if (priceInput) priceInput.step = PRICE_STEP;
    const unitHidden = row.querySelector('input[name*="-unit_price"]');
    if (priceInput && !priceInput.value && unitHidden?.value) {
      priceInput.value = (parseFloat(unitHidden.value) * IGV_MULT).toFixed(PRICE_DECIMALS);
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
  const memoModalElement = document.getElementById('memoModal');
  const memoModal = memoModalElement ? new bootstrap.Modal(memoModalElement) : null;

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
    if (!btn || !memoModal) return;
    _memoRow = btn.closest('.line-row');
    const memoInput = _memoRow?.querySelector('input[name*="-memo"]');
    document.getElementById('memo-modal-text').value = memoInput?.value || '';
    memoModal.show();
  });

  document.getElementById('memo-modal-save')?.addEventListener('click', function () {
    if (!_memoRow || !memoModal) return;
    const memoInput = _memoRow.querySelector('input[name*="-memo"]');
    const text      = document.getElementById('memo-modal-text').value.trim().slice(0, 1000);
    if (memoInput) memoInput.value = text;
    updateMemoBtnStyle(_memoRow);
    memoModal.hide();
    _memoRow = null;
  });

  // ── Número preview ────────────────────────────────────────────────────────
  const SERIES_NUMBER_URL_TPL = configEl.dataset.seriesNumberUrl || '';
  const SERIES_OPTIONS_URL = configEl.dataset.seriesOptionsUrl || '';
  const NUMBER_AVAILABILITY_URL = configEl.dataset.numberAvailabilityUrl || '';
  const QUOTATION_ID = configEl.dataset.quotationId || '';
  const documentTypeEl = document.querySelector('select[name="document_type"]');
  const seriesEl = document.querySelector('select[name="series"]');
  const numberEl = document.getElementById('id_number');
  const manualNumberEl = document.getElementById('id_manual_number');

  function useAutomaticNumber() {
    if (manualNumberEl) manualNumberEl.value = '';
    if (numberEl) numberEl.readOnly = true;
    document.getElementById('series-number-conflict')?.classList.add('d-none');
  }

  async function validateNumberAvailability() {
    if (!NUMBER_AVAILABILITY_URL || !seriesEl?.value || !numberEl?.value) return true;
    const params = new URLSearchParams({number: numberEl.value});
    if (QUOTATION_ID) params.set('exclude', QUOTATION_ID);
    const warning = document.getElementById('series-number-conflict');
    try {
      const availabilityUrl = NUMBER_AVAILABILITY_URL.replace(
        '00000000-0000-0000-0000-000000000000', seriesEl.value
      );
      const data = await window.ApiService.get(`${availabilityUrl}?${params}`);
      warning?.classList.toggle('d-none', data.available);
      if (warning && !data.available) {
        warning.textContent = data.message;
      }
      numberEl.classList.toggle('is-invalid', !data.available);
      return data.available;
    } catch (err) {
      console.error('Error al validar correlativo', err);
      return false;
    }
  }

  async function refreshSeriesNumber(force = false) {
    const seriesId = seriesEl?.value;
    if (!seriesId || !SERIES_NUMBER_URL_TPL) {
      if (numberEl) numberEl.value = '';
      return;
    }
    if (!force && manualNumberEl?.value) return;
    const url = SERIES_NUMBER_URL_TPL.replace('00000000-0000-0000-0000-000000000000', seriesId);
    try {
      const data = await window.ApiService.get(url);
      if (numberEl) numberEl.value = String(data.next_number || '').padStart(8, '0');
      document.getElementById('series-number-conflict')?.classList.add('d-none');
      validateNumberAvailability();
    } catch (err) {
      console.error('Error al obtener número de serie', err);
    }
  }

  async function refreshSeriesOptions() {
    if (!documentTypeEl || !seriesEl || !SERIES_OPTIONS_URL) return;
    const previousValue = seriesEl.value;
    seriesEl.disabled = true;
    seriesEl.innerHTML = '<option value="">Cargando…</option>';
    useAutomaticNumber();
    if (numberEl) numberEl.value = '';
    try {
      const url = `${SERIES_OPTIONS_URL}?document_type=${encodeURIComponent(documentTypeEl.value)}`;
      const data = await window.ApiService.get(url);
      seriesEl.innerHTML = '<option value="">Seleccionar…</option>';
      (data.results || []).forEach(item => {
        const option = new Option(item.text, item.id, false, item.id === previousValue);
        seriesEl.add(option);
      });
      if (!seriesEl.value && data.results?.length) seriesEl.value = data.results[0].id;
      seriesEl.dispatchEvent(new Event('change'));
    } catch (err) {
      seriesEl.innerHTML = '<option value="">No se pudieron cargar las series</option>';
      console.error('Error al obtener series documentales', err);
    } finally {
      seriesEl.disabled = false;
    }
  }

  seriesEl?.addEventListener('change', () => {
    useAutomaticNumber();
    refreshSeriesNumber(true);
  });

  linesBody.addEventListener('change', event => {
    if (!event.target.matches('.product-unit-select')) return;
    const row = event.target.closest('.line-row');
    const hidden = row?.querySelector('input[name*="-unit"]');
    if (hidden) hidden.value = event.target.value;
    updateUnitEquivalence(row);
    const option = event.target.selectedOptions[0];
    const hasConfiguredPrice = option?.dataset.price !== undefined && option.dataset.price !== '';
    if (!hasConfiguredPrice && row.dataset.basePrice === undefined) return;
    const price = priceForSelectedUnit(row, row.dataset.basePrice || 0);
    const priceInput = row?.querySelector('input.price-unit-input');
    if (priceInput && Number.isFinite(price)) {
      priceInput.value = Number(price).toFixed(PRICE_DECIMALS);
      calcRow(row);
      updateSummary();
    }
  });
  documentTypeEl?.addEventListener('change', refreshSeriesOptions);
  document.getElementById('edit-number-btn')?.addEventListener('click', () => {
    if (!numberEl || !seriesEl?.value) return;
    numberEl.readOnly = false;
    if (manualNumberEl) manualNumberEl.value = 'on';
    document.getElementById('series-number-conflict')?.classList.remove('d-none');
    numberEl.focus();
    numberEl.select();
  });
  numberEl?.addEventListener('input', () => {
    numberEl.value = numberEl.value.replace(/\D/g, '').slice(0, 8);
  });
  numberEl?.addEventListener('blur', validateNumberAvailability);
  document.getElementById('refresh-number-btn')?.addEventListener('click', () => {
    useAutomaticNumber();
    refreshSeriesNumber(true);
  });

  // Cargar al iniciar si ya hay una serie seleccionada
  if (seriesEl?.value && !numberEl?.value) refreshSeriesNumber();

}());
