"""`/api/status` publishes the phone-facing listener, and says when it is down.

    python3 backend/test_phone_listener_status.py

WHY THIS EXISTS. The phone reaches the PC through a SECOND `jarvis_hud.py`
process, started with `JARVIS_HUD_BIND` set to this machine's Tailscale or
Meshnet address. That process is unsupervised: it vanished twice on 2026-11-20
and `/api/status` reported healthy both times, because its payload had no
`phone_listener` key at all - the keys were activity, budget, business,
default_model, jarvis, lanes, models, ollama, proxy, routing, tools, and
nothing that said whether a listener was configured or answering.

The morning ruling 5.1 (quoted in `decisions.d/2026-11-20-phone-listener-status.md`)
is what this file proves, exactly:

    publish phone_listener: {"configured": bool, "listening": bool,
                             "bind_address": "100.x:4719" | null}
    on /api/status, with "phone_listener_down" in degraded[] when
    configured && !listening

WHAT IS DRIVEN HERE, and it is the real base HUD (`jarvis-backend/jarvis_hud.py`,
the published base the deploy carries), not a paraphrase of it:

  1. NO STATE FILE - the honest empty shape, and NO degradation. A machine that
     never set up phone access is not broken.
  2. A FILE NAMING A LOOPBACK ADDRESS - not configured, no degradation: a
     loopback bind cannot be reached by a phone, so it is not a phone listener.
  3. A FILE NAMING A NON-LOOPBACK ADDRESS AND NOTHING LISTENING - configured,
     not listening, `bind_address` names the address and port, and `degraded`
     names `phone_listener_down`. This is the outage the key exists for.
  4. A LISTENER THAT ANSWERS - listening true, no degradation, and the probe
     really went to the configured address and port with the ~0.5 s cap.
  5. The probe itself, against a REAL loopback fixture (tests never bind a
     non-loopback address): it answers True, and False for a closed port, in
     under the cap. Nothing raises.
  6. The state file's own contract: the writer records only bind_address, pid
     and written - NEVER the token - writes nothing for a loopback bind, and
     the clean-exit remover deletes only this process's own record.

This suite runs offline: no HUD, no network, no token and no non-loopback
bind. The ONE live dependency is the published base HUD file itself.
"""
from __future__ import annotations

import inspect
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
HUD = BASE / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


class Fake:
    """Just enough of a BaseHTTPRequestHandler for the /api/status branch."""

    def __init__(self, path="/api/status"):
        self.path = path
        self._headers_sent = False
        self.headers = {}
        self.client_address = ("127.0.0.1", 5)
        self.sent = []

    def _send(self, code, obj):
        self.sent.append((code, obj))
        return code, obj


def route_block(text: str) -> str:
    """The base HUD's own /api/status handler, from its `if` to the 404 after it."""
    start = text.index('        if path == "/api/status":')
    end = text.index('        return self._send(404, {"error": "not found"})', start)
    return text[start:end]


def main() -> int:
    if not HUD.is_file():
        print("skip  jarvis-backend/jarvis_hud.py is not here")
        return 0

    # ---- the published base HUD carries the field, before anything runs it ---
    source = HUD.read_text(encoding="utf-8")
    block = route_block(source)
    check("the base HUD's /api/status route builds `phone_listener`",
          "phone_listener = _phone_listener_status()" in block, block[:200])
    check("... and the payload carries the field and the degraded list",
          '"phone_listener": phone_listener,' in block
          and '"degraded": degraded,' in block, block[:200])
    check("... the helper is the one that writes and removes the state file",
          all(word in source for word in
              ("PHONE_LISTENER_FILE", "def _phone_listener_write(",
               "def _phone_listener_clear(", "def _phone_listener_probe(",
               "def _phone_listener_status(", "def _phone_listener_degraded(")))
    check("... the process records itself only after its socket has bound",
          "    _phone_listener_write(bind)\n    _install_shutdown(httpd)" in source)
    check("... and the clean exit removes it, beside the GPU handback",
          "atexit.register(_release_gpu)\n    atexit.register(_phone_listener_clear)"
          in source)

    # Hermetic BEFORE the import: the config folder this module reads is a temp
    # one, so no real ~/.openjarvis file can make a case pass or fail.
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-phone-listener-"))
    os.environ["OPENJARVIS_CONFIG_DIR"] = str(tmp)
    os.environ.pop("JARVIS_BACKEND", None)
    sys.path.insert(0, str(BASE))
    try:
        import jarvis_hud as mod
    except Exception as exc:  # noqa: BLE001 - say why, never traceback a run
        check("the published base HUD imports", False, f"{type(exc).__name__}: {exc}")
        print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
        return 1
    check("the published base HUD imports", True)
    check("the state file lives in the config folder",
          mod.PHONE_LISTENER_FILE == tmp / "phone-listener.json",
          mod.PHONE_LISTENER_FILE)
    check("the probe cap is about half a second (0 < cap <= 0.5)",
          0 < mod._PHONE_PROBE_TIMEOUT <= 0.5, mod._PHONE_PROBE_TIMEOUT)

    # ---- drive the REAL route with a warm upstream cache ---------------------
    def answer(path="/api/status"):
        mod._STATUS_CACHE.clear()
        mod._STATUS_CACHE.update({"jarvis": True, "ollama": False, "proxy": False,
                                  "models": [], "polled_at": 1.0})
        h = Fake(path)
        saved = (mod._origin_ok, mod._token_ok)
        mod._origin_ok = lambda _self: True
        mod._token_ok = lambda _self: True
        try:
            mod.Handler.do_GET(h)
        finally:
            mod._origin_ok, mod._token_ok = saved
        return h.sent[0][1] if h.sent else {}

    def state_file(bind, pid=None, extra=None):
        data = {"bind_address": bind, "pid": os.getpid() if pid is None else pid,
                "written": "2026-11-20T15:00:00-08:00"}
        if extra:
            data.update(extra)
        mod.PHONE_LISTENER_FILE.parent.mkdir(parents=True, exist_ok=True)
        mod.PHONE_LISTENER_FILE.write_text(json.dumps(data), encoding="utf-8")

    def no_state_file():
        try:
            mod.PHONE_LISTENER_FILE.unlink()
        except OSError:
            pass

    # ---- 1. no state file: the honest empty shape, and no degradation -------
    no_state_file()
    body = answer()
    field = body.get("phone_listener")
    check("no state file -> phone_listener is present with configured false",
          isinstance(field, dict) and field.get("configured") is False, field)
    check("... listening false and bind_address null",
          field.get("listening") is False and field.get("bind_address") is None, field)
    check("... and NOTHING is degraded (a machine with no phone access is not broken)",
          isinstance(body.get("degraded"), list)
          and "phone_listener_down" not in body["degraded"], body.get("degraded"))

    # ---- 2. a loopback address is not a phone-facing listener --------------
    state_file("127.0.0.1")
    field = answer().get("phone_listener")
    check("a file naming 127.0.0.1 -> configured false, no bind_address",
          field == {"configured": False, "listening": False, "bind_address": None},
          field)
    check("... a loopback file is NOT degraded",
          "phone_listener_down" not in answer().get("degraded", []))

    # ---- 3. configured non-loopback, nothing listening: FAIL, named ---------
    state_file("100.75.21.228")
    real_create = mod.socket.create_connection
    probes = []

    def refused(target, timeout=None):
        probes.append((target, timeout))
        raise ConnectionRefusedError(10061, "connection refused")

    mod.socket.create_connection = refused
    try:
        body = answer()
    finally:
        mod.socket.create_connection = real_create
    field = body.get("phone_listener")
    check("a non-loopback file with nothing listening -> configured true",
          field.get("configured") is True, field)
    check("... listening false", field.get("listening") is False, field)
    check("... bind_address names the address AND port",
          field.get("bind_address") == "100.75.21.228:4719", field)
    check("... and degraded names phone_listener_down",
          body.get("degraded") == ["phone_listener_down"], body.get("degraded"))
    check("... the probe went to that exact address and port, with the ~0.5 s cap",
          probes and probes[0][0] == ("100.75.21.228", 4719)
          and probes[0][1] == mod._PHONE_PROBE_TIMEOUT, probes)

    # ---- 4. a listener that answers -> listening true, NOT degraded ---------
    class FakeSock:
        def close(self):
            return None

    seen = []

    def answering(target, timeout=None):
        seen.append((target, timeout))
        return FakeSock()

    mod.socket.create_connection = answering
    try:
        body = answer()
    finally:
        mod.socket.create_connection = real_create
    field = body.get("phone_listener")
    check("a configured listener that answers -> listening true",
          field.get("configured") is True and field.get("listening") is True, field)
    check("... bind_address is unchanged", field.get("bind_address")
          == "100.75.21.228:4719", field)
    check("... and nothing is degraded", body.get("degraded") == [], body.get("degraded"))
    check("... the probe asked exactly the configured socket",
          seen and seen[0][0] == ("100.75.21.228", 4719), seen)

    # ---- the hole case: a malformed file is absent, never a crash -----------
    mod.PHONE_LISTENER_FILE.write_text("{not json", encoding="utf-8")
    check("a malformed state file answers the empty shape, not an exception",
          mod._phone_listener_status()
          == {"configured": False, "listening": False, "bind_address": None})
    mod.PHONE_LISTENER_FILE.write_text(json.dumps(["not", "an", "object"]),
                                       encoding="utf-8")
    check("... and so does a JSON file that is not an object",
          mod._phone_listener_status()
          == {"configured": False, "listening": False, "bind_address": None})

    # ---- 5. the REAL probe: a loopback fixture answers, a closed port not ---
    no_state_file()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = []

    def acceptor():
        try:
            conn, _ = server.accept()
            accepted.append(True)
            conn.close()
        except Exception:
            pass

    threading.Thread(target=acceptor, daemon=True).start()
    old_port = mod.HUD_PORT
    mod.HUD_PORT = port
    try:
        check("the real probe answers True for a loopback listener",
              mod._phone_listener_probe("127.0.0.1") is True)
        server.close()
        started = time.perf_counter()
        down = mod._phone_listener_probe("127.0.0.1")
        elapsed = time.perf_counter() - started
        check("... and False, quickly and without raising, for a closed port",
              down is False and elapsed < mod._PHONE_PROBE_TIMEOUT + 0.25, elapsed)
        started = time.perf_counter()
        down = mod._phone_listener_probe("")
        elapsed = time.perf_counter() - started
        check("... an empty address is a False answer, never an exception",
              down is False and elapsed < mod._PHONE_PROBE_TIMEOUT + 0.25, elapsed)
    finally:
        mod.HUD_PORT = old_port
        try:
            server.close()
        except OSError:
            pass

    # ---- 6. the state file's own contract: no token, own-pid-only removal ---
    no_state_file()
    mod._phone_listener_write("127.0.0.1")
    check("a loopback bind records NOTHING (no phone listener is configured)",
          not mod.PHONE_LISTENER_FILE.exists())
    mod.HUD_TOKEN = "s3cret-token-that-must-never-reach-disk"
    try:
        mod._phone_listener_write("100.75.21.228")
    finally:
        raw = (mod.PHONE_LISTENER_FILE.read_text(encoding="utf-8")
               if mod.PHONE_LISTENER_FILE.exists() else "")
    try:
        data = json.loads(raw)
    except Exception:
        data = {}
    check("the state file holds exactly bind_address, pid and written",
          isinstance(data, dict) and set(data) == {"bind_address", "pid", "written"},
          data)
    check("... its bind_address is the address THIS process bound",
          data.get("bind_address") == "100.75.21.228", data)
    check("... its pid is this process's own", data.get("pid") == os.getpid(), data)
    check("... and the token is not in it, by name or by value",
          "token" not in raw.lower()
          and "s3cret-token-that-must-never-reach-disk" not in raw, raw)
    check("... the writer never reads the token at all",
          "HUD_TOKEN" not in inspect.getsource(mod._phone_listener_write))
    check("... the clean-exit remover deletes this process's own record",
          (mod._phone_listener_clear(), not mod.PHONE_LISTENER_FILE.exists())[1])
    mod._phone_listener_write("100.75.21.228")
    mod.PHONE_LISTENER_FILE.write_text(json.dumps(
        {"bind_address": "100.75.21.228", "pid": os.getpid() + 1,
         "written": "2026-11-20T15:00:00-08:00"}), encoding="utf-8")
    mod._phone_listener_clear()
    check("... but never another process's record",
          mod.PHONE_LISTENER_FILE.exists())
    no_state_file()

    # ---- the payload never leaks the token into /api/status -----------------
    mod.HUD_TOKEN = "s3cret-token-that-must-never-reach-disk"
    state_file("100.75.21.228")
    mod.socket.create_connection = answering
    try:
        body = answer()
    finally:
        mod.socket.create_connection = real_create
    check("the /api/status answer carries no token by name or by value",
          "token" not in json.dumps(body).lower(), body.get("phone_listener"))

    # ---- 7. the CARRIER: base + five literal deltas, never a new .patch ----
    # jarvis_hud.py is a patched-base file: the live copy is newer than the
    # published base and is never replaced, so a change that lives in the base
    # and in no patch reaches it through tools/reconcile_live_backend.py's
    # DELTA_TABLE - the same route DEF-002 and the A4 latches took. This section
    # proves that route is fully wired, because a base edit with no delta would
    # be a change the owner's own PC can never receive.
    sys.path.insert(0, str(REPO / "tools"))
    import reconcile_live_backend as R
    names = ("hud-phone-listener.patch", "hud-phone-listener-route.patch",
             "hud-phone-listener-keys.patch", "hud-phone-listener-start.patch",
             "hud-phone-listener-exit.patch")
    check("the deploy carries the change as five literal deltas",
          all(n in R.DELTA_TABLE for n in names),
          [n for n in names if n not in R.DELTA_TABLE])
    block_files_ok = True
    for name in names:
        entry = R.DELTA_TABLE[name]["jarvis_hud.py"]
        block_files_ok = block_files_ok and bool(entry.get("probes")) and (
            bool(entry.get("file")) or bool(entry.get("replace_file")))
        for key in ("file", "replace_file"):
            if entry.get(key):
                block_files_ok = block_files_ok and \
                    (REPO / "tools" / "hud-deltas" / str(entry[key])).is_file()
    check("... each with post-image probes and its block file on disk", block_files_ok)
    helpers = "\n".join(R._delta_lines(str(
        R.DELTA_TABLE["hud-phone-listener.patch"]["jarvis_hud.py"]["file"])))
    check("the helper block IS the published base's own text, byte for byte",
          helpers != "" and source.count(helpers) == 1, source.count(helpers))
    route_lines = "\n".join(R._delta_lines(str(
        R.DELTA_TABLE["hud-phone-listener-route.patch"]["jarvis_hud.py"]["file"])))
    check("the route block is the base's own compute lines, byte for byte",
          route_lines != "" and source.count(route_lines) == 1,
          source.count(route_lines))
    check("NO backend patch carries the phone_listener change (the carrier is "
          "base + delta)",
          not any(b"phone_listener" in p.read_bytes()
                  for p in (REPO / "backend").glob("*.patch")))
    order = list(R.DELTA_TABLE)
    check("the keys delta is ordered AFTER activity-turn-guard.patch "
          "(its old block ends on a line that patch writes)",
          order.index("activity-turn-guard.patch")
          < order.index("hud-phone-listener-keys.patch"))
    activity_patch = (REPO / "backend" / "activity-turn-guard.patch").read_text(
        encoding="utf-8", errors="replace")
    keys_old = "\n".join(R._delta_lines(str(
        R.DELTA_TABLE["hud-phone-listener-keys.patch"]["jarvis_hud.py"]["replace_file"])))
    check("... and that last line really is one the activity patch adds",
          keys_old.splitlines()
          and all(line.strip() in activity_patch
                  for line in keys_old.splitlines()[-2:]))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
