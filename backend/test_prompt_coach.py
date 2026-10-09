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
               t_both_paths_end_in_one_writer):
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
