# Report 53 (outside-suggestion-check), agent af6e0ff8, 2026-09-30T07:22Z

> **What it was asked** (first 600 characters of the task): Check this outside (Gemini) suggestion against the real code and past decisions in /home/user/Epic-Jarvis (read CLAUDE.md, docs/AUDIT-2026-09-28-REPO-REFS.md first: its disproven findings stay closed; grep docs/ and backend/ for each name before judging). Suggestion: for Jarvis widget features use (1) s00d/tauri-plugin-widgets (one declarative IR rendered as Android Glance, WidgetKit, Windows Adaptive Cards, desktop webview; desktop backend emits a JSON widget spec the Android plugin maps to Glance); (2) android/platform-samples appwidgets/Glance showcase and NicosNicolaou16/AndroidWidgetWithC

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Verdicts on the four widget suggestions. The main finding is that Jarvis already has the feature the suggestion proposes to build, and its design rejects the free-form version.

**What Jarvis already has (item a)**
- I checked the phone widgets. `jarvis-client/app/src/main/java/com/jarvis/client/widget/` holds ApprovalWidget.kt, JarvisBoardWidget.kt, QuickLinkWidget.kt and ApprovalWidgetRules.kt. ApprovalWidget.kt imports `androidx.glance.*`, and the widget code has no RemoteViews classes. Glance is the toolkit.
- `jarvis-client/app/build.gradle.kts` (lines 313-319) already lists `glance-appwidget:1.1.1`, `glance:1.1.1`, and `kotlinx-serialization-json:1.7.3` with the serialization plugin. Adding those dependencies is redundant. `glance-material3` is not listed, and I did not check whether any code uses it. minSdk is already 33.
- Glance is already in `jarvis-client/app/src/main/assets/licenses/NOTICES.txt`.
- "Widgets you describe" is already built, in JARVIS-API §86 (docs/JARVIS-API.md, near line 13407). Backend `backend/jarvis_widgets.py` and `test_widgets.py` implement it.
  - The owner says what a widget should show. The local model turns that into JSON, and plain code then checks it.
  - The fixed menu has 5 block types (title, number, list, progress, button) and a fixed list of data sources: reminders, timers, Today cards, to-do, briefing counts, disk, focus, and what is playing.
  - Buttons are limited to 5 actions: focus, a 10-minute timer, Brief me, Stop everything, and play/pause.
  - Anything else is refused with a 422 "off the menu". Text with `< > { }`, a web address, or any colour, size or style key is refused or stripped.
  - Limits are 8 blocks, 12 saved widgets, and a body of at most 16 KB.
  - Flow: `POST /api/widgets/draft`, then a preview, then `/add`. The desktop has Brain → Work → Widgets. The phone has WidgetsPlate.kt, plus three home-screen slots ("Jarvis widget 1-3", `JarvisBoardWidget.kt`, native Glance).
- The suggestion's "JSON-driven Glance renderer" therefore already exists, in a restricted form. The phone app draws only the five block kinds.
- §86.5 explicitly rejects an earlier outside review's "widgets written as code by the model". Its stated reasons are that no check can prove arbitrary code safe, and that outside text could steer it.

**Item 1: s00d/tauri-plugin-widgets. SKIP.**
- Grepping the repo for it found nothing.
- I could not check whether the repo exists, its licence or its maturity, because WebFetch is disabled here. Not checked.
- ARCHITECTURE §8 says the Windows 11 widget board needs an MSIX-packaged app, and this app is not packaged that way.
- Jarvis already draws one widget in the desktop widget window, and the phone uses its own Glance renderer. A new plugin plus a shared layout format would be a second widget system.

**Item 2: platform-samples and AndroidWidgetWithCompose. BORROW IDEA only.**
- I did not open those repos. Not checked.
- Responsive sizing, dynamic colour and state handling are worth reading as reference. Jarvis already uses Glance, so no new dependency is needed.
- Glance 1.2.0 is already queued in `docs/research-audit-2026-09-28/report-oss-apps.md` item 5.

**Item 3: fibelatti/photo-widget and LeanBitLab/Lwidget. BORROW IDEA only.**
- No mention of either in `docs/`, and I did not open them. Not checked, including the Apache-2.0 claim.
- Shape masks, aspect ratios and photo borders belong to a photo widget, which Jarvis does not have.
- Worth borrowing:
  1. A configuration screen with a live preview before pinning. Jarvis already previews a draft before Add, but only on the app screen, not per home-screen slot.
  2. Per-widget transparency and accent choices.
  3. A high-contrast switch.
- If the owner wants these, I found no existing per-widget options: I grepped the three widget files for alpha, opacity, transparency and contrast and found no matches. They would be plain theme settings, not model-authored.

**Item 4: free-form recursive JSON renderer with POST /api/widget/update. SKIP.**
- It is against the design in §86.
  - A free schema (Column/Row/Text/Spacer) removes the fixed menu and its validator. The menu is what keeps outside text and web addresses out of widgets.
  - Widgets currently show only data both apps already show. Free-form layouts would need a new rule for which data may appear.
  - A push endpoint from the desktop would be a new path. The current design has the phone pull the checked, filled-in answer from the PC, and buttons are held on a stale link (rule 4).
  - The 2026-09-28 App lock rule stays intact only because buttons come from the five known actions (`QuickTiles.widgetOpensApp`). A free-form button would break that.
- The claim "without recompiling" is already true. The menu is data, so a new widget needs no rebuild.
- Wrong facts in the checklist:
  - The path `com/jarvis/widget/...` is wrong. The package is `com.jarvis.client`.
  - `POST /api/widget/update` is singular, and the real routes are `/api/widgets/*`.
  - "WebSocket or local sync" is wrong. The phone uses the HTTP/SSE API.
  - The dependencies it says to add are already there.
  - `dynamic_widget_info.xml` would be a fourth `widget_*_info.xml` (the existing ones are approval, board and quicklink). The board widget already has three slots for this purpose.
- No local Android compiler exists here, so CI is the only check for any Kotlin change. Also unchecked: whether a Gradle lock file exists (the suggestion asked about supply chain), and any notices needed for new dependencies. A borrow-idea change would add none.

**What the owner would need to decide (if anything)**
- Whether to add two things to the existing widgets: a per-widget "transparent / accent / high contrast" setting, and a live preview shown before the widget is pinned. Recommended: yes to a small version of both, as plain settings on the existing board widget. Not recommended: any free-form layout.

**Related open work**
- Another agent is auditing the widget inventory. I did not repeat that.
- Per §86.5, the Windows widget board, a dashboard server and live-by-event updates were already rejected or deferred.
- §86 itself says the home-screen widget has not been seen on a real launcher, so it is untested on a real phone.
