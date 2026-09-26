/**
 * Where a spoken answer is cut into pieces (src/speech-pieces.js): the
 * first piece at its first comma once the phrase is long enough, the rest
 * by sentence. The cases are tests/fixtures/first-piece-cases.json, which
 * the phone's SpeechTextTest.kt reads too, so both apps are held to the
 * same list - and this checks the phone's numbers and word list against it
 * as well. Needs no browser.
 *
 *     node tests/speech-pieces.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as P from "../src/speech-pieces.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(read("tests/fixtures/first-piece-cases.json"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** What main.js does as an answer streams in (checkForSpeakableSentence),
 *  then at its end (finishStream): pieces, trimmed. */
function speak(text, step) {
  const out = [];
  let spokenUpTo = 0;
  for (let end = step; ; end = Math.min(text.length, end + step)) {
    const buffer = text.slice(0, end);
    for (;;) {
      const cut = P.nextSpeechPiece(buffer.slice(spokenUpTo), spokenUpTo === 0);
      if (!cut) break;
      spokenUpTo += cut.consumed;
      if (cut.piece.trim()) out.push(cut.piece.trim());
    }
    if (end >= text.length) break;
  }
  const rest = text.slice(spokenUpTo).trim();
  if (rest) out.push(rest);
  return out;
}

check("the numbers and the word list are the shared ones", () => {
  assert.equal(P.FIRST_PIECE_MIN_CHARS, FIX.min_chars);
  assert.equal(P.FIRST_PIECE_FORCE_WORDS, FIX.force_words);
  assert.equal(P.FIRST_PIECE_MARKS, FIX.marks);
  assert.deepEqual([...P.AVOID_PAUSE_WORDS], FIX.avoid_pause_words);
});

for (const c of FIX.cases) {
  check(`${c.name} (all at once)`, () => assert.deepEqual(speak(c.text, c.text.length || 1), c.pieces));
  check(`${c.name} (one character at a time)`, () => assert.deepEqual(speak(c.text, 1), c.pieces));
}

check("after the first piece, only sentences: a comma is not a cut", () => {
  assert.equal(P.nextSpeechPiece("with light rain, then sun, later on", false), null);
  assert.deepEqual(P.nextSpeechPiece("Tomorrow looks mild, with rain", true),
    { piece: "Tomorrow looks mild,", consumed: 21 });
});

check("the phone uses the same numbers and the same word list", () => {
  const kt = read("../jarvis-client/app/src/main/java/com/jarvis/client/voice/SpeechText.kt");
  const num = (name) => Number((kt.match(new RegExp(`const val ${name} = (\\d+)`)) || [])[1]);
  assert.equal(num("FIRST_PIECE_MIN_CHARS"), FIX.min_chars);
  assert.equal(num("FIRST_PIECE_FORCE_WORDS"), FIX.force_words);
  assert.equal((kt.match(/const val FIRST_PIECE_MARKS = "([^"]*)"/) || [])[1], FIX.marks);
  const block = (kt.match(/val AVOID_PAUSE_WORDS: List<String> = listOf\(([\s\S]*?)\n {4}\)/) || [])[1] || "";
  const words = [...block.replace(/\/\/[^\n]*/g, "").matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(words, FIX.avoid_pause_words);
});

check("main.js cuts with it, first piece while nothing is cut yet", () => {
  const js = read("src/main.js");
  assert.match(js, /import \{ nextSpeechPiece \} from "\.\/speech-pieces\.js";/);
  assert.match(js, /nextSpeechPiece\(state\.buffer\.slice\(spokenUpTo\), spokenUpTo === 0\)/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall passed");
