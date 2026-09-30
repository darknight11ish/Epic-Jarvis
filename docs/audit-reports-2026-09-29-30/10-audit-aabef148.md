# Report 10 (audit), agent aabef148, 2026-09-29T09:59Z

> **What it was asked** (first 600 characters of the task): Repo /home/user/Epic-Jarvis, branch ccr-a9b557ac-cpnbwx (= origin/main cbc6d12d + a few small audit fixes). Do NOT edit files. PR #29 just landed the animal faces: the fifth robot face, painted eyelids, listening nods, sentence-end gestures, focus buddy, petting, idle moments, seasonal touches, sun/moon/weather scene, Still option, wake/sleep animations, Zs, rings, voice-speed handling, Animal options and 'ask Jarvis to change them' (backend settings), the one-time animal voice question. Bug-hunt it: desktop (jarvis-desktop/src/*.js incl. faces/critters/animal-options/season/lipsync/voice-spee

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

Bug-hunt of PR #29 (animal faces): no safety-rule break and no crash found. Three small real issues plus one cosmetic point.

## Confirmed issues, worst first (all low)

**1. A phone's old "Keep the animal still" can be lost if any other animal switch was changed on the PC first.**
- Where: jarvis-desktop/src-tauri/src/animal.rs:203-208 (`still_move_needed`) and the phone's net/AnimalOptions.kt (`stillMoveNeeded`, ~line 220). I read both; I did not run this.
- The move is skipped whenever `changed > 0`, but `changed` is stamped by any switch. `jarvis_animal._save` writes `"changed": time.time()` for nods, petting and the rest, not just Still.
- Trigger: the owner turns off, say, Listening nods on the PC before the phone first runs the new build, and the phone's old Still was ON. The move is skipped, the phone marks itself migrated, and `effectiveStill` stops honouring the old "on". The animal moves again, which breaks "if either device had Still on, keep it on".
- Fix: compare against a Still-specific timestamp, or skip the move only when the PC's `still` was itself changed. Or accept it and document it.

**2. On the phone, a long press on the face during an approval, error or standby does nothing at all.**
- Where: ui/screens/HomeScreen.kt `tapThrough` (~line 1769) and `AnimalNow.pressOpensBrain`.
- A long press counts as petting, so it no longer opens Brain (`pressOpensBrain` checks only the character face and the Petting switch, never the state). But the pose ignores petting in those states (confirmed by the pose fuzz below), so the press is swallowed.
- Fix: pass "is the state awake" into `pressOpensBrain`. Only a press that can actually pet should skip the tap.

**3. Animal-option voice phrases can fire without naming an animal.** I ran these through `jarvis_quick.match`:
- "raise the quality", "lower the frame rate" and "turn down the resolution" become `animal_device` changes.
- "stop the weather" becomes `animal_weather off`.
- All cosmetic and per-device. It could still surprise the owner if "quality" meant something else.
- Fix: require "animal", "face" or "robot" in the `_DEV_UPDOWN` grammar, or accept it.

**4. Cosmetic: the "Sun rises…, sets…" line in Settings mixes days.**
- `sky.js` `summary`/`todayWords` look at the next 30 hours. I ran Denver at 08:00 local: it printed sunrise as `09-30T12:55` (tomorrow's) next to today's sunset. Only clock times are shown, so the numbers are right; the word "today" is not.

## What I tried where I found nothing

**Cute or animated behaviour during an approval, error, Still or a crisis turn.**
- I fuzzed all five species' `pose()` with full behaviour options against the same options off, across ~1,300 clock values.
- Result: bit-for-bit identical in approval, error, banked and standby. Also identical under `still=1` and `serious=1` in every awake state, with the face-switch hello and goodbye at 0.5. No NaN.
- Script: /tmp/claude-0/-home-user-Epic-Jarvis/9107f2ad-de34-5a00-97f9-3a345fb31dd0/scratchpad/leak.mjs

**Fact-saved nod under App lock or "Hide memory lists".**
- Desktop: `face-moments.js` `quietOf` fails closed while the lock state is unknown. `get_lock_flags` returns exactly two booleans, and the HUD, floating and widget capabilities all grant it.
- Phone: `AnimalNow.factSavedIf` is the only nod caller, and JarvisRuntime.kt:4055 passes `appLock` and `privateLists`. No other path stamps `factAt`.

**Weather and location.**
- Open-Meteo can only turn on via `jarvis_sky.request_weather`, which raises the approval card. It needs `change_own_config` at tier `ask`, rechecks the position after approval, and any town change drops the source.
- The outgoing URL carries only the position rounded to 0.1 degree, refuses redirects and refuses any other host. The phone cannot set the town (403).
- Every new Rust request uses `jarvis_headers` (`X-Jarvis-Client`).
- test_animal.py 93/93 and test_sky.py 88/88 pass.

**Season, sun and moon maths.**
- `sky.scene` and `sky.summary`: 8 latitudes including both poles and the polar circles, 4 longitudes, ~110 dates, no NaN.
- `season.scene`: 6 time zones (half-hour and +14 included), latitudes null/negative/0/NaN, across a 2024 leap year, no NaN.
- Feb 29, the New Year rollover and the southern-hemisphere shift are correct in `windowAt`. The phone uses `TimeZone.getOffset(ms) / 60000.0`, so it follows DST.

**Generators and shaders.**
- `gen_season.py`, `gen_critters.py` and `gen_animal_cases.py --check` are up to date; the working tree stayed clean.
- `tools/shader_size.py --check`: panda 59,693, owl 52,064, otter 55,018, monkey 59,602, robot 45,206. All under the 60,000 project cap and the 100,000 Android limit.

**Screen-reader wording parity.**
- Desktop `face-words.js` and phone `FaceWords` sentences match, including offline and focus. The focus-Quiet exception matches across jarvis-link.js, tray.rs and `RestingFace`.

**Settings overwritten by a stale copy.**
- Animal switches go one at a time. `_appearance_save` ignores `animal`, and the Faces-window save sends only face and bindings. Animal options live in their own `animal.json`.

**Desktop headless suite (117 files).**
- All passed except three that failed for reasons unrelated to this PR: `animal-options` and `faces` only hit my 200 s limit under load (`animal-options` passes alone in 3.5 minutes), and `memory` hit a Python pyo3 panic in this container.

## Not tested
- Nothing on the phone was compiled or run; all Kotlin conclusions are from reading. AGSL size is checked only by `shader_size.py`.
- I could not test real Ollama, Kokoro, Windows Hello or real DST behaviour on a device. I did not check `Season.kt` and `Sky.kt` beyond their golden fixtures.
