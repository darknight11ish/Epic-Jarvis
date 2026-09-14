/**
 * voice.js — Jarvis's own voice, and the owner's, as motion.
 *
 * Section B of the work order: "The page exposes `setSpeechLevel(0..1)`; call
 * it per audio frame with the level of the TTS audio you are playing (a Web
 * Audio AnalyserNode on the playback element, RMS of the time-domain buffer).
 * `setLevel(0..1)` is the same thing for the microphone while listening."
 *
 * On Android that shell already exists. On the desktop it did not, so this
 * file is both halves: the envelope the shell would have applied, and the
 * two entry points a caller feeds. Everything below is `jarvis-visual-spec.json`
 * → `speech`, and `tests/voicecheck.mjs` re-reads that block and fails if these
 * constants drift from it.
 *
 * What it drives: three custom properties on the element handed to `startVoice`.
 *
 *   --voice-env    0..1, the smoothed envelope itself
 *   --voice-scale  1 .. 1.035, a positional push (spec `scale`)
 *   --voice-lift   0 .. 0.18, a brightness lift (spec `brightness_lift`)
 *
 * A surface opts in by using them; nothing is forced on anyone. The reactor in
 * `style.css` and the widget's dot both do.
 *
 * On the flash limits. `limits.flash` calls itself a hard limit because the
 * Android face "fills well over a quarter of the visual field". The desktop
 * reactor is a 34px glyph in a title bar, so a 0.18 lift confined to it moves
 * the surface's relative luminance by far less than the `min_luma_delta` of
 * 0.10 below which a transition is not counted at all — no transition here is
 * countable, at any syllable rate. The scale push is positional and is exempt
 * by the spec's own reasoning. Reduced motion still turns both off, because
 * "not a seizure risk" and "not distracting" are different questions.
 */

/* ── The spec's numbers, and only the spec's numbers ─────────────────────── */

/** `speech.envelope` — a syllable rises in ~40ms and decays in ~120ms. */
const SPEECH_ATTACK_S = 0.04;
const SPEECH_RELEASE_S = 0.12;
/** `speech.envelope.gate` — keeps player hiss from animating anything. */
const GATE = 0.04;
/** `speech.listening_uses_same_path` — the microphone's own envelope. */
const MIC_ATTACK_S = 0.03;
const MIC_RELEASE_S = 0.22;
/** `speech.scale` — up to 3.5% growth on a loud syllable. */
const SCALE = 0.035;
/** `speech.brightness_lift`. */
const BRIGHTNESS_LIFT = 0.18;
/** `speech.speak_floor` — a speaking face between words still glows above idle. */
const SPEAK_FLOOR = 0.18;
/** `speech.fallback` — 4.2Hz syllables, a 220ms rest every 2.3s, after 0.5s of silence. */
const FALLBACK_AFTER_S = 0.5;
const SYLLABLE_HZ = 4.2;
const REST_EVERY_S = 2.3;
const REST_FOR_S = 0.22;

/* ── State ───────────────────────────────────────────────────────────────── */

const REDUCED = typeof matchMedia === "function"
  ? matchMedia("(prefers-reduced-motion: reduce)")
  : { matches: false, addEventListener() {} };

const voice = {
  /** `null` | `"speaking"` | `"listening"`. Nothing runs when null. */
  mode: null,
  /** The last level a caller fed, 0..1, before any smoothing. */
  raw: 0,
  /** `performance.now()` of that feed, or 0 if none has ever arrived. */
  rawAt: 0,
  /** The smoothed envelope, 0..1. This is what surfaces see. */
  env: 0,
  /** Set while the synthetic envelope is standing in for a silent source. */
  synthetic: false,
  /** Seconds since the current mode began, for the fallback's own clock. */
  clock: 0,
  /** rAF handle, and the timestamp of the previous frame. */
  raf: 0,
  last: 0,
  /** Where the custom properties are written. */
  root: null,
  /** The last values written, so a still frame does no style work. */
  wrote: -1,
};

/* ── The two entry points from the work order ────────────────────────────── */

/**
 * The level of the TTS audio being played, 0..1, once per audio frame.
 *
 * Feeding this is what stops the fallback: one call inside the last 500ms and
 * the synthetic envelope stands down mid-syllable rather than fighting the
 * real one.
 */
export function setSpeechLevel(level) {
  feed(level, "speaking");
}

/**
 * The microphone level, 0..1, while listening. Same path, slower release, so
 * the owner's own voice visibly moves the face.
 */
export function setLevel(level) {
  feed(level, "listening");
}

function feed(level, want) {
  const value = Number(level);
  if (!Number.isFinite(value)) return;
  voice.raw = value < 0 ? 0 : value > 1 ? 1 : value;
  voice.rawAt = now();
  // A caller that feeds levels is authoritative about what is happening: audio
  // is playing, whatever the event stream last said. Believing the feed rather
  // than the link means the face never lags the sound by a stream round trip.
  if (voice.mode !== want) setVoiceMode(want);
}

/* ── Mode ────────────────────────────────────────────────────────────────── */

/**
 * Tells the envelope what Jarvis is doing. Pass the composed face state —
 * `faceState()` in `jarvis-link.js` — and anything that is not `speaking` or
 * `listening` stops the loop and releases the face to rest.
 */
export function setVoiceMode(mode) {
  const next = mode === "speaking" || mode === "listening" ? mode : null;
  if (next === voice.mode) return;
  voice.mode = next;
  voice.clock = 0;
  voice.synthetic = false;
  if (!next) {
    // Do not snap to zero: a hard cut at the end of a sentence reads as a
    // glitch. The loop keeps running until the envelope has decayed, then
    // stops itself.
    voice.raw = 0;
    voice.rawAt = 0;
  }
  pump();
}

/** The envelope as it stands, 0..1. Exported for tests and for the widget. */
export function voiceLevel() {
  return voice.env;
}

/* ── The loop ────────────────────────────────────────────────────────────── */

function now() {
  return typeof performance === "object" && performance.now
    ? performance.now()
    : Date.now();
}

/**
 * Starts writing the custom properties onto `root` (default: `<html>`).
 *
 * Idempotent, and safe to call before anything is speaking: with no mode set
 * the loop is not running and the cost is one property write.
 */
export function startVoice(root) {
  voice.root = root || (typeof document === "object" ? document.documentElement : null);
  voice.wrote = -1;
  write(0);
  REDUCED.addEventListener?.("change", () => {
    voice.wrote = -1;
    write(REDUCED.matches ? 0 : voice.env);
    pump();
  });
  pump();
}

/** Stops the loop and releases the face. Used when a window is hidden. */
export function stopVoice() {
  voice.mode = null;
  voice.raw = 0;
  voice.env = 0;
  if (voice.raf) cancelAnimationFrame(voice.raf);
  voice.raf = 0;
  write(0);
}

function pump() {
  if (voice.raf) return;
  if (typeof requestAnimationFrame !== "function") return;
  // Nothing to animate and nothing left to decay.
  if (!voice.mode && voice.env <= 0.001) return;
  voice.last = now();
  voice.raf = requestAnimationFrame(tick);
}

function tick(stamp) {
  voice.raf = 0;
  // A tab that was backgrounded returns with a dt of several seconds. Clamping
  // to 100ms keeps the one-pole stable instead of teleporting the envelope.
  const dt = Math.min(0.1, Math.max(0, (stamp - voice.last) / 1000));
  voice.last = stamp;
  voice.clock += dt;
  write(advance(dt));
  pump();
}

/**
 * One frame of the envelope. Pure, and `tests/voicecheck.mjs` drives it
 * directly with a synthetic clock — a rise this fast is not something a
 * screenshot can check.
 */
export function advance(dt) {
  const target = targetFor();
  const rising = target > voice.env;
  const tau = voice.mode === "listening"
    ? (rising ? MIC_ATTACK_S : MIC_RELEASE_S)
    : (rising ? SPEECH_ATTACK_S : SPEECH_RELEASE_S);
  // One-pole follower, framed in seconds rather than frames, so 60Hz and
  // 240Hz reach the same place at the same wall-clock moment.
  const coef = tau > 0 ? 1 - Math.exp(-dt / tau) : 1;
  voice.env += (target - voice.env) * coef;
  if (voice.env < 0.0005) voice.env = 0;
  return voice.env;
}

function targetFor() {
  if (!voice.mode) return 0;
  const stale = !voice.rawAt || (now() - voice.rawAt) / 1000 > FALLBACK_AFTER_S;
  // Listening has no fallback. An invented microphone level would say "I can
  // hear you" when the truth is that nothing is being captured, and that is a
  // lie about the one thing the owner most needs to be true.
  if (stale && voice.mode === "listening") return 0;
  if (stale) {
    voice.synthetic = true;
    return synth(voice.clock);
  }
  voice.synthetic = false;
  const gated = voice.raw < GATE ? 0 : voice.raw;
  return voice.mode === "speaking" ? Math.max(SPEAK_FLOOR, gated) : gated;
}

/**
 * `speech.fallback`: "syllables at 4.2Hz with varying weight and a 220ms rest
 * every 2.3s. Speaking is never frozen, even before TTS is wired."
 *
 * The weight varies on a slow irrational-ratio wobble rather than a random
 * number, so the shape is deterministic — a test can assert it, and two
 * surfaces reading the same clock stay in step without talking to each other.
 */
export function synth(t) {
  const phase = t % REST_EVERY_S;
  if (phase > REST_EVERY_S - REST_FOR_S) return SPEAK_FLOOR;
  const syllable = 0.5 - 0.5 * Math.cos(2 * Math.PI * SYLLABLE_HZ * t);
  const weight = 0.55 + 0.45 * (0.5 - 0.5 * Math.cos(2 * Math.PI * t / 1.7));
  return SPEAK_FLOOR + (1 - SPEAK_FLOOR) * syllable * weight;
}

function write(env) {
  const root = voice.root;
  if (!root || !root.style) return;
  const shown = REDUCED.matches ? 0 : env;
  // Two decimals is under a tenth of one percent of the 3.5% push — below the
  // point a subpixel transform can express it — and it cuts the style writes
  // on a held vowel to nothing.
  const q = Math.round(shown * 100) / 100;
  // The MODE is written first and unconditionally. It used to sit below the
  // early return, so it only landed when the envelope value also changed —
  // and `listening` has no fallback envelope by design, so with nothing
  // feeding `setLevel()` the value stays at 0, the return fires every time,
  // and `data-voice="listening"` was never written at all. The one on-screen
  // signal that the microphone is live could not appear.
  const mode = voice.mode || "";
  if (root.dataset.voice !== mode) root.dataset.voice = mode;
  if (q === voice.wrote) return;
  voice.wrote = q;
  root.style.setProperty("--voice-env", String(q));
  root.style.setProperty("--voice-scale", String(1 + SCALE * q));
  root.style.setProperty("--voice-lift", String(BRIGHTNESS_LIFT * q));
}

/* ── Audio sources ───────────────────────────────────────────────────────── */

/**
 * The Web Audio half the work order names: an AnalyserNode on a playback
 * element, RMS of the time-domain buffer, per animation frame.
 *
 * Nothing in this build plays TTS yet — the backend speaks out of process, so
 * there is no element here to analyse and the synthetic envelope is what
 * actually runs. This is the one call that replaces it the day an `<audio>`
 * element appears, and `attachMicSource` is the same for capture. Written now
 * because the alternative is a hook nobody can find later.
 *
 * Returns a function that detaches and releases the context.
 */
export function attachSpeechSource(element, { context } = {}) {
  return attachAnalyser(element, setSpeechLevel, context, "element");
}

/** The same, for a `MediaStream` from `getUserMedia`, feeding `setLevel`. */
export function attachMicSource(stream, { context } = {}) {
  return attachAnalyser(stream, setLevel, context, "stream");
}

function attachAnalyser(source, sink, given, kind) {
  const Ctx = typeof AudioContext === "function"
    ? AudioContext
    : typeof webkitAudioContext === "function"
      ? webkitAudioContext
      : null;
  if (!Ctx || !source) return () => {};
  const ctx = given || new Ctx();
  const node = kind === "stream"
    ? ctx.createMediaStreamSource(source)
    : ctx.createMediaElementSource(source);
  const analyser = ctx.createAnalyser();
  // 1024 samples is ~21ms at 48kHz — inside the 40ms attack, so a syllable's
  // leading edge is not averaged away before the envelope ever sees it.
  analyser.fftSize = 1024;
  node.connect(analyser);
  // A media element must still reach the speakers; a capture stream must not.
  if (kind === "element") node.connect(ctx.destination);
  const buffer = new Float32Array(analyser.fftSize);
  let live = true;
  let raf = 0;
  const read = () => {
    if (!live) return;
    analyser.getFloatTimeDomainData(buffer);
    let sum = 0;
    for (let i = 0; i < buffer.length; i += 1) sum += buffer[i] * buffer[i];
    const rms = Math.sqrt(sum / buffer.length);
    // RMS of speech sits low even when loud. 3.2 puts a normal speaking level
    // near the top of the range without clipping every syllable to 1.
    sink(Math.min(1, rms * 3.2));
    raf = requestAnimationFrame(read);
  };
  raf = requestAnimationFrame(read);
  return () => {
    live = false;
    if (raf) cancelAnimationFrame(raf);
    try { node.disconnect(); } catch { /* already torn down */ }
    if (!given) ctx.close().catch(() => {});
  };
}
