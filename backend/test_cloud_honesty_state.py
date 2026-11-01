"""test_cloud_honesty_state.py - the owner-reported cloud/API denial, fixed.

    python -B backend/test_cloud_honesty_state.py

WHAT THIS PROVES, with the real modules and a temporary config folder:

1. THE SYSTEM LINE. Every local prompt carries ONE redacted line describing the
   real cloud state: the chosen Cloud provider, whether its key is saved (a
   bool, never a value), whether it can be used and the standing switch. It
   appears in the prompt a model would receive (`dress_messages`), after the
   rules and before the question, and contains no key or fragment.
2. THE QUICK ANSWERS. Ten sentence shapes ("are you connected to my deepseek
   api?", "do you have my deepseek key?", "is the cloud on/off?", ...) are
   answered deterministically from that state, in every state the owner can be
   in: key saved/not, preset chosen/not, ready/not, switch on/off. No model is
   called, no key is echoed, and an unrelated "what is the cloud?" is not
   over-captured.
3. THE PRIVACY WORDS. The one rule is quoted in the answers: email, files,
   credentials and stored memory stay on the local model; a cloud turn is
   explicit opt-in; the key is in Windows Credential Manager and never logged
   or echoed.

The key store, the gate and the money file are stood in for: this suite must
never read the owner's real credentials. The provider/preset state is the real
`jarvis_presets` module with its own functions monkeypatched, so the code path
under test is the real one.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(Path(tempfile.mkdtemp(prefix="jarvis-cloud-state-")))
os.environ["JARVIS_CONFIG_DIR"] = os.environ["OPENJARVIS_CONFIG_DIR"]
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

import jarvis_chatbot_api as API  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_agent as AG  # noqa: E402

KEY = "sk-cloud-honesty-test-SECRET-0123456789"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def state(*, provider="deepseek_api", key=True, ready="", escalate=False,
          deepseek=True):
    """Put the modules in one real state, with no real credential store."""
    API.key_saved = lambda pid: (key if pid == provider else
                                 (deepseek if pid == "deepseek_api" else False))
    API.ready_for = lambda pid: ready
    API.model_for = lambda pid: (API.PRESETS[pid].model, "")
    P.cloud_chosen = lambda: provider
    P.escalate_on = lambda: bool(escalate)
    P.escalate_why = lambda: "" if escalate else "not turned on"


def reply(sentence):
    got = Q.match(sentence, now=0)
    check(f"shape: {sentence}", got is not None and got.name == "cloud_honesty",
          got.name if got else "the model")
    if got is None or got.name != "cloud_honesty":
        return ""
    return str(Q.answer(sentence, now=0, peer="127.0.0.1", local=True).reply)


def main():
    # ---- 1. the system line, in the prompt a model receives ----------------
    state(provider="deepseek_api", key=True, ready="", escalate=False)
    line = AG.cloud_state_note() or ""
    check("the system line names the chosen service, host and model",
          "DeepSeek" in line and "api.deepseek.com" in line and "deepseek-flash" in line, line)
    check("... says the key is saved without printing it",
          "key is saved" in line and KEY not in line and "sk-" not in line, line)
    check("... says the preset does not send by itself and quotes the privacy rule",
          "nothing" in line.lower() and "email" in line and "files" in line
          and "credentials" in line and "memory" in line, line)
    prompt = AG.dress_messages([{"role": "user", "content": "hello"}], manner=None)
    system = [m.get("content") for m in prompt if isinstance(m, dict) and m.get("role") == "system"]
    check("the prompt the model receives starts with the rules",
          system and system[0] == AG.LANE_SYSTEM, system[:1])
    check("... and carries the cloud-state line before the question",
          any("Cloud preset" in str(s) and "DeepSeek" in str(s) for s in system[1:]),
          system[1:])
    check("... with no key anywhere in the prompt",
          KEY not in str(prompt) and "sk-" not in str(prompt), str(prompt)[:300])

    state(provider="deepseek_api", key=False, ready="no key is saved", escalate=False)
    line = AG.cloud_state_note() or ""
    check("no key: the line says so and claims no connection",
          "no DeepSeek API key is saved" in line and "stay on this PC" in line, line)

    # ---- 2. every sentence shape, with the real state each reads ----------
    state(provider="deepseek_api", key=True, ready="", escalate=False)
    sentences = [
        "are you connected to my deepseek api?",
        "do you have my deepseek key?",
        "are you using the cloud right now?",
        "is this answer from deepseek or the local model?",
        "how do I escalate something to the cloud?",
        "what gets sent when you use the cloud?",
        "what never gets sent?",
        "can you call the deepseek api for this?",
        "is the cloud on/off?",
        "which provider is the cloud preset using?",
    ]
    replies = {s: reply(s) for s in sentences}
    check("connected: yes, names DeepSeek and says the key is saved",
          "Yes." in replies[sentences[0]] and "DeepSeek" in replies[sentences[0]]
          and "key is saved" in replies[sentences[0]], replies[sentences[0]])
    check("key: yes, never shows the key",
          "Yes" in replies[sentences[1]] and KEY not in replies[sentences[1]]
          and "sk-" not in replies[sentences[1]], replies[sentences[1]])
    check("using: says the preset is a choice, not a live answer",
          "written on this PC" in replies[sentences[2]]
          and "does not send by itself" in replies[sentences[2]], replies[sentences[2]])
    check("origin: says this answer is local and a cloud turn needs a door",
          "written on this PC" in replies[sentences[3]]
          and "Try the cloud model" in replies[sentences[3]], replies[sentences[3]])
    check("how: names all three real doors",
          "Try the cloud model" in replies[sentences[4]]
          and "escalate to the cloud" in replies[sentences[4]]
          and "send this to the cloud" in replies[sentences[4]], replies[sentences[4]])
    check("sent: the newest words only, and the never-sent list",
          "newest" in replies[sentences[5]] and "Never sent" in replies[sentences[5]]
          and "email" in replies[sentences[5]], replies[sentences[5]])
    check("never: quotes the privacy rule",
          "Email, files, credentials and stored memory always stay" in replies[sentences[6]],
          replies[sentences[6]])
    check("call: allowed only through an allowed cloud turn",
          "only through a cloud turn" in replies[sentences[7]]
          and "never call its API silently" in replies[sentences[7]], replies[sentences[7]])
    check("on/off: reports the preset and the standing switch",
          "Cloud preset is chosen" in replies[sentences[8]]
          and "standing escalation switch is OFF" in replies[sentences[8]], replies[sentences[8]])
    check("provider: names DeepSeek (API)",
          "DeepSeek" in replies[sentences[9]] and "deepseek" in replies[sentences[9]].lower(),
          replies[sentences[9]])
    check("no answer in any state echoes the key",
          all(KEY not in r and "sk-" not in r for r in replies.values()), replies)

    # ---- 3. the other states ---------------------------------------------
    state(provider="deepseek_api", key=False, ready="", escalate=False)
    r = reply("are you connected to my deepseek api?")
    check("chosen but no key: not yet, and says where the key goes",
          "Not yet, no." in r and "Credential Manager" in r, r)
    state(provider="deepseek_api", key=True, ready="no monthly limit is set", escalate=False)
    r = reply("are you connected to my deepseek api?")
    check("key saved but not usable: partly, with the real reason",
          "Partly, no." in r and "no monthly limit is set" in r, r)
    state(provider="", key=False, ready="", escalate=False, deepseek=True)
    r = reply("are you connected to my deepseek api?")
    check("no provider but DeepSeek key saved: not connected, key present",
          "Not connected, no." in r and "DeepSeek API key is saved" in r, r)
    state(provider="", key=False, ready="", escalate=False, deepseek=False)
    r = reply("do you have my deepseek key?")
    check("no DeepSeek key: says so with no fragment",
          "No." in r and KEY not in r, r)
    state(provider="deepseek_api", key=True, ready="", escalate=True)
    r = reply("are you using the cloud right now?")
    check("standing switch on is reported as on",
          "standing escalation switch is ON" in r, r)

    # ---- 4. no over-capture and no model call -----------------------------
    state(provider="deepseek_api", key=True, ready="", escalate=False)
    got = Q.match("what is the cloud?", now=0)
    check("a generic cloud question is not over-captured",
          got is None or got.name != "cloud_honesty", got.name if got else None)
    got = Q.match("what is the weather?", now=0)
    check("an unrelated question is not captured as cloud honesty",
          got is None or got.name != "cloud_honesty", got.name if got else None)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
