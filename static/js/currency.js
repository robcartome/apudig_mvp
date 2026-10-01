(function (global) {
  'use strict';

  const symbols = Object.freeze({
    PEN: 'S/.', USD: '$', EUR: '€', GBP: '£', JPY: '¥', CNY: '¥',
    CAD: 'C$', AUD: 'A$', CHF: 'CHF', BRL: 'R$', MXN: 'MX$',
    CLP: 'CL$', COP: 'COL$', ARS: 'AR$', BOB: 'Bs.',
  });

  function symbol(code) {
    const normalized = String(code || '').trim().toUpperCase();
    return symbols[normalized] || normalized;
  }

  global.CurrencyDisplay = Object.freeze({ symbol, symbols });
})(window);
