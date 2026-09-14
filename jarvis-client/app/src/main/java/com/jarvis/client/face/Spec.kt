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

    // The palette lives in Palette.kt now, generated from the spec JSON rather
    // than typed in by hand. These aliases stay so existing call sites keep
    // reading; new code should name Palette directly.
    val ICE_3 = Palette.ICE_3
    val ICE_4 = Palette.ICE_4
    val ICE_5 = Palette.ICE_5
    val EMBER_4 = Palette.EMBER_4
    val AMBER_4 = Palette.AMBER_4
    val ROSE_4 = Palette.ROSE_4
    val NEUTRAL_3 = Palette.NEUTRAL_3
    val NEUTRAL_4 = Palette.NEUTRAL_4

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
     * limits.flash.strobe_max_s — a strobe may not run longer than this at full
     * face width. Enforced by [StrobeBudget]; nothing enforced it before, and
     * the state most likely to strobe is error, which lasts until someone fixes
     * whatever is wrong.
     */
    const val STROBE_MAX_S = 2.0f

    /**
     * The shortest strobe period that stays inside the transition budget.
     *
     * `2 / max_transitions_per_s`, which is 0.667s — **not** the 0.4 the
     * strobe pattern's own `safety` prose gives. A strobe makes TWO opposing
     * transitions per period, not one, so 0.4s is 5 transitions a second
     * against a limit of 3. I took 0.4 from that sentence and shipped it; the
     * spec's `enforced_in.resolve` says `2/max_transitions_per_s` and the
     * arithmetic agrees with the spec, not with the prose.
     *
     * The desktop hit the same factor of two from the other side — its first
     * clamp used `1/max_transitions_per_s` and still ran at 5.67/s — and only
     * measuring caught it. Hence the test that counts transitions rather than
     * asserting this constant.
     */
    const val STROBE_MIN_PERIOD_S = 2f / FLASH_MAX_TRANSITIONS_PER_S

    /**
     * limits.flash.flicker_rate_hz_max and flicker_harmonic.
     *
     * 1.3 is already the harmonic-adjusted cap: 1.3 x 2.3 = 2.99, just under
     * the three opposing transitions a second the guidance allows. Worth
     * flagging upstream that `why_these_numbers` says "the stated rate must
     * stay below the limit divided by 2.3", which would cap it at 0.57 and make
     * the spec's own flicker default of 1.2 Hz illegal. The numbers are
     * self-consistent; the sentence explaining them is not.
     */
    const val FLICKER_RATE_HZ_MAX = 1.3f
    const val FLICKER_HARMONIC = 2.3f

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

/**
 * The eleven kinds from `pattern_kinds`.
 *
 * All eleven, not the eight a shipped default happens to use: `randomise` can
 * roll `cycle` or `temperature` for thinking and `flicker` for approval or
 * error, so a picker on eight kinds is a Randomise button that silently cannot
 * produce three of its own outcomes.
 */
enum class PatternKind {
    SOLID, HUE_SWEEP, STEP_CYCLE, BREATHE, PULSE, GRADIENT,
    COMET, FLICKER, REACTIVE, TEMPERATURE, STROBE,
}

/**
 * A pattern's parameters. Every field is nullable, and that is the whole point.
 *
 * Null means *unset*, which is what lets rule 1 work: the pattern's own params
 * are the base and the binding overrides them key by key. The previous shape
 * gave every field one generic default shared by all twelve patterns, so an
 * unset key fell back to 4.5 seconds and a 360° span whatever pattern it
 * belonged to — a bound `sweep` rendered as a full rainbow, and an unbound
 * `gradient` ran ice→ice instead of azure→magenta. It happened to be invisible
 * because the eight shipped bindings hardcode their merged result; it would
 * have become visible on the first pattern anyone picked.
 */
data class Params(
    val color: Color? = null,
    val periodS: Float? = null,
    val depth: Float? = null,
    val sharpness: Float? = null,
    val spanDeg: Float? = null,
    val offsetDeg: Float? = null,
    val sat: Float? = null,
    val light: Float? = null,
    val from: Color? = null,
    val to: Color? = null,
    val tail: Color? = null,
    /** `strobe`'s two colours, which the spec calls `a` and `b`. */
    val onColor: Color? = null,
    val offColor: Color? = null,
    val quiet: Color? = null,
    val loud: Color? = null,
    val gain: Float? = null,
    val colors: List<Color>? = null,
    val holdS: Float? = null,
    val blendS: Float? = null,
    val family: String? = null,
    val rateHz: Float? = null,
    val cold: Color? = null,
    val warm: Color? = null,
    val hot: Color? = null,
) {
    /**
     * Rule 1, as `shell.html` writes it:
     * `Object.assign({}, P.params, bind.params || {})`.
     *
     * Receiver wins; [base] fills the gaps.
     */
    fun over(base: Params): Params = Params(
        color = color ?: base.color,
        periodS = periodS ?: base.periodS,
        depth = depth ?: base.depth,
        sharpness = sharpness ?: base.sharpness,
        spanDeg = spanDeg ?: base.spanDeg,
        offsetDeg = offsetDeg ?: base.offsetDeg,
        sat = sat ?: base.sat,
        light = light ?: base.light,
        from = from ?: base.from,
        to = to ?: base.to,
        tail = tail ?: base.tail,
        onColor = onColor ?: base.onColor,
        offColor = offColor ?: base.offColor,
        quiet = quiet ?: base.quiet,
        loud = loud ?: base.loud,
        gain = gain ?: base.gain,
        colors = colors ?: base.colors,
        holdS = holdS ?: base.holdS,
        blendS = blendS ?: base.blendS,
        family = family ?: base.family,
        rateHz = rateHz ?: base.rateHz,
        cold = cold ?: base.cold,
        warm = warm ?: base.warm,
        hot = hot ?: base.hot,
    )
}

/**
 * The spec's twelve patterns over eleven kinds.
 *
 * `rainbow` and `sweep` are both `hue_sweep` and differ only in their params,
 * which is exactly why a binding must carry the pattern and not just the kind:
 * with only the kind there is nothing to merge against and the two are the same
 * pattern.
 */
enum class Pattern(val id: String, val kind: PatternKind, val params: Params) {
    SOLID("solid", PatternKind.SOLID, Params(color = Palette.ICE_4)),
    RAINBOW(
        "rainbow", PatternKind.HUE_SWEEP,
        Params(periodS = 6f, sat = 0.82f, light = 0.62f, spanDeg = 360f, offsetDeg = 0f),
    ),
    CYCLE(
        "cycle", PatternKind.STEP_CYCLE,
        Params(
            colors = listOf(Palette.ICE_4, Palette.VIOLET_4, Palette.AMBER_4, Palette.VERDANT_4),
            holdS = 2f, blendS = 0.45f,
        ),
    ),
    BREATHE("breathe", PatternKind.BREATHE, Params(color = Palette.ICE_4, periodS = 4.5f, depth = 0.45f)),
    PULSE("pulse", PatternKind.PULSE, Params(color = Palette.AMBER_4, periodS = 1.8f, sharpness = 9f)),
    GRADIENT(
        "gradient", PatternKind.GRADIENT,
        Params(from = Palette.AZURE_4, to = Palette.MAGENTA_4, periodS = 7f),
    ),
    SWEEP(
        "sweep", PatternKind.HUE_SWEEP,
        Params(periodS = 5f, sat = 0.7f, light = 0.6f, spanDeg = 90f, offsetDeg = 180f),
    ),
    COMET("comet", PatternKind.COMET, Params(color = Palette.ICE_5, tail = Palette.ICE_1, periodS = 2.4f)),
    FLICKER("flicker", PatternKind.FLICKER, Params(family = "ember", rateHz = 1.2f, depth = 0.25f)),
    REACTIVE(
        "reactive", PatternKind.REACTIVE,
        Params(quiet = Palette.AZURE_3, loud = Palette.ROSE_4, gain = 1.6f),
    ),
    TEMPERATURE(
        "temperature", PatternKind.TEMPERATURE,
        Params(cold = Palette.ICE_2, warm = Palette.AMBER_4, hot = Palette.ROSE_4, periodS = 9f),
    ),
    STROBE(
        "strobe", PatternKind.STROBE,
        Params(onColor = Palette.ROSE_4, offColor = Palette.NEUTRAL_1, periodS = 0.8f),
    ),
    ;

    companion object {
        fun byId(id: String): Pattern? = entries.firstOrNull { it.id == id }
    }
}

/**
 * One state's binding: which pattern, which colour, and any param overrides.
 *
 * `color` is nullable because `hue_sweep` derives its own hue and a bound colour
 * would fight it. [merged] is the only thing the resolver should read.
 */
data class Binding(
    val pattern: Pattern,
    val color: Color? = null,
    val params: Params = Params(),
) {
    val kind: PatternKind get() = pattern.kind

    /** Rule 1 applied: this binding's params over the pattern's own. */
    val merged: Params get() = params.over(pattern.params)

    /** The bound colour, or the pattern's own. */
    val tint: Color? get() = color ?: merged.color
}

/**
 * The per-state bindings.
 *
 * These are the spec's `states[].default`, verbatim — pattern and colour only,
 * with params supplied only where the spec supplies them. Every other value now
 * comes from the pattern via rule 1, which is the point: a default that repeats
 * a pattern's own param is a value that can drift from it, and one of them did.
 */
data class Bindings(val byState: Map<FaceState, Binding>) {

    fun of(state: FaceState): Binding = byState[state] ?: DEFAULTS.byState.getValue(FaceState.IDLE)

    companion object {
        val DEFAULTS = Bindings(
            mapOf(
                FaceState.IDLE to Binding(Pattern.BREATHE, Palette.ICE_3),
                // Ember stays: it is the product's established look. Listening is
                // made unmistakable by MOTION instead — the mic envelope scales
                // the whole face. See colour_science: ember-4 against approval's
                // amber-4 is only 4.5 ΔE to a deuteranope, so hue is not carrying
                // this distinction and was never asked to.
                FaceState.LISTENING to Binding(Pattern.SOLID, Palette.EMBER_4),
                // A narrow cool sweep, hue 217-275. The full rainbow had no
                // identity — sixteen faces red, three green, one violet in one
                // gallery — and its first replacement bottomed out on cyan,
                // which is idle's hue, so a thinking face caught at that phase
                // read as idle.
                FaceState.THINKING to Binding(
                    Pattern.SWEEP, null,
                    Params(offsetDeg = 246f, spanDeg = 58f, periodS = 5f, sat = 0.72f, light = 0.62f),
                ),
                // Was gradient azure→magenta, whose own colours beat the bound
                // ice and rendered speaking pink on nineteen of twenty faces.
                FaceState.SPEAKING to Binding(
                    Pattern.REACTIVE, Palette.ICE_4,
                    Params(loud = Palette.ICE_5, gain = 1.4f),
                ),
                FaceState.APPROVAL to Binding(Pattern.PULSE, Palette.AMBER_4),
                FaceState.STANDBY to Binding(Pattern.BREATHE, Palette.NEUTRAL_3),
                // A pulse on rose that never leaves rose. Was strobe to
                // near-black, so any glance on the off phase saw nothing and
                // read as crashed.
                FaceState.ERROR to Binding(
                    Pattern.PULSE, Palette.ROSE_4,
                    Params(periodS = 1.1f, sharpness = 4f),
                ),
                FaceState.BANKED to Binding(Pattern.SOLID, Palette.NEUTRAL_4),
            ),
        )
    }
}
