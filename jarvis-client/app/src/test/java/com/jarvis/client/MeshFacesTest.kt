package com.jarvis.client

import com.jarvis.client.face.Faces
import com.jarvis.client.face.gl.MeshFaces
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * `MeshFaces.isMesh` and `MeshFaces.rendererFor` must name the same faces.
 *
 * FaceThumbnail asks `isMesh` so it does not build a renderer just to find
 * out, and draws a stand-in for those faces. A face that `rendererFor` knows
 * and `isMesh` does not would have its `draw` called - which for a mesh face
 * throws, and would take the Appearance screen down with it.
 */
class MeshFacesTest {

    @Test
    fun `isMesh agrees with rendererFor for every offered face`() {
        for (face in Faces.all) {
            assertEquals(
                "MeshFaces.isMesh and rendererFor disagree about '${face.id}'",
                MeshFaces.rendererFor(face.id) != null,
                MeshFaces.isMesh(face.id),
            )
        }
    }
}
