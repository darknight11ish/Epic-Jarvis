/**
 * Gemini ruling 5 (2026-10-31): a chat loaded from the HUD's ARCHIVED list can
 * be continued, and continuing it must never hide the new turn in the Archive
 * filter. The page's answer: the first new message reopens that chat on the PC
 * BEFORE the message is sent (the existing /api/history/archive route with
 * archived:false) - auto-unarchive, the ruling's first allowed option.
 *
 *   node tests/hud-history-archived.mjs
 *
 * WHAT THIS PINS, without a browser (the real page is driven by the Playwright
 * cases in tests/hud-history.mjs, which CI runs):
 *
 *   - the host marks an archived conversation when it loads one, and clears
 *     the mark for a live one and for New chat;
 *   - send() reopens the archived chat first, using the EXISTING route, body
 *     {id, archived: false} and X-Jarvis-Client: hud, so new turns are filed
 *     into a chat the History list shows again;
 *   - the reopen is best-effort - a failed request must not stop the message;
 *   - the three HUD page copies stay byte-identical.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const ROOT = join(HERE, "..", "..");
const read = (file) => readFileSync(file, "utf8");
const readBytes = (file) => readFileSync(file);

const PAGE = read(join(SRC, "jarvis_hud.html"));

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

check("the host marks a loaded ARCHIVED conversation, and only that", () => {
  assert.ok(PAGE.includes("window.__jarvisArchivedContinue = c.archived === true ? S.conversationId : \"\";"),
    "the page does not mark/clear the archived-continue state from the conversation");
});

check("New chat clears the archived-continue state", () => {
  const newChat = PAGE.slice(PAGE.indexOf("newChat: function () {"));
  assert.ok(newChat.slice(0, 260).includes('window.__jarvisArchivedContinue = "";'),
    "New chat can leave a stale archived id behind");
});

check("send() reopens the archived chat BEFORE the turn goes out", () => {
  const sendAt = PAGE.indexOf("async function send()");
  const bodyAt = PAGE.indexOf("const body = {", sendAt);
  const reopenAt = PAGE.indexOf("/api/history/archive", sendAt);
  assert.ok(sendAt > 0 && bodyAt > reopenAt && reopenAt > sendAt,
    "the reopen is not in send(), or it happens after the chat request is built");
  assert.ok(PAGE.includes('body: JSON.stringify({id: archivedId, archived: false})'),
    "the reopen does not use the existing archive route's {id, archived:false} body");
  assert.ok(PAGE.includes('"X-Jarvis-Client":"hud"'),
    "the reopen does not identify itself as the HUD");
});

check("the reopen is best-effort: the message still sends if it fails", () => {
  const sendAt = PAGE.indexOf("async function send()");
  const bodyAt = PAGE.indexOf("const body = {", sendAt);
  const block = PAGE.slice(sendAt, bodyAt);
  assert.match(block, /catch\(err\)\{\s*\/\* older PC or a dropped connection: send anyway \*\//,
    "a failed unarchive would throw and stop the message");
  assert.match(block, /window\.__jarvisArchivedContinue = "";[\s\S]*?try\{/,
    "the mark is not cleared before the attempt (a retry could reopen the wrong chat)");
});

check("the sidebar's archived refusal is unchanged (nothing else was loosened)", () => {
  const HISTORY = read(join(SRC, "hud-history.js"));
  assert.ok(HISTORY.includes("ARCHIVED_NOT_CONTINUED"),
    "the archived row's honest sentence is gone");
});

check("the three HUD page copies stay byte-identical", () => {
  const files = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
  ];
  const first = readBytes(files[0]);
  for (const file of files.slice(1)) {
    assert.ok(first.equals(readBytes(file)), `${files[0]} and ${file} differ`);
  }
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
