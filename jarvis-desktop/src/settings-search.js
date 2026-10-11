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
 * WHAT SEARCH IS ALLOWED TO DO. Show and hide what is already on the page.
 * That is the whole of it:
 *
 *   - no setting is added, removed, renamed, moved or hidden for good;
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
 * same three rules in Kotlin.
 *
 * @module settings-search
 */

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
 * Does one part match, and how well? Pure - no DOM.
 *
 * Three rules, in order, and the first two are deliberately stricter than a
 * plain "contains":
 *
 *   1. an empty query matches nothing (the caller shows everything instead,
 *      so it is never reached with one);
 *   2. the label equals the query, or starts with it, or a word in the label
 *      does - "voice" finds "Your voice", and "check" finds "Voice check:
 *      how strict";
 *   3. otherwise the whole part's text merely contains the query - "who can
 *      see my chats" finding a paragraph that mentions it in passing.
 *
 * A rank is returned rather than a boolean so a caller can order results if
 * it ever wants to; 0 means no match. Rules 2 and 3 are also why "wi fi"
 * finds "Wi-Fi": both sides went through `normalise` first.
 */
export function rank(label, text, query) {
  return rankWords(normalise(label), normalise(text), normalise(query));
}

/**
 * `rank` on words that have ALREADY been through `normalise`: the same three
 * rules, and the only place they are written down. The page keeps both sides
 * normalised (see `partsFor` and `apply`), so a keystroke compares strings
 * instead of re-folding 38 cards' worth of text.
 */
function rankWords(labelWords, textWords, queryWords) {
  if (!queryWords) return 0;
  if (labelWords) {
    if (labelWords === queryWords) return 3;
    if (labelWords.startsWith(queryWords)) return 2;
    if (labelWords.split(" ").some((w) => w.startsWith(queryWords))) return 2;
  }
  return textWords.includes(queryWords) ? 1 : 0;
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
 * Split a card into parts: the labelled rows it directly holds (each keeping
 * its own child rows, so a row's words are never also the card's), plus
 * everything else as one run.
 */
function partsOf(card) {
  const parts = [];
  const outside = card.cloneNode(true);
  // A selector cannot say "everything that is not one of these", so the rows
  // are dropped from the clone by identity, then it is read as one run.
  const rows = [...outside.querySelectorAll(ROW)].filter((r) => r.closest(ROW) === r);
  for (const row of rows) row.remove();
  const rest = readableText(outside);
  if (normalise(rest)) parts.push({ node: card, words: rest, named: false });
  for (const row of [...card.querySelectorAll(ROW)].filter((r) => r.closest(ROW) === r)) {
    parts.push({ node: row, words: readableText(row), named: true });
  }
  return parts;
}

/** Has this card been repainted under us since the parts were read? */
const sameParts = (parts, now) =>
  parts.length === now.length &&
  parts.every((p, i) => p.node === now[i].node && p.words === now[i].words);

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

  /** Bands and their cards, in page order: headings sit between cards. */
  function bands() {
    const out = [];
    let current = null;
    for (const node of doc.querySelectorAll(`main .card, main ${BAND}`)) {
      if (node.matches(BAND)) {
        current = { heading: node, cards: [] };
        out.push(current);
      } else if (current) {
        current.cards.push(node);
      } else {
        // A card above the first band - there is none today - belongs to none.
        out.push({ heading: null, cards: [node] });
      }
    }
    return out;
  }

  /**
   * A card's parts, read once and re-read when the page repaints that card
   * underneath us. `rest` is the text OUTSIDE every row, and `#af-groups`,
   * `#crash-notes-list` and the other JS-filled boxes are inside it - their
   * words arrive after load, so a cache that never noticed would search a
   * page that no longer exists. Comparing the words is what notices. The
   * normalised forms are kept beside them, because a search compares those
   * and never re-folds the text.
   */
  const cache = new Map();
  function partsFor(card) {
    const fresh = partsOf(card);
    const parts = cache.get(card);
    if (parts && sameParts(parts, fresh)) return parts;
    for (const part of fresh) {
      part.words = { raw: part.words, norm: normalise(part.words) };
    }
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
    for (const card of cards()) {
      const hidden = hiddenByMenu(card);
      if (searching) {
        let hit = false;
        for (const part of partsFor(card)) {
          const rank = part.named
            ? rankWords(part.words.norm, part.words.norm, query)
            : rankWords("", part.words.norm, query);
          if (rank > 0) { hit = true; break; }
        }
        card.hidden = !(hit && !hidden);
        if (hit && !hidden && card.classList.contains("card-collapsed")) {
          card.classList.remove("card-collapsed");
          card.dataset.searchWasCollapsed = "true";
        }
      } else {
        card.hidden = hidden;
      }
      if (!card.hidden) showing += 1;
    }

    if (!searching) foldBackOpenedCards();

    for (const band of bands()) {
      if (!band.heading) continue;
      band.heading.hidden = searching && !band.cards.some((c) => !c.hidden);
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
