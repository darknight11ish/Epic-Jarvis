/**
 * Focus presets, the desktop reading - a plain Node test, no browser.
 *
 * The real contract is `backend/fixtures/work_presets.json`, generated from
 * `backend/jarvis_presets.py`; this test reads that file itself so the UI
 * cannot drift from the PC's own nine presets and hardware block. The fixture
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
import { budgetFor } from "../src/invoke-budget.js";

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
const withoutApplyRoute = (value) => {
  const other = clone(value);
  for (const preset of other.presets) {
    preset.apply = { ...(preset.apply || {}) };
    delete preset.apply.apply_route;
  }
  return other;
};
const withApplyRoute = (value) => {
  const other = clone(value);
  for (const preset of other.presets) {
    preset.apply = { ...(preset.apply || {}), apply_route: "/api/work/apply" };
  }
  return other;
};

await check("the reading takes the contract's nine presets, in its order", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  assert.equal(read.available, true);
  assert.deepEqual(read.presets.map((p) => p.id), FIXTURE.presets.map((p) => p.id));
  assert.deepEqual(read.presets.map((p) => p.name), FIXTURE.presets.map((p) => p.title));
  assert.equal(
    read.presets.length,
    FIXTURE.presets.length,
    `the reading's preset count drifted from the contract (got ${read.presets.length}, the fixture has ${FIXTURE.presets.length})`,
  );
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

await check("the fixture route plus the wired bridge enables the one action", async () => {
  const read = Focus.normaliseReading(clone(FIXTURE));
  assert.equal(Focus.APPLY_BRIDGE_WIRED, true, "the app-side bridge is wired now");
  assert.equal(read.applyContractReady, true, "the fixture now publishes apply_route");
  assert.equal(read.applyRoute, "/api/work/apply");
  assert.equal(read.applyReady, true);
  assert.equal(read.applyAction, "Use this preset");
  const view = Focus.pickerView(read, "fast");
  assert.equal(view.available, true);
  assert.equal(view.action.label, "Use this preset");
  assert.equal(view.action.disabled, false);
  assert.equal(view.action.why, "");
});

await check("a contract with no apply route keeps the one action disabled, with its waiting line", async () => {
  const read = Focus.normaliseReading(withoutApplyRoute(FIXTURE));
  const wiredButNoRoute = Focus.normaliseReading(withoutApplyRoute(FIXTURE), { applyWired: true });
  assert.equal(wiredButNoRoute.applyReady, false);
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
await check("both the contract route and the app wiring are required", async () => {
  const routed = withApplyRoute(FIXTURE);

  // A backend ahead of the app: the route is there, the app is not wired.
  const notWired = Focus.normaliseReading(routed, { applyWired: false });
  assert.equal(notWired.applyRoute, "/api/work/apply", "the contract route is kept, not hidden");
  assert.equal(notWired.applyContractReady, true);
  assert.equal(notWired.applyWired, false);
  assert.equal(notWired.applyReady, false);
  const waiting = Focus.pickerView(notWired, "fast");
  assert.equal(waiting.action.disabled, true);
  assert.equal(waiting.action.why, Focus.APPLY_WAITING);

  // Both present: the one action is finally ready.
  const wired = Focus.normaliseReading(routed);
  assert.equal(wired.applyContractReady, true);
  assert.equal(wired.applyWired, true);
  assert.equal(wired.applyReady, true);
  assert.equal(Focus.pickerView(wired, "fast").action.disabled, false);

  // App wiring alone, with no contract route, must stay disabled too.
  const noRouteButWired = Focus.normaliseReading(withoutApplyRoute(FIXTURE));
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
  const read = Focus.normaliseReading(other);
  assert.equal(read.applyReady, true);
  assert.equal(read.applyWired, true);
  assert.equal(read.applyRoute, "/api/work/apply");
  const current = Focus.pickerView(read, "coding");
  assert.equal(current.items.find((p) => p.id === "coding").current, true);
  assert.equal(current.action.disabled, true);
  assert.equal(current.action.why, Focus.ALREADY_CHOSEN);
  const different = Focus.pickerView(read, "fast");
  assert.equal(different.action.disabled, false);
  assert.equal(different.action.label, "Use this preset");
});

await check("heavy-mode Coding is refused with the PC's own explanation", async () => {
  const other = withApplyRoute(FIXTURE);
  other.chosen = "general";
  const read = Focus.normaliseReading(other);
  const coding = read.presets.find((p) => p.id === "coding");
  assert.equal(coding.heavyMode, true);
  const view = Focus.pickerView(read, "coding");
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, coding.heavyWords);
  assert.match(view.action.why, /both|heavy|cannot/i);
  assert.equal(view.items.find((p) => p.id === "coding").blockerWords, coding.heavyWords);
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
  const blocker = view.items.find((p) => p.id === "general_uncensored").blockerWords;
  assert.ok(blocker.startsWith(row.pending_words), blocker);
  assert.ok(blocker.includes(row.cost), "the PC's own cost sentence is kept");
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, blocker);
});

await check("Settings is disabled on a stale link, exactly like the bar", async () => {
  const read = Focus.normaliseReading(withApplyRoute(FIXTURE), { applyWired: true });
  const view = Focus.settingsView(read, "fast", { stale: true });
  assert.equal(view.action.disabled, true);
  assert.equal(view.action.why, Focus.STALE_WORDS);
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

await check("the older direct hardware shape stays a compatibility fallback", async () => {
  // PRIMARY is the fixture's {detected, questionnaire}; the old live route sent
  // hardware as the detected object with a top-level questionnaire. Keep reading
  // that fallback, but the live route itself is being aligned to the fixture.
  const older = clone(FIXTURE);
  older.hardware = {
    count: 2,
    cards: [
      { index: 0, name: "RTX 2060", vram_gib: 12, uuid: "a" },
      { index: 1, name: "RTX 2080 SUPER", vram_gib: 8, uuid: "b" },
    ],
    source: "jarvis_hardware.detect()",
  };
  older.questionnaire = FIXTURE.hardware.questionnaire;
  older.chosen = "coding";
  older.active_lane = { key: "coding", base_url: "http://127.0.0.1:11435" };
  const read = Focus.normaliseReading(withApplyRoute(older));
  assert.equal(read.available, true, "the presets themselves are still readable");
  assert.equal(read.hardware.available, true);
  assert.equal(read.hardware.count, 2);
  assert.deepEqual(read.hardware.cards.map((c) => c.name), ["RTX 2060", "RTX 2080 SUPER"]);
  assert.deepEqual(read.hardware.focusChoices, FIXTURE.hardware.questionnaire.focus_choices);
  assert.equal(read.chosen.name, "Coding");
  assert.equal(read.lane.label, "coding");
  const view = Focus.settingsView(read, read.chosenId);
  assert.equal(view.hardware.count, 2);
});

await check("a missing hardware block still says the contract needs updating", async () => {
  const missing = clone(FIXTURE);
  delete missing.hardware;
  const read = Focus.normaliseReading(withApplyRoute(missing));
  assert.equal(read.hardware.available, false);
  assert.equal(read.hardware.why, Focus.CONTRACT_SHAPE_UPDATE);
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
  assert.equal(Focus.resultLine({ ok: true, changed: true, preset: { title: "Coding" } }),
    "Coding is now the chosen preset.");
  assert.equal(Focus.resultLine({ ok: true, changed: true }), "The preset is now chosen.");
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

await check("the JavaScript bridge and the Rust commands name the same seam", async () => {
  const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
  const bridge = read("src/focus-presets-bridge.js");
  const rust = read("src-tauri/src/focus_presets.rs");
  for (const command of ["get_focus_presets", "apply_focus_preset"]) {
    assert.ok(bridge.includes(command), `the bridge does not name ${command}`);
    assert.ok(rust.includes(command), `the Rust module does not expose ${command}`);
  }
  assert.ok(bridge.includes('"/api/work/apply"') || bridge.includes("/api/work/apply"),
    "the bridge comment/route seam no longer names /api/work/apply");
  assert.ok(rust.includes('FOCUS_PRESETS_APPLY_PATH: &str = "/api/work/apply"'),
    "the Rust command does not post to /api/work/apply");
  assert.ok(rust.includes('FOCUS_PRESETS_PATH: &str = "/api/work"'),
    "the Rust command does not read /api/work");
});

await check("the bridged apply waits longer than the PC\'s approval gate", async () => {
  // Rust waits 1200 s for the switch_model card; the JS budget must outlast it so
  // the page does not say "not known" while a real, still-open card can still be
  // answered. Keep the two numbers together.
  assert.ok(budgetFor("apply_focus_preset", "action") >= 1_200_000,
    "the apply bridge gives up before the PC's own approval gate");
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
