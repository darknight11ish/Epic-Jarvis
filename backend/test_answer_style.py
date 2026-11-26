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

# The same isolation test_agent.py uses, and for the same reason: a manner line,
# a cloud key or a setup-quiz line from the owner's own config would change the
# request bytes this suite pins. Set BEFORE any product module is imported.
_CFG = tempfile.TemporaryDirectory(prefix="answer-style-agent-cfg-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _CFG.name

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


def t_the_route_both_apps_read():
    """GET/POST /api/answer-style, installed by the drop-in folder."""
    _with_temp_config()
    AS.set_style("auto")
    state = AS.state()
    check("the route answers the three choices with the module's own labels",
          [c["label"] for c in state["choices"]]
          == [AS.LABEL[s] for s in AS.STYLES], repr(state.get("choices")))
    check("... each with its own reason, in the module's words",
          [c["why"] for c in state["choices"]]
          == [AS.WHY[s] for s in AS.STYLES])
    check("... and the one in force", state["style"] == "auto", repr(state["style"]))
    code, out = AS.handle_get(AS.STATE_PATH)
    check("GET answers 200", code == 200 and out.get("style") == "auto", repr(code))
    code, out = AS.handle_post(AS.STATE_PATH, {"style": "bullets"})
    check("POST one change answers 200 with the new state",
          code == 200 and out.get("style") == "bullets", repr((code, out.get("style"))))
    check("... and says what changed in the PC's own sentence",
          "bullet" in str(out.get("said") or "").lower(), repr(out.get("said")))
    code, out = AS.handle_post(AS.STATE_PATH, {"style": "rainbow"})
    check("POST refuses a value nobody offered, in words",
          code == 400 and "bullet" in str(out.get("message") or "").lower(),
          repr((code, out.get("message"))))
    check("... and wrote nothing", AS.current() == "bullets", repr(AS.current()))
    code, out = AS.handle_post(AS.STATE_PATH, {"colour": "red"})
    check("POST refuses a field the setting does not have", code == 400, repr(code))
    code, _out = AS.handle_get("/api/manner")
    check("every other route falls through to the core", code == 404, repr(code))


def _turn(messages, **kw):
    """One real run_local_turn through a fake stream; the messages it sent."""
    import jarvis_agent as AG
    import _ollama_wire as W
    sent = []

    def opener(url, body):
        sent.append(body)
        return W.FakeResponse(W.stream([("content", "ok"), ("done", "stop")]))

    AG.run_local_turn(list(messages), "jarvis-primary",
                      ollama_url="http://127.0.0.1:11434",
                      stream_out=lambda b: None, open_stream=opener,
                      enabled_tools=set(), context_length=16384,
                      on_step=lambda s: None, record_chain=lambda s: None,
                      keepalive_seconds=60, status_delay=60, lane_choice=None, **kw)
    return sent[0]["messages"]


def t_the_note_reaches_a_typed_turn():
    """THE WHOLE POINT: the note is in the request - after the rules, before the
    newest question - and only where it belongs."""
    import jarvis_agent as AG
    _with_temp_config()
    AS.set_style("auto")
    # The same cosmetic notes test_agent.py stubs for its request pins:
    # neither is this suite's subject, and both would make the bytes below
    # depend on this PC. (The model/preset line is stubbed there too.)
    import jarvis_model_knowledge as _model_knowledge
    saved_prompt = _model_knowledge.prompt_line
    _model_knowledge.prompt_line = lambda: ""
    saved_manner, saved_setup = AG._manner_now, AG.setup_state_note
    AG._manner_now = lambda *a, **k: None
    AG.setup_state_note = lambda: None
    try:
        rules = {"role": "system", "content": AG.LANE_SYSTEM}
        note = AS.note_message()
        first = [{"role": "user", "content": "hello"}]
        got = _turn(first)
        check("a first question stays byte-identical to before this note "
              "(the request pin in test_agent.py)",
              got == [rules] + first, [str(m.get("content"))[:30] for m in got])

        history = [{"role": "user", "content": "q1"},
                   {"role": "assistant", "content": "a1"},
                   {"role": "user", "content": "q2"}]
        got = _turn(history)
        check("a typed follow-up carries the declared note",
              note in got, [str(m.get("content"))[:30] for m in got])
        check("... after the Jarvis rules", got[0] == rules,
              [str(m.get("content"))[:20] for m in got[:2]])
        check("... and before the newest user message", got[-1] == history[-1])
        check("... with nothing else between it and the question",
              len(got) >= 2 and got[-2] == note,
              [str(m.get("content"))[:24] for m in got])
        check("the caller's own messages were not changed (the relay never "
              "sees the note)", history[-1] == {"role": "user", "content": "q2"}
              and len(history) == 3, repr(history))

        spoken = history[:-1] + [{"role": "user", "content": "q2",
                                  "provenance": "voice"}]
        got = _turn(spoken)
        check("a SPOKEN turn never carries the typed-layout note",
              note not in got, [m["role"] for m in got])
        check("... because the spoken note forbids lists, and says so",
              any(AG.SPOKEN_NOTE == m.get("content") for m in got),
              [str(m.get("content"))[:30] for m in got])

        AS.set_style("prose")
        got = _turn(history)
        check("prose adds nothing at all - the follow-up is what it was",
              note not in got and got[-1] == history[-1],
              [str(m.get("content"))[:24] for m in got])
    finally:
        AG._manner_now, AG.setup_state_note = saved_manner, saved_setup
        _model_knowledge.prompt_line = saved_prompt
        AS.set_style("auto")


def t_chat_sentences_set_the_style():
    """Each phrasing the owner may type, and both directions of the pin: a
    GitHub sentence must not be swallowed, and a layout sentence must not be."""
    import jarvis_quick as Q
    _with_temp_config()
    AS.set_style("auto")
    cases = {"use bullet points": "bullets",
             "always use bullet points": "bullets",
             "no bullet points": "prose",
             "plain paragraphs": "prose",
             "bullet points when it helps": "auto",
             "from now on, use bullet points": "bullets"}
    wrong = {}
    for phrase, want in cases.items():
        intent = Q.match(phrase)
        if intent is None or intent.name != "answer_style_set":
            wrong[phrase] = None if intent is None else intent.name
            continue
        ran = Q.run(intent, None, 0.0)
        if AS.current() != want or ran.intent != "answer_style_set" or not ran.reply:
            wrong[phrase] = (AS.current(), ran.intent, ran.reply[:60])
    check("every layout sentence sets the style and says what changed",
          not wrong, repr(wrong))
    others = ["how do I use bullet points in GitHub markdown?",
              "show me the bullet points in that file",
              "does GitHub support bullet points",
              "what are bullet points"]
    swallowed = {p: Q.match(p).name for p in others if Q.match(p) is not None}
    check("a GitHub or question sentence is NOT swallowed as a layout command",
          not swallowed, repr(swallowed))
    AS.set_style("auto")


def t_the_settings_row_and_the_desktop_control():
    """One registry row beside the manner/personality pair, its three labels
    from the module, and a real desktop control in the Settings page."""
    import jarvis_settings_registry as R
    _with_temp_config()
    AS.set_style("auto")
    row = next((r for r in R.CHOICE_SETTINGS if r.key == "answer_style"), None)
    check("the registry has ONE answer_style row", row is not None)
    if row is not None:
        labels = [AS.LABEL[s] for s in AS.STYLES]
        options = row.options()
        check("... in the manner card, beside the personality row",
              row.where == "manner"
              and any(r.key == "personality" for r in R.CHOICE_SETTINGS),
              repr(row.where))
        check("... whose three choices are the module's own three styles",
              set(options.values()) == set(AS.STYLES), repr(sorted(options)))
        check("... each reachable by the module's own label",
              all(R._choice_key(label) in options for label in labels),
              repr(sorted(options)))
        check("... and it reads the module's current value in its own words",
              row.now() == R._choice_key(AS.LABEL["auto"]), repr(row.now()))
        out = R.set_answer_style("bullets")
        check("... and setting it through the registry changes the same file",
              out.ok and AS.current() == "bullets", f"{out.ok} {AS.current()!r}")
        AS.set_style("auto")
    html = (HERE.parent / "jarvis-desktop" / "src" / "settings.html").read_text(
        encoding="utf-8")
    check("the desktop Settings page has the control beside How Jarvis talks",
          'id="as-list"' in html and 'id="as-choices"' in html
          and 'id="as-status"' in html, "the #as-* ids are missing")
    check("... loaded by its own module, next to manner-settings.js",
          'src="answer-style-settings.js"' in html
          and html.index("manner-settings.js") < html.index("answer-style-settings.js"))
    check("... and the row is inside the How Jarvis talks card",
          html.index('id="manner"') < html.index('id="as-list"'),
          "the control is outside #manner")
    js = (HERE.parent / "jarvis-desktop" / "src" / "answer-style-settings.js").read_text(
        encoding="utf-8")
    check("the control reads and writes the PC's one route, not a local copy",
          'invoke("get_answer_style")' in js and 'invoke("set_answer_style"' in js
          and "localStorage.setItem" not in js
          and "localStorage.getItem" not in js,
          "the desktop module is not wired")
    plugin = (HERE.parent / "plugins" / "ready" / "answer-style" / "plugin.json")
    check("the route ships as a drop-in folder naming this module (no patch)",
          plugin.is_file() and '"jarvis_answer_style"' in plugin.read_text(encoding="utf-8"),
          str(plugin))



def main():
    for fn in (t_the_three_styles_and_the_default,
               t_a_missing_or_damaged_file_is_the_default,
               t_aliases_an_owner_would_type,
               t_saving_and_reading_back,
               t_the_note_itself,
               t_what_the_owner_is_told,
               t_setting_it_from_chat,
               t_the_route_both_apps_read,
               t_the_note_reaches_a_typed_turn,
               t_chat_sentences_set_the_style,
               t_the_settings_row_and_the_desktop_control,
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
