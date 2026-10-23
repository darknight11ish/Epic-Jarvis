"""The HUD's two request-edge checks, tested as the EXACT production code.

    python3 backend/test_origin.py

WHY THIS SUITE EXISTS (SECPRIV audit 2026-10-18, and Gemini's ruling on it).
`jarvis_hud.py` is on the owner's PC and is not in this repository. The checks
that decide whether a request may enter - `_origin_ok` (an Origin must be one
this server was configured to serve; no Origin needs `X-Jarvis-Client: hud`)
and `_token_ok` (header, cookie or one-time query token, compared as bytes) -
therefore used to be tested only by lifting them out of the installed HUD. On
a clean checkout that suite SKIPPED, so CI never ran the real decision at all.

`hud-origin-module.patch` moves those two decisions into
`jarvis_owner_check.py` (a tracked, $SHIPPED module) and leaves `jarvis_hud.py`
with a thin delegation plus the parts only the running server knows
(`_served_origins()` - the bind address and HUD_PORT - `HUD_TOKEN`, and the two
request extractors). This suite imports the production functions and runs with
ZERO skips: no owner PC, no live HUD, no network.

WHAT STAYS IN THE LIVE HUD, HONESTLY: `_served_origins()` (configuration),
`HUD_TOKEN` resolution, `_cookie`/`_query_token` extraction, and the call sites
that pass them in. This suite proves the DECISION is right and that the patch
wires the HUD to it; it cannot prove the owner's copy of `jarvis_hud.py` has
the patch applied - `backend/test_origin_hud_header.py` still does that check
on the owner's PC when the file is there.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_owner_check as OC  # noqa: E402

FAILED, PASSED = [], []
PATCH = HERE / "hud-origin-module.patch"
PS1 = HERE.parent / "scripts" / "apply-patches.ps1"


def check(name, cond, detail=""):
    (FAILED if not cond else PASSED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class FakeHandler:
    """The duck-typed request the two production functions accept."""

    def __init__(self, *, headers=None, client_address=("127.0.0.1", 5000),
                 path="/"):
        self.headers = dict(headers or {})
        self.client_address = client_address
        self.path = path


#: A device on the owner's Tailscale/Meshnet, and a public address that is
#: not: the two peers the mesh-Origin rule (Bite 1) turns on.
MESH_PEER = ("100.96.1.25", 50000)
PUBLIC_PEER = ("203.0.113.5", 50000)


def t_origin_ok_is_the_decision_the_hud_makes():
    served = {"http://127.0.0.1:4719", "http://localhost:4719",
              "http://100.64.12.3:4719"}
    for origin in served:
        check(f"a served Origin is allowed: {origin}",
              OC.origin_ok(FakeHandler(headers={"Origin": origin}), served))
    for origin in ("http://attacker.example", "http://127.0.0.1:9999",
                   "https://evil.example", "null"):
        check(f"an Origin we do not serve is refused: {origin}",
              not OC.origin_ok(FakeHandler(headers={"Origin": origin}), served))
    # A trailing slash is the same origin to a browser.
    check("a trailing slash on a served origin still counts",
          OC.origin_ok(FakeHandler(headers={"Origin": "http://127.0.0.1:4719/"}),
                       served))
    # DNS rebinding: the attacker page's Origin is not a served origin, whatever
    # its Host header says (this function never reads Host).
    check("a matching Host header does not rescue an outside Origin",
          not OC.origin_ok(FakeHandler(headers={
              "Origin": "http://attacker.example",
              "Host": "attacker.example"}), served))
    # No Origin: only the HUD's own header, exactly.
    for value in ("hud",):
        check(f"no Origin + X-Jarvis-Client: {value} is allowed",
              OC.origin_ok(FakeHandler(headers={"X-Jarvis-Client": value}),
                           served))
    for headers in ({}, {"X-Jarvis-Client": ""}, {"X-Jarvis-Client": "HUD"},
                    {"X-Jarvis-Client": "phone"}, {"Origin": ""}):
        check(f"no usable Origin and header {headers.get('X-Jarvis-Client')!r} "
              "is refused",
              not OC.origin_ok(FakeHandler(headers=headers), served))


def t_token_ok_is_the_decision_the_hud_makes():
    token = "a-long-random-token"
    h = FakeHandler(headers={"X-Jarvis-Token": token})
    check("the header with the right token is allowed",
          OC.token_ok(h, token, lambda _h: "", lambda _h: ""))
    check("a wrong header token is refused",
          not OC.token_ok(FakeHandler(headers={"X-Jarvis-Token": "wrong"}),
                          token, lambda _h: "", lambda _h: ""))
    check("the cookie is a second way (SameSite=Strict)",
          OC.token_ok(FakeHandler(), token, lambda _h: token, lambda _h: ""))
    check("the one-time query token is the third",
          OC.token_ok(FakeHandler(), token, lambda _h: "", lambda _h: token))
    # A latin-1 header byte is not ASCII; compare_digest on str would raise.
    # The decision must be "refused", never a traceback.
    try:
        got = OC.token_ok(FakeHandler(headers={"X-Jarvis-Token": "\xff\xfe"}),
                          token, lambda _h: "", lambda _h: "")
        raised = False
    except Exception:
        raised = True
        got = None
    check("a non-ASCII token is refused, never raised", raised is False and got is False)
    # No token configured: loopback only, and that must fail closed for others.
    for peer, expected in (("127.0.0.1", True), ("::1", True),
                           ("::ffff:127.0.0.1", True),
                           ("100.101.102.103", False), ("", False)):
        got = OC.token_ok(FakeHandler(client_address=(peer, 1)), "",
                          lambda _h: "", lambda _h: "")
        check(f"with no token, peer {peer!r} is {'allowed' if expected else 'refused'}",
              got is expected, got)
    # A handler whose headers raise is a refusal, not a crash.
    class Broken:
        @property
        def headers(self):
            raise RuntimeError("no headers")
    check("a handler that cannot be read is refused, never raised",
          OC.token_ok(Broken(), token, lambda _h: "", lambda _h: "") is False)


def t_bite1_mesh_origins_are_accepted_from_the_owners_network():
    """Bite 1 of the PWA blueprint (2026-10-23): a browser on the owner's
    iPad or second PC opens Jarvis by its Meshnet / Tailscale name, so the
    Origin it sends is a name `_served_origins()` never lists - that set is
    built from the bind address and the port, not from a DNS name. It must be
    accepted - but only from a peer on this PC or the private mesh, only over
    http(s), only on a port this server serves, and never for a third-party
    page. A public address must get nothing new from any of it."""
    served = {"http://127.0.0.1:4719"}       # the configuration: no `.nord`
    accepted = ("http://mariorelan11-alps.nord:4719",
                "https://mariorelan11-alps.nord:4719",
                "http://my-pc.tailnet.ts.net:4719",
                "https://my-pc.tailnet.ts.net:4719",
                "http://100.96.1.25:4719",
                "http://sub.mariorelan11-alps.nord:4719",
                "http://mariorelan11-alps.nord",          # no explicit :4719
                "http://localhost:4719",
                "http://[::1]:4719")
    for origin in accepted:
        check(f"Bite 1: a mesh Origin is accepted from a mesh peer: {origin}",
              OC.origin_ok(FakeHandler(headers={"Origin": origin},
                                       client_address=MESH_PEER), served) is True)
    for origin in accepted:
        check(f"Bite 1: ... and from this PC (a loopback peer): {origin}",
              OC.origin_ok(FakeHandler(headers={"Origin": origin},
                                       client_address=("127.0.0.1", 5000)),
                           served) is True)
    refused = ("https://evil.com",
               "http://mariorelan11-alps.nord:9999",       # not a served port
               "http://mariorelan11-alps.nord.evil.com:4719",   # lookalike suffix
               "http://notnord:4719",                      # no mesh suffix
               "ftp://mariorelan11-alps.nord:4719",        # not a page scheme
               "http://foo@mariorelan11-alps.nord:4719",   # userinfo in an Origin
               "null")
    for origin in refused:
        check(f"Bite 1: ... and refused from a mesh peer: {origin}",
              OC.origin_ok(FakeHandler(headers={"Origin": origin},
                                       client_address=MESH_PEER), served) is False)
    for origin in accepted:
        check(f"Bite 1: a PUBLIC peer gains nothing from this rule: {origin}",
              OC.origin_ok(FakeHandler(headers={"Origin": origin},
                                       client_address=PUBLIC_PEER), served) is False)
    for peer in (("", 1), ("not an address", 1)):
        check(f"Bite 1: a peer that cannot be placed fails closed ({peer[0]!r})",
              OC.origin_ok(FakeHandler(headers={
                  "Origin": "http://mariorelan11-alps.nord:4719"},
                  client_address=peer), served) is False)
    # The two rules that did NOT change with this slice.
    check("Bite 1: a configured Origin is still accepted, whatever the peer",
          OC.origin_ok(FakeHandler(headers={"Origin": "http://127.0.0.1:4719"},
                                   client_address=PUBLIC_PEER), served) is True)
    check("Bite 1: a third-party Origin is still refused from this PC",
          OC.origin_ok(FakeHandler(headers={"Origin": "http://evil.example"}),
                       served) is False)


def t_bite2_the_event_stream_from_a_browser_on_the_mesh():
    """Bite 2's other half: a browser's EventSource cannot set a header, and
    a same-origin subscription is sent with NO Origin. The no-Origin fallback
    used to demand X-Jarvis-Client: hud, and the HUD's own
    `_same_origin_stream` exemption only believed a loopback peer - so a
    browser on the iPad or a second PC was refused 403 on /api/events and the
    HUD stayed "stale", which holds Approve for ever. The stream itself, from
    this PC or the mesh, asking for text/event-stream, is accepted; every
    other route keeps the real Origin check."""
    def stream(peer=MESH_PEER, path="/api/events", accept="text/event-stream"):
        headers = {"Accept": accept} if accept is not None else {}
        return OC.origin_ok(FakeHandler(headers=headers, client_address=peer,
                                        path=path), set())

    for peer in (MESH_PEER, ("127.0.0.1", 5000)):
        check(f"Bite 2: a no-Origin /api/events from {peer[0]} is accepted",
              stream(peer=peer) is True)
    check("Bite 2: ... with ?since= on the path", stream(path="/api/events?since=12") is True)
    check("Bite 2: ... but never from a public peer", stream(peer=PUBLIC_PEER) is False)
    check("Bite 2: ... not for another route", stream(path="/api/status") is False)
    check("Bite 2: ... and not without the event-stream Accept header",
          stream(accept=None) is False)
    check("Bite 2: an outside Origin is still refused on the stream",
          OC.origin_ok(FakeHandler(headers={
              "Origin": "https://evil.example",
              "Accept": "text/event-stream"}, client_address=MESH_PEER,
              path="/api/events"), set()) is False)
    check("Bite 2: a peer that cannot be placed fails closed on the stream",
          stream(peer=("", 1)) is False)
    check("Bite 2: the HUD's own X-Jarvis-Client: hud fallback still works",
          OC.origin_ok(FakeHandler(headers={"X-Jarvis-Client": "hud"},
                                   client_address=MESH_PEER), set()) is True)


def t_the_hud_patch_wires_it_to_this_module():
    check("the delegation patch ships", PATCH.is_file(), PATCH)
    text = PATCH.read_text(encoding="utf-8") if PATCH.is_file() else ""
    check("... calls jarvis_owner_check.origin_ok",
          "jarvis_owner_check.origin_ok" in text)
    check("... calls jarvis_owner_check.token_ok",
          "jarvis_owner_check.token_ok" in text)
    check("... leaves the configuration read in the HUD",
          "_served_origins()" in text)
    ps1 = PS1.read_text(encoding="utf-8")
    start = ps1.index("$PATCHES = @(")
    names = [line.strip().strip("'") for line in
             ps1[start:ps1.index("\n)", start)].splitlines()
             if line.strip().startswith("'")]
    check("apply-patches.ps1 applies it, before plugin-loader.patch (which must "
          "stay last)",
          "hud-origin-module.patch" in names
          and names.index("hud-origin-module.patch")
          < names.index("plugin-loader.patch"))


if __name__ == "__main__":
    for fn in (t_origin_ok_is_the_decision_the_hud_makes,
               t_token_ok_is_the_decision_the_hud_makes,
               t_bite1_mesh_origins_are_accepted_from_the_owners_network,
               t_bite2_the_event_stream_from_a_browser_on_the_mesh,
               t_the_hud_patch_wires_it_to_this_module):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
