/**
 * select2.js — Shared Select2 defaults for the project.
 * Exposes: window.Select2Plugin.build(options)
 */
window.Select2Plugin = (function ($) {
  'use strict';

  function build(options) {
    return {
      theme: 'bootstrap-5',
      width: '100%',
      dropdownParent: $('body'),
      ...options,
    };
  }

  return { build };
}(jQuery)); 