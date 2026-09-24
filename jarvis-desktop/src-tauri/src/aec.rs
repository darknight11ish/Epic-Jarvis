//! Windows' own echo cancelling, for "hey Jarvis" listening while Jarvis
//! speaks.
//!
//! WHAT PROBLEM THIS SOLVES
//! While Jarvis reads an answer aloud, the microphone hears it too. Every
//! sentence of Jarvis's own voice is then sent to the server as a clip
//! (dropped there, but it drowns the owner's "hey Jarvis" or "stop" said over
//! the top of it). An *echo canceller* removes what the speakers are playing
//! from what the microphone hears, so the owner's voice is left.
//!
//! WHERE THE ECHO CANCELLER COMES FROM
//! Windows itself. A capture stream opened in the "communications" category
//! (the category calling apps use) gets the audio driver's - or, on recent
//! Windows 11, the system's own "Voice Clarity" - communications processing,
//! which on most machines includes acoustic echo cancellation. It uses what
//! the PC is playing as its reference, so it needs nothing from the page
//! that plays Jarvis's voice.
//!
//! WHY NOT A LIBRARY. `webrtc-audio-processing` (the WebRTC echo canceller)
//! builds C++ through meson at compile time, which this project cannot build
//! for the Windows target from its Linux checks, and it would need Jarvis's
//! own audio fed to it sample-accurately - but the reply is played by the
//! webview, not by Rust. The pure-Rust ports are young. Windows' own is
//! already on the machine and is what calling apps rely on.
//!
//! WHETHER IT IS REALLY ON. Not every machine has it. After opening the
//! stream, Windows is asked which effects are active on it
//! (`IAudioEffectsManager`, Windows 11) and this is used ONLY when acoustic
//! echo cancellation is listed and switched on. Anything else - an older
//! Windows, a driver without it, any error - and voice.rs uses the ordinary
//! capture exactly as before. So this can only ever add echo cancelling,
//! never take the old path away.
//!
//! NOT VERIFIED ON WINDOWS. It compiles against the Windows target from the
//! container (`cargo check --target x86_64-pc-windows-msvc`); it has not been
//! run on a Windows machine. Every failure falls back to the old capture.

use std::sync::mpsc;
use std::sync::{Arc, Mutex};

/// What an opened echo-cancelled capture looks like.
pub(crate) struct Opened {
    pub spec: hound::WavSpec,
}

/// Pumps the default communications microphone, echo-cancelled, into
/// `samples` until `stop` fires. Reports on `ready` exactly once: the format
/// when the stream is open AND Windows says echo cancelling is on, or why
/// not (and then returns without capturing).
#[cfg(windows)]
pub(crate) fn run(
    samples: Arc<Mutex<Vec<i16>>>,
    ready: mpsc::Sender<Result<Opened, String>>,
    stop: mpsc::Receiver<()>,
) {
    // SAFETY: every call below is a plain COM call on interfaces this
    // function created and holds for its whole life; the one raw buffer
    // (GetBuffer's) is read only for the frame count WASAPI gave with it and
    // released before the next call.
    let outcome = unsafe { imp::capture(&samples, &ready, &stop) };
    if let Err(e) = outcome {
        // Harmless when ready was already sent: the receiver only reads once.
        let _ = ready.send(Err(e));
    }
}

#[cfg(not(windows))]
pub(crate) fn run(
    _samples: Arc<Mutex<Vec<i16>>>,
    ready: mpsc::Sender<Result<Opened, String>>,
    _stop: mpsc::Receiver<()>,
) {
    let _ = ready.send(Err("echo cancelling is Windows-only".to_string()));
}

/// Converts one captured packet to i16, mono or not (kept interleaved, as the
/// cpal path keeps it - the WAV header carries the channel count).
pub(crate) fn to_i16(bytes: &[u8], float: bool, bits: u16) -> Vec<i16> {
    if float && bits == 32 {
        bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| {
                let v = f32::from_le_bytes(*b);
                (v.clamp(-1.0, 1.0) * i16::MAX as f32) as i16
            })
            .collect()
    } else if !float && bits == 16 {
        bytes
            .as_chunks::<2>()
            .0
            .iter()
            .map(|b| i16::from_le_bytes(*b))
            .collect()
    } else if !float && bits == 32 {
        bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| (i32::from_le_bytes(*b) >> 16) as i16)
            .collect()
    } else if !float && bits == 24 {
        bytes
            .as_chunks::<3>()
            .0
            .iter()
            .map(|b| (i32::from_le_bytes([0, b[0], b[1], b[2]]) >> 16) as i16)
            .collect()
    } else {
        Vec::new()
    }
}

#[cfg(windows)]
mod imp {
    use super::{to_i16, Opened};
    use std::sync::mpsc;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;
    use windows::Win32::Media::Audio::{
        eCapture, eCommunications, AudioCategory_Communications, AudioClientProperties,
        IAudioCaptureClient, IAudioClient2, IAudioEffectsManager, IMMDeviceEnumerator,
        MMDeviceEnumerator, AUDCLNT_BUFFERFLAGS_SILENT, AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMOPTIONS_NONE, AUDIO_EFFECT, AUDIO_EFFECT_STATE_ON, WAVEFORMATEX,
        WAVEFORMATEXTENSIBLE,
    };
    use windows::Win32::Media::KernelStreaming::{
        AUDIO_EFFECT_TYPE_ACOUSTIC_ECHO_CANCELLATION, WAVE_FORMAT_EXTENSIBLE,
    };
    use windows::Win32::Media::Multimedia::{
        KSDATAFORMAT_SUBTYPE_IEEE_FLOAT, WAVE_FORMAT_IEEE_FLOAT,
    };
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_ALL,
        COINIT_MULTITHREADED,
    };

    /// How long WASAPI buffers for us: the loop drains it every 10 ms.
    const BUFFER_100NS: i64 = 2_000_000; // 200 ms

    struct Com;
    impl Drop for Com {
        fn drop(&mut self) {
            // SAFETY: paired with the successful CoInitializeEx below.
            unsafe { CoUninitialize() };
        }
    }

    /// The effects Windows says are active on this stream include echo
    /// cancelling, switched on.
    unsafe fn echo_cancelling_on(client: &IAudioClient2) -> bool {
        let Ok(manager) = client.GetService::<IAudioEffectsManager>() else {
            return false; // older Windows: cannot know, so not used
        };
        let mut effects: *mut AUDIO_EFFECT = std::ptr::null_mut();
        let mut count: u32 = 0;
        if manager.GetAudioEffects(&mut effects, &mut count).is_err() || effects.is_null() {
            return false;
        }
        let list = std::slice::from_raw_parts(effects, count as usize);
        let on = list.iter().any(|e| {
            e.id == AUDIO_EFFECT_TYPE_ACOUSTIC_ECHO_CANCELLATION && e.state == AUDIO_EFFECT_STATE_ON
        });
        CoTaskMemFree(Some(effects as *const _));
        on
    }

    /// A WASAPI error, in words, prefixed with what was being tried.
    fn err(what: &'static str) -> impl Fn(windows::core::Error) -> String {
        move |e| format!("{what}: {e}")
    }

    pub(super) unsafe fn capture(
        samples: &Arc<Mutex<Vec<i16>>>,
        ready: &mpsc::Sender<Result<Opened, String>>,
        stop: &mpsc::Receiver<()>,
    ) -> Result<(), String> {
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(err("could not start COM"))?;
        let _com = Com;

        let enumerator: IMMDeviceEnumerator =
            CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL)
                .map_err(err("could not list the microphones"))?;
        let device = enumerator
            .GetDefaultAudioEndpoint(eCapture, eCommunications)
            .map_err(err("no communications microphone"))?;
        let client: IAudioClient2 = device
            .Activate(CLSCTX_ALL, None)
            .map_err(err("could not open the microphone"))?;
        let props = AudioClientProperties {
            cbSize: std::mem::size_of::<AudioClientProperties>() as u32,
            bIsOffload: false.into(),
            eCategory: AudioCategory_Communications,
            Options: AUDCLNT_STREAMOPTIONS_NONE,
        };
        client
            .SetClientProperties(&props)
            .map_err(err("could not ask for communications processing"))?;

        let format: *mut WAVEFORMATEX = client
            .GetMixFormat()
            .map_err(err("could not read the microphone's format"))?;
        let f = *format;
        let tag = f.wFormatTag as u32;
        let float = tag == WAVE_FORMAT_IEEE_FLOAT
            || (tag == WAVE_FORMAT_EXTENSIBLE
                && std::ptr::read_unaligned(std::ptr::addr_of!(
                    (*(format as *const WAVEFORMATEXTENSIBLE)).SubFormat
                )) == KSDATAFORMAT_SUBTYPE_IEEE_FLOAT);
        let channels = f.nChannels;
        let rate = f.nSamplesPerSec;
        let bits = f.wBitsPerSample;
        let block = f.nBlockAlign as usize;
        let init = client.Initialize(AUDCLNT_SHAREMODE_SHARED, 0, BUFFER_100NS, 0, format, None);
        CoTaskMemFree(Some(format as *const _));
        init.map_err(err("could not start the microphone"))?;
        if to_i16(&vec![0u8; block], float, bits).is_empty() {
            return Err(format!(
                "the microphone's format ({bits}-bit) is not one this reads"
            ));
        }

        if !echo_cancelling_on(&client) {
            return Err("Windows does not report echo cancelling on this microphone".to_string());
        }
        let capture: IAudioCaptureClient = client
            .GetService()
            .map_err(err("could not read from the microphone"))?;
        client
            .Start()
            .map_err(err("could not start the microphone"))?;

        let spec = hound::WavSpec {
            channels,
            sample_rate: rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        if ready.send(Ok(Opened { spec })).is_err() {
            let _ = client.Stop();
            return Ok(()); // the caller gave up waiting
        }

        loop {
            match stop.recv_timeout(Duration::from_millis(10)) {
                Ok(()) | Err(mpsc::RecvTimeoutError::Disconnected) => break,
                Err(mpsc::RecvTimeoutError::Timeout) => {}
            }
            loop {
                let next = capture
                    .GetNextPacketSize()
                    .map_err(err("the microphone stopped"))?;
                if next == 0 {
                    break;
                }
                let mut data: *mut u8 = std::ptr::null_mut();
                let mut frames: u32 = 0;
                let mut flags: u32 = 0;
                capture
                    .GetBuffer(&mut data, &mut frames, &mut flags, None, None)
                    .map_err(err("the microphone stopped"))?;
                let n = frames as usize * block;
                let chunk = if flags & (AUDCLNT_BUFFERFLAGS_SILENT.0 as u32) != 0 || data.is_null()
                {
                    vec![0i16; frames as usize * channels as usize]
                } else {
                    to_i16(std::slice::from_raw_parts(data, n), float, bits)
                };
                capture
                    .ReleaseBuffer(frames)
                    .map_err(err("the microphone stopped"))?;
                samples
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner())
                    .extend_from_slice(&chunk);
            }
        }
        let _ = client.Stop();
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::to_i16;

    #[test]
    fn packets_convert_like_the_cpal_path() {
        let f: Vec<u8> = [0.5f32, -1.0, 2.0]
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        assert_eq!(to_i16(&f, true, 32), vec![16383, -32767, 32767]);
        let s: Vec<u8> = [1234i16, -5].iter().flat_map(|v| v.to_le_bytes()).collect();
        assert_eq!(to_i16(&s, false, 16), vec![1234, -5]);
        let w: Vec<u8> = [0x0012_3400i32]
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect();
        assert_eq!(to_i16(&w, false, 32), vec![0x0012]);
        assert!(
            to_i16(&[0u8; 8], true, 64).is_empty(),
            "an unknown format is refused"
        );
    }
}
