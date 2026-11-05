"""jarvis_call_notes.py - record a phone call, transcribe it here, file it as a note.

THE OWNER'S REQUEST (2026-11-04, in their own words): "add the ability of jarvis
to record a call if I tell it a keyword 'record call' where it will record all
the audio, transcribe it, put a date and identify the speakers in the
transcription, and store all of it in a new obsidian note labeled with the date
and time" - the call being taken through the Android Jarvis app on their phone.

WHAT THIS MODULE IS: the PC half. The phone records; this assembles the audio,
transcribes it locally, labels who spoke, and creates ONE new Obsidian note
named for the date and time. It is one shipped module with four routes, wired
by `plugins/ready/call-notes` exactly like `jarvis_media_index` is, so it needs
no patch.

PLATFORM TRUTH - WHY THE PHONE RECORDS THROUGH ITS MICROPHONE (this must not
be contradicted in code or docs):

  * The call happens on the owner's phone, and his primary phone is a **Google
    Pixel 9**. This PC can neither see nor hear that call; it only receives the
    audio the phone sends.
  * Android does not let an ordinary app capture the call's OWN audio stream:
    `MediaRecorder.AudioSource.VOICE_CALL` is privileged, and a normal app
    asking for it gets silence or a `SecurityException`. There is no
    third-party route to the downlink/uplink mix.
  * So the PHONE lane records through the microphone with the call on speaker
    ("the speaker path"), and this module does everything after: chunk
    assembly, local transcription, speaker labelling, date/time, the note.
  * THE HONEST CONSEQUENCE, said plainly here and in docs/CALL-RECORDING.md:
    the far end is heard through the speaker and re-recorded by the phone's
    microphone, so it is quieter and noisier than a system recorder would give,
    and the words are less reliable than a recording of the call's own stream.
    Nothing here claims otherwise.
  * **No real call was driven on that phone by either lane.** The Pixel was not
    attached while this was built (the Android half's own pull request says the
    same), so the speaker path, how much of the far end it really catches, and
    how good the words are afterwards are **NOT-TESTABLE** until the owner's own
    field test. Nothing in this module claims otherwise.
  * If the phone's built-in call recorder exists and produces a file, importing
    that file is a later addition. It is NOT built here and is not claimed.

THE ROUTES (docs/JARVIS-API.md, "Call recording"; the Android lane is
written against this contract):

    POST /api/call/recording/start
         {"started_at": "2026-11-04T13:36:05-08:00", "sample_rate": 16000,
          "channels": 1, "format": "s16le", "device": "phone"}
      -> 200 {"ok": true, "session": "call_<24 hex>", "state": "recording"}
         202 {"ok": true, "session": ..., "state": "waiting"}   (a card is up)
         403 {"ok": false, "state": "off" | "refused", "error": <one sentence>}

    POST /api/call/recording/chunk
         {"session": "call_...", "seq": 1, "data_b64": "<base64 PCM>"}
      -> 200 {"ok": true, "session": ..., "seq": 1,
              "bytes": <every byte held now>, "chunk_bytes": <this chunk>}
         200 {"ok": true, ..., "chunk_bytes": 0, "already": true}
             (a seq BELOW the next one: already held, nothing written twice)
         409 {"ok": false, "error": ..., "expected": <next seq>}  (a GAP: seq above)
         413 {"ok": false, "error": ...}                          (too big)
      `seq` starts at **1** (the Android half's own first chunk is 1) and goes up
      by one; a failed send is retried with the SAME number. `bytes` is the
      running total the PC holds, which is what the phone reads back to tell a
      PC that is appending from one that answers 0 to every chunk.
      **A REPEATED (LOWER) SEQ IS NOT AN ERROR.** It is the one thing a crash
      leaves behind: the PC answered 200 and the phone died before it appended
      the number to `sent.txt`, so the retry asks for a chunk we already have.
      Answering 409 there (which this route did until 2026-11-05) retried the
      same number for ever and made the recording permanently unsendable. Only
      a seq ABOVE `expected` is a gap, and only a gap is a 409.

    POST /api/call/recording/finish
         {"session": "call_...", "duration_sec": 812.4,
          "title": "...", "consent_notice": "on"}
      -> 200 {"ok": true, "session": ..., "receipt": "<one line>",
              "note": "<vault path>" | "pending", "wav": "<path>",
              "recording": {...}}
      The WAV is assembled and the transcription starts on a daemon thread; the
      request itself never waits for the model. `consent_notice` must be the
      literal "on": it is the phone saying the notice was shown. **`receipt` is
      a STRING** - the frozen contract's own shape, and the only one the phone
      reads (`CallRecordWire.finished` takes `receipt` when it is a string); the
      structured session record rides in `recording`, and is what
      `GET /api/call/recording?session=` answers.

    GET /api/call/recording            -> {"ok": true, "recordings": [...]}
    GET /api/call/recording?session=ID -> {"ok": true, "recording": {...}}
      Read-only: the date, duration, note path, status and speaker list. Never
      the transcript text (the note holds the words; this route does not).
      **PC-only** - the repo's own rule for a route the phone has no use for,
      through `jarvis_owner_check.from_this_pc` exactly as `jarvis_media_index`
      does it: a request from another device is 403 in plain words. The three
      POST routes above are the phone's by necessity (it holds the microphone),
      which is the one deliberate departure, written down in
      docs/CALL-RECORDING.md.

    POST /api/call/recording/delete
         {"session": "call_..."}
      -> 200 {"ok": true, "state": "deleted", "removed": [...], "message": "..."}
         202 {"ok": true, "state": "waiting", "message": "..."}  (its card is up)
         403 {"ok": false, "state": "refused" | "off", "error": "..."}
         404 {"ok": false, "state": "unknown", "error": "..."}
         409 {"ok": false, "state": ..., "error": "..."}  (still running / transcribing)
      THE DELETE ROUTE, AND WHY IT IS A POST. This backend wraps `do_GET` and
      `do_POST` for every optional feature and has no `do_DELETE` anywhere
      (JARVIS-API section 112 says the same about the goals store): a second
      mechanism for one route would be a second thing to get wrong. So remove
      is a POST, exactly like `/api/goals/<id>/remove`.
      **PC-only** (the same `from_this_pc` check the list route uses - the phone
      never deletes anything on the PC), and behind ONE approval card of its
      own, `delete_call_recording`, tier `ask`: deleting the audio and the
      transcript cannot be undone. The delete runs on that card's worker, so a
      card still waiting answers 202 (the shape `start` already uses) and the
      recording is gone from the GET once it is approved. It removes the
      session's whole folder - `audio.pcm`, `audio.wav`, `transcript.md`,
      `receipt.json` and any `part-*.wav` - which is also the list's row. The
      Obsidian note, if one was written, is a document of its own and is NOT
      deleted here (that is the notes editor's own card and undo); the answer
      names the note so the owner knows what is left. It does not need the
      feature switch on: removing something is the safe direction, and an owner
      who has switched the feature off must still be able to delete what it
      already kept.

WHAT IT REUSES, AND WHERE IT DELIBERATELY ADDS NOTHING

  * Speech-to-text: `jarvis_media_read.read_media(path)`, which is the existing
    sherpa-onnx Parakeet TDT model in `jarvis_speech._transcribe()` (English
    only, segment-level start/end times already in its result). No second STT
    engine, no model download, no cloud. read_media's own cap is 10 minutes and
    100 MB per file, so a longer call is transcribed in 9-minute parts of the
    SAME wav and each part's times are shifted by its offset - one engine, a
    loop around it, nothing forked. Its per-segment `start`/`end` are what make
    speaker-labelling possible, so no helper was needed for that either.
  * The owner's voice: `jarvis_voice.find_profile()` / `load_profile()` and the
    embedder the print was made with - `EcapaEmbedder` (`model.onnx`) or, when
    the print says `strong`, `StrongEmbedder` (`strong.onnx`), both already on
    this PC under `<config dir>/voice-models/speaker/` - compared with
    `jarvis_voice.cosine()`. The voice modules are IMPORTED, never edited.
  * The note: `jarvis_notes_edit.handle_create()`, the editor's own public
    create path - so the vault/protected/hidden/collision checks, the File
    Guardian copy, the undo receipt and the ONE `edit_vault_note` card are the
    ones the owner already has. This module never writes into the vault itself.
    `jarvis_notes.obsidian_vault()` and `vault_problem()` decide whether a
    vault is usable, exactly as `jarvis_note_capture` does.
  * The audio: one WAV per recording under `<config dir>/call-recordings/
    <session>/`, next to `receipt.json` and `transcript.md`. Standard library
    only (`wave`), no ffmpeg, no new dependency in requirements.lock.

SPEAKER LABELS - HOW, AND WHEN IT REFUSES TO GUESS

  Match first, cluster second (the numbers are named constants, not buried):
  1. The clip's embedding is compared with the owner's enrolled print (its
     centroid and every sub-print, whichever scores highest) using the print's
     OWN threshold, clamped up to `jarvis_voice.MIN_THRESHOLD`. At or above it
     the line is "You".
  2. Every other line joins the cluster whose centroid is at or above
     `SPEAKER_MERGE_SIMILARITY`; otherwise it starts a cluster, up to
     `MAX_SPEAKERS`. A final merge pass joins clusters that similar, repeated
     until none are (the stop rule). Clusters are numbered "Speaker 1",
     "Speaker 2", ... in the order they first speak.
  3. A line shorter than `MIN_EMBED_SECONDS`, or one whose embedding is empty,
     carries the previous line's label (speaker continuity) and never invents a
     new one.
  4. If the speaker model is not installed, OR the owner's voice print is
     missing, EVERY line is "Speaker" and the note records which of the two was
     missing (`speaker_labels_why`). Never a guessed name, never "You" on a
     guess.

  A segment is the reader's own ~10-second window, so two people talking inside
  one window get one label. That is the existing reader's granularity and it is
  written in the docs rather than papered over.

THE NOTE (a NEW file, named for the date and time)

  `Calls/YYYY-MM-DD HHMM - Call.md` (a second call in the same minute gets
  " (2)", " (3)", ... - a new note is never an edit of an old one). YAML
  frontmatter: `date`, `started_at`, `duration`, `duration_seconds`, `source`
  ("phone call, speaker recording"), `speakers`, `audio` (the wav's path),
  `session`, `consent` ("Recorded locally; tell the other person"), `title`,
  `speaker_labels`, `speaker_labels_why`, `english_only`. Body: one heading,
  the consent reminder as a visible line, then `[HH:MM:SS] You: ...` per line -
  the time of day each line was said (the call's start plus the segment's
  offset).

  A CALL CAN RAISE TWO CARDS: the `record_call` card before any AUDIO is kept
  (the session's folder, its receipt and an empty `audio.pcm` are made before
  the card, so a crash cannot lose the first chunk - see "NO AUDIO BEFORE YES"
  below), and the notes editor's own `edit_vault_note` card before the note is
  written (a transcript is other people's words, so it is never a card-free
  write). Deleting a recording is a THIRD card, `delete_call_recording` - see
  the route table above.

  IF THE VAULT IS MISSING OR INVALID the transcript is STILL written, as
  `transcript.md` beside the audio in the config folder, and that path is
  returned with a plain sentence saying why the note was not made. The
  transcript is in fact always written there first, so a vault problem or a
  refused card can never lose a recording.

SAFETY AND WHAT THIS MODULE WILL NOT DO

  * Recording starts ONLY from the owner's own command: the keyword/the phone
    app asks `POST .../start`, and that route asks the approval gate under the
    action `record_call`. It never starts on boot, on a timer, or because
    something else asked. Nothing is recorded while the feature is off.
  * OFF BY DEFAULT. `[call_recording] enabled = false` in the shipped
    `jarvis-framework.toml`; a settings file with no `[call_recording]` table
    is off too. Turning it on is a hand edit of that one line and is recorded
    as the owner's choice (the same pattern `github_search` and `shell_exec`
    use: "off by default; there is no in-app switch").
  * The gate action is `record_call`, shipped at tier `ask` in
    `[autonomy.tiers]`. That is the conservative choice and it is documented:
    the owner-initiated note actions (`append_obsidian_daily`,
    `append_logseq_journal`) ship `auto`, but this one starts capturing OTHER
    PEOPLE'S speech, so it asks until the owner deliberately loosens it.
    `jarvis_gate.py` HAS a `_RISK` row for this name (added 2026-11-05, by this
    fix): `("yes", "local", ...)` - a recording changes nothing and can be
    deleted again, and nothing leaves this PC. Before that row the card carried
    the gate's generic unclassified warning, whose second half ("able to leave
    this PC") was wrong for this action.
  * NO AUDIO BEFORE YES, AND THE FOLDER IS NOT AUDIO. The session's folder,
    its `receipt.json` and an empty `audio.pcm` are created before the card, so
    a crash between the phone's first chunk and the approval cannot lose it;
    the card's refusal leaves that empty session behind (the delete route
    removes it). No audio byte is written until the card is approved
    (`chunk` answers 409 while the state is `waiting`).
  * The `consent_notice` field must be "on" or the recording is not finished -
    the phone says it showed the reminder, and the note carries the reminder
    too.
  * No network, no tunnel, no cloud, no model call to anywhere but the local
    STT: every byte stays on this PC. This module imports no socket and no
    HTTP client at all.
  * DELETING IS A ROUTE AND A CARD, NOT A MANUAL JOB. `POST .../delete`
    removes one recording's folder - the audio, the transcript and the receipt
    that is the list's row - behind ONE `delete_call_recording` card at tier
    `ask`, PC-only, with no bulk form. It is the ONLY thing that deletes a
    recording besides the owner's own Explorer. There is no automatic expiry:
    recordings and transcripts are kept until the owner deletes them, and the
    400-recording cap REFUSES a new start rather than deleting anything
    (docs/CALL-RECORDING.md section 7 is the retention policy).
  * THE THREE POST ROUTES ARE THE PHONE'S BY NECESSITY, and that is the one
    deliberate departure from `jarvis_media_index`'s POST-is-PC-only rule: the
    device that holds the microphone is the phone, so a PC-only start would make
    the feature impossible. Their controls are the origin+token checks on every
    request, the `record_call` card, and the feature being off by default; the
    note write then keeps the editor's own `edit_vault_note` card. The
    READ-ONLY route AND THE DELETE ROUTE are **PC-ONLY** (the repo's rule): the
    phone has no use for a list of the owner's recordings and note paths, and
    it never deletes anything on this PC.
  * The stale-link rule (never act on a stale picture of the world) is a
    client-side rule here: the phone stops recording if its own link to the PC
    has gone stale. The PC has no event-stream state to be stale about.

WHAT IS NOT TESTED, AND IS SAID SO IN THE PR
  No real phone recording, no real transcription model run, no real speaker
  model run, no real vault write, and no real approval card were driven by this
  lane. The suite drives fake readers, fake embedders, fake prints and a fake
  note creator. Those rows are NOT-TESTABLE here, never "passed".

Standard library only. No network. No model loaded at import time.
"""
from __future__ import annotations

import array
import base64
import datetime as _dt
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
import wave
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   Names, paths, caps
# --------------------------------------------------------------------------

START_PATH = "/api/call/recording/start"
CHUNK_PATH = "/api/call/recording/chunk"
FINISH_PATH = "/api/call/recording/finish"
LIST_PATH = "/api/call/recording"
DELETE_PATH = "/api/call/recording/delete"
POST_PATHS = (START_PATH, CHUNK_PATH, FINISH_PATH, DELETE_PATH)
GET_PATHS = (LIST_PATH,)

#: The approval gate's action for STARTING a recording. One name, used by the
#: module, by the settings file's [autonomy.tiers] line, by
#: jarvis_card_words.TITLES and by jarvis_asks_first's page.
ACTION = "record_call"

#: The approval gate's action for DELETING one. Its own name, so the card can
#: say what it is and so a tier can be set for it alone; the row in
#: jarvis_gate._RISK is `("yes", "local", ...)` - a recording changes nothing
#: and can be deleted again, and nothing leaves this PC. Tier `ask`: deleting
#: audio cannot be undone.
DELETE_ACTION = "delete_call_recording"

#: The feature switch's section in jarvis-framework.toml. No table = OFF.
CONFIG_SECTION = "call_recording"
#: The settings folder's own sub-folder for every recording.
RECORDINGS_FOLDER = "call-recordings"
#: An env override for the root folder - an install and the suite point it at
#: their own folder. The same shape jarvis_media_index uses for its config dir.
ROOT_ENV = "JARVIS_CALL_RECORDINGS"
CONFIG_DIR_ENV = ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR")

#: What the phone sends. One shape only: a second shape would be a second
#: decoder we do not need, so an unexpected value is refused and named.
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2                     # s16le
FORMATS = ("s16le",)
DEVICES = ("phone",)

#: One chunk is at most 512 KiB decoded - 16 seconds of 16 kHz mono s16le - and
#: about 683 KiB once base64 is applied, comfortably inside the PC's 4 MiB
#: MAX_BODY (token-store.patch), which is the same ceiling
#: jarvis_attached_file.MAX_BYTES is sized against. The phone cuts 64 KiB
#: chunks; the cap is deliberately generous so a phone that cuts a little more
#: is not refused mid-call.
MAX_CHUNK_BYTES = 512 * 1024
MAX_CHUNK_B64 = (MAX_CHUNK_BYTES + 2) // 3 * 4 + 8
#: The longest call this will hold: 4 hours. (4 h * 16000 * 2 = 460.8 MB.)
MAX_RECORDING_SECONDS = 4 * 60 * 60
MAX_RECORDING_BYTES = MAX_RECORDING_SECONDS * SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS
MAX_CHUNKS = 200000
#: How many recordings may sit in the folder before a new start is refused.
#: This cap NEVER deletes anything (docs/CALL-RECORDING.md section 7): it
#: refuses a new start and names the folder, and the owner deletes with
#: `POST .../delete` or by hand. Nothing else expires either - a recording the
#: owner asked for is not something a timer may throw away.
MAX_SESSIONS = 400
#: A start whose `started_at` is further from this PC's clock than this is
#: refused, so a wrong phone clock cannot name a note in the past or the future.
MAX_CLOCK_SKEW_SECONDS = 24 * 60 * 60

#: read_media refuses a file longer than 10 minutes, and its own decode rounds
#: seconds, so parts are 9 minutes with a minute of margin.
PART_SECONDS = 540
#: A live voice turn makes read_media say "busy"; the worker retries a few
#: times, then records the gap in the note instead of inventing words.
BUSY_RETRIES = 6
BUSY_SLEEP_SECONDS = 10.0
#: Speaker labelling: named, so a later measurement changes one number.
SPEAKER_MERGE_SIMILARITY = 0.55
MAX_SPEAKERS = 6
MIN_EMBED_SECONDS = 0.6
#: Longer transcripts are cut at this many lines, with a plain "more lines"
#: sentence: the note editor refuses a create over its own 2 MiB ceiling.
MAX_NOTE_LINES = 20000

SID_RE = re.compile(r"^call_[0-9a-f]{24}$")

#: "no argument given" for the seams, so `None` can mean "there is none".
_UNSET = object()

#: The eight whole messages the owner may say (the keywords rule is
#: WHOLE-MESSAGE ONLY: a sentence that merely contains one of these is the
#: model's). Kept here, not in jarvis_quick.py, so there is one list.
ARM_PHRASES = ("record call", "record this call", "record the call",
               "start recording the call", "start call recording")
STOP_PHRASES = ("stop recording", "stop the call recording", "stop call recording")

OFF_WORDS = ("Recording calls is off on this PC. Turn it on in the settings file "
             "(jarvis-framework.toml, [call_recording] enabled = true) and ask again.")
ARM_REPLY = ("Recording a call: your phone records it through its microphone with the call "
             "on speaker - Android does not let an app record the call's own audio, so the "
             "other person is heard through the speaker. When the call ends this PC "
             "transcribes it, labels who spoke and writes a new Obsidian note named for the "
             "date and time. Nothing leaves this PC. Tell the other person the call is being "
             "recorded.")
ARM_REPLY_CARD = (" One more thing: your PC will ask on an approval card before it starts "
                  "recording - approve it there and the phone begins.")
STOP_REPLY = ("Stopped. Your phone stops recording; this PC still transcribes what it has and "
              "writes the note when the call ends.")
UNKNOWN_ACTION = "I only know how to start or stop a call recording."

#: The card's own words (the gate shows this as the prompt).
START_CARD = "\n".join([
    "Record a phone call and file it as a note?",
    "",
    "Your phone starts recording through its microphone, with the call on speaker. "
    "The audio is kept in this PC's settings folder, transcribed here, and written "
    "into a NEW Obsidian note named for the date and time.",
    "",
    "Android does not let an ordinary app record the call's own audio, so the other "
    "person is heard through the speaker - the words will be less clear than a system "
    "recorder would give.",
    "",
    "Nothing is sent anywhere. Tell the other person the call is being recorded.",
    "",
    # EXACT, not "nothing is kept": the session's folder, its receipt.json and
    # an empty audio.pcm are made BEFORE this card (so a crash between the
    # phone's first chunk and the approval cannot lose it). No audio byte is
    # written until it is approved, and that is what the words say.
    "If you say no: no audio is kept.",
])

REFUSED_WORDS = {
    "denied": "You said no, so nothing is being recorded.",
    "timed_out": "Nobody answered the approval card in time, so nothing is being recorded.",
    "refused": "Your PC refused the recording, so nothing is being recorded.",
    "never": "Recording a call is set to \"never\" in the settings file, so nothing is being "
             "recorded.",
}

#: What a refused DELETE card says. Its own words, not REFUSED_WORDS: "nothing
#: is being recorded" is the wrong sentence for something that was not deleted.
DELETE_REFUSED_WORDS = {
    "denied": "You said no, so nothing was deleted.",
    "timed_out": "Nobody answered the approval card in time, so nothing was deleted.",
    "refused": "Your PC refused to delete that recording, so nothing was deleted.",
    "never": "Deleting a recording is set to \"never\" in the settings file, so nothing "
             "was deleted.",
}

#: The DELETE card's own words. It says what goes, what stays, and that there is
#: no undo - the three things a deletion card has to say.
DELETE_CARD = "\n".join([
    "Delete one recorded call from this PC?",
    "",
    "This removes that recording's whole folder: audio.pcm, audio.wav, "
    "transcript.md, receipt.json and any part files. It disappears from the list "
    "of recordings.",
    "",
    "The Obsidian note, if one was already written, is a document of its own and "
    "STAYS in your vault - delete it there if you want that gone too.",
    "",
    "This cannot be undone, and nothing here keeps a copy.",
])

#: What the PC-only routes answer to a device that is not this PC. Two
#: sentences, because "reading the list" is not what a delete asked for:
#: nothing was shown in one case and nothing was deleted in the other.
PC_ONLY_REFUSAL = ("Reading the list of recorded calls can only be done on the "
                   "PC itself, so nothing was shown.")
PC_ONLY_DELETE_REFUSAL = ("Deleting a recorded call can only be done on the PC itself, so "
                          "nothing was deleted.")

#: The states the delete route refuses, in plain words, and why. A recording
#: that is still being captured or transcribed is in use: deleting its folder
#: under a live writer would leave a half-deleted recording and a phone that
#: keeps posting chunks into nothing. Everything else (waiting, refused, empty,
#: failed, done) can go.
DELETE_REFUSED_STATE = {
    "recording": "that call is still being recorded on your phone, so nothing was deleted - "
                 "stop it on the phone first, and delete it when it has been sent",
    "transcribing": "that recording is still being turned into words on this PC, so nothing "
                    "was deleted - try again when its note has been written",
}

BODY_NOT_OBJECT = "the request was not a JSON object"
BAD_SESSION = "that recording is not on this PC (the session id is not one of ours)"

#: RLock, because the chunk route holds it around its order check and its
#: append and then calls `_update`, which takes it again.
_lock = threading.RLock()


# --------------------------------------------------------------------------
#   The feature switch (off by default)
# --------------------------------------------------------------------------

def _framework():
    try:
        import jarvis_framework
        return jarvis_framework
    except Exception:                                       # noqa: BLE001
        return None


def _config_dir() -> Path:
    for name in CONFIG_DIR_ENV:
        value = os.environ.get(name, "").strip()
        if value:
            return Path(os.path.expanduser(value))
    fw = _framework()
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:                                   # noqa: BLE001
            pass
    return Path(os.path.expanduser("~")) / ".openjarvis"


def recordings_root() -> Path:
    """Where every recording lives: `<config dir>/call-recordings` unless an
    install or the suite points `JARVIS_CALL_RECORDINGS` somewhere else."""
    value = os.environ.get(ROOT_ENV, "").strip()
    if value:
        return Path(os.path.expanduser(value))
    return _config_dir() / RECORDINGS_FOLDER


def framework_default() -> bool:
    """What the shipped settings file says. A missing table is OFF, which is
    the direction this feature ships in (see the module docstring)."""
    fw = _framework()
    if fw is not None:
        try:
            section = fw.load_framework().get(CONFIG_SECTION) or {}
            if isinstance(section, dict) and "enabled" in section:
                return section.get("enabled") is True
        except Exception:                                   # noqa: BLE001
            pass
    return False


def settings() -> dict:
    """{"enabled": bool, "why": str}. The settings file decides; a file that
    cannot be read is reported, never quietly read as ON."""
    fw = _framework()
    if fw is None:
        return {"enabled": framework_default(),
                "why": "the settings file could not be read, so the shipped "
                       "default (off) is used"}
    try:
        fw.load_framework()
    except Exception as exc:                                # noqa: BLE001
        return {"enabled": framework_default(),
                "why": f"the settings file could not be read ({type(exc).__name__}), "
                       f"so the shipped default (off) is used"}
    return {"enabled": framework_default(), "why": ""}


def enabled() -> bool:
    """True only when `[call_recording] enabled = true` is really there."""
    return settings()["enabled"] is True


def _tier(action: str) -> str:
    fw = _framework()
    if fw is not None:
        try:
            return str(fw.action_tier(action) or "ask").strip().lower()
        except Exception:                                   # noqa: BLE001
            pass
    return "ask"


def _audit(event: str, detail: dict) -> None:
    fw = _framework()
    if fw is None:
        return
    try:
        fw.audit_log("call_notes." + event, detail)
    except Exception:                                       # noqa: BLE001
        pass


# --------------------------------------------------------------------------
#   The gate, failing CLOSED on anything wrong
# --------------------------------------------------------------------------

class _RefusedVerdict:
    """What a missing or broken gate answers: allowed is False, always."""

    allowed = False
    outcome = "refused"
    tier = "ask"

    def __init__(self, reason: str):
        self.reason = reason


def _gate_check(action: str, detail: dict, prompt: str):
    try:
        import jarvis_gate
    except Exception as exc:                                # noqa: BLE001
        return _RefusedVerdict(f"the approval gate is not available here "
                               f"({type(exc).__name__})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:                                # noqa: BLE001
        return _RefusedVerdict(f"the approval gate raised {type(exc).__name__}")


# --------------------------------------------------------------------------
#   Sessions: the receipt file is the truth (a restart does not forget)
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_iso(value):
    """A datetime for `value`, or None. A naive timestamp is the phone's local
    time, read as this PC's local time (documented in the API section)."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        got = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if got.tzinfo is None:
        got = got.replace(tzinfo=_dt.datetime.now().astimezone().tzinfo)
    return got


def session_dir(session) -> Optional[Path]:
    """The folder for `session`, or None when the id is not one this module
    makes. The id is NEVER used as a path on its own: it must match SID_RE and
    the folder must really be under the recordings root."""
    sid = str(session or "").strip()
    if not SID_RE.fullmatch(sid):
        return None
    root = recordings_root()
    path = root / sid
    try:
        root_real = os.path.realpath(str(root))
        if os.path.commonpath([root_real, os.path.realpath(str(path))]) != root_real:
            return None
    except (ValueError, OSError):
        return None
    return path


def _receipt_path(folder: Path) -> Path:
    return folder / "receipt.json"


def read_receipt(session) -> Optional[dict]:
    folder = session_dir(session)
    if folder is None:
        return None
    try:
        doc = json.loads(_receipt_path(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def write_receipt(session, doc: dict) -> dict:
    """Write the session's receipt atomically. Never raises; a receipt that
    cannot be written says so in the dict it returns."""
    folder = session_dir(session)
    if folder is None:
        return {"ok": False, "error": "not one of this PC's recordings"}
    path = _receipt_path(folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:                                  # noqa: BLE001
        return {"ok": False,
                "error": f"the receipt could not be saved ({type(exc).__name__})"}
    return {"ok": True}


def _update(session, **fields) -> dict:
    """One field-set on the receipt, read-modify-write under the module lock.

    Locked because two threads really do write here - the chunk route and the
    card's own decision thread - and an unlocked read-modify-write let the
    slower one put `status: "waiting"` back over `status: "recording"`, which
    would then refuse every later chunk.
    """
    with _lock:
        doc = read_receipt(session) or {}
        if not doc:
            return {}
        doc.update(fields)
        doc["updated"] = time.time()
        write_receipt(session, doc)
        return doc


def receipt_text(doc: dict) -> str:
    """The frozen contract's `receipt`: ONE line, for the owner's eyes.

    It is a STRING on the wire (`CallRecordWire.finished` reads `receipt` only
    when it is a string), and the structured form of the same facts is the
    `recording` object in the same answer - and what the list route serves.
    """
    if not isinstance(doc, dict) or not doc:
        return ""
    bits = []
    seconds = float(doc.get("duration_sec") or 0.0)
    if seconds:
        bits.append(_duration_words(seconds) + " of audio")
    lines = int(doc.get("lines") or 0)
    if lines:
        bits.append(f"{lines} line(s)")
    speakers = doc.get("speakers") or []
    if speakers:
        bits.append("speakers " + ", ".join(str(s) for s in speakers))
    note = str(doc.get("note") or "")
    bits.append("note " + note if note else "note pending")
    head = str(doc.get("session") or "")
    return ": ".join([head, ", ".join(bits)]) if bits else head


def _public_receipt(doc: dict) -> dict:
    """The receipt as a route returns it: the facts, never the transcript."""
    if not isinstance(doc, dict):
        return {}
    out = {"session": str(doc.get("session") or ""),
           "status": str(doc.get("status") or "")}
    for key in ("started_at", "finished_at", "duration_sec", "sample_rate",
                "channels", "format", "device", "bytes", "chunks", "note",
                "note_job", "transcript", "speakers", "speaker_method",
                "speaker_why", "lines", "message", "title", "consent_notice",
                "english_only", "audio", "date"):
        value = doc.get(key)
        if value not in (None, "", [], {}):
            out[key] = value
    started = _parse_iso(doc.get("started_at"))
    if started is not None:
        out["date"] = started.strftime("%Y-%m-%d")
    return out


def list_receipts(limit: int = 20) -> list:
    """Newest first, at most `limit`. Reads receipts only - never audio."""
    root = recordings_root()
    try:
        folders = [p for p in root.iterdir() if p.is_dir() and SID_RE.fullmatch(p.name)]
    except OSError:
        return []
    rows = []
    for folder in folders:
        try:
            doc = json.loads(_receipt_path(folder).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict):
            rows.append(doc)
    rows.sort(key=lambda d: float(d.get("created") or 0), reverse=True)
    return rows[:max(1, int(limit))]


# --------------------------------------------------------------------------
#   Building and reading the WAV
# --------------------------------------------------------------------------

def pcm_to_wav(pcm_path, wav_path, *, rate: int = SAMPLE_RATE,
               channels: int = CHANNELS) -> dict:
    """Write a canonical 16-bit WAV from raw little-endian PCM bytes.

    Byte-exact: `wave` writes the canonical 44-byte header (RIFF/WAVE/fmt /data)
    and copies the PCM through untouched, so the frames in the WAV are the bytes
    the phone sent, in the order it sent them. An odd trailing byte (a chunk
    that split a sample) is dropped and reported rather than guessed at.
    """
    src = Path(pcm_path)
    dst = Path(wav_path)
    out = {"ok": False, "bytes": 0, "frames": 0, "dropped_tail": 0,
           "rate": int(rate), "channels": int(channels), "seconds": 0.0}
    try:
        raw = src.read_bytes()
    except OSError as exc:                                  # noqa: BLE001
        out["error"] = (f"the recorded audio could not be read "
                        f"({type(exc).__name__})")
        return out
    frame_bytes = SAMPLE_WIDTH * int(channels)
    dropped = 0
    if frame_bytes > 1 and len(raw) % frame_bytes:
        dropped = len(raw) % frame_bytes
        raw = raw[:len(raw) - dropped]
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dst), "wb") as handle:
            handle.setnchannels(int(channels))
            handle.setsampwidth(SAMPLE_WIDTH)
            handle.setframerate(int(rate))
            handle.writeframes(raw)
    except (OSError, wave.Error) as exc:                    # noqa: BLE001
        out["error"] = (f"the recording could not be turned into a WAV "
                        f"({type(exc).__name__})")
        return out
    frames = len(raw) // frame_bytes if frame_bytes else 0
    out.update(ok=True, bytes=len(raw), frames=frames, dropped_tail=dropped,
               seconds=round(len(raw) / float(max(1, int(rate) * int(channels)
                                                * SAMPLE_WIDTH)), 3))
    return out


class WavReader:
    """Read spans of the assembled WAV as floats in -1..1, one open handle.

    Only ever opened on this module's OWN file under the settings folder (see
    "SAFETY" in the module docstring), and only by the transcription thread.
    """

    def __init__(self, path):
        self.path = str(path)
        self._handle = wave.open(self.path, "rb")
        self.rate = int(self._handle.getframerate() or SAMPLE_RATE)
        self.channels = int(self._handle.getnchannels() or CHANNELS)
        self.frames = int(self._handle.getnframes())

    @property
    def seconds(self) -> float:
        return self.frames / float(max(1, self.rate))

    def samples(self, start: float, end: float) -> list:
        """The clip between two moments, as floats in -1..1."""
        first = max(0, int(round(float(start) * self.rate)))
        last = min(self.frames, int(round(float(end) * self.rate)))
        if last <= first:
            return []
        try:
            self._handle.setpos(first)
            raw = self._handle.readframes(last - first)
        except (OSError, wave.Error, EOFError):
            return []
        values = array.array("h")
        values.frombytes(raw[:len(raw) - (len(raw) % 2)])
        if sys.byteorder == "big":                          # pragma: no cover
            values.byteswap()
        return [v / 32768.0 for v in values]

    def copy_to(self, part_path, first: int, last: int) -> bool:
        """Copy frames [first, last) into their own small WAV."""
        try:
            self._handle.setpos(int(first))
            raw = self._handle.readframes(int(last) - int(first))
            with wave.open(str(part_path), "wb") as handle:
                handle.setnchannels(self.channels)
                handle.setsampwidth(SAMPLE_WIDTH)
                handle.setframerate(self.rate)
                handle.writeframes(raw)
            return True
        except (OSError, wave.Error, EOFError):
            return False

    def close(self) -> None:
        try:
            self._handle.close()
        except Exception:                                   # noqa: BLE001
            pass


# --------------------------------------------------------------------------
#   Transcription - the existing reader, in 9-minute parts
# --------------------------------------------------------------------------

def _read_media_default(path: str) -> dict:
    try:
        import jarvis_media_read as M
        return M.read_media(path)
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "error": f"the speech reader is not available here "
                                      f"({type(exc).__name__})"}


def transcribe_wav(wav_path, *, reader: Optional[Callable] = None,
                   part_seconds: float = PART_SECONDS,
                   sleep: Callable = time.sleep) -> dict:
    """Transcribe the assembled WAV through `jarvis_media_read`, part by part.

    Returns {"segments": [{"start","end","text"}], "gaps": [{"start","end","reason"}],
             "parts": n, "english_only": True, "why": ""}.
    `reader(path)` is the seam the suite drives; the default is read_media.
    """
    read = reader or _read_media_default
    out = {"segments": [], "gaps": [], "parts": 0, "english_only": True, "why": ""}
    try:
        source = WavReader(wav_path)
    except (OSError, wave.Error) as exc:                    # noqa: BLE001
        out["why"] = f"the recording could not be opened ({type(exc).__name__})"
        return out
    folder = Path(wav_path).parent
    step = max(1, int(round(float(part_seconds) * source.rate)))
    try:
        first = 0
        while first < source.frames:
            last = min(source.frames, first + step)
            offset = first / float(source.rate)
            span = last / float(source.rate)
            part = folder / f"part-{out['parts']:03d}.wav"
            try:
                if not source.copy_to(part, first, last):
                    out["gaps"].append({"start": round(offset, 2), "end": round(span, 2),
                                        "reason": "this part of the audio could not be cut out"})
                else:
                    out["parts"] += 1
                    got = {}
                    for attempt in range(BUSY_RETRIES):
                        got = read(str(part)) or {}
                        if got.get("reason") != "busy":
                            break
                        if attempt + 1 < BUSY_RETRIES:
                            sleep(BUSY_SLEEP_SECONDS)
                    if got.get("ok"):
                        for seg in got.get("segments") or []:
                            try:
                                start = offset + float(seg.get("start") or 0.0)
                                end = offset + float(seg.get("end") or 0.0)
                            except (TypeError, ValueError):
                                continue
                            text = str(seg.get("text") or "").strip()
                            if text:
                                out["segments"].append({"start": round(start, 2),
                                                        "end": round(end, 2),
                                                        "text": text})
                    else:
                        reason = str(got.get("error") or got.get("reason")
                                     or "the words could not be read")
                        out["gaps"].append({"start": round(offset, 2), "end": round(span, 2),
                                            "reason": reason})
            finally:
                try:
                    part.unlink()
                except OSError:
                    pass
            first = last
    finally:
        source.close()
    out["segments"].sort(key=lambda s: s["start"])
    return out


# --------------------------------------------------------------------------
#   Speaker labels - the owner's print first, then clusters
# --------------------------------------------------------------------------

def _cosine(a, b) -> float:
    """The project's own cosine (`jarvis_voice.cosine`) when it is importable,
    so the maths is the voice modules' own; otherwise the same dot over both
    norms here (the same rule, in one line)."""
    try:
        import jarvis_voice
        return float(jarvis_voice.cosine(a, b))
    except Exception:                                       # noqa: BLE001
        pass
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = sum(float(x) * float(x) for x in a) ** 0.5
    nb = sum(float(y) * float(y) for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def _mean_unit(vectors: list) -> list:
    if not vectors:
        return []
    width = len(vectors[0])
    total = [0.0] * width
    for vec in vectors:
        if len(vec) != width:
            continue
        for i, value in enumerate(vec):
            total[i] += float(value)
    norm = sum(v * v for v in total) ** 0.5
    return [v / norm for v in total] if norm else []


def _owner_vectors(profile) -> list:
    """Every centroid the owner's print carries: the whole print's, plus each
    per-condition sub-print for any model name (jarvis_voice's own shape)."""
    out = []
    centroid = getattr(profile, "centroid", None)
    if isinstance(centroid, (list, tuple)) and centroid:
        out.append([float(x) for x in centroid])
    subprints = getattr(profile, "subprints", None)
    names = []
    for name in (str(getattr(profile, "embedder", "") or "").strip().lower(),
                 "ecapa", "small", "strong"):
        if name and name not in names:
            names.append(name)
    if callable(subprints):
        for name in names:
            try:
                for sub in subprints(name) or []:
                    got = (sub or {}).get("centroid")
                    if isinstance(got, (list, tuple)) and got:
                        out.append([float(x) for x in got])
            except Exception:                               # noqa: BLE001
                continue
    return out


def _owner_bar(profile) -> float:
    try:
        bar = float(getattr(profile, "threshold", 0.35))
    except (TypeError, ValueError):
        bar = 0.35
    floor = 0.05
    try:
        import jarvis_voice
        floor = float(getattr(jarvis_voice, "MIN_THRESHOLD", floor))
    except Exception:                                       # noqa: BLE001
        pass
    return max(bar, floor)


def _embed(embedder, clip: list, rate: int) -> list:
    """One vector, from either shape of embedder in this project: the real one
    takes the sample rate, a stub in a suite takes the clip alone."""
    try:
        got = embedder.embed(clip, rate)
    except TypeError:
        try:
            got = embedder.embed(clip)
        except Exception:                                   # noqa: BLE001
            return []
    except Exception:                                       # noqa: BLE001
        return []
    try:
        return [float(x) for x in (got or [])]
    except (TypeError, ValueError):
        return []


def label_segments(segments: list, *, wav=None, embedder=None, profile=None,
                   rate: int = SAMPLE_RATE) -> dict:
    """Label each segment "You", "Speaker 1", ... or "Speaker".

    Returns {"lines": [{"start","end","text","speaker"}], "speakers": [...],
             "method": "owner-print+clusters" | "none", "why": str}.

    The degrade rule is the honest one (module docstring, point 4): no speaker
    model or no owner print means EVERY line is "Speaker", with the reason
    recorded - never a guess and never "You".
    """
    plain = [{"start": seg["start"], "end": seg["end"], "text": seg["text"],
              "speaker": "Speaker"} for seg in segments]
    if not segments:
        return {"lines": [], "speakers": [], "method": "none",
                "why": "no speech was recognised"}
    why = ""
    if embedder is None:
        why = "the speaker model is not installed on this PC"
    elif profile is None:
        why = "no voice has been trained on this PC"
    if why:
        return {"lines": plain, "speakers": ["Speaker"], "method": "none", "why": why}
    owner = _owner_vectors(profile)
    if not owner:
        return {"lines": plain, "speakers": ["Speaker"], "method": "none",
                "why": "the voice print has no usable template"}
    bar = _owner_bar(profile)
    vectors, labels = [], []
    for seg in segments:
        clip = wav.samples(seg["start"], seg["end"]) if wav is not None else []
        seconds = max(0.0, float(seg.get("end") or 0) - float(seg.get("start") or 0))
        vector = _embed(embedder, clip, rate) if clip and seconds >= MIN_EMBED_SECONDS else []
        vectors.append(vector)
        if vector and max(_cosine(vector, ref) for ref in owner) >= bar:
            labels.append("You")
        else:
            labels.append(None)
    # Cluster every vector that is not the owner's, in time order.
    clusters = []                      # [{"vectors": [...], "centroid": [...], "first": float}]
    member = {}                        # line index -> cluster index
    for index, vector in enumerate(vectors):
        if not vector or labels[index] == "You":
            continue
        best, best_score = None, -2.0
        for position, cluster in enumerate(clusters):
            score = _cosine(vector, cluster["centroid"])
            if score > best_score:
                best, best_score = position, score
        if best is not None and best_score >= SPEAKER_MERGE_SIMILARITY:
            clusters[best]["vectors"].append(vector)
            clusters[best]["centroid"] = _mean_unit(clusters[best]["vectors"])
            clusters[best]["first"] = min(clusters[best]["first"],
                                          float(segments[index]["start"]))
            member[index] = best
        elif len(clusters) < MAX_SPEAKERS:
            clusters.append({"vectors": [vector], "centroid": list(vector),
                             "first": float(segments[index]["start"])})
            member[index] = len(clusters) - 1
        elif clusters:
            member[index] = best      # over the cap: the nearest, never a new name
    # One merge pass, repeated until nothing merges (the stop rule).
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                if _cosine(clusters[i]["centroid"],
                           clusters[j]["centroid"]) >= SPEAKER_MERGE_SIMILARITY:
                    clusters[i]["vectors"] += clusters[j]["vectors"]
                    clusters[i]["centroid"] = _mean_unit(clusters[i]["vectors"])
                    clusters[i]["first"] = min(clusters[i]["first"], clusters[j]["first"])
                    clusters.pop(j)
                    for key, value in list(member.items()):
                        if value == j:
                            member[key] = i
                        elif value > j:
                            member[key] = value - 1
                    merged = True
                    break
            if merged:
                break
    order = sorted(range(len(clusters)), key=lambda k: clusters[k]["first"])
    names = {index: f"Speaker {position + 1}" for position, index in enumerate(order)}
    lines, previous = [], "Speaker"
    for index, seg in enumerate(segments):
        if labels[index]:
            speaker = labels[index]
        elif index in member:
            speaker = names[member[index]]
        else:
            speaker = previous            # a line too short to embed: the one before it
        lines.append({"start": seg["start"], "end": seg["end"], "text": seg["text"],
                      "speaker": speaker})
        previous = speaker
    speakers = []
    for line in lines:
        if line["speaker"] not in speakers:
            speakers.append(line["speaker"])
    return {"lines": lines, "speakers": speakers, "method": "owner-print+clusters",
            "why": ""}


def label_defaults() -> tuple:
    """(embedder, profile, why) from this PC's own voice modules, never raising.

    The embedder is chosen to MATCH the print: a print enrolled with the strong
    model (`<config dir>/voice-models/speaker/strong.onnx`) is compared with
    `StrongEmbedder`, everything else with `EcapaEmbedder` (`model.onnx`) - the
    two models have different dimensions, so the wrong one scores 0 against
    every line and would label the owner's own voice "Speaker". The spectral
    `Embedder` fallback is deliberately NOT used for labelling: it is not a
    speaker model, and "Speaker 1" from a spectral guess would be an invented
    identity. A missing model returns None and the caller degrades honestly.
    """
    why = ""
    try:
        import jarvis_voice
    except Exception as exc:                                # noqa: BLE001
        return None, None, f"the voice modules are not available here " \
                           f"({type(exc).__name__})"
    profile = None
    try:
        found = getattr(jarvis_voice, "find_profile", None)
        if callable(found):
            got = found("phone")
            profile = got[0] if isinstance(got, tuple) and got else got
        else:
            profile = jarvis_voice.load_profile()
    except Exception:                                       # noqa: BLE001
        profile = None
    wanted = str(getattr(profile, "embedder", "") or "").strip().lower()
    order = (["StrongEmbedder", "EcapaEmbedder"] if wanted.startswith("strong")
             else ["EcapaEmbedder"])
    embedder = None
    for name in order:
        factory = getattr(jarvis_voice, name, None)
        if not callable(factory):
            continue
        try:
            embedder = factory()
            break
        except Exception:                                   # noqa: BLE001
            continue
    if embedder is None:
        why = "the speaker model is not installed on this PC"
    if profile is None and not why:
        why = "no voice has been trained on this PC"
    return embedder, profile, why


# --------------------------------------------------------------------------
#   The note
# --------------------------------------------------------------------------

def _clock(started_at: _dt.datetime, offset: float) -> str:
    moment = started_at + _dt.timedelta(seconds=max(0.0, float(offset or 0.0)))
    return moment.strftime("%H:%M:%S")


def _duration_words(seconds: float) -> str:
    total = max(0, int(round(float(seconds or 0))))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def note_name(started_at: _dt.datetime, *, taken=()) -> str:
    """`Calls/YYYY-MM-DD HHMM - Call.md`, with " (2)" before the extension when
    that name is already used. A new note is never an edit of an old one."""
    stem = f"Calls/{started_at:%Y-%m-%d %H%M} - Call"
    used = {str(name).casefold() for name in (taken or ())}
    if f"{stem}.md".casefold() not in used:
        return f"{stem}.md"
    for number in range(2, 100):
        candidate = f"{stem} ({number}).md"
        if candidate.casefold() not in used:
            return candidate
    return f"{stem} ({started_at:%H%M%S}).md"


def render_note(*, started_at: _dt.datetime, duration_sec: float, lines: list,
                speakers: list, audio_path: str, session: str,
                title: str = "", speaker_method: str = "", speaker_why: str = "",
                gaps: Optional[list] = None, english_only: bool = True,
                more_lines: int = 0) -> str:
    """The whole new note: YAML frontmatter, the consent reminder, the lines."""
    when = started_at.strftime("%Y-%m-%d %H:%M")
    head = [
        "---",
        f"date: {started_at:%Y-%m-%d}",
        f"started_at: {json.dumps(started_at.isoformat(timespec='seconds'))}",
        f"duration: {json.dumps(_duration_words(duration_sec))}",
        f"duration_seconds: {int(round(float(duration_sec or 0)))}",
        f"source: {json.dumps('phone call, speaker recording')}",
        f"speakers: {json.dumps(list(speakers))}",
        f"audio: {json.dumps(str(audio_path))}",
        f"session: {json.dumps(str(session))}",
        f"consent: {json.dumps('Recorded locally; tell the other person')}",
    ]
    if title:
        head.append(f"title: {json.dumps(str(title))}")
    if speaker_method:
        head.append(f"speaker_labels: {json.dumps(str(speaker_method))}")
    if speaker_why:
        head.append(f"speaker_labels_why: {json.dumps(str(speaker_why))}")
    head.append(f"english_only: {'true' if english_only else 'false'}")
    head.append("---")
    body = [f"# Call - {when}", "",
            "> Recorded locally; tell the other person.", "",
            "Source: phone call, speaker recording (Android cannot record the call's own "
            "audio, so the phone records it through its microphone with the call on "
            "speaker). Transcribed on this PC.", "",
            "Speakers: " + (", ".join(speakers) if speakers else "Speaker")
            + (f" ({speaker_why})" if speaker_why else "") + ".", ""]
    for line in list(lines)[:MAX_NOTE_LINES]:
        body.append(f"[{_clock(started_at, line['start'])}] {line['speaker']}: {line['text']}")
    if more_lines:
        body += ["", f"({more_lines} more lines were transcribed and are in the copy beside "
                     f"the audio.)"]
    for gap in (gaps or []):
        body.append(f"[{_clock(started_at, gap.get('start', 0.0))}] "
                    f"(not transcribed: {gap.get('reason') or 'not available'})")
    if not lines:
        body += ["", "(No words were recognised in this recording.)"]
    body += ["", f"Audio: {audio_path}"]
    return "\n".join(head + body) + "\n"


def vault_state() -> tuple:
    """(usable, why not). The vault decision is jarvis_notes' own."""
    try:
        import jarvis_notes as N
    except Exception as exc:                                # noqa: BLE001
        return False, f"jarvis_notes.py is not available here ({type(exc).__name__})"
    vault = N.obsidian_vault()
    problem = N.vault_problem(vault)
    return (not problem), problem


def create_note(name: str, text: str, *, by: str = "call-recording",
                wait_s: float = 0.0) -> tuple:
    """Create ONE new note through the notes editor's own public create path.

    Returns (code, body). `provenance="after_outside_text"` is the honest mark:
    a transcript is other people's words, so this is NOT an owner-typed write
    and the editor keeps its one `edit_vault_note` card.
    """
    try:
        import jarvis_notes_edit as E
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "error": "the notes editor is not available here "
                                           f"({type(exc).__name__})"}
    try:
        return E.handle_create({"path": name, "text": text}, by=by,
                               provenance="after_outside_text", wait_s=wait_s)
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False,
                     "error": f"the note could not be created ({type(exc).__name__})"}


def _write_text(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def write_transcript_copy(session: str, text: str) -> str:
    """The transcript beside the audio - written BEFORE the vault is touched,
    so a vault problem or a refused card can never lose the words."""
    folder = session_dir(session)
    if folder is None:
        return ""
    path = folder / "transcript.md"
    return str(path) if _write_text(path, text) else ""


def _note_names_in_use() -> list:
    """The names already under `Calls/` in the vault, for the collision suffix.
    Read-only; a vault that cannot be listed yields no names (the editor's own
    create then refuses a collision rather than this module overwriting)."""
    try:
        import jarvis_notes as N
    except Exception:                                       # noqa: BLE001
        return []
    vault = N.obsidian_vault()
    if vault is None:
        return []
    try:
        return [f"Calls/{path.name}" for path in (Path(vault) / "Calls").glob("*.md")]
    except OSError:
        return []


# --------------------------------------------------------------------------
#   finish's worker: transcribe, label, write the note, settle the receipt
# --------------------------------------------------------------------------

def run_transcription(session: str, *, reader: Optional[Callable] = None,
                      embedder=_UNSET, profile=_UNSET,
                      create: Optional[Callable] = None) -> dict:
    """The daemon thread's whole job. Never raises; the receipt is the report.

    `embedder`/`profile` default to `label_defaults()`; passing None explicitly
    means "there is none" (the suite drives the degrade case that way), and
    `create(name, text)` is the note seam.
    """
    doc = read_receipt(session) or {}
    folder = session_dir(session)
    if not doc or folder is None:
        return {}
    audio = Path(doc.get("audio") or (folder / "audio.wav"))
    out = {"ok": False}
    try:
        read = transcribe_wav(audio, reader=reader)
        real_why = ""
        if embedder is _UNSET or profile is _UNSET:
            real_embedder, real_profile, real_why = label_defaults()
            if embedder is _UNSET:
                embedder = real_embedder
            if profile is _UNSET:
                profile = real_profile
        labelled = {"lines": [], "speakers": ["Speaker"], "method": "none",
                    "why": real_why}
        if read["segments"]:
            handle = None
            try:
                handle = WavReader(audio)
            except (OSError, wave.Error):
                handle = None
            try:
                labelled = label_segments(read["segments"], wav=handle,
                                          embedder=embedder, profile=profile,
                                          rate=int(doc.get("sample_rate") or SAMPLE_RATE))
            finally:
                if handle is not None:
                    handle.close()
        started = _parse_iso(doc.get("started_at")) or _dt.datetime.now().astimezone()
        text = render_note(started_at=started,
                           duration_sec=float(doc.get("duration_sec") or 0.0),
                           lines=labelled["lines"], speakers=labelled["speakers"],
                           audio_path=str(audio), session=session,
                           title=str(doc.get("title") or ""),
                           speaker_method=labelled["method"],
                           speaker_why=labelled["why"] or read.get("why", ""),
                           gaps=read.get("gaps") or [],
                           more_lines=max(0, len(labelled["lines"]) - MAX_NOTE_LINES))
        copy = write_transcript_copy(session, text)
        out.update(ok=True, lines=len(labelled["lines"]), speakers=labelled["speakers"],
                   transcript=copy, method=labelled["method"], why=labelled["why"])
        usable, problem = vault_state()
        note, note_job, message = "", "", ""
        if not usable:
            note = copy
            message = (f"The transcript is saved beside the audio at {copy}, because no "
                       f"Obsidian vault could be used: {problem}")
        elif not labelled["lines"]:
            note = copy
            message = (f"No words were recognised, so no note was written. The audio and "
                       f"the empty transcript are at {copy}.")
        else:
            name = note_name(started, taken=_note_names_in_use())
            code, created = (create or create_note)(name, text)
            body = created if isinstance(created, dict) else {}
            if code in (200, 202) and body.get("ok"):
                note = str(body.get("path") or name)
                if str(body.get("state") or "") == "waiting":
                    note_job = str(body.get("id") or "")
                    message = ("The note is waiting for your approval card on this PC; the "
                               "transcript is already saved beside the audio.")
                else:
                    message = f"The note is at {note} in your Obsidian vault."
            else:
                note = copy
                message = ("The note could not be created ("
                           + str(body.get("error") or "the editor refused it")
                           + f"), so the transcript is saved at {copy}.")
        settled = _update(session, status="done", note=note, note_job=note_job,
                          transcript=copy, lines=len(labelled["lines"]),
                          speakers=labelled["speakers"],
                          speaker_method=labelled["method"],
                          speaker_why=labelled["why"] or read.get("why", ""),
                          message=message, english_only=True)
        _audit("transcribed", {"session": session, "lines": len(labelled["lines"]),
                               "speakers": len(labelled["speakers"]),
                               "method": labelled["method"]})
        out.update(note=note, message=message, receipt=settled)
        return out
    except Exception as exc:                                # noqa: BLE001
        message = (f"The recording is safe at {audio}, but it could not be transcribed "
                   f"({type(exc).__name__}). Nothing was lost.")
        _update(session, status="failed", message=message)
        _audit("transcribe_failed", {"session": session, "why": type(exc).__name__})
        out.update(ok=False, error=message)
        return out


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

def _bad(message: str, state: str = "refused") -> tuple:
    return 400, {"ok": False, "state": state, "error": message}


def _start_thread(thread) -> None:
    """The default `spawn` seam: start an already-built thread. Injectable so
    the suite can run a worker inline without a thread of its own."""
    thread.start()


def _decide(session: str, gate: Callable) -> None:
    """Ask the one card, then (and only then) let the session record."""
    detail = {"what": "record a phone call and file it as an Obsidian note",
              "leaves_this_pc": False, "setting": "call_recording_enabled",
              "audio": "kept in this PC's settings folder",
              "words": "transcribed on this PC, in a new note"}
    verdict = gate(ACTION, detail, START_CARD)
    if getattr(verdict, "allowed", False):
        _update(session, status="recording",
                outcome=str(getattr(verdict, "outcome", "") or ""))
        _audit("started", {"session": session,
                           "outcome": str(getattr(verdict, "outcome", "") or "")})
        return
    outcome = str(getattr(verdict, "outcome", "refused") or "refused")
    _update(session, status="refused", outcome=outcome,
            message=REFUSED_WORDS.get(outcome,
                                      "Your PC refused the recording, so nothing is being "
                                      "recorded."),
            reason=str(getattr(verdict, "reason", "") or "")[:200])
    _audit("refused", {"session": session, "outcome": outcome})


def start(body, *, gate: Optional[Callable] = None, spawn=None,
          wait_s: float = 2.0) -> tuple:
    """POST /api/call/recording/start. See the module docstring for the shape."""
    if not isinstance(body, dict):
        return _bad(BODY_NOT_OBJECT)
    if not enabled():
        return 403, {"ok": False, "state": "off", "error": OFF_WORDS}
    started = _parse_iso(body.get("started_at"))
    if started is None:
        return _bad("started_at must be an ISO 8601 date and time, like "
                    "\"2026-11-04T13:36:05-08:00\"")
    now = _dt.datetime.now().astimezone()
    if abs((started.astimezone() - now).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
        return _bad("the phone's clock and this PC's clock are more than a day apart, so "
                    "the note could not be named for the right time - set the phone's "
                    "clock and try again")
    try:
        rate = int(body.get("sample_rate", SAMPLE_RATE))
        channels = int(body.get("channels", CHANNELS))
    except (TypeError, ValueError):
        return _bad("sample_rate and channels must be whole numbers")
    fmt = str(body.get("format") or "s16le").strip().lower()
    device = str(body.get("device") or "phone").strip().lower()
    if rate != SAMPLE_RATE or channels != CHANNELS:
        return _bad(f"this PC records {SAMPLE_RATE} Hz mono only, so send "
                    f"sample_rate: {SAMPLE_RATE} and channels: {CHANNELS}")
    if fmt not in FORMATS:
        return _bad("format must be one of " + ", ".join(FORMATS)
                    + " (16-bit little-endian PCM)")
    if device not in DEVICES:
        return _bad("device must be one of " + ", ".join(DEVICES))
    if len(list_receipts(limit=MAX_SESSIONS + 1)) > MAX_SESSIONS:
        return 507, {"ok": False, "state": "full",
                     "error": f"there are already more than {MAX_SESSIONS} recordings in "
                              f"{recordings_root()} - move some away, then ask again"}
    session = "call_" + secrets.token_hex(12)
    folder = session_dir(session)
    if folder is None:                                      # pragma: no cover - defensive
        return 503, {"ok": False, "state": "failed",
                     "error": "the recording folder is not on this PC"}
    doc = {"session": session, "status": "waiting", "created": time.time(),
           "started_at": started.astimezone().isoformat(timespec="seconds"),
           "sample_rate": rate, "channels": channels, "format": fmt, "device": device,
           "bytes": 0, "chunks": 0, "consent_notice": "", "title": "",
           "audio": str(folder / "audio.wav"),
           "engine": "sherpa-onnx through jarvis_media_read"}
    written = write_receipt(session, doc)
    if not written.get("ok"):
        return 503, {"ok": False, "state": "failed",
                     "error": str(written.get("error")
                                  or "the recording could not be started")}
    try:
        (folder / "audio.pcm").touch()
    except OSError as exc:                                  # noqa: BLE001
        _update(session, status="failed", message="the audio file could not be made")
        return 503, {"ok": False, "state": "failed",
                     "error": f"the audio file could not be made ({type(exc).__name__})"}
    worker = threading.Thread(target=_decide, args=(session, gate or _gate_check),
                              name="jarvis-call-notes-start", daemon=True)
    (spawn or _start_thread)(worker)
    worker.join(max(0.0, float(wait_s)))
    doc = read_receipt(session) or doc
    state = str(doc.get("status") or "waiting")
    if state == "recording":
        return 200, {"ok": True, "session": session, "state": "recording",
                     "sample_rate": rate, "channels": channels, "format": fmt}
    if state == "refused":
        return 403, {"ok": False, "session": session, "state": "refused",
                     "error": str(doc.get("message") or REFUSED_WORDS["refused"])}
    return 202, {"ok": True, "session": session, "state": "waiting",
                 "message": "An approval card is waiting on this PC. No audio is written "
                            "until it is approved."}


def chunk(body) -> tuple:
    """POST /api/call/recording/chunk: append one base64 PCM chunk, in order."""
    if not isinstance(body, dict):
        return _bad(BODY_NOT_OBJECT)
    if not enabled():
        return 403, {"ok": False, "state": "off", "error": OFF_WORDS}
    session = str(body.get("session") or "").strip()
    doc = read_receipt(session)
    if doc is None:
        return 404, {"ok": False, "state": "unknown", "error": BAD_SESSION}
    state = str(doc.get("status") or "")
    if state != "recording":
        return 409, {"ok": False, "state": state or "unknown",
                     "error": f"this recording is {state or 'not running'}, so this chunk "
                              f"was not kept"}
    try:
        seq = int(body.get("seq"))
    except (TypeError, ValueError):
        return _bad("seq must be a whole number, starting at 1")
    if seq < 1 or seq > MAX_CHUNKS:
        return _bad(f"seq must be between 1 and {MAX_CHUNKS}")
    expected = int(doc.get("chunks") or 0) + 1
    # A SEQ BELOW `expected` IS A RETRY OF A CHUNK THIS PC ALREADY HAS, and it
    # is the one thing a crash leaves behind: we answered 200 and the phone
    # died before it appended the number to its `sent.txt`, so it asks again
    # for a chunk that is already on disk. Answer 200 with the same shape and
    # write NOTHING. This used to be a 409, which retried the same number for
    # ever and made the recording permanently unsendable (the audit of
    # 2026-11-05, D3). Only a seq ABOVE `expected` is a real gap - a hole in
    # the audio nothing repairs - and only a gap is a 409.
    # The check is repeated under the lock below: a retry can overlap the
    # original request, and the first one may not have landed yet.
    if seq < expected:
        return 200, {"ok": True, "session": session, "seq": seq,
                     "bytes": int(doc.get("bytes") or 0), "chunk_bytes": 0,
                     "already": True}
    if seq > expected:
        return 409, {"ok": False, "state": state, "expected": expected,
                     "error": f"chunks must arrive in order: this recording is waiting for "
                              f"seq {expected}, and {seq} arrived"}
    encoded = body.get("data_b64")
    if not isinstance(encoded, str) or not encoded:
        return _bad("data_b64 must be the base64 of one PCM chunk")
    if len(encoded) > MAX_CHUNK_B64:
        return 413, {"ok": False, "state": state,
                     "error": f"that chunk is over the {MAX_CHUNK_BYTES // 1024} KiB limit "
                              f"for one chunk of 16 kHz mono audio"}
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return _bad("data_b64 is not valid base64")
    if not data:
        return _bad("that chunk is empty")
    if len(data) > MAX_CHUNK_BYTES:
        return 413, {"ok": False, "state": state,
                     "error": f"that chunk is over the {MAX_CHUNK_BYTES // 1024} KiB limit "
                              f"for one chunk of 16 kHz mono audio"}
    total = int(doc.get("bytes") or 0)
    if total + len(data) > MAX_RECORDING_BYTES:
        return 413, {"ok": False, "state": state,
                     "error": f"this call is over the {MAX_RECORDING_SECONDS // 3600} hour "
                              f"limit, so nothing more was kept"}
    folder = session_dir(session)
    if folder is None:                                      # pragma: no cover - defensive
        return 404, {"ok": False, "state": "unknown", "error": BAD_SESSION}
    path = folder / "audio.pcm"
    # THE ORDER CHECK AND THE WRITE ARE ONE STEP, under the lock: a phone that
    # retries a chunk while the first attempt is still landing must not be able
    # to write the same bytes twice (or two chunks around the check).
    with _lock:
        doc = read_receipt(session) or {}
        state = str(doc.get("status") or "")
        if state != "recording":
            return 409, {"ok": False, "state": state or "unknown",
                         "error": f"this recording is {state or 'not running'}, so this "
                                  f"chunk was not kept"}
        expected = int(doc.get("chunks") or 0) + 1
        if seq < expected:                                  # the same retry, one lock later
            return 200, {"ok": True, "session": session, "seq": seq,
                         "bytes": int(doc.get("bytes") or 0), "chunk_bytes": 0,
                         "already": True}
        if seq > expected:
            return 409, {"ok": False, "state": state, "expected": expected,
                         "error": f"chunks must arrive in order: this recording is "
                                  f"waiting for seq {expected}, and {seq} arrived"}
        total = int(doc.get("bytes") or 0)
        if total + len(data) > MAX_RECORDING_BYTES:
            return 413, {"ok": False, "state": state,
                         "error": f"this call is over the "
                                  f"{MAX_RECORDING_SECONDS // 3600} hour limit, so nothing "
                                  f"more was kept"}
        try:
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
            handle = os.open(str(path), flags, 0o644)
            try:
                written = os.write(handle, data)
            finally:
                os.close(handle)
        except OSError as exc:                              # noqa: BLE001
            return 503, {"ok": False, "state": state,
                         "error": f"the chunk could not be written ({type(exc).__name__})"}
        if written != len(data):
            return 503, {"ok": False, "state": state,
                         "error": "the chunk was only partly written, so the recording is "
                                  "out of step - start a new recording"}
        doc = _update(session, bytes=total + written, chunks=seq) or doc
    return 200, {"ok": True, "session": session, "seq": seq,
                 "bytes": int(doc.get("bytes") or 0), "chunk_bytes": written}


def finish(body, *, spawn=None, reader: Optional[Callable] = None,
           embedder=_UNSET, profile=_UNSET, create=None,
           wait_s: float = 0.0) -> tuple:
    """POST /api/call/recording/finish: make the WAV and start the words."""
    if not isinstance(body, dict):
        return _bad(BODY_NOT_OBJECT)
    if not enabled():
        return 403, {"ok": False, "state": "off", "error": OFF_WORDS}
    notice = str(body.get("consent_notice") or "").strip().lower()
    if notice != "on":
        return _bad('the recording was not finished: consent_notice must be "on" (the '
                    'phone says the "this call is being recorded" notice was shown)')
    session = str(body.get("session") or "").strip()
    doc = read_receipt(session)
    if doc is None:
        return 404, {"ok": False, "state": "unknown", "error": BAD_SESSION}
    state = str(doc.get("status") or "")
    if state in ("transcribing", "done"):
        return 409, {"ok": False, "state": state, "receipt": receipt_text(doc),
                     "recording": _public_receipt(doc),
                     "error": "this recording has already been finished"}
    if state == "refused":
        return 403, {"ok": False, "state": "refused",
                     "error": str(doc.get("message") or REFUSED_WORDS["refused"])}
    if state != "recording":
        return 409, {"ok": False, "state": state or "unknown",
                     "error": f"this recording is {state or 'not running'}, so it cannot "
                              f"be finished"}
    folder = session_dir(session)
    if folder is None:                                      # pragma: no cover - defensive
        return 404, {"ok": False, "state": "unknown", "error": BAD_SESSION}
    wav_path = folder / "audio.wav"
    built = pcm_to_wav(folder / "audio.pcm", wav_path,
                       rate=int(doc.get("sample_rate") or SAMPLE_RATE),
                       channels=int(doc.get("channels") or CHANNELS))
    if not built.get("ok"):
        _update(session, status="failed", message=str(built.get("error") or ""))
        return 503, {"ok": False, "state": "failed",
                     "error": str(built.get("error") or "the WAV could not be made")}
    if not built.get("frames"):
        _update(session, status="empty",
                message="no audio arrived, so there was nothing to transcribe")
        return 400, {"ok": False, "state": "empty",
                     "error": "no audio arrived for this recording, so there was nothing to "
                              "transcribe. The empty recording is at " + str(folder)}
    try:
        reported = (float(body.get("duration_sec"))
                    if body.get("duration_sec") is not None else None)
    except (TypeError, ValueError):
        return _bad("duration_sec must be a number of seconds")
    title = str(body.get("title") or "").strip()[:200]
    doc = _update(session, status="transcribing", consent_notice="on", title=title,
                  duration_sec=float(built.get("seconds") or 0.0),
                  reported_duration_sec=reported,
                  finished_at=_now_iso(),
                  dropped_tail=int(built.get("dropped_tail") or 0),
                  audio=str(wav_path)) or doc
    _audit("finished", {"session": session,
                        "seconds": round(float(built.get("seconds") or 0), 1),
                        "bytes": int(doc.get("bytes") or 0)})
    worker = threading.Thread(
        target=run_transcription, args=(session,),
        kwargs={"reader": reader, "embedder": embedder, "profile": profile,
                "create": create},
        name="jarvis-call-notes-words", daemon=True)
    (spawn or _start_thread)(worker)
    worker.join(max(0.0, float(wait_s)))
    doc = read_receipt(session) or doc
    note = str(doc.get("note") or "")
    return 200, {"ok": True, "session": session, "receipt": receipt_text(doc),
                 "note": note or "pending", "wav": str(wav_path),
                 "recording": _public_receipt(doc)}


def _remove_session(session) -> dict:
    """Delete one recording's folder and every file in it.

    Under the module lock, because the chunk route appends to `audio.pcm`
    while holding it: a folder cannot be removed under a live writer, and a
    delete that raced one would leave half a recording behind.

    Returns `{"ok": True, "removed": [<file name>, ...]}` or a plain `error`.
    """
    folder = session_dir(session)
    if folder is None:
        return {"ok": False, "error": BAD_SESSION}
    with _lock:
        try:
            names = sorted(p.name for p in folder.iterdir() if p.is_file())
        except OSError:
            names = []
        try:
            shutil.rmtree(str(folder))
        except OSError as exc:                              # noqa: BLE001
            return {"ok": False,
                    "error": f"the recording could not be deleted "
                             f"({type(exc).__name__}) - close anything that is reading it, "
                             f"and try again"}
    return {"ok": True, "removed": names}


def _deleted_words(doc: dict, removed: list) -> str:
    """One plain sentence for the owner: what went, and what did not."""
    files = ", ".join(removed) if removed else "the folder"
    words = f"Deleted from this PC: {files}."
    note = str(doc.get("note") or "").strip()
    if note and note != "pending":
        words += (f" The note it was filed into stays in your vault ({note}) - delete it in "
                  f"Obsidian if you want that gone too.")
    elif note:
        words += " No note had been written for it yet."
    else:
        words += " No note had been written for it."
    return words


def delete(body, *, gate: Optional[Callable] = None, spawn=None,
           wait_s: float = 2.0) -> tuple:
    """POST /api/call/recording/delete: remove ONE recording from this PC.

    PC-ONLY at the route: `install()` refuses any device but this one before
    this function runs (the caller's own peer address, through
    `jarvis_owner_check.from_this_pc`, the same check the list route makes).
    Behind ONE approval card of its own, `delete_call_recording` at tier
    `ask`, because deleting the audio and its transcript cannot be undone.

    THE DELETE RUNS ON THE CARD'S OWN WORKER, exactly as `start` does: a card
    still waiting answers 202, and the folder goes when it is approved - so
    there is no "approved but nothing happened" state for a caller to fall
    into. 200 means it is already gone.

    IT DOES NOT NEED THE FEATURE SWITCH ON. Removing something is the safe
    direction; an owner who has switched the feature off must still be able to
    delete what it already kept.

    Refused while the recording is still being captured or transcribed
    ([DELETE_REFUSED_STATE]): deleting a folder under a live writer would
    leave half a recording and a phone posting chunks into nothing.
    """
    if not isinstance(body, dict):
        return _bad(BODY_NOT_OBJECT)
    session = str(body.get("session") or "").strip()
    doc = read_receipt(session)
    if doc is None:
        return 404, {"ok": False, "state": "unknown",
                     "error": BAD_SESSION + " - so nothing was deleted"}
    state = str(doc.get("status") or "")
    blocked = DELETE_REFUSED_STATE.get(state)
    if blocked:
        return 409, {"ok": False, "state": state, "error": blocked}

    held: dict = {}

    def worker() -> None:
        detail = {"what": "delete one recorded call from this PC",
                  "session": session,
                  "state": state,
                  "audio": str(doc.get("audio") or ""),
                  "note": str(doc.get("note") or ""),
                  "leaves_this_pc": False,
                  "setting": ""}
        verdict = (gate or _gate_check)(DELETE_ACTION, detail, DELETE_CARD)
        # A DELETION IS NEVER CARD-FREE, whatever the tier table says. With a
        # _RISK row but no [autonomy.tiers] line this action takes
        # `unknown_action_tier` ("ask" as shipped), and an owner who loosens
        # that to "auto" would otherwise let a delete run with nobody asked.
        # The route promises a card, so it refuses an answer that was not one.
        tier = str(getattr(verdict, "tier", "ask") or "ask").strip().lower()
        if getattr(verdict, "allowed", False) and tier != "ask":
            held["state"] = "refused"
            held["message"] = ("Deleting a recording always asks first, and the approval gate "
                               "answered without asking, so nothing was deleted.")
            held["reason"] = f"the gate answered at tier {tier!r}"
            _audit("delete_refused", {"session": session, "outcome": "card_free"})
            return
        if not getattr(verdict, "allowed", False):
            outcome = str(getattr(verdict, "outcome", "refused") or "refused")
            held["state"] = "refused"
            held["reason"] = str(getattr(verdict, "reason", "") or "")[:200]
            held["message"] = DELETE_REFUSED_WORDS.get(
                outcome,
                "Your PC refused to delete that recording, so nothing was deleted.")
            _audit("delete_refused", {"session": session, "outcome": outcome})
            return
        gone = _remove_session(session)
        held["removed"] = list(gone.get("removed") or [])
        if gone.get("ok"):
            held["state"] = "deleted"
            _audit("deleted", {"session": session, "was": state,
                               "files": len(held["removed"])})
        else:
            held["state"] = "failed"
            held["error"] = str(gone.get("error") or "the recording could not be deleted")
            _audit("delete_failed", {"session": session})

    worker_thread = threading.Thread(target=worker, name="jarvis-call-notes-delete",
                                     daemon=True)
    (spawn or _start_thread)(worker_thread)
    worker_thread.join(max(0.0, float(wait_s)))
    got = held.get("state")
    if got == "deleted":
        return 200, {"ok": True, "session": session, "state": "deleted",
                     "removed": held.get("removed") or [],
                     "message": _deleted_words(doc, held.get("removed") or [])}
    if got == "failed":
        return 503, {"ok": False, "session": session, "state": "failed",
                     "error": held.get("error") or "the recording could not be deleted"}
    if got == "refused":
        return 403, {"ok": False, "session": session, "state": "refused",
                     "error": held.get("message") or REFUSED_WORDS["refused"]}
    return 202, {"ok": True, "session": session, "state": "waiting",
                 "message": "An approval card to delete this recording is waiting on this "
                            "PC. Nothing is deleted until it is approved."}


def listing(query: str = "") -> tuple:
    """GET /api/call/recording: the recent recordings, or ONE by `?session=`."""
    got = urllib.parse.parse_qs(str(query or "").lstrip("?"))
    session = str((got.get("session") or [""])[0]).strip()
    if session:
        doc = read_receipt(session)
        if doc is None:
            return 404, {"ok": False, "error": BAD_SESSION}
        return 200, {"ok": True, "recording": _public_receipt(doc)}
    rows = [_public_receipt(doc) for doc in list_receipts(limit=20)]
    return 200, {"ok": True, "enabled": enabled(), "recordings": rows,
                 "where": str(recordings_root()),
                 "message": ("No call has been recorded on this PC yet."
                             if not rows else "")}


def handle_get(query: str = "") -> tuple:
    try:
        return listing(query)
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "error": type(exc).__name__}


def handle_post(route: str, body) -> tuple:
    route = str(route or "").rstrip("/")
    try:
        if route == START_PATH:
            return start(body)
        if route == CHUNK_PATH:
            return chunk(body)
        if route == FINISH_PATH:
            return finish(body)
        if route == DELETE_PATH:
            return delete(body)
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "error": type(exc).__name__}
    return 404, {"ok": False, "error": "no such route"}


# --------------------------------------------------------------------------
#   The chat fast path's words (jarvis_quick.py calls these; the list lives
#   here so there is exactly one)
# --------------------------------------------------------------------------

def _flat(text) -> str:
    one = " ".join(str(text or "").replace("\u2019", "'").split())
    return one.strip(" .!?,\t").casefold()


def phrase_action(text) -> Optional[str]:
    """'arm', 'stop' or None - WHOLE MESSAGES ONLY.

    The keywords rule in this project is whole-message: the whole sentence must
    be one of the eight, and a sentence that merely CONTAINS one of them
    ("record call now", "I recorded a call yesterday", "record a call") is the
    model's. `_flat` folds case, spacing and trailing punctuation only.

    jarvis_quick.py applies the repo's own tidier (`normalize_spoken_command`,
    which drops polite lead-ins such as "can you ..." for EVERY command in that
    file) before asking this, so "can you record the call" there is the same
    command as "record the call". That is the existing rule, not a second one.
    """
    flat = _flat(text)
    if not flat:
        return None
    if flat in ARM_PHRASES:
        return "arm"
    if flat in STOP_PHRASES:
        return "stop"
    return None


def arm_reply(*, card: bool = False) -> str:
    """What the owner is told when the recording is armed.

    The card sentence is added only when this PC's tier really makes the start
    ask, so the reply never promises a card that will not appear.
    """
    return ARM_REPLY + (ARM_REPLY_CARD if card else "")


def quick_answer(action: str) -> tuple:
    """(ok, the words) for the chat fast path.

    STOPPING IS ALWAYS ALLOWED - it only narrows what is happening, the same
    direction every "turn off" in this project takes. Starting needs the
    feature switch on; the card (if any) is raised by the route, not here.
    """
    got = str(action or "").strip().lower()
    if got == "stop":
        return True, STOP_REPLY
    if got != "arm":
        return False, UNKNOWN_ACTION
    if not enabled():
        return False, OFF_WORDS
    return True, arm_reply(card=(_tier(ACTION) == "ask"))


# --------------------------------------------------------------------------
#   install(): the loader's convention, exactly like jarvis_media_index
# --------------------------------------------------------------------------

#: `PC_ONLY_REFUSAL` and `PC_ONLY_DELETE_REFUSAL` live beside the other
#: refusal sentences (see "Names, paths, caps" above), so a route and its
#: sentence are never in two different parts of this file.


def _from_this_pc(peer, local) -> bool:
    """Is this request from this PC? Fails CLOSED: no helper, no answer.

    `jarvis_owner_check.from_this_pc` is the project's one answer to this
    question (jarvis_media_index, jarvis_brain_reads and jarvis_self_improve
    wrap it the same way), so this module has no second rule of its own.
    """
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:                                       # noqa: BLE001
        return False


def install(handler_cls, *, origin_ok, token_ok, read_body,
            from_this_pc=None) -> str:
    """Wrap the core's Handler with these five routes.

    GET /api/call/recording is read-only AND PC_ONLY: it lists the owner's
    recordings and the note paths they went to, which is a PC surface, and the
    phone has no use for it. POST /api/call/recording/delete is PC_ONLY for the
    same reason and with its own sentence: the phone never deletes anything on
    this PC. The three POST routes for the audio need origin+token, like every
    other route, and are NOT PC-only ON PURPOSE - the phone holds the
    microphone (module docstring, "SAFETY"). Every other request goes to the
    original handler untouched. `from_this_pc` is injectable so the suite can
    drive both sides without a network; the shipped default is the project's
    own check.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    pc_here = from_this_pc or _from_this_pc
    if getattr(post0, "_jarvis_call_notes", False):
        return ("  call-notes  Call recording answers at /api/call/recording "
                "(already on)")

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:                                   # noqa: BLE001
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def _pc_only(self, refusal: str) -> bool:
        """Is this request from this PC? Sends `refusal` itself when it is not.

        One helper for both PC-only routes, so the list and the delete cannot
        drift apart: `jarvis_owner_check.from_this_pc` is the project's one
        answer, and a peer we cannot read is nobody (it fails closed).
        """
        peer = (getattr(self, "client_address", None) or ("",))[0]
        try:
            local = self.connection.getsockname()[0]
        except Exception:                                   # noqa: BLE001
            local = None
        if pc_here(peer, local):
            return True
        self._send(403, {"ok": False, "error": refusal})
        return False

    def do_GET(self):
        parts = urllib.parse.urlsplit(str(getattr(self, "path", "") or ""))
        if parts.path.rstrip("/") != LIST_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        # PC_ONLY, before the list is built: the owner's recordings and the
        # paths they were filed to are not a phone surface.
        if not _pc_only(self, PC_ONLY_REFUSAL):
            return None
        code, out = handle_get(parts.query)
        return self._send(code, out)

    def do_POST(self):
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route not in POST_PATHS:
            return post0(self)
        if not _allowed(self):
            return None
        # PC_ONLY before the body is even parsed: deleting a recording is not
        # something another device may ask for, whatever it holds.
        if route == DELETE_PATH and not _pc_only(self, PC_ONLY_DELETE_REFUSAL):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:                            # noqa: BLE001
            return self._send(400, {"ok": False,
                                    "error": f"the request was not JSON "
                                             f"({type(exc).__name__})"})
        code, out = handle_post(route, body)
        return self._send(code, out)

    do_GET._jarvis_call_notes = True
    do_POST._jarvis_call_notes = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("  call-notes  Record a call from your phone: "
            + ("on - audio is kept and transcribed on this PC, in a new note per call"
               if enabled() else "off - nothing is recorded"))
