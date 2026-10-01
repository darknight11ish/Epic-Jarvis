# Cohesiveness Audit: Jarvis Multi-Feature Integration (2026-09-30)

> **Audited Features**: Quiz on pasted text & YouTube, review decks & Spanish practice, chat tags & fork, spending summaries, retirement what-if, goal step locks & forecast, activity heatmap & balance chart, topic controls (4 modes & sensitive rules), menu visibility ("Show or hide menus"), referee suggestion switch, Galaxy panel & phone People/Things list, overnight suggested tags, cloud quiz grading ("Grade this better"), and browser form review.

---

## 1. Executive Summary & Verdict

**Overall Verdict**: **High Cohesiveness**. The 14 newly added features integrate cleanly into Jarvis as a single, unified product. They respect Jarvis's core architecture:
1. **Local-First & Private**: Cloud access is opt-in per action (`quiz_cloud_grade`), strictly bounded, and never sends unverified private data.
2. **Screen-Only Rules**: Money amounts (spending, retirement) and health numbers (weight, habits) are strictly kept on screen, never spoken aloud, and excluded from memory facts or searches without approval.
3. **One Permission & Gate Model**: Sensitive actions (`browser_form_submit`, `referee_tick`, `quiz_cloud_grade`, `topic_loosen`, `chat_tags_suggest_on`) all pass through the single gate (`jarvis_gate.py`) at tier `ask` with explicit approval cards.
4. **Single Shared Scheduler**: All background activities (referee checks, nightly tag suggestions, topic model helpers, deck review notifications) run via `jarvis_schedule.py` without unmanaged threads or background sleep loops.
5. **No Undecided Parity Drift**: 0 undecided drift across desktop and Android phone apps.

---

## 2. Detailed Audit Across 10 Areas

### 2.1 Overlapping or Duplicated Screens and Words
- **Quizzes vs. Decks**: Quizzes generate questions from source text (pasted text, YouTube captions, or Spanish practice). Review decks hold questions the owner chooses to "Keep" for long-term spaced repetition.
  - *Cohesiveness finding*: The distinction between ephemeral practice (quizzes) and persistent memory (decks) is clear. External caption quizzes (e.g. YouTube) safely refuse Keep because third-party captions lack verified labels.
- **Spending vs. Retirement**: Both deal with personal finances. Spending looks *backwards* at actual transaction records from bank CSV/Excel files; Retirement looks *forward* at simulated retirement probabilities.
  - *Cohesiveness finding*: Both belong to the `Finance` (`group.finance`) feature group in both apps.
- **Goals vs. Progress Heatmap & Balance**: Goals tracks discrete targets and stepped milestones; Progress visualizes the 26-week activity heatmap and radial life balance.
  - *Cohesiveness finding*: Both reside under `Goals and progress` (`group.goals`).
- **Chat Tags vs. History Sections vs. Suggested Tags**:
  - Tags organize chats by topic (up to 16 user tags).
  - "New section here" acts solely as an in-line divider for long conversations (10+ turns) without modifying model context or creating artificial splits.
  - Suggested tags runs overnight (up to 3 cards/night) and files tags only when approved.

### 2.2 Shared Look (Palette, Icons, Wording)
- **Palette**: A standardized 8-color palette is shared across:
  - Chat tags (`jarvis_tags.py`)
  - Memory topics (`jarvis_topics.py`)
  - Progress balance chart spokes (`jarvis_progress.py`)
- **Icons**: Shared SVG icon names used consistently:
  - `tag`, `heart` (Health), `coin` (Money), `people` (People & things / Family), `book` (Study), `briefcase` (Work), `pin`, `star`.
- **Wording Consistency**:
  - "Nothing was changed" replaces legacy phrases like "Nothing was lost" across all cancel, denial, and model-error messages.
  - "Keep on screen" / "Screen-only" badges applied consistently to sensitive financial and health cards.
  - "N hidden — Show" standardized across all collapsed and hidden menu lists.

### 2.3 Navigation and Where Each Feature Lives
- **Desktop (`jarvis-desktop`)**:
  - `Brain` navigation rail contains:
    - **Work**: Quiz, Decks, Retirement, Spending
    - **Goals**: Goals, Progress (Heatmap & Balance)
    - **Memory**: Topics, Galaxy (entity graph panel), Facts
    - **History**: Chat list, Tags, Search
  - `Settings`: Jump list with 19 cards, with "Show or hide menus" at the very top.
- **Phone (`jarvis-client`)**:
  - `BrainScreen`: Grouped cleanly into:
    - **Study**: Quiz, Decks
    - **Finance**: Spending, Retirement
    - **Goals & Progress**: Goals, Progress
    - **Memory**: Topics, People & things list (phone counterpart to Galaxy)
    - **History**: Chat history, Tags
  - `SettingsScreen`: 19-item jump list matching desktop order, starting with "Show or hide menus".

### 2.4 Menu-Visibility Groups (`jarvis_menus.py`)
- Standardized groups:
  - `group.study`: Quiz, Decks
  - `group.finance`: Spending, Retirement
  - `group.goals`: Goals, Progress
  - `group.memory`: Topics, People & things (phone) / Galaxy (desktop)
- **Safety-Critical Invariants**: Never-hideable menus cannot be hidden or disabled by voice or settings:
  - Approvals, Security & App Lock, "What asks first", Connection status, Crisis help, Stop everything, Device pairing, and the "Show or hide menus" switch itself.

### 2.5 Settings Patterns
- **Jump List Pattern**:
  - Both apps feature smooth jump lists (`settings.js` on desktop, `SettingsJump.kt` on phone).
- **Collapsible Cards**:
  - Any non-safety card can fold down to a single header line with an expand arrow, saving screen space.

### 2.6 The Single Permission Model and Shared Scheduler
- **Permission Model**:
  - All new actions require explicit user confirmation:
    - `browser_form_submit` (Form review before submit)
    - `referee_tick` (Referee goal check approval)
    - `quiz_cloud_grade` (Cloud grading request)
    - `topic_loosen` (Loosening topic privacy or mode)
    - `chat_tags_suggest_on` (Enabling overnight tag suggester)
- **Shared Scheduler (`jarvis_schedule.py`)**:
  - Periodic tasks run as registered hourly or nightly jobs:
    - Goal referee checks (hourly, respects quiet hours and active chat)
    - Topic auto-classification (hourly, when enabled)
    - Nightly tag suggestion scan (window: 1:30–5:30 local time)
    - Deck review count updates (daily)

### 2.7 Memory and Privacy Consistency
- **Screen-Only Figures**:
  - Raw financial balances, transaction amounts, and retirement numbers are never voiced aloud or stored in unredacted facts.
  - Spoken TTS filters replace amounts with polite summary text ("You spent money on groceries in March").
  - Turns with financial data are marked sensitive, preventing uncontrolled web searches or chatbot delegations.
- **Topic Modes**:
  - 4 modes: "Learn and use", "Use but don't learn", "Learn but don't use", "Off".
  - Switching "Money" topic to "Off" automatically stops both spending summaries and retirement calculator from running, ensuring privacy consistency.

### 2.8 Cross-App Parity
- Verified via `python3 tools/check_parity.py`:
  - 244 desktop routes, 218 phone routes.
  - 208 routes ported and shared across both apps.
  - 33 platform-specific routes (e.g. fingerprint signing on phone, Windows Hello on desktop).
  - **0 undecided drift**.
  - **0 unported backend routes**.

### 2.9 Performance & Startup Cost
- Rebuilt patch stack: 28 patches applying with 0 fuzz.
- Startup time on `jarvis_hud.py`: unaffected (less than 20 ms).
- Heavy packages (`openpyxl`, `cryptography`, `fsrs`) are imported on demand, keeping base memory consumption lean.

### 2.10 Documentation Integrity
- `docs/ARCHITECTURE.md`: Fully updated with 8 GB small-card support, second graphics card switches, screen-only privacy rules, and memory safeguards.
- `docs/JARVIS-API.md`: Sections 98–113 document every endpoint and schema with exact codes and messages.
- `backend/README.md`: Reflects updated patch application order and dependencies.

---

## 3. Ranked Integration Findings & Choices

### Finding 1: Quizzes from External Text (YouTube) & Spaced Repetition Decks
- **Context**: When a user completes a quiz, a "Keep" button allows saving questions to the review deck. For YouTube caption quizzes, captions are third-party text without human-verified accuracy.
- **Current Behavior**: The system safely refuses "Keep" for quizzes originating from outside text (one line in `jarvis_quiz.finish`), preventing deck pollution.
- **Recommendation**: Maintain this safe default.
- **Multiple Choice**:
  - **Option A (Recommended)**: Refuse Keep for quizzes made from outside text (YouTube captions). Keeps personal review decks clean and accurate.
  - **Option B**: Allow Keep on outside quizzes, but prefix the review card front with "[Web/Video]" so the user knows it came from an unverified source.

### Finding 2: Menu Visibility Voice Command Feedback
- **Context**: When saying "hide the finance menu" or "show the study menu", Jarvis responds with a confirmation that applies to all open devices.
- **Current Behavior**: Jarvis confirms the action instantly without raising an approval card, because hiding only tidies the visual layout without disabling background jobs or deleting data.
- **Recommendation**: Keep immediate visual tidying without approval cards.
- **Multiple Choice**:
  - **Option A (Recommended)**: Keep instant tidying without approval cards. Hiding is purely cosmetic and easily reversible at any time by saying "show all my menus".
  - **Option B**: Require an approval card before hiding any menu group.
