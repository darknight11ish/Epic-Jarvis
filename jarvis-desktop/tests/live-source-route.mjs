/**
 * Where the desktop's Jarvis Live sentence is posted - a source pin.
 *
 * THE DETERMINISM AUDIT'S F18 (2026-11-08) could not prove the desktop Live
 * client path from the queued tree: the HUD page only ever sets `provenance`
 * "typed"/"pasted", the Rust listener emits `voice-heard`, and main.js sends
 * `send(text,"voice")` - but which code posts a desktop Live sentence to
 * `/api/chat` with `provenance:"voice"` AND `live:true` was not pinned in one
 * place. This suite pins it, browser-free, by reading the two files.
 *
 * THE CHAIN IT PINS (each check names the file and prints the line):
 *   1. src/main.js: `liveSend()` sets `state.voiceTurn = true` and calls
 *      `send(text, "voice", { live: true })` - the desktop Live sentence.
 *   2. src/main.js: `send(promptText, provenance = "typed", { live: ... })`
 *      accepts the Live mark and calls `liveBeforeSend(isLive, provenance)`.
 *   3. src/main.js: `liveBeforeSend()` sets `state.liveTurn` only for
 *      `live && provenance === "voice" && liveOnHere()` - so a typed mark can
 *      never become a Live turn.
 *   4. src/main.js: the newest user message is wrapped in `liveTag(...)`,
 *      which adds `live: true` to the message when `state.liveTurn`; its
 *      `provenance` was set just above by `sentProvenance(provenance, ...)`,
 *      which passes "voice" through.
 *   5. src/main.js: `streamViaBackend()` invokes `"stream_chat"` with the
 *      payload - the Tauri command (not a page fetch).
 *   6. src-tauri/src/commands.rs: `pub async fn stream_chat` forwards
 *      `"messages": messages` unchanged, so each message's own `provenance`
 *      and `live` marker reach the backend, then `pump_chat` posts it to
 *      `/api/chat`.
 *
 * The backend half (its `_live_body` requires `provenance:"voice"` +
 * `live:true` on the newest user message) is proved by
 * backend/test_live_parity.py and backend/test_factual_determinism.py; this
 * file only pins the desktop end.
 *
 * If the desktop Live path is ever removed or renamed this test fails loudly
 * rather than letting the audit's one unproven client path go quiet.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const main = read("src/main.js");
const rust = read("src-tauri/src/commands.rs");

let failed = 0;
let passed = 0;
const check = (name, fn) => {
  try {
    fn();
    passed += 1;
    console.log(`ok    ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

const lineOf = (text, needle) => {
  const i = text.indexOf(needle);
  return i < 0 ? null : text.slice(0, i).split("\n").length;
};
const requireLine = (text, needle, file) => {
  const line = lineOf(text, needle);
  assert.ok(line !== null, `${file} does not contain: ${needle}`);
  return line;
};
const count = (text, needle) => text.split(needle).length - 1;

/* ── 1. the sender: liveSend() posts the Live sentence ─────────────────── */

check("src/main.js: liveSend() calls send(text, \"voice\", { live: true })", () => {
  const line = requireLine(main, "send(text, \"voice\", { live: true });", "src/main.js");
  const start = main.lastIndexOf("function liveSend(", main.indexOf(
    "send(text, \"voice\", { live: true });"));
  assert.ok(start >= 0, "liveSend() is not the function that sends the Live sentence");
  const body = main.slice(start, main.indexOf("\n}", start));
  assert.ok(body.includes("state.voiceTurn = true;"),
    "liveSend() must mark the turn as a voice turn");
  console.log(`      main.js:${line}  liveSend() -> send(..., "voice", { live: true })`);
});

check("src/main.js: there is exactly ONE desktop Live send call", () => {
  assert.equal(count(main, "{ live: true }"), 1,
    "a second send with live:true would be a second desktop Live path");
});

/* ── 2. send() accepts the Live mark and marks the turn ────────────────── */

check("src/main.js: send() takes the live option and calls liveBeforeSend", () => {
  const sig = requireLine(main,
    "async function send(promptText, provenance = \"typed\", { live: isLive = false, cloudYes = false } = {})",
    "src/main.js");
  const call = requireLine(main, "liveBeforeSend(isLive, provenance);", "src/main.js");
  console.log(`      main.js:${sig}  send() signature; main.js:${call}  liveBeforeSend(isLive, provenance)`);
});

check("src/main.js: liveBeforeSend() needs BOTH live and provenance voice", () => {
  const line = requireLine(main,
    "state.liveTurn = Boolean(isLive) && provenance === \"voice\" && liveOnHere();",
    "src/main.js");
  const fn = main.slice(main.lastIndexOf("function liveBeforeSend(", main.indexOf(
    "state.liveTurn = Boolean(isLive) && provenance === \"voice\" && liveOnHere();")));
  assert.ok(fn.includes("function liveBeforeSend(isLive, provenance)"),
    "the assignment is not inside liveBeforeSend(isLive, provenance)");
  console.log(`      main.js:${line}  a typed mark can never become a Live turn`);
});

/* ── 3. the marker rides on the newest user message ────────────────────── */

check("src/main.js: liveTag() adds live:true to the newest user message", () => {
  const tag = requireLine(main, "return state.liveTurn ? { ...message, live: true } : message;",
    "src/main.js");
  const fnLine = requireLine(main, "function liveTag(message) {", "src/main.js");
  assert.ok(fnLine < tag, "the live:true line is not inside liveTag()");
  console.log(`      main.js:${fnLine}  liveTag(); main.js:${tag}  live: true`);
});

check("src/main.js: the payload wraps the user message in liveTag()", () => {
  const line = requireLine(main,
    "liveTag(withCutOff(screenTag(userMessage(content, state.turnProvenance))))",
    "src/main.js");
  console.log(`      main.js:${line}  liveTag(...) on the newest user message`);
});

check("src/main.js: the provenance is \"voice\" for a spoken turn", () => {
  const line = requireLine(main,
    "state.turnProvenance = sentProvenance(provenance, Boolean(state.capture));",
    "src/main.js");
  // sentProvenance() lives in chat-history.js and is imported here; it keeps
  // the known tag unchanged, so a spoken turn's tag stays "voice".
  const at = main.indexOf("sentProvenance,");
  assert.ok(at >= 0, "main.js does not import sentProvenance");
  const importSrc = main.slice(at, main.indexOf('from "./chat-history.js"', at));
  assert.ok(importSrc.length > 0, "sentProvenance is not imported from chat-history.js");
  const ch = read("src/chat-history.js");
  const fn = requireLine(ch, "export function sentProvenance(tag, hasPicture) {",
    "src/chat-history.js");
  const bodyStart = ch.indexOf("export function sentProvenance(");
  const body = ch.slice(bodyStart, ch.indexOf("\n}", bodyStart));
  assert.ok(body.includes("return known;"),
    "sentProvenance no longer returns the known tag unchanged");
  const knownLine = requireLine(ch, "export function knownProvenance(tag) {",
    "src/chat-history.js");
  const knownBody = ch.slice(ch.indexOf("export function knownProvenance("),
                             ch.indexOf("\n}", ch.indexOf("export function knownProvenance(")));
  assert.ok(knownBody.includes("includes(tag)"),
    "knownProvenance must accept a known tag such as voice");
  console.log(`      main.js:${line}  turnProvenance; chat-history.js:${fn}  sentProvenance() keeps "voice"; :${knownLine}  knownProvenance()`);
});

/* ── 4. the transport: the Tauri command, not a page fetch ─────────────── */

check("src/main.js: streamViaBackend() invokes the stream_chat command", () => {
  const line = requireLine(main, "await invokeStrict(\"stream_chat\", { ...payload, onEvent: channel });",
    "src/main.js");
  const fn = main.lastIndexOf("async function streamViaBackend(", main.indexOf(
    "await invokeStrict(\"stream_chat\", { ...payload, onEvent: channel });"));
  assert.ok(fn >= 0, "the invoke is not inside streamViaBackend()");
  console.log(`      main.js:${line}  invokeStrict("stream_chat", {...payload})`);
});

/* ── 5. Rust: stream_chat forwards messages untouched, then posts ──────── */

check("src-tauri/src/commands.rs: stream_chat forwards `messages` unchanged", () => {
  const sig = requireLine(rust, "pub async fn stream_chat(", "src-tauri/src/commands.rs");
  const passthrough = requireLine(rust, "\"messages\": messages,", "src-tauri/src/commands.rs");
  const post = requireLine(rust, "pump_chat(&app, base, headers, payload, &on_event)",
    "src-tauri/src/commands.rs");
  assert.ok(sig < passthrough && passthrough < post,
    "stream_chat must put the messages on the payload before pump_chat posts it");
  console.log(`      commands.rs:${sig}  stream_chat(); :${passthrough}  messages ride unchanged; :${post}  pump_chat -> /api/chat`);
});

check("src-tauri/src/commands.rs: a Live marker is NOT stripped or rebuilt", () => {
  // `live` is per message, inside the array Rust passes through; if Rust ever
  // rebuilt the messages, the per-message mark would need an explicit copy.
  assert.ok(!/messages\s*[:=][^;]*map\(|messages[\s\S]{0,80}filter\(/.test(
    rust.slice(rust.indexOf("pub async fn stream_chat("),
               rust.indexOf("pub async fn stream_chat(") + 8000)),
    "stream_chat appears to rewrite the messages; per-message live/provenance would be lost");
  console.log("      commands.rs: the message array is passed through, not rebuilt");
});

/* ── summary ──────────────────────────────────────────────────────────── */

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
