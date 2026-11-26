"""test_note_duplicates.py - DEF-095: finding duplicate and near-duplicate notes.

    python -B backend/test_note_duplicates.py

WHY THIS SUITE EXISTS. The owner asked, in their own words on 2026-11-24:

    "i would like you to go through my notes and delete any copy or almost
     identical copy. leave at least one copy, delete any duplicates"

and the answer was "I cannot delete your notes. My access to your Obsidian or
Joplin files is strictly read-only" - false twice. Deleting a note had shipped
the day before (`delete_vault_notes`, one card naming every path, into .trash),
and the half that truly did not exist was the duplicate scan: measured on the
live install, "look for notes that have copies", "find duplicate notes" and
"do I have any duplicate notes" all reached NO intent and fell to the model.
This suite is that measurement turned into a test.

WHAT IT PINS

1. ROUTING. Every sentence the owner says reaches `note_duplicates` and is
   answered without the model; the two capability questions ("can you delete my
   notes?", "can you find duplicates?") reach their own answers, which say YES
   and never "I cannot"; and sentences that name a real search term, a named
   note or a topic are NOT swallowed by the new lane.
2. THE THREE KINDS, on a seeded vault:
     (a) two identical copies (the same normalised body, front matter ignored);
     (b) the same title in two different folders;
     (c) a near copy with one word changed (>= the stated threshold);
     (d) two DIFFERENT notes on one subject, which must NOT be grouped;
     plus an empty, untitled note, whose count the answer reports.
3. THE BOUNDS. A 1,202-note vault: exactly 1,200 are opened, the two OLDEST are
   skipped, the answer says so, and the identical pair among those two is found
   only when the cap is lifted - so the cap, not luck, is what excluded it.
4. THE ANSWER. The groups, the threshold it used, the counts it covered and
   skipped, the group cap, the one it would keep (oldest, tie to the shorter
   path), and the ONE offer: "Say which to remove".
5. NOTHING IS DELETED BY THE SCAN. No card is raised and every note's bytes are
   unchanged. The removal, when the owner names the notes, is exactly ONE
   `delete_vault_notes` card naming both paths, and both notes land in .trash.
6. THE TWIN is byte-identical (the repository's two-file rule).

THE VAULT HERE IS FAKE: a temporary folder, temp settings and a temp receipts
DB; `jarvis_framework` and the gate's `check` are stand-ins; no model, no
network, nothing of the owner's is read or written. The clock is fixed so the
"oldest" / "newest" sentences are deterministic.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_notes.py", "jarvis_quick.py",
                "jarvis_feature_catalogue.py")

# ── a temporary vault, and settings that are never the owner's ──────────────
_TMP = Path(tempfile.gettempdir()) / ("jarvis-note-dupes-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ.pop("JARVIS_BACKEND", None)

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask"
FW.audit_log = lambda event, detail: None
sys.modules["jarvis_framework"] = FW


class _Verdict:
    """The gate's own answer shape; the stand-in approves everything."""

    allowed = True
    outcome = "approved"
    tier = "ask"
    reason = ""


GATE = {"calls": [], "cards": []}


def gate_check(action, detail=None, prompt="", **kwargs):
    GATE["calls"].append(action)
    GATE["cards"].append((action, detail, prompt))
    return _Verdict()


GATE_MODULE = types.ModuleType("jarvis_gate")
GATE_MODULE.check = gate_check
GATE_MODULE.taint_active = lambda: False
GATE_MODULE.pending = lambda: []
sys.modules["jarvis_gate"] = GATE_MODULE

import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402

#: A fixed clock: Wednesday 2026-11-25, 21:30 local. Every date and "oldest"
#: sentence below is read against it, never against the day the suite runs.
NOW = time.mktime(time.strptime("2026-11-25 21:30:00", "%Y-%m-%d %H:%M:%S"))
DAY = 86400.0


class Stub:
    """The scheduler stand-in `answer()` wants; the note lane never uses it."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: []

    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"ok   {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}" + (f"\n        {detail}" if detail else ""))


def skip(why):
    """A skip is NEVER a pass here: it is printed and counted on its own."""
    SKIPPED.append(why)
    print(f"SKIP {why}")


def put(rel: str, text: str, age_days: float = 0.0) -> Path:
    full = VAULT / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    stamp = NOW - float(age_days) * DAY
    os.utime(full, (stamp, stamp))
    return full


def here(rel: str) -> bool:
    return (VAULT / rel).is_file()


def reset_all() -> None:
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    try:
        E._reset_for_tests()
    except Exception:                       # noqa: BLE001 - not in every build
        pass
    GATE["calls"], GATE["cards"] = [], []


def snapshot() -> dict:
    return {str(p.relative_to(VAULT)).replace("\\", "/"): p.read_bytes()
            for p in VAULT.rglob("*") if p.is_file()}


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=NOW, peer="127.0.0.1", local=True)


def intent_of(res) -> str:
    return getattr(res, "intent", "") or ""


def said(res) -> str:
    return getattr(res, "reply", "") or ""


# --------------------------------------------------------------------------
#   The seeded small vault, in the shape of the owner's live one
# --------------------------------------------------------------------------
A_BODY = "# Shopping\n\nmilk eggs bread butter cheese apples\n"


def seed_small() -> None:
    """(a) identical, (b) same title in two folders, (c) near, (d) not a copy.

    The two notes in (a) carry the SAME H1, because the body is what is
    compared - two notes whose titles differ are still copies when their words
    are the same. The (d) pair shares its subject (tomatoes, the last frost) and
    must still be two different notes: the threshold is stated so a reader can
    see why it is not a group.

    Two pairs are here to be EXCLUDED (the owner's ruling, 2026-11-25): two
    byte-identical `untitled` notes and two empty files. Neither may appear in a
    group or in the one removal the answer offers.
    """
    reset_all()
    # (a) identical normalised bodies
    put("Shopping.md", A_BODY, 30.0)
    put("Archive/Shopping copy.md", A_BODY, 5.0)
    # (b) the same title in two different folders
    put("Projects/Plan.md",
        "# Plan\n\nfirst the survey then the drawings then the build\n", 20.0)
    put("Archive/Plan.md",
        "# Plan\n\nthe boiler service is due in march and the car needs new "
        "tyres\n", 3.0)
    # (c) a near copy: one word changed in a 15-word body
    put("Boiler.md",
        "# Boiler\n\nthe boiler service is due in march and the car needs new "
        "tyres soon\n", 10.0)
    put("Boiler notes.md",
        "# Boiler notes\n\nthe boiler service is due in march and the car needs "
        "new tyres now\n", 2.0)
    # (d) two DIFFERENT notes on one subject: the same topic, other sentences.
    put("Garden.md",
        "# Garden\n\nplant the tomatoes after the last frost and water them "
        "every day\n", 8.0)
    put("Garden plan.md",
        "# Garden plan\n\nplant the tomatoes after the last frost then feed "
        "them once a week and cut the lawn\n", 7.0)
    # Excluded by name: two BYTE-IDENTICAL untitled notes.
    put("untitled.md",
        "# Untitled\n\nthe identical words in both untitled files here\n", 6.0)
    put("untitled 3.md",
        "# Untitled\n\nthe identical words in both untitled files here\n", 4.0)
    # Excluded by size: two empty files.
    put("Empty one.md", "", 9.0)
    put("Empty two.md", "", 8.0)


# --------------------------------------------------------------------------
# 1. Routing: every sentence reaches the new lane, and near misses do not
# --------------------------------------------------------------------------
FINDING_ROWS = (
    "look for notes that have copies",
    "find duplicate notes",
    "do I have any duplicate notes",
    "find my notes with copies",
    "any duplicate notes",
    "which notes are duplicated",
    "show me duplicated notes",
    "are there any duplicate notes",
    "check my notes for duplicates",
    "find my duplicate notes in my vault",
    "delete duplicate notes",
    "delete the copies",
)

CAPABILITY_ROWS = (
    ("can you delete my notes", "note_delete_capability"),
    ("can you delete notes", "note_delete_capability"),
    ("can you delete all my notes", "note_delete_capability"),
    ("can you find duplicates", "note_duplicates_capability"),
    ("can you find duplicate notes", "note_duplicates_capability"),
    ("do you have a way to find duplicate notes", "note_duplicates_capability"),
)

#: Sentences that must NOT be swallowed by the new lane: the note search lane,
#: a named note (a delete REQUEST with its one card), and a topic.
NOT_SWALLOWED = (
    ("find my notes about milk", "note_search"),
    ("search my notes for milk", "note_search"),
    ("find notes about the boiler", "note_search"),
)


def t_every_sentence_reaches_the_lane():
    seed_small()
    for text in FINDING_ROWS:
        try:
            got = Q.match(text, NOW)
        except Exception as exc:            # noqa: BLE001 - a crash IS a finding
            check(f"{text!r} routes", False, f"{type(exc).__name__}: {exc}")
            continue
        name = None if got is None else got.name
        check(f"{text!r} -> note_duplicates", name == "note_duplicates", name)
    for text, want in CAPABILITY_ROWS:
        got = Q.match(text, NOW)
        name = None if got is None else got.name
        check(f"{text!r} -> {want}", name == want, name)
    for text, want in NOT_SWALLOWED:
        got = Q.match(text, NOW)
        name = None if got is None else got.name
        check(f"{text!r} is not the duplicate lane", name == want, name)
    got = Q.match("can you delete my Shopping note", NOW)
    name = None if got is None else got.name
    check("a delete question that NAMES a note stays a delete request",
          name == "note_delete", name)
    got = Q.match("find duplicate notes about the boiler", NOW)
    check("a duplicate question that names a TOPIC is not the bare scan",
          got is None or got.name != "note_duplicates",
          None if got is None else got.name)


def t_the_capability_answers_say_yes_and_never_cannot():
    for text, want in CAPABILITY_ROWS[:1] + CAPABILITY_ROWS[3:4]:
        res = ask(text)
        reply = said(res)
        check(f"{text!r} answers {want}, not the model", intent_of(res) == want,
              intent_of(res) or "the model")
        check(f"... and it says YES in words ({text!r})",
              reply.strip().lower().startswith("yes"), reply[:120])
        check(f"... and it never says I cannot ({text!r})",
              "cannot" not in reply.lower() and "can't" not in reply.lower(),
              reply[:160])
    del_res = ask("can you delete my notes")
    check("... the delete answer names the real card, its confirmation and .trash",
          "one approval card" in said(del_res).lower()
          and ".trash" in said(del_res)
          and "windows hello" in said(del_res).lower()
          and "20" in said(del_res), said(del_res)[:400])
    dup_res = ask("can you find duplicates")
    reply = said(dup_res)
    check("... the duplicate answer names the threshold and the cap it really uses",
          f"at least {int(round(E.DUP_SIMILARITY * 100))}% the same words" in reply
          and f"at most {E.DUP_SCAN_CAP} notes" in reply, reply[:400])
    check("... it says untitled and empty notes are left out",
          "Untitled notes and empty files are left out" in reply, reply[:400])
    check("... and it promises no write: the scan never deletes",
          "never deletes or changes anything" in reply, reply[:400])


# --------------------------------------------------------------------------
# 2. The scan: the three kinds, the counts, the threshold, the offer
# --------------------------------------------------------------------------
def t_the_scan_finds_the_three_kinds_and_skips_the_different_ones():
    seed_small()
    before = snapshot()
    code, body = E.chat_find_duplicates()
    check("the scan answers 200", code == 200, (code, body))
    if code != 200:
        return
    check("it opened every note it could compare in this small vault",
          body["total"] == 12 and body["candidates"] == 8
          and body["opened"] == 8 and body["skipped"] == 0, body)
    check("it compared 8 notes and could not read none",
          body["scanned"] == 8 and body["unreadable"] == 0, body)
    check("the two untitled notes and the two empty files were excluded",
          body["excluded_untitled"] == 2 and body["excluded_empty"] == 2, body)
    check("it states the cap and the threshold it used",
          body["cap"] == E.DUP_SCAN_CAP and body["threshold"] == E.DUP_SIMILARITY,
          (body.get("cap"), body.get("threshold")))
    kinds = [g["kind"] for g in body["groups"]]
    check("the three groups are identical, same-name and near, in that order",
          body["count"] == 3 and kinds == ["identical", "same_name", "near"], kinds)
    groups = body["groups"]
    identical = groups[0]
    check("the identical pair is the two notes with the same normalised body",
          identical["paths"] == ["Archive/Shopping copy.md", "Shopping.md"],
          identical["paths"])
    check("... and the oldest of them is the one it would keep",
          identical["keep"] == "Shopping.md"
          and identical["newest"] == "Archive/Shopping copy.md",
          (identical["keep"], identical["newest"]))
    same = groups[1]
    check("the same-name group is the one title in two folders",
          same["paths"] == ["Archive/Plan.md", "Projects/Plan.md"], same["paths"])
    check("... it names the largest and the one it would keep",
          same["largest"] == "Archive/Plan.md"
          and same["keep"] == "Projects/Plan.md",
          (same["largest"], same["keep"]))
    near = groups[2]
    check("the near pair is the one-word-changed copy",
          near["paths"] == ["Boiler notes.md", "Boiler.md"], near["paths"])
    check("... at or above the stated threshold, and it says the figure it found",
          near["similarity"] is not None
          and near["similarity"] >= E.DUP_SIMILARITY, near["similarity"])
    flat = str(body)
    check("two different notes on one subject are NOT a group",
          "Garden" not in flat, [p for g in groups for p in g["paths"]])
    paths = [p for g in groups for p in g["paths"]]
    check("two byte-identical untitled notes are NOT a group",
          not any("untitled" in p.lower() for p in paths), paths)
    check("two empty files are NOT a group",
          not any("empty" in p.lower() for p in paths), paths)
    after = snapshot()
    check("the scan changed nothing on disk", before == after,
          sorted(set(before) ^ set(after)))
    check("the scan raised no approval card", GATE["calls"] == [], GATE["calls"])


def t_untitled_and_empty_notes_are_never_copies():
    """The owner's ruling, 2026-11-25: untitled notes get their own management,
    and two empty files are not copies of each other - even when the bytes of
    the two untitled ones are identical."""
    reset_all()
    put("untitled.md", "# Untitled\n\nidentical words in both untitled notes\n", 3.0)
    put("untitled 2.md", "# Untitled\n\nidentical words in both untitled notes\n", 2.0)
    put("Empty A.md", "", 4.0)
    put("Empty B.md", "", 1.0)
    code, body = E.chat_find_duplicates()
    check("a vault of only untitled and empty notes has no groups",
          code == 200 and body["count"] == 0 and body["groups"] == [], body)
    check("... and it counts both, separately, before reading anything",
          body["excluded_untitled"] == 2 and body["excluded_empty"] == 2
          and body["candidates"] == 0, body)
    res = ask("any duplicate notes")
    reply = said(res)
    check("... the answer says they were left out and why",
          "I left out 2 untitled notes and 2 empty files" in reply
          and "does not treat those as copies" in reply, reply[:400])
    check("... it says there was nothing it could compare",
          "no notes I can compare" in reply, reply[:300])
    check("... and it offers nothing to remove",
          "Say which to remove" not in reply, reply[-200:])


def t_the_answer_states_what_it_covered_and_offers_one_next_step():
    seed_small()
    res = ask("find duplicate notes")
    reply = said(res)
    check("the sentence reaches the scan, not the model",
          intent_of(res) == "note_duplicates", intent_of(res) or "the model")
    check("it says it scanned every note it could compare, and names the cap",
          "I scanned all 8 notes I could compare in your vault" in reply
          and f"{E.DUP_SCAN_CAP} is the most I read in one pass" in reply,
          reply[:300])
    check("it says what it left out, and why, in one clause",
          "I left out 2 untitled notes and 2 empty files" in reply
          and "does not treat those as copies" in reply, reply[:500])
    check("it says what it found, in groups",
          "I found 3 groups of copies." in reply, reply[:300])
    check("it states the threshold and the shortest note it compares",
          f"at least {int(round(E.DUP_SIMILARITY * 100))}% the same words" in reply
          and f"at least {E.DUP_MIN_WORDS} words" in reply, reply[:400])
    check("it names the keep rule in words",
          "it is the oldest copy; a tie goes to the shorter path" in reply,
          reply[:400])
    check("it lists all three kinds by name",
          "1. identical copies:" in reply
          and "2. the same name in two different folders:" in reply
          and "3. near copies (at least" in reply, reply)
    check("it says which copy it would keep for the identical pair",
          "the oldest, which I would keep, is Shopping.md" in reply, reply)
    check("it ends with ONE offer: say which to remove",
          reply.rstrip().endswith("I delete up to 20 notes at a time.")
          and 'Say which to remove' in reply
          and "one card before anything moves" in reply, reply[-300:])
    check("the offer raised nothing yet", GATE["calls"] == [], GATE["calls"])


def t_a_vault_with_no_duplicates_says_so_and_offers_nothing():
    reset_all()
    put("One.md", "# One\n\nsomething entirely its own about the sea and the wind\n", 4.0)
    put("Two.md", "# Two\n\nanother note about the kitchen and the shopping list\n", 3.0)
    res = ask("do I have any duplicate notes")
    reply = said(res)
    check("an ordinary vault answers with the scan",
          intent_of(res) == "note_duplicates", intent_of(res) or "the model")
    check("it says it found no groups, and it still names the measure",
          "I found no groups of copies." in reply
          and "the same words" in reply, reply[:400])
    check("with nothing to remove it makes no removal offer",
          "Say which to remove" not in reply, reply[-200:])


def t_a_delete_shaped_sentence_is_still_a_read():
    seed_small()
    before = snapshot()
    res = ask("delete duplicate notes")
    reply = said(res)
    check("'delete duplicate notes' is the scan, not a delete",
          intent_of(res) == "note_duplicates", intent_of(res) or "the model")
    check("... it opens by saying nothing has been deleted",
          reply.startswith("Nothing has been deleted."), reply[:120])
    check("... and it still offers the one named removal",
          "Say which to remove" in reply, reply[-200:])
    check("... and nothing moved", before == snapshot())
    check("... and no card was raised", GATE["calls"] == [], GATE["calls"])


# --------------------------------------------------------------------------
# 3. The bound: a 1,202-note vault opens 1,200 and says which two it skipped
# --------------------------------------------------------------------------
OUTSIDE_A = "# Outside\n\nthe same words in both of these two files\n"
OUTSIDE_B = "# Outside\n\nthe same words in both of these two files\n"


def seed_huge_vault() -> None:
    """1,202 notes: 1,200 unique fillers plus an identical pair OLDER than all.

    The pair is a real duplicate - lifting the cap finds it - so the test proves
    the cap excluded it, not that it was never a copy.
    """
    reset_all()
    for i in range(1200):
        put(f"filler/filler{i:04d}.md",
            f"filler {i} alpha{i} beta{i}", 0.05 + i / 100000.0)
    put("zz/Outside A.md", OUTSIDE_A, 40.0)
    put("zz/Outside B.md", OUTSIDE_B, 39.0)


def t_the_scan_is_bounded_and_says_which_notes_it_skipped():
    seed_huge_vault()
    code, body = E.chat_find_duplicates()
    check("the huge vault answers 200", code == 200, (code, body))
    if code != 200:
        return
    check("exactly the cap was opened, and the two oldest were not",
          body["total"] == 1202 and body["opened"] == E.DUP_SCAN_CAP
          and body["scanned"] == E.DUP_SCAN_CAP and body["skipped"] == 2, body)
    check("the outside pair is not in any group",
          body["count"] == 0 and not any("Outside" in str(g) for g in body["groups"]),
          body["groups"])
    res = ask("find duplicate notes")
    reply = said(res)
    check("the answer says how many it scanned, out of how many, and why",
          f"I scanned {E.DUP_SCAN_CAP} of the 1202 notes" in reply
          and "2 older notes were not read" in reply, reply[:400])
    check("... it never claims the whole vault",
          "That was all of them" not in reply and "all 1202" not in reply,
          reply[:400])
    # The control: lift the cap and the same two notes ARE a group.
    code, full = E.chat_find_duplicates(limit=1202)
    check("with the cap lifted the same two notes are one identical group",
          code == 200 and full["count"] == 1
          and full["groups"][0]["kind"] == "identical"
          and sorted(full["groups"][0]["paths"])
          == ["zz/Outside A.md", "zz/Outside B.md"], full.get("groups"))
    check("the cap, not the content, is what excluded them",
          E.DUP_SCAN_CAP < 1202, E.DUP_SCAN_CAP)


def t_the_group_list_is_capped_and_says_so():
    """Nine identical PAIRS - nine groups - and only eight are listed."""
    reset_all()
    for i in range(9):
        body = (f"# Shared {i}\n\none two three four five six seven eight nine "
                f"ten eleven twelve {i}\n")
        put(f"pair{i}a.md", body, 20.0 - i)
        put(f"pair{i}b.md", body, 19.0 - i)
    code, scanned = E.chat_find_duplicates()
    check("nine identical pairs make nine groups, eight listed",
          code == 200 and scanned["count"] == 9 and scanned["shown"] == 8
          and scanned["truncated"] is True, scanned)
    res = ask("which notes are duplicated")
    check("... and the answer says it has shown the first eight of nine",
          "I have shown the first 8 of 9 groups" in said(res), said(res)[:400])


# --------------------------------------------------------------------------
# 4. The removal: nothing until asked, then exactly ONE existing card
# --------------------------------------------------------------------------
def t_the_delete_is_the_existing_card_with_both_paths_named():
    seed_small()
    GATE["calls"], GATE["cards"] = [], []
    first = ask("find duplicate notes")
    check("the scan itself raises no card",
          GATE["calls"] == [] and "Say which to remove" in said(first),
          GATE["calls"])
    res = ask("delete notes Shopping and Shopping copy")
    check("naming both notes is a delete through the existing lane",
          intent_of(res) in ("note_deleted", "note_delete_waiting"),
          intent_of(res) or "the model")
    check("... exactly ONE card, under delete_vault_notes",
          GATE["calls"] == ["delete_vault_notes"], GATE["calls"])
    if GATE["cards"]:
        action, detail, prompt = GATE["cards"][-1]
        check("... the card names both paths in its own line",
              "Shopping.md" in prompt and "Archive/Shopping copy.md" in prompt,
              prompt)
        check("... and its detail carries the same two paths, and says .trash",
              detail.get("paths") == ["Shopping.md", "Archive/Shopping copy.md"]
              and detail.get("trash") is True and detail.get("deletes") is True,
              detail)
    check("... both notes left the vault and are in .trash",
          not here("Shopping.md")
          and not here("Archive/Shopping copy.md")
          and (VAULT / ".trash" / "Shopping.md").is_file()
          and (VAULT / ".trash" / "Archive" / "Shopping copy.md").is_file(),
          sorted(str(p.relative_to(VAULT)) for p in VAULT.rglob("*.md")))
    check("... and nothing else was touched",
          here("Boiler.md") and here("Projects/Plan.md"), "another note moved")


def t_the_hidden_lists_rule_is_kept():
    try:
        import jarvis_private_view as PV
        PV.note_state(app_locked=False, hide_memory_lists=True)
    except Exception:                       # noqa: BLE001 - not in every build
        skip("jarvis_private_view is not in this checkout, so the hidden-lists "
             "rule could not be driven here - it is NOT verified by this run")
        return
    try:
        seed_small()
        res = ask("find duplicate notes")
        check("while the lists are hidden the scan lists no title",
              intent_of(res) == "note_duplicates"
              and said(res) == Q.NOTES_SEARCH_HIDDEN
              and "Shopping" not in said(res), said(res)[:200])
        check("... and raises no card", GATE["calls"] == [], GATE["calls"])
    finally:
        PV.note_state(app_locked=False, hide_memory_lists=False)


# --------------------------------------------------------------------------
# 5. The twin rule, and the module's own constants
# --------------------------------------------------------------------------
def t_the_two_copies_are_one_file():
    for name in ("jarvis_notes_edit.py", "jarvis_quick.py",
                 "jarvis_feature_catalogue.py"):
        a = (REPO / "backend" / name).read_bytes()
        b = (REPO / "jarvis-backend" / name).read_bytes()
        check(f"twin: {name} is identical in both copies", a == b,
              f"backend {len(a)} bytes, jarvis-backend {len(b)}")


def t_the_constants_are_bounded_numbers():
    check("the scan cap is a real bound, not the whole vault",
          isinstance(E.DUP_SCAN_CAP, int) and 0 < E.DUP_SCAN_CAP <= 2000,
          E.DUP_SCAN_CAP)
    check("the group cap is smaller than the notes it can find",
          isinstance(E.DUP_GROUP_CAP, int) and 2 <= E.DUP_GROUP_CAP < E.DUP_SCAN_CAP,
          E.DUP_GROUP_CAP)
    check("the threshold is high (0.85 or more) and below 1",
          isinstance(E.DUP_SIMILARITY, float)
          and 0.85 <= E.DUP_SIMILARITY < 1.0, E.DUP_SIMILARITY)
    check("a note too short to compare is never near-matched",
          isinstance(E.DUP_MIN_WORDS, int) and E.DUP_MIN_WORDS >= 6,
          E.DUP_MIN_WORDS)


def main() -> int:
    print(f"note duplicates (DEF-095) - clock fixed at 2026-11-25 21:30 local")
    for fn in (t_every_sentence_reaches_the_lane,
               t_the_capability_answers_say_yes_and_never_cannot,
               t_the_scan_finds_the_three_kinds_and_skips_the_different_ones,
               t_the_answer_states_what_it_covered_and_offers_one_next_step,
               t_a_vault_with_no_duplicates_says_so_and_offers_nothing,
               t_untitled_and_empty_notes_are_never_copies,
               t_a_delete_shaped_sentence_is_still_a_read,
               t_the_scan_is_bounded_and_says_which_notes_it_skipped,
               t_the_group_list_is_capped_and_says_so,
               t_the_delete_is_the_existing_card_with_both_paths_named,
               t_the_hidden_lists_rule_is_kept,
               t_the_constants_are_bounded_numbers,
               t_the_two_copies_are_one_file):
        print()
        print(f"-- {fn.__name__} " + "-" * max(0, 60 - len(fn.__name__)))
        try:
            fn()
        except Exception as exc:            # noqa: BLE001 - a crash IS a finding
            import traceback
            traceback.print_exc()
            FAILED.append(f"{fn.__name__} raised {type(exc).__name__}")
    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    for name in SKIPPED:
        print(f"  SKIPPED (not a pass): {name}")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
