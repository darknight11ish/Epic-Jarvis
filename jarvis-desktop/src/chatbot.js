/**
 * "Talk to a chatbot for me" (the owner's decisions of 2026-09-27 and
 * 2026-09-28; docs/CHATBOT-DRIVER-DESIGN.md; JARVIS-API.md section 60;
 * backend jarvis_chatbot.py and jarvis_chatbot_routes.py).
 *
 * Jarvis asks an AI chatbot (Gemini first) about something for the owner
 * and writes its own follow-ups on the PC, within limits the owner set on
 * ONE approval card. This module holds the words and reads what the PC
 * sends; brain.js draws the Work tab's card (the form, the live
 * conversation, Pause / Resume / Stop, Change limits, the end summary) and
 * calls the Rust commands in src-tauri/src/brain/chatbot.rs.
 *
 * The chatbot's words and the summary are OUTSIDE TEXT: shown in the
 * outside-text style, never read aloud (nothing here speaks), never offered
 * to be remembered.
 *
 * The phone says the same words (net/Chatbot.kt); tests/chatbot.mjs and the
 * phone's ChatbotTest check them against tools/gen_chatbot_cases.py's file,
 * which takes them from the PC's own jarvis_chatbot_routes.WORDS.
 *
 * @module chatbot
 */

/** The sentences both apps show, word for word (jarvis_chatbot_routes.WORDS). */
export const WORDS = {
  title: "Talk to a chatbot for me",
  detail:
    "Jarvis asks an AI chatbot about something for you, and writes its own follow-up " +
    "questions on this PC, within limits you set. One approval card covers the whole " +
    "conversation. While it does this, Jarvis knows only your goal - not your memory, " +
    "email, calendar, notes or files.",
  chatbot_label: "Chatbot",
  goal_label: "What should Jarvis find out?",
  goal_note: "These words will be sent to the chatbot exactly as you type them.",
  messages_label: "Most messages",
  minutes_label: "Most minutes",
  never_label: "Words it must never send (optional, separated by commas)",
  start: "Start",
  start_note: "Nothing is sent until you approve the card.",
  pause: "Pause",
  resume: "Resume",
  stop: "Stop",
  change_limits: "Change limits",
  limits_note: "A change to the limits needs a new approval card.",
  transcript_title: "The conversation",
  outside_note:
    "The chatbot's words are outside text: shown here, never learned from, never read aloud.",
  summary_title: "What Jarvis found",
  summary_note: "Written on this PC from the chatbot's words, so it is outside text too.",
  claim_sourced: "it gave a source (not checked by Jarvis)",
  claim_unsourced: "no source given",
  open_title: "Still open",
  question_title: "The chatbot asked about you",
  question_note:
    "Jarvis never answers questions about you. It is shown here for you to decide.",
  none_built:
    "No chatbot can be reached from this PC yet. The line beside each one says what is missing. Start waits until one can.",
  sign_in_pc:
    "Signing in to the chatbot's account happens on the PC only, in the browser window Jarvis uses.",
  missing: "Your PC's Jarvis cannot talk to chatbots yet - run apply-patches.ps1 on the PC.",
  gone:
    "That conversation is gone: Jarvis on the PC restarted, and conversations are kept in memory only.",
  hidden: "The goal and the conversation are hidden until you confirm it is you.",
  version: "Version",
  notify_running: "Talking to {name}, {used} of {max}",
  notify_waiting: "Waiting for your yes to talk to {name}",
  notify_paused: "Paused: talking to {name}, {used} of {max}",
  notify_locked: "Jarvis is talking to a chatbot for you.",
};

/** The states in which a conversation is still going. */
export const LIVE = new Set(["asking", "approved", "running", "paused"]);

/** Held on a stale link: they make Jarvis send, or ask a card to. */
export const HELD_WHEN_STALE = new Set(["start", "resume", "limits"]);

/** How often the card reads again while a conversation is live. */
export const POLL_MS = 4000;

/** What each state is called on screen. */
export const STATE_WORDS = {
  asking: "Waiting for your yes on the approval card.",
  approved: "Approved - starting.",
  running: "Talking now.",
  paused: "Paused.",
  done: "Finished.",
  stopped: "Stopped.",
  refused: "Not started.",
};

const text = (v) => (typeof v === "string" ? v.trim() : "");
const num = (v, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : null);

function readTurn(t) {
  const o = obj(t);
  if (!o) return null;
  const who = o.who === "chatbot" ? "chatbot" : o.who === "jarvis" ? "jarvis" : "";
  if (!who) return null;
  return {
    who,
    n: num(o.n),
    text: typeof o.text === "string" ? o.text : "",
    // Belt and braces: anything the chatbot said is outside text, whatever
    // the flag says.
    outside: who === "chatbot" || o.outside_text === true,
    move: text(o.move),
  };
}

function readSummary(s) {
  const o = obj(s);
  if (!o) return null;
  return {
    answer: text(o.answer),
    claims: Array.isArray(o.claims)
      ? o.claims.map(obj).filter(Boolean).map((c) => ({
        claim: text(c.claim),
        sourced: c.source_given === true,
      })).filter((c) => c.claim)
      : [],
    open: Array.isArray(o.open) ? o.open.map(text).filter(Boolean) : [],
    byModel: o.by_model === true,
  };
}

/** One conversation as the PC described it, or null. */
export function readSession(s) {
  const o = obj(s);
  if (!o || typeof o.id !== "string" || typeof o.state !== "string") return null;
  return {
    id: o.id,
    chatbot: text(o.chatbot),
    name: text(o.name) || "the chatbot",
    goal: typeof o.goal === "string" ? o.goal : "",
    state: o.state,
    live: LIVE.has(o.state),
    tierName: text(o.tier_name),
    used: num(o.messages_used),
    max: num(o.max_messages),
    minutesUsed: num(o.minutes_used),
    maxMinutes: num(o.max_minutes),
    never: Array.isArray(o.never_send) ? o.never_send.map(text).filter(Boolean) : [],
    // The PC keeps the last pause's words after a stop; they are shown only
    // while it is really paused.
    paused: o.state === "paused" ? text(o.paused) : "",
    ended: text(o.ended),
    question: text(o.question),
    problem: text(o.problem),
    summary: readSummary(o.summary),
    transcript: Array.isArray(o.transcript) ? o.transcript.map(readTurn).filter(Boolean) : [],
    hidden: o.hidden === true,
  };
}

/**
 * GET /api/chatbot/status as a view, or `{available: false, why}` for a PC
 * without the routes (Rust answers that for a 404 or 501) or anything
 * unreadable.
 */
export function readChatbot(body) {
  const o = obj(body);
  if (!o || o.available === false || !Array.isArray(o.chatbots) || !obj(o.tier)) {
    return { available: false, why: text(o && o.why) || WORDS.missing };
  }
  const t = o.tier;
  const chatbots = o.chatbots.map(obj).filter((c) => c && typeof c.id === "string").map((c) => ({
    id: c.id,
    name: text(c.name) || c.id,
    host: text(c.host),
    // `built` here means "can be used now": built AND set up on this PC
    // (`ready`, e.g. Gemini's window signed in). `made` is built at all.
    built: c.built === true && c.ready !== false,
    made: c.built === true,
    note: text(c.note),
  }));
  const lim = obj(o.limits) || {};
  return {
    available: true,
    chatbots,
    anyBuilt: chatbots.some((c) => c.built),
    tier: {
      id: text(t.id),
      name: text(t.name),
      words: text(t.words),
      why: text(t.why),
      turnsDefault: num(t.turns_default, 5),
      turnsMax: num(t.turns_max, 8),
      minutesDefault: num(t.minutes_default, 10),
      minutesMax: num(t.minutes_max, 15),
    },
    session: readSession(o.session),
    limits: { waiting: lim.waiting === true, said: text(lim.said) },
  };
}

/** "Version: the limited version (one graphics card) - shorter conversations; ..." */
export function versionLine(view) {
  if (!view || !view.available || !view.tier.name) return "";
  return `${WORDS.version}: ${view.tier.name}` + (view.tier.words ? ` - ${view.tier.words}` : "");
}

/** The never-send words typed, as a list: split on commas, tidied, no repeats. */
export function neverWords(value) {
  const out = [];
  for (const raw of String(value == null ? "" : value).split(",")) {
    const w = raw.split(/\s+/).filter(Boolean).join(" ");
    if (w && !out.some((o) => o.toLowerCase() === w.toLowerCase())) out.push(w);
  }
  return out;
}

/** A limit typed, or null when it is not 1 to `most`. */
export function limitOf(value, most) {
  const s = String(value == null ? "" : value).trim();
  if (!/^\d{1,3}$/.test(s)) return null;
  const n = Number(s);
  return n >= 1 && n <= most ? n : null;
}

/** What is wrong with the form, in a sentence, or "" when it can be sent. */
export function formProblem(view, { chatbot, goal, messages, minutes }) {
  if (!view || !view.available) return WORDS.missing;
  const bot = view.chatbots.find((c) => c.id === chatbot);
  if (!bot) return "Choose a chatbot.";
  if (!bot.built) {
    if (bot.made && bot.note) return /[.!?]$/.test(bot.note) ? bot.note : `${bot.note}.`;
    return `${bot.name} is not built yet.`;
  }
  if (!String(goal || "").trim()) return "Say what Jarvis should find out.";
  if (String(goal).trim().length > 1000) return "The goal is longer than 1000 characters.";
  if (limitOf(messages, view.tier.turnsMax) === null) {
    return `Most messages: 1 to ${view.tier.turnsMax} in this version.`;
  }
  if (limitOf(minutes, view.tier.minutesMax) === null) {
    return `Most minutes: 1 to ${view.tier.minutesMax} in this version.`;
  }
  return "";
}

/** "Message 2 of 4 · 1.5 of 10 minutes". */
export function progressLine(s) {
  if (!s) return "";
  return `Message ${s.used} of ${s.max} · ${s.minutesUsed} of ${s.maxMinutes} minutes`;
}

/** The buttons for a conversation, in order. Stop is always there while it is live. */
export function actionsOf(s) {
  if (!s || !s.live) return [];
  if (s.state === "paused") return ["resume", "stop"];
  if (s.state === "running") return ["pause", "stop"];
  return ["stop"];
}

/** One conversation's status line: the PC's own words when it has them. */
export function statusLine(s) {
  if (!s) return "";
  if (s.state === "paused" && s.paused) return s.paused;
  if (!s.live && s.ended) return s.ended;
  return STATE_WORDS[s.state] || s.state;
}

/** The phone's ongoing notification line; the desktop uses it as the card's heading line. */
export function talkingLine(s) {
  if (!s || !s.live) return "";
  const fill = (w) => w.replace("{name}", s.name).replace("{used}", String(s.used))
    .replace("{max}", String(s.max));
  if (s.state === "asking") return fill(WORDS.notify_waiting);
  if (s.state === "paused") return fill(WORDS.notify_paused);
  return fill(WORDS.notify_running);
}
