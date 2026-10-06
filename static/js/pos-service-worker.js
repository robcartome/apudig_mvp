const CACHE_NAME = 'apudig-pos-static-v5';
const STATIC_ASSETS = [
  '/static/css/pos.css?v=20261006-4',
  '/static/vendor/zxing/zxing-browser-0.2.1.min.js?v=0.2.1',
  '/static/js/pos-barcode-scanner.js?v=20261006-2',
  '/static/js/pos.js?v=20261006-5',
  '/static/pwa/pos-icon-192.png',
  '/static/pwa/pos-icon-512.png',
];
const CACHEABLE_PATHS = new Set(STATIC_ASSETS.map((asset) => new URL(asset, self.location.origin).pathname));

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.startsWith('apudig-pos-') && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => new Response(
        '<!doctype html><html lang="es"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ApuDig POS sin conexión</title><body style="font-family:system-ui;padding:2rem"><h1>Sin conexión</h1><p>ApuDig POS necesita conexión para consultar precios, stock y registrar ventas.</p></body></html>',
        { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      ))
    );
    return;
  }

  if (url.origin === self.location.origin && CACHEABLE_PATHS.has(url.pathname)) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
  }
});
