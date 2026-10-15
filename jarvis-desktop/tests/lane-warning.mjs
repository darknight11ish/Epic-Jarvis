/**
 * A dead model lane says so, standing, in both desktop windows.
 *
 * The defect, measured on the owner's PC on 2026-10-13: his Jarvis talks to an
 * Ollama lane on another port (`OLLAMA_URL=http://127.0.0.1:11436` in his
 * environment). Both lanes were dead from about 16:30 until about 21:5x, and
 * nothing said so - the scheduled tasks still reported "last run 09:11, result
 * 0", and both apps looked normally connected. Jarvis only admitted it when he
 * asked a question, with the chat error `model_not_running`. The backend's own
 * `GET /api/status` carried `"ollama": false` the whole time
 * (`jarvis_hud.py`, `_reachable(OLLAMA_URL + "/api/tags")`).
 *
 * What this holds, in the order it matters:
 *
 * 1. **Only the PC's own `false` is a dead lane.** `true` and "the PC did not
 *    say" both draw nothing. A warning that appears whenever a read fails is
 *    one the owner learns to ignore - which is how five hours happened in the
 *    first place.
 * 2. **It is not "Jarvis isn't connected".** The PC answering with its model
 *    down and the PC not answering at all are different facts, and the second
 *    already has its own words (`face-words.js` OFFLINE_WORDS).
 * 3. **Both windows draw it, from one file** - the HUD window and the widget -
 *    and both ask again on a beat, because a lane dying publishes no event.
 * 4. **CONTROLs**: the words are calm, nothing acts, and the wrong-port probe
 *    is really gone (the app must judge the lane where the chat does).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  HEALTH_BEAT_MS,
  hostWords,
  laneWarning,
  LANE_DOWN_FIX,
  LANE_DOWN_WORDS,
  paintLaneWarning,
  startHealthBeat,
} from "../src/lane-warning.js";
import { OFFLINE_WORDS } from "../src/face-words.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── 1. The rule ────────────────────────────────────────────────────────── */

await check("the PC saying its model is not running draws the line", async () => {
  const warn = laneWarning(false);
  assert.equal(warn.down, true);
  assert.equal(warn.words, LANE_DOWN_WORDS);
  assert.equal(warn.fix, LANE_DOWN_FIX);
});

await check("CONTROL: up, and not-said, both draw nothing", async () => {
  for (const said of [true, null, undefined]) {
    const warn = laneWarning(said);
    assert.equal(warn.down, false, `ollama=${said} drew a warning`);
    assert.equal(warn.words, "");
    assert.equal(warn.fix, "");
  }
});

/* ── 2. Its own state, not the link's ───────────────────────────────────── */

await check("it never says the link's words - the PC is answering here", async () => {
  assert.notEqual(LANE_DOWN_WORDS, OFFLINE_WORDS);
  assert.ok(!LANE_DOWN_WORDS.includes("connected"),
    `the model line borrowed the link's word: "${LANE_DOWN_WORDS}"`);
  assert.ok(!LANE_DOWN_FIX.includes("isn't connected"), LANE_DOWN_FIX);
  // And the two host lines are about the host, so the owner can tell which of
  // the two things is actually wrong.
  assert.match(hostWords(true), /PC is answering/);
  assert.match(hostWords(false), /not answering/);
  assert.equal(hostWords(null), "", "an unknown host state must not be spoken as a fact");
});

await check("CONTROL: calm, plain, and nothing acts", async () => {
  assert.ok(!LANE_DOWN_WORDS.includes("!"), "no alarm");
  assert.ok(!LANE_DOWN_FIX.includes("!"), "no alarm");
  // It says which program to open, once, in brackets - and the plain phrase
  // comes first, because the owner is learning.
  assert.ok(LANE_DOWN_WORDS.indexOf("local model") < LANE_DOWN_WORDS.indexOf("PC") + 99);
  assert.match(LANE_DOWN_FIX, /Ollama/);
  assert.match(LANE_DOWN_FIX, /ollama serve/);
  // The rule module has no verb for starting or changing anything: no fetch,
  // no invoke, no process. If a "start the lane for me" ever appears it will
  // be the owner's decision, and this is the check that will notice. Read with
  // the comments stripped, so prose about restarting is not mistaken for code
  // that does it.
  const code = read("src/lane-warning.js")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  for (const verb of ["fetch(", "invoke(", "spawn", "restart", "POST", "exec("]) {
    assert.ok(!code.includes(verb), `lane-warning.js acts on the world: ${verb}`);
  }
});

/* ── 3. The DOM half ────────────────────────────────────────────────────── */

/** A page with the four ids `paintLaneWarning` names, and nothing else. */
function fakePage() {
  const nodes = new Map();
  const node = (id) => ({ id, textContent: "", hidden: false });
  for (const id of ["model-warn", "model-warn-text", "model-warn-fix", "model-warn-host"]) {
    nodes.set(id, node(id));
  }
  return {
    getElementById: (id) => nodes.get(id) || null,
    at: (id) => nodes.get(id),
  };
}

await check("a down lane fills the line in, and it is visible", async () => {
  const doc = fakePage();
  const drawn = paintLaneWarning(doc, false, true);
  assert.equal(drawn, true);
  assert.equal(doc.at("model-warn").hidden, false, "the line is hidden on a down lane");
  assert.equal(doc.at("model-warn-text").textContent, LANE_DOWN_WORDS);
  assert.equal(doc.at("model-warn-fix").textContent, LANE_DOWN_FIX);
  assert.equal(doc.at("model-warn-host").textContent, hostWords(true));
  assert.equal(doc.at("model-warn-host").hidden, false);
});

await check("a lane that comes back clears itself, with no mark left", async () => {
  const doc = fakePage();
  paintLaneWarning(doc, false, true);
  const drawn = paintLaneWarning(doc, true, true);
  assert.equal(drawn, false);
  assert.equal(doc.at("model-warn").hidden, true, "the line was left standing after the lane returned");
  assert.equal(doc.at("model-warn-text").textContent, "");
  assert.equal(doc.at("model-warn-fix").textContent, "");
  assert.equal(doc.at("model-warn-host").hidden, true);
});

await check("CONTROL: a page that has not said leaves the line alone", async () => {
  const doc = fakePage();
  // The one that matters: a read that did not land, or an older backend. The
  // page must not draw a warning out of an absent field.
  assert.equal(paintLaneWarning(doc, null, null), false);
  assert.equal(doc.at("model-warn").hidden, true);
  assert.equal(paintLaneWarning(doc, undefined, false), false);
  assert.equal(doc.at("model-warn").hidden, true);
});

await check("CONTROL: a window without the row is not an error", async () => {
  // The old HUD page, or a page that simply does not carry it.
  assert.equal(paintLaneWarning(fakePageWithoutRow(), false, true), false);
});

function fakePageWithoutRow() {
  return { getElementById: () => null };
}

/* ── 4. The beat ────────────────────────────────────────────────────────── */

await check("the beat waits its interval, twice over, and stops", async () => {
  const waits = [];
  let probes = 0;
  let armed = null;
  const stop = startHealthBeat(async () => { probes += 1; }, {
    doc: { hidden: false },
    schedule: (fn, ms) => { waits.push(ms); armed = fn; return waits.length; },
    cancel: () => { armed = null; },
  });
  assert.equal(waits.length, 1, "the beat did not arm itself");
  assert.equal(waits[0], HEALTH_BEAT_MS);
  // It must not be a beat that a simulated idle minute can see: timers.mjs
  // counts wake-ups in exactly that window, and the cohesion audit emptied it.
  assert.ok(HEALTH_BEAT_MS > 60_000, `a ${HEALTH_BEAT_MS} ms beat is back inside the idle minute`);
  await armed();
  assert.equal(probes, 1);
  assert.equal(waits[1], HEALTH_BEAT_MS, "the second wait changed");
  await armed();
  assert.equal(probes, 2);
  stop();
  assert.equal(armed, null);
  const before = probes;
  await (async () => {})();
  assert.equal(probes, before);
});

await check("a hidden window does no work, and still wakes up", async () => {
  const waits = [];
  let probes = 0;
  let armed = null;
  startHealthBeat(async () => { probes += 1; }, {
    doc: { hidden: true },
    schedule: (fn, ms) => { waits.push(ms); armed = fn; return waits.length; },
    cancel: () => {},
  });
  await armed();
  assert.equal(probes, 0, "a hidden window probed the PC");
  assert.equal(waits.length, 2, "a hidden window stopped re-arming and could never notice being shown");
});

await check("a probe that throws does not stop the beat", async () => {
  const waits = [];
  let armed = null;
  startHealthBeat(async () => { throw new Error("the PC went away mid-probe"); }, {
    doc: { hidden: false },
    schedule: (fn, ms) => { waits.push(ms); armed = fn; return waits.length; },
    cancel: () => {},
  });
  await assert.rejects(() => armed());
  assert.equal(waits.length, 2, "one failed probe ended the beat for the session");
});

/* ── 5. Both windows, and the one source of truth ───────────────────────── */

await check("the HUD window draws it, from the shared file", async () => {
  const hud = read("src/jarvis_hud.html");
  for (const id of ["model-warn", "model-warn-text", "model-warn-fix", "model-warn-host"]) {
    assert.ok(hud.includes(`id="${id}"`), `the HUD window has no #${id}`);
  }
  assert.ok(hud.includes('from "./lane-warning.js"'),
    "the HUD window does not import the shared rule");
  // It re-reads `/api/status` on the page's own beat rather than once at boot:
  // that one read was the whole bug.
  assert.ok(hud.includes("async function paintHost()"), "the HUD never re-reads the PC's verdict");
  assert.match(hud, /paintHost\(\);\s*\n\s*let data;/,
    "the HUD's 30 s beat does not carry the model read");
});

await check("the widget draws it, from the shared file", async () => {
  const widget = read("src/widget.html");
  const js = read("src/widget.js");
  for (const id of ["widget-model", "widget-model-text", "widget-model-fix"]) {
    assert.ok(widget.includes(`id="${id}"`), `the widget has no #${id}`);
  }
  assert.ok(js.includes('from "./lane-warning.js"'), "the widget does not import the shared rule");
  assert.ok(js.includes("startHealthBeat("), "the widget still probes only at boot");
  // Its own row, never the offline row's: that one is the link's.
  assert.ok(widget.indexOf('id="widget-offline"') < widget.indexOf('id="widget-model"'),
    "the widget's model row is not its own element");
});

await check("the Jarvis bar draws it too, and clears it", async () => {
  const bar = read("src/index.html");
  const js = read("src/main.js");
  assert.ok(bar.includes('id="model-warn"'), "the bar has no model line");
  assert.ok(js.includes("paintLaneWarning("), "the bar never draws the model line");
  assert.ok(js.includes('from "./lane-warning.js"'), "the bar does not import the shared rule");
  assert.ok(js.includes("startHealthBeat("), "the bar only ever probes on an event");
});

/* ── 6. The wrong port ──────────────────────────────────────────────────── */

await check("the app judges the lane where the chat does, not on 11434", async () => {
  const commands = read("src-tauri/src/commands.rs");
  // The health check must not probe OLLAMA_URL itself any more: that is 11434,
  // while the owner's everyday lane is 11436. The backend asks the address the
  // chat uses, so its own `/api/status` is the only honest source.
  const health = commands.slice(
    commands.indexOf("pub async fn check_server_health"),
    commands.indexOf("fn ollama_status"),
  );
  assert.ok(!health.includes("OLLAMA_URL/api/tags"),
    "the health check is still probing the wrong port directly");
  assert.ok(health.includes('body.get("ollama")'),
    "the health check does not read the backend's own ollama field");
  // And the row it builds says where it came from, rather than printing an
  // address this shell never asked.
  const row = commands.slice(commands.indexOf("fn ollama_status"));
  assert.ok(!row.slice(0, 2000).includes("11434"), "the model row still names the wrong port");
  assert.ok(row.includes('Some(false) =>'), "the model row has no false case");
  assert.ok(row.includes('None =>'), "the model row has no unknown case");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nA dead lane says so");
