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
 * - "Ask several and compare": the tick box shows one box per chatbot and
 *   asks for ONE card with the ticked ones; a comparison shows each
 *   chatbot's line, Pause/Resume/Stop for the whole of it, each conversation
 *   under its name, and at the end ONE summary (agree, disagree - who said
 *   what -, sources not checked, who dropped out) as outside text; Start is
 *   held on a stale link, Stop is not.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  actionsOf,
  chatbotGroups,
  usageLine,
  moneyLine,
  compareFormProblem,
  compareStatusLine,
  compareTalkingLine,
  memberLine,
  pickLine,
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
  assert.ok(html.includes(WORDS.compare_toggle), "the form has no compare tick box");
  assert.ok(html.includes(`>${WORDS.compare_detail}</p>`));
  assert.ok(html.includes(`>${WORDS.compare_limits_note}</p>`));
  assert.ok(read("src-tauri/src/brain/chatbot.rs").includes(`"${WORDS.missing}"`));
});

await check("every real answer reads: version, conversation, buttons", async () => {
  const none = readChatbot(CASES.not_ready);
  assert.equal(none.available, true);
  assert.equal(none.anyBuilt, false, "Gemini is built but not signed in on this PC, and must not read as usable");
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
  // Built but not set up on this PC: the form says exactly what is missing.
  assert.equal(formProblem(none, { chatbot: "gemini_web", goal: "x", messages: "5", minutes: "10" }),
    `${CASES.not_ready.chatbots[0].note}.`);
  assert.equal(formProblem(built, { chatbot: "gemini_web", goal: " ", messages: "5", minutes: "10" }),
    "Say what Jarvis should find out.");
  assert.equal(formProblem(built, { chatbot: "gemini_web", goal: "x", messages: "20", minutes: "10" }),
    "Most messages: 1 to 8 in this version.");
  assert.equal(formProblem(built, { chatbot: "gemini_web", goal: "x", messages: "5", minutes: "10" }), "");
});

await check("a comparison reads: every chatbot, its lines, the summary, the form's checks", async () => {
  const none = readChatbot(CASES.compare_none);
  assert.equal(none.compare, null);
  assert.equal(none.tier.compareMin, 2);
  assert.equal(none.tier.compareMax, 3);
  assert.equal(none.canCompare, true);
  assert.equal(pickLine(none), "Chatbots to ask (pick 2 to 3)");
  assert.equal(readChatbot(CASES.not_ready).canCompare, false, "nothing usable, yet it could compare");
  const asking = readChatbot(CASES.compare_asking).compare;
  assert.equal(compareTalkingLine(asking), "Waiting for your yes to ask 3 chatbots");
  assert.deepEqual(actionsOf(asking), ["stop"]);
  const run = readChatbot(CASES.compare_running);
  assert.equal(run.session, null, "a comparison's conversation read as the single one");
  assert.equal(compareTalkingLine(run.compare), "Comparing 3 chatbots: asking ChatGPT, 2 of 3");
  assert.deepEqual(actionsOf(run.compare), ["pause", "stop"]);
  assert.deepEqual(run.compare.members.map((m) => memberLine(m, run.compare)), [
    "Gemini: It used all 3 messages you allowed.", "ChatGPT: Talking now.", "Claude: Waiting its turn."]);
  assert.ok(run.compare.members.every((m) => m.transcript.filter((t) => t.who === "chatbot")
    .every((t) => t.outside)));
  const paused = readChatbot(CASES.compare_paused).compare;
  assert.deepEqual(actionsOf(paused), ["resume", "stop"]);
  assert.equal(compareStatusLine(paused), CASES.compare_paused.compare.paused);
  assert.equal(compareTalkingLine(paused), "Paused: comparing 2 chatbots");
  const done = readChatbot(CASES.compare_done).compare;
  assert.equal(done.live, false);
  assert.equal(compareTalkingLine(done), "");
  const sm = done.summary;
  assert.ok(sm.answer && sm.agree.length === 2 && sm.byModel);
  assert.deepEqual(sm.disagree[0].views.map((v) => v.who), ["Gemini", "ChatGPT"]);
  assert.deepEqual(sm.dropped.map((d) => d.who), ["Claude"]);
  assert.match(sm.dropped[0].why, /captcha/);
  assert.deepEqual(sm.sources.map((x) => x.who), ["Gemini", "ChatGPT"]);
  const stopped = readChatbot(CASES.compare_stopped).compare;
  assert.equal(stopped.paused, "", "a stopped comparison still read as paused");
  assert.deepEqual(actionsOf(stopped), []);
  const form = { goal: "x", messages: "3", minutes: "10" };
  assert.equal(compareFormProblem(none, { ...form, chatbots: ["gemini_web"] }),
    "Pick at least 2 chatbots to compare.");
  const four = JSON.parse(JSON.stringify(CASES.compare_none));
  four.chatbots.push({ id: "grok_web", name: "Grok", host: "grok.com", built: true, ready: true, note: "" });
  assert.equal(compareFormProblem(readChatbot(four),
    { ...form, chatbots: ["gemini_web", "chatgpt_web", "claude_web", "grok_web"] }),
  "Pick at most 3 chatbots in this version.");
  assert.equal(compareFormProblem(none, { ...form, goal: " ", chatbots: ["gemini_web", "chatgpt_web"] }),
    "Say what Jarvis should find out.");
  assert.equal(compareFormProblem(none, { ...form, chatbots: ["gemini_web", "chatgpt_web"] }), "");
  assert.equal(compareFormProblem(readChatbot(CASES.not_ready), { ...form, chatbots: ["gemini_web", "x"] }),
    WORDS.compare_not_enough);
  assert.equal(CASES.compare_too_few.body.error, WORDS.compare_too_few.replace("{min}", "2"));
  assert.equal(CASES.compare_card_lists.names.length, 3, "the card did not list every chatbot");
  assert.equal(CASES.compare_card_lists.goal_word_for_word, true);
});

await check("a long list is grouped by how each chatbot is reached; an API conversation's counts read", async () => {
  const v = readChatbot(CASES.long_list);
  assert.deepEqual(chatbotGroups(v).map((g) => [g.kind, g.title, g.chatbots.map((c) => c.id)]), [
    ["website", WORDS.kind_website, ["chatgpt_web", "gemini_web", "perplexity_web"]],
    ["api", WORDS.kind_api, ["openai_api", "deepseek_api", "groq_api"]],
    ["local", WORDS.kind_local, ["local_ai"]],
  ]);
  assert.deepEqual(v.chatbots.filter((c) => c.built).map((c) => c.id), ["openai_api", "gemini_web"]);
  assert.ok(v.chatbots.filter((c) => !c.built).every((c) => c.note), "a chatbot not ready gave no reason");
  const old = readChatbot({ ...CASES.long_list, chatbots: [{ id: "x", name: "X", built: true }] });
  assert.equal(old.chatbots[0].kind, "website", "an older PC's chatbot was not read as a website");
  const u = readChatbot(CASES.usage_done).session;
  assert.equal(usageLine(u.usage),
    "Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about $0.01");
  const members = readChatbot(CASES.compare_usage).compare.members;
  assert.deepEqual(members.map((m) => usageLine(m.usage)),
    ["", "Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about $0.01"]);
  assert.equal(usageLine({ requests: 1, tokens: 1234567, model: "" }),
    "Used so far: 1 request, 1,234,567 word-pieces (tokens)");
  assert.equal(usageLine({ requests: 2, tokens: 10, model: "m", cost: "" }),
    "Used so far: 2 requests, 10 word-pieces (tokens), model m", "an older PC's usage grew a cost");
  assert.equal(readChatbot(CASES.running).session.usage, null, "a website conversation grew a usage line");
});

await check("an answer the money limit's cap cut short is read as cut off, and only that one", async () => {
  const turns = readChatbot(CASES.cut_off).session.transcript;
  assert.deepEqual(turns.map((t) => [t.who, t.cutOff]),
    [["jarvis", false], ["chatbot", true], ["jarvis", false], ["chatbot", false]]);
  assert.ok(readChatbot(CASES.running).session.transcript.every((t) => !t.cutOff),
    "a website conversation grew a cut-off note");
  const forged = readChatbot({ ...CASES.cut_off, session: { ...CASES.cut_off.session,
    transcript: [{ who: "jarvis", n: 1, text: "x", cut_off: true }] } }).session.transcript;
  assert.equal(forged[0].cutOff, false, "Jarvis's own message was marked cut off");
});

await check("an API service's money limit reads as the PC wrote it; reached, and never set", async () => {
  const v = readChatbot(CASES.long_list);
  const openai = v.chatbots.find((c) => c.id === "openai_api");
  assert.equal(moneyLine(openai),
    "About $4.55 of $5.00 left this month for OpenAI (prices are estimates you can correct on the PC).");
  assert.ok(v.chatbots.filter((c) => c.id !== "openai_api").every((c) => c.money === null),
    "a chatbot with no limit grew a money line");
  const r = readChatbot(CASES.money_reached);
  const reached = r.chatbots.find((c) => c.id === "openai_api");
  assert.equal(reached.built, false, "a service at its limit read as usable");
  assert.equal(reached.money.reached, true);
  assert.equal(moneyLine(reached),
    "About $0.00 of $1.00 left this month for OpenAI (prices are estimates you can correct on the PC).");
  assert.equal(formProblem(r, { chatbot: "openai_api", goal: "x", messages: 3, minutes: 5 }),
    reached.note);
  assert.match(reached.note, /^You set \$1\.00 a month for OpenAI; about \$1\.02 is used this month\. .*October 1\.$/);
  const mistral = r.chatbots.find((c) => c.id === "mistral_api");
  assert.equal(mistral.money, null);
  assert.match(mistral.note, /^No monthly money limit is set for Mistral AI/);
  assert.equal(CASES.start_money_reached.code, 400);
  assert.equal(CASES.start_money_reached.body.error, reached.note);
  assert.match(CASES.start_no_limit.body.error, /limit mistral 5/);
});

await check("CONTROL: Rust holds what sends, hides the owner's words, Brain only", async () => {
  const rs = read("src-tauri/src/brain/chatbot.rs");
  const fn = (name) => {
    const f = rs.slice(rs.indexOf(`pub async fn ${name}(`));
    return f.slice(0, f.indexOf("\n}\n"));
  };
  for (const held of ["chatbot_start", "chatbot_limits", "chatbot_resume", "chatbot_compare_start"]) {
    const f = fn(held);
    assert.ok(f.indexOf("require_link_live") >= 0 && f.indexOf("require_link_live") < f.indexOf("post("),
      `${held} is not held on a stale link`);
  }
  for (const free of ["chatbot_stop", "chatbot_pause", "chatbot_status", "chatbot_compare_stop"]) {
    assert.ok(!fn(free).includes("require_link_live"), `${free} is held on a stale link`);
  }
  assert.match(fn("chatbot_status"), /private_hidden\(&app\)[\s\S]*hide_words\(answer\)/);
  assert.match(rs, /get_mut\("compare"\)[\s\S]*get_mut\("members"\)[\s\S]*hide_session\(m\)/,
    "a comparison's words are not hidden with the private lists");
  assert.match(fn("chatbot_pause"), /"\/api\/task\/pause"/);
  assert.match(fn("chatbot_resume"), /"\/api\/task\/resume"/);
  const cmds = ["chatbot_status", "chatbot_start", "chatbot_limits", "chatbot_stop", "chatbot_pause",
    "chatbot_resume", "chatbot_compare_start", "chatbot_compare_stop"];
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

await check("Brain, Gemini not set up on this PC: the form shows, Start is greyed and says why", async () => {
  const page = await workTab({ chatbot: { status: CASES.not_ready } });
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
  assert.deepEqual(options, [[`Gemini - ${CASES.not_ready.chatbots[0].note}`, true]]);
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

await check("Brain: an answer the money limit's cap cut short says so under it, word for word", async () => {
  const page = await workTab({ chatbot: { status: CASES.cut_off } });
  const notes = await page.locator("#chatbot-log .chatbot-turn").evaluateAll((ts) => ts.map((t) => {
    const n = t.querySelector(".chatbot-cut-off");
    return n ? n.textContent : "";
  }));
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(notes, ["", WORDS.cut_off, "", ""]);
  assert.deepEqual(errors || [], []);
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

/* ── A long list, grouped; what an API conversation used ────────────── */

await check("Brain, a long list: grouped under three headings, each not-ready one says why", async () => {
  const page = await workTab({ chatbot: { status: CASES.long_list } });
  const groups = await page.locator("#chatbot-which optgroup").evaluateAll((gs) => gs.map((g) => [
    g.label, [...g.querySelectorAll("option")].map((o) => [o.value, o.disabled])]));
  const picked = await page.locator("#chatbot-which").inputValue();
  await page.locator("#chatbot-compare").check();
  await page.waitForTimeout(200);
  const rows = await page.locator("#chatbot-several-list > *").evaluateAll((ns) => ns.map((n) =>
    n.tagName === "LABEL" ? ["box", n.querySelector("input").value, n.querySelector("input").disabled]
      : [n.className.includes("chatbot-kind") ? "heading" : n.className.includes("chatbot-money-line")
        ? "money" : n.className.includes("chatbot-money-note") ? "pc" : "why", n.textContent]));
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(groups, [
    [WORDS.kind_website, [["chatgpt_web", true], ["gemini_web", false], ["perplexity_web", true]]],
    [WORDS.kind_api, [["openai_api", false], ["deepseek_api", true], ["groq_api", true]]],
    [WORDS.kind_local, [["local_ai", true]]],
  ]);
  assert.equal(picked, "gemini_web", "the first usable chatbot was not picked");
  const note = (id) => CASES.long_list.chatbots.find((c) => c.id === id).note;
  assert.deepEqual(rows, [
    ["heading", WORDS.kind_website], ["box", "chatgpt_web", true], ["why", note("chatgpt_web")],
    ["box", "gemini_web", false], ["box", "perplexity_web", true], ["why", note("perplexity_web")],
    ["heading", WORDS.kind_api], ["box", "openai_api", false],
    ["money", "About $4.55 of $5.00 left this month for OpenAI (prices are estimates you can correct on the PC)."],
    ["box", "deepseek_api", true],
    ["why", note("deepseek_api")], ["box", "groq_api", true], ["why", note("groq_api")],
    ["pc", WORDS.money_pc_only],
    ["heading", WORDS.kind_local], ["box", "local_ai", true], ["why", note("local_ai")],
  ]);
  assert.deepEqual(errors, []);
});

await check("Brain, what an API conversation used: one line, alone and per chatbot in a comparison", async () => {
  let page = await workTab({ chatbot: { status: CASES.usage_done } });
  const one = await page.locator("#chatbot .chatbot-usage").allInnerTexts();
  await page.close();
  assert.deepEqual(one, ["Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about $0.01"]);
  page = await workTab({ chatbot: { status: CASES.compare_usage } });
  const each = await page.locator("#chatbot .chatbot-members li").evaluateAll((ls) => ls.map((l) => {
    const u = l.querySelector(".chatbot-usage");
    return u ? u.textContent : "";
  }));
  await page.close();
  assert.deepEqual(each, ["", "Used so far: 3 requests, 4,215 word-pieces (tokens), model gpt-5-mini, about $0.01"]);
});

await check("Brain, a service with a key: the money left under the chooser, and that it is set on the PC", async () => {
  const page = await workTab({ chatbot: { status: CASES.long_list } });
  const shown = async () => ({
    hidden: await page.locator("#chatbot-money").evaluate((n) => n.hidden),
    text: await page.locator("#chatbot-money").textContent(),
  });
  const onGemini = await shown();
  await page.locator("#chatbot-which").selectOption("openai_api");
  await page.waitForTimeout(100);
  const onOpenai = await shown();
  const errors = page.__errors;
  await page.close();
  assert.equal(onGemini.hidden, true, "a website showed a money line");
  assert.equal(onOpenai.hidden, false);
  assert.equal(onOpenai.text,
    "About $4.55 of $5.00 left this month for OpenAI (prices are estimates you can correct on the PC). "
    + WORDS.money_pc_only);
  assert.deepEqual(errors, []);
});

/* ── Ask several and compare ─────────────────────────────────────────── */

async function tickTwoAndStart(page, ids) {
  await page.locator("#chatbot-compare").check();
  await page.waitForTimeout(200);
  for (const id of ids) await page.locator(`#chatbot-several-list input[value="${id}"]`).check();
  await page.locator("#chatbot-goal").fill("Which ferns suit a dark bathroom?");
  await page.locator("#chatbot-messages").fill("3");
  await page.locator("#chatbot-start").click();
  await page.waitForTimeout(600);
}

await check("Brain, compare: the tick box shows every chatbot, and Start asks for ONE card", async () => {
  const page = await workTab({ chatbot: { status: CASES.compare_none } });
  const offBefore = await page.locator("#chatbot-several").isHidden();
  await page.locator("#chatbot-compare").check();
  await page.waitForTimeout(200);
  const legend = await page.locator("#chatbot-several-legend").innerText();
  const which = await page.locator("#chatbot-which-label").isHidden();
  const note = await page.locator("#chatbot-compare-note").isVisible();
  const detail = await page.locator("#chatbot-compare-detail").isVisible();
  const boxes = await page.locator("#chatbot-several-list input").evaluateAll(
    (bs) => bs.map((b) => [b.value, b.disabled]));
  await page.locator('#chatbot-several-list input[value="gemini_web"]').check();
  await page.locator('#chatbot-several-list input[value="claude_web"]').check();
  await page.locator("#chatbot-goal").fill("Which ferns suit a dark bathroom?");
  await page.locator("#chatbot-never").fill("Project Nimbus");
  await page.locator("#chatbot-start").click();
  await page.waitForTimeout(500);
  const sent = await page.evaluate(() => window.__chatbotCalls);
  const toast = await page.locator("#toast").innerText();
  const errors = page.__errors;
  await page.close();
  assert.equal(offBefore, true, "the tick boxes showed before compare was ticked");
  assert.equal(legend, "Chatbots to ask (pick 2 to 3)");
  assert.equal(which, true, "the single chatbot picker still showed");
  assert.equal(note && detail, true);
  assert.deepEqual(boxes, [["gemini_web", false], ["chatgpt_web", false], ["claude_web", false]]);
  assert.deepEqual(sent, [{ cmd: "chatbot_compare_start", chatbots: ["gemini_web", "claude_web"],
    goal: "Which ferns suit a dark bathroom?", maxMessages: 5, maxMinutes: 10,
    neverSend: ["Project Nimbus"] }]);
  assert.match(toast, /An approval card lists every chatbot/);
  assert.deepEqual(errors, []);
});

await check("Brain, compare: one tick is refused here, nothing asked", async () => {
  const page = await workTab({ chatbot: { status: CASES.compare_none } });
  await tickTwoAndStart(page, ["chatgpt_web"]);
  const sent = await page.evaluate(() => window.__chatbotCalls);
  const toast = await page.locator("#toast").innerText();
  await page.close();
  assert.deepEqual(sent, []);
  assert.equal(toast.trim(), "Pick at least 2 chatbots to compare.");
});

await check("Brain, comparing: each chatbot's line, Pause and Stop for the whole, each conversation as outside text", async () => {
  const page = await workTab({ chatbot: { status: CASES.compare_running } });
  const head = await page.locator("#chatbot .chatbot-head").innerText();
  const members = await page.locator("#chatbot .chatbot-members li").allInnerTexts();
  const buttons = await page.locator("#chatbot .row-actions button").allInnerTexts();
  const form = await page.locator("#chatbot-form").isHidden();
  const limits = await page.locator("#chatbot-limits").isHidden();
  const logs = await page.locator("#chatbot-log .chatbot-member-log").evaluateAll((ps) => ps.map((p) => [
    p.dataset.chatbot, p.querySelector("h4").textContent,
    [...p.querySelectorAll(".chatbot-turn")].every((t) => (t.dataset.who === "chatbot")
      === (t.classList.contains("chatbot-outside") && Boolean(t.querySelector(".history-mark-taint"))))]));
  const text = await page.locator("#chatbot-card").evaluate((n) => n.textContent);
  await page.getByRole("button", { name: "Pause" }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await page.waitForTimeout(300);
  const sent = await page.evaluate(() => window.__chatbotCalls);
  await page.close();
  assert.equal(head, "Comparing 3 chatbots: asking ChatGPT, 2 of 3");
  assert.deepEqual(members, ["Gemini: It used all 3 messages you allowed.", "ChatGPT: Talking now.",
    "Claude: Waiting its turn."]);
  assert.deepEqual(buttons, ["Pause", "Stop"]);
  assert.equal(form, true, "the start form showed during a comparison");
  assert.equal(limits, true, "Change limits showed for a comparison");
  assert.deepEqual(logs, [["gemini_web", "Gemini", true], ["chatgpt_web", "ChatGPT", true]]);
  assert.ok(text.includes(WORDS.conversations_title) && text.includes(WORDS.outside_note));
  assert.deepEqual(sent, [{ cmd: "chatbot_pause" },
    { cmd: "chatbot_compare_stop", id: CASES.compare_running.compare.id }]);
});

await check("Brain, after a comparison: ONE summary stays - agree, disagree by name, sources not checked, who dropped out", async () => {
  // The window only knows a comparison's id once it has started one; the
  // PC then answers the read by that id with the finished comparison.
  const page = await workTab({ chatbot: { status: CASES.compare_none, namedCompare: CASES.compare_done } });
  await tickTwoAndStart(page, ["gemini_web", "chatgpt_web"]);
  const summary = await page.locator("#chatbot-log .chatbot-compare-summary").evaluate((n) => n.textContent);
  const outside = await page.locator("#chatbot-log .chatbot-compare-summary .history-mark-taint").count();
  const compares = await page.evaluate(() => window.__chatbot.compares);
  const head = await page.locator("#chatbot .chatbot-head").innerText();
  const form = await page.locator("#chatbot-form").isVisible();
  await page.close();
  const sm = CASES.compare_done.compare.summary;
  assert.ok(compares.includes("cmp_000000000001"), JSON.stringify(compares));
  assert.equal(head, `${WORDS.compare_title}: ${CASES.compare_done.compare.ended}`);
  for (const words of [WORDS.compare_summary_title, WORDS.compare_summary_note, sm.answer,
    WORDS.agree_title, sm.agree[0], WORDS.disagree_title, sm.disagree[0].point,
    `Gemini: ${sm.disagree[0].views[0].said}`, `ChatGPT: ${sm.disagree[0].views[1].said}`,
    WORDS.sources_title, "ChatGPT: https://example.org/low-light-plants", WORDS.dropped_title,
    `Claude - ${sm.dropped[0].why}`, WORDS.open_title]) {
    assert.ok(summary.includes(words), `the summary does not say: ${words}`);
  }
  assert.equal(outside, 1, "the summary is not marked outside text");
  assert.equal(form, true, "a new one could not be started after the comparison ended");
});

await check("Brain, stale link: a comparison's Resume and Start wait, Stop does not", async () => {
  let page = await workTab({ chatbot: { status: CASES.compare_paused }, link: { stale: true } });
  const states = await page.locator("#chatbot button").evaluateAll(
    (bs) => bs.map((b) => [b.textContent, b.disabled]));
  const text = await page.locator("#chatbot").innerText();
  await page.close();
  assert.deepEqual(states, [["Resume", true], ["Stop", false]]);
  assert.ok(text.includes(CASES.compare_paused.compare.paused));
  page = await workTab({ chatbot: { status: CASES.compare_none }, link: { stale: true } });
  await page.locator("#chatbot-compare").check();
  const start = await page.locator("#chatbot-start").isDisabled();
  await page.close();
  assert.equal(start, true, "Start (compare) was offered on a stale link");
});

await check("Brain: a comparison's words are hidden with the private lists", async () => {
  // What Rust sends while "Hide memory lists and chat history" hides them.
  const hidden = JSON.parse(JSON.stringify(CASES.compare_running));
  Object.assign(hidden.compare, { goal: "", summary: null, ended: "", never_send: [], hidden: true });
  for (const m of hidden.compare.members) {
    Object.assign(m, { goal: "", transcript: [], summary: null, question: "", ended: "", hidden: true });
  }
  const page = await workTab({ chatbot: { status: hidden } });
  const text = await page.locator("#chatbot").innerText();
  const log = await page.locator("#chatbot-log").innerText();
  await page.close();
  assert.ok(!text.includes(CASES.compare_running.compare.goal), text);
  assert.ok(text.includes(WORDS.hidden));
  assert.ok(text.includes("Comparing 3 chatbots: asking ChatGPT, 2 of 3"));
  assert.equal(log.trim(), "");
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nTalk to a chatbot for me: the PC's words, one card to start, outside text marked, held on a stale link");
process.exit(fails.length ? 1 : 0);
