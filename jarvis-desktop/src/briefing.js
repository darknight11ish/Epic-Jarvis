/**
 * The morning briefing (the owner's decisions of 2026-09-25; JARVIS-API.md
 * section 22; backend jarvis_briefing.py) - the words, and how to read what
 * the PC sends.
 *
 * A short list of the day, put together on the PC WITHOUT the AI model:
 * today's calendar (only when it is set up for Jarvis), today's alarms,
 * reminders and timers, the to-do list, how many approval cards wait, and -
 * only when email is set up - how many unread emails and who the newest are
 * from (the owner's decision of 2026-09-25), or the number only when the
 * owner turns "Show who new emails are from" off.
 * Weather and news are not available: no provider has been chosen.
 *
 * Two places use this module:
 *  - the Brain's Work tab (brain.js): the latest briefing and "Brief me now"
 *    (brain/briefing.rs brain_briefing, brain_briefing_now - reads, so not
 *    held on a stale link; the lines taken out in Rust while the private
 *    lists are hidden);
 *  - Settings, "Morning briefing" (briefing-settings.js): when it arrives
 *    (get_briefing_setup, set_briefing - the scheduler's ONE approval card,
 *    held on a stale link - and stop_briefing, one at a time), and "Show who
 *    new emails are from" (set_briefing_senders: OFF at once, ON through ONE
 *    approval card on the PC, held on a stale link).
 *
 * The phone says the same words (net/Briefing.kt); tests/briefing.mjs
 * checks that they match, and that the PC's own words (jarvis_briefing.py)
 * are these.
 *
 * @module briefing
 */

export const BRIEFING_TITLE = "Morning briefing";
export const BRIEFING_DETAIL =
  "A short list of your day, put together on your PC without the AI model. It only reads: " +
  "it changes nothing and approves nothing.";
export const EMPTY = "No briefing yet. Say \"brief me now\", or set one up to arrive each morning.";
export const NOW_LABEL = "Brief me now";
export const NOW_BUSY = "Putting it together…";
export const BUILDING = "Putting your briefing together…";
export const BRIEFING_MISSING =
  "Your PC's Jarvis does not have the morning briefing yet - run apply-patches.ps1 on the PC.";
export const KEPT = "Kept on your PC until Jarvis restarts. Nothing of it is written to disk.";

/** All a notification ever says (jarvis_briefing.LOCK_SCREEN). */
export const LOCK_SCREEN = "Jarvis: your morning briefing is ready.";
export const TOAST_TITLE = "Morning briefing";

/** The line weather and news get (jarvis_briefing.OUTSIDE_LINE). */
export const OUTSIDE_LINE =
  "Weather and news: not available. No provider has been chosen, so Jarvis fetches nothing " +
  "from the internet for this.";

/** Settings. */
export const SETUP_DETAIL =
  "Choose when your briefing arrives. It repeats, so Jarvis asks you once with an approval " +
  "card that lists the next three times; nothing is set up until you approve the card. Stopping it is " +
  "immediate. You can also say \"brief me every weekday at 7\", or \"brief me now\" at any time.";
export const SETUP_NONE = "No briefing is set up.";
export const SET_LABEL = "Set up";
export const STOP_LABEL = "Stop";
export const ASKED =
  "Asked. Your PC shows an approval card that lists the next three times - nothing is set up until you approve it.";
export const READS_TITLE = "What it includes";
export const SPOKEN =
  "It is read aloud only when you ask (\"read my briefing\"), and then only under your " +
  "private-answers setting, like a calendar answer.";

/**
 * "Show who new emails are from" (jarvis_briefing.py SENDERS; on by
 * default). OFF is immediate; ON raises ONE approval card on the PC and
 * changes nothing until it is approved.
 */
export const SENDERS_LABEL = "Show who new emails are from";
export const SENDERS_DETAIL =
  "The briefing lists who your newest unread emails are from (up to 5), next to how many " +
  "there are. Off: the number only. Turning it on shows you an approval card first; turning " +
  "it off happens at once.";
export const SENDERS_WAITING = "Waiting for your yes on the approval card, on your PC or phone.";
export const SENDERS_MISSING =
  "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC.";

/** The repeats a briefing can be set up with - the scheduler's own rules. */
export const EVERY = Object.freeze([
  { id: "weekday", label: "Weekdays (Monday to Friday)" },
  { id: "day", label: "Every day" },
  { id: "week", label: "Chosen days" },
]);
export const DAY_NAMES = Object.freeze(
  ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]);

const text = (v) => (typeof v === "string" ? v : "");
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

function readSection(s) {
  return {
    key: text(s.key),
    title: text(s.title),
    state: text(s.state),
    summary: text(s.summary),
    items: Array.isArray(s.items) ? s.items.filter((i) => typeof i === "string") : [],
  };
}

/**
 * `brain_briefing`'s, `brain_briefing_now`'s and `get_briefing_setup`'s
 * answer, read. `available: false` with `why` from an older PC; `hidden`
 * while the private lists are hidden (Rust took the lines out).
 */
export function readBriefing(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const available = a.available !== false && "briefing" in a;
  const b = a.briefing && typeof a.briefing === "object" ? a.briefing : null;
  const setups = Array.isArray(a.setups) ? a.setups.filter(
    (j) => j && typeof j === "object" && /^s[0-9a-f]{10}$/.test(String(j.id || ""))) : [];
  return {
    available,
    why: available ? "" : text(a.why) || BRIEFING_MISSING,
    building: a.building === true,
    hidden: available && (a.hidden === true || Boolean(b && b.hidden === true)),
    briefing: available && b ? {
      id: text(b.id),
      heading: text(b.heading),
      made: num(b.made),
      missed: text(b.missed),
      sections: Array.isArray(b.sections) ? b.sections.filter((s) => s && typeof s === "object")
        .map(readSection) : [],
      notIncluded: Array.isArray(b.not_included) ? b.not_included.filter((n) => typeof n === "string") : [],
      hidden: b.hidden === true,
    } : null,
    setups: available ? setups.map((j) => ({
      id: j.id,
      state: text(j.state),
      repeats: j.repeats === true,
      repeat: text(j.repeat),
      when: text(j.when),
    })) : [],
    sources: available && a.sources && typeof a.sources === "object" ? a.sources : {},
    senders: available ? readSenders(a.senders) : null,
  };
}

/**
 * The senders setting from `GET /api/briefing`'s `senders`, or null from a
 * PC without it (then the switch is not offered, and SENDERS_MISSING says why).
 */
export function readSenders(raw) {
  if (!raw || typeof raw !== "object" || typeof raw.on !== "boolean") return null;
  const last = raw.last && typeof raw.last === "object" ? raw.last : null;
  return {
    on: raw.on,
    waiting: raw.waiting === true,
    last: last ? text(last.message) : "",
    lastOutcome: last ? text(last.outcome) : "",
    why: text(raw.why),
  };
}

/**
 * What the switch shows: checked while on or while an ON card waits; the
 * lines under it. OFF is never held; ON is held on a stale link (rule 4).
 */
export function sendersView(senders, live) {
  if (!senders) return { show: false, checked: false, canChange: false, lines: [SENDERS_MISSING] };
  const lines = [];
  if (senders.waiting) lines.push(SENDERS_WAITING);
  else if (senders.last && senders.lastOutcome !== "enabled") lines.push(senders.last);
  if (senders.why) lines.push(senders.why.charAt(0).toUpperCase() + senders.why.slice(1) + ".");
  const checked = senders.on || senders.waiting;
  return { show: true, checked, canChange: checked || Boolean(live), lines };
}

/** "(Due at 07:00 - the PC was off or asleep, so it is late.)" */
export function lateLine(briefing) {
  if (!briefing || !briefing.missed) return "";
  return `(Due ${briefing.missed.replace("missed at ", "at ")} - the PC was off or asleep, so it is late.)`;
}

/** One setup, in words - Coming up's words for a job. */
export function setupLine(job) {
  let words = job.repeats ? job.repeat || "a repeating briefing" : job.when || "once";
  if (job.state === "waiting") words += " - waiting for your yes on the approval card";
  else if (job.state === "paused") words += " - paused";
  return words;
}

/** What a briefing includes, in the PC's words (jarvis_briefing.sources). */
export function sourceLines(sources) {
  const s = sources && typeof sources === "object" ? sources : {};
  const out = [];
  for (const key of ["calendar", "email", "weather"]) {
    const said = s[key] && typeof s[key].said === "string" ? s[key].said : "";
    if (said) out.push(said);
  }
  return out;
}

/** The body set_briefing sends, or null when it is not a briefing's repeat. */
export function setupArgs(every, at, days = []) {
  if (!EVERY.some((e) => e.id === every)) return null;
  if (!/^([01]?\d|2[0-3]):[0-5]\d$/.test(String(at || ""))) return null;
  const d = [...new Set(days.filter((x) => Number.isInteger(x) && x >= 0 && x <= 6))].sort();
  if (every === "week" && !d.length) return null;
  return every === "week" ? { every, at, days: d } : { every, at };
}
