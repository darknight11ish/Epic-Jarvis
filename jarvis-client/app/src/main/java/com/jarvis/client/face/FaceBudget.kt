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
    /** Stored in [com.jarvis.client.data.FaceTuning]; never renamed, so saved settings keep working. */
    val id: String,
    /** The spec's `frame_rate.animals.levels` label, the same word as the desktop's Settings. */
    val label: String,
    /** The kit's own `detail` for this tier, before the solo floor. */
    val kitDetail: Float,
    val gpu: Float,
    val post: Boolean,
    /**
     * The share of the phone's full resolution an ANIMAL is traced at before
     * it is enlarged (the spec's `phone_trace`) - see CritterFace's
     * `traceScale`. Maximum is the full resolution.
     */
    val animalTrace: Float,
    /** The level's one-line cost, word for word the desktop's (face-tuning.js QUALITIES). */
    val note: String,
) {
    LOW(
        "low", "Lower", 0.75f, 0.62f, false, 0.4f,
        "Softest picture and the least work for the graphics chip. Easiest on battery and heat.",
    ),
    MEDIUM(
        "medium", "Balanced", 1.0f, 0.80f, true, 0.5f,
        "A little softer than High, with less work for the graphics chip.",
    ),
    HIGH(
        "high", "High", 1.4f, 1.0f, true, 0.75f,
        "Sharp. A fair amount of work for the graphics chip.",
    ),
    MAX(
        "max", "Maximum", 2.0f, 1.0f, true, 1.0f,
        "The sharpest edges. The most work for the graphics chip, and the most battery and heat.",
    ),
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
 * The frame-rate targets: `auto | 30 | 60 | 90 | 120 | max` (the spec's
 * `frame_rate.targets`, default auto; 30 and 90 joined on 2026-09-28). Each
 * is drawn on whole vsyncs by [FramePacing.strideNear].
 *
 * On the web "auto" and "max" are the same. On Android they are not, and the
 * kit says so: "max" also ASKS the system for the panel's fastest mode, which
 * auto only does while the face is doing something (see
 * [FaceBudget.smoothFor] and `DisplayRate.wantsHigh`).
 */
enum class FrameRateTarget(val id: String, val label: String, val hz: Float) {
    AUTO("auto", "Auto", 0f),
    FPS_30("30", "30", 30f),
    FPS_60("60", "60", 60f),
    FPS_90("90", "90", 90f),
    FPS_120("120", "120", 120f),
    MAX("max", "Max", 0f),
    ;

    companion object {
        val DEFAULT = AUTO

        /** The Frame rate row's one-line note - word for word the desktop's (face-tuning.js FRAME_RATE_NOTE). */
        const val NOTE = "How many times a second the face is drawn. Higher is smoother but uses more battery and " +
            "graphics work. It keeps to whole steps of the screen's rate and never goes below your pick, so on a " +
            "144 Hz screen 90 draws 144 - the next rate the screen can do evenly."

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
     * panel's own rate; a picked rate is capped at what the panel can do,
     * then drawn by [strideNear].
     */
    fun strideFor(target: FrameRateTarget, panelHz: Float): Int {
        val hz = sane(panelHz)
        return strideNear(hz, if (target.hz <= 0f) hz else target.hz)
    }

    /**
     * The spec's `frame_rate.pick_rule` (owner, 2026-09-28): a whole divisor
     * of the panel, rounded UP - never slower than [wantFps]. The stride is
     * the largest whole number that still draws at least [wantFps]; a pick at
     * or above the panel's rate is every frame. So 90 draws 144 on a 144 Hz
     * panel and 120 on a 120 Hz one, 120 draws 165 on 165 Hz, 60 draws 72 on
     * 144 Hz. The 0.01 lets a panel that reports 59.94 still draw 30 as every
     * other frame. The desktop's `FacePace.strideNear` is the same sum.
     */
    fun strideNear(panelHz: Float, wantFps: Float): Int {
        val hz = sane(panelHz)
        val want = if (wantFps.isFinite() && wantFps > 0f) min(wantFps, hz) else hz
        return max(1, floor(hz / want + 0.01f).toInt())
    }

    /** The largest divisor that still draws at least [fps] a second: a rung of the animals' ladder. */
    fun strideAtLeast(panelHz: Float, fps: Int): Int = max(1, floor(sane(panelHz) / fps + 1e-3f).toInt())

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
 * For an ANIMAL ([onFrame]'s `animal`) it walks the spec's own ladder
 * instead ([AnimalPace.ladder], `frame_rate.animals.auto`): Maximum -> High,
 * then the frame rate down to 60, then Balanced, then 30, then Lower - and it
 * may climb to Maximum, but only while frames take under
 * [AnimalPace.CLIMB_TO_MAX_BELOW] of their budget, and only where the ceiling
 * allows (heat, a software renderer).
 *
 * Nothing here allocates per frame (the animal ladder is built once per panel
 * rate), and one call is a handful of float operations, so it cannot make a
 * slow phone slower.
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
    // The animal ladder's holds, one per rung (at most six).
    private val rungBlockedUntil = LongArray(8)
    private val rungHoldMs = LongArray(8)
    private var ladderHz = -1f
    private var ladderBase = -1
    private var ladder: List<AnimalPace.Rung> = emptyList()

    /** Back to the start: [to] at [extraStride] divisor steps, no holds, warm-up again. */
    fun reset(to: QualityTier = startTier, extraStride: Int = 0) {
        tier = to
        this.extraStride = max(0, extraStride)
        blockedUntil.fill(0L)
        holdMs.fill(0L)
        rungBlockedUntil.fill(0L)
        rungHoldMs.fill(0L)
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
        rungBlockedUntil.fill(0L)
        rungHoldMs.fill(0L)
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
     * @param animal the face is an animal: the spec's ladder, up to Maximum.
     * @return true when [tier] or [extraStride] changed.
     */
    fun onFrame(
        nowMs: Long,
        costMs: Float,
        budgetMs: Float,
        panelHz: Float,
        baseStride: Int = 1,
        ceiling: QualityTier = QualityTier.MAX,
        animal: Boolean = false,
    ): Boolean {
        val top = minOf(ceiling, if (animal) ANIMAL_AUTO_TOP else AUTO_TOP)
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

        if (animal) return animalStep(nowMs, since, panelHz, baseStride, top)

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

    /** The animals' ladder, rebuilt only when the panel rate or the base stride changes. */
    private fun ladderFor(panelHz: Float, baseStride: Int): List<AnimalPace.Rung> {
        if (panelHz != ladderHz || baseStride != ladderBase) {
            ladder = AnimalPace.ladder(panelHz, baseStride)
            ladderHz = panelHz
            ladderBase = baseStride
        }
        return ladder
    }

    /** One step of the animal ladder (see the class doc). */
    private fun animalStep(nowMs: Long, since: Long, panelHz: Float, baseStride: Int, top: QualityTier): Boolean {
        val rungs = ladderFor(panelHz, baseStride)
        val i = AnimalPace.rungOf(rungs, tier, baseStride + extraStride)
        val severe = avg > SEVERE_LOAD && samples >= SEVERE_MIN_SAMPLES && since >= SEVERE_COOLDOWN_MS
        if (!severe && (samples < MIN_SAMPLES || since < COOLDOWN_MS)) return false
        val j = when {
            severe -> rungs.size - 1
            avg > FramePacing.DOWNGRADE_ABOVE -> min(i + 1, rungs.size - 1)
            i > 0 && rungs[i - 1].tier <= top && nowMs >= rungBlockedUntil[i - 1] -> {
                val up = rungs[i - 1]
                val need = when {
                    up.tier == QualityTier.MAX -> AnimalPace.CLIMB_TO_MAX_BELOW
                    up.stride < rungs[i].stride -> AnimalPace.RAISE_RATE_BELOW
                    else -> AnimalPace.RAISE_QUALITY_BELOW
                }
                if (avg < need) i - 1 else i
            }
            else -> i
        }
        if (j == i) return false
        if (j > i) {
            // Every rung being left is held off for a while, and longer each time.
            for (k in i until j) {
                rungHoldMs[k] = if (rungHoldMs[k] == 0L) HOLD_FIRST_MS else min(rungHoldMs[k] * 2, HOLD_MAX_MS)
                rungBlockedUntil[k] = nowMs + rungHoldMs[k]
            }
        }
        tier = rungs[j].tier
        extraStride = max(0, rungs[j].stride - baseStride)
        changed(nowMs)
        return true
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
        /** Auto never picks above High for a face that is not an animal, as in the kit. */
        val AUTO_TOP = QualityTier.HIGH

        /** For an animal it may climb to Maximum (see [AnimalPace.CLIMB_TO_MAX_BELOW]). */
        val ANIMAL_AUTO_TOP = QualityTier.MAX

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

/**
 * The animals' own rules - the owner's "sharp animals on capable hardware"
 * (2026-09-28). Every number is the spec's `frame_rate.animals`, which the
 * desktop reads straight from the file (face-pace.js) and SpecDriftTest holds
 * these to. Pure, like the rest of this file except [FaceQuality].
 */
object AnimalPace {
    /** Auto may climb to Maximum only while frames take under this share of their budget. */
    const val CLIMB_TO_MAX_BELOW = 0.25f

    /** A frame-rate step back up needs the load under this (the kit's 0.55 x 0.6)... */
    const val RAISE_RATE_BELOW = 0.33f

    /** ...and a quality step back up under this (the kit's upgrade_below). */
    const val RAISE_QUALITY_BELOW = 0.55f

    /** Resting rates with Frame rate on Auto: 60 with headroom, 30 without. */
    const val AUTO_REST_HEADROOM = 60
    const val AUTO_REST_NO_HEADROOM = 30

    /** Headroom: the average frame under ON_BELOW of a 60 fps frame's time, lost above OFF_ABOVE. */
    const val HEADROOM_BUDGET_FPS = 60
    const val HEADROOM_ON_BELOW = 0.5f
    const val HEADROOM_OFF_ABOVE = 0.8f
    const val HEADROOM_MIN_FRAMES = 10

    /** The soft shadow is skipped when the animal's square is under this many device pixels. */
    const val NO_SHADOW_BELOW_PX = 200

    /** One step of Auto's ladder: this tier, drawing every [stride]th vsync. */
    data class Rung(val tier: QualityTier, val stride: Int)

    /**
     * The resting rate for an animal in [state], in frames a second; 0 for
     * "every frame the active stride allows". [target] is the Frame rate
     * choice (AUTO while Auto adjust or Battery saver is on); [headroom]
     * see [Headroom]; [busy] an idle happening is playing (the pose's busy()).
     * The other faces keep [Spec.fpsFor].
     */
    fun restFps(state: com.jarvis.client.FaceState, target: FrameRateTarget, headroom: Boolean, busy: Boolean): Int =
        when (state) {
            com.jarvis.client.FaceState.STANDBY, com.jarvis.client.FaceState.BANKED -> Spec.fpsFor(state)
            com.jarvis.client.FaceState.IDLE, com.jarvis.client.FaceState.APPROVAL -> when (target) {
                FrameRateTarget.AUTO -> when {
                    busy && state == com.jarvis.client.FaceState.IDLE -> 0
                    headroom -> AUTO_REST_HEADROOM
                    else -> AUTO_REST_NO_HEADROOM
                }
                FrameRateTarget.MAX -> 0
                else -> target.hz.toInt()
            }
            else -> 0
        }

    /**
     * Auto's ladder for an animal (`frame_rate.animals.auto.step_down`):
     * Maximum, High, then High at 60, Balanced at 60, Balanced at 30, Lower at
     * 30. A rung that changes nothing on this panel (60 on a 60 Hz one) is
     * left out; no rung goes under [baseStride].
     */
    fun ladder(panelHz: Float, baseStride: Int = 1): List<Rung> {
        val b = max(1, baseStride)
        val s60 = max(b, FramePacing.strideAtLeast(panelHz, 60))
        val s30 = max(b, FramePacing.strideAtLeast(panelHz, FramePacing.MIN_FPS))
        val raw = listOf(
            Rung(QualityTier.MAX, b), Rung(QualityTier.HIGH, b), Rung(QualityTier.HIGH, s60),
            Rung(QualityTier.MEDIUM, s60), Rung(QualityTier.MEDIUM, s30), Rung(QualityTier.LOW, s30),
        )
        val out = ArrayList<Rung>(raw.size)
        for (r in raw) if (out.isEmpty() || out.last() != r) out.add(r)
        return out
    }

    /** Where [tier] at [stride] sits on [rungs]: exactly, else the first rung no richer. */
    fun rungOf(rungs: List<Rung>, tier: QualityTier, stride: Int): Int {
        var i = rungs.indexOfFirst { it.tier == tier && it.stride == stride }
        if (i < 0) i = rungs.indexOfFirst { it.tier <= tier && it.stride >= stride }
        return if (i < 0) rungs.size - 1 else i
    }

    /** Whether to skip the soft shadow: the animal's square under [NO_SHADOW_BELOW_PX], or Lower. */
    fun noShadow(squarePx: Float, tier: QualityTier): Boolean =
        tier == QualityTier.LOW || squarePx < NO_SHADOW_BELOW_PX

    /** "60 fps · 4.2 ms per frame · animal resolution 810 px (75%)" - the desktop's FacePace.readout. */
    fun readout(fps: Float, ms: Float, animalPx: Int, animalOf: Int): String {
        val msText = String.format(java.util.Locale.ROOT, "%.1f", if (ms.isFinite()) ms else 0f)
        val base = "${kotlin.math.round(fps).toInt()} fps · $msText ms per frame"
        if (animalPx <= 0 || animalOf <= 0) return base
        return "$base · animal resolution $animalPx px (${kotlin.math.round(animalPx * 100f / animalOf).toInt()}%)"
    }
}

/**
 * Whether frames are cheap enough for an animal to rest at 60: the average
 * frame cost under [AnimalPace.HEADROOM_ON_BELOW] of a 60 fps frame's time,
 * lost again above [AnimalPace.HEADROOM_OFF_ABOVE] of it, and not decided
 * before [AnimalPace.HEADROOM_MIN_FRAMES] frames. Pure; not thread-safe
 * (the frame loop's own).
 */
class Headroom {
    private var avg = 0f
    private var n = 0

    var on = false
        private set

    fun frame(costMs: Float): Boolean {
        if (!costMs.isFinite() || costMs < 0f) return on
        avg = if (n == 0) costMs else avg * 0.9f + costMs * 0.1f
        n++
        val budget = 1000f / AnimalPace.HEADROOM_BUDGET_FPS
        if (n >= AnimalPace.HEADROOM_MIN_FRAMES) {
            on = if (on) avg <= AnimalPace.HEADROOM_OFF_ABOVE * budget else avg < AnimalPace.HEADROOM_ON_BELOW * budget
        }
        return on
    }

    fun reset() {
        avg = 0f
        n = 0
        on = false
    }
}

/**
 * How an animal rests right now, for [FaceHost.advance]: the Frame rate
 * choice that applies and whether there is headroom. Replaced, never
 * changed, so the frame loop can read it without a lock.
 */
data class RestPace(val target: FrameRateTarget, val headroom: Boolean) {
    companion object {
        val DEFAULT = RestPace(FrameRateTarget.AUTO, false)
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
     *  - Battery saver, or a chosen 30 or 60: never ask.
     *  - Max: ask whenever the face is busy, with no time limit (the kit: "max
     *    also REQUESTS the highest supported mode").
     *  - Auto adjust, Auto, 120: the existing rule.
     */
    fun smoothFor(t: FaceTuning, phoneSaver: Boolean): SmoothMotion = when {
        saverOn(t, phoneSaver) -> SmoothMotion.OFF
        t.autoAdjust -> SmoothMotion.AUTO
        // 30 and 60 never need more than a 60 Hz panel.
        t.frameRate == FrameRateTarget.FPS_60 || t.frameRate == FrameRateTarget.FPS_30 -> SmoothMotion.OFF
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

    /** The face on screen is an animal (see [onFaceChanged]). */
    @Volatile
    var animal = false
        private set

    // Frames cheap enough for an animal to rest at 60 (frame loop only).
    private val headroom = Headroom()

    /** How an animal rests right now (see [RestPace]); read by the frame loop. */
    @Volatile
    var pace: RestPace = RestPace.DEFAULT
        private set

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

    /**
     * A different face is on screen: its first frames are not its real cost.
     * An animal may be taken to Maximum by Auto; any other face goes back to
     * High at most on its next frame (the governor's `top`).
     */
    fun onFaceChanged(isAnimal: Boolean = false) {
        animal = isAnimal
        governor.restartWarmup()
        headroom.reset()
        pace = restPaceFor(current)
    }

    /**
     * One drawn frame, for the governor. Does nothing unless Auto adjust is in
     * charge.
     *
     * @param budgetMs the frame budget measured against the display's real
     *   vsync ([FramePacing.vsyncPeriodMs] times the stride).
     */
    fun onFrame(nowMs: Long, costMs: Float, budgetMs: Float) {
        val c = current
        // Headroom counts every drawn frame, governed or not: Frame rate on
        // Auto rests an animal at 60 or 30 by it either way.
        val had = headroom.on
        if (headroom.frame(costMs) != had) pace = restPaceFor(c)
        if (!c.governed) return
        val changed = governor.onFrame(
            nowMs = nowMs,
            costMs = costMs,
            budgetMs = budgetMs,
            panelHz = c.panelHz,
            baseStride = FramePacing.strideFor(FrameRateTarget.AUTO, c.panelHz),
            ceiling = FaceBudget.autoCeiling(heat, softwareGpu),
            animal = animal,
        )
        if (changed) recompute()
    }

    /** The Frame rate choice that applies to an animal's rest: Auto whenever Auto adjust or Battery saver decides. */
    private fun restPaceFor(b: ResolvedBudget): RestPace {
        val target = if (b.governed || b.saver) FrameRateTarget.AUTO else tuning.frameRate
        val p = pace
        return if (p.target == target && p.headroom == headroom.on) p else RestPace(target, headroom.on)
    }

    // The Face editor's readout (fps, ms per frame, the animal's resolution).
    @Volatile private var tracePx = 0
    @Volatile private var traceOf = 0

    /** What an animal was last traced at, and the size it fills (CritterFace, main thread). */
    fun noteTrace(px: Int, of: Int) {
        tracePx = px
        traceOf = of
    }

    private val _stats = MutableStateFlow("")

    /** "60 fps · 4.2 ms per frame · animal resolution 810 px (75%)", about twice a second while a face draws. */
    val stats: StateFlow<String> = _stats.asStateFlow()

    /** The frame loop's measurement, twice a second: frames drawn a second and the average ms each. */
    fun publishStats(fps: Float, msPerFrame: Float) {
        _stats.value = if (animal) {
            AnimalPace.readout(fps, msPerFrame, tracePx, traceOf)
        } else {
            AnimalPace.readout(fps, msPerFrame, 0, 0)
        }
    }

    private fun recompute() {
        val r = FaceBudget.resolve(
            tuning, phoneSaver, heat, governor.tier, governor.extraStride, panelHz, softwareGpu,
        )
        pace = restPaceFor(r)
        if (r == current) return
        current = r
        _live.value = r
    }
}
