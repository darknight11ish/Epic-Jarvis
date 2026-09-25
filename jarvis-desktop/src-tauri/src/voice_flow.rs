//! The voice flow on this PC (docs/JARVIS-API.md section 17): interrupting
//! Jarvis by talking, the "One moment." clip, and `waited_ms`.
//!
//! INTERRUPTING BY TALKING - PAUSE FIRST, DECIDE SECOND
//! While "hey Jarvis" listening is on, the listener (voice.rs `run_vad_loop`)
//! keeps hearing the room while Jarvis speaks. When one utterance has held
//! [`BARGE_ONSET`] of speech, it tells the Jarvis bar (`VOICE_BARGE_ONSET`,
//! with the utterance's number). The bar decides - is Jarvis talking, past
//! the first three seconds of the reply, the owner's switch on, the PC able
//! to tell the owner's voice (src/voice-flow.js) - and if so PAUSES the
//! reply at once and asks for that utterance to be checked
//! ([`judge_barge_in`]). The listener then sends about [`BARGE_CLIP`] of it,
//! from where the speech started, to the PC as `source=barge_in`, or less if
//! the utterance ends first, and hands the answer back
//! (`VOICE_BARGE_VERDICT`): stop for good, or carry on.
//!
//! The PC decides whose voice it was (the owner's voice print, or the word
//! "stop" said by anyone). The clip is NEVER transcribed there - the route
//! answers "stop or not" and nothing else - and it goes only to the Jarvis
//! server on this PC: the same loopback check as every other clip the
//! listener sends (`wake_audio_refusal`), and never while the event stream
//! is stale (rule 4 - then the bar is told "no answer" and carries on).
//!
//! The utterance is still sent as `source=wake_word` when it ends, exactly as
//! before, so "hey Jarvis, ..." said over a reply is still answered and
//! "stop" still stops.
//!
//! Why the Jarvis bar asks, rather than the listener deciding: only the bar
//! knows whether a reply is playing and for how long, and the rules are the
//! phone's word for word (voice-flow.js and VoiceFlow.kt share one list of
//! cases). The listener never sends `source=barge_in` for an utterance the
//! bar did not ask about, so an older PC - which would treat an unknown
//! source as push-to-talk and transcribe it - is never sent one: the bar
//! asks only when `/api/voice/status` has a `flow` block saying barge-in is
//! available ([`get_voice_flow`]).

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers};

/// Speech in one utterance before the Jarvis bar is told (voice-flow.js
/// `ONSET_MS`, the phone's `VoiceFlow.ONSET_MS`).
pub(crate) const BARGE_ONSET: Duration = Duration::from_millis(500);
/// How much of the utterance, from where the speech started, is sent. The
/// PC recognised the owner from 2-second clips and not from 1.2-1.5 second
/// ones (backend/README.md, "The voice flow").
pub(crate) const BARGE_CLIP: Duration = Duration::from_millis(2000);
/// One small WAV and a voice-print check (139-273 ms measured), over loopback.
const BARGE_TIMEOUT: Duration = Duration::from_secs(4);
/// `/api/voice/status` and the "One moment." clip are small.
const FLOW_TIMEOUT: Duration = Duration::from_secs(8);

/// The utterance the Jarvis bar asked to have checked ([`judge_barge_in`]),
/// or 0 for none.
static BARGE_WANTED: AtomicU64 = AtomicU64::new(0);
/// Numbers the listener's utterances, from 1.
static UTTERANCE_SEQ: AtomicU64 = AtomicU64::new(0);

/// A new utterance's number.
pub(crate) fn next_utterance_id() -> u64 {
    UTTERANCE_SEQ.fetch_add(1, Ordering::Relaxed) + 1
}

/// Whether the Jarvis bar asked for utterance `id` to be checked.
pub(crate) fn barge_wanted(id: u64) -> bool {
    id != 0 && BARGE_WANTED.load(Ordering::Relaxed) == id
}

/// Tell the bar now: enough speech, and not told yet.
pub(crate) fn onset_due(voiced: Duration, told: bool) -> bool {
    !told && voiced >= BARGE_ONSET
}

/// Send the clip now: the bar asked, it was not sent yet, and either
/// [`BARGE_CLIP`] has passed since the speech started or the utterance just
/// ended (`cut`).
pub(crate) fn clip_due(elapsed: Duration, wanted: bool, sent: bool, cut: bool) -> bool {
    wanted && !sent && (cut || elapsed >= BARGE_CLIP)
}

/// `VOICE_BARGE_ONSET`'s payload.
#[derive(Debug, Clone, Serialize)]
pub struct BargeOnset {
    pub id: u64,
}

/// `VOICE_BARGE_VERDICT`'s payload: the PC's answer for utterance `id`.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct BargeVerdict {
    pub id: u64,
    /// Stop the reply for good: the owner's voice, or "stop".
    pub stop: bool,
    /// False: the PC cannot tell the owner's voice now; stop asking until
    /// its status says otherwise.
    pub available: bool,
    /// The PC's code (`owner_voice`, `not_owner`, `jarvis_voice`, ...), or
    /// this app's own: `held` (stale link), `refused` (not this PC),
    /// `failed` (no answer).
    pub why: String,
}

/// The barge-in reply, the fields read here. A route without
/// `voice-flow.patch` answers the usual utterance reply, whose `stop` means
/// the same (section 17).
#[derive(Debug, Deserialize)]
struct BargeRaw {
    #[serde(default)]
    stop: bool,
    #[serde(default = "yes")]
    available: bool,
    #[serde(default)]
    why: String,
}

fn yes() -> bool {
    true
}

/// The PC's answer to a barge-in clip, read. Anything that is not a 200
/// with JSON is "carry on" - an interruption that could not be checked
/// never stops the reply.
pub(crate) fn barge_answer(id: u64, status: u16, body: &str) -> BargeVerdict {
    let failed = |why: &str| BargeVerdict {
        id,
        stop: false,
        available: true,
        why: why.to_string(),
    };
    if !(200..300).contains(&status) {
        return failed("failed");
    }
    match serde_json::from_str::<BargeRaw>(body) {
        Ok(raw) => BargeVerdict {
            id,
            stop: raw.stop,
            available: raw.available,
            why: raw.why,
        },
        Err(_) => failed("failed"),
    }
}

/// "Carry on", for an utterance that was not sent, and why.
pub(crate) fn not_sent(id: u64, why: &str) -> BargeVerdict {
    BargeVerdict {
        id,
        stop: false,
        available: true,
        why: why.to_string(),
    }
}

/// Sends utterance `id`'s first [`BARGE_CLIP`] (or all of it, if shorter)
/// to the PC at `base` as `source=barge_in`, and reads the answer. `base`
/// must already have passed `wake_audio_refusal` (loopback only). Held -
/// nothing sent - while the event stream is stale.
pub(crate) async fn post_barge_in(
    app: &AppHandle,
    base: &str,
    spec: hound::WavSpec,
    samples: &[i16],
    id: u64,
) -> BargeVerdict {
    if app.state::<crate::stream::StreamState>().link().stale {
        return not_sent(id, "held");
    }
    let per_ms = (spec.sample_rate as usize * spec.channels as usize) / 1000;
    let clip_len = (BARGE_CLIP.as_millis() as usize + 300) * per_ms.max(1);
    let clip = &samples[..samples.len().min(clip_len)];
    let wav = match crate::voice::server_wav(spec, clip) {
        Ok(wav) => wav,
        Err(_) => return not_sent(id, "failed"),
    };
    let Ok(client) = jarvis_client(Some(BARGE_TIMEOUT)) else {
        return not_sent(id, "failed");
    };
    let Ok(headers) = jarvis_headers(app) else {
        return not_sent(id, "failed");
    };
    let sent = client
        .post(format!(
            "{base}/api/voice/utterance?source=barge_in&mic=desktop"
        ))
        .headers(headers)
        .header("Content-Type", "audio/wav")
        .body(wav)
        .send()
        .await;
    match sent {
        Ok(response) => {
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            barge_answer(id, status, &body)
        }
        Err(_) => not_sent(id, "failed"),
    }
}

/// The Jarvis bar: check utterance `id` as an interruption (it has just
/// paused the reply). Sends nothing itself - the listener sends the clip
/// when it is long enough. Quickbar only (permissions/surfaces.toml, `voice`).
#[tauri::command]
pub fn judge_barge_in(id: u64) -> Result<(), String> {
    BARGE_WANTED.store(id, Ordering::Relaxed);
    Ok(())
}

/// What the PC's `/api/voice/status` says about the voice flow: its `flow`
/// block as is, or `null` from a PC without one (then nothing here is
/// used). Quickbar only: the Jarvis bar reads it to know whether it may ask
/// for barge-in checks and whether a "One moment." clip exists. A read.
#[tauri::command]
pub async fn get_voice_flow(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(FLOW_TIMEOUT))?
        .get(format!("{base}/api/voice/status"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| crate::commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    Ok(flow_answer(status, &body))
}

/// The `flow` block of a status answer, or `null`.
pub(crate) fn flow_answer(status: u16, body: &str) -> serde_json::Value {
    if !(200..300).contains(&status) {
        return serde_json::Value::Null;
    }
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("flow").cloned())
        .filter(|f| f.is_object())
        .unwrap_or(serde_json::Value::Null)
}

/// The "One moment." clip, `GET /api/voice/moment`, as a `data:audio/wav`
/// URI (the shape `speak_reply` returns). A 503 is the PC's own "none right
/// now", passed on as its sentence. Quickbar only.
#[tauri::command]
pub async fn get_voice_moment(app: AppHandle) -> Result<String, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(FLOW_TIMEOUT))?
        .get(format!("{base}/api/voice/moment"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| crate::commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    if !(200..300).contains(&status) {
        let body = response.text().await.unwrap_or_default();
        return Err(moment_refusal(status, &body));
    }
    let bytes = response
        .bytes()
        .await
        .map_err(|e| format!("could not read the \"One moment.\" clip: {e}"))?;
    if bytes.is_empty() {
        return Err("the PC sent an empty \"One moment.\" clip".to_string());
    }
    Ok(format!("data:audio/wav;base64,{}", BASE64.encode(&bytes)))
}

/// Why there is no clip, in the PC's words when it gave any.
pub(crate) fn moment_refusal(status: u16, body: &str) -> String {
    let why = serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| {
            v.get("why")
                .or_else(|| v.get("error"))
                .and_then(|w| w.as_str())
                .map(str::to_string)
        })
        .filter(|w| !w.trim().is_empty());
    match (status, why) {
        (_, Some(why)) => why,
        (404, None) => "This PC's Jarvis has no \"One moment.\" clip yet.".to_string(),
        (code, None) => format!("the PC answered HTTP {code} for the \"One moment.\" clip"),
    }
}

/// How long the end of a clip was quiet: `waited_ms` for push-to-talk,
/// "from the moment the speech detector last heard speech to the moment the
/// clip is sent" (section 17, 2). The same loudness rule as the listener:
/// a 30 ms window is speech when it is louder than three times the quietest
/// window in the clip, within [`crate::voice::start_threshold`]'s bounds.
/// `None` when nothing in the clip was loud enough to be speech.
pub(crate) fn trailing_quiet(spec: hound::WavSpec, samples: &[i16]) -> Option<Duration> {
    let per_ms = (spec.sample_rate as usize * spec.channels.max(1) as usize) / 1000;
    let window = (30 * per_ms).max(1);
    let levels: Vec<f32> = samples.chunks(window).map(crate::voice::rms).collect();
    let floor = levels.iter().copied().fold(f32::INFINITY, f32::min);
    if !floor.is_finite() {
        return None;
    }
    let bar = crate::voice::start_threshold(floor);
    let last_loud = levels.iter().rposition(|&l| l >= bar)?;
    let quiet_windows = levels.len() - 1 - last_loud;
    Some(Duration::from_millis((quiet_windows * 30) as u64))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(n: u64) -> Duration {
        Duration::from_millis(n)
    }

    #[test]
    fn the_bar_is_told_once_after_half_a_second_of_speech() {
        assert!(!onset_due(ms(499), false));
        assert!(onset_due(ms(500), false));
        assert!(!onset_due(ms(900), true));
    }

    #[test]
    fn the_clip_goes_after_two_seconds_or_when_the_speech_ends_and_only_if_asked() {
        assert!(!clip_due(ms(1999), true, false, false));
        assert!(clip_due(ms(2000), true, false, false));
        assert!(clip_due(ms(900), true, false, true));
        assert!(!clip_due(ms(5000), false, false, true));
        assert!(!clip_due(ms(5000), true, true, true));
    }

    #[test]
    fn only_the_asked_utterance_is_checked() {
        let a = next_utterance_id();
        let b = next_utterance_id();
        assert!(b > a && a > 0);
        judge_barge_in(b).unwrap();
        assert!(barge_wanted(b));
        assert!(!barge_wanted(a));
        assert!(!barge_wanted(0));
    }

    #[test]
    fn the_answer_is_read_and_anything_else_carries_on() {
        let v = barge_answer(
            4,
            200,
            r#"{"stop": true, "available": true, "source": "barge_in", "why": "owner_voice"}"#,
        );
        assert_eq!(
            (v.id, v.stop, v.available, v.why.as_str()),
            (4, true, true, "owner_voice")
        );
        let off = barge_answer(
            4,
            200,
            r#"{"stop": false, "available": false, "why": "off"}"#,
        );
        assert!(!off.stop && !off.available);
        // An older route: the usual utterance reply, `stop` means the same.
        let old = barge_answer(4, 200, r#"{"ok": false, "text": "", "stop": true}"#);
        assert!(old.stop && old.available);
        for (code, body) in [(500, "{}"), (200, "not json"), (404, "")] {
            let v = barge_answer(4, code, body);
            assert!(!v.stop, "{code} {body}");
            assert_eq!(v.why, "failed");
        }
    }

    #[test]
    fn the_flow_block_or_nothing() {
        assert_eq!(
            flow_answer(200, r#"{"flow": {"available": true}}"#)["available"],
            true
        );
        assert!(flow_answer(200, r#"{"gate": {}}"#).is_null());
        assert!(flow_answer(200, r#"{"flow": 3}"#).is_null());
        assert!(flow_answer(503, r#"{"flow": {}}"#).is_null());
    }

    #[test]
    fn no_clip_is_said_in_the_pcs_words() {
        assert_eq!(
            moment_refusal(503, r#"{"available": false, "why": "switched off"}"#),
            "switched off"
        );
        assert!(moment_refusal(404, "").contains("no \"One moment.\" clip"));
        assert!(moment_refusal(500, "").contains("500"));
    }

    fn spec() -> hound::WavSpec {
        hound::WavSpec {
            channels: 1,
            sample_rate: 16_000,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        }
    }

    #[test]
    fn the_quiet_at_the_end_is_measured() {
        let loud: Vec<i16> = (0..16_000)
            .map(|i| if i % 2 == 0 { 8000 } else { -8000 })
            .collect();
        let mut clip = vec![20i16; 4_800];
        clip.extend(&loud);
        clip.extend(vec![20i16; 9_600]); // 600 ms of near-silence
        let q = trailing_quiet(spec(), &clip).unwrap();
        assert!(q >= ms(570) && q <= ms(630), "{q:?}");
        assert!(trailing_quiet(spec(), &vec![0i16; 16_000]).is_none());
        assert!(trailing_quiet(spec(), &[]).is_none());
    }
}
