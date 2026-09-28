/**
 * Today cards (the owner's choice of 2026-09-28, the research audit's idea
 * 6; JARVIS-API.md section 82; backend jarvis_today.py) - the words, and how
 * to read what the PC sends.
 *
 * Short notes in the owner's own words ("Gym bag") that show on the Today
 * part of the Brain's Work tab at a time, on chosen days, from that time to
 * the end of the day - plus the briefing's own parts (the weather from the
 * owner's own Home Assistant, the calendar, new email, what is still to come
 * today) from the latest briefing made today. Nothing new is read for it:
 * the cards come from `brain_schedule` (they are jobs of kind "today" on the
 * one scheduler) and the briefing parts from `brain_briefing`, both already
 * read for Coming up and Morning briefing.
 *
 * The Today page itself was designed but never built; the feasibility audit
 * said it may only grow out of what is already there, never become a fourth
 * summary. So it is this one card, above Coming up, on the same tab as the
 * briefing.
 *
 * No approval card: like a plain repeating reminder, only the owner's own
 * words or taps can set one, it acts on nothing, and Delete is immediate.
 * Adding one is held on a stale link (brain_schedule_add_today), like every
 * change here. While the private lists are hidden, Rust has already taken
 * the words out; the times stay.
 *
 * The phone says the same words (net/Today.kt); tests/today.mjs checks
 * that they match, and that the PC's own words (jarvis_today.py) are these.
 *
 * @module today
 */

export const TODAY_TITLE = "Today";
export const TODAY_DETAIL =
  "Your own cards, shown at the times and on the days you choose, and the parts of your " +
  "latest briefing. Kept on your PC; nothing new is read for this page, and adding a card " +
  "needs no approval card.";
export const EMPTY_CARDS = "No cards for today yet.";
export const LATER_TITLE = "Later today";
export const FROM_BRIEFING = "From your briefing";
export const NO_BRIEFING_TODAY =
  "No briefing made today yet - \"Brief me now\" under Morning briefing puts one together.";
export const HINT =
  "Or say \"show gym bag on my Today page on Mondays and Wednesdays at 7\". " +
  "Delete removes a card at once; it is also under Coming up, where Pause skips it.";

/** The small form. */
export const ADD_TITLE = "Add a card";
export const TEXT_PLACEHOLDER = "What the card says, like Gym bag";
export const TIME_LABEL = "From";
export const DAYS_LABEL = "On";
export const ADD_LABEL = "Add";
export const DELETE_LABEL = "Delete";
export const DAY_SHORT = Object.freeze(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);

/** The PC's own words (jarvis_today.py). */
export const MAX_TEXT = 80;
export const NO_WORDS = "A Today card needs some words: what should it say?";
export const TOO_LONG = `A Today card is at most ${MAX_TEXT} characters - say it more briefly.`;
export const NO_DAYS = "Pick at least one day.";
export const BAD_TIME = "Write the time as HH:MM, like 07:00.";
export const MISSING =
  "Your PC's Jarvis cannot do Today cards yet - run apply-patches.ps1 on the PC.";

/** The kind on the scheduler, and its tag in Coming up. */
export const KIND = "today";
export const TAG = "today card";

/** The briefing parts shown here, in this order - never news (outside text the
 *  owner reads in full under Morning briefing). */
export const BRIEFING_PARTS = Object.freeze(["weather", "calendar", "email", "today"]);

/**
 * The owner's cards from `readSchedule`'s view (coming-up.js): each with
 * `today` ("showing" / "later" / "") and `showsAt` ("07:00"), as the PC
 * worked them out by its own clock.
 */
export function cardsOf(view) {
  const jobs = view && Array.isArray(view.jobs) ? view.jobs : [];
  return jobs.filter((j) => j.kind === KIND).map((j) => ({
    id: j.id,
    text: j.text,
    hidden: j.hidden === true,
    state: j.state,
    today: j.today === "showing" || j.today === "later" ? j.today : "",
    showsAt: j.showsAt || "",
    repeat: j.repeat || "",
  }));
}

/** {showing, later}: the cards on today's page, and those later today. */
export function todayCards(cards) {
  const list = Array.isArray(cards) ? cards : [];
  const byTime = (a, b) => a.showsAt.localeCompare(b.showsAt);
  return {
    showing: list.filter((c) => c.today === "showing").sort(byTime),
    later: list.filter((c) => c.today === "later").sort(byTime),
  };
}

/** A card's words, or a stand-in while the private lists are hidden. */
export function cardTitle(card) {
  return card.hidden || !card.text ? `(hidden) ${TAG}` : card.text;
}

/** "From 07:00" - under a card. */
export function cardMeta(card) {
  return card.showsAt ? `From ${card.showsAt}` : "";
}

/** Is `made` (epoch seconds) today, by this device's clock? */
export function madeToday(made, nowMs = Date.now()) {
  if (typeof made !== "number" || !Number.isFinite(made)) return false;
  const a = new Date(made * 1000);
  const b = new Date(nowMs);
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

/**
 * The latest briefing's parts to show as cards: [{key, title, summary,
 * items, state}] - only a briefing made today, and never "What did I miss?"
 * (it is not a briefing). Its lines are already gone while hidden.
 */
export function briefingCards(briefingView, nowMs = Date.now()) {
  const b = briefingView && briefingView.briefing;
  if (!b || b.source === "missed" || !madeToday(b.made, nowMs)) return null;
  const out = [];
  for (const key of BRIEFING_PARTS) {
    const s = b.sections.find((x) => x.key === key);
    if (s) out.push({ ...s, items: b.hidden ? [] : s.items });
  }
  return out;
}

const HHMM = /^([01]?\d|2[0-3]):([0-5]\d)$/;

/**
 * The arguments for brain_schedule_add_today, or {error} in both apps'
 * words. `days` are 0 (Monday) to 6.
 */
export function addArgs(text, at, days) {
  const t = String(text || "").split(/\s+/).filter(Boolean).join(" ");
  if (!t) return { error: NO_WORDS };
  if ([...t].length > MAX_TEXT) return { error: TOO_LONG };
  const m = HHMM.exec(String(at || "").trim());
  if (!m) return { error: BAD_TIME };
  const d = [...new Set((days || []).filter((x) => Number.isInteger(x) && x >= 0 && x <= 6))]
    .sort();
  if (!d.length) return { error: NO_DAYS };
  return { text: t, at: `${m[1].padStart(2, "0")}:${m[2]}`, days: d };
}
