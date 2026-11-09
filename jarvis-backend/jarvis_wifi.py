"""jarvis_wifi.py - keep this desktop's Wi-Fi link repaired, on its own, while offline.

THE OWNER'S REQUEST (desktop chat, 2026-11-08):

    "add a feature to jarvis that defaults on but can be changed in settings or
     chat with jarvis, that jarvis if its running on a desktop and the desktop
     has lost internet connection, that it will tell the desktop to try to
     reconnect to password protected networks (that have already been connected
     to in the past on that desktop) every 2 hours on its own if its still
     offline."

WHAT THIS MODULE IS, in one paragraph: a small switch (ON by default), a
2-hourly check that only acts when the PC is really offline, and - when it acts
- a bounded attempt to reconnect using ONLY the Wi-Fi profiles Windows already
has saved in its own profile store (the password is already stored there; this
module never reads, prints, types or asks for one), never an open network and
never a new one. It reports every attempt in one calm sentence. It is PC-only.

WHAT IT MAY NOT DO, said plainly because each one is a rule rather than an
omission:
  * it never reads a Wi-Fi key: no plaintext-key export, no profile XML, no export at all;
  * it never connects to a network the PC has not saved, and never to an OPEN
    one - a profile must report a stored key and a Personal/PSK authentication
    to be a candidate;
  * it never toggles the radio, never changes a Windows setting and never
    starts/stops the owner's VPN or Meshnet app;
  * it never acts while the link is healthy, and never while a chat/voice turn
    is streaming or a multi-step task is running (idle-only);
  * it never runs more often than the owner asked (one check per 2 hours, one
    bounded attempt inside that check);
  * it never shows or logs a network name: the PC's own profile names stay in
    Windows' profile store, and this module's records name a profile only by
    its position in the list it read ("saved profile 2");
  * a model answer can never toggle it: the only writers are the Settings
    switch (through the route below) and the deterministic chat/Live sentences
    in `jarvis_quick.py`, which call the switch's own setter here.

PERMISSION SHAPE - AND THE HONEST ARGUMENT (2026-11-08). The owner asked for a
feature that is ON by default and acts on its own every 2 hours. This module
treats that ONE narrow action - "ask Windows to connect to a saved,
password-protected Wi-Fi profile while this PC has no internet" - as a STANDING
ACTION the owner explicitly enabled by asking for it and can turn off at once.
It raises NO card per attempt, because a card every 2 hours is not a question a
person can answer (the owner is often not at the PC precisely when it is
offline, and the request is to repair itself). The `wifi_reconnect_set` intent
and the Settings switch are the owner's control, and every attempt is logged and
reported. This is the same shape as the shipped read-aloud switch (ON by
default, cardless both ways, because OFF never loosens anything and ON restores
the shipped default) and the model lane's automatic restart (bounded, reported).
WHAT IT IS NOT: a general "change my network" permission. It never touches a
network that is not saved and password-protected, it never runs while the PC is
online, it never runs mid-turn, and OFF stops it immediately.

WHERE STATE LIVES: `wifi_reconnect.json` in the Jarvis settings folder (the one
every other module uses, so a backup carries it and a test can point
`OPENJARVIS_CONFIG_DIR` at a temp folder). A missing file is the shipped
default ON. A damaged file FAILS SAFE (OFF): a file that cannot be read must not
start changing the network.

THE ROUTE: GET/POST `/api/wifi-reconnect`, installed by this module's own
`install()` and loaded by `plugins/ready/wifi-reconnect/plugin.json` - the
the read-aloud and anti-slop drop-in pattern, so this feature
needs no `jarvis_hud.py` patch. The watcher is armed from `install()` only when
the real Handler class is given (a test with a fake handler never starts a
thread), because installing a route must never start background work as a side
effect.

THE ONE REAL WINDOWS CALL: `_RealLocal.connect()` is the only function in this
module that runs `netsh wlan connect`. Everything else the module needs from
Windows (the saved-profile list, the adapter/connection state) is behind the
same injectable `Local` object, so the entire backend suite runs with a
`FakeLocal` and the live connection is never touched. `net_probe()` is a read
only (a TCP connect, no payload) and is injectable too.

Standard library only. No model, no cloud, no approval card of its own.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

#: The shipped default: ON, because the owner asked for exactly that in words
#: ("defaults on but can be changed in settings or chat with jarvis"). It is a
#: recorded decision, not an accident: a missing state file means ON.
DEFAULT_ON = True

#: The owner's interval ("every 2 hours"). One check is due only when this long
#: has passed since the last one; a check that finds the PC online does not act
#: and is not retried sooner.
CHECK_INTERVAL_S = 2 * 60 * 60

#: How many saved profiles one cycle may try, and how long a single attempt may
#: take before it is called "not reconnected". Bounded on purpose: no hammering,
#: and the whole cycle stays well inside the 2-hour window.
MAX_PROFILES_PER_CYCLE = 3
ATTEMPT_SETTLE_S = 20.0
ATTEMPT_POLL_S = 2.0

#: After a cycle that could not reconnect, the next one is still only after the
#: full interval - the owner asked for two-hourly, not for a tighter retry.
#: Consecutive failures are counted so the report can say "still offline".

#: The state file and the one route.
STATE_NAME = "wifi_reconnect.json"
ROUTE_PATH = "/api/wifi-reconnect"

#: The environment switch that makes every run a DRY RUN: the diagnosis is
#: still read, the plan is still logged, and `connect()` is never called. Used
#: for every test on this PC (and by the owner window's first pass).
DRY_RUN_ENV = "JARVIS_WIFI_DRY_RUN"

#: The probe target: a TCP connect (no payload, no DNS body) through the PC's
#: current default route. If this succeeds but the Wi-Fi interface's own NCSI
#: verdict is not "Internet", the Wi-Fi link is fine and the VPN/upstream is the
#: problem - that is a different failure and this module does NOT touch Wi-Fi.
PROBE_HOST = "www.msftconnecttest.com"
PROBE_PORT = 80
PROBE_TIMEOUT_S = 4.0

#: Never a key, never a name. The only fields a record may carry about a network
#: are its POSITION in the saved-profile list it read and whether it is the one
#: Windows is currently on.
_LOCK = threading.Lock()
_WATCH = {"thread": None, "stop": None, "started_at": 0.0}

# --------------------------------------------------------------------------
#   Owner-facing words - written HERE so every surface says the same sentence
# --------------------------------------------------------------------------

STATE_ON = (
    "On. Every 2 hours while this PC has no internet, Jarvis tries the saved "
    "password-protected Wi-Fi networks it already knows - the ones Windows has "
    "connected to before - and tells you what happened. It never asks for a "
    "password, never tries an open or new network, and does nothing while the "
    "PC is online or while Jarvis is answering you."
)
STATE_OFF = (
    "Off. Jarvis never touches this PC's Wi-Fi choice. Turn it back on in "
    "Settings or by saying \"turn on the auto Wi-Fi reconnect\"."
)
SET_ON = (
    "The auto Wi-Fi reconnect is on now - every 2 hours while this PC has no "
    "internet, Jarvis will try the saved password-protected networks it already "
    "knows."
)
SET_OFF = (
    "The auto Wi-Fi reconnect is off now - I will not touch this PC's Wi-Fi "
    "choice, and nothing else changed."
)
ALREADY_ON = "The auto Wi-Fi reconnect is already on. Nothing was changed."
ALREADY_OFF = "The auto Wi-Fi reconnect is already off. Nothing was changed."
ABOUT = (
    "The auto Wi-Fi reconnect keeps this desktop's internet link repaired on "
    "its own. While this PC is offline, every 2 hours it asks Windows to "
    "connect to a Wi-Fi network this PC has already saved and whose password is "
    "already stored - never an open network, never a new one, and it never asks "
    "you for a password. It tries at most 3 saved networks per check, waits "
    "about 20 seconds for each, stops as soon as the internet is back, and says "
    "what it did. It does nothing while the PC is online, while Jarvis is "
    "answering you, or while a task is running. It is on by default and you can "
    "turn it off in Settings or by asking me."
)
NO_SAVED = (
    "The auto Wi-Fi reconnect is on, but this PC has no saved password-protected "
    "Wi-Fi network to try - Windows has no profile with a stored key on it, so "
    "there is nothing Jarvis may connect to. Join a network once yourself and "
    "it will be one of the ones Jarvis can use."
)
NOT_WINDOWS = (
    "The auto Wi-Fi reconnect is only for this PC's Windows Wi-Fi link; this "
    "computer does not report a Wi-Fi adapter, so there is nothing for it to do."
)
DRY_RUN_LINE = (
    "Dry run: Jarvis would try {what}, and would not call Windows."
)

#: The chat answers for the state and the clock question. Both are read from
#: this module's own state file by `jarvis_quick.py`'s deterministic sentences -
#: never by the model, never guessed.
NO_CHECK_YET = "It has not checked yet."


def _config_dir() -> Path:
    """The Jarvis settings folder, the same order every shipped module uses."""
    try:
        import jarvis_framework  # type: ignore
        return Path(jarvis_framework.CONFIG_DIR)
    except Exception:
        pass
    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        raw = os.environ.get(name)
        if raw:
            return Path(raw)
    return Path.home() / ".openjarvis"


def state_path() -> Path:
    """`wifi_reconnect.json` in the Jarvis settings folder."""
    return _config_dir() / STATE_NAME


def _on_disk():
    """(found, the document) for the state file. Never raises.

    `(False, None)` = never written, so the shipped default applies.
    `(True, None)` = written but unreadable, so the caller FAILS SAFE (OFF):
    a damaged file must not start changing the network.
    """
    path = state_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, None
    except OSError:
        return True, None
    try:
        doc = json.loads(raw)
    except Exception:
        return True, None
    if not isinstance(doc, dict):
        return True, None
    return True, doc


def _write(doc: dict) -> bool:
    """Write the state file atomically. False when it could not be saved.

    Called under `_LOCK` by every writer. The file holds the switch, the dry-run
    flag, the last check/attempt times, the bounded history and the last calm
    sentence - never a network name, never a password, never a key.
    """
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _now(now=None) -> float:
    return float(now if now is not None else time.time())


def dry_run() -> bool:
    """Is this build set to log what it WOULD do and never call Windows?

    The build setting is the environment variable `JARVIS_WIFI_DRY_RUN=1`
    (kept out of the UI on purpose: it is a test/owner-window build switch, not
    a setting the owner needs to see). A state file may also carry `"dry_run":
    true` so a scripted owner window can flip it for one session.
    """
    raw = str(os.environ.get(DRY_RUN_ENV) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    found, doc = _on_disk()
    return bool(found and doc and doc.get("dry_run") is True)


# --------------------------------------------------------------------------
#   The switch - read, changed, and the way it fails
# --------------------------------------------------------------------------

def enabled() -> bool:
    """Is the auto Wi-Fi reconnect on right now?

    Missing file = the shipped default (ON). A damaged file = OFF (fail safe):
    the owner can turn it back on with one sentence, and nothing acts on a
    setting that cannot be read.
    """
    found, doc = _on_disk()
    if not found:
        return DEFAULT_ON
    if doc is None:
        return False
    value = doc.get("enabled")
    if isinstance(value, bool):
        return value
    if "enabled" not in doc:
        return DEFAULT_ON
    return False


def _last(doc) -> dict:
    """The last record, or {}. Never raises on a damaged document."""
    if not isinstance(doc, dict):
        return {}
    last = doc.get("last")
    return last if isinstance(last, dict) else {}


def _next_check_at(doc) -> float:
    """The epoch the next check becomes due. 0 when it never ran."""
    if not isinstance(doc, dict):
        return 0.0
    try:
        last = float(doc.get("last_check_at") or 0)
    except (TypeError, ValueError):
        return 0.0
    return (last + CHECK_INTERVAL_S) if last > 0 else 0.0


def _when_words(epoch) -> str:
    """A short local time, or "" - the one place a timestamp becomes words."""
    try:
        value = float(epoch)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return time.strftime("%H:%M", time.localtime(value))


def state() -> dict:
    """The whole switch as the Settings page, chat and the HUD read it.

    Read-only. Carries the calm sentence (`words`), the last check's own sentence
    (`last_words`), when the next check is due, and how many saved
    password-protected profiles this PC has (a COUNT - never a name).
    """
    found, doc = _on_disk()
    on = enabled()
    known = (not found) or (doc is not None and
                            (isinstance(doc.get("enabled"), bool) or
                             "enabled" not in doc))
    last = _last(doc)
    last_words = str(last.get("words") or "").strip()
    words = STATE_ON if on else STATE_OFF
    if on and found:
        # The last check's sentence belongs on the switch line once there is
        # one: the owner opening Settings wants to know what it did, not only
        # what it would do.
        if last_words:
            words = (STATE_ON.split(" Every ")[0]
                     + " " + last_words)
    try:
        attempts = int(doc.get("attempts") or 0) if isinstance(doc, dict) else 0
    except (TypeError, ValueError):
        attempts = 0
    return {"ok": True, "enabled": on, "default": DEFAULT_ON, "known": known,
            "dry_run": dry_run(), "words": words,
            "last_words": last_words, "last_at": last.get("at"),
            "last_class": str(last.get("class") or ""),
            "last_check_at": (doc or {}).get("last_check_at") if isinstance(doc, dict) else None,
            "next_check_at": _next_check_at(doc) or None,
            "attempts": attempts, "state_path": str(state_path())}


def set_enabled(on: bool) -> dict:
    """Turn the auto Wi-Fi reconnect on or off, and say what really happened.

    Cardless in BOTH directions, and that is a decision (see this module's
    header): OFF removes an automatic action and so cannot loosen anything; ON
    restores the owner's own shipped default. The change is written atomically,
    the previous value is read before it, and OFF stops the watcher's next pass
    immediately (the loop re-reads this file before acting).
    """
    if not isinstance(on, bool):
        raise ValueError("the auto Wi-Fi reconnect takes on or off, not that")
    before = enabled()
    found, doc = _on_disk()
    doc = dict(doc) if isinstance(doc, dict) else {}
    doc["enabled"] = bool(on)
    doc["updated_at"] = _now()
    with _LOCK:
        saved = _write(doc)
    if not saved:
        return {"ok": False, "enabled": before, "before": before,
                "changed": False,
                "words": ("I could not save the auto Wi-Fi reconnect setting on "
                          "this PC - nothing changed.")}
    changed = before != on
    _publish({"enabled": bool(on), "changed": changed})
    said = ((SET_ON if on else SET_OFF) if changed
            else (ALREADY_ON if on else ALREADY_OFF))
    out = state()
    out.update({"before": before, "changed": changed, "words": said})
    return out


def state_words() -> str:
    """The chat/Live STATE answer, read from the switch itself."""
    return STATE_ON if enabled() else STATE_OFF


def set_words(on: bool) -> str:
    """The chat/Live CHANGE answer, including the honest no-op sentence."""
    changed = enabled() != on
    if changed and on:
        return SET_ON
    if changed:
        return SET_OFF
    return ALREADY_ON if on else ALREADY_OFF


def about_words() -> str:
    """The chat/Live "what does it do" answer."""
    return ABOUT


def when_words(now=None) -> str:
    """The chat/Live "when will it try again" answer, from the state file.

    It says the truth even when it cannot try: OFF, no saved profile, or online
    right now are all real answers rather than a made-up time.
    """
    if not enabled():
        return ("It will not try - the auto Wi-Fi reconnect is off. Say \"turn "
                "on the auto Wi-Fi reconnect\" or turn it on in Settings.")
    found, doc = _on_disk()
    try:
        profiles = _usable_count(profiles())
    except Exception:
        profiles = 0
    if profiles <= 0:
        return ("It will not try - this PC has no saved password-protected Wi-Fi "
                "network for Jarvis to reconnect to. Join one once yourself and "
                "it becomes one of the networks Jarvis may use.")
    if not found:
        return ("It has not tried yet. The first check is due within two hours, "
                "and it only acts if this PC is offline.")
    last_check = float(doc.get("last_check_at") or 0) if isinstance(doc, dict) else 0.0
    if last_check <= 0:
        return "It has not tried yet. The first check is due within two hours."
    last = _last(doc)
    due = _next_check_at(doc)
    last_when = _when_words(last_check)
    due_when = _when_words(due)
    said = str(last.get("words") or "").strip()
    parts = []
    if last_when:
        parts.append(f"The last check was at {last_when}.")
    if said:
        parts.append(said)
    if due_when:
        parts.append(f"The next check is due at {due_when}, and only if this PC "
                     f"still has no internet.")
    return " ".join(parts) or "It has not checked yet."


# --------------------------------------------------------------------------
#   The Windows surface: ONE injectable object, and ONE real connect call
# --------------------------------------------------------------------------
#
# Everything this module needs from Windows lives on `Local` so the entire test
# suite can pass a `FakeLocal` and never touch the live link. `_RealLocal` is
# the only implementation that runs a program, and its `connect()` is the only
# function in the repository that asks Windows to change the Wi-Fi connection.

class Local:
    """The four Windows reads/writes this module needs. Injected in tests."""

    def profiles(self) -> list:
        """[{"name": str, "secure": bool, "auto": bool}] from Windows' store."""
        raise NotImplementedError

    def connection(self) -> dict:
        """{"adapter": bool, "up": bool, "profile": str, "ipv4": str}."""
        raise NotImplementedError

    def connect(self, name: str) -> tuple:
        """(ok, detail) - ask Windows to join the saved profile `name`."""
        raise NotImplementedError


def _child_env() -> dict:
    """A narrow environment for the child programs - never the whole parent."""
    try:
        import jarvis_child_env  # type: ignore
        return jarvis_child_env.inherited(names=("PATH",))
    except Exception:
        out = {}
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME",
                     "USERPROFILE", "LOCALAPPDATA"):
            if os.environ.get(name):
                out[name] = os.environ[name]
        return out


def _run_argv(argv: list, timeout: float = 15.0) -> tuple:
    """Run one program with an argv list, never a shell. (code, stdout).

    The single subprocess helper for this module. `netsh` is always an argv
    list - never a command string - so a profile name can never be read as a
    flag or a second command.
    """
    try:
        proc = subprocess.run([str(a) for a in argv], capture_output=True,
                              text=True, timeout=timeout, shell=False,
                              env=_child_env())
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}"
    return int(proc.returncode or 0), (proc.stdout or "")


def _parse_profiles(text: str) -> list:
    """`netsh wlan show profiles` -> [{"name", "secure", "auto"}].

    The list alone does not say whether a profile is password-protected, so this
    only collects the names; `_RealLocal.profiles()` follows each with
    `show profile` (never a plaintext-key export) to read `Security key: Present` and the
    `Connection mode` line. A name listed here is exactly what Windows printed,
    so a caller can hand it back to `netsh wlan connect name=` unchanged.
    """
    names = []
    for line in str(text or "").splitlines():
        match = re.match(r"\s*All User Profile\s*:\s*(.+?)\s*$", line)
        if match:
            name = match.group(1)
            if name and name not in names:
                names.append(name)
    return [{"name": n} for n in names]


def _parse_profile_detail(text: str) -> dict:
    """`netsh wlan show profile name=…` -> the two facts that matter.

    `secure` requires BOTH a stored key (`Security key: Present`) and a
    Personal/PSK authentication - an OPEN profile has no key and is never a
    candidate. `auto` is Windows' own "Connect automatically" flag; it is
    reported, not required (the owner's feature may connect a manual profile
    only when offline, which is the same choice Windows' own UI makes).
    """
    secure = False
    auto = False
    auth = ""
    has_key = False
    for line in str(text or "").splitlines():
        low = line.strip()
        if low.lower().startswith("security key"):
            has_key = bool(re.search(r"Present\s*$", low, re.I))
        elif low.lower().startswith("authentication"):
            auth = low.split(":", 1)[-1].strip()
        elif low.lower().startswith("connection mode"):
            auto = "connect automatically" in low.lower()
    if has_key and auth:
        auth_low = auth.lower()
        secure = ("personal" in auth_low or "psk" in auth_low
                  or "sae" in auth_low)
    return {"secure": bool(secure), "auto": bool(auto),
            "authentication": auth}


class _RealLocal(Local):
    """The only implementation that talks to Windows. Never used by the tests."""

    adapter_match = "Wi-Fi"

    def profiles(self) -> list:
        code, text = _run_argv(["netsh", "wlan", "show", "profiles"], 20.0)
        if code != 0:
            return []
        out = []
        for row in _parse_profiles(text):
            name = row["name"]
            c2, detail = _run_argv(
                ["netsh", "wlan", "show", "profile", f"name={name}"], 20.0)
            facts = (_parse_profile_detail(detail) if c2 == 0
                     else {"secure": False, "auto": False, "authentication": ""})
            out.append({"name": name, "secure": bool(facts["secure"]),
                        "auto": bool(facts["auto"])})
        return out

    def connection(self) -> dict:
        """Adapter + per-interface network verdict, read without a scan.

        `Get-NetConnectionProfile` is the Network List Manager's per-interface
        view: it says whether THIS interface's network has internet, which is
        what tells "Wi-Fi is broken" from "the VPN/upstream is broken". It needs
        no Location permission (a scan would) and changes nothing.
        """
        script = (
            "$ErrorActionPreference='Stop';"
            "$w=@(Get-NetAdapter -Name 'Wi-Fi*' -ErrorAction SilentlyContinue);"
            "$p=@(Get-NetConnectionProfile -ErrorAction SilentlyContinue);"
            "$o=[pscustomobject]@{adapter=($w.Count -gt 0);"
            "up=[bool](@($w | Where-Object {$_.Status -eq 'Up'}).Count -gt 0);"
            "profile=(@($p | Where-Object {$_.InterfaceAlias -like 'Wi-Fi*'} | "
            "Select-Object -First 1 -ExpandProperty Name) -join '');"
            "ipv4=(@($p | Where-Object {$_.InterfaceAlias -like 'Wi-Fi*'} | "
            "Select-Object -First 1 -ExpandProperty IPv4Connectivity) -join '')};"
            "$o | ConvertTo-Json -Compress")
        code, text = _run_argv(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script], 20.0)
        if code != 0:
            return {"adapter": False, "up": False, "profile": "", "ipv4": ""}
        try:
            doc = json.loads(text.strip() or "{}")
        except Exception:
            return {"adapter": False, "up": False, "profile": "", "ipv4": ""}
        return {"adapter": bool(doc.get("adapter")),
                "up": bool(doc.get("up")),
                "profile": str(doc.get("profile") or ""),
                "ipv4": str(doc.get("ipv4") or "")}

    def connect(self, name: str) -> tuple:
        """THE one real network-changing call: `netsh wlan connect name=<saved>`.

        The profile must already exist (the caller only ever passes a name it
        read from this PC's own store). The command's own documentation says it
        connects to a saved profile with no password prompt, and that joining the
        network it is already on is a no-op (so a two-hourly retry cannot flap a
        working link). The caller polls `connection()` for the real result: the
        command itself is not a result code.
        """
        code, text = _run_argv(
            ["netsh", "wlan", "connect", f"name={name}"], 30.0)
        return code == 0, (text or "").strip()[:200]


def net_probe(*, host: str = PROBE_HOST, port: int = PROBE_PORT,
              timeout: float = PROBE_TIMEOUT_S) -> bool:
    """Is there internet through the PC's current route? A TCP connect only.

    No payload, no certificate, no DNS query the caller can read: one bounded
    connect to port 80 of Microsoft's NCSI host (the same host Windows' own
    connectivity check uses). Read-only and injectable; a failure is data, not
    an exception.
    """
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout)):
            return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   Diagnosis - "offline" is not "Wi-Fi is broken"
# --------------------------------------------------------------------------

CLASS_ONLINE = "online"
CLASS_WIFI_DISCONNECTED = "wifi_disconnected"
CLASS_WIFI_NO_INTERNET = "wifi_no_internet"
CLASS_UPSTREAM = "upstream_down"
CLASS_NO_ADAPTER = "no_wifi_adapter"
CLASS_UNKNOWN = "unknown"


def diagnose(*, local: Local, probe=None, now=None) -> dict:
    """Which failure is this? A dict with `class`, `words` and the facts.

    THE DISTINCTION IS THE POINT. This PC's internet runs through a VPN tunnel
    (measured 2026-11-08: NordLynx is the default route; the Wi-Fi interface's
    own verdict was "Internet"). So "no internet" has four shapes, and only two
    of them are Wi-Fi's fault:

    * no adapter at all -> report only;
    * Wi-Fi not up -> `wifi_disconnected` (a reconnect is justified);
    * Wi-Fi up but its own network says not Internet -> `wifi_no_internet`
      (a reconnect is justified);
    * Wi-Fi up and its own network says Internet, but a real probe fails ->
      `upstream_down`: the VPN/tunnel/DNS or the wider internet is the problem.
      **Wi-Fi is NOT touched** - reconnecting it cannot fix this and would drop
      the tunnel and the phone link.
    """
    facts = local.connection() if local is not None else {}
    adapter = bool((facts or {}).get("adapter"))
    up = bool((facts or {}).get("up"))
    profile = str((facts or {}).get("profile") or "")
    ipv4 = str((facts or {}).get("ipv4") or "")
    if not adapter:
        return {"class": CLASS_NO_ADAPTER, "adapter": False, "up": False,
                "profile": "", "ipv4": ipv4, "probed": False,
                "wifi_broken": False,
                "words": ("This PC reports no Wi-Fi adapter, so there is no "
                          "wireless link for Jarvis to repair.")}
    if not up:
        return {"class": CLASS_WIFI_DISCONNECTED, "adapter": True, "up": False,
                "profile": profile, "ipv4": ipv4, "probed": False,
                "wifi_broken": True,
                "words": "The Wi-Fi is disconnected."}
    if ipv4.lower() != "internet":
        return {"class": CLASS_WIFI_NO_INTERNET, "adapter": True, "up": True,
                "profile": profile, "ipv4": ipv4, "probed": False,
                "wifi_broken": True,
                "words": ("The Wi-Fi is connected to its network but that "
                          "network has no internet.")}
    reachable = bool((probe or net_probe)())
    if reachable:
        return {"class": CLASS_ONLINE, "adapter": True, "up": True,
                "profile": profile, "ipv4": ipv4, "probed": True,
                "wifi_broken": False,
                "words": "The internet is working."}
    return {"class": CLASS_UPSTREAM, "adapter": True, "up": True,
            "profile": profile, "ipv4": ipv4, "probed": True,
            "wifi_broken": False,
            "words": ("The Wi-Fi link is fine and this PC's network says it has "
                      "internet, but a real connection to the internet failed - "
                      "so the problem is the VPN/private link or the internet "
                      "upstream, not the Wi-Fi. Jarvis will not change the Wi-Fi.")}


# --------------------------------------------------------------------------
#   Read the saved store, choose only the ones the owner allowed
# --------------------------------------------------------------------------

def profiles(*, local: Local = None) -> list:
    """The saved profiles, read-only. Never raises; never returns a key.

    Each row is {"name", "secure", "auto", "id"} where `id` is the profile's
    position in the list Windows returned - the only identifier this module ever
    writes down. A name the caller cannot read is kept out (a candidate must be
    usable), and nothing here mentions passwords or key material at all.
    """
    try:
        rows = list((local or _RealLocal()).profiles() or [])
    except Exception:
        return []
    out = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        out.append({"name": name, "secure": bool(row.get("secure")),
                    "auto": bool(row.get("auto")), "id": index})
    return out


def _usable(rows) -> list:
    """Only the password-protected ones - the owner's rule, enforced here."""
    return [r for r in (rows or ()) if r.get("secure")]


def _usable_count(rows) -> int:
    return len(_usable(rows))


def candidate_order(rows, current: str = "") -> list:
    """Which saved profiles to try, in order: the one in use first, then the rest.

    The current profile is tried first because reconnecting it is the cheapest
    repair and (per the netsh documentation) a no-op when it is already the
    active network. The rest follow in Windows' own order. Only names that are
    `secure` are ever returned; `current` is matched to a SAVED profile, so a
    name Windows never stored can never be introduced.
    """
    usable = _usable(rows)
    if not usable:
        return []
    first = [r for r in usable if r.get("name") == current]
    rest = [r for r in usable if r.get("name") != current]
    return first + rest


def plan(rows, *, current: str = "") -> list:
    """What a cycle would try, in words a log can carry (no network names).

    Each entry names the profile only by its saved-list position and says
    whether it is the one in use. This is the dry-run's output and the attempt
    log's shape - so a log can be read without revealing the owner's networks.
    """
    out = []
    for row in candidate_order(rows, current)[:MAX_PROFILES_PER_CYCLE]:
        out.append({"id": int(row.get("id") or 0),
                    "current": bool(current and row.get("name") == current),
                    "words": ("the network this PC is on now"
                              if current and row.get("name") == current
                              else f"saved profile {int(row.get('id') or 0)}")})
    return out


# --------------------------------------------------------------------------
#   One bounded check: the 2-hourly cycle
# --------------------------------------------------------------------------

def _busy_words() -> str:
    """Why this is not a moment to touch the network, or "".

    Borrowed from the shipped modules rather than re-implemented: the benchmark's
    own "is an answer streaming" reader, its standby reader and its multi-step
    task reader are the same questions every background action in this project
    asks. A backend without those modules simply has nothing busy to report.
    """
    try:
        import jarvis_bench  # type: ignore
    except Exception:
        return ""
    try:
        if jarvis_bench.answer_streaming():
            return "a chat or voice answer is streaming"
    except Exception:
        pass
    try:
        if jarvis_bench.read_standby():
            return "Jarvis is on standby"
    except Exception:
        pass
    try:
        if jarvis_bench.running_tasks():
            return "a task is running"
    except Exception:
        pass
    return ""


def due(now=None, *, doc=None) -> bool:
    """Is a check due NOW? Read-only; the 2-hour spacing lives here.

    A missing `last_check_at` is due (the first check after install); otherwise
    due only when the full interval has passed. Across sleep/resume this means
    one check on waking, not a burst: the file carries the real last time.
    """
    found, ondisk = _on_disk()
    document = doc if isinstance(doc, dict) else (ondisk if found else {})
    try:
        last = float((document or {}).get("last_check_at") or 0)
    except (TypeError, ValueError):
        last = 0.0
    if last <= 0:
        return True
    return (_now(now) - last) >= CHECK_INTERVAL_S


def _record(doc, *, kind: str, words: str, when: float, extra: dict = None) -> dict:
    """One history row: bounded, names never, the calm sentence always."""
    row = {"at": when, "class": str(kind), "words": str(words)[:300]}
    if extra:
        for key, value in extra.items():
            if key in ("id", "current", "attempt", "dry_run", "online"):
                row[key] = value
    doc = dict(doc or {})
    history = doc.get("history") if isinstance(doc.get("history"), list) else []
    history.append(row)
    doc["history"] = history[-20:]
    doc["last"] = row
    return doc


def check_once(*, now=None, local: Local = None, probe=None,
               busy=None, persist: bool = True, sleep=None) -> dict:
    """Run ONE 2-hourly check. Returns the record it wrote (or would write).

    THE ORDER IS THE SAFETY, top to bottom:
      1. the switch is read first - OFF returns at once, touches nothing;
      2. the 2-hour spacing is read from the state file (sleep/resume safe);
      3. a busy check: an answer streaming, standby, or a task running means
         this cycle is SKIPPED and said so - never a network change mid-turn;
      4. the diagnosis: ONLINE does nothing; UPSTREAM (Wi-Fi fine, VPN/internet
         broken) does nothing to Wi-Fi and says why; only a genuinely broken
         Wi-Fi link goes on;
      5. the saved store is read (read-only) and only `secure` profiles are
         candidates; a PC with none says so;
      6. at most `MAX_PROFILES_PER_CYCLE` attempts, each bounded; the first one
         that brings the internet back stops the cycle.
    A DRY RUN does 1-5, writes the plan, and never calls `connect()`.

    `now`, `local`, `probe` and `busy` exist so the suite can drive every branch
    with no network, no Windows call and no clock.
    """
    when = _now(now)
    on = enabled()
    found, doc = _on_disk()
    doc = dict(doc) if isinstance(doc, dict) else {}
    if not on:
        return {"ok": True, "ran": False, "class": "off",
                "dry_run": dry_run(),
                "words": "The auto Wi-Fi reconnect is off; nothing was checked."}
    if not due(when, doc=doc):
        return {"ok": True, "ran": False, "class": "not_due",
                "dry_run": dry_run(),
                "words": "Not due yet; the last check is inside the two hours."}
    blocked = (busy() if callable(busy) else _busy_words())
    if blocked:
        words = f"Check skipped: {blocked}, and Jarvis never changes the network then."
        doc = _record(doc, kind="skipped", words=words, when=when)
        doc["last_check_at"] = when
        if persist:
            with _LOCK:
                _write(doc)
        return {"ok": True, "ran": False, "class": "skipped",
                "dry_run": dry_run(), "words": words}
    real = local or _RealLocal()
    try:
        facts = diagnose(local=real, probe=probe, now=when)
    except Exception as exc:
        facts = {"class": CLASS_UNKNOWN, "wifi_broken": False,
                 "words": f"The Wi-Fi state could not be read ({type(exc).__name__})."}
    dry = dry_run()
    if not facts.get("wifi_broken"):
        doc = _record(doc, kind=str(facts.get("class") or CLASS_UNKNOWN),
                      words=str(facts.get("words") or ""), when=when)
        doc["last_check_at"] = when
        if persist:
            with _LOCK:
                _write(doc)
        return {"ok": True, "ran": True, "class": facts.get("class"),
                "dry_run": dry, "online": facts.get("class") == CLASS_ONLINE,
                "words": str(facts.get("words") or "")}
    rows = profiles(local=real)
    candidates = candidate_order(rows, current=str(facts.get("profile") or ""))
    if not candidates:
        words = NO_SAVED
        doc = _record(doc, kind="no_saved_profiles", words=words, when=when)
        doc["last_check_at"] = when
        if persist:
            with _LOCK:
                _write(doc)
        return {"ok": True, "ran": True, "class": "no_saved_profiles",
                "dry_run": dry, "words": words}
    planned = plan(rows, current=str(facts.get("profile") or ""))
    attempts = []
    final_words = ""
    reconnected = False
    for row in candidates[:MAX_PROFILES_PER_CYCLE]:
        ident = int(row.get("id") or 0)
        what = ("the network this PC is on now" if row.get("name") ==
                str(facts.get("profile") or "") else f"saved profile {ident}")
        if dry:
            attempts.append({"id": ident, "attempt": "would-connect",
                             "dry_run": True,
                             "words": f"Dry run: would ask Windows to connect to {what}."})
            final_words = ("Dry run: Jarvis would soon try " +
                           ", ".join(entry["words"] for entry in planned) +
                           ". It did not call Windows and nothing changed.")
            break
        ok, detail = False, ""
        try:
            ok, detail = real.connect(str(row.get("name") or ""))
        except Exception as exc:
            detail = f"{type(exc).__name__}"
        attempts.append({"id": ident, "attempt": "connect",
                         "ok": bool(ok),
                         "words": f"Asked Windows to connect to {what}."})
        reconnected = _settle(real, probe=probe, sleep=sleep)
        if reconnected:
            final_words = ("The desktop's Wi-Fi was down; Jarvis reconnected to "
                           "a saved password-protected network this PC already "
                           "knew and the internet is back.")
            break
    if not final_words:
        final_words = (
            "The desktop's Wi-Fi is still down; Jarvis tried "
            + str(len(attempts)) + " saved password-protected network(s) and "
              "none brought the internet back. It will try again in 2 hours.")
    record = {"ok": True, "ran": True, "class": "attempted",
              "dry_run": dry, "attempts": attempts, "reconnected": bool(reconnected),
              "words": final_words}
    doc = _record(doc, kind="attempted", words=final_words, when=when,
                  extra={"attempt": len(attempts), "dry_run": bool(dry),
                         "online": bool(reconnected)})
    doc["last_check_at"] = when
    try:
        attempts_total = int(doc.get("attempts") or 0) + (1 if attempts and not dry else 0)
    except (TypeError, ValueError):
        attempts_total = 0
    doc["attempts"] = attempts_total
    if persist:
        with _LOCK:
            _write(doc)
    _publish({"state": "attempted", "reconnected": bool(reconnected),
              "dry_run": bool(dry), "words": final_words})
    return record


def _settle(local, *, probe=None, sleep=None, timeout: float = ATTEMPT_SETTLE_S,
            poll: float = ATTEMPT_POLL_S) -> bool:
    """Wait, bounded, for the internet to come back after an attempt.

    It asks the same diagnosis twice: the Wi-Fi interface's own verdict first
    (association takes a moment even when the network is right), then a real
    probe. Never longer than `timeout`, so one cycle can never hang.
    """
    waiter = sleep or time.sleep
    remaining = float(timeout)
    step = max(0.1, float(poll))
    while remaining > 0:
        try:
            facts = diagnose(local=local, probe=probe)
        except Exception:
            facts = {}
        if facts.get("class") == CLASS_ONLINE:
            return True
        if facts.get("class") == CLASS_UPSTREAM:
            # The link is up; whether the tunnel settles is not Wi-Fi's job.
            return True
        waiter(step)
        remaining -= step
    return False


# --------------------------------------------------------------------------
#   The watcher - ONE cheap beat, armed from install() on the real backend
# --------------------------------------------------------------------------

def watch_start(*, local: Local = None, probe=None, sleep=None) -> str:
    """Arm the 2-hourly beat. Returns the one banner line startup prints.

    The thread is a daemon and does one cheap thing per tick: re-read the switch,
    ask whether a check is due, and sleep otherwise. It is deliberately NOT
    started by a state read or by the route: installing must never start
    background work (the same rule `jarvis_model_lanes.watch_start()` follows).
    """
    stop = threading.Event()
    with _LOCK:
        if _WATCH["thread"] is not None and _WATCH["thread"].is_alive():
            return "wifi-reconnect   the 2-hour online check is already armed"
        _WATCH["stop"] = stop
        _WATCH["started_at"] = time.time()

        def loop():
            waiter = sleep or time.sleep
            while not stop.is_set():
                try:
                    if enabled() and due():
                        check_once(local=local, probe=probe)
                        continue
                except Exception:
                    # A background beat that dies is worse than one that waits.
                    pass
                # Tick at most every 5 minutes: cheap, and it means the
                # 2-hour mark is honoured within a few minutes of waking.
                waiter(300.0 if sleep is None else 0.01)

        thread = threading.Thread(target=loop, name="jarvis-wifi-reconnect",
                                  daemon=True)
        _WATCH["thread"] = thread
        thread.start()
    return ("wifi-reconnect   the 2-hour online check is armed (on by default; "
            "off in Settings)")


def watch_stop() -> bool:
    """Stop the beat (tests and a clean shutdown). True when one was running."""
    with _LOCK:
        stop = _WATCH.get("stop")
        thread = _WATCH.get("thread")
        if stop is not None:
            stop.set()
        _WATCH["thread"] = None
        _WATCH["stop"] = None
        return bool(thread is not None and getattr(thread, "is_alive", lambda: False)())


def _publish(data: dict) -> None:
    """Tell an open event stream what happened. Never raises, never a name."""
    try:
        import jarvis_events  # type: ignore
        jarvis_events.BUS.publish("wifi_reconnect", data)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   The route (GET the state, POST one switch change) - installed by the loader
# --------------------------------------------------------------------------

def _from_this_pc(peer: str) -> bool:
    """The switch is PC-only by nature: no phone may change this PC's network."""
    text = str(peer or "").strip().lower()
    if not text:
        return False
    if text in ("127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"):
        return True
    return text.startswith("127.") or text.startswith("::ffff:127.")


def handle_get(route: str, query: str = "", *, peer: str = "127.0.0.1") -> tuple:
    """GET /api/wifi-reconnect -> (200, the state). A read; nothing is written."""
    if route != ROUTE_PATH:
        return 404, {"ok": False, "error": "not_found"}
    if not _from_this_pc(peer):
        return 403, {"ok": False, "error": "pc_only",
                     "message": ("The Wi-Fi reconnect setting is changed on the "
                                 "desktop itself, not from another device.")}
    return 200, state()


def handle_post(route: str, body: object, *, peer: str = "127.0.0.1") -> tuple:
    """POST /api/wifi-reconnect {"enabled": true|false} -> (200, the new state).

    One setting only; anything else is a 400 rather than a silent ignore, so a
    caller with a typo finds out. Cardless in both directions (see the module
    header), and a failed save is reported as not saved.
    """
    if route != ROUTE_PATH:
        return 404, {"ok": False, "error": "not_found"}
    if not _from_this_pc(peer):
        return 403, {"ok": False, "error": "pc_only",
                     "message": ("The Wi-Fi reconnect setting is changed on the "
                                 "desktop itself, not from another device.")}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "bad_body",
                     "message": "the request body must be a JSON object"}
    unknown = sorted(set(body) - {"enabled"})
    if unknown:
        return 400, {"ok": False, "error": "unknown_setting",
                     "message": f"the auto Wi-Fi reconnect has no setting called "
                                f"{unknown[0]}"}
    try:
        out = set_enabled(body.get("enabled"))
    except ValueError as exc:
        return 400, {"ok": False, "error": "bad_value", "message": str(exc)}
    except Exception as exc:                     # noqa: BLE001 - said, not swallowed
        return 503, {"ok": False, "error": type(exc).__name__,
                     "message": "the auto Wi-Fi reconnect setting could not be saved"}
    return (200 if out.get("ok") else 503), out


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap the core Handler so this module answers its own route.

    The read-aloud `install()` shape: every other request goes straight
    to the original. The watcher is armed here ONLY for a real
    `http.server` Handler class - a test that installs this module against a fake
    handler gets the route and no thread.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_wifi", False):
        return "wifi-reconnect   the 2-hour online check is already on"
    from urllib.parse import urlsplit

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

    def _peer(self) -> str:
        try:
            return str((getattr(self, "client_address", None) or ("",))[0])
        except Exception:
            return ""

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route != ROUTE_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query, peer=_peer(self))
        except Exception as exc:                 # noqa: BLE001 - never a traceback page
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route != ROUTE_PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body, peer=_peer(self))
        except Exception as exc:                 # noqa: BLE001 - never a traceback page
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_wifi = True
    do_POST._jarvis_wifi = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    try:
        real = (isinstance(handler_cls, type)
                and "BaseHTTPRequestHandler" in
                [c.__name__ for c in handler_cls.__mro__])
    except Exception:
        real = False
    if real and not dry_run():
        return watch_start()
    return ("wifi-reconnect   on by default; the 2-hour check is NOT armed "
            "(dry run or a test handler)")
