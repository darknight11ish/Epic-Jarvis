/* Injected into the HUD webview before any of the page's own scripts run.
 *
 * `jarvis_hud.html` is vendored byte-identical from the backend folder, so it
 * is the browser's page first and the desktop's second. This script is how the
 * desktop shell adapts it without forking it. It does two things.
 *
 * ------------------------------------------------------------------------
 * 1. Configure JARVIS before the page's first fetch
 * ------------------------------------------------------------------------
 * The page's shim reads its base and token from localStorage at the moment it
 * is defined, and inside Tauri the origin is http://tauri.localhost, so an
 * unconfigured page resolves /api/status against the wrong host and every call
 * fails. Configuring it from `on_page_load` is too late — by then the page has
 * already fired.
 *
 * Seeding localStorage would be early enough, and is exactly what DESKTOP-BUILD
 * §3.1 step 4 forbids: the shell holds the token and injects it at load, and
 * "a copy in this page's localStorage would be a second, staler source of the
 * token that outlives the shell's own storage".
 *
 * This comment used to say "the OS keystore". It is not in a keystore. It is
 * a bare JSON string in tauri-plugin-store's file under %APPDATA%, which the
 * uninstaller leaves behind. Saying otherwise made the storage look stronger
 * than it is to the next person reading this, which is the only audience a
 * comment has. Moving it to DPAPI is worth doing; claiming it already moved
 * was not.
 *
 * So instead: intercept the assignment. The page does
 *
 *     const JARVIS = window.JARVIS = (() => { ... })();
 *
 * and an accessor installed on `window.JARVIS` beforehand runs the instant that
 * object exists — before the next statement in the page, let alone the next
 * script tag. The value of an assignment expression is its right-hand side
 * regardless of any setter, so the page's own `const JARVIS` still binds to the
 * same object; both spellings keep working.
 *
 * ------------------------------------------------------------------------
 * 2. Replace EventSource with a shim fed by the shell's one stream
 * ------------------------------------------------------------------------
 * Rust holds a single GET /api/events open and fans every frame out to all
 * three windows. If the HUD page also opened one, the desktop would be back to
 * two subscriptions, two resume points and two opinions about whether an
 * approval is still open.
 *
 * The shim is a faithful EventSource: named events go to listeners registered
 * for that name and `onmessage` only ever sees type "message", exactly as the
 * WHATWG spec says. It deliberately does NOT "fix" the page's handler — that
 * is the page's business — it only removes the second socket.
 *
 * A side effect worth naming: the page's `streamUrl()` puts the token in the
 * query string, because EventSource cannot set a header. Under the shim no
 * request is made at all, so on the desktop the token never reaches a URL.
 */
(function () {
  "use strict";

  var BASE = __JARVIS_BASE__;
  var TOKEN = __JARVIS_TOKEN__;

  /* ---------------------------------------------------------------- *
   * 1. JARVIS configuration
   * ---------------------------------------------------------------- */

  function configure(api) {
    if (!api || typeof api.set !== "function") return;
    try {
      // Clear anything an earlier browser session against this same origin
      // left behind, so a stale token cannot shadow the real one.
      if (typeof api.forget === "function") api.forget();
      // The third argument is persist=false: the shell re-injects on every
      // load and the keystore is the single source.
      api.set(BASE, TOKEN, false);
      console.info("[jarvis] shell configured the HUD for " + (BASE || "same origin"));
    } catch (err) {
      console.error("[jarvis] shell configuration failed", err);
    }
  }

  var held;
  try {
    Object.defineProperty(window, "JARVIS", {
      configurable: true,
      enumerable: true,
      get: function () {
        return held;
      },
      set: function (api) {
        held = api;
        configure(api);
      },
    });
  } catch (err) {
    // A future page that defines JARVIS non-configurably would land here. The
    // Rust side still runs its on_page_load fallback, which is late but not
    // nothing.
    console.error("[jarvis] could not intercept window.JARVIS", err);
  }

  /* ---------------------------------------------------------------- *
   * 2. EventSource shim
   * ---------------------------------------------------------------- */

  var instances = [];

  function ShellEventSource(url, config) {
    this.url = String(url);
    this.withCredentials = !!(config && config.withCredentials);
    this.readyState = ShellEventSource.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this._listeners = Object.create(null);
    instances.push(this);
    var self = this;
    // A real EventSource never fires open synchronously from its constructor.
    // Neither does this: the page assigns its handlers on the next statements.
    setTimeout(function () {
      if (self.readyState === ShellEventSource.CLOSED) return;
      if (linkUp) self._open();
    }, 0);
  }

  ShellEventSource.CONNECTING = 0;
  ShellEventSource.OPEN = 1;
  ShellEventSource.CLOSED = 2;
  ShellEventSource.prototype.CONNECTING = 0;
  ShellEventSource.prototype.OPEN = 1;
  ShellEventSource.prototype.CLOSED = 2;

  ShellEventSource.prototype.addEventListener = function (type, fn) {
    if (typeof fn !== "function") return;
    var list = this._listeners[type] || (this._listeners[type] = []);
    if (list.indexOf(fn) === -1) list.push(fn);
  };

  ShellEventSource.prototype.removeEventListener = function (type, fn) {
    var list = this._listeners[type];
    if (!list) return;
    var at = list.indexOf(fn);
    if (at !== -1) list.splice(at, 1);
  };

  ShellEventSource.prototype.close = function () {
    this.readyState = ShellEventSource.CLOSED;
    var at = instances.indexOf(this);
    if (at !== -1) instances.splice(at, 1);
  };

  ShellEventSource.prototype.dispatchEvent = function (event) {
    if (this.readyState === ShellEventSource.CLOSED) return true;
    var list = this._listeners[event.type];
    if (list) {
      list.slice().forEach(function (fn) {
        try {
          fn.call(this, event);
        } catch (err) {
          console.error("[jarvis] EventSource listener threw", err);
        }
      }, this);
    }
    // Per the spec, `onmessage` is the handler for type "message" alone. A
    // named event (`event: approval`) reaches addEventListener and nothing
    // else. Reproduced rather than smoothed over: the page must behave the
    // same here as it does in a browser.
    var inline =
      event.type === "message"
        ? this.onmessage
        : event.type === "open"
          ? this.onopen
          : event.type === "error"
            ? this.onerror
            : null;
    if (typeof inline === "function") {
      try {
        inline.call(this, event);
      } catch (err) {
        console.error("[jarvis] EventSource handler threw", err);
      }
    }
    return true;
  };

  ShellEventSource.prototype._open = function () {
    if (this.readyState === ShellEventSource.OPEN) return;
    this.readyState = ShellEventSource.OPEN;
    this.dispatchEvent({ type: "open", target: this });
  };

  ShellEventSource.prototype._fail = function () {
    if (this.readyState === ShellEventSource.CLOSED) return;
    // A real EventSource drops back to CONNECTING while it retries, and the
    // shell is retrying on this one's behalf.
    this.readyState = ShellEventSource.CONNECTING;
    this.dispatchEvent({ type: "error", target: this });
  };

  var linkUp = false;

  function deliver(payload) {
    if (!payload || !payload.kind) return;
    var data;
    try {
      data = JSON.stringify(payload.data === undefined ? {} : payload.data);
    } catch (err) {
      data = "{}";
    }
    var lastEventId = payload.id === null || payload.id === undefined ? "" : String(payload.id);
    instances.slice().forEach(function (es) {
      if (es.readyState !== ShellEventSource.OPEN) es._open();
      es.dispatchEvent({
        type: payload.kind,
        data: data,
        lastEventId: lastEventId,
        origin: BASE || window.location.origin,
        target: es,
      });
    });
  }

  function linkChanged(link) {
    var up = !!(link && link.connected);
    if (up === linkUp) return;
    linkUp = up;
    instances.slice().forEach(function (es) {
      if (up) es._open();
      else es._fail();
    });
  }

  /* The feed.
   *
   * Rust pushes into this by evaluating a call to it in this webview, rather
   * than the page subscribing over Tauri's IPC — because it cannot. This page
   * carries its own Content-Security-Policy meta tag, and its `connect-src`
   * lists the backend's loopback origins and nothing else. Tauri's IPC on
   * Windows is a fetch to http://ipc.localhost, so every `invoke` and every
   * `listen` from this page is blocked by that policy before it leaves the
   * webview. An eval from the host is not a fetch and is not subject to it.
   *
   * (That is worth fixing in the page itself — adding `ipc: http://ipc.localhost`
   * to its connect-src costs nothing in a browser, where neither is reachable,
   * and it is what any future button in this page that needs the shell will
   * require. Until then, nothing here depends on IPC.)
   */
  window.__jarvisFeed = function (channel, payload) {
    try {
      if (channel === "event") deliver(payload);
      else if (channel === "link") linkChanged(payload);
    } catch (err) {
      console.error("[jarvis] feed failed", err);
    }
  };

  window.EventSource = ShellEventSource;
  console.info("[jarvis] EventSource is served by the shell's single stream");

  /* ---------------------------------------------------------------- *
   * 2b. The Web Speech recogniser, refused
   *
   * The vendored page takes `window.SpeechRecognition ||
   * window.webkitSpeechRecognition` and wires it to the mic button and to
   * the space bar. Its own section header says what it is: "browser speech
   * in, browser speech out. Swap these two for the local pipeline (whisper
   * + Kokoro) later." The swap never happened.
   *
   * In Chromium that API is not implemented in page JS. The engine opens
   * the microphone and POSTs the audio to a vendor speech endpoint FROM
   * THE BROWSER PROCESS. `connect-src` does not govern it, so the app CSP
   * — which is otherwise doing real work here, and is what refuses the
   * page's Google Fonts link below — cannot see it and cannot stop it.
   * Raw microphone audio would leave the machine, which is the one thing
   * this product says it never does.
   *
   * The Android client already refuses the same API for the same reason,
   * and argues it well (net/VoiceModels.kt: "Android's own recogniser is
   * also a network service unless on-device recognition happens to be
   * installed, so the privacy boundary would move without anyone being
   * told"). This applies that decision to the desktop.
   *
   * Undefining it is enough and is deliberately gentle: the page does
   * `if (SR) { ... }`, `start()` opens with `if (!rec || listening)
   * return`, and the status line already renders "unsupported" when SR is
   * absent. So the mic button goes inert and says so, rather than
   * throwing. Done here rather than by editing jarvis_hud.html so the next
   * copy of that file from the backend needs no re-patching — the same
   * reasoning as the fonts below.
   *
   * When the local pipeline lands, this block is what to delete.
   * ---------------------------------------------------------------- */
  try {
    delete window.SpeechRecognition;
    delete window.webkitSpeechRecognition;
  } catch (err) {
    /* non-configurable on some builds; the assignment below still wins */
  }
  window.SpeechRecognition = undefined;
  window.webkitSpeechRecognition = undefined;
  console.info(
    "[jarvis] Web Speech recognition is disabled: it uploads microphone " +
      "audio from outside the CSP. Dictation waits on the local pipeline."
  );

  /* ---------------------------------------------------------------- *
   * 3. Fonts, served locally
   *
   * The vendored page links Chakra Petch and IBM Plex from
   * fonts.googleapis.com. In a browser served by the backend that is the
   * page author's call; in a packaged desktop app it means every window
   * open leaks the user's IP to Google, and the typography falls back to
   * system fonts with no network.
   *
   * The app CSP no longer lists either Google origin, so the page's own
   * <link> is refused before a request leaves the webview — no fork of
   * jarvis_hud.html required, and nothing to re-apply when the next copy
   * of it arrives. This supplies the replacement: the same families,
   * bundled under the SIL OFL (see fonts/OFL.txt), from disk.
   * ---------------------------------------------------------------- */
  function localFonts() {
    if (document.getElementById("jarvis-local-fonts")) return;
    var link = document.createElement("link");
    link.id = "jarvis-local-fonts";
    link.rel = "stylesheet";
    link.href = "fonts/fonts.css";
    (document.head || document.documentElement).appendChild(link);
  }
  if (document.head) localFonts();
  else document.addEventListener("DOMContentLoaded", localFonts, { once: true });
})();