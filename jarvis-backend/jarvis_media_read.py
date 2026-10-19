"""jarvis_media_read.py - read the words in ONE audio or video file, locally.

F5's smallest slice S1 (2026-10-18, `docs/MEDIA-READ-DESIGN.md`): a read-only
read of one media file that is already inside a folder on the owner's "Folders
Jarvis may look in" list. It returns a bounded transcript with timestamps, and
for a video a few sampled frames' on-screen text. It stores NOTHING: no index,
no memory fact, no file. S2 (a searchable index) is a separate owner switch and
is not built here.

WHAT IT REUSES, NEVER A NEW MODEL

  * Speech-to-text: the existing sherpa-onnx Parakeet TDT model through
    `jarvis_speech._transcribe()` (English-only; the model is already on disk).
  * On-screen text: the existing `jarvis_ocr.read_text()` (Windows' own OCR; no
    model download). A WAV needs no decoder; every other format needs the local
    `ffmpeg` already on the PC - if it is missing, the plain refusal says so and
    nothing is read.
  * The outside-text rules: the caller (`jarvis_agent.TOOLS["my_files"]`) marks
    the result as outside text; this module only returns text with `{path,
    seconds}` provenance in the result.

HONEST LIMITS

  * English speech only, segment-level timestamps, no diarization, no summary.
  * One file, at most 10 minutes and 100 MB; at most ~20,000 characters of text.
  * Only files inside the owner's listed folders; links are resolved by the
    existing `jarvis_documents.allowed_path()` rule (hidden folders/protected
    places refused) before this module is called.
  * A video's PICTURES are not understood: frames are only OCR'd for visible
    text, one every 10 seconds. Vision is not part of S1.
  * The only new prerequisite is ffmpeg, for anything that is not a WAV. It is
    run as a CHILD process with `-protocol_whitelist file,pipe` (no network
    protocols), a scrubbed environment, a wall-clock timeout and a bounded
    stdout, and it never sees a secret in its environment.
  * Live voice pause: a caller may pass `owner_busy=`; the default looks for a
    live "the owner is talking" answer in the voice modules and otherwise says
    no. The chat turn itself cannot run at the same time as another chat turn,
    and one media read at a time is enforced here.

Standard library only. No network. No model is loaded at import time.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

MEDIA_TOOL = "media_read"
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma")
VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v")
MEDIA_EXTS = AUDIO_EXTS + VIDEO_EXTS

MAX_SECONDS = 600                    # 10 minutes, the S1 cap
MAX_BYTES = 100 * 1024 * 1024        # 100 MB, the S1 cap
MAX_TEXT = 20000                     # characters returned in total
MAX_CHILD_BYTES = 64 * 1024 * 1024   # a decoder that floods the pipe is stopped
WINDOW_SECONDS = 10.0                # transcript windows (and frame sampling)
MAX_FRAMES = 60                      # 10 minutes at one frame per 10 s
SILENCE_RMS = 0.003                  # below this a window carries no speech
CHILD_TIMEOUT = 180.0

#: One media read at a time (the STT model peaks about 1.2 GB). Tests may
#: replace this with a lock they hold to prove the guard.
READ_LOCK = threading.Lock()

BUSY_WORDS = ("Not now: Jarvis is listening or speaking, so this recording was "
              "not opened. Ask again when the conversation is quiet.")
NO_FFMPEG = ("This PC has no ffmpeg, so this file's sound cannot be read. A WAV "
             "file needs no ffmpeg; an MP3, M4A or video does.")


class Refused(Exception):
    """One plain sentence, and nothing else."""


# --------------------------------------------------------------------------
#   Where the file is - the existing folder rule, called from the tool
# --------------------------------------------------------------------------


def prepare(args: dict):
    """(state, the card/tool description) for `my_files` action `read_media`.
    Raises ValueError with one plain sentence - the agent turns that into a
    tool result the model can read and retry from."""
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("say which recording or video file to read - its full path")
    ext = Path(path.strip()).suffix.lower()
    if ext not in MEDIA_EXTS:
        raise ValueError("that is not an audio or video file this reader knows "
                         "(wav, mp3, m4a, aac, flac, ogg, opus, wma, mp4, mkv, "
                         "mov, webm, avi, m4v)")
    try:
        import jarvis_documents as DOCS
        got = DOCS.allowed_path(path.strip())
    except Exception as exc:                      # noqa: BLE001
        raise ValueError(f"the file list could not be read ({type(exc).__name__}), "
                         f"so nothing was opened")
    if not got:
        raise ValueError("that file is not inside a folder on your list, so it "
                         "was not opened")
    real = got[0]
    if not os.path.isfile(real):
        raise ValueError("that file is not there any more, so nothing was read")
    try:
        size = os.path.getsize(real)
    except OSError as exc:
        raise ValueError(f"that file could not be read ({type(exc).__name__})")
    if size > MAX_BYTES:
        raise ValueError("that file is bigger than 100 MB, which is this "
                         "reader's limit, so nothing was read")
    return {"path": real}, (f"Read the words in one recording or video (at most "
                            f"{MAX_SECONDS // 60} minutes): {real}")


# --------------------------------------------------------------------------
#   The child decoder - the only outside dependency (ffmpeg), bounded
# --------------------------------------------------------------------------


def _ffmpeg() -> Optional[str]:
    try:
        import shutil
        return shutil.which("ffmpeg")
    except Exception:
        return None


def _child_env() -> dict:
    """A scrubbed environment: the project's own child allow-list when it is
    there, otherwise PATH only. No token, key or Jarvis setting is passed."""
    try:
        import jarvis_child_env
        return jarvis_child_env.inherited()
    except Exception:
        keep = {}
        for name in ("PATH", "SYSTEMROOT", "WINDIR"):
            value = os.environ.get(name)
            if value:
                keep[name] = value
        return keep


def _run_child(argv: list) -> bytes:
    """Run one decoder command to completion with a timeout and a bounded
    stdout. It never gets a shell, and the caller's arguments include
    `-protocol_whitelist file,pipe`, so a playlist or reference cannot make it
    reach a network protocol."""
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=_child_env(), creationflags=flags)
    except Exception as exc:                      # noqa: BLE001
        raise Refused(f"the decoder could not start ({type(exc).__name__}), so "
                      f"nothing was read.")
    deadline = time.monotonic() + CHILD_TIMEOUT
    chunks, size = [], 0
    try:
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                raise Refused("the decoder took too long and was stopped, so "
                              "nothing was read.")
            block = proc.stdout.read(65536)
            if not block:
                break
            size += len(block)
            if size > MAX_CHILD_BYTES:
                proc.kill()
                raise Refused("the decoder produced more data than this reader "
                              "allows, so nothing was read.")
            chunks.append(block)
    finally:
        try:
            proc.stdout.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:                         # noqa: BLE001
            try:
                proc.kill()
            except Exception:
                pass
    if proc.returncode not in (0, None):
        raise Refused("the decoder could not read this file, so nothing was read.")
    return b"".join(chunks)


def _decode_default(path: str):
    """(samples, rate, seconds) for one media file. WAV is read in-process;
    every other format is decoded by the local ffmpeg as a bounded child."""
    ext = Path(path).suffix.lower()
    if ext == ".wav":
        try:
            with wave.open(path, "rb") as handle:
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                rate = handle.getframerate()
                raw = handle.readframes(handle.getnframes())
        except Exception as exc:                  # noqa: BLE001
            raise Refused(f"that WAV could not be read ({type(exc).__name__}), so "
                          f"nothing was read.")
        try:
            import numpy as np
        except Exception as exc:                  # noqa: BLE001
            raise Refused(f"the sound could not be read ({type(exc).__name__}).")
        if width == 2:
            pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif width == 4:
            pcm = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        elif width == 1:
            pcm = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            raise Refused("this WAV's sample size is not one Jarvis reads.")
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1)
        return pcm, int(rate or 16000), len(pcm) / float(rate or 16000)
    exe = _ffmpeg()
    if not exe:
        raise Refused(NO_FFMPEG)
    import io
    data = _run_child([exe, "-nostdin", "-v", "error",
                       "-protocol_whitelist", "file,pipe",
                       "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                       "-f", "wav", "pipe:1"])
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            rate = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            raw = handle.readframes(handle.getnframes())
    except Exception:                             # noqa: BLE001
        raise Refused("the decoder's sound was not the shape Jarvis reads, so "
                      "nothing was read.")
    try:
        import numpy as np
    except Exception as exc:                      # noqa: BLE001
        raise Refused(f"the sound could not be read ({type(exc).__name__}).")
    pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0 if width == 2 \
        else np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)
    return pcm, int(rate or 16000), len(pcm) / float(rate or 16000)


def _transcribe_default(samples, rate: int) -> str:
    """The existing local speech-to-text model; empty when it is not set up."""
    try:
        import jarvis_speech
        return str(jarvis_speech._transcribe(samples, rate) or "").strip()
    except Exception:
        return ""


def _frames_default(path: str) -> list:
    """[(seconds, JPEG bytes)] - one frame every 10 s, at most 60."""
    exe = _ffmpeg()
    if not exe:
        return []
    data = _run_child([exe, "-nostdin", "-v", "error",
                       "-protocol_whitelist", "file,pipe",
                       "-i", path, "-vf", f"fps=1/{int(WINDOW_SECONDS)}",
                       "-frames:v", str(MAX_FRAMES),
                       "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"])
    frames, marker = [], b"\xff\xd8"
    # MJPEG stream: split on every JPEG start marker.
    starts = []
    index = data.find(marker)
    while index != -1:
        starts.append(index)
        index = data.find(marker, index + 2)
    for number, start in enumerate(starts, start=0):
        end = starts[number + 1] if number + 1 < len(starts) else len(data)
        if end > start:
            frames.append((number * WINDOW_SECONDS, data[start:end][:2 * 1024 * 1024]))
    return frames


def _ocr_default(image: bytes) -> str:
    try:
        import jarvis_ocr
        got = jarvis_ocr.read_text(image)
        return str(got.get("text") or "").strip() if isinstance(got, dict) else ""
    except Exception:
        return ""


def _owner_busy_default() -> bool:
    """Is the owner in a live voice turn right now? This tree has no single
    public "talking now" flag; the seam checks the voice modules' own
    documented functions if a later slice adds one, and otherwise says no."""
    try:
        import jarvis_voice_flow
        for name in ("owner_talking", "is_listening", "listening_now"):
            fn = getattr(jarvis_voice_flow, name, None)
            if callable(fn):
                return bool(fn())
    except Exception:
        pass
    try:
        import jarvis_speech
        for name in ("owner_talking", "is_listening", "listening_now"):
            fn = getattr(jarvis_speech, name, None)
            if callable(fn):
                return bool(fn())
    except Exception:
        pass
    return False


def _windows(samples, rate: int) -> list:
    """(start_seconds, end_seconds, the samples) for energy-marked windows."""
    step = max(1, int(rate * WINDOW_SECONDS))
    out = []
    for start in range(0, len(samples), step):
        piece = samples[start:start + step]
        if len(piece) < step // 2:
            continue
        try:
            peak = max(abs(float(x)) for x in piece[:: max(1, len(piece) // 2000)])
        except Exception:
            peak = 0.0
        out.append((start / float(rate), min(len(samples), start + step) / float(rate),
                    piece, peak))
    return out


# --------------------------------------------------------------------------
#   The read
# --------------------------------------------------------------------------


def read_media(path, *, decode: Optional[Callable] = None,
               transcribe: Optional[Callable] = None,
               frames: Optional[Callable] = None,
               ocr: Optional[Callable] = None,
               owner_busy: Optional[Callable] = None,
               lock=None) -> dict:
    """Read one media file into bounded text. Always returns a dict.

    `decode`, `transcribe`, `frames` and `ocr` are seams: the default ones use
    the local model/ffmpeg/OCR, and the suite injects fakes so no model is
    needed. `owner_busy` pauses (refuses) while the owner is in a live voice
    turn; `lock` enforces one read at a time.
    """
    path = str(path or "")
    ext = Path(path).suffix.lower()
    busy = owner_busy or _owner_busy_default
    try:
        if busy():
            return {"ok": False, "path": path, "reason": "busy", "error": BUSY_WORDS}
    except Exception:
        pass
    one = lock if lock is not None else READ_LOCK
    got_lock = one.acquire(blocking=False)
    if not got_lock:
        return {"ok": False, "path": path, "reason": "busy", "error": BUSY_WORDS}
    try:
        return _read_locked(path, ext, decode or _decode_default,
                            transcribe or _transcribe_default,
                            frames or _frames_default, ocr or _ocr_default)
    finally:
        try:
            one.release()
        except Exception:
            pass


def _read_locked(path: str, ext: str, decode: Callable, transcribe: Callable,
                 frames: Callable, ocr: Callable) -> dict:
    try:
        if not os.path.isfile(path):
            raise Refused("That file is not there any more, so nothing was read.")
        if os.path.getsize(path) > MAX_BYTES:
            raise Refused("That file is bigger than 100 MB, so nothing was read.")
        samples, rate, seconds = decode(path)
        if seconds > MAX_SECONDS:
            raise Refused("That recording is longer than 10 minutes, which is "
                          "this reader's limit, so nothing was read.")
        if not samples:
            raise Refused("No sound was found in that file, so nothing was read.")
        segments, used = [], 0
        for start, end, piece, peak in _windows(samples, rate):
            if peak < SILENCE_RMS:
                continue
            text = str(transcribe(piece, rate) or "").strip()
            if not text:
                continue
            left = MAX_TEXT - used
            if left <= 0:
                break
            segments.append({"start": round(start, 2), "end": round(end, 2),
                             "text": text[:left]})
            used += len(text[:left])
        if not segments:
            raise Refused("No speech was recognised in that file, so there is no "
                          "transcript to show.")
        ocr_parts = []
        if ext in VIDEO_EXTS:
            try:
                for at, image in frames(path)[:MAX_FRAMES]:
                    text = str(ocr(image) or "").strip()
                    if text and used < MAX_TEXT:
                        piece = text[: MAX_TEXT - used]
                        ocr_parts.append({"at": round(float(at), 2), "text": piece})
                        used += len(piece)
            except Refused:
                ocr_parts = []
            except Exception:
                ocr_parts = []
        words = ("Read the transcript of one recording or video on this PC. The "
                 "words are the file's own sound, not a summary; on-screen text "
                 "is read where there is any.")
        return {"ok": True, "path": path, "seconds": round(float(seconds), 2),
                "segments": segments,
                "text": "\n".join(seg["text"] for seg in segments)[:MAX_TEXT],
                "ocr": ocr_parts[:MAX_FRAMES], "words": words,
                "english_only": True, "stored": False}
    except Refused as exc:
        return {"ok": False, "path": path, "error": str(exc)}
    except Exception as exc:                      # noqa: BLE001
        return {"ok": False, "path": path,
                "error": f"This file could not be read ({type(exc).__name__}), so "
                         f"nothing was read."}
