# Cutting-edge audit, round 2, 2026-09-26: trust, safety and robustness

One slice of "What else can we add?": the technology that makes a local
assistant **dependable** - against planted instructions, lost data, bad
updates, crashes and stolen keys. **Research only. Nothing was built and no
code was changed.** It builds on, and does not repeat, `RESEARCH-2026-09-24.md`
§4 (planted instructions; CaMeL, SecAlign, NeMo and mcp-scan already turned
down), `APPROVAL-GAP-DESIGN.md` (Windows Hello, KeyCredentialManager, the
phone's per-use key in outline), `DEPS-TESTS-CI-AUDIT-2026-09-26.md` (the
desktop updater's empty minisign key) and the round-1 reports.

**How it was checked.** Jarvis read at commit `43f04ed`; every file:line below
was opened. Read myself: raw GitHub files (licences, READMEs, changelogs of
AgentDojo, garak, promptfoo, CaMeL, pip, cryptography, age, restic,
Tailscale's `whois.go`, Microsoft's WER docs source), PyPI metadata, and
Anthropic's auto-mode post. **Blocked here:** arxiv.org, github.com pages,
huggingface.co, kde.org, simonwillison.net, neuraltrust.ai,
learn.microsoft.com. Papers and pages seen only through search results are
marked **(summary)**. Vendor and paper numbers are **claims**. Nothing was run
or measured on the owner's PC.

## In six lines, for the owner

1. **Jarvis's core defence is the right one in 2026.** Research has moved to "enforce safety outside the model" - which is what the approval card already is. Detectors and labels only warn; defence-aware attacks beat them.
2. **First, measure:** a test on your PC that feeds planted instructions to the real model and counts how many *attacker-made cards* you would have seen. Every other safety idea here should be judged by that number.
3. **Your data has no way back in.** Memory can be exported, but not restored, and the chat-history key lives only in this Windows account. An **encrypted backup with a recovery code** fixes both.
4. **Jarvis does not restart itself after a crash, and leaves nothing behind to explain one.** A small watchdog and "what was it doing when it hung" notes, kept on the PC, fix that.
5. **QR pairing and the phone's half of the approval fix now have a concrete design:** a one-time secret in the QR code, a key locked in the phone's security chip, matching words on both screens, and a fingerprint-signed yes for risky cards.
6. **Not for Jarvis:** an AI that approves for you, cloud backups, passkeys over the home network, and red-team tools that phone home by default.

## Where Jarvis stands today, against the 2026 defences

Jarvis's "outside text" model, read in `backend/jarvis_agent.py`: tool results
are stripped of chat markers until nothing changes (`strip_chat_markers`,
:2337), labelled as data (`OUTSIDE_FIELD`/`OUTSIDE_NOTE`, :2261-2268),
scanned for warning signs (`outside_flags`, :2380, rules in
`jarvis_intake.py:975`), and tracked per turn (`_TurnWatch`, :2451). Only
`typed` and `voice` count as the owner's words (`OWN_WORDS`, :2300). A turn
that read outside text puts note writes on a card (`NOTE_AFTER_OUTSIDE_ACTION`,
:1264), and every card says which values came from what was read
(`shaped_by`, :2607). The conversation stays marked afterwards
(`jarvis_chat_log.conversation_tainted`, :860). Nothing leaves or acts
without the gate.

| 2026 approach | What it is | Jarvis today |
|---|---|---|
| **Out-of-band enforcement** (CaMeL, FIDES, Progent) | A rule outside the model decides what a tool call may do | **Has it**: the gate and one card per action. Human, not a policy engine |
| **Information-flow labels** (FIDES, CaMeL) | Every *value* carries "trusted/untrusted" and "public/private"; a tool can refuse untrusted inputs | **Coarser**: the whole *turn* is marked. Values are matched by text only for the card's words (`_ARG_PIECE`, :2430) |
| **Dual LLM / quarantined reader** (CaMeL, FIDES) | A tool-less model reads the untrusted text; the tool-using model never sees it raw | **No**: the tool loop reads raw (cleaned, labelled) text |
| **Spotlighting** (Microsoft) | Delimit, datamark (a mark between every word) or encode outside text | **Delimiting only** (the label) |
| **Detectors** (Prompt Guard 2, ProtectAI DeBERTa) | A small classifier flags injection-looking text | **Pattern rules** (33 of 46 AgentDojo goals caught, backend/README) |
| **Masked re-run** (MELON) | Re-run without the owner's request; the same tool call means the text drove it | **No** |

The 2026 evidence **(summary)**: out-of-band systems report near-zero attack
success on AgentDojo, but only on fixed tests; defence-aware attacks broke
twelve in-band defences at over 90% ("Adaptive Evaluation of Out-of-Band
Defenses", June 2026). In its one small test, Progent held against an
adaptive attack (25.8% to 4.2%). **Conclusion for Jarvis:** keep the card as
the wall, and treat every model-side idea below as something that *reduces
attacker-made cards and sharpens their warnings*, never as a gate.

## Ranked list

Size: S = one module plus tests; M = several files, maybe a line in both
apps; L = a new subsystem.

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | Planted-instruction test with the **real** model, on the PC | Turns "is Jarvis safe?" into a number; decides ideas 7, 10, 11, 14 | S-M | none (offline) |
| 2 | Encrypted backup with a recovery code, and a plain restore | Today a dead disk or a Windows reinstall loses memory and history | M | low (local only; restore is a card) |
| 3 | Data health in the preflight: database check, disk space, backup age, keys present | Catches a damaged file before it becomes lost memory | S | none |
| 4 | Watchdog: restart the backend after a crash, at most 3 times | Jarvis stays up overnight; today it stays down | S-M | none (cards die with the process, as now) |
| 5 | Hang and crash notes kept on the PC (faulthandler, Rust panic file) | "It froze" becomes a stack you can send | S | low (paths in them; stays on PC) |
| 6 | QR pairing with per-device keys (the queued "more devices") | Ends the 43-character token; one lost device is removable alone | L | low if built as below |
| 7 | Approval gap step 2: a fingerprint-signed yes from the phone | Closes the "stolen token on another device" row | M (inside 6) | lowers it |
| 8 | "What was used and how fast I decided" ledger, counts only | Spots rubber-stamping (93% of prompts approved, Anthropic) | S-M | none |
| 9 | Safer backend updates: staged install, preflight, one-step back; pinned packages with a 7-day wait | A bad update or a poisoned package is caught before it runs | M | none |
| 10 | Value-level labels on tool arguments (FIDES/Progent-lite) | Stricter, per-argument warnings ("this address came from the email") | M | none if stricter only |
| 11 | A tool-less "reader" pass for email and web text (dual-LLM-lite) | The tool-using model sees a short, fixed-form summary, not the raw text | M | none |
| 12 | Masked re-run before a card after outside text (MELON idea) | Labels the card "your question did not lead here" | M | none (label only) |
| 13 | Datamarking of tool output | Free; may cut obedience in small models (unmeasured) | S | none |
| 14 | Small injection classifier as a second warning | May catch the quiet goals patterns miss | S-M | none (warning only) |
| 15 | `tailscale whois` to name the device behind a request; Tailnet Lock | Names "Pixel 8" on cards; blocks a node added behind your back | S | none |
| 16 | Windows crash dumps kept on the PC (WER LocalDumps) | Native crashes (voice, vectors) become diagnosable | S | medium: dumps can hold secrets; your call |

## Details

**1. Planted-instruction test with the real model.** `test_injection_cases.py`
already runs AgentDojo's 46 goals through the real loop with a *scripted,
obedient* model. It proves the wall holds; it cannot say how often the real
`qwen3:8b` obeys. Add `tools/tool_eval/injection_eval.py` beside
`ollama_tool_eval.py`: Jarvis's real tool schemas, fake email/web/file results
carrying AgentDojo's attack texts (`backend/agentdojo_injections.json`) and a
few hundred LLMail-Inject emails, run against the local Ollama. Score: how
often the model *proposes the attacker's call* (= a card you would see), how
often the card's warning fires, and ordinary-task success. Run it with and
without ideas 10-14. **Sources:** AgentDojo (MIT, checked; v0.1.35, Oct 2025;
it can itself target any OpenAI-compatible endpoint, which Ollama is, and has
built-in `tool_filter`, `spotlighting_with_delimiting`,
`repeat_user_prompt`, `transformers_pi_detector` defences); LLMail-Inject
(Microsoft's email-assistant challenge; repo MIT, checked; the dataset's
licence was not checked - huggingface is blocked). InjecAgent (1,054 cases):
**no licence file found**, so run it locally only and never copy it into the
repo. **Fits:** no card, nothing sent; runs only on the owner's PC.

**2. Encrypted backup and plain restore.** Today: `/api/memory/export` saves
every fact as **plain JSON** (`jarvis-desktop/src-tauri/src/brain.rs:527`),
and there is no import or restore route anywhere (`JARVIS-API.md` checked).
Chat history is encrypted with a key held only in this Windows account's
Credential Manager (`jarvis_chat_log.py:112`): lose the account, lose the
history. Design: "Back up now" in the desktop's Settings, and optionally a
kind on the one scheduler (weekly). It makes one file:
1. Snapshots each database with SQLite's online backup API (Python's
   `sqlite3.Connection.backup`, safe while Jarvis runs): `memory.db`,
   `history.db`, `schedule.db`, `feedback.db`; plus the `*.json` settings,
   `jarvis-framework.toml`, the notes folder and the voice enrolment. **Not**
   the pairing token, API keys (re-entered; rule 3), models or logs.
2. Adds the chat-history key, so the backup can be opened on a new PC.
3. Zips and encrypts it in the **age** format with a **recovery code** shown
   once ("write this down"). age is a small standard tool (BSD-3, v1.3.2;
   Python binding `pyrage`, MIT): if Jarvis itself is broken, the owner can
   still open the file with one command, `age -d`. Alternative with no new
   package: AES-GCM plus Argon2id from `cryptography`, already required
   (Argon2id since 44.0.0) - but then only Jarvis can open it.

Restore: pick the file, type the code, see what is inside (counts and date,
never content), then **one approval card plus Windows Hello** ("Replace your
memory and history with the backup from 20 Sept?"). Jarvis first backs up
the current state, so the restore itself can be undone. Destination: this
PC or a removable drive (question 1). Phone: shows "last backup: 3 days ago"
only; restoring is a PC job (ARCHITECTURE §8, one-sided on purpose).
**Fits:** rule 1 (nothing leaves), rule 3 (no keys in the file), rule 4 (a
card). **Honest limit:** "Erase the words" cannot reach old backups; the
restore card and the Forget screen must say so.

**3. Data health in the preflight.** `selftest.py --preflight` (:742-1611)
checks the running chains but not the data: no `PRAGMA quick_check` anywhere
in `backend/` (searched), and free disk space only for the big model
(`jarvis_big_model.py:296`). Add one check: `quick_check` on each database
(read-only), free space on the `.openjarvis` drive, age of the last backup,
and whether the chat-history key is in Credential Manager (without reading
it). WARN, never fix. Stdlib only. **S.**

**4. Watchdog.** The desktop supervises the backend (`sidecar.rs`) but only
restarts it when asked from the tray (`sidecar.rs:396` says so). Add: when
supervision is on and the process exits or `/api/status` stops answering for
60 s, restart it - at most 3 times in 10 minutes, then stop and say so in
plain words (question 2). The rules already make this safe: a card waiting
at a restart is refused, and the stamp secret is new each start
(`jarvis_owner_check.py:241`). **Not** a Windows service (see "Not for
Jarvis").

**5. Hang and crash notes on the PC.** Python's `faulthandler` (stdlib) can
write every thread's stack to a file on a native crash, and
`faulthandler.dump_traceback_later(60, repeat=True, file=f)` writes one if a
heartbeat stops - the "Jarvis froze" case. Rust: a `std::panic::set_hook`
that writes a panic file (none exists; searched). Files go in
`.openjarvis/crash/`, newest 10 kept. `jarvis_scrub.py:71` already says it
cannot scrub faulthandler's writes, so a "prepare a bug report" step runs
them through `scrub_text` before the owner shares anything.

**6. QR pairing with per-device keys.** The design current practice supports:
- **The QR code carries** Jarvis's address, a **one-time 128-bit secret**,
  the PC key's fingerprint and an expiry (10 minutes, as OpenClaw does;
  `COMPETITORS-OPEN-SOURCE` row "Mobile"). A 128-bit secret needs no special
  protocol: it cannot be guessed.
- **The phone makes its own key** in Android Keystore (EC P-256; StrongBox
  when the phone has one, `setIsStrongBoxBacked(true)`, else the TEE) and
  sends its public key with **key attestation**: a certificate chain proving
  a real phone's security chip holds the key, inside the Jarvis app. The PC
  checks the chain **offline** against Google's roots - **both** the old RSA
  root and the new P-384 root, which RKP phones use exclusively since 10
  April 2026 **(summary)**. A program on the PC that photographed the QR
  cannot fake that.
- **One approval card on the PC** ("Pair 'Pixel 8'?"), with Windows Hello,
  showing **four words both screens show**, made from both keys *and* fresh
  randomness. KDE Connect's 2025 advisory is the lesson: a short code made
  from long-lived keys alone could be brute-forced; they added a time
  component **(summary)**.
- **Each device gets its own token**, listed in both apps with a Remove
  that works alone. The old shared token keeps working until the owner
  retires it.
- **The typed backup code** (already decided) is short, so it must only be
  accepted over an encrypted link (loopback, Tailscale, Meshnet - not plain
  http on the home network) and burns after 3 wrong tries. A PAKE (a
  protocol that makes a short code safe even against a listener: SPAKE2,
  RFC 9382; CPace, still a CFRG draft) is the upgrade. The Python `spake2`
  package (MIT) was **not checked** for RFC 9382 compatibility, and no
  Android implementation was checked.
Plugs into `jarvis_token_store.py`, the phone's `TokenStore.kt:104` and
`jarvis_owner_check.from_this_pc` (:211). **L**, as already queued.

**7. Approval gap step 2, concretely.** Today the phone's fingerprint prompt
is not tied to any key: `BiometricGate.kt:189` calls
`prompt.authenticate(builder.build())` with no `CryptoObject`. Step 2: a
second Keystore key, `setUserAuthenticationParameters(0,
AUTH_BIOMETRIC_STRONG or AUTH_DEVICE_CREDENTIAL)` (a fresh check for every
use) and `setInvalidatedByBiometricEnrollment(true)`; the prompt gets a
`CryptoObject(Signature)`; the phone signs *card id + one-time number +
hash of the card's words*; the backend checks it with `cryptography`. Two
facts to design around: face unlock on many phones is "Class 2" and cannot
unlock such a key, though the PIN still can (Android's documentation, not
re-read today); and **Android Protected
Confirmation** - where the phone's secure chip itself shows the words - is
**deprecated** and was Pixel-only, so it is not an option. **M**, inside 6.

**8. A ledger of decisions, counts only.** Anthropic reports that Claude Code
users approve **93% of permission prompts** and names the result "approval
fatigue" (read myself, 25 March 2026). Jarvis keeps speed numbers the same
way already (`jarvis_speed.py`: a fixed list of number fields, text dropped
in code). Add, per card: action, outcome, seconds to decide, "shaped by
outside text", warning codes. Show weekly in both apps: "12 cards, 11
approved, 7 decided in under 2 seconds." It informs the owner's own "What
asks first" choices. It **never** changes a tier by itself (rule 4).

**9. Safer backend updates.** Today: `git pull`, then `apply-patches.ps1`,
which backs up changed files and has `-Revert` (lines 1243-1276, 1019).
Missing: a check that the new version *works* before it is the one running,
and protection from a poisoned Python package. Add:
- **Staged install:** apply into a copy, run `selftest.py --preflight`
  against it, switch only if it passes; one command switches back.
- **Pinned packages:** a hash-locked requirements file (`--require-hashes`,
  or pip's new `pylock.toml`), and `--uploaded-prior-to P7D` so a package
  version younger than 7 days is not installed (pip 26.0, January 2026;
  day durations since 26.1): a hijacked release has a week to be noticed
  before Jarvis would install it.
- **Optional:** CI builds a backend bundle with a GitHub artifact attestation
  (Sigstore; `sigstore` 4.5.0, Apache-2.0) and the script checks it. It
  proves "built by this repo's CI from commit X" - not that the code is good.
  TUF (`tuf` 7.0.1) is the full answer and is too big for one owner.
The desktop's own updater needs only its minisign key (DEPS audit).

**10. Value-level labels (FIDES/Progent-lite).** FIDES (Microsoft Agent
Framework, MIT, since v1.3.0, May 2026) labels every value
trusted/untrusted and public/private; a tool declares `accepts_untrusted=False`
and a breach becomes an approval request. Jarvis already finds outside-sourced
values for the card (`_ARG_PIECE`). The step up: each tool names its
**sensitive arguments** (email recipients, a shell command, a file path, a
URL), and an outside-sourced value there gets a heavy, top-of-card line,
and makes the card "heavy" even when nothing else would. Optional owner
policies, Progent-style: "email only to addresses I have written to
before." **Stricter only**; any loosening (e.g. no search card when every
search word is the owner's own) is the owner's call and is not proposed.

**11. A tool-less reader pass.** CaMeL's and FIDES's "quarantined model", made
small: after `email_check` or `web_search`, the same local model is asked
once **with no tools** to fill a fixed form through Ollama's `format`
(already the chosen way, ARCHITECTURE §11): sender, subject, a summary of at
most 300 characters, dates, and `asks_you_to_act: yes/no`. The tool loop sees
the form, and the raw text only when the owner asks for it. Costs one extra
model call per read (seconds on the 8 GB card). The summary is still outside
text - taint unchanged. Build only if idea 1 shows it cuts attacker cards.

**12. Masked re-run (MELON idea).** Before raising a card in a turn shaped by
outside text, ask the model again with the owner's request replaced by
"summarise this". If it proposes the same call, the text drove it; the card
says so ("Your question did not lead here"). MELON (ICML 2025) reports
strong AgentDojo results **(claim)**; its repo has **no licence file**, so
the idea only. A second call, only on those cards.

**13. Datamarking.** Microsoft's spotlighting puts a marker between every
word of outside text and tells the model so. The paper reports attack
success falling from over 50% to under 2% - **on GPT-family models (claim)**;
small local models were not tested. Free to add to `_tool_content`
(`jarvis_agent.py:2077`); measure with idea 1 first (it may hurt reading).

**14. A second, learned warning.** `protectai/deberta-v3-base-prompt-injection-v2`
(what AgentDojo's own detector uses) or Meta's Prompt Guard 2 22M (Llama 4
Community License, gated download), run on the processor with onnxruntime,
already installed. Adds a warning code; never blocks. Check false alarms on
the 383 ordinary texts first. Model licences not checked (huggingface
blocked).

**15. Tailscale: name the device, lock the network.** `tailscale whois --json
<ip>` (read in `cmd/tailscale/cli/whois.go`, BSD-3) tells the backend which
machine and user a 100.x address belongs to, so a card can say "approved on
Pixel 8" and `from_this_pc` gets a second opinion. **Tailnet Lock**
(generally available since July 2025 **(summary)**) stops Tailscale's own
servers from adding a device to your network without your signature; plus a
rule that only your phone may reach Jarvis's port. Both are Tailscale
settings, owner-side; `INSTALL.md` would describe them. Meshnet: no
equivalent checked.

**16. Windows crash dumps kept on the PC.** Windows Error Reporting can keep
a dump of a crashed program locally, off by default, with a registry key
under `HKLM\...\Windows Error Reporting\LocalDumps\<program>.exe` (admin
once; `DumpType` 1 = small "mini" dump; `DumpCount` keeps the newest N; kept
even when sending reports to Microsoft is off - Microsoft's docs source,
read). **Your call:** even a mini dump can contain pieces of memory, such as
the token or a decrypted chat. Never attach one to a report unread.
**TPM-bound keys (not ranked):** keys made with `NCRYPT_USE_VIRTUAL_ISOLATION_FLAG`
or the TPM cannot be copied off the PC **(summary)**, but any program of yours
can still *use* them - the same-user limit in `APPROVAL-GAP-DESIGN.md` §2.
Worth it for the chat-history key only after backups exist, since a cleared
TPM would otherwise lose the history for good.

## Not for Jarvis

- **An AI that approves for you** (Claude Code's "auto mode": a classifier
  decides which actions skip the prompt). Rule 4 and invariant 3. The 93%
  figure argues for *fewer, better* cards (ideas 8, 10), not a machine yes.
- **Backups to a cloud** (restic or Kopia to S3/B2, Google Drive), even
  encrypted: stored memory would leave the PC (rule 1). restic (BSD-2,
  0.19.1) is fine to a USB drive if the owner prefers it to idea 2.
- **Passkeys/WebAuthn on the home network:** they need a real domain name
  and a public HTTPS certificate (`tailscale cert` would publish the PC's
  name in public certificate logs, as Tailscale's own docs warn; not re-read), and phone passkeys sync through Google.
  The Keystore key (idea 6) gives the same proof with none of that.
- **Base64 "encoding" spotlighting:** only reported with large cloud models;
  an 8B model cannot reliably read base64.
- **Full CaMeL** (turned down 2026-09-24): its own README calls the code "a
  research artifact" whose interpreter "likely contains bugs".
- **promptfoo as shipped** (MIT, owned by OpenAI since March 2026):
  telemetry is on by default, and red-team generation falls back to
  promptfoo's servers; its docs say the off switch "is not a network egress
  firewall". **garak** (Apache-2.0, has an Ollama driver) is acceptable
  offline but tests the model, not Jarvis's loop.
- **Android Protected Confirmation:** deprecated.
- **Running the backend as a Windows service** for self-healing: services run
  in session 0, with no desktop, so window control, microphone and Windows
  Hello prompts would break.
- **An extra Noise channel:** Tailscale and Meshnet already are WireGuard
  (a Noise protocol). The plain-http home-network case is handled by keeping
  pairing codes and risky approvals off it (idea 6).
- **Online attestation revocation checks, crash-report services (Sentry):**
  each is a new outbound request carrying device or crash data.
- **A detector as a block:** defence-aware attacks beat them (above).

## Questions for the owner

**1. Where may backups be saved?** They are encrypted, but they hold
everything Jarvis knows.
- **This PC or a USB drive only** (recommended)
- **Also a shared folder on your home network**

**2. If the backend crashes, should the desktop app restart it?**
- **Yes, up to 3 times in 10 minutes, then stop and tell me** (recommended)
- **No, I will restart it myself**

## Sources

- [Adaptive Evaluation of Out-of-Band Defenses (arXiv 2606.26479)](https://arxiv.org/abs/2606.26479) (summary)
- [Design Patterns for Securing LLM Agents against Prompt Injections (arXiv 2506.08837)](https://arxiv.org/abs/2506.08837) (summary)
- [CaMeL code, Apache-2.0](https://github.com/google-research/camel-prompt-injection) · [CaMeLoT (arXiv 2609.18674)](https://arxiv.org/abs/2609.18674) (summary)
- [FIDES in Microsoft Agent Framework, discussion #5624](https://github.com/microsoft/agent-framework/discussions/5624) (read via fetch; framework MIT)
- [Spotlighting paper (arXiv 2403.14720)](https://arxiv.org/abs/2403.14720) (summary) · [Microsoft MSRC on indirect injection](https://www.microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks) (summary)
- [MELON (arXiv 2502.05174)](https://arxiv.org/abs/2502.05174) (summary) · [repo](https://github.com/kaijiezhu11/MELON)
- [AgentDojo, MIT](https://github.com/ethz-spylab/agentdojo) · [LLMail-Inject challenge, MIT](https://github.com/microsoft/llmail-inject-challenge) · [InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent)
- [garak, Apache-2.0](https://github.com/NVIDIA/garak) · [promptfoo, MIT](https://github.com/promptfoo/promptfoo) · [OpenAI to acquire Promptfoo](https://openai.com/index/openai-to-acquire-promptfoo/) (summary)
- [Llama Prompt Guard 2 model card](https://github.com/meta-llama/PurpleLlama/blob/main/Llama-Prompt-Guard-2/86M/MODEL_CARD.md) (summary)
- [Anthropic: Claude Code auto mode (93% of prompts approved)](https://www.anthropic.com/engineering/claude-code-auto-mode)
- [age, BSD-3](https://github.com/FiloSottile/age) · [pyrage, MIT](https://github.com/woodruffw/pyrage) · [restic, BSD-2](https://github.com/restic/restic) · [pyca/cryptography changelog](https://github.com/pyca/cryptography/blob/main/CHANGELOG.rst)
- [pip NEWS (`--uploaded-prior-to`, `pylock.toml`)](https://github.com/pypa/pip/blob/main/NEWS.rst) · [python-tuf](https://github.com/theupdateframework/python-tuf) · [sigstore-python](https://github.com/sigstore/sigstore-python)
- [RFC 9382 SPAKE2](https://datatracker.ietf.org/doc/rfc9382/) · [CPace draft](https://datatracker.ietf.org/doc/draft-irtf-cfrg-cpace/) · [RFC 9807 OPAQUE](https://datatracker.ietf.org/doc/rfc9807/) (summary)
- [KDE Connect security advisory 2025-04-18](https://kde.org/info/security/advisory-20250418-3.txt) (summary)
- [Android key attestation root rotation, 2026](https://bayton.org/android/android-enterprise-faq/key-attestation-root-certificate-change/) (summary) · [Android Protected Confirmation](https://developer.android.com/privacy-and-security/security-android-protected-confirmation) (summary)
- [Advancing key protection in Windows using VBS](https://techcommunity.microsoft.com/blog/windows-itpro-blog/advancing-key-protection-in-windows-using-vbs/4050988) (summary)
- [WER "Collecting User-Mode Dumps" (MicrosoftDocs source)](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/wer/collecting-user-mode-dumps.md)
- [Tailscale `whois.go`](https://github.com/tailscale/tailscale/blob/main/cmd/tailscale/cli/whois.go) · [Tailnet Lock GA](https://tailscale.com/blog/tailnet-lock-ga) (summary)
