package com.jarvis.client.face.gl

import android.opengl.GLES30
import androidx.compose.ui.graphics.Color
import com.jarvis.client.FaceState
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
 * one. This is the one face in this app that genuinely cannot be a pure
 * function of `t`: each node's height depends on the two heights before it,
 * so it needs real state that persists between frames. Unlike a `Face`
 * singleton (shared, stateless, safe because it holds nothing but a
 * compiled program), a [MembraneRenderer] is created fresh per composition
 * by [MeshFaces] - exactly the right place to own that state, since it
 * already has to own live GL object ids tied to one specific surface.
 *
 * Ported close to the reference's own physics (`draw()` in the desktop's
 * `faces.html`: the five-point Laplacian stencil, the rim clamp, the
 * energy/"room" limiter that backs off the drive as the skin gets livelier)
 * and its GPU mesh upload (`gpu()`: central-difference normals from the
 * slope of the simulated heights, the rim pulled onto a circle rather than
 * left jagged, `MEMBRANE_VS`/`MEMBRANE_FS`). Nucleus and Tokamak's
 * precedent is followed for what's dropped and why: no environment
 * texture, no `HUD.beat`, and the shell's own hot/cool in place of the
 * reference's hardcoded per-state colours.
 *
 * Three things are NOT literal ports, because the reference's own model for
 * them has no honest Android equivalent:
 *
 *  - Time stepping. The reference advances Verlet by a whole tick per frame
 *    at 1x and takes extra whole substeps above it, both driven by a global
 *    `SPEED` slider this app has no equivalent of - `speedFor` only ever
 *    scales an accumulated phase, never hands a face a raw multiplier. This
 *    uses a standard fixed-timestep accumulator instead: real elapsed time
 *    between frames feeds an accumulator (scaled by the state's own `rate`,
 *    playing the same role `p.rate` plays in the reference), which drains
 *    in fixed-size physics ticks - the numerically stable technique this
 *    kind of explicit stencil is normally built on anyway, and it needs no
 *    translation of a slider that was never there. The backlog IS chased,
 *    up to [MAX_STEPS_PER_FRAME] - that bound is what stops a stall from
 *    bursting, and it is set high enough that no real render rate in the
 *    spec is throttled into slow motion by it.
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
        // Conservative and fixed rather than the reference's adaptive
        // detail() ramp, matching Tokamak's own reasoning - there is no
        // device here to profile it against.
        const val N = 40
        const val AMPL_H = 0.42f
        const val DIST = 4.2f
        const val FIXED_STEP = 1f / 60f

        // How much simulated time one rendered frame may carry.
        //
        // The old ceiling of 4 ticks (0.067 s of sim) coupled the drum's speed
        // to the panel and to the shell's frame-rate gate, because the surplus
        // was thrown away: THINKING asks for rate 6.0, which is 0.1 s of sim
        // per 60 Hz frame and could never fit in 4 ticks, so the same state ran
        // at 4.0x on a 60 Hz phone and 6.0x on a 120 Hz one. Worse, the shell
        // renders BANKED at 2 fps - 0.5 s of real time per frame, 0.7 s of sim
        // at that state's rate 1.4 - so the membrane crawled at about an eighth
        // of real speed, breaking the contract FaceView states for every other
        // face: frame skipping, not slow motion.
        //
        // The bound is the worst LEGITIMATE case, so nothing real is discarded
        // and a genuine stall still cannot burst without limit: the slowest
        // render rate in the spec is BANKED's 2 fps (0.5 s), and the highest
        // rate any state asks for is THINKING's 6.0 - but those never coincide,
        // since BANKED's borrowed motion is a resting one. 0.8 s of sim, 48
        // ticks, covers BANKED at 0.7 s with slack and is ~150 k cell updates
        // in the worst frame, which that state only reaches twice a second.
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

        val FS = """
            #version 300 es
            precision highp float;
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
                vec3 env = vec3(22.0, 24.0, 30.0) / 255.0;
                vec3 col = mix(base, env, clamp(0.05 + rim * 0.28, 0.0, 1.0));
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

    private var vao = 0
    private var posBuf = 0
    private var nrmBuf = 0
    private var auxBuf = 0
    private var idxBuf = 0
    private var indexCount = 0

    private var surfaceW = 1
    private var surfaceH = 1

    // The simulation. Three grids rotated each physics tick rather than
    // copied, and a fixed mask worked out once: the clamped rim, tested
    // once up front rather than inside the step loop, where cells being
    // zeroed mid-sweep is a known way this kind of stencil detonates.
    private val mid = (N - 1) / 2f
    private var z = FloatArray(N * N)
    private var zp = FloatArray(N * N)
    private var zn = FloatArray(N * N)
    private val mask = BooleanArray(N * N) { idx ->
        val i = idx % N
        val j = idx / N
        val di = i - mid
        val dj = j - mid
        i > 0 && j > 0 && i < N - 1 && j < N - 1 && sqrt(di * di + dj * dj) / mid <= 0.96f
    }
    /** Cells the stencil actually integrates. Fixed by [mask], so counted once. */
    private val liveCells = max(1, mask.count { it })
    private var physicsTime = 0f
    private var accumulator = 0f
    private var lastFrameNanos = 0L
    /**
     * RMS height of the live cells, carried between ticks. Accumulated inside
     * the stencil sweep that produces it rather than by a second full pass over
     * all 1600 cells per frame, which is what it used to cost.
     */
    private var rms = 0f

    // Written from the UI thread via queueEvent, read only on the GL thread.
    private var frame: FaceFrame? = null
    private var hot = Color(0xFF8AD8FF)
    private var cool = Color(0xFF2F5FA8)
    private var fit = 1f

    override fun setFrame(f: FaceFrame, hot: Color, cool: Color, fit: Float) {
        this.frame = f
        this.hot = hot
        this.cool = cool
        this.fit = fit
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // The renderer INSTANCE outlives any one EGL context - GLSurfaceView
        // calls this again on the same object after a context loss - and
        // nothing here ever deleted what it was about to overwrite. That is
        // harmless only while `setPreserveEGLContextOnPause` stays at its
        // default false, because the lost context takes the objects with it;
        // preserve the context and every background/foreground cycle leaks a
        // program, a VAO and four buffers. Deleting first is right either way:
        // after a real context loss the stale ids name nothing in the new
        // context and the driver ignores them.
        deleteGlObjects()
        // Rendering stopped while the context was gone, so the clock this
        // renderer measures its own timestep with is stale by however long that
        // was. See RESUME_GAP_S.
        lastFrameNanos = 0L
        program = GL.compileProgram(VS, FS)
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

        val vaoArr = IntArray(1)
        GLES30.glGenVertexArrays(1, vaoArr, 0)
        vao = vaoArr[0]
        val bufs = IntArray(4)
        GLES30.glGenBuffers(4, bufs, 0)
        posBuf = bufs[0]
        nrmBuf = bufs[1]
        auxBuf = bufs[2]
        idxBuf = bufs[3]

        // The rim is a circle, so a quad whose corners stray past it is cut
        // rather than left in - otherwise the silhouette is a polygon with
        // one side per grid cell, which is most of what reads as "jagged".
        val tris = ArrayList<Int>(N * N * 6)
        for (j in 0 until N - 1) {
            for (i in 0 until N - 1) {
                val di = i - mid + 0.5f
                val dj = j - mid + 0.5f
                if (sqrt(di * di + dj * dj) / mid > 0.99f) continue
                val a = j * N + i
                val b = j * N + i + 1
                val c = (j + 1) * N + i + 1
                val d = (j + 1) * N + i
                tris.add(a); tris.add(b); tris.add(c)
                tris.add(a); tris.add(c); tris.add(d)
            }
        }
        indexCount = tris.size
        val idxData = GL.intBuffer(tris.toIntArray())
        GLES30.glBindVertexArray(vao)
        GLES30.glBindBuffer(GLES30.GL_ELEMENT_ARRAY_BUFFER, idxBuf)
        GLES30.glBufferData(
            GLES30.GL_ELEMENT_ARRAY_BUFFER,
            indexCount * 4,
            idxData,
            GLES30.GL_STATIC_DRAW,
        )
        GLES30.glBindVertexArray(0)

        // The three attribute stores are DYNAMIC but FIXED SIZE, so their GPU
        // storage is allocated once here (`null` data = uninitialised store)
        // and refilled with glBufferSubData every frame. Calling glBufferData
        // per frame instead orphans and re-allocates the whole store on the
        // driver side, three times a frame, for nothing.
        allocAttr(posBuf, pos.size * 4)
        allocAttr(nrmBuf, nrm.size * 4)
        allocAttr(auxBuf, aux.size * 4)

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

    override fun onDrawFrame(gl: GL10?) {
        val f = frame ?: return
        step(f)
        upload()
        draw(f)
    }

    /** Advances the simulation by whatever real time has actually passed. */
    private fun step(f: FaceFrame) {
        val st = stFor(f.motion)
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

        accumulator += dt * st.rate
        // The only place time is discarded. See MAX_STEPS_PER_FRAME: the cap is
        // the worst legitimate frame, so this trims genuine stalls only, and
        // the loop below drains the whole of what is left - the physics runs at
        // the state's rate whatever the panel and the frame-rate gate are doing.
        val backlogCap = MAX_STEPS_PER_FRAME * FIXED_STEP
        if (accumulator > backlogCap) accumulator = backlogCap

        // How hard the skin is struck, before the energy limiter. A drum driven
        // at a fixed rate with light damping pumps itself to infinity, which is
        // a real failure mode of this stencil, not a hypothetical one.
        val driveBase = st.drive * (if (f.motion == FaceState.LISTENING) 0.4f + f.amp * 2.2f else 1f)
        // Tuned in CELLS on a small grid; scaling by the grid keeps the
        // strike the same FRACTION of the skin at any resolution.
        val gs = (26f / N) * (26f / N)
        val k = min(0.24f, st.k)

        var steps = 0
        while (accumulator >= FIXED_STEP && steps < MAX_STEPS_PER_FRAME) {
            accumulator -= FIXED_STEP
            physicsTime += FIXED_STEP

            var energy = 0f
            for (q in 0 until N * N) {
                if (!mask[q]) { zn[q] = 0f; continue }
                val acc = (z[q - 1] + z[q + 1] + z[q - N] + z[q + N] - 4f * z[q]) * k
                var nv = z[q] + (z[q] - zp[q]) * st.damp + acc
                if (nv > 1.2f) nv = 1.2f else if (nv < -1.2f) nv = -1.2f
                zn[q] = nv
                energy += nv * nv
            }
            val tmp = zp
            zp = z
            z = zn
            zn = tmp
            // Free: the sweep above already touched every live cell. It used to
            // be a separate 1600-cell pass per frame, and re-evaluating it per
            // TICK rather than per frame matters now that a frame can carry
            // dozens of ticks - a limiter held fixed across a long catch-up
            // burst is a limiter that does not limit.
            rms = sqrt(energy / liveCells)
            val drive = driveBase * max(0f, 1f - rms / 0.27f)

            // Excitation applied after the step, so it reads as a real
            // impulse rather than a forced boundary condition.
            val ph = physicsTime
            for (j in 1 until N - 1) {
                for (i in 1 until N - 1) {
                    val q = j * N + i
                    if (!mask[q]) continue
                    val di = i - mid
                    val dj = j - mid
                    val cd = di * di + dj * dj
                    z[q] += exp(-cd * 0.10f * gs) * (drive * 0.30f * sin(ph * 1.3f))
                }
            }
            steps++
        }
    }

    private val pos = FloatArray(N * N * 3)
    private val nrm = FloatArray(N * N * 3)
    private val aux = FloatArray(N * N * 2)

    // One direct buffer per attribute for the life of the renderer. These were
    // a fresh `ByteBuffer.allocateDirect` each, three times a frame - ~51 KB a
    // frame of native memory that only the Cleaner ever hands back, so at frame
    // rate it accumulates faster than it is freed. The sizes are fixed, so one
    // each is all that was ever needed.
    private val posFb = GL.directFloatBuffer(pos.size)
    private val nrmFb = GL.directFloatBuffer(nrm.size)
    private val auxFb = GL.directFloatBuffer(aux.size)

    /** Hands the simulated grid to the GPU as a triangle mesh, rebuilt every frame since it IS the simulation. */
    private fun upload() {
        val step = 1.9f / N
        val rimR = mid * 0.96f
        for (j in 0 until N) {
            for (i in 0 until N) {
                val q = j * N + i
                val o3 = q * 3
                val o2 = q * 2
                val di = i - mid
                val dj = j - mid
                val rr = sqrt(di * di + dj * dj)
                var gi = i.toFloat()
                var gj = j.toFloat()
                var hh = z[q] * AMPL_H
                if (rr > rimR && rr > 0f) {
                    val fpull = rimR / rr
                    gi = mid + di * fpull
                    gj = mid + dj * fpull
                    hh = 0f
                }
                pos[o3] = (gi - mid) * step
                pos[o3 + 1] = hh
                pos[o3 + 2] = (gj - mid) * step

                val iL = if (i > 0) q - 1 else q
                val iR = if (i < N - 1) q + 1 else q
                val jU = if (j > 0) q - N else q
                val jD = if (j < N - 1) q + N else q
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
        GLES30.glClearColor(Spec.BACKGROUND.red, Spec.BACKGROUND.green, Spec.BACKGROUND.blue, 1f)
        GLES30.glClearDepthf(1f)
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
        GLES30.glDisable(GLES30.GL_BLEND)
        GLES30.glUseProgram(program)

        GLES30.glUniform2f(uResLoc, surfaceW.toFloat(), surfaceH.toFloat())
        // No auto-spin term here - see the class doc comment on why the
        // camera stays touch-only for this face specifically.
        GLES30.glUniform1f(uYawLoc, f.yaw)
        GLES30.glUniform1f(uPitLoc, -0.72f + f.pitch)
        GLES30.glUniform1f(uDistLoc, DIST)
        // Same derivation as Tokamak's: r (the on-screen radius every face
        // is handed) at this scale makes the skin's own object-space half
        // extent (mid * step) fill roughly that radius.
        val r = min(surfaceW, surfaceH) / 2f * 0.5f * fit
        val halfExtent = mid * (1.9f / N)
        GLES30.glUniform1f(uScaleLoc, r * DIST / halfExtent)
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
