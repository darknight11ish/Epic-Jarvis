package com.jarvis.client.face.gl

import android.opengl.GLES30
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.nio.IntBuffer

/**
 * The handful of raw GLES 3.0 calls every mesh face needs.
 *
 * GLES does not throw on a bad shader - a failed `glCompileShader` or
 * `glLinkProgram` just leaves the object unusable and everything after it
 * silently draws nothing, which on a device this can't be watched running
 * would look identical to "it never got called". `compileProgram` asks the
 * driver directly (`glGetShaderiv`/`glGetProgramiv` with the log) and turns
 * a bad shader into a real Kotlin exception instead, so `FaceRenderTest`
 * has something to catch.
 *
 * Not a renderer and not an abstraction over draw calls - each face's own
 * `GLSurfaceView.Renderer` still owns its own buffer ids, uniform locations
 * and draw order. This is only the two pieces that would otherwise be
 * copied verbatim into both of this app's mesh faces.
 */
object GL {
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

    /** A direct, native-order buffer - what `glBufferData`/`glBufferSubData` require. */
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
}
