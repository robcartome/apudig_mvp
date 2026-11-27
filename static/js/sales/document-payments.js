(function () {
  'use strict';
  const modalEl = document.getElementById('salesPaymentModal');
  const bodyEl = document.getElementById('sales-payment-body');
  if (!modalEl || !bodyEl || !window.bootstrap) return;
  const modal = new bootstrap.Modal(modalEl);
  let loading = false;
  let saving = false;
  const headers = { 'X-Requested-With': 'XMLHttpRequest' };
  document.querySelectorAll('.js-sales-payment').forEach(function (button) {
    button.addEventListener('click', async function (event) {
      event.preventDefault();
      if (loading || saving) return;
      loading = true;
      bodyEl.innerHTML = '<div class="text-center text-muted py-4">Cargando…</div>';
      modal.show();
      try {
        const response = await fetch(button.dataset.paymentUrl, { headers: headers });
        if (!response.ok || response.redirected) throw new Error('load');
        bodyEl.innerHTML = await response.text();
      } catch (error) {
        bodyEl.innerHTML = '<div class="alert alert-danger">No se pudo cargar la cobranza. Cierra e intenta nuevamente.</div>';
      } finally {
        loading = false;
      }
    });
  });
  modalEl.addEventListener('hide.bs.modal', function (event) {
    if (saving) event.preventDefault();
  });
  bodyEl.addEventListener('submit', async function (event) {
    const form = event.target.closest('.js-sales-collection-form');
    if (!form) return;
    event.preventDefault();
    if (saving) return;
    saving = true;
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    const oldError = bodyEl.querySelector('.js-payment-error');
    if (oldError) oldError.remove();
    try {
      const response = await fetch(form.action, {
        method: 'POST', headers: headers, body: new FormData(form)
      });
      if (response.redirected) throw new Error('session');
      if (response.ok && response.headers.get('content-type').includes('application/json')) {
        window.location.reload();
        return;
      }
      if (response.status === 400) {
        bodyEl.innerHTML = await response.text();
      } else {
        throw new Error('save');
      }
    } catch (error) {
      const alert = document.createElement('div');
      alert.className = 'alert alert-danger js-payment-error';
      alert.setAttribute('role', 'alert');
      alert.textContent = 'No se pudo confirmar la cobranza. Reintenta para comprobar el mismo cobro sin duplicarlo.';
      form.prepend(alert);
      button.disabled = false;
    } finally {
      saving = false;
    }
  });
}());
