/**
 * "How Jarvis talks": warm and brief (the default), or plain (the owner's
 * decision of 2026-09-25; JARVIS-API.md section 24; backend jarvis_manner.py).
 *
 * Manner changes only how Jarvis words its answers - never what it does,
 * asks or remembers - so neither choice raises an approval card. The PC
 * sends its own words with every GET /api/manner and Settings shows those;
 * the copies below are the same words (tests/manner.mjs checks them against
 * tests/fixtures/plain-error-cases.json, made from the backend's own), used
 * only when an answer lacks them. The phone's net/Manner.kt has the same.
 *
 * Pure: manner-settings.js draws it.
 *
 * @module manner
 */

export const MANNERS = Object.freeze(["warm", "plain"]);
export const DEFAULT = "warm";
export const TITLE = "How Jarvis talks";
export const DETAIL =
  "Changes only how Jarvis words its answers. It never changes what Jarvis does, what it asks you, or what it remembers.";
export const SPOKEN = "Spoken answers stay short and easy to listen to either way.";
export const LABEL = Object.freeze({
  warm: "Warm and brief (default)",
  plain: "Plain",
});
export const WHY = Object.freeze({
  warm: "Friendly and short, like a helpful person. No gushing, no filler and no emoji unless you use them.",
  plain: "Neutral and businesslike: just the answer, with no small talk.",
});
export const SAID = Object.freeze({
  warm: "Jarvis will now answer warmly and briefly.",
  plain: "Jarvis will now answer plainly.",
});
export const MISSING =
  "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC.";

/**
 * GET /api/manner (through get_manner), read: `{available, manner, title,
 * detail, spoken, choices: [{id, label, why}]}`, or `{available: false, why}`.
 */
export function readManner(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  if (v.available === false) return { available: false, why: String(v.why || MISSING) };
  // Not an answer this page can read (no choices at all): said plainly,
  // never drawn as if the PC had said "warm".
  if (!Array.isArray(v.choices)) return { available: false, why: MISSING };
  const given = Array.isArray(v.choices) ? v.choices : [];
  const choices = MANNERS.map((id) => {
    const c = given.find((x) => x && x.id === id) || {};
    return {
      id,
      label: typeof c.label === "string" && c.label ? c.label : LABEL[id],
      why: typeof c.why === "string" && c.why ? c.why : WHY[id],
    };
  });
  return {
    available: true,
    manner: MANNERS.includes(v.manner) ? v.manner : DEFAULT,
    title: typeof v.title === "string" && v.title ? v.title : TITLE,
    detail: typeof v.detail === "string" && v.detail ? v.detail : DETAIL,
    spoken: typeof v.spoken === "string" && v.spoken ? v.spoken : SPOKEN,
    choices,
  };
}
