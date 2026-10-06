/**
 * palette.mjs - the command palette's list, held to the real catalogue and to
 * the pages the rows open.
 *
 *     node tests/palette.mjs
 *
 * No browser, on purpose: this is the half that must pass on any PC, and the
 * half a browser suite cannot check as cheaply. It answers the three ways a
 * palette in this project could be wrong while looking right:
 *
 *   1. a SECOND list of names, typed by hand beside the generated catalogue,
 *      which drifts from backend/jarvis_menus.py and sends the owner to a
 *      card that no longer exists - the exact class of defect the 2026-10-05
 *      UI audit was written about;
 *   2. a row that opens NOTHING: the place it names has no matching card in
 *      settings.html or brain.html, so pressing Enter does nothing and says
 *      nothing;
 *   3. a search that cannot find the app's own words, or an empty state that
 *      shows a bare nothing / a bare zero instead of a sentence.
 *
 * The keyboard half (focus trap, arrows, Enter, Escape, the screen-reader
 * announcement) is tests/palette-ui.mjs, which needs Playwright.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  WORDS,
  buildPalette,
  describe,
  entryPlace,
  fill,
  headingOf,
  placeFor,
  search,
} from "../src/palette.js";
import { GROUP_PREFIX, GROUPS, MENUS, has } from "../src/menu-visibility.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");
const page = (name) => readFileSync(join(SRC, name), "utf8");

const fails = [];
const check = (name, fn) => {
  try { fn(); console.log(`ok    ${name}`); }
  catch (e) { fails.push(name); console.log(`FAIL  ${name}\n      ${e.message}`); }
};

const DESKTOP = MENUS.filter((m) => has(m, "desktop"));
/** The catalogue's own "never hidden" bookkeeping: not destinations, so the
 *  palette leaves them out on purpose (there is a check for that below). */
const NOT_A_PLACE = DESKTOP.filter((m) => m.area === "safety" && m.kind !== "entry");
const PLACEABLE = DESKTOP.filter((m) => !NOT_A_PLACE.includes(m));
const ITEMS = buildPalette();
const ROWS = ITEMS.filter((i) => i.kind !== "group");
/** menu-catalog.js's own GROUPS carry the prefix already (`group.study`). */
const GROUP_IDS = new Set(GROUPS.map((g) => g.id));

/* ── 1. One list: the catalogue's, never a second copy ──────────────────── */

check("every menu this PC has is in the palette, exactly once", () => {
  const ids = ROWS.map((r) => r.id);
  assert.equal(new Set(ids).size, ids.length, "a menu is in the list twice");
  const missing = PLACEABLE.map((m) => m.id).filter((id) => !ids.includes(id));
  assert.deepEqual(missing, [], `in the catalogue and not in the palette: ${missing.join(", ")}`);
  const extra = ids.filter((id) => !PLACEABLE.some((m) => m.id === id));
  assert.deepEqual(extra, [], `in the palette and not in the catalogue: ${extra.join(", ")}`);
});

check("the palette drops only what no window can open, and drops nothing else", () => {
  const ids = new Set(ROWS.map((r) => r.id));
  const dropped = DESKTOP.filter((m) => !ids.has(m.id));
  assert.deepEqual(dropped.map((m) => m.id).sort(), NOT_A_PLACE.map((m) => m.id).sort(),
    "the palette dropped something other than the catalogue's non-destination rows");
  for (const m of NOT_A_PLACE) {
    // Every one of them is a THING, not a place: "Approval cards, the widget,
    // the notification". There is no window to open, so a row would do
    // nothing when pressed - worse than not being there.
    assert.equal(placeFor({ kind: m.kind, id: m.id, place: entryPlace(m) }), null,
      `${m.id} is listed as a non-destination but placeFor opens something`);
  }
});

check("every name, sentence and alias comes from the catalogue", () => {
  const byId = new Map(DESKTOP.map((m) => [m.id, m]));
  for (const row of ROWS) {
    const m = byId.get(row.id);
    assert.ok(m, `${row.id} is not a catalogue id`);
    assert.equal(row.title, m.title, `${row.id}'s title was retyped`);
    assert.equal(row.about, m.about, `${row.id}'s one-line description was retyped`);
    assert.deepEqual(row.names, m.names, `${row.id}'s spoken names were retyped`);
  }
});

check("the six named groups are the catalogue's own", () => {
  const groups = ITEMS.filter((i) => i.kind === "group");
  // The catalogue's own ids already carry the prefix (`group.study`).
  const wanted = GROUPS.filter((g) => g.members.desktop.length > 0);
  assert.deepEqual(groups.map((g) => g.id), wanted.map((g) => g.id));
  assert.equal(groups.length, wanted.length,
    `${groups.length} groups listed, ${wanted.length} have a menu on this PC (home has none on the desktop)`);
  assert.ok(groups.length >= 5, "the palette dropped a named group");
  for (const g of groups) {
    const src = wanted.find((w) => w.id === g.id);
    assert.equal(g.title, src.title);
    assert.equal(g.about, src.about);
  }
});

check("the palette does not carry a second list of names in its own source", () => {
  // A name typed by hand here is the drift this file exists to refuse. The
  // words, the icons and the key are allowed; a menu title is not. Comments
  // are blanked first, because prose ABOUT a card is documentation, not a
  // second list (the same reason check-tokens.py blanks them).
  const strip = (text) => text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/^\s*\/\/.*$/gm, " ");
  const headings = new Set(Object.values(WORDS.group_headings));
  for (const file of ["palette.js", "palette-ui.js"]) {
    const text = strip(page(file));
    for (const m of DESKTOP) {
      if (GROUP_IDS.has(m.id)) continue;       // a group's title IS one of the palette's own words
      if (headings.has(m.title)) continue;     // "Settings" is a heading here, not a copied name
      assert.ok(!text.includes(`"${m.title}"`),
        `${file} spells out the menu title "${m.title}" instead of reading the catalogue`);
      if (m.about && m.about.length > 20) {
        assert.ok(!text.includes(m.about), `${file} retypes the description of ${m.id}`);
      }
    }
  }
});

check("nothing in the palette invokes, fetches or answers anything", () => {
  // "It offers only what already exists": no new command, no new way out of
  // the PC, no card. The two places that DO ask Rust to open a window live in
  // main.js beside the mechanisms that were already there.
  for (const file of ["palette.js", "palette-ui.js"]) {
    const text = page(file);
    assert.doesNotMatch(text, /invoke\(|fetch\(|stream_chat|decide_approval/,
      `${file} reaches the backend directly`);
  }
  // And no literal colour: the token guard (scripts/check-tokens.py) covers
  // style.css, not a colour welded into a module.
  for (const file of ["palette.js", "palette-ui.js"]) {
    assert.doesNotMatch(page(file), /#[0-9a-fA-F]{3,8}\b(?![-\w])/, `${file} has a hex colour`);
  }
});

/* ── 2. Every row opens something real ──────────────────────────────────── */

const settingsIds = new Set(
  [...page("settings.html").matchAll(/id="([a-z0-9-]+)"/g)].map((m) => m[1]));
const brainIds = new Set(
  [...page("brain.html").matchAll(/data-menu-id="([a-z0-9.\-]+)"/g)].map((m) => m[1]));
/** Rail tabs are `tab-<view>` inside #rail-nav (tests/rail-tabs.mjs counts the
 *  same list); the view key is the catalogue's own `view`. */
const brainTabs = new Set(
  [...page("brain.html").matchAll(/id="tab-([a-z0-9]+)"/g)].map((m) => m[1]));

check("every row's place exists on the page it opens", () => {
  for (const row of ROWS) {
    const place = placeFor(row);
    assert.ok(place, `${row.id} has no place, so pressing Enter would do nothing`);
    const m = DESKTOP.find((x) => x.id === row.id);
    if (place.window === "settings") {
      // The same mapping settings.js's goToPlace uses: `settings.hardware` is
      // #hardware, and a row of a card opens its parent card.
      assert.ok(settingsIds.has(place.place),
        `${row.id} opens Settings at #${place.place}, which settings.html does not have`);
    } else {
      assert.ok(brainTabs.has(place.tab),
        `${row.id} opens the Brain at tab "${place.tab}", which the rail does not have`);
      if (m.kind === "tab") {
        assert.equal(place.card, "", `${row.id} is a tab and names a card as well`);
      } else if (m.kind === "card") {
        assert.equal(place.card, row.id, `${row.id} is a card and opens something else`);
      } else {
        // A row of a card (`brain.work.quiz.youtube`, `brain.history.tag-suggestions`)
        // has no element of its own: it opens the nearest card it lives in.
        let at = m.parent;
        let up = at ? DESKTOP.find((x) => x.id === at) : null;
        while (up && up.kind !== "card") {
          at = up.parent;
          up = at ? DESKTOP.find((x) => x.id === at) : null;
        }
        assert.ok(up && up.kind === "card",
          `${row.id} is neither a card nor a row of one, so nothing could show it`);
        assert.ok(brainIds.has(up.id), `${row.id} opens ${up.id}, which is not on the page`);
        assert.equal(place.card, up.id, `${row.id} does not open the card it lives in`);
      }
    }
  }
});

check("every group row opens its first member rather than nowhere", () => {
  for (const item of ITEMS.filter((i) => i.kind === "group")) {
    const place = placeFor(item);
    assert.ok(place, `${item.title} opens nothing`);
    const first = item.place.members[0];
    const target = DESKTOP.find((m) => m.id === first);
    assert.equal(place.window, target.area === "settings" ? "settings" : "brain",
      `${item.title} opens the wrong window for ${first}`);
  }
});

check("placeFor refuses what it cannot open instead of guessing", () => {
  assert.equal(placeFor(null), null);
  assert.equal(placeFor({ kind: "card", id: "brain.work.quiz" }), null,
    "a row with no place must come back null, not a made-up window");
  assert.equal(placeFor({ kind: "card", id: "x", place: { window: "nope" } }), null);
});

check("entryPlace reads the Brain view straight off the catalogue", () => {
  const quiz = DESKTOP.find((m) => m.id === "brain.work.quiz");
  const place = entryPlace(quiz);
  assert.equal(place.tab, "work");
  assert.equal(place.window, "brain");
  const hardware = DESKTOP.find((m) => m.id === "settings.hardware");
  assert.equal(entryPlace(hardware).window, "settings");
  assert.equal(entryPlace(hardware).tab, "");
});

/* ── 3. The search finds the app's own words ────────────────────────────── */

const top = (query) => {
  const hits = search(ITEMS, query);
  return hits.length ? hits[0].item : null;
};

check("a few letters of a menu's own name find it", () => {
  for (const [query, id] of [
    ["hardware", "settings.hardware"],
    ["backup", "settings.backup"],
    ["what asks", "settings.asks-first"],
    ["reach", "settings.reach"],
    ["animal", "settings.animal-options"],
    ["retirement", "brain.work.retirement"],
    ["undo", "brain.work.undo"],
  ]) {
    const hit = top(query);
    assert.ok(hit, `"${query}" matched nothing at all`);
    assert.equal(hit.id, id, `"${query}" found ${hit.id}, not ${id}`);
  }
});

check("a screen is found by the word the owner would use", () => {
  const memory = top("memory");
  assert.ok(memory, "memory matched nothing");
  assert.ok(["brain.tab.memory", "brain.memory.known", "brain.memory.topics",
    "brain.memory.learning", "brain.memory.auto", "brain.memory.profile",
    "brain.memory.wiki", "brain.memory.deep", "brain.memory.waiting",
    "brain.memory.between-us", "brain.memory.history-import"].includes(memory.id),
  `"memory" found ${memory.id}, which is not a memory screen`);
  const work = top("work");
  assert.equal(work.id, "brain.tab.work", `"work" found ${work.id}`);
});

check("the words Jarvis itself answers to are searchable", () => {
  // The catalogue's aliases are what voice and chat already match, so typing
  // one has to reach the same row here - otherwise the palette is harder to
  // use than asking out loud. (A group may come first when its own name is
  // the better match; what matters is that the menu is reachable at all -
  // "gpu" is an alias of the graphics-cards group as well as of Hardware, so
  // it is deliberately not in this list.)
  for (const [query, id] of [
    ["faq", "settings.faq"],
    ["pairing", "settings.connection"],
    ["themes", "settings.appearance-card"],
    ["quiz", "brain.work.quiz"],
    ["hardware and models", "settings.hardware"],
  ]) {
    const hits = search(ITEMS, query).map((h) => h.item.id);
    assert.ok(hits.includes(id), `"${query}" does not reach ${id} (found ${hits.slice(0, 3).join(", ")})`);
  }
  // ...and an alias that only one row carries does put that row first.
  const second = search(ITEMS, "second gpu").map((h) => h.item.id);
  assert.equal(second[0], "settings.second-card", `"second gpu" found ${second[0]}`);
  // "gpu" belongs to the graphics-cards GROUP in the catalogue (its own
  // `names`), so the group comes first - not the Hardware card, whose
  // description only mentions "the second card" - and the Hardware card is
  // still reachable by its own name.
  const gpu = search(ITEMS, "gpu").map((h) => h.item.id);
  assert.equal(gpu[0], "group.graphics-cards", `"gpu" found ${gpu[0]}`);
  const hardware = search(ITEMS, "hardware and models").map((h) => h.item.id);
  assert.equal(hardware[0], "settings.hardware", `"hardware and models" found ${hardware[0]}`);
});

check("searching is blind to case and punctuation", () => {
  const a = search(ITEMS, "What Asks First?").map((h) => h.item.id);
  const b = search(ITEMS, "what asks first").map((h) => h.item.id);
  assert.deepEqual(a, b);
  assert.ok(a.includes("settings.asks-first"));
});

check("an empty box lists everything; a miss lists nothing", () => {
  assert.equal(search(ITEMS, "").length, ITEMS.length, "the empty box hid rows");
  assert.equal(search(ITEMS, "   ").length, ITEMS.length, "spaces hid every row");
  assert.deepEqual(search(ITEMS, "zzzqqq"), [], "a nonsense word matched something");
});

check("a search that matches nothing has words, not a bare nothing", () => {
  assert.ok(WORDS.none_title.length > 5, "the no-match state has no sentence");
  assert.ok(WORDS.none_body.length > 20, "the no-match state does not say what to do");
  assert.doesNotMatch(WORDS.none_title, /\d/, "the no-match state shows a number");
  assert.doesNotMatch(WORDS.empty_title, /^\s*$/, "the empty state is blank");
  assert.ok(WORDS.empty_body.length > 20, "the empty state does not explain itself");
});

check("the count line reads as a sentence, singular and plural", () => {
  assert.equal(fill(WORDS.all_many, { n: 1 }).includes("1"), true);
  assert.match(WORDS.all_many, /\{n\}/, "the plural line lost its count");
  assert.match(WORDS.opened, /\{n\}/);
  assert.ok(!/\{n\}/.test(fill(WORDS.results_many, { n: 7 })), "a placeholder reached the screen");
  assert.equal(fill(WORDS.results_many, { n: 7 }).includes("7"), true);
});

check("every row can say what it is, in a sentence", () => {
  for (const item of ITEMS) {
    const line = describe(item);
    if (item.kind === "group") {
      assert.match(line, /menus?\./, `${item.title} does not say how many menus it holds`);
    } else {
      assert.ok(item.about.length > 0 || line.length > 0, `${item.id} says nothing about itself`);
    }
    assert.ok(!/\{n\}/.test(line), `${item.id}'s line has a raw placeholder`);
  }
});

check("a hidden menu is still listed, and says so", () => {
  const hidden = buildPalette({ hiddenFor: (id) => id === "settings.faq" });
  const faq = hidden.find((i) => i.id === "settings.faq");
  assert.ok(faq, "a hidden menu vanished from the palette");
  assert.equal(faq.hidden, true);
  assert.match(describe(faq), /hidden/i, "the row does not say it is hidden");
  const shown = buildPalette();
  assert.equal(shown.find((i) => i.id === "settings.faq").hidden, false);
});

/* ── 4. Headings come off the catalogue too ─────────────────────────────── */

check("every row lands under one of the four headings", () => {
  const wanted = new Set(Object.values(WORDS.group_headings));
  for (const item of ITEMS) {
    const heading = headingOf(item);
    assert.ok(wanted.has(heading), `${item.id} has the heading "${heading}"`);
  }
  // The screens heading is for the rail's own tabs, and nothing else.
  for (const item of ITEMS) {
    if (item.kind === "tab") assert.equal(headingOf(item), WORDS.group_headings.screens);
  }
});

/* ── 5. The surface the palette is drawn into ───────────────────────────── */

check("index.html has the palette, and the bar's way in", () => {
  const html = page("index.html");
  for (const id of ["palette", "palette-search", "palette-list", "palette-status",
    "palette-empty", "palette-hint"]) {
    assert.match(html, new RegExp(`id="${id}"`), `index.html has no #${id}`);
  }
  // A live region inside a hidden box announces nothing: the count line has
  // to be OUTSIDE the palette (which is itself hidden when closed), and it
  // must still be in the accessibility tree - so `.sr-only`, never `hidden`.
  const section = html.slice(html.indexOf('id="palette"'), html.indexOf("</section>",
    html.indexOf('id="palette"')));
  const statusAt = html.indexOf('id="palette-status"');
  assert.ok(statusAt > 0, "index.html has no live count line");
  const statusTag = html.slice(html.lastIndexOf("<", statusAt), html.indexOf(">", statusAt) + 1);
  assert.match(statusTag, /aria-live="polite"/, "the count line is not a polite live region");
  assert.match(statusTag, /class="sr-only"/, "the count line is not kept in the tree but out of sight");
  assert.ok(statusAt > html.indexOf("</section>", html.indexOf('id="palette"')),
    "the live region is inside the hidden panel, so it would announce nothing");
  assert.match(section, /id="palette"[^>]*role="dialog"/, "the palette is not a dialog");
  assert.match(section, /aria-modal="true"/, "a modal dialog without aria-modal teaches the wrong model");
  assert.match(section, /aria-labelledby="palette-title"/, "the dialog has no accessible name");
  assert.match(section, /id="palette-search"[\s\S]{0,400}?role="combobox"/,
    "the search field does not say what it is");
  assert.match(section, /id="palette-list"[^>]*role="listbox"/, "the list is not a listbox");
});

check("main.js opens the palette with the mechanisms that were already there", () => {
  const main = page("main.js");
  assert.match(main, /mountPalette\(\{/);
  assert.match(main, /openPlace: openPlaceFromPalette/);
  // The two navigation mechanisms, and no third one: settings by place, the
  // Brain by place. Both already existed for voice and chat.
  const fn = main.slice(main.indexOf("function openPlaceFromPalette"));
  const body = fn.slice(0, fn.indexOf("\n}\n\n/** Paints the three health dots"));
  assert.match(body, /SETTINGS_PLACE_KEY/);
  assert.match(body, /BRAIN_PLACE_KEY/);
  assert.match(body, /invoke\("open_fix_place", \{ place: "settings" \}\)/);
  assert.match(body, /invoke\("open_fix_place", \{ place: "brain" \}\)/);
  const commands = [...body.matchAll(/invoke\("([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(commands)], ["open_fix_place"],
    `the palette asks Rust for more than opening a window: ${commands.join(", ")}`);
});

check("the palette never opens over a waiting approval", () => {
  const main = page("main.js");
  assert.match(main, /canOpen: \(\) => !state\.approval/,
    "the palette can cover the one surface the app stops for");
});

check("the Brain and Settings can be told which place to open", () => {
  // The palette writes the same keys the bar's own "open <a settings
  // section>" and "earlier chats" already write, and both pages already
  // read them; a place this project cannot show would be a row that does
  // nothing.
  assert.match(page("settings.js"), /SETTINGS_PLACE_KEY/);
  assert.match(page("brain.js"), /takeAnyPlace/);
});

if (fails.length) {
  console.log(`\n${fails.length} failed: ${fails.join("; ")}`);
  process.exit(1);
}
console.log(`\n${ITEMS.length} rows, every one from the catalogue, every one opening something real.`);
