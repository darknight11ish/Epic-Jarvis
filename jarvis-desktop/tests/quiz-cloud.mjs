/**
 * Cloud "Grade this better" button on the Quiz screen
 * (docs/STUDY-FROM-TEXT-DESIGN.md section 15; docs/JARVIS-API.md section 113;
 * src/quiz.js QC_*, brain.js, src-tauri/src/brain/quiz_cloud.rs).
 *
 * Held to fixtures/quiz-cloud-cases.json (written by tools/gen_quiz_cloud_cases.py,
 * the phone reads the same file): words word for word, phases, poll gap,
 * unknown-state limit and sample reply expectations.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as Q from "../src/quiz.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(read("tests/fixtures/quiz-cloud-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words, the phases and the samples ────────────────────────────── */

await check("the shared words, word for word, in the module", async () => {
  const W = FIX.words;
  assert.equal(Q.QC_BUTTON, W.button);
  assert.equal(Q.QC_TITLE, W.title);
  assert.equal(Q.QC_INTRO, W.intro);
  assert.equal(Q.QC_LEAVES, W.leaves);
  assert.equal(Q.QC_CANCEL, W.cancel);
  assert.equal(Q.QC_MARK_PREFIX, W.mark_label_prefix);
  assert.equal(Q.QC_POLL_SECONDS, FIX.poll_seconds);
  assert.equal(Q.QC_UNKNOWN_LIMIT_SECONDS, FIX.unknown_state_limit_seconds);
  assert.equal(Q.QC_PAYLOAD_MAX, FIX.payload_max);
});

await check("every state has the phase the contract gives it; an unknown one is still working", async () => {
  for (const [state, phase] of Object.entries(FIX.phases)) {
    assert.equal(Q.qcPhase(state), phase, state);
    assert.equal(Q.qcIsKnown(state), true, state);
  }
  assert.equal(Q.qcPhase("evaluating"), "working");
  assert.equal(Q.qcIsKnown("evaluating"), false);
  assert.equal(Q.qcPhase(undefined), "working");
  assert.equal(Q.qcPhase("constructor"), "working");
  assert.equal(Q.qcKeepPolling("waiting"), true);
  assert.equal(Q.qcKeepPolling("working"), true);
  assert.equal(Q.qcKeepPolling("ready"), false);
  assert.equal(Q.qcKeepPolling("ended"), false);
});

await check("an empty message falls back to the state's reference words, and an end is never blank", async () => {
  for (const [state, words] of Object.entries(FIX.state_words)) {
    const r = Q.qcReadRequest({ id: "abc", state, message: "" });
    assert.equal(Q.qcShown(r), words, state);
    const own = Q.qcReadRequest({ id: "abc", state, message: "The PC's own." });
    assert.equal(Q.qcShown(own), "The PC's own.");
  }
});

await check("the give-up rule: an unknown state is dropped after 180 seconds, not before", async () => {
  assert.equal(Q.qcGiveUpOnUnknown(null, 999999), false);
  assert.equal(Q.qcGiveUpOnUnknown(1000, 1000 + 179999), false);
  assert.equal(Q.qcGiveUpOnUnknown(1000, 1000 + 180000), true);
});

await check("every sample reply is read as its expect says", async () => {
  for (const [name, s] of Object.entries(FIX.samples)) {
    const e = s.expect;
    if (name.startsWith("info_")) {
      const info = Q.qcReadInfo(s.body);
      assert.equal(info.available, e.available, `${name} available`);
      assert.equal(info.ready, e.ready, `${name} ready`);
      assert.equal(info.cheapest, e.cheapest, `${name} cheapest`);
      assert.equal(info.services.length, e.service_count, `${name} service_count`);
      continue;
    }
    const lead = "Not started.";
    const outcome = Q.qcOutcome(s.body, lead);
    assert.equal(outcome.ok, e.ok, `${name} ok`);
    if (e.ok === true) {
      assert.equal(outcome.request.phase, e.phase, `${name} phase`);
      if (e.shown) assert.equal(outcome.said, e.shown, `${name} shown`);
      if (e.quiz_id) assert.equal(outcome.request.quiz.id, e.quiz_id, `${name} quiz_id`);
      if (e.questions) assert.equal(outcome.request.quiz.questions.length, e.questions, `${name} questions`);
    } else {
      if (e.code) assert.equal(outcome.code, e.code, `${name} code`);
    }
  }
});

await check("a refusal keeps the PC's words word for word", async () => {
  for (const [code, r] of Object.entries(FIX.refusals)) {
    const body = { ok: false, error: code, message: r.message };
    const outcome = Q.qcOutcome(body, "Refused.");
    assert.equal(outcome.ok, false, code);
    assert.equal(outcome.said, r.message, code);
    assert.equal(outcome.code, code, code);
  }
});

await check("cloud marks are read with markedBy cloud, service, and cloudLabel in markLines", async () => {
  const m = Q.readMark({
    level: "got_it", comment: "Great.", passage: "Text.",
    marked_by: "cloud", service: "Mistral"
  });
  assert.equal(m.markedBy, "cloud");
  assert.equal(m.service, "Mistral");
  const lines = Q.markLines(m, { verified: false, keySource: "text" });
  assert.equal(lines.cloudLabel, "Marked by Mistral");
  assert.equal(lines.showGuess, true, "cloud mark on unverified quiz keeps guess");
  const verifiedLines = Q.markLines(m, { verified: true, keySource: "text" });
  assert.equal(verifiedLines.showGuess, false, "verified quiz drops guess");
});

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
}
