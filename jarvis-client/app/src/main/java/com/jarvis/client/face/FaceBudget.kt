package com.jarvis.client.face

import com.jarvis.client.data.FaceTuning
import com.jarvis.client.platform.SmoothMotion
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * How much work the face is allowed to do: the reactor kit's quality tiers,
 * its frame-rate targets and divisor rule, and its AUTO governor, ported for
 * the phone. Everything in this file except [FaceQuality] is pure - time and
 * frame costs are passed in - so it is unit-tested on the JVM
 * (`FaceBudgetTest`).
 *
 * The kit (the Jarvis Reactor Kit artifact) is the reference for every number
 * here. Where the phone differs, the difference is written next to it.
 */

/**
 * The kit's `SOLO.detail = Math.max(1.9, Q.detail)`: its single-face view
 * never draws below a detail of 1.9, and the kit calls that view "what Jarvis
 * will really look like". Top-level rather than in [QualityTier]'s companion,
 * because enum entries are built before their companion object is.
 */
const val SOLO_DETAIL_FLOOR = 1.9f

/**
 * The kit's `TIERS` (artifact, `const TIERS`):
 *
 * | tier   | ss  | detail | gpu  | post  |
 * |--------|-----|--------|------|-------|
 * | low    | 1   | 0.75   | 0.62 | false |
 * | medium | 1.5 | 1.0    | 0.80 | true  |
 * | high   | 2   | 1.4    | 1.00 | true  |
 * | max    | 2   | 2.0    | 1.00 | true  |
 *
 * What the phone uses from each:
 *  - [detail] - how much geometry a face builds (`KitParity`/`CoreKit`/`GL`
 *    all read it through [FaceQuality.detail]). High and Max apply the kit's
 *    solo floor, `max(1.9, detail)`, because the phone's face IS the kit's solo
 *    view: High is 1.9 - exactly what the phone drew before this setting
 *    existed - and Max is 2.0. Low and Medium deliberately do NOT get the
 *    floor: with it they would be 1.9 as well and save nothing, and the whole
 *    point of stepping down on a phone is to do less work. They use the kit's
 *    own tier numbers, 0.75 and 1.0.
 *  - [gpu] - the share of device pixels the two mesh faces size their mesh
 *    for (the kit's `GPUPX = devpx * Q.gpu`).
 *  - [post] - whether the glow is drawn at all. Off at Low, as in the kit: "a
 *    phone that has already been pushed to the low tier has no budget for a
 *    halo, however cheap".
 *  - `ss` (supersample) has no phone equivalent and is not carried: the kit
 *    draws into a canvas it sizes itself, while Compose already draws at the
 *    screen's own pixel density.
 */
enum class QualityTier(
    val id: String,
    val label: String,
    /** The kit's own `detail` for this tier, before the solo floor. */
    val kitDetail: Float,
    val gpu: Float,
    val post: Boolean,
) {
    LOW("low", "Low", 0.75f, 0.62f, false),
    MEDIUM("medium", "Medium", 1.0f, 0.80f, true),
    HIGH("high", "High", 1.4f, 1.0f, true),
    MAX("max", "Max", 2.0f, 1.0f, true),
    ;

    /** What the phone's faces multiply their element counts by. See the class doc. */
    val detail: Float = if (ordinal >= 2) max(SOLO_DETAIL_FLOOR, kitDetail) else kitDetail

    fun down(): QualityTier = entries[(ordinal - 1).coerceAtLeast(0)]

    fun up(): QualityTier = entries[(ordinal + 1).coerceAtMost(entries.size - 1)]

    companion object {
        /** High: what the phone drew before there was a choice. */
        val DEFAULT = HIGH

        /** Anything unknown or missing is the default, never a crash. */
        fun byId(id: String?): QualityTier = entries.firstOrNull { it.id == id } ?: DEFAULT
    }
}

/**
 * The kit's frame-rate targets: `auto | 60 | 120 | max` (`renderer.frame_rate`
 * in its spec, default auto).
 *
 * On the web "auto" and "max" are the same. On Android they are not, and the
 * kit says so: "max" also ASKS the system for the panel's fastest mode, which
 * auto only does while the face is doing something (see
 * [FaceBudget.smoothFor] and `DisplayRate.wantsHigh`).
 */
enum class FrameRateTarget(val id: String, val label: String, val hz: Float) {
    AUTO("auto", "Auto", 0f),
    FPS_60("60", "60", 60f),
    FPS_120("120", "120", 120f),
    MAX("max", "Max", 0f),
    ;

    companion object {
        val DEFAULT = AUTO

        fun byId(id: String?): FrameRateTarget = entries.firstOrNull { it.id == id } ?: DEFAULT
    }
}

/**
 * The kit's DISPLAY CLOCK rules.
 *
 * PACING BY DIVISOR: "If a face cannot hold the full rate, drop to a whole
 * divisor (120 -> 60 -> 40 -> 30) rather than chasing an uneven number. Every
 * frame then lands on a real vsync." [strideFor] is the kit's `applyTarget`.
 *
 * BUDGET: "Thresholds are fractions of the measured budget, never fixed
 * milliseconds. At 120Hz the budget is 8.3ms, so a governor tuned to 60Hz
 * thinks a 20ms frame is healthy while the display is running at half rate."
 * [budgetMs] is `1000 / (hz / stride)`; the thresholds are [DOWNGRADE_ABOVE]
 * and [UPGRADE_BELOW] of it.
 */
object FramePacing {
    /** The kit's `pacing.min_fps`: the governor never strides below this. */
    const val MIN_FPS = 30

    /** The kit's `budget.downgrade_above`. */
    const val DOWNGRADE_ABOVE = 1.45f

    /** The kit's `budget.upgrade_below`. */
    const val UPGRADE_BELOW = 0.55f

    /**
     * A drawn frame that arrives later than this share of the expected
     * interval is counted as having cost the whole interval - see [frameCostMs].
     */
    const val LATE_FACTOR = 1.25f

    /** A gap longer than this is a pause (a GC, the app in the background), not a frame. */
    const val MAX_INTERVAL_MS = 1_500f

    private val COMMON_HZ = floatArrayOf(60f, 75f, 90f, 100f, 120f, 144f, 165f, 240f)

    /** The panel rate, or 60 if what was read is missing or nonsense. */
    fun sane(hz: Float): Float = if (hz.isFinite() && hz >= 20f && hz <= 1000f) hz else 60f

    /** JavaScript's Math.round (half up), which is what the kit's divisions use. */
    private fun jsRound(v: Float): Float = floor(v + 0.5f)

    /**
     * The kit's `snapHz`: a noisy 118.4 reported as 120, because every budget
     * derived from a slightly wrong rate is slightly wrong.
     */
    fun snapHz(raw: Float): Float {
        if (!raw.isFinite() || raw < 20f) return 60f
        var best = COMMON_HZ[0]
        var d = Float.MAX_VALUE
        for (c in COMMON_HZ) {
            val dd = abs(c - raw)
            if (dd < d) {
                d = dd
                best = c
            }
        }
        return if (d <= max(6f, raw * 0.08f)) best else jsRound(raw)
    }

    /**
     * The kit's `applyTarget`: draw every Nth vsync. Auto and Max take the
     * panel's own rate; 60 and 120 are capped at what the panel can do, then
     * rounded to a whole divisor.
     */
    fun strideFor(target: FrameRateTarget, panelHz: Float): Int {
        val hz = sane(panelHz)
        val want = if (target.hz <= 0f) hz else min(target.hz, hz)
        return max(1, jsRound(hz / want).toInt())
    }

    /** The smallest whole divisor that keeps the face at or under [maxFps]. */
    fun strideAtMost(panelHz: Float, maxFps: Int): Int {
        val hz = sane(panelHz)
        return max(1, ceil(hz / maxFps - 1e-3f).toInt())
    }

    /** `budget_ms = 1000 / (hz / stride)`: the time one displayed frame has. */
    fun budgetMs(panelHz: Float, stride: Int): Float = 1000f / (sane(panelHz) / max(1, stride))

    /**
     * The time between two vsyncs, in milliseconds: the platform's reported
     * rate, unless the fastest gap actually seen between frame callbacks
     * lately says the panel is running slower than reported - many phones
     * drop to 60 at low brightness or when warm while still reporting 120 -
     * in which case that. Never more than twice the reported period: a face
     * that is itself slow makes every gap long, and must not be able to talk
     * the budget up to match its own slowness (the kit: "a slow scene must
     * not be able to talk the clock down").
     *
     * @param fastestSeenMs the shortest vsync gap seen lately, or anything
     *   non-finite, zero or huge for "not measured yet".
     */
    fun vsyncPeriodMs(reportedHz: Float, fastestSeenMs: Float): Float {
        val reported = 1000f / sane(reportedHz)
        if (!fastestSeenMs.isFinite() || fastestSeenMs <= 0f || fastestSeenMs > 1_000f) return reported
        return fastestSeenMs.coerceIn(reported, reported * 2f)
    }

    /** The kit's `CLOCK.hz / (CLOCK.stride + 1) >= 30`. */
    fun canStrideFurther(panelHz: Float, stride: Int): Boolean = sane(panelHz) / (stride + 1) >= MIN_FPS

    /**
     * What a frame cost, for the governor, in milliseconds.
     *
     * The kit times its own draw with `performance.now()`. The phone times the
     * face's draw too ([drawMs]) - but on Android a lot of the real cost is not
     * in that call: the GPU rasterises later, on another thread, and a slow GPU
     * shows up only as frames arriving late. So when a drawn frame arrives
     * noticeably later than it was due ([intervalMs] against
     * [expectedIntervalMs]), the lateness counts as cost too. Without this a
     * phone whose GPU can manage three frames a second, but whose CPU records
     * the drawing quickly, would look healthy to the governor forever.
     *
     * [expectedIntervalMs] is what the loop meant to wait - the budget while
     * drawing every (Nth) vsync, 1000/30 while idling at 30 - and the part of
     * the wait that was deliberate is taken off before comparing with
     * [budgetMs].
     *
     * Two float comparisons and a subtraction: cheap enough for every frame.
     */
    fun frameCostMs(drawMs: Float, intervalMs: Float, expectedIntervalMs: Float, budgetMs: Float): Float {
        val draw = if (drawMs.isFinite()) max(0f, drawMs) else 0f
        if (!intervalMs.isFinite() || intervalMs <= 0f || intervalMs > MAX_INTERVAL_MS) return draw
        if (!expectedIntervalMs.isFinite() || expectedIntervalMs <= 0f) return draw
        if (intervalMs <= expectedIntervalMs * LATE_FACTOR) return draw
        val deliberate = max(0f, expectedIntervalMs - budgetMs)
        return max(draw, intervalMs - deliberate)
    }
}

/**
 * The kit's AUTO governor (its `budget()` function), made pure.
 *
 * Measured against the display's real frame budget, never fixed milliseconds.
 * It keeps a smoothed load - frame cost over budget - and:
 *  - above [FramePacing.DOWNGRADE_ABOVE]: steps quality down a tier; at Low it
 *    drops to the next whole divisor of the refresh rate instead (never below
 *    30 fps), as the kit does - "a locked 60 on a 120Hz panel looks better than
 *    a soft, uneven 75";
 *  - below [FramePacing.UPGRADE_BELOW]: steps quality back up, but only as far
 *    as High (the kit's `i < 2`: Auto never picks Max for you);
 *  - well below that, with nothing left to raise: undoes one divisor step;
 *  - at most one change every [COOLDOWN_MS], the kit's two seconds.
 *
 * What the phone adds, because nobody has timed the new faces on a slow phone
 * and the CI emulator (software graphics) froze on them:
 *  - SEVERE: a load over [SEVERE_LOAD] jumps straight to Low after two frames,
 *    with a shorter cooldown, rather than walking down one tier every two
 *    seconds. A phone managing three frames a second would otherwise spend
 *    most of a minute getting there.
 *  - A warm-up: the first [WARMUP_MS] after start (or a face change) are not
 *    counted, because the first frames of a face include one-off work - a
 *    shader compiling, a point cloud being built - that is not its real cost.
 *  - The average restarts after every change, so the next decision is made
 *    on frames drawn at the NEW setting.
 *  - Hysteresis against flapping: after stepping down out of a tier, stepping
 *    back up into it is held off for [HOLD_FIRST_MS], doubling each time it
 *    happens again (up to [HOLD_MAX_MS]). A phone that can almost manage High
 *    tries it again now and then instead of bouncing every two seconds.
 *
 * Nothing here allocates, and one call is a handful of float operations, so
 * it cannot make a slow phone slower.
 */
class FrameGovernor(private val startTier: QualityTier = QualityTier.DEFAULT) {

    var tier: QualityTier = startTier
        private set

    /** Divisor steps added on top of the target's own stride (Auto only). */
    var extraStride: Int = 0
        private set

    private var avg = 0f
    private var samples = 0
    private var startedAtMs = UNSET
    private var lastChangeMs = UNSET
    private val blockedUntil = LongArray(QualityTier.entries.size)
    private val holdMs = LongArray(QualityTier.entries.size)

    /** Back to the start: [to] at [extraStride] divisor steps, no holds, warm-up again. */
    fun reset(to: QualityTier = startTier, extraStride: Int = 0) {
        tier = to
        this.extraStride = max(0, extraStride)
        blockedUntil.fill(0L)
        holdMs.fill(0L)
        lastChangeMs = UNSET
        restartWarmup()
    }

    /**
     * A different face: keep the tier, forget the average and the holds (a
     * different face costs something different), and warm up again.
     */
    fun restartWarmup() {
        avg = 0f
        samples = 0
        startedAtMs = UNSET
        blockedUntil.fill(0L)
        holdMs.fill(0L)
    }

    /**
     * One drawn frame.
     *
     * @param nowMs a monotonic clock, in milliseconds.
     * @param costMs what the frame cost - [FramePacing.frameCostMs].
     * @param budgetMs the display budget - [FramePacing.budgetMs].
     * @param panelHz the panel's refresh rate, for the divisor rule.
     * @param baseStride the target's own stride, before the governor's.
     * @param ceiling the highest tier allowed right now (heat lowers it).
     * @return true when [tier] or [extraStride] changed.
     */
    fun onFrame(
        nowMs: Long,
        costMs: Float,
        budgetMs: Float,
        panelHz: Float,
        baseStride: Int = 1,
        ceiling: QualityTier = QualityTier.MAX,
    ): Boolean {
        val top = minOf(ceiling, AUTO_TOP)
        if (tier > top) {
            tier = top
            changed(nowMs)
            return true
        }
        if (startedAtMs == UNSET) {
            startedAtMs = nowMs
            // The start counts as a change, so the first ordinary step waits
            // out the same cooldown as every later one.
            if (lastChangeMs == UNSET) lastChangeMs = nowMs
        }
        if (nowMs - startedAtMs < WARMUP_MS) return false
        if (!costMs.isFinite() || !budgetMs.isFinite() || budgetMs <= 0f) return false

        val load = (costMs / budgetMs).coerceIn(0f, MAX_LOAD)
        avg = if (samples == 0) load else avg * (1f - EMA) + load * EMA
        samples++
        val since = if (lastChangeMs == UNSET) Long.MAX_VALUE else nowMs - lastChangeMs

        if (avg > SEVERE_LOAD && samples >= SEVERE_MIN_SAMPLES && since >= SEVERE_COOLDOWN_MS) {
            if (tier != QualityTier.LOW) {
                stepDownTo(QualityTier.LOW, nowMs)
                return true
            }
            if (FramePacing.canStrideFurther(panelHz, baseStride + extraStride)) {
                extraStride++
                changed(nowMs)
                return true
            }
        }

        if (samples < MIN_SAMPLES || since < COOLDOWN_MS) return false

        if (avg > FramePacing.DOWNGRADE_ABOVE) {
            if (tier == QualityTier.LOW) {
                if (FramePacing.canStrideFurther(panelHz, baseStride + extraStride)) {
                    extraStride++
                    changed(nowMs)
                    return true
                }
                return false
            }
            stepDownTo(tier.down(), nowMs)
            return true
        }
        if (avg < FramePacing.UPGRADE_BELOW && tier < top && nowMs >= blockedUntil[tier.up().ordinal]) {
            tier = tier.up()
            changed(nowMs)
            return true
        }
        if (avg < FramePacing.UPGRADE_BELOW * 0.6f && extraStride > 0) {
            extraStride--
            changed(nowMs)
            return true
        }
        return false
    }

    private fun stepDownTo(to: QualityTier, nowMs: Long) {
        // Every tier being left is held off for a while, and longer each time.
        for (i in to.ordinal + 1..tier.ordinal) {
            holdMs[i] = if (holdMs[i] == 0L) HOLD_FIRST_MS else min(holdMs[i] * 2, HOLD_MAX_MS)
            blockedUntil[i] = nowMs + holdMs[i]
        }
        tier = to
        changed(nowMs)
    }

    private fun changed(nowMs: Long) {
        lastChangeMs = nowMs
        avg = 0f
        samples = 0
    }

    companion object {
        /** Auto never picks above High, as in the kit. */
        val AUTO_TOP = QualityTier.HIGH

        /** The kit's `costAvg * .9 + cost * .1`. */
        const val EMA = 0.1f
        const val COOLDOWN_MS = 2_000L
        const val MIN_SAMPLES = 5
        const val WARMUP_MS = 1_000L
        const val SEVERE_LOAD = 4f
        const val SEVERE_MIN_SAMPLES = 2
        const val SEVERE_COOLDOWN_MS = 750L
        const val HOLD_FIRST_MS = 10_000L
        const val HOLD_MAX_MS = 120_000L
        private const val MAX_LOAD = 100f
        private const val UNSET = Long.MIN_VALUE
    }
}

/** Everything the face is running with right now, after every rule has had its say. */
data class ResolvedBudget(
    val tier: QualityTier,
    /** Draw every [stride]th vsync while the face draws at the display's rate. */
    val stride: Int,
    val panelHz: Float,
    /** Glow on or off (the kit's `post`). */
    val post: Boolean,
    /** Calm motion forced on (battery saver). */
    val calm: Boolean,
    /** The face's speed multiplier. Never above 1 while [calm]. */
    val speed: Float,
    /** Auto adjust is choosing [tier] and [stride]. */
    val governed: Boolean,
    /** Battery saver is in force. */
    val saver: Boolean,
    /** ...and only because the phone's own Battery Saver is on. */
    val saverFromPhone: Boolean,
) {
    val budgetMs: Float get() = FramePacing.budgetMs(panelHz, stride)

    /** Whole frames a second, as the owner would read it. */
    val fps: Int get() = kotlin.math.round(FramePacing.sane(panelHz) / stride).toInt()
}

/**
 * Who wins. In order:
 *  1. Battery saver - the owner's switch, or Android's own Battery Saver. Low
 *     detail, no glow, at most [SAVER_MAX_FPS], calm motion. Overrides
 *     everything else.
 *  2. Auto adjust - the governor's tier and divisor, under a ceiling that heat
 *     lowers ([ceilingFor]), and that a software renderer lowers too
 *     ([SOFTWARE_AUTO_TOP]).
 *  3. The owner's own Quality and Frame rate. An explicit choice is not
 *     overridden, as in the kit ("you picked a tier; it stays picked") - not
 *     even by heat; Android throttles a hot phone on its own anyway.
 */
object FaceBudget {
    const val SAVER_MAX_FPS = 30

    /** Where Auto starts, and the most frames a second, on a software renderer. */
    const val SOFTWARE_START_MAX_FPS = 30

    /**
     * The highest tier Auto may climb to on a software renderer (see
     * [isSoftwareRenderer]). It starts at Low and may step up if its frames
     * measure fast - but never back to High's 1.9, the detail the phone CI's
     * software-graphics emulator crashed or froze at within seconds, in four
     * runs in a row. A real phone never has a software renderer, so this only
     * ever applies to emulators.
     *
     * LOW, not Medium: whether Medium (detail 1.0) also takes the emulator
     * down is unknown, and the phone CI publishes nothing until it passes.
     * Raise it only with a green run that shows the emulator surviving it.
     */
    val SOFTWARE_AUTO_TOP = QualityTier.LOW

    fun saverOn(t: FaceTuning, phoneSaver: Boolean): Boolean = t.batterySaver || phoneSaver

    /**
     * The highest tier Auto may use at a heat level: 0 cool, 1 warm (Android's
     * THERMAL_STATUS_MODERATE), 2 hot (SEVERE or worse).
     */
    fun ceilingFor(heat: Int): QualityTier = when {
        heat >= 2 -> QualityTier.LOW
        heat == 1 -> QualityTier.MEDIUM
        else -> QualityTier.MAX
    }

    /** [ceilingFor], lowered further on a software renderer. */
    fun autoCeiling(heat: Int, softwareGpu: Boolean): QualityTier =
        if (softwareGpu) minOf(ceilingFor(heat), SOFTWARE_AUTO_TOP) else ceilingFor(heat)

    /**
     * Whether an OpenGL ES `GL_RENDERER` string names a renderer that draws on
     * the CPU: SwiftShader (what the phone CI's emulator uses), Mesa's
     * llvmpipe and softpipe, and the emulator's own translator, whatever it
     * wraps. Case-insensitive. Null or blank - the query failed - is NOT
     * software: fail safe towards "a normal GPU", and let the governor do its
     * job.
     */
    fun isSoftwareRenderer(renderer: String?): Boolean {
        if (renderer.isNullOrBlank()) return false
        val r = renderer.lowercase()
        return SOFTWARE_RENDERERS.any { it in r }
    }

    private val SOFTWARE_RENDERERS = listOf(
        "swiftshader",
        "llvmpipe",
        "softpipe",
        "android emulator opengl es translator",
    )

    fun resolve(
        t: FaceTuning,
        phoneSaver: Boolean,
        heat: Int,
        governedTier: QualityTier,
        governedExtraStride: Int,
        panelHz: Float,
        softwareGpu: Boolean = false,
    ): ResolvedBudget {
        val hz = FramePacing.sane(panelHz)
        return when {
            saverOn(t, phoneSaver) -> ResolvedBudget(
                tier = QualityTier.LOW,
                stride = FramePacing.strideAtMost(hz, SAVER_MAX_FPS),
                panelHz = hz,
                post = false,
                calm = true,
                speed = min(t.speed, 1f),
                governed = false,
                saver = true,
                saverFromPhone = phoneSaver && !t.batterySaver,
            )
            t.autoAdjust -> {
                val tier = minOf(governedTier, autoCeiling(heat, softwareGpu))
                ResolvedBudget(
                    tier = tier,
                    stride = FramePacing.strideFor(FrameRateTarget.AUTO, hz) + max(0, governedExtraStride),
                    panelHz = hz,
                    post = tier.post,
                    calm = false,
                    speed = t.speed,
                    governed = true,
                    saver = false,
                    saverFromPhone = false,
                )
            }
            else -> ResolvedBudget(
                tier = t.quality,
                stride = FramePacing.strideFor(t.frameRate, hz),
                panelHz = hz,
                post = t.quality.post,
                calm = false,
                speed = t.speed,
                governed = false,
                saver = false,
                saverFromPhone = false,
            )
        }
    }

    /**
     * Whether to ask the panel for its fastest mode - carried to
     * `DisplayRate.wantsHigh`, which still says no in battery saver, when hot,
     * with the face off screen and in the resting states.
     *  - Battery saver, or a chosen 60: never ask.
     *  - Max: ask whenever the face is busy, with no time limit (the kit: "max
     *    also REQUESTS the highest supported mode").
     *  - Auto adjust, Auto, 120: the existing rule.
     */
    fun smoothFor(t: FaceTuning, phoneSaver: Boolean): SmoothMotion = when {
        saverOn(t, phoneSaver) -> SmoothMotion.OFF
        t.autoAdjust -> SmoothMotion.AUTO
        t.frameRate == FrameRateTarget.FPS_60 -> SmoothMotion.OFF
        t.frameRate == FrameRateTarget.MAX -> SmoothMotion.ALWAYS
        else -> SmoothMotion.AUTO
    }
}

/**
 * The one live budget the whole app's face runs with - the kit has one
 * governor per page, and the phone shows one live face at a time.
 *
 * Written on the main thread only (MainActivity's settings, FaceView's frame
 * loop, the GPU probe's result). Read on the main thread by the canvas faces
 * and on the GL thread by the two mesh faces, hence @Volatile on what they
 * read.
 */
object FaceQuality {

    private val governor = FrameGovernor()

    @Volatile private var tuning = FaceTuning()
    @Volatile private var phoneSaver = false
    @Volatile private var heat = 0
    @Volatile private var panelHz = 60f
    private var probed = false

    /** The GPU probe found a software renderer (an emulator). See [onGpuProbed]. */
    @Volatile
    var softwareGpu = false
        private set

    @Volatile
    var current: ResolvedBudget = FaceBudget.resolve(tuning, phoneSaver, heat, governor.tier, governor.extraStride, panelHz)
        private set

    private val _live = MutableStateFlow(current)

    /** [current], for the Appearance screen to show what Auto picked. Changes rarely. */
    val live: StateFlow<ResolvedBudget> = _live.asStateFlow()

    /** The detail multiplier every face builds its geometry with. */
    val detail: Float get() = current.tier.detail

    /** The share of device pixels the mesh faces size their mesh for. */
    val gpu: Float get() = current.tier.gpu

    /** The owner's settings, the phone's Battery Saver, and its heat level (see [FaceBudget.ceilingFor]). */
    fun configure(tuning: FaceTuning, phoneSaver: Boolean, heat: Int) {
        this.tuning = tuning
        this.phoneSaver = phoneSaver
        this.heat = heat
        recompute()
    }

    /** The panel's refresh rate as the platform reports it. Snapped to a real rate. */
    fun setPanelHz(hz: Float) {
        val snapped = FramePacing.snapHz(hz)
        if (snapped == panelHz) return
        panelHz = snapped
        recompute()
    }

    /**
     * What the one-time GPU check found (`GpuProbe`). Acted on once per
     * process; later calls are ignored.
     *
     * A software renderer puts Auto adjust at Low and at most
     * [FaceBudget.SOFTWARE_START_MAX_FPS] before the first frame is drawn -
     * the governor alone would be too late, because the CI emulator died
     * within six to twelve seconds of its first face. Auto may still climb
     * from there if frames measure fast, as far as
     * [FaceBudget.SOFTWARE_AUTO_TOP].
     */
    fun onGpuProbed(software: Boolean) {
        if (probed) return
        probed = true
        softwareGpu = software
        if (software) {
            val base = FramePacing.strideFor(FrameRateTarget.AUTO, panelHz)
            val capped = FramePacing.strideAtMost(panelHz, FaceBudget.SOFTWARE_START_MAX_FPS)
            governor.reset(QualityTier.LOW, extraStride = capped - base)
        }
        recompute()
    }

    /** A different face is on screen: its first frames are not its real cost. */
    fun onFaceChanged() = governor.restartWarmup()

    /**
     * One drawn frame, for the governor. Does nothing unless Auto adjust is in
     * charge.
     *
     * @param budgetMs the frame budget measured against the display's real
     *   vsync ([FramePacing.vsyncPeriodMs] times the stride).
     */
    fun onFrame(nowMs: Long, costMs: Float, budgetMs: Float) {
        val c = current
        if (!c.governed) return
        val changed = governor.onFrame(
            nowMs = nowMs,
            costMs = costMs,
            budgetMs = budgetMs,
            panelHz = c.panelHz,
            baseStride = FramePacing.strideFor(FrameRateTarget.AUTO, c.panelHz),
            ceiling = FaceBudget.autoCeiling(heat, softwareGpu),
        )
        if (changed) recompute()
    }

    private fun recompute() {
        val r = FaceBudget.resolve(
            tuning, phoneSaver, heat, governor.tier, governor.extraStride, panelHz, softwareGpu,
        )
        if (r == current) return
        current = r
        _live.value = r
    }
}
