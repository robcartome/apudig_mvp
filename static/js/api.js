/**
 * api.js — Centralized HTTP service layer (plain JS, no framework)
 * Exposes: window.ApiService  { get(url), post(url, body, csrf) }
 */
window.ApiService = (function () {
  'use strict';

  const HEADERS = { 'X-Requested-With': 'XMLHttpRequest' };

  async function get(url) {
    const response = await fetch(url, { headers: HEADERS });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  async function post(url, body, csrf) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...HEADERS,
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
      },
      body: JSON.stringify(body),
    });

    const json = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(json.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = json;
      throw error;
    }

    return json;
  }

  return { get, post };
}());