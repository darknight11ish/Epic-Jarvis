"""test_notes_resolve.py - ONE name, ONE note, and the vault's daily settings.

    python -B backend/test_notes_resolve.py

WHY THIS SUITE EXISTS (the architect's Wave 1 ruling, 2026-11-16). `find_name()`
in `jarvis_notes_edit.py` resolved a name, but every note tool had its own idea
of what a name means, and a name that found nothing could end up filed into
today's daily note. The ruling is that `jarvis_notes_edit.py` stays the ONLY
vault writer and that RESOLUTION moves to `backend/jarvis_notes.py`, one place
every note tool routes through:

    exact vault path -> case-insensitive basename -> the note's `aliases:`
    -> the note's own favourite flag -> refuse, listing the candidates

with no daily-note fallback at any point, and with the refusal vocabulary
(`case_variant_exists`, `ambiguous_section` + `candidates`, `content_preexists`)
and the two boolean create options (`create_target_if_missing`,
`reject_if_content_preexists`) rather than a second HTTP surface.

The favourite tier is the one added here on 2026-11-18: "add this to my
favourite note" names no note, and `favorite: true` in a note's front matter was
already real and persisted - it is now what the words SELECT, and no more than
that (no note content in a prompt, no change to a route or a plate).

It also pins the vault's own daily-note settings: `.obsidian/daily-notes.json`
is read for folder, format and template (the behaviour of
liamcain/obsidian-daily-notes-interface's settings.ts/createDailyNote, MIT),
with a template applied only when the daily note is new. A vault with NO such
file - the owner's vault today - behaves exactly as before: YYYY-MM-DD in the
vault's top folder, a new note holding just the owner's words, no settings file
invented.

No model, no network, no real gate: a temp folder with `.obsidian/` in it is
the vault, and every write is `NC.run(plan, approved=True)` on that vault.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes.py", "jarvis_note_capture.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-resolve-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "guardian-home")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = _TMP
FW.LOG_DIR = _TMP
CONFIG = {}
FW.load_framework = lambda: CONFIG
FW.audit_log = lambda e, d: None
sys.modules["jarvis_framework"] = FW

import jarvis_note_capture as NC  # noqa: E402
import jarvis_notes as N  # noqa: E402

DAY = dt.datetime(2026, 11, 16, 9, 0)
TODAY = "2026-11-16"
WORKOUT = "Private & Shared/Workout/Workout Log.md"
WORKOUT_TEXT = """---
aliases:
  - workout log
  - my workout log
pinned: true
---

# Workout Log

## 2026-11-15

- Light cardio.
"""

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def write(vault: Path, rel: str, text: str) -> Path:
    p = vault / rel
    _require_scratch(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return p


def _require_scratch(path: Path) -> None:
    """Refuse to touch anything that is not under THIS suite's scratch folder.

    The owner's real vault lives at whatever `JARVIS_OBSIDIAN_VAULT` or
    `[notes.obsidian]` names. Every test below builds its own vault under
    `_TMP`; this check runs before the first byte is written and before the
    vault is pointed at, so a mis-shaped path can never reach the real one.
    """
    try:
        inside = (os.path.commonpath([os.path.realpath(str(_TMP)),
                                      os.path.realpath(str(path))])
                  == os.path.realpath(str(_TMP)))
    except ValueError:                       # different drives on Windows
        inside = False
    if not inside:
        raise RuntimeError(
            "refusing to use a vault outside this suite's scratch folder: "
            + str(path))


def make_vault(settings=None, with_workout: bool = True,
               with_daily: bool = True, name: str = "") -> Path:
    """A fresh vault, set as THE vault. `settings` becomes daily-notes.json."""
    v = _TMP / (name or ("vault-" + secrets.token_hex(5)))
    _require_scratch(v)
    (v / ".obsidian").mkdir(parents=True)
    if with_workout:
        write(v, WORKOUT, WORKOUT_TEXT)
        write(v, "Private & Shared/Workout.md", "# Workout\n")
    write(v, "Welcome.md", "# Welcome\n\nSome words.\n")
    write(v, "Notes/Gym.md", "# Gym\n")
    if with_daily:
        write(v, TODAY + ".md", "daily sentinel\n")
    if settings is not None:
        (v / ".obsidian" / "daily-notes.json").write_text(
            settings if isinstance(settings, str) else json.dumps(settings),
            encoding="utf-8")
    os.environ[N.OBSIDIAN_VAULT_ENV] = str(v)
    return v


def paths(got: dict) -> list:
    return [str(c.get("path") or "") for c in (got.get("candidates") or [])]


# --------------------------------------------------------------------------
# 1. THE TIERS, EACH ONE SEPARATELY
# --------------------------------------------------------------------------
def t_tier_one_exact_path():
    v = make_vault()
    got = N.resolve_note(WORKOUT)
    check("tier path: the exact vault path resolves",
          got.get("ok") and got.get("tier") == "path"
          and got.get("path") == WORKOUT, got)
    got = N.resolve_note("Private & Shared/Workout/Workout Log")
    check("tier path: the same path without .md resolves at the path tier",
          got.get("ok") and got.get("tier") == "path"
          and got.get("path") == WORKOUT, got)
    got = N.resolve_note("Welcome.md")
    check("tier path: a root note named with its .md is an exact path",
          got.get("ok") and got.get("tier") == "path"
          and got.get("path") == "Welcome.md", got)
    got = N.resolve_note("private & shared/workout/workout log.md")
    check("tier path: a path's CASE is the path's (tier 2 decides it instead)",
          got.get("ok") and got.get("tier") == "basename", got)
    check("tier path: only a path is looked up as a path",
          N.resolve_note("Welcome").get("tier") == "basename",
          N.resolve_note("Welcome"))


def t_tier_two_case_insensitive_basename():
    v = make_vault()
    for name in ("Welcome", "welcome", "WELCOME"):
        got = N.resolve_note(name)
        check(f"tier basename: {name!r} finds Welcome.md, case-insensitively",
              got.get("ok") and got.get("tier") == "basename"
              and got.get("path") == "Welcome.md", got)
    got = N.resolve_note("Gym")
    check("tier basename: a nested note is found by its file name alone",
          got.get("ok") and got.get("tier") == "basename"
          and got.get("path") == "Notes/Gym.md", got)


def t_tier_three_the_notes_own_aliases():
    v = make_vault()
    for name in ("my workout log", "the workout log", "MY WORKOUT LOG"):
        got = N.resolve_note(name)
        check(f"tier alias: {name!r} finds the note by its aliases:",
              got.get("ok") and got.get("tier") == "alias"
              and got.get("path") == WORKOUT
              and sorted(got.get("aliases") or []) == ["my workout log", "workout log"],
              got)
    got = N.resolve_note("workout log")
    check("tier basename: 'workout log' is the file's own name, so tier 2 wins",
          got.get("ok") and got.get("tier") == "basename"
          and got.get("path") == WORKOUT, got)
    # The alias tier is only reached when the file-name tier found nothing.
    got = N.resolve_note("Workout Log")
    check("tier alias: a real file name resolves at the BASENAME tier first",
          got.get("ok") and got.get("tier") == "basename", got)
    # A note that never claimed the name does not answer to it.
    write(v, "Notes/Gym.md", "---\naliases:\n  - the gym\n---\n\n# Gym\n")
    got = N.resolve_note("my workout log")
    check("tier alias: the alias list is the note's own, not a guess",
          got.get("ok") and got.get("path") == WORKOUT, got)
    check("tier alias: a different note's alias is not borrowed",
          N.resolve_note("the gym").get("path") == "Notes/Gym.md",
          N.resolve_note("the gym"))


# --------------------------------------------------------------------------
# 2. REFUSALS: CANDIDATES, AMBIGUITY, AND NEVER THE DAILY NOTE
# --------------------------------------------------------------------------
def t_refusal_lists_the_candidates():
    v = make_vault()
    got = N.resolve_note("garden bucket")
    check("refuse: an unknown name is not_found",
          got.get("ok") is False and got.get("code") == "not_found", got)
    check("refuse: ... and it names no file", not got.get("path"), got)
    got = N.resolve_note("the workout")
    check("refuse: a near name is REFUSED, never auto-picked",
          got.get("ok") is False and got.get("code") == "not_found", got)
    check("refuse: ... and the candidates are listed",
          WORKOUT in paths(got)
          and "Private & Shared/Workout.md" in paths(got), paths(got))
    check("refuse: ... with a plain sentence naming the closest",
          "closest" in str(got.get("reason")) and WORKOUT in str(got.get("reason")),
          got.get("reason"))


def t_two_matches_ask_and_name_both():
    v = make_vault()
    write(v, "Other/Welcome.md", "# Other welcome\n")
    got = N.resolve_note("Welcome")
    check("ambiguous: two files with that name are an ambiguous_section",
          got.get("ok") is False and got.get("code") == "ambiguous_section", got)
    check("ambiguous: ... and BOTH candidates are named",
          sorted(paths(got)) == ["Other/Welcome.md", "Welcome.md"], paths(got))
    check("ambiguous: ... and nothing is chosen", not got.get("path"), got)
    write(v, "Other/Other log.md",
          "---\naliases:\n  - my workout log\n---\n\n# Other\n")
    got = N.resolve_note("my workout log")
    check("ambiguous: two notes claiming one alias also ask",
          got.get("ok") is False and got.get("code") == "ambiguous_section"
          and sorted(paths(got)) == ["Other/Other log.md", WORKOUT], got)
    check("ambiguous: ... and the sentence names them",
          "Other/Other log.md" in str(got.get("reason"))
          and WORKOUT in str(got.get("reason")), got.get("reason"))


def t_no_daily_note_fallback():
    v = make_vault(with_workout=False)          # only Welcome, Gym and the daily
    got = N.resolve_note("my workout log")
    check("no fallback: a name that is not there is a refusal",
          got.get("ok") is False and got.get("code") == "not_found", got)
    check("no fallback: ... and today's daily note is not the answer",
          not str(got.get("path") or "").endswith(TODAY + ".md")
          and (TODAY + ".md") not in paths(got), got)
    check("no fallback: ... the resolver has no daily-note branch at all",
          "daily" not in " ".join(N.RESOLVE_TIERS).lower(), N.RESOLVE_TIERS)
    before = (v / (TODAY + ".md")).read_text(encoding="utf-8")
    check("no fallback: ... and resolving wrote nothing",
          (v / (TODAY + ".md")).read_text(encoding="utf-8") == before)


# --------------------------------------------------------------------------
# 2b. THE FAVOURITE FLAG: a property the owner set, read as the resolver's LAST
#     tier (2026-11-18)
# --------------------------------------------------------------------------
# The owner's own sentence is "add this to my favourite note". The flag is real
# and persisted - a create writes `favorite: true`, and a carded `set_property`
# edit writes it - but until this case existed nothing read it for anything
# except one yes/no answer ("is my X note favourited?"). These cases make it
# SELECT a note, through the existing tiers: the flag is a DESCRIPTION of a
# note, so it is asked only after every name tier has said no.
WORKOUT_TITLE = "Workout Log"
FAVOURITE_NOTE_TEXT = (
    "---\n"
    "aliases:\n"
    "  - workout log\n"
    "  - my workout log\n"
    "favorite: true\n"
    "---\n\n# Workout Log\n\n- Light cardio.\n"
)


def t_favourite_one_note_resolves_and_says_its_name():
    v = make_vault()
    write(v, WORKOUT, FAVOURITE_NOTE_TEXT)
    before = (v / WORKOUT).read_bytes()
    got = N.resolve_note("my favourite note")
    check("favourite: one flagged note resolves, at its own tier",
          got.get("ok") and got.get("tier") == "favourite"
          and got.get("path") == WORKOUT, got)
    check("favourite: ... and the answer says which note it picked",
          WORKOUT_TITLE in str(got.get("said") or "")
          and "favourite" in str(got.get("said")), got.get("said"))
    full = os.path.realpath(str(got.get("full") or ""))
    check("favourite: ... the pick is a real file under THIS test's vault",
          os.path.commonpath([full, os.path.realpath(str(v))])
          == os.path.realpath(str(v)) and os.path.isfile(full), full)
    check("favourite: ... and reading it changed nothing",
          (v / WORKOUT).read_bytes() == before)
    for phrase in ("favourite", "my favourite", "my favorite note",
                   "the favourite notes", "my favourites"):
        got = N.resolve_note(phrase)
        check(f"favourite: {phrase!r} is the same pick",
              got.get("ok") and got.get("tier") == "favourite"
              and got.get("path") == WORKOUT, got)
    # A hand-written British key is the flag too, exactly like Jarvis's US one.
    write(v, WORKOUT, "---\nfavourite: true\n---\n\n# Workout Log\n")
    got = N.resolve_note("my favourite note")
    check("favourite: a hand-written `favourite: true` counts too",
          got.get("ok") and got.get("path") == WORKOUT, got)
    # A hidden folder is never read by `_vault_notes`, so its note is never a
    # candidate: the one real favourite stays the only pick.
    write(v, WORKOUT, FAVOURITE_NOTE_TEXT)
    write(v, ".trash/Hidden.md", "---\nfavorite: true\n---\n\n# Hidden\n")
    got = N.resolve_note("my favourite note")
    check("favourite: a note in a hidden folder is never a candidate",
          got.get("ok") and got.get("path") == WORKOUT, got)
    # A `favorite:` line is a PROPERTY only inside a front matter that CLOSES;
    # without the second `---` Obsidian reads it as body text, and so does this.
    write(v, WORKOUT, "---\nfavorite: true\n\n# Workout Log\n")
    got = N.resolve_note("my favourite note")
    check("favourite: an UNCLOSED front matter is not a favourite",
          got.get("ok") is False and got.get("code") == "not_found", got)
    # The FIRST `favorite:` line wins, as YAML reads it - a later `true` cannot
    # overrule an earlier `false`.
    write(v, WORKOUT, "---\nfavorite: false\nfavorite: true\n---\n\n# Workout\n")
    got = N.resolve_note("my favourite note")
    check("favourite: the first `favorite:` line wins over a later one",
          got.get("ok") is False and got.get("code") == "not_found", got)


def t_favourite_three_notes_list_and_ask():
    v = make_vault()
    for rel, text in ((WORKOUT, FAVOURITE_NOTE_TEXT),
                      ("Notes/Gym.md", "---\nfavorite: true\n---\n\n# Gym\n"),
                      ("Welcome.md", "---\nfavorite: true\n---\n\n# Welcome\n")):
        write(v, rel, text)
    before = {rel: (v / rel).read_bytes()
              for rel in (WORKOUT, "Notes/Gym.md", "Welcome.md")}
    got = N.resolve_note("my favourite note")
    check("favourite: three flagged notes ASK, never guess",
          got.get("ok") is False and got.get("code") == "ambiguous_section", got)
    check("favourite: ... every candidate is listed",
          sorted(paths(got)) == sorted([WORKOUT, "Notes/Gym.md", "Welcome.md"]),
          paths(got))
    check("favourite: ... and nothing is chosen", not got.get("path"), got)
    check("favourite: ... in the resolver's own two-or-more question words",
          "3 notes" in str(got.get("reason"))
          and "Say the folder and the note's name, so one is chosen."
          in str(got.get("reason")), got.get("reason"))
    check("favourite: ... and no note was written to",
          all((v / rel).read_bytes() == data for rel, data in before.items()))


def t_favourite_none_answers_honestly_and_creates_nothing():
    v = make_vault()                  # Welcome, Gym, the daily note: none flagged
    files_before = sorted(str(p.relative_to(v)) for p in v.rglob("*"))
    got = N.resolve_note("my favourite note")
    check("favourite: no flagged note is a plain not_found",
          got.get("ok") is False and got.get("code") == "not_found", got)
    check("favourite: ... it says plainly that no note is a favourite",
          "No note in your vault is marked as a favourite"
          in str(got.get("reason")), got.get("reason"))
    check("favourite: ... it names what it looked for, and the words used",
          "my favourite note" in str(got.get("reason"))
          and "nothing was created" in str(got.get("reason")),
          got.get("reason"))
    check("favourite: ... it does not fall through to a fuzzy match",
          not got.get("candidates") and not got.get("path"), got)
    for phrase in ("favourite", "my favourite", "my favorites"):
        got = N.resolve_note(phrase)
        check(f"favourite: {phrase!r} with nothing flagged is refused",
              got.get("ok") is False and got.get("code") == "not_found", got)
    # A create-shaped lookup must not turn the description into a new note.
    target = N.create_target("my favourite note", create_target_if_missing=True)
    check("favourite: a create lookup is refused, not turned into a new note",
          target.get("ok") is False and target.get("code") == "not_found"
          and target.get("create") is not True, target)
    check("favourite: ... and nothing at all was created",
          sorted(str(p.relative_to(v)) for p in v.rglob("*")) == files_before)


def t_favourite_never_overrides_a_named_note():
    v = make_vault()
    write(v, WORKOUT, FAVOURITE_NOTE_TEXT)          # the only favourite
    got = N.resolve_note("Gym")
    check("favourite: an explicit file name still resolves by its name",
          got.get("ok") and got.get("tier") == "basename"
          and got.get("path") == "Notes/Gym.md", got)
    got = N.resolve_note("Welcome.md")
    check("favourite: an explicit path still resolves by its path",
          got.get("ok") and got.get("tier") == "path"
          and got.get("path") == "Welcome.md", got)
    got = N.resolve_note("my favourite note")
    check("favourite: the description still picks the flagged note",
          got.get("ok") and got.get("tier") == "favourite"
          and got.get("path") == WORKOUT, got)
    # A note that explicitly CLAIMS the word as an alias is a name, and a name
    # tier is asked before the flag tier, always.
    write(v, "Notes/Other.md", "---\naliases:\n  - favourite\n---\n\n# Other\n")
    got = N.resolve_note("my favourite")
    check("favourite: a note that claims the word as an ALIAS wins over the flag",
          got.get("ok") and got.get("tier") == "alias"
          and got.get("path") == "Notes/Other.md", got)
    # A note literally CALLED Favourite is a name too, and names win.
    write(v, "Favourite.md", "# Favourite\n")
    got = N.resolve_note("Favourite")
    check("favourite: a note NAMED Favourite resolves at the basename tier",
          got.get("ok") and got.get("tier") == "basename"
          and got.get("path") == "Favourite.md", got)
    got = N.resolve_note("Favourite.md")
    check("favourite: ... and by its exact path when the path is said",
          got.get("ok") and got.get("tier") == "path"
          and got.get("path") == "Favourite.md", got)
    # A NAME THAT LOOKS LIKE A PATH is a file name, never the flag: a create of
    # `Favourite.md` still proposes that new note even though a favourite exists.
    any_favourite = make_vault(name="v-any-fav-" + secrets.token_hex(4))
    write(any_favourite, WORKOUT, FAVOURITE_NOTE_TEXT)
    got = N.resolve_note("Favourite.md", vault=any_favourite)
    check("favourite: a path-like name never reaches the flag tier",
          got.get("ok") is False and got.get("code") == "not_found", got)
    target = N.create_target("Favourite.md", create_target_if_missing=True,
                             vault=any_favourite)
    check("favourite: ... so creating a note called Favourite.md still works",
          target.get("ok") and target.get("create") is True
          and target.get("path") == "Favourite.md", target)


def t_favourite_tier_does_not_fire_on_a_plain_note_question():
    v = make_vault()
    write(v, WORKOUT, FAVOURITE_NOTE_TEXT)
    got = N.resolve_note("Welcome")
    check("favourite: a plain note question still resolves by its name",
          got.get("ok") and got.get("tier") == "basename"
          and got.get("path") == "Welcome.md", got)
    for phrase in ("garden bucket", "favourite colour", "the workout"):
        got = N.resolve_note(phrase)
        check(f"favourite: {phrase!r} is never answered with the favourite",
              got.get("ok") is False and not got.get("path")
              and got.get("tier") != "favourite", got)
    got = N.resolve_note("favourite colour")
    check("favourite: ... a phrase that merely mentions a favourite refuses",
          got.get("code") == "not_found"
          and 'No note in your vault is called "favourite colour".'
          in str(got.get("reason")), got.get("reason"))
    check("favourite: ... and the tier is stated last in the resolver's order",
          N.RESOLVE_TIERS == ("path", "basename", "alias", "favourite"),
          N.RESOLVE_TIERS)


# --------------------------------------------------------------------------
# 3. THE CREATE VOCABULARY AND THE TWO BOOLEAN OPTIONS
# --------------------------------------------------------------------------
def t_content_preexists_and_the_two_options():
    v = make_vault()
    got = N.create_target("Welcome")
    check("create: an existing note with content is content_preexists",
          got.get("ok") is False and got.get("code") == "content_preexists", got)
    check("create: ... the default rejects it",
          N.create_target("Welcome", reject_if_content_preexists=True).get("code")
          == "content_preexists")
    check("create: ... and False still never replaces content",
          N.create_target("Welcome", reject_if_content_preexists=False).get("code")
          == "content_preexists")
    write(v, "Empty.md", "")
    got = N.create_target("Empty", reject_if_content_preexists=False)
    check("create: an EMPTY existing note may be filled when the option is False",
          got.get("ok") and got.get("existing_empty") and got.get("create") is False,
          got)
    check("create: ... but the default still refuses it",
          N.create_target("Empty").get("code") == "content_preexists")
    got = N.create_target("Brand New")
    check("create: a missing name is refused by default (nothing is created)",
          got.get("ok") is False and got.get("code") == "not_found", got)
    got = N.create_target("Brand New", create_target_if_missing=True)
    check("create: create_target_if_missing=True proposes the one new path",
          got.get("ok") and got.get("create") is True
          and got.get("path") == "Brand New.md", got)


def t_case_variant_exists():
    v = make_vault()
    got = N.create_target("Notes/gym.md", create_target_if_missing=True)
    check("case: a name that differs only by case is case_variant_exists",
          got.get("ok") is False and got.get("code") == "case_variant_exists", got)
    check("case: ... and it names the existing file",
          got.get("path") == "Notes/Gym.md" and paths(got) == ["Notes/Gym.md"], got)
    check("case: ... so Windows cannot silently write the other note",
          "capital letters" in str(got.get("reason")), got.get("reason"))
    got = N.create_target("Notes/Brand New.md", create_target_if_missing=True)
    check("case: a genuinely new path in that folder is still allowed",
          got.get("ok") and got.get("create") is True
          and got.get("path") == "Notes/Brand New.md", got)
    got = N.create_target("Other/Gym.md", create_target_if_missing=True)
    check("case: a named folder is a new note even when that name lives elsewhere",
          got.get("ok") and got.get("create") is True
          and got.get("path") == "Other/Gym.md", got)
    got = N.create_target("Notes/Gym.txt", create_target_if_missing=True)
    check("case: a different extension is not a case collision",
          got.get("ok") and got.get("create") is True
          and got.get("path") == "Notes/Gym.txt", got)
    got = N.create_target("../escape", create_target_if_missing=True)
    check("case: a name that climbs out of the vault is refused",
          got.get("ok") is False, got)
    write(v, "Notes/Readme.txt", "plain text\n")
    got = N.resolve_note("Notes/Readme.txt")
    check("case: a .txt note is resolved as a path and titled without its suffix",
          got.get("ok") and got.get("tier") == "path"
          and got.get("title") == "Readme", got)


# --------------------------------------------------------------------------
# 4. THE VAULT'S DAILY-NOTE SETTINGS, AND THE ABSENT FILE
# --------------------------------------------------------------------------
def t_absent_daily_notes_json_is_exactly_the_old_behaviour():
    v = make_vault(with_daily=False)
    settings, why = NC.daily_settings(v)
    check("absent: no daily-notes.json means the documented defaults",
          settings == {"folder": "", "format": "YYYY-MM-DD", "template": ""}
          and why == "", (settings, why))
    check("absent: no template is read", NC.daily_template(v) == ("", ""),
          NC.daily_template(v))
    p = NC.plan("obsidian", "call the plumber", now=DAY)
    check("absent: the daily note is YYYY-MM-DD in the vault's top folder",
          p.file == os.path.join(os.path.realpath(str(v)), TODAY + ".md")
          and not p.reason_empty, repr(p))
    check("absent: the plan names no template and gives no template reason",
          p.template == "" and p.template_why == "", (p.template, p.template_why))
    card = NC.describe(p)
    check("absent: the card says no daily note template is set",
          "not there yet" in card and "No daily note template is set" in card, card)
    check("absent: no settings file was invented before the write",
          not (v / ".obsidian" / "daily-notes.json").exists())
    out = NC.run(p, approved=True)
    check("absent: the new note holds just the owner's words",
          out.get("ok") and (v / (TODAY + ".md")).read_text(encoding="utf-8")
          == "call the plumber\n", out)
    check("absent: ... and still no settings file was invented",
          not (v / ".obsidian" / "daily-notes.json").exists())


def t_daily_note_template_is_applied_when_the_settings_name_one():
    v = make_vault({"folder": "Daily", "format": "YYYY-MM-DD",
                    "template": "Templates/Daily.md"}, with_daily=False)
    write(v, "Templates/Daily.md", "# Daily\n\nBody\n")
    p = NC.plan("obsidian", "did 20 squats", now=DAY)
    check("template: the settings' folder and format still choose the file",
          p.file == os.path.join(os.path.realpath(str(v)), "Daily", TODAY + ".md"),
          repr(p))
    check("template: the plan carries the relative template path",
          p.template == "Templates/Daily.md" and p.template_why == "",
          (p.template, p.template_why))
    card = NC.describe(p)
    check("template: the card names the template before the write",
          "Templates/Daily.md" in card and "is made from your daily note template" in card,
          card)
    out = NC.run(p, approved=True)
    got = (v / "Daily" / (TODAY + ".md")).read_text(encoding="utf-8")
    check("template: the new daily note is the template, then the note",
          out.get("ok") and got == "# Daily\n\nBody\n\ndid 20 squats\n", repr(got))
    check("template: ... and the write says which template it used",
          out.get("template") == "Templates/Daily.md", out)
    # A second capture the same day appends under it and applies no template again.
    p2 = NC.plan("obsidian", "and 10 push-ups", now=DAY)
    NC.run(p2, approved=True)
    got = (v / "Daily" / (TODAY + ".md")).read_text(encoding="utf-8")
    check("template: an existing daily note only gets the new words",
          got == "# Daily\n\nBody\n\ndid 20 squats\n\nand 10 push-ups\n", repr(got))


def t_missing_or_unsafe_templates_are_said_plainly():
    cases = [
        ({"template": "Templates/Nope.md"}, "not in your vault"),
        ({"template": "../outside"}, "goes outside"),
        ({"template": ".trash/x"}, "hidden folder"),
    ]
    for settings, part in cases:
        v = make_vault(settings, with_daily=False,
                       name="v-" + secrets.token_hex(4))
        p = NC.plan("obsidian", "hello", now=DAY)
        check(f"template: {settings['template']!r} is not applied ({part})",
              p.template == "" and part in p.template_why, p.template_why)
        card = NC.describe(p)
        check(f"template: ... and the card says why ({part})",
              "not applied" in card and part in card, card)
        out = NC.run(p, approved=True)
        check(f"template: ... the note is made with just the words ({part})",
              out.get("ok") and (v / (TODAY + ".md")).read_text(encoding="utf-8")
              == "hello\n", out)


def t_periodic_notes_still_wins_when_it_is_on():
    """A vault that lets Periodic Notes name the note is still refused."""
    v = make_vault({"format": "YYYY-MM-DD"})
    (v / ".obsidian" / "community-plugins.json").write_text(
        '["dataview", "periodic-notes"]', encoding="utf-8")
    p = NC.plan("obsidian", "x", now=DAY)
    check("settings: Periodic Notes turned on is still refused",
          "Periodic Notes" in p.reason_empty, p.reason_empty)


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
TESTS = [
    t_tier_one_exact_path,
    t_tier_two_case_insensitive_basename,
    t_tier_three_the_notes_own_aliases,
    t_refusal_lists_the_candidates,
    t_two_matches_ask_and_name_both,
    t_no_daily_note_fallback,
    t_favourite_one_note_resolves_and_says_its_name,
    t_favourite_three_notes_list_and_ask,
    t_favourite_none_answers_honestly_and_creates_nothing,
    t_favourite_never_overrides_a_named_note,
    t_favourite_tier_does_not_fire_on_a_plain_note_question,
    t_content_preexists_and_the_two_options,
    t_case_variant_exists,
    t_absent_daily_notes_json_is_exactly_the_old_behaviour,
    t_daily_note_template_is_applied_when_the_settings_name_one,
    t_missing_or_unsafe_templates_are_said_plainly,
    t_periodic_notes_still_wins_when_it_is_on,
]


def main():
    print("=" * 74)
    print("jarvis_notes.resolve_note + the vault's daily-note settings")
    print("=" * 74)
    for test in TESTS:
        print()
        print("--", test.__name__, "-" * max(0, 60 - len(test.__name__)))
        try:
            test()
        except Exception:                                   # noqa: BLE001
            FAILED.append(test.__name__ + " (exception)")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP {len(SKIPPED)}")
    for name in FAILED:
        print("  FAIL:", name)
    shutil.rmtree(_TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
