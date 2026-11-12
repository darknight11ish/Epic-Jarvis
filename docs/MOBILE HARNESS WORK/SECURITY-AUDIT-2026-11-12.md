# Full Security Audit Report: Epic Jarvis Project (`main` Branch)

**Date:** 12 November 2026  
**Auditor:** Antigravity AI Pair Programmer  
**Target:** Epic Jarvis (`main` branch @ clean working tree)  
**Scope:** Python backend, Tauri v2 desktop application, Android companion (`jarvis-client`), server shims, plugins/skills, cryptographic storage, and build/deploy scripts.

---

## 1. Executive Summary & The Five Rules Scorecard

Epic Jarvis is an exceptionally security-conscious, local-first personal AI assistant. The repository demonstrates defense-in-depth engineering rarely seen in open personal assistant software: hardware-backed biometric cryptographic signatures, multi-layered sandbox process isolation, AST validation with memory-bomb guards, timing-safe token verifications, and strict origin validation.

No catastrophic breaches of the project's core Five Rules were found in the current commit on `main`. However, the audit identified **8 specific security and privacy findings**, ranging from medium to low severity, including an unencrypted memory database at rest (`DEF-055`), proxy bypass leaks on certain loopback model calls, an App-Lock bypass in the desktop tray updater (`DEF-045`), and an overly broad mesh origin regular expression.

### The Five Rules Compliance Scorecard

| # | Rule | Status | Audit Assessment |
|---|------|--------|------------------|
| **1** | **Email, files, credentials & memory stay local** | **PASS WITH CAVEAT** | Outside text taint tracking prevents private data ingestion into cloud escalation lanes (`test_cloud_lane_taint.py`). However, raw `urllib.request.urlopen` calls in image generation and model capability checks could leak local loopback prompts to system proxies (Finding 1). |
| **2** | **No public tunnels (no ngrok, Cloudflare, Funnel)** | **PASS** | Cleartext traffic is banned by default on Android and restricted to Tailscale (`*.ts.net`) and NordVPN Meshnet (`*.nord`). The backend strictly validates mesh and loopback peer IPs. |
| **3** | **API keys & tokens handled with care** | **PASS** | No plaintext keys or live credentials committed to git. Tokens and keys are stored in Windows Credential Manager (DPAPI) and Android KeyStore. Log scrubbing (`jarvis_scrub.py`) redacts sensitive tokens from stderr/stdout and logfiles. |
| **4** | **Never auto-approve; stale event streams block acting** | **PASS WITH CAVEAT** | High-risk tools (`shell_exec`, file writes, web fetch) are gated by `jarvis_gate.check` requiring human approval cards and ephemeral HMAC stamps. However, conversation history deletion on Android (`DEF-047`) and live backend updates from the desktop tray (`DEF-045`) bypass approval cards/locks. |
| **5** | **Non-commercial build & sideloaded via ADB** | **PASS** | Android app configuration contains no Google Play dependencies or billing SDKs; licensing notices in `THIRD-PARTY-NOTICES.txt` are maintained. |

---

## 2. Detailed Vulnerability Findings

### Finding 1: System Proxy Leak on Loopback Model & Image Calls (Medium Severity)
- **Files Affected:**
  - `backend/jarvis_pictures.py:451, :761`
  - `backend/jarvis_self_improve.py:782`
  - `backend/jarvis_thinking.py:233`
  - `backend/jarvis_personality_creator.py:429`
  - `backend/jarvis_picture_card.py:494`
  - `backend/jarvis_live.py:396`
  - `backend/jarvis_presets.py:1190`
- **Mechanism:** In `backend/jarvis_local_http.py`, the project documented bug `CONN-1`: standard `urllib.request.urlopen` uses the operating system's proxy settings (such as corporate proxies or VPN proxies set in the Windows registry). Windows' `<local>` proxy bypass only excludes single-word hostnames, not `127.0.0.1`. Calling `urllib.request.urlopen` directly sends traffic to the proxy. While `jarvis_local_http.urlopen()` was engineered with an empty proxy table to solve this, the files listed above still call raw `urllib.request.urlopen()` for local Ollama and ComfyUI/SD endpoints.
- **Impact:** If the owner has a corporate or VPN proxy configured on their PC, prompts sent to `{where}/api/generate`, `{url}/api/show`, or image generation endpoints will be routed through the external proxy in plaintext, violating Rule 1.
- **Remediation:** Replace all raw `urllib.request.urlopen` invocations in these files with `jarvis_local_http.urlopen(req, timeout)`.

---

### Finding 2: `memory.db` Unencrypted at Rest (`DEF-055`) (Medium Severity)
- **Files Affected:**
  - `jarvis-backend/jarvis_memory.py:2206`
  - `backend/rebuilt/jarvis_memory.py:2206`
- **Mechanism:** As confirmed in `jarvis_memory.py` line 2206 ("memory.db has no cipher"), the core memory database storing learned facts, user attributes, preferences, topics, and entities is stored as unencrypted SQLite database records. In contrast, conversation transcripts (`chat.db`) and backups (`*.jarvisbackup`) are encrypted with AES-256-GCM.
- **Impact:** Any process or user with read access to the local user directory (or unencrypted backups/drives) can inspect the owner's full cognitive memory graph and personal profile without authentication.
- **Remediation:** Implement AES-256-GCM record-level encryption or SQLCipher for `memory.db`, deriving keys from Windows Credential Manager identical to `jarvis_chat_log.py`.

---

### Finding 3: Desktop Tray Update Bypasses App-Lock (`DEF-045`) (Medium Severity)
- **Files Affected:**
  - `jarvis-desktop/src-tauri/src/tray.rs:2030-2034`
  - `jarvis-desktop/src-tauri/src/lock.rs`
- **Mechanism:** In PR #1138, the desktop system tray added an "Update Jarvis" menu entry (`run_update_from_tray`). This calls `crate::update::install_from_tray`, patching the live backend folder and updating desktop executables. However, `tray.rs` does not check `lock.rs:locked_now()` or `app_locked()`.
- **Impact:** When App Lock is engaged (requiring Windows Hello / PIN to view or change settings), anyone with physical access to the desktop can trigger a backend code rewrite directly from the system tray menu without authentication.
- **Remediation:** Add `if crate::lock::locked_now(&app) { return; }` (or prompt Windows Hello) before invoking `install_from_tray` in `tray.rs`.

---

### Finding 4: Overly Permissive Mesh Host Regex in `_mesh_origin_ok` (Medium Severity)
- **Files Affected:**
  - `backend/jarvis_owner_check.py:650-652, :734`
- **Mechanism:** In `backend/jarvis_owner_check.py`:
  ```python
  _MESH_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:nord|ts\.net)")
  ```
  `_mesh_origin_ok` accepts ANY origin whose hostname matches `_MESH_HOST` as long as the peer connection is from loopback or mesh. Because loopback (`127.0.0.1`) is trusted as a mesh peer, a browser running on the owner's PC visiting any third-party website on Tailscale (e.g. `malicious-user.ts.net`) can make cross-origin requests to `http://127.0.0.1:4719`. If no token is configured (or if the `jarvis_token` cookie is present), the Origin check passes.
- **Impact:** Any attacker who owns an arbitrary Tailscale MagicDNS node can host a malicious webpage that executes cross-origin API calls against the local Jarvis backend.
- **Remediation:** Restrict allowed mesh hostnames to the specific tailnet name configured by the owner (e.g. `*.my-tailnet.ts.net`), rather than the global `.ts.net` wildcard.

---

### Finding 5: Phone Uncarded Conversation Deletion (`DEF-047`) (Low-Medium Severity)
- **Files Affected:**
  - `jarvis-client/app/src/main/java/com/jarvis/client/net/JarvisApi.kt:2289`
  - `jarvis-client/app/src/main/java/com/jarvis/client/net/ChatLog.kt:49`
  - `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt:601`
- **Mechanism:** The Android app provides a conversation delete button that calls `POST /api/history/delete`. This endpoint executes deletion immediately without raising an approval card on the desktop. The two-phase carded endpoint (`POST /api/conversations/clear`) is implemented on the backend but unreferenced by the Android client.
- **Impact:** Irreversible deletion of chat history from the phone without PC approval card verification, diverging from the project's documented two-phase approval contract.
- **Remediation:** Wire `HistoryScreen.kt` to call `POST /api/conversations/clear` and display the pending approval card state.

---

### Finding 6: Silent Setting Modification via Model Tool (`DEF-034`) (Low-Medium Severity)
- **Files Affected:**
  - `backend/jarvis_agent.py:14530`
- **Mechanism:** The model-facing `change_setting` tool modifies cardless boolean or choice rows directly via `setting.set()` without generating an undo receipt in `jarvis_receipts`.
- **Impact:** If an indirect prompt injection manipulates the model into calling `change_setting` for a cardless option (such as turning off wake word detection or switching browser modes), the setting changes silently and cannot be undone using the conversational "undo" command.
- **Remediation:** Call the shared settings receipt helper (`_settings_receipt`) upon successful execution of `change_setting`.

---

### Finding 7: Phone Biometric Prompt Wording Discrepancy (`DEF-022`) (Low Severity)
- **Files Affected:**
  - `jarvis-client/app/src/main/java/com/jarvis/client/data/Security.kt:230-240`
  - `jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt`
- **Mechanism:** The phone card displays "Approve asks for your fingerprint or PIN" on risky cards regardless of whether signed approvals are turned on. When signed approvals are disabled, tapping Approve does not display the biometric prompt but instead presents an offer notice ("Risky approvals from this phone need to be signed...").
- **Impact:** Fails closed (no unauthorized action is approved), but presents inaccurate authentication expectations to the user.
- **Remediation:** Land the pending patch in `fix/def-022-phone-card-promise-2026-10-31` to condition the prompt description on `SignedApproval.State`.

---

### Finding 8: Live Backend Patch Reconcile Gap (`DEF-035`) (Low Severity)
- **Files Affected:**
  - `tools/reconcile_live_backend.py`
  - `backend/gate-tool-actions-gap.patch`
- **Mechanism:** `reconcile_live_backend.py` reports patch deltas as applied based on DELTA_TABLE presence checks. If an extended patch adds rows not indexed in DELTA_TABLE, the tool falsely reports 100% applied while the code is missing from the live installation.
- **Impact:** Silent patch omission during backend deployments.
- **Remediation:** Enhance `reconcile_live_backend.py` with full-file SHA-256 verification against expected patched targets.

---

## 3. Subsystem Security Architecture Review

### 3.1 Network Security & SSRF Defenses (`jarvis_local_http.py`)
- **DNS Rebinding Prevention:** `public_urlopen` uses custom `_connect_public` connection factories where a single DNS resolution is performed, all resolved IPs are validated against `_PRIVATE_NETS` (including IPv4-mapped IPv6, NAT64 `64:ff9b::/96`, link-local, multicast, and RFC 5735/6890 reserved ranges), and the socket connects directly to the checked IP literal. This completely prevents fast DNS rebinding attacks.
- **Proxy Bypass:** Loopback requests through `jarvis_local_http.urlopen()` use `ProxyHandler({})` to prevent leaking requests to system proxies.

### 3.2 Authentication & Signed Approvals
- **Token Verification:** `jarvis_owner_check.py` uses constant-time `hmac.compare_digest` with byte encoding to prevent timing attacks and UTF-8 decoder crashes. Failed attempts are rate-limited (`TokenFailureLimiter`, 10 failures in 60s trigger HTTP 429).
- **Android KeyStore Signed Approvals:** `jarvis-client` uses hardware-backed StrongBox / TEE EC P-256 keys requiring biometric/PIN user authentication per signature (`setUserAuthenticationRequired(true)`). Approval payloads include a cryptographic SHA-256 digest of display text, action, and request ID separated by `0x1F` delimiters.
- **Ephemeral Windows Hello Stamps:** Approvals on the desktop require Windows Hello authentication, which stamps the in-memory process state with an ephemeral HMAC secret (`take_stamp`), preventing direct SQLite modifications from faking approved actions.

### 3.3 Execution Sandbox (`jarvis_sandbox_exec.py`)
- **AST Allowlist:** Untrusted scripts are restricted to a whitelist of 10 math/data modules. Dunder methods, `eval`, `exec`, `open`, `compile`, and filesystem modules are rejected at parse time.
- **Memory Bomb Guards:** AST checks explicitly cap power operations (`**`), bit shifts (`<<`), sequence multiplications, and range sizes before execution.
- **Process Isolation:** Runs via `python -B -I` with stripped environment variables (`jarvis_child_env.inherited()`) inside a Win32 Job Object enforcing a 256 MiB memory cap, 5.0s hard timeout, 64 KiB stdout cap, and `JOB_OBJECT_UILIMIT_ALL` (blocking clipboard, window, and desktop access).

### 3.4 Android Companion (`jarvis-client`)
- **Exported Surface:** All activities and services except `MainActivity` (launcher), `ShareToLive` (text share receiver), and system-bound services are non-exported (`android:exported="false"`). All system-bound services are protected with signature-level permissions (`BIND_QUICK_SETTINGS_TILE`, `BIND_ACCESSIBILITY_SERVICE`, `BIND_VOICE_INTERACTION`).
- **File Providers:** Two `FileProvider` declarations are strictly `android:exported="false"` with ephemeral URI grant permissions for verified APK updates and approved file viewing.
- **Cleartext Traffic Policy:** Cleartext HTTP is globally blocked by `network_security_config.xml`, with explicit exemptions only for encrypted mesh domains (`*.ts.net`, `*.nord`).

### 3.5 Desktop Shell (`jarvis-desktop` Tauri v2)
- **Content Security Policy:** Strict CSP enforces `'self'` for scripts, prohibits `'unsafe-eval'`, and restricts `connect-src` to loopback ports `4719` and IPC localhost.
- **Prototype Freezing:** `freezePrototype: true` is enabled in `tauri.conf.json`.
- **Capability Isolation:** Windows operate under granular permissions (`quickbar.json`, `hud.json`, `brain.json`). The animated face renderer (`faces.html`) is sandboxed in an iframe with zero Tauri event emit permissions, preventing UI spoofing attacks.

### 3.6 Dependency Supply Chain
- **Python:** 78 pinned packages in `backend/requirements.lock`, each verified with multiple SHA-256 hashes. Installed via `pip --require-hashes` with 7-day exclusion policies to mitigate zero-day package takeovers. Offline integrity verification passes cleanly.
- **Rust / Tauri:** Tauri 2.12 generation locked in `Cargo.lock` with MSRV 1.90. Update artifacts are cryptographically verified via Minisign Ed25519 public key before installation.

---

## 4. Prioritized Remediation Plan

1. **Immediate (Next Build):**
   - Switch raw `urllib.request.urlopen` calls in `jarvis_pictures.py`, `jarvis_self_improve.py`, `jarvis_thinking.py`, etc., to `jarvis_local_http.urlopen` to ensure 100% proxy isolation.
   - Restrict `_MESH_HOST` regex in `jarvis_owner_check.py` to match the owner's specific tailnet name rather than arbitrary `*.ts.net` domains.
   - Add App-Lock validation (`locked_now()`) to `run_update_from_tray` in `tray.rs`.

2. **Medium Term (Design & Planned Slices):**
   - Implement encryption at rest for `memory.db` (`DEF-055`) using AES-256-GCM.
   - Wire conversation deletion on Android to `POST /api/conversations/clear` (`DEF-047`).
   - Add undo receipt logging to the `change_setting` agent tool (`DEF-034`).

3. **Low / Maintenance:**
   - Land `DEF-022` biometric prompt wording fix in `jarvis-client`.
   - Upgrade `reconcile_live_backend.py` (`DEF-035`) with whole-file SHA-256 checks.
