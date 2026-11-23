(function () {
  'use strict';

  const table = document.getElementById('price-table');
  const options = document.getElementById('column-options');
  if (!table || !options) return;

  const storageKey = 'apudig:price-report:' + options.dataset.scope;
  const defaultOptions = Array.from(options.querySelectorAll('.price-column-option'));
  const columns = new Map(defaultOptions.map(option => [option.dataset.col, option]));
  const defaultOrder = Array.from(columns.keys());
  const rows = Array.from(table.querySelectorAll('tr')).map(row => {
    const cells = Array.from(row.querySelectorAll('.col-dyn'));
    // An empty-results row spans the table and contains no price cells.
    if (!cells.length) return null;
    return {row, cells: new Map(defaultOrder.map((key, index) => [key, cells[index]]))};
  }).filter(Boolean);

  function optionRows() {
    return Array.from(options.querySelectorAll('.price-column-option'));
  }

  function savePreference() {
    const entries = optionRows();
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        order: entries.map(option => option.dataset.col),
        hidden: entries.filter(option => !option.querySelector('.col-toggle').checked)
          .map(option => option.dataset.col),
      }));
    } catch (error) {
      // The report remains usable when browser storage is unavailable.
    }
  }

  function renderColumns() {
    const entries = optionRows();
    entries.forEach((option, index) => {
      const key = option.dataset.col;
      const visible = option.querySelector('.col-toggle').checked;
      option.querySelector('.move-column-up').disabled = index === 0;
      option.querySelector('.move-column-down').disabled = index === entries.length - 1;
      rows.forEach(({row, cells}) => {
        const cell = cells.get(key);
        if (cell) {
          cell.style.display = visible ? '' : 'none';
          row.appendChild(cell);
        }
      });
    });
  }

  function restorePreference() {
    let preference;
    try { preference = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (error) { return; }
    if (!preference || !Array.isArray(preference.order) || !Array.isArray(preference.hidden)) return;
    const order = [...new Set(preference.order.filter(key => columns.has(key))), ...defaultOrder];
    const seen = new Set();
    order.forEach(key => {
      if (seen.has(key)) return;
      seen.add(key);
      const option = columns.get(key);
      option.querySelector('.col-toggle').checked = !preference.hidden.includes(key);
      options.appendChild(option);
    });
  }

  options.addEventListener('change', function (event) {
    if (!event.target.matches('.col-toggle')) return;
    renderColumns();
    savePreference();
  });
  options.addEventListener('click', function (event) {
    const button = event.target.closest('.move-column-up, .move-column-down');
    if (!button) return;
    const option = button.closest('.price-column-option');
    const isUp = button.classList.contains('move-column-up');
    const neighbor = isUp ? option.previousElementSibling : option.nextElementSibling;
    if (!neighbor) return;
    if (isUp) options.insertBefore(option, neighbor);
    else options.insertBefore(neighbor, option);
    renderColumns();
    savePreference();
    // Keep keyboard focus within the moved item, including at the list boundaries.
    if (button.disabled) option.querySelector(isUp ? '.move-column-down' : '.move-column-up').focus();
    else button.focus();
  });

  function setAll(checked) {
    optionRows().forEach(option => { option.querySelector('.col-toggle').checked = checked; });
    renderColumns();
    savePreference();
  }
  document.getElementById('col-select-all').addEventListener('click', () => setAll(true));
  document.getElementById('col-select-none').addEventListener('click', () => setAll(false));
  document.getElementById('col-reset').addEventListener('click', function () {
    defaultOptions.forEach(option => {
      option.querySelector('.col-toggle').checked = true;
      options.appendChild(option);
    });
    renderColumns();
    savePreference();
  });
  document.getElementById('btn-export-excel').addEventListener('click', function () {
    const selected = optionRows().filter(option => option.querySelector('.col-toggle').checked)
      .map(option => option.dataset.col);
    const url = new URL(window.location.href);
    url.searchParams.set('format', 'xlsx');
    url.searchParams.set('cols', selected.join(','));
    url.searchParams.delete('page');
    window.location.href = url.toString();
  });

  restorePreference();
  renderColumns();
})();
