/**
 * hud-web-bridge.js — the browser half of the universal HUD (PWA slice 2).
 *
 * Loaded by one external `<script src="hud-web-bridge.js">` line in the three
 * `jarvis_hud.html` copies (the page's inline-script count is pinned by
 * tests/csp-inline.mjs, so the bridge must stay external). It is a classic
 * script on purpose: it must be able to replace `window.EventSource` and
 * `window.fetch` BEFORE the page's own inline scripts run, and it must define
 * `window.__jarvisOpenBar` before the page's quickbar painter looks for it.
 *
 * DESKTOP IS UNTOUCHED. Inside the Tauri webview `window.__TAURI__` exists
 * before any page script (the shell injects `hud_bootstrap.js` first), and
 * this file returns immediately: no fetch wrapper, no EventSource shim, no
 * overlay, no token of any kind. Every job below is one `hud_bootstrap.js`
 * already owns there (Tauri IPC, the Rust event stream, the Windows quickbar,
 * the settings store), and none of it may run twice.
 *
 * WHAT IT DOES IN A PLAIN BROWSER (no `__TAURI__`):
 *   * pairing: paste the `jdk1...` kind of key the PC printed for this browser
 *     (docs/JARVIS-API.md §90) → `POST /api/devices/web-session` → the PC
 *     answers with the HttpOnly `jarvis_token` cookie. The key is held in this
 *     tab's memory for the tab's whole session (so the requests that follow can
 *     carry it); it is never written to localStorage, never logged, and never
 *     put in a URL. The cookie is what persists. `jarvis.web.paired_host`
 *     remembers which host this browser was paired to; if the page is later
 *     served from a different host the bridge refuses to send the in-memory key
 *     and asks to pair again.
 *   * the live stream: EventSource cannot set a header; a fetch() +
 *     ReadableStream SSE reader can, and carries the cookie too. The bridge
 *     replaces `window.EventSource` with a spec-shaped shim fed by that one
 *     reader, so the page's existing subscribe() code (hello/approval/
 *     proposal/finding/activity/power/wellbeing/schedule) works unchanged. It
 *     reconnects with backoff, asking for `?since=<last id>` each time so the
 *     backend does not replay what was already seen; a frame the server DOES
 *     send twice is not de-duplicated here — the page treats events as a
 *     doorbell (it re-reads state), so a duplicate costs a re-read, never a
 *     wrong action. It also re-syncs on visibilitychange/pageshow.
 *   * the honest link verdict: it pushes `jarvis-link-status` (the same shape
 *     hud_bootstrap.js pushes) — "catching up" until `/api/status` and
 *     `/api/pending` resolve, then linked; offline when the stream drops. The
 *     safety rail's rule is unchanged (Approve waits on a stale link, Deny
 *     never does).
 *   * per-device layout: `jarvis.web.hud_layout.v1` in this browser's
 *     localStorage, normalized by the real `hud-layout.js`. The host PC's
 *     layout is never read or written from here; the desktop store is only
 *     reachable through Tauri IPC, which this script never calls.
 *   * the launcher: in a browser there is no Windows quickbar to open, so the
 *     one "Open the Jarvis bar" control focuses the page's own chat input.
 *   * web voice: the client-side `SpeechRecognition` path has been removed
 *     from the page (a client must not do speech-to-text). The mic here says
 *     so plainly; browser voice waits for the HTTPS/AudioWorklet slice.
 *
 * No token is ever logged, put in a URL, or written to disk. No second HTML
 * shell is created: one pairing overlay and one status line are added to the
 * page that is already there. `default-src 'self'` in the CSP is unchanged.
 *
 * @module hud-web-bridge (classic script, not an ES module)
 */
(function () {
  "use strict";

  /* Desktop: hand everything to the injected shell bootstrap and leave. */
  if (window.__TAURI__) return;
  /* The shell's internal origin exists only inside the desktop webview. A real
   * browser reaches the page through the backend (loopback or a Meshnet/
   * Tailscale address), never through this host name - so a page served under
   * it without __TAURI__ is a bare page, not a browser deployment of the app.
   * Leave it exactly as it always was. */
  if (/(^|\.)tauri\.localhost$/.test(window.location.hostname)) return;
  if (window.__JARVIS_WEB_MODE) return;

  var VERSION = "pwa-slice-2";

  /** This host's pairing marker. A host change invalidates the session path. */
  var HOST_KEY = "jarvis.web.paired_host";
  /** This browser's own HUD layout document (never the PC's). */
  var LAYOUT_KEY = "jarvis.web.hud_layout.v1";
  var CLIENT = "hud";
  var OVERLAY_ID = "hud-web-pair";
  var STATUS_ID = "hud-web-status";
  var RECONNECT_MIN = 1000;
  var RECONNECT_MAX = 30000;
  var DEVICE_KEY_RE = /^jdk1\.d[0-9a-f]{8}\.[A-Za-z0-9_-]{43}$/;

  window.__JARVIS_WEB_MODE = true;

  var nativeFetch = typeof window.fetch === "function"
    ? window.fetch.bind(window)
    : null;

  var state = {
    mode: "web",
    version: VERSION,
    started: false,
    probing: false,
    paired: false,
    session: false,
    catchingUp: true,
    hostOk: true,
    keyInMemory: "",
    incoming: [],
    // SSE reader bookkeeping (exposed for the suite; not a public API).
    stream: null,
    reader: null,
    connecting: false,
    reconnects: 0,
    connections: 0,
    frames: [],
    lastEventId: "",
    lastLink: null,
    pairs: 0,
    errors: [],
    reconnectDelayMin: RECONNECT_MIN,
    reconnectDelayMax: RECONNECT_MAX,
  };

  var esInstances = [];

  /* ---------------------------------------------------------------- *
   * 1. Storage, host guard and headers
   * ---------------------------------------------------------------- */

  function storeGet(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function storeSet(key, value) {
    try { window.localStorage.setItem(key, value); return true; } catch (e) { return false; }
  }
  function storeRemove(key) {
    try { window.localStorage.removeItem(key); } catch (e) { /* private mode */ }
  }

  /** The host this browser was paired to, or "" when it never was. */
  function pairedHost() {
    return String(storeGet(HOST_KEY) || "");
  }

  /** True when the in-memory key may be sent to THIS host. */
  function hostAllowed() {
    var remembered = pairedHost();
    if (!remembered) return true;             // first pairing, nothing to compare
    return remembered === window.location.host;
  }
  state.hostOk = hostAllowed();

  function sendTokenAllowed() {
    return Boolean(state.keyInMemory) && hostAllowed();
  }

  function rememberPairedHost() {
    storeSet(HOST_KEY, window.location.host);
    state.hostOk = true;
  }

 /** The pairing guard's own mutation point: dropping the in-memory key when
   * the page is served from another host. Exposed for the suite. */
  function dropKeyIfHostChanged() {
    if (!hostAllowed()) {
      state.keyInMemory = "";
      state.hostOk = false;
      return true;
    }
    return false;
  }

  /** Headers every bridge request carries. The key rides only while it is
   * still in memory AND the page's host is the paired one. */
  function authHeaders(extra) {
    var headers = { "X-Jarvis-Client": CLIENT };
    if (extra) {
      for (var k in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, k)) headers[k] = extra[k];
      }
    }
    if (sendTokenAllowed()) headers["X-Jarvis-Token"] = state.keyInMemory;
    return headers;
  }

  function sameOrigin(url) {
    try {
      if (typeof url !== "string") return false;
      var resolved = new URL(url, window.location.href);
      return resolved.origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function apiUrl(path) {
    return new URL(path, window.location.href).toString();
  }

  /* ---------------------------------------------------------------- *
   * 2. Link status — the same facts and words hud_bootstrap.js pushes
   * ---------------------------------------------------------------- */

  function pushLink(detail) {
    state.lastLink = detail;
    try {
      window.dispatchEvent(new CustomEvent("jarvis-link-status", { detail: detail }));
    } catch (e) { /* an old engine: the row keeps its last words */ }
    paintStatusLine(detail);
  }

  /** The bootstrap's linkWords(): the page composes its one row from these. */
  function linkCatchingUp() {
    return { up: true, words: "stale — reconnecting", short: "reconnecting", tone: "warn" };
  }
  function linkLinked() {
    return { up: true, words: "linked", short: "linked", tone: "ok" };
  }
  function linkOffline(words) {
    var first = String(words || "no link to your PC").trim().split(/[.!?]\s/)[0];
    return { up: false, words: "offline · " + first, short: "no link", tone: "bad" };
  }
  function linkConnecting() {
    return { up: false, words: "connecting…", short: "connecting", tone: "bad" };
  }

  /* ---------------------------------------------------------------- *
   * 3. A small, plain status line (so a browser user can see the state)
   * ---------------------------------------------------------------- */

  function paintStatusLine(detail) {
    if (!detail || typeof detail !== "object") return;
    var el = document.getElementById(STATUS_ID);
    if (!el) return;
    // The page's own one status row already says this for linked/offline;
    // this line only explains the transient browser states that row cannot
    // ("catching up", "not paired").
    var words = "";
    if (detail.tone === "warn") {
      words = "Catching up with your PC… approvals wait; Deny still works.";
    }
    if (words) el.textContent = words;
    else el.textContent = "";
    el.hidden = !words;
  }

  function ensureStatusLine() {
    if (document.getElementById(STATUS_ID)) return;
    var el = document.createElement("p");
    el.id = STATUS_ID;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.hidden = true;
    el.style.cssText = "position:fixed;left:50%;bottom:12px;transform:translateX(-50%);" +
      "margin:0;padding:6px 12px;max-width:min(680px,calc(100vw - 24px));" +
      "background:rgba(8,13,20,.92);border:1px solid #3a5264;border-radius:6px;" +
      "color:#cdd8e3;font:12px/1.4 system-ui,sans-serif;z-index:70;";
    (document.body || document.documentElement).appendChild(el);
  }

  var noteTimer = 0;
  /** Say one plain sentence in the little browser status line (the mic uses
   *  this for "web voice needs HTTPS"). Never markup - textContent only. */
  function note(words) {
    var el = document.getElementById(STATUS_ID);
    if (!el) return;
    var text = String(words || "").trim();
    el.textContent = text;
    el.hidden = !text;
    if (noteTimer) window.clearTimeout(noteTimer);
    if (text) {
      noteTimer = window.setTimeout(function () {
        if (el.textContent === text) { el.textContent = ""; el.hidden = true; }
      }, 9000);
    }
  }

  /* ---------------------------------------------------------------- *
   * 4. The pairing overlay (one small sheet; textContent only)
   * ---------------------------------------------------------------- */

  var overlay = null;
  var overlayParts = null;

  function wordsForRefusal(reason, fallback) {
    switch (String(reason || "")) {
      case "device_removed":
        return "This browser's key was removed on your PC. Pair this browser again.";
      case "shared_first_pair_only":
        return "Your PC now only accepts this browser's own key, not the old shared one.";
      case "off_network":
        return "Open this page on your own PC or over Tailscale/NordVPN Meshnet. A public address is never used.";
      case "shared_retired":
        return "The old shared key was retired on your PC. Pair this browser with its own key.";
      default:
        return fallback || "The PC did not accept this browser. Pair it again.";
    }
  }

  function buildOverlay() {
    if (overlay) return overlay;
    var wrap = document.createElement("div");
    wrap.id = OVERLAY_ID;
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-modal", "true");
    wrap.setAttribute("aria-label", "Pair this browser with your PC's Jarvis");
    wrap.style.cssText = "position:fixed;inset:0;z-index:90;display:flex;" +
      "align-items:center;justify-content:center;padding:16px;" +
      "background:rgba(3,7,12,.82);font:14px/1.5 system-ui,sans-serif;color:#e6edf5;";

    var card = document.createElement("div");
    card.style.cssText = "width:min(520px,calc(100vw - 32px));box-sizing:border-box;" +
      "background:#0c141e;border:1px solid #3a5264;border-radius:12px;padding:20px;" +
      "box-shadow:0 18px 48px rgba(0,0,0,.55);";

    var h = document.createElement("h2");
    h.textContent = "Pair this browser";
    h.style.cssText = "margin:0 0 8px;font-size:18px;font-weight:600;";
    card.appendChild(h);

    var lead = document.createElement("p");
    lead.textContent = "Jarvis showed a pairing key for this browser on your PC. " +
      "Paste it here once; this browser keeps only the PC's own secure cookie afterwards.";
    lead.style.cssText = "margin:0 0 12px;color:#b9c6d4;";
    card.appendChild(lead);

    var where = document.createElement("p");
    where.textContent = "No key yet? On your PC: Settings → Devices → Add a browser device, " +
      "or run: py -3 jarvis_devices.py --add-device \"iPad Safari\" --kind tablet";
    where.style.cssText = "margin:0 0 12px;color:#8ea1b4;font-size:12px;";
    card.appendChild(where);

    var label = document.createElement("label");
    label.textContent = "Pairing key (starts jdk1…)";
    label.setAttribute("for", "hud-web-pair-key");
    label.style.cssText = "display:block;margin:0 0 4px;font-size:12px;color:#b9c6d4;";
    card.appendChild(label);

    var input = document.createElement("input");
    input.id = "hud-web-pair-key";
    input.type = "password";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = "jdk1.d…";
    input.style.cssText = "width:100%;box-sizing:border-box;padding:10px 12px;margin:0 0 10px;" +
      "border-radius:8px;border:1px solid #3a5264;background:#070d15;color:#e6edf5;" +
      "font:13px/1.2 ui-monospace,Consolas,monospace;";
    card.appendChild(input);

    var row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;";
    var pair = document.createElement("button");
    pair.type = "button";
    pair.id = "hud-web-pair-go";
    pair.textContent = "Pair this browser";
    pair.style.cssText = "padding:9px 16px;border-radius:8px;border:1px solid #2f7f9b;" +
      "background:#0f3341;color:#dff6ff;font:inherit;cursor:pointer;";
    row.appendChild(pair);
    var retry = document.createElement("button");
    retry.type = "button";
    retry.id = "hud-web-pair-retry";
    retry.textContent = "Retry connection";
    retry.style.cssText = "padding:9px 14px;border-radius:8px;border:1px solid #3a5264;" +
      "background:transparent;color:#b9c6d4;font:inherit;cursor:pointer;";
    row.appendChild(retry);
    card.appendChild(row);

    var err = document.createElement("p");
    err.id = "hud-web-pair-error";
    err.setAttribute("role", "alert");
    err.hidden = true;
    err.style.cssText = "margin:10px 0 0;color:#ff9d9d;font-size:13px;";
    card.appendChild(err);

    wrap.appendChild(card);
    overlay = wrap;
    overlayParts = { card: card, input: input, pair: pair, retry: retry, error: err };
    pair.addEventListener("click", function () { submitPairing(); });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); submitPairing(); }
    });
    retry.addEventListener("click", function () { retryConnection(); });
    return wrap;
  }

  function showPairOverlay(message) {
    var wrap = buildOverlay();
    if (!wrap.parentNode) (document.body || document.documentElement).appendChild(wrap);
    wrap.hidden = false;
    wrap.style.display = "flex";
    setPairError(message || "");
    try { overlayParts.input.focus(); } catch (e) { /* keyboard optional */ }
  }

  function hidePairOverlay() {
    if (!overlay) return;
    overlay.hidden = true;
    overlay.style.display = "none";
    setPairError("");
  }

  function setPairError(message) {
    if (!overlayParts) return;
    overlayParts.error.textContent = message || "";
    overlayParts.error.hidden = !message;
  }

  function clearKeyInput() {
    if (!overlayParts) return;
    overlayParts.input.value = "";
  }

  function submitPairing() {
    if (!overlayParts) return;
    var key = String(overlayParts.input.value || "").trim();
    if (!DEVICE_KEY_RE.test(key)) {
      // Never echo the value back: it may be a mistyped secret.
      setPairError("That does not look like a pairing key. It starts with jdk1. and is one line.");
      return;
    }
    pairWithKey(key);
  }

  /** POST the key for the HttpOnly cookie. The key never leaves this tab
   * except in this one request's header, and it is not stored on disk. */
  function pairWithKey(key) {
    if (!nativeFetch) { setPairError("This browser cannot talk to your PC."); return; }
    setPairError("");
    if (overlayParts) {
      overlayParts.pair.disabled = true;
      overlayParts.pair.textContent = "Pairing…";
    }
    var done = function () {
      if (overlayParts) {
        overlayParts.pair.disabled = false;
        overlayParts.pair.textContent = "Pair this browser";
      }
    };
    nativeFetch(apiUrl("/api/devices/web-session"), {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-Jarvis-Client": CLIENT, "X-Jarvis-Token": key },
    }).then(function (response) {
      return response.json().catch(function () { return {}; })
        .then(function (body) { return { response: response, body: body }; });
    }).then(function (answer) {
      done();
      var response = answer.response;
      var body = answer.body || {};
      if (!response.ok) {
        var reason = body.reason || body.key || "";
        setPairError(wordsForRefusal(reason, body.error));
        if (reason === "device_removed" || reason === "shared_retired") refreshPairingMarker();
        return;
      }
      // Paired: the cookie is set. Keep the key only in this tab's memory for
      // the first requests; clear the visible field at once.
      state.keyInMemory = key;
      state.paired = true;
      state.session = true;
      state.pairs += 1;
      rememberPairedHost();
      clearKeyInput();
      hidePairOverlay();
      pushLink(linkCatchingUp());
      resync({ reason: "paired" });
      startStream();
      paintDeviceLine(body);
    }).catch(function () {
      done();
      setPairError("Could not reach your PC to pair. Check the address, then retry.");
    });
  }

  /** A small line naming the device the PC paired — words come from the PC. */
  function paintDeviceLine(body) {
    var el = document.getElementById("hud-web-device");
    if (!el) {
      el = document.createElement("p");
      el.id = "hud-web-device";
      el.style.cssText = "position:fixed;right:10px;bottom:12px;margin:0;padding:4px 8px;" +
        "background:rgba(8,13,20,.85);border:1px solid #2b3d4d;border-radius:5px;" +
        "color:#8ea1b4;font:11px/1.4 system-ui,sans-serif;z-index:69;";
      (document.body || document.documentElement).appendChild(el);
    }
    var name = String((body && body.device_name) || "").trim();
    var kind = String((body && body.kind) || "").trim();
    if (!name) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = "This browser: " + name + (kind && kind !== "pc" ? " (" + kind + ")" : "");
  }

  function refreshPairingMarker() {
    storeRemove(HOST_KEY);
    state.keyInMemory = "";
    state.paired = false;
    state.hostOk = false;
  }

  /** Clear this browser's session on the PC (keyless route), then ask for a
   * new pairing. Revokes nothing: the PC's Remove is what cuts a device off. */
  function logout() {
    state.keyInMemory = "";
    state.paired = false;
    state.session = false;
    stopStream();
    storeRemove(HOST_KEY);
    pushLink(linkConnecting());
    var done = function () { showPairOverlay("Signed out on this browser. Pair it again to continue."); };
    if (!nativeFetch) { done(); return Promise.resolve(false); }
    return nativeFetch(apiUrl("/api/devices/web-logout"), {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "X-Jarvis-Client": CLIENT },
    }).then(function () { done(); return true; }, function () { done(); return false; });
  }

  /* ---------------------------------------------------------------- *
   * 5. Session, re-sync and the honest link verdict
   * ---------------------------------------------------------------- */

  /** Ask the PC what it already knows: /api/status with the cookie. A 401 or
   * 403 means this browser has no usable session → the pairing sheet. */
  function probeSession() {
    if (!nativeFetch || state.probing) return Promise.resolve(false);
    state.probing = true;
    state.hostOk = hostAllowed();
    if (!state.hostOk) {
      state.probing = false;
      pushLink(linkOffline("this browser was paired to another address"));
      showPairOverlay("This browser was paired to a different address. Pair it again for this one.");
      return Promise.resolve(false);
    }
    return nativeFetch(apiUrl("/api/status"), {
      cache: "no-store",
      credentials: "same-origin",
      headers: authHeaders(),
    }).then(function (response) {
      state.probing = false;
      if (response.status === 401 || response.status === 403) {
        state.paired = false;
        state.session = false;
        pushLink(linkConnecting());
        showPairOverlay();
        return false;
      }
      if (!response.ok) {
        pushLink(linkOffline("the PC answered " + response.status));
        showPairOverlay("The PC is answering, but not with a session. Pair this browser.");
        return false;
      }
      state.paired = true;
      state.session = true;
      hidePairOverlay();
      pushLink(linkCatchingUp());
      startStream();
      resync({ reason: "probe" });
      return true;
    }).catch(function () {
      state.probing = false;
      pushLink(linkOffline("could not reach your PC"));
      showPairOverlay("Could not reach your PC. Check the address and try again.");
      return false;
    });
  }

  /** The two reads the safety rail's honest state needs. Until both succeed
   * the link is "catching up" and the rail holds Approve (Deny stays on). */
  function resync(options) {
    var reason = (options && options.reason) || "";
    if (!nativeFetch) return Promise.resolve(false);
    if (reason !== "paired") pushLink(linkCatchingUp());
    state.catchingUp = true;
    var status = nativeFetch(apiUrl("/api/status"), {
      cache: "no-store", credentials: "same-origin", headers: authHeaders(),
    }).then(function (r) { return r.ok ? r.json().catch(function () { return {}; }) : null; })
      .catch(function () { return null; });
    var pending = nativeFetch(apiUrl("/api/pending"), {
      cache: "no-store", credentials: "same-origin", headers: authHeaders(),
    }).then(function (r) { return r.ok ? r.json().catch(function () { return {}; }) : null; })
      .catch(function () { return null; });
    return Promise.all([status, pending]).then(function (answers) {
      if (!answers[0] || !answers[1]) {
        state.catchingUp = false;
        pushLink(linkOffline("the PC did not answer the link check"));
        scheduleReconnect();
        return false;
      }
      state.catchingUp = false;
      state.session = true;
      pushLink(linkLinked());
      return true;
    });
  }

  function retryConnection() {
    setPairError("");
    if (!state.keyInMemory && !state.session) { probeSession(); return; }
    resync({ reason: "retry" });
    startStream();
  }

  /* ---------------------------------------------------------------- *
   * 6. fetch() wrapper: the page's own calls carry the cookie/token and a
   *    refused session reaches the human as the pairing sheet.
   * ---------------------------------------------------------------- */

  function wrapFetch() {
    if (!nativeFetch || window.fetch.__jarvisBridge) return;
    var wrapped = function (input, init) {
      var isString = typeof input === "string" || (typeof URL !== "undefined" && input instanceof URL);
      if (isString && sameOrigin(String(input)) && sendTokenAllowed()) {
        var headers = {};
        if (init && init.headers) {
          try {
            var h = new Headers(init.headers);
            h.forEach(function (value, name) { headers[name] = value; });
          } catch (e) { headers = {}; }
        }
        if (!Object.prototype.hasOwnProperty.call(headers, "X-Jarvis-Client")) {
          headers["X-Jarvis-Client"] = CLIENT;
        }
        if (!Object.prototype.hasOwnProperty.call(headers, "X-Jarvis-Token")) {
          headers["X-Jarvis-Token"] = state.keyInMemory;
        }
        init = Object.assign({}, init || {}, { headers: headers, credentials: "same-origin" });
        input = String(input);
      }
      var promise = nativeFetch(input, init);
      promise.then(function (response) {
        if (!response || (response.status !== 401 && response.status !== 403)) return response;
        // The pairing exchange reports its own refusal in the sheet; every
        // other refusal means this tab's session is gone.
        try {
          var target = String((response && response.url) || (isString ? input : ""));
          if (target.indexOf("/api/devices/web-session") !== -1) return response;
        } catch (e) { /* fall through to the sheet */ }
        response.clone().json().then(function (body) {
          var reason = (body && (body.reason || body.key)) || "";
          pushLink(linkOffline(wordsForRefusal(reason, "the browser session is not accepted")));
          showPairOverlay(wordsForRefusal(reason));
        }, function () {
          pushLink(linkOffline("the browser session is not accepted"));
          showPairOverlay(wordsForRefusal(""));
        });
        return response;
      }, function () { /* a network error: the stream's link verdict says it */ });
      return promise;
    };
    wrapped.__jarvisBridge = true;
    window.fetch = wrapped;
  }

  /* ---------------------------------------------------------------- *
   * 7. The SSE reader: fetch() + ReadableStream, parsed incrementally
   * ---------------------------------------------------------------- */

  /** Parse whole SSE frames out of the buffered text. Returns the frames and
   * the unfinished tail. Split frames and split multi-byte characters are the
   * caller's job (TextDecoder with stream:true handles the latter). */
  function parseFrames(buffer) {
    var text = String(buffer || "").replace(/\r\n?/g, "\n");
    var frames = [];
    var index;
    while ((index = text.indexOf("\n\n")) !== -1) {
      var block = text.slice(0, index);
      text = text.slice(index + 2);
      if (!block.trim()) continue;
      var type = "message";
      var id = "";
      var data = [];
      var lines = block.split("\n");
      for (var i = 0; i < lines.length; i += 1) {
        var line = lines[i];
        if (!line || line.charAt(0) === ":") continue;
        var colon = line.indexOf(":");
        var field = colon === -1 ? line : line.slice(0, colon);
        var value = colon === -1 ? "" : line.slice(colon + 1);
        if (value.charAt(0) === " ") value = value.slice(1);
        if (field === "event") type = value || "message";
        else if (field === "id") id = value;
        else if (field === "data") data.push(value);
      }
      frames.push({ type: type, data: data.join("\n"), id: id });
    }
    return { frames: frames, rest: text };
  }

  function dispatchFrame(frame) {
    if (!frame) return;
    // A small, bounded record for the suite (and for anyone debugging a stuck
    // browser HUD): the type, and a capped copy of the frame's data. Never a
    // token: the stream carries none.
    state.frames.push({ type: frame.type, id: frame.id, data: String(frame.data).slice(0, 4000) });
    if (state.frames.length > 50) state.frames.shift();
    if (frame.id) state.lastEventId = frame.id;
    var payload = {
      type: frame.type,
      data: frame.data,
      lastEventId: frame.id,
      origin: window.location.origin,
    };
    esInstances.slice().forEach(function (source) {
      source._deliver(payload);
    });
  }

  function scheduleReconnect() {
    if (!state.started) return;
    state.reconnects += 1;
    var delay = Math.min(state.reconnectDelayMax,
      Math.round(state.reconnectDelayMin * Math.pow(1.8, Math.min(state.reconnects, 8))));
    // A small fixed floor keeps a test fast without changing the shape.
    delay = Math.max(state.reconnectDelayMin, delay);
    window.setTimeout(function () { openStream(); }, delay);
  }

  function closeStream() {
    state.connecting = false;
    if (state.reader) {
      try { state.reader.cancel(); } catch (e) { /* already closed */ }
      state.reader = null;
    }
    if (state.stream) {
      try { state.stream.abort ? state.stream.abort() : null; } catch (e) { /* ignore */ }
      state.stream = null;
    }
    esInstances.slice().forEach(function (source) { source._fail(); });
  }

  function openStream() {
    if (!nativeFetch || !state.started) return;
    if (state.connecting || state.reader) return;
    if (!state.session) return;
    state.connecting = true;
    state.connections += 1;
    pushLink(linkCatchingUp());
    var controller = (typeof AbortController !== "undefined") ? new AbortController() : null;
    state.stream = controller;
    var url = apiUrl("/api/events" + (state.lastEventId ? "?since=" + encodeURIComponent(state.lastEventId) : ""));
    nativeFetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      headers: authHeaders({ Accept: "text/event-stream" }),
      signal: controller ? controller.signal : undefined,
    }).then(function (response) {
      if (!response.ok || !response.body || !response.body.getReader) {
        state.connecting = false;
        if (response.status === 401 || response.status === 403) {
          pushLink(linkOffline("the browser session is not accepted"));
          showPairOverlay(wordsForRefusal(""));
          return;
        }
        pushLink(linkOffline("the stream is not available (" + response.status + ")"));
        scheduleReconnect();
        return;
      }
      state.connecting = false;
      state.reconnects = 0;
      esInstances.slice().forEach(function (source) { source._open(); });
      var reader = response.body.getReader();
      state.reader = reader;
      var decoder = (typeof TextDecoder !== "undefined") ? new TextDecoder("utf-8") : null;
      var buffered = "";
      var pump = function () {
        return reader.read().then(function (step) {
          if (step.done) throw new Error("stream ended");
          var chunk = step.value || new Uint8Array(0);
          var text = decoder
            ? decoder.decode(chunk, { stream: true })
            : String.fromCharCode.apply(null, Array.prototype.slice.call(chunk));
          buffered += text;
          var parsed = parseFrames(buffered);
          buffered = parsed.rest;
          parsed.frames.forEach(dispatchFrame);
          return pump();
        });
      };
      return pump();
    }).catch(function () {
      var wasStreaming = Boolean(state.reader);
      state.connecting = false;
      state.reader = null;
      if (wasStreaming) esInstances.slice().forEach(function (source) { source._fail(); });
      pushLink(linkOffline("the live link dropped"));
      scheduleReconnect();
    });
  }

  function startStream() {
    state.started = true;
    openStream();
  }

  function stopStream() {
    state.started = false;
    closeStream();
  }

  /** A spec-shaped EventSource the page's own subscribe() talks to. The page
   *  cannot tell it apart from the browser's, except that it works. */
  function BridgeEventSource(url) {
    this.url = String(url || "");
    this.readyState = 0;                     // CONNECTING
    this.onmessage = null;
    this.onerror = null;
    this.onopen = null;
    this._listeners = { message: [], open: [], error: [] };
    this._open = false;
    esInstances.push(this);
    if (!state.started && state.session) startStream();
  }
  BridgeEventSource.CONNECTING = 0;
  BridgeEventSource.OPEN = 1;
  BridgeEventSource.CLOSED = 2;
  BridgeEventSource.prototype.CONNECTING = 0;
  BridgeEventSource.prototype.OPEN = 1;
  BridgeEventSource.prototype.CLOSED = 2;
  BridgeEventSource.prototype.addEventListener = function (type, fn) {
    if (typeof fn !== "function") return;
    (this._listeners[type] = this._listeners[type] || []).push(fn);
  };
  BridgeEventSource.prototype.removeEventListener = function (type, fn) {
    var list = this._listeners[type] || [];
    var at = list.indexOf(fn);
    if (at !== -1) list.splice(at, 1);
  };
  BridgeEventSource.prototype.close = function () {
    this.readyState = 2;                     // CLOSED
    var at = esInstances.indexOf(this);
    if (at !== -1) esInstances.splice(at, 1);
    if (!esInstances.length) stopStream();
  };
  BridgeEventSource.prototype._open = function () {
    if (this.readyState === 2) return;
    var first = this.readyState !== 1;
    this.readyState = 1;                     // OPEN
    if (first) this._emit("open", { type: "open", target: this });
  };
  BridgeEventSource.prototype._fail = function () {
    if (this.readyState === 2) return;
    this.readyState = 0;                     // CONNECTING (the browser retries too)
    this._emit("error", { type: "error", target: this });
  };
  BridgeEventSource.prototype._deliver = function (payload) {
    this._open();
    if (payload.type === "message") this._emit("message", payload);
    else this._emit(payload.type, payload);
  };
  BridgeEventSource.prototype._emit = function (type, event) {
    if (typeof this["on" + type] === "function") {
      try { this["on" + type].call(this, event); } catch (e) { /* page handler's own error */ }
    }
    var list = (this._listeners[type] || []).slice();
    for (var i = 0; i < list.length; i += 1) {
      try { list[i].call(this, event); } catch (e) { /* page handler's own error */ }
    }
  };

  function replaceEventSource() {
    if (typeof window.EventSource === "function") window.__NativeEventSource = window.EventSource;
    window.EventSource = BridgeEventSource;
  }

  /* ---------------------------------------------------------------- *
   * 8. Launcher: the browser's "Open the Jarvis bar" focuses the chat box
   * ---------------------------------------------------------------- */

  function focusChatInput() {
    var input = document.getElementById("input");
    if (!input) return false;
    try {
      input.focus();
      if (typeof input.setSelectionRange === "function" && typeof input.value === "string") {
        input.setSelectionRange(input.value.length, input.value.length);
      }
      return true;
    } catch (e) { return false; }
  }

  /** In a browser there is no Windows quickbar, so the page's own launcher
   *  becomes "focus the box I am typing in". One control, same words. */
  function bootLauncher() {
    window.__jarvisOpenBar = focusChatInput;
    var pill = document.getElementById("rail-quickbar");
    if (!pill) return;
    var label = pill.querySelector(".qp-label");
    if (label) label.textContent = "Open the Jarvis bar";
    pill.title = "Open the Jarvis bar";
    pill.setAttribute("aria-label", "Open the Jarvis bar");
    var show = function () {
      try {
        // The P0.6 CSS hides this duplicate on the desktop; in a browser it is
        // the only launcher, and inline !important beats a stylesheet !important.
        pill.style.setProperty("display", "flex", "important");
        pill.hidden = false;
        pill.removeAttribute("hidden");
      } catch (e) { /* the launcher stays hidden: the box is still focusable */ }
    };
    show();
    // paintQuickbar() runs at load and again 600 ms later; it would hide a
    // launcher it thinks has no shell. Keep this ONE shown, and nothing else.
    if (typeof MutationObserver !== "undefined") {
      var watcher = new MutationObserver(function () {
        if (pill.hidden || pill.getAttribute("hidden") !== null) show();
      });
      watcher.observe(pill, { attributes: true, attributeFilter: ["hidden", "style"] });
    }
    window.setTimeout(show, 900);
  }

  /* ---------------------------------------------------------------- *
   * 9. Per-device layout: load it, push its shell, follow later saves
   * ---------------------------------------------------------------- */

  function dispatchLayoutShell(doc) {
    if (!doc || typeof doc !== "object") return;
    var preview = {
      shell_template: String(doc.shell_template || "three-column"),
      density: String(doc.density || "comfortable"),
      default_stage_tab: String(doc.default_stage_tab || "talk"),
    };
    try {
      window.__jarvisHudLayout = doc;
      window.dispatchEvent(new CustomEvent("jarvis:hud-layout", { detail: doc }));
      window.dispatchEvent(new CustomEvent("jarvis:hud-shell", { detail: preview }));
    } catch (e) { /* an old engine: the editor still paints */ }
  }

  function bootLayout() {
    // Dynamic import resolves relative to the page: the same folder, served
    // by the same closed-world static route as the page's own modules.
    import("./hud-layout-store.js").then(function (store) {
      if (!store || typeof store.loadLayout !== "function") return null;
      return store.loadLayout().then(function (answer) {
        if (answer && answer.layout) dispatchLayoutShell(answer.layout);
        return answer;
      });
    }).catch(function () { /* no module graph: the page keeps its preview */ });
    window.addEventListener("jarvis:hud-layout-saved", function (event) {
      var doc = event && event.detail;
      if (doc && typeof doc === "object") dispatchLayoutShell(doc);
    });
  }

  /* ---------------------------------------------------------------- *
   * 10. Boot
   * ---------------------------------------------------------------- */

  function boot() {
    wrapFetch();
    replaceEventSource();
    ensureStatusLine();
    bootLauncher();
    dropKeyIfHostChanged();
    pushLink(linkConnecting());
    probeSession();
    bootLayout();
    startStreamIfPossible();
  }

  function startStreamIfPossible() {
    if (state.session) startStream();
  }

  /** The whole of the bridge's public face. The suite drives these; nothing
   * in the page depends on it. */
  window.__jarvisWebBridge = {
    version: VERSION,
    state: state,
    keys: { host: HOST_KEY, layout: LAYOUT_KEY },
    overlayId: OVERLAY_ID,
    pair: pairWithKey,
    pairs: function () { return state.pairs; },
    resync: resync,
    probeSession: probeSession,
    connect: startStream,
    disconnect: stopStream,
    retry: retryConnection,
    logout: function () { return logout(); },
    parseFrames: parseFrames,
    focusChatInput: focusChatInput,
    hostAllowed: hostAllowed,
    sendTokenAllowed: sendTokenAllowed,
    dropKeyIfHostChanged: dropKeyIfHostChanged,
    rememberPairedHost: rememberPairedHost,
    showPairOverlay: showPairOverlay,
    hidePairOverlay: hidePairOverlay,
    configure: function (options) {
      if (options && typeof options.reconnectDelayMin === "number") {
        state.reconnectDelayMin = Math.max(10, options.reconnectDelayMin);
      }
      if (options && typeof options.reconnectDelayMax === "number") {
        state.reconnectDelayMax = Math.max(state.reconnectDelayMin, options.reconnectDelayMax);
      }
    },
    authHeaders: authHeaders,
    note: note,
  };

  /* PWA slice 3b (2026-10-23): the shell worker. Registration is the third
   * line of the page hook; this external file hosts it so the page's
   * inline-script count stays 4. Only a secure context may register a worker,
   * so over the private mesh on plain http this does nothing - and nothing on
   * screen claims otherwise. The worker caches only the manifest and icons,
   * never a backend route. */
  if (window.isSecureContext && "serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
