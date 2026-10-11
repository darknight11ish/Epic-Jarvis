r"""Build backend/ollama-direct.patch from the owner's real jarvis_hud.py.

Run this when it has to change:

    python3 tools/gen_ollama_direct_patch.py [path to jarvis_hud.py]

WHAT IT PUTS IN THE HUD, AND WHAT IT DELIBERATELY LEAVES OUT

`_completions_url(lane, body)` is the one line of `_open` this work may change,
so it does four small things and nothing else:

  1. adds the helper itself, which used to send EVERY lane to `JARVIS_URL` -
     OpenJarvis's own port, a program this setup never installs;
  2. sends the local lane to Ollama's own OpenAI-compatible endpoint;
  3. for a non-local lane, ASKS `jarvis_chatbot_api.lane_state(lane)` where the
     request should go, puts the answer's model ON THE BODY IT IS HANDED (the
     copy of `payload` that `_open` is about to serialise - a parameter, never
     a name read from around here: see the helper's own comment), and returns
     that service's own pinned https address;
  4. adds nothing else. Which service, which model, which key and why a lane
     cannot be used are the MODULE's answer; the HUD only carries it. That is
     the whole point of `lane_state`/`last_lane_state`: this patch is ~40 added
     lines, not ~60, and the HUD's own logic does not grow.

`_auth_headers` - the one place a request's Authorization header is built -
reads this thread's resolved lane back from the same module
(`last_lane_state()["key"]`) instead of Jarvis's pairing token. The key is
never a name in the HUD's own scope, is never logged, and is never written to
disk (rule 3); a local lane has nothing stored, so it behaves exactly as it did
before.

WHAT IS NOT REBUILT HERE

  * `cloud-one-turn.patch` - its added lines are read back by tests, and its
    context is `body = dict(payload); body["model"] = lane` and the
    `urllib.request.urlopen(` call. Its LAST context line is the call itself,
    and that is the one line this patch changes on purpose: the helper is
    handed the body it must put the model on, so the call reads
    `_completions_url(lane, body),`. Because cloud-one-turn.patch's context
    covers that line, its copy was re-anchored in the same commit (2026-10-06)
    rather than left broken; every other line of that context - the
    `body = dict(payload)` line, which chat-history.patch and
    rules-first-relay.patch also anchor on, and the whole `urlopen(...)` call -
    is untouched, and this patch may not rewrite any of it.
    `test_cloud_one_turn.py` and `test_ollama_direct.py` are what catch a
    mistake in either rule; run them first.
  * THE 503's CLOUD WORDING. The message a failed cloud lane shows is
    `chat-stream.patch`'s: it rewrites that whole block later in the stack. So
    the block is only LIFTED into `unreachable_msg` here, with the words it
    already had, so that chat-stream has the text it anchors on - nothing about
    what the owner reads changes on this patch's account alone.
    `test_second_card.py` and `test_cloud_one_turn.py` are what catch a
    mistake in either of those two rules; run them first.

IT EXPECTS THE STATE JUST BEFORE THIS PATCH. On the owner's machine the older
text of this same patch is already applied, and apply-patches.ps1 takes that
older text off (backend/patch-history holds it) before it puts this one on - so
the file this reads must be the file at that moment:

    $d = "C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\Desktop program"
    cd $d
    git apply -R <the older backend/ollama-direct.patch>   # or let the script do it
    py -3 <repo>\\tools\\gen_ollama_direct_patch.py "$d\jarvis_hud.py"

Generating from the file with the older text still on it would write a patch
whose removed lines only exist there, and it would not apply for anyone else.
"""
import difflib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKEND = REPO / "backend"
DEFAULT_HUD = (Path.home() / "Documents" / "Claude" / "Open jarvis files"
               / "Desktop program" / "jarvis_hud.py")


# ===========================================================================
#   ollama-direct.patch
# ===========================================================================

#: Where the helper goes: the lines `route_header["memory_side"]` ends on, just
#: above `_open` and `_completions_url`. The whole block is the anchor rather
#: than the last two lines alone, because `"jarvis" if jarvis_side_memory ...`
#: reads exactly the same in more than one route.
OLD_ANCHOR = '''        route_header["memory_side"] = (
            "jarvis" if jarvis_side_memory else ("hud" if injected else "none")
        )

'''

#: The helper, and everything this patch has to say about a lane's transport.
#: The module's `lane_state()` does the deciding - this asks once, puts the
#: answer's model on the body it is HANDED and returns the answer's address.
#:
#: `body` is a PARAMETER, and that is the whole of the 2026-10-06 fix. This
#: function is nested in do_POST, where a bare `body` is do_POST's own parsed
#: request (`body = json.loads(raw or b"{}")`), while the object `_open`
#: serialises is its own `body = dict(payload)` copy - a sibling function's
#: local, not an enclosing one's, so it was never in scope here. The first
#: version of this helper wrote `body["model"] = _state["model"]` with no
#: parameter at all, so the service's model landed on do_POST's parsed request
#: and the request that actually went out kept the LANE's name
#: (`jarvis-escalate`): the cloud lane reached DeepSeek and asked it for a
#: model that does not exist. The caller now passes the very dict it is about
#: to hand to `json.dumps`, one argument to the left of it in the same call, so
#: the same resolution that decides the address also names the model asked of
#: it - and a lane this PC cannot pay for writes nothing, exactly as before.
#:
#: The empty lane name is passed for the LOCAL lane on purpose: `lane_state`
#: STORES what it resolves on this thread, and the empty one clears it, so a
#: hop back down the degrade chain can never leave a cloud lane's key where the
#: next `_auth_headers` call would pick it up and send it to Ollama.
#:
#: Nothing here reads a key, decides a price, or knows a service's name.
NEW_FUNCTION = '''        def _completions_url(lane: str, body: dict) -> str:
            # The local lane talks to Ollama directly, which has spoken this
            # exact OpenAI-compatible shape for a long time - no separate
            # agent process required.
            #
            # A non-local lane goes to the service behind it: which service,
            # which model, which key and why it cannot be used are
            # `lane_state()`'s answer in jarvis_chatbot_api.py, not this file's.
            # A lane this PC cannot pay for comes back with no address, so the
            # request goes to the LOCAL endpoint and nothing is spent. The local
            # lane is passed as the empty name, which clears this thread's
            # answer - a hop back down cannot leave a cloud key behind (rule 3).
            #
            # `body` is the request `_open` is about to send - its own copy of
            # `payload`, handed in as a parameter on purpose. This function is
            # nested in do_POST, where a bare `body` is do_POST's PARSED
            # REQUEST, and `_open`'s copy is a sibling's local, never in scope
            # here: writing `body["model"]` without the parameter put the
            # service's model on an object nothing serialises and left the
            # LANE's own name on the request that went out. The caller passes
            # the dict it is about to give `json.dumps`, in the same call, so
            # the address and the model asked of it can never disagree.
            try:
                import jarvis_chatbot_api as _api
                _state = _api.lane_state(lane if lane != local_model else "")
            except Exception:
                _state = {}
            if _state.get("url"):
                body["model"] = _state["model"]
                return _state["url"]
            return f"{OLLAMA_URL}/v1/chat/completions"

'''

NEW_ANCHOR = OLD_ANCHOR + NEW_FUNCTION

#: The request `_open` builds used to name `JARVIS_URL` itself; it asks the
#: helper now, and hands it the body the helper must put the resolved model on.
#: This line is also the last line of cloud-one-turn.patch's own context, so
#: that patch's copy of it is re-anchored to this text (2026-10-06, same
#: commit) - and it must stay exactly `_completions_url(lane, body),`.
OLD_CALL = '''                    f"{JARVIS_URL}/v1/chat/completions",
'''

NEW_CALL = '''                    _completions_url(lane, body),
'''

OLD_AUTH = '''def _auth_headers(extra: dict | None = None) -> dict:
    headers = dict(extra or {})
    if JARVIS_API_KEY:
        headers["Authorization"] = f"Bearer {JARVIS_API_KEY}"
    return headers
'''

NEW_AUTH = '''def _auth_headers(extra: dict | None = None) -> dict:
    # The one place a request's Authorization header is built. A cloud lane
    # carries its own service's key instead of Jarvis's pairing token: the
    # resolved lane is read back from jarvis_chatbot_api, never a name in this
    # file - never logged, never on disk (rule 3). A local lane stores nothing,
    # so this behaves as it did before.
    headers = dict(extra or {})
    try:
        import jarvis_chatbot_api as _api
        bearer = _api.last_lane_state().get("key") or JARVIS_API_KEY
    except Exception:
        bearer = JARVIS_API_KEY
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers
'''

#: The 503 `_open`'s caller sends, as the stack has it BEFORE this patch: one
#: message, no name, whichever lane failed. This patch only lifts it, and the
#: words are the same ones - the cloud half's real wording is chat-stream's.
OLD_UNREACHABLE = '''                self._send(503, {
                    "error": f"Jarvis is not answering on {JARVIS_URL}. "
                             f"Start it with `uv run jarvis serve`. ({exc})",
                    "route": route_header,
                })
'''

NEW_UNREACHABLE = '''                unreachable_msg = (
                    f"Ollama is not answering on {OLLAMA_URL}. "
                    f"Start it with `ollama serve`. ({exc})"
                    if lane == local_model else
                    f"Jarvis is not answering on {JARVIS_URL}. "
                    f"Start it with `uv run jarvis serve`. ({exc})"
                )
                self._send(503, {
                    "error": unreachable_msg,
                    "route": route_header,
                })
'''

#: (what, the text this patch replaces, its after-image). The anchor first: it
#: is what the helper is inserted against, and the lines it carries stay unique
#: afterwards.
DIRECT_EDITS = (("the helper's insertion point", OLD_ANCHOR, NEW_ANCHOR),
                ("_auth_headers", OLD_AUTH, NEW_AUTH),
                ("the request `_open` builds", OLD_CALL, NEW_CALL),
                ("the 503's words", OLD_UNREACHABLE, NEW_UNREACHABLE))


def build_direct(text: str) -> str:
    for what, old, new in DIRECT_EDITS:
        if text.count(old) != 1:
            raise SystemExit(f"ollama-direct, {what}: expected exactly one match, "
                             f"found {text.count(old)}")
        text = text.replace(old, new, 1)
    return text


def _diff(old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True),
                                        new.splitlines(keepends=True),
                                        fromfile="a/jarvis_hud.py",
                                        tofile="b/jarvis_hud.py", n=3))


def main(argv) -> int:
    src = Path(argv[0]) if argv else DEFAULT_HUD
    old = src.read_text(encoding="utf-8")
    direct = build_direct(old)
    text = _diff(old, direct)
    if not text:
        raise SystemExit("ollama-direct.patch: nothing changed")
    added = sum(1 for l in text.splitlines()
                if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in text.splitlines()
                  if l.startswith("-") and not l.startswith("---"))
    out = BACKEND / "ollama-direct.patch"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(text.splitlines())} lines, "
          f"+{added}/-{removed})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
