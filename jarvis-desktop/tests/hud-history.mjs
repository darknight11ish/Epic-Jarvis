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
 *     delete sentence is the Brain's own, word for word (ARCHIVE joined them
 *     on 2026-10-29: one reversible flag, no question, and the Archived list
 *     is the same read with `archived=1`);
 *   - an archived chat is put away, not deleted: one Archived section, no
 *     confirm, never opened from the live list, and Unarchive brings it back;
 *   - the page's main strip carries ONE History door in every shell whose left
 *     layout shell, and it calls the SAME open routine as the rail icon (one
 *     panel, one list - the owner's ask of 2026-10-29: "i want the chat
 *     history accesible directly from the jarvis hud on desktop");
 *   - the page's half is wired: one external script (no new inline block),
 *     `window.hudHistoryHost` with its three functions, all three vendored
 *     copies of the page byte-identical, the module byte-identical in
 *     backend/static/ and the published base, and the server's closed
 *     whitelist naming it;
 *   - an open group's chevron points DOWN and a collapsed one points RIGHT.
 *     The caret is the page's one right-pointing chevron, so the rotation is
 *     the whole reading; the rule used to rotate the CLOSED case instead, which
 *     left an open section looking collapsed beside its own rows;
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
import { fileURLToPath, pathToFileURL } from "node:url";


const HERE = dirname(fileURLToPath(import.meta.url));
const DESKTOP = join(HERE, "..");
const REPO = join(DESKTOP, "..");
const SRC = join(DESKTOP, "src");
const read = (...parts) => readFileSync(join(...parts), "utf8");

const MODULE = read(SRC, "hud-history.js");
const ACTIONS = read(SRC, "history-actions.js");
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

/* Load the module the way the page does - an ES module whose global is
 * `window` (there is none in Node, so it takes `globalThis`) - with no
 * document, so nothing mounts and nothing touches a browser API. */
await import(pathToFileURL(join(SRC, "hud-history.js")).href);
const H = globalThis.hudHistory;
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
  // Put away (2026-10-29): only the PC's own `true` says so.
  assert.equal(H.rowOf({ id: "c", archived: true }, NOW, "").archived, true);
  assert.equal(H.rowOf({ id: "c", archived: false }, NOW, "").archived, false);
  assert.equal(H.rowOf({ id: "c" }, NOW, "").archived, false);
});

/* ── the archived list ────────────────────────────────────────────────── */

check("the Archived list is ONE section: pins and tags do not regroup it", () => {
  const list = [
    row("a", "Away one", 100, { archived: true, pinned: true, tag_id: 1 }),
    row("b", "Away two", 50, { archived: true, tag_id: 3 }),
    row("c", "Still live", 10),
  ];
  const got = H.buildSections(list, TAGS, { now: NOW, archived: true });
  assert.equal(got.length, 1, "the archived list was grouped like the live one");
  assert.equal(got[0].key, "archived");
  assert.equal(got[0].title, "Archived");
  assert.deepEqual(got[0].rows.map((r) => r.id), ["b", "a"],
    "the archived list is not newest first");
  assert.equal(got[0].count, 2);
  assert.equal(H.buildSections([], [], { now: NOW, archived: true }).length, 0);
  // The live list still groups exactly as it always has.
  assert.deepEqual(build().map((s) => s.key), ["pinned", "tag:1", "tag:3", "none"]);
});

check("a long archived list caps and remembers its collapse like any other", () => {
  const many = Array.from({ length: 8 }, (_, i) =>
    row("x" + i, "Away " + i, (i + 1) * 60, { archived: true }));
  const capped = H.buildSections(many, [], { now: NOW, cap: 5, archived: true });
  assert.equal(capped[0].rows.length, 5);
  assert.equal(capped[0].more, 3);
  const opened = H.buildSections(many, [], {
    now: NOW, cap: 5, archived: true, expanded: { "!archived": true },
  });
  assert.equal(opened[0].rows.length, 8);
  const collapsed = H.buildSections(many, [], {
    now: NOW, archived: true, expanded: { archived: false },
  });
  assert.equal(collapsed[0].open, false);
  assert.equal(collapsed[0].rows.length, 0);
  assert.equal(collapsed[0].count, 8, "a collapsed section still says how many");
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

/* ── the writes ───────────────────────────────────────────────────────── */

check("a write is pin, tag, archive or delete - one chat, and that action's own value", () => {
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
  // Archiving: ONE flag, both ways - reversible, so no confirm and no card.
  assert.deepEqual(H.actArgs("archive", "conv-aaaa", true), {
    action: "archive",
    id: "conv-aaaa",
    archived: true,
  });
  assert.deepEqual(H.actArgs("archive", "conv-aaaa", false), {
    action: "archive",
    id: "conv-aaaa",
    archived: false,
  });
  assert.deepEqual(H.actArgs("delete", "conv-aaaa"), {
    action: "delete",
    id: "conv-aaaa",
  });
  for (const bad of [
    ["pin", "conv-aaaa", "yes"],
    ["pin", "conv-aaaa"],
    ["archive", "conv-aaaa"],
    ["archive", "conv-aaaa", "yes"],
    ["archive", "conv-aaaa", 1],
    ["tag", "conv-aaaa", "7"],
    ["tag", "conv-aaaa", 0],
    ["tag", "conv-aaaa", -1],
    ["delete", ""],
  ]) {
    assert.equal(H.actArgs(...bad), null, JSON.stringify(bad) + " was accepted");
  }
  // The browser's POST bodies are the documented shapes: archive sends the id
  // and the one flag, and nothing else; delete is unchanged (no archived key).
  assert.deepEqual(H.actBody("archive", "conv-aaaa", true), {
    id: "conv-aaaa",
    archived: true,
  });
  assert.deepEqual(H.actBody("archive", "conv-aaaa", false), {
    id: "conv-aaaa",
    archived: false,
  });
  assert.deepEqual(H.actBody("delete", "conv-aaaa"), { id: "conv-aaaa" });
  assert.equal(Object.hasOwn(H.actBody("delete", "conv-aaaa"), "archived"), false);
});

check("the archive labels are the shared table's, and the Delete question did not move", () => {
  assert.equal(H.ACTION_LABELS.archive, "Archive");
  assert.equal(H.ACTION_LABELS.unarchive, "Unarchive");
  assert.equal(H.labelFor("archive", false, false), "Archive");
  assert.equal(H.labelFor("archive", false, true), "Unarchive");
  assert.deepEqual([...H.ROW_ACTIONS], ["open", "pin", "move", "archive", "delete"]);
  // Delete's confirmation is exactly what it was (the brief: keep it).
  assert.equal(H.DELETE_QUESTION, "Delete this conversation?");
  assert.ok(H.DELETE_REMOVES.includes("cannot be undone"));
  assert.ok(H.DELETE_KEEPS_FACTS.includes("Forget a time frame"));
  // Both windows read these from ONE file (2026-10-29, the same Gemini ruling
  // that shared pin/tag/delete): no second copy of any archived word.
  const sources = [MODULE, ACTIONS, read(SRC, "history-view.js"), read(SRC, "brain.js")];
  for (const name of ["ARCHIVED", "ARCHIVED_NOT_CONTINUED", "ARCHIVE_DONE",
    "UNARCHIVE_DONE", "ARCHIVE_CURRENT_DONE", "ROW_ACTIONS"]) {
    const found = sources.filter((text) =>
      new RegExp(`(?:export\\s+)?(?:const|var|let)\\s+${name}\\s*=`).test(text));
    assert.equal(found.length, 1, name + " is defined in " + found.length + " files");
  }
  assert.match(ACTIONS, /export const ARCHIVED_NOT_CONTINUED =/,
    "the shared module lost the archived sentence");
  assert.match(MODULE, /import \{[^}]*ARCHIVED_NOT_CONTINUED[^}]*\} from "\.\/history-actions\.js"/,
    "the HUD no longer imports the shared archived words");
  assert.match(read(SRC, "brain.js"),
    /import \{[^}]*ARCHIVED_NOT_CONTINUED[^}]*\} from "\.\/history-actions\.js"/,
    "the Brain no longer imports the shared archived words");
});

check("the delete words are ONE copy, the one both windows read", () => {
  // The Gemini ruling of 2026-10-27: share the row-action helpers, do not keep
  // two copies held equal by a test. So the sentence is defined in
  // history-actions.js and NOWHERE else, and the Brain re-exports it.
  const definitions = [MODULE, ACTIONS, read(SRC, "history-view.js"), read(SRC, "brain.js")]
    .filter((text) => /(?:export\s+)?(?:const|var|let)\s+DELETE_KEEPS_FACTS\s*=/.test(text));
  assert.deepEqual(
    definitions.map(() => "a copy"),
    ["a copy"],
    "DELETE_KEEPS_FACTS is defined in more than one file"
  );
  assert.match(ACTIONS, /export const DELETE_KEEPS_FACTS =/, "the shared module lost the words");
  assert.match(
    read(SRC, "history-view.js"),
    /import \{[^}]*DELETE_KEEPS_FACTS[^}]*\} from "\.\/history-actions\.js"/,
    "the Brain no longer imports the shared sentence"
  );
  assert.match(
    read(SRC, "history-view.js"),
    /export \{ DELETE_KEEPS_FACTS \};/,
    "history-view.js must keep its public export working"
  );
  assert.equal(H.DELETE_KEEPS_FACTS, H.DELETE_KEEPS_FACTS.trim());
  assert.ok(H.DELETE_KEEPS_FACTS.includes("Forget a time frame"));
  assert.ok(H.DELETE_QUESTION.includes("Delete this conversation?"));
  assert.ok(H.DELETE_REMOVES.includes("cannot be undone"));
  // The HUD's box shows the Brain's three sentences, in the Brain's order.
  const at = MODULE.indexOf("DELETE_QUESTION + \" \" + DELETE_REMOVES");
  assert.notEqual(at, -1, "the HUD's confirm no longer says the Brain's words");
  assert.ok(MODULE.indexOf("DELETE_KEEPS_FACTS", at) > at);
});

check("the row menu's labels come from the shared table, not from literals here", () => {
  assert.equal(H.ACTION_LABELS.delete, "Delete");
  assert.equal(H.labelFor("pin", false), "Pin chat");
  assert.equal(H.labelFor("pin", true), "Unpin chat");
  for (const action of ["open", "pin", "move", "archive", "delete"]) {
    assert.ok(H.ACTION_LABELS[action], action + " has no label");
    assert.ok(
      MODULE.includes('ACTION_LABELS.' + action) || MODULE.includes('labelFor("' + action),
      action + " is labelled with a literal in the HUD"
    );
  }
  // ... and the Brain's own History row uses the same table. Its archive label
  // is `historyLabelFor` because the Galaxy constellation already imported a
  // `labelFor` of its own; the table it reads is the shared one.
  assert.match(read(SRC, "brain.js"), /button\(ACTION_LABELS\.delete/);
  assert.match(read(SRC, "brain.js"), /ACTION_LABELS[\s\S]{0,500}\} from "\.\/history-actions\.js"/);
  assert.match(read(SRC, "brain.js"), /historyLabelFor\("archive"/,
    "the Brain's Archive label is not from the shared table");
  assert.match(read(SRC, "brain.js"), /labelFor as historyLabelFor/,
    "the Brain no longer imports the shared labelFor");
});

check("Archive asks no question in the menu; Delete keeps its confirm", () => {
  const menuAt = MODULE.indexOf("function openMenu(row, anchor)");
  const body = MODULE.slice(menuAt,
    MODULE.indexOf("/* ---- delete, with the page's own are-you-sure ---- */", menuAt));
  const archAt = body.indexOf('var archive = menuItem(labelFor("archive"');
  assert.notEqual(archAt, -1, "the row menu has no Archive item");
  const archItem = body.slice(archAt, body.indexOf("var del =", archAt));
  assert.match(archItem, /act\("archive", row\.id, true\)/,
    "Archive does not send the one archive action");
  assert.doesNotMatch(archItem, /askDelete/, "Archive asks a confirm - it is reversible");
  const delAt = body.indexOf("var del =");
  assert.match(body.slice(delAt, delAt + 400), /askDelete\(row, anchor\)/,
    "Delete no longer asks its question");
  // The archived list's own menu: Unarchive first, Delete still asks, and no
  // Open (an archived chat is not carried on from here).
  const archViewAt = body.indexOf("if (row.archived === true) {");
  assert.notEqual(archViewAt, -1, "the archived list has no menu of its own");
  const archView = body.slice(archViewAt,
    body.indexOf("var open = menuItem(ACTION_LABELS.open", archViewAt));
  assert.match(archView, /act\("archive", row\.id, false\)/,
    "the archived list offers no Unarchive");
  assert.match(archView, /askDelete\(row, anchor\)/,
    "Delete does not ask in the archived list");
  assert.doesNotMatch(archView, /openChat\(row\)/,
    "an archived row still opens from the archived list");
  // A click on an archived row says why it will not open, and does not open it.
  const openAt = MODULE.indexOf("function openChat(row)");
  assert.match(MODULE.slice(openAt, openAt + 600), /ARCHIVED_NOT_CONTINUED/,
    "opening an archived chat does not say why it will not");
  assert.match(MODULE.slice(openAt, openAt + 2000), /conv\.archived === true/,
    "a chat archived on the PC since the list was read can still be opened");
});

check("ONE always-visible History door in the main strip calls the SAME open routine", () => {
  // The page's main strip is between the log and the composer, so it is drawn
  // in every layout shell. Exactly one History door lives there; the rail's
  // clock icon stays as the other door.
  const barAt = PAGE.indexOf('<div class="history-bar">');
  const composerAt = PAGE.indexOf('<div class="composer">');
  assert.ok(barAt > 0 && barAt < composerAt, "the history strip is not above the composer");
  const doorAt = PAGE.indexOf('id="hud-history-open"');
  assert.ok(doorAt > barAt && doorAt < composerAt, "the one-click door is not in the main strip");
  assert.equal((PAGE.match(/id="hud-history-open"/g) || []).length, 1,
    "the page has more than one History door");
  assert.match(PAGE, /<button class="ghost history-open" id="hud-history-open"/,
    "the History door is not a page button");
  // Drawn where the LEFT RAIL IS A DRAWER - center-core, two-column-right,
  // single-stage-bento - because there the rail's own clock icon is behind
  // [Controls]. The shells whose left rail is on screen keep that icon and no
  // strip: measured 2026-10-30, the strip took the hidden-galaxy layout from
  // 30px of conversation to 24px at 1280x650 (hud.mjs). Ambient's transcript
  // toggle stays Ambient-only.
  const DRAWER_SHELLS = ["center-core", "two-column-right", "single-stage-bento"];
  const SCREENED_SHELLS = ["split-stage", "three-column", "two-column-left"];
  assert.match(PAGE, /\.history-bar\{display:none;\}/,
    "the history strip is shown by the base rule, in every shell");
  for (const shell of DRAWER_SHELLS) {
    assert.match(PAGE, new RegExp(`html\\[data-hud-shell="${shell}"\\] \\.history-bar`),
      `${shell}: its left rail is a drawer, so its History door is two clicks deep`);
  }
  for (const shell of SCREENED_SHELLS) {
    assert.doesNotMatch(PAGE, new RegExp(`html\\[data-hud-shell="${shell}"\\] \\.history-bar`),
      `${shell}: the strip is drawn although its left rail is on screen`);
  }
  assert.match(PAGE, /\.history-toggle\{display:none;\}/,
    "the Ambient transcript toggle is no longer Ambient-only");
  assert.match(PAGE, /html\[data-hud-shell="center-core"\] \.history-toggle\{display:inline-flex;\}/,
    "Ambient lost its Show-full-history toggle");
  // ONE open routine, two doors: the rail icon and the strip door both call
  // `setOpen`, and the panel is created once.
  assert.equal((MODULE.match(/function setOpen\(on\)/g) || []).length, 1,
    "the HUD has more than one open routine");
  assert.equal((MODULE.match(/panel\.id = "history-sidebar"/g) || []).length, 1,
    "the HUD creates more than one panel");
  assert.match(MODULE, /var stripBtn = doc\.getElementById\("hud-history-open"\)/,
    "the module never finds the page's one-click door");
  const clickAt = MODULE.indexOf('stripBtn.addEventListener("click"');
  assert.notEqual(clickAt, -1, "the one-click door has no click handler");
  assert.match(MODULE.slice(clickAt, clickAt + 600), /setOpen\(true\)/,
    "the one-click door does not open the panel through setOpen");
  assert.match(MODULE, /railBtn\.addEventListener\("click"[\s\S]{0,140}setOpen\(!/,
    "the rail icon no longer uses the same setOpen");
  assert.match(MODULE, /open: function \(\) \{\s*state\.opener = stripBtn \|\| railBtn;\s*setOpen\(true\);/,
    "window.hudHistory.open is not the same open routine");
  // No new inline script: the click is wired by the external module, so the
  // page's inline-script count and every CSP hash are untouched.
  assert.equal((PAGE.match(/src="hud-history\.js"/g) || []).length, 1);
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

check("the page loads the module with one external MODULE script and no inline block", () => {
  assert.match(PAGE, /<script type="module" src="hud-history\.js"><\/script>/);
  // One external file either way: no new inline block, so no CSP hash moves.
  assert.equal((PAGE.match(/src="hud-history\.js"/g) || []).length, 1);
  const before = read(REPO, "backend", "jarvis_hud.html");
  assert.equal(PAGE, before, "the page and its backend copy have drifted");
});

check("Space on the page bails out for the sidebar, a control or a menu", () => {
  // The Gemini ruling of 2026-10-27: the global push-to-talk key must never
  // fire while a sidebar row, its menu, the search box or the panel itself has
  // the key. `spaceBelongsToTheSidebar` is that guard.
  assert.match(PAGE, /function spaceBelongsToTheSidebar\(e\)/);
  assert.ok(
    PAGE.includes(
      "'#history-sidebar, input, textarea, button, [role=\"menu\"]'"
    ),
    "the push-to-talk guard does not name the sidebar's controls"
  );
  assert.match(
    PAGE,
    /spaceIsThePages\(\) && !spaceBelongsToTheSidebar\(e\)/,
    "the key handler does not call the guard"
  );
  assert.match(PAGE, /window\.hudHistory\.isOpen/, "an open sidebar does not stop Space");
  // ... and the panel really is #history-sidebar.
  assert.match(MODULE, /panel\.id = "history-sidebar"/);
});

check("a row is a listitem holding two SIBLING buttons, never one inside another", () => {
  assert.match(MODULE, /item\.setAttribute\("role", "listitem"\)/);
  assert.match(MODULE, /var button = el\("button", "hh-open"\)/);
  assert.match(MODULE, /var dots = el\("button", "hh-dots"\)/);
  const at = MODULE.indexOf("function rowItem(row)");
  const body = MODULE.slice(at, MODULE.indexOf("function paint()", at));
  assert.ok(
    body.indexOf("item.appendChild(button)") < body.indexOf("item.appendChild(dots)"),
    "the two buttons are not appended as siblings"
  );
  // A nested button would show up as one button being appended to the other.
  assert.doesNotMatch(body, /button\.appendChild\(dots\)/, "a button inside a button");
  assert.match(MODULE, /rows\.setAttribute\("role", "list"/);
  assert.match(MODULE, /headBtn\.setAttribute\("aria-expanded"/);
});

check("each age is a <time> with a datetime and the long words on hover", () => {
  assert.match(MODULE, /el\("time", "hh-age", row\.age\)/);
  assert.match(MODULE, /age\.setAttribute\("datetime", when\)/);
  assert.match(MODULE, /age\.setAttribute\("title", row\.ageLong\)/);
  assert.match(MODULE, /function isoOf\(seconds\)/);
  // A clock that is ahead of the PC is clamped, so no row says "in 3 minutes".
  assert.equal(H.ageWords(T(-600), NOW), "now");
});

check("Escape gives the keyboard back: to the ... , then to the rail icon", () => {
  assert.match(MODULE, /function closeMenu\(focusBack\)/);
  assert.match(MODULE, /if \(focusBack && anchor && anchor\.focus\) anchor\.focus\(\)/);
  assert.match(MODULE, /if \(state\.menu\) closeMenu\(true\);\s*\n\s*else setOpen\(false\)/);
  assert.match(MODULE, /doc\.addEventListener\("keydown"[\s\S]{0,220}closeMenu\(true\)/);
  assert.match(MODULE, /railBtn\.focus\(\)/);
  assert.match(MODULE, /var railBtn = el\("button", "rail-toolbar-btn"\)/);
});

check("'Show N more' moves focus to the first chat it revealed", () => {
  const at = MODULE.indexOf("var shownBefore = section.rows.length;");
  assert.notEqual(at, -1, "the panel does not count what it has shown");
  const body = MODULE.slice(at, MODULE.indexOf("wrap.appendChild(more)", at));
  assert.ok(body.indexOf("paint()") < body.indexOf("target.focus()"), "focus before the repaint");
  assert.match(body, /items\[shownBefore\]/, "focus does not land on the first NEW row");
  // ... and the control itself is not a child of `role="list"`, which may hold
  // only listitems: a button in it is invalid and reads out as one of the chats.
  assert.doesNotMatch(MODULE, /rows\.appendChild\(more\)/, "a button inside the list");
  assert.match(MODULE, /wrap\.appendChild\(more\)/, "the control is not beside the list");
});

check("collapsing a section keeps the keyboard on its own header", () => {
  const at = MODULE.indexOf('headBtn.addEventListener("click"');
  assert.notEqual(at, -1, "the section header has no click handler");
  const body = MODULE.slice(at, MODULE.indexOf("wrap.appendChild(headBtn)", at));
  const paintAt = body.indexOf("paint()");
  const focusAt = body.indexOf("again.focus()");
  assert.ok(paintAt !== -1, "the header no longer repaints the list");
  assert.ok(focusAt > paintAt, "the repaint drops the keyboard at the top of the page");
  assert.match(
    body,
    /\.hh-sec\[data-key="' \+ section\.key \+ '"\] \.hh-head/,
    "focus does not go back to the SAME section's header"
  );
});

check("the Pinned group is ordered by pinned_at, then updated", () => {
  const at = NOW - 1000;
  const pinned = [
    row("old-pin", "Old pin", 10, { pinned: true, pinned_at: 100 }),
    row("new-pin", "New pin", 500, { pinned: true, pinned_at: 300 }),
    row("same-pin", "Same moment", 900, { pinned: true, pinned_at: 300 }),
  ];
  const got = H.buildSections(pinned, [], { now: NOW, cap: 5 });
  // Two pins in the same second: the newer CHAT first, which is the second
  // half of `pinned_at DESC, updated_at DESC`.
  assert.deepEqual(got[0].rows.map((r) => r.id), ["new-pin", "same-pin", "old-pin"]);
  // The sort button does not reorder the Pinned group: a pin's meaning is its
  // moment, not the chat's name.
  const named = H.buildSections(pinned, [], { now: NOW, cap: 5, sort: "name" });
  assert.deepEqual(named[0].rows.map((r) => r.id), ["new-pin", "same-pin", "old-pin"]);
  assert.equal(H.rowOf(pinned[0], at, "").pinned_at, 100, "pinned_at is not read from the row");
});

check("the page's half is hudHistoryHost, with the three functions the panel calls", () => {
  assert.match(PAGE, /window\.hudHistoryHost = \{/);
  assert.match(PAGE, /current: function \(\) \{\s*return S\.conversationId;/);
  assert.match(PAGE, /open: function \(conv\) \{/);
  assert.match(PAGE, /newChat: function \(\) \{/);
  assert.match(PAGE, /continuable === false/,
    "a support/chatbot record must not be continued in this window");
});

check("an open section's chevron points DOWN, and a collapsed one points RIGHT", () => {
  // The caret is one right-pointing chevron in the page's own glyph set
  // (`chevron: "M9 6l6 6-6 6"` in src/hud-history.js), so a CSS rotation is the
  // only thing that decides which way it reads. Rotated 90 it points DOWN - an
  // open section; no rotation it points RIGHT - a collapsed one. The rule used
  // to be keyed on data-open="0" with rotate(-90deg), which left an OPEN
  // section showing an unrotated right-pointing caret beside its own rows, i.e.
  // reading as collapsed (seen in the render check, 2026-10-27).
  assert.match(PAGE, /\.hh-sec\[data-open="1"\] \.hh-head \.glyph\.hh-caret\{transform:rotate\(90deg\);\}/,
    "an open section's chevron is not rotated down");
  assert.doesNotMatch(PAGE, /\.hh-sec\[data-open="0"\] \.hh-head \.glyph\.hh-caret\{/,
    "a rule still rotates the caret for a CLOSED section - an open one would read as collapsed");
  // The caret really is the page's right-pointing chevron, not a re-drawn one.
  assert.match(MODULE, /chevron: "M9 6l6 6-6 6"/);
  assert.match(MODULE, /icon\("chevron", "hh-caret"\)/);
});

check("all three vendored copies of the page are byte-identical", () => {
  const a = read(SRC, "jarvis_hud.html");
  const b = read(REPO, "backend", "jarvis_hud.html");
  const c = read(REPO, "jarvis-backend", "jarvis_hud.html");
  assert.equal(a, b);
  assert.equal(a, c);
});

check("the module and the table it imports are byte-identical in the three places they ship", () => {
  assert.equal(read(REPO, "backend", "static", "hud-history.js"), MODULE);
  assert.equal(read(REPO, "jarvis-backend", "hud-history.js"), MODULE);
  assert.equal(read(REPO, "backend", "static", "history-actions.js"), ACTIONS);
  assert.equal(read(REPO, "jarvis-backend", "history-actions.js"), ACTIONS);
});

check("the server's closed whitelist names both files the page and its module load", () => {
  const base = read(REPO, "jarvis-backend", "jarvis_hud.py");
  assert.match(base, /"\/hud-history\.js": \("hud-history\.js"/);
  assert.match(base, /"\/history-actions\.js": \("history-actions\.js"/);
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

check("archiving is ONE action on the same command, one body builder for both windows", () => {
  // The HUD's archive is the same `hud_history_act` command (no new command,
  // no new permission on this window), and the body is the shared builder the
  // Brain's own archive command also calls (2026-10-29).
  assert.match(rustHistory, /pub\(crate\) fn archive_body\(id: &str, archived: bool\)/);
  assert.match(rustHistory, /"archive" => \{/);
  assert.match(rustHistory, /Ok\(\("\/api\/history\/archive", archive_body\(id, archived\)\?\)\)/);
  assert.match(rustHistory, /pub async fn brain_history_archive\(/,
    "the Brain has no archive command of its own");
  assert.match(rustLib, /brain::history::brain_history_archive,/,
    "the Brain's archive command is not registered");
  assert.match(rustBuild, /"brain_history_archive",/,
    "the Brain's archive command has no permission in build.rs");
  const brainSet = surfaces.slice(surfaces.indexOf('identifier = "brain-history"'));
  assert.match(brainSet.slice(0, 1600), /"allow-brain-history-archive"/,
    "the Brain's archive permission is not in the brain-history set");
  assert.match(surfaces, /archive or bring back ONE chat/i,
    "the HUD's History set does not describe the archive action");
  // The archived list is a READ on the same allow-list entry (`archived=1`),
  // and the lock redacts it like every other History read (the path is split
  // at '?', so the flag cannot walk around the redaction).
  assert.match(rustHistory, /"archived" if archived\.is_none\(\) => \{/);
  assert.match(rustHistory, /if archived == Some\(true\) \{\s*path\.push_str\(&format!\("\{sep\}archived=1"\)\)/);
  const lockAt = rustLock.indexOf("pub fn redact_hud_read");
  assert.match(rustLock.slice(lockAt, lockAt + 900), /let route = path\.split\('\?'\)\.next\(\)/,
    "the lock no longer splits a read's query off before matching it");
});

check("the HUD's static whitelist, the patcher and the base all carry both files", () => {
  const base = read(REPO, "jarvis-backend", "jarvis_hud.py");
  const ps1 = read(REPO, "scripts", "apply-patches.ps1");
  const where = read(REPO, "backend", "_where.py");
  for (const name of ["hud-history.js", "history-actions.js"]) {
    assert.ok(base.includes("/" + name), name + " is not in the whitelist");
    assert.ok(ps1.includes("'static/" + name + "'"), name + " is not shipped by the patcher");
    assert.ok(where.includes('"static/' + name + '"'), name + " is not in SHIPPED");
  }
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
