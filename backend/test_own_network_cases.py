"""The "own networks only" table both apps' server-address checks read is current.

    python3 test_own_network_cases.py

The owner decided on 2026-09-26 (CLAUDE.md) that both apps accept a Jarvis
server address on the owner's own networks only. Neither app has a rule of
its own: both follow this folder's `jarvis_local_http._own_network`, the
rule plain http:// to Home Assistant and the calendar already uses, through
a table of cases tools/gen_own_network_cases.py makes by running it:

    jarvis-desktop/tests/fixtures/own-network-cases.json
    jarvis-client/app/src/test/resources/contract/own-network-cases.json

WHAT THIS PINS
  1. Both copies are exactly what the generator makes today - so a change to
     the backend's rule that nobody carried to the apps fails here, in CI,
     instead of the apps quietly judging by the old one.
  2. The cases the rule exists for are in the table with the right verdict:
     the public tunnels, the addresses just outside each private range,
     0.0.0.0, and the names dressed up as own ones.
  3. The sentence the apps show is one sentence (the desktop's link line
     shows only the first), names what IS allowed, and leaves the address
     out cleanly when it cannot be repeated back.

Runs anywhere: standard library only, no owner's files, nothing opened.
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_both_copies_are_current():
    import gen_own_network_cases as G
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8").replace("\r\n", "\n") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_own_network_cases.py)",
              have == doc)


def t_the_cases_the_rule_exists_for():
    import gen_own_network_cases as G
    table = G.build()
    host = {c["host"]: c["own"] for c in table["hosts"]}
    origin = {c["url"]: c["own"] for c in table["origins"]}
    for h in ("100.63.255.255", "100.128.0.0", "172.15.255.255", "172.32.0.0", "0.0.0.0",
              "localhost.evil.com", "10.0.0.1.nip.io", "abc123.ngrok-free.app",
              "my-jarvis.trycloudflare.com", "169.254.1.1", "fe80::1", "8.8.8.8"):
        check(f"{h} is refused", host.get(h) is False, host.get(h))
    for h in ("localhost", "127.0.0.1", "::1", "10.0.0.1", "172.16.0.1", "192.168.1.20",
              "100.64.0.0", "100.127.255.255", "homeassistant.local",
              "desktop.tail1234.ts.net", "marioirelan11-alps.nord"):
        check(f"{h} is allowed", host.get(h) is True, host.get(h))
    check("https:// to a public tunnel is refused too - it is about where the key goes",
          origin.get("https://abc123.ngrok-free.app") is False)
    check("every tricky user-name form the backend reads is refused",
          all(not c["own"] for c in table["tricky"] if "@" in c["url"]))


def t_the_sentence():
    import gen_own_network_cases as G
    said = G.MESSAGE.replace("{address}", "https://abc123.ngrok-free.app")
    # The desktop's linkWords splits a reason at ". " (or "! ", "? ").
    check("one sentence", not any(f"{p} " in said for p in ".!?"), said)
    for allowed in ("this PC", "home network", ".local", "Tailscale", ".ts.net",
                    "NordVPN Meshnet", ".nord"):
        check(f"it names what is allowed: {allowed}", allowed in said)
    check("the unshown form leaves the address out cleanly",
          G.MESSAGE_UNSHOWN.startswith("Jarvis's address is not on your own networks"),
          G.MESSAGE_UNSHOWN)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)
