"""The work setups: the five combinations, their plain words, the offer that
reads the owner's own words, the choice file, and work.patch.

    python3 test_work.py

Everything outside the module is replaced: Ollama's /api/tags and /api/ps
answers are Python sets and strings handed straight in, and the choice file is
written to a temporary folder. Nothing is started, no model is switched, and
the owner's own config folder is never touched.

What it proves:
  - the five setups, their models, cards, contexts and measured numbers, and
    that NOTHING in them spills to the processor (that is the rule the whole
    design rests on: a spilled model writes at 8-26 tok/s and nothing warns);
  - every setup's "awkward" facts are stated rather than hidden: ornith:9b's
    8/10, the 4B's wrong trap answer, qwen3.5:9b leaving no room on the 2060,
    and the thinking trap on the two models that have it on by default;
  - the offer: the six sentences that must propose something, and the six that
    must propose NOTHING - a mention, someone already switching models,
    someone already looking at the setups, small talk, a crisis turn, and
    nothing at all;
  - OFFER ONLY: recommend() switches no model, loads none, writes nothing, and
    names exactly one route, /api/models/switch - the existing approval card;
  - the choice file: choosing records a preference and changes no model; an
    unknown id is refused with a plain sentence; an id this module no longer
    knows reads as no choice;
  - readiness: what is downloaded, what is not, and that a missing model is
    named with the ordinary download card rather than downloaded;
  - work.patch applies to what the whole earlier stack wrote, reverses, and
    its two blocks compile; the strings the desktop/phone test reads are the
    words this module really produces;
  - the golden file (tools/gen_work_cases.py) and the base copy.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

# This folder is on sys.path too (every suite here does that), and it now holds
# a symlink of jarvis_work.py. _where has already put BACKEND in front, but
# jarvis_work was imported by tools/gen_work_cases.py before this line on some
# runs - so drop anything already loaded and import it fresh, to be certain the
# module under test is the backend's copy, not this folder's.
for _name in ("jarvis_work", "jarvis_hardware", "jarvis_profiles"):
    sys.modules.pop(_name, None)
import importlib  # noqa: E402
importlib.invalidate_caches()

import jarvis_work as W  # noqa: E402
import _stack  # noqa: E402
import _where  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


#: The owner's PC today, as /api/tags reports it (the benchmark, section 1).
TODAY = {"qwen3:8b", "qwen3.5:9b", "qwen3.5:4b", "qwen3.5:2b", "qwen3.5:0.8b",
         "qwen3:0.6b", "jarvis-primary:latest", "ornith:9b"}
#: A PC that has only ever run the everyday model.
FRESH = {"qwen3:8b", "jarvis-primary:latest"}


class World:
    """A temporary config folder standing in for the owner's, with Ollama's
    two answers replaced. Every write the module could make lands here.

    `tags=TODAY` is the owner's PC; `tags=None` is an Ollama that cannot be
    reached - NOT an empty PC, which is a different thing (the module must
    never report "not downloaded" when it simply could not ask). `current=None`
    is "could not read which model is running".

    Every one of these is set explicitly on the way in: the module's own
    `installed()` caches /api/tags for a few seconds, and without the explicit
    set a run that had just read the real Ollama would answer from that cache
    and quietly test the opposite of what the test says it tests.
    """

    def __init__(self, tags: Optional[set] = TODAY, current: Optional[str] = "qwen3:8b"):
        self.tags = tags
        self.current = current
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-work-test-"))

    def __enter__(self):
        self._saved = (W.installed, W._current_model, W._config_dir)
        W.installed = lambda force=False: self.tags
        W._current_model = lambda: self.current
        W._config_dir = lambda: self.dir
        return self

    def __exit__(self, *exc):
        W.installed, W._current_model, W._config_dir = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)
        return False

    def files(self) -> list:
        return sorted(p.name for p in self.dir.iterdir())

    def set_choice(self, setup_id):
        (self.dir / W.CHOICE_FILE).write_text(
            json.dumps({"setup": setup_id, "at": 1770000000}), encoding="utf-8")


# --------------------------------------------------------------------------
#   The five setups
# --------------------------------------------------------------------------

def t_the_five_setups():
    check("five setups, in the picker's order",
          W.SETUP_IDS == ("everyday", "coding", "admin", "long", "specialist"),
          W.SETUP_IDS)
    check("the four kinds of work the owner named are all covered",
          all(any(needle in s.work for s in W.SETUPS)
              for needle in ("short questions", "coding work", "letters",
                             "long back-and-forth")),
          [s.work for s in W.SETUPS])
    check("every setup has a name, a kind of work, a what, a cost, a worse, a "
          "uses and a why",
          all(s.name and s.work and s.what and s.cost and s.worse and s.uses and s.why
              for s in W.SETUPS))
    check("every one of them uses BOTH cards, one model each",
          all(s.both_cards and len(s.places) == 2 for s in W.SETUPS))
    check("no setup puts two models on the same card",
          all(len({p.card for p in s.places}) == len(s.places) for s in W.SETUPS))
    check("no setup has a pre-tuned name in it (jarvis-chat / jarvis-long / "
          "jarvis-vision are the hardware presets' own, and this module must not "
          "pretend they exist)",
          not any("jarvis-" in m for s in W.SETUPS for m in s.models))
    check("no setup names a model that is not on this PC today",
          all(m in TODAY for s in W.SETUPS for m in s.models),
          [m for s in W.SETUPS for m in s.models if m not in TODAY])


def t_nothing_spills():
    """The rule the whole design rests on: a model that spills writes at
    8-26 tok/s and nothing warns. No setup may contain one."""
    for s in W.SETUPS:
        for p in s.places:
            check(f"{s.id}: {p.model} on the {p.card} at {p.ctx:,} does not spill",
                  p.clean and p.spill_gib == 0.0, p.spill_gib)
            check(f"{s.id}: {p.model} on the {p.card} fits in video memory",
                  p.vram_gib < p.card_gb, f"{p.vram_gib} of {p.card_gb}")
            check(f"{s.id}: {p.model} leaves the card's own room",
                  p.free_gib > 0.5, p.free_gib)


def t_the_measured_numbers():
    """The exact figures the two reports contain, so a typo cannot quietly
    become a wrong claim about the owner's machine."""
    by = {s.id: s for s in W.SETUPS}
    e, c, a, lo, sp = (by["everyday"], by["coding"], by["admin"], by["long"],
                       by["specialist"])
    check("Everyday: qwen3:8b on the FAST card at 16,384, 64.0 tok/s, 5.84 GB",
          e.main.model == "qwen3:8b" and e.main.card == W.CARD_FAST
          and e.main.ctx == 16384 and e.main.speed == 64.0 and e.main.vram_gib == 5.84)
    check("Everyday: qwen3.5:9b beside it at 196,608 on the 12 GB card",
          e.beside.model == "qwen3.5:9b" and e.beside.card == W.CARD_BIG
          and e.beside.ctx == 196608 and e.beside.vram_gib == 9.17)
    check("Coding: qwen3.5:9b on the 12 GB card at 196,608, 44.9 tok/s",
          c.main.model == "qwen3.5:9b" and c.main.card == W.CARD_BIG
          and c.main.ctx == 196608 and c.main.speed == 44.9)
    check("Coding: qwen3.5:4b beside it at 65,536 on the fast card, 77.1 tok/s",
          c.beside.model == "qwen3.5:4b" and c.beside.card == W.CARD_FAST
          and c.beside.ctx == 65536 and c.beside.speed == 77.1)
    check("Admin: the better model on the 12 GB card, qwen3:8b on the fast one",
          a.main.model == "qwen3.5:9b" and a.beside.model == "qwen3:8b"
          and a.beside.ctx == 16384)
    check("Long: qwen3.5:4b at 262,144 (its own limit) at 8.27 GB, 63.1 tok/s",
          lo.main.model == "qwen3.5:4b" and lo.main.ctx == 262144
          and lo.main.vram_gib == 8.27 and lo.main.speed == 63.1)
    check("Specialist: ornith:9b at 196,608 on the 12 GB card, 49.1 tok/s",
          sp.main.model == "ornith:9b" and sp.main.card == W.CARD_BIG
          and sp.main.ctx == 196608 and sp.main.speed == 49.1)
    check("Specialist: qwen3.5:9b beside it gets only 8,192 on the fast card",
          sp.beside.model == "qwen3.5:9b" and sp.beside.ctx == 8192)
    check("the everyday model's real input ceiling is said, not hidden",
          "15,600" in e.cost)


def t_the_awkward_facts_are_on_the_label():
    """Each of these is a thing the owner must be told BEFORE he chooses. The
    test is that it is in the setup's own words, not in a document."""
    by = {s.id: s for s in W.SETUPS}
    check("the coding specialist's 8/10 is in ITS OWN text, twice (cost and worse)",
          "8/10" in by["specialist"].cost and "8/10" in by["specialist"].worse)
    check("... and it says the general models scored 10/10",
          "10/10" in by["specialist"].cost)
    check("... and that it is NOT the default for coding",
          "not the default for coding" in by["specialist"].worse,
          by["specialist"].worse)
    check("the 4B's wrong trap answer is in the Long setup's own words",
          "WRONG" in by["long"].worse and "all but 9" in by["long"].worse)
    check("the admin setup says plainly that document work was not measured",
          "no summarise-a-whole-document test was run today" in by["admin"].worse,
          by["admin"].worse)
    check("the everyday setup says its model gave the weakest explanation",
          "weakest" in by["everyday"].worse)
    check("both thinking-by-default models say the trap in their own setup",
          "EMPTY" in by["coding"].thinking and "nothing" in by["specialist"].thinking)
    check("qwen3:8b's thinking trap is said too, in the everyday setup",
          "nothing at all" in by["everyday"].thinking)
    check("no setup says the owner's uncensored/abliterated models are part of it",
          not any("abliterated" in (s.what + s.cost + s.why).lower()
                  or "uncensored" in (s.what + s.cost + s.why).lower()
                  for s in W.SETUPS))


def t_the_awkward_model_is_named():
    """The design note has to say which model is awkward and why. The module
    carries the same facts in words a screen can show."""
    by = {s.id: s for s in W.SETUPS}
    check("qwen3.5:9b's 9.17 GB - the figure that leaves no room on the 2060 - "
          "is in the setups that use it",
          "9.17" in by["coding"].why or "9.17" in by["coding"].cost
          or "9.17" in by["everyday"].cost)
    check("the everyday setup's why names the 12x conversation the 2060 buys",
          "12x" in by["everyday"].why, by["everyday"].why)
    check("the long setup explains why 262,144 needs the SMALLER model "
          "(the 9B spills at that size)",
          "spills 2.91 GB" in by["long"].why, by["long"].why)
    check("the specialist says it is the only one built for the job, and that "
          "the comparison favoured the general models",
          "only model installed" in by["specialist"].why
          and "8/10" in by["specialist"].why, by["specialist"].why)
    check("the long setup says qwen3:8b stops at 40,960 because that is the "
          "model's own limit",
          "40,960" in by["long"].why, by["long"].why)


# --------------------------------------------------------------------------
#   The offer
# --------------------------------------------------------------------------

OFFERS = (
    ("I'm going to build an Android app this weekend", "coding"),
    ("I need to fix a bug in the code for my app", "coding"),
    ("help me with my gradle build, it keeps failing", "coding"),
    ("I have to sort out my taxes and some paperwork", "admin"),
    ("I need to fill in a form for the council", "admin"),
    ("I need to read a long document and summarise it", "long"),
    ("help me with multi-step coding, many files at once", "specialist"),
    ("I just want to ask you a few quick questions", "everyday"),
)

NOTHING = (
    ("I read a letter yesterday", "it only mentions the word"),
    ("I want to switch the model to qwen3.5:9b", "already switching models"),
    ("which work setup should I use?", "already looking at the setups"),
    ("how are you today?", "small talk"),
    ("I feel like I can't go on and want to die", "a crisis turn"),
    ("", "nothing at all"),
)


def t_the_offer_matches_the_work():
    for words, want in OFFERS:
        got = W.match(words)
        check(f"offers \"{want}\" for {words!r}",
              got is not None and got["id"] == want,
              got and got["id"])


def t_the_offer_says_nothing_when_it_should():
    for words, why in NOTHING:
        check(f"offers nothing for {words!r} ({why})", W.match(words) is None,
              W.match(words))


def t_the_offer_words_are_plain_and_say_what_it_is_for():
    for s in W.SETUPS:
        w = W.offer_words(s)
        check(f"{s.id}: the offer names the kind of work in plain words",
              s.work.split(",")[0] in w, w)
        check(f"{s.id}: the offer names the setup by its screen name",
              s.name in w, w)
        check(f"{s.id}: the offer says nothing has changed",
              "Nothing has changed" in w, w)
        check(f"{s.id}: the offer says the switch is the owner's to approve",
              "yours to approve" in w, w)
        check(f"{s.id}: the offer is short (three sentences at most)",
              w.count(". ") <= 3, w)
        check(f"{s.id}: the offer never claims the switch happened",
              not re.search(r"\b(I'?ve |I have )?switched\b", w, re.I), w)


def t_a_crisis_turn_never_offers_a_setup():
    for words in ("I can't go on", "I want to die", "I am suicidal",
                  "I have been self-harming", "there is no reason to live"):
        check(f"no offer for {words!r}", W.match(words) is None, W.match(words))
    check("looks_like_crisis is a pure check that cannot raise",
          W.looks_like_crisis("kill myself") is True
          and W.looks_like_crisis(None) is False
          and W.looks_like_crisis(123) is False)
    check("... and an offer still works on an ordinary turn right after a crisis "
          "phrase has been seen (no state is kept)",
          W.match("I'm going to build an android app") is not None)


def t_whole_words_only():
    """A trigger word must match as a WORD. "app" must not fire on
    "apparently", "code" must not fire on "decode"."""
    check("\"apparently\" does not count as \"app\"",
          W.match("I'm going to apparently work on something") is None,
          W.match("I'm going to apparently work on something"))
    check("\"decode\" does not count as \"code\"",
          W.match("I need to decode this message") is None,
          W.match("I need to decode this message"))
    check("\"form\" does not fire on \"former\"",
          W.match("I need to sort out the former thing") is None)
    check("a strong phrase does fire on its own words",
          W.match("I want to work on an android app") is not None)


def t_the_offer_only_ever_names_the_existing_switch_card():
    for s in W.SETUPS:
        st = W.step(s, TODAY, "jarvis-primary:latest")
        check(f"{s.id}: the one step is the model switch, when it is needed",
              st["kind"] == "switch" and st["route"] == W.SWITCH_PATH
              and st["body"] == {"ref": s.main.model}, st)
    check("the route the module names is the one the owner already approves",
          W.SWITCH_PATH == "/api/models/switch")
    check("... and it names NOTHING else that could start or fetch a model",
          set(re.findall(r"/api/[a-z/]+", Path(W.__file__).read_text(encoding="utf-8")))
          <= {"/api/models/switch", "/api/tags", "/api/ps", "/api/version",
              "/api/work", "/api/work/recommend", "/api/work/choose",
              "/api/models/install", "/api/models/switch\","},
          sorted(set(re.findall(r"/api/[a-z/]+",
                                Path(W.__file__).read_text(encoding="utf-8")))))


def t_the_step_when_the_model_is_already_running():
    with World(TODAY, "qwen3.5:9b") as w:
        st = W.step(W.by_id("admin"), TODAY, "qwen3.5:9b")
        check("nothing to do when the setup's model is already the everyday one",
              st["kind"] == "none" and st["done"] is True and st["route"] is None, st)
        check("... and it says so in plain words",
              "already the model Jarvis uses" in st["words"], st["words"])
        w.set_choice("admin")
        s = W.status()
        check("the status agrees", s["chosen"] == "admin" and s["current_model"] == "qwen3.5:9b")


def t_the_step_when_the_model_is_missing():
    st = W.step(W.by_id("specialist"), FRESH, "qwen3:8b")
    check("a model that is not downloaded is named, not downloaded",
          st["kind"] == "missing" and st["route"] is None
          and "ornith:9b" in st["title"], st)
    check("... and points at the ordinary download card",
          "Brain, Models" in st["words"], st["words"])


def t_ollama_unreachable_is_said_not_guessed():
    st = W.step(W.by_id("coding"), None, None)
    check("an unreachable Ollama gives 'could not be read', never a guess",
          st["kind"] == "unknown" and st["route"] is None, st)
    with World(None, None) as w:
        s = W.status()
        check("the status says Ollama was not seen", not s["ollama_seen"], s["ollama_seen"])
        check("... and every setup says so rather than 'not downloaded'",
              all(x["ready"] == "unknown" for x in s["setups"]))
        for x in s["setups"]:
            check(f"{x['id']}: the unknown words do not claim it is missing",
                  "cannot tell whether this setup needs one" in x["ready_words"],
                  x["ready_words"])
        check("nothing was written", w.files() == [], w.files())


# --------------------------------------------------------------------------
#   OFFER ONLY: it never switches anything
# --------------------------------------------------------------------------

def t_recommend_switches_nothing():
    with World() as w:
        out = W.recommend("I'm going to build an Android app")
        check("it offers", out["offered"] is True and out["id"] == "coding", out)
        check("... and says outright that it switched nothing",
              out["switched"] is False)
        check("... and the step it hands over is a REQUEST, not a change",
              out["step"]["kind"] == "switch" and out["step"]["route"] == W.SWITCH_PATH
              and out["step"]["body"] == {"ref": "qwen3.5:9b"}, out["step"])
        check("... and NOTHING was written anywhere: no choice, no file",
              w.files() == [], w.files())
        for words, _want in OFFERS:
            W.recommend(words)
        check("a hundred offers later, still nothing written", w.files() == [], w.files())


def t_the_module_never_switches_a_model_itself():
    """Read the module's own source. It may build the switch request; it may
    never make one, and it may never touch the gate or the network."""
    src = Path(W.__file__).read_text(encoding="utf-8")
    for forbidden in ("urllib.request", "urlopen", "requests.", "socket.",
                      "subprocess", "jarvis_gate", "Popen", "http.client"):
        check(f"jarvis_work.py never uses {forbidden}", forbidden not in src)
    check("... and never calls Ollama's generate/chat/create/pull",
          not re.search(r"/api/(generate|chat|create|pull|delete|unload)", src))
    check("... and its only write is the choice file and its .tmp",
          'tmp = p.with_suffix(p.suffix + ".tmp")' in src
          and src.count("write_text") == 1, src.count("write_text"))
    check("... and it names the switch card, which is the owner's own card",
          'SWITCH_PATH = "/api/models/switch"' in src)


def t_the_offer_survives_anything():
    for bad in (None, 0, [], {}, " ", "\n", "a" * 20000, "\x00", "🙂"):
        out = W.recommend(bad)
        check(f"recommend({type(bad).__name__}) answers instead of raising",
              isinstance(out, dict) and "offered" in out, out)


def t_handle_recommend_shape():
    code, out = W.handle_recommend({"words": "I'm going to build an Android app"})
    check("POST /api/work/recommend answers 200 with the offer",
          code == 200 and out["offered"] is True, out)
    code, out = W.handle_recommend({})
    check("... and 400, with a plain sentence, when no words were sent",
          code == 400 and "words" in out["error"], out)


# --------------------------------------------------------------------------
#   The choice
# --------------------------------------------------------------------------

def t_choosing_records_a_preference_and_changes_no_model():
    with World() as w:
        code, out = W.choose("coding")
        check("choosing answers 200 with the setup's record",
              code == 200 and out["ok"] is True and out["chosen"] == "coding", out)
        check("... and says nothing has changed",
              "Nothing has changed" in out["message"], out["message"])
        check("... and writes ONE file, the choice, and nothing else",
              w.files() == [W.CHOICE_FILE], w.files())
        check("... and the step it returns is a request with a route",
              out["setup"]["step"]["route"] == W.SWITCH_PATH, out["setup"]["step"])
        check("nothing about a model was touched: the file holds an id and a time",
              set(json.loads((w.dir / W.CHOICE_FILE).read_text()).keys())
              == {"setup", "at"})
        s = W.status()
        check("the status reads the choice back", s["chosen"] == "coding"
              and s["chosen_name"] == "Building an Android app")


def t_choosing_nothing_forgets_it():
    with World() as w:
        W.choose("long")
        code, out = W.choose(None)
        check("choosing nothing answers 200 and forgets the choice",
              code == 200 and out["chosen"] is None, out)
        check("... and says the models are exactly as they are",
              "exactly as" in out["message"], out["message"])
        check("the status then says no setup is used",
              W.status()["chosen"] is None and W.status()["recommended"] is None)


def t_an_unknown_setup_is_refused_in_plain_words():
    with World() as w:
        code, out = W.choose("sports")
        check("an unknown setup is a 400 with a sentence, not a crash",
              code == 400 and "no work setup called" in out["error"], out)
        check("... and names the real ones", "everyday" in out["error"], out)
        check("... and wrote nothing", w.files() == [], w.files())


def t_a_forgotten_setup_reads_as_no_choice():
    with World() as w:
        w.set_choice("something-removed-later")
        s = W.status()
        check("an id this module no longer knows reads as no choice at all",
              s["chosen"] is None and s["recommended"] is None)
        check("... and the choice() reader normalises it the same way",
              W.choice()["setup"] is None)


def t_a_half_written_choice_file_is_not_a_crash():
    with World() as w:
        (w.dir / W.CHOICE_FILE).write_text("{not json", encoding="utf-8")
        check("a choice file that does not parse reads as no choice",
              W.choice()["setup"] is None and W.status()["chosen"] is None)
        (w.dir / W.CHOICE_FILE).write_text('["a list"]', encoding="utf-8")
        check("... and so does one that is not an object",
              W.choice()["setup"] is None)


def t_handle_choose_shape():
    with World() as w:
        code, out = W.handle_choose({"setup": "long"})
        check("POST /api/work/choose answers 200 for a real setup",
              code == 200 and out["chosen"] == "long", out)
        code, out = W.handle_choose({})
        check("... and 400 with the shape it wants when 'setup' is absent",
              code == 400 and "setup" in out["error"], out)


# --------------------------------------------------------------------------
#   Readiness and the status
# --------------------------------------------------------------------------

def t_readiness():
    r = W.readiness(W.by_id("coding"), TODAY)
    check("a setup whose models are all here reads ready",
          r["state"] == "ready" and r["need"] == [] and "downloaded already" in r["words"], r)
    r = W.readiness(W.by_id("specialist"), FRESH)
    check("a setup with nothing here reads missing, and names what is needed",
          r["state"] == "missing" and r["need"] == ["ornith:9b", "qwen3.5:9b"], r)
    r = W.readiness(W.by_id("everyday"), {"qwen3:8b"})
    check("half here reads partial, naming both halves",
          r["state"] == "partial" and r["have"] == ["qwen3:8b"]
          and r["need"] == ["qwen3.5:9b"], r)
    check("... and it says the download is the usual card, not a download here",
          "usual download card" in r["words"], r["words"])
    r = W.readiness(W.by_id("everyday"), None)
    check("an unreachable Ollama is 'unknown', never 'not downloaded'",
          r["state"] == "unknown" and r["have"] == []
          and "cannot tell whether" in r["words"], r)
    r = W.readiness(W.by_id("everyday"))
    check("... and the default (ASK) really asks Ollama rather than assuming",
          isinstance(r, dict) and r["state"] in ("ready", "partial", "missing", "unknown"), r)


def t_status():
    with World() as w:
        s = W.status()
        # The LIVE GET /api/work is answered by the preset contract since
        # presets.patch (2026-10-18, docs/JARVIS-API.md section 145) - this suite
        # still pins jarvis_work.status() ITSELF, which is what its own module
        # answers; /api/work/recommend and /choose are still these routes.
        check("jarvis_work.status() carries the five setups, in order "
              "(the live GET /api/work route is presets.patch's now)",
              [x["id"] for x in s["setups"]] == list(W.SETUP_IDS))
        check("... the sentence that says what this is",
              "5 work setups" in s["found"] and "RTX" not in s["found"], s["found"])
        check("... and the plain how-to", "Say what you are about to work on" in s["how_to"])
        check("... and says outright that it is not a catalogue",
              "no list here of models" in s["not_a_catalogue"], s["not_a_catalogue"])
        check("... and hands the apps the route they may post a step to",
              s["switch_path"] == W.SWITCH_PATH)
        first = s["setups"][0]
        for key in ("id", "name", "work", "what", "cost", "worse", "uses", "why",
                    "summary", "models", "places", "ready", "ready_words",
                    "step", "card_words", "both_cards"):
            check(f"setup {first['id']} carries {key}", key in first)
        check("... and every setup has a step, whether or not it can be taken",
              all(x["step"]["kind"] in ("none", "missing", "switch", "unknown")
                  for x in s["setups"]))
        check("nothing was written by a read", w.files() == [], w.files())


def t_status_never_raises():
    """The route wraps it, but the module promises it too: a broken read must
    answer in words, never take the whole request down."""
    saved = W.installed
    try:
        W.installed = lambda force=False: (_ for _ in ()).throw(RuntimeError("boom"))
        s = W.status()
        check("a read that blows up answers with an error in words",
              bool(s.get("error")) and s["setups"] == [], s)
    finally:
        W.installed = saved


def t_the_names_the_apps_show():
    """The words a screen shows for each setup, word for word - the same
    strings the phone's test reads out of the golden file."""
    check("the five screen names",
          [s.name for s in W.SETUPS] ==
          ["Everyday quick answers", "Building an Android app", "Admin and paperwork",
           "Long conversations and big documents",
           "Careful coding with a coding specialist"], [s.name for s in W.SETUPS])
    check("the awkward one says so in its own name",
          "specialist" in W.by_id("specialist").name.lower())
    check("a setup with no choice reads as Custom in one place only (name_of)",
          W.name_of("everyday") == "Everyday quick answers"
          and W.name_of(None) == "Custom (your own models)"
          and W.name_of("nonsense") == "Custom (your own models)")


def t_the_cards_words():
    for s in W.SETUPS:
        t = W.card_words(s)
        check(f"{s.id}: the card names the setup and the model it switches to",
              s.name in t and s.main.model in t, t[:120])
        check(f"{s.id}: the card says where the model goes and how much room it takes",
              s.main.card in t and f"{s.main.ctx:,}" in t, t[:200])
        check(f"{s.id}: the card says what it costs and what it is worse at",
              "What it costs:" in t and "What it is worse at:" in t)
        check(f"{s.id}: the card says nothing changed yet, and nothing is downloaded",
              "Nothing has changed yet" in t and "does not download anything" in t)
        check(f"{s.id}: the card promises switching back is one more switch",
              "switching back is one more switch" in t)
    check("the card for the specialist carries its 8/10 on the label",
          "8/10" in W.card_words(W.by_id("specialist")))


# --------------------------------------------------------------------------
#   work.patch
# --------------------------------------------------------------------------

def _rehearse():
    """(ok, why, before, after) for jarvis_hud.py: the whole stack before
    work.patch, then work.patch on it with plain `git apply`."""
    order = _stack.order()
    if "work.patch" not in order:
        return False, "work.patch is not in apply-patches.ps1's list", "", ""
    before_list = order[:order.index("work.patch")]
    git = shutil.which("git")
    if not git:
        return False, "git is not installed", "", ""
    before, log = _stack.stand_in("jarvis_hud.py", before_list)
    if before is None:
        return False, "; ".join(log), "", ""
    d = Path(tempfile.mkdtemp(prefix="jarvis-work-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(before, encoding="utf-8", newline="\n")
        (d / "p.patch").write_text((HERE / "work.patch").read_text(encoding="utf-8"),
                                   encoding="utf-8", newline="\n")
        import _gitapply
        env = _gitapply.env_for(git, d)
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True,
                           text=True, env=env)
        if r.returncode != 0:
            return False, r.stderr, before, ""
        after = (d / "jarvis_hud.py").read_text(encoding="utf-8")
        r = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                           text=True, env=env)
        if r.returncode != 0 or (d / "jarvis_hud.py").read_text(encoding="utf-8") != before:
            return False, "does not reverse cleanly: " + r.stderr, before, after
        return True, "", before, after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_the_patch():
    if not shutil.which("git"):
        return skip("git is not installed")
    ok, why, before, hud = _rehearse()
    check("work.patch applies to what the whole earlier stack wrote (no invented "
          "context), and reverses", ok, why)
    if not ok:
        return
    i = hud.index('        if path == "/api/work":')
    blk = hud[i:hud.index('        if path in ("/api/wiki", "/api/wiki/ingest"):', i)]
    check("GET /api/work checks origin and token and answers status()",
          "_origin_ok(self)" in blk and "_token_ok(self)" in blk
          and "jarvis_work.status()" in blk)
    i = hud.index('        if route in ("/api/work/recommend", "/api/work/choose"):')
    blk2 = hud[i:hud.index('        if route == "/api/wiki/ingest":', i)]
    check("the two POSTs check origin and token and hand the body over",
          "_origin_ok(self)" in blk2 and "_token_ok(self)" in blk2
          and "jarvis_work.handle_recommend(body)" in blk2
          and "jarvis_work.handle_choose(body)" in blk2)
    check("... and a body that will not parse is a 400, as for the other routes",
          "JSONDecodeError" in blk2 and "400" in blk2)
    check("NOTHING in the patched block raises or posts to a model route by itself",
          "/api/work" in blk and "/api/work" in blk2
          and not re.search(r"jarvis_(models|hardware)\.(request|switch|install|"
                            r"handle_(switch|install|post))", blk + blk2)
          and "urlopen" not in blk + blk2
          and "SWITCH_PATH" not in blk + blk2)
    for name, b in (("GET", blk), ("POST", blk2)):
        try:
            compile("def f(self, path, route):\n" + b, "<patched block>", "exec")
            check(f"the patched {name} block compiles", True)
        except SyntaxError as exc:
            check(f"the patched {name} block compiles", False, str(exc))
    check("hardware.patch's own blocks are untouched",
          before.count("jarvis_hardware.status()") == hud.count("jarvis_hardware.status()")
          and before.count('        if path == "/api/hardware":')
          == hud.count('        if path == "/api/hardware":'))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [l.strip().strip("'") for l in ps1[start:ps1.index("\n)", start)].splitlines()
             if l.strip().startswith("'")]
    check("apply-patches.ps1 applies work.patch, after hardware.patch",
          "work.patch" in names and names.index("hardware.patch") < names.index("work.patch"))
    check("... and after second-card-suggest.patch, whose POST block it appends to",
          names.index("second-card-suggest.patch") < names.index("work.patch"))
    check("... and before plugin-loader.patch, which must stay last",
          names.index("work.patch") < names.index("plugin-loader.patch"))
    shipped = ps1[ps1.index("$SHIPPED = @("):]
    import _where
    check("the new module is copied in, in _where.SHIPPED too",
          "'jarvis_work.py'" in shipped and "jarvis_work.py" in _where.SHIPPED)
    check("_where and the script list it in the same order",
          [n for n in _where.SHIPPED].index("jarvis_work.py")
          == [n for n in _where.SHIPPED].index("jarvis_hardware.py") + 1)


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return skip("no jarvis_hud.py here; the rehearsal above is the proof")
    s = (BACKEND / "jarvis_hud.py").read_text(encoding="utf-8")
    check("the backend's jarvis_hud.py has /api/work (work.patch applied)",
          '"/api/work"' in s and '"/api/work/recommend"' in s)


# --------------------------------------------------------------------------
#   The golden file, the claims and the base copy
# --------------------------------------------------------------------------

def t_the_golden_file():
    import gen_work_cases as G
    # The tool patches the module it imports, so make sure it is the BACKEND
    # copy and not a stale one from this folder (see the note at the top).
    assert G.W is W, f"gen_work_cases imported {G.W.__file__}, not {W.__file__}"
    rc = G.main(["--check"])
    check("contract/work-setups-cases.json equals a fresh run of the real code",
          rc == 0, "run python3 tools/gen_work_cases.py")
    if rc != 0:
        return
    got = json.loads(G.OUT.read_text(encoding="utf-8"))
    cases = got["cases"]
    check("the golden file carries the five ids and the switch route",
          got["setup_ids"] == list(W.SETUP_IDS) and got["switch_path"] == W.SWITCH_PATH)
    check("... and says outright that it is not a catalogue",
          "already on this PC" in got["not_a_catalogue"]
          and "no list here" not in got["not_a_catalogue"])
    check("every words case in it pairs words with an answer",
          all(("words" in c and "answer" in c) for name, c in cases.items()
              if name.startswith(("words_", "none_"))))
    check("the offer cases that must be silent really are",
          all(cases[name]["answer"]["offered"] is False
              for name in cases if name.startswith("none_")))
    check("... and there are at least five of those",
          sum(1 for name in cases if name.startswith("none_")) >= 5)
    check("the offer cases that must offer something really do",
          all(cases[name]["answer"]["offered"] is True
              for name in cases if name.startswith("words_")))
    check("EVERY offer in the golden file says it switched nothing",
          all(c["answer"].get("switched") is False for c in cases.values()
              if isinstance(c.get("answer"), dict) and c["answer"].get("offered")))
    check("no case in the golden file carries a token-shaped string",
          not re.search(r"X-Jarvis-Token|bearer ", json.dumps(got), re.I))


def t_the_measured_claims():
    tool = REPO / "tools" / "check_work_claims.py"
    check("the claims checker is in the repository", tool.is_file(), str(tool))
    if not tool.is_file():
        return
    done = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    if done.returncode == 2:
        return skip("the two measurement reports are not in this checkout "
                    "(.dsh-scratch/ is not in git) - the claim check needs them")
    check("every measured claim in jarvis_work.py traces back to a report",
          done.returncode == 0, (done.stdout or "") + (done.stderr or ""))


def t_the_base_copy():
    ours = HERE / "jarvis_work.py"
    theirs = REPO / "jarvis-backend" / "jarvis_work.py"
    check("jarvis-backend/ has this module (the base is shipped too)", theirs.is_file())
    if theirs.is_file():
        same = (ours.read_bytes().replace(b"\r\n", b"\n")
                == theirs.read_bytes().replace(b"\r\n", b"\n"))
        check("... and its copy is this repository's copy, byte for byte", same,
              "copy backend/jarvis_work.py over jarvis-backend/ after a change")


# --------------------------------------------------------------------------
#   The phone's half reads the same words
# --------------------------------------------------------------------------

def t_the_phone_reads_the_same_words():
    """The phone builds its screen from THIS module's answers. If a word here
    changes, that test fails - which is the point: the two halves cannot drift
    apart silently."""
    client = REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"
    kt = client / "net" / "WorkSetups.kt"
    plate = client / "ui" / "screens" / "HardwarePlate.kt"
    phone_test = (REPO / "jarvis-client" / "app" / "src" / "test" / "java" / "com" / "jarvis"
                  / "client" / "WorkSetupsContractTest.kt")
    check("the phone has a WorkSetups module", kt.is_file(), str(kt))
    if not kt.is_file():
        return
    src = kt.read_text(encoding="utf-8")
    # F11 (2026-10-22): the phone no longer builds the dead recommend route;
    # the PC keeps it, and `POST /api/work/choose` stays handled/unified.
    check("... with the routes the phone still uses",
          all(r in src for r in ("/api/work", "/api/work/choose"))
          and "RECOMMEND_PATH" not in src)
    check("... with the model-switch route named as the only step route",
          'SWITCH_PATH = "/api/models/switch"' in src)
    check("... and the five ids the PC sends", all(f'"{i}"' in src for i in W.SETUP_IDS))
    check("... and no other route a step could be posted to",
          all(r not in src for r in ("/api/models/install", "/api/models/unload")))
    check("the phone's screen draws the setups", plate.is_file()
          and "WorkSetupsSection" in plate.read_text(encoding="utf-8"))
    check("... and the phone's own test reads the golden file", phone_test.is_file(),
          str(phone_test))
    if phone_test.is_file():
        t = phone_test.read_text(encoding="utf-8")
        # F11 removed the phone offer surface, and with it that Kotlin test;
        # the rule that remains is the other half - the explanation is on
        # screen before a choice is applied.
        check("... including the rule that the explanation is on screen first",
              "the explanation is on screen before the choice is applied" in t)
    golden = (REPO / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
              / "work-setups-cases.json")
    check("the golden file the phone reads is the one the tool writes", golden.is_file())
    if golden.is_file():
        got = json.loads(golden.read_text(encoding="utf-8"))
        check("... and it holds every setup's own words, not a summary",
              all(got["cases"]["today"]["setups"][i]["what"]
                  and got["cases"]["today"]["setups"][i]["worse"]
                  for i in range(len(W.SETUP_IDS))))


def t_the_offer_surface_is_gone():
    """F11 (2026-10-22): the dead phone-side work offer was REMOVED.

    `/api/work/recommend` was built only by `JarvisRuntime.offerWorkSetup`, and
    nothing under the phone's `main` called it - so the offer panel could never
    be populated. The owner's ruling was to remove that dead surface from the
    phone and keep `POST /api/work/choose` handled and unified (the PC route
    and the docs/parity side are Session A's). This check holds the removal, so
    the surface cannot creep back without this file being updated on purpose.
    """
    client = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com"
              / "jarvis" / "client")
    runtime = client / "JarvisRuntime.kt"
    if not runtime.is_file():
        check("the phone's runtime is in this checkout", False, str(runtime))
        return
    src = runtime.read_text(encoding="utf-8")
    check("the runtime has no work-offer function or state left",
          "offerWorkSetup" not in src and "workOffer" not in src)
    posts = []
    for kt in client.rglob("*.kt"):
        body = kt.read_text(encoding="utf-8", errors="replace")
        if "RECOMMEND_PATH" in body:
            posts.append(kt.name)
    check("nothing under the phone's main builds the dead recommend route",
          posts == [], f"still built by {sorted(posts)}")
    work = client / "net" / "WorkSetups.kt"
    kt = work.read_text(encoding="utf-8")
    check("... and POST /api/work/choose is still the one work-setup write",
          'CHOOSE_PATH = "/api/work/choose"' in kt)
    api = (client / "net" / "JarvisApi.kt").read_text(encoding="utf-8")
    check("... and the API layer serves exactly that route",
          "path != WorkSetups.CHOOSE_PATH" in api)


def t_the_phone_switches_a_model_only_from_a_chosen_setups_step():
    """Read the phone's own runtime. A model switch is reached from the CHOSEN
    setup's step and nowhere else - the Kotlin test proves what the PC's answer
    says, and this proves the client does not act on anything else."""
    kt = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
          / "client" / "JarvisRuntime.kt")
    if not kt.is_file():
        return skip("the phone's runtime is not in this checkout")
    src = kt.read_text(encoding="utf-8")

    def body(name: str) -> str:
        """The whole of `... fun name(...)`, up to the next member at the same
        indent. Read from the declaration backwards, so `suspend` may sit on the
        line above the name (which is how the longer signatures are wrapped)."""
        at = src.index(f"fun {name}(")
        line = src.rfind("\n", 0, at) + 1
        if not src[line:at].strip():
            line = src.rfind("\n", 0, line - 1) + 1
        end = src.find("\n    suspend fun ", at + 1)
        stop = src.find("\n    // ", at + 1)
        rest = [i for i in (end, stop) if i != -1]
        return src[line:min(rest)] if rest else src[line:]

    step = body("workSetupStep")
    check("the step is posted through the EXISTING hardware switch route",
          "api.hardwarePost(ask.route, ask.body)" in step)
    check("... and only after stepRequest allowed it", "stepRequest(status, setup)" in step)
    choice = body("chooseWorkSetup")
    check("choosing posts only the choose route",
          "WorkSetups.CHOOSE_PATH" in choice and "SWITCH_PATH" not in choice
          and "hardwarePost" not in choice)
    check("the offer route is not reachable from either",
          "RECOMMEND_PATH" not in step and "RECOMMEND_PATH" not in choice)


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover - a crash is a failure
                import traceback
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed in test_work: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
