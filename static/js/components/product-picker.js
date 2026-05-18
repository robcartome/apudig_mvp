/**
 * product-picker.js — Reusable Select2 product picker.
 *
 * Responsibilities:
 *   - Initialize / destroy Select2 on a row's .product-select element
 *   - Keep the hidden Django product input in sync
 *   - Trigger generic DOM events for consumers:
 *       • product-picker:selected
 *       • product-picker:cleared
 *   - Handle quick product creation through a configurable modal
 *
 * Requires: jQuery, Select2, bootstrap, window.ApiService, window.Select2Plugin
 * Exposes: window.ProductPicker = { configure, init, destroy, open }
 */
window.ProductPicker = (function ($) {
  'use strict';

  const DEFAULTS = {
    searchUrl: '',
    createUrl: '',
    csrfToken: '',
    getWarehouse: () => '',
    modalId: 'quickCreateModal',
    errorId: 'qc-error',
    nameId: 'qc-name',
    skuId: 'qc-sku',
    unitId: 'qc-unit',
    saveButtonId: 'qc-btn-save',
  };

  let settings = { ...DEFAULTS };
  let quickCreateRow = null;
  let saveAttached = false;

  function configure(options) {
    settings = { ...settings, ...options };
  }

  function ensureConfigured() {
    if (!settings.searchUrl || !settings.createUrl || !settings.csrfToken) {
      throw new Error('ProductPicker requires searchUrl, createUrl and csrfToken.');
    }
  }

  function getElement(id) {
    return document.getElementById(id);
  }

  function esc(str) {
    return $('<div>').text(str || '').html();
  }

  function getWarehouse() {
    return typeof settings.getWarehouse === 'function' ? settings.getWarehouse() : '';
  }

  function emitSelected(row, product) {
    const hiddenInput = row.querySelector('input[type=hidden][name*="-product"]');
    if (hiddenInput) hiddenInput.value = product.id;

    row.dispatchEvent(new CustomEvent('product-picker:selected', {
      bubbles: true,
      detail: product,
    }));
  }

  function emitCleared(row) {
    const hiddenInput = row.querySelector('input[type=hidden][name*="-product"]');
    if (hiddenInput) hiddenInput.value = '';

    row.dispatchEvent(new CustomEvent('product-picker:cleared', {
      bubbles: true,
    }));
  }

  function openCreateModal(row, term) {
    quickCreateRow = row;

    getElement(settings.nameId).value = term || '';
    getElement(settings.skuId).value = '';
    getElement(settings.unitId).value = '';

    const errorEl = getElement(settings.errorId);
    if (errorEl) errorEl.classList.add('d-none');

    bootstrap.Modal.getOrCreateInstance(getElement(settings.modalId)).show();
  }

  function attachSaveHandler() {
    if (saveAttached) return;
    saveAttached = true;

    getElement(settings.saveButtonId).addEventListener('click', async () => {
      const name = getElement(settings.nameId).value.trim();
      const sku = getElement(settings.skuId).value.trim();
      const unitId = getElement(settings.unitId).value;
      const button = getElement(settings.saveButtonId);
      const errorEl = getElement(settings.errorId);

      if (!name || !unitId) {
        if (errorEl) {
          errorEl.textContent = !name
            ? 'El nombre del producto es requerido.'
            : 'Seleccione una unidad de medida.';
          errorEl.classList.remove('d-none');
        }
        return;
      }

      button.disabled = true;
      try {
        const product = await ApiService.post(
          settings.createUrl,
          { name, sku, unit_id: unitId },
          settings.csrfToken
        );

        bootstrap.Modal.getInstance(getElement(settings.modalId)).hide();

        if (quickCreateRow) {
          const $select = $(quickCreateRow).find('.product-select');
          const option = new Option(product.name, product.id, true, true);
          $select.append(option).trigger('change');
          emitSelected(quickCreateRow, product);
        }
      } catch (error) {
        if (errorEl) {
          errorEl.textContent = error.message || 'Error al crear el producto.';
          errorEl.classList.remove('d-none');
        }
      } finally {
        button.disabled = false;
      }
    });
  }

  function renderOption(product) {
    if (product.loading || product.disabled) {
      return $('<div class="text-muted" style="font-size:.85rem">').text(product.text);
    }

    if (product._isCreate) {
      return $(`<div class="d-flex align-items-center gap-2 py-1 text-primary fw-semibold"
                     style="font-size:.85rem">
        <i class="ti ti-plus fs-5"></i>
        <span>Crear <strong>${esc(product.text)}</strong></span>
      </div>`);
    }

    const totalStock = (product.total_stock !== null && product.total_stock !== undefined) ? product.total_stock : '—';
    const stockClass = typeof totalStock === 'number'
      ? (totalStock > 0 ? 'text-success' : totalStock < 0 ? 'text-danger' : 'text-muted')
      : 'text-muted';

    return $(`
      <div class="d-flex justify-content-between align-items-start gap-3 py-1">
        <div style="min-width:0">
          <div class="fw-semibold text-truncate" style="font-size:.85rem">${esc(product.sku || 'SIN-COD')} | ${esc(product.name || product.text)}</div>
          <div class="text-muted" style="font-size:.72rem">
            Stock total: <strong class="${stockClass}">${totalStock}</strong>
            ${esc(product.unit || '')}
          </div>
        </div>
        <div class="text-end text-muted flex-shrink-0" style="font-size:.72rem">
          P.Compra<br><strong>S/ ${parseFloat(product.price_purchase || 0).toFixed(2)}</strong>
        </div>
      </div>`);
  }

  function buildSelectedLabel(product) {
    const code = product.sku || 'SIN-COD';
    const name = product.name || product.text || '';
    const total = (product.total_stock !== null && product.total_stock !== undefined) ? product.total_stock : '—';
    return `${code} | ${name} | Stock Total: ${total}`;
  }

  function renderSelection(product) {
    return $('<div>').text(buildSelectedLabel(product));
  }

  function init(row) {
    ensureConfigured();
    attachSaveHandler();

    const $select = $(row).find('.product-select');
    if (!$select.length || $select.data('select2')) return;

    $select.select2(window.Select2Plugin.build({
      placeholder: 'Buscar producto…',
      allowClear: true,
      minimumInputLength: 0,
      language: {
        noResults: () => 'No se encontró el producto',
        searching: () => 'Buscando…',
        inputTooShort: () => '',
        loadingMore: () => 'Cargando más resultados…',
      },
      ajax: {
        delay: 300,
        transport(params, success, failure) {
          const term = (params.data.q || '').trim();
          ApiService.get(
            `${settings.searchUrl}?q=${encodeURIComponent(term)}&warehouse=${encodeURIComponent(getWarehouse())}`
          ).then(success).catch(failure);
        },
        data: params => ({ q: params.term || '' }),
        processResults(data, params) {
          const term = (params.term || '').trim();
          const results = (data.products || []).map(product => ({
            id: product.id,
            text: product.name,
            ...product,
          }));

          if (term.length >= 3) {
            results.push({ id: '__create__', text: term, _isCreate: true });
          }

          return { results };
        },
      },
      templateResult: renderOption,
      templateSelection: renderSelection,
    }));

    $select.on('select2:select', function (event) {
      const product = event.params.data;
      const currentRow = $(this).closest('.line-row')[0];

      if (product.id === '__create__') {
        $(this).val(null).trigger('change');
        openCreateModal(currentRow, product.text);
        return;
      }

      emitSelected(currentRow, product);
    });

    $select.on('select2:clear', function () {
      emitCleared($(this).closest('.line-row')[0]);
    });
  }

  function destroy(row) {
    const $select = $(row).find('.product-select');
    if ($select.data('select2')) $select.select2('destroy');
  }

  function open(row) {
    const $select = $(row).find('.product-select');
    if ($select.data('select2')) $select.select2('open');
  }

  return { configure, init, destroy, open };
}(jQuery));