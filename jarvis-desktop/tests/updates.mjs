/**
 * The updater, and the line it must not cross.
 *
 * The owner's rule for this app is that nothing acts without a person: no
 * auto-approve, no approve-all, anywhere. An update replaces the executable,
 * which is the largest single change anything here can make to the machine, so
 * that rule applies to it more than to anything else — and the failure mode is
 * silent, because an updater that installed on its own would simply appear to
 * work.
 *
 * So the load-bearing test in this file is `a check never installs`. The rest
 * is whether the window tells the truth about what it found.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import { DESKTOP_FAQ } from "../src/desktop-help.js";
import { buildPalette, search as searchPalette } from "../src/palette.js";
import { asksForUpdates, UPDATE_WORDS } from "../src/settings-search.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const VIEW = { width: 760, height: 1000 };
const open = (data = {}) => K.open(browser, base, "settings.html", data, VIEW);
const calls = (page) => page.evaluate(() => window.__calls.map((c) => c[0]));

const FOUND = { available: "0.2.0", notes: "Fixed the thing.", date: "2026-09-20" };

/* BOTH OR NEITHER (the owner's standing rule, stated 2026-11-20 21:12 PT).
 * When the backend half cannot run, the Install press installs NOTHING: it says
 * in one plain line which folder/thing is missing, and it never claims Jarvis
 * was updated. Every test that drives the desktop download/progress/restart
 * path therefore opens a PC whose backend half CAN run - the only state in
 * which the desktop may be installed at all. */
const BLOCKED = { where: { blocked: "The backend folder could not be found." } };

/* ── The rule ────────────────────────────────────────────────────────────── */

await check("a check never installs", async () => {
  const page = await open({ found: FOUND });
  await page.locator("#update-check").click();
  await page.waitForTimeout(300);
  const seen = await calls(page);
  await page.close();
  assert.ok(seen.includes("__checked"), "the check did not run");
  assert.ok(!seen.includes("__installed"),
    "checking installed something — this is the one thing that must never happen");
});

await check("nothing installs without a press, even with one available", async () => {
  // Open the window with an update already known, wait well past anything that
  // could be a debounce, and confirm the app just sits there.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(1200);
  const seen = await calls(page);
  await page.close();
  assert.ok(!seen.includes("__installed"), "an update installed itself");
});

await check("CONTROL: the button runs BOTH halves, so the negatives mean something", async () => {
  // The owner's requirement (2026-11-03): one Update press moves the desktop
  // AND the backend together. The default scenario has both backend folders, so
  // the press must go through update_both - through the ONE runner the
  // "Update both halves" control also uses - and never the desktop-only install.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.locator("#update-install").click();
  await page.waitForTimeout(500);
  const seen = await calls(page);
  const status = await page.locator("#update-status").innerText();
  await page.close();
  assert.ok(seen.includes("__updatedBoth"), "the Install button did not update both halves");
  assert.ok(!seen.includes("__installed"),
    "the desktop-only install ran while the backend half was available");
  assert.match(status, /backend/i, `the ending did not name the backend half: "${status}"`);
});

await check("the update button installs nothing when the backend cannot run", async () => {
  // The owner's standing rule, 2026-11-20 21:12 PT: "when I update Jarvis the
  // HUD and backend should always update at the same time." This press must
  // therefore do NOTHING when the backend half cannot run - no desktop-only
  // install, no claim that anything was updated - and must say in one plain
  // line which folder/thing is missing.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.locator("#update-install").click();
  await page.waitForTimeout(400);
  const seen = await calls(page);
  const status = await page.locator("#update-status").innerText();
  const tone = await page.locator("#update-status").getAttribute("data-tone");
  const installHidden = await page.locator("#update-install").isHidden();
  const restartHidden = await page.locator("#update-restart").isHidden();
  await page.close();
  assert.ok(!seen.includes("__installed"),
    "the desktop-only install ran while the backend half could not run");
  assert.ok(!seen.includes("__updatedBoth"),
    "update_both ran with the backend half blocked");
  assert.match(status, /NOT installed/i, `the refusal does not say nothing was installed: "${status}"`);
  assert.match(status, /backend folder could not be found/i,
    `the refusal does not name what is missing: "${status}"`);
  assert.match(status, /both halves/i, `the refusal does not say the update moves both: "${status}"`);
  assert.doesNotMatch(status, /installed on the desktop/i,
    `a half-updated PC reads as updated: "${status}"`);
  assert.equal(tone, "bad", "installing nothing was painted as a good state");
  assert.equal(installHidden, false,
    "the Install button disappeared even though nothing was installed");
  assert.equal(restartHidden, true,
    "a Restart button appeared after an install that never happened");
});

await check("CONTROL: the same both-or-neither gate is in Rust before any download", () => {
  // The page is a second witness; the guard that cannot be bypassed is
  // `update.rs`'s `install_update`, which asks the pure gate before a byte is
  // downloaded or anything stopped. The pure rule itself is a Rust unit test
  // (`the_both_or_neither_gate_allows_a_desktop_install_only_with_a_runnable_backend`).
  const rust = read("src-tauri/src/update.rs");
  const install = rust.slice(rust.indexOf("pub async fn install_update"),
                             rust.indexOf("pub fn desktop_install_gate"));
  assert.notEqual(install.length, 0, "there is no install_update command");
  const gateAt = install.indexOf("desktop_install_gate(here.blocked.as_deref())");
  const downloadAt = install.indexOf("prepare_desktop_half");
  assert.ok(gateAt >= 0, "install_update never asks the both-or-neither gate");
  assert.ok(downloadAt >= 0, "install_update never prepares the desktop package");
  assert.ok(gateAt < downloadAt,
    "install_update downloads/stops before asking whether the backend half can run");
  assert.ok(!install.includes("update.install("),
    "install_update installs outside the ordered prepare/install split");
});

await check("CONTROL: Rust keeps checking and installing as separate commands", async () => {
  // A flag on one command is how this rule gets lost in a later edit.
  const rust = read("src-tauri/src/update.rs");
  assert.match(rust, /pub async fn check_for_update/);
  assert.match(rust, /pub async fn install_update/);
  const checkFn = rust.slice(rust.indexOf("pub async fn check_for_update"),
                             rust.indexOf("pub fn set_update_check_on_start"));
  assert.ok(!/download_and_install/.test(checkFn),
    "the check path can install");
  // Up to the unit tests, which are not part of the startup check: the tests
  // below name `download_and_install` on purpose (they pin the hand-off that
  // writes the update record before the installer can end the process).
  const startup = rust.slice(rust.indexOf("pub fn spawn_startup_check"),
                             rust.indexOf("#[cfg(test)]"));
  assert.ok(startup.length > 0, "there is no startup check");
  assert.ok(!/download_and_install/.test(startup),
    "the startup check can install");
});

/* ── It tells the truth about what it found ──────────────────────────────── */

await check("no update says so, with the version", async () => {
  const page = await open();
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const installVisible = await page.locator("#update-install").isVisible();
  await page.close();
  assert.match(state, /0\.1\.0/, `said "${state}"`);
  assert.equal(installVisible, false, "an Install button is offered with nothing to install");
});

/* ── The four states (Task-50, Wave 12) ──────────────────────────────────────
 * Up to date / update available / unknown / cannot check. The bug this
 * replaces: with `available: null, error: null` (a fresh launch, no check
 * ever run) the card printed "the newest published" - a claim nothing had
 * made. So each state is driven from the PC's own `state` field here, and the
 * two that must never look alike are compared directly. */

await check("a card that has never checked says UNKNOWN, not 'the newest published'", async () => {
  const page = await open();   // K.UPDATE_NONE: state "unknown", no checked_at
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.match(state, /not checked yet/i, `said "${state}"`);
  assert.ok(!/newest published/i.test(state),
    `claimed to be the newest with no check behind it: "${state}"`);
});

await check("a finished check with nothing newer says UP TO DATE and when", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2026-11-09 14:32" },
  });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.match(state, /newest published/i, `said "${state}"`);
  assert.match(state, /last checked .*14:32/i, `did not say when it checked: "${state}"`);
});

await check("an older check keeps its date, so it cannot read as today", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2020-01-02 09:05" },
  });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.match(state, /2020-01-02 09:05/, `dropped the date off an old check: "${state}"`);
});

await check("a check that could not answer says so, with the reason and the time", async () => {
  const page = await open({
    update: {
      ...K.UPDATE_NONE,
      state: "cannot_check",
      error: "Could not reach the release endpoint: connection refused",
      checked_at: "2026-11-09 14:32",
    },
  });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const installVisible = await page.locator("#update-install").isVisible();
  await page.close();
  assert.match(state, /could not reach/i, `did not carry the reason: "${state}"`);
  assert.match(state, /14:32/, `did not say when it tried: "${state}"`);
  assert.ok(!/newest published/i.test(state), "a failed check was drawn as a good state");
  assert.equal(installVisible, false, "an Install button appeared after a failed check");
});

await check("unknown and up to date are never the same sentence", async () => {
  const textOf = async (update) => {
    const page = await open({ update });
    await page.waitForTimeout(300);
    const said = await page.locator("#update-state").innerText();
    await page.close();
    return said;
  };
  const unknown = await textOf({ ...K.UPDATE_NONE });
  const fresh = await textOf({
    ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2026-11-09 14:32",
  });
  assert.notEqual(unknown, fresh, "an unchecked card reads exactly like a checked one");
});

await check("CONTROL: the state is computed in Rust, and Settings only renders it", () => {
  // One rule, one place: `update.rs` owns the four words and the checked time,
  // so the card and the tray row cannot disagree about the same fact.
  const rust = read("src-tauri/src/update.rs");
  assert.match(rust, /fn state_of\(/, "there is no single state rule");
  for (const state of ["unknown", "cannot_check", "up_to_date", "update_available"]) {
    assert.ok(rust.includes(`"${state}"`), `update.rs never names ${state}`);
  }
  assert.match(rust, /status\.checked_at = Some\(local_stamp\(\)\)/,
    "a finished check does not record when it ran");
  assert.match(rust, /status\.checked_at = Some\(local_stamp\(\)\);\s*\n\s*status\.error/,
    "the failed-updater path does not record the attempt");
});

await check("an available update names both versions", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const label = await page.locator("#update-install").innerText();
  await page.close();
  assert.match(state, /0\.2\.0/, `said "${state}"`);
  assert.match(state, /0\.1\.0/, "did not say what is running now");
  assert.match(label, /0\.2\.0/, `the button says "${label}"`);
});

await check("the two versions are read back and said as IN SYNC", async () => {
  // 2026-11-03, the owner's requirement: after an update the card shows what
  // each half says it is. The default bridge answers the in-sync shape the
  // real both-halves update leaves.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.waitForTimeout(400);
  const sync = await page.locator("#update-sync").innerText();
  const tone = await page.locator("#update-sync").getAttribute("data-tone");
  const hidden = await page.locator("#update-sync").isHidden();
  await page.close();
  assert.equal(hidden, false, "the version handshake line never showed");
  assert.match(sync, /IN SYNC/, `said "${sync}"`);
  assert.equal(tone, "ok", "in sync was not painted as the one good state");
});

await check("CONTROL: a desktop-only update finishes its backend half automatically, once", () => {
  // Rule 2 of the owner's standing rule: the Windows installer path cannot be
  // hooked, so the next start finishes the backend half by itself. The decision,
  // the once-per-mismatch record and the SAME backend runner are Rust; this
  // holds the wiring no browser test can reach.
  const rust = read("src-tauri/src/update.rs");
  const self = read("src-tauri/src/backend_self.rs");
  assert.match(rust, /pub fn auto_finish_plan\(/,
    "update.rs has no automatic-finish decision");
  assert.match(rust, /AutoFinish::Blocked\(/,
    "the automatic finish has no honest blocked answer");
  assert.match(rust, /AUTO_FINISH_ATTEMPTS\.claim\(/,
    "the automatic finish has no once-per-mismatch record");
  assert.match(rust, /crate::backend_update::run\(\s*app,\s*"responsive",\s*&label,/,
    "the automatic finish does not run the SAME backend half at the default pace");
  // ...and it carries the baseline (the build BEFORE the installer) for the
  // release's new tool defaults (2026-11-21).
  assert.match(rust, /previous_desktop_build\(\)/,
    "the automatic finish does not name the build the installer replaced");
  // It must never touch the desktop install: it runs because the desktop was
  // ALREADY installed by the Windows installer.
  const start = rust.indexOf("pub async fn finish_backend_if_desktop_ahead");
  const end = rust.indexOf("/// The update a chat message asked for");
  assert.ok(start >= 0 && end > start, "update.rs has no automatic-finish block");
  const automatic = rust.slice(start, end);
  assert.ok(!/install_now\(|install_update\(|prepare_desktop_half\(/.test(automatic),
    "the automatic backend finish can install the desktop half");
  assert.match(self,
    /crate::update::finish_backend_if_desktop_ahead\(&handle, &sync\)\.await/,
    "the startup handshake never asks for the automatic finish");
});

await check("CONTROL: the boot-strap run passes the baseline for the release's own files", () => {
  // The desktop's backend half now also carries (a) the release's new tool
  // defaults into the owner's config and (b) the release's look spec into the
  // live backend folder (both measured broken on 2026-11-21). The baseline for
  // (a) is the desktop build BEFORE this update; the repo tool must receive it,
  // and Rust must show its report lines verbatim.
  const rust = read("src-tauri/src/update.rs");
  const backend = read("src-tauri/src/backend_update.rs");
  assert.match(backend, /--previous-release/,
    "backend_update.rs never passes the previous build to the update tool");
  // The report lines are read from the WHOLE run output, not the last-60-lines
  // tail (2026-11-21): the look spec is delivered with the file half, before the
  // proof suites, and an hour of suite lines would push its BESIDE: line out of
  // the tail exactly when a run ended by a bound needs it in the report.
  assert.match(backend, /pub fn notes_of\(/,
    "backend_update.rs has no single reader for the release's report lines");
  assert.match(backend, /notes_of\(&full\)/,
    "the release-file report lines are not read from the whole run");
  assert.match(rust, /previous_release = crate::backend_update::app_commit\(\)/,
    "the in-app press does not pass the running build as the baseline");
  assert.match(rust, /remember_previous_desktop_build\(pending\.app_commit\.as_deref\(\)\)/,
    "the startup reconcile does not remember the replaced build");
});

await check("a backend behind the desktop reads as a MISMATCH that finishes automatically", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    versionSync: {
      desktop: "0.2.486",
      backend: "0.2.484",
      state: "backend-older",
      words: "MISMATCH: the backend 0.2.484, but this HUD expects 0.2.486. The update " +
        "runs both halves - Jarvis finishes the backend half automatically after a " +
        "desktop-only update, so this usually clears on its own. If it does not, Finish " +
        "the backend update - Settings, then Updates, and press Update everything there " +
        "(that one press updates both halves).",
    },
  });
  await page.waitForTimeout(400);
  const sync = await page.locator("#update-sync").innerText();
  const tone = await page.locator("#update-sync").getAttribute("data-tone");
  await page.close();
  assert.match(sync, /MISMATCH/, `said "${sync}"`);
  assert.match(sync, /Update everything/, "the mismatch no longer names the button that exists");
  assert.match(sync, /both halves/i, "the mismatch does not say the update runs both halves");
  assert.match(sync, /finishes the backend half automatically/i,
    "the mismatch does not say a desktop-only update finishes automatically");
  assert.match(sync, /0\.2\.484/, `said "${sync}"`);
  assert.match(sync, /0\.2\.486/, `said "${sync}"`);
  assert.equal(tone, "bad", "a mismatched pair was painted as fine");
});

await check("the card's three version states each say the truth, and never each other's", async () => {
  // Rule 4 of the 2026-11-20 work: both equal (in sync), backend behind
  // (updating/finishing automatically), backend newer (safe, the next desktop
  // release gets them in step). The words are `backend_self.rs`'s, so a Rust
  // test holds their truth; this holds that the card draws each one as itself.
  const readSync = async (versionSync) => {
    const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, versionSync });
    await page.waitForTimeout(300);
    const said = await page.locator("#update-sync").innerText();
    const tone = await page.locator("#update-sync").getAttribute("data-tone");
    const hidden = await page.locator("#update-sync").isHidden();
    await page.close();
    return { said, tone, hidden };
  };
  const inSync = await readSync({
    desktop: "0.2.486", backend: "0.2.486", state: "in-sync",
    words: "Jarvis Desktop 0.2.486 and the backend 0.2.486 - IN SYNC.",
  });
  assert.equal(inSync.hidden, false, "the equal state never showed");
  assert.match(inSync.said, /IN SYNC/, `said "${inSync.said}"`);
  assert.equal(inSync.tone, "ok", "the one good state was not painted green");

  const behind = await readSync({
    desktop: "0.2.486", backend: "0.2.484", state: "backend-older",
    words: "MISMATCH: the backend 0.2.484, but this HUD expects 0.2.486. The update " +
      "runs both halves - Jarvis finishes the backend half automatically after a " +
      "desktop-only update. Finish the backend update by pressing Update everything " +
      "in Settings, then Updates.",
  });
  assert.match(behind.said, /MISMATCH/, `said "${behind.said}"`);
  assert.match(behind.said, /Update everything/, `said "${behind.said}"`);

  const newer = await readSync({
    desktop: "0.2.486", backend: "0.2.490", state: "backend-newer",
    words: "The backend 0.2.490 is newer than Jarvis Desktop 0.2.486. That is safe - " +
      "the HUD keeps working and adds nothing it does not know - and the next desktop " +
      "release is what gets the two in step.",
  });
  assert.match(newer.said, /safe/i, `said "${newer.said}"`);
  assert.match(newer.said, /next desktop release/i,
    `the newer state does not say what closes the gap: "${newer.said}"`);
  assert.doesNotMatch(newer.said, /MISMATCH/, `the safe state reads as a failure: "${newer.said}"`);
  assert.notEqual(newer.tone, "bad", "a newer backend was painted as a failure");
  // Three states, three sentences, and only the equal one claims IN SYNC.
  assert.notEqual(inSync.said, behind.said);
  assert.notEqual(inSync.said, newer.said);
  assert.notEqual(behind.said, newer.said);
  assert.doesNotMatch(behind.said, /IN SYNC/);
  assert.doesNotMatch(newer.said, /IN SYNC/);
});

await check("a backend that is unreachable is said, and the card still works", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    versionSync: {
      desktop: "0.2.0",
      backend: null,
      state: "unreachable",
      words: "Jarvis Desktop 0.2.0: backend unreachable, so the two versions " +
        "cannot be compared. Nothing was changed.",
    },
  });
  await page.waitForTimeout(400);
  const sync = await page.locator("#update-sync").innerText();
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.match(sync, /backend unreachable/i, `said "${sync}"`);
  assert.match(state, /0\.2\.0/, "the updates card stopped working when the backend was down");
});

await check("release notes are shown, but folded away", async () => {
  // Published text of arbitrary length, and not ours.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(300);
  const open_ = await page.evaluate(() => document.getElementById("update-notes").open);
  // `textContent`, not `innerText`: a closed <details> renders nothing, so
  // innerText is empty even when the notes are there.
  const body = await page.evaluate(() =>
    document.getElementById("update-notes-body").textContent);
  await page.close();
  assert.equal(open_, false, "the notes push the button off the screen by default");
  assert.match(body, /Fixed the thing/);
});

await check("a build with no key says so instead of offering a dead button", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, supported: false } });
  await page.waitForTimeout(300);
  const state = await page.locator("#update-state").innerText();
  const disabled = await page.locator("#update-check").isDisabled();
  await page.close();
  assert.match(state, /no update key/i, `said "${state}"`);
  assert.equal(disabled, true, "a Check button that can only fail is still pressable");
});

await check("\"not set up yet\" follows the build's key in Updates, and the FAQ sends you here", async () => {
  const read = async (supported) => {
    const page = await open({ update: { ...K.UPDATE_NONE, supported } });
    const out = await page.evaluate(() => ({
      off: !document.getElementById("update-intro-off").hidden,
      on: !document.getElementById("update-intro-on").hidden,
      offText: document.getElementById("update-intro-off").textContent,
    }));
    await page.close();
    return out;
  };
  const without = await read(false);
  const withKey = await read(true);
  assert.deepEqual([without.off, without.on], [true, false],
    "a build with no key must say updates are not set up");
  assert.match(without.offText, /Not set up yet/);
  assert.match(without.offText, /Turning on updates/);
  assert.deepEqual([withKey.off, withKey.on], [false, true],
    "a build WITH a key still said updates were not set up");
  // THE FAQ HALF OF THIS. The old Settings card swapped a live line into its
  // "Will Jarvis update itself without asking?" answer from `paintUpdate()`,
  // and this check used to read the two spans that did it. The answer moved to
  // the Brain's Help tab on 2026-10-08, where the live swap is deliberately
  // GONE: a page that no longer renders beside the Updates card must not claim
  // to know that card's state. So what is held here is the more useful pair of
  // facts - the answer never promises a self-install, and it sends the owner to
  // the one place that really knows, which is the card this suite drives.
  const answer = DESKTOP_FAQ.find((q) => q.id === "updates-itself");
  assert.ok(answer, "desktop-help.js no longer holds the update FAQ answer");
  assert.match(answer.a, /never installs one on its own/i,
    `the FAQ no longer says Jarvis never installs by itself: "${answer.a}"`);
  assert.match(answer.a, /Updates card/,
    "the FAQ no longer sends the owner to the Updates card for whether this copy can check");
  assert.doesNotMatch(answer.a, /not set up yet/i,
    "the FAQ claims the live update state from a page that cannot see it");
});

await check("before the window has read anything, it says not set up", async () => {
  // The safe default: a window that has not heard from Rust yet claims
  // nothing. paintUpdate() switches it once `supported` is known.
  const html = read("src/settings.html");
  assert.match(html, /id="update-intro-off">/);
  assert.match(html, /id="update-intro-on" hidden>/);
});

await check("the update endpoint is the desktop's own rolling release, and the workflow publishes there", async () => {
  const conf = JSON.parse(read("src-tauri/tauri.conf.json"));
  const flow = readFileSync(join(HERE, "..", "..", ".github", "workflows", "desktop-release.yml"), "utf8");
  assert.deepEqual(conf.plugins.updater.endpoints,
    ["https://github.com/darknight11ish/Epic-Jarvis/releases/download/desktop-latest/latest.json"]);
  // Not /releases/latest/: that is whichever full release in the whole repo
  // is newest, which is not a promise about the desktop at all.
  assert.match(flow, /TAG: desktop-latest/);
  assert.doesNotMatch(flow, /TAG: client-latest|release create "?client-latest/);
  assert.equal(conf.bundle.createUpdaterArtifacts, false,
    "the committed config must build without a key; the workflow turns signing on");
});

await check("a failed install is reported, not swallowed", async () => {
  // The both-halves run itself failing (a signature that does not verify, a
  // PC that would not start the patcher) must be said, not swallowed.
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    updateBoth: { fails: "signature verification failed" },
  });
  await page.locator("#update-install").click();
  await page.waitForTimeout(300);
  const status = await page.locator("#update-status").innerText();
  const tone = await page.locator("#update-status").getAttribute("data-tone");
  await page.close();
  assert.match(status, /signature/i, `said "${status}"`);
  assert.equal(tone, "bad");
});

/* ── Download progress and restart ───────────────────────────────────────── */

await check("the progress bar is hidden until a download starts", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(300);
  const hidden = await page.evaluate(() => document.getElementById("update-progress").hidden);
  await page.close();
  assert.equal(hidden, true, "the progress bar shows with nothing downloading");
});

await check("a progress event with a total paints a percentage", async () => {
  // The progress bar is a renderer of Rust's own download events, so it is fed
  // one directly here: `install_update` is the only command that emits these,
  // and it is reachable only on a PC whose backend half can run.
  const page = await open();
  await page.waitForTimeout(200);
  // Exact multiples of a MiB, so the rendered text has no rounding to guess at.
  const mib = 1024 * 1024;
  await page.evaluate(
    ([downloaded, total]) => window.__emit("update-progress", { downloaded, total }),
    [2 * mib, 4 * mib]
  );
  await page.waitForTimeout(100);
  const hidden = await page.evaluate(() => document.getElementById("update-progress").hidden);
  const indeterminate = await page.evaluate(() =>
    document.getElementById("update-progress").dataset.indeterminate);
  const width = await page.evaluate(() => document.getElementById("update-progress-fill").style.width);
  const status = await page.locator("#update-status").innerText();
  await page.close();
  assert.equal(hidden, false, "a download in progress hid its own bar");
  assert.equal(indeterminate, "false", "a known total was treated as unknown");
  assert.equal(width, "50%", `expected 50%, painted "${width}"`);
  assert.match(status, /2\.0 MB of 4\.0 MB/i, `said "${status}"`);
});

await check("a progress event with no total says so instead of guessing", async () => {
  const page = await open();
  await page.waitForTimeout(200);
  await page.evaluate(() => window.__emit("update-progress", { downloaded: 500_000, total: null }));
  await page.waitForTimeout(100);
  const indeterminate = await page.evaluate(() =>
    document.getElementById("update-progress").dataset.indeterminate);
  const status = await page.locator("#update-status").innerText();
  await page.close();
  assert.equal(indeterminate, "true", "an unknown total was painted as a fixed percentage");
  assert.match(status, /so far/i, `said "${status}", which claims a size it does not have`);
});

await check("a finished install swaps Install for Restart, not back to a status line alone", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.locator("#update-install").click();
  await page.waitForTimeout(400);
  const installHidden = await page.locator("#update-install").isHidden();
  const restartHidden = await page.locator("#update-restart").isHidden();
  const progressHidden = await page.evaluate(() => document.getElementById("update-progress").hidden);
  await page.close();
  assert.equal(installHidden, true, "Install is still offered after it already installed");
  assert.equal(restartHidden, false, "nothing offers a restart after a successful install");
  assert.equal(progressHidden, true, "the progress bar outlives the download it tracked");
});

await check("pressing Restart calls the one command that can restart the app", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND } });
  await page.locator("#update-install").click();
  await page.waitForTimeout(400);
  await page.locator("#update-restart").click();
  await page.waitForTimeout(100);
  const seen = await calls(page);
  await page.close();
  assert.ok(seen.includes("__restarted"), "the Restart button did not call restart_app");
});

await check("a restart that could not even be requested is reported, not silent", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    restartFails: "no window left to restart from",
  });
  await page.locator("#update-install").click();
  await page.waitForTimeout(400);
  await page.locator("#update-restart").click();
  await page.waitForTimeout(100);
  const status = await page.locator("#update-status").innerText();
  const disabled = await page.locator("#update-restart").isDisabled();
  await page.close();
  assert.match(status, /no window left to restart from/i, `said "${status}"`);
  assert.equal(disabled, false, "a failed restart left the button stuck disabled with no way to retry");
});

await check("CONTROL: restart_app asks Tauri to restart, and only from the button", async () => {
  const rust = read("src-tauri/src/update.rs");
  assert.match(rust, /pub fn restart_app\(app: AppHandle\)/, "there is no restart_app command");
  const fn = rust.slice(rust.indexOf("pub fn restart_app"));
  assert.match(fn, /request_restart\(\)/,
    "restart_app does not call request_restart — an async command runs off the main thread, " +
    "where plain restart() skips the exit event the sidecar shutdown depends on");
});

await check("a result found at startup is still there when Settings opens", async () => {
  // The window is opened LATER — after a startup check has already found
  // something. Without a cache, `update_status` rebuilt a blank answer and the
  // window said "the newest published" while the tray said 0.2.0.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(300);
  const seen = await calls(page);
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.ok(!seen.includes("__checked"),
    "opening Settings fired a network check of its own");
  assert.match(state, /0\.2\.0/, `said "${state}" without having checked`);
});

await check("CONTROL: Rust caches the result rather than rebuilding a blank one", async () => {
  const rust = read("src-tauri/src/update.rs");
  assert.match(rust, /pub struct UpdateState/, "there is no cache");
  const fn = rust.slice(rust.indexOf("pub fn update_status"), rust.indexOf("/// Checks now"));
  assert.match(fn, /state::<UpdateState>\(\)/, "update_status ignores the cache");
});

/* ── The startup check ───────────────────────────────────────────────────── */

await check("the startup check can be turned off", async () => {
  const page = await open();
  assert.equal(await page.locator("#update-auto").isChecked(), true,
    "being told is the point of the feature, so it should start on");
  await page.locator("#update-auto").uncheck();
  await page.waitForTimeout(200);
  const status = await page.locator("#update-status").innerText();
  await page.close();
  assert.match(status, /will not look/i, `said "${status}"`);
});

await check("CONTROL: only one endpoint, and it is the releases URL", async () => {
  // The whole network surface of this feature. If it grows, it should grow
  // visibly.
  const conf = JSON.parse(read("src-tauri/tauri.conf.json"));
  const endpoints = conf.plugins.updater.endpoints;
  assert.equal(endpoints.length, 1, `${endpoints.length} endpoints configured`);
  assert.match(endpoints[0], /^https:\/\/github\.com\//, endpoints[0]);
  assert.ok(!/\?|token|key=/i.test(endpoints[0]),
    "the endpoint carries a query string, so it is sending something");
});

/* ── The place opens THIS card (2026-10-27; the tray row's own press stopped
   naming it on 2026-11-03, when that row began installing instead) ─────────── */

await check("the place Rust names opens Settings scrolled to the Updates card", async () => {
  // The owner, 2026-10-27: "when i right click the jarvis tray icon, click on
  // update available, it only opens the settings page". `windows.rs`'s
  // `show_settings_at` builds a NEW window at `settings.html#updates`, and
  // `settings.js` consumes that fragment. The tray's own row now INSTALLS
  // rather than naming this place (`tray.rs`, 2026-11-03); the place itself is
  // still the destination every other route uses, and is what this checks.
  const page = await K.open(browser, base, "settings.html#updates",
    { update: { ...K.UPDATE_NONE, ...FOUND } }, VIEW);
  await page.waitForFunction(() => {
    const card = document.getElementById("updates");
    return card && Math.abs(card.getBoundingClientRect().top) < 60;
  }, null, { timeout: 3000 }).catch(() => {});
  const seen = await page.evaluate(() => {
    const card = document.getElementById("updates");
    return {
      top: card.getBoundingClientRect().top,
      active: document.activeElement && document.activeElement.id,
      inside: card.contains(document.activeElement),
      hash: location.hash,
      state: document.getElementById("update-state").textContent,
    };
  });
  await page.close();
  assert.ok(seen.top >= -4 && seen.top < 60,
    `the Updates card is ${Math.round(seen.top)}px from the top of the window`);
  assert.equal(seen.inside, true,
    `focus is on "${seen.active}", outside the card the tray named`);
  assert.equal(seen.hash, "",
    "the place stayed in the address, so opening Settings again would jump back to it");
  assert.match(seen.state, /0\.2\.0/, `the card does not show the version: "${seen.state}"`);
});

await check("an OPEN window hears the place instead of being reloaded", async () => {
  // The other door: Rust finds the window already open and emits
  // `settings-place` rather than building a new one, which would lose whatever
  // was typed in it. The page must move; a place it does not have must be
  // ignored rather than throwing.
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(300);
  await page.evaluate(() => window.scrollTo(0, 0));
  // A search in the box filters the page and hides this card. A place names one
  // card, so it has to let the filter go first - otherwise the scroll and the
  // focus land on something that is not on screen.
  await page.locator("#settings-search-input").fill("voice");
  await page.waitForTimeout(200);
  assert.equal(await page.locator("#updates").isVisible(), false,
    "the filter did not hide the card this check needs hidden");
  await page.evaluate(() => window.__emit("settings-place", "updates"));
  await page.waitForFunction(() => {
    const card = document.getElementById("updates");
    return card && !card.hidden && Math.abs(card.getBoundingClientRect().top) < 60;
  }, null, { timeout: 3000 }).catch(() => {});
  const seen = await page.evaluate(() => {
    const card = document.getElementById("updates");
    return {
      top: card.getBoundingClientRect().top,
      hidden: card.hidden,
      search: document.getElementById("settings-search-input").value,
      active: document.activeElement && document.activeElement.id,
      inside: card.contains(document.activeElement),
    };
  });
  const errorsBefore = page.__errors.length;
  await page.evaluate(() => window.__emit("settings-place", "no-such-card"));
  await page.waitForTimeout(100);
  const errorsAfter = page.__errors.length;
  await page.close();
  assert.equal(seen.hidden, false, "a search kept hiding the card the place named");
  assert.equal(seen.search, "", "the search box still filters the page after a place arrived");
  assert.ok(seen.top >= -4 && seen.top < 60,
    `the Updates card is ${Math.round(seen.top)}px from the top of the window`);
  assert.equal(seen.inside, true,
    `focus is on "${seen.active}", outside the card the event named`);
  assert.equal(errorsAfter, errorsBefore, "a place the page does not have threw");
});

/* ── The update words put the Updates card first (the owner, 2026-11-21) ───
 *
 * *"when i search updates in the settings i have to scroll all the way to the
 * bottom of the list to find the update section for jarvis. it should be at the
 * top of the list."* Ranking by the words on the card already did it for
 * "update"/"updates", but NOT for the words a person types for the card:
 * "upgrade" appears on no card on the page (it matched nothing at all) and
 * "version" appears on several (About outranked Updates). These checks drive
 * the real page and THE update words, including the two that were wrong, so the
 * old tree fails them. */

await check("every update word puts the Updates card first in the search results", async () => {
  const words = ["update", "updates", "upgrade", "upgrades", "upgrading", "version", "versions"];
  for (const word of words) {
    const page = await open();
    await page.waitForTimeout(300);
    await page.locator("#settings-search-input").fill(word);
    await page.waitForTimeout(250);
    const left = await page.evaluate(() =>
      [...document.querySelectorAll("main .card")].filter((card) => !card.hidden)
        .map((card) => card.id));
    await page.close();
    assert.ok(left.includes("updates"), `"${word}" hid the Updates card: ${left.join(", ")}`);
    assert.equal(left[0], "updates",
      `"${word}" put ${left[0] ?? "nothing"} first, not Updates: ${left.join(", ")}`);
  }
});

await check("an update word shows the Update card even when no card spells it", async () => {
  // "upgrade" is on no card's words on this page, so before the pin the search
  // answered "Nothing here matches" about the one card the owner was looking
  // for. It is still not claimed to contain the word - the card is just the
  // place the word means.
  const page = await open();
  await page.waitForTimeout(300);
  await page.locator("#settings-search-input").fill("upgrade");
  await page.waitForTimeout(250);
  const left = await page.evaluate(() =>
    [...document.querySelectorAll("main .card")].filter((card) => !card.hidden)
      .map((card) => card.id));
  const count = await page.locator("#settings-search-status").innerText();
  const noneHidden = await page.evaluate(() =>
    document.getElementById("settings-search-none").hidden);
  await page.close();
  assert.deepEqual(left, ["updates"], `"upgrade" showed ${left.join(", ") || "nothing"}`);
  assert.match(count, /1 setting matches/i, `the count said "${count}"`);
  assert.equal(noneHidden, true, "the page said nothing matched while the card was shown");
});

await check("a search that is not about updates is left to the ordinary ranking", async () => {
  // The pin is for update words only: no unrelated search is reordered for it.
  const page = await open();
  await page.waitForTimeout(300);
  await page.locator("#settings-search-input").fill("backup");
  await page.waitForTimeout(250);
  const left = await page.evaluate(() =>
    [...document.querySelectorAll("main .card")].filter((card) => !card.hidden)
      .map((card) => card.id));
  await page.close();
  assert.equal(left[0], "backup",
    `"backup" put ${left[0] ?? "nothing"} first: ${left.join(", ")}`);
  assert.notEqual(left[0], "updates", "an unrelated search was pinned to Updates");
});

await check("only an update-intent query is pinned to Updates, word for word", () => {
  // The ruling's own vocabulary (Gemini 5.4, 2026-11-21): the card's name, both
  // spellings of the action, the version word, the two words the HANDSHAKE
  // prints when the halves differ ("sync" / "mismatch"), and the card's own
  // button name ("check now"). Every one is update-intent on its own.
  for (const word of ["update", "updates", "upgrade", "version", "versions",
    "sync", "mismatch"]) {
    assert.ok(UPDATE_WORDS.includes(word), `"${word}" is not an update word`);
    assert.equal(asksForUpdates(word), true, `"${word}" is not pinned to Updates`);
  }
  for (const phrase of ["check now", "check for updates", "check for update"]) {
    assert.equal(asksForUpdates(phrase), true, `"${phrase}" is not pinned to Updates`);
  }
  // ANY other word turns the pin off. An unrelated search is never reordered,
  // even when one of its words is an update word - so "version history" is a
  // question about History, not a second way to spell the Updates card.
  for (const query of ["", "backup", "version history", "sync settings", "check",
    "now", "check now please", "update the lights", "mismatched", "resync"]) {
    assert.equal(asksForUpdates(query), false, `"${query}" was pinned to Updates`);
  }
});

await check("the handshake's own words find the Updates card, and so does its button name", async () => {
  // "sync" and "mismatch" are what the version line prints when the halves
  // differ, and "check now" is printed on the card's own button: after reading
  // either, searching that word must land on the card, not below it.
  for (const query of ["sync", "mismatch", "check now"]) {
    const page = await open();
    await page.waitForTimeout(300);
    await page.locator("#settings-search-input").fill(query);
    await page.waitForTimeout(250);
    const left = await page.evaluate(() =>
      [...document.querySelectorAll("main .card")].filter((card) => !card.hidden)
        .map((card) => card.id));
    await page.close();
    assert.ok(left.includes("updates"), `"${query}" hid the Updates card: ${left.join(", ")}`);
    assert.equal(left[0], "updates",
      `"${query}" put ${left[0] ?? "nothing"} first, not Updates: ${left.join(", ")}`);
  }
});

await check("the one quick entry sits above the jump list and opens the Updates card", async () => {
  const page = await open();
  await page.waitForTimeout(400);
  const entry = await page.evaluate(() => {
    const quick = document.getElementById("settings-quick");
    const link = quick && quick.querySelector("a");
    const jump = document.getElementById("settings-jump");
    return {
      exists: Boolean(quick),
      visible: Boolean(quick && !quick.hidden),
      href: link ? link.getAttribute("href") : null,
      words: link ? link.textContent.trim() : "",
      beforeJump: Boolean(quick && jump &&
        (quick.compareDocumentPosition(jump) & Node.DOCUMENT_POSITION_FOLLOWING)),
    };
  });
  assert.equal(entry.exists, true, "the page has no quick entry above the jump list");
  assert.equal(entry.visible, true, "the quick entry is hidden with nothing typed");
  assert.equal(entry.href, "#updates", `the quick entry points at "${entry.href}"`);
  assert.equal(entry.words, "Updates", `the quick entry says "${entry.words}"`);
  assert.equal(entry.beforeJump, true, "the quick entry is below the jump list");
  // ...and it really opens the card (the jump the owner does not have to make).
  await page.locator("#settings-quick a").click();
  await page.waitForTimeout(500);
  const top = await page.evaluate(() =>
    Math.round(document.getElementById("updates").getBoundingClientRect().top));
  assert.ok(top >= -4 && top < 120, `the Update card is ${top}px from the top of the window`);
  // A filtered page does not keep a map to the cards it hid.
  await page.locator("#settings-search-input").fill("voice");
  await page.waitForTimeout(250);
  const hiddenWhileSearching = await page.evaluate(() =>
    document.getElementById("settings-quick").hidden);
  await page.close();
  assert.equal(hiddenWhileSearching, true,
    "the quick entry stayed over a filtered page it cannot point at");
});

await check("the app-wide Find list puts the Updates row first for the update words", () => {
  // The compiled menu catalogue is the third box the owner may have called
  // "settings search" (the bar's Find, built from backend/jarvis_menus.py). It
  // shared the bug: "upgrade" found nothing, "version" found About first. The
  // pin is the SAME `asksForUpdates` rule the Settings page uses, so the two
  // boxes cannot disagree about what "the update card" is.
  const items = buildPalette();
  for (const word of ["update", "updates", "upgrade", "upgrades", "upgrading",
    "version", "versions", "sync", "mismatch"]) {
    const rows = searchPalette(items, word);
    assert.equal(rows[0] && rows[0].item.id, "settings.updates",
      `"${word}" put ${rows[0] ? rows[0].item.id : "nothing"} first`);
  }
  // "upgrade" has to BE the row, not merely be ranked: before the pin the list
  // came back empty and the bar said "Nothing matches that".
  assert.equal(searchPalette(items, "upgrade")[0].item.title, "Updates");
  // An unrelated search is not reordered.
  assert.notEqual(searchPalette(items, "backup")[0].item.id, "settings.updates");
});

await check("the Updates card says the three states plainly - equal, behind, finishing", async () => {
  const read = async (data) => {
    const page = await open(data);
    await page.waitForTimeout(400);
    const out = await page.evaluate(() => ({
      state: document.getElementById("update-state").textContent,
      checkDisabled: document.getElementById("update-check").disabled,
      installHidden: document.getElementById("update-install").hidden,
    }));
    await page.close();
    return out;
  };
  const checkedNoNewer = { ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2026-11-09 14:32" };
  const equalSync = {
    desktop: "0.2.492", backend: "0.2.492", state: "in-sync",
    words: "Jarvis Desktop 0.2.492 and the backend 0.2.492 - IN SYNC.",
  };
  const behindSync = {
    desktop: "0.2.492", backend: "0.2.491", state: "backend-older",
    words: "MISMATCH: the backend 0.2.491, but this HUD expects 0.2.492.",
  };

  // 1. Both halves equal, and the check found nothing newer: "Up to date."
  const equal = await read({ update: checkedNoNewer, versionSync: equalSync });
  assert.match(equal.state, /^Up to date\./, `said "${equal.state}"`);
  assert.match(equal.state, /newest published/i,
    `the finished check's own line was lost: "${equal.state}"`);
  assert.equal(equal.checkDisabled, false, "the Check button went dead on an equal pair");

  // 2. The backend is behind: the INSTALLED desktop and the OLDER backend are
  //    named, and the one press that finishes it is named.
  const behind = await read({ update: checkedNoNewer, versionSync: behindSync });
  assert.match(behind.state,
    /Jarvis Desktop 0\.2\.492 is installed; the backend is 0\.2\.491/,
    `said "${behind.state}"`);
  assert.match(behind.state, /Update everything to finish the backend half/,
    `the one press is not named: "${behind.state}"`);
  assert.doesNotMatch(behind.state, /^Up to date\./,
    "the card claimed to be up to date with a backend behind it");

  // 3. A run is in flight: it says so, and does not restate a mismatch.
  const finishing = await read({
    update: checkedNoNewer,
    versionSync: { ...behindSync, running: true },
  });
  assert.match(finishing.state, /^Finishing the backend half now\./,
    `said "${finishing.state}"`);
  assert.match(finishing.state, /0\.2\.491/, `said "${finishing.state}"`);
  assert.doesNotMatch(finishing.state, /MISMATCH/, "the card repeated the stale mismatch");

  // The three are three different sentences.
  assert.notEqual(equal.state, behind.state);
  assert.notEqual(behind.state, finishing.state);
  assert.notEqual(equal.state, finishing.state);
});

await check("a check that finds no newer release never hides a backend half behind", async () => {
  // The owner's measured complaint: *"when i go to updates in settings it says
  // none available when i click check for updates"* - true about the RELEASE and
  // misleading about the machine, because the backend half was still behind and
  // the card implied there was nothing to do. Pressing Check must not repaint
  // over the half that needs finishing.
  const page = await open({
    update: { ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2026-11-09 14:32" },
    versionSync: {
      desktop: "0.2.492", backend: "0.2.491", state: "backend-older",
      words: "MISMATCH: the backend 0.2.491, but this HUD expects 0.2.492.",
    },
  });
  await page.waitForTimeout(400);
  await page.locator("#update-check").click();
  await page.waitForTimeout(500);
  const state = await page.locator("#update-state").innerText();
  const status = await page.locator("#update-status").innerText();
  await page.close();
  assert.match(status, /Nothing newer/i, `the press did not answer: "${status}"`);
  assert.match(state, /Jarvis Desktop 0\.2\.492 is installed; the backend is 0\.2\.491/,
    `the no-newer answer hid the backend half: "${state}"`);
  assert.match(state, /Update everything to finish the backend half/,
    `the card stopped offering the one press: "${state}"`);
});

/* ── The Settings banner and the bounded proof's phase line ───────────────
 *
 * Gemini's rulings 5.2 and 5.4 (2026-11-21). Two things the owner must not have
 * to scroll for, or wait for a release check to learn:
 *
 *   - the top banner, whenever the backend half is behind or a half is being
 *     finished right now, clearing in place on an IN SYNC read-back;
 *   - the clean `Step N/M: <phase> - x of y…` line while a bounded proof runs,
 *     fed by the runner's own `PROOF: Step N/M - <phase> - x of y` output.
 */

const BEHIND_SYNC = {
  desktop: "0.2.492", backend: "0.2.491", state: "backend-older",
  words: "MISMATCH: the backend 0.2.491, but this HUD expects 0.2.492.",
};
const EQUAL_SYNC = {
  desktop: "0.2.492", backend: "0.2.492", state: "in-sync",
  words: "Jarvis Desktop 0.2.492 and the backend 0.2.492 - IN SYNC.",
};

await check("a banner at the top of Settings says when the backend half is behind", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, versionSync: BEHIND_SYNC });
  await page.waitForTimeout(400);
  const seen = await page.evaluate(() => {
    const banner = document.getElementById("settings-update-banner");
    const link = document.getElementById("settings-update-banner-link");
    const card = document.getElementById("updates");
    return {
      hidden: banner.hidden,
      tone: banner.dataset.tone,
      words: document.getElementById("settings-update-banner-words").textContent,
      linkHref: link.getAttribute("href"),
      linkWords: link.textContent.trim(),
      beforeCard: Boolean(banner.compareDocumentPosition(card)
        & Node.DOCUMENT_POSITION_FOLLOWING),
      top: Math.round(banner.getBoundingClientRect().top),
      cardTop: Math.round(card.getBoundingClientRect().top),
    };
  });
  await page.close();
  assert.equal(seen.hidden, false, "no banner while the backend half was behind");
  assert.equal(seen.tone, "bad", "a pair that does not match was painted as fine");
  // It names BOTH halves, says what is wrong in the card's own words, and
  // points at the one press that fixes it.
  assert.match(seen.words, /0\.2\.492/, `the banner does not name the desktop: "${seen.words}"`);
  assert.match(seen.words, /0\.2\.491/, `the banner does not name the backend: "${seen.words}"`);
  assert.match(seen.words, /do not match yet/i, `the banner does not say what is wrong: "${seen.words}"`);
  assert.match(seen.words, /Update everything/, `the banner does not name the fix: "${seen.words}"`);
  assert.equal(seen.linkHref, "#updates", `the banner links at "${seen.linkHref}"`);
  assert.equal(seen.linkWords, "Go to Updates");
  assert.equal(seen.beforeCard, true, "the banner is not above the Updates card");
  assert.ok(seen.top < seen.cardTop,
    `the banner (${seen.top}px) is below the card it is about (${seen.cardTop}px)`);
});

await check("the banner stays away when there is nothing to act on", async () => {
  // Equal halves: the ruling's own clearing state. A newer backend: safe, and
  // "Update everything" would be the wrong instruction. Unreachable: the card
  // says so in its own sentence, and a banner cannot compare what it cannot
  // read. None of these is a reason to put a banner at the top of Settings.
  for (const versionSync of [
    EQUAL_SYNC,
    { desktop: "0.2.486", backend: "0.2.490", state: "backend-newer",
      words: "The backend 0.2.490 is newer than Jarvis Desktop 0.2.486." },
    { desktop: "0.2.486", backend: null, state: "unreachable",
      words: "Jarvis Desktop 0.2.486: backend unreachable." },
  ]) {
    const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, versionSync });
    await page.waitForTimeout(350);
    const hidden = await page.evaluate(() =>
      document.getElementById("settings-update-banner").hidden);
    await page.close();
    assert.equal(hidden, true,
      `a banner appeared for state "${versionSync.state}"`);
  }
});

await check("the banner clears in place when the read-back says IN SYNC (no reload)", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2026-09-20 14:32" },
    versionSync: BEHIND_SYNC,
  });
  await page.waitForTimeout(400);
  const before = await page.evaluate(() => {
    // A marker on THIS document: if the page reloaded, it is gone.
    window.__bannerPageMarker = "same-page";
    return !document.getElementById("settings-update-banner").hidden;
  });
  assert.equal(before, true, "the check needs a banner to clear");
  await page.evaluate(() => {
    window.__versionSync = {
      desktop: "0.2.492", backend: "0.2.492", state: "in-sync",
      words: "Jarvis Desktop 0.2.492 and the backend 0.2.492 - IN SYNC.",
    };
    // The run's own ending event: the card reads the two versions back.
    window.__emit("backend-update-progress", { phase: "done", verdict: "ok", done: 1, total: 1 });
  });
  await page.waitForFunction(
    () => document.getElementById("settings-update-banner").hidden,
    null, { timeout: 3000 }).catch(() => {});
  const after = await page.evaluate(() => ({
    hidden: document.getElementById("settings-update-banner").hidden,
    marker: window.__bannerPageMarker,
    sync: document.getElementById("update-sync").textContent,
    card: document.getElementById("update-state").textContent,
  }));
  await page.close();
  assert.equal(after.hidden, true, "the banner stayed after the read-back said IN SYNC");
  assert.equal(after.marker, "same-page", "the page reloaded instead of clearing the banner in place");
  assert.match(after.sync, /IN SYNC/, `the read-back was not the in-sync one: "${after.sync}"`);
  assert.match(after.card, /^Up to date\./, `the card did not follow the read-back: "${after.card}"`);
});

await check("a run that has written the file half does not claim 'Up to date.'", async () => {
  // MEASURED 2026-11-21: the 0.2.492 proof run was ended by the 3-hour ceiling
  // at 20:32:11Z AFTER the file half had written VERSION. In that window the
  // version read-back already says IN SYNC while the run's own checks are
  // unfinished - so "Up to date." is a claim the run has not earned, and the
  // card must say so and name the read-back that settles it.
  const page = await open({
    update: { ...K.UPDATE_NONE, state: "up_to_date", checked_at: "2026-11-21 12:30" },
    versionSync: { ...EQUAL_SYNC, running: true },
  });
  await page.waitForTimeout(400);
  const seen = await page.evaluate(() => ({
    card: document.getElementById("update-state").textContent,
    bannerHidden: document.getElementById("settings-update-banner").hidden,
    banner: document.getElementById("settings-update-banner-words").textContent,
  }));
  await page.close();
  assert.doesNotMatch(seen.card, /^Up to date\./,
    `the card claimed "Up to date." while the run's checks were unfinished: "${seen.card}"`);
  assert.match(seen.card, /not claimed to match yet/,
    `the card and the banner must agree the halves are not claimed in step: "${seen.card}"`);
  assert.match(seen.card, /Restart Jarvis and it will read IN SYNC/,
    `the card has no restart hint for a check that cannot finish: "${seen.card}"`);
  assert.equal(seen.bannerHidden, false, "no banner while a backend half was mid-update");
  assert.match(seen.banner, /Updating now/, `the banner said "${seen.banner}"`);
});

await check("the Updates card shows the bounded proof's own phase and count line", async () => {
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    versionSync: { ...BEHIND_SYNC, running: true },
  });
  await page.waitForTimeout(400);
  const read = () => page.evaluate(() => ({
    hidden: document.getElementById("update-phase").hidden,
    words: document.getElementById("update-phase").textContent,
  }));
  // The runner's exact shape, carried by the Rust reader as `proof`.
  await page.evaluate(() => window.__emit("backend-update-progress", {
    phase: "testing", done: 2, total: 8, fraction: 0.25, mode: "responsive",
    proof: "PROOF: Step 3/4 - live invariants - 8 of 12",
  }));
  await page.waitForTimeout(150);
  const first = await read();
  assert.equal(first.hidden, false, "the bounded proof's step line never appeared");
  assert.equal(first.words, "Step 3/4: Live invariants - 8 of 12…",
    `the card line said "${first.words}"`);
  // The five-minute heartbeat is the SILENCE GUARD's sign of life, not progress:
  // it carries no step, so it must leave the last one standing.
  await page.evaluate(() =>
    window.__emit("backend-update-progress", { phase: "testing", note: "still running" }));
  await page.waitForTimeout(120);
  assert.deepEqual(await read(), first, "a heartbeat erased or replaced the step line");
  // The newest step wins: the card follows the run.
  await page.evaluate(() => window.__emit("backend-update-progress", {
    phase: "testing", proof: "PROOF: Step 4/4 - look spec & config - 3 of 3",
  }));
  await page.waitForTimeout(120);
  assert.equal((await read()).words, "Step 4/4: Look spec & config - 3 of 3…");
  // The line belongs to the RUN, so the run's ending takes it down.
  await page.evaluate((sync) => {
    window.__versionSync = sync;
    window.__emit("backend-update-progress", { phase: "done", verdict: "ok", done: 12, total: 12 });
  }, EQUAL_SYNC);
  await page.waitForFunction(
    () => document.getElementById("update-phase").hidden,
    null, { timeout: 3000 }).catch(() => {});
  const ended = await read();
  await page.close();
  assert.equal(ended.hidden, true, `the step line outlived its run: "${ended.words}"`);
});

await check("a legacy full sweep keeps the card's own words - no invented step line", async () => {
  // An older desktop's full sweep prints suites and a liveness heartbeat, never
  // a `PROOF: Step` line, so no progress event carries `proof`. The card must
  // fall back to its current words rather than invent a phase or a count.
  const page = await open({
    update: { ...K.UPDATE_NONE, ...FOUND },
    versionSync: { ...BEHIND_SYNC, running: true },
  });
  await page.waitForTimeout(400);
  for (const event of [
    { phase: "reading" },
    { phase: "testing", done: 0, total: null },
    { phase: "testing", done: 3 },
  ]) {
    await page.evaluate((payload) =>
      window.__emit("backend-update-progress", payload), event);
  }
  await page.waitForTimeout(200);
  const seen = await page.evaluate(() => ({
    hidden: document.getElementById("update-phase").hidden,
    words: document.getElementById("update-phase").textContent,
    state: document.getElementById("update-state").textContent,
  }));
  await page.close();
  assert.equal(seen.hidden, true,
    `a full sweep invented a step line: "${seen.words}"`);
  assert.equal(seen.words, "");
  assert.match(seen.state, /^Finishing the backend half now\./,
    `the legacy fallback words changed: "${seen.state}"`);
});

await check("an equal pair with no finished check does not claim 'Up to date.'", async () => {
  // "Up to date." is a claim about the release check AND the two halves. A pair
  // that matches with no check behind it is not licence to say it.
  const page = await open({
    update: { ...K.UPDATE_NONE },   // state "unknown", no checked_at
    versionSync: {
      desktop: "0.2.492", backend: "0.2.492", state: "in-sync",
      words: "Jarvis Desktop 0.2.492 and the backend 0.2.492 - IN SYNC.",
    },
  });
  await page.waitForTimeout(400);
  const state = await page.locator("#update-state").innerText();
  await page.close();
  assert.doesNotMatch(state, /^Up to date\./, `claimed "${state}" with no check`);
  assert.match(state, /Not checked yet/i, `said "${state}"`);
});

await check("CONTROL: no page threw", async () => {
  const page = await open({ update: { ...K.UPDATE_NONE, ...FOUND }, updateBoth: BLOCKED });
  await page.waitForTimeout(400);
  assert.deepEqual(page.__errors, [], page.__errors.join(" | "));
  await page.close();
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nthe updater holds its line");
process.exit(fails.length ? 1 : 0);


