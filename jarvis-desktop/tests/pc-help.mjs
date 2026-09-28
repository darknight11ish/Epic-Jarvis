/**
 * Settings -> Hardware and models -> PC help (pc-help.js, hardware.rs
 * get_pc_help; JARVIS-API section 84).
 *
 * Every answer here is REAL: tests/fixtures/pc-help-cases.json is
 * jarvis_pc_help.read() with made-up readings, written by
 * tools/gen_pc_help_cases.py. Nothing is hand-made.
 *
 * What must hold:
 * - nothing is asked of the PC until "Check now" is pressed (no timer);
 * - the five answers are shown in the PC's own words, in order, with the
 *   "only reads" and "program names stay on your PC" lines;
 * - an older backend, or a failure, is a sentence - never a code or JSON;
 * - the button is never held on a stale link (it only reads), and there is
 *   no other control: nothing here can change anything.
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
const CASES = JSON.parse(read("tests/fixtures/pc-help-cases.json")).cases;

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** Open Settings with get_pc_help answering `answer` (or throwing `fail`). */
async function open(answer, { fail = null, link = {} } = {}) {
  const page = await K.open(browser, base, "settings.html", { link }, { width: 760, height: 1400 });
  await page.evaluate(({ answer, fail }) => {
    const core = window.__TAURI__.core;
    const invoke = core.invoke;
    window.__pcHelpReads = 0;
    core.invoke = async (cmd, args) => {
      if (cmd !== "get_pc_help") return invoke(cmd, args);
      window.__pcHelpReads += 1;
      if (fail) throw new Error(fail);
      return JSON.parse(JSON.stringify(answer));
    };
  }, { answer, fail });
  return page;
}

const state = (page) => page.evaluate(() => ({
  reads: window.__pcHelpReads,
  items: [...document.querySelectorAll("#pc-help-list .pc-help-item")].map((li) => ({
    id: li.dataset.id,
    title: li.querySelector(".pc-help-title").innerText,
    words: li.querySelector(".pc-help-words").innerText,
  })),
  notes: [...document.querySelectorAll("#pc-help-list .pc-help-note")].map((li) => li.innerText),
  status: document.getElementById("pc-help-status").innerText,
  button: document.getElementById("pc-help-check").innerText,
  disabled: document.getElementById("pc-help-check").disabled,
  buttons: document.querySelectorAll("#pc-help button").length,
  all: document.getElementById("pc-help").innerText,
}));

const noRaw = (text) => {
  assert.doesNotMatch(text, /[{}]|HTTP \d|"available"|\bnull\b|undefined|\[object|NaN/,
    `raw data on the page: ${text.slice(0, 400)}`);
};

const press = async (page) => {
  await page.click("#pc-help-check");
  await page.waitForFunction(() => {
    const s = document.getElementById("pc-help-status");
    return !document.getElementById("pc-help-check").disabled
      && (document.querySelector("#pc-help-list li") || s.dataset.tone === "warn");
  });
};

await check("nothing is asked until Check now is pressed", async () => {
  const page = await open(CASES.busy);
  await page.waitForTimeout(400);
  const s = await state(page);
  await page.close();
  assert.equal(s.reads, 0, "the PC was asked on opening");
  assert.equal(s.button, "Check now");
  assert.equal(s.items.length, 0);
  assert.equal(s.buttons, 1, "PC help has a control other than Check now");
});

await check("the five answers, the PC's own words, in order, with both notes", async () => {
  const page = await open(CASES.busy);
  await press(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.reads, 1);
  assert.deepEqual(s.items.map((i) => i.id), ["slow", "disk", "gpu", "heat", "restart"]);
  for (const [i, sec] of CASES.busy.sections.entries()) {
    assert.equal(s.items[i].title, sec.title);
    assert.equal(s.items[i].words, sec.words);
  }
  assert.match(s.items[0].words, /Jarvis's AI model \(38%\)/);
  assert.deepEqual(s.notes, [CASES.busy.private, CASES.busy.changes]);
  assert.match(s.notes[1], /PC help only reads/);
  assert.equal(s.status, "");
  noRaw(s.all);
});

await check("nothing could be read: five plain sentences, no numbers made up", async () => {
  const page = await open(CASES.nothing_read);
  await press(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.items.length, 5);
  for (const i of s.items) assert.equal(i.words, "Jarvis could not read this on your PC just now.");
  noRaw(s.all);
});

await check("an older backend says to update, in words", async () => {
  const page = await open({ available: false,
    why: "This PC's Jarvis does not have PC help yet. Update the backend by running apply-patches.ps1, then try again." });
  await press(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.items.length, 0);
  assert.match(s.status, /does not have PC help yet.*apply-patches\.ps1/);
  noRaw(s.all);
});

await check("a failure is a sentence, never a bridge error", async () => {
  const page = await open(null, { fail: "command get_pc_help not allowed on window settings" });
  await press(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.status, "Try again in a moment, or restart Jarvis Desktop.");
  noRaw(s.all);
});

await check("a stale link does not hold it: it only reads", async () => {
  const page = await open(CASES.calm, { link: { stale: true } });
  await press(page);
  const s = await state(page);
  await page.close();
  assert.equal(s.items.length, 5);
});

await check("CONTROL: the command is registered, allowed on Settings only, and the path is the PC's", async () => {
  const lib = read("src-tauri/src/lib.rs");
  const build = read("src-tauri/build.rs");
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  const rs = read("src-tauri/src/hardware.rs");
  assert.match(lib, /hardware::get_pc_help,/);
  assert.match(build, /"get_pc_help",/);
  assert.equal((surfaces.match(/"allow-get-pc-help"/g) || []).length, 1, "allowed on more than one surface");
  assert.match(rs, /PC_HELP_PATH: &str = "\/api\/pc\/help"/);
  assert.doesNotMatch(rs.split("fn get_pc_help")[1].split("\n}\n")[0], /stale\(/,
    "a read is held on a stale link");
});

await browser.close();
await close();
if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
