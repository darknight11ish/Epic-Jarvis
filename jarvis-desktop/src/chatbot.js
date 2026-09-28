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
 * "Ask several and compare" (backend jarvis_chatbot_compare.py): the same
 * form asks two or more chatbots the same goal - ONE card listing every one,
 * one conversation each, one after another - and the PC writes ONE summary
 * (where they agree, where they disagree and who said what, the sources each
 * gave, who dropped out and why). Pause / Resume / Stop act on the whole
 * comparison. The summary is outside text too.
 *
 * An API service (a chatbot reached with a key) carries this month's money
 * limit from the PC (`money` on the chatbot: "$4.02" and so on, written by
 * the PC), shown with WORDS.money_left; a conversation's `usage.cost` is the
 * PC's estimate. Limits and prices are set on the PC only (its command
 * line, like keys) - this app only shows them.
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
  compare_toggle: "Ask several and compare",
  compare_detail:
    "Jarvis asks two or more chatbots the same goal, one after another, each in its own " +
    "conversation under the same limits. One approval card lists every chatbot it will ask. " +
    "At the end, one summary shows where they agree, where they disagree, and the sources " +
    "each gave.",
  compare_pick: "Chatbots to ask (pick {min} to {max})",
  compare_limits_note: "Most messages and most minutes apply to each chatbot on its own.",
  compare_title: "Comparing chatbots",
  compare_summary_title: "Where they agree and disagree",
  compare_summary_note:
    "Written on this PC from the chatbots' words, so it is outside text too.",
  agree_title: "They agree",
  disagree_title: "They disagree",
  sources_title: "Sources each gave (not checked by Jarvis)",
  dropped_title: "Dropped out",
  conversations_title: "Each conversation",
  compare_too_few: "Pick at least {min} chatbots to compare.",
  compare_too_many: "Pick at most {max} chatbots in this version.",
  compare_not_enough:
    "Fewer than two chatbots can be reached from this PC, so there is nothing to compare yet.",
  compare_gone:
    "That comparison is gone: Jarvis on the PC restarted, and comparisons are kept in memory only.",
  notify_compare_running: "Comparing {count} chatbots: asking {name}, {at} of {count}",
  notify_compare_waiting: "Waiting for your yes to ask {count} chatbots",
  notify_compare_paused: "Paused: comparing {count} chatbots",
  member_waiting: "Waiting its turn.",
  kind_website: "Websites (a browser window on the PC)",
  kind_api: "With a key (each message costs a little)",
  kind_local: "On this PC",
  usage_line: "Used so far: {requests}, {tokens} word-pieces (tokens), model {model}, about {cost}",
  money_left:
    "About {left} of {limit} left this month for {company} (prices are estimates you can correct on the PC).",
  money_pc_only:
    "Each service with a key needs a monthly money limit before Jarvis uses it. Limits and prices are set on the PC only, like keys; the amounts are estimates.",
};

/** How each chatbot is reached (`kind`), in the order the chooser groups them. */
export const KINDS = ["website", "api", "local"];

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

/** What an API (or local) conversation has used so far, or null. */
export function readUsage(u) {
  const o = obj(u);
  if (!o) return null;
  const requests = num(o.requests);
  const tokens = num(o.total_tokens) || num(o.prompt_tokens) + num(o.completion_tokens);
  if (!requests && !tokens) return null;
  // `cost` is the PC's own estimate, as it writes it ("$0.03"); an older PC
  // sends none.
  return { requests, tokens, model: text(o.model), cost: text(o.cost) };
}

/** 4215 as "4,215" - the same on every machine (no locale). */
export function grouped(n) {
  return String(Math.round(num(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about $0.01", or "". */
export function usageLine(u) {
  if (!u) return "";
  let line = WORDS.usage_line;
  if (!u.model) line = line.replace(", model {model}", "");
  if (!u.cost) line = line.replace(", about {cost}", "");
  return line.replace("{requests}", `${u.requests} request${u.requests === 1 ? "" : "s"}`)
    .replace("{tokens}", grouped(u.tokens)).replace("{model}", u.model || "")
    .replace("{cost}", u.cost || "");
}

/** An API service's money limit this month, as the PC wrote it, or null. */
export function readMoney(m) {
  const o = obj(m);
  if (!o || !text(o.limit) || !text(o.left)) return null;
  return {
    company: text(o.company),
    limit: text(o.limit),
    left: text(o.left),
    spent: text(o.spent),
    until: text(o.until),
    reached: o.reached === true,
  };
}

/** "About $4.55 of $5.00 left this month for OpenAI (...)", or "". */
export function moneyLine(bot) {
  const m = bot && bot.money;
  if (!m) return "";
  return WORDS.money_left.replace("{left}", m.left).replace("{limit}", m.limit)
    .replace("{company}", m.company || bot.name || "");
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
    usage: readUsage(o.usage),
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
    // "website", "api" or "local" (an older PC sends none: its chatbots
    // were all websites).
    kind: text(c.kind) || "website",
    // An API service's monthly money limit (the PC's own amounts), or null.
    money: readMoney(c.money),
  }));
  const lim = obj(o.limits) || {};
  const tier = {
    id: text(t.id),
    name: text(t.name),
    words: text(t.words),
    why: text(t.why),
    turnsDefault: num(t.turns_default, 5),
    turnsMax: num(t.turns_max, 8),
    minutesDefault: num(t.minutes_default, 10),
    minutesMax: num(t.minutes_max, 15),
    // An older PC has no comparisons: 0 means "cannot compare".
    compareMin: num(t.compare_min, 2),
    compareMax: num(t.compare_max, 0),
  };
  const usable = chatbots.filter((c) => c.built).length;
  return {
    available: true,
    chatbots,
    anyBuilt: usable > 0,
    canCompare: tier.compareMax >= tier.compareMin && usable >= tier.compareMin,
    tier,
    session: readSession(o.session),
    compare: readCompare(o.compare),
    limits: { waiting: lim.waiting === true, said: text(lim.said) },
  };
}

const texts = (v) => (Array.isArray(v) ? v.map(text).filter(Boolean) : []);

function readCompareSummary(s) {
  const o = obj(s);
  if (!o) return null;
  const list = (v) => (Array.isArray(v) ? v.map(obj).filter(Boolean) : []);
  return {
    answer: text(o.answer),
    agree: texts(o.agree),
    disagree: list(o.disagree).map((d) => ({
      point: text(d.point),
      views: list(d.views).map((v) => ({ who: text(v.who), said: text(v.said) }))
        .filter((v) => v.who && v.said),
    })).filter((d) => d.point && d.views.length),
    // Every source is the chatbot's own and NOT checked by Jarvis, whatever
    // the flag says.
    sources: list(o.sources).map((x) => ({ who: text(x.who), items: texts(x.items) }))
      .filter((x) => x.who && x.items.length),
    dropped: list(o.dropped).map((x) => ({ who: text(x.who), why: text(x.why) }))
      .filter((x) => x.who),
    open: texts(o.open),
    byModel: o.by_model === true,
  };
}

/** One comparison as the PC described it, or null. */
export function readCompare(c) {
  const o = obj(c);
  if (!o || typeof o.id !== "string" || typeof o.state !== "string") return null;
  const chatbots = Array.isArray(o.chatbots)
    ? o.chatbots.map(obj).filter(Boolean).map((b) => ({ id: text(b.id), name: text(b.name) || text(b.id) }))
    : [];
  return {
    id: o.id,
    goal: typeof o.goal === "string" ? o.goal : "",
    state: o.state,
    live: LIVE.has(o.state),
    tierName: text(o.tier_name),
    chatbots,
    count: num(o.count, chatbots.length),
    current: num(o.current),
    currentName: text(o.current_name),
    used: num(o.messages_used),
    max: num(o.max_messages),
    maxMinutes: num(o.max_minutes),
    never: texts(o.never_send),
    paused: o.state === "paused" ? text(o.paused) : "",
    ended: text(o.ended),
    problem: text(o.problem),
    summary: readCompareSummary(o.summary),
    members: Array.isArray(o.members) ? o.members.map(readSession).filter(Boolean) : [],
    hidden: o.hidden === true,
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

/** What is wrong with the "Ask several and compare" form, or "". */
export function compareFormProblem(view, { chatbots, goal, messages, minutes }) {
  if (!view || !view.available) return WORDS.missing;
  if (!view.canCompare) return WORDS.compare_not_enough;
  const picked = [...new Set(chatbots || [])];
  const usable = picked.filter((id) => view.chatbots.some((c) => c.id === id && c.built));
  if (usable.length < picked.length) return "Choose only chatbots that can be reached now.";
  if (usable.length < view.tier.compareMin) {
    return WORDS.compare_too_few.replace("{min}", String(view.tier.compareMin));
  }
  if (usable.length > view.tier.compareMax) {
    return WORDS.compare_too_many.replace("{max}", String(view.tier.compareMax));
  }
  return formProblem(view, { chatbot: usable[0], goal, messages, minutes });
}

/** "Chatbots to ask (pick 2 to 3)". */
export function pickLine(view) {
  if (!view || !view.available) return "";
  return WORDS.compare_pick.replace("{min}", String(view.tier.compareMin))
    .replace("{max}", String(view.tier.compareMax));
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

/** A comparison's heading while it is going ("Comparing 3 chatbots: asking ChatGPT, 2 of 3"). */
export function compareTalkingLine(c) {
  if (!c || !c.live) return "";
  const fill = (w) => w.split("{count}").join(String(c.count)).replace("{name}", c.currentName)
    .replace("{at}", String(c.current + 1));
  if (c.state === "asking") return fill(WORDS.notify_compare_waiting);
  if (c.state === "paused") return fill(WORDS.notify_compare_paused);
  return fill(WORDS.notify_compare_running);
}

/** A comparison's status line: the PC's own words when it has them. */
export function compareStatusLine(c) {
  if (!c) return "";
  if (c.state === "paused" && c.paused) return c.paused;
  if (!c.live && c.ended) return c.ended;
  return STATE_WORDS[c.state] || c.state;
}

/** "4 messages sent in all · at most 3 messages and 10 minutes with each chatbot". */
export function compareProgress(c) {
  if (!c) return "";
  return `${c.used} message${c.used === 1 ? "" : "s"} sent in all · at most ${c.max} messages ` +
    `and ${c.maxMinutes} minutes with each chatbot`;
}

/** One chatbot's line inside a comparison. */
export function memberLine(m, compare) {
  if (!m) return "";
  const waiting = (m.state === "approved" || m.state === "planned") && compare && compare.live;
  return `${m.name}: ${waiting ? WORDS.member_waiting : statusLine(m)}`;
}

/**
 * The chooser's groups, in KINDS order, each with its heading; empty ones
 * left out. A kind this app does not know goes last, with no heading.
 */
export function chatbotGroups(view) {
  if (!view || !view.available) return [];
  const titles = { website: WORDS.kind_website, api: WORDS.kind_api, local: WORDS.kind_local };
  const out = KINDS.map((kind) => ({ kind, title: titles[kind],
    chatbots: view.chatbots.filter((c) => c.kind === kind) }));
  out.push({ kind: "other", title: "", chatbots: view.chatbots.filter((c) => !KINDS.includes(c.kind)) });
  return out.filter((g) => g.chatbots.length);
}
