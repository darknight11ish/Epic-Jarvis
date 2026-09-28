/**
 * Jarvis's voice, for the faces in the other windows (lip-sync, 2026-09-28).
 *
 * The problem this solves: the Jarvis bar (main.js) is the one window that
 * PLAYS Jarvis's voice, but the faces that should move with it live in other
 * windows - the Widget's tray, the floating face and the HUD, each a
 * `faces.html?mode=display&feed=parent` frame. Before this, none of them was
 * told anything about the sound: every face's "speaking" ran a made-up
 * 4.2 Hz beat, and the animals mouthed words even for a typed answer that
 * was never spoken at all.
 *
 * How it works, in three steps (docs/LIPSYNC.md has the analysis itself):
 *
 *  1. SENDER (main.js, `followClip`). Every spoken clip reaches the Jarvis
 *     bar as a complete WAV before it plays. It is analysed once, up front,
 *     into a "mouth track" (lipsync.js: 100 frames a second of loudness,
 *     open, wide, round; open/wide/round come instead from the voice
 *     engine's own timing when the PC put that in the clip - the "jmth"
 *     chunk, lipsync.js `merge`), packed small (~4 KB for 10 s), and sent
 *     with the first message about that clip. After that only the PLAYBACK CLOCK is
 *     sent: where the audio element is (`currentTime`, the truth about what
 *     is being heard), when that was read, and whether it is playing - at
 *     play, pause, seek and end, and every 250 ms while it plays.
 *  2. RUST (voice.rs `face_voice`) checks the message's shape and hands it
 *     to every window as the `face-voice` event. A page is not allowed to
 *     send an event itself (tests/security.mjs), so this one narrow command
 *     does it, and it can only ever send this one kind of message.
 *  3. RELAY (widget.js, floating.js, jarvis_hud.html, `relayFaceVoice`).
 *     Tauri delivers an event to a window's top-level page, never to a frame
 *     inside it, so each window passes the message into its face frame by
 *     postMessage - the same way it already passes the face's state. The
 *     microphone's level (`voice-level`, from Rust) goes the same way, so
 *     `listening` follows the owner's real voice.
 *
 * faces.html then works out, every frame, where the audio is NOW (the last
 * clock plus the time since), samples the track there and moves the face.
 *
 * Nothing here leaves this PC (rule 1): the track is a few numbers per
 * hundredth of a second, made from sound that was already here, sent only
 * between this app's own windows. Nothing here approves or decides anything.
 *
 * @module face-voice
 */

import "./lipsync.js";

/** The Rust event every window hears (lib.rs `events::FACE_VOICE`). */
export const FACE_VOICE_EVENT = "face-voice";
/** The microphone's level, 0..1 (lib.rs `events::VOICE_LEVEL`). */
export const MIC_LEVEL_EVENT = "voice-level";
/** The postMessage type faces.html's display frame listens for. */
export const FACE_VOICE_MESSAGE = "jarvis-face-voice";
/** How often the clock is re-sent while a clip plays. Often enough that a
 *  frame's own estimate (last clock + time since) never drifts far; rare
 *  enough to cost nothing. */
export const CLOCK_EVERY_MS = 250;
/** The most output delay `followClip` will take off the clock, in seconds -
 *  a guard against a browser reporting something absurd. */
export const MAX_LATENCY_S = 0.2;
/** Track strings longer than this are not sent (Rust refuses them too):
 *  about ten minutes of speech, far past any one sentence. */
export const MAX_TRACK_CHARS = 262144;

/* ── The sender: main.js ─────────────────────────────────────────────────── */

/** A few recent clips' tracks, by their data URI, so a clip analysed when
 *  its sound arrived (main.js asks for the next sentence while one plays)
 *  is not analysed again when it starts. */
const tracks = new Map();
const TRACKS_KEPT = 4;

/**
 * The packed mouth track for one spoken clip (a `data:audio/wav;base64,...`
 * URI), or null when it cannot be read - then no face is told anything and
 * the animals keep their mouths shut, which is the honest answer.
 * Never throws: a lip-sync failure must never cost the owner the reply.
 */
export function trackFor(uri) {
  if (typeof uri !== "string") return null;
  if (tracks.has(uri)) return tracks.get(uri);
  let packed = null;
  try {
    const L = globalThis.JarvisLipSync;
    const bytes = wavBytes(uri);
    if (L && bytes) {
      const wav = L.fromWav(bytes);
      if (wav && wav.samples && wav.samples.length > 0) {
        let track = L.analyse(wav.samples, wav.sampleRate);
        // Mouth shapes from the voice engine's own timing, when the PC put
        // them in the clip ("jmth" chunk, lipsync.js): the loudness stays
        // this clip's own, the shapes come from the PC. A clip without
        // them, or with ones that do not fit, keeps the analysis above.
        if (track && wav.mouth && typeof L.merge === "function") track = L.merge(track, wav.mouth);
        if (track && track.n > 0) {
          const s = L.pack(track);
          if (typeof s === "string" && s.length <= MAX_TRACK_CHARS) packed = s;
        }
      }
    }
  } catch (error) {
    packed = null;
  }
  tracks.set(uri, packed);
  while (tracks.size > TRACKS_KEPT) tracks.delete(tracks.keys().next().value);
  return packed;
}

/** The bytes of a base64 WAV data URI, or null for anything else. */
function wavBytes(uri) {
  const comma = uri.indexOf(",");
  if (comma < 0 || !/^data:audio\/[\w.+-]*;base64$/i.test(uri.slice(0, comma))) return null;
  // A "#..." fragment (the test harness tags clips with one) is not data.
  let body = uri.slice(comma + 1);
  const hash = body.indexOf("#");
  if (hash >= 0) body = body.slice(0, hash);
  const text = atob(body);
  const out = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i += 1) out[i] = text.charCodeAt(i);
  return out;
}

/** Clip ids only ever go up - even across a reload of the Jarvis bar,
 *  because they start from the wall clock - so a frame can tell a message
 *  about an older clip from one about the clip playing now. */
let lastId = 0;
function nextId() {
  lastId = Math.max(Date.now(), lastId + 1);
  return lastId;
}

/**
 * Follows one clip as it plays and tells the faces about it.
 *
 * - `audio`   the `<audio>` element the clip plays through.
 * - `uri`     the clip's data URI (analysed here, or taken from the cache).
 * - `send`    how a message goes out: `(cue) => invoke("face_voice", {cue})`.
 * - `latency` seconds between the element's `currentTime` and the sound
 *             actually leaving the speakers (the Web Audio graph's output
 *             delay, when the clip is routed through one - main.js). Taken
 *             off the clock, so the mouth follows what is HEARD.
 *
 * Returns a function that stops following it (and tells the faces the clip
 * is over). Safe to call more than once. Call it when the clip ends or is
 * dropped; `ended` and `error` also stop it by themselves.
 */
export function followClip(audio, uri, { send, latency = 0 } = {}) {
  const packed = trackFor(uri);
  if (!packed || !audio || typeof send !== "function") return () => {};
  const id = nextId();
  const lat = Math.min(MAX_LATENCY_S, Math.max(0, Number(latency) || 0));
  let n = 0;
  let done = false;
  let timer = 0;
  // One message at a time, in order: the track goes first, and a clock can
  // never overtake an older one on the way to Rust. A failed send is
  // dropped quietly - the reply plays whatever happens here.
  let chain = Promise.resolve();
  const post = (cue) => {
    chain = chain.then(() => send(cue)).catch(() => {});
  };
  const position = () => Math.max(0, (Number(audio.currentTime) || 0) - lat);
  const cue = (extra) => {
    const playing = !audio.paused && !audio.ended;
    post({
      id, n: n++, t: position(), at: Date.now(), playing,
      rate: Number(audio.playbackRate) > 0 ? Number(audio.playbackRate) : 1,
      ...extra,
    });
  };
  const onClock = () => { if (!done) cue(); };
  const onEnd = () => stop();
  const EVENTS = ["playing", "pause", "seeked", "ratechange"];
  function stop() {
    if (done) return;
    done = true;
    clearInterval(timer);
    EVENTS.forEach((e) => audio.removeEventListener(e, onClock));
    audio.removeEventListener("ended", onEnd);
    audio.removeEventListener("error", onEnd);
    cue({ playing: false, end: true });
  }
  EVENTS.forEach((e) => audio.addEventListener(e, onClock));
  audio.addEventListener("ended", onEnd);
  audio.addEventListener("error", onEnd);
  timer = setInterval(() => { if (!done && !audio.paused) cue(); }, CLOCK_EVERY_MS);
  // The track, before the clip makes a sound.
  cue({ track: packed });
  return stop;
}

/* ── The relay: widget.js, floating.js, jarvis_hud.html ──────────────────── */

/**
 * Passes Jarvis's voice and the owner's microphone level into one face
 * frame, for a window that shows one.
 *
 * - `frame`  the `<iframe>` holding `faces.html?mode=display&feed=parent`.
 * - `listen` the window's own `(event, handler)` subscriber (Tauri's).
 *
 * The frame may load in the middle of a clip (the Widget loads its face only
 * when expanded; the HUD reloads it on a face change): the clip's track is
 * kept here and handed over again with the latest clock when it loads.
 */
export function relayFaceVoice(frame, listen) {
  if (!frame || typeof listen !== "function") return;
  let clip = null;      // { id, track } of the clip playing now
  let latest = null;    // the newest message about that clip
  const post = (message) => {
    const w = frame.contentWindow;
    if (!w) return;
    try {
      // "/" = this page's own origin - the only sender faces.html accepts.
      w.postMessage({ type: FACE_VOICE_MESSAGE, ...message }, "/");
    } catch (error) {
      /* the frame is mid-navigation; its load event hands the clip over */
    }
  };
  listen(FACE_VOICE_EVENT, (event) => {
    const cue = event && event.payload;
    if (!cue || typeof cue !== "object") return;
    const id = Number(cue.id);
    if (!(id > 0) || (clip && id < clip.id)) return;
    if (typeof cue.track === "string") clip = { id, track: cue.track };
    if (clip && id === clip.id && (!latest || latest.id !== id || Number(cue.n) > Number(latest.n))) {
      latest = cue;
    }
    if (cue.end && clip && id === clip.id) clip = null;
    post(cue);
  });
  listen(MIC_LEVEL_EVENT, (event) => {
    const level = Number(event && event.payload);
    if (Number.isFinite(level)) post({ mic: Math.max(0, Math.min(1, level)) });
  });
  frame.addEventListener("load", () => {
    if (clip && latest && latest.id === clip.id) post({ ...latest, track: clip.track });
  });
}
