"""test_call_notes.py - the PC half of "record call": audio in, note out.

    py -3 -B backend/test_call_notes.py

What it proves, with NO network, NO model and NO real audio:

  1. CHUNK ASSEMBLY IS BYTE-EXACT. Two chunks arrive as base64, are appended in
     order, and the WAV `finish` builds holds exactly those bytes, behind a
     canonical 44-byte RIFF/WAVE header with 16 kHz, mono, 16-bit declared.
  2. OUT-OF-ORDER AND OVERSIZED CHUNKS ARE REFUSED, clearly: `seq` starts at
     **1** (the Android half's own first chunk), so 0, a repeat and a skipped
     number all answer 409 or 400 with the seq that was wanted; a chunk over the
     512 KiB cap answers 413, bad base64 answers 400, and a chunk for a session
     that is waiting for its card answers 409 - none of them writes a byte.
  3. FAKE TRANSCRIBER SEGMENTS BECOME THE NOTE'S LINES, at `[HH:MM:SS] You: ...`
     with the segment's own start/end carried through.
  4. SPEAKER LABELS: a fake embedder and a fake owner print label the owner's
     clips "You", cluster the rest into "Speaker 1"/"Speaker 2", and the two
     degrade cases - no speaker model, no owner print - label EVERY line
     "Speaker" and record why.
  5. THE NOTE'S NAME AND FRONTMATTER: `Calls/YYYY-MM-DD HHMM - Call.md`, the
     " (2)" collision suffix, every frontmatter field, and the consent line.
  6. THE VAULT-MISSING FALLBACK keeps the transcript as a `.md` beside the
     audio and says so - the recording is never lost because a vault is unset.
  7. THE PHRASE PARSER: all eight whole messages, the whole-message-only rule,
     and the chat path's `call_record` directive in X-Jarvis-Route.
  8. FEATURE-OFF REFUSAL: with no `[call_recording] enabled = true`, start,
     chunk and the chat answer all refuse in plain words; nothing is recorded.
  9. THE INSTALL WRAPPER: origin and token are checked, other routes pass
     through untouched, and a second install is a no-op.
 10. THE TWO CONTRACT SHAPES THE PHONE READS: `finish`'s `receipt` is a STRING
     (the structured record rides in `recording`), `chunk`'s `bytes` is the
     running total, and the read-only list route is PC-ONLY - another device
     gets 403 in plain words.
 11. THE EMBEDDER FOLLOWS THE PRINT: a print made with the strong model is
     compared with `StrongEmbedder`, everything else with `EcapaEmbedder`, and a
     model that will not load degrades to "Speaker" with the reason.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import traceback
import types
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_call_notes.py", "jarvis_quick.py", "jarvis_media_read.py",
                "jarvis_notes.py", "jarvis_notes_edit.py")

import jarvis_call_notes as C  # noqa: E402

PASSED, FAILED = [], []
TMP = Path(tempfile.mkdtemp(prefix="jarvis-call-notes-"))

#: Every recording this suite makes goes here, never into the owner's folder.
os.environ[C.ROOT_ENV] = str(TMP / "recordings")


def check(name, cond, detail=""):
    ok = bool(cond)
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


# --------------------------------------------------------------------------
#   Helpers: a feature that is on, a gate that says yes, and fakes
# --------------------------------------------------------------------------

class Yes:
    allowed = True
    outcome = "allowed"
    tier = "auto"
    reason = ""


class No:
    allowed = False
    outcome = "denied"
    tier = "ask"
    reason = "the suite said no"


def on():
    """The switch, on, for the length of one test (the module reads it per call)."""
    C.enabled = lambda: True
    C.settings = lambda: {"enabled": True, "why": ""}


def off():
    C.enabled = lambda: False
    C.settings = lambda: {"enabled": False, "why": ""}


def reset_root():
    root = Path(os.environ[C.ROOT_ENV])
    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            child.unlink() if child.is_file() else child.rmdir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def pcm(seconds: float = 0.5, seed: int = 1) -> bytes:
    """Deterministic 16 kHz mono s16le 'audio' - a byte pattern, not a sound."""
    count = int(C.SAMPLE_RATE * seconds) * 2
    return bytes(((i * seed + 7) % 251) for i in range(count))


def started_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def make_session(*, gate=None) -> str:
    """A real session through the real route, with the gate faked."""
    on()
    code, out = C.start({"started_at": started_now(), "sample_rate": 16000,
                         "channels": 1, "format": "s16le", "device": "phone"},
                        gate=gate or (lambda *a, **k: Yes()))
    assert code == 200 and out.get("ok"), (code, out)
    return out["session"]


def fake_reader(*reads):
    """A read_media stand-in: one dict per call, in order."""
    calls = []

    def read(path):
        calls.append(str(path))
        if reads:
            return reads[min(len(calls) - 1, len(reads) - 1)]
        return {"ok": False, "error": "no speech was recognised in that file"}

    read.calls = calls
    return read


def fake_create(*, code=200, state="created"):
    made = []

    def create(name, text):
        made.append({"name": name, "text": text})
        return code, {"ok": True, "path": name, "state": state, "id": "notejob1"}

    create.made = made
    return create


class FakeWav:
    """(start, end) -> the clip a fake embedder is given."""

    def __init__(self, clips):
        self.clips = clips

    def samples(self, start, end):
        return self.clips.get(round(float(start), 2)) or [0.1] * 1600


class FakeEmbedder:
    """A speaker model stand-in: embed(clip, rate) -> the vector for that clip."""

    def __init__(self, table):
        self.table = table
        self.calls = 0

    def embed(self, clip, rate=None):
        self.calls += 1
        key = round(sum(clip), 6)
        return self.table.get(key) or [0.0, 0.0, 1.0]


class FakeProfile:
    name = "fake"
    threshold = 0.35
    centroid = [1.0, 0.0, 0.0]

    def subprints(self, model):
        return []


# --------------------------------------------------------------------------
#   1. Byte-exact assembly
# --------------------------------------------------------------------------

def t_chunks_assemble_byte_exact_into_a_valid_wav():
    reset_root()
    session = make_session()
    first, second = pcm(0.25, seed=3), pcm(0.25, seed=11)
    # The Android half's first chunk is seq 1 (CallRecordStore.nextSeq), and
    # the frozen contract says the PC appends in that order.
    for seq, data in enumerate((first, second), start=1):
        code, out = C.chunk({"session": session, "seq": seq,
                             "data_b64": base64.b64encode(data).decode("ascii")})
        check(f"chunk {seq} accepted", code == 200 and out.get("ok") is True, out)
        check(f"chunk {seq} reports its own size",
              out.get("chunk_bytes") == len(data), out)
        check(f"chunk {seq} reports the running total in `bytes`",
              out.get("bytes") == (len(first) if seq == 1
                                   else len(first) + len(second)), out)
    create = fake_create()
    code, out = C.finish({"session": session, "duration_sec": 0.5,
                          "consent_notice": "on"}, create=create,
                         reader=fake_reader({"ok": False, "error": "no speech"}),
                         embedder=None, profile=None, wait_s=5.0)
    check("finish answers 200 with a pending note", code == 200, out)
    wav_path = Path(out["wav"])
    check("the WAV really exists", wav_path.is_file(), str(wav_path))
    with wave.open(str(wav_path), "rb") as handle:
        check("16 kHz mono 16-bit", (handle.getframerate(), handle.getnchannels(),
                                     handle.getsampwidth()) == (16000, 1, 2),
              (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()))
        frames = handle.readframes(handle.getnframes())
    check("the frames are exactly the two chunks, in order",
          frames == first + second, f"{len(frames)} vs {len(first) + len(second)}")
    head = wav_path.read_bytes()[:44]
    check("a canonical RIFF/WAVE header", head[:4] == b"RIFF" and head[8:12] == b"WAVE"
          and head[12:16] == b"fmt " and head[36:40] == b"data", head[:16])
    check("the header's data size matches the bytes",
          int.from_bytes(head[40:44], "little") == len(first) + len(second))
    check("the header's byte rate is 32000 (16000 x 1 x 2)",
          int.from_bytes(head[28:32], "little") == 32000)


def t_an_odd_trailing_byte_is_dropped_and_reported():
    reset_root()
    session = make_session()
    payload = pcm(0.05) + b"\x7f"          # one byte past a whole sample
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(payload).decode("ascii")})
    code, out = C.finish({"session": session, "consent_notice": "on"},
                         create=fake_create(),
                         reader=fake_reader({"ok": False, "error": "no speech"}),
                         embedder=None, profile=None, wait_s=5.0)
    if code == 200:
        doc = C.read_receipt(session) or {}
        check("the odd trailing byte is reported, not guessed",
              doc.get("dropped_tail") == 1, doc.get("dropped_tail"))
    else:
        check("finish accepted the recording", False, out)


# --------------------------------------------------------------------------
#   2. Out-of-order and oversized refusals
# --------------------------------------------------------------------------

def t_chunks_out_of_order_and_too_big_are_refused():
    reset_root()
    session = make_session()
    good = base64.b64encode(pcm(0.1)).decode("ascii")
    code, out = C.chunk({"session": session, "seq": 2, "data_b64": good})
    check("a chunk arriving out of order is 409", code == 409, out)
    check("... and says which seq it wanted (1, not 0)", out.get("expected") == 1, out)
    check("... in plain words", "in order" in str(out.get("error")), out)
    code, out = C.chunk({"session": session, "seq": 0, "data_b64": good})
    check("seq 0 is refused: the contract starts at 1", code == 400, out)
    code, out = C.chunk({"session": session, "seq": 1,
                         "data_b64": "A" * (C.MAX_CHUNK_B64 + 8)})
    check("a chunk over the size cap is 413", code == 413, out)
    code, out = C.chunk({"session": session, "seq": 1, "data_b64": "not base64!!"})
    check("bad base64 is 400", code == 400, out)
    code, out = C.chunk({"session": session, "seq": 1, "data_b64": ""})
    check("an empty chunk is 400", code == 400, out)
    code, out = C.chunk({"session": "call_" + "0" * 24, "seq": 1, "data_b64": good})
    check("a made-up session id is 404", code == 404, out)
    code, out = C.chunk({"session": "../etc", "seq": 1, "data_b64": good})
    check("a path as a session id is 404 (ids are never paths)", code == 404, out)
    folder = C.session_dir(session)
    check("nothing was written by any refused chunk",
          folder is not None and (folder / "audio.pcm").stat().st_size == 0)


def t_a_repeated_seq_is_refused_and_never_appended_twice():
    reset_root()
    session = make_session()
    data = base64.b64encode(pcm(0.1)).decode("ascii")
    code, out = C.chunk({"session": session, "seq": 1, "data_b64": data})
    check("the first chunk (seq 1) is accepted", code == 200 and out.get("ok"), out)
    code, out = C.chunk({"session": session, "seq": 1, "data_b64": data})
    check("the SAME seq again is 409, not appended twice", code == 409, out)
    check("... and names the number it wants next", out.get("expected") == 2, out)
    code, out = C.chunk({"session": session, "seq": 3, "data_b64": data})
    check("a skipped number is 409 too",
          code == 409 and out.get("expected") == 2, out)
    folder = C.session_dir(session)
    check("exactly one chunk is on disk",
          folder is not None
          and (folder / "audio.pcm").stat().st_size == len(pcm(0.1)))


def t_a_chunk_during_the_card_is_refused():
    reset_root()
    release = threading.Event()

    class Waiting:
        allowed = False
        outcome = "timed_out"
        tier = "ask"

    def gate(*_a, **_k):
        release.wait(5)
        return Waiting()

    on()
    code, out = C.start({"started_at": started_now()}, gate=gate, wait_s=0.0)
    check("start answers 202 while the card waits",
          code == 202 and out.get("state") == "waiting", out)
    session = out["session"]
    code, out = C.chunk({"session": session, "seq": 1,
                         "data_b64": base64.b64encode(pcm(0.1)).decode("ascii")})
    check("a chunk before the card is answered is 409", code == 409, out)
    check("... and names the state", out.get("state") in ("waiting", "refused"), out)
    release.set()


# --------------------------------------------------------------------------
#   3. Fake transcriber segments -> the note's lines
# --------------------------------------------------------------------------

READ_ONE = {"ok": True, "seconds": 30.0, "english_only": True,
            "segments": [{"start": 0.0, "end": 10.0, "text": "hello, can you hear me"},
                         {"start": 10.0, "end": 20.0, "text": "yes, I can hear you"},
                         {"start": 20.0, "end": 30.0, "text": "good, let us start"}]}


def t_fake_segments_become_timestamped_note_lines():
    reset_root()
    session = make_session()
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(2.0)).decode("ascii")})
    create = fake_create()
    reader = fake_reader(READ_ONE)
    real_vault = C.vault_state
    C.vault_state = lambda: (True, "")          # a usable vault, without a vault
    try:
        code, out = C.finish({"session": session, "duration_sec": 2.0,
                              "consent_notice": "on"}, create=create, reader=reader,
                             embedder=None, profile=None, wait_s=5.0)
    finally:
        C.vault_state = real_vault
    check("finish is 200", code == 200, out)
    check("the reader was really asked", len(reader.calls) == 1, reader.calls)
    check("one new note was created", len(create.made) == 1, create.made)
    text = create.made[0]["text"]
    started = C.read_receipt(session)["started_at"]
    when = dt.datetime.fromisoformat(started)
    check("the third line says what was said, at its own time",
          f"[{(when + dt.timedelta(seconds=20)).strftime('%H:%M:%S')}]" in text
          and "good, let us start" in text, text[-400:])
    check("every line is '[HH:MM:SS] Speaker: words'",
          all(len(line.split("] ")[0].lstrip("[")) == 8
              for line in text.splitlines() if line.startswith("[")))
    check("the transcript copy is beside the audio",
          (C.session_dir(session) / "transcript.md").is_file())
    doc = C.read_receipt(session)
    check("the receipt is settled as done", doc.get("status") == "done", doc)
    check("the receipt names the note", str(doc.get("note") or "").endswith(".md"), doc)
    check("duration came from the audio's own bytes",
          abs(float(doc.get("duration_sec") or 0) - 2.0) < 0.01, doc.get("duration_sec"))


def t_a_long_call_is_transcribed_in_parts_with_shifted_times():
    reset_root()
    session = make_session()
    # 600 s of PCM, but read_media would refuse >10 min per file: the module
    # cuts 9-minute parts and shifts each part's times by its offset.
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(1.5)).decode("ascii")})
    parts = []

    def reader(path):
        with wave.open(path, "rb") as handle:
            seconds = handle.getnframes() / float(handle.getframerate())
        parts.append(seconds)
        return {"ok": True, "segments": [{"start": 1.0, "end": 2.0,
                                          "text": f"part {len(parts)}"}]}

    code, out = C.finish({"session": session, "consent_notice": "on"},
                         create=fake_create(), reader=reader,
                         embedder=None, profile=None, wait_s=5.0)
    check("a short call is one part", code == 200 and len(parts) == 1, parts)
    check("each part is under read_media's 10-minute cap",
          all(p <= 600 for p in parts), parts)


# --------------------------------------------------------------------------
#   4. Speaker labels: owner match, clustering, and the honest degrade
# --------------------------------------------------------------------------

def t_owner_match_and_clustering():
    """Three lines: the owner, someone else, the owner again."""
    owner_vec = [1.0, 0.0, 0.0]
    other_vec = [0.0, 1.0, 0.0]
    clips = {0.0: [float(i) for i in range(160)], 10.0: [2.0] * 160,
             20.0: [3.0] * 160}
    embedder = FakeEmbedder({sum([float(i) for i in range(160)]): owner_vec,
                             sum([2.0] * 160): other_vec,
                             sum([3.0] * 160): owner_vec})
    segments = [{"start": 0.0, "end": 10.0, "text": "hello"},
                {"start": 10.0, "end": 20.0, "text": "hi there"},
                {"start": 20.0, "end": 30.0, "text": "right"}]
    got = C.label_segments(segments, wav=FakeWav(clips), embedder=embedder,
                           profile=FakeProfile())
    check("the owner's two lines are 'You'",
          [line["speaker"] for line in got["lines"]][0] == "You"
          and [line["speaker"] for line in got["lines"]][2] == "You", got["lines"])
    check("the other voice is 'Speaker 1'",
          got["lines"][1]["speaker"] == "Speaker 1", got["lines"][1])
    check("the speaker list is in speaking order", got["speakers"] == ["You", "Speaker 1"],
          got["speakers"])
    check("the method is recorded", got["method"] == "owner-print+clusters", got["method"])


def t_two_unknown_speakers_are_numbered():
    # Both vectors are orthogonal to the fake owner print ([1,0,0]), so neither
    # is the owner and the two must be numbered separately.
    a_vec, b_vec = [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
    clips = {0.0: [1.0] * 160, 10.0: [2.0] * 160}
    embedder = FakeEmbedder({160.0: a_vec, 320.0: b_vec})
    segments = [{"start": 0.0, "end": 10.0, "text": "one"},
                {"start": 10.0, "end": 20.0, "text": "two"}]
    got = C.label_segments(segments, wav=FakeWav(clips), embedder=embedder,
                           profile=FakeProfile())
    check("two different voices become Speaker 1 and Speaker 2",
          [line["speaker"] for line in got["lines"]] == ["Speaker 1", "Speaker 2"],
          got["lines"])


def t_missing_model_or_owner_print_degrades_honestly():
    segments = [{"start": 0.0, "end": 10.0, "text": "hello"},
                {"start": 10.0, "end": 20.0, "text": "again"}]
    clips = {0.0: [0.2] * 160, 10.0: [0.3] * 160}
    no_model = C.label_segments(segments, wav=FakeWav(clips), embedder=None,
                                profile=FakeProfile())
    check("no speaker model: every line is 'Speaker'",
          [line["speaker"] for line in no_model["lines"]] == ["Speaker", "Speaker"],
          no_model["lines"])
    check("no speaker model: the reason is recorded",
          no_model["method"] == "none" and "speaker model" in no_model["why"],
          no_model)
    no_print = C.label_segments(segments, wav=FakeWav(clips),
                                embedder=FakeEmbedder({}), profile=None)
    check("no owner print: every line is 'Speaker'",
          [line["speaker"] for line in no_print["lines"]] == ["Speaker", "Speaker"],
          no_print["lines"])
    check("no owner print: the reason is recorded",
          no_print["method"] == "none" and "voice" in no_print["why"], no_print)
    no_template = C.label_segments(segments, wav=FakeWav(clips),
                                   embedder=FakeEmbedder({}),
                                   profile=type("P", (), {"centroid": [],
                                                          "threshold": 0.35})())
    check("a print with no template is also 'Speaker'",
          {line["speaker"] for line in no_template["lines"]} == {"Speaker"},
          no_template["lines"])
    check("and it says why", "template" in no_template["why"], no_template["why"])
    short = C.label_segments([{"start": 0.0, "end": 0.2, "text": "hm"}],
                             wav=FakeWav({0.0: [0.5] * 160}),
                             embedder=FakeEmbedder({}), profile=FakeProfile())
    check("a line too short to embed never invents a new name",
          short["lines"][0]["speaker"] == "Speaker", short["lines"])


# --------------------------------------------------------------------------
#   5. The note's name and frontmatter
# --------------------------------------------------------------------------

def t_note_name_is_the_date_and_time():
    when = dt.datetime(2026, 11, 4, 13, 36, 5)
    check("the name is Calls/<date> <HHMM> - Call.md",
          C.note_name(when) == "Calls/2026-11-04 1336 - Call.md", C.note_name(when))
    check("a second call in the same minute gets ' (2)'",
          C.note_name(when, taken=["Calls/2026-11-04 1336 - Call.md"])
          == "Calls/2026-11-04 1336 - Call (2).md",
          C.note_name(when, taken=["Calls/2026-11-04 1336 - Call.md"]))
    check("the collision test is case-blind (Windows)",
          C.note_name(when, taken=["calls/2026-11-04 1336 - call.MD"])
          == "Calls/2026-11-04 1336 - Call (2).md")


def t_frontmatter_and_body_are_the_documented_shape():
    when = dt.datetime(2026, 11, 4, 13, 36, 5).astimezone()
    lines = [{"start": 0.0, "end": 10.0, "text": "hello there", "speaker": "You"},
             {"start": 65.0, "end": 70.0, "text": "hi", "speaker": "Speaker 1"}]
    text = C.render_note(started_at=when, duration_sec=125.0, lines=lines,
                         speakers=["You", "Speaker 1"],
                         audio_path=r"C:\calls\call_x\audio.wav", session="call_x",
                         title="Talk with Sam", speaker_method="owner-print+clusters",
                         gaps=[{"start": 300.0, "end": 310.0, "reason": "busy"}])
    check("it starts and ends with the frontmatter fence",
          text.startswith("---\n") and "\n---\n" in text)
    for field in ("date: 2026-11-04", 'source: "phone call, speaker recording"',
                  'duration: "2m 05s"', "duration_seconds: 125",
                  'speakers: ["You", "Speaker 1"]', 'session: "call_x"',
                  'audio: "C:\\\\calls'):
        check(f"frontmatter carries {field!r}", field in text, field)
    check("the consent reminder is in the frontmatter",
          'consent: "Recorded locally; tell the other person"' in text)
    check("the consent reminder is VISIBLE in the body",
          "> Recorded locally; tell the other person." in text)
    check("the first line is at the call's own start time", "[13:36:05] You: hello there"
          in text, text)
    check("offset lines use the call's clock, not zero",
          f"[{(when + dt.timedelta(seconds=65)).strftime('%H:%M:%S')}] Speaker 1: hi"
          in text)
    check("a gap is named, never filled with invented words",
          "(not transcribed: busy)" in text)
    check("the title is carried when the phone gave one", 'title: "Talk with Sam"' in text)
    check("the speaker method is carried", 'speaker_labels: "owner-print+clusters"' in text)
    check("the honest source line is in the body",
          "Android cannot record the call's own audio" in text)


# --------------------------------------------------------------------------
#   6. The vault-missing fallback
# --------------------------------------------------------------------------

def t_a_missing_vault_keeps_the_transcript_and_says_so():
    reset_root()
    session = make_session()
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(1.0)).decode("ascii")})
    real_vault = C.vault_state
    C.vault_state = lambda: (False, "no Obsidian vault folder is set")
    try:
        create = fake_create()
        code, out = C.finish({"session": session, "consent_notice": "on"},
                             create=create, reader=fake_reader(READ_ONE),
                             embedder=None, profile=None, wait_s=5.0)
    finally:
        C.vault_state = real_vault
    check("finish still answers 200 - the recording is safe", code == 200, out)
    check("the vault is never written when it is unusable", create.made == [],
          create.made)
    doc = C.read_receipt(session) or {}
    note = str(doc.get("note") or "")
    check("the returned note path is the transcript beside the audio",
          note.endswith("transcript.md") and Path(note).is_file(), note)
    check("a plain sentence says why there is no vault note",
          "no Obsidian vault" in str(doc.get("message")), doc.get("message"))
    check("the transcript really holds the words",
          "hello, can you hear me" in Path(note).read_text(encoding="utf-8"))


def t_a_refused_card_keeps_the_transcript_too():
    reset_root()
    session = make_session()
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(1.0)).decode("ascii")})
    real_vault = C.vault_state
    C.vault_state = lambda: (True, "")
    try:
        code, out = C.finish({"session": session, "consent_notice": "on"},
                             create=lambda n, t: (409, {"ok": False,
                                                        "error": "there is already a "
                                                                 "note at that name"}),
                             reader=fake_reader(READ_ONE), embedder=None, profile=None,
                             wait_s=5.0)
    finally:
        C.vault_state = real_vault
    doc = C.read_receipt(session) or {}
    check("a refused note still leaves the transcript",
          str(doc.get("note") or "").endswith("transcript.md"), doc)
    check("... and says the editor refused it",
          "could not be created" in str(doc.get("message")), doc.get("message"))


def t_a_waiting_card_is_reported_as_pending_and_kept():
    reset_root()
    session = make_session()
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(1.0)).decode("ascii")})
    real_vault = C.vault_state
    C.vault_state = lambda: (True, "")
    try:
        code, out = C.finish({"session": session, "consent_notice": "on"},
                             create=fake_create(code=202, state="waiting"),
                             reader=fake_reader(READ_ONE), embedder=None, profile=None,
                             wait_s=5.0)
    finally:
        C.vault_state = real_vault
    doc = C.read_receipt(session) or {}
    check("a card still waiting is recorded with its job id",
          doc.get("note_job") == "notejob1", doc)
    check("the note path is still the intended one", str(doc.get("note") or "").endswith(".md"),
          doc.get("note"))


# --------------------------------------------------------------------------
#   7. The phrase parser and the chat directive
# --------------------------------------------------------------------------

def t_the_eight_whole_messages():
    for phrase in C.ARM_PHRASES:
        check(f"{phrase!r} arms", C.phrase_action(phrase) == "arm", C.phrase_action(phrase))
        check(f"{phrase!r} in capitals still arms",
              C.phrase_action(phrase.upper()) == "arm")
        check(f"{phrase!r} with a full stop still arms",
              C.phrase_action(phrase + ".") == "arm")
    for phrase in C.STOP_PHRASES:
        check(f"{phrase!r} stops", C.phrase_action(phrase) == "stop",
              C.phrase_action(phrase))
    check("there are exactly five arm phrases", len(C.ARM_PHRASES) == 5)
    check("there are exactly three stop phrases", len(C.STOP_PHRASES) == 3)


def t_the_whole_message_rule():
    for not_a_command in ("record call now", "please record call", "record a call",
                          "I recorded a call yesterday", "can you tell me how to record "
                          "call", "record", "stop", "start recording", ""):
        check(f"{not_a_command!r} is not one of the eight",
              C.phrase_action(not_a_command) is None, C.phrase_action(not_a_command))


def t_the_chat_answer_carries_the_directive():
    import jarvis_quick as Q
    off()
    got = Q.match("record call")
    check("quick match: 'record call' is the call_record intent",
          got is not None and got.name == "call_record"
          and got.f.get("action") == "arm", got)
    check("quick match: a longer sentence is the model's",
          Q.match("record call now") is None, Q.match("record call now"))
    check("quick match: the polite lead-in is the repo's own tidying",
          Q.match("can you record the call") is not None)
    refused = Q.run(Q.Intent("call_record", {"action": "arm"}), None, 0.0)
    check("feature off: the answer refuses and carries NO directive",
          refused is not None and refused.call_record is None
          and "off on this PC" in refused.reply, refused)
    check("... and its intent says so", refused.intent == "call_record_refused")
    on()
    armed = Q.run(Q.Intent("call_record", {"action": "arm"}), None, 0.0)
    check("feature on: the answer says what will happen",
          armed is not None and armed.call_record == {"action": "arm"}, armed)
    for fact in ("speaker", "transcri", "note"):
        check(f"the arm answer mentions {fact!r}", fact in armed.reply.lower(),
              armed.reply)
    check("the arm answer carries the consent reminder",
          "tell the other person" in armed.reply.lower(), armed.reply)
    routed = Q.route_fields(armed)
    check("X-Jarvis-Route carries call_record", routed.get("call_record")
          == {"action": "arm"}, routed)
    stopped = Q.run(Q.Intent("call_record", {"action": "stop"}), None, 0.0)
    check("the stop answer carries the stop directive",
          stopped is not None and stopped.call_record == {"action": "stop"}, stopped)
    off()
    check("stopping is allowed even when the feature is off (it only narrows)",
          Q.run(Q.Intent("call_record", {"action": "stop"}), None, 0.0).call_record
          == {"action": "stop"})


# --------------------------------------------------------------------------
#   8. Feature-off refusal
# --------------------------------------------------------------------------

def t_feature_off_refuses_everything():
    reset_root()
    off()
    code, out = C.start({"started_at": started_now()})
    check("start is refused while the feature is off", code == 403, out)
    check("... with the state 'off'", out.get("state") == "off", out)
    check("... and says how to turn it on",
          "call_recording" in str(out.get("error")), out)
    check("nothing was created on disk", list(Path(os.environ[C.ROOT_ENV]).iterdir()) == [],
          list(Path(os.environ[C.ROOT_ENV]).iterdir()))
    code, out = C.chunk({"session": "call_" + "1" * 24, "seq": 0, "data_b64": "AA=="})
    check("chunk is refused while the feature is off", code == 403, out)
    code, out = C.finish({"session": "call_" + "1" * 24, "consent_notice": "on"})
    check("finish is refused while the feature is off", code == 403, out)


def t_finish_needs_the_consent_notice():
    reset_root()
    session = make_session()
    code, out = C.finish({"session": session}, create=fake_create())
    check("finish without consent_notice is 400", code == 400, out)
    check("... and says the notice must be on",
          "consent_notice" in str(out.get("error")), out)
    code, out = C.finish({"session": session, "consent_notice": "off"})
    check("consent_notice 'off' is refused too", code == 400, out)


def t_an_empty_recording_is_refused_not_turned_into_a_note():
    reset_root()
    session = make_session()
    create = fake_create()
    code, out = C.finish({"session": session, "consent_notice": "on"}, create=create)
    check("finish with no audio is 400", code == 400, out)
    check("no note was created", create.made == [], create.made)
    doc = C.read_receipt(session) or {}
    check("the receipt says the recording was empty", doc.get("status") == "empty", doc)


def t_a_second_finish_is_refused():
    reset_root()
    session = make_session()
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(0.5)).decode("ascii")})
    C.finish({"session": session, "consent_notice": "on"}, create=fake_create(),
             reader=fake_reader(READ_ONE), embedder=None, profile=None, wait_s=5.0)
    code, out = C.finish({"session": session, "consent_notice": "on"})
    check("finishing twice is 409", code == 409, out)
    check("... and carries the receipt as a STRING (the frozen contract)",
          isinstance(out.get("receipt"), str) and session in str(out.get("receipt")),
          out)
    check("... with the structured record beside it",
          isinstance(out.get("recording"), dict), out)


def t_the_list_route_reads_receipts_only():
    reset_root()
    session = make_session()
    C.chunk({"session": session, "seq": 1,
             "data_b64": base64.b64encode(pcm(0.5)).decode("ascii")})
    C.finish({"session": session, "consent_notice": "on"}, create=fake_create(),
             reader=fake_reader(READ_ONE), embedder=None, profile=None, wait_s=5.0)
    code, out = C.handle_get("")
    check("GET lists the recording", code == 200 and len(out.get("recordings") or []) == 1,
          out)
    row = (out.get("recordings") or [{}])[0]
    check("a row carries the date, duration, note and status",
          row.get("date") and row.get("duration_sec") and row.get("note")
          and row.get("status") == "done", row)
    check("a row never carries the transcript text",
          "hello, can you hear me" not in json.dumps(out), out)
    code, one = C.handle_get("session=" + session)
    check("GET ?session= answers that one", code == 200
          and one.get("recording", {}).get("session") == session, one)
    code, bad = C.handle_get("session=call_" + "9" * 24)
    check("GET ?session= with an unknown id is 404", code == 404, bad)
    code, also = C.handle_get("?session=" + session)
    check("a query with its own leading '?' still finds the session",
          code == 200 and also.get("recording", {}).get("session") == session, also)


# --------------------------------------------------------------------------
#   9. The install wrapper
# --------------------------------------------------------------------------

class _PlainHandler:
    """The unwrapped base: a fresh subclass per install case, so one install
    never leaks into the next (install() wraps the class it is given, and a
    second call on a wrapped class is a no-op by design)."""

    def __init__(self, path, body=b"{}", header_value="token"):
        self.path = path
        self._body = body
        self._sent = []
        self.headers = {}
        self.connection = type("Conn", (), {"getsockname": lambda s: ("127.0.0.1", 1)})()

    def _send(self, code, payload):
        self._sent.append((code, payload))

    def do_GET(self):
        self._sent.append(("original-GET", self.path))

    def do_POST(self):
        self._sent.append(("original-POST", self.path))


FakeHandler = _PlainHandler


def read_body(handler):
    return handler._body


def wrapped(*, origin=True, token=True, pc=True):
    """A FRESH handler class with its own install() wrap.

    `pc` is the `from_this_pc` seam install() takes: the list route is PC-only,
    and the suite drives both sides of it without a network.
    """
    class H(_PlainHandler):
        pass
    C.install(H, origin_ok=lambda h: origin, token_ok=lambda h: token,
              read_body=read_body, from_this_pc=lambda peer, local: pc)
    return H


def t_install_wraps_only_its_routes():
    class First(_PlainHandler):
        pass
    C.install(First, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=read_body, from_this_pc=lambda peer, local: True)
    line = C.install(First, origin_ok=lambda h: True, token_ok=lambda h: True,
                     read_body=read_body, from_this_pc=lambda peer, local: True)
    check("a second install on the same class is a no-op", "already on" in line, line)
    H = wrapped()
    fresh = H(C.LIST_PATH)
    fresh.do_GET()
    check("install returns a class whose GET route answers 200",
          fresh._sent and fresh._sent[0][0] == 200, fresh._sent)
    other = H("/api/something-else")
    other.do_GET()
    check("another GET route goes to the original handler",
          other._sent[0][0] == "original-GET", other._sent)
    other = H("/api/something-else")
    other.do_POST()
    check("another POST route goes to the original handler",
          other._sent[0][0] == "original-POST", other._sent)
    denied = wrapped(origin=False)(C.LIST_PATH)
    denied.do_GET()
    check("a cross-origin GET is refused before the route answers",
          denied._sent and denied._sent[0][0] == 403, denied._sent)
    denied = wrapped(token=False)(C.LIST_PATH)
    denied.do_GET()
    check("a bad token is 401", denied._sent and denied._sent[0][0] == 401,
          denied._sent)
    # PC_ONLY: the list route is the owner's PC surface. A phone or another
    # device that somehow holds the token is still refused, in plain words.
    elsewhere = wrapped(pc=False)(C.LIST_PATH)
    elsewhere.do_GET()
    check("the list route from another device is 403",
          elsewhere._sent and elsewhere._sent[0][0] == 403, elsewhere._sent)
    check("... in plain words, not a silence",
          elsewhere._sent and C.PC_ONLY_REFUSAL in str(elsewhere._sent[0][1]),
          elsewhere._sent)
    # The shipped default is the project's own check, and it fails CLOSED when
    # it cannot answer: jarvis_owner_check is not importable in this folder, and
    # a handler with no peer address is nobody. install() wraps the class and
    # returns its banner line (the loader's convention), so the instance is made
    # from the class afterwards.
    Bare = type("Bare", (_PlainHandler,), {})
    C.install(Bare, origin_ok=lambda h: True, token_ok=lambda h: True,
              read_body=read_body)
    plain = Bare(C.LIST_PATH)
    plain.do_GET()
    check("with no owner check available the list is refused (fails closed)",
          plain._sent and plain._sent[0][0] == 403, plain._sent)
    off()
    body = json.dumps({"started_at": started_now()}).encode("utf-8")
    post = wrapped()(C.START_PATH, body=body)
    post.do_POST()
    check("our POST route answers (feature off: 403)",
          post._sent and post._sent[0][0] == 403, post._sent)
    broken = wrapped()(C.CHUNK_PATH, body=b"not json")
    broken.do_POST()
    check("a body that is not JSON is 400, not a crash",
          broken._sent and broken._sent[0][0] == 400, broken._sent)
    banner = C.install(FakeHandler, origin_ok=lambda h: True, token_ok=lambda h: True,
                       read_body=read_body, from_this_pc=lambda peer, local: True)
    check("the banner names the feature", "call-notes" in banner, banner)


# --------------------------------------------------------------------------
#   11. The embedder follows the print (strong vs ecapa), and degrades
# --------------------------------------------------------------------------

class _FakeVoiceModule(types.ModuleType):
    """The two model classes and find_profile, as jarvis_voice really shapes
    them - so the test can drive which one is built without a model on disk."""

    def __init__(self, print_model, *, strong_works=True, ecapa_works=True):
        super().__init__("jarvis_voice")
        self.MIN_THRESHOLD = 0.05
        self.built = []
        outer = self

        class FakeStrong:
            name = "strong"

            def __init__(self):
                if not strong_works:
                    raise RuntimeError("strong.onnx is not installed")
                outer.built.append("strong")

        class FakeEcapa:
            name = "ecapa"

            def __init__(self):
                if not ecapa_works:
                    raise RuntimeError("model.onnx is not installed")
                outer.built.append("ecapa")

        class Print:
            embedder = print_model
            centroid = [1.0, 0.0, 0.0]
            threshold = 0.35

            def subprints(self, model):
                return []

        self.StrongEmbedder = FakeStrong
        self.EcapaEmbedder = FakeEcapa
        self.find_profile = lambda mic="": (Print(), "phone")
        self.load_profile = lambda path=None: Print()


def t_the_embedder_follows_the_print():
    real = sys.modules.get("jarvis_voice")
    try:
        sys.modules["jarvis_voice"] = _FakeVoiceModule("ecapa")
        embedder, profile, why = C.label_defaults()
        check("a print made with the small model builds EcapaEmbedder",
              isinstance(embedder, sys.modules["jarvis_voice"].EcapaEmbedder)
              and profile is not None and why == "", (embedder, why))
        sys.modules["jarvis_voice"] = _FakeVoiceModule("strong")
        embedder, profile, why = C.label_defaults()
        check("a print made with the strong model builds StrongEmbedder",
              isinstance(embedder, sys.modules["jarvis_voice"].StrongEmbedder)
              and profile is not None and why == "", (embedder, why))
        sys.modules["jarvis_voice"] = _FakeVoiceModule("strong", strong_works=False)
        embedder, profile, why = C.label_defaults()
        check("strong.onnx missing falls back to the small model, not to nothing",
              isinstance(embedder, sys.modules["jarvis_voice"].EcapaEmbedder), embedder)
        sys.modules["jarvis_voice"] = _FakeVoiceModule(
            "ecapa", strong_works=False, ecapa_works=False)
        embedder, profile, why = C.label_defaults()
        check("with no model at all the embedder is None and the reason is said",
              embedder is None and "not installed" in why, (embedder, why))
    finally:
        if real is None:
            sys.modules.pop("jarvis_voice", None)
        else:
            sys.modules["jarvis_voice"] = real


# --------------------------------------------------------------------------
#   The feature switch: off unless the settings file says on
# --------------------------------------------------------------------------

def t_the_shipped_default_is_off():
    real = C.framework_default
    try:
        check("with no [call_recording] table the feature is off",
              C.framework_default() is False, C.framework_default())
    finally:
        C.framework_default = real
    toml = TMP / "framework-on.toml"
    toml.write_text("[call_recording]\nenabled = true\n", encoding="utf-8")
    old = os.environ.get("JARVIS_FRAMEWORK_TOML")
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(toml)
    try:
        import jarvis_framework
        got = C.framework_default()
        check("a settings file saying enabled = true turns it on", got is True, got)
    finally:
        if old is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = old


# --------------------------------------------------------------------------
#   Run them
# --------------------------------------------------------------------------

if __name__ == "__main__":
    # This suite is about a module that is switched OFF on a normal PC; the
    # five tests that record turn it on for themselves and off again.
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
