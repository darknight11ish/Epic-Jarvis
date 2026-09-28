/**
 * Jarvis Live's rules on this PC - the same as the phone's
 * (voice/LiveRules.kt), both held to tests/fixtures/live-cases.json, which
 * tools/gen_live_cases.py writes from backend/jarvis_live.py.
 *
 * Jarvis Live (the owner's decision and answers of 2026-09-28,
 * docs/LIVE-DESIGN.md): a back-and-forth voice conversation the owner starts
 * and stops. The session is the PC's (GET/POST /api/voice/live); these are
 * the few things each app decides for itself:
 *
 *   liveSign        what the always-on-top badge says (and its buttons)
 *   liveListen      may the next clip be sent, and may the microphone be
 *                   open at all - closed while a card waits (cards are
 *                   decided by tapping only), on a stale link (rule 4),
 *                   while muted or on a call; open but CHECK-ONLY during a
 *                   voice pause, so the owner's own voice carries on
 *   liveReply       what to do with the PC's answer to one clip
 *   liveTransition  the fixed line to say when the status changed by itself
 *   liveChips       the tap buttons after a spoken question (never on a card)
 *   isSideTalk /    an answer that is only "[not for me]" is never spoken;
 *   couldBeSideTalk speech waits while an answer could still be it
 *   liveBarge       interrupting: another voice LOWERS Jarvis's volume; it
 *                   stops only when the PC says it was the owner
 *   liveFold        a second thought before Jarvis's first sound joins the
 *                   question
 *   cameraShown     never on the PC (the camera is the phone's)
 *
 * Pure: no DOM, no Tauri - so node can run it (tests/jarvis-live.mjs).
 */

export const TITLE = "Jarvis Live";
export const DOT = " · ";
export const LINK_WORDS = "Paused: link lost";
/** The PC only (live.rs): Windows' lock screen could not be read, so Live
 *  pauses rather than listen through it. */
export const LOCK_UNKNOWN_WORDS = "Paused: can't tell if the PC is locked";
export const SIDE_TALK_MARK = "[not for me]";
export const VOICE_PAUSES = Object.freeze(["other_voices", "voice_trouble"]);
export const CARD_PAUSES = Object.freeze(["card", "cards_unknown"]);

/** Fixed words the apps SHOW (jarvis_live.SEEN). */
export const SEEN = Object.freeze({
  short: "Didn't catch that - say a bit more",
  heard: "Heard you - thinking",
  quiet_warn: "Live ends soon - it's quiet",
  end_hint: "To end, say \"Okay Jarvis, that's all for now\", or press End.",
  call_unknown: "Jarvis can't tell when you're on a call - use Mute",
  move: "Live is on your {device} - move it here?",
  not_for_me: "(not for Jarvis)",
});

/** Fixed lines Jarvis SAYS (jarvis_live.LINES). */
export const LINES = Object.freeze({
  started: "I'm listening.",
  waking: "Waking up, a few seconds.",
  short: "Say a bit more, so I can tell it's you.",
  bye: "Okay. Live ended.",
  extended: "Okay, {n} more minutes.",
  warn: "Two minutes left. To keep going, say: give me twenty more minutes.",
  quiet: "Live ended - it was quiet.",
});

/** "Interrupting Jarvis in Live": a setting of THIS app (Settings -> Voice),
 *  the same words as the phone's. */
export const INTERRUPT_TITLE = "Interrupting Jarvis in Live";
export const INTERRUPT = Object.freeze([
  {
    id: "voice",
    label: "Interrupt by voice",
    recommended: true,
    detail: "In Jarvis Live, start talking while Jarvis talks and it stops for your voice.",
  },
  {
    id: "tap",
    label: "Interrupt by tap only",
    detail: "In Jarvis Live, talking over Jarvis does not stop it - tap Stop talking instead. Good for a noisy room.",
  },
]);
export const STOP_TALKING = "Stop talking";
/** Smart Turn in Live: an unfinished-sounding sentence may pause this long. */
export const TURN = Object.freeze({ askAfterMs: 200, maxPauseMs: 3000 });
/** How far Jarvis's voice drops while another voice is being checked. */
export const DUCK_VOLUME = 0.3;
export const MAX_CHIPS = 3;

const YES_NO_START = new Set(["do", "does", "did", "is", "are", "was", "were", "should", "shall",
  "can", "could", "will", "would", "have", "has", "want", "may", "am"]);

const obj = (v) => (v && typeof v === "object" ? v : {});

/** Is `status` a session on `me` ("desktop" or "phone")? */
export function onHere(status, me) {
  const s = obj(status);
  return s.on === true && s.device === me;
}

/**
 * The sign on `me`: `{show, title, detail, stop, mute, carryOn, resume}`.
 * `thinking`: the bar heard the owner and is waiting for the answer;
 * `short`: the last clip was probably the owner, but too short.
 */
export function liveSign(status, me, { stale = false, thinking = false, short = false } = {}) {
  const s = obj(status);
  const none = { show: false, title: "", detail: "", stop: "", mute: "", carryOn: false, resume: false };
  if (s.state === "ended" && s.ended_device === me) {
    const words = s.ended_words || "";
    return { ...none, show: true, title: `${TITLE} ended`, detail: words ? `It ended: ${words}.` : "", resume: s.resumable === true };
  }
  if (!onHere(s, me)) return none;
  const title = TITLE + (Number.isInteger(s.minutes_left) ? `${DOT}${s.minutes_left} min left` : "");
  let detail = "";
  if (stale) detail = LINK_WORDS;
  else if (s.muted) detail = s.muted_words || "";
  else if (s.paused) detail = s.pause_words || "";
  else if (s.quiet_warn) detail = SEEN.quiet_warn;
  else if (thinking) detail = SEEN.heard;
  else if (short) detail = SEEN.short;
  else if (s.hint) detail = s.hint_words || "";
  return {
    ...none,
    show: true,
    title,
    detail,
    stop: me === "phone" ? "End" : "Stop",
    mute: s.muted ? "Unmute" : "Mute",
    carryOn: VOICE_PAUSES.includes(s.paused),
  };
}

/** `{listen, mic, why}`: may the next clip go, and may the microphone be open? */
export function liveListen(status, me, { stale = false, cardShown = false, answering = false, appLocked = false, interrupt = "voice" } = {}) {
  const s = obj(status);
  if (!onHere(s, me)) return { listen: false, mic: false, why: "off" };
  if (appLocked) return { listen: false, mic: false, why: "locked" };
  if (stale) return { listen: false, mic: false, why: "link" };
  if (s.muted) return { listen: false, mic: false, why: "muted" };
  if (cardShown || CARD_PAUSES.includes(s.paused)) return { listen: false, mic: false, why: "card" };
  if (VOICE_PAUSES.includes(s.paused)) return { listen: true, mic: true, why: "check" };
  if (answering) return { listen: false, mic: interrupt === "voice", why: "answering" };
  return { listen: true, mic: true, why: "" };
}

/** `{action, say}` for the PC's answer to one clip in Live. Reads both the
 *  PC's own names (`live_say`) and the desktop's camelCase ones (`liveSay`,
 *  voice.rs HeardReply). */
export function liveReply(heard) {
  const h = obj(heard);
  const pick = (a, b) => (h[a] !== undefined ? h[a] : h[b]);
  const say = pick("live_say", "liveSay") || "";
  const live = h.live || "";
  if (live === "ended") return { action: "end", say };
  if (live === "refused") return { action: "refused", say: "" };
  if (live === "started") return { action: "start", say };
  if (pick("live_elsewhere", "liveElsewhere")) return { action: "move", say: "" };
  if (live === "off" || h.available === false) return { action: "end", say: "" };
  if (h.stop === true) return { action: "stop", say: "" };
  if (live === "paused") return { action: "pause", say };
  const text = String(h.text || "").trim();
  const ok = h.ok !== undefined ? h.ok === true : (h.isOwner === true && h.available !== false);
  if (ok && text) return { action: "answer", say: "" };
  if (pick("too_short", "tooShort") === true && pick("live_short", "liveShort") === "owner") {
    return { action: "short", say };
  }
  return { action: "listen", say };
}

/** The fixed line to say when the status changed by itself, or "". */
export function liveTransition(before, after, me) {
  const b = obj(before);
  const a = obj(after);
  if (a.state === "ended" && a.ended === "quiet" && a.ended_device === me && onHere(b, me)) return LINES.quiet;
  if (onHere(a, me) && a.ending_soon && !b.ending_soon && b.session === a.session) return LINES.warn;
  return "";
}

const cap = (s) => {
  const t = String(s).trim();
  return t ? t[0].toUpperCase() + t.slice(1) : t;
};

/** The tap buttons after a spoken answer that ends with a question. Each is
 *  sent as the owner's typed words. Never while a card is on screen. */
export function liveChips(answer, { cardShown = false } = {}) {
  if (cardShown) return [];
  const text = String(answer || "").split(/\s+/).filter(Boolean).join(" ");
  if (!text.endsWith("?")) return [];
  const parts = text.split(/(?<=[.!?])\s+/);
  const q = parts[parts.length - 1].replace(/\?+$/, "").trim();
  const words = q.toLowerCase().split(" ").filter(Boolean);
  const at = q.lastIndexOf(" or ");
  if (at >= 0) {
    const left = q.slice(0, at);
    const right = q.slice(at + 4).replace(/^[\s,]+|[\s,]+$/g, "");
    const rwords = right.split(" ").filter(Boolean);
    if (rwords.length >= 1 && rwords.length <= 4) {
      const n = rwords.length;
      const segs = left.split(",").map((s) => s.trim());
      const first = segs[0].split(" ").filter(Boolean);
      let options = first.length >= n ? [first.slice(-n).join(" ")] : [];
      options = options.concat(segs.slice(1).filter((s) => s && s.split(" ").filter(Boolean).length <= 4));
      options = options.filter(Boolean).concat([right]);
      if (options.length >= 2 && options.length <= MAX_CHIPS) return options.map(cap);
    }
    // An either-or whose options are too long for a button: no chips.
    return [];
  }
  if (words.length && YES_NO_START.has(words[0])) return ["Yes", "No"];
  return [];
}

/** Is this whole answer the side-talk marker? (jarvis_live.is_side_talk) */
export function isSideTalk(answer) {
  const a = String(answer || "").trim().toLowerCase().replace(/\.+$/, "").trim();
  return a === SIDE_TALK_MARK;
}

/** Hold speech while the answer so far could still turn out to be the marker. */
export function couldBeSideTalk(partial) {
  const p = String(partial || "").trim().toLowerCase();
  return Boolean(p) && (SIDE_TALK_MARK.startsWith(p) || isSideTalk(p));
}

/** Interrupting in Live: "onset" -> duck; "owner" -> stop; anything else -> restore. */
export function liveBarge(event) {
  return event === "onset" ? "duck" : event === "owner" ? "stop" : "restore";
}

/** A second thought before Jarvis's first sound joins the question. */
export function liveFold(previous, next, sounded) {
  const prev = String(previous || "").trim();
  const now = String(next || "").trim();
  if (sounded || !prev) return now;
  return `${prev} ${now}`.trim();
}

/** The camera switch: the phone's only, and only when the PC says ready. */
export function cameraShown(status, me) {
  const s = obj(status);
  return me === "phone" && onHere(s, me) && obj(s.camera).ready === true;
}

/** The interrupt setting as stored (localStorage), or the default. */
export const INTERRUPT_KEY = "jarvis.live.interrupt";
export function loadInterrupt(storage = globalThis.localStorage) {
  try {
    const v = storage && storage.getItem(INTERRUPT_KEY);
    return v === "tap" ? "tap" : "voice";
  } catch {
    return "voice";
  }
}
export function saveInterrupt(value, storage = globalThis.localStorage) {
  try {
    if (storage) storage.setItem(INTERRUPT_KEY, value === "tap" ? "tap" : "voice");
  } catch {
    /* a setting that cannot be saved stays the default */
  }
}
