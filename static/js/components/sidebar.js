/*!
 * APUDIG — Sidebar component JS
 * Handles: collapse toggle | flyout submenus | icon tooltips | collapsed-nav | mobile slide-in
 */
(function () {
  'use strict';

  /* ─── State ─── */
  var sidebar, toggleBtn, toggleIcon, headerSidebarBtn;
  var flyoutEl     = null;
  var flyoutTimer  = null;
  var tooltipEl    = null;
  var tooltipTimer = null;
  var overlay      = null;
  var KEY          = 'apudig_sidebar_collapsed';
  var MOBILE_KEY   = 'apudig_sidebar_mobile_open';
  var SIDEBAR_W    = '3.5rem';

  function readState(key) {
    try { return localStorage.getItem(key) === '1'; } catch (error) { return false; }
  }

  function saveState(key, value) {
    try { localStorage.setItem(key, value ? '1' : '0'); } catch (error) { /* Continue without persistence. */ }
  }

  /* ══════════════════════════════════════════
     TOOLTIP (only visible when icon-only mode)
     ══════════════════════════════════════════ */
  function getTooltip() {
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.className = 'apudig-sidebar-tooltip';
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  function showTooltip(link, label) {
    if (!sidebar.classList.contains('sidebar-collapsed')) return;
    var rect = link.getBoundingClientRect();
    var tt = getTooltip();
    tt.textContent = label;
    tt.style.top = Math.round(rect.top + rect.height / 2) + 'px';
    clearTimeout(tooltipTimer);
    /* tiny delay prevents flicker when moving quickly between items */
    tooltipTimer = setTimeout(function () { tt.classList.add('visible'); }, 50);
  }

  function hideTooltip() {
    clearTimeout(tooltipTimer);
    if (tooltipEl) tooltipEl.classList.remove('visible');
  }

  function bindTooltips() {
    sidebar.querySelectorAll('[data-tooltip-label]').forEach(function (el) {
      /* flyout handles parent items — skip them here */
      if (el.hasAttribute('data-bs-toggle')) return;
      el.addEventListener('mouseenter', function () { showTooltip(el, el.dataset.tooltipLabel); });
      el.addEventListener('mouseleave', hideTooltip);
      el.addEventListener('click',      hideTooltip);
    });
  }

  /* ══════════════════════════════════════════
     FLYOUT SUBMENU (only while collapsed)
     Opens to the LEFT of the right sidebar rail
     ══════════════════════════════════════════ */
  function removeFlyout() {
    clearTimeout(flyoutTimer);
    if (flyoutEl) {
      flyoutEl.classList.remove('visible');
      var _el = flyoutEl;
      flyoutEl = null;
      setTimeout(function () { if (_el.parentNode) _el.parentNode.removeChild(_el); }, 160);
    }
  }

  function showFlyout(li, parentLink) {
    removeFlyout();
    var subLinks = li.querySelectorAll('.navbar-nav a.nav-link');
    if (!subLinks.length) return;

    var panel = document.createElement('div');
    panel.className = 'apudig-flyout';

    var header = document.createElement('div');
    header.className = 'apudig-flyout-header';
    var titleEl = parentLink.querySelector('.nav-link-title');
    header.textContent = (titleEl ? titleEl.textContent : '') ||
                         (parentLink.dataset.tooltipLabel || '');
    panel.appendChild(header);

    subLinks.forEach(function (a) {
      var link = document.createElement('a');
      link.href = a.href;
      link.textContent = a.textContent.trim();
      if (a.classList.contains('active')) link.classList.add('active');
      panel.appendChild(link);
    });

    document.body.appendChild(panel);
    flyoutEl = panel;

    /* vertical position: align top of flyout with the hovered item */
    var rect = li.getBoundingClientRect();
    panel.style.top = Math.round(rect.top) + 'px';

    /* show with transition */
    requestAnimationFrame(function () { panel.classList.add('visible'); });

    /* close when mouse leaves the flyout */
    panel.addEventListener('mouseleave', removeFlyout);
  }

  function bindFlyouts() {
    sidebar.querySelectorAll('.nav-item').forEach(function (li) {
      var parentLink = li.querySelector('.nav-link[data-bs-toggle="collapse"]');
      if (!parentLink) return;

      li.addEventListener('mouseenter', function () {
        if (!sidebar.classList.contains('sidebar-collapsed')) return;
        clearTimeout(flyoutTimer);
        flyoutTimer = setTimeout(function () { showFlyout(li, parentLink); }, 80);
      });

      li.addEventListener('mouseleave', function (e) {
        /* keep flyout alive if mouse moved into it */
        if (flyoutEl && flyoutEl.contains(e.relatedTarget)) return;
        clearTimeout(flyoutTimer);
      });
    });
  }

  /* ══════════════════════════════════════════
     COLLAPSED NAVIGATION
     When collapsed, clicking icon → navigate to section
     ══════════════════════════════════════════ */
  function bindCollapsedNav() {
    sidebar.querySelectorAll('.nav-link[data-section-url]').forEach(function (link) {
      /* Use capture phase so we run before Bootstrap's collapse handler */
      link.addEventListener('click', function (e) {
        if (window.innerWidth >= 992 && sidebar.classList.contains('sidebar-collapsed')) {
          e.preventDefault();
          e.stopImmediatePropagation();
          window.location.href = link.dataset.sectionUrl;
        }
      }, true);
    });
  }

  /* ══════════════════════════════════════════
     MOBILE SIDEBAR — slide in / out
     ══════════════════════════════════════════ */
  function openMobileSidebar(persist) {
    sidebar.classList.add('sidebar-mobile-open');
    document.body.classList.add('sidebar-mobile-open-body');
    if (overlay) overlay.classList.add('active');
    if (headerSidebarBtn) headerSidebarBtn.setAttribute('aria-expanded', 'true');
    if (persist !== false) saveState(MOBILE_KEY, true);
  }

  function closeMobileSidebar(persist) {
    sidebar.classList.remove('sidebar-mobile-open');
    document.body.classList.remove('sidebar-mobile-open-body');
    if (overlay) overlay.classList.remove('active');
    if (headerSidebarBtn) headerSidebarBtn.setAttribute('aria-expanded', 'false');
    if (persist !== false) saveState(MOBILE_KEY, false);
  }

  function setupMobileOverlay() {
    overlay = document.querySelector('.apudig-sidebar-overlay');

    /* Tap overlay → close sidebar */
    if (overlay) overlay.addEventListener('click', function () { closeMobileSidebar(); });

    /* Keep section toggles open, but close the menu before navigating to a view. */
    sidebar.addEventListener('click', function (event) {
      if (window.innerWidth >= 992 || event.defaultPrevented || event.button !== 0 ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      var link = event.target.closest('a[href]');
      if (!link || link.hasAttribute('data-bs-toggle') || link.getAttribute('href').charAt(0) === '#' ||
          (link.target && link.target !== '_self')) return;
      closeMobileSidebar();
    });
  }

  /* ══════════════════════════════════════════
     SIDEBAR COLLAPSE / EXPAND
     ══════════════════════════════════════════ */
  function applyCollapse(collapsed) {
    sidebar.classList.toggle('sidebar-collapsed', collapsed);
    document.body.classList.toggle('sidebar-collapsed-body', collapsed);
    if (headerSidebarBtn && window.innerWidth >= 992) headerSidebarBtn.setAttribute('aria-expanded', String(!collapsed));

    /* Flex layout handles resizing automatically — no CSS var or margin hack needed */

    /* Swap toggle icon */
    if (toggleIcon) {
      toggleIcon.className = collapsed
        ? 'ti ti-menu-2 fs-3'
        : 'ti ti-layout-sidebar-left-collapse fs-2';
    }
    if (toggleBtn) toggleBtn.title = collapsed ? 'Expandir menú' : 'Colapsar menú';
    if (toggleBtn) toggleBtn.style.display = collapsed ? 'none' : '';

    /* When expanding, dismiss any open flyout */
    if (!collapsed) removeFlyout();
  }

  /* ══════════════════════════════════════════
     INIT
     ══════════════════════════════════════════ */
  document.addEventListener('DOMContentLoaded', function () {
    sidebar          = document.getElementById('sidebar');
    toggleBtn        = document.getElementById('sidebar-toggle-btn');
    toggleIcon       = document.getElementById('sidebar-toggle-icon');
    headerSidebarBtn = document.getElementById('header-sidebar-btn');

    if (!sidebar) return;

    applyCollapse(readState(KEY));

    /* Desktop collapse button (inside sidebar) */
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function () {
        hideTooltip();
        var collapsed = !sidebar.classList.contains('sidebar-collapsed');
        applyCollapse(collapsed);
        saveState(KEY, collapsed);
      });
    }

    /* Header button: mobile toggle OR desktop expand */
    if (headerSidebarBtn) {
      headerSidebarBtn.addEventListener('click', function () {
        if (window.innerWidth < 992) {
          /* Mobile: slide the sidebar in / out */
          if (sidebar.classList.contains('sidebar-mobile-open')) {
            closeMobileSidebar();
          } else {
            openMobileSidebar();
          }
        } else {
          /* Desktop: expand collapsed sidebar */
          hideTooltip();
          applyCollapse(false);
          saveState(KEY, false);
        }
      });
    }

    setupMobileOverlay();
    if (window.innerWidth < 992 && readState(MOBILE_KEY)) openMobileSidebar(false);
    document.documentElement.classList.remove('sidebar-initial-collapsed', 'sidebar-initial-mobile-open');
    bindTooltips();
    bindFlyouts();
    bindCollapsedNav();

    /* Dismiss flyout on scroll */
    document.addEventListener('scroll', removeFlyout, { passive: true });
    window.addEventListener('storage', function (event) {
      if (event.key === KEY) applyCollapse(event.newValue === '1');
      if (event.key === MOBILE_KEY && window.innerWidth < 992) {
        if (event.newValue === '1') openMobileSidebar(false);
        else closeMobileSidebar(false);
      }
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth >= 992) {
        closeMobileSidebar(false);
        if (headerSidebarBtn) headerSidebarBtn.setAttribute('aria-expanded', String(!sidebar.classList.contains('sidebar-collapsed')));
      }
      else if (readState(MOBILE_KEY)) openMobileSidebar(false);
    });
  });
})();
