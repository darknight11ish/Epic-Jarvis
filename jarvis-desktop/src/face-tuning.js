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

/**
 * The quality levels, low to max. The ids match `faces.html`'s `TIERS` and
 * stay the old ones, so a setting saved before the rename still works; the
 * words are the spec's (`frame_rate.animals.levels`) and the phone's
 * (`QualityTier` in FaceBudget.kt) - tests/continuity.mjs holds all three
 * together. The lowest is "Lower", not "Battery saver": the phone already has
 * a Battery saver switch. Each note is the one-line cost of that level.
 */
export const QUALITIES = [
  { id: "low", label: "Lower",
    note: "Softest picture and the least work for the graphics chip. Easiest on battery and heat." },
  { id: "medium", label: "Balanced",
    note: "A little softer than High, with less work for the graphics chip." },
  { id: "high", label: "High",
    note: "Sharp. A fair amount of work for the graphics chip." },
  { id: "max", label: "Maximum",
    note: "The sharpest edges. The most work for the graphics chip, and the most battery and heat." },
];

/** The frame-rate choices (spec `frame_rate.targets`). 30 and 90 joined on 2026-09-28. */
export const FRAME_RATES = [
  { id: "auto", label: "Auto" },
  { id: "30", label: "30" },
  { id: "60", label: "60" },
  { id: "90", label: "90" },
  { id: "120", label: "120" },
  { id: "max", label: "Max" },
];

/** The Frame rate row's one-line note - the phone's Face editor says the same. */
export const FRAME_RATE_NOTE =
  "How many times a second the face is drawn. Higher is smoother but uses more battery and graphics work. " +
  "It keeps to whole steps of the screen's rate, so 90 becomes 72 on a 144 Hz screen.";

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
  // "Keep the animal still" (owner, 2026-09-28): an animal face only
  // breathes and blinks - no looking around, gestures or little idle
  // happenings. Off unless chosen. Every face page on this computer reads it
  // (faces.html FACE_STILL); the other faces ignore it. The phone has its
  // own switch (Appearance), since this whole object never leaves this PC.
  still: false,
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
  // Only a real `true` turns it on: anything else is the default, off.
  const still = v.still === true;
  return { quality, frameRate, speed, autoAdjust, still };
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
 * The divisor rule, with the spec's pick rule (`frame_rate.pick_rule`): draw
 * every Nth vsync so frames land on real vsyncs, the nearest whole share of
 * the screen's rate but never more than a fifth faster than what was picked -
 * 90 is 72 on a 144 Hz screen and 60 on a 120 Hz one. `hz` is the display's
 * refresh rate. Auto and Max are the display's own rate on the web. The same
 * sum as face-pace.js's strideNear (which faces.html uses) and the phone's
 * FramePacing.strideNear; tests/face-pace.mjs checks the first two agree.
 */
export function strideFor(frameRate, hz) {
  const rate = Number(hz) > 0 ? Number(hz) : 60;
  const n = Number(frameRate);
  const want = Math.min(Number.isFinite(n) && n > 0 ? n : rate, rate);
  let s = Math.max(1, Math.round(rate / want));
  if (rate / s > want * 1.2) s++;
  return s;
}
