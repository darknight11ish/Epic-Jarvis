/**
 * onboarding.mjs - the first-run walkthrough, read as the page a new owner
 * actually meets.
 *
 *     node tests/onboarding.mjs
 *
 * No browser: the walkthrough is static text and one small script, and what
 * matters about it is what it SAYS and that it says it once. The findings this
 * file pins down come from the 2026-10-05 UI audit, section 5 and its "what I
 * would change" row 3:
 *
 *   * "the app's onboarding teaches nothing about the product's central idea
 *     - the approval card. A new owner meets their first card with no
 *     explanation of what it grants, what it does not, or what happens if
 *     they refuse";
 *   * "what Jarvis can reach" was nowhere in the walkthrough;
 *   * and the ease-of-use work that landed with it ("3 examples on screen 2",
 *     the memory screen's exact words) must keep working, which is why the
 *     new screens were added ON THE END rather than in the middle.
 *
 * tests/sayable.mjs, tests/faq.mjs and tests/auto-learn.mjs already hold the
 * words of screens 1-3 to their own contracts; this file holds the SHAPE and
 * the new half, so the two cannot drift.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const page = (name) => readFileSync(join(SRC, name), "utf8");

const HTML = page("onboarding.html");
const RUST = readFileSync(join(HERE, "..", "src-tauri", "src", "commands.rs"), "utf8");
const WINDOWS = readFileSync(join(HERE, "..", "src-tauri", "src", "windows.rs"), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** Every screen, with its number, hidden state and text. */
const screens = (() => {
  const out = [...HTML.matchAll(/<section class="screen" id="screen-(\d+)" data-n="(\d+)"([^>]*)>([\s\S]*?)<\/section>/g)]
    .map((m) => ({
      n: Number(m[1]),
      dataN: Number(m[2]),
      hidden: /\bhidden\b/.test(m[3]),
      html: m[4],
      text: m[4].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim(),
    }));
  return out;
})();
const byN = (n) => screens.find((s) => s.n === n);

/* ── The shape: a few steps, one on screen, skippable ───────────────────── */

check("the walkthrough is a handful of ordered screens, never more", () => {
  assert.ok(screens.length >= 4 && screens.length <= 6,
    `${screens.length} screens: the owner asked for a handful, not a manual`);
  assert.deepEqual(screens.map((s) => s.n), screens.map((_, i) => i + 1),
    "the screens are not numbered in order");
  for (const s of screens) {
    assert.equal(s.dataN, s.n, `screen ${s.n} draws a different dot than its own number`);
  }
  // Exactly one is on screen at load: the first.
  assert.equal(byN(1).hidden, false, "the first screen starts hidden, so the window opens empty");
  for (const s of screens.slice(1)) {
    assert.equal(s.hidden, true, `screen ${s.n} is on screen at the same time as screen 1`);
  }
});

check("the script counts the same screens the page draws", () => {
  const steps = Number((HTML.match(/const STEPS = (\d+);/) || [])[1]);
  assert.equal(steps, screens.length, `STEPS is ${steps} and there are ${screens.length} screens`);
  const dots = (HTML.match(/<span[^>]*data-n="\d+"[^>]*><\/span>/g) || []).length;
  assert.equal(dots, screens.length, `${dots} dots for ${screens.length} screens`);
});

check("every screen is short enough for one sitting", () => {
  for (const s of screens) {
    assert.ok(s.text.length > 80, `screen ${s.n} says almost nothing`);
    assert.ok(s.text.length < 1100, `screen ${s.n} is ${s.text.length} characters - a wall of text`);
    const words = s.text.split(/\s+/).length;
    assert.ok(words < 170, `screen ${s.n} is ${words} words`);
  }
});

check("the walkthrough can be skipped at any point, and never comes back", () => {
  // Esc closes it from anywhere, and the last screen's button says what it
  // does; the marker is a version in Rust, so "once" is a fact about the
  // store and not about the page.
  assert.match(HTML, /event\.key === "Escape"/, "there is no way out but the button");
  assert.match(HTML, /if \(event\.key === "Escape"\) finish\(\)/,
    "Escape does not close the walkthrough");
  assert.match(HTML, /invoke\("finish_onboarding"\)/, "the walkthrough never marks itself seen");
  assert.match(RUST, /pub const ONBOARDING_VERSION: u64 = \d;/);
  assert.match(RUST, /store\.set\(\s*ONBOARDING_VERSION_KEY/, "the marker is never written");
  assert.ok(!/onboarding_seen/.test(HTML), "the page reads the old yes/no marker");
  // Shown at most once per install: lib.rs asks before building the window.
  assert.match(WINDOWS, /commands::onboarding_seen/,
    "the walkthrough window is built without asking whether it has been seen");
});

/* ── What a new owner must be told ──────────────────────────────────────── */

const ALL = screens.map((s) => s.text).join(" ");

check("it says what Jarvis is and that it runs on this PC", () => {
  assert.match(ALL, /on this PC|on this machine|this machine/i,
    "nothing tells a new owner where Jarvis runs");
  assert.match(ALL, /memory and your chat history\s+are all on this machine|stays here/i,
    "the promise that private things stay on the PC is not made");
});

check("it says how to talk to it", () => {
  const screen = screens.find((s) => /talking to it/i.test(s.text));
  assert.ok(screen, "no screen is about talking to Jarvis");
  assert.match(screen.html, /Alt<\/kbd>\+<kbd>Space/, "the way in (Alt+Space) is not named");
  assert.match(screen.html, /<kbd>Enter<\/kbd>/, "there is no word about Enter");
  assert.match(screen.text, /microphone/i, "the talk button is never mentioned");
  assert.match(screen.html, /<kbd>Esc<\/kbd>/, "there is no word about getting rid of the bar");
});

check("it says where the settings live", () => {
  const screen = screens.find((s) => /settings/i.test(s.text) && /tray/i.test(s.text));
  assert.ok(screen, "no screen says where the settings are");
  assert.match(screen.text, /jump list/i, "the settings page's own way around is not described");
  assert.match(screen.text, /What asks first/i, "the settings screen never points at What asks first");
});

check("it explains the approval card, which the audit says was missing", () => {
  // "A new owner meets their first card with no explanation of what it
  // grants, what it does not, or what happens if they refuse."
  const screen = screens.find((s) => /asks before anything risky/i.test(s.text));
  assert.ok(screen, "the approval screen is gone");
  assert.match(screen.text, /Approve/, "the card's Approve button is not named");
  assert.match(screen.text, /Deny/, "the card's Deny button is not named");
  // What it does NOT grant, in the project's own words for it.
  assert.match(screen.text, /one action, and only that one/i,
    "the card is not said to be one action only");
  assert.match(screen.text, /does not\s+allow that kind of thing in future/i,
    "the walkthrough never says approving is not a standing permission");
  assert.match(screen.text, /no .approve\s+everything. button/i,
    "the walkthrough never says there is no approve-everything");
  // ...and what happens if they refuse.
  assert.match(screen.text, /always say no/i, "refusing is not said to be safe");
  // The shared sentence the FAQ and voice.rs hold to the same words is intact.
  assert.match(screen.html, /<span class="approve-where">[\s\S]*?<\/span>/,
    "the shared 'where you approve' sentence lost its span (tests/faq.mjs holds its words)");
});

check("it points at what Jarvis can reach, which the audit asked for", () => {
  // Row 3 of the audit's list: 'put "What Jarvis can reach" on the first
  // screen'. It is on the settings screen here, NAMED in the walkthrough's
  // own words - see the report for why it is not on screen 1: the first
  // screen's numbering and wording are held by three other suites, and the
  // audit's own words are that the app "cannot install this yet", so the
  // first screen stays the one every new owner can act on today.
  assert.match(ALL, /What\s+Jarvis can reach/,
    "the walkthrough never names the page that lists every way out of the PC");
  const screen = screens.find((s) => /What\s+Jarvis can reach/.test(s.text));
  assert.match(screen.text, /way out of this PC/i, "the page is named without saying what it is for");
});

check("the memory screen the earlier walkthrough shipped is untouched", () => {
  // tests/auto-learn.mjs holds screens 3's exact words, and screen 3's number
  // is what tests/sayable.mjs slices the file by - so the new screens went on
  // the end and this one did not move.
  const s3 = byN(3);
  assert.match(s3.text, /your own words/);
  assert.match(s3.text, /Forget/);
  assert.match(s3.text, /wait for your yes/);
  assert.match(s3.text, /memory/i);
});

/* ── The words the owner reads are plain ────────────────────────────────── */

check("no jargon and no code names on any screen", () => {
  for (const s of screens) {
    for (const jargon of ["Tauri", "IPC", "invoke", "JSON", "repo", "backend",
      "localhost", "API", "token", "WebView", "config"]) {
      assert.ok(!new RegExp(`\\b${jargon}\\b`, "i").test(s.text),
        `screen ${s.n} says "${jargon}" to a beginner`);
    }
  }
});

check("the screen headers count themselves honestly", () => {
  for (const s of screens) {
    assert.match(s.html, new RegExp(`${s.n} of ${screens.length}`),
      `screen ${s.n} is not labelled "${s.n} of ${screens.length}"`);
  }
});

check("the last screen's button says it finishes, not just Next", () => {
  assert.match(HTML, /step === STEPS \? "Got it/,
    "the last screen's button still says Next, so nothing says this is the end");
});

check("CONTROL: the walkthrough still asks for nothing but the theme", () => {
  // It is the first window anyone sees, before the backend exists. It may
  // read the theme and close itself - nothing else.
  const calls = [...HTML.matchAll(/invoke\("([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(calls)].sort(), ["finish_onboarding", "get_theme"],
    `the walkthrough asks Rust for: ${calls.join(", ")}`);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log(`\n${screens.length} screens: what it is, the card, memory, talking to it, the settings.`);
