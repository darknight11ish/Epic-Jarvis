/**
 * The desktop face's own settings: how hard it works and how fast it moves.
 *
 * The desktop twin of the phone's `FaceTuning.kt`: the reactor kit's Quality,
 * Frame rate and All speeds, plus Auto adjust. Battery saver is phone-only and
 * is not here.
 *
 * Per computer and never synced, for the phone's reason: what this machine's
 * graphics card can draw says nothing about the phone's. So it lives in this
 * window origin's localStorage - shared by every Jarvis window on this
 * computer, including the face frames in the widget and the HUD - and never
 * in the appearance document that goes to the server.
 *
 * No side effects on import: `faces.html` imports this into its display frame,
 * where nothing but the face should run.
 *
 * @module face-tuning
 */

/** The localStorage key. */
export const FACE_TUNING_KEY = "jarvis.faceTuning";

/** The kit's tiers, low to max. Names match `faces.html`'s `TIERS`. */
export const QUALITIES = [
  { id: "low", label: "Low" },
  { id: "medium", label: "Medium" },
  { id: "high", label: "High" },
  { id: "max", label: "Max" },
];

/** The kit's frame-rate targets. */
export const FRAME_RATES = [
  { id: "auto", label: "Auto" },
  { id: "60", label: "60" },
  { id: "120", label: "120" },
  { id: "max", label: "Max" },
];

/**
 * Slow-down only. The phone's reason, copied: some faces pulse their own
 * brightness on the face's clock, and the flash limits in the spec police the
 * state COLOURS, not those pulses. Faster than 1x stays off until those
 * pulses are checked against the same limits, which keeps the standing rule
 * that motion settings only ever slow the face. `normaliseFaceTuning` clamps,
 * so no stored value can get past it either.
 */
export const MIN_SPEED = 0.25;
export const MAX_SPEED = 1;
export const SPEEDS = [0.25, 0.5, 0.75, 1];

/** What a computer that has never been set starts with - the phone's defaults. */
export const FACE_TUNING_DEFAULT = Object.freeze({
  quality: "high",
  frameRate: "auto",
  speed: 1,
  autoAdjust: true,
});

/**
 * Anything unreadable falls back to the default for that field, and a wholly
 * unreadable value is the default tuning. Speed is pulled into 0.25..1.
 */
export function normaliseFaceTuning(raw) {
  const d = FACE_TUNING_DEFAULT;
  const v = raw && typeof raw === "object" ? raw : {};
  const quality = QUALITIES.some((q) => q.id === v.quality) ? v.quality : d.quality;
  const frameRate = FRAME_RATES.some((f) => f.id === String(v.frameRate))
    ? String(v.frameRate)
    : d.frameRate;
  const n = Number(v.speed);
  const speed = Number.isFinite(n) ? Math.min(MAX_SPEED, Math.max(MIN_SPEED, n)) : d.speed;
  const autoAdjust = typeof v.autoAdjust === "boolean" ? v.autoAdjust : d.autoAdjust;
  return { quality, frameRate, speed, autoAdjust };
}

/** The stored tuning, or the default. Never throws. */
export function loadFaceTuning(storage = globalThis.localStorage) {
  try {
    const text = storage && storage.getItem(FACE_TUNING_KEY);
    return normaliseFaceTuning(text ? JSON.parse(text) : null);
  } catch (error) {
    return normaliseFaceTuning(null);
  }
}

/** Clamps, saves and returns what was saved. */
export function saveFaceTuning(value, storage = globalThis.localStorage) {
  const clean = normaliseFaceTuning(value);
  try {
    if (storage) storage.setItem(FACE_TUNING_KEY, JSON.stringify(clean));
  } catch (error) {
    /* private mode: it still applies to this window for this session */
  }
  return clean;
}

/**
 * The kit's divisor rule: draw every Nth vsync so frames land on real vsyncs
 * (120 -> 60 -> 40 -> 30) rather than at an uneven rate. `hz` is the display's
 * refresh rate. Auto and Max are the display's own rate on the web.
 */
export function strideFor(frameRate, hz) {
  const rate = Number(hz) > 0 ? Number(hz) : 60;
  const want = frameRate === "60" ? 60 : frameRate === "120" ? 120 : rate;
  return Math.max(1, Math.round(rate / Math.min(want, rate)));
}
