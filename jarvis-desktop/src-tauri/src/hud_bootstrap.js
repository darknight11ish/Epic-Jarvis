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
   * (jarvis-link.js linkWords).
   *
   * ONE ROW, since 2026-10-21 (field fix). The page's #brand-sub used to be
   * written once at boot from an Ollama probe, so this bootstrap kept its own
   * line under it - and the installed app showed "ONLINE · LOCAL FIRST" above
   * "LINKED · LOCAL FIRST": the same truth twice in two near-identical rows.
   * The page now says both truths in its one brand row. It marks that with
   * `data-hud-link-row` on <html> from its own script (which runs before the
   * DOMContentLoaded paint below), and this pushes the link words to it on
   * every change; the page composes "online · local first · linked" or, when
   * the link is down, the link words alone (without a link nothing about the
   * model is known any more).
   *
   * A line is still drawn by this bootstrap when the page in front of it has
   * no such marker: the live page is copied to the backend separately from
   * the app, so a new shell can meet an older page. Nothing is lost in that
   * pairing; it just has the old two-row look. */
  var lastLink = null;

  /** The link's truth: `words` for the fallback line, `short` for the page's
   *  one row suffix, and a tone both use. `up` is the shell's own verdict;
   *  `null` means no link push has arrived yet, which is "we have not been
   *  told", not "disconnected" - the page must not put it where a model
   *  verdict goes. */
  function linkWords(link) {
    var l = link;
    if (!l) {
      return { up: null, words: "connecting…", short: "", tone: "bad" };
    }
    if (!l.connected) {
      if (!l.error) {
        return { up: false, words: "connecting…", short: "connecting", tone: "bad" };
      }
      var first = String(l.error).trim().split(/[.!?]\s/)[0];
      return { up: false, words: "offline · " + first, short: "no link", tone: "bad" };
    }
    if (l.stale !== false) {
      return { up: true, words: "stale — reconnecting", short: "reconnecting", tone: "warn" };
    }
    return { up: true, words: "linked", short: "linked", tone: "ok" };
  }

  /** Whether the page in front of this bootstrap composes the one status row
   *  itself (jarvis_hud.html sets `data-hud-link-row` from its own script). */
  function pageShowsLinkRow() {
    return document.documentElement.getAttribute("data-hud-link-row") === "1";
  }

  function paintLink() {
    var link = lastLink;
    var root = document.documentElement;
    if (root) {
      // Kept for the stylesheet (hud-link.css): the stale state's colour.
      // Approve and Deny are removed here whatever the link does (section 5).
      if (linkStale) root.classList.add("jarvis-stale");
      else root.classList.remove("jarvis-stale");
    }
    var words = linkWords(link);
    if (pageShowsLinkRow()) {
      // The page owns the one row. A line injected before its script ran (a
      // first link push can arrive before the page finishes parsing) is
      // removed here, so the duplicate cannot win the race.
      var stale = document.getElementById("jarvis-link-line");
      if (stale && stale.parentNode) stale.parentNode.removeChild(stale);
      try {
        window.dispatchEvent(new CustomEvent("jarvis-link-status", { detail: words }));
      } catch (err) {
        console.error("[jarvis] link status failed", err);
      }
      return;
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
    line.textContent = words.words;
    line.setAttribute("data-tone", words.tone);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", paintLink, { once: true });
  }

  var lastPower = "";
  function powerChanged(link) {
    if (!link || typeof link.power !== "string") return;
    var by = typeof link.power_set_by === "string" ? link.power_set_by : "";
    var key = link.power + "|" + by;
    if (key === lastPower) return;
    lastPower = key;
    var detail = { power: link.power, set_by: by };
    window.__jarvisPower = detail;
    window.dispatchEvent(new CustomEvent("jarvis-power", { detail: detail }));
  }

  function linkChanged(link) {
    // Read before the early return below, so a payload that only flips
    // `stale` (not `connected`) still updates the gate in section 4.
    linkStale = !!(link && link.stale);
    lastLink = link || null;
    // The power mode and who set it, for the page's face: a focus session's
    // Quiet shows the focus buddy, a Quiet set by hand shows a sleeping
    // animal. Two words, nothing else from the link.
    powerChanged(link);
    // Every call, not only when `connected` flips: stale comes and goes
    // while connected stays true.
    paintLink();
    // The page's own verdict on /api/status (see the block just below).
    // Every call, for the same reason: the push that arrives right after a
    // reload lands before the page's own read has finished, so it is a later
    // one that finds a fallback left standing by a read that failed.
    recheckBrand(link);
    // And the same verdict, for the page's own standing model line. A change
    // is said at once; a verdict that has not changed is said again on the
    // beat, because the page may not have been listening yet (see tellLane).
    tellLane();
    var up = !!(link && link.connected);
    if (up === linkUp) return;
    linkUp = up;
    instances.slice().forEach(function (es) {
      if (up) es._open();
      else es._fail();
    });
  }

  /* ---------------------------------------------------------------- *
   * The page's own "not connected" verdict, re-checked
   *
   * 2026-10-09, from the owner's running app: the main window read
   * "DEMO · NOT CONNECTED" while the shell held a live, established stream
   * to its own backend. boot() reads /api/status ONCE, through this shell,
   * and writes #brand-sub from that one answer - "demo · not connected"
   * when the read threw, which is what an unreachable backend does
   * (hud_proxy.rs returns Err, so the page's fetch rejects). Nothing in the
   * page reads it again: not its 30 s safety net (apprPoll/initPoll), not
   * the stream's hello. So one failed read at load was that window's verdict
   * for the rest of the session, however healthy the link became. And
   * S.online is left at false by the same read, which is the page's whole
   * idea of "am I talking to Jarvis": Send answers with sampleReply() -
   * "Jarvis is not connected" - and the face is shown asleep.
   *
   * The link is live and checked: Rust sets `connected` from the stream's
   * hello frame alone, and pushes it here on every change. So it, not a
   * boot-time default, is what decides whether that verdict still stands.
   * When it says the backend is answering, the page's own read is made
   * again; if that succeeds, the page was wrong, and it is put back through
   * its own boot path by reloading - the page's own words for this state are
   * "reload this window and your messages will get real answers". Nothing
   * smaller would do: the line, the banner, the face, the lane list and Send
   * all come from that one read, and the page's `S` is a top-level `const`,
   * so no other script can correct it - only the page can re-derive it.
   *
   * Three guards, and no way through them: only while #brand-sub still holds
   * the page's own fallback; never while the owner has unsent words in the
   * box; and at most once per window (`window.name` outlives a reload of the
   * same window), so a backend that answers the stream and not /api/status
   * cannot put this window in a reload loop.
   * ---------------------------------------------------------------- */
  var DEMO_BRAND = /^\s*demo\b/i; // the page's own "demo · not connected"
  var BRAND_RELOADED = "jarvis-hud-demo-reload";
  var brandReading = false;

  function brandIsFallback() {
    var sub = document.getElementById("brand-sub");
    return !!sub && DEMO_BRAND.test(sub.textContent || "");
  }

  function recheckBrand(link) {
    if (brandReading || !link || !link.connected || !brandIsFallback()) return;
    if (window.name === BRAND_RELOADED) return;
    var box = document.getElementById("input");
    if (box && String(box.value || "").trim()) return;
    brandReading = true;
    // Through the same shim, the same proxy and the same route the page's own
    // read took - this is that read, made again, not a second opinion.
    window
      .fetch("/api/status", { cache: "no-store", headers: { "X-Jarvis-Client": "hud" } })
      .then(function (res) {
        return res && res.ok ? res.json() : null;
      })
      .then(function (status) {
        brandReading = false;
        // Only a read that actually landed proves the fallback wrong. Still
        // no answer means the page's verdict is not disproved, so it stands
        // and the live link line under it says what is really happening.
        if (!status || !brandIsFallback()) return;
        try {
          window.name = BRAND_RELOADED;
        } catch (err) {
          /* a window that will not take a name: the landed read above is
             still what stops a second reload, since the page it reloads
             into will read the same answer and never show the fallback */
        }
        window.location.reload();
      })
      .catch(function () {
        brandReading = false;
      });
  }

  /* The page's own beat, so a fallback left standing is still found when the
   * link never changes again - a quiet Jarvis pushes no events at all, and
   * the owner would be left reading the wrong word on an idle desktop.
   * `apprPoll` is a top-level function declaration, so the page's
   * `setInterval` resolves it on the global object and sees this wrapper -
   * the same reason section 4 can wrap `setView`. Installed once the page's
   * own script has run, which is where the function exists at all. */
  function watchPageBeat() {
    if (typeof window.apprPoll !== "function" || window.apprPoll.__jarvisBrandBeat) return;
    var pagePoll = window.apprPoll;
    var beat = function () {
      var result = pagePoll.apply(this, arguments);
      recheckBrand(lastLink);
      tellLane();
      return result;
    };
    beat.__jarvisBrandBeat = true;
    window.apprPoll = beat;
    // And once now: a verdict that changed while the page was loading is
    // older than the page's listener, so the first beat is 30 s too late.
    tellLane();
  }

  /* Is the PC answering, said to the page on every change and on the beat.
   *
   * The page's standing "the local model isn't running" line needs two
   * facts: the PC's own /api/status verdict (which the page reads itself, on
   * this same beat) and this shell's live-stream verdict, which the page
   * cannot work out. That second one is only knowable here, and it is what
   * separates "the PC is answering, its model is not" from "Jarvis is not
   * answering at all" - two different things to tell the owner.
   *
   * The page reads the model field itself and never reloads on this: the
   * shell's own recheckBrand above reloads a page whose read failed, which
   * would throw away whatever is in the box, so this only ever hands over a
   * verdict. One event, no payload beyond it. */
  function tellLane() {
    var up = !!(lastLink && lastLink.connected);
    if (up === laneUp) return;
    laneUp = up;
    try {
      window.dispatchEvent(new CustomEvent("jarvis-lane", {
        detail: { linkUp: up },
      }));
    } catch (err) {
      console.error("[jarvis] lane verdict failed", err);
    }
  }
  var laneUp = null;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watchPageBeat, { once: true });
  } else {
    watchPageBeat();
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
      else if (channel === "bar") barStateChanged(payload);
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
   * 2e. Spoken replies: kept on screen when the answer is private, and
   *     this computer's voices only
   *
   * The page reads every answer aloud with the browser's speech synthesis.
   * Two rules stand in front of it. Neither is a new permission path and
   * neither adds a setting: they are the rules the other windows already
   * run, read off the one fact this page already has - the route its own
   * chat header carried (`HudReply.route`, the same `X-Jarvis-Route` the
   * page draws the lane and the gate from).
   *
   * 1. **An answer that used a sensitive saved fact stays on screen**, and
   *    so does one the PC gated as private (`gate: "private"`). This is the
   *    Jarvis bar's rule for a spoken answer - private-speech.js
   *    `mayReadAloud`, whose FIRST line is the sensitive check, and the
   *    owner's decision of 2026-09-24 - applied to the one surface that
   *    rule was missing. Read the scope honestly: the documented rule was
   *    written for a VOICE answer, and a TYPED question is otherwise
   *    allowed to be read aloud; the HUD is the only window that speaks
   *    typed answers at all, so **on the owner's instruction of
   *    2026-10-16 - "Gate it - keep sensitive answers on screen in the HUD
   *    too" - that exception is removed HERE and nowhere else.** It is a
   *    decision, not an oversight: the bar, the widget and the phone are
   *    unchanged, and the one fixed line below is the bar's own sentence.
   *    A route this window does not have (an older PC, a chat that failed)
   *    gates nothing, which is the same reading the bar makes of a missing
   *    route.
   *
   * 2. **Only this computer's voices.** In WebView2 that list includes
   *    Microsoft's "Online (Natural)" voices, which send the text to
   *    Microsoft to be spoken - so an answer quoting an email or a file
   *    could leave the machine as speech-to-be. Each voice says which kind
   *    it is (`localService`), so the page is shown only the local ones, and
   *    an utterance that would use anything else is given a local voice or
   *    not spoken at all.
   * ---------------------------------------------------------------- */

  /** What the HUD shows instead of reading a private answer aloud: the bar's
   *  own sentence, word for word (private-speech.js `PRIVATE_LINE`), so the
   *  two windows cannot come to two ways of saying one thing. Shown, not
   *  spoken - this is the window the owner is looking at. */
  var KEPT_ON_SCREEN_LINE = "It's on your screen.";

  /** The route of the answer on screen now, from its own chat header (2c,
   *  `shellChat`). Null until one arrives. */
  var answerRoute = null;

  /** Every chat's head frame says this answer's route, or says nothing - in
   *  which case nothing is gated, as the page shows no lane for it either. */
  function noteAnswerRoute(raw) {
    answerRoute = null;
    if (typeof raw !== "string" || !raw) return;
    try {
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") answerRoute = parsed;
    } catch (err) {
      /* not a route: gate nothing */
    }
  }

  /** A whole number from a route field, or null when it is not one. */
  function routeCount(value) {
    var n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  /** Does the answer on screen have to stay on screen? The bar's rule, in
   *  this file's words (private-speech.js `usedSensitiveFact`, plus the
   *  `gate: "private"` refusal in `mayReadAloud`). tests/hud.mjs lifts this
   *  function out and holds it against that module route by route, so the
   *  two cannot drift. */
  function keptOnScreen(route) {
    if (!route || typeof route !== "object") return false;
    if (String(route.gate || "").trim().toLowerCase() === "private") return true;
    var sensitive = routeCount(route.injected_sensitive);
    if (sensitive !== null) return sensitive > 0;
    // A PC that does not say how many were sensitive, with facts in: fail
    // closed, because they may all be sensitive. The bar reads it the same.
    var facts = routeCount(route.injected_facts);
    return facts !== null && facts > 0;
  }

  /** The line under the answer, once per answer. */
  function showKeptOnScreen() {
    var log = document.getElementById("log");
    if (!log) return;
    var answers = log.querySelectorAll(".msg.jarvis");
    var node = answers.length ? answers[answers.length - 1] : log;
    var old = node.querySelector ? node.querySelector(".jarvis-kept") : null;
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var line = document.createElement("p");
    line.className = "jarvis-kept";
    line.setAttribute("role", "status");
    line.textContent = KEPT_ON_SCREEN_LINE;
    node.appendChild(line);
  }

  (function spokenReplies() {
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
        if (keptOnScreen(answerRoute)) {
          // Decision 13, and the owner's instruction of 2026-10-16: this
          // answer used something sensitive he saved, so the room does not
          // hear it. The line says so on screen, in the bar's own words.
          console.info("[jarvis] this answer is kept on screen, so it is not spoken");
          showKeptOnScreen();
          return undefined;
        }
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
   *     (the fixed list in `hud_proxy.rs`'s `allowed_get`: status, graph,
   *     pending, initiative, memory/pending, presets, schedule,
   *     secret-handoff/pending, models, and /retrieve?q=) and refuses every
   *     other path before sending anything;
   *   - POST /api/chat goes to `hud_chat`, streamed back over a channel and
   *     rebuilt into a streaming Response, so the page reads the answer as
   *     it always has. Its AbortController still stops it (`hud_chat_cancel`).
   *   - /api/approve and /api/deny are refused here, stale link or not: a
   *     decision goes through `decide_approval` (section 5), which is the one
   *     command that carries Windows Hello, the stale check and the App-lock
   *     rule. This shim is what stops the page's own POST from becoming a
   *     second, unchecked approval path.
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
  // "Always keep in mind" route (/api/memory/profile) and "Between us"
  // (/api/memory/shared) are refused whole - their POST pins or tags a
  // fact, and this page never reads either list.
  var MEMORY_WRITE =
    /\/api\/memory\/(decide|keep_both|forget|erase|edit|learning|sleep_time|profile|shared)(\?|$)/;
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
          // This answer's route, for the spoken-reply gate (2e): the same
          // header the page reads the lane and the gate from.
          noteAnswerRoute(frame.route);
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
        // The page's own POST is never the path, on any link: a decision goes
        // through `decide_approval` (section 5), which adds the token in Rust,
        // asks Windows Hello when the card needs it, and refuses a stale link
        // and a locked PC. This shim is what keeps the page's own fetch from
        // becoming a second, unchecked approval path.
        return jsonReply(403, {
          ok: false,
          error:
            "an approval is answered through Jarvis's own approval command, not " +
            "by this page - nothing was sent",
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
   * 5. The approval cards: shown AND answered here
   *
   * (apps security audit M2, 2026-09-25; the owner's ask of 2026-10-16:
   * "i should also be able to approve any card from the jarvis hud directly
   * on my desktop and not need the jarvis widget or jarvis bar to do so".)
   *
   * The page draws each waiting approval with its own Approve and Deny. Those
   * buttons are real now, and they are NOT a second permission path: they go
   * through the SAME Tauri command the Jarvis bar and the widget call,
   * `decide_approval`, so every check written for that command applies
   * unchanged - the stale-link refusal and the cut-off refusal (commands.rs),
   * Windows Hello for the card the settings say needs it (lock.rs), and the
   * App-lock rule (a window the lock covers approves nothing; the bar opens
   * and asks there instead). Nothing in this file decides anything, and
   * nothing in this file talks to /api/approve.
   *
   * Three layers, and only the middle one changed:
   *   - the stylesheet (hud-link.css, a file, so neither CSP objects) shows
   *     the buttons;
   *   - this capture-phase listener stops the page's own onclick - which
   *     posts to a relative /api/approve that never reached Jarvis, an
   *     approval path with none of those checks - and sends the decision
   *     through `decide_approval` instead;
   *   - the fetch shim (2c) still refuses /api/approve and /api/deny, so a
   *     later copy of the page that brings its own buttons back still cannot
   *     post one behind the command's back.
   *
   * A stale link is not second-guessed here: the command refuses it and the
   * card shows the command's own sentence, which says more than a button that
   * quietly stops working.
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

  /* What the command answered when it refused, on the card itself. Rust's
   * sentence is the honest one - it names Windows Hello, the stale link or App
   * lock - so it is shown as it came, the same way the bar's own hint carries
   * it. Never a control: there is nothing to press in it. */
  function sayOnCard(card, text) {
    var why = card.querySelector(".why");
    if (!why) {
      why = document.createElement("p");
      why.className = "why";
      var btns = card.querySelector(".btns");
      if (btns && btns.parentNode) btns.parentNode.insertBefore(why, btns.nextSibling);
      else card.appendChild(why);
    }
    why.textContent = String(text);
  }

  /* One decision, sent the one way: the command the bar uses. `id` is the
   * card's own id, from the queue this page read - the command re-reads no
   * queue of its own, so the id must be the one on screen. */
  function answerApproval(id, approved, card) {
    card.classList.add("settled");
    var buttons = card.querySelectorAll("button");
    buttons.forEach(function (b) { b.disabled = true; });
    shellInvoke("decide_approval", { id: id, approved: approved }).then(
      function () {
        // The queue is the record, so the card goes when the server says it
        // has: asking again now is what makes that land on this beat.
        setTimeout(function () { card.remove(); apprPoll(); }, 400);
      },
      function (err) {
        var why = String((err && err.message) || err);
        card.classList.remove("settled");
        buttons.forEach(function (b) { b.disabled = false; });
        sayOnCard(card, why);
        // "Already decided" (the server's 409, or a timeout) means the card is
        // not waiting any more; anything else leaves it standing so the owner
        // can read what happened and decide again.
        if (/already|409/i.test(why)) {
          setTimeout(function () { card.remove(); apprPoll(); }, 1200);
        }
      }
    );
  }

  /* ---------------------------------------------------------------- *
   * A card that REPLACES what is on the PC takes TWO presses - review
   * ruling 8.2 of FOR-GEMINI-COMPREHENSIVE-REVIEW-2026-10-20-LATE.
   *
   * WHY IT LIVES HERE AS WELL AS IN THE PAGE. The page (jarvis_hud.html)
   * draws "REPLACES CURRENT DATA" and its own two-press, but inside the
   * desktop HUD the page's onclick NEVER RUNS: this capture listener stops it
   * on every click and sends the decision through `decide_approval`. So a
   * single click on a restore in the HUD window would decide it - the exact
   * surface the owner's incident came from - and the page's rule could not
   * save it. The rule is therefore implemented on the path that really owns
   * the button, keyed by the card's id, and the page's copy stays for the
   * browser case (where no bootstrap is injected).
   *
   * The set of state-replacing cards is READ FROM THE PC, not guessed here:
   * `hud_get /api/pending` is one of the reads the page is already allowed,
   * and each row carries `replaces` (jarvis_gate.pending()). That also means
   * an older live page without the heading still gets the guard.
   *
   * FAIL SAFE, NEVER ONE CLICK ON DOUBT. The field has three states, and only
   * an EXPLICIT `replaces: false` is ordinary: `true` replaces data, and an
   * ABSENT field or a read that cannot confirm the row (a missing row, an
   * older PC during a partial deploy, a failed read) means the PC never said
   * "ordinary", so the second press is required with honest words. Treating
   * an unknown as "ordinary" is how this guard would quietly re-open during
   * exactly the deploy window it exists for.
   * ---------------------------------------------------------------- */
  var HUD_REPLACE_ARM_MS = 10000;

  /* The client-side FLOOR for the actions whose card replaces data, the same
   * set as the page's and the phone's (the owner extended the guard on
   * 2026-10-21 to the other irreversible data changers). The PC's `replaces`
   * field can ADD an action; this list can never SUBTRACT one - an explicit
   * `false` on a listed action still takes the second press, and an absent
   * field on a listed action does too. */
  var HUD_REPLACE_ACTIONS = [
    "restore_backup", "register_approval_key", "memory_forget_range",
    "delete_file", "delete_joplin_note", "delete_logseq_page",
    "edit_joplin_note", "edit_logseq_page", "modify_own_code",
    "app_merge_change",
  ];

  /* The pure rule, kept free of the DOM so a suite can drive it (see
   * jarvis-desktop/tests/hud-replace-confirm.mjs and the Playwright case in
   * jarvis-desktop/tests/hud.mjs): given a card id and the PC's answer about
   * whether it replaces data, answer "send", "arm-replace" or "arm-unknown".
   * `replaces` is true / false / null-undefined (unknown). An arm is for ONE
   * id and expires; an EXPLICITLY ordinary card is always "send" at once. */
  function replacePressGuard(opts) {
    opts = opts || {};
    var now = typeof opts.now === "function" ? opts.now : function () { return Date.now(); };
    var armMs = typeof opts.armMs === "number" ? opts.armMs : HUD_REPLACE_ARM_MS;
    var armedId = "";
    var armedAt = 0;
    function isArmed(id) {
      return !!armedId && armedId === String(id || "") && (now() - armedAt) <= armMs;
    }
    return {
      isArmed: isArmed,
      /* Forget the arm for this id whatever the clock says - the expiry timer
       * calls this unconditionally, so a timer that fires a millisecond late
       * cannot leave the button saying "Confirm replace". */
      clearIf: function (id) {
        if (String(id || "") !== armedId) return;
        armedId = "";
        armedAt = 0;
      },
      clear: function () { armedId = ""; armedAt = 0; },
      decide: function (id, replaces) {
        id = String(id || "");
        if (isArmed(id)) {
          armedId = "";
          armedAt = 0;
          return "send";
        }
        if (replaces === false) return "send";
        armedId = id;
        armedAt = now();
        return replaces === true ? "arm-replace" : "arm-unknown";
      },
    };
  }

  var replacePress = replacePressGuard();
  var replaceArmTimer = null;
  /* The card whose label/warning is showing, so arming another card clears it
   * (the stale label was its own fail-open: a "Confirm replace" button on the
   * wrong card looks like an ordinary one press). */
  var replaceArmCard = null;
  var replaceArmId = "";
  /* Ids whose /api/pending read is in flight: a second click while it is out
   * must be ignored, or one first press could queue two reads and two arms. */
  var replaceArmBusy = {};

  function restoreReplaceCard(card) {
    if (!card) return;
    var yes = card.querySelector("button.yes");
    if (yes) yes.textContent = "Approve";
    var why = card.querySelector(".why");
    if (why && /REPLACES what is on your PC|could not check what this will replace/
        .test(String(why.textContent || ""))) {
      why.textContent = "";
    }
  }

  function disarmReplaceCard() {
    if (replaceArmTimer !== null) {
      clearTimeout(replaceArmTimer);
      replaceArmTimer = null;
    }
    if (replaceArmCard) restoreReplaceCard(replaceArmCard);
    replaceArmCard = null;
    replaceArmId = "";
  }

  function armReplaceCard(card, id, verdict, row) {
    // Arming a DIFFERENT card first clears whatever the last one was showing,
    // so no card can keep a "Confirm replace" label for an arm that is gone.
    disarmReplaceCard();
    // Review ruling 8.1: the PC's own category and honest words when the row
    // carries them; the generic sentence stays for an older PC that marks the
    // card but sends no words.
    var heading = row && row.replaces_heading
      ? String(row.replaces_heading) : "REPLACES CURRENT DATA";
    var note = row && row.replaces_note ? String(row.replaces_note) : "";
    var words = verdict === "arm-replace"
      ? heading + (note ? ". " + note : " This REPLACES what is on your PC.")
        + " Press Approve once more to do it."
      : "I could not check what this will replace. Press Approve once more if "
        + "you want it.";
    sayOnCard(card, words);
    var yes = card.querySelector("button.yes");
    if (yes) yes.textContent = "Confirm replace";
    replaceArmCard = card;
    replaceArmId = id;
    replaceArmTimer = setTimeout(function () {
      // UNCONDITIONAL for this id: an expiry firing a millisecond late must
      // still take the arm and its label away, or the next press would send.
      replaceArmTimer = null;
      if (replaceArmId !== id) return;      // a different card is armed now
      replacePress.clearIf(id);
      restoreReplaceCard(card);
      replaceArmCard = null;
      replaceArmId = "";
    }, HUD_REPLACE_ARM_MS);
  }

  /* The row this card is for, from the queue this page is allowed to read.
   * A decision is never guessed from a card's words: only the PC's own
   * `replaces` field answers whether it replaces data. A row that is not in
   * the list (or a read that fails) returns null = UNKNOWN, which the rule
   * treats as "require the second press". */
  function pendingRowFor(id) {
    if (!shellGet) return Promise.reject(new Error("no shell"));
    return shellGet("/api/pending").then(function (response) {
      return response.json();
    }).then(function (doc) {
      var rows = (doc && doc.pending) || [];
      for (var i = 0; i < rows.length; i++) {
        if (String(rows[i] && rows[i].id) === id) return rows[i];
      }
      return null;
    });
  }

  document.addEventListener(
    "click",
    function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      var button = target.closest("#approvals .appr .btns button");
      if (!button) return;
      // The page's own handler first: it must not run at all. The decision is
      // the command's to send, never a fetch from this page.
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      var card = button.closest(".appr");
      var id = card && card.dataset ? String(card.dataset.id || "") : "";
      if (!card || !id || button.disabled) return;

      // Deny is never held and never two-step: refusing is the safe direction.
      if (button.className.indexOf("yes") < 0) {
        disarmReplaceCard();
        answerApproval(id, false, card);
        return;
      }

      // A confirming press: send it, and NOTHING was sent before it.
      if (replacePress.isArmed(id)) {
        replacePress.clearIf(id);
        disarmReplaceCard();
        answerApproval(id, true, card);
        return;
      }

      // First press. Read the PC's own answer before deciding what this click
      // means; while the read is in flight, more clicks on the same card are
      // ignored so a double-tap cannot become one send.
      if (replaceArmBusy[id]) return;
      replaceArmBusy[id] = true;
      pendingRowFor(id).then(function (row) {
        replaceArmBusy[id] = false;
        // The PC's field is the authority and can ADD an action; the local
        // list is the fail-safe FLOOR and can only ever ADD a second press.
        // An explicit `false` on a listed action is NOT trusted to remove the
        // guard, and a row missing from a successful read (or a read that
        // failed) stays UNKNOWN, which also takes the second press.
        var replaces = null;
        if (row) {
          var action = String(row.action || "");
          if (row.replaces === true || HUD_REPLACE_ACTIONS.indexOf(action) >= 0) {
            replaces = true;
          } else if (typeof row.replaces === "boolean") {
            replaces = row.replaces;
          }
        }
        var verdict = replacePress.decide(id, replaces);
        if (verdict === "send") {
          answerApproval(id, true, card);
          return;
        }
        armReplaceCard(card, id, verdict, row);   // nothing is sent on this press
      }, function () {
        // The queue could not be read: UNKNOWN, never "ordinary".
        replaceArmBusy[id] = false;
        var verdict = replacePress.decide(id, null);
        if (verdict === "send") answerApproval(id, true, card);
        else armReplaceCard(card, id, verdict, null);
      });
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

  /* ---------------------------------------------------------------- *
   * The HUD's own chat box, with one button beside it
   *
   * The owner's decision of 2026-09-28 ("Chats, after the chat audit") was
   * that the HUD's box should open the Jarvis bar instead, so the PC had
   * one chat box; this hid the box and its Send and put a button in their
   * place. The owner has since reversed that, and the box and its Send are
   * back: they work as the page always made them, and a button beside the
   * box still opens the Jarvis bar ready to type (`hud_open_bar`, voice.rs
   * - it shows a window and sends nothing). The mic button stays: it
   * already opens the bar.
   *
   * AND IT IS ONE BUTTON THAT TOGGLES (the owner's ask of 2026-10-09, with a
   * screenshot): its label follows what is on screen - "Open the Jarvis bar"
   * while the bar is hidden, "Hide the Jarvis bar" while it is shown - and
   * clicking it again hides the bar. The state reaches this page from the
   * shell, never from the click: see `barOnScreen` below.
   *
   * Why the reversal was possible: what was held against the box is now a
   * KNOWN LIMITATION of this window, not a reason to hide it. It is its
   * own conversation, with its own id, and it is filed in History as HUD
   * (jarvis_hud.html sends `device: "hud"` and a conversation id of its
   * own). What it does NOT have, and the Jarvis bar does: no Temporary
   * chat, no New conversation, no "Used in this answer", no crisis panel.
   *
   * Only with the shell (window.__TAURI__): the page served on its own, in
   * a plain browser, has no Jarvis bar to open. There the button is not
   * added and the box was never hidden - the page's own composer, exactly
   * as it ships.
   *
   * AND A SWITCH FOR THE BUTTON (the owner's request of 2026-10-06). Looking
   * at this window, the owner asked for its "Open the Jarvis bar" button to be
   * replaced by a text box he could type into, and then chose: keep the button
   * beside the box, AND add a Settings option controlling whether the button
   * shows in this window at all. That option is "The big HUD window" in
   * Settings (settings.html, src/hud-window.js), ON by default - the state the
   * owner already approved ("The 'Open the Jarvis bar' button stays in that
   * window, beside the box").
   *
   * Cosmetic, so it changes at once and raises no approval card (CLAUDE.md):
   * the box, its Send and the mic button are untouched, and Alt+Space still
   * opens the Jarvis bar. It is per computer, in this window origin's
   * localStorage, like the floating face and "Interrupt Jarvis while it
   * talks".
   *
   * This file cannot `import` src/hud-window.js: it is injected as a plain
   * script, before the page's own. So the key and the reading are spelled a
   * second time here, deliberately, and tests/hud-window.mjs reads this file
   * and fails unless the two agree - value by value, by running this code.
   * ---------------------------------------------------------------- */
  var OPEN_BAR = "Open the Jarvis bar";
  var HIDE_BAR = "Hide the Jarvis bar";

  /* The localStorage key src/hud-window.js exports as OPEN_BAR_KEY. */
  var OPEN_BAR_KEY = "jarvis.hud.openBar";

  /* Whether the Jarvis bar is on screen. NOT guessed and NOT remembered from
   * a click: the shell knows (src-tauri/src/windows.rs `publish_bar_state`)
   * and pushes it on the feed's own "bar" channel, because the bar can also
   * go away by itself - losing focus, its X, an open-a-chat call from another
   * window - and a label that only followed this button's own clicks would go
   * on saying "Hide the Jarvis bar" with nothing on screen to hide.
   *
   * A page that has just loaded has heard nothing yet, and a bar summoned
   * before it loaded is already up, so the shell pushes the state again on
   * every page load (lib.rs, `on_page_load`), exactly as it does the link and
   * the appearance document. Until then: hidden, which is how the bar
   * starts. */
  var barOnScreen = false;

  /* Whether the button shows: ON unless this computer saved it off, and ON
   * when storage cannot be read at all - the reading notifications-prefs.js's
   * loadBool and src/hud-window.js's openBarShown both use ("true"/"on" is on,
   * nothing stored is on, any other stored value is off). */
  function openBarShown() {
    try {
      var saved = window.localStorage.getItem(OPEN_BAR_KEY);
      if (saved === null) return true;
      return saved === "true" || saved === "on";
    } catch (err) {
      return true;
    }
  }

  /* The words the button carries, given what is on screen (the owner's ask of
   * 2026-10-09: it said "Open the Jarvis bar" whether the bar was open or
   * not). The same shape as the wording that was already there - an imperative
   * and the bar's name - and the SAME string is the tooltip and the accessible
   * name, so a screen reader is never told something the sighted label
   * contradicts. `title` is set from this, never from a fixed line. */
  function barLabel(on) {
    return on ? HIDE_BAR : OPEN_BAR;
  }

  function paintOpenBarLabel() {
    var drawn = document.getElementById("hud-open-bar");
    if (!drawn) return;
    var words = barLabel(barOnScreen);
    if (drawn.textContent !== words) drawn.textContent = words;
    if (drawn.title !== words) drawn.title = words;
  }

  /* The shell's push: the bar came on screen, or went. Repaints the label and
   * nothing else - it decides nothing, and it is the only writer of
   * `barOnScreen`. */
  function barStateChanged(visible) {
    barOnScreen = visible === true;
    paintOpenBarLabel();
  }

  function openBarFromHud() {
    var tauri = window.__TAURI__;
    var invoke = tauri && tauri.core && tauri.core.invoke;
    if (typeof invoke !== "function") return;
    /* One button, both directions (the owner's ask of 2026-10-09: clicking it
     * again hides the bar). Which command to send follows the state the shell
     * pushed, because the button is labelled from that same state - so the
     * words on it and what a click does can never disagree. The shell answers
     * a push of its own, which is what flips the label back. */
    var command = barOnScreen ? "hide_quickbar" : "hud_open_bar";
    Promise.resolve()
      .then(function () {
        return invoke(command);
      })
      .catch(function (err) {
        hudMicNote(
          "Could not " +
            (command === "hide_quickbar" ? "hide" : "open") +
            " the Jarvis bar: " +
            String((err && err.message) || err) +
            (command === "hide_quickbar"
              ? ". Press Escape in it, or close it with its X."
              : ". Open it with its shortcut (Alt+Space unless you changed it).")
        );
      });
  }
  window.__jarvisOpenBar = openBarFromHud;

  /* Adds the button, once, before the box. Silent if it is already there. */
  function addOpenBarButton() {
    var input = document.getElementById("input");
    if (!input || !input.parentNode || document.getElementById("hud-open-bar")) return;
    var open = document.createElement("button");
    open.type = "button";
    open.id = "hud-open-bar";
    open.className = "act primary hud-open-bar";
    open.textContent = barLabel(barOnScreen);
    // The page's `.act` is a square icon button; this one carries words.
    // hud-link.css could not be used for it: that file has rules for the
    // mark and the link line only, and no width rule for this id.
    open.style.width = "auto";
    open.style.padding = "0 14px";
    // The tooltip and the accessible name are the visible label, so the two
    // can never contradict each other in a screen reader.
    open.title = barLabel(barOnScreen);
    open.addEventListener("click", openBarFromHud);
    input.parentNode.insertBefore(open, input);
  }

  /* The setting, applied: drawn when it is on, gone when it is off. */
  function applyOpenBar() {
    var drawn = document.getElementById("hud-open-bar");
    if (openBarShown()) {
      if (!drawn) addOpenBarButton();
    } else if (drawn && drawn.parentNode) {
      drawn.parentNode.removeChild(drawn);
    }
  }

  /* The HUD's box and Send stay exactly as the page made them: visible, in
   * the tab order, and working. This only adds the button that opens the
   * Jarvis bar, before the box - when the owner's setting says to. */
  function hudChatBox() {
    var tauri = window.__TAURI__;
    if (!(tauri && tauri.core && typeof tauri.core.invoke === "function")) return;
    var input = document.getElementById("input");
    var send = document.getElementById("send");
    if (!input || !send) return;
    applyOpenBar();
    // A change made in Settings while this window is open. This computer's
    // localStorage is shared by every Jarvis window on this origin, and a
    // write in one of them fires `storage` in the others - so the button
    // appears or goes at once rather than at the next launch. Where a browser
    // does not deliver that event, the window obeys the setting the next time
    // it loads.
    window.addEventListener("storage", function (event) {
      if (event && event.key && event.key !== OPEN_BAR_KEY) return;
      applyOpenBar();
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hudChatBox, { once: true });
  } else {
    hudChatBox();
  }

  /* ---------------------------------------------------------------- *
   * The HUD's settings gear
   *
   * THE OWNER'S DECISION (2026-10-10, question 2 of
   * docs/BARS-AND-SETTINGS-AUDIT-2026-10-10.md): the big HUD window gets a
   * settings gear too. The audit had left it off - this window's capability
   * file was the one that said, in so many words, that it holds "no approve,
   * deny, memory-write, recording or settings command" - and the owner chose
   * otherwise, so that sentence has been corrected in
   * capabilities/hud.json rather than left to contradict the code.
   *
   * WHERE IT SITS, AND WHAT IT CALLS. The owner's request of 2026-10-26, in
   * their own words: "move the settings from the top right to the left
   * column". The HUD has no title bar of its own (it is an ordinary decorated
   * window, so the OS draws one); its own controls live on the stage bar at
   * the top of the conversation view, and that is where this gear was put on
   * 2026-10-10 - the top-right row the owner has now asked to move it out of.
   * It goes into the page's own `.rail-toolbar` in the left rail, beside
   * the Presets button (`#rail-presets`): that toolbar is the one rail block
   * no shell hides. (`#rail-tools` was already taken by the RIGHT rail's
   * "Abilities used" card, which hud-edit.js maps - so nothing here reuses
   * it.) The Studio shell the owner runs (split-stage) draws a 60px
   * icon rail and hides `.rail-nav`, `.rail-lanes` and `.rail-systems` by CSS,
   * so the left column is where the two controls can be found together, and
   * in every other shell the toolbar is in the same place. It calls exactly
   * what the Jarvis bar's gear and the widget's gear call - plain_errors.rs's
   * `open_fix_place {place: "settings"}`, navigation only, through the app
   * lock like every other way in - so there is NO new Tauri command and no
   * new Rust code. It keeps the same "Jarvis settings" name for a screen
   * reader as the bar's and the widget's gears, and since 2026-10-27 it draws
   * the PAGE's own stroke gear (24-unit grid, fill none, currentColor,
   * stroke-width 1.8) instead of the bar's filled 16-unit one: the owner
   * asked for it to match the icons of the rail buttons it sits beside ("i
   * want the settings to be in a similar style of icon to the others"). All
   * three still read alike to a screen reader; the HUD's gear now looks like
   * its own rail.
   *
   * WHY IT IS ADDED HERE rather than in the page: jarvis_hud.html is
   * vendored byte-identical from the backend folder, and section 2b below
   * says why that matters (a new copy from the backend must need no
   * re-patching). This script is how the shell adapts the page without
   * forking it: it adds no buttons of its own beyond two - the "Open the
   * Jarvis bar" control beside the chat box, and this gear. The Presets
   * button it now sits beside is the PAGE's, because it only has to
   * dispatch the page's own `jarvis:hud-presets-open` event - no shell
   * command, no grant, nothing a browser-served page cannot do.
   *
   * THE ACL CHANGE THIS NEEDED, deliberately: `open-fix-place` (the set that
   * holds `allow-open-fix-place`) is now granted to this window in
   * capabilities/hud.json. It was the widget that needed it last, for the
   * same reason and with the same argument: a visible control wired to a
   * command the window does not hold fails silently, which is exactly how
   * the widget's offline card stayed dead. tests/bar-chrome.mjs holds both
   * halves.
   * ---------------------------------------------------------------- */
  var GEAR_SAID = "Jarvis settings";

  function settingsFromHud() {
    var tauri = window.__TAURI__;
    var invoke = tauri && tauri.core && tauri.core.invoke;
    if (typeof invoke !== "function") return;
    Promise.resolve()
      .then(function () {
        return invoke("open_fix_place", { place: "settings" });
      })
      .catch(function (err) {
        hudMicNote(
          "Could not open Jarvis settings: " +
            String((err && err.message) || err) +
            ". Open them from the Jarvis tray icon."
        );
      });
  }
  window.__jarvisOpenSettings = settingsFromHud;

  /* Adds the gear, once, into the left rail's own toolbar - beside the
   * page's Presets button (2026-10-26). Silent if the page has no such group
   * (an older or newer copy of the vendored page): the gear is chrome the
   * shell adds to a page it does not fork, never a control the page is made
   * to carry.
   *
   * THE SAME BOX AS THE PRESETS BUTTON (2026-10-27). The owner said "the
   * spacing of the two new buttons is uneven" and "i want the settings to be
   * in a similar style of icon to the others". The gear used to be a `.ghost`
   * sized with 26px inline styles while the Presets button was a plain
   * `.rail-toolbar-btn`, so the two were different heights - and in the Studio
   * rail (split-stage) the page's CSS draws every `.rail-toolbar-btn` as the
   * same 42x38 box, which the ghost was not. It now takes that page class, so
   * padding, border, height and the 14px glyph (16px in the Studio rail) all
   * come from the same rules the Presets button uses; only the flex is
   * overridden, so an icon-only button does not stretch to the labelled
   * button's width. */
  function addSettingsGear() {
    var railToolbar = document.querySelector(".rail-toolbar");
    if (!railToolbar || document.getElementById("hud-settings")) return;
    var gear = document.createElement("button");
    gear.type = "button";
    gear.id = "hud-settings";
    gear.className = "rail-toolbar-btn hud-settings";
    gear.title = GEAR_SAID;
    // `.rail-toolbar-btn` is `flex:1 1 auto` so the labelled Presets button
    // fills the row; this box carries no label, so it keeps its own width and
    // centres its glyph. Everything else - the padding, the border, the height
    // - still comes from the shared class, which is what makes the pair line
    // up (and in the Studio rail's column, where the page sets both to
    // 42x38, the two are the same box exactly).
    gear.style.flex = "0 0 auto";
    gear.style.justifyContent = "center";
    gear.setAttribute("aria-label", GEAR_SAID);
    // The rail's own icon language, copied from the page's #rail-presets
    // glyph: a line drawing on the 24-unit grid, no fill, currentColor,
    // stroke-width 1.8. The Jarvis bar's gear and the widget's gear keep
    // their filled 16-unit one - they are different windows, and the owner
    // asked for THIS one to match the buttons beside it. The name for a
    // screen reader is unchanged, so all three still read alike.
    gear.innerHTML =
      '<svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" focusable="false">' +
      '<circle cx="12" cy="12" r="3" />' +
      '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />' +
      "</svg>";
    gear.addEventListener("click", settingsFromHud);
    // After the page's own Presets button, so the group reads "Presets, then
    // settings" in every shell. Exactly one gear: the id check above is the
    // guard, and the page itself never carries one (bar-chrome.mjs pins that).
    railToolbar.appendChild(gear);
  }

  /* Only with the shell (window.__TAURI__): the page served on its own, in a
   * plain browser, has no Settings window to open and no `open_fix_place` to
   * call - there the gear is not added at all, exactly as the "Open the
   * Jarvis bar" button is not. */
  function hudSettingsGear() {
    var tauri = window.__TAURI__;
    if (!(tauri && tauri.core && typeof tauri.core.invoke === "function")) return;
    addSettingsGear();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hudSettingsGear, { once: true });
  } else {
    hudSettingsGear();
  }
})();

/* ---------------------------------------------------------------------------
 * 7. The saved HUD layout (H1/H2; H3 renders the preset, 2026-10-22)
 * ---------------------------------------------------------------------------
 * ONE truth: the HUD-layout document in the shell's appearance-class settings
 * store (`hud_layout.rs`, the same store the theme uses). Settings and the
 * in-window H2/H3 editor write it; this bootstrap only READS it. The page's own
 * localStorage layout key is retired.
 *
 * H3 (Q5): the preset's own `shell_template`, `density` and `default_stage_tab`
 * are now rendered. This bootstrap puts them on <html>/<body> and announces
 * them as `jarvis:hud-shell`; the page's own script opens the mapped view or
 * tab. The four-into-three LOOKS alias map is gone. The full document is left
 * on `window.__jarvisHudLayout` and announced as `jarvis:hud-layout` for the
 * editor and the Layouts menu.
 *
 * FIRST PAINT: the async store read may finish after the first frame. The same
 * facts are mirrored into localStorage under `jarvis.hud.preview` after every
 * successful read (and by `hud-layout-store.js` after every save); the page's
 * head reads that mirror once, only to paint the right shell before the store
 * answers. It is a view mirror, never the truth.
 * ------------------------------------------------------------------------- */
(function () {
  var tauri = window.__TAURI__;
  var invoke = tauri && tauri.core && tauri.core.invoke;
  if (typeof invoke !== "function") return;

  var PREVIEW_KEY = "jarvis.hud.preview";
  var SHELLS = ["three-column", "split-stage", "center-core",
    "two-column-left", "two-column-right", "single-stage-bento"];
  var DENSITIES = ["comfortable", "compact", "spacious"];
  var TABS = ["talk", "galaxy", "today", "reminders", "memory", "telemetry"];

  function factsOf(layout) {
    if (!layout || typeof layout !== "object") return null;
    return {
      shell_template: SHELLS.indexOf(layout.shell_template) >= 0
        ? layout.shell_template : "three-column",
      density: DENSITIES.indexOf(layout.density) >= 0
        ? layout.density : "comfortable",
      default_stage_tab: TABS.indexOf(layout.default_stage_tab) >= 0
        ? layout.default_stage_tab : "talk",
      base_preset: String(layout.base_preset || "cockpit"),
      name: String(layout.name || "")
    };
  }

  function applyFacts(facts) {
    var root = document.documentElement;
    if (root) {
      root.setAttribute("data-hud-shell", facts.shell_template);
      root.setAttribute("data-hud-density", facts.density);
    }
    if (document.body && document.body.dataset) {
      document.body.dataset.hudShell = facts.shell_template;
      document.body.dataset.hudDensity = facts.density;
    }
  }

  function rememberPreview(facts) {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(PREVIEW_KEY, JSON.stringify({
          shell_template: facts.shell_template,
          density: facts.density,
          default_stage_tab: facts.default_stage_tab
        }));
      }
    } catch (e) {
      /* Private mode / storage full: the store still answers in a moment. */
    }
  }

  function applyLayout(layout) {
    var facts = factsOf(layout);
    if (!facts) return;
    window.__jarvisHudLayout = layout;
    applyFacts(facts);
    rememberPreview(facts);
    try {
      // H3: the page opens the preset's own view/tab from this.
      window.dispatchEvent(new CustomEvent("jarvis:hud-shell", { detail: facts }));
      // H2/H3: the editor and the Layouts menu read the whole document.
      window.dispatchEvent(new CustomEvent("jarvis:hud-layout", { detail: layout }));
    } catch (e) {
      /* An old engine without CustomEvent: the attributes are still set. */
    }
  }

  function applyWhenReady(layout) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () {
        applyLayout(layout);
      }, { once: true });
    } else {
      applyLayout(layout);
    }
  }

  try {
    invoke("get_hud_layout").then(function (answer) {
      if (answer && answer.layout) applyWhenReady(answer.layout);
    }).catch(function () {
      /* No saved layout yet (or no shell store): the page keeps its preview. */
    });
  } catch (e) {
    /* Never let a layout read break the page's own script. */
  }

  /* H2 (2026-10-22): Settings' "Edit HUD in the window" button asks Rust to
   * show this window and emit `jarvis:hud-edit-request`. Rust's emit reaches
   * the page as a Tauri event; the page's editor listens for a DOM event, so
   * forward it once here. A page without an editor simply has no listener. */
  try {
    var listen = tauri && tauri.event && tauri.event.listen;
    if (typeof listen === "function") {
      listen("jarvis:hud-edit-request", function () {
        try {
          window.dispatchEvent(new CustomEvent("jarvis:hud-edit-request"));
        } catch (e) { /* older engine: nothing to tell */ }
      });
    }
  } catch (e) {
    /* An older shell without event.listen: the header button still edits. */
  }
})();