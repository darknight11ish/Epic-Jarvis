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
SKIPPED = []
LANES = ["jarvis-escalate", "jarvis-bulk"]
# Long and clause-heavy, so the complexity gate alone would escalate it - the
# private gate is the only thing that can keep these local.
PAD = (", explain in detail and compare the trade-offs step by step, "
       "why it works and how it fails") * 2


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _config_list():
    if CONFIG is None or tomllib is None:
        return None
    with open(CONFIG, "rb") as f:
        return (tomllib.load(f).get("privacy") or {}).get("never_leaves_device")


def t_every_config_topic_keeps_a_turn_local():
    terms = _config_list()
    if terms is None:
        return skip("no jarvis-framework.toml (or no tomllib) to read")
    check("the config has the list", isinstance(terms, list) and len(terms) > 5, repr(terms))
    # CONTROL: without a private word, this question does escalate - so the
    # private gate is what keeps each one below local, not something else.
    control = RT.choose("tell me about rivers" + PAD, local_model="local", lanes=LANES,
                        budget=RT.Budget(path=None), owner_said_yes=True)
    check("CONTROL: the same question with no private word goes to a cloud lane",
          control.lane in LANES, repr(control))
    for term in terms:
        typed = term.replace("_", " ")
        d = RT.choose(f"tell me about my {typed}" + PAD, local_model="local", lanes=LANES,
                      budget=RT.Budget(path=None), owner_said_yes=True)
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
            d = RT.choose(q + PAD, local_model="local", lanes=LANES, budget=RT.Budget(path=None), owner_said_yes=True)
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


def t_distress_and_crisis_words_stay_local():
    """Cutting-edge round 4, "Keep distress off the cloud offer" (CLAUDE.md,
    2026-09-27): the router's private-word backstop had `diagnos`,
    `prescription`, `medical` but nothing for mood, mental health or
    self-harm, so a long distress message could reach gate 6's "ask a cloud
    model?" offer - the wrong moment to ask, and health is private under
    rule 1. Checks both halves of the fix: the explicit words the owner
    named, and jarvis_wellbeing.CRISIS_PHRASES_EN reused rather than
    duplicated."""
    for q in ("I've been feeling really depressed lately",
              "my anxiety has been so bad this week",
              "I had a panic attack this morning",
              "my therapist thinks I should try something else",
              "I've been having thoughts of self-harm",
              "I keep thinking about suicide"):
        check(f"{q!r} is private (the explicit mood/mental-health words)", RT.is_private(q))
        d = RT.choose(q + PAD, local_model="local", lanes=LANES,
                     budget=RT.Budget(path=None), owner_said_yes=True)
        check(f"... and a long {q!r} stays on the local model", d.lane == "local"
              and d.gate == "private", repr(d))
    # jarvis_wellbeing.CRISIS_PHRASES_EN, reused: every phrase that module
    # answers crisis()=True for is also private here, so the SAME message
    # that gets the crisis help line never also reaches the cloud offer.
    try:
        import jarvis_wellbeing as WB
        skip = False
    except Exception:
        skip = True
    if skip:
        return skip("jarvis_wellbeing.py is not importable here")
    for q in ("I want to kill myself", "I want to end my life", "I just want to die",
              "there is no reason to live anymore", "everyone would be better off "
              "without me", "she took her own life"):
        check(f"CRISIS_PHRASES_EN case {q!r} is private too", RT.is_private(q))
    # CONTROL: jarvis_wellbeing's own false alarms - an everyday idiom that
    # shares a word with a crisis phrase - must not be swept in by the new
    # CRISIS_PHRASES_EN patterns, which (unlike the router's own bare
    # `\bsuicid\w*\b`/`\bself[- ]harm\w*\b`, added deliberately broad) are
    # the SAME precise phrase-shapes jarvis_wellbeing.crisis() uses.
    for q in ("this bug is killing me", "kill the process", "dead tired after "
              "that run", "sudden death overtime in the game last night"):
        check(f"CONTROL: {q!r} is not private", not RT.is_private(q), repr(RT._PRIVATE.search(q)))
    # NOT a control: "Suicide Squad" (a jarvis_wellbeing false alarm, so the
    # CRISIS_PHRASES_EN reuse above does not catch it) IS swept in by the
    # router's own bare `\bsuicid\w*\b`, added deliberately broad - the
    # owner's own words for this list ("Broad on purpose - a false match
    # only keeps a question local, which is the safe direction to err in").
    check("'have you watched Suicide Squad' is private too (the router's "
          "own broad word, not a crisis phrase)", RT.is_private("have you watched Suicide Squad"))


def t_health_medicine_and_pregnancy_words():
    """Security audit 2026-09-28 #4: common health words matched nothing, so
    the chatbot driver's last check and "Try the cloud model" let them by.
    Each of the audit's own phrases, plus conditions, pregnancy, medicines
    and mental health - and the everyday phrases that share a word with
    them stay NOT private (a false match costs quality, but a list that
    blocks every plant question would make the chatbot driver useless)."""
    for q in ("my cholesterol is 240", "I have diabetes", "my blood pressure is high",
              "I am pregnant", "my HIV test came back", "I take sertraline 50mg",
              "my divorce lawyer called", "My sister Anna is pregnant, what gifts?",
              "is metformin safe with alcohol", "my GP changed my medication",
              "should I take 20 mg of it at night", "how long does IVF take",
              "I was diagnosed with ADHD last year", "my son is autistic",
              "living with bipolar disorder", "my blood sugar keeps dropping",
              "the chemo starts Monday", "my asthma inhaler ran out",
              "what helps with PTSD nightmares", "my mum has dementia",
              "is Ozempic worth it", "I'm on antidepressants", "my psychiatrist said",
              "recovering from an eating disorder", "my migraines are worse"):
        check(f"{q!r} is private", RT.is_private(q), repr(RT._PRIVATE.search(q)))
    d = RT.choose("I have diabetes" + PAD, local_model="local", lanes=LANES,
                  budget=RT.Budget(path=None), owner_said_yes=True)
    check("... and a long diabetes question stays local even after 'Try the cloud model'",
          d.lane == "local" and d.gate == "private", repr(d))
    for q in ("how do bipolar transistors work", "std::vector resize is slow",
              "a blood orange sorbet recipe", "which pressure washer for the patio",
              "my plant has yellow leaves, is it a disease", "hospitality jobs near me",
              "meal prep ideas for the week", "lithium battery life in the cold",
              "I am addicted to this song", "make the pill-shaped button bigger",
              "Which plants cope best with a north-facing window?",
              "add a new row to the table", "my consultant sent the slides",
              "a dose of reality", "hearing aids for my grandad",
              "how much does the period drama cost to stream"):
        check(f"CONTROL: {q!r} is not private", not RT.is_private(q),
              repr(RT._PRIVATE.search(q)))


def t_an_ollama_cloud_model_is_never_local():
    """Ollama runs "-cloud" models through 127.0.0.1 but answers on
    ollama.com. Set as the "local" model, memory used to be injected into
    every turn (the memory-safety red team, 2026-09-24)."""
    for name in ("gpt-oss:120b-cloud", "deepseek-v3.1:671b-cloud",
                 "qwen3-coder:480b-cloud", "kimi-k2:1t-cloud", "glm-4.6:cloud",
                 "GPT-OSS:120B-CLOUD"):
        d = RT.choose("what's on my calendar", name, [])
        check(f"{name}: not local, no memory injected",
              not RT.is_local_lane(name, name) and d.inject_memory is False, d)
    for name in ("llama3.1:8b", "qwen3:8b", "cloudy-llama:8b", "mycloud:latest",
                 "jarvis-local"):
        d = RT.choose("what's on my calendar", name, [])
        check(f"CONTROL {name}: still local, memory still injected",
              RT.is_local_lane(name, name) and d.inject_memory is True, d)


def t_a_turn_carrying_the_screen_stays_local():
    """"Look at this" and "Watch with me" (docs/SCREEN-DESIGN.md section 5,
    2026-09-28): a turn carrying words read off the owner's screen stays on
    this PC like a picture does - even when it is long, complex, not a
    private-topic question, a cloud lane is offered, the budget allows it,
    and the owner said yes for this question. The words on screen can be an
    email or a bank page; the private-topic check reads only the question."""
    q = "what does this say about the plan" + PAD
    base = dict(local_model="jarvis-primary", lanes=list(LANES), owner_said_yes=True,
                budget=RT.Budget(path=None))
    control = RT.choose(q, **base)
    check("CONTROL: the same question without the screen escalates (the owner said yes)",
          control.gate == "escalate" and control.lane == LANES[0], control.as_dict())
    d = RT.choose(q, has_screen=True, **base)
    check("with the screen's words: stays on this PC, gate 'screen'",
          d.gate == "screen" and d.lane == "jarvis-primary", d.as_dict())
    check("... no cloud lane is offered for it either", not d.offer, d.as_dict())
    check("... the reason says why, in plain words",
          "screen" in d.reason and "stays on this machine" in d.reason, d.reason)
    d = RT.choose(q, has_screen=True, has_image=True, **base)
    check("with a picture too: still local", d.lane == "jarvis-primary"
          and d.gate in ("image", "screen"), d.as_dict())
    d = RT.choose(q, local_model="glm-4.6:cloud", lanes=list(LANES), has_screen=True,
                  owner_said_yes=True, budget=RT.Budget(path=None))
    check("an Ollama cloud model as the 'local' lane is still refused first",
          d.gate == "cloud_model" and d.inject_memory is False, d.as_dict())
    seen = []
    real = getattr(FW, "audit_log", None)
    FW.audit_log = lambda event, detail=None, **k: seen.append(event)
    try:
        RT.choose(q, has_screen=True, **base)
    finally:
        if real is not None:
            FW.audit_log = real
    check("has_screen is a real argument, not one **_extra swallows",
          "router.unknown_argument" not in seen, seen)


if __name__ == "__main__":
    for fn in (t_every_config_topic_keeps_a_turn_local,
               t_the_built_in_list_covers_the_topics_on_its_own,
               t_the_note_stores_without_their_app_names,
               t_a_word_added_to_the_config_takes_effect,
               t_the_hud_call_shape_still_works,
               t_distress_and_crisis_words_stay_local,
               t_health_medicine_and_pregnancy_words,
               t_an_ollama_cloud_model_is_never_local,
               t_a_turn_carrying_the_screen_stays_local):
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
