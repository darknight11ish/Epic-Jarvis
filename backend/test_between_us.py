"""test_between_us.py - "Between us": a shared joke or nickname is an
ordinary fact with a label.

    python3 backend/test_between_us.py

The owner's decision of 2026-09-27 (CLAUDE.md): "Inside jokes: yes, a
'between us' list in Brain with Forget, from the owner's own words only."
Full design: docs/CUTTING-EDGE-2026-09-26-round4-growth.md section 7.

What "Between us" is, and is not:

  * NOT a new way to save a fact. "Remember: we call the printer 'the
    beast'" is saved exactly as any other "Remember: ..." is
    (jarvis_auto_learn.after_remember) - nothing here changes that.
  * A LABEL, `meta.kind == "shared"`, the owner's own tap adds to or takes
    off a fact that already exists - the same shape as pin/unpin for
    "Always keep in mind", except the label lives IN the fact's own meta
    (so it survives "Erase the words": ERASE_KEEPS_META now keeps `kind`).
  * Never set automatically, and never by the model - only
    MemoryStore.shared(), called from the owner's own tap through
    POST /api/memory/shared.
  * "Jarvis may use it in an answer when relevant, in Warm only":
    without_shared_in_plain() takes a shared fact out of what a Plain-manner
    turn recalls - jarvis_agent._run_memory_search (the memory_search tool)
    already calls it; with_profile() takes an optional `manner` for the
    same reason, for a caller that passes one.
  * The usual sensitive-topic checks are untouched: a shared fact can also
    be sensitive, and shared() never reads or writes `meta.sensitive`.
  * Never pinned automatically: shared() never touches the `profile` table.

What is proved here, against real SQLite files in a temp folder, the whole
patch stack, and jarvis_manner.py / jarvis_agent.py's own filtering:

No pytest, no network, no model.
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import time
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("rebuilt/jarvis_memory.py", "jarvis_manner.py", "jarvis_agent.py")

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-between-us-"))
try:
    import jarvis_memory as M
except ImportError:
    sys.path.append(str(REPO / "backend" / "rebuilt"))
    import jarvis_memory as M
import jarvis_manner as MN  # noqa: E402
import jarvis_agent as AG  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []

JOKE = "We call the printer 'the beast'"
PLAIN_FACT = "Owner's bank is Monzo"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass. (It used to be check("SKIP - ...", True) - a condition of
    the constant True, so it printed as a pass and was counted as one.)"""
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh(name: str):
    d = _TMP / name
    d.mkdir(parents=True, exist_ok=True)
    st = M.MemoryStore(path=d / "memory.db", embedder=M.HashEmbedder())
    M._store = st
    return st


# ------------------------------------------------------------------ the store

def t_tagging_and_untagging():
    st = fresh("tag")
    fid = st.add(JOKE)
    check("not shared yet", st.is_shared(fid) is False)
    out = st.shared(fid, True)
    check("tagged: ok, shared, changed, no words in the reply",
          out["ok"] and out["shared"] and out["changed"] and JOKE not in json.dumps(out), out)
    check("is_shared() now true", st.is_shared(fid) is True)
    check("the fact's own words are untouched", st.get(fid)["text"] == JOKE)
    again = st.shared(fid, True)
    check("tagging it again changes nothing", again["ok"] and not again["changed"], again)
    off = st.shared(fid, False)
    check("untagged: ok, changed, no longer shared",
          off["ok"] and off["changed"] and off["shared"] is False, off)
    check("is_shared() now false", st.is_shared(fid) is False)
    again_off = st.shared(fid, False)
    check("untagging again changes nothing", again_off["ok"] and not again_off["changed"], again_off)
    check("no such fact: 'no_such_fact', not raised",
          st.shared(987654, True) == {"ok": False, "id": 987654, "shared": False,
                                       "changed": False, "reason": "no_such_fact"})


def t_only_a_current_fact_can_be_tagged():
    st = fresh("current")
    fid = st.add(JOKE)
    st.retire(fid)
    out = st.shared(fid, True)
    check("a forgotten fact cannot be tagged: not_current, nothing changed",
          out["reason"] == "not_current" and not out["changed"] and st.is_shared(fid) is False, out)
    fid2 = st.add(JOKE + "2")
    st.erase(fid2)
    check("an already-erased fact cannot be tagged either",
          st.shared(fid2, True)["reason"] == "not_current")


def t_the_list_and_forget():
    st = fresh("list")
    a = st.add(JOKE)
    b = st.add("We call the router 'the goblin'")
    c = st.add(PLAIN_FACT)
    st.shared(a, True)
    st.shared(b, True)
    got = st.shared_facts()
    check("the list holds only tagged facts, newest first, full rows",
          [f["id"] for f in got] == [b, a]
          and [f["text"] for f in got] == ["We call the router 'the goblin'", JOKE], got)
    check("an ordinary fact never appears in it", c not in [f["id"] for f in got])
    st.retire(a)
    check("Forget on a shared fact takes it off the list, exactly like any other",
          [f["id"] for f in st.shared_facts()] == [b])
    check("... and it is no longer current, the usual way",
          all(f["id"] != a for f in st.current_facts()))
    check("(the tag itself is untouched underneath - erase() below reads it back)",
          M._fact_kind(st.get(a)["meta"]) == "shared")


def t_never_pinned_automatically():
    st = fresh("pin")
    fid = st.add(JOKE)
    st.shared(fid, True)
    check("tagging a fact never pins it", st.is_pinned(fid) is False and st.profile() == [])
    st.pin(fid)
    check("pinning it separately is the owner's own, independent choice",
          st.is_pinned(fid) is True and st.is_shared(fid) is True)
    st.unpin(fid)
    check("unpinning leaves the shared tag alone", st.is_shared(fid) is True)


def t_sensitive_checks_are_untouched():
    st = fresh("sensitive")
    fid = st.add(JOKE, meta={"sensitive": "health"})
    before = json.loads(st.get(fid)["meta"])["sensitive"]
    st.shared(fid, True)
    after = json.loads(st.get(fid)["meta"])
    check("shared() never reads or writes meta.sensitive - it is still there",
          after.get("sensitive") == before == "health", after)
    check("... and the shared tag sits beside it, not instead of it",
          after.get("kind") == "shared", after)


def t_erase_keeps_the_tag_never_the_words():
    st = fresh("erase")
    fid = st.add(JOKE)
    st.shared(fid, True)
    out = st.erase(fid)
    check("erased: the marker, not the words", st.get(fid)["text"] == M.ERASED_TEXT, out)
    check("meta.kind survives ERASE_KEEPS_META - the history still shows a shared joke sat here",
          M._fact_kind(st.get(fid)["meta"]) == "shared", st.get(fid))
    check("is_shared() still reads true - it is a label, not words", st.is_shared(fid) is True)
    check("but the list of CURRENT shared facts no longer has it (it is retired)",
          fid not in [f["id"] for f in st.shared_facts()])
    check("\"kind\" really is in ERASE_KEEPS_META", "kind" in M.ERASE_KEEPS_META)


# ------------------------------------------------------- Warm only (recall)

def t_without_shared_in_plain():
    shared_row = {"id": 1, "text": JOKE, "meta": json.dumps({"kind": "shared"})}
    plain_row = {"id": 2, "text": PLAIN_FACT, "meta": json.dumps({})}
    no_meta_row = {"id": 3, "text": "no meta key at all"}
    hits = [shared_row, plain_row, no_meta_row]
    check("plain manner: the shared fact is left out, everything else stays",
          M.without_shared_in_plain(hits, "plain") == [plain_row, no_meta_row])
    check("warm manner: nothing is filtered", M.without_shared_in_plain(hits, "warm") == hits)
    check("no manner known (None): nothing is filtered - the old behaviour",
          M.without_shared_in_plain(hits, None) == hits)
    check("an unknown manner: nothing is filtered either",
          M.without_shared_in_plain(hits, "sarcastic") == hits)
    check("empty or None hits: empty, never raises",
          M.without_shared_in_plain([], "plain") == [] and M.without_shared_in_plain(None, "plain") == [])


def t_with_profile_manner_leaves_pins_alone():
    st = fresh("withprofile")
    joke = st.add(JOKE)
    st.shared(joke, True)
    st.pin(joke)
    plain = st.add(PLAIN_FACT)
    hit = {"id": plain, "text": PLAIN_FACT, "meta": json.dumps({})}
    out_plain = M.with_profile(st, [hit], k=5, manner="plain")
    check("a PINNED shared fact still comes through even in Plain manner - "
          "pinning is its own, separate choice",
          any(p.get("id") == joke and p.get("pinned") for p in out_plain), out_plain)
    check("the ordinary search hit is still there too", any(h.get("id") == plain for h in out_plain))
    check("no `manner` argument at all: unchanged, exactly as before this feature",
          M.with_profile(st, [hit], k=5) == M.with_profile(st, [hit], k=5, manner=None))


def t_memory_search_tool_honours_manner():
    st = fresh("tool")
    joke = st.add(JOKE)
    st.shared(joke, True)
    plain = st.add(PLAIN_FACT)
    real_manner_now = AG._manner_now
    try:
        AG._manner_now = lambda *a, **k: "plain"
        out = AG._run_memory_search({"query": "printer beast Monzo bank", "k": 10})
        ids = {f["id"] for f in out["facts"]}
        check("memory_search, in Plain: the shared joke is never offered",
              joke not in ids, out)
        check("... an ordinary fact still is", plain in ids, out)
        AG._manner_now = lambda *a, **k: "warm"
        out2 = AG._run_memory_search({"query": "printer beast Monzo bank", "k": 10})
        check("memory_search, in Warm: the shared joke may be offered",
              joke in {f["id"] for f in out2["facts"]}, out2)
    finally:
        AG._manner_now = real_manner_now


def t_the_plain_manner_line_says_not_to_bring_up_shared_jokes():
    check("the Plain manner line tells the model not to bring up shared jokes",
          "shared jokes" in MN.NOTE["plain"] or "nicknames" in MN.NOTE["plain"], MN.NOTE["plain"])
    check("still short (test_manner.py's own limit)", len(MN.NOTE["plain"]) < 420)
    check("still says wording only and every rule applies",
          "wording only" in MN.NOTE["plain"].lower()
          and "rules still apply in full" in MN.NOTE["plain"].lower())
    check("the Warm line is unchanged by this feature - Warm may use it when relevant",
          "shared jokes" not in MN.NOTE["warm"])


# ------------------------------------------------------------------ the route

class _Handler:
    def __init__(self):
        self.sent = None

    def _send(self, code, body):
        self.sent = (code, body)
        return self.sent


def _fragment(src, start, stop, *, after=0):
    i = src.index(start, after)
    i = src.rfind("\n", 0, i) + 1
    j = src.index(stop, i)
    j = src.rfind("\n", 0, j) + 1
    return textwrap.dedent(src[i:j])


def _stacked():
    hud, log = _stack.stand_in("jarvis_hud.py")
    check("the whole jarvis_hud.py stack builds", hud is not None, "\n".join(log or [])[-400:])
    return hud


def _call(block, arg, raw=b"", *, origin=True, token=True, memory=True, module=None):
    ns = {"_origin_ok": lambda s: origin, "_token_ok": lambda s: token, "MEMORY": memory,
          "_read_body": lambda s: raw, "json": json, "jarvis_memory": module or M}
    exec(compile(f"def handle(self, {arg}):\n" + textwrap.indent(block, "    "),
                 "<memory-shared route>", "exec"), ns)
    h = _Handler()
    ns["handle"](h, "/api/memory/shared")
    return h.sent


def t_the_routes():
    hud = _stacked()
    if hud is None:
        return
    get = _fragment(hud, '        if path == "/api/memory/shared":',
                    '        if path in ("/api/memory/pending"')
    post = _fragment(hud, '        if route == "/api/memory/shared":',
                     '        if route == "/api/memory/erase":')
    check("the GET route sits right above 'pending', with its own checks",
          hud.index('if path == "/api/memory/shared":')
          < hud.index('if path in ("/api/memory/pending"'))
    check("the POST route sits right above erase, with its own checks",
          hud.index('if route == "/api/memory/shared":')
          < hud.index('if route == "/api/memory/erase":'))
    st = fresh("route")
    fid = st.add(JOKE)
    check("GET: another site's page (403)", _call(get, "path", origin=False)[0] == 403)
    check("GET: no or a wrong token (401)", _call(get, "path", token=False)[0] == 401)
    check("GET: memory not running (503)", _call(get, "path", memory=False)[0] == 503)
    check("POST: 403 and 401, nothing tagged",
          _call(post, "route", b'{"id": %d, "shared": true}' % fid, origin=False)[0] == 403
          and _call(post, "route", b'{"id": %d, "shared": true}' % fid, token=False)[0] == 401
          and st.is_shared(fid) is False)
    check("POST: not JSON is 400", _call(post, "route", b"nope")[0] == 400)
    for raw, why in ((b'{"id": %d}' % fid, "no 'shared' key"),
                     (b'{"id": %d, "shared": "yes"}' % fid, "'shared' not a bool"),
                     (b'{"id": "%d", "shared": true}' % fid, "id in quotes"),
                     (b'{"id": %d, "shared": true, "extra": 1}' % fid, "an extra key")):
        code, body = _call(post, "route", raw)
        check(f"POST 400: {why}", code == 400 and st.is_shared(fid) is False, (code, body))
    code, body = _call(post, "route", b'{"id": %d, "shared": true}' % fid)
    check("POST: tagged (200), no words in the reply",
          code == 200 and body["shared"] and JOKE not in json.dumps(body), (code, body))
    code, body = _call(get, "path")
    check("GET: the list, the words, the id",
          code == 200 and [f["text"] for f in body["facts"]] == [JOKE]
          and body["facts"][0]["id"] == fid, (code, body))
    code, body = _call(post, "route", b'{"id": 424242, "shared": true}')
    check("POST: no such fact is 404 with its reason",
          code == 404 and body["reason"] == "no_such_fact", (code, body))
    st.retire(fid)
    code, body = _call(post, "route", b'{"id": %d, "shared": true}' % fid)
    check("POST: no longer current is 409 in words",
          code == 409 and body["reason"] == "not_current"
          and body["error"] == M.SHARED_NOT_CURRENT, (code, body))
    old = types.SimpleNamespace(store=M.store)
    check("an older jarvis_memory.py: 501 in words, both ways",
          _call(get, "path", module=old)[0] == 501
          and _call(post, "route", b'{"id": %d, "shared": false}' % fid, module=old)[0] == 501
          and "jarvis_memory.py" in _call(get, "path", module=old)[1]["error"])


def t_listed_where_it_must_be():
    names = [str(p).replace("\\", "/").split("/")[-1] for p in _stack.order()]
    check("memory-shared.patch is in apply-patches.ps1's order, after memory-profile",
          "memory-shared.patch" in names
          and names.index("memory-shared.patch") > names.index("memory-profile.patch"), names[-3:])
    check("the store that does the work is shipped whole",
          "rebuilt/jarvis_memory.py" in _where_shipped())


def _where_shipped():
    import _where
    return _where.SHIPPED


def t_the_patch_applies_forwards_and_backwards():
    import shutil
    import subprocess
    git = shutil.which("git")
    if not git:
        return skip("git is not installed")
    order = _stack.order()
    at = order.index("memory-shared.patch")
    before, log = _stack.stand_in("jarvis_hud.py", order[:at])
    check("jarvis_hud.py: the stack before memory-shared.patch builds", before is not None,
          "\n".join(log or [])[-400:])
    if before is None:
        return
    d = _TMP / "patch-check"
    d.mkdir(parents=True, exist_ok=True)
    (d / "jarvis_hud.py").write_text(before, encoding="utf-8")
    shutil.copy(HERE / "memory-shared.patch", d / "p.patch")
    materialised = sum(1 for line in (log or []) if "materialised" in line)
    check("every hunk of it found its context (none made up)",
          not any("memory-shared.patch: materialised" in line for line in (log or [])),
          materialised)
    for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
        r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                           text=True)
        check(f"git apply {' '.join(extra) or '(forwards)'} memory-shared.patch",
              r.returncode == 0, r.stderr.strip())
    full = _stack.stand_in("jarvis_hud.py", order[:at + 1])[0]
    check("forwards gives the stack's own text",
          (d / "jarvis_hud.py").read_text(encoding="utf-8") == full)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
