/* sw.js - the HUD's service worker (PWA slice 3c, owner/Gemini ruling Q5).
 *
 * WHAT IT IS ALLOWED TO DO, in one sentence: it keeps a copy of four frozen
 * presentation files (the manifest and its three icons) and nothing else.
 *
 * The rules, and why each one is here:
 *   * Only those four named files are ever stored, and only during install.
 *     Nothing is written to the cache at request time, so no response that a
 *     person's request happened to produce can ever end up on disk.
 *   * The fetch handler never handles the backend's application routes. Any
 *     request that is not one of the four frozen files is not intercepted at
 *     all; it falls through to the network exactly as if there were no service
 *     worker. Nothing about the owner's data passes through this file.
 *   * GET only. A POST, PUT or DELETE is never touched.
 *   * This origin only. A request to any other origin is never intercepted and
 *     never stored; there are no remote addresses anywhere in this file.
 *   * No request headers are read, no response headers are inspected, no
 *     per-browser state is written: the cache holds the same four bytes for
 *     every person and every pairing.
 *   * skipWaiting() is called only when the page explicitly asks for it with a
 *     JARVIS_SW_SKIP_WAITING message (the update prompt the page hook will
 *     show), never on install. clients.claim() runs on activate, so a new
 *     version takes over open pages at the moment the page asked for it.
 *   * Safe to serve over plain HTTP: it is inert unless registered, and the
 *     page hook only registers from a secure context (window.isSecureContext),
 *     so over the mesh address with no TLS this file is simply never installed.
 *
 * Bump CACHE_NAME when the four files change: the new worker is downloaded,
 * the page shows its update prompt, the message below activates it, and
 * activate() deletes the previous cache.
 */
"use strict";

const CACHE_NAME = "jarvis-pwa-shell-v1";

/** The only files this worker may ever store. Add NOTHING here that is not a
 * frozen presentation file: no page, no script, no style, no data. */
const SHELL_FILES = Object.freeze([
  "/manifest.webmanifest",
  "/icons/jarvis-180.png",
  "/icons/jarvis-192.png",
  "/icons/jarvis-512.png",
]);
const SHELL_PATHS = new Set(SHELL_FILES);

/** The page's update prompt sends this one message. Nothing else is a command:
 * an unknown message is ignored. */
const SKIP_WAITING_MESSAGE = "JARVIS_SW_SKIP_WAITING";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
    );
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  const data = (event && event.data) || {};
  if (data.type === SKIP_WAITING_MESSAGE) {
    // Only behind the page's update prompt; never on install.
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  // 1. GET only.
  if (request.method !== "GET") return;
  // 2. This origin only. Anything else is left entirely to the browser.
  let url;
  try { url = new URL(request.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) return;
  // 3. One of the four frozen files only. Every other path - every backend
  //    route included - is not intercepted at all and goes to the network.
  if (!SHELL_PATHS.has(url.pathname)) return;
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(request, { ignoreSearch: false });
      if (cached) return cached;
      // Not cached (only possible if the install copy was cleared): go to the
      // network and do NOT store the answer.
      return fetch(request);
    })
  );
});
