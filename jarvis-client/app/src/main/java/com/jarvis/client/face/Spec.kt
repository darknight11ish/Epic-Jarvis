package com.jarvis.client.face

import androidx.compose.ui.graphics.Color
import com.jarvis.client.FaceState

/**
 * The parts of `jarvis-visual-spec.json` the client actually renders.
 *
 * Transcribed as Kotlin constants rather than parsed from the JSON asset, and
 * the reason is worth recording: the spec is the *contract*, but it is also
 * 59 KB of which this client reads perhaps a tenth, and a parse failure on a
 * field nobody uses would take the face down. Every value below carries the
 * spec path it came from so a drift is findable by grep.
 *
 * The one thing that must NOT be hardcoded is a state's colour. The user binds
 * those and can re-roll all seven with Randomise, so a constant would be wrong
 * the moment they touch it and the phone would then disagree with the desktop
 * about what Jarvis is doing. [Bindings] carries them; the values here are only
 * the spec's defaults for a fresh install.
 */
object Spec {

    // palette.colors — the entries this client names. Full ARGB, as the spec
    // exports them for exactly this purpose.
    val ICE_3 = Color(0xFF2EA8CC)
    val ICE_4 = Color(0xFF6FE3FF)
    val ICE_5 = Color(0xFFB8F4FF)
    val EMBER_4 = Color(0xFFFF9B52)
    val AMBER_4 = Color(0xFFFFB648)
    val ROSE_4 = Color(0xFFFF7B86)
    val NEUTRAL_3 = Color(0xFF46566A)
    val NEUTRAL_4 = Color(0xFF8FA3B8)

    /** renderer.background — one background for all faces, replacing each face's own. */
    val BACKGROUND = Color(0xFF04070C)

    /** renderer.depth_gain — exponent on the perspective depth factor. */
    const val DEPTH_GAIN = 1.6f

    // state_transforms
    const val RATE_EASE_S = 0.22f
    const val COLOR_EASE_S = 0.30f
    const val TINT_DELAY_APPROVAL_S = 0.10f
    const val APPROVAL_CLOCK_S = 20f
    const val LISTEN_FLOOR = 0.28f

    // state_transforms.amp_envelope — the microphone.
    const val MIC_ATTACK_S = 0.03f
    const val MIC_RELEASE_S = 0.22f
    const val MIC_GATE = 0.04f

    // speech — Jarvis's own voice.
    const val VOICE_ATTACK_S = 0.04f
    const val VOICE_RELEASE_S = 0.12f
    const val VOICE_GATE = 0.04f
    const val SPEAK_FLOOR = 0.18f
    const val SPEECH_SCALE = 0.035f
    const val SPEECH_BRIGHTNESS = 0.18f
    const val SPEECH_FALLBACK_AFTER_S = 0.5f
    const val SPEECH_SYLLABLE_HZ = 4.2f
    const val SPEECH_REST_EVERY_S = 2.3f
    const val SPEECH_REST_S = 0.22f

    // interaction.tap / interaction.drag
    const val TAP_RING_S = 0.15f
    const val TAP_FLINCH_S = 0.15f
    const val TAP_FLINCH_FRAC = 0.01f
    const val TAP_RING_FRAC = 0.28f
    const val DRAG_YAW_PER_PX = 0.008f
    const val DRAG_PITCH_PER_PX = 0.006f
    const val DRAG_PITCH_LIMIT = 1.4f
    const val DRAG_INERTIA_TAU_S = 0.45f
    const val DRAG_MAX_RAD_S = 4f

    // frame_rate.state_fps — resting states are nine tenths of screen-on time.
    fun fpsFor(state: FaceState): Int = when (state) {
        FaceState.IDLE, FaceState.APPROVAL -> 30
        FaceState.STANDBY -> 15
        FaceState.BANKED -> 2
        else -> 0 // 0 means "every frame the display gives us"
    }

    /** The 600 ms after any change, and any tap, run at full rate regardless. */
    const val FULL_RATE_WINDOW_S = 0.6f

    // limits.flash — photosensitive-seizure bounds. Hard limits, not advice:
    // the face fills well over a quarter of the visual field at phone reading
    // distance, so the small-area exemption does not apply.
    const val FLASH_MAX_TRANSITIONS_PER_S = 3
    const val FLASH_MIN_LUMA_DELTA = 0.10f

    /**
     * state_transforms.states — the four borrowed states, as a clock
     * multiplier, a direction, a dim and at most one overlay. Applied by the
     * shell on top of a borrowed motion table so all faces behave identically
     * and this is implemented once rather than twenty times.
     */
    data class Transform(
        val borrow: FaceState,
        val rate: Float,
        val dir: Int,
        val dim: Float,
        val overlay: Overlay,
    )

    enum class Overlay { NONE, CLOCK, HITCH, NOTCHES }

    fun transformFor(state: FaceState): Transform = when (state) {
        // Borrows IDLE, not listening. A dozen faces branch on the state name
        // and multiply by the microphone level, and during an approval the mic
        // is not live — so borrowing listening made the one state that must
        // pull the eye across a room the deadest thing on the screen.
        FaceState.APPROVAL -> Transform(FaceState.IDLE, 1.0f, 1, 1.0f, Overlay.CLOCK)
        // Runs BACKWARDS, and nothing else in this product ever does, so the
        // direction is the signal. Colour alone fails for the one man in twelve
        // with a red-green deficiency, at a glance, and in any frozen frame.
        FaceState.ERROR -> Transform(FaceState.THINKING, 0.3f, -1, 0.9f, Overlay.HITCH)
        FaceState.STANDBY -> Transform(FaceState.IDLE, 0.5f, 1, 0.6f, Overlay.NONE)
        // Still, not slow. rate 0.0 means the clock actually stops.
        FaceState.BANKED -> Transform(FaceState.IDLE, 0.0f, 1, 0.45f, Overlay.NOTCHES)
        else -> Transform(state, 1.0f, 1, 1.0f, Overlay.NONE)
    }

    /** True when the state should get the cached glow halo. renderer.active_states. */
    fun isActive(state: FaceState): Boolean = when (state) {
        FaceState.LISTENING, FaceState.THINKING, FaceState.SPEAKING,
        FaceState.APPROVAL, FaceState.ERROR,
        -> true
        else -> false
    }
}

/** A pattern kind from `pattern_kinds`. Only the ones a default uses are here. */
enum class PatternKind { SOLID, HUE_SWEEP, BREATHE, PULSE, GRADIENT, REACTIVE, COMET, STROBE }

/**
 * One state's binding: which pattern, which colour, and the pattern's params.
 *
 * `color` is nullable because `hue_sweep` derives its own hue and a bound colour
 * would fight it.
 */
data class Binding(
    val kind: PatternKind,
    val color: Color?,
    val periodS: Float = 4.5f,
    val depth: Float = 0.45f,
    val sharpness: Float = 9f,
    val spanDeg: Float = 360f,
    val offsetDeg: Float = 0f,
    val sat: Float = 0.8f,
    val light: Float = 0.62f,
    val loud: Color? = null,
    val gain: Float = 1.6f,
    val to: Color? = null,
)

/**
 * The per-state bindings. Defaults are the spec's `states[].default`, including
 * the three the second audit corrected.
 */
data class Bindings(val byState: Map<FaceState, Binding>) {

    fun of(state: FaceState): Binding = byState[state] ?: DEFAULTS.byState.getValue(FaceState.IDLE)

    companion object {
        val DEFAULTS = Bindings(
            mapOf(
                FaceState.IDLE to Binding(PatternKind.BREATHE, Spec.ICE_3, periodS = 4.5f),
                // Ember stays: it is the product's established look. Listening is
                // made unmistakable by MOTION instead — the mic envelope scales
                // the whole face.
                FaceState.LISTENING to Binding(PatternKind.SOLID, Spec.EMBER_4),
                // A narrow cool sweep, hue 217-275. The full rainbow had no
                // identity — sixteen faces red, three green, one violet in one
                // gallery — and its first replacement bottomed out on cyan,
                // which is idle's hue, so a thinking face caught at that phase
                // read as idle.
                FaceState.THINKING to Binding(
                    PatternKind.HUE_SWEEP, null,
                    offsetDeg = 246f, spanDeg = 58f, periodS = 5f, sat = 0.72f, light = 0.62f,
                ),
                // Was gradient azure→magenta, whose own colours beat the bound
                // ice and rendered speaking pink on nineteen of twenty faces.
                FaceState.SPEAKING to Binding(
                    PatternKind.REACTIVE, Spec.ICE_4, loud = Spec.ICE_5, gain = 1.4f,
                ),
                FaceState.APPROVAL to Binding(PatternKind.PULSE, Spec.AMBER_4, periodS = 1.8f),
                FaceState.STANDBY to Binding(PatternKind.BREATHE, Spec.NEUTRAL_3, periodS = 11f),
                // A pulse on rose that never leaves rose. Was strobe to
                // near-black, so any glance on the off phase saw nothing and
                // read as crashed.
                FaceState.ERROR to Binding(
                    PatternKind.PULSE, Spec.ROSE_4, periodS = 1.1f, sharpness = 4f,
                ),
                FaceState.BANKED to Binding(PatternKind.SOLID, Spec.NEUTRAL_4),
            ),
        )
    }
}
