/* Injected into the HUD webview before any of the page's own scripts run.
 *
 * `jarvis_hud.html` is vendored byte-identical from the backend folder, so it
 * is the browser's page first and the desktop's second. This script is how the
 * desktop shell adapts it without forking it.
 *
 * THE PAGE HOLDS NO PAIRING TOKEN (apps security audit M2, 2026-09-25). It
 * used to be given one, here and on every page load, so any script running in
 * the page could read it and call the whole API - `POST /api/approve`
 * included, past Windows Hello and the stale check. Now section 1 sets the
 * page's token to empty, and section 2c sends every request the page makes to
 * Jarvis through Rust (src-tauri/src/hud_proxy.rs), which adds the token
 * itself and allows only the page's own reads, its chat, and the right/wrong
 * mark. Approve and Deny are not answered in this window at all (section 5).
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
 * Where the shell holds the token, precisely: a token typed into Settings is
 * in Windows Credential Manager, which is DPAPI-encrypted to the Windows user
 * (token_store.rs). A token nobody typed is the backend's own, which the
 * backend keeps in Credential Manager too (token-store.patch). It is never in
 * this page: the base is configured here, and the token is set to empty.
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
 * request is made at all - and the page has no token to put there anyway.
 */
(function () {
  "use strict";

  var BASE = __JARVIS_BASE__;

  /* ---------------------------------------------------------------- *
   * 1. JARVIS configuration
   * ---------------------------------------------------------------- */

  function configure(api) {
    if (!api || typeof api.set !== "function") return;
    try {
      // Clear anything an earlier browser session against this same origin
      // left behind, so a stale token cannot shadow the real one.
      if (typeof api.forget === "function") api.forget();
      // An EMPTY token, on purpose (apps security audit M2): the page's
      // requests go through Rust, which adds the token (section 2c). The
      // third argument is persist=false, so nothing is left in localStorage.
      api.set(BASE, "", false);
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
  // Matches LinkState::default() on the Rust side: stale until the first
  // hello says otherwise, so approve/deny is refused for the first instant
  // of every launch rather than enabled against a queue nobody has read.
  var linkStale = true;

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

  /* What the link is doing, in the words every other window uses
   * (jarvis-link.js linkWords). The page's own #brand-sub is written once,
   * at boot, from an Ollama probe, and then never changes - so the HUD said
   * "online" for as long as it was open, whatever the stream did. The page
   * is vendored and not ours to edit, and its boot() may write #brand-sub
   * after this runs, so the link gets its own line directly under it rather
   * than fighting over that one: the Ollama hint stays, and this is live. */
  var lastLink = null;

  function linkLine(link) {
    var l = link || {};
    if (!l.connected) {
      if (!l.error) return "connecting…";
      var first = String(l.error).trim().split(/[.!?]\s/)[0];
      return "offline · " + first;
    }
    if (l.stale !== false) return "stale — reconnecting";
    return "linked · local first";
  }

  function paintLink() {
    var link = lastLink;
    var root = document.documentElement;
    if (root) {
      // Kept for the stylesheet (hud-link.css): the link line's colour.
      // Approve and Deny are removed here whatever the link does (section 5).
      if (linkStale) root.classList.add("jarvis-stale");
      else root.classList.remove("jarvis-stale");
    }
    var sub = document.getElementById("brand-sub");
    if (!sub || !sub.parentNode) return;
    var line = document.getElementById("jarvis-link-line");
    if (!line) {
      line = document.createElement("div");
      line.id = "jarvis-link-line";
      line.className = "sub";
      line.setAttribute("role", "status");
      sub.parentNode.insertBefore(line, sub.nextSibling);
    }
    line.textContent = linkLine(link);
    line.setAttribute("data-tone", !link || !link.connected ? "bad" : linkStale ? "warn" : "ok");
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paintLink, { once: true });
  }

  function linkChanged(link) {
    // Read before the early return below, so a payload that only flips
    // `stale` (not `connected`) still updates the gate in section 4.
    linkStale = !!(link && link.stale);
    lastLink = link || null;
    // Every call, not only when `connected` flips: stale comes and goes
    // while connected stays true.
    paintLink();
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
   * Rust pushes into this by evaluating a call to it in this webview. This
   * comment used to say that was because Tauri's IPC cannot work from this
   * page, whose own Content-Security-Policy does not list
   * http://ipc.localhost. That was wrong (apps security audit M2): when that
   * fetch is refused, Tauri falls back to `window.ipc.postMessage`, which no
   * CSP governs, so `invoke` works here - the mic button (2d) and every
   * request in 2c use it. What limits this page is capabilities/hud.json.
   * The feed stays: it hands the shell's one event stream to the
   * EventSource shim above without a second subscription.
   */
  window.__jarvisFeed = function (channel, payload) {
    try {
      if (channel === "event") deliver(payload);
      else if (channel === "link") linkChanged(payload);
      else if (channel === "appearance") appearanceChanged(payload);
    } catch (err) {
      console.error("[jarvis] feed failed", err);
    }
  };

  /* The owner's appearance document - which face, which colours - for the
   * page's reactor, which is the kit face (faces.html in display mode) in
   * an iframe. Pushed for the same reason as everything else in this feed:
   * this window has no app commands (capabilities/hud.json), so it cannot
   * ask for it. Cosmetic only; it approves nothing and carries no secret.
   *
   * Kept on `window` as well as announced, because the push can land before
   * the page's own script has subscribed, and a page that missed it would
   * wear the default face until the owner next saved. */
  function appearanceChanged(doc) {
    if (!doc || typeof doc !== "object") return;
    window.__jarvisAppearance = doc;
    window.dispatchEvent(new CustomEvent("jarvis-appearance", { detail: doc }));
  }

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
   * The local pipeline has landed - on the quickbar, not here (voice.rs:
   * the microphone is recorded by the app and sent only to the Jarvis
   * server on this machine). Section 2d below points this page's mic
   * button at it. This block stays: the page must never reach for the
   * browser recogniser again, whatever the next copy of it does.
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
      "audio from outside the CSP. The mic button opens the quickbar's " +
      "local push-to-talk instead."
  );

  /* ---------------------------------------------------------------- *
   * 2d. The mic button: the quickbar's push-to-talk, not a dead button
   *
   * With the recogniser gone (2b) the page's mic button did nothing at
   * all, while its tooltip still said "Hold to talk". The real, local
   * push-to-talk lives in the quickbar (voice.rs): the app records the
   * microphone itself and sends the clip only to the Jarvis server on
   * this machine, which checks it is the owner's voice before turning it
   * into words.
   *
   * This page is not given the recording commands (capabilities/hud.json).
   * It gets one command, `summon_push_to_talk`, which shows the quickbar
   * with its mic button focused. It records nothing: the owner then holds
   * that mic (or Space/Enter on it) to talk, the same as always.
   *
   * A capture-phase listener takes the click before the page's own
   * handler, which would only call the refused recogniser. The page's
   * Space-bar shortcut is left alone: summoning a window on a key that is
   * still held down would land the rest of the press in the quickbar.
   * ---------------------------------------------------------------- */
  var MIC_TITLE =
    "Talk to Jarvis: opens the quickbar - hold its mic button to speak. " +
    "Your voice stays on this computer.";

  function hudMicNote(text) {
    if (typeof window.addMessage === "function") {
      try {
        window.addMessage("system", text);
        return;
      } catch (err) {
        /* fall through to the console */
      }
    }
    console.warn("[jarvis] " + text);
  }

  function summonPushToTalk() {
    var tauri = window.__TAURI__;
    var invoke = tauri && tauri.core && tauri.core.invoke;
    if (typeof invoke !== "function") {
      hudMicNote(
        "The mic works in the quickbar. Open it with its shortcut " +
          "(Alt+Space unless you changed it) and hold the mic button."
      );
      return Promise.resolve(false);
    }
    return Promise.resolve()
      .then(function () {
        return invoke("summon_push_to_talk");
      })
      .then(function () {
        return true;
      })
      .catch(function (err) {
        hudMicNote(
          "Could not open the quickbar's push-to-talk: " +
            String((err && err.message) || err) +
            ". Open the quickbar with its shortcut and hold the mic button."
        );
        return false;
      });
  }
  window.__jarvisSummonPushToTalk = summonPushToTalk;

  function wireHudMic() {
    var mic = document.getElementById("mic");
    if (mic) {
      mic.title = MIC_TITLE;
      mic.setAttribute("aria-label", MIC_TITLE);
      mic.setAttribute("aria-pressed", "false");
      mic.dataset.jarvisMic = "quickbar";
    }
    // The readout under "listening" said "unsupported", which was true of
    // the browser recogniser and is not true of Jarvis.
    var readout = document.getElementById("r-stt");
    if (readout) readout.textContent = "in quickbar";
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireHudMic, { once: true });
  } else {
    wireHudMic();
  }

  /* ---------------------------------------------------------------- *
   * 2e. Spoken replies: this computer's voices only
   *
   * The page reads every answer aloud with the browser's speech
   * synthesis, picking a British voice by name and falling back to ANY
   * en-GB voice. In WebView2 that list includes Microsoft's "Online
   * (Natural)" voices, which send the text to Microsoft to be spoken - so
   * an answer quoting an email or a file could leave the machine as
   * speech-to-be. Each voice says which kind it is (`localService`), so
   * the page is shown only the local ones, and an utterance that would
   * use anything else is given a local voice or not spoken at all.
   * ---------------------------------------------------------------- */
  (function localVoicesOnly() {
    var synth = window.speechSynthesis;
    if (!synth || typeof synth.getVoices !== "function" || typeof synth.speak !== "function") return;
    var allVoices = synth.getVoices.bind(synth);
    var realSpeak = synth.speak.bind(synth);
    function localVoices() {
      return (allVoices() || []).filter(function (v) {
        return v && v.localService === true;
      });
    }
    try {
      synth.getVoices = localVoices;
      synth.speak = function (utterance) {
        if (!utterance) return undefined;
        if (utterance.voice && utterance.voice.localService !== true) utterance.voice = null;
        if (!utterance.voice) {
          var mine = localVoices();
          var english = mine.filter(function (v) {
            return /^en/i.test(v.lang || "");
          });
          var pick = english[0] || mine[0];
          if (!pick) {
            // No voice on this computer (or none loaded yet): silence, not
            // the browser's choice, which could be an online one.
            console.info("[jarvis] no local voice available, so this reply is not spoken");
            return undefined;
          }
          utterance.voice = pick;
        }
        return realSpeak(utterance);
      };
    } catch (err) {
      console.warn("[jarvis] could not limit speech to local voices", err);
    }
  })();

  document.addEventListener(
    "click",
    function (event) {
      var target = event.target;
      if (!target || !target.closest || !target.closest("#mic")) return;
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      summonPushToTalk();
    },
    true
  );

  /* ---------------------------------------------------------------- *
   * 2c. Every request to Jarvis goes through Rust, which holds the token
   *
   * (apps security audit M2.) The page has no token (section 1), so a
   * request it made itself would be refused. This replaces `window.fetch`
   * for anything under /api/ and hands it to src-tauri/src/hud_proxy.rs:
   *
   *   - a GET goes to `hud_get`, which allows only the page's own reads
   *     (/api/status, /graph, /pending, /initiative, /memory/pending and
   *     /retrieve?q=) and refuses every other path before sending anything;
   *   - POST /api/chat goes to `hud_chat`, streamed back over a channel and
   *     rebuilt into a streaming Response, so the page reads the answer as
   *     it always has. Its AbortController still stops it (`hud_chat_cancel`).
   *   - /api/approve and /api/deny are refused here, stale link or not:
   *     approvals are answered in the Jarvis bar or the widget, through
   *     decide_approval, with Windows Hello and the stale check (section 5).
   *   - memory writes are refused (the Brain decides memory);
   *   - anything else under /api/ is refused.
   *
   * Everything that is not under /api/ (fonts, the stylesheet) is fetched
   * as before. Outside the desktop (no __TAURI__) the page is not changed.
   * ---------------------------------------------------------------- */
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  var tauriCore = window.__TAURI__ && window.__TAURI__.core;
  var shellInvoke =
    tauriCore && typeof tauriCore.invoke === "function" ? tauriCore.invoke.bind(tauriCore) : null;
  var ShellChannel = tauriCore && tauriCore.Channel;
  // Memory is decided in the Brain window, and only there: its cards warn
  // about text that reads like a slipped-in instruction, offer "Both are
  // true", say "would replace" only when something really is replaced, and
  // refuse while the link is stale. This page's own copy of those cards had
  // none of that. The page no longer draws them (jarvis_hud.html), and a
  // later copy of the page that brings them back still cannot send one:
  // every memory write from this page is refused here, stale link or not.
  // Reads (/api/memory/pending, /status, /facts) pass untouched. The
  // "Always keep in mind" route (/api/memory/profile) is refused whole -
  // its POST pins a fact, and this page never reads the list.
  var MEMORY_WRITE =
    /\/api\/memory\/(decide|keep_both|forget|erase|edit|learning|sleep_time|profile)(\?|$)/;
  var APPROVAL = /^\/api\/(approve|deny)(\?|$)/;

  function jsonReply(status, body) {
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: status,
        headers: { "Content-Type": "application/json" },
      })
    );
  }

  /* The /api/... path and query of a request, or null for anything else. */
  function apiPath(target) {
    var url;
    try {
      url = new URL(String(target), window.location.href);
    } catch (err) {
      return null;
    }
    if (url.pathname.indexOf("/api/") !== 0) return null;
    return url.pathname + url.search;
  }

  function abortReason(signal) {
    return signal && signal.reason !== undefined
      ? signal.reason
      : new DOMException("The operation was aborted.", "AbortError");
  }

  function replyHeaders(contentType, route) {
    var headers = new Headers();
    if (contentType) headers.set("Content-Type", contentType);
    if (route) {
      try {
        headers.set("X-Jarvis-Route", route);
      } catch (err) {
        /* not a valid header value: the page shows no route, as before */
      }
    }
    return headers;
  }

  function okStatus(status) {
    return status >= 200 && status <= 599 ? status : 502;
  }

  function shellGet(path) {
    return shellInvoke("hud_get", { path: path }).then(
      function (reply) {
        var status = okStatus(reply && reply.status);
        var empty = status === 204 || status === 205 || status === 304;
        return new Response(empty ? null : String((reply && reply.body) || ""), {
          status: status,
          headers: replyHeaders(reply && reply.contentType, reply && reply.route),
        });
      },
      function (err) {
        // A fetch that could not reach the server rejects with a TypeError.
        throw new TypeError(String((err && err.message) || err));
      }
    );
  }

  function shellChat(init) {
    var body = null;
    try {
      body = JSON.parse(init && typeof init.body === "string" ? init.body : "null");
    } catch (err) {
      body = null;
    }
    var signal = init && init.signal;
    return new Promise(function (resolve, reject) {
      if (signal && signal.aborted) {
        reject(abortReason(signal));
        return;
      }
      var controller = null;
      var stream = new ReadableStream({
        start: function (c) {
          controller = c;
        },
      });
      var encoder = new TextEncoder();
      var headed = false;
      var over = false;
      function finish() {
        if (over) return;
        over = true;
        if (signal) signal.removeEventListener("abort", onAbort);
      }
      function fail(err) {
        if (over) return;
        finish();
        if (!headed) reject(err);
        else {
          try {
            controller.error(err);
          } catch (e) {
            /* already closed */
          }
        }
      }
      function onAbort() {
        shellInvoke("hud_chat_cancel").catch(function () {});
        fail(abortReason(signal));
      }
      if (signal) signal.addEventListener("abort", onAbort, { once: true });
      var channel = new ShellChannel();
      channel.onmessage = function (raw) {
        if (over) return;
        var frame = null;
        try {
          frame = JSON.parse(raw);
        } catch (err) {
          frame = null;
        }
        if (!frame) return;
        if (frame.kind === "head" && !headed) {
          headed = true;
          resolve(
            new Response(stream, {
              status: okStatus(frame.status),
              headers: replyHeaders(frame.contentType, frame.route),
            })
          );
        } else if (frame.kind === "data" && headed) {
          controller.enqueue(encoder.encode(String(frame.text || "")));
        } else if (frame.kind === "end" && headed) {
          finish();
          controller.close();
        }
      };
      shellInvoke("hud_chat", { body: body, onEvent: channel }).then(
        function () {
          if (over) return;
          if (!headed) {
            fail(new TypeError("the Jarvis server sent no answer"));
            return;
          }
          // The reply can arrive before the channel's last frames: give
          // them a moment, then close whatever has come.
          setTimeout(function () {
            if (over) return;
            finish();
            controller.close();
          }, 1500);
        },
        function (err) {
          fail(new TypeError(String((err && err.message) || err)));
        }
      );
    });
  }

  if (realFetch && shellInvoke && ShellChannel) {
    window.fetch = function (input, init) {
      var isRequest = typeof Request !== "undefined" && input instanceof Request;
      var target = isRequest ? input.url : input;
      var path = apiPath(target);
      if (path === null) return realFetch(input, init);
      var method = String((init && init.method) || (isRequest && input.method) || "GET").toUpperCase();
      if (MEMORY_WRITE.test(path)) {
        return jsonReply(403, {
          ok: false,
          error:
            "memory is decided in the Brain window's Memory tab, not here - " +
            "nothing was sent",
        });
      }
      if (APPROVAL.test(path)) {
        return jsonReply(403, {
          ok: false,
          error:
            "approvals are answered in the Jarvis bar or the widget, not in this " +
            "window - nothing was sent",
        });
      }
      if (method === "GET" && !isRequest) return shellGet(path);
      if (method === "POST" && path === "/api/chat" && !isRequest) {
        return shellChat(init).then(function (res) {
          // The answer's id rides in X-Jarvis-Route as `turn_id`
          // (feedback.patch); section 6 puts a right/wrong mark on the
          // answer it belongs to. Read-only: the response goes to the page
          // untouched.
          try {
            var raw = res.headers.get("X-Jarvis-Route");
            var route = raw ? JSON.parse(raw) : null;
            var id = route && route.turn_id;
            if (typeof id === "string" && /^[0-9a-f]{32}$/.test(id)) expectAnswer(id);
          } catch (err) {
            /* no id: no mark */
          }
          return res;
        });
      }
      return jsonReply(403, {
        ok: false,
        error: "the HUD window cannot send that - nothing was sent",
      });
    };
  }

  /* ---------------------------------------------------------------- *
   * 6. Right or wrong: the mark on one answer (feedback.patch)
   *
   * Under the answer the id belongs to - the next "jarvis" message the page
   * adds to #log - two small buttons. One answer, one mark; pressing the
   * one already on takes it back. Sent through Rust's `mark_answer` - the same
   * command the Jarvis bar uses, which checks the id and the mark and adds
   * the token (the page has none). A backend without the route answers
   * 404/503, `mark_answer` says `available: false`, and the buttons remove
   * themselves, quietly. A mark changes no memory; it only counts.
   * ---------------------------------------------------------------- */
  var awaitingTurn = null;

  function expectAnswer(turnId) {
    awaitingTurn = turnId;
    var log = document.getElementById("log");
    if (!log || typeof MutationObserver === "undefined") return;
    var watch = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var added = records[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var node = added[j];
          if (node.nodeType === 1 && node.classList.contains("msg") && node.classList.contains("jarvis")) {
            watch.disconnect();
            if (awaitingTurn === turnId) attachMark(node, turnId);
            return;
          }
        }
      }
    });
    watch.observe(log, { childList: true });
    // An answer that never arrives (an error) must not leave this watching.
    setTimeout(function () { watch.disconnect(); }, 120000);
  }

  function attachMark(msg, turnId) {
    var row = document.createElement("div");
    row.className = "jarvis-mark";
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "Was this answer right?");
    var q = document.createElement("span");
    q.textContent = "Was this answer right?";
    var right = document.createElement("button");
    right.type = "button";
    right.textContent = "Right";
    var wrong = document.createElement("button");
    wrong.type = "button";
    wrong.textContent = "Wrong";
    var current = "none";
    function paint() {
      right.setAttribute("aria-pressed", String(current === "right"));
      wrong.setAttribute("aria-pressed", String(current === "wrong"));
    }
    function send(mark) {
      var next = current === mark ? "none" : mark;
      if (!shellInvoke) return;
      right.disabled = wrong.disabled = true;
      shellInvoke("mark_answer", { turnId: turnId, mark: next })
        .then(function (reply) {
          if (reply && reply.available === false) {
            row.remove();
            return;
          }
          current = next;
        })
        .catch(function () { /* leave it as it was */ })
        .then(function () {
          right.disabled = wrong.disabled = false;
          paint();
        });
    }
    right.addEventListener("click", function () { send("right"); });
    wrong.addEventListener("click", function () { send("wrong"); });
    paint();
    row.appendChild(q);
    row.appendChild(right);
    row.appendChild(wrong);
    msg.appendChild(row);
    // Only on an answer that FINISHED. A streamed answer's message is added
    // empty and filled as it arrives, so the mark used to appear at once -
    // and stayed on an answer that was then cut off and labelled
    // "[interrupted]", inviting a right/wrong verdict on half a reply. The
    // page sets data-state="done" when the answer ends properly and
    // "interrupted" when it does not; until then the row is hidden.
    function settle() {
      var st = msg.dataset ? msg.dataset.state : "";
      if (st === "done") {
        row.hidden = false;
        return true;
      }
      if (st === "interrupted") {
        row.remove();
        return true;
      }
      row.hidden = true;
      return false;
    }
    if (!settle() && typeof MutationObserver !== "undefined") {
      var until = new MutationObserver(function () {
        if (settle()) until.disconnect();
      });
      until.observe(msg, { attributes: true, attributeFilter: ["data-state"] });
    }
  }

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

  /* ---------------------------------------------------------------- *
   * 5. The approval cards: shown here, answered elsewhere
   *
   * (apps security audit M2, 2026-09-25.) The page draws each waiting
   * approval with its own Approve and Deny. On the desktop they are
   * removed: approvals are answered in the Jarvis bar or the widget, where
   * `decide_approval` asks Windows Hello and refuses on a stale link. The
   * page's own buttons posted to a relative /api/approve that never reached
   * Jarvis, and a later "fix" pointing them at the backend would have been
   * an approval path with neither check.
   *
   * Three layers, none of which decides anything: the stylesheet
   * (hud-link.css, a file, so neither CSP objects) hides the buttons and
   * says where to answer; a capture-phase listener stops any click on them
   * before the page's own handler runs; and the fetch shim (2c) refuses
   * /api/approve and /api/deny. The card itself - what is being asked,
   * and how long is left - stays, so the owner sees it here too.
   * ---------------------------------------------------------------- */
  function staleSheet() {
    if (document.getElementById("jarvis-hud-link-css")) return;
    var link = document.createElement("link");
    link.id = "jarvis-hud-link-css";
    link.rel = "stylesheet";
    link.href = "hud-link.css";
    (document.head || document.documentElement).appendChild(link);
  }
  if (document.head) staleSheet();
  else document.addEventListener("DOMContentLoaded", staleSheet, { once: true });

  document.addEventListener(
    "click",
    function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      if (!target.closest("#approvals .appr .btns button")) return;
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    },
    true
  );

  /* ---------------------------------------------------------------- *
   * 4. Relabel the "Brain" tab to "Galaxy"
   *
   * The separate Brain window (brain.html) is the one place "Brain" is
   * meant to mean anything in this app. Inside the HUD, a second tab also
   * labelled "Brain" opens something else entirely - confirmed against
   * the markup, not guessed: it is a live constellation of memory nodes
   * (canvas id="galaxy", a ".brain-search" bar, "reset view" / "pause
   * spin" controls). The page's own code already calls this visual the
   * galaxy; only the tab label and the stage title still said "Brain".
   * Having both surfaces answer to the same name is what made "open the
   * Brain" ambiguous.
   *
   * Relabelled here, not in jarvis_hud.html, for the same reason as
   * everything else in this file: the next vendored drop needs no
   * re-patching. `data-view="brain"` and `id="brain"` are left exactly as
   * they are - the page's own script keys off those strings, and nothing
   * here touches them; only the two visible text labels change.
   * ---------------------------------------------------------------- */
  function relabelBrainTab() {
    var btn = document.querySelector('button.mode[data-view="brain"]');
    if (btn) {
      for (var i = 0; i < btn.childNodes.length; i++) {
        var n = btn.childNodes[i];
        if (n.nodeType === 3 && n.textContent.trim() === "Brain") {
          n.textContent = n.textContent.replace("Brain", "Galaxy");
        }
      }
    }
    // setView(), defined by the page's own script (which has already run
    // by the time DOMContentLoaded fires), sets #stage-title to "Brain
    // map" on every switch into this tab - not just the first, so the
    // title is wrapped rather than patched once.
    if (typeof window.setView === "function") {
      var original = window.setView;
      window.setView = function (v) {
        var result = original(v);
        if (v === "brain") {
          var title = document.getElementById("stage-title");
          if (title && title.textContent === "Brain map") title.textContent = "Galaxy";
        }
        return result;
      };
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", relabelBrainTab, { once: true });
  } else {
    relabelBrainTab();
  }
})();