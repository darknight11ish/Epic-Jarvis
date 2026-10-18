/**
 * Clipboard history (Pillar 14B) — the drawer's own logic, in plain node.
 *
 * The ring, the refusals and the three transforms live in Rust
 * (`src-tauri/src/clipboard_time_machine.rs`) and are tested by `cargo test`;
 * this suite covers the half a Rust test cannot see: what the Quickbar drawer
 * SAYS and DRAWS from whatever Rust answered. The functions under test are
 * pure - `src/clipboard-drawer.js` only touches the DOM inside its `mount`
 * function, which this file never calls - so no browser and no Tauri bridge
 * are needed, and CI's frontend job runs this file like every other
 * `tests/*.mjs`.
 *
 * What must hold, in the owner's words:
 *   - OFF is the first thing the drawer says, and turning it on is its own
 *     explicit button - nothing is kept before that;
 *   - while locked, nothing is drawn at all, even if a stale answer said a
 *     copy was kept (the ring wipes itself on lock; the drawer fails closed);
 *   - a transform's answer is either copyable, or the Rust refusal's own plain
 *     words - never a half-transformed table shown as if it worked;
 *   - the three buttons are exactly the three deterministic transforms.
 */
import assert from "node:assert/strict";
import {
  TRANSFORMS,
  WORDS,
  fromLine,
  kindLabel,
  mountClipboardDrawer,
  previewText,
  rowFor,
  transformWords,
  view,
} from "../src/clipboard-drawer.js";

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

const COPY = (text, app = "Code.exe", title = "notes.py") => ({ text, app, title });

/* ── The three transforms are the advertised three ──────────────────────── */

check("the drawer offers exactly the three deterministic transforms", () => {
  assert.deepEqual(
    TRANSFORMS.map((t) => t.kind),
    ["markdown_table", "pretty_json", "strip_tracking_params"],
  );
  // Each one is a button with words a beginner can read and a title that says
  // what it will do - no transform is an unlabelled icon.
  for (const step of TRANSFORMS) {
    assert.ok(step.label.length > 0, `${step.kind} has no label`);
    assert.ok(step.title.length > step.label.length, `${step.kind} has no explanation`);
  }
});

check("a kind is named in the drawer's words, and unknown kinds fall back", () => {
  assert.equal(kindLabel("markdown_table"), "Table");
  assert.equal(kindLabel("pretty_json"), "Pretty JSON");
  assert.equal(kindLabel("strip_tracking_params"), "Clean link");
  assert.equal(kindLabel("make_it_pretty"), "make_it_pretty");
  assert.equal(kindLabel(null), "");
});

/* ── Previews: one flat line, never a wall of copied text ───────────────── */

check("a copy becomes one flat, short preview line", () => {
  assert.equal(previewText("  one\n\n  two\tthree  "), "one two three");
  assert.equal(previewText(""), "");
  assert.equal(previewText(null), "");
  const long = "x".repeat(400);
  const shown = previewText(long, 40);
  assert.equal([...shown].length, 40);
  assert.ok(shown.endsWith("…"), "a cut preview does not say it was cut");
  // Counted in characters, not UTF-16 units: an emoji is one character and
  // the preview must not end in half of one.
  const emoji = previewText("😀".repeat(300), 20);
  assert.equal([...emoji].length, 20);
  assert.equal(emoji, "😀".repeat(19) + "…");
});

check("where a copy came from is one line, and may be empty", () => {
  assert.equal(fromLine(COPY("x", "Code.exe", "notes.py")), "Code.exe · notes.py");
  assert.equal(fromLine(COPY("x", "Code.exe", "")), "Code.exe");
  assert.equal(fromLine(COPY("x", "", "notes.py")), "notes.py");
  assert.equal(fromLine(COPY("x", "", "")), "");
  assert.equal(fromLine(null), "");
});

check("a row keeps its place, so a transform asks about the right copy", () => {
  const row = rowFor(COPY("second"), 1);
  assert.equal(row.index, 1);
  assert.equal(row.preview, "second");
  assert.equal(row.from, "Code.exe · notes.py");
});

/* ── OFF by default, and LOUD about it ──────────────────────────────────── */

check("CONTROL: before it is turned on the drawer says Off and keeps nothing", () => {
  const shown = view({ enabled: false, locked: false, items: [], max_items: 25 });
  assert.equal(shown.enabled, false);
  assert.equal(shown.rows.length, 0);
  assert.equal(shown.status, "Off");
  assert.match(shown.line, /Nothing you copy is being kept/i);
  // The one control offered is turning it on.
  assert.equal(shown.canEnable, true);
  assert.equal(shown.canDisable, false);
  assert.equal(shown.canForget, false);
  assert.equal(shown.canLock, false);
});

check("the off line and the privacy line make the promises this feature keeps", () => {
  // These are the words the owner reads before pressing Turn on. They must
  // keep saying: memory only, never disk, off now, forgotten on lock.
  assert.match(WORDS.offLine, /memory only/i);
  assert.match(WORDS.offLine, /never on disk/i);
  assert.match(WORDS.offLine, /until you turn it off/i);
  assert.match(WORDS.onLine, /memory only/i);
  assert.match(WORDS.onLine, /forgotten when Jarvis locks/i);
  assert.match(WORDS.privacy, /password managers/i);
  assert.match(WORDS.privacy, /one-time codes/i);
  assert.match(WORDS.privacy, /card numbers/i);
  assert.match(WORDS.privacy, /never kept/i);
  assert.match(WORDS.privacy, /nothing here leaves this PC/i);
});

/* ── Locked fails closed ────────────────────────────────────────────────── */

check("while locked nothing is drawn, even if the state still holds copies", () => {
  const shown = view({
    enabled: true,
    locked: true,
    items: [COPY("a secret the lock already forgot")],
  });
  assert.equal(shown.locked, true);
  assert.equal(shown.rows.length, 0, "a locked drawer drew a kept copy");
  assert.equal(shown.status, "Locked");
  assert.equal(shown.line, WORDS.locked);
  assert.equal(shown.canEnable, false);
  assert.equal(shown.canDisable, false);
  assert.equal(shown.canForget, false);
  assert.equal(shown.canLock, false);
});

check("CONTROL: with the same state unlocked, the copy IS drawn", () => {
  // The control for the check above: the lock is what hides it, not a broken
  // fixture.
  const shown = view({ enabled: true, locked: false, items: [COPY("copy one")] });
  assert.equal(shown.rows.length, 1);
  assert.equal(shown.rows[0].preview, "copy one");
  assert.equal(shown.rows[0].index, 0);
});

/* ── On, empty, and filling up ──────────────────────────────────────────── */

check("an empty ring that is on says so, and offers the way to forget nothing", () => {
  const shown = view({ enabled: true, locked: false, items: [] });
  assert.equal(shown.status, "On");
  assert.match(shown.line, /Nothing kept yet/i);
  assert.equal(shown.canEnable, false);
  assert.equal(shown.canDisable, true);
  assert.equal(shown.canForget, false);
  assert.equal(shown.canLock, true);
});

check("each kept copy is one row, newest first, with its own transform buttons", () => {
  const shown = view({
    enabled: true,
    locked: false,
    items: [COPY("newest"), COPY("middle"), COPY("oldest")],
  });
  assert.deepEqual(shown.rows.map((r) => r.preview), ["newest", "middle", "oldest"]);
  assert.deepEqual(shown.rows.map((r) => r.index), [0, 1, 2]);
  assert.equal(shown.canForget, true);
  assert.equal(shown.canLock, true);
});

check("a switch that is off can still have copies from before it was turned off", () => {
  // Turning capture off does not discard what was already kept; only "Forget"
  // and a lock do (the Rust ring's rule, mirrored in what the drawer shows).
  const shown = view({ enabled: false, locked: false, items: [COPY("kept earlier")] });
  assert.equal(shown.status, "Off");
  assert.equal(shown.rows.length, 1);
  assert.equal(shown.canEnable, true);
  assert.equal(shown.canForget, true);
});

/* ── A transform's answer ───────────────────────────────────────────────── */

check("a successful transform is shown and can be copied", () => {
  const shown = transformWords({ ok: true, kind: "pretty_json", text: '{\n  "a": 1\n}', reason: "" });
  assert.equal(shown.canCopy, true);
  assert.equal(shown.line, "");
  assert.equal(shown.text, '{\n  "a": 1\n}');
});

check("a refused transform says the PC's own plain reason and cannot be copied", () => {
  for (const reason of [
    "a table needs at least 2 rows",
    "a table needs at least 2 columns",
    "every row needs the same number of columns",
    "that is not valid JSON",
    "that is not a transform I know",
  ]) {
    const shown = transformWords({ ok: false, kind: "markdown_table", text: "", reason });
    assert.equal(shown.canCopy, false, `a refusal could be copied: ${reason}`);
    assert.equal(shown.line, reason);
    assert.equal(shown.text, "");
  }
});

check("a broken or missing answer is refused in the same words, never copied", () => {
  for (const answer of [null, undefined, "ok", 7, {}]) {
    const shown = transformWords(answer);
    assert.equal(shown.canCopy, false);
    assert.equal(shown.text, "");
    assert.ok(shown.line.length > 0);
  }
  // An `ok` answer with no text is still an answer that carries no words: the
  // copy button would copy nothing, so it is not offered as text.
  const empty = transformWords({ ok: true, text: "", reason: "" });
  assert.equal(empty.canCopy, true);
  assert.equal(empty.text, "");
});

/* ── No readable state at all ───────────────────────────────────────────── */

check("with no bridge at all the drawer says it is unavailable and offers nothing", () => {
  const shown = view(null);
  assert.equal(shown.readable, false);
  assert.equal(shown.rows.length, 0);
  assert.equal(shown.line, WORDS.unreadable);
  assert.equal(shown.canEnable, false, "offered a switch it cannot reach");
  assert.equal(shown.canDisable, false);
  assert.equal(shown.canForget, false);
  assert.equal(shown.canLock, false);
});

check("the drawer is mountable from this module", () => {
  // It is a function; mounting it is main.js's job (and needs a DOM), not this
  // suite's. A missing export would otherwise silently leave the hotkey with
  // no drawer at all.
  assert.equal(typeof mountClipboardDrawer, "function");
});

if (fails.length) {
  console.error(`\n${fails.length} clipboard drawer check(s) failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nAll clipboard drawer checks passed.");
