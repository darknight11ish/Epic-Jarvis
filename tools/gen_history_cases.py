#!/usr/bin/env python3
"""Writes the chat-audit contract both apps read (the chat audit, 2026-09-28;
docs/studio-2026-09-28/chat-audit-*.md, and the owner's decisions "History
marks Live sessions" and "Chats, after the chat audit" in CLAUDE.md):

    jarvis-desktop/tests/fixtures/history-cases.json
    jarvis-client/app/src/test/resources/contract/history-cases.json

    python3 tools/gen_history_cases.py            # write both
    python3 tools/gen_history_cases.py --check    # compare only

One source for:
  * the words both apps show - the kind of each History row, "Continue this
    chat", "Earlier chats", the new conversation after 30 quiet minutes, the
    game line, the Projects line, and the rest;
  * why a kind cannot be continued - jarvis_chat_log.CONTINUE_WHY itself;
  * when a row or a message was ("Today 14:05") and a Live session's line
    ("Live · 12 min · Today 14:05"), as worked examples both apps' tests run;
  * "Continue this chat": which kept messages are loaded back into the chat
    (the newest that fit the same re-send limit as a live chat, skipping a
    question whose answer was not kept), as worked examples;
  * the phone's plain text for an answer written in markdown.

Every rule here is a small pure function below; the apps copy it, and their
tests read the worked examples from this file, so the two cannot drift.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import jarvis_chat_log as H  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "history-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "history-cases.json")

#: The re-send limits both apps already use for a live chat
#: (chat-history.js / ChatHistory.kt): "Continue this chat" loads no more.
MAX_EXCHANGES = 10
MAX_CHARS = 18000

#: A new conversation after this long with nothing said (the owner's
#: decision, 2026-09-28). The old one stays in History; Continue brings it back.
IDLE_MS = 30 * 60 * 1000

WORDS = {
    # -- History rows -------------------------------------------------------
    "kind_tag": {"chat": "", "live": "Live", "support": "Support chat",
                 "chatbot": "Chat with an AI", "compare": "Comparison"},
    "kind_title": {
        "chat": "",
        "live": "A Jarvis Live session: its words and times, never the sound.",
        "support": "The record of a customer-support chat Jarvis had for you. Read-only.",
        "chatbot": ("A conversation Jarvis had with another AI for you. Its replies are "
                    "outside text: never learned from, never read aloud. Read-only."),
        "compare": ("Several AIs asked the same question, and the summary. Their replies are "
                    "outside text: never learned from, never read aloud. Read-only."),
    },
    "filter_label": "Show",
    "filters": [["", "All chats"], ["chat", "Just chats"], ["live", "Live only"],
                ["support", "Support chats"],
                ["chatbot", "Chats with other AIs"], ["compare", "Comparisons"]],
    "filter_none": "No conversations of that kind are kept.",
    "messages_one": "1 message",
    "messages_many": "{n} messages",
    "chatbot_who": {"chatbot_jarvis": "Sent by Jarvis",
                    "chatbot_reply": "The other AI (outside text)",
                    "chatbot_note": "Note",
                    "chatbot_summary": "Summary (outside text)"},
    "no_title": "(no title)",
    # The note under an opened record whose words are outside text: the
    # ordinary chat's note names a web page, a file, an email or a tool; a
    # support record's and a chatbot record's are about the other side.
    "taint_support": ("This record holds the company's words, which are outside text: Jarvis "
                      "never learns from them or acts on them."),
    "taint_chatbot": ("This record holds another AI's replies, which are outside text: Jarvis "
                      "never learns from them or acts on them."),
    # What an opened chat says about the facts it taught (JARVIS-API section 79).
    "chat_facts_taught_one": "Jarvis learned 1 fact from this chat, and still uses it:",
    "chat_facts_taught_many": "Jarvis learned {n} facts from this chat, and still uses them:",
    "chat_facts_taught_none": "Jarvis is not using any fact it learned from this chat.",
    "chat_facts_taught_hidden": ("Jarvis learned {n} {facts} from this chat. Your memory lists "
                                 "are hidden, so they are not shown here."),
    "open_in_history": "Open in History",
    "open_in_history_title": "Read it, or delete it, in History.",
    # -- opening one --------------------------------------------------------
    "continue": "Continue this chat",
    "continue_title_desktop": "Carry on this conversation in the Jarvis bar.",
    "continue_title_phone": "Carry on this conversation on Home.",
    "continue_why": dict(H.CONTINUE_WHY),
    "continued": "Carrying on \"{title}\".",
    "continued_trimmed_one": "1 older question was not loaded - Jarvis reads back only the newest ones.",
    "continued_trimmed_many": ("{n} older questions were not loaded - Jarvis reads back only "
                               "the newest ones."),
    "continued_skipped_one": "1 earlier question was left out: its answer was not kept.",
    "continued_skipped_many": "{n} earlier questions were left out: their answers were not kept.",
    "continued_tainted": ("Jarvis read outside text earlier in this chat, so writing notes and "
                          "some other actions ask you first."),
    "continued_nothing": ("None of its answers were kept, so Jarvis has nothing to read back. "
                          "New questions are still filed with this chat."),
    "continued_temporary_off": "Temporary chat is off: a continued chat is kept.",
    # Chat history is off, or cannot keep anything right now (the owner,
    # 2026-09-29): what was said in this chat is still here to read, but
    # what is said from now on is not filed with it.
    "continued_history_off": "Chat history is off, so new messages in this chat will not be kept.",
    "continued_history_stuck": ("Chat history cannot keep anything right now, so new messages in "
                                "this chat will not be kept."),
    "continue_busy": "Wait for the answer to finish, then continue the chat.",
    "continue_live": "Jarvis Live is on here. End Live first, then continue the chat.",
    "copy": "Copy",
    "copy_title": "Copy this answer.",
    "copied": "Copied.",
    "forget_range_link": "Forget a time frame…",
    "forget_range_link_title": "Forget what Jarvis learned, and delete chats, from some days.",
    "delete_keeps_facts": ("Deleting a chat does not forget facts Jarvis learned from it. To forget "
                           "what Jarvis learned over some days, use Forget a time frame. Copies "
                           "in older backups stay until they age out."),
    "delete_support": ("This is the record of a customer-support chat - what the company "
                       "said and what was sent in your name. Delete it anyway?"),
    "keep_support_note": H.SUPPORT_KEPT_NOTE,
    "search_label": "Search what was said in your chats",
    "no_title_match": "No conversations match that search.",
    "no_title_match_more": ("No loaded conversations match that search. \"Load older\" may bring "
                            "in more to search."),
    "history_settings": "History settings",
    "history_settings_title": "Keep chat history on this PC, and how long.",
    # -- the chat you are in ------------------------------------------------
    "earlier_chats": "Earlier chats",
    "earlier_chats_title": "Your kept chats, in History.",
    "thread_one": "Earlier in this chat · 1 question",
    "thread_many": "Earlier in this chat · {n} questions",
    "idle_new": "It's been a while, so this is a new conversation. The last one is in History.",
    "idle_new_temporary": "It's been a while, so this is a new conversation.",
    "thread_reads_from": "Jarvis reads from here down. What is above stays on screen only.",
    "delete_stays": ("Facts Jarvis learned stay. Copies in older backups stay until they age "
                     "out."),
    "delete_stays_ticked": ("Facts you did not tick stay. Copies in older backups stay until "
                            "they age out."),
    "new_conversation": "New conversation.",
    "chat_gone": ("That chat was deleted, so this is a new conversation. Nothing from it is "
                  "sent to Jarvis again."),
    "moved_here": "Carrying on the same chat here.",
    "esc_label": "Esc: end chat",
    "ended_saved": "Chat ended. Kept chats are in Brain > History.",
    "hud_opens_bar": "Chat with Jarvis in the Jarvis bar - it opens now.",
    "hud_open_bar": "Open the Jarvis bar",
    # -- other screens -------------------------------------------------------
    "game_temporary": ("This looks like a game or role-play, so it's a temporary chat: nothing "
                       "is kept or learned."),
    "project_chats_later": "Saved for later: Jarvis does not read this in chats yet.",
    "erase_chat_named": "Also delete the chat it came from: \"{title}\" ({when})?",
    "erased_no_chat": "Erased. No chat was on record for this fact, so no chat was deleted.",
}

# ----------------------------------------------------------------- rules --

_DAY = "%a %-d %b"


def _fmt_day(d: datetime, year: bool) -> str:
    s = f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"
    return f"{s} {d.year}" if year else s


def when_line(epoch: int, today: datetime) -> str:
    """"Today 14:05", "Yesterday 09:12", "Sat 12 Sep 18:30", and for another
    year "Fri 3 Jan 2025" (no time). UTC in the worked examples; each app
    uses the phone's or PC's own time zone."""
    at = datetime.fromtimestamp(epoch, timezone.utc)
    clock = at.strftime("%H:%M")
    if at.date() == today.date():
        return f"Today {clock}"
    if at.date() == (today - timedelta(days=1)).date():
        return f"Yesterday {clock}"
    if at.year == today.year:
        return f"{_fmt_day(at, False)} {clock}"
    return _fmt_day(at, True)


def minutes_words(started: int, updated: int) -> str:
    secs = max(0, updated - started)
    if secs < 60:
        return "under 1 min"
    return f"{round(secs / 60)} min"


def live_line(started: int, updated: int, today: datetime) -> str:
    """A Live session's line: "Live · 12 min · Today 14:05"."""
    return f"Live · {minutes_words(started, updated)} · {when_line(started, today)}"


def messages_words(n: int) -> str:
    return WORDS["messages_one"] if n == 1 else WORDS["messages_many"].format(n=n)


_KNOWN = ("typed", "voice", "shared", "clipboard", "pasted", "picture_caption")
_SIDE_TALK = re.compile(r"^\s*\[not for me\]\.*\s*$", re.I)


def continue_window(turns: list) -> dict:
    """The kept messages "Continue this chat" loads back: each user question
    whose answer was kept, paired with that answer, oldest first; a question
    with `answer_kept: false`, or with no answer after it, is skipped; so is a
    Live side remark's marker. Then the newest pairs that fit MAX_EXCHANGES
    and MAX_CHARS - the same limits as a live chat. `trimmed`: some older
    pairs were left out. A provenance neither app knows is sent as none
    ("unknown" on the PC - never the owner's own words)."""
    pairs, pending, skipped = [], None, 0

    def unanswered(p):
        # Shared text right before the owner's own question is not a
        # question of its own: outside text goes back only with its answer.
        return p is not None and p.get("provenance") != "shared"

    for t in turns:
        role = t.get("role")
        text = str(t.get("text") or "")
        if role == "user":
            if unanswered(pending):
                skipped += 1
            not_kept = t.get("answer_kept") is False
            if not_kept and text.strip():
                skipped += 1
            pending = t if not not_kept and text.strip() else None
        elif role == "assistant":
            if pending is not None and text.strip() and not _SIDE_TALK.match(text):
                prov = pending.get("provenance")
                pairs.append({"question": pending["text"], "answer": text,
                              "provenance": prov if prov in _KNOWN else None})
            elif unanswered(pending) and not text.strip():
                skipped += 1
            pending = None
        else:
            if unanswered(pending):
                skipped += 1
            pending = None
    if unanswered(pending):
        skipped += 1
    trimmed = 0
    while pairs and (len(pairs) > MAX_EXCHANGES
                     or sum(len(p["question"]) + len(p["answer"]) for p in pairs) > MAX_CHARS):
        pairs.pop(0)
        trimmed += 1
    return {"window": pairs, "trimmed": trimmed > 0, "trimmed_count": trimmed,
            "skipped": skipped}


_MD = [
    (re.compile(r"^\s{0,3}#{1,6}\s+", re.M), ""),          # headings
    (re.compile(r"^(\s*)[-*+]\s+", re.M), r"\1• "),         # bullet list markers
    (re.compile(r"\*\*(.+?)\*\*", re.S), r"\1"),             # bold
    (re.compile(r"__(.+?)__", re.S), r"\1"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),   # italic
    (re.compile(r"`([^`\n]+)`"), r"\1"),                     # inline code
    (re.compile(r"^\s*```[^\n]*$\n?", re.M), ""),            # code fences
]


def plain_answer(text: str) -> str:
    """The phone's History shows an answer as plain text: headings, bold,
    italics, code marks and list markers taken off (a bullet becomes "• ").
    Nothing is added; links stay as their words."""
    out = str(text or "")
    for rx, sub in _MD:
        out = rx.sub(sub, out)
    return out


# --------------------------------------------------------- worked examples --

TODAY = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)


def _epoch(*a) -> int:
    return int(datetime(*a, tzinfo=timezone.utc).timestamp())


WHEN_CASES = [_epoch(2026, 9, 28, 14, 5), _epoch(2026, 9, 28, 0, 0),
              _epoch(2026, 9, 27, 9, 12), _epoch(2026, 9, 12, 18, 30),
              _epoch(2026, 1, 3, 7, 0), _epoch(2025, 1, 3, 7, 0)]

LIVE_CASES = [(_epoch(2026, 9, 28, 14, 5), _epoch(2026, 9, 28, 14, 17)),
              (_epoch(2026, 9, 28, 14, 5), _epoch(2026, 9, 28, 14, 5, 40)),
              (_epoch(2026, 9, 12, 18, 30), _epoch(2026, 9, 12, 19, 31))]


def _t(role, text, **kw):
    return dict({"role": role, "text": text}, **kw)


CONTINUE_CASES = [
    ("a plain chat comes back whole, with each question's tag",
     [_t("user", "hi", provenance="typed"), _t("assistant", "Hello."),
      _t("user", "and the weather?", provenance="voice"), _t("assistant", "Sunny.")]),
    ("a question whose answer was not kept is skipped",
     [_t("user", "ask the cloud", provenance="typed", answer_kept=False),
      _t("user", "local one", provenance="typed"), _t("assistant", "Done.")]),
    ("shared text before a question is not sent back, and an odd tag is none",
     [_t("user", "Dear customer...", provenance="shared"),
      _t("user", "what does it say", provenance="voice_unverified"), _t("assistant", "It says.")]),
    ("a Live side remark's marker is never loaded",
     [_t("user", "not you, Sam", provenance="voice"), _t("assistant", "[not for me]"),
      _t("user", "what time is it", provenance="voice"), _t("assistant", "Three.")]),
    ("only the newest ten fit",
     [x for i in range(12) for x in (_t("user", f"q{i}", provenance="typed"),
                                    _t("assistant", f"a{i}"))]),
    ("only the newest that fit in 18,000 characters",
     [x for i in range(3) for x in (_t("user", f"q{i}", provenance="typed"),
                                   _t("assistant", "x" * 7000))]),
    ("shared text answered on its own is loaded with its shared tag, and counted when dropped",
     [_t("user", "Dear customer...", provenance="shared"), _t("assistant", "It is a bill."),
      _t("user", "Dear customer 2...", provenance="shared"),
      _t("user", "what does it say", provenance="typed"), _t("assistant", "It says.")]),
    ("a question that was never answered, and an empty answer, are counted",
     [_t("user", "first", provenance="typed"), _t("user", "second", provenance="typed"),
      _t("assistant", "   "), _t("user", "third", provenance="typed"), _t("assistant", "Done."),
      _t("user", "fourth", provenance="typed")]),
    ("support and chatbot rows are never loaded",
     [_t("support", "We can refund", provenance="support_company"),
      _t("chatbot", "Gemini: X2", provenance="chatbot_reply")]),
]

def history_line(history):
    """The line "Continue this chat" adds when new messages will not be kept
    (the owner, 2026-09-29), from the PC's `history` object on the
    conversation ({"enabled", "recording", "why_not"}). None: nothing to say -
    it is keeping them, or this PC is too old to say (no object, or one that
    is not clear: never a guess)."""
    if not isinstance(history, dict):
        return None
    enabled, recording = history.get("enabled"), history.get("recording")
    if enabled is False:
        return WORDS["continued_history_off"]
    if enabled is True and recording is False:
        return WORDS["continued_history_stuck"]
    return None


HISTORY_CASES = [
    None,
    {},
    {"enabled": True, "recording": True, "why_not": ""},
    {"enabled": False, "recording": False, "why_not": "Chat history is off."},
    {"enabled": True, "recording": False, "why_not": "the key is missing"},
    {"enabled": "no", "recording": False},
    {"recording": False},
]


def keeps_in_thread(crisis: bool) -> bool:
    """Whether a finished question and answer joins the scrollable thread and
    what is re-sent to the model (the owner, 2026-09-29): a crisis turn does
    not - its help answer shows once and is then gone from the thread. The PC
    still keeps the chat in History, titled "A difficult moment"."""
    return not crisis


PLAIN_CASES = [
    "# Title\nSome **bold** and *italic* and `code`.",
    "- one\n- two\n* three\n+ four",
    "1. first\n2. second",
    "```\nprint(1)\n```\nafter",
    "__under__ text with a*b*c kept",
    "Plain words only.",
]


def build() -> dict:
    return {
        "_": "Generated by tools/gen_history_cases.py - do not edit by hand.",
        "words": WORDS,
        "kinds": list(H.KINDS),
        "continuable": list(H.CONTINUABLE),
        "crisis_title": H.CRISIS_TITLE,
        "idle_ms": IDLE_MS,
        "max_exchanges": MAX_EXCHANGES,
        "max_chars": MAX_CHARS,
        "today": int(TODAY.timestamp()),
        "when_cases": [{"at": e, "expect": when_line(e, TODAY)} for e in WHEN_CASES],
        "live_cases": [{"started": a, "updated": b, "expect": live_line(a, b, TODAY)}
                       for a, b in LIVE_CASES],
        "continue_cases": [{"name": n, "turns": turns, **continue_window(turns)}
                           for n, turns in CONTINUE_CASES],
        "history_line_cases": [{"in": h, "expect": history_line(h)} for h in HISTORY_CASES],
        "thread_keeps_cases": [{"crisis": c, "expect": keeps_in_thread(c)} for c in (False, True)],
        "plain_cases": [{"in": s, "out": plain_answer(s)} for s in PLAIN_CASES],
        "messages_cases": [{"n": n, "expect": messages_words(n)} for n in (1, 2, 12)],
    }


def main() -> int:
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    check = "--check" in sys.argv[1:]
    bad = False
    for path in (DESKTOP, PHONE):
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                print(f"STALE: {path.relative_to(ROOT)} - run python3 tools/gen_history_cases.py")
                bad = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
