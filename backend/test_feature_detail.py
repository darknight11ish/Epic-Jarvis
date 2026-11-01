"""test_feature_detail.py - Jarvis talks about every feature IN DETAIL.

    python -B backend/test_feature_detail.py

THE OWNER'S ASK (2026-10-31): "I want Jarvis to be able to talk about all of
its features in detail. make sure you aren't missing anything." #1041 gave
tell-me/how/limits/asks/surface/why/compare/overview for every catalogue row;
this suite is the DEPTH half and its acceptance test:

1. EVERY ROW, DYNAMICALLY. For every row in `features/features.json` (147 and
   counting), "explain <title> in detail" and "how do I use <title>" both
   resolve to that row and the detail answer quotes at least five of the row's
   own fields, carries its live/derived state, and points at "Everything
   Jarvis can do".
2. EVERY DETAIL SHAPE. explain-in-detail, tell-me-everything, how-do-I-use,
   what-do-I-say-to-use, give-me-an-example, how-do-I-set-X-up, is-X-private,
   what-does-X-need, why-is-X-on/off, what-can-go-wrong, can-X-do-Y and
   what-is-X-like each answer from the row's own fields - and an unrecorded
   limit/privacy note is said plainly, never invented.
3. EVERY ALIAS AND THE NEW ROWS. Every `aliases` entry in the source, the
   owner aliases #1041 added (Today board, quiet hours, thinking level,
   memories), and the newer rows (File from your PC, Protected from Jarvis,
   Create and customize your notes) are detail-answerable.
4. NO OVER-CAPTURE. Ordinary conversation about non-features ("explain the
   theory of relativity", "how do I use a screwdriver", "what is love like")
   still reaches the model.
5. READ-ONLY. The detail intents are in READ_ONLY_INTENTS: they read the
   catalogue and the state, raise no card and write nothing.

No model, no network, no owner's settings file: the catalogue is the shipped
module and the state reads are the same ones the Features pages use.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-feature-detail-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []
NOW = time.mktime(time.strptime("2026-10-31 09:05:00", "%Y-%m-%d %H:%M:%S"))
SOURCE = __import__("json").loads(
    (REPO / "features" / "features.json").read_text(encoding="utf-8"))
BY_ID = {row["id"]: row for row in SOURCE}
TITLES = {row["title"]: row["id"] for row in SOURCE}
TAIL = FG.CAPABILITY_TAIL


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def words_of(out: dict) -> str:
    return str((out or {}).get("words") or "")


def quick(phrase: str):
    return Q.match(phrase, NOW)


# --------------------------------------------------------------------------
# 1. Every row, dynamically: two deep shapes resolve and quote 5 own fields
# --------------------------------------------------------------------------
def t_every_row_is_deep_answerable_by_both_shapes():
    bad_match, bad_fields = [], []
    for row in SOURCE:
        fid, title = row["id"], row["title"]
        for phrase in (f"explain {title} in detail",
                       f"how do I use {title}"):
            got = quick(phrase)
            if (got is None or got.name != "feature_detail"
                    or got.f.get("id") != fid
                    or got.f.get("mode") != "detail"):
                bad_match.append((fid, phrase,
                                  got.name if got else "the model",
                                  got.f if got else None))
        out = FG.detail(title)
        words = words_of(out)
        if (out.get("kind") != "feature"
                or (out.get("feature") or {}).get("id") != fid):
            bad_fields.append((fid, "not-this-row", out.get("kind")))
            continue
        own = [str(row.get(k) or "").strip() for k in
               ("what", "where", "asks", "limit", "surface", "group")]
        quoted = [f for f in own if f and f in words]
        if row["title"] not in words or len(quoted) < 5:
            bad_fields.append((fid, len(quoted)))
        for marker in ("Where it lives:", "Does it ask first?",
                       "The honest limit:", "Its state:",
                       "Which app(s):", "What it needs:"):
            if marker not in words:
                bad_fields.append((fid, "missing:" + marker))
        if TAIL not in words:
            bad_fields.append((fid, "no list pointer"))
    check(f"all {len(SOURCE)} rows resolve through BOTH deep shapes",
          not bad_match, bad_match[:8])
    check(f"all {len(SOURCE)} rows quote >=5 own fields, state and pointer",
          not bad_fields, bad_fields[:8])


def t_every_row_carries_an_honest_limit():
    # 2026-10-31 coverage: no row is left with an empty limit any more - every
    # row the audit called thin now carries its own one-line limit. The branch
    # is kept dynamic for a future row: a row with an empty limit must say so
    # plainly rather than inventing one.
    empty = [r for r in SOURCE if not str(r.get("limit") or "").strip()]
    check("every catalogue row carries a limit (none is left empty)",
          not empty, empty)
    for row in empty:
        words = words_of(FG.detail(row["title"]))
        check(f"{row['id']}: no recorded limit is said plainly, not invented",
              ("no limit" in words.lower() or "records no limit" in words.lower()),
              words[:300])
        wrong = words_of(FG.goes_wrong(row["title"]))
        check(f"{row['id']}: 'what can go wrong' also says no limit is recorded",
              "records no limit" in wrong.lower(), wrong[:300])


# --------------------------------------------------------------------------
# 2. Each detail shape, one honest example per shape
# --------------------------------------------------------------------------
def t_each_detail_shape_answers_from_the_rows_own_fields():
    row = BY_ID["galaxy"]
    shapes = {
        "explain Galaxy in detail": ("detail", "mode:detail"),
        "tell me everything about Galaxy": ("detail", "mode:detail"),
        "how do I use Galaxy": ("detail", "mode:detail"),
        "what do I say to use Galaxy": ("detail", "mode:example"),
        "give me an example of Galaxy": ("detail", "mode:example"),
        "how do I set Galaxy up": ("detail", "mode:detail"),
        "is Galaxy private": ("detail", "mode:private"),
        "what does Galaxy need": ("detail", "mode:needs"),
        "why is Galaxy on": ("detail", "mode:why_state"),
        "what can go wrong with Galaxy": ("detail", "mode:goes_wrong"),
        "what is Galaxy like": ("detail", "mode:like"),
    }
    for phrase, (_name, want) in shapes.items():
        got = quick(phrase)
        mode = got.f.get("mode") if got is not None else None
        check(f"{phrase!r} is the detail answer",
              got is not None and got.name == "feature_detail"
              and got.f.get("id") == "galaxy" and mode == want.split(":")[1],
              (got.name if got else "the model", got.f if got else None))
    # The private answer quotes the row's own words and is honest when no
    # privacy note is recorded.
    priv = words_of(FG.is_private("galaxy"))
    check("is-X-private quotes only the row's own words",
          row["where"] in priv and row["limit"] in priv, priv[:320])
    # Needs names the real Settings place and the asks rule, never a guessed
    # dependency.
    needs = words_of(FG.needs("galaxy"))
    check("what-does-X-need names the Settings place and ask rule",
          "What it needs:" in needs and "Settings" in needs
          and row["asks"] in needs, needs[:320])
    # Why-on/off quotes the state and the row's limlimit.
    why = words_of(FG.why_state("galaxy"))
    check("why-is-X-on/off quotes the state and the honest limit",
          "Its state:" in why and row["limit"] in why, why[:320])
    # What-can-go-wrong is the row's own limit, no invention.
    wrong = words_of(FG.goes_wrong("galaxy"))
    check("what-can-go-wrong is the row's own limit",
          row["limit"] in wrong and "can go wrong" not in wrong.lower()
          or "honest limit" in wrong, wrong[:320])


def t_can_x_do_y_answers_only_from_xs_own_text():
    yes = FG.can_do("galaxy", "a map of what Jarvis knows")
    check("a capability in the row is answered with the row's own words",
          yes.get("kind") == "feature"
          and "map of what Jarvis knows" in words_of(yes)
          and "not listed" not in words_of(yes), words_of(yes)[:320])
    no = FG.can_do("galaxy", "send an email")
    check("a capability NOT in the row says so plainly and gives its limits",
          no.get("kind") == "not_listed"
          and "That is not listed as part of Galaxy." in words_of(no)
          and BY_ID["galaxy"]["limit"] in words_of(no), words_of(no)[:320])
    got = quick("can Galaxy do 3D?")
    check("the quick path routes 'can X do Y' to the can-do answer",
          got is not None and got.name == "feature_can_do"
          and got.f.get("id") == "galaxy"
          and got.f.get("capability") == "3d", got.f if got else "the model")


# --------------------------------------------------------------------------
# 3. Aliases and the newer rows
# --------------------------------------------------------------------------
def t_every_alias_and_the_new_rows_are_detail_answerable():
    bad = []
    for row in SOURCE:
        for alias in row.get("aliases") or ():
            out = FG.detail(alias)
            if (out.get("kind") != "feature"
                    or (out.get("feature") or {}).get("id") != row["id"]):
                bad.append((alias, row["id"], out.get("kind")))
    owner_aliases = {
        "Today board": "today",
        "quiet hours": "notifications",
        "thinking level": "thinking-levels",
        "memories": "memory-saved",
    }
    for alias, fid in owner_aliases.items():
        out = FG.detail(alias)
        check(f"the owner alias {alias!r} resolves in detail to {fid!r}",
              (out.get("feature") or {}).get("id") == fid, out.get("kind"))
    check(f"every source alias ({sum(len(r.get('aliases') or ()) for r in SOURCE)}) "
          "resolves in detail to its own row", not bad, bad[:8])
    for title, fid in (("File from your PC", "file-from-pc"),
                       ("Protected from Jarvis", "protected-items"),
                       ("Create and customize your notes", "notes-editor")):
        row = next((r for r in SOURCE if r["title"] == title), None)
        check(f"the newer row {title!r} exists in the catalogue", row is not None,
              [r["id"] for r in SOURCE][:5])
        if row is not None:
            words = words_of(FG.detail(row["title"]))
            check(f"... and is deep-answerable with its own fields",
                  row["title"] in words and row["what"] in words
                  and "Its state:" in words, words[:260])


# --------------------------------------------------------------------------
# 4. No over-capture of ordinary conversation
# --------------------------------------------------------------------------
def t_detail_shapes_do_not_capture_ordinary_conversation():
    for phrase in ("explain the theory of relativity",
                   "how do I use a screwdriver",
                   "what is love like",
                   "is my oven private",
                   "what does a plant need",
                   "what can go wrong with my car",
                   "can my car do 100mph"):
        got = quick(phrase)
        check(f"{phrase!r} is still the model's",
              got is None or got.name != "feature_detail"
              and got.name != "feature_can_do",
              got.name if got else "the model")
    check("the detail intents are read-only",
          "feature_detail" in Q.READ_ONLY_INTENTS
          and "feature_can_do" in Q.READ_ONLY_INTENTS)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
