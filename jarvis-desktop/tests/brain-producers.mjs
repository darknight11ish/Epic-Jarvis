/**
 * The Brain window, fed what the backend's own modules really produce.
 *
 * Five things the 2026-09-23 audit found this window reading wrongly or not
 * at all:
 *
 * - Compute read plan / gpu / vram_total_mb / gpu_layers / context / note,
 *   and jarvis_compute.Plan.as_dict() sends none of them - so the pane always
 *   said "No compute plan reported".
 * - Models ignored the `speed` block (speed-record.patch) that JARVIS-API.md
 *   says to show, and had no way to install a model, which the phone has.
 * - The rush latch's quoted words were read as `phrase`; the phone read
 *   `quote`. jarvis_content_risk is only on the owner's PC, so both are read.
 * - The undo shelf and job list read only this window's field names; the
 *   phone's (label, reversible, capabilities, private) now read too.
 *
 * The compute plan and the speed block are not hand-written here: they are
 * made by running the REAL backend modules (backend/rebuilt/jarvis_compute.py,
 * backend/jarvis_speed.py) with python3, so a renamed key on either side
 * fails this test. It skips those two, loudly, when python3 is missing.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const BACKEND = join(HERE, "..", "..", "backend");

/** Runs python3 with `code`, the backend (and its rebuilt modules) importable. */
function python(code) {
  try {
    const out = execFileSync("python3", ["-c", code], {
      cwd: BACKEND,
      env: { ...process.env, PYTHONPATH: [join(BACKEND, "rebuilt"), BACKEND].join(":"),
             OPENJARVIS_CONFIG_DIR: mkdtempSync(join(tmpdir(), "jarvis-brain-test-")) },
      encoding: "utf8",
    });
    return JSON.parse(out);
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

// jarvis_compute.plan() with two cards, the owner's planned setup.
const PLAN = python(`
import json
from unittest import mock
import jarvis_compute as C
cards = [C.Device(0, "NVIDIA GeForce RTX 2080 SUPER", 8192, 1944),
         C.Device(1, "NVIDIA GeForce RTX 2060", 12288, 11000)]
with mock.patch.object(C, "devices", return_value=cards):
    print(json.dumps(C.plan("qwen3:8b").as_dict()))
`);

// jarvis_speed.view() over a log of real-shaped rows: 30 answers, the last 10
// slower, then one model switch.
const SPEED = python(`
import json, os, tempfile
from pathlib import Path
import jarvis_speed as S
log = S.SpeedLog(Path(tempfile.mkdtemp()) / "speed.jsonl")
for i in range(30):
    slow = i >= 20
    log.append({"kind": "answer", "model": "qwen3:8b", "first_word_ms": 900 if slow else 800,
                "words_per_s": 9.0 if slow else 14.2, "tokens_per_s": 12.0 if slow else 19.0,
                "on_gpu_percent": 100, "at": 1700000000 + i})
log.append({"kind": "switch", "old_model": "llama3.1:8b", "new_model": "qwen3:8b",
            "old_tokens_per_s": 21.0, "new_tokens_per_s": 19.0, "old_source": "measured"})
print(json.dumps(S.view(log=log, current="qwen3:8b")))
`);

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const SIZE = { width: 1180, height: 900 };

async function tab(id, brain) {
  const page = await K.open(browser, base, "brain.html", { brain: { ...K.BRAIN, ...brain } }, SIZE);
  await page.locator(`#tab-${id}`).click();
  await page.waitForTimeout(300);
  return page;
}

/* ── Compute ─────────────────────────────────────────────────────────────── */

await check("Compute shows the real plan, not 'No compute plan reported'", async () => {
  if (!PLAN) return console.log("      SKIP - python3 is not installed");
  const page = await tab("faculties", { compute: PLAN });
  const text = await page.locator("#compute").innerText();
  await page.close();
  assert.doesNotMatch(text, /No compute plan reported/);
  assert.match(text, /qwen3:8b/, "the model the plan is for");
  // Everyday chat stays on the 2080 SUPER. It used to go to the card with the
  // most FREE memory - the slower 2060 12 GB - which is what this test once
  // asserted; jarvis_compute now picks the monitor's card, else nvidia-smi's
  // first (docs/MODEL-TOPOLOGY.md, docs/SECOND-CARD.md).
  assert.match(text, /graphics card 0/, "where it runs, in words (text_on)");
  assert.doesNotMatch(text, /graphics card 1/, "everyday chat went to the second card");
  assert.match(text, /RTX 2060/, "the cards");
  assert.match(text, /everyday chat on the NVIDIA GeForce RTX 2080 SUPER/, "the plan's own why");
});

await check("CONTROL: a plan with no card measured says it is a guess", async () => {
  if (!PLAN) return console.log("      SKIP - python3 is not installed");
  const guess = { ...PLAN, devices: [], simulated: true, total_mb: 0, text_on: "cpu" };
  const page = await tab("faculties", { compute: guess });
  const text = await page.locator("#compute").innerText();
  await page.close();
  assert.match(text, /this is a guess/);
  assert.match(text, /the processor/);
});

/* ── Models: speed, and installing one ───────────────────────────────────── */

const MODELS = { ...K.BRAIN.models, speed: SPEED };

await check("Models shows how fast recent answers were, from the real speed block", async () => {
  if (!SPEED) return console.log("      SKIP - python3 is not installed");
  const page = await tab("faculties", { models: MODELS });
  const text = await page.locator("#models").innerText();
  await page.close();
  assert.match(text, /Recent answers: about \d+ words a second, first word after \d\.\d s/);
  assert.match(text, /slower than the 20 before them/, "the backend's own slowdown note");
  assert.ok(SPEED.last_switch_note && text.includes(SPEED.last_switch_note.trim()),
    "the backend's own old-vs-new sentence, word for word");
});

await check("Install sends the typed name, and only asks", async () => {
  const page = await tab("faculties", {});
  await page.locator("#model-install-ref").fill("  llama3.1:8b  ");
  await page.locator("#model-install").click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__calls);
  const text = await page.locator("#models").innerText();
  await page.close();
  const sent = calls.find((c) => c[0] === "brain_model");
  assert.ok(sent, "brain_model was never called");
  assert.equal(sent[1].action, "install");
  assert.equal(sent[1].reference, "llama3.1:8b");
  assert.match(text, /Waiting for your approval: installing llama3\.1:8b/);
});

// AP-3 (audit 3): the "Waiting for your approval" line cleared only on a
// `model` event. A card denied or left to expire brings none, so the line
// kept claiming a card was waiting that no longer existed. The phone drops
// it when the card leaves /api/pending (JarvisRuntime.noteModelRequest).
const MODEL_CARD = { id: "gate-model-1", action: "install_model", tier: "ask",
                     detail: { reference: "llama3.1:8b" }, created: 1 };

async function installAsked(page) {
  // The click raises exactly one new card: the one the line is about.
  await page.evaluate((card) => { window.__pendingNow = [card]; }, MODEL_CARD);
  await page.locator("#model-install-ref").fill("llama3.1:8b");
  await page.locator("#model-install").click();
  await page.waitForTimeout(300);
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), MODEL_CARD);
  await page.waitForTimeout(100);
}
const cardGone = (page) => page.evaluate(() => {
  window.__pendingNow = [];
  window.__emit("approvals-changed", { count: 0, items: [] });
});
const modelsText = (page) => page.locator("#models").innerText();

await check("the waiting line goes when its card leaves the queue unanswered here, and says denied or ran out of time", async () => {
  const page = await tab("faculties", {});
  await installAsked(page);
  const before = await modelsText(page);
  await cardGone(page);
  await page.waitForTimeout(3600); // the grace an approval's `model` event gets
  const after = await modelsText(page);
  await page.close();
  assert.match(before, /Waiting for your approval: installing llama3\.1:8b/);
  assert.doesNotMatch(after, /Waiting for your approval/, "the line still claims a card is waiting");
  assert.match(after, /installing llama3\.1:8b is no longer waiting: it was denied or ran out of time/);
});

await check("a card denied on this PC says denied, at once", async () => {
  const page = await tab("faculties", {});
  await installAsked(page);
  await page.evaluate((id) => window.__emit("approval-resolved", { id, approved: false }), MODEL_CARD.id);
  await cardGone(page);
  await page.waitForTimeout(200);
  const after = await modelsText(page);
  await page.close();
  assert.doesNotMatch(after, /Waiting for your approval/);
  assert.match(after, /You denied installing llama3\.1:8b\. Nothing changed\./);
});

await check("CONTROL: an approval's `model` event clears the line and says nothing about denying", async () => {
  const page = await tab("faculties", {});
  await installAsked(page);
  await cardGone(page);
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "model", data: {} }));
  await page.waitForTimeout(3600);
  const after = await modelsText(page);
  await page.close();
  assert.doesNotMatch(after, /Waiting for your approval/);
  assert.doesNotMatch(after, /denied/);
});

await check("CONTROL: while its card is still in the queue, the line stays", async () => {
  const page = await tab("faculties", {});
  await installAsked(page);
  // Another card comes and goes; the model's own card is still there.
  await page.evaluate((card) => window.__emit("approvals-changed", { count: 1, items: [card] }), MODEL_CARD);
  await page.waitForTimeout(3600);
  const after = await modelsText(page);
  await page.close();
  assert.match(after, /Waiting for your approval: installing llama3\.1:8b/);
});

await check("Install with nothing typed sends nothing", async () => {
  const page = await tab("faculties", {});
  await page.locator("#model-install").click();
  await page.waitForTimeout(200);
  const calls = await page.evaluate(() => window.__calls);
  await page.close();
  assert.ok(!calls.some((c) => c[0] === "brain_model"), "an empty install was sent");
});

await check("CONTROL: there is no catalogue - no list of models that could be installed", async () => {
  const page = await tab("faculties", {});
  const lists = await page.locator("#models datalist, #models select").count();
  await page.close();
  assert.equal(lists, 0);
});

/* ── Rush latch: `quote` as well as `phrase` ─────────────────────────────── */

await check("a rush latch whose words come as `quote` shows them", async () => {
  const risk = { ...K.BRAIN.content_risk,
    rush: { quote: "approve it now, no time", source: "tool:web_fetch" } };
  // The strip is at the top of every view, so the default one will do.
  const page = await tab("memory", { content_risk: risk });
  const strip = await page.locator("#rush-strip").innerText();
  await page.close();
  assert.match(strip, /approve it now, no time/);
});

/* ── Undo shelf and jobs: the phone's field names ────────────────────────── */

await check("undo rows and jobs in the phone's field names still read", async () => {
  const undo = { available: true, shelf: [
    { id: "p1", label: "Deleted notes.txt", reversible: true, at_ms: Date.now() - 60000 },
    { id: "p2", label: "Sent the invoice", reversible: false, reason: "there is no unsend" }] };
  const jobs = { available: true, jobs: [
    { id: "pj", label: "weekly digest", state: "running", capabilities: ["memory.read"],
      private: true, progress: 0.5 }] };
  const page = await tab("work", { undo, jobs });
  const shelf = await page.locator("#undo").innerText();
  const work = await page.locator("#jobs").innerText();
  const putBack = await page.locator("#undo").getByRole("button", { name: "Put it back" }).count();
  await page.close();
  assert.match(shelf, /Deleted notes\.txt/);
  assert.match(shelf, /Sent the invoice/);
  assert.equal(putBack, 1, "the reversible one (by the phone's name) offers Put it back");
  assert.match(work, /memory\.read/);
  assert.match(work, /50% done/);
  assert.match(work, /private/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nBrain reads what the backend sends");
process.exit(fails.length ? 1 : 0);
