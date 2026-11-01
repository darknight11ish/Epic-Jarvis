/**
 * A History row opens that chat in the main HUD and continues it (the owner's
 * request, 2026-10-31: live the HUD sidebar said "This window cannot open a
 * chat on its own - open the Brain's History tab"; he wants the row to load
 * the conversation into the main HUD chat and let him carry on).
 *
 *   node tests/hud-history-open.mjs
 *
 * WHAT THIS PINS, without a browser (the real page is driven by the Playwright
 * cases in tests/hud-history.mjs, which CI runs):
 *
 *   - the read is the EXISTING PC route, `/api/history/conversation?id=` (no
 *     new route was added);
 *   - the page's own host really opens a kept chat: `hudHistoryHost.open`
 *     draws its turns with `addMessage` and makes it the conversation new
 *     messages belong to by setting `S.conversationId` to the chat's own id -
 *     which is what the page sends as `conversation_id`, so the main chat
 *     continues the SAME conversation;
 *   - a non-continuable record (someone else's conversation) is drawn
 *     read-only with a NEW id, so typing never files words into that record;
 *   - the sad fallback sentence survives only for a page with NO host at all
 *     (a standalone window), and the sidebar re-reads the host lazily first;
 *   - the three copies of the sidebar module and of the row-action table are
 *     byte-identical, as are the three HUD page copies.
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
const HISTORY = read(join(SRC, "hud-history.js"));

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok   ${name}`);
}

check("a row opens the EXISTING conversation read route - no new route", () => {
  assert.ok(HISTORY.includes('"/api/history/conversation?id=" + encodeURIComponent(row.id)'),
    "the History sidebar no longer reads the PC's own conversation route");
  assert.ok(!/\/api\/history\/open|\/api\/chat\/resume|\/api\/conversations\//.test(HISTORY),
    "a new open/resume route was added instead of reusing the real one");
});

check("the page's host opens a kept chat into the main HUD thread", () => {
  assert.match(PAGE, /window\.hudHistoryHost = \{/);
  assert.match(PAGE, /open: function \(conv\) \{/);
  assert.match(PAGE, /S\.conversationId = record \? newConversationId\(\) : String\(c\.id \|\| newConversationId\(\)\)/,
    "the opened chat's own id is not made the conversation new messages belong to");
  assert.match(PAGE, /addMessage\("user", words, when\)/);
  assert.match(PAGE, /addMessage\("jarvis", words, when\)/);
  assert.match(PAGE, /conversation_id: S\.conversationId/,
    "the next chat turn does not carry the opened conversation's id");
});

check("turn timestamps ride with the bubbles (the caret menu's real source)", () => {
  assert.match(PAGE, /const when = turn\.at !== undefined && turn\.at !== null \? turn\.at : null;/,
    "a kept chat's turn time is not read");
  assert.match(PAGE, /data-at/,
    "the turn time is not put on the message for the answer menu");
  assert.match(PAGE, /function addMessage\(role, text, at\)/,
    "addMessage does not accept the turn time");
});

check("a non-continuable record is read-only and gets a new id", () => {
  assert.match(PAGE, /const record = c\.continuable === false;/);
  assert.ok(PAGE.includes("It can be read here, and it cannot be carried on"),
    "the read-only record's honest line is gone");
});

check("the fallback is honest and only for a page with no host at all", () => {
  assert.match(HISTORY, /root\.hudHistoryHost/,
    "the sidebar does not look at the page's own host");
  assert.match(HISTORY, /host && typeof host\.open === "function" \? function \(c\) \{ host\.open\(c\); \}/,
    "the lazy host open retry is missing");
  assert.match(HISTORY, /This window cannot open a chat on its own - open the Brain's History tab\./);
  // The refusal is inside the branch where NEITHER door exists.
  const at = HISTORY.indexOf("This window cannot open a chat on its own");
  const before = HISTORY.slice(Math.max(0, at - 700), at);
  assert.match(before, /typeof opener !== "function"/,
    "the fallback is not guarded by 'there is no opener at all'");
});

check("the row's own actions are the real routes", () => {
  for (const route of ["pin", "tag", "archive", "delete"]) {
    assert.ok(HISTORY.includes(`${route}: "/api/history/${route}"`),
      `the ${route} row action is not the PC's own route`);
  }
});

check("the three sidebar copies and the three page copies stay byte-identical", () => {
  const histFiles = [
    join(SRC, "hud-history.js"),
    join(ROOT, "jarvis-backend", "hud-history.js"),
    join(ROOT, "backend", "static", "hud-history.js"),
  ];
  const first = readBytes(histFiles[0]);
  for (const file of histFiles.slice(1)) {
    assert.ok(first.equals(readBytes(file)), `${histFiles[0]} and ${file} differ`);
  }
  const pageFiles = [
    join(SRC, "jarvis_hud.html"),
    join(ROOT, "jarvis-backend", "jarvis_hud.html"),
    join(ROOT, "backend", "jarvis_hud.html"),
  ];
  const firstPage = readBytes(pageFiles[0]);
  for (const file of pageFiles.slice(1)) {
    assert.ok(firstPage.equals(readBytes(file)), `${pageFiles[0]} and ${file} differ`);
  }
});

console.log(`\n${passed} passed, 0 skipped, 0 failed`);
