/**
 * Chat tags and sections in History, on the desktop (docs/CHAT-TAGS-DESIGN.md,
 * the frozen contract in section 10; JARVIS-API.md section 99; src/history-tags.js,
 * brain.js "Chat tags and sections", src-tauri/src/brain/history.rs).
 *
 * Two halves, like history.mjs:
 *  1. PURE checks - run with plain node, no browser: the shared words, the
 *     palette and icon list held to tests/fixtures/history-cases.json (written
 *     by tools/gen_history_cases.py), reading the PC's answers, grouping into
 *     sections, the open/closed flags, the older-chat route fields, and
 *     CONTROL checks that read the Rust, the permission files and the CSS.
 *  2. BROWSER checks - the Brain window on the uikit mock. They need
 *     Playwright AND its Chromium; when either is missing they are SKIPPED
 *     (said out loud), not passed. They were NOT run when this file was
 *     written (the container cannot download Chromium), so they need a run on
 *     a machine that can before they are trusted.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as T from "../src/history-tags.js";
import { readHistory, readSearch } from "../src/history-view.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const CASES = JSON.parse(read("tests/fixtures/history-cases.json"));

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/** A storage that remembers strings, like localStorage. */
const memory = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), all: m };
};

const REG = {
  ok: true,
  tags: [
    { id: 2, name: "Learning", colour: 1, icon: "book", order: 1, count: 2 },
    { id: 1, name: "Work", colour: 0, icon: "briefcase", order: 0, count: 3 },
    { id: 3, name: "Empty", colour: 2, icon: "home", order: 2, count: 0 },
  ],
  untagged: 1,
};
const row = (id, tag, updated) => ({ id, title: id, updated, tagId: tag, kind: "chat" });

/* ── The words and the palette are the fixture's ───────────────────────── */

await check("the shared words are the fixture's, word for word", () => {
  const w = CASES.words;
  assert.equal(T.UNTAGGED, w.tag_untagged);
  assert.equal(T.ALL, w.tag_all);
  assert.equal(T.TAGS_TITLE, w.tag_editor_title);
  assert.equal(T.ADD_TAG, w.tag_add);
  assert.equal(T.RENAME, w.tag_rename);
  assert.equal(T.DELETE_TAG, w.tag_delete);
  assert.equal(T.MOVE_TO, w.tag_move_to);
  assert.equal(T.NO_TAG, w.tag_none);
  assert.equal(T.bannerText("Home"), w.tag_banner.replace("{name}", "Home"));
  assert.equal(T.filedWords("Home"), w.tag_filed.replace("{name}", "Home"));
  assert.equal(T.UNFILED_WORDS, w.tag_unfiled);
  assert.equal(T.MOVE_PLACEHOLDER, w.tag_move_placeholder);
  assert.equal(T.fileUnderWords("Home"), w.tag_file_under.replace("{name}", "Home"));
  assert.deepEqual({ ...T.TAG_ERRORS }, w.tag_errors);
  assert.deepEqual(Object.keys(T.TAG_ERRORS), CASES.tag_error_codes);
});

await check("section headers, the screen-reader form and the delete question match the cases", () => {
  for (const c of CASES.tag_section_cases) {
    assert.equal(T.headerText(c.name, c.count), c.header);
    assert.equal(T.sectionSpeech(c.name, c.count, c.expanded), c.sr);
    // The desktop's label leaves the state to aria-expanded (no double announcement).
    assert.equal(T.sectionLabel(c.name, c.count), c.label);
    assert.ok(!/collapsed|expanded/.test(T.sectionLabel(c.name, c.count)));
  }
  for (const c of CASES.tag_delete_cases) assert.equal(T.deleteConfirm(c.name, c.count), c.expect);
});

await check("the limits, colours, icons and starters are the contract's", () => {
  assert.equal(T.MAX_TAGS, CASES.tag_limits.max_tags);
  assert.equal(T.NAME_MAX, CASES.tag_limits.name_max);
  assert.equal(T.COLOURS.length, CASES.tag_limits.colours);
  assert.deepEqual(T.COLOURS.map((c) => ({ ...c })), CASES.tag_palette);
  assert.deepEqual([...T.ICONS], CASES.tag_icons);
  assert.deepEqual(T.STARTERS.map((t) => ({ ...t })),
    CASES.tag_starters.map(({ order, ...rest }) => rest));
});

await check("theme.css carries the palette: light ink in Daylight, dark ink elsewhere, with the tints", () => {
  const css = read("src/theme.css");
  const rootAt = css.indexOf(":root {");
  const paperAt = css.indexOf('[data-theme="paper"] {');
  assert.ok(rootAt >= 0 && paperAt > rootAt);
  const dark = css.slice(rootAt, css.indexOf("\n}\n", rootAt));
  const light = css.slice(paperAt, css.indexOf("\n}\n", paperAt));
  for (const c of CASES.tag_palette) {
    assert.match(dark, new RegExp(`--tag-${c.slot}: ${c.dark};`), `dark ${c.slot}`);
    assert.match(light, new RegExp(`--tag-${c.slot}: ${c.light};`), `light ${c.slot}`);
  }
  assert.match(dark, new RegExp(`--tag-tint: ${Math.round(CASES.tag_tint.dark * 100)}%;`));
  assert.match(light, new RegExp(`--tag-tint: ${Math.round(CASES.tag_tint.light * 100)}%;`));
});

await check("the ink meets 4.5:1 on its own tinted header, in both variants", () => {
  const lum = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const mix = (ink, base, a) => [1, 3, 5].map((i) =>
    Math.round(parseInt(ink.slice(i, i + 2), 16) * a + parseInt(base.slice(i, i + 2), 16) * (1 - a)));
  const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  const hex = (rgb) => `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  // The two surfaces the contract names: near-black (Reactor), white (Daylight).
  for (const c of CASES.tag_palette) {
    const onDark = hex(mix(c.dark, "#0a1119", CASES.tag_tint.dark));
    const onLight = hex(mix(c.light, "#ffffff", CASES.tag_tint.light));
    assert.ok(ratio(lum(c.dark), lum(onDark)) >= 4.5, `dark ${c.name}`);
    assert.ok(ratio(lum(c.light), lum(onLight)) >= 4.5, `light ${c.name}`);
  }
});

await check("every icon has a drawing, and each draws as an inline svg with no emoji", () => {
  const made = [];
  const doc = { createElementNS: (ns, tag) => {
    const n = { ns, tag, attrs: {}, kids: [], classList: { add() {} },
      setAttribute(k, v) { this.attrs[k] = v; }, append(...k) { this.kids.push(...k); } };
    made.push(n);
    return n;
  } };
  for (const name of T.ICONS) {
    assert.ok(T.ICON_PATHS[name] && T.ICON_PATHS[name].length, name);
    const svg = T.iconNode(name, doc);
    assert.equal(svg.tag, "svg");
    assert.equal(svg.attrs["aria-hidden"], "true", "decoration only: the name says the same");
    assert.equal(svg.kids.length, T.ICON_PATHS[name].length);
    for (const d of T.ICON_PATHS[name]) assert.ok(!/[^\x20-\x7e]/.test(d), "ASCII path data");
  }
  assert.equal(T.iconNode("nope", doc).kids.length, T.ICON_PATHS.folder.length, "unknown draws the folder");
  assert.deepEqual(Object.keys(T.ICON_PATHS).sort(), [...T.ICONS].sort());
});

/* ── Reading the PC's answers ──────────────────────────────────────────── */

await check("the tag registry is read in the owner's order, and an older PC has none", () => {
  const v = T.readTags(REG);
  assert.equal(v.available, true);
  assert.deepEqual(v.tags.map((t) => t.name), ["Work", "Learning", "Empty"]);
  assert.equal(v.untagged, 1);
  assert.equal(T.tagById(v, 2).icon, "book");
  assert.equal(T.tagById(v, 99), null);
  const old = T.readTags({ available: false, why: "update" });
  assert.equal(old.available, false);
  assert.deepEqual(old.tags, []);
  assert.equal(T.tagById(old, 1), null);
  const odd = T.readTags({ tags: [{ id: 4, name: 7, colour: 99, icon: "smiley", count: -2 }, { id: "x" }, null] });
  assert.equal(odd.tags.length, 1);
  assert.deepEqual([odd.tags[0].name, odd.tags[0].colour, odd.tags[0].icon, odd.tags[0].count],
    ["", 6, "folder", 0]);
});

await check("while private lists are hidden a tag is only a count - no name, in any field", () => {
  const v = T.readTags({ ok: true, hidden: true, untagged: 2,
    tags: [{ id: 1, name: "Health worries", order: 0, count: 3 }] });
  assert.equal(v.hidden, true);
  assert.equal(v.tags[0].name, "");
  assert.equal(v.tags[0].count, 3);
});

await check("a chat row and a search hit carry tag_id as tagId, or null", () => {
  const list = readHistory({ enabled: true, conversations: [
    { id: "c-1", title: "a", tag_id: 3 }, { id: "c-2", title: "b" }, { id: "c-3", tag_id: "3" }, { id: "c-4", tag_id: 0 }] });
  assert.deepEqual(list.conversations.map((c) => c.tagId), [3, null, null, null]);
  const found = readSearch({ query_ok: true, conversations: [
    { id: "c-1", title: "a", tag_id: 2, snippet: { parts: [] } }] });
  assert.equal(found.conversations[0].tagId, 2);
});

/* ── Sections ──────────────────────────────────────────────────────────── */

await check("chats group by tag in the tags' order, newest first, Untagged last", () => {
  const v = T.readTags(REG);
  const rows = [row("a", 2, 90), row("b", 1, 80), row("c", null, 70), row("d", 1, 60), row("e", 9, 50)];
  const sec = T.groupRows(rows, v);
  assert.deepEqual(sec.map((s) => s.key), ["1", "2", "none"], "Empty (no chats, no count) is left out");
  assert.deepEqual(sec[0].rows.map((r) => r.id), ["b", "d"], "list order (newest first) is kept");
  assert.deepEqual(sec[2].rows.map((r) => r.id), ["c", "e"], "a chat whose tag vanished is untagged");
  assert.equal(sec[0].count, 3, "the PC's count when nothing narrows the list");
  assert.equal(sec[2].count, 2);
  const narrowed = T.groupRows(rows, v, { exact: false });
  assert.deepEqual(narrowed.map((s) => s.count), [2, 1, 2], "a filter counts what is shown");
});

await check("a tag whose chats are all on older pages still shows, with its count", () => {
  const v = T.readTags(REG);
  const sec = T.groupRows([row("c", null, 70)], v);
  const learning = sec.find((s) => s.key === "2");
  assert.equal(learning.rows.length, 0);
  assert.equal(learning.count, 2);
});

await check("no tags at all: no sections, the list is flat", () => {
  const sec = T.groupRows([row("a", null, 1)], T.readTags({ tags: [], untagged: 1 }));
  assert.deepEqual(sec, []);
});

await check("the fixture's worked grouping cases give the same sections in both apps", () => {
  assert.ok(CASES.tag_group_cases.length >= 6);
  for (const c of CASES.tag_group_cases) {
    const view = T.readTags({ ok: true, untagged: c.untagged,
      tags: c.tags.map((t, i) => ({ id: t.id, name: t.name, colour: 0, icon: "folder", order: i, count: t.count })) });
    const rows = c.rows.map((r) => ({ id: r.id, tagId: r.tag, updated: r.updated }));
    const sections = T.groupRows(rows, view, { exact: c.exact });
    const got = { flat: sections.length === 0 && c.tags.length === 0,
      sections: sections.map((s) => ({ key: s.key, count: s.count, rows: s.rows.map((r) => r.id) })) };
    assert.deepEqual(got, c.expect, c.name);
  }
});

await check("a tag name is judged in code points, NFC, with something visible (the fixture's cases)", () => {
  for (const c of CASES.tag_name_cases) {
    const got = T.validTagName(c.name);
    assert.equal(got !== null, c.valid, JSON.stringify(c.name));
  }
  const emoji24 = "\u{1F600}".repeat(24);
  assert.equal(T.codePointLength(emoji24), 24);
  assert.equal(emoji24.length, 48, "24 code points are 48 UTF-16 units");
  assert.equal(T.clipTagName("\u{1F600}".repeat(30)), emoji24, "cut at 24 code points");
  const cut = T.clipTagName("a".repeat(23) + "\u{1F600}\u{1F600}");
  assert.equal(T.codePointLength(cut), 24);
  assert.ok(!/[\ud800-\udbff]$/.test(cut), "never cut inside a surrogate pair");
  assert.equal(T.validTagName("Cafe\u0301"), "Caf\u00e9", "NFC");
});

/* ── What this device keeps ─────────────────────────────────────────────── */

await check("only open/closed flags are kept, by tag id, and nothing else", () => {
  const s = memory();
  assert.deepEqual(T.readOpenFlags(s), {});
  T.saveOpenFlag("1", false, s);
  T.saveOpenFlag("none", true, s);
  T.saveOpenFlag("Work", false, s);             // a name is not a key
  T.saveOpenFlag("1; drop", false, s);
  assert.deepEqual(T.readOpenFlags(s), { 1: false, none: true });
  assert.equal(T.isOpen(T.readOpenFlags(s), "1"), false);
  assert.equal(T.isOpen(T.readOpenFlags(s), "2"), true, "open unless closed");
  const stored = [...s.all.values()].join("");
  assert.ok(!/Work|Learning/.test(stored));
  s.setItem(T.SECTIONS_KEY, JSON.stringify({ 1: "no", Work: true, 2: false, 3: 1 }));
  assert.deepEqual(T.readOpenFlags(s), { 2: false }, "junk is dropped");
  s.setItem(T.SECTIONS_KEY, "not json");
  assert.deepEqual(T.readOpenFlags(s), {});
  const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.deepEqual(T.readOpenFlags(broken), {});
  assert.doesNotThrow(() => T.saveOpenFlag("1", false, broken));
});

/* ── "Label my chat about the boiler as Home" ──────────────────────────── */

await check("the older-chat route fields are read as a tag id and search words, or not at all", () => {
  assert.deepEqual(T.readFilePlace({ place: "history", file_under: "3", history_q: "  the   boiler " }),
    { tagId: 3, q: "the boiler" });
  assert.deepEqual(T.readFilePlace({ file_under: 4, history_q: "boiler" }), { tagId: 4, q: "boiler" });
  for (const bad of [null, {}, { file_under: "3" }, { history_q: "boiler" },
    { file_under: "x", history_q: "b" }, { file_under: "0", history_q: "b" },
    { file_under: "3", history_q: "   " }, { file_under: "1234567", history_q: "b" }]) {
    assert.equal(T.readFilePlace(bad), null, JSON.stringify(bad));
  }
  assert.equal(T.readFilePlace({ file_under: "3", history_q: "x".repeat(300) }).q.length, 100);
});

await check("the error words: a classified code gets its sentence; bad_request and unknown codes the PC's own", () => {
  assert.equal(T.errorWords({ ok: false, error: "name_taken" }), CASES.words.tag_errors.name_taken);
  assert.equal(T.errorWords({ ok: false, error: "weird", message: "Try later." }), "Try later.");
  assert.equal(T.errorWords({ ok: false, error: "bad_request", message: "Chat history is off. Tags are not changed." }),
    "Chat history is off. Tags are not changed.");
  assert.equal(T.errorWords({ ok: false, error: "bad_request" }), CASES.words.tag_errors.bad_request);
  // One rule for tags and fork: the PC's message wins when it is not empty.
  assert.equal(T.errorWords({ ok: false, error: "name_taken", message: "The PC's own words." }), "The PC's own words.");
  assert.equal(T.errorWords({ ok: false, error: "name_taken", message: "  " }), CASES.words.tag_errors.name_taken);
  assert.equal(T.errorWords(null), CASES.words.tag_error_fallback);
  for (const c of CASES.tag_error_cases) {
    assert.equal(T.errorWords(c.answer), c.expect, JSON.stringify(c.answer));
  }
});

/* ── CONTROL: the Rust, the permissions and the page hold to the rules ─── */

await check("CONTROL: the three tag commands are registered and only the History set holds them", () => {
  const cmds = ["brain_history_tags", "brain_history_tags_edit", "brain_history_tag"];
  const toml = read("src-tauri/permissions/surfaces.toml");
  const sets = toml.split("[[set]]").slice(1);
  const build = read("src-tauri/build.rs");
  const lib = read("src-tauri/src/lib.rs");
  for (const cmd of cmds) {
    const perm = `allow-${cmd.replace(/_/g, "-")}`;
    const holders = sets.filter((s) => s.includes(`"${perm}"`))
      .map((s) => s.match(/identifier = "([^"]+)"/)[1]);
    assert.deepEqual(holders, ["brain-history"], `${perm}: ${holders}`);
    assert.match(build, new RegExp(`"${cmd}"`), `${cmd} missing from build.rs`);
    assert.match(lib, new RegExp(`brain::history::${cmd},`), `${cmd} missing from lib.rs`);
    assert.match(read(`src-tauri/permissions/autogenerated/${cmd}.toml`), new RegExp(`allow-${cmd.replace(/_/g, "-")}`));
  }
  for (const c of ["faces", "floating", "hud", "onboarding", "quickbar", "settings", "widget"]) {
    const json = read(`src-tauri/capabilities/${c}.json`);
    assert.ok(!json.includes("brain_history_tag") && !json.includes("brain-history\""), `${c} holds History`);
  }
});

await check("CONTROL: every tag command asks the lock; the two writes are held on a stale link and post nothing before it", () => {
  const rust = read("src-tauri/src/brain/history.rs");
  const body = (name) => {
    const at = rust.indexOf(`pub async fn ${name}(`);
    assert.ok(at > 0, name);
    return rust.slice(at, rust.indexOf("\n}\n", at));
  };
  for (const name of ["brain_history_tags", "brain_history_tags_edit", "brain_history_tag"]) {
    assert.match(body(name), /crate::lock::private_hidden\(&app\)/, `${name} ignores the lock`);
  }
  for (const name of ["brain_history_tags_edit", "brain_history_tag"]) {
    const b = body(name);
    assert.ok(b.indexOf("private_hidden") < b.indexOf("post("), `${name} posts while hidden`);
    assert.ok(b.indexOf("require_link_live") > 0 && b.indexOf("require_link_live") < b.indexOf("post("),
      `${name} posts before rule 4`);
  }
  assert.ok(!/println!|eprintln!|log::|tracing::/.test(rust.slice(rust.indexOf("// Chat tags"))), "nothing logged");
  assert.ok(!/approv|card/i.test(body("brain_history_tag").replace(/\/\/.*$/gm, "")), "no card on filing");
});

await check("CONTROL: the route-key whitelist lets file_under and history_q through", () => {
  const rust = read("src-tauri/src/commands.rs");
  assert.match(rust, /"history_q",/);
  assert.match(rust, /route\.get\("file_under"\)/);
  assert.match(rust, /the_route_line_carries_the_older_chat_tag_fields/);
});

await check("CONTROL: main.js leaves the two fields for the Brain, and the Brain takes them once", () => {
  const main = read("src/main.js");
  assert.match(main, /route\.open_brain === "history"/);
  assert.match(main, /left\.file_under = route\.file_under/);
  const brain = read("src/brain.js");
  assert.match(brain, /applyHistoryFilePlace\(takePlaceExtras\(\)\)/);
  assert.match(read("src/forget-range-panel.js"), /export function takePlaceExtras/);
});

await check("CONTROL: main.js drops the place key after a minute if the Brain never read it", () => {
  const main = read("src/main.js");
  assert.match(main, /now\.at === left\.at\) localStorage\.removeItem\(BRAIN_PLACE_KEY\)/);
  const panel = read("src/forget-range-panel.js");
  assert.match(panel, /if \(left\) localStorage\.removeItem\(BRAIN_PLACE_KEY\)/, "removed as soon as it is read");
});

await check("CONTROL: every tag control has a stable data-fkey, focus is given back, and a used menu is not repainted", () => {
  const brain = read("src/brain.js");
  for (const key of ["`chip:${value}`", "`sec:${sec.key}`", "`move:${c.id}`", "`open:${c.id}`", "`file:${c.id}`",
    "`up:${t.id}`", "`down:${t.id}`", "`del:${t.id}`", "`rename:${t.id}`", "`name:${t.id}`", "`colour:${t.id}`",
    "`icon:${t.id}`", '"editor-toggle"', '"add-name"', '"add-btn"', '"banner-cancel"']) {
    assert.ok(brain.includes(`dataset.fkey = ${key}`) || brain.includes(key), `no data-fkey ${key}`);
  }
  assert.match(brain, /function giveBackTagFocus\(\)/);
  assert.match(brain, /function tagControlBusy\(\)/);
  assert.match(brain, /hold = background && tagControlBusy\(\)/, "the 15-second re-read waits for a used menu");
  assert.match(brain, /if \(tagControlBusy\(\)\) chats\.paintPending = true;/);
  assert.match(brain, /document\.addEventListener\("focusout"/, "and repaints when it closes");
  assert.match(brain, /`sec:\$\{value === "none" \? "none" : value\}`/, "a moved row falls back to its new header");
});

await check("CONTROL: the File under button's label starts with its visible words; chips are 32px tall", () => {
  const brain = read("src/brain.js");
  assert.match(brain, /aria-label", `\$\{fileUnderWords\(chats\.filing\.name\)\}: \$\{named\}`/);
  assert.ok(!/maxLength = NAME_MAX/.test(brain), "the UTF-16 maxLength is gone; code points are counted");
  assert.match(read("src/brain.css"), /\.tag-chip \{[^}]*min-height: 32px/s);
  assert.match(brain, /tagView\.tags\.length && !chats\.tag/, "no tags: a flat list, no Untagged-only section");
});

await check("CONTROL: the page is keyboard-operable, reads the shared words and respects reduced motion", () => {
  const brain = read("src/brain.js");
  assert.match(brain, /head\.setAttribute\("aria-expanded"/);
  assert.match(brain, /aria-label", sectionLabel\(name, sec\.count\)/);
  assert.ok(!/sectionSpeech\(/.test(brain), "the state is said once, by aria-expanded");
  assert.match(brain, /"history-section-head"/);
  assert.match(brain, /el\("button", "history-section-head"\)/, "a section header is a button");
  const css = read("src/brain.css");
  assert.match(css, /@media \(prefers-reduced-motion: no-preference\)\s*\{\s*\.history-section-chevron/);
  assert.match(css, /\.tag-chip\[aria-pressed="true"\]::before/, "the chosen chip has a tick, not just a colour");
  assert.ok(!/[\u{1F300}-\u{1FAFF}]/u.test(read("src/history-tags.js")), "no emoji");
  const html = read("src/brain.html");
  assert.match(html, /id="history-tagbar"/);
});

await check("CONTROL: no tag name is written to this device", () => {
  const brain = read("src/brain.js");
  const from = brain.indexOf("Chat tags and sections (history-tags.js");
  const to = brain.indexOf("Above the list", from);
  const block = brain.slice(from, to);
  assert.ok(!/localStorage|sessionStorage|indexedDB/.test(block), "the tags block touches storage");
  assert.equal((block.match(/saveOpenFlag\(/g) || []).length, 1, "only the open flag is saved");
});

/* ── The Brain window (needs Playwright and its Chromium) ──────────────── */

let K = null;
let browser = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
  browser = await K.launch();
} catch (e) {
  console.log(`SKIP  browser checks: ${String(e.message).split("\n")[0]}`);
}

if (browser) {
  const { base, close } = await K.serve();
  const NOW = Math.floor(Date.now() / 1000);
  const TAGS = [
    { id: 1, name: "Work", colour: 0, icon: "briefcase", order: 0 },
    { id: 2, name: "Learning", colour: 1, icon: "book", order: 1 },
    { id: 3, name: "Personal", colour: 2, icon: "home", order: 2 },
  ];
  const chat = (id, title, ago, tag) => ({ id, title, started: NOW - ago - 30, updated: NOW - ago, turns: 2,
    device: "desktop", has_voice: false, tainted: false, ...(tag ? { tag_id: tag } : {}) });
  const CONVS = () => [
    chat("conv-0001-aaaa", "Quarterly numbers", 60, 1), chat("conv-0002-aaaa", "Spanish verbs", 120, 2),
    chat("conv-0003-aaaa", "Boiler service", 180, null), chat("conv-0004-aaaa", "Team offsite", 240, 1),
  ];
  const tab = async (history = {}, extra = {}) => {
    const page = await K.open(browser, base, "brain.html",
      { history: { conversations: CONVS(), tags: JSON.parse(JSON.stringify(TAGS)), ...history }, ...extra },
      { width: 1180, height: 900 });
    await page.locator("#tab-history").click();
    await page.waitForTimeout(350);
    return page;
  };
  const calls = (page, cmd) => page.evaluate((c) => window.__calls.filter((x) => x[0] === c).map((x) => x[1]), cmd);

  await check("browser: sections show icon-name-count headers, newest first, Untagged last", async () => {
    const page = await tab();
    const heads = await page.locator(".history-section-head").evaluateAll((els) =>
      els.map((e) => ({ text: e.innerText, label: e.getAttribute("aria-label"), expanded: e.getAttribute("aria-expanded") })));
    assert.deepEqual(heads.map((h) => h.text.trim()), ["Work (2)", "Learning (1)", "Untagged (1)"]);
    assert.deepEqual(heads.map((h) => h.label), ["Work, 2 chats", "Learning, 1 chats", "Untagged, 1 chats"]);
    assert.deepEqual(heads.map((h) => h.expanded), ["true", "true", "true"], "the state is aria-expanded's");
    const inWork = await page.locator('.history-section[data-key="1"] .row-title').allInnerTexts();
    assert.deepEqual(inWork, ["Quarterly numbers", "Team offsite"]);
    assert.equal(await page.locator('.history-section[data-key="1"] .history-section-head svg').count(), 1, "an icon");
    await page.close();
  });

  await check("browser: a header is a button that collapses and remembers only the flag", async () => {
    const page = await tab();
    const head = page.locator('.history-section[data-key="1"] .history-section-head');
    await head.focus();
    await page.keyboard.press("Enter");
    assert.equal(await head.getAttribute("aria-expanded"), "false");
    assert.equal(await head.getAttribute("aria-label"), "Work, 2 chats");
    assert.equal(await head.evaluate((n) => document.activeElement === n), true, "still focused");
    assert.equal(await page.locator('.history-section[data-key="1"] .history-section-body').isVisible(), false);
    const stored = await page.evaluate(() => localStorage.getItem("jarvis.history.sections"));
    assert.deepEqual(JSON.parse(stored), { 1: false });
    await page.close();
  });

  await check("browser: a chip filters through the PC, All clears it, Show keeps working with it", async () => {
    const page = await tab();
    await page.locator(".tag-chip", { hasText: "Learning" }).click();
    await page.waitForTimeout(250);
    assert.ok((await calls(page, "brain_history_list")).some((c) => c.tag === "2"));
    assert.deepEqual(await page.locator("#history-list .row-title").allInnerTexts(), ["Spanish verbs"]);
    assert.equal(await page.locator(".history-section").count(), 0, "one flat list under a chip");
    await page.locator(".tag-chip", { hasText: "All" }).click();
    await page.waitForTimeout(250);
    assert.equal(await page.locator(".history-section").count(), 3);
    await page.locator(".tag-chip", { hasText: "Untagged" }).click();
    await page.waitForTimeout(250);
    assert.ok((await calls(page, "brain_history_list")).some((c) => c.tag === "none"));
    await page.close();
  });

  await check("browser: Move to files one chat, with no card, and Untagged is one tap", async () => {
    const page = await tab();
    const move = page.locator('.row-item[data-id="conv-0003-aaaa"] select.history-move');
    await move.selectOption({ label: "Personal" });
    await page.waitForTimeout(300);
    assert.deepEqual((await calls(page, "brain_history_tag")).at(-1), { id: "conv-0003-aaaa", tagId: 3 });
    assert.ok(await page.locator('.history-section[data-key="3"] .row-title').first().isVisible());
    const pill = await page.locator('.row-item[data-id="conv-0003-aaaa"] .history-tagpill').innerText();
    assert.equal(pill.trim(), "Personal");
    await page.locator('.row-item[data-id="conv-0003-aaaa"] select.history-move').selectOption({ label: "No tag" });
    await page.waitForTimeout(300);
    assert.deepEqual((await calls(page, "brain_history_tag")).at(-1), { id: "conv-0003-aaaa", tagId: null });
    await page.close();
  });

  const activeKey = (page) => page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey || "");

  await check("browser: the keyboard stays on a chip after it is pressed", async () => {
    const page = await tab();
    await page.locator(".tag-chip", { hasText: "Learning" }).focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(350);
    assert.equal(await activeKey(page), "chip:2");
    await page.close();
  });

  await check("browser: after Move to, the keyboard is on the moved row (or its new header)", async () => {
    const page = await tab();
    const move = page.locator('.row-item[data-id="conv-0003-aaaa"] select.history-move');
    await move.focus();
    await move.selectOption({ label: "Personal" });
    await page.waitForTimeout(400);
    const key = await activeKey(page);
    assert.ok(key === "move:conv-0003-aaaa" || key === "sec:3", `focus was ${JSON.stringify(key)}`);
    await page.close();
  });

  await check("browser: Move up / Rename keep the keyboard, and the editor is not closed by a re-read", async () => {
    const page = await tab();
    await page.locator("#tag-editor-toggle").click();
    const down = page.locator('.tag-editor-row[data-tag="1"] button', { hasText: "Move down" });
    await down.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(350);
    assert.ok(["down:1", "up:1"].includes(await activeKey(page)), "Move down keeps the keyboard on that tag");
    await page.close();
  });

  await check("browser: a Move-to menu in use is not repainted by the 15-second re-read", async () => {
    const page = await tab();
    const move = page.locator('.row-item[data-id="conv-0003-aaaa"] select.history-move');
    await move.focus();
    await page.evaluate(() => { document.querySelector("select.history-move").dataset.mark = "same"; });
    // Painting the tab again (what the re-read ends with) must leave the menu alone.
    await page.evaluate(() => document.querySelector("#tab-history").click());
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => document.querySelector("select.history-move").dataset.mark), "same",
      "the menu was drawn afresh under the owner's hand");
    await page.locator("#history-find, #history-filter").first().focus();
    await page.waitForTimeout(200);
    await page.close();
  });

  await check("browser: with no tags at all the list is flat", async () => {
    const page = await tab({ tags: [] });
    assert.equal(await page.locator(".history-section").count(), 0);
    assert.equal(await page.locator("#history-list .row-item").count(), 4);
    await page.close();
  });

  await check("browser: the Tags editor adds, refuses a duplicate in plain words, and asks before deleting", async () => {
    const page = await tab();
    await page.locator("#tag-editor-toggle").click();
    await page.fill("#tag-add-name", "Garage");
    await page.locator("#tag-editor .tag-editor-add button").click();
    await page.waitForTimeout(300);
    assert.equal((await calls(page, "brain_history_tags_edit")).at(-1).op, "add");
    assert.ok((await page.locator(".tag-chip").allInnerTexts()).some((t) => t.includes("Garage")));
    await page.fill("#tag-add-name", "work");
    await page.locator("#tag-editor .tag-editor-add button").click();
    await page.waitForTimeout(300);
    assert.equal(await page.locator(".tag-editor-error").innerText(), CASES.words.tag_errors.name_taken);
    let asked = "";
    page.on("dialog", async (d) => { asked = d.message(); await d.accept(); });
    await page.locator('.tag-editor-row[data-tag="1"] button', { hasText: "Delete this tag" }).click();
    await page.waitForTimeout(300);
    assert.equal(asked, "Delete the tag Work? Its 2 chats become untagged.");
    assert.equal((await calls(page, "brain_history_tags_edit")).at(-1).op, "delete");
    await page.close();
  });

  await check("browser: hidden lists show no tag name anywhere", async () => {
    const page = await tab({}, { security: { hidden: true } });
    const text = await page.locator("#view-history").innerText();
    for (const name of ["Work", "Learning", "Personal"]) assert.ok(!text.includes(name), name);
    assert.equal(await page.locator("#history-tagbar").isHidden(), true);
    await page.close();
  });

  await check("browser: an older PC without tags keeps the flat list", async () => {
    const page = await tab({ tags: undefined });
    assert.equal(await page.locator(".history-section").count(), 0);
    assert.equal(await page.locator("#history-list .row-item").count(), 4);
    await page.close();
  });

  await check("browser: 'label my chat about the boiler as Home' opens History with the banner, and a tap files it", async () => {
    const page = await K.open(browser, base, "brain.html",
      { history: { conversations: CONVS(), tags: JSON.parse(JSON.stringify(TAGS)) } }, { width: 1180, height: 900 });
    await page.evaluate(() => localStorage.setItem("jarvis.brain.place",
      JSON.stringify({ place: "history", file_under: "3", history_q: "boiler", at: Date.now() })));
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForTimeout(700);
    assert.equal(await page.locator("#history-filter").inputValue(), "boiler");
    assert.equal((await page.locator(".history-file-banner").innerText()).includes("Tap the chat to file it under Personal."), true);
    assert.equal((await calls(page, "brain_history_tag")).length, 0, "nothing is filed until a tap");
    await page.locator('.row-item[data-id="conv-0003-aaaa"]').click({ position: { x: 20, y: 10 } });
    await page.waitForTimeout(400);
    assert.deepEqual((await calls(page, "brain_history_tag")).at(-1), { id: "conv-0003-aaaa", tagId: 3 });
    assert.equal(await page.locator(".history-file-banner").count(), 0, "the banner clears");
    await page.close();
  });

  await check("browser: Cancel clears the banner and files nothing", async () => {
    const page = await K.open(browser, base, "brain.html",
      { history: { conversations: CONVS(), tags: JSON.parse(JSON.stringify(TAGS)) } }, { width: 1180, height: 900 });
    await page.evaluate(() => localStorage.setItem("jarvis.brain.place",
      JSON.stringify({ place: "history", file_under: "1", history_q: "boiler", at: Date.now() })));
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForTimeout(700);
    await page.locator(".history-file-banner button", { hasText: "Cancel" }).click();
    assert.equal(await page.locator(".history-file-banner").count(), 0);
    assert.equal((await calls(page, "brain_history_tag")).length, 0);
    await page.close();
  });

  await browser.close();
  close();
}

console.log(fails.length ? `\n${fails.length} failed: ${fails.join(", ")}` : "\nchat tags hold to the contract");
process.exit(fails.length ? 1 : 0);
