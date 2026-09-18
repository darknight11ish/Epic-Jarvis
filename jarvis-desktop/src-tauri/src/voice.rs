//! Real microphone capture and the voice round trip: push-to-talk in, a
//! spoken reply out.
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
//! WHY THIS DOES NOT TOUCH THE HUD WINDOW
//! `jarvis_hud.html` is vendored byte-identical from the backend folder and
//! is granted NO app commands at all - `capabilities/hud.json` says so on
//! purpose, so a future drop of that file can never arrive already holding a
//! permission nobody audited it for. These commands are granted to the
//! quickbar instead (see `permissions/surfaces.toml`'s `voice` set) - the
//! window that already streams chat and already has a real, audited IPC
//! surface.
//!
//! PUSH-TO-TALK, NOT AUTOMATIC LISTENING
//! There is no voice-activity-detection anywhere in this codebase yet
//! (confirmed by reading `backend/jarvis_speech.py` directly - it has
//! speech-to-text and text-to-speech, nothing that decides when speech
//! starts or stops on its own). Automatic listening needs that piece built
//! first; recording only while a key or button is held down does not, and
//! is the honest v1.
//!
//! WHAT "STOP" ACTUALLY DOES
//! `cpal::Stream` is not `Send` on every platform (it wraps native audio-API
//! handles), so it cannot live in ordinary Tauri-managed state shared across
//! async tasks. It - and the host/device it came from - live on one
//! dedicated thread for the capture's whole lifetime; `stop_voice_capture`
//! signals that thread to drop the stream and joins it before reading back
//! whatever was recorded, so nothing is ever read mid-write.
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
//! themselves, not JSON. `source` defaults to exactly `"push_to_talk"`,
//! which is also this file's own default. `say`'s `text` argument, and
//! whether it arrives as a JSON body or something else, is the one part of
//! this contract genuinely unconfirmed - built here as `{"text": ...}` to
//! match how every other structured-input route in this backend already
//! works (`/api/chat`, the wake-toggle route's `body.get("enabled")`), but
//! worth checking against the real file before trusting it blind.

use std::io::Cursor;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, State};

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers};

/// Total round-trip budget for one utterance: speaker verification plus a
/// whole-clip transcription is not instant, but it is also not a chat
/// completion - thirty seconds is generous without being indefinite.
const UTTERANCE_TIMEOUT: Duration = Duration::from_secs(30);
/// Synthesising a reply is comparable work in the other direction.
const SAY_TIMEOUT: Duration = Duration::from_secs(30);
/// How long `start_voice_capture` waits to hear back from the capture
/// thread before giving up and reporting the microphone as unreachable,
/// rather than returning success for a stream that never actually opened.
const STREAM_READY_TIMEOUT: Duration = Duration::from_secs(3);

// ---------------------------------------------------------------------------
// State - one capture at a time, owned by its own thread
// ---------------------------------------------------------------------------

/// The one recording in progress, if any. A second `start_voice_capture`
/// while this is `Some` is refused rather than silently replacing it - two
/// concurrent recordings from one push-to-talk control should not be
/// reachable, and if it ever is, that is a bug to see, not paper over.
#[derive(Default)]
pub struct VoiceCaptureState(Mutex<Option<ActiveCapture>>);

struct ActiveCapture {
    stop_tx: mpsc::Sender<()>,
    samples: Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    join: JoinHandle<()>,
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
        }
    }
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------

/// Opens the default microphone and starts buffering. Sends nothing
/// anywhere - the clip is only posted once `stop_voice_capture` is called.
#[tauri::command]
pub fn start_voice_capture(state: State<VoiceCaptureState>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(poisoned)?;
    if guard.is_some() {
        return Err("already recording".to_string());
    }

    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    let thread_samples = Arc::clone(&samples);
    let (ready_tx, ready_rx) = mpsc::channel::<Result<hound::WavSpec, String>>();
    let (stop_tx, stop_rx) = mpsc::channel::<()>();

    // `cpal::Stream` is not `Send`, so the host, the device and the stream
    // all have to be built AND live out here, on this one thread - moving
    // any of them across a channel back to the caller is not an option.
    // `stream` is a plain local for the rest of this closure (not returned
    // from a nested one), so it stays alive across the `stop_rx.recv()`
    // block below and only drops - stopping capture - when this whole
    // thread function returns.
    let join = std::thread::spawn(move || {
        let host = cpal::default_host();
        let device = match host.default_input_device() {
            Some(d) => d,
            None => {
                let _ = ready_tx.send(Err("no microphone was found".to_string()));
                return;
            }
        };
        let config = match device.default_input_config() {
            Ok(c) => c,
            Err(e) => {
                let _ = ready_tx.send(Err(format!("could not read the microphone's format: {e}")));
                return;
            }
        };
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
            let _ = ready_tx.send(Err(format!(
                "this microphone's sample format ({sample_format:?}) is not one this app reads"
            )));
            return;
        }
        let stream_config: cpal::StreamConfig = config.config();
        let err_fn = |err: cpal::StreamError| eprintln!("[voice] input stream error: {err}");
        let stream_result = match sample_format {
            cpal::SampleFormat::I16 => device.build_input_stream(
                &stream_config,
                move |data: &[i16], _: &cpal::InputCallbackInfo| {
                    if let Ok(mut buf) = thread_samples.lock() {
                        buf.extend_from_slice(data);
                    }
                },
                err_fn,
                None,
            ),
            cpal::SampleFormat::U16 => device.build_input_stream(
                &stream_config,
                move |data: &[u16], _: &cpal::InputCallbackInfo| {
                    if let Ok(mut buf) = thread_samples.lock() {
                        // u16 PCM is centred on 32768, not 0 - shift before
                        // narrowing, the same conversion `cpal::Sample`'s own
                        // i16 impl documents.
                        buf.extend(data.iter().map(|&s| (s as i32 - 32_768) as i16));
                    }
                },
                err_fn,
                None,
            ),
            cpal::SampleFormat::F32 => device.build_input_stream(
                &stream_config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    if let Ok(mut buf) = thread_samples.lock() {
                        buf.extend(
                            data.iter()
                                .map(|&s| (s.clamp(-1.0, 1.0) * i16::MAX as f32) as i16),
                        );
                    }
                },
                err_fn,
                None,
            ),
            // Guarded above - every other variant already returned.
            _ => unreachable!("sample_format was checked to be I16, U16 or F32 above"),
        };
        let stream = match stream_result {
            Ok(s) => s,
            Err(e) => {
                let _ = ready_tx.send(Err(format!("could not open the microphone: {e}")));
                return;
            }
        };
        if let Err(e) = stream.play() {
            let _ = ready_tx.send(Err(format!("could not start the microphone: {e}")));
            return;
        }
        // Reported success to the caller only now that the stream is
        // genuinely open and playing - `start_voice_capture` never returns
        // Ok for a microphone that never actually started.
        if ready_tx.send(Ok(spec)).is_err() {
            return; // the caller already gave up waiting
        }
        let _ = stop_rx.recv();
        // `stream` (and `device`, `host`) drop here, stopping capture.
    });

    match ready_rx.recv_timeout(STREAM_READY_TIMEOUT) {
        Ok(Ok(spec)) => {
            *guard = Some(ActiveCapture {
                stop_tx,
                samples,
                spec,
                join,
            });
            Ok(())
        }
        Ok(Err(reason)) => {
            let _ = join.join();
            Err(reason)
        }
        Err(_) => {
            // The thread is still doing *something* - drop `stop_tx` so it
            // is not left recv()-ing forever if it does eventually open.
            drop(stop_tx);
            Err("the microphone did not respond in time".to_string())
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

    if raw_samples.is_empty() {
        return Err("nothing was recorded - the microphone produced no audio".to_string());
    }

    let mut cursor = Cursor::new(Vec::new());
    {
        let mut writer = hound::WavWriter::new(&mut cursor, spec)
            .map_err(|e| format!("could not start encoding the recording: {e}"))?;
        for sample in &raw_samples {
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
            "{}/api/voice/utterance?source=push_to_talk",
            jarvis_base(&app)
        ))
        .headers(jarvis_headers(&app)?)
        .header("Content-Type", "audio/wav")
        .body(wav_bytes)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("could not reach the Jarvis server at {}", jarvis_base(&app))
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
