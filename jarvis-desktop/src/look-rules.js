/**
 * "Look at this" and "Watch with me" on this PC: the words and the few rules
 * each window decides for itself (the owner's decision of 2026-09-28;
 * docs/SCREEN-DESIGN.md; JARVIS-API sections 62 and 96; look.rs and
 * backend/jarvis_screen.py are the session).
 *
 * The session is the PC's. It says only fixed words and numbers - on/off, the
 * minutes left, a pause or end reason from a fixed list ("a password box"),
 * and whether a look is held for follow-up questions - never a program, a
 * site, a title or a word from the screen. What this file does with that:
 *
 *   watchSign     what the always-on-top badge and the bar's strip say (and
 *                 their buttons): Stop watching, 20 more minutes
 *   lookLine      what the bar says after ONE look: "Looked at: Chrome
 *                 window · words only", or the PC's own reason there was none
 *   screenMark    the mark a question carries so the PC adds the screen's
 *                 words to THAT question (`screen: "look"`), only while a look
 *                 is held - the words themselves never pass through an app
 *   markMessage   a chat message with that mark, or unchanged
 *   stripShown    whether the bar's strip has anything to say
 *
 * Pure: no DOM, no Tauri - so node can run it (tests/look-rules.mjs).
 */

export const TITLE = "Jarvis is watching";
export const PAUSED_TITLE = "Jarvis is watching - paused";
export const ENDED_TITLE = "Watching ended";
export const STOP = "Stop watching";
export const MORE = "20 more minutes";
export const START_LABEL = "Watch with me";
export const DROP = "Forget this look";
/** The mark on a question that should read the look the PC holds. */
export const MARK = "look";
export const DOT = " · ";
/** How long the badge and the strip keep saying why a session ended. */
export const ENDED_SHOW_S = 15;

/** Fixed words the windows SHOW. */
export const SEEN = Object.freeze({
  hint: "Press the Look at this key, then ask - Jarvis reads the words on the window in front, once, and keeps nothing.",
  held: "Jarvis is holding what it read for your follow-up questions. It is thrown away when it is two minutes old or the bar closes.",
  held_short: "Answered using what Jarvis read from your screen (words only).",
  link: "The link to Jarvis is catching up - Stop still works",
  watching_note: "Ask about your screen and Jarvis looks when you start. A picture is never saved.",
});

/** "24 min left", "1 min left", "under a minute left". */
export function minutesLeft(leftS) {
  if (!Number.isFinite(leftS) || leftS < 0) return "";
  if (leftS < 60) return "under a minute left";
  return `${Math.ceil(leftS / 60)} min left`;
}

function words(x) {
  return typeof x === "string" ? x.trim() : "";
}

/** Is a session on, from a status? */
export function watchOn(status) {
  return Boolean(status) && status.on === true;
}

/**
 * The sign. `status` is the PC's (GET /api/screen or a `screen_watch` event);
 * `opts.stale`: the link is catching up; `opts.endedAgo`: seconds since it
 * ended, counted on locally.
 *
 * -> { show, on, title, detail, stop, more, tone }
 */
export function watchSign(status, opts = {}) {
  const s = status && typeof status === "object" ? status : {};
  const none = { show: false, on: false, title: "", detail: "", stop: "", more: "", tone: "off" };
  if (watchOn(s)) {
    const left = minutesLeft(s.left_s);
    const paused = s.state === "paused";
    const bits = [];
    if (paused) bits.push(`Paused: ${words(s.pause_words) || "something private is in front"}`);
    if (s.ending_soon === true && !paused) bits.push(`Ending soon - ${left || "almost done"}`);
    else if (left) bits.push(left);
    if (opts.stale === true) bits.push(SEEN.link);
    return {
      show: true,
      on: true,
      title: paused ? PAUSED_TITLE : TITLE,
      detail: bits.join(DOT),
      stop: STOP,
      more: s.ending_soon === true ? MORE : "",
      tone: paused ? "paused" : "watching",
    };
  }
  if (s.state === "ended") {
    const ago = Number.isFinite(opts.endedAgo) ? opts.endedAgo : 0;
    if (ago >= ENDED_SHOW_S) return none;
    return {
      show: true,
      on: false,
      title: ENDED_TITLE,
      detail: words(s.ended_words) ? `Ended: ${words(s.ended_words)}` : "",
      stop: "",
      more: "",
      tone: "ended",
    };
  }
  return none;
}

/**
 * What the bar says after a look: the payload of `screen-look`
 * (`{ok, note, said}`), as one line and a tone. The note names the program the
 * owner asked about - it is on their own screen and stays on it.
 */
export function lookLine(payload) {
  const p = payload && typeof payload === "object" ? payload : {};
  if (p.ok === true) {
    return { text: words(p.note) || "Looked at your screen.", tone: "ok" };
  }
  const said = words(p.said);
  return { text: said || "Jarvis could not look at your screen just now.", tone: "warn" };
}

/** A look is held on the PC for follow-up questions. */
export function lookHeld(status) {
  return Boolean(status) && status.look_held === true;
}

/** The mark for the next question, or null. */
export function screenMark(status) {
  return lookHeld(status) ? MARK : null;
}

/** `message` with the screen mark when a look is held; the same object when
 *  not (never a copy of the words - there are none here). */
export function markMessage(message, status) {
  const mark = screenMark(status);
  if (!mark || !message || typeof message !== "object") return message;
  return { ...message, screen: mark };
}

/** Seconds left of the held look, from the status. */
export function heldLeft(status) {
  const n = status && status.look_left_s;
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Does the bar's strip have anything to show? A session, a held look, a
 *  note or a refusal from the last look. */
export function stripShown(status, note) {
  return watchOn(status) || lookHeld(status) || Boolean(words(note));
}

/**
 * Why Watch with me did not start, for the strip: the PC's or the app's own
 * sentence, or a plain one - never a bridge error.
 */
export function refusedWords(error) {
  const said = words(error && error.message ? error.message : error);
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Watch with me could not start. Try again in a moment.";
  }
  return said;
}

/* ── Settings: the Never look at list ─────────────────────────────────── */

/** The words of Settings -> "Look at this and Watch with me". */
export const SETTINGS = Object.freeze({
  title: "Look at this and Watch with me",
  detail:
    "Jarvis looks at your screen only when you ask. \"Look at this\" reads the words on the window in front, once " +
    "(its key is under Shortcuts). \"Watch with me\" keeps a sign on screen the whole time and takes a fresh look each " +
    "time you start a question. Jarvis reads the words only: a picture is never saved, and what it read is never kept in " +
    "your chats. Anything that looks like a key, a password or a card number is hidden first. It pauses on password " +
    "boxes, on private browser windows, on anything on the list below, and on windows that ask not to be captured.",
  neverTitle: "Never look at",
  neverDetail:
    "Programs and websites Jarvis never looks at - it starts with password managers, Windows sign-in and streaming " +
    "video sites. A window on this list is painted black in what Jarvis looks at, even when it is behind another " +
    "window; so is a private browser window. " +
    "Adding one is instant. Taking one off asks you first, with a card, because it lets Jarvis read that one again. " +
    "This list lives on this PC only.",
  empty: "Nothing added of your own yet. Add your bank here.",
  kindProgram: "A program (like MyBank.exe)",
  kindSite: "A website (like mybank.com)",
  add: "Add to the list",
  take: "Take off...",
  builtIn: "Built in",
  yours: "Added by you",
  program: "Program",
  site: "Website",
  pending: "Waiting for your yes on the card in the Jarvis bar.",
  added: "Added. Jarvis will not look at it.",
  already: "It was already on the list.",
  askedCard: "A card is waiting for your yes in the Jarvis bar. It stays on the list until you say yes.",
  unreadable:
    "Your Never look at list could not be read, so Jarvis is not looking at anything until it can be. " +
    "Nothing on it can be changed either.",
  thisPcOnly: "The list can only be seen and changed on the PC Jarvis runs on.",
});

/** One row of the list, in words: {name, kind, tag, builtIn}. */
export function neverRow(entry) {
  const e = entry && typeof entry === "object" ? entry : {};
  return {
    name: words(e.value),
    kind: e.kind === "site" ? SETTINGS.site : SETTINGS.program,
    tag: e.built_in === true ? SETTINGS.builtIn : SETTINGS.yours,
    builtIn: e.built_in === true,
  };
}

/** The whole list view from GET /api/screen/never-look:
 *  {rows, unreadable, pending, lastWords}. */
export function neverView(out) {
  const o = out && typeof out === "object" ? out : {};
  const entries = Array.isArray(o.entries) ? o.entries : [];
  const last = o.last_removal && typeof o.last_removal === "object" ? o.last_removal : {};
  return {
    rows: entries.map(neverRow).filter((r) => r.name),
    unreadable: o.unreadable === true,
    pending: Array.isArray(o.pending) && o.pending.length > 0,
    lastWords: words(last.message),
  };
}
