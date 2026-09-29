package com.jarvis.client

import com.jarvis.client.face.CritterPose
import com.jarvis.client.face.CritterShaders
import com.jarvis.client.face.Faces
import com.jarvis.client.face.MonkeyPose
import com.jarvis.client.face.OtterPose
import com.jarvis.client.face.OwlPose
import com.jarvis.client.face.RobotPose
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
            "monkey" -> MonkeyPose::pose
            "robot" -> RobotPose::pose
            else -> error("no Kotlin pose for '$species' - add one, or drop it from tools/gen_critters.py")
        }

    private fun overlayOf(species: String): (FloatArray, Float, Float, Float) -> FloatArray = when (species) {
        "redpanda" -> CritterPose::overlay
        "pygmyowl" -> OwlPose::overlay
        "seaotter" -> OtterPose::overlay
        "monkey" -> MonkeyPose::overlay
        "robot" -> RobotPose::overlay
        else -> error("no Kotlin pose for '$species'")
    }

    private fun uniformsOf(species: String): (FloatArray, FloatArray?) -> Map<String, FloatArray> = when (species) {
        "redpanda" -> CritterPose::uniforms
        "pygmyowl" -> OwlPose::uniforms
        "seaotter" -> OtterPose::uniforms
        "monkey" -> MonkeyPose::uniforms
        "robot" -> RobotPose::uniforms
        else -> error("no Kotlin pose for '$species'")
    }

    @Test
    fun `every pose matches the desktop's`() {
        val species = cases.map { it.jsonObject["species"]!!.jsonPrimitive.content }.toSet()
        assertEquals("the fixture should cover every animal and the robot", setOf("redpanda", "pygmyowl", "seaotter", "monkey", "robot"), species)
        assertTrue("the fixture should cover every state", cases.size >= 4 * 8 * 5)
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
                optsOf(opts),
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

    /**
     * The slow wander that replaced the shared sines (noise, breathWave) and the
     * host's look-ahead for phrase ends (aheadStep) give the phone's numbers the
     * desktop's, at moments inside one period, past it and days on.
     */
    @Test
    fun `the slow wander and the look-ahead match the desktop's`() {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("critter-drift-golden.json")) {
            "critter-drift-golden.json is missing from test resources - run tools/gen_critters.py"
        }.bufferedReader().readText()
        val o = Json.parseToJsonElement(text).jsonObject
        for (c in o["noise"]!!.jsonArray) {
            val n = c.jsonObject
            val got = CritterPose.noise(n["t"]!!.jsonPrimitive.float, n["seed"]!!.jsonPrimitive.float.toInt(), n["scale"]!!.jsonPrimitive.float)
            assertEquals("noise $n", n["v"]!!.jsonPrimitive.float, got, 2e-3f)
        }
        for (c in o["breath"]!!.jsonArray) {
            val n = c.jsonObject
            val got = CritterPose.breathWave(n["t"]!!.jsonPrimitive.float, n["k"]!!.jsonPrimitive.float, n["seed"]!!.jsonPrimitive.float.toInt())
            assertEquals("breath $n", n["v"]!!.jsonPrimitive.float, got, 2e-3f)
        }
        val lim = o["ahead_limits"]!!.jsonObject
        assertEquals(lim["MIN"]!!.jsonPrimitive.float, CritterPose.Ahead.MIN, 0f)
        assertEquals(lim["MAX"]!!.jsonPrimitive.float, CritterPose.Ahead.MAX, 0f)
        var rec: CritterPose.AheadRec? = null
        for (c in o["ahead"]!!.jsonArray) {
            val a = c.jsonObject
            val next = a["next"]!!.let { if (it is kotlinx.serialization.json.JsonNull) null else it.jsonPrimitive.float }
            rec = CritterPose.aheadStep(rec, a["dt"]!!.jsonPrimitive.float, next)
            assertEquals("ahead n $a", a["n"]!!.jsonPrimitive.float.toInt(), rec.n)
            val due = a["due"]!!.let { if (it is kotlinx.serialization.json.JsonNull) null else it.jsonPrimitive.float }
            if (due == null) assertEquals("ahead due $a", null, rec.due) else assertEquals("ahead due $a", due, rec.due!!, 1e-4f)
        }
    }

    /** The host's opts as the fixture gives them (the desktop's keys, the switches by their ids). */
    private fun optsOf(o: kotlinx.serialization.json.JsonObject?): CritterPose.Opts {
        fun f(k: String, d: Float) = o?.get(k)?.jsonPrimitive?.float ?: d
        fun i(k: String, d: Int) = o?.get(k)?.jsonPrimitive?.content?.toFloat()?.toInt() ?: d
        return CritterPose.Opts(
            calm = f("calm", 0f), serious = f("serious", 0f), still = f("still", 0f),
            variety = f("variety", 0f), cute = f("cute_moments", f("cute", 1f)),
            nods = f("nods", 1f), focusBuddy = f("focus_buddy", 1f), acks = f("acks", 1f), petting = f("petting", 1f),
            focus = f("focus", 0f), pet = f("pet", 0f), petX = f("petX", 0f), petDir = f("petDir", 0f),
            hello = f("hello", 1f), goodbye = f("goodbye", 0f),
            heard = f("heard", CritterPose.NEVER), heardN = i("heardN", -1),
            phraseEnd = f("phraseEnd", CritterPose.NEVER), phraseN = i("phraseN", -1),
            ackNod = f("ackNod", CritterPose.NEVER), ackGlow = f("ackGlow", CritterPose.NEVER),
            focusEnd = f("focusEnd", CritterPose.NEVER),
            attention = f("attention", 1f), phraseDue = f("phraseDue", Float.NaN),
        )
    }

    /**
     * Whether an idle happening is playing - what the frame pacer on both
     * apps reads to draw a stretch or a scratch at the full rate. The
     * desktop's busy(state, t), four times a second over 320 s and a day on.
     */
    @Test
    fun `the phone knows when a happening plays, as the desktop does`() {
        val text = checkNotNull(javaClass.classLoader?.getResourceAsStream("critter-busy-golden.json")) {
            "critter-busy-golden.json is missing from test resources - run tools/gen_critters.py"
        }.bufferedReader().readText()
        val o = Json.parseToJsonElement(text).jsonObject
        assertEquals(o["happening_s"]!!.jsonPrimitive.float, CritterPose.HAPPENING_S, 0f)
        val times = o["times"]!!.jsonArray.map { it.jsonPrimitive.float }
        val busy = o["busy"]!!.jsonObject
        val phone = mapOf<String, (FaceState, Float, CritterPose.Opts?) -> Boolean>(
            "redpanda" to { s, t, o -> CritterPose.busy(s, t, null, o) }, "pygmyowl" to { s, t, o -> OwlPose.busy(s, t, null, o) },
            "seaotter" to { s, t, o -> OtterPose.busy(s, t, null, o) }, "monkey" to { s, t, o -> MonkeyPose.busy(s, t, null, o) },
            "robot" to { s, t, o -> RobotPose.busy(s, t, null, o) },
        )
        assertEquals(phone.keys, busy.keys)
        val idle0 = o["busy_att0"]!!.jsonObject
        assertEquals(phone.keys, idle0.keys)
        for ((sp, fn) in phone) {
            val want = busy[sp]!!.jsonPrimitive.content
            val got = times.joinToString("") { if (fn(FaceState.IDLE, it, null)) "1" else "0" }
            assertEquals("$sp: busy differs from the desktop's", want, got)
            // ...and while the owner is not using Jarvis (`attention` 0): about one in four.
            val want0 = idle0[sp]!!.jsonPrimitive.content
            val notUsed = CritterPose.Opts(attention = 0f)
            assertEquals("$sp: busy with attention 0 differs from the desktop's", want0,
                times.joinToString("") { if (fn(FaceState.IDLE, it, notUsed)) "1" else "0" })
            for (st in FaceState.entries) if (st != FaceState.IDLE) assertTrue("$sp busy in $st", times.none { fn(st, it, null) })
        }
        // And whether one of its own talking gestures plays - what the host
        // checks before it hands the pose Jarvis's phrase ends mid-answer.
        assertEquals(o["gesture_s"]!!.jsonPrimitive.float, CritterPose.GESTURE_S, 0f)
        val gest = o["gesturing"]!!.jsonObject
        val phoneG = mapOf<String, (Float) -> Boolean>(
            "redpanda" to CritterPose::gesturing, "pygmyowl" to OwlPose::gesturing, "seaotter" to OtterPose::gesturing,
            "monkey" to MonkeyPose::gesturing, "robot" to RobotPose::gesturing,
        )
        assertEquals(phoneG.keys, gest.keys)
        for ((sp, fn) in phoneG) {
            val want = gest[sp]!!.jsonPrimitive.content
            assertEquals("$sp: gesturing differs from the desktop's", want, times.joinToString("") { if (fn(it)) "1" else "0" })
            assertTrue("$sp: never gestures", '1' in want)
            assertTrue("$sp: always gestures", '0' in want)
        }
        // And whether a moment the host hands in plays (a stroke, a fact's
        // nod, the glow, the focus stretch) - the frame pacer draws those at
        // the full rate too.
        val moments = o["moments"]!!.jsonArray
        assertTrue(moments.size > 20)
        for (c in moments) {
            val m = c.jsonObject
            val st = state(m["state"]!!.jsonPrimitive.content)
            val want = m["busy"]!!.jsonPrimitive.content.toBooleanStrict()
            assertEquals("momentsBusy $m", want, CritterPose.momentsBusy(st, optsOf(m["opts"]?.jsonObject)))
        }
    }

    @Test
    fun `each shader declares every uniform its pose sets`() {
        // A uniform set but never declared would throw at draw time, on the
        // phone, in front of the owner. Cheaper to find it here.
        val host = setOf("uHot", "uCool", "uYaw", "uPit", "uTime", "uZoom", "uCenter", "uR", "uPx", "uNoShadow")
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
            "MONKEY" to (CritterShaders.MONKEY to MonkeyPose.uniforms(
                MonkeyPose.pose(FaceState.IDLE, FaceState.IDLE, 5f, 1f, 0f),
            ).keys),
            "ROBOT" to (CritterShaders.ROBOT to RobotPose.uniforms(
                RobotPose.pose(FaceState.IDLE, FaceState.IDLE, 5f, 1f, 0f),
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
        Animal("monkey", { s, p, since -> MonkeyPose.pose(s, p, since, 2f, 0.3f) }, MonkeyPose::uniforms, MonkeyPose::speakingWeight),
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
        "monkey" to { s: FaceState, p: FaceState, since: Float, t: Float, h: CritterPose.Hist ->
            MonkeyPose.uniforms(MonkeyPose.pose(s, p, since, t, 0.3f, hist = h)) },
        "robot" to { s: FaceState, p: FaceState, since: Float, t: Float, h: CritterPose.Hist ->
            RobotPose.uniforms(RobotPose.pose(s, p, since, t, 0.3f, hist = h)) },
    )

    // The eyelids and pupils may be quick (a blink, a glance) and the water's
    // ripple phase wraps round by design; everything else must glide. (The
    // robot's eyelids are uEyes' first two, and the gleam crossing its visor
    // - uFins' last - starts at one side and is gone at the other.)
    private fun glides(name: String, i: Int) =
        !(name == "uFace" && i < 2) && !(name == "uEyes" && i < 2) && name != "uLook" &&
            !(name == "uWater" && i == 1) && !(name == "uFins" && i == 3)

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
                for (name in listOf("uPawL", "uPawR", "uWingL0", "uWingR0", "uHandL", "uHandR", "uHeadR0", "uHeadR1")) {
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
    fun `all four animals and the robot are offered`() {
        for (id in listOf("redpanda", "pygmyowl", "seaotter", "monkey", "robot")) {
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
        "monkey" to { s: FaceState, t: Float, o: CritterPose.Opts ->
            MonkeyPose.uniforms(MonkeyPose.pose(s, s, 99f, t, 0.3f, opts = o)) },
        "robot" to { s: FaceState, t: Float, o: CritterPose.Opts ->
            RobotPose.uniforms(RobotPose.pose(s, s, 99f, t, 0.3f, opts = o)) },
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
            "monkey" to { s: FaceState, p: FaceState, since: Float ->
                MonkeyPose.overlay(MonkeyPose.pose(s, p, since, 30f, 0f)) },
            "robot" to { s: FaceState, p: FaceState, since: Float ->
                RobotPose.overlay(RobotPose.pose(s, p, since, 30f, 0f)) },
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
        Sleeper("monkey", MonkeyPose::pose, { s, p, since, t, amp, h, o ->
            CritterPose.blend(MonkeyPose::stateTargets, MonkeyPose.HALF, s, p, since, t, amp, CritterPose.Look(), h, o)
        }, MonkeyPose::uniforms, MonkeyPose::overlay),
        Sleeper("robot", RobotPose::pose, { s, p, since, t, amp, h, o ->
            CritterPose.blend(RobotPose::stateTargets, RobotPose.HALF, s, p, since, t, amp, CritterPose.Look(), h, o)
        }, RobotPose::uniforms, RobotPose::overlay),
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
    /**
     * The biggest difference between two poses' uniforms, leaving out the
     * eyelids - and, with [vine], how far back the monkey's vine is (and its
     * hand on it, and so that arm's elbow). The monkey sleeps sitting ON its vine and hangs from it
     * awake, so the plain settling alone would draw the vine straight through
     * it; it always sends the vine behind while it passes (critter-monkey.js's
     * wakeSleep). That is part of the move, not an extra, so it stays under
     * calm, serious and still, and waking into waiting on you.
     */
    private fun bodyGap(a: Map<String, FloatArray>, b: Map<String, FloatArray>, vine: Boolean = false): Float {
        var worst = 0f
        for ((name, v) in a) for (i in v.indices) {
            if (name == "uFace" && i < 2) continue
            // (The robot's eyes are all of uEyes and uEyes2, where they look
            // (uLook: painted on its visor, not a turning eyeball) and the
            // light they throw, uOrbGlow: their shape and glow are the eyes too.)
            if (name == "uEyes" || name == "uEyes2" || (a.containsKey("uEyes") && (name == "uOrbGlow" || name == "uLook"))) continue
            if (vine && ((name == "uVine" && i == 1) || (name == "uHandA" && i == 2) || name == "uElbA")) continue
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
            val eyes = eyesOf(woke(0.3f))[0]
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
            val half = eyesOf(a.uniforms(nod(0.4f), null))[0]
            assertTrue("${a.id}: eyes ${half} 0.4 s into nodding off", half in 0.3f..1.0f)
            assertEquals("${a.id}: eyes open at 3 s", 0f, eyesOf(a.uniforms(nod(3.0f), null))[0], 1e-6f)
        }
    }

    @Test
    fun `waking into waiting on you or an error, only the eyes open`() {
        for (a in sleepers) for (s in listOf(FaceState.APPROVAL, FaceState.ERROR, FaceState.BANKED)) {
            for (f in 0..50) {
                val x = f * 0.05f
                val got = a.uniforms(a.pose(s, FaceState.STANDBY, x, 160f + x, ampOf(s), CritterPose.Look(), asleep9, opts()), null)
                val was = a.uniforms(a.plain(s, FaceState.STANDBY, x, 160f + x, ampOf(s), asleep9, opts()), null)
                val gap = bodyGap(got, was, a.id == "monkey")
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
                    val gap = bodyGap(got, was, a.id == "monkey")
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
            for (i in voiceOf(was).indices) assertEquals("${a.id}: mouth[$i] at $x s", voiceOf(was)[i], voiceOf(got)[i], 1e-6f)
        }
    }

    // --- the new behaviours (critter-pose.js "New behaviours") ------------

    /** Every animal's pose and uniforms, with the host's opts. */
    private fun u(a: Sleeper, s: FaceState, since: Float, t: Float, o: CritterPose.Opts, prev: FaceState = s,
                  h: CritterPose.Hist = CritterPose.Hist(), mouth: FloatArray? = null) =
        a.uniforms(a.pose(s, prev, since, t, ampOf(s), CritterPose.Look(), h, o), mouth)
    /**
     * The eyes (open left, open right, ...), the voice's mark (the mouth -
     * or, on the robot, which has none, its eyes' pulse) and the orb's glow
     * (the robot's eyes') of any face.
     */
    private fun eyesOf(u: Map<String, FloatArray>) = u["uFace"] ?: u.getValue("uEyes")
    private fun voiceOf(u: Map<String, FloatArray>) = u["uMouth"] ?: floatArrayOf(u.getValue("uEyes2")[3])
    private fun glowOf(u: Map<String, FloatArray>) = if (u.containsKey("uEyes")) u.getValue("uEyes2")[2] else u.getValue("uOrbGlow")[0]
    private fun gap(a: Map<String, FloatArray>, b: Map<String, FloatArray>): Float {
        var worst = 0f
        for ((name, v) in a) for (i in v.indices) worst = maxOf(worst, abs(v[i] - b.getValue(name)[i]))
        return worst
    }
    private val awakeStates = listOf(FaceState.IDLE, FaceState.LISTENING, FaceState.THINKING, FaceState.SPEAKING)
    /** Every input a host may pass, at once, part way through each. */
    private fun everything(base: CritterPose.Opts = opts()) = base.copy(
        variety = 1f, focus = 0.7f, pet = 0.8f, petX = 0.4f, petDir = 0.5f, goodbye = 0.3f,
        heard = 0.4f, heardN = 2, phraseEnd = 0.5f, phraseN = 3, ackNod = 0.4f, ackGlow = 0.8f, focusEnd = 1.1f,
    )

    @Test
    fun `left out, the new inputs and switches change nothing`() {
        // The owner's switches are on unless given, and do nothing without
        // something happening: so a host passing none of the new inputs draws
        // exactly what it drew before (the fixture holds the rest).
        val off = CritterPose.Opts(cute = 0f, nods = 0f, focusBuddy = 0f, acks = 0f, petting = 0f)
        for (a in sleepers) for (s in FaceState.entries) for (f in 0 until 120) {
            val t = 40f + f * 0.37f
            assertEquals("${a.id} $s at $t", 0f, gap(u(a, s, 99f, t, opts()), u(a, s, 99f, t, off)), 0f)
        }
    }

    @Test
    fun `still, serious and the waiting and wrong looks switch every new behaviour off`() {
        for (a in sleepers) for (s in awakeStates) for (f in 0 until 20) {
            val t = 60f + f * 0.29f
            for (w in listOf(opts(still = 1f), opts(serious = 1f))) {
                // (hello and goodbye are the host's cross-fade under these: the pose plays none of it)
                val g = gap(u(a, s, 20f, t, w), u(a, s, 20f, t, everything(w)))
                assertTrue("${a.id} $s: a new behaviour moved it by $g under $w", g < 1e-5f)
            }
        }
        // Waiting on you, something wrong, asleep, dozing: none of them (the
        // arrival's reaction is over after its first 1.3 s).
        for (a in sleepers) for (s in listOf(FaceState.APPROVAL, FaceState.ERROR, FaceState.STANDBY, FaceState.BANKED)) {
            val o = everything().copy(goodbye = 0f)
            for (f in 0 until 20) {
                val t = 60f + f * 0.29f
                val g = gap(u(a, s, 20f, t, opts()), u(a, s, 20f, t, o))
                assertTrue("${a.id} $s: moved $g", g < 1e-5f)
            }
        }
    }

    @Test
    fun `calm makes the new behaviours smaller, not bigger`() {
        for (a in sleepers) for (s in awakeStates) {
            var full = 0f
            var calm = 0f
            for (f in 0 until 40) {
                val t = 70f + f * 0.13f
                // (The focus session too, since 2026-09-28: its pose is taken
                // smaller under calm, like every other behaviour; only the
                // happenings it takes away stay away, calm or not.)
                full = maxOf(full, bodyGap(u(a, s, 20f, t, opts()), u(a, s, 20f, t, everything().copy(goodbye = 0f))))
                calm = maxOf(calm, bodyGap(u(a, s, 20f, t, opts(calm = 1f)), u(a, s, 20f, t, everything(opts(calm = 1f)).copy(goodbye = 0f))))
            }
            assertTrue("${a.id} $s: calm $calm against $full", calm <= full * 0.75f + 1e-4f)
        }
    }

    @Test
    fun `the mouth is never touched by a new behaviour`() {
        val voice = floatArrayOf(0.6f, 0.4f, 0.2f)
        for (a in sleepers) for (f in 0 until 60) {
            val t = 80f + f * 0.11f
            val plain = voiceOf(u(a, FaceState.SPEAKING, 20f, t, opts(), mouth = voice))
            val busy = voiceOf(u(a, FaceState.SPEAKING, 20f, t, everything(), mouth = voice))
            for (i in plain.indices) assertEquals("${a.id}: mouth[$i]", plain[i], busy[i], 1e-6f)
        }
    }

    @Test
    fun `a shuffle bag never deals the same one twice running`() {
        for (salt in listOf(74, 154, 234, 118)) {
            var last = -1
            val seen = IntArray(3)
            for (n in 0 until 3000) {
                val k = CritterPose.bagKind(n, 3, salt)
                assertTrue("salt $salt: kind $k twice running at $n", k != last)
                seen[k]++
                last = k
            }
            assertTrue("salt $salt: a kind never came up", seen.all { it > 800 })
        }
    }

    @Test
    fun `the pause finder counts a pause after talking, never closer than its gap`() {
        // Talk 1.2 s, quiet 0.5 s, over and over, at 60 frames a second.
        var rec: CritterPose.PauseRec? = null
        val at = ArrayList<Float>()
        var lastN = 0
        for (f in 0 until 60 * 30) {
            val t = f / 60f
            val level = if ((t % 1.7f) < 1.2f) 0.4f else 0.01f
            rec = CritterPose.pauseStep(rec, 1f / 60f, level, CritterPose.Pause.NOD_QUIET, CritterPose.Pause.NOD_GAP)
            if (rec.n != lastN) { at.add(t); lastN = rec.n; assertEquals(0f, rec.ago, 0f) }
        }
        assertTrue("too few pauses: $at", at.size >= 7)
        for (i in 1 until at.size) assertTrue("pauses ${at[i - 1]} and ${at[i]} too close", at[i] - at[i - 1] >= CritterPose.Pause.NOD_GAP - 1e-3f)
        // Silence, or a cough too short to be talking, is never a pause.
        var q: CritterPose.PauseRec? = null
        for (f in 0 until 600) q = CritterPose.pauseStep(q, 1f / 60f, if (f % 100 < 10) 0.5f else 0f, 0.3f, 3f)
        assertEquals(0, q!!.n)
    }

    @Test
    fun `Jarvis's phrase ends are found in the short quiet between fast sentences, not in a consonant`() {
        // Voice-speed check (2026-09-28): at the normal pace and faster two
        // sentences back to back leave about 0.1 s of quiet in the level;
        // PHRASE_QUIET was 0.15 s and found none of them.
        assertEquals(0.05f, CritterPose.Pause.PHRASE_QUIET, 0f)
        fun run(talkS: Float, quietS: Float): Int {
            var rec: CritterPose.PauseRec? = null
            val period = ((talkS + quietS) * 60).toInt()
            for (f in 0 until 60 * 20) {
                val level = if (f % period < talkS * 60) 0.4f else 0.02f
                rec = CritterPose.pauseStep(rec, 1f / 60f, level, CritterPose.Pause.PHRASE_QUIET, CritterPose.Pause.PHRASE_GAP)
            }
            return rec!!.n
        }
        // 2.4 s sentences, 0.1 s apart: one gesture per sentence (20 s / 2.5 s).
        assertEquals(8, run(2.4f, 0.1f))
        // A 30 ms silent hold (a "b" or "t") inside the words is never a phrase end.
        assertEquals(0, run(0.4f, 0.03f))
    }

    @Test
    fun `a listening nod is small and plays once, all three kinds`() {
        for (a in sleepers) for (n in 0 until 3) {
            var most = 0f
            var any = 0f
            for (f in 0 until 90) {
                val x = f / 60f
                val o = opts().copy(heard = x, heardN = n)
                val p0 = u(a, FaceState.LISTENING, 20f, 30f + x, opts())
                val p1 = u(a, FaceState.LISTENING, 20f, 30f + x, o)
                val g = gap(p0, p1)
                any = maxOf(any, g)
                for (nm in listOf("uHeadR0", "uHeadR1", "uHeadR2")) for (i in 0 until 3) most = maxOf(most, abs(p0.getValue(nm)[i] - p1.getValue(nm)[i]))
                if (x > CritterPose.NOD_S) assertTrue("${a.id}: nod $n still playing at $x", g < 1e-5f)
            }
            assertTrue("${a.id}: nod $n did nothing", any > 0.005f)
            // Small: the head turns at most about 3 degrees (0.06 of its turn).
            assertTrue("${a.id}: nod $n turned the head by $most", most < 0.07f)
            // The switch takes it away.
            val sw = gap(u(a, FaceState.LISTENING, 20f, 30.4f, opts()),
                u(a, FaceState.LISTENING, 20f, 30.4f, opts().copy(heard = 0.4f, heardN = n, nods = 0f)))
            assertTrue("${a.id}: nodded with the switch off", sw < 1e-5f)
        }
    }

    @Test
    fun `with the host's phrase ends, gestures come only at them`() {
        // phraseN 0: the host counts phrases but none has ended - no gesture
        // at all, where the random ones would have played.
        for (a in sleepers) {
            var random = 0f
            var none = 0f
            for (f in 0 until 1200) {
                val t = 100f + f / 10f
                val still = u(a, FaceState.SPEAKING, 20f, t, opts(calm = 0f).copy(phraseN = 0))
                val talk = u(a, FaceState.SPEAKING, 20f, t, opts())
                random = maxOf(random, gap(still, talk))
                none = maxOf(none, gap(still, u(a, FaceState.SPEAKING, 20f, t, opts(still = 0f).copy(phraseN = 5, phraseEnd = 9f))))
            }
            assertTrue("${a.id}: the random gestures never played ($random)", random > 0.01f)
            assertTrue("${a.id}: a gesture long after a phrase end ($none)", none < 1e-5f)
        }
        // At a phrase end one plays (most phrase ends; one near a look is let go).
        for (a in sleepers) {
            var played = 0
            for (n in 1..60) {
                val t = 100f + n * 3.1f
                val g = gap(u(a, FaceState.SPEAKING, 20f, t, opts().copy(phraseN = 0)),
                    u(a, FaceState.SPEAKING, 20f, t, opts().copy(phraseN = n, phraseEnd = 0.5f)))
                if (g > 0.005f) played++
            }
            // (Sixty, not twenty: about half are let go for a look, and twenty
            // was too few to tell a face that never gestures from bad luck.)
            assertTrue("${a.id}: only $played of 60 phrase ends had a gesture", played >= 22)
        }
    }

    @Test
    fun `a saved fact nods, a ready answer swells the orb - not while waiting on you`() {
        for (a in sleepers) {
            val glow = glowOf(u(a, FaceState.IDLE, 20f, 30f, opts().copy(ackGlow = 0.9f))) -
                glowOf(u(a, FaceState.IDLE, 20f, 30f, opts()))
            assertTrue("${a.id}: the orb did not swell ($glow)", glow > 0.2f)
            val nod = gap(u(a, FaceState.IDLE, 20f, 30f, opts()), u(a, FaceState.IDLE, 20f, 30f, opts().copy(ackNod = 0.4f)))
            assertTrue("${a.id}: no nod ($nod)", nod > 0.01f)
            for (s in listOf(FaceState.APPROVAL, FaceState.ERROR, FaceState.STANDBY)) {
                val g = gap(u(a, s, 20f, 30f, opts()), u(a, s, 20f, 30f, opts().copy(ackNod = 0.4f, ackGlow = 0.9f)))
                assertTrue("${a.id} $s: acknowledged ($g)", g < 1e-5f)
            }
            val sw = gap(u(a, FaceState.IDLE, 20f, 30f, opts()), u(a, FaceState.IDLE, 20f, 30f, opts().copy(ackNod = 0.4f, ackGlow = 0.9f, acks = 0f)))
            assertTrue("${a.id}: acknowledged with the switch off", sw < 1e-5f)
        }
    }

    @Test
    fun `in a focus session it looks about far less, and stretches at the end`() {
        for (a in sleepers) {
            fun looksIn(o: CritterPose.Opts): Int {
                var n = 0
                var last = u(a, FaceState.IDLE, 99f, 1000f, o).getValue("uLook")
                for (f in 1 until 6000) {
                    val now = u(a, FaceState.IDLE, 99f, 1000f + f / 10f, o).getValue("uLook")
                    if (abs(now[0] - last[0]) + abs(now[1] - last[1]) > 0.15f) n++
                    last = now
                }
                return n
            }
            val normal = looksIn(opts())
            val focus = looksIn(opts().copy(focus = 1f))
            assertTrue("${a.id}: $focus looks in focus against $normal", focus * 2 < normal)
            val stretch = gap(u(a, FaceState.IDLE, 20f, 30f, opts()), u(a, FaceState.IDLE, 20f, 30f, opts().copy(focusEnd = 1.2f)))
            assertTrue("${a.id}: no stretch at the end of a session ($stretch)", stretch > 0.02f)
            val sw = gap(u(a, FaceState.IDLE, 20f, 30f, opts()), u(a, FaceState.IDLE, 20f, 30f, opts().copy(focus = 1f, focusEnd = 1.2f, focusBuddy = 0f)))
            assertTrue("${a.id}: focus buddy with the switch off", sw < 1e-5f)
        }
    }

    /** The biggest difference between two poses' head turns (the head's rotation). */
    private fun headGap(a: Map<String, FloatArray>, b: Map<String, FloatArray>): Float {
        var worst = 0f
        for (name in listOf("uHeadR0", "uHeadR1", "uHeadR2")) for (i in 0 until 3) {
            worst = maxOf(worst, abs(a.getValue(name)[i] - b.getValue(name)[i]))
        }
        return worst
    }

    @Test
    fun `calm makes the focus buddy's pose smaller too`() {
        // The owner's rule: calm makes every behaviour smaller. The focus pose
        // (the owl's half turn to watch the work, the panda's look into its
        // orb...) used to be drawn in full under calm - the owl's head turned
        // 20 to 43 degrees. Measured against the still animal at the same
        // moment, the head turns clearly less under calm (the pose is taken
        // at 40 percent), while the happenings stay away all the same.
        for (a in sleepers) {
            var full = 0f
            var calm = 0f
            for (f in 0 until 80) {
                val t = 30f + f * 0.53f
                val rest = u(a, FaceState.IDLE, 20f, t, opts(still = 1f))
                full = maxOf(full, headGap(rest, u(a, FaceState.IDLE, 20f, t, opts().copy(focus = 1f))))
                calm = maxOf(calm, headGap(rest, u(a, FaceState.IDLE, 20f, t, opts(calm = 1f).copy(focus = 1f))))
            }
            assertTrue("${a.id}: the focus pose under calm turned the head $calm against $full", calm < 0.75f * full)
        }
    }

    @Test
    fun `waiting on you or at an error, a face switch is only the cross-fade`() {
        // The owner's rule: approval and error are serious moments, and under
        // a serious moment a face switch is a quick gentle cross-fade - no
        // bow, no ducking out of view, no bounce.
        for (a in sleepers) for (s in listOf(FaceState.APPROVAL, FaceState.ERROR)) {
            val rest = u(a, s, 20f, 30f, opts())
            for (w in listOf(0.2f, 0.5f, 0.9f)) {
                val g = gap(rest, u(a, s, 20f, 30f, opts().copy(goodbye = w)))
                val h = gap(rest, u(a, s, 20f, 30f, opts().copy(hello = w)))
                assertTrue("${a.id} $s: the goodbye moved it by $g at $w", g < 1e-5f)
                assertTrue("${a.id} $s: the hello moved it by $h at $w", h < 1e-5f)
            }
            assertEquals("$s", 0.3f, CritterPose.switchAlpha(opts().copy(goodbye = 0.7f), s), 1e-5f)
            assertEquals("$s", 0.25f, CritterPose.switchAlpha(opts().copy(hello = 0.25f), s), 1e-5f)
        }
        // Awake, the animal plays its own piece and is drawn whole; the old
        // one-argument call answers as it always did.
        assertEquals(1f, CritterPose.switchAlpha(opts().copy(goodbye = 0.7f), FaceState.IDLE), 0f)
        assertEquals(1f, CritterPose.switchAlpha(opts().copy(goodbye = 0.7f)), 0f)
    }

    @Test
    fun `stroked, it leans toward the hand and its eyes soften`() {
        for (a in sleepers) {
            val left = u(a, FaceState.IDLE, 20f, 30f, opts().copy(pet = 1f, petX = -1f))
            val right = u(a, FaceState.IDLE, 20f, 30f, opts().copy(pet = 1f, petX = 1f))
            assertTrue("${a.id}: leans the same way whichever side the hand is", gap(left, right) > 0.02f)
            // (At a moment its eyes are open - not mid-blink.)
            val t = (0 until 200).map { 30f + it * 0.05f }.first { eyesOf(u(a, FaceState.IDLE, 20f, it, opts()))[0] > 0.9f }
            val eyes = eyesOf(u(a, FaceState.IDLE, 20f, t, opts().copy(pet = 1f)))[0]
            val open = eyesOf(u(a, FaceState.IDLE, 20f, t, opts()))[0]
            assertTrue("${a.id}: eyes $eyes against $open", eyes < open - 0.2f)
            val sw = gap(u(a, FaceState.IDLE, 20f, 30f, opts()), u(a, FaceState.IDLE, 20f, 30f, opts().copy(pet = 1f, petX = 1f, petting = 0f)))
            assertTrue("${a.id}: petted with the switch off", sw < 1e-5f)
        }
    }

    @Test
    fun `the cute moments take turns, only after it has rested, and the switch stops them`() {
        val salts = mapOf("redpanda" to (76 to floatArrayOf(7f, 5f)), "pygmyowl" to (156 to floatArrayOf(8.2f, 3f)),
            "seaotter" to (236 to floatArrayOf(6.8f, 6.5f)), "monkey" to (121 to floatArrayOf(5.5f, 4.4f)),
            "robot" to (251 to floatArrayOf(3.3f, 3.2f)))
        for ((id, sl) in salts) {
            val kinds = ArrayList<Int>()
            var was = false
            for (k in 0 until 4096 * 20) {
                val c = CritterPose.cuteAt(k / 20f, 1e6f, sl.first, sl.second)
                if (c[0] >= 0f && !was) kinds.add(c[0].toInt())
                was = c[0] >= 0f
            }
            assertEquals("$id: one cute moment every 256 s", 16, kinds.size)
            for (i in 1 until kinds.size) assertTrue("$id: the same cute moment twice running", kinds[i] != kinds[i - 1])
        }
        for (a in sleepers) {
            val start = mapOf("redpanda" to 102.082f, "pygmyowl" to 173.461f, "seaotter" to 101.685f, "monkey" to 87.92f,
                "robot" to 130.566f).getValue(a.id)
            val t = start + 2.6f
            val on = gap(u(a, FaceState.IDLE, 1e6f, t, opts()), u(a, FaceState.IDLE, 1e6f, t, opts().copy(cute = 0f)))
            assertTrue("${a.id}: the cute moment did nothing ($on)", on > 0.02f)
            val fresh = gap(u(a, FaceState.IDLE, 100f, t, opts()), u(a, FaceState.IDLE, 100f, t, opts().copy(cute = 0f)))
            assertTrue("${a.id}: a cute moment before it had rested", fresh < 1e-5f)
        }
    }

    @Test
    fun `goodbye takes it out of view and hello brings it back`() {
        for (a in sleepers) {
            val rest = u(a, FaceState.IDLE, 20f, 30f, opts())
            val gone = u(a, FaceState.IDLE, 20f, 30f, opts().copy(goodbye = 1f))
            val coming = u(a, FaceState.IDLE, 20f, 30f, opts().copy(hello = 0f))
            // The whole animal moves well over a picture's height away (1 is
            // half the picture): the monkey on its vine, the others' bodies.
            val key = if (a.id == "monkey") "uVine" else "uBodyPos"
            val i = if (a.id == "monkey") 0 else 1
            for (w in listOf(gone, coming)) assertTrue("${a.id}: only ${abs(w.getValue(key)[i] - rest.getValue(key)[i])} away",
                abs(w.getValue(key)[i] - rest.getValue(key)[i]) > (if (a.id == "seaotter") 0.5f else 1.5f))
            assertEquals("${a.id}: hello done is its own pose", 0f, gap(rest, u(a, FaceState.IDLE, 20f, 30f, opts().copy(hello = 1f))), 0f)
            // Under calm the pose plays none of it: the host cross-fades.
            assertTrue("${a.id}: moved under calm", gap(u(a, FaceState.IDLE, 20f, 30f, opts(calm = 1f)),
                u(a, FaceState.IDLE, 20f, 30f, opts(calm = 1f).copy(goodbye = 0.7f))) < 1e-5f)
        }
        assertEquals(1f, CritterPose.switchAlpha(opts().copy(goodbye = 0.7f)), 0f)
        assertEquals(0.3f, CritterPose.switchAlpha(opts(calm = 1f).copy(goodbye = 0.7f)), 1e-5f)
        assertEquals(0.25f, CritterPose.switchAlpha(opts(still = 1f).copy(hello = 0.25f)), 1e-5f)
    }

    @Test
    fun `an arrival reacts a little, then is still - never the same reaction twice running`() {
        for (a in sleepers) for (s in listOf(FaceState.APPROVAL, FaceState.ERROR)) {
            val h = CritterPose.Hist(prevAmp = 0f)
            val o = opts().copy(variety = 1f)
            val early = (1..12).maxOf { f -> gap(u(a, s, f * 0.1f, 40f + f * 0.1f, opts(), FaceState.IDLE, h), u(a, s, f * 0.1f, 40f + f * 0.1f, o, FaceState.IDLE, h)) }
            val body = (1..12).maxOf { f -> bodyGap(u(a, s, f * 0.1f, 40f + f * 0.1f, opts(), FaceState.IDLE, h), u(a, s, f * 0.1f, 40f + f * 0.1f, o, FaceState.IDLE, h)) }
            assertTrue("${a.id} $s: no reaction ($early)", early > 0.005f)
            assertTrue("${a.id} $s: too big a reaction ($body)", body < 0.1f)
            for (f in 0 until 10) {
                val x = 1.35f + f * 0.3f
                assertEquals("${a.id} $s: still reacting at $x", 0f,
                    gap(u(a, s, x, 40f + x, opts(), FaceState.IDLE, h), u(a, s, x, 40f + x, o, FaceState.IDLE, h)), 1e-6f)
            }
        }
        // Back to back (waiting on you, idle a few seconds, waiting on you again): never the same one.
        for (s in listOf(FaceState.APPROVAL, FaceState.ERROR)) for (k in 0 until 400) {
            val t = 20f + k * 1.37f
            val back = listOf(CritterPose.Change(FaceState.IDLE, 3f, 0f), CritterPose.Change(s, 2f, 0f), CritterPose.Change(FaceState.IDLE, 9f, 0f))
            val now = CritterPose.arriveKind(s, back, 0, 0.2f, t, 255)
            val before = CritterPose.arriveKind(s, back, 2, 2f, t - 0.2f - 3f, 255)
            assertTrue("$s at $t: reaction $now twice running", now != before)
        }
    }

    /** The largest change of speed in one frame at 240 a second, over a run of the host's opts and states. */
    private fun worstRun(a: Sleeper, secs: Float, t0: Float, since0: Float, plan: (Float) -> Pair<FaceState, CritterPose.Opts>): Float {
        val dt = 1f / 240f
        val frames = ArrayList<Map<String, FloatArray>>()
        var worst = 0f
        for (k in 0 until (secs * 240).toInt()) {
            val x = k * dt
            val (s, o) = plan(x)
            val now = u(a, s, since0 + x, t0 + x, o)
            for ((name, v) in now) for (i in v.indices) assertTrue("${a.id}: $name[$i] is not a number at $x", v[i].isFinite())
            frames.add(now)
            if (frames.size >= 3) {
                val (p2, p1, p0) = Triple(frames[0], frames[1], frames[2])
                for ((name, v) in p0) for (i in v.indices) {
                    if (!glides(name, i)) continue
                    val dv = abs((v[i] - p1.getValue(name)[i]) - (p1.getValue(name)[i] - p2.getValue(name)[i])) / dt
                    worst = maxOf(worst, dv)
                }
                frames.removeAt(0)
            }
        }
        return worst
    }

    @Test
    fun `the new behaviours never change speed suddenly, and are always numbers`() {
        fun eased(x: Float, a: Float, b: Float) = CritterPose.ease((x - a) / 0.8f) * (1f - CritterPose.ease((x - b) / 0.8f))
        val runs = listOf<Triple<String, Float, (Float) -> Pair<FaceState, CritterPose.Opts>>>(
            Triple("nods", 8f) { x -> FaceState.LISTENING to opts().copy(heard = if (x < 1f) CritterPose.NEVER else (x - 1f) % 3f, heardN = ((x - 1f) / 3f).toInt()) },
            Triple("phrases", 9f) { x -> FaceState.SPEAKING to opts().copy(phraseEnd = if (x < 0.5f) CritterPose.NEVER else (x - 0.5f) % 2.2f, phraseN = ((x - 0.5f) / 2.2f).toInt() + 1) },
            Triple("focus", 10f) { x -> FaceState.IDLE to opts().copy(focus = eased(x, 0.5f, 6f), focusEnd = if (x < 6.8f) CritterPose.NEVER else x - 6.8f) },
            Triple("acks", 4f) { x -> FaceState.IDLE to opts().copy(ackNod = if (x < 0.5f) CritterPose.NEVER else x - 0.5f, ackGlow = if (x < 1.5f) CritterPose.NEVER else x - 1.5f) },
            Triple("pet", 6f) { x -> FaceState.IDLE to opts().copy(pet = eased(x, 0.5f, 4f), petX = 0.5f, petDir = kotlin.math.sin(x * 2f)) },
            Triple("goodbye", 1.5f) { x -> FaceState.IDLE to opts().copy(goodbye = CritterPose.clamp(x - 0.2f, 0f, 1f)) },
            Triple("hello", 1.5f) { x -> FaceState.IDLE to opts().copy(hello = CritterPose.clamp(x - 0.2f, 0f, 1f)) },
            Triple("variety", 16f) { x -> (if (x < 8f) FaceState.LISTENING else FaceState.THINKING) to opts().copy(variety = 1f) },
        )
        for (a in sleepers) for ((name, secs, plan) in runs) {
            // (The variety run crosses from listening to thinking without the
            // host's history: that jump is the settling's to smooth, not this.)
            val w = if (name == "variety") maxOf(worstRun(a, 7.9f, 2000f, 20f, plan), worstRun(a, 7.9f, 2008.1f, 20f) { plan(it + 8.1f) })
                    else worstRun(a, secs, 60f, 20f, plan)
            // A goodbye and a hello move the whole animal out of view in about
            // half a second - quickly, but eased: still no step.
            val limit = if (name == "goodbye" || name == "hello") 0.6f else 0.25f
            assertTrue("${a.id} $name: speed changed by $w a second in one frame", w < limit)
        }
        // The cute moments, from end to end.
        val starts = mapOf("redpanda" to listOf(102.082f, 408.591f), "pygmyowl" to listOf(173.461f, 313.491f),
            "seaotter" to listOf(101.685f, 403.501f), "monkey" to listOf(87.92f, 426.323f),
            "robot" to listOf(130.566f, 452.031f))
        for (a in sleepers) for (st in starts.getValue(a.id)) {
            val w = worstRun(a, 9f, st - 0.5f, 1e6f) { FaceState.IDLE to opts() }
            assertTrue("${a.id} cute at $st: speed changed by $w a second in one frame", w < 0.25f)
        }
    }
}
