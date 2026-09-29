//! Settings -> Voice, the parts that record and change things: training
//! the owner's voice on this PC, the strictness and private-answer
//! settings, the guided "how often would I have to repeat myself?" test,
//! and custom voices (docs/JARVIS-API.md sections 15 and 16).
//!
//! WHERE THE AUDIO IS. Recorded here, through the same microphone code as
//! push-to-talk (`voice.rs`: `spawn_capture_thread`, one channel, 16 kHz -
//! what the desktop already sends), and HELD HERE, in this process's
//! memory, under a slot name the page chose ("t2-4": round 2, sentence 5;
//! "m7": the guided test's eighth sentence; "voice": a recording for a
//! custom voice, kept at 24 kHz). The page never holds a recording: it gets
//! back a length and a loudness, and later names the slots to send. A held
//! recording is dropped when it is sent and the PC answers yes, when the
//! page discards it (Cancel, or the window closing), and after
//! [`HELD_FOR`] whatever happens - never written to disk, never logged.
//! Sent only to the Jarvis server this app is set to (`jarvis_base`), with
//! `X-Jarvis-Client: hud` and the token through [`jarvis_headers`], like
//! every other request.
//!
//! NOTHING HERE TRANSCRIBES ANYTHING (CLAUDE.md: a client must not do
//! speech-to-text). The words of a training sentence are never sent; the
//! words of a custom voice are the sentence the page showed, or what the
//! owner typed.
//!
//! THE MICROPHONE IS SHARED. A Settings recording refuses while the Jarvis
//! bar's talk button is recording, and push-to-talk and "hey Jarvis"
//! listening refuse while one runs ([`MIC_IN_SETTINGS`]). "Hey Jarvis"
//! listening is stopped when a Settings recording starts - with a sentence
//! in the Jarvis bar saying so - because half the training sentences start
//! with "hey Jarvis" and must not be taken as commands.
//!
//! WHAT IS HELD ON A STALE LINK (rule 4). Only what raises an approval card
//! or loosens something: finishing a training (the card), the one-shot
//! training an older PC takes, loosening the voice check or the privacy
//! setting, adding a voice, switching to a custom voice, turning the
//! better voice on, and the stricter bar the "someone else" check suggests
//! (its card). Tightening, cancelling, going back to the built-in voice,
//! deleting a voice, turning the better voice off, sending a round that is
//! only held in memory, the guided test and the "someone else" check itself
//! (neither changes anything) always go through: each only narrows what
//! Jarvis does, or changes nothing at all.
//!
//! Settings window only (permissions/surfaces.toml, `settings-surface`).

use std::collections::HashMap;
use std::ops::Range;
use std::sync::{mpsc, Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use serde::Serialize;
use serde_json::{json, Value};
use tauri::{AppHandle, Manager, State};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};
use crate::voice::{
    clip_length, encode_wav, poisoned, rms, spawn_capture_thread, stop_listening_because,
    to_format, wait_for_ready, VoiceCaptureState,
};

/// Which microphone these recordings train, as the server names it.
const MIC_DESKTOP: &str = "desktop";
/// The rate every training and test clip is sent at (the server refuses
/// any other: `jarvis_voice_enroll.SAMPLE_RATE`).
const TRAINING_RATE: u32 = 16_000;
/// The rate a custom voice's recording is kept at (`jarvis_voices.SAMPLE_RATE`).
const VOICE_RATE: u32 = 24_000;
/// The longest single recording kept. The server takes at most 10 s per
/// training clip and 10 s of speech per voice; this only stops a recording
/// nobody stopped from filling memory.
const MAX_SAMPLE: Duration = Duration::from_secs(30);
/// How long a recording is held if nothing sends or discards it.
const HELD_FOR: Duration = Duration::from_secs(30 * 60);
/// The most recordings held at once: three rounds of twelve, the guided
/// test's twenty and one voice fit.
const MAX_HELD: usize = 64;
/// Each guided-test request stays under the server's 80 s (and 20 clips).
const MEASURE_PART_SECONDS: f64 = 78.0;
const MEASURE_PART_CLIPS: usize = 20;
/// Training and the guided test run the voice-ID models on the PC.
const ENROLL_TIMEOUT: Duration = Duration::from_secs(120);
/// Adding a voice checks it against the owner's voice prints first.
const VOICES_TIMEOUT: Duration = Duration::from_secs(60);
/// `jarvis_voices.MAX_CLIP_BYTES`: the largest WAV the server reads.
const VOICE_CLIP_MAX_BYTES: usize = 2_900_000;

/// What push-to-talk and "hey Jarvis" listening say while Settings records.
/// Settings' recorder took the microphone while Jarvis Live was on.
pub(crate) const LIVE_ENDED_FOR_SETTINGS: &str = "Jarvis Live ended because Settings is recording.";
pub(crate) const MIC_IN_SETTINGS: &str =
    "Settings is recording with the microphone. Finish or cancel that first.";
/// What a backend without the training route, or too old for it, is told.
pub(crate) const TRAINING_UPDATE: &str =
    "This PC's Jarvis cannot train a voice yet. Update the backend by running \
     apply-patches.ps1, then open this again.";
/// What a backend without `jarvis_voices.py` is told.
pub(crate) const VOICES_UPDATE: &str =
    "This PC's Jarvis does not have custom voices yet. Update the backend by running \
     apply-patches.ps1, then open this again.";
/// "Try it" on a PC whose backend has no route for it yet. The phone says
/// the same (CustomVoices.kt `TRY_UPDATE`; custom-voices.js too).
pub(crate) const TRY_UPDATE: &str =
    "Your PC cannot play an animal's voice yet. Run the patch script on the PC first.";
/// "Try it" while the talk button records: it would be recorded with the
/// question. The phone says the same (CustomVoices.kt `TRY_BUSY`).
pub(crate) const TRY_BUSY: &str = "Jarvis is busy talking or listening. Try it again in a moment.";
/// Asking for a card, or loosening, while the event stream is stale.
pub(crate) const HELD_STALE: &str =
    "The connection to Jarvis is catching up, so this cannot be sent until it does. \
     Anything that only makes Jarvis stricter still works.";
/// A slot the page named is not held (sent already, discarded, too old).
pub(crate) const NOT_HELD: &str =
    "A recording is no longer held on this PC (it was sent, cancelled or over 30 \
     minutes old). Record it again.";

// ---------------------------------------------------------------------------
// The recordings
// ---------------------------------------------------------------------------

/// The Settings recording in progress, if any, and the recordings held.
#[derive(Default)]
pub struct SampleState {
    active: Mutex<Option<ActiveSample>>,
    held: Mutex<HashMap<String, HeldClip>>,
}

struct ActiveSample {
    slot: String,
    stop_tx: mpsc::Sender<()>,
    samples: Arc<Mutex<Vec<i16>>>,
    spec: hound::WavSpec,
    join: JoinHandle<()>,
}

struct HeldClip {
    /// One complete WAV, mono, at [`slot_rate`].
    wav: Vec<u8>,
    seconds: f64,
    at: Instant,
}

impl SampleState {
    /// A Settings recording holds the microphone right now.
    pub(crate) fn recording(&self) -> bool {
        self.active
            .lock()
            .map(|g| g.is_some())
            .unwrap_or_else(|p| p.into_inner().is_some())
    }

    fn held(&self) -> std::sync::MutexGuard<'_, HashMap<String, HeldClip>> {
        let mut g = self.held.lock().unwrap_or_else(|p| p.into_inner());
        g.retain(|_, c| c.at.elapsed() < HELD_FOR);
        g
    }
}

/// What a finished recording came to - never the audio itself.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct SampleTaken {
    pub slot: String,
    /// How long the clip is, as sent (the server's own "seconds").
    pub seconds: f64,
    /// Its loudest sample, 0..1 - near 0 is a microphone that heard nothing.
    pub peak: f64,
}

/// A slot name the page may use: `voice`, `t<round 1-3>-<sentence 0-11>`,
/// `m<sentence 0-19>`, or `o<sentence 0-4>` (someone else's voice, for the
/// "someone else" check). Anything else is refused, so a page cannot fill
/// memory with names of its own.
pub(crate) fn valid_slot(slot: &str) -> Result<&str, String> {
    let number = |s: &str, below: u32| {
        !s.is_empty()
            && s.len() <= 2
            && !(s.len() == 2 && s.starts_with('0'))
            && s.bytes().all(|b| b.is_ascii_digit())
            && s.parse::<u32>().is_ok_and(|n| n < below)
    };
    let ok = slot == "voice"
        || slot.strip_prefix('m').is_some_and(|n| number(n, 20))
        || slot.strip_prefix('o').is_some_and(|n| number(n, 5))
        || slot.strip_prefix('t').is_some_and(|rest| {
            rest.split_once('-')
                .is_some_and(|(r, n)| matches!(r, "1" | "2" | "3") && number(n, 12))
        });
    if ok {
        Ok(slot)
    } else {
        Err("That is not a recording this page can make.".to_string())
    }
}

/// The rate a slot's recording is kept at.
pub(crate) fn slot_rate(slot: &str) -> u32 {
    if slot == "voice" {
        VOICE_RATE
    } else {
        TRAINING_RATE
    }
}

/// The loudest sample, 0..1.
pub(crate) fn peak(samples: &[i16]) -> f64 {
    samples
        .iter()
        .map(|&s| (f64::from(s) / 32768.0).abs())
        .fold(0.0, f64::max)
}

/// Opens the microphone for one recording under `slot`. Sends nothing.
#[tauri::command]
pub fn start_voice_sample(
    app: AppHandle,
    slot: String,
    state: State<SampleState>,
    talk: State<VoiceCaptureState>,
) -> Result<(), String> {
    let slot = valid_slot(slot.trim())?.to_string();
    // The talk button and "hey Jarvis" listening are asked, and stopped,
    // BEFORE this state's lock is taken, as they ask `recording` before
    // taking theirs: none of the three holds its lock while asking another,
    // so they cannot deadlock.
    if talk.busy() {
        return Err(
            "The Jarvis bar's talk button is using the microphone. Let go of it first.".to_string(),
        );
    }
    if state.recording() {
        return Err("Already recording. Press Stop first.".to_string());
    }
    if app.state::<crate::talk_type::TalkTypeState>().mic_busy() {
        return Err(crate::voice::TALK_TYPE_HAS_MIC.to_string());
    }
    // Jarvis Live has this microphone too (even while paused): recording
    // ends Live, and the owner is told that - not that "hey Jarvis" stopped.
    let why = if crate::voice::LIVE_MODE.load(std::sync::atomic::Ordering::SeqCst) {
        LIVE_ENDED_FOR_SETTINGS
    } else {
        "This PC stopped listening for \"hey Jarvis\" while you record in Settings. Turn \
         it back on here when you are done."
    };
    stop_listening_because(&app, why.to_string());
    let mut guard = state.active.lock().map_err(poisoned)?;
    if guard.is_some() {
        return Err("Already recording. Press Stop first.".to_string());
    }
    let samples: Arc<Mutex<Vec<i16>>> = Arc::new(Mutex::new(Vec::new()));
    let (ready_tx, ready_rx) = mpsc::channel();
    let (stop_tx, stop_rx) = mpsc::channel();
    let join = spawn_capture_thread(
        Arc::clone(&samples),
        ready_tx,
        stop_rx,
        |_samples, _spec, stop_rx| {
            let _ = stop_rx.recv();
        },
    );
    match wait_for_ready(ready_rx, stop_tx.clone()) {
        Ok(spec) => {
            *guard = Some(ActiveSample {
                slot,
                stop_tx,
                samples,
                spec,
                join,
            });
            Ok(())
        }
        Err(reason) => {
            let _ = join.join();
            Err(format!("The microphone could not be opened: {reason}."))
        }
    }
}

/// How loud the last tenth of a second was, 0..1, so the page can show the
/// microphone hearing something. 0 when nothing is recording. A number
/// only: no audio leaves here.
#[tauri::command]
pub fn voice_sample_level(state: State<SampleState>) -> f32 {
    let guard = state.active.lock().unwrap_or_else(|p| p.into_inner());
    let Some(active) = guard.as_ref() else {
        return 0.0;
    };
    let buf = active.samples.lock().unwrap_or_else(|p| p.into_inner());
    let window = (active.spec.sample_rate as usize / 10) * usize::from(active.spec.channels);
    let from = buf.len().saturating_sub(window.max(1));
    (rms(&buf[from..]) * 4.0).min(1.0)
}

/// Stops the microphone and holds the recording under its slot.
#[tauri::command]
pub async fn stop_voice_sample(state: State<'_, SampleState>) -> Result<SampleTaken, String> {
    let ActiveSample {
        slot,
        stop_tx,
        samples,
        spec,
        join,
    } = state
        .active
        .lock()
        .map_err(poisoned)?
        .take()
        .ok_or_else(|| "Nothing is recording.".to_string())?;
    let _ = stop_tx.send(());
    tauri::async_runtime::spawn_blocking(move || join.join())
        .await
        .map_err(|_| "The recording could not be finished.".to_string())?
        .map_err(|_| "The recording could not be finished.".to_string())?;
    let raw = Arc::try_unwrap(samples)
        .map(|m| m.into_inner().unwrap_or_default())
        .unwrap_or_else(|arc| arc.lock().map(|g| g.clone()).unwrap_or_default());
    if raw.is_empty() {
        return Err("The microphone recorded nothing. Check it is plugged in and on.".to_string());
    }
    if clip_length(spec, &raw) > MAX_SAMPLE {
        return Err("That was far too long, so it was not kept. Record it again.".to_string());
    }
    let (out_spec, mono) = to_format(spec, &raw, slot_rate(&slot));
    drop(raw);
    let taken = SampleTaken {
        slot: slot.clone(),
        seconds: (mono.len() as f64 / f64::from(out_spec.sample_rate) * 100.0).round() / 100.0,
        peak: (peak(&mono) * 1000.0).round() / 1000.0,
    };
    let wav = encode_wav(out_spec, &mono)?;
    let mut held = state.held();
    held.insert(
        slot,
        HeldClip {
            wav,
            seconds: taken.seconds,
            at: Instant::now(),
        },
    );
    while held.len() > MAX_HELD {
        let oldest = held
            .iter()
            .min_by_key(|(_, c)| c.at)
            .map(|(k, _)| k.clone());
        match oldest {
            Some(k) => {
                held.remove(&k);
            }
            None => break,
        }
    }
    Ok(taken)
}

/// Stops a recording and keeps nothing of it.
#[tauri::command]
pub fn cancel_voice_sample(state: State<SampleState>) -> Result<(), String> {
    if let Some(active) = state.active.lock().map_err(poisoned)?.take() {
        let _ = active.stop_tx.send(());
    }
    Ok(())
}

/// Drops held recordings: every one, or those whose slot starts with
/// `prefix` ("t" for the training, "m" for the test, "voice").
#[tauri::command]
pub fn discard_voice_samples(state: State<SampleState>, prefix: Option<String>) {
    let mut held = state.held();
    match prefix.as_deref().map(str::trim).filter(|p| !p.is_empty()) {
        Some(p) => held.retain(|k, _| !k.starts_with(p)),
        None => held.clear(),
    }
}

/// The held recordings for `slots`, in that order, as (base64 WAV, seconds).
fn take_held(state: &SampleState, slots: &[String]) -> Result<Vec<(String, f64)>, String> {
    let held = state.held();
    slots
        .iter()
        .map(|s| {
            let s = valid_slot(s.trim())?;
            held.get(s)
                .map(|c| (BASE64.encode(&c.wav), c.seconds))
                .ok_or_else(|| NOT_HELD.to_string())
        })
        .collect()
}

fn forget(state: &SampleState, slots: &[String]) {
    let mut held = state.held();
    for s in slots {
        held.remove(s.trim());
    }
}

// ---------------------------------------------------------------------------
// The answers
// ---------------------------------------------------------------------------

fn parsed_object(body: &str) -> Option<serde_json::Map<String, Value>> {
    match serde_json::from_str::<Value>(body).ok()? {
        Value::Object(m) => Some(m),
        _ => None,
    }
}

/// The answer as the page reads it: the server's JSON object as is, with
/// the HTTP code added as `http` - a 202 (a card is up) and a 200 (held,
/// or done) mean different things, and a 400 or 409 carries the sentence
/// to show (`error`) and what it is about (`refused`, `session`, `round`).
fn with_code(mut m: serde_json::Map<String, Value>, status: u16) -> Value {
    m.insert("http".to_string(), json!(status));
    Value::Object(m)
}

/// `POST /api/voice/enroll`'s answer (`jarvis_voice_enroll.stage()`).
///
/// * a JSON object with `ok` or `error` - passed on with `http` added;
/// * 404 (no such route: an older backend), or 503 `{"available": false}`
///   (`jarvis_voice_enroll.py` missing) - [`TRAINING_UPDATE`];
/// * anything else - a sentence, never the body.
pub(crate) fn enroll_answer(status: u16, body: &str) -> Result<Value, String> {
    let m = parsed_object(body);
    if status == 404
        || (status == 503
            && m.as_ref()
                .and_then(|m| m.get("available"))
                .and_then(Value::as_bool)
                == Some(false))
    {
        return Err(TRAINING_UPDATE.to_string());
    }
    if status == 401 || status == 403 {
        return Err(backend_refusal(status, body));
    }
    match m {
        Some(m) if m.contains_key("ok") || m.contains_key("error") => Ok(with_code(m, status)),
        _ => Err(backend_refusal(status, body)),
    }
}

/// A `POST /api/voice/voices/*` answer (`jarvis_voices.handle_post()`).
/// Like [`enroll_answer`], except that a 404 WITH `ok` in it is the
/// module's own "there is no voice with that id", passed on; a 404 without
/// it is a route this backend does not have.
pub(crate) fn voices_answer(status: u16, body: &str) -> Result<Value, String> {
    let m = parsed_object(body);
    let has_ok = m.as_ref().is_some_and(|m| m.contains_key("ok"));
    let missing = m
        .as_ref()
        .and_then(|m| m.get("available"))
        .and_then(Value::as_bool)
        == Some(false);
    if (status == 404 && !has_ok) || (status == 503 && missing) {
        return Err(VOICES_UPDATE.to_string());
    }
    if status == 401 || status == 403 {
        return Err(backend_refusal(status, body));
    }
    match m {
        Some(m) if m.contains_key("ok") || m.contains_key("error") => Ok(with_code(m, status)),
        _ => Err(backend_refusal(status, body)),
    }
}

/// `GET /api/voice/voices`'s answer: `status()` as is, or
/// `{"available": false, "why": VOICES_UPDATE}` from a backend without it.
pub(crate) fn voices_status_answer(status: u16, body: &str) -> Result<Value, String> {
    let m = parsed_object(body);
    let missing = m
        .as_ref()
        .and_then(|m| m.get("available"))
        .and_then(Value::as_bool)
        == Some(false);
    if status == 404 || (status == 503 && missing) {
        return Ok(json!({ "available": false, "why": VOICES_UPDATE }));
    }
    if (200..300).contains(&status) {
        return match m {
            Some(m) if m.get("voices").is_some_and(Value::is_array) => Ok(Value::Object(m)),
            _ => Ok(json!({ "available": false, "why": VOICES_UPDATE })),
        };
    }
    Err(backend_refusal(status, body))
}

fn is_2xx(v: &Value) -> bool {
    v.get("http")
        .and_then(Value::as_u64)
        .is_some_and(|c| (200..300).contains(&c))
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: &Value,
    timeout: Duration,
) -> Result<(u16, String), String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(timeout))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    Ok((status, text))
}

// ---------------------------------------------------------------------------
// Training, and the guided test
// ---------------------------------------------------------------------------

/// The body for one round (`mode: train`), or - `legacy`, for a PC whose
/// `gate.training.rounds` is not true - the one-shot training every older
/// app sends, which such a PC reads as one round with one card.
pub(crate) fn training_body(
    round: u8,
    clips: &[String],
    add: bool,
    finish: bool,
    legacy: bool,
) -> Value {
    if legacy {
        return json!({ "clips": clips, "mic": MIC_DESKTOP });
    }
    let mut body = json!({ "mode": "train", "round": round, "mic": MIC_DESKTOP, "add": add });
    if !clips.is_empty() {
        body["clips"] = json!(clips);
    }
    if finish {
        body["finish"] = json!(true);
    }
    body
}

/// One round of training from this PC's microphone: `slots` are the held
/// recordings, in order. Without `finish` the PC only holds the round (200,
/// no card); with it, ONE approval card is raised for every held round
/// (202) - and that is held while the event stream is stale.
#[tauri::command]
pub async fn send_voice_training(
    app: AppHandle,
    round: u8,
    slots: Vec<String>,
    add: bool,
    finish: bool,
    legacy: bool,
    state: State<'_, SampleState>,
) -> Result<Value, String> {
    if !(1..=3).contains(&round) {
        return Err("There are three rounds, 1 to 3.".to_string());
    }
    if slots.len() > 12 || (slots.is_empty() && (legacy || !finish)) {
        return Err("Record the sentences first.".to_string());
    }
    if (finish || legacy) && stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let clips: Vec<String> = take_held(&state, &slots)?
        .into_iter()
        .map(|(c, _)| c)
        .collect();
    let body = training_body(round, &clips, add, finish, legacy);
    drop(clips);
    let (status, text) = post(&app, "/api/voice/enroll", &body, ENROLL_TIMEOUT).await?;
    drop(body);
    let answer = enroll_answer(status, &text)?;
    if is_2xx(&answer) {
        forget(&state, &slots);
    }
    Ok(answer)
}

/// Deletes every round the PC holds (`{"mode": "train", "cancel": true}`).
/// Never held: it only throws recordings away.
#[tauri::command]
pub async fn cancel_voice_training(
    app: AppHandle,
    state: State<'_, SampleState>,
) -> Result<Value, String> {
    discard_voice_samples(state, Some("t".to_string()));
    let (status, text) = post(
        &app,
        "/api/voice/enroll",
        &json!({ "mode": "train", "cancel": true }),
        ENROLL_TIMEOUT,
    )
    .await?;
    enroll_answer(status, &text)
}

/// The guided test in requests the server takes: at most 20 clips and
/// [`MEASURE_PART_SECONDS`] each, in order.
pub(crate) fn measure_parts(seconds: &[f64]) -> Vec<Range<usize>> {
    let mut parts = Vec::new();
    let mut start = 0;
    let mut total = 0.0;
    for (i, s) in seconds.iter().enumerate() {
        if i > start && (total + s > MEASURE_PART_SECONDS || i - start >= MEASURE_PART_CLIPS) {
            parts.push(start..i);
            start = i;
            total = 0.0;
        }
        total += s;
    }
    if start < seconds.len() {
        parts.push(start..seconds.len());
    }
    parts
}

/// The guided test's answers, added up the way docs/JARVIS-API.md §16 says
/// ("send two halves if the sentences are long, and add the counts up").
pub(crate) fn combine_measures(parts: &[Value]) -> Value {
    let n = |v: &Value, a: &str, b: &str| {
        v.get(a)
            .and_then(|x| x.get(b))
            .and_then(Value::as_u64)
            .unwrap_or(0)
    };
    let mut out = json!({ "ok": true, "http": 200, "parts": parts.len() });
    let clips: u64 = parts
        .iter()
        .map(|p| p.get("clips").and_then(Value::as_u64).unwrap_or(0))
        .sum();
    out["clips"] = json!(clips);
    out["strong_model"] = json!(
        !parts.is_empty()
            && parts
                .iter()
                .all(|p| p.get("strong_model").and_then(Value::as_bool) == Some(true))
    );
    for s in ["very_strict", "balanced"] {
        let passed: u64 = parts.iter().map(|p| n(p, s, "passed")).sum();
        let of: u64 = parts.iter().map(|p| n(p, s, "of")).sum();
        let short: u64 = parts.iter().map(|p| n(p, s, "too_short")).sum();
        let rate = if of > 0 {
            ((1.0 - passed as f64 / of as f64) * 1000.0).round() / 1000.0
        } else {
            0.0
        };
        out[s] = json!({ "passed": passed, "of": of, "too_short": short, "repeat_rate": rate });
    }
    out
}

/// The guided test (`mode: measure`): the owner's own sentences, each judged
/// at both settings. No card, nothing changed, so never held.
#[tauri::command]
pub async fn measure_voice(
    app: AppHandle,
    slots: Vec<String>,
    state: State<'_, SampleState>,
) -> Result<Value, String> {
    if slots.is_empty() || slots.len() > 20 {
        return Err("Record the sentences first.".to_string());
    }
    let held = take_held(&state, &slots)?;
    let seconds: Vec<f64> = held.iter().map(|(_, s)| *s).collect();
    let mut answers = Vec::new();
    for part in measure_parts(&seconds) {
        let clips: Vec<&String> = held[part].iter().map(|(c, _)| c).collect();
        let body = json!({ "mode": "measure", "mic": MIC_DESKTOP, "clips": clips });
        let (status, text) = post(&app, "/api/voice/enroll", &body, ENROLL_TIMEOUT).await?;
        let answer = enroll_answer(status, &text)?;
        if !is_2xx(&answer) || answer.get("ok").and_then(Value::as_bool) != Some(true) {
            return Ok(answer);
        }
        answers.push(answer);
    }
    drop(held);
    forget(&state, &slots);
    Ok(combine_measures(&answers))
}

/// A setting and value the server knows, and whether choosing it LOOSENS
/// the check (which raises a card, and is held on a stale link).
pub(crate) fn voice_setting(
    setting: &str,
    value: &str,
) -> Result<(&'static str, &'static str, bool), String> {
    match (setting, value) {
        ("strictness", "very_strict") => Ok(("strictness", "very_strict", false)),
        ("strictness", "balanced") => Ok(("strictness", "balanced", true)),
        ("privacy", "private_on_screen") => Ok(("privacy", "private_on_screen", false)),
        ("privacy", "voice_is_enough") => Ok(("privacy", "voice_is_enough", true)),
        ("memory", "memory_on_screen") => Ok(("memory", "memory_on_screen", false)),
        ("memory", "memory_aloud") => Ok(("memory", "memory_aloud", true)),
        // Decision 13: answers that use a sensitive saved fact. Keeping them
        // on screen is the default and applies at once; reading them aloud
        // raises the voice card and is held on a stale link.
        ("sensitive_memory", "sensitive_on_screen") => {
            Ok(("sensitive_memory", "sensitive_on_screen", false))
        }
        ("sensitive_memory", "sensitive_aloud") => {
            Ok(("sensitive_memory", "sensitive_aloud", true))
        }
        // How far "Hey Jarvis" is trusted (the owner's decision,
        // 2026-09-24). "Only trust the talk button" is the stricter choice
        // and applies at once; going back to "same as the talk button" (the
        // default) raises the voice card and is held on a stale link.
        ("hands_free", "button_only") => Ok(("hands_free", "button_only", false)),
        ("hands_free", "same_as_button") => Ok(("hands_free", "same_as_button", true)),
        // Answers about the screen after "Hey Jarvis", under "Only trust the
        // talk button" (the owner's decision, 2026-09-28). Keeping them on
        // screen is the default and applies at once; reading them aloud
        // raises the voice card and is held on a stale link.
        ("hands_free_screen", "screen_on_screen") => {
            Ok(("hands_free_screen", "screen_on_screen", false))
        }
        ("hands_free_screen", "screen_aloud") => Ok(("hands_free_screen", "screen_aloud", true)),
        // Jarvis Live under "Only trust the talk button" (the owner's
        // answers, 2026-09-28): three choices, strictest last. The strictest
        // is never a loosening; the other two MAY be (from a stricter one) -
        // `live_trust_loosens` decides when the choice now is known.
        ("hands_free_live", "live_like_hey_jarvis") => {
            Ok(("hands_free_live", "live_like_hey_jarvis", false))
        }
        ("hands_free_live", "live_button_start_only") => {
            Ok(("hands_free_live", "live_button_start_only", true))
        }
        ("hands_free_live", "live_trust_fully") => {
            Ok(("hands_free_live", "live_trust_fully", true))
        }
        // When App lock ends Jarvis Live on this PC (the owner's decision,
        // 2026-09-28): when App lock would ask again (the default, applies
        // at once), or only when Windows itself locks (the voice card, held
        // on a stale link).
        ("live_end", "live_end_app_lock") => Ok(("live_end", "live_end_app_lock", false)),
        ("live_end", "live_end_windows_lock") => Ok(("live_end", "live_end_windows_lock", true)),
        // Talk-to-type on the PC (the owner's decision, 2026-09-27): OFF at
        // once; ON raises the voice card and is held on a stale link.
        ("talk_to_type", "off") => Ok(("talk_to_type", "off", false)),
        ("talk_to_type", "on") => Ok(("talk_to_type", "on", true)),
        // "Better voice" (2026-09-28, docs/JARVIS-API.md section 80). Two
        // "hey Jarvis" detectors that must agree only narrows when Jarvis
        // wakes, so it applies at once; going back to one raises the voice
        // card. The newer, unmeasured voice-ID model raises the card; the
        // measured one applies at once.
        ("wake_confirm", "both") => Ok(("wake_confirm", "both", false)),
        ("wake_confirm", "one") => Ok(("wake_confirm", "one", true)),
        ("voice_id_model", "titanet") => Ok(("voice_id_model", "titanet", false)),
        ("voice_id_model", "resnet221") => Ok(("voice_id_model", "resnet221", true)),
        _ => Err("That is not one of the voice settings.".to_string()),
    }
}

/// The Live trust choices, loosest first (backend jarvis_voice `_ORDER`).
const LIVE_TRUST_ORDER: [&str; 3] = [
    "live_trust_fully",
    "live_button_start_only",
    "live_like_hey_jarvis",
];

/// Whether moving Live's trust from `current` to `value` loosens it. An
/// unknown `current` counts as the strictest, so a looser-looking choice is
/// held on a stale link rather than let through.
pub(crate) fn live_trust_loosens(value: &str, current: Option<&str>) -> bool {
    let rank = |v: &str| LIVE_TRUST_ORDER.iter().position(|c| *c == v);
    match (rank(value), current.and_then(rank)) {
        (Some(v), Some(c)) => v < c,
        (Some(v), None) => v < LIVE_TRUST_ORDER.len() - 1,
        _ => true,
    }
}

/// How strict the voice check is, and whether private answers may be read
/// aloud. Tightening applies at once; loosening raises ONE card and changes
/// nothing itself - and only loosening is held on a stale link.
#[tauri::command]
pub async fn set_voice_setting(
    app: AppHandle,
    setting: String,
    value: String,
    current: Option<String>,
) -> Result<Value, String> {
    let (setting, value, mut loosening) = voice_setting(setting.trim(), value.trim())?;
    if setting == "hands_free_live" {
        loosening = live_trust_loosens(value, current.as_deref().map(str::trim));
    }
    if loosening && stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    if setting == "talk_to_type" {
        // Whatever the PC answers, the next press asks it again rather than
        // trusting an "on" it said a moment ago.
        crate::talk_type::forget_switch(&app);
    }
    let (status, text) = post(
        &app,
        "/api/voice/enroll",
        &json!({ "mode": setting, "value": value }),
        ENROLL_TIMEOUT,
    )
    .await?;
    enroll_answer(status, &text)
}

// ---------------------------------------------------------------------------
// The "someone else" check, and the stricter bar it may suggest
// ---------------------------------------------------------------------------

/// Whether the PC's voice status says it understands `mode: calibrate` and
/// `mode: threshold` (`gate.training.calibrate`). An older PC reads any body
/// with clips in it as a TRAINING - the other person's voice would become a
/// card to make them "the owner" - so nothing is sent unless it is true.
pub(crate) fn calibrate_understood(status: &Value) -> bool {
    status
        .pointer("/gate/training/calibrate")
        .and_then(Value::as_bool)
        == Some(true)
}

/// The body for the threshold card: this PC's microphone's print, the bar
/// rounded to two places (the server's own rounding), and the model the
/// check was scored with when it said (`small` or `strong`).
pub(crate) fn threshold_body(threshold: f64, model: Option<&str>) -> Result<Value, String> {
    if !threshold.is_finite() || !(0.05..=0.9).contains(&threshold) {
        return Err("The setting must be between 0.05 and 0.90.".to_string());
    }
    let mut body = json!({
        "mode": "threshold",
        "mic": MIC_DESKTOP,
        "threshold": (threshold * 100.0).round() / 100.0,
    });
    match model.map(str::trim).unwrap_or("") {
        "" => {}
        m @ ("small" | "strong") => body["model"] = json!(m),
        _ => return Err("That is not one of the voice-ID models.".to_string()),
    }
    Ok(body)
}

/// Said when the PC is too old for the check.
pub(crate) const CHECK_UPDATE: &str =
    "Your PC does not have this check yet. Update the backend by running apply-patches.ps1, \
     then open this again.";

/// The "someone else" check (`mode: calibrate`): another person's sentences,
/// recorded here under `o0`..`o4`, scored on the PC against the owner's
/// print for this microphone and thrown away there. The recordings are
/// dropped here too, whatever the answer. Changes nothing and raises no
/// card, so it is NOT held on a stale link - the phone's rule. It is
/// refused unless the PC says it understands it ([`calibrate_understood`]).
#[tauri::command]
pub async fn check_voice_with_someone_else(
    app: AppHandle,
    slots: Vec<String>,
    state: State<'_, SampleState>,
) -> Result<Value, String> {
    // Only someone else's slots: the owner's own training or test recordings
    // are never sent as "someone else", and never dropped from here.
    if slots.is_empty() || slots.len() > 5 || !slots.iter().all(|s| s.trim().starts_with('o')) {
        return Err("Record their sentences first.".to_string());
    }
    let understood = match crate::voice::get_voice_status(app.clone()).await {
        Ok(status) => calibrate_understood(&status),
        Err(e) => {
            forget(&state, &slots);
            return Err(e);
        }
    };
    if !understood {
        forget(&state, &slots);
        return Err(CHECK_UPDATE.to_string());
    }
    let clips = match take_held(&state, &slots) {
        Ok(held) => held.into_iter().map(|(c, _)| c).collect::<Vec<_>>(),
        Err(e) => {
            forget(&state, &slots);
            return Err(e);
        }
    };
    let body = json!({ "mode": "calibrate", "mic": MIC_DESKTOP, "clips": clips });
    drop(clips);
    let sent = post(&app, "/api/voice/enroll", &body, ENROLL_TIMEOUT).await;
    drop(body);
    // Scored and thrown away on the PC; nothing is kept here either.
    forget(&state, &slots);
    let (status, text) = sent?;
    enroll_answer(status, &text)
}

/// Asks the PC to use a stricter bar for the owner's voice on this PC's
/// microphone (`mode: threshold`): ONE approval card, and the bar changes
/// only once it is approved. Held while the event stream is stale (rule 4),
/// the same as every other card.
#[tauri::command]
pub async fn propose_voice_threshold(
    app: AppHandle,
    threshold: f64,
    model: Option<String>,
) -> Result<Value, String> {
    let body = threshold_body(threshold, model.as_deref())?;
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(&app, "/api/voice/enroll", &body, ENROLL_TIMEOUT).await?;
    enroll_answer(status, &text)
}

// ---------------------------------------------------------------------------
// Custom voices
// ---------------------------------------------------------------------------

/// A voice id the server could have made (`jarvis_voices._ID_RE`), or
/// `builtin`.
pub(crate) fn voice_id(v: &str) -> Result<&str, String> {
    let v = v.trim();
    let ok = v == "builtin"
        || (!v.is_empty()
            && v.len() <= 32
            && v.bytes()
                .next()
                .is_some_and(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
            && v.bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'));
    if ok {
        Ok(v)
    } else {
        Err("That is not one of Jarvis's voices.".to_string())
    }
}

/// A WAV file the owner chose, as the page read it (base64): decoded to
/// check it is a WAV and not too big, then sent as it is. The server reads
/// the rest (bits, rate, length) and says what is wrong in words.
pub(crate) fn chosen_wav(file: &str) -> Result<String, String> {
    let raw = BASE64
        .decode(file.trim())
        .map_err(|_| "That file could not be read.".to_string())?;
    if raw.len() > VOICE_CLIP_MAX_BYTES {
        return Err(format!(
            "That file is too big ({:.1} MB; at most 2.9 MB). Use a shorter clip, 10 seconds \
             at most, saved as a mono WAV if you can.",
            raw.len() as f64 / 1e6
        ));
    }
    if raw.len() < 44 || &raw[0..4] != b"RIFF" || &raw[8..12] != b"WAVE" {
        return Err(
            "That is not a WAV file. Save the recording as a WAV file and try again.".to_string(),
        );
    }
    Ok(BASE64.encode(raw))
}

/// The voices kept on this PC, which one Jarvis speaks in and why the
/// built-in one is used instead, the better voice, a waiting card and the
/// last few timings: `GET /api/voice/voices`. A read.
#[tauri::command]
pub async fn get_custom_voices(app: AppHandle) -> Result<Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(VOICES_TIMEOUT))?
        .get(format!("{base}/api/voice/voices"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    voices_status_answer(status, &body)
}

/// Adds a voice: ONE approval card, nothing kept until it is approved. The
/// recording is either the one held under `voice` (the owner read the
/// sentence the page showed, which is `transcript`) or a WAV file the owner
/// chose (`file`, with the words they typed). Held on a stale link.
#[tauri::command]
pub async fn create_custom_voice(
    app: AppHandle,
    name: String,
    transcript: String,
    slot: Option<String>,
    file: Option<String>,
    state: State<'_, SampleState>,
) -> Result<Value, String> {
    let name = name.trim().to_string();
    let transcript = transcript.trim().to_string();
    if name.is_empty() {
        return Err("Give the voice a name.".to_string());
    }
    if transcript.is_empty() {
        return Err("Type exactly what is said in the recording.".to_string());
    }
    if name.chars().count() > 200 || transcript.chars().count() > 2000 {
        return Err("That name or those words are far too long.".to_string());
    }
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (clip, recorded) = match (slot.as_deref(), file.as_deref()) {
        (Some("voice"), None) => {
            let held = take_held(&state, &["voice".to_string()])?;
            (
                held.into_iter().next().map(|(c, _)| c).unwrap_or_default(),
                true,
            )
        }
        (None, Some(f)) => (chosen_wav(f)?, false),
        _ => return Err("Record the sentence, or choose a WAV file.".to_string()),
    };
    let body = json!({ "name": name, "clip": clip, "transcript": transcript });
    drop(clip);
    let (status, text) = post(&app, "/api/voice/voices/create", &body, VOICES_TIMEOUT).await?;
    drop(body);
    let answer = voices_answer(status, &text)?;
    if recorded && is_2xx(&answer) {
        forget(&state, &["voice".to_string()]);
    }
    Ok(answer)
}

/// Which voice Jarvis speaks in. `builtin` is immediate and never held (it
/// also withdraws a waiting switch card); a custom voice raises ONE card
/// and is held on a stale link.
#[tauri::command]
pub async fn set_active_voice(app: AppHandle, voice: String) -> Result<Value, String> {
    let voice = voice_id(&voice)?.to_string();
    if voice != "builtin" && stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/active",
        &json!({ "voice": voice }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// Deletes a voice. Immediate and never held: it only takes a voice away
/// (the page asks the owner to confirm first).
#[tauri::command]
pub async fn delete_custom_voice(app: AppHandle, voice: String) -> Result<Value, String> {
    let voice = voice_id(&voice)?.to_string();
    if voice == "builtin" {
        return Err("The built-in voice cannot be deleted.".to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/delete",
        &json!({ "voice": voice }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// The better voice on the second graphics card. ON raises ONE card and is
/// held on a stale link; OFF is immediate.
#[tauri::command]
pub async fn set_better_voice(app: AppHandle, enabled: bool) -> Result<Value, String> {
    if enabled && stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/better",
        &json!({ "enabled": enabled }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// The three speaking speeds the PC offers (`GET /api/voice/voices`
/// `speed.choices`). Anything else is refused here, before it is sent.
pub(crate) const SPEEDS: [&str; 3] = ["slower", "normal", "faster"];

/// How fast every voice on the PC speaks. No card either way - it trusts
/// nothing more (like the manner setting) - but, like every change sent to
/// the PC, held on a stale link (rule 4).
#[tauri::command]
pub async fn set_voice_speed(app: AppHandle, speed: String) -> Result<Value, String> {
    let speed = speed.trim().to_string();
    if !SPEEDS.contains(&speed.as_str()) {
        return Err("Choose Slower, Normal or Faster.".to_string());
    }
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/speed",
        &json!({ "speed": speed }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// The built-in voices Kokoro offers (`GET /api/voice/voices`
/// `speaker.choices`, eleven of them, "0".."10"). Checked against that same
/// list here too, so a PC on an older backend that never sends `speaker` at
/// all cannot be sent a value it has no way to show back correctly.
pub(crate) const SPEAKERS: [&str; 11] = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

/// Which of Kokoro's own voices the built-in voice uses. Same shape as
/// [`set_voice_speed`]: no card either way, held on a stale link (rule 4).
#[tauri::command]
pub async fn set_voice_speaker(app: AppHandle, speaker: String) -> Result<Value, String> {
    let speaker = speaker.trim().to_string();
    if !SPEAKERS.contains(&speaker.as_str()) {
        return Err("Choose one of the listed voices.".to_string());
    }
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/speaker",
        &json!({ "speaker": speaker }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// "Voice follows the face": with an animal face showing, the built-in
/// voice becomes that animal's (`GET /api/voice/voices` `face_voice`). Same
/// shape as [`set_voice_speaker`]: no card either way, held on a stale link
/// (rule 4) whichever way it is switched.
#[tauri::command]
pub async fn set_voice_face(app: AppHandle, enabled: bool) -> Result<Value, String> {
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/face",
        &json!({ "enabled": enabled }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// The animal faces with a voice of their own (`GET /api/voice/voices`
/// `face_voice.animals`) - the four animals and the robot, which counts as
/// one here as everywhere. Anything else is refused here, before it is sent.
pub(crate) const ANIMALS: [&str; 5] = ["redpanda", "pygmyowl", "seaotter", "monkey", "robot"];

/// How far an animal's pitch may move, in semitones ("steps" on screen):
/// 3 deeper to 4 higher, in half steps - the PC's own range
/// (`face_voice.animal_choices.pitch`, jarvis_voices.MIN/MAX_SEMITONES).
pub(crate) const PITCH_MIN: f64 = -3.0;
pub(crate) const PITCH_MAX: f64 = 4.0;

fn animal_id(face: &str) -> Result<&'static str, String> {
    let face = face.trim();
    ANIMALS.iter().copied().find(|a| *a == face).ok_or_else(|| {
        "Choose the Red Panda, the Pygmy Owl, the Sea Otter, the Monkey or the Robot.".to_string()
    })
}

/// `semitones` if it is a pitch the PC takes (in range, whole half steps).
pub(crate) fn animal_pitch(semitones: f64) -> Option<f64> {
    if !semitones.is_finite() || !(PITCH_MIN..=PITCH_MAX).contains(&semitones) {
        return None;
    }
    let halves = semitones * 2.0;
    if (halves - halves.round()).abs() > 1e-9 {
        return None;
    }
    Some(halves.round() / 2.0)
}

/// The body for one animal's voice (`POST /api/voice/voices/face_animal`),
/// or why it cannot be sent.
pub(crate) fn animal_body(
    face: &str,
    speaker: &str,
    semitones: f64,
    pace: &str,
) -> Result<Value, String> {
    let face = animal_id(face)?;
    let speaker = speaker.trim();
    if !SPEAKERS.contains(&speaker) {
        return Err("Choose one of the listed voices.".to_string());
    }
    let semitones = animal_pitch(semitones).ok_or_else(|| {
        "The pitch must be from 3 steps deeper to 4 steps higher, in half steps.".to_string()
    })?;
    let pace = pace.trim();
    if !SPEEDS.contains(&pace) {
        return Err("Choose Slower, Normal or Faster.".to_string());
    }
    Ok(json!({ "face": face, "speaker": speaker, "semitones": semitones, "pace": pace }))
}

/// One animal's own voice, pitch and pace (under "Voice follows the face").
/// Same shape as [`set_voice_speaker`]: no card either way, held on a stale
/// link (rule 4).
#[tauri::command]
pub async fn set_voice_animal(
    app: AppHandle,
    face: String,
    speaker: String,
    semitones: f64,
    pace: String,
) -> Result<Value, String> {
    let body = animal_body(&face, &speaker, semitones, &pace)?;
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(&app, "/api/voice/voices/face_animal", &body, VOICES_TIMEOUT).await?;
    voices_answer(status, &text)
}

/// "Reset to its own voice" for one animal. No card, held on a stale link
/// like every change sent to the PC (rule 4).
#[tauri::command]
pub async fn reset_voice_animal(app: AppHandle, face: String) -> Result<Value, String> {
    let face = animal_id(&face)?;
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(
        &app,
        "/api/voice/voices/face_animal",
        &json!({ "face": face, "reset": true }),
        VOICES_TIMEOUT,
    )
    .await?;
    voices_answer(status, &text)
}

/// The most sound "Try it" takes back: one short fixed line is a few
/// hundred kilobytes; anything far bigger is not that.
const TRY_MAX_BYTES: usize = 4_000_000;

/// "Try it": the PC says one fixed line (its own words, never the app's) in
/// that animal's voice as it is now, and it comes back as
/// `{"ok": true, "audio": "data:audio/wav;base64,..."}` for the page to
/// play - the same data-URI shape as [`crate::voice::speak_reply`]. Changes
/// nothing on the PC, so it is not held on a stale link. A refusal is the
/// PC's own sentence, as for every other voice answer. Refused while the
/// talk button records ([`TRY_BUSY`]): the sound would go into the question.
/// Settings also refuses while Jarvis is speaking, from the events it hears
/// (voice-panel.js `jarvisBusy`).
#[tauri::command]
pub async fn try_voice_animal(
    app: AppHandle,
    capture: State<'_, VoiceCaptureState>,
    face: String,
) -> Result<Value, String> {
    let face = animal_id(&face)?;
    if capture.busy() {
        return Err(TRY_BUSY.to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(VOICES_TIMEOUT))?
        .post(format!("{base}/api/voice/voices/face_animal/try"))
        .headers(jarvis_headers(&app)?)
        .json(&json!({ "face": face }))
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let audio = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| v.starts_with("audio/"));
    if (200..300).contains(&status) && audio {
        let bytes = response
            .bytes()
            .await
            .map_err(|e| format!("could not read the sound: {e}"))?;
        return try_answer(&bytes);
    }
    let text = response.text().await.unwrap_or_default();
    try_refusal(status, &text)
}

/// Why "Try it" got no sound. A 404 that is not the PC's own answer means
/// its backend is older than the route: said in the same words as the
/// phone ([`TRY_UPDATE`]), not the general "update the backend" one.
pub(crate) fn try_refusal(status: u16, body: &str) -> Result<Value, String> {
    let has_ok = parsed_object(body).is_some_and(|m| m.contains_key("ok"));
    if status == 404 && !has_ok {
        return Err(TRY_UPDATE.to_string());
    }
    voices_answer(status, body)
}

/// The sound "Try it" got back, as the page plays it - or why not.
pub(crate) fn try_answer(bytes: &[u8]) -> Result<Value, String> {
    if bytes.len() < 12 || &bytes[..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err("The PC sent something that is not a sound.".to_string());
    }
    if bytes.len() > TRY_MAX_BYTES {
        return Err("The PC sent far more sound than one short line.".to_string());
    }
    Ok(json!({
        "ok": true,
        "http": 200,
        "audio": format!("data:audio/wav;base64,{}", BASE64.encode(bytes)),
    }))
}

// ---------------------------------------------------------------------------
// The one-time animal voice question (the owner, 2026-09-28)
// ---------------------------------------------------------------------------
//
// The first time the owner picks an animal face, one line asks "The Red
// Panda has its own voice. Use it?" - "Use it" / "Keep my voice",
// remembered per face ON THE PC. The PC decides whether to ask
// (`GET /api/voice/voices` `face_voice.offer`) and says every word; the
// apps show those words as they are. A face never changes the voice by
// itself: only "Use it" turns "Voice follows the face" on.

/// The longest question or button word the page is handed.
const OFFER_MAX_CHARS: usize = 200;

/// The PC's `face_voice.offer`, checked: `{face, question, use, keep}` for
/// one of the four animals, every word present and short - or null.
pub(crate) fn face_offer_of(status: &Value) -> Value {
    let Some(offer) = status
        .get("face_voice")
        .and_then(|fv| fv.get("offer"))
        .and_then(Value::as_object)
    else {
        return Value::Null;
    };
    let word = |key: &str| {
        offer
            .get(key)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|s| !s.is_empty() && s.chars().count() <= OFFER_MAX_CHARS)
    };
    let face = offer.get("face").and_then(Value::as_str).unwrap_or("");
    match (
        animal_id(face).ok(),
        word("question"),
        word("use"),
        word("keep"),
    ) {
        (Some(face), Some(question), Some(use_it), Some(keep)) => json!({
            "face": face,
            "question": question,
            "use": use_it,
            "keep": keep,
        }),
        _ => Value::Null,
    }
}

/// The body for the owner's answer (`POST /api/voice/voices/face_offer`),
/// or why it cannot be sent.
pub(crate) fn face_offer_body(face: &str, answer: &str) -> Result<Value, String> {
    let face = animal_id(face)?;
    let answer = answer.trim();
    if answer != "use" && answer != "keep" {
        return Err("Choose \"Use it\" or \"Keep my voice\".".to_string());
    }
    Ok(json!({ "face": face, "answer": answer }))
}

/// For the Faces window, which may not read the voices list itself: only
/// the waiting question (or null) and whether the link is stale, so the
/// page can grey its buttons (rule 4). A read; changes nothing.
#[tauri::command]
pub async fn get_face_voice_offer(app: AppHandle) -> Result<Value, String> {
    let status = get_custom_voices(app.clone()).await?;
    Ok(json!({ "offer": face_offer_of(&status), "stale": stale(&app) }))
}

/// The owner's answer to the one-time question: "use" turns "Voice follows
/// the face" on, "keep" leaves the voice as it is; the PC remembers the
/// face either way. No card (the switch itself has none), held on a stale
/// link like every change sent to the PC (rule 4).
#[tauri::command]
pub async fn answer_face_voice_offer(
    app: AppHandle,
    face: String,
    answer: String,
) -> Result<Value, String> {
    let body = face_offer_body(&face, &answer)?;
    if stale(&app) {
        return Err(HELD_STALE.to_string());
    }
    let (status, text) = post(&app, "/api/voice/voices/face_offer", &body, VOICES_TIMEOUT).await?;
    voices_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The backend's real answers (tools/gen_voice_training_cases.py).
    const CASES: &str = include_str!("../../tests/fixtures/voice-training-cases.json");

    fn cases() -> Value {
        serde_json::from_str(CASES).expect("voice-training-cases.json is JSON")
    }

    #[test]
    fn every_real_enroll_answer_is_passed_on_with_its_code() {
        let all = cases();
        for (name, a) in all["enroll"].as_object().expect("enroll") {
            let code = a["code"].as_u64().expect("code") as u16;
            let got = enroll_answer(code, &a["body"].to_string())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(got["http"], json!(code), "{name}");
            let mut body = got.clone();
            body.as_object_mut().expect("object").remove("http");
            assert_eq!(body, a["body"], "{name} was changed on the way");
        }
    }

    #[test]
    fn every_real_voices_answer_is_passed_on_with_its_code() {
        let all = cases();
        for (name, a) in all["voice_posts"].as_object().expect("voice_posts") {
            let code = a["code"].as_u64().expect("code") as u16;
            let got = voices_answer(code, &a["body"].to_string())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(got["http"], json!(code), "{name}");
        }
        for (name, st) in all["voices"].as_object().expect("voices") {
            let got = voices_status_answer(200, &st.to_string())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, st, "{name}");
        }
    }

    #[test]
    fn each_animals_choices_are_the_pcs_own() {
        let all = cases();
        let fv = &all["voices"]["face_showing"]["face_voice"];
        let faces: Vec<&str> = fv["animals"]
            .as_array()
            .expect("animals")
            .iter()
            .map(|a| a["face"].as_str().expect("face"))
            .collect();
        assert_eq!(
            faces, ANIMALS,
            "the PC's animals and the ones sent from here"
        );
        let ch = &fv["animal_choices"];
        let voices: Vec<&str> = ch["voices"]
            .as_array()
            .expect("voices")
            .iter()
            .map(|c| c["id"].as_str().expect("id"))
            .collect();
        assert_eq!(voices, SPEAKERS);
        let paces: Vec<&str> = ch["paces"]
            .as_array()
            .expect("paces")
            .iter()
            .map(|c| c["id"].as_str().expect("id"))
            .collect();
        assert_eq!(paces, SPEEDS);
        assert_eq!(ch["pitch"]["min"], json!(PITCH_MIN));
        assert_eq!(ch["pitch"]["max"], json!(PITCH_MAX));
        assert_eq!(ch["pitch"]["step"], json!(0.5));
    }

    #[test]
    fn an_animal_body_is_checked_before_it_is_sent() {
        assert_eq!(
            animal_body("redpanda", "3", -1.5, "faster").expect("sent"),
            json!({"face": "redpanda", "speaker": "3", "semitones": -1.5, "pace": "faster"})
        );
        assert!(animal_body("orbit", "3", 0.0, "normal").is_err());
        assert!(animal_body("redpanda", "11", 0.0, "normal").is_err());
        assert!(animal_body("redpanda", "3", 0.0, "fast").is_err());
        for bad in [4.5, -3.5, 1.25, f64::NAN, f64::INFINITY] {
            assert!(
                animal_body("redpanda", "3", bad, "normal").is_err(),
                "{bad}"
            );
        }
        for ok in [-3.0, -0.5, 0.0, 2.5, 4.0] {
            assert_eq!(animal_pitch(ok), Some(ok));
        }
    }

    #[test]
    fn try_it_is_a_wav_or_a_sentence() {
        let wav = [b"RIFF".as_slice(), &[0; 4], b"WAVEfmt "].concat();
        let got = try_answer(&wav).expect("a sound");
        assert_eq!(got["ok"], true);
        assert!(got["audio"]
            .as_str()
            .unwrap_or("")
            .starts_with("data:audio/wav;base64,"));
        assert!(try_answer(b"<html>not a sound</html>").is_err());
        assert!(try_answer(b"").is_err());
        let all = cases();
        let bad = voices_answer(
            400,
            &all["voice_posts"]["animal_try_bad"]["body"].to_string(),
        )
        .expect("the PC's own sentence");
        assert_eq!(bad["http"], 400);
    }

    #[test]
    fn try_it_on_an_older_pc_says_so_like_the_phone() {
        // No route: the server's own 404, which is not a voices answer.
        for body in ["", "{\"error\": \"not found\"}", "<html>404</html>"] {
            assert_eq!(try_refusal(404, body).unwrap_err(), TRY_UPDATE, "{body:?}");
        }
        // The PC's own refusals still come through in its own words.
        let all = cases();
        let bad = try_refusal(
            400,
            &all["voice_posts"]["animal_try_bad"]["body"].to_string(),
        )
        .expect("the PC's own sentence");
        assert_eq!(bad["http"], 400);
        let busy = try_refusal(
            429,
            &all["voice_posts"]["animal_try_busy"]["body"].to_string(),
        )
        .expect("the PC's own sentence");
        assert_eq!(busy["http"], 429);
        assert_eq!(busy["ok"], false);
        // A 503 from a backend without jarvis_voices.py is still the general one.
        assert_eq!(
            try_refusal(503, "{\"available\": false, \"error\": \"x\"}").unwrap_err(),
            VOICES_UPDATE
        );
    }

    #[test]
    fn the_speed_choices_are_the_pcs_own() {
        let all = cases();
        let st = &all["voices"]["speed_chosen"]["speed"];
        let ids: Vec<&str> = st["choices"]
            .as_array()
            .expect("choices")
            .iter()
            .map(|c| c["id"].as_str().expect("id"))
            .collect();
        assert_eq!(ids, SPEEDS, "the PC's choices and the ones sent from here");
        assert_eq!(st["choice"], "faster");
        let bad = voices_answer(400, &all["voice_posts"]["speed_bad"]["body"].to_string())
            .expect("passed on");
        assert_eq!(bad["http"], 400);
        assert!(bad["error"].as_str().unwrap_or("").contains("speed"));
    }

    #[test]
    fn an_older_backend_is_a_sentence() {
        assert_eq!(enroll_answer(404, "").unwrap_err(), TRAINING_UPDATE);
        assert_eq!(
            enroll_answer(
                503,
                r#"{"error": "voice training is not installed on this PC", "available": false}"#
            )
            .unwrap_err(),
            TRAINING_UPDATE
        );
        // The stricter check's own 503 (an old jarvis_voice.py) is a sentence to show.
        let old = enroll_answer(503, r#"{"error": "the voice check on this PC is too old for this setting (run the patch script)"}"#)
            .expect("passed on");
        assert_eq!(old["http"], 503);
        assert_eq!(
            voices_answer(404, r#"{"error": "not found"}"#).unwrap_err(),
            VOICES_UPDATE
        );
        assert_eq!(
            voices_answer(
                503,
                r#"{"available": false, "error": "custom voices are not installed on this PC"}"#
            )
            .unwrap_err(),
            VOICES_UPDATE
        );
        let gone = voices_status_answer(404, "").expect("a sentence");
        assert_eq!(gone["why"], VOICES_UPDATE);
        let gone =
            voices_status_answer(503, r#"{"available": false, "error": "x", "reason": "y"}"#)
                .expect("a sentence");
        assert_eq!(gone["available"], false);
        let odd = voices_answer(500, "<html>boom</html>").unwrap_err();
        assert!(odd.contains("500") && !odd.contains("boom"), "{odd}");
        let said = enroll_answer(403, r#"{"error": "cross-origin request refused"}"#).unwrap_err();
        assert_eq!(said, "Cross-origin request refused");
    }

    #[test]
    fn only_known_slots_and_voices() {
        for ok in ["voice", "t1-0", "t3-11", "m0", "m19", "o0", "o4"] {
            assert_eq!(valid_slot(ok), Ok(ok));
        }
        for bad in [
            "", "t4-0", "t1-12", "t1-01", "m20", "m", "voice2", "t1", "../x", "t1-a", "o5", "o",
            "o01",
        ] {
            assert!(valid_slot(bad).is_err(), "{bad} was accepted");
        }
        assert_eq!(slot_rate("voice"), 24_000);
        assert_eq!(slot_rate("t1-0"), 16_000);
        for ok in ["builtin", "grandpa", "aunt-may", "a1"] {
            assert_eq!(voice_id(ok), Ok(ok));
        }
        for bad in ["", "Grandpa", "-x", "a/b", "a b", &"x".repeat(33)] {
            assert!(voice_id(bad).is_err(), "{bad} was accepted");
        }
    }

    #[test]
    fn someone_else_only_to_a_pc_that_understands_it() {
        assert!(calibrate_understood(
            &json!({ "gate": { "training": { "calibrate": true } } })
        ));
        for older in [
            json!({ "gate": { "training": { "available": true } } }),
            json!({ "gate": { "training": { "calibrate": "true" } } }),
            json!({ "available": false }),
            json!(null),
        ] {
            assert!(!calibrate_understood(&older), "{older}");
        }
    }

    #[test]
    fn the_threshold_card_names_this_microphone_and_the_model() {
        assert_eq!(
            threshold_body(0.553, Some("strong")),
            Ok(
                json!({ "mode": "threshold", "mic": "desktop", "threshold": 0.55, "model": "strong" })
            )
        );
        assert_eq!(
            threshold_body(0.5, None),
            Ok(json!({ "mode": "threshold", "mic": "desktop", "threshold": 0.5 }))
        );
        assert_eq!(
            threshold_body(0.5, Some(" ")).map(|b| b.get("model").is_none()),
            Ok(true)
        );
        for bad in [0.0, 0.04, 0.95, f64::NAN, f64::INFINITY] {
            assert!(threshold_body(bad, None).is_err(), "{bad} was accepted");
        }
        assert!(threshold_body(0.5, Some("huge")).is_err());
    }

    #[test]
    fn only_loosening_is_marked_loosening() {
        assert_eq!(
            voice_setting("strictness", "balanced"),
            Ok(("strictness", "balanced", true))
        );
        assert_eq!(
            voice_setting("privacy", "voice_is_enough"),
            Ok(("privacy", "voice_is_enough", true))
        );
        assert_eq!(
            voice_setting("strictness", "very_strict").map(|t| t.2),
            Ok(false)
        );
        assert_eq!(
            voice_setting("privacy", "private_on_screen").map(|t| t.2),
            Ok(false)
        );
        assert_eq!(
            voice_setting("memory", "memory_aloud"),
            Ok(("memory", "memory_aloud", true))
        );
        assert_eq!(
            voice_setting("memory", "memory_on_screen").map(|t| t.2),
            Ok(false)
        );
        assert_eq!(
            voice_setting("sensitive_memory", "sensitive_aloud"),
            Ok(("sensitive_memory", "sensitive_aloud", true))
        );
        assert_eq!(
            voice_setting("sensitive_memory", "sensitive_on_screen"),
            Ok(("sensitive_memory", "sensitive_on_screen", false))
        );
        // Each value belongs to its own setting only.
        assert!(voice_setting("memory", "sensitive_aloud").is_err());
        assert!(voice_setting("sensitive_memory", "memory_aloud").is_err());
        assert_eq!(
            voice_setting("hands_free", "same_as_button"),
            Ok(("hands_free", "same_as_button", true))
        );
        assert_eq!(
            voice_setting("hands_free", "button_only"),
            Ok(("hands_free", "button_only", false))
        );
        assert!(voice_setting("hands_free", "sensitive_aloud").is_err());
        assert!(voice_setting("memory", "button_only").is_err());
        assert_eq!(
            voice_setting("hands_free_screen", "screen_aloud"),
            Ok(("hands_free_screen", "screen_aloud", true))
        );
        assert_eq!(
            voice_setting("hands_free_screen", "screen_on_screen"),
            Ok(("hands_free_screen", "screen_on_screen", false))
        );
        assert!(voice_setting("hands_free_screen", "same_as_button").is_err());
        assert!(voice_setting("hands_free", "screen_aloud").is_err());
        assert!(voice_setting("mode", "broad").is_err());
        // Jarvis Live's three choices: the strictest never loosens.
        assert_eq!(
            voice_setting("hands_free_live", "live_like_hey_jarvis"),
            Ok(("hands_free_live", "live_like_hey_jarvis", false))
        );
        assert!(voice_setting("hands_free_live", "screen_aloud").is_err());
        // When App lock ends Jarvis Live on this PC: only when Windows locks
        // is the looser choice (a card).
        assert_eq!(
            voice_setting("live_end", "live_end_windows_lock"),
            Ok(("live_end", "live_end_windows_lock", true))
        );
        assert_eq!(
            voice_setting("live_end", "live_end_app_lock"),
            Ok(("live_end", "live_end_app_lock", false))
        );
        assert!(voice_setting("live_end", "live_trust_fully").is_err());
        assert!(voice_setting("hands_free_screen", "live_trust_fully").is_err());
        assert!(live_trust_loosens(
            "live_trust_fully",
            Some("live_button_start_only")
        ));
        assert!(live_trust_loosens(
            "live_button_start_only",
            Some("live_like_hey_jarvis")
        ));
        assert!(!live_trust_loosens(
            "live_button_start_only",
            Some("live_trust_fully")
        ));
        assert!(!live_trust_loosens(
            "live_like_hey_jarvis",
            Some("live_trust_fully")
        ));
        assert!(!live_trust_loosens(
            "live_trust_fully",
            Some("live_trust_fully")
        ));
        assert!(
            live_trust_loosens("live_button_start_only", None),
            "unknown: held"
        );
        assert!(!live_trust_loosens("live_like_hey_jarvis", None));
        // Talk-to-type (2026-09-28): on is the card, off is at once.
        assert_eq!(
            voice_setting("talk_to_type", "on"),
            Ok(("talk_to_type", "on", true))
        );
        assert_eq!(
            voice_setting("talk_to_type", "off"),
            Ok(("talk_to_type", "off", false))
        );
        assert!(voice_setting("talk_to_type", "yes").is_err());
        // "Better voice" (2026-09-28): both detectors and the measured model
        // at once; one detector and the unmeasured model are the card.
        assert_eq!(
            voice_setting("wake_confirm", "both"),
            Ok(("wake_confirm", "both", false))
        );
        assert_eq!(
            voice_setting("wake_confirm", "one"),
            Ok(("wake_confirm", "one", true))
        );
        assert_eq!(
            voice_setting("voice_id_model", "titanet"),
            Ok(("voice_id_model", "titanet", false))
        );
        assert_eq!(
            voice_setting("voice_id_model", "resnet221"),
            Ok(("voice_id_model", "resnet221", true))
        );
        assert!(voice_setting("voice_id_model", "resnet293").is_err());
        assert!(voice_setting("wake_confirm", "on").is_err());
    }

    #[test]
    fn the_training_body_is_the_one_the_backend_reads() {
        let clips = vec!["QQ==".to_string()];
        let round = training_body(2, &clips, true, false, false);
        assert_eq!(
            round,
            json!({"mode": "train", "round": 2, "mic": "desktop", "add": true, "clips": ["QQ=="]})
        );
        let finish = training_body(3, &[], false, true, false);
        assert_eq!(
            finish,
            json!({"mode": "train", "round": 3, "mic": "desktop", "add": false, "finish": true})
        );
        let old = training_body(1, &clips, false, false, true);
        assert_eq!(old, json!({"clips": ["QQ=="], "mic": "desktop"}));
    }

    #[test]
    fn the_guided_test_is_split_under_the_servers_limits_and_added_up() {
        assert_eq!(measure_parts(&[3.0; 20]), vec![0..20]);
        assert_eq!(measure_parts(&[5.0; 20]), vec![0..15, 15..20]);
        assert_eq!(measure_parts(&[]), Vec::<Range<usize>>::new());
        let all = cases();
        let one = all["enroll"]["measure"]["body"].clone();
        let mut withcode = one.clone();
        withcode["http"] = json!(200);
        let two = combine_measures(&[withcode.clone(), withcode]);
        assert_eq!(two["clips"], json!(one["clips"].as_u64().unwrap() * 2));
        assert_eq!(
            two["very_strict"]["passed"],
            json!(one["very_strict"]["passed"].as_u64().unwrap() * 2)
        );
        assert_eq!(
            two["very_strict"]["repeat_rate"],
            one["very_strict"]["repeat_rate"]
        );
        assert_eq!(two["strong_model"], one["strong_model"]);
    }

    #[test]
    fn a_chosen_file_must_be_a_wav_and_not_too_big() {
        let mut wav = b"RIFF\0\0\0\0WAVEfmt ".to_vec();
        wav.resize(64, 0);
        assert!(chosen_wav(&BASE64.encode(&wav)).is_ok());
        assert!(chosen_wav(
            &BASE64.encode(b"ID3 not a wav at all, an mp3 header........................")
        )
        .is_err());
        assert!(chosen_wav("not base64!").is_err());
        let big = vec![0u8; VOICE_CLIP_MAX_BYTES + 1];
        assert!(chosen_wav(&BASE64.encode(big))
            .unwrap_err()
            .contains("too big"));
    }

    #[test]
    fn the_loudest_sample() {
        assert_eq!(peak(&[0, 16384, -32768]), 1.0);
        assert_eq!(peak(&[]), 0.0);
    }
    #[test]
    fn the_animal_voice_question_is_passed_on_only_when_whole() {
        let st = json!({"face_voice": {"enabled": false, "offer": {
            "face": "redpanda",
            "question": "The Red Panda has its own voice. Use it?",
            "use": "Use it", "keep": "Keep my voice"}}});
        let got = face_offer_of(&st);
        assert_eq!(got["face"], json!("redpanda"));
        assert_eq!(
            got["question"],
            json!("The Red Panda has its own voice. Use it?")
        );
        assert_eq!(got["use"], json!("Use it"));
        assert_eq!(got["keep"], json!("Keep my voice"));
        assert!(face_offer_of(&json!({"face_voice": {"offer": null}})).is_null());
        assert!(face_offer_of(&json!({"voices": []})).is_null());
        let mut not_animal = st.clone();
        not_animal["face_voice"]["offer"]["face"] = json!("orbit");
        assert!(face_offer_of(&not_animal).is_null());
        let mut no_words = st.clone();
        no_words["face_voice"]["offer"]["keep"] = json!("");
        assert!(face_offer_of(&no_words).is_null());
        let mut long = st;
        long["face_voice"]["offer"]["question"] = json!("x".repeat(OFFER_MAX_CHARS + 1));
        assert!(face_offer_of(&long).is_null());
    }

    #[test]
    fn the_answer_is_use_or_keep_for_an_animal() {
        assert_eq!(
            face_offer_body("seaotter", "use").unwrap(),
            json!({"face": "seaotter", "answer": "use"})
        );
        assert_eq!(
            face_offer_body(" monkey ", " keep ").unwrap(),
            json!({"face": "monkey", "answer": "keep"})
        );
        assert!(face_offer_body("orbit", "use").is_err());
        assert!(face_offer_body("redpanda", "yes").is_err());
        assert!(face_offer_body("redpanda", "").is_err());
    }
}
