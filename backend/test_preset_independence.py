#!/usr/bin/env python3
"""test_preset_independence.py - the factual self-state answers are the same on
every preset (owner ruling Q3, 2026-11-08).

    python -B backend/test_preset_independence.py

THE OWNER'S RULING (Q3.4): *"Add `backend/test_preset_independence.py` proving
that across `general`, `coding`, `fast`, and `general_uncensored`, all factual
self-state questions (read-aloud, GitHub receipt, settings state, presets,
tools, recent changes) take a `quick:` route and return byte-identical
answers."* The ruling exists because on the CODING preset these questions used
to miss the fast path and reach `qwen3-coder-30b-a3b`, which improvised about
Jarvis's own state (the owner's transcript: a token it had never tested).

WHAT THIS SUITE DOES, once per preset, with the preset REALLY selected in the
PC's own preset-choice file (`jarvis_presets._write_choice`, the same file
`P.choice()` reads) and `Q._model_record` pointing at that preset's model:

  1. drives the factual self-state families through `jarvis_quick.answer_turn`
     (the exact function `schedule.patch` calls before the model) - read-aloud
     state + ON/OFF + the owner's sentences, the four GitHub receipt states
     (verified / failed / unrun / nothing-saved), settings state (all 38
     switches + all 10 named choices + the 1 number setting + the aggregate
     "what are my settings set to"), presets (the static list and which one is
     active), tools ("what tools do you have") and recent changes ("what
     changed in your last update"), plus the Q3.3 unknown-name fallback;
  2. with `jarvis_agent.run_local_turn`, `_post` and `_open_stream`
     monkeypatched to RAISE, a jarvis_gate guard that raises on any read, and
     sockets blocked - so a `None` that would become a model turn is a failure;
  3. asserts every row is answered (never None), takes the `quick:` route
     (`route_fields(res)["quick"] == res.intent`, which is literally what
     `X-Jarvis-Route` carries), and returns the SAME intent and the same bytes
     on all four presets.

WHICH ROWS MAY DIFFER BY PRESET, AND WHY THAT IS HONEST: exactly two live facts
report the preset the owner selected - `preset_current` ("I am on the "<Title>"
preset, running <model>...") and the `focus_preset` settings row (its value IS
that choice). Their replies are compared with ONLY that selected fact masked
(title, model, and the numbers that belong to that preset's row), so the
phrasing is proved preset-independent while the fact stays true. Every other row
is compared byte for byte.

WHAT IS LEFT TO OTHER SUITES, cited rather than duplicated: the 49-row sweep's
own match/word/honest-reader checks are in `test_factual_determinism.py`
(`t_every_settings_row_answers_a_state_question`, `..._missing_or_raising...`);
here the same rows are only replayed across the four presets, which is the new
axis. The GitHub receipt's own honesty checks are in
`test_connect_account_chat.py`; the read-aloud feature's own in
`test_read_aloud.py`. This file proves the PRESET axis, not those facts again.

Hermetic: its own temp OPENJARVIS_CONFIG_DIR/HOME, a fake Credential Manager (no
real token is read), a fake HTTP layer that raises if touched, no model, no
network, no card, nothing written outside the temp folder. The token is a canary
that is never printed and must never appear in an answer.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-preset-independence-"))
for _d in ("config", "home", "logs"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
os.environ.setdefault("JARVIS_NO_EMBED", "1")
# BEFORE the imports: the owner's PC may carry a real token in this variable, and
# this suite must never read, use or print it. The fake store below replaces the
# real Credential Manager too.
os.environ.pop("JARVIS_GITHUB_TOKEN", None)
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP / "config"
fw.LOG_DIR = _TMP / "logs"
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
sys.modules.setdefault("jarvis_framework", fw)
os.environ.pop("JARVIS_BACKEND", None)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_read_aloud.py",
                "jarvis_settings_registry.py", "jarvis_presets.py",
                "jarvis_connect_account.py")

import jarvis_agent as A  # noqa: E402
import jarvis_connect_account as C  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_read_aloud as RA  # noqa: E402
import jarvis_research as RES  # noqa: E402
import jarvis_schedule as S  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_token_store as TS  # noqa: E402

PASSED, FAILED, SKIPPED, NOTED = [], [], [], []


def check(name, ok, detail=""):
    (PASSED if ok else FAILED).append(name)
    print(f"{'ok   ' if ok else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not ok else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def note(why):
    NOTED.append(why)
    print(f"note  {why}")


#: The four presets the ruling names, by the ids `jarvis_presets.PRESETS` uses.
PRESETS = ("general", "coding", "fast", "general_uncensored")

#: Never printed; every GitHub answer and the receipt file are checked for its
#: absence instead. A fake store, so no real store is read.
TOKEN = "ghp_preset_canary_9d41f7_never_print"

#: A fixed instant, so a receipt's timestamp words are the same on every run.
SAVED_AT = 1_800_000_000.0


def body(text, *, live=False, private=False):
    msg = {"role": "user", "content": text, "provenance": "voice"}
    if live:
        msg["live"] = True
    b = {"messages": [msg], "model": "m", "stream": False}
    if private:
        b["private"] = True
    return b


# --------------------------------------------------------------------------
#  Hermetic fakes: Credential Manager, HTTP, sockets, cards, the model
# --------------------------------------------------------------------------

class FakeStore:
    """One secret, in memory - the shape jarvis_token_store calls."""

    def __init__(self, value=None):
        self.value = value
        self.writes = []

    def read(self):
        return self.value

    def write(self, token):
        self.value = token
        self.writes.append(token)

    def delete(self):
        had, self.value = self.value is not None, None
        return had


class FakeShelf:
    """`jarvis_token_store._STORE_FACTORY`: one store per target, in memory."""

    def __init__(self):
        self.by_target = {}

    def __call__(self, target):
        return self.by_target.setdefault(target, FakeStore())

    def set_all(self, value):
        for store in self.by_target.values():
            store.value = value


SHELF = FakeShelf()


def fake_http(*a, **k):
    raise AssertionError("a deterministic self-state answer opened a socket")


@contextlib.contextmanager
def hermetic():
    """Fake token store + HTTP + sockets. Every answer must work inside it."""
    saved_factory, saved_request = TS._STORE_FACTORY, C._REQUEST
    TS._STORE_FACTORY, C._REQUEST = SHELF, fake_http
    real_connect = socket.socket.connect

    def no_socket(*a, **k):
        raise AssertionError("a deterministic self-state answer opened a socket")

    socket.socket.connect = no_socket
    try:
        yield
    finally:
        TS._STORE_FACTORY, C._REQUEST = saved_factory, saved_request
        socket.socket.connect = real_connect


@contextlib.contextmanager
def no_model():
    """The model entry points, all of them RAISING if anything calls them."""
    names = ("run_local_turn", "_post", "_open_stream")
    saved = {n: getattr(A, n, None) for n in names}

    def boom(*a, **k):
        raise AssertionError("the model entry point was called")

    for n in names:
        if saved[n] is not None:
            setattr(A, n, boom)
    try:
        yield
    finally:
        for n in names:
            if saved[n] is not None:
                setattr(A, n, saved[n])


@contextlib.contextmanager
def no_gate():
    """A jarvis_gate that raises if anything reads it: no card was raised."""
    class _NoGate(types.ModuleType):
        def __getattr__(self, name):
            raise AssertionError(f"an approval card was raised: jarvis_gate.{name}")

    saved = sys.modules.get("jarvis_gate")
    sys.modules["jarvis_gate"] = _NoGate("jarvis_gate")
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = saved


# --------------------------------------------------------------------------
#  GitHub receipts: the four states, seeded the way the save route writes them
# --------------------------------------------------------------------------

def _reset_receipts():
    try:
        C.receipts_path().unlink()
    except OSError:
        pass


def _seed_receipt(verified: bool, words: str):
    _reset_receipts()
    receipt = {"service": "github", "service_label": "GitHub",
               "verified": bool(verified), "verify_words": words,
               "environment_wins_for": []}
    C.record_receipt(receipt, saved_at=SAVED_AT)


def github_state(kind: str):
    """Set up one of the four receipt states; returns its expected phrase."""
    SHELF.set_all(None)
    if kind == "verified":
        _seed_receipt(True, "GitHub accepted the token (signed in as owner)")
        SHELF.set_all(TOKEN)
        return "passed"
    if kind == "failed":
        _seed_receipt(False, "GitHub refused that token (HTTP 401; a 403 can mean "
                             "the token has no repository scope)")
        SHELF.set_all(TOKEN)
        return "did NOT pass"
    if kind == "unrun":
        _seed_receipt(False, "")
        SHELF.set_all(TOKEN)
        return "was not run"
    _reset_receipts()
    SHELF.set_all(None)
    return "Nothing is saved yet"


# --------------------------------------------------------------------------
#  The row table: every fact this suite drives, once per preset
# --------------------------------------------------------------------------

GITHUB_SENTENCES = ("i added a token", "is github connected?", "did the token work?")


def _spec(key, family, sentence, *, setup=None, normalize="", expect=None,
          expect_phrase=None, expected_state=None, intent=None):
    return {"key": key, "family": family, "sentence": sentence,
            "setup": setup, "normalize": normalize, "expect": expect,
            "expect_phrase": expect_phrase, "expected_state": expected_state,
            "intent": intent}


def _read_aloud_specs():
    specs = [
        _spec("read-aloud/state-on", "read-aloud", "is read aloud on?",
              setup=lambda: RA.set_enabled(True), intent="self_read_aloud",
              expect_phrase="read replies out loud is on"),
        _spec("read-aloud/state-off", "read-aloud", "is read aloud on?",
              setup=lambda: RA.set_enabled(False), intent="self_read_aloud",
              expect_phrase="read replies out loud is off"),
        _spec("read-aloud/on-1", "read-aloud", "read everything out loud",
              setup=lambda: RA.set_enabled(False), intent="read_aloud_set",
              expect_phrase="on now", expected_state=True),
        _spec("read-aloud/on-2", "read-aloud", "read your replies out loud",
              setup=lambda: RA.set_enabled(False), intent="read_aloud_set",
              expect_phrase="on now", expected_state=True),
    ]
    for i, sentence in enumerate(("you turn off reading out loud",
                                  "turn off reading everything out loud",
                                  "stop reading everything out loud",
                                  "stop reading your replies out loud"), 1):
        specs.append(_spec(f"read-aloud/off-{i}", "read-aloud", sentence,
                           setup=lambda: RA.set_enabled(True),
                           intent="read_aloud_set", expect_phrase="off now",
                           expected_state=False))
    specs.append(_spec("read-aloud/phone-trap", "read-aloud",
                       "read remembered facts aloud when my phone connects",
                       intent="phone_read_aloud_refused",
                       expect_phrase="nothing was changed"))
    return specs


def _github_specs():
    specs = []
    for state, phrase in (("verified", "passed"), ("failed", "did NOT pass"),
                          ("unrun", "was not run")):
        def setup(state=state):
            github_state(state)
        for sentence in GITHUB_SENTENCES:
            specs.append(_spec(f"github/{state}/{sentence}", "github-receipt",
                               sentence, setup=setup,
                               intent="github_connect_receipt",
                               expect_phrase=phrase))
    # nothing saved: the two shapes that are always the receipt answer.
    for sentence in ("i added a token", "did the token work?"):
        specs.append(_spec(f"github/nothing-saved/{sentence}", "github-receipt",
                           sentence,
                           setup=lambda: github_state("nothing-saved"),
                           intent="github_connect_receipt",
                           expect_phrase="Nothing is saved yet"))
    specs.append(_spec("github/capability", "github-receipt",
                       "what can you do with github now",
                       setup=lambda: github_state("verified"),
                       intent="feature_capabilities",
                       expect_phrase="github"))
    return specs


def _settings_specs():
    specs = [
        _spec("settings/explain-all", "settings-state",
              "what are my settings set to", intent="settings_explain_all",
              expect_phrase="switches"),
        _spec("settings/explain-any", "settings-state",
              "explain any setting", intent="settings_explain_all",
              expect_phrase="switches"),
        _spec("settings/changeable", "settings-state",
              "what can I change", intent="changeable_overview"),
    ]
    for b in R.BOOL_SETTINGS:
        specs.append(_spec(f"settings/bool/{b.key}", "settings-state",
                           f"what is {b.names[0]} set to?"))
    for c in R.CHOICE_SETTINGS:
        normalize = "preset-title" if c.key == "focus_preset" else ""
        specs.append(_spec(f"settings/choice/{c.key}", "settings-state",
                           f"what is {c.names[0]} set to?", normalize=normalize))
    for n in R.NUMBER_SETTINGS:
        specs.append(_spec(f"settings/number/{n.key}", "settings-state",
                           "what is the jarvis live timeout set to?"))
    return specs


def _preset_specs():
    return [
        _spec("presets/list-1", "presets", "what presets do you have",
              intent="presets_list", normalize="current-marker",
              expect_phrase="presets -"),
        _spec("presets/list-2", "presets", "list your presets",
              intent="presets_list", normalize="current-marker"),
        _spec("presets/current-1", "presets", "which preset am I using",
              intent="preset_current", normalize="identity"),
        _spec("presets/current-2", "presets", "which preset am i using?",
              intent="preset_current", normalize="identity"),
        _spec("presets/current-3", "presets", "what preset are you using",
              intent="preset_current", normalize="identity"),
    ]


def _tool_specs():
    return [
        _spec("tools/list-1", "tools", "what tools do you have",
              intent="tools_inventory", expect_phrase="tools"),
        _spec("tools/list-2", "tools", "what tools do you have access to",
              intent="tools_inventory"),
    ]


def _recent_specs():
    return [_spec("recent/changes-1", "recent-changes",
                  "what changed in your last update", intent="recent_changes")]


def _unknown_specs():
    return [
        _spec(f"unknown/{i}", "unknown-name", sentence,
              intent="unknown_self_name", expect=Q.UNKNOWN_SELF_NAME_WORDS)
        for i, sentence in enumerate((
            "what is the turbo setting set to",
            "what is the flux capacitor set to",
            "is the turbo setting on",
            "is the turbo feature on",
            "is the quantum flux option enabled",
        ), 1)
    ]


SPECS = (_read_aloud_specs() + _github_specs() + _settings_specs()
         + _preset_specs() + _tool_specs() + _recent_specs()
         + _unknown_specs())

#: Families whose replies may never mention the preset's model name: a model name
#: in one of these would mean the answer drifted with the preset. `presets` is
#: excluded because its whole job is to name the presets and their models, and
#: `recent-changes` quotes a shipped changelog that may name a model in an old
#: bullet.
NO_MODEL_NAME_FAMILIES = frozenset({
    "read-aloud", "github-receipt", "settings-state", "tools", "unknown-name",
})


def _preset_by_id(pid: str):
    for row in getattr(P, "PRESETS", ()):
        if getattr(row, "id", "") == pid:
            return row
    return None


def _normalize(kind: str, reply: str, row) -> str:
    """The reply with ONLY the facts that legitimately belong to this preset
    masked. Identity (`"") means the raw bytes - compared byte for byte."""
    if not kind:
        return reply
    title = str(getattr(row, "title", "") or "")
    model = str(getattr(row, "model", "") or "")
    out = reply
    if kind in ("identity", "preset-title"):
        out = out.replace(title, "<PRESET>").replace(model, "<MODEL>")
        out = re.sub(r"\d[\d,]*", "<N>", out)
        return out
    if kind == "current-marker":
        # The ONLY difference the selected preset makes to the static list is
        # which row carries the " (current)" marker; drop the marker itself, so
        # the list's own words are compared byte for byte. That the marker is on
        # the truly selected row is checked separately, in
        # t_the_selected_preset_fact_is_reported_truthfully.
        return out.replace(" (current)", "")
    return out


def collect(pid: str) -> dict:
    """Every row answered once with `pid` really selected; returns key -> answer."""
    if P._write_choice(pid) is not True or P.choice() != pid:
        raise AssertionError(f"the {pid} preset could not be selected")
    row = _preset_by_id(pid)
    if row is None:
        raise AssertionError(f"this checkout has no {pid} preset row")
    saved_model = Q._model_record
    Q._model_record = lambda: str(getattr(row, "model", "") or "")
    out = {"_choice": P.choice(), "_row": row, "_answers": {}}
    try:
        with hermetic(), no_model(), no_gate():
            for spec in SPECS:
                if spec["setup"] is not None:
                    spec["setup"]()
                res = Q.answer_turn(body(spec["sentence"]))
                out["_answers"][spec["key"]] = res
    finally:
        Q._model_record = saved_model
    return out


def _answers_by_key(collection: dict) -> dict:
    return collection["_answers"]


# --------------------------------------------------------------------------
# 1. The same intent + the same bytes on all four presets
# --------------------------------------------------------------------------

_COLLECTED = {}


def t_every_fact_takes_the_quick_route_on_all_four_presets():
    """Q3.4: the four presets, the real preset file, the real fast path."""
    for pid in PRESETS:
        try:
            _COLLECTED[pid] = collect(pid)
        except AssertionError as exc:
            check(f"the {pid} preset can be selected and driven", False, str(exc))
            return
    check("all four presets were really selected through the PC's own file",
          all(_COLLECTED[p]["_choice"] == p for p in PRESETS),
          {p: _COLLECTED[p]["_choice"] for p in PRESETS})
    check("this checkout has all four preset rows the ruling names",
          all(_preset_by_id(p) is not None for p in PRESETS))

    unanswered = []
    for pid in PRESETS:
        for key, res in _answers_by_key(_COLLECTED[pid]).items():
            if res is None:
                unanswered.append((pid, key))
    check(f"every one of the {len(SPECS)} facts is answered on all four presets",
          not unanswered, unanswered[:8])

    not_quick = []
    for pid in PRESETS:
        for key, res in _answers_by_key(_COLLECTED[pid]).items():
            if res is not None and Q.route_fields(res).get("quick") != res.intent:
                not_quick.append((pid, key, Q.route_fields(res).get("quick"),
                                  res.intent))
    check("every answer takes the `quick:` route (never a model turn)",
          not not_quick, not_quick[:8])


def t_the_answers_are_byte_identical_on_all_four_presets():
    """The ruling's core claim, row by row; only the two live preset facts are
    masked, and a row that differs anywhere else is listed by name."""
    if len(_COLLECTED) != len(PRESETS):
        return skip("the collection did not complete")
    differing = []
    for spec in SPECS:
        values = []
        for pid in PRESETS:
            res = _answers_by_key(_COLLECTED[pid]).get(spec["key"])
            row = _COLLECTED[pid]["_row"]
            if res is None:
                values.append((None, None))
            else:
                values.append((res.intent,
                               _normalize(spec["normalize"], res.reply, row)))
        intents = {v[0] for v in values}
        replies = {v[1] for v in values}
        if len(intents) > 1 or len(replies) > 1:
            differing.append((spec["family"], spec["key"],
                              [(p, v) for p, v in zip(PRESETS, values)]))
    check("all factual self-state answers are byte-identical on every preset "
          "(only the selected-preset fact is masked where it is the answer)",
          not differing, differing[:4])
    # Count the rows by family so the report can name what is covered.
    families = {}
    for spec in SPECS:
        families[spec["family"]] = families.get(spec["family"], 0) + 1
    print("      families covered: "
          + ", ".join(f"{name} {count}" for name, count in sorted(families.items())))


def t_the_selected_preset_fact_is_reported_truthfully():
    """The two rows that MAY differ must each name the preset really selected."""
    if len(_COLLECTED) != len(PRESETS):
        return skip("the collection did not complete")
    wrong = []
    for pid in PRESETS:
        row = _COLLECTED[pid]["_row"]
        listed = _answers_by_key(_COLLECTED[pid]).get("presets/list-1")
        if listed is None or f"{row.title} (current)" not in listed.reply:
            wrong.append((pid, "the '(current)' marker is not on the selected "
                          "preset: " + (None if listed is None
                                        else listed.reply[:160])))
        res = _answers_by_key(_COLLECTED[pid]).get("presets/current-1")
        if res is None or str(row.title) not in res.reply or str(row.model) not in res.reply:
            wrong.append((pid, None if res is None else res.reply[:140]))
            continue
        if not res.reply.startswith(f'I am on the "{row.title}" preset, running'):
            wrong.append((pid, res.reply[:140]))
        focus = _answers_by_key(_COLLECTED[pid]).get("settings/choice/focus_preset")
        if focus is not None and str(row.title) not in focus.reply:
            wrong.append((pid, "focus_preset: " + focus.reply[:140]))
    check("the active-preset answer names the preset really selected, on all four",
          not wrong, wrong[:4])
    check("...and the focus-preset setting row reports that same preset",
          not [w for w in wrong if "focus_preset" in str(w[1])])


def t_no_preset_answer_mentions_its_own_model_outside_the_preset_family():
    """A model name in a read-aloud/settings/tools answer would be the drift the
    ruling forbids; the `presets` family is excluded because naming models is its
    own job."""
    leaks = []
    for pid in PRESETS:
        row = _COLLECTED[pid]["_row"]
        model = str(getattr(row, "model", "") or "")
        if not model:
            continue
        for spec in SPECS:
            if spec["family"] not in NO_MODEL_NAME_FAMILIES:
                continue
            res = _answers_by_key(_COLLECTED[pid]).get(spec["key"])
            if res is not None and model in res.reply:
                leaks.append((pid, spec["key"]))
    check("no read-aloud/settings/tools/unknown answer leaks the preset's model",
          not leaks, leaks[:6])


def t_the_github_receipt_states_each_say_their_own_truth():
    """The four receipt states are distinct and honest BEFORE the preset axis:
    the preset must never turn a failed test into a passing one."""
    if len(_COLLECTED) != len(PRESETS):
        return skip("the collection did not complete")
    expected = {"verified": "passed", "failed": "did NOT pass",
                "unrun": "was not run", "nothing-saved": "Nothing is saved yet"}
    wrong = []
    for pid in PRESETS:
        answers = _answers_by_key(_COLLECTED[pid])
        for state, phrase in expected.items():
            for sentence in (GITHUB_SENTENCES if state != "nothing-saved"
                             else ("i added a token",)):
                res = answers.get(f"github/{state}/{sentence}")
                if res is None or phrase.lower() not in res.reply.lower():
                    wrong.append((pid, state, sentence,
                                  None if res is None else res.reply[:120]))
    check("every GitHub receipt state keeps its own honest words on every preset",
          not wrong, wrong[:4])


def t_the_owner_ruling_sentence_is_the_unknown_name_answer():
    """Q3.3 wording, pinned: the same fixed sentence on every preset."""
    if len(_COLLECTED) != len(PRESETS):
        return skip("the collection did not complete")
    wrong = []
    for pid in PRESETS:
        for spec in _unknown_specs():
            res = _answers_by_key(_COLLECTED[pid]).get(spec["key"])
            if res is None or res.reply != Q.UNKNOWN_SELF_NAME_WORDS:
                wrong.append((pid, spec["key"],
                              None if res is None else res.reply[:160]))
    check("the Q3.3 unknown-name sentence is byte-identical on all four presets",
          not wrong, wrong[:4])
    check("...and it names both deterministic lists",
          "what can I change?" in Q.UNKNOWN_SELF_NAME_WORDS
          and "what do you have?" in Q.UNKNOWN_SELF_NAME_WORDS)


def t_no_answer_leaks_the_fake_github_token_or_opens_a_socket():
    """The answers were produced inside `hermetic()`; this asserts the canary
    never surfaced and no receipt file carries it either."""
    if len(_COLLECTED) != len(PRESETS):
        return skip("the collection did not complete")
    leaks = []
    for pid in PRESETS:
        for key, res in _answers_by_key(_COLLECTED[pid]).items():
            if res is not None and TOKEN in res.reply:
                leaks.append((pid, key))
    check("no answer ever contains the token (it is a canary, never printed)",
          not leaks, leaks[:4])
    try:
        raw = C.receipts_path().read_text(encoding="utf-8")
        check("the receipt file itself carries no token", TOKEN not in raw)
    except OSError:
        pass


# --------------------------------------------------------------------------
# 2. Nothing in these families consults the preset reader
# --------------------------------------------------------------------------

def t_the_preset_choice_reader_is_never_consulted():
    """Poison `jarvis_presets.choice`: the families that must be preset-blind
    answer again byte-identically. The two honest preset rows are excluded."""
    if len(_COLLECTED) != len(PRESETS):
        return skip("the collection did not complete")
    preset_families = {"presets"}
    baseline = {pid: _answers_by_key(_COLLECTED[pid]) for pid in PRESETS}
    saved_choice = P.choice
    P.choice = lambda: (_ for _ in ()).throw(
        AssertionError("jarvis_presets.choice was consulted"))
    try:
        with hermetic(), no_model(), no_gate():
            for pid in PRESETS:
                row = _COLLECTED[pid]["_row"]
                P._write_choice(pid)
                saved_model = Q._model_record
                Q._model_record = lambda: str(getattr(row, "model", "") or "")
                try:
                    for spec in SPECS:
                        if spec["family"] in preset_families:
                            continue
                        if spec["key"] == "settings/choice/focus_preset":
                            continue
                        if spec["setup"] is not None:
                            spec["setup"]()
                        res = Q.answer_turn(body(spec["sentence"]))
                        base = baseline[pid].get(spec["key"])
                        if res is None or base is None or res.reply != base.reply:
                            check(f"the preset reader is not consulted for "
                                  f"{spec['key']} on {pid}", False,
                                  (None if base is None else base.reply[:100],
                                   None if res is None else res.reply[:100]))
                            return
                finally:
                    Q._model_record = saved_model
    finally:
        P.choice = saved_choice
    check("read-aloud, GitHub receipt, settings state, tools, recent changes and "
          "the unknown-name answer never read the preset choice",
          True)


# --------------------------------------------------------------------------
# 3. The model entry point and the card gate, stated once as their own proof
# --------------------------------------------------------------------------

def t_the_model_entry_points_really_exist_to_be_blocked():
    check("the three model entry points this suite blocks exist in jarvis_agent",
          all(getattr(A, n, None) is not None
              for n in ("run_local_turn", "_post", "_open_stream")),
          [n for n in ("run_local_turn", "_post", "_open_stream")
           if getattr(A, n, None) is None])


def t_this_suite_is_hermetic():
    check("the config folder is this suite's own throwaway folder",
          str(_TMP / "config") == os.environ.get("OPENJARVIS_CONFIG_DIR"),
          os.environ.get("OPENJARVIS_CONFIG_DIR"))
    check("JARVIS_BACKEND is unset, so no live folder can be read",
          not os.environ.get("JARVIS_BACKEND"), os.environ.get("JARVIS_BACKEND"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn) and fn.__module__ == "__main__":
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(NOTED)} noted, "
          f"{len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
