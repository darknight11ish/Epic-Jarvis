# Cutting-edge audit, round 2, 2026-09-26: trust, safety and robustness

One slice of "What else can we add?": what makes a local assistant
**dependable** against planted instructions, lost data, bad updates, crashes
and stolen keys. **Research only. Nothing was built and no code was changed.**
It does not repeat `RESEARCH-2026-09-24.md` §4 (CaMeL, SecAlign, NeMo,
mcp-scan already turned down), `APPROVAL-GAP-DESIGN.md` (Windows Hello,
KeyCredentialManager, the phone key in outline), `DEPS-TESTS-CI-AUDIT` (the
updater's empty minisign key) or the round-1 reports.

**How it was checked.** Jarvis read at commit `43f04ed`; every file:line below
was opened. Read myself: raw GitHub files (licences, READMEs, changelogs of
AgentDojo, garak, promptfoo, CaMeL, pip, cryptography, age, restic,
Tailscale's `whois.go`, Microsoft's WER docs source), PyPI metadata, and
Anthropic's auto-mode post. **Blocked:** arxiv.org, github.com pages,
huggingface.co, kde.org, learn.microsoft.com and some blogs; those are marked
**(summary)** (search results only). Paper and vendor numbers are **claims**.
Nothing was run or measured on the owner's PC.

## In six lines, for the owner

1. **Jarvis's core defence is the right one in 2026.** Research has moved to "enforce safety outside the model" - which is what the approval card already is. Detectors and labels only warn; defence-aware attacks beat them.
2. **First, measure:** a test on your PC that feeds planted instructions to the real model and counts how many *attacker-made cards* you would have seen. Judge every other safety idea by that number.
3. **Your data has no way back in.** Memory can be exported but not restored, and the chat-history key lives only in this Windows account. An **encrypted backup with a recovery code** fixes both.
4. **Jarvis does not restart itself after a crash, and leaves nothing behind to explain one.** A small watchdog and "what was it doing when it froze" notes, kept on the PC, fix that.
5. **QR pairing and the phone's half of the approval fix now have a concrete design:** a one-time secret in the QR code, a key locked in the phone's security chip, matching words on both screens, and a fingerprint-signed yes for risky cards.
6. **Not for Jarvis:** an AI that approves for you, cloud backups, passkeys over the home network, and red-team tools that phone home by default.

## Where Jarvis stands, against the 2026 defences

In `backend/jarvis_agent.py`, tool results are stripped of chat markers until
nothing changes (`strip_chat_markers`, :2337), labelled as data
(`OUTSIDE_FIELD`/`OUTSIDE_NOTE`, :2261-2268), scanned for warning signs
(`outside_flags`, :2380; rules at `jarvis_intake.py:975`) and tracked per
turn (`_TurnWatch`, :2451). Only `typed` and `voice` are the owner's words
(`OWN_WORDS`, :2300). After outside text, note writes need a card (:1264),
every card says which values came from what was read (`shaped_by`, :2607),
and the conversation stays marked (`jarvis_chat_log.py:860`).

| 2026 approach | What it is | Jarvis today |
|---|---|---|
| **Out-of-band enforcement** (CaMeL, FIDES, Progent) | A rule outside the model decides what a tool call may do | **Has it**: the gate, one card per action - a person, not a policy engine |
| **Information-flow labels** (FIDES, CaMeL) | Every *value* is labelled trusted/untrusted, public/private; a tool can refuse untrusted inputs | **Coarser**: the whole *turn* is marked; values are matched only for the card's words (`_ARG_PIECE`, :2430) |
| **Dual LLM / quarantined reader** | A tool-less model reads untrusted text; the tool-using model never sees it raw | **No** |
| **Spotlighting** (Microsoft) | Delimit, datamark (a mark between words) or encode outside text | **Delimiting only** (the label) |
| **Detectors** (Prompt Guard 2, ProtectAI DeBERTa) | A small classifier flags injection-like text | **Pattern rules** (33 of 46 AgentDojo goals, backend/README) |
| **Masked re-run** (MELON) | Re-run without the owner's request; the same tool call means the text drove it | **No** |

The evidence **(summary)**: out-of-band systems report near-zero attack
success on AgentDojo, but only on fixed tests; earlier work cited there broke
twelve in-model defences at over 90% with defence-aware attacks. In one small
test, Progent cut attack success from 25.8% to 4.2% and a hand-made adaptive
attack did not raise it ("Adaptive Evaluation of Out-of-Band Defenses", June
2026). **For Jarvis:** the card stays the wall; every model-side idea below
only *reduces attacker-made cards and sharpens their warnings*.

## Ranked list

Size: S = one module plus tests; M = several files, maybe a line in both
apps; L = a new subsystem.

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | Planted-instruction test with the **real** model, on the PC | Turns "is Jarvis safe?" into a number; decides ideas 10-14 | S-M | none (offline) |
| 2 | Encrypted backup with a recovery code, and a plain restore | A dead disk or a Windows reinstall loses memory and history today | M | low (local only; restore is a card) |
| 3 | Data health in the preflight: database check, disk space, backup age, keys present | Catches a damaged file before it becomes lost memory | S | none |
| 4 | Watchdog: restart the backend after a crash, at most 3 times | Jarvis stays up overnight; today it stays down | S-M | none |
| 5 | Hang and crash notes kept on the PC | "It froze" becomes a stack you can send | S | low (stays on PC) |
| 6 | QR pairing with per-device keys (the queued "more devices") | Ends the 43-character token; a lost phone is removable alone | L | low if built as below |
| 7 | Approval gap step 2: a fingerprint-signed yes from the phone | Closes the "stolen token on another device" row | M (inside 6) | lowers it |
| 8 | A ledger of decisions, counts only | Spots rubber-stamping (93% of prompts approved, Anthropic) | S-M | none |
| 9 | Safer backend updates: staged install, preflight, one step back; pinned packages with a 7-day wait | A bad update or poisoned package is caught before it runs | M | none |
| 10 | Value-level labels on tool arguments (FIDES/Progent-lite) | Per-argument warnings: "this address came from the email" | M | none if stricter only |
| 11 | A tool-less "reader" pass for email and web text | The tool-using model sees a short fixed form, not raw text | M | none |
| 12 | Masked re-run before a card after outside text (MELON idea) | Labels the card "your question did not lead here" | M | none (label only) |
| 13 | Datamarking of tool output | Free; may cut obedience in small models (unmeasured) | S | none |
| 14 | Small injection classifier as a second warning | May catch the quiet goals the patterns miss | S-M | none (warning only) |
| 15 | `tailscale whois` to name the device; Tailnet Lock | "Approved on Pixel 8"; no device added behind your back | S | none |
| 16 | Windows crash dumps kept on the PC (WER LocalDumps) | Native crashes (voice, vector search) become diagnosable | S | medium: dumps can hold secrets |

## Details

**1. Planted-instruction test with the real model.** `test_injection_cases.py`
runs AgentDojo's 46 goals through the real loop with a *scripted, obedient*
model: it proves the wall holds, not how often `qwen3:8b` obeys. Add
`tools/tool_eval/injection_eval.py` beside `ollama_tool_eval.py`: Jarvis's
real tool schemas, fake email/web/file results carrying the attack texts in
`backend/agentdojo_injections.json` plus a sample of LLMail-Inject emails,
against the local Ollama. Score: how often the model proposes the attacker's
call (= a card you would see), how often the warning fires, and ordinary-task
success - with and without ideas 10-14. **Sources:** AgentDojo (MIT, checked;
v0.1.35, Oct 2025; it can target any OpenAI-compatible endpoint, which Ollama
is, and ships `tool_filter`, `spotlighting_with_delimiting`,
`repeat_user_prompt` and a detector as defences); LLMail-Inject (Microsoft's
email-assistant challenge; repo MIT, checked; dataset licence not checked).
InjecAgent (1,054 cases) has **no licence file**: run locally, never copy in.

**2. Encrypted backup and plain restore.** Today `/api/memory/export` saves
every fact as **plain JSON** (`jarvis-desktop/src-tauri/src/brain.rs:527`),
nothing imports or restores (`JARVIS-API.md` searched), and the chat-history
key exists only in this account's Credential Manager (`jarvis_chat_log.py:112`).
Design - "Back up now" in the desktop's Settings, optionally weekly on the one
scheduler - making one file:
1. Snapshots with SQLite's online backup API (`sqlite3.Connection.backup`,
   safe while running): `memory.db`, `history.db`, `schedule.db`,
   `feedback.db`; plus the `*.json` settings, `jarvis-framework.toml`, the
   notes folder, the voice enrolment and the chat-history key. **Not** the
   pairing token, API keys (re-entered; rule 3), models or logs.
2. Encrypts the zip in the **age** format with a **recovery code** shown once.
   age (BSD-3, v1.3.2; Python binding `pyrage`, MIT) means that if Jarvis is
   broken, one command, `age -d`, still opens it. No-new-package alternative:
   AES-GCM plus Argon2id from `cryptography` (Argon2id since 44.0.0) - but
   then only Jarvis can open it.

Restore: pick the file, type the code, see counts and date (never content),
then **one card plus Windows Hello**; the current state is backed up first,
so a restore can be undone. The phone shows "last backup: 3 days ago" only
(ARCHITECTURE §8, one-sided on purpose). **Honest limit:** "Erase the words"
cannot reach old backups; the Forget screen and restore card must say so.

**3. Data health in the preflight.** `selftest.py --preflight` (:742-1611)
checks live chains, not data: no `PRAGMA quick_check` anywhere in `backend/`
(searched), free disk only for the big model (`jarvis_big_model.py:296`).
Add one read-only check: `quick_check` per database, free space, backup age,
and whether the chat-history key exists (not read). WARN, never fix.

**4. Watchdog.** The desktop supervises the backend (`sidecar.rs`) but only
restarts it from the tray (`sidecar.rs:396`). Add: with supervision on, if
the process exits or `/api/status` is silent for 60 s, restart - at most 3
times in 10 minutes, then stop and say so (question 2). Safe under the rules:
a card waiting at a restart is refused, and the approval stamp's secret is
new each start (`jarvis_owner_check.py:241`).

**5. Hang and crash notes.** Python's `faulthandler` (stdlib) writes every
thread's stack to a file on a native crash, and
`dump_traceback_later(60, repeat=True, file=f)` writes one when a heartbeat
stops. Rust: a `std::panic::set_hook` panic file (none exists; searched).
Kept in `.openjarvis/crash/`, newest 10. `jarvis_scrub.py:71` says it cannot
scrub faulthandler's writes, so a "prepare a bug report" step scrubs them
before anything is shared.

**6. QR pairing with per-device keys.**
- **The QR code carries** the address, a **one-time 128-bit secret**, the PC
  key's fingerprint and a 10-minute expiry (as OpenClaw, per
  `COMPETITORS-OPEN-SOURCE`). 128 bits cannot be guessed; no special protocol.
- **The phone makes its own key** in Android Keystore (EC P-256; StrongBox
  when present via `setIsStrongBoxBacked(true)`, else the TEE) and sends
  **key attestation**: a certificate chain proving a real phone's security
  chip holds the key, for the Jarvis app. The PC checks it **offline**
  against **both** Google roots: the old RSA one and the new P-384 one, used
  exclusively by RKP phones since 10 April 2026 **(summary)**. A program on
  the PC that photographed the QR code cannot fake that.
- **One card on the PC** with Windows Hello, showing **four words both
  screens show**, made from both keys *and* fresh randomness - KDE Connect's
  2025 advisory: a short code from long-lived keys alone was brute-forceable,
  so they added a time part **(summary)**.
- **A token per device**, listed in both apps with its own Remove; the old
  shared token works until the owner retires it.
- **The typed backup code** is short, so it is accepted only over encrypted
  links (loopback, Tailscale, Meshnet; not plain http at home) and burns
  after 3 wrong tries. A PAKE (makes a short code safe even from a listener:
  SPAKE2, RFC 9382; CPace, a CFRG draft) is the upgrade; Python `spake2`
  (MIT) not checked for RFC compatibility, no Android library checked.
Plugs into `jarvis_token_store.py`, `TokenStore.kt:104` and
`jarvis_owner_check.from_this_pc` (:211).

**7. Approval gap step 2.** Today the phone's prompt is tied to no key:
`BiometricGate.kt:189` calls `prompt.authenticate(builder.build())` without a
`CryptoObject`. Step 2: a second Keystore key with
`setUserAuthenticationParameters(0, AUTH_BIOMETRIC_STRONG or
AUTH_DEVICE_CREDENTIAL)` (fresh check per use), the prompt given a
`CryptoObject(Signature)`, signing *card id + one-time number + hash of the
card's words*; the backend verifies with `cryptography`. Design around: face
unlock on many phones is "Class 2" and cannot unlock such a key, though the
PIN can (Android docs, not re-read); **Android Protected Confirmation**, where
the chip itself shows the words, is **deprecated** and was Pixel-only.

**8. A ledger of decisions.** Anthropic: Claude Code users "approve 93% of
permission prompts", which "leads to approval fatigue" (read myself, 25
March 2026). Keep, per card, only action, outcome, seconds to decide, "shaped
by outside text" and warning codes - the `jarvis_speed.py` pattern (a fixed
list of fields, text dropped in code). Both apps, weekly: "12 cards, 11
approved, 7 in under 2 seconds." It informs the owner's "What asks first"
choices and **never** changes a tier itself (rule 4).

**9. Safer backend updates.** Today: `git pull`, then `apply-patches.ps1`,
which backs up changed files (:1243-1276) and has `-Revert` (:1019).
Missing: proof the new version works before it runs, and package pinning.
- **Staged install:** apply into a copy, run `--preflight` on it, switch only
  on a pass; one command switches back.
- **Pinned packages:** hash-locked requirements (`--require-hashes` or the
  new `pylock.toml`) and `--uploaded-prior-to P7D` (pip 26.0, Jan 2026; day
  form since 26.1): a hijacked release has a week to be caught first.
- **Optional:** a CI-built bundle with a GitHub artifact attestation (Sigstore;
  `sigstore` 4.5.0, Apache-2.0). It proves "built by this repo's CI from
  commit X", not that the code is good. TUF (`tuf` 7.0.1) is too big here.

**10. Value-level labels.** FIDES (Microsoft Agent Framework, MIT, v1.3.0, May
2026) labels values and lets a tool declare `accepts_untrusted=False`; a
breach becomes an approval request. Jarvis step: each tool names its
**sensitive arguments** (recipients, a command, a path, a URL); an
outside-sourced value there gets a top-of-card line and makes the card
"heavy". Optional owner policies, Progent-style ("email only addresses I have
written to"). **Stricter only**; any loosening is the owner's call, not
proposed here.

**11. A tool-less reader pass.** The "quarantined model", made small: after
`email_check` or `web_search`, the local model is asked once **with no
tools** to fill a fixed form through Ollama's `format` (already chosen,
ARCHITECTURE §11): sender, subject, a 300-character summary, dates,
`asks_you_to_act`. The loop sees the form; raw text only on request. One
extra model call per read; still outside text. Build only if idea 1 shows
fewer attacker cards.

**12. Masked re-run (MELON, ICML 2025).** Before a card in a turn shaped by
outside text, re-ask with the owner's request replaced by "summarise this";
the same call means the text drove it, and the card says so. Strong AgentDojo
results **(claim)**; no licence file in its repo, so the idea only.

**13. Datamarking.** Spotlighting marks every word of outside text; the paper
reports attack success from over 50% to under 2% **on GPT-family models
(claim)**, small models untested. Free in `_tool_content`
(`jarvis_agent.py:2077`); measure with idea 1 (it may hurt reading).

**14. A second, learned warning.** `protectai/deberta-v3-base-prompt-injection-v2`
(AgentDojo's own detector) or Prompt Guard 2 22M (Llama 4 Community License,
gated), on the processor via onnxruntime (installed). Warning only; check
false alarms on the 383 ordinary texts. Model licences not checked.

**15. Tailscale.** `tailscale whois --json <ip>` (read in `whois.go`, BSD-3)
names the machine and user behind a 100.x address: cards can say "approved on
Pixel 8", and `from_this_pc` gets a second opinion. **Tailnet Lock** (GA July
2025 **(summary)**) stops Tailscale's servers adding a device without your
signature; an access rule can let only the phone reach Jarvis's port. Both
owner-side settings for `INSTALL.md`. Meshnet: no equivalent checked.

**16. Windows crash dumps.** WER keeps a dump of a crashed program locally
when `HKLM\...\Windows Error Reporting\LocalDumps\<program>.exe` exists
(admin once; `DumpType` 1 = mini dump; `DumpCount` keeps the newest N; works
with reporting to Microsoft off - Microsoft's docs source, read). **Your
call:** even a mini dump can hold pieces of memory, such as the token.
**Not ranked - TPM/VBS keys** (`NCRYPT_USE_VIRTUAL_ISOLATION_FLAG`): cannot be
copied off the PC **(summary)**, but any program of yours can still *use*
them (the same-user limit, `APPROVAL-GAP-DESIGN.md` §2). For the chat-history
key only after backups exist: a cleared TPM would lose the history for good.

## Not for Jarvis

- **An AI that approves for you** (Claude Code's "auto mode" classifier).
  Rule 4, invariant 3. The 93% figure argues for fewer, better cards (8, 10).
- **Cloud backups** (restic or Kopia to S3/B2, Google Drive), even encrypted:
  stored memory leaves the PC (rule 1). restic (BSD-2, 0.19.1) to a USB drive
  is fine if preferred to idea 2.
- **Passkeys/WebAuthn at home:** they need a real domain and a public HTTPS
  certificate (`tailscale cert` puts the PC's name in public certificate
  logs, as Tailscale warns; not re-read), and phone passkeys sync through
  Google. The Keystore key (6) proves the same without that.
- **Base64 "encoding" spotlighting:** reported only with large cloud models;
  an 8B model cannot reliably read base64.
- **Full CaMeL** (turned down 09-24): its README calls it "a research
  artifact" whose interpreter "likely contains bugs".
- **promptfoo as shipped** (MIT; OpenAI's since March 2026): telemetry on by
  default, red-team generation falls back to its servers, and its docs say
  the off switch "is not a network egress firewall". **garak** (Apache-2.0,
  Ollama driver) is fine offline but tests the model, not Jarvis's loop.
- **Android Protected Confirmation:** deprecated.
- **The backend as a Windows service:** services run in session 0, with no
  desktop, so window control, microphone and Windows Hello prompts break.
- **An extra Noise channel:** Tailscale and Meshnet already are WireGuard, a
  Noise protocol; plain http at home is handled by idea 6's rule.
- **Online attestation revocation checks, crash services (Sentry):** new
  outbound requests carrying device or crash data.
- **A detector as a block:** defence-aware attacks beat them (above).

## Questions for the owner

**1. Where may backups be saved?** They are encrypted, but hold everything
Jarvis knows.
- **This PC or a USB drive only** (recommended)
- **Also a shared folder on your home network**

**2. If the backend crashes, should the desktop app restart it?**
- **Yes, up to 3 times in 10 minutes, then stop and tell me** (recommended)
- **No, I will restart it myself**

## Sources

- Papers **(summary)**: [Adaptive Evaluation of Out-of-Band Defenses, 2606.26479](https://arxiv.org/abs/2606.26479) · [Design Patterns for Securing LLM Agents, 2506.08837](https://arxiv.org/abs/2506.08837) · [CaMeLoT, 2609.18674](https://arxiv.org/abs/2609.18674) · [Spotlighting, 2403.14720](https://arxiv.org/abs/2403.14720) · [MELON, 2502.05174](https://arxiv.org/abs/2502.05174)
- Defences: [CaMeL code, Apache-2.0](https://github.com/google-research/camel-prompt-injection) · [FIDES, agent-framework #5624 (MIT)](https://github.com/microsoft/agent-framework/discussions/5624) · [MSRC on indirect injection](https://www.microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks) (summary) · [MELON repo](https://github.com/kaijiezhu11/MELON) · [Prompt Guard 2 card](https://github.com/meta-llama/PurpleLlama/blob/main/Llama-Prompt-Guard-2/86M/MODEL_CARD.md) (summary)
- Tests: [AgentDojo, MIT](https://github.com/ethz-spylab/agentdojo) · [LLMail-Inject, MIT](https://github.com/microsoft/llmail-inject-challenge) · [InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent) · [garak, Apache-2.0](https://github.com/NVIDIA/garak) · [promptfoo, MIT](https://github.com/promptfoo/promptfoo) · [OpenAI to acquire Promptfoo](https://openai.com/index/openai-to-acquire-promptfoo/) (summary)
- [Anthropic: Claude Code auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode)
- Backup and updates: [age, BSD-3](https://github.com/FiloSottile/age) · [pyrage, MIT](https://github.com/woodruffw/pyrage) · [restic, BSD-2](https://github.com/restic/restic) · [cryptography changelog](https://github.com/pyca/cryptography/blob/main/CHANGELOG.rst) · [pip NEWS](https://github.com/pypa/pip/blob/main/NEWS.rst) · [python-tuf](https://github.com/theupdateframework/python-tuf) · [sigstore-python](https://github.com/sigstore/sigstore-python)
- Pairing: [RFC 9382 SPAKE2](https://datatracker.ietf.org/doc/rfc9382/) · [CPace draft](https://datatracker.ietf.org/doc/draft-irtf-cfrg-cpace/) · [RFC 9807 OPAQUE](https://datatracker.ietf.org/doc/rfc9807/) · [KDE Connect advisory 2025-04-18](https://kde.org/info/security/advisory-20250418-3.txt) (all summary)
- Keys: [Android attestation root change, 2026](https://bayton.org/android/android-enterprise-faq/key-attestation-root-certificate-change/) (summary) · [Android Protected Confirmation](https://developer.android.com/privacy-and-security/security-android-protected-confirmation) (summary) · [Windows VBS key protection](https://techcommunity.microsoft.com/blog/windows-itpro-blog/advancing-key-protection-in-windows-using-vbs/4050988) (summary)
- PC health: [WER "Collecting User-Mode Dumps" (MicrosoftDocs source)](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/wer/collecting-user-mode-dumps.md) · [Tailscale `whois.go`](https://github.com/tailscale/tailscale/blob/main/cmd/tailscale/cli/whois.go) · [Tailnet Lock GA](https://tailscale.com/blog/tailnet-lock-ga) (summary)
