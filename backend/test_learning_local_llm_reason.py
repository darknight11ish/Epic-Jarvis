"""test_learning_local_llm_reason.py - a failed local-model call must say WHY.

    python3 backend/test_learning_local_llm_reason.py

THE LIVE SYMPTOM THIS PINS. On 2026-10-28 the HUD's learning lane printed this,
22 times over two weeks:

    ! learning pass reached no model at http://127.0.0.1:11436 (asked for
      'qwen3.5:9b') - nothing was learned. Is it pulled?

while Ollama listed `qwen3.5:9b`, had it loaded (9.86 GB VRAM), and answered a
one-token `POST /api/generate` in 1.969 s. "Is it pulled?" was measurably the
wrong question: `jarvis_extract._local_llm()`'s `except Exception: return None`
threw away the exception class, the HTTP status and the body - the only three
things that could say what happened.

WHAT IS PROVED HERE, with the HTTP opener monkeypatched (no network, no model,
no owner file):

  * a timeout, an HTTP error, an `{"error": ...}` body and a 200 with an empty
    `response` each record a CLOSED-WORLD reason: the class name (or the kind
    of empty answer), the HTTP status, the wall duration and Ollama's own
    `done_reason` - and `_local_llm` still returns None exactly as before;
  * the reason reaches the learner's counters through
    `jarvis_auto_learn.note_model_failure`, which /api/memory/learning already
    reads back - `model_failures` moves and `last_model_error` says what
    happened, so the HUD can stop at "reached no model" and start saying why;
  * NOT ONE PROMPT WORD AND NOT ONE ANSWER WORD reaches the reason, the stats
    file, the audit line or the human sentence. Two sentinels are put in the
    prompt and in the model's own error text, and are then searched for in
    everything this code writes;
  * a call that WORKS clears the previous reason instead of leaving a stale
    one behind;
  * THE BITE PROOF, on this repository's own text: with this PR's patch
    (backend/learning-extract-reason.patch) taken back off
    `jarvis-backend/jarvis_extract.py`, the old `_local_llm` has no way to say
    why at all and records nothing - so the checks above fail on the code being
    replaced, not merely pass on the new code.

WHERE THE CODE UNDER TEST COMES FROM. `jarvis-backend/jarvis_extract.py` is
the published base - the owner's file with the whole patch stack applied - so
the suite execs THAT whole file, and proves three things about where it comes
from before it trusts a single check:

  * `backend/learning-extract-reason.patch` is in `apply-patches.ps1`'s own
    list (`_stack.order()`), immediately before `plugin-loader.patch`;
  * `backend/_stack.py`'s walk over that list - the rehearsal every suite
    uses - carries this patch's lines, so the stack really produces them;
  * taking the patch back off the published base gives the old file, and
    applying it forward again reproduces the base byte for byte. That is what
    makes the base the patch's own output rather than a file that happens to
    sit beside it.

No network: the opener is a fake, and the module's own `OLLAMA` is a loopback
address, so a check that forgot the fake still could not reach anything.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_auto_learn.py")

_TMP = Path(tempfile.gettempdir()) / f"jarvis-llm-reason-{uuid.uuid4().hex[:8]}"
# NOT tempfile.mkdtemp(): it creates the folder mode 0o700, and on the owner's
# Windows machine `os.mkdir(d, 0o700)` produces a folder this process is then
# denied (`tools/build_patch_history.py` records the same trap). `os.makedirs`
# inherits ordinary permissions, so the folder is writable here.
_TMP.mkdir(parents=True, exist_ok=True)
_CFG = _TMP / "config"
_CFG.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_CFG)

#: Every audit line the code writes, captured instead of logged to a real log.
AUDIT = []


def _audit(event, detail=None):
    AUDIT.append((str(event), detail))


fw = sys.modules.get("jarvis_framework")
if fw is None:
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = str(_CFG)
    fw.LOG_DIR = str(_TMP)
    fw.load_framework = lambda: {}
    fw.audit_log = _audit
    fw.action_tier = lambda action: "ask"
    sys.modules["jarvis_framework"] = fw

try:
    import jarvis_memory as M  # noqa: F401  (jarvis_extract imports it)
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M  # noqa: F401
import _gitapply  # noqa: E402
import _stack  # noqa: E402
import jarvis_auto_learn as A  # noqa: E402

PASSED, FAILED = [], []
PATCH_NAME = "learning-extract-reason.patch"
PROMPT_SENTINEL = "PROMPT-SENTINEL-9f3a-do-not-record"
ANSWER_SENTINEL = "ANSWER-SENTINEL-7c1d-do-not-record"
LOOPBACK = "http://127.0.0.1:11436"

#: The patch file this branch adds, and the markers the checks look for.
PATCH_NAME = "learning-extract-reason.patch"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ------------------------------------------------------------ a fake opener --

class _Resp:
    """The little of `http.client.HTTPResponse` that `_local_llm` reads."""

    def __init__(self, status, body):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_returning(status, body):
    def _open(req, timeout=None):
        return _Resp(status, body)
    return _open


def opener_raising(exc):
    def _open(req, timeout=None):
        raise exc
    return _open


class patched_opener:
    """Monkeypatch `urllib.request.urlopen` for exactly one call."""

    def __init__(self, fn):
        self.fn = fn
        self.real = None

    def __enter__(self):
        self.real = urllib.request.urlopen
        urllib.request.urlopen = self.fn
        return self

    def __exit__(self, *exc):
        urllib.request.urlopen = self.real
        return False


# ------------------------------------------------------------- the modules ---

def _writable_mkdtemp(*args, **kwargs):
    """`tempfile.mkdtemp`, but a folder this process can actually write into.

    `mkdtemp` creates its folder mode 0o700, and in a confined session that
    folder is then denied to the same process. The repository ships
    `sitecustomize.py` at its root for exactly this, and that is what CI and a
    normal shell get; this local copy leaves the suite runnable when the shim
    is not on PYTHONPATH.
    """
    base = Path(tempfile.gettempdir()) / f"jarvis-llm-reason-{uuid.uuid4().hex[:10]}"
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


_STACK_TEXT = None


def stack_text():
    """The whole walk's jarvis_extract.py, built ONCE for the whole suite.

    Only used to prove the stack CARRIES this patch's lines. The module this
    suite drives is built from the complete published base instead, because the
    walk holds the patched regions and not the owner's whole file.
    """
    global _STACK_TEXT
    if _STACK_TEXT is not None:
        return _STACK_TEXT
    if PATCH_NAME not in _stack.order():
        raise AssertionError(
            f"{PATCH_NAME} is not in scripts/apply-patches.ps1's $PATCHES - "
            f"nothing in this suite would be testing the fix")
    real = tempfile.mkdtemp
    tempfile.mkdtemp = _writable_mkdtemp
    try:
        text, log = _stack.stand_in("jarvis_extract.py")
    finally:
        tempfile.mkdtemp = real
    if not text or "def _local_llm" not in text:
        raise AssertionError("the patch stack cannot build jarvis_extract.py: "
                             + (log[-1] if log else "no reason given"))
    _STACK_TEXT = text
    return text


def load_file(text, name):
    """Exec one COMPLETE backend file as a module."""
    mod = types.ModuleType(name)
    mod.__file__ = f"<{name}>"
    exec(compile(text, mod.__file__, "exec"), mod.__dict__)
    # Pinned AFTER the exec so a machine with OLLAMA_URL set cannot make this
    # suite point anywhere but loopback. Every call is faked anyway.
    mod.OLLAMA = LOOPBACK
    return mod


def patched_module(name="jarvis_extract_under_test"):
    return load_file(published_base_text(), name)


def _scratch_with_base():
    scratch = _TMP / "patch"
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "jarvis_extract.py").write_text(published_base_text(),
                                               encoding="utf-8", newline="\n")
    return scratch


def _git_apply(args, scratch):
    git = shutil.which("git")
    if not git:
        raise AssertionError("git is not on PATH - the patch proof needs it")
    done = subprocess.run([git, "apply", *args], cwd=str(scratch),
                          capture_output=True, text=True,
                          env=_gitapply.env_for(git, scratch))
    return done, git


def published_base_text():
    """The published base: the owner's jarvis_extract.py with the stack applied."""
    return (REPO / "jarvis-backend" / "jarvis_extract.py").read_text(encoding="utf-8")


def old_module(name="jarvis_extract_before_the_fix"):
    """The SAME file with this PR's patch taken back off: the old swallow."""
    patch = HERE / PATCH_NAME
    if not patch.is_file():
        raise AssertionError(f"{patch} is missing - the bite proof has no material")
    scratch = _scratch_with_base()
    done, _git = _git_apply(["--reverse", "-p1", str(patch)], scratch)
    if done.returncode != 0:
        raise AssertionError("the reverse of the patch failed: "
                             + (done.stdout or "") + (done.stderr or ""))
    old = (scratch / "jarvis_extract.py").read_text(encoding="utf-8")
    return load_file(old, name)


def stats_file():
    return Path(A.stats_path())


def stats_text():
    try:
        return stats_file().read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------- the checks --

def t_the_patch_is_the_one_in_the_stack():
    order = _stack.order()
    check(f"{PATCH_NAME} is in apply-patches.ps1's order",
          PATCH_NAME in order, order[-3:])
    check("... immediately before plugin-loader.patch, which must stay last",
          len(order) > 1 and order[-1] == "plugin-loader.patch"
          and order[-2] == PATCH_NAME, order[-3:])
    base = published_base_text()
    check("the published base carries the closed-world record",
          "def local_llm_failure" in base and "note_model_failure" in base
          and "LAST_LLM_FAILURE" in base)
    walk = stack_text()
    check("the stack's own walk carries the patch's lines too",
          "def local_llm_failure" in walk and "note_model_failure" in walk)
    # THE ROUND TRIP: reverse the patch out of the base, then put it back. If
    # both work and the text is the base again, the patch IS the difference
    # this suite is testing - not a file that happens to sit beside it.
    scratch = _scratch_with_base()
    patch = HERE / PATCH_NAME
    done, _git = _git_apply(["--reverse", "-p1", str(patch)], scratch)
    check("this PR's patch reverses out of the published base",
          done.returncode == 0, (done.stdout or "") + (done.stderr or ""))
    if done.returncode == 0:
        back, _git = _git_apply(["-p1", str(patch)], scratch)
        check("... and applying it forward again reproduces the base exactly",
              back.returncode == 0
              and (scratch / "jarvis_extract.py").read_text(encoding="utf-8") == base,
              (back.stdout or "") + (back.stderr or ""))


def t_a_failed_call_records_a_reason_and_still_returns_none():
    X = patched_module()
    check("the code under test asks a LOOPBACK address (nothing here can go out)",
          str(X.OLLAMA).startswith("http://127.0.0.1:"), repr(X.OLLAMA))
    with patched_opener(opener_raising(TimeoutError("timed out"))):
        out = X._local_llm("hello", model="qwen3.5:9b")
    reason = X.local_llm_failure()
    check("a timeout still returns None", out is None, repr(out))
    check("... and a reason is recorded", isinstance(reason, dict), repr(reason))
    if not isinstance(reason, dict):
        return
    check("the reason names the exception class",
          reason.get("kind") == "TimeoutError", repr(reason))
    check("... carries a wall duration in seconds",
          isinstance(reason.get("seconds"), (int, float)) and reason["seconds"] >= 0,
          repr(reason))
    check("... and says plainly that there was no HTTP status",
          reason.get("status") is None, repr(reason))

    with patched_opener(opener_raising(urllib.error.HTTPError(
            LOOPBACK, 500, "server error", {}, b"nope"))):
        out = X._local_llm("hello", model="qwen3.5:9b")
    reason = X.local_llm_failure() or {}
    check("an HTTP error still returns None", out is None, repr(out))
    check("... and the status is recorded, not thrown away",
          reason.get("kind") == "HTTPError" and reason.get("status") == 500,
          repr(reason))


def t_an_empty_or_error_body_is_a_reason_too():
    X = patched_module()
    with patched_opener(opener_returning(200, {"error": "runner exploded"})):
        out = X._local_llm("hello")
    reason = X.local_llm_failure() or {}
    check("a 200 with an error body returns None", out is None, repr(out))
    check("... and is recorded as an error body, with its 200",
          reason.get("kind") == "error_body" and reason.get("status") == 200,
          repr(reason))

    with patched_opener(opener_returning(
            200, {"response": "", "thinking": "Okay", "done_reason": "length"})):
        out = X._local_llm("hello")
    reason = X.local_llm_failure() or {}
    check("a 200 with an EMPTY answer returns None", out is None, repr(out))
    check("... and records Ollama's own done_reason",
          reason.get("kind") == "empty_response"
          and reason.get("done_reason") == "length", repr(reason))


def t_the_learner_counters_carry_the_reason():
    before = int(A.stats().get("model_failures") or 0)
    X = patched_module()
    with patched_opener(opener_raising(urllib.error.HTTPError(
            LOOPBACK, 503, "unavailable", {}, b""))):
        X._local_llm("hello")
    after = A.stats()
    check("the learner's counter moved (a model that never answers is not silence)",
          int(after.get("model_failures") or 0) == before + 1, repr(after))
    words = str(after.get("last_model_error") or "")
    check("the recorded sentence names the class and the status",
          "HTTPError" in words and "503" in words, words)
    note = str(after.get("note") or "")
    check("... and the human sentence /api/memory/learning shows says so too",
          "did not answer" in note and "HTTPError" in note, note)
    check("... and one audit line was written, closed-world",
          any(e == "learning.model_unreachable" for e, _ in AUDIT),
          [e for e, _ in AUDIT][-4:])


def t_no_prompt_word_and_no_answer_word_reaches_anything():
    """The privacy check: two sentinels go in and must not come out anywhere."""
    X = patched_module()
    prompt = f"{PROMPT_SENTINEL}: please remember my private words"
    body = {"error": f"the runner quoted the request back: {ANSWER_SENTINEL}"}
    with patched_opener(opener_returning(200, body)):
        X._local_llm(prompt)
    recorded = json.dumps(X.local_llm_failure(), sort_keys=True)
    written = stats_text()
    audited = json.dumps(AUDIT[-3:], default=str)
    counters = A.stats()
    sentence = str(counters.get("note") or "") + str(counters.get("last_model_error") or "")
    for where, blob in (("the recorded reason", recorded),
                        ("learning-stats.json", written),
                        ("the audit line", audited),
                        ("the human sentence", sentence)):
        check(f"neither sentinel reaches {where}",
              PROMPT_SENTINEL not in blob and ANSWER_SENTINEL not in blob,
              blob[:400])
    check("the sentinels really were in play (a control, so the checks above "
          "cannot pass over nothing)",
          PROMPT_SENTINEL in prompt and ANSWER_SENTINEL in json.dumps(body))


def t_a_working_call_clears_the_last_reason():
    X = patched_module()
    with patched_opener(opener_raising(TimeoutError("timed out"))):
        X._local_llm("hello")
    check("a failure leaves a reason behind", X.local_llm_failure() is not None)
    with patched_opener(opener_returning(200, {"response": '{"facts": []}'})):
        out = X._local_llm("hello")
    check("a working call returns the model's answer unchanged",
          out == '{"facts": []}', repr(out))
    check("... and clears the previous reason instead of leaving a stale one",
          X.local_llm_failure() is None, repr(X.local_llm_failure()))


def t_the_old_text_cannot_say_why():
    """THE BITE PROOF. Without this, the checks above only prove the new code
    works; they do not prove they would have caught the old swallow."""
    old = old_module()
    check("the pre-patch text has no local_llm_failure at all",
          not hasattr(old, "local_llm_failure"))
    # A fresh folder, so "recorded nothing" cannot be hidden by the checks above.
    fresh = _TMP / "config-bite"
    fresh.mkdir(parents=True, exist_ok=True)
    saved = sys.modules["jarvis_framework"].CONFIG_DIR
    sys.modules["jarvis_framework"].CONFIG_DIR = str(fresh)
    try:
        with patched_opener(opener_raising(urllib.error.HTTPError(
                LOOPBACK, 500, "server error", {}, b""))):
            out = old._local_llm("hello")
        check("the old code still returns None for an HTTP error", out is None, repr(out))
        check("... and records NOTHING: the reason is lost, which is the defect",
              not (fresh / "learning-stats.json").exists(),
              str(fresh / "learning-stats.json"))
        check("... so the model_failures counter is still zero on the old text",
              int(A.stats().get("model_failures") or 0) == 0, repr(A.stats()))
    finally:
        sys.modules["jarvis_framework"].CONFIG_DIR = saved


if __name__ == "__main__":
    for fn in (t_the_patch_is_the_one_in_the_stack,
               t_a_failed_call_records_a_reason_and_still_returns_none,
               t_an_empty_or_error_body_is_a_reason_too,
               t_the_learner_counters_carry_the_reason,
               t_no_prompt_word_and_no_answer_word_reaches_anything,
               t_a_working_call_clears_the_last_reason,
               t_the_old_text_cannot_say_why):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
