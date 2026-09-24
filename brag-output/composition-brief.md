# Hyperframes Composition Brief: Jarvis

## Objective
Create a short, cinematic launch video for Jarvis — a private, local-first
personal assistant with a Windows desktop app and an Android phone app.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: ~20s (18-21s acceptable)

## Source Material
- Project root: `/home/user/Epic-Jarvis`
- Primary files read: `README.md`, `docs/ARCHITECTURE.md`,
  `jarvis-desktop/src/theme.css`, `jarvis-desktop/src/faces-spec.js`,
  `jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt`,
  `jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/BrainScreen.kt`
- Product name: Jarvis
- Tagline / strongest claim: "Your own Jarvis: a voice assistant that lives
  on your PC, answers to 'Hey Jarvis', and never sends your private life to
  anyone else's cloud."
- Key UI or visual moment to recreate: the reactor face — a glowing animated
  disc that changes colour/state (idle → listening → thinking → speaking) —
  and the approval card with its live countdown.
- Copy that must appear verbatim:
  - "Hey Jarvis."
  - "Nothing leaves the room."
  - "Your assistant. Your PC. Your rules."
  - "Expires in 0m 45s" (or a similarly formatted live countdown — matches
    the real `ExpiryCountdown` composable's `"Expires in ${m}m ${s}s"` format)

## Creative Direction
- Tone preset: cinematic
- Creative direction: dark, precise, a little cinematic — the reactor face
  as hero image, calm confidence rather than hype
- Interpretation: wide, deliberate shots; big display type that lands and
  holds; dramatic reveals rather than rapid cuts; roughly 5 scenes, each
  given room to breathe
- Angle: play it straight, like a serious product film. No jokes. The
  reactor face glowing alone in the dark IS the opening image. The claim
  "nothing leaves the room" carries the whole hook.
- Hook: near-black frame, one glowing reactor face (idle, cool cyan),
  "Hey Jarvis." slams in, then "Nothing leaves the room."
- Outro / punchline: phone and desktop side by side, faces synced, "Your
  assistant. Your PC. Your rules."
- Avoid:
  - Generic SaaS language ("streamline your workflow" etc.)
  - Abstract filler visuals unconnected to the real product
  - Unrelated visual redesign — stay inside the token palette below
  - Any implication of speed/accuracy benchmarks (none exist)
  - Any competitor name (no Gemini/Siri/ChatGPT)
  - Any Play Store / app store reference (this is sideloaded, non-commercial)
  - Any of the roadmap items (second-GPU mode, big-model mode, reminders,
    calendar, etc.) — not in scope for this video at all
  - Real personal data on screen — any sample data must be obviously fake

## Visual Identity
- Background: `#08090c` (from `--bg-window: rgba(8, 9, 12, 0.86)`)
- Text: `#f2f5f8` primary, `#a8b2c1` muted (from `--text` / `--text-muted`)
- Accent: `#38f0ff` (cyan, from `--accent`)
- Face-state colours (use these, not invented ones):
  idle `#2ea8cc`, listening `#ff9b52`, thinking `#ae7bff`,
  speaking `#6fe3ff`, approval `#ffb648`
- Display font: "Chakra Petch" (real product font,
  `jarvis-desktop/src/fonts/chakra-petch-*.woff2` — if not portable into the
  composition, substitute a similar geometric/technical display face and
  note the substitution)
- Body font: system sans (Segoe UI Variable Display fallback chain)
- Visual references from the project: the reactor face's colour-crossfade
  behavior between states (~300ms), the approval card's swipe gesture and
  live countdown text, the token-based theming system (dark, translucent
  surfaces, one accent hue plus semantic state colours)

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. Hook — 3.5s — reactor face idle (cyan), "Hey Jarvis." then "Nothing
   leaves the room."
2. Reveal: private by design — 4s — abstracted glow suggesting the owner's
   own graphics card; "Runs on your own graphics card." then "Email, files,
   credentials, memory — never leave this PC."
3. Voice — 4.5s — face crossfades idle → listening (amber) → thinking
   (violet); "Hey Jarvis." (smaller/spoken) then "Speech is understood on
   the PC. Not the cloud."
4. Approval cards — 5.5s — phone + desktop side by side; a card slides in
   with a live countdown ("Expires in 0m 45s"); simulated right-swipe to
   approve; face tints amber (approval state) in sync; "It asks first.
   Every time." then "One card. One decision. Nothing is ever
   auto-approved."
5. Outro — 3s — phone + desktop at rest, faces synced back to idle cyan;
   "Your assistant. Your PC. Your rules." long hold, cut to black.

## Audio
- Audio role: cinematic support — low, steady bed with two restrained swells
- Audio arc: near-silent open → steady bed (~0.3) through the middle → small
  lift into the approval-card beat → fade to near-silence under the outro
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
- Music treatment: fade up from ~0 under Scene 1's second line; hold ~0.3
  through Scenes 2-3; small perceived lift into Scene 4's swipe-resolve;
  fade down through Scene 5's hold, silent by the cut to black. Never above
  0.4.
- Music cue guidance: bundled preset at
  `happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.md/json`
  (tempo ~110 BPM). Candidate strong-cue locks (±0.15s): ~8.74s for the
  Scene 3 listening-state entrance, ~17.47s/18.56s for the Scene 4
  swipe-resolve. Use only if they don't cost readability — natural timing
  is fine otherwise.
- Audio-reactive treatment: subtle — let the reactor face's glow/opacity
  breathe gently with RMS or bass energy in Scenes 2-4; no waveform or
  equalizer visuals.
- Audio-coupled moments:
  - Scene 1 — the "Nothing leaves the room." line landing — soft
    impact/bell cue
  - Scene 3 — the face's crossfade into listening — soft interface tone
  - Scene 4 — card slide-in, then the swipe-resolve — card-slide SFX, then
    a distinct resolve SFX
  - Scene 5 — the closing line — one restrained final impact/bell cue
- SFX selection guidance: sparse, cinematic-weight families —
  `impact/impactBell_heavy_*`, `impact/impactSoft_medium_*`,
  `casino/card-slide-*` for the card's entrance. 2-4 cues total, no
  stacking, softer volumes (polished/cinematic posture, not chaotic).
- SFX analysis guidance: read
  `<hyperframes-skills>/assets/sfx/sfx-analysis.md` if available; prefer
  low/medium high-frequency-risk files for the repeated card/impact moments.
- Exact SFX choice: Hyperframes should pick exact filenames, timestamps,
  density, and volume once the animation exists.
- Audio files: copy the chosen music (and any SFX Hyperframes selects) into
  `brag-output/composition/assets/`.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills —
`hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`,
`hyperframes-keyframes`, and `hyperframes-cli`. `/brag` is its own
workflow: do not enter the `hyperframes` entry-point intent interview or
route into its generic promo/launch-video workflow. Prefer native
Hyperframes conventions over anything prescribed here.

Requirements:
- Show at least one real UI/copy/visual element from the source project
  (the reactor face states + colours, and the approval card's countdown
  copy, both satisfy this — use the real values above, not invented ones).
- Keep all text readable in the final render (respect the reading-time
  floors from `brag-plan.md`/`step-2-plan.md`).
- Keep the video within 15-25 seconds.
- Include the planned music/SFX layer (not disabled by the user).
- Treat the audio notes above as guidance, not a fixed cue sheet — choose
  exact SFX after the visual animation exists.
- Treat music cue metadata as optional timing hints; ignore cues that hurt
  readability, pacing, or story. 1-3 strong-cue locks max.
- Honor the planned fade-in/fade-out and volume posture (never above 0.4
  for music, softer values for a cinematic/restrained posture).
- Add a subtle audio-reactive treatment on the reactor face's glow if
  extraction is available; skip and note it if not — do not block the
  render on it.
- Use local assets for audio and any runtime/media dependencies.
- Run `npx hyperframes check` before render — it is `/brag`'s single gate.

Hard constraints carried over from the brief (do not violate):
- No benchmark numbers, no speed claims, no accuracy claims.
- No competitor names (Gemini, Siri, ChatGPT).
- No Play Store / app store language — this is sideloaded.
- Nothing from the "waiting for hardware" or "planned/next" feature lists
  appears on screen, even implied as working today.
- No real device names, usernames, network addresses, tokens, or real email
  content on screen. Any sample text (e.g. an approval card's subject line)
  must read as obviously fictional, in the spirit of "Dentist, Tuesday
  10:00" — e.g. "Lock the front door" or "Run cleanup.sh".
