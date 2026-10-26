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

/* ── The Today board (GTD-2, 2026-10-18) ───────────────────────────────────
 *
 * The page's three added sections and the said-I'd-do switch. The data comes
 * from the SAME Coming up read: Rust asks the PC for GET /api/today/cockpit
 * (backend jarvis_today.py) and passes it through under `cockpit`. Nothing
 * here creates a reminder: the buttons only put a prompt in the chat box (a
 * private clipboard write, the app's own existing command) for the owner to
 * send through the ordinary flow. The proposal shelf is OFF by default; the
 * switch's own state is what the PC says, never this page's guess.
 */

/** The sections' words. */
export const DUE_TITLE = "Due now";
export const DUE_DETAIL =
  "Reminders, alarms and timers whose time has come, or that went off in the last hour.";
export const NEXT_TITLE = "Next steps";
export const NEXT_DETAIL =
  "The first step of each goal you are working on, and of each project's work list.";
export const PROPOSALS_TITLE = "You said you would";
export const PROPOSALS_DETAIL =
  "Things your own words said you would do, that no reminder covers yet. Nothing is " +
  "created until you act on one.";
export const PROPOSALS_OFF =
  "Said-I'd-do suggestions are off. Turning them on asks for your approval first: " +
  "Jarvis reads your own words in recent chats (never an incognito or crisis chat).";
export const PROPOSALS_ON_LABEL = "Turn on (asks first)";
export const PROPOSALS_OFF_LABEL = "Turn off";
export const PROPOSALS_WAITING = "Waiting for your approval. Nothing has changed yet.";
export const PROPOSALS_TURNED_ON = "Said-I'd-do suggestions are on.";
export const PROPOSALS_TURNED_OFF = "Said-I'd-do suggestions are off.";

/** A due reminder's own controls. */
export const DO_THIS_LABEL = "⚡ Do This With Jarvis";
export const DO_THIS_COPIED = "Prompt copied - paste it into the Jarvis bar.";
export const DO_THIS_COPY_FAILED = "Could not copy the prompt.";
export const BREAK_LABEL = "✨ Break Into 3 Easy Steps";
export const BREAK_COPIED = "Prompt copied - paste it into the Jarvis bar to break it up.";
export const SNOOZE_LABEL = "⏱ Snooze";
export const SNOOZED_SAID = "Snoozed.";
export const SNOOZE_FAILED = "Could not snooze that.";
export const SENSITIVE_NOTE =
  "Sensitive: Jarvis will not offer to break this into steps.";

/** A proposal's one tap: a prompt for the owner to send, never a reminder. */
export const REMIND_LABEL = "Remind me…";

/** The plain prompt when the PC sent no suggested one. */
export function doThisPrompt(reminder) {
  const title = String((reminder && reminder.text) || "").trim();
  return title
    ? `Help me with this reminder: ${title}.`
    : "Help me with a reminder that is due.";
}

/** The prompt behind "Break Into 3 Easy Steps" - only when it may show. */
export function breakStepsPrompt(reminder) {
  const title = String((reminder && reminder.text) || "").trim();
  return title
    ? `Help me break this into 3 easy steps: ${title}.`
    : "Help me break a reminder down into 3 easy steps.";
}

/** "Remind me to ..." for a proposal; the owner still sends it themselves. */
export function remindPrompt(proposal) {
  const text = String((proposal && proposal.text) || "").trim();
  const due = String((proposal && proposal.suggested_due) || "").trim();
  if (!text) return "Remind me to do the thing I mentioned.";
  return due ? `Remind me to ${text} (${due}).` : `Remind me to ${text}.`;
}

/** The board inside `readSchedule`'s view, or null on an older PC. */
export function cockpitOf(view) {
  const c = view && view.cockpit;
  return c && typeof c === "object" ? c : null;
}

/** Is the said-I'd-do switch on, as the PC said? OFF unless it says true. */
export function unspokenEnabled(cockpit) {
  return Boolean(cockpit && cockpit.unspoken_commitments_enabled === true);
}

const SNOOZABLE_KINDS = Object.freeze(["reminder", "alarm", "timer"]);

/** When "Tonight" (19:00) and "Tomorrow" (09:00) fall, in seconds from now.
 * A target that is past, or outside the PC's 1-minute..24-hour snooze range,
 * is left out rather than sent to be refused. */
export function snoozeOffers(nowMs = Date.now()) {
  const offers = [{ label: "+15 min", seconds: 900 }, { label: "+1 hour", seconds: 3600 }];
  const secondsUntil = (hour, dayAhead) => {
    const d = new Date(nowMs);
    d.setDate(d.getDate() + dayAhead);
    d.setHours(hour, 0, 0, 0);
    return Math.round((d.getTime() - nowMs) / 1000);
  };
  const tonight = secondsUntil(19, 0);
  if (tonight >= 60 && tonight <= 86400) offers.push({ label: "Tonight", seconds: tonight });
  const tomorrow = secondsUntil(9, 1);
  if (tomorrow >= 60 && tomorrow <= 86400) offers.push({ label: "Tomorrow", seconds: tomorrow });
  return offers;
}

/** One due reminder as a row: what to show, what to offer. A timer, alarm or
 * reminder that WENT OFF can be snoozed (that is what the PC's snooze action
 * takes); one merely overdue has not gone off yet, so it has no snooze. */
export function dueRows(cockpit, nowMs = Date.now()) {
  const list = cockpit && Array.isArray(cockpit.due_reminders) ? cockpit.due_reminders : [];
  const offers = snoozeOffers(nowMs);
  return list.filter((r) => r && typeof r === "object").map((r) => {
    const text = String(r.text || "");
    const hidden = r.hidden === true || !text;
    const meta = [];
    if (r.went_off === true) meta.push(r.when ? `Went off (${r.when})` : "Went off");
    else if (r.overdue === true) meta.push(r.when ? `Overdue - ${r.when}` : "Overdue");
    else if (r.when) meta.push(String(r.when));
    const sensitive = r.sensitive === true;
    return {
      id: String(r.id || ""),
      kind: String(r.kind || ""),
      tag: String(r.kind || "reminder"),
      title: hidden ? "(hidden) reminder" : text,
      hidden,
      meta,
      overdue: r.overdue === true,
      sensitive,
      prompt: !hidden && typeof r.suggested_prompt === "string" && r.suggested_prompt.trim()
        ? r.suggested_prompt.trim() : doThisPrompt(r),
      breakPrompt: !hidden && r.stuck_hint === true && !sensitive
        ? breakStepsPrompt(r) : null,
      snooze: !hidden && r.went_off === true && SNOOZABLE_KINDS.includes(r.kind)
        ? offers : null,
    };
  });
}

/** The first open step of each active goal and project work list, as rows. */
export function nextRows(cockpit) {
  const list = cockpit && Array.isArray(cockpit.active_next_steps)
    ? cockpit.active_next_steps : [];
  return list.filter((s) => s && typeof s === "object" && String(s.step || "").trim())
    .map((s) => {
      const meta = [];
      if (s.name) meta.push(String(s.name));
      if (s.kind === "project") meta.unshift("work list");
      if (s.by) meta.push(String(s.by));
      return {
        id: String(s.id || ""),
        kind: s.kind === "project" ? "project" : "goal",
        tag: s.kind === "project" ? "project" : "goal",
        title: String(s.step || ""),
        meta,
      };
    });
}

/** The proposal chips: [{title, meta, prompt}] and nothing else. */
export function proposalRows(cockpit) {
  if (!unspokenEnabled(cockpit)) return [];
  const list = cockpit && Array.isArray(cockpit.proposals) ? cockpit.proposals : [];
  return list.filter((p) => p && typeof p === "object" && String(p.text || "").trim())
    .map((p) => ({
      title: String(p.text || ""),
      meta: p.suggested_due ? [`a good day: ${String(p.suggested_due)}`] : [],
      prompt: remindPrompt(p),
    }));
}

