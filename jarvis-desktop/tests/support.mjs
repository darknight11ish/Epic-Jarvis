/**
 * "Chat with customer support for me" on the desktop (the owner's decisions
 * of 2026-09-28; JARVIS-API.md section 65; src/support.js, brain.js
 * paintSupport, src-tauri/src/brain/support.rs).
 *
 * What must hold:
 * - the words are the PC's (jarvis_support.WORDS) and the phone's, word for
 *   word;
 * - every real answer (fixtures/support-cases.json, made by the real routes
 *   and support loop) reads: the companies, the version, the chat, its state
 *   in the PC's words (waiting for the chat, the queue, the agent), its
 *   buttons, a waiting offer, a question handed to the owner;
 * - the Brain's Work tab: the form (the company and its terms risk, the
 *   goal, the details as name-and-value rows, the limits) asks for ONE card
 *   and sends nothing itself; a waiting offer shows its words and the exact
 *   reply its card would send, and offers Decline / Say something else /
 *   Take over - never an Accept button (accepting is only the card); the
 *   transcript marks the company's words as outside text; after the end the
 *   summary, the reference, "kept in your encrypted chat history" and
 *   Export stay on screen; Start, Decline, Say and Resume wait on a stale
 *   link, Stop and Take over do not;
 * - CONTROL: Rust holds start and the sending answers on a stale link and
 *   not stop, take over or status; hides the owner's words while the private
 *   lists are hidden; export needs the lists shown; the commands are the
 *   Brain's alone; nothing in this window speaks the company's words.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actionsOf,
  detailRows,
  formProblem,
  holdingLine,
  offerActions,
  progressLine,
  readSupport,
  savedLine,
  statusLine,
  talkingLine,
  versionLine,
  whoOf,
  WORDS,
} from "../src/support.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/support-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

await check("the words are the PC's and the phone's, word for word", async () => {
  assert.deepEqual(WORDS, CASES.words);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Support.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const [key, words] of Object.entries(WORDS)) {
    assert.ok(kt.includes(`"${words.replace(/"/g, '\\"')}"`), `the phone does not say ${key}: ${words}`);
  }
  const html = read("src/brain.html");
  for (const k of ["detail", "goal_note", "details_note", "start_note", "sign_in_pc"]) {
    assert.ok(html.includes(`>${WORDS[k]}</p>`), `the form does not say ${k}`);
  }
  assert.ok(html.includes(`<h2>${WORDS.title}</h2>`));
  assert.ok(read("src-tauri/src/brain/support.rs").includes(`"${WORDS.missing}"`));
});

await check("every real answer reads: companies, version, the chat and its buttons", async () => {
  const none = readSupport(CASES.nothing);
  assert.equal(none.available, true);
  assert.equal(none.chat, null);
  assert.deepEqual(none.companies.map((c) => [c.id, c.typed]), [["groupon", false], ["other", true]]);
  assert.match(none.companies[0].terms, /REAL Groupon account could be closed/);
  assert.match(versionLine(none), /^Version: the limited version \(one graphics card\) - basic chats/);
  const asking = readSupport(CASES.asking).chat;
  assert.equal(talkingLine(asking), "Waiting for your yes to chat with Groupon");
  assert.deepEqual(actionsOf(asking), ["stop"]);
  const queue = readSupport(CASES.in_queue).chat;
  assert.equal(statusLine(queue), "In the queue: number 2");
  assert.deepEqual(actionsOf(queue), ["take_over", "stop"]);
  assert.equal(talkingLine(queue), "Chat with Groupon: 1 of 15 messages");
  const offer = readSupport(CASES.offer_waiting).chat;
  assert.equal(talkingLine(offer), "Chat with Groupon: offer waiting");
  assert.equal(offer.offer.card, "waiting");
  assert.equal(offer.offer.reply, CASES.offer_accept_line);
  assert.deepEqual(offerActions(offer), ["decline", "say_else", "take_over"]);
  assert.equal(statusLine(offer), "Talking with Priya");
  const no = readSupport(CASES.offer_card_no).chat;
  assert.equal(no.offer.card, "no");
  const bot = readSupport(CASES.paused_bot_question).chat;
  assert.deepEqual(actionsOf(bot), ["resume", "stop"]);
  assert.match(statusLine(bot), /never claims to be a person/);
  assert.match(bot.question, /bot or a real person/);
  assert.equal(talkingLine(bot), "Paused: chat with Groupon");
  assert.equal(readSupport(CASES.paused_identity).chat.pausedCode, "identity");
  assert.equal(readSupport(CASES.paused_takeover).chat.takeOver, true);
  const done = readSupport(CASES.done).chat;
  assert.equal(done.live, false);
  assert.deepEqual(actionsOf(done), []);
  assert.equal(done.reference, "GRP48213");
  assert.equal(savedLine(done), WORDS.saved_yes);
  assert.ok(done.summary.answer && done.summary.agreed.length === 1);
  assert.ok(done.transcript.filter((t) => t.who === "company" || t.who === "system").every((t) => t.outside));
  assert.ok(done.transcript.filter((t) => t.who === "jarvis").every((t) => !t.outside));
  assert.equal(whoOf(done.transcript[0], done), WORDS.who_jarvis);
  assert.equal(whoOf(done.transcript.find((t) => t.who === "company"), done), "Groupon");
  assert.match(progressLine(done), /^Message 4 of 15 · /);
  assert.equal(readSupport(CASES.no_chat).chat.ended, CASES.no_chat.support.ended);
  assert.equal(readSupport(CASES.gone).chat, null);
  for (const nothing of [null, {}, { available: false }, "x", { chatbots: [], tier: {} }]) {
    const n = readSupport(nothing);
    assert.equal(n.available, false);
    assert.equal(n.why, WORDS.missing);
  }
  assert.equal(holdingLine({ offer: { holds: 2, holdsMost: 3 } }),
    "Jarvis told the agent \"One moment please\" 2 of 3 times.");
});

await check("History: a support chat's record reads, each line with its author, the same words as the phone's", async () => {
  const { readConversation, SUPPORT_WHO } = await import("../src/history-view.js");
  const conv = readConversation({ id: "support-sup_000000000003", title: "Support chat with Groupon - 2027-01-15",
    tainted: true, turns: [
      { role: "support", provenance: "support_note", text: "Details card", at: 1, read_outside: true },
      { role: "support", provenance: "support_company", text: "Hi", at: 2, read_outside: true },
      { role: "support", provenance: "support_jarvis", text: "Hello", at: 3, read_outside: true }] });
  assert.deepEqual(conv.turns.map((t) => [t.role, t.provenance]), [
    ["support", "support_note"], ["support", "support_company"], ["support", "support_jarvis"]]);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/ChatLog.kt");
  for (const [prov, words] of Object.entries(SUPPORT_WHO)) {
    assert.ok(kt.includes(`"${prov}" to "${words}"`), `the phone's History does not say ${words}`);
  }
});

await check("the form's own checks", async () => {
  const v = readSupport(CASES.nothing);
  const ok = { company: "groupon", address: "", goal: "Refund my voucher", rows: [],
    messages: "15", minutes: "30", queue: "45" };
  assert.equal(formProblem(v, ok), "");
  assert.equal(formProblem(v, { ...ok, goal: " " }), "Say what Jarvis should get done.");
  assert.equal(formProblem(v, { ...ok, company: "other" }), "Type the company's help page, starting with https://");
  assert.equal(formProblem(v, { ...ok, company: "other", address: "https://help.example.com" }), "");
  assert.equal(formProblem(v, { ...ok, rows: [{ name: "Email", value: "" }] }), "The detail \"Email\" has no value.");
  assert.equal(formProblem(v, { ...ok, messages: "26" }), "Most messages: 1 to 25 in this version.");
  assert.deepEqual(detailRows([{ name: "  Order  number ", value: " 12 " }, { name: "", value: "" }]),
    [{ name: "Order number", value: "12" }]);
  assert.equal(CASES.start_refused_detail.code, 400);
  assert.match(CASES.start_refused_detail.body.error, /can never be on the card/);
  assert.equal(CASES.answer_accept_refused.code, 400);
  assert.equal(CASES.answer_say_yes_refused.code, 400);
  assert.equal(CASES.answer_decline.code, 202);
});

await check("CONTROL: Rust holds what sends, hides the owner's words, Brain only", async () => {
  const rs = read("src-tauri/src/brain/support.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  const start = fn("support_start");
  assert.ok(start.indexOf("require_link_live") >= 0 && start.indexOf("require_link_live") < start.indexOf("post("),
    "support_start is not held on a stale link");
  assert.match(fn("support_answer"), /if choice != "takeover" \{\s*require_link_live/);
  for (const free of ["support_stop", "support_takeover", "support_status"]) {
    assert.ok(!fn(free).includes("require_link_live"), `${free} is held on a stale link`);
  }
  assert.match(fn("support_status"), /private_hidden\(&app\)[\s\S]*hide_words\(answer\)/);
  assert.match(fn("support_export"), /require_private_shown/);
  const cmds = ["support_status", "support_start", "support_stop", "support_takeover",
    "support_answer", "support_export"];
  for (const cmd of cmds) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::support::${cmd},`));
  }
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  for (const cmd of cmds) {
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["support"], `${cmd} is in ${holders}`);
  }
  const caps = (w) => JSON.parse(read(`src-tauri/capabilities/${w}.json`)).permissions;
  assert.ok(caps("brain").includes("support"));
  for (const other of ["widget", "quickbar", "hud", "settings", "faces", "floating", "onboarding"]) {
    assert.ok(!caps(other).includes("support"), `${other} holds the support set`);
  }
  const js = read("src/brain.js");
  const part = js.slice(js.indexOf("Chat with customer support for me (the owner's"),
    js.indexOf("Coming up - timers, alarms"));
  assert.ok(part.length > 1000, "the support part of the Brain was not found");
  assert.ok(!/speak\(|speakText|speechSynthesis|say_text|voice_say/i.test(part),
    "the support part of the Brain speaks");
  assert.ok(!/choice: "accept"|"Accept"/.test(part), "the Brain offers an Accept of its own");
});

/* ── The window ───────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1600 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

await check("Brain, start: the company, its terms risk, the details rows, ONE card asked for", async () => {
  const page = await workTab({ support: { status: CASES.nothing } });
  const companies = await page.locator("#support-company option").evaluateAll((os) => os.map((o) => o.value));
  const terms = await page.locator("#support-terms").innerText();
  const address = await page.locator("#support-address-label").isHidden();
  const msgs = await page.locator("#support-messages").inputValue();
  await page.locator("#support-goal").fill("Refund my spa voucher: the spa closed.");
  await page.locator("#support-rows input").nth(0).fill("Order number");
  await page.locator("#support-rows input").nth(1).fill("4481902217");
  await page.locator("#support-add").click();
  await page.locator("#support-rows input").nth(2).fill("Email");
  await page.locator("#support-rows input").nth(3).fill("alex.q@example.net");
  await page.locator("#support-start").click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__supportCalls);
  const toast = await page.locator("#toast").innerText();
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(companies, ["groupon", "other"]);
  assert.match(terms, /^Terms risk: Groupon's terms reportedly forbid/);
  assert.equal(address, true, "the address box showed for Groupon");
  assert.equal(msgs, "15");
  assert.deepEqual(sent, [{ cmd: "support_start", company: "groupon", address: null,
    goal: "Refund my spa voucher: the spa closed.",
    details: [{ name: "Order number", value: "4481902217" }, { name: "Email", value: "alex.q@example.net" }],
    maxMessages: 15, maxMinutes: 30, maxQueueMinutes: 45 }]);
  assert.match(toast, /Nothing has been sent yet/);
  assert.deepEqual(errors || [], []);
});

await check("Brain, another company: the help page's address is asked for and sent", async () => {
  const page = await workTab({ support: { status: CASES.nothing } });
  await page.locator("#support-company").selectOption("other");
  await page.waitForTimeout(200);
  const shown = await page.locator("#support-address-label").isVisible();
  await page.locator("#support-goal").fill("Cancel my order");
  await page.locator("#support-start").click();
  await page.waitForTimeout(300);
  const first = await page.evaluate(() => window.__supportCalls.length);
  const toast = await page.locator("#toast").innerText();
  await page.locator("#support-address").fill("https://help.example.com/chat");
  await page.locator("#support-start").click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__supportCalls);
  await page.close();
  assert.equal(shown, true);
  assert.equal(first, 0, "a start went with no address");
  assert.match(toast, /https:\/\//);
  assert.equal(sent[0].address, "https://help.example.com/chat");
  assert.equal(sent[0].company, "other");
});

await check("Brain, an offer waiting: its words, the exact reply, Decline / Say / Take over - no Accept", async () => {
  const page = await workTab({ support: { status: CASES.offer_waiting } });
  const text = await page.locator("#support").evaluate((n) => n.textContent);
  const buttons = await page.locator("#support .support-offer button").allInnerTexts();
  const form = await page.locator("#support-form").isHidden();
  await page.getByRole("button", { name: WORDS.decline }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: WORDS.say_else }).click();
  await page.locator("#support-say").fill("Could it go to my Groupon balance instead?");
  await page.locator("#support-say-send").click();
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__supportCalls);
  await page.close();
  const id = CASES.offer_waiting.support.id;
  assert.ok(text.includes(WORDS.offer_title));
  assert.ok(text.includes(CASES.offer_waiting.support.offer.words));
  assert.ok(text.includes(`"${CASES.offer_accept_line}"`), "the exact reply was not shown");
  assert.ok(text.includes(WORDS.offer_note));
  assert.deepEqual(buttons, [WORDS.decline, WORDS.say_else, WORDS.take_over]);
  assert.ok(!buttons.some((b) => /accept/i.test(b)), "an Accept button was offered");
  assert.equal(form, true, "the start form showed during a chat");
  assert.deepEqual(sent, [
    { cmd: "support_answer", id, offer: 1, choice: "decline", text: null },
    { cmd: "support_answer", id, offer: 1, choice: "say",
      text: "Could it go to my Groupon balance instead?" },
  ]);
});

await check("Brain, the offer card said no: it says so, and the choices stay", async () => {
  const page = await workTab({ support: { status: CASES.offer_card_no } });
  const text = await page.locator("#support").evaluate((n) => n.textContent);
  await page.close();
  assert.ok(text.includes(WORDS.offer_card_no));
});

await check("Brain, 'are you a bot?' handed over: the question, Resume and Stop", async () => {
  const page = await workTab({ support: { status: CASES.paused_bot_question } });
  const text = await page.locator("#support").evaluate((n) => n.textContent);
  const buttons = await page.locator("#support .support-now > .row-actions button").allInnerTexts();
  await page.getByRole("button", { name: "Resume" }).click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__chatbotCalls);
  await page.close();
  assert.ok(text.includes(WORDS.question_title) && text.includes(WORDS.question_note));
  assert.ok(text.includes(CASES.paused_bot_question.support.question));
  assert.deepEqual(buttons, ["Resume", "Stop"]);
  assert.deepEqual(calls, [{ cmd: "chatbot_resume" }], "Resume is not the task's own card");
});

await check("Brain, in the queue: its line, Take over and Stop; the transcript as outside text", async () => {
  const page = await workTab({ support: { status: CASES.in_queue } });
  const head = await page.locator("#support .chatbot-head").innerText();
  const line = await page.locator("#support .chatbot-line").innerText();
  const turns = await page.locator("#support-log .chatbot-turn").evaluateAll((ts) => ts.map((t) => [
    t.dataset.who, t.classList.contains("chatbot-outside")]));
  await page.getByRole("button", { name: WORDS.take_over }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__supportCalls);
  await page.close();
  const id = CASES.in_queue.support.id;
  assert.equal(head, "Chat with Groupon: 1 of 15 messages");
  assert.equal(line, "In the queue: number 2");
  assert.deepEqual(turns, [["jarvis", false], ["system", true]]);
  assert.deepEqual(sent, [{ cmd: "support_takeover", id }, { cmd: "support_stop", id }]);
});

await check("Brain, stale link: Start, Decline, Say's Send and Resume wait; Stop and Take over do not", async () => {
  let page = await workTab({ support: { status: CASES.offer_waiting }, link: { stale: true } });
  await page.getByRole("button", { name: WORDS.say_else }).click();
  const states = await page.locator("#support button").evaluateAll((bs) =>
    bs.map((b) => [b.textContent, b.disabled]));
  await page.close();
  const got = Object.fromEntries(states);
  assert.equal(got[WORDS.decline], true);
  assert.equal(got[WORDS.say_send], true);
  assert.equal(got[WORDS.take_over], false);
  assert.equal(got.Stop, false);
  page = await workTab({ support: { status: CASES.paused_bot_question }, link: { stale: true } });
  const resume = await page.getByRole("button", { name: "Resume" }).isDisabled();
  await page.close();
  assert.equal(resume, true);
  page = await workTab({ support: { status: CASES.nothing }, link: { stale: true } });
  const start = await page.locator("#support-start").isDisabled();
  await page.close();
  assert.equal(start, true, "Start was offered on a stale link");
});

await check("Brain, after it ends: summary, reference, kept, Export (with its not-encrypted note)", async () => {
  const page = await workTab({ support: { status: CASES.done } });
  const log = await page.locator("#support-log").evaluate((n) => n.textContent);
  await page.locator("#support-export").click();
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__supportCalls);
  const toast = await page.locator("#toast").innerText();
  const form = await page.locator("#support-form").isVisible();
  await page.close();
  assert.ok(log.includes(WORDS.summary_title) && log.includes("outside text"));
  assert.ok(log.includes(CASES.done.support.summary.answer));
  assert.ok(log.includes("Reference number: GRP48213"));
  assert.ok(log.includes(WORDS.saved_yes));
  assert.ok(log.includes(WORDS.export_note));
  assert.deepEqual(sent, [{ cmd: "support_export", id: CASES.done.support.id }]);
  assert.match(toast, /NOT encrypted/);
  assert.equal(form, true, "a new chat could not be started after one ended");
});

await check("Brain: the owner's words are hidden with the private lists", async () => {
  const hidden = JSON.parse(JSON.stringify(CASES.offer_waiting));
  Object.assign(hidden.support, { goal: "", details: [], transcript: [], question: "",
    summary: null, reference: "", ended: "", paused: "", hidden: true });
  Object.assign(hidden.support.offer, { words: "", reply: "", said: "" });
  const page = await workTab({ support: { status: hidden } });
  const text = await page.locator("#support-card").evaluate((n) => n.textContent);
  await page.close();
  assert.ok(!text.includes(CASES.offer_waiting.support.goal), text);
  assert.ok(!text.includes("4481902217"));
  assert.ok(text.includes(WORDS.hidden));
  assert.ok(text.includes("Chat with Groupon: offer waiting"));
});

await check("Brain: a PC without support chats says so; an activity event reads it again", async () => {
  let page = await workTab({});
  const text = await page.locator("#support").innerText();
  const form = await page.locator("#support-form").isHidden();
  await page.close();
  assert.equal(text.trim(), WORDS.missing);
  assert.equal(form, true);
  page = await workTab({ support: { status: CASES.in_queue } });
  const before = await page.evaluate(() => window.__support.reads);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "activity", id: 9, data: { value: "working", detail: "Chat with Groupon: message 2 of 15." } }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__support.reads);
  await page.close();
  assert.ok(after > before, `${before} -> ${after}`);
});

await browser.close();
await close();

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
