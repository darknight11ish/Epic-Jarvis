/**
 * "Open the card" - one line at the top of Settings and the Brain while an
 * approval card waits, with a button that opens the Jarvis bar on it.
 *
 * Many buttons in those two windows raise a card: a switch that loosens a
 * rule, "Set up" for the morning briefing, a web search key, a voice
 * setting, a model to install. Each one used to say "Asked. Your PC shows
 * an approval card..." and leave the owner to find it; the card often sat
 * unseen and ran out of time (creativity audit, 2026-09-25, finding 5).
 * One line per window, rather than a link under each of twenty buttons,
 * so no button that raises a card can be missed - including ones added
 * later - and a card raised by voice while Settings is open shows here too.
 *
 * The button DECIDES NOTHING. It calls `open_approval_in_quickbar`, which
 * opens the Jarvis bar - behind App lock, so Windows Hello is asked first
 * when the lock is on - on that card, where Deny and Approve are. The
 * line shows the card's title only (card-words.js), never `detail` or
 * `prompt`: the title is built by the PC from its own tables.
 *
 * The phone has the same line on every screen but Home (`CardWaitingLine`
 * in MainActivity.kt), with the same words.
 *
 * @module card-link
 */

import { onQueue, openCardInBar } from "./jarvis-link.js";
import { CARD_KICKER, cardTitle } from "./card-words.js";

/** The button's words, the same on the phone. */
export const OPEN_CARD = "Open the card";

/**
 * What the line says for a queue, or null when nothing waits. Pure.
 * The card named is the LAST one read - the phone's `CardWords.waiting`
 * picks the same one - most likely the one the owner's last click raised;
 * "and N more" says the rest are there too.
 */
export function cardLinkView(items) {
  const list = Array.isArray(items) ? items.filter((i) => i && i.id) : [];
  if (!list.length) return null;
  const newest = list[list.length - 1];
  const more = list.length - 1;
  return {
    id: String(newest.id),
    kicker: CARD_KICKER,
    title: cardTitle(newest),
    more: more > 0 ? `and ${more} more waiting` : "",
    button: OPEN_CARD,
  };
}

/** Fills `host` and keeps it in step with the approval queue. */
export function mountCardLink(host) {
  if (!host) return;
  const kicker = document.createElement("span");
  kicker.className = "card-link-kicker";
  const title = document.createElement("span");
  title.className = "card-link-title";
  const more = document.createElement("span");
  more.className = "card-link-more";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "btn card-link-open";
  open.textContent = OPEN_CARD;
  const said = document.createElement("span");
  said.className = "card-link-said";
  said.setAttribute("role", "status");
  host.replaceChildren(kicker, title, more, open, said);

  let current = null;
  open.addEventListener("click", async () => {
    if (!current) return;
    said.textContent = "";
    try {
      await openCardInBar(current.id);
    } catch (error) {
      said.textContent = `Could not open the Jarvis bar: ${String((error && error.message) || error)}`;
    }
  });

  onQueue((queue) => {
    current = cardLinkView(queue && queue.items);
    host.hidden = !current;
    if (!current) return;
    kicker.textContent = current.kicker;
    title.textContent = current.title;
    more.textContent = current.more;
    more.hidden = !current.more;
  });
}
