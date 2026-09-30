# Report 15 (audit), agent af9505b3, 2026-09-29T21:04Z

> **What it was asked** (first 600 characters of the task): Check what merged in PR #34 (screen 'Look at this'/'Watch with me', chat-picture cleaning, secret rules, Kokoro v1.0 voices, custom voices) and PR #33 (encrypted captured phone notifications, inbox-tidy Undo limit, animal-face fixes, EventStream buffer) against the five non-negotiable rules and every owner decision in CLAUDE.md and docs/ARCHITECTURE.md. `main` is checked out read-only at /tmp/main34 (use `git -C /tmp/main34 diff 7df0be91 0fdd81be` for #34 and `git -C /tmp/main34 log` for #33; ignore docs/SOURCE-BUNDLE.md). Look for: screen images or text leaving the PC, anything saved to disk 

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

RULES CHECK: PR #34 (0fdd81be, diff 7df0be91..0fdd81be) and PR #33 (7df0be91, diff 7df0be91^1..7df0be91). Read-only. I read the code and docs; I did not run any tests. Line numbers are in /tmp/main34. I also read `.claude/agents/JARVIS-TODAY.md`.

**Bottom line:** none of the five rules is broken. I found no screen picture or screen text leaving the PC. I found no plain-text disk write of screen content. I found no voice cloning of the owner. I found no new outward path that is missing from ARCHITECTURE §4. There are 2 real gaps, 2 smaller ones, and some doc drift.

**Verdict table**

| Item | Verdict |
|---|---|
| Screen Look at this / Watch with me: PC side (`jarvis_screen.py`, `jarvis_screen_win.py`, `look.rs`) | KEEPS THE RULES |
| Router keeps a screen turn on the PC (`screen.patch`, `has_screen`) | KEEPS THE RULES |
| Screen turn counted as a read: notes, web search, plan card, email all ask after it | KEEPS THE RULES |
| Crisis handling on screen turns | KEEPS THE RULES |
| Picture mode (`jarvis_screen_picture.py`, gate `screen_picture_enable`, tier ask) | NEEDS A CARD (has one) |
| Chat-picture cleaning (`jarvis_chat_picture.py`) and Photo-to-reminder cleaning | KEEPS THE RULES |
| Secret rules (`jarvis_secrets.py`, `jarvis_secret_rules.py`, gitleaks/Presidio credit) | KEEPS THE RULES |
| Phone screen: assistant gesture (words only, off by default, fingerprint to turn on) | KEEPS THE RULES |
| Phone "Watch this phone with me" | NEEDS THE OWNER (gap 1) |
| Kokoro v1.0 and the "Hear it" button | KEEPS THE RULES |
| Ashby and Clara blended voices | NEEDS A LOOK (gap 2) |
| #33 encrypted captured phone notifications | KEEPS THE RULES |
| #33 inbox tidy: no sixth Undo | KEEPS THE RULES |
| #33 animal-face fixes and quick-command changes | KEEPS THE RULES |
| #33 EventStream unbounded buffer | KEEPS THE RULES (one note) |
| Docs and CLAUDE.md | Drift found (below) |

**Gap 1: the phone's Watch has no password-box pause (NEEDS THE OWNER)**
- **The decision:** CLAUDE.md, 2026-09-28: Watch with me is "pausing on password fields and on apps the owner excludes (banking)".
- **What the code does:** on the phone, `ScreenWatch.decide` at `jarvis-client/.../net/ScreenWatch.kt:216` checks only these things:
  - the screen is off;
  - the app in front is unknown;
  - an app is on the Never look at list or is a bank/password-manager app;
  - the picture is almost black.
- **What is missing:** it has no password-box, private-window or on-screen-keyboard check.
- **What partly covers it:** the PC blacks out secret-shaped words in the frame. The docs already say a password shown with a "show" eye is not caught (`docs/SCREEN-DESIGN.md:202-204,272`).
- **The docs gap:** the docs never say that the phone's Watch cannot pause on password boxes. ARCHITECTURE §8 item (f) only covers the missing "windows behind" and the private-window pause. The Never look at text in `ScreenNever.kt:97` warns "Android does not always mark them".
- **Suggested fix:** write the gap into §8 and JARVIS-API §96. Either the owner accepts it, or the phone's Watch takes a picture only when the assistant structure says no password field is focused.
- This is unverified on a real phone.

**Gap 2: Ashby and Clara can be spoken without the owner-voice check (NEEDS A LOOK, rule-adjacent to "never the owner's voice")**
- **The decision:** CLAUDE.md, 2026-09-28: animal voices must pass the "not the owner's voice" check. The 2026-09-29 decision says each blend passes it too.
- **The problem:** the speaking path is fail-open.
  - `backend/jarvis_voices.py:453` reads `if got in K.MIX and blend_refused(got)`.
  - `blend_refused` (`:712-714`) returns False when no verdict is kept.
  - Verdicts live only in memory: `_BLEND_CHECKS`.
  - They are keyed on the voice-print fingerprint (`_blend_key`).
- **When this bites:** after every Jarvis restart, and after the owner retrains their voice print, a saved Ashby or Clara speaks with no check.
- **Where the re-check runs:** `_recheck_saved_blend` is called only from `speaker_view` (`:582`), meaning only when an app fetches GET /api/voice/voices.
- **Second hole:** with no voice print trained, `owner_check` lets the blend through (comment at `:668-673`). The comment says it is re-checked once trained, which relies on that same `speaker_view` call.
- **Fix:** run `blend_check` (or the re-check) at engine build or first speech, and treat "not checked yet" as "use the pack default", the way a failed check already does.
- **What is fine:** animals never use blends. `builtin_voice` (`:1130`) uses `pack_kind()` for animals. Nothing copies the owner's voice. `Hear it` and choosing a blend both run the check.

**Smaller items**
- **Failed screen read leaves the original message (fail-open shape, low risk):** `jarvis_screen.py:1134-1135`, `with_screen`'s `except Exception` returns the ORIGINAL messages. A raw `screen_text` part and an uncleaned phone picture stay in the message.
  - The `screen_text` part is not text-typed, so `_text_of` drops it from the model input (`jarvis_agent.py:3396`).
  - The picture is still cleaned by `clean_attached_pictures`, and `_phone_screen_turn` keeps it off the vision lane.
  - So nothing raw reaches a model today, but this rests on those later stages.
  - Better: return the messages with the screen parts removed.
- **Lockdown and the What-asks-first page do not mention looking (owner's call):** `jarvis_reach.py` and `jarvis_asks_first.py` have rows only for `screen_picture_enable`. There is no row for "Look at this" or "Watch with me" (no card, sign on screen). Lockdown does not stop or refuse a running watch. The 2026-09-26 decision says that page "lists every action and whether it asks". Suggest one row, and Lockdown ending a watch.
- **Any local program can trigger a look (documented limit, no action needed):** `is_local` accepts the PC's own Tailscale address (`jarvis_screen.py:1715-1737`). A program on the PC holding the token could call `do:look` and then a chat with `screen:"look"`. That program can already screenshot on its own. The sign stays on screen.
- **#33 EventStream: `.buffer(Channel.UNLIMITED)` (`EventStream.kt:281`):**
  - Rule 4 (blocking action on a stale stream) still looks intact. Alive signals queue behind events, so ordering holds.
  - It means a replayed old `approval` event can reach the collector late. The server still decides validity.
  - I did not check the staleness watchdog against a backlog test.

**Checked and clean**
- **Screen words and images:**
  - Nothing is written to disk. `jarvis_ocr.py:218` is an in-memory writer, and the PowerShell fallback uses stdin.
  - The only writes are the picture-mode switch and measurement files, and Ollama's own log at `jarvis_screen_picture.py:867`.
  - Chat history (`jarvis_chat_log.py:320`) reads only `text` parts. `screen_text` is ignored and images are only flagged.
  - `screen` is stripped before the model (`temporary-chat.patch`).
  - The phone code logs no content.
- **Egress:**
  - Picture mode runs its own Ollama on 127.0.0.1 with `CUDA_VISIBLE_DEVICES=-1` and `OLLAMA_NO_CLOUD=1` (`jarvis_screen_picture.py:733`). It refuses `-cloud` model names (`:300-303`) and gets no token in its environment.
  - The model is downloaded by an owner-pasted line, and so is the Kokoro pack. Neither is a Jarvis egress path.
  - The phone sends screen text and pictures only inside the chat request to the PC. So no new §4 row is needed. The phone update-check row was added by #33.
- **Cards:**
  - Picture mode on is one card (`screen-picture.patch`), and off is instant.
  - It has a voice and chat second door in `jarvis_settings_registry.py`, which raises the same card.
  - The Never look at list: adding is instant, removing is one card, and the list is PC-only.
- **Approval-gap items:**
  - Removing an app from the phone's list asks for a fingerprint. Turning on the phone's gesture asks for a fingerprint.
  - Under App lock, the desktop holds looks (`look.rs:262`), and the phone waits for the unlock (`ScreenLook.kt:37`). The badge stays visible on purpose (`look.rs:582`), matching the 2026-09-27 App-lock decision.
- **Crisis:** crisis is computed from `newest_own_words` (`jarvis_agent.py:3530`), so screen text never triggers or feeds it. Screen words are added after the crisis decision. Learning is excluded because the turn records a read.
- **Credits:** `THIRD-PARTY-NOTICES.txt` credits gitleaks, Presidio, winocr, pywinrt and MiniCPM-V.
- **#33 phone notifications:** the store is now AES-GCM in the Android Keystore, and drops rows rather than falling back to plain text. `CapturedNotifications.kt` is fine. One side effect: it cannot be read before the first unlock.
- **#33 inbox tidy:** a sixth Undo is refused both in `plan()` and in `run()`. That is stricter and needs no extra card.
- **Header and token:** no token logging in the new desktop screen code (`look.rs`).

**Doc drift to fix**
1. `.claude/agents/JARVIS-TODAY.md:170` says "Words only on one graphics card - no model is shown a picture". Picture mode is built (off by default) and JARVIS-TODAY never mentions it. Add it, and fix the "Decided but not built" line (`:215`), which lists talk-to-type and others as built but not the screen items.
2. `CLAUDE.md:742-743` ("Full picture understanding needs the 12 GB card; with one card, Jarvis reads the screen's text only") is now superseded. The reversal is only recorded at `CLAUDE.md:1588`. Add a pointer at line 742.
3. `CLAUDE.md:699` queue item 5, "finishing the screen feature", is not marked built. #34 built it, with limits. Nothing else in CLAUDE.md marks it done.
4. ARCHITECTURE §8 item (b) says the phone has "no phone notification yet" for the PC's watching. It does show a Home plate (`HomeScreen.kt PcWatchingPlate`). This is small.
5. Gap 1 is not written down anywhere. See above.

**Hardware note:**
- **Picture mode:** works with one card (0 GB of graphics memory). It is slow and needs processor and RAM. It is unmeasured, and the model tag `minicpm-v:4.6` is unverified (`docs/MODEL-TOPOLOGY.md:544`).
- **Screen looks and Watch:** words only, so one card or two.
- **Camera and Live pictures:** still wait for the 12 GB card.
- **Blend voices:** processor only.

Key files:
- /tmp/main34/backend/jarvis_voices.py (lines 453, 527, 582, 712, 775)
- /tmp/main34/backend/jarvis_screen.py (lines 1050-1136, 1715)
- /tmp/main34/backend/jarvis_screen_picture.py
- /tmp/main34/jarvis-client/app/src/main/java/com/jarvis/client/net/ScreenWatch.kt (line 216)
- /tmp/main34/docs/ARCHITECTURE.md (§8 screen row, around line 1954)
- /tmp/main34/.claude/agents/JARVIS-TODAY.md (line 170)
- /tmp/main34/CLAUDE.md (lines 699, 742, 1588)
