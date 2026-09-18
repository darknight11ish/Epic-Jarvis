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
 * Eighteen faces, not twenty.
 *
 * The brief is explicit that porting all twenty is the real cost of going fully
 * native. Seventeen of these are from the spec's `stays_on_canvas` list — line,
 * stroke, point and glow art that Compose draws correctly and cheaply. The
 * eighteenth, nucleus, needs a real fragment shader and gets one (AGSL, via
 * `android.graphics.RuntimeShader`) rather than a rasterised approximation —
 * see its own doc comment. Membrane and tokamak are still absent: both need a
 * real OpenGL mesh (GLES 3.0, vertex and index buffers, per-vertex normals),
 * not a shader over the existing Canvas, which is a materially larger piece of
 * infrastructure this app has never had. A rasterised version of either is the
 * faceted, upscaled thing the first audit was about, and shipping it would be
 * worse than not offering them. That mesh pipeline, and those two faces, are
 * tracked as their own follow-up, not something to finish here as a side
 * effect of another task.
 *
 * The picker shows only what is actually rendered — not all twenty with most of
 * them missing.
 *
 * Rime, Orbital, Geodesic and Kirkwood are stateless outright: the spec marks
 * them `integrates_per_frame: false`, meaning a pure function of `t`, which
 * means the result COULD be pinned by a golden test the way the pattern
 * engine is — though as of this writing no face's geometry has one; only
 * `Resolve.kt`'s colours do (`PatternGoldenTest`).
 *
 * Spectrum, Coreplate, Workbench, Swarm, Shoal, Accretion and Cascade are a
 * different case, and it is worth being honest about which. The spec marks
 * all seven `integrates_per_frame: true` because their JS/desktop reference
 * genuinely does carry state between frames — a running FFT smoother, boid
 * velocities, a DLA grid, a live particle list. None of that was ported here.
 * Each one is instead reimplemented as a deterministic function of `t`, a
 * fixed per-element seed (`hash01` or a seeded `Random`), and `f.amp` — which
 * is already smoothed upstream by `FaceHost.advance()`, so there is no
 * envelope left to track locally. Nothing here is appended to, removed from,
 * or nudged by its own last frame; call `draw` with the same `(t, amp)` twice
 * and it draws the same picture twice. That makes these seven exactly as
 * pinnable as Rime and Kirkwood, even though the spec's flag — describing the
 * *reference's* technique, not this port's — says otherwise. See
 * `SpecDriftTest`'s `iris is the only offered face that cannot be pinned`
 * for where that distinction is enforced and argued in more detail.
 */
object Faces {
    val all: List<Face> = listOf(
        Arc, Orbit, Comb, Spiral, Iris, Fullerene, Rime, Orbital, Geodesic, Kirkwood,
        Spectrum, Coreplate, Workbench, Swarm, Shoal, Accretion, Cascade, Nucleus,
    )
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

/**
 * Subdivided icosahedron, lit by a wave travelling across the surface.
 *
 * The reference subdivides each icosahedral face once (42 vertices, three
 * wave origins on `thinking`) and swaps that count per state. This port uses
 * the plain icosahedron (12 vertices, 30 edges — every vertex degree 5) and
 * one wave origin: `speedFor` carries the per-state difference instead, the
 * same simplification every other 3D face here already makes rather than
 * re-deriving geometry per state. Brightness is computed against the
 * UNROTATED vertex positions, same as the reference — the wave lives on the
 * object, not the camera, so it must not depend on how the sphere is turned.
 */
object Geodesic : Face {
    override val id = "geodesic"
    override val name = "Geodesic"

    private val verts: Array<FloatArray> = run {
        val phi = (1f + kotlin.math.sqrt(5f)) / 2f
        arrayOf(
            floatArrayOf(-1f, phi, 0f), floatArrayOf(1f, phi, 0f),
            floatArrayOf(-1f, -phi, 0f), floatArrayOf(1f, -phi, 0f),
            floatArrayOf(0f, -1f, phi), floatArrayOf(0f, 1f, phi),
            floatArrayOf(0f, -1f, -phi), floatArrayOf(0f, 1f, -phi),
            floatArrayOf(phi, 0f, -1f), floatArrayOf(phi, 0f, 1f),
            floatArrayOf(-phi, 0f, -1f), floatArrayOf(-phi, 0f, 1f),
        ).map { v ->
            val len = kotlin.math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
            floatArrayOf(v[0] / len, v[1] / len, v[2] / len)
        }.toTypedArray()
    }

    // The 20 triangular faces of the icosahedron, walked once to derive the 30
    // unique edges — a hand-typed edge list could silently miss or duplicate
    // one and nothing would catch it, since there is no golden test for any
    // face's geometry, only for the colour engine (see PatternGoldenTest).
    private val edges: Array<IntArray> = run {
        val faces = arrayOf(
            intArrayOf(0, 11, 5), intArrayOf(0, 5, 1), intArrayOf(0, 1, 7),
            intArrayOf(0, 7, 10), intArrayOf(0, 10, 11), intArrayOf(1, 5, 9),
            intArrayOf(5, 11, 4), intArrayOf(11, 10, 2), intArrayOf(10, 7, 6),
            intArrayOf(7, 1, 8), intArrayOf(3, 9, 4), intArrayOf(3, 4, 2),
            intArrayOf(3, 2, 6), intArrayOf(3, 6, 8), intArrayOf(3, 8, 9),
            intArrayOf(4, 9, 5), intArrayOf(2, 4, 11), intArrayOf(6, 2, 10),
            intArrayOf(8, 6, 7), intArrayOf(9, 8, 1),
        )
        val seen = HashSet<Int>()
        val out = ArrayList<IntArray>()
        for (tri in faces) {
            for (k in 0 until 3) {
                val a = tri[k]
                val b = tri[(k + 1) % 3]
                val lo = minOf(a, b)
                val hi = maxOf(a, b)
                val key = lo * 100 + hi
                if (seen.add(key)) out.add(intArrayOf(lo, hi))
            }
        }
        out.toTypedArray()
    }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.7f
        FaceState.THINKING -> 1.7f
        FaceState.SPEAKING -> 0.9f
        else -> 0.4f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val n = verts.size
        val xs = FloatArray(n)
        val ys = FloatArray(n)
        val depth = FloatArray(n)
        val cp = cos(f.pitch)
        val sp = sin(f.pitch)
        val cyw = cos(f.angle + f.yaw)
        val syw = sin(f.angle + f.yaw)
        for (i in 0 until n) {
            val v = verts[i]
            val x0 = v[0] * cyw - v[2] * syw
            val z0 = v[0] * syw + v[2] * cyw
            xs[i] = x0
            ys[i] = v[1] * cp - z0 * sp
            val z = v[1] * sp + z0 * cp
            depth[i] = ((z + 1f) / 2f).pow(Spec.DEPTH_GAIN)
        }

        // One wave origin orbiting the sphere on the unrotated object; a
        // travelling pulse lights whatever vertex it is currently passing.
        val rate = 0.6f
        val originAngle = f.t * rate * 0.6f
        val ox = cos(originAngle)
        val oy = sin(originAngle * 0.7f)
        val oz = sin(originAngle)
        val bright = FloatArray(n)
        for (i in 0 until n) {
            val v = verts[i]
            val dx = v[0] - ox
            val dy = v[1] - oy
            val dz = v[2] - oz
            val d = kotlin.math.sqrt(dx * dx + dy * dy + dz * dz) / 2f
            var ph = (f.t * rate - d * 2.2f) % 2f
            if (ph < 0f) ph += 2f
            bright[i] = if (ph < 1f) (sin(ph * PI.toFloat())).coerceAtLeast(0f) else 0f
        }
        val ampBoost = (f.amp * 0.3f).coerceAtMost(0.3f)

        for (edge in edges) {
            val i = edge[0]
            val j = edge[1]
            val d = (depth[i] + depth[j]) / 2f
            val b = ((bright[i] + bright[j]) / 2f + ampBoost).coerceAtMost(1f)
            drawLine(
                color = (if (b > 0.25f) mix(cool, hot, b) else cool)
                    .copy(alpha = (0.05f + (d - 0.55f).coerceAtLeast(0f) * 1.5f) * (0.35f + b * 1.6f)),
                start = Offset(cx + xs[i] * r, cy + ys[i] * r),
                end = Offset(cx + xs[j] * r, cy + ys[j] * r),
                strokeWidth = r * (0.006f + 0.012f * b) * d.coerceAtLeast(0.2f),
            )
        }
        for (i in 0 until n) {
            val b = bright[i]
            if (b < 0.05f && depth[i] < 0.85f) continue
            drawCircle(
                color = (if (b > 0.3f) hot else cool).copy(alpha = (0.18f + b * 0.82f).coerceAtMost(1f)),
                radius = r * (0.02f + 0.05f * b) * depth[i].coerceAtLeast(0.3f),
                center = Offset(cx + xs[i] * r, cy + ys[i] * r),
            )
        }
    }
}

/**
 * The Kirkwood gaps: an asteroid belt cleared by resonance with a shepherd
 * body ("Jupiter"), not evenly filled.
 *
 * Positions are a fixed, seeded layout — semi-major axis, eccentricity,
 * phase, a scatter for depth — generated once so the belt is identical every
 * time this face is picked rather than reshuffling. Only each rock's ANGLE
 * advances with time, the same way the reference's own random layout is
 * generated once and cached (`this.rocks`) despite the spec marking this face
 * `integrates_per_frame: false`: the cache is a frozen layout, not evolving
 * simulation state.
 *
 * Depth comes from Orbit's own squashed-ellipse technique in this file, not a
 * real camera pitch: this is a flat belt seen at an angle, not a point cloud
 * on a sphere, so Fullerene's rotation does not apply here.
 */
object Kirkwood : Face {
    override val id = "kirkwood"
    override val name = "Kirkwood"

    private const val N = 420
    private const val JUPITER_A = 1.32f

    // a = aJupiter * ratio^(-2/3) — Kepler's third law, solved for the radius
    // that shares Jupiter's orbital period times a simple fraction. A member
    // function, not a file-level one, so it reads JUPITER_A directly instead
    // of a second copy of the same literal that could drift from this one.
    private fun gapAt(ratio: Float): Float = JUPITER_A * ratio.pow(-2f / 3f)

    private val gaps = floatArrayOf(gapAt(3f), gapAt(5f / 2f), gapAt(2f))

    // Fixed per-rock layout, seeded so it never reshuffles between draws.
    private val rockA = FloatArray(N)
    private val rockE = FloatArray(N)
    private val rockPhase = FloatArray(N)
    private val rockDepthSeed = FloatArray(N)
    private val rockSize = FloatArray(N)

    init {
        val rnd = kotlin.random.Random(20260913)
        for (i in 0 until N) {
            rockA[i] = 0.45f + rnd.nextFloat() * 0.55f
            rockE[i] = rnd.nextFloat() * 0.10f
            rockPhase[i] = rnd.nextFloat() * PI2
            rockDepthSeed[i] = (rnd.nextFloat() - 0.5f) * 0.10f
            rockSize[i] = rnd.nextFloat()
        }
    }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.5f
        FaceState.THINKING -> 1.4f
        FaceState.SPEAKING -> 0.6f
        else -> 0.3f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        for (i in 0 until N) {
            val a = rockA[i]
            var clear = 1f
            for (gap in gaps) {
                val dd = kotlin.math.abs(a - gap)
                clear = minOf(clear, (dd / 0.045f).coerceIn(0f, 1f))
            }
            if (clear < 0.06f) continue

            // Kepler: inner orbits move faster.
            val om = a.pow(-1.5f)
            val ang = rockPhase[i] + f.angle * om + f.yaw
            val rr = a * (1f - rockE[i] * cos(ang * 2f))
            val x = cos(ang) * rr
            // Squashed, like Orbit's own belt: y for the ellipse, a separate
            // depth term (never read for position) for size and alpha only.
            val y = sin(ang) * rr * 0.32f
            val z = sin(ang) * 0.32f + rockDepthSeed[i]
            val d = ((z + 1f) / 2f).pow(Spec.DEPTH_GAIN)
            val bright = if (rockSize[i] > 0.9f) hot else cool
            drawCircle(
                color = bright.copy(alpha = ((0.18f + rockSize[i] * 0.5f) * clear * d).coerceIn(0f, 1f)),
                radius = (r * 0.0035f * d * (0.4f + rockSize[i])).coerceAtLeast(0.5f),
                center = Offset(cx + x * r, cy + y * r),
            )
        }

        // The sun, and Jupiter itself doing the clearing.
        drawCircle(
            color = lift(hot, 0.35f).copy(alpha = 0.85f),
            radius = r * 0.09f,
            center = Offset(cx, cy),
        )
        val ja = f.angle * JUPITER_A.pow(-1.5f) + f.yaw
        val jx = cos(ja) * JUPITER_A
        val jy = sin(ja) * JUPITER_A * 0.32f
        drawCircle(
            color = hot,
            radius = r * 0.032f,
            center = Offset(cx + jx * r, cy + jy * r),
        )
    }
}

/**
 * Thirty-two bars in a ring, each a pure function of its own index, the
 * clock and the current drive — no persisted per-bar smoothing.
 *
 * The reference lerps each bar toward a per-state target every frame
 * (`this.bands[i] = lerp(...)`), which is the one piece of real memory in an
 * otherwise stateless face. `f.amp` arrives here already smoothed — attack
 * and release envelopes are applied once, upstream, in `FaceHost` — so a
 * second smoothing layer on top of an already-smooth input would have added
 * nothing but state. Height is a direct function of `(i, t, amp)` instead,
 * which keeps this face out of the set `SpecDriftTest` pins as unverifiable
 * — a genuine simplification from the reference, not a workaround of it.
 */
object Spectrum : Face {
    override val id = "spectrum"
    override val name = "Spectrum"

    private const val N = 32

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.0f
        FaceState.THINKING -> 2.4f
        FaceState.SPEAKING -> 1.3f
        else -> 0.5f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val incl = 0.55f
        val ci = cos(incl)
        val si = sin(incl)
        for (i in 0 until N) {
            val a = i / N.toFloat() * PI2 + f.angle * 0.35f + f.yaw
            val ambient = 0.10f + 0.08f * sin(f.t * 0.9f + i * 0.5f)
            val reactive = f.amp * (0.4f + 0.6f * kotlin.math.abs(sin(i * 0.7f + f.t * 3f)))
            val height = (ambient + reactive).coerceIn(0.05f, 1.1f)
            val bx = cos(a) * r
            val bz = sin(a) * si
            val d = ((bz + 1f) / 2f).pow(Spec.DEPTH_GAIN)
            val baseY = sin(a) * r * ci
            val topY = baseY - height * r * 0.6f * d.coerceAtLeast(0.35f)
            drawLine(
                color = mix(cool, hot, height.coerceAtMost(1f)).copy(
                    alpha = (0.2f + d * 0.7f).coerceAtMost(1f),
                ),
                start = Offset(cx + bx, cy + baseY),
                end = Offset(cx + bx, cy + topY),
                strokeWidth = (r * 0.028f * d.coerceAtLeast(0.3f)).coerceAtLeast(1.5f),
            )
        }
    }
}

/**
 * A power cell with its lid off: coaxial plates and a helical winding.
 *
 * The reference eases plate separation toward a per-state target every frame
 * (`this.sepNow = lerp(...)`) — the one piece of memory in it; the winding's
 * travelling current was already a pure function of `t`. Separation here is
 * a direct function of `f.amp` instead, for the same reason as Spectrum.
 */
object Coreplate : Face {
    override val id = "coreplate"
    override val name = "Coreplate"

    private val rings = floatArrayOf(0.82f, 0.66f, 0.50f, 0.32f)
    private val counts = intArrayOf(24, 32, 14, 8)

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.9f
        FaceState.THINKING -> 2.1f
        FaceState.SPEAKING -> 1.2f
        else -> 0.45f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val sep = 0.06f + f.amp * 0.22f
        for (ri in rings.indices) {
            val rr = rings[ri] * r
            val n = counts[ri]
            val off = (ri - 1.5f) * sep * r
            for (i in 0 until n) {
                if (i % 2 == 1) continue // dashed, like the reference's plates
                val a0 = i / n.toFloat() * PI2 + f.angle * 0.2f
                val a1 = (i + 1) / n.toFloat() * PI2 + f.angle * 0.2f
                drawLine(
                    color = mix(cool, hot, 0.3f).copy(alpha = 0.5f),
                    start = Offset(cx + cos(a0) * rr, cy + off * 0.35f + sin(a0) * rr * 0.12f),
                    end = Offset(cx + cos(a1) * rr, cy + off * 0.35f + sin(a1) * rr * 0.12f),
                    strokeWidth = r * 0.02f,
                )
            }
        }
        // Helical winding: a travelling current, already stateless in the
        // reference — a sharp pulse from an even power, rather than the
        // reference's max(0, sin)^5, which needs no separate clamp.
        val turns = 7
        val segs = 90
        fun point(u: Float): Offset {
            val ang = u * PI2 * turns
            val rr = (0.46f + 0.05f * sin(u * PI2 * 3f)) * r
            val y = (-0.2f + u * 0.42f) * sep * r * 4f
            return Offset(cx + cos(ang) * rr, cy + y + sin(ang) * rr * 0.12f)
        }
        for (k in 0 until segs) {
            val u0 = k / segs.toFloat()
            val u1 = (k + 1) / segs.toFloat()
            val s = sin(u0 * PI2 * 2f - f.t * 2.2f)
            val flow = s * s * s * s
            drawLine(
                color = mix(hot, Color.White, flow.coerceIn(0f, 1f)),
                start = point(u0),
                end = point(u1),
                strokeWidth = (r * 0.008f * (1f + flow * 2f)).coerceAtLeast(0.6f),
            )
        }
        drawCircle(
            color = hot.copy(alpha = 0.5f + 0.4f * f.amp),
            radius = r * (0.05f + 0.02f * sin(f.t * 4f)),
            center = Offset(cx, cy),
        )
    }
}

/**
 * An assembly exploded in mid-air, with a scan plane sweeping through it.
 *
 * The reference eases shell separation toward a per-state target every
 * frame — the same one piece of memory Coreplate's plates have — and the
 * scan plane was already a pure function of `t`. Separation here is a
 * direct function of `f.amp`, matching Coreplate and Spectrum's note.
 */
object Workbench : Face {
    override val id = "workbench"
    override val name = "Workbench"

    private val shells = floatArrayOf(0.68f, 0.52f, 0.36f, 0.20f)
    private val counts = intArrayOf(16, 12, 8, 6)

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.8f
        FaceState.THINKING -> 1.9f
        FaceState.SPEAKING -> 1.0f
        else -> 0.4f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val sep = 0.10f + f.amp * 0.35f
        val scanY = sin(f.t * 0.6f) * r * 0.7f
        for (si in shells.indices) {
            val rr = shells[si] * r
            val off = (si - 1.5f) * sep * r
            val n = counts[si]
            for (i in 0 until n) {
                val a = i / n.toFloat() * PI2 + f.angle * 0.15f
                val x = cx + cos(a) * rr
                val yTop = cy + off - rr * 0.3f
                val yBot = cy + off + rr * 0.3f
                val mid = (yTop + yBot) / 2f - cy
                val e = (mid - scanY) / (r * 0.18f)
                val lit = kotlin.math.exp(-(e * e))
                drawLine(
                    color = mix(cool, hot, lit.coerceIn(0f, 1f)).copy(
                        alpha = (0.2f + lit * 0.8f).coerceAtMost(1f),
                    ),
                    start = Offset(x, yTop),
                    end = Offset(x, yBot),
                    strokeWidth = (r * 0.012f * (1f + lit * 1.5f)).coerceAtLeast(0.7f),
                )
            }
        }
        drawLine(
            color = hot.copy(alpha = 0.18f),
            start = Offset(cx - r * 0.75f, cy + scanY),
            end = Offset(cx + r * 0.75f, cy + scanY),
            strokeWidth = r * 0.01f,
        )
    }
}

/**
 * Two hundred agents that read as a cloud moving together, and pull tighter
 * while listening.
 *
 * The reference integrates real velocity and position every frame — each
 * agent remembers where it was a moment ago. Here every agent instead
 * follows a fixed, closed path parametrized directly by `t` and the agent's
 * own fixed phase (seeded once at startup, the same way Kirkwood's rocks
 * are): the cloud still reads as many small bodies moving together, and
 * `f.amp` tightens the radius the way "listening pulls the swarm into a
 * ball" did in the reference — without a frame of memory anywhere. This is
 * not a flocking simulation; it is chosen specifically so this face stays
 * out of the set `SpecDriftTest` pins as unverifiable.
 */
object Swarm : Face {
    override val id = "swarm"
    override val name = "Swarm"

    private const val N = 160
    private val seedA = FloatArray(N) { hash01(it * 7 + 1) * PI2 }
    private val seedB = FloatArray(N) { hash01(it * 13 + 3) * PI2 }
    private val seedR = FloatArray(N) { 0.3f + hash01(it * 19 + 5) * 0.7f }
    private val seedSize = FloatArray(N) { hash01(it * 29 + 11) }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.1f
        FaceState.THINKING -> 2.3f
        FaceState.SPEAKING -> 1.4f
        else -> 0.5f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val cp = cos(f.pitch)
        val sp = sin(f.pitch)
        val pull = (1f - f.amp * 0.6f).coerceIn(0.35f, 1f)
        for (i in 0 until N) {
            val orbit = f.t * (0.3f + seedR[i] * 0.2f) + seedA[i]
            val wob = f.t * (0.6f + seedR[i] * 0.4f) + seedB[i]
            val rr = seedR[i] * pull
            val x0 = cos(orbit) * rr
            val y0 = sin(wob) * rr * 0.7f
            val z0 = sin(orbit) * rr
            val x = x0 * cos(f.yaw) - z0 * sin(f.yaw)
            val z1 = x0 * sin(f.yaw) + z0 * cos(f.yaw)
            val y = y0 * cp - z1 * sp
            val z = y0 * sp + z1 * cp
            val d = ((z + 1f) / 2f).pow(Spec.DEPTH_GAIN)
            drawCircle(
                color = mix(cool, hot, d).copy(alpha = (0.25f + d * 0.65f).coerceAtMost(1f)),
                radius = (r * 0.012f * d.coerceAtLeast(0.25f) * (0.5f + seedSize[i])).coerceAtLeast(0.6f),
                center = Offset(cx + x * r, cy + y * r),
            )
        }
    }
}

/**
 * A schooling sheet that flashes as it wheels — orientation catching the
 * light is the visual idea, not the school's shape.
 *
 * Like Swarm, agents follow a fixed path parametrized by `t` and a per-agent
 * seed rather than an integrated simulation, for the same reason.
 */
object Shoal : Face {
    override val id = "shoal"
    override val name = "Shoal"

    private const val N = 140
    private val seedA = FloatArray(N) { hash01(it * 17 + 2) * PI2 }
    private val seedR = FloatArray(N) { 0.35f + hash01(it * 23 + 6) * 0.65f }
    private val seedSize = FloatArray(N) { hash01(it * 31 + 9) }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.0f
        FaceState.THINKING -> 2.0f
        FaceState.SPEAKING -> 1.2f
        else -> 0.5f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val pull = (1f - f.amp * 0.35f).coerceIn(0.55f, 1f)
        for (i in 0 until N) {
            val orbit = f.t * (0.35f + seedR[i] * 0.25f) + seedA[i] + f.yaw
            val rr = seedR[i] * pull * r
            val bx = cos(orbit) * rr
            val by = sin(orbit * 0.6f) * rr * 0.5f
            // Heading from the derivative of the path above, so the body
            // always points the way it is actually moving.
            val vx = -sin(orbit)
            val vy = cos(orbit * 0.6f) * 0.36f
            val vlen = kotlin.math.sqrt(vx * vx + vy * vy).coerceAtLeast(1e-4f)
            val len = r * 0.045f * (0.6f + seedSize[i])
            val hx = vx / vlen * len
            val hy = vy / vlen * len
            val flash = kotlin.math.abs(sin(orbit * 1.7f + seedA[i]))
            val d = 0.6f + 0.4f * cos(orbit)
            drawLine(
                color = mix(cool, hot, flash).copy(alpha = (0.35f + d * 0.5f).coerceAtMost(1f)),
                start = Offset(cx + bx - hx, cy + by - hy),
                end = Offset(cx + bx + hx, cy + by + hy),
                strokeWidth = (len * 0.6f).coerceAtLeast(1f),
            )
        }
    }
}

/**
 * A branching structure that grows outward from a seed.
 *
 * The reference genuinely grows a diffusion-limited-aggregation cluster one
 * random walker at a time — real per-frame state, and an unbounded one at
 * that (a grid that fills over minutes of uptime). This uses Rime's own
 * technique instead: deterministic, hash-seeded branches, revealed
 * progressively as a function of `t` and cycling rather than accumulating —
 * the exact choice Rime's own comment already explains for crystal growth,
 * applied here to an asymmetric, coral-like branch pattern instead of Rime's
 * clean six-fold one.
 */
object Accretion : Face {
    override val id = "accretion"
    override val name = "Accretion"

    private const val ARMS = 5
    private const val SEGMENTS = 22

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.9f
        FaceState.THINKING -> 2.0f
        FaceState.SPEAKING -> 1.1f
        else -> 0.4f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        // Cycles out and resets rather than accumulating forever — the same
        // choice Rime makes, for the same reason.
        val grown = (0.4f + 0.5f * (0.5f + 0.5f * sin(f.t * 0.25f)) + f.amp * 0.15f).coerceIn(0f, 1f)
        for (arm in 0 until ARMS) {
            val armSeed = arm * 71 + 3
            var px = cx
            var py = cy
            var ang = hash01(armSeed) * PI2 + f.angle * 0.1f
            for (seg in 0 until SEGMENTS) {
                val f01 = seg / (SEGMENTS - 1f)
                if (f01 > grown) break
                val h = hash01(armSeed + seg * 13)
                ang += (h - 0.5f) * 0.7f
                val step = r * 0.045f * (1f - f01 * 0.3f)
                val nx = px + cos(ang) * step
                val ny = py + sin(ang) * step
                val bright = 1f - f01
                drawLine(
                    color = mix(cool, hot, bright).copy(alpha = (0.35f + bright * 0.5f).coerceAtMost(1f)),
                    start = Offset(px, py),
                    end = Offset(nx, ny),
                    strokeWidth = (r * 0.012f * (1f - f01 * 0.5f)).coerceAtLeast(0.7f),
                )
                if (hash01(armSeed + seg * 29 + 5) > 0.72f) {
                    val side = if (hash01(armSeed + seg * 41) > 0.5f) 1f else -1f
                    val bAng = ang + side * 0.9f
                    val blen = step * 1.6f
                    drawLine(
                        color = mix(cool, hot, bright * 0.7f).copy(alpha = (0.2f + bright * 0.35f).coerceAtMost(1f)),
                        start = Offset(nx, ny),
                        end = Offset(nx + cos(bAng) * blen, ny + sin(bAng) * blen),
                        strokeWidth = r * 0.006f,
                    )
                }
                px = nx
                py = ny
            }
        }
        drawCircle(hot.copy(alpha = 0.7f), r * 0.02f, Offset(cx, cy))
    }
}

/**
 * Water leaving a lip as a sheet, breaking into falling parcels lower down.
 *
 * The reference is a genuine particle system — added at the top, updated by
 * drag and gravity, removed at the bottom — which is real per-frame state,
 * and an unbounded list at that. Each parcel here instead follows a fixed
 * vertical fall cycle keyed to its own seed, `(t*speed + seed) mod 1`, so it
 * recycles forever with no list to grow or shrink: the standard
 * deterministic-rain technique, applied for the same reason Rime and
 * Accretion use one.
 */
object Cascade : Face {
    override val id = "cascade"
    override val name = "Cascade"

    private const val N = 260
    private val seedX = FloatArray(N) { hash01(it * 11 + 1) }
    private val seedPhase = FloatArray(N) { hash01(it * 41 + 7) }
    private val seedSize = FloatArray(N) { hash01(it * 53 + 13) }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.1f
        FaceState.THINKING -> 2.2f
        FaceState.SPEAKING -> 1.3f
        else -> 0.6f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val flowRate = 0.5f + f.amp * 0.4f
        val topY = cy - r * 0.85f
        val botY = cy + r * 0.85f
        for (i in 0 until N) {
            var phase = (f.t * (0.7f + flowRate) + seedPhase[i]) % 1f
            if (phase < 0f) phase += 1f
            val x = cx + (seedX[i] - 0.5f) * r * 0.9f
            // Squared phase, not linear: covers more distance per unit phase
            // near the bottom than the top, the way a real fall accelerates.
            val eased = phase * phase
            val y = topY + eased * (botY - topY)
            val fade = (1f - phase) * 0.6f + 0.4f
            val half = r * 0.02f * (0.5f + seedSize[i])
            drawLine(
                color = mix(hot, cool, phase * 0.5f).copy(alpha = (fade * 0.7f).coerceAtMost(1f)),
                start = Offset(x, y - half),
                end = Offset(x, y + half),
                strokeWidth = (r * 0.006f * (0.5f + seedSize[i])).coerceAtLeast(0.6f),
            )
        }
        drawLine(
            color = hot.copy(alpha = 0.6f),
            start = Offset(cx - r * 0.3f, topY),
            end = Offset(cx + r * 0.3f, topY),
            strokeWidth = r * 0.02f,
        )
        drawCircle(
            color = hot.copy(alpha = 0.15f),
            radius = r * 0.5f,
            center = Offset(cx, botY),
        )
    }
}

/**
 * A sphere-traced signed distance field: a core, an equatorial ring and three
 * orbiting beads, blended together as maths (`smin`, a polynomial smooth
 * minimum) before anything is drawn, so they melt into each other rather
 * than intersect. There is no mesh - every pixel fires a ray, walks it
 * forward by the distance to the nearest surface until it lands, and shades
 * from the field's own gradient at that point. That is genuinely too much
 * work per pixel for the CPU path every other face in this file uses, which
 * is why this is the one face rendered through a real fragment shader (AGSL,
 * via `android.graphics.RuntimeShader`) instead of `DrawScope` draw calls.
 * `RuntimeShader` needs API 33, which is already this app's `minSdk` - there
 * is no older device to fall back from.
 *
 * The march, the field and the lighting are a close port of the reference's
 * own GPU shader (`NUCLEUS_FS` in the desktop's `faces.html`). Unlike the
 * object-rotation faces elsewhere in this file, a ray-based camera needs its
 * origin and its ray directions built from the exact same rotation, so this
 * keeps the reference's own pitch-then-yaw camera formula rather than
 * reordering it to match Geodesic's yaw-then-pitch convention - getting that
 * order right by inspection, with no way to render this and look at it
 * before it ships, mattered more here than file-wide consistency. `uYaw` and
 * `uPit` still feed from `f.angle`, `f.yaw` and `f.pitch` the same way every
 * other 3D face here does, and the screen-to-object-space mapping is redone
 * for a circle (`(fragCoord - uCenter) / uR`) rather than ported from the
 * reference's square canvas (`(fragCoord - 0.5*res) / min(res.x, res.y)`) -
 * the two are the same normalisation for the shape this app actually draws.
 *
 * Three things ARE dropped, and none of them is the rotation question:
 *  - `HUD.beat`, a global heartbeat pulse with nothing this app tracks to
 *    drive it. It only ever scaled the field's blend radii; at a fixed 1 the
 *    `M()` wrapper the reference uses to apply it becomes the identity, so
 *    this calls `field()` directly and the wrapper is gone rather than kept
 *    around multiplying by one.
 *  - The reference's environment-reflection texture. There is no panorama to
 *    sample on a phone, so this always takes the reference's own fallback
 *    tone (`vec3(22,24,30)/255`) rather than adding a texture uniform that
 *    would only ever return that one constant anyway.
 *  - The reference's own hardcoded per-state glow/hot colours. Every other
 *    face in this file shades with the `hot`/`cool` this call is handed -
 *    the user's own chosen binding for the current state - and a face that
 *    quietly used its own fixed palette instead would be the one face immune
 *    to the colour picker. Geometry (the blend/ring/displacement numbers,
 *    which have no user-facing control) keeps the reference's own per-state
 *    table; colour does not.
 */
object Nucleus : Face {
    override val id = "nucleus"
    override val name = "Nucleus"

    // faces[].render.fit for nucleus specifically - the shape reads slightly
    // larger than its bounding sphere once the rim light is added.
    override val fit: Float = 0.92f

    private data class Geo(val blend: Float, val ring: Float, val disp: Float)

    private fun geoFor(motion: FaceState): Geo = when (motion) {
        FaceState.LISTENING -> Geo(blend = 0.20f, ring = 0.88f, disp = 0.11f)
        FaceState.THINKING -> Geo(blend = 0.07f, ring = 1.05f, disp = 0.19f)
        FaceState.SPEAKING -> Geo(blend = 0.17f, ring = 0.90f, disp = 0.08f)
        else -> Geo(blend = 0.13f, ring = 0.95f, disp = 0.05f)
    }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.1f
        FaceState.THINKING -> 2.0f
        FaceState.SPEAKING -> 0.8f
        else -> 0.5f
    }

    // Compiled once, like every other fixed per-face resource in this file -
    // only the uniforms change per frame.
    private val shader = android.graphics.RuntimeShader(AGSL)

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val geo = geoFor(f.motion)
        val pump = if (f.motion == FaceState.LISTENING) 1f + f.amp * 0.35f else 1f
        val yaw = f.angle * 0.35f + f.yaw
        val pitch = -0.52f + f.pitch

        shader.setFloatUniform("uCenter", cx, cy)
        shader.setFloatUniform("uR", r)
        shader.setFloatUniform("uT", f.angle)
        shader.setFloatUniform("uBlend", geo.blend)
        shader.setFloatUniform("uRing", geo.ring)
        shader.setFloatUniform("uDisp", geo.disp)
        shader.setFloatUniform("uPump", pump)
        shader.setFloatUniform("uYaw", yaw)
        shader.setFloatUniform("uPit", pitch)
        shader.setFloatUniform("uGlow", cool.red, cool.green, cool.blue)
        shader.setFloatUniform("uHot", hot.red, hot.green, hot.blue)

        drawCircle(
            brush = androidx.compose.ui.graphics.ShaderBrush(shader),
            radius = r,
            center = Offset(cx, cy),
        )
    }

    private const val AGSL = """
uniform float2 uCenter;
uniform float uR;
uniform float uT, uBlend, uRing, uDisp, uPump, uYaw, uPit;
uniform float3 uGlow, uHot;

const float TAU = 6.283185307179586;
const float3 LIGHT = float3(-0.4510, -0.7517, -0.4812);
const float DIST = 2.05;
const int STEPS = 72;

float fres3(float vdot) {
    float m = 1.0 - clamp(vdot, 0.0, 1.0);
    return m * m * m;
}

float3 tonemap(float3 c) {
    return c / (1.0 + c);
}

float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return b + (a - b) * h - k * h * (1.0 - h);
}

// Distance to the nearest surface: core, equatorial ring and three orbiting
// beads, folded together with a smooth minimum so they fuse rather than
// intersect. Everything the march and the lighting know about the shape
// comes from this one function.
float field(float3 q) {
    float disp = uDisp * sin(q.y * 6.0 + uT * 2.1) * sin(q.x * 5.0 - uT * 1.7) * sin(q.z * 5.5 + uT * 1.3);
    float core = length(q) - (0.50 + disp);
    float qx = length(q.xz) - uRing;
    float ring = length(float2(qx, q.y)) - 0.105;
    float d = smin(core, ring, uBlend);
    for (int i = 0; i < 3; i++) {
        float a = uT * 0.9 + float(i) * TAU / 3.0;
        float3 b = float3(cos(a) * 0.74, sin(a * 2.0) * 0.34, sin(a) * 0.74);
        d = smin(d, length(q - b) - 0.105, 0.22);
    }
    return d;
}

float3 normalAt(float3 h) {
    float e = 0.0045;
    float m1 = field(h + float3( e, -e, -e));
    float m2 = field(h + float3(-e, -e,  e));
    float m3 = field(h + float3(-e,  e, -e));
    float m4 = field(h + float3( e,  e,  e));
    return normalize(float3(m1 - m2 - m3 + m4, -m1 - m2 + m3 + m4, -m1 + m2 - m3 + m4));
}

half4 main(float2 fragCoord) {
    float2 p = (fragCoord - uCenter) / uR;
    float3 dir = normalize(float3(p, 1.55));

    float cp = cos(uPit), sp = sin(uPit), cy = cos(uYaw), sy = sin(uYaw);
    float ry1 = dir.y * cp - dir.z * sp;
    float rz1 = dir.y * sp + dir.z * cp;
    float3 rd = float3(dir.x * cy + rz1 * sy, ry1, -dir.x * sy + rz1 * cy);
    float3 ro = float3(-DIST * cp * sy, DIST * sp, -DIST * cp * cy);

    float BR = 1.28;
    float b0 = dot(ro, rd);
    float cc = dot(ro, ro) - BR * BR;
    float disc = b0 * b0 - cc;
    if (disc < 0.0) {
        return half4(0.0, 0.0, 0.0, 0.0);
    }
    float sq = sqrt(disc);
    float tt = max(0.0, -b0 - sq);
    float tMax = -b0 + sq;

    float hit = -1.0;
    int steps = 0;
    for (int i = 0; i < STEPS; i++) {
        float ds = field(ro + rd * tt);
        steps = i;
        if (ds < 0.0015) { hit = tt; break; }
        tt += ds;
        if (tt > tMax) break;
    }
    if (hit < 0.0) {
        return half4(0.0, 0.0, 0.0, 0.0);
    }

    float3 hp = ro + rd * hit;
    float3 n = normalAt(hp);
    float lam = max(0.0, -dot(n, LIGHT));
    float3 env = float3(22.0, 24.0, 30.0) / 255.0;
    float fres = fres3(abs(dot(n, rd)));
    float ao = 1.0 - min(0.75, float(steps) / float(STEPS) * 1.5);

    float sh = 1.0;
    float ts = 0.035;
    for (int i = 0; i < 20; i++) {
        float3 sp2 = hp - LIGHT * ts;
        float hd = field(sp2);
        if (hd < 0.001) { sh = 0.0; break; }
        sh = min(sh, 9.0 * hd / ts);
        ts += max(0.02, hd);
        if (ts > 2.2) break;
    }
    sh = 0.35 + 0.65 * clamp(sh, 0.0, 1.0);

    float wrap = max(0.0, (-dot(n, LIGHT) + 0.35) / 1.35);
    float spec = pow(lam, 26.0) * 1.5;
    float rad = length(hp);
    float inner = exp(-max(0.0, rad - 0.45) * 3.4);
    float base = (0.20 + wrap * wrap * 1.35 * uPump) * sh + inner * 0.55;
    float rimE = fres * (1.15 + inner * 0.8);

    float3 col = uGlow * base + uHot * (rimE + spec) + env * 0.30;
    col *= ao;
    return half4(tonemap(col), 1.0);
}
"""
}
