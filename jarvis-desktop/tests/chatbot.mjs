/**
 * "Talk to a chatbot for me" on the desktop (the owner's decisions of
 * 2026-09-27 and 2026-09-28; JARVIS-API.md section 60; src/chatbot.js,
 * brain.js paintChatbot, src-tauri/src/brain/chatbot.rs).
 *
 * What must hold:
 * - the words are the PC's (jarvis_chatbot_routes.WORDS) and the phone's,
 *   word for word;
 * - every real answer (fixtures/chatbot-cases.json, made by the real routes
 *   and driver loop) reads: the version, the conversation, its buttons;
 * - the Brain's Work tab: the form (the goal marked "these words will be
 *   sent", limits within the version's caps, never-send words) asks for a
 *   card and sends nothing itself; a live conversation shows its state, the
 *   counts, Pause/Resume/Stop and Change limits, the transcript with the
 *   chatbot's words marked outside text; the summary stays on screen after
 *   it ends; Start, Resume and Change limits wait on a stale link, Stop and
 *   Pause do not; with nothing built Start is greyed and says why;
 * - CONTROL: Rust holds start/limits/resume on a stale link and not stop or
 *   pause, takes the owner's words out while the private lists are hidden,
 *   and the commands are the Brain's alone; nothing in this window speaks a
 *   chatbot's words.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actionsOf,
  formProblem,
  limitOf,
  neverWords,
  progressLine,
  readChatbot,
  statusLine,
  talkingLine,
  versionLine,
  WORDS,
} from "../src/chatbot.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/chatbot-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

await check("the words are the PC's and the phone's, word for word", async () => {
  assert.deepEqual(WORDS, CASES.words);
  const kt = readRepo("jarvis-client/app/src/main/java/com/jarvis/client/net/Chatbot.kt")
    .replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const [key, words] of Object.entries(WORDS)) {
    assert.ok(kt.includes(`"${words.replace(/"/g, '\\"')}"`), `the phone does not say ${key}: ${words}`);
  }
  const html = read("src/brain.html");
  assert.ok(html.includes(`<h2>${WORDS.title}</h2>`));
  assert.ok(html.includes(`>${WORDS.detail}</p>`));
  assert.ok(html.includes(`>${WORDS.goal_note}</p>`), "the form does not say the goal is sent");
  assert.ok(html.includes(`>${WORDS.start_note}</p>`));
  assert.ok(read("src-tauri/src/brain/chatbot.rs").includes(`"${WORDS.missing}"`));
});

await check("every real answer reads: version, conversation, buttons", async () => {
  const none = readChatbot(CASES.nothing_built);
  assert.equal(none.available, true);
  assert.equal(none.anyBuilt, false, "Gemini is not built yet, and must not read as built");
  assert.equal(none.session, null);
  assert.match(versionLine(none), /^Version: the limited version \(one graphics card\) - /);
  const asking = readChatbot(CASES.asking).session;
  assert.equal(asking.state, "asking");
  assert.deepEqual(actionsOf(asking), ["stop"]);
  assert.equal(talkingLine(asking), "Waiting for your yes to talk to Gemini");
  const run = readChatbot(CASES.running).session;
  assert.deepEqual(actionsOf(run), ["pause", "stop"]);
  assert.equal(talkingLine(run), "Talking to Gemini, 2 of 4");
  assert.equal(progressLine(run), "Message 2 of 4 · 0.1 of 10 minutes".replace("0.1", String(run.minutesUsed)));
  assert.ok(run.transcript.filter((t) => t.who === "chatbot").every((t) => t.outside));
  assert.ok(run.transcript.filter((t) => t.who === "jarvis").every((t) => !t.outside));
  const paused = readChatbot(CASES.paused_captcha).session;
  assert.deepEqual(actionsOf(paused), ["resume", "stop"]);
  assert.match(statusLine(paused), /captcha/);
  assert.equal(talkingLine(paused), "Paused: talking to Gemini, 2 of 4");
  const stopped = readChatbot(CASES.stopped).session;
  assert.equal(stopped.paused, "", "a stopped conversation still read as paused");
  assert.deepEqual(actionsOf(stopped), []);
  assert.equal(statusLine(stopped), "You stopped it. Nothing more is sent.");
  const done = readChatbot(CASES.done_goal_met).session;
  assert.equal(done.live, false);
  assert.ok(done.summary && done.summary.answer && done.summary.claims.length === 2);
  assert.equal(readChatbot(CASES.done_goal_met).limits.said, "The new limits apply from the next message.");
  assert.ok(readChatbot(CASES.asked_about_you).session.question);
  for (const nothing of [null, {}, { available: false }, "x"]) {
    const n = readChatbot(nothing);
    assert.equal(n.available, false);
    assert.equal(n.why, WORDS.missing);
  }
  assert.deepEqual(neverWords(" Project  Nimbus, , project nimbus,Aunt Rosa "), ["Project Nimbus", "Aunt Rosa"]);
  assert.equal(limitOf("5", 8), 5);
  assert.equal(limitOf("9", 8), null);
  assert.equal(limitOf("0", 8), null);
  const built = readChatbot(CASES.running);
  assert.equal(formProblem(none, { chatbot: "gemini_web", goal: "x", messages: "5", minutes: "10" }),
    "Gemini is not built yet.");
  assert.equal(formProblem(built, { chatbot: "gemini_web", goal: " ", messages: "5", minutes: "10" }),
    "Say what Jarvis should find out.");
  assert.equal(formProblem(built, { chatbot: "gemini_web", goal: "x", messages: "20", minutes: "10" }),
    "Most messages: 1 to 8 in this version.");
  assert.equal(formProblem(built, { chatbot: "gemini_web", goal: "x", messages: "5", minutes: "10" }), "");
});

await check("CONTROL: Rust holds what sends, hides the owner's words, Brain only", async () => {
  const rs = read("src-tauri/src/brain/chatbot.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  for (const held of ["chatbot_start", "chatbot_limits", "chatbot_resume"]) {
    const f = fn(held);
    assert.ok(f.indexOf("require_link_live") >= 0 && f.indexOf("require_link_live") < f.indexOf("post("),
      `${held} is not held on a stale link`);
  }
  for (const free of ["chatbot_stop", "chatbot_pause", "chatbot_status"]) {
    assert.ok(!fn(free).includes("require_link_live"), `${free} is held on a stale link`);
  }
  assert.match(fn("chatbot_status"), /private_hidden\(&app\)[\s\S]*hide_words\(answer\)/);
  assert.match(fn("chatbot_pause"), /"\/api\/task\/pause"/);
  assert.match(fn("chatbot_resume"), /"\/api\/task\/resume"/);
  const cmds = ["chatbot_status", "chatbot_start", "chatbot_limits", "chatbot_stop", "chatbot_pause", "chatbot_resume"];
  for (const cmd of cmds) {
    assert.match(read("src-tauri/build.rs"), new RegExp(`"${cmd}"`));
    assert.match(read("src-tauri/src/lib.rs"), new RegExp(`brain::chatbot::${cmd},`));
  }
  const sets = read("src-tauri/permissions/surfaces.toml").split("[[set]]").slice(1);
  for (const cmd of cmds) {
    const holders = sets.filter((s) => s.includes(`"allow-${cmd.replace(/_/g, "-")}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["chatbot"], `${cmd} is in ${holders}`);
  }
  const caps = (w) => JSON.parse(read(`src-tauri/capabilities/${w}.json`)).permissions;
  assert.ok(caps("brain").includes("chatbot"));
  for (const other of ["widget", "quickbar", "hud", "settings", "faces", "floating", "onboarding"]) {
    assert.ok(!caps(other).includes("chatbot"), `${other} holds the chatbot set`);
  }
  // Nothing in the chatbot's part of the Brain speaks.
  const js = read("src/brain.js");
  const part = js.slice(js.indexOf("Talk to a chatbot for me (the owner's"), js.indexOf("Coming up - timers, alarms"));
  assert.ok(!/speak\(|speakText|speechSynthesis|say_text|"say"|voice_say/i.test(part),
    "the chatbot's part of the Brain speaks");
});

/* ── The window ───────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1400 };

async function workTab(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-work").click();
  await page.waitForTimeout(500);
  return page;
}

await check("Brain, nothing built: the form shows, Start is greyed and says why", async () => {
  const page = await workTab({ chatbot: { status: CASES.nothing_built } });
  const form = await page.locator("#chatbot-form").isVisible();
  const version = await page.locator("#chatbot-version").innerText();
  const text = await page.locator("#chatbot").innerText();
  const start = await page.locator("#chatbot-start").isDisabled();
  const options = await page.locator("#chatbot-which option").evaluateAll(
    (os) => os.map((o) => [o.textContent, o.disabled]));
  const errors = page.__errors;
  await page.close();
  assert.equal(form, true);
  assert.match(version, /one graphics card/);
  assert.ok(text.includes(WORDS.none_built), text);
  assert.equal(start, true, "Start was offered with nothing built");
  assert.deepEqual(options, [["Gemini - Not built yet.", true]]);
  assert.deepEqual(errors, []);
});

await check("Brain, start: the form asks for the card with the goal as typed", async () => {
  const built = JSON.parse(JSON.stringify(CASES.latest_none));
  const page = await workTab({ chatbot: { status: built } });
  const msgs = await page.locator("#chatbot-messages").inputValue();
  const mins = await page.locator("#chatbot-minutes").inputValue();
  await page.locator("#chatbot-goal").fill("Find out which ferns suit a dark bathroom.");
  await page.locator("#chatbot-messages").fill("6");
  await page.locator("#chatbot-never").fill("Project Nimbus, Aunt Rosa");
  await page.locator("#chatbot-start").click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__chatbotCalls);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(msgs, String(built.tier.turns_default));
  assert.equal(mins, String(built.tier.minutes_default));
  assert.deepEqual(sent, [{ cmd: "chatbot_start", chatbot: "gemini_web",
    goal: "Find out which ferns suit a dark bathroom.", maxMessages: 6, maxMinutes: 10,
    neverSend: ["Project Nimbus", "Aunt Rosa"] }]);
  assert.match(toast, /Nothing has been sent yet/);
});

await check("Brain, start: too many messages for this version is refused here", async () => {
  const page = await workTab({ chatbot: { status: CASES.latest_none } });
  await page.locator("#chatbot-goal").fill("Anything");
  await page.locator("#chatbot-messages").fill("12");
  await page.locator("#chatbot-start").click();
  await page.waitForTimeout(400);
  const sent = await page.evaluate(() => window.__chatbotCalls);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(sent, []);
  assert.match(toast, /Most messages: 1 to 8 in this version\./);
});

await check("Brain, start refused by the PC: its sentence is shown", async () => {
  const page = await workTab({ chatbot: { status: CASES.latest_none,
    startRefuses: CASES.start_goal_refused.body.error } });
  await page.locator("#chatbot-goal").fill("x");
  await page.locator("#chatbot-start").click();
  await page.waitForTimeout(400);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.equal(toast.trim(), CASES.start_goal_refused.body.error);
});

await check("Brain, running: state, counts, Pause and Stop, limits, the transcript as outside text", async () => {
  const page = await workTab({ chatbot: { status: CASES.running } });
  const head = await page.locator("#chatbot .chatbot-head").innerText();
  const buttons = await page.locator("#chatbot .row-actions button").allInnerTexts();
  const form = await page.locator("#chatbot-form").isHidden();
  const turns = await page.locator("#chatbot-log .chatbot-turn").evaluateAll((ts) => ts.map((t) => [
    t.dataset.who, t.classList.contains("chatbot-outside"),
    Boolean(t.querySelector(".history-mark-taint"))]));
  const text = await page.locator("#chatbot-card").innerText();
  await page.getByRole("button", { name: "Pause" }).click();
  await page.waitForTimeout(300);
  await page.locator("#chatbot-new-messages").fill("6");
  await page.locator("#chatbot-limits-go").click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__chatbotCalls);
  await page.close();
  assert.equal(head, "Talking to Gemini, 2 of 4");
  assert.deepEqual(buttons, ["Pause", "Stop"]);
  assert.equal(form, true, "the start form showed during a conversation");
  assert.deepEqual(turns, [["jarvis", false, false], ["chatbot", true, true], ["jarvis", false, false]]);
  assert.ok(text.includes(WORDS.outside_note));
  assert.ok(text.includes(WORDS.limits_note));
  assert.ok(text.includes("Version: the limited version (one graphics card)"));
  const id = CASES.running.session.id;
  assert.deepEqual(sent, [
    { cmd: "chatbot_pause" },
    { cmd: "chatbot_limits", id, maxMessages: 6, maxMinutes: 10, neverSend: ["Project Nimbus"] },
    { cmd: "chatbot_stop", id },
  ]);
});

await check("Brain, running: a re-read does not wipe limits being typed, or take the focus", async () => {
  const page = await workTab({ chatbot: { status: CASES.running } });
  await page.locator("#chatbot-new-messages").fill("7");
  await page.locator("#chatbot-new-messages").focus();
  const before = await page.evaluate(() => window.__chatbot.reads);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "activity", id: 9, data: { value: "working", detail: "Talking to Gemini: message 3 of 4." } }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__chatbot.reads);
  const value = await page.locator("#chatbot-new-messages").inputValue();
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.id);
  await page.close();
  assert.ok(after > before, "it did not read again");
  assert.equal(value, "7");
  assert.equal(focused, "chatbot-new-messages");
});

await check("Brain, paused at a captcha: the PC's words, Resume and Stop", async () => {
  const page = await workTab({ chatbot: { status: CASES.paused_captcha } });
  const text = await page.locator("#chatbot").innerText();
  const buttons = await page.locator("#chatbot .row-actions button").allInnerTexts();
  await page.close();
  assert.match(text, /captcha/);
  assert.match(text, /never solves or skips/);
  assert.deepEqual(buttons, ["Resume", "Stop"]);
});

await check("Brain, stale link: Resume and Change limits wait, Stop does not; Start waits", async () => {
  let page = await workTab({ chatbot: { status: CASES.paused_captcha }, link: { stale: true } });
  const states = await page.locator("#chatbot button, #chatbot-limits button").evaluateAll(
    (bs) => bs.map((b) => [b.textContent, b.disabled]));
  await page.close();
  assert.deepEqual(states, [["Resume", true], ["Stop", false], ["Change limits", true]]);
  page = await workTab({ chatbot: { status: CASES.latest_none }, link: { stale: true } });
  const start = await page.locator("#chatbot-start").isDisabled();
  await page.close();
  assert.equal(start, true, "Start was offered on a stale link");
});

await check("Brain, after it ends: the summary stays on screen, marked outside text", async () => {
  // The latest live one is none; the one this window last showed is read by id.
  const page = await workTab({ chatbot: { status: CASES.latest_none, named: CASES.done_goal_met } });
  // The window only knows an id once it has seen one: start one first.
  await page.locator("#chatbot-goal").fill("x");
  await page.locator("#chatbot-start").click();
  await page.waitForTimeout(600);
  const summary = await page.locator("#chatbot-log .chatbot-summary").evaluate((n) => n.textContent);
  const ids = await page.evaluate(() => window.__chatbot.ids);
  const form = await page.locator("#chatbot-form").isVisible();
  await page.close();
  assert.ok(summary.includes(WORDS.summary_title));
  assert.ok(summary.includes("outside text"));
  assert.ok(summary.includes(CASES.done_goal_met.session.summary.answer));
  assert.ok(summary.includes(WORDS.claim_sourced) && summary.includes(WORDS.claim_unsourced));
  assert.ok(ids.includes("chat_000000000001"), JSON.stringify(ids));
  assert.equal(form, true, "a new conversation could not be started after one ended");
});

await check("Brain, the chatbot asked about you: handed back, never answered", async () => {
  const page = await workTab({ chatbot: { status: CASES.asked_about_you } });
  const text = await page.locator("#chatbot").evaluate((n) => n.textContent);
  await page.close();
  assert.ok(text.includes(WORDS.question_title));
  assert.ok(text.includes(WORDS.question_note));
  assert.ok(text.includes(CASES.asked_about_you.session.question));
});

await check("Brain: the owner's words are hidden with the private lists", async () => {
  // What Rust sends while "Hide memory lists and chat history" hides them.
  const hidden = JSON.parse(JSON.stringify(CASES.running));
  Object.assign(hidden.session, { goal: "", transcript: [], summary: null, question: "",
    never_send: [], ended: "", hidden: true });
  const page = await workTab({ chatbot: { status: hidden } });
  const text = await page.locator("#chatbot").innerText();
  await page.close();
  assert.ok(!text.includes(CASES.running.session.goal), text);
  assert.ok(text.includes(WORDS.hidden));
  assert.ok(text.includes("Talking to Gemini, 2 of 4"));
});

await check("Brain: a PC without the routes says so", async () => {
  const page = await workTab({});
  const text = await page.locator("#chatbot").innerText();
  const form = await page.locator("#chatbot-form").isHidden();
  await page.close();
  assert.equal(text.trim(), WORDS.missing);
  assert.equal(form, true);
});

await check("Brain: an activity event reads it again", async () => {
  const page = await workTab({ chatbot: { status: CASES.running } });
  const before = await page.evaluate(() => window.__chatbot.reads);
  await page.evaluate(() => window.__emit("jarvis-event",
    { kind: "activity", id: 9, data: { value: "working", detail: "Talking to Gemini: message 3 of 4." } }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__chatbot.reads);
  await page.close();
  assert.ok(after > before, `${before} -> ${after}`);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nTalk to a chatbot for me: the PC's words, one card to start, outside text marked, held on a stale link");
process.exit(fails.length ? 1 : 0);
