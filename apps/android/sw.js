/* Service worker: caches ONLY the app shell (the files listed in SHELL), so the app opens and shows its pairing screen
   with no tunnel. It never touches audio, the WebSocket, /live/events, /session or any verdict: those are not in SHELL,
   and every other request is left to the network untouched (no respondWith, no caching). */
const VERSION = "ds-android-shell-v1";
const SHELL = ["./", "index.html", "app.css", "app.js", "worklet.js", "outfit.woff2", "manifest.webmanifest",
  "lib/pcm.js", "lib/protocol.js", "lib/verdict.js", "icons/icon-192.png", "icons/icon-512.png", "icons/mark-light.svg", "icons/mark-dark.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  const rel = url.pathname.slice(new URL("./", self.location.href).pathname.length);
  if (!SHELL.includes(rel === "" ? "./" : rel)) return;
  e.respondWith(
    fetch(req).then((res) => {                       // network first: the shell updates whenever the laptop serves it
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true }))
  );
});
