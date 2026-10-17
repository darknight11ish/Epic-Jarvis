/**
 * Every desktop window's commands must go through ONE budget (2026-10-16).
 *
 * WHY THIS SUITE EXISTS. The owner pressed "Pair a phone" in Settings and the
 * section froze for ever. The cause was general: `devices.js` awaited
 * `TAURI.core.invoke` with no budget, so a command that never settled left its
 * `busy` flag true, `paint()` kept every control disabled, and the section said
 * nothing. `settings.js` had a budget - a private `OPEN_READS` set only its own
 * `invoke()` could use - and 100 call sites across 39 files had none at all.
 *
 * THE FIX THIS PINS: one shared module, `src/invoke-budget.js`, that every
 * window can import: a budget per class (30 s for a small backend call, 120 s
 * when the network is the wait, 15 min for a command that copies data or waits
 * on an approval card) and TWO sentences, because a late read and a late action
 * are not the same claim - Rust does not cancel a command, so a late action may
 * genuinely have happened and "it failed" would be a lie.
 *
 * WHAT IT DRIVES: the real `src/settings.html` through `tests/uikit.mjs`, with
 * `pair_start` wrapped so it never settles, and the window's own words for a
 * late action read off the real page. Then the CONTROL - the same card with
 * `pair_start` answering - because a suite that only ever sees one side cannot
 * tell "the fix works" from "the card is broken".
 *
 * Run by hand (it waits out a real 30 s budget, the way
 * `settings-open-budget.mjs` does); CI's frontend job runs every tests/*.mjs,
 * so it is in CI too:
 *
 *     node tests/invoke-budget.mjs [budgetSeconds]
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import * as B from "../src/invoke-budget.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
/** Above READ_BUDGET_MS (30 s) in src/invoke-budget.js, plus room to poll. */
const BUDGET_S = Number(process.argv[2] || 40);

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── the module: the budgets, and the two different claims ─────────────── */

await check("a small backend call gets 30 s, whether it is a read or an action", async () => {
  assert.equal(B.budgetFor("devices_list", "read"), 30_000);
  assert.equal(B.budgetFor("pair_start", "action"), 30_000);
});

await check("the network gets longer, and data work gets longer still", async () => {
  assert.ok(B.budgetFor("check_tool_updates") > B.READ_BUDGET_MS,
    "a network check is bounded like a loopback read");
  for (const cmd of ["backup_now", "restore_backup", "delete_older_backups", "set_backup_folder"]) {
    assert.ok(B.budgetFor(cmd, "action") >= 600_000,
      `${cmd} is bounded like a status read - it copies data or waits on a card`);
  }
});

await check("a late READ and a late ACTION are different claims", async () => {
  assert.notEqual(B.LATE_READ, B.LATE_ACTION);
  assert.match(B.LATE_READ, /out of date/i, "a late read must say the part is out of date");
  assert.match(B.LATE_ACTION, /not known whether it happened/i,
    "a late action must say it is not known - never that it failed");
  assert.doesNotMatch(B.LATE_ACTION, /\bfailed\b|did not work/i,
    "a late action claims the work failed, which cannot be known");
  for (const words of [B.LATE_READ, B.LATE_ACTION]) {
    assert.doesNotMatch(words, /[{}<>]|::|undefined|null/i, words);
    assert.ok(words.length <= 400, "too long for problemWords() to pass on");
  }
});

await check("a command that never answers rejects with those words, and stops waiting", async () => {
  const started = Date.now();
  await assert.rejects(
    () => B.withBudget(new Promise(() => {}), { ms: 60, late: B.LATE_ACTION }),
    (e) => e.message === B.LATE_ACTION);
  assert.ok(Date.now() - started < 2_000, "the budget did not fire promptly");
});

await check("... and a command that DOES answer is not touched", async () => {
  assert.equal(await B.withBudget(Promise.resolve("the answer")), "the answer");
});

/* ── the one shared door: no card reaches the bridge on its own ────────── */

await check("no converted card calls TAURI.core.invoke itself any more", async () => {
  // A source pin, so reverting one file fails fast and names it.
  const converted = ["devices.js"];
  for (const f of converted) {
    const text = readFileSync(join(SRC, f), "utf8");
    const hits = [...text.matchAll(/TAURI\.core\.invoke\(/g)];
    assert.equal(hits.length, 0, `${f} still reaches the bridge directly ${hits.length} time(s)`);
    assert.match(text, /from "\.\/invoke-budget\.js"/, `${f} does not import the shared budget`);
  }
});

await check("the shared module is the ONLY place that reaches the bridge", async () => {
  const files = readdirSync(SRC).filter((f) => f.endsWith(".js"));
  const offenders = files.filter((f) => f !== "invoke-budget.js"
    && /TAURI\.core\.invoke\(/.test(readFileSync(join(SRC, f), "utf8")));
  // Not a rule yet - the sweep is a first slice. This prints the remaining
  // inventory so the next PR has an exact list instead of a grep.
  console.log(`      ${offenders.length} file(s) still to convert: ${offenders.length > 12 ? offenders.length + " files" : offenders.join(", ")}`);
  assert.ok(!offenders.includes("devices.js"), "devices.js is back on the raw bridge");
});

/* ── the real page: a pairing request that never answers ───────────────── */

async function open({ hang }) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1200 });
  await page.addInitScript((hang) => {
    const wrap = () => {
      const core = window.__TAURI__ && window.__TAURI__.core;
      if (!core) return false;
      const real = core.invoke.bind(core);
      window.__pairStartCalls = 0;
      core.invoke = (cmd, args) => {
        if (cmd === "devices_list") {
          return Promise.resolve({ devices: [], shared_retired: false, live: true });
        }
        if (cmd === "pair_phone_address") {
          return Promise.resolve({ address: "my-pc.tail1234.ts.net", known: true });
        }
        if (cmd === "pair_start") {
          window.__pairStartCalls += 1;
          if (hang) return new Promise(() => {}); // accepted, never answered
        }
        return real(cmd, args);
      };
      return true;
    };
    if (!wrap()) {
      const iv = setInterval(() => { if (wrap()) clearInterval(iv); }, 1);
    }
  }, hang);
  await page.reload();
  await page.waitForTimeout(2500);
  await page.evaluate(() => {
    for (const d of document.querySelectorAll("details")) d.open = true;
  });
  await page.evaluate(() => {
    const el = document.querySelector("#dv-address");
    if (el) el.value = "my-pc.tail1234.ts.net";
  });
  const pair = page.locator("#dv-pair");
  await pair.scrollIntoViewIfNeeded();
  await pair.click({ force: true });
  return page;
}

const stateOf = (page) => page.evaluate(() => ({
  calls: window.__pairStartCalls,
  status: ((document.querySelector("#dv-pair-status") || {}).textContent || "").trim(),
  pairDisabled: Boolean(document.querySelector("#dv-pair").disabled),
}));

const hung = await open({ hang: true });
await new Promise((r) => setTimeout(r, BUDGET_S * 1000));
const stuck = await stateOf(hung);
await hung.close();

await check(`after ${BUDGET_S}s with no answer, the card is not still saying it is asking`, async () => {
  assert.equal(stuck.calls, 1, "pair_start was never called - the click did not reach the card");
  assert.doesNotMatch(stuck.status, /Asking your PC for a code/,
    `still saying it is asking after ${BUDGET_S}s: ${stuck.status}`);
  assert.equal(stuck.status, B.LATE_ACTION, `the card said something else: ${stuck.status}`);
});

await check("... and the controls came back", async () => {
  assert.equal(stuck.pairDisabled, false, "Pair a phone is still disabled - the section is dead");
});

const answered = await open({ hang: false });
await new Promise((r) => setTimeout(r, 3000));
const fine = await stateOf(answered);
await answered.close();

await check("CONTROL: the same card, with pair_start answering, is not stuck", async () => {
  assert.ok(fine.calls > 0, "CONTROL FAILED: the control never called pair_start");
  assert.equal(fine.pairDisabled, false,
    "CONTROL FAILED: the card is broken even when the PC answers, so this proves nothing");
});

await browser.close(); close();
console.log(fails.length ? `\n${fails.length} FAILED`
  : "\none budget for every command, and a late action does not claim it failed");
process.exit(fails.length ? 1 : 0);
