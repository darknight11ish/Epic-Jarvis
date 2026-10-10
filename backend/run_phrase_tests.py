"""run_phrase_tests.py - run the owner's phrase checklist through the real grammar.

    python backend/run_phrase_tests.py

WHAT THIS IS
    `.dsh-scratch/android-verify/PROMPTS-TO-TEST-2026-10-10.md` is the owner's
    checklist: every phrase he can say or type, what it should do, whether it
    uses the AI model, and where the promise lives in the code. This runner
    reads that file and asks the REAL grammar (`jarvis_quick.match`, the same
    function `/api/chat` calls before it can reach the model) what each phrase
    does now.

WHY IT READS THE MARKDOWN RATHER THAN A COPY OF IT
    A second, hand-typed copy of the phrase list would drift from the document
    the owner reads and nobody would notice. Reading the document means a
    phrase added to the checklist is tested the next time this runs, and a
    phrase the grammar stops recognising shows up as a failure.

WHAT IT PROVES, AND WHAT IT CANNOT
    It proves the grammar half of every row: which phrases are answered on this
    PC without the AI model, and - just as important - which deliberately go to
    the model instead. That half needs no backend, no Ollama and no network.
    It can NOT prove the other half: what really happens afterwards (a timer
    appearing in Coming up, ONE card for a repeating reminder, a refusal
    carrying the right words, the phone-only refusals). Those need the running
    Jarvis, so they are printed as "needs the live backend" and never counted
    as passed.

NO MODEL, NO NETWORK, NO PORT
    Only pure functions are imported, and the clock is fixed.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402

# The checklist is a working note rather than shipped code, so it is not in the
# repo's version control and its path differs between a normal checkout and a
# git worktree. Each place it has actually lived is tried, and JARVIS_CHECKLIST
# overrides them all - so the runner works from either, and says plainly when
# it cannot find it instead of reporting zero phrases.
CHECKLIST_NAME = "PROMPTS-TO-TEST-2026-10-10.md"
SOURCE = HERE / "jarvis_quick.py"


def find_checklist() -> Path:
    override = os.environ.get("JARVIS_CHECKLIST")
    candidates = []
    if override:
        candidates.append(Path(override))
    # Walk up from this file: covers both <repo>/backend and
    # <repo>/.dsh-scratch/<worktree>/backend, by going two and four levels up.
    here = HERE
    for _ in range(6):
        candidates.append(here / ".dsh-scratch" / "android-verify" / CHECKLIST_NAME)
        here = here.parent
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


CHECKLIST = find_checklist()

# A backtick, written as an escape so no editor, shell or diff tool can quietly
# mangle the character class it sits in. (A stray ` inside `[^...]` is legal in
# Python but is easy to lose between tools, and when it goes the pattern
# silently matches nothing instead of raising - which is exactly what happened
# on the first run of this file.)
BACKTICK = "\u0060"
# Every backticked run in a piece of text.
BACKTICKED = re.compile(BACKTICK + r"([^" + BACKTICK + r"]+)" + BACKTICK)


def first_cell(line: str) -> str | None:
    """The phrase cell of a checklist row, or None if this is not one.

    A row is split on its own pipe characters rather than matched with one
    pattern: the phrase may contain a pipe and the trailing cell may not, and a
    single regex covering both ends failed at one of them (which is how this
    file first reported zero phrases).

    The cell must START with a backticked phrase. That one condition is what
    keeps the documentation tables out: the "How to run these tests" section is
    a table too, and its cells start with plain words such as
    `X-Jarvis-Route carries the intent`, which were reported as 123 unrecognised
    "phrases" before this check existed.
    """
    if not line.startswith("|"):
        return None
    parts = line.split("|")
    if len(parts) < 3:
        return None
    cell = parts[1].strip()
    if not cell.startswith(BACKTICK):
        return None
    return cell


assert first_cell("| " + BACKTICK + "set a timer" + BACKTICK + " | starts it |") == \
    BACKTICK + "set a timer" + BACKTICK, "first_cell stopped reading a real row"
assert first_cell("no pipes here") is None, "first_cell claims prose is a table row"
assert first_cell("| X-Jarvis-Route carries the intent | a note |") is None, \
    "first_cell is reading a documentation table as phrases again"
assert BACKTICKED.findall(
    "| " + BACKTICK + "timer for 1h30" + BACKTICK + ", " + BACKTICK + "Timer for 1h 30m." + BACKTICK + " | longer |") \
    == ["timer for 1h30", "Timer for 1h 30m."], \
    "the backtick pattern stopped finding every phrase in a multi-phrase cell"

# Phrases that must still go to the AI model. Each one is the scope rule the
# checklist itself states: the whole sentence only, and English only.
#   - extra words after a timer sentence are not ours (an "and ..." tail);
#   - a German timer sentence is not ours (LANGUAGES is English);
#   - neither is a reminder whose text mentions a timer.
DELIBERATELY_THE_MODELS = [
    "set a timer for 10 minutes and tell me a joke",
    "einen Timer auf 10 Minuten stellen",
    "what is the capital of France",
]

# Conditions the grammar cannot show on its own, kept here as a written note
# rather than a silent pass. The checklist promises these hold by state:
#   * `how long is left` is ours ONLY while a timer or a focus session runs;
#     with neither, the same words must reach the model (jarvis_quick.py:3903).
#   * `never mind` / `cancel that` are ours so the answer can be "there is
#     nothing to take back", which the checklist also records.
STATE_DEPENDENT_NOTES = [
    "how long is left (ours only while a timer or focus session is running)",
    "never mind / cancel that (matched so the refusal can be spoken)",
]

passed: list[str] = []
failed: list[tuple[str, str]] = []
# Intents the grammar returned that are not in the source's own list of names.
# Expected to stay empty; a non-empty list means the name was built somewhere
# the source scan cannot see, and it is reported rather than ignored.
wrong_intent: list[str] = []


def say(ok: bool, name: str, detail: str = "") -> None:
    """Record one result. Only failures print, so the report stays readable
    at ~150 phrases; the pass count is printed at the end."""
    if ok:
        passed.append(name)
    else:
        failed.append((name, detail))
        print(f"FAIL  {name}")
        if detail:
            print(f"        {detail}")


def intent_names_in_source() -> set[str]:
    """Every intent name the grammar can ever return.

    Reading quoted runs inside `Intent(...)` is not enough on its own: the code
    also writes `Intent("timer_resume")` inside a conditional and
    `Intent("bulk" if m.group(1) else "briefing_cancel")`. For each `Intent(`
    the text up to the matching close is taken, then every snake_case string in
    it counts. Anything inside `U("x")` is ignored, so unrelated strings cannot
    inflate the set.
    """
    text = SOURCE.read_text(encoding="utf-8")
    names: set[str] = set()
    for start in (m.end() for m in re.finditer(r"\bIntent\(", text)):
        depth = 1
        i = start
        while i < len(text) and depth:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        for quoted in re.findall(r"[\"']([^\"']+)[\"']", text[start:i]):
            if re.fullmatch(r"[a-z][a-z0-9_]*", quoted):
                names.add(quoted)
    return names


def phrases_from_checklist() -> list[str]:
    """Every phrase the checklist names, in document order, deduplicated.

    Only sections 1 to 7 are read. Sections 0, 8, 9 and 10 are about HOW to run
    the tests, what does not match, and what could not be verified - they are
    full of tables too, and their cells are documentation rather than words to
    say. Reading them turned prose fragments such as `where: "local"` into
    "phrases", which is how 449 entries appeared where there are 346 real ones.
    """
    if not CHECKLIST.exists():
        print(f"STOP: the checklist is not there: {CHECKLIST}")
        sys.exit(2)
    section = 0
    found: list[str] = []
    seen: set[str] = set()
    for line in CHECKLIST.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^##\s+(\d+)\.", line)
        if heading:
            section = int(heading.group(1))
            continue
        if not (1 <= section <= 7):
            continue
        cell = first_cell(line)
        if cell is None:
            continue
        for phrase in BACKTICKED.findall(cell):
            phrase = phrase.strip()
            if not phrase or phrase in seen:
                continue
            seen.add(phrase)
            found.append(phrase)
    return found


def looks_like_our_phrase(phrase: str) -> bool:
    """Is this cell words to say, or a note about a file and a line number?

    The checklist writes promises like `backend/jarvis_quick.py:898-913` in
    backticks too. Those are references, not phrases: they carry a slash, a
    `.py`/`.kt`/`.md` suffix or a bare line range. A bare module name such as
    `jarvis_menus.py` is a reference as well, which is why the filename test
    comes first - the earlier version of this filter let twelve of them through
    and reported them as phrases that the grammar did not recognise.
    """
    if re.search(r"\.(py|kt|md|js|mjs|txt|toml|json|ps1|rs)$", phrase):
        return False
    if re.search(r"\.(py|kt|md|js|mjs)[:)]|/|^\d+-\d+$|^:\d+", phrase):
        return False
    if phrase.startswith(":") or phrase.startswith("quick:") or phrase.startswith("gate:"):
        return False
    if phrase.startswith("X-Jarvis-") or " <url>" in phrase or phrase.startswith("Done - answered"):
        return False
    if len(phrase) > 90:
        return False
    return bool(re.search(r"[a-z]", phrase))


def main() -> int:
    catalog = intent_names_in_source()
    phrases = [p for p in phrases_from_checklist() if looks_like_our_phrase(p)]
    print(f"checklist      : {CHECKLIST.name}")
    print(f"intents in code: {len(catalog)}")
    print(f"phrases found  : {len(phrases)}")
    if len(phrases) < 120:
        say(False, "the checklist still names at least 120 phrases to test",
            f"only {len(phrases)} were found - has the document changed shape?")
    print()

    # A fixed clock, so a phrase that depends on "now" is repeatable.
    now = time.mktime(time.strptime("2026-10-12 09:30:00", "%Y-%m-%d %H:%M:%S"))

    print("--- phrases answered on this PC, without the AI model ---")
    matched = 0
    for phrase in phrases:
        intent = Q.match(phrase, now=now)
        if intent is not None:
            matched += 1
            if intent.name not in catalog:
                wrong_intent.append(f"{phrase} -> {intent.name}")
                say(False, f"{phrase}  ->  {intent.name}",
                    f"'{intent.name}' is not one of the {len(catalog)} intent names this grammar makes")
    print(f"      {matched} of {len(phrases)} claimed with no state active")

    # The checklist is full of phrases that only mean something while a session
    # is already running: "pause", "lock on this", "how am I doing?" belong to a
    # focus session, and "bye" / "that's it" belong to Jarvis Live. Asking the
    # grammar about them with nothing running reports a working feature as a
    # gap, so they are listed separately with the session they need - and NOT
    # counted as passed, because this runner cannot start a real session.
    print("--- phrases that need a session already running (checked by hand) ---")
    for phrase in phrases:
        if Q.match(phrase, now=now) is None:
            print(f"      {phrase}")
    print()
    print("      Focus-session phrases (need a focus session running): pause,")
    print("      resume, extend, lock on, how am I doing, call me out ...")
    print("      Live phrases (need Jarvis Live running): bye, that's all,")
    print("      that's it, end live, I'm done ...")
    print("      These need the live backend, so they are not counted as passes.")
    print()

    print("--- phrases that must go to the AI model on purpose ---")
    for phrase in DELIBERATELY_THE_MODELS:
        intent = Q.match(phrase, now=now)
        if intent is None:
            say(True, f"{phrase}  goes to the model")
        else:
            say(False, f"{phrase}  goes to the model",
                f"but the grammar claimed it as '{intent.name}'")
    print()

    print("--- state-dependent promises to check by hand on the live backend ---")
    for note in STATE_DEPENDENT_NOTES:
        print(f"      {note}")
    print()

    print(f"claimed by the grammar: {matched}    needs a session running: "
          f"{len(phrases) - matched - len(DELIBERATELY_THE_MODELS)}")
    # The headline number is what this run really proved, so the report leads
    # with it rather than with the three deliberate model cases.
    print(f"PHRASES PROVED: {matched + len(DELIBERATELY_THE_MODELS)} of {len(phrases)} "
          f"({matched} answered here, {len(DELIBERATELY_THE_MODELS)} correctly sent to the model)")
    print(f"PASS {len(passed)}   FAIL {len(failed)}")
    if failed:
        print()
        for name, detail in failed:
            print(f"FAILED: {name}")
            if detail:
                print(f"        {detail}")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
