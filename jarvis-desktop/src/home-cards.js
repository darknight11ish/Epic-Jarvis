/**
 * home-cards.js - which Jarvis FEATURES sit on the main screen, in what order
 * (the owner's requirement of 2026-10-29: *"for features that I would like
 * EASILY accessible ... make sure I can add them to the main screen through the
 * edit jarvis hud on desktop and make an equivalent edit android hud for the
 * android app"*).
 *
 * WHAT THIS IS, IN PLAIN WORDS. The HUD's main screen can show a row of cards,
 * one per Jarvis feature the owner wants within one click - Today, Calendar,
 * Memory, Pictures, Voice check, Settings and so on. This module is the one
 * place that says WHICH features may be a card (the catalogue), what each one
 * is called, which of the two apps can draw it, how big it is, and how a
 * document someone pasted or hand-edited becomes a safe choice. It draws
 * nothing and saves nothing; `hud-edit.js` draws the add/remove/reorder panel,
 * `jarvis_hud.html` draws the cards, and `home-cards-store.js` saves them.
 *
 * WHY THE KEYS ARE `features/features.json`'s OWN IDS. Both apps already ship
 * that file byte-identical (`tools/check_feature_list.py` holds the three
 * copies together), it is the list of everything Jarvis can do, and every
 * entry has a `surface` saying which app has it. Using its ids as the card keys
 * means a card can never name a feature that does not exist, and "one id is one
 * feature in both apps" is the same rule `MenuCatalog` already runs on. A card
 * is a DOOR to something that already exists, never a second copy of it.
 *
 * WHAT IS DELIBERATELY NOT IN THE CATALOGUE. The safety surfaces - the
 * approvals queue, Stop everything, app lock, "What asks first", the stale-link
 * warning - are not cards and cannot be made into one. Ruling 25 (2026-10-21)
 * already says a layout may never hide or move the one surface a pending
 * approval must reach, and the phone's own model repeats it. Keeping them out
 * of the catalogue makes that rule a property of the data instead of a check
 * somebody could forget: there is no key an owner, a hand-edited file or a
 * hostile document could add, remove or reorder to reach them.
 *
 * NOT THE SAME QUESTION AS `hud-layout.js`. That module arranges the HUD's own
 * panels (the rails, the stage, the inspector cards). This one chooses which
 * FEATURES are on the main screen. A card here is not a card there, and neither
 * list may be read as the other.
 *
 * NO DEPENDENCY, NO BUILD STEP. Plain ES module, imported by the HUD page
 * (through `hud-edit.js` and its own inline glue), by `home-cards-store.js` and
 * by `tests/home-cards.mjs`. There is no DOM in this file, so every rule here
 * runs in plain Node.
 *
 * @module home-cards
 */

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

/** The cards the main screen actually draws, in order, for one app. */
export function homeCardsFor(doc, app = "desktop") {
  const clean = normalizeHomeCards(doc);
  return clean.cards
    .filter((entry) => {
      const card = BY_KEY.get(entry.key);
      return Boolean(card) && card.apps.includes(app);
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
function renumber(cards) {
  cards.forEach((entry, index) => { entry.order = index; });
  return cards;
}

function clampInt(value, lo, hi, fallback) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(n)) return fallback;
  return Math.min(hi, Math.max(lo, n));
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
      ? normalizeHomeCards({ ...base, cards: renumber(cards),
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
