"""The four keyless integrations (calendar, email, notes, home), wired into
jarvis_agent.py's TOOLS dict as five tools (home split into home_read and
home_control because reading and acting are different tiers).

This is the seam most likely to hold a real bug even though each module's
own plan()/describe()/run() is separately proven in test_calendar.py,
test_email.py, test_notes.py, and test_home_control.py: a wrong argument
name in a `_prepare_*`/`_run_*` pair, or a `gate_lookup_name` string that
does not match what backend/README.md documents, would pass every one of
those tests and still fail the instant a real model tries to call the tool.

    python3 test_integrations_wiring.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _where import BACKEND, REPO  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_agent as AG

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


EXPECTED_GATE_NAMES = {
    "calendar_read": "jarvis_calendar_read_run",
    "email_check": "jarvis_email_read_run",
    "notes_search": "jarvis_notes_search_run",
    "home_read": "jarvis_home_read_run",
    "home_control": "jarvis_home_control_run",
}

for name, gate_name in EXPECTED_GATE_NAMES.items():
    check(f'"{name}" is registered in TOOLS', name in AG.TOOLS)
    if name not in AG.TOOLS:
        continue
    tool = AG.TOOLS[name]
    check(f'"{name}".schema() names itself correctly',
          tool.schema()["function"]["name"] == name)
    check(f'"{name}" resolves to the documented gate action',
          tool.gate_lookup_name({}) == gate_name,
          f"got {tool.gate_lookup_name({})!r}")

# ── none of the five requires an announce callback - each is one request,
#    not a multi-step plan like control_computer/control_phone/browser_control ──
for name in EXPECTED_GATE_NAMES:
    check(f'"{name}" does not need a step-by-step announce callback',
          AG.TOOLS[name].needs_announce is False)

# ── prepare()/execute() actually dispatch to the right module, with the
#    right arguments, and fail honestly (not with a raised exception) when
#    nothing is configured - proven by NOT setting any of the integrations'
#    env vars for this whole file. ─────────────────────────────────────────

CASES = [
    ("calendar_read", {"days_ahead": 3}, "calendar"),
    ("email_check", {"limit": 5, "unread_only": False}, "mail server"),
    ("notes_search", {"query": "budget", "limit": 5}, "notes app configured"),
    ("home_read", {"entity_ids": ["light.kitchen"]}, "Home Assistant"),
    ("home_control", {"domain": "light", "service": "turn_on",
                       "entity_id": "light.kitchen", "data": {"brightness": 120}},
     "Home Assistant"),
]

for name, args, expect_fragment in CASES:
    tool = AG.TOOLS[name]
    try:
        plan_obj, description = tool.prepare(args)
    except Exception as exc:
        check(f'"{name}".prepare() does not raise with nothing configured', False,
              f"{type(exc).__name__}: {exc}")
        continue
    check(f'"{name}".prepare() does not raise with nothing configured', True)
    check(f'"{name}".prepare() still returns a description string',
          isinstance(description, str) and len(description) > 0)
    check(f'"{name}" describe() explains why nothing would be sent',
          expect_fragment in description)

    try:
        result = tool.execute(args, plan_obj)
    except Exception as exc:
        check(f'"{name}".execute() does not raise with nothing configured', False,
              f"{type(exc).__name__}: {exc}")
        continue
    check(f'"{name}".execute() does not raise with nothing configured', True)
    check(f'"{name}".execute() reports failure honestly, not a silent no-op',
          result.get("ok") is False)

# ── home_control's schema requires the fields the module needs to act ────

home_control_schema = AG.TOOLS["home_control"].parameters
check("home_control's schema requires domain, service, and entity_id",
      set(home_control_schema.get("required", [])) == {"domain", "service", "entity_id"})

print()
if FAILED:
    print(f"{len(FAILED)} failed: {', '.join(FAILED)}")
    sys.exit(1)
print(f"{len(PASSED)} passed - calendar_read, email_check, notes_search, home_read, "
      "and home_control are wired, named, and fail honestly with nothing configured")
