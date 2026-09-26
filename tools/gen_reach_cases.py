#!/usr/bin/env python3
"""Writes "What Jarvis can reach"'s contract file for both apps, and checks it.

    python3 tools/gen_reach_cases.py            # write both copies
    python3 tools/gen_reach_cases.py --check    # compare only

What GET /api/reach really answers (backend/jarvis_reach.py), in named
situations, made by the real code - nothing is written by hand:

    jarvis-desktop/tests/fixtures/reach-cases.json
    jarvis-client/app/src/test/resources/contract/reach-cases.json

(byte-identical). Both apps build against it: the desktop's Rust and
JavaScript tests, and the phone's ReachTest.

Every setting is a fake made here (environment variables, tiers, the web
search settings, the switch files), so the file is the same on every
machine. The fake secrets are built by concatenation, and render() refuses
to write a file that holds any of them.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_TMP = tempfile.mkdtemp(prefix="jarvis-reach-cases-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_reach as R  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "reach-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "reach-cases.json")
COPIES = (DESKTOP, PHONE)

# Fake secrets, built by concatenation; none may appear in the output.
FAKE_PASSWORD = "hunter" + "2-" + "fake-mail-pw"
FAKE_ICS = ("https://calendar.google.com/calendar/ical/me%40example.com/private-"
            + "0123abcd" + "4567ef89" + "0123abcd" + "4567ef89" + "/basic.ics")
FAKE_TOPIC = "jarvis-" + "topic-" + "q8w7e6r5"
FAKE_HOME = "eyJ" + "hbGciOi" + "fakehometoken0123"
FAKE_GITHUB = "gh" + "p_" + "fake" + "0123456789abcdef0123456789abcd"
FAKE_JOPLIN = "jop" + "lin" + "fake0123456789"
SECRETS = (FAKE_PASSWORD, FAKE_ICS, "private-0123abcd", FAKE_TOPIC, FAKE_HOME, FAKE_GITHUB,
           FAKE_JOPLIN)

_ENV_NAMES = ("JARVIS_IMAP_HOST", "JARVIS_IMAP_USER", "JARVIS_IMAP_PASSWORD",
              "JARVIS_CALDAV_URL", "JARVIS_CALDAV_USER", "JARVIS_CALDAV_PASSWORD",
              "JARVIS_CALENDAR_ICS_SECRET_URL", "JARVIS_HOME_URL", "JARVIS_HOME_TOKEN",
              "JARVIS_NTFY_TOPIC", "JARVIS_NTFY_SERVER", "JARVIS_GITHUB_TOKEN",
              "JARVIS_JOPLIN_TOKEN", "JOPLIN_TOKEN", "JARVIS_JOPLIN_URL",
              "JARVIS_OBSIDIAN_API_KEY", "JARVIS_OBSIDIAN_URL", "JARVIS_OBSIDIAN_VAULT",
              "JARVIS_NOTES_BACKEND")


def _set_env(values: dict) -> None:
    for n in _ENV_NAMES:
        os.environ.pop(n, None)
    os.environ.update(values)


EVERYDAY_ENV = {
    "JARVIS_IMAP_HOST": "imap.example.com", "JARVIS_IMAP_USER": "me@example.com",
    "JARVIS_IMAP_PASSWORD": FAKE_PASSWORD,
    "JARVIS_CALENDAR_ICS_SECRET_URL": FAKE_ICS,
    "JARVIS_NTFY_TOPIC": FAKE_TOPIC,
}
ALL_ENV = dict(EVERYDAY_ENV, **{
    "JARVIS_HOME_URL": "http://homeassistant.local:8123/api", "JARVIS_HOME_TOKEN": FAKE_HOME,
    "JARVIS_GITHUB_TOKEN": FAKE_GITHUB, "JARVIS_JOPLIN_TOKEN": FAKE_JOPLIN,
    "JARVIS_NTFY_SERVER": "https://ntfy.example.net",
})
TIERS_SHIPPED = {"calendar_read": "auto", "email_read": "auto", "notes_search": "auto",
                 "home_read": "auto", "home_control": "ask", "web_research": "ask",
                 "research_authenticated": "ask", "append_obsidian_daily": "auto",
                 "append_logseq_journal": "auto", "create_joplin_note": "notify",
                 "control_computer": "ask", "control_phone": "ask", "control_browser": "ask",
                 "run_shell_on_host": "ask", "read_files_readonly": "auto"}
SEARXNG = {"provider": "searxng", "searxng_url": "http://127.0.0.1:8888",
           "ask_every_time": False, "why": ""}
OFF = {"master": False, "features": {}}


NO_PLUGINS = {"servers": [], "running": [], "problem": "", "card_every_start": False}


def _ctx(enabled, *, tiers=None, search=None, keys=None, lanes=None, providers=None,
         second=None, big=None, plugins=None) -> R.Ctx:
    tiers = dict(TIERS_SHIPPED, **(tiers or {}))
    return R.Ctx(enabled=set(enabled), tier=lambda a: tiers.get(a, "ask"),
                 env=lambda n: str(os.environ.get(n, "") or "").strip(),
                 lanes=list(lanes or []), providers=list(providers or []),
                 search=dict(search or SEARXNG),
                 key_saved=lambda p: (keys or {}).get(p, False),
                 second_card=second or OFF, big_model=big or {"master": False},
                 gate_action=lambda lookup: None, plugins=plugins or NO_PLUGINS)


def cases() -> dict:
    out = {}
    _set_env({})
    out["nothing_set_up"] = R.view(_ctx(set()))
    _set_env(EVERYDAY_ENV)
    out["everyday"] = R.view(_ctx({"calculator", "memory_search", "web_search", "email_check",
                                   "calendar_read", "append_obsidian_daily",
                                   "control_computer"}))
    _set_env(ALL_ENV)
    everything = set(R.TOOL_NAMES)
    out["everything_on"] = R.view(_ctx(
        everything, search={"provider": "tavily", "searxng_url": "http://127.0.0.1:8888",
                            "ask_every_time": True, "why": ""},
        keys={"tavily": True}, lanes=["jarvis-escalate"], providers=["openrouter"],
        second={"master": True, "features": {"long_context": True, "browser_control": True,
                                             "vision": True}},
        big={"master": True, "wiki": True, "deep_questions": False},
        plugins={"servers": ["repo"], "running": ["repo"], "problem": "",
                 "card_every_start": False}))
    _set_env(EVERYDAY_ENV)
    out["blocked_and_no_key"] = R.view(_ctx(
        {"web_search", "email_check", "browser_control"}, tiers={"email_read": "never"},
        search={"provider": "exa", "searxng_url": "http://127.0.0.1:8888",
                "ask_every_time": False, "why": ""}, keys={"exa": False}))
    _set_env({})
    out["damaged_search"] = R.view(_ctx({"web_search"}, search={
        "provider": None, "searxng_url": "http://127.0.0.1:8888", "ask_every_time": True,
        "why": "damaged"}))
    _set_env({})
    return {"cases": out, "ids": [k for k, _ in R.KINDS], "title": R.TITLE,
            "detail": R.DETAIL, "missing": R.MISSING, "states": dict(R.STATE_WORDS),
            "tools_title": R.TOOLS_TITLE, "tools_none": R.TOOLS_NONE,
            "everything_else": R.EVERYTHING_ELSE, "where_label": R.WHERE_LABEL,
            "asks_label": R.ASKS_LABEL}


def render() -> str:
    text = json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    for s in SECRETS:
        assert s not in text, "a secret reached the contract file"
    return text


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(str(path.relative_to(ROOT)))
        if stale:
            print("out of date (run python3 tools/gen_reach_cases.py): " + ", ".join(stale))
            return 1
        print("reach-cases.json: both copies up to date")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
