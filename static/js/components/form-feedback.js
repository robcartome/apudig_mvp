(function () {
  'use strict';
  const marked = new WeakSet();

  function addHintIcons(root) {
    const hints = [];
    if (root.matches && root.matches('.form-hint:not(label)')) hints.push(root);
    root.querySelectorAll('.form-hint:not(label)').forEach(hint => hints.push(hint));
    hints.forEach(hint => {
      if (!hint.textContent.trim() || hint.hasAttribute('role') || hint.hasAttribute('aria-live')) return;
      if (hint.querySelector('.form-hint-icon')) return;
      const icon = document.createElement('i');
      icon.className = 'ti ti-info-circle form-hint-icon';
      icon.setAttribute('aria-hidden', 'true');
      hint.prepend(icon);
    });
  }

  function displayed(field) {
    if (field.type !== 'hidden') return field;
    const picker = document.getElementById(field.id + '-picker');
    if (picker) return picker;
    const cell = field.closest('td');
    return cell && cell.querySelector('.product-select, .product-unit-select, input:not([type="hidden"]), select');
  }

  function mark(field) {
    const control = displayed(field);
    if (!control) return null;
    const select2 = control.nextElementSibling && control.nextElementSibling.classList.contains('select2-container')
      ? control.nextElementSibling : null;
    control.classList.add('is-invalid');
    control.setAttribute('aria-invalid', 'true');
    if (select2) select2.classList.add('is-invalid');
    if (!marked.has(control)) {
      marked.add(control);
      const clear = function () {
        control.classList.remove('is-invalid');
        control.removeAttribute('aria-invalid');
        field.removeAttribute('aria-invalid');
        field.classList.remove('is-invalid');
        if (select2) select2.classList.remove('is-invalid');
      };
      control.addEventListener('input', clear);
      control.addEventListener('change', clear);
      if (window.jQuery && control.classList.contains('select2-hidden-accessible')) {
        window.jQuery(control).on('select2:select select2:clear', clear);
      }
    }
    return select2 || control;
  }

  function collect(root) {
    const fields = new Set();
    if (root.matches && root.matches('[aria-invalid="true"], .is-invalid')) fields.add(root);
    root.querySelectorAll('[aria-invalid="true"], input.is-invalid, select.is-invalid, textarea.is-invalid').forEach(field => fields.add(field));
    root.querySelectorAll('[data-invalid-field]').forEach(marker => {
      const field = document.getElementById(marker.dataset.invalidField);
      if (field) fields.add(field);
    });
    return Array.from(fields).map(mark).filter(Boolean);
  }

  function focusFirst(elements) {
    const first = elements.find(element => element.getClientRects().length && !element.closest('[hidden], .modal:not(.show), .collapse:not(.show)'));
    if (!first) return;
    first.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const target = first.matches('.select2-container') ? first.querySelector('.select2-selection') : first;
    if (target && !target.disabled) target.focus({ preventScroll: true });
  }

  document.addEventListener('invalid', function (event) { mark(event.target); }, true);
  document.addEventListener('shown.bs.modal', function (event) { focusFirst(collect(event.target)); });
  document.addEventListener('shown.bs.collapse', function (event) { focusFirst(collect(event.target)); });
  const initial = collect(document);
  addHintIcons(document);
  if (initial.length) requestAnimationFrame(() => focusFirst(initial));
  new MutationObserver(function (mutations) {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          addHintIcons(node);
          const elements = collect(node);
          if (node.closest('.modal.show') && elements.length) focusFirst(elements);
        }
      }
    }
  }).observe(document.body, { childList: true, subtree: true });
}());
