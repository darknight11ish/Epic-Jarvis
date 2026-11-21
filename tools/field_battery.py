#!/usr/bin/env python3
"""run_battery.py - ONE command that field-tests the deployed Jarvis build.

    py -3 .dsh-scratch/wave21/field-battery/run_battery.py

Flags (all optional):

    --self-test          run the offline assertion cases and exit (no HUD, no network)
    --section NAME       run one section only (e.g. --section section_project_chat)
    --allow-stale-cloud  ad-hoc only: run the money rows on a build that is not
                         main, stamp every line "STALE BUILD (override)", exit 2

No arguments runs every section. It prints one PASS / FAIL / SKIP line per
section and a final table, and exits 0 ONLY when every section is PASS or SKIP.

WHAT IT IS FOR
    The owner's top priority (2026-11-18): prove, in a single run, whether the
    build that was just deployed actually works - not whether the code that was
    merged looks right. This script is the repeatable form of tonight's ad-hoc
    probes in .dsh-scratch/wave21/live-card/ (test_hybrid.py,
    retest_private.py, github_battery.py).

THE STALE-BUILD GUARD (the most important line in the script)
    A run BEFORE the deploy would describe the OLD build. Section B reads the
    live backend's own identity (`SOURCE-COMMIT` and `VERSION` beside the
    backend, plus GET /api/self/version as the second witness), compares it
    with origin/main - and with GitHub's own main when `gh` is available - and
    prints exactly:

        STALE BUILD - cloud and feature rows skipped

    Cloud rows never run on a stale build (they spend money). Every feature row
    is additionally gated on whether the deployed build actually contains its
    code, so a row for a merged-but-not-deployed fix is SKIP("not in this
    build"), never a FAIL of a build that was never asked to have it.

MONEY
    Two sections cost money, both cloud sections and nowhere else:
      * C5 (Cloud escalation): one genuinely hard, non-private question sent to
        the chosen cloud provider (deepseek-flash at the shipped prices).
      * EFFICIENCY: up to four hard, non-private questions. It prints the
        expected MAXIMUM spend before sending any of them, and SKIPs without
        spending when the ledger's remaining monthly cap is below that figure,
        when the price table cannot turn the turns into dollars, or when the
        announced maximum would pass a few-cents ceiling. Its ten ordinary
        questions are expected to cost $0.00; an ordinary question that reaches
        the cloud is a FAIL and is named.
    At the shipped prices the whole battery now expects to spend about 1-2
    cents (C5 about $0.003 + up to four EFFICIENCY turns at about $0.004
    each). The expected maximum is printed before it is spent; the actual
    dollars, token counts and the monthly cap are printed after every paid
    turn.
    C6 (Cloud privacy) is a private question and must stay local - it spends
    nothing, and the script checks the ledger did not move.

READ-ONLY
    * The live backend: GETs only, except the cloud chat turns and the chat
      sentences of the feature rows (which create/favourite throwaway notes,
      and are deleted by the script itself).
    * The live config: never written. ~/.openjarvis files are read only,
      including chatbot/api-money.json (the spend ledger).
    * The GitHub battery runs `gh` reads only.
    * The two conversion rows call the DEPLOYED modules in this process
      (module-level, the same code the server loads) and write only inside one
      clearly-marked throwaway folder under Documents, deleted at the end.
    * A token, API key or private fact is never printed.

EACH SECTION, AND WHAT IT PROVES
    PREFLIGHT       the tools this battery needs are present: token, live HUD,
                    live identity files, git, gh, the money ledger, the lanes.
    BUILD           which commit is deployed, and whether it is current.
    C5  Cloud escalation   a hard non-private question really goes to the
                    cloud (X-Jarvis-Route where=cloud, gate=escalate), an
                    answer comes back, and the ledger moved by real dollars.
    EFFICIENCY      does the route escalate only when it should, and what does
                    one escalated turn cost? Ten ordinary, non-private
                    questions must ALL stay where=local - an ordinary question
                    that reaches the cloud is FAIL and is named, because that
                    is money and a rule-1 surface for no benefit. Four hard,
                    non-private questions SHOULD reach where=cloud,
                    gate=escalate; a local one is MISS with the route reason
                    (local is the safe default, but the feature missed). Every
                    escalated turn records wall-clock seconds, the ledger's
                    dollar delta and its prompt/completion token delta, so the
                    section can report cost and seconds per escalated turn and
                    divide them into what is left of the monthly cap. It reads
                    the cap instead of spending to reach it. On a stale build
                    it prints "STALE BUILD - efficiency rows skipped" and
                    spends nothing.
    C6  Cloud privacy      a question naming private material is answered
                    on this PC (where=local, gate=taint) and the ledger does
                    not move. This is the row that failed before #1378.
    GITHUB          the eight GitHub questions from github_battery.py, each
                    checked against ground truth from `gh`. "Plausible" is not
                    a pass: a question answered from the model with the right
                    shape but no data is FAIL(plausible).
    CAPABILITIES    the three measured false-denial questions answer from their
                    catalogue row, not from the model (PR #1377).
    CAP-EXACT       five questions that quote a feature's exact catalogue name
                    resolve to THAT row, not to a shared-word neighbour
                    (PR #1379).
    PRESETS         /api/ps on every lane port; the everyday lane is on its
                    preset model at 196,608 with the spill figure reported
                    (never invented).
    NOTES           one create, one recall in a later turn, throwaway only.
    FAVOURITES      the favourite flag is a resolver tier, later turn (PR
                    #1371); a favourite's CONTENT never being shown to a model
                    is reported NOT-TESTABLE, with the reason.
    CLOUD-SETTINGS  the five cloud-settings questions answer from
                    cloud-choice.json / escalate-cloud.json /
                    chatbot\\api-money.json, naming the file and date, and the
                    values match the files (PR #1376).
    DEFECTS         the defect register count comes from
                    docs/defect-register.tsv and matches the file's own rows;
                    DEF-089 is described from its row (PR #1385).
    PICTURES        two throwaway JPEGs become ONE PDF whose pages are those
                    pictures and whose bytes contain the original JPEG streams;
                    one picture converts to another format (PR #1368).
    AUDIO           a real recording goes through the attach path and is
                    transcribed, with none of the old "(ValueError)" sentence
                    (PR #1366).
    LANE-SERVICE    the deployed jarvis_chatbot_api.lane_service fails closed:
                    an unknown lane gets no service and no URL, the empty name
                    stays local, a real lane still resolves (PR #1384).
    FALLBACK        X-Jarvis-Route carries degraded_from only when a model was
                    substituted; an ordinary local turn omits it (PR #1378).
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
import wave
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
#   Where things live
# ---------------------------------------------------------------------------
LIVE = Path(os.environ.get("JARVIS_BACKEND") or
            (Path(os.environ.get("USERPROFILE") or Path.home())
             / "Documents" / "Claude" / "Open jarvis files" / "Desktop program"))
BASE = "http://127.0.0.1:4719"
GH_REPO = "darknight11ish/Epic-Jarvis"
LANE_PORTS = (11434, 11435, 11436, 11450)
EVERYDAY_PORT = 11436
EVERYDAY_CONTEXT = 196608

HOME = Path.home()
SETTINGS = HOME / ".openjarvis"
VERSION_FILE = LIVE / "VERSION"
SOURCE_COMMIT = LIVE / "SOURCE-COMMIT"
MONEY_FILE = SETTINGS / "chatbot" / "api-money.json"
CLOUD_CHOICE = SETTINGS / "cloud-choice.json"
ESCALATE_FILE = SETTINGS / "escalate-cloud.json"
MODEL_STATE = SETTINGS / "model-state.json"
STATE_FILE = LIVE / "_jarvis-state.json"

#: The checkout this file lives in (…/tools/field_battery.py).
REPO = Path(os.environ.get("JARVIS_REPO") or Path(__file__).resolve().parents[1])
DEFECT_REGISTER = REPO / "docs" / "defect-register.tsv"
DEFECT_CHECKER = REPO / "tools" / "check_defect_register.py"


PORT = 4719

#: Set by --allow-stale-cloud: ad-hoc local testing only. Every line this run
#: prints carries the override stamp, and the process exits 2, so a stale run can
#: never be mistaken for a clean post-deploy pass (ruling 5.5, 2026-11-20).
ALLOW_STALE_CLOUD = {"on": False}

#: Where the phone-facing listener should be, if remote access is configured.
REMOTE_BIND_FILE = LIVE / "jarvis-framework.toml"
REMOTE_BIND_FALLBACK = REPO / "jarvis-backend" / "jarvis-framework.toml"


def remote_bind() -> str:
    """The configured non-loopback bind, or "" when remote access is off.

    Read the same two places the HUD reads (`jarvis_hud._bind_address`):
    the environment first, then `[security].bind_address` in the settings.
    A loopback or empty value means the phone-facing listener is not a thing
    on this install, so the two-address row SKIPs rather than failing.
    """
    env = (os.environ.get("JARVIS_HUD_BIND") or "").strip()
    value = env
    if not value:
        text = ""
        for candidate in (REMOTE_BIND_FILE, REMOTE_BIND_FALLBACK):
            try:
                text = candidate.read_text(encoding="utf-8")
                break
            except OSError:
                continue
        in_section = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_section = stripped == "[security]"
                continue
            if in_section and stripped.startswith("bind_address"):
                value = stripped.split("=", 1)[1].split("#", 1)[0].strip().strip('"\'')
                break
    if value in ("", "127.0.0.1", "localhost", "::1"):
        return ""
    return value


def two_address_verdict(bind: str, local_code: int, remote_code: int) -> tuple:
    """(state, problems) for the two-address check.

    `state` is "off" when remote access is not configured, "ok" when both
    addresses answer, and "broken" otherwise. `problems` names each address
    that did not answer - a phone-facing listener that vanished must never
    look healthy just because localhost still works.
    """
    if not bind:
        return "off", []
    problems = []
    if remote_code == 0:
        problems.append(f"nothing answers on {bind}:{PORT} (the phones are offline)")
    if local_code == 0:
        problems.append(f"nothing answers on 127.0.0.1:{PORT}")
    return ("ok" if not problems else "broken"), problems


def phone_listener_verdict(field) -> tuple:
    """(state, problems) for `/api/status`'s own `phone_listener` field.

    Ruling 5.1 (2026-11-20) makes the HUD the authority on the phone-facing
    listener, because THAT is the process that can see it: the listener is a
    second `jarvis_hud.py` started with `JARVIS_HUD_BIND` in the DESKTOP's
    environment, which this battery cannot read. So when the field exists it is
    read before anything is inferred from settings:

      * `{"configured": true, "listening": false}` -> "broken", and the problem
        names the configured address. This is the outage the row exists for:
        the phones are offline while localhost still looks healthy.
      * `{"configured": true, "listening": true}` -> "ok".
      * `{"configured": false, ...}` -> "off": no phone listener is configured
        on this install, which is an honest SKIP, not a failure.
      * missing/not an object -> "absent": an older HUD that does not publish
        the field. The caller falls back to the settings-based two-address
        check it has always done; absence is never guessed at.
    """
    if not isinstance(field, dict):
        return "absent", []
    if not field.get("configured"):
        return "off", []
    address = str(field.get("bind_address") or "").strip()
    named = address or f"the configured phone address on port {PORT}"
    if field.get("listening"):
        return "ok", []
    return "broken", [f"phone_listener says a listener is configured at {named} "
                      f"but nothing answers there (the phones are offline)"]


def address_answers(host: str, port: int = PORT) -> int:
    """The HTTP status the HUD answers at `host:port`, or 0 when nothing does.

    A 403 (no token) still proves a listener: the question is whether anything
    is listening, not whether the request was authorised.
    """
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=8) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001 - any failure means "nothing answered"
        return 0

#: The four trees that ARE the runtime (the owner's Q6 rule).
RUNTIME_PATHS = ("jarvis-backend/", "jarvis-desktop/src/",
                 "jarvis-desktop/src-tauri/src/", "jarvis-client/app/src/main/")

STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
MARKER = "FIELD-BATTERY-" + datetime.now().strftime("%Y%m%d") + "-" + STAMP[-6:]
ARTIFACT_DIR = HOME / "Documents" / ("FieldBattery-" + STAMP)
VAULT_SCAN_CAP = 5000

DATE_RE = re.compile(r"\b\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\b")
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ASK_WHO_RE = re.compile(
    r"owner/name|owner/repo|full repository name|repository name in the format|"
    r"who owns|github username|your (github )?username|"
    r"provide (the |your )?(repository|repo)|"
    r"(which|what) repositor|confirm (which|the) repo|"
    r"tell me (which|the) repo|need to know (which|the) repo|"
    r"need the (full )?(owner|repository)|which repository it", re.I)
DENY_RE = re.compile(
    r"i (do not|don't) have (any |direct |specific )*(access|a way|that|a file|"
    r"a database|a register)|"
    r"i (do not|don't) know (where|which|what)|"
    r"i (do not|don't) have access|i (can not|cannot|can't) access|"
    r"i (am not|'m not) able to access|no access to|"
    r"i (can not|cannot|can't) (read|see|open|create)", re.I)
DENIAL_WORDS = ("don't have", "do not have", "cannot", "can not", "can't",
                "not able", "no access", "isn't available", "is not available",
                "not available", "unable to")

STATUS_ORDER = ("PASS", "FAIL", "SKIP")


# ---------------------------------------------------------------------------
#   Printing / recording
# ---------------------------------------------------------------------------
class Recorder:
    """One line per check; one summary row per section; a final table."""

    def __init__(self):
        self.rows = []
        self.cur = None

    def header(self, sid, title, requirement=""):
        print("\n" + "=" * 78)
        print(f"[{sid}] {title}" + (f"\n      needs: {requirement}" if requirement else ""))
        self.cur = {"sid": sid, "title": title, "pass": 0, "fail": 0,
                    "miss": 0, "skip": "", "last": ""}

    def info(self, text):
        print("  INFO  " + text)

    def ok(self, name, detail=""):
        self.cur["pass"] += 1
        print("  PASS  " + name + (f" - {detail}" if detail else ""))
        return True

    def expect(self, name, condition, detail=""):
        if condition:
            return self.ok(name, detail)
        self.cur["fail"] += 1
        print("  FAIL  " + name + (f" - {detail}" if detail else ""))
        return False

    def fail(self, name, detail=""):
        return self.expect(name, False, detail)

    def miss(self, name, detail=""):
        """A row the FEATURE missed without the product failing.

        A hard question answered on this PC is the safe default, not a privacy
        or product failure - but it IS a miss of the escalation feature and a
        missing data point, so it is printed as MISS and can never read as a
        PASS. The section still FAILs when a MISS leaves a measurement missing."""
        self.cur["miss"] += 1
        print("  MISS  " + name + (f" - {detail}" if detail else ""))
        return False

    def end(self, verdict, detail=""):
        """Close the current section with an explicit verdict."""
        verdict = verdict if verdict in STATUS_ORDER else "FAIL"
        print(f"  => {verdict}" + (f": {detail}" if detail else ""))
        self.cur["last"] = detail
        self.rows.append({"sid": self.cur["sid"], "title": self.cur["title"],
                          "status": verdict, "detail": detail,
                          "pass": self.cur["pass"], "fail": self.cur["fail"],
                          "miss": self.cur["miss"]})
        self.cur = None

    def skip(self, reason):
        print("  SKIP  " + reason)
        self.end("SKIP", reason)

    def table(self):
        print("\n" + "=" * 78)
        print("FINAL TABLE")
        print("=" * 78)
        width = max([len(r["sid"]) for r in self.rows] + [4])
        for row in self.rows:
            print(f"  {row['status']:<4}  {row['sid']:<{width}}  {row['title']}")
            print(f"          {row['detail']}")
        failed = [r for r in self.rows if r["status"] == "FAIL"]
        skipped = [r for r in self.rows if r["status"] == "SKIP"]
        passed = [r for r in self.rows if r["status"] == "PASS"]
        print("-" * 78)
        print(f"  {len(passed)} PASS, {len(failed)} FAIL, {len(skipped)} SKIP")
        if failed:
            print("  FAILED SECTIONS: " + ", ".join(r["sid"] for r in failed))
            print("  RESULT: NOT PROVEN - see the FAIL lines above")
        else:
            print("  RESULT: every section is PASS or SKIP")
        return 0 if not failed else 1


REC = Recorder()
STATE = {"ready": False, "token": "", "fresh": None, "live_commit": "",
         "live_version": "", "main_sha": "", "headline": "", "stale_reason": ""}


# ---------------------------------------------------------------------------
#   Small utilities
# ---------------------------------------------------------------------------
def norm(text):
    return " ".join(str(text or "").split())


def has(answer, needle):
    return norm(needle).lower() in norm(answer).lower()


def read_text(path, limit=None):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return text[:limit] if limit else text
    except OSError:
        return ""


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="replace")), ""
    except OSError as exc:
        return None, f"{path} could not be read ({type(exc).__name__})"
    except ValueError as exc:
        return None, f"{path} is not valid JSON ({exc})"


def pennies(value):
    try:
        return f"${float(value):,.4f}"
    except (TypeError, ValueError):
        return "$?"


def money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$?"


def dollars6(value):
    """Six decimals: a deepseek turn costs well under a tenth of a cent, and
    rounding that to four places can print a real cost as $0.0000."""
    try:
        return f"${float(value):,.6f}"
    except (TypeError, ValueError):
        return "$?"


def _saved_words(path):
    """'saved 31 Oct 2026' - the same words the deployed cloud-settings answers use.

    Read from the file's own mtime, exactly as jarvis_cloud_settings._saved_words
    does, so the battery compares against the answer's own evidence."""
    try:
        stamp = time.localtime(Path(path).stat().st_mtime)
    except OSError:
        return ""
    return f"saved {stamp.tm_mday} {time.strftime('%b', stamp)} {stamp.tm_year}"


def run(cmd, *, timeout=120, cwd=None):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(cwd) if cwd else None)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{' '.join(cmd[:2])} timed out after {timeout}s"
    except OSError as exc:
        return 126, "", f"{type(exc).__name__}: {exc}"


def git(*args, timeout=60):
    return run(["git", "-C", str(REPO)] + list(args), timeout=timeout)


def gh_json(*args, timeout=120):
    code, out, err = run(["gh"] + list(args), timeout=timeout)
    if code != 0:
        return None, norm(err or out)[:200]
    try:
        return json.loads(out), ""
    except ValueError as exc:
        return None, f"gh output is not JSON ({exc})"


def gh_text(*args, timeout=120):
    code, out, err = run(["gh"] + list(args), timeout=timeout)
    if code != 0:
        return "", norm(err or out)[:200]
    return out.strip(), ""


_live_mods = {}


def live_module(name):
    """Import a module from the DEPLOYED folder (read-only), or (None, why).

    This is how the conversion / audio / lane-service rows exercise the code the
    server actually loads. Importing runs the module body only; it opens no
    socket and writes nothing."""
    if name in _live_mods:
        return _live_mods[name]
    if str(LIVE) not in sys.path:
        sys.path.insert(0, str(LIVE))
    try:
        mod = importlib.import_module(name)
        _live_mods[name] = (mod, "")
        return mod, ""
    except Exception as exc:  # noqa: BLE001 - a state, never a crash
        _live_mods[name] = (None, f"{type(exc).__name__}: {exc}")
        return None, _live_mods[name][1]


def live_text(name):
    return read_text(LIVE / name)


# ---------------------------------------------------------------------------
#   HTTP to the live HUD
# ---------------------------------------------------------------------------
def headers():
    return {"Content-Type": "application/json",
            "X-Jarvis-Token": STATE["token"], "X-Jarvis-Client": "hud"}


def http_json(path, *, method="GET", body=None, timeout=30, use_token=True):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = headers() if use_token else {"Content-Type": "application/json"}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            hd = dict(resp.headers)
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        hd = dict(exc.headers or {})
        status = exc.code
    except Exception as exc:  # noqa: BLE001
        return 0, {}, {}, f"{type(exc).__name__}: {exc}"
    try:
        doc = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        doc = {"raw": raw.decode("utf-8", "replace")[:400]}
    return status, doc, hd, ""


def route_of(hdrs):
    try:
        return json.loads(hdrs.get("X-Jarvis-Route", "{}") or "{}")
    except ValueError:
        return {}


class Turn:
    __slots__ = ("status", "route", "answer", "headers", "secs", "error", "body")

    def __init__(self, **kw):
        for key in self.__slots__:
            setattr(self, key, kw.get(key))


def chat(text, *, timeout=300, attachment=None, provenance=False, project=None):
    """One /api/chat turn. Handles both answer shapes the HUD can send.

    A deterministic fast-path answer comes back as JSON (or plain text); a
    model answer streams as SSE. `provenance: typed` is what the HUD's own page
    sends and is REQUIRED for the deterministic feature rows - without it the
    deployed build falls through to the model (measured 2026-11-18)."""
    message = {"role": "user", "content": text}
    body = {"messages": [message]}
    if project is not None:
        # A chat that belongs to one project (2026-11-20): the id or the name.
        body["project"] = project
    if provenance:
        message["provenance"] = "typed"
        body["provenance"] = "typed"
    if attachment is not None:
        message["attachment"] = attachment
        body["has_file"] = True
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/chat", data=data, method="POST",
                                 headers=headers())
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            hdrs = dict(resp.headers)
            ctype = hdrs.get("Content-Type", "")
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return Turn(status=exc.code, route=route_of(dict(exc.headers or {})),
                    answer=raw[:600], headers=dict(exc.headers or {}),
                    secs=time.time() - started, error=f"HTTP {exc.code}",
                    body=raw)
    except Exception as exc:  # noqa: BLE001
        return Turn(status=0, route={}, answer="", headers={},
                    secs=time.time() - started,
                    error=f"{type(exc).__name__}: {exc}", body="")

    answer = ""
    if "event-stream" in ctype:
        parts = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("data: "):
                continue
            try:
                delta = json.loads(line[6:])
            except ValueError:
                continue
            for choice in delta.get("choices") or []:
                parts.append((choice.get("delta") or {}).get("content") or "")
            if delta.get("error"):
                parts.append(" [stream error] " + str(delta["error"])[:200])
        answer = "".join(parts)
    else:
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = None
        if isinstance(doc, dict):
            choices = doc.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                answer = msg.get("content") or ""
            if not answer:
                for key in ("answer", "text", "reply", "content"):
                    if isinstance(doc.get(key), str):
                        answer = doc[key]
                        break
        if not answer:
            answer = raw.strip()
    return Turn(status=status, route=route_of(hdrs), answer=answer,
                headers=hdrs, secs=time.time() - started, error="", body=raw)


def numbers_in(text):
    out = []
    for match in re.findall(r"#?(\d{3,5})", str(text or "")):
        value = int(match)
        if 100 <= value <= 9999 and not (2020 <= value <= 2035):
            out.append(value)
    return out


def turns_spend_answer(turn):
    """The answer text, or "" when the turn did not really answer."""
    if turn.error:
        return ""
    return (turn.answer or "").strip()


def approve_own_card(token_texts, *, timeout=8.0):
    """Approve ONLY an approval card this battery raised itself.

    A note append is a write and is carded on this PC; the battery's own
    throwaway note is the only card it may ever answer. A card whose detail or
    prompt does NOT name one of `token_texts` is never touched - it is reported
    as not ours instead. Returns (approved, card_id, why).
    """
    wanted = [str(t).lower() for t in token_texts if str(t or "").strip()]
    if not wanted:
        return False, "", "no token to recognise our own card by"
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        status, doc, _, err = http_json("/api/pending", timeout=10)
        if status == 200 and isinstance(doc, dict):
            for card in doc.get("pending") or []:
                if not isinstance(card, dict):
                    continue
                card_id = str(card.get("id") or "")
                blob = " ".join(str(card.get(key) or "")
                                for key in ("detail", "prompt", "action")).lower()
                if card_id:
                    seen.append(card_id)
                if not card_id or not any(token in blob for token in wanted):
                    continue
                code, body, _, why = http_json("/api/approve", method="POST",
                                               body={"id": card_id,
                                                     "by": "field-battery"},
                                               timeout=20)
                ok = isinstance(body, dict) and bool(body.get("ok"))
                return ok, card_id, "" if ok else (why or f"HTTP {code}")
        time.sleep(0.4)
    if seen:
        return False, "", ("cards were waiting but none named our throwaway: "
                           + ", ".join(seen[:4]))
    return False, "", "no approval card appeared"


# ---------------------------------------------------------------------------
#   Live identity and the stale-build guard
# ---------------------------------------------------------------------------
def read_live_identity():
    version = read_text(VERSION_FILE).strip()
    source, why = read_json(SOURCE_COMMIT)
    commit = ref = src_version = ""
    if isinstance(source, dict):
        commit = str(source.get("commit") or "").strip()
        ref = str(source.get("ref") or "").strip()
        src_version = str(source.get("version") or "").strip()
    status, doc, _, err = http_json("/api/self/version")
    app_version = ""
    if status == 200 and isinstance(doc, dict):
        app_version = str(doc.get("app_version") or "").strip()
    return {"version": version, "source_error": why, "commit": commit,
            "ref": ref, "source_version": src_version,
            "app_version": app_version, "http_status": status,
            "http_error": err}


def remote_main_sha():
    """GitHub's own main sha, via `gh --jq` (raw text, never JSON-quoted)."""
    out, why = gh_text("api", f"repos/{GH_REPO}/commits/main", "--jq", ".sha")
    out = (out or "").strip()
    if re.fullmatch(r"[0-9a-f]{40}", out):
        return out, ""
    return "", why or f"unexpected gh answer: {out[:120]}"


def gh_compare_status(base, head):
    """{status, ahead, behind} from GitHub's compare API for two commits."""
    out, why = gh_text("api", f"repos/{GH_REPO}/compare/{base}...{head}", "--jq",
                       '.status, (.ahead_by|tostring), (.behind_by|tostring)')
    lines = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if len(lines) >= 3:
        return {"status": lines[0], "ahead": lines[1], "behind": lines[2]}, ""
    return None, why or f"unexpected compare answer: {(out or '')[:120]}"


def decide_freshness(identity):
    """('FRESH'|'STALE'|'UNKNOWN', detail) for the deployed commit."""
    live = identity.get("commit") or ""
    if not live:
        return "UNKNOWN", "the live SOURCE-COMMIT names no commit"
    _, out, _ = run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet",
                     "origin/main"])
    main_local = (out or "").strip()
    remote, remote_why = remote_main_sha()
    target = remote or main_local
    if not target:
        return "UNKNOWN", ("neither GitHub main nor this checkout's origin/main "
                           "could be read")
    if live == target:
        return "FRESH", f"deployed commit {live[:9]} is main"
    # GitHub's own compare works even when this clone has never seen the commit.
    if remote:
        doc, why = gh_compare_status(live, remote)
        if isinstance(doc, dict):
            status = str(doc.get("status") or "")
            if status == "identical":
                return "FRESH", f"deployed commit {live[:9]} is GitHub main"
            if status == "behind":
                return "FRESH", (f"deployed commit {live[:9]} contains GitHub main "
                                 f"({remote[:9]})")
            if status == "ahead":
                return "STALE", (f"GitHub main is {doc.get('ahead')} commit(s) ahead "
                                 f"of the deployed {live[:9]}")
        else:
            remote_why = why or remote_why
    # Fall back to this checkout: runtime-tree diff is the owner's Q6 rule, so
    # a docs/test/tools-only commit after the deploy is still FRESH.
    resolvable, _, _ = run(["git", "-C", str(REPO), "cat-file", "-e",
                            live + "^{commit}"])
    if resolvable == 0:
        if main_local and live == main_local:
            return "FRESH", f"deployed commit {live[:9]} is this checkout's origin/main"
        # Does live contain local main? (deployed from a newer branch)
        behind, _, _ = run(["git", "-C", str(REPO), "merge-base", "--is-ancestor",
                            main_local, live])
        if behind == 0:
            return "FRESH", (f"deployed commit {live[:9]} contains this checkout's "
                             f"origin/main {main_local[:9]}")
        diff, _, _ = git("diff", "--name-only", f"{live}..{main_local}", "--",
                         *RUNTIME_PATHS)
        changed = [line for line in diff.splitlines() if line.strip()]
        if main_local and not changed:
            return "FRESH", (f"runtime tree identical to origin/main {main_local[:9]} "
                             f"(only non-runtime commits differ)")
        if changed:
            return "STALE", (f"{len(changed)} runtime file(s) differ between the "
                             f"deployed {live[:9]} and main {main_local[:9]} "
                             f"({', '.join(changed[:3])}"
                             f"{' ...' if len(changed) > 3 else ''})")
    return "UNKNOWN", (f"the deployed commit {live[:9]} cannot be compared with "
                       f"main ({remote_why or 'this checkout cannot resolve it'})")


# ---------------------------------------------------------------------------
#   SECTIONS
# ---------------------------------------------------------------------------
def section_preflight():
    REC.header("PREFLIGHT", "the tools this battery needs are present and answering",
               "a HUD token, the live HUD on 4719, the live folder, git, gh, the ledger")
    token = ""
    try:
        if str(LIVE) not in sys.path:
            sys.path.insert(0, str(LIVE))
        import jarvis_token_store  # noqa: E402
        token = jarvis_token_store.resolve(LIVE / "hud-token.txt").token or ""
    except Exception as exc:  # noqa: BLE001
        REC.fail("the HUD token could be resolved", f"{type(exc).__name__}: {exc}")
    else:
        REC.expect("the HUD token could be resolved (never printed)", bool(token))
    STATE["token"] = token

    status, doc, _, err = http_json("/api/version")
    REC.expect("GET /api/version answers", status == 200 and not err,
               f"HTTP {status}" + (f" {err}" if err else ""))
    REC.expect("the live server is jarvis-hud",
               isinstance(doc, dict) and doc.get("server") == "jarvis-hud",
               str((doc or {}).get("server")))

    identity = read_live_identity()
    STATE["live_identity"] = identity
    version_ok = bool(identity["version"]) and identity["version"] == identity["app_version"]
    REC.expect("VERSION beside the backend matches the running HUD's app_version",
               version_ok, f"file {identity['version'] or '?'} vs HTTP "
                           f"{identity['app_version'] or '?'}")
    REC.expect("SOURCE-COMMIT names the deployed commit",
               bool(re.match(r"^[0-9a-f]{7,40}$", identity["commit"] or "")),
               identity["commit"][:12] or identity["source_error"])

    code, out, err = git("rev-parse", "--verify", "--quiet", "origin/main")
    local_main = (out or "").strip() if code == 0 else ""
    REC.expect("this checkout's origin/main is readable", bool(local_main),
               local_main[:12] or norm(err)[:120])
    STATE["local_main"] = local_main

    gh_repo_name, gh_why = gh_text("api", f"repos/{GH_REPO}", "--jq", ".full_name")
    REC.expect("gh is authenticated and reaches the repository",
               (gh_repo_name or "").strip() == GH_REPO,
               gh_why or str(gh_repo_name)[:120])

    ledger, ledger_why = read_json(MONEY_FILE)
    ledger_ok = isinstance(ledger, dict) and isinstance(ledger.get("months"), dict) \
        and isinstance(ledger.get("limits"), dict)
    REC.expect("the spend ledger is readable (read-only)", ledger_ok,
               str(MONEY_FILE) if ledger_ok else ledger_why)

    # THE PHONE-FACING LISTENER (2026-11-20). It is a SECOND HUD process; a
    # restart that loses it leaves the desktop healthy on localhost while both
    # phones are offline - measured twice. Ruling 5.1 makes /api/status the
    # authority, because the HUD that answers can see the listener's own state
    # file and probe the socket; this battery runs in ITS environment and cannot
    # see the desktop's. So the field is read FIRST and trusted when present.
    bind = remote_bind()
    STATE["remote_bind"] = bind
    _pstatus, _pdoc, _, _perr = http_json("/api/status")
    field = (_pdoc or {}).get("phone_listener") if isinstance(_pdoc, dict) else None
    state, problems = phone_listener_verdict(field)
    STATE["phone_listener"] = field
    if state == "ok":
        REC.expect(f"the phone-facing listener at {field.get('bind_address')} "
                   f"answers (reported by /api/status)", True)
    elif state == "broken":
        # FAIL, never SKIP: a configured listener that does not answer is the
        # outage this row was written for, and the problem names the address.
        REC.expect("the phone-facing listener configured on this PC answers",
                   False, "; ".join(problems))
    elif state == "off":
        REC.info("no phone-facing listener is configured on this install "
                 "(/api/status says configured: false), so there is no second "
                 "address to check here")
    elif not bind:
        # An older HUD with no phone_listener key. Fall back to the settings
        # this process can read; a listener started in the desktop's environment
        # is invisible from here, so this remains an honest SKIP.
        REC.info("remote access is not configured in the settings this battery "
                 "can read and /api/status carries no phone_listener field, so "
                 "there is no second address to check here")
    else:
        local_code = address_answers("127.0.0.1")
        remote_code = address_answers(bind)
        two_address_verdict(bind, local_code, remote_code)   # the same shape, kept honest
        REC.expect(f"the phone-facing listener answers on {bind}:{PORT}",
                   remote_code != 0, f"nothing answered on {bind}:{PORT}")
        REC.expect("... and localhost answers alongside it",
                   local_code != 0, f"nothing answered on 127.0.0.1:{PORT}")
        if remote_code == 0:
            REC.info(f"the install is configured for {bind!r} but nothing is "
                     f"listening there - the phones are offline right now")

    reachable = []
    for port in LANE_PORTS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ps",
                                        timeout=8) as resp:
                lane_doc = json.loads(resp.read().decode("utf-8", "replace"))
            loaded = [m.get("name") for m in (lane_doc.get("models") or [])]
            reachable.append((port, loaded, ""))
        except Exception as exc:  # noqa: BLE001
            reachable.append((port, [], f"{type(exc).__name__}"))
    STATE["lanes"] = reachable
    named = [row for row in reachable if row[0] in (11434, 11435, 11436)]
    REC.expect("the three named lanes (11434/11435/11436) answer /api/ps",
               all(not row[2] for row in named),
               "; ".join(f"{p}:{m}" for p, m, e in named if e) or
               "; ".join(f"{p}={','.join(ms) or 'empty'}" for p, ms, _ in named))
    pooled = next(row for row in reachable if row[0] == 11450)
    REC.info(f"11450 (pooled, on demand): "
             f"{'refused - not running' if pooled[2] else (','.join(pooled[1]) or 'empty')}")

    switch, switch_why = read_json(ESCALATE_FILE)
    choice, choice_why = read_json(CLOUD_CHOICE)
    REC.info("standing switch: " +
             ("ON" if isinstance(switch, dict) and switch.get("on") is True
              else "OFF/absent" if switch is not None else "unreadable")
             + f" ({ESCALATE_FILE.name})")
    REC.info("chosen cloud provider: " +
             (str(choice.get("provider")) if isinstance(choice, dict)
              and choice.get("provider") else "none/absent") + f" ({CLOUD_CHOICE.name})")
    STATE["switch_on"] = isinstance(switch, dict) and switch.get("on") is True
    STATE["provider"] = (str(choice.get("provider") or "")
                         if isinstance(choice, dict) else "")

    if REC.cur["fail"]:
        STATE["ready"] = False
        REC.end("FAIL", "preflight failed - the live backend or its tools are not "
                        "all reachable; nothing that depends on them can be proven")
    else:
        STATE["ready"] = True
        REC.end("PASS", f"live {identity['version'] or '?'} at {LIVE.name}; "
                        f"{len(named)} named lanes answering")



def stale_decision(state: str, allow_override: bool) -> tuple:
    """(verdict, stamped sentence) for BUILD's freshness.

    `state` is `decide_freshness`'s own answer ("FRESH"/"STALE"/"UNPROVEN").
    A stale build SKIPs the cloud rows by default, because they spend money and
    would describe a build that is not the commit under test. `--allow-stale-cloud`
    runs them anyway for ad-hoc local testing, and then every sentence carries
    "STALE BUILD (override)" so the run cannot read as a clean pass.
    """
    if state == "FRESH":
        return "pass", "the deployed build is current"
    if state == "STALE":
        if allow_override:
            return "override", ("STALE BUILD (override) - the cloud and feature "
                                "rows ran against a build that is not main")
        return "skip", "STALE BUILD - cloud and feature rows skipped"
    return "fail", "build identity unproven"

def section_build():
    REC.header("BUILD", "which commit is deployed, and is it the build to test",
               "the live VERSION/SOURCE-COMMIT and main")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    identity = STATE.get("live_identity") or read_live_identity()
    live = identity["commit"]
    version_ok = bool(identity["version"]) and identity["version"] == identity["app_version"]
    REC.expect("the running HUD is the code in this live folder",
               version_ok,
               f"VERSION {identity['version'] or '?'} / HTTP "
               f"{identity['app_version'] or '?'}")
    state, detail = decide_freshness(identity)
    STATE["fresh"] = (state == "FRESH")
    STATE["stale_reason"] = "" if state == "FRESH" else detail
    STATE["live_commit"] = live
    STATE["live_version"] = identity["version"]
    remote, remote_why = remote_main_sha()
    STATE["remote_main"] = remote or ""
    REC.info(f"deployed: {live[:12] or '?'} (VERSION {identity['version'] or '?'}, "
             f"ref {identity['ref'] or '?'}); main is read fresh each run, so a "
             f"merge during the run can move it for a later row")
    REC.info(f"main: GitHub {str(STATE.get('remote_main') or remote_why or '?')[:12]} / "
             f"this checkout {str(STATE.get('local_main') or '?')[:12]}")
    verdict, stamped = stale_decision(state, ALLOW_STALE_CLOUD["on"])
    if verdict == "pass":
        REC.ok(stamped, detail)
        REC.end("PASS", detail)
    elif verdict == "skip":
        print("\n  *** STALE BUILD - cloud and feature rows skipped ***")
        print(f"      {detail}")
        REC.info("cloud turns will NOT be sent (they would describe the old build)")
        REC.info("feature rows are gated on their own code being in this build")
        REC.info("--allow-stale-cloud runs them anyway, and stamps every line")
        REC.end("SKIP", f"STALE BUILD - {detail}")
    elif verdict == "override":
        STATE["fresh"] = True
        STATE["stale_override"] = detail
        print("\n  *** STALE BUILD (override) - cloud and feature rows WILL run ***")
        print(f"      {detail}")
        REC.info("this run is NOT a clean post-deploy pass; it exits 2")
        REC.ok("the deployed build is current - OVERRIDE ACCEPTED", detail)
        REC.end("PASS", f"STALE BUILD (override): {detail}")
    else:
        REC.fail("the deployed build's freshness can be determined", detail)
        print("\n  *** STALE BUILD - cloud and feature rows skipped (identity unproven) ***")
        REC.end("FAIL", f"build identity unproven: {detail}")


def _cloud_preconditions():
    """(ok, reason) for a cloud turn - switch, provider, cap."""
    switch, why = read_json(ESCALATE_FILE)
    if not isinstance(switch, dict) or switch.get("on") is not True:
        return False, ("the standing escalation switch is off/absent "
                       f"(escalate-cloud.json: {why or 'not on'}) - a cloud turn "
                       "would wait for a yes this script cannot give")
    choice, _ = read_json(CLOUD_CHOICE)
    provider = str((choice or {}).get("provider") or "") if isinstance(choice, dict) else ""
    if not provider:
        return False, "no cloud provider is chosen in cloud-choice.json"
    ledger, why = read_json(MONEY_FILE)
    if not isinstance(ledger, dict):
        return False, f"the spend ledger cannot be read ({why}), so spend is unprovable"
    return True, ""


def _ledger_totals(ledger):
    months = (ledger or {}).get("months") or {}
    month = datetime.now().strftime("%Y-%m")
    rows = months.get(month) or {}
    dollars = rounded = 0.0
    requests = 0
    services = []
    for pid, row in (rows.items() if isinstance(rows, dict) else ()):
        if not isinstance(row, dict):
            continue
        try:
            dollars += float(row.get("dollars") or 0.0)
            requests += int(row.get("requests") or 0)
        except (TypeError, ValueError):
            continue
        services.append(pid)
    return {"month": month, "dollars": dollars, "requests": requests,
            "services": services, "rows": rows}


def _ledger_provider_row(ledger, provider, month=""):
    """This month's own row for ONE provider, or {} when it has no row yet.

    C5 asks whether the ledger moved at all; EFFICIENCY has to attribute a
    single turn's dollars and tokens to the service that answered it, so it
    reads the provider's own row and refuses to guess when the movement lands
    under a different service id."""
    months = (ledger or {}).get("months") or {}
    month = month or datetime.now().strftime("%Y-%m")
    rows = months.get(month) or {}
    row = rows.get(provider) if isinstance(rows, dict) else None
    return (row if isinstance(row, dict) else {}), month


def _ledger_cap(ledger, provider):
    limits = (ledger or {}).get("limits") or {}
    if provider and provider in limits:
        return limits[provider], provider
    if len(limits) == 1:
        return next(iter(limits.values())), next(iter(limits))
    return None, ""


def section_cloud_escalation():
    REC.header("C5", "cloud escalation actually escalates, answers, and costs money",
               "a fresh build, escalation switch ON, a provider chosen, a readable ledger")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    if STATE["fresh"] is not True:
        return REC.skip("STALE BUILD - a cloud turn now would describe the old build "
                        "(and spend money on it)")
    ok, reason = _cloud_preconditions()
    if not ok:
        return REC.skip(reason)
    ledger_before, why = read_json(MONEY_FILE)
    if not isinstance(ledger_before, dict):
        REC.fail("the ledger is readable before the turn", why)
        return REC.end("FAIL", "cannot prove spend moved")
    before = _ledger_totals(ledger_before)
    cap, cap_service = _ledger_cap(ledger_before, STATE.get("provider"))
    prices = ((ledger_before.get("prices") or {}).get(STATE.get("provider") or "")
              or {})
    estimate = ""
    for model, row in (prices.items() if isinstance(prices, dict) else ()):
        try:
            est = (float(row.get("in", 0)) * 1500 + float(row.get("out", 0)) * 400) / 1e6
        except (TypeError, ValueError):
            continue
        estimate = f"about {pennies(est)} at {STATE.get('provider')}'s own prices ({model})"
        break
    print(f"\n  THIS IS ONE OF THE BATTERY'S TWO PAID SECTIONS (the other is EFFICIENCY).")
    print(f"  Expect: one hard answer; {estimate or 'a fraction of a cent'}.")
    print(f"  Cap: {money(cap) if cap is not None else 'no cap set'} per month "
          f"({cap_service or 'service'}). Ledger read before/after, never written.")
    hard = ("Prove by induction that the sum of the first n odd numbers equals n squared. "
            "Then explain carefully, for a beginner, why the induction step is legitimate "
            "rather than circular, and give one counterexample-shaped argument that would "
            "fail if the claim were changed to even numbers.")
    turn = chat(hard, timeout=300)
    REC.expect("the hard question got an HTTP answer", turn.status == 200 and not turn.error,
               f"HTTP {turn.status} {turn.error}".strip())
    answer = turns_spend_answer(turn)
    REC.expect("an answer came back", bool(answer), f"{len(answer)} characters")
    STATE["c5_answer_len"] = len(answer or "")
    route = turn.route or {}
    # EFFICIENCY reads this: if C5 already measured a hard question REFUSED by
    # the route, there is no point spending four more turns to prove the same
    # refusal - and no way to measure cost per escalated turn from it.
    STATE["c5_route"] = {k: route.get(k) for k in ("lane", "where", "gate", "reason")
                         if k in route}
    REC.info("X-Jarvis-Route: " + json.dumps(
        {k: route.get(k) for k in ("lane", "where", "gate", "reason", "offer")
         if k in route}, ensure_ascii=False)[:400])
    REC.expect("the route says it went to the cloud", route.get("where") == "cloud",
               f"where={route.get('where')!r}")
    REC.expect("the route gate is escalate, not offer", route.get("gate") == "escalate",
               f"gate={route.get('gate')!r}")

    ledger_after, why = read_json(MONEY_FILE)
    spent, new_requests = 0.0, 0
    if not isinstance(ledger_after, dict):
        REC.fail("the ledger is readable after the turn", why)
    else:
        after = _ledger_totals(ledger_after)
        spent = round(after["dollars"] - before["dollars"], 6)
        new_requests = after["requests"] - before["requests"]
        REC.expect("the spend ledger moved", spent > 0 or new_requests > 0,
                   f"dollars +{pennies(spent)}, requests +{new_requests}")
        REC.info(f"this turn cost about {pennies(spent)}; this month now "
                 f"{money(after['dollars'])} ({after['requests']} answer(s)) of "
                 f"the {money(cap) if cap is not None else 'no-cap'} cap")
    if REC.cur["fail"]:
        REC.end("FAIL", "the cloud escalation row did not prove itself")
    else:
        REC.end("PASS", "where=cloud, gate=escalate, an answer came back, and the "
                        f"ledger moved by ~{pennies(spent)}")


def section_cloud_privacy():
    REC.header("C6", "a question naming private material stays on this PC",
               "a fresh build (free - this turn must not spend)")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    if STATE["fresh"] is not True:
        return REC.skip("STALE BUILD - the privacy row's fix (#1378) may not be in "
                        "the old build, so its answer would describe the old build")
    ledger_before, _ = read_json(MONEY_FILE)
    before = _ledger_totals(ledger_before) if isinstance(ledger_before, dict) else None
    private = ("My email password is in my notes, and this is about my medical history. "
               "Summarise what you already know about my health from my private files.")
    turn = chat(private, timeout=300)
    answer = turns_spend_answer(turn)
    REC.expect("the private question got an HTTP answer",
               turn.status == 200 and not turn.error,
               f"HTTP {turn.status} {turn.error}".strip())
    REC.expect("an answer came back (the pre-#1378 failure was NO answer)",
               bool(answer), f"{len(answer)} characters")
    route = turn.route or {}
    REC.info("X-Jarvis-Route: " + json.dumps(
        {k: route.get(k) for k in ("lane", "where", "gate", "reason", "tainted")
         if k in route}, ensure_ascii=False)[:400])
    REC.expect("the route says it stayed local", route.get("where") == "local",
               f"where={route.get('where')!r}")
    REC.expect("the route gate is taint", route.get("gate") == "taint",
               f"gate={route.get('gate')!r}")
    ledger_after, _ = read_json(MONEY_FILE)
    after = _ledger_totals(ledger_after) if isinstance(ledger_after, dict) else None
    if before is not None and after is not None:
        REC.expect("the ledger did NOT move - nothing left the PC",
                   after["requests"] == before["requests"]
                   and round(after["dollars"] - before["dollars"], 6) == 0,
                   f"requests {before['requests']} -> {after['requests']}")
    if REC.cur["fail"]:
        REC.end("FAIL", "the private question did not prove it stayed on this PC")
    else:
        REC.end("PASS", "where=local, gate=taint, answered, and no cloud spend was added")


# ---------------------------------------------------------------------------
#   EFFICIENCY - only-when-it-should, and the price of it happening
# ---------------------------------------------------------------------------
#: The two question sets are FIXED, hand-picked, and written down BEFORE any
#: answer is seen, each with the reason it is in the set. A set chosen after
#: seeing what escalated would prove nothing.
#:
#: The literal "make a note" and "set a timer" requests are deliberately
#: represented by their READ-ONLY shapes: this section may not write, and a real
#: note append is a carded write the battery must not need. A real timer would
#: be a live action left running; a real weather fetch IS kept, because it is
#: the owner's own example and the deployed quick lane answers it on this PC.
#:
#: ORDINARY - every one of these must stay `where: local`. An ordinary question
#: that reaches a paid lane is money spent and a rule-1 surface opened for no
#: benefit, so it is a FAIL and is named in the output.
EFFICIENCY_ORDINARY = (
    ("What's the weather like today?",
     "weather - the owner's own example, answered by the deployed quick lane on "
     "this PC"),
    ("What timers do I have running right now?",
     "a timer state read - an everyday request that must not buy an answer"),
    ("What is a semicolon?",
     "a short definition - small talk the local model exists to answer for free"),
    ("What are notes for in Jarvis?",
     "a note-shaped product question - it reads and writes no note (read-only)"),
    ("What is 17 times 24?",
     "arithmetic - a checkable answer that costs nothing to make on this PC"),
    ("What's the capital of Australia?",
     "a schoolroom fact - exactly what an 8B local model answers well"),
    ("What day of the week is 1 January 2027?",
     "date arithmetic - a deterministic local answer, no reasoning to pay for"),
    ("Tell me a short joke about penguins.",
     "a tiny creative request - ordinary local-model work, not cloud work"),
    ("What does the word serendipity mean?",
     "a one-word definition - another ordinary local answer"),
    ("How many minutes are in a day?",
     "a unit conversion - ordinary arithmetic, and it keeps the word 'how' (a "
     "scorer cue) inside an ordinary question"),
)

#: HARD - each is non-private on purpose and hard on purpose: multi-step
#: reasoning, a proof, or a long exact calculation. One answered locally is not
#: a product failure (local is the safe default) - it is a MISS of the feature
#: and is printed as MISS with the route's own reason.
EFFICIENCY_HARD = (
    ("Prove by induction that the sum of the first n odd numbers equals n squared. "
     "Then explain carefully, for a beginner, why the induction step is legitimate "
     "rather than circular, and give one counterexample-shaped argument that would "
     "fail if the claim were changed to even numbers.",
     "a multi-step induction proof - the same question C5 uses, so a matching "
     "escalation shows the two sections agree about what 'hard' is"),
    ("A train leaves at 09:15 travelling at 85 kilometres per hour. A second train "
     "leaves the same station at 10:00 at 110 kilometres per hour in the same "
     "direction. Calculate, step by step, when and where the second train catches "
     "the first, and show the algebra for both trains.",
     "a multi-part word problem with an explicit step-by-step demand - real "
     "multi-step reasoning and nothing private in it"),
    ("Explain why the halting problem is undecidable, and outline the "
     "diagonalisation argument that proves it, step by step, in enough detail that "
     "a beginner could reproduce the proof.",
     "a proof by contradiction explained at length - textbook-hard, non-private"),
    ("Work through this long multiplication step by step: 12,345,679 multiplied by "
     "987,654,321. Then divide the product by 7 and state the exact remainder, and "
     "verify the remainder using modular arithmetic.",
     "the 'long calculation' shape - a big exact computation whose answer can be "
     "checked, and too long for the deterministic quick lane to answer for free"),
)

#: What this section may spend, in dollars. The announced maximum is turns x
#: cost per turn; CEILING is the line above which the section refuses to start
#: at all; STOP is a running guard that finishes the measurement it already has
#: rather than cross a few cents. All three are deliberately small.
EFF_CEILING_DOLLARS = 0.05
EFF_STOP_DOLLARS = 0.04

#: The token figures the per-turn estimate prices in. Deliberately generous: a
#: MAXIMUM, so a run that beats it is inside the promise, and one that exceeds
#: it FAILs rather than quietly costing more than the owner was told.
EFF_EST_PROMPT_TOKENS = 1500
EFF_EST_COMPLETION_TOKENS = 3000

#: How long to wait for `record_spend` to land in the ledger after a turn ends.
#: `jarvis_speed.Meter.finish` records on the answer's own thread, so the write
#: can be a moment behind the last streamed byte. Polling is free (it reads a
#: small JSON file); a turn that never appears is a missing measurement, never
#: a $0.00 answer.
EFF_LEDGER_SETTLE_SECS = 8.0

#: The exact words the stale-build guard prints for this section. The em dash is
#: the owner's own wording; the SKIP line and the README quote it.
EFF_STALE_WORDS = "STALE BUILD \u2014 efficiency rows skipped"


def _eff_taint_state():
    """(active, words) for the PC's process-wide cloud-refusal latch, READ-ONLY.

    The latch is the privacy rule working: after a private read (notes, email, a
    file) the shipped router refuses the cloud until it expires, so a run made
    while it is active cannot measure escalation at all - every hard question
    would correctly go local and cost nothing. The section therefore SKIPs
    instead of pretending that is a routing result.

    Read straight out of the gate's own SQLite file with `mode=ro`, because
    `jarvis_gate.taint_active()` INITIALISES that database - a write this
    section must never make. The in-memory fallback the server keeps when its
    database write failed is invisible here; if it is the reason, the MISS lines
    below say `gate='taint'` and the section reports that."""
    # The same folder jarvis_framework.CONFIG_DIR resolves to, without importing
    # it (an import here would only be a side effect risk; the rule is four
    # lines in jarvis_framework.py:77-84 and replicated exactly).
    base = SETTINGS
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        base = Path(os.path.expanduser(env))
    db = base / "approvals.db"
    try:
        conn = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT until, why FROM taint WHERE key='conversation'").fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - a state, never a crash
        return None, f"{db} could not be read ({type(exc).__name__}: {exc})"
    if not row:
        return False, ""
    try:
        until = float(row[0])
    except (TypeError, ValueError):
        return None, "the taint latch row has no readable expiry"
    if until <= time.time():
        return False, ""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(until))
    why = str((row[1] if len(row) > 1 else "") or "unsaid")[:60]
    return True, f"a private read latched taint until {stamp} (why: {why})"


def _eff_snapshot(provider):
    """(snapshot, why) for the chosen provider's own row in this month's ledger.

    The row carries everything a single turn is measured against: dollars,
    requests, prompt/completion tokens and the unpriced counter. The cap is read
    from the same ledger, so the two can never disagree about what was spent."""
    ledger, why = read_json(MONEY_FILE)
    if not isinstance(ledger, dict):
        return None, why or "the spend ledger is not a JSON object"
    row, month = _ledger_provider_row(ledger, provider)
    try:
        snap = {"month": month, "provider": provider, "row_present": bool(row),
                "dollars": float(row.get("dollars") or 0.0),
                "requests": int(row.get("requests") or 0),
                "prompt_tokens": int(row.get("prompt_tokens") or 0),
                "completion_tokens": int(row.get("completion_tokens") or 0),
                "unpriced": int(row.get("unpriced") or 0)}
    except (TypeError, ValueError) as exc:
        return None, f"the ledger row for {provider} is not numeric ({exc})"
    cap, cap_service = _ledger_cap(ledger, provider)
    say = ((ledger.get("months") or {}).get(month) or {})
    snap["cap"] = cap
    snap["cap_service"] = cap_service
    snap["services"] = sorted(say.keys()) if isinstance(say, dict) else []
    return snap, ""


def _eff_delta(before, after):
    """What one turn added to the ledger, field by field (after - before)."""
    return {
        "dollars": round(float(after["dollars"]) - float(before["dollars"]), 8),
        "requests": after["requests"] - before["requests"],
        "prompt_tokens": after["prompt_tokens"] - before["prompt_tokens"],
        "completion_tokens": after["completion_tokens"] - before["completion_tokens"],
        "unpriced": after["unpriced"] - before["unpriced"],
    }


def _eff_stable_snapshot(provider, *, settle=3.0):
    """A snapshot that has not changed across a short wait.

    C5 spends one turn just before this section, and its ledger write can land
    a moment after its answer ends. Reading a settled baseline here keeps that
    earlier turn out of the ordinary set's "did anything move" check."""
    first, why = _eff_snapshot(provider)
    if first is None:
        return None, why
    deadline = time.time() + settle
    while time.time() < deadline:
        time.sleep(0.5)
        again, why = _eff_snapshot(provider)
        if again is None:
            return None, why
        keys = ("dollars", "requests", "prompt_tokens", "completion_tokens")
        if all(again[k] == first[k] for k in keys):
            return again, ""
        first = again
    return first, ""


def _eff_wait_for_ledger(provider, before, *, timeout=None):
    """(snapshot, why): the ledger after THIS turn's request is recorded.

    Polling never spends money; it only re-reads the ledger. A request that
    never appears means the turn's cost is not attributable from the ledger,
    which is a missing measurement - not a $0.00 turn."""
    timeout = EFF_LEDGER_SETTLE_SECS if timeout is None else timeout
    deadline = time.time() + timeout
    snap, why = before, ""
    while True:
        snap, why = _eff_snapshot(provider)
        if snap is not None and snap["requests"] > before["requests"]:
            return snap, ""
        if time.time() >= deadline:
            return snap, why
        time.sleep(0.5)


def _eff_estimate(ledger, provider, turns):
    """What `turns` escalated turns are expected to cost AT MOST.

    The larger of two honest figures:
      * the ledger's own price for the provider applied to a generous token
        budget (EFF_EST_PROMPT_TOKENS + EFF_EST_COMPLETION_TOKENS), and
      * the ledger's measured average dollars per completed request this month,
        when it has one.
    A zero figure means the ledger cannot price this provider at all; the caller
    refuses to run on that rather than announce "$0.00, probably"."""
    prices = ((ledger or {}).get("prices") or {}).get(provider) or {}
    per, model, in_price, out_price = 0.0, "", 0.0, 0.0
    for name, row in (prices.items() if isinstance(prices, dict) else ()):
        try:
            price_in = float(row.get("in", 0))
            price_out = float(row.get("out", 0))
            est = (price_in * EFF_EST_PROMPT_TOKENS
                   + price_out * EFF_EST_COMPLETION_TOKENS) / 1e6
        except (TypeError, ValueError):
            continue
        if est > per or not model:
            per, model, in_price, out_price = est, name, price_in, price_out
    row, _ = _ledger_provider_row(ledger, provider)
    observed = 0.0
    try:
        requests = int(row.get("requests") or 0)
        if requests > 0:
            observed = float(row.get("dollars") or 0.0) / requests
    except (TypeError, ValueError):
        observed = 0.0
    if observed > per:
        per = observed
    return {"per_turn": per, "observed": observed, "total": per * turns,
            "turns": turns, "model": model,
            "in_price": in_price, "out_price": out_price}


def section_cloud_efficiency():
    REC.header(
        "EFFICIENCY",
        "does the route escalate only when it should, and what does one escalated "
        "turn cost and take?",
        "a fresh build, escalation switch ON, a chosen provider, a readable ledger "
        "with a cap and a price, no active taint latch")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    if STATE["fresh"] is not True:
        print("\n  *** " + EFF_STALE_WORDS + " ***")
        print(f"      {STATE.get('stale_reason') or 'the deployed build is not main'}")
        print("      no ordinary and no paid turn is sent: the cost of the OLD route "
              "would describe the old build")
        return REC.skip(EFF_STALE_WORDS + " - " +
                        (STATE.get("stale_reason") or "not a fresh build"))
    ok, reason = _cloud_preconditions()
    if not ok:
        return REC.skip(reason)
    provider = STATE.get("provider") or ""
    if not provider:
        return REC.skip("no cloud provider is chosen in cloud-choice.json")

    # A hard question cannot escalate through the PC's privacy latch - and that
    # is the rule working, not a routing answer. Do not spend to discover it.
    latched, latch_words = _eff_taint_state()
    if latched is None:
        return REC.skip(f"cannot tell whether this PC's cloud-refusal latch is on "
                        f"({latch_words}) - no money spent on measurements that may "
                        f"only prove the latch")
    if latched:
        return REC.skip(f"the PC's taint latch is active ({latch_words}); the shipped "
                        f"router refuses the cloud while it lasts, so cost per "
                        f"escalated turn cannot be measured - rerun after it expires")

    # If C5 already measured a hard question REFUSED by the route, four more
    # turns would spend money to prove the same refusal and still leave the cost
    # unmeasured. Say so and spend nothing.
    c5 = STATE.get("c5_route") or {}
    if c5 and (c5.get("where") != "cloud" or c5.get("gate") != "escalate"):
        return REC.skip(f"C5 already measured a hard question refused by the route "
                        f"(where={c5.get('where')!r}, gate={c5.get('gate')!r}); the "
                        f"same refusal would leave cost per escalated turn unmeasured "
                        f"- nothing sent")

    before, why = _eff_stable_snapshot(provider)
    if before is None:
        return REC.skip(f"the spend ledger cannot be read ({why}) - spend is unprovable")
    ledger, why = read_json(MONEY_FILE)
    if not isinstance(ledger, dict):
        return REC.skip(f"the spend ledger cannot be read ({why}) - spend is unprovable")
    est = _eff_estimate(ledger, provider, len(EFFICIENCY_HARD))
    if est["per_turn"] <= 0:
        return REC.skip(f"the ledger has no usable price for {provider}, so the "
                        f"expected maximum spend cannot be stated - nothing sent")
    cap = before["cap"]
    try:
        cap_value = float(cap)
    except (TypeError, ValueError):
        return REC.skip(f"the ledger sets no numeric monthly cap for {provider}, so "
                        f"'does the budget stop it' cannot be answered and the spend "
                        f"would be unbounded - nothing sent")
    remaining = cap_value - float(before["dollars"])

    print(f"\n  THIS SECTION SPENDS MONEY: up to {len(EFFICIENCY_HARD)} escalated "
          f"turn(s), and no other turn is expected to cost anything.")
    print(f"  Announced maximum: {len(EFFICIENCY_HARD)} turn(s) x "
          f"{dollars6(est['per_turn'])} = {pennies(est['total'])} "
          f"(ceiling for this section {money(EFF_CEILING_DOLLARS)}; it stops "
          f"sending once {money(EFF_STOP_DOLLARS)} has really been spent).")
    print(f"  Per-turn figure: the larger of the ledger's price for {provider}"
          f"{('/' + est['model']) if est['model'] else ''} "
          f"(${est['in_price']:.2f}/M in, ${est['out_price']:.2f}/M out) applied to "
          f"{EFF_EST_PROMPT_TOKENS:,} prompt + {EFF_EST_COMPLETION_TOKENS:,} "
          f"completion tokens, and the ledger's measured average per request "
          f"({dollars6(est['observed']) if est['observed'] else 'none recorded yet'}).")
    print(f"  Cap: {money(cap_value)} per month on {before['cap_service'] or provider}; "
          f"already spent {pennies(before['dollars'])}; remaining {pennies(remaining)}.")
    if est["total"] > EFF_CEILING_DOLLARS:
        return REC.skip(f"the announced maximum {pennies(est['total'])} is above this "
                        f"section's {money(EFF_CEILING_DOLLARS)} ceiling - nothing sent "
                        f"(raise EFF_CEILING_DOLLARS deliberately if the owner wants a "
                        f"bigger measurement)")
    if remaining < est["total"]:
        return REC.skip(f"the remaining monthly cap {pennies(remaining)} is below the "
                        f"announced maximum {pennies(est['total'])} - nothing sent")
    REC.info(f"guard passed: remaining {pennies(remaining)} >= announced maximum "
             f"{pennies(est['total'])}; the {len(EFFICIENCY_ORDINARY)} ordinary "
             f"questions are expected to cost $0.00")

    # ---- 1. ordinary questions: all of them must stay local -----------------
    print(f"\n  --- 1. ordinary questions ({len(EFFICIENCY_ORDINARY)}) - each must stay "
          f"where=local, at $0.00 ---")
    ordinary_local = 0
    ordinary_cloud = []
    for index, (question, why_it_is_here) in enumerate(EFFICIENCY_ORDINARY, 1):
        # `provenance: typed` is what the HUD's own page sends for a typed
        # question, and it lets the deployed deterministic lane answer the
        # everyday shapes (weather, timer state) instead of a local model.
        # It cannot change the ROUTE: choose() runs on the question text before
        # that lane is consulted, so this only makes the ordinary set behave
        # like real typing while keeping the measurement about routing.
        turn = chat(question, timeout=300, provenance=True)
        route = turn.route or {}
        where, gate = route.get("where"), route.get("gate")
        print(f"  Q{index}: {question}")
        print(f"       why it is ordinary: {why_it_is_here}")
        print(f"       HTTP {turn.status}{(' ' + turn.error) if turn.error else ''} in "
              f"{turn.secs:.1f}s  where={where!r} gate={gate!r} "
              f"complexity={route.get('complexity')!r} quick={route.get('quick')!r} "
              f"answer={len(turn.answer or '')}ch")
        if turn.status != 200 or turn.error:
            REC.fail(f"ordinary question {index} got an HTTP answer",
                     f"HTTP {turn.status} {(turn.error or '').strip()}")
        elif where == "local":
            ordinary_local += 1
            REC.ok(f"ordinary question {index} stayed local", f"gate={gate!r}")
        elif where == "cloud":
            ordinary_cloud.append(index)
            REC.fail(f"ordinary question {index} WENT TO THE CLOUD",
                     f"where=cloud gate={gate!r} - money spent and a rule-1 surface "
                     f"opened for no benefit")
        else:
            REC.fail(f"ordinary question {index} has a usable route header",
                     f"where={where!r} - a measurement that was not made is not a pass")
    after_ordinary, why = _eff_snapshot(provider)
    if after_ordinary is None:
        REC.fail("the ledger is readable after the ordinary questions", why)
    else:
        moved = _eff_delta(before, after_ordinary)
        REC.expect("no ordinary question moved the spend ledger",
                   moved["dollars"] == 0 and moved["requests"] == 0,
                   f"dollars {dollars6(before['dollars'])} -> "
                   f"{dollars6(after_ordinary['dollars'])}, requests "
                   f"{before['requests']} -> {after_ordinary['requests']}"
                   + ("" if ordinary_cloud else
                      f" - the ledger moved under {', '.join(after_ordinary['services']) or 'no'} "
                      f"row(s) but no ordinary route said cloud"))

    # ---- 2. hard questions: each SHOULD reach the cloud --------------------
    # A private read during the ordinary set (a local model that chose a reading
    # tool, say) would latch the gate and make every hard question local: four
    # model turns that cost minutes, no dollars, and no measurement. Re-check
    # once, and do not send what the router would only refuse.
    latched_now, latch_now_words = _eff_taint_state()
    hard_set = () if latched_now else EFFICIENCY_HARD
    print(f"\n  --- 2. hard questions ({len(hard_set)}) - each SHOULD reach "
          f"where=cloud, gate=escalate; a local answer is MISS, never PASS ---")
    if latched_now:
        print(f"  SKIP  hard set: the PC's taint latch came on during the ordinary "
              f"set ({latch_now_words}); no hard turn is sent because the shipped "
              f"router would refuse the cloud and the cost would be unmeasured")
        REC.fail("the hard set could be measured",
                 f"a taint latch came on mid-section ({latch_now_words}) - the "
                 f"privacy rule working, but a missing measurement: rerun after "
                 f"it expires")
    escalations = []
    misses = []
    spent_this_section = 0.0
    stop_words = ""
    for index, (question, why_it_is_hard) in enumerate(hard_set, 1):
        snap_before, why = _eff_snapshot(provider)
        if snap_before is None:
            REC.fail(f"the ledger is readable before hard question {index}", why)
            break
        turn = chat(question, timeout=300)
        route = turn.route or {}
        where, gate = route.get("where"), route.get("gate")
        print(f"  Q{index}: {question}")
        print(f"       why it is hard: {why_it_is_hard}")
        print(f"       HTTP {turn.status}{(' ' + turn.error) if turn.error else ''} in "
              f"{turn.secs:.1f}s  where={where!r} gate={gate!r} "
              f"complexity={route.get('complexity')!r} "
              f"reason={str(route.get('reason') or '')[:180]!r} "
              f"answer={len(turn.answer or '')}ch")
        if turn.status != 200 or turn.error:
            REC.fail(f"hard question {index} got an HTTP answer",
                     f"HTTP {turn.status} {(turn.error or '').strip()}")
        elif where == "cloud" and gate == "escalate":
            snap_after, why = _eff_wait_for_ledger(provider, snap_before)
            if snap_after is None:
                REC.fail(f"the ledger is readable after hard question {index}", why)
            else:
                moved = _eff_delta(snap_before, snap_after)
                spent_this_section += moved["dollars"]
                problems = []
                if moved["requests"] < 1:
                    problems.append(
                        f"no request recorded ({dollars6(snap_before['dollars'])} -> "
                        f"{dollars6(snap_after['dollars'])}; ledger rows this month: "
                        f"{', '.join(snap_after['services']) or 'none'})")
                if moved["prompt_tokens"] <= 0 and moved["completion_tokens"] <= 0:
                    problems.append("no token counts recorded")
                if moved["unpriced"] > 0:
                    problems.append("the ledger could not price it (unpriced +1)")
                if not (turn.answer or "").strip():
                    problems.append("no answer text came back from the paid turn")
                print(f"       ledger: dollars {dollars6(snap_before['dollars'])} -> "
                      f"{dollars6(snap_after['dollars'])} (delta "
                      f"{dollars6(moved['dollars'])}); prompt "
                      f"{snap_before['prompt_tokens']} -> {snap_after['prompt_tokens']} "
                      f"(+{moved['prompt_tokens']}); completion "
                      f"{snap_before['completion_tokens']} -> "
                      f"{snap_after['completion_tokens']} "
                      f"(+{moved['completion_tokens']}); requests "
                      f"{snap_before['requests']} -> {snap_after['requests']} "
                      f"(+{moved['requests']})")
                if problems:
                    REC.fail(f"hard question {index} left a usable measurement",
                             "; ".join(problems))
                else:
                    escalations.append({"index": index, "secs": turn.secs, **moved})
                    REC.ok(f"hard question {index} escalated",
                           f"{turn.secs:.1f}s, {dollars6(moved['dollars'])}, prompt "
                           f"+{moved['prompt_tokens']}, completion "
                           f"+{moved['completion_tokens']}")
        elif where == "local":
            misses.append((index, route))
            REC.miss(f"hard question {index} was answered locally",
                     f"gate={gate!r}; route says: "
                     f"{str(route.get('reason') or 'no reason given')[:200]}")
        else:
            REC.fail(f"hard question {index} has a usable route header",
                     f"where={where!r} - a measurement that was not made is not a pass")
        if spent_this_section >= EFF_STOP_DOLLARS and index < len(EFFICIENCY_HARD):
            stop_words = (f"stopped after {index} of {len(EFFICIENCY_HARD)} hard "
                          f"questions: {pennies(spent_this_section)} really spent, "
                          f"the few-cents stop line is {money(EFF_STOP_DOLLARS)}")
            print("  STOP  " + stop_words)
            break

    # ---- 3. cost and seconds per escalated turn ----------------------------
    cost_per = secs_per = 0.0
    final, why = _eff_snapshot(provider)
    if final is None:
        REC.fail("the ledger is readable at the end of the section", why)
    if not escalations:
        tainted = [m for m in misses if (m[1] or {}).get("gate") == "taint"]
        detail = ("no hard question reached where=cloud, gate=escalate, so cost and "
                  "seconds per escalated turn were never measured")
        if tainted:
            detail += ("; every MISS was refused by the PC's taint latch (gate "
                       "'taint') - an environmental refusal, not a routing miss")
        if latched_now:
            detail += (f"; a taint latch came on during the ordinary set "
                       f"({latch_now_words}) and the hard set was not sent")
        REC.fail("at least one hard question escalated", detail)
    else:
        count = len(escalations)
        cost_per = sum(e["dollars"] for e in escalations) / count
        secs_per = sum(e["secs"] for e in escalations) / count
        prompt_per = sum(e["prompt_tokens"] for e in escalations) / count
        completion_per = sum(e["completion_tokens"] for e in escalations) / count
        REC.ok("cost per escalated turn",
               f"{dollars6(cost_per)} across {count} escalated turn(s) = ledger "
               f"dollars delta {pennies(sum(e['dollars'] for e in escalations))}")
        REC.ok("seconds per escalated turn",
               f"{secs_per:.1f}s across {count} turn(s), wall-clock time measured "
               f"around the HTTP call")
        REC.info(f"tokens per escalated turn: prompt {prompt_per:,.0f}, completion "
                 f"{completion_per:,.0f} (ledger deltas, divided by {count})")
        if spent_this_section > est["total"] + 1e-9:
            REC.fail("the section stayed inside the maximum spend it announced",
                     f"really spent {pennies(spent_this_section)}, announced "
                     f"{pennies(est['total'])}")

    # ---- 4. what the budget does, computed and not spent -------------------
    if final is not None:
        if final["cap"] is None:
            REC.fail("the ledger still sets a monthly cap", "the cap disappeared mid-run")
        else:
            try:
                cap_now = float(final["cap"])
            except (TypeError, ValueError):
                cap_now = 0.0
                REC.fail("the monthly cap is a number", repr(final["cap"]))
            remaining_after = cap_now - float(final["dollars"])
            REC.ok("the monthly cap is readable",
                   f"{money(cap_now)} per month on "
                   f"{final['cap_service'] or provider}; {money(final['dollars'])} "
                   f"spent, {money(remaining_after)} left")
            if escalations and cost_per > 0:
                left = max(0.0, remaining_after) / cost_per
                print("\n  --- 4. what happens at the cap (computed, NOT spent) ---")
                print(f"  remaining {pennies(remaining_after)} / measured "
                      f"{dollars6(cost_per)} per escalated turn = about {left:,.0f} more "
                      f"escalated questions this month at today's price.")
                print(f"  At the cap, jarvis_router.choose() gate 5 refuses the cloud "
                      f"(gate 'budget'), so turns answer on this PC until the month "
                      f"resets. This run did NOT spend to the cap to prove that.")
                REC.ok("the budget stops it, computed from the measured price",
                       f"{money(remaining_after)} left = about {left:,.0f} more turns "
                       f"at {dollars6(cost_per)} each")
            elif escalations:
                print("\n  --- 4. what happens at the cap (computed, NOT spent) ---")
                print("  the ledger priced every escalated turn at $0.000000, so at its "
                      "own price the cap never binds; the cost is only real if the "
                      "provider bills differently from the ledger's price table.")
                REC.ok("what the cap does at the measured price",
                       "free at the ledger's price - the cap does not bind")

    if REC.cur["fail"]:
        REC.end("FAIL", "an efficiency row did not prove itself - see the FAIL lines above")
    else:
        bits = [f"{ordinary_local}/{len(EFFICIENCY_ORDINARY)} ordinary stayed local "
                f"($0.00)"]
        bits.append(f"{len(escalations)}/{len(EFFICIENCY_HARD)} hard escalated")
        if escalations:
            bits.append(f"{dollars6(cost_per)} and {secs_per:.1f}s per escalated turn")
        if final is not None and final["cap"] is not None and escalations and cost_per > 0:
            remaining_after = float(final["cap"]) - float(final["dollars"])
            bits.append(f"{money(remaining_after)} left = about "
                        f"{max(0.0, remaining_after) / cost_per:,.0f} more turns")
        if misses:
            bits.append(f"{len(misses)} hard question(s) MISSed (reported above)")
        if stop_words:
            bits.append(stop_words)
        REC.end("PASS", "; ".join(bits))


# ---- GitHub battery --------------------------------------------------------
def _gh_checks(pr):
    """(check rows, why) for one pull request, from gh's own categorization.

    `gh pr checks --json name,bucket,state` reports every check with gh's own
    `bucket` - the documented categorization of its `state` into pass / fail /
    pending / skipping / cancel - and the raw `state` beside it. The battery
    uses ONLY those gh words as ground truth: `bucket == "fail"` is a FAILED
    check, `bucket == "pending"` is a check that has not finished, and nothing
    else counts as a failure (ruling 5.2, 2026-11-20).

    `gh pr checks` exits 8 when any check is still PENDING. That is a valid
    answer, not an error, so this read cannot go through `gh_json`, which
    refuses every non-zero exit - it would throw away exactly the pending
    ground truth the running-checks question compares against.
    """
    code, out, err = run(["gh", "pr", "checks", str(pr), "--repo", GH_REPO,
                          "--json", "name,bucket,state"])
    if code not in (0, 8):
        return [], norm(err or out)[:200]
    try:
        rows = json.loads(out)
    except ValueError as exc:
        return [], f"gh output is not JSON ({exc})"
    return rows if isinstance(rows, list) else [], ""


def _check_names(rows, bucket):
    """The names of the checks gh put in one of its own buckets."""
    names = []
    for row in rows or []:
        if str(row.get("bucket") or "") == bucket:
            name = str(row.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _squashed_bases(names):
    """`names` reduced to what a squashed answer can be searched for."""
    return {re.sub(r"[^a-z0-9]", "", name.split(" (")[0].lower())
            for name in names}


def _mentions_count(text, count):
    """True when `count` appears as its OWN number, never inside another one.

    The old substring test read the `1` in a pull request number ("#1400") as a
    count of one failed check, so an answer that named only the PR number passed
    the "names the failed checks" rule. Ruling 5.2's ground truth is only as
    honest as the comparison against it, so the count is matched as a whole
    number, not as a substring of any other number.
    """
    return re.search(r"(?<!\d)" + str(int(count)) + r"(?!\d)",
                     str(text)) is not None


def _failing_answer_ok(text, pr, names):
    """True when the answer names the failed checks gh ground truth holds.

    RULING 5.2 (2026-11-20): the battery asks this question only about a
    SETTLED pull request - gh shows a failed check and NO pending one - so the
    answer must name one of the checks gh puts in its `fail` bucket (or the real
    count) and must not say nothing is failing. A "still going" answer is not
    the answer to this question's own state.
    """
    low = norm(text).lower()
    squashed = re.sub(r"[^a-z0-9]", "", low)
    named = any(base and base in squashed for base in _squashed_bases(names))
    said_none = any(phrase in low for phrase in
                    ("no failing", "nothing is failing", "nothing failing",
                     "all checks pass", "no failed"))
    count_ok = bool(names) and _mentions_count(text, len(names))
    return str(pr) in str(text) and (named or count_ok) and not said_none \
        and not ASK_WHO_RE.search(text)


def _pending_answer_ok(text, pr, names):
    """True when the answer says the pending checks are still going, not failed.

    RULING 5.2 (2026-11-20): the battery asks this question about a pull request
    whose checks gh calls PENDING and none it calls failed. The answer must name
    the pull request and at least one pending check (or the real count), say
    they are still going / not finished / pending, and must NEVER use the
    failing words - a check that has not finished has not failed.
    """
    low = norm(text).lower()
    squashed = re.sub(r"[^a-z0-9]", "", low)
    named = any(base and base in squashed for base in _squashed_bases(names))
    count_ok = bool(names) and _mentions_count(text, len(names))
    still = any(phrase in low for phrase in
                ("still going", "still running", "not all finished",
                 "not finished", "have not finished", "pending"))
    said_failed = any(phrase in low for phrase in
                      ("failed", "failing", "not all green",
                       "did not finish successfully"))
    return str(pr) in str(text) and (named or count_ok) and still \
        and not said_failed and not ASK_WHO_RE.search(text)


# ---- recognising an honest "there is nothing" (fixed 2026-11-19) -----------
#: The measured failure this block fixes. With an EMPTY queue the deployed build
#: answered "There are no open pull requests on darknight11ish/Epic-Jarvis." -
#: the honest answer for the actual state - and the old rules FAILed it, twice:
#:   * "none", "not ready" and "no pull request" are none of them substrings of
#:     "there are no OPEN pull requests" (singular vs plural, and "open" sits
#:     between the words);
#:   * with no open pull request there is no branch head to mention and no count
#:     to match, so "real data" was required of a queue that has none.
#: The rules below accept the natural shapes of "there are none" and NOTHING
#: that invents data: a PR number where no PR exists, a CI check where none can
#: run (there is no pull request to run it on), an owner/name request, or a
#: denial are still a FAIL.
_NOTHING_RE = re.compile(
    r"\bnone\b"
    r"|\bnothing\b(?:\s+(?:is|are|to))?\s*(?:open|ready|mergeable|to\s+merge|"
    r"merged|unmerged|outstanding|pending)\b"
    r"|\bno\s+(?:open\s+|current\s+|active\s+|unmerged\s+|merge[- ]ready\s+|"
    r"pending\s+)?(?:pull\s+requests?|prs?)\b"
    r"|\bno\s+(?:unmerged\s+(?:branches|work)|open\s+(?:work|branches))\b"
    r"|\bnot\s+(?:yet\s+)?(?:ready|mergeable|merge[- ]ready)\b"
    r"|\b(?:0|zero)\s+(?:open\s+)?(?:pull\s+requests?|prs?|defects?|branches)\b"
    r"|\b(?:queue|list|backlog)\b[^.]{0,24}\bempty\b", re.I)

#: A CI check can only be claimed if a pull request exists to run it on. The word
#: "checked" is deliberately NOT matched ("I checked GitHub" is honest prose).
_CHECK_WORD_RE = re.compile(r"\bchecks?\b|\bci\b", re.I)


def says_there_are_none(text):
    """True for the natural honest shapes of "there is nothing", and only those.

    The answer must SAY it, not merely fail to answer: a denial ("I cannot see
    them") is not "there are none", so it is refused here.
    """
    return (bool(_NOTHING_RE.search(norm(text).lower()))
            and not DENY_RE.search(str(text or "")))


#: A number the answer names AS a pull request: "#1432", "PR 1432", "pull
#: request #1432". Deliberately NOT a bare digit run: a cockpit row also prints
#: the 40-character head commit, and `numbers_in` was reading `...b9f1556` and
#: `...c1863ba...` as invented PRs - measured 2026-11-21 on the deploy #6 run,
#: where the answer named exactly the one real PR and "None of them are ready to
#: merge yet" and was failed for it. The instrument, not the answer, was wrong.
_PR_REF_RE = re.compile(
    r"(?:#|\b(?:pr|pull\s+requests?)\s*(?:number\s*)?#?)(\d{1,7})\b", re.I)


def pr_numbers_in(text):
    """PR numbers an answer NAMES as pull requests (never digits inside a sha)."""
    return [int(n) for n in _PR_REF_RE.findall(str(text or ""))]


def invented_pr_numbers(text, real=()):
    """PR numbers the answer names as pull requests that gh does not have."""
    known = {int(n) for n in real or ()}
    return [n for n in pr_numbers_in(text) if n not in known]


#: A positive count claim in an answer that must say "there are none" (e.g.
#: "3 open pull requests", "4 unmerged branches", "5 checks") is invented data
#: when NO open pull request exists, so it is refused. "0 open pull requests" is
#: not a positive claim.
_POSITIVE_COUNT_RE = re.compile(
    r"\b[1-9]\d*\s+(?:open\s+(?:pull\s+requests?|prs?)|"
    r"unmerged\s+(?:branches|pull\s+requests?|prs?)|"
    r"(?:pull\s+requests?|prs?)|checks?)\b", re.I)

#: "3 open pull requests" - a claim that CAN be checked when gh has a queue.
_OPEN_COUNT_RE = re.compile(r"\b(\d+)\s+(?:open\s+)?(?:pull\s+requests?|prs?)\b", re.I)


def empty_answer_ok(text, open_numbers=()):
    """(ok, why) for a row whose gh ground truth is empty (no CLEAN PR / no PR).

    Two empty states share this rule:
      * the queue itself is empty - the honest answer may say so in any natural
        form, but may NOT invent a PR number, claim a positive count or a CI
        check (nothing exists to run one on);
      * the queue has open pull requests but NONE is CLEAN - the honest answer
        may name the real open count ("of the 3 open pull requests, none are
        ready"), but a wrong count or a made-up PR number still FAILs.
    A denial or an owner/name request never passes. The negative controls in
    `--self-test` feed exactly these wrong shapes and require them to FAIL.
    """
    low = norm(text).lower()
    real = {int(n) for n in open_numbers or ()}
    why = []
    invented = invented_pr_numbers(text, real)
    if invented:
        why.append(f"it invents pull-request number(s) {sorted(set(invented))}")
    claimed = [int(m.group(1)) for m in _OPEN_COUNT_RE.finditer(low)]
    positive_claims = [number for number in claimed if number > 0]
    if claimed:
        if not real:
            if positive_claims:
                why.append(f"it claims {positive_claims[0]} open pull request(s) "
                           "where gh has none")
        elif any(number != len(real) for number in claimed):
            why.append(f"it claims {claimed[0]} open pull request(s), gh has "
                       f"{len(real)}")
    if not real:
        positive = _POSITIVE_COUNT_RE.search(low)
        if positive:
            why.append(f"it claims a count that cannot exist ({positive.group(0)!r})")
        if _CHECK_WORD_RE.search(low):
            why.append("it claims CI checks where there is no pull request to run "
                       "them")
    if ASK_WHO_RE.search(str(text or "")):
        why.append("it asks for owner/name")
    if not says_there_are_none(text):
        why.append("it does not say there are none (accepted: none / nothing open / "
                   "no pull requests / nothing ready / an empty queue)")
    return (not why), "; ".join(why)


def defect_answer_ok(text, open_count):
    """The answer names the register AND the count its own `status` column has.

    The register is TAB-separated and its header names the column `status`; the
    deployed feature counts open rows from that column with its own checker, and
    this predicate accepts only that number (word-bounded, so a wrong "138 open"
    cannot hide the right "38" inside it) said as an OPEN count beside the file
    it was read from.
    """
    low = norm(text).lower()
    return ("defect-register.tsv" in low
            and bool(re.search(rf"\b{int(open_count)}\b(?:\s+\w+){{0,2}}\s+open\b",
                               low)))


def section_github():
    REC.header("GITHUB", "the eight GitHub questions, checked against `gh` ground truth",
               "an authenticated gh; read-only for GitHub and for Jarvis")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    ground = {}
    open_rows, why = gh_json("pr", "list", "--repo", GH_REPO, "--state", "open",
                             "--json", "number,title,mergeStateStatus,mergeable,headRefName",
                             "--limit", "40")
    if not isinstance(open_rows, list):
        REC.fail("open pull requests could be read from gh", why)
        return REC.end("FAIL", "no GitHub ground truth, so no GitHub claim can pass")
    ground["open"] = open_rows
    ground["open_numbers"] = [int(r["number"]) for r in open_rows]
    ground["heads"] = [str(r.get("headRefName") or "") for r in open_rows]
    ground["ready"] = [int(r["number"]) for r in open_rows
                       if str(r.get("mergeStateStatus") or "") == "CLEAN"]
    print("\n  GROUND TRUTH (gh, read-only):")
    print(f"    open PRs: {ground['open_numbers']}")
    print(f"    ready (mergeStateStatus CLEAN): {ground['ready']}")
    for row in open_rows:
        print(f"      #{row['number']:<5} {row.get('mergeStateStatus','?'):<9} "
              f"{(row.get('headRefName') or '')[:52]}")

    # RULING 5.2 (2026-11-20): a check that has not finished is PENDING, not
    # failing, so each question picks a subject whose gh state makes its expected
    # answer unambiguous:
    #   * failing - a SETTLED pull request: at least one failed check and NO
    #     pending check, so nothing on it can honestly be called "still going"
    #     and the answer must not mix the two groups;
    #   * running - a pull request with pending checks and NO failed check, so
    #     the honest answer is about the checks still going (in the product's
    #     own order a failed check outranks a running one, so a mixed PR would
    #     answer about the failure instead).
    # gh's own `bucket` is the ground truth: fail is failed, pending is pending.
    failing_pr = pending_pr = None
    failing_names = pending_names = []
    for number in ground["open_numbers"]:
        rows, _ = _gh_checks(number)
        failed = _check_names(rows, "fail")
        pending = _check_names(rows, "pending")
        if failed and not pending and failing_pr is None:
            failing_pr, failing_names = number, failed
        if pending and not failed and pending_pr is None:
            pending_pr, pending_names = number, pending
    if failing_pr is None:
        print("    failing checks: no open pull request has a settled "
              "failing check (an unsettled one is only pending)")
    if pending_pr is None:
        print("    pending checks: no open pull request has only pending checks")
    main_txt, main_why = gh_text("api", f"repos/{GH_REPO}/commits/main", "--jq",
                                 '.sha, .commit.message')
    main_lines = [line.strip() for line in (main_txt or "").splitlines()
                  if line.strip()]
    main_sha = main_lines[0] if main_lines else ""
    main_subject = norm(main_lines[1]) if len(main_lines) > 1 else ""
    if not main_sha:
        REC.info(f"gh could not read main's latest commit: {main_why}")
    branches_txt, _ = gh_text("api", f"repos/{GH_REPO}/branches?per_page=100",
                              "--jq", ".[].name")
    branch_set = {line.strip() for line in branches_txt.splitlines() if line.strip()}
    print(f"    main: {main_sha[:12]} {main_subject[:60]}")
    print(f"    failing checks ({failing_pr}): {failing_names}")
    print(f"    pending checks ({pending_pr}): {pending_names}")
    print(f"    branches on GitHub: {len(branch_set)}")

    questions = []
    questions.append(("open PRs", "What are my open pull requests on Epic-Jarvis?",
                      "open_prs"))
    questions.append(("ready to merge", "Which pull requests on Epic-Jarvis are ready "
                                       "to merge?", "ready")) 
    if failing_pr is not None:
        questions.append(("failing checks", f"What is failing on pull request {failing_pr}?",
                          "failing"))
    if pending_pr is not None:
        questions.append(("running checks", f"What checks are still running on PR "
                                            f"{pending_pr}?", "pending"))
    questions.append(("latest main commit", "What is the latest commit on main in "
                                            "Epic-Jarvis?", "main"))
    questions.append(("unmerged branches", "Which branches have work that is not merged?",
                      "branches"))
    questions.append(("merge how-to", "How do I merge a pull request on GitHub?", "howto"))
    questions.append(("defect count", "How many open defects are in the register?", "defects"))

    results = []
    q_timeout = 300 if STATE["fresh"] is True else 45
    for label, sentence, kind in questions:
        turn = chat(sentence, timeout=q_timeout, provenance=True)
        answer = turns_spend_answer(turn) or (turn.answer or "")
        quick = (turn.route or {}).get("quick")
        text = answer if answer else f"[no answer: {turn.error or 'HTTP ' + str(turn.status)}]"
        classify = "answered"
        if ASK_WHO_RE.search(text):
            classify = "asked for owner/name"
        elif DENY_RE.search(text):
            classify = "denied"
        elif quick:
            classify = f"answered (deterministic quick={quick})"
        print(f"\n  Q: {sentence}")
        print(f"     quick: {quick!r}  [{classify}]  {turn.secs:.1f}s")
        print(f"     A: {' '.join(text.split())[:420]}")
        results.append((label, kind, text, quick))
    REC.info("the GitHub questions were " +
             ("run (observed)" if STATE["fresh"] is not True else "run (counted)"))

    if STATE["fresh"] is not True:
        print("\n  NOTE: this build is not current, so these answers describe the old")
        print("  build and are NOT counted. They are reported so the next run can be")
        print("  compared. The same rows ARE counted after a fresh deploy.")
        return REC.end("SKIP", "STALE BUILD - GitHub answers observed but not counted")

    # Counted mode: every data question must be verified against gh.
    ok = True
    for label, kind, text, quick in results:
        low = norm(text).lower()
        if kind == "open_prs":
            mentioned = set(pr_numbers_in(text))
            missing = [n for n in ground["open_numbers"] if n not in mentioned]
            extra = [n for n in mentioned
                     if n not in ground["open_numbers"] and n >= 1000]
            got = not missing and not extra and not ASK_WHO_RE.search(text)
            ok &= REC.expect(f"open PRs verified against gh ({len(ground['open_numbers'])} "
                             f"open)", got,
                             f"missing {missing}" + (f", invented {extra}" if extra else ""))
        elif kind == "ready":
            mentioned = {n for n in pr_numbers_in(text) if n in ground["open_numbers"]}
            expected = set(ground["ready"])
            if expected:
                extras = mentioned - expected
                caveat = any(word in low for word in
                             ("not ready", "blocked", "cannot merge",
                              "can't merge", "needs review", "not mergeable"))
                got = expected <= mentioned and (not extras or caveat) \
                    and not ASK_WHO_RE.search(text)
                ok &= REC.expect(f"ready-to-merge verified (gh CLEAN: {sorted(expected)})",
                                 got, f"answer named {sorted(mentioned)}"
                                      + (f", extra {sorted(extras)}" if extras else ""))
            else:
                # The CLEAN set is empty. Two honest states share this branch:
                # no open pull request at all, or open pull requests of which
                # none is CLEAN - the accepted answer names neither a made-up PR
                # nor a wrong count (see empty_answer_ok).
                got, empty_why = empty_answer_ok(text, ground["open_numbers"])
                ok &= REC.expect("ready-to-merge verified (gh: none are CLEAN)",
                                 got,
                                 "gh says none are CLEAN; " + empty_why
                                 if not got else "gh says none are CLEAN")
        elif kind == "failing":
            # RULING 5.2: the subject is a SETTLED PR (gh: a failed check and no
            # pending one), so the answer must name one of the checks gh calls
            # FAILED - and must not read as "still going".
            got = _failing_answer_ok(text, failing_pr, failing_names)
            ok &= REC.expect(f"PR {failing_pr}'s failing checks verified "
                             f"(settled: no pending checks)", got,
                             f"gh failing: {failing_names}")
        elif kind == "pending":
            # RULING 5.2: the subject has PENDING checks and no failed one, so
            # the honest answer says they are still going/pending - and NEVER
            # "failed": a still-running check has not failed.
            got = _pending_answer_ok(text, pending_pr, pending_names)
            ok &= REC.expect(f"PR {pending_pr}'s running checks verified "
                             f"(gh pending: {len(pending_names)})", got,
                             f"gh pending: {pending_names}")
        elif kind == "main":
            short = main_sha[:7].lower()
            got = bool(short) and short in low and not ASK_WHO_RE.search(text)
            ok &= REC.expect("latest main commit verified against gh", got,
                             f"gh: {main_sha[:12]} {main_subject[:40]}")
        elif kind == "branches":
            if ground["open_numbers"]:
                mentioned_head = [head for head in ground["heads"]
                                  if head and head.lower() in low]
                count_ok = str(len(ground["open_numbers"])) in text
                got = (bool(mentioned_head) or count_ok) \
                    and not ASK_WHO_RE.search(text)
                detail = f"gh open branches: {ground['heads'][:4]}"
            else:
                # gh ground truth is empty: there IS no unmerged work this read
                # can see, so the honest answer says so. No branch head, count or
                # CI check may be invented - the same negative control as above.
                got, empty_why = empty_answer_ok(text, ground["open_numbers"])
                detail = ("gh: no open pull requests, so no unmerged work is "
                          "visible" + ("" if got else "; " + empty_why))
            ok &= REC.expect("unmerged branches answered with real data", got, detail)
        elif kind == "howto":
            # A procedure answer, not a data claim: naming "owner/repo#42" as
            # an EXAMPLE is correct here, so the ask-for-name test does not
            # apply; a denial does.
            got = ("merge" in low) and not DENY_RE.search(text)
            ok &= REC.expect("the merge how-to is answered (no data claim)", got,
                             "mentions merging; not a GitHub data question")
        elif kind == "defects":
            if "defect_register" not in live_text("jarvis_quick.py"):
                REC.info("the defect count is not in this deployed build (PR #1385); "
                         "the DEFECTS section reports SKIP(not in this build)")
            else:
                rows, named, source, _why = defect_ground_truth()
                if rows is None:
                    ok &= REC.fail("the defect register count can be verified",
                                   str(named))
                else:
                    # The register's OWN header names the column `status`; the
                    # deployed feature counts open rows from THAT column with the
                    # checker beside the register. Same file, same checker, same
                    # column here - measured 2026-11-19: the battery used to read
                    # a different register copy (37 open) than the build (38).
                    open_count = len({str(r.get("id") or "")
                                      for r in rows
                                      if str(r.get("status") or "").strip() == "open"})
                    REC.info(f"the register the deployed build reads: {named} "
                             f"({source}); its status column has {open_count} open")
                    got = defect_answer_ok(text, open_count)
                    ok &= REC.expect(f"defect count verified from the register "
                                     f"({open_count} open)", got,
                                     "answer must name the file and the count the "
                                     "file's status column has")
    if ok:
        REC.end("PASS", "all eight GitHub questions verified against gh ground truth")
    else:
        REC.end("FAIL", "at least one GitHub answer was asked-for-name, denied, or "
                        "did not match gh ground truth")


# ---- capability rows -------------------------------------------------------
def catalogue_rows():
    """{id: row} from the DEPLOYED feature catalogue (read-only import)."""
    module, why = live_module("jarvis_feature_catalogue")
    if module is None:
        return None, why
    features = getattr(module, "FEATURES", None) or []
    return {str(row.get("id")): row for row in features}, ""


def _row_words(row):
    return str(row.get("what") or ""), str(row.get("where") or "")


def _section_feature_gate(sid, title, marker_file, marker_text, requirement):
    REC.header(sid, title, requirement)
    if not STATE["ready"]:
        REC.skip("preflight failed")
        return False
    text = live_text(marker_file)
    if not text:
        REC.skip(f"not in this deployed build: {marker_file} is not in the live "
                 f"folder (the fix is merged-but-not-deployed, or not merged yet)")
        return False
    if marker_text not in text:
        REC.skip(f"not in this deployed build: {marker_file} has no {marker_text!r} "
                 f"(the fix is merged but not deployed, or not merged yet)")
        return False
    return True


def section_capabilities():
    if not _section_feature_gate(
            "CAPABILITIES", "the three measured false-denial questions answer from "
            "the catalogue (PR #1377)",
            "jarvis_quick.py", "_CAP_CAN_YOU_NAMED",
            "the deployed quick path with the #1377 catalogue leads"):
        return
    rows, why = catalogue_rows()
    if rows is None:
        return REC.skip(f"the deployed catalogue could not be imported ({why})")
    wanted = [("Can you send a file from my PC to my phone?", "file-from-pc"),
              ("Can you read my phone notifications?", "phone-notifications"),
              ("Can you add up my spending?", "spending")]
    ok = True
    for sentence, row_id in wanted:
        row = rows.get(row_id)
        if row is None:
            REC.fail(f"catalogue row {row_id} exists in the deployed build")
            ok = False
            continue
        turn = chat(sentence, timeout=180, provenance=True)
        answer = turns_spend_answer(turn)
        quick = (turn.route or {}).get("quick")
        what, where = _row_words(row)
        low = norm(answer).lower()
        denial = any(word in low for word in DENIAL_WORDS)
        print(f"\n  Q: {sentence}")
        print(f"     quick={quick!r}  row={row_id}")
        print(f"     A: {' '.join(answer.split())[:360]}")
        ok &= REC.expect(f"answered from the catalogue fast path ({row_id})",
                         quick == "capability_answer", f"quick={quick!r}")
        ok &= REC.expect(f"quotes {row_id}'s own what/where",
                         bool(what) and has(answer, what) and bool(where)
                         and has(answer, where),
                         "expected the row's own words verbatim")
        ok &= REC.expect(f"no denial in the {row_id} answer", not denial,
                         "a denial phrase was in the answer")
    REC.end("PASS" if ok else "FAIL",
            "all three false denials answer from the catalogue"
            if ok else "a false-denial question still fails")


def section_cap_exact():
    if not _section_feature_gate(
            "CAP-EXACT", "five exact-name questions resolve to their own catalogue "
            "row (PR #1379)",
            "jarvis_quick.py", "_named_feature_question",
            "the deployed quick path with the #1379 exact-name lane"):
        return
    rows, why = catalogue_rows()
    if rows is None:
        return REC.skip(f"the deployed catalogue could not be imported ({why})")
    wanted = [
        ('Do you have a feature called "How much Jarvis may interrupt you"?',
         "attention-budget", "stop-everything"),
        ('Do you have a feature called "Also on my phone"?',
         "also-on-phone", "call-recording"),
        ('Do you have a feature called "Open an app on your phone"?',
         "phone-apps", "call-recording"),
        ('Do you have a feature called "Jarvis starts the local model again by '
         'itself when it dies"?', "restart-the-model-lane", "start-the-model-lane"),
        ("Do you have a feature that asks me my saved study questions again on a "
         "schedule?", "decks", "reminder-asks"),
    ]
    ok = True
    for sentence, row_id, wrong_id in wanted:
        row = rows.get(row_id)
        if row is None:
            REC.fail(f"catalogue row {row_id} exists in the deployed build")
            ok = False
            continue
        turn = chat(sentence, timeout=180, provenance=True)
        answer = turns_spend_answer(turn)
        quick = (turn.route or {}).get("quick")
        what, where = _row_words(row)
        low = norm(answer).lower()
        print(f"\n  Q: {sentence[:84]}")
        print(f"     quick={quick!r}  expected row={row_id} (not {wrong_id})")
        print(f"     A: {' '.join(answer.split())[:360]}")
        ok &= REC.expect(f"answered from the catalogue fast path ({row_id})",
                         quick == "capability_answer", f"quick={quick!r}")
        ok &= REC.expect(f"the answer is {row_id}'s row, not {wrong_id}'s",
                         bool(what) and has(answer, what) and bool(where)
                         and has(answer, where),
                         "the expected row's own what/where were not both quoted")
        ok &= REC.expect(f"no denial in the {row_id} answer",
                         not any(word in low for word in DENIAL_WORDS), "")
    REC.end("PASS" if ok else "FAIL",
            "every exact-name question reached its own row"
            if ok else "an exact-name question reached the wrong answer")


# ---- presets ---------------------------------------------------------------
def _lane_ps(port):
    """(models, why) from the lane's own /api/ps - read-only, no token."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ps",
                                    timeout=8) as resp:
            doc = json.loads(resp.read().decode("utf-8", "replace"))
        return doc.get("models") or [], ""
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}"


def section_presets():
    REC.header("PRESETS", "every lane's /api/ps, and whether the everyday lane is on "
               "its own one-card preset at 196,608 (spill reported, never invented)",
               "/api/presets and /api/ps on every lane port")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    status, presets_doc, _, err = http_json("/api/presets")
    presets = (presets_doc or {}).get("presets") if isinstance(presets_doc, dict) else None
    if status != 200 or not isinstance(presets, list) or not presets:
        REC.fail("GET /api/presets answers with the preset table",
                 f"HTTP {status} {err}".strip())
        return REC.end("FAIL", "the preset table could not be read")

    # Every lane's own measurement first: model, size, context, spill.
    measurements = {}
    print("  /api/ps on every lane port (what is REALLY resident):")
    for port in LANE_PORTS:
        models, why = _lane_ps(port)
        measurements[port] = (models, why)
        if why:
            print(f"    lane {port}: REFUSED ({why}) - reported, not guessed")
            continue
        if not models:
            print(f"    lane {port}: (empty - no model resident)")
            continue
        for entry in models:
            size = entry.get("size")
            vram = entry.get("size_vram")
            spill = ""
            if isinstance(size, (int, float)) and isinstance(vram, (int, float)):
                spill = f", spill {(size - vram) / (1024 ** 3):.3f} GiB"
            shown_size = (f"size={size / (1024 ** 3):.2f} GiB"
                          if isinstance(size, (int, float)) else "size not reported")
            print(f"    lane {port}: {entry.get('name')!r} "
                  f"context={entry.get('context_length')} {shown_size}{spill}")

    # The preset table's own declarations, per row (the deployed truth, not a
    # fixed expectation: general became a 26B heavy mode on the pooled lane on
    # 2026-11-18, while several one-card rows still declare 196,608 on 11436).
    print("\n  /api/presets declarations:")
    rows = []
    for row in presets:
        if not isinstance(row, dict):
            continue
        lane = row.get("lane") or {}
        try:
            port = int(lane.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        try:
            context = int(row.get("context") or 0)
        except (TypeError, ValueError):
            context = 0
        rows.append({"id": str(row.get("id") or ""), "model": str(row.get("model") or ""),
                     "lane": str(lane.get("key") or ""), "port": port,
                     "context": context, "heavy": bool(row.get("heavy_mode"))})
        print(f"    {rows[-1]['id']:<20} {rows[-1]['model'][:44]:<44} "
              f"lane={rows[-1]['lane']:<7} port={port:<6} ctx={context}"
              + ("  HEAVY (pooled)" if rows[-1]["heavy"] else ""))

    ok = True
    bad_ports = [row["id"] for row in rows if row["port"] not in LANE_PORTS]
    ok &= REC.expect("every preset names a real lane port",
                     not bad_ports,
                     f"{len(rows)} rows, ports "
                     + str(sorted({row['port'] for row in rows}))
                     + (f", bad: {bad_ports}" if bad_ports else ""))
    general = next((row for row in rows if row["id"] == "general"), None)
    if general is None:
        ok &= REC.fail("the preset table has a general row", "")
    elif general["heavy"] or general["port"] == 11450:
        REC.info(f"general is deliberately HEAVY: {general['model']!r} on the pooled "
                 f"lane {general['port']} at {general['context']:,} tokens - it is "
                 f"not a one-card preset, so it cannot be 'one-card at 196,608'. "
                 f"The one-card everyday rows are the 11436 rows above.")
    else:
        REC.info(f"general is a one-card preset: {general['model']!r} on lane "
                 f"{general['port']} at {general['context']:,} tokens")

    # The brief's row: is the everyday lane on its own one-card model at 196,608?
    main_rows = [row for row in rows if row["port"] == EVERYDAY_PORT]
    long_rows = [row for row in main_rows if row["context"] == EVERYDAY_CONTEXT]
    ok &= REC.expect(f"the preset table has a one-card row at {EVERYDAY_CONTEXT:,} "
                     f"tokens on lane {EVERYDAY_PORT}",
                     bool(long_rows),
                     ", ".join(row["id"] for row in long_rows[:6]) or
                     "no such row")
    resident, why = measurements.get(EVERYDAY_PORT, ([], "not measured"))
    if why:
        ok &= REC.fail("the everyday lane answers /api/ps at all", why)
    elif not resident:
        ok &= REC.fail("the everyday lane has a model resident",
                       "11436 is empty, so the one-card claim cannot be measured")
    else:
        entry = resident[0]
        name = str(entry.get("name") or "")
        got_ctx = entry.get("context_length")
        match = [row for row in main_rows
                 if row["model"] == name and row["context"] == got_ctx]
        ok &= REC.expect("the everyday lane is on a model its own preset table "
                         "declares for it", bool(match),
                         f"resident {name!r} @ {got_ctx}; declared 11436 rows: "
                         + ", ".join(f"{r['id']}={r['model']}@{r['context']}"
                                     for r in main_rows[:6]))
        if match:
            REC.info(f"everyday lane: {name!r} at context {got_ctx} = preset "
                     f"{match[0]['id']!r}")
        on_long = [row for row in long_rows
                   if row["model"] == name and got_ctx == EVERYDAY_CONTEXT]
        ok &= REC.expect(f"the everyday lane is on its one-card model at "
                         f"{EVERYDAY_CONTEXT:,} tokens", bool(on_long),
                         f"resident {name!r} at context {got_ctx}")
        size, vram = entry.get("size"), entry.get("size_vram")
        if isinstance(size, (int, float)) and isinstance(vram, (int, float)):
            spill_gib = (size - vram) / (1024 ** 3)
            ok &= REC.expect("that one-card model is fully in VRAM", spill_gib <= 0.001,
                             f"reported spill {spill_gib:.3f} GiB")
            REC.info(f"reported spill: {spill_gib:.3f} GiB "
                     f"(from /api/ps size - size_vram; not invented)")
        else:
            REC.info("reported spill: /api/ps does not carry size_vram on this lane - "
                     "no spill figure is claimed")
    for row in rows:
        if row["port"]==11450 and row["heavy"]:
            loaded, lane_why = measurements.get(11450, ([], ""))
            REC.info(f"pooled lane 11450 for {row['id']!r}: "
                     f"{'not running' if lane_why else ((', '.join(str(m.get('name')) for m in loaded)) or 'empty')}"
                     f" - on demand, so not running is not a failure")
            break
    if ok:
        REC.end("PASS", f"everyday 11436 matches its one-card preset at "
                        f"{EVERYDAY_CONTEXT:,}; every lane reported")
    else:
        REC.end("FAIL", "the everyday lane does not match its own preset table")

# ---- notes -----------------------------------------------------------------
def notes_module():
    return live_module("jarvis_notes")


def vault_path():
    module, why = notes_module()
    if module is None:
        return None, f"the deployed jarvis_notes could not be imported ({why})"
    try:
        vault = module.obsidian_vault()
    except Exception as exc:  # noqa: BLE001
        return None, f"the vault path could not be worked out ({type(exc).__name__})"
    if not vault:
        return None, "no Obsidian vault is set up on this PC"
    return Path(vault), ""


def vault_files():
    vault, why = vault_path()
    if vault is None:
        return [], why
    out = []
    try:
        for path in vault.rglob("*"):
            if path.is_file():
                out.append(path)
            if len(out) >= VAULT_SCAN_CAP:
                break
    except OSError as exc:
        return out, f"the vault walk stopped ({type(exc).__name__})"
    return out, ""


def find_vault_note(token):
    files, _ = vault_files()
    low = token.lower()
    hits = [p for p in files if low in p.name.lower()]
    return hits


def section_notes():
    REC.header("NOTES", "one create, one recall in a later turn - throwaway only",
               "an Obsidian vault configured for the live build")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    vault, why = vault_path()
    if vault is None:
        return REC.skip(why)
    name = MARKER + "-NOTE"
    token = MARKER + "-CONTENT-" + STAMP[-4:]
    sentence = f"create a note called {name} with content {token}"
    turn = chat(sentence, timeout=180, provenance=True)
    answer = turns_spend_answer(turn)
    quick = (turn.route or {}).get("quick")
    print(f"\n  create: {sentence}")
    print(f"  quick={quick!r}  A: {' '.join(answer.split())[:300]}")
    files = find_vault_note(name)
    if not files and (quick == "note_create_ask" or "approval" in answer.lower()
                      or "waiting" in answer.lower()):
        # A note write may be carded on this PC; answer ONLY our own card.
        approved, card_id, card_why = approve_own_card([MARKER])
        REC.info(f"note-create card: approved={approved} id={card_id or '-'} "
                 f"({card_why})")
        if approved:
            time.sleep(1.0)
            files = find_vault_note(name)
    created = bool(files)
    body_ok = False
    if created:
        try:
            body_ok = token in files[0].read_text(encoding="utf-8", errors="replace")
        except OSError:
            body_ok = False
    ok = True
    ok &= REC.expect("the create went through the deterministic note path",
                     quick == "note_created", f"quick={quick!r}")
    ok &= REC.expect("the note really exists in the vault", created,
                     f"found {[p.name for p in files] or 'nothing'}")
    ok &= REC.expect("the note really holds the throwaway content", body_ok, "")
    if created:
        REC.info(f"the note is {files[0]}")

    recall_turn = chat(f"read my note {name}", timeout=180, provenance=True)
    recall = turns_spend_answer(recall_turn)
    recall_quick = (recall_turn.route or {}).get("quick")
    print(f"\n  recall (later turn): read my note {name}")
    print(f"  quick={recall_quick!r}  A: {' '.join(recall.split())[:300]}")
    ok &= REC.expect("the later turn recalled the note from disk",
                     recall_quick == "note_read" and token in recall,
                     f"quick={recall_quick!r}, token present={token in recall}")

    # Clean up ONLY our own note (the exact file we created).
    cleaned = True
    for path in files:
        try:
            path.unlink()
        except OSError as exc:
            cleaned = False
            REC.fail("the throwaway note was deleted", f"{path}: {exc}")
    left = find_vault_note(name) if cleaned else []
    ok &= REC.expect("cleanup removed only the throwaway note", cleaned and not left,
                     f"left: {[p.name for p in left]}")
    REC.end("PASS" if ok else "FAIL",
            "created, recalled in a later turn, and deleted its own throwaway note"
            if ok else "the notes row did not prove itself")


# ---- favourite notes -------------------------------------------------------
def _read_frontmatter(path, limit=4096):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(limit)
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip().lower()] = value.strip().lower()
    return out


def section_favourites():
    if not _section_feature_gate(
            "FAVOURITES", "the favourite flag is a resolver tier, later turn "
            "(PR #1371)", "jarvis_notes.py", 'RESOLVE_TIERS = ("path", "basename", '
            '"alias", "favourite")',
            "the deployed jarvis_notes.py with the favourite tier"):
        return
    vault, why = vault_path()
    if vault is None:
        return REC.skip(why)
    # Do not touch the owner's own favourite notes: if the vault already has
    # any, adding another would make "my favourite note" ambiguous and this
    # script must never edit or remove one.
    files, _ = vault_files()
    existing = []
    for path in files:
        if path.suffix.lower() not in (".md", ".markdown"):
            continue
        front = _read_frontmatter(path)
        if str(front.get("favorite") or front.get("favourite") or "") in (
                "true", "yes", "on", "1"):
            existing.append(path)
    if existing:
        return REC.skip(f"the vault already has {len(existing)} note(s) marked as a "
                        f"favourite ({', '.join(p.name for p in existing[:3])}); the "
                        f"tier would be ambiguous and the script does not touch the "
                        f"owner's favourites")
    seed = vault / (MARKER + "-FAVOURITE.md")
    token = MARKER + "-FAV-APPEND-" + STAMP[-4:]
    try:
        seed.write_text("---\nfavorite: true\n---\n" + MARKER + " throwaway favourite "
                        "seeded by run_battery.py\n", encoding="utf-8")
    except OSError as exc:
        return REC.skip(f"the temp vault could not be written ({exc})")
    ok = True
    try:
        REC.info(f"seeded the only favourite note (throwaway): {seed.name}")
        turn = chat(f"add {token} to my favourite note", timeout=180, provenance=True)
        answer = turns_spend_answer(turn)
        quick = (turn.route or {}).get("quick")
        print(f"  later turn: add {token} to my favourite note")
        print(f"  quick={quick!r}  A: {' '.join(answer.split())[:320]}")
        ok &= REC.expect("the favourite words resolved through the note resolver",
                         quick in ("note_appended", "note_append",
                                   "note_append_done", "note_append_waiting"),
                         f"quick={quick!r}")
        if quick == "note_append_waiting":
            # A note write is carded on this PC. The battery answers ITS OWN
            # card (the card names the throwaway note) and never any other.
            approved, card_id, card_why = approve_own_card([MARKER, seed.stem])
            ok &= REC.expect("the battery approved only its own note-write card",
                             approved, f"card {card_id}: {card_why}")
            deadline = time.time() + 5.0
            content = ""
            while time.time() < deadline:
                try:
                    content = seed.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    content = ""
                if token in content:
                    break
                time.sleep(0.4)
        else:
            try:
                content = seed.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
        ok &= REC.expect("the words were appended to the favourite note itself",
                         token in content, f"token present={token in content}")
        ok &= REC.expect("the answer did not deny the feature",
                         not any(word in norm(answer).lower() for word in DENIAL_WORDS),
                         "")
        ok &= REC.expect("the tier is stated last in the resolver's order",
                         'RESOLVE_TIERS = ("path", "basename", "alias", '
                         '"favourite")' in live_text("jarvis_notes.py"), "")
        REC.info("a favourite's CONTENT never being shown to a model: NOT-TESTABLE "
                 "here - it would need the model's own prompt, and a reply that "
                 "quotes it would not prove anything either way")
    finally:
        try:
            seed.unlink()
        except OSError as exc:
            ok = False
            REC.fail("the throwaway favourite note was deleted", str(exc))
    ok &= REC.expect("cleanup removed the seeded favourite", not seed.exists(), "")
    REC.end("PASS" if ok else "FAIL",
            "the favourite tier resolved the only favourite in a later turn"
            if ok else "the favourite tier did not prove itself")


# ---- cloud settings from chat ---------------------------------------------
def _cloud_expected():
    choice, _ = read_json(CLOUD_CHOICE)
    switch, _ = read_json(ESCALATE_FILE)
    ledger, _ = read_json(MONEY_FILE)
    provider = str((choice or {}).get("provider") or "") if isinstance(choice, dict) else ""
    api, api_why = live_module("jarvis_chatbot_api")
    company = provider
    dollars = None
    month_key = datetime.now().strftime("%Y-%m")
    if api is not None:
        presets = getattr(api, "PRESETS", {}) or {}
        entry = presets.get(provider)
        if entry is not None:
            company = str(getattr(entry, "company", "") or provider)
        try:
            month_key = str(api.month_key())
        except Exception:  # noqa: BLE001
            pass
        dollars = getattr(api, "dollars", None)
    def fmt(value):
        if callable(dollars):
            try:
                return str(dollars(value))
            except Exception:  # noqa: BLE001
                pass
        return money(value)
    limits = (ledger or {}).get("limits") or {} if isinstance(ledger, dict) else {}
    rows = (((ledger or {}).get("months") or {}).get(month_key) or {}) \
        if isinstance(ledger, dict) else {}
    total = 0.0
    requests = 0
    for row in (rows.values() if isinstance(rows, dict) else ()):
        if isinstance(row, dict):
            try:
                total += float(row.get("dollars") or 0.0)
                requests += int(row.get("requests") or 0)
            except (TypeError, ValueError):
                pass
    cap = limits.get(provider) if provider in limits else (
        next(iter(limits.values())) if len(limits) == 1 else None)
    return {"provider": provider, "company": company,
            "on": isinstance(switch, dict) and switch.get("on") is True,
            "switch_exists": isinstance(switch, dict),
            "cap": cap, "cap_words": fmt(cap) if cap is not None else "",
            "month_key": month_key, "total": total, "spend_words": fmt(total),
            "requests": requests, "api_why": api_why}


def section_cloud_settings():
    if not _section_feature_gate(
            "CLOUD-SETTINGS", "the five cloud-settings questions answer from the "
            "PC's own files, with the date (PR #1376)",
            "jarvis_quick.py", "_cloud_settings_prompt",
            "the deployed quick path and jarvis_cloud_settings.py"):
        return
    if not (LIVE / "jarvis_cloud_settings.py").is_file():
        return REC.skip("not in this deployed build: jarvis_cloud_settings.py is not "
                        "in the live folder")
    exp = _cloud_expected()
    # The exact "saved 31 Oct 2026" words each answer should carry, read the
    # same way the deployed module reads them: from the file's own mtime.
    saved_expected = {}
    for token, path in (("cloud-choice.json", CLOUD_CHOICE),
                        ("escalate-cloud.json", ESCALATE_FILE),
                        ("api-money.json", MONEY_FILE)):
        saved_expected[token] = _saved_words(path)
    print("\n  GROUND TRUTH read by the battery itself (never written):")
    print(f"    cloud-choice.json provider: {exp['provider']!r} ({exp['company']})")
    print(f"    escalate-cloud.json: {'on' if exp['on'] else 'off'}")
    print(f"    api-money.json limits: cap={exp['cap_words'] or 'none'}, "
          f"month={exp['month_key']} spent={exp['spend_words']} "
          f"({exp['requests']} answer(s))")
    print(f"    file mtimes: {saved_expected}")
    questions = [
        ("provider", "Which cloud provider am I using?", "cloud-choice.json",
         [exp["company"]] if exp["company"] else []),
        ("escalation", "Is escalation on?", "escalate-cloud.json",
         ["is ON"] if exp["on"] else ["is off"]),
        ("cap", "What's my cap?", "api-money.json",
         [exp["cap_words"]] if exp["cap_words"] else []),
        ("spend", "How much have I spent this month?", "api-money.json",
         [exp["spend_words"]] + ([str(exp["requests"])] if exp["requests"] else [])),
        ("what_it_does", "What does escalation actually do?", "escalate-cloud.json", []),
    ]
    ok = True
    for label, sentence, file_token, must in questions:
        turn = chat(sentence, timeout=180, provenance=True)
        answer = turns_spend_answer(turn)
        quick = (turn.route or {}).get("quick")
        print(f"\n  Q: {sentence}")
        print(f"     quick={quick!r}  A: {' '.join(answer.split())[:380]}")
        ok &= REC.expect(f"{label}: answered from the fast path, not the model",
                         quick == "cloud_settings", f"quick={quick!r}")
        ok &= REC.expect(f"{label}: names {file_token}",
                         file_token in answer, f"answer names no {file_token}")
        saved = saved_expected.get(file_token) or ""
        if saved:
            ok &= REC.expect(f"{label}: names the date it read ({saved!r})",
                             saved in answer, "the answer's date is not the file's")
        else:
            ok &= REC.expect(f"{label}: names the date it read",
                             bool(DATE_RE.search(answer)),
                             "no '18 Nov 2026'-style date")
        for needle in must:
            ok &= REC.expect(f"{label}: matches the file ({needle!r})",
                             has(answer, needle), f"file says {needle!r}")
    REC.end("PASS" if ok else "FAIL",
            "every cloud-settings answer named its file and date and matched it"
            if ok else "a cloud-settings answer did not come from the PC's files")


# ---- defect register -------------------------------------------------------
#: The two names the DEPLOYED feature itself resolves its register from
#: (`jarvis_quick._defect_register_location` reads these from the HUD process).
_DEFECT_REGISTER_ENV = "JARVIS_DEFECT_REGISTER"
_REVIEW_REPO_ENV = "JARVIS_REVIEW_REPO"


def _live_hud_pid():
    """(pid, why) of the running HUD, from its own /api/self/version."""
    status, doc, _, err = http_json("/api/self/version", timeout=10)
    if status != 200 or not isinstance(doc, dict):
        return 0, f"HTTP {status}" + (f" {err}" if err else "")
    try:
        return int(doc.get("pid") or 0), ""
    except (TypeError, ValueError):
        return 0, "the HUD named no pid"


def live_hud_environment(names):
    """{NAME: value} from the RUNNING HUD's own process, or ({}, why).

    WHY THIS EXISTS (measured 2026-11-19). The deployed defect-register answer
    resolves its file from ITS OWN process environment - `jarvis_quick.
    _defect_register_location` reads JARVIS_DEFECT_REGISTER, then
    JARVIS_REVIEW_REPO, then `<backend>/..`. This battery is a different process
    and inherits neither, so it read a different register copy (37 open) from the
    one the build answered from (38 open) and FAILed a correct answer. Asking the
    build what it was started with is the only way the ground truth can be the
    same register the answer names.

    Read-only on the live machine: OpenProcess with query+read access, then read
    the process's own environment block. Nothing is written, no process state is
    changed, no config is touched, and no token is read. If the HUD runs as
    another user, or this is not Windows, the caller falls back to the places it
    can see itself and says so - an unreadable environment is never invented.
    """
    wanted = [str(n) for n in names]
    if sys.platform != "win32":
        return {}, "not a Windows HUD"
    pid, why = _live_hud_pid()
    if not pid:
        return {}, f"the live HUD's pid could not be read ({why})"
    handle = None
    try:
        import ctypes
        import struct

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY|VM_READ
        if not handle:
            return {}, f"the HUD process {pid} could not be opened"

        class _Basic(ctypes.Structure):
            _fields_ = [("reserved1", ctypes.c_void_p),
                        ("peb", ctypes.c_void_p),
                        ("reserved2", ctypes.c_void_p * 2),
                        ("pid", ctypes.c_void_p),
                        ("reserved3", ctypes.c_void_p)]

        basic = _Basic()
        used = ctypes.c_ulong(0)
        if ntdll.NtQueryInformationProcess(
                handle, 0, ctypes.byref(basic), ctypes.sizeof(basic),
                ctypes.byref(used)) != 0 or not basic.peb:
            return {}, f"the HUD process {pid}'s block could not be queried"

        def read(address, size):
            buffer = ctypes.create_string_buffer(size)
            got = ctypes.c_size_t(0)
            if not kernel32.ReadProcessMemory(
                    handle, ctypes.c_void_p(address), buffer, size,
                    ctypes.byref(got)) or not got.value:
                return b""
            return buffer.raw[:got.value]

        # x64 PEB->ProcessParameters at 0x20; RTL_USER_PROCESS_PARAMETERS->
        # Environment at 0x80, as the Python that runs the HUD is 64-bit.
        raw = read(basic.peb + 0x20, 8)
        if not raw:
            return {}, "the HUD process's parameters could not be read"
        params = struct.unpack("<Q", raw)[0]
        raw = read(params + 0x80, 8) if params else b""
        environment = struct.unpack("<Q", raw)[0] if raw else 0
        data = read(environment, 65536) if environment else b""
        if not data:
            return {}, "the HUD process's environment block could not be read"
        upper = {name.upper() for name in wanted}
        found = {}
        for item in data.decode("utf-16-le", "replace").split("\x00"):
            name, sep, value = item.partition("=")
            if sep and name.upper() in upper:
                found[name.upper()] = value
        if not found:
            return {}, ("the HUD's environment names none of "
                        + ", ".join(wanted))
        return found, ""
    except Exception as exc:  # noqa: BLE001 - an unreadable block is a state
        return {}, f"the HUD's environment could not be read ({type(exc).__name__})"
    finally:
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except Exception:  # noqa: BLE001
                pass


def defect_ground_truth():
    """(rows, register_named, source, why) for the register the BUILD reads.

    Resolved in the same order the deployed feature resolves it: the file named
    by JARVIS_DEFECT_REGISTER, then JARVIS_REVIEW_REPO's checkout, then
    `<backend>/..`. The first two are asked of the RUNNING HUD's own environment
    (see `live_hud_environment`), because this battery is a separate process and
    the build does not answer from whatever copy this shell can see: measured
    2026-11-19, the battery reported 37 open from another worktree while the
    build answered 38 open from the Epic-Jarvis-main checkout.

    The rows are parsed by the checker that sits BESIDE the register - the same
    `tools/check_defect_register.py` the deployed feature loads from the
    register's own tree - so the header's `status` column is read by one parser
    in both places, and a count can never come from a hand-rolled column guess.
    """
    candidates = []

    def add(path, source):
        candidates.append((Path(path).expanduser(), source))

    # An explicit operator override in THIS shell wins, then the build's own
    # environment - the file the answer really came from.
    if os.environ.get(_DEFECT_REGISTER_ENV, "").strip():
        add(os.environ[_DEFECT_REGISTER_ENV], "this shell's JARVIS_DEFECT_REGISTER")
    if os.environ.get(_REVIEW_REPO_ENV, "").strip():
        add(Path(os.environ[_REVIEW_REPO_ENV]) / "docs" / "defect-register.tsv",
            "this shell's JARVIS_REVIEW_REPO")
    live_env, _env_why = live_hud_environment((_DEFECT_REGISTER_ENV, _REVIEW_REPO_ENV))
    if str(live_env.get(_DEFECT_REGISTER_ENV) or "").strip():
        add(live_env[_DEFECT_REGISTER_ENV],
            "the deployed HUD's own JARVIS_DEFECT_REGISTER")
    if str(live_env.get(_REVIEW_REPO_ENV) or "").strip():
        add(Path(live_env[_REVIEW_REPO_ENV]) / "docs" / "defect-register.tsv",
            "the deployed HUD's own JARVIS_REVIEW_REPO")
    # Then the places this script can see for itself.
    add(LIVE.parent / "docs" / "defect-register.tsv", "the live backend's parent")
    add(DEFECT_REGISTER, "the checkout named by JARVIS_REPO / this script's tree")

    found = source = None
    for path, why in candidates:
        if path.is_file():
            found, source = path, why
            break
    if found is None:
        return (None, "", "", "no defect register found; looked at "
                + str([str(path) for path, _ in candidates]))

    # The repository's own checker is the authority on the rows (the feature uses
    # the same parser, from the tree the register lives in), loaded from source
    # so nothing is written beside it.
    checker = found.parent.parent / "tools" / "check_defect_register.py"
    if not checker.is_file():
        checker = DEFECT_CHECKER
        source += "; its tree has no tools/check_defect_register.py, so this "
        source += "checkout's checker is used"
    rows = None
    if checker.is_file():
        try:
            import types
            module = types.ModuleType("fieldbattery_defect_checker")
            module.__file__ = str(checker)
            source_code = checker.read_text(encoding="utf-8-sig")
            exec(compile(source_code, str(checker), "exec"), module.__dict__)
            problems = []
            rows = module.parse_tsv(found, problems)
            if problems:
                return (None, str(found), source, "the register is not well formed: "
                        + "; ".join(str(p) for p in problems[:2]))
        except Exception as exc:  # noqa: BLE001
            return (None, str(found), source,
                    f"the checker could not parse it ({type(exc).__name__})")
    if rows is None:
        # Narrow standard-library fallback: the header names every column, so the
        # count still comes from the column called `status`, never from a guess.
        try:
            raw = found.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            return None, str(found), source, f"the register could not be read ({exc})"
        header = [cell.strip() for cell in (raw[0].split("\t") if raw else [])]
        if "status" not in header:
            return (None, str(found), source,
                    f"the register has no TSV header column named 'status' "
                    f"(found {header})")
        rows = []
        for line in raw[1:]:
            parts = [cell.strip() for cell in line.split("\t")]
            if len(parts) == len(header):
                rows.append(dict(zip(header, parts)))
    return rows, str(found), source, ""


def section_defects():
    if not _section_feature_gate(
            "DEFECTS", "the defect register count comes from its own file and "
            "matches it (PR #1385)",
            "jarvis_quick.py", "_defect_register_location",
            "the deployed quick path and a docs/defect-register.tsv it can reach"):
        return
    rows, register, source, why = defect_ground_truth()
    if rows is None:
        REC.fail("the defect register can be read for ground truth", why)
        return REC.end("FAIL", "no register to check the answer against")
    REC.info(f"ground truth: {register} ({len(rows)} rows; from {source})")
    open_ids = [str(r.get("id")) for r in rows if str(r.get("status")) == "open"]
    total = len(rows)
    print(f"  file says: {len(open_ids)} open, {total - len(open_ids)} closed, "
          f"{total} rows")
    ok = True
    turn = chat("How many open defects are in the register?", timeout=180, provenance=True)
    answer = turns_spend_answer(turn)
    quick = (turn.route or {}).get("quick")
    print(f"  Q: How many open defects are in the register?")
    print(f"  quick={quick!r}  A: {' '.join(answer.split())[:400]}")
    ok &= REC.expect("answered from the defect-register fast path",
                     quick == "defect_register", f"quick={quick!r}")
    ok &= REC.expect(f"the count matches the file ({len(open_ids)} open)",
                     f"{len(open_ids)} open" in answer,
                     f"file has {len(open_ids)} open of {total}")
    ok &= REC.expect("the answer names docs/defect-register.tsv",
                     "defect-register.tsv" in answer, "")
    today = datetime.now().strftime("%Y-%m-%d")
    ok &= REC.expect(f"the answer names the date it read ({today})",
                     today in answer,
                     "expected today's YYYY-MM-DD read date")
    if "no-checkout" in answer.lower() or "no checkout" in answer.lower() or \
            "not there" in answer.lower():
        REC.info("the deployed build could not find a checkout: set "
                 "JARVIS_REVIEW_REPO to this repository (or JARVIS_DEFECT_REGISTER "
                 "to the tsv) in the environment that starts Jarvis, then restart it")

    target = next((r for r in rows if str(r.get("id")) == "DEF-089"), None)
    one = chat("what is DEF-089", timeout=180, provenance=True)
    text = turns_spend_answer(one)
    quick = (one.route or {}).get("quick")
    print(f"\n  Q: what is DEF-089")
    print(f"  quick={quick!r}  A: {' '.join(text.split())[:400]}")
    ok &= REC.expect("DEF-089 answered from the defect-register fast path",
                     quick == "defect_register", f"quick={quick!r}")
    if target is None:
        ok &= REC.fail("DEF-089 exists in the register", "the file has no DEF-089 row")
    else:
        files = [p.strip() for p in str(target.get("files") or "").split(";") if p.strip()]
        evidence = norm(str(target.get("evidence") or ""))
        ok &= REC.expect("DEF-089's status is described from its row",
                         str(target.get("status") or "") in text, "")
        ok &= REC.expect("DEF-089's files are named from its row",
                         any(os.path.basename(f) in text for f in files),
                         f"row files: {files[:2]}")
        ok &= REC.expect("a quote of DEF-089's own evidence appears",
                         bool(evidence) and has(text, evidence[:60]),
                         f"row evidence starts {evidence[:60]!r}")
        ok &= REC.expect("DEF-089's answer names the read date",
                         bool(ISO_DATE_RE.search(text)), "")
    REC.end("PASS" if ok else "FAIL",
            "the register count and DEF-089 both came from the file"
            if ok else "the defect register answer did not match its own file")


# ---- pictures -> PDF, format conversion -----------------------------------
def _pdf_pages_and_streams(data):
    pages = len(re.findall(rb"/Type\s*/Page\b(?!s)", data))
    return pages


def section_pictures():
    if not _section_feature_gate(
            "PICTURES", "pictures into ONE PDF (byte-lossless for JPEG) and one "
            "picture into another format (PR #1368)",
            "jarvis_image_convert.py", "def convert(",
            "the deployed jarvis_image_convert.py, Pillow and img2pdf"):
        return
    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        return REC.skip(f"Pillow is not importable for this Python ({type(exc).__name__}) "
                        f"- cannot make or verify throwaway pictures")
    module, why = live_module("jarvis_image_convert")
    if module is None:
        return REC.skip(f"the deployed converter could not be imported ({why})")
    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return REC.skip(f"the throwaway folder could not be made ({exc})")
    ok = True
    made = []
    try:
        jpeg_a = ARTIFACT_DIR / "field-battery-a.jpg"
        jpeg_b = ARTIFACT_DIR / "field-battery-b.jpg"
        Image.new("RGB", (48, 32), (200, 30, 30)).save(jpeg_a, "JPEG")
        Image.new("RGB", (32, 48), (30, 30, 200)).save(jpeg_b, "JPEG")
        made += [jpeg_a, jpeg_b]
        raw_a = jpeg_a.read_bytes()
        raw_b = jpeg_b.read_bytes()
        REC.info(f"made two throwaway JPEGs in {ARTIFACT_DIR} "
                 f"({len(raw_a)} and {len(raw_b)} bytes)")

        tier = ""
        try:
            tier = str(module._tier(module.ACTION))
        except Exception as exc:  # noqa: BLE001
            tier = f"unreadable ({type(exc).__name__})"
        ok &= REC.expect("the conversion gate tier is ask (one card per file written)",
                         tier == "ask", f"deployed tier={tier!r}")

        try:
            state, card = module.prepare(
                {"action": "convert", "to": "pdf", "paths": [str(jpeg_a), str(jpeg_b)]},
                tier_of=lambda _action: "ask")
        except Exception as exc:  # noqa: BLE001
            ok &= REC.fail("the PDF conversion was prepared by the deployed module",
                           str(exc)[:300])
            state = None
        if state:
            result = module.convert(state)
            path = Path(str(result.get("path") or ""))
            made.append(path)
            ok &= REC.expect("the deployed converter wrote the PDF",
                             bool(result.get("ok")) and path.is_file(),
                             str(result.get("error") or "")[:250])
            if path.is_file():
                data = path.read_bytes()
                ok &= REC.expect("the product opens as a PDF", data.startswith(b"%PDF-"),
                                 data[:8].decode("latin-1"))
                pages = _pdf_pages_and_streams(data)
                ok &= REC.expect("the PDF has the right page count (2)", pages == 2,
                                 f"{pages} page(s)")
                ok &= REC.expect("the first original JPEG's bytes are in the PDF",
                                 raw_a in data, "byte-for-byte stream copy")
                ok &= REC.expect("the second original JPEG's bytes are in the PDF",
                                 raw_b in data, "byte-for-byte stream copy")

        out_png = ARTIFACT_DIR / "field-battery-converted.png"
        try:
            state2, _card2 = module.prepare(
                {"action": "convert", "to": "png", "out": str(out_png),
                 "path": str(jpeg_a)},
                tier_of=lambda _action: "ask")
        except Exception as exc:  # noqa: BLE001
            state2 = None
            ok &= REC.fail("the format conversion was prepared", str(exc)[:300])
        if state2:
            result2 = module.convert(state2)
            got = Path(str(result2.get("path") or ""))
            made.append(got)
            ok &= REC.expect("the format conversion wrote a file",
                             bool(result2.get("ok")) and got.is_file(),
                             str(result2.get("error") or "")[:250])
            if got.is_file():
                data = got.read_bytes()
                ok &= REC.expect("the output is really the requested format (PNG)",
                                 data.startswith(b"\x89PNG\r\n\x1a\n"),
                                 got.suffix)
                try:
                    with Image.open(got) as image:
                        ok &= REC.expect("the converted picture opens and keeps its size",
                                         image.size == (48, 32), f"{image.size}")
                except Exception as exc:  # noqa: BLE001
                    ok &= REC.fail("the converted picture opens", f"{type(exc).__name__}")
    finally:
        shutil.rmtree(ARTIFACT_DIR, ignore_errors=True)
    ok &= REC.expect("the throwaway folder and its files are gone",
                     not ARTIFACT_DIR.exists(), str(ARTIFACT_DIR))
    REC.info("the chat -> tool -> approval-card path is NOT exercised here: the "
             "deployed module is driven directly (no card is raised, nothing outside "
             "the throwaway folder is written)")
    REC.end("PASS" if ok else "FAIL",
            "one PDF from two JPEGs with the original streams inside, and a PNG "
            "conversion" if ok else "the picture conversion row did not prove itself")


# ---- audio attach ----------------------------------------------------------
#: The words the synthesised sample says. The sample is made on this PC by
#: Windows' own speech synthesiser (System.Speech, no network, no owner voice,
#: nothing private), so the transcript has a known reference - a missing sample
#: is a SKIP, never a pass.
SPEECH_WORDS = ("field battery test", "quick brown fox")


def _synth_speech_sample():
    """(path, why): a throwaway WAV saying SPEECH_WORDS, or (None, why)."""
    path = Path(tempfile.gettempdir()) / f"field-battery-speech-{STAMP}.wav"
    quoted = str(path).replace("'", "''")
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{quoted}'); "
              "$s.Speak('field battery test. one two three. the quick brown fox.'); "
              "$s.Dispose()")
    code, out, err = run(["powershell.exe", "-NoProfile", "-NonInteractive",
                          "-Command", script], timeout=90)
    if path.is_file() and path.stat().st_size > 6000:
        return path, ""
    return None, norm(err or out)[:200] or "the synthesised WAV was not written"


def section_audio():
    if not _section_feature_gate(
            "AUDIO", "a recording attached to chat is read and transcribed, with no "
            "old '(ValueError)' (PR #1366)",
            "jarvis_media_read.py", "def read_media_bytes(",
            "the deployed audio reader and a synthesised speech sample"):
        return
    attached, why = live_module("jarvis_attached_file")
    if attached is None:
        return REC.skip(f"the deployed jarvis_attached_file could not be imported ({why})")
    if "RECORDING_KINDS" not in live_text("jarvis_attached_file.py"):
        return REC.skip("not in this deployed build: jarvis_attached_file.py has no "
                        "RECORDING_KINDS")
    sample, synth_why = _synth_speech_sample()
    if sample is None:
        return REC.skip("no speech sample could be made on this machine "
                        f"({synth_why}) - a missing sample is never a pass")
    ok = True
    try:
        raw = sample.read_bytes()
        try:
            with wave.open(str(sample)) as handle:
                seconds = handle.getnframes() / max(handle.getframerate(), 1)
        except wave.Error:
            seconds = 0.0
        REC.info(f"synthesised sample: {sample.name} ({len(raw)} bytes, "
                 f"{seconds:.1f}s) - says {SPEECH_WORDS!r}; made for this run and "
                 f"deleted afterwards")
        payload = {"name": "field-battery-recording.wav", "size": len(raw),
                   "data": base64.b64encode(raw).decode("ascii")}
        try:
            result = attached.read(payload)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "why": f"raised {type(exc).__name__}: {exc}"}
        words = str(result.get("words") or "")
        refused = str(result.get("refusal") or result.get("said")
                      or result.get("why") or "")
        print(f"  module read (the same reader the server uses): ok={result.get('ok')} "
              f"kind={result.get('kind')!r}")
        print(f"  words: {' '.join(words.split())[:280]!r}")
        print(f"  refusal/why: {' '.join(refused.split())[:280]!r}")
        ok &= REC.expect("the recording was recognised as a recording",
                         str(result.get("kind") or "") == "recording",
                         f"kind={result.get('kind')!r}")
        ok &= REC.expect("no old 'could not be read (ValueError)' answer",
                         "ValueError" not in words + refused, "")
        ok &= REC.expect("words came back from the recording",
                         bool(result.get("ok")) and len(norm(words)) >= 8,
                         f"{len(norm(words))} characters of transcript")
        low_words = norm(words).lower()
        ok &= REC.expect("the transcript carries the words that were spoken",
                         "battery" in low_words and "fox" in low_words,
                         f"expected {SPEECH_WORDS!r} in the words")
        turn = chat("Transcribe the recording I attached and say what it says.",
                    timeout=300, attachment=payload)
        answer = turns_spend_answer(turn)
        print(f"\n  HTTP attach: status={turn.status} route="
              f"{json.dumps({k: (turn.route or {}).get(k) for k in ('gate', 'where') if k in (turn.route or {})})}")
        print(f"  A: {' '.join(answer.split())[:320]}")
        ok &= REC.expect("the chat accepted the attachment",
                         turn.status == 200 and not turn.error,
                         f"HTTP {turn.status} {turn.error}".strip())
        if ("approval" in answer.lower() or "waiting" in answer.lower()
                or (turn.route or {}).get("quick") == "file_gate_waiting"):
            approved, card_id, card_why = approve_own_card(
                ["field-battery-recording"])
            REC.info(f"attachment card: approved={approved} id={card_id or '-'} "
                     f"({card_why}) - only a card naming our own sample")
        ok &= REC.expect("the reply does not carry the old reader error",
                         "could not be read (ValueError)" not in answer
                         and "ValueError" not in answer, "")
        ok &= REC.expect("the reply is not a refusal or a denial",
                         bool(answer) and not DENY_RE.search(answer)
                         and "not a kind jarvis reads" not in norm(answer).lower(), "")
    finally:
        try:
            sample.unlink()
        except OSError:
            pass
    REC.end("PASS" if ok else "FAIL",
            "the synthesised recording was read, transcribed with its known words, "
            "and accepted over the attach path"
            if ok else "the audio row did not prove itself")


# ---- lane_service fails closed --------------------------------------------
def section_lane_service():
    if not _section_feature_gate(
            "LANE-SERVICE", "jarvis_chatbot_api.lane_service fails closed: an unknown "
            "lane names no service and no URL (PR #1384)",
            "jarvis_chatbot_api.py", "LANE_UNKNOWN",
            "the deployed jarvis_chatbot_api module (a unit-level check, not live)"):
        return
    module, why = live_module("jarvis_chatbot_api")
    if module is None:
        return REC.skip(f"the deployed jarvis_chatbot_api could not be imported ({why})")
    lane_service = getattr(module, "lane_service", None)
    if not callable(lane_service):
        return REC.fail("the deployed module has lane_service") or \
            REC.end("FAIL", "lane_service is missing from the deployed module")
    ok = True
    known = []
    presets = getattr(module, "PRESETS", {}) or {}
    known = list(presets.keys())[:2]
    print(f"  deployed PRESETS: {known}")
    try:
        unknown = lane_service("field-battery-no-such-lane")
        local = lane_service("")
        real = lane_service("jarvis-escalate")
        model_name = lane_service("qwen3.5:9b")
    except Exception as exc:  # noqa: BLE001
        return REC.fail("lane_service could be called", f"{type(exc).__name__}: {exc}") \
            or REC.end("FAIL", "lane_service raised")
    print(f"  lane_service('field-battery-no-such-lane') = {unknown!r}")
    print(f"  lane_service('') = {local!r}; lane_service('qwen3.5:9b') = {model_name!r}")
    print(f"  lane_service('jarvis-escalate') = {real!r}")
    ok &= REC.expect("an unknown lane name gets NO service and NO model",
                     tuple(unknown) == ("", ""), f"{unknown!r}")
    ok &= REC.expect("a local model's name is not turned into a cloud service",
                     tuple(model_name) == ("", ""), f"{model_name!r}")
    ok &= REC.expect("the empty name still means local",
                     tuple(local) == ("", ""), f"{local!r}")
    ok &= REC.expect("a real lane still resolves to a service and a model",
                     bool(real and real[0]) and bool(real[1])
                     and (not presets or real[0] in presets), f"{real!r}")
    cloud_lane = getattr(module, "cloud_lane", None)
    if callable(cloud_lane):
        try:
            got = cloud_lane("field-battery-no-such-lane")
            ok &= REC.expect("cloud_lane(unknown) names nothing", got is None, repr(got))
        except Exception as exc:  # noqa: BLE001
            ok &= REC.fail("cloud_lane(unknown) could be called",
                           f"{type(exc).__name__}: {exc}")
    lane_state = getattr(module, "lane_state", None)
    if callable(lane_state):
        try:
            state = lane_state("field-battery-no-such-lane")
            url = str(state.get("url") or "") if isinstance(state, dict) else ""
            pid = str(state.get("pid") or "") if isinstance(state, dict) else ""
            ok &= REC.expect("an unknown lane has no URL and no service in its state",
                             not url and not pid,
                             f"pid={pid!r} url={url!r}")
        except Exception as exc:  # noqa: BLE001
            REC.info(f"lane_state(unknown) raised {type(exc).__name__} - not counted")
    REC.end("PASS" if ok else "FAIL",
            "an unknown lane is not a cloud lane, the empty name is local, a real "
            "lane resolves" if ok else "lane_service did not fail closed")


# ---- fallback guard --------------------------------------------------------
def section_fallback():
    if not _section_feature_gate(
            "FALLBACK", "degraded_from appears only when a model was substituted "
            "(PR #1378)", "jarvis_router.py", "MODEL_CANNOT_RUN_HERE",
            "a fresh local turn and the deployed router"):
        return
    turn = chat("Write one short sentence about the sea.", timeout=300)
    answer = turns_spend_answer(turn)
    route = turn.route or {}
    print(f"  ordinary local turn: status={turn.status} answer={answer[:120]!r}")
    print(f"  route keys: {sorted(route.keys())}")
    ok = True
    ok &= REC.expect("the ordinary turn answered", bool(answer),
                     f"HTTP {turn.status} {turn.error}".strip())
    ok &= REC.expect("the ordinary turn stayed local", route.get("where") == "local",
                     f"where={route.get('where')!r}")
    ok &= REC.expect("degraded_from is ABSENT (not empty) on an ordinary turn",
                     "degraded_from" not in route,
                     f"degraded_from={route.get('degraded_from')!r}")

    router, why = live_module("jarvis_router")
    situation = {}
    lane_url = f"http://127.0.0.1:{EVERYDAY_PORT}"
    model_state, _ = read_json(MODEL_STATE)
    current = ""
    if isinstance(model_state, dict):
        current = str(model_state.get("current") or model_state.get("model") or "")
    if router is not None and current:
        probe = getattr(router, "local_model_fallback", None)
        if callable(probe):
            try:
                situation = probe(current, lane_url) or {}
            except Exception as exc:  # noqa: BLE001
                REC.info(f"local_model_fallback raised {type(exc).__name__} - "
                         f"situation treated as absent")
    if situation:
        REC.info(f"substitution situation present: saved model {current!r} -> "
                 f"{situation.get('model')!r}")
        turn2 = chat("Write one short sentence about the sky.", timeout=300)
        route2 = turn2.route or {}
        entries = route2.get("degraded_from") or []
        print(f"  substituted turn route: "
              f"{json.dumps({k: route2.get(k) for k in ('lane', 'degraded_from')}, ensure_ascii=False)[:500]}")
        ok &= REC.expect("the substituted turn carries degraded_from",
                         isinstance(entries, list) and bool(entries),
                         f"entries={entries!r}")
        if entries:
            first = entries[0] if isinstance(entries[0], dict) else {}
            ok &= REC.expect("its code is model_cannot_run_on_this_lane",
                             first.get("code") == "model_cannot_run_on_this_lane",
                             str(first.get("code")))
            ok &= REC.expect("the header's lane is the model that really ran",
                             route2.get("lane") == first.get("model"),
                             f"lane={route2.get('lane')!r} model={first.get('model')!r}")
        REC.end("PASS" if ok else "FAIL",
                "a model substitution is named in degraded_from and an ordinary "
                "turn omits it" if ok else "the fallback guard did not prove itself")
    else:
        REC.info("no substitution situation exists right now: the saved everyday "
                 f"model {current or '(unknown)'!r} fits its lane, so the positive "
                 "half cannot be measured")
        if ok:
            REC.end("SKIP", "situation absent - the ordinary turn omitted "
                            "degraded_from (checked), but no model substitution "
                            "happened to prove the positive half")
        else:
            REC.end("FAIL", "the ordinary turn's route detail is wrong")


# ---------------------------------------------------------------------------
#   self-test: the GITHUB "there is nothing" rules (offline, no HUD)
# ---------------------------------------------------------------------------
def self_test_github():
    """Offline proof of the GITHUB comparison rules.

    The three empty-queue rules fixed on 2026-11-19, plus ruling 5.2 (2026-11-20):
    a still-going check is never accepted as a failure, and an answer using the
    failing words is never accepted for the running-checks question.

    No network, no gh, no HUD, no token, no money: it feeds the EXACT answers the
    deployed build gave against the empty queue (and wrong answers a model could
    invent instead) to the same predicates `section_github` uses, and requires
    every honest answer to be accepted and every wrong one to be refused.

    Run it with:  py -3 .dsh-scratch/wave21/field-battery/run_battery.py --self-test
    """
    print("=" * 78)
    print("SELF-TEST - the GITHUB comparison rules, empty-state and ruling 5.2 "
          "(offline)")
    print("=" * 78)

    honest_ready = [
        # The measured answer of the deployed build on 2026-11-19, empty queue.
        "There are no open pull requests on darknight11ish/Epic-Jarvis.",
        "None are ready to merge.",
        "There is nothing ready to merge right now.",
        "No pull requests are ready to merge.",
        "The ready-to-merge queue is empty.",
        "There are 0 open pull requests.",
    ]
    wrong_ready = [
        "PR #1400 is ready to merge.",
        "There are no open pull requests, but #1400 is ready to merge.",
        "None are ready, and all checks have passed.",
        "3 open pull requests are ready to merge.",
        "Which repository? Give me the owner/name.",
        "I cannot see the pull requests, so none are ready.",
    ]
    honest_branches = [
        # The measured answer of the deployed build on 2026-11-19, empty queue.
        "The unmerged work on darknight11ish/Epic-Jarvis is in these open pull "
        "requests; a branch with no pull request is not something this read can "
        "see. There are no open pull requests on that repository.",
        "There are no open pull requests, so there is no unmerged work I can see.",
        "None.",
        "Nothing is unmerged that this read can see.",
    ]
    wrong_branches = [
        "There are 4 unmerged branches: fix/a, fix/b, fix/c, fix/d.",
        "There are no open pull requests; all checks are green.",
        "PR #1400 has work that is not merged.",
        "I cannot access the branch list.",
        "There are 0 unmerged branches, 3 open pull requests remain.",
    ]
    defect_cases = [
        # (answer, the register's open count, expected, what the case proves)
        ("The defect register has 38 open and 51 closed - 89 rows in all. I read "
         "docs/defect-register.tsv on this PC on 2026-11-19.",
         38, True, "the answer the deployed build gave"),
        ("The defect register has 37 open and 52 closed - 89 rows in all. I read "
         "docs/defect-register.tsv on this PC on 2026-11-19.",
         38, False, "the stale worktree's count"),
        ("The defect register has 138 open and 51 closed. I read "
         "docs/defect-register.tsv on this PC on 2026-11-19.",
         38, False, "'38' hidden inside a wrong '138'"),
        ("The defect register has 38 closed and 51 open. I read "
         "docs/defect-register.tsv on this PC on 2026-11-19.",
         38, False, "the count is the CLOSED column, not the status=open one"),
        ("There are 38 open defects in the register.", 38, False,
         "the answer names no file"),
    ]
    # RULING 5.2 (2026-11-20): the two CI questions' comparison rules. The
    # failing question is asked only about a SETTLED pull request (a failed
    # check and no pending one); the running question about a pull request whose
    # checks are pending and none failed. A still-going run is NEVER accepted as
    # a failure, and an answer using the failing words is never accepted for the
    # running question - that is the deploy #4 bug, in words.
    failing_cases = [
        # (the answer, PR number, gh fail names, expected, what it proves)
        ("The checks on pull request #1400 in darknight11ish/Epic-Jarvis are NOT "
         "all green.\n1 failing check(s):\n  rust: failure",
         1400, ["rust"], True, "the failing answer the fixed build gives"),
        ("GitHub reports no check runs on pull request #1400 in "
         "darknight11ish/Epic-Jarvis; 2 CI runs are still going: CI, Jarvis "
         "client. Nothing is known about them yet - ask again when they finish.",
         1400, ["rust"], False, "a still-going answer is not a failing one"),
        ("There is no failing check on pull request #1400.",
         1400, ["rust"], False, "a 'nothing is failing' answer is refused"),
    ]
    running_cases = [
        # (the answer, PR number, gh pending names, expected, what it proves)
        ("The checks on pull request #1401 in darknight11ish/Epic-Jarvis have "
         "not all finished: audit, backend-shard (3/4). Nothing is known about "
         "them yet - ask again when they finish.",
         1401, ["audit"], True, "the running answer the fixed build gives"),
        ("GitHub reports no check runs on pull request #1401 in "
         "darknight11ish/Epic-Jarvis; 2 CI runs are still going: CI, Jarvis "
         "client. Nothing is known about them yet - ask again when they finish.",
         1401, ["CI"], True, "the no-check-runs pending sentence"),
        ("The checks on pull request #1401 are NOT all green. 1 failing check(s): "
         "audit: failure", 1401, ["audit"], False,
         "failing words are never accepted for the running question"),
        ("Did not finish successfully - pull request #1401 has failures.",
         1401, ["audit"], False, "the old false-failure sentence is refused"),
    ]

    failed = []
    total = 0

    def case(label, got, want, detail):
        nonlocal total
        total += 1
        good = (got == want)
        print(f"  {'PASS' if good else 'FAIL'}  {label}: {detail}")
        if not good:
            failed.append(label)

    print("\n  fix 1 - 'ready to merge', empty queue (gh says none are CLEAN):")
    for answer in honest_ready:
        ok, why = empty_answer_ok(answer)
        case("honest", ok, True, f"accepted {answer!r}"
             + ("" if ok else f" - refused: {why}"))
    for answer in wrong_ready:
        ok, why = empty_answer_ok(answer)
        case("wrong", ok, False, f"REFUSED {answer!r}"
             + (f" ({why})" if not ok else " - ACCEPTED a wrong answer"))

    # The same empty CLEAN set, but the queue HAS open pull requests (none of
    # them CLEAN): the honest answer may name the real open count, and a wrong
    # count or a made-up number still FAILs.
    open_queue = (1397, 1398, 1399)
    honest_open_queue = [
        "Of the 3 open pull requests, none are ready to merge.",
        "None of the 3 open pull requests are ready to merge.",
    ]
    wrong_open_queue = [
        "None are ready to merge, except #1404.",
        "4 open pull requests, none are ready to merge.",
    ]
    print("\n  fix 1b - 'ready to merge', open queue but none CLEAN:")
    for answer in honest_open_queue:
        ok, why = empty_answer_ok(answer, open_queue)
        case("honest", ok, True, f"accepted {answer!r}"
             + ("" if ok else f" - refused: {why}"))
    for answer in wrong_open_queue:
        ok, why = empty_answer_ok(answer, open_queue)
        case("wrong", ok, False, f"REFUSED {answer!r}"
             + (f" ({why})" if not ok else " - ACCEPTED a wrong answer"))

    print("\n  fix 2 - 'unmerged branches', no open pull requests:")
    for answer in honest_branches:
        ok, why = empty_answer_ok(answer)
        case("honest", ok, True, f"accepted {answer!r}"
             + ("" if ok else f" - refused: {why}"))
    for answer in wrong_branches:
        ok, why = empty_answer_ok(answer)
        case("wrong", ok, False, f"REFUSED {answer!r}"
             + (f" ({why})" if not ok else " - ACCEPTED a wrong answer"))

    print("\n  fix 3 - the defect count comes from the register's `status` column:")
    for answer, count, want, detail in defect_cases:
        got = defect_answer_ok(answer, count)
        case("count", got, want, f"{detail}: {answer[:72]!r}"
             + ("" if got == want else " - WRONG"))

    print("\n  ruling 5.2 - 'failing checks', a settled PR (gh: failed, no pending):")
    for answer, pr, names, want, detail in failing_cases:
        got = _failing_answer_ok(answer, pr, names)
        case("failing", got, want, f"{detail}: {answer[:64]!r}"
             + ("" if got == want else " - WRONG"))
    print("\n  ruling 5.2 - 'running checks', a pending PR (gh: pending, no failed):")
    for answer, pr, names, want, detail in running_cases:
        got = _pending_answer_ok(answer, pr, names)
        case("pending", got, want, f"{detail}: {answer[:64]!r}"
             + ("" if got == want else " - WRONG"))

    # The old substring rule, shown once on the honest answer it failed.
    honest_ready_text = honest_ready[0]
    old = ("none" in honest_ready_text.lower()
           or "not ready" in honest_ready_text.lower()
           or "no pull request" in honest_ready_text.lower())
    print("\n  NOTE  the pre-fix rule on that honest answer: "
          f"'none' / 'not ready' / 'no pull request' substrings -> {old} "
          "(it used to FAIL the correct answer)")
    print(f"\n  {total - len(failed)}/{total} self-test cases as expected"
          + ("" if not failed else f"; FAILED: {', '.join(failed)}"))
    print("  RESULT: " + ("PASS - honest empty answers accepted, wrong answers "
                          "still refused" if not failed else
                          "FAIL - a rule does not recognise the answer it must"))
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
#   main
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#   The project store's answers, the scoped chat and the bounded cloud answer
#   (2026-11-20). The battery had no row for any of them, so the three features
#   PM1 and the project-chat lane shipped were merged, field-checked by hand -
#   and unguarded by the repeatable run. These are those checks, made repeatable.
# ---------------------------------------------------------------------------

PROJECTS_DB = SETTINGS / "projects.db"


def read_project_rows(db=None):
    """Read-only: (count, [{"id","name"}, ...]). Never opens the store for writing."""
    path = Path(db) if db is not None else PROJECTS_DB
    if not path.is_file():
        return 0, []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = [dict(zip(("id", "name"), r))
                    for r in con.execute("select id, name from projects order by created")]
        finally:
            con.close()
        return len(rows), rows
    except Exception:  # noqa: BLE001 - an unreadable store is reported, not crashed
        return -1, []


def section_project_answers():
    if not _section_feature_gate(
            "PROJECT-ANSWERS", "the project store's three answers from projects.db "
            "(PM1, 2026-11-20)", "jarvis_quick.py", '"project_working"',
            "the PM1 reads in the deployed quick lane"):
        return
    today = datetime.now().strftime("%Y-%m-%d")
    count, rows = read_project_rows()
    if count < 0:
        return REC.fail("projects.db is readable for the count", str(PROJECTS_DB))
    REC.info(f"projects.db holds {count} project(s): "
             + ", ".join(r["name"] for r in rows[:4]))
    for question, intent in (
            ("What am I working on?", "project_working"),
            ("What should I work on next?", "project_next"),
            ("What's blocking Jarvis?", "project_blocking")):
        turn = chat(question, timeout=180, provenance=True)
        route = turn.route or {}
        reply = turns_spend_answer(turn)
        REC.expect(f"{question!r} is answered by {intent}, not the model",
                   route.get("quick") == intent, f"quick={route.get('quick')!r}")
        REC.expect("... and it names projects.db and the date it read",
                   "projects.db" in reply and today in reply, reply[:200])
    # The honest empty is only honest when the store is proven empty.
    if count == 0:
        turn = chat("What should I work on next?", timeout=180, provenance=True)
        REC.expect("with no plan rows the next answer is the honest empty",
                   "Nothing is ready to work on right now"
                   in (turns_spend_answer(turn) or ""),
                   (turns_spend_answer(turn) or "")[:200])
    else:
        REC.info("plan rows exist, so no empty answer is expected; the store's own "
                 "contents are what the three answers must agree with")
    REC.end("PASS", "the three project answers come from the store, naming it and the day")


def section_project_chat():
    if not _section_feature_gate(
            "PROJECT-CHAT", "a chat can belong to a project (2026-11-20)",
            "jarvis_quick.py", '"project_unknown"',
            "the project-scoped chat in the deployed quick lane"):
        return
    count, rows = read_project_rows()
    if count <= 0:
        return REC.skip(f"no project to scope a chat to ({count} in projects.db)")
    project = rows[0]
    turn = chat("What's next on this project?", project=project["id"],
                timeout=180, provenance=True)
    route = turn.route or {}
    got = route.get("project") or {}
    REC.expect("a chat scoped by the project's id resolves it",
               isinstance(got, dict) and got.get("id") == project["id"],
               repr(got))
    REC.expect("... and the scoped answer names the stores it read",
               "projects.db" in (turns_spend_answer(turn) or ""),
               (turns_spend_answer(turn) or "")[:200])
    turn = chat("What's next on this project?", project=project["name"],
                timeout=180, provenance=True)
    got = (turn.route or {}).get("project") or {}
    REC.expect("... and so does one scoped by the project's own name",
               isinstance(got, dict) and got.get("id") == project["id"], repr(got))
    turn = chat("What's next on this project?", project="0" * 32,
                timeout=180, provenance=True)
    reply = turns_spend_answer(turn) or ""
    REC.expect("an id that is not a project is refused plainly",
               "no project with the id" in reply.lower() and "nothing was changed" in reply.lower(),
               reply[:220])
    turn = chat("What's next on this project?", timeout=180, provenance=True)
    route = turn.route or {}
    REC.expect("the control: with no project the route carries no project key",
               "project" not in route, repr(route.get("project")))
    REC.expect("... and the model answers it, exactly as before the lane",
               route.get("quick") is None, f"quick={route.get('quick')!r}")
    REC.end("PASS", "by id and by name, an unknown id refused, and no project unchanged")


#: PM4 (2026-11-21): the plan read and the export door both apps share. These
#: rows are READ-ONLY: the plan read writes nothing, and the export door is
#: proven POST-only by a GET (405) and by POSTing an id that is not a project
#: (404) - never by raising the owner's export card on a real project.
_PM4_PLAN_KEYS = ("objective", "milestones", "work_items", "ready", "events", "counts")


def _plan_shape_ok(plan):
    """(ok, why) for an `/api/projects/<id>/plan` answer's own counts and bounds.

    The answer carries `counts` as the store's TRUE totals while the lists may be
    bounded (`ready` at 20, `events` at the newest 100), so a count is never
    required to equal a list length - only to be at least it. A list that names
    something the plan does not hold is a refusal.
    """
    if not isinstance(plan, dict):
        return False, f"not a JSON object ({type(plan).__name__})"
    missing = [key for key in _PM4_PLAN_KEYS if key not in plan]
    if missing:
        return False, f"missing key(s): {missing}"
    counts = plan.get("counts") if isinstance(plan.get("counts"), dict) else None
    if counts is None:
        return False, "counts is not an object"
    for key in ("milestones", "work_items", "ready", "events"):
        rows = plan.get(key)
        if not isinstance(rows, list):
            return False, f"{key} is not a list"
        if not isinstance(counts.get(key), int):
            return False, f"counts.{key} is not a number"
        if counts[key] < len(rows):
            return False, f"counts.{key}={counts[key]} but {len(rows)} row(s) are listed"
    if len(plan.get("ready") or []) > 20:
        return False, f"ready lists {len(plan['ready'])}, the route bounds it at 20"
    if len(plan.get("events") or []) > 100:
        return False, f"events lists {len(plan['events'])}, the route bounds it at 100"
    ids = {str(item.get("id")) for item in plan.get("work_items") or []
           if isinstance(item, dict)}
    unknown = [rid for rid in plan.get("ready") or [] if str(rid) not in ids]
    if unknown:
        return False, f"ready names item(s) the plan does not hold: {unknown[:3]}"
    return True, ""


def section_pm4():
    REC.header("PM4", "the plan read both apps share, and the export door "
               "(2026-11-21)", "/api/projects + /plan + /export")
    if not STATE["ready"]:
        return REC.skip("preflight failed")
    status, projects, _, err = http_json("/api/projects")
    items = (projects or {}).get("projects") if isinstance(projects, dict) else None
    if status != 200 or not isinstance(items, list) or not items:
        REC.fail("GET /api/projects answers with a project to read", f"HTTP {status} {err}".strip())
        return REC.end("FAIL", "the project list could not be read")
    project = items[0]
    pid = project.get("id")
    status, plan, _, err = http_json(f"/api/projects/{pid}/plan")
    if status == 404:
        return REC.skip("the deployed build has no PM4 plan read (older release)")
    ok, why = _plan_shape_ok(plan)
    REC.expect("the plan read answers with its own keys and true counts", ok, why)
    if ok:
        REC.info(f"plan: {plan['counts'].get('work_items')} work item(s), "
                 f"{len(plan.get('ready') or [])} ready listed, "
                 f"{len(plan.get('events') or [])} event(s) listed")
        status2, again, _, _ = http_json(f"/api/projects/{pid}/plan")
        REC.expect("reading it twice changes nothing", status2 == 200 and again == plan,
                   "the second read differed" if again != plan else "")
        empty_honest = not (plan.get("work_items") or [])
        REC.expect("an empty plan is the honest empty, not a made-up row",
                   (not empty_honest) or (not (plan.get("ready") or [])
                                          and not (plan.get("milestones") or [])),
                   f"work_items={len(plan.get('work_items') or [])} "
                   f"ready={len(plan.get('ready') or [])}")
    status, bad, _, err = http_json(f"/api/projects/{'0' * 32}/plan")
    REC.expect("a plan read for an id that is not a project is refused", status == 404,
               f"HTTP {status} {err}".strip())
    status, doc, _, _ = http_json(f"/api/projects/{pid}/export")
    REC.expect("the export door is POST-only (a GET cannot write)", status == 405,
               f"HTTP {status}")
    status, doc, _, _ = http_json(f"/api/projects/{'0' * 32}/export", method="POST",
                                  body={})
    said = str(doc.get("error") if isinstance(doc, dict) else doc).lower()
    REC.expect("... and an id that is not a project is refused before any card",
               status == 404 and "no such project" in said, f"HTTP {status} {said[:160]}")
    return REC.end("PASS", "the plan read carries its own counts, twice identical, "
                           "and the export door answers 405/404 without a write")


def section_bounded_cloud():
    if not _section_feature_gate(
            "CLOUD-BOUND", "the cloud answer is bounded (PR #1408, 2026-11-19)",
            "jarvis_chatbot_api.py", "cloud_request_body",
            "the answer-bound composer in the deployed chat API"):
        return
    route = STATE.get("c5_route") or {}
    length = STATE.get("c5_answer_len")
    if not route:
        return REC.skip("C5 did not run, so there is no escalated turn to measure")
    REC.info(f"C5's escalated answer was {length} characters")
    REC.expect("the escalated turn really did reach the cloud",
               route.get("where") == "cloud", repr(route))
    # 4,096 tokens is the standard ceiling; a character is never fewer than one
    # token, so a long answer would show up well past this generous bound.
    REC.expect("the answer came back bounded, not unbounded",
               isinstance(length, int) and 0 < length <= 4096 * 4,
               f"{length} characters")
    turn = chat("Compare SQLite and PostgreSQL for a small inventory app.",
                timeout=180, provenance=True)
    route = turn.route or {}
    REC.expect("the control: a medium question still stays local",
               route.get("where") == "local",
               f"where={route.get('where')!r} complexity={route.get('complexity')!r}")
    REC.end("PASS", "the escalated answer is bounded and a medium question stays local")


def main(only=None, allow_stale_cloud=False):
    print("=" * 78)
    print("JARVIS FIELD BATTERY - one run against the DEPLOYED build")
    print("=" * 78)
    print(f"  started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  live backend: {LIVE}")
    print(f"  HUD: {BASE}")
    print(f"  checkout: {REPO}")
    print(f"  throwaway marker: {MARKER}")
    print("  spends money ONLY in sections C5 (one hard cloud question) and EFFICIENCY")
    print("  (up to four, behind an announced maximum and a remaining-cap check); every")
    print("  other row is read-only or writes only its own throwaway artifact, removed again.")
    print("  a token, key or private fact is never printed.")

    sections = [
        section_preflight,
        section_build,
        section_cloud_escalation,
        section_cloud_efficiency,
        section_cloud_privacy,
        section_github,
        section_capabilities,
        section_cap_exact,
        section_presets,
        section_notes,
        section_favourites,
        section_cloud_settings,
        section_defects,
        section_pictures,
        section_audio,
        section_lane_service,
        section_fallback,
        section_project_answers,
        section_project_chat,
        section_pm4,
        section_bounded_cloud,
    ]
    if only:
        wanted = [sec for sec in sections if sec.__name__ == only]
        if not wanted:
            print(f"unknown section: {only!r} (have: "
                  + ", ".join(sec.__name__ for sec in sections) + ")")
            return 2
        # PREFLIGHT always runs: a later row needs STATE["ready"] to mean
        # something, and a section run on an unchecked build is not a proof.
        sections = [section_preflight] + [sec for sec in wanted
                                          if sec is not section_preflight]
    for section in sections:
        try:
            section()
        except KeyboardInterrupt:
            print("\n  interrupted by the owner - stopping")
            REC.end("FAIL", "interrupted")
            break
        except Exception as exc:  # noqa: BLE001 - one broken row never hides the rest
            print(f"\n  UNEXPECTED ERROR in {section.__name__}: "
                  f"{type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
            if REC.cur is not None:
                REC.end("FAIL", f"the section crashed: {type(exc).__name__}: {exc}")
    if REC.cur is not None:  # a section that forgot to close
        REC.end("FAIL", "the section did not finish")
    code = REC.table()
    if allow_stale_cloud and STATE.get("stale_override"):
        print("\n  RESULT OVERRIDE: STALE BUILD (override) was used - the cloud and")
        print("  feature rows ran against a build that is not main. This is NOT a")
        print("  clean post-deploy pass; the exit code is 2 so a script cannot")
        print("  mistake it for one.")
        return 2
    return code


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--self-test" in argv:
        sys.exit(self_test_github())
    only = None
    if "--allow-stale-cloud" in argv:
        ALLOW_STALE_CLOUD["on"] = True
    if "--section" in argv:
        at = argv.index("--section")
        only = argv[at + 1] if at + 1 < len(argv) else ""
        if not only:
            print("--section needs a section name")
            sys.exit(2)
    sys.exit(main(only, allow_stale_cloud=ALLOW_STALE_CLOUD["on"]))

