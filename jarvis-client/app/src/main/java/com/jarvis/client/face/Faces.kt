package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.nativeCanvas
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

/**
 * Truncated icosahedron cage - the real C60, sixty atoms and ninety bonds.
 * Survives thinking and speaking where geodesic smears.
 *
 * A line-for-line port of the reactor kit's own Fullerene (the owner's
 * artifact, the `fullerene` entry in its THEMES list; the same code as the
 * desktop's `faces.html`). This face used to be a golden-angle spiral of 62
 * dots joined to their next three neighbours by index, drawn with a flat
 * depth ramp - a fuzzy ball rather than a cage, and not the molecule the
 * name promises. The geometry, the camera, the colour slots, the draw order
 * (far bonds, atoms, near bonds, so the cage reads hollow) and every size
 * now come from the kit, and every size is a share of the face rather than
 * a fixed pixel count.
 */
object Fullerene : Face {
    override val id = "fullerene"
    override val name = "Fullerene"

    // The kit's own construction: cut each icosahedral vertex, which lands
    // the new vertices one third and two thirds along each of the 30 edges -
    // 60 atoms - and a bond is every pair at the one short separation (0.35;
    // the next nearest pair is 0.57, so the 0.42 cut cannot catch a wrong one).
    // Checked once, offline, against the kit's JS: 30 edges, 60 atoms, 90 bonds.
    private val vx: FloatArray
    private val vy: FloatArray
    private val vz: FloatArray
    private val bondA: IntArray
    private val bondB: IntArray

    init {
        val t2 = (1f + kotlin.math.sqrt(5f)) / 2f
        val raw = arrayOf(
            floatArrayOf(-1f, t2, 0f), floatArrayOf(1f, t2, 0f),
            floatArrayOf(-1f, -t2, 0f), floatArrayOf(1f, -t2, 0f),
            floatArrayOf(0f, -1f, t2), floatArrayOf(0f, 1f, t2),
            floatArrayOf(0f, -1f, -t2), floatArrayOf(0f, 1f, -t2),
            floatArrayOf(t2, 0f, -1f), floatArrayOf(t2, 0f, 1f),
            floatArrayOf(-t2, 0f, -1f), floatArrayOf(-t2, 0f, 1f),
        )
        val len = kotlin.math.sqrt(1f + t2 * t2)
        val ico = raw.map { v -> floatArrayOf(v[0] / len, v[1] / len, v[2] / len) }
        fun dist(a: FloatArray, b: FloatArray): Float {
            val dx = a[0] - b[0]
            val dy = a[1] - b[1]
            val dz = a[2] - b[2]
            return kotlin.math.sqrt(dx * dx + dy * dy + dz * dz)
        }
        val atoms = ArrayList<FloatArray>(60)
        for (i in 0 until 12) {
            for (j in i + 1 until 12) {
                if (dist(ico[i], ico[j]) >= 1.2f) continue
                for (k in floatArrayOf(1f / 3f, 2f / 3f)) {
                    atoms.add(
                        floatArrayOf(
                            ico[i][0] + (ico[j][0] - ico[i][0]) * k,
                            ico[i][1] + (ico[j][1] - ico[i][1]) * k,
                            ico[i][2] + (ico[j][2] - ico[i][2]) * k,
                        ),
                    )
                }
            }
        }
        vx = FloatArray(atoms.size) { atoms[it][0] }
        vy = FloatArray(atoms.size) { atoms[it][1] }
        vz = FloatArray(atoms.size) { atoms[it][2] }
        val a = ArrayList<Int>()
        val b = ArrayList<Int>()
        for (i in atoms.indices) {
            for (j in i + 1 until atoms.size) {
                if (dist(atoms[i], atoms[j]) < 0.42f) {
                    a.add(i)
                    b.add(j)
                }
            }
        }
        bondA = a.toIntArray()
        bondB = b.toIntArray()
    }

    // Per-frame scratch, written in full before it is read - the same pattern
    // Orbital and Geodesic use, and safe for the same reason (a singleton face
    // drawn on one thread).
    private val px = FloatArray(vx.size)
    private val py = FloatArray(vx.size)
    private val pz = FloatArray(vx.size)
    private val pd = FloatArray(vx.size)
    private val bondZ = FloatArray(bondA.size)
    private val bondOrder = IntArray(bondA.size)
    private val atomOrder = IntArray(vx.size)
    private val cam = KitParity.Camera()
    private val labelPaint = KitParity.LabelPaint()

    // The kit's per-state `sp`. It spins the cage as `t * sp * 1.8`, the
    // absolute clock times the state's speed - which is exactly the pattern
    // FaceHost's angle comment explains teleports the face on every state
    // change. So the SPEED is the kit's, and the angle is FaceHost's
    // integrated one: identical while a state holds, continuous across a
    // change. The desktop's fix, kept rather than loosened to match.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.5f
        FaceState.THINKING -> 1.2f
        FaceState.SPEAKING -> 0.35f
        else -> 0.22f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        with(scope) {
            KitParity.inKitCanvas(this) {
                val px0 = KitParity.backingPx(this)
                val u = 4f * r / px0
                val mid = mix(hot, cool, 0.5f)
                // The kit's `stt` table. This face has no palette of its own
                // in the kit; its slots read PC = [hot, cool, midpoint].
                // Speaking's accent is a white literal there; here it is white
                // dimmed toward the ground like every other colour this shell
                // hands out, so a dimmed state cannot carry a full-white
                // highlight the rest of the face has given up.
                val listening = f.motion == FaceState.LISTENING
                val col: Color
                val acc: Color
                val flow: Float
                when (f.motion) {
                    FaceState.LISTENING -> { col = mid; acc = hot; flow = 1.6f }
                    FaceState.THINKING -> { col = mid; acc = mid; flow = 3.4f }
                    FaceState.SPEAKING -> { col = mid; acc = KitParity.white(f); flow = 1.0f }
                    else -> { col = cool; acc = mid; flow = 0.6f }
                }

                // Yaw and pitch are added twice, as in the kit: once here and
                // once inside its `proj`. Doubling is what the drag feels like
                // there, so it is what it feels like here.
                val ry = f.angle * 1.8f + f.yaw + f.yaw
                val rx = -0.20f + sin(f.angle * 1.1f) * 0.48f + f.pitch + f.pitch
                cam.aim(ry, rx, dist = 3.6f, scale = 4f * r * 1.35f, cx = cx, cy = cy)
                val grow = 1f + if (listening) f.amp * 0.06f else 0f
                for (i in vx.indices) {
                    cam.at(vx[i] * grow, vy[i] * grow, vz[i] * grow)
                    px[i] = cam.x
                    py[i] = cam.y
                    pz[i] = cam.z
                    pd[i] = cam.d
                }

                // Bonds behind, then atoms, then bonds in front - so the cage
                // reads hollow. Sorted far to near from the identity every
                // frame (the kit's Array.sort is stable), so the draw order is
                // a function of this frame alone.
                for (k in bondA.indices) {
                    bondZ[k] = (pz[bondA[k]] + pz[bondB[k]]) / 2f
                    bondOrder[k] = k
                }
                KitParity.sortFarFirst(bondOrder, bondZ)

                var drewFar = false
                for (pass in 0..1) {
                    val far = pass == 0
                    for (k in bondOrder) {
                        if ((bondZ[k] > 0f) != far) continue
                        val a = bondA[k]
                        val b = bondB[k]
                        // Charge circulating around the cage. The kit phases it
                        // on the bond's position in ITS canvas pixels, so the
                        // position is mapped back into those before use - on
                        // raw phone pixels the bands would be a different width.
                        val kitX = px0 + ((px[a] - cx) + (py[a] - cy)) / u
                        val ph = sin(kitX * 0.01f + f.t * flow) * 0.5f + 0.5f
                        val ink = mix(KitParity.shade(col, 0.5f + pd[a] * 0.6f), acc, ph * 0.7f)
                        drawLine(
                            color = ink,
                            start = Offset(px[a], py[a]),
                            end = Offset(px[b], py[b]),
                            strokeWidth = kotlin.math.max(0.6f, px0 * 0.010f * pd[a]) * u,
                            cap = KitParity.ROUND,
                            alpha = if (far) 0.45f else 1f,
                        )
                        if (far) drewFar = true
                    }
                    if (far) {
                        // Near atoms only, far to near.
                        for (i in atomOrder.indices) atomOrder[i] = i
                        KitParity.sortFarFirst(atomOrder, pz)
                        // In the kit the atoms inherit the 0.45 alpha the far
                        // bonds left on the context - it resets to 1 only
                        // after them. That is what the cage has always looked
                        // like there, so it is matched rather than tidied.
                        val atomAlpha = if (drewFar) 0.45f else 1f
                        val rim = KitParity.shade(col, 0.7f)
                        for (i in atomOrder) {
                            if (pz[i] > 0f) continue
                            val rad = kotlin.math.max(1f, px0 * 0.019f * pd[i]) * u
                            drawCircle(
                                brush = KitParity.conical(
                                    px[i] - rad * 0.3f, py[i] - rad * 0.3f, rad * 0.1f,
                                    px[i], py[i], rad, acc, rim,
                                ),
                                radius = rad,
                                center = Offset(px[i], py[i]),
                                alpha = atomAlpha,
                            )
                        }
                    }
                }

                labelPaint.draw(
                    this, "C₆₀",
                    x = cx + (px0 * 0.06f - px0 / 2f) * u,
                    y = cy + (px0 * 0.11f - px0 / 2f) * u,
                    sizePx = KitParity.jsRound(px0 * 0.045f) * u,
                    color = acc.copy(alpha = 0.45f),
                )
            }
        }
    }
}

/**
 * The reactor kit's own camera and sizing, shared by the five faces around
 * it (Fullerene, Rime, Orbital, Geodesic, Kirkwood) so each one can be a
 * literal port of the kit's draw code rather than an approximation of it.
 *
 * Why these faces needed it: every size in the kit is a share of `S`, the
 * side of its canvas, and that canvas is sized in real pixels - device
 * pixels times a supersample (see the kit's sizeSurface). The old ports here
 * mixed shares of the radius with fixed pixel floors and a flat depth ramp,
 * and drew points a third to a half the size the kit does. Working in the
 * kit's own pixel space and converting once, through [backingPx], is what
 * makes a line here the same share of the face as the line there, on any
 * screen density.
 */
private object KitParity {
    /**
     * The kit's detail budget for the one face that fills the screen: its
     * SOLO view, which forces `detail = max(1.9, Q.detail)` and which the kit
     * itself calls "the only place worth judging sharpness". That is the
     * phone's Home face. Thumbnails are small enough that [detail]'s ramp
     * brings them back down on its own.
     */
    const val QUALITY = 1.9f

    val PLUS = androidx.compose.ui.graphics.BlendMode.Plus
    val ROUND = androidx.compose.ui.graphics.StrokeCap.Round

    /**
     * How many pixels wide the kit's canvas would be for this face: CSS width
     * times `min(dpr, 2) * 2` (the SOLO supersample), capped at 4x and at the
     * spec's `max_px` of 1800. Sizes are computed in that space and then
     * multiplied by `4r / backingPx` - the shell's radius is a quarter of the
     * face - so fit and the speech push carry through exactly as the kit's
     * `g.scale(fit * push)` does.
     */
    fun backingPx(scope: DrawScope): Float {
        val density = scope.density.coerceAtLeast(0.5f)
        val css = scope.size.minDimension / density
        val scale = kotlin.math.min(kotlin.math.min(density, 2f) * 2f, 4f)
        return kotlin.math.max(1f, kotlin.math.min(1800f, jsRound(css * scale)))
    }

    /** The kit's `detail(w, lo, hi, cap)`, at [QUALITY]. */
    fun detail(backing: Float, lo: Int, hi: Int, cap: Float = hi * 2.4f): Int {
        val k = ((backing - 200f) / 620f).coerceIn(0f, 1f)
        val n = (lo + (hi - lo) * k) * QUALITY
        return kotlin.math.max(lo, jsRound(kotlin.math.min(cap, n)).toInt())
    }

    /** JavaScript's Math.round - half up - not Kotlin's half-to-even. */
    fun jsRound(v: Float): Float = kotlin.math.floor(v + 0.5f)

    /**
     * Clips to the square the kit's canvas occupies. The kit's canvas clips
     * whatever reaches past its edge (Orbital's near lobes do); a Compose
     * Canvas does not, so without this those points would be painted over
     * whatever sits around the face.
     */
    inline fun inKitCanvas(scope: DrawScope, block: () -> Unit) {
        val half = scope.size.minDimension / 2f
        val mx = scope.size.width / 2f
        val my = scope.size.height / 2f
        val canvas = scope.drawContext.canvas
        canvas.save()
        canvas.clipRect(mx - half, my - half, mx + half, my + half)
        try {
            block()
        } finally {
            canvas.restore()
        }
    }

    /** The kit's `shade(col, m)`: every channel times m, clamped. */
    fun shade(c: Color, m: Float): Color = Color(
        red = (c.red * m).coerceIn(0f, 1f),
        green = (c.green * m).coerceIn(0f, 1f),
        blue = (c.blue * m).coerceIn(0f, 1f),
        alpha = c.alpha,
    )

    /**
     * White, dimmed the way the shell dims every colour it hands a face -
     * toward the ground, by the state's `dim`. The kit draws two literal
     * whites (Orbital's nucleus, Fullerene's speaking accent) that ignore its
     * own dim transform. Here they obey it: this can only ever take light
     * away. [Spec.BACKGROUND] stands in for the themed ground, which a face
     * is not told; every theme's well is near-black, so the difference is a
     * rounding error on a dimmed dot.
     */
    fun white(f: FaceFrame): Color =
        if (f.dim >= 1f) Color.White else mix(Spec.BACKGROUND, Color.White, f.dim)

    /**
     * The kit's radial highlight - `createRadialGradient` with two circles,
     * which Compose's `Brush.radialGradient` (one centre) cannot express.
     * Android's own two-circle RadialGradient can (API 31; minSdk is 33).
     */
    fun conical(
        x0: Float, y0: Float, r0: Float,
        x1: Float, y1: Float, r1: Float,
        c0: Color, c1: Color,
    ): androidx.compose.ui.graphics.Brush = androidx.compose.ui.graphics.ShaderBrush(
        android.graphics.RadialGradient(
            x0, y0, r0.coerceAtLeast(0f),
            x1, y1, r1.coerceAtLeast(0.01f),
            longArrayOf(
                android.graphics.Color.pack(c0.red, c0.green, c0.blue, c0.alpha),
                android.graphics.Color.pack(c1.red, c1.green, c1.blue, c1.alpha),
            ),
            null,
            android.graphics.Shader.TileMode.CLAMP,
        ),
    )

    /** The kit's radial glow: `c` at `a0` in the middle, falling to nothing at [radius]. */
    fun glow(c: Color, a0: Float, center: Offset, radius: Float) =
        radial(center, radius, 0f to c.copy(alpha = a0.coerceIn(0f, 1f)), 1f to Color.Transparent)

    /**
     * A radial gradient that falls off the way the kit's canvas gradients do.
     *
     * The kit ends its glows on `"rgba(0,0,0,0)"` - transparent BLACK - and
     * its canvas blends between stops unpremultiplied, so the colour darkens
     * toward black while the alpha fades: halfway out, a glow is a quarter as
     * bright, not half. Compose's gradient, rendered through Skia, blended the
     * same two stops premultiplied - a straight-line fade - and measured
     * against the kit that made Geodesic's node glows and Rime's frost
     * visibly larger and brighter. Android's own gradient shaders are
     * understood to blend premultiplied too, but that was not measured on a
     * device, so this does not depend on it: the kit's curve is sampled here,
     * six steps per segment, and handed over as stops that give the same
     * answer under EITHER blending rule - a fully transparent sample takes its
     * neighbour's colour, so no step ever fades toward a colour it cannot be
     * seen in.
     */
    fun radial(
        center: Offset,
        radius: Float,
        vararg stops: Pair<Float, Color>,
    ): androidx.compose.ui.graphics.Brush {
        val steps = 6
        val out = ArrayList<Pair<Float, Color>>((stops.size - 1) * steps + 1)
        for (k in 0 until stops.size - 1) {
            val (t0, c0) = stops[k]
            val (t1, c1) = stops[k + 1]
            for (j in (if (k == 0) 0 else 1)..steps) {
                val s = j / steps.toFloat()
                out.add(
                    (t0 + (t1 - t0) * s) to Color(
                        red = c0.red + (c1.red - c0.red) * s,
                        green = c0.green + (c1.green - c0.green) * s,
                        blue = c0.blue + (c1.blue - c0.blue) * s,
                        alpha = (c0.alpha + (c1.alpha - c0.alpha) * s).coerceIn(0f, 1f),
                    ),
                )
            }
        }
        for (i in out.indices) {
            if (out[i].second.alpha > 0f) continue
            val near = out.getOrNull(i - 1)?.second?.takeIf { it.alpha > 0f }
                ?: out.getOrNull(i + 1)?.second ?: continue
            out[i] = out[i].first to near.copy(alpha = 0f)
        }
        return androidx.compose.ui.graphics.Brush.radialGradient(
            *out.toTypedArray(),
            center = center,
            radius = radius.coerceAtLeast(0.01f),
        )
    }

    /**
     * An insertion sort of [order] by [z], largest (farthest) first - the
     * kit's `sort((a,b) => b.z - a.z)`. Stable like JavaScript's, and on
     * primitive arrays so a frame allocates nothing for it.
     */
    fun sortFarFirst(order: IntArray, z: FloatArray) {
        for (i in 1 until order.size) {
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

    /**
     * The kit's `proj`: rotate about Y, then X, then real perspective. [d] is
     * its depth factor, `dist / (dist + z)` raised to the spec's depth_gain -
     * 1 at the origin, above 1 in front, below behind - and is what every
     * size and alpha in these faces reads. The old ports used
     * `((z + 1) / 2)^gain`, 0 to 1, which made the far side vanish and the
     * near side no bigger than the middle.
     *
     * Yaw and pitch are NOT added here, unlike the kit's proj, so a caller
     * can see what it is doing: each face adds `f.yaw` / `f.pitch` itself,
     * as many times as the kit does.
     */
    class Camera {
        private var cyw = 1f
        private var syw = 0f
        private var cpt = 1f
        private var spt = 0f
        private var dist = 4f
        private var scale = 1f
        private var ox = 0f
        private var oy = 0f
        var x = 0f
        var y = 0f
        var z = 0f
        var d = 1f

        fun aim(ry: Float, rx: Float, dist: Float, scale: Float, cx: Float, cy: Float) {
            cyw = cos(ry)
            syw = sin(ry)
            cpt = cos(rx)
            spt = sin(rx)
            this.dist = dist
            this.scale = scale
            ox = cx
            oy = cy
        }

        fun at(px: Float, py: Float, pz: Float) {
            val x0 = px * cyw - pz * syw
            val z0 = px * syw + pz * cyw
            val y1 = py * cpt - z0 * spt
            val z1 = py * spt + z0 * cpt
            val k = scale / (dist + z1)
            x = ox + x0 * k
            y = oy + y1 * k
            z = z1
            d = (dist / (dist + z1)).pow(Spec.DEPTH_GAIN)
        }
    }

    /**
     * The kit's two chemistry labels (`C60`, and Orbital's term symbol) are
     * canvas `fillText` in a monospace face. Compose's own text drawing needs
     * a TextMeasurer, which needs a composition to build; the platform canvas
     * does not. One Paint per face, created on first draw - not at class
     * load, because `Faces.all` is touched by JVM unit tests where
     * android.graphics is a stub.
     */
    class LabelPaint {
        private val paint by lazy(LazyThreadSafetyMode.NONE) {
            android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                typeface = android.graphics.Typeface.MONOSPACE
            }
        }

        fun draw(scope: DrawScope, text: String, x: Float, y: Float, sizePx: Float, color: Color) {
            if (sizePx < 1f) return
            val p = paint
            p.textSize = sizePx
            p.color = android.graphics.Color.argb(
                color.alpha.coerceIn(0f, 1f), color.red, color.green, color.blue,
            )
            scope.drawContext.canvas.nativeCanvas.drawText(text, x, y, p)
        }
    }
}

/**
 * Snow crystal: one arm grown and mirrored six times, branching by
 * supersaturation.
 *
 * A literal port of the reactor kit's Rime. The old port here grew six
 * hash-wandered arms out along a tilted plane and swept a growth front that
 * reset; the kit's is a straight spine per arm with side branches whose
 * length follows a supersaturation band along the arm, second-order
 * branchlets on the big ones, a hexagonal plate at each tip once the crystal
 * is nearly grown, a hexagonal core and a faint frost halo. It is flat - the
 * kit's Rime has no pitch - and turns with a drag at half the yaw.
 *
 * Still a pure function of the frame: growth is `sin(angle)`, so the crystal
 * breathes in and out rather than accumulating anything.
 */
object Rime : Face {
    override val id = "rime"
    override val name = "Rime"

    // Reused for every hexagon, every frame. Lazy, not built at class load:
    // `Faces.all` is touched by JVM unit tests, where the android.graphics
    // Path underneath is a stub.
    private val path by lazy(LazyThreadSafetyMode.NONE) { androidx.compose.ui.graphics.Path() }

    // The kit's per-state `sp` - how fast the growth breathes and the crystal
    // turns - and `branch`, how long the side arms run. (`grow` is declared in
    // the kit's table but never read by its draw, so it is not carried here.)
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.3f
        FaceState.THINKING -> 0.8f
        FaceState.SPEAKING -> 0.18f
        else -> 0.10f
    }

    private fun branchFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.7f
        FaceState.THINKING -> 1.0f
        FaceState.SPEAKING -> 0.62f
        else -> 0.55f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        with(scope) {
            KitParity.inKitCanvas(this) {
                val px0 = KitParity.backingPx(this)
                val u = 4f * r / px0
                // R is 0.44 of the kit's canvas, in phone pixels.
                val big = 4f * r * 0.44f
                val phase = f.angle
                val branch = branchFor(f.motion)
                // Growth cycles, so it is always visibly forming.
                val grow = (sin(phase) * 0.5f + 0.5f) * 0.55f + 0.45f +
                    if (f.motion == FaceState.LISTENING) f.amp * 0.15f else 0f
                val centre = Offset(cx, cy)

                // Faint halo, the way frost scatters light. The kit's `col`
                // slot, which its colour binding fills with the cool colour.
                drawCircle(
                    brush = KitParity.glow(cool, 0.22f, centre, big * 1.15f),
                    radius = big * 1.15f,
                    center = centre,
                )

                val nb = KitParity.detail(px0, 7, 12)
                val turn = phase * 0.12f + f.yaw * 0.5f
                val third = PI.toFloat() / 3f
                for (arm in 0 until 6) {
                    val a = arm / 6f * PI2 + turn
                    val ca = cos(a)
                    val sa = sin(a)
                    // Arm space (along, across) to screen: the kit's
                    // translate + rotate, written out.
                    fun sx(along: Float, across: Float) = cx + along * ca - across * sa
                    fun sy(along: Float, across: Float) = cy + along * sa + across * ca

                    // Main spine.
                    drawLine(
                        color = hot,
                        start = centre,
                        end = Offset(sx(big * grow, 0f), sy(big * grow, 0f)),
                        strokeWidth = kotlin.math.max(0.8f * u, big * 0.014f),
                        cap = KitParity.ROUND,
                        alpha = 0.75f,
                    )
                    // Side branches: spacing set by the supersaturation at
                    // that radius, which bands the structure fine and coarse.
                    for (i in 1..nb) {
                        val fr = i / nb.toFloat()
                        if (fr > grow) break
                        val x = big * fr
                        val sat = 0.5f + 0.5f * sin(fr * 9.4f + phase * 2f)
                        val len = big * (0.06f + sat * 0.20f) * branch * sin(fr * PI.toFloat() * 0.9f)
                        for (s in -1..1 step 2) {
                            val ba = -s * third
                            val bx = x + cos(ba) * len
                            val by = sin(ba) * len
                            drawLine(
                                color = hot,
                                start = Offset(sx(x, 0f), sy(x, 0f)),
                                end = Offset(sx(bx, by), sy(bx, by)),
                                strokeWidth = kotlin.math.max(0.5f * u, big * 0.008f * (1f - fr * 0.4f)),
                                cap = KitParity.ROUND,
                                alpha = (0.35f + sat * 0.4f).coerceIn(0f, 1f),
                            )
                            // Second-order branchlets on the bigger side arms.
                            if (sat > 0.55f) {
                                val l2 = len * 0.34f
                                val a2 = ba + s * 0.9f
                                for (k in 1..2) {
                                    val bf = k / 3f
                                    val qx = x + (bx - x) * bf
                                    val qy = by * bf
                                    val ex = qx + cos(a2) * l2
                                    val ey = qy + sin(a2) * l2
                                    drawLine(
                                        color = hot,
                                        start = Offset(sx(qx, qy), sy(qx, qy)),
                                        end = Offset(sx(ex, ey), sy(ex, ey)),
                                        strokeWidth = kotlin.math.max(0.4f * u, big * 0.004f),
                                        cap = KitParity.ROUND,
                                        alpha = (0.22f + sat * 0.25f).coerceIn(0f, 1f),
                                    )
                                }
                            }
                        }
                    }
                    // The hexagonal plate at the tip.
                    if (grow > 0.85f) {
                        val tx = big * grow
                        val ps = big * 0.05f
                        path.reset()
                        for (i in 0 until 6) {
                            val aa = i / 6f * PI2
                            val hx = tx + cos(aa) * ps
                            val hy = sin(aa) * ps
                            if (i == 0) path.moveTo(sx(hx, hy), sy(hx, hy)) else path.lineTo(sx(hx, hy), sy(hx, hy))
                        }
                        path.close()
                        drawPath(
                            path = path,
                            color = hot,
                            alpha = 0.6f,
                            style = Stroke(width = kotlin.math.max(0.5f * u, big * 0.006f)),
                        )
                    }
                }

                // Central hexagonal core.
                val core = big * 0.085f
                path.reset()
                for (i in 0 until 6) {
                    val a = i / 6f * PI2 + turn
                    val hx = cx + cos(a) * core
                    val hy = cy + sin(a) * core
                    if (i == 0) path.moveTo(hx, hy) else path.lineTo(hx, hy)
                }
                path.close()
                drawPath(
                    path = path,
                    color = hot,
                    alpha = 0.85f,
                    style = Stroke(width = kotlin.math.max(1f * u, big * 0.012f)),
                )
            }
        }
    }
}

/**
 * Where the electron probably is: real spherical harmonics, rejection-sampled.
 *
 * A literal port of the reactor kit's Orbital. The old port here was 240
 * hashed points on a pinched shell - an orbital-shaped ball. The kit's is the
 * actual angular wavefunction Y(l, m) for s, p, d and f, sampled so the
 * density of dots really is the probability, two colours for the two signs
 * of the wavefunction, and a state that walks up the orbitals (p when idle,
 * d when listening or speaking, f when thinking), with its term symbol in the
 * corner.
 *
 * The one deliberate difference: the kit samples with Math.random, so every
 * cloud is new; here the sampler is seeded per orbital, so a given state
 * always shows the same cloud. That keeps this face a pure function of the
 * frame - the property `SpecDriftTest`'s pinned set depends on - and the
 * cloud is a cached layout, not evolving state, exactly as the kit's `pts`
 * cache is.
 *
 * Cost: 3,230 additive dots at full size (the kit's SOLO detail). They are
 * drawn unsorted: the kit sorts them far to near, but its blend is additive
 * and addition does not care about order, so the sort bought nothing.
 */
object Orbital : Face {
    override val id = "orbital"
    override val name = "Orbital"

    // Sampled clouds, keyed by (l, m, count): x, y, z, sign, jitter per point.
    // Four orbitals at two or three sizes; the bound keeps a resizing
    // thumbnail from growing it without limit.
    private val clouds = HashMap<Long, FloatArray>()
    private val cam = KitParity.Camera()
    private val labelPaint = KitParity.LabelPaint()

    // The kit gives Orbital no `sp`, so its shell spins it at 1. It does not
    // read the spin anyway: the tumble below is on the raw clock, as in the kit.
    override fun speedFor(motion: FaceState) = 1f

    private fun lOf(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 2
        FaceState.THINKING -> 3
        FaceState.SPEAKING -> 2
        else -> 1
    }

    private fun mOf(motion: FaceState) = when (motion) {
        FaceState.THINKING -> 2
        FaceState.SPEAKING -> 1
        else -> 0
    }

    /** Real spherical harmonics, written out for l = 0..3 - the kit's `Y`. */
    private fun y(l: Int, m: Int, c: Float, s: Float, ph: Float): Float = when (l) {
        0 -> 0.282f
        1 -> if (m == 0) 0.488f * c else 0.488f * s * cos(ph)
        2 -> when (m) {
            0 -> 0.315f * (3f * c * c - 1f)
            1 -> 1.092f * s * c * cos(ph)
            else -> 0.546f * s * s * cos(2f * ph)
        }
        else -> when (m) {
            0 -> 0.373f * c * (5f * c * c - 3f)
            2 -> 1.445f * s * s * c * cos(2f * ph)
            else -> 0.457f * s * (5f * c * c - 1f) * cos(ph)
        }
    }

    private fun cloud(l: Int, m: Int, want: Int): FloatArray {
        val key = (l.toLong() shl 40) or (m.toLong() shl 32) or want.toLong()
        clouds[key]?.let { return it }
        // Rejection sampling: propose a point, keep it with probability |Y|^2.
        // Same draws, same order and same acceptance test as the kit.
        val rnd = kotlin.random.Random(20260923 + l * 131 + m * 17)
        val out = FloatArray(want * 5)
        var n = 0
        var guard = 0
        while (n < want && guard++ < want * 40) {
            val uu = rnd.nextFloat() * 2f - 1f
            val ph = rnd.nextFloat() * PI2
            val c = uu
            val s = kotlin.math.sqrt((1f - c * c).coerceAtLeast(0f))
            val rr0 = rnd.nextFloat().pow(0.33f)
            val yy = y(l, m, c, s, ph)
            if (rnd.nextFloat() < yy * yy * 3.2f) {
                val rr = rr0 * (0.35f + kotlin.math.abs(yy) * 1.5f)
                val o = n * 5
                out[o] = s * cos(ph) * rr
                out[o + 1] = c * rr
                out[o + 2] = s * sin(ph) * rr
                out[o + 3] = if (yy > 0f) 1f else -1f
                out[o + 4] = rnd.nextFloat()
                n++
            }
        }
        // If the guard ever ran out, the unfilled tail is marked empty (sign 0)
        // rather than drawn as a pile of points at the origin.
        for (i in n until want) out[i * 5 + 3] = 0f
        if (clouds.size >= 12) clouds.clear()
        clouds[key] = out
        return out
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        with(scope) {
            KitParity.inKitCanvas(this) {
                val px0 = KitParity.backingPx(this)
                val u = 4f * r / px0
                val l = lOf(f.motion)
                val m = mOf(f.motion)
                val want = KitParity.detail(px0, 700, 1700)
                val pts = cloud(l, m, want)

                // A p or d cloud is close to symmetric about any single axis,
                // so it tumbles on two axes at incommensurate rates. Yaw and
                // pitch are added twice, as in the kit (here and in its proj).
                val ry = f.t * 0.42f + f.yaw + f.yaw
                val rx = -0.18f + sin(f.t * 0.27f) * 0.55f + f.pitch + f.pitch
                cam.aim(ry, rx, dist = 3.4f, scale = 4f * r * 1.5f, cx = cx, cy = cy)
                val puff = 1f + if (f.motion == FaceState.LISTENING) f.amp * 0.22f else 0f

                // The kit's slots: `col` is the structural (cool) colour and
                // takes the positive lobe; `neg` is neither hot nor cool, so its
                // colour binding gives it the midpoint.
                val pos = cool
                val neg = mix(hot, cool, 0.5f)
                for (i in 0 until want) {
                    val o = i * 5
                    val sign = pts[o + 3]
                    if (sign == 0f) continue
                    cam.at(pts[o] * puff, pts[o + 1] * puff, pts[o + 2] * puff)
                    val rad = kotlin.math.max(0.5f, px0 * 0.006f * cam.d * (0.5f + pts[o + 4])) * u
                    drawCircle(
                        color = if (sign > 0f) pos else neg,
                        radius = rad,
                        center = Offset(cam.x, cam.y),
                        alpha = (0.10f + cam.d * 0.30f).coerceIn(0f, 1f),
                        blendMode = KitParity.PLUS,
                    )
                }

                // The nucleus, and the term symbol.
                cam.at(0f, 0f, 0f)
                drawCircle(
                    color = KitParity.white(f),
                    radius = kotlin.math.max(1.5f, px0 * 0.010f) * u,
                    center = Offset(cam.x, cam.y),
                )
                labelPaint.draw(
                    this, TERMS[l] + "  m=" + m,
                    x = cx + (px0 * 0.06f - px0 / 2f) * u,
                    y = cy + (px0 * 0.11f - px0 / 2f) * u,
                    sizePx = KitParity.jsRound(px0 * 0.05f) * u,
                    color = pos.copy(alpha = 0.6f),
                )
            }
        }
    }

    private val TERMS = arrayOf("s", "p", "d", "f")
}

/**
 * A sphere that thinks in waves: a once-subdivided icosahedron, lit by waves
 * travelling across its surface.
 *
 * A literal port of the reactor kit's Geodesic. The old port here used the
 * plain 12-vertex icosahedron and one wave, and said so; the kit subdivides
 * once (42 vertices, 120 edges) and runs one wave when idle, two when
 * listening or speaking and three when thinking, each at its own rate. Lit
 * nodes carry a soft glow of their own and the centre has a faint core glow.
 *
 * Brightness is computed against the UNROTATED vertex positions, as in the
 * kit - the wave lives on the object, not the camera, so it must not depend
 * on how the sphere is turned.
 */
object Geodesic : Face {
    override val id = "geodesic"
    override val name = "Geodesic"

    private val vx: FloatArray
    private val vy: FloatArray
    private val vz: FloatArray
    private val edgeA: IntArray
    private val edgeB: IntArray

    init {
        // The kit's ICO, built the same way: the 20 icosahedral faces, each
        // split into four by its edge midpoints pushed back out to the sphere.
        // Midpoints are shared through a map, so each is made once: 12 + 30 =
        // 42 vertices and 120 edges, in the kit's own insertion order.
        val phi = (1f + kotlin.math.sqrt(5f)) / 2f
        val xs = ArrayList<Float>()
        val ys = ArrayList<Float>()
        val zs = ArrayList<Float>()
        fun push(x: Float, y: Float, z: Float): Int {
            val len = kotlin.math.sqrt(x * x + y * y + z * z)
            xs.add(x / len)
            ys.add(y / len)
            zs.add(z / len)
            return xs.size - 1
        }
        val base = arrayOf(
            floatArrayOf(-1f, phi, 0f), floatArrayOf(1f, phi, 0f),
            floatArrayOf(-1f, -phi, 0f), floatArrayOf(1f, -phi, 0f),
            floatArrayOf(0f, -1f, phi), floatArrayOf(0f, 1f, phi),
            floatArrayOf(0f, -1f, -phi), floatArrayOf(0f, 1f, -phi),
            floatArrayOf(phi, 0f, -1f), floatArrayOf(phi, 0f, 1f),
            floatArrayOf(-phi, 0f, -1f), floatArrayOf(-phi, 0f, 1f),
        )
        for (v in base) push(v[0], v[1], v[2])
        val faces = arrayOf(
            intArrayOf(0, 11, 5), intArrayOf(0, 5, 1), intArrayOf(0, 1, 7),
            intArrayOf(0, 7, 10), intArrayOf(0, 10, 11), intArrayOf(1, 5, 9),
            intArrayOf(5, 11, 4), intArrayOf(11, 10, 2), intArrayOf(10, 7, 6),
            intArrayOf(7, 1, 8), intArrayOf(3, 9, 4), intArrayOf(3, 4, 2),
            intArrayOf(3, 2, 6), intArrayOf(3, 6, 8), intArrayOf(3, 8, 9),
            intArrayOf(4, 9, 5), intArrayOf(2, 4, 11), intArrayOf(6, 2, 10),
            intArrayOf(8, 6, 7), intArrayOf(9, 8, 1),
        )
        val mid = HashMap<Int, Int>()
        fun midpoint(a: Int, b: Int): Int {
            val key = minOf(a, b) * 1000 + maxOf(a, b)
            mid[key]?.let { return it }
            val i = push((xs[a] + xs[b]) / 2f, (ys[a] + ys[b]) / 2f, (zs[a] + zs[b]) / 2f)
            mid[key] = i
            return i
        }
        val edges = LinkedHashSet<Int>()
        for (tri in faces) {
            val a = tri[0]
            val b = tri[1]
            val c = tri[2]
            val ab = midpoint(a, b)
            val bc = midpoint(b, c)
            val ca = midpoint(c, a)
            val pairs = intArrayOf(
                a, ab, ab, ca, ca, a, b, bc, bc, ab, ab, b,
                c, ca, ca, bc, bc, c, ab, bc, bc, ca, ca, ab,
            )
            for (k in pairs.indices step 2) {
                edges.add(minOf(pairs[k], pairs[k + 1]) * 1000 + maxOf(pairs[k], pairs[k + 1]))
            }
        }
        vx = xs.toFloatArray()
        vy = ys.toFloatArray()
        vz = zs.toFloatArray()
        edgeA = edges.map { it / 1000 }.toIntArray()
        edgeB = edges.map { it % 1000 }.toIntArray()
    }

    // Scratch space for one draw, kept on the face instead of reallocated -
    // every slot is written at the top of `draw` before anything reads it.
    private val px = FloatArray(vx.size)
    private val py = FloatArray(vx.size)
    private val depth = FloatArray(vx.size)
    private val bright = FloatArray(vx.size)
    private val ox = FloatArray(3)
    private val oy = FloatArray(3)
    private val oz = FloatArray(3)
    private val cam = KitParity.Camera()

    // The kit's per-state `sp`, `waves` and `rate`.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.5f
        FaceState.THINKING -> 0.85f
        FaceState.SPEAKING -> 0.4f
        else -> 0.3f
    }

    private fun wavesFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 2
        FaceState.THINKING -> 3
        FaceState.SPEAKING -> 2
        else -> 1
    }

    private fun rateFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.6f
        FaceState.THINKING -> 2.3f
        FaceState.SPEAKING -> 1.0f
        else -> 0.55f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        with(scope) {
            KitParity.inKitCanvas(this) {
                val px0 = KitParity.backingPx(this)
                val u = 4f * r / px0
                val n = vx.size
                cam.aim(
                    ry = f.angle + f.yaw,
                    rx = sin(f.t * 0.22f) * 0.45f + f.pitch,
                    dist = 3.4f, scale = 4f * r * 0.60f, cx = cx, cy = cy,
                )
                for (i in 0 until n) {
                    cam.at(vx[i], vy[i], vz[i])
                    px[i] = cam.x
                    py[i] = cam.y
                    depth[i] = cam.d
                }

                // Wave origins move over the surface; brightness is distance
                // from them.
                val waves = wavesFor(f.motion)
                val rate = rateFor(f.motion)
                for (k in 0 until waves) {
                    val a = f.t * rate * 0.6f + k * PI2 / waves
                    ox[k] = cos(a)
                    oy[k] = sin(a * 0.7f)
                    oz[k] = sin(a)
                }
                for (i in 0 until n) {
                    var best = 0f
                    for (k in 0 until waves) {
                        val dx = vx[i] - ox[k]
                        val dy = vy[i] - oy[k]
                        val dz = vz[i] - oz[k]
                        val d = kotlin.math.sqrt(dx * dx + dy * dy + dz * dz) / 2f
                        // Kotlin's % keeps the dividend's sign, as JavaScript's
                        // does, so a negative phase is excluded the same way.
                        val ph = (f.t * rate - d * 2.2f) % 2f
                        if (ph > 0f && ph < 1f) best = kotlin.math.max(best, sin(ph * PI.toFloat()))
                    }
                    bright[i] = best
                }

                for (e in edgeA.indices) {
                    val i = edgeA[e]
                    val j = edgeB[e]
                    val d = (depth[i] + depth[j]) / 2f
                    val b = (bright[i] + bright[j]) / 2f
                    // Clamped both ways: the kit's canvas ignores an alpha
                    // outside 0..1, but Compose's Color.copy throws on one.
                    drawLine(
                        color = if (b > 0.25f) mix(cool, hot, b) else cool,
                        start = Offset(px[i], py[i]),
                        end = Offset(px[j], py[j]),
                        strokeWidth = kotlin.math.max(0.4f, px0 * 0.0018f * (0.6f + b * 2.2f) * d) * u,
                        alpha = ((0.04f + (d - 0.55f) * 1.5f) * (0.35f + b * 1.6f)).coerceIn(0f, 1f),
                    )
                }
                for (i in 0 until n) {
                    val b = bright[i]
                    if (b < 0.05f && depth[i] < 0.85f) continue
                    val ga = (0.18f + b * 1.2f).coerceIn(0f, 1f)
                    val rad = kotlin.math.max(0.8f, px0 * 0.004f * (1f + b * 2.6f) * depth[i]) * u
                    val at = Offset(px[i], py[i])
                    if (b > 0.3f) {
                        drawCircle(
                            brush = KitParity.glow(hot, 0.7f * b, at, rad * 4f),
                            radius = rad * 4f,
                            center = at,
                            alpha = ga,
                        )
                    }
                    drawCircle(color = if (b > 0.3f) hot else cool, radius = rad, center = at, alpha = ga)
                }

                // The core glow; it swells with the microphone while listening.
                val cr = (px0 * 0.05f + if (f.motion == FaceState.LISTENING) f.amp * px0 * 0.04f else 0f) * u
                drawCircle(
                    brush = KitParity.glow(hot, 0.5f, Offset(cx, cy), cr * 3f),
                    radius = cr * 3f,
                    center = Offset(cx, cy),
                )
            }
        }
    }
}

/**
 * The Kirkwood gaps: an asteroid belt cleared by resonance with a shepherd
 * body ("Jupiter"), not evenly filled.
 *
 * A literal port of the reactor kit's Kirkwood. The old port here flattened
 * the belt into a squashed ellipse with a made-up depth term and drew its
 * rocks at a third of the kit's size. The kit's belt is a real 3D ring seen
 * from 54 degrees above the plane through its perspective camera, with a
 * glowing sun, a glowing Jupiter, the three resonance radii drawn as faint
 * rings, and more rocks while thinking (when the gaps also half fill in).
 *
 * The layout is seeded and generated once, for the most rocks any state can
 * ask for; a state that wants fewer uses the first N. The kit regenerates a
 * fresh random belt whenever its count changes - on every step into or out
 * of thinking - which here would have been a reshuffle on a state change and
 * a face that is no longer a pure function of the frame.
 */
object Kirkwood : Face {
    override val id = "kirkwood"
    override val name = "Kirkwood"

    // faces[].render.fit for kirkwood is 0.9 in the spec. This face never set
    // it, so it drew at 1.0 - larger than the kit, with Jupiter's orbit
    // (1.32 of the belt) nearer the edge than the spec frames it.
    override val fit = 0.9f

    private const val JUPITER_A = 1.32f

    /** The most rocks [KitParity.detail] can return for the kit's largest `n` (700). */
    private const val MAX_ROCKS = 1680

    // a = aJupiter * ratio^(-2/3) - Kepler's third law, solved for the radius
    // that shares Jupiter's orbital period times a simple fraction: the 3:1,
    // 5:2 and 2:1 resonances.
    private fun gapAt(ratio: Float): Float = JUPITER_A * ratio.pow(-2f / 3f)

    private val gaps = floatArrayOf(gapAt(3f), gapAt(5f / 2f), gapAt(2f))

    // Jupiter's own angular rate, a^-1.5.
    private val jupiterOmega = JUPITER_A.pow(-1.5f)

    // Fixed per-rock layout, drawn in the kit's order: a, e, phase, inc, s.
    private val rockA = FloatArray(MAX_ROCKS)
    private val rockE = FloatArray(MAX_ROCKS)
    private val rockPhase = FloatArray(MAX_ROCKS)
    private val rockInc = FloatArray(MAX_ROCKS)
    private val rockSize = FloatArray(MAX_ROCKS)

    // Functions of the fixed layout alone, so decided once: Kepler's rate
    // a^-1.5 (a Math.pow per rock per frame otherwise), and how clear of a
    // resonance each orbit sits before the state's `clear` is applied.
    private val rockOmega = FloatArray(MAX_ROCKS)
    private val rockClear = FloatArray(MAX_ROCKS)

    // Reused for the three gap rings; lazy for the same reason as Rime's.
    private val path by lazy(LazyThreadSafetyMode.NONE) { androidx.compose.ui.graphics.Path() }
    private val cam = KitParity.Camera()

    init {
        val rnd = kotlin.random.Random(20260913)
        for (i in 0 until MAX_ROCKS) {
            rockA[i] = 0.45f + rnd.nextFloat() * 0.55f
            rockE[i] = rnd.nextFloat() * 0.10f
            rockPhase[i] = rnd.nextFloat() * PI2
            rockInc[i] = (rnd.nextFloat() - 0.5f) * 0.10f
            rockSize[i] = rnd.nextFloat()
            rockOmega[i] = rockA[i].pow(-1.5f)
            var clear = 1f
            for (gap in gaps) {
                clear = minOf(clear, (kotlin.math.abs(rockA[i] - gap) / 0.045f).coerceIn(0f, 1f))
            }
            rockClear[i] = clear
        }
    }

    // The kit's per-state `sp`.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.22f
        FaceState.THINKING -> 0.6f
        FaceState.SPEAKING -> 0.14f
        else -> 0.10f
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) {
        with(scope) {
            KitParity.inKitCanvas(this) {
                val px0 = KitParity.backingPx(this)
                val u = 4f * r / px0
                val thinking = f.motion == FaceState.THINKING
                // The kit's `n` and `clear`: thinking crowds the belt and lets
                // the gaps two-thirds fill in.
                val count = kotlin.math.min(MAX_ROCKS, KitParity.detail(px0, 260, if (thinking) 700 else 520))
                val clearK = if (thinking) 0.35f else 1f
                val mid = mix(hot, cool, 0.5f)

                // Yaw and pitch twice, as in the kit (here and in its proj).
                cam.aim(
                    ry = f.yaw + f.yaw,
                    rx = -0.95f + f.pitch + f.pitch,
                    dist = 4.2f, scale = 4f * r * 1.35f, cx = cx, cy = cy,
                )
                val phase = f.angle
                for (i in 0 until count) {
                    // How close is this orbit to a resonance? That decides if
                    // it survives.
                    val clear = 1f + (rockClear[i] - 1f) * clearK
                    if (clear < 0.06f) continue
                    // Kepler: inner orbits are faster.
                    val ang = rockPhase[i] + phase * rockOmega[i]
                    val rr = rockA[i] * (1f - rockE[i] * cos(ang * 2f))
                    cam.at(cos(ang) * rr, rockInc[i], sin(ang) * rr)
                    val s = rockSize[i]
                    drawCircle(
                        color = if (s > 0.9f) mid else cool,
                        radius = kotlin.math.max(0.5f, px0 * 0.0035f * cam.d * (0.4f + s)) * u,
                        center = Offset(cam.x, cam.y),
                        alpha = ((0.18f + s * 0.5f) * clear * cam.d).coerceIn(0f, 1f),
                        blendMode = KitParity.PLUS,
                    )
                }

                // The sun, and Jupiter doing the clearing.
                cam.at(0f, 0f, 0f)
                val sun = Offset(cam.x, cam.y)
                val sunR = px0 * 0.10f * u
                drawCircle(
                    brush = KitParity.radial(
                        sun, sunR,
                        0f to lift(hot, 0.35f).copy(alpha = 0.85f),
                        0.35f to hot.copy(alpha = 0.45f),
                        1f to Color.Transparent,
                    ),
                    radius = sunR,
                    center = sun,
                )
                val ja = phase * jupiterOmega
                cam.at(cos(ja) * JUPITER_A, 0f, sin(ja) * JUPITER_A)
                val jup = Offset(cam.x, cam.y)
                val jupR = px0 * 0.045f * cam.d * u
                drawCircle(
                    brush = KitParity.radial(jup, jupR, 0f to hot, 0.6f to cool, 1f to Color.Transparent),
                    radius = jupR,
                    center = jup,
                )

                // Label the gaps where they actually are: a one-kit-pixel ring
                // at each resonance radius.
                for (gap in gaps) {
                    path.reset()
                    for (i in 0..48) {
                        val a2 = i / 48f * PI2
                        cam.at(cos(a2) * gap, 0f, sin(a2) * gap)
                        if (i == 0) path.moveTo(cam.x, cam.y) else path.lineTo(cam.x, cam.y)
                    }
                    drawPath(path = path, color = mid, alpha = 0.14f, style = Stroke(width = 1f * u))
                }
            }
        }
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
