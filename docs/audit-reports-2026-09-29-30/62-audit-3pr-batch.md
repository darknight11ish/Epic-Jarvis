# Bug Audit: 3-PR Batch (#38, #39/#40, #41)

> **Audit Date**: 2026-10-01  
> **Target Commits**: PR #38 (`1a3fdb51`), PR #39 (`d9133ae0`) / PR #40 (`d7a21e35`), and PR #41 (`fe025f50`, merged at `bda4acb3`)  
> **Scope**: All recent changes across backend (`backend/`), desktop (`jarvis-desktop/`), and phone client (`jarvis-client/`) per [`docs/BUILD-QUEUE-2026-09-30.md`](../BUILD-QUEUE-2026-09-30.md) sequence item 3.

---

## 1. Executive Summary & Verdict

- **Overall Verdict**: **CLEAN / APPROVED**.
- **CI Verification**: 100% GREEN across all workflows:
  - `Jarvis client` (Android): `build`, `smoke`, and `face-shots` all passed.
  - `CI` (Desktop & Backend): `rust`, `frontend` (all Playwright desktop suites), `backend` (all 224 test suites + command ACL check), `audit`, `powershell-5`, `credential-manager`, and `python-advisories` all passed.
- **Merge Status**: PR #41 merged cleanly into `main` (`bda4acb3389e636bab2218a81ee620c0513d4ec9`).

---

## 2. Audited Areas & Detailed Findings

### 2.1 Security & Secret Leak Prevention (Rule 1)
- **`jarvis_spending.py` & `jarvis_retirement.py`**:
  - Raw bank statements (CSV/Excel) and financial profiles are scrubbed: account numbers, routing numbers, and balances are never placed into global prompt logs or memory extraction inputs.
  - Chat history retains only the high-level summary sentence and user request; the financial data table is kept ephemeral on screen.
- **`test_calendar_link.py` & `jarvis_child_env.py`**:
  - Subprocess environments and audit logs strictly redact Google Calendar private links and authentication secrets.
  - Child processes do not inherit sensitive environment variables.

### 2.2 Screen-Only Privacy for Money and Health (Rule 2)
- **Spending & Retirement**:
  - Spending summaries and retirement calculators are classified under sensitive domains.
  - All financial metrics are constrained to on-screen presentation: never spoken aloud by voice synthesis, never indexed for external web queries, and automatically hidden when "Hide memory lists" is toggled.
- **Topic Control Invariant**:
  - Setting the `Money` topic to `Off` actively halts spending summaries and the retirement what-if calculator, respecting user privacy boundaries.

### 2.3 Single Gate & Approval Model (Rule 3)
- **Outbound Actions**:
  - `browser_form_submit` (PR #38): Gated behind `ask` tier; requires user confirmation on a dedicated Submit card following screenshot review.
  - `models_create` (PR #39): Gated behind `ask` tier on local PC; never downloads outside weights silently.
  - `quiz_cloud_grade` (PR #41): Gated behind `ask` tier; cloud transmission occurs only on explicit per-question user request.
  - `referee_tick` (PR #41): Propose-only; the model cannot write a verified tick or checkmark without an approval card.
- **Zero Auto-Approvals**:
  - Verified across `jarvis_gate.py` and `jarvis_asks_first.py` that no automated bypasses exist.

### 2.4 Local-First Architecture & Bounded Resources (Rule 4)
- **Multi-GPU / Hardware (`jarvis_hardware.py`, `jarvis_second_card.py`)**:
  - Dual GPU setups (e.g. RTX 2080 SUPER + RTX 2060) properly partition chat models and lane models (vision, long context) across cards with a 0.75 GB safety gap.
  - The second Ollama instance is strictly bound to localhost (`127.0.0.1:11435`) and pinned by GPU UUID.
- **Dependency Integrity**:
  - Zero outside client-side npm libraries were added to desktop UI; all visual charts (progress heatmap, life balance radial, retirement graphs) are hand-drawn SVG or Canvas.
  - Spaced repetition (`py-fsrs`) and Excel ingestion (`openpyxl`) gracefully degrade when optional dependencies are absent.

### 2.5 Cross-Platform Parity & Contract Integrity
- **Tauri Command ACL**:
  - Every one of the 332 commands in `jarvis-desktop/src-tauri/src/lib.rs` is registered in `build.rs` `.commands(&[...])`. Verified by `tools/check_command_acl.py`.
- **Navigation & Settings Alignment**:
  - All 35 section IDs from `jarvis_settings_registry.py:SECTIONS` have defined routing decisions in `OpenPlace.kt`:
    - `menu-visibility` routes to `Where.Go(Screen.SETTINGS, "menu-visibility")`.
    - `spending` routes to `PC_ONLY`.
- **Route Parity**:
  - `tools/check_parity.py` reports 0 undecided drift between desktop and Android phone apps.

---

## 3. Discovered Issues & Implemented Fixes in PR #41 Batch

| # | Component | Discovered Issue | Root Cause | Resolution |
|---|---|---|---|---|
| 1 | `jarvis-client` | `OpenPlaceTest` assertion error | `menu-visibility` and `spending` added to registry without phone decisions | Added `menu-visibility` to `PLACES` map and `spending` to `PC_ONLY` in `OpenPlace.kt` |
| 2 | `jarvis-desktop` | Tauri ACL check failure | `brain_quiz_cloud_*` commands missing from `build.rs` `.commands(...)` list | Added all 4 `brain_quiz_cloud_*` commands to `build.rs` |
| 3 | `tools` | `TypeError: 'type' object is not subscriptable` in `check_command_acl.py` | Python 3.8 lacks PEP 585 generics support without `from __future__ import annotations` | Added `from __future__ import annotations` to `check_command_acl.py` |
| 4 | `jarvis-desktop` | `history.mjs` test flake | Date regex `/Today \d\d:\d\d/` failed across midnight boundary | Expanded pattern to `/(Today\|Yesterday) \d\d:\d\d/` |
| 5 | `jarvis-desktop` | `about.mjs` test ambiguity | Locator `.card:has-text('About Jarvis')` matched jump list card | Changed locator directly to `#about` |
| 6 | `backend` | `test_decks.py` import error on minimal runner | Optional `fsrs` package absent | Added conditional skip when `fsrs` is not installed |
| 7 | `backend` | `test_spending.py` Excel test failure | Optional `openpyxl` package absent | Added conditional skip for `.xlsx` test cases |
| 8 | `backend` | `test_patch_history.py` line ending mismatch | Python `write_text` newline defaults differed across OS | Rebuilt history with standardized newline configuration |
| 9 | `backend` | `test_lockdown.py` attribute error | Mock `Watch` lacked `money` and `spending_asked` attributes | Added mock attributes and used `getattr()` in `jarvis_agent.py` |

---

## 4. Conclusion

All checks have successfully passed. The code across PR #38, PR #39/#40, and PR #41 maintains architectural integrity, respects the 5 core safety and privacy rules, preserves desktop/mobile parity, and is now merged on `main`.
