(function () {
  'use strict';

  document.querySelectorAll('.js-advanced-filters').forEach(function (panel) {
    const button = document.querySelector('[data-bs-target="#' + panel.id + '"]');
    if (!button) return;
    const label = button.querySelector('.js-filter-toggle-label');
    const chevron = button.querySelector('.js-filter-toggle-chevron');
    const update = function (expanded) {
      if (label) label.textContent = expanded ? 'Ocultar filtros' : 'Mostrar filtros';
      if (chevron) {
        chevron.classList.toggle('ti-chevron-up', expanded);
        chevron.classList.toggle('ti-chevron-down', !expanded);
      }
    };
    panel.addEventListener('shown.bs.collapse', function () { update(true); });
    panel.addEventListener('hidden.bs.collapse', function () { update(false); });
    update(panel.classList.contains('show'));
  });
}());
