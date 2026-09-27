package com.jarvis.client

import com.jarvis.client.face.CritterPose
import com.jarvis.client.face.CritterShaders
import com.jarvis.client.face.Faces
import com.jarvis.client.face.OtterPose
import com.jarvis.client.face.OwlPose
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

    /** Each animal's pose and uniforms, by face id - the desktop's CritterPose.species. */
    private fun poseOf(species: String): (FaceState, FaceState, Float, Float, Float, CritterPose.Look, CritterPose.Hist) -> FloatArray =
        when (species) {
            "redpanda" -> CritterPose::pose
            "pygmyowl" -> OwlPose::pose
            "seaotter" -> OtterPose::pose
            else -> error("no Kotlin pose for '$species' - add one, or drop it from tools/gen_critters.py")
        }

    private fun uniformsOf(species: String): (FloatArray) -> Map<String, FloatArray> = when (species) {
        "redpanda" -> CritterPose::uniforms
        "pygmyowl" -> OwlPose::uniforms
        "seaotter" -> OtterPose::uniforms
        else -> error("no Kotlin pose for '$species'")
    }

    @Test
    fun `every pose matches the desktop's`() {
        val species = cases.map { it.jsonObject["species"]!!.jsonPrimitive.content }.toSet()
        assertEquals("the fixture should cover every animal", setOf("redpanda", "pygmyowl", "seaotter"), species)
        assertTrue("the fixture should cover every state", cases.size >= 3 * 8 * 5)
        for (c in cases) {
            val o = c.jsonObject
            val sp = o["species"]!!.jsonPrimitive.content
            val look = o["look"]!!.jsonObject
            val hist = o["hist"]?.jsonObject
            val pose = poseOf(sp)(
                state(o["state"]!!.jsonPrimitive.content),
                state(o["prev"]!!.jsonPrimitive.content),
                o["since"]!!.jsonPrimitive.float,
                o["t"]!!.jsonPrimitive.float,
                o["amp"]!!.jsonPrimitive.float,
                CritterPose.Look(
                    x = look["x"]?.jsonPrimitive?.float ?: 0f,
                    y = look["y"]?.jsonPrimitive?.float ?: 0f,
                    w = look["w"]?.jsonPrimitive?.float ?: 0f,
                ),
                CritterPose.Hist(
                    prev2 = hist?.get("prev2")?.jsonPrimitive?.content?.let(::state),
                    gap = hist?.get("gap")?.jsonPrimitive?.float ?: 1e9f,
                    prevAmp = hist?.get("prevAmp")?.jsonPrimitive?.float ?: Float.NaN,
                ),
            )
            val got = uniformsOf(sp)(pose)
            val want = o["uniforms"]!!.jsonObject
            assertEquals("uniform names differ from the desktop's", want.keys, got.keys)
            val where = "$sp: ${o["state"]} from ${o["prev"]} at t=${o["t"]}"
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
    fun `each shader declares every uniform its pose sets`() {
        // A uniform set but never declared would throw at draw time, on the
        // phone, in front of the owner. Cheaper to find it here.
        val host = setOf("uHot", "uCool", "uYaw", "uPit", "uTime", "uZoom", "uCenter", "uR", "uPx")
        val shaders = mapOf(
            "RED_PANDA" to (CritterShaders.RED_PANDA to CritterPose.uniforms(
                CritterPose.pose(FaceState.IDLE, FaceState.IDLE, 5f, 1f, 0f),
            ).keys),
            "PYGMY_OWL" to (CritterShaders.PYGMY_OWL to OwlPose.uniforms(
                OwlPose.pose(FaceState.IDLE, FaceState.IDLE, 5f, 1f, 0f),
            ).keys),
            "SEA_OTTER" to (CritterShaders.SEA_OTTER to OtterPose.uniforms(
                OtterPose.pose(FaceState.IDLE, FaceState.IDLE, 5f, 1f, 0f),
            ).keys),
        )
        for ((const, pair) in shaders) {
            val (src, names) = pair
            for (n in names + host) {
                assertTrue(
                    "CritterShaders.$const has no uniform named $n",
                    Regex("""uniform\s+\w+\s+$n\s*;""").containsMatchIn(src),
                )
            }
        }
    }

    @Test
    fun `leaving speaking, the mouth closes over the blend instead of at once`() {
        // The loudness at the change carries the old pose; the new state's
        // loudness is 0 and used to shut the mouth in one frame.
        val mouth = { since: Float ->
            CritterPose.uniforms(
                CritterPose.pose(
                    FaceState.IDLE, FaceState.SPEAKING, since, 2f, 0f,
                    hist = CritterPose.Hist(prevAmp = 0.6f),
                ),
            ).getValue("uFace")[3]
        }
        assertTrue("the mouth is already shut on the frame of the change", mouth(0f) > 0.7f)
        assertTrue("the mouth is still open once the blend is over", mouth(1f) == 0f)
    }

    @Test
    fun `all three animals are offered`() {
        for (id in listOf("redpanda", "pygmyowl", "seaotter")) {
            assertTrue("$id is not in Faces.all", Faces.all.any { it.id == id })
        }
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
