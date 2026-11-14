/**
 * The bar's spoken answer, three ways it used to get it wrong - found by an
 * independent review of speech against origin/main 0b19b4052 (2026-11-13):
 *
 *   1. Pressing Stop could START more talking. Stop cancelled the stream
 *      (`state.abort` -> `finishStream("done", "Stopped")`) and nothing else:
 *      the sentences already queued behind the one playing kept going, and
 *      `finishStream` queued the tail of what had arrived (its `!speechMuted`
 *      guard was never tripped because Stop never set it).
 *   2. A timer or a Live line was spoken straight over an answer that was
 *      playing: `sayAside` had no `jarvisTalking()` guard, unlike the focus
 *      callout's own.
 *   3. `if (!dataUri) continue;` (drainSpeechQueue) dropped the line when the
 *      PC could not make the voice, so an answer could be entirely silent
 *      with no word to the owner - where the HUD draws a fixed line under the
 *      answer (jarvis_hud.html READ_FAILED_LINE).
 *
 * Fake transport, no real audio (tests/uikit.mjs); the speaker is
 * `K.slowSpeaker`, so what was asked for, played and ended is written down.
 *
 *     node tests/voice-stop-aside-failure.mjs
 */
import assert from "node:assert/strict";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const quickbar = (data) => K.open(browser, base, "index.html", data);
const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });
const asked = (log) => log.filter((l) => l.startsWith("speak ")).map((l) => l.slice(6));
const played = (log) => log.filter((l) => l.startsWith("play ")).map((l) => l.slice(5));
const status = (page) => page.evaluate(() => document.getElementById("card-status-text").textContent);
const playedByNow = async (page, text) => played(await K.speechLog(page)).includes(text);

async function holdAndRelease(page) {
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(80);
  await page.mouse.up();
}

/** Empty deltas: each one is a real event-loop tick with the stream still
 *  open, so "the answer is still arriving" can be held for as long as a
 *  scenario needs (the same trick voice-speech.mjs uses). */
const filler = (n) => Array.from({ length: n }, () => delta(""));

const askedFor = (log, text) => asked(log).some((said) => said.includes(text));

/* ── 1. Stop silences the answer ────────────────────────────────────────── */

await check("Stop during a voice answer: nothing queued behind it is ever played", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. "), delta("Three, the tail"), ...filler(300)]],
    speakDelayMs: 20,
  });
  // A clip lasts 400 ms, long enough that the answer is still open and Two
  // is made ahead while One plays - the state the owner presses Stop in.
  await K.slowSpeaker(page, 400);
  await holdAndRelease(page);
  await K.until(page, "the answer to have started speaking", async () =>
    (await K.speechLog(page)).includes("play One."));
  await K.until(page, "the second sentence to be made ahead", async () =>
    askedFor(await K.speechLog(page), "Two."));
  const before = await K.speechLog(page);
  await page.locator("#stop").click();
  await page.waitForTimeout(2000);
  const log = await K.speechLog(page);
  // Everything written down after the click: nothing may be asked for, and
  // nothing may be played, from here on.
  const after = log.slice(before.length);
  const said = await status(page);
  const errors = page.__errors;
  await page.close();

  assert.deepEqual(errors, []);
  assert.equal(said, "Stopped", "the Stop path did not run - this proves nothing");
  assert.ok(played(before).includes("One."), `the scenario was not speaking: ${JSON.stringify(before)}`);
  assert.deepEqual(played(log), ["One."],
    `the bar kept talking after Stop: ${JSON.stringify(played(log))}`);
  assert.deepEqual(asked(after), [],
    `a line was asked for after Stop: ${JSON.stringify(asked(after))}`);
  assert.deepEqual(played(after), [],
    `a clip was played after Stop: ${JSON.stringify(played(after))}`);
  assert.ok(!askedFor(log, "Three, the tail"),
    `the rest of the answer was queued after Stop: ${JSON.stringify(asked(log))}`);
});

await check("CONTROL: a question asked after a Stop is answered out loud again", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [
      [delta("One. "), delta("Two. "), delta("Three, the tail"), ...filler(300)],
      [delta("Clean answer. ")],
    ],
    speakDelayMs: 20,
  });
  await K.slowSpeaker(page, 200);
  await holdAndRelease(page);
  await K.until(page, "the answer to have started speaking", async () =>
    (await K.speechLog(page)).includes("play One."));
  await page.locator("#stop").click();
  await page.waitForTimeout(300);
  await holdAndRelease(page);
  await K.until(page, "the question asked after the Stop to be spoken", async () =>
    askedFor(await K.speechLog(page), "Clean answer."));
  const log = await K.speechLog(page);
  await page.close();
  assert.ok(askedFor(log, "Clean answer."),
    `Stop muted the bar for good: ${JSON.stringify(asked(log))}`);
});

/* ── 2. An aside never talks over an answer ─────────────────────────────── */

/** A timer going off while "hey Jarvis" listening is on: what the bar says
 *  aloud (coming-up.js aloudFor, the owner's 2026-09-25 decision). */
const timerFrame = { kind: "schedule", data: { state: "fired", kind: "timer", notify: true } };

await check("a timer going off while an answer plays is not spoken over it", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. "), delta("Three."), ...filler(200)]],
    speakDelayMs: 20,
  });
  await K.slowSpeaker(page, 400);
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(100);
  await page.evaluate((heard) => window.__emit("voice-heard", heard), K.HEARD_OWNER);
  await K.until(page, "the answer to have started speaking", async () =>
    (await K.speechLog(page)).includes("play One."));
  await page.evaluate((frame) => window.__emit("jarvis-event", frame), timerFrame);
  // The answer carrying on past the timer's own moment is also what proves
  // the drain was running when the aside arrived: a line queued there would
  // have been asked for by now (that ask is synchronous with the event).
  await K.until(page, "the answer to carry on past the timer", () => playedByNow(page, "Two."));
  const log = await K.speechLog(page);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
  assert.ok(!askedFor(log, "Your timer is done"),
    `the timer was spoken over the answer: ${JSON.stringify(asked(log))}`);
});

await check("a Live line arriving while an answer plays is not spoken over it", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. "), delta("Two. "), delta("Three."), ...filler(200)]],
    speakDelayMs: 20,
  });
  await K.slowSpeaker(page, 400);
  await holdAndRelease(page);
  await K.until(page, "the answer to have started speaking", async () =>
    (await K.speechLog(page)).includes("play One."));
  await page.evaluate(() =>
    window.__emit("live-status", { say: "Jarvis Live is on your phone." }));
  await K.until(page, "the answer to carry on past the Live line", () => playedByNow(page, "Two."));
  const log = await K.speechLog(page);
  await page.close();
  assert.ok(!askedFor(log, "Jarvis Live is on your phone"),
    `the Live line was spoken over the answer: ${JSON.stringify(asked(log))}`);
});

await check("CONTROL: with nothing playing, a timer and a Live line are still spoken", async () => {
  const page = await quickbar({});
  await page.locator("#voice-auto").click();
  await page.waitForTimeout(150);
  await page.evaluate((frame) => window.__emit("jarvis-event", frame), timerFrame);
  await page.waitForTimeout(300);
  await page.evaluate(() =>
    window.__emit("live-status", { say: "Jarvis Live is on your phone." }));
  await page.waitForTimeout(400);
  const log = await K.speechLog(page);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
  assert.ok(askedFor(log, "Your timer is done"),
    `an idle bar no longer says a timer aloud: ${JSON.stringify(asked(log))}`);
  assert.ok(askedFor(log, "Jarvis Live is on your phone"),
    `an idle bar no longer says a Live line aloud: ${JSON.stringify(asked(log))}`);
});

/* ── 3. A voice that cannot be made is said, not swallowed ──────────────── */

const FAILED_LINE = "Jarvis's voice could not read this aloud, so nothing was spoken.";

/** The PC answers speak_reply with nothing: the voice could not be made. A
 *  resolved empty string, not a rejection - `if (!dataUri) continue;` is
 *  what swallowed it. The call is recorded the way the harness records one,
 *  so the same waits work for both shapes. */
const noVoice = (page) => page.evaluate(() => {
  const core = window.__TAURI__.core;
  const real = core.invoke;
  window.__speakAsks = 0;
  core.invoke = async (cmd, args) => {
    if (cmd !== "speak_reply") return real(cmd, args);
    window.__speakAsks += 1;
    window.__voiceCalls.push(["speak", args.text]);
    return "";
  };
});

/** The answer really finished, and both of its lines were asked for - so
 *  "nothing was said" cannot be the answer not having got that far yet. */
async function answerDoneAndAsked(page, n = 2) {
  const log = await K.speechLog(page);
  return (await status(page)) === "Complete" && asked(log).length >= n;
}

const read = (page) => page.evaluate(() => ({
  note: document.getElementById("chat-note").textContent,
  noteShown: !document.getElementById("chat-note").hidden,
  problem: !document.getElementById("answer-problem").hidden,
  answer: document.getElementById("answer").textContent,
  asks: window.__speakAsks,
}));

await check("a voice that could not be made is said once, in fixed words, not as an error", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. Two.")]],
    speakDelayMs: 20,
  });
  await noVoice(page);
  await holdAndRelease(page);
  await K.until(page, "the answer to finish with both of its lines asked for",
    () => answerDoneAndAsked(page));
  const got = await read(page);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
  assert.equal(got.noteShown, true, "nothing was said when the voice could not be made");
  assert.equal(got.note, FAILED_LINE, `the bar said something else: ${JSON.stringify(got.note)}`);
  assert.equal(got.problem, false, "a sentence with no voice was shown as a failed answer");
  assert.match(got.answer, /One\. Two\./, "the answer itself was changed");
  // Still asked for each line: a transient failure is not the end of the
  // answer, it is only its sound.
  assert.ok(got.asks >= 2, `the rest of the answer was abandoned: ${got.asks} line(s) asked for`);
});

await check("a rejected speak_reply says the same fixed line", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. Two.")]],
    speakDelayMs: 20,
    speakFails: "the voice service answered 503",
  });
  await holdAndRelease(page);
  await K.until(page, "the answer to finish with both of its lines asked for",
    () => answerDoneAndAsked(page));
  const got = await read(page);
  await page.close();
  assert.equal(got.noteShown, true, "a rejected speak_reply was swallowed");
  assert.equal(got.note, FAILED_LINE);
  assert.equal(got.problem, false);
  assert.doesNotMatch(got.note, /503|service/, "the reason leaked into the bar's words");
});

await check("CONTROL: a spoken answer that worked says nothing about a failure", async () => {
  const page = await quickbar({
    heard: K.HEARD_OWNER,
    chatReplies: [[delta("One. Two.")]],
    speakDelayMs: 20,
  });
  await K.slowSpeaker(page, 60);
  await holdAndRelease(page);
  await K.until(page, "the answer to be spoken", () => playedByNow(page, "One."));
  const got = await read(page);
  const log = await K.speechLog(page);
  await page.close();
  assert.ok(played(log).includes("One."), `the scenario did not speak: ${JSON.stringify(log)}`);
  assert.equal(got.noteShown, false, `a working answer carried a failure line: ${JSON.stringify(got.note)}`);
});

await browser.close();
close();
console.log(fails.length
  ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nStop silences, asides wait, and a silent voice is said");
process.exit(fails.length ? 1 : 0);
