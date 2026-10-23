/**
 * pwa-manifest.mjs — PWA slice 3b/3c: the manifest, its icons, and the
 * privacy-safe service worker. Hermetic: two loopback HTTP servers (one
 * "Jarvis", one stand-in for a remote origin) and a real Chromium; no network.
 *
 * What is proven, one check each:
 *   1. manifest.webmanifest parses, names Jarvis, standalone, starts/scopes at
 *      "/", and its two colours are the HUD's own deep-space surface tokens
 *      (read from tokens/themes.tokens.json, not typed in here);
 *   2. the three icons exist as real PNGs with the declared sizes, the
 *      maskable one keeps the mark inside Android's 80% safe zone, the regular
 *      one's mark is larger, and every icon sits on the token background;
 *   3. every manifest icon is a local path and the manifest names no remote
 *      origin;
 *   4. sw.js: no backend route, no per-person state handling, GET only,
 *      same-origin only, the four frozen files only, writes only on install,
 *      skipWaiting only behind the update message, clients.claim on activate;
 *   5. in a real browser over loopback (a secure context): registration works,
 *      exactly the four files are cached, a backend GET and POST and a
 *      remote-origin fetch are NOT cached and still reach the network, and a
 *      same-origin page keeps falling through;
 *   6. the three HUD page copies are still untouched by this slice (no manifest
 *      link, no theme-color meta, no registration call: those hooks are later).
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, "..", "src");
const REPO = path.join(HERE, "..", "..");
const MANIFEST = path.join(SRC, "manifest.webmanifest");
const SW = path.join(SRC, "sw.js");
const TOKENS = path.join(REPO, "tokens", "themes.tokens.json");
const TWINS = [
  path.join(SRC, "jarvis_hud.html"),
  path.join(REPO, "backend", "jarvis_hud.html"),
  path.join(REPO, "jarvis-backend", "jarvis_hud.html"),
];

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (error) { fails.push(name); console.log(`FAIL  ${name}\n      ${error.message}`); }
};

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".webmanifest": "application/manifest+json",
  ".png": "image/png", ".svg": "image/svg+xml", ".woff": "font/woff",
  ".woff2": "font/woff2", ".txt": "text/plain" };

/** A real PNG's IHDR: bytes 16..24 are width and height (big endian). */
function pngSize(file) {
  const buffer = fs.readFileSync(file);
  if (buffer.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a") return null;
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

/** One "Jarvis" origin: the page's static files plus a stand-in backend route. */
function startJarvis() {
  const calls = [];
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    calls.push(`${req.method} ${url.pathname}`);
    if (url.pathname === "/") {
      res.writeHead(200, { "Content-Type": "text/html" });
      return res.end("<!doctype html><meta charset=\"utf-8\"><title>sw harness</title>");
    }
    if (url.pathname === "/api/ping") {
      // A real backend route: it answers, and it must never enter the cache.
      return res.writeHead(200, { "Content-Type": "application/json" }).end('{"ok":true}');
    }
    const rel = decodeURIComponent(url.pathname).replace(/^\//, "");
    const file = path.join(SRC, rel);
    if (!file.startsWith(SRC) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); return res.end();
    }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve({
      base: `http://127.0.0.1:${server.address().port}`,
      calls,
      close: () => server.close(),
    }));
  });
}

/** A different origin, so "no remote origins" is testable with a real request. */
function startRemote() {
  const server = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*" });
    res.end('{"remote":true}');
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve({
      url: `http://127.0.0.1:${server.address().port}/remote.json`,
      close: () => server.close(),
    }));
  });
}

const EXPECTED_CACHE_PATHS = [
  "/icons/pwa-192.png",
  "/icons/pwa-512.png",
  "/icons/pwa-maskable-512.png",
  "/manifest.webmanifest",
];

const manifest = JSON.parse(fs.readFileSync(MANIFEST, "utf8"));
const tokens = JSON.parse(fs.readFileSync(TOKENS, "utf8"));
const deepSpace = tokens.themes["deep-space"];
const swSource = fs.readFileSync(SW, "utf8");

const iconOf = (size, purpose) => manifest.icons.find(
  (icon) => icon.sizes === `${size}x${size}` && (icon.purpose || "any") === purpose);

/* ── 1. Manifest fields and colours ─────────────────────────────────── */
await check("manifest: Jarvis, standalone, / start + scope, id and orientation", () => {
  assert.equal(manifest.name, "Jarvis");
  assert.equal(manifest.short_name, "Jarvis");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "/");
  assert.equal(manifest.scope, "/");
  assert.equal(manifest.id, "/");
  assert.equal(manifest.orientation, "any");
  assert.ok(String(manifest.description || "").length > 20, "no plain description");
});

await check("manifest: theme/background colours are the HUD's own deep-space tokens", () => {
  assert.equal(manifest.background_color, deepSpace.surfaceSunken.$value,
    `background_color ${manifest.background_color} is not deep-space surfaceSunken ${deepSpace.surfaceSunken.$value}`);
  assert.equal(manifest.theme_color, deepSpace.swatchReactorGround.$value,
    `theme_color ${manifest.theme_color} is not deep-space swatchReactorGround ${deepSpace.swatchReactorGround.$value}`);
});

await check("manifest: exactly three local icons (192, 512, maskable 512), none remote", () => {
  assert.ok(Array.isArray(manifest.icons), "no icons array");
  const described = manifest.icons.map((icon) => `${icon.sizes} ${icon.purpose || "any"} ${icon.type}`);
  assert.deepEqual(described, [
    "192x192 any image/png",
    "512x512 any image/png",
    "512x512 maskable image/png",
  ]);
  for (const icon of manifest.icons) {
    assert.ok(!/^[a-z]+:\/\//i.test(icon.src), `remote icon address: ${icon.src}`);
    assert.ok(icon.src.startsWith("icons/"), `icon is not a local icons/ path: ${icon.src}`);
  }
  assert.ok(!/https?:\/\//i.test(fs.readFileSync(MANIFEST, "utf8")),
    "the manifest names a remote origin");
});

/* ── 2. Icons: real PNGs, right sizes, mark inside the maskable safe zone ── */
await check("icons: the three files are real PNGs with the declared sizes", () => {
  for (const icon of manifest.icons) {
    const file = path.join(SRC, icon.src);
    assert.ok(fs.existsSync(file), `${icon.src} does not exist`);
    const size = pngSize(file);
    assert.ok(size, `${icon.src} is not a PNG`);
    const [width, height] = icon.sizes.split("x").map(Number);
    assert.deepEqual(size, { width, height }, `${icon.src} is ${size.width}x${size.height}`);
    assert.ok(fs.statSync(file).size < 20 * 1024, `${icon.src} is too big to be a simple tile`);
  }
});

await check("icons: token background, ice mark, and the maskable mark inside the safe zone", async () => {
  const jarvis = await startJarvis();
  const browser = await K.launch();
  const page = await browser.newPage();
  try {
    await page.goto(jarvis.base + "/");
    const readIcon = (url) => page.evaluate(async (iconUrl) => {
      const response = await fetch(iconUrl);
      const image = await createImageBitmap(await response.blob());
      const canvas = document.createElement("canvas");
      canvas.width = image.width;
      canvas.height = image.height;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0);
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const w = canvas.width;
      const h = canvas.height;
      const hex = (index) => `#${[0, 1, 2]
        .map((channel) => data[index + channel].toString(16).padStart(2, "0")).join("")}`;
      const corners = [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]]
        .map(([x, y]) => hex((y * w + x) * 4));
      let ink = 0;
      let minX = w, minY = h, maxX = -1, maxY = -1;
      for (let y = 0; y < h; y += 1) {
        for (let x = 0; x < w; x += 1) {
          const at = (y * w + x) * 4;
          // The mark is the accent #38f0ff; edges are antialiased toward the
          // background, so a generous "near the accent" band is the ink test.
          if (data[at] < 130 && data[at + 1] > 190 && data[at + 2] > 190) {
            ink += 1;
            minX = Math.min(minX, x); maxX = Math.max(maxX, x);
            minY = Math.min(minY, y); maxY = Math.max(maxY, y);
          }
        }
      }
      return { w, h, corners, ink, bbox: [minX, minY, maxX, maxY] };
    }, url);

    const regular = await readIcon("/" + iconOf(512, "any").src);
    const maskable = await readIcon("/" + iconOf(512, "maskable").src);
    const small = await readIcon("/" + iconOf(192, "any").src);
    for (const [name, icon] of [["192", small], ["512", regular], ["maskable 512", maskable]]) {
      assert.deepEqual(icon.corners, ["#04070c", "#04070c", "#04070c", "#04070c"],
        `${name} icon does not sit on the token background`);
      assert.ok(icon.ink > 50, `${name} icon has no mark`);
    }
    const safe = { min: 512 * 0.10, max: 512 * 0.90 };
    assert.ok(maskable.bbox[0] >= safe.min && maskable.bbox[1] >= safe.min
      && maskable.bbox[2] <= safe.max && maskable.bbox[3] <= safe.max,
    `the maskable mark leaves the 80% safe zone: ${JSON.stringify(maskable.bbox)}`);
    const regularWidth = regular.bbox[2] - regular.bbox[0];
    const maskableWidth = maskable.bbox[2] - maskable.bbox[0];
    assert.ok(regularWidth > maskableWidth,
      `the maskable mark (${maskableWidth}px) is not smaller than the regular one (${regularWidth}px)`);
  } finally {
    await page.close();
    await browser.close();
    await jarvis.close();
  }
});

/* ── 3. sw.js static rules ──────────────────────────────────────────── */
await check("sw.js: no backend route, no per-person state words, no remote address", () => {
  assert.ok(!/\/api/i.test(swSource), "sw.js names a backend route");
  assert.ok(!/cookie/i.test(swSource), "sw.js mentions cookies");
  assert.ok(!/set-cookie/i.test(swSource), "sw.js handles Set-Cookie");
  assert.ok(!/authorization/i.test(swSource), "sw.js mentions an authorization header");
  assert.ok(!/token/i.test(swSource), "sw.js mentions a token");
  assert.ok(!/jarvis_token/i.test(swSource), "sw.js names the session key");
  assert.ok(!/https?:\/\//i.test(swSource), "sw.js names a remote origin");
  assert.ok(!/\bimportScripts\b/i.test(swSource), "sw.js pulls code from elsewhere");
});

await check("sw.js: the cache list is exactly the manifest + its three icons", () => {
  const match = /const SHELL_FILES = Object\.freeze\(\[([\s\S]*?)\]\)/.exec(swSource);
  assert.ok(match, "SHELL_FILES is not the frozen list this test reads");
  const listed = [...match[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(listed, EXPECTED_CACHE_PATHS, "the cached shell list changed");
  for (const pathname of listed) {
    assert.ok(pathname.startsWith("/") && !/\/api/i.test(pathname),
      `a non-static path would be cached: ${pathname}`);
    assert.ok(fs.existsSync(path.join(SRC, pathname)), `${pathname} is not a file in src/`);
  }
});

await check("sw.js: writes only during install; fetch never stores an answer", () => {
  const install = swSource.indexOf('self.addEventListener("install"');
  const fetchHandler = swSource.indexOf('self.addEventListener("fetch"');
  assert.ok(install !== -1 && fetchHandler !== -1, "install/fetch handlers missing");
  assert.equal((swSource.match(/cache\.addAll\(/g) || []).length, 1, "more than one addAll");
  assert.equal((swSource.match(/cache\.put\(/g) || []).length, 0, "cache.put is used");
  assert.equal((swSource.match(/cache\.add\(/g) || []).length, 0, "cache.add is used");
  assert.ok(install < swSource.indexOf("cache.addAll("),
    "the addAll is not inside the install handler");
  assert.ok(swSource.indexOf("cache.addAll(") < fetchHandler,
    "a response is stored inside the fetch handler");
  assert.ok(!/cache\.(put|add|addAll)\(/.test(swSource.slice(fetchHandler)),
    "the fetch handler stores something");
});

await check("sw.js: GET only, same-origin only, the four files only", () => {
  assert.match(swSource, /request\.method\s*!==\s*"GET"/, "no GET-only guard");
  assert.match(swSource, /url\.origin\s*!==\s*self\.location\.origin/, "no same-origin guard");
  assert.match(swSource, /!SHELL_PATHS\.has\(url\.pathname\)/, "no frozen-path guard");
  const body = swSource.slice(swSource.indexOf('self.addEventListener("fetch"'));
  assert.ok(body.indexOf('"GET"') < body.indexOf("caches.open"),
    "the cache is reached before the method guard");
  assert.ok(body.indexOf("url.origin") < body.indexOf("caches.open"),
    "the cache is reached before the origin guard");
  assert.ok(body.indexOf("SHELL_PATHS.has") < body.indexOf("caches.open"),
    "the cache is reached before the frozen-path guard");
});

await check("sw.js: skipWaiting only behind the update message; clients.claim on activate", () => {
  const messageAt = swSource.indexOf('self.addEventListener("message"');
  const skipAt = swSource.indexOf("self.skipWaiting(");
  const activateAt = swSource.indexOf('self.addEventListener("activate"');
  const claimAt = swSource.indexOf("self.clients.claim(");
  assert.ok(messageAt !== -1 && skipAt !== -1, "no message-gated skipWaiting");
  assert.equal((swSource.match(/self\.skipWaiting\(/g) || []).length, 1,
    "skipWaiting is called more than once");
  assert.ok(messageAt < skipAt, "skipWaiting is not inside the message handler");
  assert.ok(activateAt !== -1 && claimAt > activateAt,
    "clients.claim is not in the activate handler");
  assert.ok(skipAt > activateAt, "skipWaiting runs outside the update flow");
});

/* ── 4. A real browser: the worker behaves as the source says ───────── */
await check("browser over loopback (secure context): caches the four files, nothing else", async () => {
  const jarvis = await startJarvis();
  const remote = await startRemote();
  const browser = await K.launch();
  const page = await browser.newPage();
  try {
    await page.goto(jarvis.base + "/");
    await page.evaluate(() => navigator.serviceWorker.register("/sw.js"));
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null,
      { timeout: 15000 });
    await page.waitForTimeout(400);

    const snapshot = () => page.evaluate(async () => {
      const out = [];
      for (const name of await caches.keys()) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
          out.push({ cache: name, url: request.url, method: request.method });
        }
      }
      return out.sort((a, b) => a.url.localeCompare(b.url));
    });

    const before = await snapshot();
    assert.equal(before.length, 4, `cache holds ${before.length} entries, not 4`);
    assert.deepEqual(before.map((entry) => new URL(entry.url).pathname).sort(),
      EXPECTED_CACHE_PATHS);
    assert.ok(before.every((entry) => new URL(entry.url).origin === new URL(jarvis.base).origin),
      "the cache holds an entry from another origin");
    assert.ok(before.every((entry) => entry.method === "GET"), "a non-GET request was cached");

    const getAnswer = await page.evaluate(async () => {
      const response = await fetch("/api/ping", { cache: "no-store" });
      return { ok: response.ok, text: await response.text() };
    });
    assert.equal(getAnswer.ok, true, "the backend GET did not reach the network");
    const postAnswer = await page.evaluate(async () => {
      const response = await fetch("/api/ping", { method: "POST", body: "{}" });
      return { ok: response.ok, text: await response.text() };
    });
    assert.equal(postAnswer.ok, true, "the backend POST did not reach the network");
    const pageAnswer = await page.evaluate(async () => {
      const response = await fetch("/jarvis_hud.html", { cache: "no-store" });
      return response.ok;
    });
    assert.equal(pageAnswer, true, "the page did not fall through to the network");
    const remoteAnswer = await page.evaluate(async (url) => {
      const response = await fetch(url);
      return { ok: response.ok, text: await response.text() };
    }, remote.url);
    assert.equal(remoteAnswer.ok, true, "the remote fetch did not reach the network");

    const after = await snapshot();
    assert.deepEqual(after, before, "a request-time response was stored in the cache");
    assert.ok(jarvis.calls.includes("GET /api/ping"), "the GET /api/ping never reached the server");
    assert.ok(jarvis.calls.includes("POST /api/ping"), "the POST /api/ping never reached the server");

    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) await registration.unregister();
      const names = await caches.keys();
      for (const name of names) await caches.delete(name);
    });
  } finally {
    await page.close();
    await browser.close();
    await jarvis.close();
    await remote.close();
  }
});

/* ── 5. This slice does not touch the HUD page ─────────────────────── */
await check("the three HUD page copies are untouched: hooks are a later slice", () => {
  for (const file of TWINS) {
    const html = fs.readFileSync(file, "utf8");
    const name = path.basename(path.dirname(file)) + "/" + path.basename(file);
    assert.ok(!/rel=["']?manifest/i.test(html), `${name} already links a manifest`);
    assert.ok(!/name=["']theme-color/i.test(html), `${name} already has a theme-color meta`);
    assert.ok(!/serviceWorker\.register/i.test(html), `${name} already registers a worker`);
  }
});

console.log(`\n${fails.length ? `${fails.length} failed: ` + fails.join(", ") : "all passed"}`);
if (fails.length) process.exit(1);
