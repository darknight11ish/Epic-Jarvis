//! Real microphone capture and the voice round trip: push-to-talk, automatic
//! (voice-activity-detected) listening, and a spoken reply out.
//!
//! WHAT THIS FIXES
//! Before this file, there was no real audio capture anywhere in this app.
//! The mic button visible in the UI used to route through the browser's own
//! Web Speech API - which sends raw microphone audio to a vendor's servers
//! to transcribe - and was deliberately disabled for exactly that reason
//! (`hud_bootstrap.js` strips `window.SpeechRecognition` at injection time).
//! The button has done nothing since, and the app's own FAQ says so. This
//! module is the real replacement: audio is captured here, on this machine,
//! and posted only to the local Jarvis server - never to a cloud vendor.
//!
//! WHY THE HUD DOES NOT RECORD ANYTHING ITSELF
//! `jarvis_hud.html` is vendored from the backend folder, so a future drop
//! of that file must never arrive already holding the microphone. The
//! recording commands are granted to the quickbar only (see
//! `permissions/surfaces.toml`'s `voice` set) - the window that already
//! streams chat and already has a real, audited IPC surface.
//!
//! The HUD's own mic button used to do nothing at all (its browser speech
//! recogniser is switched off in `hud_bootstrap.js`, because it uploads
//! audio). It now calls [`summon_push_to_talk`], the ONE command the HUD
//! holds: it shows the quickbar with its mic button ready. It opens no
//! microphone and records nothing - the owner still holds the quickbar's
//! mic to talk, exactly as if they had opened the quickbar themselves.
//!
//! TWO LISTENING MODES, MUTUALLY EXCLUSIVE
//! Push-to-talk (`start_voice_capture`/`stop_voice_capture`) records exactly
//! what is held down and sends it once, on release. "Hey Jarvis" listening
//! (`start_automatic_listening`/`stop_automatic_listening` - the old names,
//! kept so the command surface and its permissions do not change) opens the
//! microphone once and keeps it open, cutting it into utterances and sending
//! each one as `source=wake_word`. Both modes want the same physical
//! microphone, so starting one refuses while the other is active rather than
//! trying to run two capture threads against one device.
//!
//! WHERE "HEY JARVIS" IS HEARD - AND WHY THE AUDIO NEVER LEAVES THIS PC
//! The Jarvis server on this same PC owns every speech model, so it also owns
//! the wake-word spotter (`backend/jarvis_wakeword.py`). Each utterance cut
//! here goes to it over loopback; it runs ONLY the spotter first, and a clip
//! without "hey Jarvis" in it is dropped there - not owner-checked, not
//! transcribed, not kept. That is why this mode refuses to start unless the
//! server address is loopback (`is_loopback_base`): a desktop pointed at a
//! server elsewhere would be sending every sentence spoken in the room over
//! the network before the wake word had been heard. Building a second
//! spotter into this app (ONNX Runtime from Rust) would have meant a second
//! copy of the models and a native dependency CI would have to fetch, for no
//! privacy gain on one machine.
//!
//! It also refuses to start until the server says the wake word is ON - and
//! if it is off, asking for it raises the ONE approval card
//! (`POST /api/voice/wake`), exactly as the phone's switch does. Nothing
//! here can turn it on without that card being approved.
//!
//! THE LOCAL DETECTOR IS A LOUDNESS TRIGGER; SILERO DECIDES
//! What is here cuts the stream into utterances by loudness: root-mean-square
//! amplitude against a threshold that follows the room's own background
//! level (`start_threshold`), with a silence hangover so a normal mid-
//! sentence pause does not cut the utterance in half. It is deliberately
//! cheap and deliberately eager - a door slam or the TV will trip it. The
//! decision about whether there was speech at all is made on the server by
//! Silero VAD (the neural VAD `docs/ARCHITECTURE.md` names), which drops a
//! clip with no speech before anything else runs and trims the silence off
//! one that has some. A missed quiet word here is the failure that matters,
//! so the trigger errs towards sending. Its numbers are reasoned-about
//! defaults, not measured against a real microphone - none is reachable
//! from the container this was written in.
//!
//! WHAT "STOP" ACTUALLY DOES
//! `cpal::Stream` is not `Send` on every platform (it wraps native audio-API
//! handles), so it cannot live in ordinary Tauri-managed state shared across
//! async tasks. It - and the host/device it came from - live on one
//! dedicated thread for the capture's whole lifetime; stopping signals that
//! thread to drop the stream, which is what actually releases the
//! microphone.
//!
//! THE WIRE CONTRACT, AND HOW SURE THIS IS OF IT
//! `jarvis_hud.py` itself is not in this repository, so the exact request
//! shape for `/api/voice/utterance` and `/api/voice/say` is not something
//! this file can read directly - only infer from what IS here:
//! `backend/jarvis_speech.py`'s real `hear(raw: bytes, source: str =
//! "push_to_talk") -> Heard` and `say(text) -> bytes | None`, and
//! `backend/test_voice_503.py`'s confirmed literal route strings
//! (`route == "/api/voice/utterance"`, `route == "/api/voice/say"`).
//! `raw` is documented as "one complete WAV" and `_read_wav` reads any
//! sample rate from the file's own header, so the body is the WAV bytes
//! themselves, not JSON. `source` defaults to exactly `"push_to_talk"`;
//! `"automatic"` for the VAD path is this file's own choice, not a value
//! confirmed anywhere upstream, made so the two paths are at least
//! distinguishable in whatever logs or telemetry `source` ends up in.
//! `say`'s `text` argument, and whether it arrives as a JSON body or
//! something else, is the one part of this contract genuinely unconfirmed -
//! built here as `{"text": ...}` to match how every other structured-input
//! route in this backend already works (`/api/chat`, the wake-toggle
//! route's `body.get("enabled")`), but worth checking against the real file
//! before trusting it blind.

use std::io::Cursor;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers};
use crate::events::{VOICE_HEARD, VOICE_SPEECH_STARTED};

/// Total round-trip budget for one utterance: speaker verification plus a
/// whole-clip transcription is not instant, but it is also not a chat
/// completion - thirty seconds is generous without being indefinite.
const UTTERANCE_TIMEOUT: Duration = Duration::from_secs(30);
/// Synthesising a reply is comparable work in the other direction.
const SAY_TIMEOUT: Duration = Duration::from_secs(30);
/// How long `start_voice_capture`/`start_automatic_listening` wait to hear
/// back from the capture thread before giving up and reporting the
/// microphone as unreachable, rather than returning success for a stream
/// that never actually opened.
const STREAM_READY_TIMEOUT: Duration = Duration::from_secs(3);

// ---------------------------------------------------------------------------
// Shared: opening the microphone
// ---------------------------------------------------------------------------

/// Builds and starts an input stream on the CURRENT thread, appending every
/// sample it produces (converted to i16) into `samples`. Returns once the
/// stream is confirmed playing. The returned `cpal::Stream` must be kept
/// alive by the caller for capture to continue - dropping it stops the
/// microphone.
///
/// Not `async` and not `Send` in what it returns: `cpal::Stream` cannot
/// cross a thread boundary, which is the whole reason every caller of this
/// runs it on a dedicated `std::thread` rather than the async runtime.
fn open_input_stream(
    samples: Arc<Mutex<Vec<i16>>>,
) -> Result<(hound::WavSpec, cpal::Stream), String> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or_else(|| "no microphone was found".to_string())?;
    let config = device
        .default_input_config()
        .map_err(|e| format!("could not read the microphone's format: {e}"))?;
    let spec = hound::WavSpec {
        channels: config.channels(),
        sample_rate: config.sample_rate().0,
        bits_per_sample: 16,
        sample_format: hound::SampleFormat::Int,
    };
    let sample_format = config.sample_format();
    if !matches!(
        sample_format,
        cpal::SampleFormat::I16 | cpal::SampleFormat::U16 | cpal::SampleFormat::F32
    ) {
        return Err(format!(
            "this microphone's sample format ({sample_format:?}) is not one this app reads"
        ));
    }
    let stream_config: cpal::StreamConfig = config.config();
    let err_fn = |err: cpal::StreamError| eprintln!("[voice] input stream error: {err}");
    // The three capture callbacks below all recover from a poisoned sample
    // mutex with `unwrap_or_else(|p| p.into_inner())` - the convention the
    // rest of this codebase uses, and a deliberate change from the
    // `if let Ok(...)` they started with. A poisoned lock here is not a
    // transient condition: once any thread panics while holding it, EVERY
    // later `lock()` returns `Err` for the life of the process, so
    // `if let Ok` quietly dropped every sample from then on. Recording would
    // go permanently silent with nothing logged anywhere, and
    // `stop_voice_capture` would POST an empty WAV as if the owner had said
    // nothing. The buffer holds PCM samples, not an invariant a panic can
    // corrupt into something unsafe to read, so carrying on with it is right.
    let stream_result = match sample_format {
        cpal::SampleFormat::I16 => device.build_input_stream(
            &stream_config,
            move |data: &[i16], _: &cpal::InputCallbackInfo| {
                let mut buf = samples
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner());
                buf.extend_from_slice(data);
            },
            err_fn,
            None,
        ),
        cpal::SampleFormat::U16 => device.build_input_stream(
            &stream_config,
            move |data: &[u16], _: &cpal::InputCallbackInfo| {
                let mut buf = samples
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner());
                // u16 PCM is centred on 32768, not 0 - shift before
                // narrowing, the same conversion `cpal::Sample`'s own
                // i16 impl documents.
                buf.extend(data.iter().map(|&s| (s as i32 - 32_768) as i16));
            },
            err_fn,
            None,
        ),
        cpal::SampleFormat::F32 => device.build_input_stream(
            &stream_config,
            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                let mut buf = samples
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner());
                buf.extend(
                    data.iter()
                        .map(|&s| (s.clamp(-1.0, 1.0) * i16::MAX as f32) as i16),
                );
            },
            err_fn,
            None,
        ),
        // Guarded above - every other variant already returned.
        _ => unreachable!("sample_format was checked to be I16, U16 or F32 above"),
    };
    let stream = stream_result.map_err(|e| format!("could not open the microphone: {e}"))?;
    stream
        .play()
        .map_err(|e| format!("could not start the microphone: {e}"))?;
    Ok((spec, stream))
}

/// Spawns the dedicated thread every capture mode needs: opens the
/// microphone, reports success or failure through `ready_tx`, then runs
/// `body` for as long as the stream should stay open. `body` receives the
/// live `samples` buffer and the channel to watch for a stop signal; it
/// returns when told to stop, at which point this function returns and the
/// stream - a local in this function's own scope, never moved into `body` -
/// drops, releasing the microphone.
fn spawn_capture_thread(
    samples: Arc<Mutex<Vec<i16>>>,
    ready_tx: mpsc::Sender<Result<hound::WavSpec, String>>,
    stop_rx: mpsc::Receiver<()>,
    body: impl FnOnce(&Arc<Mutex<Vec<i16>>>, hound::WavSpec, &mpsc::Receiver<()>) + Send + 'static,
) -> JoinHandle<()> {
    std::thread::spawn(move || match open_input_stream(Arc::clone(&samples)) {
        Ok((spec, stream)) => {
            if ready_tx.send(Ok(spec)).is_err() {
                return; // the caller already gave up waiting
            }
            body(&samples, spec, &stop_rx);
            drop(stream); // explicit: this is the line that stops the mic
        }
        Err(reason) => {
            let _ = ready_tx.send(Err(reason));
        }
    })
}

fn wait_for_ready(
    ready_rx: mpsc::Receiver<Result<hound::WavSpec, String>>,
    stop_tx_on_timeout: mpsc::Sender<()>,
) -> Result<hound::WavSpec, String> {
    match ready_rx.recv_timeout(STREAM_READY_TIMEOUT) {
        Ok(Ok(spec)) => Ok(spec),
        Ok(Err(reason)) => Err(reason),
        Err(_) => {
            // The thread is still doing *something* - drop the stop sender so
            // it is not left recv()-ing forever if it does eventually open.
            drop(stop_tx_on_timeout);
            Err("the microphone did not respond in time".to_string())
        }
    }
}

fn poisoned<T>(_: T) -> String {
    "voice capture state was poisoned by an earlier panic".to_string()
}

// ---------------------------------------------------------------------------
// Payload types
// ---------------------------------------------------------------------------

/// `jarvis_speech.Heard.as_dict()`, read verbatim (snake_case, matching the
/// dataclass field names `asdict()` emits) - this is what the backend's JSON
/// actually looks like, not what a future JS caller wants it renamed to.
#[derive(Debug, Deserialize)]
struct HeardRaw {
    is_owner: bool,
    #[serde(default)]
    text: String,
    #[serde(default)]
    score: f64,
    #[serde(default)]
    threshold: f64,
    #[serde(default = "default_true")]
    available: bool,
    #[serde(default)]
    source: String,
    #[serde(default)]
    reason: String,
    #[serde(default)]
    wake_heard: bool,
    #[serde(default)]
    awake: bool,
    #[serde(default)]
    awake_seconds: f64,
}

fn default_true() -> bool {
    true
}

/// The same fields, camelCased for the frontend - Tauri's own IPC boundary,
/// a separate hop from the HTTP one `HeardRaw` deserialises off of.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HeardReply {
    pub is_owner: bool,
    pub text: String,
    pub score: f64,
    pub threshold: f64,
    pub available: bool,
    pub source: String,
    pub reason: String,
    /// `source=wake_word` only: "hey Jarvis" was heard in this clip, from
    /// the owner. False on a wake-word clip means it was not addressed to
    /// Jarvis and is dropped without a word.
    pub wake_heard: bool,
    /// The clip was "hey Jarvis" and nothing else: the server is listening
    /// for the next clip without the phrase, for `awake_seconds`.
    pub awake: bool,
    pub awake_seconds: f64,
}

impl From<HeardRaw> for HeardReply {
    fn from(raw: HeardRaw) -> Self {
        Self {
            is_owner: raw.is_owner,
            text: raw.text,
            score: raw.score,
            threshold: raw.threshold,
            available: raw.available,
            source: raw.source,
            reason: raw.reason,
            wake_heard: raw.wake_heard,
            awake: raw.awake,
            awake_seconds: raw.awake_seconds,
        }
    }
}

/// Encodes `samples` as a WAV and posts it to `/api/voice/utterance`. Shared
/// by push-to-talk and automatic listening; only `source` differs between
/// them.
async fn post_utterance(
    app: &AppHandle,
    spec: hound::WavSpec,
    samples: &[i16],
    source: &str,
) -> Result<HeardReply, String> {
    if samples.is_empty() {
        return Err("nothing was recorded - the microphone produced no audio".to_string());
    }

    let mut cursor = Cursor::new(Vec::new());
    {
        let mut writer = hound::WavWriter::new(&mut cursor, spec)
            .map_err(|e| format!("could not start encoding the recording: {e}"))?;
        for sample in samples {
            writer
                .write_sample(*sample)
                .map_err(|e| format!("could not encode a sample: {e}"))?;
        }
        writer
            .finalize()
            .map_err(|e| format!("could not finish encoding the recording: {e}"))?;
    }
    let wav_bytes = cursor.into_inner();

    let response = jarvis_client(Some(UTTERANCE_TIMEOUT))?
        .post(format!(
            "{}/api/voice/utterance?source={source}",
            jarvis_base(app)
        ))
        .headers(jarvis_headers(app)?)
        .header("Content-Type", "audio/wav")
        .body(wav_bytes)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(app))
            } else {
                format!("sending the recording failed: {e}")
            }
        })?;

    let status = response.status();
    let body = response.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!(
            "the server answered HTTP {} to the recording: {}",
            status.as_u16(),
            body.trim()
        ));
    }
    serde_json::from_str::<HeardRaw>(&body)
        .map(HeardReply::from)
        .map_err(|e| format!("the server's answer did not look like a transcription: {e}"))
}

// ---------------------------------------------------------------------------
// Push-to-talk
// ---------------------------------------------------------------------------

/// The one push-to-talk recording in progress, if any. A second
/// `start_voice_capture` while this is `Some` is refused rather than
/// silently replacing it - two concurrent recordings from one control
/// should not be reachable, and if it ever is, that is a bug to see, not
/// paper over.
#[derive(Default)]
pub struct VoiceCaptureState(Mutex<Option<ActiveCapture>>);

struct ActiveCapture {
    stop_tx: mpsc::Sender<()>,
    samples: Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    join: JoinHandle<()>,
}

/// The HUD's mic button: bring up the quickbar with its push-to-talk ready.
///
/// Opens NO microphone and records nothing. It shows the quickbar and tells
/// it to put focus on its mic button (`VOICE_SUMMON`); recording starts only
/// when the owner holds that button (or Space/Enter on it), through
/// [`start_voice_capture`] like any other push-to-talk. That is why this is
/// the one app command the HUD window is allowed (`capabilities/hud.json`,
/// `permissions/surfaces.toml`'s `hud-voice` set): the worst a page can do
/// with it is open a window.
#[tauri::command]
pub fn summon_push_to_talk(app: AppHandle) -> Result<(), String> {
    crate::windows::show_quickbar(&app)?;
    crate::emit_quickbar(&app, crate::events::VOICE_SUMMON, ());
    Ok(())
}

/// Opens the default microphone and starts buffering. Sends nothing
/// anywhere - the clip is only posted once `stop_voice_capture` is called.
/// Refuses while automatic listening already owns the microphone.
#[tauri::command]
pub fn start_voice_capture(
    state: State<VoiceCaptureState>,
    auto: State<AutoListenState>,
) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(poisoned)?;
    if guard.is_some() {
        return Err("already recording".to_string());
    }
    if auto.0.lock().map_err(poisoned)?.is_some() {
        return Err("automatic listening is already using the microphone".to_string());
    }

    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    let (ready_tx, ready_rx) = mpsc::channel();
    let (stop_tx, stop_rx) = mpsc::channel();

    let join = spawn_capture_thread(
        Arc::clone(&samples),
        ready_tx,
        stop_rx,
        |_samples, _spec, stop_rx| {
            // Push-to-talk just holds the stream open until told to stop -
            // `_samples` fills itself via the callback captured inside
            // `open_input_stream`; there is nothing else to do here.
            let _ = stop_rx.recv();
        },
    );

    match wait_for_ready(ready_rx, stop_tx.clone()) {
        Ok(spec) => {
            *guard = Some(ActiveCapture {
                stop_tx,
                samples,
                spec,
                join,
            });
            Ok(())
        }
        Err(reason) => {
            let _ = join.join();
            Err(reason)
        }
    }
}

/// Stops the microphone, encodes what was captured as a WAV, and posts it to
/// `/api/voice/utterance`. Returns the transcription (or an honest "not
/// available"/"not you" answer) - never silently drops a failed request.
#[tauri::command]
pub async fn stop_voice_capture(
    app: AppHandle,
    state: State<'_, VoiceCaptureState>,
) -> Result<HeardReply, String> {
    let ActiveCapture {
        stop_tx,
        samples,
        spec,
        join,
    } = state
        .0
        .lock()
        .map_err(poisoned)?
        .take()
        .ok_or_else(|| "not recording".to_string())?;

    // Ignored: a closed receiver means the thread already exited (an error
    // it already reported through `ready_tx`), not a new failure to surface.
    let _ = stop_tx.send(());

    tauri::async_runtime::spawn_blocking(move || join.join())
        .await
        .map_err(|e| format!("the capture thread could not be joined: {e}"))?
        .map_err(|_| "the capture thread panicked".to_string())?;

    let raw_samples = Arc::try_unwrap(samples)
        .map(|m| m.into_inner().unwrap_or_default())
        .unwrap_or_else(|arc| arc.lock().map(|g| g.clone()).unwrap_or_default());

    post_utterance(&app, spec, &raw_samples, "push_to_talk").await
}

/// If a recording is in progress, discards it without sending anything -
/// the desktop equivalent of releasing push-to-talk without meaning it.
#[tauri::command]
pub fn cancel_voice_capture(state: State<VoiceCaptureState>) -> Result<(), String> {
    let active = state.0.lock().map_err(poisoned)?.take();
    if let Some(active) = active {
        let _ = active.stop_tx.send(());
        // Not joined: the caller is not waiting on a result, and this
        // command must not block the UI thread for the stream to close.
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// "Hey Jarvis" listening: a loudness trigger here, the spotter on the server
// ---------------------------------------------------------------------------

/// The floor under the adaptive threshold: below this RMS nothing counts as
/// speech however quiet the room, or a silent room would trigger on hiss.
const VAD_MIN_RMS: f32 = 0.006;
/// The ceiling: however loud the background, a voice at this RMS still
/// counts - so a noisy room makes the trigger less eager, never deaf.
const VAD_MAX_RMS: f32 = 0.05;
/// Speech must be this many times the room's own background level. The old
/// fixed threshold (0.02) is what this replaced: too high for a quiet
/// microphone, which then never triggered at all, and too low in a noisy
/// room, which triggered on everything.
const VAD_FLOOR_FACTOR: f32 = 3.0;
/// Where the background estimate starts before the room has been heard.
const VAD_INITIAL_FLOOR: f32 = 0.005;
/// A burst of speech shorter than this is treated as noise (a cough, a
/// click), not an utterance worth sending.
const VAD_MIN_SPEECH: Duration = Duration::from_millis(250);
/// How long the level must stay below the threshold after speech before the
/// utterance is considered finished. Too short clips a mid-sentence
/// breath; too long makes every exchange feel sluggish.
const VAD_SILENCE_HANGOVER: Duration = Duration::from_millis(900);
/// Safety valve: send even mid-sentence rather than buffer forever if the
/// level parks above threshold indefinitely (a held note, sustained noise).
const VAD_MAX_UTTERANCE: Duration = Duration::from_secs(20);
/// Kept from before the threshold was crossed, so the "h" of "hey" is not
/// clipped.
const VAD_PREROLL: Duration = Duration::from_millis(300);
/// How often the listening loop re-examines the buffer.
const VAD_POLL_INTERVAL: Duration = Duration::from_millis(30);
/// While nothing has crossed the threshold, the buffer is trimmed back to
/// this much trailing audio rather than growing for as long as the
/// microphone stays open with nobody talking.
const VAD_IDLE_KEEP: Duration = Duration::from_millis(500);
/// `/api/voice/status` and `/api/voice/wake` are small; a loopback server
/// that takes longer than this is not going to hear anything either.
const WAKE_CHECK_TIMEOUT: Duration = Duration::from_secs(8);

/// The level a chunk must reach to count as speech, given the background.
pub(crate) fn start_threshold(noise_floor: f32) -> f32 {
    (noise_floor * VAD_FLOOR_FACTOR).clamp(VAD_MIN_RMS, VAD_MAX_RMS)
}

/// The background estimate after one more quiet chunk at `level`. Falls
/// quickly (a door that stopped banging) and rises slowly (so a voice that
/// has not yet crossed the threshold cannot drag the threshold up past it).
pub(crate) fn update_floor(floor: f32, level: f32) -> f32 {
    if level < floor {
        floor * 0.7 + level * 0.3
    } else {
        floor * 0.995 + level * 0.005
    }
}

/// Whether `base` (the API address) is this machine. Wake-word listening
/// sends every utterance in the room to it BEFORE the wake word is heard, so
/// it may only ever go to loopback.
pub(crate) fn is_loopback_base(base: &str) -> bool {
    let rest = base
        .trim()
        .strip_prefix("http://")
        .or_else(|| base.trim().strip_prefix("https://"))
        .unwrap_or("");
    let authority = rest.split('/').next().unwrap_or("");
    let host = if let Some(v6) = authority.strip_prefix('[') {
        v6.split(']').next().unwrap_or("")
    } else {
        authority.split(':').next().unwrap_or("")
    };
    let host = host.to_ascii_lowercase();
    // Parsed, not prefix-matched: "127.0.0.1.example.com" starts with "127."
    // and is somebody else's machine.
    host == "localhost"
        || host
            .parse::<std::net::IpAddr>()
            .map(|ip| ip.is_loopback())
            .unwrap_or(false)
}

/// What `/api/voice/status` says about starting wake-word listening here.
#[derive(Debug, PartialEq)]
pub(crate) enum WakeReadiness {
    /// On, and this PC can hear the phrase: start.
    Ready,
    /// Off, and no card is waiting: ask for one.
    Off,
    /// Off, and a card to turn it on is already waiting.
    Waiting,
    /// Cannot start, for this reason (in the server's own words where it
    /// gave any).
    Cannot(String),
}

pub(crate) fn wake_readiness(status: &serde_json::Value) -> WakeReadiness {
    let Some(wake) = status.get("wake").filter(|w| w.is_object()) else {
        return WakeReadiness::Cannot(
            "The Jarvis server on this PC is too old for \"hey Jarvis\". Run \
             scripts\\apply-patches.ps1 to update it."
                .to_string(),
        );
    };
    let flag = |v: &serde_json::Value, k: &str| v.get(k).and_then(|b| b.as_bool()) == Some(true);
    let spotter = wake.get("spotter").cloned().unwrap_or_default();
    if !flag(wake, "enabled") {
        return if flag(wake, "pending") {
            WakeReadiness::Waiting
        } else {
            WakeReadiness::Off
        };
    }
    if !flag(&spotter, "available") {
        let why = spotter
            .get("why")
            .and_then(|w| w.as_str())
            .filter(|w| !w.is_empty())
            .unwrap_or("its wake-word model is not installed");
        return WakeReadiness::Cannot(format!(
            "This PC cannot listen for \"hey Jarvis\" yet: {why}."
        ));
    }
    WakeReadiness::Ready
}

/// Asks the server whether wake-word listening can start, and - if the wake
/// word is off - asks for it to be turned on, which raises the approval card
/// and changes nothing by itself. `Ok(())` only when it is already on.
async fn ensure_wake_ready(app: &AppHandle) -> Result<(), String> {
    let base = jarvis_base(app);
    if !is_loopback_base(&base) {
        return Err(format!(
            "\"Hey Jarvis\" listening only works with the Jarvis server on this PC. \
             It is set to {base}, and every sentence said in the room would be sent \
             there before the wake word was heard."
        ));
    }
    let client = jarvis_client(Some(WAKE_CHECK_TIMEOUT))?;
    let unreachable = |e: reqwest::Error| {
        if e.is_connect() {
            format!("could not reach the Jarvis server at {base}")
        } else {
            format!("could not ask the Jarvis server about the wake word: {e}")
        }
    };
    let status: serde_json::Value = client
        .get(format!("{base}/api/voice/status"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(unreachable)?
        .json()
        .await
        .map_err(|e| format!("the server's voice status could not be read: {e}"))?;
    match wake_readiness(&status) {
        WakeReadiness::Ready => Ok(()),
        WakeReadiness::Cannot(why) => Err(why),
        WakeReadiness::Waiting => Err(
            "Waiting for you to approve turning on \"hey Jarvis\". Approve the card, \
             then turn this on again."
                .to_string(),
        ),
        WakeReadiness::Off => {
            let reply: serde_json::Value = client
                .post(format!("{base}/api/voice/wake"))
                .headers(jarvis_headers(app)?)
                .json(&serde_json::json!({ "enabled": true }))
                .send()
                .await
                .map_err(unreachable)?
                .json()
                .await
                .unwrap_or_default();
            if reply.get("enabled").and_then(|b| b.as_bool()) == Some(true) {
                return Ok(());
            }
            if reply.get("pending").and_then(|b| b.as_bool()) == Some(true) {
                return Err(
                    "\"Hey Jarvis\" is off. Jarvis has asked for your approval to turn it \
                     on - approve the card, then turn this on again."
                        .to_string(),
                );
            }
            Err(reply
                .get("error")
                .and_then(|e| e.as_str())
                .map(str::to_string)
                .unwrap_or_else(|| {
                    "the server did not turn on the wake word or raise a card".to_string()
                }))
        }
    }
}

#[derive(Default)]
pub struct AutoListenState(Mutex<Option<AutoListenHandle>>);

struct AutoListenHandle {
    stop_tx: mpsc::Sender<()>,
    #[allow(dead_code)] // kept so the thread's lifetime is visible in state, not polled
    join: JoinHandle<()>,
}

enum VadPhase {
    Silence,
    Speaking {
        /// Index into the sample buffer where this utterance begins,
        /// already stepped back by `VAD_PREROLL`.
        started_at_index: usize,
        started_at: Instant,
        last_voiced_at: Instant,
    },
}

fn rms(samples: &[i16]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let sum_sq: f64 = samples
        .iter()
        .map(|&s| {
            let v = s as f64 / i16::MAX as f64;
            v * v
        })
        .sum();
    ((sum_sq / samples.len() as f64).sqrt()) as f32
}

fn busy_error(auto: bool, manual: bool) -> Option<String> {
    if auto {
        return Some("already listening".to_string());
    }
    if manual {
        return Some("push-to-talk is already using the microphone".to_string());
    }
    None
}

/// Starts listening for "hey Jarvis": checks with the server first (see
/// `ensure_wake_ready` - off means an approval card, not a microphone), then
/// opens the microphone and keeps it open, cutting and sending one utterance
/// at a time. Refuses while a push-to-talk recording owns the microphone.
#[tauri::command]
pub async fn start_automatic_listening(
    app: AppHandle,
    state: State<'_, AutoListenState>,
    manual: State<'_, VoiceCaptureState>,
) -> Result<(), String> {
    {
        let auto_busy = state.0.lock().map_err(poisoned)?.is_some();
        let manual_busy = manual.0.lock().map_err(poisoned)?.is_some();
        if let Some(e) = busy_error(auto_busy, manual_busy) {
            return Err(e);
        }
    }

    ensure_wake_ready(&app).await?;

    // Checked again: the server round trip above is an await, and the
    // other mode may have taken the microphone meanwhile.
    let mut guard = state.0.lock().map_err(poisoned)?;
    let manual_busy = manual.0.lock().map_err(poisoned)?.is_some();
    if let Some(e) = busy_error(guard.is_some(), manual_busy) {
        return Err(e);
    }

    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    let (ready_tx, ready_rx) = mpsc::channel();
    let (stop_tx, stop_rx) = mpsc::channel();

    let join = spawn_capture_thread(
        Arc::clone(&samples),
        ready_tx,
        stop_rx,
        move |samples, spec, stop_rx| run_vad_loop(&app, samples, spec, stop_rx),
    );

    match wait_for_ready(ready_rx, stop_tx.clone()) {
        Ok(_spec) => {
            *guard = Some(AutoListenHandle { stop_tx, join });
            Ok(())
        }
        Err(reason) => {
            let _ = join.join();
            Err(reason)
        }
    }
}

/// The trigger's state machine. Runs on the dedicated capture thread - NOT
/// the realtime audio callback, which only ever appends samples - so
/// blocking here on `tauri::async_runtime::block_on` to post a finished
/// utterance is safe. Returns when `stop_rx` fires or disconnects.
fn run_vad_loop(
    app: &AppHandle,
    samples: &Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    stop_rx: &mpsc::Receiver<()>,
) {
    let samples_per_ms = (spec.sample_rate as u128 * spec.channels as u128) / 1000;
    let ms_to_samples = |d: Duration| (d.as_millis() * samples_per_ms) as usize;
    let preroll = ms_to_samples(VAD_PREROLL);
    let idle_keep = ms_to_samples(VAD_IDLE_KEEP);

    let mut read_to: usize = 0;
    let mut phase = VadPhase::Silence;
    let mut floor = VAD_INITIAL_FLOOR;

    loop {
        match stop_rx.recv_timeout(VAD_POLL_INTERVAL) {
            Ok(()) => return,
            Err(mpsc::RecvTimeoutError::Disconnected) => return,
            Err(mpsc::RecvTimeoutError::Timeout) => {}
        }

        // Recovered, not bailed on. The old comment here said a poisoned lock
        // meant "the whole app is already unwinding" - this module contradicts
        // that 460 lines earlier, where the capture callbacks were converted to
        // exactly this call because "once any thread panics while holding it,
        // EVERY later `lock()` returns `Err` for the life of the process".
        //
        // Returning instead ended the VAD loop for good while
        // `AutoListenState` still held its handle, so
        // `start_automatic_listening` answered "already listening" ever after:
        // the microphone open, nothing transcribed, nothing logged. The lock
        // guards a sample buffer, and a partially-written buffer of audio is
        // not a reason to stop listening.
        let mut buf = samples
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if buf.len() <= read_to {
            continue; // nothing new since the last tick
        }
        let level = rms(&buf[read_to..]);
        let now = Instant::now();
        let voiced = level >= start_threshold(floor);

        match &mut phase {
            VadPhase::Silence => {
                if voiced {
                    phase = VadPhase::Speaking {
                        started_at_index: read_to.saturating_sub(preroll),
                        started_at: now,
                        last_voiced_at: now,
                    };
                    // No barge-in here any more. In this mode the trigger
                    // fires on the TV, on other people, and on Jarvis's own
                    // voice from the speakers - stopping a reply for every
                    // one of those would stop every reply. A reply is cut
                    // off when "hey Jarvis" is actually heard (below).
                } else {
                    floor = update_floor(floor, level);
                    if buf.len() > idle_keep {
                        // Nothing has been said in a while - do not let the
                        // buffer grow for the entire time the mic is open.
                        let drop_to = buf.len() - idle_keep;
                        buf.drain(0..drop_to);
                    }
                }
            }
            VadPhase::Speaking {
                started_at_index,
                started_at,
                last_voiced_at,
            } => {
                if voiced {
                    *last_voiced_at = now;
                }
                let silence_elapsed = now.duration_since(*last_voiced_at);
                let speech_elapsed = now.duration_since(*started_at);
                let should_cut = (silence_elapsed >= VAD_SILENCE_HANGOVER
                    && speech_elapsed >= VAD_MIN_SPEECH)
                    || speech_elapsed >= VAD_MAX_UTTERANCE;
                if should_cut {
                    let clip: Vec<i16> = buf[*started_at_index..buf.len()].to_vec();
                    // Reset for the next utterance. Everything captured
                    // during this cut's own send() is preserved - it just
                    // starts the next utterance's buffer, since `buf` here
                    // is truncated, not the live capture stopped.
                    buf.clear();
                    read_to = 0;
                    phase = VadPhase::Silence;
                    drop(buf); // release the lock before the blocking POST

                    let app = app.clone();
                    let heard = tauri::async_runtime::block_on(post_utterance(
                        &app,
                        spec,
                        &clip,
                        "wake_word",
                    ));
                    match heard {
                        Ok(reply) if !reply.available => {
                            // The server cannot do this at all right now
                            // (switched off, no model): the frontend says so
                            // once and turns listening off.
                            let _ = app.emit(VOICE_HEARD, reply);
                        }
                        Ok(reply) if reply.wake_heard => {
                            // Barge-in: "hey Jarvis" stops a reply that is
                            // still being spoken.
                            let _ = app.emit(VOICE_SPEECH_STARTED, ());
                            let _ = app.emit(VOICE_HEARD, reply);
                        }
                        Ok(_) => {
                            // Not addressed to Jarvis, or not the owner. The
                            // server kept nothing; neither does this.
                        }
                        Err(reason) => {
                            eprintln!("[voice] wake-word utterance not sent: {reason}");
                        }
                    }
                    continue;
                }
            }
        }
        read_to = buf.len();
    }
}

/// Stops wake-word listening on this PC (the server's switch is left as it
/// is - the phone may be using it). Fire-and-forget, like
/// `cancel_voice_capture`: the caller is not waiting on a result, and this
/// must not block the UI thread for the stream to close or a POST already in
/// flight to finish.
#[tauri::command]
pub fn stop_automatic_listening(state: State<AutoListenState>) -> Result<(), String> {
    if let Some(active) = state.0.lock().map_err(poisoned)?.take() {
        let _ = active.stop_tx.send(());
    }
    Ok(())
}

#[cfg(test)]
mod wake_tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn only_loopback_may_hear_the_room() {
        for ok in [
            "http://127.0.0.1:4719",
            "http://localhost:4719/",
            "http://[::1]:4719",
            "https://127.0.0.2",
        ] {
            assert!(is_loopback_base(ok), "{ok}");
        }
        for no in [
            "http://100.64.1.2:4719",
            "http://desktop.tailnet.ts.net:4719",
            "http://127.0.0.1.evil.example:4719",
            "http://localhost.example",
            "",
            "127.0.0.1:4719",
        ] {
            assert!(!is_loopback_base(no), "{no}");
        }
    }

    #[test]
    fn readiness_follows_the_server() {
        let ready = json!({"wake": {"enabled": true, "pending": false,
                                    "spotter": {"available": true, "why": ""}}});
        assert_eq!(wake_readiness(&ready), WakeReadiness::Ready);
        let off = json!({"wake": {"enabled": false, "pending": false, "spotter": {}}});
        assert_eq!(wake_readiness(&off), WakeReadiness::Off);
        let waiting = json!({"wake": {"enabled": false, "pending": true}});
        assert_eq!(wake_readiness(&waiting), WakeReadiness::Waiting);
        let no_model = json!({"wake": {"enabled": true,
                                       "spotter": {"available": false, "why": "no files"}}});
        assert!(
            matches!(wake_readiness(&no_model), WakeReadiness::Cannot(w) if w.contains("no files"))
        );
        let old = json!({"listening": {"wake_word": true}});
        assert!(matches!(wake_readiness(&old), WakeReadiness::Cannot(w) if w.contains("too old")));
    }

    #[test]
    fn the_threshold_follows_the_room_within_bounds() {
        assert_eq!(start_threshold(0.0), VAD_MIN_RMS);
        assert!((start_threshold(0.004) - 0.012).abs() < 1e-6);
        assert_eq!(start_threshold(1.0), VAD_MAX_RMS);
        // A quiet room settles low...
        let mut f = VAD_INITIAL_FLOOR;
        for _ in 0..200 {
            f = update_floor(f, 0.001);
        }
        assert!(start_threshold(f) <= 0.007, "{f}");
        // ...and one loud chunk does not drag the floor up past a voice.
        let g = update_floor(f, 0.3);
        assert!(start_threshold(g) < 0.02, "{g}");
    }
}

// ---------------------------------------------------------------------------
// Speech
// ---------------------------------------------------------------------------

/// Asks the backend to speak `text` and returns it as a `data:audio/wav`
/// URI - the same base64-data-URI shape `capture_screen` already returns
/// images in, so the frontend needs no new binary-transfer plumbing.
#[tauri::command]
pub async fn speak_reply(app: AppHandle, text: String) -> Result<String, String> {
    let text = text.trim();
    if text.is_empty() {
        return Err("nothing to speak".to_string());
    }

    let response = jarvis_client(Some(SAY_TIMEOUT))?
        .post(format!("{}/api/voice/say", jarvis_base(&app)))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "text": text }))
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
            } else {
                format!("asking for speech failed: {e}")
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        return Err(format!(
            "the server answered HTTP {} rather than audio: {}",
            status.as_u16(),
            body.trim()
        ));
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|e| format!("could not read the spoken reply: {e}"))?;
    if bytes.is_empty() {
        return Err("the server sent an empty reply".to_string());
    }
    Ok(format!("data:audio/wav;base64,{}", BASE64.encode(&bytes)))
}
