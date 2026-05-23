/**
 * movement-form.js — Inventory movement form behavior.
 *
 * Responsibilities:
 *   - Configure the reusable ProductPicker component
 *   - Handle formset add / remove / reindex logic
 *   - Update unit, stock and price when a product is selected
 *   - Refresh stock when warehouse changes
 */
(function () {
  'use strict';

  const linesBody = document.getElementById('lines-body');
  if (!linesBody) return;

  const configEl = document.getElementById('inv-form-config');
  const stockUrl = configEl.dataset.stockUrl;
  const locationUrl = configEl.dataset.locationUrl;
  const movementType = configEl.dataset.movementType;
  const showUnitPrice = configEl.dataset.showUnitPrice === '1';
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  const warehouseInput = document.getElementById(
    movementType === 'TRANSFER' ? 'id_warehouse_origin' : 'id_warehouse'
  );

  const getWarehouse = () => warehouseInput?.value || '';

  ProductPicker.configure({
    searchUrl: configEl.dataset.searchUrl,
    createUrl: configEl.dataset.createUrl,
    csrfToken,
    getWarehouse,
    modalId: 'quickCreateModal',
    errorId: 'qc-error',
    nameId: 'qc-name',
    skuId: 'qc-sku',
    unitId: 'qc-unit',
    saveButtonId: 'qc-btn-save',
  });

  function setUnitSelect(row, unitId, unitLabel) {
    const unitSelect = row.querySelector('.product-unit-select');
    if (!unitSelect) return;

    const value = unitId || '';
    const label = unitLabel || '—';
    unitSelect.innerHTML = `<option value="${value}">${label}</option>`;
    unitSelect.value = value;
  }

  function setStockEl(row, value) {
    const stockInput = row.querySelector('.product-stock');
    if (!stockInput) return;

    if (value === null || value === undefined) {
      stockInput.value = '—';
      stockInput.classList.remove('text-success', 'text-danger');
      stockInput.classList.add('text-muted');
      return;
    }

    stockInput.value = String(value);
    stockInput.classList.remove('text-success', 'text-danger', 'text-muted');
    stockInput.classList.add(value > 0 ? 'text-success' : value < 0 ? 'text-danger' : 'text-muted');
  }

  async function refreshStock(row) {
    const hiddenInput = row.querySelector('input[type=hidden][name*="-product"]');
    const warehouse = getWarehouse();

    if (!hiddenInput?.value || !warehouse) {
      setStockEl(row, null);
      return;
    }

    try {
      const data = await ApiService.get(
        `${stockUrl}?product=${encodeURIComponent(hiddenInput.value)}&warehouse=${encodeURIComponent(warehouse)}`
      );
      setStockEl(row, data.stock);
    } catch {
      setStockEl(row, null);
    }
  }

  function totalForms() {
    return document.getElementById('id_lines-TOTAL_FORMS');
  }

  function renumber() {
    linesBody.querySelectorAll('.line-row').forEach((row, index) => {
      const lineNumber = row.querySelector('.line-num');
      if (lineNumber) lineNumber.textContent = index + 1;
    });
  }

  function reindex() {
    linesBody.querySelectorAll('.line-row').forEach((row, index) => {
      row.querySelectorAll('[name]').forEach(element => {
        element.name = element.name.replace(/-\d+-/, `-${index}-`);
      });
      row.querySelectorAll('[id]').forEach(element => {
        if (element.id) element.id = element.id.replace(/-\d+-/, `-${index}-`);
      });
    });

    totalForms().value = linesBody.querySelectorAll('.line-row').length;
    renumber();
  }

  function buildRow(index) {
    const row = document.createElement('tr');
    row.className = 'line-row';
    const unitPriceCell = showUnitPrice
      ? `<td>
        <input type="number" name="lines-${index}-unit_price" id="id_lines-${index}-unit_price"
               class="form-control form-control-sm" step="0.001" min="0" value="">
      </td>`
      : '';

    row.innerHTML = `
      <td class="text-center text-muted line-num">${index + 1}</td>
      <td style="min-width:220px">
        <input type="hidden" name="lines-${index}-product" id="id_lines-${index}-product" value="">
        <select class="product-select w-100"></select>
      </td>
      <td>
        <select class="form-select form-select-sm product-unit-select" disabled
                title="La unidad se define por producto. Cuando existan equivalencias se habilitará.">
          <option value="">—</option>
        </select>
      </td>
      <td>
        <input type="number" name="lines-${index}-quantity" id="id_lines-${index}-quantity"
               class="form-control form-control-sm" step="0.001" min="0.001" value="">
      </td>
      <td>
        <input type="text" class="form-control form-control-sm product-stock text-end text-muted"
               value="—" disabled readonly>
      </td>
      <td style="min-width:160px">
        <input type="hidden" name="lines-${index}-location" id="id_lines-${index}-location" value="">
        <select class="location-select w-100"
                data-location-url="${locationUrl}"
                data-placeholder="Ubicación (opcional)">
        </select>
      </td>
      ${unitPriceCell}
      <td class="text-center">
        <button type="button" class="btn btn-sm btn-outline-danger remove-line" title="Eliminar fila">
          <i class="ti ti-x"></i>
        </button>
      </td>`;

    return row;
  }

  linesBody.addEventListener('product-picker:selected', event => {
    const row = event.target.closest('.line-row');
    const product = event.detail;

    setUnitSelect(row, product.unit_id, product.unit);
    setStockEl(row, product.stock !== undefined ? product.stock : null);

    const priceInput = row.querySelector('input[name*="-unit_price"]');
    if (priceInput && parseFloat(product.price_purchase) > 0 &&
        (!priceInput.value || priceInput.value === '0' || priceInput.value === '0.000')) {
      priceInput.value = parseFloat(product.price_purchase).toFixed(3);
    }
  });

  linesBody.addEventListener('product-picker:cleared', event => {
    const row = event.target.closest('.line-row');
    setUnitSelect(row, '', '—');
    setStockEl(row, null);
  });

  if (warehouseInput) {
    warehouseInput.addEventListener('change', () => {
      linesBody.querySelectorAll('.line-row').forEach(refreshStock);
      linesBody.querySelectorAll('.line-row').forEach(row => {
        const $loc = $(row).find('.location-select');
        if ($loc.data('select2')) {
          $loc.val(null).trigger('change');
          $loc.select2('destroy');
          const hiddenInput = row.querySelector('input[type=hidden][name*="-location"]');
          if (hiddenInput) hiddenInput.value = '';
          initLocationSelect(row);
        }
      });
    });
  }

  document.getElementById('add-line').addEventListener('click', () => {
    const index = parseInt(totalForms().value, 10);
    const row = buildRow(index);

    linesBody.appendChild(row);
    totalForms().value = index + 1;
    renumber();

    ProductPicker.init(row);
    ProductPicker.open(row);
    initLocationSelect(row);
  });

  linesBody.addEventListener('click', event => {
    const button = event.target.closest('.remove-line');
    if (!button) return;

    const row = button.closest('.line-row');
    if (linesBody.querySelectorAll('.line-row').length <= 1) return;

    ProductPicker.destroy(row);
    row.remove();
    reindex();
  });

  function init() {
    renumber();
    linesBody.querySelectorAll('.line-row').forEach(row => {
      const unitLabel = row.dataset.initUnit || row.querySelector('.product-unit-select option')?.textContent || '—';
      const unitId = row.dataset.initUnitId || row.querySelector('.product-unit-select option')?.value || '';
      setUnitSelect(row, unitId, unitLabel);
      ProductPicker.init(row);
      refreshStock(row);
    });
  }

  init();

  // ── Partner (Supplier / Customer) Select2 pickers ──────────────────────
  function initPartnerSelects() {
    document.querySelectorAll('.partner-select').forEach(function (el) {
      const searchUrl  = el.dataset.partnerUrl;
      const hiddenId   = el.dataset.hiddenId;
      const placeholder = el.dataset.placeholder || 'Buscar…';
      const $el = $(el);

      $el.select2({
        theme: 'bootstrap-5',
        width: '100%',
        dropdownParent: $('body'),
        placeholder: placeholder,
        allowClear: true,
        minimumInputLength: 0,
        ajax: {
          transport: function (params, success, failure) {
            window.ApiService.get(searchUrl + '?q=' + encodeURIComponent(params.data.term || ''))
              .then(success)
              .catch(failure);
          },
          processResults: function (data) {
            return { results: data.results || [] };
          },
          delay: 250,
        },
      });

      $el.on('select2:select', function (e) {
        document.getElementById(hiddenId).value = e.params.data.id || '';
      });
      $el.on('select2:unselect select2:clear', function () {
        document.getElementById(hiddenId).value = '';
      });
    });
  }

  initPartnerSelects();

  // ── Reason field: Select2 with tags (predefined + free text) ────────────
  function initReasonSelect() {
    const el = document.getElementById('id_reason_ui');
    if (!el) return;
    const initVal = el.dataset.init || '';

    // If editing and value is not in predefined list, add it as an option
    if (initVal) {
      let found = false;
      for (let i = 0; i < el.options.length; i++) {
        if (el.options[i].value === initVal) { found = true; el.options[i].selected = true; break; }
      }
      if (!found) {
        const opt = new Option(initVal, initVal, true, true);
        el.prepend(opt);
      }
    } else {
      // New form: select first option by default
      el.selectedIndex = 0;
    }

    $(el).select2({
      theme: 'bootstrap-5',
      width: '100%',
      dropdownParent: $('body'),
      placeholder: '— Seleccionar o escribir operación —',
      allowClear: true,
      tags: true,
      createTag: function (params) {
        const term = $.trim(params.term);
        if (!term) return null;
        return { id: term, text: term, newTag: true };
      },
    });
  }

  initReasonSelect();

  // ── Location select (per row, AJAX) ─────────────────────────────────────
  function initLocationSelect(row) {
    const el = row.querySelector('.location-select');
    if (!el || $(el).data('select2')) return;

    const url = el.dataset.locationUrl || locationUrl;

    $(el).select2({
      theme: 'bootstrap-5',
      width: '100%',
      dropdownParent: $('body'),
      placeholder: el.dataset.placeholder || 'Ubicación (opcional)',
      allowClear: true,
      minimumInputLength: 0,
      ajax: {
        transport: function (params, success, failure) {
          const warehouse = getWarehouse();
          const q = encodeURIComponent(params.data.term || '');
          window.ApiService.get(`${url}?warehouse=${encodeURIComponent(warehouse)}&q=${q}`)
            .then(success).catch(failure);
        },
        processResults: function (data) {
          return { results: data.results || [] };
        },
        delay: 250,
      },
    });

    $(el).on('select2:select', function (e) {
      const hiddenInput = row.querySelector('input[type=hidden][name*="-location"]');
      if (hiddenInput) hiddenInput.value = e.params.data.id || '';
    });
    $(el).on('select2:unselect select2:clear', function () {
      const hiddenInput = row.querySelector('input[type=hidden][name*="-location"]');
      if (hiddenInput) hiddenInput.value = '';
    });
  }

  function initAllLocationSelects() {
    linesBody.querySelectorAll('.line-row').forEach(initLocationSelect);
  }

  initAllLocationSelects();
}());