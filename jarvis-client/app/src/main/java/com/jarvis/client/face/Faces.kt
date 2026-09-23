package com.jarvis.client.face

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import com.jarvis.client.FaceState
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

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
 * or nudged by its own last frame; call `draw` with the same [FaceFrame]
 * twice and it draws the same picture twice. (The whole frame, not just
 * `(t, amp)`: Spectrum, Coreplate, Workbench, Swarm and Shoal ease a
 * per-state target across a state change from `prevMotion` and
 * `hitchPhase`, both fields of the frame - see `CoreKit.settle`.) That
 * makes these six exactly as pinnable as Rime and Kirkwood, even though the
 * spec's flag — describing the *reference's* technique, not this port's —
 * says otherwise. See
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

/**
 * Concentric rings round a glowing core: the classic, tightened.
 *
 * A line-for-line port of the Reactor Kit artifact's `arc` draw(), which is
 * also the desktop's (faces.html) - the two are byte-identical for this face.
 * The version it replaces was five plain arcs and a dot, drawn at a quarter
 * of the box; this is the artifact's four layers - a 72-tick bezel, three
 * segmented rings turning at their own rates, a ring of 60 spokes the voice
 * drives, and a bloomed core with the dark triangle cut into it.
 *
 * Every length and line width is a fraction of [FirstFiveKit.sz], the same
 * fraction the artifact takes of its canvas width, so a 715px phone box gets
 * the same several-pixel strokes the artifact draws rather than hairlines.
 *
 * Two inputs the artifact has and this port does not: the pointer lean
 * (`TOUCH`, spokes pulling toward a held finger - the phone reports taps, not
 * a held position) and the beat detector (`HUD.beat`, which nothing on the
 * phone computes). Both are additive terms that are zero when idle in the
 * artifact too, so leaving them out removes a reaction, not any drawing.
 */
object Arc : Face {
    override val id = "arc"
    override val name = "Arc"

    // The artifact's per-state `sp`. The shell integrates this into
    // `f.angle`, which is exactly the artifact's PHASE.
    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.7f
        FaceState.THINKING -> 1.35f
        FaceState.SPEAKING -> 0.5f
        else -> 0.22f
    }

    /** The artifact's per-state `gl`: how strongly the core blooms. */
    private fun bloomFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.95f
        FaceState.THINKING -> 0.8f
        FaceState.SPEAKING -> 1f
        else -> 0.42f
    }

    // The core's triangle, rebuilt in place each frame rather than allocated.
    private val tri = Path()

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = FirstFiveKit.frame(scope, r) { paint(cx, cy, r, hot, cool, f) }

    private fun DrawScope.paint(cx: Float, cy: Float, r: Float, hot: Color, cool: Color, f: FaceFrame) {
        val sz = FirstFiveKit.sz(r)
        // `min(w,h)/2 - w*.06` on the artifact's square canvas.
        val rim = sz * 0.44f
        val t = f.t
        // Speaking and thinking pulse on the clock rather than the level, as
        // the artifact's do; listening is the one state driven by the mic.
        val drive = when (f.motion) {
            FaceState.LISTENING -> f.amp
            FaceState.SPEAKING -> 0.42f + 0.32f * abs(sin(t * 6f))
            FaceState.THINKING -> 0.3f + 0.14f * sin(t * 3.4f)
            else -> 0.16f + 0.05f * sin(t * 1.3f)
        }
        val spin = f.angle + f.yaw

        // The bezel: 72 ticks, every sixth one long and brighter.
        val tickRot = spin * 0.35f
        val tickW = sz * 0.006f
        for (i in 0 until 72) {
            val a = i / 72f * PI2 + tickRot
            val long = i % 6 == 0
            val inner = rim - if (long) rim * 0.09f else rim * 0.045f
            val ca = cos(a)
            val sa = sin(a)
            drawLine(
                color = cool,
                start = Offset(cx + ca * rim, cy + sa * rim),
                end = Offset(cx + ca * inner, cy + sa * inner),
                strokeWidth = tickW,
                alpha = if (long) 0.7f else 0.26f,
            )
        }

        // Three segmented rings, each turning at its own rate and direction.
        // The yaw terms are the artifact's own: a drag turns each ring by a
        // different amount, which is what makes them read as separate layers.
        ring(cx, cy, rim * 0.82f, 6, 0.34f, sz * 0.016f, cool, 0.85f, -spin * 0.8f + f.yaw * 0.6f)
        ring(cx, cy, rim * 0.68f, 12, 0.18f, sz * 0.009f, hot, 0.4f, spin * 1.4f + f.yaw * 1.3f)
        ring(cx, cy, rim * 0.55f, 3, 0.55f, sz * 0.026f, cool, 0.3f, -spin * 0.5f + f.yaw * 0.4f)

        // Sixty spokes pointing inward from 0.44 of the rim; their length is
        // the drive, with a fast per-spoke shimmer on top.
        val spokeW = sz * 0.007f
        val spokeAlpha = (0.12f + drive * 0.5f).coerceIn(0f, 1f)
        val base = rim * 0.44f
        for (i in 0 until 60) {
            val a = i / 60f * PI2
            val n = sin(i * 2.1f + t * 7f) * 0.5f + 0.5f
            val len = rim * 0.04f + drive * rim * 0.3f * (0.35f + n * 0.65f)
            val ca = cos(a)
            val sa = sin(a)
            drawLine(
                color = hot,
                start = Offset(cx + ca * base, cy + sa * base),
                end = Offset(cx + ca * (base - len), cy + sa * (base - len)),
                strokeWidth = spokeW,
                alpha = spokeAlpha,
            )
        }

        // The core: a bloom out to 2.3x, then a solid centre over it. The
        // gradient goes through FirstFiveKit.radial, which is what keeps it as
        // tight as the artifact's - see there.
        val cr = rim * 0.22f + drive * rim * 0.09f
        val centre = Offset(cx, cy)
        drawCircle(
            brush = FirstFiveKit.radial(
                0f to hot,
                0.3f to hot.copy(alpha = 0.75f),
                0.65f to cool.copy(alpha = 0.2f),
                1f to Color.Transparent,
                center = centre,
                radius = cr * 2.3f,
            ),
            radius = cr * 2.3f,
            center = centre,
            alpha = bloomFor(f.motion).coerceAtMost(1f),
        )
        drawCircle(hot, cr * 0.42f, centre)

        // The dark triangle cut into the core, counter-rotating. The artifact
        // strokes it in its background colour, #04070c, which is the spec's
        // background and so Spec.BACKGROUND here.
        val triRot = -spin * 0.25f
        tri.reset()
        for (i in 0 until 3) {
            val a = i / 3f * PI2 - PI.toFloat() / 2f + triRot
            val x = cx + cos(a) * cr * 0.3f
            val y = cy + sin(a) * cr * 0.3f
            if (i == 0) tri.moveTo(x, y) else tri.lineTo(x, y)
        }
        tri.close()
        drawPath(tri, Spec.BACKGROUND, alpha = 0.85f, style = Stroke(width = sz * 0.016f))
    }

    /** The artifact's `ring()`: [segs] arcs round the circle, each short by [gap] radians. */
    private fun DrawScope.ring(
        cx: Float, cy: Float, rad: Float, segs: Int, gap: Float,
        width: Float, color: Color, alpha: Float, rot: Float,
    ) {
        val stroke = Stroke(width = width)
        val step = PI2 / segs
        val sweep = Math.toDegrees((step - gap).toDouble()).toFloat()
        val topLeft = Offset(cx - rad, cy - rad)
        val box = Size(rad * 2f, rad * 2f)
        for (i in 0 until segs) {
            drawArc(
                color = color,
                startAngle = Math.toDegrees((rot + i * step).toDouble()).toFloat(),
                sweepAngle = sweep,
                useCenter = false,
                topLeft = topLeft,
                size = box,
                alpha = alpha,
                style = stroke,
            )
        }
    }
}

/**
 * Five bodies on inclined, eccentric orbits, depth sorted around a glowing core.
 *
 * A port of the artifact's `orbit` draw() (identical to the desktop's). What
 * it replaced was five rings of 48 evenly spaced dots - a pattern, not
 * orbits. Here each body is a real Kepler ellipse, r = a(1-e^2)/(1+e cos),
 * with its path traced faintly behind it, seen through a true perspective
 * camera; the states change the eccentricity, not just the speed, so
 * thinking swings the bodies out on long ellipses and listening pulls them
 * into tight circles. The core is painted at the right point in the depth
 * sort, so the far bodies pass behind it and the near ones in front.
 */
object Orbit : Face {
    override val id = "orbit"
    override val name = "Orbit"

    private const val BODIES = 5
    private const val PATH_STEPS = 64

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.1f
        FaceState.THINKING -> 0.75f
        FaceState.SPEAKING -> 0.5f
        else -> 0.35f
    }

    /** The artifact's per-state `ecc`. */
    private fun eccFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.04f
        FaceState.THINKING -> 0.55f
        FaceState.SPEAKING -> 0.25f
        else -> 0.15f
    }

    // Per-frame scratch, on the singleton rather than reallocated - the same
    // pattern Fullerene's buffers set out. Every slot is written before it is
    // read, so nothing carries between frames.
    private val bx = FloatArray(BODIES)
    private val by = FloatArray(BODIES)
    private val bz = FloatArray(BODIES)
    private val bd = FloatArray(BODIES)
    private val order = IntArray(BODIES)
    private val trace = Path()

    // The artifact traces each orbit at a fixed 1.1 px. That is its own raw
    // number, not a fraction of the canvas, and it is 1.1 of the artifact's
    // BACKING pixels - which on a phone are finer than device pixels - so a
    // fixed 1.1 device px here is already a touch heavier than the reference.
    private val traceStroke = Stroke(width = 1.1f)

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = FirstFiveKit.frame(scope, r) { paint(cx, cy, r, hot, cool, f) }

    private fun DrawScope.paint(cx: Float, cy: Float, r: Float, hot: Color, cool: Color, f: FaceFrame) {
        val sz = FirstFiveKit.sz(r)
        val t = f.t
        val phase = f.angle
        // The spin (ry) rides the state's speed; the slow nod (rx) stays on
        // the raw clock, so it does not speed up when Jarvis starts thinking.
        FirstFiveKit.view(phase * 0.5f + f.yaw, -0.42f + sin(t * 0.18f) * 0.1f + f.pitch)
        val dist = 4.2f
        val scale = sz * 1.15f
        val baseEcc = eccFor(f.motion)
        val traceColor = cool.copy(alpha = 0.30f)

        for (i in 0 until BODIES) {
            val orbR = 0.42f + i * 0.22f
            val incl = (i - 2) * 0.42f
            val si = sin(incl)
            val ci = cos(incl)
            val ecc = baseEcc * (1f + i * 0.12f)
            val ang = phase * (1.6f - i * 0.2f) + i * 1.31f
            val rr = orbR * (1f - ecc * ecc) / (1f + ecc * cos(ang))
            // The orbit plane is tilted about X by its inclination.
            val ox = cos(ang) * rr
            val oz = sin(ang) * rr
            FirstFiveKit.proj(ox, oz * si, oz * ci, dist, scale, cx, cy)
            bx[i] = FirstFiveKit.px
            by[i] = FirstFiveKit.py
            bz[i] = FirstFiveKit.pz
            bd[i] = FirstFiveKit.pd
            order[i] = i

            // The path itself, faint, drawn before any body.
            trace.reset()
            for (k in 0..PATH_STEPS) {
                val a2 = k / PATH_STEPS.toFloat() * PI2
                val r2 = orbR * (1f - ecc * ecc) / (1f + ecc * cos(a2))
                val z0 = sin(a2) * r2
                FirstFiveKit.proj(cos(a2) * r2, z0 * si, z0 * ci, dist, scale, cx, cy)
                if (k == 0) trace.moveTo(FirstFiveKit.px, FirstFiveKit.py)
                else trace.lineTo(FirstFiveKit.px, FirstFiveKit.py)
            }
            trace.close()
            drawPath(trace, traceColor, style = traceStroke)
        }

        // Far to near. Five entries: an insertion sort, no comparator object.
        for (i in 1 until BODIES) {
            val o = order[i]
            var j = i - 1
            while (j >= 0 && bz[order[j]] < bz[o]) {
                order[j + 1] = order[j]
                j--
            }
            order[j + 1] = o
        }

        // The core sits at the origin, so it is painted just before the first
        // body that is nearer than it (z < 0).
        var coreDrawn = false
        for (o in order) {
            if (!coreDrawn && bz[o] < 0f) {
                paintCore(cx, cy, sz, t, hot, f)
                coreDrawn = true
            }
            val d = bd[o]
            val rr = max(2f, sz * 0.030f * d * d)
            val a = min(1f, 0.30f + d * 0.62f)
            val at = Offset(bx[o], by[o])
            drawCircle(
                brush = FirstFiveKit.radial(
                    0f to hot,
                    0.4f to cool.copy(alpha = 0.5f),
                    1f to Color.Transparent,
                    center = at,
                    radius = rr * 2.6f,
                ),
                radius = rr * 2.6f,
                center = at,
                alpha = a,
            )
            drawCircle(hot, rr, at, alpha = a)
        }
        if (!coreDrawn) paintCore(cx, cy, sz, t, hot, f)
    }

    private fun DrawScope.paintCore(cx: Float, cy: Float, sz: Float, t: Float, hot: Color, f: FaceFrame) {
        val cr = sz * 0.075f + if (f.motion == FaceState.LISTENING) f.amp * sz * 0.06f else sz * 0.016f * sin(t * 4f)
        val centre = Offset(cx, cy)
        // The artifact's core is white-hot at the centre. White is a literal,
        // so the shell's dim never reaches it; it is dimmed here by the same
        // factor instead, so a dimmed state (standby, banked) does not keep a
        // full-white core in an otherwise dimmed face. At dim 1 it is white.
        val white = mix(Spec.BACKGROUND, Color.White, f.dim)
        // Drawn at full strength, the one place this face is brighter
        // than the artifact, on purpose. The artifact's paintCore never sets
        // its own alpha, so it inherits whatever the body drawn just before
        // it left behind - anywhere from 0.3 to 1 - and that value jumps
        // in a single frame whenever a body crosses in front of the core and
        // the depth order changes. On a glow half the face across, that
        // is a sudden brightness step a few times a revolution; the spec's
        // flash limits are the reason not to copy it.
        drawCircle(
            brush = FirstFiveKit.radial(
                0f to white,
                0.25f to hot,
                0.6f to hot.copy(alpha = 0.22f),
                1f to Color.Transparent,
                center = centre,
                radius = cr * 3.4f,
            ),
            radius = cr * 3.4f,
            center = centre,
        )
    }
}

/**
 * Honeycomb with real extruded walls, filling from the middle outward.
 *
 * A port of the artifact's `comb` draw() (identical to the desktop's). What
 * it replaced was 37 flat hexagon outlines. This is a hex lattice on an
 * axial grid - 37 to 217 cells depending on how big the face is drawn (at
 * the kit's single-face quality, see FirstFiveKit.detail) -
 * seen from above at an angle through a real perspective camera, with each
 * cell's six inner walls filled and shaded by which way they face, honey
 * sitting in the bottom at a level that spreads outward from the centre, and
 * only the wall tops catching the light. Thinking drains it; listening fills
 * it with the voice.
 *
 * The artifact's comb has no spin of its own: it moves only by the fill wave
 * (on the raw clock) and the drag. That is kept - `speedFor` feeds nothing
 * here, and still carries the artifact's `sp` so the table is honest.
 *
 * Cost: at 217 cells, eight filled or stroked paths each - about 1,700 path
 * draws a frame, all from one reused Path. The heaviest of these five, and
 * not yet timed on a phone; [KitParity.QUALITY] is the knob if it struggles.
 */
object Comb : Face {
    override val id = "comb"
    override val name = "Comb"

    // The kit's rings are `small_n(w, 3, 4)`, which at its solo quality
    // (see FirstFiveKit.detail) reaches round(4 * 1.9) = 8 rings: 3*8*9 + 1.
    private const val MAX_RINGS = 8
    private const val MAX_CELLS = 3 * MAX_RINGS * (MAX_RINGS + 1) + 1
    private const val CELL_R = 0.135f
    private const val DEPTH = 0.20f

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.35f
        FaceState.THINKING -> 0.9f
        FaceState.SPEAKING -> 0.2f
        else -> 0.10f
    }

    private fun fillFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.80f
        FaceState.THINKING -> 0.22f
        FaceState.SPEAKING -> 0.68f
        else -> 0.55f
    }

    private fun waveFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.6f
        FaceState.THINKING -> 3.2f
        FaceState.SPEAKING -> 1.0f
        else -> 0.6f
    }

    private val cellX = FloatArray(MAX_CELLS)
    private val cellZ = FloatArray(MAX_CELLS)
    private val cellD = FloatArray(MAX_CELLS)
    private val cellKey = FloatArray(MAX_CELLS)
    private val order = IntArray(MAX_CELLS)
    private val topX = FloatArray(6)
    private val topY = FloatArray(6)
    private val botX = FloatArray(6)
    private val botY = FloatArray(6)
    private val hexCos = FloatArray(6) { cos(it / 6f * PI2) }
    private val hexSin = FloatArray(6) { sin(it / 6f * PI2) }
    private val path = Path()

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = FirstFiveKit.frame(scope, r) { paint(cx, cy, r, hot, cool, f) }

    private fun DrawScope.paint(cx: Float, cy: Float, r: Float, hot: Color, cool: Color, f: FaceFrame) {
        val sz = FirstFiveKit.sz(r)
        val t = f.t
        // The artifact passes yaw*.7 and pitch*.7 into rot3, which then adds
        // the full view yaw and pitch again: a drag turns the comb 1.7x.
        FirstFiveKit.view(f.yaw * 0.7f + f.yaw, -0.78f + f.pitch * 0.7f + f.pitch)
        val dist = 4.6f
        val scale = sz * 1.15f
        val rings = min(MAX_RINGS, FirstFiveKit.detail(sz / fit, 3, 4))
        val fill = fillFor(f.motion)
        val wave = waveFor(f.motion)
        val listening = f.motion == FaceState.LISTENING

        var n = 0
        for (q in -rings..rings) {
            for (s in max(-rings, -q - rings)..min(rings, -q + rings)) {
                val x = CELL_R * 1.5f * q
                val z = CELL_R * sqrt(3f) * (s + q / 2f)
                cellX[n] = x
                cellZ[n] = z
                cellD[n] = hypot(x, z)
                FirstFiveKit.rot(x, 0f, z)
                cellKey[n] = FirstFiveKit.rz
                order[n] = n
                n++
            }
        }
        // Far to near, so near walls cover far ones.
        for (i in 1 until n) {
            val o = order[i]
            var j = i - 1
            while (j >= 0 && cellKey[order[j]] < cellKey[o]) {
                order[j + 1] = order[j]
                j--
            }
            order[j + 1] = o
        }

        val wallTop = Stroke(width = max(0.8f, sz * 0.006f))
        val coolLit = FirstFiveKit.shade(cool, 1.5f)
        val hotShade = FirstFiveKit.shade(hot, 0.55f)
        for (idx in 0 until n) {
            val c = order[idx]
            val x = cellX[c]
            val z = cellZ[c]
            val d = cellD[c]
            // Fill spreads outward from the centre; the wave is provisioning.
            val lvl = ((fill - d * 0.55f) * 2f + sin(t * wave - d * 4f) * 0.18f +
                (if (listening) f.amp * 0.4f else 0f)).coerceIn(0f, 1f)

            hex(x, z, -DEPTH, CELL_R * 0.92f, dist, scale, cx, cy, topX, topY)
            hex(x, z, 0f, CELL_R * 0.92f, dist, scale, cx, cy, botX, botY)

            // The six inner walls, so the cell has visible depth. Shaded by
            // which way each one faces the viewer.
            for (i in 0 until 6) {
                val j = (i + 1) % 6
                path.reset()
                path.moveTo(topX[i], topY[i])
                path.lineTo(topX[j], topY[j])
                path.lineTo(botX[j], botY[j])
                path.lineTo(botX[i], botY[i])
                path.close()
                val facing = topX[j] - topX[i]
                drawPath(path, FirstFiveKit.shade(cool, 0.22f + max(0f, facing / (sz * 0.06f)) * 0.30f))
            }

            // The honey sitting in the bottom of the cell.
            if (lvl > 0.02f) {
                hex(x, z, -DEPTH * lvl, CELL_R * 0.86f, dist, scale, cx, cy, botX, botY)
                path.reset()
                for (i in 0 until 6) {
                    if (i == 0) path.moveTo(botX[i], botY[i]) else path.lineTo(botX[i], botY[i])
                }
                path.close()
                drawPath(path, mix(hotShade, hot, lvl), alpha = 0.55f + lvl * 0.45f)
            }

            // Wall tops: the only part catching direct light.
            path.reset()
            for (i in 0 until 6) {
                if (i == 0) path.moveTo(topX[i], topY[i]) else path.lineTo(topX[i], topY[i])
            }
            path.close()
            drawPath(path, mix(coolLit, hot, 0.25f + lvl * 0.4f), style = wallTop)
        }
    }

    /** The artifact's `hexPts`: a hexagon of radius [rad] at height [y], projected. */
    private fun hex(
        x: Float, z: Float, y: Float, rad: Float,
        dist: Float, scale: Float, cx: Float, cy: Float,
        outX: FloatArray, outY: FloatArray,
    ) {
        for (i in 0 until 6) {
            FirstFiveKit.rot(x + hexCos[i] * rad, y, z + hexSin[i] * rad)
            val k = scale / (dist + FirstFiveKit.rz)
            outX[i] = cx + FirstFiveKit.rx * k
            outY[i] = cy + FirstFiveKit.ry * k
        }
    }
}

/**
 * A barred spiral galaxy whose arms are a traffic jam, not a structure.
 *
 * A port of the artifact's `spiral` draw() (identical to the desktop's). What
 * it replaced was three rigid logarithmic arms of 90 dots each. Here, as in
 * the artifact, 600-2850 stars (more the bigger the face is drawn) each run
 * their own closed oval at their own Keplerian rate, and the ovals are turned
 * a little more the further out they are; nothing is drawn as an arm - the
 * arms are where the ovals crowd, and they persist while every star moves
 * through them. Crowded stars are brighter, the youngest carry a small glow,
 * and the whole field adds light ("lighter" compositing, [BlendMode.Plus]).
 *
 * The artifact seeds its stars from Math.random on first draw; this seeds a
 * fixed generator instead, so the galaxy is the same one every time the face
 * is picked. Only the star layout is fixed - every position is still a pure
 * function of the angle, as in the artifact.
 *
 * Cost: one `drawCircle` per star, up to 2850 a frame at the kit's
 * single-face quality plus about 3% more for the glows, all additive - the
 * most draw calls of these five, though each one is a small dot. Not yet
 * timed on a phone; [KitParity.QUALITY] is the knob if it struggles.
 */
object Spiral : Face {
    override val id = "spiral"
    override val name = "Spiral"

    // The kit's `small_n(w, 600, 1500)`; at its solo quality that reaches
    // 1500 * 1.9 = 2850 (see FirstFiveKit.detail).
    private const val KIT_STARS = 1500
    private const val MAX_STARS = 2850

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.25f
        FaceState.THINKING -> 0.6f
        FaceState.SPEAKING -> 0.16f
        else -> 0.10f
    }

    private fun armsFor(motion: FaceState) = when (motion) {
        FaceState.THINKING -> 4
        FaceState.SPEAKING -> 3
        else -> 2
    }

    private fun windFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.50f
        FaceState.THINKING -> 0.75f
        FaceState.SPEAKING -> 0.46f
        else -> 0.42f
    }

    // The fixed layout, and everything about each star that is a function of
    // the layout alone - its orbital rate, its eccentricity and the log term
    // of its precession - so the draw loop computes only what moves.
    private val starR = FloatArray(MAX_STARS)
    private val starA0 = FloatArray(MAX_STARS)
    private val starZ = FloatArray(MAX_STARS)
    private val starM = FloatArray(MAX_STARS)
    private val starC = FloatArray(MAX_STARS)
    private val starOmega = FloatArray(MAX_STARS)
    private val starEcc = FloatArray(MAX_STARS)
    private val starLog = FloatArray(MAX_STARS)

    init {
        val rnd = kotlin.random.Random(20260923)
        for (i in 0 until MAX_STARS) {
            val a = rnd.nextFloat().pow(0.55f)
            starR[i] = a
            starA0[i] = rnd.nextFloat() * PI2
            starZ[i] = (rnd.nextFloat() - 0.5f) * 0.10f / (0.2f + a)
            starM[i] = rnd.nextFloat()
            starC[i] = rnd.nextFloat()
            starOmega[i] = 1f / (0.18f + a)
            // Ovals rounder in the bulge.
            starEcc[i] = 0.26f * min(1f, a / 0.30f)
            starLog[i] = ln(0.10f + a)
        }
    }

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = FirstFiveKit.frame(scope, r) { paint(cx, cy, r, hot, cool, f) }

    private fun DrawScope.paint(cx: Float, cy: Float, r: Float, hot: Color, cool: Color, f: FaceFrame) {
        val sz = FirstFiveKit.sz(r)
        val n = min(MAX_STARS, FirstFiveKit.detail(sz / fit, 600, KIT_STARS))
        // As in the artifact, the view is passed in AND added again by the
        // projection, so a drag turns the disc twice as far as the drag.
        FirstFiveKit.view(f.yaw + f.yaw, -1.05f + f.pitch + f.pitch)
        val dist = 4.0f
        val scale = sz * 1.5f
        val phase = f.angle
        val half = armsFor(f.motion) / 2f
        val wind = windFor(f.motion)
        // The artifact's PC slots: [hot, cool, their midpoint].
        val mid = mix(hot, cool, 0.5f)
        val drift = phase * 0.28f

        for (i in 0 until n) {
            val a = starR[i]
            // Where the star is on its own oval.
            val th = starA0[i] + phase * starOmega[i] * 0.5f
            val c = cos(th * half)
            val rr = a * (1f - starEcc[i] * c)
            // Apsidal precession with radius: the tilt that winds the nest of
            // ovals into a spiral instead of a rosette.
            val ang = th + starLog[i] / wind + drift
            FirstFiveKit.proj(cos(ang) * rr, starZ[i], sin(ang) * rr, dist, scale, cx, cy)
            val d = FirstFiveKit.pd
            // A star lingers longest at the near end of its oval, which is
            // also where the ovals crowd - so the arm holds more stars, longer.
            val crowd = abs(c).pow(2.4f)
            val young = crowd > 0.62f && starC[i] > 0.5f
            val m = starM[i]
            val col = if (young || a < 0.22f) mid else cool
            val br = (0.045f + crowd * 0.62f) * (if (young) 1.9f else 1f) * (0.35f + m * 0.85f)
            val rad = max(0.45f, sz * 0.0042f * d * (if (young) 1.7f else 1f) * (0.35f + m))
            val at = Offset(FirstFiveKit.px, FirstFiveKit.py)
            drawCircle(
                color = col,
                radius = rad,
                center = at,
                alpha = min(0.92f, br * d),
                blendMode = BlendMode.Plus,
            )
            // The brightest arm stars carry their own little HII glow.
            if (young && m > 0.72f) {
                drawCircle(
                    color = cool,
                    radius = rad * 3.4f,
                    center = at,
                    alpha = (0.12f * crowd).coerceIn(0f, 1f),
                    blendMode = BlendMode.Plus,
                )
            }
        }

        // The bulge, added over the stars.
        FirstFiveKit.proj(0f, 0f, 0f, dist, scale, cx, cy)
        val c0 = Offset(FirstFiveKit.px, FirstFiveKit.py)
        drawCircle(
            brush = FirstFiveKit.radial(
                0f to hot.copy(alpha = 0.45f),
                0.4f to mid.copy(alpha = 0.14f),
                1f to Color.Transparent,
                center = c0,
                radius = sz * 0.16f,
            ),
            radius = sz * 0.16f,
            center = c0,
            blendMode = BlendMode.Plus,
        )
    }
}

/**
 * An eye, built the way an iris actually is.
 *
 * A port of the artifact's `iris` draw() (identical to the desktop's). What
 * it replaced was nine straight lines and a dot. This is the artifact's
 * anatomy: 120-418 stromal fibres (more the bigger the face is drawn), each
 * a gently wandering seven-point curve from the pupil out to the limbus with
 * its own depth and brightness; the raised collarette ring; a black pupil
 * that dilates on the state - wide when listening, a pinhole when thinking -
 * and a dark limbal ring round the edge.
 *
 * The pupil eases toward its target rather than jumping - "a real sphincter
 * has mass" - which is the one piece of state this face carries, and why
 * SpecDriftTest lists iris among the faces that cannot be pinned. The
 * artifact eases by 6% a frame; this eases by the matching time constant
 * (0.27 s, which is 6% a frame at 60 Hz) so a 120 Hz panel does not dilate
 * twice as fast.
 *
 * One deliberate difference: the artifact paints its sclera gradient over the
 * whole canvas, opaque to the corners, which replaces the background. Here
 * the same gradient fades to transparent at its outer edge instead, so the
 * eye sits in the theme's own well like every other face (see the single
 * ground in FaceView's drawFace) rather than in its own grey rectangle.
 *
 * Cost: up to 418 anti-aliased path strokes a frame at the kit's
 * single-face quality, the most fill work of these five after Comb. Worth
 * watching on an old phone; [KitParity.QUALITY] is the knob.
 */
object Iris : Face {
    override val id = "iris"
    override val name = "Iris"
    override val fit = 0.86f

    // The kit's `small_n(w, 120, 220)`; at its solo quality that reaches
    // round(220 * 1.9) = 418 (see FirstFiveKit.detail).
    private const val KIT_FIBRES = 220
    private const val MAX_FIBRES = 418

    override fun speedFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 1.4f
        FaceState.THINKING -> 2.2f
        FaceState.SPEAKING -> 0.9f
        else -> 0.5f
    }

    private fun pupilFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.46f
        FaceState.THINKING -> 0.15f
        FaceState.SPEAKING -> 0.34f
        else -> 0.30f
    }

    private fun jitterFor(motion: FaceState) = when (motion) {
        FaceState.LISTENING -> 0.09f
        FaceState.THINKING -> 0.05f
        FaceState.SPEAKING -> 0.04f
        else -> 0.02f
    }

    // The artifact's per-fibre hash, frac(sin(i * 12.9898) * 43758.5453), in
    // double precision like the reference, computed once.
    private val fibreRnd = FloatArray(MAX_FIBRES) {
        val s = kotlin.math.sin(it * 12.9898) * 43758.5453
        (s - kotlin.math.floor(s)).toFloat()
    }

    // sin(k/6 * PI) for the seven points along a fibre: the wander is zero at
    // both ends and largest in the middle.
    private val bow = FloatArray(7) { sin(it / 6f * PI.toFloat()) }

    private var pupil = 0.30f
    private var lastT = Float.NaN

    private val fibre = Path()
    private val disc = Path()

    // Each fibre has its own width, so each needs its own Stroke: 220 new
    // objects a frame if made in the draw. These are rebuilt only when the
    // face's size changes, so while it holds still (idle, thinking) the fibres
    // allocate nothing. Speaking and listening push the size every frame, and
    // then they are rebuilt every frame - no worse than making them inline.
    private val fibreStrokes = Array(MAX_FIBRES) { Stroke(width = 1f) }
    private var strokesFor = -1f

    override fun draw(
        scope: DrawScope, cx: Float, cy: Float, r: Float,
        hot: Color, cool: Color, f: FaceFrame,
    ) = FirstFiveKit.frame(scope, r) { paint(cx, cy, r, hot, cool, f) }

    private fun DrawScope.paint(cx: Float, cy: Float, r: Float, hot: Color, cool: Color, f: FaceFrame) {
        val sz = FirstFiveKit.sz(r)
        val rim = sz * 0.44f
        val centre = Offset(cx, cy)

        // The pupil eases toward the state's size. A step backwards in the
        // clock, or a long gap, means this singleton was just drawn by some
        // other host (a thumbnail, a new screen): snap rather than ease from
        // a stranger's pupil.
        val target = max(0.08f, pupilFor(f.motion) * if (f.motion == FaceState.LISTENING) 1f + f.amp * 0.5f else 1f)
        val dt = f.t - lastT
        pupil = if (dt.isNaN() || dt < 0f || dt > 0.5f) target
        else pupil + (target - pupil) * (1f - exp(-dt / 0.27f))
        lastT = f.t
        val pr = rim * pupil

        // Sclera: the artifact's off-centre gradient, lit from the upper left.
        // A two-point gradient (focal point offset from the centre) is not
        // something Compose's Brush offers, so this is Android's own
        // RadialGradient, API 31+, well inside this app's minSdk 33.
        drawRect(
            brush = scleraBrush(cx, cy, rim),
            topLeft = Offset.Zero,
            size = size,
        )

        disc.reset()
        disc.addOval(Rect(centre, rim))
        clipPath(disc) {
            drawCircle(FirstFiveKit.shade(cool, 0.45f), rim, centre)

            val nf = min(MAX_FIBRES, FirstFiveKit.detail(sz / fit, 120, KIT_FIBRES))
            if (sz != strokesFor) {
                for (i in 0 until MAX_FIBRES) {
                    fibreStrokes[i] = Stroke(width = max(0.6f, sz * 0.004f * (0.5f + fibreRnd[i])))
                }
                strokesFor = sz
            }
            val jit = jitterFor(f.motion)
            for (i in 0 until nf) {
                val a = i / nf.toFloat() * PI2
                val rnd = fibreRnd[i]
                val wob = sin(a * 7f + f.angle) * jit + (rnd - 0.5f) * 0.06f
                val inner = pr * (1f + rnd * 0.10f)
                val outer = rim * (0.86f + rnd * 0.14f)
                val lit = 0.35f + rnd * 0.65f
                fibre.reset()
                for (k in 0..6) {
                    val fk = k / 6f
                    val rr = inner + (outer - inner) * fk
                    val aa = a + wob * bow[k] * 1.6f
                    val x = cx + cos(aa) * rr
                    val y = cy + sin(aa) * rr
                    if (k == 0) fibre.moveTo(x, y) else fibre.lineTo(x, y)
                }
                drawPath(
                    fibre,
                    mix(FirstFiveKit.shade(cool, 0.5f + lit * 0.7f), hot, rnd * rnd * 0.5f),
                    alpha = 0.30f + lit * 0.55f,
                    style = fibreStrokes[i],
                )
            }

            // Collarette: the raised ridge where the two muscle layers meet.
            drawCircle(
                color = hot.copy(alpha = 0.5f),
                radius = pr * 1.32f,
                center = centre,
                style = Stroke(width = max(1f, sz * 0.008f)),
            )
            drawCircle(Color.Black, pr, centre)
        }

        // The wet limbal ring: the edge of the iris darkens into the sclera.
        drawCircle(
            brush = FirstFiveKit.radial(
                0f to Color.Transparent,
                0.72f to Color.Transparent,
                1f to Color.Black.copy(alpha = 0.85f),
                center = centre,
                radius = rim,
            ),
            radius = rim,
            center = centre,
        )
    }

    // The artifact's #1a1c1e at the lit point and its #050403 at the edge -
    // the edge here with no alpha, so the gradient hands over to the well
    // instead of covering it. Expanded the same way FirstFiveKit.radial
    // expands its stops, once, since these two colours never change.
    private val scleraStops = FirstFiveKit.expand(arrayOf(0f to Color(0xFF1A1C1E), 1f to Color(0x00050403)))
    private val scleraPos = FloatArray(scleraStops.size) { scleraStops[it].first }
    private val scleraColors = LongArray(scleraStops.size) { android.graphics.Color.pack(scleraStops[it].second.toArgb()) }

    private fun scleraBrush(cx: Float, cy: Float, rim: Float): Brush = ShaderBrush(
        android.graphics.RadialGradient(
            cx - rim * 0.2f, cy - rim * 0.25f, rim * 0.1f,
            cx, cy, rim * 1.5f,
            scleraColors,
            scleraPos,
            android.graphics.Shader.TileMode.CLAMP,
        ),
    )
}

/**
 * The shared bits of the artifact's drawing kit that Arc, Orbit, Comb,
 * Spiral and Iris use: its perspective projection, its `shade`, and its
 * `detail` scaling. Named for those five so it cannot collide with a helper
 * another face adds to this file.
 *
 * Mutable scratch on a singleton, like the faces' own buffers: every face is
 * drawn on the main thread, one at a time, and every register is written by
 * the call that the caller reads it straight after.
 */
private object FirstFiveKit {

    /**
     * The artifact's canvas size for a face drawn at radius [r].
     *
     * FaceView hands a face `r = (box / 4) * fit * speechPush`. The artifact
     * draws into the whole box - its `min(w, h)` - and then scales the result
     * by fit and the same push. So 4r is exactly the artifact's `min(w, h)`
     * with that scale already applied, and every fraction the artifact takes
     * of its canvas becomes the same fraction of this.
     */
    fun sz(r: Float) = 4f * r

    /**
     * The frame each of the five draws in.
     *
     * Nothing at all for a zero-size box (mid-layout), whose zero radius the
     * gradients would hand to Android's RadialGradient, which rejects it with
     * an exception.
     *
     * And clipped to the box. The artifact draws into a canvas that clips at
     * its own edge; a Compose Canvas does not. At the artifact's scale a
     * thinking Orbit's outer body and the Spiral's outer arm reach past the
     * box, so without this they would paint over whatever sits round it.
     */
    inline fun frame(scope: DrawScope, r: Float, body: DrawScope.() -> Unit) {
        if (r <= 0f) return
        scope.clipRect(block = body)
    }

    /**
     * The artifact's `detail(w, lo, hi)`: more geometry the bigger the face is
     * actually drawn, from `lo` at 200 px to `hi` at 820 px, times the kit's
     * quality multiplier. That multiplier is 1.9 in the kit's single-face
     * view (`SOLO.detail = Math.max(1.9, Q.detail)`), which is the view the
     * phone's face corresponds to - so a result can reach `hi * 1.9`, and the
     * arrays below are sized for that. It was left at 1 here, which drew
     * about half the kit's stars, fibres and cells; Fullerene to Kirkwood and
     * Accretion already used 1.9. One shared implementation, [KitParity.detail],
     * so there is one [KitParity.QUALITY] to turn down if a phone struggles.
     */
    fun detail(px: Float, lo: Int, hi: Int): Int = KitParity.detail(px, lo, hi)

    private var cyw = 1f
    private var syw = 0f
    private var cpt = 1f
    private var spt = 0f

    /** Sets the camera for [rot] and [proj]: yaw about Y, then pitch about X. */
    fun view(yaw: Float, pitch: Float) {
        cyw = cos(yaw)
        syw = sin(yaw)
        cpt = cos(pitch)
        spt = sin(pitch)
    }

    var rx = 0f
    var ry = 0f
    var rz = 0f

    /** The artifact's `rot3`, into [rx], [ry], [rz]. */
    fun rot(x: Float, y: Float, z: Float) {
        val x1 = x * cyw - z * syw
        val z1 = x * syw + z * cyw
        rx = x1
        ry = y * cpt - z1 * spt
        rz = y * spt + z1 * cpt
    }

    var px = 0f
    var py = 0f
    var pz = 0f
    var pd = 0f

    /**
     * The artifact's `proj`, into [px], [py], [pz] and [pd]. [pd] is the
     * unitless depth factor raised to the spec's depth_gain: read for size
     * and alpha only, never position, so far things are smaller and fainter.
     */
    fun proj(x: Float, y: Float, z: Float, dist: Float, scale: Float, cx: Float, cy: Float) {
        rot(x, y, z)
        val k = scale / (dist + rz)
        px = cx + rx * k
        py = cy + ry * k
        pz = rz
        pd = (dist / (dist + rz)).pow(Spec.DEPTH_GAIN)
    }

    /**
     * A radial gradient that fades the way the artifact's do.
     *
     * The browser's canvas blends gradient colours before applying alpha, so
     * the artifact's halos - every one of which ends on `rgba(0,0,0,0)` -
     * darken as they fade and fall off as the square of the distance.
     * Android's gradients (and Compose Desktop's) blend after, which falls off
     * in a straight line: the same stops drew every halo visibly wider and
     * brighter than the artifact's. Measured in the browser: white fading to
     * transparent black, over black, reads 143 / 63 / 16 at a quarter, half
     * and three quarters of the way; blended after alpha it would read 191 /
     * 128 / 64.
     *
     * So each span between the caller's stops is split into [SUB] smaller
     * ones, sampled from the browser's curve. Between two nearby samples the
     * two blend orders agree to within about one level of 255, which makes
     * this correct whichever order the device uses.
     */
    fun radial(vararg stops: Pair<Float, Color>, center: Offset, radius: Float): Brush =
        Brush.radialGradient(*expand(stops), center = center, radius = radius)

    /** [radial]'s stop expansion, on its own for the one gradient Brush cannot draw (Iris's sclera). */
    fun expand(stops: Array<out Pair<Float, Color>>): Array<Pair<Float, Color>> =
        Array((stops.size - 1) * SUB + 1) { n ->
            if (n == (stops.size - 1) * SUB) {
                stops.last()
            } else {
                val (o0, c0) = stops[n / SUB]
                val (o1, c1) = stops[n / SUB + 1]
                val u = (n % SUB) / SUB.toFloat()
                // [mix] interpolates alpha alongside the colour channels, not
                // premultiplied: exactly the browser's blend.
                (o0 + (o1 - o0) * u) to mix(c0, c1, u)
            }
        }

    private const val SUB = 6

    /**
     * The artifact's `shade(col, m)`: every channel multiplied by [m], clamped.
     * Unlike [lift], which blends toward white, this can push a colour past
     * itself - `shade(c, 1.5)` is how the comb's wall tops catch the light.
     */
    fun shade(c: Color, m: Float): Color = Color(
        red = (c.red * m).coerceIn(0f, 1f),
        green = (c.green * m).coerceIn(0f, 1f),
        blue = (c.blue * m).coerceIn(0f, 1f),
        alpha = c.alpha,
    )
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
 * 361 fish by canvas size (the reference's `detail(w, 90, 190)` at its
 * single-face quality of 1.9, see CoreKit.detail), the same
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

    // The reference's `detail(w, 90, 190)`; at its single-face quality that
    // reaches round(190 * 1.9) = 361 (see CoreKit.detail).
    private const val KIT_N = 190
    private const val N = 361
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
    // Built once and scaled per fish, rather than rebuilt per fish a frame;
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
        val n = min(N, CoreKit.detail(s / (fit * px1), 90, KIT_N))
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

        // The kit's canvas is `min(w, h)` = S wide, and in its solo view that
        // canvas IS the face's box. The shell hands a face r = box / 4 x fit,
        // and the kit applies `fit` as a scale around the centre, so S = 4r -
        // the same S every other face in this file now uses. (This was 2r,
        // which kept the old phone size: the coral sat at half the kit's
        // size, beside fifteen faces drawn at the kit's.) The grid spans the
        // whole of S, as the kit's does, so a cell is S / GW, and each is
        // drawn 1.25 cells wide so neighbours overlap into a continuous
        // branch rather than a lattice - the kit's own numbers.
        val sz = r * 4f
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

        // The kit's square canvas is S = 4r across (see Accretion), and
        // everything below is in its 0..1 units: u across, v down.
        val sz = r * 4f
        val left = cx - sz / 2f
        val top = cy - sz / 2f
        fun px(u: Float) = left + u * sz
        fun py(v: Float) = top + v * sz

        // The kit's canvas edge clips parcels that fly out sideways after
        // the bounce. `fit` shrinks the drawing, not the canvas, so the card
        // edge is at the box's own edge, 2r / fit from the centre, not at 2r.
        val card = 2f * r / fit
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
 * reference's square canvas (`(fragCoord - 0.5*res) / min(res.x, res.y) * 2`).
 * The reference's p = 1 is at half its canvas, and its canvas is the face's
 * box scaled by `fit` - which is 2r here, so uR = 2r. (It was r, which drew
 * the nucleus at half the kit's size, beside faces drawn at the kit's.)
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
        shader.setFloatUniform("uR", 2f * r)
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
        // the core. Its buffer is its whole canvas, which is 4r / fit here
        // (see Accretion on S = 4r; `fit` scales the drawing, not the canvas).
        shader.setIntUniform("uSteps", if (4f * r / fit > 900f) 96 else 72)

        // The reference's whole square canvas, |p.x| and |p.y| up to 1. Its
        // bounding sphere projects to about p = 1.24, so a circle of p = 1
        // could cut off something the kit draws in its corners. A ray that
        // misses the bounding sphere returns transparent, so the corners cost
        // one ray test a pixel and paint nothing.
        drawRect(
            brush = shaderBrush,
            topLeft = Offset(cx - 2f * r, cy - 2f * r),
            size = Size(4f * r, 4f * r),
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
