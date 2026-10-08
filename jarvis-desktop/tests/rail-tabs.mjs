/**
 * rail-tabs.mjs - the Brain rail's tabs, held to the views behind them.
 *
 * Runs on plain Node with no browser, because the bug this exists for was
 * invisible to every suite that needs one. The Tutorials commit (d41a0de8)
 * added a "Tutorials" entry to `VIEWS` in `brain.js` - the list the keyboard
 * walk, `Home` and `End` all count through - and never added the rail button
 * in `brain.html`. So `End` selected a tab that was not there: `focus()` on
 * `tab-tutorials` found no element and did nothing, the focus stayed where it
 * was, and every real tab was left at `tabindex="-1"`, which leaves the rail
 * with no tab stop at all. `tests/a11y.mjs` catches the behaviour, but only
 * with Playwright installed; this catches the same wiring fault from the
 * text, so it fails on the PC that cannot run the browser suites.
 *
 * A view named in `VIEWS` with no `tab-<key>` button, or a rail button with
 * no view, is the shape to refuse: the two lists are the same list.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(HERE, "..", p), "utf8");

const JS = read("src/brain.js");
const HTML = read("src/brain.html");

const fails = [];
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok    ${name}`);
  } catch (e) {
    fails.push(name);
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
};

/* ── The two lists, read out of the real files ─────────────────────────── */

/** The keys of `const VIEWS = {...}` in brain.js, in the order written. */
function viewOrder() {
  const start = JS.indexOf("const VIEWS = {");
  assert.ok(start > -1, "brain.js has no `const VIEWS = {`");
  const block = JS.slice(start, JS.indexOf("\n};", start));
  const keys = [...block.matchAll(/^ {2}([A-Za-z][A-Za-z0-9]*): \{/gm)].map((m) => m[1]);
  assert.ok(keys.length >= 6, `only ${keys.length} views were read out of VIEWS`);
  assert.equal(new Set(keys).size, keys.length, "a view is named twice in VIEWS");
  return keys;
}

/** The `<li>`s of the rail, in the order they are written. */
function railItems() {
  const at = HTML.indexOf('id="rail-nav"');
  assert.ok(at > -1, "brain.html has no #rail-nav");
  const block = HTML.slice(at, HTML.indexOf("</ul>", at));
  return [...block.matchAll(/<li([^>]*)>([\s\S]*?)<\/li>/g)].map((m) => ({
    hidden: /\bhidden\b/.test(m[1]),
    markup: m[2],
    id: (m[2].match(/id="tab-([A-Za-z0-9]+)"/) || [])[1] || null,
  }));
}

/** `const ADVANCED_VIEWS = [...]` in brain.js. */
function advancedViews() {
  const m = JS.match(/const ADVANCED_VIEWS = \[([^\]]*)\]/);
  assert.ok(m, "brain.js has no ADVANCED_VIEWS");
  return [...m[1].matchAll(/"([A-Za-z0-9]+)"/g)].map((x) => x[1]);
}

/** The view the window opens on, from `const state = { view: "..." }`. */
function opensOn() {
  const m = JS.match(/const state = \{[\s\S]{0,200}?view: "([A-Za-z0-9]+)"/);
  assert.ok(m, "brain.js's state has no starting view");
  return m[1];
}

/** The rail's own keydown handler, as text. */
function railHandler() {
  const at = JS.indexOf('dom.rail?.addEventListener("keydown"');
  assert.ok(at > -1, "brain.js has no keydown listener on the rail");
  const end = JS.indexOf("\n});", at);
  assert.ok(end > at, "the rail's keydown listener has no end");
  return JS.slice(at, end);
}

/** Every `role="tabpanel"` section: its own id, and the tab that names it. */
function panels() {
  return [...HTML.matchAll(/<section[^>]*role="tabpanel"[^>]*>/g)].map((m) => ({
    view: (m[0].match(/id="view-([A-Za-z0-9-]+)"/) || [])[1] || null,
    labelledby: (m[0].match(/aria-labelledby="tab-([A-Za-z0-9-]+)"/) || [])[1] || null,
  }));
}

const VIEWS = viewOrder();
const ITEMS = railItems();
const ADVANCED = advancedViews();
const PANELS = panels();
const OPEN_ON = opensOn();
const RAIL_IDS = ITEMS.map((i) => i.id).filter(Boolean);

/* ── 1. The rail and the views are one list, in one order ─────────────── */

await check("every view has a rail tab, and every rail tab has a view", async () => {
  const missing = VIEWS.filter((k) => !RAIL_IDS.includes(k));
  assert.deepEqual(missing, [],
    `named in brain.js's VIEWS with no tab-<key> button in brain.html: ${missing.join(", ")}` +
    " - the arrow keys and End walk these, so one of them is a tab focus cannot land on");
  const extra = RAIL_IDS.filter((k) => !VIEWS.includes(k));
  assert.deepEqual(extra, [],
    `on the rail with no entry in VIEWS: ${extra.join(", ")} - its panel would never open`);
});

await check("the rail's order and the keyboard's order are the same order", async () => {
  // A different order is not a crash: the arrows would simply jump about the
  // rail instead of walking down it, which is what the pattern is for.
  assert.deepEqual(RAIL_IDS, VIEWS,
    `the rail draws ${RAIL_IDS.join(" > ")} but the arrows walk ${VIEWS.join(" > ")}`);
});

await check("every tab names its own panel, and the panel names it back", async () => {
  for (const key of VIEWS) {
    const item = ITEMS.find((i) => i.id === key);
    assert.ok(item, `tab-${key} is not on the rail, so there is nothing to point at view-${key}`);
    assert.match(item.markup, new RegExp(`aria-controls="view-${key}"`),
      `tab-${key} does not point at view-${key}`);
    assert.match(item.markup, new RegExp(`data-goto="${key}"`),
      `tab-${key}'s click has no data-goto (the other tabs have one)`);
    const panel = PANELS.find((p) => p.view === key);
    assert.ok(panel, `tab-${key} points at view-${key}, which is not on the page`);
    assert.equal(panel.labelledby, key,
      `view-${key} is not labelled by tab-${key}`);
  }
  const orphans = PANELS.map((p) => p.view).filter((v) => v && !VIEWS.includes(v));
  assert.deepEqual(orphans, [], `panels nothing can open: ${orphans.join(", ")}`);
});

await check("every tab says its name in words", async () => {
  for (const key of VIEWS) {
    const item = ITEMS.find((i) => i.id === key);
    assert.ok(item, `tab-${key} is not on the rail`);
    const label = (item.markup.match(/<span class="rail-label">([^<]*)<\/span>/) || [])[1];
    assert.ok(label && label.trim().length > 1, `tab-${key} has no readable name`);
  }
});

/* ── 2. The roving half: exactly one tab stop, and it is the open view ── */

await check("the markup starts with exactly one tab stop, on the tab the window opens on", async () => {
  assert.ok(VIEWS.includes(OPEN_ON),
    `brain.js opens on "${OPEN_ON}", which is not a view - there would be no tab stop at all`);
  const stops = ITEMS.filter((i) => /tabindex="0"/.test(i.markup)).map((i) => i.id);
  assert.deepEqual(stops, [OPEN_ON],
    `${stops.length} tabs start in the tab order (${stops.join(", ")}); a tablist has exactly one,` +
    ` and it is the view the window opens on (${OPEN_ON})`);
  for (const key of VIEWS.filter((k) => k !== OPEN_ON)) {
    const item = ITEMS.find((i) => i.id === key);
    assert.ok(item, `tab-${key} is not on the rail, so it has no tab order to be in`);
    assert.match(item.markup, /tabindex="-1"/, `tab-${key} is a second tab stop`);
  }
});

await check("the tab the window opens on is the selected one", async () => {
  const selected = ITEMS.filter((i) => /aria-selected="true"/.test(i.markup)).map((i) => i.id);
  assert.deepEqual(selected, [OPEN_ON],
    `aria-selected is on ${selected.join(", ") || "nothing"}, not on ${OPEN_ON}`);
});

/* ── 3. Advanced is a disclosure over the rail, not a second rail ─────── */

await check("only the Advanced views start hidden, and they are the ones hidden", async () => {
  const hidden = ITEMS.filter((i) => i.hidden).map((i) => i.id);
  assert.deepEqual(hidden.slice().sort(), ADVANCED.slice().sort(),
    `hidden at load: ${hidden.join(", ") || "nothing"}; ADVANCED_VIEWS is ${ADVANCED.join(", ")}`);
});

/* ── 4. The keyboard half is still the handler this all rests on ──────── */

await check("the rail's keydown handler moves on the arrows and on Home/End", async () => {
  const handler = railHandler();
  // STEP names the arrows without quotes; Home and End are compared to event.key.
  for (const key of ["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"]) {
    assert.ok(handler.includes(`${key}:`), `the rail's handler ignores ${key}`);
  }
  for (const key of ["Home", "End"]) {
    assert.ok(handler.includes(`"${key}"`), `the rail's handler ignores ${key}`);
  }
  assert.match(handler, /preventDefault\(\)/,
    "the arrows must not also scroll the page");
  assert.match(handler, /order\.length - 1/,
    "End no longer means the last tab on the rail");
  assert.match(handler, /showView\(order\[next\]\)/,
    "the arrows must open the view they move to (selection follows focus here)");
  assert.match(handler, /\.focus\(\)/,
    "the arrows must move the focus as well as the selection");
});

await check("clicking a rail tab is wired from the same list, not one id at a time", async () => {
  // The click wiring is a loop over the same VIEWS list; a tab added to the
  // rail by hand still needs the entry there to be clickable at all.
  assert.match(JS, /for \(const key of TAB_ORDER\) \{[\s\S]{0,120}?tab-\$\{key\}/,
    "the rail's click wiring no longer loops over the views");
});

/* ── 5. The tab this file was written for ─────────────────────────────── */

await check("Tutorials and the FAQ is on the rail, wired like its siblings", async () => {
  assert.ok(VIEWS.includes("tutorials"), "tutorials is not a view in brain.js");
  const item = ITEMS.find((i) => i.id === "tutorials");
  assert.ok(item, "tab-tutorials is missing from the rail");
  // The label names both halves since 2026-10-08 (PR #108's own retitle): the
  // desktop's FAQ moved into this tab, so it is no longer only tutorials.
  assert.match(item.markup, /<span class="rail-label">Tutorials and the FAQ<\/span>/);
  assert.match(item.markup, /role="tab"/);
  assert.equal(item.hidden, false,
    "Tutorials and the FAQ is an everyday tab, not one of the four behind Advanced");
  // Everyday tabs are drawn above the hidden group, so this one is too.
  const here = ITEMS.indexOf(item);
  const advancedAt = ITEMS.map((i, n) => (ADVANCED.includes(i.id) ? n : -1)).filter((n) => n > -1);
  assert.ok(here > ITEMS.findIndex((i) => i.id === "projects") && here < Math.min(...advancedAt),
    "Tutorials and the FAQ belongs with the everyday tabs, above the Advanced group");
  assert.match(JS, /case "tutorials":[\s\S]{0,600}?showTutorials\(\$\("tutorials-root"\)\)/,
    "the tutorials view is on the rail but nothing draws it");
  // One Help place: the tab is also where Help goes, so the view must be
  // openable by name (the palette writes exactly this string).
  assert.match(JS, /TUTORIALS_PLACE/, "brain.js no longer names the Help place");
  assert.match(HTML, /id="open-features"/,
    "the Help tab no longer draws the button that moved there with the FAQ");
});

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
} else {
  console.log("\nThe rail and its views are one list.");
}
