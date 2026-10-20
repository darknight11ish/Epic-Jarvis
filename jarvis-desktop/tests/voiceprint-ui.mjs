/**
 * tests/voiceprint-ui.mjs - the "Write like me" settings page's own contract.
 *
 * No DOM, no Tauri: parseStatus, forgetAsk and boundedInvoke are pure, and the
 * source is checked for the two sinks that would make PC text dangerous.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  BLOCKED,
  DETAIL,
  EMPTY,
  MAX_TEXT,
  TITLE,
  boundedInvoke,
  forgetAsk,
  parseStatus,
  problemWords,
  sampleProblem,
} from "../src/voiceprint-settings.js";

const HERE = dirname(fileURLToPath(import.meta.url));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const ok = (name, cond, detail = "") => assert.ok(cond, `${name}${detail ? `: ${detail}` : ""}`);

test("words are the feature's own", () => {
  ok("title", TITLE === "Write like me");
  ok("detail names the promise", DETAIL.includes("draft") && DETAIL.includes("chatbot"));
});

test("parseStatus keeps only what it can render", () => {
  const v = parseStatus({
    available: true, enabled: true, count: 2, scrubber: true,
    samples: [
      { id: "vp1", text: "Hello [name]", kind: "sample", prompt: "" },
      { id: "vp2", text: "Second", kind: "edit" },
      { nope: true },
    ],
  });
  ok("enabled", v.enabled === true);
  ok("two valid rows survive", v.samples.length === 2, String(v.samples.length));
  ok("id and text are kept", v.samples[0].id === "vp1" && v.samples[0].text === "Hello [name]");
  ok("a malformed row is dropped, not rendered", !JSON.stringify(v).includes("nope"));
  ok("empty list says so", parseStatus({ samples: [] }).message === EMPTY);
  ok("the switch defaults OFF", parseStatus({}).enabled === false);
});

test("forget always asks first, with the sample's own first words", () => {
  const ask = forgetAsk({ id: "vp1", text: "Please send the invoice to Priya at work" });
  ok("asks the question", ask.startsWith("Forget this sample?"));
  ok("quotes the sample", ask.includes("Please send the invoice"));
  ok("says it cannot be undone", ask.includes("cannot be undone"));
});

test("the sample guard refuses empty and over-long text", () => {
  ok("empty refused", sampleProblem("   ") !== "");
  ok("over-long refused", sampleProblem("x".repeat(MAX_TEXT + 1)) !== "");
  ok("ordinary text allowed", sampleProblem("A normal message.") === "");
});

test("problemWords never leaks a bridge error", () => {
  ok("json refused", problemWords('{"error":"x"}') === BLOCKED);
  ok("plain words kept", problemWords("The PC is busy.") === "The PC is busy.");
});

test("boundedInvoke resolves a fast answer and rejects a stalled one in plain words", async () => {
  const fast = await boundedInvoke((cmd, args) => Promise.resolve({ cmd, args }), "voiceprint_status", null);
  ok("fast answer arrives", fast.cmd === "voiceprint_status");
  let rejected = "";
  try {
    await boundedInvoke(() => new Promise(() => {}), "voiceprint_status", null, 20);
  } catch (e) { rejected = String(e.message || e); }
  ok("a stalled invoke is cut off", rejected.includes("30 seconds") || rejected.includes("did not answer"));
  ok("the module bounds the real deadline at 30 s",
    readFileSync(join(HERE, "..", "src", "voiceprint-settings.js"), "utf8").includes("TIMEOUT_MS = 30_000"));
});

test("the page never uses innerHTML on PC text", () => {
  const src = readFileSync(join(HERE, "..", "src", "voiceprint-settings.js"), "utf8");
  ok("no innerHTML sink", !src.includes(".innerHTML"));
  ok("no outerHTML sink", !src.includes(".outerHTML"));
  ok("no insertAdjacentHTML sink", !src.includes("insertAdjacentHTML("));
  ok("text is placed with textContent", src.includes("textContent"));
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${e && e.message ? e.message : e}`);
  }
}
console.log(`\n${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
