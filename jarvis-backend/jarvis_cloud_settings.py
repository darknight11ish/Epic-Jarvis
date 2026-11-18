"""jarvis_cloud_settings.py - the hybrid/cloud settings, from chat, on the PC.

NEW MODULE, shipped whole (no patch of its own): `jarvis_quick.py` calls it
from the fast path, so a question about the cloud is answered in a second,
with no model, and a change goes through the doors that already exist.

TWO JOBS, AND THEY ARE DELIBERATELY DIFFERENT.

1. ANSWER, from THIS PC's own files. Nothing here asks a model and nothing
   guesses. The three files read are the ones the settings themselves use:

     <settings>/cloud-choice.json      which cloud service is chosen
                                       (jarvis_presets.CLOUD_CHOICE_FILE)
     <settings>/escalate-cloud.json    the standing "send hard questions
                                       without asking first" switch
     <settings>/chatbot/api-money.json the monthly money caps and the
                                       ledger of what has been spent

   Every answer names the file it read and when that file was last saved, so
   the owner can check the sentence instead of trusting it. A missing file is
   said in plain words - "not set up" - together with what that means (no
   cloud service is chosen, so there is no cloud path at all), never as an
   empty or confident answer.

2. CHANGE, only through the doors that already exist. This module adds no
   route, no file writer and no second mechanism:

     the service     jarvis_presets.apply_cloud  - the ONE `change_own_config`
                     card the Presets menu's Cloud row raises; the choice is
                     written only after that yes.
     the switch      jarvis_presets.cloud_escalate - ON raises the same ONE
                     card, OFF is instant (the existing rule), and ON with no
                     service chosen is refused BEFORE a card.
     the money cap   jarvis_chatbot_limits.change - the SAME door behind
                     `POST /api/chatbot/money`: raising the cap raises ONE
                     `raise_api_limit` card (tier "ask", Windows Hello on this
                     PC or the asking phone's own fingerprint), while lowering,
                     removing and correcting a price are instant because they
                     only ever spend less. Nothing is written before the yes.

   A provider name this PC does not know is refused with the list read from
   `jarvis_chatbot_api.PRESETS` - the code that owns the six - never accepted
   and never guessed at.

WHAT IS NEVER HERE. No API key is read, shown, logged or put in a sentence:
`jarvis_chatbot_api.key_saved` and Windows Credential Manager are not called
at all. Nothing private is read: only the three setting files above, numbers
and names. No network, no card is ever approved here, no write happens before
an approval, and the module never raises into the chat turn.

Standard library only. No I/O at import.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

#: The names this module answers in chat, so the caller has ONE place to wire
#: both jobs without knowing a shape. `jarvis_quick` builds a Result from the
#: answer, and dispatches a change to the runners below.
ANSWER = "cloud_settings"
CHANGE = "cloud_settings_change"

#: The settings files, spelled with their owners' own names when those modules
#: are here (they are in every install) and with the same literals otherwise.
CLOUD_CHOICE_FILE = "cloud-choice.json"
CLOUD_ESCALATE_FILE = "escalate-cloud.json"
MONEY_FILE = "api-money.json"

#: The file words used in an answer: a bare file name, not a full path (a path
#: holds the Windows user name, and a chat answer does not need it).
CHOICE_WORDS = "cloud-choice.json"
SWITCH_WORDS = "escalate-cloud.json"
MONEY_WORDS = "chatbot\\api-money.json"

#: Where the owner runs the command-line answer instead, for the one thing
#: chat cannot do on a PC whose module is missing.
MONEY_PAGE = "the Chatbot money limits page on the PC"

#: The aliases a person types for a service. The ids AND the short names come
#: from `jarvis_chatbot_api.PRESETS` itself; these are the extra words a person
#: says (the same words `jarvis_quick._CLOUD_PROVIDER_WORDS` uses, kept as
#: plain names here so this module has no import at module level).
_PROVIDER_ALIASES = (
    ("openai", "openai_api"), ("open ai", "openai_api"),
    ("chatgpt", "openai_api"), ("chat gpt", "openai_api"),
    ("deepseek", "deepseek_api"), ("deep seek", "deepseek_api"),
    ("mistral", "mistral_api"),
    ("openrouter", "openrouter_api"), ("open router", "openrouter_api"),
    ("groq", "groq_api"),
    ("xai", "xai_api"), ("x ai", "xai_api"), ("grok", "xai_api"),
)


# ---------------------------------------------------------------------------
#   The files, read once per call
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Jarvis's settings folder - through its one owner, jarvis_presets."""
    try:
        import jarvis_presets as P
        return Path(P._config_dir())
    except Exception:                                       # noqa: BLE001
        env = os.environ.get("OPENJARVIS_CONFIG_DIR")
        return Path(os.path.expanduser(env)) if env else (
            Path(os.path.expanduser("~")) / ".openjarvis")


def _choice_path() -> Path:
    try:
        import jarvis_presets as P
        name = getattr(P, "CLOUD_CHOICE_FILE", CLOUD_CHOICE_FILE)
        return Path(P._config_dir()) / str(name)
    except Exception:                                       # noqa: BLE001
        return _config_dir() / CLOUD_CHOICE_FILE


def _switch_path() -> Path:
    try:
        import jarvis_presets as P
        name = getattr(P, "CLOUD_ESCALATE_FILE", CLOUD_ESCALATE_FILE)
        return Path(P._config_dir()) / str(name)
    except Exception:                                       # noqa: BLE001
        return _config_dir() / CLOUD_ESCALATE_FILE


def _read_json(path: Path) -> tuple:
    """(the document, "") or (None, why it cannot be read, in plain words).

    A missing file is NOT an error here: the caller says "not there" in its
    own words. An unreadable or malformed file is, because it must never read
    as "the switch is off" without saying why.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, f"it could not be opened ({type(exc).__name__})"
    try:
        got = json.loads(raw)
    except ValueError:
        return None, "it is not readable JSON"
    if not isinstance(got, dict):
        return None, "it is not the expected shape"
    return got, ""


def _saved_words(path: Path) -> str:
    """'saved 31 Oct 2026' for an answer's own evidence, or '' if unknown."""
    try:
        lt = time.localtime(path.stat().st_mtime)
    except Exception:                                       # noqa: BLE001
        return ""
    return f"saved {lt.tm_mday} {time.strftime('%b', lt)} {lt.tm_year}"


def _source(path: Path, words: str) -> str:
    """'(cloud-choice.json, saved 31 Oct 2026)': the file, read by this answer."""
    saved = _saved_words(path)
    return f"({words},{' ' + saved if saved else ' no saved time readable'})"


# ---------------------------------------------------------------------------
#   The code that owns the six services
# ---------------------------------------------------------------------------

def _api():
    """jarvis_chatbot_api, or None. It owns PRESETS, the money file's rules
    and the service names; importing it lazily keeps a backend without it from
    failing to import this module."""
    try:
        import jarvis_chatbot_api as API
    except Exception:                                       # noqa: BLE001
        return None
    return API


def known_ids() -> tuple:
    """The service ids THIS PC knows, in the code's own order, or ()."""
    API = _api()
    if API is None:
        return ()
    try:
        return tuple(API.PRESETS)
    except Exception:                                       # noqa: BLE001
        return ()


def _known_names() -> str:
    """'OpenAI (openai), DeepSeek (deepseek), ...' - the six, read from code."""
    API = _api()
    if API is None:
        return "none - the cloud services are not set up on this PC"
    try:
        return ", ".join(f"{p.company} ({p.short})" for p in API.PRESETS.values())
    except Exception:                                       # noqa: BLE001
        return "none - the cloud services are not set up on this PC"


def provider_for_words(words: str) -> str:
    """The service id a person's words name, or "". Never guesses."""
    text = " ".join(str(words or "").lower().split())
    if not text:
        return ""
    API = _api()
    ids = known_ids()
    for pid in ids:
        try:
            p = API.PRESETS[pid]
            for form in (pid, p.short, p.company, p.name):
                if " ".join(str(form or "").lower().split()) == text:
                    return pid
        except Exception:                                   # noqa: BLE001
            continue
    for word, pid in _PROVIDER_ALIASES:
        if word == text and pid in ids:
            return pid
    return ""


def _who(pid: str) -> str:
    """'DeepSeek (API) - model deepseek-flash at api.deepseek.com', or the id."""
    API = _api()
    if API is None:
        return pid
    try:
        p = API.PRESETS[pid]
        model = p.model
        try:
            model = str(API.model_for(pid)[0] or p.model)
        except Exception:                                   # noqa: BLE001
            pass
        return f"{p.company} ({p.name}) - model {model} at {p.host}"
    except Exception:                                       # noqa: BLE001
        return pid


def _company(pid: str) -> str:
    API = _api()
    try:
        return API.PRESETS[pid].company
    except Exception:                                       # noqa: BLE001
        return pid


# ---------------------------------------------------------------------------
#   What is on disk
# ---------------------------------------------------------------------------

def provider_state() -> dict:
    """Which cloud service is chosen, from cloud-choice.json, and the file's
    own evidence. Never includes a key."""
    path = _choice_path()
    out = {"path": path, "exists": path.is_file(), "provider": "",
           "raw": "", "error": "", "saved": _saved_words(path)}
    doc, why = _read_json(path)
    if doc is None:
        out["error"] = why
        return out
    raw = str(doc.get("provider") or "").strip()
    out["raw"] = raw
    if not raw:
        out["error"] = "it names no cloud service"
    elif not known_ids():
        out["error"] = "the cloud services are not set up on this PC"
    elif raw not in known_ids():
        out["error"] = (f"it names {raw!r}, a cloud service this PC does not know")
    else:
        out["provider"] = raw
    return out


def escalation_state() -> dict:
    """The standing switch, from escalate-cloud.json. ON only when the file
    says `"on": true`; absent, unreadable or corrupt all read as OFF, the same
    fail-closed rule `jarvis_presets.escalate_on` keeps."""
    path = _switch_path()
    doc, why = _read_json(path)
    return {"path": path, "exists": path.is_file(),
            "on": isinstance(doc, dict) and doc.get("on") is True,
            "error": why, "saved": _saved_words(path)}


def _money_api():
    return _api()


def money_state() -> dict:
    """The caps and this month's ledger, from chatbot/api-money.json.

    Never raises. `error` is set when the file is there but cannot be read
    (the money module's own `_file_words` sentence says so in plain words);
    a missing file is `exists: False`, which means no cap and no spending."""
    API = _money_api()
    out = {"available": API is not None, "path": None, "exists": False,
           "error": "", "month": "", "month_name": "", "limits": {},
           "month_rows": {}, "month_total": 0.0, "month_requests": 0,
           "other_months": [], "saved": ""}
    if API is None:
        out["error"] = "the money record module is not here"
        return out
    try:
        path = Path(API.money_path())
    except Exception as exc:                                # noqa: BLE001
        out["error"] = f"the money record's place could not be worked out ({type(exc).__name__})"
        return out
    out["path"] = path
    out["exists"] = path.is_file()
    out["saved"] = _saved_words(path)
    if not out["exists"]:
        return out
    try:
        data = API._load()
    except API.MoneyFileError as exc:
        out["error"] = str(API._file_words(str(exc)))
        return out
    except Exception as exc:                                # noqa: BLE001
        out["error"] = f"the money record could not be read ({type(exc).__name__})"
        return out
    try:
        month = str(API.month_key())
        out["month"] = month
        try:
            month_no = int(month.split("-")[1])
            out["month_name"] = API.MONTHS[month_no - 1]
        except Exception:                                   # noqa: BLE001
            out["month_name"] = month
        limits = {}
        for pid in API.PRESETS:
            try:
                amount = API.limit_of(pid, data)
            except Exception:                               # noqa: BLE001
                amount = None
            if amount is not None:
                limits[pid] = float(amount)
        out["limits"] = limits
        rows = data.get("months") or {}
        this_month = rows.get(month) or {}
        money_rows, total, requests = {}, 0.0, 0
        for pid, row in (this_month.items() if isinstance(this_month, dict) else ()):
            if not isinstance(row, dict):
                continue
            dollars = API._num(row.get("dollars")) or 0.0
            count = API._num(row.get("requests")) or 0
            money_rows[pid] = {"dollars": float(dollars), "requests": int(count)}
            total += float(dollars)
            requests += int(count)
        out["month_rows"] = money_rows
        out["month_total"] = total
        out["month_requests"] = requests
        other = []
        for key in sorted(rows):
            if key == month or not isinstance(rows.get(key), dict):
                continue
            d = r = 0
            for pid, row in rows[key].items():
                if not isinstance(row, dict):
                    continue
                d += API._num(row.get("dollars")) or 0.0
                r += API._num(row.get("requests")) or 0
            other.append({"month": key, "dollars": float(d), "requests": int(r)})
        out["other_months"] = other
    except Exception as exc:                                # noqa: BLE001
        out["error"] = f"the money record could not be read ({type(exc).__name__})"
    return out


def _money_words(API, amount) -> str:
    """'$10.00' through the money module's own formatting, so one module owns
    how a dollar amount is written."""
    try:
        return API.dollars(amount)
    except Exception:                                       # noqa: BLE001
        return f"${float(amount or 0):,:.2f}"


def _cap_service(money: dict, provider: str = "") -> str:
    """Which service "my cap" means: the chosen one when it has a cap, else
    the only service that has one. "" when that is not a single answer."""
    limits = money.get("limits") or {}
    if provider and provider in limits:
        return provider
    if len(limits) == 1:
        return next(iter(limits))
    return ""


def _default_cap_service() -> str:
    """The service a plain "set my cap to $5" means, or "" (then ask which)."""
    return _cap_service(money_state(), provider_state().get("provider") or "")


def _send_rule(esc: dict) -> str:
    """One honest clause for whether Jarvis may send by itself, from the file
    read. It never says "nothing is sent by itself" while the switch is ON."""
    if esc.get("on"):
        return ("a hard question can go to the cloud without asking you first (the "
                "standing switch is ON), after every privacy check and the monthly cap")
    if esc.get("error"):
        return ("nothing is sent by itself: the switch file cannot be read, so it counts "
                "as off and every cloud turn waits for your yes")
    if not esc.get("exists"):
        return ("nothing is sent by itself: no switch has been saved, so every cloud "
                "turn waits for your yes")
    return "nothing is sent by itself: the switch is off, so every cloud turn waits for your yes"


# ---------------------------------------------------------------------------
#   1. The answers - one fixed sentence per shape, read fresh every time
# ---------------------------------------------------------------------------

#: What escalation never sends. The project's first rule, in the owner's words,
#: and the same list jarvis_router.choose()'s gates enforce.
_NEVER_SENT = ("Email, files, notes, credentials, stored memory, a picture, your "
               "screen, a private question, a pasted secret and a conversation that "
               "has already read text from outside this PC never go to the cloud.")


def _provider_words() -> str:
    st = provider_state()
    if not st["exists"]:
        return ("The cloud service is not set up on this PC yet: cloud-choice.json is not "
                "there. That means there is no cloud path at all - every answer is "
                "written by the model on this PC. To set one up, say \"switch to "
                "DeepSeek as my cloud provider\" (one approval card asks first), or "
                "pick one in the Presets menu.")
    pid = st["provider"]
    if not pid:
        why = st["error"] or "it cannot be read"
        return (f"The cloud provider file cloud-choice.json is there but {why}, so no "
                f"cloud service is set up on this PC: every answer is written here and "
                f"there is no cloud path at all. Pick one in the Presets menu, or say "
                f"\"switch to DeepSeek as my cloud provider\".")
    return (f"Your cloud service is {_who(pid)}. I read that from cloud-choice.json "
            f"({st['saved'] or 'no saved time readable'}). That is only a choice: "
            f"{_send_rule(escalation_state())}.")


def _on_cloud_words() -> str:
    st = provider_state()
    esc = escalation_state()
    if not st["provider"]:
        return ("No - this answer is written on this PC, and the cloud service is not "
                "set up: cloud-choice.json " + ("is not there" if not st["exists"]
                                               else "does not hold a usable choice") +
                ", so every answer is written by the model here.")
    return (f"This answer is written on this PC, not by a cloud service. "
            f"{_who(st['provider'])} is chosen for hard questions (cloud-choice.json, "
            f"{st['saved'] or 'no saved time readable'}), but that choice sends nothing "
            f"by itself: {_send_rule(esc)}.")


def _escalation_words() -> str:
    esc = escalation_state()
    st = provider_state()
    saved = esc.get("saved") or "no saved time readable"
    if esc.get("on"):
        who = (_company(st["provider"]) if st["provider"] else "the cloud service you chose")
        tail = (f" It can go to {who}: a hard question may be sent without asking you "
                f"first, so I may spend money and send that message's own words by "
                f"myself." if st["provider"] else
                " No cloud service is chosen, so there is nothing for it to send to "
                "until one is picked in the Presets menu.")
        return (f"Escalation is ON: escalate-cloud.json ({saved}) says on.{tail} "
                f"{_NEVER_SENT} Every privacy check and the monthly cap still run "
                f"first. Say \"turn escalation off\" to stop it.")
    if not esc["exists"]:
        state = "escalate-cloud.json is not there, so no switch has been saved"
    elif esc.get("error"):
        state = (f"escalate-cloud.json is there but {esc['error']}, so it counts as off")
    else:
        state = f"escalate-cloud.json says off ({saved})"
    return (f"No - escalation is off: {state}, so every cloud turn waits for your yes "
            f"and I never send anything to the cloud by myself. (Even with the switch "
            f"on, {_NEVER_SENT[0].lower() + _NEVER_SENT[1:]})")


def _cap_words() -> str:
    API = _money_api()
    money = money_state()
    if API is None:
        return ("I cannot read the money record on this PC (the cloud money module is "
                "not here), so I cannot say what your cap is.")
    if money.get("error"):
        return ("I cannot say what your cap is: " + str(money["error"]).rstrip(".") + ".")
    if not money["exists"]:
        return ("No cap is set up on this PC yet: chatbot\\api-money.json is not there, "
                "so no paid cloud service can be used at all. Say \"set my cap to $5\" "
                "to set one (one approval card asks first).")
    chosen = provider_state().get("provider") or ""
    pid = _cap_service(money, chosen)
    limits = money["limits"]
    if pid:
        p = API.PRESETS[pid]
        return (f"Your cap for {p.company} is {_money_words(API, limits[pid])} a month. "
                f"Read from chatbot\\api-money.json "
                f"({money['saved'] or 'no saved time readable'}).")
    if not limits:
        return ("No monthly cap is set for any cloud service in chatbot\\api-money.json, "
                "and a missing cap means that service is not used at all - it does not "
                "mean unlimited. Say \"set my cap to $5\" (one approval card asks first).")
    parts = "; ".join(f"{API.PRESETS[pid].company} {_money_words(API, amount)} a month"
                      for pid, amount in limits.items())
    return ("No single cloud service is chosen to be your cap, and these caps are set in "
            f"chatbot\\api-money.json: {parts}. Say which one to change, for example "
            "\"set my DeepSeek cap to $5\".")


def _spend_words() -> str:
    API = _money_api()
    money = money_state()
    if API is None:
        return ("I cannot read the money record on this PC (the cloud money module is "
                "not here), so I cannot say what has been spent.")
    if money.get("error"):
        return ("I cannot say what has been spent: " + str(money["error"]).rstrip(".") + ".")
    if not money["exists"]:
        return ("Nothing is recorded yet: chatbot\\api-money.json is not there, so no "
                "monthly cap is set and no cloud spend has been written down.")
    month = money.get("month_name") or money.get("month") or "this month"
    total = _money_words(API, money["month_total"])
    count = money["month_requests"]
    head = (f"This month ({month}): about {total} is recorded, from {count} "
            f"answer{'s' if count != 1 else ''}.")
    other = money.get("other_months") or []
    if other:
        bits = []
        for row in other:
            nm = row["month"]
            try:
                nm = API.MONTHS[int(str(row["month"]).split("-")[1]) - 1]
            except Exception:                               # noqa: BLE001
                pass
            n = row["requests"]
            bits.append(f"{nm} - {n} answer{'s' if n != 1 else ''}, about "
                        f"{_money_words(API, row['dollars'])}")
        head += " The ledger also holds " + "; ".join(bits) + "."
    else:
        head += " The ledger holds no earlier month."
    chosen = provider_state().get("provider") or ""
    pid = _cap_service(money, chosen)
    if pid:
        p = API.PRESETS[pid]
        spent = (money["month_rows"].get(pid) or {}).get("dollars", 0.0)
        head += (f" For {p.company} this month: about {_money_words(API, spent)} of its "
                 f"{_money_words(API, money['limits'][pid])} cap.")
    head += (f" Read from chatbot\\api-money.json "
             f"({money['saved'] or 'no saved time readable'}).")
    return head


def _what_it_does_words() -> str:
    esc = escalation_state()
    st = provider_state()
    saved = esc.get("saved") or "no saved time readable"
    if not esc["exists"]:
        source = "escalate-cloud.json is not there"
    elif esc.get("error"):
        source = f"escalate-cloud.json cannot be read ({esc['error']})"
    else:
        source = f"escalate-cloud.json, {saved}"
    state = ("It is ON right now." if esc.get("on") else
             "It is OFF right now." if not esc.get("error") else
             "It cannot be read right now, so it counts as OFF.")
    who = (_company(st["provider"]) if st["provider"] else "a cloud service once one is chosen")
    return (f"The standing switch ({source}) is how you let a hard question go "
            f"to {who} without a card for each one: I may then spend money and send "
            f"that message's own words by myself. {_NEVER_SENT} Lockdown, every privacy "
            "check and the monthly cap still run first, and turning it off makes every "
            f"cloud turn wait for your yes again. {state}")


def answer(shape: str) -> str:
    """The one fixed answer for a shape `prompt()` returned. Never a model."""
    shape = str(shape or "")
    if shape == "provider":
        return _provider_words()
    if shape == "on_cloud":
        return _on_cloud_words()
    if shape == "escalation":
        return _escalation_words()
    if shape == "cap":
        return _cap_words()
    if shape == "spend":
        return _spend_words()
    if shape == "what_it_does":
        return _what_it_does_words()
    return ""


# ---------------------------------------------------------------------------
#   2. The changes - through the doors that already exist, nothing before a yes
# ---------------------------------------------------------------------------

def set_provider(pid: str) -> tuple:
    """Make ONE service the chosen cloud provider - through its own door.

    `jarvis_presets.apply_cloud` refuses a name this PC does not know (and says
    the six), refuses a service this PC cannot use yet BEFORE any card, and
    raises the ONE `change_own_config` card; cloud-choice.json is written only
    after that yes. This module copies none of those rules and approves nothing.
    """
    name = str(pid or "").strip()
    ids = known_ids()
    if not ids:
        return 503, {"ok": False, "changed": False,
                     "error": ("the cloud services are not set up on this PC, so no "
                               "cloud provider can be chosen")}
    if name not in ids:
        return 400, {"ok": False, "changed": False,
                     "error": (f"there is no cloud service called {name!r} on this PC; "
                               f"the services are {_known_names()}")}
    try:
        import jarvis_presets as P
    except Exception:                                       # noqa: BLE001
        return 503, {"ok": False, "changed": False,
                     "error": "the cloud settings are not set up on this PC"}
    try:
        return P.apply_cloud(provider=name)
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "changed": False,
                     "error": f"the cloud provider could not be changed ({type(exc).__name__})"}


def set_escalation(on: bool) -> tuple:
    """Turn the standing switch on (ONE card) or off (instant) - its own door."""
    try:
        import jarvis_presets as P
    except Exception:                                       # noqa: BLE001
        return 503, {"ok": False, "changed": False, "card": False,
                     "error": "the cloud settings are not set up on this PC"}
    try:
        return P.cloud_escalate(on=bool(on))
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "changed": False,
                     "error": f"the cloud switch could not be changed ({type(exc).__name__})"}


def set_cap(dollars, *, provider: str = "", peer=None, local=None) -> tuple:
    """Set ONE service's monthly money cap - through the route's own door.

    `jarvis_chatbot_limits.change` is the exact function behind
    `POST /api/chatbot/money`. It decides the DIRECTION from the amount against
    the cap it already holds: an amount above today's cap raises ONE
    `raise_api_limit` card (tier "ask") and writes nothing before that yes; an
    amount at or below it only spends less, so it applies at once with no card.
    No card is ever approved here and no file is written by this module.

    With no service named, the chosen provider is used; when that is not a
    single answer the turn ASKS which service, and nothing is raised.
    """
    API = _money_api()
    if API is None:
        return 503, {"ok": False, "changed": False,
                     "error": "the money record is not set up on this PC"}
    amount = _dollars_value(dollars)
    if amount is None:
        return 400, {"ok": False, "changed": False,
                     "error": "say the monthly cap as a number of dollars, for example $5"}
    pid = str(provider or "").strip()
    if not pid:
        pid = _default_cap_service()
    if not pid:
        return 409, {"ok": False, "changed": False,
                     "error": ("say which cloud service's cap to change: "
                               f"{_known_names()}")}
    if pid not in API.PRESETS:
        return 400, {"ok": False, "changed": False,
                     "error": (f"there is no cloud service called {pid!r} on this PC; "
                               f"the services are {_known_names()}")}
    try:
        import jarvis_chatbot_limits as L
    except Exception:                                       # noqa: BLE001
        return 503, {"ok": False, "changed": False,
                     "error": (f"changing the monthly cap from chat is not set up on this "
                               f"PC; it is done in {MONEY_PAGE}")}
    body = {"action": "raise_limit",
            "service": str(API.PRESETS[pid].short),
            "dollars": float(amount)}
    try:
        return L.change(body, peer=peer, local=local)
    except Exception as exc:                                # noqa: BLE001
        return 503, {"ok": False, "changed": False,
                     "error": f"the monthly cap could not be changed ({type(exc).__name__})"}


def _dollars_value(value) -> Optional[float]:
    """A dollars amount from a number or from the words a person typed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        got = float(value)
        return got if got == got and got >= 0 and got != float("inf") else None
    text = str(value or "")
    found = re.search(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text)
    if not found:
        return None
    try:
        return float(found.group(1).replace(",", ""))
    except ValueError:
        return None


def change_words(kind: str, status, body, *, provider: str = "") -> str:
    """The one chat sentence for a change, built ONLY from the door's own body.

    It never says "done" unless the body says a change really happened; a card
    that was not approved is reported as not changed, and a card that is still
    waiting is reported as waiting. That is the same honesty rule the cloud
    provider and the standing switch runners in jarvis_quick.py already keep.
    """
    body = body if isinstance(body, dict) else {}
    if kind == "provider":
        if status in (200, 202) and body.get("changed") is True:
            name = _company(str(body.get("provider") or provider))
            said = str(body.get("message") or "").strip()
            return f"Making {name} the cloud service: done. " + said
        outcome = str(body.get("outcome") or "").strip()
        if outcome:
            return (f"The cloud service was not changed - the ONE approval card was not "
                    f"approved ({outcome}), so it stays as it was.")
        reason = (str(body.get("error") or "").strip()
                  or str(body.get("message") or "").strip()
                  or "the PC refused it")
        return f"Nothing was changed - {reason}"
    if kind == "escalation":
        error = str(body.get("error") or "").strip()
        if error:
            return error
        said = (str(body.get("said") or "").strip()
                or str(body.get("message") or "").strip())
        pending = (body.get("waiting") is True
                   or (body.get("card") is True and body.get("changed") is not True
                       and not body.get("outcome")))
        if pending:
            if not re.search(r"wait|approv|card", said, re.I):
                said = (said + " " if said else "") + (
                    "Waiting for your yes on the approval card on this PC. Nothing "
                    "has changed yet.")
            return said
        if body.get("changed") is True:
            if said:
                return said
            return ("Escalation is on now." if body.get("on") is True
                    else "Escalation is off now.")
        return said or "Nothing was changed."
    if kind == "cap":
        error = str(body.get("error") or "").strip()
        said = str(body.get("said") or "").strip()
        if status in (200, 202) and body.get("changed") is True:
            return said or "The monthly cap was changed."
        if error:
            reason = str(body.get("message") or "").strip() or error
            return (f"Nothing was changed - {reason}")
        return said or "Nothing was changed."
    return "Nothing was changed."


# ---------------------------------------------------------------------------
#   The sentences this module claims - questions first, changes second
# ---------------------------------------------------------------------------

#: A question, even after normalize_spoken_command strips its polite lead-in:
#: "will you send things to the cloud by yourself?" becomes "send things to the
#: cloud by yourself", which must never be read as the command to start doing
#: it. Checked against the RAW words, before any change parser runs.
_QUESTION_LEADS = frozenset({
    "is", "are", "was", "were", "am", "do", "does", "did", "can", "could",
    "will", "would", "should", "shall", "what", "which", "who", "how", "have",
    "has", "tell", "explain", "show", "list",
})


def _is_question(raw: str) -> bool:
    text = " ".join(str(raw or "").strip().split())
    if not text:
        return False
    if text.endswith("?"):
        return True
    first = re.sub(r"^[^a-z0-9']+", "", text.lower().split()[0])
    return first in _QUESTION_LEADS


_Q_PROVIDER = re.compile(
    r"(?:which|what)\s+(?:cloud\s+)?(?:provider|service|api)\s+"
    r"(?:am\s+i|are\s+(?:you|we))\s+(?:using|on|connected\s+to|set\s+to)\b.*"
    r"|(?:which|what)\s+(?:cloud\s+)?(?:provider|service)\s+(?:is\s+)?"
    r"(?:chosen|selected|set|in\s+use|active)\b.*"
    r"|what(?:'s|\s+is)\s+my\s+cloud\s+(?:provider|service)\b.*"
    r"|which\s+cloud\s+(?:am\s+i|are\s+we)\s+(?:on|using|connected\s+to)\b.*")

_Q_ON_CLOUD = re.compile(
    r"am\s+i\s+(?:on|using|connected\s+to)\s+(?:the\s+)?cloud\b.*"
    r"|am\s+i\s+on\s+(?:a\s+)?(?:cloud|the\s+cloud)\b.*")

_Q_ESCALATION = re.compile(
    r"(?:is|are)\s+(?:the\s+)?(?:cloud\s+)?escalation\s+"
    r"(?:on|off|enabled|disabled|turned\s+(?:on|off)|switched\s+(?:on|off))\b.*"
    r"|(?:is|are)\s+(?:the\s+)?(?:cloud\s+)?escalation\s+switch\s+(?:on|off)\b.*"
    r"|(?:will|would|do|does)\s+(?:you|jarvis)\s+(?:automatically\s+|ever\s+)?"
    r"(?:send|share|use|escalate)\s+(?:things|stuff|questions|anything|messages?|"
    r"words?)?\s*(?:to\s+)?(?:the\s+)?cloud\b.*"
    r"|(?:will|would|do|does)\s+(?:you|jarvis)\s+(?:send|escalate|share)\b.*"
    r"(?:by\s+yourself|on\s+your\s+own|without\s+asking|automatically)\b.*"
    r"|send\s+things\s+to\s+the\s+cloud\s+by\s+yourself\b.*")

_Q_WHAT_IT_DOES = re.compile(
    r"what\s+(?:does|do)\s+(?:cloud\s+)?escalation\s+(?:actually\s+)?"
    r"(?:do|mean|change|send|allow)\b.*"
    r"|what\s+happens\s+(?:when|if)\s+(?:cloud\s+)?escalation\s+"
    r"(?:is\s+on|is\s+enabled|turns?\s+on|goes?\s+on)\b.*"
    r"|what\s+(?:is|does)\s+(?:the\s+)?(?:cloud\s+)?(?:standing\s+)?"
    r"(?:escalation|cloud\s+switch)\b.*"
    r"|explain\s+(?:the\s+)?(?:cloud\s+)?escalation\b.*"
    r"|what\s+is\s+cloud\s+escalation\b.*"
    r"|what\s+can\s+(?:go|be\s+sent)\s+to\s+the\s+cloud\b.*")

_Q_CAP = re.compile(
    r"what(?:'s|\s+is)\s+my\s+(?:monthly\s+|cloud\s+|api\s+|spending\s+)?"
    r"(?:cap|limit|budget)\b.*"
    r"|what(?:'s|\s+is)\s+(?:the|my)\s+(?:monthly\s+)?(?:cloud|api|chatbot)\s+"
    r"(?:cap|limit|budget)\b.*"
    r"|how\s+much\s+(?:can|may|are)\s+(?:you|jarvis)\s+(?:spend|allowed\s+to\s+spend)\b.*"
    r"|what\s+is\s+my\s+spending\s+limit\b.*")

_Q_SPEND = re.compile(
    r"how\s+much\s+(?:have|did|do)\s+i\s+spend\s+(?:this\s+month|so\s+far)\b.*"
    r"|how\s+much\s+(?:have|did)\s+i\s+(?:spend|spent)\s*\??$"
    r"|how\s+much\s+(?:has|have)\s+(?:you|jarvis)\s+spent\s*"
    r"(?:this\s+month|so\s+far)?\s*\??$"
    r"|how\s+much\s+(?:have|did)\s+i\s+(?:spent|spend)\s+"
    r"(?:this\s+month|so\s+far)\b.*"
    r"|(?:what(?:'s|\s+is)|show\s+(?:me\s+)?)\s+(?:my\s+)?spending\s+"
    r"(?:this\s+month|so\s+far|summary|total|report)\b.*")

_Q_QUESTION_SHAPES = (
    ("what_it_does", _Q_WHAT_IT_DOES),
    ("escalation", _Q_ESCALATION),
    ("on_cloud", _Q_ON_CLOUD),
    ("provider", _Q_PROVIDER),
    ("cap", _Q_CAP),
    ("spend", _Q_SPEND),
)


def _forms(normalized: str, raw: str) -> list:
    forms = []
    for form in (normalized, " ".join(str(raw or "").strip().lower().split())):
        if form and form not in forms:
            forms.append(form)
    return forms


# --- the changes: only the sentences no earlier door claims -----------------

_ESC_ON = re.compile(
    r"(?:turn|switch)\s+on\s+(?:the\s+|my\s+)?(?:standing\s+)?escalation\b.*"
    r"|(?:turn|switch)\s+(?:the\s+|my\s+)?(?:standing\s+)?escalation\s+on\b.*"
    r"|(?:enable|activate|start)\s+(?:the\s+|my\s+)?(?:standing\s+)?escalation\b.*"
    r"|(?:turn|switch)\s+on\s+(?:the\s+|my\s+)?cloud\s+switch\b.*"
    r"|(?:enable|activate)\s+(?:the\s+|my\s+)?cloud\s+switch\b.*"
    r"|start\s+escalating\b.*")

_ESC_OFF = re.compile(
    r"(?:turn|switch)\s+off\s+(?:the\s+|my\s+)?(?:standing\s+)?escalation\b.*"
    r"|(?:turn|switch)\s+(?:the\s+|my\s+)?(?:standing\s+)?escalation\s+off\b.*"
    r"|(?:disable|deactivate|stop)\s+(?:the\s+|my\s+)?(?:standing\s+)?escalation\b.*"
    r"|(?:turn|switch)\s+off\s+(?:the\s+|my\s+)?cloud\s+switch\b.*"
    r"|(?:disable|deactivate)\s+(?:the\s+|my\s+)?cloud\s+switch\b.*"
    r"|stop\s+escalating\b(?![^.;!?]*\bto\s+the\s+cloud\b).*"
    r"|(?:stop|don'?t)\s+send(?:ing)?\s+(?:things|stuff|questions|them)?\s*"
    r"to\s+the\s+cloud\s+(?:by\s+yourself|on\s+your\s+own|without\s+asking|"
    r"automatically)\b.*")

#: "set my cap to $5", "set the monthly limit to 5 dollars", "lower my cap to
#: $2.50", "set my DeepSeek cap to $5". The service word is optional; without
#: it the chosen one is used and, when that is not a single answer, the turn
#: asks which - it never guesses and never raises a card for a guess.
_CAP_AMOUNT = r"(?P<amount>\$?\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?\s*(?:dollars?|bucks|usd)?)"
_CAP_CHANGE = re.compile(
    r"(?:set|change|make|put|raise|lower|cap|limit)\b[^0-9$]{0,40}?"
    r"(?:cap|limit|budget|spending)\b[^0-9$]{0,20}?"
    + _CAP_AMOUNT + r"(?:\s*(?:a|per)\s+month|\s+monthly)?\s*\??$")

_CAP_CHANGE_NAMED = re.compile(
    r"(?:set|change|raise|lower|make)\s+(?:my|the)\s+"
    r"(?P<service>openai|chatgpt|deepseek|deep\s+seek|mistral|openrouter|"
    r"open\s+router|groq|xai|grok|cloud|api)\s+"
    r"(?:monthly\s+)?(?:cap|limit|budget)\s+(?:to|at|of)\s+"
    r"(?P<amount2>\$?\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?\s*(?:dollars?|bucks|usd)?)"
    r"(?:\s*(?:a|per)\s+month|\s+monthly)?\s*\??$")

_PROVIDER_CHANGE_NAMED = re.compile(
    r"(?:switch|change|move|set|make|use|choose|pick)\s+(?:me\s+)?(?:over\s+)?"
    r"(?:my\s+|the\s+|our\s+)?(?:cloud\s+)?(?:provider|service|api)\s+"
    r"(?:to|as)\s+(?P<name>[a-z0-9][a-z0-9 .'-]{1,40}?)\s*\??$"
    r"|(?:switch|change|move|use|choose|pick|set)\s+(?:me\s+)?(?:over\s+)?"
    r"(?:to\s+)?(?P<name2>[a-z0-9][a-z0-9 .'-]{1,40}?)\s+(?:as|for)\s+"
    r"(?:my\s+|the\s+|our\s+)?(?:cloud\s+)?(?:provider|service|api)\s*\??$")


def _change_escalation(form: str) -> Optional[dict]:
    # The existing "cloud escalation" door keeps its own sentences: its words
    # are pinned by test_cloud_escalate_setting.py, and this module must not
    # take them over. It only adds the phrasings that door does not know.
    if "cloud escalation" in form:
        return None
    if _ESC_ON.fullmatch(form):
        return {"kind": "escalation", "on": True}
    if _ESC_OFF.fullmatch(form):
        return {"kind": "escalation", "on": False}
    return None


def _change_cap(form: str) -> Optional[dict]:
    m = _CAP_CHANGE.fullmatch(form)
    amount = _dollars_value(m.group("amount")) if m is not None else None
    service = ""
    if m is None:
        m = _CAP_CHANGE_NAMED.fullmatch(form)
        if m is None:
            return None
        amount = _dollars_value(m.group("amount2"))
        service = m.groupdict().get("service") or ""
    if amount is None:
        return None
    pid = provider_for_words(service) if service else ""
    return {"kind": "cap", "dollars": amount, "provider": pid}


def _change_provider(form: str) -> Optional[dict]:
    m = _PROVIDER_CHANGE_NAMED.fullmatch(form)
    if m is None:
        return None
    name = (m.groupdict().get("name") or m.groupdict().get("name2") or "").strip()
    pid = provider_for_words(name)
    if pid:
        # A name this PC knows: the older provider door already answers this
        # sentence (and raises the same one card), so it keeps it.
        return None
    return {"kind": "provider", "provider": name, "unknown": True}


def prompt(normalized: str, raw: str = "") -> Optional[dict]:
    """The intent for one cloud-settings sentence, or None (the model's).

    `normalized` is `jarvis_quick.normalize_spoken_command`'s reading and
    `raw` the owner's own words; either may carry the shape, and the RAW one
    decides whether the sentence is a QUESTION (see `_is_question`).

    Deliberately narrow. A sentence must name the cloud provider/service, the
    escalation switch, the monthly cap or this month's spending, so every
    other sentence - a feature question, a settings change, "what is the
    cloud?" - keeps the path it had.
    """
    forms = _forms(normalized, raw)
    if not forms:
        return None
    for form in forms:
        if len(form) > 400:
            continue
        for shape, rx in _Q_QUESTION_SHAPES:
            if rx.fullmatch(form):
                return {"intent": ANSWER, "shape": shape}
    if _is_question(raw or normalized):
        return None
    for form in forms:
        if len(form) > 400:
            continue
        got = (_change_escalation(form) or _change_cap(form)
               or _change_provider(form))
        if got is not None:
            got["intent"] = CHANGE
            return got
    return None
