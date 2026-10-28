"""jarvis_antislop.py - the Anti-Slop filter: a cardless output-quality switch.

WHAT THIS IS

`miqdadbadjuber/anti-slop` (MIT, v3.2.23, commit 6732aee) is a rulebook for
keeping agent-written words and interfaces free of the tells that make them
read as machine-made: em dashes everywhere in prose (R-02), generic CTAs such
as "Get Started" (R-15), marketing buzzwords such as "seamless" and
"revolutionary" (R-16), glassmorphism and glow stacked past a dose cap (R-10 /
R-13), unrounded WCAG AA contrast failures (R-25), dead controls (R-26), a
keyboard focus ring removed with nothing put back (R-32), and decorative
comment banners in code (its `antislop-code` skill). The rules are DISTILLED
here, in this module, and vendored: no `npx antislop-ai`, no npm, no network,
no second folder of Markdown to read at run time. THIRD-PARTY-NOTICES.txt
carries the MIT attribution and says exactly what was taken.

WHY IT IS SHAPED THIS WAY, and not as the rulebook's own skill folder

Raw `antislop.md` is 56 KB (about 14,000 tokens). Prepending that to every turn
would blow this project's system-prompt budget and add seconds of prefill on
the local 8-9B model for a filter that is mostly a checklist. So the same rules
arrive in two shapes, and neither one is a model call:

  1. a compact `<antislop_filter mode="...">` system note, at most
     MAX_PROMPT_CHARS (1,050) characters, scoped to the owner's copy/code/ui
     switches and carrying the Liveliness dials. OFF costs exactly 0 tokens.
  2. deterministic Python: an em-dash scrub and a code-comment cleanup applied
     to the words the model already wrote (post_process_reply / ReplyFilter),
     and a pure auditor (audit_text_or_ui) for an existing file or page.

TWO MODES (the rulebook's own)

  during  filter as the words are written: the prompt note plus the scrub.
  after   audit only. The note tells the model to answer with a numbered
          findings list and NOT to edit anything, and the scrub is bypassed -
          an audit's own text is allowed to quote the very em dash it reports.

CARDLESS, BOTH DIRECTIONS, LIKE THE PROMPT COACH

Turning this on opens no network door, reads no folder, takes no action and
loosens no gate: it changes the words Jarvis writes. So both directions are
instant and NEITHER raises an approval card (the owner's own classification -
`docs/DECISIONS.md`, 2026-10-28). Every change does leave ONE action receipt
with a one-click Undo (jarvis_receipts.py, when that module is present), which
is the project's pattern for "this changed something, put it back".

STATE

`antislop.json` in the Jarvis settings folder (`~/.openjarvis` by default, or
`jarvis_framework.CONFIG_DIR` when that module is present), written atomically
under a lock like every other setting file here. Default: OFF, `during` mode,
copy + code + ui scopes, dials ENERGY 1 / RHYTHM 2 / MOTION 1 - the rulebook's
own starting dials in its Liveliness section.

ROUTES (installed by this module's install(), which is what the drop-in folder
plugins/ready/antislop asks jarvis_plugins.py to call - no patch of its own)

  GET  /api/antislop          the state, plus what the filter would say now
  POST /api/antislop          change enabled / mode / scopes / dials / gate
  POST /api/antislop/audit    a read-only `after`-mode audit of supplied text

Standard library only. No network, no child process, no model call.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

#: The file holding the switch, in the Jarvis settings folder.
STATE_NAME = "antislop.json"

#: The receipt's own name, so Undo knows how to put the state back
#: (jarvis_receipts.register_restorer), and so a receipt list reads plainly.
TOOL_NAME = "antislop"

#: Where the rules come from, for the attribution the project requires and for
#: anyone reading a finding who wants the rule in full.
SOURCE = "miqdadbadjuber/anti-slop v3.2.23 (MIT), rules distilled and vendored"

#: The hard ceiling on the prompt block. The blueprint's own number: about 240
#: tokens, and never more than this many characters. A block over it is a bug,
#: not a style choice - `_block` asserts it in the suite and clamps in the
#: field, because a prompt that grows quietly is how a 3,800-token budget dies.
MAX_PROMPT_CHARS = 1050

MODES = ("during", "after")
DEFAULT_MODE = "during"
SCOPES = ("copy", "code", "ui")
DIAL_NAMES = ("energy", "rhythm", "motion")

#: The rulebook's own starting dials (its Liveliness section, Part 3).
DEFAULT_DIALS = {"energy": 1, "rhythm": 2, "motion": 1}

#: The shortest and longest a dial may be. 1..3 is the rulebook's scale.
DIAL_MIN, DIAL_MAX = 1, 3

#: Every state key, in the order a reader of the JSON sees them.
STATE_KEYS = ("enabled", "mode", "scopes", "dials",
              "show_delivery_gate_on_ui_tasks", "updated_at")

# --------------------------------------------------------------------------
#   R-16: forbidden AI marketing buzzwords (Quality Lock, LOW)
# --------------------------------------------------------------------------
#
# Distilled from the rulebook's own list. Matched case-insensitively on word
# boundaries, so "seamlessly" and "seamless" both count while "delved into the
# archive" does not become a finding about "delve" as a substring of a name.
BANNED_AI_BUZZWORDS = (
    "ai-powered", "ai powered", "next-generation", "next generation",
    "revolutionary", "seamless", "seamlessly", "cutting-edge", "cutting edge",
    "revolutionize", "game-changer", "game changer", "effortless", "effortlessly",
    "next level", "supercharge", "unlock the power", "elevate your",
    "delve into", "delve", "tapestry", "testament to", "beacon of",
    "symphony of", "in today's fast-paced", "unleash",
)

#: R-15: generic default calls to action (Quality Lock, LOW). A whole phrase,
#: not a word: "learn more about volcanoes" in an answer is ordinary English,
#: which is why the audit also requires the phrase to look like a control (see
#: `_cta_findings`) before it says anything.
GENERIC_CTAS = (
    "get started", "learn more", "try now", "sign up free", "click here",
    "explore now", "discover more",
)

#: Which tier each rule sits in, taken from the rulebook's own three groups:
#: Hard Gate (HIGH), Purpose-Gate (MEDIUM), Quality Locks (LOW).
RULE_TIER = {
    "R-02": "HIGH",     # em dash in agent-written prose
    "R-10": "MEDIUM",   # glassmorphism past its dose cap
    "R-13": "MEDIUM",   # glow past its dose cap
    "R-15": "LOW",      # generic CTA
    "R-16": "LOW",      # AI buzzword
    "R-25": "HIGH",     # WCAG AA contrast, unrounded
    "R-26": "HIGH",     # dead control
    "R-32": "HIGH",     # focus ring removed, nothing put back
    "antislop-code": "LOW",   # decorative comment banner
}

#: The rulebook's own dose cap for R-10 and R-13: "at most 1-2 elements".
DOSE_CAP = 2

#: WCAG 2.1 AA: 4.5:1 for normal text, 3:1 for large text (>= 18pt, or 14pt
#: bold). Compared UNROUNDED - see `check_contrast` for why that is the whole
#: point of the rule.
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0

EM_DASH = "\u2014"

#: The audit's kinds. "auto" reads the content and decides; the rest only run
#: the checks that can apply, so a plain-text answer is never told it has no
#: focus ring.
KINDS = ("auto", "text", "markdown", "md", "html", "css", "js", "code", "ui")


# --------------------------------------------------------------------------
#   The settings file
# --------------------------------------------------------------------------

_LOCK = threading.Lock()


def _config_dir() -> Path:
    """The Jarvis settings folder, the same one every other module uses:
    jarvis_framework's own answer first, then the environment, then the
    default. Read-only here - this module never creates it except when it
    writes its own file."""
    try:
        import jarvis_framework
        return Path(jarvis_framework.CONFIG_DIR)
    except Exception:
        pass
    for name in ("OPENJARVIS_CONFIG_DIR", "JARVIS_CONFIG_DIR"):
        raw = os.environ.get(name)
        if raw:
            return Path(raw)
    return Path.home() / ".openjarvis"


def state_path() -> Path:
    """antislop.json in the Jarvis settings folder."""
    return _config_dir() / STATE_NAME


def _default_state() -> dict:
    return {"enabled": False, "mode": DEFAULT_MODE,
            "scopes": {name: True for name in SCOPES},
            "dials": dict(DEFAULT_DIALS),
            "show_delivery_gate_on_ui_tasks": True,
            "updated_at": 0.0}


def _clean(doc: object) -> dict:
    """`doc` as a valid state, key by key, each falling back to ITS OWN default.

    A damaged or half-written file must never move the filter somewhere the
    owner never chose - the same rule jarvis_prompt_coach.py states for its own
    four settings. So a value of the wrong type, an unknown mode and a dial
    outside 1..3 each fall back alone; the rest of the file still counts.
    """
    out = _default_state()
    if not isinstance(doc, dict):
        return out
    if isinstance(doc.get("enabled"), bool):
        out["enabled"] = doc["enabled"]
    if doc.get("mode") in MODES:
        out["mode"] = doc["mode"]
    scopes = doc.get("scopes")
    if isinstance(scopes, dict):
        for name in SCOPES:
            if isinstance(scopes.get(name), bool):
                out["scopes"][name] = scopes[name]
    dials = doc.get("dials")
    if isinstance(dials, dict):
        for name in DIAL_NAMES:
            value = dials.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                out["dials"][name] = max(DIAL_MIN, min(DIAL_MAX, value))
    if isinstance(doc.get("show_delivery_gate_on_ui_tasks"), bool):
        out["show_delivery_gate_on_ui_tasks"] = doc["show_delivery_gate_on_ui_tasks"]
    stamp = doc.get("updated_at")
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        out["updated_at"] = float(stamp)
    return out


def _on_disk() -> dict:
    """The file as it is, cleaned. Never raises: a file that cannot be read is
    treated as the defaults, so a bad file is REPAIRED by the next change
    rather than blocking it."""
    try:
        return _clean(json.loads(state_path().read_text(encoding="utf-8")))
    except Exception:
        return _default_state()


def _write(state: dict) -> None:
    """The one writer. Atomic (`.tmp` + os.replace), under a lock, like every
    other setting file here."""
    with _LOCK:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, path)


def get_state() -> dict:
    """The state as it stands: enabled, mode, scopes, dials, gate, updated_at."""
    return _on_disk()


def is_enabled() -> bool:
    """The one question the hot paths ask. Fails to OFF."""
    try:
        return _on_disk().get("enabled") is True
    except Exception:
        return False


def _publish(state: dict) -> None:
    """Tell anything with an event stream open that the switch moved.

    The repo's shape for this is one kind per feature - jarvis_animal.py
    publishes "appearance", jarvis_devices.py "devices", jarvis_coder
    "big-coder" - so this publishes "antislop" with the whole state. (The
    blueprint called it a "settings" event; no such kind exists in this
    backend, and inventing one would have meant a second convention.)
    Never raises: a backend without an event bus still changes the setting."""
    try:
        import jarvis_events
        jarvis_events.BUS.publish("antislop", dict(state))
    except Exception:
        pass


def _register_restorer() -> bool:
    """Say how a change is put back from its before snapshot (after a restart,
    when the in-memory callable is gone). Never raises."""
    try:
        import jarvis_receipts
        return bool(jarvis_receipts.register_restorer(TOOL_NAME, restore_from_before))
    except Exception:
        return False


def restore_from_before(before: object) -> None:
    """Put a whole state document back, exactly. The restorer receipts call.

    Called with the `before` snapshot of one change, so Undo puts back the
    settings that were there rather than a guessed "off". A snapshot that is
    not a dict changes nothing (a receipt with no snapshot is not a licence to
    invent one)."""
    if not isinstance(before, dict):
        return
    state = _clean(before)
    state["updated_at"] = time.time()
    _write(state)
    _publish(state)


def _receipt(before: dict, after: dict, summary: str) -> str:
    """ONE action receipt with a one-click Undo, or "" when the receipts module
    is not on this PC (then the change still happened - see record()'s own
    "never writes anything at all without the project's scrubber")."""
    try:
        import jarvis_receipts
        return jarvis_receipts.record(
            TOOL_NAME, summary, before=before, after=after,
            undo=lambda: restore_from_before(before))
    except Exception:
        return ""


def _change(summary: str, edit: Callable[[dict], None]) -> dict:
    """Read, edit, write, tell, receipt - the shape every setter here shares.

    The receipt is written AFTER the write here (the write is a whole-file
    replace, so a receipt saying "before this" is only true once the file is
    already its new self); `before` is the state as it was read at the top.
    """
    before = _on_disk()
    state = _clean(before)
    edit(state)
    state["updated_at"] = time.time()
    _write(state)
    _publish(state)
    receipt = _receipt(before, state, summary)
    out = dict(state)
    out["ok"] = True
    out["message"] = summary
    out["receipt_id"] = receipt
    return out


def _scope_words(scopes: dict) -> str:
    on = [name for name in SCOPES if scopes.get(name)]
    if not on:
        return "nothing (every scope is off)"
    if len(on) == len(SCOPES):
        return "copy, code comments and UI"
    return " and ".join(on)


def _dials_words(dials: dict) -> str:
    return ", ".join(f"{name.upper()} {dials.get(name, DEFAULT_DIALS[name])}"
                     for name in DIAL_NAMES)


def set_enabled(on: bool) -> dict:
    """Write the master switch. Both directions are instant and NEITHER asks:
    this changes the words Jarvis writes, not what it may reach or do."""
    on = bool(on)
    if on:
        now = _on_disk()
        # The sentence the owner reads back, and the receipt's own summary:
        # turning it ON is only useful if it says what it is now watching.
        mode_words = "During" if now["mode"] == "during" else "After"
        summary = (f"Anti-Slop filter on ({mode_words} mode: "
                   f"{_scope_words(now['scopes'])}; "
                   f"dials {_dials_words(now['dials'])}).")
    else:
        summary = "Anti-Slop filter off."
    return _change(summary, lambda s: s.__setitem__("enabled", on))


def set_mode(mode: str) -> dict:
    """`during` (filter as it writes) or `after` (audit and list findings).
    An unknown mode is refused in words, never guessed at."""
    want = str(mode or "").strip().lower()
    if want not in MODES:
        raise ValueError(f"\"{mode}\" is not a mode; the two are "
                         f"{' and '.join(MODES)}.")
    words = ("during - filter live" if want == "during"
             else "after - audit and list findings first")
    return _change(f"Anti-Slop mode set to {words}.",
                   lambda s: s.__setitem__("mode", want))


def set_scope(scope: str, on: bool) -> dict:
    """Turn one of copy / code / ui on or off inside the filter."""
    name = str(scope or "").strip().lower()
    if name not in SCOPES:
        raise ValueError(f"\"{scope}\" is not a scope; the three are "
                         f"{', '.join(SCOPES)}.")
    on = bool(on)
    state = _change(f"Anti-Slop {'on' if on else 'off'} for {name}.",
                    lambda s: s["scopes"].__setitem__(name, on))
    return state


def set_dials(energy: Optional[int] = None, rhythm: Optional[int] = None,
              motion: Optional[int] = None) -> dict:
    """Set the three Liveliness dials (1..3). A dial left out keeps its value;
    one outside 1..3 is refused rather than clamped, because a silent clamp
    reads back as "your setting moved" when it did not."""
    wanted = {"energy": energy, "rhythm": rhythm, "motion": motion}
    now = _on_disk()["dials"]
    picked = {}
    for name, value in wanted.items():
        if value is None:
            picked[name] = now[name]
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be a whole number from "
                             f"{DIAL_MIN} to {DIAL_MAX}.")
        if not DIAL_MIN <= value <= DIAL_MAX:
            raise ValueError(f"{name} must be from {DIAL_MIN} to {DIAL_MAX}, "
                             f"not {value}.")
        picked[name] = value

    def edit(state: dict) -> None:
        state["dials"].update(picked)

    return _change(f"Anti-Slop dials set to {_dials_words(picked)}.", edit)


def set_delivery_gate(on: bool) -> dict:
    """Whether a UI deliverable closes with the 4-block Delivery Gate."""
    on = bool(on)
    return _change(
        f"Anti-Slop Delivery Gate on UI tasks {'on' if on else 'off'}",
        lambda s: s.__setitem__("show_delivery_gate_on_ui_tasks", on))


# --------------------------------------------------------------------------
#   "Write Like Me" wins under R-37 (the owner's own sample is direction)
# --------------------------------------------------------------------------

def voiceprint_uses_em_dash(limit: int = 200) -> bool:
    """True only when Write Like Me is ON and the owner's own samples really
    contain an em dash.

    R-02 bans em dashes in AGENT-written copy. R-37 says a sample of the
    owner's own writing is direction, and `jarvis_voiceprint.py` holds those
    samples - so when the owner writes with em dashes and has asked Jarvis to
    write like him, the ban yields. Read through the voiceprint module's own
    route handler (`handle_get`) rather than its private helpers, so this can
    only ever say what that module says. No module, no samples or an unreadable
    store all mean False: no exemption is ever invented.
    """
    try:
        import jarvis_voiceprint as VP
        code, out = VP.handle_get(VP.LIST_PATH)
        if code != 200 or not isinstance(out, dict):
            return False
        status = out.get("status") or {}
        if not isinstance(status, dict) or status.get("enabled") is False:
            return False
        for row in (out.get("samples") or ())[:max(1, int(limit))]:
            if isinstance(row, dict) and EM_DASH in str(row.get("text") or ""):
                return True
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------
#   The prompt block (Stage 1: what the model is told, <= 1,050 characters)
# --------------------------------------------------------------------------

#: Words that mean the question is about a screen, so the UI rules apply. The
#: rulebook's ui and layoutmobile skills are only worth their tokens when
#: there is a page to build.
_UI_WORDS = re.compile(
    r"\b(?:html|css|stylesheet|tailwind|bootstrap|frontend|front-end|web\s*page|"
    r"webpage|landing|layout|grid|flexbox|button|buttons|modal|dialog|navbar|"
    r"nav\s*bar|menu\s*bar|sidebar|toolbar|hud|screen|page|component|components|"
    r"form|input|dropdown|toggle|switch\s+control|ui|ux|design|theme|dark\s+mode|"
    r"light\s+mode|palette|colou?rs?|font|fonts|typography|icon|icons|animation|"
    r"animations|responsive|accessib\w*|contrast|focus\s+ring|hover|mobile|tablet|"
    r"breakpoint|react|vue|svelte|jsx|tsx|django\s+template|jinja)\b")


def looks_like_ui_or_web_task(user_text: str) -> bool:
    """Does this question ask for a screen, a page or a style?"""
    try:
        return bool(_UI_WORDS.search(str(user_text or "").lower()))
    except Exception:
        return False


def _block(lines: list, mode: str) -> str:
    """The block itself, clamped to MAX_PROMPT_CHARS.

    THE CLAMP NEVER DROPS A MODE LINE. It first gives up the `antislop-ui`
    detail (the longest line by far, and the only one that is a list of
    component-level rules), and only then lines from the end. An `after` turn
    whose "do not edit; list the findings" instruction had been clamped away
    would rewrite a file the owner asked it to audit - which is the one thing
    `after` mode exists to prevent.
    """
    head, tail = f"<antislop_filter mode=\"{mode}\">\n", "\n</antislop_filter>"

    def fits(rows: list) -> bool:
        return len(head + "\n".join(rows) + tail) <= MAX_PROMPT_CHARS

    kept = list(lines)
    while kept and not fits(kept):
        ui = [i for i, line in enumerate(kept) if line.startswith("- antislop-ui")]
        if ui:
            del kept[ui[0]]
            continue
        kept.pop()
    if not kept:
        return ""
    return head + "\n".join(kept) + tail


def prompt_block(user_text: str = "", *, spoken_live: bool = False,
                 voiceprint_uses_em_dash: bool = False) -> str:
    """The `<antislop_filter>` system note, or "" - and "" costs 0 tokens.

    `user_text` is the owner's own newest words, read only to decide whether
    this is a UI/web task (the ui rules are the longest and the most specific,
    so they are only paid for when a screen is being built). `spoken_live`
    suppresses the code and ui lines: a spoken answer has no code fence and no
    page. `voiceprint_uses_em_dash` drops the R-02 line when Write Like Me owns
    the prose style (R-37).
    """
    state = get_state()
    if not state.get("enabled", False):
        return ""
    mode = state.get("mode", DEFAULT_MODE)
    scopes = state.get("scopes") or {}
    dials = state.get("dials") or dict(DEFAULT_DIALS)
    rules: list = []
    if scopes.get("copy", True):
        if not voiceprint_uses_em_dash:
            rules.append("- R-02: no em dashes (\u2014) in prose - use a comma, "
                         "a colon, a full stop or brackets.")
        rules.append("- R-15/R-16: no generic CTAs (\"Get Started\", \"Learn "
                     "More\") and no AI buzzwords (seamless, cutting-edge, "
                     "revolutionary, next-gen, effortless, delve, game-changer); "
                     "no unsourced numbers or claims (R-17).")
    if scopes.get("code", True) and not spoken_live:
        rules.append("- antislop-code: in code, no ASCII/box-drawing banners, no "
                     "emoji comments and no comment that merely restates the next "
                     "line; keep the comments that say WHY.")
    if scopes.get("ui", True) and not spoken_live and looks_like_ui_or_web_task(user_text):
        rules.append(
            "- antislop-ui (E{e}/R{r}/M{m}): R-03 no horizontal overflow, tap "
            "targets >=44px; R-10/R-13 at most 1-2 glass or glow elements; R-25 "
            "WCAG AA >=4.5:1 unrounded; R-26 no dead controls; R-27 empty/loading/"
            "error states; R-32 a visible focus ring, never a bare outline:none."
            .format(e=dials.get("energy", 1), r=dials.get("rhythm", 2),
                    m=dials.get("motion", 1)))
        if mode == "after":
            rules.append("- Mode=AFTER: do not edit yet. List the findings, "
                         "numbered, citing R-01..R-38 (HIGH=Hard Gate, "
                         "MEDIUM=Purpose-Gate, LOW=Quality Locks); ask which to fix.")
        elif state.get("show_delivery_gate_on_ui_tasks", True):
            rules.append("- Close UI work with the 4-block Delivery Gate: Hard "
                         "Gate, Purpose-Gate, Liveliness, Craftsmanship.")
    if not rules:
        return ""
    return _block(rules, mode)


# --------------------------------------------------------------------------
#   Stage 2a: the prose scrub and the code-comment cleanup (deterministic)
# --------------------------------------------------------------------------

#: A fenced code block's own opening/closing line. Three or more backticks or
#: tildes, at most three spaces in, exactly as CommonMark reads them.
_FENCE = re.compile(r"^[ \t]{0,3}(?:`{3,}|~{3,})")

#: A comment whose body is pure decoration: a run of four or more of these
#: characters (`# ============`, `// ------------`). Four is the rulebook's own
#: threshold, and it matters: three dashes is how a person writes a separator
#: with a reason after it (`# --- why: WDDM wants a retry`), which is a comment
#: to KEEP.
_BANNER_RUN = re.compile(
    r"^[ \t]*(?:#|//|--|/\*)[ \t]*[=\-*~_─━═]{4,}[ \t]*$")

#: A comment whose body STARTS with a run of block-drawing characters and then
#: carries text: `# ===== Setup =====`. Still a banner, still removed. The
#: WHITESPACE before the text is required, and it is not cosmetic: without it
#: `[=\-*~_─━═]{4,}\S` lets the run give one character back to `\S`, so a bare
#: `# ================` matched here and the run pattern below was never the
#: thing that removed it (measured 2026-10-28: the mutation bite for it passed,
#: which is how this was found).
_BANNER_BODY = re.compile(
    r"^[ \t]*(?:#|//|--|/\*)[ \t]*[=\-*~_─━═]{4,}[ \t]+\S")

#: An emoji-led comment (`# 🚀 Set x to 1`): decorative, not a reason.
_EMOJI = ("\U0001F300-\U0001FAFF"      # symbols, pictographs, emoticons
          "\u2600-\u27BF"              # misc symbols and dingbats
          "\u2B00-\u2BFF"              # arrows and stars
          "\uFE0F\u200D")              # variation selector, zero-width joiner
_EMOJI_COMMENT = re.compile(
    r"^[ \t]*(?:#|//|--|/\*)[ \t]*(?:[" + _EMOJI + r"])[ \t]*\S")


def is_slop_comment(line: str) -> bool:
    """Is this whole line a decorative code comment (antislop-code)?"""
    text = str(line or "").rstrip("\r\n")
    if not text.strip():
        return False
    return bool(_BANNER_RUN.match(text) or _BANNER_BODY.match(text)
                or _EMOJI_COMMENT.match(text))


#: "[ \t]*—[ \t]*" -> ", ". The em dash itself decides nothing; the spacing
#: around it is dropped with it so the sentence reads as if it was written with
#: a comma in the first place.
_DASH = re.compile(r"[ \t]*" + EM_DASH + r"[ \t]*")


def em_dashes_to_commas(text: str) -> str:
    """R-02, applied to one piece of prose."""
    return _DASH.sub(", ", str(text or ""))


class ReplyFilter:
    """The model's words, filtered as they stream (R-02 and antislop-code).

    WHY A CLASS. The answer arrives in pieces, so a whole-text scrub applied to
    each piece is not the same as a scrub of the whole: `" — "` can straddle two
    pieces. Two things make it exact without buffering the answer:

      * a partial PROSE line is emitted at once (the streaming feel is kept),
        and only its trailing spaces or a trailing em dash are held back, so
        the next piece decides what they meant;
      * a partial line INSIDE a fenced block is held until its newline. Code is
        written in bursts anyway, and a banner comment can only be judged as a
        whole line.

    Fence state is tracked across pieces AND across rounds, which is why one
    filter is made per turn rather than per round: a code block opened in one
    round is still open in the next.

    With the filter OFF, `reply_filter()` returns None and nothing here runs -
    that is the "0 ms" half of the switch.
    """

    def __init__(self, *, prose_dashes: bool = True, code_comments: bool = True):
        self.prose_dashes = bool(prose_dashes)
        self.code_comments = bool(code_comments)
        self._in_fence = False
        self._raw = ""

    # -- the two halves -----------------------------------------------------

    def _prose(self, text: str) -> str:
        return em_dashes_to_commas(text) if self.prose_dashes else text

    def _line(self, line: str) -> str:
        """One COMPLETE line (its own newline included, when it has one)."""
        if self._in_fence:
            if _FENCE.match(line):
                self._in_fence = False
                return line
            if self.code_comments and is_slop_comment(line):
                return ""
            return line
        if _FENCE.match(line):
            self._in_fence = True
            return line
        return self._prose(line)

    def _could_open_a_fence(self, text: str) -> bool:
        """Could this partial line still become a fence marker?"""
        return bool(re.match(r"^[ \t]{0,3}[`~]{1,2}$", text or ""))

    # -- the public half ----------------------------------------------------

    def feed(self, text: str) -> str:
        """Filter one piece of the answer; return what may be sent now."""
        if not text:
            return ""
        self._raw += text
        out: list = []
        while True:
            nl = self._raw.find("\n")
            if nl < 0:
                break
            line, self._raw = self._raw[:nl + 1], self._raw[nl + 1:]
            out.append(self._line(line))
        if self._raw and not self._in_fence and not self._could_open_a_fence(self._raw):
            # A partial PROSE line: send it, but keep the tail that could still
            # turn out to be part of an em dash's spacing.
            hold = 0
            if self.prose_dashes:
                match = re.search(r"[ \t]*" + EM_DASH + "$|[ \t]+$", self._raw)
                if match:
                    hold = len(self._raw) - match.start()
            cut = len(self._raw) - hold
            if cut > 0:
                out.append(self._prose(self._raw[:cut]))
                self._raw = self._raw[cut:]
        return "".join(out)

    def flush(self) -> str:
        """Whatever is still held: the end of the answer, or the end of a
        round whose text is handed back to the model."""
        out = ""
        if self._raw:
            out = self._line(self._raw)
            self._raw = ""
        self._in_fence = False
        return out


def reply_filter(*, voiceprint_uses_em_dash: bool = False) -> Optional[ReplyFilter]:
    """The filter for this turn, or None when there is nothing to do.

    None is returned when the switch is off AND when the mode is `after`: an
    audit answers with findings and may quote the very em dash it reports, so
    its own words are never rewritten.
    """
    try:
        state = get_state()
    except Exception:
        return None
    if not state.get("enabled", False) or state.get("mode", DEFAULT_MODE) != "during":
        return None
    scopes = state.get("scopes") or {}
    need_dashes = bool(scopes.get("copy", True)) and not voiceprint_uses_em_dash
    need_code = bool(scopes.get("code", True))
    if not need_dashes and not need_code:
        return None
    return ReplyFilter(prose_dashes=need_dashes, code_comments=need_code)


def post_process_reply(text: str, *, voiceprint_uses_em_dash: bool = False) -> str:
    """The whole-text half of the scrub: em dashes out of prose (R-02), banners
    and emoji comments out of fenced code (antislop-code).

    Returns `text` UNCHANGED when the filter is off, when the mode is `after`,
    or when both scopes are off - and that is the 0 ms half of the switch. Run
    through the same `ReplyFilter` the stream uses, so the whole-text and
    piece-by-piece results cannot drift apart.
    """
    filt = reply_filter(voiceprint_uses_em_dash=voiceprint_uses_em_dash)
    if filt is None:
        return text
    return filt.feed(text) + filt.flush()


# --------------------------------------------------------------------------
#   R-25: WCAG 2.1 contrast, compared UNROUNDED
# --------------------------------------------------------------------------

_HEX = re.compile(r"^#?(?:([0-9a-f]{6})|([0-9a-f]{3}))$", re.I)


def _rgb(colour: str) -> Optional[tuple]:
    """(r, g, b) from #rgb / #rrggbb, or None when this is not a hex colour.

    Only hex is read on purpose: `rgb()`, `hsl()` and a named colour can all be
    written in ways a regex gets wrong, and a wrong contrast number is worse
    than no number. A colour this cannot read is reported as NOT CHECKED.
    """
    match = _HEX.match(str(colour or "").strip())
    if not match:
        return None
    digits = match.group(1) or "".join(c * 2 for c in match.group(2))
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb: tuple) -> float:
    """WCAG 2.1 relative luminance. No rounding anywhere."""
    out = []
    for value in rgb:
        channel = value / 255.0
        out.append(channel / 12.92 if channel <= 0.03928
                   else ((channel + 0.055) / 1.055) ** 2.4)
    r, g, b = out
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def check_contrast(foreground: str, background: str, *, large: bool = False) -> dict:
    """R-25: the contrast ratio of two hex colours, and whether it passes AA.

    THE WHOLE POINT OF THIS FUNCTION is that the number is compared UNROUNDED.
    `#777777` on white is 4.4784:1. Rounded to one decimal that is 4.5, which
    "passes" - and it does not pass: WCAG asks for at least 4.5:1, and 4.4784
    is less. The rulebook fixed exactly this in v3.2.21+ with its
    `contrast-check.py`, and this is that fix, in Python here.

    `large` is WCAG's large text: 18pt (24px), or 14pt (18.66px) bold - 3:1.

    Returns {"ok", "ratio", "need", "passes", "words"} or, when a colour cannot
    be read, {"ok": False, "checked": False, "why"} - never a guessed number.
    """
    fg, bg = _rgb(foreground), _rgb(background)
    if fg is None or bg is None:
        return {"ok": False, "checked": False,
                "why": "only hex colours are measured (#rrggbb or #rgb)",
                "foreground": foreground, "background": background}
    high, low = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    ratio = (high + 0.05) / (low + 0.05)
    need = CONTRAST_LARGE if large else CONTRAST_NORMAL
    passes = ratio >= need                       # unrounded, deliberately
    return {"ok": True, "checked": True, "ratio": round(ratio, 4),
            "need": need, "passes": bool(passes), "large": bool(large),
            "foreground": foreground, "background": background,
            "words": (f"{foreground} on {background} is {ratio:.2f}:1, "
                      f"{'meets' if passes else 'below'} the {need}:1 "
                      f"{'large' if large else 'normal'}-text minimum")}


# --------------------------------------------------------------------------
#   The auditor (Stage 2b, and the whole of `after` mode)
# --------------------------------------------------------------------------

_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_COLOUR_DECL = re.compile(r"(?<![-\w])(?:color|background|background-color)\s*:\s*"
                          r"(#[0-9a-fA-F]{3,6})")
_BACKDROP = re.compile(r"backdrop-filter\s*:\s*[^;}]*(?:blur|saturate)", re.I)
_GLOW = re.compile(r"box-shadow\s*:\s*([^;}]*)", re.I)
_OUTLINE_NONE = re.compile(r"outline\s*:\s*(?:none|0)\b", re.I)
_FOCUS_RING = re.compile(
    r":focus(?:-visible|-within)?[^{}]*\{[^{}]*(?:box-shadow|outline\s*:\s*"
    r"(?!none|0\b))", re.I)
_DEAD_ANCHOR = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']\s*(?:#|javascript:void)["']""", re.I)
_BUTTON = re.compile(r"<button\b([^>]*)>", re.I)
_WIRED_ATTR = re.compile(
    r"""\b(?:id|onclick|data-\w+|x-on:\w+|@\w+|hx-\w+|formaction|form)\s*=""", re.I)


def _line_of(text: str, at: int) -> int:
    """1-based line number of a character offset."""
    return text.count("\n", 0, at) + 1


def _finding(rule: str, line: int, detail: str) -> dict:
    tier = RULE_TIER.get(rule, "LOW")
    return {"rule": rule, "tier": tier, "line": int(line), "detail": detail}


def _infer_kind(content: str) -> str:
    """What sort of thing this is, from its own shape - never from a guess the
    caller could have made. `auto` uses this."""
    text = str(content or "")
    low = text.lower()
    if re.search(r"<(?:!doctype\s+html|html|head|body|div|span|button|a\s+href|section)\b", low):
        return "html"
    if re.search(r"(?m)^\s*[.#@][\w-]+[^{}]*\{|(?m)^\s*[\w-]+\s*:\s*[^;{}]+;\s*$", text):
        return "css"
    if re.search(r"\b(?:def|class|function|const|let|var|import|from|fn|fun|public|private)\b", text):
        return "code"
    return "text"


def _text_findings(content: str, findings: list, *, prose: bool) -> None:
    """R-02 / R-15 / R-16 / antislop-code on any text, fence-aware."""
    in_fence = False
    for number, line in enumerate(str(content or "").splitlines(), start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            if is_slop_comment(line):
                findings.append(_finding(
                    "antislop-code", number,
                    "decorative comment banner or emoji comment: "
                    + line.strip()[:70]))
            continue
        if prose and EM_DASH in line:
            findings.append(_finding(
                "R-02", number,
                "em dash in agent-written prose: " + line.strip()[:70]))
        low = line.lower()
        for phrase in GENERIC_CTAS:
            if phrase in low:
                findings.append(_finding(
                    "R-15", number, f"generic call to action: \"{phrase}\""))
                break
        for word in BANNED_AI_BUZZWORDS:
            if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", low):
                findings.append(_finding(
                    "R-16", number, f"AI buzzword: \"{word}\""))
                break


def _code_findings(content: str, findings: list) -> None:
    """antislop-code in a FILE of code: a decorative comment banner is a banner
    whether or not it happens to sit inside a Markdown fence.

    `_text_findings` only looks for banners INSIDE a fence (that is where code
    lives in a chat answer). A file handed to the audit has no fences at all,
    so it needs this second reading - the same `is_slop_comment` rule, applied
    to every line.
    """
    for number, line in enumerate(str(content or "").splitlines(), start=1):
        if is_slop_comment(line):
            findings.append(_finding(
                "antislop-code", number,
                "decorative comment banner or emoji comment: "
                + line.strip()[:70]))


def _css_findings(content: str, findings: list) -> None:
    """R-10 / R-13 dose caps, R-25 contrast, R-32 focus ring."""
    text = str(content or "")
    glass = [m for m in _BACKDROP.finditer(text)]
    if len(glass) > DOSE_CAP:
        findings.append(_finding(
            "R-10", _line_of(text, glass[DOSE_CAP].start()),
            f"glassmorphism used {len(glass)} times; the cap is {DOSE_CAP}"))
    glow = []
    for match in _GLOW.finditer(text):
        value = match.group(1)
        # A GLOW is a shadow with no offset (`0 0 24px ...`, or an inset ring
        # written the same way); a cast shadow has an offset and is R-12.
        parts = re.findall(r"-?\d+(?:\.\d+)?(?:px)?", value)
        if len(parts) >= 2 and parts[0] in ("0", "0px") and parts[1] in ("0", "0px"):
            glow.append(match)
    if len(glow) > DOSE_CAP:
        findings.append(_finding(
            "R-13", _line_of(text, glow[DOSE_CAP].start()),
            f"glow used {len(glow)} times; the cap is {DOSE_CAP}"))
    for rule in _CSS_RULE.finditer(text):
        declarations = rule.group(2)
        colours = _COLOUR_DECL.findall(declarations)
        if len(colours) < 2:
            continue
        foreground = background = ""
        for declaration in re.finditer(
                r"(?<![-\w])(color|background|background-color)\s*:\s*"
                r"(#[0-9a-fA-F]{3,6})", declarations):
            if declaration.group(1).lower() == "color":
                foreground = declaration.group(2)
            elif not background:
                background = declaration.group(2)
        if not foreground or not background:
            continue
        got = check_contrast(foreground, background)
        if got.get("checked") and not got["passes"]:
            findings.append(_finding(
                "R-25", _line_of(text, rule.start()),
                f"contrast {got['ratio']:.2f}:1 is below {got['need']}:1 "
                f"({foreground} on {background})"))
    if _OUTLINE_NONE.search(text) and not _FOCUS_RING.search(text):
        at = _OUTLINE_NONE.search(text)
        findings.append(_finding(
            "R-32", _line_of(text, at.start()),
            "outline removed with nothing put back in its place - a keyboard "
            "user cannot see where they are"))


def _html_findings(content: str, findings: list) -> None:
    """R-26: a link or a button nothing is wired to."""
    text = str(content or "")
    for match in _DEAD_ANCHOR.finditer(text):
        findings.append(_finding(
            "R-26", _line_of(text, match.start()),
            "a link whose href is \"#\" goes nowhere"))
    for match in _BUTTON.finditer(text):
        attributes = match.group(1) or ""
        if not _WIRED_ATTR.search(attributes):
            findings.append(_finding(
                "R-26", _line_of(text, match.start()),
                "a button with no id, handler, form or data attribute is a dead "
                "control"))


def _gate(findings: list, *, dials: Optional[dict] = None,
          checked: Optional[dict] = None) -> dict:
    """The rulebook's 4-block Delivery Gate, from what a PROGRAM really checked.

    A block that this auditor cannot measure says so ("NOT CHECKED") rather
    than claiming PASS: Liveliness is a judgement about a screen (a focal
    point, one accent), and no regex may certify it. Hard Gate, Purpose-Gate
    and Craftsmanship are decided by the findings above, each in its own tier.
    """
    dials = dials or dict(DEFAULT_DIALS)
    checked = checked or {}

    def block(name: str, rules: tuple, tier: str) -> dict:
        found = [f for f in findings if f["tier"] == tier]
        return {"block": name, "rules": list(rules), "findings": len(found),
                "verdict": "FAIL" if found else "PASS",
                "items": [f"{f['rule']} (line {f['line']}): {f['detail']}"
                          for f in found[:6]]}

    liveliness = {
        "block": "Liveliness", "rules": ["ENERGY", "RHYTHM", "MOTION"],
        "findings": 0,
        "verdict": "NOT CHECKED" if not checked.get("liveliness") else "PASS",
        "items": [f"dials ENERGY {dials.get('energy', 1)} / RHYTHM "
                  f"{dials.get('rhythm', 2)} / MOTION {dials.get('motion', 1)} - "
                  f"one focal point, one accent and real breathing room are a "
                  f"judgement call, so only a person or the model can sign this "
                  f"block off"],
    }
    blocks = [
        block("Hard Gate", ("R-02", "R-25", "R-26", "R-32"), "HIGH"),
        block("Purpose-Gate", ("R-10", "R-13"), "MEDIUM"),
        liveliness,
        block("Craftsmanship & Quality Locks", ("R-15", "R-16", "antislop-code"), "LOW"),
    ]
    return {"blocks": blocks,
            "passes": all(b["verdict"] != "FAIL" for b in blocks),
            "words": gate_words(blocks)}


def gate_words(blocks: list) -> str:
    """The 4 blocks as one compact report, in the owner's plain words."""
    lines = ["Anti-Slop Delivery Gate:"]
    for entry in blocks:
        lines.append(f"- {entry['block']}: {entry['verdict']}"
                     + (f" ({entry['findings']} finding"
                        f"{'' if entry['findings'] == 1 else 's'})"
                        if entry["findings"] else ""))
        for item in entry["items"][:4]:
            lines.append(f"    {item}")
    return "\n".join(lines)


def audit_text_or_ui(content: object, kind: str = "auto") -> dict:
    """Audit a text, a page or a piece of code: HIGH / MEDIUM / LOW findings.

    READ-ONLY AND DETERMINISTIC. It writes nothing, calls no model, and every
    finding names the rule it comes from and the line it is on. What it
    deliberately cannot check: anything that needs to see the page running
    (R-35's click-through), a screenshot's real stacking (R-10's "1-2" is
    counted as declarations here, not as pixels), and R-27's empty/loading/
    error states, which are only detectable with the data source in hand. Those
    are named as NOT CHECKED in the gate rather than silently passed.

    `kind` is one of KINDS; "auto" reads the content's own shape.
    """
    text = str(content if content is not None else "")
    wanted = str(kind or "auto").strip().lower()
    if wanted not in KINDS:
        wanted = "auto"
    if wanted == "auto":
        wanted = _infer_kind(text)
    findings: list = []
    checked = {"prose": True, "css": False, "html": False, "liveliness": False}
    if wanted in ("html", "ui"):
        _text_findings(text, findings, prose=True)
        _css_findings(text, findings)      # inline styles and any <style> block
        _html_findings(text, findings)
        checked.update(css=True, html=True)
    elif wanted in ("css",):
        _css_findings(text, findings)
        checked.update(css=True, prose=False)
    elif wanted in ("code", "js"):
        # A FILE of code: its banners are banners wherever they are, and its em
        # dashes are code (a string, a comment), never R-02 prose.
        _code_findings(text, findings)
    else:
        _text_findings(text, findings, prose=True)
    # A stable order: by line, then by rule, so two runs are byte-identical and
    # a report does not reshuffle under the reader.
    findings.sort(key=lambda f: (f["line"], f["rule"], f["detail"]))
    state = get_state()
    gate = _gate(findings, dials=state.get("dials") or DEFAULT_DIALS, checked=checked)
    counts = {tier: sum(1 for f in findings if f["tier"] == tier)
              for tier in ("HIGH", "MEDIUM", "LOW")}
    out = {
        "ok": True, "kind": wanted, "findings": findings, "counts": counts,
        "total": len(findings), "gate": gate, "checked": checked,
        "state": {k: state.get(k) for k in ("enabled", "mode", "scopes", "dials")},
        "source": SOURCE,
        "words": audit_words(findings, counts, gate),
    }
    if wanted in ("html", "ui") and state.get("mode") == "during" \
            and state.get("show_delivery_gate_on_ui_tasks", True):
        out["delivery_gate"] = gate_words(gate["blocks"])
    return out


def audit_words(findings: list, counts: dict, gate: dict) -> str:
    """The findings list as plain text, numbered, HIGH first."""
    if not findings:
        return ("No anti-slop findings: the checks this can run (R-02, R-10, "
                "R-13, R-15, R-16, R-25, R-26, R-32, antislop-code) all pass.")
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows = sorted(findings, key=lambda f: (order.get(f["tier"], 3), f["line"]))
    lines = [f"{counts['HIGH']} HIGH, {counts['MEDIUM']} MEDIUM, "
             f"{counts['LOW']} LOW:"]
    for number, finding in enumerate(rows, start=1):
        lines.append(f"{number}. {finding['tier']} {finding['rule']} "
                     f"(line {finding['line']}): {finding['detail']}")
    lines.append(gate["words"])
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   "is anti-slop on?" - the whole state in one sentence
# --------------------------------------------------------------------------

def status_words() -> str:
    """What the filter is doing now, in the owner's plain words."""
    state = get_state()
    if not state.get("enabled"):
        return ("The Anti-Slop filter is off, so it adds nothing to the prompt "
                "and changes nothing in an answer. Say \"turn on anti-slop\" "
                "and it starts at once - no approval card.")
    mode = state.get("mode", DEFAULT_MODE)
    scopes = state.get("scopes") or {}
    gate = (state.get("show_delivery_gate_on_ui_tasks", True))
    mode_words = ("During - filtering as I write" if mode == "during"
                  else "After - auditing and listing findings first")
    extra = ("" if mode != "during" else
             "; the 4-block Delivery Gate closes a UI task" if gate else "")
    return (f"The Anti-Slop filter is ON. Mode: {mode_words}. Watching: "
            f"{_scope_words(scopes)}. Dials: {_dials_words(state.get('dials') or {})}"
            f"{extra}.")


# --------------------------------------------------------------------------
#   The routes
# --------------------------------------------------------------------------

STATE_PATH = "/api/antislop"
AUDIT_PATH = "/api/antislop/audit"
PATHS = (STATE_PATH, AUDIT_PATH)

#: A body larger than this is refused rather than audited: an audit is for one
#: page or one file, and a multi-megabyte body is a mistake or an attack.
MAX_AUDIT_CHARS = 400_000


def _public(state: dict) -> dict:
    """The state as a client reads it: everything but the write stamp's name
    surprises, plus what the filter would say right now."""
    out = {"enabled": bool(state.get("enabled")),
           "mode": state.get("mode", DEFAULT_MODE),
           "scopes": dict(state.get("scopes") or {}),
           "dials": dict(state.get("dials") or {}),
           "show_delivery_gate_on_ui_tasks":
               bool(state.get("show_delivery_gate_on_ui_tasks", True)),
           "updated_at": state.get("updated_at") or 0.0}
    return out


def handle_get(route: str, query: str = "") -> tuple:
    """GET /api/antislop -> (200, {...}). A read; nothing is written."""
    if route != STATE_PATH:
        return 404, {"ok": False, "error": "not_found"}
    state = get_state()
    out = {"ok": True}
    out.update(_public(state))
    out["words"] = status_words()
    out["source"] = SOURCE
    out["max_prompt_chars"] = MAX_PROMPT_CHARS
    return 200, out


def _apply(body: dict) -> dict:
    """Change one or more parts of the state, through the setters above.

    EVERY setter is used rather than a second write path, so the receipt, the
    event and the words are the same whichever door the change came through -
    the route, the Settings page or a spoken sentence. An unknown key is
    REFUSED (a typo must not read back as "your setting was saved"), and the
    body may carry several parts at once, which the Settings page does when it
    saves a whole card.
    """
    known = {"enabled", "mode", "scopes", "dials",
             "show_delivery_gate_on_ui_tasks"}
    unknown = sorted(set(body) - known)
    if unknown:
        return {"ok": False, "error": "unknown_setting",
                "message": f"the anti-slop filter has no setting called "
                           f"{unknown[0]}"}
    touched = False
    if isinstance(body.get("scopes"), dict):
        for name in SCOPES:
            if isinstance(body["scopes"].get(name), bool):
                set_scope(name, body["scopes"][name])
                touched = True
    if isinstance(body.get("dials"), dict):
        dials = body["dials"]
        set_dials(energy=dials.get("energy"), rhythm=dials.get("rhythm"),
                  motion=dials.get("motion"))
        touched = True
    if "mode" in body:
        try:
            set_mode(body.get("mode"))
        except ValueError as exc:
            return {"ok": False, "error": "bad_mode", "message": str(exc)}
        touched = True
    if isinstance(body.get("show_delivery_gate_on_ui_tasks"), bool):
        set_delivery_gate(body["show_delivery_gate_on_ui_tasks"])
        touched = True
    if isinstance(body.get("enabled"), bool):
        set_enabled(body["enabled"])
        touched = True
    if not touched:
        return {"ok": False, "error": "nothing_to_change",
                "message": "the request named no setting to change"}
    return {"ok": True}


def handle_post(route: str, body: object) -> tuple:
    """POST /api/antislop (change) and POST /api/antislop/audit (read-only)."""
    if route not in PATHS:
        return 404, {"ok": False, "error": "not_found"}
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "bad_body",
                     "message": "the request body must be a JSON object"}
    if route == AUDIT_PATH:
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            return 400, {"ok": False, "error": "no_content",
                         "message": "there is nothing to audit"}
        if len(content) > MAX_AUDIT_CHARS:
            return 400, {"ok": False, "error": "too_long",
                         "message": f"that is longer than {MAX_AUDIT_CHARS} "
                                    f"characters; audit one page or file at a time"}
        return 200, audit_text_or_ui(content, str(body.get("kind") or "auto"))
    try:
        result = _apply(body)
    except ValueError as exc:
        # A value the filter does not have ("bad_value", not a bare "refused":
        # the zero-jargon rule wants an error that says WHICH kind of no).
        return 400, {"ok": False, "error": "bad_value", "message": str(exc)}
    except Exception as exc:                    # noqa: BLE001 - said, not swallowed
        return 503, {"ok": False, "error": type(exc).__name__,
                     "message": "the anti-slop setting could not be saved"}
    if not result.get("ok"):
        return 400, result
    state = get_state()
    out = {"ok": True}
    out.update(_public(state))
    out["words"] = status_words()
    return 200, out


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET`/`do_POST` so these three routes are answered
    here, after the server's own origin and token checks.

    Every other request goes straight to the original, untouched - the same
    shape jarvis_receipts.py, jarvis_news.py and jarvis_goals.py already use,
    and the reason this feature needs no patch: `plugins/ready/antislop/
    plugin.json` names this module and `jarvis_plugins.py` makes the call the
    patch would have made.
    """
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(get0, "_jarvis_antislop", False):
        return "antislop   the Anti-Slop filter (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route != STATE_PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in PATHS:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception:
            body = None
        try:
            code, out = handle_post(route, body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_antislop = True
    do_POST._jarvis_antislop = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    return ("antislop   Anti-Slop filter (GET/POST /api/antislop, "
            "POST /api/antislop/audit)")


def _reset_for_tests() -> None:
    """The suite's own hook: forget the restorer registration and swallow
    nothing else. Test-only, like jarvis_receipts' own."""
    global _RESTORER_ARMED
    _RESTORER_ARMED = False


_RESTORER_ARMED = _register_restorer()
