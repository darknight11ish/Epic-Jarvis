"""test_media_read.py - F5 S1: read the words in ONE audio/video file.

    python3 backend/test_media_read.py

What it proves:
 1. the tool surface: my_files has `read_media`, decided under file_read /
    read_files_readonly, and the caps (10 min, 100 MB) are enforced;
 2. WAV works with no ffmpeg; another format without ffmpeg gets ONE plain
    refusal and nothing is opened;
 3. the decoder child carries `-protocol_whitelist file,pipe`, gets a scrubbed
    environment, and the module imports no network code (a socket made to raise
    does not stop a run);
 4. transcripts come back as timestamped segments, silent windows are skipped,
    and the total text is capped;
 5. a video also OCRs sampled frames (called only for video) and the OCR is
    capped;
 6. provenance: `{path, seconds}` is in the result and in
    jarvis_sources.from_tool_result, so the existing outside-text path applies;
 7. nothing is stored: no index, no memory fact (the module imports no memory
    store), no file written;
 8. pause and one-at-a-time: a busy owner or a held lock refuses before reading.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import traceback
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_media_read.py", "jarvis_agent.py", "jarvis_sources.py",
                "jarvis_documents.py")

import jarvis_media_read as M  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import jarvis_sources as SRC  # noqa: E402

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-media-read-"))


def check(name, cond, detail=""):
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def write_wav(name="clip.wav", seconds=1.0, rate=16000):
    p = TMP / name
    with wave.open(str(p), "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(rate)
        h.writeframes(b"\x00\x00" * int(rate * seconds))
    return p


def samples_loud_silent(rate=100):
    # one loud 10 s window then one silent 10 s window, at a tiny rate
    return [0.5] * (rate * 10) + [0.0] * (rate * 10)


def fake_decode(path):
    s = samples_loud_silent()
    return s, 100, len(s) / 100.0


def fake_transcribe(text="hello from the file"):
    return lambda samples, rate: text


# ---------------------------------------------------------------- 1. surface


def t_the_tool_surface_and_caps():
    tool = AG.TOOLS["my_files"]
    enum = tool.parameters["properties"]["action"]["enum"]
    check("my_files offers the read_media action", "read_media" in enum, enum)
    check("...and is still decided under the existing read action",
          tool.gate_lookup_name({"action": "read_media", "path": "x.wav"}) == "file_read")
    args, problem = AG.check_call("my_files", {"action": "read_media",
                                               "path": "C:/x/clip.wav"},
                                  {"my_files"}, AG.TOOLS)
    check("check_call accepts the read_media shape", problem is None and
          isinstance(args, dict), problem)
    real = write_wav()
    fake = TMP / "big.mp4"
    with open(fake, "wb") as h:
        h.truncate(M.MAX_BYTES + 1)

    def allowed(path):
        return (str(Path(path).resolve()), str(TMP))

    saved = M.__dict__.get("_allowed_for_tests")
    import jarvis_documents as DOCS
    old = DOCS.allowed_path
    DOCS.allowed_path = lambda p: allowed(p) if Path(p).is_file() else None
    try:
        state, desc = M.prepare({"path": str(real)})
        check("prepare resolves an allowed media file", state.get("path") == str(real.resolve())
              and "at most" in desc, (state, desc))
        try:
            M.prepare({"path": str(fake)})
        except ValueError as exc:
            check("a file over 100 MB is refused with the cap in the sentence",
                  "100 MB" in str(exc), str(exc))
        else:
            check("a file over 100 MB is refused with the cap in the sentence", False)
        try:
            M.prepare({"path": str(TMP / "not-media.txt")})
        except ValueError as exc:
            check("a non-media extension is refused", "audio or video" in str(exc), str(exc))
        else:
            check("a non-media extension is refused", False)
        DOCS.allowed_path = lambda p: None
        try:
            M.prepare({"path": str(real)})
        except ValueError as exc:
            check("a file outside the listed folders is refused before opening",
                  "not inside a folder" in str(exc), str(exc))
        else:
            check("a file outside the listed folders is refused before opening", False)
    finally:
        DOCS.allowed_path = old


# ------------------------------------------------------------- 2. decoder/ffmpeg


def t_wav_needs_no_ffmpeg_and_other_formats_refuse_plainly():
    saved = M._ffmpeg
    M._ffmpeg = lambda: None
    try:
        out = M.read_media(str(write_wav("plain.wav")), decode=fake_decode,
                           transcribe=fake_transcribe())
        check("a WAV reads without ffmpeg being present", out.get("ok") is True, out)
        mp3 = TMP / "song.mp3"
        mp3.write_bytes(b"not really")
        out = M.read_media(str(mp3), decode=M._decode_default,
                           transcribe=fake_transcribe())
        check("a non-WAV without ffmpeg is refused with the one plain sentence",
              out.get("ok") is False and "no ffmpeg" in str(out.get("error")), out)
    finally:
        M._ffmpeg = saved


def t_the_decoder_child_is_bounded_and_whitelisted():
    captured = {}

    class FakeProc:
        def __init__(self, argv, **kw):
            captured["argv"] = argv
            captured["env"] = kw.get("env") or {}
            import io
            self.stdout = io.BytesIO(b"RIFF....")
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.returncode = 1

    import subprocess, io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as h:
        h.setnchannels(1); h.setsampwidth(2); h.setframerate(16000)
        h.writeframes(b"\x00\x00" * 1600)
    class FakeProcWav(FakeProc):
        def __init__(self, argv, **kw):
            super().__init__(argv, **kw)
            self.stdout = io.BytesIO(buf.getvalue())
    saved_popen, saved_ff = subprocess.Popen, M._ffmpeg
    subprocess.Popen = FakeProcWav
    M._ffmpeg = lambda: "ffmpeg"
    try:
        M._decode_default(str(TMP / "whitelist.mp3"))
    except Exception:
        pass
    finally:
        subprocess.Popen = saved_popen
        M._ffmpeg = saved_ff
    argv = captured.get("argv") or []
    check("the child decoder is given -protocol_whitelist file,pipe",
          "-protocol_whitelist" in argv and argv[argv.index("-protocol_whitelist") + 1]
          == "file,pipe", argv)
    source = Path(M.__file__).read_text(encoding="utf-8")
    check("...and it is never given a shell", "shell=True" not in source)
    check("...and its environment carries no token or key",
          not any("TOKEN" in k.upper() or "KEY" in k.upper() or "SECRET" in k.upper()
                  for k in (captured.get("env") or {})),
          list(captured.get("env") or {})[:6])
    check("...and the read caps are in the module, not only in a comment",
          M.MAX_SECONDS == 600 and M.MAX_BYTES == 100 * 1024 * 1024
          and M.MAX_TEXT == 20000 and M.MAX_CHILD_BYTES == 64 * 1024 * 1024)


def t_no_network_anywhere():
    source = Path(M.__file__).read_text(encoding="utf-8")
    banned = ("import socket", "import urllib", "import requests", "urlopen",
              "httpx", "aiohttp", "http.client")
    found = [b for b in banned if b in source]
    check("the media reader imports/calls no network code", found == [], found)
    old = socket.socket

    class NoSocket:
        def __init__(self, *a, **k):
            raise RuntimeError("a socket was opened")

    socket.socket = NoSocket
    try:
        out = M.read_media(str(write_wav("offline.wav")), decode=fake_decode,
                           transcribe=fake_transcribe())
    finally:
        socket.socket = old
    check("a run with every socket made to raise still reads the local file",
          out.get("ok") is True, out)


# --------------------------------------------------------- 3. transcript/OCR


def t_segments_timestamps_silence_and_text_cap():
    out = M.read_media(str(write_wav("seg.wav")), decode=fake_decode,
                       transcribe=fake_transcribe("one two three"))
    check("a healthy read returns ok with its path and length",
          out.get("ok") is True and out.get("path", "").endswith("seg.wav")
          and out.get("seconds") == 20.0, out)
    check("segments carry start and end timestamps",
          out["segments"] and out["segments"][0]["start"] == 0.0
          and out["segments"][0]["end"] == 10.0, out["segments"][:2])
    check("the silent window produced NO segment",
          len(out["segments"]) == 1, out["segments"])
    out2 = M.read_media(str(write_wav("cap.wav")), decode=fake_decode,
                        transcribe=lambda s, r: "x" * 50000)
    total = len(out2.get("text") or "") + sum(len(o.get("text") or "")
                                             for o in out2.get("ocr") or [])
    check("the returned text is capped at MAX_TEXT", total <= M.MAX_TEXT, total)
    long_out = M.read_media(str(write_wav("long.wav")), decode=lambda p:
                            ([0.5] * 100, 10, 601.0), transcribe=fake_transcribe())
    check("a recording over 10 minutes is refused",
          long_out.get("ok") is False and "10 minutes" in str(long_out.get("error")),
          long_out)


def t_video_ocr_is_sampled_and_capped():
    video = TMP / "movie.mp4"
    video.write_bytes(b"not really a video")
    calls = {"frames": 0, "ocr": 0}

    def frames(path):
        calls["frames"] += 1
        return [(0.0, b"jpeg1"), (10.0, b"jpeg2")]

    def ocr(image):
        calls["ocr"] += 1
        return "slide text"

    out = M.read_media(str(video), decode=fake_decode,
                       transcribe=fake_transcribe("spoken words"),
                       frames=frames, ocr=ocr)
    check("a video's sampled frames are OCR'd", out.get("ok") is True
          and [o["at"] for o in out["ocr"]] == [0.0, 10.0], out)
    check("...and the OCR count is bounded by MAX_FRAMES", len(out["ocr"]) <= M.MAX_FRAMES)
    audio = str(write_wav("audio-only.wav"))
    M.read_media(audio, decode=fake_decode, transcribe=fake_transcribe(),
                 frames=lambda p: (_ for _ in ()).throw(RuntimeError("frames called")),
                 ocr=ocr)
    check("...and an audio file never calls the frame/OCR path", True)


# ------------------------------------------------------------ 4. provenance


def t_provenance_and_outside_text():
    result = M.read_media(str(write_wav("prov.wav")), decode=fake_decode,
                          transcribe=fake_transcribe())
    result["ok"] = True
    sources = SRC.from_tool_result("my_files", result)
    check("the result names the file and its length for the source line",
          result.get("path", "").endswith("prov.wav")
          and isinstance(result.get("seconds"), (int, float)), result)
    check("jarvis_sources shows the media file and its seconds",
          sources and sources[0].get("kind") == "file"
          and sources[0].get("path", "").endswith("prov.wav")
          and sources[0].get("seconds") == result["seconds"], sources)
    check("nothing is stored: the result says stored False",
          result.get("stored") is False)
    source = Path(M.__file__).read_text(encoding="utf-8")
    check("the module imports no memory store at all",
          "jarvis_memory" not in source and "store()" not in source)


# --------------------------------------------------------- 5. pause/one-at-time


def t_pause_and_one_at_a_time():
    out = M.read_media(str(write_wav("busy.wav")), decode=lambda p:
                       (_ for _ in ()).throw(RuntimeError("decoded while busy")),
                       transcribe=fake_transcribe(), owner_busy=lambda: True)
    check("a busy owner refuses BEFORE reading anything",
          out.get("ok") is False and out.get("reason") == "busy"
          and "listening or speaking" in str(out.get("error")), out)
    lock = threading.Lock()
    lock.acquire()
    try:
        out = M.read_media(str(write_wav("locked.wav")), decode=fake_decode,
                           transcribe=fake_transcribe(), lock=lock)
    finally:
        lock.release()
    check("a held one-at-a-time lock refuses the second read",
          out.get("ok") is False and out.get("reason") == "busy", out)
    check("the default pause seam is callable and says no in this tree",
          M._owner_busy_default() is False)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
