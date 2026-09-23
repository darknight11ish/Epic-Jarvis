package com.jarvis.client.face.gl

import android.opengl.GLES30
import android.opengl.GLSurfaceView
import android.util.Log
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
    /**
     * @param background the colour to clear to - FaceView's own `background`,
     *   which is the theme's well when the caller passes one. Handed over with
     *   every frame rather than set once, so a theme change reaches the GL
     *   thread through the same one crossing point as everything else.
     */
    fun setFrame(f: FaceFrame, hot: Color, cool: Color, fit: Float, background: Color)
}

/**
 * The desktop's own torus mesh, ported close to `TOKAMAK_VS`/`TOKAMAK_FS` and
 * the `mesh()` path of `tokamak` in the reactor kit
 * (`docs/reference/jarvis-reactor-kit.html`, the same code as the desktop's
 * `faces.html`). Rotation and the perspective divide happen in the vertex
 * shader exactly as the reference does it - the same `k = scale / (dist + z)`
 * division every other 3D face in this app already does on the CPU, just
 * moved onto the GPU because this one draws as a real mesh instead of lines
 * and circles.
 *
 * Brought up to the kit where the first port drew less than it:
 *  - Mesh density. The kit builds `detail(GPUPX, 48, 150, 168)` segments
 *    around the ring and `detail(GPUPX, 20, 56, 64)` around the tube, which
 *    in its solo view (see [GL.detail]) is 168 x 64 on any phone-sized face.
 *    This used a fixed 48 x 18, so the current bands were stepped across 18
 *    rings of the tube.
 *  - Spin. The kit turns the torus by its whole accumulated phase
 *    (`ry = PHASE`); this turned it by `0.35 * phase` - Nucleus's camera
 *    factor, carried over - so it spun at about a third of the kit's speed.
 *  - Pitch. The kit nods the torus by `sin(t * 0.17) * 0.1` around its -0.55
 *    tilt, on the raw clock. That nod was missing.
 *  - The current and the wobble run on the kit's raw clock `t` (`f.t` here),
 *    not on the spin phase - so the current used to flow at 0.3x the kit's
 *    speed at idle, the state it is most often looked at in.
 *  - The environment reflection (see [com.jarvis.client.face.EnvMap]) and
 *    4x multisampled edges (see [GL.MsaaConfigChooser]) - the first port
 *    took the no-texture fallback tone and single-sample edges.
 *
 * Two things are still dropped. `HUD.beat`, a global pulse nothing in this
 * app drives - the bass-hit "kick" term it fed is simply absent, not zeroed.
 * And the reference's own hardcoded per-state accent colour and its
 * separately defined "plate" colour: every canvas face in this app shades
 * with the `hot`/`cool` it is handed - the user's own chosen binding for the
 * current state - and this uses that same pair (`uA` = hot, `uPlate` = cool)
 * rather than a private palette that would make this the one face immune to
 * the colour picker. Geometry (flow/tightness/instability, which have no
 * user-facing control) keeps the reference's own per-state table.
 *
 * Size is the kit's: `scale = S * 1.05`, where S is the kit's canvas - the
 * face's box, scaled by `fit` - which is 4r for the radius r every face is
 * handed. Every canvas face in Faces.kt uses the same S = 4r. This used
 * `r * DIST` (4r), about 5% smaller than the kit.
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

        // The environment block goes in straight after `precision`, which
        // GLSL ES has to see before the first float declaration. Joined as
        // separate strings rather than trimIndent()ed as one: trimIndent
        // strips the smallest indent of ALL lines, and GL.ENV_GLSL has none.
        val FS = """
            #version 300 es
            precision highp float;
        """.trimIndent() + "\n" + GL.ENV_GLSL + """
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
                vec3 base = uPlate * (0.22 + lam * 1.05);
                base = mix(base, envSample(n), clamp(0.06 + rim * 0.4, 0.0, 1.0));
                // Rim: the containment field is brightest where the surface
                // turns away.
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
    private var uEnvLoc = -1

    private var vao = 0
    private var posBuf = 0
    private var nrmBuf = 0
    private var curBuf = 0
    private var idxBuf = 0
    private var envTex = 0
    private var indexCount = 0

    private var surfaceW = 1
    private var surfaceH = 1

    // The mesh, sized by GL.detail for the surface it is drawn on and rebuilt
    // only when that size (or the GL context) changes - see ensureMesh.
    //
    // These used to be `FloatArray(...)` locals inside `onDrawFrame` - heap
    // churn per frame at up to 120 fps, which is pure GC pressure on the one
    // code path in the app that must never stutter. They stay fields,
    // allocated once per mesh size; they are just no longer a fixed 48 x 18.
    private var nu = 0
    private var nv = 0
    /** The GPU side (index list, normals, attribute stores) needs building. */
    private var gpuMeshStale = true
    private var pos = FloatArray(0)
    private var nrm = FloatArray(0)
    private var cur = FloatArray(0)
    private var posFb = GL.directFloatBuffer(0)
    private var curFb = GL.directFloatBuffer(0)
    /** [pos] holds the unwobbled torus, and it is already on the GPU. */
    private var restingUploaded = false

    // Per-ring and per-tube-station trig, so the inner loop has none. The
    // torus is separable in u and v; the wobble is a product of a u term and
    // a v term, and the current's sine of a difference expands into the same
    // shape. At 168 x 64 that turns ~55,000 sin/cos a frame into ~470.
    private var cu = FloatArray(0)
    private var su = FloatArray(0)
    private var cvT = FloatArray(0)
    private var svT = FloatArray(0)
    private var wobU = FloatArray(0)
    private var wobV = FloatArray(0)
    private var curSU = FloatArray(0)
    private var curCU = FloatArray(0)
    private var curSV = FloatArray(0)
    private var curCV = FloatArray(0)

    // Written from the UI thread via queueEvent, read only on the GL thread -
    // GLSurfaceView's own contract for crossing that boundary safely.
    private var frame: FaceFrame? = null
    private var hot = Color(0xFF39E0FF)
    private var cool = Color(0xFF0B6B8F)
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
        // The renderer INSTANCE outlives any one EGL context: GLSurfaceView
        // calls this again after a context loss, on the same object. Nothing
        // here ever deleted what it overwrote, which is harmless only while
        // `setPreserveEGLContextOnPause` stays at its default false (the lost
        // context takes the objects with it). Turn that on - or hit a driver
        // that preserves anyway - and every background/foreground cycle leaks
        // a program, a VAO, four buffers and a texture. Deleting first is
        // correct either way: after a real context loss the stale ids name
        // nothing in the new context, so the driver ignores them.
        deleteGlObjects()
        // Caught, not allowed to propagate. `GL.compileProgram` ends in
        // `error(...)`, and this runs on GLSurfaceView's own GLThread where
        // nothing catches it - so a driver that rejects any construct in this
        // GLES 3.00 source took the whole process down. The chosen face is
        // PERSISTED, so relaunching restored the same face and died again:
        // an unrecoverable loop with no way out but clearing app data. A face
        // that will not compile should cost that face, not the app.
        program = runCatching { GL.compileProgram(VS, FS) }
            .onFailure {
                Log.w("JarvisFaceGL", "Tokamak shader would not build; face disabled", it)
                GL.lastBuildFailure = "tokamak: ${it.message}"
            }
            .getOrDefault(0)
        if (program == 0) return
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
        uEnvLoc = GLES30.glGetUniformLocation(program, "uEnv")

        val vaoArr = IntArray(1)
        GLES30.glGenVertexArrays(1, vaoArr, 0)
        vao = vaoArr[0]
        val bufs = IntArray(4)
        GLES30.glGenBuffers(4, bufs, 0)
        posBuf = bufs[0]
        nrmBuf = bufs[1]
        curBuf = bufs[2]
        idxBuf = bufs[3]
        envTex = GL.envTexture()

        // Everything sized by the mesh is (re)built on the first frame that
        // knows the surface size - see ensureMesh.
        gpuMeshStale = true

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
        if (envTex != 0) {
            GLES30.glDeleteTextures(1, intArrayOf(envTex), 0)
            envTex = 0
        }
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        surfaceW = max(1, width)
        surfaceH = max(1, height)
        GLES30.glViewport(0, 0, surfaceW, surfaceH)
    }

    /**
     * Sizes the mesh to the kit's `detail()` for this surface and builds
     * what depends on that size: the CPU arrays, the per-ring trig, the
     * normals (a torus's normal is fixed per vertex, so it is uploaded once
     * here rather than every frame) and the index list. A no-op on every
     * frame where neither the size nor the GL context changed. The size is
     * quantised by detail() to whole segments, so dragging the face's pane
     * larger rebuilds a few times, not on every pixel.
     */
    private fun ensureMesh() {
        val px = GL.meshPx(surfaceW, surfaceH)
        val wantU = GL.detail(px, 48, 150, 168)
        val wantV = GL.detail(px, 20, 56, 64)
        val resized = wantU != nu || wantV != nv
        if (!resized && !gpuMeshStale) return
        if (resized) {
            nu = wantU
            nv = wantV
            val count = (nu + 1) * (nv + 1)
            pos = FloatArray(count * 3)
            nrm = FloatArray(count * 3)
            cur = FloatArray(count)
            posFb = GL.directFloatBuffer(pos.size)
            curFb = GL.directFloatBuffer(cur.size)
            cu = FloatArray(nu + 1)
            su = FloatArray(nu + 1)
            wobU = FloatArray(nu + 1)
            curSU = FloatArray(nu + 1)
            curCU = FloatArray(nu + 1)
            cvT = FloatArray(nv + 1)
            svT = FloatArray(nv + 1)
            wobV = FloatArray(nv + 1)
            curSV = FloatArray(nv + 1)
            curCV = FloatArray(nv + 1)
            for (iu in 0..nu) {
                val u = iu.toFloat() / nu * TAU
                cu[iu] = cos(u)
                su[iu] = sin(u)
            }
            for (iv in 0..nv) {
                val v = iv.toFloat() / nv * TAU
                cvT[iv] = cos(v)
                svT[iv] = sin(v)
            }
            val vv = nv + 1
            for (iu in 0..nu) {
                for (iv in 0..nv) {
                    val o = (iu * vv + iv) * 3
                    // The analytic normal of the UNPERTURBED torus, exactly
                    // as the reference's own mesh() computes it - the
                    // instability wobble moves the surface without being fed
                    // back into its own lighting.
                    nrm[o] = cvT[iv] * cu[iu]
                    nrm[o + 1] = svT[iv]
                    nrm[o + 2] = cvT[iv] * su[iu]
                }
            }
        }

        // The seam row at u = TAU is a duplicated row of vertices rather
        // than a wrapped index, matching the reference's own comment on
        // why: one extra row is cheaper than a special case in the inner
        // loop.
        val vv = nv + 1
        val tris = IntArray(nu * nv * 6)
        var t = 0
        for (iu in 0 until nu) {
            for (iv in 0 until nv) {
                val a = iu * vv + iv
                val b = (iu + 1) * vv + iv
                val c = (iu + 1) * vv + iv + 1
                val d = iu * vv + iv + 1
                tris[t++] = a; tris[t++] = b; tris[t++] = c
                tris[t++] = a; tris[t++] = c; tris[t++] = d
            }
        }
        indexCount = tris.size
        GLES30.glBindVertexArray(vao)
        GLES30.glBindBuffer(GLES30.GL_ELEMENT_ARRAY_BUFFER, idxBuf)
        GLES30.glBufferData(
            GLES30.GL_ELEMENT_ARRAY_BUFFER,
            indexCount * 4,
            GL.intBuffer(tris),
            GLES30.GL_STATIC_DRAW,
        )
        // Normals are fixed for a given mesh: STATIC, uploaded once, and the
        // attribute pointer recorded in the VAO here rather than per frame.
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, nrmBuf)
        GLES30.glBufferData(
            GLES30.GL_ARRAY_BUFFER,
            nrm.size * 4,
            GL.floatBuffer(nrm),
            GLES30.GL_STATIC_DRAW,
        )
        if (aNrmLoc >= 0) {
            GLES30.glEnableVertexAttribArray(aNrmLoc)
            GLES30.glVertexAttribPointer(aNrmLoc, 3, GLES30.GL_FLOAT, false, 0, 0)
        }
        GLES30.glBindVertexArray(0)

        // Positions and current are DYNAMIC but FIXED SIZE for this mesh, so
        // their GPU storage is allocated here (`null` data = uninitialised
        // store) and refilled with glBufferSubData. Re-calling glBufferData
        // every frame orphans and re-allocates the whole store on the driver
        // side for no gain.
        allocAttr(posBuf, pos.size * 4)
        allocAttr(curBuf, cur.size * 4)
        restingUploaded = false
        gpuMeshStale = false
    }

    private fun allocAttr(buf: Int, bytes: Int) {
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER, buf)
        GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER, bytes, null, GLES30.GL_DYNAMIC_DRAW)
    }

    override fun onDrawFrame(gl: GL10?) {
        // The shader did not build on this device (see onSurfaceCreated).
        // Clearing to the ground leaves a dark, still surface rather than
        // whatever the uninitialised framebuffer holds.
        if (program == 0) {
            GLES30.glClearColor(background.red, background.green, background.blue, 1f)
            GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
            return
        }
        val f = frame ?: return
        ensureMesh()
        val st = stFor(f.motion)
        val inst = st.inst * if (f.motion == FaceState.LISTENING) 1f + f.amp else 1f
        // The kit's raw clock, for the current and the wobble. The spin
        // phase (f.angle) is for the rotation below and nothing else.
        val t = f.t

        // This frame's per-ring and per-station terms:
        //   wob = 1 + inst * sin(3u + 4t) * sin(2v - 3t)
        //   cur = max(0, sin(tight*u + 2*flow*t - 2v))^6, the sine of that
        //         difference expanded as sin(A)cos(B) - cos(A)sin(B).
        val flowT = t * st.flow * 2f
        for (iu in 0..nu) {
            val u = iu.toFloat() / nu * TAU
            wobU[iu] = sin(u * 3f + t * 4f)
            val a = u * st.tight + flowT
            curSU[iu] = sin(a)
            curCU[iu] = cos(a)
        }
        for (iv in 0..nv) {
            val v = iv.toFloat() / nv * TAU
            wobV[iv] = sin(v * 2f - t * 3f)
            curSV[iv] = sin(v * 2f)
            curCV[iv] = cos(v * 2f)
        }

        val vv = nv + 1
        // With no instability (idle) the torus itself does not move between
        // frames - only its current does - so the positions go up once and
        // stay until a state with a wobble arrives.
        val wobbling = inst != 0f
        val uploadPos = wobbling || !restingUploaded
        for (iu in 0..nu) {
            for (iv in 0..nv) {
                val k = iu * vv + iv
                if (uploadPos) {
                    val o = k * 3
                    val rr = OBJ_R0 * (1f + inst * wobU[iu] * wobV[iv])
                    val ring = OBJ_R + rr * cvT[iv]
                    pos[o] = ring * cu[iu]
                    pos[o + 1] = rr * svT[iv]
                    pos[o + 2] = ring * su[iu]
                }
                val c = (curSU[iu] * curCV[iv] - curCU[iu] * curSV[iv]).coerceAtLeast(0f)
                val c2 = c * c
                cur[k] = c2 * c2 * c2
            }
        }

        GLES30.glBindVertexArray(vao)
        if (uploadPos) uploadAttr(posBuf, aPosLoc, pos, posFb, 3)
        restingUploaded = !wobbling
        uploadAttr(curBuf, aCurLoc, cur, curFb, 1)
        GLES30.glBindBuffer(GLES30.GL_ELEMENT_ARRAY_BUFFER, idxBuf)

        // The caller's ground (the theme's well), not a fixed Spec.BACKGROUND,
        // so this face sits in the same black as the pane around it.
        GLES30.glClearColor(background.red, background.green, background.blue, 1f)
        GLES30.glClearDepthf(1f)
        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT or GLES30.GL_DEPTH_BUFFER_BIT)
        GLES30.glDisable(GLES30.GL_BLEND)
        GLES30.glUseProgram(program)
        GL.bindEnv(envTex, uEnvLoc)

        GLES30.glUniform2f(uResLoc, surfaceW.toFloat(), surfaceH.toFloat())
        // The kit's `ry = PHASE` - the whole phase, not a fraction of it -
        // and `rx = -.55 + sin(t * .17) * .1` on the raw clock. The drag adds
        // on top, as it does for every 3D face here.
        val yaw = f.angle + f.yaw
        val pitch = -0.55f + sin(f.t * 0.17f) * 0.1f + f.pitch
        GLES30.glUniform1f(uYawLoc, yaw)
        GLES30.glUniform1f(uPitLoc, pitch)
        GLES30.glUniform1f(uDistLoc, DIST)
        // The kit's `scale = S * 1.05`, with S = 4r - see the class comment.
        // `uScale` is in the surface's own pixels, as the kit's is in its
        // backing store's (`scale * rw / w`).
        val r = min(surfaceW, surfaceH) / 2f * 0.5f * fit
        GLES30.glUniform1f(uScaleLoc, 4f * r * 1.05f)
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
