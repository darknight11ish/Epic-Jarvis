package com.jarvis.client.face

import androidx.compose.ui.graphics.Color
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/** The two colours a pattern produces: the hot accent and the structural one. */
data class Swatch(val a: Color, val b: Color)

/** Brighten (k>0) or darken (k<0), matching the shell's `lift()`. */
fun lift(c: Color, k: Float): Color {
    fun f(v: Float) = if (k >= 0f) v + (1f - v) * k else v * (1f + k)
    return Color(
        red = f(c.red).coerceIn(0f, 1f),
        green = f(c.green).coerceIn(0f, 1f),
        blue = f(c.blue).coerceIn(0f, 1f),
        alpha = c.alpha,
    )
}

fun mix(a: Color, b: Color, k: Float): Color {
    val t = k.coerceIn(0f, 1f)
    return Color(
        red = a.red + (b.red - a.red) * t,
        green = a.green + (b.green - a.green) * t,
        blue = a.blue + (b.blue - a.blue) * t,
        alpha = a.alpha + (b.alpha - a.alpha) * t,
    )
}

private fun hsl(hDeg: Float, s: Float, l: Float): Color {
    val h = ((hDeg % 360f) + 360f) % 360f / 360f
    fun hue(p: Float, q: Float, tIn: Float): Float {
        var t = tIn
        if (t < 0) t += 1f
        if (t > 1) t -= 1f
        return when {
            t < 1f / 6f -> p + (q - p) * 6f * t
            t < 1f / 2f -> q
            t < 2f / 3f -> p + (q - p) * (2f / 3f - t) * 6f
            else -> p
        }
    }
    if (s == 0f) return Color(l, l, l)
    val q = if (l < 0.5f) l * (1f + s) else l + s - l * s
    val p = 2f * l - q
    return Color(hue(p, q, h + 1f / 3f), hue(p, q, h), hue(p, q, h - 1f / 3f))
}

/** Relative luminance, for the photosensitivity governor. */
fun relLuma(c: Color): Float {
    fun ch(v: Float) = if (v <= 0.03928f) v / 12.92f else ((v + 0.055f) / 1.055f).pow(2.4f)
    return 0.2126f * ch(c.red) + 0.7152f * ch(c.green) + 0.0722f * ch(c.blue)
}

/**
 * The photosensitive-seizure governor.
 *
 * **One of these per surface.** A single page-wide window fed by every surface
 * in turn saw twenty faces with twenty clocks as one face flashing between
 * twenty colours: it spent its budget on those cross-surface transitions and
 * then held one face's colour on another. A client that draws several reactors
 * — a face picker — must give each its own.
 */
class FlashGovernor {
    private val window = ArrayDeque<Float>()
    private var lastY: Float? = null
    private var safe: Swatch? = null
    private var dir = 0

    fun reset() {
        window.clear(); lastY = null; safe = null; dir = 0
    }

    fun govern(out: Swatch, t: Float): Swatch {
        // Pruned on EVERY call, not only when a transition is detected. Pruning
        // inside the transition branch leaves stale entries whenever the colour
        // sits still for a while, so the budget appears spent when it is not.
        while (window.isNotEmpty() && t - window.first() > 1f) window.removeFirst()

        val y = relLuma(out.a)
        val prev = lastY
        if (prev == null) {
            lastY = y; safe = out; return out
        }
        val d = y - prev
        if (abs(d) < Spec.FLASH_MIN_LUMA_DELTA) {
            lastY = y; safe = out; return out
        }
        val newDir = if (d > 0) 1 else -1
        val opposing = newDir != dir
        if (opposing && window.size >= Spec.FLASH_MAX_TRANSITIONS_PER_S) {
            // Over budget. Hold the colour that was ALREADY on screen — not the
            // one being refused, which was the whole point. Holding is the right
            // failure: going dark is itself a transition and going bright is the
            // thing being prevented, so freezing is the only move that adds no
            // luminance change at all.
            return safe ?: out
        }
        if (opposing) {
            window.addLast(t); dir = newDir
        }
        lastY = y; safe = out
        return out
    }
}

/**
 * The pattern engine — the thing that makes a face ignorant of which state
 * Jarvis is in. Port this before any face.
 *
 * Reads [Binding.merged], never the binding's raw params: that merge IS rule 1,
 * and reading around it is how a bound `sweep` becomes a full rainbow.
 *
 * @param amp the smoothed drive: the microphone while listening, Jarvis's own
 *   voice while speaking. Never the raw level; the shell owns the envelope.
 */
fun resolveRaw(bind: Binding, t: Float, amp: Float): Swatch {
    val q = bind.merged
    val periodS = (q.periodS ?: 4.5f).coerceAtLeast(0.05f)

    return when (bind.kind) {
        PatternKind.SOLID -> {
            val a = bind.tint ?: Palette.ICE_4
            Swatch(a, lift(a, -0.55f))
        }

        PatternKind.HUE_SWEEP -> {
            val span = q.spanDeg ?: 360f
            val sat = q.sat ?: 0.8f
            val light = q.light ?: 0.62f
            val ph = (t / periodS) % 1f
            val h = (q.offsetDeg ?: 0f) + if (span >= 360f) {
                ph * 360f
            } else {
                sin(ph * PI2) * span * 0.5f
            }
            Swatch(hsl(h, sat, light), hsl(h + 28f, sat * 0.9f, light * 0.55f))
        }

        PatternKind.STEP_CYCLE -> {
            // Holds each colour, then blends to the next. The blend is the only
            // part that moves, which is what makes this readable at a glance and
            // cheap on the flash budget.
            val ring = q.colors?.takeIf { it.isNotEmpty() } ?: listOf(bind.tint ?: Palette.ICE_4)
            val hold = (q.holdS ?: 2f).coerceAtLeast(0.05f)
            val blend = (q.blendS ?: 0.45f).coerceAtLeast(0f)
            val step = hold + blend
            val total = step * ring.size
            val u = ((t % total) + total) % total
            val i = (u / step).toInt().coerceIn(0, ring.size - 1)
            val within = u - i * step
            val k = if (blend <= 0f) 0f else ((within - hold) / blend).coerceIn(0f, 1f)
            val a = mix(ring[i], ring[(i + 1) % ring.size], k)
            Swatch(a, lift(a, -0.55f))
        }

        PatternKind.BREATHE -> {
            val base = bind.tint ?: Palette.ICE_4
            val depth = q.depth ?: 0.45f
            val e = (sin(t / periodS * PI2) * 0.5f + 0.5f) * depth
            Swatch(lift(base, e * 0.8f - depth * 0.25f), lift(base, -0.6f + e * 0.3f))
        }

        PatternKind.PULSE -> {
            val base = bind.tint ?: Palette.AMBER_4
            val ph = max(0f, sin(t / periodS * PI2))
            val e = ph.pow(q.sharpness ?: 9f)
            Swatch(lift(base, e * 0.75f), lift(base, -0.7f + e * 0.4f))
        }

        PatternKind.GRADIENT -> {
            // The bound colour WINS. Before this rule, binding ice-5 to a
            // gradient still swung to the pattern's own magenta — which is why
            // nineteen of the twenty speaking tiles in the audit were pink. A
            // bound colour with no explicit `to` runs between the colour and its
            // own darker step; the two-hue default applies only when nothing is
            // bound, and those two hues are the pattern's own azure→magenta.
            val a = bind.color ?: q.from ?: Palette.AZURE_4
            val b = q.to?.takeIf { bind.color == null || bind.params.to != null }
                ?: if (bind.color != null) lift(a, -0.38f) else Palette.MAGENTA_4
            val k = sin(t / periodS * PI2) * 0.5f + 0.5f
            Swatch(mix(a, b, k), mix(b, a, k))
        }

        PatternKind.COMET -> {
            val head = bind.tint ?: Palette.ICE_5
            // The tail is the pattern's own colour, not a darkened head. Derived
            // from the head, the two collapsed to the same value at the loop
            // extreme and the comet had no tail at all.
            val tail = q.tail ?: lift(head, -0.75f)
            val k = (t / periodS) % 1f
            val e = (1f - abs(k * 2f - 1f)).pow(3)
            Swatch(mix(tail, head, e), tail)
        }

        PatternKind.FLICKER -> {
            // Rate is clamped to limits.flash.flicker_rate_hz_max before it
            // reaches the oscillator, not merely validated somewhere else: this
            // is the only path to a colour, so the clamp belongs here.
            val rate = (q.rateHz ?: 1.2f).coerceIn(0.05f, Spec.FLICKER_RATE_HZ_MAX)
            val depth = (q.depth ?: 0.25f).coerceIn(0f, 1f)
            val family = q.family ?: "ember"
            val base = bind.tint ?: Palette.byId["$family-4"] ?: Palette.EMBER_4
            // Two components, the stated rate and its 2.3x harmonic — the
            // harmonic is what the spec's limit is actually sized against.
            val n = sin(t * rate * PI2) * 0.6f +
                sin(t * rate * Spec.FLICKER_HARMONIC * PI2) * 0.4f
            val e = n * 0.5f * depth
            Swatch(lift(base, e), lift(base, -0.6f + e * 0.5f))
        }

        PatternKind.REACTIVE -> {
            val a = bind.color ?: q.quiet ?: Palette.AZURE_3
            val b = q.loud ?: Palette.ROSE_4
            val k = (amp * (q.gain ?: 1.6f)).coerceIn(0f, 1f)
            val out = mix(a, b, k)
            Swatch(out, lift(out, -0.55f))
        }

        PatternKind.TEMPERATURE -> {
            // Cold → warm → hot and back. One axis, three stops, so it reads as
            // a gauge rather than as a colour show.
            val cold = q.cold ?: Palette.ICE_2
            val warm = q.warm ?: Palette.AMBER_4
            val hot = q.hot ?: Palette.ROSE_4
            val u = sin(t / periodS * PI2) * 0.5f + 0.5f
            val a = if (u < 0.5f) mix(cold, warm, u * 2f) else mix(warm, hot, (u - 0.5f) * 2f)
            Swatch(a, lift(a, -0.55f))
        }

        PatternKind.STROBE -> {
            // The pattern's own safety note: below 0.4s it exceeds the
            // transition budget on its own, before the governor sees it.
            val strobeS = periodS.coerceAtLeast(Spec.STROBE_MIN_PERIOD_S)
            val on = ((t / strobeS) % 1f) < 0.5f
            // The off phase is the pattern's own neutral-1, not the renderer
            // background. Strobing to the background made the face vanish
            // entirely on half the cycle, which reads as crashed rather than as
            // alarmed.
            val a = if (on) {
                bind.color ?: q.onColor ?: Palette.ROSE_4
            } else {
                q.offColor ?: Palette.NEUTRAL_1
            }
            Swatch(a, lift(a, -0.5f))
        }
    }
}

/**
 * How long a strobe has been running, so [resolve] can stop it.
 *
 * `limits.flash.strobe_max_s` says a strobe must never run more than two
 * seconds at full face width. Nothing enforced that: a binding could strobe for
 * as long as its state lasted, and error states last until someone fixes them.
 * Kept per surface alongside the governor, for the same reason the governor is.
 */
class StrobeBudget {
    private var startedAt: Float? = null

    fun reset() { startedAt = null }

    /** True when this strobe has run past its limit and must be held. */
    fun spent(isStrobe: Boolean, t: Float): Boolean {
        if (!isStrobe) { startedAt = null; return false }
        val began = startedAt ?: t.also { startedAt = it }
        return t - began > Spec.STROBE_MAX_S
    }
}

/**
 * The only path to a colour, so a hand-written binding cannot get past the
 * flash limits.
 */
fun resolve(
    bind: Binding,
    t: Float,
    amp: Float,
    governor: FlashGovernor,
    strobe: StrobeBudget? = null,
): Swatch {
    val raw = resolveRaw(bind, t, amp)
    // A spent strobe freezes on its lit phase. Freezing on the dark phase would
    // leave the face looking switched off, and the state that most often strobes
    // is the one that most needs to stay visible.
    val capped = if (strobe?.spent(bind.kind == PatternKind.STROBE, t) == true) {
        val lit = bind.color ?: bind.merged.onColor ?: Palette.ROSE_4
        Swatch(lit, lift(lit, -0.5f))
    } else {
        raw
    }
    return governor.govern(capped, t)
}

const val PI2 = (Math.PI * 2).toFloat()

/** One-pole smoothing in SECONDS, so a 120 Hz panel smooths like a 60 Hz one. */
fun smooth(current: Float, target: Float, dt: Float, attackS: Float, releaseS: Float): Float {
    val tau = if (target > current) attackS else releaseS
    if (tau <= 0f) return target
    val k = 1f - kotlin.math.exp(-dt / tau)
    return current + (target - current) * min(1f, k)
}
