/**
 * hud-web-bridge.mjs — the browser half of the universal HUD (PWA slice 2).
 *
 * The page is served by a small in-test HTTP server (static files + the API
 * routes the HUD reads) and opened WITHOUT `__TAURI__`, which is exactly what
 * a tablet/laptop browser gets. The desktop path is the same page opened WITH
 * `__TAURI__` defined: the bridge must stay completely out of the way there.
 *
 * What is proven here, one check each:
 *   1. desktop: the bridge does not activate and calls no Tauri command;
 *   2. browser: the bridge activates, replaces EventSource, and offers the
 *      pairing sheet when the PC refuses a session (401/403);
 *   3. a wrong key is refused with words, the right key pairs, and the key is
 *      in no URL, no localStorage and no console line;
 *   4. the fetch-SSE reader carries the token header and the cookie, parses
 *      frames split across chunks (including a split multi-byte character),
 *      and reconnects after the stream drops;
 *   5. the honest link verdict: catching up holds Approve and keeps Deny
 *      enabled, then linked releases Approve;
 *   6. per-device layout: saved in this browser's localStorage through the
 *      real normalizer, restored on reload, and never written by the desktop;
 *   7. the one launcher focuses the page's own chat box in a browser;
 *   8. no client-side speech recogniser exists in any of the three twins, and
 *      the web mic says web voice is not here yet instead of listening;
 *   9. the host-change guard refuses to send the remembered key elsewhere.
 *
 * The real iPad/PWA device rows are NOT-TESTABLE in this container: this is
 * the page behaviour a real browser can be expected to have, not a device test.
 */
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, "..", "src");
const TWINS = [
  path.join(SRC, "jarvis_hud.html"),
  path.join(HERE, "..", "..", "backend", "jarvis_hud.html"),
  path.join(HERE, "..", "..", "jarvis-backend", "jarvis_hud.html"),
];
const GOOD_KEY = "jdk1.d0123abcd." + "a".repeat(43);
const WRONG_KEY = "jdk1.d0123abcd." + "b".repeat(43);

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (error) { fails.push(name); console.log(`FAIL  ${name}\n      ${error.message}`); }
};

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".woff": "font/woff", ".woff2": "font/woff2",
  ".png": "image/png", ".svg": "image/svg+xml" };

/* One server for static files AND the API the page reads. Each scenario
 * mutates `config`, so a test drives a real browser against real HTTP. */
function startServer() {
  const config = {
    expectedKey: GOOD_KEY,
    sessionCookie: "",
    statusMode: "deny",     // "deny" = 401; "ok" = 200
    pendingMode: "ok",
    statusDelayMs: 0,
    pendingDelayMs: 0,
    sse: "idle",            // "idle" | "chunks" | "drop" | "deny"
    sseChunks: [],
    sseChunkDelayMs: 15,
    sseKeepOpen: true,
    apiEvents: 0,
    connections: 0,
    requests: [],
    pairCalls: [],
    pending: [],
    approveMode: "ok",      // "risky" = the PC refuses an unsigned risky approval
  };
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    const pathname = url.pathname;
    const record = { method: req.method, path: pathname, headers: req.headers, url: req.url };
    config.requests.push(record);
    const origin = "http://" + (req.headers.host || "127.0.0.1");
    const json = (status, body, extraHeaders) => {
      res.writeHead(status, Object.assign({
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Cache-Control": "no-store",
      }, extraHeaders || {}));
      res.end(JSON.stringify(body));
    };
    if (pathname.startsWith("/api/")) {
      if (pathname === "/api/devices/web-session" && req.method === "POST") {
        let body = "";
        req.on("data", (chunk) => { body += chunk; });
        req.on("end", () => {
          const presented = String(req.headers["x-jarvis-token"] || "");
          config.pairCalls.push({ presented, body });
          if (presented !== config.expectedKey) {
            return json(401, { ok: false, key: "device_removed",
              error: "This device is no longer paired." });
          }
          config.sessionCookie = "jarvis_token=" + presented + "; Path=/; HttpOnly; SameSite=Strict";
          config.statusMode = "ok";
          return json(200, { ok: true, device_id: "d0123abcd",
            device_name: "Suite Browser", kind: "tablet", from_this_pc: false },
            { "Set-Cookie": config.sessionCookie });
        });
        return;
      }
      if (pathname === "/api/devices/web-logout") {
        config.sessionCookie = "";
        config.statusMode = "deny";
        return json(200, { ok: true });
      }
      if (pathname === "/api/status") {
        const answer = () => {
          if (config.statusMode !== "ok") {
            return json(401, { error: "bad or missing X-Jarvis-Token" });
          }
          json(200, { jarvis: true, ollama: true, proxy: false, online: true,
            link: { connected: true, stale: false }, pending: config.pending.length });
        };
        if (config.statusDelayMs) setTimeout(answer, config.statusDelayMs);
        else answer();
        return;
      }
      if (pathname === "/api/pending") {
        const answer = () => {
          if (config.pendingMode !== "ok") {
            return json(401, { error: "bad or missing X-Jarvis-Token" });
          }
          json(200, { available: true, pending: config.pending, history: [] });
        };
        if (config.pendingDelayMs) setTimeout(answer, config.pendingDelayMs);
        else answer();
        return;
      }
      if (pathname === "/api/events") {
        config.apiEvents += 1;
        config.connections += 1;
        if (config.sse === "deny" || config.statusMode !== "ok") {
          return json(401, { error: "bad or missing X-Jarvis-Token" });
        }
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-store",
          "Connection": "keep-alive",
        });
        const chunks = config.sse === "chunks" ? config.sseChunks : [];
        let at = 0;
        const writeNext = () => {
          if (config.sse === "drop") {
            if (at === 0) {
              // An id'd frame, then a drop: the reconnect must say `since=`.
              res.write('id: 4242\nevent: hello\ndata: {"stale":false}\n\n');
              at += 1;
              setTimeout(() => { try { res.end(); } catch (e) { /* gone */ } }, 30);
            }
            return;
          }
          if (at < chunks.length) {
            res.write(chunks[at]);
            at += 1;
            setTimeout(writeNext, config.sseChunkDelayMs);
            return;
          }
          if (!config.sseKeepOpen) { try { res.end(); } catch (e) { /* gone */ } }
        };
        writeNext();
        req.on("close", () => { try { res.end(); } catch (e) { /* gone */ } });
        return;
      }
      if ((pathname === "/api/approve" || pathname === "/api/deny") && req.method === "POST") {
        if (config.approveMode === "risky" && pathname === "/api/approve") {
          return json(403, { ok: false, key: "no_approval_key",
            error: "This approval needs the approval key registered on the paired phone." });
        }
        return json(200, { ok: true });
      }
      if (pathname === "/api/initiative") return json(200, { available: true, items: [] });
      if (pathname === "/api/memory/pending") return json(200, { available: true, pending: [] });
      if (pathname === "/api/presets") return json(200, { available: true, presets: [] });
      return json(200, {});
    }
    const rel = decodeURIComponent(pathname).replace(/^\//, "");
    const file = path.join(SRC, rel);
    if (!file.startsWith(SRC) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); return res.end();
    }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    res.end(fs.readFileSync(file));
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({
        base: `http://127.0.0.1:${server.address().port}`,
        config,
        close: () => server.close(),
      });
    });
  });
}

function watch(page, log) {
  page.on("pageerror", (error) => log.errors.push(String(error)));
  page.on("console", (message) => {
    const text = message.text();
    log.console.push(text);
    if (message.type() === "error" && !/favicon|Failed to load resource/.test(text)) {
      log.errors.push("console: " + text);
    }
  });
  return log;
}

async function openWeb(server, options = {}) {
  const browser = await K.launch();
  const page = await browser.newPage({ viewport: options.viewport || { width: 1280, height: 820 } });
  const log = watch(page, { errors: [], console: [] });
  await page.addInitScript(() => {
    window.__linkHistory = [];
    window.addEventListener("jarvis-link-status", (event) => {
      window.__linkHistory.push(event.detail);
    });
    window.__mediaCalls = 0;
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      const real = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = function () {
        window.__mediaCalls += 1;
        return real.apply(this, arguments);
      };
    }
  });
  await page.goto(server.base + "/jarvis_hud.html");
  await page.waitForTimeout(options.waitMs || 1200);
  return { browser, page, log };
}

async function openDesktop(server) {
  const browser = await K.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  const log = watch(page, { errors: [], console: [] });
  await page.addInitScript(() => {
    window.__tauriInvokes = [];
    window.__TAURI__ = { core: { invoke: async (command) => {
      window.__tauriInvokes.push(command);
      return null;
    } } };
  });
  await page.goto(server.base + "/jarvis_hud.html");
  await page.waitForTimeout(900);
  return { browser, page, log };
}

async function closeApp(app) {
  await app.page.close();
  await app.browser.close();
}

async function pair(page, key) {
  await page.evaluate((value) => {
    const input = document.getElementById("hud-web-pair-key");
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    document.getElementById("hud-web-pair-go").click();
  }, key);
  await page.waitForTimeout(900);
}

const server = await startServer();

/* ── 1. Desktop: the bridge must not exist there ───────────────────── */
await check("desktop webview: the bridge does not activate and calls no Tauri command", async () => {
  const app = await openDesktop(server);
  const facts = await app.page.evaluate(() => ({
    webMode: Boolean(window.__JARVIS_WEB_MODE),
    bridge: Boolean(window.__jarvisWebBridge),
    overlay: Boolean(document.getElementById("hud-web-pair")),
    esName: typeof EventSource === "function" ? EventSource.name : "none",
    fetchWrapped: Boolean(window.fetch && window.fetch.__jarvisBridge),
    invokes: window.__tauriInvokes || [],
  }));
  await closeApp(app);
  assert.equal(facts.webMode, false, "the web mode flag was set in the desktop webview");
  assert.equal(facts.bridge, false, "the browser bridge object exists in the desktop webview");
  assert.equal(facts.overlay, false, "a pairing overlay was added in the desktop webview");
  assert.equal(facts.fetchWrapped, false, "the bridge wrapped window.fetch in the desktop webview");
  assert.notEqual(facts.esName, "BridgeEventSource", "the bridge replaced EventSource in the desktop webview");
  assert.ok(!facts.invokes.some((command) => /hud_layout/.test(String(command))),
    "the bridge read or wrote a HUD layout through Tauri in a desktop page");
});

/* ── 2. Browser: bridge activates; a refused session shows the sheet ── */
await check("browser: the bridge activates, replaces EventSource, and offers pairing on 401", async () => {
  server.config.statusMode = "deny";
  const app = await openWeb(server);
  const facts = await app.page.evaluate(() => {
    const overlay = document.getElementById("hud-web-pair");
    return {
      webMode: Boolean(window.__JARVIS_WEB_MODE),
      bridge: Boolean(window.__jarvisWebBridge),
      esName: EventSource.name,
      overlayShown: Boolean(overlay && !overlay.hidden),
      hasInput: Boolean(document.getElementById("hud-web-pair-key")),
      inputType: (document.getElementById("hud-web-pair-key") || {}).type,
    };
  });
  await closeApp(app);
  assert.equal(facts.webMode, true, "the bridge did not mark the page as web mode");
  assert.equal(facts.bridge, true, "window.__jarvisWebBridge is missing");
  assert.equal(facts.esName, "BridgeEventSource", "EventSource was not replaced by the fetch-SSE shim");
  assert.equal(facts.overlayShown, true, "a 401 from /api/status did not open the pairing sheet");
  assert.equal(facts.hasInput, true, "the pairing sheet has no key input");
  assert.equal(facts.inputType, "password", "the pairing key input is not masked");
});

/* ── 3. Pairing: wrong key refused, right key pairs, key never sticks ── */
await check("browser: a wrong key is refused, the right key pairs, and the key is in no URL/localStorage/console", async () => {
  server.config.statusMode = "deny";
  server.config.pending = [];
  server.config.expectedKey = GOOD_KEY;
  const app = await openWeb(server);
  const keyBefore = server.config.pairCalls.length;
  await pair(app.page, WRONG_KEY);
  const afterWrong = await app.page.evaluate(() => ({
    errors: (document.getElementById("hud-web-pair-error") || {}).textContent || "",
    overlayShown: !document.getElementById("hud-web-pair").hidden,
    pairs: window.__jarvisWebBridge.state.pairs,
  }));
  assert.equal(afterWrong.overlayShown, true, "a refused key closed the pairing sheet");
  assert.match(afterWrong.errors, /removed|pair|different|accept/i,
    "a refused key said nothing useful: " + afterWrong.errors);
  assert.equal(afterWrong.pairs, 0, "a refused key was counted as a pairing");
  const refusedCall = server.config.pairCalls[keyBefore];
  assert.ok(refusedCall && refusedCall.presented === WRONG_KEY,
    "the pairing POST did not carry the pasted key in the header");

  await pair(app.page, GOOD_KEY);
  await app.page.waitForTimeout(900);
  const afterRight = await app.page.evaluate(() => {
    const values = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      values.push(key + "=" + String(localStorage.getItem(key)));
    }
    return {
      overlayShown: Boolean(document.getElementById("hud-web-pair") && !document.getElementById("hud-web-pair").hidden),
      pairs: window.__jarvisWebBridge.state.pairs,
      pairedHost: localStorage.getItem("jarvis.web.paired_host"),
      host: location.host,
      storage: values.join("\n"),
      keyInMemory: window.__jarvisWebBridge.state.keyInMemory,
      link: window.__jarvisWebBridge.state.lastLink,
    };
  });
  await closeApp(app);
  assert.equal(afterRight.overlayShown, false, "the right key did not close the pairing sheet");
  assert.equal(afterRight.pairs, 1, "the right key was not counted as one pairing");
  assert.equal(afterRight.pairedHost, afterRight.host, "the paired host was not remembered");
  assert.equal(afterRight.keyInMemory, GOOD_KEY, "the paired key was not held in this tab's memory");
  assert.ok(!afterRight.storage.includes(GOOD_KEY),
    "the pairing key was written to localStorage (CLAUDE.md rule 3)");
  const keyInUrls = server.config.requests.filter((r) => String(r.url).includes(GOOD_KEY));
  assert.deepEqual(keyInUrls.map((r) => r.url), [], "the pairing key appeared in a request URL");
  const logged = server.config.requests.filter((r) =>
    String((r.headers && r.headers["x-jarvis-token"]) || "") === GOOD_KEY);
  assert.ok(logged.length >= 1, "no request carried the device key in the X-Jarvis-Token header");
  assert.ok(logged.every((r) => !String(r.url).includes(GOOD_KEY)),
    "a request put the key in its query string instead of the header");
  const consoleText = app.log.console.join("\n");
  assert.ok(!consoleText.includes(GOOD_KEY), "the pairing key was logged to the console");
});

/* ── 4. SSE reader: headers, split frames, multi-byte split, reconnect ── */
await check("browser: fetch-SSE carries the token header and reconnects after a drop", async () => {
  server.config.statusMode = "deny";
  server.config.sse = "drop";
  const app = await openWeb(server);
  await pair(app.page, GOOD_KEY);
  await app.page.waitForTimeout(400);
  await app.page.evaluate(() => window.__jarvisWebBridge.configure({ reconnectDelayMin: 120, reconnectDelayMax: 240 }));
  await app.page.waitForTimeout(1800);
  const facts = await app.page.evaluate(() => ({
    connections: window.__jarvisWebBridge.state.connections,
    reconnects: window.__jarvisWebBridge.state.reconnects,
    link: window.__jarvisWebBridge.state.lastLink,
  }));
  const eventsCalls = server.config.requests.filter((r) => r.path === "/api/events");
  await closeApp(app);
  assert.ok(eventsCalls.length >= 1, "the page never asked for /api/events over fetch()");
  const eventRequest = eventsCalls[eventsCalls.length - 1];
  assert.equal(eventRequest.headers["x-jarvis-client"], "hud",
    "the SSE fetch is missing X-Jarvis-Client: hud");
  assert.equal(eventRequest.headers["accept"], "text/event-stream",
    "the SSE fetch did not ask for an event stream");
  assert.equal(eventRequest.headers["x-jarvis-token"], GOOD_KEY,
    "the SSE fetch did not carry the device key in the token header");
  assert.ok(String(eventRequest.headers.cookie || "").includes("jarvis_token="),
    "the SSE fetch did not send the session cookie");
  assert.ok(facts.connections >= 2, `the stream did not reconnect after a drop (connections=${facts.connections})`);
  assert.ok(facts.link && facts.link.tone === "bad", "a dropped stream did not say the link was bad");
  // The drop is an id'd frame (id: 4242), so every reconnect must ask the
  // server not to replay what was already delivered. The bridge does NOT
  // de-duplicate a frame the server sends twice (the page treats events as a
  // doorbell and re-reads state), so this asserts the `since=` request, not
  // duplicate suppression.
  const sinceCalls = eventsCalls
    .map((r) => new URL("http://mock" + String(r.url)).searchParams.get("since"))
    .filter(Boolean);
  assert.ok(sinceCalls.includes("4242"),
    `the reconnect did not carry since=4242 (saw ${JSON.stringify(sinceCalls)})`);
});

await check("browser: the SSE parser keeps frames and multi-byte characters split across chunks", async () => {
  server.config.sse = "chunks";
  const splitHello = 'event: hello\ndata: {"stale":false}\n\n';
  const marker = "héllo-✓";
  const frame = `event: activity\ndata: ${JSON.stringify({ text: marker, n: 7 })}\n\n`;
  const bytes = new TextEncoder().encode(frame);
  // Split INSIDE a multi-byte character: find the last start byte (>= 0xC0)
  // and cut right after it, so the continuation bytes arrive in the next write.
  let cut = bytes.length - 1;
  for (let i = bytes.length - 1; i >= 0; i -= 1) {
    if (bytes[i] >= 0xc0) { cut = i + 1; break; }
  }
  server.config.sseChunks = [
    splitHello.slice(0, 9),              // an event name cut mid-word
    splitHello.slice(9),
    bytes.slice(0, cut),                 // a multi-byte char cut in half
    bytes.slice(cut),
    'event: power\ndata: {"value":"standby"}\n\n',
  ];
  server.config.sseKeepOpen = true;
  const app = await openWeb(server);
  await K.until(app.page, "the split activity frame to arrive", async () =>
    (await app.page.evaluate(() => window.__jarvisWebBridge.state.frames
      .some((f) => f.type === "activity"))), { ms: 8000 });
  const facts = await app.page.evaluate(() => {
    const frames = window.__jarvisWebBridge.state.frames;
    const activity = frames.find((f) => f.type === "activity");
    let body = null;
    try { body = JSON.parse(activity.data); } catch (e) { body = null; }
    return { bodies: frames.map((f) => f.type), activityBody: body,
      hello: frames.find((f) => f.type === "hello") || null };
  });
  await closeApp(app);
  assert.ok(facts.hello, "the hello frame split across chunks never arrived");
  assert.deepEqual(facts.activityBody, { text: marker, n: 7 },
    "the activity frame split inside a multi-byte character was dropped or mangled");
  assert.ok(facts.bodies.includes("power"), "a later frame was lost after the split frames");
});

/* ── 5. The honest link verdict and the Approve/Deny rule ───────────── */
await check("browser: catching up holds Approve and keeps Deny enabled, then linked releases Approve", async () => {
  server.config.statusMode = "ok";
  server.config.sse = "chunks";
  server.config.sseChunks = ['event: hello\ndata: {"stale":false}\n\n'];
  server.config.sseKeepOpen = true;
  server.config.pending = [{ id: "91", action: "send_email", tier: "ask",
    replaces: false, expires_in: 120 }];
  const app = await openWeb(server);
  await K.until(app.page, "the approval card to paint", async () =>
    (await app.page.evaluate(() => document.querySelectorAll("#approvals .appr").length)) >= 1,
  { ms: 6000 });
  const duringCatchUp = await app.page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("jarvis-link-status", { detail: {
      up: true, words: "stale — reconnecting", short: "reconnecting", tone: "warn" } }));
    const card = document.querySelector("#approvals .appr");
    return {
      approveDisabled: Boolean(card && card.querySelector(".yes") && card.querySelector(".yes").disabled),
      denyEnabled: Boolean(card && card.querySelector(".no") && !card.querySelector(".no").disabled),
      chip: (document.getElementById("hud-safety-link") || {}).textContent || "",
    };
  });
  assert.equal(duringCatchUp.approveDisabled, true, "catching up did not hold Approve");
  assert.equal(duringCatchUp.denyEnabled, true, "catching up disabled Deny");
  const afterLinked = await app.page.evaluate(() => {
    window.dispatchEvent(new CustomEvent("jarvis-link-status", { detail: {
      up: true, words: "linked", short: "linked", tone: "ok" } }));
    const card = document.querySelector("#approvals .appr");
    return Boolean(card && card.querySelector(".yes") && !card.querySelector(".yes").disabled);
  });
  assert.equal(afterLinked, true, "a linked verdict did not release Approve");
  const history = await app.page.evaluate(() => window.__linkHistory.map((d) => d.short));
  await closeApp(app);
  assert.ok(history.includes("reconnecting"),
    `the bridge never pushed a catching-up link verdict (saw ${JSON.stringify(history)})`);
  assert.ok(history.includes("linked"),
    `the bridge never pushed a linked verdict after /api/status + /api/pending resolved (saw ${JSON.stringify(history)})`);
  assert.ok(history.indexOf("reconnecting") < history.indexOf("linked"),
    "the link claimed linked before it had caught up");
});

/* ── 6. Per-device layout: saved here, restored here, not on the PC ── */
await check("browser: a layout save goes to this browser's localStorage and survives a reload", async () => {
  server.config.statusMode = "ok";
  server.config.pending = [];
  const app = await openWeb(server);
  const saved = await app.page.evaluate(async () => {
    const layout = await import("./hud-layout.js");
    const store = await import("./hud-layout-store.js");
    const answer = await store.saveLayout(layout.presetLayout("ambient"));
    return {
      key: store.WEB_KEY,
      saved: answer.saved,
      source: answer.source,
      raw: localStorage.getItem(store.WEB_KEY),
      protectedIds: layout.PROTECTED_IDS,
    };
  });
  assert.equal(saved.key, "jarvis.web.hud_layout.v1", "the per-device layout key changed");
  assert.equal(saved.saved, true, "saving this browser's own layout was refused");
  assert.equal(saved.source, "browser", "the browser layout was saved through the desktop store");
  assert.ok(saved.raw && saved.raw.length > 100, "nothing was written to this browser's layout key");
  const stored = JSON.parse(saved.raw);
  assert.ok(Array.isArray(saved.protectedIds) && saved.protectedIds.length > 0,
    "hud-layout.js exports no protected ids to compare");
  await app.page.evaluate(async () => {
    // The stored document is the real one: reload and let the editor adopt it.
    window.location.reload();
  });
  await app.page.waitForLoadState("load");
  await app.page.waitForTimeout(1500);
  const afterReload = await app.page.evaluate(() => ({
    shell: document.documentElement.getAttribute("data-hud-shell"),
    editorPreset: window.__jarvisHudEdit && window.__jarvisHudEdit.layout
      ? window.__jarvisHudEdit.layout.base_preset : null,
  }));
  await closeApp(app);
  assert.equal(afterReload.shell, "center-core",
    "the saved Ambient layout was not applied as the shell on reload");
  assert.equal(afterReload.editorPreset, "ambient",
    "the editor did not adopt this browser's saved layout");
});

await check("desktop: the browser layout store is not written and the desktop store is used", async () => {
  const app = await openDesktop(server);
  const facts = await app.page.evaluate(async () => {
    const store = await import("./hud-layout-store.js");
    const layout = await import("./hud-layout.js");
    const answer = await store.saveLayout(layout.presetLayout("studio"));
    return { saved: answer.saved, source: answer.source,
      webKey: localStorage.getItem(store.WEB_KEY),
      invokes: window.__tauriInvokes || [] };
  });
  await closeApp(app);
  assert.equal(facts.saved, false, "a desktop page said it saved a browser layout");
  assert.equal(facts.webKey, null, "a desktop page wrote the browser layout key");
  assert.ok(facts.invokes.includes("set_hud_layout"),
    "the desktop page did not use the Tauri layout store it always used");
});

/* ── 7. The one launcher focuses the page's own chat box ─────────────── */
await check("browser: the one launcher focuses the chat box (and the dock duplicate stays hidden)", async () => {
  server.config.statusMode = "ok";
  server.config.pending = [];
  const app = await openWeb(server);
  const launcher = await app.page.evaluate(() => {
    const pill = document.getElementById("rail-quickbar");
    const dock = document.getElementById("dock-quickbar");
    const shown = (el) => {
      if (!el) return false;
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return box.width > 0 && box.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    };
    return {
      pillShown: shown(pill),
      pillWords: pill ? (pill.textContent || "").replace(/\s+/g, " ").trim() : "",
      pillTitle: pill ? pill.title : "",
      dockShown: shown(dock),
      openBar: typeof window.__jarvisOpenBar,
    };
  });
  assert.equal(launcher.pillShown, true, "a browser shows no launcher at all");
  assert.equal(launcher.dockShown, false, "a browser shows two launchers (dock lightning is visible too)");
  assert.match(launcher.pillWords, /Open the Jarvis bar/, "the launcher's words do not say what it does");
  assert.equal(launcher.pillTitle, "Open the Jarvis bar", "the launcher's tooltip does not say what it does");
  assert.equal(launcher.openBar, "function", "window.__jarvisOpenBar is not wired in a browser");
  // The click is dispatched on the element itself: an element.click() is the
  // same DOM event the page's own listener receives.
  const focused = await app.page.evaluate(() => {
    const input = document.getElementById("input");
    input.blur();
    document.getElementById("rail-quickbar").click();
    return document.activeElement && document.activeElement.id;
  });
  await closeApp(app);
  assert.equal(focused, "input", "clicking the launcher did not focus the page's chat box");
});

/* ── 8. Client-side speech-to-text is gone; the web mic says so ─────── */
await check("all three twins: no client-side speech recogniser, and the web mic says web voice is not here yet", async () => {
  for (const file of TWINS) {
    const html = fs.readFileSync(file, "utf8");
    assert.ok(!/webkitSpeechRecognition/i.test(html), `${path.basename(path.dirname(file))}/jarvis_hud.html still names webkitSpeechRecognition`);
    assert.ok(!/window\.SpeechRecognition|new\s+SR\s*\(/.test(html), `${file} still creates a browser speech recogniser`);
    assert.ok(!/getUserMedia\s*\(/.test(html), `${file} still opens the microphone itself`);
  }
  const app = await openWeb(server);
  const facts = await app.page.evaluate(() => ({
    stt: (document.getElementById("r-stt") || {}).textContent,
    micTitle: (document.getElementById("mic") || {}).title,
    speechRecognition: typeof window.SpeechRecognition + "/" + typeof window.webkitSpeechRecognition,
  }));
  await app.page.evaluate(() => document.getElementById("mic").click());
  await app.page.waitForTimeout(200);
  const afterClick = await app.page.evaluate(() => ({
    mediaCalls: window.__mediaCalls,
    note: (document.getElementById("hud-web-status") || {}).textContent || "",
    stt: (document.getElementById("r-stt") || {}).textContent,
  }));
  await closeApp(app);
  assert.equal(facts.stt, "not yet", "the web voice readout does not say web voice is not here yet");
  assert.match(String(facts.micTitle), /HTTPS/, "the web mic's tooltip does not say what web voice still needs");
  assert.match(String(facts.micTitle), /web-voice/, "the web mic's tooltip does not name the web-voice update (HTTPS alone is not enough)");
  assert.equal(afterClick.mediaCalls, 0, "the mic opened the microphone in a browser (client STT/mic is forbidden here)");
  const spoken = afterClick.note + " " + afterClick.stt + " " + String(facts.micTitle);
  assert.ok(/HTTPS/.test(spoken) && /web-voice/.test(spoken),
    "clicking the web mic did not say it needs both HTTPS and the web-voice update: " + spoken);
});

/* ── 9. Host-change guard: the remembered key is not sent elsewhere ─── */
await check("browser: a changed host stops the remembered key from being sent", async () => {
  server.config.statusMode = "ok";
  server.config.pending = [];
  const app = await openWeb(server);
  const requestsBefore = server.config.requests.length;
  const guard = await app.page.evaluate(async () => {
    const bridge = window.__jarvisWebBridge;
    bridge.state.keyInMemory = "jdk1.d0123abcd." + "a".repeat(43);
    bridge.rememberPairedHost();
    // While the host matches, the wrapped fetch carries the key...
    await fetch("/api/presets", { cache: "no-store" });
    // ...then the page is served from somewhere else: the guard drops it.
    localStorage.setItem("jarvis.web.paired_host", "some-other-host.example:4711");
    const changed = bridge.dropKeyIfHostChanged();
    const allowed = bridge.sendTokenAllowed();
    await fetch("/api/presets", { cache: "no-store" });
    return { changed, allowed, host: location.host };
  });
  await app.page.waitForTimeout(200);
  const presetRequests = server.config.requests.slice(requestsBefore)
    .filter((r) => r.path === "/api/presets");
  await closeApp(app);
  assert.equal(guard.changed, true, "the host-change guard did not fire");
  assert.equal(guard.allowed, false, "a changed host still allowed the remembered key");
  assert.ok(presetRequests.length >= 2, "the two probe requests never reached the server");
  assert.ok(String(presetRequests[0].headers["x-jarvis-token"] || "").includes("d0123abcd"),
    "the same-host request did not carry the remembered key");
  for (const request of presetRequests.slice(1)) {
    assert.ok(!String(request.headers["x-jarvis-token"] || "").includes("d0123abcd"),
      "a request sent the remembered key to a different host");
  }
});

/* ── 10. A refused session after pairing re-opens the sheet, not silence ── */
await check("browser: losing the session (403) re-opens the pairing sheet", async () => {
  server.config.statusMode = "ok";
  server.config.pending = [];
  const app = await openWeb(server);
  server.config.statusMode = "deny";
  server.config.pendingMode = "deny";
  await app.page.evaluate(async () => {
    await fetch("/api/status", { cache: "no-store" }).catch(() => {});
  });
  await app.page.waitForTimeout(600);
  const facts = await app.page.evaluate(() => ({
    overlay: Boolean(document.getElementById("hud-web-pair") && !document.getElementById("hud-web-pair").hidden),
    link: window.__jarvisWebBridge.state.lastLink,
  }));
  await closeApp(app);
  assert.equal(facts.overlay, true, "a refused session did not re-open the pairing sheet");
  assert.ok(facts.link && facts.link.up === false, "a refused session left the link claiming it was up");
});

/* ── 11. A risky approval refused by the PC says where to answer it ────── */
await check("browser: a risky approval the PC refuses says to answer it on the PC or paired phone", async () => {
  server.config.statusMode = "ok";
  server.config.pendingMode = "ok";
  server.config.approveMode = "risky";
  server.config.pending = [{ id: "92", action: "delete_files", tier: "risky",
    replaces: false, expires_in: 120 }];
  const app = await openWeb(server);
  await K.until(app.page, "the risky card to paint", async () =>
    (await app.page.evaluate(() => document.querySelectorAll("#approvals .appr").length)) >= 1,
  { ms: 6000 });
  await app.page.evaluate(() => {
    const card = document.querySelector("#approvals .appr");
    card.querySelector(".yes").click();
  });
  await app.page.waitForTimeout(600);
  const words = await app.page.evaluate(() => {
    const card = document.querySelector("#approvals .appr");
    return card ? (card.querySelector(".det") || {}).textContent || "" : "";
  });
  server.config.approveMode = "ok";
  server.config.pending = [];
  await closeApp(app);
  assert.match(words, /risky approval/i,
    "a risky refusal was not named as a risky approval: " + JSON.stringify(words));
  assert.match(words, /PC|phone/i,
    "a risky refusal did not say where it can be answered: " + JSON.stringify(words));
  assert.doesNotMatch(words, /no longer waiting/i,
    "a risky refusal was mislabelled as an expired request: " + JSON.stringify(words));
});

await server.close();
console.log(`\n${fails.length ? `${fails.length} failed: ` + fails.join(", ") : "all passed"}`);
if (fails.length) process.exit(1);
