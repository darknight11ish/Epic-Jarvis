/**
 * Read out loud, in Jarvis's OWN voice, with Pause / Resume / Stop (TASK-51).
 *
 *   node tests/hud-read-aloud-voice.mjs
 *
 * THE BUG THIS SUITE EXISTS FOR (the owner's decision of 2026-11-08, Gemini's
 * Q7). The HUD is the one desktop window that reads a TYPED answer aloud. It
 * did that with the webview's own speech engine, picking a voice by hand -
 * British first, then any English one, then whatever came first - under a
 * comment that said "match the Kokoro bm_george choice: British, male". The
 * owner's configured voice is Kokoro's (default `af_heart`, a woman), the same
 * voice a spoken answer and Jarvis Live use, and WebView2 cannot produce it.
 * The owner's report of 2026-11-08 names the fallback he heard: Windows'
 * index-0 `Microsoft David`, a man.
 *
 * So the page must:
 *   1. ask THIS PC for the sound, through the bar's own `speak_reply` command
 *      (`/api/voice/say` -> the configured voice), and never touch a browser
 *      speech engine - no second voice, no index-0, no male substitute;
 *   2. say so in one plain line when the PC cannot make the sound, and speak
 *      nothing else instead;
 *   3. offer Pause / Resume beside Read out loud, and a Stop that is a FULL
 *      reset (token, queue, clip, URL, line and meter);
 *   4. stop on Stop everything and on the PC's `read_aloud {enabled: false}`;
 *   5. keep the privacy rule in front of every tap (answerMayBeSpoken, failing
 *      closed), and the microphone/voiceprint path untouched.
 *
 * Pure node, no browser: the page is read, the pure splitter is lifted out and
 * run, and the wiring is pinned as source. The Playwright half that taps the
 * real page is `tests/hud-live-read-aloud.mjs`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const TAURI = join(HERE, "..", "src-tauri");
const ROOT = join(HERE, "..", "..");

const page = readFileSync(join(SRC, "jarvis_hud.html"), "utf8");
const bootstrap = readFileSync(join(TAURI, "src", "hud_bootstrap.js"), "utf8");
const voiceRs = readFileSync(join(TAURI, "src", "voice.rs"), "utf8");
const commandsRs = readFileSync(join(TAURI, "src", "commands.rs"), "utf8");
const hudCap = JSON.parse(readFileSync(join(TAURI, "capabilities", "hud.json"), "utf8"));
const surfaces = readFileSync(join(TAURI, "permissions", "surfaces.toml"), "utf8");

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

/** The page with its comments taken out, so a regex sees CODE only: the
 *  comments in this file quote the old bug on purpose and must not be read as
 *  the code still doing it. */
function codeOnly(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

/** One `function name(...) { ... }` block, by brace matching, so its real
 *  body can be checked (and, for the pure splitter, run) here. */
function sliceFunction(src, name) {
  const start = src.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `no function ${name}() in the page`);
  const open = src.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error(`function ${name}() is never closed`);
}

const pageCode = codeOnly(page);

check("the page asks no browser speech engine at all - so no index-0, no British-male pick", () => {
  // Code only: the comments above the player quote the old bug on purpose.
  assert.doesNotMatch(pageCode, /speechSynthesis/i,
    "the page still reaches the webview's own voice list");
  assert.doesNotMatch(pageCode, /SpeechSynthesisUtterance/,
    "the page still builds a browser utterance");
  assert.doesNotMatch(pageCode, /\bgetVoices\s*\(/,
    "the page still lists the browser's voices");
  assert.doesNotMatch(pageCode, /\bvoice\.speak\s*\(/,
    "the old voice.speak path is still called");
  // The hand-picked voice from the bug: no accent/name matching survives in
  // code (comments may name it; only the executable half matters).
  assert.doesNotMatch(pageCode, /en-GB|en_US|Microsoft|Daniel|George|Arthur|Zira|David/i,
    "a hand-picked Windows voice is still selected somewhere in the page");
});

check("the one voice is the PC's own, through the bar's speak_reply command", () => {
  // Inside the shell: the SAME Rust command a spoken answer calls.
  assert.match(page,
    /window\.__TAURI__\.core\.invoke\("speak_reply", \{ text: piece \}\)/,
    "read-aloud does not ask the PC for the answer's sound");
  // In a plain browser (the backend serves this page at "/"): the same route,
  // directly - still the configured voice, never the browser's.
  assert.match(page, /jfetch\("\/api\/voice\/say"/,
    "the browser half does not ask the PC's own voice route");
  // The command still is that route: `speak_reply` -> POST /api/voice/say.
  assert.match(voiceRs, /pub async fn speak_reply/);
  assert.match(voiceRs, /\.post\(format!\("\{\}\/api\/voice\/say", jarvis_base\(&app\)\)\)/,
    "speak_reply no longer asks the PC's voice route");
});

check("Pause, Resume and Stop are the page's own functions, with one door to them", () => {
  assert.match(page, /function pauseSpeechPlayback\(\)/);
  assert.match(page, /function resumeSpeechPlayback\(\)/);
  assert.match(page, /function stopSpeechPlayback\(\)/);
  assert.match(page, /window\.__jarvisSpeech = \{/,
    "the answer menu has no state to read the player from");
  assert.match(page, /pause: pauseSpeechPlayback,/);
  assert.match(page, /resume: resumeSpeechPlayback,/);
  assert.match(page, /stop: stopSpeechPlayback,/);
  assert.match(page, /function readAnswerAloud\(text, bubble\)/);
});

check("the answer menu draws Pause / Resume and Stop reading beside Read out loud", () => {
  assert.match(bootstrap, /item\("Read out loud"/);
  assert.match(bootstrap, /pauseItem = item\("Pause"/,
    "there is no Pause item beside Read out loud");
  assert.match(bootstrap, /stopItem = item\("Stop reading"/,
    "there is no Stop reading item");
  assert.match(bootstrap, /pauseItem\.textContent = now === "paused" \? "Resume" : "Pause";/,
    "Pause does not become Resume while it is paused");
  assert.match(bootstrap, /pauseItem\.hidden = !reading;/,
    "Pause is shown when nothing is being read");
  assert.match(bootstrap, /stopItem\.hidden = !reading;/);
  assert.match(bootstrap, /speech\.stateFor\(msg\)/,
    "the menu does not ask the page which answer is being read");
  // TASK-51b (2026-11-13): the item's next tap is decided by the page's state,
  // and both calls still go to the page's one player.
  assert.match(bootstrap, /var resuming = speechStateHere\(\) === "paused";/,
    "the menu no longer reads the player state to decide Pause or Resume");
  assert.match(bootstrap, /acted = resuming \? speech\.resume\(\) : speech\.pause\(\);/,
    "the menu does not call the page's own pause and resume");
  assert.match(bootstrap, /speech\.pause\(\)/);
  assert.match(bootstrap, /speech\.stop\(\)/);
});

check("Stop is a full reset - token, queue, clip, release, line and meter", () => {
  const stop = sliceFunction(page, "stopSpeechPlayback");
  for (const part of [
    "readAloudState.token += 1;",
    "readAloudState.pieces = [];",
    "readAloudState.at = 0;",
    "readAloudState.audio = null;",
    "const settle = readAloudState.settle;",
    "readAloudState.settle = null;",
    "if(settle){",
    "audio.pause()",
    'audio.removeAttribute("src")',
    "clearReadFailed(bubble);",
    'speechSetState("idle")',
  ]) {
    assert.ok(stop.includes(part), `stopSpeechPlayback does not: ${part}`);
  }
  // The page holds no file/blob road (tests/hud-shell.mjs pins that), so the
  // browser half must deliver the sound as a data URI too - never a blob URL.
  assert.doesNotMatch(pageCode, /createObjectURL|revokeObjectURL/,
    "the page grew an object URL road");
});

check("a voice that cannot be made is said in words - and never swapped for another", () => {
  assert.match(page,
    /const READ_FAILED_LINE =\s*\n\s*"Jarvis's voice could not read this aloud, so nothing was spoken\.";/,
    "there is no fixed, plain sentence for a voice that could not be made");
  const giveUp = sliceFunction(page, "speechGiveUp");
  assert.match(giveUp, /showReadFailed\(bubble\)/,
    "a failed read leaves the owner with silence and no explanation");
  // The only source of sound is the PC's voice route: no fallback branch.
  const request = sliceFunction(page, "speechRequest");
  assert.match(request, /invoke\("speak_reply"/);
  assert.match(request, /\/api\/voice\/say/);
  assert.doesNotMatch(request, /speechSynthesis|getVoices|SpeechSynthesisUtterance/);
});

check("Stop everything and the PC's read_aloud OFF both call the full reset", () => {
  assert.match(page, /events\.listen\("stop-everything", \(\) => stopSpeechPlayback\(\)\)/,
    "Stop everything does not stop this page's read-aloud");
  assert.match(page, /es\.addEventListener\("read_aloud", \(m\) => \{/,
    "the page does not listen for the PC's read-aloud switch");
  assert.match(page, /if \(d\.enabled === false\) stopSpeechPlayback\(\);/,
    "read_aloud OFF does not stop the answer being read");
  // Rust emits that event before it asks the PC to stop anything, which is
  // what makes the page's listener fire at once.
  assert.match(commandsRs, /crate::emit_all\(app, crate::events::STOP_EVERYTHING, \(\)\);/);
  // ...and the page's own stop-everything button goes through the same command.
  assert.match(page, /core\.invoke\("stop_everything"\)/);
});

check("the privacy rule still comes first, for THAT answer, and fails closed", () => {
  assert.match(page, /answerMayBeSpoken\(said\.route\)/,
    "the read hook no longer asks private-speech.js for this answer");
  assert.match(page, /return readAnswerAloud\(said\.text, bubble\);/,
    "an allowed answer is not handed to the player with its own bubble");
  assert.match(page,
    /readAnswerAloud\(ANSWER_SAID\.get\(bubble\) \? ANSWER_SAID\.get\(bubble\)\.text : "", bubble\)/,
    "the speaker icon does not use the one player");
  assert.match(page, /if\(!may \|\| !readAloudIconsOn\(\) \|\| !bubble\.isConnected\) return;/,
    "the speaker's own gate changed shape");
});

check("the page's one command is granted by its own narrow set, never the voice set", () => {
  assert.ok(hudCap.permissions.includes("hud-speech"),
    "capabilities/hud.json does not pull the read-aloud set in");
  assert.ok(!hudCap.permissions.includes("voice"),
    "the HUD was given the bar's recording/voice set");
  const from = surfaces.indexOf('identifier = "hud-speech"');
  assert.ok(from >= 0, "surfaces.toml has no hud-speech set");
  const set = surfaces.slice(from, surfaces.indexOf('identifier = "hud-link"'));
  assert.match(set, /permissions = \["allow-speak-reply"\]/,
    "hud-speech grants something other than speak_reply");
});

check("the new caller's text is bounded, in characters", () => {
  assert.match(voiceRs, /pub\(crate\) const SAY_MAX_CHARS: usize = 4000;/);
  assert.match(voiceRs, /fn say_length_problem\(text: &str\) -> Option<&'static str>/);
  assert.match(voiceRs, /if let Some\(problem\) = say_length_problem\(text\) \{/,
    "speak_reply does not enforce its own text bound");
  assert.match(voiceRs,
    /fn a_read_at_the_limit_is_allowed_and_one_character_over_is_refused/,
    "the bound has no test");
});

check("one answer is cut into pieces small enough for one request", () => {
  // The real splitter, with the page's own limits, lifted out and run here.
  const from = page.indexOf("const READ_PIECE_MAX");
  const to = page.indexOf("const readAloudState");
  assert.ok(from >= 0 && to > from, "the splitter's own block was not found in the page");
  const pieceCap = Number((/const READ_PIECE_MAX = (\d+);/.exec(page) || [])[1]);
  assert.ok(Number.isFinite(pieceCap) && pieceCap > 0, "the piece cap is not a number");
  const speechPieces = new Function(`${page.slice(from, to)}; return speechPieces;`)();
  assert.deepEqual(speechPieces(""), []);
  assert.deepEqual(speechPieces("   \n "), []);
  assert.deepEqual(speechPieces("Hello there."), ["Hello there."]);
  // Markdown is not read out as punctuation.
  assert.deepEqual(speechPieces("**bold** and `code`"), ["bold and code"]);
  // A long answer becomes several requests, none over the cap.
  const long = "This is one sentence. ".repeat(40).trim();
  const pieces = speechPieces(long);
  assert.ok(pieces.length > 1, `a long answer was sent as ${pieces.length} request(s)`);
  for (const piece of pieces) assert.ok(piece.length <= pieceCap, `piece too long: ${piece.length}`);
  assert.equal(pieces.join(" ").replace(/\s+/g, " "), long.replace(/\s+/g, " "),
    "the pieces do not add back up to the answer");
  // A wall of text with no spaces is still cut.
  const wall = "a".repeat(1200);
  const bits = speechPieces(wall);
  assert.ok(bits.length >= 3);
  assert.ok(bits.every((piece) => piece.length <= pieceCap));
  assert.equal(bits.join(""), wall);
});

check("the page's own CSP lets the PC's data: clip through (measured, not assumed)", () => {
  // The clip `speak_reply` answers with is a `data:audio/wav` URI, and this
  // page's own <meta> CSP is enforced in addition to the shell's header. With
  // `media-src 'self' blob:` alone Chromium refused every clip with
  // NotSupportedError and logged `media-src data` - measured on this PC while
  // building TASK-51. The header CSP already allowed `data:`; this page's
  // policy was the half that would have silenced the feature.
  assert.match(page, /<meta http-equiv="Content-Security-Policy" content="[^"]*media-src 'self' data: blob:;/,
    "the page's own CSP does not allow the data: clip the PC makes");
  assert.doesNotMatch(page, /media-src 'self' blob:;/,
    "the page's CSP still refuses data: media");
  // ...and that data URI shape is what the one voice command returns.
  assert.match(voiceRs, /data:audio\/wav;base64/);
});

check("the page is still ONE page, byte for byte, in all three places", () => {
  const own = readFileSync(join(SRC, "jarvis_hud.html"));
  for (const other of [join(ROOT, "backend", "jarvis_hud.html"),
                       join(ROOT, "jarvis-backend", "jarvis_hud.html")]) {
    assert.ok(own.equals(readFileSync(other)),
      `${other} has drifted from jarvis-desktop/src/jarvis_hud.html`);
  }
});

console.log(`\n${passed} checks passed.`);
