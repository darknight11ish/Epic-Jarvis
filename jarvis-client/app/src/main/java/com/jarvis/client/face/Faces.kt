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
 * Spectrum, Coreplate, Workbench, Swarm, Shoal and Accretion are a
 * different case, and it is worth being honest about which. The spec marks
 * all six `integrates_per_frame: true` because their JS/desktop reference
 * genuinely does carry state between frames — a running FFT smoother, boid
 * velocities, a DLA grid. None of that was ported here as frame-to-frame
 * state. Each one is instead reimplemented as a deterministic function of `t`
 * (Accretion: of the walker count `f.tableAngle` implies, see its own
 * comment), a fixed per-element seed (`hash01` or a seeded `Random`), and `f.amp` — which
 * is already smoothed upstream by `FaceHost.advance()`, so there is no
 * envelope left to track locally. Nothing here is appended to, removed from,
 * or nudged by its own last frame; call `draw` with the same `(t, amp)` twice
 * and it draws the same picture twice. That makes these six exactly as
 * pinnable as Rime and Kirkwood, even though the spec's flag — describing the
 * *reference's* technique, not this port's — says otherwise. See
 * `SpecDriftTest`'s `iris membrane and cascade are the only offered faces
 * that cannot be pinned` for where that distinction is enforced and argued in
 * more detail.
 *
 * Membrane is the one face here that genuinely cannot make that same claim.
 * Its Verlet simulation needs the previous two frames' heights to compute
 * the next one - a real dependency on its own history, not a description of
 * a technique this port declined to use. It joins `iris` in that same test's
 * pinned exact set, by name, argued there rather than folded into the
 * deterministic six above where it would not belong.
 *
 * Cascade joined it. It was the seventh "deterministic" face until it was
 * ported to the reactor kit's own particle system: a parcel's path depends
 * on the drag and random walk of every tick before it and on the flow of
 * whichever state was showing when it fell, and a pure function of the
 * frame could only fake that - which is exactly what it used to do, as a
 * field of dashes on a fixed fall cycle that looked nothing like the kit.
 * Its own comment says how little history it keeps (the last ~4 seconds).
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
        // Every interior vertex of the winding is shared by two segments, and
        // `point` was called for both ends of every one of them: 180 calls where
        // 91 do, each costing three trig calls plus an Offset allocation. Carrying
        // the previous segment's end forward halves both. The two calls were
        // computing the same u from the same expression - `(k + 1) / segs`, then
        // `k / segs` one iteration later - so the line ends are bit-identical and
        // nothing on screen moves.
        var p0 = point(0f)
        for (k in 0 until segs) {
            val u0 = k / segs.toFloat()
            val u1 = (k + 1) / segs.toFloat()
            val p1 = point(u1)
            val s = sin(u0 * PI2 * 2f - f.t * 2.2f)
            val flow = s * s * s * s
            drawLine(
                color = mix(hot, Color.White, flow.coerceIn(0f, 1f)),
                start = p0,
                end = p1,
                strokeWidth = (r * 0.008f * (1f + flow * 2f)).coerceAtLeast(0.6f),
            )
            p0 = p1
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
        // A zero-size layout (r == 0) makes the scan-plane falloff below divide
        // by zero, and the NaN that comes out does NOT merely draw nothing: it
        // flows through mix() in Resolve.kt into Color(red, green, blue, alpha),
        // whose `require` on the three colour channels rejects NaN and throws
        // IllegalArgumentException. So the failure mode is a crashed draw, not a
        // blank face. There is nothing to draw at zero radius anyway, so stop.
        if (r <= 0f) return@with
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
        // Hoisted, exactly the way Orbit already hoists its inclination above.
        // The yaw is one number for the whole draw, but these were evaluated
        // inside the 160-agent loop: 320 redundant trig calls a frame, roughly
        // 38,000 a second at 120fps, for two values that cannot differ between
        // agents. Same numbers out, a great deal less arithmetic in.
        val cyw = cos(f.yaw)
        val syw = sin(f.yaw)
        val pull = (1f - f.amp * 0.6f).coerceIn(0.35f, 1f)
        for (i in 0 until N) {
            val orbit = f.t * (0.3f + seedR[i] * 0.2f) + seedA[i]
            val wob = f.t * (0.6f + seedR[i] * 0.4f) + seedB[i]
            val rr = seedR[i] * pull
            val x0 = cos(orbit) * rr
            val y0 = sin(wob) * rr * 0.7f
            val z0 = sin(orbit) * rr
            val x = x0 * cyw - z0 * syw
            val z1 = x0 * syw + z0 * cyw
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
 * Diffusion-limited aggregation: particles wander at random until they touch
 * what is already there, then stick for good. This is the reactor kit's own
 * algorithm (`accretion` in `docs/reference/jarvis-reactor-kit.html`), ported
 * walker for walker: the 243-cell grid, the release circle just outside the
 * cluster, the kill circle at `2.2 * rmax + 8`, the 420-step walks, both
 * reset rules, and the drawing - one square per stuck cell, coloured and
 * faded by its distance from the seed, with the faint rim circle on top.
 *
 * It used to be something else wearing the name: five hash-seeded arms of 22
 * line segments, on the grounds that the reference's grid was "unbounded (a
 * grid that fills over minutes of uptime)". That was not true of the
 * reference. Its grid is bounded (243 x 243 here, see [GW]), it starts over
 * the moment the coral reaches the rim circle or covers 5.5% of the grid,
 * and one whole growth takes about 9,000-12,000 walkers - four or five
 * seconds at idle. Bounded, cheap (~15,000 random-walk steps a frame), and
 * nothing like five arms. Side by side with the kit, the phone was showing
 * a different face.
 *
 * It is still a pure function of the frame, which is the property
 * `SpecDriftTest` pins this face on. The walker COUNT is the clock rather
 * than the frame: `f.tableAngle` - which the shell integrates from
 * [speedFor], so it already carries each state's rate, calm motion and the
 * transforms, and never runs backwards - times [WALKERS_PER_UNIT] says how
 * many walkers have been released since this face started, and each growth
 * cycle draws its random numbers from a generator seeded by that cycle's own
 * index. So the same `tableAngle` always grows the same coral however many
 * frames it took to get there; [Growth] is a cache that walks forward to
 * that count, not state the picture depends on. (One edge, stated rather
 * than hidden: a THIRD simultaneous viewer - there are two slots, for the
 * live face and a picker thumbnail - arriving far into a session cannot
 * afford the replay from zero, and restarts at the cycle that count would
 * roughly be on. Still a function of the count, just not the same coral.)
 *
 * What differs from the kit, deliberately:
 *  - The kit's listening rate is also multiplied by `1 + amp * 2`. `f.amp`
 *    is instantaneous; integrating it would make the walker count depend on
 *    the microphone's whole history instead of on the frame. Listening still
 *    grows at twice idle's rate, from [speedFor].
 *  - Thinking in the kit sticks only 70% of the time. Which walkers get
 *    rejected would depend on WHEN each was released, i.e. on the state
 *    history, for the same reason. Every walker sticks here; thinking's coral
 *    is a little less furry than the kit's, and grows at its 1.5x rate.
 *  - The kit's rate is per display frame, so it grows twice as fast on a
 *    120 Hz panel as on a 60 Hz one. This is the kit at 60 Hz, everywhere.
 */
object Accretion : Face {
    override val id = "accretion"
    override val name = "Accretion"

    // The kit's walkers per frame - idle 40, listening 80, thinking 60,
    // speaking 22 - as multiples of idle's. The shell integrates these into
    // `f.tableAngle`, which is what the walker count reads.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 2.0f
        FaceState.THINKING -> 1.5f
        FaceState.SPEAKING -> 0.55f
        else -> 1.0f
    }

    /**
     * The kit's `small_n(w, 84, 128)` in its solo view, which runs every face
     * at a detail of 1.9 ("solo is what Jarvis will really look like"): 128 x
     * 1.9 = 243 on any phone-sized face. The gallery's 128 is a thumbnail's
     * grid; at 243 the coral is twice as fine, cells ~2 px on a phone.
     */
    private const val GW = 243
    /** Idle's 40 walkers a frame, at 60 frames a second. */
    private const val WALKERS_PER_UNIT = 40f * 60f
    private const val MID = (GW - 1) / 2f
    /** The rim circle; the coral starts over just inside it. */
    private const val R0 = MID * 0.94f
    /** `(GW/2)|0` in both axes - one cell off true centre, as in the kit. */
    private const val SEED_CELL = (GW / 2) * GW + GW / 2
    /** The kit's other reset: 5.5% of the grid covered. */
    private const val FILL_LIMIT = GW * GW * 0.055f
    private const val WALK_STEPS = 420
    /**
     * The most walkers one draw will replay to catch up. The live face moves
     * 20-160 walkers a frame; a picker thumbnail starts from zero at ~3,000
     * (~1 M random-walk steps, once, when the picker opens). Anything past
     * this is the third-viewer edge described above.
     */
    private const val CATCH_UP_MAX = 6_000L
    /** A typical cycle's walker count at GW 243, used only by that edge. */
    private const val TYPICAL_CYCLE = 10_000L

    /** The kit's `d`: each cell's distance from the seed, over MID. Fixed. */
    private val dist = FloatArray(GW * GW) { q ->
        val dx = q % GW - MID
        val dy = q / GW - MID
        kotlin.math.sqrt(dx * dx + dy * dy) / MID
    }

    private class Growth {
        val grid = BooleanArray(GW * GW)
        var cells = 0
        var rmax = 1f
        var cycle = 0
        var released = -1L
        var rng = 1
        var lastUse = 0L

        fun reset(nextCycle: Int) {
            grid.fill(false)
            grid[SEED_CELL] = true
            cells = 1
            rmax = 1f
            cycle = nextCycle
            // Any odd-mixed nonzero seed; xorshift must never be handed 0.
            rng = (nextCycle * -1640531535 + 0x5BD1E995) or 1
        }

        /** xorshift32 -> [0, 1). Math.random's stand-in, seeded per cycle. */
        fun next(): Float {
            var x = rng
            x = x xor (x shl 13)
            x = x xor (x ushr 17)
            x = x xor (x shl 5)
            rng = x
            return (x ushr 8) * (1f / 16_777_216f)
        }

        /** One walker, released, walked and (maybe) stuck - the kit's inner loop. */
        fun walk() {
            // The kit checks the fill limit once at the top of each frame;
            // per walker is the same rule without a frame to hang it on.
            if (cells > FILL_LIMIT) reset(cycle + 1)
            val rl = minOf(R0, rmax + 3f)
            val rk = minOf(MID - 1f, rmax * 2.2f + 8f)
            val rk2 = rk * rk
            val a = next() * PI2
            // Math.round, which rounds halves up.
            var x = kotlin.math.floor(MID + cos(a) * rl + 0.5f).toInt()
            var y = kotlin.math.floor(MID + sin(a) * rl + 0.5f).toInt()
            for (s in 0 until WALK_STEPS) {
                x += (next() * 3f).toInt() - 1
                y += (next() * 3f).toInt() - 1
                if (x < 1 || y < 1 || x >= GW - 1 || y >= GW - 1) break
                val dx = x - MID
                val dy = y - MID
                val rr2 = dx * dx + dy * dy
                if (rr2 > rk2) break
                val q = y * GW + x
                if (grid[q - 1] || grid[q + 1] || grid[q - GW] || grid[q + GW]) {
                    // The kit counts a stick even when the walker is standing
                    // on a cell that is already set; so does this, since the
                    // count is what the fill limit reads.
                    grid[q] = true
                    cells++
                    val rr = kotlin.math.sqrt(rr2)
                    if (rr > rmax) rmax = rr
                    break
                }
            }
            released++
            if (rmax > R0 - 2f) reset(cycle + 1)
        }
    }

    private val slots = arrayOf(Growth(), Growth())
    private var uses = 0L

    /** The coral after [target] walkers, from whichever slot can reach it. */
    private fun growthAt(target: Long): Growth {
        uses++
        var best: Growth? = null
        for (s in slots) {
            if (s.released < 0 || s.released > target || target - s.released > CATCH_UP_MAX) continue
            if (best == null || s.released > best.released) best = s
        }
        val g = best ?: slots.minBy { it.lastUse }.also { fresh ->
            if (target <= CATCH_UP_MAX) {
                fresh.reset(0)
                fresh.released = 0L
            } else {
                // The third-viewer edge: see the class comment.
                fresh.reset((target / TYPICAL_CYCLE).toInt())
                fresh.released = target
            }
        }
        while (g.released < target) g.walk()
        g.lastUse = uses
        return g
    }

    private fun shade(c: Color, m: Float) = Color(c.red * m, c.green * m, c.blue * m, c.alpha)

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val g = growthAt((f.tableAngle * WALKERS_PER_UNIT).toLong().coerceAtLeast(0L))

        // The kit's canvas is `min(w, h)` = S wide and its faces reach about
        // 0.44 S; this app hands every face its radius r instead, so S = 2r -
        // the same equivalence Nucleus's shader uses (p = 1 at r). The grid
        // spans the whole of S, as the kit's does, so a cell is S / GW, and
        // each is drawn 1.25 cells wide so neighbours overlap into a
        // continuous branch rather than a lattice - the kit's own numbers.
        val sz = r * 2f
        val cell = sz / GW
        val ox = cx - sz / 2f
        val oy = cy - sz / 2f
        val side = androidx.compose.ui.geometry.Size(cell * 1.25f, cell * 1.25f)
        // Age is encoded by distance from the seed, so the tips read hot.
        val base = shade(cool, 0.55f)
        val grid = g.grid
        for (y in 0 until GW) {
            val row = y * GW
            for (x in 0 until GW) {
                if (!grid[row + x]) continue
                val d = dist[row + x]
                drawRect(
                    color = mix(base, hot, minOf(1f, d * 1.5f)),
                    topLeft = Offset(ox + x * cell, oy + y * cell),
                    size = side,
                    alpha = (0.55f + d * 0.45f).coerceAtMost(1f),
                )
            }
        }
        // The rim the coral resets at. The kit's `lineWidth = 1` is one
        // backing-store pixel, which at its default quality on a phone is
        // almost exactly one device pixel - so a hairline here too.
        drawCircle(
            color = cool,
            radius = R0 * cell,
            center = Offset(cx, cy),
            alpha = 0.22f,
            style = Stroke(width = 1f),
        )
    }
}

/**
 * Water leaves the lip as a coherent sheet and only breaks up once it has
 * fallen far enough for drag to win: glassy at the top, shredding in the
 * middle, spray at the bottom, and a plume where the parcels bounce off the
 * pool. The reactor kit's own particle system (`cascade` in
 * `docs/reference/jarvis-reactor-kit.html`), ported parcel for parcel: the
 * lip and its two ledges, the gradient sheet, per-parcel gravity, speed-
 * dependent drag and a lateral random walk that grows with age, one bounce
 * at 0.84 of the height, the plunge-pool glow, and each parcel drawn as a
 * streak along its own velocity that thins and fades as it breaks up.
 *
 * It used to be 260 vertical dashes on a fixed fall cycle between two
 * points, with a bar for the lip and a flat disc for the pool - no sheet, no
 * drag, no spray, no bounce, a quarter of the kit's parcel count, and hard
 * 0.6 px floors under widths the kit scales with the face. Recognisably
 * "falling", but not this face.
 *
 * This one is genuinely stateful, and says so: a parcel's path depends on
 * the drag and the random walk of every tick before it, and on the flow and
 * spread of whichever state was showing when it fell - none of which a
 * function of the current frame can know. Making it one (the old approach)
 * is what produced the dashes: a pure function of `t` has to either rescale
 * every parcel in flight the instant the state changes, or give up the
 * physics. So `cascade` moves out of `SpecDriftTest`'s "deterministic
 * despite the spec flag" set and into its stateful set, argued there.
 *
 * The state is kept as small and as honest as that allows:
 *  - It ticks at a fixed 60 per unit of `f.tableAngle` ([speedFor] is 1 for
 *    every state, so that is 60 a second times the shell's transform rate
 *    and calm motion - BANKED's stopped clock stops the water too). The kit
 *    ticks once per display frame instead, so it pours twice as fast on a
 *    120 Hz panel; this is the kit at 60 Hz.
 *  - A parcel lives at most ~250 ticks, so the picture never depends on
 *    more than the last ~4 seconds. When the clock jumps (a new host, a
 *    picker thumbnail, a long stall), [pour] refills the last 250 ticks from
 *    a seed fixed by the tick count rather than trying to be continuous with
 *    a history it does not have.
 *  - Two slots, like Accretion's, so a thumbnail and the live face do not
 *    keep throwing each other's water away.
 *
 * Cost: up to 1,400 parcels, one `drawLine` each - about 1-3 ms a frame on a
 * mid-range phone at thinking's flow, the most expensive canvas face in this
 * file after Kirkwood. The kit caps at the same 1,400.
 */
object Cascade : Face {
    override val id = "cascade"
    override val name = "Cascade"

    // faces[].render.fit for cascade: the lip ledges run to the edge of the
    // kit's canvas, so the whole picture is pulled in. Was left at the
    // default 1, so the phone drew this face 22% larger than the kit does.
    override val fit: Float = 0.82f

    // Not a spin rate - this face has none. 1 for every state makes
    // `f.tableAngle` a plain clock carrying only the shell's transform rate
    // and calm motion, which is what the particle ticks run on. Per-state
    // pace lives in the flow table below, as it does in the kit.
    override fun speedFor(motion: FaceState) = 1f

    private data class St(val flow: Float, val spread: Float)

    private fun stFor(motion: FaceState): St = when (motion) {
        FaceState.LISTENING -> St(flow = 130f, spread = 0.20f)
        FaceState.THINKING -> St(flow = 220f, spread = 0.34f)
        FaceState.SPEAKING -> St(flow = 100f, spread = 0.17f)
        else -> St(flow = 70f, spread = 0.14f)
    }

    private const val TICKS_PER_UNIT = 60f
    /** The kit's `parts.slice(-1400)`: the oldest parcels go first. */
    private const val CAP = 1400
    /** Room for one tick's emission on top of CAP (listening at full mic: 38). */
    private const val HEADROOM = 64
    /** `life > 4` at 0.016 a tick. Nothing older than this is on screen. */
    private const val LONGEST_LIFE_TICKS = 251
    /** The kit removes a parcel 20 px below its ~1,100 px canvas. */
    private const val REMOVE_BELOW = 1.018f

    // Geometry in the kit's canvas units, 0..1 across its square.
    private const val LIP_Y = 0.16f
    private const val LIP_X0 = 0.30f
    private const val LIP_X1 = 0.70f
    private const val BOUNCE_Y = 0.84f

    /** One pour of water: parcels in birth order, oldest first, as the kit's array. */
    private class Pour {
        val x = FloatArray(CAP + HEADROOM)
        val y = FloatArray(CAP + HEADROOM)
        val vx = FloatArray(CAP + HEADROOM)
        val vy = FloatArray(CAP + HEADROOM)
        val rad = FloatArray(CAP + HEADROOM)
        val life = FloatArray(CAP + HEADROOM)
        val bounced = BooleanArray(CAP + HEADROOM)
        var n = 0
        var tick = -1L
        var rng = 1
        var lastUse = 0L

        fun restart(atTick: Long) {
            n = 0
            tick = atTick
            rng = (atTick.toInt() * -1640531535 + 0x27D4EB2F) or 1
        }

        fun next(): Float {
            var v = rng
            v = v xor (v shl 13)
            v = v xor (v ushr 17)
            v = v xor (v shl 5)
            rng = v
            return (v ushr 8) * (1f / 16_777_216f)
        }

        /** One tick of the kit's update, at SPEED 1. */
        fun step(st: St, flowK: Float) {
            // `for(i=0; i<flow*.12; i++)`: the kit emits the CEILING of that,
            // nine a tick at idle.
            val emit = st.flow * flowK * 0.12f
            var i = 0
            while (i < emit && n < x.size) {
                x[n] = LIP_X0 + next() * (LIP_X1 - LIP_X0)
                y[n] = LIP_Y
                vx[n] = (next() - 0.5f) * 0.4f
                vy[n] = 1f + next() * 0.6f
                rad[n] = 0.4f + next() * 1.5f
                life[n] = 0f
                bounced[n] = false
                n++
                i++
            }
            var k = 0
            for (j in 0 until n) {
                val lf = life[j] + 0.016f
                var nvy = vy[j] + 0.09f
                // Drag grows with speed, which is what shreds the sheet. (On
                // the way back UP after the bounce vy is negative and this
                // briefly becomes a push - the kit's formula, kept.)
                nvy *= 1f - minOf(0.06f, nvy * 0.004f)
                var nvx = vx[j] + (next() - 0.5f) * st.spread * 0.5f * minOf(1f, lf * 2f)
                val nx = x[j] + nvx * 0.012f
                val ny = y[j] + nvy * 0.012f
                var nr = rad[j]
                var nb = bounced[j]
                if (ny > BOUNCE_Y && !nb) {
                    nb = true
                    nvy *= -0.32f
                    nvx += (next() - 0.5f) * 4f
                    nr *= 0.6f
                }
                if (ny > REMOVE_BELOW || lf > 4f) continue
                x[k] = nx; y[k] = ny; vx[k] = nvx; vy[k] = nvy
                rad[k] = nr; life[k] = lf; bounced[k] = nb
                k++
            }
            n = k
            if (n > CAP) {
                val drop = n - CAP
                x.copyInto(x, 0, drop, n); y.copyInto(y, 0, drop, n)
                vx.copyInto(vx, 0, drop, n); vy.copyInto(vy, 0, drop, n)
                rad.copyInto(rad, 0, drop, n); life.copyInto(life, 0, drop, n)
                bounced.copyInto(bounced, 0, drop, n)
                n = CAP
            }
            tick++
        }
    }

    private val pours = arrayOf(Pour(), Pour())
    private var uses = 0L

    /** The water at [target] ticks: advanced, or refilled if it cannot be. */
    private fun pour(target: Long, st: St, flowK: Float): Pour {
        uses++
        var best: Pour? = null
        for (p in pours) {
            if (p.tick < 0 || p.tick > target || target - p.tick > LONGEST_LIFE_TICKS) continue
            if (best == null || p.tick > best.tick) best = p
        }
        val p = best ?: pours.minBy { it.lastUse }.also {
            it.restart(maxOf(0L, target - LONGEST_LIFE_TICKS))
        }
        while (p.tick < target) p.step(st, flowK)
        p.lastUse = uses
        return p
    }

    private fun shade(c: Color, m: Float) = Color(c.red * m, c.green * m, c.blue * m, c.alpha)

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = with(scope) {
        val st = stFor(f.motion)
        val flowK = if (f.motion == FaceState.LISTENING) 1f + f.amp * 1.4f else 1f
        val p = pour((f.tableAngle * TICKS_PER_UNIT).toLong().coerceAtLeast(0L), st, flowK)

        // The kit's square canvas is S = 2r across (see Accretion), and
        // everything below is in its 0..1 units: u across, v down.
        val sz = r * 2f
        val left = cx - r
        val top = cy - r
        fun px(u: Float) = left + u * sz
        fun py(v: Float) = top + v * sz

        // The kit's canvas edge clips parcels that fly out sideways after
        // the bounce. `fit` shrinks the drawing, not the canvas, so the card
        // edge is at r / fit from the centre, not at r.
        val card = r / fit
        drawContext.canvas.save()
        drawContext.transform.clipRect(cx - card, cy - card, cx + card, cy + card)

        // The coherent sheet at the top, before break-up.
        drawRect(
            brush = androidx.compose.ui.graphics.Brush.verticalGradient(
                colors = listOf(hot.copy(alpha = 0.55f), hot.copy(alpha = 0f)),
                startY = py(LIP_Y),
                endY = py(0.52f),
            ),
            topLeft = Offset(px(LIP_X0), py(LIP_Y)),
            size = androidx.compose.ui.geometry.Size((LIP_X1 - LIP_X0) * sz, 0.36f * sz),
        )

        // Parcels: streaks while fast, dots once broken up. Widths scale with
        // the face as the kit's do (`r * S * .0035`, 0.75-3.6 px on a 1080 px
        // face); the 0.5 floor is the kit's own, in its pixels.
        for (j in 0 until p.n) {
            val age = minOf(1f, p.life[j] * 1.3f)
            val a = 0.10f + (1f - age) * 0.35f + if (p.bounced[j]) 0.18f else 0f
            val x = p.x[j]
            val y = p.y[j]
            drawLine(
                color = hot,
                start = Offset(px(x), py(y)),
                end = Offset(px(x - p.vx[j] * 0.010f), py(y - p.vy[j] * 0.014f)),
                strokeWidth = maxOf(0.5f, p.rad[j] * sz * 0.0035f * (1f - age * 0.4f)),
                alpha = a.coerceAtMost(1f),
            )
        }

        // Plunge pool: the kit's radial glow, cut off at the canvas bottom.
        drawRect(
            brush = androidx.compose.ui.graphics.Brush.radialGradient(
                colors = listOf(hot.copy(alpha = 0.20f), hot.copy(alpha = 0f)),
                center = Offset(px(0.5f), py(0.88f)),
                radius = 0.42f * sz,
            ),
            topLeft = Offset(px(0f), py(0.7f)),
            size = androidx.compose.ui.geometry.Size(sz, 0.3f * sz),
        )

        // The lip itself: two ledges, and the bright edge the water leaves.
        val ledge = shade(cool, 0.5f)
        val ledgeH = 0.05f * sz
        drawRect(
            color = ledge,
            topLeft = Offset(px(0f), py(LIP_Y) - ledgeH),
            size = androidx.compose.ui.geometry.Size(LIP_X0 * sz, ledgeH),
        )
        drawRect(
            color = ledge,
            topLeft = Offset(px(LIP_X1), py(LIP_Y) - ledgeH),
            size = androidx.compose.ui.geometry.Size((1f - LIP_X1) * sz, ledgeH),
        )
        val edge = maxOf(1f, sz * 0.005f)
        drawLine(hot, Offset(px(0f), py(LIP_Y)), Offset(px(LIP_X0), py(LIP_Y)), edge, alpha = 0.5f)
        drawLine(hot, Offset(px(LIP_X1), py(LIP_Y)), Offset(px(1f), py(LIP_Y)), edge, alpha = 0.5f)

        drawContext.canvas.restore()
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
 * is no older device to fall back from. It shades one fragment per real
 * device pixel, which is already as sharp as the kit gets (the kit renders
 * this at 0.8x device pixels at its default quality, and upscales).
 *
 * The march, the field and the lighting are a close port of the reference's
 * own GPU shader (`NUCLEUS_FS` in the desktop's `faces.html`). Unlike the
 * object-rotation faces elsewhere in this file, a ray-based camera needs its
 * origin and its ray directions built from the exact same rotation, so this
 * keeps the reference's own pitch-then-yaw camera formula rather than
 * reordering it to match Geodesic's yaw-then-pitch convention. `uYaw` and
 * `uPit` still feed from `f.angle`, `f.yaw` and `f.pitch` the same way every
 * other 3D face here does, and the screen-to-object-space mapping is redone
 * for a circle (`(fragCoord - uCenter) / uR`) rather than ported from the
 * reference's square canvas (`(fragCoord - 0.5*res) / min(res.x, res.y)`) -
 * the two are the same normalisation for the shape this app actually draws.
 *
 * With one correction that port missed: the reference's `gl_FragCoord` - and
 * its CPU fallback, which says so explicitly (`v = -(py / R - .5) * 2`) -
 * counts y UP the screen. AGSL's `fragCoord` counts it DOWN. Porting the
 * normalisation without flipping y rendered the nucleus upside down: lit
 * from below instead of above, and the ring seen from underneath instead of
 * from the kit's "look down on it" angle. `p.y` is negated below.
 *
 * Two things ARE dropped:
 *  - `HUD.beat`, a global heartbeat pulse with nothing this app tracks to
 *    drive it. It only ever scaled the field's blend radii; at a fixed 1 the
 *    `M()` wrapper the reference uses to apply it becomes the identity, so
 *    this calls `field()` directly and the wrapper is gone rather than kept
 *    around multiplying by one.
 *  - The reference's own hardcoded per-state glow/hot colours. Every other
 *    face in this file shades with the `hot`/`cool` this call is handed -
 *    the user's own chosen binding for the current state - and a face that
 *    quietly used its own fixed palette instead would be the one face immune
 *    to the colour picker. Geometry (the blend/ring/displacement numbers,
 *    which have no user-facing control) keeps the reference's own per-state
 *    table; colour does not.
 *
 * The environment reflection used to be a third drop ("there is no panorama
 * to sample on a phone"). There is - the kit's own, in [EnvMap] - and it is
 * sampled here exactly as the kit's `envSample` does, four-tap tent and all.
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
    //
    // The panorama is bound here, once: it never changes, and an AGSL child
    // has to be bound before the first draw or the shader samples nothing.
    // REPEAT across, CLAMP down and bilinear, as the kit sets its texture -
    // the seam at the back of the panorama wraps, the poles do not.
    private val shader by lazy {
        android.graphics.RuntimeShader(AGSL).apply {
            setInputShader(
                "uEnv",
                android.graphics.BitmapShader(
                    EnvMap.bitmap,
                    android.graphics.Shader.TileMode.REPEAT,
                    android.graphics.Shader.TileMode.CLAMP,
                ).apply { filterMode = android.graphics.BitmapShader.FILTER_MODE_LINEAR },
            )
            setFloatUniform(
                "uEnvSize",
                EnvMap.bitmap.width.toFloat(),
                EnvMap.bitmap.height.toFloat(),
            )
        }
    }

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
        // The kit marches 96 steps once its buffer is over 900 px across and
        // 72 below - more steps resolve the thin fillet where the ring meets
        // the core. Its buffer is its whole canvas, which is 2r / fit here
        // (see Accretion on S = 2r; `fit` scales the drawing, not the canvas).
        shader.setIntUniform("uSteps", if (2f * r / fit > 900f) 96 else 72)

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
uniform int uSteps;
uniform shader uEnv;
uniform float2 uEnvSize;

const float TAU = 6.283185307179586;
const float3 LIGHT = float3(-0.4510, -0.7517, -0.4812);
const float DIST = 2.05;
const int MAX_STEPS = 96;

// The kit's envSample: reflect the fixed view ray about the normal, look the
// reflection up in the equirectangular panorama, and average four taps a
// texel apart - the kit's fix for bilinear showing as diamond facets when a
// 128 x 64 picture is magnified across a smooth surface. `eval` takes texel
// coordinates rather than 0..1, hence uEnvSize.
float3 envSample(float3 n) {
    float d = -n.z;
    float3 r = normalize(float3(-2.0 * d * n.x, -2.0 * d * n.y, -1.0 - 2.0 * d * n.z));
    float u = 0.5 + atan(r.x, -r.z) / TAU;
    float v = 0.5 - asin(clamp(r.y, -1.0, 1.0)) / 3.14159265;
    float2 uv = float2(u, v) * uEnvSize;
    float e = 0.75;
    // eval() hands back half4; widened explicitly rather than trusting an
    // implicit half-to-float coercion in the sum.
    float3 s = float3(uEnv.eval(uv + float2( e,  e)).rgb)
             + float3(uEnv.eval(uv + float2(-e,  e)).rgb)
             + float3(uEnv.eval(uv + float2( e, -e)).rgb)
             + float3(uEnv.eval(uv + float2(-e, -e)).rgb);
    return 0.25 * s;
}

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
    // y negated: fragCoord counts down the screen, the kit's gl_FragCoord up.
    float2 p = (fragCoord - uCenter) / uR;
    p.y = -p.y;
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

    // A constant bound with an early exit, because AGSL loops must have one;
    // uSteps is the kit's own 72-or-96.
    float hit = -1.0;
    int steps = 0;
    for (int i = 0; i < MAX_STEPS; i++) {
        if (i >= uSteps) break;
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
    float3 env = envSample(n);
    float fres = fres3(abs(dot(n, rd)));
    float ao = 1.0 - min(0.75, float(steps) / float(uSteps) * 1.5);

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
