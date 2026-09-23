package com.jarvis.client.face.gl

import android.opengl.EGLExt
import android.opengl.GLES30
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.IntBuffer
import javax.microedition.khronos.egl.EGL10
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.egl.EGLDisplay

/**
 * The handful of raw GLES 3.0 calls every mesh face needs.
 *
 * GLES does not throw on a bad shader - a failed `glCompileShader` or
 * `glLinkProgram` just leaves the object unusable and everything after it
 * silently draws nothing, which on a device this can't be watched running
 * would look identical to "it never got called". `compileProgram` asks the
 * driver directly (`glGetShaderiv`/`glGetProgramiv` with the log) and turns
 * a bad shader into a real Kotlin exception instead.
 *
 * That exception is CAUGHT by each renderer's `onSurfaceCreated` and recorded
 * in [lastBuildFailure], rather than being allowed off the GLThread. It used
 * to propagate, and the comment here used to say it did so "so
 * `FaceRenderTest` has something to catch" - which was never true: the test
 * catches nothing, it reads `CrashLog` back from disk after the process has
 * already died. Since the selected face is persisted, that death repeated on
 * every launch, so a shader one driver disliked bricked the app until its
 * data was cleared. [lastBuildFailure] is what the test asserts on now.
 *
 * Not a renderer and not an abstraction over draw calls - each face's own
 * `GLSurfaceView.Renderer` still owns its own buffer ids, uniform locations
 * and draw order. This is only the pieces that would otherwise be
 * copied verbatim into both of this app's mesh faces.
 */
object GL {

    /**
     * Set by a renderer whose shader would not build, and never cleared by
     * one that succeeds - so a failure cannot be papered over by whichever
     * face happens to be drawn next.
     *
     * This exists because the failure is otherwise invisible: the renderer
     * degrades to a dark surface on purpose, which on a device nobody is
     * watching looks the same as a face that is simply dark. Cleared by
     * `FaceRenderTest` before each face and asserted null after.
     */
    @Volatile
    var lastBuildFailure: String? = null

    fun compileProgram(vertexSrc: String, fragmentSrc: String): Int {
        val vs = compileShader(GLES30.GL_VERTEX_SHADER, vertexSrc)
        val fs = compileShader(GLES30.GL_FRAGMENT_SHADER, fragmentSrc)
        val program = GLES30.glCreateProgram()
        GLES30.glAttachShader(program, vs)
        GLES30.glAttachShader(program, fs)
        GLES30.glLinkProgram(program)
        val status = IntArray(1)
        GLES30.glGetProgramiv(program, GLES30.GL_LINK_STATUS, status, 0)
        // The shaders are compiled into the program either way; only their
        // standalone objects have no further use once linking is done.
        GLES30.glDeleteShader(vs)
        GLES30.glDeleteShader(fs)
        if (status[0] == 0) {
            val log = GLES30.glGetProgramInfoLog(program)
            GLES30.glDeleteProgram(program)
            error("shader program failed to link: $log")
        }
        return program
    }

    private fun compileShader(type: Int, src: String): Int {
        val shader = GLES30.glCreateShader(type)
        GLES30.glShaderSource(shader, src)
        GLES30.glCompileShader(shader)
        val status = IntArray(1)
        GLES30.glGetShaderiv(shader, GLES30.GL_COMPILE_STATUS, status, 0)
        if (status[0] == 0) {
            val log = GLES30.glGetShaderInfoLog(shader)
            val kind = if (type == GLES30.GL_VERTEX_SHADER) "vertex" else "fragment"
            GLES30.glDeleteShader(shader)
            error("$kind shader failed to compile: $log")
        }
        return shader
    }

    /**
     * An EMPTY direct buffer of a fixed float capacity, kept by a renderer for
     * the life of its surface and re-filled each frame.
     *
     * [floatBuffer] allocates fresh native memory on every call, and the mesh
     * faces called it once per attribute per frame - three `allocateDirect`s a
     * frame each, ~51 KB/frame in Membrane, so roughly 3 MB/s of native memory
     * that only the Cleaner ever gives back. The sizes involved are fixed and
     * known at surface-creation time, so there is no reason to allocate more
     * than one of each, ever.
     */
    fun directFloatBuffer(floats: Int): FloatBuffer =
        ByteBuffer.allocateDirect(floats * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()

    /**
     * A direct, native-order buffer - what `glBufferData`/`glBufferSubData`
     * require. One-time setup use only (index data and the like); anything
     * uploaded every frame wants [directFloatBuffer] instead.
     */
    fun floatBuffer(data: FloatArray): FloatBuffer =
        ByteBuffer.allocateDirect(data.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .apply { put(data); position(0) }

    fun intBuffer(data: IntArray): IntBuffer =
        ByteBuffer.allocateDirect(data.size * 4)
            .order(ByteOrder.nativeOrder())
            .asIntBuffer()
            .apply { put(data); position(0) }

    /**
     * The reactor kit's `detail(w, lo, hi, cap)`: how fine a mesh to build
     * for a face drawn [px] pixels across. A straight ramp from `lo` at 200 px
     * to `hi` at 820 px, times the kit's detail multiplier, capped at `cap`.
     *
     * The multiplier is [SOLO_DETAIL], the kit's solo view: "the grid is a
     * picker; the actual product shows ONE face. Solo is what Jarvis will
     * really look like", and solo runs every face at a detail of at least
     * 1.9. At High (the default, 1.9) any phone-sized face saturates at the
     * cap - 168 x 64 for the torus, 168 cells across for the drum. Medium and
     * Low build a coarser mesh, which is the point of them.
     *
     * Both mesh faces used to use a fixed grid "until it can be measured on
     * real hardware" - 48 x 18 for the torus and 40 x 40 for the drum, a
     * quarter and a fifth of the kit's. The kit runs its numbers, in
     * JavaScript, on the phones it was surveyed on. At 40 cells the drum's
     * ripples were each only a few cells wide and the torus's current bands
     * were stepped across 18 rings, which is the faceting the kit's own GPU
     * notes say the mesh path exists to remove.
     *
     * [px] is the kit's `GPUPX`: device pixels times the quality tier's `gpu`
     * scale, which is what [meshPx] computes.
     */
    fun detail(px: Float, lo: Int, hi: Int, cap: Int): Int {
        val k = ((px - 200f) / 620f).coerceIn(0f, 1f)
        val n = (lo + (hi - lo) * k) * SOLO_DETAIL
        return maxOf(lo, kotlin.math.round(minOf(cap.toFloat(), n)).toInt())
    }

    /**
     * The kit's solo-view detail multiplier: `Math.max(1.9, Q.detail)` - 1.9
     * at the default High. Read from [com.jarvis.client.face.FaceQuality] on
     * this GL thread (it is @Volatile there), so the face editor's Quality
     * and Auto adjust reach the mesh: ensureMesh/ensureGrid rebuild when the
     * answer changes.
     */
    val SOLO_DETAIL: Float get() = com.jarvis.client.face.FaceQuality.detail

    /**
     * The kit's `GPUPX` for a surface: its short side in device pixels times
     * the quality tier's `gpu` share (0.62 Low, 0.8 Medium, 1.0 High and Max).
     * This used to be a fixed 0.8, the kit's Medium; at phone sizes the
     * detail cap is reached either way at High, so Home's default mesh is
     * the same size it was (a small preview gets a slightly finer one).
     */
    fun meshPx(surfaceW: Int, surfaceH: Int): Float =
        minOf(surfaceW, surfaceH) * com.jarvis.client.face.FaceQuality.gpu

    /**
     * The reflection panorama ([com.jarvis.client.face.EnvMap]) as a GL
     * texture on the current context, set up the way the kit sets its own:
     * REPEAT across so the seam at the back of the panorama never shows,
     * CLAMP down so the poles do not wrap into each other, bilinear both
     * ways. Called from `onSurfaceCreated`, so a lost context gets a fresh
     * one; the caller deletes the old id first, like every other object.
     */
    fun envTexture(): Int {
        val ids = IntArray(1)
        GLES30.glGenTextures(1, ids, 0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, ids[0])
        android.opengl.GLUtils.texImage2D(
            GLES30.GL_TEXTURE_2D, 0, com.jarvis.client.face.EnvMap.bitmap, 0,
        )
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_REPEAT)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, 0)
        return ids[0]
    }

    /** Binds [texture] to unit 0 and points the program's `uEnv` sampler at it. */
    fun bindEnv(texture: Int, uEnvLoc: Int) {
        if (uEnvLoc < 0 || texture == 0) return
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D, texture)
        GLES30.glUniform1i(uEnvLoc, 0)
    }

    /**
     * The kit's `envSample` (its `GLSL_COMMON`), verbatim apart from the
     * `uHasEnv` switch: [envTexture] is always bound - to a 1x1 texture of
     * the kit's fallback tone if the panorama ever failed to decode - so the
     * switch would only ever read 1. Pasted into both mesh faces' fragment
     * shaders after their `precision` line.
     */
    const val ENV_GLSL = """
uniform sampler2D uEnv;
const float ENV_TAU = 6.283185307179586;
// Reflect the fixed view ray (0,0,-1) about the view-space normal and look
// the reflection up in the equirectangular panorama. Four taps a texel apart:
// the panorama is 128 x 64 and is magnified many times across a smooth
// surface, where plain bilinear shows as diamond facets.
vec3 envSample(vec3 n) {
    float d = -n.z;
    vec3 r = normalize(vec3(-2.0 * d * n.x, -2.0 * d * n.y, -1.0 - 2.0 * d * n.z));
    float u = 0.5 + atan(r.x, -r.z) / ENV_TAU;
    float v = 0.5 - asin(clamp(r.y, -1.0, 1.0)) / 3.14159265;
    vec2 uv = vec2(u, v);
    vec2 e = 0.75 / vec2(textureSize(uEnv, 0));
    return 0.25 * (texture(uEnv, uv + vec2( e.x,  e.y)).rgb
                 + texture(uEnv, uv + vec2(-e.x,  e.y)).rgb
                 + texture(uEnv, uv + vec2( e.x, -e.y)).rgb
                 + texture(uEnv, uv + vec2(-e.x, -e.y)).rgb);
}
"""

    /**
     * An EGL config with 4x multisampling, falling back to none.
     *
     * The kit asks its WebGL context for `antialias: true`, which is
     * hardware multisampling on every triangle edge - the torus's silhouette
     * and the drum's rim are smooth there. `setEGLConfigChooser(8, 8, 8, 8,
     * 16, 0)`, which both mesh faces used to get, has no sample buffers at
     * all, so their silhouettes were drawn as single-sample staircases: the
     * sharpest-looking thing on screen, and the most jagged.
     *
     * Same RGBA8888 + 16-bit depth + no stencil as before, same "exactly 8
     * bits a channel" choice `GLSurfaceView`'s own chooser makes. If the
     * device offers no multisampled config at all (some emulators), the
     * second pass asks for exactly what the old chooser did, so the worst
     * case is the old picture, never a missing one.
     */
    class MsaaConfigChooser : android.opengl.GLSurfaceView.EGLConfigChooser {
        override fun chooseConfig(egl: EGL10, display: EGLDisplay): EGLConfig =
            pick(egl, display, samples = 4)
                ?: pick(egl, display, samples = 0)
                ?: throw IllegalArgumentException("No RGBA8888 + depth16 GLES 3 config on this device")

        private fun pick(egl: EGL10, display: EGLDisplay, samples: Int): EGLConfig? {
            val spec = intArrayOf(
                EGL10.EGL_RED_SIZE, 8,
                EGL10.EGL_GREEN_SIZE, 8,
                EGL10.EGL_BLUE_SIZE, 8,
                EGL10.EGL_ALPHA_SIZE, 8,
                EGL10.EGL_DEPTH_SIZE, 16,
                EGL10.EGL_STENCIL_SIZE, 0,
                // What setEGLContextClientVersion(3) adds to the default
                // chooser's spec; a custom chooser has to ask for it itself.
                EGL10.EGL_RENDERABLE_TYPE, EGLExt.EGL_OPENGL_ES3_BIT_KHR,
                EGL10.EGL_SAMPLE_BUFFERS, if (samples > 0) 1 else 0,
                EGL10.EGL_SAMPLES, samples,
                EGL10.EGL_NONE,
            )
            val count = IntArray(1)
            if (!egl.eglChooseConfig(display, spec, null, 0, count) || count[0] <= 0) return null
            val configs = arrayOfNulls<EGLConfig>(count[0])
            if (!egl.eglChooseConfig(display, spec, configs, count[0], count)) return null
            val value = IntArray(1)
            fun get(c: EGLConfig, attr: Int): Int =
                if (egl.eglGetConfigAttrib(display, c, attr, value)) value[0] else 0
            // eglChooseConfig returns "at least" matches; keep the first that
            // is exactly 8 bits a channel, as GLSurfaceView's own chooser does.
            return configs.firstOrNull { c ->
                c != null &&
                    get(c, EGL10.EGL_RED_SIZE) == 8 && get(c, EGL10.EGL_GREEN_SIZE) == 8 &&
                    get(c, EGL10.EGL_BLUE_SIZE) == 8 && get(c, EGL10.EGL_ALPHA_SIZE) == 8 &&
                    get(c, EGL10.EGL_DEPTH_SIZE) >= 16
            }
        }
    }
}
