/**
 * "Chat with customer support for me" (the owner's decisions of 2026-09-28;
 * docs/CHATBOT-DRIVER-DESIGN.md "Customer-support chats"; JARVIS-API.md
 * section 65; backend jarvis_support.py through jarvis_chatbot_routes.py).
 *
 * Jarvis chats with a company's customer support (Groupon first) in the
 * owner's name, in a browser window on the PC. ONE approval card lists
 * exactly which details it may give; EVERY offer gets its own card, and
 * nothing is accepted before the owner approves it; "are you a bot?" and
 * identity checks are handed to the owner. This module holds the words and
 * reads what the PC sends; brain.js draws the Work tab's card and calls the
 * Rust commands in src-tauri/src/brain/support.rs.
 *
 * The company's words and the summary are OUTSIDE TEXT: shown in the
 * outside-text style, never read aloud (nothing here speaks), never offered
 * to be remembered.
 *
 * The phone says the same words (net/Support.kt); tests/support.mjs and the
 * phone's SupportTest check them against tools/gen_support_cases.py's file,
 * which takes them from the PC's own jarvis_support.WORDS.
 *
 * @module support
 */

/** The sentences both apps show, word for word (jarvis_support.WORDS). */
export const WORDS = {
  title: "Chat with customer support for me",
  detail:
    "Jarvis chats with a company's customer support for you (Groupon first), in your name, " +
    "in a browser window on the PC. One approval card lists exactly which of your details " +
    "it may give. Every offer - a refund, a credit, a cancellation - gets its own card, and " +
    "nothing is accepted before you approve it.",
  company_label: "Company",
  address_label: "The company's help page (https://...)",
  goal_label: "What should Jarvis get done?",
  goal_note: "Jarvis writes its own messages from these words, in your name.",
  details_label: "Details Jarvis may give (one per row: a name and its exact value)",
  details_note:
    "Never a password, PIN, security answer, card number or ID number: those are refused, " +
    "and if the agent asks, Jarvis hands it to you.",
  detail_name: "Name (like Order number)",
  detail_value: "Exact value",
  add_detail: "Add a detail",
  remove_detail: "Remove",
  messages_label: "Most messages",
  minutes_label: "Most minutes of chat",
  queue_label: "Most minutes in the queue",
  start: "Start",
  start_note: "Nothing is sent until you approve the card.",
  terms_title: "Terms risk",
  sign_in_pc:
    "You sign in to your own account by hand in the window on the PC, and open the " +
    "company's chat there yourself (its Chat or Help button). Jarvis never types, sees or " +
    "keeps a password.",
  take_over: "Take over",
  take_over_note: "Jarvis stops sending; you type in the chat window on the PC.",
  resume: "Resume",
  stop: "Stop",
  offer_title: "An offer is waiting for your answer",
  offer_note:
    "Accepting is done only on the approval card, which shows the exact reply. Nothing is " +
    "accepted before you approve it.",
  offer_card_no: "The card was not approved: nothing was accepted. Choose what to do next.",
  decline: "Decline",
  say_else: "Say something else",
  say_send: "Send",
  say_note:
    "Your words go through the same check as Jarvis's. To accept, approve the card instead.",
  holding: "Jarvis told the agent \"One moment please\" {holds} of {most} times.",
  queue_line: "In the queue: number {position}",
  queue_waiting: "Waiting in the queue",
  waiting_for_chat:
    "Open the chat on the company's help page in the window on the PC (its Chat or Help " +
    "button). Jarvis starts once it shows.",
  agent_line: "Talking with {agent}",
  question_title: "Handed to you",
  question_note:
    "Jarvis never answers this. Answer it yourself in the chat window on the PC, then press " +
    "Resume - or Stop.",
  transcript_title: "The chat",
  outside_note:
    "The company's words are outside text: shown here, never learned from, never read aloud.",
  who_jarvis: "You (sent by Jarvis)",
  who_owner: "You",
  who_button: "You pressed",
  summary_title: "What happened",
  summary_note: "Written on this PC from the chat, so it is outside text too.",
  agreed_title: "What they agreed to",
  open_title: "Still open",
  reference_line: "Reference number: {reference}",
  saved_yes: "Kept in your encrypted chat history on the PC.",
  saved_no: "Not kept in your chat history: {why}",
  export: "Export transcript",
  export_note:
    "This file is NOT encrypted: anyone who can open it can read the whole chat, with the " +
    "details you allowed. Keep it somewhere safe, or delete it when you no longer need it.",
  export_pc_only: "Export transcript is on the PC only.",
  hidden: "The chat and your details are hidden until you confirm it is you.",
  gone:
    "That chat is gone from the screen: Jarvis on the PC restarted. The encrypted chat " +
    "history keeps a copy.",
  missing:
    "Your PC's Jarvis cannot chat with customer support yet - run apply-patches.ps1 on the PC.",
  version: "Version",
  notify_running: "Chat with {company}: {used} of {max} messages",
  notify_offer: "Chat with {company}: offer waiting",
  notify_waiting: "Waiting for your yes to chat with {company}",
  notify_paused: "Paused: chat with {company}",
  notify_locked: "Jarvis is chatting with customer support for you.",
};

/** The states in which a support chat is still going. */
export const LIVE = new Set(["asking", "approved", "running", "paused"]);

/** How often the card reads again while a chat is going. */
export const POLL_MS = 4000;

/** The most detail rows, and their lengths (jarvis_support's). */
export const MAX_DETAILS = 12;
export const MAX_NAME = 40;
export const MAX_VALUE = 200;
export const MAX_GOAL = 1000;

/** What each state is called on screen. */
export const STATE_WORDS = {
  asking: "Waiting for your yes on the approval card.",
  approved: "Approved - starting.",
  running: "Chatting now.",
  paused: "Paused.",
  done: "Finished.",
  stopped: "Stopped.",
  refused: "Not started.",
};

const text = (v) => (typeof v === "string" ? v.trim() : "");
const num = (v, d = 0) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : null);
const list = (v) => (Array.isArray(v) ? v : []);

function readTurn(t) {
  const o = obj(t);
  if (!o) return null;
  const who = ["jarvis", "owner", "company", "system", "note"].includes(o.who) ? o.who : "";
  if (!who) return null;
  return {
    who,
    text: typeof o.text === "string" ? o.text : "",
    // Belt and braces: anything from the company's side is outside text,
    // whatever the flag says.
    outside: who === "company" || who === "system" || o.outside_text === true,
    button: o.button === true,
    move: text(o.move),
  };
}

function readOffer(o) {
  const x = obj(o);
  if (!x || typeof x.id !== "number") return null;
  return {
    id: x.id,
    words: typeof x.words === "string" ? x.words : "",
    reply: typeof x.reply === "string" ? x.reply : "",
    state: text(x.state),
    // "waiting" (the card is up), "no" (the card was not approved), "yes".
    card: text(x.card) || "waiting",
    holds: num(x.holds),
    holdsMost: num(x.holds_most, 3),
    said: text(x.said),
    choice: text(x.choice),
  };
}

function readSummary(s) {
  const o = obj(s);
  if (!o) return null;
  return {
    answer: text(o.answer),
    agreed: list(o.agreed).map(text).filter(Boolean),
    open: list(o.open).map(text).filter(Boolean),
    reference: text(o.reference),
    byModel: o.by_model === true,
  };
}

/** One support chat as the PC described it, or null. */
export function readChat(s) {
  const o = obj(s);
  if (!o || typeof o.id !== "string" || typeof o.state !== "string") return null;
  return {
    id: o.id,
    company: text(o.company),
    companyName: text(o.company_name) || "the company",
    helpUrl: text(o.help_url),
    goal: typeof o.goal === "string" ? o.goal : "",
    details: list(o.details).map(obj).filter(Boolean)
      .map((d) => ({ name: text(d.name), value: typeof d.value === "string" ? d.value : "" }))
      .filter((d) => d.name),
    state: o.state,
    live: LIVE.has(o.state),
    tierName: text(o.tier_name),
    used: num(o.messages_used),
    max: num(o.max_messages),
    minutesUsed: num(o.minutes_used),
    maxMinutes: num(o.max_minutes),
    queueMinutes: num(o.queue_minutes),
    maxQueue: num(o.max_queue_minutes),
    inQueue: o.in_queue === true,
    queuePosition: typeof o.queue_position === "number" ? o.queue_position : null,
    agent: text(o.agent),
    waitingForChat: o.waiting_for_chat === true,
    // The PC keeps the last pause's words after a stop; shown only while it
    // is really paused.
    paused: o.state === "paused" ? text(o.paused) : "",
    pausedCode: o.state === "paused" ? text(o.paused_code) : "",
    takeOver: o.take_over === true,
    ended: text(o.ended),
    question: text(o.question),
    problem: text(o.problem),
    offer: o.state === "running" ? readOffer(o.offer) : null,
    reference: text(o.reference),
    summary: readSummary(o.summary),
    saved: text(o.saved),
    terms: text(o.terms),
    transcript: list(o.transcript).map(readTurn).filter(Boolean),
    hidden: o.hidden === true,
  };
}

/**
 * GET /api/chatbot/status as the support card's view, or `{available:
 * false, why}` for a PC without support chats (no `companies`) or anything
 * unreadable.
 */
export function readSupport(body) {
  const o = obj(body);
  if (!o || o.available === false || !Array.isArray(o.companies) || !obj(o.support_tier)) {
    return { available: false, why: text(o && o.why) || WORDS.missing };
  }
  const t = o.support_tier;
  return {
    available: true,
    companies: o.companies.map(obj).filter((c) => c && typeof c.id === "string").map((c) => ({
      id: c.id,
      name: text(c.name) || c.id,
      host: text(c.host),
      helpUrl: text(c.help_url),
      terms: text(c.terms),
      // "other": the owner types the help page's address.
      typed: c.id === "other",
    })),
    tier: {
      id: text(t.id),
      name: text(t.name),
      words: text(t.words),
      messagesDefault: num(t.messages_default, 15),
      messagesMax: num(t.messages_max, 25),
      minutesDefault: num(t.minutes_default, 30),
      minutesMax: num(t.minutes_max, 45),
      queueDefault: num(t.queue_default, 45),
      queueMax: num(t.queue_max, 120),
    },
    chat: readChat(o.support),
  };
}

/** "Version: the limited version (one graphics card) - basic chats; ..." */
export function versionLine(view) {
  if (!view || !view.available || !view.tier.name) return "";
  return `${WORDS.version}: ${view.tier.name}` + (view.tier.words ? ` - ${view.tier.words}` : "");
}

/** A limit typed, or null when it is not 1 to `most`. */
export function limitOf(value, most) {
  const s = String(value == null ? "" : value).trim();
  if (!/^\d{1,3}$/.test(s)) return null;
  const n = Number(s);
  return n >= 1 && n <= most ? n : null;
}

/** The detail rows typed, tidied: blank rows dropped, names' spaces collapsed. */
export function detailRows(rows) {
  return list(rows).map((r) => ({
    name: String((r && r.name) || "").split(/\s+/).filter(Boolean).join(" "),
    value: String((r && r.value) || "").trim(),
  })).filter((r) => r.name || r.value);
}

/** What is wrong with the form, in a sentence, or "" when it can be sent. */
export function formProblem(view, { company, address, goal, rows, messages, minutes, queue }) {
  if (!view || !view.available) return WORDS.missing;
  const co = view.companies.find((c) => c.id === company);
  if (!co) return "Choose a company.";
  if (co.typed && !/^https:\/\/[^\s/]+\.[^\s/]+/i.test(String(address || "").trim())) {
    return "Type the company's help page, starting with https://";
  }
  const g = String(goal || "").trim();
  if (!g) return "Say what Jarvis should get done.";
  if (g.length > MAX_GOAL) return `The goal is longer than ${MAX_GOAL} characters.`;
  const d = detailRows(rows);
  if (d.length > MAX_DETAILS) return `At most ${MAX_DETAILS} details.`;
  for (const r of d) {
    if (!r.name) return "Every detail needs a name, like \"Order number\".";
    if (!r.value) return `The detail "${r.name}" has no value.`;
    if (r.name.length > MAX_NAME) return `A detail's name is longer than ${MAX_NAME} characters.`;
    if (r.value.length > MAX_VALUE) return `The detail "${r.name}" is longer than ${MAX_VALUE} characters.`;
  }
  if (limitOf(messages, view.tier.messagesMax) === null) {
    return `Most messages: 1 to ${view.tier.messagesMax} in this version.`;
  }
  if (limitOf(minutes, view.tier.minutesMax) === null) {
    return `Most minutes of chat: 1 to ${view.tier.minutesMax} in this version.`;
  }
  if (limitOf(queue, view.tier.queueMax) === null) {
    return `Most minutes in the queue: 1 to ${view.tier.queueMax}.`;
  }
  return "";
}

/** The buttons for a chat, in order. Stop is always there while it is going. */
export function actionsOf(c) {
  if (!c || !c.live) return [];
  if (c.state === "paused") return ["resume", "stop"];
  if (c.state === "running") return ["take_over", "stop"];
  return ["stop"];
}

/** The offer's buttons (other than the card itself), while one is waiting. */
export function offerActions(c) {
  return c && c.offer && c.offer.state === "waiting" ? ["decline", "say_else", "take_over"] : [];
}

/** The chat's status line: the PC's own words when it has them. */
export function statusLine(c) {
  if (!c) return "";
  if (c.state === "paused" && c.paused) return c.paused;
  if (!c.live && c.ended) return c.ended;
  if (c.state === "running") {
    if (c.waitingForChat) return WORDS.waiting_for_chat;
    if (c.inQueue) {
      return c.queuePosition != null
        ? WORDS.queue_line.replace("{position}", String(c.queuePosition)) : WORDS.queue_waiting;
    }
    if (c.agent) return WORDS.agent_line.replace("{agent}", c.agent);
  }
  return STATE_WORDS[c.state] || c.state;
}

/** The phone's ongoing notification line; the desktop uses it as the card's heading. */
export function talkingLine(c) {
  if (!c || !c.live) return "";
  const fill = (w) => w.replace("{company}", c.companyName).replace("{used}", String(c.used))
    .replace("{max}", String(c.max));
  if (c.state === "asking") return fill(WORDS.notify_waiting);
  if (c.state === "paused") return fill(WORDS.notify_paused);
  if (c.offer) return fill(WORDS.notify_offer);
  return fill(WORDS.notify_running);
}

/** "Message 2 of 15 · 1.5 of 30 minutes · 0.4 of 45 minutes in the queue". */
export function progressLine(c) {
  if (!c) return "";
  return `Message ${c.used} of ${c.max} · ${c.minutesUsed} of ${c.maxMinutes} minutes · ` +
    `${c.queueMinutes} of ${c.maxQueue} minutes in the queue`;
}

/** "Jarvis told the agent ... 1 of 3 times." while an offer card waits, or "". */
export function holdingLine(c) {
  if (!c || !c.offer || !c.offer.holds) return "";
  return WORDS.holding.replace("{holds}", String(c.offer.holds))
    .replace("{most}", String(c.offer.holdsMost));
}

/** Who a line of the chat is from, as shown. */
export function whoOf(t, c) {
  if (!t) return "";
  if (t.who === "jarvis") return t.button ? WORDS.who_button : WORDS.who_jarvis;
  if (t.who === "owner") return WORDS.who_owner;
  if (t.who === "note") return "Note";
  return (c && c.companyName) || "The company";
}

/** "Kept in your encrypted chat history on the PC." or why not; "" before the end. */
export function savedLine(c) {
  if (!c || !c.saved) return "";
  return c.saved === "yes" ? WORDS.saved_yes : WORDS.saved_no.replace("{why}", c.saved);
}
