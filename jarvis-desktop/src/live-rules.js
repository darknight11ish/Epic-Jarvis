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
 *   liveSign        what the always-on-top badge and the bar's strip say
 *                   (and their buttons): End Live, Mic off / Mic on /
 *                   Listen anyway, Carry on, Resume Live, 20 more minutes,
 *                   Show the card, Move it here - and "Jarvis Live is on
 *                   your phone" when it runs there
 *   liveListen      may the next clip be sent, and may the microphone be
 *                   open at all - closed while a card waits (cards are
 *                   decided by tapping only), on a stale link (rule 4),
 *                   while muted or on a call; open but CHECK-ONLY during a
 *                   voice pause, so the owner's own voice carries on
 *   liveReply       what to do with the PC's answer to one clip
 *   liveTransition  the fixed line to say when the status changed by itself
 *   liveChips       the tap buttons after a spoken question (never on a card,
 *                   never garbled)
 *   isSideTalk /    an answer that is only "[not for me]" is never spoken;
 *   couldBeSideTalk speech waits while an answer could still be it
 *   liveBarge       interrupting: another voice LOWERS Jarvis's volume; it
 *                   stops only when the PC says it was the owner
 *   liveFold        a second thought before Jarvis's first sound joins the
 *                   question
 *   cameraShown     never on the PC (the camera is the phone's)
 *   interruptChoice the ONE "Interrupting Jarvis" setting (the owner's
 *                   answer of 2026-09-28 merged the older "Interrupt Jarvis
 *                   while it talks" switch and "Interrupting Jarvis in
 *                   Live"), and how an older choice carries over
 *
 * Pure: no DOM, no Tauri - so node can run it (tests/jarvis-live.mjs).
 */

export const TITLE = "Jarvis Live";
export const DOT = " · ";
export const LINK_WORDS = "Paused: link lost - Live carries on when the link is back";
/** The PC only (live.rs): Windows' lock screen could not be read, so Live
 *  pauses rather than listen through it. */
export const LOCK_UNKNOWN_WORDS = "Paused: can't tell if the PC is locked - Live carries on when it can, or use End Live";
export const SIDE_TALK_MARK = "[not for me]";
export const VOICE_PAUSES = Object.freeze(["other_voices", "voice_trouble"]);
export const CARD_PAUSES = Object.freeze(["card", "cards_unknown"]);

/** Fixed words the apps SHOW (jarvis_live.SEEN). */
export const SEEN = Object.freeze({
  short: "Didn't catch that - say a bit more",
  heard: "Heard you - thinking",
  quiet_warn: "Live ends soon - it's quiet. Say something to keep going",
  end_hint: "To end, say \"Okay Jarvis, that's all for now\", or use End Live.",
  call_unknown: "Jarvis can't tell when you're on a call - use Mic off",
  move: "Live is on your {device} - move it here?",
  elsewhere: "Jarvis Live is on your {device}",
  not_for_me: "(not for Jarvis)",
  trouble: "Heard you, but the words couldn't be made out - say it again",
  busy_mic: "Jarvis Live is already listening - just talk",
  temporary_on: "Temporary is on - this Live session will not be kept in History.",
});

/** How the PC's "no voice trained yet" refusal starts (jarvis_live
 *  NEEDS_VOICE, without its full stop: the PC adds where to train it). */
export const NEEDS_VOICE = "Jarvis Live didn't start: it needs your voice trained first";

/** How each device is named (jarvis_live.DEVICE_WORDS): never "desktop". */
export const DEVICE_WORDS = Object.freeze({ desktop: "PC", phone: "phone" });

/** Why a pause, from the PC (jarvis_live.PAUSE_WORDS) - the card line is
 *  also shown by this app for a card on screen before the PC's own pause. */
export const CARD_WORDS = "Waiting for the card - approve or deny it, and Live carries on";

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
/** Said on the device Live left when it moved (jarvis_live.END_SAID). */
export const MOVED_SAID = "Live moved to your other device.";

/** The buttons, the same words on both apps. */
export const BUTTONS = Object.freeze({
  endLive: "End Live",
  micOff: "Mic off",
  micOn: "Mic on",
  listenAnyway: "Listen anyway",
  moreTime: "20 more minutes",
  stopTalking: "Stop talking",
});
/** The short sound when Live ends here: (hz, ms) notes, made like the "I
 *  heard you" sound (voice-flow.js heardSoundSamples). */
export const END_TONE = Object.freeze([[990, 75], [660, 90]]);
/** "20 more minutes" shows only in the last few minutes. */
export const MORE_TIME_WITHIN_MIN = 5;
/** How long "Jarvis Live ended" shows after an end that cannot be resumed,
 *  and how long "Resume Live" is offered - the PC's `limits` win. */
export const ENDED_SHOW_S = 15;
export const RESUME_S = 600;

/** "Interrupting Jarvis": ONE setting of THIS app (Settings -> Voice), the
 *  same words as the phone's, for Live and for ordinary replies alike. */
export const INTERRUPT_TITLE = "Interrupting Jarvis";
export const INTERRUPT = Object.freeze([
  {
    id: "voice",
    label: "Interrupt by voice",
    recommended: true,
    detail: "While Jarvis talks, say \"stop\" or just start talking, and it stops for your voice. The Stop talking button works too.",
  },
  {
    id: "tap",
    label: "By button only",
    detail: "Talking over Jarvis doesn't stop it - use the Stop talking button instead. Good for a noisy room. In Jarvis Live the microphone closes while Jarvis talks.",
  },
  {
    id: "off",
    label: "Don't interrupt",
    detail: "Jarvis finishes what it is saying: talking over it doesn't stop it, and there is no Stop talking button. End Live and Stop everything still stop it.",
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
const WH_START = new Set(["which", "what", "who", "where", "when", "how", "why"]);
const DETERMINERS = new Set(["the", "a", "an", "my", "your", "this", "that", "these", "those", "some"]);
const TRIM = /^[\s,;:"'.\-–—]+|[\s,;:"'.\-–—]+$/g;

const obj = (v) => (v && typeof v === "object" ? v : {});
const int = (v) => (Number.isInteger(v) ? v : null);

/** Is `status` a session on `me` ("desktop" or "phone")? */
export function onHere(status, me) {
  const s = obj(status);
  return s.on === true && s.device === me;
}

/** "PC" / "phone" / "other device". */
export function deviceWords(device) {
  return DEVICE_WORDS[device] || "other device";
}

/** "Live is on your PC - move it here?" */
export function moveWords(device) {
  return SEEN.move.replace("{device}", deviceWords(device));
}

function limit(s, key, fallback) {
  const v = obj(s.limits)[key];
  return Number.isInteger(v) ? v : fallback;
}

/**
 * The sign on `me`: `{show, title, detail, stop, mute, carryOn, resume,
 * moreTime, showCard, move}`. `thinking`: the bar heard the owner and is
 * waiting for the answer; `short`: the last clip was probably the owner, but
 * too short; `cardShown`: this app shows a card raised in this session;
 * `endedAgo`: seconds since it ended, as this app counts them on from the
 * PC's `ended_ago_s`.
 */
export function liveSign(status, me, { stale = false, thinking = false, short = false, cardShown = false, endedAgo = null } = {}) {
  const s = obj(status);
  const none = {
    show: false, title: "", detail: "", stop: "", mute: "",
    carryOn: false, resume: false, moreTime: false, showCard: false, move: false,
  };
  if (s.state === "ended" && s.ended_device === me) {
    const ago = int(endedAgo) ?? int(s.ended_ago_s) ?? 0;
    const resume = s.resumable === true && ago <= limit(s, "resume_s", RESUME_S);
    if (!resume && ago > limit(s, "ended_show_s", ENDED_SHOW_S)) return none;
    return { ...none, show: true, title: `${TITLE} ended`, detail: s.ended_words || "", resume };
  }
  if (s.on === true && Object.hasOwn(DEVICE_WORDS, s.device) && s.device !== me) {
    return { ...none, show: true, title: SEEN.elsewhere.replace("{device}", deviceWords(s.device)), move: true };
  }
  if (!onHere(s, me)) return none;
  const mins = int(s.minutes_left);
  const title = TITLE + (mins !== null ? `${DOT}${mins} min left` : "");
  const paused = s.paused || "";
  let detail = "";
  if (stale) detail = LINK_WORDS;
  else if (s.muted) detail = s.muted_words || "";
  else if (paused) detail = s.pause_words || "";
  else if (cardShown) detail = CARD_WORDS;
  else if (s.quiet_warn) detail = SEEN.quiet_warn;
  else if (thinking) detail = SEEN.heard;
  else if (short) detail = SEEN.short;
  else if (s.hint) detail = s.hint_words || "";
  let mute = BUTTONS.micOff;
  if (s.muted) mute = s.muted_why === "call" || s.muted_why === "mic_in_use" ? BUTTONS.listenAnyway : BUTTONS.micOn;
  return {
    ...none,
    show: true,
    title,
    detail,
    stop: BUTTONS.endLive,
    mute,
    carryOn: VOICE_PAUSES.includes(paused),
    moreTime: mins !== null && mins <= MORE_TIME_WITHIN_MIN,
    showCard: paused === "card" || cardShown,
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
  if (live === "off") return { action: "end", say: "" };
  // The owner's voice, but no words could be made of it: Live carries on.
  if (h.available === false) return { action: "trouble", say: "" };
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
  if (a.state === "ended" && a.ended_device === me && onHere(b, me)) return a.ended_say || "";
  if (onHere(b, me) && a.on === true && a.device != null && a.device !== me) return MOVED_SAID;
  if (onHere(a, me) && a.ending_soon && !b.ending_soon && b.session === a.session) return LINES.warn;
  return "";
}

const cap = (s) => {
  const t = String(s).trim();
  return t ? t[0].toUpperCase() + t.slice(1) : t;
};
const trim = (s) => String(s).replace(TRIM, "");
const wordsOf = (s) => String(s).split(" ").filter(Boolean);

/** The tap buttons after a spoken answer that ends with a question. Each is
 *  sent as the owner's typed words. Never while a card is on screen, and
 *  never a garbled one: no buttons rather than wrong ones
 *  (tools/gen_live_cases.py `chips` says the rule in words). */
export function liveChips(answer, { cardShown = false } = {}) {
  if (cardShown) return [];
  const text = wordsOf(String(answer || "").split(/\s+/).join(" ")).join(" ");
  if (!text.endsWith("?")) return [];
  const parts = text.split(/(?<=[.!?])\s+/);
  const q = parts[parts.length - 1].replace(/\?+$/, "").trim();
  const words = wordsOf(q.toLowerCase());
  const at = q.lastIndexOf(" or ");
  if (at < 0) return words.length && YES_NO_START.has(words[0]) ? ["Yes", "No"] : [];
  let left = q.slice(0, at);
  const right = trim(q.slice(at + 4));
  let cut = -1;
  let cutLen = 0;
  for (const sep of [": ", " - ", " – ", " — "]) {
    const i = left.lastIndexOf(sep);
    if (i > cut) {
      cut = i;
      cutLen = sep.length;
    }
  }
  if (cut >= 0) left = left.slice(cut + cutLen);
  const rwords = wordsOf(right);
  if (rwords.length < 1 || rwords.length > 4) return [];
  const segs = left.split(",").map(trim).filter(Boolean);
  if (!segs.length) return [];
  const lead = wordsOf(segs[0])[0].toLowerCase();
  let options;
  if (WH_START.has(lead) && segs.length >= 2) {
    options = segs.slice(1);
  } else if (WH_START.has(lead) || YES_NO_START.has(lead)) {
    const first = wordsOf(segs[0]);
    const n = segs.length >= 2 ? wordsOf(segs[1]).length : rwords.length;
    if (first.length <= n) return [];
    const tail = first.slice(-n);
    const head = tail[0].toLowerCase();
    if (n > 1 && !DETERMINERS.has(head)) return [];
    if (YES_NO_START.has(head) || WH_START.has(head)) return [];
    options = [tail.join(" "), ...segs.slice(1)];
  } else {
    options = segs;
  }
  options = options.filter(Boolean).concat([right]);
  if (options.some((o) => wordsOf(o).length > 4)) return [];
  return options.length >= 2 && options.length <= MAX_CHIPS ? options.map(cap) : [];
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

/** A card raised this long before Live started still counts (jarvis_live.CARD_SLACK_S). */
export const CARD_SLACK_S = 2;

/**
 * Does a card this app shows hold Live (close the microphone, hide the tap
 * buttons)? Only one raised in THIS session - the PC's own rule (the design's
 * C8): a card already waiting before Live started does not. A card whose
 * time cannot be read, or a status without `started_at`, counts (fail
 * closed). `created` and `started_at` are both the PC's clock.
 */
export function cardInSession(created, status) {
  const s = obj(status);
  if (typeof created !== "number" || !Number.isFinite(created)) return true;
  if (typeof s.started_at !== "number" || !Number.isFinite(s.started_at)) return true;
  return created >= s.started_at - CARD_SLACK_S;
}

/** The camera switch: the phone's only, and only when the PC says ready. */
export function cameraShown(status, me) {
  const s = obj(status);
  return me === "phone" && onHere(s, me) && obj(s.camera).ready === true;
}

/* ── The one "Interrupting Jarvis" setting ─────────────────────────────── */

/** Where it is kept (localStorage), and the two older settings it replaced. */
export const INTERRUPT_KEY = "jarvis.interrupt";
export const OLD_BARGE_IN_KEY = "jarvis.voice.bargeIn";
export const OLD_LIVE_INTERRUPT_KEY = "jarvis.live.interrupt";
const CHOICE_IDS = ["voice", "tap", "off"];

/**
 * The setting, from what is stored: the new one when chosen, else the older
 * ones carried over - "Interrupt Jarvis while it talks" turned OFF becomes
 * "Don't interrupt", Live's "tap only" becomes "By button only". `echo`:
 * this device can take its own voice's echo out (the PC's old switch was on
 * by default, so the PC passes true).
 */
export function interruptChoice(saved, oldBargeIn, oldLive, echo) {
  if (CHOICE_IDS.includes(saved)) return saved;
  if (oldBargeIn === false) return "off";
  if (oldLive === "tap") return "tap";
  if (oldBargeIn === true) return "voice";
  return echo ? "voice" : "tap";
}

/** The setting as this PC has it stored (localStorage), or the default. */
export function loadInterrupt(storage = globalThis.localStorage) {
  try {
    if (!storage) return "voice";
    const saved = storage.getItem(INTERRUPT_KEY);
    const old = storage.getItem(OLD_BARGE_IN_KEY);
    const oldBargeIn = old === "off" ? false : old === "on" ? true : null;
    return interruptChoice(saved, oldBargeIn, storage.getItem(OLD_LIVE_INTERRUPT_KEY), true);
  } catch {
    return "voice";
  }
}

/** Saves it. Returns whether it could be saved. */
export function saveInterrupt(value, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(INTERRUPT_KEY, CHOICE_IDS.includes(value) ? value : "voice");
    return true;
  } catch {
    return false;
  }
}
