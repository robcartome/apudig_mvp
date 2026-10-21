/** Searchable, exact customer/supplier filters for list views. */
(function ($) {
  'use strict';

  document.querySelectorAll('.js-partner-filter').forEach(function (element) {
    if (element.dataset.partnerFilterReady === '1') return;
    element.dataset.partnerFilterReady = '1';
    const $element = $(element);

    function formatResult(partner) {
      if (partner.loading) return partner.text;
      const result = document.createElement('div');
      result.className = 'partner-filter-result';

      const name = document.createElement('div');
      name.className = 'partner-filter-result__name';
      name.textContent = element.dataset.partnerType === 'supplier'
        ? (partner.name || partner.text)
        : (partner.legal_name || partner.text);

      const documentNumber = document.createElement('div');
      documentNumber.className = 'partner-filter-result__document';
      documentNumber.textContent = partner.document_number
        ? 'Documento: ' + partner.document_number
        : 'Sin documento registrado';

      result.append(name, documentNumber);
      return $(result);
    }

    $element.select2(window.Select2Plugin.build({
      placeholder: element.dataset.placeholder || 'Buscar y seleccionar…',
      allowClear: true,
      minimumInputLength: 0,
      templateResult: formatResult,
      language: {
        noResults: function () { return 'No se encontraron coincidencias'; },
        searching: function () { return 'Buscando…'; },
        loadingMore: function () { return 'Cargando más resultados…'; },
      },
      ajax: {
        url: element.dataset.searchUrl,
        dataType: 'json',
        delay: 250,
        data: function (params) {
          return { q: params.term || '' };
        },
        processResults: function (data) {
          return { results: data.results || [] };
        },
      },
    }));

    $element.on('select2:select', function () {
      const group = element.dataset.exclusiveGroup;
      if (!group) return;
      document.querySelectorAll(
        '.js-partner-filter[data-exclusive-group="' + group + '"]'
      ).forEach(function (peer) {
        if (peer !== element) $(peer).val(null).trigger('change');
      });
    });
  });
}(jQuery));
