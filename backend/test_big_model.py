"""The big model (slow) with colibri: detection, the switches, the engine
process, lane_for, the wiki's use of it, deep questions, and the patch.

    python3 test_big_model.py

Runs anywhere. No colibri, no model, no Windows: the PC is replaced by the
same World tools/gen_big_model_cases.py uses (folders, memory, disk, drive
type, the process start - recorded, never done), and colibri's answers come
either from a stand-in function or, for deep questions, from a real HTTP
server on 127.0.0.1 in colibri's documented OpenAI shape.

What it proves:

  - detection: colibri absent / present, Python absent (and the Store's
    stand-in python.exe), models missing / present / not a finished download,
    too little memory in total and free right now, a full disk, a giant model
    on a SATA drive; it never raises, and it is cached about 30 s.
  - the switches: ON is exactly one card (big_model_enable), a second ON
    while it waits is 409, OFF is immediate, ON is refused when not capable,
    before the main switch, or when the tier is not "ask"; only "ask" +
    "approved" turns it on.
  - the engine: its command line (127.0.0.1 only, the port, the model id, no
    graphics card by default), its environment (the key in COLI_API_KEY and
    nowhere else), the second card only with cuda "on", a port someone else
    holds, not enough free memory; the key is in no command line, status,
    card, error, log, event, audit line or printed output.
  - idle stop, and stop when switched off.
  - lane_for() is None in every not-ready state, and for any job but the two.
  - the wiki: the big model only when its switch is on; while it loads the job
    waits in "reading", saying why, and it never falls back to the second
    card; its call goes to colibri with the schema as instructions, no
    response_format; GET /api/wiki does not start colibri.
  - deep questions: queued, run against a stub server on loopback, kept in
    deep-questions.jsonl (capped), listed, a failure said honestly, tokens
    and words per second recorded, one doorbell event with no text.
  - big-model.patch applies after wiki.patch to what the earlier patches
    wrote, and reverses; the install lists, the toml, the fixture.
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, require_shipped  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

require_shipped("jarvis_big_model.py", "jarvis_wiki.py", "jarvis_second_card.py",
                "jarvis_token_store.py")

import jarvis_big_model as BM  # noqa: E402
import jarvis_second_card as SC  # noqa: E402
import jarvis_wiki as W  # noqa: E402
import gen_big_model_cases as G  # noqa: E402

FAILED, PASSED = [], []
KEY = G.KEY
#: Everything printed while the tests run, to grep for the key at the end.
CAPTURED = io.StringIO()


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    line = f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else "")
    sys.__stdout__.write(line + "\n")


def no_key(*things) -> bool:
    return all(KEY not in (t if isinstance(t, str) else json.dumps(t, default=str))
               for t in things)


Verdict = G.Verdict
World = G.World


# ------------------------------------------------------------ detection --

def t_detection():
    with World(colibri=False):
        d = BM.detect()
        check("colibri absent: not capable, and says where to put it",
              d["capable"] is False and d["colibri"]["found"] is False
              and "coli_path" in d["why"] and "no coli.cmd" in d["why"], d["why"])
    with World(colibri=False, cfg={"coli_path": ""}):
        d = BM.detect()
        check("no coli_path and none on PATH: says so", d["capable"] is False
              and "was not found" in d["why"] and "BIG-MODEL.md" in d["why"], d["why"])
    with World():
        d = BM.detect()
        check("colibri, Python and two models: capable",
              d["capable"] is True and d["colibri"]["found"] and d["python"]["found"]
              and [m["id"] for m in d["models"] if m["usable"]] == ["qwen36", "dsv4-flash"])
        check("the private parts (launcher, python command) are not in the public view",
              not any(k.startswith("_") for k in BM._public_det(d)))
    with World(python=False):
        d = BM.detect()
        check("no Python 3: not capable, and says to tick Add python.exe to PATH",
              d["capable"] is False and "Add python.exe to PATH" in d["why"], d["why"])
    with World() as w:
        w.which = lambda name: ("C:\\Users\\o\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe"
                                if name == "python" else None)
        BM._which = w.which
        d = BM.detect(fresh=True)
        check("only the Microsoft Store's python.exe: not Python, and said so",
              d["python"]["found"] is False and "Microsoft Store" in d["python"]["why"])
    with World(models=()):
        d = BM.detect()
        check("no models configured: says to add one", d["capable"] is False
              and "no model is set up" in d["why"])
    with World(models=(G.MEDIUM,), missing=("qwen36",)):
        d = BM.detect()
        check("a model folder that does not exist: not usable, named",
              d["models"][0]["usable"] is False and "does not exist" in d["models"][0]["why"])
    with World(models=(G.MEDIUM,), no_config=("qwen36",)):
        d = BM.detect()
        check("a folder with no config.json: not a finished download",
              d["models"][0]["found"] is False and "config.json" in d["models"][0]["why"])
    bad = [dict(G.MEDIUM, id="a b"), dict(G.MEDIUM, id="ok1", kind="huge")]
    with World(models=bad):
        rows = BM.detect()["models"]
        check("a bad id and a bad kind are refused, in words",
              "letters, digits" in rows[0]["why"] and '"medium" or "giant"' in rows[1]["why"])
    with World(ram=(16.0, 14.0)):
        rows = {m["id"]: m for m in BM.detect()["models"]}
        check("16 GB in total: the medium model (24 GB) is not usable, citing colibri",
              rows["qwen36"]["usable"] is False and "needs 24 GB" in rows["qwen36"]["why"]
              and "README" in rows["qwen36"]["why"])
        check("... the giant one (16 GB minimum) is", rows["dsv4-flash"]["usable"] is True)
    with World(ram=(31.9, 12.0)):
        rows = {m["id"]: m for m in BM.detect()["models"]}
        check("enough in total but not free now: usable, cannot start now, with the numbers",
              rows["qwen36"]["usable"] and not rows["qwen36"]["can_start_now"]
              and "24 GB" in rows["qwen36"]["why"] and "12 GB is free" in rows["qwen36"]["why"])
    with World(free={"D:": 1.2, "E:": 290.0}):
        rows = {m["id"]: m for m in BM.detect()["models"]}
        check("a nearly full drive: not usable, says how much to keep free",
              rows["qwen36"]["usable"] is False and "1.2 GB free" in rows["qwen36"]["why"])
    with World(models=(dict(G.GIANT, dir="D:\\models\\ds"),)):
        row = BM.detect()["models"][0]
        check("a giant model on the SATA drive: usable, with the owner's note",
              row["usable"] and row["drive"] == "D:" and "SATA" in row["note"]
              and "NVMe" in row["note"])
    with World(drives={}):
        rows = {m["id"]: m for m in BM.detect()["models"]}
        check("drive type unknown: the owner's own note, not a guess",
              rows["dsv4-flash"]["drive_type"] == "unknown"
              and "could not tell" in rows["dsv4-flash"]["note"]
              and rows["qwen36"]["note"] is None)
    check("Get-PhysicalDisk's answer, in words",
          BM.parse_drive_type("NVMe|SSD") == "NVMe" and BM.parse_drive_type("SATA|SSD") == "SATA SSD"
          and BM.parse_drive_type("SATA|HDD") == "SATA HDD" and BM.parse_drive_type("") == "unknown"
          and BM.parse_drive_type("garbage") == "unknown")
    with World() as w:
        calls = []
        real = BM._detect
        BM._detect = lambda: calls.append(1) or real()
        try:
            BM.detect()
            BM.detect()
            check("cached: the second look within 30 s reads nothing", len(calls) == 1)
            w.clock += 31
            BM.detect()
            check("... and after 30 s it looks again", len(calls) == 2)
            BM._detect = lambda: 1 / 0
            d = BM.detect(fresh=True)
            check("never raises: an error is 'not capable', in words",
                  d["capable"] is False and "ZeroDivisionError" in d["why"])
        finally:
            BM._detect = real


# ------------------------------------------------------------- switches --

def t_switches():
    with World() as w:
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = BM.request_change("wiki", True, gate=gate)
        check("a job before the main switch: 400, no card",
              code == 400 and "main switch" in out["error"] and not seen, out)
        code, out = BM.request_change("master", True, gate=gate, spawn=lambda fn: None)
        check("master ON: a card is up, nothing is on yet",
              code == 200 and out["pending"] is True and out["enabled"] is False
              and BM._read_switches()["master"] is False)
        code2, out2 = BM.request_change("master", True, gate=gate, spawn=lambda fn: None)
        check("a second ON while the card waits: 409", code2 == 409
              and "already waiting" in out2["error"])
        check("status lists it as pending", BM.status()["pending"] == ["master"])
        code, out = BM.request_change("master", False)
        check("OFF is at once, needs no card, and withdraws the waiting one",
              code == 200 and out["enabled"] is False and not seen and BM.status()["pending"] == [])
        code, out = BM.request_change("master", True, gate=gate)
        check("approved: exactly one card, action big_model_enable",
              len(seen) == 1 and seen[0][0] == "big_model_enable", seen)
        d, text = seen[0][1], seen[0][2]
        check("the card names the models, memory, disk, 127.0.0.1 only, and nothing leaves",
              "Qwen3.6-35B-A3B" in text and "DeepSeek V4 Flash" in text and "24 GB" in text
              and "31.9 GB" in text and "3100 GB free on D:" in text
              and "127.0.0.1:8765" in text and "Nothing leaves this PC" in text
              and "never for chat, voice or approvals" in text and "If you say no" in text
              and d["leaves_this_pc"] is False, text)
        check("the card says the speed is not verified here", "checked on this PC" in text)
        check("the main switch is on", BM._read_switches()["master"] is True)
        seen.clear()
        code, out = BM.request_change("deep_questions", True, gate=gate)
        check("deep_questions: one card naming its model",
              code == 200 and len(seen) == 1 and "DeepSeek V4 Flash (giant)" in seen[0][2]
              and seen[0][1]["model"] == "dsv4-flash" and BM._read_switches()["deep_questions"])
        for label, v in (("tier notify", Verdict(True, "notify", "notify")),
                         ("tier auto", Verdict(True, "auto", "auto")),
                         ("denied", Verdict(False, "ask", "denied")),
                         ("timed out", Verdict(False, "ask", "timed_out")),
                         ("old gate, allowed on auto", Verdict(True, "auto", None))):
            BM.request_change("wiki", False)
            BM.request_change("wiki", True, gate=lambda a, dd, p, v=v: v)
            check(f"{label}: wiki stays off", BM._read_switches()["wiki"] is False)
        held = []
        BM.request_change("wiki", True, gate=lambda a, dd, p: Verdict(True, "ask", "approved"),
                          spawn=lambda fn: held.append(fn))
        BM.request_change("wiki", False)
        held[0]()
        check("OFF while the card waited, then approved: the later OFF wins",
              BM._read_switches()["wiki"] is False)
        # AP-5: two full rounds; the first card is answered last.
        cards = []
        yes = lambda a, dd, p: Verdict(True, "ask", "approved")
        BM.request_change("wiki", True, gate=yes, spawn=cards.append)
        BM.request_change("wiki", False)
        BM.request_change("wiki", True, gate=yes, spawn=cards.append)
        BM.request_change("wiki", False)
        cards[0]()
        check("two ON/OFF rounds, the FIRST card approved: the later OFF still wins",
              len(cards) == 2 and BM._read_switches()["wiki"] is False)
        cards[1]()
        check("... and the second card too", BM._read_switches()["wiki"] is False)
        code, out = BM.request_change("wiki", True, gate=gate, tier_of=lambda a: "auto")
        check("tier not 'ask': refused before any card", code == 503 and "'ask'" in out["error"])
        check("unknown switch: 400", BM.request_change("chat", True)[0] == 400)
        check("enabled must be a boolean", BM.handle_post({"switch": "wiki", "enabled": 1})[0] == 400)
        check("a body that is not an object: 400", BM.handle_post([1])[0] == 400)
    # AP-6: status()["last"] says how the most recent card ended.
    with World() as w:
        check("no card has ended yet: last is null", BM.status()["last"] is None)
        BM.request_change("master", True, gate=lambda *a: Verdict(True, "ask", "approved"))
        last = BM.status()["last"]
        check("approved: enabled, with the switch and a sentence",
              set(last) == {"feature", "outcome", "why", "at"} and last["feature"] == "master"
              and last["outcome"] == "enabled" and last["why"] == "The big model was turned on.",
              last)
        BM.request_change("wiki", True, gate=lambda *a: Verdict(False, "ask", "denied"))
        last = BM.status()["last"]
        check("denied: said as denied, naming the job",
              last["feature"] == "wiki" and last["outcome"] == "denied"
              and last["why"] == "You said no, so \"Wiki builder\" stays off.", last)
        BM.request_change("wiki", True, gate=lambda *a: Verdict(False, "ask", "timed_out"))
        check("timed out: said as timed_out", BM.status()["last"]["outcome"] == "timed_out")
    # AP-4: the master card says what comes back; a job's card answered after
    # the master switch went off does not turn the job on.
    with World() as w:
        seen = []
        gate = lambda a, d, p: seen.append(p) or Verdict(True, "ask", "approved")
        w.switches(master=False, wiki=True)
        BM.request_change("master", True, gate=gate)
        check("master card with a job left on: says it works again at once",
              seen and "If you say yes: \"Wiki builder\" works again at once" in seen[0], seen)
        seen.clear()
        w.switches(master=False)
        BM.request_change("master", True, gate=gate)
        check("master card with no job on: says no job uses it yet",
              seen and "no job uses it yet" in seen[0], seen)
        held = []
        BM.request_change("deep_questions", True,
                          gate=lambda a, d, p: Verdict(True, "ask", "approved"),
                          spawn=held.append)
        BM.request_change("master", False)
        held[0]()
        check("job approved after master went OFF: stays off, refused with the reason",
              BM._read_switches()["deep_questions"] is False
              and BM._LAST["deep_questions"]["outcome"] == "refused"
              and "switch was turned off" in BM._LAST["deep_questions"]["reason"],
              BM._LAST.get("deep_questions"))
    with World(colibri=False) as w:
        seen = []
        code, out = BM.request_change("master", True, gate=lambda *a: seen.append(a))
        check("ON with colibri not found: 503 with the reason, no card",
              code == 503 and ("colibri was not found" in out["error"]
                               or "no coli.cmd" in out["error"]) and not seen, out)
    with World(ram=(16.0, 14.0), models=(G.MEDIUM,)) as w:
        code, out = BM.request_change("master", True, gate=lambda *a: None)
        check("ON with too little memory in total: 503, says why",
              code == 503 and "needs 24 GB" in out["error"], out)
    with World(models=(G.MEDIUM,)) as w:
        w.switches(master=True)
        code, out = BM.request_change("deep_questions", True, gate=lambda *a: None)
        check("deep_questions falls back to the only model (medium) when no giant is set up",
              code == 200, out)
    with World(cfg={"deep_model": "nope"}) as w:
        w.switches(master=True)
        code, out = BM.request_change("deep_questions", True, gate=lambda *a: None)
        check("a job whose chosen model id is not configured: 503, names the setting",
              code == 503 and "deep_model" in out["error"], out)
    src = (HERE / "jarvis_big_model.py").read_text(encoding="utf-8")
    code_only = re.sub(r'(?s)""".*?"""', "", src)
    check("no auto-approve anywhere in the module",
          "auto_approve" not in code_only and "confirm_auto" not in code_only)


# ------------------------------------------------------------ the engine --

def t_the_engine():
    with World() as w:
        w.switches(master=True, deep_questions=True)
        lane = BM.lane_for("deep_questions")
        check("lane_for starts colibri, and it is ready: the lane is loopback",
              len(w.started) == 1 and lane is not None and lane.url == "http://127.0.0.1:8765"
              and lane.model == "dsv4-flash" and lane.num_ctx == 16384, repr(lane))
        p = w.started[0]
        a = p.args
        check("the command: python, colibri's coli script, serve",
              a[:2] == ["C:\\Windows\\py.exe", "-3"] and a[3] == "serve"
              and a[2].replace("/", "\\") == "C:\\colibri\\coli", a)

        def opt(name):
            return a[a.index(name) + 1] if name in a else None
        check("--model the folder, --host 127.0.0.1, --port 8765, --model-id the id",
              opt("--model") == "E:\\models\\DeepSeek-V4-Flash" and opt("--host") == "127.0.0.1"
              and opt("--port") == "8765" and opt("--model-id") == "dsv4-flash")
        check("--ctx 16384, --gpu none (no card), --ram 16 for a giant model",
              opt("--ctx") == "16384" and opt("--gpu") == "none" and opt("--ram") == "16")
        env = p.kwargs["env"]
        check("the key reaches colibri in COLI_API_KEY", env.get("COLI_API_KEY") == KEY)
        check("... and not on the command line", no_key(a))
        check("no graphics card: CUDA_VISIBLE_DEVICES -1, COLI_CUDA 0, DSV4_CUDA 0",
              env["CUDA_VISIBLE_DEVICES"] == "-1" and env["COLI_CUDA"] == "0"
              and env["DSV4_CUDA"] == "0")
        check("the key is kept in Credential Manager (a stand-in here)",
              w.stored_key == KEY and BM.status()["key_kept"] == "credential-manager")
        keyed = [(u, k) for (m, u, pl, k) in w.http if k]
        check("the key is sent only to http://127.0.0.1:8765",
              keyed and all(u.startswith("http://127.0.0.1:8765/") for (u, k) in keyed))
        check("asking again does not start a second one",
              BM.lane_for("deep_questions") is not None and len(w.started) == 1)
        st = BM.status()
        check("status: ready, with the model, and no key in it",
              st["engine"]["state"] == "ready" and st["engine"]["model"] == "dsv4-flash"
              and no_key(st))
        # Idle stop.
        w.clock += 9 * 60
        check("nine minutes idle: still running", BM._ENGINE.check_idle() is False
              and p.alive)
        BM._ENGINE.begin()
        w.clock += 5 * 60
        check("busy past ten minutes: not stopped", BM._ENGINE.check_idle() is False)
        BM._ENGINE.end()
        w.clock += 11 * 60
        check("ten minutes with nothing to do: stopped - that one, and only it",
              BM._ENGINE.check_idle() is True and w.killed == [p]
              and BM.status()["engine"]["state"] == "off"
              and "10 minutes" in BM.status()["engine"]["why"])
        BM.lane_for("deep_questions")
        check("a new job starts it again", len(w.started) == 2 and w.started[1].alive)
        BM.request_change("deep_questions", False)
        check("switching the job off stops it at once", w.killed[-1] is w.started[1]
              and BM._ENGINE.state == "off")
    with World(windows=False, store=False) as w:
        w.switches(master=True, wiki=True)
        BM.lane_for("wiki")
        check("no Credential Manager: the key lives in memory for this run, and says so",
              w.started and w.started[0].kwargs["env"]["COLI_API_KEY"] == KEY
              and BM.status()["key_kept"] == "this-run-only"
              and "for this run only" in BM.status()["key_where"])
        check("the medium model gets no --ram (colibri's qwen36 ignores it)",
              "--ram" not in w.started[0].args)
    with World(port_taken=True) as w:
        w.switches(master=True, wiki=True)
        check("a port someone else holds: no process, failed, said plainly",
              BM.lane_for("wiki") is None and not w.started
              and "another program" in BM.status()["engine"]["why"])
    with World(ram=(31.9, 20.0)) as w:
        w.switches(master=True, wiki=True)
        check("not enough memory free right now: not started, with the numbers",
              BM.lane_for("wiki") is None and not w.started
              and "needs 24 GB" in BM.status()["engine"]["why"]
              and "20 GB is free" in BM.status()["engine"]["why"])
    with World(ready=False) as w:
        w.switches(master=True, wiki=True)
        check("never answers: None, then failed after load_minutes, and stopped",
              BM.lane_for("wiki") is None and BM._ENGINE.state == "failed"
              and "did not finish loading within 20 minutes" in BM._ENGINE.why
              and w.killed == w.started)
    # The command line itself.
    col = {"found": True, "dir": "C:\\colibri", "launcher": "C:\\colibri\\coli.cmd",
           "script": "C:\\colibri\\coli"}
    m = dict(G.MEDIUM)
    for host in ("0.0.0.0", "192.168.1.5", "localhost"):
        try:
            BM.engine_command(m, colibri=col, python=["py", "-3"], port=8765, ctx=8192,
                              gpu="none", host=host)
            check(f"engine_command refuses host {host}", False)
        except ValueError:
            check(f"engine_command refuses host {host}", True)
    for port in (11434, 11435, 80):
        try:
            BM.engine_command(m, colibri=col, python=["py", "-3"], port=port, ctx=8192, gpu="none")
            check(f"engine_command refuses port {port}", False)
        except ValueError:
            check(f"engine_command refuses port {port}", True)
    cmd_only = dict(col, script=None)
    argv = BM.engine_command(m, colibri=cmd_only, python=None, port=8765, ctx=8192, gpu="none")
    check("without the coli script beside it, coli.cmd itself",
          argv[:2] == ["C:\\colibri\\coli.cmd", "serve"])
    try:
        BM.engine_command(dict(m, dir="D:\\a&calc"), colibri=cmd_only, python=None, port=8765,
                          ctx=8192, gpu="none")
        check("through coli.cmd, a folder with & in its name is refused", False)
    except ValueError as exc:
        check("through coli.cmd, a folder with & in its name is refused", "rename" in str(exc))
    env = BM.engine_env(KEY, base={"COLI_ALLOWED_HOSTS": "evil.example", "COLI_API_KEY": "old",
                                   "CUDA_VISIBLE_DEVICES": "0", "COLI_ALLOW_INSECURE_BIND": "1",
                                   "PATH": "/bin"})
    check("inherited settings that would widen colibri are dropped",
          "COLI_ALLOWED_HOSTS" not in env and "COLI_ALLOW_INSECURE_BIND" not in env
          and env["COLI_API_KEY"] == KEY and env["CUDA_VISIBLE_DEVICES"] == "-1"
          and env["PATH"] == "/bin")
    for bad in ("0", "1", "GPU-x; rm"):
        try:
            BM.engine_env(KEY, cuda_uuid=bad, base={})
            check(f"a card only by its id, not {bad!r}", False)
        except ValueError:
            check(f"a card only by its id, not {bad!r}", True)


def t_one_job_at_a_time():
    # K2: the wiki and deep questions (by default two different models) each
    # restarted colibri for their own model while the other was loading.
    # The audit's shape: both jobs polling, three rounds each.
    with World(spawn_now=False) as w:
        w.switches(master=True, wiki=True, deep_questions=True)
        for _ in range(3):
            BM.lane_for("wiki")
            BM.lane_for("deep_questions")
        check("two jobs asking in turn: colibri started ONCE, never killed",
              len(w.started) == 1 and not w.killed, [p.args for p in w.started])
        st, why = BM.job_state("deep_questions")
        check("the waiting job is 'busy', and says which job has it and what it waits for",
              st == "busy" and "Wiki builder job" in why and "DeepSeek V4 Flash" in why,
              (st, why))
        check("the holding job still reads 'loading'", BM.job_state("wiki")[0] == "loading")
        BM.release("deep_questions")          # not the holder: changes nothing
        BM.lane_for("deep_questions")
        check("only the holder's release frees it", len(w.started) == 1)
        BM.release("wiki")
        BM.lane_for("deep_questions")
        check("after the wiki job ends, deep questions get it: one stop, one start",
              len(w.started) == 2 and len(w.killed) == 1
              and BM._ENGINE.model_id == "dsv4-flash" and BM._ENGINE.holder == "deep_questions")
    with World(spawn_now=False) as w:
        w.switches(master=True, wiki=True, deep_questions=True)
        BM.lane_for("wiki")
        w.clock += BM._Engine.HOLD_SECONDS + 1        # the wiki job died without release
        BM.lane_for("deep_questions")
        check("a hold nobody refreshed lapses after HOLD_SECONDS",
              len(w.started) == 2 and BM._ENGINE.model_id == "dsv4-flash")
    with World() as w:
        w.switches(master=True, deep_questions=True)
        BM.ask("Why is the sky blue?")
        check("a deep question gives the engine back when it ends",
              BM._ENGINE.holder is None and BM.deep_status()["jobs"][0]["state"] == "done")


def t_the_graphics_card():
    capable = {"capable": True, "uuid": G.U_2060, "name": "NVIDIA GeForce RTX 2060",
               "lane": "off", "why": "the RTX 2060 can take the second-card features"}
    with World(cfg={"cuda": "on"}, second=capable) as w:
        w.switches(master=True, deep_questions=True)
        BM.lane_for("deep_questions")
        env, a = w.started[0].kwargs["env"], w.started[0].args
        check("cuda on, a capable second card, its lane off: pinned to THAT card by its id",
              env["CUDA_VISIBLE_DEVICES"] == G.U_2060 and env["COLI_CUDA"] == "1"
              and "DSV4_CUDA" not in env and a[a.index("--gpu") + 1] == "0")
        check("... and status says which card", "RTX 2060" in BM.status()["cuda"]["why"])
    with World(cfg={"cuda": "on"}, second=dict(capable, lane="running")) as w:
        w.switches(master=True, deep_questions=True)
        check("cuda on, but the second card's own lane is running: refused, no process",
              BM.lane_for("deep_questions") is None and not w.started
              and "running on the NVIDIA GeForce RTX 2060" in BM.status()["engine"]["why"])
    with World(cfg={"cuda": "on"}) as w:
        w.switches(master=True, deep_questions=True)
        check("cuda on, no capable second card: refused; never the main card",
              BM.lane_for("deep_questions") is None and not w.started
              and "never put on the main card" in BM.status()["engine"]["why"])
    with World(cfg={"cuda": "maybe"}) as w:
        check("a cuda value it does not know is 'off'", BM.status()["cuda"]["setting"] == "off")
    # AP-1: the check-then-start race. The second card's lane has taken the
    # card's claim (jarvis_compute) but its state still reads "off".
    import jarvis_compute as CP
    with World(cfg={"cuda": "on"}, second=capable) as w:
        w.switches(master=True, deep_questions=True)
        CP.claim_card(G.U_2060, "second_card")
        try:
            check("the lane's claim alone (it is mid-start): colibri is not started on the card",
                  BM.lane_for("deep_questions") is None and not w.started
                  and BM.engine_card() is None, BM.status()["engine"])
        finally:
            CP.release_card(G.U_2060, "second_card")
    with World(cfg={"cuda": "on"}, second=capable) as w:
        w.switches(master=True, deep_questions=True)
        BM.lane_for("deep_questions")
        check("colibri on the card holds its claim, and engine_card() says which card",
              CP.card_holder(G.U_2060) == "big_model"
              and (BM.engine_card() or {}).get("uuid") == G.U_2060)
        BM.request_change("deep_questions", False)
        check("switched off: colibri stopped and the claim given back",
              CP.card_holder(G.U_2060) is None and BM.engine_card() is None)
    with World() as w:
        w.switches(master=True, deep_questions=True)
        BM.lane_for("deep_questions")
        check("cuda off (the default): colibri holds no card", BM.engine_card() is None
              and CP.card_holder(G.U_2060) is None)


def t_lane_for_is_none_when_not_ready():
    with World() as w:
        check("everything off (the default): None, nothing started",
              BM.lane_for("wiki") is None and not w.started)
        w.switches(master=False, wiki=True)
        check("job on, main switch off: None", BM.lane_for("wiki") is None)
        w.switches(master=True)
        check("main switch on, job off: None", BM.lane_for("wiki") is None and not w.started)
        w.switches(master=True, wiki=True, deep_questions=True)
        for job in ("chat", "voice", "approvals", "long_context", ""):
            check(f"only the two jobs may ask: {job!r} gets None",
                  BM.lane_for(job) is None and not w.started)
        real = BM.detect
        BM.detect = lambda fresh=False: 1 / 0
        try:
            check("never raises", BM.lane_for("wiki") is None)
        finally:
            BM.detect = real
    with World(colibri=False) as w:
        w.switches(master=True, wiki=True)
        check("colibri gone: None, and the choice is kept",
              BM.lane_for("wiki") is None and BM.status()["switches"][0]["enabled"] is True
              and "choice is kept" in BM.status()["switches"][0]["why"])
    with World(spawn_now=False) as w:
        w.switches(master=True, wiki=True)
        check("still loading: None, state loading, with why",
              BM.lane_for("wiki") is None and BM.job_state("wiki")[0] == "loading"
              and "can take several minutes" in BM.job_state("wiki")[1])
    with World(spawn_now=False) as w:
        w.switches(master=True, wiki=True, deep_questions=True)
        BM.lane_for("wiki")
        BM._ENGINE.state = "ready"
        BM._ENGINE.begin()
        check("busy with the other model's job: None, state busy, nothing restarted",
              BM.lane_for("deep_questions") is None and BM.job_state("deep_questions")[0] == "busy"
              and len(w.started) == 1 and not w.killed)
        BM._ENGINE.end()
        BM.lane_for("deep_questions")
        check("its answer is done, but the wiki job has not ended: still not restarted (K2)",
              len(w.started) == 1 and not w.killed
              and BM.job_state("deep_questions")[0] == "busy")
        BM.release("wiki")
        BM.lane_for("deep_questions")
        check("once it is free, it switches model: the old one stopped first",
              len(w.started) == 2 and w.killed == [w.started[0]]
              and BM._ENGINE.model_id == "dsv4-flash")


# ---------------------------------------------------------------- wiki --

def t_the_wiki():
    import test_wiki as TW
    second = SC.Lane("http://127.0.0.1:11435", "qwen3:14b", 16384, "Wiki builder: second card")
    asked_second = []
    saved = SC.lane_for
    SC.lane_for = lambda f: asked_second.append(f) or second
    try:
        with World() as w, TW.Vault():
            check("big model's wiki switch off: the wiki uses the second card's lane",
                  W._lane() is second and not w.started)
            w.switches(master=True, deep_questions=True)
            check("big model on, but not for the wiki: still the second card",
                  W._lane() is second and not w.started)
            w.switches(master=True, wiki=True)
            asked_second.clear()
            lane = W._lane()
            check("big model on for the wiki: ITS lane, and the second card is not asked",
                  isinstance(lane, BM.Lane) and lane.url == "http://127.0.0.1:8765"
                  and asked_second == [], repr(lane))
        with World(spawn_now=False) as w, TW.Vault():
            w.switches(master=True, wiki=True)
            st = W.status()
            check("GET /api/wiki with the big model chosen: available, and it starts nothing",
                  st["available"] is True and "big model" in st["why"] and not w.started, st["why"])
            held = []
            code, body = W.ingest("meeting.md", spawn=lambda fn: held.append(fn))
            check("Add to wiki while colibri loads: 202, state reading, saying it waits",
                  code == 202 and body["state"] == "reading"
                  and "Waiting for the big model" in body["message"], body)
            # It never finishes loading, and then the owner turns the big
            # model off for the wiki: the job fails; it never moves lanes.
            asked_second.clear()
            sleeps = []

            def turn_off(seconds):
                sleeps.append(seconds)
                if len(sleeps) == 2:
                    w.switches(master=True)
            saved_sleep = W._wait_sleep
            W._wait_sleep = turn_off
            try:
                held[0]()
            finally:
                W._wait_sleep = saved_sleep
            _, job = W.ingest_status(body["id"])
            check("switched off while it waited: failed, nothing written, and the second card "
                  "was never asked", job["state"] == "failed" and "switched off" in job["message"]
                  and asked_second == [] and len(sleeps) == 2, job)
        with World(ram=(31.9, 10.0)) as w, TW.Vault():
            w.switches(master=True, wiki=True)
            code, body = W.ingest("meeting.md", spawn=lambda fn: None)
            check("not enough free memory: 503 with the big model's reason, no fallback",
                  code == 503 and "big model" in body["error"] and "24 GB" in body["error"]
                  and asked_second == [], body)
        # The whole job through colibri's (stand-in) API.
        with World() as w, TW.Vault() as v:
            w.switches(master=True, wiki=True)
            bodies = []

            def answer(payload):
                bodies.append(payload)
                sysmsg = payload["messages"][0]["content"]
                obj = TW.ANALYSIS if '"contradictions"' in sysmsg else TW.GOOD
                return "```json\n" + json.dumps(obj) + "\n```"
            w.answer_fn = answer
            cards = []
            code, body = W.ingest("meeting.md", spawn=lambda fn: fn(),
                                  gate_check=lambda a, d, p: cards.append(d) or
                                  TW.Verdict(True, "approved"))
            _, job = W.ingest_status(body["id"])
            check("the wiki job runs on the big model and writes the approved pages",
                  job["state"] == "done" and (v.pages / "Margaret Hale.md").is_file(), job)
            check("two calls, to colibri's /v1/chat/completions, with the key, on loopback",
                  len(bodies) == 2 and all(u == "http://127.0.0.1:8765/v1/chat/completions"
                                           and k == KEY for (m, u, pl, k) in w.http
                                           if u.endswith("/completions")))
            check("no response_format (colibri refuses it for these engines); the schema is "
                  "in the instructions; temperature 0",
                  all("response_format" not in b and "format" not in b
                      and "JSON schema" in b["messages"][0]["content"]
                      and b["temperature"] == 0 and b["stream"] is False for b in bodies))
            check("the card says the big model wrote the plan, on this PC",
                  "The big model (qwen36, run by colibri on this PC)" in cards[0]["text"])
            check("the wiki call's speed is measured",
                  BM.status()["measured"]["wiki"]["words"] > 0)
            check("and the second card was never asked", asked_second == [])
            check("the wiki job gave the engine back when it ended (K2)",
                  BM._ENGINE.holder is None)
        with World() as w, TW.Vault() as v:
            w.switches(master=True, wiki=True)
            w.answer_fn = lambda payload: "Sure! Here are the pages: {not json"
            code, body = W.ingest("meeting.md", spawn=lambda fn: fn(),
                                  gate_check=lambda *a: TW.Verdict(True, "approved"))
            _, job = W.ingest_status(body["id"])
            check("an answer that is not JSON is refused by the same strict validation",
                  job["state"] == "refused" and "not valid JSON" in job["message"]
                  and not (v.pages / "Margaret Hale.md").exists(), job)
        with World() as w, TW.Vault() as v:
            w.switches(master=True, wiki=True)
            w.finish = "length"
            w.answer_fn = lambda payload: json.dumps(TW.ANALYSIS)
            code, body = W.ingest("meeting.md", spawn=lambda fn: fn(),
                                  gate_check=lambda *a: TW.Verdict(True, "approved"))
            _, job = W.ingest_status(body["id"])
            check("an answer cut off at max_tokens is refused (finish_reason length)",
                  job["state"] == "refused" and "ran out of room" in job["message"], job)
    finally:
        SC.lane_for = saved


# ------------------------------------------------------- deep questions --

class _Colibri(BaseHTTPRequestHandler):
    """colibri's gateway in its documented shape (docs/api.md): Bearer auth,
    /v1/models, /v1/chat/completions. Not colibri: a stand-in."""
    key = KEY
    fail = None
    seen = []

    def _auth(self):
        return self.headers.get("Authorization") == f"Bearer {_Colibri.key}"

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        _Colibri.seen.append(("GET", self.path, dict(self.headers)))
        if not self._auth():
            return self._send(401, {"error": {"message": "Invalid or missing API key."}})
        self._send(200, {"object": "list", "data": [{"id": "dsv4-flash", "object": "model"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Colibri.seen.append(("POST", self.path, body))
        if not self._auth():
            return self._send(401, {"error": {"message": "Invalid or missing API key."}})
        if _Colibri.fail:
            return self._send(_Colibri.fail, {"error": {"message": "engine exited"}})
        time.sleep(0.4)          # so there is a time to measure
        self._send(200, {"id": "chatcmpl-x", "object": "chat.completion", "model": body["model"],
                         "choices": [{"index": 0, "finish_reason": "stop",
                                      "message": {"role": "assistant",
                                                  "content": "<think>hmm</think>Rayleigh "
                                                             "scattering: shorter blue "
                                                             "wavelengths scatter more."}}],
                         "usage": {"prompt_tokens": 70, "completion_tokens": 20,
                                   "total_tokens": 90}})

    def log_message(self, *a):
        pass


def t_deep_questions():
    srv = HTTPServer(("127.0.0.1", 0), _Colibri)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with World(real_http=True, cfg={"port": port}) as w:
            code, body = BM.ask("Why is the sky blue?")
            check("switch off: 503, refused, with the reason", code == 503
                  and body["state"] == "refused" and "switch is off" in body["error"])
            w.switches(master=True, deep_questions=True)
            for bad in ("", "   ", None, 5, "x" * (BM.MAX_QUESTION_CHARS + 1)):
                code, body = BM.ask(bad)
                if code != 400:
                    break
            check("an empty, non-text or too-long question: 400", code == 400, (bad, body))
            code, body = BM.ask("Why is the sky blue?", spawn=lambda fn: None)
            check("POST /api/deep/ask: 202, queued, one job",
                  code == 202 and body["state"] == "queued" and body["id"] == "deep_000001")
            st = BM.deep_status()
            check("GET /api/deep lists it queued, with no answer yet",
                  st["jobs"][0]["state"] == "queued" and "answer" not in st["jobs"][0])
            BM.ask("two?", spawn=lambda fn: None)
            BM.ask("three?", spawn=lambda fn: None)
            code, body = BM.ask("four?", spawn=lambda fn: None)
            check("more than three waiting: 409", code == 409 and "already waiting" in body["error"])
            with BM._DEEP_LOCK:
                for jid in list(BM._DEEP)[1:]:
                    BM._DEEP.pop(jid)
            BM._deep_worker()
            st = BM.deep_status()
            job = st["jobs"][0]
            check("answered by the stub on loopback: done, <think> removed",
                  job["state"] == "done" and job["answer"].startswith("Rayleigh scattering"), job)
            check("its speed is recorded: tokens, seconds, tokens and words per second",
                  job["tokens"] == 20 and job["seconds"] >= 0.4 and job["tokens_per_s"]
                  and abs(job["tokens_per_s"] - 20 / job["seconds"]) < 20 / job["seconds"] * 0.3
                  and 0 < job["words_per_s"] < job["tokens_per_s"]
                  and "tokens a second" in job["why"], job)
            post = [s for s in _Colibri.seen if s[0] == "POST"][-1][2]
            check("asked with no tools, no web, no memory: one system and one user message",
                  "tools" not in post and [m["role"] for m in post["messages"]] == ["system", "user"]
                  and post["messages"][1]["content"] == "Why is the sky blue?"
                  and "no tools, no internet" in post["messages"][0]["content"])
            check("every request to the stub carried the key as a Bearer header",
                  all(s[0] == "POST" or s[2].get("Authorization") == f"Bearer {KEY}"
                      for s in _Colibri.seen))
            rows = [json.loads(l) for l in (w.dir / "deep-questions.jsonl").read_text(
                encoding="utf-8").splitlines()]
            check("kept in <config dir>/deep-questions.jsonl, one line, the answer in it",
                  len(rows) == 1 and rows[0]["id"] == "deep_000001"
                  and rows[0]["answer"].startswith("Rayleigh"))
            check("one doorbell event, id and state only - no question, no answer",
                  w.events == [("deep", {"id": "deep_000001", "state": "done"})])
            check("status shows the measured speed", BM.status()["measured"]["deep_questions"]
                  ["tokens"] == 20)
            BM._reset_for_tests()
            check("after a restart the job is still listed, from the file",
                  BM.deep_status()["jobs"][0]["answer"].startswith("Rayleigh")
                  and BM.status()["measured"]["deep_questions"]["tokens_per_s"])
            # Failure, said honestly.
            _Colibri.fail = 500
            BM.ask("And sunsets?")
            job = BM.deep_status()["jobs"][0]
            check("colibri answering 500: failed, 'HTTP 500', no answer",
                  job["state"] == "failed" and "HTTP 500" in job["why"] and "answer" not in job, job)
            _Colibri.fail = None
            _Colibri.key = "not-our-key"
            BM.ask("Again?")
            job = BM.deep_status()["jobs"][0]
            check("a server that does not know our key is not used (401): failed",
                  job["state"] == "failed", job)
            _Colibri.key = KEY
            check("a failure rings the doorbell too", ("deep", {"id": job["id"], "state": "failed"})
                  in w.events)
        with World(real_http=True, cfg={"port": port}) as w:
            w.switches(master=True, deep_questions=True)
            BM.lane_for("deep_questions")
            srv.shutdown()
            srv.server_close()
            BM.ask("Anyone there?")
            job = BM.deep_status()["jobs"][0]
            check("colibri gone mid-way: failed, 'could not be reached'",
                  job["state"] == "failed" and "could not be reached" in job["why"], job)
    finally:
        try:
            srv.shutdown()
        except Exception:
            pass
    with World() as w:
        w.switches(master=True, deep_questions=True)
        lines = [json.dumps({"v": 1, "id": f"deep_old{i:04d}", "question": "q", "state": "done",
                             "answer": "a" * 100, "queued": i}) for i in range(BM.KEEP_JOBS + 5)]
        (w.dir / "deep-questions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        BM.ask("One more?")
        rows = BM._load_deep()
        check(f"the file is capped at {BM.KEEP_JOBS} jobs, oldest dropped",
              len(rows) == BM.KEEP_JOBS and rows[-1]["question"] == "One more?"
              and rows[0]["id"] == "deep_old0006")
        check("GET /api/deep lists at most 20, newest first",
              len(BM.deep_status()["jobs"]) == 20
              and BM.deep_status()["jobs"][0]["question"] == "One more?")
    with World(ram=(31.9, 10.0)) as w:
        w.switches(master=True, deep_questions=True)
        code, body = BM.ask("Now?")
        check("not enough free memory: the question is refused up front, with the numbers",
              code == 503 and "16 GB" in body["error"] and "10 GB is free" in body["error"], body)


# ------------------------------------------------------------- the key --

def t_the_key_is_never_shown():
    with World() as w:
        w.switches(master=True, wiki=True, deep_questions=True)
        seen = []
        BM.request_change("wiki", False)
        BM.request_change("wiki", True, gate=lambda a, d, p: seen.append((d, p)) or
                          Verdict(True, "ask", "approved"))
        BM.lane_for("deep_questions")
        BM.ask("Why?")
        w.chat_error = urllib.error.HTTPError("http://127.0.0.1:8765/v1/chat/completions", 401,
                                              f"bad key {KEY}", None, None)
        BM.ask("Why not?")
        things = [BM.status(), BM.deep_status(), seen, w.audits, w.events,
                  [p.args for p in w.started]]
        log = w.dir / "big-model-engine.log"
        things.append(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
        things.append((w.dir / "deep-questions.jsonl").read_text(encoding="utf-8"))
        things.append((w.dir / "big-model.json").read_text(encoding="utf-8"))
        check("the key is in no status, card, audit line, event, command line, log or file",
              no_key(*things))
        check("... while colibri really was given it", w.started[0].kwargs["env"]["COLI_API_KEY"] == KEY)
        check("repr() of a Lane has no key in it", no_key(repr(BM.lane_for("deep_questions"))))
    check("nothing printed while these tests ran contains the key", no_key(CAPTURED.getvalue()))
    src = (HERE / "jarvis_big_model.py").read_text(encoding="utf-8")
    check("the module never prints or logs anything itself",
          not re.search(r"^\s*print\(", re.sub(r'if __name__ == "__main__":[\s\S]*', "", src), re.M)
          and "logging." not in src)


# ------------------------------------------------------------ the patch --

def _rehearse():
    import _skeleton
    import test_second_card as TS
    git = shutil.which("git")
    d = Path(tempfile.mkdtemp(prefix="jarvis-bm-"))
    try:
        with open(d / "jarvis_hud.py", "w", encoding="utf-8", newline="\n") as f:
            f.write(TS._stand_in())
        (d / "jarvis_gate.py").write_text(
            _skeleton.build("ui-control-wiring.patch", target="jarvis_gate.py"), encoding="utf-8")
        for name, inc in (("note-capture.patch", ["--include=jarvis_gate.py"]),
                          ("second-card.patch", []), ("wiki.patch", [])):
            lf = d / name
            lf.write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
            r = subprocess.run([git, "apply", *inc, str(lf)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"{name}: {r.stderr}", "", "", "", ""
        before = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        gate_before = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        lf = d / "big-model.patch"
        lf.write_bytes((HERE / "big-model.patch").read_bytes().replace(b"\r\n", b"\n"))
        after = gate_after = ""
        for args in (["apply", "--check"], ["apply"], ["apply", "--check", "--reverse"]):
            r = subprocess.run([git, *args, str(lf)], cwd=d, capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"git {' '.join(args)}: {r.stderr}", before, "", gate_before, ""
            if args == ["apply"]:
                after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
                gate_after = (d / "jarvis_gate.py").read_text(encoding="utf-8")
        for name in ("big-model.patch", "wiki.patch", "second-card.patch"):
            r = subprocess.run([git, "apply", "--reverse", str(d / name)], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, f"reverse {name}: {r.stderr}", before, after, gate_before, gate_after
        return True, "", before, after, gate_before, gate_after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_patch():
    if not shutil.which("git"):
        return check("SKIP - git is not installed", True)
    ok, err, before, after, gb, ga = _rehearse()
    check("big-model.patch applies after wiki.patch to what the earlier patches wrote, "
          "reverses, and wiki and second-card still reverse after it", ok, err)
    if not ok:
        return
    i = after.index('if path in ("/api/big-model", "/api/deep"):')
    blk = after[i:i + 1600]
    check("GET /api/big-model and /api/deep check origin and token",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk)
    check("... and answer status() / deep_status()",
          "jarvis_big_model.status()" in blk and "jarvis_big_model.deep_status()" in blk)
    i = after.index('if route in ("/api/big-model", "/api/deep/ask"):')
    blk = after[i:i + 2400]
    check("POST /api/big-model and /api/deep/ask check origin and token and hand the body over",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk
          and "jarvis_big_model.handle_post(body)" in blk
          and "jarvis_big_model.handle_deep_post(body)" in blk)
    check("the routes sit after the wiki's",
          after.index('"/api/wiki"') < after.index('"/api/big-model"')
          and after.index('if route == "/api/wiki/ingest":')
          < after.index('if route in ("/api/big-model"'))
    check("the wiki's blocks are untouched",
          before[before.index('if route == "/api/wiki/ingest":'):].split("\n\n")[0]
          == after[after.index('if route == "/api/wiki/ingest":'):].split("\n\n")[0])
    check("the approval notice knows big_model_enable stays on this PC",
          '"big_model_enable": ("yes", "local",' in ga and '"wiki_update"' in ga)
    for start, end in (('        if path in ("/api/big-model"', '        if path in ("/api/memory/pending"'),
                       ('        if route in ("/api/big-model"', '        if route in ("/api/memory/forget"')):
        block = after[after.index(start):after.index(end)]
        try:
            compile("def f(self, path, route):\n" + block, "<patched block>", "exec")
            check(f"the patched block {start.strip()[:30]}... compiles", True)
        except SyntaxError as exc:
            check(f"the patched block {start.strip()[:30]}... compiles", False, str(exc))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies big-model.patch last, after wiki.patch",
          names and names[-1] == "big-model.patch"
          and names.index("wiki.patch") < names.index("big-model.patch"))
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    check("apply-patches.ps1 copies jarvis_big_model.py in, right after jarvis_wiki.py",
          "'jarvis_big_model.py'" in shipped
          and shipped.index("'jarvis_wiki.py'") < shipped.index("'jarvis_big_model.py'"))
    import _where
    check("_where.SHIPPED has it too, in the same place",
          "jarvis_big_model.py" in _where.SHIPPED
          and _where.SHIPPED.index("jarvis_wiki.py") + 1 == _where.SHIPPED.index("jarvis_big_model.py"))


def t_the_toml():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    check('the shipped toml has big_model_enable = "ask"',
          re.search(r'^big_model_enable\s*=\s*"ask"', toml, re.M) is not None)
    check("and a [big_model] section, with cuda off and 127.0.0.1-only port 8765",
          "\n[big_model]\n" in toml and re.search(r'^cuda = "off"', toml, re.M)
          and re.search(r"^port = 8765", toml, re.M))
    section = toml[toml.index("\n[big_model]\n"):].split("\n[", 2)[1]
    check("no switch lives in it (they are in big-model.json)",
          not re.search(r"^\s*(master|wiki|deep_questions)\s*=", section, re.M))
    import tomllib
    data = tomllib.loads(toml)
    check("it parses, and the models are commented out (nothing is on by default)",
          data["big_model"]["port"] == 8765 and "models" not in data["big_model"])
    example = "\n".join(l[2:] for l in section.splitlines()
                        if l.startswith(("# [[big_model.models]]", "# id =", "# name =",
                                         "# dir =", "# kind =")))
    parsed = tomllib.loads(example)
    check("the commented examples parse once uncommented (single-quoted Windows paths)",
          [m["id"] for m in parsed["big_model"]["models"]] == ["qwen36", "dsv4-flash"]
          and parsed["big_model"]["models"][0]["dir"] == "D:\\models\\qwen36_i4_gs64", parsed)
    try:
        import jarvis_framework as fw
        got = fw.action_tier("big_model_enable")
        check("jarvis_framework reads it as 'ask' from the shipped file", got == "ask", got)
    except Exception as exc:
        check("jarvis_framework reads it", False, repr(exc))


def t_one_line_powershell():
    src = (HERE / "jarvis_big_model.py").read_text(encoding="utf-8")
    m = re.search(r'script = \((.*?)\)\n', src, re.S)
    script = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))) if m else ""
    check("the drive-type check is one PowerShell line, 5.1-safe (no ??)",
          script and "\n" not in script and "??" not in script and "Get-PhysicalDisk" in script)
    pwsh = "/opt/pwsh/pwsh"
    if not os.path.exists(pwsh):
        return check("SKIP - no PowerShell here to parse it", True)
    probe = script.replace("{letter}", "C").replace("{{", "{").replace("}}", "}")
    r = subprocess.run([pwsh, "-NoProfile", "-Command",
                        "$e=$null; [System.Management.Automation.Language.Parser]::ParseInput("
                        f"'{probe.replace(chr(39), chr(39) * 2)}', [ref]$null, [ref]$e) | Out-Null; "
                        "$e.Count"], capture_output=True, text=True, timeout=60)
    check("PowerShell parses it with no errors", r.stdout.strip() == "0", r.stdout + r.stderr)


def t_the_fixture():
    rc = G.main(["--check"])
    check("big-model-cases.json (the desktop's and the phone's copy) equals a fresh run",
          rc == 0, "run python3 tools/gen_big_model_cases.py")
    data = json.loads(G.FIXTURE.read_text(encoding="utf-8"))["cases"]
    states = {data[k]["jobs"][0]["state"] for k in data if k.startswith("deep_") and data[k]["jobs"]}
    check("every deep-question state is in it",
          states >= {"queued", "loading", "thinking", "done", "failed"}, states)
    engines = {data[k]["engine"]["state"] for k in data if k.startswith("status_")}
    check("and every engine state", engines >= {"off", "loading", "ready", "failed"}, engines)
    check("no key in it", no_key(G.FIXTURE.read_text(encoding="utf-8")))


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - no jarvis_hud.py here; the rehearsal above is the proof", True)
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/big-model (big-model.patch applied)",
          '"/api/big-model"' in s)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    # The key check reads what everything before it printed, so it goes last.
    tests.remove(t_the_key_is_never_shown)
    tests.append(t_the_key_is_never_shown)
    for fn in tests:
        sys.__stdout__.write(f"\n--- {fn.__name__} ---\n")
        try:
            # Everything the module (and these tests) print is kept, to grep
            # for the key at the end; check() writes past it.
            with contextlib.redirect_stdout(CAPTURED), contextlib.redirect_stderr(CAPTURED):
                fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc(file=sys.__stdout__)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
