/**
 * The big Jarvis window's prompt window must move in BLOCKS, not slide.
 *
 * `jarvis_hud.html` used to send `S.messages.slice(-12)`. Past the twelfth
 * message that drops the oldest one on every turn, so the message part of the
 * prompt differed from its first token every turn and nothing could be reused
 * from the model's cache: measured 2026-10-07 over a twelve-turn exchange,
 * 5,822 of 7,279 message tokens (80%) were re-read for nothing.
 *
 * `windowForPrompt` keeps whole exchanges and only moves its boundary when the
 * window is genuinely too big, which is what `chat-history.js` (the Jarvis
 * bar) and `ChatHistory.kt` (the phone) already do for their own histories.
 *
 * The function is lifted out of the page and run as it is, the way
 * approvals-contract.mjs and card-words.mjs treat the HUD's other helpers - so
 * this suite reads the SHIPPED text, not a copy of it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const HUD = readFileSync(join(HERE, "..", "src", "jarvis_hud.html"), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const num = (name) => {
  const m = HUD.match(new RegExp(`const ${name} = (\\d+)\\s*;`));
  assert.ok(m, `jarvis_hud.html has no const ${name}`);
  return m[1];
};

const KEEP = Number(num("KEEP_MESSAGES"));
const SMALL = Number(num("DROP_TO_MESSAGES"));
const body = HUD.match(/function windowForPrompt\(messages, drop\)\{[\s\S]*?\n\}\n/);
assert.ok(body, "jarvis_hud.html has no windowForPrompt(messages, drop)");
const windowForPrompt = new Function(
  "const KEEP_MESSAGES = " + KEEP + ";\n" +
  "const DROP_TO_MESSAGES = " + SMALL + ";\n" +
  body[0] +
  "\nreturn windowForPrompt;")();

/** n exchanges, oldest first: user then assistant. */
const exchanges = (n) => {
  const out = [];
  for (let i = 1; i <= n; i += 1) {
    out.push({ role: "user", content: `question ${i}` });
    out.push({ role: "assistant", content: `answer ${i}` });
  }
  return out;
};

/** What the page does: send, then remember the drop for the next send. */
const send = (state, messages) => {
  const got = windowForPrompt(messages, state.drop);
  state.drop = got.drop;
  return got.window;
};

check("a short conversation is sent whole", () => {
  const six = exchanges(6);                        // exactly the window
  assert.deepEqual(send({ drop: 0 }, six), six);
  const one = exchanges(1);
  assert.deepEqual(send({ drop: 0 }, one), one);
  assert.deepEqual(send({ drop: 0 }, []), []);
});

check("a conversation past the window is trimmed, never grown", () => {
  const sent = send({ drop: 0 },
    exchanges(6).concat([{ role: "user", content: "question 7" }]));
  assert.ok(sent.length <= KEEP,
    `13 messages went out as ${sent.length}; the window is ${KEEP}`);
  assert.ok(sent.length >= SMALL - 1,
    `it trimmed to ${sent.length}, below the small window ${SMALL}`);
});

check("the boundary holds still between drops, so messages are reused", () => {
  // THE regression this exists for. A model reuses a prompt from its first
  // token onward, so what matters is how many of last turn's messages are
  // still there, unchanged, at the front of this turn's. A sliding window
  // keeps ZERO - its first message is a different one every single turn.
  const state = { drop: 0 };
  let msgs = exchanges(6);
  let previous = send(state, msgs).map((m) => JSON.stringify(m));
  const turns = 14;
  let totalReused = 0;
  let total = 0;
  let quietTurns = 0;
  for (let i = 7; i <= 6 + turns; i += 1) {
    msgs = msgs.concat([
      { role: "user", content: `question ${i}` },
      { role: "assistant", content: `answer ${i}` },
    ]);
    const now = send(state, msgs).map((m) => JSON.stringify(m));
    let same = 0;
    while (same < previous.length && same < now.length && previous[same] === now[same]) same += 1;
    totalReused += same;
    total += previous.length;
    if (same > 0) quietTurns += 1;
    previous = now;
  }
  assert.ok(quietTurns > 0,
    "not one turn reused a single message - the window slides every turn");
  assert.ok(totalReused / total >= 0.4,
    `only ${Math.round(100 * totalReused / total)}% of last turn's messages were reused; ` +
    `a block trim should keep most of them, a sliding window keeps 0%`);
  assert.ok(send(state, msgs).length <= KEEP, "the window grew past KEEP_MESSAGES");
});

check("the newest message and whole exchanges survive every size", () => {
  for (let n = 13; n <= 40; n += 1) {
    const all = exchanges(20).slice(0, n);
    const sent = send({ drop: 0 }, all);
    assert.equal(sent[sent.length - 1], all[n - 1], `the newest message was dropped (n=${n})`);
    if (sent.length !== all.length) {
      assert.equal(sent[0].role, "user",
        `the region starts on a ${sent[0].role} at n=${n}, so an answer lost its question`);
      assert.equal(sent.length % 2, all.length % 2,
        `a lone message was dropped at n=${n} (sent ${sent.length} of ${n})`);
    }
  }
});

check("a leading system turn is kept, and the trim starts after it", () => {
  const withSystem = [{ role: "system", content: "rules" }].concat(exchanges(10));
  const sent = send({ drop: 0 }, withSystem);
  assert.equal(sent[0].role, "system", "the conversation's opening instruction must survive");
  assert.equal(sent[0].content, "rules");
  assert.equal(sent[1].role, "user", "an exchange, not a lone message, follows it");
});

check("it does not mutate the page's own array", () => {
  const msgs = exchanges(12);
  const before = JSON.stringify(msgs);
  send({ drop: 0 }, msgs);
  assert.equal(JSON.stringify(msgs), before, "S.messages must not be edited in place");
});

check("nonsense input is not fatal", () => {
  assert.deepEqual(send({ drop: 0 }, undefined), []);
  assert.deepEqual(send({ drop: 0 }, null), []);
  assert.deepEqual(send({ drop: 0 }, "not an array"), []);
  assert.deepEqual(send({ drop: -5 }, exchanges(1)), exchanges(1));
  assert.deepEqual(send({ drop: 9999 }, exchanges(1)), exchanges(1),
    "a stale count must not blank the prompt");
  assert.deepEqual(send({}, exchanges(1)), exchanges(1), "an absent count must not blank the prompt");
});

check("the page sends the window, not a bare slice", () => {
  assert.match(HUD, /messages: promptWindow\(\)\.window/,
    "jarvis_hud.html no longer sends promptWindow().window");
  assert.doesNotMatch(HUD, /messages: S\.messages\.slice\(-/,
    "the sliding slice is back - it re-reads the whole conversation every turn");
  assert.match(HUD, /S\.dropped = got\.drop;/,
    "the sticky drop count is no longer remembered, so the window would slide again");
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\nall prompt-window checks passed");
