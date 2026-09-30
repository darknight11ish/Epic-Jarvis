# Report 26 (audit), agent aff0c419, 2026-09-30T06:13Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis, focused on the DESKTOP and PHONE apps and settings defaults for multi-GPU. Question: for a PC with the 8 GB RTX 2080 Super plus 1-2 extra cards of 8-12 GB, do both apps (jarvis-desktop Settings/Brain 'Second graphics card' + 'Third graphics card' sections; jarvis-client SecondCardPlate/net/SecondCard.kt) show, explain and correctly gate every GPU-dependent feature? And is every feature that cannot run on ONE card off by default in the settings/config defaults the backend ships (backend/jarvis_second_card.py, jarvis_hardware.py presets, jarvis_settings

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Multi-GPU audit of the desktop and phone apps and the backend defaults. Nothing was run and no files were changed. This was read-only, except that `python3 tools/check_parity.py` reported "No undecided drift".

Overall: every backend feature that needs a second card ships off. The apps show all five switches, and the third-card assignment is a select on the desktop and chips on the phone that offer only the switches already on. I found no card-count assumption that breaks anything. The real gaps are mostly wording, plus one identity gap.

1. **A third-card assignment is not tied to the physical card the owner approved.** (Medium; read, not run.)
   - `jarvis_second_card.py:2777-2779` builds the card text with the exact card name, memory and uuid.
   - `_write_third` (line 965) stores only `cur["third_feature"] = feature`. Nothing keeps the uuid.
   - `_detect` (~line 1095) re-picks "second" and "third" on every read: `sorted(candidates, key=lambda d: (-d.total_mb, d.index))`, with third = `lanes[1]`.
   - Say the owner approves "Pictures on the 10 GB card", then later adds a 12 GB card or the indexes shift. The assignment silently follows a different physical card, with no new approval card.
   - Suggested fix: store the approved card's uuid next to `third_feature`, and treat a mismatch as unassigned ("your choice is kept, ask again").

2. **Under a chosen preset, the 10 GB and Turing checks are skipped, and a real third card looks absent.** (Medium; read, not run.)
   - `_detect_preset` (~lines 1140-1215) builds "second" from the preset's `lane_card` and never calls `_not_capable`. An 8 GB card, or a pre-Turing card with an id, can become the lane.
   - The apps' blocked text says "10 GB or more". That text only shows when the backend says "not capable", so under a preset the 10 GB rule and the app text do not match.
   - The same function sets `"_third": None` and marks every other card "the preset does not use it". A capable third card is therefore hidden, and the Third section only appears if something was assigned.
   - `jarvis_profiles.plan` (line ~516) also cuts to two cards with "Jarvis plans for up to two cards; the X is left out". That is intentional and documented.
   - This is a design choice, not a crash. Only whether the wording matches is open; see owner decision (a).

3. **Wording that assumes exactly a second card, 12 GB, or "not installed".** (Low.)
   - `jarvis_chatbot_local.py:225-227` says "on your second graphics card" even when Longer conversations was moved to the third card. `lane_for("long_context")` returns the third lane in that case.
   - `jarvis_chatbot.py:194` (`TIER_WORDS`) says "the second graphics card".
   - `jarvis_live.py:1238` says "the second graphics card (the 12 GB one)". Any 10 GB or 12 GB card qualifies.
   - `jarvis-desktop/src/settings.html` (the "One bigger model" note) says "the second card is not installed". That will be false once it is installed.
   - `jarvis_second_card.py:2792` says "starts a fourth copy of Ollama". The third card gets the third copy (main, second, third), and the apps say "third copy".
   - `jarvis_chatbot_local.py:89`: `LANE_MAX_BYTES = 9 GiB` assumes a 12 GB lane. On a 10 GB card a 9 GiB model plus its conversation memory may not fit. Not checked.

4. **Some features have no card-3 or card-count control in the apps.** (Low; read.)
   - The chatbot "full version" (two-card tier) is only the config line `[chatbot] full_version` in `jarvis-framework.toml` (`jarvis_chatbot.py:~808`). The apps only see the resulting tier text. Both apps' Chatbot screens were not checked.
   - Compare's cap is `MAX_AIS = {ONE_CARD: 3, TWO_CARDS: 4}` (`jarvis_chatbot_compare.py:98`). It is decided by that tier flag, not by the count of detected cards. Three cards give nothing extra, which is fine.

5. **Suggestion offers default on, but they are gated.** (Info.)
   - `SUGGEST_DEFAULT = True` (line 887) lets Jarvis offer "One bigger model on both cards" on its own. It is gated by `_combined_capable`, which needs at least 18 GiB across the two cards, and it is always an approval card. This is fine but worth knowing.
   - Combined only ever reads the main card plus the best extra card (`_lanes[0]`), so a third card is ignored there, as documented.

6. **Defaults confirmed off by reading the source.**
   - Second-card master, all five features, combined and `third_feature`: off (`_read_switches`, lines 906-927).
   - Screen picture mode: off (`jarvis_screen_picture.py:372-392`, "No file … OFF").
   - Live camera: `CAMERA_WIRED = False` plus a photo test (`jarvis_live.py:1238-1330`).
   - Chatbot full version: false as shipped.
   - Projects and apps code-writing: not built and waiting for the 12 GB card (`jarvis_projects.py:33`, `jarvis_apps.py:20`).
   - Wiki builder and browser control: they run only through `lane_for`, so they sit behind the switches. I did not audit browser control's own toml gate.
   - Learner: the background learner works without a second card. I did not verify that path beyond a grep.

7. **Card counts of 0, 1, 2 and 3 in the apps.**
   - The desktop and phone list every card with its reason, so an 8 GB extra card is shown as "not enough: … at least 10 GB".
   - The Third section is hidden unless the third card is capable or an assignment is kept (`settings.js:1973`, `SecondCardPlate.kt:132`). Neither app shows a card that is not there or hides a capable one, apart from the preset case in item 2.
   - An 8 GB extra card is never capable. 8 GB + 12 GB gives second = 12 GB and no third. 8 GB + 12 GB + 10 GB gives second = 12 GB and third = 10 GB.
   - A 10 GB card holds LONG (7.69 GiB) and vision (~7.15 GiB) with room to spare.

8. **Parity.** `tools/check_parity.py` reports "No undecided drift". `/api/second-card` is "ported" and both apps have the five switch rows, combined, the suggest toggles, the third-card section and the lane line. Only the route level was checked. I did not diff the row wording between apps in detail.

**Open owner decisions**
(a) Under a hardware preset, should the 10 GB, Turing and third-card rules be enforced or explained as they are outside presets? (Recommended: explain in words.)
(b) Store the approved card's uuid with the third-card assignment? (Recommended: yes.)
(c) Should the chatbot "full version" and its card count get a switch in the apps, or stay a config line until measured? (Recommended: stay config until measured.)
(d) Should the wording fixes in item 3 be generalized to "the extra card"? (Recommended: yes.)
