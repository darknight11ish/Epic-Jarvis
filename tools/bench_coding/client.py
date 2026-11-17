"""Talk to the live Jarvis the way a client does - and read what it says.

WHAT THIS MODULE OWNS. One `JarvisClient` around the live backend at
`http://127.0.0.1:4719`: the pairing token read from the live folder's own
`jarvis_token_store.py` (never printed, never written), one `POST /api/chat`
with a hard wall-clock deadline, and the read-only GETs the benchmark needs
(`/api/status`, `/api/version`, `/api/work`, `/api/models/resources`,
`/api/pending`).

WHAT IT DOES NOT OWN. There is deliberately no `approve` call in this file.
The benchmark never says yes to a card on the owner's behalf. It DOES decline
a card that appears during one of its own turns: a NO executes nothing and
creates no permission, and without it a tool call the model makes would hold
the turn for the card's whole lifetime, so the benchmark would measure the
approval timeout instead of the answer. The card id, action and decline are
recorded in the result. That is the same line the project draws between a yes
and a no; only the yes needs a person.

THE ROUTE. `POST /api/chat` answers with an `X-Jarvis-Route` response header
whose body is JSON. `jarvis_hud.py` builds it from the router's own
`Decision.as_dict()` - `lane`, `reason`, `gate`, `complexity`,
`inject_memory`, `tainted`, `offer`, `auto` - and then adds `turn_id`,
`where`, `memory_side`, `injected_facts`, `injected_ids`, `temporary` and the
other per-turn fields. This module reads that header and keeps it verbatim,
because it is the product's own statement of which lane answered and why.

THE TOKEN. `jarvis_token_store.py show` is the supported read; the output is
held in memory only. `scrub()` is applied to every string this module hands
back, so a token accidentally echoed in an answer can never reach a report,
a JSON file or a terminal line.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#: The live backend on this PC, as every app reaches it.
DEFAULT_BASE_URL = "http://127.0.0.1:4719"

#: Where the live install lives when nothing names it. Last resort only.
FALLBACK_LIVE = Path(
    r"C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"
)

#: The typed provenance the HUD sends for a question the owner typed.
PROVENANCE = "typed"

#: What the benchmark says when it declines a card its own turn raised. The
#: deny path executes nothing; it only stops the turn waiting for a person.
DECLINE_NOTE = (
    "Declined by tools/bench_coding: this card was raised while a benchmark "
    "test was running. Nothing is executed, and the denial is recorded in the "
    "run's result. The benchmark never approves a card."
)


class Blocked(Exception):
    """The benchmark cannot measure this run; the sentence says exactly why."""


def one_line(text: object, limit: int = 300) -> str:
    """One bounded line, for a sentence or a table cell."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 3)] + "..."


def scrub(text: object, secret: str = "") -> str:
    """The text with the pairing token removed, if one found its way in."""
    value = str(text or "")
    if secret:
        value = value.replace(secret, "<redacted>")
    return value


def find_live_backend(explicit: str = "") -> Path:
    """The live install's folder, or a Blocked sentence.

    `--live-backend`, then `JARVIS_BACKEND`, then the same value as Windows
    stores it at USER level (a PowerShell session that clears
    `$env:JARVIS_BACKEND` must not stop the harness from finding the token),
    then the known install path. It is never guessed from the checkout.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("JARVIS_BACKEND", "").strip()
    if env:
        candidates.append(Path(env))
    if os.name == "nt":
        try:
            import winreg  # noqa: PLC0415 - Windows only

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _kind = winreg.QueryValueEx(key, "JARVIS_BACKEND")
            if str(value or "").strip():
                candidates.append(Path(str(value)))
        except OSError:
            pass
    candidates.append(FALLBACK_LIVE)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if (resolved / "jarvis_token_store.py").is_file():
            return resolved
    raise Blocked(
        "the live backend folder was not found - pass --live-backend <the folder "
        "holding jarvis_token_store.py>"
    )


def read_token(live: Path) -> str:
    """The pairing token, read through the live folder's own token store.

    The ONLY supported read: `jarvis_token_store.py show`. The value is
    returned to the caller and never printed here. A missing store, a refused
    read or an empty value is a Blocked sentence, never a guess.
    """
    store = live / "jarvis_token_store.py"
    if not store.is_file():
        raise Blocked(f"the live folder has no jarvis_token_store.py: {live}")
    py = shutil.which("py")
    argv = [py, "-3", str(store), "show"] if py else [sys.executable, str(store), "show"]
    try:
        done = subprocess.run(
            argv, cwd=str(live), capture_output=True, text=True, timeout=60
        )
    except Exception as exc:  # noqa: BLE001 - a sentence, not a traceback
        raise Blocked(f"the token store could not be run ({type(exc).__name__})") from None
    token = (done.stdout or "").strip()
    if done.returncode != 0 or not token:
        detail = one_line(done.stderr or "", 160)
        raise Blocked(
            "the token store returned no pairing token"
            + (f": {detail}" if detail else "")
        )
    if len(token) < 16 or any(ch.isspace() for ch in token):
        raise Blocked("the token store returned something that is not a pairing token")
    return token


class _Headers(dict):
    """A case-insensitive view of the response headers."""

    def __init__(self, pairs):
        super().__init__()
        self._lower = {}
        for key, value in pairs or []:
            self[key] = value
            self._lower[str(key).lower()] = value

    def get_ci(self, name: str, default=None):
        return self._lower.get(name.lower(), default)


class Reply:
    """One `POST /api/chat` answer, with everything measurable about it."""

    def __init__(self, **kw):
        self.status: int = int(kw.get("status") or 0)
        self.answer: str = str(kw.get("answer") or "")
        self.route: dict = dict(kw.get("route") or {})
        self.route_raw: str = str(kw.get("route_raw") or "")
        self.error: str = str(kw.get("error") or "")
        self.seconds: float = float(kw.get("seconds") or 0.0)
        self.timed_out: bool = bool(kw.get("timed_out"))
        self.attempts: int = int(kw.get("attempts") or 1)
        self.declined: list = list(kw.get("declined") or [])

    def as_dict(self, secret: str = "") -> dict:
        return {
            "status": self.status,
            "answer": scrub(self.answer, secret),
            "route": json.loads(scrub(json.dumps(self.route), secret)),
            "route_raw": scrub(self.route_raw, secret),
            "error": scrub(self.error, secret),
            "seconds": self.seconds,
            "timed_out": self.timed_out,
            "attempts": self.attempts,
            "declined": self.declined,
        }


class JarvisClient:
    """The live backend, read and asked, with a hard wall-clock deadline."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, live: Path | None = None,
                 *, timeout: float = 300.0, client: str = "hud"):
        self.base_url = base_url.rstrip("/")
        self.live = Path(live) if live else find_live_backend()
        self.token = read_token(self.live)
        self.timeout = float(timeout)
        self.client = client

    # -- helpers ---------------------------------------------------------
    def _headers(self, json_body: bool = False) -> dict:
        headers = {
            "X-Jarvis-Token": self.token,
            "X-Jarvis-Client": self.client,
            "Accept": "application/json",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def get(self, path: str, *, timeout: float = 30.0) -> dict:
        """One authenticated GET; a refusal is a Blocked sentence."""
        url = self.base_url + path
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except Exception as exc:  # noqa: BLE001
            raise Blocked(f"GET {path} failed: {one_line(exc, 160)}") from None
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise Blocked(f"GET {path} answered {status} with no JSON body") from None
        if not isinstance(parsed, dict):
            raise Blocked(f"GET {path} answered {status} with a non-object body")
        return parsed

    def pending_cards(self) -> list[dict]:
        """Every pending card as a dict, for the id/action a decision needs."""
        answer = self.get("/api/pending", timeout=10)
        cards = answer.get("pending")
        return [card for card in cards or [] if isinstance(card, dict)]

    def pending(self) -> dict:
        """The approval queue: a count is recorded, the cards are left alone."""
        answer = self.get("/api/pending")
        cards = answer.get("pending")
        cards = [card for card in cards or [] if isinstance(card, dict)]
        return {
            "pending": len(cards),
            "actions": [one_line(card.get("action"), 60) for card in cards],
            "ids": [str(card.get("id") or "") for card in cards],
        }

    def decline_card(self, card_id: str, *, note: str = DECLINE_NOTE) -> dict:
        """Decline ONE card. This is the only card decision the harness makes.

        It is a NO, never a yes: a denial executes nothing, creates no
        permission, and is the safe direction. The benchmark declines only a
        card that appeared DURING one of its own turns (the caller compares the
        ids before and after). Without this, one tool call the model makes
        would hold the turn for the card's whole lifetime and the harness would
        measure the approval timeout instead of the answer.
        """
        answer = self.post("/api/deny", {"id": str(card_id), "by": self.client,
                                         "note": note})
        body = answer.get("body") or {}
        return {
            "id": str(card_id),
            "status": answer.get("status"),
            "state": body.get("state") or "",
            "ok": bool(body.get("ok")),
            "error": answer.get("error") or one_line(body.get("error"), 160),
        }

    def verify(self) -> dict:
        """One GET /api/status; a 401 means the token was refused."""
        status = self.get("/api/status")
        return {
            "ok": True,
            "routing": status.get("routing"),
            "taint_latched": status.get("taint_latched"),
            "rush_latched": status.get("rush_latched"),
            "default_model": status.get("default_model"),
            "cloud_allowed": (status.get("budget") or {}).get("cloud_allowed"),
        }

    def version(self) -> dict:
        return self.get("/api/version")

    def work(self) -> dict:
        """The presets: which one is chosen and which lane chat points at."""
        answer = self.get("/api/work")
        return {
            "chosen": answer.get("chosen"),
            "chosen_model": answer.get("chosen_model"),
            "active_lane": answer.get("active_lane"),
            "lane": answer.get("lane"),
            "auto": answer.get("auto"),
            "cloud_escalate": ((answer.get("cloud") or {}).get("escalate") or {}),
        }

    def resources(self) -> dict:
        """The lanes, what is loaded, and the warnings the PC itself emits."""
        answer = self.get("/api/models/resources")
        lanes = []
        for lane in answer.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            lanes.append({
                "key": lane.get("key"),
                "url": lane.get("url"),
                "is_chat_lane": lane.get("is_chat_lane"),
                "state": lane.get("state"),
                "model": lane.get("model"),
                "context_length": lane.get("context_length"),
                "spill_bytes": lane.get("spill_bytes"),
                "on_card_percent": lane.get("on_card_percent"),
            })
        return {
            "active_lane": answer.get("active_lane"),
            "lanes": lanes,
            "warnings": [one_line(w, 240) for w in answer.get("warnings") or []],
            "words": [one_line(w, 240) for w in answer.get("words") or []],
        }

    def post(self, path: str, body: dict, *, timeout: float = 120.0) -> dict:
        """One authenticated POST, with the status and the JSON body kept.

        Used only by `apply_preset`. There is no approve/deny path here.
        """
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path, data=payload,
            headers=self._headers(json_body=True), method="POST",
        )
        status = 0
        raw = ""
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:  # a refusal still carries a body
            status = exc.code
            raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        except Exception as exc:  # noqa: BLE001
            return {"status": 0, "body": {}, "error": one_line(exc, 160)}
        parsed = _json_or_empty(raw)
        return {"status": status, "body": parsed,
                "error": one_line(parsed.get("error"), 200) if isinstance(
                    parsed, dict) else ""}

    def apply_preset(self, preset_id: str) -> dict:
        """Ask the live backend to apply a preset, and report what it did.

        A Coding apply raises ONE `switch_model` card. This method CANNOT
        answer it - there is no approve path in this module - so when a card
        is raised the answer says `applied: false` and the card is left for
        the owner, which is exactly what the harness must do.
        """
        answer = self.post("/api/work/apply", {"preset": str(preset_id)})
        body = answer.get("body") or {}
        pending = body.get("pending") or body.get("waiting") or body.get("card")
        return {
            "requested": str(preset_id),
            "status": answer.get("status"),
            "applied": bool(body.get("ok")) and not pending,
            "pending_card": bool(pending),
            "error": answer.get("error") or one_line(body.get("error"), 200),
            "restored": body.get("restored"),
            "not_restored": body.get("not_restored"),
            "changed": body.get("changed"),
        }

    # -- the one write this module makes ----------------------------------
    def chat(self, text: str, *, conversation_id: str = "",
             temporary: bool = True, timeout: float | None = None) -> Reply:
        """One `POST /api/chat` with a HARD wall-clock deadline.

        `stream: false` on purpose: the benchmark needs the whole answer and
        the response header, and a keepalive tick can hold a streamed turn
        open far past any socket timeout. The whole request runs on a worker
        thread; when the deadline passes the CONNECTION IS CLOSED, which both
        ends the row and lets the server release the turn.

        `temporary: true` so the run leaves no conversation in the owner's
        chat history and depends on no remembered fact. The route header must
        confirm it - an app that asked for temporary and did not get it back
        is told so, and this client records the same fact.
        """
        body = {
            "messages": [{"role": "user", "content": text,
                          "provenance": PROVENANCE}],
            "has_image": False,
            "stream": False,
            "auto": True,
            "device": self.client,
            "provenance": PROVENANCE,
        }
        if temporary:
            body["temporary"] = True
        if conversation_id:
            body["conversation_id"] = conversation_id
        payload = json.dumps(body).encode("utf-8")
        parts = urllib.parse.urlsplit(self.base_url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or (443 if parts.scheme == "https" else 80)
        deadline = float(timeout if timeout is not None else self.timeout)
        answer, route, status, err, raw, route_raw = "", {}, 0, "", "", ""
        timed_out = False
        started = time.time()
        attempts = 0
        declined: list[dict] = []
        declined_ids: set[str] = set()

        def decline_new(baseline: set[str]) -> None:
            """Decline any card this turn raised - a NO, never a yes."""
            try:
                for card in self.pending_cards():
                    card_id = str(card.get("id") or "")
                    if not card_id or card_id in baseline or card_id in declined_ids:
                        continue
                    declined_ids.add(card_id)
                    record = self.decline_card(card_id)
                    record["action"] = one_line(card.get("action"), 80)
                    declined.append(record)
            except Exception:  # noqa: BLE001 - a polling miss is not the turn
                return

        for attempt in (1, 2):
            attempts = attempt
            try:
                baseline = {card.get("id") for card in self.pending_cards()}
            except Exception:  # noqa: BLE001
                baseline = set()
            conn = http.client.HTTPConnection(host, port, timeout=deadline)
            box: dict = {}

            def worker(conn=conn, box=box):
                try:
                    headers = self._headers(json_body=True)
                    conn.request("POST", "/api/chat", body=payload, headers=headers)
                    response = conn.getresponse()
                    box["status"] = response.status
                    box["headers"] = dict(response.getheaders())
                    box["raw"] = response.read(8 * 1024 * 1024)
                except Exception as exc:  # noqa: BLE001
                    box["err"] = f"{type(exc).__name__}: {one_line(exc, 160)}"

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            # While the turn runs, watch the approval queue. A card the turn
            # raises would otherwise hold it for the card's minute-scale
            # lifetime; declining it at once lets the turn finish, changes
            # nothing on the PC, and is recorded in the result.
            finish_by = time.time() + deadline
            while thread.is_alive() and time.time() < finish_by:
                thread.join(min(2.0, max(0.05, finish_by - time.time())))
                if thread.is_alive():
                    decline_new(baseline)
            decline_new(baseline)
            if thread.is_alive():
                timed_out = True
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
                thread.join(3)
                err = ("hard deadline: no complete reply in "
                       f"{int(deadline)}s - the connection was closed")
                status = 0
                break
            status = box.get("status", 0)
            headers = _Headers((box.get("headers") or {}).items())
            route_raw = headers.get_ci("X-Jarvis-Route", "") or ""
            raw = (box.get("raw") or b"").decode("utf-8", "replace")
            err = box.get("err", "") or ""
            route = _json_or_empty(route_raw)
            if attempt == 1 and status in (409, 429, 503) and any(
                word in raw for word in ("busy", "in use", "One moment", "loading")
            ):
                time.sleep(8)
                continue
            break
        elapsed = round(time.time() - started, 2)
        parsed = _json_or_empty(raw)
        if isinstance(parsed, dict):
            choices = parsed.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    answer = message["content"]
            if not answer:
                err = err or _error_sentence(parsed)
        return Reply(status=status, answer=answer, route=route,
                     route_raw=one_line(route_raw, 800), error=err,
                     seconds=elapsed, timed_out=timed_out, attempts=attempts,
                     declined=declined)

    def close(self) -> None:
        """Nothing is held open; here so a caller can be explicit."""
        return None


def _json_or_empty(text: str) -> dict:
    try:
        value = json.loads(text) if text else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _error_sentence(parsed: dict) -> str:
    """The error a chat body carries, in one plain sentence, or ""."""
    error = parsed.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return "the reply carried an error: " + one_line(message, 160)
        return ""
    if isinstance(error, str) and error.strip():
        return "the reply carried an error: " + one_line(error, 160)
    return ""
