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
 * Eight faces, not twenty.
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
 *
 * Rime and Orbital were chosen over the flashier candidates for one reason:
 * they are the only two missing faces the spec marks `integrates_per_frame:
 * false` that are neither `heavy` nor recommended for the archive. Stateless
 * means a pure function of `t`, which means the result can be pinned by a
 * golden test the way the pattern engine is. Swarm, shoal, cascade, membrane
 * and the rest carry simulation state between frames, so there is no value to
 * assert and nothing to catch a drift — and drift in a face is invisible until
 * someone compares it side by side with the desktop.
 */
object Faces {
    val all: List<Face> = listOf(Arc, Orbit, Comb, Spiral, Iris, Fullerene, Rime, Orbital)
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
            // Hoisted: these were recomputed for all 48 steps of the inner
            // loop, 480 redundant trig calls a frame.
            val ci = cos(incl)
            val si = sin(incl)
            for (s in 0 until steps) {
                val a = s / steps.toFloat() * PI2 + f.angle * (0.5f + o * 0.15f) + f.yaw
                val x = cos(a) * r
                val y = sin(a) * r * ci
                // Depth is read for size and alpha only, never position. Raising
                // it is the one change that makes the most 3D faces read as
                // volumes: far particles smaller and fainter, near ones bigger.
                val z = sin(a) * si
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

    /**
     * Floats, not nullable Offsets.
     *
     * `Offset` is a value class over a Long, so it is free — until it is made
     * nullable, at which point every assignment boxes. `prev` and `first` were
     * `Offset?`, which cost 7 boxes per hexagon; at 37 hexagons that is 259
     * allocations a frame, 15,500 a second, around 250 KB/s — the largest
     * single allocation source in the app, and precisely the shape the
     * Fullerene comment further down congratulates itself on having removed.
     *
     * The Offsets handed to the inlined [edge] are non-null and stay unboxed.
     */
    private inline fun hexagon(
        x: Float, y: Float, rad: Float, rot: Float,
        edge: (Offset, Offset) -> Unit,
    ) {
        val firstX = x + cos(rot) * rad
        val firstY = y + sin(rot) * rad
        var prevX = firstX
        var prevY = firstY
        for (i in 1..5) {
            val a = rot + i / 6f * PI2
            val px = x + cos(a) * rad
            val py = y + sin(a) * rad
            edge(Offset(prevX, prevY), Offset(px, py))
            prevX = px
            prevY = py
        }
        edge(Offset(prevX, prevY), Offset(firstX, firstY))
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
        // The pupil, unchanged. It was followed by a drifting catchlight - a
        // highlight here plus a second small offset one that tracked touch -
        // removed to match the reactor kit's v10, which dropped the same two
        // elements from its own Iris. No reason was given upstream for the
        // removal; ported as a straight parity change, not because a defect
        // was found in this port on its own.
        drawCircle(hot, r * open * 0.55f, Offset(cx, cy))
    }
}

/** Truncated icosahedron cage. Survives thinking and speaking where geodesic smears. */
object Fullerene : Face {
    override val id = "fullerene"
    override val name = "Fullerene"

    private const val N = 62
    private val xBuf = FloatArray(N)
    private val yBuf = FloatArray(N)
    private val zBuf = FloatArray(N)

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
        val n = N
        // Three reused FloatArrays rather than an ArrayList of Triples.
        //
        // The list rebuilt itself every frame: 62 Triples plus about 186 boxed
        // Floats, so roughly 250 objects a frame and 15,000 a second, for a
        // nursery collection every few seconds in the middle of a 60fps draw.
        // The arrays are fields on the face, which is a singleton, so this is
        // 744 bytes allocated once for the life of the process.
        val xs = xBuf
        val ys = yBuf
        val zs = zBuf
        val golden = PI.toFloat() * (3f - kotlin.math.sqrt(5f))
        val cp = cos(f.pitch)
        val sp = sin(f.pitch)
        for (i in 0 until n) {
            val y = 1f - (i / (n - 1f)) * 2f
            val rad = kotlin.math.sqrt(1f - y * y)
            val th = golden * i + f.angle * 0.5f + f.yaw
            val x = cos(th) * rad
            val z0 = sin(th) * rad
            xs[i] = x
            ys[i] = y * cp - z0 * sp
            zs[i] = y * sp + z0 * cp
        }
        for (i in 0 until n) {
            val x = xs[i]
            val y = ys[i]
            val z = zs[i]
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
            for (j in i + 1 until minOf(i + 4, n)) {
                val qx = xs[j]
                val qy = ys[j]
                val dq = ((zs[j] + 1f) / 2f).pow(Spec.DEPTH_GAIN)
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

/**
 * Crystal growth: six-fold frost, climbing and receding.
 *
 * Deterministic despite looking organic. The branch positions and lengths come
 * from [hash01] on the segment index, so they are irregular but identical on
 * every run and on every device — which is what makes this face testable at
 * all, and is why it was ported ahead of the simulation-driven ones.
 *
 * The growth front sweeps out and resets rather than accumulating, so nothing
 * is remembered between frames. A crystal that genuinely accreted would need
 * per-frame state and would then differ between the phone and the desktop from
 * the moment either one dropped a frame.
 */
object Rime : Face {
    override val id = "rime"
    override val name = "Rime"

    private const val ARMS = 6
    private const val SEGMENTS = 14

    // Per-segment and identical for all six arms — frost is symmetric, which
    // is the whole reason these are hashed on `s` alone. They were recomputed
    // inside the inner loop, so the same 42 values were derived 6 times a
    // frame.
    private val wobBuf = FloatArray(SEGMENTS + 1) { (hash01(it * 37) - 0.5f) * 0.20f }
    private val branchBuf = FloatArray(SEGMENTS + 1) { hash01(it * 91 + 7) }
    private val lenBuf = FloatArray(SEGMENTS + 1) { hash01(it * 53) }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.7f
        FaceState.THINKING -> 1.9f
        FaceState.SPEAKING -> 1.15f
        else -> 0.34f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        // The hex plane is tilted by the drag, so this reads as a plate seen at
        // an angle rather than a flat snowflake sticker.
        val cp = cos(f.pitch)
        // How far the frost has climbed, 0..1, sawtooth. `angle` already
        // carries the state's speed multiplier, so the growth rate follows the
        // face's motion table without this needing to know the state.
        val front = ((f.angle * 0.12f) % 1f + 1f) % 1f
        val reach = 0.30f + 0.66f * front

        for (a in 0 until ARMS) {
            val base = a * (2f * PI.toFloat() / ARMS) + f.yaw + f.angle * 0.06f
            var prevX = cx
            var prevY = cy
            for (s in 1..SEGMENTS) {
                val k = s / SEGMENTS.toFloat()
                if (k > reach) break
                val rad = r * k * 0.94f
                // A slight per-segment wander, hashed on the segment rather
                // than on the arm, so all six arms stay congruent — frost is
                // symmetric, and six independently wandering arms read as a
                // scribble.
                val wob = wobBuf[s]
                val th = base + wob
                val x = cx + cos(th) * rad
                val y = cy + sin(th) * rad * cp
                // Depth from the tilt: the far half of the plate sits dimmer.
                val d = ((sin(th) * cp + 1f) / 2f).pow(Spec.DEPTH_GAIN)
                val fade = (1f - (k / reach).coerceIn(0f, 1f) * 0.45f)
                val ink = mix(cool, hot, d).copy(alpha = (0.30f + 0.70f * d) * fade)

                drawLine(
                    color = ink,
                    start = Offset(prevX, prevY),
                    end = Offset(x, y),
                    strokeWidth = r * (0.016f - 0.008f * k) * (1f + f.amp * 0.5f),
                )

                // Side branches, at the hexagonal 60 degrees, on segments the
                // hash selects. Length falls off outward so the tips look fine
                // rather than blunt.
                if (branchBuf[s] > 0.42f && s > 2) {
                    val blen = r * 0.16f * (1f - k) * (0.6f + 0.8f * lenBuf[s])
                    // A progression, not a fresh IntArray per segment per arm
                    // per frame — that was ~50 arrays a frame while Rime was on
                    // screen, for two values that never change.
                    for (sign in -1..1 step 2) {
                        val bth = th + sign * (PI.toFloat() / 3f)
                        drawLine(
                            color = ink.copy(alpha = ink.alpha * 0.8f),
                            start = Offset(x, y),
                            end = Offset(x + cos(bth) * blen, y + sin(bth) * blen * cp),
                            strokeWidth = r * 0.008f * (1f + f.amp * 0.4f),
                        )
                    }
                }
                prevX = x
                prevY = y
            }
        }

        // The seed, so the centre is not a hole while the frost is low.
        drawCircle(
            color = hot.copy(alpha = 0.55f),
            radius = r * (0.035f + 0.02f * f.amp),
            center = Offset(cx, cy),
        )
    }
}

/**
 * An electron probability cloud: a shell of points, denser where the orbital is.
 *
 * Stateless in the same way [Rime] is — point `i` has a fixed hashed position,
 * and time only rotates and breathes it. Two hashes give a direction and a
 * radius, and the radius is shaped by a lobe function so the cloud has the
 * pinched waist of a p-orbital rather than being a uniform fuzzy ball.
 *
 * The spec lists this face under `point_batch`, and this does **not** use
 * `drawPoints`. Batching there means building a `List<Offset>` per frame, which
 * boxes every point, and the measurement that would justify it has to happen on
 * the real panel rather than in a software-GL container. 240 `drawCircle` calls
 * is fewer draw operations than Fullerene already issues, so this is the
 * conservative choice until there is a device to measure on.
 */
object Orbital : Face {
    override val id = "orbital"
    override val name = "Orbital"

    private const val N = 240
    private val xBuf = FloatArray(N)
    private val yBuf = FloatArray(N)
    private val zBuf = FloatArray(N)

    // The three hashes depend only on the point index, and `hash01` is a
    // double-precision sin — the most expensive call in the draw path. They
    // were recomputed every frame: 720 of them, 43,200 a second, producing the
    // same 720 numbers each time. Computed once, alongside the buffers above
    // that established the pattern.
    private val uBuf = FloatArray(N) { hash01(it * 13 + 1) }
    private val vBuf = FloatArray(N) { hash01(it * 71 + 5) }
    private val rBuf = FloatArray(N) { hash01(it * 29 + 3) }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.8f
        FaceState.THINKING -> 2.2f
        FaceState.SPEAKING -> 1.25f
        else -> 0.4f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val cp = cos(f.pitch)
        val sp = sin(f.pitch)
        val spin = f.angle * 0.35f + f.yaw

        for (i in 0 until N) {
            // A fixed direction per point, from two hashes. The z term is
            // uniform in cos(theta) so the points spread evenly over the
            // sphere instead of bunching at the poles.
            val u = uBuf[i]
            val v = vBuf[i]
            val cosT = 1f - 2f * u
            val sinT = kotlin.math.sqrt((1f - cosT * cosT).coerceAtLeast(0f))
            val phi = v * 2f * PI.toFloat() + spin

            // The lobe: radius pinched at the equator and full at the poles, so
            // this reads as an orbital rather than a shell. Breathing on amp.
            val lobe = 0.45f + 0.55f * (cosT * cosT)
            val rr = lobe * (0.62f + 0.30f * rBuf[i]) * (1f + f.amp * 0.18f)

            val x0 = sinT * cos(phi) * rr
            val y0 = cosT * rr
            val z0 = sinT * sin(phi) * rr

            xBuf[i] = x0
            yBuf[i] = y0 * cp - z0 * sp
            zBuf[i] = y0 * sp + z0 * cp
        }

        for (i in 0 until N) {
            val d = ((zBuf[i] + 1f) / 2f).pow(Spec.DEPTH_GAIN)
            drawCircle(
                color = mix(cool, hot, d).copy(alpha = (0.18f + 0.72f * d)),
                radius = r * (0.006f + 0.014f * d) * (1f + f.amp * 0.35f),
                center = Offset(cx + xBuf[i] * r, cy + yBuf[i] * r),
            )
        }

        // The nucleus. Small, and the only thing in the face that is not a
        // cloud point, so the eye has somewhere to rest.
        drawCircle(
            color = hot.copy(alpha = 0.7f),
            radius = r * (0.028f + 0.022f * f.amp),
            center = Offset(cx, cy),
        )
    }
}
