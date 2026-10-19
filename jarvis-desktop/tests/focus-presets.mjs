/**
 * Focus presets, the desktop reading - a plain Node test, no browser.
 *
 * The feature is deliberately generic: this test proves the UI takes the
 * preset list, names and words from the answer rather than from hardcoded
 * desktop ids or names, and that only the one "Use this preset" action is
 * enabled - never on load, never on the current preset, never on a stale link,
 * never on a preset the PC is still preparing.
 *
 * The fixture is local stand-in data; the real contract fixture arrives with
 * the backend branch. Nothing here posts to the backend.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as Focus from "../src/focus-presets.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(
  readFileSync(join(HERE, "fixtures", "focus-presets-cases.json"), "utf8"),
);

let passed = 0;
const check = async (what, fn) => {
  await fn();
  passed += 1;
  console.log(`ok    ${what}`);
};

const clone = (value) => JSON.parse(JSON.stringify(value));

await check("the reading takes the preset list from the PC, in its order", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  assert.equal(read.available, true);
  assert.deepEqual(read.presets.map((p) => p.id), FIXTURE.presets.map((p) => p.id));
  assert.deepEqual(read.presets.map((p) => p.name), FIXTURE.presets.map((p) => p.name));
  assert.equal(read.chosenId, "general");
  assert.equal(read.chosen.name, "General");
  assert.equal(read.lane.label, "2080 SUPER chat lane");
});

await check("it is generic: new ids and names flow through untouched", async () => {
  const other = clone(FIXTURE);
  other.chosen = "alpha";
  other.presets = [
    { id: "alpha", name: "Alpha", description: "First from the PC.", ready: true },
    { id: "beta", name: "Beta", description: "Second from the PC.", ready: true },
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
    { presets: [{ name: "only-name", ready: true }] },
    { presets: [{ id: "x", name: "X", ready: true }, { id: "x", name: "X again", ready: true }] },
  ]) {
    const read = Focus.normaliseReading(bad);
    assert.equal(read.available, false, `drew a list from ${JSON.stringify(bad)}`);
    assert.deepEqual(read.presets, []);
    assert.ok(read.why, `no honest line for ${JSON.stringify(bad)}`);
  }
});

await check("the chip is the PC's current name, and a stale link disables it", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const chip = Focus.chipView(read);
  assert.equal(chip.hidden, false);
  assert.equal(chip.label, "General");
  assert.equal(chip.disabled, false);
  const stale = Focus.chipView(read, { stale: true });
  assert.equal(stale.disabled, true);
  assert.equal(stale.why, Focus.STALE_WORDS);
  assert.equal(Focus.chipView(null).hidden, true);
});

await check("the card lists every PC preset with the PC's own description and details", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const view = Focus.pickerView(read, read.chosenId);
  assert.equal(view.available, true);
  assert.equal(view.heading, "Focus presets");
  assert.deepEqual(view.items.map((p) => p.id), FIXTURE.presets.map((p) => p.id));
  for (const item of view.items) {
    const source = FIXTURE.presets.find((p) => p.id === item.id);
    assert.equal(item.description, source.description);
    for (const detail of item.details) {
      assert.ok(detail.label && detail.value, `missing detail for ${item.id}`);
    }
  }
  assert.equal(view.items.find((p) => p.id === "general").current, true);
  // On arrival the current preset is marked, and the one action cannot apply it.
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, Focus.ALREADY_CHOSEN);
});

await check("only an explicit different preset enables the one action", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const view = Focus.pickerView(read, "coding");
  assert.equal(view.action.disabled, false);
  assert.equal(view.action.label, Focus.ACTION);
  assert.equal(view.action.why, "");
  assert.equal(view.items.find((p) => p.id === "coding").selected, true);
  // No preset is applied by drawing it.
  assert.equal(read.chosenId, "general");
});

await check("a preset the PC is still preparing says so and cannot be applied", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const row = FIXTURE.presets.find((p) => p.id === "general_uncensored");
  assert.equal(read.presets.find((p) => p.id === "general_uncensored").ready, false);
  const view = Focus.pickerView(read, "general_uncensored");
  assert.equal(view.items.find((p) => p.id === "general_uncensored").statusWords, row.status_words);
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, row.status_words);
});

await check("stale and busy never leave the action pressable", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  for (const state of [{ stale: true }, { busy: true }]) {
    const view = Focus.pickerView(read, "coding", state);
    assert.equal(view.action.disabled, true);
    assert.ok(view.action.why);
  }
  assert.equal(Focus.pressable({ stale: true }), false);
  assert.equal(Focus.pressable({ busy: true }), false);
  assert.equal(Focus.pressable(), true);
});

await check("Settings draws the same list, the one-card explanation and the current mark", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  const view = Focus.settingsView(read, "general");
  assert.equal(view.oneCard, FIXTURE.one_card);
  assert.equal(view.note, FIXTURE.note);
  assert.equal(view.items.length, FIXTURE.presets.length);
  assert.equal(view.items.find((p) => p.id === "general").current, true);
  assert.equal(view.action.disabled, true);
  const other = Focus.settingsView(read, "fast");
  assert.equal(other.action.disabled, false);
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
      assert.ok(!source.includes(preset.name), `source hardcodes the name ${preset.name}`);
    }
  }
});

console.log(`\n${passed} passed, 0 failed`);
