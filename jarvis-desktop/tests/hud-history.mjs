/**
 * The HUD's History sidebar (owner request 2026-10-27: "a history tab with a
 * column icon that opens up a menu that looks like all the coversations in
 * the deepseek harness on desktop for the jarvis HUD ... both should have
 * pinnable chats, project organization by chat, and more").
 *
 *   node tests/hud-history.mjs
 *
 * WHAT IS PROVEN HERE, without a browser (this suite is pure Node, so it runs
 * on every machine and in CI's frontend shards with no Playwright):
 *
 *   - ages read like the screenshot's ("25min", "7d", "11d") and never
 *     invent a time for a chat with none;
 *   - the panel's whole grouping: Pinned first and NOT repeated inside its
 *     tag, then one section per tag in the tag registry's own order, then
 *     Untagged; a chat whose tag is gone is shown, not lost;
 *   - a long section shows five rows and a "Show N more sessions" count; a
 *     collapsed one shows none; the one-off expansion shows all and then
 *     remembers nothing across a restart (only collapsed flags persist);
 *   - the search box filters by the chat's NAME only, and while searching
 *     every section is open and uncapped;
 *   - the sort is newest-first or A to Z, inside each section, without
 *     reordering the sections themselves;
 *   - the current chat is marked, and only it;
 *   - the three writes this panel may send are pin / tag / delete and
 *     nothing else, with the exact shapes the Rust command takes - and the
 *     delete sentence is the Brain's own, word for word;
 *   - the page's half is wired: one external script (no new inline block),
 *     `window.hudHistoryHost` with its three functions, all three vendored
 *     copies of the page byte-identical, the module byte-identical in
 *     backend/static/ and the published base, and the server's closed
 *     whitelist naming it;
 *   - the Rust side really is the only door for the writes: the command is
 *     in lib.rs's handler, build.rs's manifest and the HUD's own capability
 *     set; the reads go through hud_proxy's allow-list; and the lock
 *     redacts the three History reads while the private lists are hidden;
 *   - the module contains no HTML sink - every title it shows is put in with
 *     textContent, so a chat named "<b>x</b>" is text, not markup.
 *
 * NOT here: the real desktop window in WebView2 (a rebuild and install after
 * merge), and a real PC's history. CI's `rust` job runs the Rust-side unit
 * tests for the read-path checker and the write bodies (brain/history.rs).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";


const HERE = dirname(fileURLToPath(import.meta.url));
const DESKTOP = join(HERE, "..");
const REPO = join(DESKTOP, "..");
const SRC = join(DESKTOP, "src");
const read = (...parts) => readFileSync(join(...parts), "utf8");

const MODULE = read(SRC, "hud-history.js");
const PAGE = read(SRC, "jarvis_hud.html");

let passed = 0;
const failed = [];
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log("ok   " + name);
  } catch (error) {
    failed.push(name);
    console.log("FAIL " + name + "\n     " + String((error && error.message) || error));
  }
}

/* Load the module the way the page does - as a classic script whose global is
 * `window` - but in an empty context with no document, so nothing mounts and
 * nothing touches a browser API. */
const stub = { window: {}, console };
new Function("window", "console", MODULE)(stub.window, console);
const H = stub.window.hudHistory;
assert.ok(H, "the module did not export window.hudHistory");

const NOW = 1_790_000_000; // a fixed clock, so ages are not flaky
const T = (secondsAgo) => NOW - secondsAgo;

const row = (id, title, ago, extra = {}) => ({
  id,
  title,
  started: T(ago + 100),
  updated: T(ago),
  turns: 4,
  device: "hud",
  has_voice: false,
  tainted: false,
  kind: "chat",
  project: null,
  tag_id: null,
  pinned: false,
  ...extra,
});

const TAGS = [
  { id: 3, name: "Projects", colour: 3, icon: "folder", order: 3, count: 2 },
  { id: 1, name: "Work", colour: 0, icon: "briefcase", order: 1, count: 4 },
];

const LIST = [
  row("c-pin", "What is the capital of France", 7 * 86400, { pinned: true, tag_id: 1 }),
  row("c-w1", "Standup notes", 25 * 60, { tag_id: 1 }),
  row("c-w2", "Quarterly plan", 2 * 86400, { tag_id: 1 }),
  row("c-w3", "A letter to the bank", 11 * 86400, { tag_id: 1 }),
  row("c-w4", "The patio light", 20 * 86400, { tag_id: 1 }),
  row("c-p1", "Fix the loo", 3 * 86400, { tag_id: 3 }),
  row("c-p2", "Garage shelves", 30 * 86400, { tag_id: 3 }),
  row("c-u1", "What is on my list today", 40 * 60),
  row("c-gone", "Old tag chat", 5 * 86400, { tag_id: 9 }),
];

const build = (opts = {}) =>
  H.buildSections(LIST, TAGS, { now: NOW, cap: 5, ...opts });

/* ── ages ─────────────────────────────────────────────────────────────── */

check("an age reads like the screenshot: 25min, 7d, 11d", () => {
  assert.equal(H.ageWords(T(30), NOW), "now");
  assert.equal(H.ageWords(T(25 * 60), NOW), "25min");
  assert.equal(H.ageWords(T(90 * 60), NOW), "1h");
  assert.equal(H.ageWords(T(7 * 86400), NOW), "7d");
  assert.equal(H.ageWords(T(11 * 86400), NOW), "11d");
  assert.equal(H.ageWords(T(45 * 86400), NOW), "1mo");
  assert.equal(H.ageWords(T(400 * 86400), NOW), "1y");
});

check("a chat with no time says nothing rather than '56y'", () => {
  assert.equal(H.ageWords(0, NOW), "");
  assert.equal(H.ageTitle(0, NOW), "");
  assert.equal(H.ageWords(T(-30), NOW), "now", "a clock that is ahead is 'now'");
});

check("the words form is a whole sentence for a screen reader", () => {
  assert.equal(H.ageTitle(T(25 * 60), NOW), "25 minutes ago");
  assert.equal(H.ageTitle(T(7 * 86400), NOW), "7 days ago");
  assert.equal(H.ageTitle(T(86400), NOW), "1 day ago");
});

/* ── the sections ─────────────────────────────────────────────────────── */

check("Pinned is first, and a pinned chat is not repeated in its tag", () => {
  const got = build();
  assert.deepEqual(got.map((s) => s.key), ["pinned", "tag:1", "tag:3", "none"]);
  assert.deepEqual(got[0].rows.map((r) => r.id), ["c-pin"]);
  assert.ok(!got[1].rows.some((r) => r.id === "c-pin"), "the pinned chat is in Work too");
  assert.equal(got[0].title, "Pinned");
});

check("the tag sections follow the tag registry's order, not the list's", () => {
  const got = build();
  assert.deepEqual(got.filter((s) => s.kind === "tag").map((s) => s.title), [
    "Work",
    "Projects",
  ]);
});

check("each section counts every chat it holds, and shows five", () => {
  const got = build();
  const work = got.find((s) => s.key === "tag:1");
  assert.equal(work.count, 4, "four chats under Work (the pinned one is not one of them)");
  assert.equal(work.rows.length, 4, "four fit under the cap");
  assert.equal(work.more, 0);

  const many = H.buildSections(
    Array.from({ length: 9 }, (_, i) => row("c" + i, "Chat " + i, (i + 1) * 3600)),
    [],
    { now: NOW, cap: 5, sort: "recent" }
  );
  assert.equal(many.length, 1, "one Untagged section");
  assert.equal(many[0].count, 9);
  assert.equal(many[0].rows.length, 5, "five shown");
  assert.equal(many[0].more, 4, "four behind 'Show 4 more sessions'");
  assert.equal(many[0].title, "Untagged", "the same word the phone uses");
});

check("a chat whose tag is gone is shown under Untagged, not lost", () => {
  const got = build();
  assert.ok(got.find((s) => s.key === "none").rows.some((r) => r.id === "c-gone"));
  assert.equal(H.countRows(got), LIST.length, "every chat is in exactly one section");
});

check("a collapsed section shows no rows and no 'show more'", () => {
  const got = build({ expanded: { "tag:1": false } });
  const work = got.find((s) => s.key === "tag:1");
  assert.equal(work.open, false);
  assert.equal(work.rows.length, 0);
  assert.equal(work.more, 0);
  assert.equal(work.count, 4, "the count stays, so the header still says how many");
});

check("'Show N more' opens that section fully for this visit only", () => {
  const list = Array.from({ length: 8 }, (_, i) => row("c" + i, "Chat " + i, (i + 1) * 3600));
  const capped = H.buildSections(list, [], { now: NOW, cap: 5, expanded: {} });
  assert.equal(capped[0].more, 3);
  const opened = H.buildSections(list, [], {
    now: NOW,
    cap: 5,
    expanded: { "!none": true },
  });
  assert.equal(opened[0].rows.length, 8);
  assert.equal(opened[0].more, 0);
  // ... and the one-off flag is not one of the remembered ones: the panel
  // writes only the collapsed keys to localStorage.
  assert.match(MODULE, /function pickRemembered/, "the panel remembers collapses only");
});

check("every row carries what the panel draws, and only one is current", () => {
  const got = build({ current: "c-w2" });
  const flat = got.flatMap((s) => s.rows);
  const current = flat.filter((r) => r.current);
  assert.deepEqual(current.map((r) => r.id), ["c-w2"]);
  const w2 = flat.find((r) => r.id === "c-w2");
  assert.equal(w2.age, "2d");
  assert.equal(w2.ageLong, "2 days ago");
  assert.equal(w2.kind, "chat");
  assert.equal(w2.tag_id, 1);
  assert.equal(w2.pinned, false);
});

/* ── search ───────────────────────────────────────────────────────────── */

check("the search box filters by the chat's name, and by nothing else", () => {
  const all = build({ query: "standup" });
  assert.equal(all.length, 1);
  assert.deepEqual(all[0].rows.map((r) => r.id), ["c-w1"]);
  const none = build({ query: "zzzz" });
  assert.deepEqual(none, []);
  const ci = build({ query: "  STANDUP " });
  assert.deepEqual(ci[0].rows.map((r) => r.id), ["c-w1"], "case and spaces ignored");
});

check("while searching, every section is open and shows all its matches", () => {
  const list = Array.from({ length: 8 }, (_, i) =>
    row("c" + i, "Letter " + i, (i + 1) * 3600)
  );
  const got = H.buildSections(list, [], {
    now: NOW,
    cap: 2,
    query: "letter",
    expanded: { none: false },
  });
  assert.equal(got[0].open, true, "a collapsed section opens while searching");
  assert.equal(got[0].rows.length, 8);
  assert.equal(got[0].more, 0);
});

/* ── sort ─────────────────────────────────────────────────────────────── */

check("newest first is the default, and A to Z is the other way", () => {
  const recent = H.buildSections(
    [row("a", "Zebra", 100), row("b", "Apple", 200), row("c", "Mango", 50)],
    [],
    { now: NOW, cap: 5 }
  );
  assert.deepEqual(recent[0].rows.map((r) => r.id), ["c", "a", "b"]);
  const named = H.buildSections(
    [row("a", "Zebra", 100), row("b", "Apple", 200), row("c", "Mango", 50)],
    [],
    { now: NOW, cap: 5, sort: "name" }
  );
  assert.deepEqual(named[0].rows.map((r) => r.id), ["b", "c", "a"]);
});

check("sorting never reorders the sections themselves", () => {
  const got = build({ sort: "name" });
  assert.deepEqual(got.map((s) => s.key), ["pinned", "tag:1", "tag:3", "none"]);
  const work = got.find((s) => s.key === "tag:1");
  assert.deepEqual(work.rows.map((r) => r.title), [
    "A letter to the bank",
    "Quarterly plan",
    "Standup notes",
    "The patio light",
  ]);
});

/* ── the three writes ─────────────────────────────────────────────────── */

check("a write is pin, tag or delete - one chat, and that action's own value", () => {
  assert.deepEqual(H.actArgs("pin", "conv-aaaa", true), {
    action: "pin",
    id: "conv-aaaa",
    pinned: true,
  });
  assert.deepEqual(H.actArgs("pin", "conv-aaaa", false), {
    action: "pin",
    id: "conv-aaaa",
    pinned: false,
  });
  assert.deepEqual(H.actArgs("tag", "conv-aaaa", 7), {
    action: "tag",
    id: "conv-aaaa",
    tag: 7,
  });
  assert.deepEqual(H.actArgs("tag", "conv-aaaa", null), {
    action: "tag",
    id: "conv-aaaa",
    tag: null,
  });
  assert.deepEqual(H.actArgs("delete", "conv-aaaa"), {
    action: "delete",
    id: "conv-aaaa",
  });
  for (const bad of [
    ["pin", "conv-aaaa", "yes"],
    ["pin", "conv-aaaa"],
    ["archive", "conv-aaaa"],
    ["tag", "conv-aaaa", "7"],
    ["tag", "conv-aaaa", 0],
    ["tag", "conv-aaaa", -1],
    ["delete", ""],
  ]) {
    assert.equal(H.actArgs(...bad), null, JSON.stringify(bad) + " was accepted");
  }
});

check("the delete sentence is the Brain's own, word for word", () => {
  const view = read(SRC, "history-view.js");
  const at = view.indexOf("export const DELETE_KEEPS_FACTS =");
  assert.notEqual(at, -1, "history-view.js no longer exports DELETE_KEEPS_FACTS");
  const tail = view.slice(at);
  const expr = tail.slice(tail.indexOf("=") + 1, tail.indexOf(";"));
  const parts = [...expr.matchAll(/"([^"]*)"/g)].map((m) => m[1]);
  assert.equal(H.DELETE_KEEPS_FACTS, parts.join(""),
    "the HUD and the Brain would say it two different ways");
});

/* ── glyphs ───────────────────────────────────────────────────────────── */

check("every tag icon and every kind has its own glyph", () => {
  for (const name of H.TAG_ICONS) {
    assert.notEqual(H.glyphPath(name), H.glyphPath("no-such-icon"), name + " falls back");
  }
  assert.equal(H.glyphPath("no-such-icon"), H.glyphPath("chat"), "unknown lands on the bubble");
  for (const kind of ["live", "support", "chatbot", "compare"]) {
    assert.notEqual(H.glyphPath(kind), H.glyphPath("no-such-icon"), kind + " falls back");
  }
  const seen = new Set(H.TAG_ICONS.map((n) => H.glyphPath(n)));
  assert.equal(seen.size, H.TAG_ICONS.length, "two tag icons draw the same glyph");
});

check("the ten tag icons are the shared contract's ten, in its order", () => {
  assert.deepEqual(H.TAG_ICONS, [
    "briefcase",
    "book",
    "home",
    "folder",
    "lightbulb",
    "star",
    "flag",
    "wrench",
    "leaf",
    "music",
  ]);
});

/* ── the page's half, and the copies ──────────────────────────────────── */

check("the page loads the module with one external script and no new inline block", () => {
  assert.match(PAGE, /<script src="hud-history\.js" defer><\/script>/);
  const before = read(REPO, "backend", "jarvis_hud.html");
  assert.equal(PAGE, before, "the page and its backend copy have drifted");
});

check("the page's half is hudHistoryHost, with the three functions the panel calls", () => {
  assert.match(PAGE, /window\.hudHistoryHost = \{/);
  assert.match(PAGE, /current: function \(\) \{\s*return S\.conversationId;/);
  assert.match(PAGE, /open: function \(conv\) \{/);
  assert.match(PAGE, /newChat: function \(\) \{/);
  assert.match(PAGE, /continuable === false/,
    "a support/chatbot record must not be continued in this window");
});

check("all three vendored copies of the page are byte-identical", () => {
  const a = read(SRC, "jarvis_hud.html");
  const b = read(REPO, "backend", "jarvis_hud.html");
  const c = read(REPO, "jarvis-backend", "jarvis_hud.html");
  assert.equal(a, b);
  assert.equal(a, c);
});

check("the module is byte-identical in the three places it ships", () => {
  const a = MODULE;
  assert.equal(read(REPO, "backend", "static", "hud-history.js"), a);
  assert.equal(read(REPO, "jarvis-backend", "hud-history.js"), a);
});

check("the server's closed whitelist names the module", () => {
  const base = read(REPO, "jarvis-backend", "jarvis_hud.py");
  assert.match(base, /"\/hud-history\.js": \("hud-history\.js"/);
});

/* ── the Rust side: the reads, the write, the lock ────────────────────── */

const RUST = join(DESKTOP, "src-tauri", "src");
const rustHistory = read(RUST, "brain", "history.rs");
const rustProxy = read(RUST, "hud_proxy.rs");
const rustLock = read(RUST, "lock", "rules.rs");
const rustLib = read(RUST, "lib.rs");
const rustBuild = read(join(DESKTOP, "src-tauri"), "build.rs");
const capability = read(join(DESKTOP, "src-tauri"), "capabilities", "hud.json");
const surfaces = read(join(DESKTOP, "src-tauri"), "permissions", "surfaces.toml");

check("the HUD's reads go through the proxy's allow-list, whose shape is checked once", () => {
  assert.match(rustProxy, /crate::brain::history::history_read_path\(path\)/);
  assert.match(rustHistory, /pub\(crate\) fn history_read_path\(path: &str\) -> Option<String>/);
});

check("the write command exists in the handler, the manifest and the HUD's own set", () => {
  assert.match(rustLib, /brain::history::hud_history_act,/);
  assert.match(rustBuild, /"hud_history_act",/);
  assert.match(capability, /"hud-history"/);
  assert.match(surfaces, /identifier = "hud-history"/);
  assert.match(surfaces, /"allow-hud-history-act"/);
});

check("the write asks the hidden lists and the live link, in that order", () => {
  const at = rustHistory.indexOf("pub async fn hud_history_act(");
  assert.notEqual(at, -1);
  const body = rustHistory.slice(at, rustHistory.indexOf("\n}", at));
  const hidden = body.indexOf("private_hidden");
  const live = body.indexOf("require_link_live");
  const post = body.indexOf("post(");
  assert.ok(hidden !== -1 && live !== -1 && post !== -1, "a guard is missing");
  assert.ok(hidden < live && live < post, "the guards do not come before the write");
});

check("the lock takes the words out of the three History reads", () => {
  for (const route of ["/api/history", "/api/history/conversation", "/api/history/tags"]) {
    assert.ok(rustLock.includes('"' + route + '"'), route + " is not redacted");
  }
  assert.match(rustLock, /crate::brain::history::redact_list/);
  assert.match(rustLock, /crate::brain::history::redact_tags/);
});

check("the HUD's static whitelist, the patcher and the base all carry the module", () => {
  const base = read(REPO, "jarvis-backend", "jarvis_hud.py");
  const ps1 = read(REPO, "scripts", "apply-patches.ps1");
  const where = read(REPO, "backend", "_where.py");
  assert.ok(base.includes("/hud-history.js"));
  assert.ok(ps1.includes("'static/hud-history.js'"));
  assert.ok(where.includes('"static/hud-history.js"'));
});

/* ── no HTML sink ─────────────────────────────────────────────────────── */

check("every title reaches the page as text, never as markup", () => {
  assert.doesNotMatch(MODULE, /\.innerHTML\s*=/, "an innerHTML sink in the sidebar");
  assert.doesNotMatch(MODULE, /insertAdjacentHTML|outerHTML|document\.write/);
  assert.match(MODULE, /textContent/, "the panel should draw with textContent");
});

console.log(`\n${passed} passed, 0 skipped, ${failed.length} failed`);
if (failed.length) {
  console.log("failed: " + failed.join(", "));
  process.exitCode = 1;
}
