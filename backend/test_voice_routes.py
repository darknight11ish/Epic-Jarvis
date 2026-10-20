"""The voice routes' CONTRACTS, executed - so a GitHub runner really runs them.

WHY THIS FILE EXISTS. The routes that guard the owner's voice had no passing
coverage anywhere: the only file that ever exercised them is
`.dshwork/backend-live/test_voice_http.py`, which is gitignored (not in this
repository) and cannot even import against the current code (`jarvis_speech`
has no `Transcriber`). So the one control that decides whose voice may command
the assistant rested on a single manual live test.

WHAT IT CAN AND CANNOT DO. `jarvis_hud.py` is the owner's file: this repository
holds it only as PATCHES. `backend/_stack.py` rebuilds, from those patches, the
exact text they write - and three of these routes are written ENTIRELY by a
patch, `if route == ...:` line included, so their real code can be compiled and
executed here with a fake handler. That is what this suite does, and it is why
it FAILS rather than skips on a runner. What needs the owner's PC is said out
loud at the end of a run instead of being skipped quietly:

  * the routes' ORIGINAL lines (their dispatch, the `return self._send(200,
    heard)` that hands the gate's verdict to the client) are not in any patch,
    so the whole-file cross-checks stay in `test_voice_503.py` and need
    `$JARVIS_BACKEND`;
  * a real clip through a real voice print - the accept half - needs his
    microphone and his models.

WHAT "REFUSAL" MEANS HERE, and why the shape matters as much as the code: the
phone tells "that didn't sound like you" from "that was too short" by
`threshold > 0` (`jarvis-client/.../net/VoiceModels.kt:606-613`), because a clip
refused BEFORE the voice check comes back with score and threshold at zero. A
too-short refusal that carried a threshold would be shown to the owner as a
stranger's voice; a real refusal that carried none would be shown as a cough.
`t_the_shape_the_client_reads` pins that, on the module that builds it
(`jarvis_speech.Heard.as_dict`), which is in this repository.

    python3 test_voice_routes.py          # JARVIS_BACKEND unset: the repository's copy
"""
import json
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in the
# dev container, $JARVIS_BACKEND on a real install. REPO is this repository.
from _where import BACKEND, REPO  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check this machine cannot run: printed, counted on its own, NEVER
    counted as a pass."""
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


# ---------------------------------------------------------------------------
# The patch stack's jarvis_hud.py, and the pieces of it that are routes
# ---------------------------------------------------------------------------

_STAND_IN = None


def stack_text():
    """The whole patch stack's text for jarvis_hud.py ("" when it cannot be
    built - no git, or a hunk that no longer applies)."""
    global _STAND_IN
    if _STAND_IN is None:
        import _stack
        _STAND_IN = _stack.stand_in("jarvis_hud.py")[0] or ""
    return _STAND_IN


#: Which clauses continue a statement - and only for the statement that can own
#: them. An `except` at the same indent as an `if` belongs to some enclosing
#: `try:` that is NOT in the fragment, so keeping it would produce an
#: IndentationError rather than a longer block.
_CONTINUES = (("try:", ("except", "else:", "finally:")),
              ("if ", ("elif ", "else:")),
              ("if(", ("elif ", "else:")),
              ("for ", ("else:",)),
              ("while ", ("else:",)))


def block(source, anchor):
    """The statement starting with `anchor`, and everything indented under it -
    including its own `elif`/`else`/`except` clauses, and nothing else.

    A block that is written entirely as `+` lines by a patch lands in the
    stand-in verbatim - `if route == "/api/voice/turn":` and its whole body -
    so this is the real code, not a copy of it kept here to drift.
    """
    lines = source.splitlines()
    i = next((n for n, l in enumerate(lines) if l.strip().startswith(anchor)), None)
    if i is None:
        return None
    first = lines[i].strip()
    keep = next((k for head, k in _CONTINUES if first.startswith(head)), ())
    indent = len(lines[i]) - len(lines[i].lstrip())
    out = [lines[i]]
    for line in lines[i + 1:]:
        stripped = line.strip()
        here = len(line) - len(line.lstrip())
        if stripped and here <= indent and not stripped.startswith(keep):
            break
        out.append(line)
    return "\n".join(out)


def post_image(patch, needle, *, start="try:"):
    """The patch's own hunk around `needle`, as the file looks AFTER it -
    context and `+` lines, `-` lines dropped - cut from the nearest `start`
    statement above the needle to the shortest prefix that is a complete
    statement.

    Some of what a patch adds is a FRAGMENT of the owner's route: an
    `except ImportError` clause, which cannot even be compiled on its own, and
    which only means anything together with the `try:` it belongs to. The
    post-image carries both, and the shortest compiling prefix is that
    clause - short prefixes are not statements and do not compile.
    """
    lines = (HERE / patch).read_text(encoding="utf-8").split("\n")
    hits = [n for n, l in enumerate(lines) if l.startswith("+") and needle in l]
    if len(hits) != 1:
        return None
    i = hits[0]
    a = i
    while a > 0 and not lines[a].startswith("@@"):
        a -= 1
    b = i
    while b + 1 < len(lines) and not lines[b + 1].startswith("@@"):
        b += 1
    body = [l[1:] for l in lines[a + 1:b + 1] if l[:1] in (" ", "+")]
    here = next(n for n, l in enumerate(body) if needle in l)
    owners = [n for n in range(here + 1) if body[n].strip().startswith(start)]
    if not owners:
        return None
    body = body[owners[-1]:]
    for n in range(1, len(body) + 1):
        try:
            compile("def _route(self, route, path):\n" + "\n".join(body[:n]) + "\n",
                    "<probe>", "exec")
        except SyntaxError:
            continue
        return "\n".join(body[:n])
    return None


def helpers():
    """The stack's real `_no_speech` and `_SAY_FALLBACK`, executed.

    The moment route answers a missing module THROUGH `_no_speech`, so its
    body is only meaningful against the real helper. `test_voice_503.py`
    already holds that helper's own contract; this just uses it."""
    import _stack
    src = stack_text()
    fn = _stack.function_text(src, "_no_speech")
    lines = src.splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith("_SAY_FALLBACK =")]
    if not fn or len(starts) != 1:
        raise AssertionError("the patch stack no longer writes _no_speech/_SAY_FALLBACK")
    out, depth = [], 0
    for line in lines[starts[0]:]:
        out.append(line)
        depth += sum(line.count(c) for c in "([{") - sum(line.count(c) for c in ")]}")
        if depth <= 0:
            break
    ns = {}
    exec(compile("\n".join(out) + "\n", "<_SAY_FALLBACK>", "exec"), ns)
    exec(compile(fn, "<_no_speech>", "exec"), ns)
    return ns


# ---------------------------------------------------------------------------
# A fake handler, and a way to run one route block in it
# ---------------------------------------------------------------------------

class Sent:
    """Stands in for `self` inside a route: `_send` records, and never writes
    anything anywhere."""

    def __init__(self, path="/"):
        self.path = path
        self.calls = []

    def _send(self, code, out, **k):
        self.calls.append((code, out, k))
        return (code, out)

    @property
    def last(self):
        return self.calls[-1] if self.calls else None


def run(block_src, *, route="", path="", origin=True, token=True, body=b"RIFF",
        unreadable=False, modules=None, **locals_):
    """Execute one route block against a fake handler.

    `modules` is patched over `sys.modules` AND bound as a name, so it works
    both for a route that does `import jarvis_speech` itself and for a
    fragment of one that imported it further up. A value of None means "this
    PC has not got that module" (`import x` then raises ImportError), which is
    the state the 503 branches are about.
    `locals_` is what the surrounding route has already bound - `raw`, `src`,
    `voice_mic` - because a fragment is only a fragment.
    """
    ns = dict(helpers())
    ns.update(locals_)
    for name, mod in (modules or {}).items():
        if mod is not None:
            ns[name] = mod
    ns["_origin_ok"] = lambda self: origin
    ns["_token_ok"] = lambda self: token
    if unreadable:
        def _read_body(self):
            raise OSError("the connection went away")
    else:
        _read_body = lambda self: body
    ns["_read_body"] = _read_body
    with mock.patch.dict(sys.modules, modules or {}):
        exec(compile("def _route(self, route, path):\n" + block_src + "\n",
                     "<voice route, from the patch stack>", "exec"), ns)
        sent = Sent(path or "/")
        ns["_route"](sent, route, path)
    return sent


def turns(result=None, raises=None):
    """A stand-in for the `jarvis_turn` module (its functions are module-level,
    so these are too - a class here would bind `raw` to `self`)."""
    t = SimpleNamespace(seen=[])

    def handle(raw):
        t.seen.append(raw)
        if raises is not None:
            raise raises
        return result

    t.handle = handle
    return t


def speech(moment=None, raises=None, takes=()):
    """A stand-in for the `jarvis_speech` module."""
    t = SimpleNamespace(seen=[], TAKES_WAIT="waited_ms" in takes, TAKES_MIC="mic" in takes)

    def hear(raw, **kw):
        t.seen.append(kw)
        return {"is_owner": True}

    def moment_reply():
        if raises is not None:
            raise raises
        return moment

    def barge_in(raw, **kw):
        t.seen.append(kw)
        return {"stop": True}

    t.hear, t.moment_reply, t.barge_in = hear, moment_reply, barge_in
    return t


# ---------------------------------------------------------------------------
# 1. The control: the stack really writes these routes
# ---------------------------------------------------------------------------

_ANCHORS = (
    ("jarvis_hud.py", 'if route == "/api/voice/turn":', "the turn route"),
    ("jarvis_hud.py", 'if route == "/api/voice/enroll":', "the enroll route"),
    ("jarvis_hud.py", 'if path == "/api/voice/moment":', "the moment route"),
)


def t_the_stack_still_writes_these_routes():
    """CONTROL. If a patch stops writing one of these, every check below would
    quietly test nothing - so this fails instead."""
    src = stack_text()
    check("the patch stack's jarvis_hud.py can be built at all", bool(src),
          "backend/_stack.py could not build it (git missing, or a hunk that no "
          "longer applies to its own pre-image)")
    if not src:
        return
    for _patch, anchor, what in _ANCHORS:
        check(f"the stack still writes {what}", block(src, anchor) is not None)
    check("the stack still writes the utterance route's missing-module guard",
          post_image("voice-503.patch", "do NOT recognise this yourself") is not None,
          "voice-503.patch no longer adds that `except ImportError` clause")
    for anchor, what in (('if src == "barge_in":', "the barge-in branch"),
                         ('if getattr(jarvis_speech, "TAKES_WAIT", False):',
                          "the mic/waited_ms plumbing")):
        check(f"the stack still writes {what}", block(src, anchor) is not None)


# ---------------------------------------------------------------------------
# 2. /api/voice/turn
# ---------------------------------------------------------------------------

def t_the_turn_route():
    b = block(stack_text(), 'if route == "/api/voice/turn":')
    if not b:
        return skip("turn route", "the stack no longer writes it")

    h = run(b, route="/api/voice/turn", origin=False, modules={"jarvis_turn": None})
    check("turn: a cross-origin request is 403, refused before anything else",
          h.last and h.last[0] == 403 and h.last[1]["error"] == "cross-origin request refused",
          repr(h.last))

    h = run(b, route="/api/voice/turn", token=False, modules={"jarvis_turn": None})
    check("turn: no token is 401, and the reply names the header",
          h.last and h.last[0] == 401 and "X-Jarvis-Token" in h.last[1]["error"], repr(h.last))

    h = run(b, route="/api/voice/turn", unreadable=True, modules={"jarvis_turn": None})
    check("turn: a body that cannot be read is 400",
          h.last and h.last[0] == 400 and h.last[1]["error"].startswith("could not read the request"),
          repr(h.last))

    h = run(b, route="/api/voice/turn", modules={"jarvis_turn": None})
    check("turn: with no jarvis_turn, 503 and available is explicitly false",
          h.last and h.last[0] == 503 and h.last[1]["available"] is False, repr(h.last))

    M = turns(raises=RuntimeError("the owner's own words are in here"))
    h = run(b, route="/api/voice/turn", body=b"RIFF-tail", modules={"jarvis_turn": M})
    check("turn: a module that raises is 500 carrying the exception NAME only",
          h.last and h.last == (500, {"error": "RuntimeError"}, {}), repr(h.last))
    check("turn: ...and NOT the exception's message (the request is the owner's voice)",
          "owner's own words" not in json.dumps(h.last[1]), repr(h.last[1]))
    check("turn: it was handed the whole body", M.seen == [b"RIFF-tail"], repr(M.seen))

    M = turns(result=(200, {"probability": 0.62}))
    h = run(b, route="/api/voice/turn", modules={"jarvis_turn": M})
    check("turn: a success passes the module's own code and body straight through",
          h.last == (200, {"probability": 0.62}, {}), repr(h.last))


# ---------------------------------------------------------------------------
# 3. /api/voice/enroll - it STAGES and raises a card; it enrols nothing
# ---------------------------------------------------------------------------

def t_the_enroll_route_stages_and_never_enrols():
    b = block(stack_text(), 'if route == "/api/voice/enroll":')
    if not b:
        return skip("enroll route", "the stack no longer writes it")

    h = run(b, route="/api/voice/enroll", origin=False, modules={"jarvis_voice_enroll": None})
    check("enroll: a cross-origin request is 403",
          h.last and h.last[0] == 403 and h.last[1]["error"] == "cross-origin request refused",
          repr(h.last))

    h = run(b, route="/api/voice/enroll", token=False, modules={"jarvis_voice_enroll": None})
    check("enroll: no token is 401",
          h.last and h.last[0] == 401 and "X-Jarvis-Token" in h.last[1]["error"], repr(h.last))

    h = run(b, route="/api/voice/enroll", unreadable=True, modules={"jarvis_voice_enroll": None})
    check("enroll: a body that cannot be read is 400",
          h.last and h.last[0] == 400, repr(h.last))

    h = run(b, route="/api/voice/enroll", modules={"jarvis_voice_enroll": None})
    check("enroll: with no jarvis_voice_enroll, 503 in its own words (not _no_speech's)",
          h.last and h.last[0] == 503 and h.last[1]["available"] is False
          and "voice training is not installed" in h.last[1]["error"], repr(h.last))

    E = SimpleNamespace(calls=[])

    def stage(raw):
        E.calls.append(raw)
        return 202, {"waiting": True, "card": "abc123"}

    E.stage = stage
    h = run(b, route="/api/voice/enroll", body=b'{"clips": ["AAAA"]}',
            modules={"jarvis_voice_enroll": E})
    check("enroll: the clips are handed to stage() and nothing else is called",
          E.calls == [b'{"clips": ["AAAA"]}'], repr(E.calls))
    check("enroll: what comes back is stage()'s own answer - a waiting card, not a done",
          h.last == (202, {"waiting": True, "card": "abc123"}, {}), repr(h.last))

    def bad_stage(raw):
        raise ValueError("clip 3 of 5 was the owner saying his account number")

    h = run(b, route="/api/voice/enroll", modules={"jarvis_voice_enroll": SimpleNamespace(stage=bad_stage)})
    check("enroll: a module that raises is 500 with the NAME only, never the clips",
          h.last and h.last[0] == 500 and h.last[1] == {"error": "ValueError"}, repr(h.last))
    check("enroll: ...and the exception's message is not in the reply",
          "account number" not in json.dumps(h.last[1]), repr(h.last[1]))

    # The clear mode (2026-10-19) travels the SAME route and stage(): no new
    # route, no new patch, and the body is handed over untouched.
    E2 = SimpleNamespace(calls=[])

    def stage_clear(raw):
        E2.calls.append(raw)
        return 202, {"ok": True, "pending": True, "files": 8}

    E2.stage = stage_clear
    h = run(b, route="/api/voice/enroll", body=b'{"mode": "clear"}',
            modules={"jarvis_voice_enroll": E2})
    check("enroll: the clear mode goes through the SAME route into stage() - no new route",
          h.last == (202, {"ok": True, "pending": True, "files": 8}, {})
          and E2.calls == [b'{"mode": "clear"}'], (repr(h.last), repr(E2.calls)))
    check("enroll: ...and the patched stack has no /api/voice/clear route",
          "/api/voice/clear" not in stack_text(), "a second clear route appeared")


# ---------------------------------------------------------------------------
# 4. /api/voice/moment - it speaks text the client already holds
# ---------------------------------------------------------------------------

def t_the_moment_route():
    b = block(stack_text(), 'if path == "/api/voice/moment":')
    if not b:
        return skip("moment route", "the stack no longer writes it")

    h = run(b, path="/api/voice/moment", origin=False)
    check("moment: a cross-origin request is 403",
          h.last and h.last[0] == 403, repr(h.last))

    h = run(b, path="/api/voice/moment", token=False)
    check("moment: no token is 401",
          h.last and h.last[0] == 401, repr(h.last))

    h = run(b, path="/api/voice/moment", modules={"jarvis_speech": None})
    code, out, kw = h.last
    check("moment: with no speech module it is the shared 503",
          code == 503 and out["available"] is False, repr(h.last))
    check("moment: it says the module is not installed, not that an exception happened",
          out["error"] == "the speech module is not installed on this machine"
          and "ModuleNotFoundError" in out["detail"], repr(out))
    check("moment: it OFFERS the client its own fallback - it speaks text the owner holds",
          out["client_fallback_ok"] is True, repr(out))
    check("moment: ...and the reason is the stack's own _SAY_FALLBACK sentence",
          out["reason"] == helpers()["_SAY_FALLBACK"], repr(out["reason"])[:200])

    h = run(b, path="/api/voice/moment", modules={"jarvis_speech": SimpleNamespace()})
    check("moment: a jarvis_speech older than the clip is 503 in words that fit it",
          h.last and h.last[0] == 503 and h.last[1]["available"] is False
          and "older than" in h.last[1]["error"], repr(h.last))

    h = run(b, path="/api/voice/moment",
            modules={"jarvis_speech": speech(raises=RuntimeError("engine exploded"))})
    check("moment: a module that raises is 500, available false, NAME only",
          h.last and h.last[0] == 500 and h.last[1] == {"available": False, "error": "RuntimeError"},
          repr(h.last))

    M = speech(moment=(200, b"RIFF....WAVE"))
    h = run(b, path="/api/voice/moment", modules={"jarvis_speech": M})
    check("moment: a clip comes back 200 as audio/wav",
          h.last and h.last[0] == 200 and h.last[1] == b"RIFF....WAVE"
          and h.last[2].get("ctype") == "audio/wav", repr(h.last))

    h = run(b, path="/api/voice/moment",
            modules={"jarvis_speech": speech(moment=(503, {"available": False, "error": "no voice"}))})
    check("moment: a non-200 from the module is passed through as it is",
          h.last == (503, {"available": False, "error": "no voice"}, {}), repr(h.last))


# ---------------------------------------------------------------------------
# 5. /api/voice/utterance - the patch-written pieces of it
# ---------------------------------------------------------------------------

def t_the_utterance_route_refuses_client_dictation_in_words():
    """The refusal that keeps the privacy boundary where it is."""
    frag = post_image("voice-503.patch", "do NOT recognise this yourself")
    if not frag:
        return skip("utterance missing-module guard", "voice-503.patch no longer adds it")

    h = run(frag, unreadable=False, modules={"jarvis_speech": None})
    code, out, _ = h.last
    check("utterance: with no speech module it is 503", code == 503, repr(h.last))
    check("utterance: available is explicitly false", out["available"] is False, repr(out))
    check("utterance: client_fallback_ok is FALSE - a client must not do its own speech-to-text",
          out["client_fallback_ok"] is False, repr(out))
    check("utterance: the reason tells the client what NOT to do, in words",
          "do NOT recognise this yourself" in out["reason"], repr(out["reason"]))
    check("utterance: ...and says why (the owner-voice gate)",
          "owner-voice gate" in out["reason"], repr(out["reason"]))


def t_the_utterance_barge_in_branch():
    """Interrupting Jarvis by talking: sound, never words."""
    frag = block(stack_text(), 'if src == "barge_in":')
    if not frag:
        return skip("barge-in branch", "voice-flow.patch no longer adds it")

    h = run(frag, src="barge_in", raw=b"RIFF", voice_mic="phone",
            modules={"jarvis_speech": SimpleNamespace()})
    check("barge_in: a module older than the feature answers 'do not stop', as a 200",
          h.last and h.last[0] == 200 and h.last[1]["stop"] is False
          and h.last[1]["why"] == "not_installed", repr(h.last))
    check("barge_in: ...and it never reaches hear(), so nothing is transcribed",
          "available" in h.last[1] and "text" not in h.last[1], repr(h.last))

    M = speech()
    h = run(frag, src="barge_in", raw=b"RIFF-tail", voice_mic="phone",
            modules={"jarvis_speech": M})
    check("barge_in: the clip and the microphone go to barge_in(), nothing else",
          M.seen == [{"mic": "phone"}], repr(M.seen))
    check("barge_in: the answer is the module's own", h.last[1] == {"stop": True}, repr(h.last))

    h = run(frag, src="push_to_talk", raw=b"RIFF", voice_mic="phone",
            modules={"jarvis_speech": SimpleNamespace()})
    check("barge_in: a push-to-talk clip falls straight past this branch",
          h.calls == [], repr(h.calls))


def t_the_utterance_plumbing_reaches_the_module_that_takes_it():
    """A newer jarvis_speech gets the microphone and how long the app waited;
    an older one gets what it always got - never a TypeError."""
    frag = block(stack_text(), 'if getattr(jarvis_speech, "TAKES_WAIT", False):')
    if not frag:
        return skip("mic/waited_ms plumbing", "voice-flow.patch no longer adds it")

    M = speech(takes=("mic", "waited_ms"))
    run(frag, raw=b"RIFF", src="push_to_talk", voice_mic="phone", voice_wait="900",
        modules={"jarvis_speech": M})
    check("plumbing: a module that takes both gets source, mic and waited_ms",
          M.seen == [{"source": "push_to_talk", "mic": "phone", "waited_ms": "900"}],
          repr(M.seen))

    M = speech(takes=("mic",))
    run(frag, raw=b"RIFF", src="push_to_talk", voice_mic="phone", voice_wait="900",
        modules={"jarvis_speech": M})
    check("plumbing: a module with only the mic gets no waited_ms",
          M.seen == [{"source": "push_to_talk", "mic": "phone"}], repr(M.seen))

    M = speech()
    run(frag, raw=b"RIFF", src="push_to_talk", voice_mic="phone", voice_wait="900",
        modules={"jarvis_speech": M})
    check("plumbing: an older module gets source alone, as it always did",
          M.seen == [{"source": "push_to_talk"}], repr(M.seen))


# ---------------------------------------------------------------------------
# 6. The shape the route hands the client - measured on the module that builds it
# ---------------------------------------------------------------------------

def t_the_shape_the_client_reads():
    """`jarvis_speech.Heard.as_dict()` is what `/api/voice/utterance` sends back
    (its own docstring says so), and the phone branches on it. The two refusals
    must stay tellable apart."""
    try:
        import jarvis_speech as S
    except Exception as exc:                                     # pragma: no cover
        return skip("the utterance reply shape", f"jarvis_speech did not import: {exc!r}")

    short = S.Heard(False, source="push_to_talk", seconds=1.6, too_short=True,
                    min_seconds=S._min_command_seconds(),
                    reason=S._too_short_reason(1.6, S._min_command_seconds())).as_dict()
    check("too short: too_short is true", short["too_short"] is True, repr(short))
    check("too short: threshold is 0, so the phone cannot read it as a stranger",
          short["threshold"] == 0.0, repr(short))
    check("too short: nothing was compared - no score, no print, no strictness",
          short["score"] == 0.0 and short["voice_print"] == "" and short["strictness"] == "",
          repr(short))
    check("too short: it is not an owner and not ok", short["is_owner"] is False
          and short["owner"] is False and short["ok"] is False, repr(short))
    check("too short: the floor and the sentence name the seconds",
          short["min_seconds"] > 0 and "too short" in short["reason"] and "2.0" in short["reason"],
          repr(short))

    real = S.Heard(False, source="push_to_talk", seconds=10.9, score=-0.0414,
                   threshold=0.5, voice_print="phone", strictness="very_strict",
                   reason="does not match the enrolled voice (-0.04 < 0.50)").as_dict()
    check("a real refusal: threshold > 0 and the print is named (the phone's own rule)",
          real["too_short"] is False and real["threshold"] > 0 and real["voice_print"] == "phone",
          repr(real))

    noprint = S.Heard(False, source="push_to_talk", seconds=3.0,
                      reason="no enrolled voice profile - run enrolment first").as_dict()
    check("no voice print: refused with words and no crash",
          noprint["is_owner"] is False and "enrol" in noprint["reason"], repr(noprint))
    check("no voice print: and it carries no threshold, so it is not shown as a stranger",
          noprint["threshold"] == 0.0, repr(noprint))

    passed = S.Heard(True, text="hello", threshold=0.5, score=0.71, available=True).as_dict()
    check("a pass: owner and ok are both true, and the words are there",
          passed["is_owner"] is True and passed["owner"] is True and passed["ok"] is True
          and passed["text"] == "hello", repr(passed))

    check("the voice floor the strict check uses is a real number",
          S._min_command_seconds() >= 0.0, repr(S._min_command_seconds()))


# ---------------------------------------------------------------------------
# 7. What this suite cannot reach, said out loud
# ---------------------------------------------------------------------------

def t_the_limits_are_stated_not_skipped():
    """Not a silence: a run must SAY what it did not cover."""
    hud = BACKEND / "jarvis_hud.py"
    if hud.is_file():
        check("the owner's jarvis_hud.py is here, so the whole-file checks in "
              "test_voice_503.py also run", True)
        print("      jarvis_hud.py found at " + str(hud) + ": the routes' ORIGINAL lines "
              "(their dispatch and the line that sends the gate's verdict) are readable here; "
              "test_voice_503.py checks them in this same run.")
    else:
        print("      NOT COVERED OFF THE OWNER'S PC, and not skipped quietly:")
        print("        * the routes' original lines (the dispatch, and `self._send(200, heard)`")
        print("          that hands the gate's verdict to the client) are in no patch, so the")
        print("          whole-file cross-checks need jarvis_hud.py - "
              "test_voice_503.py skips them here;")
        print("        * a real clip through a real voice print (the ACCEPT half) needs his")
        print("          microphone and his models.")
    print(f"      modules under test: {BACKEND}")
    print(f"      this repository   : {REPO}")


if __name__ == "__main__":
    print(f"running against {BACKEND}")
    for fn in (t_the_stack_still_writes_these_routes,
               t_the_turn_route,
               t_the_enroll_route_stages_and_never_enrols,
               t_the_moment_route,
               t_the_utterance_route_refuses_client_dictation_in_words,
               t_the_utterance_barge_in_branch,
               t_the_utterance_plumbing_reaches_the_module_that_takes_it,
               t_the_shape_the_client_reads,
               t_the_limits_are_stated_not_skipped):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
