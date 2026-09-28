package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.scale
import kotlin.math.max
import kotlin.math.min

/**
 * Paints a [Sky.Scene] BEHIND an animal face - the desktop's `sky.js`
 * `draw()`, the same shapes, colours and order: the tint, the dawn or dusk
 * glow, the sun, the moon in its real phase, clouds, fog, then rain, snow or
 * lines of wind. Everything is soft and see-through; nothing flashes.
 *
 * FaceView's `drawFace` calls it after the ground is painted and before the
 * animal, then lays the ground over it at `1 - dim` - the animal's own dim
 * for this frame ([CritterFace.dimFor]) - so the sky darkens and brightens
 * with the animal on standby, exactly as the desktop's `dimOver` covers both.
 */
object SkyDraw {

    private fun rgba(r: Double, g: Double, b: Double, a: Double): Color =
        Color(
            (r / 255.0).toFloat().coerceIn(0f, 1f), (g / 255.0).toFloat().coerceIn(0f, 1f),
            (b / 255.0).toFloat().coerceIn(0f, 1f), a.toFloat().coerceIn(0f, 1f),
        )

    private fun mix(a: Double, b: Double, k: Double) = a + (b - a) * k

    /**
     * @param dim the animal's dim this frame, 0..1 (1 = full brightness).
     * @param ground the face's ground colour, laid over the sky at `1 - dim`.
     */
    fun draw(scope: DrawScope, sc: Sky.Scene, dim: Float, ground: Color) = with(scope) {
        val w = size.width
        val h = size.height
        val k = min(w, h) / 2f
        val cx = w / 2f
        val cy = h / 2f
        fun at(x: Double, y: Double) = Offset(cx + (x * k).toFloat(), cy - (y * k).toFloat())

        sc.tint?.let { t ->
            drawRect(
                Brush.verticalGradient(listOf(rgba(t[0], t[1], t[2], t[3]), rgba(t[4], t[5], t[6], t[7])), 0f, h),
                size = Size(w, h),
            )
        }
        sc.glow?.let { g ->
            if (g.alpha > 0.002) {
                val c = at(g.x, g.y)
                drawRect(
                    Brush.radialGradient(
                        listOf(rgba(255.0, 150.0, 80.0, g.alpha), rgba(255.0, 150.0, 80.0, 0.0)),
                        center = c, radius = max(1f, (g.r * k).toFloat()),
                    ),
                    size = Size(w, h),
                )
            }
        }
        sc.sun?.let { s ->
            if (s.alpha > 0.002) {
                val c = at(s.x, s.y)
                val r = (s.r * k).toFloat()
                val cr = 255.0
                val cg = mix(241.0, 179.0, s.warm)
                val cb = mix(201.0, 107.0, s.warm)
                if (s.glow > 0.002) {
                    val gr = r * 4.2f
                    drawCircle(
                        Brush.radialGradient(
                            0f to rgba(255.0, 200.0, 120.0, s.glow),
                            (0.5f / 4.2f) to rgba(255.0, 200.0, 120.0, s.glow),
                            1f to rgba(255.0, 200.0, 120.0, 0.0),
                            center = c, radius = max(1f, gr),
                        ),
                        radius = gr, center = c,
                    )
                }
                drawCircle(
                    Brush.radialGradient(
                        0f to rgba(255.0, 250.0, 235.0, s.alpha),
                        0.7f to rgba(cr, cg, cb, s.alpha),
                        1f to rgba(cr, cg, cb, s.alpha * 0.55),
                        center = c, radius = max(1f, r),
                    ),
                    radius = r, center = c,
                )
            }
        }
        sc.moon?.let { m ->
            if (m.alpha > 0.002) {
                val c = at(m.x, m.y)
                val r = (m.r * k).toFloat()
                if (m.glow > 0.002) {
                    val gr = r * 3.4f
                    drawCircle(
                        Brush.radialGradient(
                            0f to rgba(200.0, 215.0, 235.0, m.glow),
                            (0.6f / 3.4f) to rgba(200.0, 215.0, 235.0, m.glow),
                            1f to rgba(200.0, 215.0, 235.0, 0.0),
                            center = c, radius = max(1f, gr),
                        ),
                        radius = gr, center = c,
                    )
                }
                // The unlit side, faintly (earthshine), so the moon reads as a disc.
                drawCircle(rgba(226.0, 232.0, 240.0, 0.07 * m.alpha), radius = r, center = c)
                if (m.fraction > 0.005) {
                    val pts = Sky.moonOutline(m.fraction, m.bx, m.by, 24)
                    val path = Path()
                    pts.forEachIndexed { i, p ->
                        val o = at(m.x + p[0] * m.r, m.y + p[1] * m.r)
                        if (i == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y)
                    }
                    path.close()
                    drawPath(path, rgba(226.0, 232.0, 240.0, 0.9 * m.alpha))
                }
            }
        }
        for (cl in sc.clouds) {
            val cr = mix(70.0, 150.0, sc.cloudDay)
            val cg = mix(80.0, 165.0, sc.cloudDay)
            val cb = mix(95.0, 180.0, sc.cloudDay)
            val c = at(cl[0], cl[1])
            val r = (cl[2] * k).toFloat()
            scale(1f, (cl[3] / cl[2]).toFloat(), pivot = c) {
                drawCircle(
                    Brush.radialGradient(listOf(rgba(cr, cg, cb, cl[4]), rgba(cr, cg, cb, 0.0)), center = c, radius = max(1f, r)),
                    radius = r, center = c,
                )
            }
        }
        if (sc.fog > 0.002) drawRect(rgba(120.0, 130.0, 140.0, sc.fog), size = Size(w, h))
        val line = max(1f, 0.006f * k)
        for (d in sc.rain) {
            drawLine(
                rgba(150.0, 180.0, 210.0, d[4]), at(d[0], d[1]), at(d[0] - d[2], d[1] + d[3]),
                strokeWidth = line, cap = StrokeCap.Round,
            )
        }
        for (f in sc.snow) {
            drawCircle(rgba(230.0, 238.0, 245.0, f[3]), radius = max(0.8f, (f[2] * k).toFloat()), center = at(f[0], f[1]))
        }
        val wisp = max(1f, 0.005f * k)
        for (wv in sc.wisps) {
            drawLine(
                rgba(190.0, 205.0, 220.0, wv[3]), at(wv[0], wv[1]), at(wv[0] + wv[2], wv[1]),
                strokeWidth = wisp, cap = StrokeCap.Round,
            )
        }
        // Dim with the animal: the ground over everything above at 1 - dim,
        // which is exactly mix(ground, sky, dim) - the desktop's dimOver.
        if (dim < 0.999f) drawRect(ground.copy(alpha = (1f - dim.coerceIn(0f, 1f))), size = Size(w, h))
    }
}

/**
 * What the animal faces draw behind them, as the phone last heard it from the
 * PC (`GET /api/sky`, [com.jarvis.client.net.SkySettings]): on or off, the
 * position rounded to 0.1 degree, the weather numbers. JarvisRuntime sets it,
 * and keeps a copy in the phone's own settings so it survives a restart and
 * works while the PC cannot be reached; every FaceView reads it each frame.
 */
object SkyNow {
    @Volatile
    var stored: com.jarvis.client.net.SkySettings.Stored =
        com.jarvis.client.net.SkySettings.Stored(false, null, null, 0L)
}

/**
 * The sky behind [face] for this frame, if the owner has switched anything
 * on: worked out from the wall clock (so it moves with real time, and both
 * apps' rain falls alike), still under calm motion, and dimmed with the
 * animal ([CritterFace.dimFor]). FaceView's `drawFace` calls it after the
 * ground and before the animal. Nothing at all is drawn when it is off.
 */
fun DrawScope.drawSkyBehind(face: CritterFace, f: FaceFrame, ground: Color) {
    val nowMs = System.currentTimeMillis()
    val live = SkyNow.stored.live(nowMs) ?: return
    val w = size.width
    val h = size.height
    val k = min(w, h)
    if (k < 1f) return
    val sc = Sky.scene(
        nowMs.toDouble(), nowMs / 1000.0, live.place, live.weather,
        calm = f.calm, ax0 = (w / k).toDouble(), ay0 = (h / k).toDouble(),
    )
    SkyDraw.draw(this, sc, face.dimFor(f), ground)
}
