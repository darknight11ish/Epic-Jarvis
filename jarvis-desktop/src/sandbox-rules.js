/**
 * The fixed words and the one read-through the data sandbox's Settings card
 * shares with its tests (LM-1C, 2026-10-18; sandbox-settings.js).
 *
 * Pure: no page, no Tauri, so tests/sandbox-settings.mjs can run it with no
 * browser. Every STATE sentence the owner reads comes from the PC's own
 * GET /api/sandbox answer (`line`, `status`); the words here are only the
 * card's own labels and the "could not read it" sentences.
 *
 * @module sandbox-rules
 */

/** The sentence for an older PC's Jarvis that has the module but not the
 *  drop-in folder - one command adds it. Never an HTTP code on screen. */
export const MISSING =
  "This PC's Jarvis does not have the data sandbox switch yet. In PowerShell on the PC, in the " +
  "Jarvis folder, run: .\\scripts\\add-plugin.ps1 -Name sandbox . Then restart Jarvis.";
export const UNREAD =
  "Could not read this switch. The switch shows as not known until a read works - it does not " +
  "pretend to be off.";
export const WAITING_LINK = "Waiting for the connection to your PC.";
export const COULD_NOT_TURN_ON = "Could not turn it on: ";
export const ASKING = "Asking your PC…";

/** The reason in plain words: never a raw "HTTP 404" or a piece of JSON. */
export function refusedWords(error) {
  let text =
    typeof error === "string"
      ? error
      : error && error.message
        ? String(error.message)
        : "";
  text = text.trim();
  if (/^HTTP (404|501)\b/i.test(text)) return MISSING;
  const start = text.indexOf("{");
  if (start >= 0) {
    try {
      const parsed = JSON.parse(text.slice(start));
      const said = parsed && (parsed.error || parsed.message);
      text = typeof said === "string" ? said.trim() : "";
    } catch {
      text = "";
    }
  }
  if (/^HTTP \d+/i.test(text)) text = "";
  if (!text || /^(undefined|null|nan|\[object Object\])$/i.test(text) || /::/.test(text)) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return text;
}

/** The PC's answer, made safe for the page: only booleans and text are read.
 *  A real JSON true/false is required for the switch itself, so an answer
 *  with no such field is "not known" (`null`) - never "off". */
export function sandboxView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (typeof raw.enabled !== "boolean") return null;
  const enabled = raw.enabled;
  const waiting = raw.waiting === true && !enabled;
  return {
    enabled,
    waiting,
    checked: enabled || waiting,
    line: typeof raw.line === "string" ? raw.line : "",
    status: typeof raw.status === "string" ? raw.status : "",
    why: typeof raw.why === "string" ? raw.why : "",
  };
}
