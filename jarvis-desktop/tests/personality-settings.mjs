/**
 * personality-settings.mjs - "How Jarvis talks": the personality presets page.
 *
 * Runs headless on plain Node + Playwright (tests/uikit.mjs):
 *
 *     node tests/personality-settings.mjs
 *
 * WHY THIS EXISTS (2026-10-23, Personality Presets SLICE 2a). The page now
 * draws the eight preset cards, the four tuning dials, the voice-sync switch
 * and "My personalities". The data mapping is held pure by
 * tests/personalities.mjs; THIS file drives the real page in a headless
 * browser with a stubbed bridge and proves what a click sends:
 *
 *   - the eight cards render in the PC's order, the active one says "In use";
 *   - "Hear Sample" asks the PC for the preset's BASE voice only
 *     (`hear_voice_sample` with exactly `{voice}` - the PC's sample route
 *     accepts one field; blended-voice previews are deferred to the
 *     Kokoro/Live slice, and the page says so) - the page never makes a sound
 *     itself;
 *   - "Use This Personality" sends the personality id alone;
 *   - a custom preset that came from another client keeps the PC's own id
 *     through Use and Delete (a server `custom-x` id is not rewritten);
 *   - a dial pill sends the four dials; the sync switch sends `voice_sync`;
 *   - a custom personality is saved and deleted with the explicit
 *     `confirm: true`, and the delete asks the owner first;
 *   - per-row actions say which personality they act on, `role="list"` is not
 *     claimed without list items, and the one-shot "Use" is not a toggle;
 *   - on a PC that does not have the personality fields yet the new controls
 *     are visible but disabled with the plain update sentence, and the older
 *     two choices still work and still send exactly `{manner}`.
 *
 * NOT proven here: the real Tauri bridge, a real backend's answers, that a
 * sample plays through a sound card, or how any of it looks on screen.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const P = await import("../src/personalities.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** A PC that has the fields: the old answer plus the new half. */
function pcAnswer() {
  return {
    available: true,
    manner: "warm",
    title: "How Jarvis talks",
    detail: "PC detail",
    spoken: "PC spoken",
    choices: [{ id: "warm", label: "Warm and brief (default)", why: "Warm." },
              { id: "plain", label: "Plain", why: "Plain." }],
    personality: "classic_butler",
    dials: { humor: 2, brevity: "balanced", formality: "formal_butler", address: "sir" },
    voice_sync: true,
    personalities: P.PRESETS.map((p) => ({
      id: p.id, title: p.title, description: `PC ${p.title} line`,
      quote: p.quote, switch_ack: p.switchAck,
      voice: { blend: p.voice.blend, fallback: p.voice.fallback,
               speed: p.voice.speed, label: p.voice.label },
    })),
    custom_personalities: [{
      id: "mine-calmy", name: "Calmy", line: "Quiet and direct.",
      example: "You: hi", based_on: "calm_stoic", dials: P.defaultDials(),
      voice: { blend: "af_sky:0.65+af_heart:0.35", fallback: "af_sky", speed: 0.94,
               label: "Soft Calm Blend" },
    }, {
      // Saved by another client (the phone/PC mints `custom-…` on a name
      // collision) - the desktop must not rewrite this id (review blocker 3).
      id: "custom-x", name: "Server Mix", line: "Saved elsewhere.",
      example: "", based_on: "warm_peer", dials: P.defaultDials(),
    }],
  };
}

/** Stub the two commands the page uses, and record every call. */
function bridge(payload) {
  const core = window.__TAURI__.core;
  const inner = core.invoke;
  window.__p = { payload, calls: [], confirmAsked: 0, confirm: true };
  core.invoke = async (cmd, args) => {
    if (cmd === "get_manner") return window.__p.payload;
    if (cmd === "set_manner") {
      window.__p.calls.push({ cmd, args });
      const p = window.__p.payload;
      const a = args || {};
      if (a.manner !== undefined) p.manner = a.manner;
      if (a.personality !== undefined) p.personality = a.personality;
      if (a.dials !== undefined) p.dials = a.dials;
      if (a.voice_sync !== undefined) p.voice_sync = a.voice_sync;
      if (a.custom && a.custom.op === "save") {
        p.custom_personalities = [...(p.custom_personalities || []),
          { ...a.custom, name: a.custom.name, line: a.custom.line,
            example: a.custom.example, based_on: a.custom.based_on }];
      }
      if (a.custom && a.custom.op === "delete") {
        p.custom_personalities = (p.custom_personalities || [])
          .filter((x) => x.id !== a.custom.id);
      }
      return { ok: true, said: "PC said it." };
    }
    if (cmd === "hear_voice_sample") {
      window.__p.calls.push({ cmd, args });
      return { ok: true, audio: "data:audio/wav;base64,UklGRg==" };
    }
    return inner(cmd, args);
  };
  window.confirm = () => { window.__p.confirmAsked += 1; return window.__p.confirm; };
}

const { base, close } = await K.serve();
const browser = await K.launch();

async function pageFor(payload) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 1200, height: 2400 });
  await page.addInitScript(bridge, payload);
  await page.reload();
  await page.waitForTimeout(700);
  return page;
}

/* ── 1. The eight cards, the active one, the voice badge ───────────────── */

await check("the eight preset cards render in order, with the PC's words", async () => {
  const page = await pageFor(pcAnswer());
  const got = await page.evaluate(() => [...document.querySelectorAll("#mn-presets .mn-preset")]
    .map((box) => ({
      id: box.dataset.preset,
      title: box.querySelector(".mn-preset-title").textContent,
      desc: box.querySelector(".mn-preset-desc").textContent,
      voice: box.querySelector(".mn-voice").textContent,
      quote: box.querySelector(".mn-preset-quote").textContent,
    })));
  await page.close();
  assert.deepEqual(got.map((g) => g.id), [...P.PRESET_IDS]);
  assert.equal(got[1].title, "Classic British Butler");
  assert.equal(got[1].desc, "PC Classic British Butler line", "the PC's description wins");
  assert.match(got[1].voice, /British Baritone Blend \u00b7 1\.02x/);
  assert.ok(got[1].quote.includes("Very good, sir"));
});

await check("the chosen personality says In use; the others offer Use", async () => {
  const page = await pageFor(pcAnswer());
  const got = await page.evaluate(() => ({
    active: [...document.querySelectorAll("#mn-presets .mn-use")]
      .filter((b) => b.dataset.active === "true").map((b) => b.dataset.use),
    text: document.querySelector('.mn-use[data-use="classic_butler"]').textContent,
  }));
  await page.close();
  assert.deepEqual(got.active, ["classic_butler"]);
  assert.equal(got.text, "In use");
});

/* ── 2. Hear Sample: the PC makes the sound, in the preset's voice ─────── */

await check("Hear Sample asks the PC for the base voice only, and says so", async () => {
  const page = await pageFor(pcAnswer());
  await page.locator('.mn-hear[data-hear="classic_butler"]').click();
  await page.waitForTimeout(300);
  const got = await page.evaluate(() => ({
    calls: window.__p.calls,
    status: document.getElementById("mn-status").textContent,
    note: document.getElementById("mn-hear-note").textContent,
  }));
  await page.close();
  const call = got.calls.find((c) => c.cmd === "hear_voice_sample");
  assert.ok(call, "no sample request reached the PC");
  // Exactly one field: the PC's route is set(body) == {"voice"} and answers a
  // 400 to anything else (review blocker 1).
  assert.deepEqual(call.args, { voice: "bm_george" });
  assert.deepEqual(Object.keys(call.args), ["voice"]);
  assert.match(got.status, /Playing British Baritone Blend/);
  assert.match(got.note, /base voice/i);
  assert.match(got.note, /blended/i, "the deferral is said on the page, not hidden");
});

/* ── 3. Use, dials, sync: ONE field per change ─────────────────────────── */

await check("Use This Personality sends the personality id alone", async () => {
  const page = await pageFor(pcAnswer());
  await page.locator('.mn-use[data-use="dry_wit"]').click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__p.calls);
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_manner", args: { personality: "dry_wit" } }]);
});

await check("a dial pill sends all four dials, with the clicked one changed", async () => {
  const page = await pageFor(pcAnswer());
  await page.locator('#mn-dials .mn-dial[data-dial="humor"] .mn-btn[data-value="3"]').click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__p.calls);
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_manner",
    args: { dials: { humor: 3, brevity: "balanced", formality: "formal_butler",
                     address: "sir" } } }]);
});

await check("the voice-sync switch sends only the switch", async () => {
  const page = await pageFor(pcAnswer());
  await page.locator("#mn-sync").uncheck();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__p.calls);
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_manner", args: { voice_sync: false } }]);
});

/* ── 4. My personalities: save, duplicate, delete with confirm ─────────── */

await check("saving a custom personality sends bounded fields and a safe id", async () => {
  const page = await pageFor(pcAnswer());
  await page.fill("#mn-custom-name", "  Tester  ");
  await page.fill("#mn-custom-line", "Calm and quick.");
  await page.fill("#mn-custom-example", "On it.");
  await page.selectOption("#mn-custom-base", "calm_stoic");
  await page.locator("#mn-custom-form button[type=submit]").click();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__p.calls);
  await page.close();
  const save = calls[0];
  assert.equal(save.cmd, "set_manner");
  assert.equal(save.args.custom.op, "save");
  assert.equal(save.args.custom.name, "Tester");
  assert.equal(save.args.custom.line, "Calm and quick.");
  assert.equal(save.args.custom.based_on, "calm_stoic");
  assert.match(save.args.custom.id, /^mine-/);
  assert.equal(save.args.custom.dials.humor, 0, "the chosen base preset's dials");
});

await check("Delete asks the owner first, then sends the explicit confirm", async () => {
  const page = await pageFor(pcAnswer());
  await page.locator('#mn-mine .mn-mine-row[data-custom="mine-calmy"] .mn-btn',
    { hasText: "Delete" }).click();
  await page.waitForTimeout(300);
  const got = await page.evaluate(() => ({ asked: window.__p.confirmAsked,
                                            calls: window.__p.calls }));
  await page.close();
  assert.equal(got.asked, 1, "the page must ask before deleting");
  assert.deepEqual(got.calls, [{ cmd: "set_manner",
    args: { custom: { op: "delete", id: "mine-calmy", confirm: true } } }]);
});

await check("the custom row is drawn with the PC's own name and line", async () => {
  const page = await pageFor(pcAnswer());
  const got = await page.evaluate(() => ({
    name: document.querySelector('#mn-mine .mn-mine-name').textContent,
    line: document.querySelector('#mn-mine .mn-mine-line').textContent,
  }));
  await page.close();
  assert.equal(got.name, "Calmy");
  assert.equal(got.line, "Quiet and direct.");
});

await check("a custom preset saved by another client keeps the PC's own id for Use and Delete", async () => {
  const page = await pageFor(pcAnswer());
  const row = '#mn-mine .mn-mine-row[data-custom="custom-x"]';
  await page.locator(`${row} .mn-btn`, { hasText: "Use" }).click();
  await page.waitForTimeout(300);
  const afterUse = await page.evaluate(() => window.__p.calls);
  await page.locator(`${row} .mn-btn`, { hasText: "Delete" }).click();
  await page.waitForTimeout(300);
  const got = await page.evaluate(() => ({ asked: window.__p.confirmAsked,
                                            calls: window.__p.calls }));
  await page.close();
  // The server's id is sent verbatim: no `mine-` prefix is invented over a row
  // that came FROM the PC (review blocker 3).
  assert.deepEqual(afterUse, [{ cmd: "set_manner", args: { personality: "custom-x" } }]);
  assert.equal(got.asked, 1, "the page must ask before deleting");
  assert.deepEqual(got.calls.at(-1), { cmd: "set_manner",
    args: { custom: { op: "delete", id: "custom-x", confirm: true } } });
});

await check("row actions name their personality; no list role, no pressed state on Use", async () => {
  const page = await pageFor(pcAnswer());
  const got = await page.evaluate(() => ({
    hear: document.querySelector('.mn-hear[data-hear="classic_butler"]').getAttribute("aria-label"),
    use: document.querySelector('.mn-use[data-use="classic_butler"]').getAttribute("aria-label"),
    usePressed: document.querySelector('.mn-use[data-use="classic_butler"]').hasAttribute("aria-pressed"),
    listRole: document.getElementById("mn-presets").getAttribute("role"),
    customLabels: [...document.querySelectorAll(
      '#mn-mine .mn-mine-row[data-custom="mine-calmy"] .mn-btn')]
      .map((b) => b.getAttribute("aria-label")),
    dialPressed: document.querySelector('#mn-dials .mn-btn[aria-pressed="true"]') !== null,
  }));
  await page.close();
  assert.match(got.hear, /Hear Sample.*Classic British Butler/,
    `a screen reader must hear which preset the sample is for: ${got.hear}`);
  assert.match(got.use, /Classic British Butler/);
  assert.equal(got.usePressed, false,
    "Use is a one-shot action; aria-pressed describes a toggle and belongs on the dial pills");
  assert.equal(got.listRole, null,
    'role="list" with no listitem children is not a list assistive tech can report');
  assert.equal(got.customLabels.length, 3);
  for (const label of got.customLabels) assert.match(label, /Calmy/,
    `a custom row action must name its personality: ${label}`);
  assert.ok(got.dialPressed, "the dial pills keep their pressed state");
});

/* ── 5. Older PC: visible, disabled, honest; the two choices still work ── */

await check("an older PC shows the update sentence and disables the new controls", async () => {
  const page = await pageFor({
    available: true, manner: "warm", title: "How Jarvis talks", detail: "PC detail",
    spoken: "PC spoken",
    choices: [{ id: "warm", label: "Warm and brief (default)", why: "Warm." },
              { id: "plain", label: "Plain", why: "Plain." }],
  });
  const got = await page.evaluate(() => ({
    note: document.getElementById("mn-presets-note").textContent,
    presetDisabled: [...document.querySelectorAll("#mn-presets .mn-btn")]
      .every((b) => b.disabled),
    syncDisabled: document.getElementById("mn-sync").disabled,
    legacyShown: document.querySelectorAll("#mn-choices .theme-row").length,
  }));
  await page.close();
  assert.ok(got.note.includes("apply-patches.ps1"), got.note);
  assert.ok(got.presetDisabled, "a preset button must not look usable on an older PC");
  assert.ok(got.syncDisabled);
  assert.equal(got.legacyShown, 2, "the older two choices stay");
});

await check("on an older PC the two choices still send exactly {manner}", async () => {
  const page = await pageFor({
    available: true, manner: "warm", title: "How Jarvis talks", detail: "PC detail",
    spoken: "PC spoken",
    choices: [{ id: "warm", label: "Warm and brief (default)", why: "Warm." },
              { id: "plain", label: "Plain", why: "Plain." }],
  });
  await page.locator('#mn-choices input[value="plain"]').check();
  await page.waitForTimeout(300);
  const calls = await page.evaluate(() => window.__p.calls);
  await page.close();
  assert.deepEqual(calls, [{ cmd: "set_manner", args: { manner: "plain" } }]);
});

/* ── 6. The page never holds a token and never talks about a yes ───────── */

await check("the page module never mentions a card or an approval", async () => {
  const source = read("src/manner-settings.js").split("*/").slice(1).join("");
  assert.ok(!/approv|card/i.test(source));
});

await browser.close();
close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
