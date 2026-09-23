package com.jarvis.client.face.gl

import android.opengl.GLES30
import android.util.Log
import androidx.compose.ui.graphics.Color
import com.jarvis.client.FaceState
import com.jarvis.client.face.CALM_MOTION_RATE
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.Spec
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * A real spring-mass drum skin, Verlet-integrated - not a moving picture of
 * one. This is one of the faces in this app that genuinely cannot be a pure
 * function of `t`: each node's height depends on the two heights before it,
 * so it needs real state that persists between frames. Unlike a `Face`
 * singleton, a [MembraneRenderer] is created fresh per composition by
 * [MeshFaces] - exactly the right place to own that state, since it already
 * has to own live GL object ids tied to one specific surface.
 *
 * Ported close to the reference's own physics (`membrane` in the reactor kit,
 * `docs/reference/jarvis-reactor-kit.html`, the same code as the desktop's
 * `faces.html`: the five-point Laplacian stencil, the rim clamp, the
 * energy/"room" limiter that backs off the drive as the skin gets livelier)
 * and its GPU mesh upload (`gpu()`: central-difference normals from the
 * slope of the simulated heights, the rim pulled onto a circle rather than
 * left jagged, `MEMBRANE_VS`/`MEMBRANE_FS`), including its environment
 * reflection ([com.jarvis.client.face.EnvMap]) and multisampled edges
 * ([GL.MsaaConfigChooser]). What is dropped: `HUD.beat` (nothing here drives
 * it) and the kit's hardcoded per-state colours, in favour of the shell's
 * own hot/cool, as for Nucleus and Tokamak.
 *
 * Two things were brought up to the kit, and both changed the picture far
 * more than their size suggests:
 *
 *  - The grid. The kit's is `detail(GPUPX, 40, 150, 168)` cells across -
 *    168 on any phone-sized face in its solo view (see [GL.detail]). This
 *    used a fixed 40. A drum's ripples are
 *    a fixed number of CELLS long for a given stiffness and drive rate, so
 *    on a 40-cell skin every ripple was about a skin wide: the surface rose
 *    and fell as one bulge instead of carrying rings across it.
 *  - The clock. The kit steps its Verlet grid once per frame at 1x speed,
 *    whatever the state; each state's `rate` only sets how fast the centre
 *    is DRIVEN (`ph = t * p.rate`). This port read `rate` as a time scale
 *    and took `rate` physics ticks per 60th of a second - six times the
 *    kit's wave speed in thinking, 1.4x at idle - which stretched every
 *    ripple by the same factor and compounded the bulge above. Now the
 *    physics ticks at the kit's 60 a second in every state and the drive
 *    phase advances at `rate`, as in the kit.
 *
 * Three things are NOT literal ports, because the reference's own model for
 * them has no honest Android equivalent:
 *
 *  - Time stepping. The kit takes one tick per display frame, which on a
 *    120 Hz panel is twice the wave speed of a 60 Hz one. This uses a fixed-
 *    timestep accumulator at 60 ticks a second instead - the kit at 60 Hz -
 *    fed by real elapsed time times the shell's transform rate and calm
 *    motion, and drained in fixed-size ticks, the numerically stable way to
 *    run an explicit stencil like this. The backlog IS chased, up to
 *    [MAX_STEPS_PER_FRAME] - that bound is what stops a stall from bursting,
 *    and it is set high enough that no real render rate in the spec is
 *    throttled into slow motion by it.
 *  - The touch-driven strike point. The reference excites the skin at a
 *    location TOUCH.x/y sets directly. Touch already means something else
 *    for every 3D face in this app - camera orbit - and turning it into a
 *    second, face-specific meaning here was a new interaction this app has
 *    no precedent for and no device to try it on. Only the reference's
 *    OTHER excitation term survives: a steady pulse at the grid's own
 *    centre.
 *  - Camera auto-rotation. Unlike Nucleus and Tokamak, the reference's own
 *    membrane camera never auto-orbits - `ry=VIEW.yaw` alone, no `PHASE`
 *    term. Kept exactly that way rather than added for cross-file
 *    consistency: a drum reads by the wave crossing it, and an orbiting
 *    camera fights that reading in a way it doesn't for a fixed shape like
 *    a torus.
 *
 * Cost, at the kit's 168-cell grid: ~28,000 cells per tick (one tick a frame
 * at 60 Hz, a few tenths of a millisecond) and ~900 KB of vertex data
 * uploaded per frame - the most bandwidth of any face, and the same the kit
 * uploads in its solo view on the same phone.
 */
class MembraneRenderer : MeshRenderer {

    private data class St(val k: Float, val damp: Float, val drive: Float, val rate: Float)

    private fun stFor(motion: FaceState): St = when (motion) {
        FaceState.LISTENING -> St(k = 0.20f, damp = 0.995f, drive = 0.85f, rate = 3.2f)
        FaceState.THINKING -> St(k = 0.22f, damp = 0.988f, drive = 1.25f, rate = 6.0f)
        FaceState.SPEAKING -> St(k = 0.19f, damp = 0.996f, drive = 0.60f, rate = 2.2f)
        else -> St(k = 0.18f, damp = 0.994f, drive = 0.30f, rate = 1.4f)
    }

    private companion object {
        const val AMPL_H = 0.42f

        /**
         * Where the ring source sits when `tf.dir` is negative, as a fraction
         * of the skin's radius. See the excitation loop in [step].
         *
         * Not at the rim itself. The rim is clamped - [mask] stops at 0.96 of
         * the radius and everything past it is held at zero - so a source any
         * closer would be fighting that clamp, and the half of its energy that
         * goes outward would reflect straight back off it. At 0.7 the outward
         * half damps into the rim and the inward half has most of the skin to
         * travel across, which is the half anyone is meant to see.
         */
        const val RING_SOURCE_R_FRAC = 0.7f
        const val DIST = 4.2f
        const val FIXED_STEP = 1f / 60f

        // How much simulated time one rendered frame may carry.
        //
        // An old ceiling of 4 ticks threw the surplus away, which coupled the
        // drum's speed to the panel and to the shell's frame-rate gate: the
        // shell renders BANKED at 2 fps and STANDBY at 15, and a frame there
        // carries 30 and 4 ticks of real time. The bound is the worst
        // LEGITIMATE case - the slowest render rate in the spec, 2 fps, is
        // 0.5 s and 30 ticks - with slack, so nothing real is discarded and a
        // genuine stall still cannot burst without limit. Ticks are 60 a
        // second times the transform rate (at most 1) in every state now, so
        // no state asks for more than that. The worst frame is 48 ticks of a
        // 168-cell grid, about 1.4 million cell updates, and only a stall can
        // reach it.
        const val MAX_STEPS_PER_FRAME = 48

        /**
         * A gap longer than this did not happen because the device was slow -
         * it happened because rendering STOPPED (backgrounded, or the frame
         * loop suspended). `lastFrameNanos` is never reset in that case, so the
         * first frame back used to see the whole clamped delta and spend the
         * entire step budget catching up on time nobody watched pass. Longer
         * than any real frame interval the spec produces, BANKED's 0.5 s
         * included.
         */
        const val RESUME_GAP_S = 1.0f

        val VS = """
            #version 300 es
            precision highp float;
            in vec3 aPos;
            in vec3 aNrm;
            in vec2 aAux;
            uniform vec2 uRes;
            uniform float uYaw, uPit, uDist, uScale;
            out vec3 vN;
            out vec2 vAux;

            vec3 rot3(vec3 v, float ry, float rx) {
                float cy = cos(ry), sy = sin(ry);
                float x = v.x * cy - v.z * sy, z = v.x * sy + v.z * cy;
                float cx = cos(rx), sx = sin(rx);
                return vec3(x, v.y * cx - z * sx, v.y * sx + z * cx);
            }

            void main() {
                vec3 v = rot3(aPos, uYaw, uPit);
                float k = uScale / (uDist + v.z);
                vec2 sp = vec2(uRes.x * 0.5 + v.x * k, uRes.y * 0.5 + v.y * k);
                vN = rot3(aNrm, uYaw, uPit);
                vAux = aAux;
                gl_Position = vec4(
                    sp.x / uRes.x * 2.0 - 1.0,
                    1.0 - sp.y / uRes.y * 2.0,
                    clamp(v.z / 6.0, -0.999, 0.999),
                    1.0
                );
            }
        """.trimIndent()

        // The environment block goes in straight after `precision` - see
        // TokamakRenderer's FS for why it is joined rather than inlined.
        val FS = """
            #version 300 es
            precision highp float;
        """.trimIndent() + "\n" + GL.ENV_GLSL + """
            in vec3 vN;
            in vec2 vAux;
            out vec4 oCol;
            uniform vec3 uCol, uHot;

            const vec3 LIGHT = vec3(-0.4510, -0.7517, -0.4812);

            float fres3(float vdot) {
                float m = 1.0 - clamp(vdot, 0.0, 1.0);
                return m * m * m;
            }

            vec3 tonemap(vec3 c) {
                return c / (1.0 + c);
            }

            void main() {
                vec3 n = normalize(vN);
                float lam = max(0.0, -dot(n, LIGHT));
                float rim = fres3(abs(n.z));
                // Curvature picks out the wavefronts, height says which way
                // the skin is displaced - neither alone reads as a drum.
                float lift = clamp(0.5 + vAux.x * 3.0 + vAux.y * 1.1, 0.0, 1.0);
                vec3 base = mix(uCol * (0.35 + lam * 1.25), uHot, min(1.0, lift * 0.55 + rim * 0.4));
                vec3 col = mix(base, envSample(n), clamp(0.05 + rim * 0.28, 0.0, 1.0));
                oCol = vec4(tonemap(col), 1.0);
            }
        """.trimIndent()
    }

    private var program = 0
    private var aPosLoc = 0
    private var aNrmLoc = 0
    private var aAuxLoc = 0
    private var uResLoc = 0
    private var uYawLoc = 0
    private var uPitLoc = 0
    private var uDistLoc = 0
    private var uScaleLoc = 0
    private var uColLoc = 0
    private var uHotLoc = 0
    private var uEnvLoc = -1

    private var vao = 0
    private var posBuf = 0
    private var nrmBuf = 0
    private var auxBuf = 0
    private var idxBuf = 0
    private var envTex = 0
    private var indexCount = 0

    private var surfaceW = 1
    private var surfaceH = 1

    // The simulation, sized by GL.detail for the surface (see ensureGrid).
    // Three grids rotated each physics tick rather than copied, and a fixed
    // mask worked out once per size: the clamped rim, tested up front rather
    // than inside the step loop, where cells being zeroed mid-sweep is a
    // known way this kind of stencil detonates.
    private var n = 0
    private var mid = 0f
    private var z = FloatArray(0)
    private var zp = FloatArray(0)
    private var zn = FloatArray(0)
    private var mask = BooleanArray(0)
    /** Cells the stencil actually integrates. Fixed by [mask], so counted once. */
    private var liveCells = 1
    /**
     * The two excitation shapes - the kit's centre pulse, and the ring used
     * when `tf.dir` is negative - per cell. They depend only on the grid, so
     * they are worked out once per size instead of an `exp()` per cell per
     * tick, which at 168 cells would be 28,000 of them every tick.
     */
    private var centreFalloff = FloatArray(0)
    private var ringFalloff = FloatArray(0)
    /** The GPU side (index list, attribute stores) needs building for [n]. */
    private var gpuGridStale = true

    /** The drive's own phase: the kit's `t * p.rate`, integrated per tick. */
    private var drivePhase = 0f
    private var accumulator = 0f
    private var lastFrameNanos = 0L
    /**
     * RMS height of the live cells, carried between ticks. Accumulated inside
     * the stencil sweep that produces it rather than by a second full pass over
     * every cell per frame, which is what it used to cost.
     */
    private var rms = 0f

    // Vertex data. x and z of every vertex are fixed for a grid size (the
    // rim pull included), so they are written once in ensureGrid and only
    // the height is rewritten per frame.
    private var pos = FloatArray(0)
    private var nrm = FloatArray(0)
    private var aux = FloatArray(0)
    /** Vertices pulled onto the rim circle; their height is pinned to 0. */
    private var onRim = BooleanArray(0)

    // One direct buffer per attribute for the life of a grid size. These were
    // once a fresh `ByteBuffer.allocateDirect` each, three times a frame -
    // native memory that only the Cleaner ever hands back, so at frame rate it
    // accumulates faster than it is freed.
    private var posFb = GL.directFloatBuffer(0)
    private var nrmFb = GL.directFloatBuffer(0)
    private var auxFb = GL.directFloatBuffer(0)

    // Written from the UI thread via queueEvent, read only on the GL thread.
    private var frame: FaceFrame? = null
    private var hot = Color(0xFF8AD8FF)
    private var cool = Color(0xFF2F5FA8)
    private var fit = 1f
    private var background = Spec.BACKGROUND

    override fun setFrame(f: FaceFrame, hot: Color, cool: Color, fit: Float, background: Color) {
        this.frame = f
        this.hot = hot
        this.cool = cool
        this.fit = fit
        this.background = background
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // The renderer INSTANCE outlives any one EGL context - GLSurfaceView
        // calls this again on the same object after a context loss - and
        // nothing here ever deleted what it was about to overwrite. That is
        // harmless only while `setPreserveEGLContextOnPause` stays at its
        // default false, because the lost context takes the objects with it;
        // preserve the context and every background/foreground cycle leaks a
        // program, a VAO, four buffers and a texture. Deleting first is right
        // either way: after a real context loss the stale ids name nothing in
        // the new context and the driver ignores them.
        deleteGlObjects()
        // Rendering stopped while the context was gone, so the clock this
        // renderer measures its own timestep with is stale by however long that
        // was. See RESUME_GAP_S.
        lastFrameNanos = 0L
        // Caught rather than thrown - same reasoning as TokamakRenderer's copy
        // of this. `GL.compileProgram` ends in `error(...)` on GLSurfaceView's
        // GLThread, where nothing catches it, and the chosen face is persisted:
        // a driver that rejects this shader killed the process on every launch
        // until app data was cleared.
        program = runCatching { GL.compileProgram(VS, FS) }
            .onFailure {
                Log.w("JarvisFaceGL", "Membrane shader would not build; face disabled", it)
                GL.lastBuildFailure = "membrane: ${it.message}"
            }
            .getOrDefault(0)
        if (program == 0) return
        aPosLoc = GLES30.glGetAttribLocation(program, "aPos")
        aNrmLoc = GLES30.glGetAttribLocation(program, "aNrm")
        aAuxLoc = GLES30.glGetAttribLocation(program, "aAux")
        uResLoc = GLES30.glGetUniformLocation(program, "uRes")
        uYawLoc = GLES30.glGetUniformLocation(program, "uYaw")
        uPitLoc = GLES30.glGetUniformLocation(program, "uPit")
        uDistLoc = GLES30.glGetUniformLocation(program, "uDist")
        uScaleLoc = GLES30.glGetUniformLocation(program, "uScale")
        uColLoc = GLES30.glGetUniformLocation(program, "uCol")
        uHotLoc = GLES30.glGetUniformLocation(program, "uHot")
        uEnvLoc = GLES30.glGetUniformLocation(program, "uEnv")

        val vaoArr = IntArray(1)
        GLES30.glGenVertexArrays(1, vaoArr, 0)
        vao = vaoArr[0]
        val bufs = IntArray(4)
        GLES30.glGenBuffers(4, bufs, 0)
        posBuf = bufs[0]
        nrmBuf = bufs[1]
        auxBuf = bufs[2]
        idxBuf = bufs[3]
        envTex = GL.envTexture()

        // The index list and attribute stores depend on the grid size, which
        // depends on the surface size - built on the first frame that knows
        // it (see ensureGrid).
        gpuGridStale = true

        GLES30.glEnable(GLES30.GL_DEPTH_TEST)
        GLES30.glDepthFunc(GLES30.GL_LEQUAL)
    }

    private fun deleteGlObjects() {
        if (program != 0) {
            GLES30.glDeleteProgram(program)
            program = 0
        }
        if (vao != 0) {
            GLES30.glDeleteVertexArrays(1, intArrayOf(vao), 0)
            vao = 0
        }
        if (posBuf != 0 || nrmBuf != 0 || auxBuf != 0 || idxBuf != 0) {
            GLES30.glDeleteBuffers(4, intArrayOf(posBuf, nrmBuf, auxBuf, idxBuf), 0)
            posBuf = 0
            nrmBuf = 0
            auxBuf = 0
            idxBuf = 0
        }
        if (envTex != 0) {
            GLES30.glDeleteTextures(1, intArrayOf(envTex), 0)
            envTex = 0
        }
    }

    private fun allocAttr(buf: Int, bytes: Int) {
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, buf)
        GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER, bytes, null, GLES30.GL_DYNAMIC_DRAW)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        surfaceW = max(1, width)
        surfaceH = max(1, height)
        GLES30.glViewport(0, 0, surfaceW, surfaceH)
    }

    /**
     * Sizes the grid to the kit's `detail()` for this surface. A new size
     * starts the skin flat again, as the kit's does when its `N` changes;
     * detail() moves in whole cells, so resizing the face's pane restarts
     * the drum a handful of times, not on every pixel of the drag.
     */
    private fun ensureGrid() {
        val want = GL.detail(GL.meshPx(surfaceW, surfaceH), 40, 150, 168)
        if (want != n) {
            n = want
            mid = (n - 1) / 2f
            val cells = n * n
            z = FloatArray(cells)
            zp = FloatArray(cells)
            zn = FloatArray(cells)
            rms = 0f
            mask = BooleanArray(cells) { idx ->
                val i = idx % n
                val j = idx / n
                val di = i - mid
                val dj = j - mid
                i > 0 && j > 0 && i < n - 1 && j < n - 1 && sqrt(di * di + dj * dj) / mid <= 0.96f
            }
            liveCells = max(1, mask.count { it })
            // Tuned in CELLS on a 26-cell grid in the kit; scaling by the grid
            // keeps the strike the same FRACTION of the skin at any size.
            val gs = (26f / n) * (26f / n)
            val ringR = mid * RING_SOURCE_R_FRAC
            centreFalloff = FloatArray(cells)
            ringFalloff = FloatArray(cells)
            for (q in 0 until cells) {
                val di = q % n - mid
                val dj = q / n - mid
                val cd = di * di + dj * dj
                centreFalloff[q] = exp(-cd * 0.10f * gs)
                val d = sqrt(cd) - ringR
                ringFalloff[q] = exp(-d * d * 0.10f * gs)
            }

            // Fixed vertex positions: the rim is a circle, so vertices past
            // it are pulled ONTO it rather than left sticking out - without
            // that the silhouette is a polygon with one side per grid cell.
            pos = FloatArray(cells * 3)
            nrm = FloatArray(cells * 3)
            aux = FloatArray(cells * 2)
            onRim = BooleanArray(cells)
            val step = 1.9f / n
            val rimR = mid * 0.96f
            for (q in 0 until cells) {
                val di = q % n - mid
                val dj = q / n - mid
                val rr = sqrt(di * di + dj * dj)
                var gi = di
                var gj = dj
                if (rr > rimR && rr > 0f) {
                    val pull = rimR / rr
                    gi = di * pull
                    gj = dj * pull
                    onRim[q] = true
                }
                pos[q * 3] = gi * step
                pos[q * 3 + 2] = gj * step
            }
            posFb = GL.directFloatBuffer(pos.size)
            nrmFb = GL.directFloatBuffer(nrm.size)
            auxFb = GL.directFloatBuffer(aux.size)
            gpuGridStale = true
        }
        if (!gpuGridStale) return

        // A quad whose centre strays past the rim is cut rather than left in,
        // for the same reason the rim vertices are pulled in.
        val tris = ArrayList<Int>(n * n * 6)
        for (j in 0 until n - 1) {
            for (i in 0 until n - 1) {
                val di = i - mid + 0.5f
                val dj = j - mid + 0.5f
                if (sqrt(di * di + dj * dj) / mid > 0.99f) continue
                val a = j * n + i
                val b = j * n + i + 1
                val c = (j + 1) * n + i + 1
                val d = (j + 1) * n + i
                tris.add(a); tris.add(b); tris.add(c)
                tris.add(a); tris.add(c); tris.add(d)
            }
        }
        indexCount = tris.size
        GLES30.glBindVertexArray(vao)
        GLES30.glBindBuffer(GLES30.GL_ELEMENT_ARRAY_BUFFER, idxBuf)
        GLES30.glBufferData(
            GLES30.GL_ELEMENT_ARRAY_BUFFER,
            indexCount * 4,
            GL.intBuffer(tris.toIntArray()),
            GLES30.GL_STATIC_DRAW,
        )
        GLES30.glBindVertexArray(0)

        // The three attribute stores are DYNAMIC but FIXED SIZE for a grid,
        // so their GPU storage is allocated here (`null` data = uninitialised
        // store) and refilled with glBufferSubData every frame. Calling
        // glBufferData per frame instead orphans and re-allocates the whole
        // store on the driver side, three times a frame, for nothing.
        allocAttr(posBuf, pos.size * 4)
        allocAttr(nrmBuf, nrm.size * 4)
        allocAttr(auxBuf, aux.size * 4)
        gpuGridStale = false
    }

    override fun onDrawFrame(gl: GL10?) {
        // The shader did not build on this device (see onSurfaceCreated). A
        // dark, still surface beats an uninitialised framebuffer - and beats
        // the process dying, which is what used to happen instead.
        if (program == 0) {
            GLES30.glClearColor(background.red, background.green, background.blue, 1f)
            GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
            return
        }
        val f = frame ?: return
        ensureGrid()
        step(f)
        upload()
        draw(f)
    }

    /** Advances the simulation by whatever real time has actually passed. */
    private fun step(f: FaceFrame) {
        val st = stFor(f.motion)
        // The STATE's transform, not the borrowed motion's table. Every other
        // face gets this for free, because every other face reads `f.angle` and
        // the shell has already folded `tf.rate` and `tf.dir` into it
        // (`FaceView.advance`: `angle += dt * rate * tf.dir * faceSpeed`). This
        // one builds its own clock out of `System.nanoTime()` - deliberately,
        // so the physics is not throttled by the frame-rate gate - and in doing
        // so it has to apply the transform layer itself: BANKED's `rate 0.0`,
        // which the spec says means "the clock actually stops", STANDBY's 0.5,
        // and ERROR's reversal (see the excitation below).
        val tf = Spec.transformFor(f.state)
        val now = System.nanoTime()
        val elapsed = if (lastFrameNanos == 0L) {
            0f
        } else {
            ((now - lastFrameNanos) / 1_000_000_000.0).toFloat()
        }
        lastFrameNanos = now
        // A gap this long means rendering had STOPPED, not that the device was
        // slow; the time did not pass for the drum, so it is dropped outright
        // rather than clamped and then chased. Without this the first frame
        // after any resume spends the whole step budget on catch-up.
        val dt = if (elapsed > RESUME_GAP_S) 0f else elapsed

        // Calm motion slows the drum the way the shell slows every other
        // face's clock. This face keeps its own clock, so the shell's slowing
        // of `f.angle` and `f.t` never reaches it; this is the one place it
        // has to be applied by hand. A factor below 1 only ever means fewer
        // physics ticks per second - slower, never faster.
        val calmK = if (f.calm) CALM_MOTION_RATE else 1f
        // 60 ticks a second in every state, as the kit ticks once a frame
        // whatever the state is - NOT times st.rate (see the class comment).
        accumulator += dt * tf.rate * calmK
        // The only place time is discarded. See MAX_STEPS_PER_FRAME: the cap is
        // the worst legitimate frame, so this trims genuine stalls only, and
        // the loop below drains the whole of what is left.
        val backlogCap = MAX_STEPS_PER_FRAME * FIXED_STEP
        if (accumulator > backlogCap) accumulator = backlogCap

        // How hard the skin is struck, before the energy limiter. A drum driven
        // at a fixed rate with light damping pumps itself to infinity, which is
        // a real failure mode of this stencil, not a hypothetical one.
        val driveBase = st.drive * (if (f.motion == FaceState.LISTENING) 0.4f + f.amp * 2.2f else 1f)
        val k = min(0.24f, st.k)
        val cells = n * n
        // WHERE the drive is applied is `tf.dir`. Negating the drive's phase -
        // the obvious reading of "backwards" - is not visible on a drum: an
        // inverted sine at the same point source still radiates outward, which
        // is the one thing the direction is supposed to tell you apart from. So
        // the source MOVES instead. Forwards it is the reference's own point
        // source at the centre and the rings expand; backwards it is a ring out
        // near the rim, and the rings collapse inward onto the centre. Nothing
        // else in this app moves inward, which is the point of `tf.dir` per
        // `Spec.transformFor`: "the direction is the signal ... colour alone
        // fails for the one man in twelve with a red-green deficiency".
        //
        // This is an interpretation, not a port - the reference has no
        // reversed membrane to copy - so it is the one thing here worth a
        // second opinion from a real screen.
        val falloff = if (tf.dir < 0) ringFalloff else centreFalloff

        var steps = 0
        while (accumulator >= FIXED_STEP && steps < MAX_STEPS_PER_FRAME) {
            accumulator -= FIXED_STEP
            // The kit's `ph = t * p.rate`: the state's rate sets how fast the
            // centre is driven, integrated so a state change bends the phase
            // rather than jumping it.
            drivePhase += FIXED_STEP * st.rate

            // Jacobi, not Gauss-Seidel: read z and zp, write zn, then rotate.
            // Mixing already-updated neighbours into the same sweep injects
            // energy.
            var energy = 0f
            for (q in 0 until cells) {
                if (!mask[q]) { zn[q] = 0f; continue }
                val acc = (z[q - 1] + z[q + 1] + z[q - n] + z[q + n] - 4f * z[q]) * k
                var nv = z[q] + (z[q] - zp[q]) * st.damp + acc
                // Hard ceiling. One bad frame should bend the skin, never
                // launch a spike off the screen.
                if (nv > 1.2f) nv = 1.2f else if (nv < -1.2f) nv = -1.2f
                zn[q] = nv
                energy += nv * nv
            }
            val tmp = zp
            zp = z
            z = zn
            zn = tmp
            // Free: the sweep above already touched every live cell. Re-read
            // per TICK rather than per frame, because a frame can carry dozens
            // of ticks - a limiter held fixed across a long catch-up burst is a
            // limiter that does not limit.
            rms = sqrt(energy / liveCells)
            val drive = driveBase * max(0f, 1f - rms / 0.27f)

            // Excitation applied after the step, so it reads as a real
            // impulse rather than a forced boundary condition.
            val kick = drive * 0.30f * sin(drivePhase * 1.3f)
            for (q in 0 until cells) {
                if (mask[q]) z[q] += falloff[q] * kick
            }
            steps++
        }
    }

    /** Hands the simulated grid to the GPU as a triangle mesh, rebuilt every frame since it IS the simulation. */
    private fun upload() {
        val step = 1.9f / n
        for (j in 0 until n) {
            for (i in 0 until n) {
                val q = j * n + i
                val o3 = q * 3
                val o2 = q * 2
                pos[o3 + 1] = if (onRim[q]) 0f else z[q] * AMPL_H

                // Central differences where they exist, one-sided at the border.
                val iL = if (i > 0) q - 1 else q
                val iR = if (i < n - 1) q + 1 else q
                val jU = if (j > 0) q - n else q
                val jD = if (j < n - 1) q + n else q
                val gx = (z[iR] - z[iL]) * AMPL_H
                val gy = (z[jD] - z[jU]) * AMPL_H
                val nX = -gx
                val nY = step * 2f
                val nZ = -gy
                val nl = sqrt(nX * nX + nY * nY + nZ * nZ).let { if (it == 0f) 1f else it }
                nrm[o3] = nX / nl
                nrm[o3 + 1] = nY / nl
                nrm[o3 + 2] = nZ / nl

                aux[o2] = z[iL] + z[iR] + z[jU] + z[jD] - 4f * z[q]
                aux[o2 + 1] = z[q] * AMPL_H
            }
        }

        GLES30.glBindVertexArray(vao)
        uploadAttr(posBuf, aPosLoc, pos, posFb, 3)
        uploadAttr(nrmBuf, aNrmLoc, nrm, nrmFb, 3)
        uploadAttr(auxBuf, aAuxLoc, aux, auxFb, 2)
        GLES30.glBindBuffer(GLES30.GL_ELEMENT_ARRAY_BUFFER, idxBuf)
    }

    private fun draw(f: FaceFrame) {
        // The caller's ground (the theme's well), not a fixed Spec.BACKGROUND,
        // so this face sits in the same black as the pane around it.
        GLES30.glClearColor(background.red, background.green, background.blue, 1f)
        GLES30.glClearDepthf(1f)
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
        GLES30.glDisable(GLES30.GL_BLEND)
        GLES30.glUseProgram(program)
        GL.bindEnv(envTex, uEnvLoc)

        GLES30.glUniform2f(uResLoc, surfaceW.toFloat(), surfaceH.toFloat())
        // No auto-spin term here - see the class doc comment on why the
        // camera stays touch-only for this face specifically.
        GLES30.glUniform1f(uYawLoc, f.yaw)
        GLES30.glUniform1f(uPitLoc, -0.72f + f.pitch)
        GLES30.glUniform1f(uDistLoc, DIST)
        // The kit's `scale = S * 1.35`, with S = 4r: the kit's canvas is the
        // face's box scaled by `fit`, and the shell hands every face r = box
        // / 4 x fit - the same S = 4r every canvas face in Faces.kt uses. This
        // used to fit the skin's half-extent (mid * step) to r, which drew it
        // at about 0.82 of the kit's size.
        val r = min(surfaceW, surfaceH) / 2f * 0.5f * fit
        GLES30.glUniform1f(uScaleLoc, 4f * r * 1.35f)
        GLES30.glUniform3f(uColLoc, cool.red, cool.green, cool.blue)
        GLES30.glUniform3f(uHotLoc, hot.red, hot.green, hot.blue)

        GLES30.glDrawElements(GLES30.GL_TRIANGLES, indexCount, GLES30.GL_UNSIGNED_INT, 0)
        GLES30.glBindVertexArray(0)
    }

    private fun uploadAttr(buf: Int, loc: Int, data: FloatArray, fb: FloatBuffer, size: Int) {
        if (loc < 0) return
        // Refill the one persistent buffer and update the one persistent GPU
        // store. Position is reset on both sides of the fill so the next frame
        // finds it exactly as this one did.
        fb.position(0)
        fb.put(data)
        fb.position(0)
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, buf)
        GLES30.glBufferSubData(GLES30.GL_ARRAY_BUFFER, 0, data.size * 4, fb)
        GLES30.glEnableVertexAttribArray(loc)
        GLES30.glVertexAttribPointer(loc, size, GLES30.GL_FLOAT, false, 0, 0)
    }
}
