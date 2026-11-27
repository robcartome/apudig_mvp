(function () {
  "use strict";
  const center = document.querySelector("[data-notification-center]");
  if (!center) return;
  const badge = center.querySelector("[data-notification-badge]");
  const body = center.querySelector("[data-notification-body]");
  const readAll = center.querySelector("[data-notification-read-all]");
  const trigger = center.querySelector("[data-bs-toggle='dropdown']");
  const tabs = Array.from(center.querySelectorAll("[data-notification-tab]"));
  const scope = [center.dataset.userId, center.dataset.companyId, center.dataset.storeId];
  const cacheKey = scope.every(Boolean) ? `apudig:notification-count:v1:${scope.join(":")}` : null;
  const cacheLifetime = 4 * 60 * 60 * 1000;
  let activeStatus = "unread";
  let loading = false;
  let cacheAvailable = Boolean(cacheKey);
  let countRevision = 0;

  function parseCachedCount(raw) {
    try {
      const data = JSON.parse(raw);
      if (!Number.isInteger(data?.count) || data.count < 0 ||
          !Number.isFinite(data.updatedAt) || data.updatedAt <= 0 || data.updatedAt > Date.now()) return null;
      return data;
    } catch (_error) {
      return null;
    }
  }
  function cachedCount() {
    if (!cacheKey) return null;
    try {
      return parseCachedCount(window.localStorage.getItem(cacheKey));
    } catch (_error) {
      cacheAvailable = false;
      return null;
    }
  }

  function csrfToken() {
    return document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1] || "";
  }
  function updateCount(count, persist = true) {
    const value = Number(count);
    if (!Number.isInteger(value) || value < 0) return;
    countRevision += 1;
    badge.textContent = value > 99 ? "99+" : String(value);
    badge.hidden = value === 0;
    readAll.hidden = value === 0;
    trigger.setAttribute("aria-label", value ? `Abrir notificaciones: ${value} sin leer` : "Abrir notificaciones");
    if (persist && cacheKey && cacheAvailable) {
      try {
        window.localStorage.setItem(cacheKey, JSON.stringify({count: value, updatedAt: Date.now()}));
      } catch (_error) {
        cacheAvailable = false;
      }
    }
  }
  function loadingState() {
    body.innerHTML = '<div class="global-notifications__loading"><span class="spinner-border spinner-border-sm"></span> Cargando…</div>';
  }
  function errorState(error) {
    if (error?.status === 404) {
      body.innerHTML = '<div class="global-notifications__error"><i class="ti ti-alert-circle"></i><strong>El contexto activo cambió. Recarga la página.</strong><button type="button" data-notification-reload>Recargar página</button></div>';
      body.querySelector("[data-notification-reload]")?.addEventListener("click", () => window.location.reload());
      return;
    }
    body.innerHTML = '<div class="global-notifications__error"><i class="ti ti-alert-circle"></i><strong>No se pudieron cargar</strong><button type="button" data-notification-retry>Reintentar</button></div>';
    body.querySelector("[data-notification-retry]")?.addEventListener("click", loadDropdown);
  }
  async function request(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin", ...options, cache: "no-store",
      headers: {
        ...(cacheKey ? {
          "X-Notification-User": scope[0],
          "X-Notification-Company": scope[1],
          "X-Notification-Store": scope[2],
        } : {}),
        ...options?.headers,
      },
    });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  async function refreshCount() {
    if (document.hidden) return;
    const revision = countRevision;
    try {
      const data = await request(center.dataset.countUrl);
      // A newer dropdown/read action or another tab may already have updated it.
      if (revision === countRevision) updateCount(data.unread_count);
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
    } catch (error) {
      errorState(error);
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
    } catch (error) {
      errorState(error);
    } finally {
      readAll.disabled = false;
    }
  });
  trigger.addEventListener("show.bs.dropdown", loadDropdown);
  bindItemLinks(document, "[data-notification-page-link]");
  const cached = cachedCount();
  if (cached) updateCount(cached.count, false);
  // No polling: check at page load only if this scope's cached count has expired.
  // When storage is blocked, fetch only on an explicit action such as opening the bell.
  if (cacheAvailable && (!cached || Date.now() - cached.updatedAt >= cacheLifetime)) refreshCount();
  window.addEventListener("storage", function (event) {
    if (!cacheKey || (event.key !== cacheKey && event.key !== null)) return;
    const changed = parseCachedCount(event.newValue);
    updateCount(changed ? changed.count : 0, false);
  });
}());
