(function () {
  'use strict';
  const input = document.getElementById('barcode-search');
  const body = document.getElementById('purchase-lines-body') || document.getElementById('lines-body');
  const config = document.getElementById('purchase-form-config') || document.getElementById('sales-form-config') || document.getElementById('inv-form-config');
  const add = document.getElementById('add-purchase-line') || document.getElementById('add-line');
  if (!input || !body || !config || !add) return;
  const message = document.getElementById('barcode-message');
  let queue = Promise.resolve();
  async function scan(code) {
    try {
      const params = new URLSearchParams({barcode: code});
      const supplier = document.getElementById('id_supplier')?.value;
      const warehouse = document.getElementById('id_warehouse')?.value || document.getElementById('id_warehouse_origin')?.value;
      if (supplier) params.set('supplier', supplier);
      if (warehouse) params.set('warehouse', warehouse);
      const data = await ApiService.get(config.dataset.searchUrl + '?' + params.toString());
      const products = data.products || [];
      if (products.length !== 1) {
        message.textContent = products.length ? 'Código duplicado: revisa los productos antes de continuar.' : 'No se encontró el código: ' + code;
        return;
      }
      const product = products[0];
      const rows = Array.from(body.querySelectorAll('.line-row')).filter(row => !row.hidden);
      let row = rows.find(r => r.querySelector('input[type=hidden][name$="-product"]')?.value === String(product.id) && r.querySelector('.product-unit-select')?.value === String(product.unit_id));
      if (row) {
        const quantity = row.querySelector('input[name$="-quantity"]');
        quantity.value = String((Number(quantity.value.replace(',', '.')) || 0) + 1);
        quantity.dispatchEvent(new Event('input', {bubbles: true}));
        quantity.dispatchEvent(new Event('change', {bubbles: true}));
      } else {
        row = rows.find(r => !r.querySelector('input[type=hidden][name$="-product"]')?.value);
        if (!row) {
          add.click();
          row = Array.from(body.querySelectorAll('.line-row')).filter(r => !r.hidden).at(-1);
          const opened = row.querySelector('.product-select');
          if (opened && $(opened).data('select2')) $(opened).select2('close');
        }
        const select = row.querySelector('.product-select');
        $(select).append(new Option(product.sku ? product.sku + ' | ' + product.name : product.name, product.id, true, true)).trigger('change');
        row.querySelector('input[type=hidden][name$="-product"]').value = product.id;
        row.dispatchEvent(new CustomEvent('product-picker:selected', {bubbles: true, detail: product}));
        const quantity = row.querySelector('input[name$="-quantity"]');
        quantity.value = '1';
        quantity.dispatchEvent(new Event('input', {bubbles: true}));
        quantity.dispatchEvent(new Event('change', {bubbles: true}));
      }
      message.textContent = 'Agregado: ' + product.name;
    } catch (error) {
      message.textContent = 'No se pudo consultar el código. Intenta nuevamente.';
      console.error(error);
    }
  }
  function submit() {
    const code = input.value.trim();
    if (!code) return;
    input.value = '';
    queue = queue.then(() => scan(code));
    input.focus();
  }
  input.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); submit(); } });
  document.getElementById('barcode-btn')?.addEventListener('click', submit);
})();
