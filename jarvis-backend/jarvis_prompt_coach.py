"""jarvis_prompt_coach.py - "Coach this": what is missing from a prompt.

The owner asked, 2026-10-08: *"Are there any GitHub repos that would help me
write better prompts and give me feedback? I'd like to integrate this as a
feature I can turn off and on in Jarvis."* The four libraries they were
offered are all rejected, with the evidence in
`docs/PROMPT-COACH-DESIGN.md`; the one that matters is that `promptimal`
requires an OpenAI API key and has no local-model support, so adopting it
would send the owner's own words to OpenAI - rule 1 broken. This module does
the job with the model already on the PC, and adds no dependency at all.

WHAT IT IS. The owner writes a question and presses **Coach this**. This module
reads that question (and, by the owner's decision of 2026-10-08, the last few
turns of the conversation, so "it" and "that" have an antecedent) and returns a
strict JSON critique: a score, up to four things that are missing, questions it
would have to ask, and one rewritten prompt. Both apps then offer "Send mine"
and "Send the suggestion".

FOUR SETTINGS, and ONE THING IT KNOWS (the owner, 2026-10-09). The single
on/off switch was not enough: *"make sure it's effective and has multiple
settings, including an enable and disable."* So beside `enabled` there are now
four, in `SETTINGS` below - **when it speaks up** (only when the prompt is
genuinely weak, or whenever it has anything to say), **how blunt it is**, **what
it coaches on** (shape only, or content too), and **per-platform behaviour**
(whether the phone behaves the same as the PC or stays quieter). Every one of
them defaults to today's behaviour, and every one is applied in ONE place
(`parse` for the screen's half, `prompt_for` for the model's) so the two apps
cannot end up with different rules.

*"make sure it is aware of what model of cloud AI I am using because each kind
has their own intricacies and make sure this can stay up to date."* The AI a
prompt is headed for is named with the request (`target`: a chatbot id, a
website adapter's id, or a model name). `advice_for()` looks it up in
`DEFAULT_TARGETS` - one row per AI, each carrying what that one handles badly,
what style suits it, and the date it was last checked - and an unknown target is
reported as UNKNOWN rather than guessed at, in the app's words and in the
model's own instructions. `TARGETS_NAME` (prompt-coach-targets.json, in the
settings folder) is how the knowledge stays current without a new build; a row
older than STALE_DAYS says so wherever it is shown; and `unknown_targets()`
lists any chatbot the driver offers that has no row yet, which
`test_prompt_coach.py` fails on - so a new AI cannot arrive unnoticed.

WHAT IT IS NOT, and this is the part that must not drift:

* **It never sends anything.** It returns text. The owner sends either their
  own words or the suggestion, by pressing a button. There is no
  improve-and-send, and no mode where the coach is in the path of every
  message - the owner chose the button, with this switch as the master switch.
* **It approves nothing and acts on nothing.** No tool runs, no file is
  touched, no approval card is raised, and this module does not import
  `jarvis_gate`. A critique is advice, never a decision, and the score is never
  a gate: a 1 out of 10 is still sendable.
* **It never leaves the PC.** The model is found the house way, and the address
  is checked with `jarvis_auto_learn.check_local_model()` **before** the
  request is built - `jarvis_entities.py`'s shape, and the check fails closed.
* **Nothing is kept.** The prompt, the critique and the score are not written
  to chat history, not saved as a fact, not learned from and not counted. The
  words are the owner's own, and the critique is not a fact about them.
* **It is off until the owner turns it on.** `enabled()` reads a file and fails
  to off - missing, unreadable, malformed or not-a-bool all mean off.

WHY THE JUDGE IS WEAK, SAID PLAINLY. The model is an 8B one on the owner's own
PC. It is a mediocre prompt critic: it will miss things a strong model catches
and will sometimes be confidently wrong. That is the reason for the button
rather than an interceptor, and for "a critique with nothing to say is a valid
answer" below. The app's own line under the switch says so.

NO NEW DEPENDENCY, AND NOTHING CLEVER. Standard library only. The one HTTP call
goes through jarvis_local_http.urlopen (the helper that ignores a proxy) and
the model name comes from jarvis_sensitive.learner_model(), so nothing is
hardcoded here.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

#: The file that holds the switch, in the Jarvis settings folder. Any *.json
#: directly in that folder is picked up by the locked backup automatically
#: (jarvis_backup.py), so a new file needs no backup edit.
SETTINGS_NAME = "prompt-coach.json"

#: What the owner sees. Second person, plain, the default stated first and the
#: consequence of each direction spelled out - the house style (see
#: jarvis_search.ENABLED_DETAIL). Neither direction raises a card, and the
#: detail says why: this reads words the chat is about to send to the same
#: local model anyway, takes no action, and opens no way out of the PC.
LABEL = "Prompt coach"
DETAIL = (
    "Off (the default): nothing is read and there is no Coach this button. "
    "On: a Coach this button appears beside the box where you type. Pressing it "
    "asks the model on your own PC what is missing from your question - a score, "
    "up to four gaps, and a rewritten version you can send instead of yours. It "
    "never sends anything by itself, it never changes your words unless you pick "
    "the rewritten one, and it is only ever advice: a low score does not stop you "
    "sending what you wrote. The model on this PC is small, so its advice is "
    "sometimes wrong and it misses things a bigger model would catch. Turning "
    "this on or off happens at once - no approval card, because nothing here "
    "leaves the PC and nothing is acted on. Beside this switch are four more: "
    "when it speaks up, how blunt it is, what it coaches on, and whether your "
    "phone behaves the same. It also coaches for the AI you are sending to - the "
    "model on this PC, or a cloud service - using what Jarvis knows about that "
    "one; when it does not know an AI it says so instead of guessing.")

HEADING = "Prompt coach"
BUTTON = "Coach this"
SEND_MINE = "Send mine"
SEND_SUGGESTION = "Send the suggestion"
OFF_LINE = "The prompt coach is switched off."

# --------------------------------------------------------------------------
#   The four settings (the owner's answers, 2026-10-09)
# --------------------------------------------------------------------------
#
# The owner's verdict on the single on/off switch was: *"make sure it's
# effective and has multiple settings, including an enable and disable."*
# These are the four they then chose, in their own words: "When it speaks up",
# "How blunt it is", "What it coaches on", "Per-platform behaviour". `on/off`
# stays the master switch above them and is unchanged.
#
# EVERY ONE OF THEM DEFAULTS TO TODAY'S BEHAVIOUR, so the switch the owner
# already has keeps meaning exactly what it meant before this file grew these
# - turning the coach on cannot silently change its character.
#
# Each is (key, names, default, {value: (word, line)}), and the words are the
# ONLY copy: `status()` hands them to both apps, so a screen never invents a
# choice's name or forgets one.
SETTINGS: tuple = (
    ("speaks_up", ("when it speaks up", "how often it speaks", "when the coach speaks"),
     "any",
     {"any": ("Whenever it has something to say",
              "The coach shows every gap it can see, even on a question that is "
              "already clear. This is how it has always worked."),
      "weak": ("Only when the prompt is weak",
               "A question it would score 7 or more is passed without advice - "
               "no gaps, no rewrite. Fewer interruptions, and the same advice on "
               "the questions that need it.")}),
    ("bluntness", ("how blunt it is", "how direct it is", "tone"),
     "gentle",
     {"gentle": ("A gentle nudge",
                 "The gaps are worded as suggestions, and the model is told to "
                 "keep the tone light. This is how it has always worked."),
      "direct": ("Direct about what is wrong",
                 "The same gaps, said plainly: what is wrong, and what to change. "
                 "No hedging, still no invented complaints.")}),
    ("coaches_on", ("what it coaches on", "how much it reads", "scope"),
     "shape",
     {"shape": ("Shape only - length and clarity",
                "How the question is built: one job at a time, what 'it' points "
                "at, what shape the answer should take, lengths and constraints. "
                "This is how it has always worked."),
      "content": ("Content too - missing details and the wrong task",
                  "Also whether the question asked for the right thing, and what "
                  "it left out that the answer needs.")}),
    ("platform", ("per-platform behaviour", "on my phone", "where it speaks up"),
     "same",
     {"same": ("The phone behaves the same as the PC",
               "One setting, both apps, the same advice. This is how it has "
               "always worked."),
      "quieter_phone": ("Quieter on the phone",
                        "On the phone the coach only answers a press of Coach this "
                        "and never offers more than the two most important gaps; the "
                        "PC is unchanged.")}),
)

#: The value a setting falls back to when its file entry is missing or is not
#: one of the values above. Never a guess at what the owner meant.
SETTING_DEFAULTS = {key: dflt for key, _n, dflt, _v in SETTINGS}
#: Every key and every allowed value, for validation.
SETTING_KEYS = tuple(SETTING_DEFAULTS)
SETTING_CHOICES = {key: tuple(values) for key, _n, _d, values in SETTINGS}

WHOLE_PROMPT = ("The prompt is a whole, clear request. Put it back in "
                "`suggestion` as it is - do not rewrite what is already fine.")
NOTHING_WEAK = ("Nothing here was weak enough to flag. Your question is fine as "
               "it is - send it.")
NOTHING_WEAK_SHORT = "Nothing looked weak enough to flag. Send it."
#: "Only when the prompt is weak" (`speaks_up`): a question the model scores at
#: or above this is passed with no advice. 7 is the owner's own line - an
#: algorithmically-constructed question scoring 7 has one small gap at most,
#: and flagging that is the noise the setting exists to remove.
WEAK_BELOW = 7
#: "Quieter on the phone" (`platform`): how much the PHONE's screen shows -
#: the two gaps that matter most, and two questions rather than four. Notes,
#: not a shrink of the model's own answer (the PC's copy is untouched).
MAX_ISSUES_QUIET = 2
MAX_MISSING_QUIET = 2

#: The most gaps ever shown. A list of ten things wrong with a question is not
#: advice, it is a wall - and the model is not reliable enough to rank ten.
MAX_ISSUES = 4
#: How many earlier turns the critique may see. The owner's answer of
#: 2026-10-08: the last few turns, so pronouns have an antecedent, and no more.
MAX_TURNS = 6
TIMEOUT_SECONDS = 120.0
#: A question shorter than this is not worth a model call, and coaching "hi"
#: would only ever produce invented complaints.
MIN_WORDS = 3

#: Ollama is given this as `format`, so the shape is constrained while it
#: decodes rather than parsed hopefully afterwards. This is the house norm -
#: every shipped module declares its own SCHEMA - and `jarvis_entities.py` is
#: the smallest module to copy the surrounding call from.
SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "clear": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"what": {"type": "string"},
                               "why": {"type": "string"},
                               "fix": {"type": "string"}},
                "required": ["what", "why", "fix"],
            },
        },
        "missing": {"type": "array", "items": {"type": "string"}},
        "suggestion": {"type": "string"},
    },
    "required": ["score", "clear", "issues", "missing", "suggestion"],
}

# --------------------------------------------------------------------------
#   Which AI the prompt is headed for (the owner's words, 2026-10-09)
# --------------------------------------------------------------------------
#
# *"make sure it is aware of what model of cloud AI I am using because each
# kind has their own intricacies and make sure this can stay up to date."*
#
# WHAT IS HERE. One row per AI a prompt can be sent to - the local Ollama
# model, the API services the chatbot driver can use (jarvis_chatbot_api.py's
# own PRESETS: OpenAI's gpt-5-mini, DeepSeek, Mistral, Grok/xAI, OpenRouter,
# Groq), and the website adapters (jarvis_chatbot.py's ADAPTERS: Gemini,
# ChatGPT, Claude, Copilot, Perplexity, DeepSeek's site, Grok's site, Le Chat,
# Meta AI). Each row says what that one handles badly and what style of prompt
# suits it, with the source and the date it was last checked.
#
# WHERE A NEW MODEL IS ADDED. Three ways, in this order:
#   1. A model in `jarvis_chatbot_api.PRESETS` or `jarvis_chatbot.ADAPTERS`
#      with no row here is REPORTED, not guessed at - `unknown_targets()`
#      lists it and `test_prompt_coach.py` fails while the list is non-empty.
#      So a new chatbot cannot ship without somebody deciding about it.
#   2. A row added to `DEFAULT_TARGETS` below, which is the shipped knowledge.
#   3. A row added to the OWNER'S OWN FILE, `prompt-coach-targets.json` in the
#      settings folder (the same folder as prompt-coach.json). It overrides a
#      shipped row field by field, or adds a target the shipped table has
#      never heard of. This is the file that "keeps it up to date" without a
#      new build: the owner (or a later pass) edits it, and `from_file()`
#      reports every reason a row was refused rather than half-reading one.
#
# WHAT HAPPENS WHEN JARVIS DOES NOT KNOW THE TARGET - the part that must not
# drift: it SAYS SO. `advice_for()` returns known=False and a plain sentence,
# the critique carries it as `target.advice`, and the coach's model prompt is
# told, in as many words, that it does not know this AI and must not invent
# anything about it. There is no fallback to the local model's notes and no
# nearest-name guess: a wrong quirk is worse than an absent one.
#
# THE DATE IS THE POINT. Every row carries `checked` (YYYY-MM-DD). A row older
# than STALE_DAYS is described as possibly out of date wherever its words are
# shown, so "keep it up to date" has a visible answer instead of a promise.
TARGETS_NAME = "prompt-coach-targets.json"
TARGET_SOURCE = "the shipped table in jarvis_prompt_coach.py"
STALE_DAYS = 180

#: One row per AI. `context` is a short human sentence, not a number the code
#: does arithmetic on - these are notes for a critic, not a token budget.
#: `quirks` are what it handles badly; `style` is what suits it.
DEFAULT_TARGETS: tuple = (
    dict(id="local", name="the model on this PC (Ollama)",
         kind="local", context="Deployed context is 4096 tokens unless the "
                               "jarvis-primary Modelfile is loaded "
                               "(docs/MODEL-TOPOLOGY.md).",
         quirks=("Loses the start of a long conversation when the context fills, "
                 "because nothing in the request chooses the window.",
                 "An 8B model is a mediocre judge and will confidently 'improve' "
                 "a prompt that was already fine.",
                 "Follows a schema more reliably than prose instructions, which "
                 "is why this module sends Ollama a JSON `format`."),
         style=("Name the file, the number and the shape of the answer.",
                "One job per question; a question with two jobs in it gets one "
                "of them answered and the other forgotten.",
                "Say what to do when the answer is empty or missing."),
         checked="2026-10-09", source="docs/MODEL-TOPOLOGY.md and this repo's "
                                      "own measurements"),
    dict(id="openai_api", name="ChatGPT (OpenAI API, gpt-5-mini)",
         kind="api", context="gpt-5-mini is the preset's default model "
                             "(jarvis_chatbot_api.PRESETS).",
         quirks=("Hidden reasoning can shorten the visible answer near the "
                 "reply cap, so a tight token budget shows up as a truncated "
                 "answer rather than an error.",
                 "Prefers a stated output format; asked for 'a summary' it "
                 "chooses its own length."),
         style=("State the deliverable and its shape in the first sentence.",
                "For anything with steps, ask for them numbered."),
         checked="2026-09-28", source="preset notes in jarvis_chatbot_api.py"),
    dict(id="deepseek_api", name="DeepSeek (API, deepseek-flash)",
         kind="api", context="Thinking mode is on by default, so an answer can "
                             "be slower and cost more than its words suggest.",
         quirks=("Its own price page no longer names deepseek-chat; the legacy "
                 "names are still accepted but the default is deepseek-flash.",
                 "Reasoning runs before the answer, so 'be brief' alone does not "
                 "make it fast."),
         style=("Say the answer's length in words or bullets, not just 'short'.",
                "Ask for the conclusion first if the reasoning is not wanted."),
         checked="2026-10-06", source="preset notes in jarvis_chatbot_api.py"),
    dict(id="mistral_api", name="Mistral (API, mistral-small-latest)",
         kind="api", context="mistral-small-latest is the preset's default.",
         quirks=("Handles long pasted context well but drifts off a long list "
                 "of constraints.",
                 "Its cap field is max_tokens, so a cap covers the answer only "
                 "when the service says so."),
         style=("Keep constraints to the few that matter and put them last.",
                "Ask for the format explicitly; it defaults to prose."),
         checked="2026-09-28", source="preset notes in jarvis_chatbot_api.py"),
    dict(id="xai_api", name="Grok (xAI API, grok-4.6)",
         kind="api", context="grok-4.6 is the preset's default.",
         quirks=("Its base URL came from xAI's own client code rather than its "
                 "API reference, which could not be opened.",
                 "Casual phrasing gets a casual answer; it does not infer that "
                 "a terse question wants a formal one."),
         style=("Say the register you want if it matters.",
                "Give it the data in the question rather than expecting it to "
                "look anything up."),
         checked="2026-09-28", source="preset notes in jarvis_chatbot_api.py"),
    dict(id="openrouter_api", name="OpenRouter (API, openai/gpt-5-mini)",
         kind="api", context="OpenRouter passes each message on to the company "
                             "that runs the model you chose.",
         quirks=("The model behind the default is OpenAI's, so its terms apply "
                 "as well as OpenRouter's.",
                 "The routed model can matter more than the prompt: the same "
                 "words reach a different model if the default changes."),
         style=("Name the model you want in the question if it matters.",
                "As for the routed company's own quirks - see that row."),
         checked="2026-09-28", source="preset notes in jarvis_chatbot_api.py"),
    dict(id="groq_api", name="Groq (API, openai/gpt-oss-20b)",
         kind="api", context="Groq serves open models very fast; "
                             "openai/gpt-oss-20b is the preset's default.",
         quirks=("Speed comes from the serving, not the model: a 20B open model "
                 "still needs the task spelled out.",
                 "It answers what it was asked and will not ask a clarifying "
                 "question back."),
         style=("Put every detail in the one question; there is no follow-up.",
                "Ask for short answers explicitly - the latency makes long ones "
                "cheap to produce and expensive to read."),
         checked="2026-09-28", source="preset notes in jarvis_chatbot_api.py"),
    dict(id="gemini_web", name="Gemini (website)",
         kind="website", context="Driven in a visible browser window, at human "
                                 "pace (docs/CHATBOT-DRIVER-DESIGN.md).",
         quirks=("The driver types and reads a web page, so a very long prompt "
                 "is slow to enter and a very long answer is slow to read.",
                 "Its own memory of previous chats can colour an answer, so a "
                 "question that assumes no history can be misread."),
         style=("Keep the question to what fits one screen of typing.",
                "Say 'ignore earlier chats' when the answer must stand alone."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="chatgpt_web", name="ChatGPT (website)",
         kind="website", context="A visible browser window, not the API.",
         quirks=("A web answer's formatting (tables, code blocks) does not "
                 "always survive being read back out of the page.",
                 "It may answer from its own memory of the chat rather than the "
                 "text in front of it."),
         style=("Ask for plain prose or a simple list when the answer is read "
                "back by a program.",
                "Restate the facts you want used."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="claude_web", name="Claude (website)",
         kind="website", context="A visible browser window, not the API.",
         quirks=("Long answers are its default; it will write more than the "
                 "driver can use unless told not to.",
                 "It asks clarifying questions back, which the driver has to "
                 "answer or stop on."),
         style=("Give an explicit length ('three sentences', 'five bullets').",
                "Say whether a clarifying question is welcome or the answer "
                "should be given straight away."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="copilot_web", name="Microsoft Copilot (website)",
         kind="website", context="A visible browser window, and often signed "
                                 "in, so answers can carry web results.",
         quirks=("It mixes searched results with its own answer, so a question "
                 "with no factual content can still come back with citations.",
                 "Terse questions get a conversational answer rather than a "
                 "structured one."),
         style=("Say if you want no web search, and say the format you want.",
                "Ask for the sources separately if they matter."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="perplexity_web", name="Perplexity (website)",
         kind="website", context="A visible browser window; it is a search-first "
                                 "assistant.",
         quirks=("It answers with sources whether or not the question wanted "
                 "research.",
                 "A question about the owner's own machine gets a general web "
                 "answer rather than a local one."),
         style=("Say 'no web search needed' for a question about your own "
                "files or PC.",
                "Ask for the answer first and the sources after."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="deepseek_web", name="DeepSeek (website)",
         kind="website", context="A visible browser window, not the API.",
         quirks=("Thinking is shown before the answer on the page, so the "
                 "driver reads past it to find the answer.",
                 "It writes long answers by default."),
         style=("Ask for the final answer first, or mark it clearly.",
                "Give a length."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="grok_web", name="Grok (website)",
         kind="website", context="A visible browser window, not the API.",
         quirks=("It may pull in live posts and treat them as context.",
                 "Tone is casual by default."),
         style=("Say the register, and say whether live context is wanted.",
                "Put the facts in the question."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="lechat_web", name="Le Chat (website)",
         kind="website", context="A visible browser window, not the API.",
         quirks=("Its answers are concise and it may drop a constraint it "
                 "judged less important.",
                 "It follows the format asked for closely, including a bad one."),
         style=("List every constraint; it will not guess the missing ones.",
                "Check the format you asked for is the one you want."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
    dict(id="metaai_web", name="Meta AI (website)",
         kind="website", context="A visible browser window, not the API.",
         quirks=("It answers briefly and can treat a detailed question as a "
                 "request for a short one.",
                 "It is the least predictable of the website adapters about "
                 "format."),
         style=("Say 'in detail' and name the format if the short answer will "
                "not do.",
                "Keep the question to one job."),
         checked="2026-09-28", source="the shipped adapter's own notes"),
)

UNKNOWN_TARGET = ("Jarvis does not know this AI yet, so it cannot say what this "
                  "one handles badly or what style suits it. Add it to "
                  f"{TARGETS_NAME} in the Jarvis settings folder to teach it.")

#: The aliases the API presets' own ids and the website adapters' ids are
#: matched by. These are the chatbot driver's own names, so nothing here is a
#: second spelling invented on this side; a model typed by name (a bare
#: "qwen3:8b") is matched by `_by_model_name` instead.
TARGET_ALIASES = {
    "openai": "openai_api", "chatgpt": "chatgpt_web", "claude": "claude_web",
    "gemini": "gemini_web", "copilot": "copilot_web",
    "perplexity": "perplexity_web", "deepseek": "deepseek_api",
    "grok": "grok_web", "lechat": "lechat_web", "le chat": "lechat_web",
    "metaai": "metaai_web", "meta ai": "metaai_web", "mistral": "mistral_api",
    "openrouter": "openrouter_api", "groq": "groq_api", "xai": "xai_api",
    "ollama": "local", "local": "local", "this pc": "local",
    "openai_api": "openai_api", "deepseek_api": "deepseek_api",
    "mistral_api": "mistral_api", "xai_api": "xai_api",
    "openrouter_api": "openrouter_api", "groq_api": "groq_api",
    "gemini_web": "gemini_web", "chatgpt_web": "chatgpt_web",
    "claude_web": "claude_web", "copilot_web": "copilot_web",
    "perplexity_web": "perplexity_web", "deepseek_web": "deepseek_web",
    "grok_web": "grok_web", "lechat_web": "lechat_web",
    "metaai_web": "metaai_web",
}

#: The fields a row may carry, and the ones it must.
TARGET_FIELDS = ("id", "name", "kind", "context", "quirks", "style",
                 "checked", "source")
TARGET_REQUIRED = ("id", "name")


def targets_path() -> Path:
    """prompt-coach-targets.json in the Jarvis settings folder - the owner's
    own rows, which override or extend the shipped table."""
    return _config_dir() / TARGETS_NAME


def _row(raw: object) -> Optional[dict]:
    """One owner-written row, read strictly. None for anything that is not a
    row at all - a half-read row of quirks is worse than none, because the
    coach would state it as fact.

    Only `id` is required HERE, on purpose: a row is laid over the shipped one
    field by field, so an owner can correct one quirk without retyping the
    name, the style and the date. Nothing is filled in here at all - the
    defaults a NEW row needs (a name to show, a date, a source) are added in
    `from_file`, so an override never silently replaces the shipped row's own
    source or date with this file's name."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for key in TARGET_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if key in ("quirks", "style"):
            if not isinstance(value, (list, tuple)):
                return None
            lines = [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
            out[key] = tuple(lines)
        elif key == "context":
            if not isinstance(value, str):
                return None
            out[key] = value.strip()
        else:
            if not isinstance(value, str) or not value.strip():
                return None
            out[key] = value.strip()
    if not out.get("id"):
        return None
    return out


def from_file() -> tuple:
    """(rows, problems) from the owner's own file. Never raises: a missing
    file is ([], []), and a file that cannot be read or parsed is ([], [one
    sentence]) - the shipped table still answers, and the problem is reported
    rather than swallowed."""
    try:
        raw = targets_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return (), ()
    except OSError as exc:
        return (), (f"The prompt coach's list of AI targets could not be read "
                    f"({type(exc).__name__}), so only the built-in list is used.",)
    try:
        doc = json.loads(raw)
    except Exception:
        return (), (f"{TARGETS_NAME} is not readable JSON, so only the built-in "
                    "list of AI targets is used.",)
    if isinstance(doc, dict):
        doc = doc.get("targets")
    if not isinstance(doc, list):
        return (), (f"{TARGETS_NAME} must hold a list of targets, so only the "
                    "built-in list is used.",)
    shipped = {row["id"] for row in DEFAULT_TARGETS}
    rows, problems = [], []
    for i, item in enumerate(doc):
        row = _row(item)
        if row is None:
            problems.append(f"{TARGETS_NAME} row {i + 1} is not a target "
                            "(it needs an id), so it was ignored.")
            continue
        if row["id"] not in shipped and not row.get("name"):
            problems.append(f"{TARGETS_NAME} row {i + 1} names a new target "
                            f"(\"{row['id']}\") with no name, so there is nothing "
                            "to show the owner - it was ignored.")
            continue
        if row["id"] not in shipped:
            # A BRAND-NEW target needs the two things an override does not: a
            # date (an undated claim would read as fresh for ever) and a source.
            row.setdefault("checked", time.strftime("%Y-%m-%d"))
            row.setdefault("source", f"your own {TARGETS_NAME}")
        rows.append(row)
    return tuple(rows), tuple(problems)


def target_table() -> dict:
    """{id: row}: the shipped rows, then the owner's own file laid over them
    field by field (so an owner can correct one quirk without retyping the
    row), then any id the shipped table has never heard of."""
    table = {}
    for row in DEFAULT_TARGETS:
        table[row["id"]] = dict(row)
    rows, _problems = from_file()
    for row in rows:
        merged = dict(table.get(row["id"]) or {})
        merged.update(row)
        table[row["id"]] = merged
    return table


def target_ids() -> tuple:
    """Every id Jarvis can name, sorted - the app's own list, and what a test
    holds the chatbot driver's own ids to."""
    return tuple(sorted(target_table()))


def _bare(words: object) -> str:
    """A name reduced to what matters when matching: lower case, punctuation to
    spaces, one space between words. So "ChatGPT (OpenAI API)" and "openai_api"
    both come out holding "openai api", and "this PC" holds "this pc"."""
    return re.sub(r"[^a-z0-9]+", " ", str(words or "").lower()).strip()


#: The short names the API presets' ids are built from ("<short>_api"), which is
#: also what the owner types at a terminal (`py -3 jarvis_chatbot_api.py key
#: openai`). Read from the preset table itself where it can be, so a preset's
#: short name is never typed twice.
def _preset_aliases() -> dict:
    out = {}
    try:
        import jarvis_chatbot_api
        for pid, preset in getattr(jarvis_chatbot_api, "PRESETS", {}).items():
            short = getattr(preset, "short", "")
            if short:
                out[_bare(short)] = str(pid)
    except Exception:
        pass
    return out


def resolve_target(target: object) -> str:
    """The id `target` names, or "" when Jarvis cannot tell.

    `target` may be a chatbot id ("openai_api"), a website adapter
    ("gemini_web"), the short name the owner types at a terminal ("openai",
    "groq"), an alias ("chatgpt"), the row's own display name ("ChatGPT (OpenAI
    API, gpt-5-mini)"), or a model typed by name ("qwen3:8b" resolves to
    nothing - the local lane covers this PC's models, and a cloud model belongs
    to its service's row).

    Matching is on a normalised form (case, punctuation and underscores
    ignored), exact first and then by whole words. An empty or unknown value is
    "", and the caller says so rather than guessing."""
    if target is None:
        return ""
    name = _bare(target)
    if not name:
        return ""
    table = target_table()
    if str(target).strip().lower() in table:
        return str(target).strip().lower()
    aliases = dict(TARGET_ALIASES)
    aliases.update(_preset_aliases())
    if name in aliases and aliases[name] in table:
        return aliases[name]
    for tid, row in sorted(table.items()):
        for candidate in (_bare(tid), _bare(row.get("name"))):
            if candidate and (name == candidate or name in candidate.split()
                              or candidate in name.split()
                              or f" {candidate} " in f" {name} "):
                return tid
    return ""


def stale(row: dict, *, today: Optional[str] = None) -> bool:
    """Whether a row's own `checked` date is older than STALE_DAYS. A date
    that cannot be read counts as stale - an undated claim is not a fresh
    one."""
    got = str(row.get("checked") or "")
    now = today or time.strftime("%Y-%m-%d")
    try:
        was = time.strptime(got, "%Y-%m-%d")
        is_now = time.strptime(now, "%Y-%m-%d")
    except Exception:
        return True
    days = (time.mktime(is_now) - time.mktime(was)) / 86400.0
    return days > STALE_DAYS


def advice_for(target: object) -> dict:
    """What Jarvis knows about the AI `target` names, in the owner's words.

    ALWAYS returns the same keys, so a screen never has to guess:
    {"known": bool, "id": str, "name": str, "advice": str, "quirks": [...],
     "style": [...], "context": str, "checked": str, "source": str,
     "stale": bool}.

    An unknown target is `known` False with UNKNOWN_TARGET in `advice` and
    every list empty. Nothing is filled in from a similar name: the owner
    asked for the app to say it does not know, not to guess."""
    tid = resolve_target(target)
    row = target_table().get(tid) if tid else None
    if not row:
        said = UNKNOWN_TARGET
        if str(target or "").strip():
            said = f"Jarvis does not know \"{str(target).strip()}\" yet, so it " \
                   "cannot say what that one handles badly or what style suits " \
                   f"it. Add it to {TARGETS_NAME} in the Jarvis settings folder " \
                   "to teach it."
        return {"known": False, "id": "", "name": "", "advice": said,
                "quirks": (), "style": (), "context": "", "checked": "",
                "source": "", "stale": False}
    aged = stale(row)
    advice = (f"{row['name']}. " + (row.get("context") or "")).strip()
    if aged:
        advice += (f" (Last checked {row.get('checked') or 'never'}"
                   f" - this may be out of date.)")
    return {"known": True, "id": tid, "name": str(row["name"]),
            "advice": advice, "quirks": tuple(row.get("quirks") or ()),
            "style": tuple(row.get("style") or ()),
            "context": str(row.get("context") or ""),
            "checked": str(row.get("checked") or ""),
            "source": str(row.get("source") or ""), "stale": aged}


def unknown_targets() -> tuple:
    """The chatbot driver's own models and adapters with no row in the table.

    This is what keeps the knowledge from freezing: a new service or website
    added to `jarvis_chatbot_api.PRESETS` or `jarvis_chatbot.ADAPTERS` appears
    here until somebody decides about it, and test_prompt_coach.py fails while
    the list is not empty. Never raises - a driver that cannot be imported
    (an older PC) reports nothing rather than failing the coach."""
    known = set(target_table())
    found = []
    try:
        import jarvis_chatbot_api
        for pid in getattr(jarvis_chatbot_api, "PRESETS", {}):
            if pid not in known:
                found.append(str(pid))
    except Exception:
        pass
    try:
        import jarvis_chatbot
        for aid in getattr(jarvis_chatbot, "ADAPTERS", {}):
            if aid == "fake" or aid in known:
                continue
            if aid.endswith("_api") or aid.endswith("_web"):
                found.append(str(aid))
    except Exception:
        pass
    return tuple(sorted(set(found)))


PROMPT = """You are checking ONE question a person is about to send to their \
own assistant. You are not answering it. You are telling them what is missing \
from it, so they can decide whether to improve it before sending.

The checks, in the order that matters:
1. WHAT IS IT ACTUALLY ASKING FOR? A question with more than one job in it, or \
with no clear ask, is the most common problem.
2. REFERENCES. Does it say "it", "that", "the file" with nothing to point at?
3. OUTPUT. Does it say what shape the answer should take - a list, a table, a \
short paragraph, a number - when that would change the answer?
4. CONSTRAINTS. Length, tone, what to leave out, what to do if it cannot.
5. ASSUMPTIONS. Anything it takes for granted that might be wrong.
6. EDGE CASES. What should happen when the answer is empty, missing or fails.

Be honest, not flattering. If the question is already clear, say so: set \
`clear` to true, keep `issues` empty, and put the question back almost \
unchanged in `suggestion`. INVENTING A COMPLAINT IS A FAILURE - an empty \
`issues` with `clear` true is a correct and expected answer.

Never add facts you were not given. Never answer the question. Never write \
more than four issues, and prefer the two that matter most. Each `fix` must be \
the smallest change that solves it.

Reply with JSON only, exactly this shape:
{"score": 1-10, "clear": true|false,
 "issues": [{"what": "...", "why": "...", "fix": "..."}],
 "missing": ["a question you would have to ask to do this well"],
 "suggestion": "the same request, rewritten"}

The question, and the few turns before it:

"""


class Refused(ValueError):
    """A plain-sentence refusal. str() is the reason, in words."""


# --------------------------------------------------------------------------
#   The switch
# --------------------------------------------------------------------------
_S_LOCK = threading.Lock()
_DAMAGED = ("The prompt coach's setting file could not be read, so the prompt "
            "coach stays off.")


def _config_dir() -> Path:
    """The Jarvis settings folder, the same one every other module uses:
    jarvis_framework's own answer first, then the environment, then the
    default. Read-only here - this module never creates it."""
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


def settings_path() -> Path:
    """prompt-coach.json in the Jarvis settings folder."""
    return _config_dir() / SETTINGS_NAME


def choices() -> dict:
    """The four settings as they stand, each validated against its own list.

    A key that is missing, or holds a value that is not one of that key's
    values, falls back to ITS OWN DEFAULT (`SETTING_DEFAULTS`) - today's
    behaviour - rather than to a guess at what the owner meant. So a damaged
    or half-written file can never move the coach somewhere the owner never
    chose."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    out = {}
    for key, _names, dflt, values in SETTINGS:
        got = doc.get(key)
        out[key] = got if isinstance(got, str) and got in values else dflt
    return out


def setting() -> dict:
    """{"on": bool, "why": str, ...the four settings}. No file: off, the
    default. Unreadable, not JSON, or `enabled` not a bool: off, and `why` says
    so - never a bare False. The four settings are keys beside `on`, so a
    caller that only reads `on` and `why` is unaffected by them."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        out = {"on": False, "why": ""}
        out.update(SETTING_DEFAULTS)
        return out
    except OSError as exc:
        out = {"on": False, "why": f"The prompt coach's setting file could not "
                                    f"be read ({type(exc).__name__}), so it stays off."}
        out.update(SETTING_DEFAULTS)
        return out
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        out = {"on": False, "why": _DAMAGED}
        out.update(SETTING_DEFAULTS)
        return out
    on = doc.get("enabled", False)
    if not isinstance(on, bool):
        out = {"on": False, "why": _DAMAGED}
        out.update(SETTING_DEFAULTS)
        return out
    out = {"on": bool(on), "why": ""}
    for key, _names, dflt, values in SETTINGS:
        got = doc.get(key)
        out[key] = got if isinstance(got, str) and got in values else dflt
    return out


def enabled() -> bool:
    """What every caller asks. Fails to off."""
    try:
        return setting()["on"] is True
    except Exception:
        return False


def _write(doc: dict) -> None:
    """The one writer. Atomic, under a lock, like every other setting here."""
    with _S_LOCK:
        path = settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            raise Refused(f"The prompt coach's setting could not be saved "
                          f"({type(exc).__name__}).")


def _on_disk() -> dict:
    """The file as it is, for a read-modify-write. Never raises: a file that
    cannot be read is treated as empty, so a bad file is REPAIRED by the next
    change rather than blocking it."""
    try:
        doc = json.loads(settings_path().read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def set_enabled(on: bool) -> dict:
    """Write the master switch. Both directions are instant: nothing about this
    feature opens a way out of the PC, takes an action or loosens a rule, so
    neither direction asks. The four settings are kept as they were."""
    doc = _on_disk()
    doc["enabled"] = bool(on)
    doc["changed"] = time.time()
    _write(doc)
    return dict(setting(), ok=True)


def set_choice(key: object, value: object) -> dict:
    """Write ONE of the four settings. Same rules as the master switch: at
    once, no card, either direction - none of the four opens a way out of the
    PC, takes an action, or changes what the coach is allowed to READ (it reads
    the same question either way; they change only what it says about it).

    A key that is not one of the four, or a value that is not one of that key's
    values, is REFUSED in words rather than guessed at: guessing here would
    mean "your setting moved" when it did not. The reason names the real
    choices, taken from `SETTINGS` - the one place they are written."""
    name = str(key or "")
    row = next((r for r in SETTINGS if r[0] == name), None)
    if row is None:
        raise Refused("The prompt coach has no setting called "
                      f"\"{name}\". It has: {', '.join(SETTING_KEYS)}.")
    want = str(value or "")
    values = row[3]
    if want not in values:
        raise Refused(f"\"{want}\" is not one of the choices for {row[0]}; it "
                      f"has: {', '.join(values)}.")
    doc = _on_disk()
    doc[name] = want
    doc["changed"] = time.time()
    _write(doc)
    return dict(status(), ok=True)


# --------------------------------------------------------------------------
#   The model
# --------------------------------------------------------------------------
def _model() -> tuple:
    """(url, model) the house way, or (None, None). Never raises: this is the
    same shape jarvis_entities.py, jarvis_widgets.py and jarvis_tidy.py use."""
    try:
        import jarvis_sensitive
        url, model = jarvis_sensitive.learner_model()
    except Exception:
        return (None, None)
    if not url or not model:
        return (None, None)
    return (str(url), str(model))


def _local_check(url: str, model: str) -> str:
    """The mandatory gate before anything is sent. "" means the address is
    this PC; anything else is the plain sentence to show instead. Fails closed:
    if the checker cannot be imported, nothing is sent."""
    try:
        import jarvis_auto_learn
        return jarvis_auto_learn.check_local_model(url, model)
    except Exception:
        return ("Jarvis could not confirm the model is on this PC, so the prompt "
                "coach did not send anything.")


def _ask(url: str, model: str, prompt: str) -> Optional[str]:
    """One non-streamed answer from the local model, or None. Standard library
    plus jarvis_local_http (which is the helper that ignores a proxy)."""
    import urllib.error
    import urllib.request

    body = {"model": model, "prompt": prompt, "stream": False, "format": SCHEMA,
            "think": False, "options": {"temperature": 0.1, "num_predict": 700}}
    req = urllib.request.Request(str(url).rstrip("/") + "/api/generate",
                                 data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        try:
            import jarvis_local_http
            resp = jarvis_local_http.urlopen(req, TIMEOUT_SECONDS)
        except ImportError:
            resp = urllib.request.build_opener(
                urllib.request.ProxyHandler({})).open(req, timeout=TIMEOUT_SECONDS)
        with resp as r:
            out = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 400 and "think" in body:
            body.pop("think", None)
            try:
                resp = urllib.request.build_opener(
                    urllib.request.ProxyHandler({})).open(
                        urllib.request.Request(
                            str(url).rstrip("/") + "/api/generate",
                            data=json.dumps(body).encode("utf-8"), method="POST",
                            headers={"Content-Type": "application/json"}),
                        timeout=TIMEOUT_SECONDS)
                with resp as r:
                    out = json.loads(r.read().decode("utf-8") or "{}")
            except Exception:
                return None
        else:
            return None
    except Exception:
        return None
    text = out.get("response") if isinstance(out, dict) else None
    return text if isinstance(text, str) else None


# --------------------------------------------------------------------------
#   Reading the answer
# --------------------------------------------------------------------------
def _clean(text: str) -> str:
    """Strip a ```json fence and any stray prose around one JSON object."""
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    return text


def parse(raw: object, *, speaks_up: str = "any", bluntness: str = "gentle",
          coaches_on: str = "shape", platform: str = "same") -> dict:
    """The critique, or Refused. Every field is checked for type, and the
    lists are trimmed to what the screen can show. A missing or malformed
    field is a refusal, never a half-filled card.

    The four settings are applied HERE, in one place, so both apps get the same
    answer and neither has to re-implement a rule:

    * `speaks_up` "weak" drops the advice for anything the model itself scored
      `WEAK_BELOW` or better - `advice_given` says which happened, so the
      screen can say "nothing to flag" instead of showing a list of nothing.
    * `platform` "quieter_phone" trims the screen's load (`MAX_ISSUES_QUIET`,
      `MAX_MISSING_QUIET`). The advice itself is not weakened: the same gaps
      are found, and the two that matter most are the ones shown.
    * `bluntness` and `coaches_on` are stated in the MODEL'S OWN prompt
      (`prompt_for`), which is where they can actually change the words."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        raise Refused("The prompt coach did not get an answer it could read.")
    try:
        doc = json.loads(_clean(raw))
    except Exception:
        raise Refused("The prompt coach's answer was not readable JSON.")
    if not isinstance(doc, dict):
        raise Refused("The prompt coach's answer was not the shape it should be.")

    score = doc.get("score")
    if not isinstance(score, int) or isinstance(score, bool):
        raise Refused("The prompt coach's answer had no score.")
    score = max(1, min(10, score))

    raw_issues = doc.get("issues")
    if not isinstance(raw_issues, list):
        raise Refused("The prompt coach's answer had no list of gaps.")
    limit = MAX_ISSUES_QUIET if platform == "quieter_phone" else MAX_ISSUES
    issues = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        what = item.get("what")
        if not isinstance(what, str) or not what.strip():
            continue
        issues.append({"what": what.strip(),
                       "why": str(item.get("why") or "").strip(),
                       "fix": str(item.get("fix") or "").strip()})
        if len(issues) >= limit:
            break

    raw_missing = doc.get("missing")
    missing = [str(m).strip() for m in raw_missing
               if isinstance(m, str) and m.strip()] if isinstance(raw_missing, list) else []
    if platform == "quieter_phone":
        missing = missing[:MAX_MISSING_QUIET]

    suggestion = doc.get("suggestion")
    if not isinstance(suggestion, str):
        suggestion = ""

    # `clear` is the model's own answer to "is this already fine?", and the
    # screen leans on it - but a model that says "clear" while listing four
    # gaps is contradicting itself, and the gaps are the more useful half.
    clear = doc.get("clear") is True and not issues

    # "Only when the prompt is weak": a question the model itself scored at or
    # above WEAK_BELOW is passed with no advice at all. This happens BEFORE
    # `clear` is decided, and it is what `advice_given` reports - so turning
    # this setting on is visible on screen rather than being a promise in a
    # settings paragraph.
    advice_given = True
    if speaks_up == "weak" and score >= WEAK_BELOW:
        issues, missing, advice_given = [], [], False
        clear = True
        if not suggestion.strip():
            suggestion = ""

    return {"score": score, "clear": clear, "issues": issues,
            "missing": missing, "suggestion": suggestion.strip(),
            "advice_given": advice_given,
            "said": "" if advice_given else NOTHING_WEAK}


# --------------------------------------------------------------------------
#   The one entry point
# --------------------------------------------------------------------------
def _turns(history: object) -> list:
    """The last few turns, as (who, text) pairs. Anything unexpected is
    dropped rather than guessed at, and the coach never sees more than the
    owner allowed."""
    out = []
    if isinstance(history, (list, tuple)):
        for item in history:
            if isinstance(item, dict):
                who, text = item.get("who"), item.get("text")
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                who, text = item
            else:
                continue
            if isinstance(text, str) and text.strip():
                out.append((str(who or "?"), text.strip()))
    return out[-MAX_TURNS:]


def prompt_for(text: str, history: object = (), *, choices_in: Optional[dict] = None,
               target: object = None, platform: str = "same") -> str:
    """The whole prompt the local model is asked. ONE place builds it, so what
    the four settings and the target's own notes do to the model's instructions
    can be read and tested rather than inferred.

    Order: the base PROMPT, then this target's own notes (or, honestly, that
    Jarvis does not know this one), then the settings that change how it
    speaks, then the conversation, then the owner's own question last."""
    sets = dict(choices_in or {})
    prompt = PROMPT
    advice = advice_for(target)
    prompt += "\n\nWHICH AI THIS IS FOR.\n"
    if advice["known"]:
        prompt += f"The question is headed for {advice['name']}.\n"
        if advice["context"]:
            prompt += f"About it: {advice['context']}\n"
        if advice["quirks"]:
            prompt += ("What it handles badly (judge the question against these, "
                       "and say so in `why` when one of them is why a gap matters):\n")
            prompt += "".join(f"- {q}\n" for q in advice["quirks"])
        if advice["style"]:
            prompt += "What style suits it:\n"
            prompt += "".join(f"- {s}\n" for s in advice["style"])
        if advice["stale"]:
            prompt += (f"NOTE: these notes were last checked {advice['checked']} and "
                       "may be out of date. Do not treat them as certain.\n")
    else:
        prompt += ("Jarvis does NOT know this AI. Do not guess anything about it, "
                   "and do not describe how it behaves. Judge the question only on "
                   "the checks above, and do not invent a claim about that AI.\n")
        prompt += f"({advice['advice']})\n"

    prompt += "\nHOW TO SPEAK TO THE OWNER.\n"
    if sets.get("bluntness") == "direct":
        prompt += ("Be direct. Say what is wrong and what to change, in plain "
                   "words, with no hedging and no praise. Still never invent a "
                   "complaint, and still never answer the question.\n")
    else:
        prompt += ("Be a gentle nudge. Word each gap as a suggestion rather than a "
                   "fault, and keep the tone light. Still never invent a "
                   "complaint.\n")
    if sets.get("coaches_on") == "content":
        prompt += ("Also judge the CONTENT: whether the question asks for the right "
                   "thing at all, and what it left out that an answer would need "
                   "(the data, the dates, the file, the constraint that changes the "
                   "answer).\n")
    else:
        prompt += ("Judge the SHAPE only: one job at a time, references, the output "
                   "format, length and constraints. Do not judge whether the task "
                   "itself was the right one to ask for.\n")
    if sets.get("speaks_up") == "weak":
        prompt += (f"Only speak up when the question is genuinely weak. If your own "
                   f"score would be {WEAK_BELOW} or more, return no issues at all, "
                   "an empty `missing`, and `clear` true.\n")
    if platform == "quieter_phone":
        prompt += (f"This is being read on a phone. Return at most "
                   f"{MAX_ISSUES_QUIET} issues - the two that matter most - and at "
                   f"most {MAX_MISSING_QUIET} questions.\n")

    prompt += "\nThe question, and the few turns before it:\n\n"
    for who, said in _turns(history):
        prompt += f"{who}: {said}\n"
    prompt += f"owner: {str(text or '').strip()}\n"
    return prompt


def coach(text: str, history: object = (), *,
          ask: Optional[Callable[[str, str, str], Optional[str]]] = None,
          url: Optional[str] = None, model: Optional[str] = None,
          target: object = None) -> dict:
    """Critique one prompt.

    `ask` is injectable so every test in test_prompt_coach.py runs with no
    model at all - the same seam jarvis_entities.py uses. Anything wrong is a
    Refused with a plain sentence; this never raises anything else.

    `target` is which AI the prompt is headed for - a chatbot id, a website
    adapter's id, or a model name. Its own notes go into the prompt the local
    model is given, and the answer carries back what Jarvis knew (`target`).
    Nothing about it changes where the critique RUNS: still this PC's model,
    still the check below, still nothing sent anywhere."""
    words = str(text or "").strip()
    if len(words.split()) < MIN_WORDS:
        raise Refused("That is too short to coach - write a little more and try again.")
    if not enabled():
        raise Refused(OFF_LINE)

    sets = choices()
    # "Quieter on the phone" belongs to the app that asked. The PC prints it as
    # its own sentence so the caller never has to work it out: PC means "same".
    platform = "quieter_phone" if sets.get("platform") == "quieter_phone" else "same"

    if url is None or model is None:
        found_url, found_model = _model()
        url = url or found_url
        model = model or found_model
    if not url or not model:
        raise Refused("Jarvis could not find the model on this PC, so there is "
                      "nothing to coach with.")

    why = _local_check(str(url), str(model))
    if why:
        raise Refused(why)

    # An older caller sends no target at all, which means the ordinary local
    # chat: the model on this PC. Anything else it names is looked up, and an
    # unknown name is carried back as unknown rather than guessed at.
    wanted = "local" if target is None or not str(target).strip() else target
    advice = advice_for(wanted)

    prompt = prompt_for(words, history, choices_in=sets, target=wanted,
                        platform=platform)

    caller = ask or _ask
    raw = caller(str(url), str(model), prompt)
    if raw is None:
        raise Refused("The model on this PC did not answer, so there is no "
                      "coaching to show. Nothing was sent anywhere.")
    out = parse(raw, speaks_up=sets["speaks_up"], bluntness=sets["bluntness"],
                coaches_on=sets["coaches_on"], platform=platform)
    out["target"] = advice
    out["settings"] = {k: sets[k] for k in SETTING_KEYS}
    return out


# --------------------------------------------------------------------------
#   The route's half
# --------------------------------------------------------------------------
def handle_post(body: object) -> tuple:
    """(status, dict). The house shape: the module answers the code itself and
    jarvis_hud.py forwards the pair without mapping any exception."""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "The request was not the shape it should be."}
    try:
        out = coach(body.get("text") or "",
                    body.get("history") or (),
                    ask=None, url=body.get("url"), model=body.get("model"),
                    target=body.get("target"))
    except Refused as exc:
        return 409, {"ok": False, "error": str(exc)}
    return 200, {"ok": True, "coach": out}


def handle_setting(body: object) -> tuple:
    """(status, dict) for POST /api/prompt/coach/setting - the switch, and the
    four settings beside it.

    `{"enabled": true|false}` moves the master switch, exactly as before.
    `{"key": "<one of the four>", "value": "<one of its values>"}` moves that
    one setting. Both may be sent together; `enabled` is applied first, so a
    request that fails on the choice has still moved the switch it named - and
    the refusal says which half failed.

    Enabled must be a real true or false, and the value must be one of the
    key's real choices. Either is refused rather than guessed at, because
    guessing here would mean "your switch moved" when it did not.
    """
    if not isinstance(body, dict):
        return 400, {"ok": False,
                     "error": "The request needs an enabled true or false."}
    if "enabled" not in body and "key" not in body:
        return 400, {"ok": False,
                     "error": "The request needs an enabled true or false."}
    if "enabled" in body:
        if not isinstance(body.get("enabled"), bool):
            return 400, {"ok": False,
                         "error": "The request needs an enabled true or false."}
        try:
            set_enabled(body["enabled"])
        except Refused as exc:
            return 409, {"ok": False, "error": str(exc)}
    if "key" in body:
        try:
            return 200, set_choice(body.get("key"), body.get("value"))
        except Refused as exc:
            return 409, {"ok": False, "error": str(exc)}
    return 200, status()


def status() -> dict:
    """The switch's own state, for the settings screens and for
    "is the prompt coach on?" - the same shape as jarvis_search.settings().

    It carries the four settings and their own words too (`settings_rows()`),
    so BOTH apps read every choice's name and meaning from the PC and neither
    keeps a second copy that can drift. Every key that was here before is
    still here, unchanged, so an app that only knows `on` and `why` keeps
    working."""
    out = dict(setting())
    out.update({"label": LABEL, "detail": DETAIL, "heading": HEADING,
                "button": BUTTON, "send_mine": SEND_MINE,
                "send_suggestion": SEND_SUGGESTION, "ok": True,
                "settings": settings_rows(),
                "targets": list(target_ids()),
                "stale_days": STALE_DAYS})
    return out


def settings_rows() -> list:
    """The four settings as the screens draw them: one row each, with the
    value it has now, its own name, and every choice with the words that
    explain it. The ONLY copy of those words - both apps render this."""
    now = choices()
    rows = []
    for key, names, dflt, values in SETTINGS:
        rows.append({
            "key": key,
            "name": names[0],
            "names": list(names),
            "value": now[key],
            "default": dflt,
            "choices": [{"value": v, "name": values[v][0], "detail": values[v][1]}
                        for v in values],
        })
    return rows
