(function () {
  'use strict';

  function initialize(topScroll) {
    const target = document.querySelector(topScroll.dataset.scrollTarget);
    const spacer = topScroll.firstElementChild;
    if (!target || !spacer) return;

    let syncing = false;
    const updateWidth = function () {
      spacer.style.width = target.scrollWidth + 'px';
      topScroll.hidden = target.scrollWidth <= target.clientWidth;
    };
    const synchronize = function (source, destination) {
      if (syncing) return;
      syncing = true;
      destination.scrollLeft = source.scrollLeft;
      syncing = false;
    };

    topScroll.addEventListener('scroll', function () {
      synchronize(topScroll, target);
    });
    target.addEventListener('scroll', function () {
      synchronize(target, topScroll);
    });
    window.addEventListener('resize', updateWidth);
    if (window.ResizeObserver) new ResizeObserver(updateWidth).observe(target);
    updateWidth();
  }

  document.querySelectorAll('.js-table-scroll-top').forEach(initialize);
}());
