/**
 * "Was this answer right?" typed in the HUD box must open the caret menu under
 * the last answer, not become a chat turn.
 *
 *   node tests/hud-answer-route.mjs
 *
 * The owner's field test, 2026-11-01: he typed that into the desktop HUD's chat
 * box and the model answered it as a question. The menu wave-2 added under
 * every finished answer already asks exactly that, so the words belong there.
 *
 * No browser needed. The page's send() and the small recogniser it calls are
 * pinned by source, and the recogniser itself is EXTRACTED FROM THE PAGE AND
 * RUN here - so the allow-list and the near-misses are tested as behaviour, not
 * as text. The real click is driven end to end by the Playwright case in
 * tests/hud.mjs ("typing 'was this answer right?' opens ...").
 *
 * What this suite exists to stop:
 *   - the model being sent the phrase again (the gap the owner found);
 *   - a user bubble (a chat turn that never happened);
 *   - the allow-list widening until a real question ("was that right about the
 *     weather?") is swallowed - a miss is harmless, a hijack is not;
 *   - the caret click moving to the wrong answer, or to no answer at all;
 *   - the three vendored copies of the page drifting apart.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, "..", "src", "jarvis_hud.html");
const SRC = readFileSync(SRC_PATH, "utf8");

/** The page is vendored three times and the copies must stay byte-identical:
 *  the desktop app serves src/, the published base carries backend/, and the
 *  backend test suite compares them (backend/test_vendored_three.py). */
const COPIES = [
  ["desktop src", SRC_PATH],
  ["backend", join(HERE, "..", "..", "backend", "jarvis_hud.html")],
  ["jarvis-backend", join(HERE, "..", "..", "jarvis-backend", "jarvis_hud.html")],
];

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

/** Everything between `start` and the brace that closes it, counting braces. */
function balancedBraces(text, start) {
  let depth = 0;
  let opened = false;
  for (let at = start; at < text.length; at += 1) {
    const ch = text[at];
    if (ch === "{") { depth += 1; opened = true; }
    else if (ch === "}") {
      depth -= 1;
      if (opened && depth === 0) return text.slice(start, at + 1);
    }
  }
  throw new Error(`a brace opened at ${start} is never closed`);
}

/** The page's own answerMarkAsk(), cut out of the page so it can be CALLED.
 *  It touches no DOM and no browser state, so this is the real function the
 *  page runs, not a copy of it. */
function helperFromPage() {
  const start = SRC.indexOf("function answerMarkAsk(");
  assert.ok(start >= 0, "the HUD page has no answerMarkAsk() helper at all");
  const end = SRC.indexOf("{", start);
  assert.ok(end > start, "answerMarkAsk() has no body");
  const body = balancedBraces(SRC, end);
  return new Function(`return ${SRC.slice(start, end)}${body}`)();
}

/** send()'s own body: from its declaration to the first line that is just "}". */
function sendBody() {
  const start = SRC.indexOf("async function send(){");
  assert.ok(start >= 0, "the HUD page has no send() function");
  const end = SRC.indexOf("\n}", start);
  assert.ok(end > start, "send() never closes");
  return SRC.slice(start, end);
}

const SEND = sendBody();
const HELPER_SOURCE = (() => {
  const start = SRC.indexOf("function answerMarkAsk(");
  const brace = SRC.indexOf("{", start);
  const end = brace + balancedBraces(SRC, brace).length;
  // The plain-words comment directly above the function is pinned too: it is
  // where the owner's field test and the reason for the short list are named.
  const doc = SRC.lastIndexOf("// The owner's field test, 2026-11-01", start);
  return SRC.slice(doc >= 0 ? doc : start, end);
})();

check("the page has the recogniser, and it is the one this suite runs", () => {
  const mark = helperFromPage();
  assert.equal(typeof mark, "function", "answerMarkAsk is not a function");
  // The real function, run: the six asks the owner uses, with the punctuation
  // and capitals he actually types.
  for (const ask of [
    "was this answer right",
    "was that answer right",
    "was the last answer right",
    "was the previous answer right",
    "was this right",
    "was that right",
  ]) {
    assert.equal(mark(ask), true, `the owner's own ask is not recognised: ${ask}`);
  }
  for (const typed of [
    "Was this answer right?",
    "  WAS   this   answer   RIGHT?  ",
    "was this answer right.",
    "was that right?!",
    "hey jarvis, was this answer right?",
    "Hey Jarvis was that right",
    "jarvis, was the last answer right?",
    "jarvis was the previous answer right",
  ]) {
    assert.equal(mark(typed), true, `a normal way of typing the ask is not recognised: ${typed}`);
  }
});

check("the allow-list stays tight: a real question is never hijacked", () => {
  const mark = helperFromPage();
  for (const question of [
    "was this right for you",
    "was that right about the weather",
    "is this answer right",
    "was my answer right",
    "was the answer correct",
    "was this answer right for me",
    "was that the right answer",
    "was the last one right",
    "was this answer right or wrong",
    "tell me was this answer right",
    "was this answer",
    "",
  ]) {
    assert.equal(mark(question), false, `a real question was swallowed as an answer mark: ${question}`);
  }
});

check("the words are normalised, and the match is the WHOLE sentence", () => {
  assert.match(HELPER_SOURCE, /\.toLowerCase\(\)/, "the helper does not lower-case the words");
  assert.match(HELPER_SOURCE, /replace\(\/\\s\+\/g, " "\)/, "the helper does not collapse internal whitespace");
  assert.match(HELPER_SOURCE, /replace\(\/\[\?!\.\]\+\$\/, ""\)/, "the helper does not strip trailing ? ! .");
  assert.match(HELPER_SOURCE, /\(\?:hey\\s\+jarvis\|jarvis\)/, "the helper has no leading hey jarvis / jarvis form");
  assert.match(HELPER_SOURCE, /\^\(\?:.*\)\$/, "the helper is not anchored to the whole sentence");
});

check("send() asks the recogniser BEFORE the turn, the bubble or the request", () => {
  const at = (needle) => {
    const i = SEND.indexOf(needle);
    assert.ok(i >= 0, `send() no longer contains ${needle}`);
    return i;
  };
  const gate = at("if(answerMarkAsk(text)){");
  assert.ok(at('const text = $("input").value.trim();') < gate, "the check runs before the words are read");
  assert.ok(at("if(!text) return;") < gate, "the empty-box guard no longer comes first");
  assert.ok(gate < at("turnRoute = null;"), "the mark still clears the turn state");
  assert.ok(gate < at("if(SEND_INFLIGHT)"), "the mark still cancels a running answer");
  assert.ok(gate < at('addMessage("user"'), "the mark still draws a user bubble");
  assert.ok(gate < at("S.messages.push"), "the mark still joins the chat history");
  assert.ok(gate < at('jfetch("/api/chat"'), "the mark still reaches the PC");
});

check("a matched ask clears the box, opens the LAST caret, and returns", () => {
  const gate = SEND.indexOf("if(answerMarkAsk(text)){");
  const end = SEND.indexOf("  // CLEARED AT THE START OF EVERY TURN", gate);
  assert.ok(end > gate, "the mark branch has no clear end");
  const branch = SEND.slice(gate, end);
  // The box is emptied exactly as a normal send empties it...
  const clear = branch.indexOf('$("input").value = "";');
  assert.ok(clear >= 0, "the mark does not clear the box");
  assert.ok(branch.includes('$("input").style.height = "auto";'), "the mark does not reset the box's height");
  // ...and the caret is found in the page's own log, newest last.
  const find = branch.indexOf('const carets = document.querySelectorAll("#log .jarvis-answer-caret");');
  assert.ok(find > clear, "the caret is looked up before the box is cleared, or not at all");
  assert.match(branch, /const last = carets\[carets\.length - 1\];/,
    "the mark does not take the LAST caret (the newest finished answer)");
  assert.match(branch, /last\.click\(\)/, "the mark does not open the menu the way a click does");
  assert.match(branch, /return;/, "the mark branch does not return");
  // No bubble, no history, no request, and never a fabricated answer.
  assert.doesNotMatch(branch, /addMessage\("user"/, "the mark drew a user bubble");
  assert.doesNotMatch(branch, /addMessage\("jarvis"/, "the mark invented an answer in Jarvis's voice");
  assert.doesNotMatch(branch, /jfetch\(|fetch\(|XMLHttpRequest|POST/,
    "the mark branch talks to the PC - it must not");
  assert.doesNotMatch(branch, /S\.messages\.push/, "the mark joined the chat history");
});

check("no finished answer yet: one honest system line, and nothing sent", () => {
  const gate = SEND.indexOf("if(answerMarkAsk(text)){");
  const branch = SEND.slice(gate, SEND.indexOf("  // CLEARED AT THE START OF EVERY TURN", gate));
  assert.match(branch,
    /addMessage\("system", "There is no answer on screen yet, so there is nothing to mark\."\);\s*return;/,
    "the no-answer path does not say, in the page's system voice, that there is nothing to mark");
});

check("the branch names the owner's 2026-11-01 field test in plain words", () => {
  assert.match(SEND, /2026-11-01/, "the route does not name the field test it fixes");
  assert.match(SEND, /field test/i, "the route does not call it what it was");
  assert.match(HELPER_SOURCE, /2026-11-01/, "the recogniser does not say why it exists");
  assert.match(HELPER_SOURCE, /was this answer right\?/i, "the recogniser does not quote the owner's words");
});

check("the three vendored copies of the page are byte-identical", () => {
  const [first, ...rest] = COPIES;
  const original = readFileSync(first[1]);
  for (const [name, file] of rest) {
    const other = readFileSync(file);
    assert.ok(original.equals(other), `${name} copy differs from ${first[0]}`);
  }
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
