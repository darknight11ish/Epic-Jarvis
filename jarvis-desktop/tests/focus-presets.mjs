/**
 * Focus presets, the desktop reading - a plain Node test, no browser.
 *
 * The real contract is `backend/fixtures/work_presets.json`, generated from
 * `backend/jarvis_presets.py`; this test reads that file itself so the UI
 * cannot drift from the PC's own five presets and hardware block. The fixture
 * is the contract half: it has no apply route yet, so the one action must be
 * disabled with the waiting line, not silently enabled. The test also injects
 * a contract route and an app-side wiring flag separately, proving BOTH are
 * required - a backend route alone must never light the button before the
 * desktop has the bridge/Rust wiring to send it.
 *
 * The feature is deliberately generic: the test proves the UI takes the preset
 * list, names and words from the answer rather than from hardcoded desktop
 * ids/names, and that only the one "Use this preset" action is enabled after
 * BOTH the apply route and the app wiring exist - never on load, never on the
 * current preset, never on a stale link, never on a preset the PC is preparing.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as Focus from "../src/focus-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(
  readFileSync(join(HERE, "..", "..", "backend", "fixtures", "work_presets.json"), "utf8"),
);

let passed = 0;
const check = async (what, fn) => {
  await fn();
  passed += 1;
  console.log(`ok    ${what}`);
};

const clone = (value) => JSON.parse(JSON.stringify(value));
const withApplyRoute = (value) => {
  const other = clone(value);
  for (const preset of other.presets) {
    preset.apply = { ...(preset.apply || {}), apply_route: "/api/work/apply" };
  }
  return other;
};

await check("the reading takes the contract's five presets, in its order", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  assert.equal(read.available, true);
  assert.deepEqual(read.presets.map((p) => p.id), FIXTURE.presets.map((p) => p.id));
  assert.deepEqual(read.presets.map((p) => p.name), FIXTURE.presets.map((p) => p.title));
  assert.equal(read.presets.length, 5);
  assert.equal(read.presets[0].description, FIXTURE.presets[0].what);
  assert.equal(read.presets[0].focus, FIXTURE.presets[0].focus);
  assert.equal(read.chosen, null, "the contract half does not name a chosen preset yet");
});

await check("it is generic: new ids and titles flow through untouched", async () => {
  const other = clone(FIXTURE);
  other.chosen = "alpha";
  other.presets = [
    { id: "alpha", title: "Alpha", focus: "first", what: "First from the PC.", pending: false,
      model: "model-a", lane: { card: "card a", words: "the first card" }, context: 1234,
      cost: "cheap", worse: "nothing", apply: { action: "Apply it" } },
    { id: "beta", title: "Beta", focus: "second", what: "Second from the PC.", pending: false,
      model: "model-b", lane: { card: "card b", words: "the second card" }, context: 4321,
      cost: "costly", worse: "everything", apply: { action: "Apply it" } },
  ];
  const read = Focus.normaliseReading(other);
  assert.equal(read.available, true);
  assert.deepEqual(read.presets.map((p) => p.id), ["alpha", "beta"]);
  assert.deepEqual(read.presets.map((p) => p.name), ["Alpha", "Beta"]);
  assert.equal(read.chosen.name, "Alpha");
});

await check("a short answer cannot draw invented presets", async () => {
  for (const bad of [
    null, "", "the PC did not answer", {}, { available: true },
    { presets: [] }, { presets: [{ id: "only-id" }] },
    { presets: [{ title: "only-title" }] },
    { presets: [{ id: "x", title: "X" }, { id: "x", title: "X again" }] },
  ]) {
    const read = Focus.normaliseReading(bad);
    assert.equal(read.available, false, `drew a list from ${JSON.stringify(bad)}`);
    assert.deepEqual(read.presets, []);
    assert.ok(read.why, `no honest line for ${JSON.stringify(bad)}`);
  }
});

await check("the contract half keeps the one action disabled, with its waiting line", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  assert.equal(Focus.APPLY_BRIDGE_WIRED, false, "the app-side apply wiring must ship OFF");
  assert.equal(read.applyReady, false);
  assert.equal(read.applyContractReady, false);
  assert.equal(read.applyRoute, "");
  assert.equal(read.applyAction, "Use this preset");
  const view = Focus.pickerView(read, "fast");
  assert.equal(view.available, true);
  assert.equal(view.action.label, "Use this preset");
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, Focus.APPLY_WAITING);
});

await check("a contract route alone is not enough: the app wiring decides the button", async () => {
  const routed = withApplyRoute(FIXTURE);
  const notWired = Focus.normaliseReading(routed);
  assert.equal(notWired.applyRoute, "/api/work/apply", "the contract route is kept, not hidden");
  assert.equal(notWired.applyContractReady, true);
  assert.equal(notWired.applyWired, false);
  assert.equal(notWired.applyReady, false);
  const waiting = Focus.pickerView(notWired, "fast");
  assert.equal(waiting.action.disabled, true);
  assert.equal(waiting.action.why, Focus.APPLY_WAITING);

  const wired = Focus.normaliseReading(routed, { applyWired: true });
  assert.equal(wired.applyContractReady, true);
  assert.equal(wired.applyWired, true);
  assert.equal(wired.applyReady, true);
  assert.equal(Focus.pickerView(wired, "fast").action.disabled, false);

  // ...and app wiring alone, with no contract route, must stay disabled too.
  const noRouteButWired = Focus.normaliseReading(clone(FIXTURE), { applyWired: true });
  assert.equal(noRouteButWired.applyReady, false);
  assert.equal(Focus.pickerView(noRouteButWired, "fast").action.disabled, true);
  assert.equal(Focus.pickerView(noRouteButWired, "fast").action.why, Focus.APPLY_WAITING);
});

await check("the chip is hidden without a reading, and names the PC's chosen preset", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const noChoice = Focus.chipView(read);
  assert.equal(noChoice.hidden, false);
  assert.equal(noChoice.label, Focus.NO_CHOICE_WORDS);
  const chosen = clone(FIXTURE);
  chosen.chosen = "coding";
  const withChoice = Focus.normaliseReading(chosen);
  assert.equal(Focus.chipView(withChoice).label, "Coding");
  const stale = Focus.chipView(withChoice, { stale: true });
  assert.equal(stale.disabled, true);
  assert.equal(stale.why, Focus.STALE_WORDS);
  assert.equal(Focus.chipView(null).hidden, true);
});

await check("the card lists every contract preset with its own words and details", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const view = Focus.pickerView(read, "");
  assert.equal(view.available, true);
  assert.deepEqual(view.items.map((p) => p.id), FIXTURE.presets.map((p) => p.id));
  for (const item of view.items) {
    const source = FIXTURE.presets.find((p) => p.id === item.id);
    assert.equal(item.name, source.title);
    assert.equal(item.focus, source.focus);
    assert.equal(item.description, source.what);
    const details = new Map(item.details.map((d) => [d.label, d.value]));
    assert.equal(details.get("Model"), source.model);
    assert.equal(details.get("Lane"), `${source.lane.card} · ${source.lane.words}`);
    assert.equal(details.get("Context"), `${source.context.toLocaleString("en-US")} tokens`);
    assert.equal(details.get("Cost"), source.cost);
    assert.equal(details.get("Worse at"), source.worse);
  }
});

await check("an apply route plus app wiring enables the one action; the current preset stays inert", async () => {
  const other = withApplyRoute(FIXTURE);
  other.chosen = "coding";
  const read = Focus.normaliseReading(other, { applyWired: true });
  assert.equal(read.applyReady, true);
  assert.equal(read.applyRoute, "/api/work/apply");
  const current = Focus.pickerView(read, "coding");
  assert.equal(current.items.find((p) => p.id === "coding").current, true);
  assert.equal(current.action.disabled, true);
  assert.equal(current.action.why, Focus.ALREADY_CHOSEN);
  const different = Focus.pickerView(read, "fast");
  assert.equal(different.action.disabled, false);
  assert.equal(different.action.label, "Use this preset");
});

await check("a preset the PC is preparing says so and cannot be applied", async () => {
  const other = withApplyRoute(FIXTURE);
  other.chosen = "general";
  const row = other.presets.find((p) => p.id === "general_uncensored");
  row.pending = true;
  row.pending_words = "The uncensored model is still being installed.";
  const read = Focus.normaliseReading(other, { applyWired: true });
  assert.equal(read.presets.find((p) => p.id === "general_uncensored").ready, false);
  const view = Focus.pickerView(read, "general_uncensored");
  assert.equal(view.items.find((p) => p.id === "general_uncensored").statusWords, row.pending_words);
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, row.pending_words);
});

await check("stale and busy never leave the action pressable", async () => {
  const read = Focus.normaliseReading(withApplyRoute(FIXTURE), { applyWired: true });
  for (const state of [{ stale: true }, { busy: true }]) {
    const view = Focus.pickerView(read, "fast", state);
    assert.equal(view.action.disabled, true);
    assert.ok(view.action.why);
  }
  assert.equal(Focus.pressable({ stale: true }), false);
  assert.equal(Focus.pressable({ busy: true }), false);
  assert.equal(Focus.pressable(), true);
});

await check("the hardware block is read generically and shown in Settings", async () => {
  const other = clone(FIXTURE);
  other.hardware.detected = {
    count: 2,
    cards: [
      { index: 0, name: "RTX 2060", vram_gib: 12, uuid: "a" },
      { index: 1, name: "RTX 2080 SUPER", vram_gib: 8, uuid: "b" },
    ],
    source: "test",
  };
  const read = Focus.normaliseReading(other);
  assert.equal(read.hardware.available, true);
  assert.equal(read.hardware.count, 2);
  assert.deepEqual(read.hardware.cards.map((c) => c.name), ["RTX 2060", "RTX 2080 SUPER"]);
  assert.deepEqual(read.hardware.focusChoices, other.hardware.questionnaire.focus_choices);
  const view = Focus.settingsView(read, read.chosenId);
  assert.equal(view.hardware.count, 2);
  assert.deepEqual(view.hardware.priorityChoices, other.hardware.questionnaire.priority_choices);
});

await check("Settings draws the same list, the one-card explanation and the current mark", async () => {
  const other = withApplyRoute(FIXTURE);
  other.chosen = "general";
  const read = Focus.normaliseReading(other, { applyWired: true });
  const view = Focus.settingsView(read, "general");
  assert.equal(view.oneCard, Focus.ONE_CARD);
  assert.equal(view.items.length, FIXTURE.presets.length);
  assert.equal(view.items.find((p) => p.id === "general").current, true);
  assert.equal(view.action.disabled, true);
  const different = Focus.settingsView(read, "fast");
  assert.equal(different.action.disabled, false);
});

await check("the result line uses the PC's words, with a card sentence only as fallback", async () => {
  assert.equal(Focus.resultLine({ said: "The card is waiting on the PC." }),
    "The card is waiting on the PC.");
  assert.equal(Focus.resultLine({ ok: false, error: "no such preset" }), "no such preset");
  assert.equal(Focus.resultLine({ pending: true }), Focus.ASKED_WORDS);
  assert.equal(Focus.resultLine(""), "");
  assert.equal(Focus.resultLine(null), "");
});

await check("the one action posts the PC's own id in one named field", async () => {
  assert.deepEqual(Focus.applyArgs("coding"), { preset: "coding" });
  assert.deepEqual(Focus.applyArgs("coding", "id"), { id: "coding" });
});

await check("a camelCase answer is read too, so the bridge may hand it on unchanged", async () => {
  const other = {
    available: true,
    current: "beta",
    laneStatus: "ready",
    presets: [{
      id: "beta", label: "Beta", words: "Second from the PC.",
      model: "model-b", lane: "card-b", worseAt: "nothing yet",
    }],
  };
  const read = Focus.normaliseReading(other);
  assert.equal(read.available, true);
  assert.equal(read.chosen.name, "Beta");
  assert.equal(read.presets[0].description, "Second from the PC.");
  assert.equal(read.presets[0].details.find((d) => d.label === "Worse at").value, "nothing yet");
});

await check("no preset id or name is hardcoded in the source", async () => {
  const sources = ["focus-presets.js", "focus-presets-bar.js", "focus-presets-settings.js", "focus-presets-bridge.js"]
    .map((name) => readFileSync(join(HERE, "..", "src", name), "utf8"));
  for (const source of sources) {
    for (const preset of FIXTURE.presets) {
      assert.ok(!source.includes(preset.id), `source hardcodes the id ${preset.id}`);
      assert.ok(!source.includes(preset.title), `source hardcodes the name ${preset.title}`);
    }
  }
});

console.log(`\n${passed} passed, 0 failed`);
