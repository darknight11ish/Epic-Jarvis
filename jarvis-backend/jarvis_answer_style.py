"""jarvis_answer_style.py - how a TYPED answer is laid out: bullets when it is long.

THE OWNER'S ASK, 2026-11-25: "if atlas has a long response can it be put with
bullet points" - and, in the same breath, "make sure I can adjust it in the
settings and adjust it through chat if i want to". So this is a real dial, kept
in a file, changed from either app or from chat, exactly like jarvis_manner.

THE THREE STYLES
    auto     (the default) - one plain sentence first, then one bullet per item
             once an answer has three or more separate items, or would run past
             about four sentences. A short answer stays a sentence.
    bullets  - the same, but any answer with more than one item is bulleted even
             when it is short.
    prose    - never bullets and never lists: how it has always been.

WHAT IT IS NOT
    It is not a Markdown engine. The reply stays plain text, and the chat pane
    already keeps line breaks (`white-space: pre-wrap`), so a line that starts
    with "- " is drawn as a bulleted line with no renderer change at all.
    It never touches a SPOKEN answer: the voice lane keeps
    `jarvis_agent.SPOKEN_NOTE`, which forbids lists and symbols because
    everything it writes is read aloud. This note is added only to a typed turn.

WHERE IT IS KEPT
    `answer-style.json` in the backend's config folder, beside `manner.json`
    and `web-search.json`, so a change made in the desktop, on the phone or
    through chat is the same change. A missing or damaged file is `auto`.

WHY A SEPARATE MODULE
    `jarvis_agent` already carries four notes that say how to answer (spoken,
    Live, cut-off, crisis). Each one is a module's own business; this one is
    this module's, so the words that go to the model live beside the setting
    that chooses them and can be tested without a model.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

AUTO = "auto"
BULLETS = "bullets"
PROSE = "prose"
STYLES = (AUTO, BULLETS, PROSE)
DEFAULT = AUTO

FILE_NAME = "answer-style.json"

TITLE = "Long answers"
DETAIL = (
    "When an answer has several parts, Jarvis can lay them out as bullet "
    "points instead of one long paragraph. Spoken answers are never bulleted - "
    "they are read aloud.")

LABEL = {
    AUTO: "Bullet points when it helps (default)",
    BULLETS: "Always bullet points for a list",
    PROSE: "Plain paragraphs, never bullets",
}

WHY = {
    AUTO: "A one-line answer stays a sentence; a list of three or more gets bullets.",
    BULLETS: "Any answer with more than one part is broken into bullets, however short.",
    PROSE: "Every answer is written as ordinary sentences and paragraphs.",
}

#: The line each style adds to a TYPED turn's system messages. `prose` adds
#: nothing at all - 0 tokens, and the same bytes the model got before this
#: module existed - which is also what makes turning it off fully reversible.
_COMMON = (
    "This answer will be READ, not spoken, so light layout is allowed. "
    "Never use headings, tables, code blocks, nested bullets, emojis, or any "
    "HTML. Write a bullet as a line that begins \"- \" and keep each bullet to "
    "one line. Never let a bullet carry more than one idea."
)

NOTE = {
    AUTO: (
        "When the answer has three or more separate parts, or would run past "
        "about four sentences, open with one short plain sentence and then put "
        "each part on its own bullet. Otherwise answer in ordinary sentences. "
        + _COMMON),
    BULLETS: (
        "When the answer has more than one part, open with one short plain "
        "sentence and then put each part on its own bullet, even if the answer "
        "is short. A single-part answer stays one sentence. "
        + _COMMON),
    PROSE: "",
}

_LOCK = threading.Lock()


def _config_dir() -> Path:
    """The folder the rest of the backend uses, found the same way.

    `JARVIS_CONFIG_DIR` wins when it is set: it is the documented way a test
    points this module at a throwaway folder, and a module that ignored it
    would write into the owner's real config folder during a suite run.
    """
    override = str(os.environ.get("JARVIS_CONFIG_DIR", "") or "").strip()
    if override:
        return Path(override)
    try:
        import jarvis_manner

        return jarvis_manner._config_dir()
    except Exception:  # noqa: BLE001 - a backend without manner still works
        pass
    try:
        import jarvis_search

        return jarvis_search._config_dir()
    except Exception:  # noqa: BLE001
        pass
    return Path.home() / ".openjarvis"


def path() -> Path:
    """Where the setting lives. Computed, never cached, so a test can point
    JARVIS_CONFIG_DIR at a temp folder."""
    return _config_dir() / FILE_NAME


def normalize_style(value) -> str:
    """A style id from anything an owner or an app might send, or "" if it is
    not one of the three. Aliases are what people actually type."""
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    if text in STYLES:
        return text
    if text in ("auto", "automatic", "sometimes", "when it helps", "default",
                "bullet points when it helps"):
        return AUTO
    if text in ("bullet", "bulleted", "bullets", "bullet points", "list",
                "lists", "always", "always bullet points",
                "points", "bulleted list"):
        return BULLETS
    if text in ("prose", "paragraph", "paragraphs", "plain", "plain text",
                "never", "no bullets", "sentences"):
        return PROSE
    return ""


def current() -> str:
    """The style in force. Unreadable or damaged file means the default."""
    try:
        raw = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT
    if not isinstance(raw, dict):
        return DEFAULT
    return normalize_style(raw.get("style")) or DEFAULT


def set_style(value) -> str:
    """Save one of the three styles and return it. Raises ValueError on
    anything else - a made-up value is a refusal, never a silent default."""
    style = normalize_style(value)
    if not style:
        raise ValueError(f"not one of {STYLES}: {value!r}")
    target = path()
    with _LOCK:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"style": style}, indent=2) + "\n",
                           encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            raise OSError(f"the answer style could not be saved: {exc}") from exc
    return style


def note_message(style: str = "") -> dict | None:
    """The system message for a TYPED turn, or None when there is nothing to say.

    `prose` returns None on purpose: no note means the model gets exactly the
    bytes it got before this module existed.
    """
    chosen = normalize_style(style) or current()
    text = NOTE.get(chosen, "")
    if not text:
        return None
    return {"role": "system", "content": text}


def said(style: str) -> str:
    """What the owner is told when the style changes. Plain words, one line."""
    chosen = normalize_style(style) or DEFAULT
    return {
        AUTO: ("Long answers now come as bullet points, and short ones stay "
               "sentences."),
        BULLETS: ("Answers with more than one part now come as bullet points, "
                  "however short."),
        PROSE: "Answers are now written as plain paragraphs, with no bullets.",
    }[chosen]


def handle_set(payload) -> tuple[bool, str, str]:
    """Change the style from a chat sentence's payload.

    Accepts the payload a quick lane builds (`{"style": ...}`) or a bare value,
    and returns `(ok, style_now, sentence_to_say)`. It raises no card: this
    dial changes wording only, exactly like `jarvis_manner`'s, and the owner
    asked to be able to change it through chat.
    """
    value = payload
    if isinstance(payload, dict):
        value = (payload.get("style") or payload.get("value")
                 or payload.get("answer_style") or "")
    try:
        style = set_style(value)
    except ValueError:
        return False, current(), (
            "I can lay answers out three ways: bullet points when it helps, "
            "always bullet points for a list, or plain paragraphs. Which one?")
    except OSError as exc:
        return False, current(), f"I could not save that: {exc}"
    return True, style, said(style)
