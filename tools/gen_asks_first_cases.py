#!/usr/bin/env python3
"""Writes "What asks first"'s contract file for both apps, and checks it.

    python3 tools/gen_asks_first_cases.py            # write both copies
    python3 tools/gen_asks_first_cases.py --check    # compare only

What GET /api/asks_first really answers (backend/jarvis_asks_first.py), in
named situations, made by the real code - nothing is written by hand - and
the words both apps show next to it:

    jarvis-desktop/tests/fixtures/asks-first-cases.json
    jarvis-client/app/src/test/resources/contract/asks-first-cases.json

(byte-identical). Both apps build against it: the desktop's Rust and
JavaScript tests (tests/asks-first.mjs), and the phone's AsksFirstTest.

Every tier is a fake made here, so the file is the same on every machine.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-asks-first-cases-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP)
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_asks_first as AF  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "asks-first-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "asks-first-cases.json")
COPIES = (DESKTOP, PHONE)

#: The shipped tiers (backend/rebuilt/jarvis-framework.toml), for the cases.
SHIPPED = {
    "web_research": "auto", "read_calendar": "auto", "calendar_read": "auto",
    "email_read": "auto", "notes_search": "auto", "home_read": "auto", "home_control": "ask",
    "read_files_readonly": "auto", "draft_email": "ask", "send_email": "ask",
    "edit_calendar_event": "ask", "delete_calendar_event": "ask", "delete_file": "ask",
    "run_shell_on_host": "ask", "spend_money": "ask", "control_computer": "ask",
    "change_own_config": "ask", "loosen_what_asks_first": "ask", "modify_own_code": "ask",
    "post_to_external_service": "never", "open_public_tunnel": "never",
    "read_joplin_note": "auto", "create_joplin_note": "notify", "edit_joplin_note": "ask",
    "delete_joplin_note": "never", "read_logseq_page": "auto", "append_logseq_journal": "auto",
    "create_logseq_page": "auto", "edit_logseq_page": "ask", "delete_logseq_page": "never",
    "append_obsidian_daily": "auto", "write_notes_after_outside_text": "ask",
    "browse_model_catalog": "auto", "download_model": "ask", "switch_model": "ask",
    "rollback_model": "auto", "models_create": "ask", "schedule_repeat": "ask",
    "search_the_web": "ask", "stop_asking_before_every_web_search": "ask",
    "power_manage": "auto", "second_card_enable": "ask", "second_card_browser_enable": "ask",
    "wiki_update": "ask", "big_model_enable": "ask", "learning_enable": "ask",
    "history_enable": "ask", "learning_auto_enable": "ask", "learning_sensitive_enable": "ask",
    "custom_voice": "ask", "better_voice_enable": "ask", "enable_reading_tool": "ask",
}


def _with(tiers: dict, *, lights=False, lights_waiting=False, loosen_waiting=None,
          search_every=False, tools_enabled=(), tool_waiting=None):
    AF._reset_for_tests()
    AF._tier = lambda a: tiers.get(a, "ask")
    AF._search_asks_every_time = lambda: search_every
    AF._file_tiers = lambda: dict(tiers)
    AF._config_dir = lambda: _TMP
    AF.tools_enabled_set = lambda: set(tools_enabled)
    f = _TMP / "asks_first.json"
    if lights:
        f.write_text(json.dumps({"lights": True, "changed": 0}), encoding="utf-8")
    elif f.exists():
        f.unlink()
    if lights_waiting:
        AF._LS_STATE["pending"].update(id="l1", since=0)
    if loosen_waiting:
        AF._L_STATE["pending"].update(id="p1", action=loosen_waiting, since=0)
    if tool_waiting:
        AF._T_STATE["pending"].update(id="t1", tool=tool_waiting, since=0)


def cases() -> dict:
    out = {}
    _with(SHIPPED)
    out["pc_shipped"] = AF.view(here=True)
    out["phone_shipped"] = AF.view(here=False)
    stricter = dict(SHIPPED, calendar_read="ask", create_joplin_note="ask",
                    email_read="never", send_email="auto")
    _with(stricter, lights=True, search_every=True, tools_enabled=["calendar_read"])
    out["pc_stricter_lights_on"] = AF.view(here=True)
    _with(stricter, lights_waiting=True, loosen_waiting="calendar_read",
          tool_waiting="email_read")
    out["phone_cards_waiting"] = AF.view(here=False)
    AF._reset_for_tests()
    return {
        "cases": out,
        "switchable": list(AF.SWITCHABLE),
        "loose": dict(AF.LOOSE),
        "tools_switchable": list(AF.TOOLS_SWITCHABLE),
        "words": {
            "title": AF.TITLE, "detail": AF.DETAIL, "missing": AF.MISSING,
            "switch_label": AF.SWITCH_LABEL, "phone_loosen": AF.PHONE_LOOSEN,
            "waiting": AF.WAITING, "pc_only": AF.PC_ONLY, "not_on_list": AF.NOT_ON_LIST,
            "lights_label": AF.LIGHTS_LABEL, "lights_detail": AF.LIGHTS_DETAIL,
            "lights_waiting": AF.LIGHTS_WAITING, "says": dict(AF.SAYS),
            "says_search": AF.SAYS_SEARCH,
            "tools_label": AF.TOOLS_LABEL, "tools_detail": AF.TOOLS_DETAIL,
            "tools_pc_only": AF.TOOLS_PC_ONLY, "tools_not_on_list": AF.TOOLS_NOT_ON_LIST,
        },
    }


def render() -> str:
    return json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(str(path.relative_to(ROOT)))
        if stale:
            print("out of date (run python3 tools/gen_asks_first_cases.py): " + ", ".join(stale))
            return 1
        print("asks-first-cases.json: both copies up to date")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
