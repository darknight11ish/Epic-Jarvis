"""jarvis_handsfree.py - hands-free mode: cards are read out, and a spoken
yes or no answers them.

THE OWNER'S REQUEST, in their own words (2026-11-04):

    "a handfree setting that i can turn off in chat, jarvis live, or through
     settings. in this mode any approval card for a task i ask jarvis to do
     will automatically be read out and i can answer confirm or deny
     (including verbally) and it will approve the card. i want jarvis to be
     able to write text messages to contacts for me in particular among the
     full fledged handsfree mode"

And their answer, on the clickable card that asked about the security
conflict: **"A voice yes counts for every card."** That supersedes the
sentence docs/ARCHITECTURE.md carried from 2026-09 (?): "Never
approve-by-voice: the voice check cannot tell a recording from the owner, so
a spoken 'yes' answers nothing." The decision record is
`decisions.d/2026-11-04-handsfree-voice-approval.md`; the old sentence stays
in its file, marked superseded, and is not edited.

WHAT THIS MODULE IS, AND WHAT IT IS NOT

It is the PC half. It:
  * reads and writes the ONE switch, `[handsfree] enabled` in the owner's
    settings file (`jarvis-framework.toml`), OFF by default;
  * raises ONE ask-tier card to turn it ON (`handsfree_enable`); OFF is
    immediate and raises nothing;
  * announces every waiting approval card to the phone as a new
    `handsfree_card` event, carrying the card's OWN plain words
    (`jarvis_gate.notice_for`, which is built from the gate's own tables and
    never reads the payload - the same rule that makes a notice safe on a
    lock screen);
  * answers ONE card from one spoken clip: the clip is turned into words by
    `jarvis_speech._transcribe` ON THIS PC (a client never does
    speech-to-text), the owner's voice print is checked first
    (`jarvis_voice.verify`), and only a word from a CLOSED vocabulary inside
    a 60-second window decides;
  * dispatches a text message to the owner's phone (`phone_command`
    {kind: "send_sms"}), which resolves the contact and sends it - the PC
    never stores a phone number and contacts never leave the phone;
  * records a receipt when the phone reports back; it never invents one.

It is NOT a second approval path. A spoken yes calls the SAME
`jarvis_gate.decide()` a touch-approve calls, after the same
`jarvis_owner_check` stamp a Windows Hello approval leaves - which is exactly
the narrow branch the owner's decision authorises, and it exists in ONE
function (`approve_one`) reachable only from `answer()` after a clip has
passed the voice print. Outside hands-free mode this module refuses before it
transcribes, which is the whole of the "the normal path is untouched" claim:
nothing else in the tree calls `approve_one`.

ORDER MATTERS: THE VOICE IS CHECKED BEFORE THE WORDS EXIST.
`jarvis_voice.verify`'s own docstring says why - "A voice that is not the
owner's is never turned into words - refusing after transcribing would leave
a stranger's speech in memory on the way to saying no." The brief for this
feature wrote "transcribe, then verify"; that order would break the rule, so
this module verifies first and the sentence a refused clip hears is the
voice module's own "that was not your voice".

NO ENROLLED VOICE PRINT MEANS NO SPOKEN YES.
`jarvis_voice.verify` answers False with "no enrolled voice profile - run
enrolment first", and this module turns that into one plain sentence rather
than falling back to vocabulary alone: without a print, a yes is
indistinguishable from a recording, so only a DENY is accepted from a voice
there. That is deliberately stricter than "a voice yes counts for every
card" - the owner's decision assumes the check can run, and it says so in
`docs/JARVIS-API.md` rather than hiding it.

Standard library only, plus the backend modules it calls lazily. No network,
no subprocess, no audio device: the clip arrives in the request body.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------
#   The one switch
# --------------------------------------------------------------------------

SECTION = "handsfree"
KEY = "enabled"

#: The owner's settings file, as `jarvis_framework` sees it. Named here so a
#: suite can point `OPENJARVIS_CONFIG_DIR`/`JARVIS_CONFIG_DIR` at a temporary
#: folder and test the real reader and writer (the same way
#: `test_tool_contract.py` copies the template in).
CONFIG_NAME = "jarvis-framework.toml"

#: One ask-tier card, and the action name it is stored under. A loosening
#: setting: ON weakens what an approval needs (a spoken yes counts), so it is
#: a risky card - Windows Hello on the PC - and OFF is instant and cardless.
ACTION_ENABLE = "handsfree_enable"

#: The model tool that writes a text message (`jarvis_agent.SEND_TEXT_TOOL`),
#: and the gate action it is stored under.
ACTION_SMS = "send_text_message"

#: The event kinds this module publishes. Frozen in docs/JARVIS-API.md
#: section 191; the Android lane reads that section, never this file.
READOUT_KIND = "handsfree_card"
PHONE_COMMAND_KIND = "phone_command"
PHONE_RESULT_KIND = "phone_result"

#: How long a read-out may be answered, in seconds. Fixed, not a setting: the
#: owner asked for a window, not a dial.
WINDOW_SEC = 60.0

#: The name written on every decision this module makes. It lands in the
#: gate's `decided_by` column and in the Activity list, so both apps show
#: that a VOICE answered, not a tap.
BY = "handsfree_voice"

#: Who may answer. Only words in these two closed lists decide anything; a
#: sentence outside them is `unclear`, asked once more, then treated as a
#: DENY (refusing is the safe direction, the same rule every card follows).
CONFIRM = ("yes", "yeah", "confirm", "approve", "do it", "go ahead", "okay", "ok")
DENY = ("no", "nope", "deny", "cancel", "stop", "don't", "do not")

#: The clip. 16 kHz mono 16-bit PCM WAV, as the contract says; a longer clip
#: is refused rather than truncated, because half a sentence is a decision
#: nobody said.
SAMPLE_RATE = 16000
MAX_SECONDS = 30.0
MAX_CLIP_BYTES = int(MAX_SECONDS * 48000) + 4096

#: The receipts store. Its own file, beside the other state the backend keeps
#: - never a table in approvals.db, which the gate is the only writer of.
RECEIPTS_NAME = "handsfree-receipts.json"
RECEIPTS_KEPT = 200

#: One sentence per answer, so the phone has something to SAY without
#: inventing words of its own. The phone speaks what it is sent.
SAID_APPROVED = "Approved. Carrying on."
SAID_DENIED = "OK, I won't do that."
SAID_AGAIN = "Sorry - was that yes or no?"
SAID_GONE = "That card is not waiting any more."
SAID_UNCLEAR_DENIED = "I didn't catch a clear answer, so I treated it as a no."
SAID_OFF = ("Hands-free mode is off, so a spoken answer decides nothing. "
            "Turn it on first.")
SAID_NO_PRINT = ("I can't tell your voice from anyone else's until you train my "
                 "voice, so I won't take a yes by voice. Say no, or answer the "
                 "card on your screen.")
SAID_NOT_YOUR_VOICE = "That was not your voice, so nothing was decided."
SAID_NO_WORDS = ("I could not turn that into words - speech to text is not "
                 "set up on this PC, so nothing was decided.")
SAID_NO_READOUT = ("That card was not read out to you, or its minute is over. "
                   "Nothing was decided.")
SAID_BAD_CLIP = "I could not read that recording, so nothing was decided."
#: Only used when jarvis_card_words cannot be imported; the real sentence lives
#: there, once, so the read-out and the phone cannot word it two ways.
SAID_ASK = 'Say "yes" to approve it or "no" to refuse.'


#: The Settings row's own words, byte for byte the desktop page's fallback
#: (`jarvis-desktop/src/handsfree-settings.js`). The page prefers what this
#: module sends on `GET /api/handsfree`; these are what it shows when the PC is
#: too old to send them, so the two copies cannot say the switch two ways.
LABEL = "Hands-free mode"
DETAIL = "Off (the default): every card needs a tap, exactly as it always has. On: every approval card that starts waiting is read out to your phone, and one word - yes, yeah, confirm, approve, do it, go ahead, okay, or no, nope, deny, cancel, stop, don't - answers THAT one card, within a minute of hearing it. It also answers the cards that would otherwise wait for Windows Hello or your phone's fingerprint; that is the part to understand before turning it on. The words are made on your PC, never by the phone; Jarvis checks the voice is yours BEFORE it turns the clip into words; with no voice trained it will not take a spoken yes at all; and one card gets one decision - an unclear answer is asked once more and then treated as a no. Turning it on raises one approval card. Turning it off is instant and asks nothing."


class Refused(ValueError):
    """A plain refusal with one sentence a person can act on."""


def _config_dir() -> Path:
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(env)
    try:
        import jarvis_framework as fw
        return Path(fw.CONFIG_DIR)
    except Exception:
        return Path.home() / ".openjarvis"


def settings_path() -> Path:
    """The owner's live settings file (never a template)."""
    try:
        import jarvis_framework as fw
        got = fw.config_path()
        if got is not None:
            return Path(got)
    except Exception:
        pass
    return _config_dir() / CONFIG_NAME


def _framework() -> dict:
    try:
        import jarvis_framework as fw
        return fw.load_framework() or {}
    except Exception:
        return {}


def enabled() -> bool:
    """Is hands-free mode on? OFF when anything cannot be read - the safe
    state, because ON is the one that changes what an approval needs."""
    try:
        return bool((_framework().get(SECTION) or {}).get(KEY, False))
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Writing the one line (same discipline as jarvis_asks_first.set_tier)
# --------------------------------------------------------------------------

def _rewrite_bool(text: str, section: str, key: str, value: bool) -> str:
    """`[section] key = <value>` in `text`, added or replaced, nothing else
    touched - comments, order and every other line survive."""
    want = "true" if value else "false"
    lines = text.splitlines(keepends=True)
    head = f"[{section}]"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == head:
            start = i
            break
    if start is None:
        sep = "" if not text or text.endswith("\n") else "\n"
        return f"{text}{sep}\n{head}\n{key} = {want}\n"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            end = j
            break
    for j in range(start + 1, end):
        s = lines[j].strip()
        if s.startswith("#") or "=" not in s:
            continue
        name = s.split("=", 1)[0].strip()
        if name == key:
            indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
            lines[j] = f"{indent}{key} = {want}\n"
            return "".join(lines)
    insert = f"{key} = {want}\n"
    if end > 0 and not lines[end - 1].endswith("\n"):
        lines[end - 1] = lines[end - 1] + "\n"
    lines.insert(end, insert)
    return "".join(lines)


def set_enabled(on: bool, *, path: Optional[Path] = None) -> dict:
    """Write `[handsfree] enabled` atomically. Raises Refused when the file
    cannot be read or written, or when the write did not take: a switch that
    says it is on and is not is worse than one that says it failed."""
    p = Path(path) if path is not None else settings_path()
    if not p.is_file():
        raise Refused("Jarvis could not find your settings file "
                      f"({CONFIG_NAME}), so nothing was changed.")
    with _FILE_LOCK:
        try:
            raw = p.read_bytes()
        except OSError as exc:
            raise Refused("Your settings file could not be read "
                          f"({type(exc).__name__}), so nothing was changed.")
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
        except UnicodeDecodeError:
            raise Refused("Your settings file is not valid UTF-8 text, so "
                          "nothing was changed.")
        new = _rewrite_bool(text, SECTION, KEY, bool(on))
        if new == text:
            _reload()
            return {"ok": True, "changed": False, "enabled": bool(on)}
        data = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
        except OSError as exc:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise Refused("Your settings file could not be written "
                          f"({type(exc).__name__}), so nothing was changed.")
    _reload()
    # Read it back. A file that was written but does not parse back as "on"
    # must fail loudly here rather than claim a switch that is not one.
    got = _read_back(p)
    if got is not None and got != bool(on):
        raise Refused("The setting was written but is not being read back as "
                      f"{'on' if on else 'off'}, so nothing is claimed.")
    if path is None and enabled() != bool(on):
        raise Refused("The setting was written but the backend is not reading it "
                      f"as {'on' if on else 'off'}, so nothing is claimed.")
    _audit("handsfree.switch", {"enabled": bool(on)})
    return {"ok": True, "changed": True, "enabled": bool(on)}


def _read_back(p: Path):
    """The value the file itself now holds, or None when it cannot be parsed."""
    try:
        import tomllib
        doc = tomllib.loads(Path(p).read_text(encoding="utf-8-sig"))
        return bool((doc.get(SECTION) or {}).get(KEY, False))
    except Exception:
        return None


def _reload() -> None:
    try:
        import jarvis_framework as fw
        fw.reload_framework()
    except Exception:
        pass


_FILE_LOCK = threading.RLock()


def request_enabled(on, *, gate: Optional[Callable] = None,
                    write: Optional[Callable] = None,
                    peer=None, local=None) -> tuple[int, dict]:
    """POST /api/handsfree {"enabled": bool}. (code, body).

    OFF is immediate, cardless and from either app: taking a power away is
    always safe. ON is ONE ask-tier card (`handsfree_enable`), because it
    changes what an approval needs from then on.
    """
    if not isinstance(on, bool):
        return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
    if not on:
        if enabled():
            try:
                (write or set_enabled)(False)
            except Refused as exc:
                return 409, {"ok": False, "error": str(exc)}
            _clear()
        return 200, {"ok": True, "enabled": False,
                     "message": "Hands-free mode is off. Approval cards are "
                                "back to needing a tap."}
    if enabled():
        return 200, {"ok": True, "enabled": True, "changed": False,
                     "message": "Hands-free mode was already on."}
    gate = gate or _gate
    try:
        verdict = gate(ACTION_ENABLE, {"text": _ON_CARD}, _ON_CARD)
    except Exception as exc:
        return 503, {"ok": False, "error": f"the approval gate: {type(exc).__name__}"}
    if not getattr(verdict, "allowed", False):
        return 403, {"ok": False, "enabled": False,
                     "error": _sentence(getattr(verdict, "reason", ""))}
    try:
        (write or set_enabled)(True)
    except Refused as exc:
        return 409, {"ok": False, "enabled": False, "error": str(exc)}
    _audit("handsfree.enabled", {"card": getattr(verdict, "request_id", None)})
    return 200, {"ok": True, "enabled": True, "changed": True,
                 "message": "Hands-free mode is on. I will read every card out, "
                            "and a spoken yes or no answers it."}


_ON_CARD = ("Turn on hands-free mode. While it is on, every approval card is "
            "read out to you and a spoken yes or no answers it - including on "
            "the cards that would otherwise wait for Windows Hello or your "
            "phone's fingerprint, and that is the part to understand before "
            "saying yes. The answer must be one word from a short list (yes, "
            "yeah, confirm, approve, do it, go ahead, okay / no, nope, deny, "
            "cancel, stop, don't), within a minute of the card being read out, "
            "and only after Jarvis has checked that the voice is yours. "
            "Turning it off is instant and raises nothing.")


def status() -> dict:
    """GET /api/handsfree - a read. Nothing here decides anything."""
    on = enabled()
    ready, why = _phone_ready(_devices_status)
    return {
        "ok": True,
        "enabled": on,
        "label": LABEL,
        "detail": DETAIL,
        "window_sec": int(WINDOW_SEC),
        "vocabulary": {"confirm": list(CONFIRM), "deny": list(DENY)},
        "voice_print": _voice_print_label(),
        "phone": {"ready": ready, "why": why},
        "reading": _last_readout(),
    }


# --------------------------------------------------------------------------
#   The read-out
# --------------------------------------------------------------------------

#: card_id -> {"at", "say", "action", "deadline", "asked"}. In memory only:
#: a read-out is a doorbell, not a record, and it is gone when the backend
#: stops. The DECISION is in approvals.db and in the audit log.
_READOUTS: dict = {}
_READY_LOCK = threading.RLock()


def _now(now: Optional[float] = None) -> float:
    return float(time.time() if now is None else now)


def _gate():
    import jarvis_gate
    return jarvis_gate


def _card_deadline(item: dict, at: float) -> float:
    """The read-out's own deadline: the 60-second window, or the card's own
    countdown when that is shorter. The card's `expires_in` stays what it
    always was - this only stops the voice window outliving the card."""
    left = item.get("expires_in")
    try:
        left = float(left)
    except (TypeError, ValueError):
        return at + WINDOW_SEC
    if left <= 0:
        return at
    return at + min(WINDOW_SEC, left)


def read_out(item: dict, *, now: Optional[float] = None,
             gate: Optional[Callable] = None) -> dict:
    """The `handsfree_card` payload for one waiting row, and the record that
    makes a spoken answer possible. It decides NOTHING: the card is still in
    /api/pending and still needs an answer, tap or voice."""
    at = _now(now)
    cid = str(item.get("id") or "")
    action = str(item.get("action") or "")
    g = gate if gate is not None else _gate()
    notice = g.notice_for(item)
    say = f"{notice.get('title', '')}. {notice.get('body', '')}".strip()
    try:
        import jarvis_card_words
        ask = jarvis_card_words.HANDSFREE_ASK
    except Exception:
        ask = SAID_ASK
    say = " ".join(f"{say} {ask}".split())
    with _READY_LOCK:
        _READOUTS[cid] = {"at": at, "say": say, "action": action,
                          "deadline": _card_deadline(item, at), "asked": 0}
    return {
        "card_id": cid,
        "action": action,
        "say": say,
        "expires_in_sec": max(0, int(round(_card_deadline(item, at) - at))),
    }


def _clear(card_id: Optional[str] = None) -> None:
    with _READY_LOCK:
        if card_id is None:
            _READOUTS.clear()
        else:
            _READOUTS.pop(str(card_id), None)


def _last_readout() -> Optional[dict]:
    with _READY_LOCK:
        if not _READOUTS:
            return None
        cid, row = max(_READOUTS.items(), key=lambda kv: kv[1].get("at") or 0)
    return {"card_id": cid, "action": row.get("action"), "say": row.get("say"),
            "expires_in_sec": max(0, int(round((row.get("deadline") or 0) - time.time())))}


def _publish_default(kind: str, data: dict) -> None:
    from jarvis_events import BUS
    BUS.publish(kind, data)


def tick(*, publish: Optional[Callable] = None, pending: Optional[Callable] = None,
         now: Optional[float] = None) -> list:
    """Announce every waiting card that has not been read out yet, and forget
    the read-outs of cards that are gone. Returns the payloads published.

    Pure enough to call from a suite: `pending` and `publish` are injected.
    The card is never touched, approved or denied here.
    """
    if not enabled():
        return []
    publish = publish or _publish_default
    try:
        rows = list((pending or (lambda: _gate().pending()))() or [])
    except Exception:
        return []
    live = {str(r.get("id") or "") for r in rows}
    with _READY_LOCK:
        for gone in [c for c in _READOUTS if c not in live]:
            _READOUTS.pop(gone, None)
        fresh = [r for r in rows if str(r.get("id") or "") not in _READOUTS]
    out = []
    for row in fresh:
        try:
            payload = read_out(row, now=now)
        except Exception:
            continue
        try:
            publish(READOUT_KIND, payload)
        except Exception:
            pass
        out.append(payload)
    return out


_thread: Optional[threading.Thread] = None
_stop = threading.Event()
POLL_SECONDS = 2.0


def start(*, interval: float = POLL_SECONDS) -> str:
    """Start the doorbell. Idempotent; one daemon thread, nothing else."""
    global _thread
    with _READY_LOCK:
        if _thread is not None and _thread.is_alive():
            return "hands-free read-out already watching"
        _stop.clear()

        def loop():
            while not _stop.wait(interval):
                try:
                    tick()
                except Exception:
                    pass
        _thread = threading.Thread(target=loop, name="handsfree-readout", daemon=True)
        _thread.start()
    return "hands-free read-out watching for cards"


def stop() -> None:
    _stop.set()
    with _READY_LOCK:
        global _thread
        _thread = None


# --------------------------------------------------------------------------
#   The spoken answer
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    keep = "".join(c.lower() if (c.isalnum() or c.isspace()) else " " for c in str(text or ""))
    return " ".join(keep.split())


_CONFIRM = frozenset(_norm(w) for w in CONFIRM)
_DENY = frozenset(_norm(w) for w in DENY)


def match_words(heard: str) -> str:
    """"confirm" | "deny" | "" - and nothing else. A CLOSED list: a sentence
    that merely contains a yes ("yes but wait") is NOT a yes."""
    said = _norm(heard)
    if not said:
        return ""
    if said in _CONFIRM:
        return "confirm"
    if said in _DENY:
        return "deny"
    return ""


def _read_wav_default(raw: bytes):
    """The PC's own reader (`jarvis_speech._read_wav`): one 16-bit PCM WAV in,
    (samples, rate) out, or None. A client never decodes the audio into
    anything but bytes; nothing here is speech-to-text."""
    import jarvis_speech
    return jarvis_speech._read_wav(raw)


def _decode_clip(data_b64, sample_rate, read_wav: Optional[Callable] = None) -> tuple:
    """(samples, rate) from the request body, or raise Refused."""
    if not isinstance(data_b64, str) or not data_b64.strip():
        raise Refused("That answer needs the card's id and the recorded sound.")
    try:
        raw = base64.b64decode(data_b64, validate=False)
    except (binascii.Error, ValueError):
        raise Refused(SAID_BAD_CLIP)
    if not raw:
        raise Refused(SAID_BAD_CLIP)
    if len(raw) > MAX_CLIP_BYTES:
        raise Refused(f"That recording is longer than {int(MAX_SECONDS)} seconds, "
                      "which is more than one answer should need.")
    if not isinstance(sample_rate, int):
        raise Refused("That answer needs the sound's rate as a whole number, usually 16000.")
    if not 8000 <= sample_rate <= 48000:
        raise Refused("That answer needs the sound's rate as a whole number, usually 16000.")
    got = (read_wav or _read_wav_default)(raw)
    if not got:
        raise Refused(SAID_BAD_CLIP)
    samples, rate = got
    if not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 48000:
        raise Refused("That answer needs the sound's rate as a whole number, usually 16000.")
    if int(rate) != int(sample_rate):
        raise Refused(f"The clip says {int(rate)} Hz but the request says "
                      f"{int(sample_rate)} Hz, so nothing was decided.")
    seconds = len(samples) / float(rate or 1)
    if seconds > MAX_SECONDS:
        raise Refused(f"That recording is {seconds:.0f} seconds long, and one "
                      "answer should be under thirty.")
    return samples, int(rate)


def _voice_print_label() -> str:
    try:
        import jarvis_voice
        prof, label = jarvis_voice.find_profile("")
        return str(label or "") if prof is not None else ""
    except Exception:
        return ""


def _has_print() -> bool:
    try:
        import jarvis_voice
        prof, _label = jarvis_voice.find_profile("")
        return prof is not None
    except Exception:
        return False


def _verify_default(samples, sample_rate: int):
    import jarvis_voice
    return jarvis_voice.verify(samples, sample_rate=sample_rate)


def _transcribe_default(samples, sample_rate: int) -> str:
    import jarvis_speech
    return jarvis_speech._transcribe(samples, sample_rate)


def _decide_default(card_id: str, approved: bool) -> bool:
    """THE approval function: the same one `/api/approve` and `/api/deny`
    reach, and the only one a touch-approve uses."""
    return bool(_gate().decide(card_id, approved, by=BY))


def _stamp_default(card_id: str, action: str) -> None:
    """The stamp a Windows Hello approval leaves. Called ONLY from
    `approve_one`, which only `answer()` reaches after the voice print
    passed - the narrow branch the owner's 2026-11-04 decision authorises."""
    import jarvis_owner_check
    jarvis_owner_check.stamp(card_id, action)


def approve_one(card_id: str, action: str, *, decide: Optional[Callable] = None,
                stamp: Optional[Callable] = None) -> bool:
    """Stamp, then decide - the two halves a touch-approve performs.

    ONE function, so "a voice yes approved it" has one implementation to
    audit. It raises nothing and invents nothing: False means the row was
    already settled.
    """
    (stamp or _stamp_default)(card_id, action)
    return bool((decide or _decide_default)(card_id, True))


def _row(card_id: str, gate=None) -> Optional[dict]:
    g = gate if gate is not None else _gate()
    try:
        rows = g.pending()
    except Exception:
        return None
    for row in rows or []:
        if str(row.get("id") or "") == card_id:
            return row
    return None


def _sentence(text) -> str:
    said = " ".join(str(text or "").split())
    return said[:400]


def answer(card_id, data_b64, sample_rate=SAMPLE_RATE, *, gate=None,
           decide: Optional[Callable] = None, stamp: Optional[Callable] = None,
           transcribe: Optional[Callable] = None,
           verify: Optional[Callable] = None,
           has_print: Optional[Callable] = None,
           read_wav: Optional[Callable] = None,
           now: Optional[float] = None) -> tuple[int, dict]:
    """POST /api/handsfree/answer. (code, body) with
    {ok, heard, decision, card_state, say}.

    ONE card, ONE decision, no list and no bulk. The order is deliberate:
    hands-free on -> a read-out exists and its minute is open -> the card is
    still waiting -> the VOICE is the owner's -> the words are in the closed
    vocabulary -> decide. Anything else decides nothing.
    """
    if not enabled():
        return 403, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unchanged", "say": SAID_OFF}
    if not isinstance(card_id, str) or not card_id.strip():
        return 400, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unchanged",
                     "error": "That answer needs the id of the card that was read out."}
    card_id = card_id.strip()
    at = _now(now)
    with _READY_LOCK:
        ro = dict(_READOUTS.get(card_id) or {})
    if not ro:
        return 409, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unknown", "say": SAID_NO_READOUT}
    if at > float(ro.get("deadline") or 0):
        _clear(card_id)
        return 409, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "expired", "say": SAID_NO_READOUT}
    try:
        samples, rate = _decode_clip(data_b64, sample_rate, read_wav)
    except Refused as exc:
        return 400, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unchanged", "error": str(exc), "say": str(exc)}
    row = _row(card_id, gate)
    if row is None:
        _clear(card_id)
        return 409, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "gone", "say": SAID_GONE}
    action = str(row.get("action") or ro.get("action") or "")
    # THE VOICE FIRST: a stranger's speech is never turned into words.
    printed = bool((has_print or _has_print)())
    clip = hashlib.sha256(data_b64.encode("ascii", "ignore")).hexdigest()
    try:
        verdict = (verify or _verify_default)(samples, rate)
    except Exception as exc:
        return 503, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unchanged",
                     "error": f"the voice check: {type(exc).__name__}",
                     "say": "The voice check could not run, so nothing was decided."}
    is_owner = bool(getattr(verdict, "is_owner", False))
    if not is_owner:
        _audit("handsfree.refused_voice", {"card": card_id, "clip": clip,
                                           "why": _sentence(getattr(verdict, "reason", ""))})
        said = SAID_NOT_YOUR_VOICE if printed else SAID_NO_PRINT
        return 403, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unchanged", "say": said,
                     "error": said}
    try:
        heard = (transcribe or _transcribe_default)(samples, rate) or ""
    except Exception as exc:
        return 503, {"ok": False, "heard": "", "decision": "refused",
                     "card_state": "unchanged",
                     "error": f"speech to words: {type(exc).__name__}",
                     "say": "I could not turn that into words, so nothing was decided."}
    heard = " ".join(str(heard).split())[:200]
    word = match_words(heard)
    if not word:
        with _READY_LOCK:
            row_out = _READOUTS.get(card_id) or {}
            asked = int(row_out.get("asked") or 0)
            if card_id in _READOUTS:
                _READOUTS[card_id]["asked"] = asked + 1
        if asked == 0:
            _audit("handsfree.unclear", {"card": card_id, "heard": heard, "clip": clip})
            return 200, {"ok": False, "heard": heard, "decision": "again",
                         "card_state": "pending", "say": SAID_AGAIN}
        word = "deny"
        _audit("handsfree.assumed_deny", {"card": card_id, "heard": heard, "clip": clip})
    approved = word == "confirm"
    if approved:
        try:
            ok = approve_one(card_id, action, decide=decide, stamp=stamp)
        except Exception as exc:
            return 503, {"ok": False, "heard": heard, "decision": "refused",
                         "card_state": "unchanged",
                         "error": f"the approval: {type(exc).__name__}",
                         "say": "The approval could not be recorded, so nothing "
                                "was decided."}
    else:
        try:
            ok = bool((decide or _decide_default)(card_id, False))
        except Exception as exc:
            return 503, {"ok": False, "heard": heard, "decision": "refused",
                         "card_state": "unchanged",
                         "error": f"the refusal: {type(exc).__name__}",
                         "say": "The refusal could not be recorded, so nothing "
                                "was decided."}
    if not ok:
        _clear(card_id)
        return 409, {"ok": False, "heard": heard, "decision": "refused",
                     "card_state": "gone", "say": SAID_GONE}
    _clear(card_id)
    decision = "approved" if approved else "denied"
    _audit("handsfree.answer", {"card": card_id, "action": action,
                               "heard": heard, "decision": decision,
                               "clip": clip, "by": BY})
    said = SAID_APPROVED if approved else (
        SAID_DENIED if word == "deny" and match_words(heard) == "deny"
        else SAID_UNCLEAR_DENIED)
    return 200, {"ok": True, "heard": heard, "decision": decision,
                 "card_state": decision, "say": said, "card_id": card_id,
                 "action": action}


# --------------------------------------------------------------------------
#   Text messages: the card, the dispatch, the receipt
# --------------------------------------------------------------------------

MAX_CONTACT = 80
MAX_TEXT = 600
MAX_RECEIPT = 300

SMS_CARD_LEAD = "Send a text message to {contact}:"
SMS_CARD_TAIL = ("Your phone looks the contact up in its own contacts and sends "
                 "it - Jarvis never stores a phone number, and nothing is sent "
                 "until you approve this card.")


def _clean_contact(value) -> str:
    contact = " ".join(str(value or "").split())
    if not contact:
        raise Refused("Which contact should the text go to? Nothing was sent.")
    if len(contact) > MAX_CONTACT:
        raise Refused(f"That contact name is longer than {MAX_CONTACT} "
                      "characters, so I did not send anything.")
    return contact


def _clean_text(value) -> str:
    text = str(value or "").strip()
    if not text:
        raise Refused("What should the message say? Nothing was sent.")
    if len(text) > MAX_TEXT:
        raise Refused(f"That message is longer than {MAX_TEXT} characters, "
                      "so I did not send anything.")
    return text


def _devices_status():
    import jarvis_devices
    return jarvis_devices.paired_status()


def _phone_ready(status: Optional[Callable] = None) -> tuple:
    """(ready, why): is there a paired phone that can receive the command?

    Honest about what it knows: a paired phone is not a phone that is awake.
    The command rides the event stream, which keeps a ring of recent events,
    so a phone that reconnects shortly after still receives it - and the
    answer says which of those happened rather than claiming it was sent.
    """
    try:
        st = (status or _devices_status)() or {}
    except Exception as exc:
        return False, (f"I could not read the list of paired devices "
                       f"({type(exc).__name__}), so nothing was sent.")
    if not st.get("readable", True):
        return False, "I could not read the list of paired devices, so nothing was sent."
    phones = [d for d in (st.get("devices") or [])
              if str(d.get("kind") or "phone") == "phone" and not d.get("removed")]
    if not phones:
        return False, ("No phone is paired with this PC, so I cannot send a "
                       "text from it. Pair your phone in Settings first.")
    seen = max([d.get("last_seen") for d in phones
                if isinstance(d.get("last_seen"), (int, float))], default=None)
    if seen is None:
        return True, "Your phone has not checked in since it was paired; it will get this when it next connects."
    age = time.time() - float(seen)
    if age > 86400:
        return True, (f"Your phone was last seen {int(age // 3600)} hours ago; it "
                      "will get this when it next connects.")
    return True, ""


def prepare_sms(args: dict, *, phone: Optional[Callable] = None) -> tuple:
    """prepare() for `send_text_message`. Returns (state, the card's words).

    Refuses BEFORE any card when hands-free is off or the phone cannot take
    the command, in one sentence - the card would otherwise promise a send
    that cannot happen.
    """
    if not enabled():
        raise Refused("Hands-free mode is off, so I cannot send a text message "
                      "for you. Turn it on first - it is one approval card - "
                      "then ask me again.")
    if not isinstance(args, dict):
        raise Refused("I need a contact and the message text. Nothing was sent.")
    contact = _clean_contact(args.get("contact"))
    text = _clean_text(args.get("text"))
    ready, why = _phone_ready(phone)
    if not ready:
        raise Refused(why or "Your phone cannot take the message, so nothing was sent.")
    state = {"contact": contact, "text": text, "at": time.time(),
             "id": uuid.uuid4().hex[:16]}
    card = (SMS_CARD_LEAD.format(contact=contact) + "\n\n" + text + "\n\n"
            + SMS_CARD_TAIL)
    return state, card


#: id -> the dispatch the phone has not reported on yet. In memory: a result
#: for an id this process never sent is refused, never recorded as a receipt.
_DISPATCHES: dict = {}


def send(state: dict, *, publish: Optional[Callable] = None,
         phone: Optional[Callable] = None) -> dict:
    """execute() for `send_text_message`: the card said yes, so hand the
    command to the phone. It NEVER reports the text as sent - only asked."""
    contact = _clean_contact((state or {}).get("contact"))
    text = _clean_text((state or {}).get("text"))
    ready, why = _phone_ready(phone)
    if not ready:
        return {"ok": False, "sent": False, "error": why or
                "Your phone cannot take the message, so nothing was sent."}
    dispatch = {"id": str((state or {}).get("id") or uuid.uuid4().hex[:16]),
                "contact": contact, "text": text, "at": time.time()}
    with _READY_LOCK:
        _DISPATCHES[dispatch["id"]] = dispatch
    try:
        (publish or _publish_default)(PHONE_COMMAND_KIND, {
            "id": dispatch["id"], "kind": "send_sms",
            "contact": contact, "text": text})
    except Exception as exc:
        with _READY_LOCK:
            _DISPATCHES.pop(dispatch["id"], None)
        return {"ok": False, "sent": False,
                "error": f"your phone could not be reached ({type(exc).__name__}), "
                         "so nothing was sent"}
    _audit("handsfree.sms_queued", {"id": dispatch["id"],
                                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                    "chars": len(text)})
    said = (f'Asked your phone to send your text to {contact}. It is not sent '
            "until your phone reports back.")
    out = {"ok": True, "queued": True, "sent": False, "id": dispatch["id"],
           "contact": contact, "said": said}
    if why:
        out["phone_note"] = why
    return out


def receipts_path() -> Path:
    return _config_dir() / RECEIPTS_NAME


def record_receipt(row: dict, *, path: Optional[Path] = None) -> dict:
    """Append one receipt, keeping the newest RECEIPTS_KEPT. The message text
    is NOT stored: its sha256 and length are, so a receipt can be tied to what
    was approved without keeping the words."""
    p = Path(path) if path is not None else receipts_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        rows = doc.get("receipts") if isinstance(doc, dict) else None
    except Exception:
        rows = None
    rows = list(rows or [])
    rows.append(dict(row, at=float(row.get("at") or time.time())))
    doc = {"receipts": rows[-RECEIPTS_KEPT:]}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        return {"ok": False, "error": "the receipt could not be written"}
    return {"ok": True, "kept": len(doc["receipts"])}


def receipts(*, path: Optional[Path] = None) -> list:
    p = Path(path) if path is not None else receipts_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return list(doc.get("receipts") or []) if isinstance(doc, dict) else []
    except Exception:
        return []


def phone_result(body, *, publish: Optional[Callable] = None) -> tuple[int, dict]:
    """POST /api/phone/result {"id", "ok", "receipt", "why"}.

    The phone's own word on what happened. Until it arrives, nothing anywhere
    says a text was sent; an id this process did not hand out is refused.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"id", "ok", "receipt", "why"}'}
    rid = body.get("id")
    if not isinstance(rid, str) or not rid.strip():
        return 400, {"ok": False, "error": 'need {"id": "<the command id>"}'}
    rid = rid.strip()
    with _READY_LOCK:
        dispatch = _DISPATCHES.pop(rid, None)
    if not dispatch:
        return 409, {"ok": False, "error": "no text message is waiting on that id"}
    sent = bool(body.get("ok"))
    receipt = " ".join(str(body.get("receipt") or "").split())[:MAX_RECEIPT]
    why = " ".join(str(body.get("why") or "").split())[:MAX_RECEIPT]
    contact = str(dispatch.get("contact") or "")
    said = (f"Your text to {contact} went through." if sent else
            f"Your text to {contact} did not send" + (f": {why}." if why else "."))
    row = {"id": rid, "contact": contact, "ok": sent, "receipt": receipt,
           "why": why, "chars": len(str(dispatch.get("text") or "")),
           "text_sha256": hashlib.sha256(
               str(dispatch.get("text") or "").encode("utf-8")).hexdigest()}
    record_receipt(row)
    _audit("handsfree.sms_result", {"id": rid, "ok": sent,
                                    "receipt": receipt[:120], "why": why[:120]})
    try:
        (publish or _publish_default)(PHONE_RESULT_KIND,
                                     {"id": rid, "ok": sent, "say": said,
                                      "receipt": receipt, "why": why})
    except Exception:
        pass
    return 200, {"ok": True, "id": rid, "sent": sent, "say": said,
                 "receipt": receipt, "why": why}


# --------------------------------------------------------------------------
#   Audit
# --------------------------------------------------------------------------

def _audit(event: str, detail: dict) -> None:
    """Never raises into a caller. The clip's sha256 and the heard words only:
    no audio, no contact list, no phone number, and the message text only
    ever as a hash."""
    try:
        import jarvis_framework as fw
        fw.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Routes (installed by plugins/ready/handsfree - no patch to jarvis_hud.py)
# --------------------------------------------------------------------------

PATH = "/api/handsfree"
ANSWER_PATH = "/api/handsfree/answer"
PHONE_RESULT_PATH = "/api/phone/result"

_ARMED = False
_ROUTE_LOCK = threading.RLock()


def handle_post(route: str, body) -> tuple[int, dict]:
    """The three POST routes, as (code, body). No server needed to test."""
    if route == PATH:
        if not isinstance(body, dict):
            return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
        return request_enabled(body.get("enabled"))
    if route == ANSWER_PATH:
        if not isinstance(body, dict):
            return 400, {"ok": False, "heard": "", "decision": "refused",
                         "card_state": "unchanged",
                         "error": "That answer needs the card's id and the recorded sound."}
        return answer(body.get("card_id"), body.get("data_b64"),
                      body.get("sample_rate", SAMPLE_RATE))
    if route == PHONE_RESULT_PATH:
        return phone_result(body)
    return 404, {"error": "That is not one of the hands-free addresses here."}


def handle_get(route: str) -> tuple[int, dict]:
    if route == PATH:
        return 200, status()
    return 404, {"error": "That is not one of the hands-free addresses here."}


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so the three routes are answered
    here, after the server's own origin and token checks. Every other request
    goes straight to the original - which is why this feature needs no patch
    and no change to jarvis_hud.py."""
    global _ARMED
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    # The owner-check wrapper is installed before this one and only touches
    # /api/approve, so our do_POST sits on top of the full chain and every
    # other route - including the approval routes - reaches it untouched.
    if getattr(get0, "_jarvis_handsfree", False):
        _ARMED = True
        return "  hands-free Watching for cards (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def _parts(self):
        # No urllib here: the route is the part before the query, and nothing
        # in this module needs to parse a URL.
        p = str(getattr(self, "path", "") or "").split("?", 1)[0]
        return p.rstrip("/")

    def do_GET(self):
        route = _parts(self)
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = _parts(self)
        if route not in (PATH, ANSWER_PATH, PHONE_RESULT_PATH):
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_handsfree = True
    do_POST._jarvis_handsfree = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    _ARMED = True
    start()
    return ("  hands-free " + ("on: cards are read out, a spoken yes or no "
                               "answers one" if enabled() else
                               "off (the default); turn it on in Settings or by "
                               "asking"))


def armed() -> bool:
    return _ARMED


if __name__ == "__main__":       # a quick, read-only look
    st = status()
    print(json.dumps(st, indent=1))
