"""A local turn must always be answerable - even when the SAVED model cannot run there.

    python3 backend/test_local_model_guard.py

THE DEFECT THIS SUITE PROVES FIXED, measured live on the owner's PC the night
of 2026-11-17/18 (a private question, `X-Jarvis-Route` gate "taint",
`where: local`):

    ~/.openjarvis/model-state.json said the everyday model was
    `qwen3-coder-30b-a3b-ud-q3-k-xl` - the Coding preset's pooled three-card
    model, written there by the live install's own preset apply (the repository
    half of that is PR #1361). The router trusted "current" for a LOCAL turn
    without asking whether that model can run on the everyday lane, and
    `jarvis_agent.local_model_refusal` then refused to load a pooled model on a
    one-card lane - honestly, in the words the owner was shown, and with
    nothing sent anywhere. The privacy behaviour was right; the turn produced
    NO ANSWER AT ALL.

The refusal stays (the spill it prevents is real). What this suite proves is
the other half:

  1. `jarvis_router.choose()` validates the chosen model against the lane the
     turn will really use, BEFORE the decision is returned, and when the saved
     model cannot run there it names the model that lane is configured for
     instead. The gate, the local lane and `inject_memory` are unchanged; the
     route detail says what was asked for, what will run, and why.
  2. The model it falls back to passes `jarvis_agent.local_model_refusal` -
     i.e. the very check `run_local_turn` makes before a request is sent - so
     the turn is answerable, not refused a second time.
  3. A local turn whose model is fine is BYTE FOR BYTE the same decision it
     was before this change (`degraded_from` is absent, not empty), and a cloud
     turn is not pulled local.
  4. THE HUD RUNS THE FALLBACK LOCALLY. A router-only change would NOT have
     been enough, and this is the part that matters most: the HUD decides
     "this is a local turn" as `lane == local_model`, so a fallback model name
     made `use_tools` false and sent the turn to the plain cloud relay. That
     relay used to resolve a lane name it did not know through
     `jarvis_chatbot_api.lane_service()` to a CLOUD provider (measured below;
     `DEFAULT_LANE` is DeepSeek), so with a saved provider key a PRIVATE prompt
     could have reached a cloud provider - rule 1 broken by a fix intended to
     protect it. `local-model-guard.patch` is the ONE line that keeps that turn
     on the local answering loop, and since the owner's 2026-11-18 ruling the
     relay fails closed as well: an unknown name names NO service. The two are
     defence in depth, and this suite reads the patched HUD's own expressions
     and evaluates them, so the proof is of the shipped text and not of a
     second copy of its logic.

WHAT IS REAL AND WHAT IS INJECTED. The router, the refusal authority
(`jarvis_agent.local_model_refusal`), the lane tables (`jarvis_model_lanes`,
`jarvis_big_coder`), the published preset module and the cloud-lane name
mapping (`jarvis_chatbot_api.lane_service`) are the real modules. The only
injected pieces are the owner's own INPUTS: a scratch config directory with a
`config.toml` naming the everyday model, and the `OLLAMA_URL` that names the
lane. No network, no model, no card, no live write: `choose()` opens nothing,
and every call that could touch a lane is a table read.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
REBUILT = HERE / "rebuilt"

#: A scratch config directory BEFORE any module reads one: `jarvis_framework`
#: and `jarvis_presets` read their config directory at import, and the owner's
#: own ~/.openjarvis must never be touched by a test.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-local-model-guard-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ.pop("OLLAMA_URL", None)
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")
# No push, said explicitly rather than relied on (the same discipline
# test_cloud_lane_taint.py uses): nothing here may post a card anywhere.
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

#: The real repository config, for `[routing]` and `[privacy]`. Absent in a
#: base-only checkout: every default then applies, exactly as on a live PC.
CONFIG = next((p for p in (BASE / "jarvis-framework.toml",
                           REBUILT / "jarvis-framework.toml") if p.is_file()), None)
if CONFIG is not None:
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(CONFIG)

# The shipped library modules, then this repository's own copies (the same
# import discipline test_cloud_lane_taint.py uses). jarvis_router is a rebuilt
# module, so it is read from backend/rebuilt/; jarvis_agent is shipped whole,
# so the copy backend/ carries is the one the live install receives.
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(REBUILT))
import jarvis_router as RT  # noqa: E402
sys.path.insert(0, str(HERE))
import jarvis_agent as AG  # noqa: E402
import _stack  # noqa: E402

SCRATCH_CONFIG = SCRATCH / "config.toml"
LANE_FILE = SCRATCH / "presets-active-lane.json"

FAILED, PASSED = [], []

PATCH = HERE / "local-model-guard.patch"
POOLED = "qwen3-coder-30b-a3b-ud-q3-k-xl"
ONE_CARD = "http://127.0.0.1:11434"
NAMED_EVERYDAY = "http://127.0.0.1:11436"
POOLED_LANE = "http://127.0.0.1:11450"
EVERYDAY_MODEL = "qwen3.5:9b"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def use_lane(url: str, *, default_model: str = EVERYDAY_MODEL) -> None:
    """Point this process's everyday lane at `url` for one test.

    Two of the owner's own inputs decide where a local turn runs and what the
    lane is configured for: the `OLLAMA_URL` environment, and
    `[intelligence] default_model` in `config.toml`. No lane file is written -
    a scratch config directory with none is exactly a fresh install.
    """
    os.environ["OLLAMA_URL"] = url
    if LANE_FILE.exists():
        LANE_FILE.unlink()
    SCRATCH_CONFIG.write_text(
        f'[intelligence]\ndefault_model = "{default_model}"\n', encoding="utf-8")


def everyday_from_the_lane_table(port: int) -> str:
    """The model `jarvis_big_coder.LANES` says the lane on `port` must hold."""
    import jarvis_big_coder as big
    for row in big.LANES:
        if int(getattr(row, "port", 0) or 0) == int(port):
            return str(row.model)
    return ""


def _passes_the_turns_own_check(model: str, lane_url: str) -> bool:
    """What `run_local_turn` asks before it sends anything: "" is "would run"."""
    return AG.local_model_refusal(lane_url, model) == ""


# ==========================================================================
#   1. The local fallback: the turn is answered, on the lane's own model
# ==========================================================================

def t_a_tainted_turn_whose_saved_model_is_pooled_answers_with_the_lane_model():
    use_lane(ONE_CARD)
    d = RT.choose("what did I write in my notes about the plan",
                  local_model=POOLED, lanes=["jarvis-escalate"],
                  conversation_tainted=True, budget=RT.Budget(path=None))
    check("a tainted turn whose SAVED model is a pooled three-card model is "
          "still answered on this PC", d.gate == "taint" and d.inject_memory is True,
          d.as_dict())
    check("... by the model the everyday lane is configured for",
          d.lane == EVERYDAY_MODEL, d.lane)
    check("... and that model passes the refusal run_local_turn makes before "
          "it sends anything, so the turn really answers",
          _passes_the_turns_own_check(d.lane, ONE_CARD),
          AG.local_model_refusal(ONE_CARD, d.lane))
    check("... the replacement is never a model answered off this machine",
          RT.is_remote_model(d.lane) is False, d.lane)
    detail = d.as_dict().get("degraded_from")
    check("... the route detail records what was ASKED FOR and what was USED",
          isinstance(detail, list) and len(detail) == 1
          and detail[0].get("lane") == POOLED
          and detail[0].get("model") == EVERYDAY_MODEL,
          detail)
    check("... and WHY, in the refusal's own words",
          isinstance(detail, list) and "pooled three-card model" in str(detail[0].get("why"))
          and detail[0].get("code") == RT.MODEL_CANNOT_RUN_HERE, detail)
    check("... the reason names both models too, so the header alone is "
          "diagnosable", POOLED in d.reason and EVERYDAY_MODEL in d.reason, d.reason)
    check("the route detail survives a JSON round trip (it is a header value)",
          json.loads(json.dumps(d.as_dict()))["degraded_from"][0]["lane"] == POOLED)
    # The same shape on the other local gates: no cloud lane offered at all is
    # still a local turn, and it must be answerable just the same.
    d2 = RT.choose("summarise the meeting notes from yesterday",
                   local_model=POOLED, lanes=[], budget=RT.Budget(path=None))
    check("a local turn with NO cloud lane offered falls back the same way",
          d2.gate == "unavailable" and d2.lane == EVERYDAY_MODEL
          and d2.degraded_from, d2.as_dict())


def t_the_saved_model_may_carry_ollamas_latest_tag():
    """`/api/ps` and `ollama list` report a pooled model with `:latest`."""
    use_lane(ONE_CARD)
    d = RT.choose("what is my home address", local_model=POOLED + ":latest",
                  lanes=["jarvis-escalate"], budget=RT.Budget(path=None))
    check("a pooled model saved with Ollama's `:latest` tag is recognised too",
          d.gate == "private" and d.lane == EVERYDAY_MODEL
          and d.degraded_from[0]["lane"] == POOLED + ":latest", d.as_dict())


def t_the_named_everyday_lane_uses_its_own_table_model():
    """A lane 11436 turn falls back to the model THAT LANE must hold."""
    use_lane(NAMED_EVERYDAY)
    expected = everyday_from_the_lane_table(11436)
    if not expected:
        return check("jarvis_big_coder.LANES names a model for the everyday "
                     "lane", False, "the lane table could not be read")
    fallback = RT.local_model_fallback(POOLED, NAMED_EVERYDAY)
    check("a lane the lane table names gets that lane's own model",
          fallback.get("model") == expected, fallback)
    check("... and that model is one this lane can hold",
          _passes_the_turns_own_check(expected, NAMED_EVERYDAY), expected)


def t_the_fallback_is_never_a_model_this_lane_cannot_hold():
    """No swap to a second invalid model: then the honest refusal stands."""
    use_lane(ONE_CARD)
    real = RT.lane_configured_model
    RT.lane_configured_model = lambda lane_url="", **kw: POOLED
    try:
        check("when the lane's own configured model is ALSO one it cannot "
              "hold, no fallback is made (the refusal is not hidden by a "
              "second invalid choice)",
              RT.local_model_fallback(POOLED, ONE_CARD) == {})
        d = RT.choose("what is my home address", local_model=POOLED, lanes=[],
                      budget=RT.Budget(path=None))
        check("... and the decision is left exactly as it was",
              d.lane == POOLED and not d.as_dict().get("degraded_from"), d.as_dict())
    finally:
        RT.lane_configured_model = real
    use_lane(ONE_CARD, default_model="glm-4.6:cloud")
    check("a configured everyday model that is itself a CLOUD model is never "
          "used as the fallback", RT.local_model_fallback(POOLED, ONE_CARD) == {},
          RT.lane_configured_model(ONE_CARD))
    use_lane(ONE_CARD, default_model="")
    # The last resort in the lane table: the model the everyday lane's own row
    # must come back holding. Read, never typed here.
    last_resort = everyday_from_the_lane_table(11436)
    check("with no configured everyday model to read, the lane table's own "
          "everyday model is the last resort - never nothing",
          RT.local_model_fallback(POOLED, ONE_CARD).get("model") == last_resort,
          (last_resort, RT.local_model_fallback(POOLED, ONE_CARD)))


# ==========================================================================
#   2. What must NOT change: a fine model, a cloud turn, the refusal
# ==========================================================================

def t_an_ordinary_local_turn_is_unchanged():
    use_lane(ONE_CARD)
    d = RT.choose("hello there", local_model=EVERYDAY_MODEL,
                  lanes=["jarvis-escalate"], budget=RT.Budget(path=None))
    detail = d.as_dict()
    check("a local turn whose saved model is fine keeps its lane",
          d.lane == EVERYDAY_MODEL and d.gate == "complexity", detail)
    check("... and gains NO degraded_from entry (absent, not empty)",
          "degraded_from" not in detail, detail)
    check("... so its route detail is exactly the keys it had before this "
          "change - no new log noise on an ordinary turn",
          set(detail) == {"lane", "reason", "gate", "complexity",
                          "inject_memory", "tainted", "offer", "auto"}, sorted(detail))
    unchanged = RT.choose("hello there", local_model=EVERYDAY_MODEL, lanes=[])
    check("a no-cloud-lane local turn is unchanged too",
          unchanged.lane == EVERYDAY_MODEL and "degraded_from" not in unchanged.as_dict(),
          unchanged.as_dict())


def t_a_cloud_turn_is_not_pulled_local():
    use_lane(ONE_CARD)
    long_q = ("explain in detail, step by step, why the trade-offs of three "
              "sorting algorithms differ, and compare them ") * 3
    d = RT.choose(long_q, local_model=EVERYDAY_MODEL, lanes=["jarvis-escalate"],
                  budget=RT.Budget(path=None), owner_said_yes=True)
    check("a turn the owner said yes to still reaches the cloud lane",
          d.gate == "escalate" and d.lane == RT.CLOUD_LANE
          and d.inject_memory is False, d.as_dict())
    check("... with no local fallback field anywhere in its route detail",
          "degraded_from" not in d.as_dict(), d.as_dict())
    # Even a pooled SAVED model must not drag a cloud turn down to local: the
    # fallback only ever replaces a model on a decision that is already local.
    d2 = RT.choose(long_q, local_model=POOLED, lanes=["jarvis-escalate"],
                   budget=RT.Budget(path=None), owner_said_yes=True)
    check("... including when the saved local model is a pooled one: the "
          "escalation decision is untouched",
          d2.gate == "escalate" and d2.lane == RT.CLOUD_LANE
          and "degraded_from" not in d2.as_dict(), d2.as_dict())


def t_the_spill_refusal_still_refuses_the_pooled_model_on_a_one_card_lane():
    use_lane(ONE_CARD)
    refusal = AG.local_model_refusal(ONE_CARD, POOLED)
    check("the existing refusal STILL refuses a pooled model on the one-card "
          "lane - this change chooses another model, it never allows the spill",
          "pooled three-card model" in refusal and "Nothing was sent" in refusal,
          refusal)
    check("... the same on the named everyday lane",
          "pooled three-card model" in AG.local_model_refusal(NAMED_EVERYDAY, POOLED))
    check("... and the same model IS allowed on the pooled lane itself, so no "
          "fallback is made where it can really run",
          AG.local_model_refusal(POOLED_LANE, POOLED) == ""
          and RT.local_model_fallback(POOLED, POOLED_LANE) == {})


def t_a_pooled_model_on_the_pooled_lane_is_untouched():
    """The #1361 world: the everyday preset may legitimately BE the 26B/30B."""
    use_lane(POOLED_LANE)
    fallback = RT.local_model_fallback(POOLED, POOLED_LANE)
    check("a pooled model at the pooled lane is not 'degraded' at all",
          fallback == {}, fallback)
    d = RT.choose("what is my home address", local_model=POOLED, lanes=[],
                  budget=RT.Budget(path=None))
    check("... the turn keeps the model it was configured with",
          d.lane == POOLED and "degraded_from" not in d.as_dict(), d.as_dict())


def t_the_unfixable_refusals_are_not_papered_over():
    use_lane(ONE_CARD)
    d = RT.choose("what is on my calendar tomorrow",
                  local_model="glm-4.6:cloud", lanes=[],
                  budget=RT.Budget(path=None))
    check("a CLOUD model saved as the everyday model is still refused by gate "
          "cloud_model, with no model substituted",
          d.gate == "cloud_model" and d.lane == "glm-4.6:cloud"
          and "degraded_from" not in d.as_dict(), d.as_dict())
    other = RT.local_model_fallback(POOLED, "http://192.168.1.50:11434")
    check("a lane address on ANOTHER machine gets no local substitute - the "
          "fallback is only for a model that cannot fit THIS PC's lane",
          other == {}, other)


# ==========================================================================
#   3. THE HUD HALF, and the cloud hazard a router-only change would open
# ==========================================================================

def _stacked_hud():
    """(text, log) of jarvis_hud.py after the WHOLE patch stack, as shipped."""
    return _stack.stand_in("jarvis_hud.py")


def _find(text: str, pattern: str, what: str) -> str:
    m = re.search(pattern, text)
    if not m:
        raise AssertionError(f"{what} not found in the stacked jarvis_hud.py")
    return m.group(1)


def t_an_unknown_lane_name_is_not_a_cloud_provider():
    """The hazard this suite was born from - now CLOSED (2026-11-18).

    This is why a fallback MODEL name must never be handed to the HUD's plain
    relay: an unknown name used to resolve to a cloud service, so a fallback
    model's name plus a saved provider key would have made `lane_state()` answer
    with that service's https address. The owner's ruling of 2026-11-18 removed
    that fallback: only a name in `CLOUD_LANES` names a service, so the hazard
    is closed at the relay as well as by the HUD guard below (defence in depth).
    """
    import jarvis_chatbot_api as API
    check("this suite is reading a new enough jarvis_chatbot_api to know the "
          "mapping", hasattr(API, "lane_service") and hasattr(API, "DEFAULT_LANE"))
    pid, model = API.lane_service(EVERYDAY_MODEL)
    check("an UNKNOWN 'lane' name - which is exactly what a fallback model "
          "looks like to it - names NO service (fail closed)",
          (pid, model) == ("", ""), (pid, model))
    state = API.lane_state(EVERYDAY_MODEL)
    check("... so no service, address, key or model reaches a request",
          state.get("pid") == "" and state.get("model") == ""
          and state.get("url") == "" and state.get("key") == "", state)
    check("... and a fallback model's own name is still not a lane",
          EVERYDAY_MODEL not in API.CLOUD_LANES)


def t_the_hud_runs_a_local_fallback_turn_locally():
    text, log = _stacked_hud()
    check("the stacked jarvis_hud.py builds (the walk had text to work with)",
          text is not None, "\n".join(log[-3:]))
    if text is None:
        return
    use_tools = _find(text,
                      r"use_tools = (\(\(lane == local_model or "
                      r"decision\.inject_memory\)\s*\n\s*and _agent_ok\))",
                      "the local-model-guard use_tools expression")
    # `is_cloud` is the owner's own line (no patch writes it, so the walk
    # cannot contain it): the published base is the snapshot of the folder
    # that holds it, which is where the suites read owner-only text from.
    owner_hud = (BASE / "jarvis_hud.py").read_text(encoding="utf-8")
    is_cloud = _find(owner_hud,
                     r"is_cloud = (decision\.lane != local_model and "
                     r"not decision\.inject_memory)",
                     "the is_cloud expression")
    check("the shipped text really carries the guarded use_tools line, not the "
          "old `lane == local_model` one",
          "or decision.inject_memory" in use_tools
          and "lane == local_model and _agent_ok" not in text.replace("\n", " "))

    def run(expr: str, **values) -> bool:
        ns = {"__builtins__": {}}
        ns.update(values)
        return bool(eval(expr, ns))

    local = SimpleNamespace(inject_memory=True, lane=EVERYDAY_MODEL)
    cloud = SimpleNamespace(inject_memory=False, lane=RT.CLOUD_LANE)
    check("THE HEADLINE: a local fallback turn (`lane` is the fallback model, "
          "which is not local_model) is run by the LOCAL answering loop",
          run(use_tools, lane=EVERYDAY_MODEL, local_model=POOLED,
              decision=local, _agent_ok=True) is True)
    check("... the OLD expression would have sent it to the plain relay "
          "(measured, not argued)",
          run("(lane == local_model and _agent_ok)",
              lane=EVERYDAY_MODEL, local_model=POOLED, _agent_ok=True) is False)
    check("... and the header calls it local (is_cloud is False), so no cloud "
          "message filtering or cloud answer handling applies",
          run(is_cloud, lane=EVERYDAY_MODEL, local_model=POOLED,
              decision=local) is False)
    check("an ordinary local turn is unchanged: use_tools true",
          run(use_tools, lane=EVERYDAY_MODEL, local_model=EVERYDAY_MODEL,
              decision=local, _agent_ok=True) is True)
    check("a CLOUD decision still uses the relay: use_tools false and "
          "is_cloud true",
          run(use_tools, lane=RT.CLOUD_LANE, local_model=EVERYDAY_MODEL,
              decision=cloud, _agent_ok=True) is False
          and run(is_cloud, lane=RT.CLOUD_LANE, local_model=EVERYDAY_MODEL,
                  decision=cloud) is True)
    # And what the relay would do with a name it does not know: since
    # 2026-11-18 it names NO service (fail closed), so even a caller that
    # skipped the guard above cannot address a cloud service with a fallback
    # model's name. The relay treats the LOCAL lane as the empty name - the
    # contract `jarvis_chatbot_api.lane_state` documents.
    import jarvis_chatbot_api as API
    check("the plain relay only treats the EMPTY name as local, and an unknown "
          "fallback model name names no service at all (fail closed, 2026-11-18)",
          API.lane_state("").get("pid") == ""
          and API.lane_state(EVERYDAY_MODEL).get("pid") == "",
          (API.lane_state(""), API.lane_state(EVERYDAY_MODEL)))


def t_the_patch_is_well_formed_and_applies_where_it_claims():
    body = PATCH.read_bytes() if PATCH.is_file() else b""
    check("backend/local-model-guard.patch exists", bool(body))
    if not body:
        return
    check("... stored with LF endings only",
          b"\r\n" not in body)
    heads = re.findall(rb"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@", body, re.M)
    targets = re.findall(rb"^\+\+\+ b/(\S+)", body, re.M)
    check("... ONE hunk, aiming at jarvis_hud.py and nothing else",
          len(heads) == 1 and targets == [b"jarvis_hud.py"], (heads, targets))
    text = body.decode("utf-8")
    removed = [l[1:] for l in text.splitlines() if l.startswith("-")
               and not l.startswith("---")]
    added = [l[1:] for l in text.splitlines() if l.startswith("+")
             and not l.startswith("+++")]
    check("... it rewrites exactly ONE line - the old `use_tools` test - and "
          "leaves the `and _agent_ok)` line it continues on alone",
          removed == ["        use_tools = (lane == local_model"], removed)
    check("... and says, in the patch itself, why `inject_memory` is the "
          "signal rather than a new Decision flag",
          any("inject_memory is the signal rather than a new Decision flag" in l
              for l in added), [l for l in added if l.strip().startswith("#")][:3])
    check("... the added code is the guarded expression, with the unchanged "
          "continuation line still beside it",
          "        use_tools = ((lane == local_model or decision.inject_memory)" in added
          and "                      and _agent_ok)" in text.splitlines(), added[-2:])
    order = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("... it is in apply-patches.ps1's list, immediately BEFORE "
          "plugin-loader.patch (which must stay last of all)",
          order[-2] == "local-model-guard.patch" and order[-1] == "plugin-loader.patch",
          order[-3:])
    # It reads ONLY lines earlier patches write (chat-stream's use_tools lines
    # and cloud-honesty's crisis block), so the walk invents nothing for it.
    stats = {}
    walked, wlog = _stack.stand_in("jarvis_hud.py", stats=stats)
    check("the stack walk had to invent no line of the owner's original file "
          "for it", walked is not None
          and "local-model-guard.patch" not in stats.get("by_patch", {}), wlog[-3:])
    check("... and the walk's invented-hunk RATCHET did not move",
          stats.get("materialised") == _stack.RATCHET.get("jarvis_hud.py"),
          (stats.get("materialised"), _stack.RATCHET.get("jarvis_hud.py")))
    # Apply it to its real pre-image (everything before it) and reverse it out.
    idx = order.index("local-model-guard.patch")
    pre, _log = _stack.stand_in("jarvis_hud.py", _stack.order()[:idx])
    if pre is None:
        return check("its pre-image could be built", False)
    work = Path(tempfile.mkdtemp(prefix="jarvis-local-model-guard-patch-"))
    try:
        (work / "jarvis_hud.py").write_text(pre, encoding="utf-8", newline="\n")
        applied = subprocess.run(["git", "apply", str(PATCH)], cwd=work,
                                 capture_output=True, text=True)
        check("... and it applies cleanly to the text the stack leaves it",
              applied.returncode == 0, (applied.stderr or applied.stdout)[-500:])
        if applied.returncode == 0:
            reverted = subprocess.run(["git", "apply", "--reverse", str(PATCH)],
                                      cwd=work, capture_output=True, text=True)
            check("... and reversing it restores the pre-image byte for byte",
                  reverted.returncode == 0
                  and (work / "jarvis_hud.py").read_text(encoding="utf-8") == pre,
                  reverted.stderr[-400:])
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


# ==========================================================================

def main() -> int:
    for fn in (t_a_tainted_turn_whose_saved_model_is_pooled_answers_with_the_lane_model,
               t_the_saved_model_may_carry_ollamas_latest_tag,
               t_the_named_everyday_lane_uses_its_own_table_model,
               t_the_fallback_is_never_a_model_this_lane_cannot_hold,
               t_an_ordinary_local_turn_is_unchanged,
               t_a_cloud_turn_is_not_pulled_local,
               t_the_spill_refusal_still_refuses_the_pooled_model_on_a_one_card_lane,
               t_a_pooled_model_on_the_pooled_lane_is_untouched,
               t_the_unfixable_refusals_are_not_papered_over,
               t_an_unknown_lane_name_is_not_a_cloud_provider,
               t_the_hud_runs_a_local_fallback_turn_locally,
               t_the_patch_is_well_formed_and_applies_where_it_claims):
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILED.append(fn.__name__ + " raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED: " + "; ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
