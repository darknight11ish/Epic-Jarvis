"""test_options_understanding.py - the 2026-11-07 options-understanding audit's
four fixes, proved from the code that owns each one.

    python -B backend/test_options_understanding.py

WHAT THIS IS FOR. The audit
(`.dsh-scratch/OPTIONS-UNDERSTANDING-AUDIT-2026-11-07/REPORT.md`) measured four
owner-visible defects against the live code. Each has its own checks here, and
none of them needs the owner's PC, a network or a model:

1. B1 - THE PROVIDER THE OWNER CHOSE IS THE ONE THAT ANSWERS.
   `jarvis_presets.cloud_chosen()` (the file `cloud-choice.json`) was read by
   every view and by the card, and by nothing on the send path:
   `jarvis_chatbot_api.lane_service()` was hard-coded to
   `("deepseek_api", "deepseek-flash")`. So choosing Mistral in the Presets menu
   still sent the words to `api.deepseek.com` - the Presets row, the card and
   `/api/reach` named one company while the request went to another. This suite
   patches the chosen provider IN MEMORY (the way the audit did; no file is
   written) for all six services and asserts `lane_service`, `lane_status` and
   `cloud_lane` resolve to THAT service, company, host, model and endpoint -
   and that the fallback for an unknown lane name follows the choice too. The
   "is my key saved?" answer is checked separately: with a non-DeepSeek provider
   chosen it must name that provider, never DeepSeek.

2. B2 - "how do I add a mistral key?" IS NOT A REMINDER QUESTION.
   `_REMINDER_HOWTO_HOW_RX` read ANY "how do I add ..." as a reminder how-to
   and the step-aside noun list had no key/API/provider word, so the owner was
   told how to set a timer. Every measured phrase from the audit is here
   verbatim, plus the real route each answer must carry: Settings, Chatbot API
   keys + the one PowerShell line for a key, Brain, Model, Models for a model,
   the phone pairing for a second PC, and an honest "not built" for Telegram.
   The reminder phrases that must keep their own answer are pinned too.

3. B4 - EVERY SWITCH ANSWERS ABOUT ITSELF.
   `jarvis_quick._run_feature_state_setting` passed the registry KEY to the
   FEATURE lookup, so 14 of the 38 switches answered a state question with
   `I do not have a feature called "lights_without_card"` - and showed the raw
   snake_case key to the owner. This suite iterates ALL 38
   `jarvis_settings_registry.BOOL_SETTINGS`, drives the real runner with each
   key, and drives the ordinary "is <label> on?" phrase through the real
   matcher and answerer. No answer may contain the false-denial sentence or a
   raw snake_case key.

4. B5 - THE CLOUD ROW NAMES NO SINGLE PROVIDER.
   The catalogue title was "Cloud (DeepSeek API)", one of six connected
   services (the docs already name all six). The title must be provider-neutral
   and match the docs.

5. Q1/B6 - THE PROVIDER CAN BE SEEN AND CHANGED FROM CHAT, THROUGH ONE CARD.
   "which cloud providers can I use?" and "switch my cloud provider to mistral"
   reached the model. The view is now a read-only answer built from the PC's own
   `cloud_providers()`; the change calls the SAME `jarvis_presets.apply_cloud`
   the Presets Cloud row calls (ONE `change_own_config` card, nothing written
   before the yes). After a chosen Mistral, the reach row, the approval-card
   text, the chat answers and the lane's own service/host/key must ALL name
   Mistral - and the lane must never send to DeepSeek.

6. Q7 - THE PRIVACY BACKSTOP IS HARDENED, AND AUTO-ESCALATION KEEPS ITS RULES.
   The backstop gains home/street/mailing address and phone number, and its
   `\bdiagnos\w*` is narrowed to medical contexts so a technical prompt can
   escalate normally (that half is pinned in test_router_private_terms.py).
   Here the ROUTER's semantics are pinned: with the standing switch off the
   hard question is only OFFERED (detect-and-ask, one card); with it on (turned
   on through its own `change_own_config` card) a clean hard prompt may escalate
   automatically, and every privacy/taint/file/screen/secret/lockdown/budget/
   complexity gate still refuses exactly as before - the switch can only waive
   the per-question yes, never a gate.

The key store, the money file and the config folder are stand-ins/throwaway: a
suite must never read the owner's real Credential Manager or `cloud-choice.json`.
No file is written outside this suite's own temporary folder.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: A throwaway config/home BEFORE any of the modules below reads one:
#: `jarvis_presets._config_dir()` would otherwise fall through to the owner's
#: real `~/.openjarvis/cloud-choice.json` on this PC.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-options-audit-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = os.environ["OPENJARVIS_CONFIG_DIR"]
os.environ["OPENJARVIS_HOME"] = str(TMP / "home")
os.environ["JARVIS_HOME"] = str(TMP / "home")
os.environ["JARVIS_SUITE_RUNNING"] = "1"
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
#: The same offline switches `backend/run_suites.py` gives every suite: a
#: direct run must not try to fetch a model because an import looked for one.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.dont_write_bytecode = True

from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_chatbot_api.py", "jarvis_presets.py",
                "jarvis_chatbot.py", "jarvis_token_store.py",
                "jarvis_settings_registry.py", "jarvis_feature_guide.py",
                "jarvis_feature_catalogue.py")

#: The same fake `jarvis_framework` the chatbot-api suite uses: the money file
#: and `[chatbot]` config lines live in THIS suite's temp folder, never the
#: owner's. It must be in sys.modules before jarvis_chatbot* import it.
CFG: dict = {}
TIERS: dict = {}
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = TMP
fw.LOG_DIR = TMP
fw.load_framework = lambda: {"chatbot": CFG}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: TIERS.get(action, "ask")
sys.modules["jarvis_framework"] = fw

import jarvis_token_store as TS  # noqa: E402
import jarvis_chatbot_api as API  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_feature_catalogue as CAT  # noqa: E402

#: A valid-looking key, built by joining strings the way the other suites do.
KEY = "sk-" + "options" + "FAKEkey" + "0123456789"
STORE: dict = {}
PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class FakeStore:
    """Credential Manager presence only: a dict of target -> value."""

    def __init__(self, target):
        self.target = target

    def read(self):
        return STORE.get(self.target)

    def write(self, value):
        STORE[self.target] = value

    def delete(self):
        return STORE.pop(self.target, None) is not None


TS._STORE_FACTORY = FakeStore


def fresh():
    """This suite's own state back to the start: no keys, no money, no config."""
    CFG.clear()
    TIERS.clear()
    STORE.clear()
    API._reset_models_for_tests()
    for f in (API.money_path(), API.money_path().with_name(API.MONEY_FILE + ".tmp")):
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    # The two files a cloud choice is remembered in, and the standing switch's
    # own file: every test starts with NO cloud service chosen.
    for name in ("cloud-choice.json", "presets-choice.json", "escalate-cloud.json"):
        try:
            (TMP / "config" / name).unlink()
        except FileNotFoundError:
            pass


def reply_of(text):
    """The words `jarvis_quick` would answer a sentence with, no model called."""
    got = Q.answer(text, now=0, peer="127.0.0.1", local=True)
    return str(getattr(got, "reply", "") or "")


def snake_case(text):
    """Every snake_case-ish token in a sentence (an internal key, if any)."""
    return re.findall(r"\b[a-z0-9]+_[a-z0-9_]*\b", str(text or ""))


# ==========================================================================
#   B1 - the chosen provider is the one that answers
# ==========================================================================

def t_the_cloud_lane_follows_the_chosen_provider():
    """Patch the choice in memory for all six services; nothing else changes.

    The audit's own measurement (`provider_route_proof.json`) was: with
    `cloud_chosen` patched to `mistral_api`, `lane_service` still returned
    DeepSeek, `lane_status` still named `api.deepseek.com` and `cloud_lane`
    still built DeepSeek's URL. Every one of those is inverted here.
    """
    fresh()
    for pid in API.PRESETS:
        API.set_limit(pid, 5.0)
        STORE[API.KEY_TARGETS[pid]] = KEY
    real = P.cloud_chosen
    try:
        for pid, preset in API.PRESETS.items():
            P.cloud_chosen = lambda pid=pid: pid
            got = API.lane_service("jarvis-escalate")
            check(f"{pid}: lane_service is the chosen service and that preset's model",
                  got == (pid, preset.model), got)
            row = API.lane_status()["lanes"][0]
            check(f"{pid}: lane_status names the chosen company, host and model",
                  row["pid"] == pid and row["company"] == preset.company
                  and row["host"] == preset.host and row["model"] == preset.model
                  and row["ready"] is True, row)
            status = API.lane_status()
            check(f"{pid}: the status fallback is the chosen service too, not a second one",
                  status["default_pid"] == pid
                  and status["fallback_model"] == preset.model, status)
            how = API.cloud_lane("jarvis-escalate")
            check(f"{pid}: cloud_lane sends to that service's own endpoint",
                  bool(how) and how["pid"] == pid and how["model"] == preset.model
                  and how["host"] == preset.host
                  and how["url"] == preset.base_url.rstrip("/") + "/chat/completions",
                  how)
            state = API.lane_state("jarvis-escalate")
            check(f"{pid}: lane_state carries that service's address and key",
                  state["pid"] == pid and state["key"] == KEY
                  and state["url"] == preset.base_url.rstrip("/") + "/chat/completions",
                  state)
            check(f"{pid}: lane_key reads that service's own key",
                  API.lane_key("jarvis-escalate") == KEY)

        # An unknown lane name (an old degrade_chain entry) must keep meaning
        # ONE cloud service - the chosen one - not a second, unpaired service.
        P.cloud_chosen = lambda: "mistral_api"
        check("an unknown lane name goes to the chosen service, not to DeepSeek",
              API.lane_service("jarvis-vision")[0] == "mistral_api",
              API.lane_service("jarvis-vision"))
        check("... and lane_status names no lane that is not in the table",
              len(API.lane_status()["lanes"]) == len(API.CLOUD_LANES))

        # The owner's own model line for the CHOSEN service still wins.
        CFG["mistral_api_model"] = "owner-picked-model"
        API._reset_models_for_tests()
        check("a model the owner typed for the chosen service is the one used",
              API.lane_service("jarvis-escalate")
              == ("mistral_api", "owner-picked-model"),
              API.lane_service("jarvis-escalate"))
        CFG.pop("mistral_api_model", None)
        API._reset_models_for_tests()

        # A Presets provider id is mapped to the chatbot-api service id. They
        # are the same id today; the short name is accepted too, so a file that
        # named "mistral" can never pick the wrong service.
        P.cloud_chosen = lambda: "mistral"
        check("a Presets short name maps to the chatbot-api service id",
              API.lane_service("jarvis-escalate")
              == ("mistral_api", API.PRESETS["mistral_api"].model),
              API.lane_service("jarvis-escalate"))
        P.cloud_chosen = lambda: "nobody"
        check("a choice this PC does not know is ignored, not guessed",
              API.lane_service("jarvis-escalate") == API.DEFAULT_LANE,
              API.lane_service("jarvis-escalate"))
    finally:
        P.cloud_chosen = real
        API._reset_models_for_tests()
    check("no choice recorded: the fallback is unchanged DeepSeek",
          P.cloud_chosen() == "" and API.lane_service("jarvis-escalate") == API.DEFAULT_LANE,
          (P.cloud_chosen(), API.lane_service("jarvis-escalate")))


def _cloud_state(**over):
    base = {"available": True, "provider": "", "provider_name": "", "company": "",
            "host": "", "model": "", "key_saved": None, "ready": "",
            "escalate": False, "escalate_why": "", "deepseek_key_saved": None}
    base.update(over)
    return base


def t_the_key_answer_names_the_chosen_provider():
    """`is my key saved?` reports the CHOSEN service's key, never DeepSeek by rote.

    The audit measured the hard-wired sentence: with OpenRouter chosen and its
    key saved, "do you have my key" answered "No. No DeepSeek API key is
    saved". The plain "is my key saved?" / "is my deepseek key saved?" phrasings
    also matched nothing and went to the model (audit B6); they are answered
    from the same real state now.
    """
    fresh()
    real = P.cloud_state
    try:
        P.cloud_state = lambda: _cloud_state(
            provider="mistral_api", provider_name="Mistral (API)",
            company="Mistral AI", host="api.mistral.ai",
            model="mistral-small-latest", key_saved=True, deepseek_key_saved=True)
        for phrase in ("do you have my key", "is my key saved",
                       "is my api key saved", "is my mistral key saved"):
            got = Q.match(phrase, now=0)
            words = reply_of(phrase)
            check(f"non-DeepSeek choice: {phrase!r} is answered for Mistral",
                  got is not None and got.name == "cloud_honesty"
                  and "Mistral" in words and "DeepSeek" not in words, (got, words))
        P.cloud_state = lambda: _cloud_state(
            provider="openrouter_api", provider_name="OpenRouter (API)",
            company="OpenRouter", host="openrouter.ai",
            model="openai/gpt-5-mini", key_saved=False, deepseek_key_saved=True)
        words = reply_of("is my key saved")
        check("non-DeepSeek choice, no key: names OpenRouter, never DeepSeek",
              "OpenRouter" in words and "No OpenRouter API key" in words
              and "DeepSeek" not in words, words)
        P.cloud_state = lambda: _cloud_state(deepseek_key_saved=True)
        words = reply_of("do you have my key")
        check("no provider chosen: says so plainly, and mentions the saved DeepSeek key",
              "No cloud service is chosen" in words and "DeepSeek API key is saved" in words,
              words)
        P.cloud_state = lambda: _cloud_state(deepseek_key_saved=False)
        words = reply_of("do you have my key")
        check("no provider and no DeepSeek key: one honest no, no fragment",
              "No." in words and "No cloud service is chosen" in words, words)
        P.cloud_state = lambda: _cloud_state(
            provider="deepseek_api", provider_name="DeepSeek (API)",
            company="DeepSeek", host="api.deepseek.com", model="deepseek-flash",
            key_saved=True, deepseek_key_saved=True)
        words = reply_of("is my key saved")
        check("DeepSeek chosen: names DeepSeek and says the key is saved",
              "DeepSeek" in words and "key is saved" in words, words)
    finally:
        P.cloud_state = real
        fresh()


# ==========================================================================
#   B2 - the measured "how do I add ..." sentences answer their real feature
# ==========================================================================

#: The phrases the audit measured, verbatim, and the intent each must reach.
B2_CASES = (
    ("how do I add a mistral key?", "adding_key_howto"),
    ("how do I add an openai key", "adding_key_howto"),
    ("how do i add a groq key", "adding_key_howto"),
    ("how do i add an api key", "adding_key_howto"),
    ("how do i add a key", "adding_key_howto"),
    ("how do i add a model", "adding_model_howto"),
    ("how do i add a second pc", "adding_second_pc_howto"),
    ("how do i add telegram", "adding_telegram_howto"),
)

#: "how do I add ..." sentences that are NOT those four nouns keep their answer.
B2_NOT_OURS = (
    ("how do i add a reminder", "reminder_howto"),
    ("how do i add milk to my shopping list", "reminder_howto"),
)


def t_the_add_howto_questions_answer_the_real_route():
    for phrase, want in B2_CASES:
        got = Q.match(phrase, now=0)
        words = reply_of(phrase)
        check(f"{phrase!r} reaches {want}", got is not None and got.name == want,
              got.name if got else "the model")
        check(f"{phrase!r}: not the reminder how-to",
              "Say or type, for example" not in words
              and "remind me to call Mom" not in words, words)
    keys = reply_of("how do I add a mistral key?")
    check("a key question names Settings, Chatbot API keys",
          "Settings, Chatbot API keys" in keys, keys)
    check("... and the one command line, with the six short names",
          "py -3 jarvis_chatbot_api.py key" in keys
          and all(short in keys for short in API.BY_SHORT), keys)
    check("... and the monthly limit line, so a saved key is actually usable",
          "jarvis_chatbot_api.py limit" in keys, keys)
    model = reply_of("how do i add a model")
    check("a model question names Brain, Model, Models and the one card",
          "Brain, Model, Models" in model and "approval card" in model
          and "nothing downloads" in model, model)
    pc = reply_of("how do i add a second pc")
    check("a second-PC question says one PC + the phone pairing, not a fake feature",
          "second PC cannot join" in pc and "pair my phone" in pc, pc)
    telegram = reply_of("how do i add telegram")
    check("a Telegram question says honestly that it is not built",
          "not built into Jarvis" in telegram, telegram)
    for phrase, want in B2_NOT_OURS:
        got = Q.match(phrase, now=0)
        check(f"{phrase!r} keeps its own answer ({want})",
              got is not None and got.name == want, got.name if got else "the model")
    got = Q.match("can you set a timer for five minutes", now=0)
    check("a real timer request is still the timer action",
          got is not None and got.name != "adding_key_howto"
          and not str(got.name).startswith("adding_"), got.name if got else None)


# ==========================================================================
#   B4 - all 38 switches answer state questions about themselves
# ==========================================================================

#: The 14 the audit measured answering "I do not have a feature called ...".
B4_MEASURED_KEYS = (
    "learn_sensitive_topics", "lights_without_card", "briefing_senders",
    "pc_reminder_sounds", "pc_briefing_notification", "pc_handoff_notification",
    "pc_setup_notification", "voice_follows_face", "voice_check_locked",
    "big_model_wiki", "big_model_deep_questions", "second_card_combined",
    "second_card_suggest_struggle", "second_card_suggest_correction",
)

_FALSE_DENIAL = "i do not have a feature called"


def _switch_answer_is_clean(setting, words, where):
    """(problem or "") - the two things B4 was: a false denial, a raw key."""
    text = str(words or "")
    if _FALSE_DENIAL in text.lower():
        return f"{where}: false denial: {text[:160]}"
    for token in snake_case(text):
        if token in {b.key for b in R.BOOL_SETTINGS}:
            return f"{where}: raw key {token!r} shown: {text[:160]}"
    if "_" in setting.key and setting.key in text:
        return f"{where}: raw key {setting.key!r} shown: {text[:160]}"
    return ""


def t_all_38_switch_read_phrases_are_about_their_own_switch():
    """The audit's own regression: ALL 38, not only the 14 measured broken."""
    fresh()
    real = tuple(R.BOOL_SETTINGS)
    check("38 bool settings, the audit's own count", len(real) == 38, len(real))
    problems = []
    missing_labels = [s.key for s in real if not Q._setting_label(s).strip()]
    answered = 0
    for setting in real:
        label = Q._setting_label(setting)
        # 1. The ordinary READ phrase the audit drove, through the real matcher
        #    and the real answerer. A sentence that is genuinely the model's may
        #    fall through; one that IS answered must be answered honestly.
        phrase = f"is {label} on?"
        intent = Q.match(phrase, now=0)
        if intent is not None:
            answered += 1
            problem = _switch_answer_is_clean(setting, reply_of(phrase), phrase)
            if problem:
                problems.append((setting.key, problem))
        # 2. The runner the intent carries, for EVERY setting: the fix itself.
        direct = Q._run_feature_state_setting({"key": setting.key})
        dwords = str(getattr(direct, "reply", "") or "")
        if not dwords.strip():
            problems.append((setting.key, "the state answer was empty"))
        else:
            problem = _switch_answer_is_clean(setting, dwords, f"state({setting.key})")
            if problem:
                problems.append((setting.key, problem))
        # 3. The same for the "how do I change it?" runner, which had the same
        #    key-not-name defect (`_run_feature_howto_setting`).
        howto = Q._run_feature_howto_setting({"key": setting.key, "on": True})
        hwords = str(getattr(howto, "reply", "") or "")
        if not hwords.strip():
            problems.append((setting.key, "the how-to answer was empty"))
        else:
            problem = _switch_answer_is_clean(setting, hwords, f"how_to({setting.key})")
            if problem:
                problems.append((setting.key, problem))
    check("every one of the 38 registry rows carries the label its card prints",
          not missing_labels, missing_labels)
    check(f"every one of the 38 read phrases is no longer a false denial "
          f"({answered} answered without the model)",
          not problems, problems[:8])
    check("the 14 the audit measured are all answered, not sent to the model",
          all(Q.match(f"is {Q._setting_label(s)} on?", now=0) is not None
              for s in (b for b in real if b.key in B4_MEASURED_KEYS)),
          [b.key for b in real if b.key in B4_MEASURED_KEYS
           and Q.match(f"is {Q._setting_label(b)} on?", now=0) is None])
    check("... and no answer anywhere shows any of the 38 raw keys",
          not any(problem for _, problem in problems), problems[:8])
    # The guide itself, one label at a time: the same reading with no intent.
    unknown = []
    for setting in real:
        label = Q._setting_name_for_guide(setting.key)
        out = FG.state(label)
        if out.get("ok") is not True or _FALSE_DENIAL in str(out.get("words") or "").lower():
            unknown.append((setting.key, out.get("kind"), str(out.get("words") or "")[:120]))
    check("the feature guide answers every one of the 38 by its own label",
          not unknown, unknown[:8])
    fresh()


# ==========================================================================
#   B5 - the Cloud row's title names no single provider
# ==========================================================================

def t_the_cloud_row_title_names_no_single_provider():
    row = next((r for r in CAT.FEATURES if r.get("id") == "cloud-escalation"), None)
    check("the Cloud row is in the feature catalogue", row is not None)
    title = str((row or {}).get("title") or "")
    check("the title is provider-neutral",
          title == "Cloud (an API service you choose)", title)
    check("... and it names none of the six services",
          not any(p.company.lower() in title.lower() or p.name.lower() in title.lower()
                  for p in API.PRESETS.values()), title)
    check("... nor does the row's own sentence still call DeepSeek the default",
          "DeepSeek" not in str((row or {}).get("what") or ""),
          str((row or {}).get("what") or "")[:160])
    features = json.loads((REPO / "features" / "features.json").read_text(encoding="utf-8"))
    source = next((r for r in features if r.get("id") == "cloud-escalation"), {})
    check("the catalogue is generated from features.json's own title",
          source.get("title") == title, source.get("title"))
    docs = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("the docs already name all six providers, and the row now agrees",
          all(p.host in docs for p in API.PRESETS.values()),
          [p.host for p in API.PRESETS.values() if p.host not in docs])


# ==========================================================================
#   Q1/B6 - the provider can be viewed and changed from chat, through ONE card
# ==========================================================================

#: Long and clause-heavy, so ONLY the gates above complexity can keep it local.
HARD_QUESTION = (
    "Compare two designs for the backup retry loop and explain in detail why "
    "each works, step by step, and how it can fail, and compare the trade-offs"
) * 2

#: The audit's measured phrasings for seeing which services exist.
Q1_LIST_PHRASES = (
    "which cloud providers can i use",
    "what cloud providers are supported",
    "do you support openai",
    "do you support mistral",
    "can i use chatgpt",
    "can i use two cloud providers",
)


class _Verdict:
    """The shape `jarvis_presets._gate` returns (allowed/outcome only)."""

    def __init__(self, allowed, outcome):
        self.allowed = allowed
        self.outcome = outcome


def _ready_provider(pid: str) -> None:
    """A service this PC can really use: its own key saved and a money limit."""
    STORE[API.KEY_TARGETS[pid]] = KEY
    API.set_limit(pid, 5.0)


def t_the_cloud_provider_can_be_seen_and_changed_from_chat():
    """The owner's Q1/B6 ruling: chat shows the six and switches the choice.

    The switch calls the SAME `jarvis_presets.apply_cloud` the Presets Cloud row
    calls, so it raises the SAME ONE `change_own_config` card and writes
    `cloud-choice.json` only after that yes. After a chosen Mistral, the reach
    row, the card text, the chat answers and the lane's own service/host/key all
    have to name Mistral - and the lane must NEVER send to DeepSeek.
    """
    fresh()
    real_gate = P._gate
    cards = []
    try:
        # ---- the view: read-only, from the PC's own provider list ----------
        for phrase in Q1_LIST_PHRASES:
            got = Q.match(phrase, now=0)
            check(f"{phrase!r} reaches the cloud-provider list",
                  got is not None and got.name == "cloud_provider_list",
                  got.name if got else "the model")
        _ready_provider("deepseek_api")
        words = reply_of("which cloud providers can I use?")
        check("... the list names all six by their own company and short name",
              all(p.company in words and p.short in words for p in API.PRESETS.values()),
              words)
        check("... it says one at a time, and where a key is added",
              "One at a time" in words and "Chatbot API keys" in words, words)
        check("... and it carries no key and no fragment of one", KEY not in words, words)
        got = Q.match("change the cloud provider", now=0)
        check("'change the cloud provider' (no service named) asks which one",
              got is not None and got.name == "cloud_provider_ask",
              got.name if got else None)
        asked = reply_of("how do i change my cloud provider")
        check("... and the answer names the six, the phrase that works and the ONE card",
              all(p.short in asked for p in API.PRESETS.values())
              and "use mistral as my cloud provider" in asked
              and "ONE approval card" in asked, asked)

        # ---- the change: ONE change_own_config card, nothing before the yes --
        _ready_provider("mistral_api")
        P._gate = lambda action, detail, prompt="": (
            cards.append((action, detail, prompt)) or _Verdict(False, "timed_out"))
        denied = reply_of("use mistral as my cloud provider")
        check("the change raises exactly ONE card", len(cards) == 1, cards)
        action, detail, prompt = cards[0]
        check("... under change_own_config, the same action the Presets row uses",
              action == "change_own_config", action)
        card_text = str(detail.get("text") or "")
        check("... whose words name Mistral, its host and model, and never DeepSeek",
              "Mistral AI" in card_text and "api.mistral.ai" in card_text
              and "mistral-small-latest" in card_text and "DeepSeek" not in card_text,
              card_text)
        check("a card that is not approved changes nothing",
              P.cloud_chosen() == "" and not (TMP / "config" / "cloud-choice.json").exists(),
              P.cloud_chosen())
        check("... and the chat answer says nothing changed",
              "nothing was changed" in denied.lower()
              and "not approved" in denied.lower(), denied)

        # ---- a service this PC cannot use is refused BEFORE any card --------
        cards.clear()
        words = reply_of("use openrouter as my cloud provider")
        check("a provider with no key is refused before any card", not cards, cards)
        check("... in the PC's own no-key words",
              "No OpenRouter API key is saved" in words, words)
        check("... and the choice is unchanged", P.cloud_chosen() == "", P.cloud_chosen())

        # ---- the approved change: the same write the Presets row makes ------
        _ready_provider("openrouter_api")
        cards.clear()
        P._gate = lambda action, detail, prompt="": (
            cards.append((action, detail, prompt)) or _Verdict(True, "approved"))
        done = reply_of("use mistral as my cloud provider")
        check("an approved card writes the choice", P.cloud_chosen() == "mistral_api",
              P.cloud_chosen())
        check("... and the answer says it is done, naming Mistral",
              "done" in done.lower() and "Mistral AI" in done, done)
        check("... from exactly ONE change_own_config card",
              len(cards) == 1 and cards[0][0] == "change_own_config", cards)

        # ---- everything that names the service must now agree ---------------
        check("the lane's service and model are Mistral's",
              API.lane_service("jarvis-escalate")
              == ("mistral_api", "mistral-small-latest"),
              API.lane_service("jarvis-escalate"))
        status = API.lane_status()["lanes"][0]
        check("lane_status names the chosen service, host and company",
              status["pid"] == "mistral_api" and status["host"] == "api.mistral.ai"
              and status["company"] == "Mistral AI" and status["ready"] is True, status)
        how = API.cloud_lane("jarvis-escalate")
        check("cloud_lane builds Mistral's own endpoint",
              bool(how) and how["url"] == "https://api.mistral.ai/v1/chat/completions"
              and how["host"] == "api.mistral.ai", how)
        STORE.pop(API.KEY_TARGETS["deepseek_api"], None)
        check("the key lookup uses Mistral's key, and no DeepSeek key is saved at all",
              API.key_saved("deepseek_api") is False
              and API.lane_key("jarvis-escalate") == KEY,
              (API.key_saved("deepseek_api"), API.lane_key("jarvis-escalate")))
        line = P.cloud_state_line()
        check("the model's own cloud-state line names Mistral and never DeepSeek",
              "Mistral AI (api.mistral.ai" in line and "DeepSeek" not in line, line)
        provider_words = reply_of("which provider is the cloud preset using")
        check("the chat provider answer names Mistral",
              "Mistral" in provider_words and "DeepSeek" not in provider_words,
              provider_words)
        list_words = reply_of("which cloud providers can I use?")
        check("the list marks Mistral as the chosen one",
              "Mistral AI (mistral) is the chosen one" in list_words, list_words)
        reach = __import__("jarvis_reach", fromlist=["view"])
        row = reach._cloud_model(reach.Ctx(lanes=None))
        check("the reach row's 'where' is Mistral's own host",
              row.get("where") == "api.mistral.ai", row)
        check("... and its line names the lane's Mistral model, never DeepSeek",
              "mistral-small-latest" in str(row.get("line") or "")
              and "DeepSeek" not in str(row.get("line") or ""), row)

        # ---- the standing switch's OWN card names the chosen provider too ---
        cards.clear()
        code, body = P.cloud_escalate(on=True)
        check("turning the standing switch ON raises its own change_own_config card",
              len(cards) == 1 and cards[0][0] == "change_own_config", cards)
        switch_text = str(cards[0][1].get("text") or "") if cards else ""
        check("... naming the chosen Mistral, never DeepSeek",
              "Mistral AI" in switch_text and "DeepSeek" not in switch_text, switch_text)
        check("... and after the yes the PC's own standing switch is ON",
              P.escalate_on() is True and bool(body.get("on")) is True, body)
    finally:
        P._gate = real_gate
        fresh()


# ==========================================================================
#   Q7 - auto-escalation is opt-in, and the switch can never lift a gate
# ==========================================================================

def t_auto_escalation_needs_the_switch_and_still_respects_every_gate():
    """The owner's Q7 ruling, on the real router.

    OFF (default): a hard question is only OFFERED - detect-and-ask, one card,
    `auto` False. ON (turned on through the standing switch's own
    `change_own_config` card, see the Q1 test): a clean hard prompt may escalate
    with no click, `auto` True - and EVERY gate above the yes still refuses
    exactly as before, because the switch may only waive the per-question yes.
    """
    import time
    import jarvis_router as RT
    lanes = [RT.CLOUD_LANE]
    local = "jarvis-primary"
    base = dict(local_model=local, lanes=list(lanes), budget=RT.Budget(path=None))
    real_standing, real_lockdown = RT.standing_escalation, RT.lockdown_on
    refused_autos = []
    try:
        RT.lockdown_on = lambda: False
        RT.standing_escalation = lambda: False
        d = RT.choose(HARD_QUESTION, **base)
        check("switch OFF: the hard question is only OFFERED (detect-and-ask)",
              d.gate == "offer" and d.offer == RT.CLOUD_LANE and d.lane == local,
              d.as_dict())
        check("... with auto False, so a blank cloud answer is never dressed up",
              d.auto is False, d.as_dict())
        RT.standing_escalation = lambda: True
        d = RT.choose(HARD_QUESTION, **base)
        check("switch ON: a clean hard question auto-escalates through the ONE lane",
              d.gate == "escalate" and d.lane == RT.CLOUD_LANE and d.auto is True,
              d.as_dict())

        RT.lockdown_on = lambda: True
        d = RT.choose(HARD_QUESTION, **base)
        refused_autos.append(d.auto)
        check("switch ON: Lockdown still refuses (gate 'lockdown')",
              d.lane == local and d.gate == "lockdown" and not d.offer, d.as_dict())
        RT.lockdown_on = lambda: False
        for label, extra, gate in (
                ("a tainted conversation", dict(conversation_tainted=True), "taint"),
                ("a picture", dict(has_image=True), "image"),
                ("an attached file", dict(has_file=True), "file"),
                ("the screen's words", dict(has_screen=True), "screen")):
            d = RT.choose(HARD_QUESTION, **{**base, **extra})
            refused_autos.append(d.auto)
            check(f"switch ON: {label} still stays local (gate '{gate}')",
                  d.lane == local and d.gate == gate and d.auto is False
                  and not d.offer, d.as_dict())
        d = RT.choose(HARD_QUESTION + " my password is hunter2", **base)
        refused_autos.append(d.auto)
        check("switch ON: a private word still stays local (gate 'private')",
              d.lane == local and d.gate == "private" and not d.offer, d.as_dict())
        d = RT.choose(HARD_QUESTION + " ghp_" + "a" * 36, **base)
        refused_autos.append(d.auto)
        check("switch ON: a pasted secret still stays local (gate 'secret')",
              d.lane == local and d.gate == "secret" and not d.offer, d.as_dict())
        spent = RT.Budget(per_minute=1, per_day=1, minute_hits=[time.time()],
                          day_hits=[time.time()], path=None)
        d = RT.choose(HARD_QUESTION, **{**base, "budget": spent})
        refused_autos.append(d.auto)
        check("switch ON: a spent cloud budget still refuses (gate 'budget')",
              d.lane == local and d.gate == "budget" and not d.offer, d.as_dict())
        d = RT.choose("what is 2 + 2", **base)
        refused_autos.append(d.auto)
        check("switch ON: an easy question never escalates (gate 'complexity')",
              d.lane == local and d.gate == "complexity", d.as_dict())
        d = RT.choose(HARD_QUESTION, **{**base, "lanes": []})
        refused_autos.append(d.auto)
        check("switch ON: no cloud lane offered still refuses (gate 'unavailable')",
              d.lane == local and d.gate == "unavailable", d.as_dict())
        d = RT.choose(HARD_QUESTION, local_model="glm-4.6:cloud", lanes=list(lanes),
                      budget=RT.Budget(path=None))
        refused_autos.append(d.auto)
        check("switch ON: an Ollama cloud model as the 'local' lane still refuses first",
              d.gate == "cloud_model" and d.lane == "glm-4.6:cloud", d.as_dict())
        check("every refused gate kept auto False, so none can look automatic",
              bool(refused_autos) and all(a is False for a in refused_autos),
              refused_autos)
    finally:
        RT.standing_escalation, RT.lockdown_on = real_standing, real_lockdown


# ==========================================================================

def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:        # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        TS._STORE_FACTORY = None
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
