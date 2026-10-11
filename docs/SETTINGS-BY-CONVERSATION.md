# Changing every setting by talking to Jarvis

**Owner's decision, 2026-10-10** (`.dsh-scratch/QUEUE-OWNER-DECISIONS-2026-10-10.md`,
Decision 4). Written by the conversation that owns the item.

*"I should be able to have a conversation with Jarvis to change all of his
settings."*

---

## 1. What already works — measured, not assumed

This is **not a green field**, and the design starts from what is really there.
Every phrase below was put through the real grammar
(`python backend/run_phrase_tests.py`, and `jarvis_quick.match` directly) on
2026-10-10. `jarvis_quick.py`'s SHA256 (`0104C36C…`) is **identical** to the
installed copy, so this is what the live PC does:

| What the owner says | Intent | What happens |
|---|---|---|
| `turn off web search` | `settings_bool` | applies, through `jarvis_settings_registry.set_web_search` |
| `turn on the prompt coach` | `settings_bool` | applies |
| `turn off background learning` | `settings_bool` | applies |
| `turn off picture mode` | `settings_bool` | applies |
| `turn on lights without asking` | `settings_bool` | **raises a card** (it loosens rule 4) |
| `stop asking before ...` | `settings_asks_first` | card, PC-only |
| `turn off weather`, `make the animal sharper` | `animal_*` | applies at once (cosmetic) |
| `switch to brave for search` | `search_use` | applies |
| `from now on be more plain` | `manner_from_now_on` | applies, with Undo |
| `hide the finance menu` | `menu_visibility` | applies |
| `turn off my work topic` | `topic_mode` | applies |
| **`what can I change?`** | **nothing — the AI model answered** | **invented an answer** |

**The tier rule is already implemented, in the right place.** Every setter in
`jarvis_settings_registry.py` returns an `Outcome` with `waiting=True` when a
card is up. So the rule "a loosening needs a card plus Windows Hello; tightening
and cosmetic changes are immediate" is **not** re-decided by the grammar — it
lives beside each setting, where it belongs. That is the single most important
fact in this design: **the conversational layer must route to those functions,
never re-classify a change itself.**

## 2. What is missing, and what this change adds

**Missing: Jarvis cannot tell the owner what it can change.** He asks, and the
model invents: it names switches that do not exist, and it never says that a
loosening still shows a card. That is the gap this slice closes.

Added by `feat/models-on-d-and-storage-tiers` (PR #229):

- **`jarvis_settings_registry.changeable_settings()` / `changeable_words()`** —
  the answer to "what can I change", **derived from `BOOL_SETTINGS`**, so it
  cannot promise a setting that is not there and cannot miss one that is. A
  switch added to the table appears by itself.
- **A `settings_help` intent** in `jarvis_quick` for "what can I change",
  "what settings can I change", "what can I change by talking to you", "which
  settings can I change", "what settings do you have", "list my settings", and
  "what can I change in settings".
- **The answer says three things plainly:** these can be changed by asking;
  anything that loosens a rule still shows a card first; and `undo` takes a
  change back in the same chat.
- **`backend/test_settings_help.py`** (43 checks) — every phrase routes to
  `settings_help`; a loosening still routes to its own intent; the added-switch
  test proves the list is derived rather than typed out.

## 3. The rules this must keep — none of them move

1. **Tier rule.** Anything that *loosens* still needs its card plus Windows
   Hello; tightening and cosmetic changes stay immediate. The help answer
   states this in words, so it can never be read as "everything happens at
   once".
2. **Ask before what cannot be undone** — forgetting, erasing, turning chat
   history off. Those keep their own cards.
3. **The write path must be one the gate already sanctions.** Settings live in
   `jarvis-framework.toml`, which is in the gate's `_PROTECTED` list, so a new
   tool writing it would be refused at tier `never` — the exact bug fixed today
   in PRs #225 and #227. Every change here goes through the **existing
   `set_*` function** the matching Settings toggle already calls. **No new write
   path is created.**
4. **`POST /api/config` stays 501.** The conversational path is
   backend-internal, not a new public write route.
5. **Say what changed, and offer Undo** — the existing "from now on" pattern.

## 4. What is deliberately NOT promised by "what can I change"

- **The pick-one settings** (web search provider, weather source). They work by
  their own phrasings today (`switch to brave for search`), but naming them in a
  generic list would promise a phrasing that does not match yet. Either widen the
  grammar to match them or leave them out — do not advertise them.
- **`stop learning about money` reached the AI model**, not the grammar, on
  2026-10-10 (topics need an existing topic, per the checklist's
  preconditions). Worth a follow-up: the topic path exists
  (`topic_mode`), so this is a grammar gap, not a missing feature.

## 5. Next slices, in order

1. **Widen the help answer to the pick-one settings** once each has a matched
   phrasing, and add "is X on?" for the switches (the `on_word`/`off_word`
   fields in `BoolSetting` were left there for exactly this).
2. **A safe "from now on" sweep** for the settings that are cosmetic, each with
   Undo already present.
3. **A test that a loosening request still raises its card**, end to end through
   the real gate — the same shape as decision 1's gate tests.

## 6. Anything that needs the owner

Nothing in this slice. The one open question is whether the phone should offer
the same "what can I change?" answer; the phone is another conversation's
surface, and `CLAUDE.md` says deep config editing stays off the phone, so this
stays a PC answer until he says otherwise.
