/**
 * Chat history on the PC, in the Brain's History tab (JARVIS-API.md section
 * 18; src/history-view.js, brain.js "History", src-tauri/src/brain/history.rs).
 *
 * What must hold (section 4 of the contract, and the rules around it):
 * - a History tab next to Memory: the list, newest first, with "Load older";
 *   each row its title, when, which app, a "voice" mark and a "read outside
 *   text" mark;
 * - open one read-only; where a user turn's words came from is said quietly
 *   when they were not typed or spoken;
 * - delete ONE, after a confirm that says it cannot be undone - and no
 *   "delete all" anywhere;
 * - "Keep chat history on this PC": ON raises a card and shows "Waiting for
 *   your approval" exactly as the learning switch does, until the card
 *   leaves the queue; OFF is immediate; ON is greyed on a stale link;
 * - "Delete conversations older than": Never / 30 days / 90 days / 1 year;
 * - `why_not` said plainly when nothing new is being kept;
 * - "Windows Hello for memory lists and chat history" holds the list back too.
 *
 * The answers are the shapes in the contract (section 3). The backend is
 * built to the same contract in parallel; when its generated fixtures land
 * these can read those instead, as deep.mjs reads big-model-cases.json.
 * Two halves, like deep.mjs: the pure module, then the Brain window in a
 * real browser on the uikit mock. CONTROL checks read the Rust.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  addPage,
  chatFactsHiddenLine,
  chatFactsIntro,
  deleteAndForgetQuestion,
  deleteChatButton,
  deleteDoneWords,
  readChatFacts,
  DELETE_KEEPS_FACTS,
  deleteQuestion,
  deviceTag,
  findCountWords,
  findMatches,
  hitsWords,
  readSearch,
  searchMoreWords,
  TITLES_ONLY,
  NOT_KEPT_LINE,
  keepConfirm,
  keepNeedsConfirm,
  keepReply,
  refreshRows,
  TAINT_TITLE,
  notRecordingLine,
  OFF_REPLY,
  olderThan,
  provenanceWords,
  readConversation,
  readHistory,
  rowMeta,
  SWITCH_DETAIL,
  SWITCH_LABEL,
  whenWords,
  whenLine,
  liveLine,
  messagesWords,
  readKind,
  KIND_TAG,
  KIND_TITLE,
  FILTERS,
  FILTER_LABEL,
  FILTER_NONE,
  CHATBOT_WHO,
  CONTINUE,
  CONTINUE_TITLE,
  CONTINUE_WHY,
  COPY,
  COPY_TITLE,
  COPIED,
  FORGET_RANGE_LINK,
  FORGET_RANGE_LINK_TITLE,
  DELETE_SUPPORT,
  KEEP_SUPPORT_NOTE,
  NO_TITLE,
  SEARCH_LABEL,
} from "../src/history-view.js";
import * as CH from "../src/chat-history.js";
import { GAME_TEMPORARY, temporaryOutcome } from "../src/memory-used.js";
import { ERASED_NO_CHAT, eraseChatNamed } from "../src/auto-learn.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The contract's own examples (section 3) ───────────────────────────── */

const NOW = Math.floor(Date.now() / 1000);
const LIST = {
  enabled: true, recording: true, why_not: "", waiting: false,
  keep_days: 0, encrypted: true,
  conversations: [{ id: "c0nv-phone-0001", title: "Dentist on Tuesday",
    started: NOW - 3600, updated: NOW - 3300, turns: 6, device: "phone",
    has_voice: true, tainted: false }],
};
const CONV = {
  id: "c0nv-phone-0001", title: "Dentist on Tuesday", tainted: false,
  turns: [
    { role: "user", text: "when is the dentist?", at: NOW - 3600, provenance: "typed", read_outside: false },
    { role: "assistant", text: "Tuesday at 3.", at: NOW - 3596 },
  ],
};

/** `n` conversations, one a minute apart, newest first. */
function many(n, extra = () => ({})) {
  return Array.from({ length: n }, (_, i) => ({
    id: `conv-${String(i).padStart(4, "0")}`, title: `Conversation ${i}`,
    started: NOW - 60 * (i + 1) - 30, updated: NOW - 60 * (i + 1), turns: 2,
    device: i % 2 ? "desktop" : "phone", has_voice: false, tainted: false, ...extra(i),
  }));
}

/* ── The pure module ───────────────────────────────────────────────────── */

await check("the contract's list and conversation are read as the PC sends them", async () => {
  const v = readHistory(LIST);
  assert.equal(v.available, true);
  assert.equal(v.enabled, true);
  assert.equal(v.recording, true);
  assert.equal(v.keepDays, 0);
  assert.deepEqual(v.conversations[0], { id: "c0nv-phone-0001", title: "Dentist on Tuesday",
    started: NOW - 3600, updated: NOW - 3300, turns: 6, device: "phone", hasVoice: true, tainted: false,
    kind: "chat", project: null });
  const c = readConversation(CONV);
  assert.equal(c.turns.length, 2);
  assert.equal(c.turns[0].provenance, "typed");
  assert.equal(c.turns[1].provenance, "", "an answer has no provenance");
  // A user turn that says nothing is "unknown", never assumed typed.
  assert.equal(readConversation({ turns: [{ role: "user", text: "x" }] }).turns[0].provenance, "unknown");
  // Jarvis Live's side-talk marker in an older chat: shown as "(not for Jarvis)", never raw.
  assert.equal(readConversation({ turns: [{ role: "assistant", text: "[not for me]" }] }).turns[0].text,
    "(not for Jarvis)");
  // Recording only when the PC says so.
  assert.equal(readHistory({ enabled: true, conversations: [] }).recording, false);
});

await check("the words under a user turn: quiet for typed and voice, said for everything else", async () => {
  assert.equal(provenanceWords("typed"), "");
  assert.equal(provenanceWords("voice"), "");
  assert.equal(provenanceWords("shared"), "shared from another app");
  assert.equal(provenanceWords("pasted"), "pasted");
  assert.equal(provenanceWords("clipboard"), "from clipboard");
  assert.equal(provenanceWords("picture_caption"), "sent with a picture");
  assert.match(provenanceWords("voice_unverified"), /not confirmed/);
  assert.equal(provenanceWords("something new"), "not known where from");
  assert.equal(provenanceWords(undefined), "not known where from");
});

await check("the PC's search answer is read defensively, and find counts every place", async () => {
  const v = readSearch({ query_ok: true, more: true, conversations: [
    { id: "c-1", title: "Dentist", hits: 2, snippet: { role: "assistant", before: true,
      parts: [{ text: "on ", hit: false }, { text: "Mill", hit: true }, { text: 7, hit: true }] } },
    { title: "no id" }] });
  assert.equal(v.available, true);
  assert.equal(v.conversations.length, 1, "a row with no id cannot be opened");
  assert.deepEqual(v.conversations[0].snippet.parts, [{ text: "on ", hit: false }, { text: "Mill", hit: true }]);
  assert.equal(v.conversations[0].snippet.role, "assistant");
  assert.equal(readSearch({ available: false }).why, TITLES_ONLY);
  assert.equal(readSearch({ query_ok: false, why: "Type at least two letters to search what was said.",
    conversations: [] }).queryOk, false);
  assert.match(searchMoreWords(v), /newest matches only/);
  assert.equal(hitsWords(1), "found in 1 message");
  assert.equal(hitsWords(0), "");
  const conv = { turns: [{ text: "Mill Road, then mill road again" }, { text: "no" }, { text: "Road!" }] };
  const m = findMatches(conv, "mill road");
  assert.deepEqual(m.map((x) => [x.turn, conv.turns[x.turn].text.slice(x.start, x.end)]),
    [[0, "Mill"], [0, "Road"], [0, "mill"], [0, "road"], [2, "Road"]]);
  assert.deepEqual(findMatches(conv, "(.*)"), [], "the words are words, not a pattern");
  assert.equal(findCountWords(0, 0), "Not in this chat.");
  assert.equal(findCountWords(0, 1), "1 match");
  assert.equal(findCountWords(2, 5), "3 of 5");
});

await check("paging: the next page goes under, never twice, and asks from the oldest shown", async () => {
  const first = readHistory({ ...LIST, conversations: many(3) }).conversations;
  const moved = { ...first[0] };
  const rows = addPage(first, [moved, ...readHistory({ ...LIST, conversations: many(5) }).conversations.slice(3)]);
  assert.deepEqual(rows.map((r) => r.id), ["conv-0000", "conv-0001", "conv-0002", "conv-0003", "conv-0004"]);
  assert.equal(olderThan(first), NOW - 180);
  assert.equal(olderThan([]), null);
});

await check("why nothing new is kept is the PC's own sentence, and nothing when it is kept", async () => {
  const why = "Chat history is on, but Windows Credential Manager could not be used, so nothing is kept.";
  assert.equal(notRecordingLine(readHistory({ ...LIST, recording: false, why_not: why })), why);
  assert.equal(notRecordingLine(readHistory(LIST)), "");
  assert.match(notRecordingLine(readHistory({ ...LIST, recording: false })), /did not say why/);
  // Off: the switch says so; no second line.
  assert.equal(notRecordingLine(readHistory({ ...LIST, enabled: false, recording: false,
    why_not: "Chat history is off." })), "");
});

await check("a keep change says what it did", async () => {
  assert.equal(keepReply(30, { deleted: 4 }), "Conversations older than 30 days are deleted. 4 were deleted just now.");
  assert.equal(keepReply(365, { deleted: 1 }), "Conversations older than a year are deleted. 1 was deleted just now.");
  assert.match(keepReply(90, { deleted: 0 }), /None were old enough/);
  assert.equal(keepReply(0, {}), "Conversations are kept until you delete them.");
  assert.equal(keepReply(30, { message: "Deleted 2 conversations." }), "Deleted 2 conversations.");
});

await check("the wording is the contract's, word for word (section 5)", async () => {
  assert.equal(SWITCH_LABEL, "Keep chat history on this PC");
  assert.equal(SWITCH_DETAIL, "Your chats, including what you say to Jarvis by voice, are kept on this PC, encrypted. Nothing is sent anywhere.");
  assert.equal(OFF_REPLY, "Chat history is off. Nothing new is kept. What is already kept stays until you delete it.");
  // "messages", never "turns", and the phone's dates (the chat audit, 2026-09-28).
  assert.match(rowMeta({ updated: NOW - 120, turns: 1 }, NOW * 1000),
    /^(Today|Yesterday) \d\d:\d\d · 1 message$/);
});

/* ── The chat audit (2026-09-28): the words and worked examples both apps
      share (tools/gen_history_cases.py -> tests/fixtures/history-cases.json) ── */

const CASES = JSON.parse(read("tests/fixtures/history-cases.json"));

await check("History's new words are the contract's, word for word", async () => {
  const w = CASES.words;
  assert.deepEqual({ ...KIND_TAG }, w.kind_tag);
  assert.deepEqual({ ...KIND_TITLE }, w.kind_title);
  assert.deepEqual(FILTERS.map((f) => [...f]), w.filters);
  assert.equal(FILTER_LABEL, w.filter_label);
  assert.equal(FILTER_NONE, w.filter_none);
  assert.deepEqual({ ...CHATBOT_WHO }, w.chatbot_who);
  assert.equal(CONTINUE, w.continue);
  assert.equal(CONTINUE_TITLE, w.continue_title_desktop);
  assert.deepEqual({ ...CONTINUE_WHY }, w.continue_why);
  assert.equal(COPY, w.copy);
  assert.equal(COPY_TITLE, w.copy_title);
  assert.equal(COPIED, w.copied);
  assert.equal(FORGET_RANGE_LINK, w.forget_range_link);
  assert.equal(FORGET_RANGE_LINK_TITLE, w.forget_range_link_title);
  assert.equal(DELETE_KEEPS_FACTS, w.delete_keeps_facts);
  assert.equal(DELETE_SUPPORT, w.delete_support);
  assert.equal(KEEP_SUPPORT_NOTE, w.keep_support_note);
  assert.equal(NO_TITLE, w.no_title);
  assert.equal(SEARCH_LABEL, w.search_label);
  // The Jarvis bar's words for the chat it is in.
  assert.equal(CH.EARLIER_CHATS, w.earlier_chats);
  assert.equal(CH.EARLIER_CHATS_TITLE, w.earlier_chats_title);
  assert.equal(CH.IDLE_NEW_LINE, w.idle_new);
  assert.equal(CH.CONTINUED_TRIMMED, w.continued_trimmed);
  assert.equal(CH.CONTINUED_TAINTED, w.continued_tainted);
  assert.equal(CH.CONTINUED_NOTHING, w.continued_nothing);
  assert.equal(CH.CONTINUED_TEMPORARY_OFF, w.continued_temporary_off);
  assert.equal(CH.CONTINUE_BUSY, w.continue_busy);
  assert.equal(CH.CHAT_GONE, w.chat_gone);
  assert.equal(CH.MOVED_HERE, w.moved_here);
  assert.equal(CH.ESC_LABEL, w.esc_label);
  assert.equal(CH.ENDED_SAVED, w.ended_saved);
  assert.equal(CH.NEW_CONVERSATION, w.new_conversation);
  assert.equal(CH.continuedLine("Dentist"), w.continued.replace("{title}", "Dentist"));
  assert.equal(CH.threadSummary(1), w.thread_one);
  assert.equal(CH.threadSummary(3), w.thread_many.replace("{n}", "3"));
  assert.equal(CH.IDLE_NEW_MS, CASES.idle_ms);
  assert.equal(CH.MAX_EXCHANGES, CASES.max_exchanges);
  assert.equal(CH.MAX_CHARS, CASES.max_chars);
  // Other screens.
  assert.equal(GAME_TEMPORARY, w.game_temporary);
  assert.equal(ERASED_NO_CHAT, w.erased_no_chat);
  assert.equal(eraseChatNamed({ title: "Dentist" }, "Today 14:05"),
    w.erase_chat_named.replace("{title}", "Dentist").replace("{when}", "Today 14:05"));
  const projects = read("src/projects.js");
  assert.ok(projects.includes(w.project_chats_later), "Projects still promises project chats");
  assert.ok(!projects.includes("Jarvis reads this in this project's chats"));
  const html = read("src/index.html");
  assert.match(html, /<kbd>Esc<\/kbd> end chat/, "the bar still says Esc dismisses");
});

await check("dates, a Live session's line and 'messages' follow the worked examples", async () => {
  const now = CASES.today * 1000;
  for (const c of CASES.when_cases) assert.equal(whenLine(c.at, now, { utc: true }), c.expect, c.at);
  for (const c of CASES.live_cases) {
    assert.equal(liveLine(c.started, c.updated, now, { utc: true }), c.expect);
    assert.equal(rowMeta({ kind: "live", started: c.started, updated: c.updated, turns: 2 }, now,
      { utc: true }), `${c.expect} · 2 messages`);
  }
  for (const c of CASES.messages_cases) assert.equal(messagesWords(c.n), c.expect);
  assert.deepEqual(CASES.kinds, ["chat", "live", "support", "chatbot", "compare"]);
  assert.equal(readKind("imported"), "chat", "an unknown kind is read as a chat");
});

await check("Continue this chat loads the kept messages the worked examples load", async () => {
  for (const c of CASES.continue_cases) {
    const got = CH.continueWindow(c.turns);
    const want = c.window.map((p) => (p.provenance ? p : { question: p.question, answer: p.answer }));
    assert.deepEqual(got.window, want, c.name);
    assert.equal(got.trimmed, c.trimmed, c.name);
  }
  // ...and the same from turns as history-view.js reads them (answerKept).
  const read2 = readConversation({ id: "c1", kind: "chat", turns: [
    { role: "user", text: "skip me", provenance: "typed", answer_kept: false },
    { role: "user", text: "keep me", provenance: "voice" },
    { role: "assistant", text: "Kept." },
  ] });
  assert.deepEqual(CH.continueWindow(read2.turns).window,
    [{ question: "keep me", answer: "Kept.", provenance: "voice" }]);
  assert.equal(read2.continuable, true);
});

await check("an opened record says whether it can be continued, and why not", async () => {
  const sup = readConversation({ id: "s1", kind: "support", continuable: false,
    continue_why: "the PC's own words", turns: [{ role: "support", text: "x", provenance: "support_company" }] });
  assert.equal(sup.continuable, false);
  assert.equal(sup.continueWhy, "the PC's own words");
  const old = readConversation({ id: "o1", turns: [{ role: "chatbot", text: "Gemini: X", provenance: "chatbot_reply" }] });
  assert.equal(old.continuable, false, "an older PC's chatbot record is never continued");
  assert.equal(old.turns[0].provenance, "chatbot_reply");
  const bot = readConversation({ id: "b1", kind: "chatbot", turns: [] });
  assert.equal(bot.continueWhy, CONTINUE_WHY.chatbot);
});

await check("the bar keeps a new conversation after 30 quiet minutes, and never mid-chat", async () => {
  const t0 = 1_000_000;
  assert.equal(CH.idleExpired(t0, t0 + CH.IDLE_NEW_MS - 1, true), false);
  assert.equal(CH.idleExpired(t0, t0 + CH.IDLE_NEW_MS, true), true);
  assert.equal(CH.idleExpired(t0, t0 + CH.IDLE_NEW_MS * 3, false), false, "nothing to start afresh");
  assert.equal(CH.idleExpired(0, t0, true), false, "no finished answer yet");
});

await check("a game the PC made temporary is said so, and only then", async () => {
  assert.equal(temporaryOutcome(false, { temporary: true }), "game");
  assert.equal(temporaryOutcome(false, {}), "");
  assert.equal(temporaryOutcome(true, { temporary: true }), "confirmed");
  assert.equal(temporaryOutcome(true, {}), "unconfirmed");
});

await check("a deleted chat is handed to the Jarvis bar by id only, once", async () => {
  const store = new Map();
  const s = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k) };
  CH.tellChatsGone(["conv-gone-0001", "not an id!"], s);
  assert.deepEqual(JSON.parse(store.get(CH.CHAT_GONE_KEY)).ids, ["conv-gone-0001"]);
  assert.deepEqual(CH.takeChatsGone(s), ["conv-gone-0001"]);
  assert.deepEqual(CH.takeChatsGone(s), [], "read once");
});

/* ── The Brain window ──────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 900 };

async function historyTab(history = {}, extra = {}) {
  const page = await K.open(browser, base, "brain.html", { history, ...extra }, SIZE);
  await page.locator("#tab-history").click();
  await page.waitForTimeout(300);
  return page;
}
const calls = (page, cmd) => page.evaluate((cmd) =>
  window.__calls.filter((c) => c[0] === cmd).map((c) => c[1]), cmd);
const listText = (page) => page.locator("#history-list").innerText();
const settingsText = (page) => page.locator("#history-settings").innerText();

await check("a History tab sits next to Memory and opens its own view", async () => {
  const page = await historyTab({ conversations: LIST.conversations });
  const order = await page.evaluate(() =>
    [...document.querySelectorAll("#rail-nav [role=tab]")].map((t) => t.id).slice(0, 3));
  const shown = await page.locator("#view-history").isVisible();
  const title = await page.locator("#view-title").innerText();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(order, ["tab-memory", "tab-history", "tab-faculties"]);
  assert.equal(shown, true);
  assert.equal(title, "History");
  assert.deepEqual(errors, []);
});

await check("each row: title, when, which app, and the voice and read-outside marks", async () => {
  const convs = [
    ...LIST.conversations,
    { id: "c0nv-desk-0002", title: "Summarise that page", started: NOW - 90000, updated: NOW - 86500,
      turns: 4, device: "desktop", has_voice: false, tainted: true },
  ];
  const page = await historyTab({ conversations: convs });
  const rows = page.locator("#history-list .row-item");
  const first = await rows.nth(0).innerText();
  const second = await rows.nth(1).innerText();
  const tags = await rows.locator(".row-tag").allInnerTexts();
  const taintTitle = await rows.nth(1).locator(".history-mark-taint").getAttribute("title");
  await page.close();
  assert.match(first, /Dentist on Tuesday/);
  assert.match(first, /(Today|Yesterday) \d\d:\d\d · 6 messages/);
  assert.match(first, /voice/);
  assert.doesNotMatch(first, /read outside text/);
  assert.match(second, /Summarise that page/);
  assert.match(second, /read outside text/);
  assert.doesNotMatch(second, /\bvoice\b/);
  assert.deepEqual(tags.map((t) => t.toLowerCase()), ["phone", "pc"]);
  assert.match(taintTitle, /did not come from you/);
});

/* ── "Search what was said" and "Find in this chat" (section 71) ───────── */

const SEARCHED = {
  conversations: [
    { id: "c-1", title: "Dentist on Tuesday", started: NOW - 3600, updated: NOW - 3300, turns: 2, device: "phone" },
    { id: "c-2", title: "Summarise that PDF", started: NOW - 7200, updated: NOW - 7000, turns: 4, device: "desktop" },
    { id: "c-3", title: "Weekend plan", started: NOW - 10800, updated: NOW - 10700, turns: 3, device: "phone" },
  ],
  transcripts: {
    "c-1": { id: "c-1", title: "Dentist on Tuesday", tainted: false, turns: [
      { role: "user", text: "when is the dentist?", at: NOW - 3600, provenance: "typed" },
      { role: "assistant", text: "Tuesday at 3, on Mill Road.", at: NOW - 3596 }] },
    "c-2": { id: "c-2", title: "Summarise that PDF", tainted: true, turns: [
      { role: "user", text: "summarise the lease", at: NOW - 7200, provenance: "typed" },
      { role: "assistant", text: "The lease ends in March.", at: NOW - 7190 }] },
    "c-3": { id: "c-3", title: "Weekend plan", tainted: false, turns: [
      { role: "user", text: "hiking near Mill Road? or the lake", at: NOW - 10800, provenance: "typed" },
      { role: "assistant", text: "Mill Road has a short loop; the lake a long one. Mill Road it is.", at: NOW - 10790 }] },
  },
};

await check("the search box asks the PC to search what was SAID, and shows a snippet with the words marked", async () => {
  const page = await historyTab(SEARCHED);
  await page.locator("#history-filter").fill("mill road");
  await page.waitForTimeout(700);
  const titles = await page.locator("#history-list .row-title").allInnerTexts();
  const snippet = await page.locator("#history-list .search-snippet").first().innerText();
  const marks = await page.locator("#history-list .search-snippet mark").first().innerText();
  const text = await listText(page);
  const asked = await page.evaluate(() => window.__history.searches);
  await page.close();
  assert.deepEqual(titles.map((t) => t.trim()), ["Dentist on Tuesday", "Weekend plan"],
    "found by words said inside the chat, not in the title");
  assert.match(snippet, /^Jarvis: Tuesday at 3, on Mill Road\./);
  assert.equal(marks.trim(), "Mill");
  assert.match(text, /Nothing is saved and nothing is sent to the AI/);
  assert.match(text, /2 conversations match/);
  assert.deepEqual(asked, ["mill road"], "one search, after typing paused");
});

await check("nothing found says so; one letter and a cleared box go back to the list, asking nothing", async () => {
  const page = await historyTab(SEARCHED);
  await page.locator("#history-filter").fill("quokka");
  await page.waitForTimeout(700);
  const none = await listText(page);
  await page.locator("#history-filter").fill("w");
  await page.waitForTimeout(700);
  const oneLetter = await page.locator("#history-list .row-title").allInnerTexts();
  await page.locator("#history-filter").fill("");
  await page.waitForTimeout(700);
  const all = await page.locator("#history-list .row-item").count();
  const asked = await page.evaluate(() => window.__history.searches);
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  await page.close();
  assert.match(none, /No kept conversation has all of those words/);
  assert.deepEqual(oneLetter.map((t) => t.trim()), ["Weekend plan"], "one letter narrows titles");
  assert.equal(all, 3);
  assert.deepEqual(asked, ["quokka"]);
  assert.ok(!/quokka/.test(stored), "the words searched for are not kept in the window's storage");
});

await check("an older PC: the box narrows the loaded list by title, and says why", async () => {
  const page = await historyTab({ ...SEARCHED, searchMissing: true });
  await page.locator("#history-filter").fill("dentist");
  await page.waitForTimeout(700);
  const titles = await page.locator("#history-list .row-title").allInnerTexts();
  const text = await listText(page);
  await page.locator("#history-filter").fill("mill road");
  await page.waitForTimeout(700);
  const none = await listText(page);
  const asked = await page.evaluate(() => window.__history.searches);
  await page.close();
  assert.deepEqual(titles.map((t) => t.trim()), ["Dentist on Tuesday"]);
  assert.match(text, /can only search titles/);
  assert.match(none, /No conversations match that search/, "words said are not searched on an older PC");
  assert.deepEqual(asked, ["dentist"], "asked once, then remembered for this window");
});

await check("opening a result finds the search words in it: marked, counted, Next and Previous step", async () => {
  const page = await historyTab(SEARCHED);
  await page.locator("#history-filter").fill("mill road");
  await page.waitForTimeout(700);
  await page.locator("#history-list .row-item").nth(1).getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(300);
  const find = await page.locator("#history-find").inputValue();
  const count = await page.locator("#history-find-count").innerText();
  const marks = await page.locator("#history-transcript mark.find-hit").count();
  const current = await page.locator("#history-transcript mark.find-current").count();
  await page.locator("#history-find-next").click();
  const second = await page.locator("#history-find-count").innerText();
  await page.locator("#history-find-prev").click();
  await page.locator("#history-find-prev").click();
  const last = await page.locator("#history-find-count").innerText();
  await page.close();
  assert.equal(find, "mill road");
  // "Mill", "Road" x3 each in c-3 = 6 places.
  assert.equal(marks, 6);
  assert.equal(current, 1);
  assert.equal(count.trim(), "1 of 6");
  assert.equal(second.trim(), "2 of 6");
  assert.equal(last.trim(), "6 of 6", "Previous from the first wraps to the last");
});

await check("Find in this chat works on a conversation opened from the list, with Enter, and asks the PC nothing", async () => {
  const page = await historyTab(SEARCHED);
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(300);
  const empty = await page.locator("#history-find").inputValue();
  await page.locator("#history-find").fill("TUESDAY");
  const one = await page.locator("#history-find-count").innerText();
  await page.locator("#history-find").fill("zzz");
  const none = await page.locator("#history-find-count").innerText();
  await page.locator("#history-find").fill("e");
  await page.locator("#history-find").press("Enter");
  const stepped = await page.locator("#history-find-count").innerText();
  const focused = await page.evaluate(() => document.activeElement.id);
  const asked = await page.evaluate(() => window.__history.searches);
  await page.close();
  assert.equal(empty, "", "opened from the list, nothing to find yet");
  assert.equal(one.trim(), "1 match");
  assert.equal(none.trim(), "Not in this chat.");
  assert.match(stepped.trim(), /^2 of \d+$/);
  assert.equal(focused, "history-find", "the find box keeps the keyboard");
  assert.deepEqual(asked, []);
});

await check("the words found are set as text: a transcript cannot become markup", async () => {
  const evil = { ...SEARCHED, transcripts: { ...SEARCHED.transcripts,
    "c-1": { id: "c-1", title: "x", turns: [{ role: "user", text: "<img src=x onerror=alert(1)> dentist", at: NOW }] } } };
  const page = await historyTab(evil);
  await page.locator("#history-filter").fill("dentist");
  await page.waitForTimeout(700);
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(300);
  const imgs = await page.locator("#history-list img").count();
  const shown = await page.locator("#history-transcript").innerText();
  await page.close();
  assert.equal(imgs, 0);
  assert.match(shown, /<img src=x onerror=alert\(1\)> dentist/);
});

await check("hidden under Windows Hello: no search is sent, no snippet shown", async () => {
  const page = await historyTab(SEARCHED, { security: { hidden: true } });
  await page.locator("#history-filter").fill("mill road");
  await page.waitForTimeout(700);
  const text = await listText(page);
  const asked = await page.evaluate(() => window.__history.searches);
  await page.close();
  assert.match(text, /hidden until Windows Hello/);
  assert.doesNotMatch(text, /Mill Road/);
  assert.deepEqual(asked, []);
});

await check("Load older asks for the page before the oldest shown, and adds it underneath", async () => {
  const page = await historyTab({ conversations: many(31) });
  const before = await page.locator("#history-list .row-item").count();
  await page.getByRole("button", { name: "Load older" }).click();
  await page.waitForTimeout(250);
  const after = await page.locator("#history-list .row-item").count();
  const reads = await page.evaluate(() => window.__history.reads);
  const more = await page.getByRole("button", { name: "Load older" }).count();
  await page.close();
  assert.equal(before, 30);
  assert.equal(after, 31);
  assert.deepEqual(reads.at(-1), { before: NOW - 60 * 30, limit: 30 });
  assert.equal(more, 0, "offered more after a short page");
});

await check("opening one shows it read-only, with where pasted, shared or clipboard words came from", async () => {
  const conv = {
    id: "c0nv-phone-0001", title: "Dentist on Tuesday", tainted: true,
    turns: [
      { role: "user", text: "when is the dentist?", at: NOW - 3600, provenance: "typed", read_outside: false },
      { role: "assistant", text: "Tuesday at 3.", at: NOW - 3596 },
      { role: "user", text: "Appointment confirmed for Tue 3pm", at: NOW - 3500, provenance: "shared", read_outside: false },
      { role: "user", text: "what does this say", at: NOW - 3400, provenance: "pasted", read_outside: false },
      { role: "user", text: "move it", at: NOW - 3350, provenance: "clipboard", read_outside: false },
      { role: "user", text: "<b>check the web</b>", at: NOW - 3300, provenance: "voice", read_outside: true },
    ],
  };
  const page = await historyTab({ conversations: LIST.conversations, transcripts: { [conv.id]: conv } });
  await page.getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(250);
  const turns = await page.locator("#history-transcript .history-turn").allInnerTexts();
  const note = await page.locator("#history-transcript .history-taint-note").innerText();
  const bold = await page.locator("#history-transcript b").count();
  const buttons = await page.locator("#history-transcript-turns button").allInnerTexts();
  // "Find in this chat" (section 71) only moves between matches.
  const findButtons = await page.locator("#history-transcript button").allInnerTexts();
  const opened = await page.evaluate(() => window.__history.opened);
  await page.getByRole("button", { name: "Close" }).click();
  await page.waitForTimeout(100);
  const closed = await page.locator("#history-transcript").count();
  await page.close();
  assert.deepEqual(opened, ["c0nv-phone-0001"]);
  assert.equal(turns.length, 6);
  assert.doesNotMatch(turns[0], /pasted|shared|clipboard|typed/, "typed words were labelled");
  assert.match(turns[1], /^Jarvis/);
  assert.match(turns[2], /shared from another app/);
  assert.match(turns[3], /pasted/);
  assert.match(turns[4], /from clipboard/);
  assert.match(turns[5], /read outside text/);
  assert.match(turns[5], /<b>check the web<\/b>/, "the text was not shown as it was written");
  assert.equal(bold, 0, "a transcript's text became markup");
  // Read-only: the only control on a message is Copy, on Jarvis's answer
  // (the chat audit, 2026-09-28); above the words, "Continue this chat" and
  // the find bar's two steps.
  assert.deepEqual(buttons, ["Copy"], "a read-only transcript has controls in it");
  assert.deepEqual(findButtons, ["Continue this chat", "Previous", "Next", "Copy"],
    "only Continue, the find bar's two steps and Copy");
  assert.match(note, /did not come from you/);
  assert.equal(closed, 0);
});

await check("delete asks first, sends one id, and a no sends nothing", async () => {
  const page = await historyTab({ conversations: many(2) });
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.dismiss(); });
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(150);
  const afterNo = await page.evaluate(() => window.__history.deleted);
  page.once("dialog", (d) => d.accept());
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(250);
  const afterYes = await page.evaluate(() => window.__history.deleted);
  const left = await page.locator("#history-list .row-item").allInnerTexts();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.match(asked, /Conversation 0/);
  assert.match(asked, /cannot be undone/);
  assert.deepEqual(afterNo, [], "dismissing the confirm still deleted");
  assert.deepEqual(afterYes, ["conv-0000"]);
  assert.equal(left.length, 1);
  assert.match(left[0], /Conversation 1/);
  assert.match(toast, /Deleted/);
});

await check("there is no delete-all anywhere: not on the page, not in Rust", async () => {
  const page = await historyTab({ conversations: many(5) });
  const labels = await page.locator("#view-history button").allInnerTexts();
  await page.close();
  assert.ok(!labels.some((l) => /all|everything|clear/i.test(l)), `a bulk control: ${labels}`);
  const rust = read("src-tauri/src/brain/history.rs");
  assert.match(rust, /pub async fn brain_history_delete\(\s*app: AppHandle,\s*id: String,?\s*\)/);
  assert.doesNotMatch(rust, /Vec<String>/, "a list of ids reaches a history command");
});

await check("the switch shows the contract's words, and on means on", async () => {
  const page = await historyTab({ conversations: [] });
  const text = await settingsText(page);
  const checked = await page.locator("#history-enabled").isChecked();
  const role = await page.locator("#history-enabled").getAttribute("role");
  const keep = await page.locator("#history-keep option").allInnerTexts();
  const empty = await listText(page);
  await page.close();
  assert.match(text, /Keep chat history on this PC/);
  assert.match(text, /Your chats, including what you say to Jarvis by voice, are kept on this PC, encrypted\. Nothing is sent anywhere\./);
  assert.equal(checked, true);
  assert.equal(role, "switch");
  assert.deepEqual(keep, ["Never", "30 days", "90 days", "1 year"]);
  assert.match(empty, /No conversations kept yet/);
});

await check("turning it ON raises a card and shows waiting, like learning - it is not on yet", async () => {
  const page = await historyTab({ waits: true,
    status: { enabled: false, recording: false, why_not: "Chat history is off." } });
  await page.locator("#history-enabled").click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__history.settings);
  const line = await page.locator("#history-settings .learning-waiting").innerText();
  const checked = await page.locator("#history-enabled").isChecked();
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(sent, [{ enabled: true, keepDays: null }]);
  assert.match(line, /Waiting for your approval to turn chat history on\. Approve it in the Jarvis bar/);
  assert.equal(checked, false, "shown as on before the card was approved");
  assert.match(toast, /Waiting for your approval/);
  assert.doesNotMatch(toast, /Chat history is (on|off)/);
});

await check("the card leaving the queue unapproved ends the wait and says so", async () => {
  const CARD = { id: "gate-history-1", action: "history_enable", tier: "ask", detail: {}, created: 1 };
  const page = await historyTab({ waits: true, status: { enabled: false, recording: false } });
  await page.evaluate((card) => { window.__pendingNow = [card]; }, CARD);
  await page.locator("#history-enabled").click();
  await page.waitForTimeout(300);
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), CARD);
  await page.waitForTimeout(100);
  const before = await settingsText(page);
  // Denied (or ran out of time): the card goes, and the PC says not waiting.
  await page.evaluate(() => {
    window.__pendingNow = [];
    window.__history.status.waiting = false;
    window.__emit("approvals-changed", { count: 0, items: [] });
  });
  await page.waitForTimeout(3600); // the grace an approval gets to land
  const after = await settingsText(page);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.match(before, /Waiting for your approval/);
  assert.doesNotMatch(after, /Waiting for your approval/, "still claims a card is waiting");
  assert.match(toast, /Chat history stays off: the card was denied or ran out of time/);
});

await check("turning it OFF is immediate and says so in the contract's words", async () => {
  const page = await historyTab({ conversations: many(1) });
  await page.locator("#history-enabled").click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__history.settings);
  const toast = await page.locator("#toast").innerText();
  const checked = await page.locator("#history-enabled").isChecked();
  const rows = await page.locator("#history-list .row-item").count();
  await page.close();
  assert.deepEqual(sent, [{ enabled: false, keepDays: null }]);
  assert.equal(toast, OFF_REPLY);
  assert.equal(checked, false);
  assert.equal(rows, 1, "what was kept stays until deleted");
});

await check("on a stale link ON and the keep choice are greyed; OFF never is", async () => {
  const off = await historyTab({ status: { enabled: false, recording: false } }, { link: { stale: true } });
  const offDisabled = await off.locator("#history-enabled").isDisabled();
  const keepDisabled = await off.locator("#history-keep").isDisabled();
  await off.close();
  const on = await historyTab({}, { link: { stale: true } });
  const onDisabled = await on.locator("#history-enabled").isDisabled();
  await on.close();
  assert.equal(offDisabled, true, "ON could be asked for on a stale link");
  assert.equal(keepDisabled, true);
  assert.equal(onDisabled, false, "OFF was held on a stale link");
});

await check("why nothing new is kept is shown plainly", async () => {
  const why = "Nothing is kept: the encryption key could not be read from Windows Credential Manager.";
  const page = await historyTab({ status: { enabled: true, recording: false, why_not: why } });
  const text = await page.locator("#history-settings .history-why-not").innerText();
  await page.close();
  assert.equal(text, why);
});

await check("a shorter keep period asks first, in both apps' words; a no sends nothing", async () => {
  const page = await historyTab({ conversations: many(3), status: { keep_days: 90 } });
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.dismiss(); });
  await page.locator("#history-keep").selectOption("30");
  await page.waitForTimeout(300);
  const afterNo = await page.evaluate(() => window.__history.settings);
  const shown = await page.locator("#history-keep").inputValue();
  // Longer, or back to Never: nothing is deleted now, so nothing is asked.
  let askedAgain = false;
  page.on("dialog", (d) => { askedAgain = true; d.dismiss(); });
  await page.locator("#history-keep").selectOption("365");
  await page.waitForTimeout(400);
  const afterLonger = await page.evaluate(() => window.__history.settings);
  await page.close();
  assert.equal(asked,
    "Delete every conversation older than 30 days from your PC now, and from then on? This cannot be undone." +
    `\n\n${KEEP_SUPPORT_NOTE}`);
  assert.deepEqual(afterNo, [], "a no still changed the period");
  assert.equal(shown, "90", "the choice moved although nothing was sent");
  assert.equal(askedAgain, false, "a longer period asked");
  assert.deepEqual(afterLonger, [{ enabled: null, keepDays: 365 }]);
  // The rule, in full: any period from Never, a shorter one; nothing else.
  assert.deepEqual([[0, 30], [0, 365], [90, 30], [365, 90], [30, 90], [30, 0], [90, 90], [null, 30]]
    .map(([f, t]) => keepNeedsConfirm(f, t)), [true, true, true, true, false, false, false, true]);
  assert.equal(keepConfirm(365),
    "Delete every conversation older than 1 year from your PC now, and from then on? This cannot be undone.");
});

await check("the 15-second re-read keeps the older pages and the open conversation", async () => {
  const convs = many(31);
  const last = convs[30];
  const page = await historyTab({ conversations: convs,
    transcripts: { [last.id]: { id: last.id, title: last.title, tainted: false,
      turns: [{ role: "user", text: "the oldest one", at: last.updated, provenance: "typed" }] } } });
  await page.getByRole("button", { name: "Load older" }).click();
  await page.waitForTimeout(250);
  await page.locator(`#history-list .row-item[data-id="${last.id}"]`).getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(250);
  // The re-read the tab does every 15 seconds - the same loadHistory the
  // private-answers events call, so one of those drives it here.
  await page.evaluate(() => window.__emit("private-hidden", {}));
  await page.waitForTimeout(300);
  const rows = await page.locator("#history-list .row-item").count();
  const transcript = await page.locator("#history-transcript").innerText();
  const firstPageReads = await page.evaluate(() => window.__history.reads.filter((r) => r.before == null).length);
  await page.close();
  assert.ok(firstPageReads >= 2, "the list was not read again");
  assert.equal(rows, 31, "the page Load older brought in was dropped");
  assert.match(transcript, /the oldest one/, "the open conversation was closed");
  // The rule on its own: a moved row is not shown twice; a short first page keeps nothing older.
  const first = readHistory({ ...LIST, conversations: many(30) }).conversations;
  const older = readHistory({ ...LIST, conversations: many(32) }).conversations.slice(30);
  const moved = { ...older[0], updated: NOW };
  const r = refreshRows([...first, ...older], [moved, ...first.slice(0, 29)], 30, true);
  assert.deepEqual(r.rows.map((c) => c.id), [moved.id, ...first.slice(0, 29).map((c) => c.id), first[29].id, older[1].id],
    "the row pushed off the first page stays, under it");
  assert.equal(r.more, true);
  assert.deepEqual(refreshRows([...first, ...older], first.slice(0, 5), 30, true), { rows: first.slice(0, 5), more: false });
});

await check("which app, and the tainted line: the words both apps use", async () => {
  assert.deepEqual(["desktop", "hud", "phone", "", "watch"].map((d) => deviceTag(d).tag),
    ["PC", "HUD", "phone", "unknown", "unknown"]);
  assert.equal(TAINT_TITLE, "In this conversation Jarvis read text that did not come from you - a web page, " +
    "a file, an email or another tool's output - from the marked message on.");
});

await check("dates say the weekday; an answer not kept and a delete say so, in the phone's words", async () => {
  // Noon UTC on Tuesday 22 September 2026, read a week later.
  const tue = Date.UTC(2026, 8, 22, 12) / 1000;
  assert.match(whenWords(tue, (tue + 7 * 86400) * 1000), /^Tue 22 Sept? 2026$/);
  // History itself: the phone's whenLine (the chat audit, 2026-09-28).
  assert.equal(whenLine(tue, (tue + 7 * 86400) * 1000, { utc: true }), "Tue 22 Sep 12:00");
  const conv = readConversation({ id: "c", turns: [
    { role: "user", text: "a", at: 1, provenance: "typed", answer_kept: false },
    { role: "user", text: "b", at: 2, provenance: "typed", answer_kept: true },
    { role: "user", text: "c", at: 3, provenance: "typed" },
  ] });
  assert.deepEqual(conv.turns.map((t) => t.answerKept), [false, true, true]);
  assert.ok(deleteQuestion({ title: "x" }).endsWith(DELETE_KEEPS_FACTS));
  const kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/net/ChatLog.kt")
    .replace(/"\s*\+\s*\n\s*"/g, "");
  for (const w of [NOT_KEPT_LINE, DELETE_KEEPS_FACTS]) {
    assert.ok(kt.includes(JSON.stringify(w).slice(1, -1).replace(/\\'/g, "'")), `the phone says: ${w}`);
  }
  // Deleting a chat offers to forget its facts (section 79): the same words
  // - every fixed piece of them, since the numbers change.
  for (const w of [
    " fact from this chat. It is kept unless you tick it - a ticked fact is forgotten, like Forget in the Brain.",
    " facts from this chat. They are kept unless you tick them - each ticked fact is forgotten, like Forget in the Brain.",
    "Your memory lists are hidden, so they are kept. To forget any, show the memory lists first.",
    "Delete the chat and forget ",
    "The facts it taught are kept.",
    "could not be forgotten - try Forget on ",
  ]) {
    assert.ok(chatFactsIntro(1).includes(w) || chatFactsIntro(2).includes(w)
      || chatFactsHiddenLine(2).includes(w) || deleteChatButton(2).includes(w)
      || deleteAndForgetQuestion({ title: "t" }, []).includes(w)
      || deleteDoneWords({ failed: 2 }).includes(w), `the desktop does not say: ${w}`);
    assert.ok(kt.includes(w), `the phone does not say: ${w}`);
  }
});

/* ── Deleting a chat offers to forget the facts it taught (section 79) ─── */

await check("the words: none ticked, how many, what is forgotten, what happened", async () => {
  assert.match(chatFactsIntro(1), /^Jarvis learned 1 fact from this chat\. It is kept unless you tick it/);
  assert.match(chatFactsIntro(2), /^Jarvis learned 2 facts from this chat\. They are kept unless you tick them/);
  assert.equal(deleteChatButton(0), "Delete the chat");
  assert.equal(deleteChatButton(1), "Delete the chat and forget 1 fact");
  assert.equal(deleteChatButton(3), "Delete the chat and forget 3 facts");
  const q = deleteAndForgetQuestion({ title: "Dentist" }, [{ id: 4, text: "Owner likes tea" }]);
  assert.match(q, /^Delete this conversation and forget 1 fact\?/);
  assert.match(q, /- Owner likes tea/);
  assert.match(q, /cannot be brought back/);
  assert.match(deleteAndForgetQuestion({ title: "D" }, []), /The facts it taught are kept\./);
  assert.equal(deleteDoneWords({}), "Deleted from this PC.");
  assert.equal(deleteDoneWords({ forgot: 2 }), "Deleted from this PC. Forgot 2 facts.");
  assert.match(deleteDoneWords({ gone: true, forgot: 1, failed: 1 }),
    /^That conversation was already deleted\. Forgot 1 fact\. 1 fact could not be forgotten/);
  assert.match(chatFactsHiddenLine(2), /hidden, so they are kept/);
  const r = readChatFacts({ facts: [{ id: 3, text: " Owner likes tea " }, { id: 0, text: "x" },
    { id: 5, text: "" }, { id: "6", text: "y" }] });
  assert.deepEqual(r.facts, [{ id: 3, text: "Owner likes tea" }]);
  assert.equal(readChatFacts({ facts: [], hidden: true, hidden_count: 2 }).hiddenCount, 2);
  assert.equal(readChatFacts({ available: false, why: "old" }).available, false);
  assert.deepEqual(readChatFacts(null).facts, []);
});

const TAUGHT = { "conv-0000": [
  { id: 41, text: "Owner's passport is in the top drawer", created: NOW - 600, source: "auto" },
  { id: 42, text: "Owner likes green tea", created: NOW - 500, source: "auto" }] };

await check("delete lists the facts the chat taught, NONE ticked, and forgets only the ticked one", async () => {
  const page = await historyTab({ conversations: many(2), chatFacts: TAUGHT });
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(250);
  const panel = await page.locator("#history-delete-facts").innerText();
  const ticked = await page.locator("#history-delete-facts input[type=checkbox]:checked").count();
  const boxes = await page.locator("#history-delete-facts input[type=checkbox]").count();
  const before = await page.evaluate(() => window.__history.deleted);
  await page.locator("#history-delete-facts input[data-fact-id='42']").check();
  const label = await page.locator("#history-delete-go").innerText();
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.accept(); });
  await page.locator("#history-delete-go").click();
  await page.waitForTimeout(400);
  const deleted = await page.evaluate(() => window.__history.deleted);
  const writes = await page.evaluate(() => window.__memoryWrites.filter((w) => w.cmd === "brain_memory_forget"));
  const toast = await page.locator("#toast").innerText();
  const gone = await page.locator("#history-delete-facts").count();
  const errors = page.__errors;
  await page.close();
  assert.match(panel, /Jarvis learned 2 facts from this chat/);
  assert.match(panel, /Owner's passport is in the top drawer/);
  assert.equal(boxes, 2);
  assert.equal(ticked, 0, "a fact was ticked before the owner ticked it");
  assert.deepEqual(before, [], "the chat went before the owner answered");
  assert.equal(label, "Delete the chat and forget 1 fact");
  assert.match(asked, /forget 1 fact/);
  assert.match(asked, /- Owner likes green tea/);
  assert.doesNotMatch(asked, /passport/, "an unticked fact was named for forgetting");
  assert.deepEqual(deleted, ["conv-0000"]);
  assert.deepEqual(writes.map((w) => w.id), [42], "not exactly the one ticked fact was forgotten");
  assert.match(toast, /Deleted from this PC\. Forgot 1 fact\./);
  assert.equal(gone, 0);
  assert.deepEqual(errors, []);
});

await check("nothing ticked: the chat goes, every fact stays; Cancel keeps both", async () => {
  const page = await historyTab({ conversations: many(2), chatFacts: TAUGHT });
  const del = () => page.locator("#history-list .row-item").first().getByRole("button", { name: "Delete" }).click();
  await del();
  await page.waitForTimeout(250);
  await page.locator("#history-delete-facts").getByRole("button", { name: "Cancel" }).click();
  await page.waitForTimeout(150);
  const afterCancel = await page.evaluate(() => window.__history.deleted);
  await del();
  await page.waitForTimeout(250);
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.accept(); });
  await page.locator("#history-delete-go").click();
  await page.waitForTimeout(400);
  const deleted = await page.evaluate(() => window.__history.deleted);
  const writes = await page.evaluate(() => window.__memoryWrites.filter((w) => w.cmd === "brain_memory_forget"));
  await page.close();
  assert.deepEqual(afterCancel, [], "Cancel deleted the chat");
  assert.match(asked, /The facts it taught are kept/);
  assert.deepEqual(deleted, ["conv-0000"]);
  assert.deepEqual(writes, [], "a fact was forgotten with nothing ticked");
});

await check("hidden memory lists: no fact is shown, and the confirm says they are kept", async () => {
  const page = await historyTab({ conversations: many(1), chatFacts: TAUGHT, chatFactsHidden: true });
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.accept(); });
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(400);
  const panel = await page.locator("#history-delete-facts").count();
  const writes = await page.evaluate(() => window.__memoryWrites.filter((w) => w.cmd === "brain_memory_forget"));
  await page.close();
  assert.equal(panel, 0);
  assert.match(asked, /Jarvis learned 2 facts from this chat\. Your memory lists are hidden, so they are kept/);
  assert.doesNotMatch(asked, /passport|green tea/);
  assert.deepEqual(writes, []);
});

await check("an older PC: delete asks exactly as before", async () => {
  const page = await historyTab({ conversations: many(1), chatFacts: TAUGHT, chatFactsMissing: true });
  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); d.accept(); });
  await page.locator("#history-list .row-item").first().getByRole("button", { name: "Delete" }).click();
  await page.waitForTimeout(400);
  const deleted = await page.evaluate(() => window.__history.deleted);
  await page.close();
  assert.ok(asked.endsWith(DELETE_KEEPS_FACTS), asked);
  assert.deepEqual(deleted, ["conv-0000"]);
});

await check("the read is a memory list: in the Brain's memory set, hidden in Rust, one Forget per fact", async () => {
  const rust = read("src-tauri/src/brain/conversation_facts.rs");
  assert.match(rust, /private_hidden\(&app\)/);
  assert.match(rust, /redact_conversation_facts/);
  const toml = read("src-tauri/permissions/surfaces.toml");
  const memorySet = toml.slice(toml.indexOf('identifier = "brain-memory"'));
  assert.ok(memorySet.slice(0, memorySet.indexOf("[[set]]", 10) > 0 ? memorySet.indexOf("[[set]]", 10) : undefined)
    .includes('"allow-brain-conversation-facts"'), "not in the brain-memory set");
  assert.match(read("src-tauri/build.rs"), /"brain_conversation_facts"/);
  assert.match(read("src-tauri/src/lib.rs"), /brain::conversation_facts::brain_conversation_facts,/);
  const js = read("src/brain.js");
  const fin = js.slice(js.indexOf("async function finishDelete("));
  assert.match(fin.slice(0, 1500), /for \(const id of factIds\)[\s\S]*invoke\("brain_memory_forget", \{ id \}\)/);
});

await check("the keep choice sends one keep_days and says how many went", async () => {
  const page = await historyTab({ conversations: many(3), deletedByKeep: 2 });
  page.once("dialog", (d) => d.accept());
  await page.locator("#history-keep").selectOption("30");
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__history.settings);
  const toast = await page.locator("#toast").innerText();
  const shown = await page.locator("#history-keep").inputValue();
  await page.close();
  assert.deepEqual(sent, [{ enabled: null, keepDays: 30 }]);
  assert.match(toast, /older than 30 days are deleted\. 2 were deleted just now/);
  assert.equal(shown, "30");
});

await check("private answers hide the list, keep the count, and Show brings it back", async () => {
  const page = await historyTab({ conversations: many(3) }, { security: { hidden: true } });
  const hidden = await listText(page);
  const titles = await page.locator("#history-list .row-item").count();
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForTimeout(300);
  const shown = await page.locator("#history-list .row-item").count();
  await page.close();
  assert.match(hidden, /3 conversations, hidden until Windows Hello confirms it is you/);
  assert.equal(titles, 0);
  assert.equal(shown, 3);
});

await check("an older backend is told to update, in a sentence", async () => {
  const page = await historyTab({ missing: true });
  const text = await settingsText(page);
  const all = await page.locator("#view-history").innerText();
  await page.close();
  assert.match(text, /Update the backend by running apply-patches\.ps1/);
  assert.doesNotMatch(all, /[{}]|undefined|null/);
});

await check("CONTROL: only the Brain holds the history commands, and ON is held on a stale link", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const holders = (perm) => sets.filter((s) => s.includes(`"${perm}"`))
    .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
  const cmds = ["brain_history_list", "brain_history_open", "brain_history_search",
    "brain_history_delete", "brain_history_settings"];
  for (const cmd of cmds) {
    const perm = `allow-${cmd.replace(/_/g, "-")}`;
    assert.deepEqual(holders(perm), ["brain-history"], `${perm} is held by ${holders(perm)}`);
  }
  for (const c of ["brain", "faces", "floating", "hud", "onboarding", "quickbar", "settings", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.equal(json.includes("\"brain-history\""), c === "brain", `${c} and brain-history`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of cmds) {
    assert.match(build, new RegExp(`"${cmd}"`), `${cmd} missing from build.rs`);
    assert.match(lib, new RegExp(`brain::history::${cmd},`), `${cmd} missing from lib.rs`);
  }
  const rust = read("src-tauri/src/brain/history.rs");
  const settings = rust.slice(rust.indexOf("pub async fn brain_history_settings("));
  assert.match(settings, /if enabled == Some\(true\) \|\| keep_days\.is_some\(\) \{\s*require_link_live/);
  const del = rust.slice(rust.indexOf("pub async fn brain_history_delete("));
  assert.ok(del.indexOf("require_link_live") < del.indexOf("post("), "delete is not held on a stale link");
  const open = rust.slice(rust.indexOf("pub async fn brain_history_open("));
  assert.ok(open.indexOf("private_hidden") < open.indexOf("get(&app"), "a transcript opens while hidden");
});

/* ── The chat audit in the windows (2026-09-28) ─────────────────────────── */

const KINDS_LIST = [
  { id: "conv-live-0001", title: "Planning the weekend", started: NOW - 7200, updated: NOW - 6480, turns: 8,
    device: "desktop", has_voice: true, tainted: false, kind: "live" },
  { id: "conv-supp-0001", title: "Groupon refund", started: NOW - 9000, updated: NOW - 8800, turns: 12,
    device: "desktop", has_voice: false, tainted: true, kind: "support" },
  { id: "conv-chat-0001", title: "Dentist on Tuesday", started: NOW - 9600, updated: NOW - 9500, turns: 2,
    device: "phone", has_voice: false, tainted: false, kind: "chat" },
];

await check("rows say their kind, a Live session its length, and Show asks the PC for one kind", async () => {
  const page = await historyTab({ conversations: KINDS_LIST });
  const rows = await page.locator("#history-list .row-item").allInnerTexts();
  const status = await page.locator("#freshness").innerText().catch(() => "");
  await page.selectOption("#history-kind", "live");
  await page.waitForTimeout(300);
  const reads = await page.evaluate(() => window.__history.reads);
  const after = await page.locator("#history-list .row-item").allInnerTexts();
  const forgetLink = await page.locator("#history-tools .history-forget-range-link").innerText();
  await page.close();
  assert.match(rows[0], /Live · 12 min · Today \d\d:\d\d · 8 messages/);
  assert.match(rows[1], /Support chat/);
  assert.doesNotMatch(rows[2], /Support chat|Chat with an AI|Comparison/);
  assert.doesNotMatch(status, /reading…/, "History's status line is stuck on reading");
  assert.deepEqual(reads.at(-1), { before: null, limit: 30, kind: "live" });
  assert.equal(after.length, 1);
  assert.equal(forgetLink, "Forget a time frame…");
});

await check("Continue this chat names the chat to the bar; a support record says why it cannot be", async () => {
  const chat = { ...CONV, id: "conv-chat-0001", kind: "chat", continuable: true };
  const support = { id: "conv-supp-0001", title: "Groupon refund", tainted: true, kind: "support",
    continuable: false, continue_why: "A customer-support record can't be continued: it is the company's " +
      "words and what was sent in your name, kept as your record.",
    turns: [{ role: "support", text: "Hello, how can I help?", provenance: "support_company", read_outside: true }] };
  const page = await historyTab({ conversations: KINDS_LIST,
    transcripts: { "conv-chat-0001": chat, "conv-supp-0001": support } });
  await page.locator("#history-list .row-item").nth(2).getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(250);
  await page.getByRole("button", { name: "Continue this chat" }).click();
  await page.waitForTimeout(150);
  const continued = await page.evaluate(() => window.__history.continued);
  await page.getByRole("button", { name: "Close" }).click();
  await page.locator("#history-list .row-item").nth(1).getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(250);
  const why = await page.locator("#history-transcript .history-continue-why").innerText();
  const cont = await page.getByRole("button", { name: "Continue this chat" }).count();
  await page.close();
  assert.deepEqual(continued, ["conv-chat-0001"]);
  assert.equal(why, support.continue_why);
  assert.equal(cont, 0);
});

await check("an old answer's markdown is drawn, escaped, and Copy copies it privately", async () => {
  const conv = { ...CONV, turns: [
    { role: "user", text: "list it", at: NOW - 60, provenance: "typed" },
    { role: "assistant", text: "## Plan\n- **one** <script>x</script>\n- two", at: NOW - 50 },
  ] };
  const page = await historyTab({ conversations: LIST.conversations, transcripts: { [conv.id]: conv } });
  await page.getByRole("button", { name: "Open" }).click();
  await page.waitForTimeout(250);
  const strong = await page.locator("#history-transcript .history-md strong").count();
  const scripts = await page.locator("#history-transcript .history-md script").count();
  const md = await page.locator("#history-transcript .history-md").innerText();
  await page.getByRole("button", { name: "Copy" }).click();
  await page.waitForTimeout(100);
  const copied = await calls(page, "write_clipboard_private");
  await page.close();
  assert.equal(strong, 1);
  assert.equal(scripts, 0, "an old answer's HTML ran as markup");
  assert.doesNotMatch(md, /\*\*|##/);
  assert.deepEqual(copied, [{ text: conv.turns[1].text }]);
});

/* ── The Jarvis bar ─────────────────────────────────────────────────────── */

async function bar(extra = {}) {
  const page = await K.open(browser, base, "index.html", { chatReplies: [], ...extra }, { width: 760, height: 900 });
  await page.waitForTimeout(250);
  return page;
}

await check("the bar: Earlier chats opens History; Esc says where the chat went", async () => {
  const page = await bar({ chatReplies: ["Tuesday at 3."] });
  await page.fill("#prompt", "when is the dentist?");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(150);
  const ended = await page.locator("#chat-ended-note").innerText();
  await page.locator("#earlier-chats-primer").click();
  await page.waitForTimeout(100);
  const opened = await calls(page, "open_fix_place");
  const footer = await page.locator("footer .keys").innerText();
  await page.close();
  assert.equal(ended, CASES.words.ended_saved);
  assert.deepEqual(opened, [{ place: "history" }]);
  assert.match(footer, /Esc\s*end chat/);
});

await check("the bar: Continue this chat loads the kept turns into the thread, the same id goes with the next question", async () => {
  const conv = { id: "conv-chat-0001", title: "Dentist on Tuesday", kind: "chat", tainted: true, turns: [
    { role: "user", text: "when is the dentist?", provenance: "typed" },
    { role: "assistant", text: "Tuesday at 3." },
    { role: "user", text: "ask the cloud", provenance: "typed", answer_kept: false },
  ] };
  const page = await bar({ history: { transcripts: { [conv.id]: conv } }, chatReplies: ["Bring your card."] });
  await page.evaluate(() => window.__emit("continue-chat", "conv-chat-0001"));
  await page.waitForTimeout(300);
  const note = await page.locator("#chat-note").innerText();
  const thread = await page.locator("#previous-answer-body").innerText();
  const summary = await page.locator("#previous-answer-summary").innerText();
  await page.fill("#prompt", "what should I bring?");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => (window.__calls || []).filter((c) => c[0] === "stream_chat").map((c) => c[1]));
  await page.close();
  assert.equal(note, `Carrying on "Dentist on Tuesday". ${CASES.words.continued_tainted}`);
  assert.match(thread, /when is the dentist\?[\s\S]*Tuesday at 3\./);
  assert.doesNotMatch(thread, /ask the cloud/, "a question whose answer was not kept came back");
  assert.equal(summary, "Earlier in this chat · 1 question");
  const last = sent.at(-1);
  assert.equal(JSON.stringify(last).includes("conv-chat-0001"), true, "the next question did not carry the chat's id");
});

await check("the bar: a chat deleted in the Brain ends here too, and says so", async () => {
  const page = await bar({ chatReplies: ["Tuesday at 3."] });
  await page.fill("#prompt", "when is the dentist?");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);
  const cid = await page.evaluate(() => {
    const c = (window.__calls || []).filter((x) => x[0] === "stream_chat").at(-1);
    return JSON.stringify(c[1]).match(/"conversation_?[iI]d":"([^"]+)"/)[1];
  });
  await page.evaluate((id) => {
    localStorage.setItem("jarvis.chat.gone", JSON.stringify({ ids: [id], at: Date.now() }));
    window.dispatchEvent(new Event("focus"));
  }, cid);
  await page.waitForTimeout(150);
  const note = await page.locator("#chat-note").innerText();
  await page.close();
  assert.equal(note, CASES.words.chat_gone);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nchat history is shown, one at a time");
process.exit(fails.length ? 1 : 0);
