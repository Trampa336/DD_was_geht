// Service Worker fuer DD was geht.
// Strategie: "network-first" fuer die Seite selbst, damit online immer die
// frischesten Termine kommen; offline greift der zuletzt geladene Stand aus
// dem Cache. Manifest und Icons werden beim Install vorab gecacht.
//
// CACHE-Namen hochzaehlen, wenn sich die Liste der ASSETS aendert, sonst
// bleiben alte Dateien haengen.
const CACHE = "ddwg-v1";
const ASSETS = ["./", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS).catch(() => {}))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(event.request).then((res) => res || caches.match("./")))
  );
});
