"""jarvis_egress_gate.py - one decision, asked before any word leaves this PC.

WHAT THIS IS, IN PLAIN WORDS
Jarvis answers most things on this PC with a model in Ollama. A few features
instead ask a company's AI service on the internet. Each of those senders used
to decide for itself whether it was allowed to. This module is the single
question they ask before they open a socket:

    check_egress(caller, target_url, payload, surface, local_only=None)

It answers with a `Decision`: `allowed` (True or False), a machine-readable
`reason` ("loopback", "escalate_off", "lockdown", "money_limit", ...), and
`words` - one plain sentence for the owner. For a refusal, `Decision.token` is
also "EGRESS_BLOCKED:<reason>", so a caller that wants a code has one.

WHAT IT DECIDES
  * A LOOPBACK address (127.0.0.1, anything in 127.0.0.0/8, localhost, ::1) is
    this PC talking to itself. It is ALWAYS allowed and needs no file read.
  * Any other address needs ALL THREE of these to say yes:
      1. The standing cloud switch is ON: escalate-cloud.json in the Jarvis
         settings folder says {"on": true}. Absent, unreadable or corrupt is
         OFF. Read by jarvis_presets.escalate_on(), not read again here.
      2. Lockdown is OFF. Read by jarvis_asks_first.lockdown_on(), whose own
         reading already fails closed (a damaged file reads as ON).
      3. The monthly money cap in chatbot/api-money.json is readable, set for
         the service that address belongs to, and not yet reached. Read by
         jarvis_chatbot_api.money_check(), the same check that driver already
         makes before it sends.
  * A caller may pass local_only=True for something that must stay on this PC
    (email, files, credentials, stored memory: rule 1). That refuses a
    non-loopback address without reading any setting.
  * A non-loopback address that belongs to no service this PC has settings for
    is refused: its money cap cannot be read, so the answer cannot be yes.

FAIL CLOSED, AND WHAT "CLOSED" MEANS HERE
Closed means REFUSED. A missing switch file is off; an unreadable or corrupt
one is off too. A damaged Lockdown file is on. A money file that cannot be
read, a service with no limit or no price, and a host that names no service all
refuse. None of those can return an allow, and an unexpected failure inside
this module is converted into a refusal with reason "config_unreadable".
The only way to an allow is an explicit yes from every reader, plus an
explicit ON from the standing switch.

WHAT IT NEVER DOES
  * It NEVER RAISES. Every path returns a Decision; a broken cloud setting
    becomes a refusal, never an exception a local caller has to catch.
  * It opens no socket, sends nothing and writes nothing.
  * It does not read the words of `payload`. The payload is only measured
    (its length is carried on the decision for the record); whether the words
    are private is decided by the existing checks in each sender, before this
    question is asked.
"""
from __future__ import annotations

import ipaddress
import urllib.parse
from dataclasses import dataclass
from typing import Optional

#: The reasons a Decision can carry. A refusal's reason is the part after
#: "EGRESS_BLOCKED:" in its token.
LOOPBACK = "loopback"
ALLOWED = "allowed"
LOCAL_ONLY = "local_only"
LOCKDOWN = "lockdown"
ESCALATE_OFF = "escalate_off"
MONEY_LIMIT = "money_limit"
UNKNOWN_SERVICE = "unknown_service"
BAD_TARGET = "bad_target"
CONFIG_UNREADABLE = "config_unreadable"

#: A refusal's plain words when the module itself could not finish the check.
_CANNOT_READ = ("Nothing was sent: Jarvis could not read the cloud settings on this PC, "
                "and it never sends anything when it cannot check.")


@dataclass(frozen=True)
class Decision:
    """The answer to one egress question.

    `allowed` is the decision; `reason` is the machine-readable code; `words`
    is the sentence a person can read ("" when the answer is yes). A refusal
    also carries `token` = "EGRESS_BLOCKED:<reason>". The rest is the record
    of what was asked, kept so a caller can log or show it without guessing.
    """

    allowed: bool
    reason: str
    words: str = ""
    caller: str = ""
    surface: str = ""
    target: str = ""
    payload_chars: int = 0

    @property
    def token(self) -> str:
        """The one-code form of a refusal: "EGRESS_BLOCKED:<reason>"."""
        return "" if self.allowed else "EGRESS_BLOCKED:" + self.reason

    def __bool__(self) -> bool:
        return self.allowed


def _refuse(reason: str, words: str, **where) -> Decision:
    return Decision(False, reason, words, **where)


def _is_loopback(host: str) -> bool:
    """Is `host` this PC? 127.0.0.0/8, ::1 and localhost all are."""
    h = (host or "").strip().strip("[]").rstrip(".").lower()
    if not h:
        return False
    if h == "localhost" or h.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _service_for(url: str):
    """(preset id, preset) whose base address names the same host, else (None, None).

    The monthly money cap is kept per service in chatbot/api-money.json, so
    this is how a target address is tied to the cap that applies to it. The
    two senders this gate serves both use `jarvis_chatbot_api.PRESETS`.
    """
    import jarvis_chatbot_api as API
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    for pid, preset in API.PRESETS.items():
        base = urllib.parse.urlsplit(str(getattr(preset, "base_url", "") or ""))
        base_host = (base.hostname or "").lower().rstrip(".")
        if base_host and base_host == host:
            return pid, preset
    return None, None


def _money_refusal(pid: str, chars: int, **where) -> Optional[Decision]:
    """The cap's answer for one service, as a refusal or None.

    `money_check(..., next_messages=0)` is the driver's own monthly-cap check:
    it reads the same file, answers the driver's own plain words for an
    unreadable file, no limit, no price or a reached limit, and needs no
    answer-length arithmetic. The next message's worst case stays where it
    already lives - in the sender, before it builds the request.
    """
    import jarvis_chatbot_api as API
    try:
        model = API.model_for(pid)[0]
    except Exception:
        model = ""
    why, _cap = API.money_check(pid, model, next_chars=chars, next_messages=0)
    if not why:
        return None
    return _refuse(MONEY_LIMIT, "Nothing was sent. " + str(why), **where)


def check_egress(caller, target_url, payload, surface,
                 local_only: Optional[bool] = None) -> Decision:
    """May this request leave this PC? A Decision; never an exception.

    `caller` and `surface` are names for the record ("jarvis_chatbot_api",
    "quiz_cloud"); `target_url` is the exact address the sender is about to
    open; `payload` is what would be sent (only its size is read);
    `local_only=True` means the caller already knows the words must stay here.

    The order below is the order a person would ask:
      1. Is this PC itself (loopback)? Then yes, always.
      2. Has the caller declared that this stays on the PC? Then no.
      3. Is Lockdown on? Then no.
      4. Is the standing cloud switch on? If not, no.
      5. Does the monthly cap for the service allow it? If not, no.
    Every step after the first must say yes; the first no is the answer.
    """
    caller = str(caller or "")
    surface = str(surface or "")
    target = str(target_url or "")
    where = {"caller": caller, "surface": surface, "target": target}
    try:
        size = len(payload) if isinstance(payload, (str, bytes, bytearray)) else 0
        where["payload_chars"] = size
        try:
            parts = urllib.parse.urlsplit(target)
            host = (parts.hostname or "").lower().rstrip(".")
        except ValueError:
            return _refuse(BAD_TARGET, "Nothing was sent: that address is not a web "
                                        "address Jarvis can check.", **where)
        if parts.scheme not in ("http", "https") or not host:
            return _refuse(BAD_TARGET, "Nothing was sent: that address is not a web "
                                        "address Jarvis can check.", **where)
        if _is_loopback(host):
            return Decision(True, LOOPBACK, "", **where)
        if local_only:
            return _refuse(LOCAL_ONLY, "Nothing was sent: this is something that stays "
                                        "on this PC.", **where)

        # 3. Lockdown. Its own reader fails closed, so a damaged file is ON.
        try:
            import jarvis_asks_first as asks
            locked = bool(asks.lockdown_on())
        except Exception:
            return _refuse(CONFIG_UNREADABLE, _CANNOT_READ, **where)
        if locked:
            return _refuse(LOCKDOWN, "Nothing was sent: Lockdown is on, so Jarvis is not "
                                      "using a cloud service.", **where)

        # 4. The standing cloud switch. Absent, unreadable or corrupt is OFF.
        try:
            import jarvis_presets as presets
            on = bool(presets.escalate_on())
        except Exception:
            return _refuse(CONFIG_UNREADABLE, _CANNOT_READ, **where)
        if not on:
            return _refuse(ESCALATE_OFF,
                           "Nothing was sent: Jarvis only uses a cloud service when the "
                           "standing cloud switch is on, and this PC's switch is off or "
                           "cannot be read. You can turn it on in the Presets menu, under "
                           "Cloud.", **where)

        # 5. The monthly cap for the service this address belongs to.
        try:
            pid, preset = _service_for(target)
        except Exception:
            return _refuse(CONFIG_UNREADABLE, _CANNOT_READ, **where)
        if pid is None:
            return _refuse(UNKNOWN_SERVICE,
                           "Nothing was sent: Jarvis has no cloud service settings for "
                           f"{host}, so it cannot check whether this may leave the PC.",
                           **where)
        try:
            no = _money_refusal(pid, size, **where)
        except Exception:
            return _refuse(CONFIG_UNREADABLE, _CANNOT_READ, **where)
        if no is not None:
            return no
        return Decision(True, ALLOWED, "", **where)
    except Exception:  # the belt over every brace above: never raise outward
        return _refuse(CONFIG_UNREADABLE, _CANNOT_READ, **where)
