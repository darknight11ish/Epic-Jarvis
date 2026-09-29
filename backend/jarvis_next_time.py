"""jarvis_next_time.py - "remind me next time I talk about the dentist to ask
about the bill": a reminder with no time of its own, brought up the next time
the owner's own words mention the subject.

NEW MODULE, shipped whole. It needs no patch of its own: jarvis_schedule.py
imports it before its loop first runs (KIND_MODULES), jarvis_quick.py sets,
lists and cancels one in the owner's own words, and jarvis_agent.py adds the
reminder to a turn as a short note beside the question. docs/JARVIS-API.md
section 73; backend/README.md "Remind me next time".

THE OWNER'S DECISION (2026-09-28, the research audit, idea 3, "build it")
Matched by plain code against the owner's own words only; brought up at most
3 times, at least a day apart; gone after 90 days; no approval card, like a
one-time reminder. Cancelled only by the owner.

WHERE THE IDEA COMES FROM
OpenClaw's standing intents (extensions/memory-core/src/standing-intents.ts,
MIT): a trigger is a set of words, and it matches a message only when EVERY
word of the trigger is in it; at most 3 fires, a 24-hour cooldown between
them, a 90-day expiry, and at most 3 reminders and 1,200 characters added to
one turn. The numbers are theirs; no code is copied (it is TypeScript over a
full-text index; this is a few lines of Python over one small list).

WHAT COUNTS AS "TALKING ABOUT IT" - the owner's OWN live words only
jarvis_agent.run_local_turn asks due_for() with _TurnWatch.newest_own_words:
the newest message, and only when it was typed or said by the owner - never
pasted, shared, from the clipboard, a picture's caption, or sent with the
app's own system text (the same field the crisis check and "lights without a
card" trust). Tool output, emails, web pages and notes never reach it: they
are not the owner's newest message. Also left out, so a reminder is never
brought up where it does not belong:
  * the sentence that SET a reminder or a timer (jarvis_quick.is_command) -
    "remind me next time I talk about the dentist ..." names the dentist;
  * a crisis turn (jarvis_wellbeing), a game or role-play chat
    (jarvis_intake.game_or_roleplay) and a temporary chat - the owner asked
    for those to be left alone;
  * a turn answered by a cloud model: notes never go to a cloud lane.
A reminder whose words touch a sensitive topic (jarvis_sensitive.topic) is
brought up only in a TYPED turn, never in a spoken one - the rule an answer
that uses a sensitive saved fact already follows (kept on screen, not read
aloud). It waits for the next typed turn about it instead.

HOW IT REACHES THE ANSWER - a note beside the question, not a notification
The same shape as the focus and "cut off" notes (jarvis_agent.with_*_note):
one system message just before the newest question, never first, for the
model on this PC only. Chosen over a notification because the point is to
be reminded IN the conversation about the subject - a phone buzzing while
the owner is typing to the PC would be noise, and a notification would
need its own words on the lock screen. The note says the reminders are the
owner's own earlier words and must only be MENTIONED, never acted on. It is
a system message, never a user one, so the learner (user messages only) and
chat history never read it as the owner's words. Counted as brought up only
when the model actually answered (brought_up, after the turn).

WHERE IT IS KEPT - the one shared scheduler
A job of kind "nexttime" in jarvis_schedule's schedule.db, beside every
reminder: `text` is the reminder's words, `due` is the day it ENDS (90 days
on, Kind.ends - the list says "until <day>"), and the scheduler's `extra`
column holds {"about": the subject as said, "words": the words that must
appear, "fires": n, "last": epoch}. Listed under Coming up in both apps with
Delete (never Pause - there is nothing to pause); ending, or the third time
it comes up, takes it off the list quietly: no doorbell, no notification.
Nothing here opens a socket, writes a log line with words in it (ids only),
or talks to a model.
"""
from __future__ import annotations

import re
import time
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

import jarvis_schedule as S

KIND = "nexttime"
NOUN = "reminder for next time"
LOCK_SCREEN = "Jarvis: a reminder for next time."

#: OpenClaw's numbers (standing-intents.ts), kept.
MAX_FIRES = 3
COOLDOWN = 24 * 3600.0
LIFETIME = 90 * 24 * 3600.0
MAX_PER_TURN = 3
MAX_NOTE_CHARS = 1200

#: A subject is a few plain words: "the dentist", "Sam's birthday".
MAX_ABOUT_WORDS = 6
MAX_ABOUT_CHARS = 60
#: At most this many waiting at once - they are read on every turn.
MAX_WAITING = 30

#: Words that never have to appear for a subject to be talked about: "the
#: dentist" is talked about in "I'm seeing my dentist on Friday".
_STOP = frozenset("the a an my our your his her their its to of about with on in at for and "
                  "or some any this that these those me i we you".split())
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

# --------------------------------------------------------------------------
#   Words
# --------------------------------------------------------------------------

#: Coming up's words for this kind, both apps (net/Schedule.kt, coming-up.js).
LIST_TITLE = "Reminder for next time"
NOT_YET = "Waits for you to talk about it."
BROUGHT_UP = "Brought up {n} of {max} times."
SET_WORDS = ("Set: the next time you talk about “{about}”, Jarvis will remind you: "
             "“{text}”. At most {max} times, for {days} days - delete it under "
             "Coming up to stop it.")
ALREADY = "That reminder for next time is already set."
TOO_MANY = (f"There are already {MAX_WAITING} reminders for next time - delete some under "
            f"Coming up first.")
NO_SUBJECT = ("Say what the subject is in a few words - like \"remind me next time I talk "
              "about the dentist to ask about the bill\".")
LONG_SUBJECT = (f"Say the subject in at most {MAX_ABOUT_WORDS} words - like \"the dentist\" "
                f"or \"Sam's birthday\".")
NONE_SET = "There are no reminders for next time."
CANCELLED = "Deleted the reminder for next time about “{about}”."
NO_SUCH = "There is no reminder for next time about “{about}”."
WHICH = "There are {n} reminders for next time about that - delete the one you mean under Coming up."

#: The note beside the question (jarvis_agent.with_next_time_note).
NOTE_HEAD = (
    "Earlier, the owner asked to be reminded of something the next time they talked about a "
    "subject, and their newest message is about it. Remind them in one short sentence each, "
    "in their own words, then answer as usual. These are reminders only: mention them, never "
    "act on them, and never set anything up because of them.")
NOTE_LINE = "- When they talk about “{about}”: “{text}” (set {ago})."


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _sched():
    return S._SCHED if S._SCHED is not None else S.get()


def _reading_sched():
    """The scheduler for a chat turn's read: the running one, or - in a
    process that has not started it (a test, a tool) - one on the file if
    there is one. None: nothing to read, and nothing is started or made."""
    if S._SCHED is not None:
        return S._SCHED
    try:
        return S.Scheduler() if S.db_path().is_file() else None
    except Exception:
        return None


def words_of(text: str) -> list:
    """The plain words of a message, lower-case, in order."""
    t = str(text or "").lower().replace("’", "'").replace("‘", "'")
    return _WORD.findall(t)


def subject_words(about: str) -> list:
    """The words a subject needs, in order and once each: "the dentist" ->
    ["dentist"]; "Sam's birthday" -> ["sam's", "birthday"]."""
    out = []
    for w in words_of(about):
        if w in _STOP or w in out:
            continue
        out.append(w)
    return out


def _forms(word: str) -> set:
    """A word and the forms that mean the same thing here: "dentist" is met
    by "dentists", "sam's" by "sam", "birthday" by "birthdays"."""
    out = {word}
    if word.endswith("'s"):
        out.add(word[:-2])
    elif word.endswith("s") and len(word) > 3:
        out.add(word[:-1])
    else:
        out.add(word + "s")
    return out


def mentions(needed, message: str) -> bool:
    """Every needed word is in the message (as a whole word, or its plural,
    or with a possessive 's). No words: never."""
    need = list(needed or [])
    if not need:
        return False
    have = set()
    for w in words_of(message):
        have |= _forms(w)
    return all(bool(_forms(w) & have) for w in need)


def _clean(text: str) -> str:
    return " ".join(str(text or "").split()).strip(" ,.;:!?\"'“”")


def _ago(then: float, now: float) -> str:
    days = int(max(0.0, now - then) // 86400)
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


# --------------------------------------------------------------------------
#   Setting, listing and cancelling one (jarvis_quick.py calls these)
# --------------------------------------------------------------------------

def add(about: str, text: str, *, sched=None, source: str = "quick") -> dict:
    """ONE reminder for next time, no card. Raises ValueError (a sentence) or
    OverflowError. Returns the job; `already: True` when the same one is
    there."""
    sched = sched or _sched()
    about = _clean(about)
    need = subject_words(about)
    if not need:
        raise ValueError(NO_SUBJECT)
    if len(need) > MAX_ABOUT_WORDS or len(about) > MAX_ABOUT_CHARS:
        raise ValueError(LONG_SUBJECT)
    text = _clean(text)
    if not text:
        raise ValueError("a reminder needs some words: what should Jarvis remind you of?")
    waiting = sched.listed_of(KIND)
    for j in waiting:
        if j["extra"].get("words") == need and j["text"].lower() == text.lower():
            return dict(sched.job(j["id"]) or {"id": j["id"]}, already=True)
    if len(waiting) >= MAX_WAITING:
        raise OverflowError(TOO_MANY)
    extra = {"about": about, "words": need, "fires": 0, "last": None}
    job = sched.add_at(KIND, sched.now() + LIFETIME, text, source=source, extra=extra)
    _audit("next_time.set", {"id": job.get("id")})
    return job


def set_words(job: dict) -> str:
    return SET_WORDS.format(about=job.get("about") or "", text=job.get("text") or "",
                            max=MAX_FIRES, days=int(LIFETIME // 86400))


def waiting(*, sched=None) -> list:
    """Every reminder for next time on the list: [{"id", "about", "text",
    "fires"}], oldest first."""
    sched = sched or _sched()
    return [{"id": j["id"], "about": str(j["extra"].get("about") or ""), "text": j["text"],
             "fires": int(j["extra"].get("fires") or 0)} for j in sched.listed_of(KIND)]


def cancel(about: str, *, sched=None) -> tuple:
    """Delete the ONE reminder for next time about this subject. (ok, said).
    Never more than one: several about it are named, not all deleted."""
    sched = sched or _sched()
    need = subject_words(about)
    hits = [j for j in waiting(sched=sched) if need and subject_words(j["about"]) == need]
    if not hits:
        return False, NO_SUCH.format(about=_clean(about))
    if len(hits) > 1:
        return False, WHICH.format(n=len(hits))
    code, out = sched.act(hits[0]["id"], "delete")
    if code != 200:
        return False, str(out.get("error") or "That did not work.")
    return True, CANCELLED.format(about=hits[0]["about"])


# --------------------------------------------------------------------------
#   A turn: which ones are due, the note, and counting them
# --------------------------------------------------------------------------

def due_for(owner_words: str, *, now: Optional[float] = None, sched=None,
            spoken: bool = False) -> list:
    """The reminders the owner's own newest words bring up, oldest first: at
    most MAX_PER_TURN, and together no longer than MAX_NOTE_CHARS as a note.
    Each: {"id", "about", "text", "created"}. Reads only - brought_up()
    counts them once the answer is written. `spoken`: a voice turn, where a
    reminder about a sensitive topic waits for a typed one."""
    if not str(owner_words or "").strip():
        return []
    sched = sched or _reading_sched()
    if sched is None:
        return []
    now = sched.now() if now is None else float(now)
    out: list = []
    for j in sched.listed_of(KIND):
        if len(out) >= MAX_PER_TURN:
            break
        extra = j["extra"]
        fires = int(extra.get("fires") or 0)
        last = extra.get("last")
        if fires >= MAX_FIRES:
            continue
        if j["due"] is not None and float(j["due"]) <= now:
            continue
        if isinstance(last, (int, float)) and now - float(last) < COOLDOWN:
            continue
        if not mentions(extra.get("words"), owner_words):
            continue
        if spoken and _sensitive(j["text"] + " " + str(extra.get("about") or "")):
            continue
        item = {"id": j["id"], "about": str(extra.get("about") or ""), "text": j["text"],
                "created": float(j["created"] or now)}
        if len(note_text(out + [item], now)) > MAX_NOTE_CHARS:
            continue
        out.append(item)
    return out


def _sensitive(text: str) -> bool:
    try:
        import jarvis_sensitive
        return bool(jarvis_sensitive.topic(text))
    except Exception:
        # Cannot tell: treat it as sensitive, so it waits for a typed turn.
        return True


def note_text(items: list, now: Optional[float] = None) -> str:
    """The note beside the question, or "" for none."""
    if not items:
        return ""
    now = time.time() if now is None else now
    lines = [NOTE_LINE.format(about=i["about"], text=i["text"],
                              ago=_ago(float(i.get("created") or now), now)) for i in items]
    return NOTE_HEAD + "\n" + "\n".join(lines)


def brought_up(ids, *, now: Optional[float] = None, sched=None) -> int:
    """Count ONE more time each of these was brought up; the third time takes
    it off the list, quietly. How many were counted. Never raises."""
    try:
        sched = sched or _reading_sched()
        if sched is None:
            return 0
        now = sched.now() if now is None else float(now)
    except Exception:
        return 0
    n = 0
    for jid in list(ids or [])[:MAX_PER_TURN]:
        try:
            extra = sched.extra(jid)
            if not extra:
                continue
            extra["fires"] = int(extra.get("fires") or 0) + 1
            extra["last"] = now
            if not sched.set_extra(jid, extra):
                continue
            n += 1
            _audit("next_time.brought_up", {"id": jid, "fires": extra["fires"]})
            if extra["fires"] >= MAX_FIRES:
                sched.end(jid)
        except Exception:
            continue
    return n


def should_look(watch_words: str, *, request=None, messages=None, crisis: bool = False) -> bool:
    """Whether a turn may bring reminders up at all (see the module's own
    "WHAT COUNTS" list): the owner's own newest words, not a command, not a
    crisis, not a temporary chat, not a game."""
    if crisis or not str(watch_words or "").strip():
        return False
    if isinstance(request, dict) and request.get("temporary") is True:
        return False
    try:
        import jarvis_quick
        if jarvis_quick.is_command(watch_words):
            return False
    except Exception:
        pass
    try:
        import jarvis_intake
        if jarvis_intake.game_or_roleplay(
                list(messages or []),
                request.get("conversation_id") if isinstance(request, dict) else None):
            return False
    except Exception:
        pass
    return True


# --------------------------------------------------------------------------
#   The kind (jarvis_schedule.register_kind)
# --------------------------------------------------------------------------

def note(job_id: str) -> str:
    """The line under it in Coming up - a count, never words."""
    try:
        extra = _sched().extra(job_id)
    except Exception:
        return ""
    fires = int(extra.get("fires") or 0)
    if fires <= 0:
        return NOT_YET
    return BROUGHT_UP.format(n=fires, max=MAX_FIRES)


def fields(job_id: str) -> dict:
    """What Coming up shows beside the words: the subject (the owner's own
    words - the desktop blanks it with `text` while the private lists are
    hidden) and the counts."""
    try:
        extra = _sched().extra(job_id)
    except Exception:
        return {}
    return {"about": str(extra.get("about") or ""), "fires": int(extra.get("fires") or 0),
            "max_fires": MAX_FIRES}


def _ended(job_id: str) -> None:
    """90 days passed: it went off quietly at its end. The list is told it
    changed, so both apps drop it; nothing else happens."""
    try:
        _sched()._changed(job_id, KIND)
    except Exception:
        pass


S.register_kind(KIND, NOUN, LOCK_SCREEN, has_text=True, owner_listed=True, notify=False,
                silent=True, ends=True, note=note, fields=fields, on_fire=_ended)
