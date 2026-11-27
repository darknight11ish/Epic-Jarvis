#!/usr/bin/env python3
"""test_awareness_honesty.py - "cannot read it" is not "none switched on",
and the wake phrase is read from this PC, not from the catalogue's old title.

    python3 backend/test_awareness_honesty.py

WHAT THIS PROVES, and why it exists (2026-11-26, the awareness audit's H2):

  - A FAILED SETTINGS READ IS AN UNKNOWN, NEVER A ZERO. `jarvis_asks_first.
    tools_enabled_set()` used to answer `set()` for a read that failed - no
    `jarvis_framework` module, no `jarvis-framework.toml`, no TOML reader, or
    a file that could not be parsed - so the tool answers built from it said
    "0 switched on ... your settings file names no tool" about a file nothing
    had read. The portrait's own docstring has always promised the opposite
    (`jarvis_self_portrait.py:642-644`: "None (never 0) when the settings file
    cannot be read"). The new `tools_enabled_read()` keeps that promise:
    `names` is None exactly when the read failed, and `why` says which read,
    in words.
  - THE ANSWER A PERSON HEARS SAYS WHICH ONE IT IS. Every tool answer that
    reads the portrait - the count, the full list, the switched-off list, one
    category, the group list, the settings group - is driven here through the
    real matcher and must say "cannot read", must not say "0 switched on",
    must not say "names no tool", and must not mark one tool "off" when it
    knows nothing. The sentences themselves live in `jarvis_quick.py` and are
    not changed by this work; what changed is the value they are given.
  - "ZERO" REMAINS AVAILABLE FOR THE CASE WHERE IT IS TRUE. A settings file
    that really was read and names no tool still says "names no tool". A file
    that names one tool, and the shipped `jarvis-framework.toml`, still count
    exactly the names in the file - the expected count is parsed out of the
    file here, never typed, so a template edit moves both sides together.
  - A DAMAGED FILE IS SAID AS DAMAGED. `load_framework()` returns `{}` both
    for an empty file and for one it could not parse, so the reader proves an
    empty config against the file itself; this suite drives a corrupt TOML and
    requires "could not be parsed" rather than "no tool".
  - THE WAKE PHRASE IS READ FROM THIS PC (the audit's H3). The catalogue row's
    title is a typed phrase ("Say \"Hey Jarvis\""), and an existing PC is never
    re-pointed, so `jarvis_feature_guide.display_title()` reads `[voice]
    wake_phrase` at answer time. This suite drives three real files: the
    shipped template must say "Hey Atlas", a copy left on `hey_jarvis` must
    say "Hey Jarvis", and a file with no `wake_phrase` line (or no settings
    module at all) must say it cannot read the phrase and name neither. It also
    pins that MATCHING still uses the catalogue's own title, so a live read
    cannot move which row a question reaches.
  - THE SUITE READS THE CHECKOUT. `_where.require_shipped` is called first, so
    a run with `JARVIS_BACKEND` still set to the owner's live folder refuses
    (NOT-TESTABLE) instead of passing against the installed copy. The config
    folder and the databases are throwaway temp paths, and no intent driven
    here writes anything: every one is in `jarvis_quick.READ_ONLY_INTENTS`.

The two answers this work does NOT fix are pinned by name so a future lane
cannot think this suite covers them (they need `jarvis_quick.py`, which a
concurrent pull request is editing): `"how do I activate the wake word"` is
built in `jarvis_quick._run_wake_word_howto` from the catalogue row directly
and still says "Hey Jarvis"; and `"can you empty the trash"` still reaches
`note_empty_trash` with `ask=False`. They are reported, not asserted here - a
check that the wrong answer stays wrong would block the fix.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-awareness-honesty-"))
# Before anything imports jarvis_framework or jarvis_memory: their config dir
# and database paths are read once, at import.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_asks_first.py", "jarvis_self_portrait.py",
                "jarvis_quick.py", "jarvis_feature_guide.py")
# The framework module the real backend ships beside these modules lives in
# `backend/rebuilt/` in a checkout; on the path, `jarvis_asks_first.fw` is the
# real module, exactly as on an install. Without it every read here would be
# "no reader on this PC" and this suite could not prove the OTHER half.
sys.path.append(str(HERE / "rebuilt"))

import jarvis_asks_first as ASK  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_self_portrait as SP  # noqa: E402

PASSED, FAILED = [], []

#: The five tool answers that report an ON/OFF count, and so have to say
#: "cannot read" instead of a number. Each one is driven through the real
#: matcher: the intent name is pinned, because a neighbour swallowing the
#: sentence is the failure this project keeps paying for.
COUNTED_TOOL_ANSWERS = (
    ("what tools do you have", "tools_inventory"),
    ("list all of your tools", "tools_list_all"),
    ("which tools are switched off", "tools_switched_off"),
    ("which github tools do you have", "tools_in_category"),
    ("what groups of tools do you have", "tools_categories"),
)
#: The sixth reads the same inventory but answers an ATTRIBUTE (which tools can
#: change a setting), so it has no count to get wrong. It already marks nothing
#: when the state is unknown; it does not say why, and that sentence lives in
#: `jarvis_quick._run_tools_settings` - a concurrent pull request's file - so
#: this suite pins the honest half it can pin and does not demand the missing
#: sentence here. A future lane that adds it will not break this check.
ATTRIBUTE_TOOL_ANSWER = ("what tools can change my settings", "tools_settings")


class _Sched:
    def mark_command(self, text):
        pass


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def answer(words):
    return Q.answer(words, sched=_Sched())


# ---------------------------------------------------------------------------
#   A settings file in a temp folder, read the way the real one is read
# ---------------------------------------------------------------------------


def _write_toml(text: str) -> str:
    """Write `text` where the reader looks, and make the cache re-read it."""
    path = _TMP / "config" / "jarvis-framework.toml"
    path.write_text(text, encoding="utf-8")
    os.environ["JARVIS_FRAMEWORK_TOML"] = str(path)
    if ASK.fw is not None:
        ASK.fw.reload_framework()
    return str(path)


def _shipped_toml_enabled() -> set:
    """The names `[tools].enabled` really holds in the SHIPPED template."""
    import tomllib
    raw = (HERE / "rebuilt" / "jarvis-framework.toml").read_bytes()
    return set((tomllib.loads(raw.decode("utf-8-sig")).get("tools") or {})
               .get("enabled") or ())


def _with_no_reader(fn):
    """Run `fn` with `jarvis_asks_first.fw` absent, the checkout's own state."""
    had = ASK.fw
    ASK.fw = None
    try:
        return fn()
    finally:
        ASK.fw = had
        if had is not None:
            had.reload_framework()


def _restore_toml_env(had):
    if had is None:
        os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
    else:
        os.environ["JARVIS_FRAMEWORK_TOML"] = had
    if ASK.fw is not None:
        ASK.fw.reload_framework()


# ---------------------------------------------------------------------------
#   1. The read itself: unknown, never an empty set
# ---------------------------------------------------------------------------


def a_failed_read_is_unknown_and_never_an_empty_set():
    Q._MEASURED_FIXTURE = None          # the suite seam must not hide the read

    def drive():
        return ASK.tools_enabled_read(), ASK.tools_enabled_set(), SP.tool_inventory()

    read, as_set, inv = _with_no_reader(drive)
    check("no settings reader: the read says 'cannot read', not a set",
          read.get("names") is None, read)
    check("... and its why names the missing reader, in plain words",
          "not on this PC" in str(read.get("why") or ""), read.get("why"))
    check("the set-only view still answers an empty set (its callers can hold one)",
          as_set == set(), as_set)
    check("the portrait's enabled count is None, never 0",
          inv.get("enabled") is None and inv.get("enabled_names") == [], inv)
    check("... and its why says the file could not be read and the answer is unknown",
          "could not be read" in str(inv.get("why") or "")
          and "unknown" in str(inv.get("why") or ""), inv.get("why"))
    counted = SP.counts({"tools": inv})
    check("the portrait's own count is unknown too, never 0",
          counted["tools"] is None, counted["tools"])
    check("... and the refresh sentence says unknown, not zero",
          "unknown" in SP.refresh_sentence({}, counted),
          SP.refresh_sentence({}, counted))

    def no_file():
        had = ASK.fw.config_path
        ASK.fw.config_path = lambda: None
        try:
            return ASK.tools_enabled_read()
        finally:
            ASK.fw.config_path = had

    read = no_file()
    check("no settings file found: names is None and the why says which read",
          read.get("names") is None
          and "was found" in str(read.get("why") or ""), read)


# ---------------------------------------------------------------------------
#   2. The answers a person hears: "cannot read", never "0 ... names no tool"
# ---------------------------------------------------------------------------


def the_tool_answers_say_the_read_failed():
    def drive():
        rows = []
        for sentence, wanted in COUNTED_TOOL_ANSWERS:
            got = Q.match(sentence)
            res = answer(sentence)
            rows.append((sentence, wanted,
                         getattr(got, "name", None),
                         str(res.reply) if res is not None else ""))
        return rows

    for sentence, wanted, intent, reply in _with_no_reader(drive):
        check(f"{sentence!r} still reaches {wanted}",
              intent == wanted, f"got {intent!r}")
        check(f"... {wanted}: the answer says it cannot read the settings",
              "cannot read" in reply, reply[:220])
        check(f"... {wanted}: it never reports a count it never measured",
              "0 switched on" not in reply
              and "None of them are switched on" not in reply
              and "of my 90 built-in tools are switched off" not in reply,
              reply[:220])
        check(f"... {wanted}: it does not claim the file names no tool",
              "names no tool" not in reply, reply[:220])
        check(f"... {wanted}: it marks no tool on and marks no tool off",
              " — on" not in reply and " — off" not in reply, reply[:220])

    sentence, wanted = ATTRIBUTE_TOOL_ANSWER

    def drive_one():
        got = Q.match(sentence)
        res = answer(sentence)
        return (getattr(got, "name", None),
                str(res.reply) if res is not None else "")

    intent, reply = _with_no_reader(drive_one)
    check(f"{sentence!r} still reaches {wanted}", intent == wanted,
          f"got {intent!r}")
    check("... the attribute answer marks nothing on or off rather than guessing",
          " — on" not in reply and " — off" not in reply, reply[:220])


# ---------------------------------------------------------------------------
#   3. The cases where a number IS a fact
# ---------------------------------------------------------------------------


def a_readable_file_is_counted_from_the_file():
    Q._MEASURED_FIXTURE = None
    had = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        _write_toml('[tools]\nenabled = ["web_search"]\n')
        read = ASK.tools_enabled_read()
        inv = SP.tool_inventory()
        check("a readable file naming one tool: the read answers that one name",
              read.get("names") == {"web_search"} and read.get("why") == "", read)
        check("... and the set-only view agrees with it",
              ASK.tools_enabled_set() == {"web_search"},
              ASK.tools_enabled_set())
        check("... the portrait counts ONE, not zero and not unknown",
              inv.get("enabled") == 1 and inv.get("enabled_names") == ["web_search"],
              inv)
        reply = answer("what tools do you have").reply
        check("... and the answer a person hears names the one tool",
              "1 of them are switched on" in reply and "Web search" in reply,
              reply[:220])

        expected = _shipped_toml_enabled()
        _write_toml((HERE / "rebuilt" / "jarvis-framework.toml")
                    .read_text(encoding="utf-8"))
        read = ASK.tools_enabled_read()
        inv = SP.tool_inventory()
        check("the SHIPPED template's enabled list is read name for name",
              read.get("names") == expected, (read.get("names"), expected))
        check("... the portrait counts exactly the names the file holds",
              inv.get("enabled") == len(expected)
              and sorted(inv.get("enabled_names") or []) == sorted(expected),
              (inv.get("enabled"), len(expected)))
        reply = answer("what tools do you have").reply
        check("... and the answer names that same count",
              f"{len(expected)} of them are switched on" in reply,
              reply[:220])

        _write_toml('[tools]\nenabled = []\n')
        read = ASK.tools_enabled_read()
        inv = SP.tool_inventory()
        check("a readable file that names no tool is a real EMPTY set",
              read.get("names") == set() and read.get("why") == "", read)
        check("... the portrait counts 0, because the file really was read",
              inv.get("enabled") == 0, inv)
        reply = answer("what tools do you have").reply
        check("... and only THEN does the answer say the file names no tool",
              "names no tool" in reply, reply[:220])
    finally:
        _restore_toml_env(had)


# ---------------------------------------------------------------------------
#   4. A file that exists but cannot be parsed is "cannot read"
# ---------------------------------------------------------------------------


def a_damaged_file_is_said_as_damaged():
    Q._MEASURED_FIXTURE = None
    had = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        _write_toml('[tools\nenabled = [\n')
        read = ASK.tools_enabled_read()
        inv = SP.tool_inventory()
        check("a damaged file: names is None, never 0",
              read.get("names") is None, read)
        check("... and the why says it could not be PARSED, not 'no tool'",
              "parsed" in str(read.get("why") or ""), read.get("why"))
        check("... the portrait says unknown, with the reason",
              inv.get("enabled") is None and "could not be read" in inv.get("why"),
              inv)
        reply = answer("what tools do you have").reply
        check("... and the answer says it cannot read, never a count",
              "cannot read" in reply and "names no tool" not in reply,
              reply[:220])
    finally:
        _restore_toml_env(had)


# ---------------------------------------------------------------------------
#   5. The wake phrase is read from THIS PC, not from a typed catalogue title
# ---------------------------------------------------------------------------


def _shipped_phrase() -> str:
    """The `[voice] wake_phrase` the shipped template really sets."""
    import tomllib
    raw = (HERE / "rebuilt" / "jarvis-framework.toml").read_bytes()
    return str((tomllib.loads(raw.decode("utf-8-sig")).get("voice") or {})
               .get("wake_phrase") or "")


def the_wake_answer_reads_the_live_phrase():
    Q._MEASURED_FIXTURE = None
    had = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        shipped = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(
            encoding="utf-8")
        phrase = _shipped_phrase()
        check("the shipped template really sets a wake phrase", bool(phrase), phrase)
        row = FG.row_by_id(FG.WAKE_ROW)
        catalogue_title = str(row["title"])

        # MATCHING is the catalogue's own word, not the live read: the row is
        # found the same way whether the PC listens for Atlas or Jarvis.
        got = Q.match("what is my wake word")
        check("the question still reaches the catalogue's wake-word row",
              got is not None and got.name == "feature_explain"
              and got.f.get("id") == "wake-word",
              (got.name if got else None, got.f if got else None))

        # A fresh install: the shipped setting differs from the list's title,
        # so the answer must carry BOTH - the title (so the row still names
        # itself on any PC, settings file or not) and the live phrase.
        _write_toml(shipped)
        live = FG.wake_phrase_title(phrase)
        title = FG.display_title(row)
        check("a fresh PC's wake row keeps the catalogue's own title",
              catalogue_title in title, (title, catalogue_title))
        check("... and adds the SHIPPED phrase as a second clause",
              live in title and title != catalogue_title, (title, live))
        first = answer("what is my wake word").reply.splitlines()[0]
        check("... and the answer a person hears opens with that",
              first == title + ".", first)
        first = answer("is the wake word on").reply.splitlines()[0]
        check("... and so does 'is the wake word on'",
              first.startswith(title), first)
        first = answer("how do I change the wake word").reply.splitlines()[0]
        check("... and 'how do I change the wake word'",
              first.startswith(title), first)

        # An existing PC left on hey_jarvis: the title already names its phrase,
        # so the answer is the catalogue title alone - no redundant clause.
        _write_toml(shipped.replace(f'wake_phrase = "{phrase}"',
                                    'wake_phrase = "hey_jarvis"'))
        title = FG.display_title(row)
        first = answer("what is my wake word").reply.splitlines()[0]
        check("a PC left on hey_jarvis is told hey_jarvis, with no stale clause",
              title == catalogue_title and first == catalogue_title + ".",
              (title, first))

        # A file with no line at all: honest, and still names the row.
        _write_toml("\n".join(line for line in shipped.splitlines()
                              if "wake_phrase" not in line))
        title = FG.display_title(row)
        first = answer("what is my wake word").reply.splitlines()[0]
        check("no wake_phrase line: the answer says it cannot read the phrase",
              "cannot read" in title and "cannot read" in first, (title, first))
        check("... and still carries the catalogue's own title",
              catalogue_title in title, (title, catalogue_title))

        # No settings module at all (a checkout, and a CI runner): the same
        # honest branch, and the title is STILL there - the CI case that this
        # suite must not bless by comparing the answer with itself.
        had_module = sys.modules.get("jarvis_framework")
        sys.modules["jarvis_framework"] = None   # makes `import` raise ImportError
        try:
            _phrase, why = FG.wake_phrase_now()
            title = FG.display_title(row)
            first = answer("what is my wake word").reply.splitlines()[0]
        finally:
            if had_module is None:
                sys.modules.pop("jarvis_framework", None)
            else:
                sys.modules["jarvis_framework"] = had_module
        check("no settings reader: the wake read says why it could not read",
              "could not be read" in why, why)
        check("... the answer names the catalogue's row and says it cannot read",
              catalogue_title in title and "cannot read" in title, title)
        check("... and the answer a person hears still names the row",
              catalogue_title in first and "cannot read" in first, first)
    finally:
        _restore_toml_env(had)


# ---------------------------------------------------------------------------


def main() -> int:
    try:
        a_failed_read_is_unknown_and_never_an_empty_set()
        the_tool_answers_say_the_read_failed()
        a_readable_file_is_counted_from_the_file()
        a_damaged_file_is_said_as_damaged()
        the_wake_answer_reads_the_live_phrase()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
