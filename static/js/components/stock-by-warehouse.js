/** Muestra el stock de la línea actual en todos los almacenes de la empresa. */
(function () {
  'use strict';

  const config = document.getElementById('sales-form-config')
    || document.getElementById('inv-form-config')
    || document.getElementById('purchase-form-config');
  const modalElement = document.getElementById('stockByWarehouseModal');
  const url = config?.dataset.stockByWarehouseUrl;
  if (!config || !modalElement || !url || !window.bootstrap || !window.ApiService) return;

  const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
  const productLabel = document.getElementById('stock-modal-product');
  const loading = document.getElementById('stock-modal-loading');
  const error = document.getElementById('stock-modal-error');
  const table = document.getElementById('stock-modal-table');
  const rows = document.getElementById('stock-modal-rows');
  const baseHeading = document.getElementById('stock-base-heading');
  const equivalentHeading = document.getElementById('stock-equivalent-heading');

  const escapeHtml = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  const formatQuantity = value => Number(Number(value || 0).toFixed(3)).toString();

  document.addEventListener('click', async event => {
    const button = event.target.closest('.stock-info-btn');
    if (!button) return;

    const row = button.closest('.line-row');
    const productId = row?.querySelector('input[type="hidden"][name*="-product"]')?.value;
    if (!productId) {
      window.alert('Seleccione primero un producto.');
      return;
    }

    const selectedUnit = row.querySelector('.product-unit-select')?.selectedOptions[0];
    const factor = Number(selectedUnit?.dataset.factor || 1);
    const selectedCode = selectedUnit?.dataset.code
      || selectedUnit?.textContent.split(' - ')[0].trim() || '';

    productLabel.textContent = '';
    loading.classList.remove('d-none');
    error.classList.add('d-none');
    table.classList.add('d-none');
    rows.innerHTML = '';
    modal.show();

    try {
      const data = await ApiService.get(`${url}?product=${encodeURIComponent(productId)}`);
      const baseCode = data.product.unit_code;
      const showEquivalent = factor !== 1 && selectedCode && selectedCode !== baseCode;
      productLabel.textContent = `${data.product.sku ? `${data.product.sku} · ` : ''}${data.product.name}`;
      baseHeading.textContent = `Stock (${baseCode})`;
      equivalentHeading.textContent = showEquivalent ? `Equivalente (${selectedCode})` : 'Equivalente';
      equivalentHeading.classList.toggle('d-none', !showEquivalent);

      if (!data.warehouses.length) {
        rows.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">No hay almacenes activos.</td></tr>';
      } else {
        rows.innerHTML = data.warehouses.map(item => {
          const stock = Number(item.stock || 0);
          return `<tr>
            <td>${escapeHtml(item.store)}</td>
            <td>${escapeHtml(item.warehouse)}</td>
            <td class="text-end fw-semibold">${formatQuantity(stock)} ${escapeHtml(baseCode)}</td>
            ${showEquivalent ? `<td class="text-end">${formatQuantity(stock / factor)} ${escapeHtml(selectedCode)}</td>` : ''}
          </tr>`;
        }).join('');
      }
      table.classList.remove('d-none');
    } catch (requestError) {
      error.textContent = requestError.message || 'No se pudo consultar el stock.';
      error.classList.remove('d-none');
    } finally {
      loading.classList.add('d-none');
    }
  });
}());
