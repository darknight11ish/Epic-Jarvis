package com.jarvis.client.platform

import android.opengl.EGL14
import android.opengl.EGLConfig
import android.opengl.EGLContext
import android.opengl.EGLSurface
import android.opengl.GLES20
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.jarvis.client.face.FaceBudget
import com.jarvis.client.face.FaceQuality
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Asks the graphics driver, once per process, what it is - so a phone (in
 * practice, an emulator) that draws graphics in software starts the face at
 * Low before its first frame, instead of waiting for the frame-time governor
 * to notice.
 *
 * Why before the first frame: the phone CI's emulator (software graphics,
 * SwiftShader) crashed or froze within six to twelve seconds of the first
 * detailed face drawing, in four runs in a row - faster than a governor that
 * has to watch a few seconds of frames can step down.
 *
 * How: a throwaway 1x1 off-screen EGL context on a background thread, one
 * `glGetString(GL_RENDERER)`, then everything torn down again. It runs once,
 * never per frame, and never on the main thread. Anything that goes wrong -
 * no display, no config, a driver that throws - reads as "not software": a
 * normal GPU is assumed and the governor does its job. The name matching is
 * [FaceBudget.isSoftwareRenderer], pure and unit-tested.
 *
 * Started from [com.jarvis.client.JarvisApp] as the process starts, so the
 * answer is normally in long before the first face composes; FaceView waits
 * a short while for it all the same (see [await]).
 */
object GpuProbe {

    private val result = CompletableDeferred<Boolean>()
    private var started = false

    /** What the driver called itself, or null if it was never asked or would not say. Logged, never sent. */
    @Volatile
    var renderer: String? = null
        private set

    /** Starts the check on a background thread. Safe to call more than once; only the first does anything. */
    fun start() {
        synchronized(this) {
            if (started) return
            started = true
        }
        Thread({
            var software = false
            try {
                val name = runCatching { queryRenderer() }
                    .onFailure { Log.w(TAG, "GPU check failed; assuming a hardware GPU", it) }
                    .getOrNull()
                renderer = name
                software = FaceBudget.isSoftwareRenderer(name)
                Log.i(TAG, "GL_RENDERER=${name ?: "(unknown)"} software=$software")
            } finally {
                // Whatever happened above, the answer arrives, so nothing waits
                // on it for ever. A no-op if it somehow completed already.
                result.complete(software)
                // Applied on the main thread, where FaceQuality is written.
                // FaceView also applies it after [await]; the second is ignored.
                val answer = software
                runCatching { Handler(Looper.getMainLooper()).post { FaceQuality.onGpuProbed(answer) } }
            }
        }, "jarvis-gpu-probe").apply { isDaemon = true }.start()
    }

    /**
     * The answer, waiting at most [timeoutMs] for it. Null if it has not come
     * in by then - the caller carries on as if the GPU were normal, and the
     * answer is applied when it does arrive.
     */
    suspend fun await(timeoutMs: Long): Boolean? {
        start()
        // await() on an already-completed answer returns at once, without suspending.
        return withTimeoutOrNull(timeoutMs) { result.await() }
    }

    private fun queryRenderer(): String? {
        val display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
        if (display == null || display == EGL14.EGL_NO_DISPLAY) return null
        val version = IntArray(2)
        if (!EGL14.eglInitialize(display, version, 0, version, 1)) return null
        var context: EGLContext = EGL14.EGL_NO_CONTEXT
        var surface: EGLSurface = EGL14.EGL_NO_SURFACE
        try {
            val attribs = intArrayOf(
                EGL14.EGL_RENDERABLE_TYPE, EGL14.EGL_OPENGL_ES2_BIT,
                EGL14.EGL_SURFACE_TYPE, EGL14.EGL_PBUFFER_BIT,
                EGL14.EGL_RED_SIZE, 8,
                EGL14.EGL_GREEN_SIZE, 8,
                EGL14.EGL_BLUE_SIZE, 8,
                EGL14.EGL_NONE,
            )
            val configs = arrayOfNulls<EGLConfig>(1)
            val count = IntArray(1)
            if (!EGL14.eglChooseConfig(display, attribs, 0, configs, 0, 1, count, 0) || count[0] <= 0) {
                return null
            }
            val config = configs[0] ?: return null
            context = EGL14.eglCreateContext(
                display, config, EGL14.EGL_NO_CONTEXT,
                intArrayOf(EGL14.EGL_CONTEXT_CLIENT_VERSION, 2, EGL14.EGL_NONE), 0,
            ) ?: EGL14.EGL_NO_CONTEXT
            if (context == EGL14.EGL_NO_CONTEXT) return null
            surface = EGL14.eglCreatePbufferSurface(
                display, config, intArrayOf(EGL14.EGL_WIDTH, 1, EGL14.EGL_HEIGHT, 1, EGL14.EGL_NONE), 0,
            ) ?: EGL14.EGL_NO_SURFACE
            if (surface == EGL14.EGL_NO_SURFACE) return null
            if (!EGL14.eglMakeCurrent(display, surface, surface, context)) return null
            return GLES20.glGetString(GLES20.GL_RENDERER)
        } finally {
            EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT)
            if (surface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, surface)
            if (context != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(display, context)
            EGL14.eglReleaseThread()
            // Not eglTerminate: the default display is shared by the whole
            // process - the app's own drawing and the GL faces use it too - and
            // terminating it here could pull it out from under them.
        }
    }

    private const val TAG = "JarvisGpuProbe"
}
