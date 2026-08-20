/** Centralized HTTP service layer. */
window.ApiService = (function () {
  'use strict';

  const DEFAULT_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' };

  class ApiError extends Error {
    constructor(message, response, data) {
      super(message);
      this.name = 'ApiError';
      this.status = response.status;
      this.data = data;
    }
  }

  function getCookie(name) {
    const cookie = document.cookie.split(';').map(value => value.trim())
      .find(value => value.startsWith(`${name}=`));
    return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : '';
  }

  function csrfToken(explicitToken) {
    return explicitToken
      || document.querySelector('[name=csrfmiddlewaretoken]')?.value
      || getCookie('csrftoken');
  }

  function validationMessage(errors) {
    return Object.values(errors || {}).flat()
      .map(item => (typeof item === 'object' ? item.message : item))
      .filter(Boolean).join(' ');
  }

  function errorMessage(data, status) {
    return data?.error || data?.detail || validationMessage(data?.errors) || `HTTP ${status}`;
  }

  async function parseResponse(response) {
    if (response.status === 204) return null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return response.json().catch(() => ({}));
    return response.text();
  }

  async function request(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = { ...DEFAULT_HEADERS, ...(options.headers || {}) };
    let body = options.body;

    if (body !== undefined && body !== null && !(body instanceof FormData)) {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
      if (headers['Content-Type'].includes('application/json') && typeof body !== 'string') {
        body = JSON.stringify(body);
      }
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const token = csrfToken(options.csrf);
      if (token) headers['X-CSRFToken'] = token;
    }

    const response = await fetch(url, {
      method,
      headers,
      body,
      signal: options.signal,
      credentials: options.credentials || 'same-origin',
    });
    const data = await parseResponse(response);
    if (!response.ok) throw new ApiError(errorMessage(data, response.status), response, data);
    return data;
  }

  function get(url, options = {}) {
    return request(url, { ...options, method: 'GET' });
  }

  // The string third argument is retained for backwards compatibility.
  function post(url, body, csrfOrOptions = {}) {
    const options = typeof csrfOrOptions === 'string' ? { csrf: csrfOrOptions } : csrfOrOptions;
    return request(url, { ...options, method: 'POST', body });
  }

  return { request, get, post, ApiError };
}());
