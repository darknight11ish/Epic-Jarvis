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
 * @param amp the smoothed drive: the microphone while listening, Jarvis's own
 *   voice while speaking. Never the raw level; the shell owns the envelope.
 */
fun resolveRaw(bind: Binding, t: Float, amp: Float): Swatch = when (bind.kind) {
    PatternKind.SOLID -> {
        val a = bind.color ?: Spec.ICE_4
        Swatch(a, lift(a, -0.55f))
    }

    PatternKind.HUE_SWEEP -> {
        val ph = (t / bind.periodS) % 1f
        val h = bind.offsetDeg + if (bind.spanDeg >= 360f) {
            ph * 360f
        } else {
            sin(ph * PI2) * bind.spanDeg * 0.5f
        }
        Swatch(
            hsl(h, bind.sat, bind.light),
            hsl(h + 28f, bind.sat * 0.9f, bind.light * 0.55f),
        )
    }

    PatternKind.BREATHE -> {
        val base = bind.color ?: Spec.ICE_4
        val e = (sin(t / bind.periodS * PI2) * 0.5f + 0.5f) * bind.depth
        Swatch(lift(base, e * 0.8f - bind.depth * 0.25f), lift(base, -0.6f + e * 0.3f))
    }

    PatternKind.PULSE -> {
        val base = bind.color ?: Spec.AMBER_4
        val ph = max(0f, sin(t / bind.periodS * PI2))
        val e = ph.pow(bind.sharpness)
        Swatch(lift(base, e * 0.75f), lift(base, -0.7f + e * 0.4f))
    }

    PatternKind.GRADIENT -> {
        // The bound colour WINS. Before this rule, binding ice-5 to a gradient
        // still swung to the pattern's own magenta — which is why nineteen of
        // the twenty speaking tiles in the audit were pink. A bound colour with
        // no explicit `to` runs between the colour and its own darker step; the
        // two-hue default applies only when nothing is bound.
        val a = bind.color ?: Spec.ICE_4
        val b = bind.to ?: if (bind.color != null) lift(a, -0.38f) else Spec.ICE_3
        val k = sin(t / bind.periodS * PI2) * 0.5f + 0.5f
        Swatch(mix(a, b, k), mix(b, a, k))
    }

    PatternKind.REACTIVE -> {
        val a = bind.color ?: Spec.ICE_4
        val b = bind.loud ?: Spec.ICE_5
        val k = (amp * bind.gain).coerceIn(0f, 1f)
        val out = mix(a, b, k)
        Swatch(out, lift(out, -0.55f))
    }

    PatternKind.COMET -> {
        val head = bind.color ?: Spec.ICE_5
        val tail = lift(head, -0.75f)
        val k = (t / bind.periodS) % 1f
        val e = (1f - abs(k * 2f - 1f)).pow(3)
        Swatch(mix(tail, head, e), tail)
    }

    PatternKind.STROBE -> {
        val on = ((t / bind.periodS) % 1f) < 0.5f
        val a = if (on) (bind.color ?: Spec.ROSE_4) else Spec.BACKGROUND
        Swatch(a, lift(a, -0.5f))
    }
}

/**
 * The only path to a colour, so a hand-written binding cannot get past the
 * flash limits.
 */
fun resolve(bind: Binding, t: Float, amp: Float, governor: FlashGovernor): Swatch =
    governor.govern(resolveRaw(bind, t, amp), t)

const val PI2 = (Math.PI * 2).toFloat()

/** One-pole smoothing in SECONDS, so a 120 Hz panel smooths like a 60 Hz one. */
fun smooth(current: Float, target: Float, dt: Float, attackS: Float, releaseS: Float): Float {
    val tau = if (target > current) attackS else releaseS
    if (tau <= 0f) return target
    val k = 1f - kotlin.math.exp(-dt / tau)
    return current + (target - current) * min(1f, k)
}
