/**
 * antislop-settings.mjs - "How Jarvis talks": the Anti-Slop filter card.
 *
 * Runs headless on plain Node + Playwright (tests/uikit.mjs):
 *
 *     node tests/antislop-settings.mjs
 *
 * WHY THIS EXISTS (2026-10-28, the anti-slop UI slice). Settings now draws the
 * Anti-Slop filter card: a master ON/OFF switch, three scope pills, a
 * During/After radio, the Delivery Gate switch and three Liveliness dials, all
 * on GET/POST /api/antislop. The data mapping is held pure by
 * tests/antislop.mjs; THIS file drives the real page in a headless browser with
 * a stubbed bridge and proves what a click sends:
 *
 *   - the card renders OFF by default, and says in one line that OFF costs
 *     0 prompt tokens;
 *   - while it is OFF the four ON-only blocks are hidden, so the card cannot
 *     offer a scope for a filter that is not running;
 *   - the master switch sends exactly `{change: {enabled}}`, and OFF -> ON ->
 *     OFF round-trips through the stubbed PC (the switch's state after each
 *     change is the PC's, never the click's);
 *   - each scope pill sends only its own scope, the mode radio only the mode,
 *     a dial only the three dials, the gate switch only the gate;
 *   - a refusal shows the PC's own words and springs the switch back to what
 *     the PC really holds;
 *   - a PC without the route says so and never claims "off";
 *   - the "settings" event re-reads, so a change made on the phone appears
 *     here without a reload.
 *
 * NOT proven here: the real Tauri bridge, a real backend's answers, that the
 * POST bodies above become the JSON the PC receives (src-tauri/src/antislop.rs
 * has nine unit tests for exactly that, run by `cargo test`), or how any of it
 * looks on screen.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const A = await import("../src/antislop.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** The PC's own answer, as jarvis_antislop.get_state() sends it, OFF. */
function pcState(over = {}) {
  return {
    enabled: false,
    mode: "during",
    scopes: { copy: true, code: true, ui: true },
    dials: { energy: 1, rhythm: 2, motion: 1 },
    show_delivery_gate_on_ui_tasks: true,
    updated_at: 1793164200.0,
    ...over,
  };
}

/**
 * Stub the two commands the card uses and record every call. The stub behaves
 * like the PC: it changes the state it was told to change, and sends the whole
 * state back, so a test can see the page paint the PC's answer rather than its
 * own optimism.
 */
function bridge(scenario) {
  const core = window.__TAURI__.core;
  const inner = core.invoke;
  window.__a = {
    state: scenario.state,
    calls: [],
    reads: 0,
    // What set_antislop answers. `null` = behave like the PC: change the state
    // and answer ok. A string = refuse with that sentence. "unreadable" = a
    // 2xx the page cannot read.
    refuse: scenario.refuse || null,
    failRead: scenario.failRead || null,
  };
  core.invoke = async (cmd, args) => {
    if (cmd === "get_antislop") {
      window.__a.reads += 1;
      if (window.__a.failRead) throw new Error(window.__a.failRead);
      return JSON.parse(JSON.stringify(window.__a.state));
    }
    if (cmd === "set_antislop") {
      window.__a.calls.push({ cmd, args });
      const said = window.__a.refuse;
      if (said) return { ok: false, error: said, enabled: window.__a.state.enabled };
      const c = (args && args.change) || {};
      const s = window.__a.state;
      if (c.enabled !== undefined) s.enabled = c.enabled;
      if (c.mode !== undefined) s.mode = c.mode;
      if (c.scope !== undefined) s.scopes = { ...s.scopes, [c.scope]: c.on };
      if (c.dials !== undefined) s.dials = c.dials;
      if (c.gate !== undefined) s.show_delivery_gate_on_ui_tasks = c.gate;
      return { ok: true, said: "PC said it.", ...JSON.parse(JSON.stringify(s)) };
    }
    return inner(cmd, args);
  };
}

const { base, close } = await K.serve();
const browser = await K.launch();

async function pageFor(scenario) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 1200, height: 2400 });
  await page.addInitScript(bridge, scenario);
  await page.reload();
  // The card is one of many on this page. Wait on the observable condition -
  // the markup is attached AND the card's own read has answered - rather than
  // on a fixed sleep, which is what tests/README.md asks for and what a busy CI
  // runner needs.
  await page.waitForSelector("#asf-enabled", { state: "attached", timeout: 30000 });
  await page.waitForFunction(() => {
    const s = document.getElementById("asf-state");
    if (!s) return false;
    return s.textContent === "" || s.dataset.tone === "bad";
  }, null, { timeout: 30000 });
  return page;
}

/* ── 1. The card renders, OFF by default, and says what OFF costs ────────── */

await check("the card renders the PC's own words and is OFF by default", async () => {
  const page = await pageFor({ state: pcState() });
  const got = await page.evaluate(() => ({
    inMannerCard: Boolean(document.getElementById("manner")?.contains(
      document.getElementById("antislop"))),
    title: document.getElementById("asf-title").textContent,
    detail: document.getElementById("asf-detail").textContent,
    offNote: document.getElementById("asf-off-note").textContent,
    checked: document.getElementById("asf-enabled").checked,
    label: document.getElementById("asf-enabled-label").textContent,
  }));
  await page.close();
  assert.equal(got.inMannerCard, true, "the card must sit in How Jarvis talks");
  assert.equal(got.title, "Anti-Slop filter");
  assert.ok(got.detail.length > 40, got.detail);
  assert.match(got.offNote, /0 prompt tokens/, "OFF must say what it costs: " + got.offNote);
  assert.match(got.offNote, /nothing is rewritten|no answer is rewritten/i);
  assert.equal(got.checked, false, "the filter ships OFF");
  assert.equal(got.label, "Anti-Slop filter");
});

await check("while it is OFF the four ON-only blocks are hidden", async () => {
  const page = await pageFor({ state: pcState() });
  const got = await page.evaluate(() => ({
    body: document.getElementById("asf-body").hidden,
    offNote: document.getElementById("asf-off-note").hidden,
    scopes: document.getElementById("asf-scopes-block").hidden,
    modes: document.getElementById("asf-modes-block").hidden,
    gate: document.getElementById("asf-gate-row").hidden,
    dials: document.getElementById("asf-dials-block").hidden,
  }));
  await page.close();
  assert.equal(got.body, false, "the switch itself is always drawn");
  assert.equal(got.offNote, false, "the 0-token line is drawn while off");
  for (const key of ["scopes", "modes", "gate", "dials"]) {
    assert.equal(got[key], true, `${key} must be hidden while the filter is off`);
  }
});

/* ── 2. The master switch: one field, and OFF -> ON -> OFF round-trips ───── */

await check("the master switch sends exactly {change: {enabled: true}}", async () => {
  const page = await pageFor({ state: pcState() });
  await page.locator("#asf-enabled").check();
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => window.__a.calls);
  await page.close();
  assert.deepEqual(got, [{ cmd: "set_antislop", args: { change: { enabled: true } } }]);
  assert.deepEqual(Object.keys(got[0].args), ["change"], "one nested change object only");
});

await check("OFF -> ON -> OFF round-trips through the PC, and the blocks follow", async () => {
  const page = await pageFor({ state: pcState() });
  await page.locator("#asf-enabled").check();
  await page.waitForTimeout(400);
  const on = await page.evaluate(() => ({
    checked: document.getElementById("asf-enabled").checked,
    scopesShown: !document.getElementById("asf-scopes-block").hidden,
    dialsShown: !document.getElementById("asf-dials-block").hidden,
    offNoteShown: !document.getElementById("asf-off-note").hidden,
    scopes: document.querySelectorAll("#asf-scopes .asf-scope").length,
  }));
  await page.locator("#asf-enabled").uncheck();
  await page.waitForTimeout(400);
  const off = await page.evaluate(() => ({
    checked: document.getElementById("asf-enabled").checked,
    scopesShown: !document.getElementById("asf-scopes-block").hidden,
    offNoteShown: !document.getElementById("asf-off-note").hidden,
    calls: window.__a.calls.map((c) => c.args.change),
  }));
  await page.close();
  assert.equal(on.checked, true);
  assert.equal(on.scopesShown, true, "ON opens the scopes");
  assert.equal(on.dialsShown, true, "ON opens the dials");
  assert.equal(on.offNoteShown, false, "the 0-token line is an OFF line");
  assert.equal(on.scopes, 3, "three scopes");
  assert.equal(off.checked, false, "OFF must leave the switch off, not mid-way");
  assert.equal(off.scopesShown, false, "OFF closes the scopes again");
  assert.equal(off.offNoteShown, true);
  assert.deepEqual(off.calls, [{ enabled: true }, { enabled: false }]);
});

/* ── 3. Each control sends its own field and nothing else ────────────────── */

await check("one scope pill sends only that scope", async () => {
  const page = await pageFor({ state: pcState({ enabled: true }) });
  await page.locator("#asf-scope-code").uncheck();
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    calls: window.__a.calls,
    copy: document.getElementById("asf-scope-copy").checked,
    code: document.getElementById("asf-scope-code").checked,
    ui: document.getElementById("asf-scope-ui").checked,
  }));
  await page.close();
  assert.deepEqual(got.calls, [
    { cmd: "set_antislop", args: { change: { scope: "code", on: false } } },
  ]);
  assert.equal(got.code, false, "the PC's answer is what is painted");
  assert.equal(got.copy, true, "the other scopes were not dragged along");
  assert.equal(got.ui, true);
});

await check("the During/After radio sends only the mode", async () => {
  const page = await pageFor({ state: pcState({ enabled: true }) });
  await page.locator('#asf-modes input[value="after"]').check();
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    calls: window.__a.calls,
    after: document.querySelector('#asf-modes input[value="after"]').checked,
    during: document.querySelector('#asf-modes input[value="during"]').checked,
  }));
  await page.close();
  assert.deepEqual(got.calls, [{ cmd: "set_antislop", args: { change: { mode: "after" } } }]);
  assert.equal(got.after, true);
  assert.equal(got.during, false, "a radio: exactly one is chosen");
});

await check("a dial pill sends all three dials with only the clicked one moved", async () => {
  const page = await pageFor({ state: pcState({ enabled: true }) });
  await page.locator('#asf-dials .asf-dial[data-dial="energy"] .mn-btn[data-value="3"]').click();
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => ({
    calls: window.__a.calls,
    pressed: [...document.querySelectorAll('#asf-dials .mn-btn[aria-pressed="true"]')]
      .map((b) => `${b.dataset.dialKey}=${b.dataset.value}`),
  }));
  await page.close();
  assert.deepEqual(got.calls, [{
    cmd: "set_antislop",
    args: { change: { dials: { energy: 3, rhythm: 2, motion: 1 } } },
  }]);
  assert.deepEqual(got.pressed, ["energy=3", "rhythm=2", "motion=1"],
    "the chosen step is a pressed state, so a screen reader can hear it");
});

await check("the Delivery Gate switch sends only the PC's own gate field", async () => {
  const page = await pageFor({ state: pcState({ enabled: true }) });
  await page.locator("#asf-gate").uncheck();
  await page.waitForTimeout(400);
  const got = await page.evaluate(() => window.__a.calls);
  await page.close();
  assert.deepEqual(got, [{ cmd: "set_antislop", args: { change: { gate: false } } }]);
});

await check("the gate switch is hidden when the UI scope is off", async () => {
  const page = await pageFor({
    state: pcState({ enabled: true, scopes: { copy: true, code: true, ui: false } }),
  });
  const got = await page.evaluate(() => ({
    gate: document.getElementById("asf-gate-row").hidden,
    scopes: document.getElementById("asf-scopes-block").hidden,
  }));
  await page.close();
  assert.equal(got.gate, true, "a gate for a scope that is not filtered is noise");
  assert.equal(got.scopes, false, "the filter is still ON, so its scopes are drawn");
});

/* ── 4. A refusal shows the PC's own words and springs back ──────────────── */

await check("a refusal shows the PC's own sentence and springs the switch back", async () => {
  const page = await pageFor({
    state: pcState(),
    refuse: "The anti-slop settings file could not be written just now.",
  });
  // `.click()`, not `.check()`: this is the one scenario where the switch is
  // SUPPOSED to spring back, and Playwright's `check()` fails a click whose
  // state does not stay changed. Proving the spring-back is the point.
  await page.locator("#asf-enabled").click();
  await page.waitForFunction(() => document.getElementById("asf-status").textContent !== "Sending…",
    null, { timeout: 15000 });
  const got = await page.evaluate(() => ({
    status: document.getElementById("asf-status").textContent,
    tone: document.getElementById("asf-status").dataset.tone,
    checked: document.getElementById("asf-enabled").checked,
  }));
  await page.close();
  assert.match(got.status, /settings file could not be written/,
    "the PC's own words, not one of the page's: " + got.status);
  assert.equal(got.tone, "bad");
  assert.equal(got.checked, false,
    "a refused ON must not leave the switch looking on");
});

await check("a failed read says so in words and draws no controls", async () => {
  const page = await pageFor({ state: pcState(), failRead: "Jarvis is not answering on this PC." });
  const got = await page.evaluate(() => ({
    state: document.getElementById("asf-state").textContent,
    tone: document.getElementById("asf-state").dataset.tone,
    body: document.getElementById("asf-body").hidden,
  }));
  await page.close();
  assert.match(got.state, /Could not read it/);
  assert.match(got.state, /not answering/, "the reason is passed on, not swallowed");
  assert.equal(got.tone, "bad");
  assert.equal(got.body, true, "nothing is offered over a state nobody read");
});

/* ── 5. An older PC says so and never claims "off" ──────────────────────── */

await check("a PC without the route says so, and never claims the filter is off", async () => {
  const page = await pageFor({ state: { available: false, why: A.MISSING } });
  const got = await page.evaluate(() => ({
    state: document.getElementById("asf-state").textContent,
    body: document.getElementById("asf-body").hidden,
  }));
  await page.close();
  assert.ok(got.state.includes("apply-patches.ps1"), got.state);
  assert.ok(!/^off/i.test(got.state.trim()), "a missing route is not an OFF filter");
  assert.equal(got.body, true, "no switch is drawn over a route that is not there");
});

/* ── 6. The "settings" event re-reads ──────────────────────────────────── */

await check("a settings event from the bus re-reads the PC's state", async () => {
  const page = await pageFor({ state: pcState() });
  const before = await page.evaluate(() => window.__a.reads);
  // The phone turns it on: the PC's answer changes and the bus says "settings".
  await page.evaluate(() => {
    window.__a.state.enabled = true;
    window.__emit("jarvis-event", { kind: "settings", id: 42, data: {} });
  });
  await page.waitForTimeout(500);
  const got = await page.evaluate(() => ({
    reads: window.__a.reads,
    checked: document.getElementById("asf-enabled").checked,
  }));
  await page.close();
  assert.ok(got.reads > before, `the event is a doorbell and must re-read (was ${before})`);
  assert.equal(got.checked, true,
    "a change made on the phone appears here without a reload");
});

await check("an unrelated bus event does not re-read", async () => {
  const page = await pageFor({ state: pcState() });
  const before = await page.evaluate(() => window.__a.reads);
  await page.evaluate(() => window.__emit("jarvis-event", { kind: "model", id: 7, data: {} }));
  await page.waitForTimeout(400);
  const after = await page.evaluate(() => window.__a.reads);
  await page.close();
  assert.equal(after, before, "every unrelated event must not become a read");
});

/* ── 7. The page never holds a token and never asks for a yes ────────────── */

await check("the page module never mentions an approval card or a token", async () => {
  const source = read("src/antislop-settings.js").split("*/").slice(1).join("");
  assert.ok(!/approv|token/i.test(source), "a local wording filter asks for nothing");
});

await check("the page is not held on a stale link, and says so", async () => {
  // The module's own comments say WHY it is not held, so the check strips every
  // block comment and reads only the code - which is where a `data-live`
  // attribute or a `linkWords` call would have to be to grey a control.
  const source = read("src/antislop-settings.js").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/linkWords/.test(source), "no control here greys for the link's state");
  assert.ok(!/data-live/.test(source), "data-live is the stale-link marker; none here");
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /"allow-get-antislop"/);
  assert.match(surfaces, /"allow-set-antislop"/);
  const rust = read("src-tauri/src/antislop.rs");
  assert.match(rust, /const ANTISLOP_PATH: &str = "\/api\/antislop"/, "the one route");
});

await browser.close();
close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
