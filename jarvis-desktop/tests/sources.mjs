/**
 * "Where this came from", and the quote check - feasibility I42/I132
 * (docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md detail 1;
 * docs/JARVIS-API.md section 54; src/memory-used.js, src/answer-memory.js,
 * commands.rs route_line_from_header, brain/sources.rs).
 *
 * What must hold:
 * - the notes, wiki pages, web results and files a reading tool actually
 *   returned this turn are listed under the answer, by reference only -
 *   never a note's full text, never a web page fetched to preview it;
 * - a web source shows its HOST only until the owner taps it, then opens
 *   as a real navigation, never inside the WebView;
 * - a quote Jarvis made that is not in what it read this turn is flagged,
 *   plainly, as a warning - it never changes the answer already shown;
 * - fetched once, quietly, as soon as the answer finishes (there is no
 *   cheap count the way "Used 2 memories" has one) - never on a temporary
 *   answer, and never when the PC gave no turn_id at all;
 * - hidden under Windows Hello, the same gate "Used in this answer" uses -
 *   how many there were stays, no reference does.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  hostOf,
  isOpenable,
  QUOTE_WARNING_LABEL,
  readSources,
  SOURCES_MISSING,
  sourceLine,
} from "../src/memory-used.js";
import * as K from "./uikit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The words ─────────────────────────────────────────────────────────── */

await check("the words are both apps' words, word for word", async () => {
  const kt = readFileSync(
    join(HERE, "..", "..", "jarvis-client/app/src/main/java/com/jarvis/client/net/ChatSources.kt"),
    "utf8");
  const flat = kt.replace(/"\s*\+\s*\n?\s*"/g, "");
  for (const words of [SOURCES_MISSING, QUOTE_WARNING_LABEL, "Where this came from"]) {
    assert.ok(flat.includes(words.replace(/"/g, '\\"')), `the phone does not say: ${words}`);
  }
  assert.ok(read("src-tauri/src/brain/sources.rs").replace(/\\\n\s*/g, "").includes(SOURCES_MISSING),
    "brain/sources.rs SOURCES_MISSING differs from the JS one");
});

/* ── The pure reading and rendering ───────────────────────────────────── */

await check("readSources: kinds, missing fields dropped, hidden, older PC", async () => {
  const v = readSources({ sources: [
    { kind: "note", ref: "Ideas.md", title: "Ideas" },
    { kind: "wiki", ref: "Jarvis Wiki/Recipes.md" },
    { kind: "web", url: "https://example.com/soup", title: "A soup site" },
    { kind: "file", path: "C:\\Users\\me\\notes.txt", title: "notes" },
    { kind: "spreadsheet", ref: "x" },   // an unknown kind: dropped
    { kind: "note" },                    // no ref, no url, no path: dropped
  ], unverified_quotes: ["a line that was never read", "  "] });
  assert.equal(v.available, true);
  assert.deepEqual(v.sources.map((s) => s.kind), ["note", "wiki", "web", "file"]);
  assert.deepEqual(v.quotes, ["a line that was never read"], "a blank quote was kept");
  const old = readSources({ available: false, why: "older" });
  assert.equal(old.available, false);
  assert.equal(old.why, "older");
  assert.equal(readSources(null).why, SOURCES_MISSING);
  assert.equal(readSources(null).available, false);
});

await check("sourceLine and hostOf: a web source shows its host only, never the full link", async () => {
  assert.equal(hostOf("https://example.com/very/private/path?x=1"), "example.com");
  assert.equal(hostOf("not a url at all"), "not a url at all");
  assert.equal(sourceLine({ kind: "web", url: "https://example.com/x" }), "Web: example.com");
  assert.equal(sourceLine({ kind: "note", ref: "Ideas.md", title: "Ideas" }), "Note: Ideas");
  assert.equal(sourceLine({ kind: "note", ref: "Ideas.md" }), "Note: Ideas.md");
  assert.equal(sourceLine({ kind: "wiki", ref: "Jarvis Wiki/Recipes.md" }),
    "Wiki page: Jarvis Wiki/Recipes.md");
  assert.equal(sourceLine({ kind: "file", path: "C:\\notes.txt" }), "File: C:\\notes.txt");
  assert.equal(isOpenable({ kind: "web", url: "https://example.com" }), true);
  assert.equal(isOpenable({ kind: "web", url: "javascript:alert(1)" }), false, "not an http(s) link");
  assert.equal(isOpenable({ kind: "note", ref: "x" }), false, "only a web source opens");
});

/* ── The quickbar ─────────────────────────────────────────────────────── */

const { base, close } = await K.serve();
const browser = await K.launch();
const SIZE = { width: 520, height: 640 };
const route = (r) => "\u001fjarvis-route:" + JSON.stringify(r);
const LOCAL = { lane: "qwen3:8b", where: "local", gate: "complexity" };
const TID = "0123456789abcdef0123456789abcdef";

async function quickbar(data = {}, setup = {}) {
  const page = await K.open(browser, base, "index.html", data, SIZE);
  await page.evaluate((s) => Object.assign(window, s), setup);
  return page;
}
const submit = async (page, text) => {
  await page.locator("#prompt").fill(text);
  await page.locator("#prompt").press("Enter");
  await page.waitForTimeout(250);
};

const SOME_SOURCES = { sources: [
  { kind: "note", ref: "Recipes/Soup.md", title: "Soup ideas" },
  { kind: "web", url: "https://example.com/soup-recipe", title: "Example Soup Co" },
], unverified_quotes: ["you should always add nutmeg"] };

await check("an answer that read something: the line appears once it finishes, fetched by turn_id", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, turn_id: TID }),
    "Try this soup."]] }, { __chatSources: { [TID]: SOME_SOURCES } });
  const before = await page.locator("#answer-sources").isVisible();
  await submit(page, "what should I cook?");
  const shown = await page.locator("#answer-sources").isVisible();
  const reads = await page.evaluate(() => window.__sourcesReads || []);
  await page.close();
  assert.equal(before, false, "shown before any answer at all");
  assert.equal(shown, true);
  assert.deepEqual(reads, [TID]);
});

await check("opening it lists what was read, a web source as a real link showing its host only", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, turn_id: TID }), "Try this soup."]] },
    { __chatSources: { [TID]: SOME_SOURCES } });
  await submit(page, "what should I cook?");
  await page.locator("#answer-sources-line").click();
  await page.waitForTimeout(200);
  const rows = await page.locator("#answer-sources-list .answer-used-item").allInnerTexts();
  const link = page.locator("#answer-sources-list a[data-external]");
  const href = await link.getAttribute("href");
  const linkText = await link.innerText();
  const expanded = await page.locator("#answer-sources-line").getAttribute("aria-expanded");
  await page.close();
  assert.equal(expanded, "true");
  assert.match(rows[0], /Note: Soup ideas/);
  assert.match(rows[1], /Web: example\.com/);
  assert.equal(href, "https://example.com/soup-recipe", "the full link IS there, in href");
  assert.equal(linkText, "Web: example.com", "but never shown as text - only the host");
  assert.doesNotMatch(linkText, /soup-recipe|Example Soup Co/);
});

await check("an unverified quote is flagged as a warning, never rewriting the answer", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, turn_id: TID }),
    "Nutmeg helps, apparently."]] }, { __chatSources: { [TID]: SOME_SOURCES } });
  await submit(page, "what should I cook?");
  const answerText = await page.locator("#answer").innerText();
  await page.locator("#answer-sources-line").click();
  await page.waitForTimeout(200);
  const warn = await page.locator("#answer-sources-list .answer-used-empty.warn").innerText();
  await page.close();
  assert.equal(answerText.trim(), "Nutmeg helps, apparently.", "the streamed answer was not touched");
  assert.match(warn, /you should always add nutmeg/);
  assert.match(warn, new RegExp(QUOTE_WARNING_LABEL));
});

await check("nothing read, or no turn_id at all: no line, and no fetch is even tried", async () => {
  const none = await quickbar({ chatReplies: [[route({ ...LOCAL, turn_id: TID }), "x"]] },
    { __chatSources: { [TID]: { sources: [], unverified_quotes: [] } } });
  await submit(none, "q");
  const shownNone = await none.locator("#answer-sources").isVisible();
  await none.close();
  assert.equal(shownNone, false, "an empty answer still shows nothing");

  const noId = await quickbar({ chatReplies: [[route(LOCAL), "x"]] },
    { __chatSources: { default: SOME_SOURCES } });
  await submit(noId, "q");
  const shownNoId = await noId.locator("#answer-sources").isVisible();
  const reads = await noId.evaluate(() => window.__sourcesReads || []);
  await noId.close();
  assert.equal(shownNoId, false, "no turn_id: nothing to fetch by");
  assert.deepEqual(reads, [], "no fetch was even attempted");
});

await check("a temporary answer never fetches, even with a real turn_id", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, turn_id: TID, temporary: true,
    injected_facts: 0 }), "Sure."]] }, { __temporaryOk: true, __chatSources: { [TID]: SOME_SOURCES } });
  await page.locator("#temporary").click();
  await page.waitForTimeout(200);
  await submit(page, "what should I cook?");
  const shown = await page.locator("#answer-sources").isVisible();
  const reads = await page.evaluate(() => window.__sourcesReads || []);
  await page.close();
  assert.equal(shown, false);
  assert.deepEqual(reads, []);
});

await check("hidden under Windows Hello: how many, never a reference", async () => {
  const page = await quickbar({ security: { hidden: true },
    chatReplies: [[route({ ...LOCAL, turn_id: TID }), "x"]] }, { __chatSources: { [TID]: SOME_SOURCES } });
  await submit(page, "q");
  await page.locator("#answer-sources-line").click();
  await page.waitForTimeout(200);
  const list = await page.locator("#answer-sources-list").innerText();
  await page.close();
  assert.match(list, /These facts are hidden until Windows Hello confirms it is you/);
  assert.doesNotMatch(list, /Soup|example\.com/);
});

await check("an older PC's list says so plainly", async () => {
  const page = await quickbar({ chatReplies: [[route({ ...LOCAL, turn_id: TID }), "x"]] },
    { __sourcesMissingRoute: true });
  await submit(page, "q");
  await page.locator("#answer-sources-line").click();
  await page.waitForTimeout(200);
  const list = await page.locator("#answer-sources-list").innerText();
  await page.close();
  assert.ok(list.includes(SOURCES_MISSING), list);
});

await browser.close();
await close();

/* ── CONTROL: the Rust ───────────────────────────────────────────────── */

await check("CONTROL: turn_id rides in the route line, chat_sources hides under Hello, capabilities wired", async () => {
  const rust = read("src-tauri/src/commands.rs").replace(/\s+/g, " ");
  assert.match(rust, /out\.insert\( *"turn_id"\.to_string\(\), *serde_json::Value::String\(id\.to_string\(\)\), *\)/);
  const src = read("src-tauri/src/brain/sources.rs");
  assert.match(src, /if crate::lock::private_hidden\(&app\) \{\s*redact_sources\(answer\)/);
  const caps = read("src-tauri/capabilities/quickbar.json");
  assert.ok(caps.includes('"chat-sources"'));
  const sets = read("src-tauri/permissions/surfaces.toml");
  const set = sets.slice(sets.indexOf('identifier = "chat-sources"'));
  assert.match(set.slice(0, 400), /"allow-chat-sources",?\s*\]/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join(", ")}`);
  process.exit(1);
}
console.log("\n\"Where this came from\": read by reference, a web link shows its host only, a bad quote just warns");
