/**
 * Search inside Settings.
 *
 * WHY THIS EXISTS. Settings is one scroll of 38 cards, and the "Jump to:" bar
 * above it is a map you have to read before it helps. The owner's request of
 * 2026-10-09: "a lot more visually simple, with a search bar in settings. I
 * still want everything adjustable, just easier to find and more efficient."
 * The jump list is kept - it is still the fastest way to a section you
 * already know - and this is the way to a setting whose card you do NOT know.
 *
 * WHAT SEARCH IS ALLOWED TO DO. Show and hide what is already on the page, and
 * put the matches in a better order while the box has words in it. That is the
 * whole of it:
 *
 *   - no setting is added, removed, renamed, moved for good or hidden for good;
 *   - nothing is written anywhere - this module contains no `invoke(`, no
 *     `fetch(`, and touches no storage (the rule tests/palette.mjs holds
 *     palette.js and palette-ui.js to, applied here too);
 *   - clearing the box restores the page exactly, because filtering only
 *     ever sets and clears the `hidden` attribute on things that were
 *     visible, and remembers what was NOT visible for a different reason.
 *
 * HIDDEN BY A MENU IS A DIFFERENT FACT FROM HIDDEN BY A SEARCH. "Show or
 * hide menus" (menu-visibility-settings.js) already hides cards, and if a
 * search wrote `card.hidden = false` for a match it would quietly un-hide a
 * menu the owner chose to hide - and clearing the box would leave it
 * showing. So that module records `data-menu-hidden` on every card it hides,
 * and this module treats that attribute as "not mine to show":
 *
 *     visible = (no search) ? !data-menu-hidden
 *                           : (matches && !data-menu-hidden)
 *
 * THE UNIT OF A MATCH is a "part":
 *
 *   - a row that can itself be found - the toggle rows and the theme rows,
 *     each carrying `data-search-row` - matched on its own words only, so a
 *     hit says which SWITCH matched rather than "something in this card";
 *   - everything else in the card, matched as one run of text.
 *
 * A card is shown when any of its parts matches, and the WHOLE card is shown
 * when it is: a switch whose detail paragraph matched is useless with that
 * paragraph folded away. The words searched are the words visible at that
 * moment, which is also what the owner can see to type.
 *
 * The matching itself is pure and lives in `rank`, because that is the part
 * worth testing on its own; the phone's `SettingsSearch.kt` implements the
 * same rules in Kotlin - the tiers, the edit budgets and the prefix guard
 * below are a contract between the two apps, not a local choice, so a change
 * here is a change there.
 *
 * ONE TYPO MUST NOT HIDE A SETTING (2026-10-10). Strict "does the text
 * contain the query" matching meant `notifcation` found nothing at all and
 * the page said the setting did not exist - the worst possible answer for a
 * search box whose whole job is finding a card whose name you half-remember.
 * So the words typed are compared word by word, and each word may be a
 * little misspelt; see `rankWords` for the tiers and `fuzzyBudget` for how
 * misspelt is allowed to be. What did NOT change: search still only shows
 * and hides what is already on the page, and `data-menu-hidden` still wins.
 *
 * RESULTS ARE RANKED, NOT LEFT WHERE THEY SIT (the owner, 2026-10-27). He
 * searched "update" in Settings and the Updates card was not the first thing
 * that came up: matches were shown in the order the cards are drawn, and the
 * page's own `Everyday`/`Rare` split put Updates far down it. The split is
 * gone from `settings.html`, and this module now orders what it shows by WHERE
 * the words matched:
 *
 *   1. the card's own title, or a name the menus catalogue already answers to
 *      for that card (`menu-catalog.js`, generated from the backend's list) -
 *      exact, then prefix, then a typo;
 *   2. a labelled row inside the card, by the same tiers;
 *   3. the card's detail text.
 *
 * Ties go to the shorter title, because the words typed then cover more of it
 * ("update" is more of "Updates" than of "Check for tool updates"), then to
 * the title itself. Nothing reads the section a card sits in, the band it used
 * to be in, or the page's document order: a result's place is a fact about the
 * words on the card and the words typed. `cardRank` and `compareMatches` are
 * the pure half, so they can be tested in plain node.
 *
 * While a search is on, the one remaining page heading ("What Jarvis does") is
 * put away with the jump list: a ranked list with a category heading partway
 * down it is two orders at once. Everything comes back, in its original order,
 * when the box is cleared.
 *
 * @module settings-search
 */

import { MENUS } from "./menu-catalog.js";

/**
 * The names the menus catalogue answers to, per settings card - the same
 * aliases "open <that card>" already uses (menu-catalog.js, generated from
 * `backend/jarvis_menus.py`). They extend a card's TITLE for ranking, so
 * "app updates" or "update" finds the Updates card even though those exact
 * words are not all printed on it. Normalised once, at load.
 */
const CATALOGUE_WORDS = (() => {
  const words = new Map();
  for (const menu of MENUS) {
    if (!menu || typeof menu.id !== "string" || !menu.id.startsWith("settings.")) continue;
    const names = Array.isArray(menu.names)
      ? menu.names.filter((name) => typeof name === "string" && name.trim())
      : [];
    if (names.length) words.set(menu.id.slice("settings.".length), normalise(names.join(" ")));
  }
  return words;
})();

/** The box's words, the same on the phone (`SettingsSearchWords`). */
export const SEARCH_LABEL = "Search settings";
export const SEARCH_PLACEHOLDER = "Search settings…";
export const SEARCH_CLEAR = "Clear";
export const SEARCH_HINT = "Type a word to show only the settings that match.";

/** What the page says when nothing matches. `{q}` is the words typed. */
export const SEARCH_NONE = "Nothing here matches “{q}”.";

/** The line under it, so a miss never reads as "that setting does not exist". */
export const SEARCH_NONE_BACK = "Clear the box and everything comes back.";

/** The live count. `{n}` is how many cards are left showing. */
export const SEARCH_ONE = "1 setting matches.";
export const SEARCH_MANY = "{n} settings match.";

/** The band headings, in page order. A band with nothing left is hidden. */
const BAND = ".settings-group-heading";

/** A row that is a unit of its own. */
const ROW = "[data-search-row]";

/** Not text a person can read: controls, and the viewer's own words. */
const UNSEARCHABLE = "input, textarea, select, option, script, style, title";

/**
 * The words of a search: lower-cased, accents dropped, every run of
 * punctuation and space collapsed to one space. `rank`'s first rule, and the
 * phone's `SettingsSearch.normalise`.
 *
 * `NFD` splits "é" into "e" + a combining accent, and the `\p{M}` pass drops
 * the accent, so "cafe" finds "café" - which matters here because the page
 * says "Jarvis's" and "naïve" in its own words.
 */
export function normalise(text) {
  return String(text == null ? "" : text)
    .normalize("NFD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/**
 * How well one part matched, for the caller that may want to order results.
 * 0 means no match. `SettingsSearch.kt` uses the same four numbers.
 */
const EXACT = 4;   // the token IS a word of the label ("voice" -> "Your voice")
const PREFIX = 3;  // the token starts a word of the label ("voic" -> "Voice")
const FUZZY = 2;   // the token is a near miss of a word of the label
const DETAIL = 1;  // the token is somewhere in the part's own text

/** How many letters a fuzzy match must keep, and they are the first ones. */
const GUARD = 2;

/**
 * Does one part match, and how well? Pure - no DOM.
 *
 * The query is split into words and EVERY word must be found in this one part
 * (AND, not OR): "voice strict" needs both words in the SAME part, because
 * "it is somewhere in the card" is exactly the vagueness the box exists to
 * remove. The part's rank is the weakest word's rank, so one exact word and
 * one near miss still ranks as a near miss.
 *
 * Within a part, one query word is looked for in this order:
 *
 *   1. EXACT, against the label's own words - "voice" finds "Your voice";
 *   2. PREFIX, against the label's own words - "voic" finds "Voice";
 *   3. FUZZY, against the label's own words - "voise" finds "Voice";
 *   4. DETAIL, anywhere in the part's text - a paragraph mentioning it in
 *      passing still shows the card (the old rule 3, kept as the floor).
 *
 * Steps 1-3 run against the label's words rather than the whole label, which
 * is what makes a heading match beat a body match: a word of the heading is
 * worth more than the same word buried in a paragraph. A token that equals a
 * word counts as EXACT even when another word in the label begins with it -
 * "cat" is the word "cat" in "Cat chat", not merely a prefix of "catalogue".
 *
 * A rank is returned rather than a boolean so the four tiers stay named and
 * ordered (the phone ranks the same way); 0 means no match. Both sides went
 * through `normalise` first, which is also why "wi fi" finds "Wi-Fi".
 */
export function rank(label, text, query) {
  return rankWords(normalise(label), normalise(text), normalise(query));
}

/**
 * How well one card matches the query: the best of its own words (title plus
 * the catalogue's names for it, where an exact or prefix hit outranks the
 * body), its labelled rows, and its detail text. Pure - no DOM, no order - so
 * it runs in plain node.
 *
 * `parts` is the shape `partsOf` returns: `{ label, text, rows }` with `label`
 * and `text` already through `normalise`, and `rows` a list of normalised row
 * texts. 0 means no match.
 */
export function cardRank(parts, query) {
  const q = normalise(query);
  if (!q) return 0;
  let best = rankWords(parts.label, parts.text, q);
  for (const row of parts.rows || []) {
    const rank = rankWords(row, row, q);
    if (rank > best) best = rank;
  }
  return best;
}

/**
 * The order two matches are shown in: the stronger match first; equal matches
 * by the SHORTER title, because the words typed then cover more of it
 * ("update" is more of "Updates" than of "Check for tool updates"); then by
 * the title itself, so the order never depends on where the card happens to
 * sit. `a` and `b` are `{ rank, title }` with `title` already normalised.
 *
 * Deliberately reads nothing else: no section, no old band, no document order.
 */
export function compareMatches(a, b) {
  if (a.rank !== b.rank) return b.rank - a.rank;
  if (a.title.length !== b.title.length) return a.title.length - b.title.length;
  return a.title < b.title ? -1 : a.title > b.title ? 1 : 0;
}

/**
 * `rank` on words that have ALREADY been through `normalise`: the rules
 * above, and the only place they are written down. The page keeps both sides
 * normalised (see `partsFor` and `apply`), so a keystroke compares strings
 * instead of re-folding 38 cards' worth of text.
 */
function rankWords(labelWords, textWords, queryWords) {
  if (!queryWords) return 0;
  const tokens = queryWords.split(" ").filter(Boolean);
  if (!tokens.length) return 0;
  let weakest = EXACT;
  for (const token of tokens) {
    const tier = tokenTier(token, labelWords, textWords);
    // One word of the query finding nothing is the whole query finding
    // nothing: typing more words narrows, never widens.
    if (!tier) return 0;
    if (tier < weakest) weakest = tier;
  }
  return weakest;
}

/** The best one query word can do inside one part: a tier, or 0. */
function tokenTier(token, labelWords, textWords) {
  const words = labelWords ? labelWords.split(" ") : [];
  if (words.includes(token)) return EXACT;
  if (words.some((w) => w.startsWith(token))) return PREFIX;
  if (words.some((w) => nearMiss(token, w))) return FUZZY;
  // The floor: a WHOLE WORD of the part's own text, or a near miss of one.
  //
  // This was `textWords.includes(token)`, and `textWords` is a normalised
  // STRING - so `.includes` was a SUBSTRING test wearing a word test's clothes,
  // and the old "merely contains" rule the header says this work replaced was
  // still here in the body. The shared cross-app fixture caught it: with the
  // part "Sending email" / "The conversation and the catalogue of drafts both
  // kept on your PC", the query `cat` matched "catalogue" and returned DETAIL.
  // The phone had already been moved to a whole-word floor, so the two engines
  // disagreed on exactly the class of match this change exists to remove.
  if (textWords.split(" ").includes(token)) return DETAIL;
  if (textWords.split(" ").some((w) => nearMiss(token, w))) return DETAIL;
  return 0;
}

/**
 * How many edits a word may be away from the word typed and still count as
 * the same word.
 *
 * 0 for one to three letters is the important one. With a budget of one,
 * "cat" would reach "chat", "bat", "cot" and "cut", and a three-letter search
 * would light up half the page; a short word has to be typed right, or be a
 * genuine prefix of what is on the page (which still finds "cats").
 *
 * Four to seven letters may be one edit out: "voise" for "voice" is one swap,
 * "setzing" for "setting" is one wrong letter. Eight or more may be two,
 * because a long word typed quickly collects more than one slip and two edits
 * in ten letters still names one word rather than several - "notifcation" for
 * "notifications" is a letter dropped and a letter added, and it is the miss
 * this whole rule exists for.
 *
 * The phone's `SettingsSearch.fuzzyBudget` is this same rule.
 */
export function fuzzyBudget(token) {
  const n = String(token == null ? "" : token).length;
  if (n <= 3) return 0;
  if (n <= 7) return 1;
  return 2;
}

/**
 * Is `word` a plausible typo of `token`? Two gates, and both must open:
 *
 *   - the edit budget above (`fuzzyBudget`);
 *   - `GUARD` letters at the front must agree. The first letters are the
 *     part of a word a slip almost never destroys - fingers land on a middle
 *     letter, not on the whole opening - so requiring them removes the class
 *     of false match where the search locks onto a different word entirely:
 *     "cat" cannot reach "chat", and a word typed in full cannot leap to an
 *     unrelated word that happens to share its shape further in. It is why
 *     "notifcation" still reaches "notifications": both open "no".
 */
function nearMiss(token, word) {
  const budget = fuzzyBudget(token);
  if (!budget) return false;
  if (word.length < GUARD || token.slice(0, GUARD) !== word.slice(0, GUARD)) return false;
  // Cheap gate before the table: two strings further apart in LENGTH than
  // the budget cannot be within it.
  if (Math.abs(token.length - word.length) > budget) return false;
  return editsApart(token, word) <= budget;
}

/**
 * How many changes turn `a` into `b`, where a change is one insertion, one
 * deletion, one substitution, or ONE SWAP of two neighbouring letters - the
 * last is why "voise" finds "voice", the single most common way a typed word
 * goes wrong. Short strings only, so the whole table is cheap.
 */
function editsApart(a, b) {
  const m = a.length;
  const n = b.length;
  let twoBack = null;
  let back = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i += 1) {
    const row = new Array(n + 1);
    row[0] = i;
    for (let j = 1; j <= n; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      let best = Math.min(back[j] + 1, row[j - 1] + 1, back[j - 1] + cost);
      if (twoBack && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        best = Math.min(best, twoBack[j - 2] + 1);
      }
      row[j] = best;
    }
    twoBack = back;
    back = row;
  }
  return back[n];
}

/** The text a part is matched on: what a person can read inside it. */
function readableText(node) {
  let out = "";
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) {
      out += ` ${child.nodeValue}`;
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    if (child.hidden || child.matches(UNSEARCHABLE)) continue;
    out += ` ${readableText(child)}`;
  }
  return out;
}

/**
 * The card's OWN heading: an `h2` inside it whose nearest `.card` is the card
 * itself. A nested card's title is not this card's title, and a subhead
 * (`h3`) is not either.
 */
function ownTitle(card) {
  for (const heading of card.querySelectorAll("h2")) {
    if (heading.closest(".card") === card) return heading.textContent;
  }
  return "";
}

/**
 * The words a card is searched by:
 *
 *   - `label`: its own title plus the names the menus catalogue answers to for
 *     it. This is the part where an exact or prefix hit outranks a body hit -
 *     the words at the top of the card, plus the aliases the rest of the app
 *     already matches it by;
 *   - `text`: everything readable inside the card except its rows and its own
 *     title, so a word buried in a paragraph is still found (the floor);
 *   - `rows`: the labelled rows the card directly holds, each keeping its own
 *     child rows, so a row's own words are never also the card's text.
 *
 * `title` is kept normalised for the ordering rule (`compareMatches`).
 */
function partsOf(card) {
  const alias = CATALOGUE_WORDS.get(card.id) || "";
  const title = ownTitle(card);
  const outside = card.cloneNode(true);
  // A selector cannot say "everything that is not one of these", so the rows
  // are dropped from the clone by identity, then it is read as one run.
  const rows = [...outside.querySelectorAll(ROW)].filter((r) => r.closest(ROW) === r);
  for (const row of rows) row.remove();
  // The title is read as the label, not twice: leaving it in the text would
  // make every title word a body word too, and no card could rank by title.
  for (const heading of outside.querySelectorAll("h2")) {
    if (heading.closest(".card") === outside) heading.remove();
  }
  return {
    label: normalise(`${title} ${alias}`),
    text: normalise(readableText(outside)),
    rows: [...card.querySelectorAll(ROW)]
      .filter((row) => row.closest(ROW) === row)
      .map((row) => normalise(readableText(row))),
    title: normalise(title),
  };
}

/** Has this card been repainted under us since the parts were read? */
const sameParts = (parts, now) =>
  parts.label === now.label &&
  parts.text === now.text &&
  parts.title === now.title &&
  parts.rows.length === now.rows.length &&
  parts.rows.every((row, i) => row === now.rows[i]);

/**
 * Wire the search box up, once. Returns a small handle so a caller - or a
 * test - can re-run the filter after the page has changed underneath it.
 */
export function mountSettingsSearch(doc = document) {
  const input = doc.getElementById("settings-search-input");
  const clear = doc.getElementById("settings-search-clear");
  const none = doc.getElementById("settings-search-none");
  const noneWords = doc.getElementById("settings-search-none-words");
  const status = doc.getElementById("settings-search-status");
  const say = doc.getElementById("settings-search-count");
  const jump = doc.getElementById("settings-jump");
  const box = doc.getElementById("settings-search");

  /** Every card, in page order. */
  const cards = () => [...doc.querySelectorAll("main .card")];

  /**
   * The top-level blocks that carry cards, in page order: a card, or the
   * folded "More options" `<details>` holding three of them. A search moves
   * these whole blocks into rank order - never a card out of its own block -
   * and puts them back the moment the box is cleared.
   */
  function units() {
    return [...doc.querySelectorAll("main > .card, main > details")]
      .map((node) => ({
        node,
        cards: node.matches(".card")
          ? [node, ...node.querySelectorAll(".card")]
          : [...node.querySelectorAll(".card")],
      }))
      .filter((unit) => unit.cards.length > 0);
  }

  /**
   * Where every block sat when the page loaded, and what it sat after, so
   * clearing the box can put the page back exactly. `prev` is the anchor a
   * restore inserts after: blocks are restored in page order, so a `prev` that
   * is itself a block has already been put back when it is used.
   */
  const originalOrder = units().map((unit) => ({
    node: unit.node,
    prev: unit.node.previousElementSibling,
  }));
  let moved = false;

  function restoreOrder() {
    if (!moved) return;
    const main = doc.querySelector("main");
    for (const { node, prev } of originalOrder) {
      if (prev && prev.parentNode === main) main.insertBefore(node, prev.nextSibling);
      else if (main) main.insertBefore(node, main.firstChild);
    }
    moved = false;
  }

  /** Put the matched blocks, already in rank order, at the top of the page. */
  function orderMatches(ranked) {
    const main = doc.querySelector("main");
    if (!main) return;
    const bar = doc.getElementById("menus-hidden-bar");
    // Results begin where the cards begin: after the search box, jump list,
    // note and hidden-menus bar, and above every card that is not a match.
    const anchor = bar ? bar.nextSibling : originalOrder[0]?.node || main.firstChild;
    for (const unit of ranked) main.insertBefore(unit.node, anchor);
    moved = true;
  }

  /**
   * A card's parts, read once and re-read when the page repaints that card
   * underneath us. The detail text is everything OUTSIDE every row, and
   * `#af-groups`, `#crash-notes-list` and the other JS-filled boxes are inside
   * it - their words arrive after load, so a cache that never noticed would
   * search a page that no longer exists. Comparing the words is what notices;
   * the words are kept normalised because a search compares those and never
   * re-folds the text.
   */
  const cache = new Map();
  function partsFor(card) {
    const fresh = partsOf(card);
    const parts = cache.get(card);
    if (parts && sameParts(parts, fresh)) return parts;
    cache.set(card, fresh);
    return fresh;
  }

  /**
   * A card folded by "Show or hide menus" is opened for the duration of a
   * search that matches inside it, and folded back when the box is cleared -
   * a match inside a collapsed card is otherwise unreachable. The marker is
   * written on every pass, so a card opened by one search and not matched by
   * the next is put back by that next pass.
   */
  function foldBackOpenedCards() {
    for (const card of cards()) {
      if (card.dataset.searchWasCollapsed !== "true") continue;
      card.classList.add("card-collapsed");
      delete card.dataset.searchWasCollapsed;
    }
  }

  function apply() {
    const value = input ? input.value : "";
    const query = normalise(value);
    const searching = Boolean(query);
    const hiddenByMenu = (card) => card.dataset.menuHidden === "true";

    if (searching) foldBackOpenedCards();

    let showing = 0;
    const ranked = [];
    for (const unit of units()) {
      let best = null;
      for (const card of unit.cards) {
        const hidden = hiddenByMenu(card);
        let hit = false;
        if (searching) {
          const parts = partsFor(card);
          const rank = cardRank(parts, query);
          hit = rank > 0 && !hidden;
          if (
            hit
            && (!best
              || rank > best.rank
              || (rank === best.rank && parts.title.length < best.title.length))
          ) {
            best = { rank, title: parts.title };
          }
          if (hit && card.classList.contains("card-collapsed")) {
            card.classList.remove("card-collapsed");
            card.dataset.searchWasCollapsed = "true";
          }
        }
        card.hidden = searching ? !hit : hidden;
        if (!card.hidden) showing += 1;
      }
      if (best) ranked.push({ node: unit.node, rank: best.rank, title: best.title });
    }

    if (!searching) foldBackOpenedCards();

    if (searching) {
      ranked.sort(compareMatches);
      orderMatches(ranked);
    } else {
      restoreOrder();
    }

    // One heading is left ("What Jarvis does"). A ranked list with a category
    // heading partway down it is two orders at once, so it is put away while
    // searching and comes back with the rest of the page.
    for (const heading of doc.querySelectorAll(`main ${BAND}`)) {
      heading.hidden = searching;
    }

    // The jump list is a map of the WHOLE page, so while the page is filtered
    // it would point at cards that are not there. It comes back on its own.
    if (jump) jump.hidden = searching;

    const empty = searching && showing === 0;
    if (none) none.hidden = !empty;
    if (noneWords) noneWords.textContent = SEARCH_NONE.replace("{q}", value.trim());
    if (clear) clear.hidden = !searching;

    if (status) {
      status.textContent = !searching ? SEARCH_HINT
        : empty ? ""
          : (showing === 1 ? SEARCH_ONE : SEARCH_MANY.replace("{n}", String(showing)));
    }
    // The live region is written only when the ANSWER changes: a count that
    // re-announced on every keystroke would talk over the owner's typing.
    if (say && searching && !empty) {
      const line = showing === 1 ? SEARCH_ONE : SEARCH_MANY.replace("{n}", String(showing));
      if (say.textContent !== line) say.textContent = line;
    }
    doc.body.classList.toggle("searching", searching);
  }

  function focusBox() {
    if (!input) return;
    input.focus();
    input.select();
  }

  function clearBox() {
    if (!input) return;
    input.value = "";
    apply();
    input.focus();
  }

  if (input) {
    input.addEventListener("input", apply);
    input.addEventListener("search", apply); // the field's own ✕, where drawn
  }
  if (clear) clear.addEventListener("click", clearBox);
  if (box) {
    box.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !input || !input.value) return;
      event.stopPropagation();
      clearBox();
    });
    doc.addEventListener("keydown", (event) => {
      // Ctrl+F and Alt+F, the two things a person tries in a long page.
      // Nothing else here binds either key: settings.js's only global keys
      // are the zoom ones (Ctrl with +, - and 0).
      if (!(event.ctrlKey || event.altKey) || event.shiftKey || event.metaKey) return;
      if (event.key !== "f" && event.key !== "F") return;
      event.preventDefault();
      focusBox();
    });
  }

  apply();
  return { apply, focusBox, clearBox };
}

if (typeof document !== "undefined" && document.getElementById("settings-search")) {
  mountSettingsSearch();
}
