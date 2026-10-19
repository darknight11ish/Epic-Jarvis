/**
 * The two calls the Focus presets surfaces make to the PC.
 *
 * This is the ONLY place that names the desktop's bridge commands and the body
 * field the one action posts. The backend contract branch owns the route, the
 * answer shape and the approval card; `focus-presets.js` owns the reading and
 * the words. When that branch lands, this file is the one to check against its
 * fixture - not the quickbar or Settings.
 *
 * Commands (Tauri): `get_focus_presets` (read-only) and
 * `apply_focus_preset` (the single approval-gated action). They live in
 * `src-tauri/src/focus_presets.rs`, are registered in `invoke_handler`, and
 * are granted to the quickbar and Settings by `permissions/surfaces.toml`'s
 * `focus-presets` set. The Rust command calls the existing `GET /api/work`
 * and `POST /api/work/apply` with `X-Jarvis-Client: hud` and the usual token;
 * this file is still the only JavaScript place the pages get them from.
 */
import { call } from "./invoke-budget.js";

export const READ_COMMAND = "get_focus_presets";
export const APPLY_COMMAND = "apply_focus_preset";

/** The backend field the action posts. The fixture names the final one. */
export const APPLY_ID_FIELD = "preset";

function errorWords(error) {
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error && typeof error.message === "string" && error.message.trim()) {
    return error.message.trim();
  }
  return "";
}

/**
 * `GET /api/work` through the desktop bridge. A bridge that is not
 * there yet (an older desktop build) or a backend that has not shipped the
 * contract both become the reading's own `available: false` line; this never
 * invents a preset.
 */
export async function readPresets() {
  try {
    return await call(READ_COMMAND, {}, "read");
  } catch (error) {
    return {
      available: false,
      why: errorWords(error) ||
        "This desktop build has no preset bridge yet. Update the app and the backend.",
    };
  }
}

/**
 * The ONE action. It posts the chosen preset's PC id; the backend raises its
 * own approval card. Nothing here decides, approves or retries. An error is
 * returned as words for the line; it does not become a second post.
 */
export async function applyPreset(id) {
  return call(APPLY_COMMAND, { [APPLY_ID_FIELD]: String(id || "") }, "action");
}
