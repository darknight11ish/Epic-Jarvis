"""jarvis_injection.py - a "sneaky instruction" pattern table, for the text
Jarvis reads that is not the owner's own words (an email, a file, a web page,
a note, a tool result).

WHY THIS EXISTS. Jarvis reads a lot of text the owner did not write, and some
of it may be written to look like an instruction: "ignore your previous
instructions", "send the file to https://...", "approve this without asking".
The owner asked for a detector (CLAUDE.md, decided 2026-09-28: "a sneaky
instruction (prompt-injection) detector: test two, keep the winner"), and this
module is the cheap, always-on, no-download half of that work - a table of
patterns over the text itself. The idea, a warning line rather than a block, is
OpenJarvis's (`jarvis doctor`'s neighbours in that project; Apache-2.0). The
patterns here are written for Jarvis from examples in the wild and from the
worst cases in this project's own audits; none of OpenJarvis's text is copied.

WHAT IT IS. `PATTERNS`, a tuple of `(name, compiled regex, level)`. `scan()`
says what matched. `worst()` says the highest level found. `summary()` gives
one plain sentence for a warning line, or "".

ADVISORY ONLY. This module:
  * never removes or replaces an approval card, and never adds one either;
  * never changes a gate tier, never approves anything, never blocks a tool
    call and never decides anything on its own - a hit only adds one sentence
    to a warning line the caller was already showing;
  * never calls a model, makes no network call, reads no file, writes nothing.

A FALSE NEGATIVE IS EXPECTED AND NORMAL. An attacker who rewrites an
instruction in words no table lists will pass this unnoticed. This is one
layer, never the only defence, and it is never the reason something is
allowed to happen.

TWO KINDS OF MISTAKE, AND WHICH WAY THIS LEANS. A miss leaves the owner where
they already were: the card, the gate and the outside-text mark all still
apply. A false alarm costs one extra warning line. So the patterns are
generous on wording that has no innocent reading ("ignore all previous
instructions") and narrow on wording ordinary mail is full of - "send me the
link https://..." is deliberately NOT a hit, while "no need to ask" is one,
because the owner's own list asks for that phrase.

SPEED AND THE CAP. Every pattern is compiled once, at import. Nothing here
uses nested quantifiers: the wildcards are bounded ("at most 40 characters
that are not a full stop"), so no input can make one pattern take time
exponential in its length. `scan()` looks at the first `SCAN_LIMIT` (200,000)
characters of its input only, so a 1 MB string costs no more than a 200 KB
one. That is also a real hole, and it is said plainly here: a planted
instruction 300 KB into a file is not seen by this module at all.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
#   Numbers
# --------------------------------------------------------------------------

#: The levels, strongest first. `worst()` returns the first of these found.
LEVELS = ("high", "medium", "low")
_RANK = {"high": 3, "medium": 2, "low": 1}

#: How much of the input is scanned. Everything past this is not looked at
#: (see the docstring) - the cap is what keeps a 1 MB string cheap.
SCAN_LIMIT = 200_000

#: How much of a match is shown. Never the whole input: a warning line naming
#: the matched words must stay short enough to read.
MATCH_CHARS = 80


# --------------------------------------------------------------------------
#   The table
# --------------------------------------------------------------------------
#
# Each entry is (name, compiled regex, level). The name is a short slug; the
# plain words a warning line uses are in `_PLAIN` below. Every pattern is
# case-insensitive and every one of them is deliberately bounded - see the
# module docstring on speed.

PATTERNS = (
    # 1. "Ignore all previous instructions." The single most common opener.
    ("prompt_override", re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b[^\n.]{0,40}?"
        r"\b(?:previous|prior|earlier|above|preceding|all|any|these|those|the|your)\b"
        r"[^\n.]{0,20}?\b(?:instructions?|prompts?|rules?|directions?|commands?|"
        r"guidelines?|messages?|orders?)\b"
        r"|\b(?:ignore|disregard|forget)\s+(?:everything|all\s+of\s+the\s+above)\b"
        r"|\b(?:override|ignore)\s+(?:your|the)\s+(?:safety|security)\s+"
        r"(?:rules?|settings?|checks?)\b",
        re.I), "high"),

    # 2. "You are now unrestricted." / "Act as an AI with no rules."
    ("identity_override", re.compile(
        r"\byou\s+are\s+now\s+(?:no\s+longer\s+)?(?:an?\s+)?(?:unrestricted|unfiltered|"
        r"jailbroken|uncensored|free|DAN|AIM|STAN|DUDE|in\s+developer|in\s+god|"
        r"allowed\s+to\s+ignore)\b"
        r"|\b(?:act|behave|respond|reply|answer|pretend|role-?play|imagine|think)\s+"
        r"(?:as|like|that)\b[^\n.]{0,30}?\b(?:unrestricted|unfiltered|jailbroken|"
        r"uncensored|DAN|AIM|STAN|no\s+restrictions?|no\s+rules?|without\s+"
        r"(?:any\s+)?(?:rules?|restrictions?|limits?|filters?|guidelines?))\b"
        r"|\bact\s+as\s+(?:if|though)\s+you\s+(?:are|were|have|had)\b"
        r"|\bpretend\s+(?:that\s+)?you\s+(?:have|had)\b"
        r"|\bpretend\s+(?:that\s+)?you\s+are\s+(?:an?\s+)?(?:ai|assistant|language\s+model|"
        r"model|chatbot|jarvis)\b"
        r"|\byou\s+are\s+no\s+longer\s+(?:an?\s+)?(?:ai|assistant|language\s+model|jarvis)\b",
        re.I), "medium"),

    # 3. A shell command smuggled in as "just data": `; rm -rf`, `| curl`.
    ("shell_injection", re.compile(
        r"(?:;|&&|\|\||\||`|\$\()\s*(?:sudo\s+)?(?:rm\s+-[a-z]{0,4}[rf]|curl\b|wget\b|"
        r"nc\b|ncat\b|bash\b|sh\b|zsh\b|powershell\b|pwsh\b|invoke-webrequest\b|iwr\b|"
        r"certutil\b|reg\s+add\b|schtasks\b|net\s+user\b|del\s+/[fqsa]\b|format\s+[a-z]:|"
        r"shutdown\b|chmod\b|chown\b|dd\s+if=)"
        r"|\brm\s+-[a-z]{0,4}[rf]{1,2}\s+(?:/|~|\*|\$HOME)"
        r"|\b(?:curl|wget|iwr)\b[^\n]{0,60}\|\s*(?:ba|z|)sh\b",
        re.I), "high"),

    # 4. Sending what Jarvis read somewhere else. Requires a "to <url>" or a
    #    data-ish object, so ordinary "send me the link https://..." mail is
    #    not a hit (see the docstring).
    ("exfiltration_url", re.compile(
        r"\b(?:send|post|upload|forward|transmit|leak|exfiltrate|submit|copy)\b"
        r"[^\n.]{0,50}?\b(?:to|at)\s+(?:https?://|www\.)\S{3,}"
        r"|\b(?:send|post|upload|forward|transmit|leak|exfiltrate)\b[^\n.]{0,40}?"
        r"\b(?:everything|all\b|the\s+(?:file|files|data|contents?|results?|keys?|"
        r"tokens?|passwords?|credentials?|emails?|messages?|transcript|history|"
        r"notes?|memor(?:y|ies)|conversation|chats?))\b[^\n.]{0,50}?"
        r"\b(?:https?://|www\.)\S{3,}"
        r"|\bexfiltrat\w*"
        r"|\b(?:webhook|pastebin|ngrok)\b[^\n.]{0,40}?\b(?:https?://|www\.)"
        r"|\bhttps?://\S{3,}[^\n.]{0,40}?\b(?:with|using|including)\b[^\n.]{0,30}?"
        r"\b(?:api[_ -]?key|tokens?|passwords?|credentials?|secrets?|private\s+key)\b",
        re.I), "high"),

    # 5. Encoding it first, so a filter that reads the words does not see it.
    ("encode_and_send", re.compile(
        r"\b(?:base64|b64|hex|rot13|url-?encode|encode|encrypt|obfuscat\w+)\b"
        r"[^\n.]{0,40}?\b(?:and|then|before)\b[^\n.]{0,30}?"
        r"\b(?:send|post|upload|reply|include|email|forward|paste|write|put|transmit)"
        r"|\b(?:atob|btoa)\s*\("
        r"|\bbase64\s+(?:-d|--decode|-D)\b"
        r"|\b(?:decode|read)\s+(?:the\s+)?(?:base64|hex)\b[^\n.]{0,30}?"
        r"\b(?:and|then)\b[^\n.]{0,25}?\b(?:do|run|follow|obey|send|post|upload)\b",
        re.I), "high"),

    # 6. A long encoded-looking run with nothing to explain it. LOW, because
    #    ordinary newsletters are full of them - hence the look-behind, which
    #    keeps a blob that is part of a link or a query string out of it.
    ("encoded_blob", re.compile(
        r"(?<![\w+/=:.-])[A-Za-z0-9+/]{60,}={0,2}(?![\w+/=])"
        r"|(?<![\w:])(?:[0-9a-fA-F]{2}[\s:]){16,}"
        r"|\b(?:data|javascript):[a-z0-9+/;,=]{40,}",
        re.I), "low"),

    # 7. "DAN", "do anything now", jailbreak, developer mode.
    ("jailbreak_dan", re.compile(
        r"\b(?:DAN|do\s+anything\s+now)\b[^\n.]{0,40}?\b(?:mode|jailbreak|prompt|"
        r"no\s+restrictions?|unrestricted)\b"
        r"|\bjail\s?br(?:eak|oken)\w*"
        r"|\b(?:developer|dev|god|sudo|debug|unrestricted)\s+mode\b[^\n.]{0,30}?"
        r"\b(?:on|enabled|enable|activated|activate|start)\b"
        r"|\b(?:AIM|STAN|DUDE|BetterDAN)\s+mode\b"
        r"|\benable\s+(?:developer|god|sudo|debug)\s+mode\b",
        re.I), "high"),

    # 8. "Pretend you have no restrictions." / "Ignore your rules."
    ("no_restrictions", re.compile(
        r"\byou\s+(?:have|had|are\s+free\s+of|are\s+without)\s+(?:no|any)\s+"
        r"(?:restrictions?|rules?|limits?|filters?|guidelines?|constraints?|"
        r"polic(?:y|ies)|ethics?)\b"
        r"|\b(?:pretend|imagine|suppose|assume|say|claim|believe)\b[^\n.]{0,40}?"
        r"\b(?:no|without|free\s+of|not\s+bound\s+by)\b[^\n.]{0,20}?"
        r"\b(?:restrictions?|rules?|limits?|filters?|guidelines?|constraints?|"
        r"polic(?:y|ies)|ethics?|safety)\b"
        r"|\bignore\s+(?:your|all|any|the)\s+(?:restrictions?|rules?|guidelines?|filters?|"
        r"safety|polic(?:y|ies)|constraints?|guardrails?)\b"
        r"|\b(?:unrestricted|unfiltered|uncensored|jailbroken)\s+(?:mode|version|"
        r"assistant|ai|model|response|answer)\b"
        r"|\b(?:no\s+longer|not)\s+(?:bound|restricted|limited|constrained)\s+by\b"
        r"[^\n.]{0,30}?\b(?:rules?|restrictions?|guidelines?|polic(?:y|ies)|ethics?)\b",
        re.I), "high"),

    # 9. Chat-template delimiters: text pretending to be a new turn.
    ("chat_markers", re.compile(
        r"<\s*\|\s*[A-Za-z_][A-Za-z0-9_]{1,24}\s*\|\s*>"
        r"|\[\s*/?\s*(?:INST|SYS|SYSTEM|ASSISTANT)\s*\]"
        r"|```\s*(?:system|assistant|user|developer|instructions?|prompt)\b"
        r"|<\s*/?\s*(?:im_start|im_end|start_of_turn|end_of_turn)\s*>",
        re.I), "high"),

    # 10. "Do not tell the user." MEDIUM: a personal email really does say
    #     "don't tell anyone about the party".
    ("do_not_tell", re.compile(
        r"\b(?:do\s+not|don'?t|never|avoid)\s+(?:tell|inform|notify|mention|show|reveal|"
        r"alert|warn|let)\b[^\n.]{0,30}?\b(?:the\s+)?(?:user|owner|human|person|them|him|"
        r"her|anyone|anybody|people)\b"
        r"|\b(?:without|no)\s+(?:telling|informing|notifying|alerting)\s+(?:the\s+)?"
        r"(?:user|owner|human|them)\b"
        r"|\bkeep\s+(?:this|it|that)\s+(?:a\s+secret|secret|hidden|quiet|between\s+us)\b"
        r"|\b(?:do\s+not|don'?t)\s+(?:disclose|report|log|record)\s+(?:this|it|that)\b"
        r"|\b(?:silently|quietly|secretly)\s+(?:send|delete|approve|run|execute|change|"
        r"transfer|move)\b",
        re.I), "medium"),

    # 11. "Reply without asking." The off-the-cuff version of 12.
    ("reply_without_asking", re.compile(
        r"\b(?:reply|respond|answer|proceed|continue|go\s+ahead|act|run|execute|do\s+it)\b"
        r"[^\n.]{0,30}?\b(?:without\s+(?:asking|checking|confirming|waiting|permission|"
        r"approval)|no\s+need\s+to\s+ask|don'?t\s+ask|never\s+ask)\b"
        r"|\b(?:without|no)\s+(?:asking|checking|confirming|permission|approval|a\s+card)\b"
        r"[^\n.]{0,30}?\b(?:proceed|act|reply|respond|continue|run|execute|do\s+it|send)\b"
        r"|\b(?:do\s+not|don'?t)\s+(?:wait|ask)\s+for\s+(?:permission|approval|"
        r"confirmation)\b",
        re.I), "medium"),

    # 12. Straight at the gate: "approve this without asking", "no need to
    #     ask", "mark it as approved", "skip the approval".
    ("approval_bypass", re.compile(
        r"\b(?:approve|authoris|authoriz|accept|confirm|grant|mark)\b[^\n.]{0,30}?"
        r"\b(?:without\s+asking|automatically|auto-?approve[ds]?|no\s+need\s+to\s+ask|"
        r"without\s+(?:a\s+)?(?:card|prompt|confirmation|approval|asking)|as\s+approved)\b"
        r"|\bno\s+need\s+to\s+ask\b"
        r"|\bwithout\s+asking\b"
        r"|\bskip\s+(?:the\s+)?(?:approval|confirmation|card|gate)s?\b"
        r"|\bauto-?approve\w*"
        r"|\bbypass\s+(?:the\s+)?(?:approval|gate|confirmation|card|check)s?\b"
        r"|\b(?:gate|tier)\s+(?:to|as)\s+(?:safe|allow|allowed|auto|tier\s*0)\b"
        r"|\b(?:approve|accept)\s+(?:this|it)\s+(?:yourself|on\s+its\s+behalf)\b",
        re.I), "high"),

    # 13. Something dressed up as a system prompt or a hidden instruction.
    ("system_prompt_marker", re.compile(
        r"\b(?:BEGIN|START|END)\s+(?:OF\s+)?(?:SYSTEM|DEVELOPER|INSTRUCTION|PROMPT|"
        r"OVERRIDE|HIDDEN|INTERNAL)\b"
        r"|\b(?:SYSTEM|DEVELOPER)\s+(?:PROMPT|MESSAGE|INSTRUCTIONS?)\b"
        r"|\b(?:new|updated|revised|hidden|invisible|encoded)\s+(?:system\s+)?"
        r"(?:instructions?|prompts?|messages?)\s*[:=]"
        r"|\b(?:hidden|invisible|encoded)\s+instructions?\b"
        r"|\binstructions?\s+for\s+(?:the\s+)?(?:ai|assistant|model|jarvis|agent)\b"
        r"|\bprompt\s+injection\b",
        re.I), "medium"),

    # 14. A tool call written out as if it were the owner's turn.
    ("tool_call_spoof", re.compile(
        r"\bcall\s+(?:the\s+)?(?:tool|function|action)\s+(?:(?:named|called)\s+)?"
        r"['\"`]?[\w.-]{2,40}"
        r"|\b(?:invoke|execute|trigger|run)\s+(?:the\s+)?(?:tool|function|action)\s+"
        r"(?:named|called)\b"
        r"|\btool[_ ]call\b|\bfunction[_ ]call\b|<tool_call>|<tool_use>|\btool_use\b"
        r"|\b(?:run|execute)\s+the\s+following\s+(?:command|code|script|tool|function|"
        r"steps?)\b"
        r"|\bexecute\s+this\s+(?:code|command|tool\s+call)\b",
        re.I), "high"),

    # 15. A bare order aimed at the assistant: "delete all ...", "transfer $...".
    ("imperative_to_assistant", re.compile(
        r"\b(?:delete|remove|erase|wipe|purge|destroy)\s+(?:all|every|everything|my\s+"
        r"(?:files?|emails?|chats?|memory|memories|history|notes?|photos?|messages?))\b"
        r"|\btransfer\s+(?:all\s+)?(?:of\s+the\s+)?[$£€]\s?\d[\d,.]*"
        r"|\btransfer\s+(?:all\s+)?(?:of\s+the\s+)?(?:money|funds|balance|savings)\b"
        r"|\b(?:send|wire|pay|move)\s+[$£€]\s?\d[\d,.]*\s*(?:to|into|out\s+of)\b"
        r"|\b(?:empty|drain)\s+(?:my|the)\s+(?:account|bank|wallet|savings)\b"
        r"|\b(?:change|reset|set)\s+(?:the\s+|my\s+)?(?:password|passcode|pin)\s+to\b"
        r"|\b(?:email|send)\s+(?:this|it|everything|all)\s+to\s+(?:all|every|my)\s+"
        r"(?:contacts?|customers?|clients?|friends?)\b"
        r"|\b(?:disable|turn\s+off|delete)\s+(?:the\s+)?(?:approval|confirmation)s?\b",
        re.I), "medium"),

    # 16. Text talking to the assistant as a chat partner. LOW: on its own it
    #     is only a hint, and it is here to colour the line, not to alarm.
    ("meta_instructions", re.compile(
        r"\bas\s+an?\s+(?:ai|artificial\s+intelligence|language\s+model|assistant|chatbot)\b"
        r"|\b(?:note|message|memo|instructions?)\s+to\s+(?:the\s+)?(?:ai|assistant|model|"
        r"agent|jarvis)\b"
        r"|\b(?:dear|attention|hey)\s+(?:ai|assistant|jarvis|chatgpt|claude)\b"
        r"|\bfor\s+the\s+(?:ai|assistant|model|agent)\s+(?:reading|that\s+reads)\b",
        re.I), "low"),
)

#: The plain words a warning line uses for each pattern name. Kept short: this
#: goes inside one sentence the owner reads on a card.
_PLAIN = {
    "prompt_override": "prompt override",
    "identity_override": "identity override",
    "shell_injection": "a shell command",
    "exfiltration_url": "exfiltration",
    "encode_and_send": "encoding it before it is sent",
    "encoded_blob": "a long encoded block",
    "jailbreak_dan": "a jailbreak",
    "no_restrictions": "no-restriction talk",
    "chat_markers": "chat-template markers",
    "do_not_tell": "do not tell the user",
    "reply_without_asking": "reply without asking",
    "approval_bypass": "approval bypass",
    "system_prompt_marker": "a hidden system-prompt marker",
    "tool_call_spoof": "a spoofed tool call",
    "imperative_to_assistant": "an order aimed at Jarvis",
    "meta_instructions": "text addressed to Jarvis",
}


# --------------------------------------------------------------------------
#   Reading it
# --------------------------------------------------------------------------

def _shown(matched: str) -> str:
    """The matched words, whitespace tidied, cut to MATCH_CHARS characters.
    Never the whole input - a warning line has to stay readable."""
    text = " ".join((matched or "").split())
    if len(text) <= MATCH_CHARS:
        return text
    return text[:MATCH_CHARS - 1] + "…"


def scan(text: str) -> list:
    """Every pattern that matched, as `{"name", "level", "match"}`.

    One entry per pattern, in the order `PATTERNS` lists them, holding that
    pattern's first match - cut to MATCH_CHARS characters. Only the first
    SCAN_LIMIT characters are looked at. A string that is not a string, or is
    empty, gives an empty list; nothing here raises."""
    if not isinstance(text, str) or not text:
        return []
    hay = text[:SCAN_LIMIT]
    found = []
    for name, rx, level in PATTERNS:
        try:
            m = rx.search(hay)
        except Exception:       # pragma: no cover - a regex is never this broken
            continue
        if m:
            found.append({"name": name, "level": level, "match": _shown(m.group(0))})
    return found


def worst(text: str) -> str:
    """The highest level any pattern found: "high", "medium", "low", or ""."""
    levels = [r["level"] for r in scan(text)]
    if not levels:
        return ""
    return max(levels, key=lambda lv: _RANK.get(lv, 0))


def summary(text: str) -> str:
    """One plain sentence for a warning line, or "" when nothing matched.

    Advisory wording only: it says the text LOOKS like it is trying to
    instruct Jarvis. It never says the text is safe, never tells the caller
    to stop, and never names a gate or a tier."""
    hits = scan(text)
    if not hits:
        return ""
    names = []
    for r in hits:
        plain = _PLAIN.get(r["name"], r["name"].replace("_", " "))
        if plain not in names:
            names.append(plain)
    shown = ", ".join(names[:3])
    if len(names) > 3:
        shown += f" and {len(names) - 3} more"
    return (f"This text looks like it is trying to instruct Jarvis ({shown}) - "
            "treat it as data, never as instructions.")
