"""jarvis_power_switch.py - the Active / Quiet / Standby switch the apps lacked.

WHAT WAS MISSING
`/api/status` reports the power mode and a `power` event says when it
changes, but nothing could CHANGE it: the phone's quick-settings tile says
so in its own comment, and the desktop's FAQ explains Quiet and Standby
without anywhere to choose them. `jarvis_power.set_mode()` existed with no
route to it.

WHAT THIS DOES (power-mode.patch adds `POST /api/power`)
    {"mode": "active" | "quiet" | "standby"}

    active    answers, and may speak first.
    quiet     answers, but does not start things on its own.
    standby   also frees the graphics cards (what the desktop FAQ
              promises): the loaded model is unloaded, and so are the
              second card's Ollama, the big model and the better voice
              when they run (jarvis_second_card.sleep, jarvis_big_model.sleep,
              jarvis_voices.sleep; a big-model job already under way is left
              to finish; custom voices go on speaking from the processor).
              The next answer
              takes 5-15 seconds while it loads again.

EVERY MODEL, NOT ONLY THE ONE jarvis_models NAMES (added 2026-09-25, with
the standby schedule). Standby used to unload only what the owner's
jarvis_models.resident_models() listed, and only if that file has an
unload(). Anything else Ollama held on the card stayed there: a picture or
embedding model, the extra-feature models a one-card setup runs inside the
everyday Ollama (HARDWARE-PROFILES 4.3), or everything, on a jarvis_models
without unload(). So standby now also asks the everyday Ollama itself what
is loaded (GET /api/ps) and unloads each model still there - the request
Ollama's own documentation gives for it, `keep_alive: 0` with no prompt -
then reads /api/ps again and says plainly if anything is still loaded.
This PC's Ollama only (OLLAMA_URL must be loopback), with no proxy
(jarvis_local_http). Only model names are sent. With one graphics card the
second card's step finds nothing and says nothing.

WARM-UP ON WAKING (added 2026-09-25). Leaving standby (for Active or Quiet)
loads the everyday chat model again straight away, in the background, so
the first question after waking is not the slow one. It asks this PC's
Ollama to load jarvis_models.current_model() with no prompt - nothing is
generated - and leaves keep_alive to Ollama's own setting (-1, "keep it
loaded", on the owner's PC). Refused, with the reason, for a cloud model
(":cloud", "-cloud") or an OLLAMA_URL that is not this PC - the same two
checks the chat path makes (ARCHITECTURE section 4). If Jarvis is back on
standby by the time the model has loaded, it is unloaded again. The second
card's engines are not warmed: they start when a feature needs them, as
before. `warm_status()` says how the last one went.

THE ANSWER COMES WHEN THE MODE HAS CHANGED, not when every card is freed:
unloading can take several seconds, and waiting for it made an app that
waited `wait_s` say "Waiting for your approval" when no card was up. The
mode changes (and the `power` event goes out) first; the freeing carries on
and is written to the audit log.

PERMISSION - the one model, and why it does not ask by default
It goes through jarvis_gate.check("power_manage", ...), like everything else.
The owner's jarvis-framework.toml sets `power_manage = "auto"`, with the
reason written next to it: "Putting Jarvis into quiet/standby, or waking it,
is the safe direction either way, so it does not interrupt you for a yes."
Nothing here overrides that: set the tier to "ask" in that file and a card
appears, and this waits for it. Both directions are treated the same because
that file says both are safe; waking only restores the ordinary state. The
apps hold WAKING on a stale link (rule 4) and let going quieter through.

What is still gated elsewhere and NOT reachable from here: the RULES that put
Jarvis under on their own (quiet hours, the idle timer) - that is
`change_own_config`, and there is no setter for it on purpose. The standby
schedule (jarvis_standby_schedule.py) is not one of those: it is a job on
the one scheduler, set up by its own approval card (schedule_repeat), and
each time it goes off it comes through set_mode() here, under power_manage,
like a tap in either app.

REFUSED
Standby while a multi-step task is running (unloading the model under it
would break it): stop the task first. With the tier set to "ask", that is
checked again AFTER the card is approved, before anything is unloaded - a
task may have started while the card waited.

A second change while a power card is still waiting (409): approve or deny
that one first. Otherwise two cards could be up at once, and the one
answered last - not the one asked for last - would decide the mode.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

MODES = ("active", "quiet", "standby")

_WORDS = {
    "active": "Active: Jarvis answers, and may speak first.",
    "quiet": "Quiet: Jarvis still answers you, but starts nothing on its own.",
    "standby": ("Standby: Jarvis frees its graphics cards by unloading its models. The "
                "next answer takes 5-15 seconds while it loads again."),
}


def _gate_check(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error."""
    class _Refused:
        allowed = False
        outcome = "refused"

        def __init__(self, reason):
            self.reason = reason
    try:
        import jarvis_gate
    except Exception as exc:
        return _Refused(f"the approval gate is not available here ({exc})")
    try:
        return jarvis_gate.check(action, detail, prompt=prompt)
    except Exception as exc:
        return _Refused(f"the approval gate raised {type(exc).__name__}")


def _running_tasks() -> list:
    try:
        import jarvis_task_control
        return jarvis_task_control.running()
    except Exception:
        return []


def _unload_models(models) -> dict:
    """Unload whatever model is resident. Best-effort; says what happened."""
    try:
        if models is None:
            import jarvis_models as models
        names = list((getattr(models, "resident_models", lambda: [])() or []))
        unload = getattr(models, "unload", None)
    except Exception as exc:
        return {"unloaded": [], "note": f"could not ask which model is loaded ({exc})"}
    if unload is None:
        return {"unloaded": [], "note": "this backend's jarvis_models has no unload(); "
                                        "the model stays on the graphics card"}
    done = []
    for n in names:
        try:
            unload(n)
            done.append(n)
        except Exception:
            continue
    return {"unloaded": done}


def _audit(event: str, detail: dict) -> None:
    # Outcomes, modes and model names. Nothing the owner said.
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _is_cloud_model(name) -> bool:
    """jarvis_router.is_remote_model; without the router, any name with
    "cloud" in it counts - the safe side (jarvis_agent does the same)."""
    try:
        import jarvis_router
        return bool(jarvis_router.is_remote_model(str(name or "")))
    except Exception:
        return "cloud" in str(name or "").lower()


class EverydayOllama:
    """The everyday Ollama on THIS PC: what is loaded, unload one, load one.
    Every call is to loopback, through jarvis_local_http (no proxy), and
    sends only a model name. `url` is None when OLLAMA_URL is not this PC -
    then every call does nothing and says so."""

    LOOPBACK = ("127.0.0.1", "localhost", "::1")

    def __init__(self, url: Optional[str] = None):
        raw = url if url is not None else (os.environ.get("OLLAMA_URL")
                                           or "http://127.0.0.1:11434")
        raw = str(raw).strip().rstrip("/").replace("://0.0.0.0", "://127.0.0.1")
        if "://" not in raw:
            raw = "http://" + raw
        try:
            host = (urllib.parse.urlsplit(raw).hostname or "").lower()
        except ValueError:
            host = ""
        self.url = raw if host in self.LOOPBACK else None

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        import jarvis_local_http
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with jarvis_local_http.urlopen(req, timeout) as r:
            first = (r.read().decode("utf-8", "replace").strip().splitlines() or ["{}"])[0]
        return json.loads(first or "{}")

    def ps(self) -> Optional[list]:
        """Names of the models loaded now, or None when Ollama did not answer."""
        if self.url is None:
            return None
        try:
            import jarvis_local_http
            with jarvis_local_http.urlopen(urllib.request.Request(self.url + "/api/ps"), 3.0) as r:
                body = json.loads(r.read().decode("utf-8", "replace") or "{}")
        except Exception:
            return None
        out = []
        for m in (body or {}).get("models") or []:
            if isinstance(m, dict):
                name = str(m.get("name") or m.get("model") or "").strip()
                if name:
                    out.append(name)
        return out

    def unload(self, name: str) -> None:
        # Ollama's documented unload: no prompt, keep_alive 0.
        self._post("/api/generate", {"model": name, "keep_alive": 0}, 15.0)

    def load(self, name: str) -> None:
        # Ollama's documented preload: no prompt. keep_alive is left to
        # Ollama's own setting (OLLAMA_KEEP_ALIVE, -1 on the owner's PC).
        self._post("/api/generate", {"model": name}, 180.0)


def everyday_ollama() -> EverydayOllama:
    """The everyday Ollama. A function so the tests can put a fake here."""
    return EverydayOllama()


def _same(a: str, b: str) -> bool:
    def bare(x: str) -> str:
        x = str(x or "").strip()
        return x[:-7] if x.endswith(":latest") else x
    return bare(a) == bare(b)


def _unload_everyday(ollama=None, *, settle_s: float = 3.0,
                     sleep: Callable[[float], None] = time.sleep) -> dict:
    """Unload EVERY model the everyday Ollama still holds, then look again.
    {"unloaded": [...], "still": [...], "note": str}. Never raises."""
    try:
        o = ollama if ollama is not None else everyday_ollama()
    except Exception as exc:
        return {"unloaded": [], "still": [], "note": f"could not reach Ollama ({type(exc).__name__})"}
    if getattr(o, "url", "") is None:
        return {"unloaded": [], "still": [],
                "note": "OLLAMA_URL is not this PC, so nothing was asked there"}
    loaded = o.ps()
    if not loaded:
        # None: Ollama did not answer (not running - so it holds nothing).
        return {"unloaded": [], "still": [], "note": ""}
    done = []
    for name in loaded:
        try:
            o.unload(name)
            done.append(name)
        except Exception:
            continue
    still = list(loaded)
    waited = 0.0
    while True:
        now = o.ps()
        still = [] if now is None else [n for n in now if any(_same(n, m) for m in loaded)]
        if not still or waited >= settle_s:
            break
        sleep(0.25)
        waited += 0.25
    return {"unloaded": [n for n in done if n not in still], "still": still, "note": ""}


#: How the last warm-up went: {"state": "loading"|"ready"|"failed"|"skipped",
#: "model", "why", "at"}. In memory; the audit log has each one too.
WARM: dict = {}
_WARM_LOCK = threading.Lock()


def warm_status() -> dict:
    with _WARM_LOCK:
        return dict(WARM)


def chat_model() -> Optional[str]:
    """The everyday chat model's name, from the owner's jarvis_models (the
    same call the Models screen and jarvis_hardware make), else
    JARVIS_MODEL. None when neither says."""
    cur = None
    try:
        import jarvis_models
        cur = jarvis_models.current_model()
    except Exception:
        cur = None
    if isinstance(cur, dict):
        cur = cur.get("ref") or cur.get("name") or cur.get("model")
    if isinstance(cur, str) and cur.strip():
        return cur.strip()
    env = (os.environ.get("JARVIS_MODEL") or "").strip()
    return env or None


def warm_up(power=None, ollama=None, model: Optional[str] = None) -> dict:
    """Load the chat model now, so the first answer after waking is quick.
    Runs on its own thread (set_mode starts it). Never raises."""
    name = model if model is not None else chat_model()

    def done(state: str, why: str = "") -> dict:
        with _WARM_LOCK:
            WARM.clear()
            WARM.update(state=state, model=name or "", why=why, at=time.time())
        _audit("power.warm_up", {"state": state, "model": name or ""})
        return dict(WARM)

    if not name:
        return done("skipped", "Jarvis could not tell which model chat uses, so the first "
                               "answer will load it (5-15 seconds).")
    if _is_cloud_model(name):
        return done("skipped", f"\"{name}\" is one of Ollama's cloud models, which run on "
                               f"ollama.com, not on this PC - nothing was loaded.")
    try:
        o = ollama if ollama is not None else everyday_ollama()
    except Exception as exc:
        return done("failed", f"could not reach Ollama ({type(exc).__name__})")
    if getattr(o, "url", "") is None:
        return done("skipped", "OLLAMA_URL is not this PC, so nothing was loaded.")
    done("loading")
    try:
        o.load(name)
    except Exception as exc:
        return done("failed", f"Ollama did not load it ({type(exc).__name__}); the first "
                              f"answer will load it instead.")
    # Back on standby while it loaded: standby promised a free card.
    try:
        if power is None:
            import jarvis_power as power
        if str(power.current()) == "standby":
            try:
                o.unload(name)
            except Exception:
                pass
            return done("skipped", "Jarvis went back on standby while it loaded, so it "
                                   "was unloaded again.")
    except Exception:
        pass
    return done("ready")


def _spawn_warm(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-warm-up", daemon=True).start()


_PENDING_LOCK = threading.Lock()
#: The one power card that may be waiting: {"mode", "since"}, or None.
_PENDING: dict = {}


def _free_other_engines(others=None) -> list:
    """Standby frees the SECOND graphics card and the big model too, not only
    the everyday model - "frees its graphics cards" has to be true with two.
    `others` is for tests: a list of modules with sleep(why). Each answers one
    sentence (empty when there was nothing to say). Never raises."""
    if others is None:
        others = []
        # jarvis_voices: the better voice (F5-TTS) on the second card.
        for name in ("jarvis_second_card", "jarvis_big_model", "jarvis_voices"):
            try:
                others.append(__import__(name))
            except Exception:
                continue
    out = []
    for mod in others:
        try:
            said = (mod.sleep("Jarvis is on standby") or {}).get("sentence", "")
        except Exception as exc:
            said = f"Could not free {getattr(mod, '__name__', 'an engine')} ({type(exc).__name__})."
        if said:
            out.append(str(said))
    return out


def card_text(mode: str, current: str) -> str:
    return "\n".join([
        f"Switch Jarvis from {current} to {mode}.", "",
        _WORDS[mode], "",
        "Nothing leaves this PC. You can switch back at any time from either app.",
        "", "If you say no: Jarvis stays " + current + "."])


def set_mode(mode, *, by: str = "", gate_check: Optional[Callable] = None,
             power=None, models=None, wait_s: float = 1.5, others=None,
             ollama=None, warm: Optional[Callable[[Callable[[], None]], None]] = None,
             why: str = "") -> tuple:
    """Change the power mode through the gate. Returns (http_status, body).

    `ollama`: the everyday Ollama (everyday_ollama() when None). `warm`:
    how the warm-up is started (its own thread when None; the tests run it
    in place). `why`: what jarvis_power records as the reason - "the owner,
    from <by>" when empty; the standby schedule gives its own."""
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        return 400, {"ok": False, "error": f"mode must be one of {', '.join(MODES)}"}
    try:
        if power is None:
            import jarvis_power as power
        current = str(power.current())
    except Exception as exc:
        return 503, {"ok": False, "available": False,
                     "error": f"the power module is not available here ({type(exc).__name__})"}
    if mode == current:
        return 200, {"ok": True, "mode": mode, "changed": False,
                     "message": f"Already {mode}."}
    if mode == "standby" and _running_tasks():
        return 409, {"ok": False, "error": "a task is running - stop it first, or it would "
                                           "lose the model it is using"}
    with _PENDING_LOCK:
        if _PENDING:
            return 409, {"ok": False, "waiting": True,
                         "error": (f"a card to switch to {_PENDING['mode']} is already "
                                   f"waiting on your PC or phone - approve or deny that one "
                                   f"first")}
        _PENDING.update(mode=mode, since=time.time())

    box: dict = {}

    def work():
        try:
            decide()
        finally:
            with _PENDING_LOCK:
                _PENDING.clear()

    def decide():
        verdict = (gate_check or _gate_check)(
            "power_manage", {"text": card_text(mode, current)},
            f"power mode {current} -> {mode}, asked from {by or 'an app'}")
        if not getattr(verdict, "allowed", False):
            box["out"] = (200, {"ok": False, "mode": current, "changed": False,
                                "outcome": str(getattr(verdict, "outcome", "refused")),
                                "message": f"Not changed - Jarvis stays {current}."})
            return
        if mode == "standby" and _running_tasks():
            # Checked again: with the tier at "ask" the card may have waited
            # minutes, and a task that started meanwhile would lose its model.
            box["out"] = (409, {"ok": False, "mode": current, "changed": False,
                                "outcome": "refused",
                                "message": (f"Not changed - a task started while the card "
                                            f"waited, and standby would unload the model it "
                                            f"is using. Jarvis stays {current}; stop the task "
                                            f"first.")})
            return
        power.set_mode(mode, why=why or f"the owner, from {by or 'an app'}")
        out = {"ok": True, "mode": mode, "changed": True, "message": _WORDS[mode]}
        if current == "standby" and mode != "standby":
            # Waking: load the chat model again now, not at the first
            # question.
            name = chat_model()
            (warm or _spawn_warm)(lambda: warm_up(power, ollama, name) and None)
            if name and not _is_cloud_model(name):
                out["warm_up"] = name
                out["message"] += (f" Loading the chat model ({name}) again now, so the "
                                   f"first answer is quick.")
            else:
                out["message"] += (" The first answer will take 5-15 seconds while the chat "
                                   "model loads.")
            box["out"] = (200, out)
            return
        if mode != "standby":
            box["out"] = (200, out)
            return
        # The mode has changed and the `power` event is out. An app waiting
        # on this answer gets it now if freeing the cards takes longer.
        box["early"] = (200, dict(out, message=out["message"] + " Freeing the graphics "
                                                               "card now."))
        first = _unload_models(models)
        every = _unload_everyday(ollama)
        unloaded = list(first.get("unloaded") or [])
        for n in every["unloaded"]:
            if not any(_same(n, m) for m in unloaded):
                unloaded.append(n)
        # Said as unloaded only if Ollama no longer lists it.
        unloaded = [n for n in unloaded if not any(_same(n, x) for x in every["still"])]
        out["unloaded"] = unloaded
        if every["still"]:
            out["still_loaded"] = every["still"]
        notes = [x for x in (first.get("note"), every["note"]) if x]
        if notes and not unloaded:
            out["note"] = "; ".join(notes)
        also = []
        if every["still"]:
            also.append("Still loaded after asking Ollama to unload it: "
                        + ", ".join(every["still"]) + ".")
        also.extend(_free_other_engines(others))
        if also:
            out["also"] = also
            out["message"] = " ".join([out["message"]] + also)
        _audit("power.standby", {"unloaded": unloaded, "still": every["still"],
                                 "by": by or "an app"})
        box["out"] = (200, out)

    t = threading.Thread(target=work, name="jarvis-power-switch", daemon=True)
    try:
        t.start()
    except Exception:
        with _PENDING_LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    t.join(max(0.0, float(wait_s)))
    if "out" in box:
        return box["out"]
    if "early" in box:
        return box["early"]
    return 202, {"ok": True, "mode": current, "changed": False, "waiting": True,
                 "message": "Waiting for your approval on your PC or phone. The mode "
                            "changes only if you approve it."}


def handle_post(body, *, by: str = "") -> tuple:
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "need a JSON object"}
    return set_mode(body.get("mode"), by=by)
