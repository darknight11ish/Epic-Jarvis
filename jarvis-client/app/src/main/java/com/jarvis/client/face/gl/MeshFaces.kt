package com.jarvis.client.face.gl

/**
 * The faces (of `Faces.all`) that render through a real GLES 3.0 mesh
 * (`GLSurfaceView`) instead of `Face.draw`'s `DrawScope` calls.
 *
 * Kept separate from the `Face` interface itself rather than bolted on as
 * an optional method: every other face in this app shares one draw
 * contract, and a mesh face's real interface - upload buffers, run its own
 * GL thread, manage its own EGL-backed lifecycle - has nothing in common
 * with it. `Face.draw` is never called for an id this returns non-null for;
 * `FaceView` checks this once per composition and swaps the whole rendering
 * path.
 *
 * A factory, not a shared instance: a `GLSurfaceView.Renderer` owns live GL
 * object ids tied to one specific EGL context, so it has to be created fresh
 * for whichever `GLSurfaceView` a given `FaceView` composition actually
 * creates - unlike every stateless `Face` singleton in `Faces.kt`, which is
 * safe to share because it holds nothing but a compiled, reusable program.
 */
object MeshFaces {
    fun rendererFor(id: String): MeshRenderer? = when (id) {
        "tokamak" -> TokamakRenderer()
        else -> null
    }
}
