/**
 * Private answers asked by voice are not read aloud unless the owner chose
 * so (docs/JARVIS-API.md section 16, "What the apps must do about private
 * answers"; private-speech.js, main.js).
 *
 * For a question that came by VOICE whose utterance reply says
 * `private_aloud: false` - or says nothing, as an older PC does - the answer
 * is read aloud only when nothing says it is private: `question_private`
 * is not true, the route has no `gate: "private"` and no `injected_facts`
 * above 0, and no tool ran while it was written: no `step` event with
 * `tool_started` / `tool_finished` since the question was sent (and no
 * `: jarvis-status working` or `approval`), with the event stream live the
 * whole time - a stream that was stale or dropped counts as "a tool may
 * have run", the phone's rule. Otherwise Jarvis says "It's on your
 * screen." once.
 *
 * The route headers are REAL (tests/fixtures/chat-stream-cases.json, made
 * by running the backend's router); they reach the page as the route line
 * commands.rs route_line_from_header builds from them.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as K from "./uikit.mjs";
import {
  createToolWatch, isToolRun, mayReadAloud, privacyFromHeard, PRIVATE_LINE, toolRanBetween, toolsKnownBetween,
} from "../src/private-speech.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CHAT = JSON.parse(read("tests/fixtures/chat-stream-cases.json"));
const header = (name) => JSON.parse(CHAT.route_headers.find((r) => r.name === name).header);
/** The route line commands.rs sends: lane, where, gate, second_card as
 *  strings, and injected_facts as a whole number. */
const routeLine = (h) => {
  const out = {};
  for (const k of ["lane", "where", "gate", "second_card"]) if (typeof h[k] === "string") out[k] = h[k];
  if (Number.isInteger(h.injected_facts) && h.injected_facts >= 0) out.injected_facts = h.injected_facts;
  return "\u001fjarvis-route:" + JSON.stringify(out);
};
const PRIVATE_ROUTE = header("local answer");       // gate "private", 1 fact
const OFFER_ROUTE = header("local answer, cloud offered"); // gate "offer", 0 facts
const delta = (text) => JSON.stringify({ choices: [{ delta: { content: text } }] });

const { base, close } = await K.serve();
const browser = await K.launch();
const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The rule ───────────────────────────────────────────────────────── */

await check("the rule, from the real route headers", async () => {
  const quiet = { privateAloud: false, questionPrivate: false, toolsKnown: true };
  assert.equal(PRIVATE_ROUTE.gate, "private");
  assert.equal(PRIVATE_ROUTE.injected_facts, 1);
  assert.equal(mayReadAloud({ ...quiet, route: PRIVATE_ROUTE }), false, "gate private");
  assert.equal(mayReadAloud({ ...quiet, route: { ...OFFER_ROUTE, injected_facts: 2 } }), false, "facts went in");
  assert.equal(mayReadAloud({ ...quiet, route: OFFER_ROUTE }), true, "nothing says private");
  assert.equal(mayReadAloud({ ...quiet, route: header("cloud answer") }), true);
  assert.equal(mayReadAloud({ privateAloud: false, questionPrivate: true, route: OFFER_ROUTE }), false);
  assert.equal(mayReadAloud({ ...quiet, route: OFFER_ROUTE, toolRan: true }), false, "a tool ran");
  assert.equal(mayReadAloud({ privateAloud: true, questionPrivate: true, route: PRIVATE_ROUTE, toolRan: true }), true,
    "the owner chose \"voice check is enough\"");
  assert.equal(mayReadAloud({ route: null, toolsKnown: true }), true, "an older PC and an older route: nothing says private");
  // The phone's rule: whether a tool ran is only known while the event
  // stream is live, and an unknown counts as "a tool may have run".
  assert.equal(mayReadAloud({ ...quiet, route: OFFER_ROUTE, toolsKnown: false }), false, "stream not live");
  assert.equal(mayReadAloud({ privateAloud: false, questionPrivate: false, route: OFFER_ROUTE }), false, "not said: unknown");
  // The owner's choice (2026-09-24): remembered facts are read aloud while
  // memory_aloud is true - and nothing else private is let through by it.
  const mem = { ...quiet, memoryAloud: true };
  assert.equal(mayReadAloud({ ...mem, route: { ...OFFER_ROUTE, injected_facts: 2 } }), true, "memory aloud");
  assert.equal(mayReadAloud({ ...mem, route: PRIVATE_ROUTE }), false, "memory aloud, gate private");
  assert.equal(mayReadAloud({ ...mem, questionPrivate: true, route: OFFER_ROUTE }), false);
  assert.equal(mayReadAloud({ ...mem, route: { ...OFFER_ROUTE, injected_facts: 2 }, toolRan: true }), false);
  // An older PC sends no private_aloud or memory_aloud: read as false, not as true.
  assert.deepEqual(privacyFromHeard(K.HEARD_OWNER), { privateAloud: false, questionPrivate: false, memoryAloud: false });
  assert.deepEqual(privacyFromHeard({ privateAloud: "true", questionPrivate: 1, memoryAloud: "yes" }),
    { privateAloud: false, questionPrivate: false, memoryAloud: false });
  assert.deepEqual(privacyFromHeard({ memoryAloud: true }), { privateAloud: false, questionPrivate: false, memoryAloud: true });
  assert.equal(PRIVATE_LINE, "It's on your screen.");
});

await check("the tool watch: step events and stream drops, as the phone counts them", async () => {
  assert.equal(isToolRun({ phase: "tool_started", tool: "calendar_read" }), true);
  assert.equal(isToolRun({ phase: "tool_finished", tool: "calendar_read", ok: true }), true);
  for (const phase of ["tool_refused", "model", "answer", undefined]) assert.equal(isToolRun({ phase }), false, String(phase));
  assert.equal(isToolRun(null), false);
  const w = createToolWatch();
  assert.equal(toolsKnownBetween(w.snapshot(), w.snapshot()), false, "never live: not known");
  w.link({ connected: true, stale: false });
  const start = w.snapshot();
  w.event({ kind: "step", data: { phase: "model" } });
  w.event({ kind: "finding", data: { phase: "tool_started" } });
  assert.equal(toolRanBetween(start, w.snapshot()), false, "a model step, and another kind: no tool");
  assert.equal(toolsKnownBetween(start, w.snapshot()), true);
  w.event({ kind: "step", data: { phase: "tool_started", tool: "email_read" } });
  assert.equal(toolRanBetween(start, w.snapshot()), true);
  const later = w.snapshot();
  w.link({ connected: true, stale: true });
  w.link({ connected: true, stale: false });
  assert.equal(toolsKnownBetween(later, w.snapshot()), false, "a drop in between: not known, even if live again");
  const again = w.snapshot();
  w.resync();
  assert.equal(toolsKnownBetween(again, w.snapshot()), false, "fell off the ring: not known");
  assert.equal(toolsKnownBetween(null, w.snapshot()), false, "no start: not known");
});

/* ── The quickbar ───────────────────────────────────────────────────── */

const quickbar = (data) => K.open(browser, base, "index.html", data);
const speakCalls = (page) => page.evaluate(() =>
  (window.__voiceCalls || []).filter((c) => Array.isArray(c) && c[0] === "speak").map((c) => c[1]));
async function holdAndRelease(page) {
  await page.hover("#mic");
  await page.mouse.down();
  await page.waitForTimeout(80);
  await page.mouse.up();
}
const spoken = async (heard, reply, link) => {
  const page = await quickbar({ heard, chatReplies: [reply], link });
  await holdAndRelease(page);
  await page.waitForTimeout(500);
  const said = await speakCalls(page);
  const errors = page.__errors;
  await page.close();
  assert.deepEqual(errors, []);
  return said;
};
const QUIET = { ...K.HEARD_OWNER, privateAloud: false, questionPrivate: false };

await check("a private route: only \"It's on your screen.\", once", async () => {
  const said = await spoken(QUIET, [routeLine(PRIVATE_ROUTE), delta("Your dentist is on Tuesday. "), delta("At ten. ")]);
  assert.deepEqual(said, [PRIVATE_LINE]);
});

await check("a private question: the same, whatever the route", async () => {
  const said = await spoken({ ...QUIET, questionPrivate: true }, [routeLine(OFFER_ROUTE), delta("You have two meetings. "), delta("Both after lunch. ")]);
  assert.deepEqual(said, [PRIVATE_LINE]);
});

await check("a tool ran while the answer was written: the rest is not read aloud", async () => {
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE), ": jarvis-status working", delta("I checked your inbox. "), delta("Two new emails. ")]);
  assert.deepEqual(said, [PRIVATE_LINE]);
});

const step = (data) => ({ emit: "jarvis-event", payload: { kind: "step", id: 90, data } });
const LINK_LIVE = { connected: true, stale: false, base: "http://127.0.0.1:4719", last_id: 7, power: "active", activity: "idle" };

await check("a quick tool (no jarvis-status at all): the step event keeps it on screen", async () => {
  // calendar_read answers in 0.4 s: the PC's `: jarvis-status working`
  // comes only after 1.5 s, so this answer carries none - only the event.
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE),
    step({ phase: "model", round: 1 }),
    step({ phase: "tool_started", tool: "calendar_read" }),
    step({ phase: "tool_finished", tool: "calendar_read", ok: true }),
    delta("Your dentist is on Tuesday. "), delta("At ten. ")]);
  assert.deepEqual(said, [PRIVATE_LINE]);
});

await check("a tool that starts halfway: reading stops there", async () => {
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE), delta("Let me look. "),
    step({ phase: "tool_finished", tool: "email_read", ok: true }), delta("Two new emails. ")]);
  assert.ok(!said.includes("Two new emails."), JSON.stringify(said));
  assert.equal(said.at(-1), PRIVATE_LINE, JSON.stringify(said));
});

await check("a refused tool did not run: read aloud", async () => {
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE), step({ phase: "tool_refused", tool: "email_send" }),
    delta("It is sunny. ")]);
  assert.deepEqual(said, ["It is sunny."]);
});

await check("the event stream went stale during the answer: a tool may have run", async () => {
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE),
    { emit: "jarvis-link", payload: { ...LINK_LIVE, stale: true } },
    { emit: "jarvis-link", payload: LINK_LIVE },
    delta("You have two meetings. ")]);
  assert.deepEqual(said, [PRIVATE_LINE]);
});

await check("the event stream was stale when the question was asked: not read aloud", async () => {
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE), delta("It is sunny. ")], { stale: true });
  assert.deepEqual(said, [PRIVATE_LINE]);
});

await check("CONTROL: nothing says private - read aloud as before", async () => {
  const said = await spoken(QUIET, [routeLine(OFFER_ROUTE), delta("It is sunny. "), delta("Twenty degrees. ")]);
  assert.deepEqual(said, ["It is sunny.", "Twenty degrees."]);
});

await check("the owner chose \"voice check is enough\": a private answer is read aloud", async () => {
  const said = await spoken({ ...QUIET, privateAloud: true, questionPrivate: true },
    [routeLine(PRIVATE_ROUTE), delta("Your dentist is on Tuesday. ")]);
  assert.deepEqual(said, ["Your dentist is on Tuesday."]);
});

await check("an older PC (no private_aloud) with a private route: not read aloud", async () => {
  const said = await spoken(K.HEARD_OWNER, [routeLine(PRIVATE_ROUTE), delta("Your dentist is on Tuesday. ")]);
  assert.deepEqual(said, [PRIVATE_LINE]);
});

await check("too short to check: the PC's own sentence, not \"that did not sound like you\"", async () => {
  const reason = "that was too short to be sure it was you (1.2 seconds of speech; a command needs at least 2.0) - say a little more";
  const page = await quickbar({ heard: { ...K.HEARD_STRANGER, isOwner: false, tooShort: true, reason } });
  await holdAndRelease(page);
  await page.waitForTimeout(300);
  const live = await page.evaluate(() => [...document.querySelectorAll("[aria-live]")].map((n) => n.textContent).join(" | "));
  await page.close();
  assert.ok(live.includes(reason), live);
  assert.doesNotMatch(live, /did not sound like you/);
});

/* ── The Rust ───────────────────────────────────────────────────────── */

await check("CONTROL (Rust): the utterance reply carries the three fields, and the route line the count", async () => {
  const voice = read("src-tauri/src/voice.rs");
  for (const f of ["too_short", "private_aloud", "question_private"]) {
    assert.match(voice, new RegExp(`#\\[serde\\(default\\)\\]\\s+${f}: bool,`), `HeardRaw.${f}`);
    assert.match(voice, new RegExp(`pub ${f}: bool,`), `HeardReply.${f}`);
  }
  const commands = read("src-tauri/src/commands.rs");
  assert.match(commands, /route\.get\("injected_facts"\)\.and_then\(\|v\| v\.as_u64\(\)\)/);
});

await browser.close();
close();
console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nPrivate answers stay on screen");
process.exit(fails.length ? 1 : 0);
