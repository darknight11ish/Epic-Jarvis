# Theme value parity — the measurement

**What this is.** The measurement `docs/HANDOFF-UI-RESEARCH-2026-10-09.md`
Phase B asks for *before* a generator is built: every theme value that the
desktop and the phone both carry, the exact value on each side, and a verdict
on each pair. Nothing was changed. No generated file, no new test, no
`tokens/` directory — this document only.

**Where it was measured.** `origin/main`, first fetched at `0541ae60` and cut as
a branch at `81547649` (the merge of #174) — `main` moved once during the work,
so both were checked. **Every source file this document cites is byte-identical
at both commits**, verified one file at a time with
`git rev-parse HEAD:<path>` against `git rev-parse origin/main:<path>`. One
caution: the research handoff itself,
`docs/HANDOFF-UI-RESEARCH-2026-10-09.md`, is **not on `origin/main`** at either
commit — it lives on `fix/widget-decides-nothing-clamped` (`9a315915`). So a
later session reading this document on `main` will not find the handoff beside
it; the citations below use the corrected `9a315915` text.

**How it was measured.** Read-only. A throwaway Node script in `%TEMP%`
parsed three files — `jarvis-desktop/src/theme.css`, `jarvis-client/…/theme/Themes.kt`
and `jarvis-client/…/face/Palette.kt` — into `(theme, token) → value` maps,
compared them, then swept every hex literal in both trees against each other.
Nothing was written into `jarvis-client/`, `tools/`, `tokens/` or
`jarvis-desktop/`. Reproduce it from the tables below; they are the output.

---

## 1. Headline

| | Count |
|---|---|
| Role-paired comparisons (17 roles × 3 themes) | **51** |
| **MATCH** — both sides the same value in the same space | **3** |
| **DRIFT** — both sides opaque, same role, different value | **36** |
| **NOT COMPARABLE** — same role, but not the same kind of value | **12** |

Narrower reading, "only pairs where both sides are an opaque colour for the
same role" (the 12 not-comparable ones dropped): **39 comparisons — 3 match,
36 have really drifted.**

Wider reading, "pairs the two apps intend to agree on, alpha ignored" (adds the
three Reactor surfaces, whose RGB does agree): **42 — 6 agree, 36 drifted.**

### The claim in the research, tested

The handoff says the values are "hand-maintained in two languages, and **three
phone values had already drifted a digit**"
(`docs/HANDOFF-UI-RESEARCH-2026-10-09.md:205-208`), and the summary repeats
"three of them had already drifted"
(`docs/SUMMARY-UI-RESEARCH-2026-10-09.md:53-55`). Neither cites anything, and
**the claim does not reproduce as stated**:

* On the same-role reading there are **36** drifts, not three, and **not one of
  them is a single-hex-digit difference.** The closest same-role pair in the
  whole measurement is Daylight's muted text, `#48566b` against `#46566a` — two
  hex digits apart (`theme.css:320` vs `Themes.kt:87`).
* Sweeping all 112 `0xFFRRGGBB` literals in `jarvis-client/app/src/main`
  against all 174 colour literals in `theme.css`, **exactly three pairs differ
  by one hex digit** — and none of them is a same-role pair:

  | phone value | desktop value | role |
  |---|---|---|
  | `Palette.ICE_5 = #B8F4FF` (`Palette.kt:27`) | `--accent-bright: #b8fbff` (`theme.css:105`, Reactor) | ice mist vs the desktop's accent-bright. The phone has no accent-bright token, and its accent is computed (§7), so there is no second side to compare |
  | `DAYLIGHT.surface0 = #EEF1F6` (`Themes.kt:81`) | `--surface-2: rgb(237, 241, 246)` = `#edf1f6` (`theme.css:312`, Daylight) | same theme, *different* surface (0 vs 2) |
  | `CONTRAST.surface2 = #0A0A0A` (`Themes.kt:122`) | `--surface-1: rgb(10, 10, 12)` = `#0a0a0c` (`theme.css:389`, High Contrast) | same theme, *different* surface (2 vs 1) |

So "three" is right only as a raw coincidence count, and in none of the three is
a value one hex digit from *its own* counterpart. The honest version of the
finding is stronger than the claim it replaces: **36 of 51 role-paired values
disagree today, and no existing test can see any of them.**

---

## 2. Why these 51 pairs

The pairing is not invented here. `theme.css:34-40` states it: the Reactor
surfaces are "the HUD's `--void` / `--plate` / `--plate-2` and the phone's
`Themes.REACTOR` surface0-2 (`#04070c`, `#0a1119`, `#0e1822`)". The phone's own
Material-3 mapping confirms the rest of the roles
(`jarvis-client/…/theme/JarvisTheme.kt:446-476`): `background = surface0`,
`surface = surface1`, `surfaceVariant = surface2`, `onSurface = textHi`,
`onSurfaceVariant = textMid`, `outline = hairlineFocus`,
`outlineVariant = hairline`, `error = badInk`.

| # | role | desktop token | phone `Chrome` field |
|---|---|---|---|
| 1 | window ground | `--bg-window` | `surface0` |
| 2 | card surface | `--surface-1` | `surface1` |
| 3 | raised surface | `--surface-2` | `surface2` |
| 4 | sunken well | `--surface-sunken` | `well` |
| 5 | high text | `--text` | `textHi` |
| 6 | mid text | `--text-muted` | `textMid` |
| 7 | low text | `--text-faint` | `textLo` |
| 8 | hairline | `--border` | `hairline` |
| 9 | strong hairline | `--border-strong` | `hairlineStrong` |
| 10 | focus edge | `--focus-ring` | `hairlineFocus` |
| 11 | ok ink | `--ok` | `okInk` |
| 12 | warn ink | `--warn` | `warnInk` |
| 13 | bad ink | `--bad` | `badInk` |
| 14 | ok mark | `--ok` (same token) | `okMark` |
| 15 | warn mark | `--warn` (same token) | `warnMark` |
| 16 | bad mark | `--bad` (same token) | `badMark` |
| 17 | cloud ink | `--info` | `cloudInk` |

Role 17 is real, not a guess: the desktop aliases the cloud colour onto `--info`
(`jarvis-desktop/src/style.css:33` — `--cloud: var(--info)`), and Chrome.kt
documents `cloudInk` as the violet that means "this is leaving your machine"
(`jarvis-client/…/theme/Chrome.kt:109-124`). Roles 14-16 are duplicates of
11-13 on the desktop, which has one token where the phone has an ink tier and a
mark tier (`Chrome.kt:86-107`); on the two dark themes the phone sets them to
the same value, so those rows move together.

The three theme ids are the deliberate, tested mapping — `deep-space ↔ reactor`,
`paper ↔ daylight`, `high-contrast ↔ contrast`
(`jarvis-desktop/tests/continuity.mjs:61`) — and are kept.

---

## 3. The table

Every value is quoted **exactly as it appears in the file**. Desktop values are
from `jarvis-desktop/src/theme.css`; phone values from
`jarvis-client/app/src/main/java/com/jarvis/client/ui/theme/Themes.kt`, with the
`Palette.kt` colour it resolves to shown in brackets.

### A. Surfaces

| theme | pair | desktop value | phone value | verdict | reason |
|---|---|---|---|---|---|
| Reactor | window ground | `rgba(4, 7, 12, 0.86)` :41 | `Color(0xFF04070C)` :42 | **NOT COMPARABLE** | same RGB `#04070c`; desktop is 86% opaque, the phone is opaque. The translucent window is deliberate (`theme.css:31-33`) |
| Reactor | card | `rgba(10, 17, 25, 0.9)` :42 | `Color(0xFF0A1119)` :43 | **NOT COMPARABLE** | same RGB `#0a1119`; alpha 0.9 vs opaque |
| Reactor | raised | `rgba(14, 24, 34, 0.92)` :43 | `Color(0xFF0E1822)` :44 | **NOT COMPARABLE** | same RGB `#0e1822`; alpha 0.92 vs opaque |
| Daylight | window ground | `rgb(244, 246, 249)` = `#f4f6f9` :310 | `Color(0xFFEEF1F6)` :81 | **DRIFT** | `#f4f6f9` vs `#eef1f6` |
| Daylight | card | `rgb(255, 255, 255)` :311 | `Color(0xFFFFFFFF)` :82 | **MATCH** | both `#ffffff` |
| Daylight | raised | `rgb(237, 241, 246)` = `#edf1f6` :312 | `Color(0xFFE8EDF4)` :83 | **DRIFT** | `#edf1f6` vs `#e8edf4` |
| High Contrast | window ground | `rgb(0, 0, 0)` :388 | `Color(0xFF000000)` :120 | **MATCH** | both `#000000` |
| High Contrast | card | `rgb(10, 10, 12)` = `#0a0a0c` :389 | `Color(0xFF000000)` :121 | **DRIFT** | `#0a0a0c` vs `#000000`; the phone flattened surface0/surface1 to one tone on purpose (`Themes.kt:112-113`) |
| High Contrast | raised | `rgb(20, 20, 24)` = `#141418` :390 | `Color(0xFF0A0A0A)` :122 | **DRIFT** | `#141418` vs `#0a0a0a` — the desktop kept a three-step ramp where the phone has two |

### B. The face's ground

| theme | pair | desktop value | phone value | verdict | reason |
|---|---|---|---|---|---|
| Reactor | sunken vs well | `--surface-sunken: #04070c` :49 | `well = Color(0xFF04070C)` :45 | **NOT COMPARABLE** | different jobs, same value by coincidence. A token that exists on one side only: the phone's `well` is the **face's** ground, theme-owned (`Chrome.kt:50-64`); on the desktop the face ground is the spec constant `#04070c` (`jarvis-desktop/src/jarvis-visual-spec.json:1901`), not a theme token at all |
| Daylight | sunken vs well | `rgb(228, 233, 240)` = `#e4e9f0` :313 | `well = Color(0xFF04070C)` :85 | **NOT COMPARABLE** | same reason; and the values differ because the phone keeps the well dark on every theme on purpose (`Chrome.kt:56-62`) |
| High Contrast | sunken vs well | `rgb(0, 0, 0)` :391 | `well = Color(0xFF000000)` :123 | **NOT COMPARABLE** | same reason |

### C. Text

| theme | pair | desktop value | phone value | verdict | reason |
|---|---|---|---|---|---|
| Reactor | high | `#f2f5f8` :66 | `Palette.NEUTRAL_5` = `#dde7f2` :46 | **DRIFT** | `#f2f5f8` vs `#dde7f2` |
| Reactor | mid | `#a8b2c1` :67 | `Palette.NEUTRAL_4` = `#8fa3b8` :47 | **DRIFT** | `#a8b2c1` vs `#8fa3b8` |
| Reactor | low | `#8e99a9` :68 | `Color(0xFF6E8397)` :48 | **DRIFT** | `#8e99a9` vs `#6e8397` |
| Daylight | high | `#10161f` :319 | `Color(0xFF0D1319)` :86 | **DRIFT** | `#10161f` vs `#0d1319` |
| Daylight | mid | `#48566b` :320 | `Palette.NEUTRAL_3` = `#46566a` :87 | **DRIFT** | `#48566b` vs `#46566a` — the nearest miss in the whole measurement (2 hex digits) |
| Daylight | low | `#59687d` :321 | `Color(0xFF54677C)` :88 | **DRIFT** | `#59687d` vs `#54677c` |
| High Contrast | high | `#ffffff` :397 | `Color(0xFFFFFFFF)` :124 | **MATCH** | both `#ffffff` |
| High Contrast | mid | `#e2e8f0` :398 | `Color(0xFFD5DDE6)` :125 | **DRIFT** | `#e2e8f0` vs `#d5dde6` |
| High Contrast | low | `#c3ccd9` :399 | `Color(0xFFD5DDE6)` :126 | **DRIFT** | `#c3ccd9` vs `#d5dde6`; the phone aliases its low tier to its mid tier on purpose (`Themes.kt:110-111,126`) |

### D. Hairlines and the focus edge

| theme | pair | desktop value | phone value | verdict | reason |
|---|---|---|---|---|---|
| Reactor | hairline | `rgba(255, 255, 255, 0.08)` :54 | `Color(0xFF172836)` :49 | **NOT COMPARABLE** | the desktop writes a separator as translucent *white* over an unknown backdrop; the phone writes an opaque slate. No common space — the desktop's rendered colour depends on the surface beneath it |
| Reactor | strong hairline | `rgba(255, 255, 255, 0.14)` :55 | `Color(0xFF24485E)` :50 | **NOT COMPARABLE** | same |
| Reactor | focus edge | `--focus-ring: #7df3ff` :60 | `hairlineFocus = Color(0xFF4E7690)` :51 | **DRIFT** | both opaque, same role and the same 3:1 non-text floor (`theme.css:57-60`, `Chrome.kt:74-83`): a bright cyan vs a slate |
| Daylight | hairline | `rgba(16, 34, 60, 0.14)` :316 | `Color(0xFFC6D0DC)` :89 | **NOT COMPARABLE** | translucent ink vs opaque |
| Daylight | strong hairline | `rgba(16, 34, 60, 0.24)` :317 | `Color(0xFF98A6B6)` :90 | **NOT COMPARABLE** | same |
| Daylight | focus edge | `#005263` :327 | `hairlineFocus = Color(0xFF7C8998)` :91 | **DRIFT** | `#005263` vs `#7c8998` — different answers to the same 3:1 question |
| High Contrast | hairline | `rgba(255, 255, 255, 0.34)` :394 | `Color(0xFF6B7A8A)` :127 | **NOT COMPARABLE** | translucent white vs opaque |
| High Contrast | strong hairline | `rgba(255, 255, 255, 0.6)` :395 | `Color(0xFF9FB0C0)` :128 | **NOT COMPARABLE** | same |
| High Contrast | focus edge | `#ffffff` :405 | `hairlineFocus = Color(0xFF9FB0C0)` :129 | **DRIFT** | `#ffffff` vs `#9fb0c0` |

### E. Semantic ink and mark

| theme | pair | desktop value | phone value | verdict | reason |
|---|---|---|---|---|---|
| Reactor | ok ink | `#3ddc97` :114 | `Palette.VERDANT_4` = `#5fe0a8` :52 | **DRIFT** | `#3ddc97` vs `#5fe0a8`; the desktop value is in **no** spec palette family |
| Reactor | warn ink | `#ffc860` :115 | `Palette.AMBER_4` = `#ffb648` :53 | **DRIFT** | `#ffc860` vs `#ffb648`; `#ffb648` *is* on the desktop — as `--state-approval` (:159) |
| Reactor | bad ink | `#ff6b7a` :116 | `Palette.ROSE_4` = `#ff7b86` :54 | **DRIFT** | `#ff6b7a` vs `#ff7b86`; `#ff7b86` is on the desktop as `--state-error` (:161) |
| Reactor | ok mark | `#3ddc97` :114 | `Palette.VERDANT_4` = `#5fe0a8` :55 | **DRIFT** | duplicate of the ink row on a dark theme |
| Reactor | warn mark | `#ffc860` :115 | `Palette.AMBER_4` = `#ffb648` :56 | **DRIFT** | duplicate |
| Reactor | bad mark | `#ff6b7a` :116 | `Palette.ROSE_4` = `#ff7b86` :57 | **DRIFT** | duplicate |
| Reactor | cloud ink | `#b98bff` :117 | `Palette.VIOLET_4` = `#ae7bff` :58 | **DRIFT** | `#b98bff` vs `#ae7bff` |
| Daylight | ok ink | `#17694a` :328 | `Palette.VERDANT_1` = `#0a3d2a` :93 | **DRIFT** | `#17694a` vs `#0a3d2a` |
| Daylight | warn ink | `#632303` :332 | `Palette.AMBER_1` = `#4a3708` :94 | **DRIFT** | `#632303` vs `#4a3708`; the desktop retuned warn to a burnt orange for deuteranopia separation (`theme.css:329-332`) and it is no palette step |
| Daylight | bad ink | `#b3202f` :333 | `Palette.ROSE_1` = `#521018` :95 | **DRIFT** | `#b3202f` vs `#521018` |
| Daylight | ok mark | `#17694a` :328 | `Palette.VERDANT_2` = `#126b47` :99 | **DRIFT** | `#17694a` vs `#126b47` |
| Daylight | warn mark | `#632303` :332 | `Palette.AMBER_2` = `#8a680e` :100 | **DRIFT** | `#632303` vs `#8a680e` |
| Daylight | bad mark | `#b3202f` :333 | `Palette.ROSE_2` = `#8f1b28` :101 | **DRIFT** | `#b3202f` vs `#8f1b28` |
| Daylight | cloud ink | `#5b34a8` :334 | `Palette.VIOLET_2` = `#551f9c` :105 | **DRIFT** | `#5b34a8` vs `#551f9c` |
| High Contrast | ok ink | `#5cff9d` :406 | `Palette.VERDANT_4` = `#5fe0a8` :130 | **DRIFT** | `#5cff9d` vs `#5fe0a8` |
| High Contrast | warn ink | `#ffd257` :407 | `Palette.AMBER_4` = `#ffb648` :131 | **DRIFT** | `#ffd257` vs `#ffb648` |
| High Contrast | bad ink | `#ff8a95` :408 | `Palette.ROSE_4` = `#ff7b86` :132 | **DRIFT** | `#ff8a95` vs `#ff7b86` |
| High Contrast | ok mark | `#5cff9d` :406 | `Palette.VERDANT_4` = `#5fe0a8` :133 | **DRIFT** | duplicate |
| High Contrast | warn mark | `#ffd257` :407 | `Palette.AMBER_4` = `#ffb648` :134 | **DRIFT** | duplicate |
| High Contrast | bad mark | `#ff8a95` :408 | `Palette.ROSE_4` = `#ff7b86` :135 | **DRIFT** | duplicate |
| High Contrast | cloud ink | `#d0a9ff` :409 | `Palette.VIOLET_4` = `#ae7bff` :136 | **DRIFT** | `#d0a9ff` vs `#ae7bff` |

### F. The three counts, restated

* **3 MATCH** — Daylight card `#ffffff`; High Contrast window ground `#000000`;
  High Contrast high text `#ffffff`.
* **36 DRIFT** — 4 surfaces, 8 text tiers, 3 focus edges, 21 semantic rows
  (of which 9 are the mark rows duplicating the ink rows on Reactor and High
  Contrast, and Daylight's 3 marks genuinely differ from its 3 inks).
  Distinct colour decisions that have drifted: **30** — 4 surfaces + 8 text
  tiers + 3 focus edges + 12 semantic inks (ok/warn/bad/cloud × 3 themes) +
  Daylight's 3 marks.
* **12 NOT COMPARABLE** — 3 Reactor surfaces (alpha), 3 sunken-vs-well (different
  job), 6 hairlines (translucent vs opaque).

---

## 4. What the two files do *not* share at all

**Desktop only.** `theme.css`'s `:root` block declares **98** tokens
(`theme.css:29-272`); **14** of them are the pairs above. The other **84** have
no `Chrome` field: `--surface-hover`/`--surface-active` (:50-51),
`--border-accent` (:56), `--text-on-accent` (:69), the eight raw channel triples
`--accent-rgb`…`--shade-rgb` (:85-92), the three prose tokens (:99-101), the
four accent tokens (:104-107), the four `-faint` tokens (:118-121), the six
semantic surfaces (`--ok-fill`, `--ok-edge`, `--ok-text`, `--bad-fill`,
`--bad-text`, `--accent-text`, :128-133), the four code/diff tokens
(:137-140), the eight face states (:155-162), the six graph tokens (:180-185),
the six swatches plus `--edge-active` (:191-197), five radii and
`--stroke-hair` (:203-212), three fonts (:215-219), the five-step type scale
(:234-238), five motion tokens (:243-247), and the three depth tokens plus nine
tag tokens (:258-271).

Two of the 84 are worth naming because a generator has an easy trap:

* The eight `--*-rgb` triples are **derived** from the eight colours above them
  (`--accent-rgb: 56 240 255` is `#38f0ff` as bare channels, :85 and :104). They
  should be generated from the colour, never authored, or they drift.
* `--accent-dim`, `--accent-faint`, `--border-accent` and `--edge-active` are
  the accent at an alpha, and **the alpha is per theme**: `--accent-faint` is
  `0.12` on Reactor (:107), **`0.1`** on Daylight (:326) and `0.2` on High
  Contrast (:404). So alpha cannot be a single constant in the token file.

**Phone only.** `Chrome.well` (the face's ground, `Themes.kt:45,85,123`) and
`Chrome.postScale` (the glow multiplier, `Chrome.kt:126-131`) have no desktop
theme token. `well` is discussed above; `postScale` is `1f` on all three themes
and the desktop's glow strength is baked into `--glow-accent` (:260), which is
not a multiplier.

**Mirrored a third time, only some of it checked.** The theme *names* and
*blurbs* live in three places: `Themes.kt:39-40,78-79,117-118`,
`jarvis-link.js:848-864` and the settings page the test drives. Only names and
blurbs are asserted equal
(`jarvis-desktop/tests/continuity.mjs:55-67`). `dark` is also a hand copy in
three places — `Themes.kt:41,80,119`, `jarvis-link.js:852,857,862`, and
`theme.css`'s `color-scheme` (:290,297,378) — and **nothing checks it**. It
agrees today (`true`/`false`/`true` on both sides). `id` is copied between
`Themes.kt` and `continuity.mjs:61`'s mapping table and *is* checked.

---

## 5. Two more hand-maintained copies a two-file generator would not fix

Both are real and both are on the phone, which is why they are reported rather
than fixed.

**(a) The Glance widget has its own fixed palette, and it is not any one
theme.** `ApprovalWidget.kt:309-321` states the reason — a Glance `RemoteViews`
host cannot reach the per-face `Chrome` — and then hand-writes seven colours:

| widget token | value | what it is |
|---|---|---|
| `Background` :314 | `#04070C` | Reactor `surface0` |
| `Surface1` :315 | `#0E1822` | Reactor **`surface2`**, not `surface1` |
| `TextHi` :316 | `#E6EEF7` | no theme's high text (`Themes.kt:46` is `#DDE7F2`) |
| `TextMuted` :317 | `#93A6BA` | no theme's mid (`#8FA3B8`) or low (`#6E8397`) text |
| `Accent` :318 | `#63F7FF` | **High Contrast's** accent (`theme.css:401`), while the widget also paints Reactor's ground |
| `StatusOk` :319 | `#6EE7A8` | not `VERDANT_4` `#5FE0A8` |
| `StatusBad` :320 | `#EF6E6E` | not `ROSE_4` `#FF7B86` |

The same three lines are repeated in `QuickLinkWidget.kt:183-184` and
`JarvisBoardWidget.kt:348-349`, and the crash screen hand-writes five more
(`ui/screens/CrashScreen.kt:65,80,89,94,102,105`). **A generator that emits
`theme.css` and `Themes.kt` would leave all four of these where they are.** If
the owner wants one source of truth, the phone's widget palette is a separate,
smaller decision with its own reason already written down.

**(b) The desktop's `faces.html` keeps a second palette, deliberately.**
`faces.html:7-12` says so ("Deliberately NOT theme.css… every colour on screen
here is a sample of the thing being edited"), and its `--void:#05070b`
(`faces.html:16`) differs from `theme.css:41`'s `#04070c` in two hex digits.
This is **not** a defect and must not be "fixed" by the generator:
`tests/themes-all.mjs` names the exclusion on purpose. `scripts/check-tokens.py`
also leaves it out of `FILES` (:12-20), so it is unguarded too. The HUD is the
opposite and is fine — `jarvis_hud.html:52-54` aliases `--void`, `--plate`,
`--plate-2` onto `theme.css`'s tokens.

---

## 6. A third source of truth already exists, and it is copied three times

The 50 palette colours the phone's semantic and state colours are chosen from
are **not** in either theme file: they are in the visual spec, generated into
`Palette.kt` by `tools/gen_palette.py` from
`app/src/test/resources/jarvis-visual-spec.json`, and re-checked by
`SpecDriftTest` (`Palette.kt:8-10`). The same spec JSON is copied three times in
this repo:

| copy | SHA256 |
|---|---|
| `jarvis-desktop/src/jarvis-visual-spec.json` | `7AF57C8EDB8EFF1AD63D88A5D30C2CD165C88FAAED033BF9A21683798A6E4FAC` |
| `jarvis-backend/jarvis-visual-spec.json` | `F0B03FE4739D901DE0C77E4DA4945B38B0694FF6DD9CFC811762946A386B78F7` |
| `jarvis-client/app/src/test/resources/jarvis-visual-spec.json` | `667C480217A6547B5A00D16600223721184153F781E5C30302E76B92DFE45632` |

The `palette.colors` map is **identical** in all three; the copies disagree in
`faces`, `limits`, `interaction`, `audit_history`, `renderer` and `frame_rate`.
So the spec is a genuine shared source for the 50 colours — but it is a
hand-copied one, and `theme.css` (or a new token file) would become a fourth
copy if the 50 colours were inlined into it. That is a design decision for the
token file, flagged in §8.

Where the two apps already agree *by construction* is the **face states**:
every desktop `--state-*` token equals the palette colour the spec binds
(`Spec.kt:359-393`, `jarvis-visual-spec.json` `states[].default`):

| state | desktop token | desktop value | spec colour | verdict |
|---|---|---|---|---|
| idle | `--state-idle` :155 | `#2ea8cc` | `ice-3` (#2EA8CC, `Palette.kt:23`) | **MATCH** |
| listening | `--state-listening` :156 | `#ff9b52` | `ember-4` (`Palette.kt:85`) | **MATCH** |
| thinking | `--state-thinking` :157 | `#ae7bff` | none — the spec binds a *sweep*, `"color": null` | **NOT COMPARABLE** (a token on one side only; `violet-4` is the desktop's pick) |
| speaking | `--state-speaking` :158 | `#6fe3ff` | `ice-4` (`Palette.kt:25`) | **MATCH** |
| approval | `--state-approval` :159 | `#ffb648` | `amber-4` (`Palette.kt:95`) | **MATCH** |
| standby | `--state-standby` :160 | `#6b7d94` | `neutral-3` is `#46566a` (`Palette.kt:113`) | **DRIFT, declared** — `theme.css:151-154` states the divergence and the measured reason |
| error | `--state-error` :161 | `#ff7b86` | `rose-4` (`Palette.kt:75`) | **MATCH** |
| banked | `--state-banked` :162 | `#8fa3b8` | `neutral-4` (`Palette.kt:115`) | **MATCH** |

That is 6 MATCH, 1 declared DRIFT, 1 not comparable — a good advertisement for
the shared-source approach, and the reason the drift in §3 stands out: the
desktop's *state* colours follow the spec exactly, while its *semantic* colours
(`--ok`/`--warn`/`--bad`/`--info`) are bespoke values that appear in no palette
family. A values-match test written the naive way — compare the desktop's tokens
with the phone's fields, alphabetically — would put these 8 state rows on the
to-do list when 6 of them are already in parity.

---

## 7. The accent: not a token, and not the same function

`Chrome.kt:163-171` says the accent is deliberately **not** a theme token: it is
`accentFor(chrome, boundIdleColour)` (Chrome.kt:178-197), so the chrome can never
disagree with the face. `jarvis-link.js:921-934` says the desktop now ports that
function, and it does (`legibleColour`, `jarvis-link.js:989-1015`, used at
`:1037`).

**How the desktop actually reads theme values.** It does not read a table. When
the owner has bound colours, `paintAppearance()` (`jarvis-link.js:1072-1095`)
reads the live CSS: `getComputedStyle(root).getPropertyValue("--surface-1")`
(:1081) and `--text-on-accent` (:1084), composites the surface over black *and*
white (:1086), takes `dark` from `THEME_INFO` (:1083,1087) and `strict` from the
theme id (:1088). When nothing is bound it returns early (:1079), so what the
user sees is `theme.css` itself. **A parity test must therefore read
`theme.css`, not this module** — and any generator that emits `theme.css` keeps
this working unchanged.

**The two implementations of "the same function" are not identical**, in three
ways that matter:

1. **Floor.** The desktop holds High Contrast to **7:1** (`:1037`, `strict` from
   `:1088`); the phone calls `accentFor` with its default **4.5:1** and never
   passes `strict` (`JarvisTheme.kt:419-420`; the default is `Chrome.kt:178`).
2. **Backdrop.** The desktop measures the **worst of the surface over black and
   over white** (`:990`, `:1086`); the phone measures `surface1` alone
   (`Chrome.kt:191`). Justified — the desktop's windows are translucent — but it
   means the same binding can select a different step on each side.
3. **When it runs.** The phone derives the accent on **every** theme
   (`JarvisTheme.kt:419`), so an untouched install gets
   `accentFor(theme, ice-3)`. The desktop only overrides when the owner has
   bound colours (`:1079`), so an untouched install keeps `theme.css`'s value.

The consequence, on an untouched install:

| theme | desktop, as shipped | phone, `accentFor(theme, ice-3)` | agree? |
|---|---|---|---|
| Reactor | `--accent: #38f0ff` (`theme.css:104`) | `ice-3` → `#2ea8cc` | **no** |
| Daylight | `--accent: #00697f` (`theme.css:323`) | `ice-2` → `#12657f` | **no** |
| High Contrast | `--accent: #63f7ff` (`theme.css:401`) | `ice-3` → `#2ea8cc` | **no** |

(Computed by re-implementing both 18-line functions from the citations above and
running them on `Palette.kt`'s values; when idle *is* bound to `ice-3`, both land
on `ice-3` for Reactor and High Contrast and on `ice-2` for Daylight, so the
algorithms agree on that input. No Kotlin was run here — see §9.)

**A second writer already disagrees with the first, in the same file's alphas.**
`theme.css` and `jarvis-link.js` both write `--border-accent` and `--edge-active`,
and their alphas differ today:

| token | `theme.css` Reactor | Daylight | High Contrast | injected by `jarvis-link.js:1052-1053` |
|---|---|---|---|---|
| `--border-accent` | `rgba(56,240,255,0.32)` :56 | `rgba(0,110,140,0.4)` :318 | `#63f7ff` (opaque) :396 | `rgba(a, **0.34**)`, always translucent |
| `--edge-active` | `rgba(56,240,255,0.65)` :197 | `rgba(0,105,127,0.7)` :340 | `#63f7ff` (opaque) :415 | `rgba(a, **0.65**)`, always translucent |

So the moment the owner binds a colour, High Contrast's opaque border becomes a
34%-opaque cyan, and Daylight's 40% border becomes 34%. Nothing tests this. Any
token file has to decide whether it owns these two tokens or `jarvis-link.js`
does — the handoff's Phase B step 2 only mentions `theme.css` and `Themes.kt`.

---

## 8. The DTCG shape

The handoff's rules, restated because everything below depends on them
(`docs/HANDOFF-UI-RESEARCH-2026-10-09.md:210-212`): a **token** is any object
with `$value`; a **group** is any object without it; `$type` inherits down; an
**alias** is `{group.token}`. Zero dependencies, Node ≥ 22 is not required for
the build (`:221-224`).

### 8.1 Structure

```jsonc
{
  "$description": "The three themes, one value each. Generated by hand-reviewed edits only.",
  "colour": {
    "$type": "color",
    "palette": {
      "$description": "The spec's 50. DO NOT author here: Palette.kt is generated from
                        jarvis-visual-spec.json (Palette.kt:8-10) and SpecDriftTest re-reads it.
                        Either generate this group from the spec, or alias it.",
      "ice-3":  { "$value": "#2ea8cc" },
      "amber-4": { "$value": "#ffb648" }
      // …48 more
    }
  },
  "theme": {
    "reactor": {
      "desktopId": { "$type": "string",  "$value": "deep-space" },
      "phoneId":   { "$type": "string",  "$value": "reactor" },
      "label":     { "$type": "string",  "$value": "Reactor" },
      "blurb":     { "$type": "string",  "$value": "The default. Cool near-black, built around the reactor's own light." },
      "dark":      { "$type": "boolean", "$value": true },

      "surface0": {
        "$value": { "colorSpace": "srgb", "components": [4, 7, 12], "alpha": 0.86, "hex": "#04070c" },
        "$extensions": {
          "jarvis": { "css": "--bg-window", "kotlin": "surface0", "parity": "rgb" }
        }
      },
      "surface1": {
        "$value": { "colorSpace": "srgb", "components": [10, 17, 25], "alpha": 0.9, "hex": "#0a1119" },
        "$extensions": { "jarvis": { "css": "--surface-1", "kotlin": "surface1", "parity": "rgb" } }
      },
      "hairline": {
        "$description": "Desktop: translucent white overlay. Phone: opaque slate. Not one value.",
        "$value": { "colorSpace": "srgb", "components": [255, 255, 255], "alpha": 0.08, "hex": "#ffffff" },
        "$extensions": { "jarvis": { "css": "--border", "kotlin": "hairline", "parity": "none" } }
      },
      "warnInk": {
        "$value": "{colour.palette.amber-4}",
        "$extensions": { "jarvis": { "css": "--warn", "kotlin": "warnInk", "parity": "exact" } }
      }
    }
    // "daylight" and "contrast" the same shape
  }
}
```

### 8.2 Why each part is there

* **`$value` as the object form.** Nine of the desktop's paired tokens carry an
  alpha — the three Reactor surfaces and all six hairline pairs — and the draft
  colour object is the only form that puts the alpha *in* `$value`. If the
  generator prefers the string form (`"$value": "#04070c"`) for tool
  compatibility, the alpha has to move into `$extensions.jarvis.css.alpha`
  — either is workable, but it must be one or the other, decided once.
* **`$type: "color"` on the `colour` group, inherited down**
  (`theme.reactor.surface0` has no `$type` of its own). `label`/`blurb`/`dark`/
  `desktopId`/`phoneId` override with `"string"` or `"boolean"` because they are
  not colours.
* **Aliases, not copies, for anything that is a spec palette colour.** The phone
  already writes `Palette.AMBER_4` (`Themes.kt:53`); the desktop writes the hex
  literally (`theme.css:159`). `{colour.palette.amber-4}` is what makes the
  desktop's `--state-approval` and the phone's `warnInk` provably the same
  colour instead of two hexes that happen to agree.
* **`$extensions.jarvis` carries the platform bindings**, which is exactly what
  DTCG reserves `$extensions` for: the CSS custom-property name (or `null`), the
  Kotlin `Chrome` field name (or `null`), and `parity`.
* **`parity` is the load-bearing key**, and its three values come straight out
  of §3: `"exact"` (both sides must equal, alpha included — 3 rows today),
  `"rgb"` (RGB must agree, the desktop adds an alpha — 3 rows), `"none"`
  (deliberately different, reason in `$description` — 12 rows). Without it, a
  `--check` mode fails on day one on the 12 rows that are not supposed to match.
* **What the file must also be able to express, or the generator will hardcode
  it:**
  * the **84 desktop-only** tokens of §4 (`css` set, `kotlin` null) and the one
    value only the phone has a theme token for, `postScale` (`kotlin` set,
    `css` null). `well` needs both keys with `parity: "none"` — it maps onto the
    desktop's differently-purposed `--surface-sunken`;
  * the **derived** channel triples (`--accent-rgb`) and the alpha-suffixed
    tokens (`--accent-dim`, `--accent-faint`, `--border-accent`,
    `--edge-active`), whose alpha is **per theme** (§4) — so either each is a
    token of its own, or the token file carries an `alpha` per theme;
  * `--accent-text: var(--accent-bright)` (`theme.css:133`) — an intra-file
    alias, expressible as `{theme.reactor.accentBright}`;
  * the **face states**, aliased to `{colour.palette.*}` (§6), which is what
    makes the desktop's `--state-*` block generated rather than typed;
  * **`--state-standby`**, the one declared divergence (`theme.css:151-154`) —
    a literal with a `$description`, *not* an alias to `neutral-3`.
* **What it must not do:** emit an accent for the phone (there is none —
  `Chrome.kt:163-171`), or unify the 12 `parity: "none"` rows, or touch the
  phone's widget palette (§5a) or `faces.html` (§5b).

### 8.3 What a `--check` drift mode compares

Compare only `parity: "exact"` and `parity: "rgb"` rows, by parsing
`theme.css`'s `:root` and the two `[data-theme]` blocks and `Themes.kt`'s
`Chrome(...)` blocks (both are regular enough for a regex — `continuity.mjs:58`
already parses `id`/`label`/`blurb` out of Themes.kt that way). Skip
`parity: "none"`. Never compare the computed accent (§7) or `--state-standby`
(§6). The two-backdrop contrast walk the desktop already has
(`tests/themecheck.mjs:7-9,14-43`, `tests/contrast.mjs:1-20`) should run on the
generated output, exactly as the handoff asks (`:218-219`).

---

## 9. What could not be determined

Listed plainly, because each one is a question the next session has to ask
somebody rather than measure:

1. **Which side is authoritative.** Nothing in the repo says whether the desktop
   should adopt the phone's values or the other way round. The two sides have
   counter-comments: `theme.css:34-40` moved *only* the surfaces and says the
   text colours "stay as they are"; `Chrome.kt:20-25` and `Themes.kt:16-25`
   explain the phone's semantic and text choices as measured decisions. So the
   36 drifts are not 36 bugs — they are one design question per block.
2. **Whether the desktop's `--ok`/`--warn`/`--bad`/`--info` were ever meant to
   be palette steps.** None of `#3ddc97`, `#ffc860`, `#ff6b7a`, `#b98bff` is one
   of the spec's 50, and no comment, commit message or doc says why. The desktop
   *does* use palette values where the meaning is a state (`--state-approval` is
   `amber-4`), so the split looks intentional — but I could not evidence it.
3. **Whether the Daylight/High-Contrast surface gaps are typos or re-tunes.**
   Daylight's desktop surfaces are uniformly lighter than the phone's by a few
   units (`#f4f6f9` vs `#eef1f6`, `#edf1f6` vs `#e8edf4`), and High Contrast's
   keep a three-step ramp where the phone flattened to two. Both readings are
   consistent with the evidence; no commit message says which.
4. **The provenance of the "three drifted a digit" claim.** It is stated twice
   with no citation (handoff `:205-208`, summary `:53-55`). I could not
   reproduce a same-role one-digit drift; the only three one-digit pairs in the
   whole tree are cross-role (§1). Not disproved as a memory of something, but
   not verifiable from this repo, and wrong as a description of today's state.
5. **Whether the phone's widget palette (§5a) is stale or intended.**
   `ApprovalWidget.kt:309-312` explains why it is fixed; it does not explain why
   its `Accent` is High Contrast's cyan while its surfaces are Reactor's.
6. **What either app actually renders.** This measured declared values. The
   desktop's surfaces are translucent, so their rendered colour depends on the
   wallpaper behind them; the phone's are opaque. "Both apps show the same
   colour" is not decidable from these two files.
7. **The phone's Compose rendering was read, not run.** No Android build or
   emulator was used. The accent values in §7 come from re-implementing
   `accentFor` (`Chrome.kt:178-197`) and `legibleColour`
   (`jarvis-link.js:989-1015`) from their own source and running them on
   `Palette.kt`'s values — 18 lines each, read line by line — not from executing
   Kotlin. What gives the desktop half confidence is that the same function is
   already covered by `continuity.mjs:110-124`, which asserts an accent stays in
   its own family and clears 4.5:1; the phone half has no equivalent test I could
   find. (Small aside: `jarvis-link.js:987` says `tests/theme-follow.mjs` can
   check it without a browser — **that file does not exist**; the coverage is in
   `continuity.mjs` instead.)
8. **Whether `--accent-bright` (`#b8fbff`, `theme.css:105`) is meant to be
   `ice-5` (`#b8f4ff`, `Palette.kt:27`).** One hex digit apart, in the same
   visual role (a paler accent), and the phone has no accent-bright token to
   answer with.

---

## 10. How to re-run this

The parser was a throwaway script, not added to the repo (writing `tools/` was
out of scope for this task). It did three things, each easy to repeat:

1. Read `theme.css` and pull the declarations out of the four blocks
   `:root`, `[data-theme="deep-space"]`, `[data-theme="paper"]`,
   `[data-theme="high-contrast"]` — a brace-matching scan, then
   `/(--[a-z0-9-]+)\s*:\s*([^;]+);/g` inside each block; resolve a later block
   against `:root` for the tokens it does not redefine.
2. Read `Themes.kt` with the same shape `continuity.mjs:58` already uses —
   `/val (REACTOR|DAYLIGHT|CONTRAST) = Chrome\(([\s\S]*?)\n    \)/` then
   `/(\w+) = (?:Color\(0x(FF[0-9A-Fa-f]{6})\)|Palette\.([A-Z]+_\d))/g` — and
   resolve every `Palette.X` through `Palette.kt`'s
   `/val ([A-Z]+_\d) = Color\(0x(FF[0-9A-Fa-f]{6})\)/g`.
3. Compare the 17 rows of §2 per theme, then sweep every `0xFFRRGGBB` in
   `jarvis-client/app/src/main` against every hex/`rgb()` literal in
   `theme.css` for hex-digit distance.

```powershell
git fetch origin; git rev-parse origin/main   # 81547649 (was 0541ae60 mid-measurement)
```

The one thing worth re-checking first, per the handoff's own step 1
(`docs/HANDOFF-UI-RESEARCH-2026-10-09.md:520-522`): **`git log --oneline -5` and
whether `main` has moved.** Every file this document rests on was identical
between `origin/main` and the working tree at **both** `0541ae60` and
`81547649`; if `main` moves again, re-verify `theme.css` and `Themes.kt` before
trusting a single row above.
