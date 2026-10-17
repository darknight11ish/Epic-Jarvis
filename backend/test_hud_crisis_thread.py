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


    print("\n--- the speech gate: shown, not said (owner, 2026-10-16) ---")
    check("the page imports the bar's own RULE rather than copying it",
          'import("./private-speech.js")' in src and ".mayReadAloud(" in src)
    check("and passes it THIS turn's route",
          "turnRoute = route;" in src and "route: turnRoute || {}" in src)
    # THE ROUTE IS PER-TURN, so it must be cleared per-turn. It is module-level
    # so the reply handler can see it, and nothing cleared it: once one turn
    # carried a sensitive route, every later turn looked private too and the page
    # said the on-screen line instead of speaking ORDINARY answers, for ever.
    # hud.mjs caught it as 10 failed "reads the real reply" checks.
    check("and the route is cleared at the start of every turn",
          "turnRoute = null;" in src,
          "a per-turn value must be per-turn")
    check("what the page cannot know is not silently claimed known",
          "toolsKnown: true" in src and "cannot know that" in src,
          "the limit must be written down beside the call")
    # THE LINE IS SPOKEN, NOT POSTED. `private-speech.js:41` is the authority -
    # "Jarvis says one fixed line instead, PRIVATE_LINE, once" - and the bar does
    # it with `speechQueue.push(PRIVATE_LINE)` (main.js:4642, :4728). #504 first
    # did `addMessage("system", ...)` instead, and a system line is how this page
    # draws an ERROR, so every private answer looked like a failure: hud.mjs
    # reported "an error was shown for a good reply" on 10 checks.
    check("speech happens only inside the rule's yes",
          re.search(r"voice\.speak\(aloud \? full :", src) is not None)
    check("and a refused answer SAYS the rule's own line instead of the answer",
          "(rule && rule.PRIVATE_LINE) ||" in src
          and 'addMessage("system", (rule' not in src,
          "spoken, not added as a message - a system line reads as an error here")
    speak_at = src.index("voice.speak(aloud ? full :")
    render_at = min(src.index("node.textContent = full"), src.index('addMessage("jarvis", full)'))
    check("the answer RENDERS before the speak decision is even reached",
          render_at < speak_at, (render_at, speak_at))

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
