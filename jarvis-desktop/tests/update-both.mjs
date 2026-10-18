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

/** Opens the card, presses Update, picks a pace (the recommended one unless
 *  told otherwise), and hands back the question's text. */
async function pressYes(page, mode = "responsive") {
  const asked = [];
  page.on("dialog", (dialog) => {
    asked.push(dialog.message());
    dialog.accept();
  });
  await page.locator("#ub-go").click();
  await page.waitForTimeout(200);
  await page.locator(`#ub-mode-buttons [data-mode="${mode}"]`).click();
  await page.waitForTimeout(400);
  return asked;
}

/** The bar's width as a percentage, read off the real DOM. */
async function barPercent(page) {
  return page.evaluate(() => {
    const fill = document.getElementById("ub-progress-fill");
    return fill ? fill.style.width : "";
  });
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

await check("a press asks the pace first, and cancelling changes nothing", async () => {
  // Playwright dismisses a dialog by default, which is exactly the Cancel
  // path. Nothing may have run when the question comes back "no".
  const page = await open();
  await page.waitForTimeout(300);
  await page.locator("#ub-go").click();
  await page.waitForTimeout(200);
  const offered = await page.locator("#ub-modes").isVisible();
  await page.locator('#ub-mode-buttons [data-mode="responsive"]').click();
  await page.waitForTimeout(400);
  const seen = await calls(page);
  const status = await page.locator("#ub-status").innerText();
  await page.close();
  assert.equal(offered, true, "the press did not offer the three paces");
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
  // ...and the pace that was chosen, its worker count and its ETA range, with
  // the first-run honesty label on it. The same checks run at every pace.
  assert.match(q, /Pace: Balanced \(responsive\) - 14 checks at a time/, q);
  assert.match(q, /not measured for this pace yet/, q);
  assert.match(q, /Every pace runs the same checks/i, q);
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

/* ── Where it has got to, while it is getting there ─────────────────────── */

/** One `backend-update-progress` event, exactly as `update_progress.rs` sends
 *  it: camelCase, and `total` null while the suites run. */
const emitProgress = (page, payload) =>
  page.evaluate((p) => window.__emit("backend-update-progress", p), payload);

/** The owner's own run of 2026-10-16 (`apply-patches-2026-10-16-135737.txt`),
 *  read off his `_jarvis-logs`: four suites failed and the verdict was
 *  "DONE WITH PROBLEMS - do not trust this update yet". Three of the four were
 *  not real failures - the PC refused the check - and per that log the failing
 *  item line is a BARE `  FAIL  test_apply_outcomes.py` with no reason on it,
 *  which is why the real one here carries an empty reason. */
const REAL_PROBLEMS = {
  phase: "done", done: 0, total: null, failed: 4, skipped: 0, verdict: "problems",
  bad: [
    { name: "test_media.py", ranHere: false,
      reason: "Access is denied: the folder would not be written" },
    { name: "test_tools.py", ranHere: false,
      reason: "the run left a __pycache__ behind and read it back" },
    { name: "test_apply_outcomes.py", ranHere: true, reason: "" },
  ],
};

await check("the line says the update has started, instead of nothing, while it boots", async () => {
  // The owner's actual complaint: "if its checking anything". The patch program
  // takes about forty seconds to print its first line, and this line was BLANKED
  // at the press - so the card said nothing at all for all of it.
  const page = await open({ updateBoth: { delayMs: 1200, outcome: UB.bothOk } });
  await page.waitForTimeout(300);
  const idle = await page.locator("#ub-status").innerText();
  await pressYes(page);
  const during = await page.locator("#ub-status").innerText();
  await page.waitForTimeout(1400);
  const after = await page.locator("#ub-status").innerText();
  await page.close();
  assert.equal(idle, "", `the idle card already said "${idle}"`);
  assert.match(during, /Starting the update/, `while the run booted it said "${during}"`);
  assert.notEqual(after, during, "the run's own ending never replaced the starting line");
});

await check("every phase the updater reports becomes one line, in counts and never an invented percentage", async () => {
  const page = await open();
  await page.waitForTimeout(250);
  const line = () => page.locator("#ub-status").innerText();
  const seen = {};
  const at = { done: 0, total: null, failed: 0, skipped: 0, verdict: null, bad: [] };
  await emitProgress(page, { ...at, phase: "reading" });
  seen.reading = await line();
  await emitProgress(page, { ...at, phase: "rehearsing", done: 12, total: 145 });
  seen.rehearsing = await line();
  await emitProgress(page, { ...at, phase: "applying", done: 3, total: 145 });
  seen.applying = await line();
  // No `total` here: the tool did not say one, so the line carries the count it
  // does have and invents no denominator. The weighted bar is separate.
  await emitProgress(page, { ...at, phase: "testing", done: 7, failed: 2, skipped: 1 });
  seen.testing = await line();
  await emitProgress(page, { ...at, phase: "done", verdict: "ok" });
  seen.done = await line();
  assert.equal(seen.reading, "Working out what to update…");
  assert.equal(seen.rehearsing, "Patching the backend — 12 of 145 items");
  assert.equal(seen.applying, "Patching the backend — 3 of 145 items");
  assert.equal(seen.testing, "Checking the backend — 7 checks done, 2 failed");
  // No `total` in that event: a denominator must not appear from nowhere.
  assert.doesNotMatch(seen.testing, /%|of \d/, `a denominator was invented: ${seen.testing}`);
  assert.match(seen.done, /No problems/, seen.done);
  // ...and when the tool DOES say a total, the line says it, because it is the
  // tool's own count and not a made-up one.
  await emitProgress(page, { ...at, phase: "testing", done: 7, total: 356, failed: 2 });
  const withTotal = await line();
  await page.close();
  assert.equal(withTotal, "Checking the backend — 7 of 356 checks, 2 failed");
});

await check("an event with nothing readable in it leaves the last line standing", async () => {
  // A phase this build does not know must not put the card back to the silence
  // the whole feature exists to remove.
  const page = await open();
  await page.waitForTimeout(250);
  await emitProgress(page, { phase: "rehearsing", done: 5, total: 145, failed: 0, skipped: 0,
    verdict: null, bad: [] });
  const good = await page.locator("#ub-status").innerText();
  await emitProgress(page, { phase: "a-phase-from-a-newer-build", done: 0, total: null,
    failed: 0, skipped: 0, verdict: null, bad: [] });
  const after = await page.locator("#ub-status").innerText();
  await page.close();
  assert.match(good, /5 of 145 items/, good);
  assert.equal(after, good, "an unknown phase blanked the line");
});

await check("a run with problems is a loud list, and a check this PC refused is NOT called a failure", async () => {
  const page = await open();
  await page.waitForTimeout(250);
  await emitProgress(page, REAL_PROBLEMS);
  const box = page.locator("#ub-problems");
  const visible = await box.isVisible();
  const role = await box.getAttribute("role");
  const inFold = await box.evaluate((el) => Boolean(el.closest("details")));
  const text = await box.innerText();
  const lists = await box.locator("ul").allInnerTexts();
  const status = await page.locator("#ub-status").innerText();
  await page.close();
  assert.equal(visible, true, "a run with problems showed nothing");
  assert.equal(role, "alert", "the verdict is not a live region");
  assert.equal(inFold, false, "the verdict is inside a fold, where it is not seen");
  assert.equal(lists.length, 2, `${lists.length} lists, expected the real ones then the refused ones`);
  assert.match(lists[0], /test_apply_outcomes\.py/, lists[0]);
  assert.doesNotMatch(lists[0], /Access is denied/, "a refused check was listed as a real failure");
  assert.match(lists[1], /Access is denied: the folder would not be written/, lists[1]);
  assert.match(lists[1], /__pycache__/, lists[1]);
  assert.match(text, /1 check the patch program reported as failed/, text);
  assert.match(text, /2 checks could not run on this PC/, text);
  assert.match(status, /do not trust this update yet/i, status);
  // `failed` is the patcher's count of FAIL lines (4 here), and it is NOT used
  // to label either list: it counts things that are not one named check - the
  // script's own "335 passed, 4 failed." summary line, and a suite's inner
  // check names. It is said plainly instead of standing in for the lists.
  assert.match(text, /counted 4 failing check\(s\) in this phase; 3 of them are named above/,
    text);
});

await check("when more checks failed than the payload carries, the count says so", async () => {
  // `bad` is capped at 20 so a catastrophic run cannot grow the event; `failed`
  // is not. Reporting the smaller number as the total would be a quiet lie.
  const page = await open();
  await page.waitForTimeout(250);
  await emitProgress(page, { phase: "done", done: 0, total: null, failed: 25, skipped: 0,
    verdict: "problems",
    bad: [{ name: "test_real.py", reason: "three rows came back instead of four", ranHere: true }] });
  const text = await page.locator("#ub-problems").innerText();
  await page.close();
  assert.match(text, /^1 check the patch program reported as failed:/m, text);
  assert.match(text, /counted 25 failing check\(s\) in this phase; 1 of them are named above/, text);
});

await check("unproven is its own sentence, and never a quiet success", async () => {
  const page = await open();
  await page.waitForTimeout(250);
  await emitProgress(page, { phase: "done", done: 0, total: null, failed: 0, skipped: 0,
    verdict: "unproven", bad: [] });
  const status = await page.locator("#ub-status").innerText();
  const visible = await page.locator("#ub-problems").isVisible();
  const box = await page.locator("#ub-problems").innerText();
  await page.close();
  assert.match(status, /not proven/i, status);
  assert.equal(visible, true, "an unproven update showed nothing");
  assert.match(box, /not the same as a proven update/i, box);
});

await check("CONTROL: a clean verdict shows no problem box at all", async () => {
  // The other half of the loud verdict: if every ending raised a box, the box
  // would stop meaning anything.
  const page = await open();
  await page.waitForTimeout(250);
  await emitProgress(page, { phase: "done", done: 0, total: null, failed: 0, skipped: 0,
    verdict: "ok", bad: [] });
  const visible = await page.locator("#ub-problems").isVisible();
  const status = await page.locator("#ub-status").innerText();
  await page.close();
  assert.equal(visible, false, "an alarm was shown for a clean run");
  assert.match(status, /Done\. No problems/, status);
});

await check("the Windows-uninstall warning shows while a run is in flight and never otherwise", async () => {
  const page = await open({ updateBoth: { delayMs: 1200, outcome: UB.bothOk } });
  await page.waitForTimeout(300);
  const idle = await page.locator("#ub-fallback").isVisible();
  await pressYes(page);
  const during = await page.locator("#ub-fallback").isVisible();
  const words = await page.locator("#ub-fallback").innerText();
  await page.waitForTimeout(1400);
  const after = await page.locator("#ub-fallback").isVisible();
  await page.close();
  assert.equal(idle, false, "the warning is furniture on an idle card");
  assert.equal(during, true, "the owner was not warned while the install could ask");
  assert.equal(after, false, "the warning stayed on the card after the run");
  assert.match(words, /uninstall Jarvis/i, words);
  assert.match(words, /Click\s+Yes/i, words);
  assert.match(words, /the old copy Windows still has registered/, words);
  // NO VERSION NUMBER IN IT. It used to name one (0.2.119), which appears
  // nowhere in this repository: it was machine state, so it would be wrong on
  // any other PC and wrong for him after his next update - and the question
  // this line answers is what to click, not which version it is.
  assert.doesNotMatch(words, /\d+\.\d+\.\d+/, `the warning names a version: ${words}`);
});

await check("CONTROL: a progress event is read-only — it starts and changes nothing", async () => {
  // The whole feature is a view of a run somebody else started. This is the
  // "never automatic" rule at its smallest, and it is why the listener is
  // written beside the existing one rather than instead of it.
  const page = await open();
  await page.waitForTimeout(250);
  await emitProgress(page, REAL_PROBLEMS);
  await emitProgress(page, { phase: "testing", done: 3, total: null, failed: 0, skipped: 0,
    verdict: null, bad: [] });
  const seen = await calls(page);
  await page.close();
  assert.ok(!seen.includes("__updatedBoth"), "a progress event started an update");
  assert.ok(!seen.includes("__installed"), "a progress event installed something");
});

/* ── The three paces, chosen when Update is pressed ──────────────────────── */

await check("pressing Update offers three paces in plain words, recommends Balanced, and runs nothing", async () => {
  const page = await open();
  await page.waitForTimeout(300);
  await page.locator("#ub-go").click();
  await page.waitForTimeout(250);
  const shown = await page.locator("#ub-modes").isVisible();
  const modes = await page.locator("#ub-mode-buttons button").evaluateAll(
    (buttons) => buttons.map((button) => button.dataset.mode));
  const labels = await page.locator("#ub-mode-buttons button").allInnerTexts();
  const recommended = await page.locator('#ub-mode-buttons [data-recommended="true"]').count();
  const status = await page.locator("#ub-status").innerText();
  const seen = await calls(page);
  await page.locator("#ub-mode-cancel").click();
  await page.waitForTimeout(200);
  const hidden = await page.locator("#ub-modes").isVisible();
  const cancelled = await page.locator("#ub-status").innerText();
  await page.close();
  assert.equal(shown, true, "the press did not offer the three paces");
  assert.deepEqual(modes, ["max_speed", "responsive", "safe"], `${modes}`);
  assert.equal(recommended, 1, `${recommended} recommended buttons, expected exactly one`);
  assert.match(labels[1] || "", /Balanced \(recommended\)/i, labels.join(" | "));
  // Each pace is plain words + an ETA RANGE + honest labelling of the source.
  labels.forEach((text) => {
    assert.match(text, /not measured for this pace yet/, `a pace did not label its estimate: ${text}`);
    // A RANGE, not one invented number: "about 1 minute to 5 minutes".
    assert.match(text, /about \d+ (second|minute)s? to \d+ (second|minute)s?/,
      `a pace did not give a range: ${text}`);
  });
  assert.match(status, /Choose how hard/i, status);
  assert.ok(!seen.includes("__updatedBoth"), "offering the paces started a run");
  assert.equal(hidden, false, "Cancel left the pace card on screen");
  assert.match(cancelled, /Cancelled/, `Cancel said "${cancelled}"`);
});

await check("choosing a pace sends EXACTLY that pace, and the question names it", async () => {
  for (const mode of ["max_speed", "safe"]) {
    const page = await open();
    await page.waitForTimeout(250);
    const asked = await pressYes(page, mode);
    const sent = await page.evaluate(() => window.__updatedMode);
    await page.close();
    assert.equal(sent, mode, `sent ${sent === undefined ? "nothing" : sent} for ${mode}`);
    assert.equal(asked.length, 1, `${asked.length} questions for ${mode}`);
    const title = mode === "safe" ? /Safest \(safe\)/ : /Fastest \(max_speed\)/;
    assert.match(asked[0], title, asked[0]);
    assert.match(asked[0], /at a time/, asked[0]);
    assert.match(asked[0], /Every pace runs the same checks/i, asked[0]);
  }
});

await check("a measured pace says where its numbers came from, instead of pretending it is new", async () => {
  const measured = UB.where.modes.map((row) => ({ ...row, measured: true,
    etaSeconds: 100, etaLowSeconds: 80, etaHighSeconds: 120 }));
  const page = await open({ updateBoth: { where: { ...UB.where, modes: measured } } });
  await page.waitForTimeout(300);
  await page.locator("#ub-go").click();
  await page.waitForTimeout(200);
  const labels = await page.locator("#ub-mode-buttons button").allInnerTexts();
  await page.close();
  labels.forEach((text) => {
    assert.match(text, /from this PC's own times/, `a measured pace hid its source: ${text}`);
    assert.doesNotMatch(text, /not measured for this pace yet/, `a measured pace still said not measured: ${text}`);
  });
});

/* ── The bar: painted only from the tool's real events ───────────────────── */

/** One real progress event: `fraction` is the tool's completed-work share. */
async function emitBar(page, payload) {
  await emitProgress(page, payload);
  await page.waitForTimeout(60);
}

const testingAt = (fraction, extra = {}) => ({
  phase: "testing", done: 12, total: 356, failed: 0, skipped: 0, verdict: null, bad: [],
  mode: "responsive", workers: 14, measured: false, fraction,
  etaSeconds: 40, etaLowSeconds: 25, etaHighSeconds: 80, ...extra,
});

await check("the bar is hidden before any real event, then painted from the fraction's own work", async () => {
  const page = await open({ updateBoth: { delayMs: 2500, outcome: UB.bothOk } });
  await page.waitForTimeout(250);
  const beforeRun = await page.locator("#ub-progress").isVisible();
  await pressYes(page);
  const beforeEvent = await page.locator("#ub-progress").isVisible();
  await emitBar(page, testingAt(0.1));
  const ten = await barPercent(page);
  const visible = await page.locator("#ub-progress").isVisible();
  const phase = await page.locator("#ub-progress-phase").innerText();
  const count = await page.locator("#ub-progress-count").innerText();
  const eta = await page.locator("#ub-progress-eta").innerText();
  const mode = await page.locator("#ub-progress-mode").innerText();
  await page.close();
  assert.equal(beforeRun, false, "the bar is furniture on an idle card");
  assert.equal(beforeEvent, false, "the bar appeared before any real progress event");
  assert.equal(visible, true, "a real fraction event did not show the bar");
  assert.equal(ten, "10%", `the bar does not match the tool's fraction: ${ten}`);
  assert.equal(phase, "Checking the backend", phase);
  assert.equal(count, "12 of 356 checks", count);
  assert.match(eta, /left/, `the ETA is missing: ${eta}`);
  assert.match(eta, /not measured for this pace yet/, `the unmeasured-pace ETA is not labelled: ${eta}`);
  assert.match(mode, /Pace: Balanced/, mode);
  assert.match(mode, /14 checks at a time/, mode);
});

await check("the bar never goes backwards within a pass and never reaches 100% early", async () => {
  const page = await open({ updateBoth: { delayMs: 2500, outcome: UB.bothOk } });
  await page.waitForTimeout(250);
  await pressYes(page);
  await emitBar(page, testingAt(0.35));
  const first = await barPercent(page);
  await emitBar(page, testingAt(0.2));            // an out-of-order older event
  const held = await barPercent(page);
  await emitBar(page, testingAt(0.995));
  const high = await barPercent(page);
  const aria = await page.locator("#ub-progress-track").getAttribute("aria-valuenow");
  await page.close();
  assert.equal(first, "35%", first);
  assert.equal(held, "35%", `the bar went backwards: ${held}`);
  assert.equal(high, "99%", `a fraction event claimed 100%: ${high}`);
  assert.equal(aria, "99", `the accessible value does not match: ${aria}`);
});

await check("an event with no fraction holds the last real value instead of guessing", async () => {
  const page = await open({ updateBoth: { delayMs: 2500, outcome: UB.bothOk } });
  await page.waitForTimeout(250);
  await pressYes(page);
  await emitBar(page, testingAt(0.42));
  const held = await barPercent(page);
  await emitBar(page, { phase: "verifying", measured: true });   // no fraction at all
  const after = await barPercent(page);
  const phase = await page.locator("#ub-progress-phase").innerText();
  await emitBar(page, { phase: "a-phase-from-a-newer-build" });   // unknowable event
  const unknown = await barPercent(page);
  await page.close();
  assert.equal(held, "42%", held);
  assert.equal(after, "42%", `a fraction-less event moved the bar: ${after}`);
  assert.equal(unknown, "42%", `an unknown event moved the bar: ${unknown}`);
  assert.equal(phase, "Checking the patched files", phase);
});

await check("100% is painted only by the final verdict, and problems stay below it", async () => {
  const page = await open({ updateBoth: { delayMs: 2500, outcome: UB.bothOk } });
  await page.waitForTimeout(250);
  await pressYes(page);
  await emitBar(page, testingAt(0.99));
  const almost = await barPercent(page);
  await emitBar(page, { phase: "done", verdict: "ok", fraction: 1, mode: "responsive" });
  const proved = await barPercent(page);
  const aria = await page.locator("#ub-progress-track").getAttribute("aria-valuenow");
  await page.close();
  assert.equal(almost, "99%", almost);
  assert.equal(proved, "100%", "the proven end did not complete the bar");
  assert.equal(aria, "100", aria);

  const bad = await open({ updateBoth: { delayMs: 2500, outcome: UB.backendRefused } });
  await bad.waitForTimeout(250);
  await pressYes(bad);
  await emitBar(bad, testingAt(0.4));
  await emitBar(bad, { phase: "done", verdict: "problems", fraction: 1,
    mode: "responsive", failed: 1 });
  const width = await barPercent(bad);
  const tone = await bad.locator("#ub-progress").getAttribute("data-tone");
  await bad.close();
  assert.equal(width, "40%", `a failed run was painted as finished: ${width}`);
  assert.equal(tone, "bad", "a failed run's bar was not marked as bad");
});

await check("a fallback resets the bar ONLY with the visible second-pass label and a new ETA", async () => {
  const page = await open({ updateBoth: { delayMs: 2500, outcome: UB.bothOk } });
  await page.waitForTimeout(250);
  await pressYes(page);
  await emitBar(page, testingAt(0.6));
  const before = await barPercent(page);
  await emitBar(page, {
    phase: "fallback", fallback: true, fraction: 0.0, mode: "safe", workers: 1,
    measured: false, etaSeconds: 500, etaLowSeconds: 250, etaHighSeconds: 1000,
    passLabel: "second pass (safe mode)",
    note: "quick check hit a problem - re-running the safe way, new ETA. " +
      "Second pass (safe mode) started.",
  });
  const reset = await barPercent(page);
  const pass = await page.locator("#ub-progress-pass").innerText();
  const passShown = await page.locator("#ub-progress-pass").isVisible();
  const eta = await page.locator("#ub-progress-eta").innerText();
  const status = await page.locator("#ub-status").innerText();
  await emitBar(page, testingAt(0.05, { mode: "safe", workers: 1, fallback: true,
    passLabel: "second pass (safe mode)" }));
  const secondPass = await barPercent(page);
  await page.close();
  assert.equal(before, "60%", before);
  assert.equal(reset, "0%", `the fallback did not start a fresh visible pass: ${reset}`);
  assert.equal(passShown, true, "the second pass has no visible label");
  assert.match(pass, /second pass \(safe mode\)/i, pass);
  assert.match(eta, /left/, `the new pass has no ETA: ${eta}`);
  assert.match(status, /re-running the safe way/, status);
  assert.equal(secondPass, "5%", `the second pass did not count its own work: ${secondPass}`);
});

await check("the patching phase shows its own real item count on the bar", async () => {
  const page = await open({ updateBoth: { delayMs: 2500, outcome: UB.bothOk } });
  await page.waitForTimeout(250);
  await pressYes(page);
  await emitBar(page, { phase: "patching", done: 3, total: 145, failed: 0, skipped: 0,
    verdict: null, bad: [], mode: "responsive", workers: 14, measured: false,
    fraction: 0.02, etaSeconds: 90, etaLowSeconds: 60, etaHighSeconds: 200 });
  const phase = await page.locator("#ub-progress-phase").innerText();
  const count = await page.locator("#ub-progress-count").innerText();
  const width = await barPercent(page);
  await page.close();
  assert.equal(phase, "Patching the backend", phase);
  assert.equal(count, "3 of 145 items", count);
  assert.equal(width, "2%", width);
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
  // One call site, and it carries the chosen pace (2026-10-18). The exact
  // spelling is allowed to include the argument; what must not change is that
  // there is ONE of them and it lives inside runBoth.
  const callSites = (js.match(/invoke\("update_both"/g) || []).length;
  assert.equal(callSites, 1, "update_both is invoked from more than one place");
  const runAt = js.indexOf("async function runBoth(");
  const callAt = js.indexOf('invoke("update_both"');
  assert.ok(runAt >= 0 && callAt > runAt, "update_both is called from outside runBoth");
  const runFn = js.slice(runAt, js.indexOf("if (dom.ubGo)"));
  assert.doesNotMatch(runFn, /setInterval|setTimeout/,
    "runBoth schedules itself — an update must never come back on a timer");
  // The press asks for the PACE; a pace button asks the question; only the
  // answer to that question reaches runBoth.
  const clickAt = js.indexOf("dom.ubGo.addEventListener");
  assert.ok(clickAt >= 0, "the button has no handler");
  const clickHandler = js.slice(clickAt, clickAt + 400);
  assert.match(clickHandler, /showModes\(\)/,
    "the button starts without offering the three paces");
  const chooseAt = js.indexOf("function chooseMode(");
  assert.ok(chooseAt >= 0, "the pace buttons have no handler");
  const chooseFn = js.slice(chooseAt, js.indexOf("async function runBoth("));
  assert.match(chooseFn, /window\.confirm\(ubQuestion\(/,
    "a pace runs the update without asking first");
  assert.match(chooseFn, /runBoth\(row\.id\)/, "a pace does not run the pace it names");
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
