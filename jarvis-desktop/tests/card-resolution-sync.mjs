/**
 * A card answered anywhere leaves every desktop surface, and all of them follow
 * ONE list (2026-10-29).
 *
 * The owner's report: *"when a decision/approval card has already been addressed
 * (approved or denied) on either the Android app or the desktop program, make
 * sure the Android widgets (and every other surface that shows a
 * card/notification) update to reflect that - no stale card left showing, no
 * dead Approve/Deny on a resolved card."*
 *
 *     node tests/card-resolution-sync.mjs
 *
 * The queue was already one list: `stream.rs`'s `refresh_pending` re-reads
 * `/api/pending` once and hands the same rows to every window
 * (`approvals-changed`), and `jarvis-link.js` is the only thing the bar, the
 * widget and the Brain subscribe to. What this file holds is the half that was
 * missing - each surface actually REMOVING a card when the list no longer holds
 * it, and the one signal they all remove it on - because "one source" is worth
 * nothing if a window keeps drawing from its own copy of the last read.
 *
 * What it drives, with no browser:
 *   1. the HUD page (`jarvis_hud.html`) drops a card whose id left the queue,
 *      and hides the box when the queue is empty;
 *   2. the Jarvis bar (`main.js`) closes the open card when the queue no longer
 *      holds it - by ID, not by "is the queue empty", so two cards do not hide
 *      each other;
 *   3. the widget (`widget.js`) does the same, and also closes on
 *      `approval-resolved`, the instant a decision is accepted on this PC;
 *   4. the two pages subscribe to `jarvis-link.js` rather than fetching the
 *      queue themselves, so "one list" is structural rather than a promise;
 *   5. Rust emits `approvals-changed` from the one read (`refresh_pending`),
 *      which is also what the 30-second fallback beat re-uses - so a decision
 *      made elsewhere reaches every surface even when the `approval` event was
 *      missed (`queue_beat_due`).
 *
 * Comments are stripped before anything is looked for, so no assertion here can
 * be satisfied by a comment that names the same thing on purpose.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const page = (name) => readFileSync(join(SRC, name), "utf8");
const rust = () =>
  readFileSync(join(HERE, "..", "src-tauri", "src", "stream.rs"), "utf8");

/** Comments become empty lines, so a comment cannot satisfy an assertion. */
function code(text) {
  const out = [];
  let inBlock = false;
  for (const line of text.split("\n")) {
    const t = line.trimStart();
    if (inBlock) {
      if (t.includes("*/")) inBlock = false;
      out.push("");
      continue;
    }
    if (t.startsWith("/*") || t.startsWith("/**")) {
      if (!t.includes("*/")) inBlock = true;
      out.push("");
      continue;
    }
    if (t.startsWith("//")) {
      out.push("");
      continue;
    }
    // A line that ends in a block comment: keep the code before it.
    out.push(line.replace(/\/\*.*?\*\//g, ""));
  }
  return out.join("\n");
}

/** The body of one call/function, from its opening line to the matching brace. */
function block(text, opener) {
  const from = text.indexOf(opener);
  assert.ok(from >= 0, `'${opener}' is gone`);
  let depth = 0;
  let started = false;
  for (let i = from; i < text.length; i++) {
    if (text[i] === "{") {
      depth++;
      started = true;
    } else if (text[i] === "}") {
      depth--;
      if (started && depth === 0) return text.slice(from, i + 1);
    }
  }
  throw new Error(`unbalanced braces after '${opener}'`);
}

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

// ---------------------------------------------------------------- the HUD ----

check("the HUD page drops a card whose id left the queue, and hides an empty box", () => {
  const hud = code(page("jarvis_hud.html"));
  const poll = block(hud, "async function apprPoll(");
  assert.match(
    poll,
    /box\.hidden\s*=\s*list\.length === 0/,
    "an empty queue must HIDE the box, not leave the last card standing",
  );
  assert.match(
    poll,
    /\[\.\.\.box\.children\]\.forEach\(/,
    "every card already on the page is examined on each read",
  );
  assert.match(
    poll,
    /if\(!want\.has\(el\.dataset\.id\)\)\s*el\.remove\(\)/,
    "cards the queue no longer holds must be removed by id",
  );
  assert.match(
    poll,
    /const want = new Set\(list\.map\(p => p\.id\)\)/,
    "the removal must be keyed on the fresh read, not on the old DOM",
  );
});

check("the HUD page has its own fallback read, not only the event", () => {
  // The page cannot receive Tauri events; it holds its own EventSource AND a
  // 30-second net. This is the number `QueueBeat` (phone) and `QUEUE_BEAT`
  // (stream.rs) were both set to, so a card is never staler than one beat.
  const hud = code(page("jarvis_hud.html"));
  assert.match(hud, /es\.addEventListener\("approval"/, "the page must follow the approval event");
  assert.match(
    hud,
    /setInterval\(\(\) => \{ apprPoll\(\); initPoll\(\); loadPresets\(\); \}, 30000\)/,
    "the page's own safety net is 30 seconds",
  );
});

// ---------------------------------------------------------------- the bar ----

check("the Jarvis bar closes the open card when the queue no longer holds it", () => {
  const bar = code(page("main.js"));
  const handler = block(bar, "onQueue((queue) => {");
  assert.match(
    handler,
    /const open = queue\.items\.find\(\(item\) => !state\.parked\.has\(item\.id\)\) \|\| null/,
    "the bar must ask the queue which card is left, not keep its own",
  );
  assert.match(
    handler,
    /if \(!open\) \{[\s\S]*?closeApproval\(\)/,
    "no card left in the queue must close whatever the bar is showing",
  );
  // Two cards must not hide each other: the close is driven by "no card left",
  // never by "this particular id is not the first one".
  assert.doesNotMatch(
    handler,
    /queue\.items\.length === 0\)\s*closeApproval/,
    "closing must not be a length test - an answered card with another behind it still has to go",
  );
});

check("the bar closes on approval-resolved too, the instant a decision lands", () => {
  const bar = code(page("main.js"));
  const handler = block(bar, 'listen("approval-resolved", (event) => {');
  assert.match(handler, /closeApproval\(\)/);
  assert.match(
    handler,
    /String\(resolved\.id\) !== state\.approval\.id/,
    "and checks the id, so resolving one card does not hide another",
  );
});

// ------------------------------------------------------------- the widget ----

check("the widget closes a card the queue no longer holds", () => {
  const widget = code(page("widget.js"));
  const handler = block(widget, "onQueue((queue) => {");
  assert.match(handler, /const open = queue\.items\[0\] \|\| null/);
  assert.match(
    handler,
    /if \(open\) openApproval\(open\);\s*else if \(state\.approval\) closeApproval\(\)/,
    "an empty queue must close the widget's card",
  );
});

check("the widget closes on approval-resolved, and only for the card it shows", () => {
  const widget = code(page("widget.js"));
  const handler = block(widget, 'listen("approval-resolved", (event) => {');
  assert.match(handler, /closeApproval\(\)/);
  assert.match(
    handler,
    /String\(resolved\.id\) !== state\.approval\.id\) return/,
    "a resolution for another card must not close this one",
  );
});

// --------------------------------------------------------- one list only ----

check("both pages take the queue from jarvis-link, so there is one list", () => {
  const link = code(page("jarvis-link.js"));
  assert.match(
    link,
    /TAURI\.event\.listen\(EV_APPROVALS/,
    "jarvis-link must be the one subscriber to approvals-changed",
  );
  assert.match(link, /export function onQueue/, "and it must expose the queue");
  for (const name of ["main.js", "widget.js"]) {
    const src = code(page(name));
    assert.match(
      src,
      /from "\.\/jarvis-link\.js"/,
      `${name} must import the one module`,
    );
    assert.match(src, /\bonQueue\b/, `${name} must subscribe to it`);
    assert.doesNotMatch(
      src,
      /fetch\(["'`]\/api\/pending/,
      `${name} must not read the queue itself - a second list is the bug`,
    );
  }
});

// ------------------------------------------------ the read behind them ----

check("Rust emits approvals-changed from the one read, and the beat re-uses it", () => {
  const src = code(rust());
  const refresh = block(src, "async fn refresh_pending(");
  assert.match(
    refresh,
    /crate::events::APPROVALS_CHANGED/,
    "the one read is what every window hears about",
  );
  assert.match(
    refresh,
    /state\s*\.pending\s*\.lock\(\)/,
    "and it is the read that replaces the cached queue",
  );
  assert.match(
    refresh,
    /publish_link\(app, \|link\| queue_read_landed\(link, items\.len\(\)\)\)/,
    "the tray's count comes from the same read, and a connected success clears stale",
  );
  // The fallback beat calls THAT function rather than a second reader.
  const beat = block(src, "ReadStep::Beat => {");
  assert.match(
    beat,
    /if queue_beat_due\(link\.connected, link\.approvals\) \{[\s\S]*?refresh_pending\(app, base\)\.await/,
    "the beat must re-read through the one queue read",
  );
  assert.doesNotMatch(
    beat,
    /last_chunk_at/,
    "the beat must never move the silence deadline",
  );
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall card-resolution-sync checks passed");
