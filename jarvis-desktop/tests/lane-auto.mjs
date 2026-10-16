/**
 * Jarvis restarts a dead model lane by itself - the desktop half, and the
 * switch that tells an automatic restart apart from a deliberate stop.
 *
 * WHAT THIS HOLDS, and why each one matters. The owner's decision of
 * 2026-10-14 was *"Also restart the lane automatically when it dies."* The
 * BACKEND does that (`backend/jarvis_model_lanes.py`); this app's job is to be
 * TOLD, because a silent automatic restart is a change to his machine that he
 * did not make.
 *
 * 1. **The words are the backend's own, drawn verbatim.** `auto_note` is
 *    written in one place and carried on `GET /api/model-lanes`; this app
 *    composes nothing, so the bar, the widget and the phone cannot come to
 *    three ways of saying one fact - the same rule the approval notice follows
 *    (`docs/ARCHITECTURE.md` §3). A CONTROL below fails if this file ever
 *    starts assembling a sentence out of fields.
 * 2. **It can be said while the lane is UP.** The standing warning clears the
 *    moment the model answers, and "it went down and Jarvis started it again"
 *    is exactly that moment - which is why the line is its own element and not
 *    a line inside the warning.
 * 3. **The switch is the honest half.** A dead process carries no intent, so
 *    only the owner can say whether the lane was stopped on purpose. The press
 *    asks the PC; the app never changes its own words to claim a change the PC
 *    did not make.
 * 4. **The cap falls back to the warning.** With `auto_capped` set, the line is
 *    the backend's "it has stopped trying" sentence and the warning stands.
 * 5. **Both windows, one file** - and neither invents a switch on an older
 *    backend that does not report one.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  AUTO_SWITCH_OFF_WORDS,
  AUTO_SWITCH_ON_WORDS,
  autoNotice,
  autoSwitchOn,
  paintAutoNotice,
} from "../src/lane-auto.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The sentence the backend writes when it restarts a lane by itself. */
const RESTARTED = "Jarvis started the local model again at 08:19, because it was not running. "
  + "It is waiting for it to answer.";
/** And the one it leaves when it has stopped trying. */
const GAVE_UP = "Jarvis started the local model 3 times and it did not come up, so it has "
  + "stopped trying. You can still start it yourself.";
/** And the one for "you turned this off". */
const OFF = "Jarvis is not starting the local model by itself: automatic restarting is off.";

/** A lane reading, as the backend sends it. Defaults: up, switch on, quiet. */
const lane = (over = {}) => ({
  ok: true,
  lane: "everyday",
  words: "the everyday model (the main one chat uses)",
  port: 11436,
  task: "Jarvis Ollama - Everyday model (RTX 2060)",
  state: "up",
  can_start: false,
  why: "It is answering - nothing to do.",
  message: "",
  auto: true,
  auto_attempts: 0,
  auto_limit: 3,
  auto_capped: false,
  auto_note: "",
  ...over,
});

/* ── 1. The rule: the backend's sentence, drawn as it stands ─────────────── */

await check("a lane Jarvis restarted is said in the backend's own words", async () => {
  const view = autoNotice(lane({ auto_note: RESTARTED, auto_attempts: 1 }));
  assert.equal(view.show, true);
  assert.equal(view.words, RESTARTED, "the sentence was rewritten on the way to the screen");
  assert.equal(view.switchWords, AUTO_SWITCH_OFF_WORDS);
  assert.equal(view.switchTo, false, "the press must ask for the switch to go OFF");
});

await check("CONTROL: a quiet, working lane draws nothing at all", async () => {
  const view = autoNotice(lane());
  assert.equal(view.show, false);
  assert.equal(view.words, "");
  // And the older backend that has no such field: no note, and NO SWITCH. A
  // window must not offer to turn off something that was never on.
  const old = autoNotice({ ok: true, state: "up" });
  assert.equal(old.show, false);
  assert.equal(old.switchWords, "");
  assert.equal(old.switchTo, null);
  assert.equal(autoSwitchOn({ ok: true }), undefined);
  assert.equal(autoNotice(null).show, false);
  assert.equal(autoNotice("not an object").show, false);
});

await check("the cap says so in the backend's sentence, and the switch stays usable", async () => {
  const view = autoNotice(lane({
    state: "down", can_start: true, auto_capped: true, auto_attempts: 3,
    auto_note: GAVE_UP,
  }));
  assert.equal(view.show, true);
  assert.equal(view.words, GAVE_UP);
  assert.equal(view.capped, true);
  // Nothing here composes a "gave up" of its own, and nothing hides the warning.
  assert.ok(!view.words.includes("nearly"), view.words);
});

await check("the switch's own sentence is drawn while the lane is UP as well", async () => {
  // This is the whole reason the line is its own element: the warning is hidden
  // when the lane answers, and this is when the owner needs the way back on.
  const view = autoNotice(lane({ auto: false, auto_note: OFF }));
  assert.equal(view.show, true);
  assert.equal(view.words, OFF);
  assert.equal(view.switchWords, AUTO_SWITCH_ON_WORDS);
  assert.equal(view.switchTo, true);
});

await check("CONTROL: an over-long or missing note never becomes a sentence", async () => {
  const blank = autoNotice(lane({ auto_note: "   " }));
  assert.equal(blank.show, false, "whitespace was drawn as a line");
  assert.equal(blank.words, "");
});

/* ── 2. The DOM half ────────────────────────────────────────────────────── */

function fakePage(ids) {
  const nodes = new Map();
  for (const id of ids) {
    nodes.set(id, { id, textContent: "", hidden: true, disabled: false, onclick: null });
  }
  return { getElementById: (id) => nodes.get(id) || null, at: (id) => nodes.get(id) };
}

const ROW_IDS = ["model-auto", "model-auto-text", "model-auto-switch"];

await check("the line and its switch are drawn, and the press asks the PC", async () => {
  const doc = fakePage(ROW_IDS);
  const asked = [];
  assert.equal(paintAutoNotice(doc, lane({ auto_note: RESTARTED, auto_attempts: 1 }),
    (on) => asked.push(on)), true);
  assert.equal(doc.at("model-auto").hidden, false);
  assert.equal(doc.at("model-auto-text").textContent, RESTARTED);
  assert.equal(doc.at("model-auto-switch").hidden, false);
  assert.equal(doc.at("model-auto-switch").textContent, AUTO_SWITCH_OFF_WORDS);
  assert.equal(typeof doc.at("model-auto-switch").onclick, "function");
  doc.at("model-auto-switch").onclick();
  assert.deepEqual(asked, [false], "the press did not ask for OFF");
  // THE APP DOES NOT ANSWER ITSELF: the words and the button are unchanged
  // until the PC's own reading comes back.
  assert.equal(doc.at("model-auto-text").textContent, RESTARTED);
  assert.equal(doc.at("model-auto-switch").textContent, AUTO_SWITCH_OFF_WORDS);
});

await check("a quiet lane clears the line, and leaves no press behind", async () => {
  const doc = fakePage(ROW_IDS);
  paintAutoNotice(doc, lane({ auto_note: RESTARTED }), () => {});
  assert.equal(paintAutoNotice(doc, lane(), () => {}), false);
  assert.equal(doc.at("model-auto").hidden, true);
  assert.equal(doc.at("model-auto-text").textContent, "");
  assert.equal(doc.at("model-auto-switch").hidden, true);
  assert.equal(doc.at("model-auto-switch").onclick, null, "a cleared switch kept its handler");
});

await check("an older backend draws the sentence with NO switch offered", async () => {
  const doc = fakePage(ROW_IDS);
  assert.equal(paintAutoNotice(doc, { state: "down", auto_note: RESTARTED }, () => {}), true);
  assert.equal(doc.at("model-auto-text").textContent, RESTARTED);
  assert.equal(doc.at("model-auto-switch").hidden, true,
    "a switch was offered by a backend that never reported one");
  assert.equal(doc.at("model-auto-switch").onclick, null);
});

await check("a refused press is said plainly, and the switch is not moved", async () => {
  const doc = fakePage(ROW_IDS);
  paintAutoNotice(doc, lane({ auto_note: RESTARTED }), () => {},
    "This PC could not write its own setting file, so nothing changed.");
  assert.equal(doc.at("model-auto-text").textContent,
    "This PC could not write its own setting file, so nothing changed.");
  assert.equal(doc.at("model-auto-switch").disabled, true,
    "the switch stayed pressable after a refusal");
  assert.equal(doc.at("model-auto-switch").onclick, null);
});

await check("CONTROL: a page without the line is not an error", async () => {
  assert.equal(paintAutoNotice(fakePage(["model-auto"]), lane({ auto_note: RESTARTED }), null), false);
  assert.equal(paintAutoNotice({ getElementById: () => null }, lane({ auto_note: RESTARTED }), null), false);
});

/* ── 3. One place writes the words, and both windows draw them ──────────── */

await check("CONTROL: this app never composes the sentence itself", async () => {
  const raw = read("src/lane-auto.js");
  const code = raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  // The only fields the rule reads are the backend's own note and switch. A
  // client that builds a summary out of elapsed seconds or a `why` string has
  // reopened the hole this rule exists to close, on the surface where it is
  // least recoverable.
  for (const field of ["elapsed_s", "left_s", ".why", ".message", "waited_s", "auto_attempts"]) {
    assert.ok(!code.includes(field), `lane-auto.js builds its own words from ${field}`);
  }
  assert.ok(code.includes("auto_note"), "the backend's own sentence is not what is drawn");
});

await check("the bar and the widget both draw it, from the one file", async () => {
  const bar = read("src/index.html");
  const barJs = read("src/main.js");
  const widget = read("src/widget.html");
  const widgetJs = read("src/widget.js");
  for (const id of ["model-auto", "model-auto-text", "model-auto-switch"]) {
    assert.ok(bar.includes(`id="${id}"`), `the bar has no #${id}`);
  }
  for (const id of ["widget-auto", "widget-auto-text", "widget-auto-switch"]) {
    assert.ok(widget.includes(`id="${id}"`), `the widget has no #${id}`);
  }
  for (const [name, js] of [["the bar", barJs], ["the widget", widgetJs]]) {
    assert.ok(js.includes('from "./lane-auto.js"'), `${name} does not import the rule`);
    assert.ok(js.includes("paintAutoNotice("), `${name} never draws the line`);
    assert.ok(js.includes('"set_model_lane_auto"'), `${name} never asks the PC for the switch`);
  }
  // Its own element OUTSIDE the standing warning, so it can be said while the
  // lane is up - the moment the warning has cleared.
  const warnEnd = bar.indexOf("</div>", bar.indexOf('id="model-warn"'));
  const autoAt = bar.indexOf('id="model-auto"');
  assert.ok(warnEnd !== -1 && autoAt > warnEnd,
    "the line was put inside the warning that hides itself when the lane is up");
});

await check("the lane is read on the beat whether or not the warning is drawn", async () => {
  // The old shape read `/api/model-lanes` only while the standing line was
  // drawn - which is exactly when the "Jarvis restarted it and it came back"
  // sentence can never be said.
  const barJs = read("src/main.js");
  const widgetJs = read("src/widget.js");
  for (const [name, js] of [["the bar", barJs], ["the widget", widgetJs]]) {
    assert.ok(js.includes("refreshLane();"), `${name} never reads the lane on the beat`);
    assert.ok(!/if \(laneDown\) refreshLaneStart/.test(js),
      `${name} still reads the lane only while the warning is drawn`);
    assert.ok(!/if \(warn\.down\) refreshLaneStart/.test(js),
      `${name} still reads the lane only while the row is down`);
  }
});

/* ── 4. The Rust half: argv discipline, and the right route ─────────────── */

await check("the Rust side posts the one option to the one route, and starts nothing", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const call = rust.slice(
    rust.indexOf("pub async fn set_model_lane_auto"),
    rust.indexOf("pub(crate) fn summarise_health"),
  );
  assert.ok(call.includes("/api/model-lanes/auto"), "the command calls another route");
  assert.ok(call.includes('json!({ "on": on })'), "the command does not send the switch's state");
  assert.ok(call.includes("is_success"), "the command does not read the status");
  assert.ok(!call.includes("Command::new"), "Rust starts a process of its own");
  assert.ok(!call.includes("schtasks"), "Rust runs schtasks itself instead of the PC's task");
  // One fact about one lane: the body carries the switch and nothing else, so
  // no client can aim this at another lane or at both.
  const body = call.slice(call.indexOf("json!"), call.indexOf(".send()"));
  assert.ok(!body.includes("lane"), `the body names a lane: ${body}`);
  const lib = read("src-tauri/src/lib.rs");
  assert.ok(lib.includes("commands::set_model_lane_auto,"), "the command is not registered");
});

await check("each window guards on its OWN element, not on the other's", async () => {
  // The audit of 2026-10-14 found the widget's `paintLane` beginning with
  // `if (!dom.modelStart) return;`, which would have hidden the automatic line
  // in any window whose Start-button markup went missing while the automatic
  // line's own element was there. The two halves are independent surfaces.
  const widgetJs = read("src/widget.js");
  const fn = widgetJs.slice(widgetJs.indexOf("function paintLane()"));
  const body = fn.slice(0, fn.indexOf("\n}"));
  assert.ok(!/if \(!dom\.modelStart\) return;/.test(body),
    "the widget's automatic line is gated on the Start button's element");
  assert.ok(body.includes("if (dom.modelStart) {"), "the button half no longer guards itself");
  assert.ok(body.includes("paintAutoNotice("), "the widget stopped drawing the automatic line");
});

await check("CONTROL: lane-start.js and lane-warning.js are untouched in what they promise", async () => {
  // This work adds a file beside them rather than changing what they are: the
  // warning still acts on nothing, and the button still runs the owner's own
  // task and never reports success it does not have.
  const warning = read("src/lane-warning.js")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  for (const verb of ["fetch(", "invoke(", "spawn", "restart", "POST", "exec("]) {
    assert.ok(!warning.includes(verb), `lane-warning.js acts on the world: ${verb}`);
  }
  const start = read("src/lane-start.js");
  assert.ok(start.includes("startUntilSettled"), "the action file lost its loop");
  assert.ok(!start.includes("auto_note"), "the action file grew the automatic half");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nA dead lane is restarted by Jarvis, and said");
