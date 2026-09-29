/**
 * The Brain -> Model list, held on disk so it survives a restart.
 *
 * `GET /api/models` (brain.js `renderModels`) has no cache today, beyond
 * `state.data.models` in memory: close the window, or restart the app,
 * while Jarvis is not running, and the very next launch has nothing to
 * show until a live read succeeds
 * (docs/OFFLINE-MODELS-DESIGN-2026-09-27.md). This module keeps the last
 * successful read in `localStorage` - the same place this app already
 * keeps small per-window state (voice-flow.js's "One moment" and "I heard
 * you" switches, face-tuning.js, barge-in.js) - never a new file on disk,
 * never anything synced anywhere, and never chat text or a token.
 *
 * Only what the design doc's field-by-field table calls "honestly
 * cacheable" is kept: which models are installed, each one's size and
 * family, and which was current/previous AT THE TIME OF THE READ. Nothing
 * here is a fact about what Ollama is doing right now (what is loaded in
 * its memory, on-card percentage, GPU heat/watts) - showing that stale
 * would read as live and be wrong, so it is stripped before it is ever
 * written, not merely hidden later. There is nothing in this file for a
 * later screen to show by accident.
 *
 * @module models-cache
 */

/** The `localStorage` key. One row only - there is only ever one "last
 *  models read" worth keeping, not a history of them. */
export const MODELS_CACHE_KEY = "jarvis.brain.modelsCache";

/** One installed model, stripped to the fields worth keeping stale. */
function cacheableModel(entry) {
  const m = typeof entry === "string" ? { ref: entry } : entry;
  if (!m || typeof m !== "object") return null;
  const ref = String(m.ref || m.name || m.model || "").trim();
  if (!ref) return null;
  const out = { ref };
  if (typeof m.size === "number" && Number.isFinite(m.size) && m.size >= 0) out.size = m.size;
  if (typeof m.family === "string" && m.family.trim()) out.family = m.family.trim();
  return out;
}

/**
 * The small object worth keeping from a real `/api/models` body: current,
 * previous, and the installed list, each trimmed to ref/size/family.
 * Everything else - `speed`, `offload`, anything added later - is dropped
 * here, once, rather than filtered out again at every render.
 */
export function cacheableModels(body) {
  const installedRaw = Array.isArray(body && body.installed) ? body.installed : [];
  const installed = installedRaw.map(cacheableModel).filter(Boolean);
  const current = String((body && (body.current || body.active)) || "");
  const previous = String((body && body.previous) || "");
  return { current, previous, installed };
}

/**
 * Reads the last cache written, or `null` when there has never been one
 * (a fresh install, private browsing storage, or a value that does not
 * look like ours). Never throws: `storage` can be missing entirely (no
 * window yet) or refuse to be read (a private window, blocked site data).
 */
export function loadModelsCache(storage = globalThis.localStorage) {
  try {
    if (!storage) return null;
    const raw = storage.getItem(MODELS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const at = Number(parsed.at);
    if (!Number.isFinite(at) || at <= 0) return null;
    const models = parsed.models;
    if (!models || typeof models !== "object" || !Array.isArray(models.installed)) return null;
    // Passed back through `cacheableModels` too, so a cache written by an
    // older version of this file (or hand-edited) cannot smuggle a live-only
    // field back onto the page.
    return { at, models: cacheableModels(models) };
  } catch {
    return null;
  }
}

/**
 * Writes the last good read, stamped with when it was read (`at`, epoch
 * ms - the same clock `state.readAt` already uses in brain.js). Never
 * throws: a full or blocked disk just means the next restart has nothing
 * to show, not a broken window - the caller does not need to check the
 * return value, but gets one to test with.
 */
export function saveModelsCache(body, at, storage = globalThis.localStorage) {
  try {
    if (!storage) return false;
    storage.setItem(MODELS_CACHE_KEY, JSON.stringify({ at, models: cacheableModels(body) }));
    return true;
  } catch {
    return false;
  }
}
