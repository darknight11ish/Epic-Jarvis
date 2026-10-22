"""test_cloud_lane_taint.py - F6 / Q3: the HUD Cloud lane can never carry a tainted turn.

    python3 backend/test_cloud_lane_taint.py

WHY THIS EXISTS (Gemini coherence ruling Q3 / finding F6, 2026-10-22).  The HUD
has a single-turn **Cloud** lane toggle: the next message goes to a cloud lane
only if the owner presses it for that one question.  Ruling Q3's third part asks
for an exhaustive backend proof that the lane is *mechanically* refused or kept
local when:

  * `jarvis_gate`'s taint latch is active (the ruling calls it `is_tainted()`;
    the published gate's own function is `taint_active()`, see section 1), or
  * the turn reads outside text, or
  * the turn touches email, files, credentials, memory, voiceprint or recordings
    (`jarvis_agent.py:879-883` names the same readers the module docstrings
    list: the sandbox file read, the people dossier, the voiceprint exemplars,
    the self-improvement reads, and the recordings index), or
  * an explicit local-only rule applies (Lockdown, a picture, screen words, a
    cloud model as the "local" model, memory injected server-side, a spent
    budget, a non-Shareable project).

... and that a **plain untainted, non-private turn CAN use the cloud lane** - the
positive control, without which a test that only checks refusals proves nothing.

WHAT IS REAL AND WHAT IS INJECTED.  The decision is **not** re-implemented here:
it is `jarvis_router.choose()`, the one production authority the HUD route, the
chat-stream contract and the auto-router all call.  The gate is the real
published `jarvis-backend/jarvis_gate.py` against a scratch database (the same
copy `test_approval_guards.py` drives).  Every reader's real latch helper is
called.  The only injected pieces are the tests' own inputs: the question text,
the one-turn Cloud "yes", a Lockdown stub module (no owner PC needed), and a
zeroed budget.  No network, no model, no card, no live write.

THE HUD PATH IS READ, NOT RE-IMPLEMENTED.  The HUD's own route is the owner's
`jarvis_hud.py` - not in this repository - so section 7 reads the installed lines out of
`backend/cloud-say-yes.patch` (outside text; the same evidence
`test_cloud_say_yes.py` uses) and shows that route passes `conversation_tainted`
and the one-turn `cloud_yes` into the real `choose()`.  The decision authority
is then exercised with exactly those arguments.  What is NOT proved here: the
HUD's private `_history_tainted()` body (owner file), and the HUD's own
memory-injection latch call (owner file) - for both, section 2/section 4 prove the latch or
boolean they feed into refuses every input it can carry.

HONEST LIMITS, stated here because the ruling asks for exhaustive on the paths
that exist, not for claims about paths that do not:
  * `test_secure_preconditions`/other suites may cover the same helpers; this
    file is the one place that connects every private-category latch to the
    Cloud-lane decision.
  * The email tool's own end-of-turn taint is recorded through the chat log
    (`jarvis_agent.py`'s `_note_outside_now`); that database path is not driven
    here.  A typed email/inbox/credential question travels through the router's
    private backstop (tested, section 3), and the email/files tools are local-lane tools
    - a cloud turn is never handed a tool (jarvis_agent.py:15).
  * The Linux "no cap"-style platform branch is irrelevant here: `choose()` is
    pure Python on every platform.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
REBUILT = HERE / "rebuilt"

#: A scratch home BEFORE anything imports the gate: jarvis_gate reads its
#: database path from the environment at import time.  The owner's own
#: ~/.openjarvis is never touched.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-cloud-lane-taint-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")
# No push, said explicitly rather than relied on: this suite must not post a
# card anywhere, and an owner with ntfy configured would otherwise get one.
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
# The REAL repository config names the private topics ([privacy]
# never_leaves_device); without it the router still has its built-in list, but
# the test would be weaker than "against the shipped config".
CONFIG = next((p for p in (BASE / "jarvis-framework.toml",
                           REBUILT / "jarvis-framework.toml") if p.is_file()), None)
if CONFIG is not None:
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(CONFIG)

# The published gate, first on the path, then the shipped library modules -
# the same import discipline as test_approval_guards.py.
_SAVED_PATH = list(sys.path)
_SAVED_DONT_WRITE_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(REBUILT))
import jarvis_gate as GATE  # noqa: E402
import jarvis_router as RT  # noqa: E402

sys.path[:] = _SAVED_PATH
sys.dont_write_bytecode = _SAVED_DONT_WRITE_BYTECODE
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_agent as AG  # noqa: E402
import jarvis_auto_router as AR  # noqa: E402
import jarvis_people_crm as PEOPLE  # noqa: E402
import jarvis_self_improve as SI  # noqa: E402
import jarvis_voiceprint as VP  # noqa: E402

FAILED, PASSED = [], []

LOCAL = "qwen3.5:9b"
#: The three cloud lanes the owner's own config defines (docs / litellm config).
LANES = ["jarvis-escalate", "jarvis-critic", "jarvis-bulk"]
CLOUD = LANES[0]
#: Long and clause-heavy: the complexity gate alone would let it out, so a
#: refusal below can only come from the gate named in that check.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _hud_route(text, *, tainted, cloud_yes, memory_injected=False,
               has_image=False, has_screen=False, lanes=None, budget=None,
               local_model=LOCAL):
    """The HUD route's `jarvis_router.choose(...)` call, byte-for-byte its arguments.

    `backend/cloud-say-yes.patch` installs exactly this shape in the owner's
    `jarvis_hud.py`: the taint answer in `conversation_tainted`, the one-turn
    Cloud button in `owner_said_yes`, no lanes at all while the HUD injects
    memory, and the image/screen flags.  Every check below calls the REAL
    `choose()` with that same shape, so a new gate or a reordered gate is seen.
    """
    return RT.choose(
        text,
        local_model=local_model,
        lanes=[] if memory_injected else list(LANES if lanes is None else lanes),
        has_image=has_image,
        conversation_tainted=bool(tainted),
        budget=budget if budget is not None else RT.Budget(path=None),
        owner_said_yes=bool(cloud_yes),
        has_screen=has_screen,
    )


def _is_cloud(decision) -> bool:
    return str(getattr(decision, "lane", "")) in LANES


def _local(decision) -> bool:
    return (str(getattr(decision, "lane", "")) == LOCAL
            and not _is_cloud(decision)
            and not getattr(decision, "offer", ""))


def _reset():
    """A clean latch and an empty scratch database before every case."""
    GATE._init()
    GATE.clear_taint()


# ==========================================================================
#  0. the real pieces are loaded - otherwise every check below is theatre
# ==========================================================================

def t_real_pieces_are_loaded():
    check("the REAL published gate is loaded from jarvis-backend/jarvis_gate.py",
          Path(GATE.__file__).resolve() == (BASE / "jarvis_gate.py").resolve(),
          GATE.__file__)
    check("... and the REAL router is the one the HUD calls",
          Path(RT.__file__).resolve().name == "jarvis_router.py"
          and hasattr(RT, "choose"), RT.__file__)
    check("... and the shipped config is the one that names the private topics",
          CONFIG is not None and os.environ.get("JARVIS_FRAMEWORK_TOML") == str(CONFIG),
          CONFIG)
    check("the latch starts clean", GATE.taint_active() is False)
    check("the control question is complex enough that ONLY a privacy gate keeps it local",
          RT.complexity(HARD) >= 0.40, RT.complexity(HARD))


# ==========================================================================
#  1. `jarvis_gate`'s own latch forces the Cloud lane local, every way HUD asks
# ==========================================================================

def t_the_gate_latch_forces_the_cloud_lane_local():
    _reset()
    check("the real gate latch works (this is the ruling's `is_tainted()`: the "
          "published function is `taint_active`)",
          GATE.latch_taint(why="outside_text") is True and GATE.taint_active() is True)
    tainted = GATE.taint_active()

    for cloud_yes in (True, False):
        d = _hud_route(HARD, tainted=tainted, cloud_yes=cloud_yes)
        check(f"tainted + HUD Cloud yes={cloud_yes}: the turn is local on gate 'taint'",
              d.lane == LOCAL and d.gate == "taint", (d.lane, d.gate, d.reason))
        check(f"tainted + HUD Cloud yes={cloud_yes}: NO cloud lane is offered",
              d.offer == "" and not _is_cloud(d), repr(d.as_dict()))
        check(f"tainted + HUD Cloud yes={cloud_yes}: the decision SAYS it is tainted",
              d.tainted is True)
        check(f"tainted + HUD Cloud yes={cloud_yes}: it is a LOCAL turn, so any "
              f"memory stays on this PC (a cloud lane would carry none)",
              d.lane == LOCAL and d.inject_memory is True)

    # While the HUD injects memory it passes lanes=[]; taint still local.
    d = _hud_route(HARD, tainted=tainted, cloud_yes=True, memory_injected=True)
    check("tainted + memory injected: local (gate 'unavailable' is the HUD's own "
          "no-lanes path, reached before taint, and is still local)",
          d.lane == LOCAL and d.gate in ("unavailable", "taint") and d.offer == "",
          (d.lane, d.gate))

    # The older spelling is still refused - a second code path to the same gate.
    d = RT.choose(HARD, local_model=LOCAL, lanes=LANES, tainted=True,
                  budget=RT.Budget(path=None), owner_said_yes=True)
    check("the older `tainted=` spelling cannot bypass the latch either",
          d.lane == LOCAL and d.gate == "taint" and d.offer == "", (d.lane, d.gate))

    # ... and a tainted turn with a SPENT budget still says taint, not budget:
    # order is policy (a later gate cannot mask an earlier refusal).
    d = _hud_route(HARD, tainted=tainted, cloud_yes=True,
                   budget=RT.Budget(per_minute=0, per_day=0))
    check("taint is decided BEFORE the budget - a spent budget cannot hide it",
          d.lane == LOCAL and d.gate == "taint", (d.lane, d.gate))

    # The single-turn contract: the next UNTAINTED message can use the Cloud lane.
    GATE.clear_taint()
    check("clearing the latch really clears it", GATE.taint_active() is False)
    d = _hud_route(HARD, tainted=GATE.taint_active(), cloud_yes=True)
    check("THE NEXT UNTAINTED MESSAGE CAN USE THE CLOUD LANE (positive control)",
          d.lane == CLOUD and d.gate == "escalate", (d.lane, d.gate, d.reason))
    check("... and is not reported tainted", d.tainted is False)
    check("... and carries NO memory (inject_memory False on every cloud lane)",
          d.inject_memory is False)
    # The same latch, set again, refuses the very next message.
    GATE.latch_taint(why="outside_text")
    d = _hud_route(HARD, tainted=GATE.taint_active(), cloud_yes=True)
    check("... and the turn AFTER a taint is local again, even with the Cloud yes",
          d.lane == LOCAL and d.gate == "taint", (d.lane, d.gate))
    _reset()


# ==========================================================================
#  2. every real private-category reader latches, and the Cloud lane refuses
# ==========================================================================

def t_every_real_private_reader_latches():
    """`jarvis_agent.py:879-883` names the readers: recordings, files, people
    dossier, voiceprint, self-improvement.  Each real helper is called; each
    must set the gate's own latch, and the HUD route must then be local."""
    cases = (
        ("recordings (media index search)", "recordings", lambda: AG._latch_media_index_read()),
        ("files (sandbox file read)", "files", lambda: AG._latch_sandbox_tool_read()),
        ("people dossier read", "people", lambda: PEOPLE._latch_taint()),
        ("voiceprint exemplars read", "voiceprint",
         lambda: (VP._latch("voiceprint_exemplars"), True)[1]),
        ("self-improvement reads", "memory/self-improve",
         lambda: SI._latch("self_improve_diagnosis")),
    )
    for label, _category, reader in cases:
        _reset()
        try:
            fired = reader()
        except Exception as exc:  # noqa: BLE001 - report, never crash the suite
            check(f"{label}: the real reader's latch helper runs", False,
                  f"{type(exc).__name__}: {exc}")
            continue
        check(f"{label}: the reader's own latch fired (returns truthy)", bool(fired))
        check(f"{label}: the gate now reports the conversation tainted",
              GATE.taint_active() is True)
        tainted = GATE.taint_active()
        d = _hud_route(HARD, tainted=tainted, cloud_yes=True)
        check(f"{label}: the HUD Cloud lane is REFUSED for the next message",
              d.lane == LOCAL and d.gate == "taint" and d.offer == "",
              (d.lane, d.gate, repr(d.offer)))
        check(f"{label}: ... and no cloud lane appears anywhere in the decision",
              not _is_cloud(d))
        _reset()
    # The reader helpers are the agent's own - not a copy of them.
    check("the recordings reader is jarvis_agent's own latch helper",
          getattr(AG._latch_media_index_read, "__module__", "") == "jarvis_agent")
    check("the files reader is jarvis_agent's own sandbox latch helper",
          getattr(AG._latch_sandbox_tool_read, "__module__", "") == "jarvis_agent")
    check("the voiceprint latch is the module's own one seam, documented as such",
          "One seam, so the suite can see it happen" in (VP._latch.__doc__ or ""))
    check("the self-improvement latch is the module's own gate helper",
          "latch" in (SI._latch.__doc__ or ""))


# ==========================================================================
#  3. private-material QUESTIONS hit the real backstop, even with the Cloud yes
# ==========================================================================

def t_private_material_questions_are_kept_local():
    email = "summarise my inbox and the emails from Sam"
    files = "read the files on disk and compare them"
    creds = "what is my api key for the chatbot"
    memory = "search my notes and vault for the meeting"
    calendar = "what is on my calendar tomorrow"
    money = "compare my bank statement with last month"
    medical = "what did my doctor say about the prescription"
    recording = "search my recordings for the word invoice"

    for label, question in (
            ("email/inbox", email), ("files", files), ("credentials", creds),
            ("memory/notes", memory), ("calendar", calendar), ("bank", money),
            ("medical", medical), ("recordings", recording)):
        check(f"the real backstop recognises the {label} question",
              RT.is_private(question) is True, question)
        d = _hud_route(question, tainted=False, cloud_yes=True)
        check(f"the {label} question stays local on gate 'private', even with the Cloud yes",
              d.lane == LOCAL and d.gate == "private" and d.offer == "",
              (d.lane, d.gate, repr(d.offer)))
        check(f"... and no cloud lane is offered for the {label} question",
              not _is_cloud(d))

    check("a plain, non-private question does NOT match the backstop",
          RT.is_private("Explain how photosynthesis works in plants.") is False)
    d = _hud_route(HARD, tainted=False, cloud_yes=True)
    check("... and the clean control still reaches the Cloud lane (the backstop "
          "is not just 'everything stays local')", d.lane == CLOUD, (d.lane, d.gate))

    # Credentials pasted literally, with no word for what they are, are gate 3.
    for sample in ("sk-proj-abcdefghijklmnop1234567890",
                   "-----BEGIN OPENSSH PRIVATE KEY-----",
                   "api_key=supersecretvalue"):
        found = RT.looks_like_a_secret(sample)
        check(f"the real secret detector recognises {sample[:18]!r}...", bool(found), found)
        d = _hud_route(HARD + "\n" + sample, tainted=False, cloud_yes=True)
        check(f"... and that message is local (gate 'secret' or the private "
              f"backstop) with the Cloud yes",
              d.lane == LOCAL and d.gate in ("secret", "private") and d.offer == "",
              (d.lane, d.gate, d.reason))

    # Memory / voiceprint / recordings questions are ALSO on the project's own
    # sensitive-question detector (used when a read is prepared).
    for label, q in (("memory", "what do you remember about me"),
                     ("voiceprint", "is this my voiceprint")):
        check(f"the project's sensitive-question detector names the {label} question",
              SI.is_sensitive(q) is True, q)
    check("the recordings question is a router backstop word too (the config list)",
          RT.is_private("search my recordings for the word invoice") is True
          or RT.is_private("search my recordings") is True)


# ==========================================================================
#  4. the explicit local-only rules: each one keeps the Cloud lane local
# ==========================================================================

def t_explicit_local_only_rules():
    # Lockdown: a stub module, because jarvis_asks_first is not part of this
    # checkout's staged backend - but the router's real `lockdown_on()` imports
    # it by name, so a stub proves the production import path.
    fake = types.ModuleType("jarvis_asks_first")
    fake.lockdown_on = lambda: True
    sys.modules["jarvis_asks_first"] = fake
    try:
        d = _hud_route(HARD, tainted=False, cloud_yes=True)
        check("Lockdown on: local on gate 'lockdown', even with the Cloud yes",
              d.lane == LOCAL and d.gate == "lockdown" and d.offer == "",
              (d.lane, d.gate))
    finally:
        sys.modules.pop("jarvis_asks_first", None)

    # A cloud model as the "local" model is a cloud lane with no yes and no
    # memory - gate -1, before every other gate.
    d = _hud_route(HARD, tainted=False, cloud_yes=True, local_model="gpt-oss:120b-cloud")
    check("a cloud model as the everyday model: refused on gate 'cloud_model', "
          "no memory, no offer",
          d.lane == "gpt-oss:120b-cloud" and d.gate == "cloud_model"
          and d.offer == "" and d.inject_memory is False,
          (d.lane, d.gate, d.inject_memory))

    d = _hud_route(HARD, tainted=False, cloud_yes=True, has_image=True)
    check("a picture always stays local on gate 'image'", d.lane == LOCAL and d.gate == "image")
    d = _hud_route(HARD, tainted=False, cloud_yes=True, has_screen=True)
    check("screen words always stay local on gate 'screen'", d.lane == LOCAL and d.gate == "screen")

    # Memory injected by the HUD: its route passes lanes=[], so no cloud lane
    # exists for the decision to choose.
    d = _hud_route(HARD, tainted=False, cloud_yes=True, memory_injected=True)
    check("memory injected server-side: local on gate 'unavailable', nothing offered",
          d.lane == LOCAL and d.gate == "unavailable" and d.offer == "",
          (d.lane, d.gate))
    # The HUD's own memory-injection latch (jarvis_hud.py:4726, cited by
    # jarvis_auto_router.py:314) is a `jarvis_gate.latch_taint` call; drive it.
    _reset()
    GATE.latch_taint(why="memory_injected")
    d = _hud_route(HARD, tainted=GATE.taint_active(), cloud_yes=True)
    check("the HUD's memory-injection latch forces the Cloud lane local too",
          d.lane == LOCAL and d.gate == "taint", (d.lane, d.gate))
    _reset()

    d = _hud_route(HARD, tainted=False, cloud_yes=True, budget=RT.Budget(per_minute=0, per_day=0))
    check("a spent cloud budget: local on gate 'budget'", d.lane == LOCAL and d.gate == "budget")
    d = _hud_route("hi", tainted=False, cloud_yes=True)
    check("a short/ordinary question: local on gate 'complexity'", d.lane == LOCAL and d.gate == "complexity")

    # A project that is not marked Shareable is local-only, through the real
    # auto-router helper (the same `choose()` authority underneath).
    check("a non-Shareable project is local-only (auto-router taint_latched)",
          AR.taint_latched({"shareable": False})[0] is True)
    check("a Shareable project with a clean gate is not blocked by that rule",
          AR.taint_latched({"shareable": True})[0] is False)


# ==========================================================================
#  5. the auto-router path (`_router_allows`) obeys the same authority
# ==========================================================================

def t_the_auto_router_path_obeys_the_same_authority():
    _reset()
    allowed, gate, why = AR._router_allows(HARD, CLOUD, budget=None, tainted=True)
    check("auto-router: a tainted question can never be recommended",
          allowed is False and gate == "router_refused:taint", (allowed, gate, why))
    allowed, gate, why = AR._router_allows(HARD, CLOUD, budget=None, tainted=False)
    check("auto-router: the same clean question is allowed - so the block above is real",
          allowed is True and gate == "escalate", (allowed, gate, why))

    _reset()
    check("auto-router taint_latched: a clean latch is not blocked", AR.taint_latched(None) == (False, ""))
    GATE.latch_taint(why="people_crm")
    tainted, why = AR.taint_latched(None)
    check("auto-router taint_latched: a latched gate blocks, with plain words",
          tainted is True and "personal material" in why, (tainted, why))
    out = AR.evaluate_route(HARD, enabled=True)
    check("auto-router evaluate_route: TURN ON but latched -> local, gate taint_latched_local_only",
          out.get("lane") == AR.LOCAL_LANE
          and out.get("recommended") is False
          and out.get("gate") == "taint_latched_local_only",
          {k: out.get(k) for k in ("lane", "recommended", "gate", "why")})
    _reset()


# ==========================================================================
#  6. `degrade()` can never walk a local turn back out to the cloud
# ==========================================================================

def t_degrade_never_walks_local_back_to_cloud():
    cases = (
        [LOCAL, CLOUD, LANES[1]],
        [CLOUD, LOCAL],
        [CLOUD, LOCAL, LANES[1]],
        [LOCAL],
        [LANES[1], LANES[2], LOCAL],
        ["qwen3:8b", CLOUD],
    )
    for lanes in cases:
        got = RT.degrade(LOCAL, lanes=lanes, local_model=LOCAL)
        check(f"degrade(local, {lanes}) never returns a cloud lane",
              got is None or got == LOCAL, repr(got))
        check(f"degrade(local, {lanes}) never returns its own input (local)",
              got != LOCAL)
    # The historical bypass: local appeared in the lane list, and the walk used
    # to move past it to the cloud entry after it.
    got = RT.degrade(LOCAL, lanes=[LOCAL, "a", "b"], local_model=LOCAL)
    check("the historical bypass (local inside the list, cloud after it) returns None",
          got is None, repr(got))
    # From a cloud lane the degrade chain may go through other cloud lanes, but
    # it must reach local rather than cycle or return the refusing lane.
    got = RT.degrade(CLOUD, lanes=[CLOUD, LOCAL, LANES[1]], local_model=LOCAL)
    check("degrade(cloud, [...]) never returns the lane that refused", got != CLOUD)
    check("degrade never returns an empty lane", bool(got))


# ==========================================================================
#  7. the HUD route that feeds all this: read its installed lines (outside text)
# ==========================================================================

def t_the_hud_route_passes_taint_and_the_one_turn_yes():
    patch = HERE / "cloud-say-yes.patch"
    check("the HUD route patch is here", patch.is_file(), patch)
    text = patch.read_text(encoding="utf-8")
    added = [ln[1:] for ln in text.splitlines()
             if ln.startswith("+") and not ln.startswith("+++")]
    installed = "\n".join(added)
    context = "\n".join(ln[1:] for ln in text.splitlines()
                         if ln.startswith(" ") and len(ln) > 1)

    both = installed + "\n" + context
    check("the HUD route passes the taint answer to the real choose(): "
          "`conversation_tainted=tainted`", "conversation_tainted=tainted" in both)
    check("... and the one-turn Cloud button as `owner_said_yes=bool(body.get(\"cloud_yes\"))`",
          'owner_said_yes=bool(body.get("cloud_yes"))' in installed)
    check("... and passes NO lanes while the HUD injects memory",
          "lanes=[] if jarvis_side_memory" in installed)
    check("... and the installed call passes `has_image` (a picture always stays local)",
          "has_image=bool(body.get(\"has_image\"))" in both)
    check("... and `tainted` is the HUD's own history/taint answer "
          "(`_history_tainted(messages, body)`), not something a request can set",
          "tainted = _history_tainted(messages, body)" in context)
    check("the patch changes the HUD route only (no backend module is patched here)",
          "+++ b/jarvis_hud.py" in text and "+++ b/jarvis_router.py" not in text)
    check("... the route makes exactly ONE router decision per turn",
          both.count("decision = jarvis_router.choose(") == 1,
          both.count("decision = jarvis_router.choose("))
    keyword_lines = [ln for ln in installed.splitlines()
                     if ln.lstrip().startswith("lanes=")]
    check("... and it installs exactly ONE `lanes=` keyword on the call "
          "(a repeated keyword is a SyntaxError that stops the backend starting)",
          len(keyword_lines) == 1, keyword_lines)
    check("the router's own docstring warns about the silently-swallowed-taint bug "
          "this test pins: the gate must never be eaten by `**kwargs`",
          "NEVER FIRED from the only production caller" in (RT.choose.__doc__ or ""))


# ==========================================================================
#  8. the decision contract the apps read: a refused turn says so in the dict
# ==========================================================================

def t_the_route_decision_contract_cannot_claim_cloud():
    _reset()
    GATE.latch_taint(why="outside_text")
    d = _hud_route(HARD, tainted=GATE.taint_active(), cloud_yes=True)
    as_dict = d.as_dict()
    check("X-Jarvis-Route: the tainted decision's lane is the LOCAL lane",
          as_dict.get("lane") == LOCAL, as_dict.get("lane"))
    check("... its gate names the refusal, not 'escalate'",
          as_dict.get("gate") == "taint" and as_dict.get("gate") != "escalate",
          as_dict.get("gate"))
    check("... it offers no cloud lane (`offer` empty, the field the apps read)",
          as_dict.get("offer") == "", repr(as_dict.get("offer")))
    check("... it is a LOCAL turn, so any injected memory stays on this PC "
          "(no cloud lane receives it)",
          as_dict.get("lane") == LOCAL and as_dict.get("inject_memory") is True)
    check("... and `tainted` is True, so a client cannot show a Cloud badge",
          as_dict.get("tainted") is True)
    _reset()
    d = _hud_route(HARD, tainted=False, cloud_yes=True)
    as_dict = d.as_dict()
    check("the clean control's dict says lane=cloud, gate=escalate, no memory",
          as_dict.get("lane") == CLOUD and as_dict.get("gate") == "escalate"
          and as_dict.get("inject_memory") is False, as_dict)


# ==========================================================================
#  main
# ==========================================================================

def main():
    print(__doc__.splitlines()[0])
    print()
    tests = (
        ("0. the real pieces are loaded", t_real_pieces_are_loaded),
        ("1. the gate latch forces the Cloud lane local", t_the_gate_latch_forces_the_cloud_lane_local),
        ("2. every real private-category reader latches", t_every_real_private_reader_latches),
        ("3. private-material questions stay local", t_private_material_questions_are_kept_local),
        ("4. explicit local-only rules", t_explicit_local_only_rules),
        ("5. the auto-router path obeys the same authority", t_the_auto_router_path_obeys_the_same_authority),
        ("6. degrade never walks local back to cloud", t_degrade_never_walks_local_back_to_cloud),
        ("7. the HUD route that feeds this", t_the_hud_route_passes_taint_and_the_one_turn_yes),
        ("8. the route decision contract", t_the_route_decision_contract_cannot_claim_cloud),
    )
    for label, fn in tests:
        print(f"-- {label}")
        try:
            fn()
        except Exception:
            FAILED.append(label)
            print(f"FAIL  {label} raised\n        {traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(str(x) for x in FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
