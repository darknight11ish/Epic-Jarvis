"""The router's private-topic backstop, against the config that names the topics.

`[privacy] never_leaves_device` in jarvis-framework.toml lists what must never
reach a cloud model - email, inbox, calendar, bank, invoice, tax, financial,
medical, files - and said it was "kept in sync with the _PRIVATE regex in
jarvis_router.py by hand". It was not: nine of those words were missing from
the router, and no code read the config list at all. So "summarise my inbox"
matched nothing, and adding a word to the config did nothing.

This reads the REAL config file (not a copy of its words typed in here) and
puts every entry, written the way a person types it, through the real
router. It also checks the built-in list covers the same topics on its own,
for a backend whose config is missing or unreadable.

No cloud lane is configured on this project yet, so today this is latent. It
is the one gate between a typed private question and a cloud model the day
one is.

    python3 test_router_private_terms.py
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO  # noqa: E402,F401

REBUILT = HERE / "rebuilt"
# The owner's own config if the suite is run against a real install, else
# the one in this repository.
CONFIG = next((p for p in (BACKEND / "jarvis-framework.toml",
                           BACKEND.parent / "jarvis-framework.toml",
                           REBUILT / "jarvis-framework.toml") if p.is_file()), None)
if CONFIG is not None:
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(CONFIG)
os.environ.setdefault("OPENJARVIS_CONFIG_DIR", tempfile.mkdtemp(prefix="jarvis-router-"))
sys.path.insert(0, str(REBUILT))

import jarvis_framework as FW  # noqa: E402
import jarvis_router as RT  # noqa: E402

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

FAILED, PASSED = [], []
LANES = ["jarvis-escalate", "jarvis-bulk"]
# Long and clause-heavy, so the complexity gate alone would escalate it - the
# private gate is the only thing that can keep these local.
PAD = (", explain in detail and compare the trade-offs step by step, "
       "why it works and how it fails") * 2


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _config_list():
    if CONFIG is None or tomllib is None:
        return None
    with open(CONFIG, "rb") as f:
        return (tomllib.load(f).get("privacy") or {}).get("never_leaves_device")


def t_every_config_topic_keeps_a_turn_local():
    terms = _config_list()
    if terms is None:
        return check("SKIP - no jarvis-framework.toml (or no tomllib) to read", True)
    check("the config has the list", isinstance(terms, list) and len(terms) > 5, repr(terms))
    # CONTROL: without a private word, this question does escalate - so the
    # private gate is what keeps each one below local, not something else.
    control = RT.choose("tell me about rivers" + PAD, local_model="local", lanes=LANES,
                        budget=RT.Budget(path=None))
    check("CONTROL: the same question with no private word goes to a cloud lane",
          control.lane in LANES, repr(control))
    for term in terms:
        typed = term.replace("_", " ")
        d = RT.choose(f"tell me about my {typed}" + PAD, local_model="local", lanes=LANES,
                      budget=RT.Budget(path=None))
        check(f"'{typed}' (from the config) keeps the turn local", d.lane == "local"
              and d.gate == "private", repr(d))


def t_the_built_in_list_covers_the_topics_on_its_own():
    real = RT._config_terms
    RT._config_terms = lambda: ()
    try:
        for q in ("summarise my inbox", "any new email from Sam?", "what's on my calendar",
                  "check my bank balance", "the invoice from March", "my tax bill",
                  "my financial plan", "my medical results", "read the files in Documents"):
            check(f"with no config at all, {q!r} is still private", RT.is_private(q))
    finally:
        RT._config_terms = real
        RT._PRIVATE._terms = None


def t_the_note_stores_without_their_app_names():
    """K6: the owner's vault, wiki, notes and journal, asked about in plain
    words, matched nothing - only "obsidian" and "joplin" did."""
    real = RT._config_terms
    RT._config_terms = lambda: ()
    try:
        for q in ("search my vault for the lease", "what does my wiki say",
                  "what did I write in my notes", "add this to my logseq journal",
                  "what is in my journal from monday", "open my Obsidian vault",
                  "check our wiki", "read my meeting notes", "my note about the boiler",
                  "what's in logseq about Sam", "My Journal, yesterday"):
            check(f"{q!r} is private", RT.is_private(q))
            d = RT.choose(q + PAD, local_model="local", lanes=LANES, budget=RT.Budget(path=None))
            check(f"... and a long {q!r} stays on the local model", d.lane == "local" and d.gate == "private",
                  repr(d))
        for q in ("show me the release notes for python 3.12",
                  "patch notes for the new game update",
                  "what notes are in a C major chord", "take notes on this lecture",
                  "summarise this Wall Street Journal article",
                  "who publishes the journal Nature",
                  "how high is the pole vault world record", "the vaulted ceiling",
                  "what does wikipedia say about rivers", "search the arch wiki for systemd",
                  "a note on style: prefer short words", "notes from the talk"):
            check(f"CONTROL: {q!r} is not private", not RT.is_private(q),
                  repr(RT._PRIVATE.search(q)))
    finally:
        RT._config_terms = real
        RT._PRIVATE._terms = None


def t_a_word_added_to_the_config_takes_effect():
    d = tempfile.mkdtemp(prefix="jarvis-router-cfg-")
    p = Path(d) / "jarvis-framework.toml"
    p.write_text('[privacy]\nnever_leaves_device = ["project_zebra"]\n', encoding="utf-8")
    old = os.environ.get("JARVIS_FRAMEWORK_TOML")
    check("CONTROL: before, 'project zebra' is not private", not RT.is_private("the project zebra plan"))
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(p)
    try:
        check("after adding it to the config, it is - no code change, no restart",
              RT.is_private("the project zebra plan") and RT.is_private("project-zebra")
              and RT.is_private("PROJECT_ZEBRA"))
    finally:
        if old is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = old


def t_the_hud_call_shape_still_works():
    """jarvis_hud calls `jarvis_router._PRIVATE.search(joined)` directly."""
    check("_PRIVATE.search returns a match object for a private word",
          RT._PRIVATE.search("my password is") is not None)
    check("and None for an ordinary one", RT._PRIVATE.search("how do rivers work") is None)


if __name__ == "__main__":
    for fn in (t_every_config_topic_keeps_a_turn_local,
               t_the_built_in_list_covers_the_topics_on_its_own,
               t_the_note_stores_without_their_app_names,
               t_a_word_added_to_the_config_takes_effect,
               t_the_hud_call_shape_still_works):
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
