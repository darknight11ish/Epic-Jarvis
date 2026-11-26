#!/usr/bin/env python3
"""test_answer_style.py - the typed-answer layout dial (jarvis_answer_style.py).

What this suite has to prove, and why each row exists:

* the three styles exist, the default is `auto`, and a damaged or missing file
  is `auto` rather than a crash - a setting that can take the chat lane down is
  worse than no setting;
* `prose` adds **no note at all**, so turning the dial off restores exactly the
  bytes the model got before this module existed (that is what makes it
  reversible);
* `auto` and `bullets` DO add a note, it asks for bullets, and it forbids the
  things that would be worse than a wall of text (headings, tables, HTML,
  nested bullets);
* the setting is one file, read and written through the same path, and a value
  nobody offered is a refusal - never a silent default;
* `jarvis_agent.with_style_note` places the note like `with_spoken_note` does
  (never first, before the newest user message) and is only reached on a TYPED
  turn, because the spoken note forbids lists outright.

Run: py -3 -B backend/test_answer_style.py   (with JARVIS_BACKEND cleared)
"""

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

PASSED, FAILED = [], []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print(f"ok   {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}  {detail}")


def _with_temp_config():
    """Point the module at a temp config folder for one case."""
    folder = tempfile.mkdtemp(prefix="answer-style-")
    os.environ["JARVIS_CONFIG_DIR"] = folder
    return Path(folder)


def t_the_three_styles_and_the_default():
    check("three styles are offered", AS.STYLES == ("auto", "bullets", "prose"),
          repr(AS.STYLES))
    check("auto is the default", AS.DEFAULT == "auto", repr(AS.DEFAULT))
    check("every style has a label the page can draw",
          set(AS.LABEL) == set(AS.STYLES), repr(sorted(AS.LABEL)))
    check("every style has a reason in words",
          set(AS.WHY) == set(AS.STYLES), repr(sorted(AS.WHY)))


def t_a_missing_or_damaged_file_is_the_default():
    folder = _with_temp_config()
    check("no file at all reads as auto", AS.current() == "auto",
          repr(AS.current()))
    (folder / AS.FILE_NAME).write_text("{not json", encoding="utf-8")
    check("a damaged file reads as auto", AS.current() == "auto",
          repr(AS.current()))
    (folder / AS.FILE_NAME).write_text('[1, 2]', encoding="utf-8")
    check("a file of the wrong shape reads as auto", AS.current() == "auto",
          repr(AS.current()))


def t_aliases_an_owner_would_type():
    cases = {
        "bullets": "bullets", "bullet points": "bullets", "Bullet Points": "bullets",
        "lists": "bullets", "always": "bullets",
        "prose": "prose", "paragraphs": "prose", "no bullets": "prose",
        "plain": "prose", "plain text": "prose",
        "auto": "auto", "when it helps": "auto", "default": "auto",
    }
    wrong = {k: AS.normalize_style(k) for k, want in cases.items()
             if AS.normalize_style(k) != want}
    check("the words an owner would type all map to a style", not wrong, repr(wrong))
    check("a made-up value is not a style", AS.normalize_style("rainbow") == "",
          repr(AS.normalize_style("rainbow")))


def t_saving_and_reading_back():
    folder = _with_temp_config()
    saved = AS.set_style("bullets")
    check("saving returns the style it saved", saved == "bullets", repr(saved))
    check("the file is where the module says it is",
          (folder / AS.FILE_NAME).is_file(), str(AS.path()))
    check("reading it back gives the same style", AS.current() == "bullets",
          repr(AS.current()))
    AS.set_style("prose")
    check("a second change replaces the first", AS.current() == "prose",
          repr(AS.current()))
    try:
        AS.set_style("rainbow")
        refused = False
    except ValueError:
        refused = True
    check("a style nobody offered is refused, not quietly accepted", refused)
    check("the refusal left the saved style alone", AS.current() == "prose",
          repr(AS.current()))


def t_the_note_itself():
    _with_temp_config()
    AS.set_style("auto")
    auto = AS.note_message()
    check("auto adds a note", isinstance(auto, dict), repr(auto))
    text = str(auto.get("content") or "") if isinstance(auto, dict) else ""
    check("the auto note says when to use bullets",
          "bullet" in text.lower() and "three or more" in text.lower(), text[:80])
    check("the note names itself as a READ answer, not a spoken one",
          "read" in text.lower() and "spoken" not in text.lower()[:40], text[:80])
    for banned in ("heading", "table", "HTML", "nested"):
        check(f"the note forbids {banned}", banned.lower() in text.lower())
    check("the note is not enormous", len(text) < 900, f"{len(text)} characters")

    AS.set_style("bullets")
    strong = AS.note_message()
    check("bullets adds a note too", isinstance(strong, dict), repr(strong))
    check("the bullets note is about any answer with more than one part",
          "more than one part" in str(strong.get("content") or "").lower(),
          str(strong.get("content") or "")[:80])

    AS.set_style("prose")
    check("prose adds NOTHING at all", AS.note_message() is None,
          repr(AS.note_message()))

    AS.set_style("auto")
    check("an explicit style argument wins over the file",
          "bullet" in str((AS.note_message("bullets") or {}).get("content") or "").lower()
          and AS.note_message("prose") is None)


def t_what_the_owner_is_told():
    for style in AS.STYLES:
        said = AS.said(style)
        check(f"{style} has a one-line sentence to say",
              isinstance(said, str) and 10 < len(said) < 200, repr(said))
    check("the plain-paragraphs sentence says there are no bullets",
          "no bullets" in AS.said("prose").lower() or
          "paragraph" in AS.said("prose").lower(), AS.said("prose"))


def t_setting_it_from_chat():
    _with_temp_config()
    ok, style, said = AS.handle_set({"style": "bullets"})
    check("a chat payload sets the style", ok and style == "bullets",
          f"ok={ok} style={style!r}")
    check("... and the owner is told what changed", "bullet" in said.lower(), said)
    ok, style, said = AS.handle_set("no bullets")
    check("a bare value works too", ok and style == "prose", f"{ok} {style!r}")
    ok, style, said = AS.handle_set({"style": "rainbow"})
    check("an unknown value is a refusal with the three options named",
          not ok and "bullet" in said.lower() and "paragraph" in said.lower(), said)
    check("... and the refused change wrote nothing", AS.current() == "prose",
          repr(AS.current()))


def main():
    for fn in (t_the_three_styles_and_the_default,
               t_a_missing_or_damaged_file_is_the_default,
               t_aliases_an_owner_would_type,
               t_saving_and_reading_back,
               t_the_note_itself,
               t_what_the_owner_is_told,
               t_setting_it_from_chat,
               ):
        fn()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


try:
    import jarvis_answer_style as AS
except Exception as exc:  # noqa: BLE001
    print(f"FAIL the module could not be imported: {type(exc).__name__}: {exc}")
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
