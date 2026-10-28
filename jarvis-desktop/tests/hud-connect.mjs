/**
 * The owner's ask of 2026-10-28, in his own words:
 *
 *   "when jarvis gets opened on the desktop from scratch, there should be a
 *    connect button next to these notifications saying its offline."
 *
 * WHAT THIS PROVES, and why each check is here:
 *
 *   1. THE BUTTON IS BESIDE EACH OFFLINE LINE. The HUD says "a model is
 *      missing" in two places - the standing #model-warn row (`lane-warning.js`
 *      fills it: "The local model isn't running on your PC." + "Open Ollama on
 *      the PC, or run ollama serve there.") and #banner ("Model not running.
 *      The HUD server is answering; the local model is not."). Each carries its
 *      own button, inside its own line, after the words.
 *   2. IT IS REACHABLE BY KEYBOARD. Both are real `<button type="button">`
 *      elements - Enter and Space press them - and neither is taken out of the
 *      tab order. A div with an onclick would pass a source grep and fail the
 *      owner.
 *   3. IT CALLS THE REAL ACTION, AND ONLY WHEN THE PC SAYS SO. The block is
 *      lifted out of the page and driven with a fake document and a fake
 *      bridge: hidden when the PC has not said, hidden when the lane answers,
 *      "Starting…" and disabled mid-press, "Start the local model" only when
 *      the PC says `can_start`, and the PC's own sentence when it says a press
 *      could not do anything.
 *   4. STARTING IS NOT ARRIVING. The press asks once, reads on a short beat,
 *      and only `state: "up"` resolves as success. A refusal resolves at once.
 *      These are the SAME fake scenarios `lane-start.js`'s `startUntilSettled`
 *      is run through at the bottom, and the two must agree - the page cannot
 *      import that module (the browser copy is dressed by a backend whitelist
 *      this repository does not own), so it carries the same loop, and this is
 *      the check that keeps the two from drifting apart unannounced.
 *   5. THE GRANT IS THE NARROW ONE. `hud.json` holds `hud-lane`, and that set
 *      is exactly `allow-read-model-lane` + `allow-start-model-lane` - never
 *      the automatic-restart switch, and no new route: the same two commands
 *      the Jarvis bar sends. The page's own POST stays refused by the shell's
 *      fetch shim, so the grant is the only way the action leaves that page.
 *   6. THE THREE COPIES ARE ONE FILE. `jarvis_hud.html` lives in three places
 *      (the desktop page and the two backend copies) and is byte-identical in
 *      all three; a fix that lands in one would silently miss the live HUD.
 *
 * Browser-free on purpose: no Playwright, no server, no PC. The page is read as
 * text and the one block this concerns is lifted exactly as it is written.
 *
 *     node tests/hud-connect.mjs
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  START_WORDS, STARTING_WORDS, CANNOT_START_WORDS, startUntilSettled,
} from "../src/lane-start.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const DESKTOP = join(HERE, "..");
const REPO = join(DESKTOP, "..");
const SRC = join(DESKTOP, "src");
const TAURI = join(DESKTOP, "src-tauri");
const read = (p) => readFileSync(p, "utf8");

const HUD = read(join(SRC, "jarvis_hud.html"));
const START_MARK = "/* == hud-lane-connect start ==";
const END_MARK = "/* == hud-lane-connect end == */";

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── the block, lifted exactly as the page writes it ─────────────────────── */

function laneBlock() {
  const at = HUD.indexOf(START_MARK);
  const end = HUD.indexOf(END_MARK);
  assert.ok(at > 0 && end > at, "the hud-lane-connect block is missing from the page");
  const body = HUD.slice(HUD.indexOf("\n", at) + 1, end);
  return new Function(`${body}
    return { LANE_START_WORDS, LANE_STARTING_WORDS, LANE_CANNOT_START_WORDS,
             LANE_WATCH_BEAT_MS, LANE_WATCH_LIMIT_MS,
             laneIsUp, laneButtonView, laneCountdownWords, laneRefusalWords,
             paintLaneConnect, hudLanePress };`)();
}
const L = laneBlock();

/* ── a fake document: just the elements the paint function reads ─────────── */

function fakeDoc(ids) {
  const nodes = new Map();
  for (const id of ids) {
    nodes.set(id, {
      id, textContent: "", hidden: true, disabled: false, onclick: null,
      attrs: {},
      setAttribute(name, value) { this.attrs[name] = String(value); },
      getAttribute(name) { return this.attrs[name]; },
    });
  }
  return { ids: [...nodes.keys()], at: (id) => nodes.get(id), getElementById: (id) => nodes.get(id) || null };
}
const ROW_IDS = ["model-warn-start", "model-warn-start-note"];
const BANNER_IDS = ["banner-connect", "banner-connect-note"];

/* ── 1. beside each offline line, in that line's own markup ──────────────── */

await check("the standing row carries its button and its note, inside itself", async () => {
  const start = HUD.indexOf('<div id="model-warn"');
  const end = HUD.indexOf("</div>", start);
  const markup = HUD.slice(start, end);
  assert.match(markup, /<button id="model-warn-start" class="lane-start" type="button"/,
    "the standing line has no button");
  assert.match(markup, /<span id="model-warn-start-note"[^>]*role="status"/,
    "the standing line has no note for a refusal");
  assert.ok(markup.indexOf('id="model-warn-fix"') < markup.indexOf('id="model-warn-start"'),
    "the button must come after the words it sits beside");
});

await check("the banner carries its own button, inside itself", async () => {
  const start = HUD.indexOf('<div id="banner"');
  const end = HUD.indexOf("</div>", start);
  const markup = HUD.slice(start, end);
  assert.match(markup, /<button id="banner-connect" class="lane-start" type="button"/,
    "the offline banner has no connect button");
  assert.match(markup, /<span id="banner-connect-note"[^>]*role="status"/,
    "the banner has no note for a refusal");
  assert.ok(markup.indexOf('id="banner-text"') < markup.indexOf('id="banner-connect"'),
    "the button must come after the words it sits beside");
});

await check("both are real buttons, in the tab order (not divs, not tabindex=-1)", async () => {
  for (const id of ["model-warn-start", "banner-connect"]) {
    const at = HUD.indexOf(`id="${id}"`);
    const open = HUD.lastIndexOf("<button", at);
    assert.ok(open > 0 && at - open < 40,
      `${id} is not a <button> (its opening tag is ${JSON.stringify(HUD.slice(open, at))})`);
    assert.doesNotMatch(HUD, new RegExp(`id="${id}"[^>]*tabindex`),
      `${id} is taken out of the tab order`);
    assert.doesNotMatch(HUD, new RegExp(`id="${id}"[^>]*aria-hidden`),
      `${id} is hidden from a screen reader`);
  }
});

await check("the page says a button is there before it is painted", async () => {
  // `hidden` in the markup, so a page whose script never runs draws no control
  // that would do nothing.
  assert.match(HUD, /id="model-warn-start"[^>]*hidden/);
  assert.match(HUD, /id="banner-connect"[^>]*hidden/);
});

/* ── 2. the words are the bar's words ────────────────────────────────────── */

await check("the button's words are lane-start.js's, not a second vocabulary", async () => {
  assert.equal(L.LANE_START_WORDS, START_WORDS);
  assert.equal(L.LANE_STARTING_WORDS, STARTING_WORDS);
  assert.equal(L.LANE_CANNOT_START_WORDS, CANNOT_START_WORDS);
  assert.equal(L.LANE_WATCH_BEAT_MS, 2000);
  assert.equal(L.LANE_WATCH_LIMIT_MS, 100000);
});

/* ── 3. what it says for each of the PC's own readings ───────────────────── */

await check("nothing is drawn from a reading the PC did not give", async () => {
  const v = L.laneButtonView(null);
  assert.deepEqual([v.show, v.disabled, v.words, v.note], [false, true, "", ""]);
  assert.equal(L.laneIsUp(null), false);
  assert.equal(L.laneIsUp({ state: "starting" }), false, "starting is not arriving");
});

await check("a lane that answers shows no button at all", async () => {
  const v = L.laneButtonView({ state: "up", can_start: false });
  assert.equal(v.show, false);
  assert.equal(v.words, "");
});

await check("a lane the PC can start shows the one action, enabled", async () => {
  const v = L.laneButtonView({ state: "down", can_start: true });
  assert.deepEqual([v.show, v.disabled, v.words, v.note],
    [true, false, START_WORDS, ""]);
});

await check("mid-press it says Starting… and cannot be pressed again", async () => {
  const v = L.laneButtonView({ state: "starting", elapsed_s: 4 });
  assert.deepEqual([v.show, v.disabled, v.words], [true, true, STARTING_WORDS]);
  assert.match(v.note, /4 seconds/, v.note);
  assert.match(L.laneCountdownWords({ state: "starting" }), /up to a minute/);
});

await check("a PC that cannot start it gives its reason instead of a button", async () => {
  const v = L.laneButtonView({ state: "down", can_start: false,
    message: "This PC has no Jarvis Ollama task for that lane." });
  assert.deepEqual([v.show, v.disabled], [false, true]);
  assert.equal(v.note, "This PC has no Jarvis Ollama task for that lane.");
});

/* ── 4. painting both surfaces ───────────────────────────────────────────── */

await check("the standing row's button is painted, pressed and cleared", async () => {
  const doc = fakeDoc([...ROW_IDS, ...BANNER_IDS]);
  const pressed = [];
  assert.equal(L.paintLaneConnect(doc, { state: "down", can_start: true },
    () => pressed.push(1), { banner: false }), true);
  assert.equal(doc.at("model-warn-start").hidden, false);
  assert.equal(doc.at("model-warn-start").textContent, START_WORDS);
  assert.equal(doc.at("model-warn-start").disabled, false);
  assert.equal(typeof doc.at("model-warn-start").onclick, "function");
  doc.at("model-warn-start").onclick();
  assert.deepEqual(pressed, [1]);
  // … and cleared, with the handler taken away.
  assert.equal(L.paintLaneConnect(doc, { state: "up" }, () => pressed.push(2),
    { banner: false }), false);
  assert.equal(doc.at("model-warn-start").hidden, true);
  assert.equal(doc.at("model-warn-start").onclick, null, "a cleared button kept its handler");
});

await check("the banner's button is only drawn while that banner is up", async () => {
  const doc = fakeDoc([...ROW_IDS, ...BANNER_IDS]);
  L.paintLaneConnect(doc, { state: "down", can_start: true }, () => {}, { banner: false });
  assert.equal(doc.at("banner-connect").hidden, true,
    "a page with no server to ask still offered to start a lane");
  L.paintLaneConnect(doc, { state: "down", can_start: true }, () => {}, { banner: true });
  assert.equal(doc.at("banner-connect").hidden, false);
  assert.equal(doc.at("banner-connect").textContent, START_WORDS);
  assert.equal(typeof doc.at("banner-connect").onclick, "function");
});

await check("a page without the elements (an older copy) is not a crash", async () => {
  assert.equal(L.paintLaneConnect({ getElementById: () => null },
    { state: "down", can_start: true }, () => {}, { banner: true }), false);
});

/* ── 5. the press: ask, then watch until it settles ──────────────────────── */

const laneScript = (reads) => {
  let i = 0;
  return {
    ask: async () => ({ state: "starting", can_start: false }),
    read: async () => reads[Math.min(i++, reads.length - 1)],
    wait: async () => {},
    now: () => 0,
    limitMs: 100000,
    beatMs: 1,
  };
};

await check("a press that comes back already up resolves at once, with no reads", async () => {
  let reads = 0;
  const out = await L.hudLanePress({
    ask: async () => ({ state: "up" }),
    read: async () => { reads++; return { state: "up" }; },
    wait: async () => {}, now: () => 0,
  });
  assert.deepEqual([out.ok, out.settled, reads], [true, true, 0]);
});

await check("starting is not arriving: the line clears only when the lane answers", async () => {
  const out = await L.hudLanePress(laneScript([
    { state: "starting", elapsed_s: 2 },
    { state: "starting", elapsed_s: 4 },
    { state: "up" },
  ]));
  assert.deepEqual([out.ok, out.settled, out.lane.state], [true, true, "up"]);
});

await check("a refusal is shown in the PC's words and nothing is retried", async () => {
  let reads = 0;
  const out = await L.hudLanePress({
    ask: async () => ({ ok: false, error: "This PC has no such task." }),
    read: async () => { reads++; return { state: "up" }; },
    wait: async () => {}, now: () => 0,
  });
  assert.deepEqual([out.ok, out.refused, out.settled, reads], [false, true, true, 0]);
  assert.equal(out.words, "This PC has no such task.");
});

await check("a press the bridge could not send says so and leaves the warning standing", async () => {
  const out = await L.hudLanePress({
    ask: async () => { throw new Error("the PC did not answer"); },
    read: async () => ({ state: "up" }), wait: async () => {}, now: () => 0,
  });
  assert.deepEqual([out.ok, out.refused], [false, true]);
  assert.match(out.words, /the PC did not answer/);
});

await check("the PC's verdict that it did not come up is the sentence shown", async () => {
  const out = await L.hudLanePress(laneScript([
    { state: "down", can_start: false, message: "It did not come up in ninety seconds." },
  ]));
  assert.deepEqual([out.ok, out.settled], [false, true]);
  assert.equal(out.words, "It did not come up in ninety seconds.");
});

await check("this page stops asking at its own limit, and says it did not come up", async () => {
  let now = 0;
  const out = await L.hudLanePress({
    ask: async () => ({ state: "starting" }),
    read: async () => ({ state: "starting" }),
    wait: async () => { now += 2000; },
    now: () => now,
    beatMs: 2000, limitMs: 10000,
  });
  assert.deepEqual([out.ok, out.settled], [false, false]);
  assert.match(out.words, /did not come up in time/);
});

/* ── 6. and the bar's own loop agrees, scenario for scenario ─────────────── */

await check("the HUD's loop and lane-start.js's resolve the same way, every time", async () => {
  const scenarios = [
    { name: "already up", reads: [], first: { state: "up" } },
    { name: "starting then up", reads: [{ state: "starting" }, { state: "up" }] },
    { name: "verdict: did not come up",
      reads: [{ state: "down", can_start: false, message: "no" }] },
    { name: "still starting at the limit", reads: [{ state: "starting" }], limit: 6000 },
  ];
  for (const s of scenarios) {
    const fakeAs = () => {
      let i = 0;
      return {
        ask: async () => s.first || { state: "starting" },
        read: async () => s.reads[Math.min(i++, Math.max(0, s.reads.length - 1))] || s.first,
        wait: async () => {},
        now: (() => { let n = 0; return () => { const v = n; n += s.limit ? 3000 : 0; return v; }; })(),
        limitMs: s.limit || 100000,
        beatMs: 1,
      };
    };
    const a = await L.hudLanePress(fakeAs());
    const b = await startUntilSettled(fakeAs().ask, fakeAs().read, fakeAs());
    assert.deepEqual([a.ok, a.settled, a.refused, a.words],
      [b.ok, b.settled, b.refused, b.words],
      `the two loops disagree on "${s.name}"`);
  }
});

/* ── 6b. what the browser probe found, pinned ────────────────────────────── */

await check("the button follows the LANE's reading, not the live stream's", async () => {
  // The first version of this wiring hid the button while `linkStatus.up` was
  // false - which means the SHELL'S EVENT STREAM dropped, not that the PC
  // cannot be asked. Driving the real page in a browser found it: both offline
  // lines were drawn and neither had a button. The bridge read goes over its
  // own road, so the lane's own reading is what decides.
  const at = HUD.indexOf("function paintLaneConnectNow(");
  assert.ok(at > 0, "paintLaneConnectNow is gone");
  const body = HUD.slice(at, HUD.indexOf("\n}", at));
  // The code, not its comment: the comment above the fix names the thing it
  // stopped doing, and a grep that could not tell code from prose would fail on
  // its own explanation.
  const code = body.split("\n").map((line) => line.replace(/\/\/.*$/, "")).join("\n");
  assert.doesNotMatch(code, /linkStatus\.up/,
    "the button is gated on the live link again: a reconnecting stream would take it away " +
    "while the PC can still be asked");
  assert.match(body, /const lane = lanePressing/);
});

/* ── 7. the grant, and the shell's own gate ──────────────────────────────── */

await check("the HUD holds the narrow lane grant, and not the auto switch", async () => {
  const cap = JSON.parse(read(join(TAURI, "capabilities", "hud.json")));
  assert.ok(cap.permissions.includes("hud-lane"), "hud.json does not grant hud-lane");
  assert.ok(!cap.permissions.includes("model-lane"),
    "the wide model-lane set (with the automatic switch) must NOT be granted to the HUD");
  const toml = read(join(TAURI, "permissions", "surfaces.toml"));
  const set = toml.slice(toml.indexOf('identifier = "hud-lane"'));
  const ends = set.indexOf("]]");
  const body = set.slice(0, ends < 0 ? set.length : ends);
  assert.ok(body.includes('"allow-read-model-lane"'));
  assert.ok(body.includes('"allow-start-model-lane"'));
  assert.ok(!body.includes("allow-set-model-lane-auto"),
    "the automatic-restart switch is not this page's to press");
});

await check("the page asks for exactly those two commands, by name", async () => {
  assert.ok(HUD.includes('core.invoke("read_model_lane")'),
    "the page never reads the lane through Rust");
  assert.ok(HUD.includes('core.invoke("start_model_lane")'),
    "the page never sends the bar's own start command");
  assert.ok(!/core\.invoke\("set_model_lane_auto"/.test(HUD),
    "the HUD calls the automatic-restart switch, which it is not granted");
});

await check("the shell's fetch shim still refuses the page's own POST", async () => {
  const boot = read(join(TAURI, "src", "hud_bootstrap.js"));
  // The shim hands GETs to hud_get and POST /api/chat to hud_chat; anything
  // else is refused. `/api/model-lanes/start` is not one of the two, so the
  // grant above is the ONLY way the action leaves this page.
  assert.ok(!boot.includes("/api/model-lanes"),
    "the fetch shim now carries the lane route: the grant is no longer the only path");
  assert.match(boot, /the HUD window cannot send that/);
});

await check("the banner's words are written into their own span (the button survives)",
  async () => {
    assert.match(HUD, /\$\("banner-text"\)\.innerHTML = status/,
      "the boot read overwrites #banner's whole contents, which would delete the button");
    assert.doesNotMatch(HUD, /\$\("banner"\)\.innerHTML/);
  });

/* ── 8. three copies, one page ───────────────────────────────────────────── */

await check("the three jarvis_hud.html copies are byte-identical", async () => {
  const files = [
    join(SRC, "jarvis_hud.html"),
    join(REPO, "backend", "jarvis_hud.html"),
    join(REPO, "jarvis-backend", "jarvis_hud.html"),
  ];
  const hashes = files.map((f) => createHash("sha256").update(readFileSync(f)).digest("hex"));
  console.log(`      sha256 ${hashes[0].slice(0, 16)}  ${files.length} copies`);
  assert.equal(new Set(hashes).size, 1,
    "a HUD fix landed in one copy and not the others:\n" +
    files.map((f, i) => `      ${hashes[i].slice(0, 16)}  ${f}`).join("\n"));
});

/* ── done ────────────────────────────────────────────────────────────────── */

console.log("");
if (fails.length) {
  console.log(`${fails.length} FAILED:`);
  for (const name of fails) console.log(`  - ${name}`);
  process.exit(1);
}
console.log("all checks passed");
