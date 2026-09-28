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

    private fun uniformsOf(species: String): (FloatArray, FloatArray?) -> Map<String, FloatArray> = when (species) {
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
                    prevAmp2 = hist?.get("prevAmp2")?.jsonPrimitive?.float ?: Float.NaN,
                ),
            )
            val mouth = o["mouth"]?.jsonObject?.let { m ->
                floatArrayOf(
                    m["open"]!!.jsonPrimitive.float, m["wide"]!!.jsonPrimitive.float, m["round"]!!.jsonPrimitive.float,
                )
            }
            val got = uniformsOf(sp)(pose, mouth)
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

    // Each animal's pose, its uniforms and its speaking weight, for the
    // mouth tests below.
    private class Animal(
        val id: String,
        val pose: (FaceState, FaceState, Float) -> FloatArray,
        val uniforms: (FloatArray, FloatArray?) -> Map<String, FloatArray>,
        val weight: (FloatArray) -> Float,
    )

    private val animals = listOf(
        Animal("redpanda", { s, p, since -> CritterPose.pose(s, p, since, 2f, 0.3f) }, CritterPose::uniforms, CritterPose::speakingWeight),
        Animal("pygmyowl", { s, p, since -> OwlPose.pose(s, p, since, 2f, 0.3f) }, OwlPose::uniforms, OwlPose::speakingWeight),
        Animal("seaotter", { s, p, since -> OtterPose.pose(s, p, since, 2f, 0.3f) }, OtterPose::uniforms, OtterPose::speakingWeight),
    )

    @Test
    fun `every animal has a three-number mouth uniform`() {
        for (a in animals) {
            val u = a.uniforms(a.pose(FaceState.IDLE, FaceState.IDLE, 5f), null)
            assertEquals("${a.id}: uMouth should be open, wide, round", 3, u.getValue("uMouth").size)
            assertEquals("${a.id}: uFace no longer carries the mouth", 3, u.getValue("uFace").size)
        }
    }

    @Test
    fun `with no voice the mouth stays shut, even while speaking`() {
        // A typed answer, Quiet mode or an answer kept on screen streams as
        // SPEAKING with no sound. The animals used to open their mouths from
        // the loudness; now nothing but the voice's own mouth track moves it.
        for (a in animals) {
            val u = a.uniforms(a.pose(FaceState.SPEAKING, FaceState.SPEAKING, 5f), null)
            assertTrue("${a.id}: mouth moved with no voice", u.getValue("uMouth").all { it == 0f })
        }
    }

    @Test
    fun `the mouth is the voice's shape times how much the pose is speaking`() {
        val mouth = floatArrayOf(0.8f, 0.5f, 0.25f)
        for (a in animals) {
            // Settled in speaking: the whole shape.
            val full = a.uniforms(a.pose(FaceState.SPEAKING, FaceState.SPEAKING, 5f), mouth).getValue("uMouth")
            for (i in 0 until 3) assertEquals("${a.id}: settled speaking", mouth[i], full[i], 1e-6f)
            // Any other state: shut, whatever the track says.
            val idle = a.uniforms(a.pose(FaceState.IDLE, FaceState.IDLE, 5f), mouth).getValue("uMouth")
            assertTrue("${a.id}: mouth open outside speaking", idle.all { it == 0f })
            // Leaving speaking: it closes over the blend, never in one frame,
            // and always in proportion to the pose's own speaking weight.
            var last = 2f
            for (step in 0..11) {
                val since = step * 0.05f
                val p = a.pose(FaceState.IDLE, FaceState.SPEAKING, since)
                val w = a.weight(p)
                val got = a.uniforms(p, mouth).getValue("uMouth")
                for (i in 0 until 3) assertEquals("${a.id}: at $since s", mouth[i] * w, got[i], 1e-5f)
                assertTrue("${a.id}: the speaking weight went back up at $since s", w <= last)
                last = w
            }
            assertTrue("${a.id}: the mouth shut at once when speaking ended", a.weight(a.pose(FaceState.IDLE, FaceState.SPEAKING, 0f)) > 0.99f)
            assertEquals("${a.id}: the mouth is still open after the blend", 0f, a.weight(a.pose(FaceState.IDLE, FaceState.SPEAKING, 1f)), 0f)
        }
    }

    @Test
    fun `the mouth values are clamped to 0 to 1`() {
        for (a in animals) {
            val p = a.pose(FaceState.SPEAKING, FaceState.SPEAKING, 5f)
            val got = a.uniforms(p, floatArrayOf(1.7f, -0.3f, Float.NaN)).getValue("uMouth")
            assertEquals(1f, got[0], 0f)
            assertEquals(0f, got[1], 0f)
            assertEquals(0f, got[2], 0f)
            // A short array is read as far as it goes.
            assertEquals(0f, a.uniforms(p, floatArrayOf(0.5f)).getValue("uMouth")[1], 0f)
        }
    }

    @Test
    fun `a quick change back draws the older pose at its own loudness`() {
        // speaking (loud) -> idle -> speaking again 0.2 s later. The speaking
        // pose the idle one was melting from must be drawn at the loudness of
        // the change out of speaking (prevAmp2), not of the latest change.
        val orb = { hist: CritterPose.Hist ->
            CritterPose.uniforms(
                CritterPose.pose(FaceState.SPEAKING, FaceState.IDLE, 0.1f, 6.2f, 0.3f, hist = hist),
            ).getValue("uOrbGlow")[0]
        }
        val base = CritterPose.Hist(prev2 = FaceState.SPEAKING, gap = 0.2f, prevAmp = 0.05f)
        val loud = orb(base.copy(prevAmp2 = 0.7f))
        val quiet = orb(base.copy(prevAmp2 = 0.05f))
        assertTrue("prevAmp2 made no difference ($loud vs $quiet)", loud > quiet + 0.05f)
        // A host that does not keep prevAmp2 gets prevAmp, as before.
        assertEquals(quiet, orb(base), 1e-6f)
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
