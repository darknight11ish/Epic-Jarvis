/**
 * "Limits and frequency" on the desktop (2026-10-08; src/limits.js,
 * src/limits-settings.js, src-tauri/src/limits.rs, backend/jarvis_limits.py,
 * limits-read.patch + limits-settings.patch).
 *
 * What must hold:
 * - the page keeps the PC's own words and drops the rows the table marks for
 *   the PHONE (a row says who owns it, so the two screens cannot drift);
 * - a choice row offers the PC's own choices and sends the value picked - and
 *   never a "raise"/"lower" label, because which way a change goes is the
 *   backend's decision, not this page's;
 * - a step row moves one step and stops at the PC's own low and high;
 * - a refusal from the PC is shown in the PC's words, and nothing is drawn as
 *   changed before the PC answers;
 * - CONTROL: the two commands sit with the Settings window only, the read is a
 *   GET and the write is a POST to the settings route.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { normaliseLimits, problemWords, rowWords, stepped, valueFor } from "../src/limits.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* A real answer, in the shape the PC's own view() writes. */
const VIEW = {
  ok: true,
  available: true,
  limits: [
    { key: "undo_window", title: "How long you can undo", kind: "int", value: 24,
      words: "keep undo for a day", choices: [1, 24, 168], low: 1, high: 720,
      unit: "hours", note: "A longer window keeps older copies of your files on this PC.",
      loosen_up: true, pc_only: false, app: "both" },
    { key: "jobs_per_tick", title: "Jobs at once", kind: "int", value: 4,
      words: "4 at once", choices: [], low: 1, high: 16, unit: "jobs",
      note: "Only this PC may change this one.", loosen_up: true, pc_only: true,
      app: "desktop" },
    { key: "memory_people", title: "Look for people and things", kind: "bool",
      value: false, words: "off", choices: [], low: 0, high: 0, unit: "",
      note: "", loosen_up: true, pc_only: false, app: "phone" },
  ],
};

/* ── The reading half ─────────────────────────────────────────────────── */

await check("the PC's words survive, and the phone's row is left out", async () => {
  const v = normaliseLimits(VIEW);
  assert.equal(v.available, true);
  assert.deepEqual(v.rows.map((r) => r.key), ["undo_window", "jobs_per_tick"]);
  assert.equal(v.rows[0].words, "keep undo for a day");
  assert.deepEqual(v.rows[0].choices, [1, 24, 168]);
  assert.equal(v.rows[1].pcOnly, true, "a PC-only row is offered here - this page IS the PC");
  // A row with no `app` is one both may change: the PC keeps it.
  assert.deepEqual(normaliseLimits({ limits: [{ key: "k", kind: "int", value: 1 }] }).rows.map((r) => r.key), ["k"]);
});

await check("an older PC, and nonsense, are both read safely", async () => {
  const old = normaliseLimits({ available: false, why: "run apply-patches.ps1" });
  assert.equal(old.available, false);
  assert.equal(old.why, "run apply-patches.ps1");
  assert.deepEqual(old.rows, []);
  assert.equal(normaliseLimits(null).rows.length, 0);
  assert.equal(normaliseLimits({ limits: "nope" }).rows.length, 0);
  // A row with no key is not a control.
  assert.equal(normaliseLimits({ limits: [{ kind: "int", value: 3 }] }).rows.length, 0);
});

await check("a step moves one step and stops at the PC's own ends", async () => {
  const [choice, stepper] = normaliseLimits(VIEW).rows;
  assert.equal(stepped(choice, 1), 168, "a choice row steps to the next choice, not to 25");
  assert.equal(stepped(choice, -1), 1);
  const top = { ...choice, value: 168 };
  assert.equal(stepped(top, 1), null, "nowhere above the last choice");
  assert.equal(stepped(stepper, 1), 5);
  assert.equal(stepped({ ...stepper, value: 16 }, 1), null, "the PC's high");
  assert.equal(stepped({ ...stepper, value: 1 }, -1), null, "the PC's low");
  // A value between two choices steps to the next one the PC offers.
  assert.equal(stepped({ ...choice, value: 7 }, 1), 24);
  assert.equal(stepped({ ...choice, value: 7 }, -1), 1);
  assert.equal(stepped({ ...choice, kind: "bool" }, 1), null, "a bool has no step");
});

await check("what a control sends is the value, never a direction", async () => {
  const [choice, , bool] = VIEW.limits;
  assert.equal(valueFor(normaliseLimits(VIEW).rows[0], 168), 168);
  assert.equal(valueFor({ ...choice, kind: "bool" }, true), true);
  assert.equal(typeof valueFor(normaliseLimits(VIEW).rows[0], 24), "number");
  assert.equal(rowWords({ ...choice, kind: "bool", value: true, words: "" }), "on");
  assert.equal(rowWords({ ...choice, words: "" }), "24 hours");
});

await check("a bridge error becomes words, not JSON", async () => {
  assert.equal(problemWords(new Error("bad or missing X-Jarvis-Token")), "bad or missing X-Jarvis-Token");
  for (const junk of [new Error("{ \"error\": 500 }"), new Error(""), new Error("x".repeat(500)),
                      new Error("not allowed by ACL"), null]) {
    assert.match(problemWords(junk), /Try again in a moment|restart Jarvis Desktop/);
  }
});

/* ── Settings ─────────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();

function limitsBridge(data = {}) {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__limitCalls = [];
  window.__limitView = data.view === "old" ? "old" : JSON.parse(JSON.stringify(data.view));
  window.__limitRefuse = data.refuse === true;
  core.invoke = async (cmd, args) => {
    if (cmd === "get_limits") {
      // An older PC answers "no such route" - which reach.rs/limits.rs turn
      // into the plain sentence below, with available:false.
      if (window.__limitView === "old") {
        return { available: false, why: "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC." };
      }
      return JSON.parse(JSON.stringify(window.__limitView));
    }
    if (cmd === "set_limit") {
      window.__limitCalls.push({ cmd, args: JSON.parse(JSON.stringify(args)) });
      if (window.__limitRefuse) throw new Error("Turning this up needs your approval on the PC.");
      return { ok: true, said: "Done - " + args.key + " is now " + JSON.stringify(args.value) + "." };
    }
    return invoke(cmd, args);
  };
}

async function settings(data = {}) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 2000 });
  await page.addInitScript(limitsBridge, data);
  await page.reload();
  // Wait for the card to have ANSWERED rather than for a fixed time: it paints
  // from an invoke, and on a loaded machine 700 ms was occasionally not enough,
  // which made this suite flaky (seen once, 2026-10-08). Either the rows are
  // drawn or the state line says why there are none - and "old" is the latter.
  await page
    .waitForFunction(
      () => {
        const rows = document.querySelectorAll("#limits-rows li").length;
        const state = (document.getElementById("limits-state") || {}).textContent || "";
        return rows > 0 || state.trim().length > 0;
      },
      null,
      { timeout: 15000 },
    )
    .catch(() => {});
  return page;
}

await check("Settings: one row per limit, in the PC's words", async () => {
  const page = await settings({ view: VIEW });
  const text = await page.locator("#limits").innerText();
  const keys = await page.locator("#limits-rows li").evaluateAll((els) => els.map((e) => e.dataset.limit));
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(keys, ["undo_window", "jobs_per_tick"]);
  assert.ok(text.includes("How long you can undo - keep undo for a day"));
  assert.ok(text.includes("A longer window keeps older copies of your files on this PC."));
  assert.ok(text.includes("Turning a number down changes at once"), "the one plain line about asks");
  assert.deepEqual(errors, []);
});

/** Waits until `fn` is true in the page. If it never is, the assertion below says why. */
async function settled(page, fn, timeout = 10000) {
  await page.waitForFunction(fn, null, { timeout }).catch(() => {});
}

await check("Settings: a choice sends that choice, and a bool sends the other way", async () => {
  const page = await settings({ view: VIEW });
  await page.locator('#limits-rows li[data-limit="undo_window"] button', { hasText: "168" }).click();
  await settled(page, () => (window.__limitCalls || []).length > 0);
  const calls = await page.evaluate(() => window.__limitCalls);
  assert.deepEqual(calls, [{ cmd: "set_limit", args: { key: "undo_window", value: 168 } }]);
  await page.close();

  const on = await settings({ view: { limits: [{ key: "memory_people", title: "Look for people",
    kind: "bool", value: false, words: "off", choices: [], low: 0, high: 0, unit: "", note: "",
    loosen_up: true, pc_only: false, app: "both" }] } });
  await on.locator('#limits-rows li[data-limit="memory_people"] button').click();
  await settled(on, () => (window.__limitCalls || []).length > 0);
  const boolCalls = await on.evaluate(() => window.__limitCalls);
  await on.close();
  assert.deepEqual(boolCalls, [{ cmd: "set_limit", args: { key: "memory_people", value: true } }]);
});

await check("Settings: the PC's refusal is shown in its own words", async () => {
  const page = await settings({ view: VIEW, refuse: true });
  await page.locator('#limits-rows li[data-limit="undo_window"] button', { hasText: "168" }).click();
  // The note says "Saving…" first and the PC's sentence last, and the re-read
  // after an answer must not wipe it - so wait for a note that is neither empty
  // nor still saving.
  await settled(page, () => {
    const said = ((document.getElementById("limits-note") || {}).textContent || "").trim();
    return said.length > 0 && said !== "Saving…";
  });
  const note = await page.locator("#limits-note").innerText();
  await page.close();
  assert.equal(note, "Turning this up needs your approval on the PC.");
});

await check("Settings: an older PC says what to do, and the list stays hidden", async () => {
  const page = await settings({ view: "old" });
  const state = await page.locator("#limits-state").innerText();
  const hidden = await page.locator("#limits-body").isHidden();
  await page.close();
  assert.match(state, /apply-patches\.ps1/);
  assert.equal(hidden, true);
});

await browser.close();
close();

/* ── CONTROL ───────────────────────────────────────────────────────────── */

await check("CONTROL: both commands sit with Settings only, read GET / write POST", async () => {
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]");
  const settingsSet = sets.find((s) => s.includes('identifier = "settings-surface"'));
  for (const perm of ['"allow-get-limits"', '"allow-set-limit"']) {
    assert.ok(settingsSet.includes(perm), perm);
    assert.equal(sets.filter((s) => s.includes(perm)).length, 1, `${perm} is granted once`);
  }
  const build = read("src-tauri/build.rs");
  assert.ok(build.includes('"get_limits"') && build.includes('"set_limit"'));
  const rs = read("src-tauri/src/limits.rs");
  assert.match(rs, /\.get\(format!\("\{base\}\{LIMITS_PATH\}"\)\)/);
  assert.match(rs, /\.post\(format!\("\{base\}\{LIMITS_SET_PATH\}"\)\)/);
  // The page never sends a direction: the ONE call it makes carries a key and
  // a value, and the value comes from the control's own reading of the row.
  const js = read("src/limits-settings.js");
  assert.match(js, /invoke\("set_limit", \{ key: limit\.key, value: valueFor\(limit, value\) \}\)/);
  const sends = js.match(/invoke\("set_limit"[^\n]*/g) || [];
  assert.equal(sends.length, 1, "one call, in one place");
  assert.doesNotMatch(sends[0], /loosen|raise|lower|direction|dir\b/i);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nLimits and frequency: the PC's words, one value at a time, asks before more");
