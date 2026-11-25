"""test_self_knowledge.py - the 2026-11-07 self-knowledge honesty bundle.

    python3 backend/test_self_knowledge.py

WHAT THIS PROVES, AND WHY EACH CHECK IS HERE

The feature self-awareness audit of 2026-11-07 measured the live backend
DENYING capabilities this PC really has (approval policy changeable by chat,
chat history, spending limits, watches and the CI watcher) and inventing
others ("I haven't changed"; a made-up cost-line meaning). The owner's ruling
was that Jarvis must know its own recent features and settings. This suite
holds the fixed answers that replaced the model's guesses:

1. F1/F15: the four false-denial families each have a DETERMINISTIC answer from
   `jarvis_feature_guide.SELF_FACTS`, reached through `jarvis_quick.match`, and
   the approval-policy words name the card, the second yes and Windows Hello.
2. F2: "what changed in your last update?" is `recent_changes`, answers from
   the generated module with the version and real bullets, and every bullet the
   module carries is a real bullet of the record, in the record's own order. A
   pull request is allowed to leave the module ONE MERGE BEHIND (the owner's
   ruling Q2, 2026-11-15: `main` regenerates it after the merge, in the
   self-code-map workflow, so two PRs adding fragments never rewrite the same
   file); byte-exact freshness is demanded only when
   `JARVIS_RECENT_CHANGES_STRICT=1`, which that workflow sets.
3. F4: "can you explain any setting" and "how do I find out what a setting is
   set to" reach the explain door, and a named "what is X set to?" resolves to
   the real registry row.
4. F6: scoped Anti-Slop never claims "on" while the filter's own switch is
   off, and an already-off scope change reports that it changed nothing.
5. F13: a toggle that asks for the value a switch already has says "already"
   and never calls the setter (so it writes no receipt).
6. F14: the off-list functions answer with their real place ("face size" is
   the HUD faces panel, never Settings, Shortcuts).
7. Q4: the two heritage halves answer deterministically and the record's
   named borrows appear - Muse, OpenMuse, ChatGPT Dots, Hermes - with the
   concrete ideas (one-card email, /api/reach, Long Fuse, redirect_note,
   hidden Unicode, "What it costs", curator_lock, session search). The lineage
   answer is read from the same table the model digest uses.
8. Q3: a two-part capability question returns EVERY row it really names, in
   the owner's order, up to three - newline-joined, never just the first.
9. WHERE THE CHATS ARE KEPT (2026-11-13): "where are my chats stored?", "are my
   chats saved?", "do you keep a record of this?", "where are the chat backups
   stored?", "is my history encrypted?" and "what happens to my voice
   transcripts?" reach `chat_history_storage`, answered from
   `jarvis_chat_log`'s own settings and its own file - on by default,
   encrypted, where it lives, voice included, and the switch that turns it off
   named as each app draws it. When the switch is off, or the record cannot be
   read, the answer says THAT rather than the default sentence; an unrelated
   question is not captured; and the false answer the live backend gave the
   owner - "Chat backups aren't stored anywhere ... until you close it or clear
   them" - never comes back in any state.

Everything here is read-only: the setters are replaced with raising stubs
where a change path is exercised, so no card can be raised and no file can be
written by this suite. That includes the chat-storage checks: their history is
a scratch ChatLog in a temporary folder and its key provider is never called.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FAILED, PASSED = [], []


def check(name, fn):
    try:
        fn()
    except AssertionError as exc:
        FAILED.append(f"{name}: {exc}")
        print(f"FAIL  {name}")
        print(f"      {exc}")
    except Exception as exc:  # noqa: BLE001 - a crash is a failure, named
        FAILED.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"FAIL  {name}")
        print(f"      {type(exc).__name__}: {exc}")
    else:
        PASSED.append(name)
        print(f"ok    {name}")


def _quick():
    import jarvis_quick as Q
    return Q


def test_approval_policy_is_deterministic():
    Q = _quick()
    for ask in ("can you change what needs an approval card by talking to you?",
                "can you change the approval policy?",
                "can i change what needs an approval card?"):
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (ask, got)
        assert got.f.get("family") == "approval_policy", (ask, got.f)
    out = Q._run_self_knowledge({"family": "approval_policy"})
    words = str(out.reply)
    for need in ("approval card", "second yes", "Windows Hello", "no bulk form"):
        assert need.lower() in words.lower(), (need, words[:200])
    assert "approval_policy" not in words, "raw snake_case key leaked to the owner"


def test_four_false_denial_families_answer():
    Q = _quick()
    cases = {
        "approval_policy": "can you change what needs an approval card by talking to you?",
        "watches_ci": "do you have watches?",
        "spending_limits": "do you have spending limits?",
        "chat_history": "how long do you keep my chat history, and can I change that by asking?",
    }
    for family, ask in cases.items():
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (family, got)
        assert got.f.get("family") == family, (family, got.f)
        out = Q._run_self_knowledge({"family": family})
        words = str(out.reply)
        assert len(words) > 80, (family, words)
        for denial in ("i don't have", "i do not have", "isn't a feature", "not a feature i have"):
            assert denial not in words.lower(), (family, denial)


def _recent_changes_generator():
    """The generator module itself, so its own uncapped record can be read."""
    sys.path.insert(0, str(HERE.parent / "tools"))
    try:
        import gen_recent_changes
    finally:
        sys.path.pop(0)
    return gen_recent_changes


def test_recent_changes_answer_and_generator():
    Q = _quick()
    got = Q.match("what changed in your last update?")
    assert got is not None and got.name == "recent_changes", got
    got = Q.match("what's new in you?")
    assert got is not None and got.name == "recent_changes", got
    # IS THE MODULE HONEST? Every bullet it carries must be a real bullet of the
    # record, in the record's own order. That is what "one merge behind" looks
    # like: the record has grown at the top, and the module is the same bullets
    # it always was. It is deliberately a SUBSEQUENCE and not a contiguous run,
    # because a real record moves underneath it in two legitimate ways - a
    # fragment can leave `changelog.d/` when the changelog roll folds it in, and
    # the module keeps only the newest `KEEP`. Both leave gaps. Neither lets an
    # invented, re-worded or re-ordered bullet through, which is the property
    # this suite is for. Freshness is main's job (ruling Q2), below.
    import jarvis_recent_changes as RC
    truth = _recent_changes_generator()
    carried = [b for b in RC.BULLETS if b]
    assert carried, "the generated module carries no bullets at all"
    assert len(carried) <= truth.KEEP, (
        f"the module carries {len(carried)} bullets; the generator ships {truth.KEEP}")
    record = truth.all_bullets()
    at = -1
    for bullet in carried:
        try:
            at = record.index(bullet, at + 1)
        except ValueError:
            raise AssertionError(
                "the module carries a bullet the record does not, in that order:\n"
                f"  module bullet: {bullet!r}\n"
                f"  record: {record[:12]!r}") from None
    # BYTE-EXACT FRESHNESS IS `main`'s BUSINESS (owner's ruling Q2, 2026-11-15):
    # the regeneration moved to the self-code-map workflow after each merge, so
    # a pull request is legitimately one merge behind and is not asked for it.
    if os.environ.get("JARVIS_RECENT_CHANGES_STRICT") == "1":
        gen = subprocess.run([sys.executable, str(HERE.parent / "tools" / "gen_recent_changes.py"),
                              "--check"], capture_output=True, text=True,
                             cwd=str(HERE.parent))
        assert gen.returncode == 0, gen.stdout + gen.stderr
    out = Q._run_recent_changes()
    words = str(out.reply)
    assert "newest changes on record are" in words, words[:300]
    assert "I haven't changed" not in words
    first = RC.bullets(1)[0]
    assert first in words, (first, words[:300])
    assert "version" in words.lower(), "version line missing from the answer"


def test_explain_door_shapes():
    Q = _quick()
    for ask in ("can you explain any setting with its current value and the exact phrase that changes it?",
                "explain your settings",
                "how do i find out what one of your settings is currently set to?"):
        got = Q.match(ask)
        assert got is not None and got.name == "settings_explain_all", (ask, got)
    out = Q._run_settings_explain_all()
    words = str(out.reply)
    for need in ("switch", "choice", "number setting", "what can i change"):
        assert need in words.lower(), (need, words[:200])
    named = Q.match("what is the anti-slop mode set to?")
    assert named is not None and named.name == "setting_explain", named
    assert named.f.get("key") == "antislop_mode", named.f
    words = str(Q._run_setting_explain(named.f).reply)
    assert "Right now:" in words, words[:300]


def test_scoped_antislop_never_claims_on_while_filter_off():
    Q = _quick()
    import jarvis_settings_registry as R
    called = []
    old_scope_now = R.antislop_scope_now
    old_set = R.set_antislop_scope
    old_read = Q._antislop_read_back
    old_receipt = Q._settings_receipt
    try:
        R.antislop_scope_now = lambda name: False
        R.set_antislop_scope = lambda name, want, **kw: (
            called.append((name, want)) or
            SimpleNamespace(ok=True, waiting=False, said="Anti-Slop on for code.",
                            receipt_id=""))
        Q._antislop_read_back = lambda key, window=6: (
            True if key.startswith("scope:") else False)   # filter itself OFF
        Q._settings_receipt = lambda *a, **k: None
        out = Q._run_settings_antislop_scope(
            {"scope": "code", "on": True}, peer="127.0.0.1", local=True)
        words = str(out.reply).lower()
        assert "still off" in words, words
        assert "anti-slop on for code" not in words, words
        assert called == [("code", True)], called
    finally:
        R.antislop_scope_now = old_scope_now
        R.set_antislop_scope = old_set
        Q._antislop_read_back = old_read
        Q._settings_receipt = old_receipt

    # already-on scope + filter off: say nothing is being filtered and change nothing
    try:
        R.antislop_scope_now = lambda name: True
        R.set_antislop_scope = lambda *a, **k: (_ for _ in ()).throw(AssertionError("setter called"))
        Q._antislop_read_back = lambda key, window=6: (
            True if key.startswith("scope:") else False)
        out = Q._run_settings_antislop_scope(
            {"scope": "code", "on": True}, peer="127.0.0.1", local=True)
        words = str(out.reply).lower()
        assert "still off" in words and "already on" in words, words
    finally:
        R.antislop_scope_now = old_scope_now
        R.set_antislop_scope = old_set
        Q._antislop_read_back = old_read


def test_unchanged_toggle_says_already_and_calls_no_setter():
    Q = _quick()
    import jarvis_settings_registry as R
    fake = SimpleNamespace(key="fake_switch", names=("fake switch",),
                           on_word="on", off_word="off",
                           set=lambda *a, **k: (_ for _ in ()).throw(
                               AssertionError("setter called for an unchanged toggle")))
    old_bools, old_current = R.BOOL_SETTINGS, R.current_value
    try:
        R.BOOL_SETTINGS = (fake,)
        R.current_value = lambda setting: "off"
        out = Q._run_settings_bool({"key": "fake_switch", "on": False},
                                   peer="127.0.0.1", local=True)
        words = str(out.reply).lower()
        assert "already off" in words and "nothing was changed" in words, words
    finally:
        R.BOOL_SETTINGS, R.current_value = old_bools, old_current


def test_off_list_places_answer_the_real_place():
    Q = _quick()
    import jarvis_feature_guide as G
    for target in ("face size", "standby hours", "attention budget", "notification styles"):
        assert G.place_for(target), target
    got = Q.match("where do i change the face size?")
    assert got is not None and got.name == "settings_where", got
    words = str(Q._run_settings_where(got.f).reply).lower()
    assert "faces panel" in words or "left rail" in words, words
    assert "shortcuts" not in words, "the audit's wrong place came back: " + words


def test_heritage_both_halves_and_named_borrows():
    Q = _quick()
    import jarvis_feature_guide as G
    got = Q.match("what makes you different from ChatGPT?")
    assert got is not None and got.name == "heritage", got
    assert got.f.get("part") == "differentiators", got.f
    got = Q.match("what did you borrow from Muse or ChatGPT Dots?")
    assert got is not None and got.name == "heritage", got
    assert got.f.get("part") == "lineage", got.f
    lineage = G.heritage_words("lineage")
    for name in ("Muse", "OpenMuse", "ChatGPT Dots", "Hermes"):
        assert name in lineage, (name, lineage[:300])
    for idea in ("one approval card per email", "/api/reach", "Long Fuse",
                 "deny-and-say-what-to-do-instead note", "hidden Unicode", "What it costs", "curator lock",
                 "session search", "provenance badges"):
        assert idea.lower() in lineage.lower(), (idea, lineage[:400])
    different = G.heritage_words("differentiators")
    for need in ("voice", "standing grants", "Windows Hello", "VACUUM",
                 "Meshnet", "Ollama"):
        assert need.lower() in different.lower(), (need, different[:300])
    both = Q._run_heritage({"part": "both"})
    assert "Muse" in str(both.reply) and "different" in str(both.reply).lower()


def test_two_part_capability_question_joins_every_row():
    Q = _quick()
    got = Q.match("can you search old chats and read my email?")
    assert got is not None and got.name == "capability_answer", got
    ids = got.f.get("ids") or []
    assert 2 <= len(ids) <= 3, ids
    out = Q._run_capability_answer({"ids": ids, "ask": False})
    words = str(out.reply)
    assert "\n" in words, "rows were not newline-joined: " + words[:300]
    assert "chat" in words.lower() and "email" in words.lower(), words[:300]


# ---------------------------------------------------------------------------
# WHERE THE CHATS ARE KEPT (2026-11-13, the owner's own question)
# ---------------------------------------------------------------------------
# Asked "where are the chat backups stored?", the live backend answered that
# they "aren't stored anywhere ... conversations live only in the app's memory
# until you close it or clear them" - false, and false in the worst direction:
# chat history, voice included, has been kept on this PC, encrypted, since the
# owner's decision of 2026-09-24 (jarvis_chat_log.py's own header).
#
# The architect's ruling (Gemini, 2026-11-13 22:30 PT, section 5.6) is that a
# self-fact about storage, history, privacy or settings is answered
# deterministically from the code, or refused - never composed by the model.
# Every check below FAILS if the rule is deleted: the shape then matches nothing
# (and reaches the model, whose answer was the false one) or answers with
# another intent.

STORAGE_ASKED = (
    "where are my chats stored?",
    "are my chats saved?",
    "do you keep a record of this?",
    "where are the chat backups stored?",
    "is my history encrypted?",
    "what happens to my voice transcripts?",
)

#: The exact false answer the live backend gave the owner on 2026-11-13. Not
#: one phrase of it may come back, in any state.
THE_OLD_LIE = (
    "aren't stored anywhere",
    "are not stored anywhere",
    "not stored anywhere",
    "only in the app's memory",
    "in the app's memory",
    "until you close it",
    "clear them",
    "throwaway",
)


def _storage_log(state="on", db="present"):
    """A scratch ChatLog, plus its folder. `state`: on / off / damaged.

    `db` is present or missing. No key is ever needed: the answer reads
    `settings()` and whether the file can be OPENED, never the cipher, so the
    provider below is never called - which is also the proof that answering
    this question writes nothing (a key would be minted only by the cipher).
    """
    import jarvis_chat_log as C
    d = Path(tempfile.mkdtemp(prefix="jarvis-chat-storage-"))
    settings = d / "chat-history.json"
    if state == "off":
        settings.write_text(json.dumps({"enabled": False, "keep_days": 0}), encoding="utf-8")
    elif state == "damaged":
        settings.write_text("{ this is not json", encoding="utf-8")
    db_path = d / "chat-history.db"
    if db == "present":
        db_path.write_bytes(b"SQLite format 3\x00")
    return d, C.ChatLog(db_path, settings, lambda: b"\x00" * 32)


def test_chat_storage_questions_are_deterministic():
    Q = _quick()
    import jarvis_chat_log as C
    old = C._DEFAULT
    _, log = _storage_log()
    try:
        C.use(log)
        for ask in STORAGE_ASKED:
            got = Q.match(ask)
            assert got is not None and got.name == "chat_history_storage", (ask, got)
            out = Q.answer(ask)
            assert out is not None, f"{ask} reached the model"
            assert out.intent == "chat_history_storage", (ask, out.intent)
            assert out.made == [], (ask, "a job was made: " + repr(out.made))
            assert out.open_settings is None, (ask, out.open_settings)
    finally:
        C.use(old)


def test_chat_storage_answer_states_the_true_facts():
    Q = _quick()
    import jarvis_chat_log as C
    old = C._DEFAULT
    _, log = _storage_log()
    try:
        C.use(log)
        words = str(Q.answer("where are my chats stored?").reply)
    finally:
        C.use(old)
    low = words.lower()
    for need in ("on by default", "encrypted", "aes-256-gcm", "credential manager",
                 "chat-history.db", ".openjarvis", "voice",
                 "chat history on this pc", "keep chat history on this pc",
                 "turn it off", "approval card"):
        assert need in low, (need, words[:400])
    for lie in THE_OLD_LIE:
        assert lie not in low, ("the old false answer came back", lie, words[:400])
    assert "chat_history_storage" not in words, "a raw intent name leaked: " + words[:200]


def test_chat_storage_says_off_when_the_switch_is_off():
    Q = _quick()
    import jarvis_chat_log as C
    old = C._DEFAULT
    _, log = _storage_log(state="off")
    try:
        C.use(log)
        words = str(Q.answer("are my chats saved?").reply)
        raw = str(Q.answer("where are my chats stored?").reply)
    finally:
        C.use(old)
    for said in (words, raw):
        low = said.lower()
        assert "off right now" in low, said[:300]
        assert "on by default" not in low, said[:300]
        assert "nothing new is kept" in low, said[:300]
        # where it lives and that it is encrypted are still true when off
        assert "chat-history.db" in low and "encrypted" in low, said[:300]
        assert "turning it on raises one approval card" in low, said[:300]
        for lie in THE_OLD_LIE:
            assert lie not in low, (lie, said[:300])


def test_chat_storage_never_claims_what_it_cannot_read():
    Q = _quick()
    import jarvis_chat_log as C
    old = C._DEFAULT
    # (a) a settings file that cannot be read: nothing is being kept, and the
    # answer says that instead of the default sentence.
    d, log = _storage_log(state="damaged")
    try:
        C.use(log)
        words = str(Q.answer("where are my chats stored?").reply)
    finally:
        C.use(old)
    low = words.lower()
    assert "cannot keep anything right now" in low, words[:300]
    assert "on by default" not in low, words[:300]
    for lie in THE_OLD_LIE:
        assert lie not in low, (lie, words[:300])
    # ... and the settings file's own path, which carries the owner's Windows
    # account name, is not repeated into a reply that also reaches the phone.
    assert str(d).lower() not in low, ("the settings path leaked", words[:400])

    # (b) the module cannot be read at all: refuse, and claim nothing.
    _, log2 = _storage_log()
    real = C._log
    try:
        C.use(log2)
        C._log = lambda: (_ for _ in ()).throw(RuntimeError("unreadable"))
        said = Q.answer("where are my chats stored?")
    finally:
        C._log = real
        C.use(old)
    assert said is not None, "the question reached the model"
    low = str(said.reply).lower()
    assert "won't guess" in low, said.reply[:300]
    for claim in ("on by default", "encrypted", "chat-history.db", ".openjarvis"):
        assert claim not in low, ("claimed what it could not read", claim, said.reply[:300])


def test_chat_storage_is_not_a_general_q_and_a():
    Q = _quick()
    for ask in ("save this chat to a file",
                "save my chat as a note",
                "where are my notes stored",
                "where are my photos kept",
                "where are my reminders stored",
                "delete my chat history",
                "clear my chat history",
                "where is my history",
                "do you keep a record of my passwords"):
        got = Q.match(ask)
        assert got is None or got.name != "chat_history_storage", (ask, got)
    # The families that already owned their shapes still own them.
    kept = Q.match("how long do you keep my chat history, and can I change that by asking?")
    assert kept is not None and kept.name == "self_knowledge", kept
    for ask in ("do you keep chat history?", "do you have chat history?",
                "is my chat history on?"):
        kept = Q.match(ask)
        assert kept is not None and kept.name == "self_knowledge", (ask, kept)
    # ... and so do the clearing / size / expiry shapes history_purge answers.
    purge = Q.match("how big is my chat history")
    assert purge is not None and purge.name == "history_purge", purge
    # The rule this test is the fence around must still BE there: a suite that
    # only proved "nothing is captured" would pass with the whole rule deleted.
    assert Q.match("where are the chat backups stored?").name == "chat_history_storage"


def test_chat_storage_writes_nothing_and_raises_no_card():
    Q = _quick()
    import jarvis_chat_log as C
    old = C._DEFAULT
    _, log = _storage_log()
    called = []
    real_set = log.set_enabled
    real_req = C.request_settings
    try:
        C.use(log)
        log.set_enabled = lambda *a, **k: called.append("set_enabled")
        C.request_settings = lambda *a, **k: called.append("request_settings")
        said = Q.answer("where are the chat backups stored?")
    finally:
        log.set_enabled = real_set
        C.request_settings = real_req
        C.use(old)
    assert called == [], ("a write path was taken", called)
    assert said is not None and said.made == [], said
def test_wake_word_activation_answer_is_the_catalogues_own():
    """The owner's own question, answered from the catalogue (2026-11-13).

    MEASURED WRONG ANSWER: "You turn it on by saying 'Hey Jarvis' out loud when
    the app is open and has microphone access granted" - it described the wake
    word as self-activating. The catalogue's row says "Turn it on in Settings,
    Voice, then tap Listen on the phone" and "Turning it on raises one approval
    card on the PC. Turning it off is instant"; the phone's own
    VoiceSwitchesPlate.kt says its listening is never on by default or after a
    restart. This pins the deterministic answer for the exact question and its
    natural variants, and pins that it never claims the false half.
    """
    Q = _quick()
    import jarvis_feature_guide as G
    row = G.row_by_id("wake-word")
    assert row is not None, "the catalogue has no wake-word row"
    out = Q._run_wake_word_howto()
    words = str(out.reply)
    low = words.lower()
    asks = ("How do I activate Hey Jarvis on my Android app?",
            "how do I turn on Hey Jarvis on my phone?",
            "how do I enable the wake word on Android?")
    for ask in asks:
        got = Q.match(ask)
        assert got is not None and got.name == "wake_word_howto", (ask, got)
        assert got.f.get("id") == "wake-word", (ask, got.f)
        live = Q.answer(ask)
        assert live is not None and str(live.reply) == words, (ask, live)
    assert str(row["where"]) in words, (row["where"], words)
    assert str(row["asks"]) in words, (row["asks"], words)
    for need in ("Settings, Voice", "Listen on the phone", "approval card",
                 "two switches", "never on by default or after a restart"):
        assert need.lower() in low, (need, words)
    assert 'saying "hey jarvis" out loud does not switch it on' in low, words
    # "hey Jarvis" is the switch's NAME, not an address: the tail normaliser
    # used to strip "jarvis", turning the owner's own sentence into "turn on
    # hey" and missing the switch entirely. This pins the one-line fix.
    got = Q.match("turn on hey jarvis")
    assert got is not None and got.name == "settings_wake_word", got
    assert got.f.get("on") is True, got.f
    for wrong in ("say it and it turns on", "out loud when the app is open",
                  "is on by default", "starts by itself", "no on/off switch",
                  "command-only", "planned"):
        assert wrong not in low, (wrong, words)


# ---------------------------------------------------------------------------
# THE TWO SENTENCES THIS WORK MADE TRUE (2026-11-25)
# ---------------------------------------------------------------------------
# Both sentences came from the two rescued branches (2026-11-07/09) and both
# were false on main at 0922b44d. Each check reads the module that OWNS the
# fact, so a future reword cannot quietly make the sentence false again, and
# each FAILS if the honesty is reverted - which is the property that matters:
# a suite that only proved "some answer exists" would pass with either fault
# present.


def test_notification_styles_place_is_the_style_modules_own_hint():
    """The answer names the row the style module names, not a guess.

    MEASURED WRONG ON MAIN at 0922b44d: "...the phone's own: Settings,
    Appearance, notification styles ... The PC has no card for them" - but the
    phone draws `NotificationStylesSection` inside the Settings row
    "Notifications from Jarvis" (`JarvisNotifyPlate.kt`), and the PC STORES the
    six values (`jarvis_notification_styles.py`: "the PC stores only the six
    values above"). So the old words sent the owner to a row that does not hold
    the control and denied a thing the PC really does.

    The owning module ships both halves in its own words - `PREVIEW_HINT` names
    where the preview is seen, `NO_CARD` says why no approval card is raised -
    so this check reads THOSE, never a hand copy.
    """
    import jarvis_feature_guide as G
    import jarvis_notification_styles as N
    Q = _quick()
    place = G.place_for("notification styles")
    assert place, "the off-list place table lost notification styles"
    words = str(place.get("words") or "")
    # Half 1: the place is the module's own hint, word for word.
    assert "Settings, Notifications from Jarvis" in N.PREVIEW_HINT, N.PREVIEW_HINT
    assert "Settings, Notifications from Jarvis" in words, words
    # Half 2: the card rule is the module's own, not a guess.
    assert "no approval card" in N.NO_CARD.lower(), N.NO_CARD[:200]
    assert "no approval card" in words.lower(), words
    # The wrong row the audit-era words named must not come back.
    assert "appearance" not in words.lower(), (
        "the 2026-11-07 wrong place came back: " + words)
    # ... and the chat answer IS those words: one table, one answer.
    got = Q.match("where do I change the notification styles?")
    assert got is not None and got.name == "settings_where", got
    reply = str(Q._run_settings_where(got.f).reply)
    assert reply == words, (reply, words)


def test_skills_digest_does_not_card_turning_a_skill_off():
    """The digest's card rule is the Skills module's own note.

    MEASURED WRONG ON MAIN at 0922b44d: "turns one off/on and edits one - each
    behind ONE approval card". The module's own `menu()` note says the opposite
    for OFF: "Turning one off, and removing one - installed or turned off - are
    immediate", and `skill_uninstall` is the "auto" row. The live model reads
    this digest, so the over-claim was a false capability sentence of exactly
    DEF-093's class: a statement about its own cards that the registry does not
    back.
    """
    import inspect
    import jarvis_agent as A
    import jarvis_skill_menu as SM
    Q = _quick()
    digest = A.LANE_SYSTEM
    assert "turning one off, and removing one, are immediate" in digest, digest[-600:]
    assert "turns one off/on" not in digest, "the over-claim came back"
    # The module's own note carries both halves; read it, do not copy it.
    note = inspect.getsource(SM.menu)
    assert "are immediate" in note, note[-600:]
    assert "ONE approval card" in note, note[-600:]
    # The chat answer's fallback note (used when the skills module cannot be
    # read on this PC) says the same two halves as the module.
    fallback = Q._skill_menu_words()[1]
    assert "ONE approval card" in fallback and "immediate" in fallback, fallback


def test_skills_digest_is_one_line_in_every_copy():
    """The corrected line is in all five copies, and none keeps the old claim.

    The digest reaches the model through five files (`jarvis-primary.Modelfile`,
    `jarvis_agent.LANE_SYSTEM`, `jarvis_profiles.JARVIS_SYSTEM`, the try-out
    Modelfile and `test_character.CAPABILITY_LINES`); the suite already pins
    that they are word-for-word equal, and this row pins the two halves of the
    repaired claim in each, so a fix in one copy only is a FAIL here.
    """
    files = (
        HERE / "jarvis-primary.Modelfile",
        HERE / "jarvis_agent.py",
        HERE / "jarvis_profiles.py",
        HERE.parent / "tools" / "model_tryout" / "Modelfile.jarvis-qwen35-9b",
        HERE / "test_character.py",
    )
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "Jarvis has a real Skills menu too" in text, path.name
        region = text.split("Jarvis has a real Skills menu too", 1)[1]
        region = region.split("Never say you cannot install skills", 1)[0]
        # Join the Python string literals the wrapped copies are written in, so
        # the SAME words can be found in a one-line Modelfile and in a wrapped
        # `jarvis_profiles.py` literal.
        flat = "".join(region.replace('"', "").replace("\\", "").split())
        assert "turningoneoff,andremovingone,areimmediate" in flat, path.name
        assert "eachbehindONEapprovalcard" in flat, path.name
        assert "turnsoneoff/on" not in flat, f"{path.name} still over-claims"


def main():
    checks = [
        ("approval policy is deterministic", test_approval_policy_is_deterministic),
        ("four false-denial families answer", test_four_false_denial_families_answer),
        ("recent changes answer and generator", test_recent_changes_answer_and_generator),
        ("explain door shapes", test_explain_door_shapes),
        ("scoped anti-slop honesty", test_scoped_antislop_never_claims_on_while_filter_off),
        ("unchanged toggle makes no change", test_unchanged_toggle_says_already_and_calls_no_setter),
        ("off-list places answer", test_off_list_places_answer_the_real_place),
        ("notification styles place is the module's own hint",
         test_notification_styles_place_is_the_style_modules_own_hint),
        ("skills digest cards only what the module cards",
         test_skills_digest_does_not_card_turning_a_skill_off),
        ("skills digest is one line in every copy",
         test_skills_digest_is_one_line_in_every_copy),
        ("heritage both halves", test_heritage_both_halves_and_named_borrows),
        ("two-part capability joins rows", test_two_part_capability_question_joins_every_row),
        ("chat storage questions are deterministic", test_chat_storage_questions_are_deterministic),
        ("chat storage answer states the true facts", test_chat_storage_answer_states_the_true_facts),
        ("chat storage says off when the switch is off", test_chat_storage_says_off_when_the_switch_is_off),
        ("chat storage claims only what it can read", test_chat_storage_never_claims_what_it_cannot_read),
        ("chat storage is not a general Q and A", test_chat_storage_is_not_a_general_q_and_a),
        ("chat storage writes nothing and raises no card", test_chat_storage_writes_nothing_and_raises_no_card),
        ("wake word activation answers from the catalogue",
         test_wake_word_activation_answer_is_the_catalogues_own),
    ]
    for name, fn in checks:
        check(name, fn)
    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for item in FAILED:
            print(" -", item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
