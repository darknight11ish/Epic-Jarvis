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
import kotlin.math.roundToInt
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
 * axial grid - 37 or 61 cells depending on how big the face is drawn -
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
 * Cost: at 61 cells, eight filled or stroked paths each - about 490 path
 * draws a frame, all from one reused Path. The heaviest of these five.
 */
object Comb : Face {
    override val id = "comb"
    override val name = "Comb"

    private const val MAX_CELLS = 61   // a 4-ring hex lattice: 3*4*5 + 1
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
        val rings = FirstFiveKit.detail(sz / fit, 3, 4)
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
 * the artifact, 600-1500 stars (more the bigger the face is drawn) each run
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
 * Cost: one `drawCircle` per star, up to 1500 a frame plus about 3% more for
 * the glows, all additive - the most draw calls of these five, about three
 * and a half times Kirkwood's 420 rocks, though each one is a small dot.
 */
object Spiral : Face {
    override val id = "spiral"
    override val name = "Spiral"

    private const val MAX_STARS = 1500

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
        val n = FirstFiveKit.detail(sz / fit, 600, MAX_STARS)
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
 * anatomy: 120-220 stromal fibres (more the bigger the face is drawn), each
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
 * Cost: up to 220 anti-aliased path strokes a frame, the most fill work of
 * these five after Comb. Worth watching on an old phone.
 */
object Iris : Face {
    override val id = "iris"
    override val name = "Iris"
    override val fit = 0.86f

    private const val MAX_FIBRES = 220

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

            val nf = FirstFiveKit.detail(sz / fit, 120, MAX_FIBRES)
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
     * actually drawn, from `lo` at 200 px to `hi` at 820 px. Its quality
     * multiplier is 1 on every surface this port has, so it is left out.
     */
    fun detail(px: Float, lo: Int, hi: Int): Int {
        val k = ((px - 200f) / 620f).coerceIn(0f, 1f)
        return max(lo, (lo + (hi - lo) * k).roundToInt())
    }

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
