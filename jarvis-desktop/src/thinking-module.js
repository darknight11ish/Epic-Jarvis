/**
 * Per-model thinking levels (Section 5.5; JARVIS-API section 27/thinking;
 * backend jarvis_thinking.py, thinking.patch).
 *
 * Lets Jarvis think through complex questions before answering. Thinking
 * spends conversation room (tokens).
 * Levels: Off / Quick / Deep / Auto per running model.
 * Changing levels needs NO approval card.
 *
 * @module thinking
 */

export const LEVELS = Object.freeze(["off", "quick", "deep", "auto"]);
export const DEFAULT = "off";
export const TITLE = "Thinking levels";
export const DETAIL =
  "Lets Jarvis think through complex questions before answering. Thinking spends some of your conversation room.";
export const NOTICE =
  "Thinking uses conversation room: when Jarvis thinks before answering, the thinking tokens take up part of the conversation room.";
export const MISSING =
  "Your PC's Jarvis does not have thinking controls yet - run apply-patches.ps1 on the PC.";

export const LEVEL_LABELS = Object.freeze({
  off: "Off",
  quick: "Quick",
  deep: "Deep",
  auto: "Automatic",
});

export const WHY = Object.freeze({
  off: "Off. Answers directly without an extra thinking step.",
  quick: "Quick thinking. Takes a brief thinking pass before answering.",
  deep: "Deep thinking. Takes more time and room to think through complex problems.",
  auto: "Automatic. Decides whether to think based on the question (simple questions stay fast, complex questions think deeply).",
});

/**
 * Parses raw GET /api/thinking response.
 */
export function readThinking(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  if (v.available === false) {
    return { available: false, why: String(v.why || MISSING) };
  }
  const rawModels = Array.isArray(v.models) ? v.models : [];
  const models = rawModels.map((m) => {
    const role = typeof m.role === "string" ? m.role : "everyday";
    const name = typeof m.name === "string" ? m.name : role;
    const model = typeof m.model === "string" ? m.model : "";
    const level = LEVELS.includes(m.level) ? m.level : DEFAULT;
    const supported = Array.isArray(m.supported)
      ? m.supported.filter((x) => LEVELS.includes(x))
      : [DEFAULT];
    const why = typeof m.why === "string" ? m.why : WHY[level] || "";
    return { role, name, model, level, supported, why };
  });

  return {
    available: true,
    title: typeof v.title === "string" ? v.title : TITLE,
    detail: typeof v.detail === "string" ? v.detail : DETAIL,
    notice: typeof v.notice === "string" ? v.notice : NOTICE,
    models,
  };
}
