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
//! here can turn it on without that card being approved. Settings' Voice
//! section has the phone's two buttons for the same switch
//! ([`set_wake_word`]): OFF at once - never held, and it stops this
//! listener too - and ON, which is the same one card.
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
//! WHERE A SENTENCE ENDS: SMART TURN, WHEN THE SERVER HAS IT
//! Loudness alone cannot tell "I have finished" from "I am thinking". When
//! the server on this PC has the Smart Turn model (`turn` in
//! `/api/voice/status`), a 200 ms pause is put to it (`POST /api/voice/turn`,
//! loopback, the same audio this listener already sends there): "finished"
//! ends the utterance at once, "not finished" keeps it open for up to two
//! seconds of quiet. Without it, the fixed 900 ms hangover below is used, as
//! before. See `pause_step` and backend/jarvis_turn.py.
//!
//! INTERRUPTING JARVIS: "STOP", AND WINDOWS' ECHO CANCELLING
//! While Jarvis speaks, this listener keeps listening. Saying "hey Jarvis"
//! already cut a reply off; saying "stop" now does too, and does nothing
//! else. The server spots it (`jarvis_wakeword.spot_stop`: a small
//! stop-word model on the same sound fingerprint as the wake word) in a
//! SHORT clip and answers `stop: true` before any voice check - stopping
//! speech is harmless, so it may act first - and this emits
//! `VOICE_SPEECH_STARTED`, which silences the reply. Anything longer is an
//! ordinary clip and goes through every check. To hear the owner over
//! Jarvis's own voice, the microphone is opened through Windows' echo
//! cancelling when the machine has it (`aec.rs`, the "communications"
//! capture category, used only when Windows reports acoustic echo
//! cancellation active on it); otherwise the plain capture below, as before.
//! Since 2026-09-25 talking over a reply works too (voice_flow.rs): half a
//! second of speech tells the Jarvis bar, which pauses the reply and asks
//! for the first two seconds to be checked by the PC as "stop or not"
//! (`source=barge_in`, never transcribed); the utterance still goes as
//! `source=wake_word` when it ends.
//! Settings' "Interrupt Jarvis while it talks" (`src/barge-in.js`, on by
//! default) is read by the Jarvis bar, not here: with it off, the bar
//! ignores both events - and any question heard - while Jarvis is talking.
//! This listener sends and emits exactly as before either way.
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
use tauri::{AppHandle, Emitter, Manager, State};

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers};
use crate::events::{
    VOICE_BARGE_ONSET, VOICE_BARGE_VERDICT, VOICE_HEARD, VOICE_LEVEL, VOICE_LISTENING,
    VOICE_SPEECH_STARTED,
};

/// Total round-trip budget for one utterance: speaker verification plus a
/// whole-clip transcription is not instant, but it is also not a chat
/// completion - thirty seconds is generous without being indefinite.
const UTTERANCE_TIMEOUT: Duration = Duration::from_secs(30);
/// Synthesising a reply is comparable work in the other direction.
const SAY_TIMEOUT: Duration = Duration::from_secs(30);
/// Which microphone this app's clips come from, as the server names it.
const MIC_DESKTOP: &str = "desktop";
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
pub(crate) fn spawn_capture_thread(
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

pub(crate) fn wait_for_ready(
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

pub(crate) fn poisoned<T>(_: T) -> String {
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
    #[serde(default)]
    stop: bool,
    /// Since the stricter voice check (docs/JARVIS-API.md section 16): the
    /// clip was too short to be sure it was the owner, and `reason` says so.
    #[serde(default)]
    too_short: bool,
    /// May an answer drawn from email, the calendar, notes or memory be READ
    /// ALOUD for this request? Missing (an older PC) is read as `false`.
    #[serde(default)]
    private_aloud: bool,
    /// The words asked about something private - a hint.
    #[serde(default)]
    question_private: bool,
    /// May an answer that uses what Jarvis remembers be read aloud, when
    /// nothing else about it is private? True by default on the PC (the
    /// owner's choice, 2026-09-24). Missing (an older PC) is read as `false`.
    #[serde(default)]
    memory_aloud: bool,
    /// May an answer that uses a SENSITIVE saved fact (health, money,
    /// passwords, other people's private details) be read aloud? True only
    /// when the owner chose "Read aloud" for those answers AND a real voice
    /// check passed (the owner's decision 13). Missing (an older PC) is read
    /// as `false`.
    #[serde(default)]
    sensitive_aloud: bool,
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
    /// The clip was the stop word ("stop", "Jarvis, stop"): silence the
    /// reply being spoken, and nothing else.
    pub stop: bool,
    /// Too short to check; `reason` says how much more to say. Not "that
    /// did not sound like you".
    pub too_short: bool,
    /// The server says a private answer may be read aloud for this
    /// request; `false` when it did not say (private-speech.js).
    pub private_aloud: bool,
    /// The question itself was about something private.
    pub question_private: bool,
    /// Answers that use remembered facts may be read aloud (private-speech.js).
    pub memory_aloud: bool,
    /// Answers that use a sensitive saved fact may be read aloud too
    /// (private-speech.js). `false` when the PC did not say.
    pub sensitive_aloud: bool,
}

impl HeardReply {
    /// "Listening cannot carry on", in the shape the quickbar already reads
    /// that from (`available: false` with the reason).
    pub(crate) fn unavailable(reason: String) -> Self {
        Self {
            is_owner: false,
            text: String::new(),
            score: 0.0,
            threshold: 0.0,
            available: false,
            source: "wake_word".to_string(),
            reason,
            wake_heard: false,
            awake: false,
            awake_seconds: 0.0,
            stop: false,
            too_short: false,
            private_aloud: false,
            question_private: false,
            memory_aloud: false,
            sensitive_aloud: false,
        }
    }
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
            stop: raw.stop,
            too_short: raw.too_short,
            private_aloud: raw.private_aloud,
            question_private: raw.question_private,
            memory_aloud: raw.memory_aloud,
            sensitive_aloud: raw.sensitive_aloud,
        }
    }
}

/// The rate the server's speech models take: `jarvis_speech.AUDIO_IN` says
/// "WAV, 16-bit mono PCM", 16000 Hz, and that the server does not convert.
const SERVER_RATE: u32 = 16_000;
/// The longest push-to-talk clip sent. At 16 kHz mono a second is 32 000
/// bytes, so two minutes is about 3.7 MiB - under the server's 4 MiB body
/// limit, with room for the WAV header. Longer is refused with a sentence
/// rather than sent to be refused by the server.
const MAX_PUSH_TO_TALK: Duration = Duration::from_secs(120);

/// `samples` (interleaved, as captured, at `spec`) as the server takes them:
/// one channel, 16 kHz.
///
/// It used to send the microphone's own format - 48 kHz stereo on many
/// PCs, 192 000 bytes a second - so a push-to-talk clip passed the server's
/// 4 MiB body limit after about 22 seconds. Channels are averaged; a higher
/// rate is brought down by averaging each output sample's span of input
/// (which also keeps what is above 8 kHz from folding back into the
/// speech band), a lower one is brought up by straight-line interpolation.
pub(crate) fn to_server_format(
    spec: hound::WavSpec,
    samples: &[i16],
) -> (hound::WavSpec, Vec<i16>) {
    to_format(spec, samples, SERVER_RATE)
}

/// `samples` (interleaved, at `spec`) as one channel at `rate`: the
/// conversion [`to_server_format`] makes, at any rate. Settings' voice
/// training sends 16 kHz like every other clip; a recording for a custom
/// voice is kept at 24 kHz, the rate the server stores voices at
/// (`jarvis_voices.SAMPLE_RATE`), so it loses nothing above 8 kHz.
pub(crate) fn to_format(
    spec: hound::WavSpec,
    samples: &[i16],
    rate: u32,
) -> (hound::WavSpec, Vec<i16>) {
    let channels = usize::from(spec.channels.max(1));
    let mono: Vec<i32> = samples
        .chunks_exact(channels)
        .map(|frame| frame.iter().map(|&s| i32::from(s)).sum::<i32>() / channels as i32)
        .collect();
    let out_spec = hound::WavSpec {
        channels: 1,
        sample_rate: rate,
        bits_per_sample: 16,
        sample_format: hound::SampleFormat::Int,
    };
    (out_spec, resample(&mono, spec.sample_rate, rate))
}

/// One channel of samples from rate `from` to rate `to`.
fn resample(mono: &[i32], from: u32, to: u32) -> Vec<i16> {
    let narrow = |v: i64| v.clamp(i64::from(i16::MIN), i64::from(i16::MAX)) as i16;
    if from == to || from == 0 || to == 0 || mono.is_empty() {
        return mono.iter().map(|&s| narrow(i64::from(s))).collect();
    }
    let (from, to) = (u64::from(from), u64::from(to));
    let len = mono.len();
    let n_out = (len as u64 * to / from) as usize;
    if from > to {
        (0..n_out)
            .map(|j| {
                let a = (j as u64 * from / to) as usize;
                let b = (((j as u64 + 1) * from / to) as usize).clamp(a + 1, len);
                let span = &mono[a..b];
                narrow(span.iter().map(|&s| i64::from(s)).sum::<i64>() / span.len() as i64)
            })
            .collect()
    } else {
        (0..n_out)
            .map(|j| {
                let pos = j as f64 * from as f64 / to as f64;
                let i = (pos.floor() as usize).min(len - 1);
                let frac = pos - i as f64;
                let a = f64::from(mono[i]);
                let b = f64::from(mono[(i + 1).min(len - 1)]);
                narrow((a + (b - a) * frac).round() as i64)
            })
            .collect()
    }
}

/// `samples` as the WAV the server takes: [`to_server_format`], encoded.
pub(crate) fn server_wav(spec: hound::WavSpec, samples: &[i16]) -> Result<Vec<u8>, String> {
    let (spec, samples) = to_server_format(spec, samples);
    encode_wav(spec, &samples)
}

/// How long `samples` (interleaved, at `spec`) lasts.
pub(crate) fn clip_length(spec: hound::WavSpec, samples: &[i16]) -> Duration {
    let per_second = u64::from(spec.sample_rate.max(1)) * u64::from(spec.channels.max(1));
    Duration::from_millis(samples.len() as u64 * 1000 / per_second)
}

/// `samples` (interleaved, as captured) as the bytes of one 16-bit WAV file.
pub(crate) fn encode_wav(spec: hound::WavSpec, samples: &[i16]) -> Result<Vec<u8>, String> {
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
    Ok(cursor.into_inner())
}

/// Encodes `samples` as a WAV and posts it to `/api/voice/utterance` at
/// `base`. Shared by push-to-talk and automatic listening; only `source`
/// differs between them. `base` is passed in rather than read here so the
/// wake-word listener sends to exactly the address it has just checked is
/// loopback ([`wake_audio_refusal`]) - reading it again here would leave a
/// gap for Settings to change it in between.
async fn post_utterance(
    app: &AppHandle,
    base: &str,
    spec: hound::WavSpec,
    samples: &[i16],
    source: &str,
    waited: Option<Duration>,
) -> Result<HeardReply, String> {
    if samples.is_empty() {
        return Err("nothing was recorded - the microphone produced no audio".to_string());
    }
    let wav_bytes = server_wav(spec, samples)?;

    // mic=desktop: the server keeps one voice print per microphone and
    // checks this clip against this PC's own when there is one (a server
    // older than 2026-09-24 ignores it). See backend/voice-mic.patch.
    // `waited_ms` (docs/JARVIS-API.md section 17, 2): how long it was since
    // speech was last heard when the clip was sent - a number, for the PC's
    // delay table; a PC without voice-flow.patch ignores it.
    let waited = waited
        .map(|w| format!("&waited_ms={}", w.as_millis().min(60_000)))
        .unwrap_or_default();
    let response = jarvis_client(Some(UTTERANCE_TIMEOUT))?
        .post(format!(
            "{base}/api/voice/utterance?source={source}&mic={MIC_DESKTOP}{waited}"
        ))
        .headers(jarvis_headers(app)?)
        .header("Content-Type", "audio/wav")
        .body(wav_bytes)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {base}")
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

impl VoiceCaptureState {
    /// A push-to-talk recording holds the microphone right now. Read by
    /// Settings' voice recordings (`voice_training.rs`), which must not
    /// open a second capture on the same device.
    pub(crate) fn busy(&self) -> bool {
        self.0
            .lock()
            .map(|g| g.is_some())
            .unwrap_or_else(|p| p.into_inner().is_some())
    }
}

struct ActiveCapture {
    stop_tx: mpsc::Sender<()>,
    samples: Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    join: JoinHandle<()>,
}

/// How often push-to-talk re-reads the tail of the buffer for the face's
/// mic-level meter - the same cadence [`VAD_POLL_INTERVAL`] uses for the
/// same reason: often enough that a syllable is not averaged away, cheap
/// enough that it is one small IPC message, never the audio.
const LEVEL_POLL_INTERVAL: Duration = Duration::from_millis(30);

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
    app: AppHandle,
    state: State<VoiceCaptureState>,
    auto: State<AutoListenState>,
    training: State<crate::voice_training::SampleState>,
) -> Result<(), String> {
    // Asked before this state's lock is taken. Settings' recorder
    // (voice_training.rs) likewise asks `busy` before taking its own: neither
    // holds its lock while asking the other, so the two cannot deadlock.
    if training.recording() {
        return Err(crate::voice_training::MIC_IN_SETTINGS.to_string());
    }
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
        move |samples, _spec, stop_rx| {
            // Push-to-talk holds the stream open until told to stop - the
            // buffer fills itself via the callback captured inside
            // `open_input_stream`. The only thing left to do here is the
            // face's mic-level meter (item 1, UI-AUDIT-2026-09-26.md): the
            // same poll-and-emit shape `run_vad_loop` already uses for the
            // wake-word trigger, one number per tick, never the audio.
            let mut read_to = 0usize;
            loop {
                match stop_rx.recv_timeout(LEVEL_POLL_INTERVAL) {
                    Ok(()) => return,
                    Err(mpsc::RecvTimeoutError::Disconnected) => return,
                    Err(mpsc::RecvTimeoutError::Timeout) => {}
                }
                let buf = samples.lock().unwrap_or_else(|p| p.into_inner());
                if buf.len() <= read_to {
                    continue; // nothing new since the last tick
                }
                let level = rms(&buf[read_to..]);
                read_to = buf.len();
                drop(buf);
                crate::emit_quickbar(&app, VOICE_LEVEL, level_from_rms(level));
            }
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

    let held = clip_length(spec, &raw_samples);
    if held > MAX_PUSH_TO_TALK {
        return Err(format!(
            "That was too long to send - {} seconds. Hold the button for under two \
             minutes, and say a long request in parts. Nothing was sent.",
            held.as_secs()
        ));
    }

    // Push-to-talk may go to a server elsewhere: holding the button is a
    // deliberate act, unlike the room audio the wake-word listener sends.
    let base = jarvis_base(&app);
    let waited = crate::voice_flow::trailing_quiet(spec, &raw_samples);
    post_utterance(&app, &base, spec, &raw_samples, "push_to_talk", waited).await
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
/// A burst of speech with less VOICED time than this is treated as noise (a
/// cough, a click), not an utterance worth sending: it is dropped when the
/// pause after it is over. Voiced time, not time since the burst began - the
/// pause itself used to count, so by the time the 900 ms hangover ended
/// every cough had "lasted" 900 ms and was sent.
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

// ---- Smart Turn: "finished, or only paused?" ------------------------------
//
// With the server's Smart Turn model available (`/api/voice/status` ->
// `turn.enabled` and `turn.available`), a pause is no longer judged by its
// length alone. After TURN_ASK_AFTER of quiet the last few seconds go to
// `POST /api/voice/turn` - on this PC, over loopback, where this listener
// already sends every utterance - and the model answers with the chance the
// sentence is finished. Finished: the utterance is cut there and then,
// instead of 900 ms later. Not finished: recording carries on, and the next
// pause is asked about again; a pause reaching TURN_MAX_PAUSE ends it
// whatever the model said, so a wrong "not finished" can never hang it. Any
// failure falls back to the old fixed hangover for the rest of the session.
// The model hears sound, not words - it produces one number
// (backend/jarvis_turn.py).

/// Quiet this long after speech, and the model is asked. Pipecat's own VAD
/// setting for Smart Turn.
const TURN_ASK_AFTER: Duration = Duration::from_millis(200);
/// With the model: the longest pause kept inside a sentence it called
/// unfinished.
const TURN_MAX_PAUSE: Duration = Duration::from_millis(2000);
/// The model looks at the last 8 s at most; no more is sent.
const TURN_WINDOW: Duration = Duration::from_secs(8);
/// One small WAV and one ~50 ms model run, over loopback.
const TURN_TIMEOUT: Duration = Duration::from_secs(3);

/// What the listener does after one more tick of an utterance.
#[derive(Debug, PartialEq)]
pub(crate) enum PauseStep {
    /// Keep recording.
    Listen,
    /// Ask Smart Turn whether the sentence is finished (once per pause).
    Ask,
    /// Cut here and send.
    Cut,
    /// Too little of it was voice (a cough, a click): drop it, send nothing.
    Discard,
}

/// The whole end-of-utterance rule, pure so it is tested: `silence` since
/// the last loud chunk, `voiced` - how much of the utterance so far was
/// loud enough to be speech - and `elapsed` since it began, whether this
/// pause was already asked about, and whether Smart Turn is in use.
pub(crate) fn pause_step(
    silence: Duration,
    voiced: Duration,
    elapsed: Duration,
    asked: bool,
    use_model: bool,
) -> PauseStep {
    if elapsed >= VAD_MAX_UTTERANCE {
        return PauseStep::Cut;
    }
    if voiced < VAD_MIN_SPEECH {
        // Never asked about, never sent: once the ordinary pause is over it
        // is dropped, and until then more speech may still make it count.
        return if silence >= VAD_SILENCE_HANGOVER {
            PauseStep::Discard
        } else {
            PauseStep::Listen
        };
    }
    let longest = if use_model {
        TURN_MAX_PAUSE
    } else {
        VAD_SILENCE_HANGOVER
    };
    if silence >= longest {
        return PauseStep::Cut;
    }
    if use_model && !asked && silence >= TURN_ASK_AFTER {
        return PauseStep::Ask;
    }
    PauseStep::Listen
}

/// `jarvis_turn.Turn.as_dict()`, the fields read here.
#[derive(Debug, Deserialize)]
struct TurnRaw {
    #[serde(default)]
    available: bool,
    #[serde(default)]
    complete: bool,
}

/// Whether `/api/voice/status` says Smart Turn may be asked.
pub(crate) fn turn_usable(status: &serde_json::Value) -> bool {
    let turn = status.get("turn");
    let flag = |k: &str| turn.and_then(|t| t.get(k)).and_then(|b| b.as_bool()) == Some(true);
    flag("enabled") && flag("available")
}

/// Asks the server at `base` whether the utterance so far is finished.
/// `Ok(None)`: the server cannot say (no model) - the caller stops asking.
/// `base` must already have passed [`wake_audio_refusal`]: this is room
/// audio, sent before any wake word was heard.
async fn ask_turn(
    app: &AppHandle,
    base: &str,
    spec: hound::WavSpec,
    samples: &[i16],
) -> Result<Option<bool>, String> {
    let wav = server_wav(spec, samples)?;
    let response = jarvis_client(Some(TURN_TIMEOUT))?
        .post(format!("{base}/api/voice/turn"))
        .headers(jarvis_headers(app)?)
        .header("Content-Type", "audio/wav")
        .body(wav)
        .send()
        .await
        .map_err(|e| format!("could not ask whether the sentence was finished: {e}"))?;
    if !response.status().is_success() {
        return Err(format!(
            "the server answered HTTP {} to the turn check",
            response.status().as_u16()
        ));
    }
    let turn: TurnRaw = response
        .json()
        .await
        .map_err(|e| format!("the turn check's answer could not be read: {e}"))?;
    Ok(turn.available.then_some(turn.complete))
}

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

/// Why wake-word audio may NOT go to `base`, or `None` when it may.
///
/// Checked when listening starts AND again before every clip and every
/// Smart Turn check leaves this PC (`run_vad_loop`): the address is read
/// from Settings on every request, so a check made only at the start let a
/// base changed afterwards - to a server elsewhere - receive every sentence
/// said in the room.
pub(crate) fn wake_audio_refusal(base: &str) -> Option<String> {
    if is_loopback_base(base) {
        return None;
    }
    Some(format!(
        "\"Hey Jarvis\" listening only works with the Jarvis server on this PC. \
         It is set to {base}, and every sentence said in the room would be sent \
         there before the wake word was heard."
    ))
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
/// and changes nothing by itself. `Ok` only when it is already on, carrying
/// whether Smart Turn may be asked (see [`turn_usable`]).
async fn ensure_wake_ready(app: &AppHandle) -> Result<bool, String> {
    let base = jarvis_base(app);
    if let Some(why) = wake_audio_refusal(&base) {
        return Err(why);
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
        WakeReadiness::Ready => Ok(turn_usable(&status)),
        WakeReadiness::Cannot(why) => Err(why),
        WakeReadiness::Waiting => Err(
            "Waiting for you to approve turning on \"hey Jarvis\". Approve the card \
             in the Jarvis bar, on the widget, or on your phone's Home screen, \
             then turn this on again."
                .to_string(),
        ),
        WakeReadiness::Off => {
            // Asking for it raises an approval card, so it is held while
            // the event stream is stale - rule 4, the same one-direction
            // hold as the second card's and the big model's ON. Stopping
            // listening never comes here and is never held.
            if app.state::<crate::stream::StreamState>().link().stale {
                return Err(
                    "\"Hey Jarvis\" is off, and turning it on needs your approval. The \
                     connection to Jarvis is catching up, so that is held until it does - \
                     try again in a moment."
                        .to_string(),
                );
            }
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
                return Ok(turn_usable(&status));
            }
            if reply.get("pending").and_then(|b| b.as_bool()) == Some(true) {
                return Err(
                    "\"Hey Jarvis\" is off. Jarvis has asked for your approval to turn it \
                     on - approve the card in the Jarvis bar, on the widget, or on your \
                     phone's Home screen, then turn this on again."
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
        /// How much of the audio since `started_at` was loud enough to be
        /// speech - what the minimum-speech rule counts.
        voiced: Duration,
        /// Smart Turn was already asked about the current pause.
        asked: bool,
        /// This utterance's number, for interrupting by talking
        /// (voice_flow.rs): the Jarvis bar asks about it by this.
        id: u64,
        /// The bar was told this utterance held enough speech to be an
        /// interruption (`VOICE_BARGE_ONSET`).
        told: bool,
        /// Its first seconds were sent as `source=barge_in`.
        barge_sent: bool,
    },
}

pub(crate) fn rms(samples: &[i16]) -> f32 {
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

/// `rms()` above sits low even for a loud voice - the same reason
/// `voice.js`'s own `attachAnalyser` scales its Web Audio reading by 3.2
/// before it reaches `setLevel()`. Used so the two sources (this file, and a
/// browser AnalyserNode, if one is ever wired here too) land on the same
/// scale before either reaches the face.
pub(crate) fn level_from_rms(rms: f32) -> f32 {
    (rms * 3.2).clamp(0.0, 1.0)
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

/// What `start_automatic_listening` tells the page, and what
/// `VOICE_LISTENING` tells it when that changes while listening.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ListenInfo {
    /// The microphone is open through Windows' echo cancelling, so "stop"
    /// and "hey Jarvis" can be heard over Jarvis's own voice.
    pub echo_cancelling: bool,
    /// Windows' name for the microphone being listened to, when it gave
    /// one - both paths open the default microphone (aec.rs, "WHICH
    /// MICROPHONE"), so the page can say which one that is.
    pub microphone: Option<String>,
    /// Something to say about a change, in words; `None` when starting.
    pub note: Option<String>,
}

/// Windows' name for the default microphone - the one both the ordinary
/// capture (cpal) and the echo-cancelled one (aec.rs) open.
fn default_microphone_name() -> Option<String> {
    cpal::default_host()
        .default_input_device()
        .and_then(|d| d.name().ok())
        .map(|n| n.trim().to_string())
        .filter(|n| !n.is_empty())
}

/// How the listening loop ended.
#[derive(Debug, PartialEq)]
pub(crate) enum VadEnd {
    /// Told to stop, or its stop channel went away.
    Stopped,
    /// Refused to send (see [`wake_audio_refusal`]); listening is already
    /// stopped and the page told.
    Refused,
    /// The echo-cancelled microphone stopped under it, for this reason.
    MicFailed(String),
}

/// Whether the microphone feeding the loop has died: a message on `died`,
/// or `died` gone without one (its thread ended - it only ends on its own
/// when something went wrong, since the loop stops it, not the other way).
pub(crate) fn mic_died(died: Option<&mpsc::Receiver<String>>) -> Option<String> {
    match died?.try_recv() {
        Ok(why) => Some(why),
        Err(mpsc::TryRecvError::Empty) => None,
        Err(mpsc::TryRecvError::Disconnected) => {
            Some("the echo-cancelled microphone stopped without saying why".to_string())
        }
    }
}

/// The echo-cancelled microphone stopped while listening: carry on through
/// the ordinary one, on the same stop channel, and tell the page - or, if
/// that cannot be opened either, stop listening and say why. Never carries
/// on deaf while the page still says "listening".
fn continue_without_echo_cancelling(
    app: &AppHandle,
    stop_rx: &mpsc::Receiver<()>,
    use_turn: bool,
    why: String,
) {
    crate::logfile::log(&format!(
        "[voice] the echo-cancelled microphone stopped ({why}); carrying on with the ordinary one"
    ));
    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    match open_input_stream(Arc::clone(&samples)) {
        Ok((spec, stream)) => {
            let _ = app.emit(
                VOICE_LISTENING,
                ListenInfo {
                    echo_cancelling: false,
                    microphone: default_microphone_name(),
                    note: Some(
                        "Echo cancelling stopped working, so Jarvis is listening through the \
                         ordinary microphone now. \"Stop\" may not be heard while Jarvis talks."
                            .to_string(),
                    ),
                },
            );
            let _ = run_vad_loop(app, &samples, spec, stop_rx, use_turn, None);
            drop(stream); // stops the microphone
        }
        Err(e) => stop_listening_because(
            app,
            format!(
                "The microphone stopped ({why}), and it could not be opened again ({e}). \
                 Listening for \"hey Jarvis\" is off."
            ),
        ),
    }
}

/// Opens the microphone through Windows' echo cancelling (aec.rs) and runs
/// the listener on it. `None` - with nothing left running - when this
/// machine does not report echo cancelling, or anything fails; the caller
/// then uses the ordinary capture.
fn start_echo_cancelled(
    app: &AppHandle,
    samples: &Arc<Mutex<Vec<i16>>>,
    use_turn: bool,
) -> Option<AutoListenHandle> {
    let (ready_tx, ready_rx) = mpsc::channel();
    let (mic_stop_tx, mic_stop_rx) = mpsc::channel();
    let (died_tx, died_rx) = mpsc::channel();
    let mic_samples = Arc::clone(samples);
    let mic =
        std::thread::spawn(move || crate::aec::run(mic_samples, ready_tx, mic_stop_rx, died_tx));
    match ready_rx.recv_timeout(STREAM_READY_TIMEOUT) {
        Ok(Ok(opened)) => {
            let (stop_tx, stop_rx) = mpsc::channel();
            let app = app.clone();
            let vad_samples = Arc::clone(samples);
            // The microphone has its own thread (it must be drained every
            // few milliseconds, which the listener - blocking on a POST -
            // cannot promise); the listener runs here, and stopping it
            // stops the microphone. If the microphone's thread fails first,
            // the listener hears it (`died`) and carries on through the
            // ordinary microphone rather than listening to nothing.
            let join = std::thread::spawn(move || {
                let end = run_vad_loop(
                    &app,
                    &vad_samples,
                    opened.spec,
                    &stop_rx,
                    use_turn,
                    Some(&died_rx),
                );
                let _ = mic_stop_tx.send(());
                let _ = mic.join();
                if let VadEnd::MicFailed(why) = end {
                    continue_without_echo_cancelling(&app, &stop_rx, use_turn, why);
                }
            });
            Some(AutoListenHandle { stop_tx, join })
        }
        Ok(Err(why)) => {
            eprintln!("[voice] no echo cancelling, using the ordinary microphone: {why}");
            let _ = mic.join();
            None
        }
        Err(_) => {
            // Still opening: dropping the stop sender ends it when it does.
            drop(mic_stop_tx);
            None
        }
    }
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
    training: State<'_, crate::voice_training::SampleState>,
) -> Result<ListenInfo, String> {
    {
        let auto_busy = state.0.lock().map_err(poisoned)?.is_some();
        let manual_busy = manual.0.lock().map_err(poisoned)?.is_some();
        if let Some(e) = busy_error(auto_busy, manual_busy) {
            return Err(e);
        }
        if training.recording() {
            return Err(crate::voice_training::MIC_IN_SETTINGS.to_string());
        }
    }

    let use_turn = ensure_wake_ready(&app).await?;

    // Checked again: the server round trip above is an await, and the
    // other mode may have taken the microphone meanwhile. Settings' recorder
    // is asked before this lock is taken, and it stops this listener before
    // taking its own: neither holds its lock while asking the other.
    if training.recording() {
        return Err(crate::voice_training::MIC_IN_SETTINGS.to_string());
    }
    let mut guard = state.0.lock().map_err(poisoned)?;
    let manual_busy = manual.0.lock().map_err(poisoned)?.is_some();
    if let Some(e) = busy_error(guard.is_some(), manual_busy) {
        return Err(e);
    }

    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    let microphone = default_microphone_name();
    if let Some(handle) = start_echo_cancelled(&app, &samples, use_turn) {
        *guard = Some(handle);
        return Ok(ListenInfo {
            echo_cancelling: true,
            microphone,
            note: None,
        });
    }
    let (ready_tx, ready_rx) = mpsc::channel();
    let (stop_tx, stop_rx) = mpsc::channel();

    let join = spawn_capture_thread(
        Arc::clone(&samples),
        ready_tx,
        stop_rx,
        move |samples, spec, stop_rx| {
            let _ = run_vad_loop(&app, samples, spec, stop_rx, use_turn, None);
        },
    );

    match wait_for_ready(ready_rx, stop_tx.clone()) {
        Ok(_spec) => {
            *guard = Some(AutoListenHandle { stop_tx, join });
            Ok(ListenInfo {
                echo_cancelling: false,
                microphone,
                note: None,
            })
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
/// utterance is safe. Returns when `stop_rx` fires or disconnects, when a
/// send is refused, or - with `died` given (the echo-cancelled microphone,
/// which runs on a thread of its own) - when that microphone stops.
fn run_vad_loop(
    app: &AppHandle,
    samples: &Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    stop_rx: &mpsc::Receiver<()>,
    mut use_turn: bool,
    died: Option<&mpsc::Receiver<String>>,
) -> VadEnd {
    let samples_per_ms = (spec.sample_rate as u128 * spec.channels as u128) / 1000;
    let ms_to_samples = |d: Duration| (d.as_millis() * samples_per_ms) as usize;
    let preroll = ms_to_samples(VAD_PREROLL);
    let idle_keep = ms_to_samples(VAD_IDLE_KEEP);
    let turn_window = ms_to_samples(TURN_WINDOW);

    let mut read_to: usize = 0;
    let mut phase = VadPhase::Silence;
    let mut floor = VAD_INITIAL_FLOOR;

    loop {
        match stop_rx.recv_timeout(VAD_POLL_INTERVAL) {
            Ok(()) => return VadEnd::Stopped,
            Err(mpsc::RecvTimeoutError::Disconnected) => return VadEnd::Stopped,
            Err(mpsc::RecvTimeoutError::Timeout) => {}
        }
        // The echo-cancelled microphone's thread failed: nothing more will
        // arrive in `samples`, so listening on would be listening to nothing.
        if let Some(why) = mic_died(died) {
            return VadEnd::MicFailed(why);
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
        // The face's mic-level meter (item 1, UI-AUDIT-2026-09-26.md): this
        // loop already computed `level` for the wake-word trigger below and
        // used to throw it away once it had. One number, never the audio.
        crate::emit_quickbar(app, VOICE_LEVEL, level_from_rms(level));
        let now = Instant::now();
        let voiced = level >= start_threshold(floor);
        // How much audio this tick looked at: the new samples, as time.
        let chunk = Duration::from_millis(
            ((buf.len() - read_to) as u128 / samples_per_ms.max(1)).min(u64::MAX as u128) as u64,
        );
        // Set when the buffer grew during a Smart Turn round trip, so the
        // next tick still looks at the audio that arrived meanwhile.
        let mut analysed_to: Option<usize> = None;

        match &mut phase {
            VadPhase::Silence => {
                if voiced {
                    phase = VadPhase::Speaking {
                        started_at_index: read_to.saturating_sub(preroll),
                        started_at: now,
                        last_voiced_at: now,
                        voiced: chunk,
                        asked: false,
                        id: crate::voice_flow::next_utterance_id(),
                        told: false,
                        barge_sent: false,
                    };
                    // No barge-in here any more. In this mode the trigger
                    // fires on the TV, on other people, and on Jarvis's own
                    // voice from the speakers - stopping a reply for every
                    // one of those would stop every reply. A reply is cut
                    // off when "hey Jarvis" is actually heard (below), or -
                    // since 2026-09-25 - paused after half a second of
                    // speech and stopped only when the PC says it was the
                    // owner (voice_flow.rs, in the Speaking arm below).
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
                voiced: voiced_time,
                asked,
                id,
                told,
                barge_sent,
            } => {
                if voiced {
                    *last_voiced_at = now;
                    *voiced_time += chunk;
                    // Speech again after a pause the model called
                    // unfinished: the next pause is a new question.
                    *asked = false;
                }
                let silence_elapsed = now.duration_since(*last_voiced_at);
                let speech_elapsed = now.duration_since(*started_at);
                let voiced_so_far = *voiced_time;

                // Interrupting by talking (voice_flow.rs): half a second of
                // speech, and the Jarvis bar hears of it - it pauses a reply
                // that is playing and asks for this utterance to be checked.
                // The first two seconds then go to this PC as "stop or not".
                if crate::voice_flow::onset_due(voiced_so_far, *told) {
                    *told = true;
                    let _ = app.emit(VOICE_BARGE_ONSET, crate::voice_flow::BargeOnset { id: *id });
                }
                if *told
                    && crate::voice_flow::clip_due(
                        speech_elapsed,
                        crate::voice_flow::barge_wanted(*id),
                        *barge_sent,
                        false,
                    )
                {
                    *barge_sent = true;
                    let base = jarvis_base(app);
                    if let Some(why) = wake_audio_refusal(&base) {
                        drop(buf);
                        stop_listening_because(app, why);
                        return VadEnd::Refused;
                    }
                    analysed_to = Some(buf.len());
                    let clip: Vec<i16> = buf[*started_at_index..].to_vec();
                    // Not holding the lock through the round trip: the
                    // microphone keeps filling the buffer.
                    drop(buf);
                    let verdict = tauri::async_runtime::block_on(crate::voice_flow::post_barge_in(
                        app, &base, spec, &clip, *id,
                    ));
                    let _ = app.emit(VOICE_BARGE_VERDICT, verdict);
                    buf = samples
                        .lock()
                        .unwrap_or_else(|poisoned| poisoned.into_inner());
                }
                let mut should_cut = match pause_step(
                    silence_elapsed,
                    voiced_so_far,
                    speech_elapsed,
                    *asked,
                    use_turn,
                ) {
                    PauseStep::Cut => true,
                    PauseStep::Listen => false,
                    PauseStep::Discard => {
                        // A cough, a click: nothing is sent, and the
                        // next utterance starts from a clean buffer.
                        buf.clear();
                        read_to = 0;
                        phase = VadPhase::Silence;
                        continue;
                    }
                    PauseStep::Ask => {
                        // Room audio is about to leave this thread: only
                        // to this PC, checked now and not only when
                        // listening started (see wake_audio_refusal).
                        let base = jarvis_base(app);
                        if let Some(why) = wake_audio_refusal(&base) {
                            drop(buf);
                            stop_listening_because(app, why);
                            return VadEnd::Refused;
                        }
                        *asked = true;
                        // Kept if the barge-in check above already set it:
                        // the audio that arrived during THAT round trip has
                        // not been looked at yet either.
                        analysed_to.get_or_insert(buf.len());
                        let from = buf.len().saturating_sub(turn_window).max(*started_at_index);
                        let window: Vec<i16> = buf[from..].to_vec();
                        // Not holding the lock through the round trip:
                        // the microphone keeps filling the buffer.
                        drop(buf);
                        let answer =
                            tauri::async_runtime::block_on(ask_turn(app, &base, spec, &window));
                        buf = samples
                            .lock()
                            .unwrap_or_else(|poisoned| poisoned.into_inner());
                        match answer {
                            Ok(Some(finished)) => finished,
                            Ok(None) | Err(_) => {
                                // No model after all, or it failed: the
                                // old fixed pause for the rest of this
                                // session, said once.
                                if let Err(reason) = answer {
                                    eprintln!("[voice] Smart Turn off for now: {reason}");
                                }
                                use_turn = false;
                                false
                            }
                        }
                    }
                };
                if !should_cut && !use_turn {
                    // Just switched off above: judge this pause by the old rule.
                    should_cut =
                        pause_step(silence_elapsed, voiced_so_far, speech_elapsed, true, false)
                            == PauseStep::Cut;
                }
                if should_cut {
                    // The same check as before a Smart Turn question: this
                    // clip goes only to a server on this PC.
                    let base = jarvis_base(app);
                    if let Some(why) = wake_audio_refusal(&base) {
                        drop(buf);
                        stop_listening_because(app, why);
                        return VadEnd::Refused;
                    }
                    let clip: Vec<i16> = buf[*started_at_index..buf.len()].to_vec();
                    // How long since speech was last heard, sent as
                    // `waited_ms` (the Smart Turn pause included).
                    let waited = now.duration_since(*last_voiced_at);
                    // Asked about as an interruption and ended before its
                    // clip was sent: what there is goes now, before the
                    // usual wake-word send below.
                    let barge_now = *told
                        && crate::voice_flow::clip_due(
                            speech_elapsed,
                            crate::voice_flow::barge_wanted(*id),
                            *barge_sent,
                            true,
                        );
                    let barge_id = *id;
                    // Reset for the next utterance. Everything captured
                    // during this cut's own send() is preserved - it just
                    // starts the next utterance's buffer, since `buf` here
                    // is truncated, not the live capture stopped.
                    buf.clear();
                    read_to = 0;
                    phase = VadPhase::Silence;
                    drop(buf); // release the lock before the blocking POST

                    let app = app.clone();
                    if barge_now {
                        let verdict = tauri::async_runtime::block_on(
                            crate::voice_flow::post_barge_in(&app, &base, spec, &clip, barge_id),
                        );
                        let _ = app.emit(VOICE_BARGE_VERDICT, verdict);
                    }
                    let heard = tauri::async_runtime::block_on(post_utterance(
                        &app,
                        &base,
                        spec,
                        &clip,
                        "wake_word",
                        Some(waited),
                    ));
                    match heard {
                        Ok(reply) if !reply.available => {
                            // The server cannot do this at all right now
                            // (switched off, no model): the frontend says so
                            // once and turns listening off.
                            let _ = app.emit(VOICE_HEARD, reply);
                        }
                        Ok(reply) if reply.stop => {
                            // "Stop": silence the reply being spoken, and
                            // nothing else - no voice check was needed for
                            // that, and nothing is sent to the chat.
                            let _ = app.emit(VOICE_SPEECH_STARTED, ());
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
        read_to = analysed_to.unwrap_or(buf.len());
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

/// Stops "hey Jarvis" listening from this side - the listener's own thread,
/// or a Settings change - and tells the quickbar why, through the same
/// "not available" `VOICE_HEARD` it already handles by saying the reason
/// once and switching its button off. Does nothing when nothing is
/// listening, so a Settings change with the listener off says nothing.
pub(crate) fn stop_listening_because(app: &AppHandle, why: String) {
    let Some(state) = app.try_state::<AutoListenState>() else {
        return;
    };
    let taken = state
        .0
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .take();
    if let Some(active) = taken {
        let _ = active.stop_tx.send(());
        let _ = app.emit(VOICE_HEARD, HeardReply::unavailable(why));
    }
}

// ---------------------------------------------------------------------------
// Settings -> Voice: what the server says, and the "hey Jarvis" switch
// ---------------------------------------------------------------------------
//
// The same facts the phone's Checks -> "Your voice" and wake-word cards show
// (VoiceModels.kt reads the same JSON): whether each microphone's voice print
// is trained, which voice check is installed, the owner's own "hey Jarvis"
// check, the wake word, the stop word, Smart Turn and the talk button. READ
// here; training stays on the phone for now. The one write is the wake-word
// switch: OFF at once and never held, ON only an approval card.

/// What a backend without `/api/voice/status` (or too old to send the nested
/// shape) is told to do about it. The page shows this sentence, never a
/// status code or a body.
pub(crate) const VOICE_UPDATE: &str = "This PC's Jarvis does not report its voice settings yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// The phone's own words (VoiceTraining.stateLine) for a voice module that
/// did not load: `{"available": false}`.
pub(crate) const VOICE_NOT_RUNNING: &str = "The voice part of Jarvis is not running on your PC.";

/// [`get_voice_status`]'s reading of the server's answer, on its own so it
/// can be tested against `tests/fixtures/voice-status-cases.json` (the real
/// `jarvis_speech.status()` output).
///
/// * 200 with `gate` and `listening` objects - the status itself, as is.
/// * `{"available": false}` with any code - the voice module did not load:
///   `{"available": false, "why": VOICE_NOT_RUNNING}`.
/// * 404, or a 200 without the nested shape (a server from before
///   2026-09-23 sent only flat keys) - `{"available": false, "why":
///   VOICE_UPDATE}`.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn voice_status_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let parsed = serde_json::from_str::<serde_json::Value>(body).ok();
    let not_loaded = parsed
        .as_ref()
        .and_then(|v| v.get("available"))
        .and_then(|a| a.as_bool())
        == Some(false);
    if not_loaded {
        return Ok(serde_json::json!({ "available": false, "why": VOICE_NOT_RUNNING }));
    }
    if (200..300).contains(&status) {
        let nested = parsed.as_ref().is_some_and(|v| {
            v.get("gate").is_some_and(|g| g.is_object())
                && v.get("listening").is_some_and(|l| l.is_object())
        });
        return Ok(if nested {
            parsed.unwrap_or_default()
        } else {
            serde_json::json!({ "available": false, "why": VOICE_UPDATE })
        });
    }
    if status == 404 {
        return Ok(serde_json::json!({ "available": false, "why": VOICE_UPDATE }));
    }
    Err(crate::commands::backend_refusal(status, body))
}

/// [`set_wake_word`]'s reading of the server's answer. 200 is
/// `jarvis_speech.set_wake_enabled()` as is: `{"ok", "enabled", "pending",
/// "message"}`, or `{"ok": false, "error"}` for a refusal (a card already
/// waiting, a tier other than `ask`). Anything else is a sentence.
pub(crate) fn wake_change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| "Jarvis answered, but not in a way this app can read.".to_string());
    }
    if status == 404 {
        return Err(VOICE_UPDATE.to_string());
    }
    Err(crate::commands::backend_refusal(status, body))
}

/// The words for turning ON while the event stream is stale.
pub(crate) const WAKE_ON_HELD: &str = "The connection to Jarvis is catching up, so \"hey Jarvis\" \
     cannot be turned on until it does. Turning it off still works.";

/// What the PC's voice settings are: `GET /api/voice/status`
/// (`jarvis_speech.status()`).
///
/// Settings window only (permissions/surfaces.toml, `settings-surface`). The
/// token goes out in `X-Jarvis-Token` through [`jarvis_headers`], with
/// `X-Jarvis-Client: hud`, like every other call to Jarvis, and is never
/// logged or put in an error.
#[tauri::command]
pub async fn get_voice_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WAKE_CHECK_TIMEOUT))?
        .get(format!("{base}/api/voice/status"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| crate::commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    voice_status_answer(status, &body)
}

/// The PC's "hey Jarvis" switch: `POST /api/voice/wake` with `{"enabled"}`.
///
/// OFF is immediate and is never held, not even on a stale link: it only
/// narrows what listens. It also stops this PC's own "hey Jarvis" listening
/// first, before the request, so the microphone closes even if the server
/// cannot be reached. ON approves nothing: the server raises ONE approval
/// card and answers `pending: true`, and ON is held while the event stream
/// is stale - rule 4, the same one-direction hold as `ensure_wake_ready`,
/// the second card and the big model. Settings window only.
#[tauri::command]
pub async fn set_wake_word(app: AppHandle, enabled: bool) -> Result<serde_json::Value, String> {
    if enabled {
        if app.state::<crate::stream::StreamState>().link().stale {
            return Err(WAKE_ON_HELD.to_string());
        }
    } else {
        stop_listening_because(
            &app,
            "\"Hey Jarvis\" was turned off in Settings, so this PC stopped listening for it."
                .to_string(),
        );
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(WAKE_CHECK_TIMEOUT))?
        .post(format!("{base}/api/voice/wake"))
        .headers(jarvis_headers(&app)?)
        .json(&serde_json::json!({ "enabled": enabled }))
        .send()
        .await
        .map_err(|e| crate::commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    wake_change_answer(status, &body)
}

#[cfg(test)]
mod voice_settings_tests {
    use super::{voice_status_answer, wake_change_answer, VOICE_NOT_RUNNING, VOICE_UPDATE};

    /// The real `jarvis_speech.status()` output, written by
    /// `tools/gen_voice_status_cases.py` - never hand-written here.
    const CASES: &str = include_str!("../../tests/fixtures/voice-status-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("voice-status-cases.json is JSON")
    }

    #[test]
    fn every_real_status_is_passed_on_as_is() {
        let all = cases();
        let named = all["cases"].as_object().expect("cases");
        assert!(named.len() >= 6, "fewer cases than expected");
        for (name, status) in named {
            let body = status.to_string();
            let got = voice_status_answer(200, &body).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, status, "{name} was changed on the way");
        }
    }

    #[test]
    fn an_old_or_missing_voice_part_is_a_sentence() {
        // A server from before 2026-09-23 sent only the flat keys.
        let flat = r#"{"enabled": true, "enrolled": false, "wake_word_enabled": false}"#;
        let got = voice_status_answer(200, flat).expect("not an error");
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], VOICE_UPDATE);
        let gone = voice_status_answer(404, "").expect("not an error");
        assert_eq!(gone["why"], VOICE_UPDATE);
        // The voice module did not load.
        for code in [200, 503] {
            let got = voice_status_answer(code, r#"{"available": false, "error": "ImportError"}"#)
                .expect("not an error");
            assert_eq!(got["why"], VOICE_NOT_RUNNING);
        }
        let odd = voice_status_answer(500, "<html>boom</html>").unwrap_err();
        assert!(odd.contains("500") && !odd.contains("boom"), "{odd}");
    }

    #[test]
    fn the_wake_switch_answers_are_passed_on() {
        let all = cases();
        for name in ["wake_on_pending", "wake_off"] {
            let body = all["answers"][name].to_string();
            let got = wake_change_answer(200, &body).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(got, all["answers"][name], "{name}");
        }
        let busy =
            r#"{"ok": false, "pending": true, "error": "a card to turn it on is already waiting"}"#;
        assert_eq!(wake_change_answer(200, busy).expect("200")["ok"], false);
        assert_eq!(wake_change_answer(404, "").unwrap_err(), VOICE_UPDATE);
        let said = wake_change_answer(403, r#"{"error": "origin not allowed"}"#).unwrap_err();
        assert_eq!(said, "Origin not allowed");
    }
}

#[cfg(test)]
mod heard_tests {
    use super::{HeardRaw, HeardReply};

    fn reply(body: &str) -> serde_json::Value {
        let raw: HeardRaw = serde_json::from_str(body).expect("an utterance reply");
        serde_json::to_value(HeardReply::from(raw)).expect("serialisable")
    }

    /// Decision 13: `sensitive_aloud` reaches the page as `sensitiveAloud`,
    /// and an older PC that does not send it reads as `false` - the
    /// on-screen answer, never the looser one.
    #[test]
    fn sensitive_aloud_is_passed_on_and_missing_is_false() {
        let said = reply(
            r#"{"is_owner": true, "text": "what is my PIN", "memory_aloud": true,
                "sensitive_aloud": true}"#,
        );
        assert_eq!(said["sensitiveAloud"], true);
        assert_eq!(said["memoryAloud"], true);
        let older = reply(r#"{"is_owner": true, "text": "hello", "memory_aloud": true}"#);
        assert_eq!(older["sensitiveAloud"], false);
        let off = serde_json::to_value(HeardReply::unavailable("no".into())).unwrap();
        assert_eq!(off["sensitiveAloud"], false);
    }
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
    fn wake_audio_goes_only_to_this_pc() {
        // Checked before every clip and every turn check (run_vad_loop), not
        // only at start: a base changed to another machine mid-listen must
        // be refused the moment the next clip is ready.
        for ok in [
            "http://127.0.0.1:4719",
            "http://localhost:4719",
            "http://[::1]:4719",
        ] {
            assert_eq!(wake_audio_refusal(ok), None, "{ok}");
        }
        for no in [
            "http://100.64.0.7:4719",
            "http://192.168.1.20:4719",
            "https://jarvis.example.com",
            "http://127.0.0.1.example.com:4719",
            "",
        ] {
            let why = wake_audio_refusal(no).expect(no);
            assert!(
                why.contains("only works with the Jarvis server on this PC"),
                "{why}"
            );
        }
        // The refusal reaches the quickbar as "not available", which it
        // already turns into "say why, switch the button off".
        let reply = HeardReply::unavailable("why".to_string());
        assert!(!reply.available);
        assert_eq!(reply.reason, "why");
        assert!(!reply.wake_heard && !reply.is_owner && reply.text.is_empty());
    }

    /// T9: the echo-cancelled microphone's thread failing is seen by the
    /// listener, not ignored while it listens to nothing.
    #[test]
    fn a_dead_echo_cancelled_microphone_is_noticed() {
        assert_eq!(mic_died(None), None, "the ordinary path has no such thread");
        let (tx, rx) = mpsc::channel::<String>();
        assert_eq!(mic_died(Some(&rx)), None, "alive and quiet");
        tx.send("the microphone stopped: device invalidated".to_string())
            .unwrap();
        assert_eq!(
            mic_died(Some(&rx)).as_deref(),
            Some("the microphone stopped: device invalidated")
        );
        drop(tx);
        assert!(
            mic_died(Some(&rx)).is_some(),
            "its thread ended without a word"
        );
    }

    fn spec(channels: u16, sample_rate: u32) -> hound::WavSpec {
        hound::WavSpec {
            channels,
            sample_rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        }
    }

    /// T13 (audit 3): the microphone's own format went to the server - at
    /// 48 kHz stereo the body passed 4 MiB after about 22 seconds.
    #[test]
    fn push_to_talk_is_sent_as_16k_mono() {
        // 22 s of 48 kHz stereo: 8.4 MB as captured.
        let raw = vec![1000i16; 48_000 * 2 * 22];
        assert!(encode_wav(spec(2, 48_000), &raw).unwrap().len() > 4 * 1024 * 1024);
        let (out_spec, out) = to_server_format(spec(2, 48_000), &raw);
        assert_eq!((out_spec.channels, out_spec.sample_rate), (1, 16_000));
        assert_eq!(out.len(), 16_000 * 22);
        assert!(
            out.iter().all(|&s| s == 1000),
            "a steady level stays that level"
        );
        let wav = server_wav(spec(2, 48_000), &raw).unwrap();
        assert!(wav.len() < 1024 * 1024, "{} bytes", wav.len());
        // Two minutes, the most push-to-talk sends, fits under 4 MiB.
        let most = (MAX_PUSH_TO_TALK.as_secs() as usize) * 16_000 * 2 + 44;
        assert!(most < 4 * 1024 * 1024);
    }

    #[test]
    fn channels_are_averaged_and_odd_rates_land_on_16k() {
        // Left and right opposite: the average is silence.
        let lr: Vec<i16> = (0..4_800).flat_map(|_| [8000i16, -8000]).collect();
        let (_, out) = to_server_format(spec(2, 48_000), &lr);
        assert_eq!(out.len(), 1_600);
        assert!(out.iter().all(|&s| s == 0));
        // 44.1 kHz: one second is 16 000 samples.
        let (_, out) = to_server_format(spec(1, 44_100), &vec![-300i16; 44_100]);
        assert_eq!(out.len(), 16_000);
        assert!(out.iter().all(|&s| s == -300));
        // Already 16 kHz mono: unchanged, sample for sample.
        let same: Vec<i16> = (0..1_000).map(|i| (i * 7 % 2000 - 1000) as i16).collect();
        assert_eq!(to_server_format(spec(1, 16_000), &same).1, same);
        // 8 kHz: twice as many samples, the in-between ones between.
        let (_, up) = to_server_format(spec(1, 8_000), &[0, 100, 200]);
        assert_eq!(up, vec![0, 50, 100, 150, 200, 200]);
    }

    #[test]
    fn a_voice_band_tone_survives_and_a_too_high_one_does_not_fold_back_loud() {
        let tone = |hz: f64, rate: u32| -> Vec<i16> {
            (0..rate)
                .map(|n| {
                    (10_000.0 * (2.0 * std::f64::consts::PI * hz * n as f64 / rate as f64).sin())
                        as i16
                })
                .collect()
        };
        let peak = |v: &[i16]| v.iter().map(|s| i32::from(*s).abs()).max().unwrap_or(0);
        // 1 kHz, squarely in speech: kept at nearly full level.
        let (_, speech) = to_server_format(spec(1, 48_000), &tone(1_000.0, 48_000));
        assert!(peak(&speech) > 9_500, "{}", peak(&speech));
        // 16 kHz is silent after averaging three samples of it: it must not
        // come back as a loud false tone in the speech band.
        let (_, high) = to_server_format(spec(1, 48_000), &tone(16_000.0, 48_000));
        assert!(peak(&high) < 500, "{}", peak(&high));
    }

    #[test]
    fn a_clip_length_is_its_duration() {
        assert_eq!(
            clip_length(spec(2, 48_000), &vec![0i16; 48_000 * 2 * 3]),
            Duration::from_secs(3)
        );
        assert_eq!(
            clip_length(spec(1, 16_000), &vec![0i16; 8_000]),
            Duration::from_millis(500)
        );
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

    fn ms(n: u64) -> Duration {
        Duration::from_millis(n)
    }

    #[test]
    fn without_smart_turn_the_old_hangover_holds() {
        // 1.5 s of voice, then a pause: cut only once the pause is 900 ms.
        let step = |silence| pause_step(silence, ms(1500), ms(1500) + silence, false, false);
        assert_eq!(step(ms(300)), PauseStep::Listen);
        assert_eq!(step(ms(899)), PauseStep::Listen);
        assert_eq!(step(ms(900)), PauseStep::Cut);
        assert_eq!(
            pause_step(ms(0), ms(2000), VAD_MAX_UTTERANCE, false, false),
            PauseStep::Cut
        );
    }

    /// T12 (audit 3): the minimum-speech rule counted ELAPSED time, which
    /// includes the pause - so when the 900 ms pause ended, a 100 ms cough
    /// had "lasted" a whole second and was sent. The old test,
    /// `pause_step(ms(900), ms(100))`, described a state the loop could
    /// never reach (900 ms of silence inside 100 ms of utterance). These are
    /// the states it does reach.
    #[test]
    fn a_cough_is_dropped_however_long_the_pause_after_it() {
        // 100 ms of voice, then silence: 100 ms voiced, elapsed = 100 + pause.
        let cough = |silence| pause_step(silence, ms(100), ms(100) + silence, false, false);
        assert_eq!(
            cough(ms(300)),
            PauseStep::Listen,
            "more voice may still come"
        );
        assert_eq!(cough(ms(899)), PauseStep::Listen);
        assert_eq!(cough(ms(900)), PauseStep::Discard, "a cough was sent");
        assert_eq!(cough(ms(3000)), PauseStep::Discard);
        // With Smart Turn it is not asked about either - just dropped.
        let cough_turn = |silence| pause_step(silence, ms(100), ms(100) + silence, false, true);
        assert_eq!(
            cough_turn(ms(200)),
            PauseStep::Listen,
            "a cough was asked about"
        );
        assert_eq!(cough_turn(ms(900)), PauseStep::Discard);
        // The threshold is voiced time: 250 ms of it is an utterance.
        assert_eq!(
            pause_step(ms(900), ms(250), ms(1150), false, false),
            PauseStep::Cut
        );
        assert_eq!(
            pause_step(ms(900), ms(249), ms(1149), false, false),
            PauseStep::Discard
        );
    }

    #[test]
    fn with_smart_turn_a_short_pause_is_asked_about_once() {
        let voiced = ms(1800);
        assert_eq!(
            pause_step(ms(100), voiced, ms(2000), false, true),
            PauseStep::Listen
        );
        assert_eq!(
            pause_step(ms(200), voiced, ms(2000), false, true),
            PauseStep::Ask
        );
        // Asked already, answered "not finished": the old 900 ms no longer
        // cuts it...
        assert_eq!(
            pause_step(ms(900), voiced, ms(2700), true, true),
            PauseStep::Listen
        );
        // ...the long pause does, whatever the model said.
        assert_eq!(
            pause_step(TURN_MAX_PAUSE, voiced, ms(4000), true, true),
            PauseStep::Cut
        );
        assert_eq!(
            pause_step(ms(0), voiced, VAD_MAX_UTTERANCE, false, true),
            PauseStep::Cut
        );
    }

    #[test]
    fn smart_turn_is_used_only_when_the_server_says_both() {
        assert!(turn_usable(
            &json!({"turn": {"enabled": true, "available": true}})
        ));
        assert!(!turn_usable(
            &json!({"turn": {"enabled": false, "available": true}})
        ));
        assert!(!turn_usable(
            &json!({"turn": {"enabled": true, "available": false}})
        ));
        assert!(!turn_usable(&json!({"wake": {}})));
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
