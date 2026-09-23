package com.jarvis.client.face

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import com.jarvis.client.FaceState
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/**
 * The reference's shared 3D maths, ported once for the five faces that were
 * rebuilt line-for-line against it: Spectrum, Coreplate, Workbench, Swarm and
 * Shoal (see each one's comment in Faces.kt for the artifact lines matched).
 *
 * Why a port and not the old "radius times cos" shortcuts: the reference
 * projects every point with real perspective (`proj`/`rot3` in the Jarvis
 * Reactor Kit, lines 2378-2449), and the perspective depth factor `d` is what
 * sizes and fades every dot, bar and line. The shortcuts drew flatter,
 * thinner versions - most with no perspective at all - and rendered side by
 * side with the reference, in 19 of the 20 face-and-state pairs they lit
 * between 1% and a third as many pixels (the exception is Swarm listening,
 * where the reference itself shrinks to one bead).
 *
 * Its own file and a single top-level name, so it cannot collide with
 * helpers the other faces in Faces.kt define.
 *
 * Main thread only. The projection writes into the fields below instead of
 * returning a new object per point - Swarm projects four hundred points a
 * frame, and an allocation per point at 120 fps is exactly what the other
 * faces' hoisted buffers were written to avoid. Every `Face.draw` runs on the
 * main thread (the GL faces never come through here), so nothing races.
 */
internal object CoreKit {

    /** Output of [proj]: screen x, y, the depth factor and the rotated z. */
    var px = 0f
    var py = 0f
    var pd = 0f
    var pz = 0f

    /** Output of [rot3]: the rotated point, not projected. */
    var rx = 0f
    var ry = 0f
    var rz = 0f

    /**
     * The reference's `rot3`: yaw about Y, then pitch about X, with the
     * owner's drag added to both - the reference adds `VIEW.yaw` and
     * `VIEW.pitch` inside the function for the same reason, so every face
     * gets the drag without doing anything itself.
     */
    fun rot3(f: FaceFrame, x: Float, y: Float, z: Float, yawIn: Float, pitchIn: Float) {
        val yaw = yawIn + f.yaw
        val pitch = pitchIn + f.pitch
        var c = cos(yaw)
        var s = sin(yaw)
        val x1 = x * c - z * s
        val z1 = x * s + z * c
        c = cos(pitch)
        s = sin(pitch)
        rx = x1
        ry = y * c - z1 * s
        rz = y * s + z1 * c
    }

    /**
     * The reference's `proj` (artifact 2378-2396): rotate, then real
     * perspective. [pd] is the unitless depth factor raised to the spec's
     * `depth_gain` - never a pixel scale, so it is safe to size lines by.
     */
    fun proj(
        f: FaceFrame, x: Float, y: Float, z: Float,
        yaw: Float, pitch: Float, dist: Float, scale: Float, cx: Float, cy: Float,
    ) {
        rot3(f, x, y, z, yaw, pitch)
        val k = scale / (dist + rz)
        px = cx + rx * k
        py = cy + ry * k
        pz = rz
        pd = (dist / (dist + rz)).pow(Spec.DEPTH_GAIN)
    }

    /**
     * One of the reference's canvas pixels, in this device's pixels.
     *
     * The reference sizes the few lines it does NOT scale with the face - a
     * hairline rim, a grid, a floor under a width - in raw canvas pixels, and
     * its canvas is `min(devicePixelRatio, 2) x 1.5` pixels per CSS pixel at
     * its default quality tier (artifact 5474-5493, `Q.ss` 1.5 at 5351). So
     * on a 2.75x phone one of its pixels is 2.75 / 3 = 0.92 real pixels.
     * Drawing that literally as `1f` would be right here by coincidence and
     * wrong on every other density; this says what it means.
     */
    fun backingPx(density: Float): Float = density / (min(density, 2f) * 1.5f)

    /**
     * The reference's `detail()` (artifact 2412-2416): how many elements a
     * face builds at a given canvas width, rising from `lo` at 200 px to
     * `hi` at 820 px. [canvasPx] is the width in the reference's own canvas
     * pixels, which is what its breakpoints are written in.
     */
    fun detail(canvasPx: Float, lo: Int, hi: Int): Int {
        val k = ((canvasPx - 200f) / 620f).coerceIn(0f, 1f)
        return kotlin.math.round(lo + (hi - lo) * k).toInt().coerceIn(lo, hi)
    }

    /** The reference's `shade()`: scale the RGB channels, clamped. Alpha kept. */
    fun shade(c: Color, m: Float): Color = Color(
        red = (c.red * m).coerceIn(0f, 1f),
        green = (c.green * m).coerceIn(0f, 1f),
        blue = (c.blue * m).coerceIn(0f, 1f),
        alpha = c.alpha,
    )

    /**
     * Clips what follows to the view the face is drawn in; the face calls
     * `drawContext.canvas.restore()` when it is done.
     *
     * The reference draws into its own canvas element, which clips: Shoal's
     * school swims past the edge, Workbench's exploded shells rise out of the
     * top, and both simply leave the frame. A Compose `Canvas` does not clip
     * to its bounds, so drawn faithfully here the same geometry would paint
     * over whatever sits next to the face - Appearance's live preview, for
     * one, is a bare `Modifier.size(160.dp)` with nothing clipping it.
     */
    fun clipToView(scope: DrawScope) {
        val c = scope.drawContext.canvas
        c.save()
        c.clipRect(0f, 0f, scope.size.width, scope.size.height)
    }

    /**
     * Gradient stops for the reference's radial fades that end at
     * `rgba(0,0,0,0)`: [c] at alpha [a] at position [from], to clear at 1.
     *
     * A browser canvas blends gradient colours WITHOUT premultiplying, so a
     * fade to transparent black also darkens toward black on the way out.
     * Compose on Skia blends premultiplied, which does not - measured on the
     * same gradient, a quarter of the way out it came to 50 / 100 / 113
     * against the browser's 37 / 75 / 87, a third brighter, and every glow on
     * Spectrum and Coreplate read as a larger, hotter halo than the
     * desktop's. Spelling out the darkening at four steps makes both kinds of
     * blending give the browser's result, so this does not depend on which
     * one the device's renderer uses.
     */
    fun fadeToClear(c: Color, a: Float, from: Float = 0f): Array<Pair<Float, Color>> = Array(5) { k ->
        val u = k / 4f
        val keep = 1f - u
        (from + (1f - from) * u) to Color(
            red = c.red * keep, green = c.green * keep, blue = c.blue * keep,
            alpha = (a * keep).coerceIn(0f, 1f),
        )
    }

    /**
     * The reference's literal `#ffffff` (Swarm's fast heads, Coreplate's
     * core, Workbench's lit edges), dimmed the way this shell dims the state
     * colours - toward the ground by `f.dim`. The reference only overrides
     * its per-state colours, so on the desktop a literal white stays full
     * white in a dimmed state; on a face that is otherwise dimmed for
     * standby or banked, that is a bright spot the dim was meant to remove.
     * `Spec.BACKGROUND` rather than a themed ground because a face is not
     * told the theme; the two differ only in a dimmed state, and only by the
     * difference between two near-black grounds.
     */
    fun white(f: FaceFrame): Color = mix(Spec.BACKGROUND, Color.White, f.dim)

    /**
     * How far a state change has settled, 0 at the change and 1 once done.
     *
     * The reference eases a few per-state targets (plate separation, a
     * flock's spread) with a per-frame lerp - `x = lerp(x, target, 0.04)` -
     * which is memory: it needs last frame's `x`. These faces are kept a pure
     * function of their frame (see `SpecDriftTest`), so they ease instead
     * from the previous state's target to this one's along the same
     * exponential curve, timed from the change. That is the same motion
     * whenever the previous ease had finished, and only differs - by a small
     * step, not a jump across the whole range - when the state changes twice
     * within about a second.
     *
     * [tauS] is the lerp's time constant: a per-frame factor `a` at 60 fps is
     * `tau = -1 / (60 ln(1 - a))`, so 0.04 is 0.41 s and 0.05 is 0.33 s.
     */
    fun settle(f: FaceFrame, tauS: Float): Float =
        if (f.prevMotion == f.motion) 1f else 1f - exp(-(f.hitchPhase.coerceAtLeast(0f)) / tauS)

    /** Blend a per-state value from the previous motion to this one. */
    inline fun eased(f: FaceFrame, tauS: Float, of: (FaceState) -> Float): Float {
        val cur = of(f.motion)
        if (f.prevMotion == f.motion) return cur
        val e = settle(f, tauS)
        return of(f.prevMotion) + (cur - of(f.prevMotion)) * e
    }

    /**
     * Sorts `order[0 until n]` so the FARTHEST point (largest z) comes first:
     * the painter's order every reference face draws in. Insertion sort,
     * because `order` is kept between frames and a cloud turns only a little
     * per frame, so it is nearly sorted already and this is close to one
     * pass. The result does not depend on the starting order except between
     * exactly equal depths, so keeping it is a cost saving, not memory.
     *
     * [fresh] restarts from 0..n-1, which the caller must ask for whenever n
     * changed since the last call: `order` then holds indices of a different
     * count, and sorting those would draw some points twice and others never.
     */
    fun sortFarFirst(order: IntArray, z: FloatArray, n: Int, fresh: Boolean) {
        if (fresh) for (i in 0 until n) order[i] = i
        for (i in 1 until n) {
            val v = order[i]
            val zv = z[v]
            var j = i - 1
            while (j >= 0 && z[order[j]] < zv) {
                order[j + 1] = order[j]
                j--
            }
            order[j + 1] = v
        }
    }
}
