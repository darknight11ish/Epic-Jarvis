package com.jarvis.client.face.gl

import android.opengl.GLES30
import android.opengl.GLSurfaceView
import androidx.compose.ui.graphics.Color
import com.jarvis.client.FaceState
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.Spec
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin

/**
 * A face rendered through a real GLES 3.0 mesh rather than `Face.draw`'s
 * `DrawScope` calls. FaceView drives it with the same [FaceFrame] every
 * other face gets, from the UI thread; [setFrame] is the one method that
 * crosses onto the GL thread, via `GLSurfaceView.queueEvent` - nothing else
 * on a renderer is safe to call off it, which is `GLSurfaceView`'s own
 * contract, not one this app invents.
 */
interface MeshRenderer : GLSurfaceView.Renderer {
    fun setFrame(f: FaceFrame, hot: Color, cool: Color, fit: Float)
}

/**
 * The desktop's own torus mesh (32x12 shaded quads there), ported close to
 * `TOKAMAK_VS`/`TOKAMAK_FS` in the desktop's `faces.html`. Rotation and the
 * perspective divide happen in the vertex shader exactly as the reference
 * does it - the same `k = scale / (dist + z)` division every other 3D face
 * in this app already does on the CPU, just moved onto the GPU because this
 * one draws as a real mesh instead of lines and circles.
 *
 * Two things are dropped, matching Nucleus's own precedent and for the same
 * reasons (see its doc comment in `Faces.kt`): the reference's
 * environment-reflection texture (no panorama to sample on a phone, so this
 * always takes its own no-texture fallback tone), and `HUD.beat`, a global
 * pulse nothing in this app drives - the bass-hit "kick" term it fed is
 * simply absent, not zeroed.
 *
 * A third thing is dropped, and unlike the two above it is not a "nothing to
 * plug in" gap: the reference's own hardcoded per-state accent colour and
 * its separately defined "plate" colour. Every canvas face in this app
 * shades with the `hot`/`cool` it is handed - the user's own chosen binding
 * for the current state - and this uses that same pair (`uA` = hot, `uPlate`
 * = cool) rather than a private palette that would make this the one face
 * immune to the colour picker. Geometry (flow/tightness/instability, which
 * have no user-facing control) keeps the reference's own per-state table.
 */
class TokamakRenderer : MeshRenderer {

    private data class St(val flow: Float, val tight: Float, val inst: Float)

    private fun stFor(motion: FaceState): St = when (motion) {
        FaceState.LISTENING -> St(flow = 2.6f, tight = 9f, inst = 0.05f)
        FaceState.THINKING -> St(flow = 5.5f, tight = 14f, inst = 0.32f)
        FaceState.SPEAKING -> St(flow = 1.8f, tight = 5f, inst = 0.12f)
        else -> St(flow = 1.0f, tight = 6f, inst = 0f)
    }

    private companion object {
        // The reference's own high tier is 150x64 vertices, chosen by its
        // detail() ramp against the real device it is running on. There is
        // no device here to profile this against, and the whole mesh is
        // rebuilt and re-uploaded every frame - it has to be, the wobble is
        // a function of time, same as the reference's own mesh() does
        // unconditionally - so a fixed, conservative grid is the safer
        // default until it can be measured on real hardware and raised.
        const val NU = 48
        const val NV = 18
        const val OBJ_R = 0.72f
        const val OBJ_R0 = 0.29f
        const val DIST = 4.0f
        val TAU = (Math.PI * 2).toFloat()

        val VS = """
            #version 300 es
            precision highp float;
            in vec3 aPos;
            in vec3 aNrm;
            in float aCur;
            uniform vec2 uRes;
            uniform float uYaw, uPit, uDist, uScale;
            out vec3 vN;
            out float vCur;

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
                vCur = aCur;
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
            in float vCur;
            out vec4 oCol;
            uniform vec3 uPlate, uA;

            const vec3 LIGHT = vec3(-0.4510, -0.7517, -0.4812);

            vec3 tonemap(vec3 c) {
                return c / (1.0 + c);
            }

            void main() {
                vec3 n = normalize(vN);
                float lam = max(0.0, -dot(n, LIGHT));
                float rim = pow(1.0 - min(1.0, abs(n.z)), 2.6);
                vec3 env = vec3(22.0, 24.0, 30.0) / 255.0;
                vec3 base = uPlate * (0.22 + lam * 1.05);
                base = mix(base, env, clamp(0.06 + rim * 0.4, 0.0, 1.0));
                base = mix(base, uA, min(0.9, rim * 0.85));
                base = mix(base, uA, min(1.0, vCur * 0.95));
                oCol = vec4(tonemap(base), 1.0);
            }
        """.trimIndent()
    }

    private var program = 0
    private var aPosLoc = 0
    private var aNrmLoc = 0
    private var aCurLoc = 0
    private var uResLoc = 0
    private var uYawLoc = 0
    private var uPitLoc = 0
    private var uDistLoc = 0
    private var uScaleLoc = 0
    private var uPlateLoc = 0
    private var uALoc = 0

    private var vao = 0
    private var posBuf = 0
    private var nrmBuf = 0
    private var curBuf = 0
    private var idxBuf = 0
    private var indexCount = 0

    private var surfaceW = 1
    private var surfaceH = 1

    // The mesh, built on the CPU every frame (the wobble is a function of
    // time, so it has to be) but allocated exactly once.
    //
    // These three used to be `FloatArray(...)` locals inside `onDrawFrame` -
    // ~26 KB of Java heap churn per frame at up to 120 fps, which is pure GC
    // pressure on the one code path in the app that must never stutter.
    // `MembraneRenderer` already held its equivalents as fields; this one was
    // simply missed.
    private val vertCount = (NU + 1) * (NV + 1)
    private val pos = FloatArray(vertCount * 3)
    private val nrm = FloatArray(vertCount * 3)
    private val cur = FloatArray(vertCount)

    // And one direct buffer per attribute, filled in place each frame instead
    // of a fresh `ByteBuffer.allocateDirect` per attribute per frame - native
    // memory that is only ever reclaimed by the Cleaner, so it accumulates
    // faster than it is freed at frame rate.
    private val posFb = GL.directFloatBuffer(pos.size)
    private val nrmFb = GL.directFloatBuffer(nrm.size)
    private val curFb = GL.directFloatBuffer(cur.size)

    // Written from the UI thread via queueEvent, read only on the GL thread -
    // GLSurfaceView's own contract for crossing that boundary safely.
    private var frame: FaceFrame? = null
    private var hot = Color(0xFF39E0FF)
    private var cool = Color(0xFF0B6B8F)
    private var fit = 1f

    override fun setFrame(f: FaceFrame, hot: Color, cool: Color, fit: Float) {
        this.frame = f
        this.hot = hot
        this.cool = cool
        this.fit = fit
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        // The renderer INSTANCE outlives any one EGL context: GLSurfaceView
        // calls this again after a context loss, on the same object. Nothing
        // here ever deleted what it overwrote, which is harmless only while
        // `setPreserveEGLContextOnPause` stays at its default false (the lost
        // context takes the objects with it). Turn that on - or hit a driver
        // that preserves anyway - and every background/foreground cycle leaks
        // a program, a VAO and four buffers. Deleting first is correct either
        // way: after a real context loss the stale ids name nothing in the new
        // context, so the driver ignores them.
        deleteGlObjects()
        program = GL.compileProgram(VS, FS)
        aPosLoc = GLES30.glGetAttribLocation(program, "aPos")
        aNrmLoc = GLES30.glGetAttribLocation(program, "aNrm")
        aCurLoc = GLES30.glGetAttribLocation(program, "aCur")
        uResLoc = GLES30.glGetUniformLocation(program, "uRes")
        uYawLoc = GLES30.glGetUniformLocation(program, "uYaw")
        uPitLoc = GLES30.glGetUniformLocation(program, "uPit")
        uDistLoc = GLES30.glGetUniformLocation(program, "uDist")
        uScaleLoc = GLES30.glGetUniformLocation(program, "uScale")
        uPlateLoc = GLES30.glGetUniformLocation(program, "uPlate")
        uALoc = GLES30.glGetUniformLocation(program, "uA")

        val vaoArr = IntArray(1)
        GLES30.glGenVertexArrays(1, vaoArr, 0)
        vao = vaoArr[0]
        val bufs = IntArray(4)
        GLES30.glGenBuffers(4, bufs, 0)
        posBuf = bufs[0]
        nrmBuf = bufs[1]
        curBuf = bufs[2]
        idxBuf = bufs[3]

        // The seam row at u = TAU is a duplicated row of vertices rather
        // than a wrapped index, matching the reference's own comment on
        // why: one extra row is cheaper than a special case in the inner
        // loop.
        val vv = NV + 1
        val tris = ArrayList<Int>(NU * NV * 6)
        for (iu in 0 until NU) {
            for (iv in 0 until NV) {
                val a = iu * vv + iv
                val b = (iu + 1) * vv + iv
                val c = (iu + 1) * vv + iv + 1
                val d = iu * vv + iv + 1
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
        // and refilled with glBufferSubData each frame. Re-calling
        // glBufferData every frame orphans and re-allocates the whole store on
        // the driver side three times a frame for no gain.
        allocAttr(posBuf, pos.size * 4)
        allocAttr(nrmBuf, nrm.size * 4)
        allocAttr(curBuf, cur.size * 4)

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
        if (posBuf != 0 || nrmBuf != 0 || curBuf != 0 || idxBuf != 0) {
            GLES30.glDeleteBuffers(4, intArrayOf(posBuf, nrmBuf, curBuf, idxBuf), 0)
            posBuf = 0
            nrmBuf = 0
            curBuf = 0
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
        val st = stFor(f.motion)
        val inst = st.inst * if (f.motion == FaceState.LISTENING) 1f + f.amp else 1f
        val t = f.angle

        val vu = NU + 1
        val vv = NV + 1
        for (iu in 0 until vu) {
            val u = iu.toFloat() / NU * TAU
            val cu = cos(u)
            val su = sin(u)
            for (iv in 0 until vv) {
                val v = iv.toFloat() / NV * TAU
                val k = iu * vv + iv
                val o = k * 3
                val cv = cos(v)
                val sv = sin(v)
                val wob = 1f + inst * sin(u * 3f + t * 4f) * sin(v * 2f - t * 3f)
                val rr = OBJ_R0 * wob
                pos[o] = (OBJ_R + rr * cv) * cu
                pos[o + 1] = rr * sv
                pos[o + 2] = (OBJ_R + rr * cv) * su
                // The analytic normal of the UNPERTURBED torus, exactly as
                // the reference's own mesh() computes it - the instability
                // wobble moves the surface without being fed back into its
                // own lighting.
                nrm[o] = cv * cu
                nrm[o + 1] = sv
                nrm[o + 2] = cv * su
                cur[k] = sin(u * st.tight - v * 2f + t * st.flow * 2f)
                    .coerceAtLeast(0f).pow(6)
            }
        }

        GLES30.glBindVertexArray(vao)
        uploadAttr(posBuf, aPosLoc, pos, posFb, 3)
        uploadAttr(nrmBuf, aNrmLoc, nrm, nrmFb, 3)
        uploadAttr(curBuf, aCurLoc, cur, curFb, 1)
        GLES30.glBindBuffer(GLES30.GL_ELEMENT_ARRAY_BUFFER, idxBuf)

        GLES30.glClearColor(Spec.BACKGROUND.red, Spec.BACKGROUND.green, Spec.BACKGROUND.blue, 1f)
        GLES30.glClearDepthf(1f)
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
        GLES30.glDisable(GLES30.GL_BLEND)
        GLES30.glUseProgram(program)

        GLES30.glUniform2f(uResLoc, surfaceW.toFloat(), surfaceH.toFloat())
        val yaw = f.angle * 0.35f + f.yaw
        val pitch = -0.55f + f.pitch
        GLES30.glUniform1f(uYawLoc, yaw)
        GLES30.glUniform1f(uPitLoc, pitch)
        GLES30.glUniform1f(uDistLoc, DIST)
        // r (the on-screen radius every other face is handed) at scale = r *
        // DIST makes the torus - whose own object-space half-extent is ~1
        // unit at a camera distance of 4 - fill roughly that same radius.
        // Derived from the reference's own numbers (scale=S*1.05, dist=4),
        // not measured on a screen, since there is no device here to look at
        // one on.
        val r = min(surfaceW, surfaceH) / 2f * 0.5f * fit
        GLES30.glUniform1f(uScaleLoc, r * DIST)
        GLES30.glUniform3f(uPlateLoc, cool.red, cool.green, cool.blue)
        GLES30.glUniform3f(uALoc, hot.red, hot.green, hot.blue)

        GLES30.glDrawElements(GLES30.GL_TRIANGLES, indexCount, GLES30.GL_UNSIGNED_INT, 0)
        GLES30.glBindVertexArray(0)
    }

    private fun uploadAttr(buf: Int, loc: Int, data: FloatArray, fb: FloatBuffer, size: Int) {
        if (loc < 0) return
        // Refill the same native buffer and update the same GPU store. The
        // position is put back to 0 on both sides of the fill so this is safe
        // to call again next frame without reallocating anything.
        fb.position(0)
        fb.put(data)
        fb.position(0)
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, buf)
        GLES30.glBufferSubData(GLES30.GL_ARRAY_BUFFER, 0, data.size * 4, fb)
        GLES30.glEnableVertexAttribArray(loc)
        GLES30.glVertexAttribPointer(loc, size, GLES30.GL_FLOAT, false, 0, 0)
    }
}
