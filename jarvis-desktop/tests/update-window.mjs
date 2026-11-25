/**
 * The update's own progress window (DEF-098; the owner's request of
 * 2026-11-24: "when i update jarvis there should be a pop up with a progress
 * bar").
 *
 * The window is `src/update-window.html`, its drawing function is
 * `viewFor` in `src/update-window.js`, and the page is opened from Rust
 * (`update_window.rs`, called by `update_both`). This suite is pure node: it
 * extracts `viewFor` and drives it with the SAME payload shapes the four
 * events carry, then pins the page and the Rust module that feed it.
 *
 * What must hold, and why each is load-bearing:
 * - before the first real number the bar is null and the words say so - a
 *   progress bar that moves with nothing behind it is the defect this fixes;
 * - the backend bar is the tool's own `fraction`, or its done/total counts;
 * - the download bar is the package's bytes, and an unknown total is no bar;
 * - 100% belongs to the tool's clean verdict, never to a fraction event, and a
 *   run with problems never reaches it;
 * - a failure names the failing file or the step in the tool's own words and
 *   is never painted as success;
 * - the installer phase stops the bar and says what is about to happen,
 *   because the installer ends the process that owns this page;
 * - the verified line is drawn where it is sent - at the end of the download,
 *   before the backend is stopped - and it never claims installer progress;
 * - the page only lists, never invokes: it cannot start, resume or approve an
 *   update, and closing it does not stop the run.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const REPO = join(HERE, "..", "..");
const read = (p) => readFileSync(join(SRC, p), "utf8");
const readRepo = (p) => readFileSync(join(REPO, p), "utf8");

const fails = [];
const check = (name, fn) => {
  try {
    fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const js = read("update-window.js");
const page = read("update-window.html");

/* ── The drawing function, extracted from the shipped page ──────────────── */

const found = /function viewFor\(state\) \{[\s\S]*?\n\}/.exec(js);
assert.ok(found, "update-window.js has no top-level `function viewFor(state) { ... }`");
const viewFor = new Function(`${found[0]}; return viewFor;`)();

/** One backend progress payload, with the same camelCase fields
 *  `update_progress.rs` actually sends (`Progress`). */
const backend = (patch = {}) => ({
  phase: "testing",
  done: 0,
  total: null,
  failed: 0,
  skipped: 0,
  verdict: null,
  fraction: null,
  etaSeconds: null,
  etaLowSeconds: null,
  etaHighSeconds: null,
  measured: null,
  bad: [],
  ...patch,
});

/** The page's state object, with every field the event handlers set. */
const state = (patch = {}) => ({
  startLine: "",
  source: null,
  backend: null,
  download: null,
  steps: { backend: null, desktop: null },
  verified: false,
  verifiedLine: "",
  installing: false,
  installingLine: "",
  ended: null,
  ...patch,
});

/* ── Nothing is measured until something really was ─────────────────────── */

check("before the first event the bar is empty and the words say nothing is measured", () => {
  const view = viewFor(state());
  assert.equal(view.bar, null, "a bar was drawn before anything was measured");
  assert.match(view.headline, /Starting the update/);
  assert.match(view.detail, /Nothing has been measured yet/);
  // ...and the same is true for a backend event that carries no numbers yet.
  const reading = viewFor(state({ source: "backend", backend: backend({ phase: "reading" }) }));
  assert.equal(reading.bar, null, "an empty reading event drew a bar");
  assert.match(reading.detail, /Nothing has been measured yet/);
  // A malformed payload cannot throw or invent a bar either.
  const broken = viewFor(state({ source: "backend", backend: {} }));
  assert.equal(broken.bar, null);
  assert.equal(viewFor(undefined).bar, null);
});

/* ── The backend bar is the update tool's own numbers ───────────────────── */

check("the backend bar is the tool's fraction, and the counts are its counts", () => {
  const view = viewFor(state({
    source: "backend",
    backend: backend({ phase: "testing", done: 12, total: 356, fraction: 0.4321 }),
  }));
  assert.ok(Math.abs(view.bar - 43.21) < 0.01, `the bar was ${view.bar}, not the tool's fraction`);
  assert.equal(view.count, "12 of 356 checks");
  assert.equal(view.headline, "Checking the backend");
  assert.match(view.detail, /never moves on a timer/, "the bar is not described as time-driven");
});

check("without a fraction the bar is done of total, and a count without a total draws no bar", () => {
  const ratio = viewFor(state({
    source: "backend",
    backend: backend({ phase: "rehearsing", done: 30, total: 120 }),
  }));
  assert.ok(Math.abs(ratio.bar - 25) < 0.01, `done/total was not the bar: ${ratio.bar}`);
  assert.equal(ratio.count, "30 of 120 items");

  const noDenominator = viewFor(state({
    source: "backend",
    backend: backend({ phase: "testing", done: 7, total: null }),
  }));
  assert.equal(noDenominator.bar, null, "a bar was invented without a total");
  assert.equal(noDenominator.count, "7 checks done", "the real count was lost with no denominator");
  assert.notEqual(noDenominator.detail, "", "nothing said why the bar is empty");
});

check("100% belongs to the tool's clean verdict, never to a fraction event", () => {
  const nearly = viewFor(state({
    source: "backend",
    backend: backend({ phase: "testing", done: 10, total: 10, fraction: 1 }),
  }));
  assert.ok(nearly.bar <= 99, `a fraction event painted ${nearly.bar}%`);

  const clean = viewFor(state({
    source: "backend",
    backend: backend({ phase: "done", done: 10, total: 10, fraction: 1, verdict: "ok" }),
  }));
  assert.equal(clean.bar, 100, "a clean verdict did not reach 100%");
  assert.match(clean.headline, /backend half is done/);
});

check("a run with problems never reaches 100 and says not to trust it", () => {
  const view = viewFor(state({
    source: "backend",
    backend: backend({ phase: "done", done: 356, total: 356, fraction: 1, verdict: "problems" }),
  }));
  assert.ok(view.bar <= 99, `a run with problems painted ${view.bar}%`);
  assert.equal(view.tone, "bad");
  assert.match(view.headline, /problems/);
  assert.match(view.detail, /did not pass/);
});

check("the failing file and the tool's reason are shown word for word", () => {
  const reason = "Access is denied: the folder would not be written";
  const view = viewFor(state({
    source: "backend",
    backend: backend({
      phase: "done",
      done: 4,
      total: 4,
      fraction: 0.9,
      verdict: "problems",
      failed: 1,
      bad: [{ name: "test_media.py", reason, ranHere: false }],
    }),
  }));
  assert.deepEqual(view.failed, [`test_media.py - ${reason}`],
    "the failing check was not named in the tool's own words");
});

/* ── A half that did not finish is never success ────────────────────────── */

check("a failed backend step is named and the bar stops", () => {
  const detail = "The backend half did not finish. Fix what the log says, then run this again.";
  const view = viewFor(state({
    source: "backend",
    backend: backend({ phase: "testing", done: 4, total: 10, fraction: 0.4 }),
    steps: { backend: { step: "backend", state: "failed", detail }, desktop: null },
  }));
  assert.equal(view.tone, "bad");
  assert.match(view.headline, /did not finish/);
  assert.equal(view.detail, detail, "the step's own sentence was not used");
  assert.equal(view.bar, null, "a failed run kept a moving-looking bar");
});

check("a skipped desktop half is a refusal, not an install", () => {
  const view = viewFor(state({
    steps: {
      backend: { step: "backend", state: "failed", detail: "backend failed" },
      desktop: { step: "desktop", state: "skipped", detail: "Not installed. The backend step did not finish." },
    },
  }));
  assert.equal(view.tone, "bad");
  assert.match(view.headline, /was not installed/);
  assert.match(view.detail, /Not installed/);
});

check("an ended run that did not finish is never called updated", () => {
  const view = viewFor(state({
    ended: { bad: true, line: "The update did not finish: backend did not. The two halves may differ." },
  }));
  assert.equal(view.tone, "bad");
  assert.match(view.headline, /did not finish/);
  assert.match(view.detail, /did not finish/);
  assert.equal(view.bar, null);
});

check("an ended run that did finish says so", () => {
  const view = viewFor(state({
    ended: { bad: false, line: "Both halves are updated. Restart Atlas to run the new version." },
  }));
  assert.equal(view.tone, "ok");
  assert.match(view.headline, /finished/);
  assert.match(view.detail, /updated/);
});

/* ── The desktop download is bytes, and the installer is not drawn ──────── */

check("the download bar is the package's bytes", () => {
  const mb = 1048576;
  const view = viewFor(state({
    source: "desktop",
    download: { downloaded: 5 * mb, total: 10 * mb },
  }));
  assert.ok(Math.abs(view.bar - 50) < 0.01, `the download bar was ${view.bar}`);
  assert.equal(view.count, "5.0 MB of 10.0 MB");
  assert.equal(view.headline, "Downloading Atlas Desktop");
});

check("an unknown download total draws no bar and says the size was not told", () => {
  const view = viewFor(state({
    source: "desktop",
    download: { downloaded: 4096, total: null },
  }));
  assert.equal(view.bar, null, "an unknown total became a bar");
  assert.match(view.count, /did not say the total size/);
});

check("a finished download words the installer, not success", () => {
  const view = viewFor(state({
    source: "desktop",
    download: { downloaded: 2048, total: 2048 },
  }));
  assert.ok(view.bar <= 99, "a finished download painted 100%");
  assert.match(view.headline, /installer is next/);
  assert.match(view.detail, /cannot show the installer's own progress/);
  assert.doesNotMatch(view.headline, /updated/i, "a download was called an update");
});

check("the installer note stops the bar and says Atlas closes and starts again", () => {
  const line = "The installer is starting now. Atlas closes and starts again by itself.";
  const view = viewFor(state({ installing: true, installingLine: line }));
  assert.equal(view.bar, null, "the window pretended to show installer progress");
  assert.match(view.headline, /installer is starting now/);
  assert.equal(view.detail, line);
  assert.doesNotMatch(view.detail, /installer progress[^,]*\d+%/);
});

check("the verified note is drawn as its own line, before the installer and with no bar", () => {
  const line = "Download verified — closing Atlas to install and restart…";
  const view = viewFor(state({ source: "desktop", verified: true, verifiedLine: line }));
  assert.equal(view.detail, line, "the page did not draw the verified note's own sentence");
  assert.equal(view.bar, null, "the verified phase drew a bar for something it cannot measure");
  assert.doesNotMatch(view.detail, /\d+\s*%|percent(age)?/i,
    "the verified line claimed a percentage of the installer");
  assert.doesNotMatch(view.headline, /installer is starting now/i,
    "the verified note is drawn as the installer already taking over");
  assert.doesNotMatch(view.detail, /updated/i, "a verified download was called an update");

  // The page's own note handler recognises the kind, so this row is not just
  // `viewFor` being driven with a hand-made state.
  assert.match(js, /note\.kind === "verified"/,
    "the page's note handler ignores the verified kind");

  // A malformed verified note still says Atlas closes and restarts, and still
  // draws no bar; the installer note then wins over it, as the run's order.
  const bare = viewFor(state({ verified: true }));
  assert.equal(bare.bar, null);
  assert.match(bare.detail, /closes and restarts/);
  const installing = viewFor(state({
    verified: true,
    verifiedLine: line,
    installing: true,
    installingLine: "The installer is starting now. Atlas closes and starts again.",
  }));
  assert.match(installing.headline, /installer is starting now/,
    "the installer note did not win over the verified one");

  // The static explanation is still on the page, in the page's own words.
  assert.match(page.replace(/\s+/g, " "), /Atlas closes and starts again/);
});

check("the desktop half before its first byte says nothing is measured", () => {
  const view = viewFor(state({ source: "desktop", download: null }));
  assert.equal(view.bar, null);
  assert.match(view.detail, /Nothing has been measured yet/);
});

/* ── The page only reports, and says what closing it does ───────────────── */

check("the page listens to the updater's own four events", () => {
  for (const name of ["backend-update-progress", "update-progress", "update-step", "update-window-note"]) {
    assert.ok(js.includes(`"${name}"`), `update-window.js never listens for ${name}`);
  }
  // The two names owned by Rust, pinned to the constants the app really sends.
  assert.match(readRepo("jarvis-desktop/src-tauri/src/update_progress.rs"),
    /PROGRESS_EVENT: &str = "backend-update-progress"/,
    "update_progress.rs no longer sends the event the window listens for");
  const lib = readRepo("jarvis-desktop/src-tauri/src/lib.rs");
  for (const [constant, name] of [
    ["UPDATE_PROGRESS", "update-progress"],
    ["UPDATE_STEP", "update-step"],
    ["UPDATE_WINDOW_NOTE", "update-window-note"],
  ]) {
    assert.ok(lib.includes(`pub const ${constant}: &str = "${name}";`),
      `lib.rs no longer defines ${constant} as ${name}`);
  }
});

check("the window holds no command and calls none", () => {
  assert.doesNotMatch(js, /core\.invoke|TAURI\.core\.invoke|\binvoke\(/, "the window calls a command");
  assert.doesNotMatch(js, /install\w*\(|update_both\(/, "the window can start an install");
  assert.doesNotMatch(js, /\bfetch\(|XMLHttpRequest|WebSocket/, "the window reaches the network");
});

check("it never draws the log folder or the script's tail", () => {
  assert.doesNotMatch(js, /logDir|\.tail\b/, "the window reads a path or the raw log tail");
});

check("closing the window is said, in words, not to stop the update", () => {
  assert.match(page.replace(/\s+/g, " "), /Closing this window does not stop the update/);
  assert.match(page.replace(/\s+/g, " "), /the run carries on/);
  assert.match(page.replace(/\s+/g, " "), /next start says how the update ended/);
});

check("the page is a real window page: UTF-8, a title, no inline script", () => {
  const head = Buffer.from(page, "utf8").subarray(0, 1024).toString("utf8");
  assert.match(head, /<meta charset="UTF-8"/i);
  assert.match(page, /<title>Atlas update<\/title>/);
  const inline = [...page.replace(/<!--[\s\S]*?-->/g, "").matchAll(/<script\b([^>]*)>/g)]
    .filter((m) => !/\bsrc\s*=/.test(m[1]));
  assert.equal(inline.length, 0, "the page carries an inline script (CSP and the page test forbid it)");
});

/* ── Result ─────────────────────────────────────────────────────────────── */

if (fails.length) {
  console.log(`\n${fails.length} check(s) failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall update-window checks passed");
