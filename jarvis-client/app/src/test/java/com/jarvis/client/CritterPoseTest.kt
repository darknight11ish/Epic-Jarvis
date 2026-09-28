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
    private fun poseOf(species: String): (FaceState, FaceState, Float, Float, Float, CritterPose.Look, CritterPose.Hist, CritterPose.Opts) -> FloatArray =
        when (species) {
            "redpanda" -> CritterPose::pose
            "pygmyowl" -> OwlPose::pose
            "seaotter" -> OtterPose::pose
            else -> error("no Kotlin pose for '$species' - add one, or drop it from tools/gen_critters.py")
        }

    private fun overlayOf(species: String): (FloatArray, Float, Float, Float) -> FloatArray = when (species) {
        "redpanda" -> CritterPose::overlay
        "pygmyowl" -> OwlPose::overlay
        "seaotter" -> OtterPose::overlay
        else -> error("no Kotlin pose for '$species'")
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
            val opts = o["opts"]?.jsonObject
            val view = o["view"]?.jsonObject
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
                    past = hist?.get("past")?.jsonArray?.map { e ->
                        val c = e.jsonObject
                        CritterPose.Change(
                            state(c["state"]!!.jsonPrimitive.content),
                            c["gap"]!!.jsonPrimitive.float, c["amp"]!!.jsonPrimitive.float,
                        )
                    },
                ),
                CritterPose.Opts(
                    calm = opts?.get("calm")?.jsonPrimitive?.float ?: 0f,
                    serious = opts?.get("serious")?.jsonPrimitive?.float ?: 0f,
                    still = opts?.get("still")?.jsonPrimitive?.float ?: 0f,
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
            val where = "$sp: ${o["state"]} from ${o["prev"]} at t=${o["t"]} opts=$opts"
            // Where the sleeping Zs rise from, and how much to show them.
            val ov = o["overlay"]!!.jsonObject
            val gotOv = overlayOf(sp)(
                pose, view?.get("yaw")?.jsonPrimitive?.float ?: 0f,
                view?.get("pitch")?.jsonPrimitive?.float ?: 0f, view?.get("zoom")?.jsonPrimitive?.float ?: 1f,
            )
            for ((i, k) in listOf("asleep", "x", "y").withIndex()) {
                val w = ov[k]!!.jsonPrimitive.float
                assertTrue("overlay $k is ${gotOv[i]} on the phone and $w on the desktop ($where)", abs(gotOv[i] - w) < 2e-3f)
            }
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

    // --- the body moving: calm, smooth, never a pop ------------------------

    private val poses = listOf(
        "redpanda" to { s: FaceState, p: FaceState, since: Float, t: Float, h: CritterPose.Hist ->
            CritterPose.uniforms(CritterPose.pose(s, p, since, t, 0.3f, hist = h)) },
        "pygmyowl" to { s: FaceState, p: FaceState, since: Float, t: Float, h: CritterPose.Hist ->
            OwlPose.uniforms(OwlPose.pose(s, p, since, t, 0.3f, hist = h)) },
        "seaotter" to { s: FaceState, p: FaceState, since: Float, t: Float, h: CritterPose.Hist ->
            OtterPose.uniforms(OtterPose.pose(s, p, since, t, 0.3f, hist = h)) },
    )

    // The eyelids and pupils may be quick (a blink, a glance) and the water's
    // ripple phase wraps round by design; everything else must glide.
    private fun glides(name: String, i: Int) =
        !(name == "uFace" && i < 2) && name != "uLook" && !(name == "uWater" && i == 1)

    @Test
    fun `a change of state never jumps`() {
        // Every one of the 56 changes, stepped at 60 frames a second: no
        // number moves further in one frame than 0.12 (a small fraction of
        // the animal's size, or about 7 degrees) - the old half-second melt
        // moved up to about 0.08.
        val states = FaceState.values()
        for ((id, u) in poses) for (a in states) for (b in states) {
            if (a == b) continue
            var last: Map<String, FloatArray>? = null
            for (f in -3..120) {
                val since = f / 60f
                val t = 40f + since
                val now = if (since < 0f) u(a, a, 9f, t, CritterPose.Hist()) else u(b, a, since, t, CritterPose.Hist(prevAmp = 0.3f))
                val prev = last
                if (prev != null) for ((name, v) in now) for (i in v.indices) {
                    assertTrue("$id: $name[$i] is not a number, $a -> $b at $since s", v[i].isFinite())
                    if (!glides(name, i)) continue
                    val d = abs(v[i] - prev.getValue(name)[i])
                    assertTrue("$id: $name[$i] jumped $d in one frame, $a -> $b at $since s", d < 0.12f)
                }
                last = now
            }
        }
    }

    @Test
    fun `asleep, only the breathing moves`() {
        // Standby: over two minutes the head turns less than a degree and a
        // half and the body does not move beyond its breath.
        for ((id, u) in poses) {
            var lo = Float.MAX_VALUE
            var hi = -Float.MAX_VALUE
            for (f in 0 until 120 * 10) {
                val r = u(FaceState.STANDBY, FaceState.STANDBY, 99f, 500f + f / 10f, CritterPose.Hist())
                val yaw = r.getValue("uHeadR0")[2]
                lo = minOf(lo, yaw); hi = maxOf(hi, yaw)
            }
            assertTrue("$id: asleep, its head swung ${hi - lo}", hi - lo < 0.03f)
        }
    }

    @Test
    fun `the little idle happenings are rare and never overlap`() {
        // A stretch, a ruffle, a face wash: at most one in any 16 seconds,
        // starting 0.5 to 6 s into it, so two are always 10 s or more apart.
        var count = 0
        var lastStart = -1e9f
        var t = 0f
        while (t < 3600f) {
            val h = CritterPose.happening(t, 16f, 0.5f, 5.5f, 16, 0.7f, 5)
            if (h[0] >= 0f && h[1] >= 0f && h[1] < 0.05f) {
                assertTrue("two happenings ${t - lastStart} s apart", t - lastStart >= 10f)
                lastStart = t; count++
            }
            t += 0.05f
        }
        assertTrue("$count happenings in an hour", count in 100..240)
    }

    @Test
    fun `the eyes jump and then hold`() {
        // Glances are jumps (a saccade), and every look is held at least
        // 0.6 s before the next jump - never a flicker.
        val jumps = mutableListOf<Float>()
        var last = CritterPose.gaze(0f, 0, 1.5f, 6f, 0.35f, 0.8f, 0.25f, 0f, 0.08f, 1.1f)
        var f = 1
        while (f < 60 * 900) {
            val t = f / 60f
            val g = CritterPose.gaze(t, 0, 1.5f, 6f, 0.35f, 0.8f, 0.25f, 0f, 0.08f, 1.1f)
            val d = abs(g[0] - last[0]) + abs(g[1] - last[1])
            if (d > 0.06f && (jumps.isEmpty() || t - jumps.last() > 0.1f)) jumps.add(t)
            last = g
            f++
        }
        assertTrue("only ${jumps.size} glances in 15 minutes", jumps.size > 100)
        for (i in 1 until jumps.size) {
            assertTrue("a look held only ${jumps[i] - jumps[i - 1]} s", jumps[i] - jumps[i - 1] >= 0.6f)
        }
    }

    @Test
    fun `a clock restarted at a multiple of 4096 seconds changes nothing`() {
        // The phone may keep its clock small by starting it again from zero;
        // at any multiple of CritterPose.PERIOD the animal must not jump.
        val period = CritterPose.PERIOD.toFloat()
        for ((id, u) in poses) for (s in FaceState.values()) {
            for (t in floatArrayOf(0.4f, 17.3f, 203.75f, 1000.5f)) {
                val a = u(s, s, 99f, t, CritterPose.Hist())
                val b = u(s, s, 99f, t + period, CritterPose.Hist())
                for ((name, v) in a) for (i in v.indices) {
                    if (name == "uWater" && i == 1) continue   // a phase: the same modulo a full turn
                    assertEquals("$id $s: $name[$i] at $t s and ${t + period} s", v[i], b.getValue(name)[i], 2e-3f)
                }
            }
        }
    }

    @Test
    fun `speaking and waiting on you look different on the otter`() {
        // Both used to raise a forearm. Now speaking keeps the pebble low on
        // its chest, and waiting holds it up a little toward you in both paws -
        // a little: held higher, the forearm stood up and read as a raised hand.
        val speak = OtterPose.uniforms(OtterPose.pose(FaceState.SPEAKING, FaceState.SPEAKING, 9f, 30f, 0.5f))
        val wait = OtterPose.uniforms(OtterPose.pose(FaceState.APPROVAL, FaceState.APPROVAL, 9f, 30f, 0.5f))
        val rest = OtterPose.uniforms(OtterPose.pose(FaceState.IDLE, FaceState.IDLE, 9f, 30f, 0f))
        val lift = { u: Map<String, FloatArray> -> u.getValue("uOrb")[1] - rest.getValue("uOrb")[1] }
        assertTrue("speaking raised the pebble ${lift(speak)}", lift(speak) < 0.03f)
        assertTrue("waiting raised the pebble only ${lift(wait)}", lift(wait) > 0.05f)
        assertTrue("waiting raised the pebble ${lift(wait)} - a raised hand again", lift(wait) < 0.10f)
    }

    @Test
    fun `waiting on you and something going wrong are still`() {
        // The owner's call (2026-09-28): at these moments no wave, no
        // scratching, nothing cute - an attentive or concerned look that
        // holds still. Over ten seconds the paws, wings and head barely move
        // (breathing only).
        for ((id, u) in poses) for (s in listOf(FaceState.APPROVAL, FaceState.ERROR)) {
            val first = u(s, s, 99f, 200f, CritterPose.Hist())
            for (f in 1..100) {
                val now = u(s, s, 99f, 200f + f / 10f, CritterPose.Hist())
                for (name in listOf("uPawL", "uPawR", "uWingL0", "uWingR0", "uHeadR0", "uHeadR1")) {
                    val a = first[name] ?: continue
                    val b = now.getValue(name)
                    for (i in a.indices) {
                        assertTrue("$id $s: $name[$i] moved ${abs(a[i] - b[i])}", abs(a[i] - b[i]) < 0.05f)
                    }
                }
            }
        }
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

    // --- calm, serious and still; many changes at once; the Zs -----------

    private fun opts(calm: Float = 0f, serious: Float = 0f, still: Float = 0f) = CritterPose.Opts(calm, serious, still)
    private val withOpts = listOf(
        "redpanda" to { s: FaceState, t: Float, o: CritterPose.Opts ->
            CritterPose.uniforms(CritterPose.pose(s, s, 99f, t, 0.3f, opts = o)) },
        "pygmyowl" to { s: FaceState, t: Float, o: CritterPose.Opts ->
            OwlPose.uniforms(OwlPose.pose(s, s, 99f, t, 0.3f, opts = o)) },
        "seaotter" to { s: FaceState, t: Float, o: CritterPose.Opts ->
            OtterPose.uniforms(OtterPose.pose(s, s, 99f, t, 0.3f, opts = o)) },
    )
    // The head's own tilt (its roll, relative to the body): the head's turn
    // is ry(yaw) rx(pitch) rz(roll) in every animal, so the roll is read off
    // the middle row of the body-to-head rotation.
    private fun tilt(u: Map<String, FloatArray>): Float {
        fun m(name: String) = FloatArray(9) { k -> u.getValue(name + (k % 3))[k / 3] }   // columns -> matrix
        val b = m("uBodyR")
        val h = m("uHeadR")
        // rel = b^T h: row 1 of it, columns 0 and 1.
        val r10 = b[1] * h[0] + b[4] * h[3] + b[7] * h[6]
        val r11 = b[1] * h[1] + b[4] * h[4] + b[7] * h[7]
        return abs(kotlin.math.atan2(r10, r11))
    }
    private fun range(xs: List<Float>) = (xs.maxOrNull() ?: 0f) - (xs.minOrNull() ?: 0f)

    @Test
    fun `calm makes the head turn less and takes the happenings away`() {
        for ((id, u) in withOpts) {
            val yawNormal = range((0 until 3000).map { u(FaceState.IDLE, 100f + it / 10f, opts())["uHeadR0"]!![2] })
            val yawCalm = range((0 until 3000).map { u(FaceState.IDLE, 100f + it / 10f, opts(calm = 1f))["uHeadR0"]!![2] })
            assertTrue("$id: calm head turned $yawCalm against $yawNormal", yawCalm < 0.6f * yawNormal)
        }
        // No talking gesture at all: the owl's wing never lifts while it talks.
        val wing = (0 until 1200).map {
            OwlPose.uniforms(OwlPose.pose(FaceState.SPEAKING, FaceState.SPEAKING, 99f, 10f + it / 10f, 0.4f, opts = opts(calm = 1f)))
                .getValue("uWingR0")[0]
        }
        assertTrue("the owl gestured with its wing under calm", wing.all { abs(it - 1f) < 1e-5f })
    }

    @Test
    fun `serious is plain - no tilt, no gestures`() {
        for ((id, u) in withOpts) for (s in listOf(FaceState.LISTENING, FaceState.SPEAKING, FaceState.IDLE, FaceState.ERROR)) {
            val worst = (0 until 600).maxOf { tilt(u(s, 200f + it / 10f, opts(serious = 1f))) }
            assertTrue("$id $s: tipped its head ${worst} under serious", worst < 0.06f)
        }
        // Without it, listening's tilt is plain to see - the check means something.
        for ((id, u) in withOpts) assertTrue("$id: no listening tilt to take away", tilt(u(FaceState.LISTENING, 200f, opts())) > 0.2f)
    }

    @Test
    fun `still only breathes and keeps its eyes on you`() {
        for ((id, u) in withOpts) for (s in listOf(FaceState.IDLE, FaceState.SPEAKING, FaceState.LISTENING)) {
            val frames = (0 until 600).map { u(s, 300f + it / 10f, opts(still = 1f)) }
            for (name in listOf("uHeadR0", "uHeadR1", "uHeadR2")) for (i in 0 until 3) {
                val r = range(frames.map { it.getValue(name)[i] })
                assertTrue("$id $s: $name[$i] moved $r under still", r < 0.01f)
            }
            if (s == FaceState.IDLE) {
                val look = frames.maxOf { maxOf(abs(it.getValue("uLook")[0]), abs(it.getValue("uLook")[1])) }
                assertTrue("$id: its eyes wandered $look under still", look < 0.05f)
            }
        }
    }

    @Test
    fun `switching an option eases, it never snaps`() {
        // The host eases each weight over about a second; stepped that way at
        // 60 frames a second nothing moves more than a sliver in one frame.
        for ((id, u) in withOpts) for (s in listOf(FaceState.IDLE, FaceState.LISTENING, FaceState.THINKING, FaceState.SPEAKING)) {
            for (which in 0 until 3) {
                var last: Map<String, FloatArray>? = null
                for (f in 0..90) {
                    val w = CritterPose.ease(f / 60f)
                    val o = when (which) { 0 -> opts(calm = w); 1 -> opts(serious = w); else -> opts(still = w) }
                    val now = u(s, 500f + f / 60f, o)
                    val prev = last
                    if (prev != null) for ((name, v) in now) for (i in v.indices) {
                        if (!glides(name, i)) continue
                        val d = abs(v[i] - prev.getValue(name)[i])
                        assertTrue("$id $s option $which: $name[$i] jumped $d at frame $f", d < 0.05f)
                    }
                    last = now
                }
            }
        }
    }

    @Test
    fun `three changes inside a second carry on smoothly`() {
        // idle -> speaking -> thinking -> listening -> idle, a quarter of a
        // second apart, stepped at 60 frames a second, with the host's list
        // of past changes: nothing jumps.
        val seq = listOf(FaceState.IDLE, FaceState.SPEAKING, FaceState.THINKING, FaceState.LISTENING, FaceState.IDLE)
        val at = listOf(-99f, 0f, 0.25f, 0.5f, 0.8f)
        for ((id, u) in poses) {
            var last: Map<String, FloatArray>? = null
            for (f in -6..180) {
                val now = f / 60f
                val k = at.indexOfLast { it <= now }
                val past = (k downTo 1).map { j -> CritterPose.Change(seq[j - 1], at[j] - at[j - 1], 0.3f) }
                val prev = if (k > 0) seq[k - 1] else seq[0]
                val r = u(seq[k], prev, now - at[k], 60f + now, CritterPose.Hist(past = past))
                val p = last
                if (p != null) for ((name, v) in r) for (i in v.indices) {
                    if (!glides(name, i)) continue
                    val d = abs(v[i] - p.getValue(name)[i])
                    assertTrue("$id: $name[$i] jumped $d at $now s", d < 0.05f)
                }
                last = r
            }
        }
    }

    @Test
    fun `a happening or a gesture is never the same kind twice running`() {
        val kinds = floatArrayOf(12f, 30f, 12f, 23f, 23f)
        var lastKind = -1
        var lastSlot = -9
        val counts = IntArray(5)
        for (n in 0 until 256) {
            val h = CritterPose.happening(n * 16f + 15.9f, 16f, 0.5f, 5.5f, 16, 0.7f, kinds)
            if (h[0] < 0f) continue
            val k = h[0].toInt()
            counts[k]++
            if (lastSlot == n - 1) assertTrue("slot $n repeats kind $k", k != lastKind)
            lastKind = k; lastSlot = n
        }
        val total = counts.sum().toFloat()
        assertTrue("stretches ${counts[0] / total} of all happenings", counts[0] / total < 0.2f)
        // Talking gestures: never the same kind in back-to-back slots, never
        // closer than 1.4 s, and never within LOOK_CLEAR of a look starting.
        var lastStart = -9f
        lastKind = -1
        for (n in 0 until 2048) {
            val b = CritterPose.beat(n * 2f + 1.99f, 40, 0, 1.8f, 6f, 0.65f)
            if (b[0] < 0f) continue
            val start = b[2]
            if (start - lastStart < 2.7f) assertTrue("gesture at $start repeats", b[0].toInt() != lastKind)
            assertTrue("gestures ${start - lastStart} s apart", start - lastStart >= 1.4f)
            lastStart = start; lastKind = b[0].toInt()
        }
    }

    @Test
    fun `the Zs show only asleep, and rise from above the head`() {
        val sleepers = listOf(
            "redpanda" to { s: FaceState, p: FaceState, since: Float ->
                CritterPose.overlay(CritterPose.pose(s, p, since, 30f, 0f)) },
            "pygmyowl" to { s: FaceState, p: FaceState, since: Float ->
                OwlPose.overlay(OwlPose.pose(s, p, since, 30f, 0f)) },
            "seaotter" to { s: FaceState, p: FaceState, since: Float ->
                OtterPose.overlay(OtterPose.pose(s, p, since, 30f, 0f)) },
        )
        for ((id, ov) in sleepers) {
            val asleep = ov(FaceState.STANDBY, FaceState.STANDBY, 99f)
            assertEquals("$id: asleep", 1f, asleep[0], 1e-6f)
            assertTrue("$id: the Zs start off the picture (${asleep[1]}, ${asleep[2]})", abs(asleep[1]) < 0.9f && asleep[2] in 0.2f..0.9f)
            for (s in FaceState.values()) if (s != FaceState.STANDBY) {
                assertEquals("$id $s: Zs while awake", 0f, ov(s, s, 99f)[0], 1e-6f)
            }
            // Nodding off takes a couple of seconds, not half of one.
            val early = ov(FaceState.STANDBY, FaceState.IDLE, 0.4f)[0]
            val late = ov(FaceState.STANDBY, FaceState.IDLE, 4f)[0]
            assertTrue("$id: Zs at ${early} 0.4 s into nodding off", early < 0.3f)
            assertTrue("$id: Zs only at ${late} 4 s in", late > 0.9f)
        }
    }

    /** The desktop's Zs fixture (tools/gen_critters.py). */
    private val zsGolden by lazy {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("critter-zs-golden.json")) {
            "critter-zs-golden.json is missing from test resources - run tools/gen_critters.py"
        }.bufferedReader().readText()
        Json.parseToJsonElement(text).jsonObject
    }

    @Test
    fun `the Zs' numbers are the desktop's`() {
        val spec = zsGolden["spec"]!!.jsonObject
        assertEquals("the same numbers, by name", spec.keys, CritterPose.Zs.all.keys)
        for ((k, v) in spec) {
            val want = v.jsonPrimitive.float
            assertEquals("ZS.$k", want, CritterPose.Zs.all.getValue(k), 1e-6f)
        }
    }

    @Test
    fun `the Zs rise, sway and fade exactly as on the desktop`() {
        val cases = zsGolden["cases"]!!.jsonArray
        assertTrue("the fixture should have its cases", cases.size >= 100)
        for (c in cases) {
            val o = c.jsonObject
            val ov = o["ov"]!!.jsonObject
            val t = o["t"]!!.jsonPrimitive.float
            val calm = o["calm"]!!.jsonPrimitive.float
            val got = CritterPose.zs(
                t,
                floatArrayOf(ov["asleep"]!!.jsonPrimitive.float, ov["x"]!!.jsonPrimitive.float, ov["y"]!!.jsonPrimitive.float),
                calm,
            )
            val want = o["zs"]!!.jsonArray
            assertEquals("how many letters", want.size * 5, got.size)
            for ((i, z) in want.withIndex()) {
                val w = z.jsonArray.map { it.jsonPrimitive.float }
                for (j in 0 until 5) {
                    assertTrue(
                        "z $i value $j is ${got[i * 5 + j]} on the phone and ${w[j]} on the desktop (t=$t calm=$calm ov=$ov)",
                        abs(got[i * 5 + j] - w[j]) < 2e-3f,
                    )
                }
            }
        }
    }

    @Test
    fun `awake, there are no Zs, and calm keeps one still z`() {
        for (t in listOf(0f, 3.3f, 17.1f, 250.5f)) {
            val awake = CritterPose.zs(t, floatArrayOf(0f, 0.4f, 0.6f), 0f)
            for (i in 0 until CritterPose.Zs.COUNT) assertEquals("awake z $i at $t", 0f, awake[i * 5 + 3], 0f)
            val calm = CritterPose.zs(t, floatArrayOf(1f, 0.4f, 0.6f), 1f)
            assertTrue("calm shows its one z", calm[3] > 0.5f)
            for (i in 1 until CritterPose.Zs.COUNT) assertEquals("calm: no rising z $i at $t", 0f, calm[i * 5 + 3], 0f)
        }
        // The still z does not move with the clock.
        val a = CritterPose.zs(1f, floatArrayOf(1f, 0.4f, 0.6f), 1f)
        val b = CritterPose.zs(9f, floatArrayOf(1f, 0.4f, 0.6f), 1f)
        for (j in 0 until 5) assertEquals(a[j], b[j], 0f)
    }

    // --- waking up and nodding off (the owner, 2026-09-28) ----------------

    private class Sleeper(
        val id: String,
        val pose: (FaceState, FaceState, Float, Float, Float, CritterPose.Look, CritterPose.Hist, CritterPose.Opts) -> FloatArray,
        /** The same settling with no wake-up or nodding-off piece: what it was before. */
        val plain: (FaceState, FaceState, Float, Float, Float, CritterPose.Hist, CritterPose.Opts) -> FloatArray,
        val uniforms: (FloatArray, FloatArray?) -> Map<String, FloatArray>,
        val overlay: (FloatArray, Float, Float, Float) -> FloatArray,
    )
    private val sleepers = listOf(
        Sleeper("redpanda", CritterPose::pose, { s, p, since, t, amp, h, o ->
            CritterPose.blend(CritterPose::stateTargets, CritterPose.HALF, s, p, since, t, amp, CritterPose.Look(), h, o)
        }, CritterPose::uniforms, CritterPose::overlay),
        Sleeper("pygmyowl", OwlPose::pose, { s, p, since, t, amp, h, o ->
            CritterPose.blend(OwlPose::stateTargets, OwlPose.HALF, s, p, since, t, amp, CritterPose.Look(), h, o)
        }, OwlPose::uniforms, OwlPose::overlay),
        Sleeper("seaotter", OtterPose::pose, { s, p, since, t, amp, h, o ->
            CritterPose.blend(OtterPose::stateTargets, OtterPose.HALF, s, p, since, t, amp, CritterPose.Look(), h, o)
        }, OtterPose::uniforms, OtterPose::overlay),
    )
    // Asleep for 9 s (awake for 20 before that), and awake for 20 s.
    private val asleep9 = CritterPose.Hist(past = listOf(
        CritterPose.Change(FaceState.STANDBY, 9f, 0f), CritterPose.Change(FaceState.IDLE, 20f, 0f)))
    private val awake20 = CritterPose.Hist(past = listOf(
        CritterPose.Change(FaceState.IDLE, 20f, 0f), CritterPose.Change(FaceState.STANDBY, 9f, 0f)))
    private fun ampOf(s: FaceState) = when (s) {
        FaceState.SPEAKING -> 0.4f
        FaceState.LISTENING, FaceState.APPROVAL -> 0.28f
        else -> 0f
    }
    /** The biggest difference between two poses' uniforms, leaving out the eyelids (and, if asked, the pupils). */
    private fun bodyGap(a: Map<String, FloatArray>, b: Map<String, FloatArray>): Float {
        var worst = 0f
        for ((name, v) in a) for (i in v.indices) {
            if (name == "uFace" && i < 2) continue
            worst = maxOf(worst, abs(v[i] - b.getValue(name)[i]))
        }
        return worst
    }

    @Test
    fun `waking up plays, and is over by 2_2 seconds`() {
        for (a in sleepers) {
            val woke = { x: Float -> a.uniforms(a.pose(FaceState.IDLE, FaceState.STANDBY, x, 120f + x, 0f, CritterPose.Look(), asleep9, opts()), null) }
            val was = { x: Float -> a.uniforms(a.plain(FaceState.IDLE, FaceState.STANDBY, x, 120f + x, 0f, asleep9, opts()), null) }
            // It plays: somewhere in its two seconds the body does something the
            // plain settling did not (a stretch, a ruffle, an eye rub).
            val most = (1..40).maxOf { f -> bodyGap(woke(f * 0.05f), was(f * 0.05f)) }
            assertTrue("${a.id}: the wake-up did nothing (${most})", most > 0.02f)
            // And the eyes open more slowly than they used to (in 0.1 s, before).
            val eyes = woke(0.3f).getValue("uFace")[0]
            assertTrue("${a.id}: eyes already ${eyes} open 0.3 s in", eyes < 0.6f)
            // It is over by 2.2 s: from then on, what the plain settling was.
            for (f in 0..20) {
                val x = 2.25f + f * 0.1f
                val gap = bodyGap(woke(x), was(x))
                assertTrue("${a.id}: still ${gap} from the plain pose ${x} s after waking", gap < 0.01f)
            }
        }
    }

    @Test
    fun `nodding off plays, and the Zs wait until it is asleep`() {
        for (a in sleepers) {
            val nod = { x: Float -> a.pose(FaceState.STANDBY, FaceState.IDLE, x, 140f + x, 0f, CritterPose.Look(), awake20, opts()) }
            val was = { x: Float -> a.uniforms(a.plain(FaceState.STANDBY, FaceState.IDLE, x, 140f + x, 0f, awake20, opts()), null) }
            val most = (1..58).maxOf { f -> bodyGap(a.uniforms(nod(f * 0.05f), null), was(f * 0.05f)) }
            assertTrue("${a.id}: nodding off did nothing (${most})", most > 0.02f)
            // No Zs for the first two seconds; all of them once it is asleep.
            for (f in 0..19) {
                val z = a.overlay(nod(f * 0.1f), 0f, 0f, 1f)[0]
                assertEquals("${a.id}: Zs at ${f * 0.1f} s into nodding off", 0f, z, 1e-6f)
            }
            assertEquals("${a.id}: asleep at 3 s", 1f, a.overlay(nod(3.0f), 0f, 0f, 1f)[0], 1e-6f)
            // Waking, they fade out within the first second.
            val gone = a.overlay(a.pose(FaceState.IDLE, FaceState.STANDBY, 1.0f, 121f, 0f, CritterPose.Look(), asleep9, opts()), 0f, 0f, 1f)[0]
            assertEquals("${a.id}: Zs a second after waking", 0f, gone, 1e-6f)
            // Eyes shut by the end, heavy (not yet shut) half a second in.
            val half = a.uniforms(nod(0.4f), null).getValue("uFace")[0]
            assertTrue("${a.id}: eyes ${half} 0.4 s into nodding off", half in 0.3f..1.0f)
            assertEquals("${a.id}: eyes open at 3 s", 0f, a.uniforms(nod(3.0f), null).getValue("uFace")[0], 1e-6f)
        }
    }

    @Test
    fun `waking into waiting on you or an error, only the eyes open`() {
        for (a in sleepers) for (s in listOf(FaceState.APPROVAL, FaceState.ERROR, FaceState.BANKED)) {
            for (f in 0..50) {
                val x = f * 0.05f
                val got = a.uniforms(a.pose(s, FaceState.STANDBY, x, 160f + x, ampOf(s), CritterPose.Look(), asleep9, opts()), null)
                val was = a.uniforms(a.plain(s, FaceState.STANDBY, x, 160f + x, ampOf(s), asleep9, opts()), null)
                val gap = bodyGap(got, was)
                assertTrue("${a.id} $s: the body moved ${gap} more than it used to, ${x} s after waking", gap < 1e-4f)
            }
        }
    }

    @Test
    fun `calm, serious and still keep only the eyes, both ways`() {
        for (a in sleepers) for (o in listOf(opts(calm = 1f), opts(serious = 1f), opts(still = 1f))) {
            for ((s, p, h) in listOf(Triple(FaceState.IDLE, FaceState.STANDBY, asleep9), Triple(FaceState.STANDBY, FaceState.IDLE, awake20))) {
                for (f in 0..64) {
                    val x = f * 0.05f
                    val got = a.uniforms(a.pose(s, p, x, 190f + x, 0f, CritterPose.Look(), h, o), null)
                    val was = a.uniforms(a.plain(s, p, x, 190f + x, 0f, h, o), null)
                    val gap = bodyGap(got, was)
                    assertTrue("${a.id} $s from $p $o: the body moved ${gap} more than it used to at ${x} s", gap < 1e-4f)
                }
            }
        }
    }

    /**
     * Steps a plan ([seconds, state] pairs) at 240 frames a second the way the
     * apps do - a list of past changes, newest first - and returns the worst
     * change of speed from one frame to the next over every gliding number
     * (units a second), failing on anything that is not a number.
     */
    private fun worstSpeedStep(a: Sleeper, plan: List<Pair<Float, FaceState>>, o: CritterPose.Opts = opts()): Float {
        val fps = 240f
        val dt = 1f / fps
        var past = listOf<CritterPose.Change>()
        var st = plan[0].second
        var at = -1e6f
        val frames = ArrayList<Map<String, FloatArray>>()
        var start = 0f
        var worst = 0f
        for ((secs, state) in plan) {
            val n = (secs * fps).toInt()
            for (k in 0 until n) {
                val now = start + k * dt
                if (state != st) {
                    past = (listOf(CritterPose.Change(st, now - at, ampOf(st))) + past).take(6)
                    st = state; at = now
                }
                val prev = past.firstOrNull()?.state ?: st
                val u = a.uniforms(a.pose(st, prev, now - at, 300f + now, ampOf(st), CritterPose.Look(), CritterPose.Hist(past = past), o), null)
                for ((name, v) in u) for (i in v.indices) {
                    assertTrue("${a.id}: $name[$i] is not a number at $now s", v[i].isFinite())
                }
                frames.add(u)
                if (frames.size >= 3) {
                    val (p2, p1, p0) = Triple(frames[frames.size - 3], frames[frames.size - 2], u)
                    for ((name, v) in p0) for (i in v.indices) {
                        if (!glides(name, i)) continue
                        val dv = abs((v[i] - p1.getValue(name)[i]) - (p1.getValue(name)[i] - p2.getValue(name)[i])) / dt
                        worst = maxOf(worst, dv)
                    }
                    frames.removeAt(0)
                }
            }
            start += n * dt
        }
        return worst
    }

    @Test
    fun `waking up and nodding off never change speed suddenly`() {
        // At 240 frames a second a sudden change of speed shows up whole
        // (a step of 0.3 a second stays 0.3), while a smooth one shrinks
        // with the frame. Before this was right, the end of each piece
        // stepped by about 3.
        val plans = listOf(
            listOf(3f to FaceState.IDLE, 4f to FaceState.STANDBY, 3f to FaceState.IDLE),
            listOf(3f to FaceState.IDLE, 0.3f to FaceState.STANDBY, 3f to FaceState.IDLE),
            listOf(4f to FaceState.STANDBY, 0.3f to FaceState.IDLE, 3.5f to FaceState.STANDBY),
            listOf(4f to FaceState.STANDBY, 0.6f to FaceState.LISTENING, 0.8f to FaceState.THINKING, 2.5f to FaceState.SPEAKING),
            listOf(4f to FaceState.STANDBY, 3f to FaceState.APPROVAL),
        )
        for (a in sleepers) for (plan in plans) {
            val w = worstSpeedStep(a, plan)
            assertTrue("${a.id}: speed changed by $w a second in one frame (${plan.map { it.second }})", w < 0.25f)
        }
        for (a in sleepers) {
            val w = worstSpeedStep(a, plans[0], opts(calm = 1f))
            assertTrue("${a.id} calm: speed changed by $w a second in one frame", w < 0.25f)
        }
    }

    @Test
    fun `woken by a question, the mouth follows the voice and nothing else`() {
        // Speaking straight after waking: the mouth is exactly the voice's
        // shape times how much it is speaking, as ever - the wake-up never
        // touches it - and its talking gestures wait until it is over.
        val voice = floatArrayOf(0.7f, 0.3f, 0.2f)
        for (a in sleepers) for (f in 0..40) {
            val x = f * 0.05f
            val got = a.uniforms(a.pose(FaceState.SPEAKING, FaceState.STANDBY, x, 170f + x, 0.4f, CritterPose.Look(), asleep9, opts()), voice)
            val was = a.uniforms(a.plain(FaceState.SPEAKING, FaceState.STANDBY, x, 170f + x, 0.4f, asleep9, opts()), voice)
            for (i in 0 until 3) assertEquals("${a.id}: mouth[$i] at $x s", was.getValue("uMouth")[i], got.getValue("uMouth")[i], 1e-6f)
        }
    }
}
