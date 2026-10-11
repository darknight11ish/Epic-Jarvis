"""jarvis_big_coder.py - the 30B coder: both cards, with Jarvis paused.

WHAT THIS IS, AND WHY IT EXISTS

One model the owner measured and asked for by name:
`qwen3-coder-30b-a3b-ud-q3-k-xl` (13,806,312,608 B, UD-Q3_K_XL, Apache 2.0). It
is the best coder and the fastest writer ever measured on this PC - 10/10 on
the project's coding test, ~101 / 76.5 / 76.3 tokens a second on the three
bench prompts, and no thinking mode to default on and return an empty answer.
Its cost is the whole reason it is a MODE and not a model: its GPU-resident
footprint at the smallest context tested is 14,813 MiB against a 12,288 MiB
card and an 8,192 MiB card, so it needs BOTH cards and cannot sit beside
anything. Measured for it: 49/49 layers across both cards and zero spill at
28,672 tokens, with the 2060 at 12,052 of its 12,288 MiB - the ceiling
(`.dsh-scratch/android-verify/BIG-MODELS-2026-10-10.md`, sections 6b, 6c, 12).

THE OWNER'S DECISION, WHICH THIS FILE IMPLEMENTS AND DOES NOT RE-LITIGATE

  1. It is OFF by default. Nothing loads and nothing downloads until the owner
     turns the switch on AND asks for the mode.
  2. It is NEVER resident beside the two live lanes. The two lanes are paused
     (both models unloaded, proved from /api/ps) BEFORE it is loaded, and if a
     lane will not go, the mode refuses and loads NOTHING.
  3. The pause is announced BEFORE it starts - the card the owner sees names
     both lanes, their models and their contexts, and the sentence goes out
     before the first unload.
  4. When the mode ends, the two lanes come back EXACTLY as they were:
     11436 qwen3.5:9b at 196608 on the RTX 2060, and 11435 qwen3:8b at 16384
     on the RTX 2080 SUPER. That is PROVED from /api/ps - model, context and
     zero spill - and a lane that does not come back is reported as a failure
     rather than glossed over.

REUSE, NOT A SECOND SUPERVISOR

`jarvis_power_switch.py` already knows how to unload a lane, load a model and
prove it from /api/ps, and how to preload one at the lane's own context instead
of Ollama's small default. None of that is re-invented here. The one thing this
mode needs that nothing else does is a server that can SEE both cards: the two
lane servers are pinned, one card each, so the model cannot be loaded on either
of them without spilling. This file starts ONE `ollama serve` for the mode,
with no `CUDA_VISIBLE_DEVICES` (both cards) and `OLLAMA_VULKAN=0` (without
which CUDA_VISIBLE_DEVICES silently falls back to Vulkan onto the other card -
`jarvis_picture_card.py` records that trap), on its own port, and stops it when
the mode ends. It never touches the lane servers, which are the owner's.

WHAT IS GATED (rule 4)

  * Turning the switch ON is ONE approval card, action `change_own_config`,
    tier "ask" - the same shape `jarvis_backup.py` and `jarvis_big_model.py`
    use for an opt-in setting. Turning it OFF is immediate.
  * Pausing the lanes and loading the model goes through `power_manage`, the
    action that already governs what is on the graphics cards (standby frees
    them). The owner's shipped tier is "auto"; set it to "ask" and a card
    appears, exactly as for standby.

REFUSED, WITH THE REASON, NEVER SILENTLY

  * the switch is off;
  * a multi-step task is running (pausing the lanes under it would break it);
  * a lane is still resident after being asked to unload - the mode will not
    run beside it, and nothing is loaded;
  * the model loads with any spill (`size_vram < size`) or at the wrong
    context - it is unloaded again and the lanes are restored;
  * a lane does not come back exactly as it was - said plainly, with what
    /api/ps shows instead.

NOTHING HERE DOWNLOADS ANYTHING, and nothing leaves this PC: every call is to
loopback through `jarvis_local_http`, and only model names and numbers are
sent.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from typing import Callable, NamedTuple, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

#: The model, the tag it is imported under, and the file it came from.
MODEL = "qwen3-coder-30b-a3b-ud-q3-k-xl"
MODEL_BYTES = 13806312608
MODEL_SHA256 = "69cd7578d77dffc0b17e34bad9ef998d08ae0e20ccceef21bad4e7eb3d8c553b"

#: The largest context measured to load with ZERO spill across both cards
#: (BIG-MODELS section 6c). 32,768 is the first rung that spills, by 0.20 GB.
NUM_CTX = 28672

#: Both cards, never one: the measured ceiling for one card is "no context
#: fits, not even the smallest".
BIG_PORT = 11450

#: The opt-in switch, and the two gate actions this mode uses. Both already
#: exist in jarvis_gate/jarvis_asks_first, so this feature invents no new
#: action for the owner's "What asks first" page to describe.
ACTION_ON = "change_own_config"
ACTION_POWER = "power_manage"

SWITCH_FILE = "big-coder.json"
SETTLE_S = 6.0
STATE: dict = {}
_STATE_LOCK = threading.Lock()


class Lane(NamedTuple):
    port: int
    model: str
    ctx: int
    card: str
    uuid: str
    why: str


#: The owner's two live lanes, exactly as they must come back. The order is
#: the order they are paused and restored in.
LANES = (
    Lane(11436, "qwen3.5:9b", 196608, "RTX 2060",
         "GPU-1ba04124-85de-3b44-bacc-7b7d9f0d8bee", "the everyday lane"),
    Lane(11435, "qwen3:8b", 16384, "RTX 2080 SUPER",
         "GPU-e4283ff2-b412-4e8c-9bae-7e433139e7d6", "the second lane"),
)


def _bare(name) -> str:
    """A model name without a ":latest" Ollama adds for itself."""
    x = str(name or "").strip()
    return x[:-7] if x.endswith(":latest") else x


def _same(a, b) -> bool:
    return _bare(a) == _bare(b)


def _url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}"


# --------------------------------------------------------------------------
#   This PC only: the config folder, the audit log, the event bus
# --------------------------------------------------------------------------


def config_dir():
    """The folder the owner's small settings files live in - the same one
    `jarvis_thinking.py` uses, so a backup of one folder keeps them all."""
    try:
        if fw is not None:
            return fw.CONFIG_DIR
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return os.path.expanduser(env)
    return os.path.join(os.path.expanduser("~"), ".openjarvis")


def switch_path() -> str:
    return os.path.join(str(config_dir()), SWITCH_FILE)


def _read_switch() -> dict:
    try:
        with open(switch_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_switch(data: dict) -> Optional[str]:
    try:
        p = switch_path()
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        os.replace(tmp, p)
    except OSError as exc:
        return f"could not save the switch ({type(exc).__name__})"
    return None


def enabled() -> bool:
    """The owner's opt-in switch. OFF unless the file says otherwise - a
    missing, empty or damaged file is off, never on."""
    return bool(_read_switch().get("on") is True)


def _audit(event: str, detail: dict) -> None:
    try:
        if fw is not None:
            fw.audit_log(event, detail)
    except Exception:
        pass


def _publish(kind: str, data: dict) -> None:
    try:
        import jarvis_events
        jarvis_events.BUS.publish(kind, data)
    except Exception:
        pass


def _gate(action: str, detail: dict, prompt: str):
    """jarvis_gate.check(), failing CLOSED on any error - the same shape
    jarvis_power_switch uses."""
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


# --------------------------------------------------------------------------
#   Loopback HTTP - a thin layer, so the whole world can be faked in a suite
# --------------------------------------------------------------------------


def _urlopen(req, timeout: float):
    import jarvis_local_http
    return jarvis_local_http.urlopen(req, timeout)


def _get_json(url: str, path: str, timeout: float = 4.0) -> Optional[dict]:
    """GET `path` on `url`, or None when it did not answer. Never raises."""
    try:
        req = urllib.request.Request(url + path, method="GET")
        with _urlopen(req, timeout) as r:
            body = r.read().decode("utf-8", "replace")
        out = json.loads(body or "{}")
        return out if isinstance(out, dict) else {}
    except Exception:
        return None


def _post_json(url: str, path: str, body: dict, timeout: float) -> Optional[dict]:
    """POST `body` to `path` on `url`, or None when it did not answer. A
    streamed reply (one JSON object per line) gives its first line."""
    try:
        req = urllib.request.Request(
            url + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with _urlopen(req, timeout) as r:
            raw = r.read().decode("utf-8", "replace").strip()
        try:
            out = json.loads(raw or "{}")
        except ValueError:
            out = json.loads((raw.splitlines() or ["{}"])[0] or "{}")
        return out if isinstance(out, dict) else {}
    except Exception:
        return None


def ps(url: str) -> Optional[list]:
    """What is loaded on `url` right now, as rows carrying at least
    `name`, `size`, `size_vram` and `context_length`. None when the server did
    not answer (which is not the same as "nothing is loaded"), [] when it
    answered and holds nothing."""
    body = _get_json(url, "/api/ps", 4.0)
    if body is None:
        return None
    out = []
    for m in (body.get("models") or []):
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or m.get("model") or "").strip()
        if name:
            out.append({"name": name,
                        "context_length": m.get("context_length"),
                        "size": m.get("size"),
                        "size_vram": m.get("size_vram")})
    return out


def _row_for(rows, model) -> Optional[dict]:
    for r in (rows or []):
        if _same(r.get("name"), model):
            return r
    return None


def _spill(row: dict) -> Optional[int]:
    """Bytes NOT in video memory, or None when the server did not say."""
    try:
        return int(row.get("size") or 0) - int(row.get("size_vram") or 0)
    except (TypeError, ValueError):
        return None


def known_on(url: str) -> Optional[bool]:
    """Is `model` imported on this server at all? None when it did not answer.
    Read-only: POST /api/show reads the model's own metadata and loads
    nothing."""
    body = _post_json(url, "/api/show", {"model": MODEL}, 8.0)
    if body is None:
        return None
    return bool(body)


def unload(url: str, model: str) -> bool:
    """Ollama's documented unload: a load with no prompt and keep_alive 0.
    Unloading needs no context - it loads nothing."""
    return _post_json(url, "/api/generate", {"model": model, "keep_alive": 0},
                      20.0) is not None


def load(url: str, model: str, num_ctx: int) -> bool:
    """Load `model` now, NAMING the context. A load that names no context
    loads at Ollama's own small default instead of the lane's setting, which
    is the trap jarvis_power_switch.py documents at length; so there is no
    code path here that omits it."""
    return _post_json(url, "/api/generate",
                      {"model": model, "options": {"num_ctx": int(num_ctx)}},
                      240.0) is not None


def _settle(url: str, model: str, *, gone: bool, settle_s: float = SETTLE_S,
            sleep: Callable[[float], None] = time.sleep) -> Optional[list]:
    """Poll /api/ps until `model` is gone (gone=True) or present (False), or
    the settle time runs out. Returns the last rows read."""
    waited = 0.0
    rows = ps(url)
    while True:
        here = _row_for(rows, model) is not None
        if rows is None or here != (not gone):
            return rows
        if waited >= settle_s:
            return rows
        sleep(0.25)
        waited += 0.25
        rows = ps(url)


# --------------------------------------------------------------------------
#   The one server this mode needs: both cards, its own port
# --------------------------------------------------------------------------

_SERVER: dict = {}
_SERVER_LOCK = threading.Lock()


def _child_env(port: int) -> dict:
    """What the mode's own `ollama serve` inherits. Windows needs its own
    variables and the model folder, so they come from jarvis_child_env (the
    same helper the second Ollama uses). `CUDA_VISIBLE_DEVICES` is REMOVED on
    purpose - leaving it unset is what lets Ollama see both cards - and
    `OLLAMA_VULKAN=0` is set, without which that unset variable silently falls
    back to Vulkan onto one card (jarvis_picture_card.py records the trap)."""
    base = dict(os.environ)
    try:
        import jarvis_child_env
        env = jarvis_child_env.inherited(base, names=("OLLAMA_MODELS",))
    except Exception:
        env = base
    env.pop("CUDA_VISIBLE_DEVICES", None)
    env["OLLAMA_VULKAN"] = "0"
    env["OLLAMA_HOST"] = f"127.0.0.1:{int(port)}"
    env["OLLAMA_NO_CLOUD"] = "1"
    return env


def server_start(port: int = BIG_PORT) -> dict:
    """Start the mode's own Ollama, or reuse one already answering there.
    {"ok", "url", "owned", "why"}. Never raises. The lane servers are not
    touched: this is a different port and a different process."""
    url = _url(port)
    if ps(url) is not None:
        return {"ok": True, "url": url, "owned": False,
                "why": f"a server was already answering on port {port}, so it was used as it is"}
    env = _child_env(port)
    try:
        proc = subprocess.Popen(["ollama", "serve"], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        return {"ok": False, "url": url, "owned": False,
                "why": f"could not start the both-cards Ollama ({type(exc).__name__})"}
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if ps(url) is not None:
            with _SERVER_LOCK:
                _SERVER.clear()
                _SERVER.update(proc=proc, url=url, port=int(port))
            return {"ok": True, "url": url, "owned": True, "why": ""}
        if proc.poll() is not None:
            return {"ok": False, "url": url, "owned": False,
                    "why": "the both-cards Ollama stopped as soon as it started"}
        time.sleep(0.5)
    try:
        proc.terminate()
    except Exception:
        pass
    return {"ok": False, "url": url, "owned": False,
            "why": "the both-cards Ollama did not answer within 30 seconds"}


def server_stop() -> dict:
    """Stop the server this mode started. A server it did not start (one
    already answering on the port) is left alone."""
    with _SERVER_LOCK:
        held = dict(_SERVER)
        _SERVER.clear()
    proc = held.get("proc")
    if proc is None:
        return {"stopped": False, "why": "this mode had not started a server"}
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    except Exception as exc:
        return {"stopped": False, "why": f"could not stop it ({type(exc).__name__})"}
    return {"stopped": True, "why": ""}


# --------------------------------------------------------------------------
#   The words the owner reads
# --------------------------------------------------------------------------


def lane_lines() -> list:
    return [f"{lane.model} at {lane.ctx:,} tokens on the {lane.card} (port {lane.port})"
            for lane in LANES]


def card_text_start() -> str:
    return "\n".join([
        "Use the big coding model: qwen3-coder-30b-a3b-ud-q3-k-xl.",
        "",
        "It needs BOTH graphics cards, so the two models running now are paused "
        "first, and they are put back exactly as they are when you stop:",
        "",
        *[f"  - pausing {line}" for line in lane_lines()],
        "",
        f"It loads at {NUM_CTX:,} tokens - the largest measured to fit both cards "
        f"with no spill - and it stays until you stop it.",
        "Nothing else changes, nothing leaves this PC, and nothing is downloaded.",
    ])


def card_text_off() -> str:
    return ("Turn the big coding model on as a choice you can use. It is OFF until you "
            "start it, it needs both graphics cards, and it pauses the two running "
            "models while it is on. Nothing loads until you start it.")


def _announce(words: str) -> None:
    """The pause, said BEFORE anything is touched: on the event bus and in the
    audit log, which is the record the apps read."""
    _publish("big-coder", {"state": "pausing", "words": words})
    _audit("big_coder.pausing", {"words": words})


# --------------------------------------------------------------------------
#   The pause, the load, the restore - each proved from /api/ps
# --------------------------------------------------------------------------


def pause_lanes(*, url_for: Callable[[int], str] = _url) -> dict:
    """Unload both lane models and prove from /api/ps that they are gone.
    {"ok", "why", "unloaded", "still", "proof"}. Never raises.

    `ok` is False when ANY lane is still resident: the mode must not run beside
    a lane, so the caller refuses and puts back what this took."""
    unloaded, still, proof = [], [], []
    for lane in LANES:
        url = url_for(lane.port)
        before = ps(url)
        if before is None:
            still.append(f"{lane.model} on port {lane.port} (the lane did not answer)")
            proof.append(f"port {lane.port}: no answer, so it is NOT proved paused")
            continue
        if _row_for(before, lane.model) is not None:
            unload(url, lane.model)
            rows = _settle(url, lane.model, gone=True)
            if rows is not None and _row_for(rows, lane.model) is not None:
                still.append(f"{lane.model} on port {lane.port}")
                proof.append(f"port {lane.port}: {lane.model} is STILL loaded after "
                             f"being asked to unload")
                continue
            unloaded.append(f"{lane.model} @{lane.port}")
        proof.append(f"port {lane.port}: {lane.model} is not loaded - the lane is paused")
    why = ""
    if still:
        why = ("Jarvis did not pause every model it must, so the big coding model was NOT "
               "started: still loaded - " + "; ".join(still)
               + ". Nothing was loaded, and what was unloaded is being put back.")
    return {"ok": not still, "why": why, "unloaded": unloaded, "still": still,
            "proof": proof}


def load_coder(*, url_for: Callable[[int], str] = _url, port: int = BIG_PORT) -> dict:
    """Load the 30B on the both-cards server and prove from /api/ps that it
    fits: present, at NUM_CTX, and with ZERO spill. On anything else it is
    unloaded again and `ok` is False."""
    url = url_for(port)
    if not load(url, MODEL, NUM_CTX):
        return {"ok": False, "why": f"the both-cards Ollama on port {port} did not load "
                                    f"{MODEL}", "proof": []}
    rows = _settle(url, MODEL, gone=False)
    row = _row_for(rows, MODEL)
    if row is None:
        return {"ok": False, "why": f"{MODEL} is not in /api/ps after loading it",
                "proof": []}
    spill = _spill(row)
    ctx = row.get("context_length")
    proof = [f"port {port}: {MODEL} ctx={ctx} size={row.get('size')} "
             f"size_vram={row.get('size_vram')} spill={spill}"]
    if spill is None or spill > 0:
        unload(url, MODEL)
        return {"ok": False,
                "why": (f"{MODEL} loaded with spill ({spill} B not in video memory) - it "
                        f"needs both cards and this machine could not give it both, so it "
                        f"was unloaded again"),
                "proof": proof}
    try:
        if ctx is not None and int(ctx) != NUM_CTX:
            unload(url, MODEL)
            return {"ok": False,
                    "why": (f"{MODEL} loaded at {ctx} tokens, not the measured "
                            f"{NUM_CTX} - it was unloaded again"),
                    "proof": proof}
    except (TypeError, ValueError):
        pass
    return {"ok": True, "why": "", "proof": proof, "row": row}


def unload_coder(*, url_for: Callable[[int], str] = _url, port: int = BIG_PORT) -> dict:
    """Unload the 30B and prove it is gone. {"ok", "why", "proof"}."""
    url = url_for(port)
    unload(url, MODEL)
    rows = _settle(url, MODEL, gone=True)
    if rows is None:
        return {"ok": True, "why": "the server had already stopped, so nothing is loaded",
                "proof": [f"port {port}: no answer, so nothing is resident"]}
    if _row_for(rows, MODEL) is not None:
        return {"ok": False, "why": f"{MODEL} is STILL loaded after being asked to unload",
                "proof": [f"port {port}: {MODEL} is still in /api/ps"]}
    return {"ok": True, "why": "", "proof": [f"port {port}: {MODEL} is not loaded"]}


def restore_lanes(*, url_for: Callable[[int], str] = _url) -> dict:
    """Put both lanes back EXACTLY as they were and prove it from /api/ps:
    the right model per lane, at the right context, with zero spill.

    {"ok", "why", "proof", "wrong"}. Never raises. A lane that does not come
    back is named, and `ok` is False - the caller says so rather than claiming
    a restore it has not shown."""
    proof, wrong = [], []
    for lane in LANES:
        url = url_for(lane.port)
        load(url, lane.model, lane.ctx)
        rows = _settle(url, lane.model, gone=False)
        row = _row_for(rows, lane.model)
        if row is None:
            wrong.append(f"{lane.model} is not loaded on port {lane.port}")
            proof.append(f"port {lane.port}: {lane.model} did NOT come back")
            continue
        try:
            ctx = int(row.get("context_length"))
        except (TypeError, ValueError):
            ctx = None
        spill = _spill(row)
        proof.append(f"port {lane.port}: {lane.model} ctx={row.get('context_length')} "
                     f"(intended {lane.ctx}) size={row.get('size')} "
                     f"size_vram={row.get('size_vram')} spill={spill}")
        if ctx is not None and ctx != lane.ctx:
            wrong.append(f"{lane.model} came back at {ctx}, not {lane.ctx}, on port "
                         f"{lane.port}")
        if spill is None or spill > 0:
            wrong.append(f"{lane.model} came back with spill ({spill} B) on port "
                         f"{lane.port}")
    why = ""
    if wrong:
        why = ("The two models were not put back exactly as they were: "
               + "; ".join(wrong) + ". Start them from the Power screen, or restart Jarvis.")
    return {"ok": not wrong, "why": why, "proof": proof, "wrong": wrong}


# --------------------------------------------------------------------------
#   State, the mode itself, and the answers the apps read
# --------------------------------------------------------------------------


def running() -> bool:
    """Is the mode on NOW? Evidence first: the model in /api/ps on the
    both-cards server. Only when that server does not answer does the
    in-memory record decide - and a server that does not answer holds
    nothing."""
    rows = ps(_url(BIG_PORT))
    if rows is not None:
        return _row_for(rows, MODEL) is not None
    with _STATE_LOCK:
        return bool(STATE.get("running"))


def state() -> dict:
    with _STATE_LOCK:
        return dict(STATE)


def _set_state(**kw) -> None:
    with _STATE_LOCK:
        STATE.clear()
        STATE.update(kw)


def status() -> dict:
    """GET /api/big-coder - read-only, and it changes nothing at all. It says
    what the switch is, what is loaded where right now, and what a start would
    touch."""
    big = _url(BIG_PORT)
    big_rows = ps(big)
    lanes = []
    for lane in LANES:
        rows = ps(_url(lane.port))
        lanes.append({"port": lane.port, "model": lane.model, "ctx": lane.ctx,
                      "card": lane.card, "why": lane.why,
                      "loaded": [r["name"] for r in rows] if rows is not None else None,
                      "ctx_now": (rows[0].get("context_length") if rows else None)})
    return {
        "available": True,
        "model": MODEL,
        "model_bytes": MODEL_BYTES,
        "model_sha256": MODEL_SHA256,
        "num_ctx": NUM_CTX,
        "on": enabled(),
        "running": running(),
        "state": state(),
        "big_lane": {
            "port": BIG_PORT,
            "answering": big_rows is not None,
            "knows_the_model": known_on(big),
            "loaded": [r["name"] for r in (big_rows or [])],
        },
        "lanes": lanes,
        "words": card_text_start(),
        "off_words": card_text_off(),
        "what_a_start_would_do": [
            f"pause {lane.model} on port {lane.port}" for lane in LANES
        ] + [f"load {MODEL} at {NUM_CTX:,} tokens on both cards (port {BIG_PORT})"],
        "measured": ("10/10 on the project's coding test; about 101 / 76.5 / 76.3 tokens a "
                     "second on the three bench prompts; 28,672 tokens with zero spill; no "
                     "thinking mode to return an empty answer"),
    }


def set_enabled(on, *, by: str = "", gate_check: Optional[Callable] = None) -> tuple:
    """Turn the opt-in switch on or off. ON is ONE approval card, action
    `change_own_config` (tier "ask" as shipped); OFF is immediate. Returns
    (http status, body)."""
    want = bool(on)
    if want == enabled():
        return 200, {"ok": True, "on": want, "changed": False,
                     "message": f"The big coding model is already {'on' if want else 'off'}."}
    if want:
        verdict = (gate_check or _gate)(
            ACTION_ON, {"text": card_text_off()},
            f"turn ON the big coding model ({MODEL}), asked from {by or 'an app'}")
        if not getattr(verdict, "allowed", False):
            return 200, {"ok": False, "on": False, "changed": False,
                         "outcome": str(getattr(verdict, "outcome", "refused")),
                         "message": "Not turned on - the big coding model stays off."}
    data = _read_switch()
    data["on"] = want
    problem = _write_switch(data)
    if problem:
        return 503, {"ok": False, "on": enabled(), "changed": False, "error": problem}
    _audit("big_coder.switch", {"on": want, "by": by or "an app"})
    return 200, {"ok": True, "on": want, "changed": True,
                 "message": (card_text_off() if want else
                             "The big coding model is off. It will not be started.")}


def start(*, by: str = "", gate_check: Optional[Callable] = None,
          tasks: Optional[Callable] = None,
          url_for: Callable[[int], str] = _url,
          start_server: Optional[Callable] = None) -> tuple:
    """Start the mode: announce, pause both lanes, load the 30B on both cards.

    The order is the contract, and it is why this function is one function:
    the announcement goes out BEFORE the first unload, both lanes are proved
    paused before anything is loaded, and ANY failure puts back what was taken
    and loads nothing. Returns (http status, body)."""
    if not enabled():
        return 409, {"ok": False, "running": False,
                     "error": ("the big coding model is switched off - turn it on in "
                               "Settings first, or ask Jarvis to")}
    if running():
        return 200, {"ok": True, "running": True, "changed": False,
                     "message": "The big coding model is already running."}
    live = (tasks or _running_tasks)()
    if live:
        return 409, {"ok": False, "running": False,
                     "error": ("a task is running - stop it first, or pausing the two models "
                               "would break it")}
    words = card_text_start()
    verdict = (gate_check or _gate)(
        ACTION_POWER, {"text": words},
        f"pause both model lanes and load {MODEL}, asked from {by or 'an app'}")
    if not getattr(verdict, "allowed", False):
        return 200, {"ok": False, "running": False, "changed": False,
                     "outcome": str(getattr(verdict, "outcome", "refused")),
                     "message": "Not started - nothing was paused and nothing was loaded."}
    # THE ANNOUNCEMENT, before anything on either card is touched.
    _announce(words)
    srv = (start_server or server_start)()
    if not srv.get("ok"):
        return 503, {"ok": False, "running": False, "error": srv.get("why") or
                                                          "could not start the both-cards Ollama"}
    paused = pause_lanes(url_for=url_for)
    if not paused["ok"]:
        restore_lanes(url_for=url_for)
        server_stop()
        return 409, {"ok": False, "running": False, "error": paused["why"],
                     "paused": paused["proof"]}
    loaded = load_coder(url_for=url_for, port=_port_of(srv.get("url")))
    if not loaded["ok"]:
        unload_coder(url_for=url_for, port=_port_of(srv.get("url")))
        back = restore_lanes(url_for=url_for)
        server_stop()
        out = {"ok": False, "running": False, "error": loaded["why"],
               "proof": loaded["proof"], "restored": back["proof"]}
        if not back["ok"]:
            out["error"] = out["error"] + " " + back["why"]
        return 503, out
    _set_state(running=True, since=time.time(), by=by or "an app",
               proof=list(paused["proof"]) + list(loaded["proof"]))
    _publish("big-coder", {"state": "running", "model": MODEL, "ctx": NUM_CTX})
    _audit("big_coder.start", {"model": MODEL, "ctx": NUM_CTX, "by": by or "an app"})
    return 200, {"ok": True, "running": True, "changed": True, "model": MODEL,
                 "num_ctx": NUM_CTX,
                 "message": (f"The big coding model is running on both cards at {NUM_CTX:,} "
                             f"tokens. The two models are paused and come back when you "
                             f"stop it."),
                 "paused": paused["proof"], "proof": loaded["proof"]}


def stop(*, by: str = "", url_for: Callable[[int], str] = _url) -> tuple:
    """Stop the mode: unload the 30B, stop the server this mode started, and
    put both lanes back exactly as they were - proved from /api/ps. Returns
    (http status, body)."""
    if not running() and not state().get("running"):
        back = restore_lanes(url_for=url_for)
        return 200, {"ok": back["ok"], "running": False, "changed": False,
                     "message": "The big coding model is not running.",
                     "restored": back["proof"],
                     **({"error": back["why"]} if not back["ok"] else {})}
    gone = unload_coder(url_for=url_for)
    server_stop()
    back = restore_lanes(url_for=url_for)
    _set_state(running=False, since=None, proof=back["proof"])
    _publish("big-coder", {"state": "stopped"})
    _audit("big_coder.stop", {"restored": back["ok"], "by": by or "an app"})
    if not gone["ok"] or not back["ok"]:
        error = "; ".join(x for x in (gone["why"], back["why"]) if x)
        return 503, {"ok": False, "running": False, "changed": True, "error": error,
                     "unloaded": gone["proof"], "restored": back["proof"]}
    return 200, {"ok": True, "running": False, "changed": True,
                 "message": ("The big coding model is stopped and the two models are back: "
                             + "; ".join(lane_lines())),
                 "unloaded": gone["proof"], "restored": back["proof"]}


def _port_of(url: Optional[str]) -> int:
    try:
        tail = str(url or "").rstrip("/").rsplit(":", 1)[-1]
        return int(tail)
    except (TypeError, ValueError):
        return BIG_PORT


def handle_get() -> tuple:
    return 200, status()


def handle_post(body, *, by: str = "") -> tuple:
    """The one POST: {"on": bool} sets the switch; {"action": "start"|"stop"}
    runs the mode. Anything else is a 400, so a caller with a bug finds out."""
    if not isinstance(body, dict):
        return 400, {"error": "send a JSON object"}
    if "on" in body:
        return set_enabled(body.get("on"), by=by)
    action = str(body.get("action") or "").strip().lower()
    if action == "start":
        return start(by=by)
    if action == "stop":
        return stop(by=by)
    return 400, {"error": "send {\"on\": true|false} or {\"action\": \"start\"|\"stop\"}"}
