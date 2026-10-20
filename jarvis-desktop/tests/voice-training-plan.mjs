/**
 * The redesigned voice training, WITHOUT a browser:
 *
 *     node tests/voice-training-plan.mjs
 *
 * Why this file exists, and what it holds:
 *
 * The backend half of PR #605 merged as `jarvis_voice_training.py`: four
 * condition rounds, twelve balanced read phrases, three free-speech prompts,
 * Live adaptation with caps / a drift guard / re-anchoring, and a held-out
 * FRR/FAR report. The desktop page is the second half. This test holds the
 * page's WORDS AND SHAPES to the PC's own fixture
 * (`tests/fixtures/voice-training-cases.json`, written by
 * `tools/gen_voice_training_cases.py`), so a screen cannot quietly invent a
 * condition, a phrase, a cap or a measurement.
 *
 * It also records the two things this desktop build does NOT wire yet, and
 * fails if the page starts claiming them:
 *
 *   1. the PC understands four conditions and `voice_training.rs` accepts
 *      rounds 1-4, so all four are recorded;
 *   2. `POST /api/voice/enroll {"mode": "adapt-reset"}` is wired through the
 *      desktop's `reset_voice_adaptation` command.
 *
 * What it canNOT prove: that a microphone records, that the page looks
 * right, or that the Rust command is granted to the settings window. The
 * Playwright suite (`voice-training.mjs`) and CI's `frontend` job own the
 * page; this file owns the contract.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as VT from "../src/voice-training.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIXTURE = JSON.parse(read("tests/fixtures/voice-training-cases.json"));
const HTML = read("src/settings.html");
const PANEL = read("src/voice-panel.js");

const S = FIXTURE.statuses;
const A = (name) => ({ ...FIXTURE.enroll[name].body, http: FIXTURE.enroll[name].code });
const PLAN = S.strong_ready.gate.training.training;
const WHERE = "in the Jarvis bar, on the widget, or on your phone's Home screen";

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};
const noRaw = (text) => {
  assert.doesNotMatch(String(text), /[{}]|HTTP \d|"available"|\bnull\b|\bundefined\b|\[object|NaN/, `raw data on the page: ${text}`);
};
const older = (st) => {
  const c = JSON.parse(JSON.stringify(st));
  delete c.gate.training.training;
  return c;
};

/* ── The material is the PC's, word for word ─────────────────────────── */

check("four conditions, in the PC's order and words", () => {
  assert.equal(VT.CONDITIONS.length, 4);
  assert.deepEqual(VT.CONDITIONS.map((c) => c.id), ["close", "table", "noise", "room"]);
  assert.deepEqual(VT.CONDITIONS.map((c) => c.id), PLAN.conditions.map((c) => c.id));
  assert.deepEqual(VT.CONDITIONS.map((c) => c.ask), PLAN.conditions.map((c) => c.ask));
  assert.deepEqual(VT.CONDITIONS.map((c) => c.label), PLAN.conditions.map((c) => c.label));
  assert.match(VT.CONDITIONS[1].ask, /two to three metres/);
  assert.match(VT.CONDITIONS[2].ask, /fan or the TV/);
  assert.match(VT.CONDITIONS[3].ask, /another room/);
});

check("twelve balanced read phrases, and three free-speech prompts, exactly the PC's", () => {
  assert.equal(VT.READ_PHRASES.length, 12);
  assert.equal(PLAN.read_phrases.length, 12);
  assert.deepEqual(VT.READ_PHRASES, PLAN.read_phrases);
  assert.equal(new Set(VT.READ_PHRASES.map((p) => p.id)).size, 12);
  assert.equal(new Set(VT.READ_PHRASES.map((p) => p.text)).size, 12, "the old repeated sentence is gone");
  assert.equal(VT.SENTENCES.length, 12);
  assert.deepEqual([...VT.SENTENCES], VT.READ_PHRASES.map((p) => p.text));

  assert.equal(VT.FREE_SPEECH.length, 3);
  assert.deepEqual(VT.FREE_SPEECH, PLAN.free_speech);
  assert.ok(VT.FREE_SPEECH.some((p) => /own words/.test(p.text)));
  assert.ok(VT.FREE_SPEECH.every((p) => Array.isArray(p.seconds) && p.seconds.length === 2));
});

check("the wake words are a separate fixed set, never training material", () => {
  assert.deepEqual([...VT.WAKE_PHRASES], ["hey Jarvis"]);
  assert.deepEqual(VT.WAKE_PHRASES, PLAN.wake_phrases);
  for (const p of [...VT.READ_PHRASES, ...VT.FREE_SPEECH]) {
    assert.doesNotMatch(p.text.toLowerCase(), /hey jarvis/);
  }
});

/* ── The plan: four conditions, three recordable, honest about the fourth ── */

check("the plan is read from the PC, and a PC without one is refused, not guessed", () => {
  assert.ok(VT.planOf(S.strong_ready));
  assert.equal(VT.planOf(older(S.strong_ready)), null);
  assert.equal(VT.understands(S.strong_ready).plan, true);
  assert.equal(VT.understands(older(S.strong_ready)).plan, false);
  assert.match(VT.trainingBlocker(older(S.strong_ready)),
    /^This PC has not sent the new four-condition training plan yet\./);
  assert.equal(VT.trainingPlan(older(S.strong_ready)).missing, true);
  assert.deepEqual(VT.trainingPlan(older(S.strong_ready)).rounds, []);
});

check("four rounds exist; all four are wired; every phrase and prompt is used once within them", () => {
  const plan = VT.trainingPlan(S.strong_ready);
  assert.equal(plan.missing, false);
  assert.equal(plan.total, 4);
  assert.equal(plan.wiredTotal, 4);
  assert.equal(plan.wiredTotal, Math.min(plan.total, VT.DESKTOP_ROUND_LIMIT));
  assert.deepEqual(plan.rounds.map((r) => r.round), [1, 2, 3, 4]);
  assert.deepEqual(plan.rounds.map((r) => r.wired), [true, true, true, true]);
  assert.deepEqual(plan.rounds.map((r) => r.items.length), [5, 5, 5, 4]);
  assert.deepEqual(plan.rounds.map((r) => r.items.filter((i) => i.kind === "free").length), [1, 1, 1, 0]);
  const wired = plan.rounds.filter((r) => r.wired).flatMap((r) => r.items);
  assert.equal(wired.filter((i) => i.kind === "read").length, 16);
  assert.equal(wired.filter((i) => i.kind === "free").length, 3);
  assert.equal(new Set(wired.map((i) => i.id)).size, 15,
    "only the fourth condition repeats its opening phrases; the first three use every phrase once");
  assert.equal(plan.rounds[3].items.filter((i) => i.kind === "read").length, 4,
    "the fourth condition repeats opening phrases, for its own sub-print");
  assert.ok(wired.every((i) => i.text));
  assert.ok(wired.filter((i) => i.kind === "free").every((i) => /10 seconds/.test(i.hint)),
    "a free prompt says the PC's own 10-second clip cap");
});

check("the page says four rounds, nineteen recordings, and no unwired condition", () => {
  const plan = VT.trainingPlan(S.strong_ready);
  assert.equal(VT.planLine(plan),
    "4 rounds on this PC, 19 recordings in all. Each round takes about a minute.");
  assert.equal(VT.roundLine(plan, 0), "Round 1 of 4: normal, close to the microphone.");
  assert.equal(VT.roundLine(plan, 1), "Round 2 of 4: about two to three metres away, on a table.");
  assert.equal(VT.roundLine(plan, 3),
    "Round 4 of 4: in another room, or at a different time of day.");
  assert.equal(VT.conditionsLine(plan),
    "The conditions: Close; On a table, 2-3 m away; With background noise; Another room or time.");
  const limit = VT.planLimitLines(plan);
  assert.deepEqual(limit, []);
  for (const line of [VT.planLine(plan), ...VT.introLines(plan, S.strong_ready), ...limit]) noRaw(line);
});

check("the first screen names the phrases, the prompts and the one card", () => {
  const lines = VT.introLines(VT.trainingPlan(S.strong_ready), S.strong_ready);
  const all = lines.join(" ");
  assert.match(all, /12 short phrases/);
  assert.match(all, /3 prompts in your own words/);
  assert.match(all, /4 listening conditions/);
  assert.match(all, /each round records 4 of the phrases/i);
  assert.match(all, /asks you to approve the change on an approval card/);
  assert.match(all, /kept in memory only/);
  assert.doesNotMatch(all, /36 sentences|same 12 short sentences 4 times/);
});

check("carrying on leaves out the rounds the PC already holds", () => {
  const plan = VT.trainingPlan(S.strong_ready, { held: [1, 2] });
  assert.deepEqual(plan.rounds.map((r) => r.round), [3, 4]);
  assert.equal(plan.rounds[0].wired, true);
  assert.equal(plan.rounds[1].wired, true);
  assert.equal(VT.planLine(plan), "2 rounds on this PC, 9 recordings in all. Each round takes about a minute.");
});

check("the left-out recordings map onto the new material, are topped up to 3, and the fourth condition is now offered", () => {
  const last = S.trained_outliers.gate.training.last;
  assert.deepEqual(last.outliers, [{ clip: 2, round: 2 }, { clip: 5, round: 2 }]);
  assert.equal(VT.outlierLine(last),
    "Jarvis left out 2 recordings because they did not sound like the rest: round 2, recording 2 and round 2, recording 5. Record them again so it knows your voice in those conditions too.");
  const plan = VT.outlierPlan(S.trained_outliers, last.outliers);
  assert.equal(plan.add, true);
  assert.equal(plan.again, true);
  assert.deepEqual(plan.rounds.map((r) => r.round), [2]);
  assert.deepEqual(plan.rounds[0].items.map((i) => i.clip), [0, 1, 4]);
  assert.equal(plan.rounds[0].items.length >= 3, true);
  assert.equal(VT.roundLine(plan, 0), "Round 2 again: about two to three metres away, on a table.");
  // The fourth condition is wired now, so a left-out clip there can be redone.
  const fourth = VT.outlierPlan(S.strong_ready, [{ round: 4, clip: 1 }]);
  assert.deepEqual(fourth.rounds.map((r) => r.round), [4]);
  assert.ok(fourth.rounds[0].items.length >= 3);
});

check("a round's answer is ONE card, and a bad clip says which round", () => {
  assert.equal(VT.roundReply(A("round_held"), WHERE).held, true);
  assert.equal(VT.roundReply(A("round_finish"), WHERE).finished, true);
  assert.match(VT.roundReply(A("round_bad_clip"), WHERE).text, /That was in round 2\.$/);
  assert.equal(VT.roundReply(A("needs_model"), WHERE).tone, "bad");
  assert.match(VT.sendBlocker({ recorded: 4, total: 5, linkBlocker: null, totalSeconds: 8, status: S.strong_ready }),
    /^Record all 5 recordings first \(4 done\)\./);
  assert.match(VT.sendBlocker({
    recorded: 5, total: 5, linkBlocker: "stale link", totalSeconds: 8, status: S.strong_ready,
  }), /^stale link$/, "the link is still the first blocker");
  assert.match(VT.clipProblem({ seconds: 0.4, peak: 0.3 }, S.strong_ready, "free"),
    /Press Record, speak for a few seconds in your own words/);
  assert.match(VT.clipProblem({ seconds: 0.4, peak: 0.3 }, S.strong_ready),
    /read the whole sentence/);
});

check("very strict and voice-check-is-enough keep their existing words and rule", () => {
  assert.deepEqual(VT.STRICTNESS.map(VT.choiceText), ["Very strict (recommended)", "Balanced"]);
  assert.deepEqual(VT.PRIVACY.map((c) => c.id), ["private_on_screen", "voice_is_enough"]);
  assert.equal(VT.loosens("privacy", "voice_is_enough"), true);
  assert.equal(VT.loosens("strictness", "balanced"), true);
  assert.equal(VT.settingsView(S.strong_ready).voiceIsEnoughAllowed, true);
  assert.equal(VT.limits(S.strong_ready).rounds, 4);
});

/* ── Live additions: count, caps, drift, re-anchor, reset ────────────── */

check("the Live-additions count and caps are the PC's own", () => {
  const view = VT.adaptationView(S.strong_ready);
  assert.ok(view);
  assert.equal(view.count, 0);
  assert.deepEqual(view.caps, { perCondition: 4, total: 12 });
  assert.deepEqual(view.rows.map((r) => [r.id, r.count, r.cap]), [
    ["close", 0, 4], ["table", 0, 4], ["noise", 0, 4], ["room", 0, 4],
  ]);
  assert.equal(view.words, "No Live additions yet.");
  const lines = VT.adaptationLines(S.strong_ready);
  assert.equal(lines[0], "No Live additions yet.");
  assert.match(lines.join(" "), /cap is 4 for each condition and 12 in all/);
  assert.match(lines.join(" "), /Not re-anchored yet/);
  assert.match(lines.join(" "), /sounds too different from your enrolled voice is refused/);
  assert.match(lines.join(" "), /never side talk, a refusal, a crisis turn/);
  for (const line of lines) noRaw(line);
});

check("a count, a re-anchor and a reset are read from the PC, never invented", () => {
  const st = JSON.parse(JSON.stringify(S.strong_ready));
  st.gate.training.adaptation = {
    available: true,
    counts: { close: 2, noise: 1 },
    count: 3,
    caps: { per_condition: 4, total: 12 },
    reanchors: 2,
    last_reanchor: 1790000000,
    resets: 1,
    reset_at: 1790000000,
    last_at: 1790000100,
    words: "close: 2, noise: 1 Live additions.",
  };
  const view = VT.adaptationView(st);
  assert.equal(view.count, 3);
  assert.equal(view.rows.find((r) => r.id === "close").count, 2);
  assert.equal(view.rows.find((r) => r.id === "noise").count, 1);
  const lines = VT.adaptationLines(st).join(" ");
  assert.match(lines, /Close: 2, noise: 1 Live additions\./);
  assert.match(lines, /Close: 2 of 4 Live additions\./);
  assert.match(lines, /Re-anchored to your original enrollment 2 times/);
  assert.match(lines, /last on /);
  assert.match(lines, /The count has been reset 1 time/);
  // No adaptation block from an older PC: the page says so, and shows no numbers.
  const old = JSON.parse(JSON.stringify(S.strong_ready));
  delete old.gate.training.adaptation;
  assert.equal(VT.adaptationView(old), null);
  assert.deepEqual(VT.adaptationLines(old), []);
});

check("resetting the count is wired through the desktop command", () => {
  assert.equal(VT.ADAPT_RESET_WIRED, true);
  assert.match(VT.ADAPT_RESET_NOTE, /zeroes the PC's Live-additions counters/);
  assert.match(VT.ADAPT_RESET_NOTE, /never changes the voice/);
  assert.match(PANEL, /invoke\("reset_voice_adaptation"\)/);
});

/* ── Held-out measurement: FRR, FAR, EER, and "not enough" ───────────── */

check("the real measure answer's held-out report, in the PC's own words", () => {
  const answer = A("measure");
  const held = answer.held_out;
  assert.equal(held.available, false);
  assert.equal(answer.thresholds_applied, false);
  const lines = VT.heldOutLines(answer);
  assert.equal(lines[0], VT.sentence(held.words));
  assert.match(lines[0], /Not enough held-out scores yet; no threshold was chosen\./);
  assert.match(lines[1], /^Close: /);
  assert.match(lines[1], /owner 20\/10, other 0\/10/);
  assert.match(lines[2], /^No threshold was changed\. A measured bar only changes with your approval\.$/);
  for (const line of lines) noRaw(line);
  // The same report comes back from measureReply, next to the pass counts.
  assert.deepEqual(VT.measureReply(answer).heldOut, lines);
});

check("the reduced report the status keeps still says 'not enough', never a number", () => {
  const last = S.measured_and_counted.gate.training.measure_last;
  assert.ok(last.held_out);
  assert.equal(last.held_out.available, false);
  const lines = VT.heldOutLines(last);
  assert.equal(lines[0], "Not enough held-out scores yet; no threshold was chosen.");
  assert.match(lines[1], /^Close: not enough measured rows yet, so no number\.$/);
  assert.equal(lines.length, 2);
});

check("a condition with enough rows becomes FRR/FAR/EER in plain counts", () => {
  const report = {
    thresholds_applied: false,
    held_out: {
      ok: true,
      available: true,
      words: "Per-condition measured numbers.",
      conditions: {
        close: { available: true, owner_rows: 12, other_rows: 12, threshold: 0.55,
          eer: 0.06, eer_threshold: 0.6, frr: 0.08, far: 0.04 },
        table: { available: false, owner_rows: 4, other_rows: 12,
          why: "not enough measured rows for this condition (owner 4/10, other 12/10)" },
      },
    },
  };
  const lines = VT.heldOutLines(report);
  assert.equal(lines[0], "Per-condition measured numbers.");
  assert.match(lines[1], /^Close: your own voice would be refused 8 in 100 \(FRR\); other voices would get in 4 in 100 \(FAR\); the two are equally likely at 6 in 100 \(EER\)\.$/);
  assert.equal(lines[2], "On a table, 2-3 m away: Not enough measured rows for this condition (owner 4/10, other 12/10).");
  assert.equal(lines[3], "No threshold was changed. A measured bar only changes with your approval.");
  for (const line of lines) noRaw(line);
});

check("no report at all reads as null, not as a zero", () => {
  assert.equal(VT.heldOutLines(S.strong_ready), null);
  assert.equal(VT.heldOutLines({}), null);
  assert.match(VT.HELD_OUT_INTRO, /FRR is how often your own voice would be turned away/);
  assert.match(VT.HELD_OUT_INTRO, /at least 10 of your clips and 10 other-voice clips/);
});

/* ── The page actually carries the new blocks ────────────────────────── */

check("the guided test sends the condition it read from the plan", () => {
  assert.match(PANEL, /vt-test-condition/);
  assert.match(PANEL, /invoke\("measure_voice", \{ slots, condition \}\)/);
});

check("the Settings page has the Live-additions and held-out blocks", () => {
  assert.match(HTML, /<h3 class="subhead">Live additions to your voice<\/h3>/);
  assert.match(HTML, /<div class="vt-box" id="vt-adapt"><\/div>/);
  assert.match(HTML, /<h3 class="subhead">Held-out measurement \(FRR and FAR\)<\/h3>/);
  assert.match(HTML, /<div class="vt-box" id="vt-held"><\/div>/);
  assert.match(PANEL, /function paintAdaptation\(\)/);
  assert.match(PANEL, /function paintHeldOut\(\)/);
  assert.match(PANEL, /paintAdaptation\(\);\s+paintSettings\(\)/);
  assert.match(PANEL, /paintHeldOut\(\);\s+paintOthers\(\)/);
  assert.match(PANEL, /VT\.DESKTOP_ROUND_LIMIT/);
  assert.match(PANEL, /VT\.heldOutLines/);
  assert.match(PANEL, /VT\.adaptationLines/);
});

check("the third wire is honest: the Rust sender is still the limit, not the page", () => {
  // A pointer, not a source pin: when the bridge accepts round 4, the
  // constant is what changes, and the test above starts requiring 4.
  const rust = read("src-tauri/src/voice_training.rs");
  assert.match(rust, /!\(1\.\.=4\)\.contains\(&round\)/,
    "voice_training.rs changed its round range: update DESKTOP_ROUND_LIMIT and this test together");
});

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nThe voice-training plan holds");
process.exit(fails.length ? 1 : 0);
