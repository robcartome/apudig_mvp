/** Shared AJAX customer/supplier selector with quick creation. */
(function ($) {
  'use strict';

  document.querySelectorAll('.partner-select').forEach(function (element) {
    if (element.dataset.partnerPickerReady === '1') return;
    element.dataset.partnerPickerReady = '1';
    const $element = $(element);
    const hidden = document.getElementById(element.dataset.hiddenId);
    const modalElement = document.getElementById(element.dataset.modalId);
    const modal = modalElement && window.bootstrap ? new bootstrap.Modal(modalElement) : null;
    let searchTerm = '';

    $element.select2(window.Select2Plugin.build({
      placeholder: element.dataset.placeholder || 'Buscar…',
      allowClear: true,
      minimumInputLength: 0,
      ajax: {
        transport(params, success, failure) {
          searchTerm = params.data.term || '';
          const controller = new AbortController();
          window.ApiService.get(
            element.dataset.partnerUrl + '?q=' + encodeURIComponent(searchTerm),
            { signal: controller.signal }
          ).then(success).catch(error => {
            if (error.name !== 'AbortError') failure(error);
          });
          return { abort: () => controller.abort() };
        },
        processResults(data) {
          const results = [...(data.results || [])];
          results.push({
            id: '__create__',
            text: element.dataset.partnerType === 'supplier' ? '+ Agregar nuevo proveedor' : '+ Agregar nuevo cliente',
          });
          return { results };
        },
        delay: 250,
      },
    }));

    $element.on('select2:select', function (event) {
      const selected = event.params.data;
      if (selected.id === '__create__') {
        $element.val(null).trigger('change');
        if (hidden) hidden.value = '';
        if (modalElement && modal) {
          const numberInput = modalElement.querySelector('.partner-document-number');
          const nameInput = modalElement.querySelector('.partner-name');
          modalElement.querySelectorAll('input').forEach(input => { input.value = ''; });
          if (/^\d+$/.test(searchTerm.trim())) numberInput.value = searchTerm.trim();
          else nameInput.value = searchTerm.trim();
          modal.show();
        }
        return;
      }
      if (hidden) hidden.value = selected.id || '';
      const addressDisplay = document.getElementById('customer-address-display');
      if (addressDisplay && element.dataset.partnerType === 'customer') {
        addressDisplay.value = selected.address || '';
      }
    });
    $element.on('select2:unselect select2:clear', function () {
      if (hidden) hidden.value = '';
    });

    modalElement?.querySelector('.partner-create-save')?.addEventListener('click', async function () {
      const button = this;
      const error = modalElement.querySelector('.partner-create-error');
      const payload = {
        document_type: modalElement.querySelector('.partner-document-type')?.value || '',
        document_number: modalElement.querySelector('.partner-document-number').value.trim(),
        name: modalElement.querySelector('.partner-name').value.trim(),
        address: modalElement.querySelector('.partner-address').value.trim(),
      };
      error?.classList.add('d-none');
      button.disabled = true;
      try {
        const data = await window.ApiService.post(element.dataset.createUrl, payload);
        $element.append(new Option(data.text, data.id, true, true)).trigger('change');
        if (hidden) hidden.value = data.id;
        const addressDisplay = document.getElementById('customer-address-display');
        if (addressDisplay && element.dataset.partnerType === 'customer') addressDisplay.value = data.address || '';
        modal.hide();
        modalElement.querySelectorAll('input').forEach(input => { input.value = ''; });
      } catch (exception) {
        if (error) {
          error.textContent = exception.message || 'No se pudo crear el registro.';
          error.classList.remove('d-none');
        }
      } finally {
        button.disabled = false;
      }
    });
  });
}(jQuery));
