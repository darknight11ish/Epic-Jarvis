/**
 * Brain -> History -> "Forget a time frame": the page (the owner's decision
 * of 2026-09-28; JARVIS-API.md section 64). forget-range.js holds the words
 * and the reading; this draws them into `#forget-range` and sends the
 * owner's taps through two Rust commands (brain/forget_range.rs):
 * `forget_range_read` (the status, or the list for some days) and
 * `forget_range_write` ("forget" - the PC raises ONE card - the second yes
 * "confirm", or "undo").
 *
 * The two yeses (owner, 2026-11-04): "Forget these" asks the PC for the ONE
 * approval card and changes nothing; approving the card makes the PC HOLD the
 * checked items for two minutes, and the status then carries `confirm`. This
 * page draws that as one more line and one more tap ("Yes, forget them"),
 * which sends the held id and a literal `yes: true`. Nothing on this page
 * approves a card - the card is answered in the Jarvis bar, like any other.
 *
 * Kept out of brain.js on purpose, so the History tab's other cards and this
 * one never edit the same lines. brain.js only calls `showForgetRange()`
 * when the History tab is shown, and `openForgetRange()` when the Jarvis bar
 * asked for it ("forget what you learned last week").
 *
 * Rules this page keeps:
 * - Everything the PC wrote reaches the page as text (`textContent`).
 * - Nothing is removed from here: "Forget these" only asks the PC, which
 *   raises ONE approval card listing every item, answered in the Jarvis
 *   bar like any other. This page never approves anything.
 * - The pinned chats the PC is keeping are drawn as KEPT: no tick box, never
 *   in the count on "Forget these", and never in what it sends.
 * - "Forget these" and the second yes are greyed while the link is stale or
 *   down (rule 4; Rust refuses them too) and while the list is hidden (the
 *   owner must be able to read what goes). Undo is never greyed: it only puts
 *   back.
 * - A 409 from either step is said in the PC's own words, never swallowed -
 *   and the status is read again straight after it, because a 409 means the
 *   card, the hold or the Undo has moved on.
 * - Hidden with the Brain's private lists, with Show.
 *
 * @module forget-range-panel
 */

import { announce, currentLink, linkWords, onLink, onQueue } from "./jarvis-link.js";
import { tellChatsGone } from "./chat-history.js";
import {
  allTicked,
  BRAIN_PLACE_KEY,
  chatKindTag,
  confirmBody,
  EXTRA,
  HISTORY_CHANGED,
  HISTORY_PLACE,
  dayOf,
  fill,
  forgetBody,
  forgetLabel,
  holdLeftLine,
  isWhen,
  messagesLine,
  pinnedKeptLine,
  PLACE,
  readPreview,
  readStatus,
  undoLine,
  WORDS,
} from "./forget-range.js";

const TAURI = globalThis.__TAURI__;

const state = {
  status: null,
  preview: null,
  /** "fact:<id>" / "chat:<id>" still ticked. */
  ticked: new Set(),
  /** "custom" or a preset id. */
  choice: "last_week",
  from: "",
  to: "",
  kinds: new Set(["facts", "chats"]),
  /** The spoken request already used to fill the form (its id). */
  askedSeen: "",
  askedSaid: "",
  error: "",
  said: "",
  saidTone: "",
  reading: false,
  /** The 20-second re-read while an Undo or a held second yes is open. */
  tickTimer: null,
};

/** Buttons that send a change and wait for a live link. */
const live = new Set();

async function invoke(command, args = {}) {
  const core = globalThis.__TAURI__ && globalThis.__TAURI__.core;
  if (!core || !core.invoke) return null;
  return core.invoke(command, args);
}

const errorText = (error) => String((error && error.message) || error || "Something went wrong.");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function canAct() {
  return linkWords(currentLink()).canAct;
}

function syncLive(node) {
  const ok = canAct();
  node.disabled = !ok || node.dataset.busy === "true" || node.dataset.off === "true";
  node.title = ok ? node.dataset.title || "" : WORDS.stale;
}

function syncAllLive() {
  for (const n of live) {
    if (!n.isConnected) live.delete(n);
    else syncLive(n);
  }
}

function button(label, onClick, { isLive = false, danger = false, id = "" } = {}) {
  const b = el("button", `btn small${danger ? " danger" : ""}`, label);
  b.type = "button";
  if (id) b.id = id;
  if (isLive) {
    live.add(b);
    syncLive(b);
  }
  b.addEventListener("click", async () => {
    b.dataset.busy = "true";
    b.disabled = true;
    try {
      await onClick();
    } finally {
      b.dataset.busy = "false";
      if (isLive) syncLive(b);
      else b.disabled = false;
    }
  });
  return b;
}

function root() {
  return document.getElementById("forget-range");
}

function say(message, tone = "") {
  state.said = String(message || "");
  state.saidTone = tone;
  const line = document.getElementById("forget-range-said");
  if (line) {
    line.textContent = state.said;
    line.dataset.tone = tone;
  }
  if (state.said) announce(state.said, tone === "bad" ? "assertive" : "polite");
}

/* ── Reading ──────────────────────────────────────────────────────────── */

/** What the last status said about removals - when it changes (a card
 *  approved, an Undo, the ten minutes over), History's list is read again
 *  (the chat audit, 2026-09-28: it used to wait for its 15-second re-read). */
let removalSeen = "";
/** The chats on the card now waiting, for the Jarvis bar once approved. */
let pendingChats = [];

function removalMark(s) {
  if (!s) return "";
  const last = s.last ? `${s.last.outcome}` : "";
  const undo = s.undo ? `${s.undo.chats}/${s.undo.facts}` : "";
  return `${last}|${undo}`;
}

async function readStatusNow() {
  try {
    state.status = readStatus(await invoke("forget_range_read", {}));
    state.error = "";
  } catch (error) {
    state.error = errorText(error);
  }
  const mark = removalMark(state.status);
  if (mark !== removalSeen) {
    const first = removalSeen === "";
    removalSeen = mark;
    if (!first) window.dispatchEvent(new CustomEvent(HISTORY_CHANGED));
    // Approved: the chats on the card are gone - the Jarvis bar, if it is
    // in one of them, starts a new chat and says so (the chat audit).
    const last = state.status && state.status.last;
    if (!first && last && last.outcome === "done" && pendingChats.length) {
      tellChatsGone(pendingChats);
      pendingChats = [];
    }
  }
  const a = state.status && state.status.asked;
  if (a && a.id && a.id !== state.askedSeen) {
    // "forget what you learned last week", said or typed: the days are
    // filled in and the list read - nothing more.
    state.askedSeen = a.id;
    state.askedSaid = a.said;
    state.choice = "custom";
    state.from = a.from;
    state.to = a.to;
    state.kinds = new Set(a.kinds.length ? a.kinds : ["facts", "chats"]);
    await readPreviewNow();
  }
}

function previewArgs() {
  const kinds = ["facts", "chats"].filter((k) => state.kinds.has(k));
  if (state.choice !== "custom") return { preview: true, preset: state.choice, kinds };
  return { preview: true, from: state.from, to: state.to, kinds };
}

/**
 * Reads the list for the chosen days.
 *
 * `keepSaid`: leave the status line alone. Reading the list normally starts a
 * fresh one (the old "the list changed" no longer applies), but when the page
 * has just said the PC's own answer - a refusal, "Put back", "Forgot 2 facts" -
 * re-reading the list must not wipe the very sentence the owner needs to read
 * (a 409's "read the list again" was being erased by doing exactly that).
 */
async function readPreviewNow({ keepSaid = false } = {}) {
  if (state.choice === "custom" && !(isWhen(state.from) && isWhen(state.to))) {
    say(WORDS.bad_date, "bad");
    return;
  }
  if (!state.kinds.size) {
    say("Choose what Jarvis learned, chats, or both.", "bad");
    return;
  }
  // What the owner unticked stays unticked when the list is read again
  // (after a card, an Undo, or "the list changed"); anything new is ticked -
  // except a customer-support record, which stays as the owner left it: a
  // support chat they ticked stays ticked (the chat audit, 2026-09-28).
  const had = state.preview && state.preview.available ? allTicked(state.preview) : null;
  const unticked = had ? [...had].filter((k) => !state.ticked.has(k)) : [];
  const tickedExtra = had ? [...state.ticked].filter((k) => !had.has(k)) : [];
  try {
    state.preview = readPreview(await invoke("forget_range_read", previewArgs()));
    state.ticked = state.preview.available ? allTicked(state.preview) : new Set();
    for (const k of unticked) state.ticked.delete(k);
    if (state.preview.available) {
      const listed = new Set(state.preview.chats.map((x) => `chat:${x.id}`));
      for (const k of tickedExtra) if (listed.has(k)) state.ticked.add(k);
    }
    if (!keepSaid) say("");
  } catch (error) {
    state.preview = null;
    say(errorText(error), "bad");
  }
}

/** Reads the status again, then draws. */
export async function showForgetRange() {
  if (state.reading) return;
  state.reading = true;
  try {
    await readStatusNow();
  } finally {
    state.reading = false;
  }
  paint();
}

/**
 * The Jarvis bar asked for this place (main.js left it under
 * BRAIN_PLACE_KEY after "forget what you learned last week"). Taken once
 * and only while fresh; returns whether it was ours, so brain.js can show
 * the History tab first.
 */
export function takePlace(freshMs = 60_000) {
  return takeAnyPlace(freshMs) === PLACE;
}

/**
 * The place the Jarvis bar left (PLACE, or HISTORY_PLACE for "Earlier
 * chats"), taken once and only while fresh; "" for none.
 */
export function takeAnyPlace(freshMs = 60_000) {
  let left = null;
  lastLeft = null;
  try {
    left = JSON.parse(localStorage.getItem(BRAIN_PLACE_KEY) || "null");
    if (left) localStorage.removeItem(BRAIN_PLACE_KEY);
  } catch {
    return "";
  }
  if (!left || Date.now() - Number(left.at) >= freshMs) return "";
  // "topics": "switch off my work topic" (topics.js TOPICS_PLACE) - the
  // picker for `topic_id`, a whole number checked again by the Brain.
  // "tutorials": the Set up Jarvis card's own "Read the FAQ"
  // (first-run-settings.js), which leaves this place and then opens the Brain -
  // the same one Help destination the palette's Help row uses (tutorials.js
  // TUTORIALS_PLACE). Named here as a literal, the way "topics" is, so this
  // file does not import the tutorials panel to learn one word.
  if (left.place === PLACE || left.place === HISTORY_PLACE || left.place === "topics"
      || left.place === "tutorials") {
    lastLeft = left;
    return left.place;
  }
  return "";
}

/** What the place was left with, taken once: the History place can carry
 *  `file_under` (a tag id) and `history_q` (search words) for "label my chat
 *  about the boiler as Home" (docs/CHAT-TAGS-DESIGN.md). Null when the last
 *  [takeAnyPlace] left nothing extra, or it was already taken. */
export function takePlaceExtras() {
  const left = lastLeft;
  lastLeft = null;
  return left;
}
let lastLeft = null;

/** After the History tab is shown for the Jarvis bar's request. */
export async function openForgetRange() {
  await showForgetRange();
  const card = document.getElementById("forget-range-card");
  if (card) {
    card.scrollIntoView({ block: "start" });
    const h = card.querySelector("h2");
    if (h) {
      if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
      h.focus({ preventScroll: true });
    }
  }
}

/* ── Changing ─────────────────────────────────────────────────────────── */

async function forgetNow() {
  const p = state.preview;
  if (!p || !p.available || p.hidden) return;
  const body = forgetBody(p, state.ticked);
  if (!body.facts.length && !body.chats.length) {
    say(WORDS.none_ticked, "bad");
    return;
  }
  try {
    const out = await invoke("forget_range_write", { action: "forget", body });
    pendingChats = body.chats.slice();
    say(String((out && out.message) || WORDS.waiting), "ok");
  } catch (error) {
    say(errorText(error), "bad");
    // The list changed since it was read: read it again, without wiping the
    // refusal that says so.
    if (/list changed/i.test(errorText(error))) await readPreviewNow({ keepSaid: true });
  }
  await readStatusNow();
  paint();
}

async function undoNow() {
  try {
    const out = await invoke("forget_range_write", { action: "undo" });
    say(String((out && out.message) || "Put back."), "ok");
  } catch (error) {
    say(errorText(error), "bad");
  }
  await readStatusNow();
  // The list under an Undo is read again - quietly, so "Put back: 2 facts and
  // 2 chats." stays on the page.
  if (state.preview && state.preview.available) await readPreviewNow({ keepSaid: true });
  paint();
}

/**
 * The SECOND yes: the id the PC is holding and a literal `true` (the card was
 * the first yes and deleted nothing). Its answer is the PC's own sentence -
 * `Forgot 2 facts and deleted 2 chats. Undo is available for 10 minutes.` -
 * and a refusal is the PC's own too: no hold, an expired hold, items that
 * changed, a card still waiting, or an Undo already open. Nothing is
 * swallowed, and the status is read again after either, so the line, the
 * second yes and the Undo banner always say what the PC actually holds.
 */
async function confirmNow() {
  const c = state.status && state.status.confirm;
  if (!c) return;
  try {
    const out = await invoke("forget_range_write", {
      action: "confirm",
      body: confirmBody(c.id),
    });
    say(String((out && out.message) || ""), "ok");
  } catch (error) {
    say(errorText(error), "bad");
  }
  await readStatusNow();
  // Quietly: the PC's sentence stays, and a 409's "read the list again" is
  // what the re-read is for - not something to erase while doing it.
  if (state.preview && state.preview.available) await readPreviewNow({ keepSaid: true });
  paint();
}

/* ── Drawing ──────────────────────────────────────────────────────────── */

/**
 * While an Undo or a held second yes is open: the minutes left, and the
 * moment it ends. Only that line is redrawn while it lasts, so a date being
 * typed or a box being ticked is not disturbed; the whole card only when it
 * is over. Both clocks are the PC's - this only asks it again.
 */
function scheduleTicks() {
  clearTimeout(state.tickTimer);
  state.tickTimer = null;
  const s = state.status;
  if (!(s && (s.undo || s.confirm))) return;
  state.tickTimer = setTimeout(async () => {
    state.tickTimer = null;
    const box = root();
    if (!box || box.closest("[hidden]")) {
      scheduleTicks();
      return;
    }
    await readStatusNow();
    const now = state.status;
    if (now && now.undo) {
      const line = box.querySelector(".fr-undo-text");
      if (line) line.textContent = undoLine(now.undo);
      scheduleTicks();
    } else if (now && now.confirm) {
      const left = box.querySelector(".fr-confirm-left");
      if (left) left.textContent = holdLeftLine(now.confirm);
      scheduleTicks();
    } else {
      paint();
    }
  }, 20_000);
}

function paint() {
  const box = root();
  if (!box) return;
  live.clear();
  const out = [];
  const s = state.status;
  if (!s) {
    out.push(el("p", "empty", state.error ? `Could not read it: ${state.error}.` : "Reading…"));
  } else if (!s.available) {
    out.push(el("p", "empty", s.why));
  } else {
    if (s.undo) out.push(undoBanner(s.undo));
    if (s.waiting) out.push(el("p", "hint fr-waiting", WORDS.waiting));
    else if (s.confirm) out.push(confirmBlock(s.confirm));
    else if (s.last && s.last.message && !s.undo && s.last.outcome !== "done") {
      out.push(el("p", "fr-last", s.last.message));
    }
    out.push(form(s));
    out.push(listPart(s));
  }
  const said = el("p", "fr-said", state.said);
  said.id = "forget-range-said";
  said.setAttribute("role", "status");
  said.dataset.tone = state.saidTone;
  out.push(said);
  box.replaceChildren(...out);
  scheduleTicks();
}

/**
 * The second yes the PC is holding: its own sentence, how long is left, and
 * one danger button. Not a card - nothing here approves or denies anything.
 */
function confirmBlock(c) {
  const box = el("div", "fr-confirm");
  box.append(el("p", "fr-confirm-text", c.text || EXTRA.confirm_text));
  box.append(el("p", "fr-confirm-left", holdLeftLine(c)));
  const go = button(EXTRA.confirm_yes, confirmNow, { isLive: true, danger: true,
    id: "forget-range-confirm" });
  go.dataset.title = "Forgets the facts and deletes the chats you ticked. Undo stays for 10 " +
    "minutes.";
  const end = el("div", "row end");
  end.append(go);
  box.append(end);
  return box;
}

function undoBanner(undo) {
  const bar = el("div", "fr-undo");
  bar.append(el("span", "fr-undo-text", undoLine(undo)));
  const b = button(WORDS.undo, undoNow, { id: "forget-range-undo" });
  b.title = "Puts back every fact and chat this removed. No card.";
  bar.append(b);
  return bar;
}

function form(s) {
  const f = el("div", "fr-form");
  if (state.askedSaid && state.choice === "custom") {
    f.append(el("p", "note fr-asked", fill(WORDS.asked, { said: state.askedSaid })));
  }
  const row = el("div", "row fr-row");
  const pick = document.createElement("select");
  pick.className = "field";
  pick.id = "forget-range-choice";
  for (const p of s.presets) {
    const o = el("option", "", p.label);
    o.value = p.id;
    pick.append(o);
  }
  const custom = el("option", "", WORDS.custom);
  custom.value = "custom";
  pick.append(custom);
  pick.value = state.choice;
  const pickLabel = el("label", "lbl");
  pickLabel.append(el("span", "", "Days"), pick);
  row.append(pickLabel);

  const dates = el("div", "row fr-dates");
  const date = (id, label, value, onSet) => {
    const box = el("label", "lbl");
    const input = document.createElement("input");
    input.type = "date";
    input.className = "field";
    input.id = id;
    input.value = dayOf(value);
    input.title = WORDS.date_hint;
    input.addEventListener("change", () => {
      onSet(input.value);
      state.choice = "custom";
      state.askedSaid = "";
      pick.value = "custom";
    });
    box.append(el("span", "", label), input);
    return box;
  };
  dates.append(date("forget-range-from", WORDS.from, state.from, (v) => { state.from = v; }),
    date("forget-range-to", WORDS.to, state.to, (v) => { state.to = v; }));
  dates.hidden = state.choice !== "custom";
  pick.addEventListener("change", () => {
    state.choice = pick.value;
    state.askedSaid = "";
    dates.hidden = state.choice !== "custom";
  });

  const kinds = el("fieldset", "fr-kinds");
  kinds.append(el("legend", "", WORDS.kinds));
  for (const [k, label] of [["facts", WORDS.kind_facts], ["chats", WORDS.kind_chats]]) {
    const l = el("label", "check");
    const c = document.createElement("input");
    c.type = "checkbox";
    c.id = `forget-range-kind-${k}`;
    c.checked = state.kinds.has(k);
    c.addEventListener("change", () => {
      if (c.checked) state.kinds.add(k);
      else state.kinds.delete(k);
    });
    l.append(c, el("span", "", label));
    kinds.append(l);
  }
  const go = button(WORDS.show, async () => {
    await readPreviewNow();
    paint();
  }, { id: "forget-range-show" });
  row.append(go);
  f.append(row, dates, kinds);
  return f;
}

function listPart(s) {
  const p = state.preview;
  const part = el("div", "fr-list");
  if (!p) return part;
  if (!p.available) {
    part.append(el("p", "empty", p.why));
    return part;
  }
  part.append(el("p", "fr-frame", p.said));
  if (p.hidden) {
    part.append(hiddenNode(p));
    return part;
  }
  if (p.empty) return part;
  // A LARGE selection is said in the PC's own words BEFORE anything is sent
  // (owner's 2026-11-08 ruling: no cap, but a big wipe keeps the two yesses).
  if (p.largeWipe) {
    const warn = el("p", "fr-large-wipe", p.largeWords || "This is a large wipe.");
    warn.setAttribute("role", "status");
    part.append(warn);
  }
  if (p.chatsWhy) part.append(el("p", "empty failed", p.chatsWhy));
  // The chats this Forget is KEEPING (owner, 2026-11-04). Above the tickable
  // lists on purpose: the owner sees what stays before what goes. Nothing
  // here is a tick box and nothing here is ever sent.
  if (p.pinnedKept.length) {
    part.append(el("h3", "fr-head",
      pinnedKeptLine(p.pinnedKeptCount || p.pinnedKept.length)));
    part.append(el("p", "note fr-pinned-why", EXTRA.pinned_why));
    const rows = el("div", "rows");
    for (const x of p.pinnedKept) rows.append(keptRow(x));
    part.append(rows);
  }
  if (p.kinds.includes("facts") && p.facts.length) {
    part.append(el("h3", "fr-head", `${WORDS.facts_head} (${p.facts.length})`));
    part.append(el("p", "note", WORDS.erase_note));
    const rows = el("div", "rows");
    for (const x of p.facts) rows.append(item(`fact:${x.id}`, x.text, x.label, [
      x.pinned ? WORDS.pinned : "", x.betweenUs ? WORDS.between_us : ""].filter(Boolean)));
    part.append(rows);
  }
  if (p.kinds.includes("chats") && p.chats.length) {
    part.append(el("h3", "fr-head", `${WORDS.chats_head} (${p.chats.length})`));
    const rows = el("div", "rows");
    for (const x of p.chats) {
      rows.append(item(`chat:${x.id}`, x.title, x.label, [chatKindTag(x.kind)].filter(Boolean),
        [x.kind === "support" ? WORDS.support : "", x.spills ? WORDS.spills : ""]
          .filter(Boolean).join(" ")));
    }
    part.append(rows);
  }
  // How long it takes, measured by the PC from the counts just read, said
  // BEFORE the owner is asked for the card (owner, 2026-11-04).
  if (p.estimate.text) part.append(el("p", "fr-estimate", p.estimate.text));
  const n = forgetBody(p, state.ticked);
  const count = n.facts.length + n.chats.length;
  const go = button(forgetLabel(count), forgetNow, { isLive: true, danger: true,
    id: "forget-range-go" });
  go.dataset.title = p.largeWipe
    ? "Asks you first, with ONE approval card listing everything ticked - this is a "
      + "large wipe, so you will be asked to say yes a second time after the card."
    : "Asks you first, with ONE approval card listing everything ticked.";
  if (!count || s.waiting || s.confirm || s.undo) {
    go.dataset.off = "true";
    syncLive(go);
  }
  const end = el("div", "row end");
  end.append(go);
  part.append(end);
  return part;
}

/**
 * One pinned chat, drawn as KEPT: a title and its message count, no check box
 * and no tap - there is nothing here to tick or untick.
 */
function keptRow(x) {
  const row = el("div", "row-item fr-item fr-kept");
  const body = el("span", "row-main");
  body.append(el("span", "row-title", x.title));
  body.append(el("span", "row-meta", messagesLine(x.messages)));
  row.append(body);
  return row;
}

/** Keeps "Forget these" in step with the ticks: its count, and whether the PC
 *  can be asked at all right now (a card waiting, a second yes held, an Undo
 *  open, a stale link). One place, so the two callers cannot drift. */
function syncGo() {
  const go = document.getElementById("forget-range-go");
  const p = state.preview;
  if (!go || !p) return;
  const n = forgetBody(p, state.ticked);
  const count = n.facts.length + n.chats.length;
  const s = state.status || {};
  go.textContent = forgetLabel(count);
  go.dataset.off = !count || s.waiting || s.confirm || s.undo ? "true" : "false";
  syncLive(go);
}

function item(key, main, label, tags, warn = "") {
  const row = el("label", "row-item fr-item");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = state.ticked.has(key);
  box.dataset.key = key;
  box.addEventListener("change", () => {
    if (box.checked) state.ticked.add(key);
    else state.ticked.delete(key);
    syncGo();
  });
  const text = el("span", "row-main");
  text.append(el("span", "row-title", main));
  text.append(el("span", "row-meta", [label, ...tags].join(" · ")));
  if (warn) text.append(el("span", "fr-spills", warn));
  row.append(box, text);
  return row;
}

function hiddenNode(p) {
  const box = el("div", "private-hidden");
  const n = p.counts.facts + p.counts.chats;
  box.append(el("p", "empty", n
    ? `${n} ${n === 1 ? "item" : "items"}, hidden until Windows Hello confirms it is you.`
    : "Hidden until Windows Hello confirms it is you."));
  const show = button("Show", async () => {
    try {
      await invoke("reveal_private_answers");
    } catch (error) {
      say(errorText(error), "bad");
      return;
    }
    await readPreviewNow();
    paint();
  });
  show.title = "Asks Windows Hello - your PIN, fingerprint or face - then shows this list.";
  box.append(show);
  return box;
}

/* ── Wiring ───────────────────────────────────────────────────────────── */

onLink(() => syncAllLive());

// The card this page caused is answered in the Jarvis bar; when the queue
// changes while it waits, read the status again (approved: the Undo shows,
// and the list is read again to show what is left).
let lastQueue = null;
onQueue((queue) => {
  const n = queue && Number.isFinite(queue.count) ? queue.count : null;
  const changed = lastQueue !== null && n !== lastQueue;
  lastQueue = n;
  const visible = root() && !root().closest("[hidden]");
  if (changed && visible && state.status && state.status.waiting) {
    setTimeout(async () => {
      await readStatusNow();
      if (state.preview && state.preview.available && !state.status.waiting) await readPreviewNow();
      paint();
    }, 800);
  }
});

if (TAURI && TAURI.event && TAURI.event.listen) {
  const reread = async () => {
    const box = root();
    if (!box || box.closest("[hidden]")) return;
    if (state.preview) await readPreviewNow();
    paint();
  };
  TAURI.event.listen("security-changed", reread);
  TAURI.event.listen("private-hidden", reread);
}
