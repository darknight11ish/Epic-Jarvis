/**
 * The conversation the quickbar sends with each question - src/chat-history.js.
 *
 * Needs no browser. The quickbar used to send the newest question alone, so
 * every follow-up started from nothing; these pin how the conversation is
 * kept inside the model's 16K window, and that the phone keeps it the same
 * way (jarvis-client/.../net/ChatHistory.kt), number for number.
 *
 *   node tests/chat-history.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  MAX_EXCHANGES,
  MAX_CHARS,
  KEEP_EXCHANGES,
  KEEP_CHARS,
  commitExchange,
  historyChars,
  historyMessages,
} from "../src/chat-history.js";

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

const build = (pairs) => pairs.reduce((w, [q, a]) => commitExchange(w, q, a), []);
const sized = (tag, chars) => [tag, "a".repeat(chars - tag.length)];
const numbered = (n) => Array.from({ length: n }, (_, i) => [`q${i + 1}`, `a${i + 1}`]);

check("a follow-up carries the earlier turns, oldest first, as user/assistant pairs", () => {
  const w = build([["when is the dentist?", "Tuesday at 3."], ["and the vet?", "Friday."]]);
  assert.deepEqual(historyMessages(w), [
    { role: "user", content: "when is the dentist?" },
    { role: "assistant", content: "Tuesday at 3." },
    { role: "user", content: "and the vet?" },
    { role: "assistant", content: "Friday." },
  ]);
});

check("nothing but role and content, and only user and assistant", () => {
  const msgs = historyMessages(build(numbered(3)));
  for (const m of msgs) {
    assert.deepEqual(Object.keys(m).sort(), ["content", "role"]);
    assert.ok(m.role === "user" || m.role === "assistant");
  }
});

check("a blank question or answer is not kept, and the window is never mutated", () => {
  const w = build([["q", "a"]]);
  const frozen = JSON.stringify(w);
  assert.equal(commitExchange(w, "  ", "answer"), w);
  assert.equal(commitExchange(w, "question", ""), w);
  assert.equal(commitExchange(w, "question", " \n "), w);
  commitExchange(w, "another", "one");
  assert.equal(JSON.stringify(w), frozen, "commitExchange changed the window it was given");
});

check("up to ten short turns are all kept", () => {
  const w = build(numbered(10));
  assert.equal(w.length, 10);
  assert.equal(w[0].question, "q1");
});

check("the eleventh drops the oldest down to six, not just one", () => {
  const w = build(numbered(11));
  assert.equal(w.length, KEEP_EXCHANGES);
  assert.deepEqual(w.map((e) => e.question), ["q6", "q7", "q8", "q9", "q10", "q11"]);
});

check("the character limit trims too, down to the lower mark", () => {
  const w6 = build(Array.from({ length: 6 }, (_, i) => sized(`q${i + 1}`, 3000)));
  assert.equal(w6.length, 6);
  assert.equal(historyChars(w6), MAX_CHARS);
  const w7 = commitExchange(w6, "q7", "a".repeat(2998));
  assert.deepEqual(w7.map((e) => e.question), ["q4", "q5", "q6", "q7"]);
  assert.ok(historyChars(w7) <= KEEP_CHARS);
});

check("after a trim the start stays put for several turns (prompt cache)", () => {
  let w = build(numbered(11));
  const first = w[0];
  for (let i = 0; i < 4; i++) {
    w = commitExchange(w, `more${i}`, "ok");
    assert.equal(w[0], first, `turn ${i} moved the start`);
  }
  assert.equal(w.length, 10);
});

check("one big answer is kept alone rather than lost, if it fits at all", () => {
  const w = build([sized("q1", 500), sized("q2", 500)]);
  const [q, a] = sized("big", 17500);
  assert.deepEqual(commitExchange(w, q, a).map((e) => e.question), ["big"]);
});

check("a turn too big to send at all leaves no history", () => {
  const [q, a] = sized("huge", MAX_CHARS + 1);
  assert.deepEqual(commitExchange(build([["q1", "a1"]]), q, a), []);
});

check("whatever is committed, neither limit is ever exceeded", () => {
  let w = [];
  const sizes = [10, 5000, 40, 9000, 1, 17999, 300, 2500, 2500, 2500, 20000, 7];
  sizes.forEach((n, i) => {
    w = commitExchange(w, `q${i}`, "a".repeat(n));
    assert.ok(w.length <= MAX_EXCHANGES, `too many after ${i}`);
    assert.ok(historyChars(w) <= MAX_CHARS, `too long after ${i}`);
  });
});

check("the budget arithmetic in the header still adds up", () => {
  // 16,384 tokens, minus answer 2,048, system 250, recalled facts 400,
  // tools 2,600, new question 3,000. History at 3 chars/token must fit.
  const room = 16384 - 2048 - 250 - 400 - 2600 - 3000;
  assert.ok(MAX_CHARS / 3 <= room);
  assert.ok(KEEP_CHARS < MAX_CHARS && KEEP_EXCHANGES < MAX_EXCHANGES);
});

check("the phone keeps the conversation by the same numbers", () => {
  const kt = readFileSync(
    fileURLToPath(
      new URL(
        "../../jarvis-client/app/src/main/java/com/jarvis/client/net/ChatHistory.kt",
        import.meta.url
      )
    ),
    "utf8"
  );
  const constant = (name) => {
    const m = kt.match(new RegExp(`const val ${name} = ([0-9_]+)`));
    assert.ok(m, `ChatHistory.kt has no ${name}`);
    return Number(m[1].replace(/_/g, ""));
  };
  assert.equal(constant("MAX_EXCHANGES"), MAX_EXCHANGES);
  assert.equal(constant("MAX_CHARS"), MAX_CHARS);
  assert.equal(constant("KEEP_EXCHANGES"), KEEP_EXCHANGES);
  assert.equal(constant("KEEP_CHARS"), KEEP_CHARS);
});

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nthe conversation is kept to budget");
