/**
 * "Update both halves" — one control, two halves, and the two rules it must
 * never break.
 *
 * The owner asked for this directly (2026-10-13): one Update control that
 * updates the desktop program AND the Python backend. Before it, the backend
 * moved only by hand — `scripts/apply-patches.ps1` in a PowerShell window —
 * and about eighty sentences in the app said "run apply-patches.ps1 on the PC"
 * whenever the two had drifted apart.
 *
 * Two things here are load-bearing, and everything else is wording:
 *
 * 1. **Nothing runs without a press, and the press asks first.** Two halves in
 *    one go is a bigger thing than either half: the backend step writes into
 *    the folder Jarvis runs from. `a press asks before anything runs` and
 *    `cancelling changes nothing` are the two checks that hold that, and the
 *    question's own words are read rather than assumed.
 *
 * 2. **A half that did not finish is never painted as done.** This project's
 *    rule is that BLOCKED is never a pass, so `a backend that did not finish is
 *    NOT reported as updated` and `patched-but-unproven is not a clean update`
 *    drive the page with Rust's own failure shapes and read what it says.
 *
 * The order itself lives in Rust (`update.rs`'s `update_both`), because a page
 * that called three commands could get it wrong in a later edit. That is why
 * two checks here read the Rust source instead of driving the page — the same
 * shape `updates.mjs` already uses for "Rust keeps checking and installing as
 * separate commands".
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1100 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const calls = (page) => page.evaluate(() => window.__calls.map((c) => c[0]));

/** Opens the card, accepts the question, and hands back the question's text. */
async function pressYes(page) {
  const asked = [];
  page.on("dialog", (dialog) => {
    asked.push(dialog.message());
    dialog.accept();
  });
  await page.locator("#ub-go").click();
  await page.waitForTimeout(400);
  return asked;
}

const UB = K.UPDATE_BOTH;

/* ── It asks first, and says what will happen ────────────────────────────── */

await check("opening the card runs nothing", async () => {
  // The card reads where the two folders are. That read must not become a run:
  // this is the "never automatic" rule at its smallest.
  const page = await open();
  await page.waitForTimeout(600);
  const seen = await calls(page);
  await page.close();
  assert.ok(seen.includes("backend_update_status"), "the card never asked where the folders are");
  assert.ok(!seen.includes("__updatedBoth"),
    "opening Settings started an update — this is the one thing that must never happen");
  assert.ok(!seen.includes("__installed"), "opening Settings installed the desktop half");
});

await check("a press asks before anything runs, and cancelling changes nothing", async () => {
  // Playwright dismisses a dialog by default, which is exactly the Cancel
  // path. Nothing may have run when the question comes back "no".
  const page = await open();
  await page.waitForTimeout(300);
  await page.locator("#ub-go").click();
  await page.waitForTimeout(400);
  const seen = await calls(page);
  const status = await page.locator("#ub-status").innerText();
  await page.close();
  assert.ok(!seen.includes("__updatedBoth"), "cancelling still ran the update");
  assert.ok(!seen.includes("__installed"), "cancelling still installed the desktop half");
  assert.match(status, /Cancelled/i, `said "${status}"`);
  assert.match(status, /[Nn]othing was changed/, `said "${status}"`);
});

await check("the question says exactly what will happen", async () => {
  // Every fact the run makes true is in the question, so nobody finds out
  // afterwards: the folder that gets written into, the backup that is kept
  // first, the stop, and which half goes first.
  const page = await open();
  await page.waitForTimeout(300);
  const asked = await pressYes(page);
  await page.close();
  assert.equal(asked.length, 1, `${asked.length} dialogs, expected exactly one`);
  const q = asked[0];
  assert.match(q, /Update both halves/i, q);
  // The backend folder itself, by path — not "your backend folder".
  assert.ok(q.includes(UB.where.backend), `the question does not name the folder: ${q}`);
  // ...and that it is the folder Jarvis runs from, and that a backup is kept.
  assert.match(q, /folder Jarvis runs from/i, q);
  assert.match(q, /_jarvis-backup-<date>/, q);
  // ...and the signed half.
  assert.match(q, /signing key/i, q);
  // ...and the order, and what happens if the first half fails.
  assert.match(q, /backend goes first/i, q);
  assert.match(q, /NOT\s+updated/i, q);
  // ...and that it is not automatic.
  assert.match(q, /Nothing happens on its own/i, q);
});

/* ── A half that did not finish is not a pass ────────────────────────────── */

await check("CONTROL: both halves ok does read as updated, so the negatives mean something", async () => {
  const page = await open({ updateBoth: { outcome: UB.bothOk } });
  await page.waitForTimeout(300);
  const asked = await pressYes(page);
  assert.equal(asked.length, 1, "the control press never asked");
  const state = await page.locator("#ub-state").innerText();
  const tone = await page.locator("#ub-state").getAttribute("data-tone");
  const rows = await page.locator("#ub-steps li").count();
  await page.close();
  assert.match(state, /Both halves are updated/i, `said "${state}"`);
  assert.equal(tone, "ok", "a fully successful run is not painted as one");
  assert.equal(rows, 2, `${rows} rows for a two-half run`);
});

await check("a backend that did not finish is NOT reported as updated", async () => {
  const page = await open({ updateBoth: { outcome: UB.backendRefused } });
  await page.waitForTimeout(300);
  await pressYes(page);
  const state = await page.locator("#ub-state").innerText();
  const tone = await page.locator("#ub-state").getAttribute("data-tone");
  const rows = await page.locator("#ub-steps").innerText();
  const seen = await calls(page);
  await page.close();
  assert.doesNotMatch(state, /Both halves are updated/i, `said "${state}"`);
  assert.equal(tone, "bad", "a failed run is not painted as bad");
  // The desktop half is present and says it was NOT installed — never left out,
  // which would leave one green-ish row where two things were promised.
  assert.match(rows, /Not installed/, rows);
  assert.match(rows, /The backend/, rows);
  // ...and the app's own half was not attempted at all (Rust does that; the
  // stub records only that update_both was called).
  assert.ok(seen.includes("__updatedBoth"), "the run never started");
  assert.ok(!seen.includes("__installed"), "a second install happened outside the one command");
});

await check("patched-but-unproven is not a clean update", async () => {
  // The project's rule, in the one place a feature could quietly break it: the
  // backend IS patched, and the patch program could not prove its checks. That
  // is `partial`, and `partial` is not a pass.
  const page = await open({ updateBoth: { outcome: UB.patchedUnproven } });
  await page.waitForTimeout(300);
  await pressYes(page);
  const state = await page.locator("#ub-state").innerText();
  const tone = await page.locator("#ub-state").getAttribute("data-tone");
  await page.close();
  assert.doesNotMatch(state, /Both halves are updated/i, `said "${state}"`);
  assert.match(state, /NOT proven/i, `said "${state}"`);
  assert.equal(tone, "bad", "an unproven update is painted as a clean one");
});

await check("a refusal is refused BEFORE the question, not after", async () => {
  // With no program folder the button is not offered at all, and the refusal
  // says which box to fill in. A button that asked first and refused after
  // would have taught the owner to press it anyway.
  const page = await open({ updateBoth: { where: UB.notTold } });
  await page.waitForTimeout(400);
  const disabled = await page.locator("#ub-go").isDisabled();
  const state = await page.locator("#ub-state").innerText();
  const found = await page.locator("#ub-found").innerText();
  const seen = await calls(page);
  await page.close();
  assert.equal(disabled, true, "a run that cannot work is still offered");
  assert.match(state, /Cannot update the backend on this PC yet/i, `said "${state}"`);
  assert.match(found, /does not know where the Jarvis program folder is/i, `said "${found}"`);
  assert.match(found, /Nothing was changed/, `said "${found}"`);
  assert.ok(!seen.includes("__updatedBoth"), "a refused run still ran");
});

await check("the command refusing outright never reads as an update", async () => {
  // The one case Rust answers with an error rather than an outcome: a build
  // with no update key. The page must say so and must not paint either half.
  const page = await open({
    updateBoth: { fails: "this build has no update key, so it cannot verify a download" },
  });
  await page.waitForTimeout(300);
  await pressYes(page);
  const state = await page.locator("#ub-state").innerText();
  const tone = await page.locator("#ub-state").getAttribute("data-tone");
  await page.close();
  assert.match(state, /no update key/i, `said "${state}"`);
  assert.equal(tone, "bad", "a refused update is painted as a good one");
});

/* ── The two folders ────────────────────────────────────────────────────── */

await check("the card says where each folder was read from, rather than implying it", async () => {
  const page = await open();
  await page.waitForTimeout(300);
  const found = await page.locator("#ub-found").innerText();
  await page.close();
  assert.ok(found.includes(UB.where.backend), `did not name the backend folder: ${found}`);
  assert.match(found, /read from the folder this app starts Jarvis from/, found);
  assert.ok(found.includes("apply-patches.ps1"), `did not name the patch program: ${found}`);
});

await check("saving the two folders sends exactly what was typed", async () => {
  const page = await open();
  await page.waitForTimeout(300);
  await page.fill("#ub-repo", "D:\\Jarvis");
  await page.fill("#ub-backend", "D:\\Jarvis-backend");
  await page.locator("#ub-save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() => window.__ubSaved || []);
  const status = await page.locator("#ub-save-status").innerText();
  await page.close();
  assert.deepEqual(saved, [{ repo: "D:\\Jarvis", backend: "D:\\Jarvis-backend" }]);
  assert.match(status, /Saved/i, `said "${status}"`);
});

await check("an empty backend box means \"not said\", not the empty folder", async () => {
  const page = await open();
  await page.waitForTimeout(300);
  await page.fill("#ub-backend", "   ");
  await page.locator("#ub-save").click();
  await page.waitForTimeout(300);
  const saved = await page.evaluate(() => window.__ubSaved || []);
  await page.close();
  assert.deepEqual(saved, [{ repo: UB.where.repo, backend: "" }],
    "a box left blank was sent as something else");
});

/* ── The two things only the Rust source can hold ────────────────────────── */

await check("CONTROL: the order is one command in Rust, backend before executable", async () => {
  const rust = read("src-tauri/src/update.rs");
  const fn = rust.slice(rust.indexOf("pub async fn update_both"));
  assert.ok(fn, "there is no update_both command");
  const backendAt = fn.indexOf("backend_update::run");
  const stopAt = fn.indexOf("// STOP.");
  const installAt = fn.indexOf("install_now(&app)");
  assert.ok(backendAt >= 0, "update_both never runs the backend half");
  assert.ok(installAt >= 0, "update_both never runs the desktop half");
  assert.ok(backendAt < installAt,
    "the executable is replaced before the backend is patched — the order this feature chose is the other way round");
  // The desktop half sits after the early return, so a backend that did not
  // finish cannot reach it. This is the rule, read off the source rather than
  // off a comment: `stopAt` is the `if !backend_ok` block.
  assert.ok(stopAt >= 0 && stopAt < installAt,
    "the desktop half is not guarded by the backend half's result");
  assert.match(fn.slice(stopAt, installAt), /return Ok\(BothOutcome/,
    "the guard does not return before the desktop half");
});

await check("CONTROL: only one boolean may be painted green, and it needs both halves", async () => {
  const rust = read("src-tauri/src/update.rs");
  const fn = rust.slice(rust.indexOf("pub fn both_updated"));
  assert.match(fn, /steps\.iter\(\)\.all\(\|s\| s\.state == "ok"\)/,
    "both_updated no longer requires every step to be ok");
  const js = read("src/settings.js");
  assert.match(js, /outcome && outcome\.updatedBoth/,
    "the page paints from something other than Rust's own updatedBoth");
  // ...and the page never decides for itself that a run succeeded.
  assert.doesNotMatch(js, /state === "ok"\s*&&\s*[\s\S]{0,80}Both halves are updated/,
    "the page is deciding what counts as an update");
});

await check("CONTROL: nothing but the button can start it", async () => {
  const js = read("src/settings.js");
  assert.equal((js.match(/invoke\("update_both"\)/g) || []).length, 1,
    "update_both is invoked from more than one place");
  // The one call site is inside runBoth, and runBoth is only reached through
  // the question. If either of those changes, the ask stops being the gate.
  const runAt = js.indexOf("async function runBoth()");
  const callAt = js.indexOf('invoke("update_both")');
  assert.ok(runAt >= 0 && callAt > runAt, "update_both is called from outside runBoth");
  const runFn = js.slice(runAt, js.indexOf("if (dom.ubGo)"));
  assert.doesNotMatch(runFn, /setInterval|setTimeout/,
    "runBoth schedules itself — an update must never come back on a timer");
  const clickAt = js.indexOf("dom.ubGo.addEventListener");
  assert.ok(clickAt >= 0, "the button has no handler");
  assert.match(js.slice(clickAt, clickAt + 700), /window\.confirm\(ubQuestion/,
    "the button runs the update without asking first");
});

await check("CONTROL: the two cards are not the same feature, and this one adds no route", async () => {
  // "Check for tool updates" is a report that never installs anything; this one
  // installs. Merging them is the mistake the brief warns about, so the two
  // sections stay apart and the read-only one stays unable to run a program.
  const html = read("src/settings.html");
  assert.match(html, /id="tool-updates"/);
  assert.match(html, /id="update-both"/);
  const tools = read("src-tauri/src/tool_updates.rs");
  assert.doesNotMatch(tools, /std::process::Command|Command::new/,
    "the read-only tool-updates report has grown a way to run a program");
  // This feature adds NO backend route — that is what makes the phone's half a
  // decision rather than an omission, and what leaves tools/check_parity.py
  // nothing to classify. Held here so a later edit cannot quietly grow one.
  const backend = read("src-tauri/src/backend_update.rs");
  assert.doesNotMatch(backend, /"\/api\//,
    "the backend updater has grown an HTTP route, which the phone would then have to be offered");
});

/* ── The stale comment the brief named ─────────────────────────────────── */

await check("the updater no longer claims it cannot update itself", async () => {
  // update.rs's own module docstring said `pubkey: ""` and "so it cannot update
  // itself at all" long after tauri.conf.json grew a real key. A comment that
  // sends the next reader looking for a bug that is not there is a defect here,
  // so it is held by a check rather than by care.
  const rust = read("src-tauri/src/update.rs");
  const doc = rust.slice(0, rust.indexOf("use serde::"));
  assert.doesNotMatch(doc, /"pubkey": ""/, "update.rs still says the public key is empty");
  assert.doesNotMatch(doc, /cannot update itself at all/i,
    "update.rs still says this build cannot update itself");
  assert.match(doc, /That key is there now/,
    "update.rs no longer says the key is configured, so a reader cannot tell");
  // ...and the fact the comment now states is the fact in the config.
  const conf = JSON.parse(read("src-tauri/tauri.conf.json"));
  assert.ok(conf.plugins.updater.pubkey.trim().length > 0,
    "the config has no pubkey, so the corrected comment is now the wrong one");
});

/* ── The phone, deliberately left out ───────────────────────────────────── */

await check("the phone is left out on purpose, in writing", async () => {
  // A phone cannot patch a PC's backend: the script, the repository and the
  // Python folder are all on the PC. There is deliberately no route, so
  // tools/check_parity.py has nothing to classify — which means the reason has
  // to live in the Architecture file or it is an oversight rather than a
  // decision.
  const arch = readRepo(join("docs", "ARCHITECTURE.md"));
  const section = arch.slice(arch.indexOf("### One-sided on purpose"),
                             arch.indexOf("## 9. Where the backend lives"));
  assert.match(section, /Update both halves|update both halves/i,
    "docs/ARCHITECTURE.md section 8 does not say why the phone has no half here");
  assert.match(section, /apply-patches\.ps1/,
    "the row does not say what the phone would have to be able to do");
});

await check("CONTROL: no page threw", async () => {
  const page = await open({ updateBoth: { outcome: UB.bothOk } });
  await page.waitForTimeout(400);
  await pressYes(page);
  await page.waitForTimeout(300);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\none press, two halves, in that order");
process.exit(fails.length ? 1 : 0);
