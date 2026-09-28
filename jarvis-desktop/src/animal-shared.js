/**
 * The animal options shared with the phone, as this computer keeps them for
 * its face pages - and the one rule for "make the animal sharper".
 *
 * The owner's decisions of 2026-09-28: "Every animal option lives in one
 * place in both apps' settings ... and Jarvis can change any of them when
 * asked", and "Look-and-behaviour options are shared between the PC and the
 * phone (one request changes both); sharpness and frame rate stay per
 * device."
 *
 * WHERE EACH ONE LIVES
 *  - "Keep the animal still" and the behaviour switches: on the PC
 *    (backend/jarvis_animal.py, GET/POST /api/animal), and in the appearance
 *    document every window already follows (`animal`, animal.patch). Every
 *    window with jarvis-link.js keeps a copy here, in this computer's
 *    localStorage (STORE_KEY), because the face frames themselves hold no
 *    command at all - the same road the sky takes (sky-feed.js).
 *  - The sun, the moon and the weather: on the PC too (jarvis_sky.py,
 *    sky-settings.js, sky-feed.js). Not here.
 *  - Sharpness and frame rate: this computer only (face-tuning.js). Jarvis
 *    names a change in the answer's X-Jarvis-Route (`face_tuning`), and
 *    main.js applies it here with stepTuning() - the PC's own rule
 *    (jarvis_animal.step_device), held equal by tests/fixtures/
 *    animal-cases.json.
 *
 * No side effects on import: faces.html imports this into its display frame.
 *
 * @module animal-shared
 */

/** This computer's copy of the shared switches. */
export const STORE_KEY = "jarvis.animal.v1";
/** Set once this computer's old "Keep the animal still" has reached the PC. */
export const MIGRATED_KEY = "jarvis.animal.migrated";

/**
 * The switches, in the PC's words (jarvis_animal.SWITCHES) - shown when the
 * PC sends none (an older PC). tests/animal-settings.mjs holds this list to
 * the fixture the PC's own code writes. A new behaviour is one more entry
 * there and here.
 */
export const SWITCHES = [
  { id: "still", label: "Keep the animal still", default: false, built: true,
    detail: "It only breathes and blinks - no looking around, gestures or little idle events. For the animal and robot faces; the others are not changed." },
  { id: "nods", label: "Listening nods", default: true, built: false,
    detail: "Small nods in your pauses while you talk, and gestures that land at the ends of Jarvis's sentences." },
  { id: "focus_buddy", label: "Focus buddy", default: true, built: false,
    detail: "In a focus session the animal works quietly beside you and stretches at the end. It never sees your screen and never scolds." },
  { id: "acks", label: "Small acknowledgements", default: true, built: false,
    detail: "A small nod when Jarvis saves a fact (not while App lock or \"Hide memory lists\" is on), and a glow when a long answer is ready." },
  { id: "petting", label: "Petting", default: true, built: false,
    detail: "Stroke the animal and it leans in. On the phone it is a long press on the face, which does not open the Brain." },
  { id: "cute_moments", label: "Cute idle moments", default: true, built: false,
    detail: "Now and then, after the face has rested a while, one of its two short cute moments plays, then it settles back. Never during an approval or an error." },
  { id: "seasonal", label: "Seasonal touches", default: false, built: false,
    detail: "Small touches for the time of year, from the date on your device. Off by default." },
];

/** The words around them, the PC's (jarvis_animal.py). */
export const WORDS = {
  title: "Animal options",
  intro: "Everything about the animal and robot faces, in one place. You can also ask Jarvis, like \"keep the animal still\" or \"turn off the weather\".",
  shared_title: "Shared with your phone",
  shared_note: "Kept on your PC: a change here, on your phone or by asking Jarvis changes both. No approval card - these only change how the animal moves.",
  serious_note: "\"Keep the animal still\" and serious moments (an approval, an error, a crisis answer) switch the behaviours off; calm motion makes them smaller.",
  coming: "Coming in the next update: saved now, and the animal starts doing it then.",
  missing: "Your PC's Jarvis cannot share the animal options yet - run apply-patches.ps1 on the PC.",
};

export const DEFAULTS = Object.freeze(Object.fromEntries(SWITCHES.map((s) => [s.id, s.default])));

/** Only a real true/false is read; anything else is that switch's default. */
export function normaliseAnimal(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  const out = {};
  for (const s of SWITCHES) out[s.id] = typeof v[s.id] === "boolean" ? v[s.id] : s.default;
  return out;
}

/** What this computer last heard from the PC, or null (never heard). */
export function loadAnimal(storage = globalThis.localStorage) {
  try {
    const text = storage && storage.getItem(STORE_KEY);
    return text ? normaliseAnimal(JSON.parse(text)) : null;
  } catch {
    return null;
  }
}

/** Keep the PC's values for every face page. True when they changed. */
export function storeAnimal(values, storage = globalThis.localStorage) {
  if (!values || typeof values !== "object") return false;
  const next = normaliseAnimal(values);
  try {
    const before = storage.getItem(STORE_KEY);
    const text = JSON.stringify(next);
    if (before === text) return false;
    storage.setItem(STORE_KEY, text);
    return true;
  } catch {
    return false;
  }
}

export function migrated(storage = globalThis.localStorage) {
  try { return storage.getItem(MIGRATED_KEY) === "1"; } catch { return false; }
}

export function markMigrated(storage = globalThis.localStorage) {
  try { storage.setItem(MIGRATED_KEY, "1"); } catch { /* tried again next time */ }
}

/**
 * Whether the animal keeps still on this computer's faces. The PC's value
 * once this computer has heard it; before that - an older PC, or not asked
 * yet - this computer's own old switch (face-tuning.js `still`), which is
 * also the one that is sent to the PC once, if it was on ("if either device
 * had Still on, keep it on"). Until that has happened an old "on" still
 * counts, so nothing the owner chose goes away during the move.
 */
export function effectiveStill(shared, legacyTuning, isMigrated) {
  const legacy = !!(legacyTuning && legacyTuning.still === true);
  if (!shared) return legacy;
  return shared.still === true || (legacy && !isMigrated);
}

/* ---------------------------------------------------------------------------
   Per device: the one stepping rule (jarvis_animal.step_device)
   ------------------------------------------------------------------------- */

const SHARP = [["low", "Lower"], ["medium", "Balanced"], ["high", "High"], ["max", "Maximum"]];
const RATES = [["auto", "Auto"], ["30", "30"], ["60", "60"], ["90", "90"], ["120", "120"], ["max", "Max"]];
const SHARP_ORDER = SHARP.map(([i]) => i);
const RATE_STEPS = ["30", "60", "90", "120", "max"];
const labelOf = (pairs, id) => (pairs.find(([i]) => i === id) || [id, id])[1];

/** Every `face_tuning` value the PC may send; anything else is ignored. */
export const DEVICE_CHANGES = [
  "sharper", "softer", "smoother", "less_smooth", "auto",
  ...SHARP.map(([i]) => `sharpness:${i}`),
  ...RATES.filter(([i]) => i !== "auto").map(([i]) => `frame_rate:${i}`),
];

/**
 * `tuning` is {quality, frameRate, autoAdjust} (and anything else, kept);
 * returns {tuning, changed, line} with "{device}" in the line. A step picks
 * a value, so Auto adjust goes off - as a tap in Settings does; while it is
 * on, a step starts from High and 60, where Auto starts.
 */
export function stepTuning(tuning, change) {
  const t = tuning && typeof tuning === "object" ? tuning : {};
  const q = SHARP_ORDER.includes(t.quality) ? t.quality : "high";
  const f = RATES.some(([i]) => i === String(t.frameRate)) ? String(t.frameRate) : "auto";
  const auto = t.autoAdjust !== false;
  const out = { quality: q, frameRate: f, autoAdjust: auto };
  const baseQ = auto ? "high" : q;
  const baseF = auto || f === "auto" ? "60" : f;
  const same = (a, b) => a.quality === b.quality && a.frameRate === b.frameRate && a.autoAdjust === b.autoAdjust;
  const done = (next, line) => ({ tuning: { ...t, ...next }, changed: !same(next, out), line });

  if (change === "sharper" || change === "softer") {
    const i = SHARP_ORDER.indexOf(baseQ) + (change === "sharper" ? 1 : -1);
    if (i < 0 || i >= SHARP_ORDER.length) {
      const end = labelOf(SHARP, baseQ);
      if (!auto) return done({ ...out }, `Sharpness is already ${end} on {device}.`);
      return done({ ...out, quality: baseQ, autoAdjust: false }, `Sharpness on {device}: ${end}.`);
    }
    return done({ ...out, quality: SHARP_ORDER[i], autoAdjust: false },
      `Sharpness on {device}: ${labelOf(SHARP, SHARP_ORDER[i])}.`);
  }
  if (change === "smoother" || change === "less_smooth") {
    let j = RATE_STEPS.includes(baseF) ? RATE_STEPS.indexOf(baseF) : 1;
    j += change === "smoother" ? 1 : -1;
    if (j < 0 || j >= RATE_STEPS.length) {
      const end = labelOf(RATES, baseF);
      if (!auto && f !== "auto") return done({ ...out }, `Frame rate is already ${end} on {device}.`);
      return done({ ...out, frameRate: baseF, autoAdjust: false }, `Frame rate on {device}: ${end}.`);
    }
    return done({ ...out, frameRate: RATE_STEPS[j], autoAdjust: false },
      `Frame rate on {device}: ${labelOf(RATES, RATE_STEPS[j])}.`);
  }
  if (change === "auto") {
    return done({ ...out, autoAdjust: true }, "Auto adjust is on for {device}: it picks sharpness and frame rate.");
  }
  if (typeof change === "string" && change.startsWith("sharpness:") && SHARP_ORDER.includes(change.slice(10))) {
    const v = change.slice(10);
    return done({ ...out, quality: v, autoAdjust: false }, `Sharpness on {device}: ${labelOf(SHARP, v)}.`);
  }
  if (typeof change === "string" && change.startsWith("frame_rate:") && RATES.some(([i]) => i === change.slice(11))) {
    const v = change.slice(11);
    return done({ ...out, frameRate: v, autoAdjust: false }, `Frame rate on {device}: ${labelOf(RATES, v)}.`);
  }
  return done({ ...out }, "");
}
