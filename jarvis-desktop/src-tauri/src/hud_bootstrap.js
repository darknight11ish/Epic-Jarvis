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
      // Section 5's stylesheet greys the page's Approve and Deny with this,
      // and the capture listener below refuses the click itself.
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
   * 2c. Approve/deny: route to the real backend, gated on the link
   *
   * jarvis_hud.html's apprDecide() is the one decision path in the file
   * that does not go through the page's own jfetch() helper - it calls
   * bare fetch("/api/approve" | "/api/deny", ...) with a relative URL and
   * no JARVIS.headers(). Two consequences, both confirmed against that
   * exact line rather than assumed:
   *
   *   1. A relative fetch resolves against this webview's own origin,
   *      http://tauri.localhost - not JARVIS.url()'s backend base. Nothing
   *      proxies tauri.localhost to the backend, so today this request
   *      never reaches Jarvis at all on the desktop build, and it carries
   *      no X-Jarvis-Token either: the one unauthenticated call in the
   *      page.
   *   2. Even reaching the backend, nothing here checks whether the
   *      shell's event stream is stale first - the exact gate
   *      decide_approval (commands.rs) enforces for the Quickbar and the
   *      Widget, quoting DESKTOP-BUILD's checklist: "disable approve/deny
   *      while the stream is stale, because answering a queue you cannot
   *      confirm is live is how you approve something twice."
   *
   * Fixed the same way as window.JARVIS and window.EventSource above:
   * intercepted here, not in jarvis_hud.html, so the next vendored drop
   * of that file needs no re-patching. This does not reach into Tauri's
   * IPC - the HUD's CSP and its empty capability grant (see hud.json)
   * both stay exactly as they are; this only stops the page's own fetch
   * from leaving through the wrong door.
   * ---------------------------------------------------------------- */
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  // Memory is decided in the Brain window, and only there: its cards warn
  // about text that reads like a slipped-in instruction, offer "Both are
  // true", say "would replace" only when something really is replaced, and
  // refuse while the link is stale. This page's own copy of those cards had
  // none of that. The page no longer draws them (jarvis_hud.html), and a
  // later copy of the page that brings them back still cannot send one:
  // every memory write from this page is refused here, stale link or not.
  // Reads (/api/memory/pending, /status, /facts) pass untouched.
  var MEMORY_WRITE =
    /\/api\/memory\/(decide|keep_both|forget|edit|learning|sleep_time)(\?|$)/;
  if (realFetch) {
    window.fetch = function (input, init) {
      var path = typeof input === "string" ? input : "";
      // A Request or URL object too, not only a string, for the refusal.
      var target = path || (input ? String(input.url || input) : "");
      if (MEMORY_WRITE.test(target)) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ok: false,
              error:
                "memory is decided in the Brain window's Memory tab, not here - " +
                "nothing was sent",
            }),
            { status: 403, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      if (path === "/api/approve" || path === "/api/deny") {
        if (linkStale) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                ok: false,
                error:
                  "the event stream is stale, so the approval queue cannot " +
                  "be confirmed live - nothing can be answered until it reconnects",
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
        var jarvis = window.JARVIS;
        if (jarvis && typeof jarvis.url === "function") {
          var merged = Object.assign({}, init);
          merged.headers = jarvis.headers(init && init.headers);
          return realFetch(jarvis.url(path), merged);
        }
      }
      // The page's own chat request (jfetch("/api/chat") -> the backend's
      // absolute URL). The answer's id rides in X-Jarvis-Route as
      // `turn_id` (feedback.patch); section 6 puts a right/wrong mark on
      // the answer it belongs to. Read-only: the response is passed back
      // to the page untouched.
      if (/\/api\/chat(\?|$)/.test(path)) {
        return realFetch(input, init).then(function (res) {
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
      return realFetch(input, init);
    };
  }

  /* ---------------------------------------------------------------- *
   * 6. Right or wrong: the mark on one answer (feedback.patch)
   *
   * Under the answer the id belongs to - the next "jarvis" message the page
   * adds to #log - two small buttons. One answer, one mark; pressing the
   * one already on takes it back. Posted straight to the backend the page
   * already talks to (window.JARVIS's own url and headers, token included),
   * because this window has no app commands. A backend without the route
   * answers 404/503 and the buttons remove themselves, quietly. A mark
   * changes no memory; it only counts.
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
      var api = window.JARVIS;
      if (!api || typeof api.url !== "function") return;
      right.disabled = wrong.disabled = true;
      realFetch(api.url("/api/feedback/mark"), {
        method: "POST",
        cache: "no-store",
        headers: api.headers({ "Content-Type": "application/json", "X-Jarvis-Client": "hud" }),
        body: JSON.stringify({ turn_id: turnId, mark: next }),
      })
        .then(function (res) {
          if (res.status === 404 || res.status === 501 || res.status === 503) {
            row.remove();
            return;
          }
          if (res.ok) current = next;
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
   * 5. The approval cards, while the link is stale
   *
   * The fetch intercept above already refuses approve/deny while stale -
   * that is the real block and it stays. But the page then printed "This
   * request is no longer waiting", which was false (it was still waiting),
   * and removed the card, which stayed gone until the next poll. And the
   * buttons looked live before the click. So: a stylesheet (a file, not an
   * inline style, so neither CSP has anything to say about it) greys the
   * buttons and says why under them while `jarvis-stale` is on the root,
   * and a capture-phase listener stops the click before the page's own
   * handler ever runs. It never decides anything; it only stops a click.
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
      if (!linkStale) return;
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