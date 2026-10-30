/**
 * home-cards.mjs - the main screen's feature cards (the owner's requirement of
 * 2026-10-29: add, remove and reorder the features on the main screen from
 * Edit HUD, and have the phone draw the same choice).
 *
 *     node tests/home-cards.mjs
 *
 * WHY THIS SUITE EXISTS, AND WHY IT NEEDS NO BROWSER. `src/home-cards.js` is the
 * data half of the feature: the catalogue, the closed-world normalizer, the one
 * reducer every input calls, and the three states a card can be drawn in. None
 * of it touches the DOM, so it is all tested here as plain functions. The
 * editor and the main screen are covered by tests/hud.mjs and by the page's own
 * `home-cards` probe.
 *
 * WHAT IT PROVES, in order:
 *   1. every catalogue row is sane - unique key, plain words, a real size, a
 *      minimum no bigger than the size it is added at, an `opens` this build
 *      knows - and every key is a REAL feature, i.e. an id in
 *      `features/features.json`, with an app list its `surface` allows. That is
 *      what stops a card naming a feature that does not exist;
 *   2. no safety surface is a card: the approvals queue, Stop everything, app
 *      lock, "What asks first" and the stale-link warning have no key in the
 *      catalogue at all, so no document can add, remove or reorder them;
 *   3. the default document is the four the design ships, and it is a fixed
 *      point of the normalizer (save-then-load cannot rewrite it);
 *   4. a hostile or just-wrong document is made safe: unknown keys, prototype
 *      keys and duplicates dropped, bounded numbers repaired, wrong version
 *      replaced by the default rather than guessed at;
 *   5. add / remove / move / switch-off each go through ONE reducer, are
 *      idempotent where they should be, refuse with a plain sentence where they
 *      must, and never mutate the document they were given;
 *   6. the off state is never blank and never JSON: `off` and `missing` are
 *      whole sentences, and "not asked" is drawn as a normal card;
 *   7. THE PROBE THE BRIEF ASKS FOR: a brand-new feature key - `health` - can be
 *      added by ONE catalogue row and then appears in the catalogue, can be put
 *      on the main screen, comes back out in order, and reports its own off
 *      state. The row is spliced into a COPY of the module and imported, so the
 *      check really runs the production code path and cannot pass by accident;
 *      the shipped module is asserted to still NOT have `health`, which is what
 *      makes the probe meaningful.
 */

import assert from "node:assert/strict";
import { readFileSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as H from "../src/hud-edit.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src", "hud-edit.js");
const FEATURES = JSON.parse(
  readFileSync(join(HERE, "..", "src", "features.json"), "utf8"),
);
const FEATURE_BY_ID = new Map(FEATURES.map((entry) => [entry.id, entry]));

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

const keys = new Set(H.HOME_CARDS.map((card) => card.key));
const SIZES = new Set(Object.keys(H.HOME_SIZES));
const OPENS = new Set(H.OPENS);

/** A catalogue entry's problems, in plain words ("" when it has none). */
function entryProblem(card) {
  if (!card.key) return "no key";
  if (!/^[a-z0-9][a-z0-9-]*$/.test(card.key)) return `${card.key}: key is not kebab-case`;
  if (!card.label || !card.label.trim()) return `${card.key}: no label`;
  if (!card.about || !card.about.trim()) return `${card.key}: no about`;
  if (!Array.isArray(card.apps) || !card.apps.length) return `${card.key}: no apps`;
  for (const app of card.apps) {
    if (app !== "desktop" && app !== "phone") return `${card.key}: unknown app ${app}`;
  }
  if (typeof card.default_on !== "boolean") return `${card.key}: default_on is not a boolean`;
  if (!SIZES.has(card.size)) return `${card.key}: size ${card.size} is not one of S/M/L/T`;
  if (!SIZES.has(card.min_size)) return `${card.key}: min_size ${card.min_size} is not a size`;
  if (H.SIZE_ORDER.indexOf(card.min_size) > H.SIZE_ORDER.indexOf(card.size)) {
    return `${card.key}: min_size is bigger than the size it is added at`;
  }
  if (!OPENS.has(card.opens)) return `${card.key}: opens ${card.opens} is not a known place`;
  return "";
}

/* ── 1. The catalogue ────────────────────────────────────────────────────── */

await check("there is one catalogue row per card, with unique keys", () => {
  assert.equal(keys.size, H.HOME_CARDS.length, "two cards share a key");
  assert.ok(H.HOME_CARDS.length >= 20, `only ${H.HOME_CARDS.length} cards in the catalogue`);
  assert.ok(H.HOME_CARDS.length <= H.MAX_HOME_CARDS);
});

await check("every row is sane and every size/minimum pair is coherent", () => {
  for (const card of H.HOME_CARDS) {
    assert.equal(entryProblem(card), "", entryProblem(card));
  }
});

await check("every key is a real feature, allowed on the apps it claims", () => {
  for (const card of H.HOME_CARDS) {
    const feature = FEATURE_BY_ID.get(card.key);
    assert.ok(feature, `${card.key} is not an id in features/features.json`);
    // `feature` is what the card reports the on/off state of; it must be the
    // same feature or one this app really has.
    if (card.feature !== null) {
      assert.ok(FEATURE_BY_ID.has(card.feature),
        `${card.key}: feature ${card.feature} is not in features.json`);
    }
    const surface = feature.surface;
    for (const app of card.apps) {
      const allowed = surface === "both" || surface === app;
      assert.ok(allowed,
        `${card.key}: features.json says surface ${surface}, card claims ${app}`);
    }
  }
});

await check("no safety surface is a card", () => {
  for (const key of ["approvals", "stop-everything", "app-lock", "what-asks-first",
    "stale-link", "captcha-handoff", "trust", "rush-latch", "outside-text"]) {
    assert.equal(H.homeCard(key), null,
      `${key} is a safety surface and must not be a main-screen card`);
  }
});

await check("calendar is desktop-only and the rest are on both apps", () => {
  assert.deepEqual(H.homeCard("calendar").apps, ["desktop"]);
  for (const card of H.HOME_CARDS) {
    if (card.key === "calendar") continue;
    assert.deepEqual(card.apps, ["desktop", "phone"], card.key);
  }
});

await check("the catalogue is frozen: an editor cannot rewrite it", () => {
  assert.throws(() => { H.HOME_CARDS.push({ key: "nope" }); });
  assert.throws(() => { H.HOME_CARDS[0].label = "Changed"; });
  assert.throws(() => { H.HOME_CARDS[0].apps.push("phone"); });
});

/* ── 2. The default document ─────────────────────────────────────────────── */

await check("the default document is the four the design ships, in order", () => {
  const doc = H.defaultHomeCards();
  assert.equal(doc.version, H.HOME_CARDS_VERSION);
  assert.deepEqual(doc.cards.map((entry) => entry.key),
    ["today", "coming-up", "now", "settings-entry"]);
  assert.ok(doc.cards.every((entry) => entry.on === true && typeof entry.order === "number"));
  assert.ok(H.isDefaultHomeCards(doc));
});

await check("the default document is a fixed point of the normalizer", () => {
  const once = H.normalizeHomeCards(H.defaultHomeCards());
  const twice = H.normalizeHomeCards(JSON.parse(JSON.stringify(once)));
  assert.deepEqual(twice, once);
  // Every catalogue card on is also a fixed point: save-then-load never
  // rewrites the order the owner chose.
  const all = { version: 1, cards: H.HOME_CARDS.map((card, index) => ({
    key: card.key, on: true, order: index })) };
  assert.deepEqual(H.normalizeHomeCards(H.normalizeHomeCards(all)), H.normalizeHomeCards(all));
});

await check("one id is one card: homeCardsFor filters by app and by folded, in order", () => {
  const doc = { version: 1, cards: [
    { key: "calendar", on: true, order: 0 },
    { key: "today", on: true, order: 1 },
    { key: "pictures", on: false, order: 2 },
  ] };
  // `pictures` is folded away (`on: false`): it stays in the document, but the
  // main strip does not draw it. Before 2026-10-30 this list still held it, so
  // "Pictures is folded away." was said while the card was on the screen.
  assert.deepEqual(H.homeCardsFor(doc, "desktop").map((entry) => entry.key),
    ["calendar", "today"]);
  // A phone cannot draw the calendar, so it is not in the phone's list at all -
  // that is the difference between "removed" and "not on this app".
  assert.deepEqual(H.homeCardsFor(doc, "phone").map((entry) => entry.key),
    ["today"]);
  assert.deepEqual(H.cardsOnlyOnOtherApp(doc, "phone").map((card) => card.key),
    ["calendar"]);
  assert.deepEqual(H.missingHomeCards(doc, "desktop").map((card) => card.key),
    H.catalogueFor("desktop").filter((card) => !["calendar", "today", "pictures"].includes(card.key))
      .map((card) => card.key));
});

/* ── 3. The normalizer: a wrong document becomes a safe one ──────────────── */

await check("unknown keys, prototype keys and duplicates are dropped", () => {
  const doc = H.normalizeHomeCards({
    version: 1,
    cards: [
      { key: "today", on: true, order: 0 },
      { key: "today", on: false, order: 1 },          // duplicate keeps its first place
      { key: "outside-text", on: true, order: 2 },    // a safety surface is not a card
      { key: "not-a-feature", on: true, order: 3 },
      { key: "__proto__", on: true, order: 4 },
      { key: "constructor", on: true, order: 5 },
      { nope: true },
      "today",
      null,
      { key: "pictures", on: "yes", order: 99 },
    ],
  });
  assert.deepEqual(doc.cards.map((entry) => entry.key), ["today", "pictures"]);
  assert.equal(doc.cards[0].on, true);
  // `on: "yes"` is not a boolean, so it is not trusted: the entry is drawn.
  assert.equal(doc.cards[1].on, true);
  // order is re-numbered contiguously, so a document cannot smuggle 99 in.
  assert.deepEqual(doc.cards.map((entry) => entry.order), [0, 1]);
  assert.equal(Object.prototype.hasOwnProperty.call(doc.cards, "__proto__"), false);
});

await check("a wrong or missing version is the default, never guessed at", () => {
  assert.deepEqual(H.normalizeHomeCards({ version: 2, cards: [] }), H.defaultHomeCards());
  assert.deepEqual(H.normalizeHomeCards({ cards: [] }), H.defaultHomeCards());
  assert.deepEqual(H.normalizeHomeCards("hello"), H.defaultHomeCards());
  assert.deepEqual(H.normalizeHomeCards(null), H.defaultHomeCards());
  assert.deepEqual(H.normalizeHomeCards([]), H.defaultHomeCards());
});

await check("an empty list is a real choice, not a corrupt document", () => {
  const empty = H.normalizeHomeCards({ version: 1, cards: [] });
  assert.deepEqual(empty.cards, []);
  assert.equal(H.describeHomeCards(empty), "The main screen has no feature cards.");
});

/* ── 4. The one reducer ──────────────────────────────────────────────────── */

await check("Add puts a card on the main screen and it appears in order", () => {
  const before = H.defaultHomeCards();
  const frozen = JSON.stringify(before);
  const result = H.applyHomeAction(before, { type: "addCard", key: "pictures" });
  assert.equal(result.changed, true);
  assert.equal(result.refused, false);
  assert.equal(result.note, "Pictures is on the main screen.");
  assert.deepEqual(result.doc.cards.map((entry) => entry.key),
    ["today", "coming-up", "now", "settings-entry", "pictures"]);
  assert.equal(JSON.stringify(before), frozen, "the reducer mutated its input");
  // Adding at an index puts it exactly there.
  const atFront = H.applyHomeAction(before, { type: "addCard", key: "pictures", index: 0 });
  assert.equal(atFront.doc.cards[0].key, "pictures");
});

await check("Add refuses a card already there, and one that is not a feature", () => {
  const doc = H.defaultHomeCards();
  const again = H.applyHomeAction(doc, { type: "addCard", key: "today" });
  assert.equal(again.changed, false);
  assert.equal(again.refused, true);
  assert.equal(again.note, "Today is already on the main screen.");
  assert.deepEqual(again.doc, H.normalizeHomeCards(doc));

  const bogus = H.applyHomeAction(doc, { type: "addCard", key: "not-a-feature" });
  assert.equal(bogus.refused, true);
  assert.equal(bogus.note, "That is not a feature this HUD can put on the main screen.");
  // A safety surface is refused by the same door, with the same words.
  assert.equal(H.applyHomeAction(doc, { type: "addCard", key: "approvals" }).refused, true);
});

await check("Remove takes one off, and a second Remove is refused, not silent", () => {
  const doc = H.applyHomeAction(H.defaultHomeCards(), { type: "addCard", key: "quiz" }).doc;
  const gone = H.applyHomeAction(doc, { type: "removeCard", key: "quiz" });
  assert.equal(gone.changed, true);
  assert.equal(gone.note, "Quiz me on a text is off the main screen.");
  assert.deepEqual(gone.doc.cards.map((entry) => entry.key),
    ["today", "coming-up", "now", "settings-entry"]);
  const twice = H.applyHomeAction(gone.doc, { type: "removeCard", key: "quiz" });
  assert.equal(twice.changed, false);
  assert.equal(twice.refused, true);
  assert.equal(twice.note, "Quiz me on a text is not on the main screen.");
  // Removing the last one is allowed: an empty main screen is a choice.
  let empty = H.normalizeHomeCards({ version: 1, cards: [] });
  assert.equal(H.applyHomeAction(empty, { type: "removeCard", key: "today" }).refused, true);
});

await check("Move reorders by one place or to an index, and a no-op is not an edit", () => {
  const doc = H.defaultHomeCards();
  const moved = H.applyHomeAction(doc, { type: "moveCard", key: "now", delta: -1 });
  assert.equal(moved.changed, true);
  assert.deepEqual(moved.doc.cards.map((entry) => entry.key),
    ["today", "now", "coming-up", "settings-entry"]);
  assert.equal(moved.note, "Right now moved up.");

  const toIndex = H.applyHomeAction(doc, { type: "moveCard", key: "today", index: 3 });
  assert.deepEqual(toIndex.doc.cards.map((entry) => entry.key),
    ["coming-up", "now", "settings-entry", "today"]);

  const still = H.applyHomeAction(doc, { type: "moveCard", key: "today", delta: -1 });
  assert.equal(still.changed, false);
  assert.equal(still.refused, false);
  assert.equal(still.note, "");
  // Out-of-range moves clamp instead of throwing.
  assert.deepEqual(
    H.applyHomeAction(doc, { type: "moveCard", key: "today", delta: -99 }).doc.cards[0].key,
    "today");
  assert.equal(
    H.applyHomeAction(doc, { type: "moveCard", key: "settings-entry", delta: 99 })
      .doc.cards[3].key, "settings-entry");
  // One place up from the top, and one down from the bottom, do nothing.
  assert.equal(H.applyHomeAction(doc, { type: "moveCard", key: "coming-up", index: 0 })
    .changed, true);
  assert.equal(H.applyHomeAction(doc, { type: "moveCard", key: "approvals", delta: 1 })
    .refused, true);
});

await check("Switch a card's tile on and off without removing it", () => {
  const doc = H.defaultHomeCards();
  const off = H.applyHomeAction(doc, { type: "setCardOn", key: "today", on: false });
  assert.equal(off.changed, true);
  assert.equal(off.doc.cards[0].on, false);
  assert.equal(off.doc.cards[0].key, "today", "switching off must not remove the card");
  assert.equal(off.note, "Today is folded away.");
  assert.equal(H.applyHomeAction(off.doc, { type: "setCardOn", key: "today", on: false })
    .changed, false);
  assert.equal(H.applyHomeAction(doc, { type: "setCardOn", key: "today" }).doc.cards[0].on,
    false, "no value means flip");
  assert.equal(H.applyHomeAction(doc, { type: "setCardOn", key: "wiki" }).refused, true);
});

await check("folding a card away takes it off the strip, and the editor keeps it", () => {
  // THE REGRESSION (2026-10-30 feature audit, HIGH): the note said "folded
  // away" while `homeCardsFor` still returned the card, so the main screen drew
  // it anyway. Drive the real reducer and the real list, as the audit did.
  const doc = H.defaultHomeCards();
  const answer = H.applyHomeAction(doc, { type: "setCardOn", key: "today", on: false });
  assert.equal(answer.note, "Today is folded away.");
  assert.deepEqual(H.homeCardsFor(answer.doc, "desktop").map((entry) => entry.key),
    ["coming-up", "now", "settings-entry"]);
  // The card is still in the document, so the editor's own list can draw it
  // again - folding must never be a quiet delete.
  assert.deepEqual(H.normalizeHomeCards(answer.doc).cards.map((entry) => entry.key),
    ["today", "coming-up", "now", "settings-entry"]);
  assert.deepEqual(H.missingHomeCards(answer.doc, "desktop").map((card) => card.key),
    H.catalogueFor("desktop").filter((card) =>
      !["today", "coming-up", "now", "settings-entry"].includes(card.key))
      .map((card) => card.key),
    "a folded card is on the main screen, so it must not be offered as missing");
  // Unfolding brings it back where it was, not at the end.
  const back = H.applyHomeAction(answer.doc, { type: "setCardOn", key: "today", on: true });
  assert.equal(back.note, "Today is drawn.");
  assert.deepEqual(H.homeCardsFor(back.doc, "desktop").map((entry) => entry.key),
    ["today", "coming-up", "now", "settings-entry"]);
  // Folding every card is allowed: an empty strip is a real choice.
  let empty = H.defaultHomeCards();
  for (const entry of empty.cards) {
    empty = H.applyHomeAction(empty, { type: "setCardOn", key: entry.key, on: false }).doc;
  }
  assert.deepEqual(H.homeCardsFor(empty, "desktop"), []);
});

await check("Reset returns the usual four, and says so when there is nothing to do", () => {
  const doc = H.applyHomeAction(H.defaultHomeCards(), { type: "addCard", key: "decks" }).doc;
  const reset = H.applyHomeAction(doc, { type: "resetHome" });
  assert.equal(reset.changed, true);
  assert.deepEqual(reset.doc, H.defaultHomeCards());
  assert.equal(reset.note, "Back to the usual four cards.");
  const again = H.applyHomeAction(reset.doc, { type: "resetHome" });
  assert.equal(again.changed, false);
  assert.equal(again.note, "That is already the usual set.");
});

await check("an unknown action is refused with a plain sentence", () => {
  const bad = H.applyHomeAction(H.defaultHomeCards(), { type: "explode" });
  assert.equal(bad.refused, true);
  assert.equal(bad.note, "That is not an edit this HUD knows.");
  assert.equal(H.applyHomeAction(H.defaultHomeCards(), null).refused, true);
});

await check("every reducer answer is a fixed point (save-then-load is safe)", () => {
  const doc = H.defaultHomeCards();
  for (const action of [
    { type: "addCard", key: "galaxy" },
    { type: "moveCard", key: "galaxy", delta: -2 },
    { type: "setCardOn", key: "today", on: false },
    { type: "removeCard", key: "now" },
    { type: "resetHome" },
  ]) {
    const answer = H.applyHomeAction(doc, action).doc;
    assert.deepEqual(H.normalizeHomeCards(JSON.parse(JSON.stringify(answer))), answer,
      `${action.type} is not a fixed point`);
  }
});

/* ── 5. The off state ────────────────────────────────────────────────────── */

await check("the off state is whole plain sentences, never blank and never JSON", () => {
  const card = H.homeCard("calendar");
  assert.equal(H.stateWords(card, "off"),
    "Calendar is turned off. Turn it on in Settings.");
  assert.equal(H.stateWords(card, "missing"), "Calendar is not on this PC yet.");
  assert.equal(H.stateWords(card, "on"), card.about);
  for (const state of ["on", "off", "missing"]) {
    const words = H.stateWords(card, state);
    assert.ok(words && words.length > 10, `${state} is blank`);
    assert.ok(!words.includes("{") && !words.includes("}"), `${state} looks like JSON`);
  }
  // An unknown card still says something true.
  assert.equal(H.stateWords(null, "off"),
    "This card is turned off. Turn it on in Settings.");
});

await check("'not asked' is drawn as a card, because unchecked is not off", () => {
  assert.equal(H.cardState("today", null), "on");
  assert.equal(H.cardState("today", {}), "on");
  assert.equal(H.cardState("today", { today: "maybe" }), "on");
  assert.equal(H.cardState("today", { today: "on" }), "on");
  assert.equal(H.cardState("today", { today: "off" }), "off");
  assert.equal(H.cardState("today", { today: "missing" }), "missing");
});

/* ── 6. The document as text ─────────────────────────────────────────────── */

await check("the document round-trips through JSON, and a bad paste is null", () => {
  const doc = H.applyHomeAction(H.defaultHomeCards(), { type: "addCard", key: "wiki" }).doc;
  const text = H.homeCardsJson(doc);
  assert.deepEqual(H.parseHomeCards(text), doc);
  assert.equal(H.parseHomeCards("{"), null);
  assert.equal(H.parseHomeCards("[]"), null);
  assert.equal(H.parseHomeCards(""), null);
  assert.equal(H.parseHomeCards(null), null);
  // The rows the phone reads carry no functions and no Map.
  const rows = H.catalogueRows();
  assert.equal(rows.length, H.HOME_CARDS.length);
  assert.deepEqual(Object.keys(rows[0]).sort(),
    ["about", "apps", "default_on", "feature", "key", "label", "min_size", "opens", "size"]);
  assert.equal(JSON.parse(JSON.stringify(rows)).length, rows.length);
});

/* ── 7. THE PROBE: a brand-new feature can become a card ─────────────────── */

await check("a new feature key can be added by one catalogue row and it appears", async () => {
  // The shipped module must NOT have it, or the probe proves nothing.
  assert.equal(H.homeCard("health"), null,
    "the probe needs a key the shipped catalogue does not have");

  // Splice ONE catalogue row into a copy of the module, exactly as the design's
  // recipe says an owner's new feature lands, and import that copy. The copy
  // imports nothing, so it runs on its own.
  const source = readFileSync(SRC, "utf8");
  const anchor = "export const HOME_CARDS = Object.freeze([";
  assert.ok(source.includes(anchor), "hud-edit.js no longer declares HOME_CARDS this way");
  const row = `
  {
    key: "health",
    label: "Health",
    about: "Your own health numbers, and what they are doing.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:main",
    feature: "crisis-help",
  },`;
  const patched = source.replace(anchor, `${anchor}${row}`);
  assert.notEqual(patched, source, "the splice changed nothing");
  // The copy is written BESIDE hud-edit.js, because that module imports its
  // neighbours by relative path; a copy in the system temp folder would not
  // resolve them. It is removed again whatever happens below.
  const here = dirname(fileURLToPath(import.meta.url));
  const file = join(here, "..", "src", `.home-cards-probe-${process.pid}.mjs`);
  writeFileSync(file, patched, "utf8");
  let probe;
  try {
    probe = await import(`file://${file.replace(/\\/g, "/")}?v=${Date.now()}`);
  } finally {
    rmSync(file, { force: true });
  }

  // 1. it is in the catalogue, sane, and on both apps' lists;
  const added = probe.homeCard("health");
  assert.ok(added, "the new key is not in the catalogue after one row");
  assert.equal(added.label, "Health");
  assert.equal(entryProblem(added), "");
  for (const app of ["desktop", "phone"]) {
    assert.ok(probe.catalogueFor(app).some((card) => card.key === "health"),
      `health is missing from the ${app} catalogue`);
  }
  assert.ok(probe.catalogueRows().some((row) => row.key === "health"));
  assert.equal(probe.defaultHomeCards().cards.some((entry) => entry.key === "health"),
    false, "a default-off card must not appear in the default document");

  // 2. it can be put on the main screen, through the same one reducer;
  const before = probe.defaultHomeCards();
  const answer = probe.applyHomeAction(before, { type: "addCard", key: "health" });
  assert.equal(answer.changed, true);
  assert.equal(answer.note, "Health is on the main screen.");

  // 3. it comes back out in order, on both apps, with its own card row;
  const onDesk = probe.homeCardsFor(answer.doc, "desktop");
  const onPhone = probe.homeCardsFor(answer.doc, "phone");
  assert.equal(onDesk[onDesk.length - 1].key, "health");
  assert.equal(onPhone[onPhone.length - 1].key, "health");
  assert.equal(onDesk[onDesk.length - 1].card.label, "Health");
  assert.equal(probe.homeCardsFor(answer.doc, "desktop").length, 5);

  // 4. and it reports a plain off state rather than drawing blank;
  assert.equal(probe.stateWords(added, "missing"), "Health is not on this PC yet.");
  assert.equal(probe.stateWords(added, "off"),
    "Health is turned off. Turn it on in Settings.");
  assert.equal(probe.cardState("health", { health: "missing" }), "missing");

  // 5. it can be reordered and removed by the same doors as any other card;
  assert.equal(probe.applyHomeAction(answer.doc, { type: "moveCard", key: "health", delta: -1 })
    .changed, true);
  assert.equal(probe.applyHomeAction(answer.doc, { type: "removeCard", key: "health" })
    .doc.cards.some((entry) => entry.key === "health"), false);
});

if (fails.length) {
  console.error(`\n${fails.length} test(s) failed`);
  process.exit(1);
} else {
  console.log("\nAll home-cards tests passed!");
}
