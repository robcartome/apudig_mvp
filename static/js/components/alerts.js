(function () {
  'use strict';

  function initAutoDismiss(alertElement) {
    const configuredTimeout = Number(alertElement.dataset.autoDismiss || 0);
    if (!configuredTimeout || configuredTimeout < 0) return;

    let remaining = configuredTimeout;
    let startedAt = 0;
    let timerId = null;

    function closeAlert() {
      timerId = null;
      if (window.bootstrap?.Alert) {
        window.bootstrap.Alert.getOrCreateInstance(alertElement).close();
        return;
      }
      alertElement.remove();
    }

    function startTimer() {
      if (timerId || remaining <= 0 || !alertElement.isConnected) return;
      startedAt = Date.now();
      timerId = window.setTimeout(closeAlert, remaining);
    }

    function pauseTimer() {
      if (!timerId) return;
      window.clearTimeout(timerId);
      timerId = null;
      remaining -= Date.now() - startedAt;
    }

    alertElement.addEventListener('mouseenter', pauseTimer);
    alertElement.addEventListener('mouseleave', startTimer);
    alertElement.addEventListener('focusin', pauseTimer);
    alertElement.addEventListener('focusout', startTimer);
    alertElement.addEventListener('closed.bs.alert', function () {
      if (timerId) window.clearTimeout(timerId);
    });

    startTimer();
  }

  document.querySelectorAll('.app-alert[data-auto-dismiss]').forEach(initAutoDismiss);
}());
