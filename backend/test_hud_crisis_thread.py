"""The HUD's own chat box keeps a crisis turn out of what it re-sends.

    python3 test_hud_crisis_thread.py

THE OWNER'S RULE (docs/DECISIONS.md, 2026-09-29): **a crisis question and its
answer do not stay in the scrollable thread** - the help shows once, and the
chat is still kept in History as "A difficult moment". The quickbar has read the
route's `wellbeing: "crisis"` flag since then (`chat-history.js` `crisisRoute`
+ `keepsInThread`, used by `main.js`), and the phone does too.

The HUD page did not read the flag at all: it pushed every finished answer into
`S.messages`, the array `windowForPrompt` builds the next request from - so the
question after a crisis one carried the owner's crisis words and the 988/911
help back to the model, and the page's own comment claimed it followed "same
rules as the quickbar (chat-history.js)".

THIS IS A SOURCE PIN, NOT A BROWSER RUN, and it says so: the page is a single
vendored HTML file with no module to import, so what is checked is the text the
browser would run - the flag read, the guarded commit, the repair of the lone
user turn, and that the bar's rule is still the thing being matched. The runtime
suites for this page are `jarvis-desktop/tests/hud*.mjs` (Playwright); they were
NOT extended here.
"""
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
COPIES = (HERE / "jarvis_hud.html",
          REPO / "jarvis-backend" / "jarvis_hud.html",
          REPO / "jarvis-desktop" / "src" / "jarvis_hud.html")
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def main() -> int:
    print("--- the three copies are one file ---")
    digests = {}
    for p in COPIES:
        check(f"present: {p.relative_to(REPO)}", p.is_file(), str(p))
        digests[p] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""
    check("all three byte-identical (backend/, jarvis-backend/, jarvis-desktop/src/)",
          len(set(digests.values())) == 1, digests)

    src = COPIES[0].read_text(encoding="utf-8")
    print("\n--- it reads the flag the quickbar and the phone read ---")
    check("the page reads route.wellbeing === \"crisis\"",
          'route.wellbeing === "crisis"' in src)
    check("into a variable the commit path can see (declared before the try)",
          re.search(r"let crisisTurn = false;\s*\n\s*try\{", src) is not None)
    check("the flag is read from the ROUTE, not guessed from the answer's words",
          "crisisTurn = route.wellbeing" in src)

    print("\n--- the crisis pair is not committed to what gets re-sent ---")
    check("the assistant push is behind the guard, not beside it",
          re.search(r"if\(crisisTurn\)\{.*?\} else \{\s*\n\s*S\.messages\.push"
                    r"\(\{role:\"assistant\", content:full\}\);", src, re.S) is not None)
    pushes = src.count('S.messages.push({role:"assistant"')
    check("there is exactly ONE assistant push, and it is the guarded one",
          pushes == 1, pushes)
    check("the question is taken back out too, so no lone user turn is re-sent",
          "S.messages.pop();" in src and "last.content === text" in src)

    print("\n--- the answer still shows once, and History still keeps it ---")
    check("the answer is still rendered (the guard only stops the re-send)",
          'node.textContent = full' in src and 'addMessage("jarvis", full)' in src)
    check("the page still sends its conversation id, so the PC still records the chat",
          "conversation_id: S.conversationId" in src)

    print("\n--- the rule being matched is still the bar's own rule ---")
    hist = (REPO / "jarvis-desktop" / "src" / "chat-history.js").read_text(encoding="utf-8")
    check("the quickbar still exports crisisRoute and keepsInThread",
          "export function crisisRoute" in hist and "export function keepsInThread" in hist)
    check("and keepsInThread still refuses a crisis turn",
          re.search(r"export function keepsInThread\(crisis\) \{\s*\n\s*return crisis !== true;",
                    hist) is not None)


    print("\n--- the speech gate: the typed send path is SILENT (Wave 9, owner 2026-11-06/07) ---")
    # Wave 9 removed automatic speech from the typed box: a typed answer is never
    # read aloud, and speech now belongs to a VOICE turn (the quickbar) or to the
    # per-answer Read out loud tap. So the old question - "did the send path ask
    # the rule before speaking?" - has a stronger answer: the send path speaks
    # nothing at all, and cannot speak by mistake.
    check("the typed send path no longer speaks",
          "voice.speak(aloud ? full :" not in src)
    check("the answer still renders before anything else can happen",
          'node.textContent = full' in src and 'addMessage("jarvis", full)' in src)
    check("the answer is still shown once, and History still keeps it",
          "conversation_id: S.conversationId" in src)
    check("the page still imports the bar's own rule for its PER-ANSWER speaker",
          'import("./private-speech.js")' in src and ".mayReadAloud(" in src)
    check("... and asks it with the answer's own route, and says what it cannot know",
          "route: route || {}" in src and "toolsKnown: true" in src)
    check("... and the route is cleared at the start of every turn",
          "turnRoute = null;" in src,
          "a per-turn value must be per-turn")
    check("the remaining voice.speak calls are the per-answer taps (icon and menu)",
          src.count("voice.speak(ANSWER_SAID") == 1
          and src.count("voice.speak(said.text)") == 1,
          (src.count("voice.speak(ANSWER_SAID"), src.count("voice.speak(said.text)")))

    print("\n--- the rule reused is still the bar's rule, and rule 1 is untouched ---")
    rule_src = (REPO / "jarvis-desktop" / "src" / "private-speech.js").read_text(encoding="utf-8")
    check("private-speech.js still exports mayReadAloud and PRIVATE_LINE",
          "export function mayReadAloud" in rule_src and "export const PRIVATE_LINE" in rule_src)
    boot = (REPO / "jarvis-desktop" / "src-tauri" / "src" / "hud_bootstrap.js").read_text(encoding="utf-8")
    check("hud_bootstrap.js 2e STILL keeps speech to local voices (rule 1)",
          "localService === true" in boot and "synth.speak = function (utterance)" in boot
          and "getVoices = localVoices" in boot)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
