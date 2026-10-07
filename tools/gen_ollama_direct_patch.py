"""Build backend/ollama-direct.patch and backend/cloud-lane-transport.patch
from the owner's real jarvis_hud.py.

Run this when either has to change:

    python3 tools/gen_ollama_direct_patch.py       # both of these patches

Two patches, because the stack already had two owners for these lines:

  ollama-direct.patch        the local lane reaches Ollama directly (one added
                             helper), and the one place a request's
                             Authorization header is built learns the
                             difference between Jarvis's own pairing token and
                             a cloud service's key.
  cloud-lane-transport.patch the cloud escalation lane's real transport: the
                             helper resolves the lane through
                             jarvis_chatbot_api.py, asks the service for ITS
                             model and sends ITS key - and answers locally when
                             the lane cannot be paid for.

WHY THE WHOLE RESOLUTION LIVES INSIDE `_completions_url`. It is the one line
of `_open` that this work may change: `_open`'s own body - `body["model"] =
lane`, and the `urllib.request.urlopen(urllib.request.Request(
_completions_url(lane), ...))` call - is cloud-one-turn.patch's context, and
nothing here may rewrite it or that patch stops applying to the file it was
written for. So `_completions_url` does four things in one added block:

  1. decides the URL - Ollama for the local lane, the service's own pinned
     https completions address for a cloud lane that can be paid for;
  2. resolves WHICH model to ask for, and remembers it, so the model the
     service is asked for and the address can never disagree;
  3. reads that service's key out of Windows Credential Manager (rule 3) and
     leaves it where the whole-request `_auth_headers` call picks it up;
  4. reports, once per request, when the cloud lane failed - so the 503 the
     owner sees names the service that was really tried.

A lane this PC cannot pay for goes to the LOCAL endpoint instead, which is
the honest answer - this PC answers, nothing is spent - and `_cloud_model`
stays empty, so the request keeps the local model's name and Jarvis's own
pairing token, exactly as a local turn always did.

NOT REBUILT HERE: cloud-one-turn.patch. Its added lines are read back by
tests (test_obsidian_notes.py runs them, test_cloud_one_turn.py lifts them
out), so its text is kept exactly as it is - and its context is the very
lines described above, left untouched on purpose.

IT EXPECTS THE PRISTINE FILE. The owner's copy of jarvis_hud.py already has
this whole patch stack applied, so de-apply the stack first, generate, then
apply it again:

    $d = "C:\\Users\\pcadmin\\Documents\\Claude\\Open jarvis files\\Desktop program"
    cd $d
    # every jarvis_hud.py patch in apply-patches.ps1, LAST FIRST:
    git apply -R <patch> ...
    py -3 <repo>\\tools\\gen_ollama_direct_patch.py "$d\\jarvis_hud.py"
    # the same list, first to last, from <repo>\\backend:
    git apply <patch> ...

    python3 tools/gen_ollama_direct_patch.py [path to jarvis_hud.py]
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

OLD_COMPLETIONS = '''        def _completions_url(lane: str) -> str:
            # The local lane talks to Ollama directly, which has spoken this
            # exact OpenAI-compatible shape for a long time - no separate
            # agent process required. A non-local lane (only reachable at
            # all when PROXY_FILE lists one - see _lane_names()) still goes
            # to JARVIS_URL, because this project has no other cloud-lane
            # transport today. That path is therefore unimplemented in
            # practice on a machine with no litellm-proxy.yaml, which is
            # every machine so far; it is left as-is rather than silently
            # papered over, so the day a cloud lane is actually configured
            # this is the one place that needs a real answer, not a second
            # thing to discover broken.
            return (f"{OLLAMA_URL}/v1/chat/completions" if lane == local_model
                    else f"{JARVIS_URL}/v1/chat/completions")
'''

#: ollama-direct's own after-image: the cloud half added, and the hunk
#: deliberately widened all the way to the request `_open` builds.
#:
#: THAT WIDTH IS LOAD-BEARING. `cloud-one-turn.patch`'s context is
#: `body = dict(payload); body["model"] = lane` and the
#: `urllib.request.urlopen(` call, and `_skeleton.build()` - the stand-in
#: test_cloud_one_turn.py rehearses against - holds only what a patch writes.
#: If this hunk stopped at the helper, those lines would be in no patch's
#: reach and that rehearsal would fail (it did).
NEW_COMPLETIONS_DIRECT = '''        def _completions_url(lane: str) -> str:
            # The local lane talks to Ollama directly, which has spoken this
            # exact OpenAI-compatible shape for a long time - no separate
            # agent process required.
            #
            # A non-local lane goes to the service behind it, through
            # jarvis_chatbot_api.py's own adapter family: HTTPS to that
            # service's pinned host, the key from Windows Credential Manager
            # only, the same monthly money limit and answer-length cap, and a
            # redirect refused. That was the "one place that needs a real
            # answer" the comment here used to ask for (the old answer - send
            # it to JARVIS_URL, OpenJarvis's own port - was unimplemented on
            # every machine so far).
            #
            # The whole resolution happens HERE, in this one line of _open,
            # on purpose. The rest of _open's body is cloud-one-turn.patch's
            # context, and rewriting any of it would stop that patch applying
            # to the file it was written for - so this function decides the
            # address, resolves which model the service is asked for, reads
            # that service's key and reports a failure, all before it returns
            # the URL it is asked for. The per-request names it sets are read
            # by `_auth_headers` (for the key) and by the 503's words (for the
            # reason).
            #
            # It runs once per request, on every hop of the degrade loop,
            # because every hop comes through _open. A lane this PC cannot pay
            # for - no key saved, a model with no price, this month's money
            # limit reached, or a message the month cannot pay for - goes to
            # the LOCAL endpoint instead: this PC answers, nothing is spent,
            # and `_cloud_model` stays empty so the request keeps the local
            # model's name and Jarvis's own pairing token. That is the strict
            # reading of the owner's rule ("a money limit comes before API
            # chatbots are used for real").
            #
            # The key is put where `_auth_headers` - called by the very next
            # lines of _open, for this same request, after this returns -
            # picks it up. Rule 3: it goes only to that service's own pinned
            # https address, is never logged, and is never written to disk.
            nonlocal _cloud_model, _cloud_key, _cloud_problem
            _cloud_model, _cloud_key, _cloud_problem = {}, "", ""
            if lane != local_model:
                try:
                    import jarvis_chatbot_api as _CA
                    _cloud_lane = _CA.cloud_lane(lane)
                    if _cloud_lane:
                        _cloud_model = _cloud_lane
                        _cloud_key = _CA.lane_key(lane) or ""
                        # The body's model is the LANE's name; the service
                        # needs its own. Rewritten here, before the request is
                        # built, because this runs first.
                        body["model"] = _cloud_lane["model"]
                    else:
                        _cloud_problem = _CA.ready_for(_CA.lane_service(lane)[0])
                except Exception as exc:
                    _cloud_problem = (f"The cloud lane could not be set up "
                                      f"({type(exc).__name__}).")
            if _cloud_model:
                return _cloud_model["url"]
            if lane != local_model and not _cloud_problem:
                # A cloud lane whose service answered nothing at all: the
                # same words the local branch would have used are wrong here,
                # so the request goes to the local endpoint knowingly.
                _cloud_problem = (f"The cloud model is not set up on this PC. "
                                  f"The cloud lane needs a saved key and a "
                                  f"monthly money limit for the service behind "
                                  f"it, both set on the PC.")
            return f"{OLLAMA_URL}/v1/chat/completions"

        # A rate-limited lane should step down, not surface a 429 to the user.
        # jarvis_router.degrade() has always described that chain; nothing
        # ever called it, so the documented behaviour did not exist. Try the
        # chosen lane, and on a refusal walk one step down and try again -
        # downward only, never back into the lane that just said no.
        #
        # The lines below are CONTEXT, on purpose: this hunk reaches all the
        # way to the request `_open` builds, so that
        # `cloud-one-turn.patch` - whose own context is `body = dict(payload);
        # body["model"] = lane` and the `urllib.request.urlopen(` call - keeps
        # the text it anchors on. `_skeleton.build()`, the stand-in
        # test_cloud_one_turn.py rehearses against, holds only what a patch
        # writes, so those lines have to be in some earlier patch's reach.
        def _open(lane: str):
            body = dict(payload); body["model"] = lane
            # chat-history.patch: the apps' own bookkeeping (provenance,
            # conversation_id, device) never reaches a model - not on the
            # request, not on any message, on every hop of the relay. See
            # _chat_client_fields_off.
            body = {k: v for k, v in body.items() if k not in _CHAT_CLIENT_FIELDS}
            if "messages" in body:
                body["messages"] = _chat_client_fields_off(body["messages"])
            return urllib.request.urlopen(
                urllib.request.Request(
                    _completions_url(lane),
'''

NEW_COMPLETIONS_TRANSPORT = '''        def _completions_url(lane: str) -> str:
            # The local lane talks to Ollama directly, which has spoken this
            # exact OpenAI-compatible shape for a long time - no separate
            # agent process required.
            #
            # A non-local lane goes to the service behind it, through
            # jarvis_chatbot_api.py's own adapter family: HTTPS to that
            # service's pinned host, the key from Windows Credential Manager
            # only, the same monthly money limit and answer-length cap, and a
            # redirect refused. That was the "one place that needs a real
            # answer" the comment here used to ask for (the old answer - send
            # it to JARVIS_URL, OpenJarvis's own port - was unimplemented on
            # every machine so far).
            #
            # The whole resolution happens HERE, in this one line of _open,
            # on purpose. The rest of _open's body is cloud-one-turn.patch's
            # context (the model line, the cut, the request's own lines), and
            # rewriting any of it would stop that patch applying to the file
            # it was written for - so this function decides the address,
            # resolves which model the service is asked for, reads that
            # service's key and reports a failure, all before it returns the
            # URL it is asked for. The per-request names it sets are declared
            # by the `nonlocal` line below and read by `_auth_headers` (for
            # the key) and by the 503's words (for the reason).
            #
            # It runs once per request, on every hop of the degrade loop,
            # because every hop comes through _open. A lane this PC cannot pay
            # for - no key saved, a model with no price, this month's money
            # limit reached, or a message the month cannot pay for - goes to
            # the LOCAL endpoint instead: this PC answers, nothing is spent,
            # and `_cloud_model` stays empty so the request keeps the local
            # model's name and Jarvis's own pairing token. That is the strict
            # reading of the owner's rule ("a money limit comes before API
            # chatbots are used for real").
            #
            # The key is put where `_auth_headers` - called by the very next
            # lines of _open, for this same request, after this returns -
            # picks it up. Rule 3: it goes only to that service's own pinned
            # https address, is never logged, and is never written to disk.
            nonlocal _cloud_model, _cloud_key, _cloud_problem
            _cloud_model, _cloud_key, _cloud_problem = {}, "", ""
            if lane != local_model:
                try:
                    import jarvis_chatbot_api as _CA
                    _cloud_lane = _CA.cloud_lane(lane)
                    if _cloud_lane:
                        _cloud_model = _cloud_lane
                        _cloud_key = _CA.lane_key(lane) or ""
                        # The body's model is the LANE's name; the service
                        # needs its own. Rewritten here, before the request is
                        # built, because this runs first.
                        body["model"] = _cloud_lane["model"]
                    else:
                        _cloud_problem = _CA.ready_for(_CA.lane_service(lane)[0])
                except Exception as exc:
                    _cloud_problem = (f"The cloud lane could not be set up "
                                      f"({type(exc).__name__}).")
            if _cloud_model:
                return _cloud_model["url"]
            if lane != local_model and not _cloud_problem:
                # A cloud lane whose service answered nothing at all: the
                # same words the local branch would have used are wrong here,
                # so the request goes to the local endpoint knowingly.
                _cloud_problem = (f"The cloud model is not set up on this PC. "
                                  f"The cloud lane needs a saved key and a "
                                  f"monthly money limit for the service behind "
                                  f"it, both set on the PC.")
            return f"{OLLAMA_URL}/v1/chat/completions"
'''

OLD_AUTH = '''def _auth_headers(extra: dict | None = None) -> dict:
    headers = dict(extra or {})
    if JARVIS_API_KEY:
        headers["Authorization"] = f"Bearer {JARVIS_API_KEY}"
    return headers
'''

NEW_AUTH = '''def _auth_headers(extra: dict | None = None) -> dict:
    # The one place a request's Authorization header is built. A cloud
    # escalation lane carries its own service's key instead of Jarvis's
    # pairing token (cloud-lane-transport.patch): `_completions_url`, which
    # _open calls immediately before this, leaves the resolved service's key
    # in the enclosing scope. The key goes only to that service's own pinned
    # https address; a redirect is refused, so urllib can never carry it
    # anywhere else (rule 3). A local lane leaves nothing there, so this
    # behaves exactly as it did before.
    headers = dict(extra or {})
    bearer = _cloud_key or JARVIS_API_KEY
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers
'''

OLD_UNREACHABLE = '''                unreachable_msg = (
                    f"The local model is not running. Open Ollama on this PC "
                    f"(or run `ollama serve`), then try again. "
                    f"(Details: nothing answered at {OLLAMA_URL}: {exc})"
                    if lane == local_model else
                    f"The cloud model is not set up on this PC - nothing "
                    f"answers at {JARVIS_URL}. Pick the local model and ask "
                    f"again. (Details: {exc})"
                )
'''

NEW_UNREACHABLE = '''                unreachable_msg = (
                    f"The local model is not running. Open Ollama on this PC "
                    f"(or run `ollama serve`), then try again. "
                    f"(Details: nothing answered at {OLLAMA_URL}: {exc})"
                    if lane == local_model else
                    # The cloud lane names the service it really tried, and
                    # says what is missing when it could not be set up at all.
                    # The old sentence blamed JARVIS_URL (OpenJarvis's own
                    # port) and told the owner to pick the local model - the
                    # wrong thing to act on now that the lane has a real
                    # destination.
                    (f"The cloud model is not answering at {_cloud_model['host']}. "
                     f"Check this PC's internet connection, then ask again. "
                     f"(Details: {exc})"
                     if _cloud_model else
                     f"{_cloud_problem} (Details: {exc})")
                )
'''

#: (name, the text ollama-direct.patch replaces, its after-image)
DIRECT_EDITS = (("_completions_url", OLD_COMPLETIONS, NEW_COMPLETIONS_TRANSPORT),
                ("_auth_headers", OLD_AUTH, NEW_AUTH),
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
    out = BACKEND / "ollama-direct.patch"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
