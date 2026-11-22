"""jarvis_router.py - which lane answers, and what it is allowed to see.

REBUILT. The original is gone. Five call sites pin the interface:

    Budget.load().status()                              jarvis_hud:1475
    budget = Budget.load()                              jarvis_hud:1705
    choose(query, local_model=, lanes=, has_image=, ...) jarvis_hud:1707
    degrade(lane, lanes, local_model)                   jarvis_hud:1846
    Decision(chosen, "you chose this lane", "manual", 0.0, inject_memory=...)
                                                        jarvis_hud:2115
    _PRIVATE.search(joined)                             jarvis_hud:2024

and `decision.lane / .reason / .gate / .inject_memory / .as_dict` are all
read. `[budget]` and `[routing]` in the config supply the numbers.

THE RULE THIS MODULE EXISTS TO ENFORCE, from JARVIS-FRAMEWORK.md section 1:

    "cloud turns get your raw question and nothing else. Local turns get your
     question plus whatever stored facts are actually relevant to it. There is
     no third option where a cloud model quietly receives your memory."

So `inject_memory` is FALSE on every cloud lane, computed from the lane rather
than passed in - a caller cannot ask for memory on a cloud turn, because the
bug that started all this (`context_from_memory = true` injecting memory into
every request, before routing even ran) was exactly a caller being trusted.

AND THE ONE THAT WAS BROKEN THE LONGEST: degrade() "has always described that
chain; nothing ever called it, so the documented behaviour did not exist"
(jarvis_hud:1820). It is called now. It walks DOWNWARD only and never returns
the lane it was given, because a degrade that can return its input is an
infinite retry loop against a service that is already refusing.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(section: str, key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get(section, {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   What must never go to a cloud lane
# --------------------------------------------------------------------------
#
# jarvis_hud:2024 uses this as `jarvis_router._PRIVATE.search(joined)`, so it
# is a compiled regex with .search, matched against joined message text.
#
# It is a BACKSTOP, not the mechanism. JARVIS-FRAMEWORK.md is explicit: "It's a
# backstop, not the primary mechanism - the primary mechanism is that cloud
# lanes are never handed memory in the first place, so even a topic missing
# from this list can't leak your stored facts, only your literal typed words."
# Anything that relies on this list being complete is designed wrong.


def _crisis_terms() -> tuple:
    """The plain-English crisis phrases `jarvis_wellbeing.py` already checks
    (CRISIS_PHRASES_EN), reused here rather than duplicated (cutting-edge
    round 4, "Keep distress off the cloud offer"). Each entry there is
    already a regex fragment with its own word shape, so it drops straight
    into this list's own `"|".join(...)`. () when jarvis_wellbeing.py is not
    on this PC, or on any error: the plain mood/mental-health words below
    still keep a distress message off the cloud offer on their own."""
    try:
        import jarvis_wellbeing
        return tuple(str(p) for p in jarvis_wellbeing.CRISIS_PHRASES_EN)
    except Exception:
        return ()


_PRIVATE_TERMS = [
    r"\bpassword\b", r"\bpassphrase\b", r"\bapi[ _-]?key\b", r"\bsecret\b",
    r"\btoken\b", r"\bcredential\b", r"\bprivate key\b", r"\bseed phrase\b",
    r"\bssn\b", r"\bsocial security\b", r"\bpassport\b",
    # Both spellings. The list otherwise uses American terms (ssn,
    # social security) and only had the British "licence" - so "what's
    # my driver's license number" typed in the owner's own words missed
    # the one backstop meant to catch literal private phrases.
    r"\bdriver'?s licen[cs]e\b",
    # The owner can be found or impersonated by these (2026-11-07, the owner's
    # Q7 ruling): home/street/mailing address, and a phone number. Deliberately
    # NOT a bare `address` - an IP address, an email address, a web address and
    # a memory address are ordinary technical words - and NOT a bare "phone"
    # ("how do I make a phone call on this PC" is not private).
    r"\bhome address\b", r"\bstreet address\b", r"\bmailing address\b",
    r"\bpostal address\b", r"\b(?:my|our)\s+address\b",
    r"\bphone number\b", r"\bphone\s+no\.?\b",
    r"\biban\b", r"\bsort code\b", r"\brouting number\b", r"\baccount number\b",
    r"\bcredit card\b", r"\bcvv\b",
    # WAS r"\bdiagnos\w*\b", and that was too broad (2026-11-07, the owner's Q7
    # ruling): an engineering question - "diagnose this test failure", "the
    # diagnostic logs" - should be allowed to escalate normally, while the
    # medical words stay private. So only the medical CONTEXTS match now: an
    # explicit "medical diagnosis", "diagnosed with <condition>", and the
    # owner's or a family member's possessive ("my diagnosis", "my son's
    # diagnosis"). The health words further down this list still catch a
    # condition named without the word "diagnosis" at all.
    r"\bmedical diagnos\w*",
    r"\bdiagnos(?:ed|is)\s+with\b",
    r"\b(?:my|our|his|her|their|your)\s+(?:[\w'-]+\s+)?diagnos(?:is|es)\b",
    r"\bprescription\b", r"\bbiopsy\b", r"\bmedical record\b",
    r"\bsalary\b", r"\bbank statement\b", r"\btax return\b",
    # The topics `[privacy] never_leaves_device` names, which this list did
    # not - rule 1 of the project is that email, files and money stay local,
    # and "summarise my inbox" or "what's on my calendar" matched nothing
    # here. Broad on purpose: a false match sends a question to the local
    # model (costs quality), a miss sends it to a cloud one (costs privacy).
    r"\be-?mails?\b", r"\binbox\w*\b", r"\bcalendars?\b",
    r"\bbank\w*\b", r"\binvoic\w*\b", r"\btax(?:es)?\b", r"\bfinanc\w*\b",
    r"\bmedical\b", r"\bfiles?\b",
    # The two private note stores. jarvis-framework.toml's [notes.joplin]
    # said this list matched "joplin"; it did not until 2026-09-24. A
    # question about them is answered where the notes search can run, and
    # that is only ever the local lane.
    r"\bjoplin\b", r"\bobsidian\b", r"\blogseq\b",
    # The same stores asked about WITHOUT naming the app: "search my vault",
    # "what does my wiki say", "what did I write in my notes", "my journal
    # from monday". Those four words are everyday English too - release
    # notes, the Wall Street Journal, a pole vault, a game's wiki - so they
    # count only as the owner's own: "my" or "our", with at most one word
    # between ("my Obsidian vault", "my meeting notes", "my bullet journal").
    r"\b(?:my|our)\s+(?:[\w'-]+\s+)?(?:vaults?|wikis?|notes?|journals?)\b",
    # Mood, mental health and crisis words (cutting-edge round 4, "Keep
    # distress off the cloud offer" - CLAUDE.md, 2026-09-27): missing here
    # entirely before this. A long distress message could otherwise reach
    # gate 6's "ask a cloud model?" offer - the wrong moment to ask, and
    # health is private under rule 1 regardless of whether jarvis_wellbeing's
    # own crisis() check also fires. Broad on purpose, as this list's own
    # comment already says: a false match here only keeps a question local,
    # which is the safe direction to err in.
    r"\bdepress\w*\b", r"\banxiet\w*\b", r"\bpanic attack\w*\b", r"\btherap\w*\b",
    r"\bself[- ]harm\w*\b", r"\bsuicid\w*\b",
    # Health conditions, pregnancy, medicines and more mental-health words
    # (security audit 2026-09-28 #4: "I have diabetes", "my blood pressure
    # is high", "I am pregnant", "my HIV test", "I take sertraline 50mg"
    # all matched nothing). The chatbot driver's last check and "Try the
    # cloud model" both lean on this list. Broad in the same safe direction
    # as the rest, but each word is one that means health in everyday
    # English: no bare "disease", "symptom", "dose", "aids", "period", "std",
    # "prep", "lithium" or "addicted" (plant diseases, "a dose of reality",
    # hearing aids, std::vector, meal prep, batteries, "addicted to this
    # song"), and "bipolar" only as the condition, not the transistor.
    r"\bdiabet\w*\b", r"\binsulin\b", r"\bcholesterol\b",
    r"\bblood (?:pressure|sugar|tests?|results?|work)\b", r"\bhypertension\b",
    r"\bhiv\b", r"\bstds\b", r"\bstis\b", r"\bsexually transmitted\b", r"\bherpes\b",
    r"\bhepatitis\b", r"\bcancer\w*\b", r"\btumou?rs?\b", r"\bchemo\w*\b",
    r"\basthma\w*\b", r"\bepilep\w*\b", r"\bdementia\b", r"\balzheimer\w*\b",
    r"\bparkinson'?s\b", r"\bmigraines?\b", r"\bheart (?:attack|condition|disease|failure)\b",
    r"\bpregnan\w*\b", r"\bmiscarr\w*\b", r"\babortion\w*\b", r"\bivf\b",
    r"\bfertility\b", r"\binfertil\w*\b", r"\bcontracepti\w*\b", r"\bbirth control\b",
    r"\bmenopaus\w*\b", r"\bmenstrua\w*\b",
    r"\bmedications?\b", r"\bmedicines?\b", r"\bpills\b", r"\bantidepressants?\b",
    r"\b\d+(?:\.\d+)?\s?mg\b", r"\bhospitals?\b",
    r"\b(?:my|our)\s+(?:[\w'-]+\s+)?(?:doctor|gp|dentist|psychiatrist|psychologist|"
    r"nurse|surgeon)\b",
    # Common medicines by name (antidepressants and anxiety medicines, ADHD,
    # diabetes and weight, heart, thyroid, pain and opioids, HIV).
    r"\b(?:sertraline|zoloft|fluoxetine|prozac|citalopram|escitalopram|lexapro|paroxetine|"
    r"venlafaxine|effexor|duloxetine|cymbalta|mirtazapine|bupropion|wellbutrin|"
    r"amitriptyline|quetiapine|seroquel|aripiprazole|abilify|olanzapine|"
    r"alprazolam|xanax|diazepam|valium|lorazepam|ativan|clonazepam|klonopin|"
    r"adderall|ritalin|methylphenidate|vyvanse|lisdexamfetamine|"
    r"metformin|ozempic|wegovy|semaglutide|mounjaro|tirzepatide|"
    r"statins?|atorvastatin|lipitor|simvastatin|lisinopril|amlodipine|"
    r"levothyroxine|warfarin|gabapentin|pregabalin|oxycodone|oxycontin|hydrocodone|"
    r"codeine|tramadol|morphine|fentanyl|opioids?|methadone|buprenorphine|suboxone|"
    r"truvada|antiretroviral\w*)\b",
    # Mental health beyond mood (the words above cover depression, anxiety,
    # therapy, self-harm and suicide).
    r"\bmental (?:health|illness)\b", r"\bpsychiatr\w*\b",
    r"\bcounsell?ing\b", r"\badhd\b", r"\badd\b(?=\s+(?:diagnosis|medication|meds))",
    r"\bautis\w*\b", r"\bocd\b", r"\bptsd\b", r"\btrauma\b",
    r"\bbipolar (?:disorder|depression)\b", r"\b(?:am|i'm|is|was|being)\s+bipolar\b",
    r"\bschizo\w*\b", r"\beating disorder\w*\b", r"\banorexi\w*\b", r"\bbulimi\w*\b",
    r"\baddictions?\b", r"\brehab\b", r"\balcoholi\w*\b",
    # A family matter the audit also found missing.
    r"\bdivorc\w*\b", r"\bcustody\b",
] + list(_crisis_terms())


def _term_pattern(term: str) -> str:
    """One `never_leaves_device` entry as a pattern for typed text:
    "files_on_disk" matches "files on disk", "files-on-disk" and itself, and a
    plural. Empty for an entry with no words in it."""
    words = [re.escape(w) for w in re.split(r"[\s_\-]+", str(term or "").strip()) if w]
    if not words:
        return ""
    return r"\b" + r"[\s_\-]?".join(words) + r"s?\b"


def _config_terms() -> tuple:
    raw = _cfg("privacy", "never_leaves_device", []) or []
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(t) for t in raw if isinstance(t, str) and t.strip())


class _PrivateMatcher:
    """The backstop: the words above AND the owner's own `[privacy]
    never_leaves_device` list in jarvis-framework.toml.

    That list said it was "kept in sync with the _PRIVATE regex in
    jarvis_router.py by hand", and it was not - nothing read it at all, so
    adding a word there changed nothing. Now it is read, on every check, so
    an edit to the config applies without a restart (the parse is cached by
    jarvis_framework and only redone when the file changes; the pattern is
    recompiled here only when the list does).

    Looks like a compiled regex to its callers - jarvis_hud calls
    `jarvis_router._PRIVATE.search(joined)` - so it has `.search`, and that
    is all it needs."""

    def __init__(self):
        self._terms: Optional[tuple] = None
        self._rx = re.compile("|".join(_PRIVATE_TERMS), re.I)

    def _current(self):
        terms = _config_terms()
        if terms != self._terms:
            extra = [p for p in (_term_pattern(t) for t in terms) if p]
            self._rx = re.compile("|".join(_PRIVATE_TERMS + extra), re.I)
            self._terms = terms
        return self._rx

    def search(self, text):
        return self._current().search(str(text or ""))

    @property
    def pattern(self) -> str:
        return self._current().pattern


_PRIVATE = _PrivateMatcher()


def is_private(text: str) -> bool:
    return bool(_PRIVATE.search(str(text or "")))


# --------------------------------------------------------------------------
#   What must never go to a cloud lane, part two: the literal secret itself
# --------------------------------------------------------------------------
#
# `is_private()` above matches the WORD for a secret ("what's my api key").
# It says nothing about a message that pastes the secret itself with no
# matching word nearby - a stack trace, a .env line, a curl command copied
# out of a terminal. That gap is real: nothing in this codebase scanned
# outbound content for a secret-SHAPED value before this, only for the
# topic words naming one.
#
# Shape-based and intentionally narrow. A false negative here still has
# is_private()'s keyword list and the taint/complexity/budget gates behind
# it; a false positive sends a genuinely safe question to the local model
# instead of the cloud, which costs quality, not privacy. That asymmetry is
# why this leans toward well-known, low-ambiguity SHAPES (a private key
# block, a provider's own documented token prefix, a JWT's three-dot
# structure) rather than a generic high-entropy-string heuristic, which
# flags far more and explains far less.
_SECRET_PATTERNS = [
    ("a private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    # AKIA is a long-lived key, ASIA a temporary one; both are keys.
    ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    # Classic tokens (ghp_ and friends) and fine-grained ones (github_pat_),
    # which GitHub has handed out by default since 2023 and the old pattern
    # missed (extraction research, Module 1).
    ("a GitHub token", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("a GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("a Stripe key", re.compile(r"\b(?:sk|rk)_(?:test|live)_[A-Za-z0-9]{16,}")),
    ("a Google OAuth token", re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}")),
    ("a Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    # Anthropic (sk-ant-api03-...) and today's OpenAI keys (sk-proj-...,
    # sk-svcacct-...) have dashes and underscores inside. The old pattern
    # allowed only letters and digits after "sk-", so it caught the 2023
    # OpenAI shape and missed both of those - the very keys the 2026-09-17
    # API-key rule made likely to be pasted here.
    ("an OpenAI or Anthropic API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("a Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("a JSON web token", re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("a bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}", re.I)),
    # A private calendar link (Google Calendar's "Secret address in iCal
    # format": .../calendar/ical/<calendar>/private-<32 hex>/basic.ics).
    # Whoever has it can read the calendar, so it is a password in all but
    # name - jarvis_calendar.py reads one from JARVIS_CALENDAR_ICS_SECRET_URL.
    ("a private calendar link", re.compile(r"/private-[0-9a-f]{16,}", re.I)),
    # A labelled assignment, not a bare high-entropy string: `token = <blob>`
    # is specific enough to act on; an unlabelled 20-character string is not
    # - it is also a hash, an id, a filename.
    ("a labelled secret value", re.compile(
        r"\b(?:api[_-]?key|secret|token|password|passwd)\s*[:=]\s*"
        r"['\"]?([A-Za-z0-9_\-/+]{16,})['\"]?", re.I)),
]


def _mask(excerpt: str) -> str:
    """First four characters and a length, never the excerpt itself. Enough
    for the owner to recognise WHICH secret this was without this function
    becoming a second place the secret is readable in full."""
    excerpt = str(excerpt)
    head = excerpt[:4]
    return f"{head}{'…' if len(excerpt) > 4 else ''} ({len(excerpt)} characters)"


def looks_like_a_secret(text: str) -> Optional[str]:
    """The kind of secret found (masked, human-readable), or None.

    Shape, not topic - see the module note above. Checked in declaration
    order and returns on the first match, so a message tripping several
    patterns is still reported once, with the earliest and most specific
    match winning.
    """
    s = str(text or "")
    for kind, pattern in _SECRET_PATTERNS:
        m = pattern.search(s)
        if m:
            return f"{kind} ({_mask(m.group(0))})"
    return None


# --------------------------------------------------------------------------
#   What only THIS machine can answer: its own repository, PRs, CI, defects
# --------------------------------------------------------------------------
#
# THE TWO MEASURED FAILURES THIS ANSWERS (2026-11-22, the live app). With the
# standing escalation switch on, "what do you know about your own GitHub
# repository" and "compare yourself to the Hermes agent" auto-escalated on
# complexity (`gate: "escalate"`, `where: "cloud"`), and the answers said "I
# don't have a GitHub repository of my own" and described the assistant as "Me
# (OpenAI model via API/ChatGPT)" - on a PC whose chosen provider is
# `deepseek_api`. A cloud lane carries no tools and no files, by rule 1, so a
# question about Atlas's own repository is not a question that lane can answer
# at all: it can only guess.
#
# So a question about THIS repository (by its own name, or by "my/your/this
# repo"), about the GitHub reads this PC owns (PRs, issues, CI), about its own
# defect register, or about the tools it has here, is answered on this machine
# BEFORE the complexity gate and whatever the switch says. Ruling 5.3 of the
# 2026-11-22 external review. A manual "Try the cloud model" click cannot lift
# it either: there is nothing on the other side to answer with. That is the
# same shape as the picture, screen and file gates - a capability refusal, not
# a privacy one - and it can only ever send the answer DOWNWARD, toward local.
#
# NARROW ON PURPOSE, and the narrowness is the part to keep. The question has
# to name a repository this PC owns, or ask about the tools or the defect
# register HERE. A question that merely mentions GitHub is an ordinary coding
# question and keeps every ordinary gate, the cloud one included: "how do I
# write a GitHub Action for my project" must still escalate. The negative cases
# are in `backend/test_router_self_repo.py`, which is the proof this is a test
# of the question and not a keyword list.
#
# The self phrases are deliberately the ones `jarvis_github.repo_from_words()`
# already resolves for the GitHub tools ("my repo", "my open PRs", "this
# repository", "Epic-Jarvis"), plus the second person, which is how the owner
# asks Atlas about itself ("your own GitHub repository"). "my project" is not
# one of them: the owner has more than one project, and a project is not a
# repository. Nor is "this issue" or "this PR": those are ordinary words for
# any codebase, so only "this repo(sitory)" carries the this-phrase.
_OWN_REPO_WORDS = re.compile(
    # This repository by name - bare, or the full owner/name form.
    r"\bepic[\s\-_]?jarvis\b"
    # "my repo", "my own GitHub repository", "your repositories", "our repos";
    # "this repo" / "this repository", and NOT "this issue" or "this PR".
    r"|\b(?:my|our|your)\s+(?:own\s+)?(?:github\s+)?(?:repositor(?:y|ies)|repos?)\b"
    r"|\bthis\s+(?:github\s+)?(?:repositor(?:y|ies)|repos?)\b"
    # "my open PRs", "your pull requests" - a PR is always a repository's.
    r"|\b(?:my|our|your)\s+(?:own\s+)?(?:open\s+)?(?:prs?|pull\s+requests?)\b"
    # Issues only when they are this PC's GitHub issues: "my issue is that
    # the build fails" is an ordinary coding question, not a repository one.
    r"|\b(?:my|our|your)\s+(?:own\s+)?(?:open|github)\s+issues?\b"
    # "Atlas's own repository" - the product's name for itself.
    r"|\batlas'?s?\s+(?:own\s+)?(?:github\s+)?(?:repositor(?:y|ies)|repos?)\b"
    # "your own GitHub" with the noun left off.
    r"|\b(?:my|our|your)\s+(?:own\s+)?github\b",
    re.I)

_OWN_TOOLS_WORDS = re.compile(
    # What this machine can do, which a cloud lane cannot: "your tools",
    # "your local tools", "what tools do you have", "the local tools".
    r"\byour\s+(?:own\s+)?(?:github\s+|local\s+)?tools?\b"
    r"|\blocal\s+tools?\b"
    r"|\bwhat\s+tools\s+(?:do\s+you\s+have|have\s+you\s+got|are\s+available)\b"
    # The three GitHub reads this PC owns, by name. Naming one is the
    # strongest signal there is that the local tool lane is the answer.
    r"|\bgithub_(?:list|ci_status|pr_detail)\b"
    # This PC's own CI, and the defect register - this project's own artefact.
    r"|\byour\s+(?:own\s+)?(?:ci|defects?)\b"
    r"|\bdefect\s+register\b"
    r"|\byour\s+(?:own\s+)?github\s+(?:ci|actions?|workflows?|checks?)\b",
    re.I)


def asks_about_own_repo(text) -> bool:
    """Is this question about what only THIS machine can answer?

    True for a question about Atlas's own repository (its PRs, issues, CI),
    its own defect register, or the tools it has on this PC; False for
    everything else, including an ordinary coding question that merely
    mentions GitHub. `choose()` reads this at gate 3b and nowhere else, and
    the module note above says why. Never raises: a non-string is simply not
    a self-repo question.
    """
    low = " ".join(str(text or "").replace("\u2019", "'").split())
    if not low:
        return False
    return bool(_OWN_REPO_WORDS.search(low) or _OWN_TOOLS_WORDS.search(low))


# --------------------------------------------------------------------------
#   The budget
# --------------------------------------------------------------------------

@dataclass
class Budget:
    """Cloud requests per minute and per day, counted on disk.

    On disk rather than in memory because the limit is meant to survive a
    restart. A per-process counter resets every time the backend is restarted,
    which on a desktop is several times a day - and a daily cap you can clear
    by restarting is not a cap.
    """

    per_minute: int = 15
    per_day: int = 800
    minute_hits: list = field(default_factory=list)
    day_hits: list = field(default_factory=list)
    path: Optional[Path] = None

    _lock = threading.RLock()

    @classmethod
    def _store_path(cls) -> Path:
        base = Path(fw.CONFIG_DIR) if fw is not None else Path.home() / ".openjarvis"
        return base / "budget.json"

    @classmethod
    def load(cls) -> "Budget":
        b = cls(per_minute=int(_cfg("budget", "requests_per_minute", 15) or 15),
                per_day=int(_cfg("budget", "requests_per_day", 800) or 800),
                path=cls._store_path())
        try:
            raw = json.loads(b.path.read_text(encoding="utf-8"))
            # Each list separately: one corrupt element in `minute` used to
            # discard a perfectly good `day` array, and `day` is the cap that
            # matters.
            for key, dest in (("minute", "minute_hits"), ("day", "day_hits")):
                try:
                    setattr(b, dest, [float(x) for x in (raw.get(key) or [])])
                except (TypeError, ValueError):
                    continue
        except Exception:
            # A missing or corrupt budget file means "no cloud calls recorded",
            # which is the permissive direction - but the alternative is
            # refusing every cloud turn because a JSON file has a stray comma,
            # and the cap is a cost control, not a safety control.
            pass
        b._prune()
        return b

    def _prune(self) -> None:
        now = time.time()
        self.minute_hits = [t for t in self.minute_hits if now - t < 60]
        self.day_hits = [t for t in self.day_hits if now - t < 86400]

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"minute": self.minute_hits,
                                       "day": self.day_hits}), encoding="utf-8")
            tmp.replace(self.path)          # atomic; a torn file reads as empty
        except Exception:
            pass

    def spend(self, n: int = 1) -> None:
        """Record cloud requests, re-reading the file first.

        jarvis_hud calls Budget.load() PER REQUEST on a threading server, so
        several Budget objects exist at once, each holding a snapshot. Without
        the re-read, two of them each spending five wrote five to disk instead
        of ten - half the day's usage lost, and a cap that does not cap.
        """
        with self._lock:
            now = time.time()
            fresh = {"minute": [], "day": []}
            if self.path is not None:
                try:
                    fresh = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    fresh = {"minute": list(self.minute_hits),
                             "day": list(self.day_hits)}
            try:
                self.minute_hits = [float(x) for x in fresh.get("minute", [])]
                self.day_hits = [float(x) for x in fresh.get("day", [])]
            except (TypeError, ValueError):
                pass
            for _ in range(max(1, n)):
                self.minute_hits.append(now)
                self.day_hits.append(now)
            self._prune()
            self.save()

    def minute_exceeded(self) -> bool:
        self._prune()
        return len(self.minute_hits) >= self.per_minute

    def day_exceeded(self) -> bool:
        self._prune()
        return len(self.day_hits) >= self.per_day

    def allows_cloud(self) -> bool:
        return not (self.minute_exceeded() or self.day_exceeded())

    def status(self) -> dict:
        self._prune()
        return {
            "per_minute": self.per_minute,
            "per_day": self.per_day,
            "used_this_minute": len(self.minute_hits),
            "used_today": len(self.day_hits),
            "minute_exceeded": self.minute_exceeded(),
            "day_exceeded": self.day_exceeded(),
            "cloud_allowed": self.allows_cloud(),
        }


# --------------------------------------------------------------------------
#   The decision
# --------------------------------------------------------------------------

@dataclass
class Decision:
    lane: str
    reason: str
    gate: str
    complexity: float = 0.0
    inject_memory: bool = False
    tainted: bool = False
    #: A cloud lane that COULD answer this turn, offered - never taken - when
    #: the owner has not said yes for this one question (gate "offer").
    #: Empty whenever a privacy gate kept the turn local: those are never
    #: offered to the cloud at all.
    offer: str = ""
    #: True when the turn went to the cloud WITHOUT a per-question click -
    #: because the PC's own standing switch is on (`escalate-cloud.json`) or
    #: because the owner asked for the cloud in the message itself ("send this
    #: to the cloud"). The apps say so on the turn, and a cloud answer with no
    #: usable text is handled differently for these: nothing the owner did not
    #: ask for is ever presented as an answer. See jarvis_chatbot_api's
    #: CloudAnswer. False on every local turn and on the per-turn "yes".
    auto: bool = False
    #: Set ONLY when this turn's local model could not run on the lane it will
    #: really use and the model that lane is configured for answered instead
    #: (2026-11-18): one entry per replacement, in the shape
    #: `{"lane": <asked for>, "model": <really used>, "code":
    #: "model_cannot_run_on_this_lane", "why": <the refusal, words>}`. The
    #: route detail already carries the field of that name when the HUD steps a
    #: cloud lane down, so it is the same key and a new reader (or the owner
    #: reading X-Jarvis-Route) sees one list either way. `as_dict()` OMITS it
    #: when it is empty, so an ordinary turn's route detail is byte for byte
    #: what it was before this field existed.
    degraded_from: Optional[list] = None

    def as_dict(self) -> dict:
        detail = asdict(self)
        if not detail.get("degraded_from"):
            detail.pop("degraded_from", None)
        return detail


def is_local_lane(lane: str, local_model: str = "") -> bool:
    """Is this lane running on this machine?

    Name-based, and that is a weakness worth stating: a lane called
    "jarvis-local" that someone pointed at a remote Ollama would read as local
    here. backend/README.md already records the same hazard for OLLAMA_URL -
    "the local model is ALSO egress if OLLAMA_URL does not point at this
    machine" - and the loopback assertion for that lives with the caller that
    opens the socket, which is the only place it can be checked honestly.
    """
    lane = str(lane or "")
    # Ollama's own cloud models ("gpt-oss:120b-cloud", "glm-4.6:cloud") are
    # run THROUGH the local Ollama but answered on ollama.com. The address is
    # 127.0.0.1 and the name can be the configured local model, so neither
    # check below can see it - only the name's "cloud" tag can. Such a lane
    # is never local, whatever else it matches, so memory is never injected
    # into it. Found by the memory-safety red team, 2026-09-24.
    if is_remote_model(lane):
        return False
    if local_model and lane == local_model:
        return True
    return bool(re.search(r"local|jarvis-primary|ollama", lane, re.I))


# The tag Ollama gives a model it runs on its own servers: ":cloud" or a
# size followed by "-cloud" ("120b-cloud"). Matched on the tag only, so a
# local model whose NAME merely contains "cloud" is not caught by accident.
_REMOTE_TAG = re.compile(r":(?:[^:/]*-)?cloud$", re.I)


def is_remote_model(name: str) -> bool:
    """Is this an Ollama model that is answered off this machine?"""
    return bool(_REMOTE_TAG.search(str(name or "").strip()))


# --------------------------------------------------------------------------
#   Which model may run on the lane this turn will use (2026-11-18)
# --------------------------------------------------------------------------
#
# THE DEFECT THIS EXISTS FOR, measured live on the owner's PC the night of
# 2026-11-17/18. `~/.openjarvis/model-state.json` said the everyday model was
# `qwen3-coder-30b-a3b-ud-q3-k-xl` - the Coding preset's pooled three-card
# model, written there by the live install's own preset apply (the repository
# half of that is PR #1361). A private question then routed CORRECTLY to the
# local lane and got NO ANSWER AT ALL:
#
#     jarvis_agent.local_model_refusal refused to load a pooled model on the
#     one-card lane, in the honest words the owner was shown, and NOTHING had
#     asked whether the model the router picked could run where it picked it.
#
# The refusal is right and stays right (the spill it prevents is real). The
# missing half was this: a local turn must always be answerable, so when the
# SAVED model is one this lane cannot hold, the turn is answered by the model
# the lane itself is configured for - said out loud in the route detail, never
# silently.
#
# NOTHING HERE DECIDES WHICH MODELS ARE POOLED, OR WHICH LANES MAY HOLD THEM.
# `jarvis_presets.is_pooled_model` is the one hand-written predicate for the
# first question, and `jarvis_agent.local_model_refusal` is the one place that
# turns it into a sentence; `jarvis_agent._pooled_model_name` is the same
# question as the refusal's own check asks it, size families included. So this
# DELEGATES to the refusal and asks it whether the replacement fits too, rather
# than keeping a second list that could drift from it in the direction that
# matters (a name this file thought was safe). The ports/models themselves are
# read from `jarvis_model_lanes` and `jarvis_big_coder`, which own them.
#
# ONLY THE ONE CLASS OF REFUSAL A DIFFERENT MODEL CAN FIX IS TREATED. A cloud
# model named as the local one, or an OLLAMA_URL that points at another
# machine, are refused exactly as before: neither is answered by loading some
# other model on a lane that is not even this PC.


def _default_local_url() -> str:
    """This PC's own default Ollama address: `OLLAMA_URL`, or Ollama's default.

    It asks `jarvis_models.ollama_url_on_this_pc()` - the ONE resolver every
    shipped module uses since PR #1330 - rather than reading the environment
    here: that resolver refuses a host that is not this PC, and
    `backend/test_ollama_url_routing.py` fails any SECOND direct read of
    `OLLAMA_URL` in the base, in whatever module (its own docstring explains
    why a checked address is not a constant). The lane module's own default is
    the fallback for a backend too old to have the resolver.
    """
    try:
        import jarvis_models
        url = str(jarvis_models.ollama_url_on_this_pc() or "").strip().rstrip("/")
        if url:
            return url
    except Exception:
        pass
    try:
        import jarvis_model_lanes
        return str(jarvis_model_lanes.DEFAULT_OLLAMA_URL)
    except Exception:
        return "http://127.0.0.1:11434"


def local_lane_url(default: str = "") -> str:
    """The address a LOCAL turn on this PC will be sent to.

    The HUD picks it from the applied preset (`jarvis_presets.active_chat_url`:
    the named lane, normally 11436, or the on-demand pooled lane at 11450),
    falling back to the checked `OLLAMA_URL` resolver
    (`jarvis_models.ollama_url_on_this_pc`). Asking the same function here is what makes
    "the lane it will run on" a measured fact rather than an assumption - and
    it also picks up that function's own repair of a persisted pointer at the
    pooled port when nothing is listening there (a read, one TCP connect at
    most, and at most one small file write; it never starts a lane and never
    asks a model anything). Never raises.
    """
    base = str(default or "").strip().rstrip("/") or _default_local_url()
    try:
        import jarvis_presets
        return str(jarvis_presets.active_chat_url(base) or base).strip().rstrip("/")
    except Exception:
        return base


def lane_port(lane_url) -> Optional[int]:
    """The loopback port a lane address names, or None. The lane module's own."""
    try:
        import jarvis_model_lanes
        return jarvis_model_lanes.port_of(str(lane_url or ""))
    except Exception:
        return None


def _configured_everyday_model() -> str:
    """`[intelligence] default_model` from the owner's `config.toml`, or "".

    The model the HUD calls "the everyday model" when no approved switch has
    overridden it (`jarvis_hud` reads this very key as its own default). Read
    here so the fallback is the model the PC is CONFIGURED for, not one this
    file remembers. Never raises.
    """
    try:
        import tomllib
    except Exception:                                            # pragma: no cover
        try:
            import tomli as tomllib                              # type: ignore
        except Exception:
            return ""
    try:
        base = Path(fw.CONFIG_DIR) if fw is not None else Path.home() / ".openjarvis"
    except Exception:
        base = Path.home() / ".openjarvis"
    try:
        data = tomllib.loads((base / "config.toml").read_text(encoding="utf-8"))
    except Exception:
        return ""
    row = data.get("intelligence") if isinstance(data, dict) else None
    if not isinstance(row, dict):
        return ""
    return str(row.get("default_model") or "").strip()


def lane_configured_model(lane_url: str = "") -> str:
    """The model the local lane at `lane_url` is configured for, or "".

    The lane's own tables, in the order they can answer:

      1. `jarvis_big_coder.LANES` - the owner's live lanes, each row naming the
         model that lane MUST come back holding (that table's own words:
         "exactly as they must come back"), matched by the lane's port;
      2. `[intelligence] default_model` in the owner's `config.toml` - what
         "the everyday model" is configured to be, which is the key the HUD
         itself falls back to when no switch is recorded;
      3. the everyday lane's own row in `jarvis_big_coder.LANES`, for an
         address no row names - which is what Ollama's plain default port,
         11434, is on this PC.

    No model name is typed here; every one is read. The caller still asks the
    refusal whether the answer fits (see `local_model_fallback`).
    """
    port = lane_port(lane_url)
    try:
        import jarvis_big_coder as big
        rows = list(getattr(big, "LANES", ()) or ())
    except Exception:
        rows = []
    if port:
        for row in rows:
            try:
                if int(getattr(row, "port", 0) or 0) != int(port):
                    continue
            except Exception:
                continue
            model = str(getattr(row, "model", "") or "").strip()
            if model:
                return model
    model = _configured_everyday_model()
    if model:
        return model
    for row in rows:
        model = str(getattr(row, "model", "") or "").strip()
        if model:
            return model
    return ""


def model_refusal_here(model: str, lane_url: str = "") -> str:
    """Why the local turn would refuse `model` at `lane_url`, in words, or "".

    The ONE authority on that question is `jarvis_agent.local_model_refusal`:
    it is what `run_local_turn` itself calls before a request is sent, so a
    router that agrees with it can never hand a turn over that will then be
    refused. This asks it rather than re-deriving its three refusals. A router
    with no `jarvis_agent` beside it answers "" (nothing refused): that is a
    backend too old to have the module the whole local turn runs through, and
    inventing a refusal there would be worse than staying as it was.
    """
    lane_url = (str(lane_url or "").strip().rstrip("/") or local_lane_url())
    try:
        import jarvis_agent
        return str(jarvis_agent.local_model_refusal(lane_url, str(model or "")) or "")
    except Exception:
        return ""


#: The `code` value `Decision.degraded_from` carries for a model this lane
#: cannot hold. Stable, short, and never the refusal sentence itself (that is
#: `why`, whose words belong to jarvis_agent).
MODEL_CANNOT_RUN_HERE = "model_cannot_run_on_this_lane"


def local_model_fallback(model: str, lane_url: str = "") -> dict:
    """The lane's own model when `model` cannot run on this lane; {} otherwise.

    The returned dict is the entry the route detail carries under
    `degraded_from`::

        {"lane":  <the model that was asked for>,
         "model": <the model that will really run>,
         "code":  "model_cannot_run_on_this_lane",
         "why":   <the refusal, in jarvis_agent's own words>}

    {} means "nothing to do", and it is the answer in three cases:

      * the lane can hold `model` - the refusal says nothing;
      * the refusal is not the one a different MODEL can fix (a cloud model
        named as the local model, or a lane on another machine) - substituting
        a model there would answer a question the refusal is not asking;
      * no configured model for that lane fits it either - then the honest
        refusal stands rather than a second invalid choice being made.

    Never raises and never sends anything: no model is loaded, no lane started.
    """
    wanted = str(model or "").strip()
    if not wanted:
        return {}
    lane_url = str(lane_url or "").strip().rstrip("/") or local_lane_url()
    try:
        import jarvis_agent
    except Exception:
        return {}
    refusal = model_refusal_here(wanted, lane_url)
    if not refusal:
        return {}
    # THE REFUSAL'S OWN CHECK FOR THE ONE FIXABLE CLASS. `_pooled_model_name`
    # is what `local_model_refusal` used to produce this sentence; asking the
    # same helper keeps this in step with the refusal including the `30b`/`27b`
    # size families, so a pooled model this repository has never seen is
    # treated exactly as the refusal treats it.
    try:
        if not jarvis_agent._pooled_model_name(wanted):
            return {}
    except Exception:
        return {}
    usable = lane_configured_model(lane_url)
    if not usable or usable == wanted:
        return {}
    if model_refusal_here(usable, lane_url):
        return {}
    return {"lane": wanted, "model": usable, "code": MODEL_CANNOT_RUN_HERE,
            "why": refusal}


#: choose()'s reason when the configured local model is a cloud one.
CLOUD_MODEL_AS_LOCAL = (
    "refused: the everyday model {model} is one of Ollama's cloud models, answered "
    "on ollama.com, not on this PC, so nothing is sent to it. Switch the everyday "
    "model to one that runs on this PC; a cloud model belongs in a cloud lane, "
    "where Jarvis asks you before each question")


# ==========================================================================
#   ONE cloud lane, and who may say yes to it (2026-10-27)
# ==========================================================================
#
# THE THREE NAMES BECOME ONE. Until 2026-10-27 the caller's lane list came from
# `litellm-proxy.yaml` - the config of a LiteLLM proxy that is not installed and
# never was - and it named `jarvis-escalate`, `jarvis-critic` and `jarvis-bulk`.
# `jarvis_chatbot_api.CLOUD_LANES` mapped all three at one service, so the
# difference between them was a label and a model name, never a route. The
# owner's decision of 2026-10-27 keeps ONE (`jarvis-escalate`) and drops the
# other two, and this is where that becomes true for every caller: whatever
# list arrives, only the one name is a cloud lane, and a list holding none of it
# is an EMPTY list - gate "unavailable" - never a substituted name.
#
# It has to be here rather than in each caller's own file, because the deletion
# of the two names must not leave a hole: an empty lane list is exactly the
# "no cloud lane was offered" answer, and a stray name from an older config must
# not quietly become "the cloud".
CLOUD_LANE = "jarvis-escalate"


def cloud_lanes(lanes) -> list:
    """The cloud lanes in `lanes`: at most ONE, the name above.

    Everything else in the list is dropped. An empty answer is the honest
    answer for a PC where nothing named a cloud lane, and `choose()` turns it
    into gate "unavailable" - which is what stops the removal of the two old
    names from silently killing escalation everywhere.
    """
    return [CLOUD_LANE] if CLOUD_LANE in [str(n or "") for n in (lanes or [])] else []


def standing_escalation() -> bool:
    """Is the PC's own standing cloud switch ON? (`escalate-cloud.json`)

    THE ONLY SOURCE OF A STANDING YES, and that is the point of it being here:
    no request body, no header and no client flag can reach this. The owner
    turns it on in the Presets menu, which raises ONE `change_own_config` card
    (jarvis_presets.cloud_escalate); turning it off is immediate. Absent,
    unreadable, corrupt, or a `jarvis_presets.py` that is not there all read as
    OFF - a privacy switch fails closed.

    docs/DECISIONS.md's 2026-10-27 entry records that this reverses the
    "no standing grant" rule of 2026-09-24; `choose()`'s own docstring still
    describes the rule the gates follow, which has not changed.
    """
    try:
        import jarvis_presets
    except Exception:
        return False
    try:
        return bool(jarvis_presets.escalate_on())
    except Exception:
        return False


#: The phrases that count as the owner asking for the cloud IN THE MESSAGE.
#: Deliberately narrow and fixed: a false positive here would send words the
#: owner did not choose, so each one has to name the cloud or the escalation
#: outright. Matched against the NEWEST message only, lower-cased, and only
#: ever read at gate 6 - after every privacy gate has had its chance to answer
#: local, so this can never lift a gate that already refused.
ESCALATE_PHRASES = (
    "escalate this",
    "escalate it",
    "use the cloud for this",
    "use the cloud",
    "send this to the cloud",
    "send it to the cloud",
    "ask the cloud",
    "the bigger model for this",
    "use the bigger model",
)


def explicit_escalation(query) -> bool:
    """Did the owner ask for the cloud in the message itself?

    FOR ONE TURN ONLY: nothing is stored, nothing is remembered, and the next
    message has to ask again. `choose()` reads it at gate 6 and nowhere else,
    so a Lockdown, a tainted conversation, a picture, the screen's words, a
    private question or a pasted secret all still answer local - the phrase can
    only turn "offer" into "escalate", never a refusal into an answer.
    """
    text = str(query or "").lower()
    if not text:
        return False
    return any(phrase in text for phrase in ESCALATE_PHRASES)


def complexity(query: str) -> float:
    """A rough 0-1 score. Longer, more clause-heavy questions score higher.

    INFERRED - only the threshold survived (`[routing] complexity_threshold =
    0.40`, "enforced today by choose() gate 2"). The scale is therefore known
    to be 0-1 with 0.40 meaning "hard enough to consider escalating", and the
    formula below is this file's, not the original's. It is deliberately dull:
    a clever scorer that nobody can predict makes routing feel random.
    """
    q = " ".join(str(query or "").split())
    if not q:
        return 0.0
    words = len(q.split())
    score = min(words / 120.0, 0.6)
    score += 0.1 * min(q.count(",") + q.count(";"), 2)
    if re.search(r"\b(why|how|compare|explain|design|prove|trade-?off)\b", q, re.I):
        score += 0.15
    if re.search(r"\b(step by step|in detail|thoroughly)\b", q, re.I):
        score += 0.1
    return round(min(score, 1.0), 3)


#: How far the answer budget may move from the configured one, as a share of
#: it. The floor is 0.75 and the cap 2.0: a hard question may be answered at
#: up to twice the configured length, an easy one at no less than
#: three-quarters. Both bounds exist because the model's room is shared:
#: `jarvis_agent.budget()` subtracts this number from the prompt's room, so
#: an unbounded raise would silently squeeze the conversation out.
TOKEN_FLOOR_SHARE = 0.75
TOKEN_CAP_SHARE = 2.0


def tokens_for_turn(query: str, base: int, *, cap: int = 0) -> int:
    """`base` (the configured answer length) adjusted by how hard the question
    looks - the idea from OpenJarvis's `adjust_tokens_for_model` in its
    complexity router (Apache-2.0); the numbers and the bounds are ours.

    Deliberately narrow, and it can never hurt the prompt:

    * the result is always between ``max(512, 0.75 * base)`` and
      ``min(2 * base, cap or 2 * base)``;
    * a low complexity never takes the budget below the floor, and a high one
      never takes it above the cap, so the caller's own limit still wins;
    * anything unreadable returns `base` unchanged - this is a tuning knob,
      never a reason for a turn to fail.
    """
    try:
        base = int(base)
    except (TypeError, ValueError):
        return 1024
    if base <= 0:
        return 1024
    lo = max(512, int(base * TOKEN_FLOOR_SHARE))
    hi = int(base * TOKEN_CAP_SHARE)
    if cap and cap > 0:
        hi = min(hi, int(cap))
    if hi < lo:
        hi = lo
    try:
        c = complexity(query)
    except Exception:
        return base
    # 0.40 is the shipped `[routing] complexity_threshold`: below it the
    # question is ordinary and keeps the configured length; above it the
    # answer grows, in proportion, up to the cap.
    if c <= 0.40:
        return max(lo, min(base, hi))
    grown = int(base * (1.0 + (c - 0.40) / 0.60))
    return max(lo, min(grown, hi))


# ============================================================================
#   The 2-strike local-failure fallback for coding turns (2026-11-19)
# ============================================================================
#
# THE RULING (external review, 2026-11-19, 6.1): keep the deterministic
# `complexity >= 0.40` pre-gate as Stage 1, and PAIR it with a 2-strike /
# local-failure fallback for coding tasks - do NOT replace it with raw
# log-probs. In this codebase that means: when a CODING turn has failed on this
# PC TWICE in the SAME conversation (the local model returned no usable answer,
# or the tool path failed), the third attempt may reach the cloud even though
# its complexity score is under the threshold - and it still has to pass EVERY
# safety gate choose() runs, every time, in the same order.
#
# WHY A COUNTER, when complexity is the pre-gate. A coding request can be long
# on code and short on prose ("fix this" plus a stack trace), so its score can
# sit under 0.40 while the local model demonstrably cannot answer it. Two
# failed local attempts are direct evidence of exactly that, and they have
# already cost the owner two turns - so the third may spend a little money
# instead of failing a third time. TWO, not one: one failure can be a transient
# load or a cancelled request, and a fallback that fires on it would spend
# money on every hiccup.
#
# WHAT IT DOES NOT DO. It never bypasses a gate: the cloud-model, no-lane,
# Lockdown, taint, image, file, screen, private, pasted-secret and budget gates
# all still run, and it still needs the owner's yes / this PC's standing switch
# at gate 6 - the fallback replaces the COMPLEXITY stage only. A private turn
# with two strikes still answers here.
#
# KEYING AND RESET. Strikes are kept per CONVERSATION, in memory, keyed by the
# conversation id the caller records against ("" when it has none). A NEW
# conversation is a NEW key, so it starts at zero by construction;
# `reset_local_failures()` forgets one explicitly for a caller that reuses an
# id. The store is bounded and drops the oldest conversation first, so a
# long-lived HUD cannot grow it without limit. It holds counts only - never a
# word of the conversation.
STRIKES_FOR_FALLBACK = 2
_STRIKES_MAX_CONVERSATIONS = 128
_LOCAL_FAILURES: dict = {}
_LOCAL_FAILURES_LOCK = threading.Lock()


def _conversation_key(conversation) -> str:
    """The counter key for one conversation: printable, short, never a secret."""
    text = "".join(c if c.isprintable() else " " for c in str(conversation or ""))
    return " ".join(text.split())[:120]


def local_failure_strikes(conversation: str = "") -> int:
    """How many local failures have been recorded for one conversation."""
    with _LOCAL_FAILURES_LOCK:
        return int(_LOCAL_FAILURES.get(_conversation_key(conversation), 0) or 0)


def note_local_failure(conversation: str = "") -> int:
    """Record ONE local failure for a conversation, and return the new count.

    ONE failure is a local attempt that produced no usable answer - the local
    model failed, or the tool path failed. The caller is whatever saw the
    failure (the relay after a local attempt that produced nothing usable);
    `choose()` reads the count for a coding turn only, and only after every
    safety gate has run. Nothing here decides anything, sends anything, or
    keeps any of the owner's words.
    """
    key = _conversation_key(conversation)
    with _LOCAL_FAILURES_LOCK:
        count = int(_LOCAL_FAILURES.pop(key, 0) or 0) + 1
        _LOCAL_FAILURES[key] = count
        while len(_LOCAL_FAILURES) > _STRIKES_MAX_CONVERSATIONS:
            _LOCAL_FAILURES.pop(next(iter(_LOCAL_FAILURES)), None)
    return count


def reset_local_failures(conversation: str = "") -> None:
    """Forget a conversation's local-failure count.

    A genuinely new conversation needs no call - it is a new key and starts at
    zero. This is for a caller that REUSES one conversation id, and for a
    caller that knows the conversation ended.
    """
    with _LOCAL_FAILURES_LOCK:
        _LOCAL_FAILURES.pop(_conversation_key(conversation), None)


#: The words the CODING preset itself already uses to recognise coding work
#: (`jarvis_presets.by_id("coding").words`, read lazily so this module imports
#: with no presets module at all). Only the fallback when that module cannot
#: answer.
_CODING_WORDS = ("code", "coding", "program", "debug", "bug", "python", "kotlin",
                 "script", "compile", "repository", "git", "android", "app")


def is_coding_turn(query: str, *, local_model: str = "",
                   coding: Optional[bool] = None) -> bool:
    """Is this turn a coding one? The ONE coding definition, shared by the
    2-strike fallback here and by jarvis_chatbot_api's deep-answer tier.

    THREE EXISTING SIGNALS, in order, and no new classifier:
      * `coding` when the caller has its own answer (the tool in play - the
        relay knows which tool set is loaded - and it wins, because a caller
        that knows must not be overruled by a word match);
      * the LOCAL MODEL'S NAME: a coder model loaded as the everyday model
        ("qwen3-coder-...") means the owner is working in code;
      * the Coding preset's own trigger words and applied state, which
        `jarvis_presets` already owns for /api/work/recommend.
    An unreadable answer reads as False: this only ever ADDS a second chance to
    a coding turn, so a missed coding turn keeps the stage-1 gate - the safe
    direction.
    """
    if coding is not None:
        return bool(coding)
    if local_model and re.search(r"cod(?:e|er|ing)", str(local_model), re.I):
        return True
    text = " ".join(str(query or "").lower().split())
    if not text:
        return False
    try:
        import jarvis_presets as P
        if str(getattr(P, "choice", lambda: None)() or "") == "coding":
            return True
        row = P.by_id("coding") if hasattr(P, "by_id") else None
        words = tuple(getattr(row, "words", ()) or ()) or _CODING_WORDS
    except Exception:
        words = _CODING_WORDS
    # WHOLE WORDS only: the preset's own trigger list holds "app" and "git",
    # and a plain substring test reads "happens" or "digit" as coding. A word
    # misses the plural "apps"; erring toward NOT deep is the safe direction
    # (the turn keeps the standard ceiling and Stage 1).
    pattern = (r"(?<![A-Za-z0-9])(?:"
               + "|".join(re.escape(str(w).lower()) for w in words if str(w).strip())
               + r")(?![A-Za-z0-9])")
    try:
        return bool(re.search(pattern, text))
    except re.error:
        return False


def lockdown_on() -> bool:
    """Is Lockdown on (jarvis_asks_first.py, 2026-09-28)? False without that
    module - the feature is not there. Its own reading fails closed (a
    damaged file reads as on); anything else going wrong here reads as ON
    too: a cloud lane is never the answer to "could not tell"."""
    try:
        import jarvis_asks_first
    except Exception:
        return False
    try:
        return bool(jarvis_asks_first.lockdown_on())
    except Exception:
        return True


def choose(query: str, local_model: str = "", lanes: Optional[list] = None,
           has_image: bool = False, conversation_tainted: bool = False,
           budget: Optional[Budget] = None, tainted: Optional[bool] = None,
           owner_said_yes: bool = False, has_screen: bool = False,
           has_file: bool = False, conversation: str = "",
           coding: Optional[bool] = None,
           **_extra) -> Decision:
    """Which lane answers this turn.

    Ten gates, in this order, and the order is the policy. Each one can only
    send the answer DOWNWARD toward local - none of them can escalate past a
    gate that already refused.

     -1. the local model is itself  -> gate "cloud_model": refused, and
         one of Ollama's cloud models    run_local_turn sends it nothing
      0. no cloud lanes offered      -> local
     0b. Lockdown is on              -> local, unconditionally, no offer
      1. the conversation is tainted -> local, unconditionally
     1b. the turn carries a picture  -> local, unconditionally
         or the screen's words
         or a FILE the owner attached (2026-10-29)
      2. private content matched     -> local
      3. a real secret was found     -> local, unconditionally
      3b. the question is about Atlas's own repository, its PRs, CI, defects
          or the tools it has here   -> local, BEFORE the complexity gate
          (gate "self_repo", 2026-11-22)
      4. not complex enough          -> local, UNLESS the 2-strike fallback
                                        below applies to a coding turn
      5. budget spent                -> local
      6. the owner has not said yes  -> local, with the cloud lane OFFERED
         for THIS question
      otherwise                      -> the first cloud lane

    STAGE 1 AND THE 2-STRIKE PAIRING (2026-11-19, external review ruling 6.1).
    Gate 4 is still the deterministic `complexity >= threshold` pre-gate - it
    was not replaced by anything statistical. It is now PAIRED with a fallback
    that only ever ADDS a way out for one narrow, measured case: a CODING turn
    whose local attempts have failed TWICE in the SAME conversation
    (`note_local_failure(conversation)`, read here) may pass gate 4 even under
    the threshold, because two failures are direct evidence the local model
    cannot answer it. "Coding" is the existing signal
    (`is_coding_turn`: the caller's tool-in-play answer, a coder model's name,
    or the Coding preset's own trigger words). It replaces NOTHING: every gate
    above gate 4 and both gates after it still run, the order is unchanged, and
    gate 6 still demands the owner's yes / this PC's standing switch. So a
    private coding turn with two failures still answers here, and a turn with
    one failure keeps the stage-1 gate. The count is keyed by `conversation`,
    so a new conversation starts at zero; it holds counts only, never words.

    Gates 1b, 2, 3 and 4 all come BEFORE the budget and the offer, and that is
    the policy rather than an accident: there is no budget to spend and no offer
    to make on a turn that can never leave this PC. `has_file` (2026-10-29) sits
    beside the picture and the screen's words for the same reason they do - a
    file's words can be anything - and because `cloud-one-turn.patch` keeps
    exactly the NEWEST user turn, which is where those words ride.

    GATE 6, AND WHY THE DEFAULT IS "NO" (the owner's decision, 2026-09-24).
    docs/ARCHITECTURE.md says cloud use is "per use, with permission ...
    and asks. No standing grant." This function used to decide on its own:
    any long, non-private question went to the first cloud lane, and the
    owner saw a Cloud badge afterwards. Now a turn reaches a cloud lane only
    when one of three things says so, and even then gates 0-5 still apply, so
    a yes can never carry a private or tainted turn out:
      * `owner_said_yes=True` - the owner's own yes for this one question;
      * the PC's own standing switch (`standing_escalation()`, the checkbox in
        the Presets menu). The owner CHANGED the "no standing grant" rule on
        2026-10-27 - docs/DECISIONS.md records it - and the switch is a file on
        this PC raised by one `change_own_config` card. No request body, no
        header and no client flag is consulted for it, so a stale page or a
        phone cannot make a standing decision this PC has not made;
      * the owner asking for the cloud in the message itself
        (`explicit_escalation`), for THAT TURN only - nothing is stored.
    Without any of them the turn is answered here and `offer` names the lane
    that could have answered, so an app can ask. Nothing learned, remembered
    or configured sets the per-question yes.
    The last two are "automatic" - no click - and the decision says so
    (`Decision.auto`), so a cloud answer with no usable text in it is never
    dressed up as an answer. See jarvis_chatbot_api.CloudAnswer.

    Gate 2 (`is_private`) catches the WORD for a secret ("what's my api
    key"); gate 3 (`looks_like_a_secret`) catches the secret ITSELF pasted
    with no matching word nearby - a stack trace, a .env line, a token
    copied out of a terminal. Neither replaces the other.

    THE PARAMETER IS `conversation_tainted`, AND THAT IS NOT A DETAIL.

    This was called `tainted`, with `**_extra` to absorb anything unexpected.
    jarvis_hud.py:1714 passes `conversation_tainted=tainted`, so `**_extra`
    silently ate it and gate 1 - the one described here as "local,
    unconditionally" - NEVER FIRED from the only production caller. A
    conversation that had read outside text went to a cloud lane, with
    `decision.tainted` reported False so the route header agreed. No
    exception, no log line.

    That is the whole argument against a permissive `**kwargs` on a function
    that makes a privacy decision: it converts a TypeError at startup, which
    someone fixes in a minute, into an open gate nobody can see. `**_extra`
    is still here so an unknown argument cannot take down every chat turn -
    but anything it catches is now RECORDED, because a silently ignored
    argument to this function is exactly the bug above.
    """
    if tainted is not None:
        # The older spelling, kept working rather than broken.
        conversation_tainted = bool(conversation_tainted) or bool(tainted)
    if _extra:
        try:
            if fw is not None:
                fw.audit_log("router.unknown_argument",
                             {"names": sorted(_extra.keys())})
        except Exception:
            pass
    lanes = cloud_lanes(lanes)
    c = complexity(query)
    local = local_model or "local"
    # Whether the "local" lane IS local, rather than assuming it. `local_model`
    # comes from a state file (jarvis_models.current_model()), not a constant,
    # so a caller can hand this function a CLOUD model as its "local" lane.
    # Computing inject_memory from the gate meant every safe-looking gate then
    # returned that cloud lane WITH memory attached - the exact thing the
    # module docstring promises cannot happen. Computed from the lane now.
    local_is_local = is_local_lane(local, local_model)

    def local_decision(gate: str, why: str) -> Decision:
        d = Decision(local, why, gate, c,
                     inject_memory=local_is_local,
                     tainted=conversation_tainted)
        return _a_model_this_lane_can_run(d)

    def _a_model_this_lane_can_run(d: Decision) -> Decision:
        """Answer locally with a model this lane can hold (2026-11-18).

        Every local gate below returns through here, so no gate can be the one
        that forgot to check. The check happens when the DECISION is made and
        not in `jarvis_agent.run_local_turn`, because that is where the choice
        of model is made (the saved model came in as `local_model`) and because
        the route detail is built from this object: the model asked for, the
        model that will really answer, and why are all in the detail BEFORE a
        single token is generated, so tonight's hour of tracing cannot happen
        again. Nothing here can turn a local gate into a cloud one - the lane
        stays `local` and the replacement is a model on this PC.
        """
        replacement = local_model_fallback(d.lane)
        if not replacement:
            return d
        wanted, usable = replacement["lane"], replacement["model"]
        return replace(
            d, lane=usable,
            reason=(f"{d.reason}; the saved model {wanted} cannot run on the lane "
                    f"this turn uses on this PC, so {usable}, the model that lane "
                    f"is configured for, answered instead"),
            # The lane this turn runs on IS this PC's local lane, whatever the
            # replacement model's NAME looks like: is_local_lane()'s name test
            # cannot be asked of a name it has never seen, so it is not used.
            inject_memory=True,
            degraded_from=[replacement])

    # Gate -1, before every other (security audit H1, 2026-09-25): the
    # "local" lane is one of Ollama's cloud models. Every gate below would
    # hand it back as the lane that "stays on this machine" - a tainted
    # turn, a picture, a private question - so none of them may run. The
    # lane is still named (the caller has no other that is local), with
    # gate "cloud_model", no memory and no offer; jarvis_agent.run_local_turn,
    # which answers every local turn, refuses to send it anything and says
    # why in the same words. Where a cloud model belongs is a cloud lane,
    # which asks the owner each time (gate 6).
    if is_remote_model(local):
        return Decision(local, CLOUD_MODEL_AS_LOCAL.format(model=local), "cloud_model", c,
                        inject_memory=False, tainted=conversation_tainted)

    if not lanes:
        # "unavailable", not "no-lanes": jarvis_hud.py:1717 tests for exactly
        # this string to rewrite the reason when Jarvis is injecting memory
        # itself. A different name left that branch dead.
        return local_decision("unavailable", "no cloud lane was offered")
    # Gate 0b (2026-09-28, jarvis_asks_first.py's Lockdown): every way out of
    # this PC asks first or stops - and a cloud model is one. No lane, and no
    # offer to ask about one either: Lockdown means "not now", not "ask me".
    if lockdown_on():
        return local_decision(
            "lockdown",
            "Lockdown is on, so nothing goes to a cloud AI model")
    if conversation_tainted:
        return local_decision(
            "taint",
            "this conversation has read outside text, so it stays on this machine")
    # A PICTURE NEVER LEAVES. A screen capture can show anything that was on
    # screen - an email, a document, a password manager, a bank statement -
    # and none of the text checks below can read it. This used to escalate a
    # picture like any other long question, and even went looking for a cloud
    # lane with "vision" in its name. Rule 1: files, email and credentials
    # stay on the local model. If the local model cannot see pictures, the
    # desktop says so before sending (jarvis-desktop's vision.rs), rather
    # than this routing around it.
    if has_image:
        return local_decision(
            "image",
            "the message carries a picture, which can show anything that was "
            "on screen, so it stays on this machine")
    # A FILE THE OWNER ATTACHED NEVER LEAVES (2026-10-29). The PC reads the
    # file's words itself and puts them in the NEWEST user turn - which is
    # exactly the turn cloud-one-turn.patch keeps when it cuts a request down -
    # so this gate is the only thing between the owner's tax return and a cloud
    # model. Its own gate name, "file", so the route header says why. It sits
    # here, before the private check, the budget and the offer, because there is
    # nothing to ask about a turn that cannot go: test_attached_file.py proves
    # it answers local before any of them run (design risk 1).
    if has_file:
        return local_decision(
            "file",
            "the message carries a file you attached, so its words stay on this "
            "machine")
    # THE SCREEN'S WORDS NEVER LEAVE EITHER (docs/SCREEN-DESIGN.md section 5,
    # "Rule 1: a turn with screen content always stays on this PC"). "Look
    # at this" and "Watch with me" hand the model the words read off the
    # owner's screen (jarvis_screen.py) - an email, a document, a chat, a
    # bank page not on the Never look at list - with or without a picture,
    # and the private-topic check below reads only the owner's question.
    # Its own gate name, "screen", so the route header says why; nothing in
    # either app reads a gate name but "private", so none needs a change.
    if has_screen:
        return local_decision(
            "screen",
            "the message carries words read from your screen, which can show "
            "anything, so it stays on this machine")
    if is_private(query):
        return local_decision("private", "the question matches the private-topic backstop")
    secret = looks_like_a_secret(query)
    if secret:
        return local_decision(
            "secret", f"the message contains what looks like {secret}, not "
                      f"just a word for one, so it stayed on this machine")
    # GATE 3b - THE QUESTION IS ABOUT THIS MACHINE ITSELF (2026-11-22, ruling
    # 5.3). A cloud lane carries no tools and no private files, so a question
    # about Atlas's own repository, its pull requests, CI or defects, or the
    # tools it has here, is one that lane cannot answer at all - it can only
    # guess, and it did: "I don't have a GitHub repository of my own". Sits
    # ABOVE the complexity gate on purpose, so the standing switch and a high
    # score cannot hand it out, and above the budget and the offer because
    # there is nothing to spend and nothing to ask about. An explicit click
    # cannot lift it either - there is no version of a cloud lane that has the
    # tools. Its reason is one plain sentence, and the gate's own test
    # (`asks_about_own_repo`) is narrow: a question that merely mentions
    # GitHub keeps every ordinary gate (test_router_self_repo.py proves it).
    if asks_about_own_repo(query):
        return local_decision(
            "self_repo",
            "the question is about this PC's own repository, its pull requests, "
            "CI or defects, or the tools it has here, so it is answered on this "
            "machine where those tools are")
    # GATE 4 - STAGE 1, the deterministic complexity pre-gate (ruling 6.1 keeps
    # it), PAIRED with the 2-strike fallback for coding turns. The fallback can
    # only turn a would-be local answer into "carry on to gate 5", and only for
    # a coding turn that failed locally twice in THIS conversation: every gate
    # above has already passed, and gates 5 and 6 still run below. It never
    # lifts a refusal, and it never runs for a non-coding turn.
    threshold = float(_cfg("routing", "complexity_threshold", 0.40) or 0.40)
    strikes = local_failure_strikes(conversation)
    fallback = (c < threshold
                and strikes >= STRIKES_FOR_FALLBACK
                and is_coding_turn(query, local_model=local_model, coding=coding))
    if c < threshold and not fallback:
        return local_decision("complexity", f"complexity {c} is under the threshold")

    b = budget or Budget.load()
    if not b.allows_cloud():
        which = "daily" if b.day_exceeded() else "per-minute"
        return local_decision("budget", f"the {which} cloud budget is spent")

    lane = lanes[0]
    # The lead-in both the offer and the escalation reason use. The fallback's
    # own sentence says WHY a turn under the threshold is here at all, in the
    # route header the owner can read.
    if fallback:
        lead = (f"complexity {c} is under the threshold, but this coding turn "
                f"failed on this PC {strikes} times in this conversation")
    else:
        lead = f"complexity {c}"
    # WHO SAID YES, and it can only ever be one of three (2026-10-27):
    #   * `owner_said_yes` - the per-question click both apps already had
    #     ("Try the cloud model"), unchanged;
    #   * the PC's own standing switch (`standing_escalation()`, read from the
    #     file on THIS machine and from nowhere else); or
    #   * the owner asking for the cloud in the message itself
    #     (`explicit_escalation`), for that one turn.
    # All three are consulted HERE, after every gate above has had its chance
    # to return local, so none of them can lift a refusal: the order is still
    # the policy. The last two are auto-escalation - the owner did not click -
    # so the decision says so (`auto`), and a cloud answer with nothing usable
    # in it is never dressed up as one (jarvis_chatbot_api.CloudAnswer).
    asked = explicit_escalation(query)
    clicked = owner_said_yes is True
    # A click for THIS question is already the owner's yes, and calling a turn
    # he chose "automatic" would change how a blank cloud answer is shown for
    # it. So the standing switch is consulted only when he did not click.
    standing = False if clicked else standing_escalation()
    if not (clicked or standing or asked):
        d = local_decision(
            "offer", f"{lead}: {lane} could answer this, but the cloud is used "
                     f"only when you say yes for this question")
        d.offer = lane
        return d
    auto = bool(asked or standing)
    if asked:
        why = f"{lead}, budget available, and you asked for the cloud in this message"
    elif clicked:
        why = f"{lead}, budget available, and you said yes for this question"
    else:
        why = (f"{lead}, budget available, and cloud escalation is on for this PC "
               f"in the Presets menu")
    return Decision(lane, why, "escalate", c,
                    inject_memory=False, tainted=conversation_tainted, auto=auto)


def degrade(lane: str, lanes: Optional[list] = None,
            local_model: str = "") -> Optional[str]:
    """One step down from `lane`, or None if there is nowhere lower.

    NEVER returns `lane`. jarvis_hud calls this after a lane refused and
    retries with the result; returning the input would retry the refusing lane
    for ever. The caller checks `if not nxt or nxt == lane: break` as a second
    guard, and that guard should never fire.

    The chain is `[budget].degrade_chain` when the current lane is in it,
    otherwise the caller's own `lanes` list, and local is always the floor -
    checked FIRST, unconditionally, before `chain` or `lanes` is even read.

    A CONFIG CAN NAME A LANE THAT NO LONGER EXISTS, AND THAT IS NOT A LANE.
    The chain is an owner's file and outlives the code that wrote it: on the
    owner's PC it still read `["jarvis-escalate", "jarvis-bulk",
    "jarvis-critic"]` long after the 2026-10-27 decision collapsed the three
    cloud lanes into one, and the patcher never overwrites an existing config
    line (backend/_apply_toml_tiers.py repairs it now, and the repository's own
    copy has been right since that decision). A stale name in this chain was
    not a harmless label: `jarvis_chatbot_api.lane_service()` maps a name it
    does not know to the CHOSEN service, so one 429 stepped the relay through
    two more real requests to the same provider under names that are not lanes
    - and the lane that finally answered was not in the caller's `lanes` list,
    so `jarvis_hud` did not count the call against the budget either. So the
    chain is FILTERED to names this module can actually serve - the cloud
    lane(s) `cloud_lanes()` keeps from the caller's list, plus the local model
    as the floor - before it is walked. A name that is dropped was going to be
    refused by `cloud_lanes()` anyway; dropping it here means the refusal lands
    on the next REAL lane, and the bottom is local.

    THAT ORDERING IS THE FIX. It used to be checked last: `order` was built
    from `chain` or `lanes`, and if `lane` (already equal to `local`) happened
    to appear inside that list with something after it, the walk returned
    THAT NEXT ENTRY instead of ever reaching the floor. `jarvis_hud:1738`
    documents that a `lanes` list containing `local_model` is a real state -
    it exists specifically so degrading FROM a cloud lane can land ON local -
    but the same list read the other way, starting the walk AT local, handed
    back a CLOUD lane. Reproduced: `degrade("local", ["local","a","b"],
    "local")` returned `"a"`. `choose()` pins a conversation to `local`
    unconditionally on taint or the private backstop - this was the one path
    that could still walk it back out to the cloud, the moment the local
    model refused or timed out and jarvis_hud asked what to try next.
    """
    lane = str(lane or "")
    local = local_model or "local"
    if lane == local:
        return None
    # The names this call can actually reach: the ONE cloud lane (or none) from
    # the caller's own list, plus the local floor. A `[budget] degrade_chain`
    # entry outside this set names a lane that does not exist any more; walking
    # to it used to mean a real request to the chosen provider under a name that
    # is not a lane (see the docstring). It is dropped, never substituted.
    serviceable = set(cloud_lanes(lanes))
    serviceable.add(local)
    chain = [str(n or "") for n in (_cfg("budget", "degrade_chain", []) or [])]
    chain = [n for n in chain if n in serviceable]
    order = chain if lane in chain else list(lanes or [])

    # Seen lanes are skipped, so a chain that lists a lane twice - or a
    # `lanes` list that CONTAINS local_model, which jarvis_hud:1738 shows is a
    # real state - cannot produce a 2-cycle. It could before: degrade("a",
    # ["a","b"], "a") gave "b" and degrade("b", ["a","b"], "a") gave "a",
    # which never returns its own input and so slipped past the caller's
    # `nxt == lane` guard while re-opening a lane that had just refused.
    if lane in order:
        seen = {lane}
        for nxt in order[order.index(lane) + 1:]:
            if nxt and nxt not in seen:
                return nxt
            seen.add(nxt)
    # Bottom of the chain, or a lane nobody listed. Local is always the floor.
    return local


def status() -> dict:
    return {"budget": Budget.load().status(),
            "complexity_threshold": _cfg("routing", "complexity_threshold", 0.40),
            "degrade_chain": _cfg("budget", "degrade_chain", []),
            "private_terms": len(_PRIVATE_TERMS) + len(_config_terms()),
            "secret_patterns": len(_SECRET_PATTERNS)}


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<22} {v}")
