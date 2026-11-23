/* Confirm state-changing forms with a reusable Bootstrap dialog. */
(function () {
  'use strict';
  const modalElement = document.getElementById('confirm-action-modal');
  if (!modalElement) return;
  const title = document.getElementById('confirm-action-title');
  const message = document.getElementById('confirm-action-message');
  const confirmButton = document.getElementById('confirm-action-submit');
  const approvedForms = new WeakSet();
  let pendingForm = null;
  let pendingSubmitter = null;

  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-confirm-title')) return;
    if (approvedForms.has(form)) {
      approvedForms.delete(form);
      return;
    }
    event.preventDefault();
    const description = form.dataset.confirmMessage || '';
    if (!window.bootstrap?.Modal) {
      if (window.confirm(form.dataset.confirmTitle + '\n\n' + description)) {
        approvedForms.add(form);
        form.requestSubmit(event.submitter || undefined);
      }
      return;
    }
    pendingForm = form;
    pendingSubmitter = event.submitter;
    title.textContent = form.dataset.confirmTitle;
    message.textContent = description;
    confirmButton.textContent = form.dataset.confirmButton || 'Confirmar';
    confirmButton.className = 'btn ' + (form.dataset.confirmVariant === 'danger' ? 'btn-danger' : 'btn-primary');
    bootstrap.Modal.getOrCreateInstance(modalElement).show();
  });

  confirmButton.addEventListener('click', function () {
    if (!pendingForm) return;
    const form = pendingForm;
    const submitter = pendingSubmitter;
    pendingForm = null;
    pendingSubmitter = null;
    bootstrap.Modal.getInstance(modalElement).hide();
    if (!form.reportValidity()) return;
    approvedForms.add(form);
    form.requestSubmit(submitter || undefined);
  });
  modalElement.addEventListener('shown.bs.modal', function () {
    modalElement.querySelector('[data-bs-dismiss="modal"]:not(.btn-close)')?.focus();
  });
  modalElement.addEventListener('hidden.bs.modal', function () {
    pendingForm = null;
    pendingSubmitter = null;
  });
})();
