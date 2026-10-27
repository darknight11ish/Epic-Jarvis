"""test_update_chat.py - "is there an update?", "what changed?", "update Jarvis"
(2026-10-26; backend/jarvis_quick.py; docs/JARVIS-API.md section 158).

    python3 backend/test_update_chat.py

The owner's own request: "can jarvis talk about an update if theres one
availabale and the changes? and start the update process for me?" - "if i ask
in chat".

Runs anywhere. NO REAL NETWORK CALL: every release-manifest read is a fake this
file supplies, and every gate call is a fake too. What it proves:

1. THE WORDS. The three phrasings answer without the model; the near-misses do
   not (bare "what's new", "how do I update Jarvis", "when is the next
   update", "update my settings", "did the update break anything").
2. THE STATES, each with its own honest sentence, never the same one twice:
   no report of the running build; a build with no update key; a failed
   check; this build newer than the published one; the newest; an update
   available. "What changed" never invents a list - an empty notes field says
   the release does not say. A release that is several versions ahead says
   its notes cover only that release.
3. STARTING IT. Exactly ONE card, raised through jarvis_gate.check, and only
   when there really is an update and the tier is "ask". Nothing is spawned
   for any other state, for a stricter tier, or when the spawn itself fails -
   and each of those says plainly that nothing was changed. The card's own
   words name both halves, the version, the restart, the pace, the signature
   check and "only on this PC".
4. THE GATE IS THE ONLY DOOR. The module downloads no installer, runs no
   program and installs nothing: the card thread calls the gate and returns.
   `desktop_update` is in `jarvis_owner_check.PC_ONLY_ACTIONS` and tier "ask",
   so only this PC can approve it, and Windows Hello comes first.
5. THE TWO FILES AND THE TWO APPS. `jarvis-backend/jarvis_quick.py` is the
   byte-identical twin. The manifest URL in the module is the one the app's
   own updater reads (`tauri.conf.json`), so the chat can never check a
   different release from the one the app installs. `answer_turn` really
   passes the body's `desktop` facts through.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

# Hermetic, like the rest of the suite: the owner's real home, config and audit
# log stay untouched (this suite answers through `answer()`, which asks
# jarvis_manner and jarvis_personality_creator for words).
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-update-chat-"))
os.environ["OPENJARVIS_HOME"] = str(_TMP)
os.environ["JARVIS_HOME"] = str(_TMP)
os.environ["JARVIS_LOG_DIR"] = str(_TMP / "logs")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py")
import jarvis_quick as Q  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class FakeSched:
    """The only scheduler surface `answer()` touches, and only inside
    try/except. A test never opens a real schedule.db."""

    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def forget_set(self, *a, **k):
        pass


def fake_fetch(manifest=None, error=None, calls=None):
    def fetch():
        if calls is not None:
            calls.append(1)
        return (dict(manifest) if manifest is not None else None), error
    return fetch


DESKTOP = {"version": "0.2.318", "can_update": True}
NEWER = {"version": "0.2.320", "notes": "Fixed the thing.\nAdded the other thing."}


# ---------------------------------------------------------------------------
# 1. the words
# ---------------------------------------------------------------------------

def t_the_three_questions_answer():
    for text, intent in (
        ("is there an update", "update_ask"),
        ("is there an update available", "update_ask"),
        ("any updates?", "update_ask"),
        ("is Jarvis up to date", "update_ask"),
        ("do I need an update", "update_ask"),
        ("what version am I on", "update_ask"),
        ("check for updates", "update_ask"),
        ("what changed in the update", "update_notes"),
        ("what's new in the update", "update_notes"),
        ("what is in the latest version", "update_notes"),
        ("what does the update change", "update_notes"),
        ("update Jarvis", "update_start"),
        ("update, Jarvis", "update_start"),
        ("update", "update_start"),
        ("start the update", "update_start"),
        ("install the update", "update_start"),
        ("do the update", "update_start"),
        ("update to the latest version", "update_start"),
    ):
        got = Q.match(text)
        check(f"{text!r} -> {intent}",
              got is not None and got.name == intent,
              f"got {got.name if got else None}")


UPDATE_INTENTS = {"update_ask", "update_notes", "update_start"}


def t_the_near_misses_are_not_update_commands():
    # Some of these are answered by an OLDER fast path ("what's new" by "what
    # did I miss?", "what's the weather like" by the weather). What matters is
    # that none of them is taken for the update grammar; the rest go to the
    # model as before.
    for text in (
        "what's new",
        "what's new with you",
        "how do I update Jarvis",
        "when is the next update",
        "update my settings",
        "update my address in the email",
        "did the update break anything",
        "what changed in the settings",
        "what's the weather like",
    ):
        got = Q.match(text)
        check(f"{text!r} is not an update command",
              got is None or got.name not in UPDATE_INTENTS,
              f"matched {got.name if got else None}")


def t_the_desktop_report_is_validated():
    check("a full report is read", Q._desktop_build(
        {"version": "0.2.320", "can_update": True}) == {
            "version": "0.2.320", "can_update": True})
    check("a missing can_update is 'cannot update'",
          Q._desktop_build({"version": "0.2.320"})["can_update"] is False)
    check("a truthy non-boolean is not a yes",
          Q._desktop_build({"version": "0.2.320", "can_update": 1})["can_update"]
          is False)
    for junk in (None, "", [], {"version": "not a version"},
                 {"version": "0.2.320; rm -rf"}, {"version": 320},
                 {"version": "0.2.320.1.2"}):
        check(f"junk report rejected: {junk!r}", Q._desktop_build(junk) is None)


# ---------------------------------------------------------------------------
# 2. the states
# ---------------------------------------------------------------------------

def t_each_state_says_its_own_true_thing():
    no_build = Q._update_answer("update_ask", None, fetch=fake_fetch(NEWER))
    check("no build report: says it cannot tell which build is asking",
          "which version is running" in no_build.reply
          and "Settings" in no_build.reply and "Platform checks" in no_build.reply,
          no_build.reply)

    cannot = Q._update_answer("update_ask",
                              {"version": "0.2.318", "can_update": False},
                              fetch=fake_fetch(NEWER))
    check("no update key: says this build cannot check or install",
          "no update key" in cannot.reply and "0.2.318" in cannot.reply,
          cannot.reply)

    failed = Q._update_answer("update_ask", DESKTOP,
                              fetch=fake_fetch(None, "URLError: no route"))
    check("a failed check says the check failed and nothing changed",
          "check failed" in failed.reply and "Nothing was changed" in failed.reply
          and "no route" in failed.reply, failed.reply)

    newest = Q._update_answer("update_ask",
                              {"version": "0.2.320", "can_update": True},
                              fetch=fake_fetch({"version": "0.2.320", "notes": "x"}))
    check("the newest version says so", "newest published" in newest.reply,
          newest.reply)

    newer_here = Q._update_answer("update_ask",
                                  {"version": "0.2.400", "can_update": True},
                                  fetch=fake_fetch(NEWER))
    check("a build ahead of the release page says it is a development build",
          "development build" in newer_here.reply and "0.2.400" in newer_here.reply,
          newer_here.reply)

    avail = Q._update_answer("update_ask", DESKTOP, fetch=fake_fetch(NEWER))
    check("an update names the version and the running one",
          "Version 0.2.320 is available" in avail.reply
          and "0.2.318" in avail.reply, avail.reply)
    check("an update says nothing installs on its own",
          "nothing installs on its own" in avail.reply.lower(), avail.reply)


def t_what_changed_never_invents_a_list():
    got = Q._update_answer("update_notes", DESKTOP, fetch=fake_fetch(NEWER))
    check("the release's own notes are quoted",
          "Fixed the thing." in got.reply and "Added the other thing." in got.reply,
          got.reply)
    check("a notes list for one release says that is all it covers "
          "(the build is more than one release behind)",
          "only" in got.reply and "between 0.2.318 and it" in got.reply, got.reply)

    empty = Q._update_answer("update_notes", DESKTOP,
                             fetch=fake_fetch({"version": "0.2.320", "notes": "  "}))
    check("empty notes: says the release does not say, and will not invent",
          "does not say what changed" in empty.reply
          and "will not make something up" in empty.reply, empty.reply)

    one_behind = Q._update_answer(
        "update_notes", {"version": "0.2.319", "can_update": True},
        fetch=fake_fetch(NEWER))
    check("one release behind: no 'between' caveat, because there is none",
          "only" not in one_behind.reply and "between" not in one_behind.reply,
          one_behind.reply)

    long_notes = Q._update_answer(
        "update_notes", DESKTOP,
        fetch=fake_fetch({"version": "0.2.320", "notes": "x" * 4000}))
    check("a huge notes body is trimmed, and says it was",
          len(long_notes.reply) < 1700 and "the rest is on the release page"
          in long_notes.reply, str(len(long_notes.reply)))


def t_versions_are_compared_as_numbers():
    check("0.2.100 is newer than 0.2.99",
          Q._version_parts("0.2.100") > Q._version_parts("0.2.99"))
    check("a v prefix is accepted", Q._version_parts("v0.2.3") == (0, 2, 3, 0))
    check("a non-version is None", Q._version_parts("latest") is None)


# ---------------------------------------------------------------------------
# 3. starting it: ONE card, and nothing else
# ---------------------------------------------------------------------------

def t_one_card_only_when_there_is_an_update():
    raised = []
    reply = Q._run_update_start(
        DESKTOP, fetch=fake_fetch(NEWER),
        tier_of=lambda a: ("ask" if a == Q.UPDATE_ACTION else "never"),
        spawn=lambda fn: raised.append(fn))
    check("one card is raised for a real update", len(raised) == 1, str(raised))
    check("the reply says one card is waiting and nothing has happened yet",
          "One card is waiting" in reply.reply
          and "Nothing has been downloaded or changed" in reply.reply,
          reply.reply)
    check("the reply names the version", "0.2.320" in reply.reply, reply.reply)
    check("the intent is update_start", reply.intent == "update_start")

    for label, desktop, manifest in (
        ("no build report", None, NEWER),
        ("no update key", {"version": "0.2.318", "can_update": False}, NEWER),
        ("the check failed", DESKTOP, None),
        ("already newest", {"version": "0.2.320", "can_update": True},
         {"version": "0.2.320"}),
        ("a development build", {"version": "0.2.400", "can_update": True}, NEWER),
    ):
        raised = []
        fetch = fake_fetch(None, "down") if manifest is None else fake_fetch(manifest)
        got = Q._run_update_start(
            desktop, fetch=fetch, tier_of=lambda a: "ask",
            spawn=lambda fn: raised.append(fn))
        check(f"{label}: no card is raised", not raised, str(raised))
        # The start reuses the check's own honest sentence rather than claiming
        # anything happened: nothing was started, so nothing needs undoing.
        said = Q._update_answer("update_ask", desktop, fetch=fetch).reply
        check(f"{label}: the check's own words are the answer", got.reply == said,
              got.reply)


def t_a_stricter_tier_raises_no_card():
    raised = []
    got = Q._run_update_start(DESKTOP, fetch=fake_fetch(NEWER),
                              tier_of=lambda a: "never",
                              spawn=lambda fn: raised.append(fn))
    check("tier never: no card", not raised)
    check("tier never: says why, and that nothing changed",
          "'never'" in got.reply and "did not raise a card" in got.reply
          and "Nothing was changed" in got.reply, got.reply)


def t_a_spawn_that_fails_claims_no_card():
    def boom(fn):
        raise RuntimeError("no thread")
    got = Q._run_update_start(DESKTOP, fetch=fake_fetch(NEWER),
                              tier_of=lambda a: "ask", spawn=boom)
    check("a spawn failure is reported, not a card", "could not raise" in got.reply,
          got.reply)


def t_the_card_says_exactly_what_will_happen():
    held, seen = {}, {}

    def gate(action, detail, prompt=""):
        seen["action"] = action
        seen["detail"] = detail
        seen["prompt"] = prompt

    """The card the module builds, driven through its own default gate slot."""
    old_gate = Q._update_gate
    Q._update_gate = gate
    try:
        Q._run_update_start(DESKTOP, fetch=fake_fetch(NEWER),
                            tier_of=lambda a: "ask",
                            spawn=lambda fn: held.setdefault("fn", fn))
        held["fn"]()          # the card thread, exactly as the module spawns it
    finally:
        Q._update_gate = old_gate

    check("the card's action is desktop_update", seen.get("action") == Q.UPDATE_ACTION)
    detail, prompt = seen["detail"], seen["prompt"]
    check("the card's exact line names the backend first, the version and the restart",
          "backend first" in detail["text"]
          and "Jarvis Desktop 0.2.320" in detail["text"]
          and "app restarts" in detail["text"], json.dumps(detail))
    check("the card says it leaves this PC (the download)",
          detail.get("leaves_this_pc") is True, json.dumps(detail))
    for phrase in ("Jarvis wants to update itself",
                   "test suites",
                   "checks its signature",
                   "then the app restarts",
                   "Pace: Balanced",
                   "Nothing is downloaded, installed or changed before you approve",
                   "only be approved on this PC"):
        check(f"the card's full words say {phrase!r}", phrase in prompt, prompt)


def t_the_card_thread_only_asks_the_gate():
    """The one function that runs after a yes may not download, install or
    start anything: the desktop shell executes the update it already owns."""
    src = Path(Q.__file__).read_text(encoding="utf-8")
    block = re.search(r"def _update_card_thread\(.*?\n\ndef ", src, re.S)
    check("_update_card_thread exists", block is not None)
    if block:
        body = block.group(0)
        # The docstring SAYS "must never download, install or start anything";
        # what matters is that the CODE does not.
        code = body.split('"""')[-1] if '"""' in body else body
        for forbidden in ("urllib", "_release_manifest", "subprocess",
                          "os.system", "Popen", "install", "apply-patches"):
            check(f"the card thread's code does not mention {forbidden!r}",
                  forbidden not in code, code[:400])
        check("the card thread calls the gate",
              "gate(UPDATE_ACTION, detail, prompt)" in code)
    for forbidden in ("subprocess", "os.system", "Popen"):
        check(f"jarvis_quick does not import/execute {forbidden!r}",
              forbidden not in src)


# ---------------------------------------------------------------------------
# 4. the gate's own tables
# ---------------------------------------------------------------------------

def t_the_card_is_pc_only_and_ask():
    import jarvis_owner_check as O
    import jarvis_card_words as W
    check("desktop_update is PC-only (Windows Hello, this PC only)",
          Q.UPDATE_ACTION in O.PC_ONLY_ACTIONS, sorted(O.PC_ONLY_ACTIONS))
    check("it has a written title, not the fallback",
          W.has_written_title(Q.UPDATE_ACTION))
    summary = W.summary_for(Q.UPDATE_ACTION)
    check("it has short words, within the limit",
          len(summary.split()) <= W.SUMMARY_MAX_WORDS, summary)
    check("its short words say update and restart",
          "update" in summary.lower() and "restart" in summary.lower(), summary)

    conf = (ROOT / "backend" / "rebuilt" / "jarvis-framework.toml").read_text(
        encoding="utf-8")
    row = re.search(r'^desktop_update\s*=\s*"([a-z]+)"', conf, re.M)
    check("the framework's tier table lists desktop_update as ask",
          row is not None and row.group(1) == "ask", row.group(0) if row else "absent")
    twin = (ROOT / "jarvis-backend" / "jarvis-framework.toml").read_text(
        encoding="utf-8")
    check("the base's framework copy carries the same row",
          row is not None and row.group(0) in twin)


# ---------------------------------------------------------------------------
# 5. the twin, the URL, and the body wiring
# ---------------------------------------------------------------------------

def t_the_twin_is_byte_identical():
    a = (ROOT / "backend" / "jarvis_quick.py").read_bytes()
    b = (ROOT / "jarvis-backend" / "jarvis_quick.py").read_bytes()
    check("jarvis-backend/jarvis_quick.py is the same file", a == b)


def t_the_manifest_url_is_the_apps_own():
    conf = json.loads((ROOT / "jarvis-desktop" / "src-tauri" / "tauri.conf.json")
                      .read_text(encoding="utf-8"))
    endpoints = conf["plugins"]["updater"]["endpoints"]
    check("the module reads the endpoint the app's updater reads",
          Q.UPDATE_MANIFEST_URL in endpoints, f"{Q.UPDATE_MANIFEST_URL} vs {endpoints}")


def t_the_body_carries_the_desktop_facts_through():
    """`answer_turn` has no test here (it opens the real scheduler); the line
    that hands the body's facts to the grammar is pinned instead, and
    `answer()` is driven directly with the same value."""
    src = Path(Q.__file__).read_text(encoding="utf-8")
    check("answer_turn reads body['desktop']",
          'desktop = body.get("desktop") if isinstance(body, dict) else None' in src)
    check("answer_turn passes it to answer()", "desktop=desktop" in src)
    check("answer() passes it to run()", "messages=messages, desktop=desktop" in src)

    Q._release_manifest = fake_fetch(NEWER)
    got = Q.answer("is there an update", sched=FakeSched(), desktop=DESKTOP)
    check("the whole route answers without the model",
          got is not None and got.intent == "update_ask"
          and "0.2.320" in got.reply, got.reply if got else None)
    missing = Q.answer("is there an update", sched=FakeSched(), desktop=None)
    check("a body with no desktop facts says it cannot tell which build",
          missing is not None and "which version is running" in missing.reply,
          missing.reply if missing else None)


def t_the_route_line_is_unchanged():
    res = Q.Result("x", "update_ask")
    route = Q.route_fields(res)
    check("an update answer adds nothing to X-Jarvis-Route",
          set(route) == {"quick", "where", "lane", "inject_memory",
                         "injected_facts", "injected_ids", "injected_sensitive"},
          sorted(route))
    check("its quick name is the intent", route["quick"] == "update_ask")


if __name__ == "__main__":
    for fn in (t_the_three_questions_answer, t_the_near_misses_are_not_update_commands,
               t_the_desktop_report_is_validated, t_each_state_says_its_own_true_thing,
               t_what_changed_never_invents_a_list, t_versions_are_compared_as_numbers,
               t_one_card_only_when_there_is_an_update,
               t_a_stricter_tier_raises_no_card,
               t_a_spawn_that_fails_claims_no_card,
               t_the_card_says_exactly_what_will_happen,
               t_the_card_thread_only_asks_the_gate,
               t_the_card_is_pc_only_and_ask, t_the_twin_is_byte_identical,
               t_the_manifest_url_is_the_apps_own,
               t_the_body_carries_the_desktop_facts_through,
               t_the_route_line_is_unchanged):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
