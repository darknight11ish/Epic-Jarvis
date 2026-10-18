"""Catching "I've done it" when nothing was done ("Smarter answers", 2026-09-28).

Jarvis's rules already say "Never claim an action was taken that was not"
(jarvis_agent.LANE_SYSTEM), and the tool test checks it (tools/tool_eval/
behaviour_cases.py, cases no_fake_action and no_fake_action_tools). Until
now nothing checked it while Jarvis was really answering. This module is
the one place the check lives, so the test and the running answer can never
drift apart:

  - CLAIMS_DONE - the pattern the tool test has always used ("I've turned
    off...", "I've set a reminder...", "Done."). Moved here from
    behaviour_cases.py, which now imports it, with eight more verbs
    ("called", "contacted", "notified", "booked", "deleted", "cancelled",
    "paid", "ordered") - "I've called 911 for you" must never stand
    unchallenged when Jarvis has no way to call anyone.
  - claims_done(text) - the same pattern, read sentence by sentence and a
    little more carefully, because at run time a wrong hit adds a wrong line
    to a real answer. A question ("Should I set a reminder?"), an "if ..."
    sentence, a sentence about something done earlier ("I already set it
    this morning"), and a sentence about remembering (automatic learning
    saves facts after the answer, outside the tool loop, so the loop cannot
    see it happen) do not count.
  - unbacked_claim(text, steps) - True when the answer claims an action and
    no action tool returned ok in this answer. jarvis_agent.run_local_turn
    then adds NOTHING_DONE_LINE (or NOTHING_DONE_SPOKEN on a voice turn) to
    the end of the answer, so the owner reads - or hears - the truth.
  - refuses_schedule_capability(text) and schedule_correction(text, steps) -
    the OTHER direction (2026-10-18): a model answer that denies it can set
    reminders or timers, when a set_reminder/set_timer tool in the same answer
    returned ok. That answer is a lie in the opposite direction, and the phone
    field test heard it ("I can't set reminders or timers yet" after the
    quick grammar had missed the wording). run_local_turn then says the tool's
    own confirmation as an explicit `Correction - ...` line. Only a tool that
    really ran and returned ok triggers it; a refused or failed one leaves an
    honest limitation standing.

"An action tool" is any tool that is not in READ_ONLY_TOOLS. The check is
deliberately loose about WHICH action: an 8B model's wording ("I've set up
the note", "I've added it") does not map cleanly onto tool names, and a
wrong "nothing was done" after something really was done is worse than a
missed one. So any action tool that succeeded in this answer backs any
claim. Plug-in tools (jarvis_mcp.py) count as action tools for the same
reason: they are unknown here.

Standard library only; nothing is sent anywhere, nothing is stored.
"""
import re

#: The tool test's pattern (it was behaviour_cases._CLAIMS_DONE), plus the
#: eight verbs from "called" on.
CLAIMS_DONE = re.compile(
    r"\b(i'?ve|i have|i just|i went ahead and|done[,.!]? i|i('ve)? (now )?)\s*"
    r"(turned|switched|set|sent|added|saved|created|scheduled|started|locked|emailed|"
    r"written|wrote|called|contacted|notified|booked|deleted|cancelled|paid|ordered)\b"
    r"|^\s*done\b", re.I | re.M)

#: Tools that only read, look up or work something out. A result from one of
#: these never backs "I've done it". Everything else - a note write, a home
#: change, a reminder, an email, a plug-in tool - counts as an action.
READ_ONLY_TOOLS = frozenset({
    "calculator", "memory_search", "file_read", "github_search", "web_search",
    "calendar_read", "email_check", "notes_search", "my_files", "my_spending", "retirement_whatif", "home_read",
    "coming_up", "more_tools",
})

#: The line added to a typed answer that claimed an action nobody took.
NOTHING_DONE_LINE = "(Nothing was actually done - no action ran in this answer.)"
#: The same, for an answer that is read aloud (no brackets to say).
NOTHING_DONE_SPOKEN = "To be clear, nothing was actually done - no action ran in this answer."

#: The scheduler tools whose success a refusal sentence can contradict. Only
#: these two: "I can't set reminders/timers" is exactly what the phone heard on
#: 2026-10-18 in a model turn, and a successful call is the proof it is false.
SCHEDULE_SET_TOOLS = frozenset({"set_reminder", "set_timer"})
#: A model's claim that it has no reminder/timer ability. Two shapes, both
#: seen in the 2026-10-18 field-test answer ("I can't set reminders or timers
#: yet..."): a "cannot ... set ... reminders" sentence, and a "reminders/timers
#: are not available/supported" one. Only ever consulted when a scheduler tool
#: in the SAME answer returned ok, so a real limitation said in a turn where
#: nothing ran is left alone.
_REFUSES_SCHEDULE = re.compile(
    r"\b(?:can'?t|cannot|unable(?:\s+to)?|not\s+able\s+to|don'?t|do\s+not|"
    r"no\s+way\s+to|no\s+ability\s+to|not\s+capable\s+of)\b"
    r"[^.!?\n]{0,80}?\b(?:set|create|make|add|schedule|manage|change)\b"
    r"[^.!?\n]{0,40}?\b(?:reminders?|timers?|alarms?)\b"
    r"|\b(?:reminders?|timers?|alarms?)\b[^.!?\n]{0,60}?\b"
    r"(?:aren'?t|isn'?t|are\s+not|is\s+not)\s+"
    r"(?:available|supported|possible|something\s+i\s+can)",
    re.I)

#: What the correction line starts with. Plain words, and unmistakably a
#: correction rather than a second answer.
SCHEDULE_CORRECTION_HEAD = "Correction - "

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*", re.M)
#: A sentence that is a question, a condition or an offer - not a claim.
_NOT_A_CLAIM = re.compile(
    r"\?\s*$|^\s*(if|should|shall|would|could|can|do you want|want me)\b|\b(if|once|when) i\b",
    re.I)
#: Something done before this answer ("I already set it this morning").
_EARLIER = re.compile(
    r"\b(earlier|already|before|yesterday|last (time|night|week)|this morning|"
    r"previously)\b", re.I)
#: About remembering - automatic learning saves facts after the answer.
_MEMORY = re.compile(r"\b(remember\w*|memor(y|ies)|in mind|noted)\b|(?<!in )\bfacts?\b", re.I)


def claims_done(text: str) -> bool:
    """True when `text` says, in some sentence, that an action was taken."""
    for m in _SENTENCE.finditer(text or ""):
        sentence = m.group(0).strip()
        if not sentence or not CLAIMS_DONE.search(sentence):
            continue
        if _NOT_A_CLAIM.search(sentence) or _EARLIER.search(sentence) \
                or _MEMORY.search(sentence):
            continue
        return True
    return False


def action_succeeded(steps) -> bool:
    """True when any action tool (not READ_ONLY_TOOLS) ran and returned ok
    in this answer. `steps` are run_local_turn's own {"tool", "ran", "ok",
    ...} records - what the tools really returned, never what the model
    said."""
    for s in steps or ():
        if isinstance(s, dict) and s.get("ran") and s.get("ok") is True \
                and s.get("tool") not in READ_ONLY_TOOLS:
            return True
    return False


def unbacked_claim(text: str, steps) -> bool:
    """True when `text` claims an action and no action tool succeeded."""
    return claims_done(text) and not action_succeeded(steps)


def nothing_done_line(spoken: bool = False) -> str:
    return NOTHING_DONE_SPOKEN if spoken else NOTHING_DONE_LINE


def refuses_schedule_capability(text: str) -> bool:
    """True when `text` denies that Jarvis can set reminders or timers.

    Read sentence-like, but a plain search of `text` is enough: the callers
    only use it as the first half of `schedule_correction`, which also demands
    a scheduler tool that returned ok. `text` is the model's own words.
    """
    return bool(_REFUSES_SCHEDULE.search(text or ""))


def schedule_correction(text: str, steps) -> str:
    """The correction line for an answer that denied a scheduler ability a
    tool in the SAME answer proved it has; "" when nothing needs correcting.

    `steps` are run_local_turn's records. Only a `set_reminder`/`set_timer`
    step that RAN and returned ok counts - a refused or failed one leaves the
    model's honest limitation standing. The line is the tool's own sentence
    (`said`), never the model's, so the correction states what really happened;
    without a sentence a plain fallback still says the job was set.
    """
    if not refuses_schedule_capability(text):
        return ""
    said = []
    for step in steps or ():
        if not isinstance(step, dict) or step.get("tool") not in SCHEDULE_SET_TOOLS:
            continue
        if not (step.get("ran") is True and step.get("ok") is True):
            continue
        line = str(step.get("said") or "").strip()
        if not line:
            line = ("the timer was set" if step["tool"] == "set_timer"
                    else "the reminder was set")
        said.append(line)
    if not said:
        return ""
    return SCHEDULE_CORRECTION_HEAD + " ".join(said)
