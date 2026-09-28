/**
 * Brain › Model offers "Use" only on a model that can chat - held to
 * tests/fixtures/model-chat-cases.json, which tools/gen_model_chat_cases.py
 * writes for both apps. The phone's ModelChatContractTest reads a
 * byte-identical copy, so the two apps cannot drift apart on which rows get
 * "Use" or on the words said instead.
 *
 *     node tests/model-chat.mjs
 *
 * No browser: src/model-chat.js is imported as it is. brain-producers.mjs
 * checks the rows on the real page.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CANNOT_CHAT, canChat } from "../src/model-chat.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(readFileSync(join(HERE, "fixtures", "model-chat-cases.json"), "utf8"));

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

check("the words match the shared table", () => {
  assert.equal(CANNOT_CHAT, CASES.cannot_chat);
});

check("the table is not empty, and has both answers", () => {
  assert.ok(CASES.cases.some((c) => c.chats));
  assert.ok(CASES.cases.some((c) => !c.chats));
});

for (const c of CASES.cases) {
  const row = { ref: c.ref };
  if ("family" in c) row.family = c.family;
  if ("capabilities" in c) row.capabilities = c.capabilities;
  check(`${JSON.stringify(row)} ${c.chats ? "can" : "cannot"} chat`, () => {
    assert.equal(canChat(row, c.ref), c.chats);
  });
}

if (fails.length) {
  console.log(`\n${fails.length} failed`);
  process.exit(1);
}
console.log("\nall passed");
