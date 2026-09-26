/**
 * "Things you can say" - about 5-8 real sentences Jarvis already answers
 * WITHOUT the AI model, in place of the Jarvis bar's old 10 shortcut-key
 * rows.
 *
 * Already approved as feasibility idea I116 ("Served by the PC; fills the
 * box, never sends") and picked up by the ease-of-use audit's own do-first
 * table, row 4 (docs/EASE-OF-USE-AUDIT-2026-09-27.md): "They replace the 10
 * shortcut rows in the empty Jarvis bar, with one line 'More: right-click
 * the Jarvis icon by the clock.' Also one 'what can you do?' command
 * answered from the same list, 3 examples on walkthrough screen 2, and a
 * Help answer in both apps. Tapping a line fills the box and never sends."
 * The audit's own critic (docs/ease-audit-2026-09-27/critic.md section 3.3)
 * scoped the fuller original design (a searchable, grouped "/" command
 * palette) down to this: one flat list, in fewer places.
 *
 * The words are backend/jarvis_sayable.py's - the same "one source, both
 * apps read it" pattern manner.js and card-words.js use. Unlike reach.js
 * (settings-dependent, fetched live from `/api/reach`), this list is fixed
 * text with no settings behind it, so it is hardcoded here rather than
 * fetched: the empty bar is the FIRST thing painted, often before the
 * backend answers at all, and an offline Jarvis should still say what it
 * can do without the model. tests/sayable.mjs holds every word here to
 * tests/fixtures/sayable-cases.json, which tools/gen_sayable_cases.py makes
 * from the backend - the phone's SayableContractTest reads the same file,
 * so the two apps cannot carry a different list.
 *
 * No page, no Tauri: node can import it.
 *
 * @module sayable
 */

/** The words above the list. */
export const TITLE = "Things you can say";
export const DETAIL = "Real sentences Jarvis already answers without the AI model. Tap one to " +
  "put it in the box - it does not send.";

/** The line replacing the bar's old shortcut rows, pointing at Settings ->
 *  Shortcuts, where the rebindable hotkeys live now. */
export const FOOTER = "More: right-click the Jarvis icon by the clock.";

/** The list itself, in the order it is shown - jarvis_sayable.SENTENCES,
 *  word for word (test_sayable.py proves every one really works). */
export const SENTENCES = Object.freeze([
  "Set a timer for 10 minutes.",
  "What did I miss?",
  "Tell me when an email from Alex arrives.",
  "Focus for 30 minutes.",
  "Remind me to call Mom at 6pm.",
  "Add milk to the shopping list.",
  "Brief me now.",
]);

/** Three of the list, for the walkthrough's screen 2 only (never screen 1
 *  or 3) - jarvis_sayable.WALKTHROUGH_EXAMPLES. */
export const WALKTHROUGH_EXAMPLES = Object.freeze([
  "Set a timer for 10 minutes.",
  "What did I miss?",
  "Remind me to call Mom at 6pm.",
]);

/** The Help/FAQ answer - jarvis_sayable.HELP_TITLE / HELP_BODY. */
export const HELP_TITLE = "What can I say?";
export const HELP_BODY = "Jarvis answers some sentences straight away, without the AI model - " +
  "so they work even when the model is slow, unloaded or asleep. A few real ones: " +
  SENTENCES.join(" ") + " Type \"what can you do?\" any time to see this list again. " +
  "Anything else goes to the AI model as before.";

/**
 * Builds the primer's list of tappable example lines. Each button's click
 * calls `onPick(sentence)` - the caller fills the input box with it and
 * never sends (the owner's own tap, then typing Enter or pressing Send, is
 * what sends). Returns a `<ul>` the caller appends; nothing here touches
 * `document` beyond creating elements, and nothing here calls `fetch` or
 * `invoke` - see the module comment for why this is a fixed list, not a
 * live one.
 *
 * @param {(text: string) => void} onPick
 */
export function buildSayableList(onPick) {
  const ul = document.createElement("ul");
  ul.className = "sayable-list";
  ul.setAttribute("aria-label", TITLE);
  for (const sentence of SENTENCES) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sayable-item";
    button.textContent = sentence;
    // aria-label spells out the behaviour for anyone using a screen reader:
    // the visible text alone would not say that this fills, not sends.
    button.setAttribute("aria-label", `Put "${sentence}" in the box`);
    button.addEventListener("click", () => onPick(sentence));
    li.append(button);
    ul.append(li);
  }
  const footer = document.createElement("li");
  footer.className = "sayable-foot";
  footer.textContent = FOOTER;
  ul.append(footer);
  return ul;
}
