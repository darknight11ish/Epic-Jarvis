#!/usr/bin/env python3
"""Writes the work setups' golden file, and checks it.

    python3 tools/gen_work_cases.py            # write it
    python3 tools/gen_work_cases.py --check    # compare only

ONE output, made by the real code - nothing is written by hand:

  jarvis-client/app/src/test/resources/contract/work-setups-cases.json - what
  `GET /api/work` and its POSTs really answer (backend/jarvis_work.py), in
  named situations, plus the twelve sentences that must offer a setup and the
  six that must offer nothing. The phone builds against it
  (`WorkSetupsContractTest.kt`). This is the folder the other 50 contract files
  already live in, so nothing new is invented here.

WHY NOTHING IS WRITTEN INTO `jarvis-desktop/`. That folder is another
conversation's surface while this feature is built (the work-setups task,
2026-10-10), so this tool does not edit it. When the desktop's own half is
built, this file is the shape it builds against too; the desktop's copy can be
produced from `build()` with no change here.

WHAT IS REAL AND WHAT IS MADE UP. The setups, their models, contexts, video
memory and speeds are the module's own, measured on the owner's PC on
2026-10-10 (`.dsh-scratch/android-verify/MODEL-STRATEGY-2026-10-10.md`).
Ollama's answers about which models are downloaded ARE made up - three
situations a person can recognise - because this tool must not touch a running
Ollama, and none was captured.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_work as W  # noqa: E402

OUT = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
       / "work-setups-cases.json")

#: The owner's PC today, as /api/tags reports it (the benchmark of 2026-10-10,
#: section 1): every model the five setups name is already here.
TODAY = {"qwen3:8b", "qwen3.5:9b", "qwen3.5:4b", "qwen3.5:2b", "qwen3.5:0.8b",
         "qwen3:0.6b", "jarvis-primary:latest", "ornith:9b"}
#: A fresh PC that has only ever run the everyday model.
FRESH = {"qwen3:8b", "jarvis-primary:latest"}

#: (name, the owner's words) - every one of these is a sentence a person would
#: really say, and the answer is what Jarvis would offer. The "none_*" cases are
#: the ones that must offer NOTHING, which is the half that matters.
WORD_CASES = (
    ("words_android_app", "I'm going to build an Android app this weekend"),
    ("words_coding_bug", "I need to fix a bug in the code for my app"),
    ("words_coding_gradle", "help me with my gradle build, it keeps failing"),
    ("words_admin_taxes", "I have to sort out my taxes and some paperwork"),
    ("words_admin_letter", "I need to fill in a form for the council"),
    ("words_admin_inbox", "I'm going to work on my inbox, it's a mess"),
    ("words_long_document", "I need to read a long document and summarise it"),
    ("words_long_book", "I'm going to work on the whole book tonight"),
    ("words_specialist", "help me with multi-step coding, many files at once"),
    ("words_everyday", "I just want to ask you a few quick questions"),
    # --- the ones that must offer nothing at all ---
    ("none_mention_only", "I read a letter yesterday"),
    ("none_already_switching", "I want to switch the model to qwen3.5:9b"),
    ("none_already_setups", "which work setup should I use?"),
    ("none_smalltalk", "how are you today?"),
    ("none_crisis", "I feel like I can't go on and want to die"),
    ("none_empty", "   "),
)


def _status(names, current, chosen=None):
    """`GET /api/work`'s real answer, with only the Ollama reads replaced.

    `installed()` and `_current_model()` are the two things that touch this PC;
    everything else below is the module's own code, unpatched. With no
    `chosen`, `choice()` is answered as "nothing chosen" so the tool never
    reads (or needs) the owner's real config folder.
    """
    saved = W.installed, W._current_model, W.choice
    W.installed = lambda force=False: names
    W._current_model = lambda: current
    if chosen is None:
        W.choice = lambda: {"setup": None, "at": None}
    try:
        if chosen is not None:
            with _choice_temp(chosen):
                return W.status()
        return W.status()
    finally:
        W.installed, W._current_model, W.choice = saved


class _choice_temp:
    """A temporary config folder holding one chosen setup, so `choose()` and
    `status()` can be exercised without touching the owner's own."""

    def __init__(self, chosen):
        self.chosen = chosen
        self.dir = None

    def __enter__(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp(prefix="jarvis-work-cases-"))
        (self.dir / W.CHOICE_FILE).write_text(
            json.dumps({"setup": self.chosen, "at": 1770000000}), encoding="utf-8")
        self.saved = W._config_dir
        W._config_dir = lambda: self.dir
        return self

    def __exit__(self, *exc):
        import shutil
        W._config_dir = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


def _post(fn, names, current):
    """Run one call with Ollama's answers replaced and any choice written to a
    temporary folder, never the owner's config folder. Returns whatever `fn`
    returns - a (code, body) pair for the routes, an offer for recommend.

    EVERY case below goes through here, including the ones that only read:
    `recommend` asks which model is running, so without this a case would
    depend on what happened to be loaded on the machine that generated the
    file - and the golden file would differ between two runs of the same code.
    """
    saved = W.installed, W._current_model
    W.installed = lambda force=False: names
    W._current_model = lambda: current
    try:
        with _choice_temp(None):
            return fn()
    finally:
        W.installed, W._current_model = saved


def build() -> dict:
    cases = {}
    cases["today"] = _status(TODAY, "qwen3:8b")
    cases["fresh_pc"] = _status(FRESH, "jarvis-primary:latest")
    cases["ollama_unreachable"] = _status(None, None)
    cases["chosen_coding"] = _status(TODAY, "jarvis-primary:latest", chosen="coding")
    cases["chosen_admin_already_running"] = _status(TODAY, "qwen3.5:9b", chosen="admin")

    for name, words in WORD_CASES:
        cases[name] = {"words": words, "answer": _post(lambda w=words: W.recommend(w),
                                                       TODAY, "qwen3:8b")}

    # The writes, as (http code, body) - exactly what a route sends.
    for name, setup_id, names, current in (
            ("post_choose_coding", "coding", TODAY, "jarvis-primary:latest"),
            ("post_choose_specialist_fresh_pc", "specialist", FRESH, "qwen3:8b"),
            ("post_choose_none", None, TODAY, "qwen3:8b"),
            ("post_choose_unknown", "nonsense", TODAY, "qwen3:8b")):
        code, body = _post(lambda i=setup_id: W.choose(i), names, current)
        cases[name] = {"status": code, "body": body}
    for name, body in (("post_handle_choose_long", {"setup": "long"}),
                       ("post_handle_choose_no_setup", {}),
                       ("post_recommend", {"words": "I'm going to build an Android app"}),
                       ("post_recommend_no_words", {})):
        fn = (W.handle_recommend if name.startswith("post_recommend")
              else W.handle_choose)
        code, out = _post(lambda b=body, f=fn: f(b), TODAY, "qwen3:8b")
        cases[name] = {"status": code, "body": out}

    return {
        "what": ("The real answers of GET /api/work and its POSTs "
                 "(backend/jarvis_work.py). Written by tools/gen_work_cases.py."),
        "measured_on": "2026-10-10, the owner's PC",
        "not_a_catalogue": ("Five combinations of models already on this PC. "
                            "Nothing here is a list of what could be downloaded."),
        "setup_ids": list(W.SETUP_IDS),
        "switch_path": W.SWITCH_PATH,
        "cases": cases,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="compare, do not write")
    args = ap.parse_args(argv)
    text = json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        if not OUT.is_file():
            print(f"FAIL  {OUT.relative_to(ROOT)} is missing")
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"FAIL  {OUT.relative_to(ROOT)} is not what the code answers now")
            print("      run: python3 tools/gen_work_cases.py")
            return 1
        print(f"ok    {OUT.relative_to(ROOT)} equals a fresh run")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
