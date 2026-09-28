package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import kotlin.math.max
import kotlin.math.min

/**
 * Paints a [Season.Scene] BEHIND a character face - the desktop's
 * `season.js` `draw()`: the same steps in the same order (soft glows, dots,
 * filled shapes, thin lines), the same colours. Nothing flashes.
 *
 * Dimming: the sky ([SkyDraw]) lays the ground over itself at `1 - dim`.
 * This layer is drawn AFTER the sky, so laying the ground again would dim
 * the sky twice; instead every colour here is pulled toward the ground by
 * the same dim - `mix(ground, colour, dim)` at the step's own alpha - which
 * is exactly what one ground layer over both would give.
 */
object SeasonDraw {

    private fun ch(ground: Float, c: Double, dim: Float): Float =
        ((ground * 255.0 + (c - ground * 255.0) * dim) / 255.0).toFloat().coerceIn(0f, 1f)

    private fun colour(v: DoubleArray, at: Int, a: Double, dim: Float, ground: Color): Color =
        Color(
            ch(ground.red, v[at], dim), ch(ground.green, v[at + 1], dim), ch(ground.blue, v[at + 2], dim),
            a.toFloat().coerceIn(0f, 1f),
        )

    /**
     * @param dim the face's dim this frame, 0..1 (1 = full brightness):
     *   [CritterFace.dimFor].
     * @param ground the face's ground colour.
     */
    fun draw(scope: DrawScope, sc: Season.Scene, dim: Float, ground: Color) = with(scope) {
        if (sc.ops.isEmpty()) return@with
        val w = size.width
        val h = size.height
        val k = min(w, h) / 2f
        val cx = w / 2f
        val cy = h / 2f
        val dm = dim.coerceIn(0f, 1f)
        fun at(x: Double, y: Double) = Offset(cx + (x * k).toFloat(), cy - (y * k).toFloat())
        fun pathOf(v: DoubleArray, from: Int, close: Boolean): Path {
            val p = Path()
            var i = from
            while (i + 1 < v.size) {
                val o = at(v[i], v[i + 1])
                if (i == from) p.moveTo(o.x, o.y) else p.lineTo(o.x, o.y)
                i += 2
            }
            if (close) p.close()
            return p
        }
        for (op in sc.ops) {
            val v = op.v
            when (op.k) {
                Season.GLOW -> {
                    val c = at(v[0], v[1])
                    val r = max(1f, (v[2] * k).toFloat())
                    drawCircle(
                        Brush.radialGradient(
                            listOf(colour(v, 3, v[6], dm, ground), colour(v, 3, 0.0, dm, ground)),
                            center = c, radius = r,
                        ),
                        radius = r, center = c,
                    )
                }
                Season.DOT -> drawCircle(
                    colour(v, 3, v[6], dm, ground),
                    radius = max(0.8f, (v[2] * k).toFloat()), center = at(v[0], v[1]),
                )
                Season.POLY -> drawPath(pathOf(v, 4, true), colour(v, 0, v[3], dm, ground))
                Season.LINE -> drawPath(
                    pathOf(v, 5, false), colour(v, 1, v[4], dm, ground),
                    style = Stroke(width = max(1f, (v[0] * k).toFloat()), cap = StrokeCap.Round, join = StrokeJoin.Round),
                )
            }
        }
    }
}

/**
 * The shared "Seasonal touches" switch (`seasonal`, off by default) as the
 * phone last heard it from the PC ([com.jarvis.client.net.AnimalOptions]).
 * JarvisRuntime sets it whenever the animal options arrive; every FaceView
 * reads it each frame, like [SkyNow].
 */
object SeasonNow {
    @Volatile
    var on: Boolean = false
}

/**
 * The seasonal touches behind [face] for this frame, when the owner has
 * switched them on: from this phone's own clock and time zone, the
 * hemisphere from the sky's saved place (north when none), hidden under
 * Still and in a serious moment, the moving and holiday pieces put away
 * during an approval or an error ([Season.holdWeight]), fewer and still
 * under calm motion, and dimmed with the face. FaceView's `drawFace` calls
 * it right after `drawSkyBehind` and before the face. Nothing at all is
 * drawn when it is off.
 */
fun DrawScope.drawSeasonBehind(face: CritterFace, f: FaceFrame, ground: Color) {
    if (!SeasonNow.on) return
    val w = size.width
    val h = size.height
    val k = min(w, h)
    if (k < 1f) return
    val nowMs = System.currentTimeMillis()
    val stored = SkyNow.stored
    val place = stored.place
    val weather = stored.live(nowMs)?.weather
    val sunAlt = place?.let { Sky.sun(nowMs.toDouble(), it.lat, it.lon).alt }
    val hold = Season.holdWeight(
        f.state.name.lowercase(), f.prevState.name.lowercase(), f.hitchPhase.toDouble(),
    )
    val sc = Season.scene(
        nowMs.toDouble(), java.util.TimeZone.getDefault().getOffset(nowMs) / 60000.0, nowMs / 1000.0,
        lat = place?.lat, calm = f.calm, hide = max(f.stillW, f.seriousW).toDouble(), hold = hold,
        ax0 = (w / k).toDouble(), ay0 = (h / k).toDouble(), sunAlt0 = sunAlt,
        snow = weather?.snow ?: 0.0, rain = weather?.rain ?: 0.0,
        snowman = Season.snowmanFor(face.id),
    )
    SeasonDraw.draw(this, sc, face.dimFor(f), ground)
}
