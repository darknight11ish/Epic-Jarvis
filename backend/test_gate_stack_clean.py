"""The patches that only ADD lines to jarvis_gate.py apply one after another.

WHY

phone-notifications.patch put its line between "restore_backup" and "})"
in the gate's "acts only on tier ask" set, and chatbot.patch - applied
later - still expected those two lines side by side. `git apply` (what
scripts/apply-patches.ps1 runs, with no fuzz) refuses such a hunk, so on
the owner's PC chatbot.patch would have failed, and forget-range.patch,
built on chatbot's line, with it. Nothing noticed: backend/_stack.py
quietly "materialises" a hunk whose context is missing, because missing
context is normally the owner's own original text.

These patches' gate hunks sit only on lines earlier patches wrote, never on
the owner's original lines, so for them a materialised hunk is always a
clash. This checks that none is.

Standard library and git only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _stack  # noqa: E402

# Each of these adds its gate lines right after an earlier patch's lines.
ON_EARLIER_LINES = (
    "phone-notifications.patch",
    "chatbot.patch",
    "forget-range.patch",
    "devices.patch",
    "apps-in-projects.patch",
    "screen-picture.patch",
    "form-review.patch",
    "web-search-switch.patch",
)

failures = 0


def check(ok, what):
    global failures
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        failures += 1


text, log = _stack.stand_in("jarvis_gate.py")
check(text is not None, "the whole stack builds a stand-in jarvis_gate.py")
order = _stack.order()
for name in ON_EARLIER_LINES:
    check(name in order, f"{name} is in apply-patches.ps1's list")
    bad = [line for line in log if line.startswith(name + ":")]
    check(not bad, f"{name} applies to what the patches before it wrote"
          + (f" - {bad}" if bad else ""))

if text is not None:
    start = text.find('"restore_backup",  # jarvis_backup.py')
    end = text.find("})", start)
    block = text[start:end]
    for entry in ('"phone_notifications_read"', '"chatbot_session"', '"memory_forget_range"',
                  '"app_merge_change"', '"browser_form_submit"'):
        check(block.count(entry) == 1, f"{entry} is in the tier-ask set exactly once")

print()
print("FAILED" if failures else "all passed", f"({failures} failure(s))")
sys.exit(1 if failures else 0)
