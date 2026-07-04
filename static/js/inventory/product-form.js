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
}());
