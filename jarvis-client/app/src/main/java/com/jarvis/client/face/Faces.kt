package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import com.jarvis.client.FaceState
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin

/**
 * A face draws itself and knows nothing about Jarvis.
 *
 * Four motion tables, not eight. The other four states borrow one of these and
 * the shell applies a transform on top — a clock multiplier, a direction, a dim
 * and at most one overlay. That is why `speedFor` takes a [FaceState] but only
 * ever receives one of the four: the shell has already resolved the borrow.
 */
interface Face {
    val id: String
    val name: String

    /** faces[].render.fit — uniform scale so the silhouette does not touch the edge. */
    val fit: Float get() = 1f

    /** Recommended for archiving behind a "more faces" toggle. Never removed. */
    val archived: Boolean get() = false

    fun speedFor(motion: FaceState): Float

    fun draw(
        scope: DrawScope,
        cx: Float,
        cy: Float,
        r: Float,
        hot: Color,
        cool: Color,
        f: FaceFrame,
    )
}

/**
 * Six faces, not twenty.
 *
 * The brief is explicit that porting all twenty is the real cost of going fully
 * native and that six to eight is the right number. These are all from the
 * spec's `stays_on_canvas` list — line, stroke, point and glow art that Compose
 * draws correctly and cheaply. The three that need a shader (nucleus via AGSL,
 * membrane and tokamak via GLES) are deliberately absent: a rasterised version
 * of those is the faceted, upscaled thing the first audit was about, and
 * shipping it would be worse than not offering them.
 *
 * The picker shows only what is actually rendered — not all twenty with most of
 * them missing.
 */
object Faces {
    val all: List<Face> = listOf(Arc, Orbit, Comb, Spiral, Iris, Fullerene)
    val default: Face = Arc
    fun byId(id: String): Face = all.firstOrNull { it.id == id } ?: default
}

/** Concentric rings. The quiet one. */
object Arc : Face {
    override val id = "arc"
    override val name = "Arc"

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.8f
        FaceState.THINKING -> 2.2f
        FaceState.SPEAKING -> 1.4f
        else -> 0.45f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val rings = 5
        for (i in 0 until rings) {
            val k = i / (rings - 1f)
            val rr = r * (0.35f + k * 0.65f)
            val dir = if (i % 2 == 0) 1f else -1f
            val sweep = 90f + 150f * (0.5f + 0.5f * sin(f.tableAngle * (0.6f + k) + i))
            drawArc(
                color = mix(cool, hot, k * (0.5f + 0.5f * f.amp)),
                startAngle = Math.toDegrees((f.angle * dir * (0.4f + k)).toDouble()).toFloat(),
                sweepAngle = sweep,
                useCenter = false,
                topLeft = Offset(cx - rr, cy - rr),
                size = androidx.compose.ui.geometry.Size(rr * 2, rr * 2),
                style = Stroke(width = r * 0.045f),
            )
        }
        drawCircle(hot, r * (0.10f + 0.04f * f.amp), Offset(cx, cy))
    }
}

/** Five inclined orbits, depth sorted. */
object Orbit : Face {
    override val id = "orbit"
    override val name = "Orbit"

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.0f
        FaceState.THINKING -> 2.6f
        FaceState.SPEAKING -> 1.6f
        else -> 0.5f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val steps = 48
        for (o in 0 until 5) {
            val incl = (o / 5f) * PI.toFloat() * 0.8f + f.pitch * 0.4f
            for (s in 0 until steps) {
                val a = s / steps.toFloat() * PI2 + f.angle * (0.5f + o * 0.15f) + f.yaw
                val x = cos(a) * r
                val y = sin(a) * r * cos(incl)
                // Depth is read for size and alpha only, never position. Raising
                // it is the one change that makes the most 3D faces read as
                // volumes: far particles smaller and fainter, near ones bigger.
                val z = sin(a) * sin(incl)
                val d = ((z + 1f) / 2f).pow(Spec.DEPTH_GAIN)
                drawCircle(
                    color = mix(cool, hot, d).copy(alpha = 0.25f + 0.75f * d),
                    radius = r * (0.012f + 0.022f * d) * (1f + f.amp * 0.5f),
                    center = Offset(cx + x, cy + y),
                )
            }
        }
    }
}

/** Hex lattice. */
object Comb : Face {
    override val id = "comb"
    override val name = "Comb"

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.7f
        FaceState.THINKING -> 1.8f
        FaceState.SPEAKING -> 1.1f
        else -> 0.35f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val cell = r * 0.28f
        var ring = 0
        while (ring <= 3) {
            val count = if (ring == 0) 1 else ring * 6
            for (i in 0 until count) {
                val a = if (ring == 0) 0f else i / count.toFloat() * PI2
                val dist = cell * ring * 1.55f
                val x = cx + cos(a) * dist
                val y = cy + sin(a) * dist
                val beat = 0.5f + 0.5f * sin(f.tableAngle * 1.4f - ring * 0.8f + i * 0.3f)
                val k = beat * (0.45f + 0.55f * f.amp)
                hexagon(x, y, cell * 0.52f, f.angle * 0.25f) { p0, p1 ->
                    drawLine(
                        color = mix(cool, hot, k),
                        start = p0,
                        end = p1,
                        strokeWidth = r * 0.018f,
                    )
                }
            }
            ring++
        }
    }

    private inline fun hexagon(
        x: Float, y: Float, rad: Float, rot: Float,
        edge: (Offset, Offset) -> Unit,
    ) {
        var prev: Offset? = null
        var first: Offset? = null
        for (i in 0..5) {
            val a = rot + i / 6f * PI2
            val p = Offset(x + cos(a) * rad, y + sin(a) * rad)
            if (first == null) first = p
            prev?.let { edge(it, p) }
            prev = p
        }
        if (prev != null && first != null) edge(prev, first)
    }
}

/** Logarithmic arms — a particle field, so the depth gain does real work. */
object Spiral : Face {
    override val id = "spiral"
    override val name = "Spiral"

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.6f
        FaceState.THINKING -> 1.9f
        FaceState.SPEAKING -> 1.0f
        else -> 0.3f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val arms = 3
        val per = 90
        for (arm in 0 until arms) {
            for (i in 0 until per) {
                val k = i / per.toFloat()
                val a = arm / arms.toFloat() * PI2 + k * 3.4f + f.angle * 0.6f + f.yaw
                val dist = r * k.pow(0.7f)
                val wobble = sin(f.tableAngle * 0.8f + k * 6f) * r * 0.03f
                val d = (1f - k).pow(Spec.DEPTH_GAIN)
                drawCircle(
                    color = mix(cool, hot, d * (0.5f + 0.5f * f.amp))
                        .copy(alpha = 0.2f + 0.8f * d),
                    radius = r * (0.006f + 0.018f * d),
                    center = Offset(cx + cos(a) * dist, cy + sin(a) * dist + wobble),
                )
            }
        }
        drawCircle(hot, r * (0.07f + 0.03f * f.amp), Offset(cx, cy))
    }
}

/** Overlapping aperture blades. */
object Iris : Face {
    override val id = "iris"
    override val name = "Iris"
    override val fit = 0.86f

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.9f
        FaceState.THINKING -> 2.0f
        FaceState.SPEAKING -> 1.3f
        else -> 0.4f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val blades = 9
        val open = 0.35f + 0.25f * (0.5f + 0.5f * sin(f.tableAngle * 0.9f)) + f.amp * 0.15f
        for (i in 0 until blades) {
            val a = i / blades.toFloat() * PI2 + f.angle * 0.3f
            val inner = r * open
            val p0 = Offset(cx + cos(a) * inner, cy + sin(a) * inner)
            val p1 = Offset(cx + cos(a + 0.9f) * r, cy + sin(a + 0.9f) * r)
            drawLine(
                color = mix(cool, hot, i / blades.toFloat()),
                start = p0,
                end = p1,
                strokeWidth = r * 0.05f,
            )
        }
        // The catchlight drifts, and follows the touch when there is one.
        val look = f.ringAt
        val lx = if (look != null) (look.x - cx) * 0.06f else sin(f.t * 0.4f) * r * 0.08f
        val ly = if (look != null) (look.y - cy) * 0.06f else cos(f.t * 0.31f) * r * 0.06f
        drawCircle(hot, r * open * 0.55f, Offset(cx, cy))
        drawCircle(
            lift(hot, 0.5f).copy(alpha = 0.7f),
            r * 0.08f,
            Offset(cx + lx - r * 0.1f, cy + ly - r * 0.1f),
        )
    }
}

/** Truncated icosahedron cage. Survives thinking and speaking where geodesic smears. */
object Fullerene : Face {
    override val id = "fullerene"
    override val name = "Fullerene"

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.75f
        FaceState.THINKING -> 2.1f
        FaceState.SPEAKING -> 1.2f
        else -> 0.38f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        // A spherical point set rotated by angle and the drag, with edges drawn
        // between near neighbours. Cheap, and it reads as a cage rather than a
        // disc because of the depth gain.
        val n = 62
        val pts = ArrayList<Triple<Float, Float, Float>>(n)
        val golden = PI.toFloat() * (3f - kotlin.math.sqrt(5f))
        for (i in 0 until n) {
            val y = 1f - (i / (n - 1f)) * 2f
            val rad = kotlin.math.sqrt(1f - y * y)
            val th = golden * i + f.angle * 0.5f + f.yaw
            var x = cos(th) * rad
            var z = sin(th) * rad
            // pitch
            val cp = cos(f.pitch); val sp = sin(f.pitch)
            val y2 = y * cp - z * sp
            z = y * sp + z * cp
            pts.add(Triple(x, y2, z))
        }
        for (i in pts.indices) {
            val (x, y, z) = pts[i]
            val d = ((z + 1f) / 2f).pow(Spec.DEPTH_GAIN)
            val px = cx + x * r
            val py = cy + y * r
            drawCircle(
                color = mix(cool, hot, d).copy(alpha = 0.25f + 0.75f * d),
                radius = r * (0.012f + 0.02f * d) * (1f + f.amp * 0.4f),
                center = Offset(px, py),
            )
            // Edges to the next few points only: a full neighbour search is
            // O(n^2) for a cage nobody can count the edges of.
            for (j in i + 1 until minOf(i + 4, pts.size)) {
                val (qx, qy, qz) = pts[j]
                val dq = ((qz + 1f) / 2f).pow(Spec.DEPTH_GAIN)
                drawLine(
                    color = mix(cool, hot, (d + dq) / 2f).copy(alpha = 0.10f + 0.3f * d),
                    start = Offset(px, py),
                    end = Offset(cx + qx * r, cy + qy * r),
                    strokeWidth = r * 0.008f,
                )
            }
        }
    }
}
