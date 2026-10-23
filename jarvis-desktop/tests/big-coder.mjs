/**
 * Settings -> Big model (slow) -> "The big coding model (30B coder)".
 *
 * Task-79 (owner requirement, 2026-10-22): every feature must be findable AND
 * adjustable in Settings, not only by typing at Jarvis. The big coding model
 * had a BoolSetting, a state reader and a PC route, but no desktop control.
 *
 * WHAT MUST HOLD:
 * - the switch reads the PC's own status and says the PC's own words;
 * - flipping it calls the ONE existing command (`big_coder`) with the ONE
 *   existing route body (on/off), never a start/stop action;
 * - ON waits for a person's card (the page says so) and OFF is immediate;
 * - ON is held while the link is stale (rule 4), OFF never is;
 * - a PC without the route is a sentence, never a code or a dead control;
 * - Settings search finds the card by the feature's ordinary words
 *   ("big coding model", "30B coder");
 * - and the control is Settings-only, wired through the app manifest, with no
 *   approval path anywhere near it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const VIEW = { width: 900, height: 1400 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);

const ready = async (page) => {
  await page.waitForFunction(
    () => {
      const body = document.getElementById("bc-body");
      const reading = document.getElementById("bc-state");
      return (body && !body.hidden) || (reading && /does not have|not have/.test(reading.textContent));
    },
    { timeout: 8000 },
  );
};

const state = (page) => page.evaluate(() => ({
  button: (document.getElementById("bc-switch") || {}).textContent || "",
  ariaChecked: document.getElementById("bc-switch")?.getAttribute("aria-checked") || "",
  disabled: Boolean(document.getElementById("bc-switch")?.disabled),
  line: (document.getElementById("bc-line") || {}).textContent || "",
  running: (document.getElementById("bc-running") || {}).textContent || "",
  linkNote: (document.getElementById("bc-link-note") || {}).textContent || "",
  said: (document.getElementById("bc-status") || {}).textContent || "",
  bodyHidden: Boolean(document.getElementById("bc-body")?.hidden),
  reading: (document.getElementById("bc-state") || {}).textContent || "",
  calls: window.__bigCoderCalls || [],
  invokes: window.__calls
    .filter((c) => c[0] === "big_coder")
    .map((c) => c[1]),
}));

await check("the switch reads the PC's own status and offers the real control", async () => {
  const page = await open({ bigCoder: { on: false, running: false,
    message: "Off unless you turn it on here." } });
  await ready(page);
  const s = await state(page);
  assert.equal(s.bodyHidden, false, "the control never appeared");
  assert.equal(s.button.trim(), "Turn the big coding model on");
  assert.equal(s.ariaChecked, "false", "the switch does not expose its off state");
  assert.match(s.line, /Off unless you turn it on here/, s.line);
  assert.equal(s.running, "", "nothing is running, so nothing is claimed");
  assert.deepEqual(s.calls, ["read"], "the read must be one command");
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await check("ON is the ONE existing command, waits for the card, and says so", async () => {
  const page = await open({ bigCoder: { on: false, running: false, message: "" } });
  await ready(page);
  await page.evaluate(() => document.getElementById("bc-switch").click());
  await page.waitForFunction(
    () => /big coding model is on/.test(document.getElementById("bc-line").textContent),
    { timeout: 8000 },
  );
  const s = await state(page);
  // The command carries the route's one boolean and nothing else.
  assert.deepEqual(s.invokes.filter((a) => a.action === "on"),
    [{ action: "on" }], JSON.stringify(s.invokes));
  assert.equal(s.button.trim(), "Turn the big coding model off");
  assert.equal(s.ariaChecked, "true", "the switch did not expose its on state");
  assert.match(s.line, /big coding model is on/, s.line);
  // The page never starts or stops the model - only the switch position.
  assert.ok(!s.invokes.some((a) => a.action === "start" || a.action === "stop"),
    "the page sent a start/stop action");
  assert.ok(!/\bstart\b/i.test(s.said) || /code job/.test(s.said),
    `the page offered to start it: ${s.said}`);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await check("OFF is one call and immediate, never held by a stale link", async () => {
  const page = await open({
    link: { stale: true },
    bigCoder: { on: true, running: false, message: "On. It starts only when you ask for a code job." },
  });
  await ready(page);
  const s = await state(page);
  assert.equal(s.disabled, false, "OFF was held on a stale link");
  assert.equal(s.button.trim(), "Turn the big coding model off");
  await page.evaluate(() => document.getElementById("bc-switch").click());
  await page.waitForFunction(
    () => /big coding model is off/i.test(document.getElementById("bc-line").textContent),
    { timeout: 8000 },
  );
  const after = await state(page);
  assert.deepEqual(after.invokes.filter((a) => a.action === "off"),
    [{ action: "off" }], JSON.stringify(after.invokes));
  assert.match(after.line, /big coding model is off/i, after.line);
  await page.close();
});

await check("ON is held while the link is stale, in plain words", async () => {
  const page = await open({ link: { stale: true }, bigCoder: { on: false, running: false } });
  await ready(page);
  const s = await state(page);
  assert.equal(s.disabled, true, "ON was offered on a stale link");
  assert.match(s.linkNote, /connection is catching up/i, s.linkNote);
  assert.match(s.linkNote, /turning it off works at once/i, s.linkNote);
  await page.evaluate(() => document.getElementById("bc-switch").click());
  await page.waitForTimeout(150);
  const after = await state(page);
  assert.ok(!after.invokes.some((a) => a.action === "on"),
    "the page called the PC while the link was stale");
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await check("a PC without the route says so and leaves no dead control", async () => {
  const page = await open({
    invokeFails: {
      big_coder: "Your PC's Jarvis does not have the big coding model yet.",
    },
    bigCoder: { on: false, running: false },
  });
  await page.waitForFunction(
    () => /does not have the big coding model/.test(
      document.getElementById("bc-state").textContent),
    { timeout: 8000 },
  );
  const s = await state(page);
  assert.equal(s.bodyHidden, true, "a dead switch was left on screen");
  assert.match(s.reading, /does not have the big coding model/, s.reading);
  await page.close();
});

await check("search finds the feature by its ordinary words", async () => {
  const page = await open();
  await ready(page);
  const type = async (text) => {
    await page.locator("#settings-search-input").fill(text);
    await page.waitForTimeout(250);
  };
  await type("big coding model");
  const first = await page.evaluate(() =>
    [...document.querySelectorAll("main .card")].filter((c) => !c.hidden).map((c) => c.id));
  assert.ok(first.includes("big-model"),
    `"big coding model" did not find the card: ${first.join(",")}`);
  await type("30b coder");
  const second = await page.evaluate(() =>
    [...document.querySelectorAll("main .card")].filter((c) => !c.hidden).map((c) => c.id));
  assert.ok(second.includes("big-model"),
    `"30B coder" did not find the card: ${second.join(",")}`);
  await type("");
  await page.close();
});

/* ── The control is Settings-only, wired, and approves nothing ───────────── */

await check("CONTROL: the command's vocabulary is the switch only, and ON waits for a person", async () => {
  const rust = read("src-tauri/src/big_coder.rs");
  assert.match(rust, /pub\(crate\) const ACTIONS: &\[&str; 3\] = &\["read", "on", "off"\];/);
  assert.match(rust, /"on" => serde_json::json!\(\{ "on": true \}\)/);
  assert.match(rust, /"off" => serde_json::json!\(\{ "on": false \}\)/);
  assert.match(rust, /const ON_WAIT: Duration = Duration::from_secs\(20 \* 60\);/);
  assert.match(rust, /fn held\(action: &str, stale: bool\) -> bool \{/);
  // It approves nothing and cannot answer a card: no decision function, no
  // approval route - the word may appear only in its own prose.
  assert.doesNotMatch(rust, /decide_approval|answer_card|fn .*approve|gate_check/);
  // It sends the switch and never a start/stop action.
  assert.doesNotMatch(rust, /"action": "(start|stop)"/);
});

await check("CONTROL: the command is declared, registered, and granted to Settings only", async () => {
  const build = read("src-tauri/build.rs");
  assert.match(build, /"big_coder",/,
    "the app manifest does not declare big_coder - the call would be refused silently");
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /pub mod big_coder;/);
  assert.match(lib, /big_coder::big_coder,/);
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  assert.match(surfaces, /identifier = "big-coder"/);
  const set = surfaces.slice(surfaces.indexOf('identifier = "big-coder"'));
  assert.match(set.slice(0, set.indexOf("[[set]]", 1)), /"allow-big-coder"/);
  const settings = read("src-tauri/capabilities/settings.json");
  assert.match(settings, /"big-coder",/);
  // No other window's capability may hold it.
  for (const name of ["quickbar", "brain", "hud", "widget", "faces", "floating",
    "features", "onboarding", "live-badge", "watch-badge"]) {
    let cap = "";
    try {
      cap = read(`src-tauri/capabilities/${name}.json`);
    } catch {
      continue;
    }
    assert.doesNotMatch(cap, /big-coder/, `${name} can call the big coder command`);
  }
  assert.ok(read("src-tauri/permissions/autogenerated/big_coder.toml")
    .includes('identifier = "allow-big-coder"'));
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}`
  : "\nthe big coding model's Settings control holds");
process.exit(fails.length ? 1 : 0);
