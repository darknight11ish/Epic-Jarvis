/**
 * Settings -> Hardware and models (hardware-panel.js, hardware.rs).
 *
 * Every status here is REAL: `K.HARDWARE` is tests/fixtures/hardware-cases.json,
 * jarvis_hardware.status() and its POST answers, written by
 * tools/gen_hardware_cases.py. Nothing is hand-made.
 *
 * What must hold (docs/HARDWARE-PROFILES.md 4.5-4.8, JARVIS-API.md 20):
 * - every card is shown, an unused one with Ollama's reason in words;
 * - today's layout reads "Custom (your own setup)", and says it is
 *   calculated to be over the card;
 * - three setups, one marked (recommended) with its reason, each saying
 *   what is off and why, and "calculated, not measured";
 * - "Use this" sends ONE request naming the setup and nothing else;
 * - the steps come in order and only the next one has a button; pressing it
 *   sends the step's id only (the Rust reads the route from the backend),
 *   and the step then says it waits for approval. No "do them all";
 * - the one command, its undo and the check line, each with Copy;
 * - an older backend, or no answer, is a sentence - never a code or JSON.
 *
 * The CONTROL checks read the Rust and the permissions.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const HW = K.HARDWARE;

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1400 };
const open = (hardware) => K.open(browser, base, "settings.html", { hardware }, VIEW);

const section = (page) => page.evaluate(() => {
  const $ = (id) => document.getElementById(id);
  return {
    stateHidden: $("hw-state").hidden,
    state: $("hw-state").innerText,
    bodyHidden: $("hw-body").hidden,
    found: $("hw-found").innerText,
    cards: [...document.querySelectorAll("#hw-cards li")].map((li) => li.innerText),
    now: $("hw-now").innerText,
    nowBar: $("hw-now-bar").innerText,
    presets: [...document.querySelectorAll("#hw-presets .hw-preset")].map((p) => ({
      id: p.dataset.id,
      text: p.innerText,
      useDisabled: p.querySelector("button").disabled,
    })),
    stepsHidden: $("hw-steps").hidden,
    steps: [...document.querySelectorAll("#hw-step-list .hw-step")].map((li) => ({
      id: li.dataset.id, state: li.dataset.state, text: li.innerText,
      buttons: li.querySelectorAll("button").length,
    })),
    commandHidden: $("hw-command-box").hidden,
    command: $("hw-command").value,
    undo: $("hw-undo").value,
    checkLine: $("hw-check").value,
    readOnly: $("hw-command").readOnly && $("hw-undo").readOnly && $("hw-check").readOnly,
    restart: $("hw-restart").innerText,
    measured: $("hw-measured").innerText,
    status: $("hw-status").innerText,
    details: $("hw-details-list").textContent,
    later: $("hw-test-later").textContent,
    all: $("hardware").innerText,
    reads: window.__hardware.reads,
    applies: window.__hardware.applies,
    stepsAsked: window.__hardware.steps,
    measures: window.__hardware.measures,
  };
});
const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|\bnull\b|undefined|\[object|NaN/,
    `raw data on the page: ${text.slice(0, 400)}`);
};
const settle = (page) => page.waitForFunction(() => !document.getElementById("hw-body").hidden
  || document.getElementById("hw-state").dataset.tone === "bad");

await check("today's PC: every card, 'Custom (your own setup)', calculated over the card", async () => {
  const page = await open({ status: HW.today_one_card });
  await settle(page);
  const s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, false);
  assert.match(s.found, /Found 2 graphics cards; Ollama can use 1: the NVIDIA GeForce RTX 2080 SUPER\./);
  assert.equal(s.cards.length, 2);
  assert.match(s.cards[0], /RTX 2080 SUPER, 8 GB; used by Ollama through CUDA; a monitor is plugged into it\./);
  assert.match(s.cards[0], /Found by Ollama's log, nvidia-smi, the registry\./);
  assert.match(s.cards[1], /Not used: Ollama's log does not list it/);
  assert.match(s.now, /^Custom \(your own setup\)\. jarvis-primary is qwen3:8b with room for 16,384 tokens; calculated about 0\.60 GB over the card/);
  assert.match(s.nowBar, /6\.17 \+ 2\.43 = 8\.60 of 8 GB/);
  assert.equal(s.stepsHidden, true, "steps shown with nothing chosen");
  noRaw(s.all);
});

await check("three setups, one (recommended) with why, each saying what is off and 'calculated, not measured'", async () => {
  const page = await open({ status: HW.today_one_card });
  await settle(page);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.presets.map((p) => p.id), ["fast", "smart", "features"]);
  const rec = s.presets.filter((p) => /\(recommended\)/.test(p.text));
  assert.equal(rec.length, 1);
  assert.equal(rec[0].id, "smart");
  assert.match(rec[0].text, /It keeps the 8B everyday model/);
  for (const p of s.presets) {
    assert.match(p.text, /Calculated, not measured\./, `${p.id}`);
    assert.match(p.text, /What is off, and why:/, `${p.id}`);
    assert.match(p.text, /Use this/);
    assert.equal(p.useDisabled, false, `${p.id} cannot be chosen`);
  }
  const fast = s.presets[0].text;
  assert.match(fast, /Chat: qwen3:4b, 32K, compact format, on the NVIDIA GeForce RTX 2080 SUPER\. It remembers about 24 pages of conversation \(an estimate\)\./);
  assert.match(fast, /Pictures: off\./);
  assert.match(s.presets[2].text, /It takes turns with chat/);
  assert.match(s.later, /Spark-X2\.5-4B/);
  assert.match(s.later, /qwen3\.5/);
  assert.match(s.details, /Everything above is calculated, not measured\./);
});

await check("'Use this' sends one request naming the setup, and changes nothing else", async () => {
  const page = await open({ status: HW.today_one_card, afterApply: HW.chosen_first_step });
  await settle(page);
  await page.click("#hw-use-fast");
  await page.waitForFunction(() => !document.getElementById("hw-steps").hidden);
  const s = await section(page);
  await page.close();
  assert.deepEqual(s.applies, ["fast"]);
  assert.deepEqual(s.stepsAsked, [], "a step was asked for by choosing");
  assert.match(s.status, /Nothing has changed yet/);
});

await check("the steps: in order, only the next one has a button, and asking sends its id only", async () => {
  const page = await open({ status: HW.chosen_first_step });
  await settle(page);
  let s = await section(page);
  assert.equal(s.stepsHidden, false);
  assert.deepEqual(s.steps.map((x) => x.state), ["next", "later", "later", "later"]);
  assert.deepEqual(s.steps.map((x) => x.buttons), [1, 0, 0, 0], "a step other than the next has a button");
  assert.match(s.steps[0].text, /Download qwen3:4b \(about 2\.5 GB\)/);
  assert.match(s.steps[0].text, /Next\. It raises its own approval card\./);
  assert.match(s.steps[1].text, /Waits for the step before it\./);
  assert.match(s.steps[3].text, /Run the one command below on your PC, then restart Ollama\./);
  const chosen = s.presets.find((p) => p.id === "fast");
  assert.match(chosen.text, /Your choice/);
  assert.equal(chosen.useDisabled, true);
  await page.click("#hw-ask-install\\:qwen3\\:4b");
  await page.waitForFunction(() => window.__hardware.steps.length === 1);
  await page.waitForFunction(() => /Waiting for your approval/.test(document.getElementById("hw-status").innerText));
  s = await section(page);
  await page.close();
  assert.deepEqual(s.stepsAsked, ["install:qwen3:4b"]);
  assert.match(s.status, /Waiting for your approval\. Approve it/);
  const all = await Promise.resolve(s.all);
  assert.doesNotMatch(all, /do them all|approve all/i);
});

await check("a 'make a model' step shows exactly what is made, and a waiting one says so", async () => {
  const page = await open({ status: HW.create_waiting });
  await settle(page);
  const s = await section(page);
  const mf = await page.evaluate(() => document.querySelector(".hw-modelfile").textContent);
  await page.close();
  assert.deepEqual(s.steps.map((x) => x.state), ["done", "waiting", "later", "later"]);
  assert.match(s.steps[0].text, /Done\./);
  assert.match(s.steps[1].text, /Waiting for your approval/);
  assert.equal(s.steps[1].buttons, 0, "a waiting step can be asked for again");
  assert.match(mf, /^FROM qwen3:8b\nPARAMETER num_ctx 8192/);
  assert.match(mf, /SYSTEM """You are Jarvis/);
});

await check("the one command, its undo and the check line: read-only, each with Copy", async () => {
  const page = await open({ status: HW.planned_pair });
  await settle(page);
  const s = await section(page);
  await page.close();
  assert.equal(s.commandHidden, false);
  assert.equal(s.readOnly, true);
  assert.match(s.command, /^\[Environment\]::SetEnvironmentVariable\('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'\); /);
  assert.match(s.command, /'CUDA_VISIBLE_DEVICES', 'GPU-3f2a9c1e-7b1d-4e8a-9c55-0d4b2e6a8f10'/);
  assert.match(s.command, /'OLLAMA_VULKAN', '0'/);
  assert.match(s.undo, /'OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User'\)/, "undo does not put today's q8_0 back");
  assert.match(s.checkLine, /^foreach \(\$n in /);
  assert.doesNotMatch(s.command + s.undo + s.checkLine, /\n|\?\?|&&/);
  const feat = s.presets.find((p) => p.id === "features").text;
  assert.match(feat, /\(recommended\)/);
  assert.match(feat, /Long conversations: qwen3:14b, 16K/);
  assert.match(feat, /NVIDIA GeForce RTX 2060/);
});

await check("an AMD card through Vulkan: best effort, not tested - said on the card and the setups", async () => {
  const page = await open({ status: HW.amd_vulkan });
  await settle(page);
  const s = await section(page);
  await page.close();
  assert.match(s.cards[0], /Best effort, not tested/);
  for (const p of s.presets) assert.match(p.text, /Best effort, not tested: the AMD Radeon RX 6600 is an AMD card/);
  assert.doesNotMatch(s.command, /OLLAMA_VULKAN/);
  noRaw(s.all);
});

await check("Measure sends one request and says what it will do first", async () => {
  const page = await open({ status: HW.today_one_card });
  await settle(page);
  await page.click("#hw-measure");
  await page.waitForFunction(() => window.__hardware.measures === 1);
  await page.waitForFunction(() => /Measuring\./.test(document.getElementById("hw-status").innerText));
  const s = await section(page);
  await page.close();
  assert.match(s.all, /It loads each model once/);
  assert.match(s.measured, /Not measured yet|Measuring/);
});

await check("an older backend, or no answer: a sentence, never a code", async () => {
  let page = await open({ status: HW.today_one_card, unavailable: true });
  await settle(page);
  let s = await section(page);
  await page.close();
  assert.equal(s.bodyHidden, true);
  assert.match(s.state, /does not have the hardware part yet\. Update the backend by running apply-patches\.ps1/);
  page = await open({ status: HW.today_one_card, getFails: "Jarvis is not answering at http://127.0.0.1:4719. Is it running?" });
  await settle(page);
  s = await section(page);
  await page.close();
  assert.match(s.state, /Jarvis could not be asked about your graphics cards\. Jarvis is not answering/);
  noRaw(s.state);
});

await check("CONTROL: only the settings window may call the four commands", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  for (const perm of ["allow-get-hardware", "allow-apply-hardware", "allow-hardware-step", "allow-measure-hardware"]) {
    const holders = sets.filter((s) => s.includes(`"${perm}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["settings-surface"], `${perm} is held by ${holders}`);
  }
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of ["get_hardware", "apply_hardware", "hardware_step", "measure_hardware"]) {
    assert.ok(build.includes(`"${cmd}"`), `${cmd} is not in build.rs`);
    assert.ok(lib.includes(`hardware::${cmd},`), `${cmd} is not registered`);
    const gen = read(`src-tauri/permissions/autogenerated/${cmd}.toml`);
    assert.match(gen, new RegExp(`commands.allow = \\["${cmd}"\\]`));
  }
});

await check("CONTROL: a step's route comes from the backend, only four routes, and asking is held on a stale link", async () => {
  const rust = read("src-tauri/src/hardware.rs");
  const cmd = rust.slice(rust.indexOf("pub async fn hardware_step("), rust.indexOf("pub async fn measure_hardware("));
  assert.match(cmd, /if stale\(&app\)/);
  assert.match(cmd, /let status = read\(&app\)\.await\?;/);
  assert.match(cmd, /step_request\(&status, &step_id\)/);
  assert.match(rust, /STEP_ROUTES: \[&str; 4\] = \[\s*"\/api\/models\/install",\s*"\/api\/models\/switch",\s*"\/api\/hardware\/create",\s*"\/api\/second-card",\s*\]/);
  const apply = rust.slice(rust.indexOf("pub async fn apply_hardware("), rust.indexOf("pub async fn hardware_step("));
  assert.match(apply, /preset\.is_some\(\) && stale\(&app\)/, "forgetting a setup is held too, or choosing is not");
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
