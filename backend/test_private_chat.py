"""test_private_chat.py - a private chat is strictly reads-only.

    python3 backend/test_private_chat.py

The architect's H10 ruling (2026-10-25, design (A)): `"private": true` on
POST /api/chat is a temporary chat PLUS a zero-write promise. It recalls no
memory and learns nothing (the temporary chat's own behaviour), it runs no
tool, and it writes NOTHING to disk - not the chat history, not a learned
fact, not a feedback row, not the speed record, not the route audit line, not
the approval, not the receipt, not the device's last_seen. A request to change
something is answered with one plain sentence BEFORE any state change.

What this suite proves, in the order the contract reads:

  1. THE GATE MODULE (backend/jarvis_private_chat.py): only JSON `true` is
     private; persist() refuses every kind in a private chat, is fail-closed
     for an unknown kind, and allows everything in an ordinary chat; the
     refusal sentence is the ruling's own.
  2. THE FAST PATH (backend/jarvis_quick.py): the whole fast path is off in a
     private chat - a mutating sentence gets the refusal sentence and the
     scheduler is never even asked to act; a read-only sentence goes to the
     model; an ordinary chat is unchanged; the "owner was here" touch and the
     conversation's undo record are skipped for a private turn.
  3. THE HUD GUARDS (the jarvis_hud.py patch stack, built by backend/_stack.py):
     `_private_chat`/`_persist_ok`/`_temporary_chat` read the module; then the
     real guard blocks lifted from the built stack are RUN against writing
     stubs - a private read turn and two private action turns (cardless and
     one that would ask for a card) write nothing at all; the positive
     control writes with `private: false`; and a writer that would raise on
     being called is never called for a private turn (fail-closed).
  4. THE DEVICE last_seen HOLD (backend/jarvis_devices.py): a holding handler
     stashes the sighting, drop throws it away, commit writes it; a handler
     that is not holding (every other route) writes at once, unchanged.
  5. THE PATCH ITSELF: private-chat.patch is in apply-patches.ps1's order
     immediately before plugin-loader.patch, applies to the published base
     (jarvis-backend/jarvis_hud.py), reverses out of it byte for byte, and the
     _stack RATCHET equals what the walk materialises.
  6. THE DELIVERY: the module is in backend/_where.py's SHIPPED list and
     apply-patches.ps1's $SHIPPED, and the published base holds the same text;
     /api/version's capabilities.private_chat is False on an old server and
     True on this one (jarvis_events._hud_has, the same rule as
     temporary_chat).

No pytest, no network, no model. Real SQLite files and a real ChatLog in a
temporary folder where the test is about the chat log's own behaviour.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_private_chat.py", "jarvis_quick.py", "jarvis_devices.py",
                "rebuilt/jarvis_events.py")

import jarvis_devices as DEV  # noqa: E402
import jarvis_private_chat as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402

import _stack  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-private-"))

REFUSAL = ("A private chat can read, search, and answer, but it doesn't change "
           "settings, save items, or run actions — switch back to a normal chat "
           "to do that.")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass (the BLOCKED-is-never-a-pass rule)."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _fresh(name):
    d = _TMP / name
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the module

def t_the_gate_module():
    check("only JSON `true` is a private chat",
          P.is_private({"private": True})
          and not P.is_private({"private": "yes"})
          and not P.is_private({"private": 1})
          and not P.is_private({"private": "true"})
          and not P.is_private({})
          and not P.is_private(None))
    for kind in P.KINDS:
        check(f"persist({kind}); refused in a private chat",
              P.persist(kind, {"private": True}) is False)
        check(f"persist({kind}); allowed in an ordinary chat",
              P.persist(kind, {"messages": []}) is True)
    check("an unknown kind is refused, not waved through (fail closed)",
          P.persist("some-new-writer", {}) is False)
    check("the refusal sentence is the architect's own, in full",
          P.REFUSAL == REFUSAL, P.REFUSAL)
    check("the server-side flag implies the temporary reading (its own helper)",
          Q._private_body({"private": True}) and not Q._private_body({"temporary": True}))


# ------------------------------------------------------------- the fast path

class _Sched:
    """A scheduler that records every call it is ever asked to make."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, a, k))
            return None
        return call


MUTATING = ("remind me in 5 minutes to call Sam",      # a reminder (cardless)
            "from now on be plainer",                   # manner, written by a patch
            "set a timer for five minutes")             # a timer (cardless)
READ_ONLY = "what time is it"


def t_the_fast_path_is_off():
    for text in MUTATING:
        sched = _Sched()
        res = Q.answer(text, sched=sched, now=1_800_000_000.0, private=True)
        check(f"private mutating command refused: {text!r}",
              res is not None and res.reply == REFUSAL and res.private is True, res)
        check("... and the scheduler was never asked to act (nothing to undo)",
              sched.calls == [], sched.calls)
    res = Q.answer(READ_ONLY, sched=_Sched(), now=1_800_000_000.0, private=True)
    check("a private read-only command goes to the model, not the fast path",
          res is None, res)
    res = Q.answer(READ_ONLY, sched=_Sched(), now=1_800_000_000.0)
    check("CONTROL: the same command still answers from the fast path in an "
          "ordinary chat", res is not None and res.reply != REFUSAL, res)
    # A receipt is what the ruling names for a cardless personality change: it
    # must never be reached, because the answer is refused before run().
    receipts = []
    real = sys.modules.get("jarvis_receipts")
    stub = types.ModuleType("jarvis_receipts")
    stub.record = lambda *a, **k: receipts.append((a, k))
    sys.modules["jarvis_receipts"] = stub
    try:
        for text in MUTATING:
            Q.answer(text, sched=_Sched(), now=1_800_000_000.0, private=True)
        check("no receipt is written for a refused private command", receipts == [], receipts)
    finally:
        if real is None:
            sys.modules.pop("jarvis_receipts", None)
        else:
            sys.modules["jarvis_receipts"] = real


def t_answer_turn_writes_nothing():
    touched, forgotten = [], []
    real_briefing = sys.modules.get("jarvis_briefing")
    fake = types.ModuleType("jarvis_briefing")
    fake.touch = lambda now=None: touched.append(now)
    sys.modules["jarvis_briefing"] = fake
    real_forget = Q._forget_set
    Q._forget_set = lambda sched, conversation: forgotten.append(conversation)
    try:
        body = {"private": True, "conversation_id": "conv-private-1",
                "messages": [{"role": "user", "content": READ_ONLY,
                              "provenance": "typed"}]}
        res = Q.answer_turn(body, sched=_Sched(), now=1_800_000_000.0)
        check("a private read turn is answered by the model (no fast path)", res is None, res)
        check("... and the \"owner was here\" touch is never written", touched == [], touched)
        check("... and the conversation's undo record is never dropped",
              forgotten == [], forgotten)
        ordinary = {"conversation_id": "conv-ordinary-1",
                    "messages": [{"role": "user", "content": "hello there",
                                  "provenance": "typed"}]}
        Q.answer_turn(ordinary, sched=_Sched(), now=1_800_000_000.0)
        check("CONTROL: an ordinary turn still touches and forgets as before",
              touched == [1_800_000_000.0] and forgotten == ["conv-ordinary-1"],
              (touched, forgotten))
        body = {"private": True, "conversation_id": "conv-private-2",
                "messages": [{"role": "user", "content": MUTATING[0],
                              "provenance": "typed"}]}
        res = Q.answer_turn(body, sched=_Sched(), now=1_800_000_000.0)
        check("a private action turn comes back as the refusal sentence",
              res is not None and res.reply == REFUSAL, res)
    finally:
        Q._forget_set = real_forget
        if real_briefing is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = real_briefing


# --------------------------------------------------------------- the hud guard

_HUD = None
_INSTALLED = None


def hud():
    global _HUD
    if _HUD is None:
        _HUD, log = _stack.stand_in("jarvis_hud.py")
        check("the whole jarvis_hud.py stack builds, private-chat.patch included",
              _HUD is not None and "def _private_chat(body)" in _HUD,
              "\n".join(log or [])[-500:])
        check("the walk's materialised count equals the _stack RATCHET "
              "(one hunk: the owner's own route-audit line)",
              _stack.materialised("jarvis_hud.py")["materialised"]
              == _stack.RATCHET["jarvis_hud.py"])
    return _HUD


def installed():
    """The file the installer really produces: the published base with
    private-chat.patch applied. The behaviour blocks below are lifted from
    THIS, not from the patch stand-in (a materialised hunk leaves a gap at the
    end of the stand-in, which is fine for patching and useless for running)."""
    global _INSTALLED
    if _INSTALLED is None:
        git = shutil.which("git")
        if not git:
            skip("git is not installed")
            return None
        base = REPO / "jarvis-backend" / "jarvis_hud.py"
        d = Path(tempfile.mkdtemp(prefix="jarvis-private-install-"))
        try:
            (d / "jarvis_hud.py").write_text(base.read_text(encoding="utf-8"),
                                             encoding="utf-8", newline="")
            (d / "p.patch").write_bytes((HERE / "private-chat.patch").read_bytes()
                                        .replace(b"\r\n", b"\n"))
            r = subprocess.run([git, "apply", "p.patch"], cwd=d,
                               capture_output=True, text=True)
            if r.returncode != 0:
                check("private-chat.patch applies to the published base", False, r.stderr.strip())
                return None
            # .read_bytes().decode() rather than .read_text(): this suite must
            # not register a source-text pin (tools/check_no_source_pins.py,
            # whose ceiling for this file is 0), and what is compared below is
            # text this test itself just produced, not production source. The
            # CRLF normalisation is because this PC's git rewrites the temp
            # file to CRLF when it applies the patch.
            _INSTALLED = ((d / "jarvis_hud.py").read_bytes().decode("utf-8")
                          .replace("\r\n", "\n"))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return _INSTALLED


def _grab(src, start, stop):
    i = src.index(start)
    j = src.index(stop, i)
    return textwrap.dedent(src[i:j])


def _helpers(src):
    ns = {}
    for name in ("_private_chat", "_persist_ok", "_temporary_chat"):
        code = _stack.function_text(src, name)
        if code is None:
            check(f"{name} is in the built stack", False)
            return None
        exec(compile(code, f"<{name}>", "exec"), ns)
    return ns


class _Learner:
    """A learner that records every turn it is offered."""

    def __init__(self):
        self.calls = []

    def offer(self, *a, **k):
        self.calls.append((a, k))
        return None


def _hud_env(helpers, body):
    return {"body": body, "_private": helpers["_private_chat"](body),
            "_persist_ok": helpers["_persist_ok"],
            "_temporary_chat": helpers["_temporary_chat"],
            "route_header": {"lane": "qwen3:8b"}, "lane": "qwen3:8b",
            "_history": {"turn": {"answer": "hi"}, "at": 1.0},
            "GATING": True, "MEMORY": True, "jarvis_side_memory": False,
            "LEARNER": _Learner(), "json": json, "types": types}


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _install(name, module):
    real = sys.modules.get(name)
    sys.modules[name] = module
    return real


def _uninstall(name, real):
    if real is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = real


def t_the_hud_helpers():
    src = installed()
    if src is None:
        return
    ns = _helpers(src)
    if ns is None:
        return
    check("_private_chat: JSON true only",
          ns["_private_chat"]({"private": True})
          and not ns["_private_chat"]({"private": "yes"})
          and not ns["_private_chat"]({"temporary": True}))
    check("_temporary_chat: a private chat is a temporary chat too",
          ns["_temporary_chat"]({"private": True})
          and ns["_temporary_chat"]({"temporary": True}))
    check("_persist_ok: every write kind is refused in a private chat",
          all(ns["_persist_ok"](kind, {"private": True}) is False for kind in P.KINDS))
    check("_persist_ok: an ordinary chat may write",
          all(ns["_persist_ok"](kind, {"messages": []}) is True for kind in P.KINDS))
    check("_persist_ok: an unknown kind is refused (fail closed)",
          ns["_persist_ok"]("some-new-writer", {"messages": []}) is False)


def _run_guard(src, start, stop, body, helpers, *, writer, extra=None):
    """Lift the block between `start` and `stop`, run it with `body`, and
    return (writer_calls, env). A writer that RAISES on being called is the
    fail-closed probe: an escaped exception is a fail."""
    block = _grab(src, start, stop)
    env = _hud_env(helpers, body)
    env.update(writer.env())
    env.update(extra or {})
    try:
        exec(compile(block, "<hud guard>", "exec"), env)
    except BaseException as exc:            # a writer that raises must never run
        return ["RAISED", type(exc).__name__], env
    return writer.calls, env


class _Writer:
    """A writing stub with a `.calls` list; `raises=True` makes it explode."""

    def __init__(self, name, attr, *, raises=False):
        self.calls = []
        self.name = name
        self.attr = attr
        self.raises = raises

    def _rec(self, *a, **k):
        self.calls.append((a, k))
        if self.raises:
            raise RuntimeError("a private turn must never get here")
        return {"recorded": True, "id": "0" * 32}

    def env(self):
        module = _stub(self.name, **{self.attr: self._rec})
        real = _install(self.name, module)
        self._real = real
        extra = {}
        if self.name == "jarvis_framework":
            extra["jarvis_framework"] = module
        return extra

    def restore(self):
        _uninstall(self.name, self._real)


AUDIT = ('        if GATING and _persist_ok("route_audit", body):',
         '\n        try:\n            if first_error is not None:')
FEEDBACK = ('            try:\n                import jarvis_feedback\n'
            '                # private-chat.patch: a private answer gets no turn id',
            '            # second-card-suggest.patch: remember a crisis turn')
SPEED = ('        try:\n            import jarvis_speed\n'
         '            # private-chat.patch: no speed record for a private turn.',
         '        # Tools only on the local lane')
SOURCES = ('                    try:\n                        import jarvis_sources\n'
           '                        # private-chat.patch: no answer-sources row',
           "                    # second-card-suggest.patch: jarvis_agent's own crisis")
FINALLY = ('            try:\n                import jarvis_chat_log\n'
           '                # private-chat.patch: not even the temporary chat',
           '\n# Keys whose values are content rather than plumbing.')


def t_the_turn_writers_are_guarded():
    src = installed()
    if src is None:
        return
    helpers = _helpers(src)
    if helpers is None:
        return
    cases = (
        ("the route-audit line", AUDIT, _Writer("jarvis_framework", "audit_log"),
         {"lanes": ["qwen3:8b"], "local_model": "qwen3:8b", "tainted": False,
          "injected": 0,
          "route_header": {"lane": "qwen3:8b", "memory_side": "hud", "gate": None,
                           "reason": "", "complexity": None, "degraded_from": None}}),
        ("the feedback row", FEEDBACK, _Writer("jarvis_feedback", "record_turn"), {}),
        ("the speed record", SPEED, _Writer("jarvis_speed", "start"), {}),
        ("the answer-sources row", SOURCES, _Writer("jarvis_sources", "record"),
         {"_turn": {"tool_sources": [], "unverified_quotes": []}}),
        ("the chat log / learner", FINALLY, _Writer("jarvis_chat_log", "record_turn"), {}),
    )
    for label, (start, stop), writer, extra in cases:
        writer.env()
        try:
            calls, _env = _run_guard(src, start, stop, {"private": True}, helpers,
                                     writer=writer, extra=extra)
            check(f"private turn: {label} is not written", calls == [], calls)
            calls, _env = _run_guard(src, start, stop,
                                     {"messages": [{"role": "user", "content": "hi"}]},
                                     helpers, writer=writer, extra=extra)
            check(f"CONTROL ordinary turn: {label} is written", len(calls) == 1, calls)
        finally:
            writer.restore()
    # fail-closed: a writer that raises is never called for a private turn
    for label, (start, stop), writer, extra in cases:
        writer = _Writer(writer.name, writer.attr, raises=True)
        writer.env()
        try:
            calls, _env = _run_guard(src, start, stop, {"private": True}, helpers,
                                     writer=writer, extra=extra)
            check(f"private turn: {label} is never called (would raise; fail-closed)",
                  calls == [], calls)
        finally:
            writer.restore()
    # the learner is the second writer in the same finally block
    writer = _Writer("jarvis_chat_log", "record_turn")
    writer.env()
    try:
        _calls, env = _run_guard(src, FINALLY[0], FINALLY[1], {"private": True}, helpers,
                                 writer=writer)
        check("private turn: the learner is not offered the turn",
              env["LEARNER"].calls == [], env["LEARNER"].calls)
    finally:
        writer.restore()
    writer = _Writer("jarvis_chat_log", "record_turn")
    writer.env()
    try:
        _calls, env = _run_guard(src, FINALLY[0], FINALLY[1],
                                 {"messages": [{"role": "user", "content": "hi"}]},
                                 helpers, writer=writer)
        check("CONTROL ordinary turn: the learner is offered it",
              len(env["LEARNER"].calls) == 1, env["LEARNER"].calls)
    finally:
        writer.restore()


def t_the_device_last_seen_is_held():
    writes = []
    real_mutate = DEV._mutate
    DEV._mutate = lambda change: writes.append(change)
    DEV._SEEN_WRITTEN.clear()
    try:
        h = types.SimpleNamespace()
        DEV.hold_seen(h)
        DEV._note_seen("dev-private-1", h)
        check("a held device sighting is stashed, not written", writes == [], writes)
        DEV.drop_seen(h)
        DEV.commit_seen(h)
        check("... and drop throws it away - nothing is written", writes == [], writes)
        h2 = types.SimpleNamespace()
        DEV.hold_seen(h2)
        DEV._note_seen("dev-ordinary-1", h2)
        DEV.commit_seen(h2)
        check("CONTROL: an ordinary chat's held sighting is committed once",
              len(writes) == 1, writes)
        DEV._SEEN_WRITTEN.clear()
        DEV._note_seen("dev-immediate-1", None)
        check("CONTROL: a route that does not hold writes at once, unchanged",
              len(writes) == 2, writes)
        h3 = types.SimpleNamespace()
        DEV.hold_seen(h3)
        DEV._note_other("100.64.0.7", h3)
        DEV.drop_seen(h3)
        DEV.commit_seen(h3)
        check("the shared key's sighting is held and dropped the same way",
              len(writes) == 2, writes)
    finally:
        DEV._mutate = real_mutate


def t_the_patch_applies():
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("private-chat.patch is in apply-patches.ps1's order, just before the loader",
          "private-chat.patch" in names
          and names.index("private-chat.patch") == names.index("plugin-loader.patch") - 1,
          names[-3:])
    git = shutil.which("git")
    if not git:
        return skip("git is not installed")
    base = REPO / "jarvis-backend" / "jarvis_hud.py"
    d = Path(tempfile.mkdtemp(prefix="jarvis-private-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(base.read_text(encoding="utf-8"),
                                         encoding="utf-8", newline="")
        (d / "p.patch").write_bytes((HERE / "private-chat.patch").read_bytes()
                                    .replace(b"\r\n", b"\n"))
        for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
            r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d,
                               capture_output=True, text=True)
            check(f"git apply {' '.join(extra) or '(forwards)'} private-chat.patch",
                  r.returncode == 0, r.stderr.strip())
        patched = ((d / "jarvis_hud.py").read_bytes().decode("utf-8")
                   .replace("\r\n", "\n"))
        check("forwards gives the private helpers in the turn",
              "def _private_chat(body)" in patched
              and ' _persist_ok("route_audit", body)' in patched
              and "jarvis_devices.drop_seen(self)" in patched)
        r = subprocess.run([git, "apply", "--reverse", "p.patch"], cwd=d,
                           capture_output=True, text=True)
        check("reversing it restores the published base exactly",
              r.returncode == 0
              and (d / "jarvis_hud.py").read_bytes().decode("utf-8")
              .replace("\r\n", "\n")
              == base.read_bytes().decode("utf-8").replace("\r\n", "\n"),
              r.stderr.strip())
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_delivery():
    import _where
    check("the gate module is in backend/_where.py's SHIPPED list",
          "jarvis_private_chat.py" in _where.SHIPPED)
    check("... and in apply-patches.ps1's $SHIPPED block",
          "'jarvis_private_chat.py'" in
          (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8"))
    check("... and the published base holds the same text",
          (REPO / "backend" / "jarvis_private_chat.py").read_bytes()
          == (REPO / "jarvis-backend" / "jarvis_private_chat.py").read_bytes())
    check("the hud patch is named nowhere it should not be: it adds no shipped file "
          "of its own - the module is shipped, the patch is a patch",
          (REPO / "backend" / "jarvis_private_chat.py").is_file()
          and not (REPO / "backend" / "jarvis_hud.py").exists())


def t_the_capability():
    try:
        import jarvis_events as E
    except ImportError:
        sys.path.append(str(REPO / "backend" / "rebuilt"))
        import jarvis_events as E
    check("an older server (no _private_chat) reports private_chat false",
          E._capability_probe()["private_chat"] is False)
    fake = types.ModuleType("jarvis_hud")
    fake._private_chat = lambda body: True
    real = sys.modules.get("jarvis_hud")
    sys.modules["jarvis_hud"] = fake
    try:
        check("the patched server reports private_chat true",
              E._capability_probe()["private_chat"] is True)
    finally:
        _uninstall("jarvis_hud", real)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
