/**
 * "What's new in Jarvis" (Task-50, Wave 12): the pane in Brain -> Tutorials
 * and the FAQ, drawn from the generated `jarvis_recent_changes.py` module.
 *
 * WHAT IS CHECKED
 *
 * * the pane renders the PC's own bullets, one row each, and nothing else -
 *   no invented change, no invented version;
 * * the module's own sentence for an empty record is the one shown, and no
 *   list is drawn under it;
 * * a PC without the read (an older backend) is told what to do, and is not
 *   shown an empty list that would read as "nothing changed";
 * * the ONE control, "Open Settings → Updates", asks `open_fix_place` for the
 *   `updates` place - Settings at its Updates card - and acts on nothing else;
 * * the pure helpers drop blanks and cap the list, so a malformed answer cannot
 *   draw a thousand rows.
 *
 * The words are the backend's throughout: `backend/test_recent_changes_read.py`
 * proves the route is a faithful read of the module, and this suite proves the
 * desktop does not add to it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import { whatsNewBullets, whatsNewWords } from "../src/tutorials.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The pure helpers, without a browser ─────────────────────────────────── */

await check("blank bullets are dropped and the list is capped", () => {
  assert.deepEqual(
    whatsNewBullets({ bullets: [" one ", "", null, "two", "   ", 3] }),
    ["one", "two", "3"]);
  assert.equal(whatsNewBullets({ bullets: Array.from({ length: 50 }, (_, i) => `c${i}`) }).length, 20);
  assert.deepEqual(whatsNewBullets({}), []);
  assert.deepEqual(whatsNewBullets(null), []);
});

await check("an empty record shows the module's own sentence, never a guess", () => {
  const own = "The newest changes are not written down beside the program on this PC, so I will not guess.";
  assert.equal(whatsNewWords({ empty_words: own }), own);
  // No sentence from the PC: this file has a plain fallback, and it is not a list.
  assert.match(whatsNewWords({}), /not written down/i);
});

/* ── The pane, in the real page ──────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 1180, height: 1100 };

async function tutorialsPage(data = {}) {
  const page = await K.open(browser, base, "brain.html", data, SIZE);
  await page.locator("#tab-tutorials").click();
  await K.until(page, "the What's new pane to draw",
    () => page.locator(".whats-new-body > *").count().then((n) => n > 0));
  return page;
}

const ANSWER = {
  ok: true,
  available: true,
  version: "0.2.320",
  bullets: [
    "Wave 10: one honest answer menu, a real receipt for the GitHub token",
    "Wave 9: the read-aloud switch and the five-suite benchmark",
  ],
  empty_words: "The newest changes are not written down beside the program on this PC, so I will not guess.",
};

await check("the pane shows the PC's own bullets, word for word, and nothing else", async () => {
  const page = await tutorialsPage({ recentChanges: ANSWER });
  const heading = await page.locator(".whats-new h3").innerText();
  const rows = await page.locator(".whats-new-list li").allInnerTexts();
  const version = await page.locator(".whats-new-version").innerText();
  await page.close();
  assert.equal(heading, "What's new in Jarvis");
  assert.deepEqual(rows, ANSWER.bullets,
    "the pane did not draw exactly the record's bullets");
  assert.match(version, /0\.2\.320/, `the version line said "${version}"`);
});

await check("a record with nothing in it says so, and draws no list", async () => {
  const page = await tutorialsPage({
    recentChanges: { ...ANSWER, version: "", bullets: [] },
  });
  const empty = await page.locator(".whats-new .empty").innerText();
  const rows = await page.locator(".whats-new-list li").count();
  await page.close();
  assert.equal(rows, 0, "an empty record still drew a list");
  assert.equal(empty.trim(), ANSWER.empty_words,
    "the pane did not use the module's own sentence");
});

await check("a PC without the read says what to do, not 'nothing changed'", async () => {
  // The default bridge answer is the shape an older backend gives.
  const page = await tutorialsPage();
  const problem = await page.locator(".whats-new .problem").innerText();
  const rows = await page.locator(".whats-new-list li").count();
  await page.close();
  assert.match(problem, /changes list/i, `said "${problem}"`);
  assert.match(problem, /apply-patches/i, "did not say what to do about it");
  assert.equal(rows, 0, "an unavailable read drew a list anyway");
});

await check("a read that failed is said, and the door is still offered", async () => {
  const page = await tutorialsPage({ recentChanges: { throws: "backend unreachable" } });
  const problem = await page.locator(".whats-new .problem").innerText();
  const door = await page.locator(".whats-new-open").isVisible();
  await page.close();
  assert.ok(problem.trim().length > 0, "a failed read said nothing");
  assert.equal(door, true, "the way to Settings -> Updates disappeared");
});

await check("the pane still draws when the tutorials read fails early", async () => {
  // `showTutorials` returns before its lists when the catalogue is unavailable;
  // the changes pane must not be left as a bare heading because of it.
  const page = await K.open(browser, base, "brain.html", {
    recentChanges: ANSWER,
    tutorials: { available: false, why: "This PC's Jarvis does not have the tutorials yet." },
  }, SIZE);
  await page.locator("#tab-tutorials").click();
  await K.until(page, "the What's new pane to draw beside the failure",
    () => page.locator(".whats-new-list li").count().then((n) => n > 0));
  const rows = await page.locator(".whats-new-list li").allInnerTexts();
  const door = await page.locator(".whats-new-open").isVisible();
  await page.close();
  assert.deepEqual(rows, ANSWER.bullets);
  assert.equal(door, true, "the door vanished with the tutorials read");
});

await check("the one button opens Settings at its Updates card, and does nothing else", async () => {
  const page = await tutorialsPage({ recentChanges: ANSWER });
  await page.locator(".whats-new-open").click();
  await K.until(page, "the button to say it opened",
    () => page.locator(".whats-new-said").innerText().then((t) => t.includes("Opened")));
  const calls = await page.evaluate(() => window.__calls);
  const said = await page.locator(".whats-new-said").innerText();
  await page.close();
  const places = calls.filter((c) => c[0] === "__openedPlace").map((c) => c[1]);
  assert.deepEqual(places, ["updates"],
    `the door asked for ${JSON.stringify(places)}, not the Updates card`);
  assert.match(said, /Opened/);
  // It asks for a place and nothing else: no install, no check, no approval.
  for (const forbidden of ["__installed", "__checked", "__updatedBoth", "__restarted"]) {
    assert.ok(!calls.some((c) => c[0] === forbidden),
      `the pane's button ran ${forbidden}`);
  }
});

await check("the pane only reads: one read command, and the navigation", async () => {
  const page = await tutorialsPage({ recentChanges: ANSWER });
  const names = await page.evaluate(() =>
    window.__calls.map((c) => c[0]).filter((n) => n !== "__openedPlace"));
  await page.close();
  assert.ok(names.includes("get_recent_changes"), "the pane never asked the PC");
  // A mutating COMMAND starts with one of these; `brain_memory_saved_unseen`
  // is a read despite the word "saved" in its name, so the match is anchored.
  const writes = names.filter((n) =>
    /^(install|update|approve|decide|set_|save_|mark_|delete|forget|erase|answer_)/.test(n));
  assert.deepEqual(writes, [], `opening the pane wrote something: ${writes.join(", ")}`);
});

/* ── The wiring, read from the real sources ─────────────────────────────── */

await check("CONTROL: the read is a real Tauri command against the real route", () => {
  const rust = read("src-tauri/src/tutorials.rs");
  assert.match(rust, /pub async fn get_recent_changes/,
    "the Brain has no read for the recent-changes module");
  assert.match(rust, /RECENT_CHANGES_PATH: &str = "\/api\/recent-changes"/,
    "the command does not call the backend route");
  const lib = read("src-tauri/src/lib.rs");
  assert.match(lib, /tutorials::get_recent_changes/,
    "the command is not registered, so the page's call would be refused");
  // The backend route is the module's own read: nothing here invents a list.
  const py = read("../backend/jarvis_brain_reads.py");
  assert.match(py, /RECENT_CHANGES_PATH = "\/api\/recent-changes"/);
  assert.match(py, /import jarvis_recent_changes as RC/,
    "the route does not read the generated module");
});

await check("CONTROL: the door is the Settings Updates place, and it is navigation only", () => {
  const rust = read("src-tauri/src/plain_errors.rs");
  const at = rust.indexOf("pub async fn open_fix_place");
  assert.notEqual(at, -1, "open_fix_place is gone");
  const body = rust.slice(at, rust.indexOf("\n}\n", at));
  assert.match(body, /"updates" => crate::windows::show_settings_at\(&app, "updates"\)/,
    "the door does not open Settings at its Updates card");
  // It navigation only: no CALL to anything that installs, updates or decides.
  // (Matched as calls, not as words - the comment above the arm says
  // "installed" while describing what the door does NOT do.)
  assert.ok(!/(install_update|update_both|answer_approval|decide_approval)\(/.test(body),
    "the navigation command started to act as well");
});

console.log(`\n${fails.length ? `${fails.length} failed` : "0 failed"}`);
await browser.close();
close();
process.exit(fails.length ? 1 : 0);
