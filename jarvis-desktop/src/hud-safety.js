/**
 * hud-safety.js — H4 of the editable HUD (2026-10-22): the safety rail.
 *
 * THE ONE STRIP NO LAYOUT CAN HIDE. App lock / hidden memory lists, evidence
 * that something Jarvis read tried to rush the owner (queue-scoped, honest),
 * and the catching-up (stale) link state live in `#hud-safety` — an element
 * owned by the page, OUTSIDE every `[data-hud-region]` and every HUD card. It
 * is not in `CARD_REGISTRY`, has no layout document entry, and no preset,
 * import, hand-edited settings file or edit-mode action can hide or move it.
 *
 * WHERE EVERY FACT COMES FROM (no new command, no new grant, no network):
 * - the link truth is the shell's own `jarvis-link-status` push (the same one
 *   the page's one status row already reads);
 * - App lock / "Hide memory lists" is the already-granted `get_lock_flags`
 *   (`hud-link`'s set; two booleans, no token, no words);
 * - the rush/outside-text evidence is the pending queue the page already
 *   polls: rows whose `raised` object carries the quote/source. It is
 *   QUEUE-SCOPED on purpose — this banner says "on the card that is waiting",
 *   never "the latch is armed" from a card alone.
 * - the two PERSISTENT session latches are the PC's own `/api/status` fields
 *   `taint_latched` and `rush_latched` (A4, 2026-10-23; read-only, no new
 *   route — `/api/status` was already on the HUD's fixed allowlist). The page
 *   hands them in from reads it already made (boot and the page's own 30 s
 *   beat), so this module opens no socket of its own. `true` says the latch is
 *   armed, `false` says it is not, and `null` means "the PC has not said" —
 *   never "not latched" — so no chip is drawn then. Reading them clears
 *   nothing, and the strip has no control that could clear either latch.
 *
 * HONEST LIMITS (also in the PR and docs):
 * - the actual App-lock "locked" state hides the HUD window (Rust), so there
 *   is deliberately no in-page locked overlay: it could never be seen;
 * - `get_lock_flags` is polled (boot, window focus, visibility, a slow 20 s
 *   beat) because no push event exists yet; the chip can lag by that beat;
 * - the strip has no controls in v1: Approve/Deny stay on the card, and while
 *   the link is stale Approve is disabled (with the words explaining why) and
 *   **Deny stays enabled** — matching Rust's own rule (`stale_answer_refusal`
 *   holds only an approved decision).
 *
 * @module hud-safety
 */

/** The rail's element id (the page's markup owns it). */
export const SAFETY_ID = "hud-safety";

/** App lock on. Same words the design/reviewer approved; pinned by tests. */
export const LOCK_WORDS =
  "App lock is on. This window hides when you step away, and approvals wait until you're back.";

/** App lock off, "Hide memory lists and chat history" on. */
export const HIDDEN_WORDS = "Memory lists are hidden until you unlock.";

/** Link catching up: Approve waits, Deny keeps working (Rust's own rule). */
export const STALE_WORDS =
  "Catching up with your PC… Approvals wait for the link; Deny still works.";

/** Link down: the Rust sentence is appended after this lead. */
export const OFFLINE_LEAD = "No link to Jarvis on your PC: ";

/** The queue-scoped rush evidence's lead and tail (never overclaims the latch). */
export const TAINT_LEAD = "Something Jarvis read tried to rush you on the card that is waiting";
export const TAINT_TAIL = "Take your time — this can never be hidden.";

/** A4 (2026-10-23): the persistent local-only session latch is armed. Plain
 *  words only - the owner never reads the word "taint" on a screen. */
export const LATCH_LOCAL_WORDS = "This session is staying on your PC.";

/** A4: the persistent rush latch is armed - every approval asks for one more
 *  look until it clears. Says what changes, not what the mechanism is called. */
export const LATCH_RUSH_WORDS =
  "Something Jarvis read tried to rush you recently. Approvals ask for one more look until it clears.";

/** The visual "you cannot hide this" line, shown only in H2's edit mode. */
export const FIXED_LABEL = "Always visible — no layout can hide this";

/** How often the lock flags are re-read when nothing else happens (ms). */
export const LOCK_BEAT_MS = 20000;

/** `raised` in every shape the backend has used: object, true, JSON text. */
export function raisedOf(value) {
  if (value === null || value === undefined || value === false || value === 0) return null;
  if (typeof value === "string") {
    const t = value.trim();
    if (!t || /^(false|null|0)$/i.test(t)) return null;
    try {
      const o = JSON.parse(t);
      if (o && typeof o === "object" && !Array.isArray(o)) return o;
    } catch (err) {}
    return {};
  }
  if (Array.isArray(value)) return value.length ? {} : null;
  if (typeof value === "object") return value;
  return value ? {} : null;
}

/** The lock chip's words, or "" when neither lock fact is on. */
export function lockWords(flags) {
  if (!flags || typeof flags !== "object") return "";
  if (flags.appLock === true) return LOCK_WORDS;
  if (flags.privateAnswers === true) return HIDDEN_WORDS;
  return "";
}

/** The link chip: null when linked (the one status row already says it). */
export function linkWords(link) {
  if (!link || typeof link !== "object") return null;
  if (link.up === true) {
    const stale = link.tone === "warn" || link.short === "reconnecting";
    return stale ? { tone: "warn", words: STALE_WORDS } : null;
  }
  if (link.up === false) {
    const words = String(link.words || "").trim().replace(/^offline\s*·\s*/i, "");
    const rust = words || "the link is down";
    const tail = /[.!?]$/.test(rust) ? "" : ".";
    return { tone: "bad", words: `${OFFLINE_LEAD}${rust}${tail}` };
  }
  return null; // no verdict yet: the page's own row says "connecting…"
}

/** The queue-scoped rush evidence, or null. Always plain text (DOM uses textContent). */
export function taintWords(rows) {
  if (!Array.isArray(rows)) return null;
  for (const row of rows) {
    const raised = raisedOf(row && row.raised);
    if (!raised) continue;
    const quote = String(raised.quote || "").trim();
    const source = String(raised.source || "").trim();
    const text = String(raised.text || "").trim();
    let words = TAINT_LEAD;
    if (quote) words += `: \u201c${quote}\u201d`;
    else if (text) words += `: ${text}`;
    if (source) words += ` (from ${source})`;
    return { tone: "warn", words: `${words}. ${TAINT_TAIL}` };
  }
  return null;
}

/**
 * A4 (2026-10-23): the persistent-session chip's words, or null.
 *
 * `latch` is the page's `{taint, rush}` object from `/api/status` - each one
 * `true`, `false`, or `null` ("the PC has not said"). ONLY `true` draws a
 * chip: `null` must never read as "not latched", and false has nothing to say.
 * Both true are shown together, because they are two different facts (this
 * session stays local AND approvals are asking more carefully).
 */
export function latchWords(latch) {
  if (!latch || typeof latch !== "object") return null;
  const parts = [];
  if (latch.taint === true) parts.push(LATCH_LOCAL_WORDS);
  if (latch.rush === true) parts.push(LATCH_RUSH_WORDS);
  if (!parts.length) return null;
  return { tone: "warn", words: parts.join(" ") };
}

/**
 * The rail's whole state, as chips in markup order. Pure: the mount paints it,
 * tests read it. `link` is the shell push's detail, `lock` the two booleans,
 * `rows` the pending queue rows, `latch` A4's two persistent booleans.
 */
export function safetyChips({ link = null, lock = null, rows = [], latch = null } = {}) {
  const chips = [];
  const lockText = lockWords(lock);
  if (lockText) chips.push({ chip: "lock", role: "status", tone: "warn", words: lockText });
  const session = latchWords(latch);
  if (session) chips.push({ chip: "latch", role: "status", tone: session.tone, words: session.words });
  const taint = taintWords(rows);
  if (taint) chips.push({ chip: "taint", role: "alert", tone: taint.tone, words: taint.words });
  const linkState = linkWords(link);
  if (linkState) chips.push({ chip: "link", role: "status", tone: linkState.tone, words: linkState.words });
  return chips;
}

/**
 * Whether Approve must wait (link stale or down) — the UI half of Rust's
 * `stale_answer_refusal(approved, stale) = approved && stale`. Deny is never
 * held: stopping only makes Jarvis do less.
 */
export function approveHeld(link) {
  // H4-LOW: until the shell has said the link is live, a click cannot be
  // honoured - hold Approve (Deny still works). The bootstrap starts stale,
  // so this only covers the first instant before its first push.
  if (!link || typeof link !== "object" || link.up !== true) return true;
  return link.tone === "warn" || link.short === "reconnecting";
}

/**
 * Apply the Approve-waits / Deny-enabled rule to ONE rendered card. Pure DOM
 * (no network): `card` is the `.appr` element, `descId` the id of the words the
 * Approve button points at. A card whose Approve is disabled for another
 * reason (cut off before it reached the card) stays disabled: that is marked
 * with `data-cutoff` by the page.
 */
export function applyApprovalControls(card, { held = false, descId = "", words = "" } = {}) {
  if (!card || typeof card.querySelector !== "function") return null;
  const yes = card.querySelector(".yes");
  const no = card.querySelector(".no");
  if (!yes || !no) return null;
  const cutoff = yes.dataset && yes.dataset.cutoff === "1";
  // H4-LOW: a card may carry its own note (the replace flow's title and an
  // aria-describedby from elsewhere). Remember the page's values before we
  // touch them and put them back when the link recovers, so this rail never
  // strips a protected card's own words.
  if (held) {
    if (yes.dataset && yes.dataset.safetySet !== "1") {
      yes.dataset.safetyTitle = yes.title || "";
      yes.dataset.safetyDesc = yes.getAttribute("aria-describedby") || "";
      yes.dataset.safetySet = "1";
    }
    yes.disabled = true;
    yes.title = words || STALE_WORDS;
    if (descId) yes.setAttribute("aria-describedby", descId);
    no.disabled = false; // Deny is never held: stopping only makes Jarvis do less.
  } else if (yes.dataset && yes.dataset.safetySet === "1") {
    if (!cutoff) yes.disabled = false;
    yes.title = yes.dataset.safetyTitle || "";
    if (yes.dataset.safetyDesc) yes.setAttribute("aria-describedby", yes.dataset.safetyDesc);
    else yes.removeAttribute("aria-describedby");
    delete yes.dataset.safetyTitle;
    delete yes.dataset.safetyDesc;
    delete yes.dataset.safetySet;
  }
  return { approveDisabled: yes.disabled, denyEnabled: !no.disabled };
}

/** The element, or null (a backend-served page without the markup). */
function el(id) {
  return typeof document === "undefined" ? null : document.getElementById(id);
}

/**
 * Mount the rail. Returns its small API; the page's inline script calls
 * `setLink` from the shell push, `setPending`/`syncApprovals` after it paints
 * the approval queue. Nothing here reads a saved setting or writes anything.
 */
export function mountSafetyRail() {
  const strip = el(SAFETY_ID);
  if (!strip) return Promise.resolve(null);
  const chips = {
    lock: el("hud-safety-lock"),
    latch: el("hud-safety-latch"),
    taint: el("hud-safety-taint"),
    link: el("hud-safety-link"),
  };
  const fixed = el("hud-safety-fixed");
  if (fixed) fixed.textContent = FIXED_LABEL;

  const state = {
    link: window.__hudLinkStatus && typeof window.__hudLinkStatus === "object"
      ? window.__hudLinkStatus : { up: null },
    lock: null,
    // A4-4: the page publishes the two persistent latches from the /api/status
    // read it already makes, BEFORE this module mounts (the fetch is not
    // awaited by the inline script), so the last one is seeded here and every
    // later read arrives as the `jarvis-latch-status` event.
    latch: window.__hudLatchFacts && typeof window.__hudLatchFacts === "object"
      ? window.__hudLatchFacts : null,
    // H4-4: rows the page painted before this module mounted (seeded once,
    // then kept in step by setPending on every paint).
    rows: Array.isArray(window.__hudSafetyPending) ? window.__hudSafetyPending.slice() : [],
  };

  function render() {
    const list = safetyChips(state);
    const byChip = new Map(list.map((chip) => [chip.chip, chip]));
    const editing = document.body.getAttribute("data-hud-edit") === "on";
    // H4-3: in edit mode the strip stays on screen with its "always visible"
    // line even while every chip is silent; outside edit mode it hides when
    // there is nothing true to say (linked is the one row's job).
    strip.hidden = list.length === 0 && !editing;
    for (const [name, node] of Object.entries(chips)) {
      if (!node) continue;
      const chip = byChip.get(name);
      if (!chip) {
        node.hidden = true;
        if (node.textContent) node.textContent = "";
        continue;
      }
      // textContent on purpose: a quote from outside text is shown, never run.
      // Only a CHANGE re-announces (H4-LOW: a live region must not repeat the
      // same sentence on every poll).
      if (node.textContent !== chip.words) node.textContent = chip.words;
      node.dataset.tone = chip.tone;
      node.setAttribute("role", chip.role);
      node.hidden = false;
    }
  }

  function setLink(link) {
    state.link = link && typeof link === "object" ? link : { up: null };
    render();
    syncApprovals(document);
  }

  function setLock(flags) {
    state.lock = flags && typeof flags === "object" ? flags : null;
    render();
  }

  function setPending(rows) {
    state.rows = Array.isArray(rows) ? rows : [];
    render();
  }

  function setLatch(facts) {
    state.latch = facts && typeof facts === "object" ? facts : null;
    render();
  }

  function syncApprovals(root) {
    const held = approveHeld(state.link);
    const words = held ? STALE_WORDS : "";
    const cards = (root && root.querySelectorAll) ? root.querySelectorAll("#approvals .appr") : [];
    for (const card of cards) applyApprovalControls(card, { held, descId: "hud-safety-link", words });
  }

  function readLock() {
    try {
      const tauri = window.__TAURI__;
      const invoke = tauri && tauri.core && tauri.core.invoke;
      if (typeof invoke !== "function") return Promise.resolve(null);
      return Promise.resolve(invoke("get_lock_flags")).then((flags) => {
        setLock(flags);
        return flags;
      }).catch(() => null);
    } catch (err) {
      return Promise.resolve(null);
    }
  }

  // H4-3: edit-mode toggling must repaint the strip (its label appears and
  // the strip stays visible while editing) without polling the body.
  if (typeof MutationObserver !== "undefined") {
    const watcher = new MutationObserver(render);
    watcher.observe(document.body, { attributes: true, attributeFilter: ["data-hud-edit"] });
  }

  // The shell pushes the link on every change; the page keeps the last one for
  // a late-mounting module (the push can arrive before this script runs).
  window.addEventListener("jarvis-link-status", (event) => {
    setLink((event && event.detail) || { up: null });
  });
  // A4: the page publishes the two persistent latches after each /api/status
  // read it already makes. Read-only: this only paints words.
  window.addEventListener("jarvis-latch-status", (event) => {
    setLatch((event && event.detail) || null);
  });
  window.addEventListener("focus", readLock);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) readLock();
  });
  const beat = window.setInterval(() => {
    if (!document.hidden) readLock();
  }, LOCK_BEAT_MS);
  // H4-LOW: no timer outlives the window/page. The interval is cheap, but a
  // destroyed page must not keep an invoke every 20 s.
  function stop() {
    window.clearInterval(beat);
  }
  window.addEventListener("pagehide", stop, { once: true });

  render();
  readLock();
  syncApprovals(document);

  return Promise.resolve({
    setLink,
    setLock,
    setPending,
    setLatch,
    syncApprovals,
    readLock,
    stop,
    state,
    strip,
  });
}
