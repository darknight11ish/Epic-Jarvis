package com.jarvis.client

import com.jarvis.client.face.CritterPose
import com.jarvis.client.face.CritterShaders
import com.jarvis.client.face.Faces
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.float
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

/**
 * The red panda moves the same way on the phone as on the desktop.
 *
 * The two apps cannot share code, so each has its own copy of the pose
 * maths: `critter-pose.js` on the desktop and [CritterPose] here.
 * `tools/gen_critters.py` runs the JavaScript at fixed moments - every state,
 * mid-blink, mid-transition, with sound and a pointer - and saves the answers
 * in `critter-pose-golden.json`. This checks the Kotlin copy gives the same
 * answers. If it fails after a change to one copy, make the same change to
 * the other and re-run the generator.
 */
class CritterPoseTest {

    private val cases: JsonArray by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("critter-pose-golden.json")) {
            "critter-pose-golden.json is missing from test resources - run tools/gen_critters.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonArray
    }

    private fun state(id: String) = FaceState.valueOf(id.uppercase())

    @Test
    fun `every pose matches the desktop's`() {
        assertTrue("the fixture should cover every state", cases.size >= 8 * 5)
        for (c in cases) {
            val o = c.jsonObject
            val look = o["look"]!!.jsonObject
            val pose = CritterPose.pose(
                state = state(o["state"]!!.jsonPrimitive.content),
                prevState = state(o["prev"]!!.jsonPrimitive.content),
                since = o["since"]!!.jsonPrimitive.float,
                t = o["t"]!!.jsonPrimitive.float,
                amp = o["amp"]!!.jsonPrimitive.float,
                look = CritterPose.Look(
                    x = look["x"]?.jsonPrimitive?.float ?: 0f,
                    y = look["y"]?.jsonPrimitive?.float ?: 0f,
                    w = look["w"]?.jsonPrimitive?.float ?: 0f,
                ),
            )
            val got = CritterPose.uniforms(pose)
            val want = o["uniforms"]!!.jsonObject
            assertEquals("uniform names differ from the desktop's", want.keys, got.keys)
            val where = "${o["state"]} from ${o["prev"]} at t=${o["t"]}"
            for ((name, arr) in want) {
                val w = arr.jsonArray.map { it.jsonPrimitive.float }
                val g = got.getValue(name)
                assertEquals("$name has a different length ($where)", w.size, g.size)
                for (i in w.indices) {
                    // 32-bit floats here against 64-bit doubles there: a
                    // thousandth is far below anything visible and far above
                    // rounding.
                    assertTrue(
                        "$name[$i] is ${g[i]} on the phone and ${w[i]} on the desktop ($where)",
                        abs(g[i] - w[i]) < 2e-3f,
                    )
                }
            }
        }
    }

    @Test
    fun `the shader declares every uniform the pose sets`() {
        // A uniform set but never declared would throw at draw time, on the
        // phone, in front of the owner. Cheaper to find it here.
        val names = CritterPose.uniforms(
            CritterPose.pose(FaceState.IDLE, FaceState.IDLE, 5f, 1f, 0f),
        ).keys + setOf("uHot", "uCool", "uYaw", "uPit", "uTime", "uZoom", "uCenter", "uR")
        for (n in names) {
            assertTrue(
                "CritterShaders.RED_PANDA has no uniform named $n",
                Regex("""uniform\s+\w+\s+$n\s*;""").containsMatchIn(CritterShaders.RED_PANDA),
            )
        }
    }

    @Test
    fun `the panda is offered`() {
        assertTrue(Faces.all.any { it.id == "redpanda" })
    }

    @Test
    fun `asleep, its eyes are shut and it does not follow the pointer`() {
        val p = CritterPose.uniforms(
            CritterPose.pose(
                FaceState.STANDBY, FaceState.STANDBY, 5f, 3f, 0f,
                CritterPose.Look(x = 1f, y = 1f, w = 1f),
            ),
        )
        val face = p.getValue("uFace")
        assertEquals(0f, face[0], 0f)
        assertEquals(0f, face[1], 0f)
        val look = p.getValue("uLook")
        assertEquals(0f, look[0], 1e-6f)
    }
}
