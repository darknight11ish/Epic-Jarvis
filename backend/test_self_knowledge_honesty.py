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
   the generated module with the version and real bullets, and the generator
   `tools/gen_recent_changes.py --check` passes (a stale module fails here).
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

Everything here is read-only: the setters are replaced with raising stubs
where a change path is exercised, so no card can be raised and no file can be
written by this suite.
"""
from __future__ import annotations

import subprocess
import sys
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
        "offline_companion": "can you work offline?",
        "mobile_project_explorer": "what is mobile project explorer?",
        "mobile_web_preview": "what is mobile web preview?",
        "mobile_offline_tools": "what tools can you run offline?",
        "mobile_keystore_vault": "how are my mobile credentials secured?",
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


def test_offline_companion_self_knowledge():
    Q = _quick()
    for ask in (
        "can you work offline?",
        "can you run on my phone?",
        "do you have an on-device model?",
        "how does offline sync work?",
        "what is your mobile edge lane?",
    ):
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (ask, got)
        assert got.f.get("family") == "offline_companion", (ask, got.f)
    out = Q._run_self_knowledge({"family": "offline_companion"})
    words = str(out.reply)
    for need in ("on-device", "gguf", "llama.cpp", "offline store", "two-way sync", "settings"):
        assert need.lower() in words.lower(), (need, words[:200])


def test_mobile_project_explorer_self_knowledge():
    Q = _quick()
    for ask in (
        "can you explore projects on my phone?",
        "what is mobile project explorer?",
        "how does project explorer work?",
        "can i browse code on my phone?",
    ):
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (ask, got)
        assert got.f.get("family") == "mobile_project_explorer", (ask, got.f)
    out = Q._run_self_knowledge({"family": "mobile_project_explorer"})
    words = str(out.reply)
    for need in ("project explorer", "codebase", "symbol", "get /api/projects/{id}/map", "five rules of jarvis"):
        assert need.lower() in words.lower(), (need, words)


def test_mobile_web_preview_self_knowledge():
    Q = _quick()
    for ask in (
        "can you preview dev servers on my phone?",
        "what is mobile web preview?",
        "how does web preview work?",
        "is web preview sandboxed?",
    ):
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (ask, got)
        assert got.f.get("family") == "mobile_web_preview", (ask, got.f)
    out = Q._run_self_knowledge({"family": "mobile_web_preview"})
    words = str(out.reply)
    for need in ("web preview", "ports 3000, 5173, or 8080", "rules 1 and 2", "console logs"):
        assert need.lower() in words.lower(), (need, words)


def test_mobile_offline_tools_self_knowledge():
    Q = _quick()
    for ask in (
        "what tools can you run offline?",
        "what is the mobile agent dispatcher?",
        "how does mobile agent dispatcher work?",
        "can you run tools offline?",
    ):
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (ask, got)
        assert got.f.get("family") == "mobile_offline_tools", (ask, got.f)
    out = Q._run_self_knowledge({"family": "mobile_offline_tools"})
    words = str(out.reply)
    for need in ("mobile agent tool dispatcher", "take_note", "remember_fact", "device_status", "rule 4"):
        assert need.lower() in words.lower(), (need, words)


def test_mobile_keystore_vault_self_knowledge():
    Q = _quick()
    for ask in (
        "how are my mobile credentials secured?",
        "what is keystore vault?",
        "how does the keystore vault work?",
        "is my mobile data encrypted?",
    ):
        got = Q.match(ask)
        assert got is not None and got.name == "self_knowledge", (ask, got)
        assert got.f.get("family") == "mobile_keystore_vault", (ask, got.f)
    out = Q._run_self_knowledge({"family": "mobile_keystore_vault"})
    words = str(out.reply)
    for need in ("keystore", "aes-256-gcm", "trusted execution environment", "strongbox", "rule 3"):
        assert need.lower() in words.lower(), (need, words)


def test_recent_changes_answer_and_generator():
    Q = _quick()
    got = Q.match("what changed in your last update?")
    assert got is not None and got.name == "recent_changes", got
    got = Q.match("what's new in you?")
    assert got is not None and got.name == "recent_changes", got
    gen = subprocess.run([sys.executable, str(HERE.parent / "tools" / "gen_recent_changes.py"),
                          "--check"], capture_output=True, text=True,
                         cwd=str(HERE.parent))
    assert gen.returncode == 0, gen.stdout + gen.stderr
    out = Q._run_recent_changes()
    words = str(out.reply)
    assert "newest changes on record are" in words, words[:300]
    assert "I haven't changed" not in words
    import jarvis_recent_changes as RC
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


def main():
    checks = [
        ("approval policy is deterministic", test_approval_policy_is_deterministic),
        ("four false-denial families answer", test_four_false_denial_families_answer),
        ("offline companion self-knowledge", test_offline_companion_self_knowledge),
        ("mobile project explorer self-knowledge", test_mobile_project_explorer_self_knowledge),
        ("mobile web preview self-knowledge", test_mobile_web_preview_self_knowledge),
        ("mobile offline tools self-knowledge", test_mobile_offline_tools_self_knowledge),
        ("mobile keystore vault self-knowledge", test_mobile_keystore_vault_self_knowledge),
        ("recent changes answer and generator", test_recent_changes_answer_and_generator),
        ("explain door shapes", test_explain_door_shapes),
        ("scoped anti-slop honesty", test_scoped_antislop_never_claims_on_while_filter_off),
        ("unchanged toggle makes no change", test_unchanged_toggle_says_already_and_calls_no_setter),
        ("off-list places answer", test_off_list_places_answer_the_real_place),
        ("heritage both halves", test_heritage_both_halves_and_named_borrows),
        ("two-part capability joins rows", test_two_part_capability_question_joins_every_row),
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
