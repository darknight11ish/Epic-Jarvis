/**
 * The nine built-in Personality Presets and the four tuning dials, as the
 * desktop Settings page draws them ("How Jarvis talks").
 *
 * WHY THIS FILE EXISTS (2026-10-23, Personality Presets SLICE 2a). The PC's
 * own `contract/personalities.json` and `jarvis_manner.py` are the owners of
 * what each preset MEANS (prompt, reflex phrases, voice blend). This module is
 * only the page's copy for when the PC is older: it holds the same nine ids,
 * titles and voice pairings as the blueprint's section 2, so Settings can draw
 * the whole grid before the backend half has landed, and `readPersonalities`
 * ALWAYS prefers the PC's answer once the PC sends one. The local copy is
 * marked `source: "local"` and the page says so; nothing here is presented as
 * if the PC had said it.
 *
 * Pure: no DOM, no fetch, no storage, no clock. manner-settings.js draws it,
 * and tests/personalities.mjs holds it to the blueprint's table.
 *
 * Words: the owner is the reader. Every string is plain English, and a preset
 * line is a count or a title - never a claim about what Jarvis will do.
 *
 * @module personalities
 */

/** The PC's default preset (legacy "warm" maps to it). */
export const DEFAULT_PRESET = "warm_peer";

/** Legacy ids still accepted by the PC, mapped to their preset. */
export const LEGACY = Object.freeze({ warm: "warm_peer", plain: "tactical_ops" });

/**
 * The nine built-in presets, in the PC's own order (blueprint section 2, with
 * the Patient Advocate appended as the ninth on 2026-10-24).
 * `voice.blend` is the 256-dim style mix the PC uses; `voice.fallback` is the
 * one Kokoro voice it can fall back to; `voice.label` is what the page shows.
 */
export const PRESETS = Object.freeze([
  Object.freeze({
    id: "warm_peer",
    badge: "Default",
    title: "Warm Collaborator",
    description: "Friendly and steady, close to how Jarvis normally talks.",
    quote: "Let's work through it together - I'm right here.",
    voice: Object.freeze({
      blend: "af_heart:0.75+af_bella:0.25",
      fallback: "af_heart",
      speed: 1.0,
      label: "Warm American Blend",
    }),
    switchAck: "Switched to Warm Collaborator - I'm right here with you.",
  }),
  Object.freeze({
    id: "classic_butler",
    badge: "2",
    title: "Classic British Butler",
    description: "Proper British manners, dry wit, always at your service.",
    quote: "Very good, sir. The schedule is in hand.",
    voice: Object.freeze({
      blend: "bm_george:0.65+bm_lewis:0.35",
      fallback: "bm_george",
      speed: 1.02,
      label: "British Baritone Blend",
    }),
    switchAck: "Very good, sir. Classic British Butler protocols are online and at your service.",
  }),
  Object.freeze({
    id: "tactical_ops",
    badge: "3",
    title: "Tactical Mission Control",
    description: "Short, clipped updates. No small talk, no decoration.",
    quote: "Copy. Timer running. Standing by.",
    voice: Object.freeze({
      blend: "am_adam:0.60+bm_george:0.40",
      fallback: "am_michael",
      speed: 1.1,
      label: "Mission Control Blend",
    }),
    switchAck: "Copy. Tactical Mission Control active. Standing by for tasking.",
  }),
  Object.freeze({
    id: "dry_wit",
    badge: "4",
    title: "Dry & Deadpan",
    description: "Sharp, sarcastic and unimpressed - on purpose.",
    quote: "Timer set. Try not to burn it this time.",
    voice: Object.freeze({
      blend: "bm_lewis:0.70+am_adam:0.30",
      fallback: "bm_lewis",
      speed: 1.05,
      label: "Deadpan Baritone Blend",
    }),
    switchAck: "Dry & Deadpan mode engaged. Humor setting at 90 percent - try to keep up.",
  }),
  Object.freeze({
    id: "friday_partner",
    badge: "5",
    title: "Sharp Tech Partner",
    description: "A quick engineering partner who gets straight to the point.",
    quote: "On it, boss - what are we building?",
    voice: Object.freeze({
      blend: "bf_isabella:0.60+af_sarah:0.40",
      fallback: "bf_isabella",
      speed: 1.06,
      label: "Tech Partner Blend",
    }),
    switchAck: "On it, boss. Sharp Tech Partner mode locked in - what are we building?",
  }),
  Object.freeze({
    id: "socratic_mentor",
    badge: "6",
    title: "Socratic Coach",
    description: "Asks the next question so you think it through yourself.",
    quote: "What do you already know about it?",
    voice: Object.freeze({
      blend: "bm_fable:0.70+bm_george:0.30",
      fallback: "bm_fable",
      speed: 0.98,
      label: "Mentor Blend",
    }),
    switchAck: "Switched to Socratic Coach. Let's think through things from first principles together.",
  }),
  Object.freeze({
    id: "devils_advocate",
    badge: "7",
    title: "No-Nonsense Critic",
    description: "Finds the hole in the plan before it costs you.",
    quote: "Bring me your plan and I'll show you where it breaks.",
    voice: Object.freeze({
      blend: "am_onyx:0.65+bm_george:0.35",
      fallback: "am_onyx",
      speed: 1.04,
      label: "Critic Blend",
    }),
    switchAck: "No-Nonsense Critic active. Bring me your plan and I'll show you where it breaks.",
  }),
  Object.freeze({
    id: "calm_stoic",
    badge: "8",
    title: "Calm & Grounded",
    description: "Quiet, gentle and unhurried. Good for late evenings.",
    quote: "No rush - take your time.",
    voice: Object.freeze({
      blend: "af_sky:0.65+af_heart:0.35",
      fallback: "af_sky",
      speed: 0.94,
      label: "Soft Calm Blend",
    }),
    switchAck: "Switched to Calm & Grounded. No rush - take your time.",
  }),
  Object.freeze({
    id: "advocate",
    badge: "9",
    title: "Patient Advocate",
    description: "In your corner for doctor visits, labs, medicines and insurance letters.",
    quote: "Let's take them one line at a time.",
    voice: Object.freeze({
      blend: "af_heart:0.65+af_bella:0.35",
      fallback: "af_heart",
      speed: 0.94,
      label: "Patient Advocate Blend",
    }),
    switchAck: "Switched to Patient Advocate. I'm in your corner - we'll go through it one line at a time.",
  }),
]);

/** The nine ids, in the same order. */
export const PRESET_IDS = Object.freeze(PRESETS.map((p) => p.id));

/**
 * The four tuning dials and their choices. The ids are the PC's; the labels
 * are the page's. `null` for address means "no title" (the PC's "none").
 */
export const DIALS = Object.freeze({
  humor: Object.freeze({
    label: "Wit & Humor",
    choices: Object.freeze([
      Object.freeze({ id: 0, label: "None" }),
      Object.freeze({ id: 1, label: "Subtle" }),
      Object.freeze({ id: 2, label: "Dry & Sharp" }),
      Object.freeze({ id: 3, label: "Playful" }),
    ]),
  }),
  brevity: Object.freeze({
    label: "Response Length",
    choices: Object.freeze([
      Object.freeze({ id: "concise", label: "Concise" }),
      Object.freeze({ id: "balanced", label: "Balanced" }),
      Object.freeze({ id: "thorough", label: "Thorough" }),
    ]),
  }),
  formality: Object.freeze({
    label: "Formality",
    choices: Object.freeze([
      Object.freeze({ id: "casual", label: "Casual" }),
      Object.freeze({ id: "warm_peer", label: "Warm Peer" }),
      Object.freeze({ id: "formal_butler", label: "Formal Butler" }),
      Object.freeze({ id: "tactical", label: "Tactical" }),
    ]),
  }),
  address: Object.freeze({
    label: "How Jarvis Addresses You",
    choices: Object.freeze([
      Object.freeze({ id: "first_name", label: "First Name" }),
      Object.freeze({ id: "sir", label: "\u201cSir\u201d" }),
      Object.freeze({ id: "ma'am", label: "\u201cMa'am\u201d" }),
      Object.freeze({ id: "boss", label: "Boss" }),
      Object.freeze({ id: "captain", label: "Captain" }),
      Object.freeze({ id: "none", label: "No Title" }),
    ]),
  }),
});

/** The four dial names, in the order the page draws them. */
export const DIAL_KEYS = Object.freeze(["humor", "brevity", "formality", "address"]);

/** A custom personality's limits (the PC's own 240-character cap on its lines). */
export const LIMITS = Object.freeze({ name: 60, line: 240, custom: 24 });

export const VOICE_SYNC_LABEL =
  "Switch Jarvis's spoken voice to match the chosen personality";
export const VOICE_SYNC_DETAIL =
  "When it is on, picking a personality also changes the voice you hear. Turn it off to keep your current voice.";

export const TITLE = "Personality presets";
export const DETAIL =
  "Pick how Jarvis sounds and how it puts answers together. This changes wording and voice only - never what Jarvis does, asks or remembers.";
export const HEAR_LABEL = "\u25b6 Hear Sample";
export const HEAR_BUSY = "Playing the sample\u2026";
/** Said on the page under the preset grid, so the button cannot mislead:
 *  the sample plays the preset's BASE voice until the Kokoro/Live slice can
 *  preview the stored blend (the blend is not yet consumed by the TTS path). */
export const HEAR_BASE_VOICE_NOTE =
  "Hear Sample plays each personality's base voice for now. " +
  "The blended voice shown above is stored with the character; " +
  "blended-voice previews arrive with the voice update.";
export const USE_LABEL = "Use This Personality";
export const IN_USE = "In use";
export const CUSTOM_TITLE = "My personalities";
export const CUSTOM_DETAIL =
  "Save your own mix of the four dials. It is kept on this PC, like the built-in presets.";
export const CUSTOM_EMPTY = "No personalities of your own yet.";
export const DELETE_QUESTION = "Delete this personality? This cannot be undone.";
export const UPDATE_SENTENCE =
  "Your PC's Jarvis does not have the personality presets yet - run apply-patches.ps1 on the PC. " +
  "The two choices above still work.";
export const NAMES = Object.freeze({
  create: "+ Create Custom Personality",
  save: "Save personality",
  cancel: "Cancel",
  name: "Name",
  line: "One line about how it should sound (up to 240 characters)",
  example: "One example exchange (up to 240 characters)",
  basedOn: "Start from",
});

/** The PC's own words for a preset id, or the id itself; never a blank badge. */
export function presetTitle(id) {
  const preset = PRESETS.find((p) => p.id === id);
  return preset ? preset.title : String(id || "");
}

/** Legacy "warm"/"plain" -> the preset id; anything else unchanged. */
export function normalizeId(id) {
  const key = String(id || "").trim();
  return LEGACY[key] || key;
}

/** "British Baritone Blend \u00b7 1.02x" - the voice badge's words. */
export function voiceBadge(preset) {
  const voice = (preset && preset.voice) || {};
  const label = typeof voice.label === "string" && voice.label ? voice.label : "Voice blend";
  const speed = Number(voice.speed);
  const speedText = Number.isFinite(speed) ? `${speed.toFixed(2)}x` : "";
  return speedText ? `${label} \u00b7 ${speedText}` : label;
}

/** The body the PC's sample route accepts: exactly ONE field.
 *
 *  `POST /api/voice/voices/sample` requires `set(body) == {"voice"}` and
 *  answers 400 to anything else (`backend/jarvis_voices.py:926`), so sending
 *  the character's blend/speed/text made every preset's sample fail. The
 *  character keeps its stored blend and speed (the badge shows them, and a
 *  later Kokoro/Live slice will preview them); they are deliberately not sent
 *  here, and `HEAR_BASE_VOICE_NOTE` says so on the page. */
export function sampleArgs(preset) {
  const voice = (preset && preset.voice) || {};
  return { voice: String(voice.fallback || "") };
}

/** True only for a value one of the four dials accepts. */
export function validDial(key, value) {
  const dial = DIALS[key];
  if (!dial) return false;
  return dial.choices.some((c) => c.id === value);
}

/** A full, valid dial set from a partial one; anything invalid reads the default preset's own. */
export function readDials(raw, fallback) {
  const base = (fallback && fallback.dials) || PRESETS[0].dials || defaultDials();
  const out = defaultDials();
  for (const key of DIAL_KEYS) {
    out[key] = validDial(key, raw && raw[key]) ? raw[key] : base[key];
  }
  return out;
}

/** The default preset's dials, as a plain object. */
export function defaultDials() {
  return { humor: 1, brevity: "balanced", formality: "warm_peer", address: "first_name" };
}

const DIAL_FALLBACKS = Object.freeze({
  warm_peer: defaultDials(),
  classic_butler: Object.freeze({ humor: 2, brevity: "balanced", formality: "formal_butler", address: "sir" }),
  tactical_ops: Object.freeze({ humor: 0, brevity: "concise", formality: "tactical", address: "none" }),
  dry_wit: Object.freeze({ humor: 3, brevity: "concise", formality: "casual", address: "first_name" }),
  friday_partner: Object.freeze({ humor: 1, brevity: "concise", formality: "casual", address: "boss" }),
  socratic_mentor: Object.freeze({ humor: 1, brevity: "thorough", formality: "warm_peer", address: "first_name" }),
  devils_advocate: Object.freeze({ humor: 0, brevity: "balanced", formality: "tactical", address: "none" }),
  calm_stoic: Object.freeze({ humor: 0, brevity: "concise", formality: "warm_peer", address: "first_name" }),
  advocate: Object.freeze({ humor: 1, brevity: "thorough", formality: "warm_peer", address: "first_name" }),
});

/** The blueprint's default dials for a preset id (local copy; the PC owns the truth). */
export function presetDials(id) {
  return { ...(DIAL_FALLBACKS[normalizeId(id)] || DIAL_FALLBACKS[DEFAULT_PRESET]) };
}

/** The PC's own id for a saved custom personality, kept verbatim.
 *
 *  A GET row may carry any id the PC itself minted - `mine-…` for a preset
 *  saved through this page, `custom-…` when the PC had to rename a same-name
 *  save. Rewriting those to `mine-…` made Use and Delete answer 400 ("There is
 *  no saved personality by that name"), so a server id that matches the PC's
 *  own rule is returned unchanged. `""` means "not one the PC would accept":
 *  the caller then makes a page id for a NEW save, which is the only thing
 *  `customId()` is for.
 */
export function serverIdOf(raw) {
  const id = typeof raw === "string" ? raw.trim() : "";
  return /^[a-z0-9][a-z0-9-]{2,63}$/.test(id) ? id : "";
}

/** A custom personality id the page can make for a NEW preset: short,
 *  lowercase, no spaces. Never used to rewrite an id that came from the PC
 *  (see serverIdOf). */
export function customId(seed) {
  const safe = String(seed || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 30);
  if (safe.startsWith("mine-") && safe.length > 5) return safe;
  return `mine-${safe || "personality"}`;
}

/** The custom line's words, cut to the PC's cap and with control characters out. */
export function cleanLine(text, max = LIMITS.line) {
  return String(text || "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

/** A custom personality, validated and normalised, or {why}. */
export function customPersonality(input, basePreset) {
  const name = cleanLine(input && input.name, LIMITS.name);
  if (!name) return { why: "Give the personality a name." };
  const line = cleanLine(input && input.line, LIMITS.line);
  const example = cleanLine(input && input.example, LIMITS.line);
  const dialect = readDials(input && input.dials, basePreset);
  return {
    id: customId((input && input.id) || name),
    name,
    line,
    example,
    dials: dialect,
    basedOn: basePreset && basePreset.id ? basePreset.id : DEFAULT_PRESET,
  };
}

/* ── The PC's answer ───────────────────────────────────────────────────── */

function asObject(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}

function readVoice(raw, local) {
  const v = asObject(raw);
  const blend = typeof v.blend === "string" && v.blend ? v.blend : local.blend;
  const fallback = typeof v.fallback === "string" && v.fallback ? v.fallback : local.fallback;
  const speed = Number(v.speed);
  const label = typeof v.label === "string" && v.label ? v.label : local.label;
  return Object.freeze({
    blend,
    fallback,
    speed: Number.isFinite(speed) && speed > 0 ? speed : local.speed,
    label,
  });
}

/** One preset from the PC's answer, falling back field-by-field to the local copy. */
function readPreset(raw, local) {
  const v = asObject(raw);
  const id = typeof v.id === "string" && v.id ? v.id : local && local.id;
  if (!id) return null;
  const known = PRESETS.find((p) => p.id === id) || local;
  const voice = readVoice(v.voice || { blend: v.voice_blend, fallback: v.voice_fallback,
                                        speed: v.voice_speed, label: v.voice_label },
                           (known && known.voice) || PRESETS[0].voice);
  const dials = v.dials && typeof v.dials === "object"
    ? readDials(v.dials, { dials: presetDials(id) })
    : presetDials(id);
  return {
    id,
    badge: typeof v.badge === "string" && v.badge ? v.badge : (known && known.badge) || String(PRESET_IDS.indexOf(id) + 1),
    title: typeof v.title === "string" && v.title ? v.title : (known && known.title) || presetTitle(id),
    description: typeof v.description === "string" && v.description
      ? v.description : (known && known.description) || "",
    quote: typeof v.quote === "string" && v.quote
      ? v.quote : (known && known.quote) || "",
    voice,
    switchAck: typeof v.switch_ack === "string" && v.switch_ack
      ? v.switch_ack : (known && known.switchAck) || "",
    dials,
    builtin: true,
  };
}

/** A custom personality from the PC's answer, validated; null when it is not one. */
function readCustom(raw) {
  const v = asObject(raw);
  const name = cleanLine(v.name, LIMITS.name);
  if (!name) return null;
  const basedOn = normalizeId(v.based_on) || DEFAULT_PRESET;
  // The PC's custom voice comes from its base preset; a thin GET row carries
  // no voice, so the label/sample follow the base rather than Warm's blend.
  const baseVoice = (PRESETS.find((p) => p.id === basedOn) || PRESETS[0]).voice;
  return {
    // A row that came FROM the PC keeps the PC's own id, verbatim (blocker 3,
    // 2026-10-23): only an idea that has not been saved yet gets a `mine-` id.
    id: serverIdOf(v.id) || customId(name),
    badge: "Mine",
    title: name,
    description: cleanLine(v.line, LIMITS.line),
    quote: cleanLine(v.example, LIMITS.line),
    voice: readVoice(v.voice, baseVoice),
    switchAck: cleanLine(v.switch_ack, LIMITS.line),
    dials: readDials(v.dials, null),
    builtin: false,
    basedOn,
  };
}

/**
 * The whole "How Jarvis talks" data, from the PC's answer when it has the
 * personality fields and from this file's copy when it does not.
 *
 * `pc` is true only when the PC sent an array of presets - the page disables
 * the new controls when it is false rather than pretending a switch worked.
 * `active` is the PC's chosen preset id (legacy ids mapped), or "" when the
 * answer does not say; `custom` is the owner's own list, always an array.
 */
export function readPersonalities(raw) {
  const v = asObject(raw);
  if (v.available === false) {
    return {
      available: false, pc: false, why: String(v.why || UPDATE_SENTENCE),
      presets: PRESETS, active: "", dials: defaultDials(), voiceSync: false, custom: [],
    };
  }
  const sent = Array.isArray(v.personalities) ? v.personalities : null;
  const pc = Boolean(sent);
  const presets = pc
    ? sent.map((p, i) => readPreset(p, PRESETS.find((local) => local.id === asObject(p).id) || PRESETS[i]))
      .filter(Boolean)
    : PRESETS.map((p) => readPreset({ id: p.id }, p));
  const active = normalizeId(
    pc ? (typeof v.personality === "string" ? v.personality : v.preset_id) : "");
  const known = presets.find((p) => p.id === active) || null;
  const custom = (Array.isArray(v.custom_personalities) ? v.custom_personalities : [])
    .map(readCustom)
    .filter(Boolean)
    .slice(0, LIMITS.custom);
  return {
    available: true,
    pc,
    presets,
    active,
    dials: v.dials && typeof v.dials === "object"
      ? readDials(v.dials, known || { dials: defaultDials() })
      : (known ? known.dials : defaultDials()),
    voiceSync: v.voice_sync === true,
    custom,
  };
}

/** The body that switches to one preset (never sends anything else). */
export function usePresetBody(preset) {
  return { personality: preset.id };
}

/** The body that saves a custom personality. */
export function saveCustomBody(person) {
  return {
    custom: {
      op: "save",
      id: person.id,
      name: person.name,
      line: person.line,
      example: person.example,
      dials: person.dials,
      based_on: person.basedOn,
    },
  };
}

/** The body that deletes one (the PC asks for the explicit `confirm: true`). */
export function deleteCustomBody(id) {
  return { custom: { op: "delete", id: String(id || ""), confirm: true } };
}
