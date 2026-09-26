#!/usr/bin/env python3
"""Writes the "own networks only" table for both apps' server address, and checks it.

    python3 tools/gen_own_network_cases.py            # write both copies
    python3 tools/gen_own_network_cases.py --check    # compare only

The owner decided on 2026-09-26 (CLAUDE.md, "Decided 2026-09-26") that both
apps accept a Jarvis server address on the owner's own networks only: this
PC, the home network, Tailscale and NordVPN Meshnet. Anything on the open
internet - a public tunnel such as ngrok or Cloudflare included - is refused,
so the pairing key never travels there. https:// is refused too: this is
about WHERE the key goes, not whether the line is scrambled.

"Own networks" is not a second rule. It is the backend's, word for word:
backend/jarvis_local_http.py, the one `plain_http_problem` already uses for
plain http:// to Home Assistant and the calendar. Every verdict below is
made by that real code - nothing is judged by hand here - and written into

    jarvis-desktop/tests/fixtures/own-network-cases.json
    jarvis-client/app/src/test/resources/contract/own-network-cases.json

(byte-identical). The desktop's Rust tests (commands.rs, own_network_tests)
and tests/own-network.mjs, and the phone's OwnNetworkTest, read it; the
backend's test_own_network_cases.py fails when it is stale.

Three lists:

  hosts    a bare host name or address, judged by `_own_network` itself.
           Both apps' host check must give the same answer for every one.
  origins  a whole address the way the owner types it (scheme, host, port).
           Judged the way `plain_http_problem` judges an http:// address,
           whatever the scheme. Both apps must agree exactly, and a refused
           one must get exactly `message`, with {address} filled in.
  tricky   odd shapes (a user name in the address, a backslash, a path, an
           unbracketed IPv6 address...). The backend's verdict is given; an
           app must refuse every one the backend refuses, and MAY refuse
           more, because each app also checks the address's shape.

The wording (`message`, and the phone's `phone_message`, which names only
the private-network names the phone can connect to) lives here, in one
place, for both apps. It is one
sentence on purpose: the desktop's link line shows only the first sentence
of a reason ("Offline - <sentence>"), and the phone shows it as it is.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_local_http as L  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "own-network-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "own-network-cases.json")
COPIES = (DESKTOP, PHONE)

#: What both apps say when an address is refused. {address} is the address
#: as the owner typed it (trimmed, without a trailing "/"). When it holds
#: something that must not be repeated back - a user name or password written
#: into it ("me:pw@..."), or a space - the apps say MESSAGE_UNSHOWN instead:
#: the same sentence without the address.
MESSAGE = ("Jarvis's address {address} is not on your own networks, so this app will not "
           "send your pairing key there: use this PC (localhost), your home network (an "
           "address like 192.168.x.x or 10.x.x.x, or a name ending in .local), Tailscale "
           "(a name ending in .ts.net) or NordVPN Meshnet (a name ending in .nord).")
MESSAGE_UNSHOWN = MESSAGE.replace("{address} ", "")

#: The phone's own ending (ease-of-use audit 2026-09-27, #1e). The phone
#: judges the address by the same rule, but it can only CONNECT in plain
#: http:// to a name ending in .ts.net or .nord (and to itself):
#: jarvis-client/app/src/main/res/xml/network_security_config.xml allows no
#: other cleartext host, and a network security config cannot list an
#: address range. So the phone's sentence names only what it can reach -
#: suggesting 192.168.x.x or a .local name there would send the owner to an
#: address that fails. The first half is MESSAGE's, word for word.
PHONE_MESSAGE = ("Jarvis's address {address} is not on your own networks, so this app will not "
                 "send your pairing key there: on this phone, use your PC's Tailscale name "
                 "(ending in .ts.net) or its NordVPN Meshnet name (ending in .nord).")
PHONE_MESSAGE_UNSHOWN = PHONE_MESSAGE.replace("{address} ", "")

HOSTS = [
    # this PC
    "localhost", "LOCALHOST", "localhost.", "127.0.0.1", "127.255.255.254", "::1",
    # the home network
    "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.255", "192.168.1.20",
    "fc00::1", "fdff::1", "homeassistant.local", "desk.lan", "nas.home.arpa",
    "nas", "jarvis-pc", "my_pc", "local",
    # Tailscale and NordVPN Meshnet
    "100.64.0.0", "100.101.102.103", "100.127.255.255", "fd7a:115c:a1e0::1",
    "desktop.tail1234.ts.net", "DESKTOP.TAIL1234.TS.NET", "desktop.tail1234.ts.net.",
    "marioirelan11-alps.nord",
    # numbers written the old way, judged as the address the OS would dial
    "3232235777", "0xc0a80101", "10.1", "0x7f.1", "::ffff:192.168.1.1",
    # just outside a range
    "100.63.255.255", "100.128.0.0", "172.15.255.255", "172.32.0.0", "11.0.0.1",
    "192.169.0.1", "126.255.255.255",
    # never own
    "", "0.0.0.0", "0", "::", "169.254.1.1", "fe80::1", "8.8.8.8", "1.1.1.1",
    "2001:db8::1", "::ffff:8.8.8.8", "134744072", "010.0.0.1", "0x08080808",
    # names on the open internet, and names dressed up as own ones
    "evil.com", "localhost.evil.com", "10.0.0.1.nip.io", "abc123.ngrok-free.app",
    "my-jarvis.trycloudflare.com", "ts.net", "evilts.net", "desktop.ts.net.evil.com",
    "a.nord.evil.com", "local.evil.com", "my.duckdns.org", "ha.example.com",
    "evil..local", ".local", "evil.com@127.0.0.1",
]

ORIGINS = [
    "http://127.0.0.1:4719", "http://localhost:4719", "http://LOCALHOST:4719",
    "http://[::1]:4719", "http://192.168.1.20:4719", "https://192.168.1.20:4719",
    "http://10.0.0.5", "http://172.16.0.1:4719", "http://homeassistant.local:4719",
    "http://jarvis-pc:4719", "http://100.64.12.3:4719", "http://100.127.255.255:4719",
    "http://[fd7a:115c:a1e0::1]:4719", "http://[FD7A:115C:A1E0::1]:4719",
    "https://desktop.tail1234.ts.net", "http://desktop.tail1234.ts.net.:4719",
    "http://marioirelan11-alps.nord:4719", "http://3232235777:4719", "http://0x7f.1:4719",
    # refused
    "http://0.0.0.0:4719", "http://0:4719", "http://100.63.255.255:4719",
    "http://100.128.0.0:4719", "http://172.15.0.1:4719", "http://172.32.0.1:4719",
    "http://169.254.10.20:4719", "http://[fe80::1]:4719", "http://8.8.8.8:4719",
    "https://8.8.8.8", "http://[2001:db8::1]:4719", "http://[::ffff:8.8.8.8]:4719",
    "http://134744072:4719", "http://010.0.0.1:4719", "https://abc123.ngrok-free.app",
    "https://my-jarvis.trycloudflare.com", "http://localhost.evil.com:4719",
    "http://10.0.0.1.nip.io:4719", "https://jarvis.example.com", "https://EVIL.COM",
    "https://desktop.tail1234.ts.net.evil.com", "http://evilts.net:4719",
]

TRICKY = [
    ("http://127.0.0.1@evil.com:4719", "a user name that looks like this PC"),
    ("http://evil.com@127.0.0.1:4719", "a user name that looks like a public name"),
    ("http://user:pw@127.0.0.1:4719", "a user name and password"),
    ("http://127.0.0.1:4719@evil.com", "a port that is really a user name"),
    ("http://evil.com\\@127.0.0.1:4719", "a backslash, which some readers take as a slash"),
    ("http://evil.com#@127.0.0.1", "a fragment hiding the real host"),
    ("http://evil.com?@127.0.0.1", "a query hiding the real host"),
    ("http://%6c%6fcalhost:4719", "a host spelt in %-escapes"),
    ("http://fe80::1:8123", "an IPv6 address without its brackets"),
    ("http://:4719", "no host at all"),
    ("http://127.0.0.1/jarvis", "a path after an own address"),
    ("http://127.0.0.1.:4719", "a trailing dot on an address"),
    ("http://localhost:99999", "a port that does not exist"),
]


def backend_own(url: str) -> bool:
    """The backend's verdict on `url`, whatever its scheme: would
    `plain_http_problem` let plain http:// go there?"""
    rest = url.split("://", 1)[1] if "://" in url else url
    return L.plain_http_problem("http://" + rest, "JARVIS_BASE", "the pairing key") == ""


def build() -> dict:
    return {
        "_comment": ("Generated by tools/gen_own_network_cases.py from "
                     "backend/jarvis_local_http.py (_own_network, plain_http_problem). "
                     "Do not edit by hand."),
        "message": MESSAGE,
        "message_unshown": MESSAGE_UNSHOWN,
        "phone_message": PHONE_MESSAGE,
        "phone_message_unshown": PHONE_MESSAGE_UNSHOWN,
        "hosts": [{"host": h, "own": L._own_network(h)} for h in HOSTS],
        "origins": [{"url": u, "own": backend_own(u)} for u in ORIGINS],
        "tricky": [{"url": u, "own": backend_own(u), "why": why} for u, why in TRICKY],
    }


def document() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main(argv) -> int:
    doc = document()
    if "--check" in argv:
        bad = [p for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8").replace("\r\n", "\n") != doc]
        for p in bad:
            print(f"STALE {p.relative_to(ROOT)} - run python3 tools/gen_own_network_cases.py")
        if not bad:
            print("own-network-cases.json: both copies up to date")
        return 1 if bad else 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
