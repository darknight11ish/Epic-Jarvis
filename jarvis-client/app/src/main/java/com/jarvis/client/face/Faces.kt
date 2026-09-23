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
 * Twenty faces. All of them.
 *
 * The brief called porting all twenty the real cost of going fully native,
 * and treated it as a multi-stage undertaking: seventeen from the spec's
 * `stays_on_canvas` list (line, stroke, point and glow art `DrawScope`
 * draws correctly and cheaply), one needing a real fragment shader
 * (Nucleus, AGSL via `android.graphics.RuntimeShader`), and two needing a
 * real OpenGL mesh - GLES 3.0, vertex and index buffers, per-vertex
 * normals - which a `GLSurfaceView` embedded alongside this file's
 * `DrawScope` faces now provides (`com.jarvis.client.face.gl`; Tokamak's
 * torus proved the pipeline, Membrane's spring-mass skin needed its own
 * live physics step on top of it). `Face.draw` is never called for any of
 * the three; `FaceView` checks `MeshFaces.rendererFor` first and swaps the
 * whole rendering path for whichever one it returns non-null for. A
 * rasterised version of any of them is the faceted, upscaled thing the
 * first audit was about, and shipping that would have been worse than not
 * offering them - which is why this took three separate, argued
 * increments to reach twenty rather than being done in the first pass.
 *
 * The picker shows only what is actually rendered — a promise that mattered
 * more while it was seventeen, or eighteen, or nineteen of twenty; it still
 * holds now that the count and the desktop's own agree.
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
 * `SpecDriftTest`'s `iris and membrane are the only offered faces that
 * cannot be pinned` for where that distinction is enforced and argued in
 * more detail.
 *
 * Membrane is the one face here that genuinely cannot make that same claim.
 * Its Verlet simulation needs the previous two frames' heights to compute
 * the next one - a real dependency on its own history, not a description of
 * a technique this port declined to use. It joins `iris` in that same test's
 * pinned exact set, by name, argued there rather than folded into the
 * deterministic seven above where it would not belong.
 */
object Faces {
    val all: List<Face> = listOf(
        Arc, Orbit, Comb, Spiral, Iris, Fullerene, Rime, Orbital, Geodesic, Kirkwood,
        Spectrum, Coreplate, Workbench, Swarm, Shoal, Accretion, Cascade, Nucleus, Tokamak,
        Membrane,
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

    // Scratch space for one draw, kept on the face instead of reallocated. These
    // four were `FloatArray(12)` locals inside `draw`, so four fresh arrays came
    // off the heap every frame - about 250 bytes a frame, 30KB a second at
    // 120fps, dropped into the nursery in the middle of the draw for no reason.
    // Fullerene and Orbital already keep their point buffers exactly this way,
    // and it is safe for the same reason: the face is a singleton drawn on one
    // thread, and all four are pure scratch - every slot is written at the top of
    // `draw` before anything reads it, so nothing carries over between frames.
    private val xs = FloatArray(verts.size)
    private val ys = FloatArray(verts.size)
    private val depth = FloatArray(verts.size)
    private val bright = FloatArray(verts.size)

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
                    .copy(
                        // Neither factor is bounded by 1 on its own - the
                        // first reaches 0.725 at d's max, the second 1.95 at
                        // b's (b is explicitly capped at 1 a few lines up,
                        // so that ceiling is reached, not theoretical) - and
                        // their product peaks at 1.41, over what
                        // `Color.copy(alpha = ...)` accepts. It throws
                        // `IllegalArgumentException` rather than clamping,
                        // so an uncoerced value here was a crash on a
                        // front-facing, fully-lit vertex, not a visual bug.
                        alpha = ((0.05f + (d - 0.55f).coerceAtLeast(0f) * 1.5f) *
                            (0.35f + b * 1.6f)).coerceIn(0f, 1f),
                    ),
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

    // Jupiter's own angular rate. A constant expression that was sitting in the
    // draw, so Math.pow ran once a frame for a number fixed at compile time.
    private val jupiterOmega = JUPITER_A.pow(-1.5f)

    // Fixed per-rock layout, seeded so it never reshuffles between draws.
    private val rockA = FloatArray(N)
    private val rockE = FloatArray(N)
    private val rockPhase = FloatArray(N)
    private val rockDepthSeed = FloatArray(N)
    private val rockSize = FloatArray(N)

    // a^-1.5: Kepler's angular rate. It is a function of the FIXED layout above
    // and of nothing else - not of time, not of state - but it was being raised
    // to a power inside the draw loop, so Math.pow ran once per rock per frame:
    // 420 calls a frame, about 50,000 a second at 120fps. Precomputed here for
    // the same reason rockA and rockPhase themselves are: decided once, then
    // only read. Costs 1.6KB for the life of the process.
    private val rockOmega = FloatArray(N)

    init {
        val rnd = kotlin.random.Random(20260913)
        for (i in 0 until N) {
            rockA[i] = 0.45f + rnd.nextFloat() * 0.55f
            rockE[i] = rnd.nextFloat() * 0.10f
            rockPhase[i] = rnd.nextFloat() * PI2
            rockDepthSeed[i] = (rnd.nextFloat() - 0.5f) * 0.10f
            rockSize[i] = rnd.nextFloat()
            rockOmega[i] = rockA[i].pow(-1.5f)
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

            // Kepler: inner orbits move faster. Precomputed at init - see rockOmega.
            val om = rockOmega[i]
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
        val ja = f.angle * jupiterOmega + f.yaw
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
 * Thirty-two bars standing on a ring, seen from above the plane, each with a
 * faint mirrored reflection below it.
 *
 * Rebuilt against the reference line for line (Jarvis Reactor Kit, artifact
 * lines 3402-3456): the same perspective ring (`proj`, yaw = PHASE x 0.35,
 * pitch -0.62, distance 3.6, scale 0.80 S, centred at 60% of the height), the
 * same per-state bar targets and height gains, the same far-to-near draw
 * order, bars 0.021 S x depth wide with round caps, a reflection at up to 34%
 * alpha, a glow cap on every bar above 0.35, and the rim ring on top.
 *
 * S is the reference's `min(w, h)`. The shell hands a face a radius of a
 * quarter of the shorter side times `fit`, and the reference applies `fit` as
 * a scale around the centre, so S = 4r reproduces its picture exactly, line
 * widths included. The old port sized bars from r (a quarter of S) with no
 * depth, no reflections, no glow and no ring: it drew about a third of this.
 *
 * One deliberate difference: the reference lerps each bar toward its target
 * every frame (`this.bands[i] = lerp(...)`, 0.18 a frame). Here a bar IS its
 * target, eased only across a state change (`CoreKit.settle`). The lerp's
 * time constant is 0.08 s and `f.amp` is already smoothed upstream in
 * `FaceHost`, so nothing visible is lost, and the face stays a pure function
 * of its frame, which `SpecDriftTest` relies on.
 */
object Spectrum : Face {
    override val id = "spectrum"
    override val name = "Spectrum"

    // faces[].render.fit in the spec is 0.86. This face was left at the
    // default 1.0, so its ring - and the speaking swell - sat 16% larger than
    // the desktop's and ran into the rim ring and notches.
    override val fit = 0.86f

    private const val N = 32

    // The bar lerp's time constant: 0.18 a frame at 60 fps.
    private const val BAND_TAU_S = 0.084f

    private val baseX = FloatArray(N)
    private val baseY = FloatArray(N)
    private val baseZ = FloatArray(N)
    private val baseD = FloatArray(N)
    private val topX = FloatArray(N)
    private val topY = FloatArray(N)
    private val reflX = FloatArray(N)
    private val reflY = FloatArray(N)
    private val band = FloatArray(N)
    private val order = IntArray(N)
    private var sorted = false
    private val rim = androidx.compose.ui.graphics.Path()

    // st[].sp: the spin rate, which is what `f.angle` (the reference's PHASE)
    // accumulates. These were 0.5 / 1.0 / 2.4 / 1.3, so thinking's sweep ran
    // half again as fast as the desktop's and speaking's twice as fast.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.0f
        FaceState.THINKING -> 1.6f
        FaceState.SPEAKING -> 0.55f
        else -> 0.4f
    }

    /** st[].h: how tall a full band stands in each state. */
    private fun heightGain(m: FaceState) = when (m) {
        FaceState.LISTENING -> 1.1f
        FaceState.THINKING -> 0.8f
        FaceState.SPEAKING -> 0.6f
        else -> 0.22f
    }

    /** The reference's per-state band target, artifact 3415-3419. */
    private fun target(m: FaceState, i: Int, f: FaceFrame): Float = when (m) {
        FaceState.LISTENING -> f.amp * (0.4f + 0.6f * kotlin.math.abs(sin(i * 0.7f + f.t * 3f)))
        FaceState.THINKING -> {
            // A pulse travelling round the ring on the spin phase. `%` on
            // floats keeps the sign exactly like JavaScript's, so this is the
            // reference's expression unchanged, negative phase included.
            val d = ((i / N.toFloat()) - ((f.angle * 0.3f) % 1f) + 1f) % 1f
            kotlin.math.exp(-d * d * 90f) * 0.9f + 0.08f
        }
        FaceState.SPEAKING -> 0.3f + 0.45f * kotlin.math.abs(sin(f.t * 2.2f + i * 0.18f))
        else -> 0.10f + 0.10f * sin(f.t * 0.9f + i * 0.5f)
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        if (r <= 0f) return@with
        val s = 4f * r
        val px1 = CoreKit.backingPx(density)
        CoreKit.clipToView(this)
        val ccy = cy + 0.10f * s // the reference centres this face at h * 0.60
        val yaw = f.angle * 0.35f
        val pitch = -0.62f
        val dist = 3.6f
        val scale = s * 0.80f
        val e = CoreKit.settle(f, BAND_TAU_S)
        val gain = CoreKit.eased(f, BAND_TAU_S) { heightGain(it) }

        for (i in 0 until N) {
            val tgt = target(f.motion, i, f)
            val v = if (e >= 1f) {
                tgt
            } else {
                val from = target(f.prevMotion, i, f)
                from + (tgt - from) * e
            }
            band[i] = v
            val a = i / N.toFloat() * PI2
            val x = cos(a)
            val z = sin(a)
            // Capped: speaking used to erupt past the frame (the spec's
            // audit_history "spectrum bar cap").
            val bh = kotlin.math.min(1.35f, (0.20f + v * gain * 1.5f) * 2.2f)
            CoreKit.proj(f, x, 0f, z, yaw, pitch, dist, scale, cx, ccy)
            baseX[i] = CoreKit.px; baseY[i] = CoreKit.py
            baseZ[i] = CoreKit.pz; baseD[i] = CoreKit.pd
            CoreKit.proj(f, x, -bh, z, yaw, pitch, dist, scale, cx, ccy)
            topX[i] = CoreKit.px; topY[i] = CoreKit.py
            CoreKit.proj(f, x, bh * 0.55f, z, yaw, pitch, dist, scale, cx, ccy)
            reflX[i] = CoreKit.px; reflY[i] = CoreKit.py
        }
        CoreKit.sortFarFirst(order, baseZ, N, fresh = !sorted)
        sorted = true

        val glowStops = CoreKit.fadeToClear(hot, 0.7f)
        for (k in 0 until N) {
            val i = order[k]
            val d = baseD[i]
            val v = band[i]
            val w = kotlin.math.max(1.5f * px1, s * 0.021f * d)
            val col = mix(cool, hot, kotlin.math.min(1f, v * 1.4f))
            val base = Offset(baseX[i], baseY[i])
            val top = Offset(topX[i], topY[i])
            drawLine(
                color = col, start = base, end = top, strokeWidth = w,
                cap = androidx.compose.ui.graphics.StrokeCap.Round,
                alpha = (0.2f + (d - 0.55f) * 1.5f).coerceIn(0f, 1f),
            )
            drawLine(
                color = col, start = base, end = Offset(reflX[i], reflY[i]), strokeWidth = w,
                cap = androidx.compose.ui.graphics.StrokeCap.Round,
                alpha = kotlin.math.min(0.34f, 0.04f + (d - 0.6f) * 0.5f).coerceIn(0f, 1f),
            )
            if (v > 0.35f) {
                // The glow cap: a radial ramp three bar-widths across, which
                // is what makes a loud band read as lit rather than drawn.
                drawCircle(
                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                        *glowStops,
                        center = top,
                        radius = w * 3f,
                    ),
                    radius = w * 3f,
                    center = top,
                    alpha = kotlin.math.min(0.8f, v),
                )
            }
        }

        // The rim the bars stand on, drawn last and faint: 35% of a 50%-alpha
        // cool, one of the reference's canvas pixels wide.
        rim.reset()
        for (k in 0..64) {
            val a = k / 64f * PI2
            CoreKit.proj(f, cos(a), 0f, sin(a), yaw, pitch, dist, scale, cx, ccy)
            if (k == 0) rim.moveTo(CoreKit.px, CoreKit.py) else rim.lineTo(CoreKit.px, CoreKit.py)
        }
        rim.close()
        drawPath(rim, color = cool.copy(alpha = 0.5f), alpha = 0.35f, style = Stroke(width = px1))
        drawContext.canvas.restore() // CoreKit.clipToView
    }
}

/**
 * A power cell with its lid off: four coaxial plates at different depths and
 * a helical winding running through them, tilted so the mechanism is seen
 * nearly edge-on.
 *
 * Rebuilt against the reference line for line (artifact 3668-3752). The old
 * port drew flat dashed ellipses and a flat helix with no perspective, no
 * depth sort, no shading and no core; this is the reference's real 3D stack:
 * 64-segment plates dashed 24 / 36 / 12 / 6, a 7-turn, 180-segment winding,
 * every piece depth-sorted together so the winding passes in front of and
 * behind the plates, plates shaded by how much they face up, the
 * travelling current brightening and fattening the winding, and the glowing
 * core with its dark three-point mark turning on top.
 *
 * Plate separation eases in from the previous state's value (`CoreKit.settle`,
 * the reference's 0.04-a-frame lerp) rather than carrying last frame's value.
 * The core's glow reach eases over the same curve; the reference snaps it,
 * and a snap in the brightest thing on the face is the one step here worth
 * rounding off.
 *
 * The current's phase differs from the reference on purpose. The reference
 * computes it as `t x cur`: the absolute clock times a per-state rate, which
 * teleports the pulse by `t x (new - old)` at every state change - exactly
 * the bug `FaceHost.advance` documents and fixes for spin. Here it runs on
 * the accumulated `tableAngle` times 2.4, the mean of the reference's
 * `cur / sp` ratios (2.0 to 2.5), so each state's current runs within 20% of
 * the reference's speed and never jumps.
 */
object Coreplate : Face {
    override val id = "coreplate"
    override val name = "Coreplate"

    private const val PLATE_SEGS = 64
    private const val TURNS = 7
    private const val COIL_SEGS = 180
    private const val MAX_ITEMS = PLATE_SEGS * 4 + COIL_SEGS
    private const val KIND_COIL = 4
    private const val SEP_TAU_S = 0.41f

    private val plateR = floatArrayOf(0.86f, 0.72f, 0.55f, 0.34f)
    private val plateY = floatArrayOf(-0.16f, -0.06f, 0.04f, 0.13f)
    private val plateLw = floatArrayOf(0.030f, 0.018f, 0.022f, 0.026f)
    private val plateHot = booleanArrayOf(false, false, true, true)
    private val plateDash = intArrayOf(24, 36, 12, 6)

    private val ax = FloatArray(MAX_ITEMS)
    private val ay = FloatArray(MAX_ITEMS)
    private val az = FloatArray(MAX_ITEMS)
    private val bx = FloatArray(MAX_ITEMS)
    private val by = FloatArray(MAX_ITEMS)
    private val bz = FloatArray(MAX_ITEMS)
    private val midZ = FloatArray(MAX_ITEMS)
    private val flowOf = FloatArray(MAX_ITEMS)
    private val kind = IntArray(MAX_ITEMS)
    private val order = IntArray(MAX_ITEMS)
    private var lastCount = -1
    private val mark = androidx.compose.ui.graphics.Path()

    // The reference draws the mark in #03060a, its old per-face background.
    private val markColor = Color(0xFF03060A)

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.2f
        FaceState.THINKING -> 2.0f
        FaceState.SPEAKING -> 0.8f
        else -> 0.5f
    }

    /** st[].sep: thinking pulls the stack apart into an exploded view. */
    private fun sepOf(m: FaceState) = when (m) {
        FaceState.LISTENING -> 0.15f
        FaceState.THINKING -> 0.85f
        FaceState.SPEAKING -> 0.25f
        else -> 0f
    }

    /** st[].gl: how far the core's glow reaches. */
    private fun glowOf(m: FaceState) = when (m) {
        FaceState.LISTENING -> 0.9f
        FaceState.THINKING -> 1f
        FaceState.SPEAKING -> 0.85f
        else -> 0.5f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        if (r <= 0f) return@with
        val s = 4f * r
        val px1 = CoreKit.backingPx(density)
        CoreKit.clipToView(this)
        val sep = CoreKit.eased(f, SEP_TAU_S) { sepOf(it) }
        val yaw = f.angle * 0.3f
        val pitch = -1.02f + sin(f.t * 0.2f) * 0.08f
        val dist = 4.0f
        val scale = s * 1.42f
        val spread = 1f + sep * 4.5f

        var n = 0
        for (p in 0 until 4) {
            val y = plateY[p] * spread
            val rr = plateR[p]
            // In doubles, exactly as the reference's JavaScript computes it:
            // 64 / 24 is not a whole number, and in floats `k / 2.6666667f`
            // lands on the other side of an integer at k = 8, which would
            // move a dash.
            val per = PLATE_SEGS.toDouble() / plateDash[p]
            for (k in 0 until PLATE_SEGS) {
                if (kotlin.math.floor(k / per).toInt() % 2 == 1) continue
                val q0 = k / PLATE_SEGS.toFloat() * PI2
                val q1 = (k + 1) / PLATE_SEGS.toFloat() * PI2
                CoreKit.rot3(f, cos(q0) * rr, y, sin(q0) * rr, yaw, pitch)
                ax[n] = CoreKit.rx; ay[n] = CoreKit.ry; az[n] = CoreKit.rz
                CoreKit.rot3(f, cos(q1) * rr, y, sin(q1) * rr, yaw, pitch)
                bx[n] = CoreKit.rx; by[n] = CoreKit.ry; bz[n] = CoreKit.rz
                midZ[n] = (az[n] + bz[n]) / 2f
                kind[n] = p
                n++
            }
        }
        val current = f.tableAngle * 2.4f
        // Each segment's end is the next one's start, so the helix point is
        // computed once per vertex rather than twice per segment.
        coilPoint(f, 0f, spread, yaw, pitch)
        var pX = CoreKit.rx
        var pY = CoreKit.ry
        var pZ = CoreKit.rz
        for (k in 0 until COIL_SEGS) {
            val u0 = k / COIL_SEGS.toFloat()
            val u1 = (k + 1) / COIL_SEGS.toFloat()
            coilPoint(f, u1, spread, yaw, pitch)
            ax[n] = pX; ay[n] = pY; az[n] = pZ
            bx[n] = CoreKit.rx; by[n] = CoreKit.ry; bz[n] = CoreKit.rz
            pX = CoreKit.rx; pY = CoreKit.ry; pZ = CoreKit.rz
            midZ[n] = (az[n] + bz[n]) / 2f
            flowOf[n] = kotlin.math.max(0f, sin(u0 * PI2 * 2f - current * 2f)).pow(5)
            kind[n] = KIND_COIL
            n++
        }
        CoreKit.sortFarFirst(order, midZ, n, fresh = n != lastCount)
        lastCount = n

        val white = CoreKit.white(f)
        val coilHot = mix(hot, white, 0.5f) // never pure white: the spec's "coreplate never white"
        for (o in 0 until n) {
            val idx = order[o]
            val ka = scale / (dist + az[idx])
            val kb = scale / (dist + bz[idx])
            val d = dist / (dist + midZ[idx])
            val start = Offset(cx + ax[idx] * ka, cy + ay[idx] * ka)
            val end = Offset(cx + bx[idx] * kb, cy + by[idx] * kb)
            if (kind[idx] == KIND_COIL) {
                val flow = flowOf[idx]
                drawLine(
                    color = if (flow > 0.25f) coilHot else hot,
                    start = start, end = end,
                    strokeWidth = kotlin.math.max(0.7f * px1, s * 0.008f * d * (1f + flow * 2.2f)),
                    cap = androidx.compose.ui.graphics.StrokeCap.Round,
                    alpha = 0.18f + flow * 0.82f,
                )
            } else {
                val p = kind[idx]
                val len = kotlin.math.sqrt(ax[idx] * ax[idx] + ay[idx] * ay[idx] + az[idx] * az[idx])
                val up = kotlin.math.max(0f, -ay[idx] / (if (len > 0f) len else 1f))
                drawLine(
                    color = CoreKit.shade(if (plateHot[p]) hot else cool, 0.55f + up * 0.9f + d * 0.25f),
                    start = start, end = end,
                    strokeWidth = kotlin.math.max(px1, s * plateLw[p] * d),
                    cap = androidx.compose.ui.graphics.StrokeCap.Round,
                    alpha = kotlin.math.min(1f, 0.35f + d * 0.5f),
                )
            }
        }

        // The core: a white-hot centre fading through the state colour, and a
        // dark three-point mark turning with the spin, squashed to the tilt.
        val ey = 0.13f * spread
        val pulse = if (f.motion == FaceState.LISTENING) f.amp * 0.45f else 0.06f * sin(f.t * 4f)
        val er = s * 0.052f * (1f + pulse)
        CoreKit.rot3(f, 0f, ey, 0f, yaw, pitch)
        val kc = scale / (dist + CoreKit.rz)
        val core = Offset(cx + CoreKit.rx * kc, cy + CoreKit.ry * kc)
        val gl = CoreKit.eased(f, SEP_TAU_S) { glowOf(it) }
        drawCircle(
            brush = androidx.compose.ui.graphics.Brush.radialGradient(
                0f to white,
                0.22f to hot,
                *CoreKit.fadeToClear(hot, 0.25f * gl, from = 0.55f),
                center = core,
                radius = er * 4f,
            ),
            radius = er * 4f,
            center = core,
        )
        mark.reset()
        for (i in 0 until 3) {
            val a = i / 3f * PI2 - (PI / 2).toFloat()
            val x = cos(a) * er * 0.8f
            val y = sin(a) * er * 0.8f
            if (i == 0) mark.moveTo(x, y) else mark.lineTo(x, y)
        }
        mark.close()
        // translate, squash, then turn - the reference's own order, so the
        // mark turns in the plane of the plates rather than of the screen.
        drawContext.canvas.save()
        drawContext.transform.translate(core.x, core.y)
        drawContext.transform.scale(1f, 0.42f, pivot = Offset.Zero)
        drawContext.transform.rotate(-f.angle * (180f / PI.toFloat()), pivot = Offset.Zero)
        drawPath(mark, color = markColor, style = Stroke(width = kotlin.math.max(2f * px1, s * 0.012f)))
        drawContext.canvas.restore()
        drawContext.canvas.restore() // CoreKit.clipToView
    }

    /** One point on the winding, rotated, into CoreKit's rx / ry / rz. */
    private fun coilPoint(f: FaceFrame, u: Float, spread: Float, yaw: Float, pitch: Float) {
        val a = u * PI2 * TURNS
        val yy = (-0.2f + u * 0.42f) * spread
        val rr = 0.46f + 0.05f * sin(u * PI2 * 3f)
        CoreKit.rot3(f, cos(a) * rr, yy, sin(a) * rr, yaw, pitch)
    }
}

/**
 * An assembly exploded in mid-air: four nested wireframe shells floating
 * apart, a scan plane sweeping through them, a floor grid, and a caliper
 * reading the real projected gap.
 *
 * Rebuilt against the reference line for line (artifact 3755-3837). The old
 * port drew each shell as a row of vertical strokes with no rings, no
 * perspective, no grid, no scan plane and no caliper. This is the
 * reference's geometry: each shell a top ring, a bottom ring and every other
 * strut (105 segments in all), depth-sorted and lit by each segment's real
 * distance to the scan plane - not a timer - with the plane itself drawn as
 * a translucent quad, the 11 x 2 floor grid under it all, and the caliper
 * and its labels on the right and top left.
 *
 * Shell separation eases in from the previous state (`CoreKit.settle`, the
 * reference's 0.05-a-frame lerp). The scan plane does too, and that is a
 * deliberate difference: the reference computes it as `sin(t x scan)`, the
 * absolute clock times a per-state rate, which teleports the plane at every
 * state change. Blending the two waves over the same third of a second
 * reaches the reference's exact position once settled, without the jump.
 */
object Workbench : Face {
    override val id = "workbench"
    override val name = "Workbench"

    private const val SEP_TAU_S = 0.33f

    private val shellR = floatArrayOf(0.70f, 0.55f, 0.38f, 0.20f)
    private val shellHh = floatArrayOf(0.34f, 0.26f, 0.20f, 0.13f)
    private val shellN = intArrayOf(16, 12, 8, 6)

    // 2n ring segments per shell plus a strut on every other vertex.
    private val maxSegs = shellN.sumOf { it * 2 + (it + 1) / 2 }

    private val ax = FloatArray(maxSegs)
    private val ay = FloatArray(maxSegs)
    private val az = FloatArray(maxSegs)
    private val bx = FloatArray(maxSegs)
    private val by = FloatArray(maxSegs)
    private val bz = FloatArray(maxSegs)
    private val midZ = FloatArray(maxSegs)
    private val lit = FloatArray(maxSegs)
    private val order = IntArray(maxSegs)
    private var sorted = false
    private val plane = androidx.compose.ui.graphics.Path()

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.45f
        FaceState.THINKING -> 0.9f
        FaceState.SPEAKING -> 0.3f
        else -> 0.25f
    }

    /** st[].sep; speaking pulls the assembly back together. */
    private fun sepOf(m: FaceState) = when (m) {
        FaceState.LISTENING -> 0.4f
        FaceState.THINKING -> 1.15f
        FaceState.SPEAKING -> 0.08f
        else -> 0.55f
    }

    /** st[].scan: how fast the scan plane sweeps. */
    private fun scanOf(m: FaceState) = when (m) {
        FaceState.LISTENING -> 1.6f
        FaceState.THINKING -> 2.6f
        FaceState.SPEAKING -> 0.8f
        else -> 0.5f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        // A zero-size layout would divide by zero in the projection below and
        // hand NaN to mix(), whose Color constructor throws on NaN channels -
        // a crashed draw rather than a blank face. Nothing to draw anyway.
        if (r <= 0f) return@with
        val s = 4f * r
        val px1 = CoreKit.backingPx(density)
        CoreKit.clipToView(this)
        // Listening narrows the gap with the voice, as the reference does.
        val sep = CoreKit.eased(f, SEP_TAU_S) {
            sepOf(it) * (if (it == FaceState.LISTENING) 1f - f.amp * 0.4f else 1f)
        }
        val yaw = f.angle
        val pitch = -0.34f + sin(f.t * 0.17f) * 0.07f
        val dist = 4.6f
        val scale = s * 1.05f
        val scanY = CoreKit.eased(f, SEP_TAU_S) { sin(f.t * scanOf(it)) * 0.85f }

        // The floor grid, drawn first so everything else sits on it.
        val gridCol = cool.copy(alpha = 0.5f)
        for (i in -5..5) {
            val g = i * 0.24f
            gridLine(f, g, -1.2f, g, 1.2f, yaw, pitch, dist, scale, cx, cy, gridCol, px1)
            gridLine(f, -1.2f, g, 1.2f, g, yaw, pitch, dist, scale, cx, cy, gridCol, px1)
        }

        var n = 0
        for (si in 0 until 4) {
            val off = (si - 1.5f) * sep
            val cnt = shellN[si]
            val rr = shellR[si]
            val hh = shellHh[si]
            for (k in 0 until cnt) {
                val j = (k + 1) % cnt
                val a0 = k / cnt.toFloat() * PI2
                val a1 = j / cnt.toFloat() * PI2
                val x0 = cos(a0) * rr
                val z0 = sin(a0) * rr
                val x1 = cos(a1) * rr
                val z1 = sin(a1) * rr
                n = segment(f, n, x0, -hh + off, z0, x1, -hh + off, z1, yaw, pitch, scanY)
                n = segment(f, n, x0, hh + off, z0, x1, hh + off, z1, yaw, pitch, scanY)
                if (k % 2 == 0) n = segment(f, n, x0, -hh + off, z0, x0, hh + off, z0, yaw, pitch, scanY)
            }
        }
        CoreKit.sortFarFirst(order, midZ, n, fresh = !sorted)
        sorted = true

        val white = CoreKit.white(f)
        for (o in 0 until n) {
            val i = order[o]
            val ka = scale / (dist + az[i])
            val kb = scale / (dist + bz[i])
            val d = dist / (dist + midZ[i])
            val l = lit[i]
            drawLine(
                color = if (l > 0.25f) mix(hot, white, l * 0.7f) else hot,
                start = Offset(cx + ax[i] * ka, cy + ay[i] * ka),
                end = Offset(cx + bx[i] * kb, cy + by[i] * kb),
                strokeWidth = kotlin.math.max(0.7f * px1, s * 0.0035f * d * (1f + l * 2.2f)),
                alpha = ((0.16f + (d - 0.72f) * 1.5f) + l * 0.85f).coerceIn(0f, 1f),
            )
        }

        // The scan plane: a translucent quad at its height, outlined.
        plane.reset()
        for (c in 0 until 4) {
            val qx = if (c == 0 || c == 3) -1f else 1f
            val qz = if (c < 2) -1f else 1f
            CoreKit.rot3(f, qx, scanY, qz, yaw, pitch)
            val k = scale / (dist + CoreKit.rz)
            val x = cx + CoreKit.rx * k
            val y = cy + CoreKit.ry * k
            if (c == 0) plane.moveTo(x, y) else plane.lineTo(x, y)
        }
        plane.close()
        drawPath(plane, color = hot, alpha = 0.16f)
        drawPath(plane, color = hot, alpha = 0.55f, style = Stroke(width = px1))

        // The caliper: the real projected distance between the outermost
        // shell tops and bottoms, on the right, with its reading.
        CoreKit.rot3(f, 0f, -1.5f * sep - 0.34f, 0f, yaw, pitch)
        val topY = cy + CoreKit.ry * (scale / (dist + CoreKit.rz))
        CoreKit.rot3(f, 0f, 1.5f * sep + 0.34f, 0f, yaw, pitch)
        val botY = cy + CoreKit.ry * (scale / (dist + CoreKit.rz))
        val gx = cx + s * 0.40f
        val calCol = hot.copy(alpha = 0.6f)
        drawLine(calCol, Offset(gx, topY), Offset(gx, botY), strokeWidth = px1)
        drawLine(calCol, Offset(gx - s * 0.02f, topY), Offset(gx + s * 0.02f, topY), strokeWidth = px1)
        drawLine(calCol, Offset(gx - s * 0.02f, botY), Offset(gx + s * 0.02f, botY), strokeWidth = px1)

        // The labels, placed where the reference puts them on its square
        // canvas (S x 0.06 across, 0.10 and 0.15 down), measured from the
        // centre so a non-square view keeps them beside the drawing.
        val textPx = kotlin.math.round(s * 0.028f)
        val mm = kotlin.math.abs(botY - topY) / s * 142f
        drawCoreLabel(
            String.format(java.util.Locale.US, "%.1fmm", mm),
            gx + s * 0.03f, (topY + botY) / 2f, textPx, hot.copy(alpha = 0.85f),
        )
        val lx = cx - s * 0.44f
        drawCoreLabel("SHELL ASSY / 4 PARTS", lx, cy - s * 0.40f, textPx, hot.copy(alpha = 0.7f))
        drawCoreLabel(
            if (f.motion == FaceState.SPEAKING) "RESEATING" else "EXPLODED",
            lx, cy - s * 0.35f, textPx, hot.copy(alpha = 0.7f),
        )
        drawContext.canvas.restore() // CoreKit.clipToView
    }

    private fun DrawScope.gridLine(
        f: FaceFrame, x0: Float, z0: Float, x1: Float, z1: Float,
        yaw: Float, pitch: Float, dist: Float, scale: Float, cx: Float, cy: Float,
        col: Color, width: Float,
    ) {
        CoreKit.rot3(f, x0, 1.05f, z0, yaw, pitch)
        val ka = scale / (dist + CoreKit.rz)
        val a = Offset(cx + CoreKit.rx * ka, cy + CoreKit.ry * ka)
        CoreKit.rot3(f, x1, 1.05f, z1, yaw, pitch)
        val kb = scale / (dist + CoreKit.rz)
        drawLine(col, a, Offset(cx + CoreKit.rx * kb, cy + CoreKit.ry * kb), strokeWidth = width)
    }

    /** Rotates one shell segment into the buffers; returns the next free slot. */
    private fun segment(
        f: FaceFrame, n: Int,
        x0: Float, y0: Float, z0: Float, x1: Float, y1: Float, z1: Float,
        yaw: Float, pitch: Float, scanY: Float,
    ): Int {
        CoreKit.rot3(f, x0, y0, z0, yaw, pitch)
        ax[n] = CoreKit.rx; ay[n] = CoreKit.ry; az[n] = CoreKit.rz
        CoreKit.rot3(f, x1, y1, z1, yaw, pitch)
        bx[n] = CoreKit.rx; by[n] = CoreKit.ry; bz[n] = CoreKit.rz
        midZ[n] = (az[n] + bz[n]) / 2f
        // Lit by the segment's own height against the plane, in the shell's
        // space before rotation - the plane belongs to the object.
        val e = ((y0 + y1) / 2f - scanY) * 3.4f
        lit[n] = kotlin.math.exp(-(e * e))
        return n + 1
    }
}

/**
 * Two hundred and twenty agents, drawn as the reference draws them: a
 * depth-fogged dot per agent with a short trail along its heading, white
 * where it is moving fast, the whole cloud under a slowly turning camera.
 *
 * The drawing is the reference's line for line (artifact 3596-3662): the
 * same camera (yaw t x 0.09, pitch -0.2, distance 3.4, scale 0.62 S), the
 * same fog `(d - 0.62) x 2.1`, dot radius 0.0065 S x depth, a trail seven
 * frames of travel long at half the fog's alpha and 0.9 of the dot's width,
 * white heads above the reference's speed threshold, the same colour slot
 * per state, and all of it depth-sorted. The old port drew 160 fixed-size
 * dots with no trails, no fog curve and no sort.
 *
 * The motion is NOT the reference's, and cannot be while this face stays a
 * pure function of its frame (`SpecDriftTest`): the reference integrates real
 * boid velocities in a curl field, and what comes out is emergent. Each state
 * here is a closed-form path instead, tuned to what that simulation actually
 * produces - measured by running it for fifty seconds per state (median
 * radius, speed spread, share of white heads):
 *  - idle: a streaming ribbon, most agents on one long arc that flows round
 *    the ball, a few stragglers drifting slowly (median speed 0.04 a frame,
 *    89% white in the reference);
 *  - listening: the whole flock pulled into one bright bead that wanders
 *    near the centre (the reference's spread falls to 0.0003 in five
 *    seconds);
 *  - thinking: fast agents scattered over the shell in competing clusters
 *    (median radius 1.9, speed 0.1 a frame, all white);
 *  - speaking: agents pinned at the shell with long radial streaks, pulsing
 *    outward in waves (median radius 1.9).
 * A state change blends the two paths over half a second, which stands in
 * for the flock accelerating from one pattern into the next.
 */
object Swarm : Face {
    override val id = "swarm"
    override val name = "Swarm"

    private const val N = 220
    private const val BUNDLES = 9
    private const val BLEND_TAU_S = 0.5f

    private val sizeSeed = FloatArray(N) { hash01(it * 29 + 11) }
    private val h1 = FloatArray(N) { hash01(it * 7 + 1) }
    private val h2 = FloatArray(N) { hash01(it * 13 + 3) }
    private val h3 = FloatArray(N) { hash01(it * 19 + 5) }
    private val h4 = FloatArray(N) { hash01(it * 37 + 17) }
    private val h5 = FloatArray(N) { hash01(it * 43 + 23) }

    // A fixed unit direction per agent, uniform over the sphere, and a
    // second unit vector perpendicular to it, for great-circle motion.
    private val dirX = FloatArray(N)
    private val dirY = FloatArray(N)
    private val dirZ = FloatArray(N)
    private val perX = FloatArray(N)
    private val perY = FloatArray(N)
    private val perZ = FloatArray(N)

    init {
        for (i in 0 until N) {
            // Speaking's bundles and thinking's clusters: shared directions
            // spread evenly over the sphere (a golden-angle spiral - random
            // ones bunched on one side and the speaking burst went
            // lopsided), each agent jittered around its own.
            val c = i % BUNDLES
            val cz = 1f - 2f * (c + 0.5f) / BUNDLES
            val cr = kotlin.math.sqrt(kotlin.math.max(0f, 1f - cz * cz))
            val cph = c * 2.3999632f
            var x = cr * cos(cph) + (h1[i] - 0.5f) * 0.6f
            var y = cz + (h2[i] - 0.5f) * 0.6f
            var z = cr * sin(cph) + (h3[i] - 0.5f) * 0.6f
            var len = kotlin.math.sqrt(x * x + y * y + z * z).coerceAtLeast(1e-4f)
            x /= len; y /= len; z /= len
            dirX[i] = x; dirY[i] = y; dirZ[i] = z
            // Any vector not parallel to dir, crossed with it, then normalised.
            val ux = if (kotlin.math.abs(y) < 0.9f) 0f else 1f
            val uy = if (kotlin.math.abs(y) < 0.9f) 1f else 0f
            var px = uy * z
            var py = -ux * z
            var pz = ux * y - uy * x
            len = kotlin.math.sqrt(px * px + py * py + pz * pz).coerceAtLeast(1e-4f)
            px /= len; py /= len; pz /= len
            perX[i] = px; perY[i] = py; perZ[i] = pz
        }
    }

    private val qx = FloatArray(N)
    private val qy = FloatArray(N)
    private val qz = FloatArray(N)
    private val qd = FloatArray(N)
    private val tx = FloatArray(N)
    private val ty = FloatArray(N)
    private val speed = FloatArray(N)
    private val order = IntArray(N)
    private var lastUse = -1

    // Filled by `model`: position, and velocity in units per SECOND.
    private var mx = 0f
    private var my = 0f
    private var mz = 0f
    private var mvx = 0f
    private var mvy = 0f
    private var mvz = 0f

    // The reference's swarm has no per-state table, so its spin rate is 1
    // in every state; nothing here reads `f.angle` anyway.
    override fun speedFor(motion: FaceState) = 1f

    /** cfg.col: idle PC[1], listening PC[0], thinking and speaking PC[2]. */
    private fun colourOf(m: FaceState, hot: Color, cool: Color) = when (m) {
        FaceState.LISTENING -> hot
        FaceState.THINKING, FaceState.SPEAKING -> mix(hot, cool, 0.5f)
        else -> cool
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        if (r <= 0f) return@with
        val s = 4f * r
        val px1 = CoreKit.backingPx(density)
        CoreKit.clipToView(this)
        // The reference drops to 110 agents on a canvas under 420 of its
        // pixels - a thumbnail - and draws all of them otherwise.
        val use = if (s / px1 < 420f) 110 else N
        val yaw = f.t * 0.09f
        val pitch = -0.2f
        val dist = 3.4f
        val scale = s * 0.62f
        val e = CoreKit.settle(f, BLEND_TAU_S)

        for (i in 0 until use) {
            model(f.motion, i, f)
            var x = mx; var y = my; var z = mz
            var vx = mvx; var vy = mvy; var vz = mvz
            if (e < 1f) {
                model(f.prevMotion, i, f)
                x = mx + (x - mx) * e; y = my + (y - my) * e; z = mz + (z - mz) * e
                vx = mvx + (vx - mvx) * e; vy = mvy + (vy - mvy) * e; vz = mvz + (vz - mvz) * e
            }
            // Per frame at 60 fps, the unit the reference's threshold and
            // trail length are written in.
            vx /= 60f; vy /= 60f; vz /= 60f
            CoreKit.proj(f, x, y, z, yaw, pitch, dist, scale, cx, cy)
            qx[i] = CoreKit.px; qy[i] = CoreKit.py; qz[i] = CoreKit.pz; qd[i] = CoreKit.pd
            CoreKit.proj(f, x - vx * 7f, y - vy * 7f, z - vz * 7f, yaw, pitch, dist, scale, cx, cy)
            tx[i] = CoreKit.px; ty[i] = CoreKit.py
            speed[i] = kotlin.math.sqrt(vx * vx + vy * vy + vz * vz)
        }
        CoreKit.sortFarFirst(order, qz, use, fresh = use != lastUse)
        lastUse = use

        val col = if (e < 1f) {
            mix(colourOf(f.prevMotion, hot, cool), colourOf(f.motion, hot, cool), e)
        } else {
            colourOf(f.motion, hot, cool)
        }
        val white = CoreKit.white(f)
        for (k in 0 until use) {
            val i = order[k]
            val d = qd[i]
            val fog = ((d - 0.62f) * 2.1f).coerceIn(0f, 1f)
            if (fog <= 0f) continue
            val rad = kotlin.math.max(0.6f * px1, s * 0.0065f * d * (0.6f + sizeSeed[i] * 0.8f))
            val head = Offset(qx[i], qy[i])
            drawLine(col, Offset(tx[i], ty[i]), head, strokeWidth = rad * 0.9f, alpha = fog * 0.5f)
            drawCircle(
                color = if (kotlin.math.min(1f, speed[i] * 36f) > 0.55f) white else col,
                radius = rad,
                center = head,
                alpha = fog,
            )
        }
        drawContext.canvas.restore() // CoreKit.clipToView
    }

    /**
     * One agent's position and velocity (units per second) in one state,
     * into mx..mvz. See the class comment for what each state is tuned to.
     */
    private fun model(m: FaceState, i: Int, f: FaceFrame) {
        val t = f.t
        val ft = t * 0.55f // the reference's flow-field clock
        when (m) {
            FaceState.LISTENING -> {
                // The reference's pull is strong enough here that the whole
                // flock falls into one point within a few seconds (measured:
                // spread 0.09 after one second, 0.0003 after five) and that
                // point wanders 0.03 to 0.2 from the centre - so listening
                // reads as a single bright bead. The bead here keeps a
                // hair of size, tighter with a louder voice (the pull grows
                // by 1 + 2.5 amp), so it is still a crowd up close.
                val ball = 0.03f * 1.7f / (1f + 2.5f * f.amp)
                val rho = ball * (0.45f + 1.4f * h4[i] * h4[i]) / 0.8f
                val w = 0.25f + 0.3f * h5[i]
                orbit(i, rho, t * w + h1[i] * PI2, w, 0f)
                val drift = 0.12f / (1f + f.amp)
                mx += drift * sin(ft * 0.7f); my += drift * 0.6f * sin(ft * 0.5f + 1f); mz += drift * cos(ft * 0.6f)
                mvx += drift * 0.7f * 0.55f * cos(ft * 0.7f)
                mvy += drift * 0.6f * 0.5f * 0.55f * cos(ft * 0.5f + 1f)
                mvz -= drift * 0.6f * 0.55f * sin(ft * 0.6f)
            }
            FaceState.THINKING -> {
                val rho = if (h4[i] < 0.55f) 1.9f else 1.1f + 0.8f * h5[i]
                val w = (4.5f + 3.5f * h3[i]) / rho
                // Each cluster starts its circle at the same angle, so the
                // agents that share a direction travel together.
                orbit(i, rho, t * w + (i % BUNDLES) * 0.9f + (h2[i] - 0.5f) * 1.1f, w, 0.12f)
            }
            FaceState.SPEAKING -> {
                // A wave per bundle: out fast on the crest, pinned at the
                // shell, then eased back a little in the trough.
                val wv = sin(ft * 5f - (i % BUNDLES) * 0.9f - h1[i] * 1.2f)
                val k = 0.5f + 0.5f * wv
                val rho = 1.9f - (1f - k) * 0.45f * h2[i]
                val out = (0.02f + 0.22f * k * kotlin.math.sqrt(k)) * 60f
                // The bundles drift slowly round the vertical axis.
                val a = t * 0.15f
                val ca = cos(a)
                val sa = sin(a)
                val dx = dirX[i] * ca - dirZ[i] * sa
                val dz = dirX[i] * sa + dirZ[i] * ca
                mx = dx * rho; my = dirY[i] * rho; mz = dz * rho
                mvx = dx * out; mvy = dirY[i] * out; mvz = dz * out
            }
            else -> {
                if (h5[i] < 0.12f) {
                    // Stragglers: slow, loose orbits inside the ball, the
                    // share of the reference's idle heads that are not white.
                    val rho = 0.6f + 1.0f * h3[i]
                    val w = 0.35f * (0.6f + 0.8f * h4[i]) / rho
                    orbit(i, rho, t * w + h1[i] * PI2, w, 0f)
                } else {
                    // The stream: agents spread along a 2.6-radian arc of a
                    // slowly morphing loop, flowing along it at 1.5 rad/s.
                    val wob = 0.35f * sin(t * 0.7f + h2[i] * PI2)
                    val u = t * 1.5f + 2.6f * (h1[i] - 0.5f) + wob
                    val du = 1.5f + 0.35f * 0.7f * cos(t * 0.7f + h2[i] * PI2)
                    val a2 = 2f * u + ft * 0.6f
                    val b2 = 2f * u + 0.9f + ft * 0.4f
                    val c3 = 3f * u - ft * 0.5f
                    val th = 1f + 0.3f * sin(t * 1.3f + h4[i] * PI2)
                    mx = 1.25f * sin(u) + 0.25f * sin(a2) + (h3[i] - 0.5f) * 0.32f * th
                    my = 0.55f * sin(b2) + (h4[i] - 0.5f) * 0.32f * th
                    mz = 1.25f * cos(u) + 0.25f * cos(c3) + (sizeSeed[i] - 0.5f) * 0.32f * th
                    mvx = (1.25f * cos(u) + 0.5f * cos(a2)) * du
                    mvy = 1.1f * cos(b2) * du
                    mvz = (-1.25f * sin(u) - 0.75f * sin(c3)) * du
                }
            }
        }
    }

    /**
     * A great circle of radius [rho] through the agent's own direction, at
     * angle [th] and angular speed [w], with an optional wiggle of [wig] off
     * the circle's plane so the trails curve the way a flow field's do.
     */
    private fun orbit(i: Int, rho: Float, th: Float, w: Float, wig: Float) {
        val c = cos(th)
        val s = sin(th)
        // The circle's normal is dir x per; the wiggle moves along it.
        val nx = dirY[i] * perZ[i] - dirZ[i] * perY[i]
        val ny = dirZ[i] * perX[i] - dirX[i] * perZ[i]
        val nz = dirX[i] * perY[i] - dirY[i] * perX[i]
        val wp = 2.7f * th + h5[i] * PI2
        val off = wig * sin(wp)
        val offV = wig * 2.7f * w * cos(wp)
        mx = rho * (c * dirX[i] + s * perX[i]) + off * nx
        my = rho * (c * dirY[i] + s * perY[i]) + off * ny
        mz = rho * (c * dirZ[i] + s * perZ[i]) + off * nz
        mvx = rho * w * (-s * dirX[i] + c * perX[i]) + offV * nx
        mvy = rho * w * (-s * dirY[i] + c * perY[i]) + offV * ny
        mvz = rho * w * (-s * dirZ[i] + c * perZ[i]) + offV * nz
    }
}

/**
 * A schooling sheet that flashes as it wheels: each fish is a filled sliver
 * with a tail, and its brightness is the angle between its flank and the
 * light, so the shoal flickers silver exactly when it turns.
 *
 * The drawing is the reference's line for line (artifact 4390-4447): up to
 * 190 fish by canvas size (the reference's `detail(w, 90, 190)`), the same
 * camera (yaw t x 0.12, pitch -0.12, distance 3.2, scale 1.7 S), body length
 * 0.042 S x depth, a quadratic body and a triangular tail, colour from a
 * depth-shaded structural tone to the hot one by `flank^3`, and far-to-near
 * order. The old port drew 140 plain line segments with no body, no tail,
 * no perspective and a flash that was not tied to the heading.
 *
 * The reference moves each fish with a damped spring toward a shared moving
 * target plus its own station in the school. That spring is stiff next to
 * how slowly the target moves, so once settled each fish simply follows the
 * target a fixed moment behind it: `lag = (1 - damp) / (damp x coh x
 * fishLag)` frames. This follows that closed form, which keeps the face a
 * pure function of its frame (`SpecDriftTest`) - checked against the real
 * simulation run for a minute per state: mean position error 0.007 to 0.08
 * units in a school about 3 units across, heading error 4 to 14 degrees.
 *
 * Two reference details kept deliberately: the owner's drag yaw is applied
 * twice, as the reference does (its `ry` already includes `VIEW.yaw`, and
 * `proj` adds it again), so a drag turns this face at the same rate on both
 * screens; and there is no touch attraction (`TOUCH`), because this shell
 * reports taps and drags, not a held finger position.
 */
object Shoal : Face {
    override val id = "shoal"
    override val name = "Shoal"

    // faces[].render.fit in the spec is 0.8; this was left at 1.0.
    override val fit = 0.8f

    private const val N = 190
    private const val SPREAD_TAU_S = 0.6f

    private val seed = FloatArray(N) { hash01(it * 31 + 9) }
    private val offX = FloatArray(N) { (hash01(it * 17 + 2) - 0.5f) * 1.9f }
    private val offY = FloatArray(N) { (hash01(it * 23 + 6) - 0.5f) * 1.1f }
    private val offZ = FloatArray(N) { (hash01(it * 41 + 4) - 0.5f) * 1.9f }

    private val qx = FloatArray(N)
    private val qy = FloatArray(N)
    private val qz = FloatArray(N)
    private val qd = FloatArray(N)
    private val ang = FloatArray(N)
    private val flash = FloatArray(N)
    private val order = IntArray(N)
    private var lastN = -1

    // The light the flank is lit by: the reference's LIGHT, normalised.
    private val lightX: Float
    private val lightY: Float

    init {
        val lx = -0.45f
        val ly = -0.75f
        val lz = -0.48f
        val n = kotlin.math.sqrt(lx * lx + ly * ly + lz * lz)
        lightX = lx / n
        lightY = ly / n
    }

    // A unit fish, one body length long, pointing along +x: the reference's
    // quadratic body (width 0.32 of the length) and its triangular tail.
    // Built once and scaled per fish, rather than rebuilt 190 times a frame;
    // lazily, on the first draw, like Nucleus's shader, so touching
    // `Faces.all` at startup builds nothing for a face never shown.
    private val body by lazy { androidx.compose.ui.graphics.Path().apply {
        moveTo(0.6f, 0f)
        quadraticTo(0f, -0.32f, -0.5f, 0f)
        quadraticTo(0f, 0.32f, 0.6f, 0f)
        close()
    } }
    private val tail by lazy { androidx.compose.ui.graphics.Path().apply {
        moveTo(-0.45f, 0f)
        lineTo(-0.75f, -0.32f * 0.8f)
        lineTo(-0.75f, 0.32f * 0.8f)
        close()
    } }

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.9f
        FaceState.THINKING -> 1.7f
        FaceState.SPEAKING -> 0.7f
        else -> 0.5f
    }

    private fun cohOf(m: FaceState) = when (m) {
        FaceState.LISTENING -> 0.020f
        FaceState.THINKING -> 0.004f
        FaceState.SPEAKING -> 0.013f
        else -> 0.008f
    }

    private fun spreadOf(m: FaceState) = when (m) {
        FaceState.LISTENING -> 0.72f
        FaceState.THINKING -> 1.25f
        FaceState.SPEAKING -> 0.9f
        else -> 1.0f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        if (r <= 0f) return@with
        val s = 4f * r
        val px1 = CoreKit.backingPx(density)
        CoreKit.clipToView(this)
        // detail() reads the canvas width before `fit` is applied.
        val n = CoreKit.detail(s / (fit * px1), 90, N)
        val yaw = f.t * 0.12f + f.yaw
        val pitch = -0.12f + f.pitch
        val dist = 3.2f
        val scale = s * 1.7f
        val tPhase = f.angle
        val spread = CoreKit.eased(f, SPREAD_TAU_S) { spreadOf(it) }
        val coh = cohOf(f.motion) * (if (f.motion == FaceState.LISTENING) 1f + f.amp * 2f else 1f)
        val rate = speedFor(f.motion)
        val lim = spread * 1.4f

        for (i in 0 until n) {
            // How far behind the target this fish runs, in phase units.
            val lagFrames = 0.05f / (0.95f * coh * (0.6f + seed[i] * 0.8f))
            val tt = tPhase - lagFrames / 60f * rate
            val x = (sin(tt * 0.7f) * 0.7f + offX[i] * spread).coerceIn(-lim, lim)
            val y = (sin(tt * 1.1f) * 0.35f + offY[i] * spread).coerceIn(-lim, lim)
            val z = (cos(tt * 0.9f) * 0.7f + offZ[i] * spread).coerceIn(-lim, lim)
            CoreKit.proj(f, x, y, z, yaw, pitch, dist, scale, cx, cy)
            qx[i] = CoreKit.px; qy[i] = CoreKit.py; qz[i] = CoreKit.pz; qd[i] = CoreKit.pd
            // Heading: the target's own velocity at that moment.
            var vx = 0.49f * cos(tt * 0.7f)
            var vy = 0.385f * cos(tt * 1.1f)
            var vz = -0.63f * sin(tt * 0.9f)
            val vl = kotlin.math.sqrt(vx * vx + vy * vy + vz * vz).coerceAtLeast(1e-6f)
            vx /= vl; vy /= vl; vz /= vl
            CoreKit.rot3(f, vx, vy, vz, yaw, pitch)
            ang[i] = kotlin.math.atan2(CoreKit.ry, CoreKit.rx)
            // The flank is perpendicular to travel; the flash is its dot
            // with the light, cubed so it reads as a glint, not a gradient.
            val flank = kotlin.math.abs(CoreKit.rx * lightY - CoreKit.ry * lightX)
            flash[i] = flank * flank * flank
        }
        CoreKit.sortFarFirst(order, qz, n, fresh = n != lastN)
        lastN = n

        val toDeg = 180f / PI.toFloat()
        val bodyPath = body
        val tailPath = tail
        for (k in 0 until n) {
            val i = order[k]
            val d = qd[i]
            val len = s * 0.042f * d * (0.6f + seed[i] * 0.7f)
            val col = mix(CoreKit.shade(cool, 0.5f + d * 0.6f), hot, kotlin.math.min(1f, flash[i] * 1.4f))
            val a = kotlin.math.min(1f, 0.25f + d * 0.6f)
            drawContext.canvas.save()
            drawContext.transform.translate(qx[i], qy[i])
            drawContext.transform.rotate(ang[i] * toDeg, pivot = Offset.Zero)
            drawContext.transform.scale(len, len, pivot = Offset.Zero)
            drawPath(bodyPath, color = col, alpha = a)
            drawPath(tailPath, color = col, alpha = a)
            drawContext.canvas.restore()
        }
        drawContext.canvas.restore() // CoreKit.clipToView
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
    //
    // And compiled LAZILY, on this face's first draw. It used to be a plain
    // `val`, which runs when the `Nucleus` object is first touched - and
    // `Faces.all` touches every face, so the very first `Faces.byId` at
    // startup compiled this 72-step raymarch on the main thread whatever face
    // was actually chosen. Now an owner who never picks Nucleus never pays
    // for it. `draw` is only ever called on the main thread, so the default
    // synchronized lazy costs one uncontended check per frame.
    private val shader by lazy { android.graphics.RuntimeShader(AGSL) }

    // The brush is only a wrapper that hands `shader` back, and `shader` is
    // already a single reused instance - so building one per frame was a fresh
    // object 120 times a second for nothing. Lazy for the same reason the
    // shader is: both are built on the same first-draw path.
    private val shaderBrush by lazy { androidx.compose.ui.graphics.ShaderBrush(shader) }

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
            brush = shaderBrush,
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

/**
 * A real parametric torus, meshed and shaded on the GPU - this app's second
 * mesh face, and its first that isn't a single fragment shader. The mesh
 * generation, both shaders, and the rendering pipeline itself (a
 * `GLSurfaceView` running real GLES 3.0, embedded in Compose alongside this
 * file's `DrawScope`-based faces) live in `com.jarvis.client.face.gl` -
 * `TokamakRenderer` specifically, with the reasoning for what was ported
 * faithfully and what was deliberately dropped in its own doc comment there,
 * matching Nucleus's own.
 *
 * `draw` below is never called. `FaceView` checks `MeshFaces.rendererFor`
 * before it ever reaches a face's own `draw`, and swaps in the GL surface
 * for any id that returns a renderer - `tokamak` is one. This still has to
 * be a full `Face` (id, name, fit, speedFor) because the picker, `Faces.all`
 * and every spec-drift check key on those the same way for every face
 * regardless of how it actually renders; only the drawing itself forks.
 */
object Tokamak : Face {
    override val id = "tokamak"
    override val name = "Tokamak"

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.5f
        FaceState.THINKING -> 0.9f
        FaceState.SPEAKING -> 0.4f
        else -> 0.3f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        error(
            "Tokamak renders through com.jarvis.client.face.gl.TokamakRenderer, " +
                "not DrawScope - FaceView should have checked MeshFaces.rendererFor(\"tokamak\") " +
                "before this was ever called.",
        )
    }
}

/**
 * A real spring-mass drum skin, Verlet-integrated on a GLES 3.0 mesh - the
 * twentieth face, and the last one. The simulation, the shaders, and the
 * mesh upload live in `com.jarvis.client.face.gl.MembraneRenderer`, with
 * the reasoning for what was ported faithfully and what genuinely has no
 * Android equivalent (a global `SPEED` slider driving substeps, a
 * touch-driven strike point, camera auto-rotation this face's own
 * reference never had) in its own doc comment there.
 *
 * `draw` below is never called, for the same reason as `Tokamak`'s:
 * `FaceView` checks `MeshFaces.rendererFor` first and swaps in the GL
 * surface for any id that returns a renderer.
 *
 * Unlike every other face this session added, this one genuinely cannot be
 * pinned: `MembraneRenderer` holds real per-frame simulation state (Verlet
 * needs the previous two heights to compute the next one, not just `t`),
 * so it joins `iris` by name in `SpecDriftTest`'s pinned exact set of
 * unpinnable faces, argued there rather than loosened quietly.
 */
object Membrane : Face {
    override val id = "membrane"
    override val name = "Membrane"

    // MembraneRenderer never reads f.angle - its camera is touch-only and
    // its physics runs on real elapsed time, both by design (see its own
    // doc comment). These numbers exist only to satisfy Face's shared
    // contract with something in the same range every other face uses, not
    // because anything here consumes them; they borrow the reference's own
    // per-state "drive" values rather than inventing separate ones.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.85f
        FaceState.THINKING -> 1.25f
        FaceState.SPEAKING -> 0.60f
        else -> 0.30f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        error(
            "Membrane renders through com.jarvis.client.face.gl.MembraneRenderer, " +
                "not DrawScope - FaceView should have checked MeshFaces.rendererFor(\"membrane\") " +
                "before this was ever called.",
        )
    }
}
