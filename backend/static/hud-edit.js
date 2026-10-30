/**
 * hud-edit.js - "Edit HUD" mode for the desktop HUD (H2 of the editable-HUD
 * design, 2026-10-21; rulings 23-27 in
 * `rulings_r1_r7_reminders_and_editable_hud_2026_10_21.md`).
 *
 * WHAT IT IS. The H1 module (`hud-layout.js`) owns the DATA - the card
 * registry, the seven presets, the closed-world normalizer, the protected-card
 * rule. This module owns the EDITOR: the pure reducer every input calls, the
 * pointer-event drag, and the card toolbars/region rendering. It is imported
 * by the HUD page as an external module (the page's inline-script count does
 * not change and its CSP stays as it was).
 *
 * THE ONE RULE. Drag, click buttons, keyboard shortcuts and undo all call the
 * SAME `applyAction`. There is no second mutation path, which is what makes
 * the WCAG 2.2 SC 2.5.7 claim mechanical instead of a promise. Every returned
 * layout has been through H1's `normalizeLayout`, so the protected cards are
 * present and visible, orders are canonical, and save-then-load cannot rewrite
 * the result.
 *
 * SINCE 2026-10-29 IT ALSO OWNS THE MAIN SCREEN'S FEATURE CARDS. That is a
 * DIFFERENT question from the layout: `hud-layout.js` arranges the HUD's own
 * panels, while the catalogue in section 0 chooses which JARVIS FEATURES are
 * drawn on the main screen and in what order (the owner's requirement of that
 * day). It lives here, not in its own served file, because the page's closed
 * whitelist would need five lists in five files before a browser could fetch
 * one; see section 0's banner for the whole reason.
 *
 * WHAT H2 EDITS (honest scope, said in the page's own words too). The cards
 * whose DOM is a self-contained section - the six Bento inspector cards, the
 * three left-rail panels, the approvals queue and (when the shell creates it)
 * the Jarvis-bar button - can move between three regions (left rail, stage
 * top, right rail), resize S/M/L/Tall, collapse and (except protected) hide.
 * The MAIN STAGE (conversation, the Galaxy view, the composer and the stage
 * tabs) is the stage: its registry rows still round-trip, but H2 does not
 * reparent the live stage, so its toolbar explains that instead of pretending
 * a move happened. Stage-card editing is H3/H4 territory.
 */

import {
  CARD_REGISTRY,
  REGIONS,
  PRESETS,
  cardRow,
  describeLayout,
  effectiveCollapsed,
  isUserLayout,
  normalizeLayout,
  presetInfo,
  presetLayout,
  userLayouts,
} from "./hud-layout.js";
import { loadLayout, saveLayout } from "./hud-layout-store.js";
import { ensureCustomCopy } from "./hud-presets.js";

/* =========================================================================
 * 0. The main-screen feature catalogue (the owner's requirement, 2026-10-29)
 *
 * WHY THIS LIVES IN THIS MODULE RATHER THAN ITS OWN FILE. The page imports
 * exactly the modules the backend's closed whitelist serves, and adding a new
 * served file means five lists in five files (the whitelist, both SHIPPED
 * lists, the re-take rule's BESIDE table and the deploy copy) before a browser
 * can fetch it. The catalogue is the editor's own data - Edit HUD is the only
 * thing that writes it - so it belongs beside the editor instead, and this
 * module is already served, already twinned and already imported by the page.
 *
 * WHAT IT IS. One entry per FEATURE that may be a card on the HUD's main
 * screen. The keys are `features/features.json`'s own ids, so a card can never
 * name a feature that does not exist. The safety surfaces (approvals, Stop
 * everything, app lock, What asks first, the stale link) are deliberately NOT
 * in the catalogue: ruling 25 says a layout may never hide or move the one
 * surface a pending approval must reach, and keeping them out of the data makes
 * that a property rather than a check somebody could forget.
 *
 * THE THREE DOORS ARE ONE REDUCER. `applyHomeAction` is the only way the
 * main-screen document changes - the Add button, the Remove button, the arrow
 * keys, the reset and the tests all call it.
 * ========================================================================= */

/** The version of the document shape this build reads and writes. */
export const HOME_CARDS_VERSION = 1;

/** The most cards the main screen may hold: the catalogue's own size. */
export const MAX_HOME_CARDS = 24;

/**
 * The editor's four sizes, in the desktop grid's columns. `min_size` is the
 * smallest an owner may shrink a card to; on the phone `S` and `M` mean one
 * column and `L`/`T` mean full width.
 */
export const HOME_SIZES = Object.freeze({
  S: Object.freeze({ key: "S", label: "Small", col_span: 4, row_span: 1 }),
  M: Object.freeze({ key: "M", label: "Medium", col_span: 6, row_span: 1 }),
  L: Object.freeze({ key: "L", label: "Wide", col_span: 12, row_span: 1 }),
  T: Object.freeze({ key: "T", label: "Tall", col_span: 12, row_span: 2 }),
});

/** The size order, smallest first - the only sizes a document may name. */
export const SIZE_ORDER = Object.freeze(["S", "M", "L", "T"]);

/**
 * Where a card opens. The vocabulary is deliberately tiny and is translated by
 * each app: `stage:<tab>` is one of the HUD's stage tabs, `settings:<section>`
 * is one of the Settings page's own sections, and the phone reads both with its
 * own existing navigation. A card whose `opens` this build does not know is
 * still drawn - it just opens nothing, which is honest.
 */
export const OPENS = Object.freeze([
  "stage:today",
  "stage:reminders",
  "stage:galaxy",
  "stage:memory",
  "stage:telemetry",
  "settings:today",
  "settings:memory",
  "settings:pictures",
  "settings:voice",
  "settings:models",
  "settings:hardware",
  "settings:spending",
  "settings:retirement",
  "settings:projects",
  "settings:learning",
  "settings:topics",
  "settings:wiki",
  "settings:quiz",
  "settings:decks",
  "settings:focus",
  "settings:skills",
  "settings:calendar",
  "settings:briefing",
  "settings:compute",
  "settings:briefing",
  "settings:pinned",
  "settings:undo",
  "settings:jobs",
  "settings:main",
  "settings:topics",
]);

/**
 * One catalogue row, frozen down to its `apps` list. `Object.freeze` on the
 * outer array alone is not enough - it is shallow, so `HOME_CARDS[0].label =
 * "x"` would still succeed and every screen in the same page would then be
 * drawing a rewritten label. Freezing each row (and its array) is what makes
 * the catalogue a constant an editor cannot edit, which the test suite proves.
 */
function freezeCardRow(card) {
  return Object.freeze({ ...card, apps: Object.freeze(card.apps.slice()) });
}

/**
 * THE CATALOGUE: one entry per feature that may be a main-screen card.
 *
 * `key`        the feature's own id in `features/features.json` (one id is one
 *              feature in both apps).
 * `label`      the owner's words, shown unchanged by the editor and both apps.
 * `about`      one plain sentence, for the Add row and the card itself.
 * `apps`       which app can draw it: `desktop`, `phone`, or both.
 * `default_on` whether a fresh install has it on the main screen.
 * `size`       the size it is added at; `min_size` the smallest it may become.
 * `opens`      where the card takes you (the vocabulary above).
 * `feature`    the feature whose on/off state the card reports, when that is
 *              not the key itself. `null` means "the card is the feature".
 */
export const HOME_CARDS = Object.freeze([
  // ---- the four that are on from the start: the HUD's own main screen
  {
    key: "today",
    label: "Today",
    about: "Today's plan and what is left of it.",
    apps: ["desktop", "phone"],
    default_on: true,
    size: "M",
    min_size: "S",
    opens: "stage:today",
    feature: "today",
  },
  {
    key: "coming-up",
    label: "Coming up",
    about: "Timers, alarms, reminders and the to-do list.",
    apps: ["desktop", "phone"],
    default_on: true,
    size: "M",
    min_size: "S",
    opens: "stage:reminders",
    feature: "coming-up",
  },
  {
    key: "now",
    label: "Right now",
    about: "What Jarvis is doing at this moment.",
    apps: ["desktop", "phone"],
    default_on: true,
    size: "S",
    min_size: "S",
    opens: "stage:telemetry",
    feature: "now",
  },
  {
    key: "settings-entry",
    label: "Settings",
    about: "Every setting, in one place.",
    apps: ["desktop", "phone"],
    default_on: true,
    size: "S",
    min_size: "S",
    opens: "settings:main",
    feature: "settings-entry",
  },
  // ---- planning and the day
  {
    key: "calendar",
    label: "Calendar",
    about: "What is booked, and what is next.",
    apps: ["desktop"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:calendar",
    feature: "calendar",
  },
  {
    key: "briefing",
    label: "Morning briefing",
    about: "The three lines worth reading first.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:briefing",
    feature: "briefing",
  },
  // ---- memory
  {
    key: "memory-tab",
    label: "Memory",
    about: "Everything Jarvis remembers, and where to forget it.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "stage:memory",
    feature: "memory-tab",
  },
  {
    key: "pinned-facts",
    label: "Always keep in mind",
    about: "Facts pinned to every answer.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:pinned",
    feature: "pinned-facts",
  },
  {
    key: "topics",
    label: "Topics",
    about: "A mode for each topic of what Jarvis learns.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:topics",
    feature: "topics",
  },
  {
    key: "wiki",
    label: "Wiki",
    about: "The wiki Jarvis builds from your notes.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:wiki",
    feature: "wiki",
  },
  {
    key: "galaxy",
    label: "Galaxy",
    about: "The names Jarvis holds and the links between them.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "T",
    min_size: "L",
    opens: "stage:galaxy",
    feature: "galaxy",
  },
  // ---- screen and pictures
  {
    key: "pictures",
    label: "Pictures",
    about: "What Jarvis has seen on your screen, and the pictures it kept.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:pictures",
    feature: "pictures",
  },
  // ---- study
  {
    key: "quiz",
    label: "Quiz me on a text",
    about: "Questions made from your own words.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:quiz",
    feature: "quiz",
  },
  {
    key: "decks",
    label: "Study decks",
    about: "The fading-card decks and the radar.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:decks",
    feature: "decks",
  },
  // ---- work
  {
    key: "focus",
    label: "Focus session",
    about: "One job at a time, until the bell.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:focus",
    feature: "focus",
  },
  {
    key: "jobs",
    label: "Background jobs",
    about: "Work that outlives the conversation.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:jobs",
    feature: "jobs",
  },
  {
    key: "undo",
    label: "Undo shelf",
    about: "What can still be undone, in one tap.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:undo",
    feature: "undo",
  },
  // ---- voice
  {
    key: "voice-check",
    label: "Voice check",
    about: "Say one line and hear how it sounds.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:voice",
    feature: "voice-check",
  },
  // ---- the machine
  {
    key: "models",
    label: "Models",
    about: "Which model answers, and where it runs.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:models",
    feature: "models",
  },
  {
    key: "compute",
    label: "Compute",
    about: "What the graphics cards are doing.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:compute",
    feature: "compute",
  },
  {
    key: "skills",
    label: "Skills",
    about: "What Jarvis has been taught to do.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "S",
    min_size: "S",
    opens: "settings:skills",
    feature: "skills",
  },
  // ---- money
  {
    key: "spending",
    label: "Spending",
    about: "Spending summaries from a bank file.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:spending",
    feature: "spending",
  },
  {
    key: "retirement",
    label: "Retirement what-if",
    about: "What the numbers look like later.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:retirement",
    feature: "retirement",
  },
  // ---- projects
  {
    key: "projects",
    label: "Projects",
    about: "What is on, and how far along it is.",
    apps: ["desktop", "phone"],
    default_on: false,
    size: "M",
    min_size: "S",
    opens: "settings:projects",
    feature: "projects",
  },
].map(freezeCardRow));

const BY_KEY = new Map(HOME_CARDS.map((card) => [card.key, card]));

/** What `about` says when a build is asked for a card it does not have. */
const UNKNOWN_ABOUT = "This build of Jarvis does not have that card.";

/** The catalogue entry for one key, or null. */
export function homeCard(key) {
  return BY_KEY.get(key) || null;
}

/** Every card this app can draw, in catalogue order. `app` may be omitted. */
export function catalogueFor(app = null) {
  if (!app) return HOME_CARDS.slice();
  return HOME_CARDS.filter((card) => card.apps.includes(app));
}

/** The four size words, for the editor's buttons. */
export function sizeInfo(key) {
  return HOME_SIZES[key] || null;
}

/** The smallest size this card may become, as a size object (or null). */
export function minSizeOf(card) {
  if (!card) return null;
  return HOME_SIZES[card.min_size] || HOME_SIZES.S;
}

/** The size this card is drawn at when it is added, as a size object. */
export function defaultSizeOf(card) {
  if (!card) return null;
  const size = HOME_SIZES[card.size] || HOME_SIZES.M;
  const min = minSizeOf(card);
  // A default smaller than the minimum is a catalogue typo; the minimum wins,
  // because the minimum is the promise the editor keeps.
  return SIZE_ORDER.indexOf(size.key) < SIZE_ORDER.indexOf(min.key) ? min : size;
}

/* =========================================================================
 * 1. The document - closed world, one normalizer
 * ========================================================================= */

function textOf(value, max, fallback = "") {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim().replace(/\s+/g, " ");
  return trimmed ? trimmed.slice(0, max) : fallback;
}

function intIn(value, lo, hi, fallback) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(n) || n < lo || n > hi) return fallback;
  return n;
}

/** One card entry from untrusted data, or null when the key is not a card. */
function entryOf(raw, index) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const key = textOf(raw.key, 40);
  if (!BY_KEY.has(key)) return null;
  return {
    key,
    on: typeof raw.on === "boolean" ? raw.on : true,
    order: intIn(raw.order, 0, MAX_HOME_CARDS, index),
  };
}

/**
 * The document this build means. CLOSED WORLD, exactly `normalizeLayout`'s
 * rule: only catalogue keys survive, a duplicate keeps its first place, `order`
 * is re-numbered 0..n-1 in the order the entries sorted to, unknown fields are
 * dropped (never copied through), and a wrong or missing `version` is not
 * repaired field by field - it is replaced by the default document, because
 * guessing what an older document meant is how a layout silently becomes a
 * different one.
 */
export function normalizeHomeCards(doc) {
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return defaultHomeCards();
  if (doc.version !== HOME_CARDS_VERSION) return defaultHomeCards();
  const seen = new Set();
  const cards = [];
  for (const raw of Array.isArray(doc.cards) ? doc.cards : []) {
    const entry = entryOf(raw, cards.length);
    if (!entry || seen.has(entry.key)) continue;
    if (cards.length >= MAX_HOME_CARDS) break;
    seen.add(entry.key);
    cards.push(entry);
  }
  cards.sort((a, b) => a.order - b.order || a.key.localeCompare(b.key));
  cards.forEach((entry, index) => { entry.order = index; });
  return {
    version: HOME_CARDS_VERSION,
    cards,
    updated_at: intIn(doc.updated_at, 0, 2 ** 52, 0),
  };
}

/** A fresh document holding exactly the catalogue's default-on cards. */
export function defaultHomeCards() {
  const cards = HOME_CARDS.filter((card) => card.default_on)
    .map((card, index) => ({ key: card.key, on: true, order: index }));
  return { version: HOME_CARDS_VERSION, cards, updated_at: 0 };
}

/** Whether a document is exactly the shipped default (so the editor can say so). */
export function isDefaultHomeCards(doc) {
  const clean = normalizeHomeCards(doc);
  const base = defaultHomeCards();
  if (clean.cards.length !== base.cards.length) return false;
  return clean.cards.every((entry, index) => {
    const other = base.cards[index];
    return other && entry.key === other.key && entry.on === other.on;
  });
}

/**
 * The cards the main screen actually draws, in order, for one app.
 *
 * A card the owner folded away (`on: false`) stays in the document and in the
 * editor's own list, so it can be drawn again - but it is NOT drawn here. That
 * is the promise the "Fold away" note makes.
 */
export function homeCardsFor(doc, app = "desktop") {
  const clean = normalizeHomeCards(doc);
  return clean.cards
    .filter((entry) => {
      const card = BY_KEY.get(entry.key);
      return Boolean(card) && card.apps.includes(app) && entry.on !== false;
    })
    .sort((a, b) => a.order - b.order)
    .map((entry) => ({ ...entry, card: BY_KEY.get(entry.key) }));
}

/** The catalogue cards this app can draw that are NOT on the main screen. */
export function missingHomeCards(doc, app = "desktop") {
  const clean = normalizeHomeCards(doc);
  const have = new Set(clean.cards.map((entry) => entry.key));
  return catalogueFor(app).filter((card) => !have.has(card.key));
}

/** The cards another app draws and this one does not, for an honest note. */
export function cardsOnlyOnOtherApp(doc, app = "desktop") {
  const clean = normalizeHomeCards(doc);
  const other = app === "phone" ? "desktop" : "phone";
  return clean.cards
    .map((entry) => BY_KEY.get(entry.key))
    .filter((card) => card && !card.apps.includes(app) && card.apps.includes(other));
}

/* =========================================================================
 * 2. The one reducer - add, remove, reorder, switch off
 * ========================================================================= */

/** Re-number `order` contiguously in array order. */
function renumberHomeCards(cards) {
  cards.forEach((entry, index) => { entry.order = index; });
  return cards;
}


/**
 * One action -> `{ doc, changed, refused, note }`. Pure: never mutates `doc`,
 * always returns a document that is a fixed point of `normalizeHomeCards`.
 * Every input - the Add button, the Remove button, the arrow keys, a reset and
 * the tests - calls this ONE function, which is what makes the editor's promise
 * mechanical rather than a matter of remembering.
 */
export function applyHomeAction(doc, action) {
  const base = normalizeHomeCards(doc);
  const act = action && typeof action === "object" ? action : {};
  const cards = base.cards.map((entry) => ({ ...entry }));
  const find = (key) => cards.find((entry) => entry.key === key);
  const say = (changed, note = "", refused = false) => {
    const next = changed
      ? normalizeHomeCards({ ...base, cards: renumberHomeCards(cards),
        updated_at: Math.floor(Date.now() / 1000) })
      : base;
    return { doc: next, changed, refused, note };
  };
  const refuse = (note) => ({ doc: base, changed: false, refused: true, note });

  switch (act.type) {
    case "addCard": {
      const card = BY_KEY.get(textOf(act.key, 40));
      if (!card) return refuse("That is not a feature this HUD can put on the main screen.");
      if (find(card.key)) return refuse(`${card.label} is already on the main screen.`);
      if (cards.length >= MAX_HOME_CARDS) return refuse("The main screen is full.");
      const at = act.index === undefined
        ? cards.length
        : clampInt(act.index, 0, cards.length, cards.length);
      cards.splice(at, 0, { key: card.key, on: true, order: at });
      return say(true, `${card.label} is on the main screen.`);
    }
    case "removeCard": {
      const key = textOf(act.key, 40);
      const card = BY_KEY.get(key);
      const at = cards.findIndex((entry) => entry.key === key);
      if (at < 0) return refuse(`${card ? card.label : "That card"} is not on the main screen.`);
      cards.splice(at, 1);
      return say(true, `${card ? card.label : key} is off the main screen.`);
    }
    case "moveCard": {
      const key = textOf(act.key, 40);
      const card = BY_KEY.get(key);
      const at = cards.findIndex((entry) => entry.key === key);
      if (at < 0) return refuse(`${card ? card.label : "That card"} is not on the main screen.`);
      let to;
      if (act.index !== undefined) {
        to = clampInt(act.index, 0, cards.length - 1, at);
      } else {
        const delta = clampInt(act.delta, -MAX_HOME_CARDS, MAX_HOME_CARDS, 0);
        to = clampInt(at + delta, 0, cards.length - 1, at);
      }
      if (to === at) {
        return { doc: base, changed: false, refused: false, note: "" };
      }
      cards.splice(to, 0, cards.splice(at, 1)[0]);
      return say(true, `${card ? card.label : key} moved ${to < at ? "up" : "down"}.`);
    }
    case "setCardOn": {
      const key = textOf(act.key, 40);
      const card = BY_KEY.get(key);
      const entry = find(key);
      if (!entry) return refuse(`${card ? card.label : "That card"} is not on the main screen.`);
      const want = act.on === undefined ? !entry.on : Boolean(act.on);
      if (entry.on === want) return { doc: base, changed: false, refused: false, note: "" };
      entry.on = want;
      return say(true, `${card ? card.label : key} is ${want ? "drawn" : "folded away"}.`);
    }
    case "resetHome": {
      if (isDefaultHomeCards(base)) {
        return { doc: base, changed: false, refused: false, note: "That is already the usual set." };
      }
      return {
        doc: defaultHomeCards(),
        changed: true,
        refused: false,
        note: "Back to the usual four cards.",
      };
    }
    default:
      return refuse("That is not an edit this HUD knows.");
  }
}

/* =========================================================================
 * 3. The off state - never blank, never raw JSON
 * ========================================================================= */

/**
 * What a card draws, given what the screen knows about its feature.
 *
 * `availability` is a plain object: `{ key: "on" | "off" | "missing" }`. A key
 * that is absent, or whose value is anything else, means **not asked** - and
 * "not asked" is drawn as a normal card, because "I have not checked" is not
 * "turned off". That is the same honesty rule `/api/status` runs on: a latch
 * that is `null` is "the PC has not said", never "not latched".
 */
export function cardState(key, availability = null) {
  const said = availability && typeof availability === "object"
    ? availability[key] : undefined;
  if (said === "on") return "on";
  if (said === "off") return "off";
  if (said === "missing") return "missing";
  return "on";
}

/**
 * The words a card draws for its state. Never empty, never JSON: the `off` and
 * `missing` lines are whole sentences an owner can act on.
 */
export function stateWords(card, state) {
  const label = card && card.label ? card.label : "This card";
  if (state === "off") return `${label} is turned off. Turn it on in Settings.`;
  if (state === "missing") return `${label} is not on this PC yet.`;
  return (card && card.about) || UNKNOWN_ABOUT;
}

/* =========================================================================
 * 4. Reading and writing the document (portability, the store, the tests)
 * ========================================================================= */

/** The document as JSON text, for a backup, a paste or the backend route. */
export function homeCardsJson(doc) {
  const clean = normalizeHomeCards(doc);
  return JSON.stringify({
    version: clean.version,
    cards: clean.cards.map((entry) => ({ key: entry.key, on: entry.on, order: entry.order })),
    updated_at: clean.updated_at,
  });
}

/** A stored or pasted document, or null when it is not even an object. */
export function parseHomeCards(text) {
  if (typeof text !== "string" || !text.trim()) return null;
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return normalizeHomeCards(value);
}

/** The catalogue as the plain rows the phone reads (no functions, no Map). */
export function catalogueRows() {
  return HOME_CARDS.map((card) => ({
    key: card.key,
    label: card.label,
    about: card.about,
    apps: card.apps.slice(),
    default_on: card.default_on,
    size: card.size,
    min_size: card.min_size,
    opens: card.opens,
    feature: card.feature,
  }));
}

/** One line saying what the main screen holds, for the editor's status line. */
export function describeHomeCards(doc) {
  const clean = normalizeHomeCards(doc);
  if (!clean.cards.length) return "The main screen has no feature cards.";
  const words = clean.cards.map((entry) => {
    const card = BY_KEY.get(entry.key);
    return card ? card.label : entry.key;
  });
  return `Main screen: ${words.join(", ")}.`;
}

/** The size buttons, as the ruling asks: Small / Medium / Wide / Tall. */
export const SIZES = Object.freeze([
  { key: "S", label: "Small", short: "S", col_span: 4, row_span: 1 },
  { key: "M", label: "Medium", short: "M", col_span: 6, row_span: 1 },
  { key: "L", label: "Wide", short: "L", col_span: 12, row_span: 1 },
  { key: "T", label: "Tall", short: "T", col_span: 12, row_span: 2 },
]);
export const SIZE_BY_KEY = Object.freeze(
  Object.fromEntries(SIZES.map((size) => [size.key, size])),
);

/** Human words for the five regions (the registry's own vocabulary). */
export const REGION_LABEL = Object.freeze({
  header: "Header",
  left_rail: "Left rail",
  stage_top: "Stage top",
  stage_main: "Stage",
  right_rail: "Right rail",
});

/** The regions H2 lets a panel card live in. */
export const EDIT_REGIONS = Object.freeze(["left_rail", "stage_top", "right_rail"]);

/**
 * The cards H2 can actually move: the ones whose DOM is a standalone section.
 * `approvals` is here (protected: it may move, it may never be hidden, and its
 * region is locked by the ruling). Everything else in the registry is FIXED:
 * the main stage, the composer, the Galaxy view, the header controls and any
 * card whose DOM does not exist on this page yet.
 */
export const MOVABLE_IDS = Object.freeze([
  "nav",
  "lanes",
  "systems",
  "bar_launcher",
  "approvals",
  "waiting",
  "telemetry",
  "tools",
  "brain_stats",
  "budget",
  "voice_stats",
]);

/** Card id -> the existing DOM element(s) that make up that card. */
export const CARD_DOM = Object.freeze({
  nav: ["#rail-nav"],
  lanes: ["#rail-lanes"],
  systems: ["#rail-systems"],
  bar_launcher: ["#hud-open-bar"],
  approvals: ["#approvals", "#initiative"],
  waiting: ["#rail-waiting"],
  telemetry: ["#rail-telemetry"],
  tools: ["#rail-tools"],
  brain_stats: ["#rail-memory"],
  budget: ["#rail-budget"],
  voice_stats: ["#rail-voice"],
});

/** Cards that H2 shows but deliberately does not reparent, with their reason. */
export const FIXED_IDS = Object.freeze({
  emergency_stop: "Stop everything is a fixed control in the header (Alt+Shift+X also works).",
  voice_controls: "The voice controls stay beside the composer.",
  conversation: "The conversation is the main stage.",
  composer: "The ask box is the main stage.",
  galaxy: "The Galaxy is the main stage's tab, not a panel card.",
  reminders: "Reminders and Today open in the main stage.",
  memory: "Memory opens in the main stage.",
});
export const FIXED_REASON = "This part of the HUD stays where it is.";

const REGION_SET = new Set(EDIT_REGIONS);
const MOVABLE_SET = new Set(MOVABLE_IDS);
const PROTECTED_SET = new Set(
  CARD_REGISTRY.filter((card) => card.protected).map((card) => card.id),
);
const CARD_BY_ID = new Map(CARD_REGISTRY.map((card) => [card.id, card]));

/* =========================================================================
 * 1. The pure reducer - ONE writer for every input
 * ========================================================================= */

function orderInRegion(cards, region) {
  return cards
    .filter((card) => card.region === region)
    .sort((a, b) => a.order - b.order || String(a.id).localeCompare(String(b.id)));
}

/** Re-number `order` contiguously 0..n-1 in each region (canonical order). */
function renumber(cards) {
  const out = [];
  for (const region of REGIONS) {
    orderInRegion(cards, region).forEach((card, index) => {
      out.push({ ...card, order: index });
    });
  }
  return out;
}

/**
 * One action -> `{ layout, changed, refused, note }`. Pure: never mutates
 * `layout`, always returns a document that is a fixed point of `normalizeLayout`.
 */
export function applyAction(layout, action, { pendingCount = 0 } = {}) {
  const base = normalizeLayout(layout);
  const act = action && typeof action === "object" ? action : {};
  const cards = base.cards.map((card) => ({ ...card, options: { ...card.options } }));
  const find = (id) => cards.find((card) => card.id === id);
  const say = (changed, note = "", refused = false) => {
    const doc = changed ? normalizeLayout(baseDocument(base, cards)) : base;
    if (changed) doc.updated_at = Math.floor(Date.now() / 1000);
    return { layout: doc, changed, refused, note };
  };
  const refuse = (note) => ({ layout: base, changed: false, refused: true, note });

  switch (act.type) {
    case "moveCard": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      if (!REGION_SET.has(act.region)) return refuse("That is not a region this editor can move a card to.");
      if (PROTECTED_SET.has(card.id)) {
        return refuse(`${CARD_BY_ID.get(card.id).label} always stays in ${REGION_LABEL[card.region]}.`);
      }
      if (card.region === act.region) {
        return { layout: base, changed: false, refused: false, note: `${CARD_BY_ID.get(card.id).label} is already in ${REGION_LABEL[act.region]}.` };
      }
      const target = orderInRegion(cards, act.region);
      const index = clampInt(act.index, 0, target.length, target.length);
      target.splice(index, 0, card);
      target.forEach((entry, at) => { entry.order = at; });
      card.region = act.region;
      const source = orderInRegion(cards, base.cards.find((c) => c.id === card.id).region)
        .filter((entry) => entry.id !== card.id);
      source.forEach((entry, at) => { entry.order = at; });
      return say(true, `${CARD_BY_ID.get(card.id).label} moved to ${REGION_LABEL[act.region]}.`);
    }
    case "reorderCard": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      const list = orderInRegion(cards, card.region);
      const at = list.findIndex((entry) => entry.id === card.id);
      const to = clampInt(at + clampInt(act.delta, -50, 50, 0), 0, list.length - 1, at);
      if (to === at) return { layout: base, changed: false, refused: false, note: "" };
      list.splice(to, 0, list.splice(at, 1)[0]);
      list.forEach((entry, index) => { entry.order = index; });
      return say(true, `${CARD_BY_ID.get(card.id).label} moved ${to < at ? "up" : "down"}.`);
    }
    case "resizeCard": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      const size = act.size
        ? SIZE_BY_KEY[act.size]
        : { col_span: act.col_span, row_span: act.row_span };
      if (!size) return refuse("That is not a size this editor offers.");
      const col = clampInt(size.col_span, 1, 12, card.col_span);
      const row = clampInt(size.row_span, 1, 4, card.row_span);
      if (col === card.col_span && row === card.row_span) {
        return { layout: base, changed: false, refused: false, note: "" };
      }
      card.col_span = col;
      card.row_span = row;
      const words = SIZES.find((entry) => entry.col_span === col && entry.row_span === row);
      return say(true, `${CARD_BY_ID.get(card.id).label} is now ${words ? words.label : `${col} wide`}.`);
    }
    case "toggleCollapsed": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      card.collapsed = act.collapsed === undefined ? !card.collapsed : Boolean(act.collapsed);
      const shown = effectiveCollapsed(card, pendingCount);
      return say(true, `${CARD_BY_ID.get(card.id).label} is ${shown ? "folded" : "open"}.`);
    }
    case "setVisible": {
      const card = find(act.id);
      if (!card) return refuse("That card is not in this layout.");
      const want = act.visible === undefined ? !card.visible : Boolean(act.visible);
      if (PROTECTED_SET.has(card.id) && !want) return refuse(`${CARD_BY_ID.get(card.id).label} can never be hidden.`);
      if (!MOVABLE_SET.has(card.id)) return refuse(FIXED_REASON);
      card.visible = want;
      return say(true, `${CARD_BY_ID.get(card.id).label} is ${want ? "shown" : "hidden"}.`);
    }
    case "resetToPreset": {
      const preset = PRESETS.find((entry) => entry.id === act.id);
      if (!preset) return refuse("That preset does not exist.");
      return { layout: presetLayout(preset.id), changed: true, refused: false, note: `Reset to ${presetInfo(preset.id).label}.` };
    }
    case "replaceLayout": {
      const doc = normalizeLayout(act.layout);
      return { layout: doc, changed: true, refused: false, note: act.note || "" };
    }
    default:
      return refuse("That is not an edit this HUD knows.");
  }
}

/** Rebuild a document from an edited card list (keeps every other field). */
function baseDocument(source, cards) {
  return {
    ...source,
    cards: renumber(cards),
    updated_at: Math.floor(Date.now() / 1000),
  };
}

function clampInt(value, lo, hi, fallback) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(n)) return fallback;
  return Math.min(hi, Math.max(lo, n));
}

/** Where a card of this size/region would sit, for tests and the toolbar. */
export function sizeKeyFor(card) {
  const found = SIZES.find(
    (size) => size.col_span === card.col_span && size.row_span === card.row_span,
  );
  return found ? found.key : null;
}

/* =========================================================================
 * 2. The editor: rendering, drag, toolbar, autosave, undo
 * ========================================================================= */

const SAVE_DEBOUNCE_MS = 400;
const UNDO_LIMIT = 50;

/** This window's own key for the main-screen cards (DESIGN.md section 4). */
const HOME_STORE_KEY = "jarvis.hud.home_cards.v1";

/**
 * Mount the editor on the live page. Returns a controller; the page's own
 * glue calls this once. Safe to call in a plain browser: without the shell
 * there is no save road, so the button hides itself (the tests that need it
 * stub the shell).
 */
export function mountHudEditor(options = {}) {
  const doc = options.document || globalThis.document;
  if (!doc) throw new Error("hud-edit needs a document");
  const store = options.store || { loadLayout, saveLayout };
  const shellPresent = typeof options.shellPresent === "boolean"
    ? options.shellPresent
    : Boolean(globalThis.__TAURI__ && globalThis.__TAURI__.core);
  let layout = null;
  let editing = false;
  let entrySnapshot = null;
  const undoStack = [];
  let saveTimer = null;
  let saving = false;
  let lastSavedAt = null;
  const cardShells = new Map();   // id -> shell element
  const regionEls = new Map();    // region -> element
  let dragState = null;
  let statusEl = null;
  let barEl = null;
  let badgeEl = null;
  let homeDoc = null;      // the main screen's feature cards
  let homeStrip = null;    // the strip they are drawn in

  const byId = (id) => doc.getElementById(id);
  const labelOf = (id) => (CARD_BY_ID.get(id) || { label: id }).label;
  const pendingCount = () => {
    try {
      const text = byId("appr-badge") ? byId("appr-badge").textContent : "";
      const n = parseInt(String(text).replace(/[^0-9]/g, ""), 10);
      return Number.isFinite(n) ? n : 0;
    } catch { return 0; }
  };

  function announce(words) {
    if (!statusEl) return;
    statusEl.textContent = words;
  }

  // ---------------------------------------------------------------- regions
  function ensureRegions() {
    if (regionEls.size) return;
    const shell = byId("shell");
    const left =
      (doc.querySelector(".rail.left") || null);
    const right = byId("rail-right");
    const stage = byId("stage");
    if (left) {
      const el = doc.createElement("div");
      el.className = "hud-region hud-region-left";
      el.setAttribute("data-hud-region", "left_rail");
      el.setAttribute("aria-label", REGION_LABEL.left_rail);
      left.insertBefore(el, byId("rail-nav"));
      regionEls.set("left_rail", el);
    }
    if (stage) {
      const el = doc.createElement("div");
      el.className = "hud-region hud-region-stage-top";
      el.setAttribute("data-hud-region", "stage_top");
      el.setAttribute("aria-label", REGION_LABEL.stage_top);
      stage.insertBefore(el, byId("banner") || stage.firstChild);
      regionEls.set("stage_top", el);
    }
    if (right) {
      const el = doc.createElement("div");
      el.className = "hud-region hud-region-right";
      el.setAttribute("data-hud-region", "right_rail");
      el.setAttribute("aria-label", REGION_LABEL.right_rail);
      right.insertBefore(el, byId("rail-close") ? byId("rail-close").nextSibling : right.firstChild);
      regionEls.set("right_rail", el);
    }
    if (!regionEls.size && shell) {
      // A very old page with no rails at all: one region so edit mode still
      // has somewhere honest to say it cannot move anything.
      const el = doc.createElement("div");
      el.className = "hud-region";
      el.setAttribute("data-hud-region", "right_rail");
      shell.appendChild(el);
      regionEls.set("right_rail", el);
    }
  }

  function makeShell(id) {
    const shell = doc.createElement("section");
    shell.className = "hud-card";
    shell.setAttribute("data-hud-card", id);
    shell.setAttribute("aria-label", labelOf(id));
    const head = doc.createElement("header");
    head.className = "hud-card-head";
    const handle = doc.createElement("button");
    handle.type = "button";
    handle.className = "hud-card-handle";
    handle.setAttribute("data-hud-card-handle", id);
    handle.setAttribute("aria-label", `Move ${labelOf(id)}. Use the arrow keys and buttons, or drag.`);
    handle.textContent = "\u2630";
    head.appendChild(handle);
    const title = doc.createElement("span");
    title.className = "hud-card-title";
    title.textContent = labelOf(id);
    head.appendChild(title);
    // Shown only while the card is hidden and Edit HUD is on: the ghost needs
    // to say what state the card is in, not just look dimmer.
    const word = doc.createElement("span");
    word.className = "hud-card-hidden-word";
    word.textContent = "hidden";
    word.hidden = true;
    head.appendChild(word);
    head.appendChild(buildToolbar(id));
    const body = doc.createElement("div");
    body.className = "hud-card-body";
    shell.appendChild(head);
    shell.appendChild(body);
    shell.addEventListener("keydown", (event) => onShellKey(event, id));
    cardShells.set(id, shell);
    // Move the real card nodes in ONCE; ids and listeners are not cloned.
    for (const selector of CARD_DOM[id] || []) {
      const node = doc.querySelector(selector);
      if (node) body.appendChild(node);
    }
    return shell;
  }

  function buildToolbar(id) {
    const wrap = doc.createElement("div");
    wrap.className = "hud-card-tools";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", `${labelOf(id)} layout controls`);
    const button = (command, text, title, extra = {}) => {
      const b = doc.createElement("button");
      b.type = "button";
      b.className = "hud-tool";
      b.setAttribute("data-hud-edit-command", command);
      b.setAttribute("data-hud-edit-card", id);
      b.textContent = text;
      b.title = title;
      b.setAttribute("aria-label", title);
      if (extra.disabled) {
        b.disabled = true;
        b.setAttribute("aria-disabled", "true");
      }
      if (extra.reason) b.setAttribute("title", `${title}\n${extra.reason}`);
      return b;
    };
    const protectedCard = PROTECTED_SET.has(id);
    const fixed = !MOVABLE_SET.has(id);
    wrap.appendChild(button("up", "\u2191", `Move ${labelOf(id)} up`, { disabled: fixed }));
    wrap.appendChild(button("down", "\u2193", `Move ${labelOf(id)} down`, { disabled: fixed }));
    // The direct region selector (ruling 27): a single-pointer alternative to
    // dragging across regions, and the words say which region is which.
    const regionWrap = doc.createElement("label");
    regionWrap.className = "hud-tool-select";
    regionWrap.textContent = "Move to";
    const select = doc.createElement("select");
    select.setAttribute("data-hud-edit-region", id);
    select.setAttribute("aria-label", `Move ${labelOf(id)} to another region`);
    for (const region of EDIT_REGIONS) {
      const option = doc.createElement("option");
      option.value = region;
      option.textContent = REGION_LABEL[region];
      select.appendChild(option);
    }
    select.disabled = fixed || protectedCard;
    if (protectedCard) select.title = `${labelOf(id)} always stays in ${REGION_LABEL[(CARD_BY_ID.get(id) || {}).region] || "its region"}.`;
    if (fixed) select.title = FIXED_IDS[id] || FIXED_REASON;
    regionWrap.appendChild(select);
    wrap.appendChild(regionWrap);
    // Size buttons S / M / L / T, each a real pressed button.
    const sizeWrap = doc.createElement("div");
    sizeWrap.className = "hud-tool-sizes";
    sizeWrap.setAttribute("role", "group");
    sizeWrap.setAttribute("aria-label", `${labelOf(id)} size`);
    for (const size of SIZES) {
      const b = button("size", size.short, `${labelOf(id)}: ${size.label}`, { disabled: fixed });
      b.setAttribute("data-hud-edit-size", size.key);
      sizeWrap.appendChild(b);
    }
    wrap.appendChild(sizeWrap);
    wrap.appendChild(button("collapse", "\u25be", `Fold ${labelOf(id)}`));
    const hide = button("hide", "\u2715", `Hide ${labelOf(id)}`, { disabled: fixed || protectedCard });
    if (protectedCard) hide.setAttribute("aria-description", `${labelOf(id)} can never be hidden.`);
    if (fixed) hide.setAttribute("title", `${FIXED_IDS[id] || FIXED_REASON}`);
    wrap.appendChild(hide);
    return wrap;
  }

  function ensureShells() {
    for (const card of layout.cards) {
      if (!MOVABLE_SET.has(card.id)) continue;
      if (cardShells.has(card.id)) continue;
      const shell = makeShell(card.id);
      const region = regionEls.get(EDIT_REGIONS.includes(card.region) ? card.region : "right_rail");
      if (region) region.appendChild(shell);
    }
    // The Jarvis-bar button is created by the shell bootstrap after this page
    // runs; catch it the first time we render after it appears.
    if (MOVABLE_SET.has("bar_launcher") && !cardShells.has("bar_launcher") && byId("hud-open-bar")) {
      const shell = makeShell("bar_launcher");
      const region = regionEls.get(
        (layout.cards.find((c) => c.id === "bar_launcher") || {}).region || "left_rail",
      );
      if (region) region.appendChild(shell);
    }
  }

  function render() {
    ensureRegions();
    ensureShells();
    if (!layout) return;
    const pending = pendingCount();
    const byRegion = new Map(EDIT_REGIONS.map((region) => [region, []]));
    for (const card of layout.cards) {
      if (!MOVABLE_SET.has(card.id)) continue;
      const shell = cardShells.get(card.id);
      if (!shell) continue;
      const regionName = EDIT_REGIONS.includes(card.region) ? card.region : "right_rail";
      byRegion.get(regionName).push(card);
      // 2026-10-28 (the owner's Edit HUD field test): a hidden card must stay
      // reachable WHILE EDITING, or its own Show control can never be clicked
      // again. So in edit mode a hidden card is painted as a dimmed ghost (its
      // header and toolbar; the page CSS folds its body away, so the card
      // itself stays hidden). Outside edit mode the shell is hidden exactly as
      // the card is, as before.
      shell.hidden = !card.visible && !editing;
      shell.classList.toggle("hud-card-hidden", !card.visible);
      shell.classList.toggle("hud-card-collapsed", effectiveCollapsed(card, pending));
      shell.setAttribute("data-hud-movable", "yes");
      shell.style.setProperty("--hud-span", String(card.col_span));
      shell.style.setProperty("--hud-rows", String(card.row_span));
      shell.setAttribute(
        "data-hud-span",
        `${card.col_span}x${card.row_span}`,
      );
      const hiddenWord = shell.querySelector(".hud-card-hidden-word");
      if (hiddenWord) hiddenWord.hidden = card.visible;
      const collapseBtn = shell.querySelector('[data-hud-edit-command="collapse"]');
      if (collapseBtn) {
        const folded = effectiveCollapsed(card, pending);
        collapseBtn.setAttribute("aria-pressed", folded ? "true" : "false");
        collapseBtn.title = `${folded ? "Open" : "Fold"} ${labelOf(card.id)}`;
        collapseBtn.setAttribute("aria-label", collapseBtn.title);
      }
      const hideBtn = shell.querySelector('[data-hud-edit-command="hide"]');
      if (hideBtn) {
        // The same pattern as Fold above: the words name the action the press
        // takes, and aria-pressed says what the card is now. One control, both
        // directions - the field test found the old one could only hide.
        const hidden = !card.visible;
        hideBtn.setAttribute("aria-pressed", hidden ? "true" : "false");
        hideBtn.textContent = hidden ? "\u25cb" : "\u2715";
        hideBtn.title = `${hidden ? "Show" : "Hide"} ${labelOf(card.id)}`;
        hideBtn.setAttribute("aria-label", hideBtn.title);
      }
    }
    for (const [region, cards] of byRegion) {
      const el = regionEls.get(region);
      if (!el) continue;
      cards.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
      for (const card of cards) {
        const shell = cardShells.get(card.id);
        if (shell && shell.parentElement !== el) el.appendChild(shell);
      }
    }
    doc.body.setAttribute("data-hud-edit", editing ? "on" : "off");
    if (barEl) barEl.hidden = !editing;
    renderHomeStrip();
    updateBadge();
    if (options.onRender) {
      try { options.onRender(layout, { editing }); } catch { /* never break the page */ }
    }
  }

  // -------------------------------------------------------------- save/undo
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    if (saving) { saveTimer = setTimeout(scheduleSave, SAVE_DEBOUNCE_MS); return; }
    saveTimer = setTimeout(flushSave, SAVE_DEBOUNCE_MS);
  }

  async function flushSave() {
    saveTimer = null;
    saving = true;
    try {
      const answer = await store.saveLayout(layout);
      if (answer && answer.layout) layout = answer.layout;
      if (answer && answer.saved) {
        lastSavedAt = new Date();
        try {
          globalThis.dispatchEvent(new CustomEvent("jarvis:hud-layout-saved",
            { detail: layout }));
        } catch { /* an old engine: the badge still shows the name */ }
        announce(`Saved. ${describeLayout(layout)}`);
      } else {
        announce(`Not saved: ${(answer && answer.error) || "the PC refused the write"}.`);
      }
    } catch (error) {
      announce(`Not saved: ${error && error.message ? error.message : error}`);
    } finally {
      saving = false;
      render();
    }
  }

  function doAction(action, { snapshot = true } = {}) {
    const before = layout;
    const result = applyAction(layout, action, { pendingCount: pendingCount() });
    if (!result.changed) {
      if (result.note) announce(result.note);
      return result;
    }
    if (snapshot) {
      undoStack.push(before);
      if (undoStack.length > UNDO_LIMIT) undoStack.shift();
    }
    // H3 (Ruling 27): the first change to a SHIPPED layout is made to the
    // owner's copy, never silently to the built-in. Reset keeps a custom copy
    // a custom copy (its name and its saved layout survive a reset).
    let next = result.layout;
    let note = result.note;
    if (action.type === "resetToPreset") {
      if (isUserLayout(before)) {
        next = normalizeLayout({
          ...next,
          id: before.id,
          name: before.name,
          user_presets: userLayouts(before),
        });
      }
    } else if (!isUserLayout(before)) {
      next = ensureCustomCopy(next);
      note = `${note ? `${note} ` : ""}Editing your copy "${next.name}".`;
    }
    layout = next;
    render();
    scheduleSave();
    if (note) announce(note);
    return { ...result, layout };
  }

  function undo() {
    const previous = undoStack.pop();
    if (!previous) { announce("Nothing to undo."); return; }
    layout = previous;
    render();
    scheduleSave();
    announce("Undone.");
  }

  // H3-PM-2 (post-merge audit, 2026-10-22): entering edit mode must never
  // leave a protected card behind a closed rail. Every rail the current shell
  // slides away (or hides outright, like split-stage's right rail) is marked
  // `.edit-reveal`, which the page CSS brings on screen; leaving edit mode
  // removes the mark so the shell's own look returns untouched.
  const editRevealedRails = new Set();
  function revealRailsForEditing() {
    const view = doc.defaultView;
    const rails = [doc.querySelector(".rail.left"), doc.getElementById("rail-right")]
      .filter(Boolean);
    for (const rail of rails) {
      if (editing) {
        const style = view ? view.getComputedStyle(rail) : null;
        const box = rail.getBoundingClientRect();
        const hidden = !style || style.display === "none" || box.right <= 1
          || box.left >= (view ? view.innerWidth : 0) - 1;
        if (hidden) {
          rail.classList.add("edit-reveal");
          editRevealedRails.add(rail);
        }
      } else if (editRevealedRails.has(rail)) {
        rail.classList.remove("edit-reveal");
        editRevealedRails.delete(rail);
      }
    }
  }

  function setEditing(on) {
    editing = Boolean(on);
    if (editing) {
      entrySnapshot = layout;
      undoStack.length = 0;
      announce("");
    } else if (saveTimer) {
      flushSave();
    }
    revealRailsForEditing();
    render();
    updateEditButton();
  }

  function updateEditButton() {
    const button = byId("hud-edit-toggle");
    if (!button) return;
    button.setAttribute("aria-pressed", editing ? "true" : "false");
    button.textContent = editing ? "Done" : "Edit HUD";
    button.title = editing
      ? "Finish editing the HUD layout"
      : "Move, resize, fold or hide the HUD's cards";
    button.hidden = !shellPresent;
  }

  // ------------------------------------------------------------ interactions
  function cardFromEvent(target) {
    const shell = target && target.closest ? target.closest("[data-hud-card]") : null;
    return shell ? shell.getAttribute("data-hud-card") : null;
  }

  function onToolbarClick(event) {
    const button = event.target && event.target.closest
      ? event.target.closest("[data-hud-edit-command]") : null;
    if (!button) return;
    event.preventDefault();
    const id = button.getAttribute("data-hud-edit-card");
    const command = button.getAttribute("data-hud-edit-command");
    if (button.disabled) {
      announce(button.title || FIXED_REASON);
      return;
    }
    if (!editing) return;
    if (command === "up") doAction({ type: "reorderCard", id, delta: -1 });
    else if (command === "down") doAction({ type: "reorderCard", id, delta: 1 });
    else if (command === "size") {
      doAction({ type: "resizeCard", id, size: button.getAttribute("data-hud-edit-size") });
    } else if (command === "collapse") doAction({ type: "toggleCollapsed", id });
    else if (command === "hide") {
      // A real toggle (2026-10-28, the owner's field test). The setVisible
      // action already flips the card's own state when no value is given, so
      // this is the SAME door as the `h` key below - never a second mutation
      // path, and never a hard-coded hide.
      doAction({ type: "setVisible", id });
    }
  }

  function onRegionChange(event) {
    const select = event.target && event.target.closest
      ? event.target.closest("[data-hud-edit-region]") : null;
    if (!select) return;
    const id = select.getAttribute("data-hud-edit-region");
    if (!editing) return;
    doAction({ type: "moveCard", id, region: select.value, index: 0 });
  }

  function onShellKey(event, id) {
    if (!editing) return;
    const target = event.target;
    if (!target || !target.classList || !target.classList.contains("hud-card-handle")) return;
    const card = layout.cards.find((entry) => entry.id === id);
    if (!card) return;
    let handled = true;
    if (event.altKey && event.key === "ArrowUp") doAction({ type: "reorderCard", id, delta: -1 });
    else if (event.altKey && event.key === "ArrowDown") doAction({ type: "reorderCard", id, delta: 1 });
    else if (event.altKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      const at = EDIT_REGIONS.indexOf(card.region);
      const next = event.key === "ArrowLeft" ? at - 1 : at + 1;
      if (next < 0 || next >= EDIT_REGIONS.length) announce(`${labelOf(id)} is already in ${REGION_LABEL[card.region]}.`);
      else doAction({ type: "moveCard", id, region: EDIT_REGIONS[next], index: 0 });
    } else if (event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      const step = event.key === "ArrowLeft" ? -2 : 2;
      doAction({ type: "resizeCard", id, col_span: card.col_span + step, row_span: card.row_span });
    } else if (event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      const step = event.key === "ArrowUp" ? -1 : 1;
      doAction({ type: "resizeCard", id, col_span: card.col_span, row_span: card.row_span + step });
    } else if (event.key === "Enter" || event.key === " ") doAction({ type: "toggleCollapsed", id });
    else if (event.key === "h" || event.key === "H") doAction({ type: "setVisible", id });
    else handled = false;
    if (handled) event.preventDefault();
  }

  // ---------------------------------------------------------------- pointer
  function onPointerDown(event) {
    if (!editing || dragState) return;
    const handle = event.target && event.target.closest
      ? event.target.closest("[data-hud-card-handle]") : null;
    if (!handle) return;
    const id = handle.getAttribute("data-hud-card-handle");
    const card = layout.cards.find((entry) => entry.id === id);
    if (!card || !MOVABLE_SET.has(id)) return;
    if (PROTECTED_SET.has(id)) {
      announce(`${labelOf(id)} always stays in ${REGION_LABEL[card.region]}.`);
      return;
    }
    event.preventDefault();
    const shell = cardShells.get(id);
    if (!shell) return;
    dragState = { id, shell, pointerId: event.pointerId, target: null };
    shell.classList.add("hud-card-dragging");
    try { handle.setPointerCapture(event.pointerId); } catch { /* ok */ }
  }

  function onPointerMove(event) {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    event.preventDefault();
    const drop = doc.elementFromPoint(event.clientX, event.clientY);
    const region = drop && drop.closest ? drop.closest("[data-hud-region]") : null;
    if (!region) return;
    for (const el of regionEls.values()) el.classList.remove("hud-region-drop");
    region.classList.add("hud-region-drop");
    dragState.target = region.getAttribute("data-hud-region");
    dragState.index = dropIndexIn(region, event.clientY, dragState.id);
  }

  function onPointerUp(event) {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    const { id, target, index } = dragState;
    dragState = null;
    const shell = cardShells.get(id);
    if (shell) shell.classList.remove("hud-card-dragging");
    for (const el of regionEls.values()) el.classList.remove("hud-region-drop");
    if (target) doAction({ type: "moveCard", id, region: target, index: index || 0 });
  }

  function dropIndexIn(region, clientY, movingId) {
    const shells = Array.from(region.querySelectorAll("[data-hud-card]"))
      .filter((el) => el.getAttribute("data-hud-card") !== movingId && !el.hidden);
    for (let i = 0; i < shells.length; i += 1) {
      const box = shells[i].getBoundingClientRect();
      if (clientY < box.top + box.height / 2) return i;
    }
    return shells.length;
  }

  // -------------------------------------------------------------- key handling
  function onKeyDown(event) {
    if (event.key === "Escape") {
      if (dragState) {
        const shell = cardShells.get(dragState.id);
        if (shell) shell.classList.remove("hud-card-dragging");
        for (const el of regionEls.values()) el.classList.remove("hud-region-drop");
        dragState = null;
        announce("Drag cancelled.");
        return;
      }
      if (editing) {
        event.preventDefault();
        setEditing(false);
        announce("HUD editing finished.");
      }
      return;
    }
    if (editing && (event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "z") {
      event.preventDefault();
      undo();
    }
  }

  // --------------------------------------------------------------------- bar
  function ensureBar() {
    const stage = byId("stage");
    if (!stage) return;
    barEl = doc.createElement("div");
    barEl.className = "hud-edit-bar hud-edit-banner";
    barEl.id = "hud-edit-bar";
    barEl.hidden = true;
    barEl.setAttribute("role", "region");
    barEl.setAttribute("aria-label", "HUD editing controls");
    // Built node by node: this page has an HTML-sink rule (tests/html-sinks.mjs)
    // and a capture bar has no dynamic text needing markup.
    const words = doc.createElement("span");
    words.className = "hud-edit-words";
    words.textContent = "Editing the HUD — drag a card or use its buttons. Press Esc when done.";
    const status = doc.createElement("span");
    status.className = "hud-edit-status";
    status.id = "hud-edit-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    barEl.append(words, status);
    for (const [what, text] of [["undo", "Undo"], ["reset", "Reset to preset"],
      ["discard", "Discard changes"], ["done", "Done"]]) {
      const button = doc.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.id = `hud-edit-${what}`;
      button.setAttribute("data-hud-edit-global", what);
      button.textContent = text;
      barEl.appendChild(button);
    }
    stage.insertBefore(barEl, byId("banner") || stage.firstChild);
    statusEl = doc.getElementById("hud-edit-status");
    barEl.addEventListener("click", (event) => {
      const button = event.target && event.target.closest
        ? event.target.closest("[data-hud-edit-global]") : null;
      if (!button) return;
      const what = button.getAttribute("data-hud-edit-global");
      if (what === "undo") undo();
      else if (what === "done") { setEditing(false); announce("HUD editing finished."); }
      else if (what === "reset") doAction({ type: "resetToPreset", id: layout.base_preset });
      else if (what === "discard" && entrySnapshot) {
        layout = entrySnapshot;
        undoStack.length = 0;
        setEditing(false);
        render();
        scheduleSave();
        announce("Changes discarded.");
      }
    });
  }

  function currentLayoutName() {
    if (!layout) return "Cockpit";
    if (isUserLayout(layout)) return layout.name;
    const info = presetInfo(layout.base_preset);
    return info ? info.label : (layout.name || "Cockpit");
  }

  function updateBadge() {
    if (!badgeEl || !layout) return;
    const name = currentLayoutName();
    badgeEl.textContent = `Layout: ${name}`;
    // The menu is called Presets since 2026-10-27 (it lists the PC's model
    // presets and personalities too), so the tooltip says that name.
    badgeEl.title = `HUD layout: ${name}. Open the Presets menu.`;
    badgeEl.setAttribute("aria-label", `HUD layout: ${name}. Open the Presets menu.`);
  }

  function ensureToggle() {
    const bar = doc.querySelector(".stage-bar");
    if (!bar) return;
    // F1 (2026-10-22): the read-only `Layout: <Preset Name>` badge sits next
    // to [Edit HUD]. It names the saved HUD layout and opens the Focus
    // presets card on click (L1) - it never chooses or saves a layout.
    badgeEl = doc.createElement("button");
    badgeEl.type = "button";
    badgeEl.className = "ghost hud-layout-badge";
    badgeEl.id = "hud-layout-badge";
    badgeEl.setAttribute("aria-expanded", "false");
    badgeEl.addEventListener("click", () => {
      try {
        globalThis.dispatchEvent(new CustomEvent("jarvis:hud-presets-open"));
      } catch { /* the badge still names the layout without a menu */ }
    });
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "ghost hud-edit-toggle";
    button.id = "hud-edit-toggle";
    button.setAttribute("aria-pressed", "false");
    button.title = "Move, resize, fold or hide the HUD's cards";
    button.textContent = "Edit HUD";
    button.setAttribute("aria-label", "Edit HUD layout");
    bar.append(badgeEl, button);
    button.hidden = !shellPresent;
    button.addEventListener("click", () => {
      setEditing(!editing);
    });
    updateBadge();
  }

  // ------------------------------------- the main screen's feature cards
  //
  // THE OWNER'S REQUIREMENT (2026-10-29). "Add them to the main screen through
  // the edit jarvis hud on desktop" - so the strip of feature cards at the top
  // of the stage and the Add/Remove/Reorder panel are BOTH drawn from this one
  // module, and both come out of the same `applyHomeAction`. Nothing else in
  // the page changes: the page already mounts this module on every load, so a
  // new served file would mean five lists in five files (the backend's closed
  // whitelist, both SHIPPED lists, the re-take table and the deploy copy)
  // before a browser could fetch it - and the catalogue is the editor's own
  // data, so it belongs here.
  //
  // WHERE THE CHOICE IS KEPT. This window's own storage, under one key. It is
  // read once at boot and written after every change; "not saved" is said out
  // loud rather than painted as saved. Moving it into the PC's settings store
  // and publishing it for the phone is the parity slice's next step - the
  // document shape is already the one both apps will read (see DESIGN.md).

  function readHomeDoc() {
    try {
      const storage = globalThis.localStorage;
      const raw = storage ? storage.getItem(HOME_STORE_KEY) : null;
      return (raw ? parseHomeCards(raw) : null) || defaultHomeCards();
    } catch {
      return defaultHomeCards();
    }
  }

  function writeHomeDoc(next) {
    try {
      const storage = globalThis.localStorage;
      if (!storage) return { saved: false, error: "this window has no store" };
      storage.setItem(HOME_STORE_KEY, homeCardsJson(next));
      return { saved: true };
    } catch (error) {
      return { saved: false, error: "this window refused to store it" };
    }
  }

  /** The strip's container, created once at the top of the stage. Its rules
   *  live in the page's own <style> ("THE MAIN SCREEN'S FEATURE-CARD STRIP" in
   *  jarvis_hud.html): the packaged CSP refuses a stylesheet built at run time,
   *  so nothing in this module may create one. */
  function ensureHomeStrip() {
    if (homeStrip && homeStrip.isConnected !== false) return homeStrip;
    const stage = byId("stage");
    if (!stage) return null;
    const wrap = doc.createElement("section");
    wrap.className = "hud-home-cards";
    wrap.id = "hud-home-cards";
    wrap.setAttribute("aria-label", "Your main screen");
    // Below the stage tabs and above the banner: the same place the editor's
    // own stage-top region is made, so a page that already asserts what is
    // at the top of the stage keeps its answer.
    stage.insertBefore(wrap, byId("banner") || byId("stage-menu") || stage.firstChild);
    homeStrip = wrap;
    return wrap;
  }

  /** What the page knows about one card's feature: a real answer or nothing. */
  function homeAvailability() {
    const seen = {};
    for (const card of HOME_CARDS) {
      const opens = String(card.opens || "");
      if (!opens.startsWith("stage:")) continue;
      const tab = opens.slice("stage:".length);
      // The feature's own stage tab is the page's own proof that the feature
      // exists in this build: a card whose tab is not on the page is drawn as
      // "not on this PC yet" rather than as a door to nowhere.
      seen[card.key] = doc.querySelector(`[data-hud-tab-choice="${tab}"]`)
        ? "on" : "missing";
    }
    return seen;
  }

  /** Open the place one card stands for: a stage tab, or the Settings window. */
  function openHomeCard(key) {
    const card = homeCard(key);
    if (!card) return;
    const opens = String(card.opens || "");
    if (opens.startsWith("stage:")) {
      const tab = doc.querySelector(`[data-hud-tab-choice="${opens.slice(6)}"]`);
      if (tab) { tab.click(); return; }
      announce(`${card.label} is not on this PC yet.`);
      return;
    }
    const invoke = globalThis.__TAURI__ && globalThis.__TAURI__.core
      ? globalThis.__TAURI__.core.invoke : null;
    if (!invoke) {
      announce(`${card.label} opens in Settings, which is on the PC.`);
      return;
    }
    // Navigation only: the same command the Settings gear and the first-run
    // card already use, and it changes no setting.
    try {
      invoke("open_fix_place", { place: "settings" });
      announce(`${card.label}: opened Settings.`);
    } catch {
      announce(`${card.label} opens in Settings, which is on the PC.`);
    }
  }

  function homeRow(card, entry) {
    const row = doc.createElement("div");
    row.className = "hud-home-row";
    const name = doc.createElement("span");
    name.className = "hud-home-name";
    name.textContent = card.label;
    row.appendChild(name);
    const note = doc.createElement("span");
    note.className = "hud-home-note";
    note.textContent = card.apps.includes("phone")
      ? `Also on the phone. Smallest size ${minSizeOf(card).label}.`
      : `On the PC only. Smallest size ${minSizeOf(card).label}.`;
    row.appendChild(note);
    const button = (command, text, title) => {
      const b = doc.createElement("button");
      b.type = "button";
      b.setAttribute("data-home-command", command);
      b.setAttribute("data-home-card", card.key);
      b.textContent = text;
      b.title = title;
      b.setAttribute("aria-label", title);
      return b;
    };
    if (entry) {
      row.appendChild(button("up", "\u2191", `Move ${card.label} earlier on the main screen`));
      row.appendChild(button("down", "\u2193", `Move ${card.label} later on the main screen`));
      const onBtn = button("switch", entry.on ? "\u25c9" : "\u25cb",
        entry.on ? `Fold ${card.label} away without removing it`
          : `Draw ${card.label} again`);
      onBtn.setAttribute("aria-pressed", entry.on ? "true" : "false");
      row.appendChild(onBtn);
      row.appendChild(button("remove", "\u2715", `Remove ${card.label} from the main screen`));
    } else {
      row.appendChild(button("add", "Add", `Add ${card.label} to the main screen`));
    }
    return row;
  }

  /** The Edit HUD panel: what is on the main screen, and everything that could be. */
  function homeEditorBlock() {
    const box = doc.createElement("div");
    box.className = "hud-home-edit";
    box.id = "hud-home-cards-editor";
    const title = doc.createElement("h3");
    title.textContent = "Main screen cards";
    box.appendChild(title);
    const clean = normalizeHomeCards(homeDoc);
    const on = doc.createElement("h4");
    on.textContent = `On the main screen (${clean.cards.length})`;
    box.appendChild(on);
    if (!clean.cards.length) {
      const line = doc.createElement("p");
      line.textContent = "Nothing yet. Add a feature from the list below.";
      box.appendChild(line);
    }
    for (const entry of clean.cards) {
      const card = homeCard(entry.key);
      if (card) box.appendChild(homeRow(card, entry));
    }
    const rest = missingHomeCards(homeDoc, "desktop");
    const off = doc.createElement("h4");
    off.textContent = `Not on the main screen (${rest.length})`;
    box.appendChild(off);
    if (!rest.length) {
      const line = doc.createElement("p");
      line.textContent = "Every card is on the main screen already.";
      box.appendChild(line);
    }
    for (const card of rest) box.appendChild(homeRow(card, null));
    const foot = doc.createElement("div");
    foot.className = "hud-home-row";
    const reset = doc.createElement("button");
    reset.type = "button";
    reset.setAttribute("data-home-command", "reset");
    reset.textContent = "Reset to the usual four";
    foot.appendChild(reset);
    const status = doc.createElement("span");
    status.className = "hud-home-edit-status";
    status.id = "hud-home-cards-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    foot.appendChild(status);
    box.appendChild(foot);
    return box;
  }

  /** Redraw the strip: the cards the owner chose, then (editing) the panel. */
  function renderHomeStrip() {
    const wrap = ensureHomeStrip();
    if (!wrap) return;
    wrap.textContent = "";
    const head = doc.createElement("h2");
    head.textContent = "Your main screen";
    wrap.appendChild(head);
    const cards = homeCardsFor(homeDoc, "desktop");
    const availability = homeAvailability();
    const grid = doc.createElement("div");
    grid.className = "hud-home-grid";
    for (const entry of cards) {
      const card = entry.card;
      const state = cardState(card.key, availability);
      const tile = doc.createElement("article");
      tile.className = `hud-home-card is-${state}`;
      tile.setAttribute("data-home-card-tile", card.key);
      const title = doc.createElement("h3");
      title.textContent = card.label;
      tile.appendChild(title);
      const line = doc.createElement("p");
      // The off state is a whole sentence, never a blank box and never JSON.
      line.textContent = stateWords(card, state);
      tile.appendChild(line);
      const open = doc.createElement("button");
      open.type = "button";
      open.className = "hud-home-open";
      open.setAttribute("data-home-command", "open");
      open.setAttribute("data-home-card", card.key);
      open.textContent = String(card.opens).startsWith("stage:") ? "Open" : "Open Settings";
      open.title = `Open ${card.label}`;
      tile.appendChild(open);
      grid.appendChild(tile);
    }
    if (!cards.length) {
      const line = doc.createElement("p");
      line.textContent = editing
        ? "The main screen has no feature cards. Add one below."
        : "The main screen has no feature cards. Open Edit HUD to add some.";
      grid.appendChild(line);
    }
    wrap.appendChild(grid);
    if (editing) wrap.appendChild(homeEditorBlock());
  }

  /** One writer for the main-screen document - Add, Remove, move, reset. */
  function homeAction(action) {
    const result = applyHomeAction(homeDoc, action);
    if (!result.changed) {
      if (result.note) announce(result.note);
      const status = byId("hud-home-cards-status");
      if (status && result.note) status.textContent = result.note;
      return result;
    }
    homeDoc = result.doc;
    const answer = writeHomeDoc(homeDoc);
    renderHomeStrip();
    const status = byId("hud-home-cards-status");
    const said = answer.saved ? result.note : `Not saved: ${answer.error}.`;
    if (status) status.textContent = said;
    if (!answer.saved) announce(said);
    return result;
  }

  function onHomeClick(event) {
    const button = event.target && event.target.closest
      ? event.target.closest("[data-home-command]") : null;
    if (!button) return;
    event.preventDefault();
    const command = button.getAttribute("data-home-command");
    const key = button.getAttribute("data-home-card");
    if (command === "open") { openHomeCard(key); return; }
    if (!editing) return;
    if (command === "add") homeAction({ type: "addCard", key });
    else if (command === "remove") homeAction({ type: "removeCard", key });
    else if (command === "up") homeAction({ type: "moveCard", key, delta: -1 });
    else if (command === "down") homeAction({ type: "moveCard", key, delta: 1 });
    else if (command === "switch") homeAction({ type: "setCardOn", key });
    else if (command === "reset") homeAction({ type: "resetHome" });
  }

  // ------------------------------------------------------------------- mount
  function wire() {
    doc.addEventListener("click", onToolbarClick);
    doc.addEventListener("click", onHomeClick);
    doc.addEventListener("change", onRegionChange);
    doc.addEventListener("pointerdown", onPointerDown, true);
    doc.addEventListener("pointermove", onPointerMove, true);
    doc.addEventListener("pointerup", onPointerUp, true);
    doc.addEventListener("pointercancel", onPointerUp, true);
    doc.addEventListener("keydown", onKeyDown);
    ensureBar();
    ensureToggle();
    // The bootstrap pushes the saved layout (H1) and asks for edit mode when
    // Settings opens this window for editing.
    const adopt = (doc) => {
      if (editing || !doc) return;
      layout = normalizeLayout(doc);
      render();
    };
    globalThis.addEventListener("jarvis:hud-layout", (event) => adopt(event.detail));
    // The bootstrap's read is asynchronous and the editor may mount first.
    // Poll briefly for its global/event result, then stop (no timer leaks).
    let tries = 0;
    const waitForLayout = setInterval(() => {
      tries += 1;
      if (globalThis.__jarvisHudLayout) adopt(globalThis.__jarvisHudLayout);
      if (tries >= 20 || globalThis.__jarvisHudLayout) clearInterval(waitForLayout);
    }, 100);
    globalThis.addEventListener("jarvis:hud-edit-request", () => setEditing(true));
  }

  async function boot() {
    // The H1 bootstrap owns the SAVED document; this page must not read the
    // store itself at boot - that read would save a migrated layout as a side
    // effect, and a page load is not an edit. Until the bootstrap pushes its
    // answer, the old three-way value is the honest preview.
    // F1 (2026-10-22): the bootstrap's saved document is the only source;
    // this page no longer reads the retired localStorage layout key. Until it
    // arrives, Cockpit is the honest preview, exactly as the page paints.
    layout = globalThis.__jarvisHudLayout
      ? normalizeLayout(globalThis.__jarvisHudLayout)
      : presetLayout("cockpit");
    // PWA slice 2: a browser has no bootstrap to push a saved document, so
    // the editor reads THIS browser's own layout (hud-layout-store.js's
    // browser branch: localStorage, never the host PC's store). The desktop
    // path above is untouched: with a shell the bootstrap still pushes.
    if (!shellPresent && globalThis.__JARVIS_WEB_MODE) {
      try {
        const answer = await store.loadLayout();
        if (answer && answer.layout) layout = normalizeLayout(answer.layout);
      } catch { /* the page keeps the Cockpit preview */ }
    }
    homeDoc = readHomeDoc();
    wire();
    render();
    updateEditButton();
    return controller;
  }

  const controller = {
    get layout() { return layout; },
    get editing() { return editing; },
    get homeCards() { return normalizeHomeCards(homeDoc); },
    homeAction(action) { return homeAction(action); },
    setLayout(next) { layout = normalizeLayout(next); render(); },
    enter() { setEditing(true); },
    exit() { setEditing(false); },
    apply(action) { return doAction(action); },
    render,
    undo,
    flush: flushSave,
    sizeKeyFor,
  };
  return boot();
}
