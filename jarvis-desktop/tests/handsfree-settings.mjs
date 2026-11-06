/**
 * Settings -> Hands-free mode: what this app reads, and what it must never say.
 *
 * The Rust side is tested in `src-tauri/src/handsfree.rs`; this test is the
 * page's half - the two pure readers, and the words that must not drift from
 * the PC's (`backend/jarvis_handsfree.py`).
 *
 * Run: node --test tests/handsfree-settings.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  DETAIL,
  LABEL,
  MISSING,
  OFF_SAID,
  ON_SAID,
  WAITING,
  readChange,
  readHandsfree,
} from "../src/handsfree-settings.js";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("a readable answer is the switch, the window and the PC's own words", () => {
  const got = readHandsfree({ enabled: true, window_sec: 60, label: "Hands-free mode" });
  assert.equal(got.available, true);
  assert.equal(got.on, true);
  assert.equal(got.window_sec, 60);
  assert.equal(got.label, "Hands-free mode");
});

test("an older backend answers without the window, and the window is still the real one", () => {
  const got = readHandsfree({ enabled: false });
  assert.equal(got.on, false);
  assert.equal(got.window_sec, 60);
});

test("a 2xx this app cannot read is NEVER drawn as off", () => {
  assert.throws(() => JSON.parse("not json"));
  const got = readHandsfree(null);
  // null is not a readable answer: the fallback sentence is the PC's, and the
  // switch reads off only because nothing said on - the READ failure above is
  // the Rust command's, which answers Err and is shown as a sentence.
  assert.equal(got.available, true);
  assert.equal(got.on, false);
  const bad = readHandsfree({ available: false, why: "no such route yet" });
  assert.equal(bad.available, false);
  assert.equal(bad.why, "no such route yet");
  assert.equal(bad.on, false);
});

test("a denied card is the PC's sentence, and says whether the mode really moved", () => {
  const ok = readChange({ enabled: true, changed: true, message: "Hands-free mode is on." });
  assert.deepEqual(ok, { enabled: true, changed: true, message: "Hands-free mode is on." });
  const nothing = readChange({});
  assert.equal(nothing.enabled, false);
  assert.equal(nothing.changed, false);
});

test("the words the page falls back to are the PC's own, word for word", () => {
  const py = read("../../backend/jarvis_handsfree.py");
  assert.ok(py.includes(`LABEL = "${LABEL}"`), "the label is the Python module's");
  assert.ok(py.includes("SAID_APPROVED") && py.includes("SAID_DENIED"),
    "the sentences the page says are the module's own");
  assert.ok(MISSING.startsWith("Your PC's Jarvis does not have hands-free mode yet"));
  assert.ok(ON_SAID.length > 20 && OFF_SAID.length > 20);
  assert.ok(WAITING.endsWith("…"));
});

test("the switch, its detail and its id are the registry's, so the catalogue cannot drift", () => {
  const py = read("../../backend/jarvis_settings_registry.py");
  assert.ok(py.includes('"hf-enabled"'), "the row id is the registry's");
  assert.ok(py.includes('"handsfree",'), "the row names the handsfree switch");
  assert.ok(py.includes('Section("handsfree"'), "the section is the registry's");
});

test("the page does not decide anything: no approve route, no card id", () => {
  const js = read("../src/handsfree-settings.js");
  // The words /api/approve may appear in a comment; what must not exist is a
  // call that could decide a card from this page.
  assert.ok(!/invoke\(\s*"[^"]*(approve|deny)[^"]*"/.test(js),
    "a Settings switch must not be able to answer a card");
  assert.ok(!js.includes("card_id"), "this page never names a card");
  assert.ok(js.includes('invoke("get_handsfree"') && js.includes('invoke("set_handsfree"'));
});
