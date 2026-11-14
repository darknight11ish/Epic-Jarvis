/**
 * Read-aloud flow: one piece ahead, and a Pause that works everywhere.
 *
 *   node tests/hud-read-aloud-flow.mjs
 *
 * THREE BUGS THIS SUITE EXISTS FOR (2026-11-13, found by an independent review
 * of the desktop speech code):
 *
 *   1. STUTTER. The HUD cuts an answer into pieces of at most 500 characters
 *      and asked for each piece's sound only after the previous clip had
 *      FINISHED (`await speechPlay`, then the next `await speechRequest`), so
 *      every sentence boundary was a silence as long as the PC takes to make
 *      the next clip. The bar already asks for one clip ahead while the
 *      current one plays (src/main.js `prefetchNextClip`, "One ahead ...
 *      instead of after a silence"); the HUD now does the same.
 *   2. A DEAD PAUSE. The per-answer menu hid Pause while the first clip was
 *      still being made, and between two pieces there is no clip to pause, so
 *      the item was drawn and did nothing (`pauseSpeechPlayback` required an
 *      audio element). Pause and Resume must act at every moment, and a press
 *      that genuinely cannot act must say so in one short line.
 *   3. A DORMANT MALE VOICE. `hud_bootstrap.js`'s speech-synthesis wrapper
 *      still carried `english[0] || mine[0]`, the rule that once read replies
 *      in Microsoft David. Nothing calls the browser voice today, so it is
 *      deleted rather than left armed and trusted to a test.
 *
 * The page's whole player block is lifted out of the real HTML and run here
 * with a fake transport and a fake `Audio` - the real player code, no browser,
 * so CI needs no Playwright for this half. The Playwright page tests live in
 * tests/hud-live-read-aloud.mjs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const PAGE = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
const BOOT = readFileSync(join(TAURI, "src", "hud_bootstrap.js"), "utf8");
const VOICE_TEST = readFileSync(join(HERE, "hud-read-aloud-voice.mjs"), "utf8");

let passed = 0;
const failed = [];
async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`ok   ${name}`);
  } catch (error) {
    // Every check runs even after one fails, so a red run lists every broken
    // pin at once - the same shape tests/hud-live-read-aloud.mjs uses.
    failed.push(name);
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}

/** Comments out, so a regex sees CODE only: the comments in these files quote
 *  the old bugs on purpose and must not be read as the code still doing them. */
function codeOnly(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

const BOOT_CODE = codeOnly(BOOT);
const QUIET = { info() {}, warn() {}, log() {} };

/**
 * The page's read-aloud player, lifted out and run against fakes.
 *
 * `plan` says how each `speak_reply` call answers, by the call's index in the
 * answer's pieces: "now" (a resolved clip) or "defer" (a promise this test
 * releases with `release(i)`). Call order and clip starts are recorded in
 * `seq` as `ask:0`, `play:0`, `end:0` ..., which is what proves the NEXT piece
 * was asked for before the current clip ended.
 */
function loadPlayer(plan = {}) {
  const from = PAGE.indexOf("const READ_PIECE_MAX");
  const to = PAGE.indexOf("/* Stop everything: Rust emits `stop-everything`");
  assert.ok(from >= 0 && to > from, "the page's read-aloud block was not found");

  const seq = [];
  const clips = [];
  const asked = [];
  const pending = [];
  let calls = 0;

  class FakeAudio {
    constructor(uri) {
      this.uri = uri;
      // The clip's index, so `seq` reads `play:0`, `end:0` - not the whole URI.
      this.id = String(uri).split(",").pop();
      this.onended = null;
      this.onerror = null;
      this.paused = true;
      this.plays = 0;
      this.ended = false;
      clips.push(this);
    }
    play() {
      this.paused = false;
      this.plays += 1;
      seq.push("play:" + this.id);
      return Promise.resolve();
    }
    pause() {
      this.paused = true;
      seq.push("pause:" + this.id);
    }
    removeAttribute() {}
    load() {}
    end() {
      if (this.ended) return;
      this.ended = true;
      seq.push("end:" + this.id);
      if (this.onended) this.onended();
    }
  }

  function invoke(cmd, args) {
    assert.equal(cmd, "speak_reply", "the page asked for something other than a clip");
    const i = calls;
    calls += 1;
    asked.push(args && args.text);
    seq.push("ask:" + i);
    if (plan[i] === "defer") {
      return new Promise((resolve) => pending.push({ i, resolve }));
    }
    return Promise.resolve("data:audio/wav;base64," + i);
  }

  const win = {
    __TAURI__: { core: { invoke }, event: { listen: async () => () => {} } },
    addEventListener() {},
    dispatchEvent() {},
  };
  const doc = {
    querySelectorAll: () => [],
    createElement: () => ({ className: "", setAttribute() {}, textContent: "", appendChild() {} }),
  };
  const bubble = { querySelector: () => null, appendChild() {} };
  const reactor = { set() {} };
  const dollar = () => null;
  const jfetch = () => { throw new Error("the shell must use speak_reply, not jfetch"); };

  // The real block, from the piece cap to the door the answer menu uses.
  const factory = new Function(
    "window", "document", "Audio", "reactor", "$", "jfetch", "console",
    `${PAGE.slice(from, to)}
     return { readAnswerAloud, pauseSpeechPlayback, resumeSpeechPlayback,
              stopSpeechPlayback, speechPieces, readAloudState };`
  );
  const api = factory(win, doc, FakeAudio, reactor, dollar, jfetch, QUIET);

  const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
  async function until(what, predicate) {
    for (let i = 0; i < 300; i += 1) {
      if (predicate()) return;
      await tick();
    }
    throw new Error(`timed out waiting for ${what}; sequence: ${seq.join(", ")}`);
  }
  function release(i) {
    const at = pending.findIndex((entry) => entry.i === i);
    assert.ok(at >= 0, `no deferred request for piece ${i} was made`);
    const [entry] = pending.splice(at, 1);
    entry.resolve("data:audio/wav;base64," + i);
  }

  return { api, bubble, clips, asked, seq, tick, until, release };
}

/** End clips as they arrive, from `first` to the last piece, then the read
 *  must be idle - the same loop every flow test finishes with. */
async function playToEnd(play, pieces, first) {
  for (let i = first; i < pieces.length; i += 1) {
    await play.until(`clip ${i}`, () => play.clips.length > i);
    assert.equal(play.api.readAloudState.audio, play.clips[i],
      `clip ${i} was made but is not the one playing`);
    play.clips[i].end();
  }
  await play.until("the read to end", () => play.api.readAloudState.state === "idle");
}

const LONG = "This is one sentence. ".repeat(80).trim();

/* ── 1. One ahead: the next piece is made while this one plays ───────────── */

await check("the next piece is asked for while this clip plays, not after it ends", async () => {
  const play = loadPlayer();
  const pieces = play.api.speechPieces(LONG);
  assert.ok(pieces.length >= 3, `the fixture made ${pieces.length} piece(s), needs at least 3`);

  assert.deepEqual(await play.api.readAnswerAloud(LONG, play.bubble), { ok: true, why: "Reading." });
  await play.until("the first clip", () => play.api.readAloudState.state === "playing");

  // The first clip has not ended, and the SECOND piece's sound is already on
  // its way. Before 2026-11-13 the sequence was ask:0, play:0, end:0, ask:1.
  assert.deepEqual(play.seq.slice(0, 3), ["ask:0", "ask:1", "play:0"],
    "the next piece was not asked for before this one started playing");
  assert.equal(play.asked[1], pieces[1], "the prefetched piece is not the next one in order");

  play.clips[0].end();
  await play.until("the second clip", () => play.seq.includes("play:1"));
  const atAsk = play.seq.indexOf("ask:1");
  const atEnd = play.seq.indexOf("end:0");
  assert.ok(atAsk >= 0 && atEnd > atAsk,
    `piece 2 was asked for after clip 1 ended: ${play.seq.join(", ")}`);

  // Nothing had to be requested in the gap: clip 2's sound was ready.
  const gap = play.seq.slice(atEnd, play.seq.indexOf("play:1"));
  assert.equal(gap.filter((entry) => entry === "ask:1").length, 0,
    "the second piece was requested again after the first clip ended");

  for (let i = 1; i < pieces.length; i += 1) {
    await play.until(`clip ${i}`, () => play.clips.length > i);
    // One ahead at most: at most the piece being played plus the next.
    assert.ok(play.asked.length <= i + 2,
      `${play.asked.length} pieces were requested while only ${i + 1} had played`);
    play.clips[i].end();
  }
  await play.until("the read to end", () => play.api.readAloudState.state === "idle");
  assert.deepEqual(play.asked, pieces, "the pieces were not asked for once each, in order");
});

/* ── 2. Pause and Resume work between pieces, and while the first is made ── */

await check("Pause between pieces pauses, Resume carries on from that piece", async () => {
  const play = loadPlayer({ 1: "defer" });
  const pieces = play.api.speechPieces(LONG);
  assert.ok(pieces.length >= 2, "the fixture needs at least two pieces");

  await play.api.readAnswerAloud(LONG, play.bubble);
  await play.until("the first clip", () => play.api.readAloudState.state === "playing");
  assert.equal(play.asked.length, 2, "the next piece was not being made during the first");

  // The first clip ends and the read is in the GAP: the next sound is still
  // being made, so there is no audio element to pause. This is the moment the
  // menu used to offer a button that did nothing.
  play.clips[0].end();
  await play.tick();
  assert.equal(play.api.readAloudState.audio, null, "the gap still holds a clip");
  assert.equal(play.api.readAloudState.state, "playing", "the gap is not a live read");

  assert.equal(play.api.pauseSpeechPlayback(), true,
    "Pause in the gap of two pieces did nothing (the dead-button bug)");
  assert.equal(play.api.readAloudState.state, "paused");

  // A paused read must not start the clip whose sound arrives while it waits.
  play.release(1);
  await play.tick();
  assert.equal(play.clips.length, 1, "a clip started while the read was paused");

  assert.equal(play.api.resumeSpeechPlayback(), true,
    "Resume in the gap of two pieces did nothing");
  await play.until("the second clip", () => play.clips.length === 2);
  assert.equal(play.api.readAloudState.state, "playing");
  assert.deepEqual(play.asked.slice(0, 2), [pieces[0], pieces[1]],
    "the resumed read did not carry on from the next piece in order");

  assert.equal(play.clips[1].uri, "data:audio/wav;base64,1",
    "the resumed clip is not the piece that was being made");
  play.clips[1].end();
  await playToEnd(play, pieces, 2);
});

await check("Pause while the first clip is being made holds it, Resume plays it", async () => {
  const play = loadPlayer({ 0: "defer" });
  const pieces = play.api.speechPieces(LONG);
  assert.ok(pieces.length >= 2, "the fixture needs at least two pieces");

  await play.api.readAnswerAloud(LONG, play.bubble);
  assert.equal(play.api.readAloudState.state, "loading", "the first clip is not being made");

  assert.equal(play.api.pauseSpeechPlayback(), true,
    "Pause while the first clip was being made did nothing");
  assert.equal(play.api.readAloudState.state, "paused");

  // The sound arrives while paused: it must wait for Resume, not start.
  play.release(0);
  await play.tick();
  assert.equal(play.clips.length, 0, "the first clip started while the read was paused");

  assert.equal(play.api.resumeSpeechPlayback(), true,
    "Resume after a pause taken while the first clip was made did nothing");
  await play.until("the first clip", () => play.clips.length === 1);
  assert.equal(play.api.readAloudState.state, "playing");
  play.clips[0].end();
  await playToEnd(play, pieces, 1);
});

await check("a Stop while paused between pieces ends the read, and a new read still works", async () => {
  const play = loadPlayer({ 1: "defer" });
  const pieces = play.api.speechPieces(LONG);
  await play.api.readAnswerAloud(LONG, play.bubble);
  await play.until("the first clip", () => play.clips.length === 1);
  play.clips[0].end();
  await play.tick();
  assert.equal(play.api.pauseSpeechPlayback(), true);
  // Stop while the loop is waiting on the pause: it must be released, not
  // left hanging, and the read must be idle at once.
  play.api.stopSpeechPlayback();
  assert.equal(play.api.readAloudState.state, "idle");
  play.release(1);
  await play.tick();
  assert.equal(play.clips.length, 1, "a stopped read played the clip it was waiting for");

  // ...and the one player can start again afterwards.
  await play.api.readAnswerAloud("A fresh answer.", play.bubble);
  await play.until("the fresh clip", () => play.clips.length === 2);
  assert.equal(play.api.readAloudState.state, "playing");
  play.clips[1].end();
  await play.until("the fresh read to end", () => play.api.readAloudState.state === "idle");
});

/* ── 3. The menu: Pause shown while making, and a press that says so ─────── */

await check("the answer menu offers Pause while the first clip is made, and never a silent press", () => {
  // "loading" is a live read: the first clip is still being made. The page
  // honours a pause taken there, so the item must be offered.
  assert.match(BOOT, /var reading = now === "playing" \|\| now === "paused" \|\| now === "loading";/,
    "the menu hides Pause while the first clip is being made");
  assert.match(BOOT, /pauseItem\.hidden = !reading;/);
  assert.match(BOOT, /pauseItem\.textContent = now === "paused" \? "Resume" : "Pause";/,
    "the item does not say what the next tap will do");
  // A tap goes to the page's own functions, and a result of false is said in
  // words on the item instead of being dropped (the dead-button report).
  assert.match(BOOT, /var resuming = speechStateHere\(\) === "paused";/,
    "the menu does not read the page's state to decide Pause or Resume");
  assert.match(BOOT, /acted = resuming \? speech\.resume\(\) : speech\.pause\(\);/,
    "the menu does not call the page's own pause/resume");
  assert.match(BOOT, /if \(!acted\) \{[\s\S]{0,400}receipt\(button, "Nothing is being read\."\);/,
    "a press that cannot act does not say so in one short line");
  // The page's own functions agree: false means "nothing is being read".
  assert.match(PAGE, /function pauseSpeechPlayback\(\)\{[\s\S]{0,300}return false;/);
  assert.match(PAGE, /function resumeSpeechPlayback\(\)\{[\s\S]{0,300}return false;/);
});

/* ── 4. No browser voice is picked, and the male voices stay forbidden ───── */

await check("no dormant browser-voice pick is left armed in the shell", () => {
  // The exact rule that once read replies in Microsoft David, and the list it
  // chose from. Deleted 2026-11-13, not merely left untested.
  assert.doesNotMatch(BOOT_CODE, /english\s*\[0\]\s*\|\|\s*mine\s*\[0\]/,
    "the index-0 voice pick is back in hud_bootstrap.js");
  assert.doesNotMatch(BOOT_CODE, /var\s+pick\b|utterance\.voice\s*=\s*pick/,
    "a voice is picked for the caller again");
  assert.doesNotMatch(BOOT_CODE, /\bmine\b|\benglish\b/,
    "the English-filtered local voice list is back");
  // The wrapper that stays is still a GUARD, not a chooser: it lists only this
  // computer's voices and drops a voice that is not local.
  assert.match(BOOT_CODE, /synth\.getVoices = localVoices;/,
    "the speech wrapper no longer limits the voice list to this computer's");
  assert.match(BOOT_CODE, /window\.speechSynthesis/,
    "the kept-on-screen speech guard was removed with the pick");
  assert.match(BOOT_CODE, /if \(!utterance\.voice\) \{/,
    "an unset voice is handed to the browser again instead of being refused");
});

await check("the page and the shell still forbid the male Windows voices", () => {
  // tests/hud-read-aloud-voice.mjs's own assertion must still name them: the
  // pin that keeps a hand-picked Windows voice out of the page survives.
  const line = VOICE_TEST.split("\n").find((l) => /doesNotMatch/.test(l) && /David/.test(l));
  assert.ok(line, "the test forbidding David|George|Zira was removed");
  for (const voice of ["David", "George", "Zira"]) {
    assert.ok(line.includes(voice), `the forbidden-voice test no longer names ${voice}`);
  }
  assert.doesNotMatch(codeOnly(PAGE), /David|George|Zira/i,
    "a hand-picked Windows voice is selected in the page's code");
});

if (failed.length) {
  console.log(`\n${failed.length} check(s) failed, ${passed} passed.`);
  process.exitCode = 1;
} else {
  console.log(`\n${passed} checks passed.`);
}
