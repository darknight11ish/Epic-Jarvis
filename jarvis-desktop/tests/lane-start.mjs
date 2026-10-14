/**
 * The button that starts the model lane that is down - the desktop half.
 *
 * WHAT THIS HOLDS, and why each one matters. The standing line PR #409 added
 * deliberately did nothing, and the owner has since decided it should offer ONE
 * action. The failure mode named in the brief is exact: **a button that reports
 * success and changes nothing.** Starting a Windows task returns long before a
 * model is loaded, so the whole feature is a claim about what is TRUE, not
 * about what was asked for:
 *
 * 1. **A down lane offers the button; an up lane does not.** And neither does a
 *    lane the PC did not report - "the PC did not say" is not "it is down",
 *    which is the rule `lane-warning.js` already follows.
 * 2. **A start that does not come up does NOT clear the warning.** The press
 *    resolves with a plain sentence from the PC, the warning stays standing,
 *    and nothing anywhere says "up".
 * 3. **It never starts a second task.** A press while one is being watched does
 *    nothing, and the PC's own "already running" answer starts nothing.
 * 4. **CONTROL: the rule file still acts on nothing.** `lane-warning.js` was
 *    pinned as a module with no verb for starting anything; this work moves the
 *    action into a second file rather than weakening that check.
 * 5. **One action, on the live line, in both windows** - from the one file, so
 *    the bar and the widget cannot come to different words for one fact.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  CANNOT_START_WORDS,
  laneIsUp,
  paintStartButton,
  refusalWords,
  START_WORDS,
  STARTING_WORDS,
  startButton,
  startUntilSettled,
  WATCH_BEAT_MS,
  WATCH_LIMIT_MS,
} from "../src/lane-start.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** A lane reading, as the backend sends it. Defaults: down, and pressable. */
const lane = (over = {}) => ({
  ok: true,
  lane: "everyday",
  words: "the everyday model (the main one chat uses)",
  port: 11436,
  task: "Jarvis Ollama - Everyday model (RTX 2060)",
  state: "down",
  can_start: true,
  why: "Nothing is answering on port 11436.",
  message: "",
  ...over,
});

/* ── 1. When the button is offered ──────────────────────────────────────── */

await check("a lane that is down offers the one action", async () => {
  const view = startButton(lane());
  assert.equal(view.show, true);
  assert.equal(view.disabled, false);
  assert.equal(view.words, START_WORDS);
  assert.equal(START_WORDS, "Start the local model");
});

await check("CONTROL: an up lane offers nothing, and an unknown lane offers nothing", async () => {
  for (const reading of [lane({ state: "up", can_start: false }), null, undefined, {}]) {
    const view = startButton(reading);
    assert.equal(view.show, false, `a reading drew a button: ${JSON.stringify(reading)}`);
    assert.equal(view.disabled, true);
  }
});

await check("a PC with no such task shows the reason and NO button", async () => {
  const view = startButton(lane({
    can_start: false,
    task: "",
    why: 'This PC has no scheduled task whose name starts with "Jarvis Ollama - Everyday model".',
  }));
  assert.equal(view.show, false, "a button was offered with nothing to start");
  assert.match(view.note, /no scheduled task/);
});

await check("while it is starting the button says so and cannot be pressed again", async () => {
  const view = startButton(lane({ state: "starting", can_start: false,
    message: "Starting the local model. It has been 6 seconds; this can take up to a minute." }));
  assert.equal(view.show, true);
  assert.equal(view.disabled, true, "the button stayed pressable while a start was in flight");
  assert.equal(view.words, STARTING_WORDS);
  assert.match(view.note, /6 seconds/);
});

await check("CONTROL: the words promise nothing they cannot do", async () => {
  assert.ok(!START_WORDS.includes("!"), "no alarm in the button");
  assert.ok(!STARTING_WORDS.includes("!"), "no alarm while starting");
  assert.equal(CANNOT_START_WORDS.indexOf("!"), -1);
  // It says "the local model", not the product name: the owner is a beginner,
  // and the standing line beside it already names Ollama in brackets.
  assert.ok(!START_WORDS.includes("Ollama"), START_WORDS);
  // And only the lane that is really up counts as up.
  assert.equal(laneIsUp(lane({ state: "starting" })), false);
  assert.equal(laneIsUp(lane({ state: "down" })), false);
  assert.equal(laneIsUp(lane({ state: "up" })), true);
  assert.equal(laneIsUp(null), false);
});

/* ── 2. Pressing it ─────────────────────────────────────────────────────── */

/** A fake PC: `readings` are what successive reads answer. */
function fakePc(startReply, readings) {
  const asked = [];
  let at = 0;
  return {
    asked,
    ask: async () => { asked.push("start"); return startReply; },
    read: async () => {
      asked.push("read");
      const next = readings[Math.min(at, readings.length - 1)];
      at += 1;
      return next;
    },
  };
}

const noWait = { wait: async () => {}, now: (() => { let t = 0; return () => (t += 1000); })() };

await check("a start that never comes up does NOT clear the warning", async () => {
  const pc = fakePc(
    lane({ state: "starting", changed: true, waiting: true,
      message: 'Started this PC\'s own task "Jarvis Ollama - Everyday model (RTX 2060)". Waiting for it to answer.' }),
    [lane({ state: "starting", can_start: false }),
     lane({ state: "starting", can_start: false }),
     lane({ state: "down", can_start: false,
       message: "The lane did not answer within 90 seconds of its task being started, so it did not come up. It is still down." })],
  );
  const out = await startUntilSettled(pc.ask, pc.read, noWait);
  assert.equal(out.ok, false, "a start that failed was reported as a success");
  assert.equal(out.settled, true, "the loop never reached the PC's own verdict");
  assert.equal(laneIsUp(out.lane), false);
  assert.match(out.words, /did not come up/, out.words);
  assert.ok(!/answered|is up|working/i.test(out.words), `a false claim: ${out.words}`);
  // And it really asked again rather than believing the press.
  assert.ok(pc.asked.filter((a) => a === "read").length >= 3, pc.asked);
});

await check("a start that does come up clears it - and only on a real 'up'", async () => {
  const pc = fakePc(lane({ state: "starting", changed: true, waiting: true }),
    [lane({ state: "starting", can_start: false }),
     lane({ state: "up", can_start: false, message: "The local model came back after 21 seconds." })]);
  const out = await startUntilSettled(pc.ask, pc.read, noWait);
  assert.equal(out.ok, true);
  assert.equal(out.settled, true);
  assert.equal(laneIsUp(out.lane), true);
  assert.equal(out.words, "", "a cleared warning carried words of its own");
});

await check("a lane that was already answering when pressed starts nothing", async () => {
  const pc = fakePc(lane({ state: "up", changed: false, can_start: false,
    message: "The local model is already answering - nothing was started." }), []);
  const out = await startUntilSettled(pc.ask, pc.read, noWait);
  assert.equal(out.ok, true);
  assert.equal(out.settled, true);
  assert.equal(laneIsUp(out.lane), true);
  assert.deepEqual(pc.asked, ["start"], "it kept asking after the lane was already up");
});

await check("a refusal is shown in the PC's own words, and the warning stands", async () => {
  const said = 'This PC has no scheduled task whose name starts with "Jarvis Ollama - Everyday model", so there is nothing to start.';
  const pc = fakePc({ ok: false, changed: false, state: "down", error: said }, []);
  const out = await startUntilSettled(pc.ask, pc.read, noWait);
  assert.equal(out.ok, false);
  assert.equal(out.settled, true);
  assert.equal(out.refused, true);
  assert.equal(out.words, said, "the PC's own sentence was replaced");
  assert.deepEqual(pc.asked, ["start"], "a refused press was retried behind the owner's back");
});

await check("a press that never reached the PC says something plain, and does not claim success", async () => {
  const pc = {
    ask: async () => { throw new Error("The Jarvis backend did not answer."); },
    read: async () => { throw new Error("should not be read"); },
  };
  const out = await startUntilSettled(pc.ask, pc.read, noWait);
  assert.equal(out.ok, false);
  assert.equal(out.settled, true);
  // The shell's own sentence is already plain words for the owner ("the Jarvis
  // backend did not answer" - `plain_errors::unreachable_words`), so it is what
  // is shown rather than being replaced by a vaguer one.
  assert.match(out.words, /did not answer/, out.words);
  assert.ok(!/(is up|working)\b/i.test(out.words), `a false claim: ${out.words}`);
  // And when there is nothing to quote at all, the fallback is still plain and
  // still says the warning stands.
  assert.match(refusalWords(null), /still not running/);
  assert.ok(!/\bnull\b|\bundefined\b/.test(refusalWords(null)), refusalWords(null));
  // And when the PC DID say something, that is what is used.
  assert.equal(refusalWords({ error: "This PC has no such task." }), "This PC has no such task.");
});

await check("a read that fails mid-watch is not read as 'it came up'", async () => {
  let reads = 0;
  const pc = {
    ask: async () => lane({ state: "starting", changed: true }),
    read: async () => {
      reads += 1;
      if (reads < 3) throw new Error("the PC went quiet");
      return lane({ state: "down", can_start: false,
        message: "The lane did not answer within 90 seconds of its task being started, so it did not come up. It is still down." });
    },
  };
  const out = await startUntilSettled(pc.ask, pc.read, noWait);
  assert.equal(out.ok, false);
  assert.equal(out.settled, true);
  assert.ok(reads >= 3, "a failed read ended the watch early");
});

await check("it stops asking at the limit, and says it could not tell", async () => {
  // A clock that runs out: the PC never gives a verdict.
  let t = 0;
  const pc = fakePc(lane({ state: "starting", changed: true }),
    [lane({ state: "starting", can_start: false })]);
  const out = await startUntilSettled(pc.ask, pc.read, {
    wait: async () => {},
    now: () => (t += WATCH_LIMIT_MS + 1),
  });
  assert.equal(out.settled, false, "it claimed a verdict it never got");
  assert.equal(out.ok, false);
  assert.match(out.words, /did not come up in time/, out.words);
  assert.ok(WATCH_LIMIT_MS > 90000, "the app must outlast the PC's own 90 s");
  assert.equal(WATCH_BEAT_MS, 2000);
});

await check("CONTROL: it asks, watches, and asks again - never once and done", async () => {
  const order = [];
  const pc = {
    ask: async () => { order.push("ask"); return lane({ state: "starting", changed: true }); },
    read: async () => { order.push("read"); return lane({ state: "up", can_start: false }); },
  };
  await startUntilSettled(pc.ask, pc.read, noWait);
  assert.deepEqual(order, ["ask", "read"], order);
});

/* ── 3. The DOM half, and both windows ──────────────────────────────────── */

function fakePage(ids) {
  const nodes = new Map();
  for (const id of ids) nodes.set(id, { id, textContent: "", hidden: false, disabled: false, onclick: null });
  return {
    getElementById: (id) => nodes.get(id) || null,
    at: (id) => nodes.get(id),
  };
}

const ROW_IDS = ["model-warn", "model-warn-start", "model-warn-start-note"];

await check("the button is drawn on a down lane and gone on an up one", async () => {
  const doc = fakePage(ROW_IDS);
  const pressed = [];
  assert.equal(paintStartButton(doc, lane(), () => pressed.push(1)), true);
  assert.equal(doc.at("model-warn-start").hidden, false);
  assert.equal(doc.at("model-warn-start").textContent, START_WORDS);
  assert.equal(doc.at("model-warn-start").disabled, false);
  assert.equal(typeof doc.at("model-warn-start").onclick, "function");
  // A second paint with the lane up clears it, and leaves no press behind.
  assert.equal(paintStartButton(doc, lane({ state: "up", can_start: false }), () => pressed.push(1)), false);
  assert.equal(doc.at("model-warn-start").hidden, true);
  assert.equal(doc.at("model-warn-start").onclick, null, "a cleared button kept its handler");
});

await check("CONTROL: a page without the button is not an error", async () => {
  const old = fakePage(["model-warn"]);
  assert.equal(paintStartButton(old, lane(), null), false);
  assert.equal(paintStartButton({ getElementById: () => null }, lane(), null), false);
});

await check("the bar draws it, and the widget draws it, from the one file", async () => {
  const bar = read("src/index.html");
  const barJs = read("src/main.js");
  const widget = read("src/widget.html");
  const widgetJs = read("src/widget.js");
  // Each window's own ids. The bar's row is the chat's own notice
  // (`model-warn`); the widget's is its compact model row - both carry the one
  // button, and both are drawn by the same `paintStartButton`.
  for (const id of ["model-warn-start", "model-warn-start-note"]) {
    assert.ok(bar.includes(`id="${id}"`), `the bar has no #${id}`);
  }
  for (const id of ["widget-model-start", "widget-model-start-note"]) {
    assert.ok(widget.includes(`id="${id}"`), `the widget has no #${id}`);
  }
  for (const [name, js] of [["the bar", barJs], ["the widget", widgetJs]]) {
    assert.ok(js.includes('from "./lane-start.js"'), `${name} does not import the action`);
    assert.ok(js.includes("startUntilSettled("), `${name} does not watch a start`);
    assert.ok(js.includes('"start_model_lane"'), `${name} never asks the PC to start it`);
    assert.ok(js.includes("read_model_lane"), `${name} never reads the lane's state`);
    assert.ok(js.includes("paintStartButton("), `${name} never draws the button`);
  }
  // Nothing anywhere builds a command line of its own: the PC runs its task.
  // Comments are stripped first, so the DOCUMENTATION saying "never `ollama
  // serve`" is not mistaken for code that runs it - the same reading
  // `lane-warning.mjs` uses for its own control.
  const strip = (text) => text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  for (const [name, js] of [["the bar", barJs], ["the widget", widgetJs], ["the action", read("src/lane-start.js")]]) {
    const code = strip(js);
    for (const verb of ["ollama serve", "Start-ScheduledTask", "schtasks"]) {
      assert.ok(!code.includes(verb),
        `${name} builds a command line of its own: ${verb}`);
    }
  }
});

await check("CONTROL: lane-warning.js still acts on nothing", async () => {
  // The rule module was pinned as one with no verb for starting anything. This
  // work moves the action into a SECOND file rather than weakening that check,
  // so the check still holds - and this is what notices if it ever stops.
  const code = read("src/lane-warning.js")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  for (const verb of ["fetch(", "invoke(", "spawn", "restart", "POST", "exec("]) {
    assert.ok(!code.includes(verb), `lane-warning.js acts on the world: ${verb}`);
  }
  // And the action file is where the acting lives.
  const action = read("src/lane-start.js");
  assert.ok(action.includes("startUntilSettled"), "the action file has no loop");
});

await check("the Rust side asks the backend, and never starts anything itself", async () => {
  const rust = read("src-tauri/src/commands.rs");
  const call = rust.slice(
    rust.indexOf("pub async fn start_model_lane"),
    rust.indexOf("pub(crate) fn summarise_health"),
  );
  assert.ok(call.includes("/api/model-lanes/start"), "the command calls another route");
  assert.ok(call.includes("start_model_lane"), "the command is missing");
  assert.ok(!call.includes("Command::new"), "Rust starts a process of its own");
  assert.ok(!call.includes("schtasks"), "Rust runs schtasks itself instead of the PC's task");
  // And the shape of the promise: a 202 is returned as the PC's own words, not
  // as a claim that the lane is up.
  assert.ok(call.includes("is_success"), "the command does not read the status");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nThe lane that is down can be started");
