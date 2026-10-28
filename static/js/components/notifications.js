(function () {
  "use strict";
  const center = document.querySelector("[data-notification-center]");
  if (!center) return;
  const badge = center.querySelector("[data-notification-badge]");
  const body = center.querySelector("[data-notification-body]");
  const readAll = center.querySelector("[data-notification-read-all]");
  const trigger = center.querySelector("[data-bs-toggle='dropdown']");
  const tabs = Array.from(center.querySelectorAll("[data-notification-tab]"));
  let activeStatus = "unread";
  let loading = false;

  function csrfToken() {
    return document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1] || "";
  }
  function updateCount(count) {
    const value = Number(count || 0);
    badge.textContent = value > 99 ? "99+" : String(value);
    badge.hidden = value === 0;
    readAll.hidden = value === 0;
    trigger.setAttribute("aria-label", value ? `Abrir notificaciones: ${value} sin leer` : "Abrir notificaciones");
  }
  function loadingState() {
    body.innerHTML = '<div class="global-notifications__loading"><span class="spinner-border spinner-border-sm"></span> Cargando…</div>';
  }
  function errorState() {
    body.innerHTML = '<div class="global-notifications__error"><i class="ti ti-alert-circle"></i><strong>No se pudieron cargar</strong><button type="button" data-notification-retry>Reintentar</button></div>';
    body.querySelector("[data-notification-retry]")?.addEventListener("click", loadDropdown);
  }
  async function request(url, options) {
    const response = await fetch(url, {credentials: "same-origin", ...options});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
  async function refreshCount() {
    if (document.hidden) return;
    try {
      const data = await request(center.dataset.countUrl);
      updateCount(data.unread_count);
    } catch (_error) {}
  }
  function bindItemLinks(root, selector) {
    root.querySelectorAll(selector).forEach((link) => {
      link.addEventListener("click", async function (event) {
        event.preventDefault();
        const target = link.href;
        try {
          const data = await request(link.dataset.readUrl, {
            method: "POST",
            headers: {"X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest"},
          });
          updateCount(data.unread_count);
        } catch (_error) {
          // Navigation still proceeds; the destination enforces its own permissions.
        } finally {
          window.location.assign(target);
        }
      });
    });
  }
  async function loadDropdown() {
    if (loading) return;
    loading = true;
    loadingState();
    try {
      const data = await request(`${center.dataset.dropdownUrl}?status=${activeStatus}`);
      body.innerHTML = data.html;
      updateCount(data.unread_count);
      bindItemLinks(body, "[data-notification-link]");
    } catch (_error) {
      errorState();
    } finally {
      loading = false;
    }
  }
  tabs.forEach((tab) => {
    tab.addEventListener("click", function () {
      activeStatus = tab.dataset.notificationTab;
      tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
      loadDropdown();
    });
  });
  readAll.addEventListener("click", async function () {
    readAll.disabled = true;
    try {
      const data = await request(center.dataset.readAllUrl, {
        method: "POST",
        headers: {"X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest"},
      });
      updateCount(data.unread_count);
      loadDropdown();
    } catch (_error) {
      errorState();
    } finally {
      readAll.disabled = false;
    }
  });
  trigger.addEventListener("show.bs.dropdown", loadDropdown);
  bindItemLinks(document, "[data-notification-page-link]");
  refreshCount();
  window.setInterval(refreshCount, 90000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refreshCount();
  });
}());
