"""test_hud_empty_service.py - the HUD refuses a lane its module cannot place.

    python3 backend/test_hud_empty_service.py

THE RULING (2026-11-18, quoted): "`lane_service()` returning `("", "")` (never
a cloud URL) is right - AND the HUD manual-lane path must explicitly check for
`("", "")` and refuse with a clear error naming the invalid lane rather than
letting an empty service pass downstream."

`jarvis_chatbot_api.lane_service()` fails closed (2026-11-18): only a name in
`CLOUD_LANES` names a service, and every other name answers `("", "")`.
`lane_state()` hands that back as an empty `pid`/`model`. `jarvis_hud.py`'s
`_completions_url(lane, body)` - the one place a chosen lane name becomes a
service and an address - read "no address" as "the local lane", so an unknown
lane name fell through to THIS PC's Ollama with the name still on the request.
Ollama has no such model, and the owner got a 503 from an endpoint they did not
choose. The helper now REFUSES a cloud-intent lane whose service is empty, by
name, before any URL is built: a 404 whose body is the plain sentence both apps
show, `There is no lane called "<name>" on this PC, so nothing was sent.` It is
deliberately NOT one of `_open`'s `DEGRADABLE` codes, so the degrade loop
cannot turn the refusal into a silent local answer, and `_open`'s existing
`except urllib.error.HTTPError` reader is what puts the sentence on screen.

WHY ITS OWN SUITE. `test_ollama_direct.py` is the patch's own suite, but
`backend/run_suites.py` skips it BY NAME when the owner's `jarvis_hud.py` is
absent (CI), so a check written only there would never run in the required
`backend` job. This suite reads the same text through `test_ollama_direct`'s
helpers (`_completions_block` reads the patch stack's own file when the live
one is absent) and runs everywhere. On the owner's older file it SKIPS, in the
same words the rest of the project uses, rather than claiming a pass.

WHAT IT PROVES, and each half can fail on its own:

  1. THE REFUSAL, driven through the REAL approved helper text: an unknown
     cloud-intent lane raises instead of returning a URL; the exception is a
     404; its body names the lane the client asked for and says nothing was
     sent; the request body is not rewritten for a service; and the module was
     asked about that lane first.
  2. THE CONTROL: the same unknown name with a local-intent fallback turn
     (`decision.inject_memory` True) still goes to this PC's Ollama and keeps
     its name on the request - the shape the helper returned for EVERY lane
     before the guard, which is what makes the refusal a change.
  3. NO URL AT ALL: the refusal happens while the argument `_open` hands
     `urllib.request.Request` is being worked out, so no URL reaches a request
     builder - "nothing was sent" is observed, not assumed.
  4. THE PATCH: `backend/ollama-direct.patch` reverses out of the file the
     stack walk builds just after it, and re-applies to that pre-image with the
     bytes identical. That is the direction `apply-patches.ps1` travels, and it
     is what catches a wrong hunk count in the added refusal.

No socket, no model, no live config and no owner's file needed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import types
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402,F401  (also puts BACKEND/rebuilt on sys.path)
import _stack  # noqa: E402
import test_ollama_direct as OD  # noqa: E402  (the patch's own fixtures)

PASSED, FAILED, SKIPPED = [], [], []

#: The refusal's two fixed pieces. The lane name between them is the name the
#: client asked for, and the checks say it is the name that gets named.
REFUSAL_STARTS = "There is no lane called"
REFUSAL_ENDS = "nothing was sent."

LANE = "jarvis-a-lane-this-pc-does-not-have"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass (the BLOCKED-is-never-a-pass rule)."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def _guard_block():
    """(the REAL `_completions_url`, where it came from) - or (None, why).

    The same source `test_ollama_direct._completions_block()` reads: the
    owner's own file when this run has one, otherwise the patch stack's text.
    An older HUD (the owner's live copy before the next deploy) has no
    refusal, so this run SKIPS rather than failing over text it does not
    have."""
    block, where = OD._completions_block()
    if block is None:
        return None, where
    if REFUSAL_STARTS not in block:
        return None, (f"the `_completions_url` in {where} is older than the "
                      "empty-service refusal")
    return block, where


def _call(block, api, lane, inject_memory=False):
    """(the HTTPError or None, the url or None, the body) from the REAL helper.

    `api` is `test_ollama_direct.FakeApi`, and `known=False` is
    `lane_service()` failing closed: no service, no model, the module's own
    sentence - exactly what the real module answers for an unknown name."""
    ns = {"OLLAMA_URL": "http://127.0.0.1:11434", "local_model": OD.LOCAL,
          "urllib": urllib, "active_ollama_url": lambda: "http://127.0.0.1:11434",
          "decision": types.SimpleNamespace(inject_memory=inject_memory),
          "body": {"model": lane}}
    source = compile(block, "<cloud _completions_url>", "exec")
    OD._with_api(api, lambda: exec(source, ns))
    try:
        url = OD._with_api(api, lambda: ns["_completions_url"](lane, ns["body"]))
    except urllib.error.HTTPError as exc:
        return exc, None, ns["body"]
    return None, url, ns["body"]


# --------------------------------------------------------------------------
#   1. The refusal
# --------------------------------------------------------------------------

def t_an_unknown_manual_lane_is_refused_by_name():
    """THE RULING. An unknown lane name - a client's `{"lane": ..., "auto":
    false}` that somehow reached the relay, or an old config's lane from a
    degrade step - names no service, so the turn is refused before any URL is
    built, with a 404 that names the lane and says nothing was sent.

    What this fails on before the change: the real helper returned the LOCAL
    Ollama URL (`http://127.0.0.1:11434/v1/chat/completions`) for this same
    input with the lane name still on the body - the 503 shape. There was no
    exception at all, so every check here is a change rather than a
    description."""
    block, where = _guard_block()
    if block is None:
        return skip(where)
    api = OD.FakeApi(known=False)
    exc, url, body = _call(block, api, LANE)
    if exc is None:
        return check("an unknown cloud-intent lane is refused, not given a URL",
                     False, f"the helper returned {url!r}")
    check("an unknown cloud-intent lane is refused, not given a URL", True)
    check("... as a 404 - a client error, and NOT a degrade-loop code",
          exc.code == 404 and exc.code not in {429, 500, 502, 503, 504}, exc.code)
    said = exc.read().decode("utf-8", "replace")
    check("... naming the lane the client asked for", f'"{LANE}"' in said, said)
    check("... and saying plainly that nothing was sent",
          REFUSAL_ENDS in said, said)
    check("... with a next step the owner can take", "ask again" in said, said)
    check("... and the request body is not rewritten for a service",
          body.get("model") == LANE, body)
    check("... because the module was asked about that lane first",
          api.calls == [LANE], api.calls)


# --------------------------------------------------------------------------
#   2. The control
# --------------------------------------------------------------------------

def t_the_lanes_that_are_fine_are_unchanged():
    """THE OTHER HALF OF THE CONTROL - the two lanes the guard must not touch.

    The EMPTY NAME is the local signal: `lane_state("")` is asked for with the
    empty name, answers no service, and the helper still returns Ollama's own
    endpoint (this is the branch the refusal must not confuse with "unknown
    lane"). A REAL cloud lane name resolves to the service behind it and
    proceeds - its address, its own model on the request - exactly as it did
    before the guard. Both ran unchanged before this work; both must still."""
    block, where = _guard_block()
    if block is None:
        return skip(where)
    # The local lane, asked for by its own model name; the helper turns it
    # into the empty lane name for the module.
    api = OD.FakeApi()
    exc, url, body = _call(block, api, OD.LOCAL)
    check("the local lane is unaffected: no refusal", exc is None, exc)
    check("... it still resolves to Ollama's own endpoint",
          url == "http://127.0.0.1:11434/v1/chat/completions", url)
    check("... asked for as the module's empty lane name", api.calls == [""], api.calls)
    check("... and the request keeps the local model's own name",
          body.get("model") == OD.LOCAL, body)
    # A real cloud lane still resolves and proceeds.
    api = OD.FakeApi()
    exc, url, body = _call(block, api, OD.LANE)
    check("a real cloud lane is unaffected: no refusal", exc is None, exc)
    check("... it still goes to the service behind it, not to Ollama",
          url == OD.DEEPSEEK_URL, url)
    check("... and the request asks for the SERVICE's model",
          body.get("model") == "deepseek-flash", body)
    check("... because the module was asked about the lane's own name",
          api.calls == [OD.LANE], api.calls)


def t_the_local_fallback_lane_is_still_answered_here():
    """THE CONTROL - the shape this refusal replaces, and the reason it is
    narrow. A router fallback lane (a LOCAL model's name, `inject_memory` True)
    names no cloud service either - `lane_service()` cannot know a local
    model's name - and that turn must still be answered by this PC's Ollama.
    The same unknown name therefore still reaches the local endpoint when the
    turn is not cloud-intent: the two checks differ only by that flag.

    Read as the "what failed before" half: this is exactly what the helper
    returned for EVERY lane, cloud picks included, before the guard."""
    block, where = _guard_block()
    if block is None:
        return skip(where)
    api = OD.FakeApi(known=False)
    exc, url, body = _call(block, api, LANE, inject_memory=True)
    check("a local-intent fallback lane is not refused", exc is None, exc)
    check("... it is still answered on this PC's own Ollama",
          url == "http://127.0.0.1:11434/v1/chat/completions", url)
    check("... and keeps its own name on the request, which Ollama serves",
          body.get("model") == LANE, body)


# --------------------------------------------------------------------------
#   3. No request is built
# --------------------------------------------------------------------------

def t_no_url_reaches_the_request_builder():
    """The helper's return value IS the address `_open` hands `Request`, so a
    refusal inside the helper is a turn that never reaches `urlopen`. This
    drives the REAL helper through a request builder that records every URL it
    is given: the refusal happens while the argument is still being worked
    out, so nothing is recorded."""
    block, where = _guard_block()
    if block is None:
        return skip(where)
    api = OD.FakeApi(known=False)
    built = []

    def build_request(url, **kwargs):
        built.append(url)
        return url

    ns = {"OLLAMA_URL": "http://127.0.0.1:11434", "local_model": OD.LOCAL,
          "urllib": urllib, "active_ollama_url": lambda: "http://127.0.0.1:11434",
          "decision": types.SimpleNamespace(inject_memory=False),
          "body": {"model": LANE}}
    source = compile(block, "<cloud _completions_url>", "exec")
    OD._with_api(api, lambda: exec(source, ns))
    try:
        build_request(OD._with_api(api, lambda: ns["_completions_url"](LANE, ns["body"])))
    except urllib.error.HTTPError:
        pass
    check("no URL reaches the request builder for an unknown cloud-intent lane",
          built == [], built)


# --------------------------------------------------------------------------
#   4. The patch itself
# --------------------------------------------------------------------------

def t_the_patch_applies_and_reverses_byte_for_byte():
    """`backend/ollama-direct.patch` itself, not the HUD's text: the stack walk
    builds the file the whole stack leaves just AFTER this patch (the pre-image
    its hunks name is invented from the patch's own context lines), the patch
    is reversed out of it in a throwaway git repo, and put back. The bytes must
    come back identical, which is the direction `apply-patches.ps1` really
    travels. This is what catches a wrong hunk count in the added refusal (the
    same failure `test_patch_wellformed.py` catches by parsing every patch)."""
    names = _stack.order()
    check("ollama-direct.patch is in apply-patches.ps1's stack",
          "ollama-direct.patch" in names)
    if "ollama-direct.patch" not in names:
        return
    index = names.index("ollama-direct.patch")
    after, log = _stack.stand_in("jarvis_hud.py", patches=names[: index + 1])
    if not after:
        return skip("the patch stack could not build jarvis_hud.py: "
                    + "; ".join(log[-2:]))
    if REFUSAL_STARTS not in after:
        return skip("the patch stack's jarvis_hud.py does not hold the refusal")
    patch = HERE / "ollama-direct.patch"
    work = Path(tempfile.mkdtemp(prefix="jarvis-hud-empty-service-"))
    target = work / "jarvis_hud.py"
    target.write_text(after, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env.pop("JARVIS_BACKEND", None)

    def git(*args):
        return subprocess.run(["git", *args], cwd=work, capture_output=True,
                              text=True, env=env, timeout=120)

    try:
        if git("init", "-q").returncode != 0:
            return skip("git is not available to run the patch round trip")
        git("add", "jarvis_hud.py")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "pre")
        reversed_it = git("apply", "-R", str(patch))
        check("the patch reverses out of the file the stack leaves",
              reversed_it.returncode == 0, reversed_it.stderr[-300:])
        if reversed_it.returncode != 0:
            return
        pre = target.read_text(encoding="utf-8")
        check("... the pre-image really has no `_completions_url` helper",
              "def _completions_url(lane: str, body: dict) -> str:" not in pre)
        applied = git("apply", str(patch))
        check("the patch applies to that pre-image again",
              applied.returncode == 0, applied.stderr[-300:])
        if applied.returncode != 0:
            return
        again = target.read_text(encoding="utf-8")
        check("... and the bytes are identical to the stack's after-image",
              again == after)
    finally:
        try:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    for fn in (t_an_unknown_manual_lane_is_refused_by_name,
               t_the_lanes_that_are_fine_are_unchanged,
               t_the_local_fallback_lane_is_still_answered_here,
               t_no_url_reaches_the_request_builder,
               t_the_patch_applies_and_reverses_byte_for_byte):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
