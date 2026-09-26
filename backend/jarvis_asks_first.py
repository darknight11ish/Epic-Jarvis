"""jarvis_asks_first.py - "What asks first": every action Jarvis can take and
whether it asks you first, in plain words; "make stricter" switches; on the
PC only, loosening a short safe list; and the "lights, plugs and fans
without a card" setting.

NEW MODULE, shipped whole. asks-first.patch adds the routes (jarvis_hud.py)
and the gate's words for the loosening card (jarvis_gate.py). Both apps show
the page: the desktop in Settings, "What asks first"; the phone on Mind.
docs/JARVIS-API.md section 32; backend/README.md "What asks first".

THE OWNER'S DECISIONS (2026-09-26, after the approvals audit,
docs/APPROVALS-AUDIT-2026-09-26.md; CLAUDE.md)
  * A "What asks first" page in both apps lists every action and whether it
    asks, in plain words, with "make stricter" switches. On the PC only,
    the owner may also loosen a short safe list - one card plus Windows
    Hello per change. Nothing outside that list can be loosened from an app.
  * Lights, plugs and fans: a setting, off by default, lets Jarvis switch
    devices the owner names without a card. Turning it on raises a card;
    turning it off is immediate. Never after outside text in the turn.
    Locks, doors, alarms and covers always keep a card of their own.

WHAT THE PAGE READS
The same things the gate reads: each action's tier in [autonomy.tiers] of
jarvis-framework.toml (jarvis_framework.action_tier - a missing line is
`unknown_action_tier`, "ask"), the tools jarvis_agent.py only ever runs on
a person's yes (NEEDS_A_PERSON), and the actions whose own module refuses
anything but "ask" (MUST_ASK below). Titles are the approval cards' own
words (jarvis_card_words.TITLES), so a row says what its card says.

MAKING SOMETHING STRICTER - immediate, no card, from either app
For an action on SWITCHABLE only (below): its line becomes "ask". It only
makes Jarvis ask more, like every "turn off" switch in both apps. It also
withdraws a waiting card that would loosen the same action.

LOOSENING - the PC only, ONE card plus Windows Hello, SWITCHABLE only
Its line goes back to the tier this repository ships for it (LOOSE). The
backend refuses it - not only the apps:
  * for any action not on SWITCHABLE (403), which never holds anything in
    NEEDS_A_PERSON or HARD_LIMITS (the tests check the two never meet);
  * from any device but this PC (403, jarvis_owner_check.from_this_pc -
    loopback, the PC's own addresses, or anything that cannot be placed);
  * when this backend cannot ask Windows Hello itself (owner-check.patch
    not armed: 503) - the card must meet Windows Hello, and without the
    backend's own check a program holding the token could approve it;
  * unless LOOSEN_ACTION's tier is "ask" (a line cannot be the owner's yes).
The card is action LOOSEN_ACTION. jarvis_owner_check.PC_ONLY_ACTIONS makes
its approval need Windows Hello whatever its risk says, and refuses it from
any other device, so a phone (or anything pretending to be one) cannot
approve it. Only "approved" from a person writes the line (the stamp and
the gate's outcome - never `allowed` alone).

THE SHORT SAFE LIST, AND WHAT IS LEFT OFF IT
SWITCHABLE = reading your own calendar, email, notes and home status, and
the three note writes (Obsidian daily note, Logseq journal, a new Joplin
note). Each acts only on the owner's own things on this PC. After outside
text a note still waits for a yes (write_notes_after_outside_text, which is
not on the list), and a read still marks the chat as having read outside
text.
The wiki was on the owner's list, and is NOT here, said plainly: since the
security audit (L1) jarvis_wiki.py writes the wiki only on a person's yes
whatever wiki_update's tier says, so a looser line would switch "Add to
wiki" off, not stop it asking. Its row says so.

WRITING THE SETTINGS FILE (set_tier)
Only the one `<action> = "<tier>"` line under [autonomy.tiers] changes - its
value, nothing else - or, when the file has no line for it, one new line is
added after the table's last line. Every other byte (comments, spacing,
line endings, a byte-order mark) is kept. The new text is parsed before it
is written, and it must parse to exactly the old settings with that one
tier changed, or nothing is written. Written to a temporary file beside it
and moved into place in one step (os.replace), so the file is never half
written. An unusual file (the table written some other way, the key twice,
not UTF-8) is refused with a sentence saying to edit it by hand.

THE LIGHTS SETTING ("Lights, plugs and fans without a card")
Off by default. The shape of every setting that trusts more
(jarvis_briefing.py SENDERS, jarvis_auto_learn.py): OFF is immediate and
withdraws a waiting ON card; ON is ONE card, action `change_own_config`,
tier "ask" only. Kept in `asks_first.json` in the Jarvis settings folder:
{"lights": bool, "changed": epoch}. No file: off. A damaged file: off.
jarvis_agent.py asks lights_without_card() before it puts a home_control
call to the gate - see that function for every condition.

Standard library only. Nothing here opens a socket.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

try:
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - Python before 3.11
    try:
        import tomli as _toml  # type: ignore
    except ModuleNotFoundError:
        _toml = None  # type: ignore

PATH = "/api/asks_first"

# ---------------------------------------------------------------------------
# The words both apps show
# ---------------------------------------------------------------------------

TITLE = "What asks first"
DETAIL = ("Everything Jarvis can do that might need your OK, and whether it asks you first. "
          "The PC writes this list from its own settings - the AI model does not write it. "
          "\"Ask me first\" makes one ask every time, at once, from either app. Letting one "
          "go ahead without asking is only for the short list below, only on the PC, and "
          "takes an approval card and Windows Hello.")
MISSING = ("Your PC's Jarvis cannot show what asks first yet - run apply-patches.ps1 on the "
           "PC.")
SWITCH_LABEL = "Ask me first"
PHONE_LOOSEN = ("To let this go ahead without asking, use the PC: Settings, What asks first. "
                "It takes an approval card and Windows Hello.")
WAITING = "Waiting for your yes on the approval card, and Windows Hello, on your PC."

#: How each tier is said.
SAYS = {
    "auto": "Does it without asking",
    "notify": "Does it, then tells you",
    "ask": "Asks you first, every time",
    "never": "Never - your settings file switches it off",
}
#: An action that only ever runs on a person's yes, set looser in the file.
SAYS_REFUSED = "Refused - it only runs on your yes, so its line must say \"ask\""
#: The fixed rows (no tier: decided in the code, by the owner).
SAYS_NO_CARD = "Does it without asking"

#: The notes under a row.
NOTE_ALWAYS = "Always asks. This cannot be changed from an app."
NOTE_FILE = "Only your settings file (jarvis-framework.toml) changes this one."
NOTE_WIKI = ("Always asks: the wiki is written only on your yes (security audit), so it "
             "cannot be loosened - a looser line would switch \"Add to wiki\" off.")
NOTE_READ = ("Asking first also leaves it out of the morning briefing and \"tell me when\", "
             "which cannot stop to ask.")
NOTE_NOTE = "After Jarvis has read outside text in a chat, a note still waits for your yes."

# ---------------------------------------------------------------------------
# The lists
# ---------------------------------------------------------------------------

#: The actions the apps may switch, and the tier this repository ships for
#: each - what "loosen" writes back. Nothing else can be loosened from an
#: app, by the backend's own refusal.
LOOSE = {
    "calendar_read": "auto",
    "email_read": "auto",
    "notes_search": "auto",
    "home_read": "auto",
    "append_obsidian_daily": "auto",
    "append_logseq_journal": "auto",
    "create_joplin_note": "notify",
}
SWITCHABLE = tuple(LOOSE)

#: The approval card for loosening one of them. jarvis_owner_check.
#: PC_ONLY_ACTIONS holds the same name.
LOOSEN_ACTION = "loosen_what_asks_first"

#: Never loosened from an app, whatever else changes: anything that leaves
#: the PC, deletes, sends, spends, moves a lock or a door, touches secrets
#: or loosens a security or privacy setting - and the actions whose module
#: accepts only "ask". test_asks_first.py checks SWITCHABLE never meets it.
HARD_LIMITS = frozenset({
    "send_email", "draft_email", "spend_money", "delete_file", "delete_calendar_event",
    "edit_calendar_event", "delete_joplin_note", "delete_logseq_page", "edit_joplin_note",
    "edit_logseq_page", "run_shell_on_host", "control_computer", "control_phone",
    "control_browser", "home_control", "post_to_external_service", "open_public_tunnel",
    "search_the_web", "web_research", "research_authenticated",
    "write_notes_after_outside_text", "change_own_config", "modify_own_code",
    LOOSEN_ACTION, "stop_asking_before_every_web_search", "learning_enable",
    "learning_auto_enable", "learning_sensitive_enable", "history_enable",
    "second_card_enable", "second_card_browser_enable", "big_model_enable", "custom_voice",
    "better_voice_enable", "download_model", "switch_model", "models_create",
    "schedule_repeat", "wiki_update", "memory_manage", "user_profile_manage",
    "agent_spawn", "agent_kill", "execute_pending_actions", "unclassified_tool",
})

#: Actions whose own module refuses anything but "ask" (a looser line
#: switches the feature off rather than removing the card) - the toml's
#: "Must stay 'ask'" lines, and the gate actions of NEEDS_A_PERSON's tools.
MUST_ASK = frozenset({
    "send_email", "run_shell_on_host", "control_computer", "control_phone", "control_browser",
    "home_control", "web_research", "research_authenticated", "write_notes_after_outside_text",
    "search_the_web", "stop_asking_before_every_web_search", "schedule_repeat",
    "models_create", "second_card_enable", "second_card_browser_enable", "big_model_enable",
    "learning_enable", "learning_auto_enable", "learning_sensitive_enable", "history_enable",
    "custom_voice", "better_voice_enable", "change_own_config", "modify_own_code",
    "wiki_update", LOOSEN_ACTION,
})

#: The page's groups, in order: (title, [action or fixed-row id]). A fixed
#: row (FIXED) has no tier: the owner decided it and the code does it.
GROUPS = (
    ("Reading your own things", ["calendar_read", "email_read", "notes_search", "home_read",
                                 "read_files_readonly", "read_calendar", "read_joplin_note",
                                 "read_logseq_page"]),
    ("Writing your notes", ["append_obsidian_daily", "append_logseq_journal",
                            "create_joplin_note", "create_logseq_page", "edit_joplin_note",
                            "edit_logseq_page", "delete_joplin_note", "delete_logseq_page",
                            "write_notes_after_outside_text", "wiki_update"]),
    ("Timers and reminders", ["fixed:timers", "fixed:repeats", "schedule_repeat"]),
    ("Your smart home", ["fixed:lights", "home_control"]),
    ("Email and calendar", ["draft_email", "send_email", "edit_calendar_event",
                            "delete_calendar_event"]),
    ("The internet", ["search_the_web", "web_research", "research_authenticated",
                      "control_browser", "post_to_external_service", "open_public_tunnel"]),
    ("This PC and your phone", ["run_shell_on_host", "control_computer", "control_phone",
                                "delete_file", "spend_money", "power_manage"]),
    ("AI models and graphics cards", ["browse_model_catalog", "download_model",
                                      "switch_model", "rollback_model", "models_create",
                                      "second_card_enable", "second_card_browser_enable",
                                      "big_model_enable"]),
    ("Jarvis's own settings, memory and voice", [
        "change_own_config", "stop_asking_before_every_web_search", "learning_enable",
        "learning_auto_enable", "learning_sensitive_enable", "history_enable",
        "memory_manage", "user_profile_manage", "custom_voice", "better_voice_enable",
        "modify_own_code", LOOSEN_ACTION]),
    ("Other", ["agent_spawn", "agent_kill", "execute_pending_actions", "unclassified_tool"]),
)

#: The fixed rows: (title, says, note).
FIXED = {
    "fixed:timers": ("Set a timer, or a reminder or alarm that goes off once", SAYS_NO_CARD,
                     "Your own words only; deleting is immediate."),
    "fixed:repeats": ("Set up a repeating reminder or alarm, or the standby schedule",
                      SAYS_NO_CARD,
                      "Your own words only; the answer says when it next goes off, and "
                      "deleting is immediate. A repeating morning briefing and \"tell me when\" "
                      "still ask (below)."),
}

# ---------------------------------------------------------------------------
# What is read, replaceable for the tests
# ---------------------------------------------------------------------------


def _tier(action: str) -> str:
    try:
        t = str(fw.action_tier(action)) if fw is not None else "ask"
    except Exception:
        return "ask"
    return t if t in SAYS else "ask"


def _file_tiers() -> dict:
    try:
        return dict(fw.all_tiers()) if fw is not None else {}
    except Exception:
        return {}


def _title(action: str) -> str:
    """The approval card's own words, as a row title: "Read your calendar"."""
    try:
        import jarvis_card_words as W
        phrase = W.TITLES.get(action)
    except Exception:
        phrase = None
    if not phrase:
        phrase = action.replace("_", " ")
    return phrase[:1].upper() + phrase[1:]


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _config_dir() -> Path:
    if fw is not None:
        try:
            return Path(fw.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def _toml_path() -> Optional[Path]:
    try:
        p = fw.config_path() if fw is not None else None
    except Exception:
        p = None
    return Path(p) if p else None


def _reload() -> None:
    try:
        if fw is not None:
            fw.reload_framework()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def _row(action: str, *, here: bool) -> dict:
    if action in FIXED:
        title, says, note = FIXED[action]
        return {"id": action, "title": title, "says": says, "note": note, "fixed": True}
    if action == "fixed:lights":
        on = lights_setting()["on"]
        return {"id": action, "title": LIGHTS_ROW,
                "says": SAYS_NO_CARD if on else SAYS["ask"],
                "note": LIGHTS_NOTE, "fixed": True, "lights": True}
    tier = _tier(action)
    row = {"id": action, "action": action, "title": _title(action), "tier": tier,
           "says": SAYS[tier], "fixed": False}
    if action in MUST_ASK:
        if tier in ("auto", "notify"):
            row["says"] = SAYS_REFUSED
        row["note"] = NOTE_WIKI if action == "wiki_update" else NOTE_ALWAYS
        return row
    if action in LOOSE:
        if tier != "never":
            row["switch"] = {"asks": tier == "ask", "loose": LOOSE[action],
                             "can_loosen": bool(here)}
        row["note"] = NOTE_READ if action.endswith(("_read", "_search")) else NOTE_NOTE
        if tier == "ask" and not here:
            row["note"] += " " + PHONE_LOOSEN
        return row
    row["note"] = NOTE_FILE
    return row


def view(*, here: bool = False) -> dict:
    """GET /api/asks_first. `here`: the request comes from this PC, so the
    page may offer loosening."""
    groups, seen = [], set()
    for title, ids in GROUPS:
        rows = [_row(a, here=here) for a in ids]
        seen.update(ids)
        groups.append({"title": title, "rows": rows})
    extra = sorted(a for a in _file_tiers() if a not in seen)
    if extra:
        # A line in the owner's file that no group names: shown, never hidden.
        groups[-1]["rows"].extend(_row(a, here=here) for a in extra)
    with _L_LOCK:
        pending = dict(_L_STATE["pending"])
        last = dict(_L_STATE["last"]) or None
    return {"available": True, "title": TITLE, "detail": DETAIL, "switch_label": SWITCH_LABEL,
            "groups": groups, "switchable": list(SWITCHABLE), "can_loosen": bool(here),
            "waiting": ({"action": pending["action"], "title": _title(pending["action"]),
                         "said": WAITING} if pending else None),
            "last": last, "lights": lights_status()}


# ---------------------------------------------------------------------------
# Writing one tier line
# ---------------------------------------------------------------------------

_FILE_LOCK = threading.Lock()
_HEADER = re.compile(r"^[ \t]*\[[ \t]*autonomy[ \t]*\.[ \t]*tiers[ \t]*\][ \t]*(?:#.*)?$")
_ANY_HEADER = re.compile(r"^[ \t]*\[")
_KEY_LINE = re.compile(r"^[ \t]*(?:[A-Za-z0-9_-]+|\"[^\"]*\"|'[^']*')[ \t]*=")
_INSERTED_NOTE = "  # set in the app's \"What asks first\" page"


class TierFileError(Exception):
    """The settings file could not be changed. The message is a sentence for
    the owner."""


HAND_EDIT = ("Your settings file (jarvis-framework.toml) is written in a way this page "
             "cannot change safely, so nothing was changed. Edit the line by hand in "
             "Notepad, under [autonomy.tiers], then restart Jarvis")


def _parse(text: str) -> dict:
    if _toml is None:
        raise TierFileError("This PC's Python cannot read the settings file (it needs "
                            "Python 3.11 or newer), so nothing was changed")
    try:
        return _toml.loads(text)
    except Exception:
        raise TierFileError("Your settings file (jarvis-framework.toml) has a mistake in "
                            "it, so nothing was changed. Open it in Notepad and fix it first")


def _tiers_of(doc: dict) -> dict:
    a = doc.get("autonomy")
    t = a.get("tiers") if isinstance(a, dict) else None
    return t if isinstance(t, dict) else {}


def rewrite(text: str, action: str, tier: str) -> str:
    """`text` with ONE tier line changed (or added). Raises TierFileError.
    Pure: no file is read or written here."""
    if tier not in SAYS or not re.fullmatch(r"[a-z][a-z0-9_]{1,60}", action or ""):
        raise TierFileError("That is not an action and a tier")
    before = _parse(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    heads = [i for i, line in enumerate(lines) if _HEADER.match(line)]
    if len(heads) != 1:
        raise TierFileError(HAND_EDIT)
    start = heads[0] + 1
    end = next((i for i in range(start, len(lines)) if _ANY_HEADER.match(lines[i])),
               len(lines))
    key = re.compile(r"^(?P<lead>[ \t]*(?:" + re.escape(action) + r"|\"" + re.escape(action)
                     + r"\"|'" + re.escape(action) + r"')[ \t]*=[ \t]*)(?P<q>[\"'])"
                     r"(?P<val>[A-Za-z]*)(?P=q)(?P<rest>[ \t]*(?:#.*)?)$")
    hits = [i for i in range(start, end) if key.match(lines[i])]
    if len(hits) > 1:
        raise TierFileError(HAND_EDIT)
    if hits:
        i = hits[0]
        m = key.match(lines[i])
        lines[i] = f"{m.group('lead')}{m.group('q')}{tier}{m.group('q')}{m.group('rest')}"
    else:
        if action in _tiers_of(before):
            # The file has it, but not as one plain line in the table.
            raise TierFileError(HAND_EDIT)
        keys = [i for i in range(start, end) if _KEY_LINE.match(lines[i])]
        at = (keys[-1] + 1) if keys else start
        lines.insert(at, f'{action} = "{tier}"{_INSERTED_NOTE}')
    out = nl.join(lines)
    after = _parse(out)
    want = json.loads(json.dumps(before))
    want.setdefault("autonomy", {}).setdefault("tiers", {})[action] = tier
    if json.loads(json.dumps(after)) != want:
        raise TierFileError(HAND_EDIT)
    return out


def set_tier(action: str, tier: str, *, path: Optional[Path] = None) -> dict:
    """Change ONE tier line in the owner's jarvis-framework.toml, atomically.
    {"ok": True, "from": old, "to": tier}. Raises TierFileError."""
    p = path or _toml_path()
    if p is None or not Path(p).is_file():
        raise TierFileError("Jarvis could not find your settings file "
                            "(jarvis-framework.toml), so nothing was changed")
    p = Path(p)
    with _FILE_LOCK:
        try:
            raw = p.read_bytes()
        except OSError as exc:
            raise TierFileError(f"Your settings file could not be read "
                                f"({type(exc).__name__}), so nothing was changed")
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
        except UnicodeDecodeError:
            raise TierFileError(HAND_EDIT)
        old = str(_tiers_of(_parse(text)).get(action, "")) or "(no line)"
        new = rewrite(text, action, tier)
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
            raise TierFileError(f"Your settings file could not be written "
                                f"({type(exc).__name__}), so nothing was changed")
    _reload()
    return {"ok": True, "from": old, "to": tier}


# ---------------------------------------------------------------------------
# Stricter (either app) and looser (the PC, one card plus Windows Hello)
# ---------------------------------------------------------------------------

_L_LOCK = threading.Lock()
_L_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
#: Held from an approved card's "was it withdrawn?" check through writing the
#: line, and from a stricter press's withdrawing through ITS write - so a
#: stricter press in between is never overwritten by the card. Always taken
#: BEFORE _L_LOCK.
_L_SWITCH = threading.Lock()

LOOSEN_LAST_WORDS = {
    "loosened": "You approved the card, so it no longer asks first.",
    "denied": "The card was turned down, so it still asks first.",
    "timed_out": "Nobody answered the card in time, so it still asks first.",
    "refused": "Your PC's settings do not let this be approved, so it still asks first.",
    "withdrawn": "You made it ask again while the card waited, so approving it changed "
                 "nothing.",
    "failed": "It was approved, but the settings file could not be changed, so it still "
              "asks first.",
}

PC_ONLY = ("Letting Jarvis do this without asking can only be done on the PC (Settings, "
           "What asks first), with an approval card and Windows Hello.")
NOT_ON_LIST = ("Only reading your calendar, email, notes and home status, and adding to "
               "your notes, can be changed from an app. Everything else changes only in "
               "your settings file (jarvis-framework.toml), and some things always ask.")
NO_OWNER_CHECK = ("Your PC's Jarvis cannot ask Windows Hello itself yet, so nothing can be "
                  "loosened from the app - run apply-patches.ps1 on the PC.")


def loosen_card(action: str) -> str:
    phrase = _title(action)
    phrase = phrase[:1].lower() + phrase[1:]
    loose = LOOSE[action]
    after = " and tell you afterwards" if loose == "notify" else ""
    extra = NOTE_NOTE if action in ("append_obsidian_daily", "append_logseq_journal",
                                    "create_joplin_note") else (
        "A chat where it reads something still counts as having read outside text, so a "
        "later web search or note in that chat still asks.")
    return "\n".join([
        f"Let Jarvis {phrase} without asking you first?",
        "",
        f"From now on Jarvis will {phrase} without an approval card{after}. This changes "
        f"one line of your settings file on this PC (jarvis-framework.toml): "
        f"{action} = \"{loose}\". Nothing else in it changes.",
        "",
        extra,
        "",
        "Approving it needs Windows Hello on this PC. You can make it ask again at any "
        "time from either app, and that is instant.",
        "",
        "If you did not just do this, say no.",
        "",
        "If you say no: nothing changes - it keeps asking first.",
    ])


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-asks-first-card", daemon=True).start()


def _owner_check_armed() -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.armed())
    except Exception:
        return False


def _from_this_pc(peer, local) -> bool:
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        # Cannot tell: not this PC, so nothing is loosened (fail closed).
        return False


def _finish(pid: str, action: str, outcome: str, why: str = "") -> None:
    with _L_LOCK:
        if _L_STATE["pending"].get("id") == pid:
            _L_STATE["pending"].clear()
        _L_STATE["withdrawn"].discard(pid)
        if _L_STATE["latest"].get("id") not in (None, pid):
            return
        _L_STATE["last"].clear()
        _L_STATE["last"].update(outcome=outcome, action=action, why=why, at=time.time(),
                                message=LOOSEN_LAST_WORDS.get(outcome, ""))
    _audit("asks_first.loosen.card", {"action": action, "outcome": outcome})


def _person_said_yes(v) -> bool:
    if getattr(v, "allowed", False) is not True:
        return False
    outcome = getattr(v, "outcome", None)
    if outcome is not None:
        return outcome == "approved" and getattr(v, "tier", "ask") == "ask"
    return getattr(v, "tier", None) == "ask"


def _decide(pid: str, action: str, gate: Callable, tier_of: Callable,
            write: Callable) -> None:
    card = loosen_card(action)
    detail = {"text": card, "what": f"{_title(action).lower()} without asking you first",
              "setting": action, "to": LOOSE[action], "leaves_this_pc": False}
    try:
        v = gate(LOOSEN_ACTION, detail, card)
    except Exception as exc:
        return _finish(pid, action, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(LOOSEN_ACTION) != "ask":
        return _finish(pid, action, "refused", f"the gate answered at tier {vtier!r}, which "
                                               f"is not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, action, outcome)
        return _finish(pid, action, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _L_SWITCH:
        with _L_LOCK:
            withdrawn = pid in _L_STATE["withdrawn"]
        if withdrawn:
            return _finish(pid, action, "withdrawn")
        try:
            write(action, LOOSE[action])
        except TierFileError as exc:
            return _finish(pid, action, "failed", str(exc))
        except Exception as exc:
            return _finish(pid, action, "failed", type(exc).__name__)
    _audit("asks_first.tier", {"action": action, "to": LOOSE[action], "how": "loosened"})
    _finish(pid, action, "loosened")


def request_tier(body, *, peer=None, local=None, gate: Optional[Callable] = None,
                 tier_of: Optional[Callable[[str], str]] = None,
                 spawn: Optional[Callable] = None, write: Optional[Callable] = None,
                 armed: Optional[Callable[[], bool]] = None,
                 here: Optional[bool] = None) -> tuple:
    """POST /api/asks_first/tier {"action", "ask": bool}. (code, body)."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    write = write or (lambda a, t: set_tier(a, t))
    armed = armed or _owner_check_armed
    if not isinstance(body, dict) or not isinstance(body.get("ask"), bool) \
            or not isinstance(body.get("action"), str):
        return 400, {"ok": False, "error": 'need {"action": "<name>", "ask": true|false}'}
    action, ask = body["action"], body["ask"]
    if action not in LOOSE or action in HARD_LIMITS or action in MUST_ASK:
        return 403, {"ok": False, "error": NOT_ON_LIST}
    now_tier = tier_of(action)
    if now_tier == "never":
        return 409, {"ok": False, "error": "Your settings file switches this off (\"never\"), "
                                          "so the app leaves it alone."}
    if ask:
        # Stricter: at once, never a card - it only makes Jarvis ask more.
        with _L_SWITCH:
            with _L_LOCK:
                p = _L_STATE["pending"]
                if p and p.get("action") == action:
                    _L_STATE["withdrawn"].add(p["id"])
                    p.clear()
            if now_tier == "ask":
                return 200, {"ok": True, "changed": False, "view": view(here=_here(here, peer, local)),
                             "message": "It already asks you first."}
            try:
                write(action, "ask")
            except TierFileError as exc:
                return 409, {"ok": False, "error": str(exc) + "."}
            except Exception as exc:
                return 500, {"ok": False, "error": f"could not change it ({type(exc).__name__})"}
        _audit("asks_first.tier", {"action": action, "to": "ask", "how": "stricter"})
        return 200, {"ok": True, "changed": True, "view": view(here=_here(here, peer, local)),
                     "message": "Done - it asks you first from now on."}
    # Looser: the PC only, one card plus Windows Hello.
    if not _here(here, peer, local):
        return 403, {"ok": False, "error": PC_ONLY, "pc_only": True}
    if now_tier == LOOSE[action] or (now_tier == "auto" and LOOSE[action] == "notify"):
        return 200, {"ok": True, "changed": False, "view": view(here=True),
                     "message": "It already goes ahead without asking."}
    if not armed():
        return 503, {"ok": False, "error": NO_OWNER_CHECK}
    t = tier_of(LOOSEN_ACTION)
    if t != "ask":
        return 503, {"ok": False, "error": (
            f"{LOOSEN_ACTION} is tier {t!r} in jarvis-framework.toml; loosening needs a "
            f"person to say yes, so it must be 'ask'")}
    with _L_LOCK:
        if _L_STATE["pending"]:
            return 409, {"ok": False, "error": "A card to loosen something is already waiting "
                                               "- answer it first."}
        pid = uuid.uuid4().hex
        _L_STATE["pending"].update(id=pid, action=action, since=time.time())
        _L_STATE["latest"]["id"] = pid
    try:
        spawn(lambda: _decide(pid, action, gate, tier_of, write))
    except Exception:
        with _L_LOCK:
            _L_STATE["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "view": view(here=True),
                 "message": "Waiting for your approval. Approve the card on this PC - it "
                            "asks Windows Hello - and it stops asking first."}


def _here(here: Optional[bool], peer, local) -> bool:
    return bool(here) if here is not None else _from_this_pc(peer, local)


# ---------------------------------------------------------------------------
# Lights, plugs and fans without a card
# ---------------------------------------------------------------------------

LIGHTS_ACTION = "change_own_config"
LIGHTS_ROW = "Switch lights, plugs and fans you name"
LIGHTS_LABEL = "Lights, plugs and fans without a card"
LIGHTS_DETAIL = ("When you name a light, plug or fan yourself - \"turn off the kitchen light\" "
                 "- Jarvis switches it without an approval card. Locks, doors, alarms, covers "
                 "and garage doors always ask, each with a card of its own, and so does "
                 "everything after Jarvis has read outside text in the chat. Turning this on "
                 "shows you an approval card first; turning it off happens at once.")
LIGHTS_NOTE = "Off by default. The switch is below."
LIGHTS_WAITING = "Waiting for your yes on the approval card, on your PC or phone."

LIGHTS_CARD = "\n".join([
    "Let Jarvis switch lights, plugs and fans without a card?",
    "",
    "When you name a light, plug or fan yourself - \"turn off the kitchen light\" - Jarvis "
    "will switch it on or off without an approval card. Only lights, plugs (Home Assistant "
    "switches) and fans; only on, off or toggle; and only the ones your own words named in "
    "that message.",
    "",
    "Locks, doors, alarms, covers, garage doors, valves, cameras, scenes and scripts always "
    "get a card of their own. So does every change after Jarvis has read outside text (an "
    "email, a web page, a file) in the chat, and anything you pasted or shared.",
    "",
    "Nothing leaves this PC except the switch itself, sent to your own Home Assistant. You "
    "can turn this off at any time from either app, and that is instant.",
    "",
    "If you did not just do this, say no.",
    "",
    "If you say no: nothing changes - every change in your home still asks.",
])

LIGHTS_LAST_WORDS = {
    "enabled": "You approved the card, so Jarvis switches the lights, plugs and fans you "
               "name without a card.",
    "denied": "The card was turned down, so every change in your home still asks.",
    "timed_out": "Nobody answered the card in time, so every change in your home still asks.",
    "refused": "Your PC's settings do not let this be approved, so every change in your home "
               "still asks.",
    "withdrawn": "You turned it off while the card waited, so approving it changed nothing.",
    "failed": "It was approved, but the setting could not be saved, so every change in your "
              "home still asks.",
}
_LIGHTS_DAMAGED = ("the settings file for this page is damaged, so every change in your "
                   "home asks. Turn \"Lights, plugs and fans without a card\" on again to "
                   "rewrite it")


def settings_path() -> Path:
    """asks_first.json in the Jarvis settings folder."""
    return _config_dir() / "asks_first.json"


_S_LOCK = threading.Lock()


def lights_setting() -> dict:
    """{"on": bool, "why": str}. No file: off (the default). Unreadable,
    not JSON, or not true/false: off, and `why` says so."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"on": False, "why": ""}
    except OSError as exc:
        return {"on": False, "why": f"the settings file for this page could not be read "
                                    f"({type(exc).__name__}), so every change in your home "
                                    f"asks"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"on": False, "why": _LIGHTS_DAMAGED}
    on = doc.get("lights", False)
    if not isinstance(on, bool):
        return {"on": False, "why": _LIGHTS_DAMAGED}
    return {"on": on, "why": ""}


def set_lights(on: bool) -> dict:
    """Write the setting. Only request_lights() calls this with True, and
    only on an approved card."""
    with _S_LOCK:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"lights": bool(on), "changed": time.time()}),
                       encoding="utf-8")
        os.replace(tmp, p)
    return dict(lights_setting(), ok=True)


_LS_LOCK = threading.Lock()
_LS_STATE: dict = {"pending": {}, "withdrawn": set(), "last": {}, "latest": {}}
_LS_SWITCH = threading.Lock()


def lights_on() -> bool:
    """What jarvis_agent.py asks: is the setting on? Fails to off."""
    try:
        return lights_setting()["on"] is True
    except Exception:
        return False


def lights_status() -> dict:
    """{"on", "waiting", "last", "why", "label", "detail"} - the switch as
    the apps show it."""
    st = lights_setting()
    with _LS_LOCK:
        waiting = bool(_LS_STATE["pending"])
        last = dict(_LS_STATE["last"]) or None
    return {"on": st["on"], "waiting": waiting, "last": last, "why": st["why"],
            "label": LIGHTS_LABEL, "detail": LIGHTS_DETAIL}


def _lights_finish(pid: str, outcome: str, why: str = "") -> None:
    with _LS_LOCK:
        if _LS_STATE["pending"].get("id") == pid:
            _LS_STATE["pending"].clear()
        _LS_STATE["withdrawn"].discard(pid)
        if _LS_STATE["latest"].get("id") not in (None, pid):
            return
        _LS_STATE["last"].clear()
        _LS_STATE["last"].update(outcome=outcome, why=why, at=time.time(),
                                 message=LIGHTS_LAST_WORDS.get(outcome, ""))
    _audit("asks_first.lights.card", {"outcome": outcome})


def _lights_decide(pid: str, apply: Callable[[bool], dict], gate: Callable,
                   tier_of: Callable[[str], str]) -> None:
    detail = {"text": LIGHTS_CARD, "what": "switch the lights, plugs and fans you name "
                                          "without a card", "setting": "lights without a card",
              "to": True, "leaves_this_pc": False}
    try:
        v = gate(LIGHTS_ACTION, detail, LIGHTS_CARD)
    except Exception as exc:
        return _lights_finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})")
    vtier = getattr(v, "tier", "unknown")
    outcome = getattr(v, "outcome", None)
    if vtier != "ask" or tier_of(LIGHTS_ACTION) != "ask":
        return _lights_finish(pid, "refused", f"the gate answered at tier {vtier!r}, which is "
                                              f"not a person saying yes")
    if not _person_said_yes(v):
        if outcome in ("denied", "timed_out"):
            return _lights_finish(pid, outcome)
        return _lights_finish(pid, "refused", str(getattr(v, "reason", "refused"))[:200])
    with _LS_SWITCH:
        with _LS_LOCK:
            withdrawn = pid in _LS_STATE["withdrawn"]
        if withdrawn:
            return _lights_finish(pid, "withdrawn")
        try:
            out = apply(True) or {}
        except Exception as exc:
            return _lights_finish(pid, "failed", type(exc).__name__)
        if out.get("ok") is False or out.get("on") is not True:
            return _lights_finish(pid, "failed", str(out.get("why") or ""))
        _lights_finish(pid, "enabled")


def request_lights(enabled, *, gate: Optional[Callable] = None,
                   tier_of: Optional[Callable[[str], str]] = None,
                   spawn: Optional[Callable] = None,
                   apply: Optional[Callable[[bool], dict]] = None) -> tuple:
    """POST /api/asks_first/lights {"enabled": bool}. (code, body). OFF at
    once; ON through ONE approval card."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    apply = apply or set_lights
    s = _LS_STATE
    if not isinstance(enabled, bool):
        return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
    if not enabled:
        with _LS_SWITCH:
            with _LS_LOCK:
                if s["pending"]:
                    s["withdrawn"].add(s["pending"]["id"])
                    s["pending"].clear()
            try:
                apply(False)
            except Exception as exc:
                return 500, {"ok": False,
                             "error": f"could not save the setting ({type(exc).__name__})"}
        _audit("asks_first.lights.off", {})
        return 200, dict(ok=True, lights=lights_status(), waiting=False,
                         message="Done - every change in your home asks you first again.")
    with _LS_LOCK:
        waiting = bool(s["pending"])
    if lights_setting()["on"] and not waiting:
        return 200, dict(ok=True, lights=lights_status(), waiting=False,
                         message="It is already on.")
    tier = tier_of(LIGHTS_ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{LIGHTS_ACTION} is tier {tier!r} in jarvis-framework.toml; this setting needs a "
            f"person to say yes, so it must be 'ask'")}
    with _LS_LOCK:
        pid = None if s["pending"] else uuid.uuid4().hex
        if pid is not None:
            s["pending"].update(id=pid, since=time.time())
            s["latest"]["id"] = pid
    if pid is None:
        return 202, dict(ok=True, lights=lights_status(), waiting=True,
                         message="A card to turn this on is already waiting for your "
                                 "approval.")
    try:
        spawn(lambda: _lights_decide(pid, apply, gate, tier_of))
    except Exception:
        with _LS_LOCK:
            s["pending"].clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, dict(ok=True, lights=lights_status(), waiting=True,
                     message="Waiting for your approval. Nothing changes unless you approve "
                             "the card, on your PC or phone.")


#: The device words an entity's own name may hold without the owner saying
#: them ("light.kitchen_light" is named by "the kitchen light").
_DEVICE_WORDS = frozenset({"light", "lights", "lamp", "lamps", "bulb", "bulbs", "switch",
                           "switches", "plug", "plugs", "socket", "sockets", "fan", "fans",
                           "strip", "led", "leds", "the"})


def named_in(entity_id: str, words: str) -> bool:
    """Did the owner's own words name this device? Every word of its id,
    after the domain and the device words, must be there as a whole word
    ("light.kitchen_ceiling" needs "kitchen" and "ceiling"). An id with no
    such word ("light.light_2" needs "2") is named only by those."""
    _, _, obj = str(entity_id or "").lower().partition(".")
    need = [w for w in obj.split("_") if w and w not in _DEVICE_WORDS]
    if not need:
        return False
    have = set(re.findall(r"[a-z0-9]+", str(words or "").lower()))
    plural = {h[:-1] for h in have if h.endswith("s")} | {h + "s" for h in have}
    return all(w in have or w in plural for w in need)


def lights_without_card(plan, owner_words: str, *, shaped: str) -> str:
    """"" when this home_control call may run WITHOUT a card, else why not
    (for the audit log - the call then goes to the gate as before).

    Every condition must hold:
      * the setting is on (off by default; a damaged file is off);
      * `shaped` is "": nothing from outside shaped this turn (a reading
        tool ran, the conversation is tainted, the newest message was
        pasted, shared or not the owner's own, or the app sent text of its
        own - jarvis_agent._TurnWatch.note_needs_a_person(), the note
        writes' test);
      * the plan is lights, switches and fans only, on, off or toggle, none
        of them a lock, door, alarm, cover, gate or anything that stands
        alone (jarvis_home.everyday_problem);
      * every device was named in the owner's newest message (named_in)."""
    if not lights_on():
        return "the setting is off"
    if shaped:
        return "outside text shaped this turn"
    try:
        import jarvis_home as HOME
        problem = HOME.everyday_problem(plan)
    except Exception as exc:
        return f"the plan could not be checked ({type(exc).__name__})"
    if problem:
        return problem
    ids = [getattr(q, "entity_id", "") for q in getattr(plan, "queries", []) or []]
    if not ids or not all(named_in(e, owner_words) for e in ids):
        return "a device was not named in your own words"
    return ""


def record_no_card(plan) -> None:
    """The audit line for a home change made without a card: the devices
    and the service, never anything else."""
    _audit("asks_first.lights.no_card", {
        "entities": [getattr(q, "entity_id", "") for q in getattr(plan, "queries", []) or []],
        "service": (getattr((getattr(plan, "queries", None) or [None])[0], "url", "") or "")
        .rsplit("/api/services/", 1)[-1]})


# ---------------------------------------------------------------------------
# Routes (asks-first.patch hands the request here)
# ---------------------------------------------------------------------------


def handle_get(peer=None, local=None) -> tuple:
    """GET /api/asks_first."""
    return 200, view(here=_from_this_pc(peer, local))


def handle_tier(body, peer=None, local=None) -> tuple:
    """POST /api/asks_first/tier."""
    return request_tier(body, peer=peer, local=local)


def handle_lights(body) -> tuple:
    """POST /api/asks_first/lights."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": 'need {"enabled": true|false}'}
    return request_lights(body.get("enabled"))


def _reset_for_tests() -> None:
    for st, lock in ((_L_STATE, _L_LOCK), (_LS_STATE, _LS_LOCK)):
        with lock:
            for v in st.values():
                v.clear()
