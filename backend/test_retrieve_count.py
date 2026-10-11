"""test_retrieve_count.py - "3 recalled · 2 near" on the phone, counts only.

    python3 backend/test_retrieve_count.py

The owner's decision of 2026-10-08, choosing from the three options in
docs/RETRIEVE-PORT-BRIEF.md: **"Just the number"**. Not the actual lines, like
the PC (the desktop's trace prints up to 150 characters of the real matched
words - a saved fact, a document, every Logseq page read off disk - which is
why the desktop blanks the whole route while "Windows Hello for memory lists
and chat history" is on), and not nothing on the phone either.

What this proves:

  * `backend/retrieve-count.patch` applies, with `git apply`, to
    `jarvis-backend/jarvis_hud.py` - this repository's copy of the state the
    whole patch stack leaves, i.e. what the owner's PC actually has. That is
    the check `_stack`'s stand-in CANNOT make (it invents a hunk's pre-image
    when it cannot find it), so it is made here, on the real text;
  * the count-only reader really answers with counts, taken from the same
    scoring the desktop's own trace uses - so the two agree;
  * **no word can reach the reply**: the four keys are the whole body, and a
    corpus full of distinctive text leaves not one character of it in the
    JSON. The step that puts matched text in a reply is never called;
  * the desktop is untouched: with no `count` on the request the handler does
    exactly what it did before, and `retrieve()`'s own signature and body are
    not edited at all;
  * the handler's own `count` condition, run as the file writes it, accepts
    exactly `1`/`true`/`yes`/`on` and nothing else - so no other value can
    quietly get a words answer back to the phone;
  * the capability both apps read (`capabilities.retrieve_count`) is the same
    word on both sides of the wire, is asked of the running server
    (`_hud_has("_retrieve_counts")`, exactly like `temporary_chat`), and is
    present in the published base copy as well as the shipped one;
  * the parity entry in `tools/check_parity.py` is REGISTERED and HONEST: not
    `todo` any more, `ported`, and its description says the phone shows
    counts only and never the words;
  * the phone really calls the route, so that classification is not a claim -
    `RetrieveCount.PATH` is the string `check_parity.py` collects.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402
import _stack  # noqa: E402

PATCH = HERE / "retrieve-count.patch"
HUD_BASE = REPO / "jarvis-backend" / "jarvis_hud.py"
PS1 = REPO / "scripts" / "apply-patches.ps1"
PARITY = REPO / "tools" / "check_parity.py"
PHONE = REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis" / "client"

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# A corpus of the kind the real one holds: a saved fact, a Logseq page, a
# document, an entity. None of these words may reach a reply.
WORDS = ("my sister likes jazz", "Isoforge: use q8_0 for the cache",
         "the landlord's number is 555-0100", "Eve Example, dentist")
CORPUS = [{"id": f"fact:{i}", "kind": "fact", "text": w} for i, w in enumerate(WORDS)]
STUB = {"available": True,
        "hits": [{"id": c["id"], "kind": c["kind"], "score": 0.7, "text": c["text"]}
                 for c in CORPUS[:3]],
        "near": [{"id": CORPUS[3]["id"], "kind": "knowledge", "score": 0.4,
                  "text": CORPUS[3]["text"]}]}


def applied_hud():
    """(applied text, why-not) - the patch on the real base, or None."""
    git = shutil.which("git")
    if not git:
        return None, "git is not installed"
    d = Path(tempfile.mkdtemp(prefix="jarvis-retrieve-count-"))
    try:
        (d / "jarvis_hud.py").write_text(HUD_BASE.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run([git, "init", "-q"], cwd=d, check=True, capture_output=True)
        r = subprocess.run([git, "apply", str(PATCH)], cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stderr or r.stdout or "").strip()
        return (d / "jarvis_hud.py").read_text(encoding="utf-8"), ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


def counts_reader(text):
    """`_retrieve_counts` exactly as the patched file defines it, run against a
    stub `retrieve()` - the function's own lines are what is under test."""
    m = re.search(r"^def _retrieve_counts\(.*?(?=^\S)", text, re.S | re.M)
    if not m:
        return None, None
    ns = {"ROUTING": True, "retrieve": lambda q: dict(STUB)}
    exec(compile(m.group(0), "<patched jarvis_hud.py>", "exec"), ns)
    return ns.get("_retrieve_counts"), ns


def t_the_patch_applies_to_the_state_the_stack_leaves():
    check("the patch is a file beside its test", PATCH.is_file())
    text, why = applied_hud()
    check("retrieve-count.patch applies, with git apply, to jarvis-backend/jarvis_hud.py",
          text is not None, why)
    if text is None:
        return
    # What it adds, in the file: the reader and the handler's branch.
    check("the count-only reader is added at module level",
          re.search(r"^def _retrieve_counts\(query: str\) -> dict:$", text, re.M) is not None)
    check("the handler answers it before anything else can",
          'if (params.get("count") or [""])[0].strip().lower() in '
          '("1", "true", "yes", "on"):' in text
          and "return self._send(200, _retrieve_counts(q))" in text)
    # The desktop's own path is untouched: retrieve() is not edited, and with
    # no `count` the handler still calls it exactly as before.
    check("retrieve() itself is not edited (the desktop's trace is unchanged)",
          'def retrieve(query: str, top_k: int = 7, near_k: int = 6) -> dict:' in text
          and 'return self._send(200, retrieve(q))' in text)
    check("the count branch sits ABOVE the empty-question guard, so `count=1` is "
          "answered even when the question is blank",
          text.index("_retrieve_counts(q)") < text.index('if not q.strip():'))
    # Every line of the patch that is ADDED has no way to carry text.
    added = [l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    check("the step that puts matched text in a reply is never called by any added line",
          not any("pack(" in l for l in added), [l for l in added if "pack(" in l])
    check("no added line mentions text, id, kind or a hits list as a key",
          not any(re.search(r'"(text|id|kind|title|hits)"\s*:', l) for l in added),
          [l for l in added if re.search(r'"(text|id|kind|title|hits)"\s*:', l)])


def t_the_reply_is_counts_and_nothing_else():
    text, why = applied_hud()
    if text is None:
        check("the count-only reply can be run (needs the patch to apply)", False, why)
        return
    fn, ns = counts_reader(text)
    check("the patched file defines a runner for the count-only reply", fn is not None)
    if fn is None:
        return
    reply = fn("what did I decide about the cache")
    check("three recalled and one near, from the same scoring the desktop uses",
          reply == {"available": True, "count_only": True, "recalled": 3, "near": 1}, reply)
    blob = json.dumps(reply)
    for word in WORDS:
        for piece in word.replace(":", " ").split():
            if len(piece) < 4:
                continue
            check(f"the reply holds no word of the corpus ({piece!r})", piece not in blob, blob)
    check("the reply is exactly four keys - no list, no row, no snippet",
          set(reply) == {"available", "count_only", "recalled", "near"}, sorted(reply))
    check("the numbers are whole numbers, not strings",
          all(isinstance(reply[k], int) and not isinstance(reply[k], bool)
              for k in ("recalled", "near")), reply)
    check("`count_only` is a real JSON true, not a string", reply["count_only"] is True)

    # Blank question, routing off, and a backend with no scoring at all.
    check("a blank question is nothing recalled, nothing near - and still no words",
          fn("") == {"available": True, "count_only": True, "recalled": 0, "near": 0},
          fn(""))
    ns["ROUTING"] = False
    check("routing off: unavailable, zero, zero",
          fn("  ") == {"available": False, "count_only": True, "recalled": 0, "near": 0}, fn("  "))
    ns["ROUTING"] = True
    ns["retrieve"] = lambda q: {"hits": [], "near": [], "available": False}
    check("a search that could not run says unavailable rather than a made-up zero",
          fn("x")["available"] is False and fn("x")["recalled"] == 0, fn("x"))
    ns["retrieve"] = lambda q: {"hits": [], "near": [], "available": True, "empty": True}
    check("an empty corpus is a true zero",
          fn("x") == {"available": True, "count_only": True, "recalled": 0, "near": 0}, fn("x"))


def t_only_the_phones_own_flag_gets_the_count():
    """The handler's own condition, run as the file writes it - so no other
    value can quietly hand a words answer to the phone."""
    text, why = applied_hud()
    if text is None:
        check("the count flag can be run (needs the patch to apply)", False, why)
        return
    m = re.search(r'^(\s*)if \(params\.get\("count"\) or \[\"\"\]\)\[0\]\.strip\(\)\.lower\(\)'
                  r' in \(([^)]*)\):$', text, re.M)
    check("the handler's own count condition is one line, found in the file", m is not None)
    if m is None:
        return
    values = [v.strip().strip('"') for v in m.group(2).split(",")]
    check("it accepts exactly 1, true, yes and on",
          values == ["1", "true", "yes", "on"], values)
    from urllib.parse import parse_qs, urlparse
    for query, want in (("?q=x&count=1", True), ("?q=x&count=true", True), ("?q=x&count=YES", True),
                        ("?q=x&count=on", True), ("?count=1&q=x", True),
                        ("?q=x", False), ("?q=x&count=0", False), ("?q=x&count=2", False),
                        ("?q=x&count=", False), ("?q=x&count=1%20", True)):
        params = parse_qs(urlparse(query).query)
        got = (params.get("count") or [""])[0].strip().lower() in tuple(values)
        check(f"{query} -> count-only: {want}", got is want, got)


def t_the_capability_is_the_same_word_on_both_sides():
    shipped = (HERE / "rebuilt" / "jarvis_events.py").read_text(encoding="utf-8")
    base = (REPO / "jarvis-backend" / "jarvis_events.py").read_text(encoding="utf-8")
    line = '"retrieve_count": _hud_has("_retrieve_counts"),'
    check("the shipped jarvis_events.py reports the capability", line in shipped, line)
    check("the published base copy says the same (they are kept in step)",
          line in base or line.replace("\n", "") in base)
    check("it is asked of the RUNNING server, like temporary_chat",
          '_hud_has("_temporary_chat")' in shipped and "_hud_has(" in shipped)
    # A capability that is false means hide the UI for it: the phone reads the
    # same word off the handshake.
    phone = (PHONE / "net" / "RetrieveCount.kt").read_text(encoding="utf-8")
    check("the phone asks for the same capability name",
          'const val CAPABILITY = "retrieve_count"' in phone)
    rt = (REPO / "jarvis-client/app/src/main/java/com/jarvis/client/JarvisRuntime.kt") \
        .read_text(encoding="utf-8")
    check("and nothing at all is sent without it",
          "can(com.jarvis.client.net.RetrieveCount.CAPABILITY)" in rt)
    # The stand-in the stack builds has it too, which is what _hud_has looks for.
    stand_in, log = _stack.stand_in("jarvis_hud.py")
    check("the stand-in of the whole stack carries the reader (what _hud_has finds)",
          stand_in is not None and re.search(r"^def _retrieve_counts\(", stand_in, re.M) is not None,
          (log or [])[-3:])
    stats = _stack.materialised("jarvis_hud.py")
    check("the walk's materialised-hunk pin is what it measures (see _stack.RATCHET)",
          stats["materialised"] == _stack.RATCHET["jarvis_hud.py"],
          f"measured {stats['materialised']}, pinned {_stack.RATCHET['jarvis_hud.py']}")
    check("retrieve-count.patch is in the walk", "retrieve-count.patch" in _stack.order())


def t_it_applies_last_and_nothing_ships_for_it():
    ps1 = PS1.read_text(encoding="utf-8")
    listed = ps1[ps1.index("$PATCHES = @("):]
    check("apply-patches.ps1 applies it", "'retrieve-count.patch'" in listed)
    check("after screen-attach.patch (every new patch goes last)",
          listed.index("'retrieve-count.patch'") > listed.index("'screen-attach.patch'"))
    check("it needs no new module copied in: nothing ships for it",
          not (HERE / "jarvis_retrieve_count.py").exists())


def t_the_parity_entry_is_registered_and_honest():
    """`tools/check_parity.py` used to carry `/api/retrieve` as the one `todo`
    entry. It is not `todo` any more, and the words have to say what the phone
    really does - counts, and never the words - or this fails."""
    src = PARITY.read_text(encoding="utf-8")
    m = re.search(r'^\s*"/api/retrieve": \("(\w+)", "(.*)"\),$', src, re.M)
    check("the /api/retrieve entry is registered in tools/check_parity.py", m is not None)
    if m is None:
        return
    kind, why = m.group(1), m.group(2)
    check("it is no longer `todo`", kind != "todo", kind)
    check("the phone calls the route, so `ported` is the honest word", kind == "ported", kind)
    lowered = why.lower()
    check("the description says the phone asks for the COUNT",
          "count" in lowered and "count=1" in lowered, why)
    check("... says it never gets or shows the words",
          "never" in lowered and "word" in lowered, why)
    check("... names the whole design, not just the route: the capability gate",
          "capabilit" in lowered, why)
    check("... says why it is safe on an older PC",
          "older" in lowered or "unpatched" in lowered, why)
    # The claim above is only true because the phone really calls it: the string
    # check_parity.py collects is the one in the phone's own source.
    phone = (PHONE / "net" / "RetrieveCount.kt").read_text(encoding="utf-8")
    check("the phone's own source carries the route check_parity.py reads",
          'const val PATH = "/api/retrieve"' in phone)
    check("the phone's request goes to that path with count=1",
          '"$PATH?q=$encoded&$COUNT_FLAG"' in phone and 'const val COUNT_FLAG = "count=1"' in phone)
    # And the docs describe both halves (the brief asked for this).
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("docs/JARVIS-API.md documents the route", "## 119." in api and "/api/retrieve" in api)
    check("... and says the phone shows the count only, and why",
          "count only" in api.lower() and "never the words" in api.lower(), "JARVIS-API.md")


def main() -> int:
    for fn in (t_the_patch_applies_to_the_state_the_stack_leaves,
               t_the_reply_is_counts_and_nothing_else,
               t_only_the_phones_own_flag_gets_the_count,
               t_the_capability_is_the_same_word_on_both_sides,
               t_it_applies_last_and_nothing_ships_for_it,
               t_the_parity_entry_is_registered_and_honest):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:                      # a broken check is a failure
            import traceback
            check(f"{fn.__name__} ran", False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
