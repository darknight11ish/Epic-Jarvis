/**
 * Settings -> "Let Jarvis Desktop start and stop Jarvis": a failed Save must
 * not leave the tick saying something the PC is not doing (2026-11-19
 * state-drift).
 *
 *   node tests/settings-supervise.mjs
 *
 * WHY THIS EXISTS. DESKTOP-STATE-DRIFT.md section 3.5 (MISMATCH-WIDGET): the
 * back-end card paints its sentence from `supervisor_status` every 5 s, but the
 * checkbox was only ever painted when `fields: true` - the first load. So a
 * REFUSED or failed save left the owner with a TICKED box and, directly under
 * it, "Jarvis Desktop is not managing Jarvis. It will not start or stop it."
 * The autostart row right below it was the model (it re-reads on a failed
 * write); the supervision save now repaints the tick from the same store read
 * that paints the words.
 *
 * This opens the REAL settings.html in the shared headless-Chromium harness
 * with a fake PC whose store says "not supervising" and whose `set_supervision`
 * refuses, then drives the owner's own two clicks:
 *
 *   1. at load: box unticked, words say it is not managing;
 *   2. tick the box and press Save -> the save is refused; the box must fall
 *      back to the STORE's value (unticked) while the words still say the PC
 *      is not managing - the two may not disagree;
 *   3. the page reports no errors.
 *
 * Run by CI's frontend shards (`tests/*.mjs`).
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();

/** commands.rs `supervisor_status`, with the store saying NOT supervising. */
const SUPERVISOR_OFF = {
  supervise: false,
  owned: false,
  configured: true,
  pid: null,
  uptime_seconds: 0,
  launcher_exited: false,
  base: "http://127.0.0.1:4719",
  backend: {
    program: "C:\\Python312\\python.exe",
    args: ["C:\\Jarvis\\jarvis_hud.py"],
    cwd: "C:\\Jarvis",
  },
};

const openSettings = async () => {
  const page = await K.open(browser, base, "settings.html", {
    supervisor: SUPERVISOR_OFF,
    // The PC refuses the supervision change: the audit's failed-Save case.
    invokeFails: { set_supervision: "The PC refused that change." },
  }, { width: 900, height: 1600 });
  await page.waitForFunction(() => {
    const line = document.getElementById("backend-state");
    return Boolean(line && /not managing/.test(line.textContent || ""));
  }, { timeout: 10000 });
  return page;
};

const card = (page) => page.evaluate(() => ({
  ticked: Boolean(document.getElementById("supervise")?.checked),
  state: (document.getElementById("backend-state") || {}).textContent || "",
  said: (document.getElementById("backend-status") || {}).textContent || "",
}));

test("at load the tick is the store's value, and the words agree", async () => {
  const page = await openSettings();
  try {
    const before = await card(page);
    assert.equal(before.ticked, false, "the store says not supervising and the box was ticked");
    assert.match(before.state, /not managing/);
    assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  } finally {
    await page.close();
  }
});

test("a refused Save leaves the tick on the STORE's value, never the click's", async () => {
  const page = await openSettings();
  try {
    // The owner ticks "Let Jarvis Desktop start and stop Jarvis" and presses
    // Save. The PC refuses the change, and its store still says not managing.
    await page.evaluate(() => {
      const box = document.getElementById("supervise");
      box.checked = true;
      box.dispatchEvent(new Event("change", { bubbles: true }));
      document.getElementById("save-backend").click();
    });
    await page.waitForFunction(() => {
      const said = document.getElementById("backend-status");
      return Boolean(said && /refused that change/.test(said.textContent || ""));
    }, { timeout: 8000 });
    await page.waitForTimeout(300);
    const after = await card(page);
    assert.match(after.said, /refused that change/, "the PC's refusal is not on screen");
    assert.equal(after.ticked, false,
      "the refused save left the box ticked - the audit's ticked box beside 'not managing'");
    assert.match(after.state, /not managing/,
      "the words stopped saying what the store says");
    assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  } finally {
    await page.close();
  }
});

test.after(async () => {
  await browser.close();
  close();
});
