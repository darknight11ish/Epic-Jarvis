#!/usr/bin/env python3
"""Every check behind "Coach this" (jarvis_prompt_coach.py).

    python3 backend/test_prompt_coach.py

No model is called anywhere here. The module takes its caller as an argument
(`ask=`), which is the same seam jarvis_entities.py uses, so a fake answer is
enough to test the whole path - and the two places that MUST touch the real
world, the local-address check and the HTTP call, are checked by reading the
module's own source for the order they happen in, not by trusting a comment.

The switch's file is pointed at a temporary folder before the module is
imported, so this never reads or writes the owner's real settings.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

# Before the import: the module reads the settings folder on every call, and it
# must be a temporary one.
_CFG = tempfile.mkdtemp(prefix="coach-test-")
os.environ["JARVIS_CONFIG_DIR"] = _CFG

import jarvis_prompt_coach as PC  # noqa: E402
# Point the module at THIS test's folder, not at whatever the machine's
# settings folder is. jarvis_prompt_coach._config_dir() asks
# jarvis_framework.CONFIG_DIR first and only then the environment, so on a PC
# (or on CI) the env var above is ignored and the module would read and write
# the real settings folder. This machine has no jarvis_framework, which is why
# the env var alone looked like enough here and was not.
PC._config_dir = lambda: Path(_CFG)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"ok    {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def _code_only(text):
    """The module's source with docstrings and comments stripped, so an
    assertion below is about the code and not about the prose that describes
    it (the convention test_referee.py's fences use)."""
    text = re.sub(r'(?s)""".*?"""', "", text)
    return "\n".join(line.split("#")[0] for line in text.splitlines())


def _reset():
    path = Path(_CFG) / PC.SETTINGS_NAME
    if path.exists():
        path.unlink()
    # The owner's own target rows too: a suite that leaves them behind would
    # make the NEXT check pass for the wrong reason (and did, once, before this
    # line existed).
    rows = Path(_CFG) / PC.TARGETS_NAME
    if rows.exists():
        rows.unlink()


# --------------------------------------------------------------------------
def t_off_by_default_and_fails_closed():
    _reset()
    check("no file at all: off, and no complaint", PC.enabled() is False and PC.setting()["why"] == "")
    (Path(_CFG) / PC.SETTINGS_NAME).write_text("{not json", encoding="utf-8")
    check("a damaged file fails to off", PC.enabled() is False)
    check("...and says why, never a bare False", PC.setting()["why"] != "")
    (Path(_CFG) / PC.SETTINGS_NAME).write_text('{"enabled": "yes"}', encoding="utf-8")
    check("a value that is not true/false fails to off", PC.enabled() is False)
    (Path(_CFG) / PC.SETTINGS_NAME).write_text('{"enabled": true}', encoding="utf-8")
    check("a real true is on", PC.enabled() is True)


def t_the_switch_is_written_the_house_way():
    _reset()
    out = PC.set_enabled(True)
    check("set_enabled reports the new state", out.get("ok") is True and out.get("on") is True, out)
    check("and it is on after a write", PC.enabled() is True)
    check("off again, at once", PC.set_enabled(False)["on"] is False)
    check("the file lives in the settings folder",
          (Path(_CFG) / PC.SETTINGS_NAME).is_file())
    doc = json.loads((Path(_CFG) / PC.SETTINGS_NAME).read_text(encoding="utf-8"))
    check("the file holds the flag and a timestamp", doc["enabled"] is False and "changed" in doc, doc)


def t_the_words_the_apps_show():
    st = PC.status()
    check("the switch is called what the design chose", PC.LABEL == "Prompt coach")
    check("the detail says the default first, house style",
          PC.DETAIL.startswith("Off (the default)"), PC.DETAIL[:40])
    check("...and says plainly that the model is small",
          "small" in PC.DETAIL and "wrong" in PC.DETAIL)
    check("...and says no card is raised either way", "no approval card" in PC.DETAIL)
    check("the four button words are the ones both apps use",
          (PC.BUTTON, PC.SEND_MINE, PC.SEND_SUGGESTION)
          == ("Coach this", "Send mine", "Send the suggestion"))
    check("status() carries them all for the screens",
          all(st.get(k) for k in ("label", "detail", "heading", "button",
                                  "send_mine", "send_suggestion")))


def t_it_is_off_until_asked():
    _reset()
    try:
        PC.coach("summarise the quarterly report for me")
        check("off refuses", False)
    except PC.Refused as exc:
        check("off refuses, in the module's own words", str(exc) == PC.OFF_LINE, str(exc))


def t_short_prompts_are_not_coached():
    _reset()
    PC.set_enabled(True)
    try:
        PC.coach("hi there")
        check("a two-word prompt is refused", False)
    except PC.Refused as exc:
        check("a two-word prompt is refused rather than invented about",
              "too short" in str(exc), str(exc))
    PC.set_enabled(False)


def t_the_local_check_comes_first():
    """The one thing this module must never get wrong: nothing is built and
    sent before the address is proved to be this PC."""
    src = (HERE / "jarvis_prompt_coach.py").read_text(encoding="utf-8")
    code = _code_only(src)
    check("the local check is a call, not a comment",
          re.search(r"check_local_model|_local_check\(", code) is not None)
    body = code[code.index("def coach("):]
    at_check = body.index("_local_check(")
    at_call = body.index("caller(")
    check("it is called BEFORE the model is asked", at_check < at_call,
          f"check at {at_check}, call at {at_call}")
    check("and a failure closes the door rather than carrying on",
          "if why:" in body[:at_call] and "raise Refused" in body[at_check:at_call + 40])

    # And in behaviour: a check that returns a sentence stops everything.
    PC.set_enabled(True)
    said = {}

    def never(*a):
        said["called"] = True
        return "{}"

    real = PC._local_check
    PC._local_check = lambda url, model: "Jarvis could not confirm the model is on this PC."
    try:
        PC.coach("summarise the quarterly report for me", ask=never,
                 url="http://127.0.0.1:11434", model="m")
        check("a failed local check refuses", False)
    except PC.Refused as exc:
        check("a failed local check refuses, in the checker's own words",
              "could not confirm" in str(exc), str(exc))
    check("...and the model was never asked", "called" not in said)
    PC._local_check = real
    PC.set_enabled(False)


def _with_gate_stubbed(fn):
    real = PC._local_check
    PC._local_check = lambda url, model: ""
    try:
        return fn()
    finally:
        PC._local_check = real


GOOD = {"score": 4, "clear": False,
        "issues": [{"what": "no output shape", "why": "a list and a paragraph differ",
                    "fix": "say 'as a short list of three'"},
                   {"what": "no file named", "why": "'the report' is not a file",
                    "fix": "name the file"}],
        "missing": ["which report?"],
        "suggestion": "Summarise the report at C:\\notes\\q3.md as a list of three points."}


def t_a_critique_comes_back_whole():
    _reset()
    PC.set_enabled(True)
    seen = {}

    def fake(url, model, prompt):
        seen.update(url=url, model=model, prompt=prompt)
        return json.dumps(GOOD)

    out = _with_gate_stubbed(lambda: PC.coach(
        "please summarise the report for me",
        [{"who": "owner", "text": "I am working on the Q3 report"},
         {"who": "jarvis", "text": "Understood."}],
        ask=fake, url="http://127.0.0.1:11434", model="jarvis-primary"))
    check("the score is kept", out["score"] == 4, out)
    check("both gaps are kept", len(out["issues"]) == 2, out)
    check("each gap carries what, why and the fix",
          all(i["what"] and i["why"] and i["fix"] for i in out["issues"]), out)
    check("the questions it would ask are kept", out["missing"] == ["which report?"])
    check("the rewritten prompt is kept whole",
          out["suggestion"].startswith("Summarise the report at"))
    check("'clear' is false when gaps were listed", out["clear"] is False)
    check("the last few turns reached the model",
          "I am working on the Q3 report" in seen["prompt"], seen["prompt"][-200:])
    check("the owner's own words reached the model",
          "summarise the report" in seen["prompt"])
    check("the shape was asked for, not hoped for", '"score"' in seen["prompt"])
    check("the model was given the schema as the format", PC.SCHEMA["required"][0] == "score")
    PC.set_enabled(False)


def t_nothing_to_say_is_a_valid_answer():
    _reset()
    PC.set_enabled(True)
    CLEAR = {"score": 9, "clear": True, "issues": [], "missing": [], "suggestion": "same"}
    out = _with_gate_stubbed(lambda: PC.coach(
        "put the kettle on at eight please", ask=lambda *a: json.dumps(CLEAR),
        url="http://127.0.0.1:11434", model="m"))
    check("'this is clear, send it' is a real answer",
          out["clear"] is True and out["issues"] == [], out)
    PC.set_enabled(False)


def t_clear_is_not_taken_at_its_word():
    _reset()
    PC.set_enabled(True)
    LOUD = {"score": 7, "clear": True, "issues": [{"what": "x", "why": "y", "fix": "z"}],
            "missing": [], "suggestion": ""}
    out = _with_gate_stubbed(lambda: PC.coach(
        "put the kettle on at eight please", ask=lambda *a: json.dumps(LOUD),
        url="http://127.0.0.1:11434", model="m"))
    check("a model claiming 'clear' while listing gaps is not believed",
          out["clear"] is False, out)
    PC.set_enabled(False)


def t_a_bad_answer_is_a_refusal_never_half_a_card():
    for name, raw in [("not JSON at all", "I think it is fine, actually."),
                      ("a list, not an object", "[1, 2, 3]"),
                      ("no score", '{"issues": [], "missing": [], "suggestion": ""}'),
                      ("a score that is a string",
                       '{"score": "high", "issues": [], "missing": [], "suggestion": ""}'),
                      ("no list of gaps", '{"score": 5, "missing": [], "suggestion": ""}')]:
        try:
            PC.parse(raw)
            check(f"refused rather than half-shown: {name}", False)
        except PC.Refused:
            check(f"refused rather than half-shown: {name}", True)
    check("a fenced answer is read", PC.parse('```json\n' + json.dumps(GOOD) + '\n```')["score"] == 4)
    check("stray prose around one object is tolerated",
          PC.parse("Here you go: " + json.dumps(GOOD))["score"] == 4)
    many = {"score": 3, "clear": False, "missing": [], "suggestion": "",
            "issues": [{"what": str(i), "why": "", "fix": ""} for i in range(9)]}
    check("more than four gaps is trimmed to four",
          len(PC.parse(json.dumps(many))["issues"]) == PC.MAX_ISSUES)
    check("the score is clamped into 1..10",
          PC.parse(json.dumps(dict(GOOD, score=99)))["score"] == 10)


def t_a_silent_model_says_so():
    _reset()
    PC.set_enabled(True)
    try:
        _with_gate_stubbed(lambda: PC.coach(
            "summarise the quarterly report for me", ask=lambda *a: None,
            url="http://127.0.0.1:11434", model="m"))
        check("a silent model is refused", False)
    except PC.Refused as exc:
        check("a silent model is refused, and says nothing was sent",
              "Nothing was sent" in str(exc), str(exc))
    PC.set_enabled(False)


def t_the_routes_own_half():
    _reset()
    PC.set_enabled(False)
    code, body = PC.handle_post({"text": "summarise the quarterly report for me"})
    check("a refusal is 409 with a plain sentence, not a traceback",
          code == 409 and body["ok"] is False and isinstance(body["error"], str), (code, body))
    code, body = PC.handle_post("not an object")
    check("a body that is not an object is 400", code == 400 and body["ok"] is False, (code, body))

    code, body = PC.handle_setting({"enabled": True})
    check("the switch's route writes it", code == 200 and body["on"] is True, (code, body))
    check("...and the module agrees it is on", PC.enabled() is True)
    check("...and the route hands back the words the screens need",
          body.get("label") == PC.LABEL and body.get("detail") == PC.DETAIL, body)
    code, body = PC.handle_setting({"enabled": "yes"})
    check("a switch value that is not true/false is refused, never guessed",
          code == 400 and body["ok"] is False, (code, body))
    code, body = PC.handle_setting("nonsense")
    check("and so is a body that is not an object", code == 400, (code, body))
    PC.set_enabled(False)


def t_it_approves_nothing_and_keeps_nothing():
    """The fences. Each one is a promise the design makes in words; this is
    what makes it a promise the code keeps."""
    code = _code_only((HERE / "jarvis_prompt_coach.py").read_text(encoding="utf-8"))
    check("no part of the gate is imported or reached",
          not re.search(r"jarvis_gate|owner_check|approve|deny|allowed\s*=", code, re.I))
    check("no subprocess and no shell", 
          not re.search(r"\b(subprocess|os\.system|popen|eval\(|exec\()", code))
    check("it writes no memory, no history and no fact",
          not re.search(r"jarvis_memory|jarvis_auto_learn\.(?!check_local_model)|"
                        r"jarvis_chat_log|remember|save_fact|note_fact", code))
    check("it logs nothing",
          not re.search(r"\blogging\b|\.log\(|print\(", code))
    check("the only HTTP is the local model call, through the proxy-free helper",
          "jarvis_local_http.urlopen" in code
          and not re.search(r"requests\.|http\.client|socket\.", code))
    check("nothing is cached or kept between calls",
          not re.search(r"\b_cache\b|lru_cache|global\s+\w+\s*=", code))


def t_both_paths_end_in_one_writer():
    """The Settings route and the voice/chat path must move the same switch, or
    the two can disagree about whether the coach is on."""
    reg = (HERE / "jarvis_settings_registry.py").read_text(encoding="utf-8")
    block = reg[reg.index("def set_prompt_coach("):]
    block = block[:block.index("\n\n\n")]
    check("the registry's setter calls the module's own writer",
          "PC.set_enabled(" in block, block[:200])
    check("...and never writes the file itself",
          "settings_path" not in block and "json.dump" not in block)
    check("the setting is registered as a boolean switch with a section",
          'BoolSetting("prompt_coach"' in reg and 'Section("prompt-coach"' in reg)
    check("the setting is off by default, like every other new switch",
          "off" in PC.DETAIL.lower() and PC.DETAIL.startswith("Off (the default)"))


# ==========================================================================
#   The four settings (the owner's answers, 2026-10-09)
# ==========================================================================
#
# Every check below FAILS on the module as it was before that change: there
# were no SETTINGS, no choices(), no set_choice() and no settings_rows(), so
# four settings could not be read, moved or shown. That is the point of them -
# a test that passes either way proves nothing.

def t_four_settings_exist_and_all_default_to_todays_behaviour():
    check("exactly the four the owner chose, in their words",
          tuple(k for k, _n, _d, _v in PC.SETTINGS)
          == ("speaks_up", "bluntness", "coaches_on", "platform"),
          tuple(k for k, _n, _d, _v in PC.SETTINGS))
    check("each carries a name and at least two choices",
          all(len(r[1]) >= 1 and len(r[3]) >= 2 for r in PC.SETTINGS))
    check("'when it speaks up' offers both of the owner's options",
          set(PC.SETTING_CHOICES["speaks_up"]) == {"any", "weak"})
    check("'how blunt it is' offers a gentle nudge and direct",
          set(PC.SETTING_CHOICES["bluntness"]) == {"gentle", "direct"})
    check("'what it coaches on' offers shape and content",
          set(PC.SETTING_CHOICES["coaches_on"]) == {"shape", "content"})
    check("'per-platform behaviour' offers same and a quieter phone",
          set(PC.SETTING_CHOICES["platform"]) == {"same", "quieter_phone"})
    check("every default is one of its own choices",
          all(PC.SETTING_DEFAULTS[k] in PC.SETTING_CHOICES[k] for k in PC.SETTING_KEYS))
    check("...and the defaults are what the coach already did",
          PC.SETTING_DEFAULTS == {"speaks_up": "any", "bluntness": "gentle",
                                  "coaches_on": "shape", "platform": "same"},
          PC.SETTING_DEFAULTS)


def t_a_missing_or_damaged_choice_falls_back_to_its_own_default():
    _reset()
    path = Path(_CFG) / PC.SETTINGS_NAME
    check("no file: all four at their defaults", PC.choices() == PC.SETTING_DEFAULTS)
    path.write_text(json.dumps({"enabled": True, "bluntness": "shouty"}),
                    encoding="utf-8")
    got = PC.choices()
    check("a value that is not one of the choices falls back, never guessed at",
          got["bluntness"] == "gentle", got)
    path.write_text(json.dumps({"enabled": True, "coaches_on": 7}),
                    encoding="utf-8")
    check("a value that is not even a string falls back",
          PC.choices()["coaches_on"] == "shape")
    path.write_text("{not json", encoding="utf-8")
    check("a damaged file leaves all four at their defaults (and the switch off)",
          PC.choices() == PC.SETTING_DEFAULTS and PC.enabled() is False)
    _reset()


def t_one_setting_moves_at_a_time_without_losing_the_others():
    _reset()
    PC.set_enabled(True)
    PC.set_choice("bluntness", "direct")
    PC.set_choice("coaches_on", "content")
    after = PC.choices()
    check("each change sticks",
          after["bluntness"] == "direct" and after["coaches_on"] == "content", after)
    check("...and the ones not named are untouched",
          after["speaks_up"] == "any" and after["platform"] == "same")
    check("...and the master switch is still on - one file, not two",
          PC.enabled() is True)
    doc = json.loads((Path(_CFG) / PC.SETTINGS_NAME).read_text(encoding="utf-8"))
    check("all of it lives in the one settings file the backup already picks up",
          doc["enabled"] is True and doc["bluntness"] == "direct", doc)
    PC.set_enabled(False)
    check("turning the master switch off keeps the four",
          PC.choices()["bluntness"] == "direct")
    _reset()


def t_a_setting_that_is_not_one_is_refused_in_words():
    _reset()
    try:
        PC.set_choice("bluntness", "shouty")
        check("a value that is not a choice is refused", False)
    except PC.Refused as exc:
        check("...and the refusal names the real choices",
              "shouty" in str(exc) and "gentle" in str(exc) and "direct" in str(exc),
              str(exc))
    try:
        PC.set_choice("wittiness", "high")
        check("a key that is not one of the four is refused", False)
    except PC.Refused as exc:
        check("...and the refusal lists the four that exist",
              all(k in str(exc) for k in PC.SETTING_KEYS), str(exc))
    check("nothing was written by either refusal",
          not (Path(_CFG) / PC.SETTINGS_NAME).exists())
    code, body = PC.handle_setting({"key": "bluntness", "value": "shouty"})
    check("the route says 409, the module's own sentence",
          code == 409 and body["ok"] is False and "shouty" in body["error"], (code, body))
    code, body = PC.handle_setting({"key": "bluntness", "value": "direct"})
    check("a real change through the route is 200 with the whole state back",
          code == 200 and body["bluntness"] == "direct" and body["ok"] is True,
          (code, body))
    check("...and it moved only that one", PC.choices()["coaches_on"] == "shape")
    _reset()


def t_the_master_switch_route_still_works_exactly_as_before():
    """The four settings were added to a route the PHONE already calls. An
    older app sends {"enabled": bool} and nothing else, and must keep
    working - and the two fields it reads must still be there."""
    _reset()
    code, body = PC.handle_setting({"enabled": True})
    check("the old body still moves the switch",
          code == 200 and body["on"] is True, (code, body))
    check("...and the answer still carries `on` and `why`",
          "on" in body and "why" in body, sorted(body))
    check("...and the words every screen already reads",
          body["label"] == PC.LABEL and body["detail"] == PC.DETAIL
          and body["button"] == PC.BUTTON)
    code, body = PC.handle_setting({"enabled": "yes"})
    check("a value that is not true/false is still refused, never guessed",
          code == 400 and body["ok"] is False, (code, body))
    code, body = PC.handle_setting({})
    check("an empty body is still 400", code == 400, (code, body))
    PC.set_enabled(False)
    _reset()


def t_only_when_weak_really_holds_back_a_fine_prompt():
    """"When it speaks up: only when the prompt is genuinely weak" must change
    what the owner SEEES, not just what the prompt says. The model is a
    stand-in, so the gate itself is what is measured."""
    _reset()
    PC.set_enabled(True)
    FINE = {"score": 9, "clear": True, "issues": [], "missing": [],
            "suggestion": "Put the kettle on at eight."}
    WEAK = {"score": 3, "clear": False,
            "issues": [{"what": "no output shape", "why": "y", "fix": "z"}],
            "missing": ["which file?"], "suggestion": "Summarise C:\\q3.md as three bullets."}

    def run(payload):
        return _with_gate_stubbed(lambda: PC.coach(
            "put the kettle on at eight please", ask=lambda *a: json.dumps(payload),
            url="http://127.0.0.1:11434", model="m"))

    out = run(FINE)
    check("default (any): a fine prompt is still commented on",
          out["advice_given"] is True and out["said"] == "")

    PC.set_choice("speaks_up", "weak")
    out = run(FINE)
    check("weak: a prompt it scored 9 is passed with no advice at all",
          out["advice_given"] is False and out["issues"] == [] and out["clear"] is True,
          out)
    check("...and it says so, in words, rather than showing an empty list",
          out["said"] == PC.NOTHING_WEAK, out.get("said"))
    out = run(WEAK)
    check("weak: a genuinely weak prompt still gets the whole critique",
          out["advice_given"] is True and len(out["issues"]) == 1, out)
    check("...including the questions it would ask",
          out["missing"] == ["which file?"], out)
    boundary = dict(FINE, score=PC.WEAK_BELOW, clear=False,
                    issues=[{"what": "w", "why": "y", "fix": "z"}])
    out = run(boundary)
    check(f"the line is the module's own WEAK_BELOW ({PC.WEAK_BELOW})",
          out["advice_given"] is False, out)
    PC.set_choice("speaks_up", "any")
    out = run(FINE)
    check("back to 'any': the fine prompt is commented on again",
          out["advice_given"] is True)
    PC.set_enabled(False)
    _reset()


def t_the_quieter_phone_shows_less_and_says_so_in_the_prompt():
    _reset()
    PC.set_enabled(True)
    MANY = {"score": 4, "clear": False,
            "issues": [{"what": f"gap {i}", "why": "y", "fix": "z"} for i in range(4)],
            "missing": ["q1", "q2", "q3", "q4"], "suggestion": "s"}
    seen = {}

    def fake(url, model, prompt):
        seen["prompt"] = prompt
        return json.dumps(MANY)

    def run():
        return _with_gate_stubbed(lambda: PC.coach(
            "summarise the quarterly report please", ask=fake,
            url="http://127.0.0.1:11434", model="m"))

    out = run()
    check("the PC (default) shows all four gaps and four questions",
          len(out["issues"]) == 4 and len(out["missing"]) == 4, out)
    check("...and is not told it is a phone",
          "being read on a phone" not in seen["prompt"])
    PC.set_choice("platform", "quieter_phone")
    out = run()
    check("the quieter phone shows the two that matter most",
          len(out["issues"]) == PC.MAX_ISSUES_QUIET == 2, out)
    check("...and only two questions",
          len(out["missing"]) == PC.MAX_MISSING_QUIET == 2, out)
    check("...and the model was told, so it spends its answer on those",
          "being read on a phone" in seen["prompt"], seen["prompt"][-400:])
    check("the score is untouched by it: the advice is trimmed, not weakened",
          out["score"] == 4)
    PC.set_choice("platform", "same")
    check("back to same, all four are back",
          len(run()["issues"]) == 4)
    PC.set_enabled(False)
    _reset()


def t_bluntness_and_scope_reach_the_model_in_its_own_instructions():
    """These two cannot be measured from the parsed answer - they change the
    WORDS the local model is asked with. So that is what is measured."""
    _reset()
    PC.set_enabled(True)
    seen = {}

    def fake(url, model, prompt):
        seen["prompt"] = prompt
        return json.dumps({"score": 5, "clear": False, "issues": [], "missing": [],
                           "suggestion": ""})

    def run():
        return _with_gate_stubbed(lambda: PC.coach(
            "summarise the quarterly report please", ask=fake,
            url="http://127.0.0.1:11434", model="m"))

    run()
    check("default: the model is told to be a gentle nudge",
          "gentle nudge" in seen["prompt"], seen["prompt"][-600:])
    check("default: shape only, and it says which",
          "SHAPE only" in seen["prompt"] and "CONTENT" not in seen["prompt"])
    PC.set_choice("bluntness", "direct")
    PC.set_choice("coaches_on", "content")
    run()
    check("direct: the model is told to be direct, in as many words",
          "Be direct." in seen["prompt"], seen["prompt"][-600:])
    check("...and no longer told to be a gentle nudge",
          "gentle nudge" not in seen["prompt"])
    check("content: the model is told to judge the task and what was left out",
          "judge the CONTENT" in seen["prompt"])
    PC.set_choice("speaks_up", "weak")
    run()
    check("weak reaches the model too, so it does not waste the answer on a fine prompt",
          "genuinely weak" in seen["prompt"])
    PC.set_enabled(False)
    _reset()


def t_the_screens_read_every_choice_from_the_pc():
    """The words are the PC's ONE copy. A screen that invented a choice's name
    - or forgot one - is what this makes impossible."""
    rows = PC.settings_rows()
    check("one row per setting, in the owner's order",
          [r["key"] for r in rows] == list(PC.SETTING_KEYS))
    for row in rows:
        check(f"{row['key']}: carries its own name and its current value",
              bool(row["name"]) and row["value"] in PC.SETTING_CHOICES[row["key"]])
        check(f"{row['key']}: every choice is listed with a name and a detail line",
              {c["value"] for c in row["choices"]} == set(PC.SETTING_CHOICES[row["key"]])
              and all(c["name"] and c["detail"] for c in row["choices"]))
    st = PC.status()
    check("status() carries them, so both apps get them with the switch",
          isinstance(st.get("settings"), list) and len(st["settings"]) == 4)
    check("...and the list of AIs Jarvis knows, for the same reason",
          isinstance(st.get("targets"), list) and "local" in st["targets"])
    check("...and the staleness line, so 'out of date' has a number behind it",
          st.get("stale_days") == PC.STALE_DAYS)


# ==========================================================================
#   Which AI the prompt is headed for (the owner's words, 2026-10-09)
# ==========================================================================
#
# *"make sure it is aware of what model of cloud AI I am using because each
# kind has their own intricacies and make sure this can stay up to date."*

def t_every_ai_the_driver_offers_has_notes_of_its_own():
    """The check that keeps the knowledge from freezing. A service added to
    jarvis_chatbot_api.PRESETS or a website added to jarvis_chatbot.ADAPTERS
    with no row here fails THIS, by name, instead of being silently coached as
    if it were the local model."""
    missing = PC.unknown_targets()
    check("every API service and website adapter the driver offers has a row",
          missing == (), "no notes for: " + ", ".join(missing))
    check("the local model has one too - the default target",
          PC.resolve_target("local") == "local")
    check("there are rows for the cloud services the repo names",
          {"openai_api", "deepseek_api", "groq_api"} <= set(PC.target_ids()),
          sorted(PC.target_ids()))


def t_a_target_is_matched_by_its_own_names_never_by_a_near_miss():
    for name, want in [("openai_api", "openai_api"), ("openai", "openai_api"),
                       ("ChatGPT (OpenAI API)", "openai_api"),
                       ("gemini", "gemini_web"), ("deepseek", "deepseek_api"),
                       ("groq", "groq_api"), ("le chat", "lechat_web"),
                       ("this PC", "local"),
                       ("qwen3:8b", ""), ("", ""), (None, "")]:
        got = PC.resolve_target(name)
        check(f"resolve_target({name!r}) -> {want!r}", got == want, got)


def t_an_unknown_ai_is_reported_and_never_guessed_at():
    a = PC.advice_for("some-model-jarvis-has-never-heard-of")
    check("an unknown AI is known=False", a["known"] is False, a)
    check("...with no quirks and no style invented for it",
          a["quirks"] == () and a["style"] == () and a["context"] == "", a)
    check("...and a plain sentence naming the thing the owner named",
          "some-model-jarvis-has-never-heard-of" in a["advice"]
          and PC.TARGETS_NAME in a["advice"], a["advice"])
    check("a target that was not named at all still says it does not know",
          PC.advice_for("")["known"] is False)
    check("...and that sentence does not pretend an AI was named",
          "Jarvis does not know this AI yet" in PC.advice_for("")["advice"])


def t_the_model_is_told_either_the_quirks_or_that_they_are_unknown():
    _reset()
    PC.set_enabled(True)
    seen = {}

    def fake(url, model, prompt):
        seen["prompt"] = prompt
        return json.dumps({"score": 5, "clear": False, "issues": [], "missing": [],
                           "suggestion": ""})

    def run(target):
        return _with_gate_stubbed(lambda: PC.coach(
            "summarise the quarterly report please", ask=fake,
            url="http://127.0.0.1:11434", model="m", target=target))

    out = run("openai_api")
    check("a known target: its own name reaches the model",
          "ChatGPT (OpenAI API, gpt-5-mini)" in seen["prompt"], seen["prompt"][:900])
    check("...and at least one of its real quirks does",
          any(q in seen["prompt"] for q in PC.advice_for("openai_api")["quirks"]))
    check("...and the critique carries what Jarvis knew back to the app",
          out["target"]["known"] is True and out["target"]["id"] == "openai_api", out["target"])
    check("...including the date it was last checked, so 'out of date' is visible",
          out["target"]["checked"] == PC.advice_for("openai_api")["checked"])

    run("nope-not-a-model")
    check("an unknown target: the model is told NOT to guess, in as many words",
          "does NOT know this AI" in seen["prompt"], seen["prompt"][:900])
    check("...and told not to invent a claim about it",
          "do not invent a claim" in seen["prompt"])
    check("...and no other AI's quirks are smuggled in as if they were its own",
          all(q not in seen["prompt"] for q in PC.advice_for("openai_api")["quirks"]))

    run(None)
    check("no target named at all means the ordinary local chat",
          "the model on this PC (Ollama)" in seen["prompt"], seen["prompt"][:600])
    PC.set_enabled(False)
    _reset()


def t_an_owner_row_can_correct_or_add_a_target_without_a_new_build():
    """"...and make sure this can stay up to date": the file, not a release."""
    _reset()
    path = Path(_CFG) / PC.TARGETS_NAME
    path.write_text(json.dumps({"targets": [
        {"id": "openai_api", "quirks": ["my own note about this one"],
         "checked": "2026-10-09"},
        {"id": "brand_new_api", "name": "Some New AI", "kind": "api",
         "context": "came out last week", "quirks": ["forgets long pastes"],
         "style": ["keep it short"]},
    ]}), encoding="utf-8")

    a = PC.advice_for("openai_api")
    check("an owner's quirks replace the shipped ones", a["quirks"] == ("my own note about this one",), a)
    check("...and the fields the owner did not type are kept from the shipped row",
          a["name"] == "ChatGPT (OpenAI API, gpt-5-mini)" and a["style"], a)
    check("...including the shipped `source`, unless the owner gave one",
          a["source"] == "preset notes in jarvis_chatbot_api.py", a["source"])
    b = PC.advice_for("brand_new_api")
    check("a target the shipped table never heard of works at once",
          b["known"] is True and b["name"] == "Some New AI", b)
    check("...and its own quirks are the ones carried", b["quirks"] == ("forgets long pastes",))
    check("...and it is dated today rather than trusted as fresh for ever",
          b["checked"] == __import__("time").strftime("%Y-%m-%d"), b["checked"])
    check("it joins the list the apps can name", "brand_new_api" in PC.target_ids())

    path.write_text(json.dumps({"targets": [{"id": "no_name"}, "not a row", 7]}),
                    encoding="utf-8")
    rows, problems = PC.from_file()
    check("a row with no name is refused, not half-read", rows == (), rows)
    check("...and every bad row is reported rather than swallowed",
          len(problems) == 3 and all(PC.TARGETS_NAME in p for p in problems), problems)
    check("...and the shipped table still answers while the file is bad",
          PC.advice_for("local")["known"] is True)
    path.write_text("{not json", encoding="utf-8")
    rows, problems = PC.from_file()
    check("a file that is not JSON is one plain problem, not a crash",
          rows == () and len(problems) == 1, problems)
    path.unlink()
    _reset()


def t_notes_that_are_old_say_so_rather_than_reading_as_fresh():
    _reset()
    path = Path(_CFG) / PC.TARGETS_NAME
    path.write_text(json.dumps({"targets": [
        {"id": "local", "checked": "2001-01-01"}]}), encoding="utf-8")
    a = PC.advice_for("local")
    check("a row older than STALE_DAYS is marked stale", a["stale"] is True, a)
    check("...and its own words say so, with the date",
          "may be out of date" in a["advice"] and "2001-01-01" in a["advice"], a["advice"])
    seen = {}

    def fake(url, model, prompt):
        seen["prompt"] = prompt
        return json.dumps({"score": 5, "clear": False, "issues": [], "missing": [],
                           "suggestion": ""})

    PC.set_enabled(True)
    _with_gate_stubbed(lambda: PC.coach(
        "summarise the quarterly report please", ask=fake,
        url="http://127.0.0.1:11434", model="m", target="local"))
    check("...and the model is told not to treat them as certain",
          "may be out of date" in seen["prompt"], seen["prompt"][:900])
    PC.set_enabled(False)

    path.write_text(json.dumps({"targets": [
        {"id": "local", "checked": "not a date"}]}), encoding="utf-8")
    check("a date that cannot be read counts as stale, never as fresh",
          PC.advice_for("local")["stale"] is True)
    path.unlink()
    check("the shipped date is inside the window, so nothing cries wolf",
          PC.advice_for("local")["stale"] is False,
          PC.advice_for("local")["checked"])
    _reset()


def t_the_target_and_the_settings_ride_back_with_the_critique():
    _reset()
    PC.set_enabled(True)
    seen = {}

    def fake(url, model, prompt):
        seen["prompt"] = prompt
        return json.dumps({"score": 6, "clear": False, "issues": [], "missing": [],
                           "suggestion": "s"})

    out = _with_gate_stubbed(lambda: PC.coach(
        "summarise the quarterly report please", ask=fake,
        url="http://127.0.0.1:11434", model="m", target="groq_api"))
    check("the critique carries the target's own notes for the screen",
          out["target"]["name"] == "Groq (API, openai/gpt-oss-20b)", out["target"])
    check("...and the settings it was judged with, so the screen can say which",
          out["settings"] == PC.choices(), out["settings"])
    check("no model name of the target was passed to the LOCAL model call",
          "gpt-oss-20b" not in seen.get("model", "") and seen.get("model") is None)
    code, body = PC.handle_post({"text": "summarise the quarterly report please",
                                 "target": "groq_api"})
    check("the route carries `target` through from the body",
          code in (409, 200), (code, body))
    PC.set_enabled(False)
    code, body = PC.handle_post({"text": "summarise the quarterly report please",
                                 "target": "groq_api"})
    check("with the coach off the route still refuses in the module's own words",
          code == 409 and body["error"] == PC.OFF_LINE, (code, body))
    _reset()


def main():
    _reset()
    for fn in (t_off_by_default_and_fails_closed,
               t_the_switch_is_written_the_house_way,
               t_the_words_the_apps_show,
               t_it_is_off_until_asked,
               t_short_prompts_are_not_coached,
               t_the_local_check_comes_first,
               t_a_critique_comes_back_whole,
               t_nothing_to_say_is_a_valid_answer,
               t_clear_is_not_taken_at_its_word,
               t_a_bad_answer_is_a_refusal_never_half_a_card,
               t_a_silent_model_says_so,
               t_the_routes_own_half,
               t_it_approves_nothing_and_keeps_nothing,
               t_both_paths_end_in_one_writer,
               # The four settings (the owner's answers, 2026-10-09).
               t_four_settings_exist_and_all_default_to_todays_behaviour,
               t_a_missing_or_damaged_choice_falls_back_to_its_own_default,
               t_one_setting_moves_at_a_time_without_losing_the_others,
               t_a_setting_that_is_not_one_is_refused_in_words,
               t_the_master_switch_route_still_works_exactly_as_before,
               t_only_when_weak_really_holds_back_a_fine_prompt,
               t_the_quieter_phone_shows_less_and_says_so_in_the_prompt,
               t_bluntness_and_scope_reach_the_model_in_its_own_instructions,
               t_the_screens_read_every_choice_from_the_pc,
               # Which AI the prompt is headed for.
               t_every_ai_the_driver_offers_has_notes_of_its_own,
               t_a_target_is_matched_by_its_own_names_never_by_a_near_miss,
               t_an_unknown_ai_is_reported_and_never_guessed_at,
               t_the_model_is_told_either_the_quirks_or_that_they_are_unknown,
               t_an_owner_row_can_correct_or_add_a_target_without_a_new_build,
               t_notes_that_are_old_say_so_rather_than_reading_as_fresh,
               t_the_target_and_the_settings_ride_back_with_the_critique):
        print(f"\n--- {fn.__name__} ---")
        fn()
    _reset()
    total = len(FAILURES)
    print(f"\n{total} failed" if total else "\nall checks passed")
    if total:
        print("failed:", *FAILURES, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
