/**
 * Topic controls on the Brain's Memory tab (the owner's request of 2026-09-30;
 * docs/TOPIC-CONTROLS-DESIGN.md, "Slice contract (frozen)" C1-C10; JARVIS-API.md
 * section 107; src/topics.js, brain.js "Topics", src-tauri/src/brain/topics.rs).
 *
 * The first half needs no browser and runs anywhere (CI's backend job too):
 * - the shared words, the four modes, the errors and the palette, word for
 *   word, against tests/fixtures/topics-cases.json (written by
 *   tools/gen_topics_cases.py, which the phone's TopicsContractTest.kt reads);
 * - the worked cases: mode_cases, name_cases, words_cases, screen_reader_cases,
 *   hidden_row_cases, preview_cases;
 * - the reading of what the PC sends, and the small pure rules (reorder, the
 *   delete destinations, the "more open" warning, the review groups);
 * - CONTROL: the Rust / JS / permissions wiring agrees, Brain window only, and
 *   the section draws owner words as text only and stores nothing.
 *
 * The second half needs Playwright (see tests/README.md) and is unexecuted where
 * it is unavailable: the rows and their tags, the four-choice picker with its
 * preview, the card-waiting flow and Undo, "Check these", "Show them", add /
 * rename / colour / reorder / private / keywords / delete, the model switch,
 * hidden lists, a stale link, and the lines elsewhere in the Brain and the chat.
 */
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");
const FIX = JSON.parse(readFileSync(join(HERE, "fixtures", "topics-cases.json"), "utf8"));
const W = FIX.words;

const T = await import("../src/topics.js");

const fails = [];
const check = async (name, fn) => {
  try { await fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

/* ── The shared words ─────────────────────────────────────────────────── */

await check("the shared words, modes, errors and card endings are word for word what the contract says", async () => {
  assert.deepEqual({ ...T.WORDS }, W);
  assert.deepEqual(T.MODES.map((m) => ({ ...m })), FIX.modes);
  assert.deepEqual(T.MODES.map((m) => m.id), ["both", "use_only", "learn_only", "off"]);
  assert.deepEqual({ ...T.ERRORS }, FIX.errors);
  assert.deepEqual({ ...T.LAST_WORDS }, FIX.last_words);
  assert.equal(T.LIMITS.maxTopics, FIX.limits.max_topics);
  assert.equal(T.LIMITS.nameMax, FIX.limits.name_max);
  assert.equal(T.LIMITS.wordsMax, FIX.limits.words_max);
  assert.equal(T.LIMITS.batch, FIX.limits.batch);
  assert.equal(T.LIMITS.colours, FIX.limits.colours);
  assert.equal(T.LIMITS.unsortedId, FIX.limits.unsorted_id);
  assert.equal(T.TOPICS_PLACE, "topics");
});

await check("the palette is the chat tags' eight, and the icons are theirs plus heart, coin and people", async () => {
  assert.deepEqual(T.COLOURS.map((c) => ({ ...c })), FIX.palette);
  assert.deepEqual([...T.ICONS], FIX.icons);
  const drawn = new Set([...Object.keys(T.EXTRA_ICON_PATHS)]);
  assert.deepEqual([...drawn].sort(), ["coin", "heart", "people"]);
  for (const name of T.ICONS) {
    const svg = fakeSvg(name);
    assert.ok(svg.paths.length >= 1, name);
    for (const d of svg.paths) assert.ok(!/[^\x20-\x7e]/.test(d), `${name}: ASCII path data`);
  }
  // Every starter and the Unsorted row wear a shared colour and a shared icon.
  for (const s of FIX.starters) {
    assert.ok(s.colour >= 0 && s.colour < 8 && T.ICONS.includes(s.icon), s.name);
  }
  assert.ok(T.ICONS.includes(FIX.unsorted.icon));
});

/** topicIconNode against a minimal document. */
function fakeSvg(name) {
  const paths = [];
  const doc = {
    createElementNS: (_ns, tag) => {
      const node = { tag, attrs: {}, kids: [], classList: { add() {} },
        setAttribute(k, v) { this.attrs[k] = v; }, append(k) { this.kids.push(k); } };
      if (tag === "path") paths.push(node);
      return node;
    },
  };
  T.topicIconNode(name, doc);
  return { paths: paths.map((p) => p.attrs.d) };
}

await check("an unknown icon draws the folder", async () => {
  assert.deepEqual(fakeSvg("nope").paths, fakeSvg("folder").paths);
});

/* ── The worked cases ─────────────────────────────────────────────────── */

await check("mode_cases: which changes open something up, and which ask (label only - the PC decides)", async () => {
  for (const c of FIX.mode_cases) {
    assert.equal(T.loosens(c.old, c.new), c.loosens, JSON.stringify(c));
    assert.equal(T.needsCardLabel(c.old, c.new, c.private), c.needs_card, JSON.stringify(c));
  }
});

await check("name_cases: the same name rule before sending", async () => {
  for (const c of FIX.name_cases) assert.equal(T.cleanName(c.raw), c.clean, JSON.stringify(c.raw));
  assert.equal(T.cleanName("a​b"), null);
  assert.equal(T.cleanName(7), null);
  assert.equal(T.cleanName("\u{1F600}".repeat(24)), "\u{1F600}".repeat(24), "characters, not bytes");
});

await check("words_cases: keywords are cleaned like the PC cleans them", async () => {
  for (const c of FIX.words_cases) assert.deepEqual(T.cleanWords(c.raw), c.clean, JSON.stringify(c.raw));
  assert.equal(T.cleanWords(Array.from({ length: 21 }, (_, i) => `word${i}`)), null);
  assert.deepEqual(T.cleanWords("Boiler, BOILER"), ["boiler"]);
});

await check("screen_reader_cases and hidden_row_cases", async () => {
  for (const c of FIX.screen_reader_cases) assert.equal(T.screenReader(c.name, c.facts, c.mode), c.expect);
  for (const c of FIX.hidden_row_cases) assert.equal(T.hiddenRow(c.index, c.facts, c.mode), c.expect);
  assert.equal(T.hiddenName(3), "Topic 3");
});

await check("count_cases: one fact / one thing reads singular, never '1 facts'", async () => {
  for (const c of FIX.count_cases) {
    const got = c.line === "kept_hidden" ? T.keptHiddenLine(c.n)
      : c.line === "skipped" ? T.rowTags({ private: false, mode: "both", facts: 9, skippedWeek: c.n })[0].text
      : T.sortedGuessLine({ unchecked: c.n, facts: c.total });
    assert.equal(got, c.expect, JSON.stringify(c));
  }
  assert.equal(T.rowTags({ private: false, mode: "off", facts: 1, skippedWeek: 0 })[0].text, "1 fact kept, hidden");
});

await check("preview_cases: the sentence is built from the numbers when the PC's is blanked", async () => {
  for (const c of FIX.preview_cases) {
    const got = T.previewLines({ ok: true, affected: c.n, pinned: 0, stops_learning: false, line: "", card_line: "" }, c.name);
    assert.equal(got.line, c.expect);
  }
  const p = { ok: true, affected: 0, pinned: 2, stops_learning: true, line: "", card_line: "" };
  assert.equal(T.previewLines(p, "Topic 1").line,
    "Nothing Jarvis knows about Topic 1 will change in answers. Jarvis will stop saving new things about Topic 1. " +
    "2 pinned facts about Topic 1 will pause until you switch it back on.");
  // The PC's own sentence wins when it sent one, and the card line is its own line.
  const pc = T.previewLines({ ok: true, line: "The PC's words.", card_line: W.private_asks }, "Work");
  assert.equal(pc.line, "The PC's words.");
  assert.equal(pc.cardLine, W.private_asks);
  assert.equal(T.previewLines({ ok: true, line: "x", card_line: "" }, "Work").cardLine, "");
});

await check("card_cases: the card's words are the PC's (the app shows them, never builds them)", async () => {
  const src = read("src/topics.js") + read("src/brain.js");
  for (const c of FIX.card_cases) {
    assert.ok(!src.includes(c.text.split("\n")[0]), "the card sentence is not written into the app");
  }
});

/* ── Reading what the PC sends ────────────────────────────────────────── */

const topic = (o = {}) => ({ id: 2, name: "Work", colour: 0, icon: "briefcase", mode: "both", private: false,
  words: [], ord: 1, system: false, created: 1, facts: 41, unchecked: 3, hidden: false, skipped_week: 0, ...o });
const UNSORTED = topic({ id: 1, name: "Unsorted", colour: 6, icon: "flag", system: true, facts: 9, unchecked: 0 });
const viewBody = (over = {}) => ({ ok: true, topics: [UNSORTED, topic(), topic({ id: 3, name: "Health", private: true, mode: "learn_only", facts: 5, unchecked: 0 })],
  unchecked: 3, facts: 55, sorted: 46, model_help: false, backfill: { done: true, remaining: 0 },
  limits: { max_topics: 16 }, modes: FIX.modes, waiting: null, last: null, ...over });

await check("readTopics: the rows, the counts, the waiting card and how the last one ended", async () => {
  const v = T.readTopics(viewBody({ waiting: { topic: 3, kind: "mode" },
    last: { outcome: "denied", why: "", at: 5, message: FIX.last_words.denied } }));
  assert.deepEqual(v.topics.map((t) => t.id), [1, 2, 3]);
  assert.equal(v.topics[0].system, true);
  assert.equal(v.topics[2].private, true);
  assert.equal(v.topics[2].mode, "learn_only");
  assert.equal(v.unchecked, 3);
  assert.equal(v.facts, 55);
  assert.equal(T.isWaiting(v), true);
  assert.equal(T.isWaitingOn(v, 3), true);
  assert.equal(T.isWaitingOn(v, 2), false);
  assert.equal(T.endedWords(v), FIX.last_words.denied);
  assert.equal(T.readTopics(viewBody()).waiting, null);
});

await check("readTopics: a row with a mode that is not one of the four is dropped, never guessed; anything else is null", async () => {
  const v = T.readTopics(viewBody({ topics: [UNSORTED, topic({ mode: "maybe" }), topic({ id: "x" })] }));
  assert.deepEqual(v.topics.map((t) => t.id), [1]);
  for (const bad of [null, undefined, "x", { ok: false }, { ok: true }, { ok: true, topics: "no" }, []]) {
    assert.equal(T.readTopics(bad), null);
  }
  assert.equal(T.readTopics(viewBody({ lists_hidden: true })).listsHidden, true);
  assert.equal(T.readTopics(viewBody({ backfill: { done: false, remaining: 12 } })).backfillRemaining, 12);
});

await check("a refusal is shown in the PC's own words; the shared sentence only when it sent none", async () => {
  assert.equal(T.isRefusal({ ok: false, error: "name_taken", message: "x" }), true);
  assert.equal(T.isRefusal({ ok: true }), false);
  assert.equal(T.refusalWords({ ok: false, error: "name_taken", message: "The PC says so." }), "The PC says so.");
  assert.equal(T.refusalWords({ ok: false, error: "name_taken" }), FIX.errors.name_taken);
  assert.equal(T.refusalWords({ ok: false, error: "made_up" }), FIX.errors.bad_request);
  assert.equal(T.refusalWords(null), FIX.errors.bad_request);
  assert.equal(T.isWaitingAnswer({ ok: true, waiting: true, id: 3, kind: "mode" }), true);
  assert.equal(T.isWaitingAnswer(viewBody()), false);
});

await check("the row: tags, the sorting line, the guess line and the reading of a row", async () => {
  const v = T.readTopics(viewBody({ backfill: { done: false, remaining: 4 } }));
  const off = T.readTopics(viewBody({ topics: [UNSORTED, topic({ mode: "off", private: true, skipped_week: 3, facts: 12 })] })).topics[1];
  assert.deepEqual(T.rowTags(off).map((t) => t.kind), ["private", "kept-hidden", "skipped"]);
  assert.equal(T.rowTags(off)[0].text, W.private_tag);
  assert.equal(T.rowTags(off)[1].text, "12 facts kept, hidden");
  assert.equal(T.rowTags(off)[2].text, "3 new things not saved this week");
  const notUsed = v.topics[2];
  assert.deepEqual(T.rowTags(notUsed).map((t) => t.text), [W.private_tag, W.not_used_tag]);
  assert.deepEqual(T.rowTags(v.topics[1]), []);
  assert.equal(T.sortingLine(v), "Jarvis is still sorting 4 of your facts.");
  assert.equal(T.sortingLine(T.readTopics(viewBody())), "");
  assert.equal(T.sortedGuessLine(v), "Jarvis sorted 3 of your 55 facts by guessing from the words. Check them so switching a topic off works as you expect.");
  assert.equal(T.checkButtonLabel(3), "Check these (3)");
  assert.equal(T.sortedGuessLine(T.readTopics(viewBody({ topics: [UNSORTED], unchecked: 0 }))), "");
  assert.equal(T.rowSpeech(v, v.topics[1]), "Work, 41 facts, Learn and use, button: change mode");
  assert.equal(T.factCount(1), "1 fact");
});

await check("hidden lists: rows read Topic N, a count and the mode; Unsorted keeps its name", async () => {
  const v = T.readTopics(viewBody({ lists_hidden: true, topics: [
    UNSORTED, topic({ name: "", mode: "use_only" }), topic({ id: 3, name: "", facts: 5, mode: "off" })] }));
  assert.equal(T.rowSpeech(v, v.topics[0]), "Unsorted, 9 facts, Learn and use, button: change mode");
  assert.equal(T.rowSpeech(v, v.topics[1]), "Topic 1, 41 facts, Use, but don't learn");
  assert.equal(T.rowSpeech(v, v.topics[2]), "Topic 2, 5 facts, Off");
  assert.equal(T.displayName(v, v.topics[2]), "Topic 2");
  assert.equal(T.displayName(v, v.topics[0]), "Unsorted");
});

await check("reorder, delete destinations, the more-open warning and the next colour", async () => {
  const own = (id) => topic({ id, name: `T${id}`, colour: id % 8 });
  const v = T.readTopics(viewBody({ topics: [UNSORTED, own(2), own(3), own(4)] }));
  assert.equal(T.moveTarget(v, 2, -1), undefined, "the first cannot go up");
  assert.equal(T.moveTarget(v, 3, -1), 2);
  assert.equal(T.moveTarget(v, 2, 1), 4, "down: before the one after the next");
  assert.equal(T.moveTarget(v, 3, 1), null, "second-last goes last");
  assert.equal(T.moveTarget(v, 4, 1), undefined, "the last cannot go down");
  assert.equal(T.moveTarget(v, 1, 1), undefined, "Unsorted does not move");
  assert.equal(T.moveTarget(v, 99, 1), undefined);
  assert.deepEqual(T.deleteDestinations(v, 3).map((t) => t.id), [1, 2, 4], "Unsorted included, first");
  const health = topic({ id: 5, name: "Health", private: true, mode: "off" });
  const open = topic({ id: 6, name: "Open", mode: "both" });
  const v2 = T.readTopics(viewBody({ topics: [UNSORTED, T.readTopics(viewBody({ topics: [UNSORTED, health, open] })).topics[1], open] }));
  const [h, o] = [T.topicById(v2, 5), T.topicById(v2, 6)];
  assert.equal(T.deleteWarning(v2, h, o), T.fill(W.delete_looser, { name: "Health" }));
  assert.equal(T.deleteWarning(v2, o, h), "");
  assert.equal(T.canAdd(v), true);
  const many = T.readTopics(viewBody({ topics: [UNSORTED, ...Array.from({ length: 16 }, (_, i) => own(i + 2))] }));
  assert.equal(T.canAdd(many), false, "16 of the owner's own; Unsorted is not counted");
  assert.equal(typeof T.nextColour(v), "number");
});

await check("the review list: facts, groups by suggested topic, the cursor", async () => {
  const facts = [
    { id: 5, text: "a", saved_at: 1, topic: 2, alt: null, how: "rule", checked: false, held_back: false },
    { id: 6, text: "b", saved_at: 1, topic: 2, alt: 4, how: "model", checked: false, held_back: true },
    { id: 7, text: "c", saved_at: 1, topic: 3, alt: null, how: "rule", checked: false, held_back: false },
    { id: "x", text: "no id" },
  ];
  const got = T.readFacts({ ok: true, facts, next: "3:8", total: 38, batch: 10 });
  assert.deepEqual(got.facts.map((f) => f.id), [5, 6, 7]);
  assert.equal(got.next, "3:8");
  assert.equal(got.total, 38);
  assert.equal(got.facts[1].heldBack, true);
  assert.equal(got.facts[1].how, "model");
  assert.deepEqual(T.groupByTopic(got.facts).map((g) => [g.topic, g.facts.length]), [[2, 2], [3, 1]]);
  assert.equal(T.readFacts({ ok: true, facts: [], next: null, total: 0 }).next, null);
  assert.equal(T.readFacts({ ok: true, lists_hidden: true, facts: [] }).listsHidden, true);
  assert.equal(T.readFacts({ ok: false }), null);
  assert.equal(T.heldWords("Work"), "Held back: might be about Work");
});

await check("the lines elsewhere: left out, kept hidden, the tag, the paused pin and the card's two buttons", async () => {
  assert.equal(T.leftOutLine(0), "");
  assert.equal(T.leftOutLine(1), W.left_out_one);
  assert.equal(T.leftOutLine(3), "Left out 3 facts because of your topic settings");
  assert.equal(T.leftOutLine("3"), "");
  assert.equal(T.keptHiddenLine(0), "");
  assert.equal(T.keptHiddenLine(4), "4 facts kept, hidden");
  const v = T.readTopics(viewBody());
  assert.equal(T.factTag(v, 3), W.not_used_tag);
  assert.equal(T.factTag(v, 2), "");
  assert.equal(T.factTag(null, 3), "", "no view, no claim");
  assert.equal(T.factTag(v, 99), "");
  assert.equal(T.pinPausedLine("Work"), "Paused: Work is off");
  assert.equal(T.pinPausedLine("Work", "off"), "Paused: Work is off");
  assert.equal(T.pinPausedLine("Work", "learn_only"), "Paused: Work is set to Learn, but don't use");
  for (const c of FIX.pin_paused_cases) assert.equal(T.pinPausedLine(c.name, c.mode), c.expect);
  assert.equal(T.keptHiddenLine(1), "1 fact kept, hidden");
  assert.deepEqual(T.askLabels({ topic_ask: true }), { accept: W.ask_save, decline: W.ask_skip });
  assert.equal(T.askLabels({ topic_ask: false }), null);
  assert.equal(T.askLabels({}), null);
  assert.deepEqual(T.readTopicPlace({ place: "topics", topic_id: 4 }), { topicId: 4 });
  assert.deepEqual(T.readTopicPlace({ place: "topics", topic_id: "4" }), { topicId: null });
  assert.deepEqual(T.readTopicPlace({ place: "history" }), { topicId: null });
});

await check("memory-used, profile and auto-learn readers keep the topic fields", async () => {
  const U = await import("../src/memory-used.js");
  const used = U.readUsed({ facts: [
    { id: 1, text: "", current: true, left_out: true },
    { id: 2, text: "Plain fact", current: true },
  ], missing: [] });
  assert.equal(used.facts[0].leftOut, true);
  assert.equal(used.facts[0].text, "");
  assert.equal(used.facts[1].leftOut, false);
  const P = await import("../src/memory-profile.js");
  const prof = P.readProfile({ facts: [{ id: 4, text: "x", added: 1, paused: true }, { id: 5, text: "y", added: 1 }], chars: 2, limit: 1200 });
  assert.deepEqual(prof.facts.map((f) => f.paused === true), [true, false]);
  const A = await import("../src/auto-learn.js");
  const auto = A.readAuto({ facts: [{ id: 8, text: "z", topic: 3 }, { id: 9, text: "q" }] });
  assert.deepEqual(auto.facts.map((f) => f.topic ?? 0), [3, 0]);
});

/* ── CONTROL: the wiring ──────────────────────────────────────────────── */

const COMMANDS = ["brain_topics", "brain_topics_edit", "brain_topics_mode", "brain_topics_file",
  "brain_topics_settings", "brain_topics_preview", "brain_topics_review", "brain_topics_hidden"];

/** The body of `pub async fn <name>` up to the next command. */
function rustBody(src, name) {
  const at = src.indexOf(`pub async fn ${name}(`);
  assert.ok(at > 0, `${name} is in topics.rs`);
  const rest = src.slice(at + 10);
  const next = rest.search(/#\[tauri::command\]|#\[cfg\(test\)\]/);
  return next < 0 ? rest : rest.slice(0, next);
}

await check("CONTROL: every command is registered, permitted on the Brain window only, and the writes are held on a stale link", async () => {
  const rs = read("src-tauri/src/brain/topics.rs");
  const lib = read("src-tauri/src/lib.rs");
  const build = read("src-tauri/build.rs");
  const surfaces = read("src-tauri/permissions/surfaces.toml");
  for (const cmd of COMMANDS) {
    assert.ok(lib.includes(`brain::topics::${cmd},`), `${cmd} in lib.rs`);
    assert.ok(build.includes(`"${cmd}",`), `${cmd} in build.rs`);
    assert.ok(surfaces.includes(`"allow-${cmd.replace(/_/g, "-")}",`), `${cmd} in surfaces.toml`);
    assert.ok(existsSync(join(HERE, "..", "src-tauri", "permissions", "autogenerated", `${cmd}.toml`)), `${cmd}.toml`);
  }
  const brain = JSON.parse(read("src-tauri/capabilities/brain.json"));
  assert.ok(brain.permissions.includes("brain-topics"));
  for (const other of ["hud", "quickbar", "settings", "widget", "floating", "faces", "onboarding"]) {
    const p = `src-tauri/capabilities/${other}.json`;
    if (existsSync(join(HERE, "..", p))) {
      assert.ok(!read(p).includes("brain-topics"), `${other} must not get the topics powers`);
    }
  }
  for (const cmd of ["brain_topics_edit", "brain_topics_mode", "brain_topics_file", "brain_topics_settings"]) {
    assert.match(rustBody(rs, cmd), /require_link_live\(&app\)\?/, `${cmd} is held on a stale link`);
  }
  for (const cmd of ["brain_topics", "brain_topics_preview", "brain_topics_review", "brain_topics_hidden"]) {
    assert.doesNotMatch(rustBody(rs, cmd), /require_link_live/, `${cmd} is a read`);
  }
  // Names and both fact lists are hidden in Rust, with the private lists and App lock.
  assert.match(rs, /private_hidden\(app\)\s*\|\|\s*crate::lock::app_locked\(app\)/);
  for (const cmd of ["brain_topics_review", "brain_topics_hidden"]) {
    const body = rustBody(rs, cmd);
    assert.ok(body.indexOf("words_hidden(&app)") >= 0 && body.indexOf("words_hidden(&app)") < body.indexOf("get(&app"),
      `${cmd} stops before asking the PC while hidden`);
  }
  assert.match(rustBody(rs, "brain_topics_file"), /words_hidden\(&app\)/);
  // The token is never logged or returned; no println of anything.
  assert.doesNotMatch(rs.split("#[cfg(test)]")[0], /println!|eprintln!|log::|tracing::/);
  // No route but the eight of section 107 is named.
  const routes = [...rs.split("#[cfg(test)]")[0].matchAll(/"(\/api\/[a-z/]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(routes)].sort(), ["/api/topics", "/api/topics/file", "/api/topics/hidden",
    "/api/topics/mode", "/api/topics/preview", "/api/topics/review", "/api/topics/settings"]);
});

await check("CONTROL: the route header carries topics_left_out and topic_id as numbers, in commands.rs", async () => {
  const c = read("src-tauri/src/commands.rs");
  assert.match(c, /route\.get\("topics_left_out"\)\.and_then\(\|v\| v\.as_u64\(\)\)/);
  assert.match(c, /\.get\("topic_id"\)/);
  assert.match(c, /fn the_route_line_carries_the_topic_fields_as_numbers_only/);
});

await check("CONTROL: brain.js only calls the eight commands, draws owner words as text, and keeps nothing", async () => {
  const brain = read("src/brain.js");
  const called = new Set([...brain.matchAll(/invoke\("(brain_topics[a-z_]*)"|topicsCall\("(brain_topics[a-z_]*)"/g)].map((m) => m[1] || m[2]));
  for (const c of called) assert.ok(COMMANDS.includes(c), `${c} is not one of the eight`);
  for (const c of COMMANDS) assert.ok(called.has(c), `${c} is used`);
  const from = brain.lastIndexOf("/* ====", brain.indexOf("Topics (the owner's request of 2026-09-30"));
  const to = brain.indexOf("Wiki - backend/wiki.patch.");
  assert.ok(from > 0 && to > from, "the section is one block");
  const block = brain.slice(from, to).replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
  assert.doesNotMatch(block, /innerHTML|insertAdjacentHTML|outerHTML|document\.write/, "owner words go in as text only");
  assert.doesNotMatch(block, /localStorage|sessionStorage|indexedDB/, "nothing of a topic is kept in this window");
  const mod = read("src/topics.js").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(mod, /localStorage|sessionStorage|innerHTML/);
  // Never a control for every topic at once, and nothing that approves a card.
  assert.doesNotMatch(block, /brain_approve|approve_|decide_approval|invoke\("decide/);
  assert.doesNotMatch(block, /forEach\([^)]*topicSetMode|for \(const t of [^)]*\)[^{]*\{\s*await topicSetMode/);
  const html = read("src/brain.html");
  assert.match(html, /id="topics-card" data-menu-id="brain\.memory\.topics"/);
});

await check("CONTROL: no hard-coded colour and no red in the topics styles", async () => {
  const css = read("src/brain.css");
  const from = css.indexOf("---- Topics (topics.js");
  assert.ok(from > 0);
  const block = css.slice(from);
  assert.doesNotMatch(block, /#[0-9a-fA-F]{3,8}\b(?![-\w])|rgba?\(|hsla?\(/, "tokens only");
  assert.doesNotMatch(block, /--danger|--bad|\bred\b/i);
});

/* ── The Brain window (needs Playwright) ──────────────────────────────── */

let K = null;
try {
  await import("playwright");
  K = await import("./uikit.mjs");
} catch {
  console.log("skip  the Brain window checks: Playwright is not installed (see tests/README.md)");
}

if (K) {
  const { base, close } = await K.serve();
  const browser = await K.launch();
  const SIZE = { width: 1180, height: 1300 };

  const own = (id, name, over = {}) => ({ id, name, colour: id % 8, icon: "folder", mode: "both", private: false,
    words: [], system: false, facts: 10, unchecked: 0, skipped_week: 0, pinned: 0, ...over });
  const scenario = (over = {}) => ({ topics: {
    topics: [
      own(1, "Unsorted", { system: true, colour: 6, icon: "flag", facts: 9 }),
      own(2, "Work", { colour: 0, icon: "briefcase", facts: 41, unchecked: 3, pinned: 1 }),
      own(3, "Health", { colour: 5, icon: "heart", private: true, mode: "learn_only", facts: 5 }),
      own(4, "Money", { colour: 2, icon: "coin", private: true, mode: "off", facts: 7, skipped_week: 2 }),
      own(5, "Hobbies", { colour: 1, icon: "music", mode: "use_only", facts: 12 }),
    ],
    review: [
      { id: 21, text: "Stand-up is at ten", saved_at: 1, topic: 2, alt: null, how: "rule", held_back: false },
      { id: 22, text: "Sister likes jazz", saved_at: 1, topic: 5, alt: 4, how: "model", held_back: true },
    ],
    hidden: { 4: [{ id: 31, text: "Owes the plumber", saved_at: 1, topic: 4, alt: null, how: "rule", checked: true, held_back: true }] },
    ...over } });

  async function memoryTab(data = {}, size = SIZE) {
    const page = await K.open(browser, base, "brain.html", data, size);
    await page.locator("#topics-card").waitFor();
    await page.waitForTimeout(500);
    return page;
  }
  const tcalls = (page) => page.evaluate(() => window.__topics.calls);
  const sent = async (page, cmd) => (await tcalls(page)).filter((c) => c.cmd === cmd);
  const text = (page, sel) => page.locator(sel).innerText();
  const settle = (page, ms = 350) => page.waitForTimeout(ms);
  const row = (page, id) => page.locator(`#topics-card .topics-row[data-topic="${id}"]`);
  const dialog = (page) => page.locator("dialog.topics-dialog");

  await check("the section shows its title, intro, Unsorted first, counts, tags and the modes as buttons", async () => {
    const page = await memoryTab(scenario());
    const title = (await page.locator("#topics-card h2").textContent()).trim();
    const intro = await text(page, "#topics-intro");
    const names = await page.locator("#topics-card .topics-name").allInnerTexts();
    const health = await text(page, `#topics-card .topics-row[data-topic="3"]`);
    const money = await text(page, `#topics-card .topics-row[data-topic="4"]`);
    const modeLabels = await page.locator("#topics-card .topics-mode").allInnerTexts();
    const aria = await page.locator(`#topics-card .topics-row[data-topic="5"] .topics-mode`).getAttribute("aria-label");
    const guess = await text(page, ".topics-guess");
    const icons = await page.locator("#topics-card .topics-row svg").count();
    await page.close();
    assert.equal(title, W.title);
    assert.equal(intro, W.intro);
    assert.deepEqual(names, ["Unsorted", "Work", "Health", "Money", "Hobbies"]);
    assert.match(health, new RegExp(W.private_tag));
    assert.match(health, new RegExp(W.not_used_tag));
    assert.match(health, /5 facts/);
    assert.match(money, /7 facts kept, hidden/);
    assert.match(money, /2 new things not saved this week/);
    assert.match(money, new RegExp(W.show_them));
    assert.deepEqual(modeLabels, ["Learn and use", "Learn and use", "Learn, but don't use", "Off", "Use, but don't learn"]);
    assert.equal(aria, "Hobbies, 12 facts, Use, but don't learn, button: change mode");
    assert.match(guess, /Jarvis sorted 3 of your 74 facts by guessing/);
    assert.match(guess, /Check these \(3\)/);
    assert.ok(icons >= 5, "an icon on every row: colour is never the only clue");
  });

  await check("a PC without topic controls says so in one line and draws no rows", async () => {
    const page = await memoryTab({});
    const body = await text(page, "#topics-card");
    const rows = await page.locator("#topics-card .topics-row").count();
    await page.close();
    assert.ok(body.includes(W.missing));
    assert.equal(rows, 0);
  });

  await check("the picker offers all four choices with their sentences, the current one marked, and sends nothing until Change", async () => {
    const page = await memoryTab(scenario());
    await row(page, 2).locator(".topics-mode").click();
    await dialog(page).waitFor();
    const labels = await dialog(page).locator(".topics-choice-name").allInnerTexts();
    const sentences = await dialog(page).locator(".topics-choice-sentence").allInnerTexts();
    const checked = await dialog(page).locator("input:checked").getAttribute("value");
    const changeDisabled = await dialog(page).getByRole("button", { name: W.check_right }).count();
    const change = dialog(page).getByRole("button", { name: "Change" });
    const disabledFirst = await change.isDisabled();
    const described = await dialog(page).locator("input[value='off']").getAttribute("aria-describedby");
    const describedText = await page.locator(`#${described}`).innerText();
    const before = (await tcalls(page)).filter((c) => c.cmd === "brain_topics_mode").length;
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    await settle(page);
    const after = (await tcalls(page)).filter((c) => c.cmd === "brain_topics_mode").length;
    const gone = await dialog(page).count();
    const back = await page.evaluate(() => document.activeElement && document.activeElement.dataset.fkey);
    await page.close();
    assert.deepEqual(labels, FIX.modes.map((m) => m.name));
    assert.deepEqual(sentences, FIX.modes.map((m) => m.sentence));
    assert.equal(checked, "both");
    assert.equal(changeDisabled, 0);
    assert.equal(disabledFirst, true, "Change is off while the current choice is selected");
    assert.equal(describedText, FIX.modes[3].sentence, "each choice is described by its sentence");
    assert.equal(before, 0);
    assert.equal(after, 0, "Cancel changes nothing");
    assert.equal(gone, 0);
    assert.equal(back, "mode-2", "the keyboard goes back to the mode button");
  });

  await check("choosing another mode reads the preview: the PC's sentence, and the card line only when a card will be raised", async () => {
    const page = await memoryTab(scenario());
    await row(page, 2).locator(".topics-mode").click();
    await dialog(page).locator("input[value='learn_only']").check();
    await settle(page);
    const line = await text(page, ".topics-preview");
    const cardLine = await dialog(page).locator(".topics-card-line").innerText();
    const asked = await sent(page, "brain_topics_preview");
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    // Health is private and "Learn, but don't use": Learn and use is looser and asks.
    await row(page, 3).locator(".topics-mode").click();
    await dialog(page).locator("input[value='both']").check();
    await settle(page);
    const healthLine = await text(page, ".topics-preview");
    const healthCard = await dialog(page).locator(".topics-card-line").innerText();
    await page.close();
    assert.deepEqual(asked.map((c) => [c.id, c.mode]), [[2, "learn_only"]]);
    assert.match(line, /41 things Jarvis knows about Work will be left out of answers\./);
    assert.match(line, /1 pinned fact about Work will pause until you switch it back on\./);
    assert.equal(cardLine, "");
    assert.equal(healthCard, W.private_asks);
    assert.match(healthLine, /Nothing Jarvis knows about Health will change in answers\./);
  });

  await check("Change sends the topic and mode, shows what happened with Undo, and Undo sends the old mode back", async () => {
    const page = await memoryTab(scenario());
    await row(page, 2).locator(".topics-mode").click();
    await dialog(page).locator("input[value='off']").check();
    await settle(page);
    await dialog(page).getByRole("button", { name: "Change" }).click();
    await settle(page, 500);
    const mode = await sent(page, "brain_topics_mode");
    const notice = await text(page, ".topics-notice");
    const label = await row(page, 2).locator(".topics-mode").innerText();
    const showThem = await row(page, 2).getByRole("button", { name: W.show_them }).count();
    await page.locator(".topics-notice").getByRole("button", { name: "Undo" }).click();
    await settle(page, 500);
    const all = await sent(page, "brain_topics_mode");
    const back = await row(page, 2).locator(".topics-mode").innerText();
    await page.close();
    assert.deepEqual(mode.map((c) => [c.id, c.mode]), [[2, "off"]]);
    assert.match(notice, /Work is now: Off\./);
    assert.equal(label, "Off");
    assert.equal(showThem, 1);
    assert.deepEqual(all.map((c) => [c.id, c.mode]), [[2, "off"], [2, "both"]]);
    assert.equal(back, "Learn and use");
  });

  await check("a looser choice on a private topic is a card: the row says waiting, the picker cannot be reopened, and the PC's ending is shown", async () => {
    const page = await memoryTab(scenario());
    await row(page, 3).locator(".topics-mode").click();
    await dialog(page).locator("input[value='both']").check();
    await settle(page);
    await dialog(page).getByRole("button", { name: "Change" }).click();
    await settle(page, 600);
    const waiting = await text(page, `#topics-card .topics-row[data-topic="3"]`);
    const modeButtons = await row(page, 3).locator(".topics-mode").count();
    const stillOld = await page.evaluate(() => window.__topicsView().topics.find((t) => t.id === 3).mode);
    await page.evaluate(() => window.__topicsDecide("applied"));
    await page.waitForTimeout(2600);
    const notice = await text(page, ".topics-notice");
    const label = await row(page, 3).locator(".topics-mode").innerText();
    await page.close();
    assert.ok(waiting.includes(W.waiting));
    assert.equal(modeButtons, 0, "the picker cannot be reopened while its card waits");
    assert.equal(stillOld, "learn_only", "nothing changed yet");
    assert.ok(notice.includes(FIX.last_words.applied));
    assert.equal(label, "Learn and use");
  });

  await check("a card that is turned down leaves the mode as it was and says so in the PC's words", async () => {
    const page = await memoryTab(scenario());
    await row(page, 4).locator(".topics-mode").click();
    await dialog(page).locator("input[value='use_only']").check();
    await settle(page);
    await dialog(page).getByRole("button", { name: "Change" }).click();
    await settle(page, 600);
    await page.evaluate(() => window.__topicsDecide("denied"));
    await page.waitForTimeout(2600);
    const notice = await text(page, ".topics-notice");
    const label = await row(page, 4).locator(".topics-mode").innerText();
    await page.close();
    assert.ok(notice.includes(FIX.last_words.denied));
    assert.equal(label, "Off");
  });

  await check("a stale link greys every write and sends nothing", async () => {
    const page = await memoryTab({ ...scenario(), link: { connected: true, stale: true } });
    await row(page, 2).locator(".topics-mode").click();
    await dialog(page).locator("input[value='off']").check();
    await settle(page);
    const change = await dialog(page).getByRole("button", { name: "Change" }).isDisabled();
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    const add = await page.getByRole("button", { name: W.add_button }).isDisabled();
    const model = await page.locator("[data-fkey='model-help']").isDisabled();
    const writes = (await tcalls(page)).filter((c) => /mode|edit|file|settings/.test(c.cmd));
    await page.close();
    assert.equal(change, true);
    assert.equal(add, true);
    assert.equal(model, true);
    assert.equal(writes.length, 0);
  });

  await check("Check these: ten at a time, grouped, guessed and held-back tags, These are right sends the ids, File under sends one", async () => {
    const page = await memoryTab(scenario());
    await page.getByRole("button", { name: "Check these (3)" }).click();
    await settle(page);
    const panel = await text(page, ".topics-review");
    const groups = await page.locator(".topics-review-group").allInnerTexts();
    const read = await sent(page, "brain_topics_review");
    await page.locator(".topics-review-fact").nth(1).locator("select").selectOption({ label: "Money" });
    await settle(page, 500);
    const filed = await sent(page, "brain_topics_file");
    await page.getByRole("button", { name: W.check_right }).click();
    await settle(page, 500);
    const both = await sent(page, "brain_topics_file");
    const empty = await text(page, ".topics-review");
    await page.close();
    assert.equal(read[0].limit, 10);
    assert.deepEqual(groups.map((g) => g.trim()), ["Work", "Hobbies"]);
    assert.match(panel, /Stand-up is at ten/);
    assert.ok(panel.includes(W.check_guessed));
    assert.ok(panel.includes("Held back: might be about Hobbies"));
    assert.deepEqual(filed.map((c) => [c.ids, c.topicId]), [[[22], 4]]);
    assert.deepEqual(both[1].ids, [21]);
    assert.equal(both[1].confirm, true);
    assert.match(empty, /Nothing to check\./);
  });

  await check("Show them lists an Off topic's facts read-only, greyed, with Forget and Erase the words", async () => {
    const page = await memoryTab(scenario());
    await row(page, 4).getByRole("button", { name: W.show_them }).click();
    await settle(page, 500);
    const shown = await text(page, `#topics-card .topics-row[data-topic="4"]`);
    const buttons = await row(page, 4).locator(".topics-hidden-fact button").allInnerTexts();
    const read = await sent(page, "brain_topics_hidden");
    await page.close();
    assert.match(shown, /Owes the plumber/);
    assert.match(shown, /Hidden from answers/);
    assert.deepEqual(buttons, ["Forget", "Erase the words"]);
    assert.deepEqual(read.map((c) => c.id), [4]);
  });

  await check("Show them: a long list shows Show more, which asks for the page after the last one", async () => {
    const many = [31, 32, 33].map((id) => ({ id, text: `Fact number ${id}`, saved_at: 1, topic: 4, alt: null, how: "rule", checked: true, held_back: true }));
    const page = await memoryTab(scenario({ hidden: { 4: many }, hiddenPage: 2 }));
    await row(page, 4).getByRole("button", { name: W.show_them }).click();
    await settle(page, 500);
    const before = await text(page, `#topics-card .topics-row[data-topic="4"]`);
    await row(page, 4).getByRole("button", { name: "Show more" }).click();
    await settle(page, 500);
    const after = await text(page, `#topics-card .topics-row[data-topic="4"]`);
    const moreLeft = await row(page, 4).getByRole("button", { name: "Show more" }).count();
    const reads = await sent(page, "brain_topics_hidden");
    await page.close();
    assert.ok(!before.includes("Fact number 33") && before.includes("Fact number 32"));
    assert.ok(after.includes("Fact number 31") && after.includes("Fact number 33"));
    assert.equal(moreLeft, 0);
    assert.equal(reads.length, 2);
    assert.equal(reads[1].after, 32);
  });

  await check("Add a topic: name, colour, icon and keywords go in one body; a name in use shows the PC's sentence; the button stops at 16", async () => {
    const page = await memoryTab(scenario());
    await page.getByRole("button", { name: W.add_button }).click();
    await dialog(page).waitFor();
    const legends = await dialog(page).locator("legend").allInnerTexts();
    const iconCount = await dialog(page).locator(".topics-icon-choice").count();
    const colourCount = await dialog(page).locator(".topics-swatch-choice").count();
    const maxLen = await dialog(page).locator("input[type=text]").getAttribute("maxlength");
    await dialog(page).getByRole("button", { name: "Save" }).click();
    const emptyName = await dialog(page).locator(".topics-dialog-error").innerText();
    await dialog(page).locator("input[type=text]").fill("work");
    await dialog(page).locator("input[name='topics-colour'][value='4']").check();
    await dialog(page).locator("input[name='topics-icon'][value='leaf']").check();
    await dialog(page).getByRole("button", { name: "Save" }).click();
    await settle(page);
    const taken = await dialog(page).locator(".topics-dialog-error").innerText();
    await dialog(page).locator("input[type=text]").fill("Garden  plans ");
    await dialog(page).locator("textarea").fill("Roses, compost");
    await dialog(page).getByRole("button", { name: "Save" }).click();
    await settle(page, 500);
    const edits = (await sent(page, "brain_topics_edit")).map((c) => c.edit);
    const names = await page.locator("#topics-card .topics-name").allInnerTexts();
    await page.close();
    assert.ok(legends.includes("Colour") && legends.includes("Icon"));
    assert.equal(iconCount, 13);
    assert.equal(colourCount, 8);
    assert.equal(maxLen, "24");
    assert.equal(emptyName, FIX.errors.bad_name);
    assert.equal(edits.length, 2, "an empty name is refused before anything is sent");
    assert.equal(taken, FIX.errors.name_taken);
    assert.deepEqual(edits[1], { op: "add", name: "Garden plans", colour: 4, icon: "leaf", words: ["roses", "compost"] });
    assert.ok(names.includes("Garden plans"));
    const full = await memoryTab({ topics: { topics: [
      own(1, "Unsorted", { system: true }), ...Array.from({ length: 16 }, (_, i) => own(i + 2, `T${i + 2}`))] } });
    const disabled = await full.getByRole("button", { name: W.add_button }).isDisabled();
    await full.close();
    assert.equal(disabled, true);
  });

  await check("the row menu: rename, colour and icon, move, mark private, keywords - each its own small change; Not private is a card", async () => {
    const page = await memoryTab(scenario());
    await row(page, 5).getByRole("button", { name: /^Edit/ }).click();
    const menu = await row(page, 5).locator(".topics-menu").locator("button").allInnerTexts();
    await row(page, 5).getByRole("button", { name: "Rename" }).click();
    await dialog(page).locator("input[type=text]").fill("Pastimes");
    await dialog(page).getByRole("button", { name: "Save" }).click();
    await settle(page, 500);
    await row(page, 5).getByRole("button", { name: "Move up" }).click();
    await settle(page, 500);
    const order = await page.locator("#topics-card .topics-name").allInnerTexts();
    await row(page, 5).getByRole("button", { name: "Mark private" }).click();
    await settle(page, 500);
    const privTag = await text(page, `#topics-card .topics-row[data-topic="5"]`);
    await row(page, 5).getByRole("button", { name: "Keywords" }).click();
    await dialog(page).locator("textarea").fill("guitar, piano lessons");
    await dialog(page).getByRole("button", { name: "Save" }).click();
    await settle(page, 500);
    await row(page, 3).getByRole("button", { name: /^Edit/ }).click();
    const notPrivate = await row(page, 3).getByRole("button", { name: "Not private" }).getAttribute("title");
    await row(page, 3).getByRole("button", { name: "Not private" }).click();
    await settle(page, 700);
    const waiting = await text(page, `#topics-card .topics-row[data-topic="3"]`);
    const edits = (await sent(page, "brain_topics_edit")).map((c) => c.edit);
    await page.close();
    assert.deepEqual(menu, ["Rename", "Colour and icon", "Move up", "Mark private", "Keywords", "Delete"],
      "the last topic cannot move down");
    assert.deepEqual(edits[0], { op: "rename", id: 5, name: "Pastimes" });
    assert.deepEqual(edits[1], { op: "move", id: 5, before: 4 });
    assert.deepEqual(edits[2], { op: "private", id: 5, private: true });
    assert.deepEqual(edits[3], { op: "words", id: 5, words: ["guitar", "piano lessons"] });
    assert.deepEqual(edits[4], { op: "private", id: 3, private: false });
    assert.deepEqual(order.slice(0, 5), ["Unsorted", "Work", "Health", "Pastimes", "Money"]);
    assert.match(privTag, new RegExp(W.private_tag));
    assert.equal(notPrivate, W.private_asks);
    assert.ok(waiting.includes(W.waiting));
  });

  await check("Unsorted has a mode button and no menu; deleting a topic asks where its facts go and warns when that home is more open", async () => {
    const page = await memoryTab(scenario());
    const unsortedMenu = await row(page, 1).getByRole("button", { name: /^Edit/ }).count();
    const unsortedMode = await row(page, 1).locator(".topics-mode").count();
    await row(page, 3).getByRole("button", { name: /^Edit/ }).click();
    await row(page, 3).getByRole("button", { name: "Delete" }).click();
    await dialog(page).waitFor();
    const words = await dialog(page).innerText();
    const del = dialog(page).getByRole("button", { name: "Delete" });
    const disabledFirst = await del.isDisabled();
    await dialog(page).locator("input[name='topics-home'][value='5']").check();
    const warn = await dialog(page).locator(".topics-card-line").innerText();
    await dialog(page).locator("input[name='topics-home'][value='4']").check();
    const noWarn = await dialog(page).locator(".topics-card-line").innerText();
    await dialog(page).locator("input[name='topics-home'][value='4']").check();
    await del.click();
    await settle(page, 500);
    const edits = (await sent(page, "brain_topics_edit")).map((c) => c.edit);
    const names = await page.locator("#topics-card .topics-name").allInnerTexts();
    await page.close();
    assert.equal(unsortedMenu, 0);
    assert.equal(unsortedMode, 1);
    assert.ok(words.includes(W.confirm_delete));
    assert.ok(words.includes(W.delete_where));
    assert.equal(disabledFirst, true);
    assert.equal(warn, T.fill(W.delete_looser, { name: "Health" }));
    assert.equal(noWarn, "");
    assert.deepEqual(edits, [{ op: "delete", id: 3, moveTo: 4 }]);
    assert.ok(!names.includes("Health"));
  });

  await check("the local-model switch sends its own setting and needs no card", async () => {
    const page = await memoryTab(scenario());
    const label = await text(page, ".topics-model-help");
    const note = await text(page, ".topics-model-note");
    await page.locator("[data-fkey='model-help']").check();
    await settle(page, 500);
    const got = await sent(page, "brain_topics_settings");
    const on = await page.locator("[data-fkey='model-help']").isChecked();
    const help = await text(page, ".topics-help");
    await page.close();
    assert.equal(label, W.model_help);
    assert.equal(note, W.model_help_note);
    assert.equal(help, W.help_plain);
    assert.deepEqual(got.map((c) => c.modelHelp), [true]);
    assert.equal(on, true);
  });

  await check("hidden lists: rows read Topic N, a count and the mode; no name, keyword or check list is drawn; the picker still works", async () => {
    const data = scenario();
    data.topics.topics[1].words = ["standup"];
    const page = await memoryTab({ ...data, security: { hidden: true } });
    const body = await text(page, "#topics-card");
    const aria = await page.locator("#topics-card .topics-mode").evaluateAll((n) => n.map((x) => x.getAttribute("aria-label")));
    const menus = await page.locator("#topics-card").getByRole("button", { name: /^Edit/ }).count();
    const check = await page.getByRole("button", { name: /^Check these/ }).count();
    const showThem = await page.getByRole("button", { name: W.show_them }).count();
    const add = await page.getByRole("button", { name: W.add_button }).count();
    const model = await page.locator("[data-fkey='model-help']").count();
    await row(page, 2).locator(".topics-mode").click();
    await dialog(page).locator("input[value='off']").check();
    await settle(page);
    const preview = await dialog(page).locator(".topics-preview").innerText();
    await dialog(page).getByRole("button", { name: "Change" }).click();
    await settle(page, 500);
    const mode = await sent(page, "brain_topics_mode");
    const reads = (await tcalls(page)).filter((c) => c.cmd === "brain_topics_review" || c.cmd === "brain_topics_hidden");
    await page.close();
    assert.doesNotMatch(body, /Work|Health|Money|Hobbies|standup/);
    assert.match(body, /Unsorted/);
    assert.deepEqual(aria, ["Unsorted, 9 facts, Learn and use, button: change mode",
      "Topic 1, 41 facts, Learn and use", "Topic 2, 5 facts, Learn, but don't use",
      "Topic 3, 7 facts, Off", "Topic 4, 12 facts, Use, but don't learn"]);
    assert.equal(menus, 0);
    assert.equal(check, 0);
    assert.equal(showThem, 0);
    assert.equal(add, 0);
    assert.equal(model, 1, "the model switch stays");
    assert.doesNotMatch(preview, /Work/);
    assert.match(preview, /Topic 1/, "the sentence is built from the numbers, with Topic N");
    assert.deepEqual(mode.map((c) => [c.id, c.mode]), [[2, "off"]]);
    assert.equal(reads.length, 0, "the two fact lists are not even asked for");
  });

  await check("App lock hides the names the same way", async () => {
    const page = await memoryTab({ ...scenario(), appLock: true });
    const body = await text(page, "#topics-card");
    await page.close();
    assert.doesNotMatch(body, /Work|Health|Money|Hobbies/);
  });

  await check("elsewhere in the Brain: the tag on a fact, the kept-hidden line, a paused pin, and a topic card's two buttons", async () => {
    const data = scenario();
    const now = Date.now() / 1000;
    data.brain = { ...K.BRAIN,
      memory_facts: { available: true, learning: true, pending: 1, topics_hidden: 4, facts: [
        { id: 61, text: "Has a dentist appointment.", source: "user", topic: 3, valid_from: now - 9000, valid_to: null },
        { id: 62, text: "Likes the piano.", source: "user", topic: 5, valid_from: now - 9000, valid_to: null }] },
      memory_pending: { available: true, setup: {}, pending: [
        { id: 71, text: "Presents at the Monday stand-up.", source: "conversation", confidence: 0.8,
          created: now - 100, topic_ask: true },
        { id: 72, text: "Likes tea.", source: "conversation", confidence: 0.8, created: now - 100 }] } };
    data.profile = { reads: 0, limit: 1200, facts: [{ id: 61, text: "Has a dentist appointment.", added: now - 500, paused: true, topic: 3 }] };
    const page = await memoryTab(data);
    await settle(page, 700);
    const facts = await text(page, "#memory-facts");
    const pins = await text(page, "#memory-profile");
    const waiting = await page.locator("#memory-proposals .row-item").evaluateAll((rows) =>
      rows.map((r) => [...r.querySelectorAll("button")].map((b) => b.textContent)));
    await page.close();
    assert.match(facts, /4 facts kept, hidden/);
    const first = facts.split("Has a dentist")[1].split("Likes the piano")[0];
    assert.ok(first.includes(W.not_used_tag), "the Learn-but-don't-use topic's fact carries the tag");
    assert.ok(!facts.split("Likes the piano")[1].includes(W.not_used_tag), "a Use-only topic's fact does not");
    assert.match(pins, /Paused: Health is set to Learn, but don't use/);
    assert.ok(!/is off/.test(pins), "Learn-but-don't-use is not called Off");
    assert.deepEqual(waiting[0], [W.ask_save, W.ask_skip]);
    assert.deepEqual(waiting[1], ["Keep", "Discard"]);
  });

  await check("the chat's quiet line: Left out N facts (a count, so shown whatever the lock settings say), and a left-out fact's own line", async () => {
    const page = await K.open(browser, base, "index.html", {}, { width: 700, height: 600 });
    const got = await page.evaluate(async () => {
      const mod = await import("/answer-memory.js");
      const mk = () => document.createElement("div");
      const parts = { box: mk(), lineButton: document.createElement("button"), list: mk(), note: mk() };
      const am = mod.createAnswerMemory({ ...parts, invoke: async () => null, isStale: () => false,
        confirm: () => false, announce: () => {}, onChange: () => {} });
      am.begin(false);
      am.route({ lane: "x", topics_left_out: 2 });
      const two = parts.note.textContent;
      am.begin(false);
      am.route({ lane: "x", topics_left_out: 1 });
      const one = parts.note.textContent;
      am.begin(false);
      am.route({ lane: "x" });
      return { two, one, none: parts.note.textContent, hiddenNone: parts.note.hidden };
    });
    await page.close();
    assert.match(got.two, /Left out 2 facts because of your topic settings/);
    assert.match(got.one, /Left out 1 fact because of your topic settings/);
    assert.equal(got.none, "");
    assert.equal(got.hiddenNone, true);
  });

  await check("a spoken 'switch off my work topic' opens the picker for that topic, and changes nothing", async () => {
    const page = await K.open(browser, base, "brain.html", scenario(), SIZE);
    await page.evaluate(() => localStorage.setItem("jarvis.brain.place",
      JSON.stringify({ place: "topics", topic_id: 2, at: Date.now() })));
    await page.evaluate(() => window.dispatchEvent(new StorageEvent("storage", {
      key: "jarvis.brain.place", newValue: localStorage.getItem("jarvis.brain.place") })));
    await page.waitForTimeout(700);
    const open = await dialog(page).count();
    const title = open ? await dialog(page).locator(".topics-dialog-title").innerText() : "";
    const writes = (await tcalls(page)).filter((c) => /mode|edit|file|settings/.test(c.cmd));
    await page.close();
    assert.equal(open, 1);
    assert.equal(title, "Work");
    assert.equal(writes.length, 0);
  });

  await browser.close();
  close();
}

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("\nTopics: the four choices are always offered, the PC decides every card, names are hidden with the private lists, every write held on a stale link");
