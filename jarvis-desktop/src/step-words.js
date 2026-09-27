/**
 * One step of a turn (`step` events, jarvis_agent.py `_step_event`), in
 * plain words - "using web_search", "writing the answer", rather than only
 * "Working…".
 *
 * Written once so the Jarvis bar and Brain's Live tab say the same thing
 * about the same step (item 10, UI-AUDIT-2026-09-26.md: the desktop used to
 * turn a step into speech, via `main.js`'s own `checkForSpeakableSentence`,
 * but never into an on-screen word - Brain already had this function under
 * its own roof and the bar had none). The phone's `Steps.kt` ports this
 * function "word for word" (its own comment), so a wording change here
 * should be carried there too.
 *
 * No page, no Tauri: node can import it, same as card-words.js.
 *
 * @module step-words
 */

/**
 * `data`: every field is from the backend's own vocabulary - a tool NAME
 * from its table, never an argument, a result or the model's text - so this
 * can only ever say which tool, not what it saw.
 */
export function stepText(data) {
  const tool = typeof data.tool === "string" && data.tool ? data.tool : "a tool";
  const shown = tool === "unknown" ? "a tool Jarvis does not have" : tool;
  switch (data.phase) {
    case "model":
      return Number.isInteger(data.round) && data.round > 1
        ? `asking the model again (round ${data.round})`
        : "asking the model";
    case "tool_started":
      return `using ${shown}`;
    case "tool_finished":
      return data.ok === false ? `${shown} failed` : `${shown} done`;
    case "tool_refused":
      return tool === "unknown"
        ? "the model asked for a tool Jarvis does not have"
        : `${shown} not allowed`;
    case "answer":
      return "writing the answer";
    default:
      return "working";
  }
}
