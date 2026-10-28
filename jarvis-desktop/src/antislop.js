/**
 * "Anti-Slop filter" - Settings -> "How Jarvis talks" (2026-10-28;
 * JARVIS-API.md section 159; backend jarvis_antislop.py).
 *
 * The rules this filters against are the MIT-licensed `miqdadbadjuber/anti-slop`
 * ruleset (v3.2.23), distilled to the few that fit a local 9B model's prompt
 * budget: no em-dashes in prose, no AI buzzwords, no decorative comment banners,
 * WCAG AA contrast, a visible focus ring, no dead buttons. ON is a preference
 * that changes the WORDING of an answer and never what Jarvis does, asks or
 * remembers, so neither direction raises an approval card, and OFF costs
 * nothing at all: no prompt block, no rewriting (the PC returns the reply
 * unchanged).
 *
 * This module is PURE - antislop-settings.js draws it. The PC sends its own
 * state with every GET /api/antislop and the page shows that; the words below
 * are the same words, used only when an answer lacks them, exactly as
 * manner.js does it for "How Jarvis talks".
 *
 * @module antislop
 */

export const TITLE = "Anti-Slop filter";
export const DETAIL =
  "Checks what Jarvis writes against the anti-slop rules and takes out the tells that read as machine-made: em-dashes in prose, AI buzzwords, decorative comment banners, dead buttons and unreadable contrast.";
export const OFF_NOTE =
  "Off: costs 0 prompt tokens. Nothing is added to a prompt and no answer is rewritten.";
export const MISSING =
  "Your PC's Jarvis cannot filter AI slop yet - run apply-patches.ps1 on the PC.";

/** The three scopes, in the order the card shows them. */
export const SCOPES = Object.freeze([
  Object.freeze({
    id: "copy",
    label: "Copy & answers",
    why: "Em-dashes in prose, AI buzzwords (seamless, revolutionary, next-generation) and unsourced claims.",
  }),
  Object.freeze({
    id: "code",
    label: "Code comments",
    why: "Decorative banners (# ======), emoji comments, and comments that only restate the next line.",
  }),
  Object.freeze({
    id: "ui",
    label: "Web & UI design",
    why: "Contrast, tap targets, a visible focus ring, dead buttons, and how much glass, glow and motion a screen uses.",
  }),
]);

/** During (filter as it writes) or After (list findings first). */
export const MODES = Object.freeze([
  Object.freeze({
    id: "during",
    label: "During - filter as Jarvis writes",
    why: "The rules go into the turn and the answer is cleaned before you read it. This is the default.",
  }),
  Object.freeze({
    id: "after",
    label: "After - audit and list numbered findings",
    why: "Jarvis changes nothing and shows a numbered list of what is wrong, so you pick what to fix.",
  }),
]);

/** The Liveliness dials, 1-3 each, with what each one moves. */
export const DIALS = Object.freeze({
  energy: Object.freeze({
    label: "Energy",
    why: "How hard a screen works to get attention: 1 is quiet, 3 is loud.",
  }),
  rhythm: Object.freeze({
    label: "Rhythm",
    why: "How varied the spacing and structure are: 1 is even, 3 is syncopated.",
  }),
  motion: Object.freeze({
    label: "Motion",
    why: "How much moves: 1 is still, 3 animates freely.",
  }),
});
export const DIAL_KEYS = Object.freeze(["energy", "rhythm", "motion"]);
export const DIAL_STEPS = Object.freeze([1, 2, 3]);
export const DIAL_DEFAULT = Object.freeze({ energy: 1, rhythm: 2, motion: 1 });

/** The switch under the UI scope: the four-block report on a finished screen. */
export const GATE_LABEL = "Close a UI answer with the four-block Anti-Slop Delivery Gate";
export const GATE_DETAIL =
  "Hard Gate, Purpose-Gate, Liveliness, Craftsmanship & Quality Locks. Only on answers that build a screen or a page.";

/** What to say when the PC's own sentence is missing. */
export const SAID = Object.freeze({
  on: "Anti-Slop filter is on. Answers are filtered from the next turn.",
  off: "Anti-Slop filter is off. That costs 0 prompt tokens: nothing is added to a prompt and nothing is rewritten.",
});

/**
 * One switch's own sentence, in the same words as `SAID` above.
 * `what` is "enabled", "gate" or a scope's id.
 */
export function saidFor(what, on) {
  if (what === "enabled") return on ? SAID.on : SAID.off;
  if (what === "gate") {
    return on
      ? "A finished screen now closes with the four-block Delivery Gate."
      : "A finished screen no longer closes with the Delivery Gate.";
  }
  const scope = SCOPES.find((s) => s.id === what);
  const name = scope ? scope.label : what;
  return on ? `${name}: filtered.` : `${name}: not filtered.`;
}

/** The mode's own sentence. */
export function modeSaid(mode) {
  return mode === "after"
    ? "Anti-Slop will audit and list findings, and change nothing."
    : "Anti-Slop will filter while Jarvis writes.";
}

function text(v, fallback) {
  return typeof v === "string" && v.trim() ? v : fallback;
}

function step(v, fallback) {
  const n = Number(v);
  return DIAL_STEPS.includes(n) ? n : fallback;
}

/**
 * GET /api/antislop, read:
 * `{enabled, mode, scopes: {copy, code, ui}, dials: {energy, rhythm, motion},
 * show_delivery_gate_on_ui_tasks}`, or `{available: false, why}`.
 *
 * A body with no `enabled` yes-or-no is NOT read as "off" - it is
 * `available: false`, because a state nobody could read is not a filter that is
 * switched off. The rest of the shape is forgiven field by field: a PC whose
 * backend answers the switch but not the dials yet still paints its switch, and
 * the dials keep their defaults, which is what it actually holds.
 */
export function readAntislop(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  if (v.available === false) return { available: false, why: text(v.why, MISSING) };
  if (typeof v.enabled !== "boolean") return { available: false, why: MISSING };
  const scopesIn = v.scopes && typeof v.scopes === "object" ? v.scopes : {};
  const dialsIn = v.dials && typeof v.dials === "object" ? v.dials : {};
  const scopes = SCOPES.map((s) => ({
    id: s.id,
    label: s.label,
    why: s.why,
    on: scopesIn[s.id] !== false,
  }));
  const dials = {};
  for (const key of DIAL_KEYS) {
    dials[key] = step(dialsIn[key], DIAL_DEFAULT[key]);
  }
  return {
    available: true,
    enabled: v.enabled,
    mode: v.mode === "after" ? "after" : "during",
    scopes,
    dials,
    gate: v.show_delivery_gate_on_ui_tasks !== false,
    title: text(v.title, TITLE),
    detail: text(v.detail, DETAIL),
    offNote: text(v.off_note, OFF_NOTE),
    // The PC's own words for a state, when it sends them: the page never
    // repaints a sentence the backend wrote.
    said: v.said && typeof v.said === "object" ? v.said : null,
  };
}

/** A scope's state as the card holds it, by id. */
export function scopeOn(view, id) {
  const found = (view && view.scopes ? view.scopes : []).find((s) => s.id === id);
  return found ? found.on === true : true;
}

/**
 * The three dials as ONE object to send, with `key` moved to `value`. The PC
 * stores all three together, so a whole table is sent - the same shape
 * manner-settings.js uses for the four manner dials.
 */
export function dialsAfter(view, key, value) {
  const out = { ...DIAL_DEFAULT };
  for (const k of DIAL_KEYS) out[k] = step(view && view.dials ? view.dials[k] : undefined, DIAL_DEFAULT[k]);
  out[key] = step(value, out[key]);
  return out;
}

/** What one dial step says, for a screen reader and the pill's own title. */
export function dialWords(key, value) {
  const dial = DIALS[key] || { label: key };
  return `${dial.label} ${value} of 3`;
}
