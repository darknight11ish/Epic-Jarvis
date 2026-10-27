"""test_schedule_actions.py - a reminder's OWN action: what it opens, and the
ONE card a reminder that acts must raise.

    python3 backend/test_schedule_actions.py

The owner's request of 2026-10-27: *"id likee to set custom reminders that open
something or do an action if i ask jarvos to make a specific remonder ... like
makinf a reminder that opens a specific image or webpage ... or action cards
(woth actions that jarvis will perform after i approve a card made by the
reminder when the time hits)"*. `DESIGN.md` answers it with ONE additive block
on a reminder: a display kind (`show-note`, `open-webpage`, `open-file`) that
opens nothing by itself, and an acting kind (`run-task`) that raises exactly ONE
`schedule_action` card at fire time and runs nothing without a yes.

What it proves, with a hand-moved clock and a real SQLite file in a temporary
folder:
  - each kind is CHECKED WHEN THE REMINDER IS SAVED: https only for a page, the
    documents allow-list AND an extension allow-list for a file, 500 characters
    and 10 lines for a note, the closed two-name list for a task - and every
    failure is one plain sentence, never a code;
  - only a REMINDER may carry one, and the block is exactly one kind plus its
    one payload key - no free text, no second target, never a shell, a command,
    a script or a webhook;
  - a reminder with NO action is byte for byte the reminder it was: no `action`
    key in the payload, no new card, no change to what fires (the additive
    contract an older client relies on), and `status()["actions"]` is the marker
    that tells a newer client the PC can keep one;
  - `run-task` raises ONE card, action `schedule_action`, and its `detail`
    carries the job id, `due`, the closed-list name and one boolean - NEVER the
    reminder's words, the URL, the path or the note (redaction can be off, and
    with it off the gate records `detail` verbatim);
  - approved runs the task ONCE; denied, timed out, refused, a tier that is not
    "ask", a gate that raised, and a reminder changed while the card waited all
    run NOTHING, and every one of them says why in the audit (ids only);
  - a display kind raises NO card when it goes off: nothing but the notice;
  - a repeating reminder asks EVERY time it goes off, never once and then
    silent, and two occurrences can never share one card;
  - a damaged action (anything on the owner's own disk can edit that row) fires
    as an ordinary reminder, opens nothing, raises no card, and says so in its
    view (`action_unreadable`);
  - the SECOND check, at the moment the target is used: a file that has gone, or
    whose folder is no longer listed, is reported as `action_problem` on the
    fired row, so no Open button is drawn for something that cannot work;
  - the `backup` task is refused when the reminder is SAVED, with its reason: a
    backup is locked with a fresh recovery code that nothing would be left to
    show, and a backup nobody can open is worse than none.

`jarvis_documents.allowed_path` is the REAL function here, handed the test's own
folder list (that is what `folders()` supplies on the owner's PC); nothing about
the allow-list is re-implemented in this file.

Standard library only. No network, no model, no owner's files.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_schedule as S  # noqa: E402
import jarvis_documents as DOCS  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-actions-"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Verdict:
    def __init__(self, allowed, tier, outcome):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome


#: The audit log, captured: the ids, kinds and outcomes a reminder's action is
#: allowed to write - and never its words.
_AUDIT = []
_real_audit = S._audit
S._audit = lambda event, detail: _AUDIT.append((event, detail))


class World:
    """A scheduler with a hand-moved clock, a gate that records what it was
    asked and answers with whatever the test says, and the audit captured."""

    def __init__(self, t, *, answer="approved", tier="ask", name="w", on_gate=None):
        self.clock = Clock(t)
        self.events, self.cards = [], []
        self.answer, self.tier = answer, tier
        self.on_gate = on_gate
        self.acted = []
        path = _TMP / f"{name}-{len(list(_TMP.iterdir()))}.db"
        self.s = S.Scheduler(path, clock=self.clock, gate=self.gate,
                             tier_of=lambda a: self.tier,
                             spawn=lambda fn: fn(),
                             publish=lambda k, d: self.events.append((k, d)))

    def gate(self, action, detail, prompt):
        self.cards.append({"action": action, "detail": dict(detail), "prompt": prompt})
        if self.on_gate is not None:
            self.on_gate(self)
        if self.answer == "approved":
            return Verdict(True, "ask", "approved")
        return Verdict(False, "ask", self.answer)

    def card(self):
        return self.cards[-1] if self.cards else {}


#: The folder the test's allowed files live in - the stand-in for the owner's
#: "Folders Jarvis may look in" (`jarvis_documents.folders()` on his PC).
ROOT = None
FILE = None


def use_root():
    """A real folder with one real picture in it, and the REAL allow-list
    resolved against it: `_documents()` is replaced by a shim that calls
    `jarvis_documents.allowed_path(path, [ROOT])`, exactly what `folders()`
    supplies in production."""
    global ROOT, FILE
    ROOT = Path(tempfile.mkdtemp(prefix="jv-action-root-"))
    FILE = ROOT / "taxes.png"
    FILE.write_bytes(b"\x89PNG\r\n\x1a\n")
    real = DOCS.allowed_path
    S._documents = lambda: type("Docs", (), {
        "allowed_path": staticmethod(lambda p, roots=None: real(p, [str(ROOT)]))})()
    return ROOT, FILE


def restore_documents():
    S._documents = _original_documents


_original_documents = S._documents


def add(w, **kwargs):
    """One reminder `seconds` ahead of the world's clock."""
    kwargs.setdefault("kind", "reminder")
    at = w.clock.t + kwargs.pop("in_seconds", 10.0)
    return w.s.add_at(kwargs.pop("kind"), at, kwargs.pop("text", "a reminder"),
                      **kwargs)


def refused(fn, words=None):
    """(refused?, sentence) - the one plain sentence a bad action gets."""
    try:
        fn()
    except ValueError as exc:
        text = str(exc)
        if words is not None and words not in text:
            return False, text
        return True, text
    except Exception as exc:                     # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"
    return False, ""


# --------------------------------------------------------------------------
#   1. The block, checked when the reminder is SAVED
# --------------------------------------------------------------------------


def t_each_kind_is_saved_and_handed_back_exactly() -> None:
    w = World(1_800_000_000.0, name="kinds")
    blocks = [
        {"kind": "show-note", "note": "Take the blue folder\nand the form"},
        {"kind": "open-webpage", "url": "https://example.com/invoice-42"},
        {"kind": "open-file", "path": str(FILE)},
        {"kind": "run-task", "task": "briefing"},
    ]
    for block in blocks:
        job = add(w, action=block, text=f"one {block['kind']}")
        check(f"{block['kind']}: it is handed back exactly what was saved",
              job.get("action") == block, job.get("action"))
        check(f"{block['kind']}: and no second key was invented",
              set(job["action"]) == set(block), job.get("action"))
        check(f"{block['kind']}: nothing is reported wrong with it",
              "action_problem" not in job and "action_unreadable" not in job, job)


def t_a_page_must_be_https_with_a_real_host() -> None:
    w = World(1_800_000_000.0, name="url")
    good = "https://example.com/invoice-42"
    check("a plain https address is accepted",
          add(w, action={"kind": "open-webpage", "url": good}).get("action")
          == {"kind": "open-webpage", "url": good})
    bad = {
        "http://example.com": "https",
        "example.com/invoice": "https",
        "javascript:alert(1)": "https",
        "file:///C:/Users/pcadmin/a.png": "https",
        "https://github.com@evil.example/": "https",
        "https://example.com\\@evil.example": "https",
        "https://exa mple.com": "https",
        "https://": "https",
    }
    for url, word in bad.items():
        got, sentence = refused(lambda u=url: add(w, action={"kind": "open-webpage", "url": u}),
                               word)
        check(f"{url!r} is refused at save", got, sentence)
    got, sentence = refused(
        lambda: add(w, action={"kind": "open-webpage", "url": "https://e.com/" + "a" * 1100}),
        "1024")
    check("an address over 1024 characters is refused at save", got, sentence)


def t_a_file_is_confined_to_the_folders_and_the_extension_list() -> None:
    w = World(1_800_000_000.0, name="file")
    check("a picture inside a listed folder is accepted",
          add(w, action={"kind": "open-file", "path": str(FILE)}).get("action")
          == {"kind": "open-file", "path": str(FILE)})

    outside = Path(tempfile.gettempdir()) / "not-in-a-listed-folder.png"
    outside.write_bytes(b"x")
    got, sentence = refused(lambda: add(w, action={"kind": "open-file", "path": str(outside)}),
                            "not in a folder Jarvis may look in")
    check("a file outside every listed folder is refused at save", got, sentence)

    # The extension is the boundary: "open a file" means "run whatever is
    # registered for it", so a shortcut, a program or a script is never on it.
    for name in ("shortcut.lnk", "setup.exe", "run.bat", "run.cmd", "run.ps1",
                 "page.html", "page.svg", "page.msi", "page.scr"):
        path = ROOT / name
        path.write_bytes(b"x")
        got, sentence = refused(lambda p=path: add(w, action={"kind": "open-file", "path": str(p)}),
                                "will not start a program")
        check(f"a .{name.rsplit('.', 1)[1]} is refused at save", got, sentence)
        path.unlink()

    missing = ROOT / "gone-tomorrow.pdf"
    got, sentence = refused(lambda: add(w, action={"kind": "open-file", "path": str(missing)}),
                            "not there")
    check("a file that is not there is refused at save", got, sentence)

    got, sentence = refused(lambda: add(w, action={"kind": "open-file", "path": "taxes.png"}),
                            "not in a folder")
    check("a bare file name is refused at save (no whole path)", got, sentence)

    got, sentence = refused(
        lambda: add(w, action={"kind": "open-file", "path": "\\\\?\\C:\\a\\b.png"}),
        "")
    check("a device path is refused at save", got, sentence)


def t_a_note_is_500_characters_and_10_lines() -> None:
    w = World(1_800_000_000.0, name="note")
    check("a note with a line break is kept as it was typed",
          add(w, action={"kind": "show-note", "note": "line one\nline two"}).get("action")
          == {"kind": "show-note", "note": "line one\nline two"})
    got, sentence = refused(lambda: add(w, action={"kind": "show-note", "note": "  "}), "note")
    check("an empty note is refused at save", got, sentence)
    got, sentence = refused(lambda: add(w, action={"kind": "show-note", "note": "x" * 501}), "500")
    check("a note over 500 characters is refused at save", got, sentence)
    got, sentence = refused(
        lambda: add(w, action={"kind": "show-note", "note": "\n".join(["x"] * 11)}), "10 lines")
    check("a note over 10 lines is refused at save", got, sentence)


def t_a_task_is_one_of_two_names_and_backup_says_why_not() -> None:
    w = World(1_800_000_000.0, name="task")
    check("the morning briefing is the task a reminder may ask for",
          add(w, action={"kind": "run-task", "task": "briefing"}).get("action")
          == {"kind": "run-task", "task": "briefing"})
    got, sentence = refused(lambda: add(w, action={"kind": "run-task", "task": "backup"}),
                            "recovery code")
    check("a backup is refused, with the reason (its code would be shown to nobody)",
          got, sentence)
    for name in ("shell", "sleep", "rm -rf /", "open-app", ""):
        got, sentence = refused(lambda n=name: add(w, action={"kind": "run-task", "task": n}))
        check(f"the task {name!r} is refused at save (the list is closed)", got, sentence)


def t_the_block_is_exactly_one_kind_and_its_one_target() -> None:
    w = World(1_800_000_000.0, name="shape")
    for label, block in [
        ("no kind", {"url": "https://example.com"}),
        ("an unknown kind", {"kind": "run-command", "command": "calc"}),
        ("two targets", {"kind": "open-webpage", "url": "https://example.com",
                         "note": "and this"}),
        ("the wrong key for the kind", {"kind": "open-webpage", "path": str(FILE)}),
        ("no target at all", {"kind": "open-file"}),
        ("an app (not in this slice)", {"kind": "open-app", "app": "Notion"}),
        ("a list instead of an object", ["open-webpage", "https://example.com"]),
        ("a bare string", "https://example.com"),
    ]:
        got, sentence = refused(lambda b=block: add(w, action=b))
        check(f"{label} is refused at save", got, sentence)
    got, sentence = refused(
        lambda: add(w, action={"kind": "show-note", "note": "x" * 4000}),
        "500")
    check("a block too big to keep with one reminder is refused", got, sentence)


def t_only_a_reminder_can_carry_one() -> None:
    w = World(1_800_000_000.0, name="kinds-only")
    for kind in ("alarm", "todo"):
        got, sentence = refused(
            lambda k=kind: add(w, kind=k, action={"kind": "show-note", "note": "hi"}),
            "only a reminder")
        check(f"a {kind} cannot carry an action", got, sentence)
    S._SCHED = w.s
    try:
        code, body = S.handle_add({"kind": "timer", "seconds": 60, "text": "tea",
                                   "action": {"kind": "show-note", "note": "hi"}})
    finally:
        S._SCHED = None
    check("a timer made through the route carries no action at all (200, ignored)",
          code == 200 and "action" not in body.get("job", {}), body)


def t_a_repeating_reminder_keeps_its_action() -> None:
    w = World(1_800_000_000.0, name="repeat-save")
    job = w.s.add_repeat("reminder", {"every": "day", "at": "07:00"}, "morning",
                         action={"kind": "open-webpage", "url": "https://example.com/today"})
    check("a repeating reminder keeps the action it was made with",
          job.get("action") == {"kind": "open-webpage",
                                "url": "https://example.com/today"}, job)
    got, sentence = refused(
        lambda: w.s.add_repeat("briefing", {"every": "day", "at": "07:00"}, "",
                               action={"kind": "show-note", "note": "hi"}),
        "")
    check("a kind that is not a reminder cannot repeat with one", got, sentence)


# --------------------------------------------------------------------------
#   2. What a client sees, and what an OLD client sees
# --------------------------------------------------------------------------


def t_a_reminder_with_no_action_is_exactly_what_it_was() -> None:
    w = World(1_800_000_000.0, name="old-client")
    plain = add(w, text="call Mum")
    for key in ("action", "action_problem", "action_unreadable"):
        check(f"a reminder with no action has no {key!r} key at all", key not in plain, plain)
    check("the words, the time and the state are untouched",
          plain["text"] == "call Mum" and plain["state"] == "active"
          and plain["due"] == w.clock.t + 10.0, plain)
    w.clock.t += 20.0
    w.s.tick()
    fired = w.s.job(plain["id"])
    check("... and when it goes off, still nothing", "action" not in fired, fired)
    check("... and no card was raised for it", w.cards == [], w.cards)


def t_the_pc_says_it_can_keep_one() -> None:
    w = World(1_800_000_000.0, name="marker")
    status = w.s.status()
    check("status() carries the additive capability marker `actions: true`",
          status.get("actions") is True, status.get("actions"))
    check("... and the older marker is still there, unchanged",
          status.get("phase2") is True and status.get("available") is True)
    check("... and no job in it grows an action key",
          all("action" not in job for job in status["jobs"]), status["jobs"])


def t_handle_add_takes_it_and_ignores_nothing_silently() -> None:
    """The HUD's own route: an action in the body reaches the row, and a body
    without one makes exactly the reminder it made before."""
    w = World(1_800_000_000.0, name="handle")
    S._SCHED = w.s
    try:
        code, body = S.handle_add({"kind": "reminder", "at": w.clock.t + 10.0,
                                   "text": "taxes",
                                   "action": {"kind": "open-webpage",
                                              "url": "https://example.com/taxes"}})
        check("POST /api/schedule/add keeps the action (200)", code == 200, body)
        check("... and the answer carries it back",
              body["job"].get("action", {}).get("url") == "https://example.com/taxes", body)
        code, body = S.handle_add({"kind": "reminder", "at": w.clock.t + 10.0,
                                   "text": "plain"})
        check("a body with no action still makes a plain reminder (200)", code == 200, body)
        check("... with no action key", "action" not in body["job"], body)
        code, body = S.handle_add({"kind": "reminder", "at": w.clock.t + 10.0,
                                   "text": "bad",
                                   "action": {"kind": "open-webpage", "url": "http://x.com"}})
        check("a bad target is a 400 with the sentence, not a silent drop",
              code == 400 and "https" in body.get("error", ""), body)
    finally:
        S._SCHED = None


# --------------------------------------------------------------------------
#   3. run-task: ONE card at fire time, and nothing without a yes
# --------------------------------------------------------------------------


def _briefing_calls():
    """A stand-in `jarvis_briefing` that records, so a check can say whether the
    briefing was put together - and never asks the real one for anything."""
    calls = []

    class Fake:
        @staticmethod
        def make(**kwargs):
            calls.append(kwargs)
            return {"ok": True}

    return Fake, calls


def t_run_task_raises_exactly_one_card_and_its_detail_carries_no_words() -> None:
    import types
    fake, calls = _briefing_calls()
    keep = sys.modules.get("jarvis_briefing")
    sys.modules["jarvis_briefing"] = fake
    try:
        w = World(1_800_000_000.0, name="card")
        job = add(w, text="taxes and the blue folder",
                  action={"kind": "run-task", "task": "briefing"})
        w.clock.t += 20.0
        w.s.tick()
        check("going off raises exactly ONE card", len(w.cards) == 1, w.cards)
        card = w.card()
        check("... and it is the scheduler's own `schedule_action`",
              card.get("action") == "schedule_action", card.get("action"))
        check("... approved, so the briefing was put together once",
              len(calls) == 1, calls)
        check("... with this reminder's id, so both apps can read it",
              calls and calls[0].get("job") == job["id"], calls)
        detail = card.get("detail") or {}
        check("the detail carries exactly the ids, the closed-list name and due",
              set(detail) == {"job", "due", "what", "task", "leaves_this_pc"}, detail)
        check("... the id and the due are the ones this occurrence had",
              detail.get("job") == job["id"] and abs(float(detail.get("due", 0))
                                                     - (job["due"])) < 0.5, detail)
        check("... and it says nothing leaves this PC",
              detail.get("leaves_this_pc") is False, detail)
        # THE ONE THAT MATTERS: `_redact` returns `detail` VERBATIM when
        # `[logging].redact_private_content_in_logs` is off, so a target here
        # would be written into the audit log in the clear. The reminder's own
        # words are not in it either - detail reaches BOTH apps on /api/pending.
        blob = json.dumps(detail)
        for word in ("taxes", "blue folder", "http", "/", "\\"):
            check(f"the detail does not carry {word!r}", word not in blob, blob)
        prompt = card.get("prompt") or ""
        check("the card's TEXT says what will happen, in the owner's words",
              "put your morning briefing together now" in prompt, prompt)
        check("... and says nothing happens before a yes",
              "only if you say yes" in prompt and "Nothing happens before that" in prompt,
              prompt)
        check("... and names the reminder the owner set",
              "Reminder: taxes and the blue folder" in prompt, prompt)
        ran = [d for e, d in _AUDIT if e == "schedule.action_ran"]
        check("the audit says it ran, with the id and the task only",
              ran and ran[-1].get("what") == "briefing" and "id" in ran[-1], ran)
    finally:
        if keep is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = keep


def t_denied_expired_and_refused_run_nothing() -> None:
    import types
    fake, calls = _briefing_calls()
    keep = sys.modules.get("jarvis_briefing")
    sys.modules["jarvis_briefing"] = fake
    try:
        for answer, label in (("denied", "denied"), ("timed_out", "nobody answered")):
            w = World(1_800_000_000.0, name=f"no-{answer}", answer=answer)
            add(w, action={"kind": "run-task", "task": "briefing"})
            w.clock.t += 20.0
            w.s.tick()
            check(f"{label}: the card was raised once", len(w.cards) == 1, w.cards)
            check(f"{label}: nothing ran", calls == [], calls)
            refused_lines = [d for e, d in _AUDIT if e == "schedule.action_refused"]
            check(f"{label}: the audit names the outcome, and only the id",
                  refused_lines and refused_lines[-1].get("outcome") == answer
                  and set(refused_lines[-1]) == {"id", "outcome"}, refused_lines[-1:])
        # A tier that is not "ask" is never a person saying yes.
        w = World(1_800_000_000.0, name="auto", tier="auto")
        add(w, action={"kind": "run-task", "task": "briefing"})
        w.clock.t += 20.0
        w.s.tick()
        check("a tier of auto raises no card at all", w.cards == [], w.cards)
        check("... and runs nothing", calls == [], calls)
        # A gate that raises is a refusal, never an exception in the tick loop.
        def boom(*a, **k):
            raise RuntimeError("the gate is broken")
        w = World(1_800_000_000.0, name="boom")
        w.s._gate = boom
        add(w, action={"kind": "run-task", "task": "briefing"})
        w.clock.t += 20.0
        check("a gate that raises does not stop the tick loop",
              w.s.tick() != [], "tick raised or returned nothing")
        check("... and runs nothing", calls == [], calls)
    finally:
        if keep is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = keep


def t_a_reminder_changed_while_the_card_waited_runs_nothing() -> None:
    """PA-6: the card named this row as it was. If it changed while the card
    waited, the thing the owner approved is not the thing that would run."""
    import types
    fake, calls = _briefing_calls()
    keep = sys.modules.get("jarvis_briefing")
    sys.modules["jarvis_briefing"] = fake
    try:
        w = World(1_800_000_000.0, name="pa6")

        def edit_it(inner):
            # The premise of PA-6: the row is plain SQLite on the owner's own
            # disk, and anything on this PC can edit it while a card waits.
            with inner.s._lock, inner.s._db() as c:
                c.execute("UPDATE jobs SET text = ?, changed = ? WHERE id = ?",
                          ("different words", inner.clock.t + 1.0,
                           inner.cards[0]["detail"]["job"]))

        w.on_gate = edit_it
        add(w, text="the first words", action={"kind": "run-task", "task": "briefing"})
        w.clock.t += 20.0
        w.s.tick()
        check("the card was raised", len(w.cards) == 1, w.cards)
        check("the reminder was edited while it waited", calls == [], calls)
        refused_lines = [d for e, d in _AUDIT if e == "schedule.action_refused"]
        check("... so nothing ran, and the audit says it was withdrawn",
              refused_lines and refused_lines[-1].get("outcome") == "withdrawn",
              refused_lines[-1:])
    finally:
        if keep is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = keep


def t_the_same_occurrence_is_never_asked_or_run_twice() -> None:
    import types
    fake, calls = _briefing_calls()
    keep = sys.modules.get("jarvis_briefing")
    sys.modules["jarvis_briefing"] = fake
    try:
        w = World(1_800_000_000.0, name="twice")
        job = add(w, action={"kind": "run-task", "task": "briefing"})
        due = w.clock.t + 10.0
        w.clock.t += 20.0
        w.s.tick()
        check("the first fire asks once", len(w.cards) == 1, w.cards)
        w.s._fire_action(job["id"], due)
        check("a retry of the SAME occurrence asks nothing more", len(w.cards) == 1, w.cards)
        check("... and runs nothing more", len(calls) == 1, calls)
        check("a second tick of a one-off fires nothing", w.s.tick() == [])
    finally:
        if keep is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = keep


def t_a_repeating_reminder_asks_every_time() -> None:
    import types
    fake, calls = _briefing_calls()
    keep = sys.modules.get("jarvis_briefing")
    sys.modules["jarvis_briefing"] = fake
    try:
        w = World(1_800_000_000.0, name="repeat-fire")
        job = w.s.add_repeat("reminder", {"every": "day", "at": "07:00"}, "stand-up",
                             action={"kind": "run-task", "task": "briefing"})
        first_due = job["due"]
        w.clock.t = first_due + 1.0
        w.s.tick()
        check("the first occurrence asks once", len(w.cards) == 1, w.cards)
        first_card = w.card()
        w.clock.t = first_due + 86400.0 + 1.0
        w.s.tick()
        check("the next occurrence asks AGAIN - never once and then silent",
              len(w.cards) == 2, w.cards)
        check("... and two occurrences can never share one card (due differs)",
              float(first_card["detail"]["due"]) != float(w.card()["detail"]["due"]),
              (first_card["detail"], w.card()["detail"]))
        check("... so the briefing was put together twice", len(calls) == 2, calls)
        prompt = w.card()["prompt"]
        check("the repeat's card says it will ask again next time",
              "It repeats, so it will ask again next time." in prompt, prompt)
    finally:
        if keep is None:
            sys.modules.pop("jarvis_briefing", None)
        else:
            sys.modules["jarvis_briefing"] = keep


def t_a_display_kind_raises_no_card_at_all() -> None:
    w = World(1_800_000_000.0, name="display")
    job = add(w, action={"kind": "open-webpage", "url": "https://example.com/invoice-42"})
    w.clock.t += 20.0
    w.s.tick()
    check("a page reminder raises NO card when it goes off", w.cards == [], w.cards)
    check("... and the app is told it went off as usual (ids and kind only)",
          any(k == "schedule" and d.get("state") == "fired" for k, d in w.events),
          w.events)
    fired = w.s.job(job["id"])
    check("... and the fired row still hands out the WHOLE target, by id, so the "
          "notice can name it before anything opens",
          fired.get("action") == {"kind": "open-webpage",
                                  "url": "https://example.com/invoice-42"}, fired)
    check("... and it is not reported as broken", "action_problem" not in fired, fired)


# --------------------------------------------------------------------------
#   4. The second check: at the moment the target is used
# --------------------------------------------------------------------------


def t_a_file_that_went_away_is_reported_on_the_fired_row() -> None:
    w = World(1_800_000_000.0, name="gone")
    path = ROOT / "letter.pdf"
    path.write_bytes(b"%PDF-1.4")
    job = add(w, action={"kind": "open-file", "path": str(path)})
    check("the file is there when the reminder is saved",
          "action_problem" not in job, job)
    path.unlink()
    w.clock.t += 20.0
    w.s.tick()
    fired = w.s.job(job["id"])
    check("once it has gone off and the file has gone, the row says so",
          fired.get("action_problem") == "That file is not there any more.", fired)
    check("... and the action is still there, so the row can say WHAT went",
          fired.get("action", {}).get("path") == str(path), fired.get("action"))


def t_a_folder_removed_from_settings_is_reported_too() -> None:
    w = World(1_800_000_000.0, name="unlisted")
    job = add(w, action={"kind": "open-file", "path": str(FILE)})
    # The owner removes that folder from Settings -> the allow-list is empty.
    shim = S._documents
    S._documents = lambda: type("Docs", (), {
        "allowed_path": staticmethod(lambda p, roots=None: None)})()
    try:
        w.clock.t += 20.0
        w.s.tick()
        fired = w.s.job(job["id"])
    finally:
        S._documents = shim
    check("a file no longer in any listed folder is reported on the row",
          "not in a folder Jarvis may look in" in fired.get("action_problem", ""), fired)


def t_a_damaged_action_fails_safe() -> None:
    w = World(1_800_000_000.0, name="damaged")
    job = add(w, text="still mine", action={"kind": "run-task", "task": "briefing"})
    # Anything on this PC can edit that row - and a half-written block is what
    # a crash mid-update would leave.
    for raw in ('{"kind": "open-webpage"}', "not json at all", '["a list"]',
                '{"kind": "run-command", "command": "calc"}', '{"kind": "open-file", "path": ""}'):
        with w.s._lock, w.s._db() as c:
            c.execute("UPDATE jobs SET action = ? WHERE id = ?", (raw, job["id"]))
        view = w.s.job(job["id"])
        check(f"a damaged action ({raw[:22]}...) is never handed out as one",
              "action" not in view, view)
        check(f"... and the row says it could not be read ({raw[:22]}...)",
              view.get("action_unreadable") is True, view)
        check(f"... and the reminder's own words are untouched ({raw[:22]}...)",
              view.get("text") == "still mine", view)
    w.clock.t += 20.0
    w.s.tick()
    check("it still fires as an ordinary reminder", w.cards == [], w.cards)
    check("... and the audit says the action could not be read, id only",
          any(e == "schedule.action_unreadable" and set(d) == {"id"} for e, d in _AUDIT),
          [x for x in _AUDIT if "unreadable" in x[0]])


# --------------------------------------------------------------------------
#   5. The audit log says ids, never words
# --------------------------------------------------------------------------


def t_nothing_private_reaches_the_audit_log() -> None:
    secret_url = "https://example.com/invoice-42-private"
    secret_note = "the blue folder for Sam"
    secret_path = str(ROOT / "blue-folder.pdf")
    (ROOT / "blue-folder.pdf").write_bytes(b"%PDF-1.4")
    w = World(1_800_000_000.0, name="audit")
    add(w, text="taxes", action={"kind": "open-webpage", "url": secret_url})
    add(w, text="folder", action={"kind": "show-note", "note": secret_note})
    add(w, text="letter", action={"kind": "open-file", "path": secret_path})
    w.clock.t += 20.0
    w.s.tick()
    blob = json.dumps(_AUDIT)
    for word in (secret_url, secret_note, secret_path, "invoice-42", "Sam",
                 "blue-folder", "taxes"):
        check(f"the audit log never carries {word!r}", word not in blob, blob[:400])
    kinds = {d.get("kind") for e, d in _AUDIT if e == "schedule.fired"}
    check("... only the kind and the id", kinds == {"reminder"}, kinds)


# --------------------------------------------------------------------------
#   The suite
# --------------------------------------------------------------------------


def main() -> int:
    try:
        use_root()
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:            # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        S._audit = _real_audit
        restore_documents()
        shutil.rmtree(_TMP, ignore_errors=True)
        if ROOT is not None:
            shutil.rmtree(ROOT, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
