/**
 * Settings -> Voice: training on this PC, how strict, private answers, the
 * guided test and the voice-ID model (voice-training.js, voice-panel.js,
 * voice_training.rs).
 *
 * Every status and every answer here is REAL: `K.TRAINING` is
 * tests/fixtures/voice-training-cases.json, the backend's own
 * jarvis_speech.status() and jarvis_voice_enroll.stage(), written by
 * tools/gen_voice_training_cases.py. The one thing made here is "an older
 * PC": today's real status minus the flags it added (`rounds`, `settings`,
 * `measure`), which is what a PC from before 2026-09-24 sends.
 *
 * What must hold (docs/JARVIS-API.md section 16; the owner's decisions):
 * - very strict trains three rounds of the phone's twelve sentences, in the
 *   PC's own conditions, sent round by round with `finish` only on the last
 *   - ONE card; balanced trains one round; an older PC gets today's single
 *   training; "Train more" adds;
 * - the recordings the PC left out are offered again, topped up to the
 *   three a round needs, and only for this PC's own training;
 * - loosening a setting is only a card ("waiting for your approval"), and is
 *   held on a stale link; tightening is immediate and is never held;
 * - "voice check is enough" only while very strict;
 * - the guided test's numbers, and the "asked you to repeat" counts, in words;
 * - a small or missing voice-ID model is said plainly, with the README link;
 * - nothing is sent that raises a card while the link is stale, in the page
 *   AND in the Rust.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import * as VT from "../src/voice-training.js";
import * as W from "../src/voice-settings.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const T = K.TRAINING;
const S = T.statuses;
const A = (name) => K.TRAINING.answer(T.enroll[name]);
const WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";
/** An older PC: today's status without the flags 2026-09-24 added. */
const older = (st) => {
  const c = JSON.parse(JSON.stringify(st));
  for (const k of ["rounds", "settings", "measure", "session", "round_asks"]) delete c.gate.training[k];
  delete c.gate.settings;
  delete c.gate.models;
  delete c.gate.repeat;
  return c;
};

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const VIEW = { width: 760, height: 2400 };
const open = (status, extra = {}) =>
  K.open(browser, base, "settings.html", { voice: { status }, ...extra }, VIEW);
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|null|undefined|\[object|NaN/, `raw data on the page: ${text}`);
};
const calls = (page, cmd) => page.evaluate((c) => window.__vt.calls.filter((x) => x[0] === c).map((x) => x[1]), cmd);
const text = (page, id) => page.evaluate((i) => document.getElementById(i).innerText, id);
const click = async (page, box, label) => {
  await page.click(`#${box} button:text-is("${label}")`);
  await page.waitForTimeout(60);
};
/** Records every sentence of one round (or the test) and opens the review. */
async function readAll(page, box, n) {
  for (let i = 0; i < n; i += 1) {
    await click(page, box, "Record");
    await click(page, box, "Stop");
    await click(page, box, i === n - 1 ? "Review" : "Next sentence");
  }
}

/* ── The words, against every real status ───────────────────────────── */

await check("every real status reads as sentences, with no raw data", async () => {
  for (const [name, st] of Object.entries(S)) {
    const lines = [
      VT.modelLine(st)?.text, VT.noteLine(st), VT.trainingBlocker(st), VT.heldSession(st)?.line,
      W.lastTrainingLine(st.gate.training.last), VT.outlierLine(st.gate.training.last),
      VT.settingWaitingLine(VT.settingsView(st)?.waiting, WHERE),
      ...VT.repeatLines(st).map((l) => l.text),
      ...(VT.measureLines(st.gate.training.measure_last) || []),
      VT.planLine(VT.trainingPlan(st)), ...VT.introLines(VT.trainingPlan(st), st),
    ].filter(Boolean);
    for (const line of lines) {
      noRaw(line);
      assert.match(line, /[.!?)]$/, `${name}: "${line}" is not a sentence`);
    }
  }
});

await check("very strict trains three rounds of the phone's twelve, in the PC's own conditions", async () => {
  const plan = VT.trainingPlan(S.strong_ready);
  assert.equal(plan.legacy, false);
  assert.equal(plan.add, false);
  assert.deepEqual(plan.rounds.map((r) => r.round), [1, 2, 3]);
  assert.deepEqual(plan.rounds.map((r) => r.ask), [1, 2, 3].map((n) => S.strong_ready.gate.training.round_asks[String(n)]));
  for (const r of plan.rounds) assert.equal(r.items.length, 12);
  // The phone's sentences (VoiceTraining.SENTENCES), word for word.
  const kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceTraining.kt");
  const phone = [...kt.slice(kt.indexOf("val SENTENCES"), kt.indexOf(")\n", kt.indexOf("val SENTENCES")))
    .matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1].replace(/\\"/g, '"'));
  assert.deepEqual([...VT.SENTENCES], phone);
  assert.equal(VT.roundLine(plan, 1), "Round 2 of 3: further away from the microphone, or quieter.");
});

await check("balanced trains one round; an older PC gets today's single training", async () => {
  const plan = VT.trainingPlan(S.balanced);
  assert.deepEqual(plan.rounds.map((r) => r.round), [1]);
  assert.equal(VT.roundLine(plan, 0), "How to record: normal, close to the microphone.");
  const old = VT.trainingPlan(older(S.strong_ready));
  assert.equal(old.legacy, true);
  assert.equal(old.rounds.length, 1);
  assert.equal(VT.roundLine(old, 0), "");
});

await check("the recordings left out are asked for again, topped up to three, and added", async () => {
  const last = S.trained_outliers.gate.training.last;
  assert.deepEqual(last.outliers, [{ clip: 2, round: 2 }, { clip: 5, round: 2 }]);
  assert.equal(VT.outlierLine(last),
    "Jarvis left out 2 recordings because they did not sound like the rest: round 2, sentence 2 and round 2, sentence 5. Record them again so it knows your voice in those conditions too.");
  const plan = VT.outlierPlan(S.trained_outliers, last.outliers);
  assert.equal(plan.add, true);
  assert.deepEqual(plan.rounds, [{ round: 2, ask: "further away from the microphone, or quieter", items: [1, 4, 5] }]);
  assert.equal(VT.roundLine(plan, 0), "Round 2 again: further away from the microphone, or quieter.");
  // Most recordings unlike the rest: nothing saved, record again somewhere quieter.
  assert.match(VT.outlierLine(S.training_failed.gate.training.last), /^Most of those recordings did not sound like the same voice, so nothing was saved\./);
});

await check("what the PC answers to a round, in words", async () => {
  const held = VT.roundReply(A("round_held"), WHERE);
  assert.equal(held.held, true);
  assert.equal(held.text, T.enroll.round_held.body.message);
  const done = VT.roundReply(A("round_finish"), WHERE);
  assert.equal(done.finished, true);
  assert.equal(done.text, `Sent. A card is waiting to finish it. Approve it ${WHERE}.`);
  assert.equal(VT.roundReply(A("legacy_accepted"), WHERE).finished, true);
  assert.equal(VT.roundReply(A("round_bad_clip"), WHERE).text,
    "Clip 3 is too short (0.5 s) - read the whole sentence. That was in round 2.");
  assert.match(VT.roundReply(A("needs_model"), WHERE).text, /^No voice-ID model is installed/);
  assert.equal(VT.roundReply(A("card_waiting"), WHERE).tone, "bad");
});

await check("the settings: very strict and on screen by default, voice-is-enough only while very strict", async () => {
  const v = VT.settingsView(S.strong_ready);
  assert.deepEqual([v.strictness, v.privacy, v.voiceIsEnoughAllowed], ["very_strict", "private_on_screen", true]);
  const b = VT.settingsView(S.balanced);
  assert.deepEqual([b.strictness, b.privacy, b.voiceIsEnoughAllowed], ["balanced", "private_on_screen", false]);
  assert.equal(VT.settingsView(older(S.strong_ready)), null);
  assert.equal(VT.settingWaitingLine(VT.settingsView(S.setting_waiting).waiting, WHERE),
    `Waiting for your approval to change how strict the voice check is to "Balanced". Approve it ${WHERE} — nothing changes until you do.`);
  assert.equal(VT.settingReply(A("loosen_strictness"), WHERE).text,
    `Waiting for your approval. Approve it ${WHERE} — nothing changes until you do.`);
  assert.equal(VT.settingReply(A("tighten_strictness"), WHERE).text, "Done - that applies now.");
  assert.equal(VT.settingReply(A("tighten_already"), WHERE).text, "It was already set that way.");
  assert.equal(VT.settingReply(A("privacy_while_balanced"), WHERE).text,
    "Private answers can only be read aloud while the voice check is very strict - make it very strict first.");
  assert.equal(W.lastTrainingLine(S.balanced.gate.training.last, S.balanced), "Approved: \"Balanced\" is on now.");
  assert.equal(W.lastTrainingLine(S.voice_is_enough.gate.training.last, S.voice_is_enough),
    "Approved: \"Voice check is enough\" is on now.");
  assert.equal(W.lastTrainingLine(S.cancelled.gate.training.last), "The last training was cancelled, and its recordings were deleted.");
});

await check("how a strictness, privacy or memory card ended: the words both apps use, never a training's", async () => {
  // The real `last` shape (the balanced status's), with the setting and
  // outcome of each card. "(recommended)" is never in the sentence.
  const card = (setting, value, outcome) => ({ ...S.balanced.gate.training.last, setting, value, outcome });
  const now = S.strong_ready; // very strict, on screen, memory read aloud
  const cases = [
    [card("memory", "memory_aloud", "setting_changed"), "Approved: \"Read aloud\" is on now."],
    [card("memory", "memory_aloud", "denied"), "You said no, so \"Read aloud\" stays."],
    [card("memory", "memory_aloud", "timed_out"), "Nobody answered the card in time, so nothing changed."],
    [card("memory", "memory_aloud", "withdrawn"), "You made it stricter while the card waited, so approving it changed nothing."],
    [card("strictness", "balanced", "denied"), "You said no, so \"Very strict\" stays."],
    [card("privacy", "voice_is_enough", "denied"), "You said no, so \"Stay on screen\" stays."],
    [card("privacy", "voice_is_enough", "timed_out"), "Nobody answered the card in time, so nothing changed."],
    [card("strictness", "balanced", "withdrawn"), "You made it stricter while the card waited, so approving it changed nothing."],
  ];
  for (const [last, want] of cases) {
    const got = W.lastTrainingLine(last, now);
    assert.equal(got, want, `${last.setting} ${last.outcome}`);
    assert.doesNotMatch(got, /training|recommended/i);
  }
  assert.equal(W.lastTrainingLine(card("memory", "memory_on_screen", "failed")),
    "The change to answers that use what Jarvis remembers failed.");
  // No status to name what stayed: still not a training's words.
  assert.equal(W.lastTrainingLine(card("memory", "memory_aloud", "denied")), "You said no, so nothing changed.");
  // The buttons say which is recommended; the sentences above do not.
  assert.deepEqual([VT.STRICTNESS, VT.PRIVACY, VT.MEMORY].map((l) => l.map(VT.choiceText)), [
    ["Very strict (recommended)", "Balanced"],
    ["Stay on screen (recommended)", "Voice check is enough"],
    ["Read aloud (recommended)", "Keep on screen"],
  ]);
  // Word for word what the phone says (StrictVoice.kt, pinned by
  // VoiceStrictTest.kt): one wording for both apps. The last two sentences
  // say plainly what the voice check cannot do (a recording or a clone).
  assert.equal(VT.STRICTNESS[0].detail,
    "Needs about 2 seconds of speech and a close match. Best at turning other people away; " +
    "now and then it may ask you to say it again. It tells your voice from other people's. " +
    "It cannot tell your voice from a recording or a copy of it.");
});

await check("\"asked you to repeat\" and the guided test, in plain words", async () => {
  assert.deepEqual(VT.repeatLines(S.measured_and_counted).map((l) => l.text),
    ["Very strict: Jarvis asked you to repeat 2 of the last 5 times. (3 turned away, 1 too short.)"]);
  assert.equal(VT.repeatLines(S.strong_ready)[0].id, "none");
  const lines = VT.measureLines(S.measured_and_counted.gate.training.measure_last);
  assert.deepEqual(lines, [
    "Very strict let 15 of 20 through; balanced 17 of 20.",
    "So at very strict, Jarvis would have asked you to repeat 5 of 20 sentences; at balanced, 3.",
    "2 of them were too short for very strict, which needs about 2 seconds of speech. Saying a little more helps.",
  ]);
  assert.deepEqual(VT.measureReply(A("measure")).lines, lines);
  assert.equal(VT.TEST_SENTENCES.length, S.strong_ready.gate.training.limits.measure_max_clips);
});

await check("the voice-ID model: the stronger one, only the small one, or none - with the README step", async () => {
  assert.equal(VT.modelLine(S.strong_ready).tone, "ok");
  const small = VT.modelLine(S.small_only);
  assert.equal(small.tone, "warn");
  assert.match(small.text, /^Only the small voice-ID model is installed, so very strict will turn you away far more often\./);
  assert.equal(small.link, VT.README_STRONGER);
  const none = VT.modelLine(S.no_model);
  assert.match(none.text, /^No voice-ID model is installed/);
  assert.equal(none.link, VT.README_MODEL);
  // The links point at headings that are really in the README.
  const readme = read("../backend/README.md");
  assert.ok(readme.includes("# The stricter voice check (2026-09-24) — only your voice, and more sure of it"));
  assert.ok(readme.includes("## Install the better voice check (recommended)"));
  assert.match(VT.trainingBlocker(S.no_model), /^No voice-ID model is installed on your PC, so training cannot help yet/);
  assert.equal(VT.modelLine(older(S.strong_ready)), null);
});

await check("clip problems: silent, too short, too long", async () => {
  assert.match(VT.clipProblem({ seconds: 3, peak: 0.001 }, S.strong_ready), /^That was silent\./);
  assert.equal(VT.clipProblem({ seconds: 0.4, peak: 0.3 }, S.strong_ready),
    "That was too short. Press Record, read the whole sentence, then press Stop.");
  assert.equal(VT.clipProblem({ seconds: 10.5, peak: 0.3 }, S.strong_ready), "That was too long. Keep it under 10 seconds.");
  assert.equal(VT.clipProblem({ seconds: 2.6, peak: 0.3 }, S.strong_ready), null);
});

/* ── The page ───────────────────────────────────────────────────────── */

await check("very strict: three rounds, round by round, finish only on the last - ONE card", async () => {
  const page = await open(S.strong_ready, { vt: { sends: [A("round_held"), A("round_2_held"), A("round_finish")] } });
  await click(page, "vt-train", "Train my voice");
  assert.match(await text(page, "vt-train"), /read the same 12 short sentences 3 times/);
  await click(page, "vt-train", "Start");
  assert.match(await text(page, "vt-train"), /Round 1 of 3: normal, close to the microphone\.\s+Sentence 1 of 12\s+Hey Jarvis, what's on my calendar today\?/);
  await readAll(page, "vt-train", 12);
  await click(page, "vt-train", "Send round 1");
  assert.match(await text(page, "vt-train"), /Round 1 is kept on your PC, in memory only\./);
  for (const r of [2, 3]) {
    await click(page, "vt-train", `Start round ${r}`);
    await readAll(page, "vt-train", 12);
    await click(page, "vt-train", r === 3 ? "Send to your PC" : `Send round ${r}`);
  }
  const sends = await calls(page, "send_voice_training");
  const starts = await calls(page, "start_voice_sample");
  const all = await text(page, "vt-train");
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(sends.map((s) => [s.round, s.finish, s.add, s.legacy, s.slots.length]),
    [[1, false, false, false, 12], [2, false, false, false, 12], [3, true, false, false, 12]]);
  assert.deepEqual(sends[1].slots, [...Array(12)].map((_, i) => `t2-${i}`));
  assert.equal(starts.length, 36);
  assert.match(all, new RegExp(`Sent\\. A card is waiting to finish it\\. Approve it ${WHERE}\\.`));
  noRaw(all);
  assert.deepEqual(errors, []);
});

await check("balanced: one round, sent with finish; an older PC: the one-shot training", async () => {
  const page = await open(S.balanced, { vt: { sends: [A("round_finish")] } });
  await click(page, "vt-train", "Train my voice");
  await click(page, "vt-train", "Start");
  await readAll(page, "vt-train", 12);
  await click(page, "vt-train", "Send to your PC");
  const sends = await calls(page, "send_voice_training");
  await page.close();
  assert.deepEqual(sends.map((s) => [s.round, s.finish, s.legacy]), [[1, true, false]]);

  const old = await open(older(S.strong_ready), { vt: { sends: [A("legacy_accepted")] } });
  await click(old, "vt-train", "Train my voice");
  await click(old, "vt-train", "Start");
  await readAll(old, "vt-train", 12);
  await click(old, "vt-train", "Send to your PC");
  const oldSends = await calls(old, "send_voice_training");
  const settingsHidden = await old.evaluate(() => document.getElementById("vt-settings").hidden);
  await old.close();
  assert.deepEqual(oldSends.map((s) => [s.round, s.finish, s.legacy, s.slots.length]), [[1, false, true, 12]]);
  assert.equal(settingsHidden, true, "an older PC has no strictness settings to show");
});

await check("\"Train more\" adds, and is offered only once this PC's microphone is trained", async () => {
  const page = await open(S.strong_ready, { vt: { sends: [A("round_held"), A("round_2_held"), A("add_finish")] } });
  await click(page, "vt-train", "Train more");
  assert.match(await text(page, "vt-train"), /Nothing it had is deleted\./);
  await click(page, "vt-train", "Start");
  await readAll(page, "vt-train", 12);
  await click(page, "vt-train", "Send round 1");
  const sends = await calls(page, "send_voice_training");
  await page.close();
  assert.equal(sends[0].add, true);
  const phoneOnly = await open(S.small_only);
  const buttons = await phoneOnly.evaluate(() => [...document.querySelectorAll("#vt-train button")].map((b) => b.innerText));
  await phoneOnly.close();
  assert.deepEqual(buttons, ["Train my voice"]);
});

await check("a silent or short recording must be made again before going on", async () => {
  const page = await open(S.strong_ready, { vt: { take: { seconds: 2.4, peak: 0.002 } } });
  await click(page, "vt-train", "Train my voice");
  await click(page, "vt-train", "Start");
  await click(page, "vt-train", "Record");
  await click(page, "vt-train", "Stop");
  const words = await text(page, "vt-train");
  const nextDisabled = await page.evaluate(() =>
    [...document.querySelectorAll("#vt-train button")].find((b) => b.innerText === "Next sentence").disabled);
  await page.close();
  assert.match(words, /That was silent\. Check the microphone/);
  assert.equal(nextDisabled, true);
});

await check("on a stale link the round that raises the card is held, and says why; the rounds before it are not", async () => {
  const page = await open(S.balanced, { link: { stale: true } });
  await click(page, "vt-train", "Train my voice");
  await click(page, "vt-train", "Start");
  await readAll(page, "vt-train", 12);
  const send = await page.evaluate(() =>
    [...document.querySelectorAll("#vt-train button")].find((b) => b.innerText === "Send to your PC").disabled);
  const words = await text(page, "vt-train");
  await page.close();
  assert.equal(send, true);
  assert.match(words, /The connection to Jarvis is catching up, so this cannot be sent until it does\./);

  const three = await open(S.strong_ready, { link: { stale: true } });
  await click(three, "vt-train", "Train my voice");
  await click(three, "vt-train", "Start");
  await readAll(three, "vt-train", 12);
  const round1 = await three.evaluate(() =>
    [...document.querySelectorAll("#vt-train button")].find((b) => b.innerText === "Send round 1").disabled);
  await three.close();
  assert.equal(round1, false, "a round that is only held in memory is not held back");
});

await check("rounds the PC already holds: carry on from the next, or delete them", async () => {
  const page = await open(S.session_held);
  assert.match(await text(page, "vt-train"), /Your PC is keeping round 1 of a training from this PC \(12 recordings\)/);
  await click(page, "vt-train", "Carry on");
  await click(page, "vt-train", "Start");
  assert.match(await text(page, "vt-train"), /^Round 2 of 3: further away/);
  await click(page, "vt-train", "Cancel");
  const cancels = await calls(page, "cancel_voice_training");
  await page.close();
  assert.equal(cancels.length, 1, "cancelling after carrying on deletes what the PC holds");

  const del = await open(S.session_held);
  await click(del, "vt-train", "Delete them");
  const c2 = await calls(del, "cancel_voice_training");
  const said = await text(del, "vt-train");
  await del.close();
  assert.equal(c2.length, 1);
  assert.match(said, /The recordings were deleted\./);
});

await check("another app's training, a waiting card, or no voice-ID model: training is not offered, and the page says why", async () => {
  for (const [st, words] of [
    [S.phone_session_held, /Your phone is in the middle of a training\./],
    [S.training_waiting, /A voice card is already waiting\. Answer it first\./],
    [S.no_model, /No voice-ID model is installed on your PC, so training cannot help yet/],
  ]) {
    const page = await open(st);
    const all = await text(page, "vt-train");
    const buttons = await page.evaluate(() => [...document.querySelectorAll("#vt-train button")].map((b) => b.innerText));
    await page.close();
    assert.match(all, words);
    assert.ok(!buttons.includes("Train my voice"), `${buttons}`);
  }
});

await check("the left-out recordings are offered again only after THIS PC's training", async () => {
  const ours = await open(S.trained_outliers, { vt: { sends: [A("add_finish")] } });
  // This PC sent a training just before the PC's outcome (the fixture's
  // fixed time, 1790000000), and has not seen an outcome since.
  await ours.evaluate(() => localStorage.setItem("jarvis.voice.trainedAt", JSON.stringify({ sent: 1789999990, at: null })));
  await ours.reload();
  await ours.waitForTimeout(300);
  const said = await text(ours, "vt-train");
  assert.match(said, /Jarvis left out 2 recordings/);
  await click(ours, "vt-train", "Record those again");
  await click(ours, "vt-train", "Start");
  assert.match(await text(ours, "vt-train"), /^Round 2 again: further away[\s\S]*Sentence 1 of 3\s+The quick brown fox/);
  await readAll(ours, "vt-train", 3);
  await click(ours, "vt-train", "Send to your PC");
  const sends = await calls(ours, "send_voice_training");
  await ours.close();
  assert.deepEqual(sends.map((s) => [s.round, s.add, s.finish, s.slots]), [[2, true, true, ["t2-1", "t2-4", "t2-5"]]]);

  const theirs = await open(S.trained_outliers);
  const words = await text(theirs, "vt-train");
  await theirs.close();
  assert.doesNotMatch(words, /left out/, "a training from the phone is not the PC's to redo");
  // This PC's own outcome was an earlier one: a later outcome is not ours.
  const later = await open(S.trained_outliers);
  await later.evaluate(() => localStorage.setItem("jarvis.voice.trainedAt", JSON.stringify({ sent: 1789999000, at: 1789999500 })));
  await later.reload();
  await later.waitForTimeout(300);
  const laterWords = await text(later, "vt-train");
  await later.close();
  assert.doesNotMatch(laterWords, /left out/, "only the first outcome after this PC's training is its own");
});

await check("loosening is a card and says so; tightening is at once; the choice shows what Jarvis says", async () => {
  const page = await open(S.strong_ready);
  await page.click('#vt-strictness button[data-value="balanced"]');
  await page.waitForTimeout(150);
  const status = await text(page, "vt-setting-status");
  const pressed = await page.evaluate(() =>
    document.querySelector('#vt-strictness button[aria-pressed="true"]').dataset.value);
  const sent = await calls(page, "set_voice_setting");
  await page.close();
  assert.deepEqual(sent, [{ setting: "strictness", value: "balanced" }]);
  assert.equal(status, `Waiting for your approval. Approve it ${WHERE} — nothing changes until you do.`);
  assert.equal(pressed, "very_strict", "nothing changes until the card is approved");

  const bal = await open(S.balanced);
  const disabled = await bal.evaluate(() =>
    document.querySelector('#vt-privacy button[data-value="voice_is_enough"]').disabled);
  assert.equal(disabled, true, "voice-is-enough only while very strict");
  assert.match(await text(bal, "vt-privacy-note"), /can only be chosen while the check is very strict/);
  await bal.click('#vt-strictness button[data-value="very_strict"]');
  await bal.waitForTimeout(150);
  assert.equal(await text(bal, "vt-setting-status"), "Done - that applies now.");
  await bal.close();

  const waiting = await open(S.setting_waiting);
  const line = await text(waiting, "vt-setting-waiting");
  await waiting.close();
  assert.match(line, /^Waiting for your approval to change how strict the voice check is to "Balanced"\./);
});

await check("on a stale link only loosening is held; tightening still goes", async () => {
  const page = await open(S.balanced, { link: { stale: true } });
  await page.click('#vt-strictness button[data-value="very_strict"]');
  await page.waitForTimeout(150);
  const tight = await calls(page, "set_voice_setting");
  await page.close();
  assert.deepEqual(tight, [{ setting: "strictness", value: "very_strict" }]);
  const loose = await open(S.strong_ready, { link: { stale: true } });
  await loose.click('#vt-privacy button[data-value="voice_is_enough"]');
  await loose.waitForTimeout(150);
  const none = await calls(loose, "set_voice_setting");
  const said = await text(loose, "vt-setting-status");
  await loose.close();
  assert.deepEqual(none, []);
  assert.match(said, /catching up/);
});

await check("answers that use memories: read aloud by default; keeping them on screen is at once; back asks", async () => {
  const page = await open(S.strong_ready);
  const shown = await page.evaluate(() => !document.getElementById("vt-memory-box").hidden);
  const pressed = await page.evaluate(() =>
    document.querySelector('#vt-memory button[aria-pressed="true"]').dataset.value);
  assert.equal(shown, true, "offered when the PC reports it");
  assert.equal(pressed, "memory_aloud", "the owner's default");
  assert.match(await text(page, "vt-memory-note"), /Anyone near the speaker will hear them/);
  await page.click('#vt-memory button[data-value="memory_on_screen"]');
  await page.waitForTimeout(150);
  assert.deepEqual(await calls(page, "set_voice_setting"), [{ setting: "memory", value: "memory_on_screen" }]);
  await page.close();
  // An older PC (no memory in its settings): not offered at all.
  const older = JSON.parse(JSON.stringify(S.strong_ready));
  delete older.gate.settings.memory;
  const old = await open(older);
  const hidden = await old.evaluate(() => document.getElementById("vt-memory-box").hidden);
  await old.close();
  assert.equal(hidden, true);
  assert.equal(VT.loosens("memory", "memory_aloud"), true);
  assert.equal(VT.loosens("memory", "memory_on_screen"), false);
});

await check("while \"voice check is enough\" is on, the memory choices are disabled and say why", async () => {
  const page = await open(S.voice_is_enough);
  const got = await page.evaluate(() => ({
    disabled: [...document.querySelectorAll("#vt-memory button")].map((b) => b.disabled),
    labels: [...document.querySelectorAll("#vt-strictness button, #vt-privacy button, #vt-memory button")].map((b) => b.textContent),
    note: document.getElementById("vt-memory-note").textContent,
  }));
  await page.close();
  assert.deepEqual(got.disabled, [true, true]);
  assert.equal(got.note,
    "\"Voice check is enough\" already reads these answers aloud. Choose \"Stay on screen\" above to use this setting.");
  assert.deepEqual(got.labels, ["Very strict (recommended)", "Balanced", "Stay on screen (recommended)",
    "Voice check is enough", "Read aloud (recommended)", "Keep on screen"]);
  // CONTROL: on screen, both can be pressed.
  const on = await open(S.strong_ready);
  const free = await on.evaluate(() => [...document.querySelectorAll("#vt-memory button")].map((b) => b.disabled));
  await on.close();
  assert.deepEqual(free, [false, false]);
});

/** A status from a PC with decision 13's setting, as `value`, said in
 *  `gate.settings` or only in `gate`. (The fixtures carry it in both since
 *  they were regenerated from the backend.) */
const withSensitive = (st, value, where = "settings") => {
  const c = withoutSensitive(st);
  if (where === "settings") c.gate.settings.sensitive_memory = value;
  else c.gate.sensitive_memory = value;
  return c;
};
/** The same status from a PC older than decision 13: no such setting. */
function withoutSensitive(st) {
  const c = JSON.parse(JSON.stringify(st));
  delete c.gate.settings.sensitive_memory;
  delete c.gate.sensitive_memory;
  return c;
}

await check("answers that use sensitive saved facts: on screen by default, the contract's words, and only when the PC has it", async () => {
  assert.deepEqual(VT.SENSITIVE_MEMORY.map(VT.choiceText), ["Keep on screen (recommended)", "Read aloud"]);
  assert.equal(VT.SENSITIVE_MEMORY[0].detail,
    "Answers that use a saved fact about your health, money, passwords or other people are shown, not read aloud.");
  assert.equal(VT.SENSITIVE_MEMORY[1].detail,
    "Those answers are read aloud when your voice passes the check. Anyone near the speaker will hear them.");
  assert.equal(VT.loosens("sensitive_memory", "sensitive_aloud"), true);
  assert.equal(VT.loosens("sensitive_memory", "sensitive_on_screen"), false);
  // Read from gate.settings, or gate itself; anything else is not offered.
  assert.equal(VT.settingsView(withSensitive(S.strong_ready, "sensitive_on_screen")).sensitiveMemory, "sensitive_on_screen");
  assert.equal(VT.settingsView(withSensitive(S.strong_ready, "sensitive_aloud", "gate")).sensitiveMemory, "sensitive_aloud");
  assert.equal(VT.settingsView(withSensitive(S.strong_ready, "loud")).sensitiveMemory, "");
  assert.equal(VT.settingsView(withoutSensitive(S.strong_ready)).sensitiveMemory, "");

  const page = await open(withSensitive(S.strong_ready, "sensitive_on_screen"));
  const got = await page.evaluate(() => ({
    shown: !document.getElementById("vt-sensitive-box").hidden,
    title: document.querySelector("#vt-sensitive-box h3").textContent,
    labels: [...document.querySelectorAll("#vt-sensitive button")].map((b) => b.textContent),
    pressed: document.querySelector('#vt-sensitive button[aria-pressed="true"]').dataset.value,
  }));
  const note = await text(page, "vt-sensitive-note");
  await page.close();
  assert.equal(got.shown, true, "not offered by a PC that reports it");
  assert.equal(got.title, "Answers that use sensitive saved facts");
  assert.deepEqual(got.labels, ["Keep on screen (recommended)", "Read aloud"]);
  assert.equal(got.pressed, "sensitive_on_screen");
  assert.match(note, /health, money, passwords or other people are shown, not read aloud/);
  // A PC without it ("" or missing): not offered at all.
  const old = await open(withoutSensitive(S.strong_ready));
  const hidden = await old.evaluate(() => document.getElementById("vt-sensitive-box").hidden);
  await old.close();
  assert.equal(hidden, true);
});

await check("sensitive saved facts under \"Keep on screen\" for memories: the note says that already covers them", async () => {
  const NOTE = "\"Keep on screen\" above already keeps these answers on screen.";
  assert.equal(VT.SENSITIVE_COVERED_NOTE, NOTE);
  const withMemory = (st, memory) => {
    const c = JSON.parse(JSON.stringify(st));
    c.gate.settings.memory = memory;
    return c;
  };
  const covered = withMemory(withSensitive(S.strong_ready, "sensitive_aloud"), "memory_on_screen");
  assert.equal(VT.sensitiveCovered(VT.settingsView(covered)), true);
  const page = await open(covered);
  const note = await text(page, "vt-sensitive-note");
  const free = await page.evaluate(() => [...document.querySelectorAll("#vt-sensitive button")].map((b) => b.disabled));
  await page.close();
  assert.ok(note.endsWith(NOTE), note);
  assert.match(note, /^Those answers are read aloud/, "the chosen one's own words stay");
  assert.deepEqual(free, [false, false], "still usable: it takes over if the memory choice changes");
  // CONTROL: memories read aloud - this choice is what holds them back.
  const aloud = await open(withMemory(withSensitive(S.strong_ready, "sensitive_on_screen"), "memory_aloud"));
  const plain = await text(aloud, "vt-sensitive-note");
  await aloud.close();
  assert.ok(!plain.includes(NOTE), plain);
  // CONTROL: "Voice check is enough" makes the memory choice moot, so it
  // covers nothing - no note.
  const moot = withMemory(withSensitive(S.voice_is_enough, "sensitive_on_screen"), "memory_on_screen");
  assert.equal(VT.sensitiveCovered(VT.settingsView(moot)), false);
  const mootPage = await open(moot);
  const mootNote = await text(mootPage, "vt-sensitive-note");
  await mootPage.close();
  assert.ok(!mootNote.includes(NOTE), mootNote);
});

await check("sensitive saved facts: keeping them on screen is at once; Read aloud asks, and is held on a stale link", async () => {
  // Never moot: it holds even under "Voice check is enough".
  const moot = await open(withSensitive(S.voice_is_enough, "sensitive_on_screen"));
  const free = await moot.evaluate(() => [...document.querySelectorAll("#vt-sensitive button")].map((b) => b.disabled));
  await moot.close();
  assert.deepEqual(free, [false, false]);
  // Aloud -> on screen: sent at once, even on a stale link.
  const tighten = await open(withSensitive(S.strong_ready, "sensitive_aloud"), { link: { stale: true } });
  await tighten.click('#vt-sensitive button[data-value="sensitive_on_screen"]');
  await tighten.waitForTimeout(150);
  const sentTight = await calls(tighten, "set_voice_setting");
  await tighten.close();
  assert.deepEqual(sentTight, [{ setting: "sensitive_memory", value: "sensitive_on_screen" }]);
  // On screen -> aloud on a stale link: nothing sent, and it says why.
  const held = await open(withSensitive(S.strong_ready, "sensitive_on_screen"), { link: { stale: true } });
  await held.click('#vt-sensitive button[data-value="sensitive_aloud"]');
  await held.waitForTimeout(150);
  const none = await calls(held, "set_voice_setting");
  const said = await text(held, "vt-setting-status");
  await held.close();
  assert.deepEqual(none, []);
  assert.match(said, /catching up/);
  // On a live link it is sent - the PC answers with the card.
  const live = await open(withSensitive(S.strong_ready, "sensitive_on_screen"));
  await live.click('#vt-sensitive button[data-value="sensitive_aloud"]');
  await live.waitForTimeout(150);
  const sent = await calls(live, "set_voice_setting");
  await live.close();
  assert.deepEqual(sent, [{ setting: "sensitive_memory", value: "sensitive_aloud" }]);
  // The waiting line and the last-card line name it.
  assert.match(VT.settingWaitingLine({ setting: "sensitive_memory", value: "sensitive_aloud" }, WHERE),
    /^Waiting for your approval to change answers that use sensitive saved facts to "Read aloud"\./);
  const card = { ...S.balanced.gate.training.last, setting: "sensitive_memory", value: "sensitive_aloud" };
  const now = withSensitive(S.strong_ready, "sensitive_on_screen");
  assert.equal(W.lastTrainingLine({ ...card, outcome: "setting_changed" }, now), "Approved: \"Read aloud\" is on now.");
  assert.equal(W.lastTrainingLine({ ...card, outcome: "denied" }, now), "You said no, so \"Keep on screen\" stays.");
  // CONTROL: the Rust knows the setting, and holds only its loosening.
  const rust = read("src-tauri/src/voice_training.rs");
  assert.match(rust, /\("sensitive_memory", "sensitive_aloud"\) => \{?\s*Ok\(\("sensitive_memory", "sensitive_aloud", true\)\)/);
  assert.match(rust, /\("sensitive_memory", "sensitive_on_screen"\) => \{?\s*Ok\(\("sensitive_memory", "sensitive_on_screen", false\)\)/);
});

await check("the guided test: 20 sentences, one request, the result in words", async () => {
  const page = await open(S.strong_ready);
  await click(page, "vt-test", "Start the test");
  await readAll(page, "vt-test", 20);
  await click(page, "vt-test", "Check them");
  const sent = await calls(page, "measure_voice");
  const words = await text(page, "vt-test");
  await page.close();
  assert.deepEqual(sent, [{ slots: [...Array(20)].map((_, i) => `m${i}`) }]);
  assert.match(words, /Very strict let 15 of 20 through; balanced 17 of 20\./);
  assert.match(words, /would have asked you to repeat 5 of 20 sentences/);
  const counted = await open(S.measured_and_counted);
  const rep = await text(counted, "vt-repeat");
  const last = await text(counted, "vt-test");
  await counted.close();
  assert.match(rep, /Very strict: Jarvis asked you to repeat 2 of the last 5 times\./);
  assert.match(last, /The last guided test:\s+Very strict let 15 of 20 through/);
});

await check("the small model is said plainly, with a link that opens in the real browser", async () => {
  const page = await open(S.small_only);
  const got = await page.evaluate(() => {
    const a = document.getElementById("vt-model-link");
    return { text: document.getElementById("vt-model").innerText, href: a.href, ext: a.dataset.external, hidden: a.hidden };
  });
  await page.click("#vt-model-link");
  await page.waitForTimeout(100);
  const opened = await page.evaluate(() => window.__calls.filter((c) => c[0] === "open_external_url").map((c) => c[1].url));
  await page.close();
  assert.match(got.text, /very strict will turn you away far more often/);
  assert.equal(got.href, VT.README_STRONGER);
  assert.equal(got.ext, "true");
  assert.deepEqual(opened, [VT.README_STRONGER]);
});

/* ── The "someone else" check ───────────────────────────────────────── */

// REAL answers: backend/jarvis_voice_enroll.calibrate() itself, run on
// three real WAV clips with the voice-ID model stood in by fixed scores
// (the scoring is the model's job; the reply's shape and words, the
// suggestion and the counting are the module's).
const BACKEND_DIR = join(HERE, "..", "..", "backend");
function realCalibrate(got) {
  const code = [
    "import sys, json, io, wave, base64, struct, math",
    "sys.path.insert(0, 'rebuilt'); sys.path.insert(0, '.')",
    "import jarvis_voice_enroll as E",
    "def clip():",
    "    b = io.BytesIO(); w = wave.open(b, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)",
    "    w.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(i / 7.0))) for i in range(32000))); w.close()",
    "    return base64.b64encode(b.getvalue()).decode()",
    `got = json.loads(${JSON.stringify(JSON.stringify(got))})`,
    "code, body = E.calibrate({'mode': 'calibrate', 'mic': 'desktop', 'clips': [clip(), clip(), clip()]}, score=lambda pcm, mic: got)",
    "body['http'] = code; print(json.dumps(body))",
  ].join("\n");
  return JSON.parse(execFileSync("python3", ["-c", code],
    { cwd: BACKEND_DIR, encoding: "utf8", env: { ...process.env, JARVIS_NO_EMBED: "1" } }));
}
const APART = realCalibrate({ ok: true, scores: [0.21, 0.33, 0.28], threshold: 0.35,
  owner_scores: [0.62, 0.7, 0.66], print: "desktop", strictness: "very_strict",
  passed: [false, false, false], model: "strong" });
const ONE_IN = realCalibrate({ ok: true, scores: [0.4, 0.3, 0.2], threshold: 0.35,
  owner_scores: [0.62, 0.7, 0.66], print: "desktop", strictness: "very_strict",
  passed: [true, false, false], model: "small" });
const TOO_CLOSE = realCalibrate({ ok: true, scores: [0.6, 0.5, 0.55], threshold: 0.35,
  owner_scores: [0.52, 0.7, 0.66], print: "desktop", strictness: "very_strict", model: "strong" });
const NOTHING_TRAINED = realCalibrate({ ok: false, why: "no voice has been trained yet" });
// What stage_threshold() answers when the card is up (jarvis_voice_enroll.py:
// `return 202, {"ok": True, "pending": True, "threshold": new, "model": which,
// "message": ...}`), as voice_training.rs passes it on (`http` added).
const THRESHOLD_UP = { ok: true, pending: true, threshold: 0.47, model: "strong", http: 202,
  message: "Approve the card on your PC or phone to use the new setting. Nothing changes until you do." };

await check("the \"someone else\" check in words, from the PC's real answers", async () => {
  assert.equal(APART.http, 200);
  const a = VT.checkResult(APART);
  assert.equal(a.text, "Good: none of their 3 clips would pass as you now. A stricter setting, 0.47 (now 0.35), would turn them away and still let you in.");
  assert.deepEqual([a.ok, a.suggested, a.model], [true, 0.47, "strong"]);
  const b = VT.checkResult(ONE_IN);
  assert.match(b.text, /^1 of their 3 clips would pass as you now\./);
  assert.equal(b.model, "small");
  const c = VT.checkResult(TOO_CLOSE);
  assert.equal(c.suggested, null, "no safe stricter setting, so none is offered");
  assert.match(c.text, /^3 of their 3 clips would pass as you now\. /, "no verdicts: the PC counts against the bar");
  const d = VT.checkResult(NOTHING_TRAINED);
  assert.equal(NOTHING_TRAINED.http, 409);
  assert.deepEqual([d.ok, d.text], [false, "No voice has been trained yet."]);
  for (const r of [a, b, c, d]) noRaw(r.text);
  assert.equal(VT.thresholdReply(THRESHOLD_UP, WHERE).text,
    `Waiting for your approval. Approve it ${WHERE} — nothing changes until you do.`);
  // Only a PC that understands it, with a print to compare against.
  assert.equal(VT.canCheck(S.strong_ready), true);
  const old = JSON.parse(JSON.stringify(S.strong_ready));
  delete old.gate.training.calibrate;
  assert.equal(VT.canCheck(old), false, "an older PC reads the clips as a training");
  const none = JSON.parse(JSON.stringify(S.strong_ready));
  for (const k of ["desktop", "phone", "general"]) none.gate.prints[k].trained = false;
  assert.equal(VT.canCheck(none), false);
  // The phone's three sentences and intro, word for word ("this phone" made "this PC's microphone").
  const phone = read("../jarvis-client/app/src/main/java/com/jarvis/client/voice/VoiceTraining.kt");
  const kotlin = phone.slice(phone.indexOf("val OTHER_SENTENCES"), phone.indexOf(")", phone.indexOf("val OTHER_SENTENCES")));
  assert.deepEqual([...kotlin.matchAll(/"([^"]+)"/g)].map((m) => m[1]), [...VT.OTHER_SENTENCES]);
});

const othersPage = (status, extra = {}) =>
  open(status, { vt: { check: APART, threshold: THRESHOLD_UP }, ...extra });

await check("someone else reads 3 sentences; the PC compares; the stricter bar is ONE card", async () => {
  const page = await othersPage(S.strong_ready);
  await click(page, "vt-others", "Start the check");
  await readAll(page, "vt-others", 3);
  await click(page, "vt-others", "Compare them");
  await page.waitForTimeout(150);
  const checked = await calls(page, "check_voice_with_someone_else");
  const said = await text(page, "vt-others");
  await click(page, "vt-others", "Use 0.47 (asks for approval)");
  await page.waitForTimeout(150);
  const proposed = await calls(page, "propose_voice_threshold");
  const after = await text(page, "vt-others");
  const sampled = await calls(page, "start_voice_sample");
  await page.close();
  assert.deepEqual(sampled.map((c) => c.slot), ["o0", "o1", "o2"]);
  assert.deepEqual(checked, [{ slots: ["o0", "o1", "o2"] }]);
  assert.match(said, /Good: none of their 3 clips would pass as you now\. A stricter setting, 0\.47 \(now 0\.35\)/);
  assert.match(said, /Nothing changes until you approve the card\./);
  assert.deepEqual(proposed, [{ threshold: 0.47, model: "strong" }]);
  assert.match(after, /Waiting for your approval\. Approve it in the Jarvis bar/);
});

await check("on a stale link the check still runs, but the stricter bar's card is held", async () => {
  const page = await othersPage(S.strong_ready, { link: { stale: true } });
  await click(page, "vt-others", "Start the check");
  await readAll(page, "vt-others", 3);
  await click(page, "vt-others", "Compare them");
  await page.waitForTimeout(150);
  const checked = await calls(page, "check_voice_with_someone_else");
  const use = await page.evaluate(() => document.getElementById("vt-others-use").disabled);
  const said = await text(page, "vt-others");
  await page.close();
  assert.equal(checked.length, 1, "the check was held, though it changes nothing");
  assert.equal(use, true, "the card could be asked for on a stale link");
  assert.match(said, /catching up/);
});

await check("an older PC is not offered the check at all", async () => {
  const old = JSON.parse(JSON.stringify(S.strong_ready));
  delete old.gate.training.calibrate;
  const page = await othersPage(old);
  const hidden = await page.evaluate(() => [document.getElementById("vt-others").hidden,
    document.getElementById("vt-others-head").hidden]);
  await page.close();
  assert.deepEqual(hidden, [true, true]);
});

await check("the guided test's 20 sentences are ONE list: the phone's is this one, word for word", async () => {
  assert.equal(VT.TEST_SENTENCES.length, 20);
  assert.equal(new Set(VT.TEST_SENTENCES).size, 20);
  const phone = read("../jarvis-client/app/src/main/java/com/jarvis/client/voice/StrictVoice.kt");
  const at = phone.indexOf("val MEASURE_SENTENCES");
  assert.ok(at > -1, "StrictVoice.MEASURE_SENTENCES is gone");
  const kotlin = phone.slice(at, phone.indexOf(")", at));
  assert.deepEqual([...kotlin.matchAll(/"([^"]+)"/g)].map((m) => m[1]), [...VT.TEST_SENTENCES],
    "the phone's guided test reads other sentences (jarvis-client voice/StrictVoice.kt)");
});

/* ── The Rust ───────────────────────────────────────────────────────── */

const fnBody = (src, sig) => {
  const at = src.indexOf(sig);
  assert.ok(at > -1, `${sig} is gone`);
  const rest = src.slice(at);
  return rest.slice(0, rest.indexOf("\n}\n"));
};
const RUST = read("src-tauri/src/voice_training.rs");
const COMMANDS = ["start_voice_sample", "voice_sample_level", "stop_voice_sample", "cancel_voice_sample",
  "discard_voice_samples", "send_voice_training", "cancel_voice_training", "measure_voice",
  "set_voice_setting", "check_voice_with_someone_else", "propose_voice_threshold",
  "get_custom_voices", "create_custom_voice", "set_active_voice",
  "delete_custom_voice", "set_better_voice"];

await check("CONTROL (Rust): what raises a card is held on a stale link, and nothing else", async () => {
  assert.match(fnBody(RUST, "pub async fn send_voice_training("), /if \(finish \|\| legacy\) && stale\(&app\) \{\s+return Err\(HELD_STALE/);
  assert.match(fnBody(RUST, "pub async fn set_voice_setting("), /if loosening && stale\(&app\)/);
  assert.doesNotMatch(fnBody(RUST, "pub async fn cancel_voice_training("), /stale/);
  assert.doesNotMatch(fnBody(RUST, "pub async fn measure_voice("), /stale/);
  // The "someone else" check changes nothing: never held. Its card is.
  assert.doesNotMatch(fnBody(RUST, "pub async fn check_voice_with_someone_else("), /stale/);
  assert.match(fnBody(RUST, "pub async fn propose_voice_threshold("), /if stale\(&app\) \{\s+return Err\(HELD_STALE/);
  // ...and it goes only to a PC that says it understands it.
  assert.match(fnBody(RUST, "pub async fn check_voice_with_someone_else("),
    /calibrate_understood\(&status\)[\s\S]*if !understood \{[\s\S]*return Err\(CHECK_UPDATE[\s\S]*"mode": "calibrate"/);
  assert.match(fnBody(RUST, "pub(crate) fn voice_setting("), /\("strictness", "balanced"\) => Ok\(\("strictness", "balanced", true\)\)/);
  assert.match(fnBody(RUST, "pub(crate) fn voice_setting("), /\("privacy", "voice_is_enough"\) => Ok\(\("privacy", "voice_is_enough", true\)\)/);
});

await check("CONTROL (Rust): every request goes through jarvis_headers, trains mic=desktop, and logs nothing", async () => {
  assert.match(fnBody(RUST, "async fn post("), /\.headers\(jarvis_headers\(app\)\?\)/);
  assert.match(RUST, /const MIC_DESKTOP: &str = "desktop";/);
  assert.match(RUST, /const TRAINING_RATE: u32 = 16_000;/);
  assert.doesNotMatch(RUST, /println!|eprintln!|log::|tracing::|dbg!|logfile/);
  assert.doesNotMatch(RUST, /\/api\/voice\/utterance|transcri(be|ption)\(/, "nothing here turns speech into text");
});

await check("CONTROL: only the settings window holds the new commands", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const c of COMMANDS) {
    const perm = `"allow-${c.replace(/_/g, "-")}"`;
    const holders = sets.filter((s) => s.includes(perm)).map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["settings-surface"], `${c} is held by ${holders}`);
    assert.ok(build.includes(`"${c}"`), `${c} not in build.rs`);
    assert.ok(lib.includes(`voice_training::${c},`), `${c} not registered`);
    assert.match(read(`src-tauri/permissions/autogenerated/${c}.toml`), new RegExp(`commands.allow = \\["${c}"\\]`));
  }
  assert.ok(lib.includes(".manage(voice_training::SampleState::default())"));
});

await check("CONTROL: push-to-talk and \"hey Jarvis\" listening refuse while Settings records", async () => {
  const voice = read("src-tauri/src/voice.rs");
  assert.match(fnBody(voice, "pub fn start_voice_capture("), /if training\.recording\(\) \{\s+return Err\(crate::voice_training::MIC_IN_SETTINGS/);
  assert.match(fnBody(voice, "pub async fn start_automatic_listening("), /if training\.recording\(\) \{/);
  assert.match(fnBody(RUST, "pub fn start_voice_sample("), /stop_listening_because\(/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nVoice training on this PC holds");
process.exit(fails.length ? 1 : 0);
