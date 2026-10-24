/**
 * "A backup was started from your phone" - the PC finishing a run the PHONE
 * started (the owner's decision of 2026-10-24).
 *
 * THE BUG THIS EXISTS FOR. The phone could always ASK for a backup, and its
 * finish call was always refused 403 `pc_only` - correctly, because the write
 * is the PC's. But nothing on the PC could finish the run either: the phone
 * showed a recovery code for a file that was never written, and its dialog
 * said "Your PC wrote the backup" before anything had been written. The owner
 * chose to let the PC finish it (`docs/AUTHENTICATION`-free, plain: the write
 * stays PC-only, the PC just gets a button).
 *
 * WHAT MUST HOLD:
 * - the block appears ONLY while `GET /api/backup` reports a run live
 *   (`prepared: {at, expires_at}`), and that read carries no code and no id;
 * - the code is TYPED, not fetched: a button reusing the code the backend
 *   still holds could write a file whose only code is on a phone screen that
 *   is already gone - the exact failure the two-call design prevents;
 * - "Write it" sends `{code}` to the EXISTING `POST /api/backup/commit` - no
 *   new route - and a refusal is the backend's own sentence, verbatim;
 * - CONTROL: no approval card, nothing automatic, and the phone's own commit
 *   is still refused - the PC-only gate is the feature, not the bug.
 *
 *     node tests/backup-phone.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const readRepo = (p) => readFileSync(join(HERE, "..", "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) {
    // Trimmed: an assertion that fails against a whole source file would
    // otherwise print the file back, which buries the actual mismatch.
    const said = String(e && e.message || e).split("\n").slice(0, 6).join("\n      ");
    fails.push(name); console.log(`FAIL  ${name}\n      ${said}`);
  }
};

/** The real code shape (four groups of five) and two real times. */
const CODE = "4F3DH-P6F4M-BXRS8-9JJT3";
const AT = 1_760_000_000;
const UNTIL = AT + 15 * 60;
const TITLE = "A backup was started from your phone";

/** `GET /api/backup` from this PC, as `view()` answers it after 2026-10-24. */
function view(extra = {}) {
  return {
    available: true,
    folder: "C:\\Users\\owner\\Backups",
    keep: 5,
    pending_delete_older_card: null,
    last_delete_older: null,
    last_backup: { ok: true, name: "jarvis-backup-20261024-030000.jbak", at: AT - 3600 },
    pending_folder_card: null,
    last_folder_card: null,
    pending_restore_card: null,
    last_restore: null,
    recovery_code_pending: false,
    erase_limit: "",
    prepared: null,
    ...extra,
  };
}

const { base, close } = await K.serve();
const browser = await K.launch();

/**
 * Settings with the Backups card driven by a scripted read.
 *
 * The bridge in `uikit.mjs` does not stub backups (no suite drove that card's
 * commands before), so this wraps `core.invoke` for the three commands this
 * slice uses and leaves every other command to the harness.
 */
async function open({ prepared, answers = [] }) {
  const page = await K.open(browser, base, "settings.html", {}, { width: 900, height: 1800 });
  const read1 = view({ prepared });
  await page.addInitScript(({ read1, answers }) => {
    const wrap = () => {
      const core = window.__TAURI__ && window.__TAURI__.core;
      if (!core) return false;
      const real = core.invoke.bind(core);
      window.__phoneCalls = [];
      window.__phoneAnswers = answers.slice();
      core.invoke = (cmd, args) => {
        if (cmd === "get_backup") return Promise.resolve(JSON.parse(JSON.stringify(read1)));
        if (cmd === "list_backups") return Promise.resolve({ backups: [] });
        if (cmd === "finish_phone_backup") {
          window.__phoneCalls.push([cmd, args]);
          const a = window.__phoneAnswers.shift();
          if (a && typeof a === "object" && a.throw) return Promise.reject(new Error(a.throw));
          return Promise.resolve(a || { ok: false, error: "no scripted answer" });
        }
        return real(cmd, args);
      };
      return true;
    };
    if (!wrap()) {
      const iv = setInterval(() => { if (wrap()) clearInterval(iv); }, 1);
    }
  }, { read1, answers });
  await page.reload();
  await page.waitForTimeout(900);
  return page;
}

/* ── the block: shown only while a run is live, and it never holds a code ── */

await check("a run the phone started is SHOWN on the PC, and says nothing is written yet",
  async () => {
    const page = await open({ prepared: { at: AT, expires_at: UNTIL } });
    const shown = await page.locator("#bk-phone").isVisible();
    const text = await page.locator("#bk-phone").innerText();
    const status = (await page.locator("#bk-status").innerText()).trim();
    const calls = await page.evaluate(() => window.__phoneCalls);
    const errors = page.__errors;
    await page.close();
    assert.equal(shown, true, "the block is hidden while a run is waiting");
    assert.ok(text.includes(TITLE), text);
    assert.ok(text.includes("Nothing has been written yet"), text);
    assert.ok(text.includes("Write it"), "the button is named in the words too");
    assert.ok(/It waits until/.test(text), `the deadline is said: ${text}`);
    assert.deepEqual(calls, [], "opening the panel must not write anything");
    assert.equal(status, "", `nothing was said before anything was pressed: ${status}`);
    assert.deepEqual(errors, [], errors.join("\n"));
  });

await check("... and no run live means no block at all - a dead run is never offered",
  async () => {
    const page = await open({ prepared: null });
    const hidden = await page.locator("#bk-phone").isHidden();
    const nowEnabled = await page.locator("#bk-now").isEnabled();
    // Not class="card" on purpose: settings-search.js's `cards()` is
    // `main .card` and its `apply()` un-hides every one of them, so a card here
    // could be shown empty by the Settings search.
    const cls = await page.locator("#bk-phone").getAttribute("class");
    const errors = page.__errors;
    await page.close();
    assert.equal(hidden, true, "the block is shown with nothing behind it");
    assert.equal(nowEnabled, true, "Back up now must be untouched by this block");
    assert.ok(!cls || !cls.split(/\s+/).includes("card"),
      `the block must not be a .card: ${cls}`);
    assert.deepEqual(errors, []);
  });

await check("the recovery code is TYPED here - the read carries no code and no run id",
  async () => {
    // This is the whole reason it is a field and not a button that reuses the
    // code the backend still holds: a file whose only code is on a phone screen
    // that is already gone is an unopenable backup, and it pushes an older one
    // out of the five kept. Typing it proves the code is in the owner's hands.
    const py = readRepo("backend/jarvis_backup.py");
    assert.match(py, /"prepared": _pending_for_reader\(\)/);
    assert.match(py,
      /return \{"at": row\.get\("at"\), "expires_at": row\.get\("expires_at"\)\}/,
      "the helper must build exactly those two fields");
    const js = read("src/backup-settings.js");
    assert.match(js, /const prepared = view\.prepared/);
    assert.ok(!/prepared\.(code|id)/.test(js), "the page must never read a code out of the view");
    // And the field itself is a plain text box with browser autofill OFF: the
    // code is not a password, and a browser must not offer to remember it.
    const page = await open({ prepared: { at: AT, expires_at: UNTIL } });
    const attrs = await page.locator("#bk-phone-code").evaluate((el) => ({
      type: el.type, autocomplete: el.autocomplete,
      spellcheck: el.getAttribute("spellcheck"),
      placeholder: el.placeholder, label: el.getAttribute("aria-label"),
    }));
    const errors = page.__errors;
    await page.close();
    assert.equal(attrs.type, "text");
    assert.equal(attrs.autocomplete, "off");
    assert.equal(attrs.spellcheck, "false");
    assert.equal(attrs.placeholder, "Recovery code");
    assert.ok(attrs.label && /recovery code/i.test(attrs.label), "the field has a name");
    assert.deepEqual(errors, []);
  });

/* ── "Write it": the existing PC-only commit, and the PC's own words back ─ */

await check("Write it sends exactly {code} to finish_phone_backup, and shows the code once",
  async () => {
    const page = await open({
      prepared: { at: AT, expires_at: UNTIL },
      answers: [{
        ok: true, name: "jarvis-backup-20261024-031500.jbak", at: AT + 60,
        counts: {}, size: 4096, folder: "Jarvis Backups", keep: 5,
        recovery_code: CODE, message: "Backed up.",
      }],
    });
    await page.locator("#bk-phone-code").fill(CODE);
    await page.locator("#bk-phone-write").click();
    await page.waitForTimeout(700);
    const calls = await page.evaluate(() => window.__phoneCalls);
    const shownCode = (await page.locator("#bk-code").innerText()).trim();
    const boxShown = await page.locator("#bk-code-box").isVisible();
    const title = (await page.locator("#bk-code-title").innerText()).trim();
    const said = (await page.locator("#bk-status").innerText()).trim();
    const errors = page.__errors;
    await page.close();
    assert.deepEqual(calls, [["finish_phone_backup", { code: CODE }]],
      "the command takes the typed code and nothing else");
    assert.equal(boxShown, true, "the code the owner kept is shown once, on the PC");
    assert.equal(shownCode, CODE);
    assert.match(title, /recovery code/i);
    assert.equal(said, "Backed up.");
    assert.deepEqual(errors, []);
  });

await check("an empty code asks for one here, without troubling the PC", async () => {
  const page = await open({ prepared: { at: AT, expires_at: UNTIL } });
  await page.locator("#bk-phone-write").click();
  await page.waitForTimeout(400);
  const calls = await page.evaluate(() => window.__phoneCalls);
  const said = (await page.locator("#bk-status").innerText()).trim();
  await page.close();
  assert.deepEqual(calls, [], "nothing was sent");
  assert.match(said, /Type the recovery code/);
});

await check("a refusal is the BACKEND'S sentence, verbatim - never a friendlier one",
  async () => {
    const gone = "That backup run has expired or was never started, so nothing was written. " +
      "Ask for a backup again from your phone.";
    const page = await open({
      prepared: { at: AT, expires_at: UNTIL },
      answers: [{ throw: gone }],
    });
    await page.locator("#bk-phone-code").fill(CODE);
    await page.locator("#bk-phone-write").click();
    await page.waitForTimeout(600);
    const said = (await page.locator("#bk-status").innerText()).trim();
    // No recovery code may be revealed by a refusal. (`#bk-code-box` itself is
    // un-hidden by settings-search.js's `apply()` on this page - a PRE-EXISTING
    // bug, `main .card` + `card.hidden = false`, and this branch does not touch
    // either file - so the check is on the code it would show, which is the
    // thing that matters and the thing this slice can be held to.)
    const codeShown = (await page.locator("#bk-code").innerText()).trim();
    const errors = page.__errors;
    await page.close();
    assert.equal(said, gone, `the PC's own words were rewritten: ${said}`);
    assert.equal(codeShown, "", "a refusal must never show a recovery code");
    assert.deepEqual(errors, []);
  });

/* ── the wire: the EXISTING route, no new one, and no card ──────────────── */

await check("CONTROL: the route is the existing PC-only commit, and it raises no card", async () => {
  const rs = read("src-tauri/src/backup.rs");
  assert.match(rs, /const COMMIT_PATH: &str = "\/api\/backup\/commit";/);
  assert.match(rs, /held_on_stale\(path: &str\) -> bool \{\s*path == FOLDER_PATH \|\| path == RESTORE_PATH \|\| path == DELETE_OLDER_PATH\s*\}/,
    "COMMIT_PATH must NOT join held_on_stale - it raises no card, like backup_now");
  assert.match(rs, /pub async fn finish_phone_backup\([\s\S]{0,400}COMMIT_PATH/);
  assert.match(rs, /finish_phone_backup[\s\S]{0,400}serde_json::json!\(\{ "code": code \}\)/,
    "the body is the code and nothing else");
  const lib = read("src-tauri/src/lib.rs");
  assert.ok(lib.includes("backup::finish_phone_backup"), "the command is registered");
  // A long budget: this copies every database the owner has, like Back up now.
  assert.match(read("src/invoke-budget.js"), /"finish_phone_backup",/);
  // The phone's own commit is still refused; that refusal is the feature.
  const py = readRepo("backend/jarvis_backup.py");
  assert.match(py, /if not is_here:\s*\n\s*return 403, \{"ok": False, "error": COMMIT_PC_ONLY, "pc_only": True\}/);
  // And the sentence it carries no longer promises a write the phone's tap
  // cannot make - it says where to finish the run instead.
  const refusal = (py.match(/COMMIT_PC_ONLY = \(([\s\S]*?)\)\n/) || [])[1] || "";
  assert.ok(refusal.includes("Settings, Backups, and finish the run there"),
    `the refusal says where to finish it: ${refusal}`);
  assert.ok(!refusal.includes("when you tap"),
    `the old promise is gone from the refusal itself: ${refusal}`);
  assert.ok(refusal.includes("nothing was written") && refusal.includes("your PC"),
    "the words the backend's own tests pin are still there");
});

await check("CONTROL: the phone stopped claiming a backup exists, and points at the PC", async () => {
  // Adjacent Kotlin string literals joined, so a sentence split across source
  // lines can be searched for as the owner reads it on screen.
  const joined = (text) => text.replace(/"\s*\+\s*\n\s*"/g, "");
  const kt = joined(readRepo(
    "jarvis-client/app/src/main/java/com/jarvis/client/net/Backup.kt"));
  assert.ok(!kt.includes("I have saved the code - write the backup"),
    "the label promised a write the phone cannot make");
  assert.match(kt, /const val COMMIT_LABEL = "Save the code, then finish this on your PC"/);
  assert.match(kt, /const val PC_ONLY_WRITE =[\s\S]{0,700}Nothing has been written yet/);
  assert.match(kt, /PC_ONLY_WRITE =[\s\S]{0,900}Settings, Backups/);
  assert.ok(!/Ask for a backup again from the phone; if it keeps happening/.test(kt),
    "the refusal no longer tells him to ask again - that never worked");
  // "Your PC" is pinned by BackupTest.kt:222 and stays the opening words.
  assert.match(kt, /const val PC_ONLY_WRITE =\s*\n\s*"Your PC/);
  const plate = readRepo(
    "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BackupPlate.kt");
  assert.match(plate, /Backup\.PREPARED_ELSEWHERE/);
});

await browser.close(); close();

/* ── the browser-free pin that the twin says the same thing ─────────────── */

await check("CONTROL: the shipped twin carries the same bytes as backend/", async () => {
  assert.equal(readRepo("jarvis-backend/jarvis_backup.py"),
    readRepo("backend/jarvis_backup.py"),
    "a shipped-whole module must be identical in both trees");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nThe PC finishes a backup the phone started: shown only while live, " +
  "typed code, the existing commit, and the backend's own words back");
