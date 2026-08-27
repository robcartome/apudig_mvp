(function () {
  'use strict';

  function initRemoteSelect2(el) {
    const url         = el.dataset.url;
    const hiddenId    = el.dataset.hiddenId;
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
          window.ApiService.get(url + '?q=' + encodeURIComponent(params.data.term || ''))
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
  }

  document.querySelectorAll('.remote-select-js').forEach(initRemoteSelect2);

  const imageSlots = [
    ['id_image_file', 'image-preview', 'image-preview-wrap', 'id_remove_image'],
    ['id_secondary_image_file', 'secondary-image-preview', 'secondary-image-preview-wrap', 'id_remove_secondary_image'],
    ['id_tertiary_image_file', 'tertiary-image-preview', 'tertiary-image-preview-wrap', 'id_remove_tertiary_image'],
  ];

  imageSlots.forEach(function (slot) {
    const imageInput = document.getElementById(slot[0]);
    const preview = document.getElementById(slot[1]);
    const previewWrap = document.getElementById(slot[2]);
    const removeImage = document.getElementById(slot[3]);
    let previewUrl = null;
    if (!imageInput || !preview || !previewWrap) return;

    imageInput.addEventListener('change', function () {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const file = imageInput.files && imageInput.files[0];
      if (!file) return;
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      previewWrap.classList.remove('d-none');
      if (removeImage) removeImage.checked = false;
    });
  });
}());
