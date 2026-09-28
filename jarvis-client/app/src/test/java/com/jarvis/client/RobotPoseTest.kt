package com.jarvis.client

import com.jarvis.client.face.CritterPose
import com.jarvis.client.face.CritterShaders
import com.jarvis.client.face.RobotPose
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/**
 * The robot (the owner's fifth face, 2026-09-28) keeps the same promises as
 * the animals - CritterPoseTest checks its answers against the desktop's and
 * runs the checks every face shares - and these are the ones that are its
 * own: it has no mouth, so its EYES follow the real voice; it zips round
 * inside its own space and never out of it; its two cute moments take turns
 * and never come at the wrong moment; it waves only at rest; and its hello
 * and goodbye.
 */
class RobotPoseTest {

    private fun opts(
        calm: Float = 0f, serious: Float = 0f, still: Float = 0f, cute: Float = 1f,
        focus: Float = 0f, hello: Float = 1f, goodbye: Float = 0f, variety: Float = 1f,
    ) = CritterPose.Opts(calm = calm, serious = serious, still = still, cute = cute, focus = focus, hello = hello, goodbye = goodbye, variety = variety)

    private fun u(s: FaceState, t: Float, since: Float = 999f, o: CritterPose.Opts = opts(), mouth: FloatArray? = null,
                  prev: FaceState = s, hist: CritterPose.Hist = CritterPose.Hist()) =
        RobotPose.uniforms(RobotPose.pose(s, prev, since, t, 0.3f, hist = hist, opts = o), mouth)

    // The eyelids, where the eyes look and the gleam's place may be quick; everything else glides.
    private fun glides(name: String, i: Int) = !(name == "uEyes" && i < 2) && name != "uLook" && !(name == "uFins" && i == 3)

    @Test
    fun `the shader declares every uniform the pose sets`() {
        val host = setOf("uHot", "uCool", "uYaw", "uPit", "uTime", "uZoom", "uCenter", "uR", "uPx", "uNoShadow")
        for (n in u(FaceState.IDLE, 1f).keys + host) {
            assertTrue("CritterShaders.ROBOT has no uniform named $n", Regex("""uniform\s+\w+\s+$n\s*;""").containsMatchIn(CritterShaders.ROBOT))
        }
        // No mouth and no orb: it never sets the animals' mouth.
        assertTrue("the robot has no mouth uniform", "uMouth" !in u(FaceState.SPEAKING, 1f).keys)
    }

    @Test
    fun `its eyes pulse with the real voice, and only with it`() {
        val voice = floatArrayOf(0.8f, 0.5f, 0.2f)
        val pulse = { m: Map<String, FloatArray> -> m.getValue("uEyes2")[3] }
        // A typed answer, Quiet, an answer kept on screen: no voice, no pulse.
        assertEquals(0f, pulse(u(FaceState.SPEAKING, 5f, mouth = null)), 0f)
        // Speaking with a voice: the opening (and a little of its width), clamped.
        assertEquals(0.95f, pulse(u(FaceState.SPEAKING, 5f, mouth = voice)), 1e-5f)
        assertEquals(1f, pulse(u(FaceState.SPEAKING, 5f, mouth = floatArrayOf(1f, 1f, 0f))), 0f)
        // Any other state: none, whatever the track says.
        for (s in FaceState.entries) if (s != FaceState.SPEAKING) assertEquals("$s", 0f, pulse(u(s, 5f, mouth = voice)), 0f)
        // Leaving speaking it eases away with how much the pose is speaking.
        var last = 2f
        for (step in 0..11) {
            val p = RobotPose.pose(FaceState.IDLE, FaceState.SPEAKING, step * 0.05f, 3f, 0f)
            val w = RobotPose.speakingWeight(p)
            assertEquals(0.95f * w, RobotPose.uniforms(p, voice).getValue("uEyes2")[3], 1e-5f)
            assertTrue("the pulse came back up", w <= last); last = w
        }
    }

    @Test
    fun `a change of state never jumps`() {
        val states = FaceState.entries
        for (a in states) for (b in states) {
            if (a == b) continue
            var last: Map<String, FloatArray>? = null
            for (f in -3..120) {
                val since = f / 60f
                val now = if (since < 0f) u(a, 40f + since, 9f) else u(b, 40f + since, since, prev = a, hist = CritterPose.Hist(prevAmp = 0.3f))
                val prev = last
                if (prev != null) for ((name, v) in now) for (i in v.indices) {
                    assertTrue("$name[$i] is not a number, $a -> $b", v[i].isFinite())
                    if (!glides(name, i)) continue
                    assertTrue("$name[$i] jumped, $a -> $b at $since s", abs(v[i] - prev.getValue(name)[i]) < 0.12f)
                }
                last = now
            }
        }
    }

    // The robot's camera and the corners of its outline (robot.sksl), for "in the frame".
    private fun screen(x: Float, y: Float, z: Float): FloatArray {
        val cp = cos(0.10f)
        val sp = sin(0.10f)
        val d = 3.25f
        val ry0 = y - (-0.05f + d * sp)
        val rz0 = z - (-d * cp)
        val dy = ry0 * cp + rz0 * sp
        val dz = -ry0 * sp + rz0 * cp
        return floatArrayOf(3.1f * x / dz, 3.1f * dy / dz)
    }
    private fun column(m: Map<String, FloatArray>, name: String, j: Int) =
        floatArrayOf(m.getValue(name + "0")[j], m.getValue(name + "1")[j], m.getValue(name + "2")[j])
    /** How near the frame's edge the robot comes (1: on it), its mittens and pods counted generously. */
    private fun edge(m: Map<String, FloatArray>): Float {
        val neck = m.getValue("uNeck")
        val hx = column(m, "uHeadR", 0)
        val hy = column(m, "uHeadR", 1)
        fun head(x: Float, y: Float) = floatArrayOf(neck[0] + hx[0] * x + hy[0] * y, neck[1] + hx[1] * x + hy[1] * y, neck[2] + hx[2] * x + hy[2] * y)
        var e = 0f
        for (q in listOf(head(0f, 0.81f), head(-0.7f, 0.3f), head(0.7f, 0.3f), head(-0.62f, 0.69f), head(0.62f, 0.69f))) {
            val s = screen(q[0], q[1], q[2]); e = max(e, max(abs(s[0]), abs(s[1])))
        }
        val b = m.getValue("uBodyPos")
        val s0 = screen(b[0], b[1] - 0.3f, b[2]); e = max(e, abs(s0[1]))
        for (h in listOf(m.getValue("uHandL"), m.getValue("uHandR"))) {
            val s = screen(h[0], h[1], h[2]); e = max(e, max(abs(s[0]) + 0.1f, abs(s[1]) + 0.1f))
        }
        return e
    }

    @Test
    fun `it zips round inside its own space, and never out of it`() {
        // An hour at rest, 20 frames a second: it stays inside the picture,
        // zips now and then (about one every two minutes), and
        // each zip is quick but eased - at most about 2.4 heights a second.
        var worst = 0f
        var zips = 0
        var moving = false
        var prev: Map<String, FloatArray>? = null
        var fastest = 0f
        for (f in 0 until 3600 * 20) {
            val t = 1000f + f / 20f
            val m = u(FaceState.IDLE, t, 999f + f / 20f)
            worst = max(worst, edge(m))
            val p = prev
            if (p != null) {
                val a = m.getValue("uBodyPos")
                val b = p.getValue("uBodyPos")
                val v = kotlin.math.sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1]) + (a[2] - b[2]) * (a[2] - b[2])) * 20f
                fastest = max(fastest, v)
                // (A zip takes it back into the picture: that is how one is counted.)
                if (a[2] > 0.3f && !moving) zips++
                moving = a[2] > 0.3f
            }
            prev = m
        }
        assertTrue("it came ${worst} of the way to the frame's edge", worst < 0.99f)
        assertTrue("$zips zips in an hour", zips in 20..40)
        assertTrue("it moved at ${fastest} a second", fastest < 3.4f)
    }

    @Test
    fun `no zip under Still, calm, a serious moment, a focus session or a petting hand, nor outside idle`() {
        for (o in listOf(opts(still = 1f), opts(calm = 1f), opts(serious = 1f), opts(focus = 1f),
                         CritterPose.Opts(pet = 1f, variety = 1f))) {
            var lo = Float.MAX_VALUE
            var hi = -Float.MAX_VALUE
            for (f in 0 until 900 * 10) {
                val z = u(FaceState.IDLE, 1000f + f / 10f, 999f, o).getValue("uBodyPos")[2]
                lo = minOf(lo, z); hi = maxOf(hi, z)
            }
            assertTrue("it zipped (depth moved ${hi - lo}) under $o", hi - lo < 0.02f)
        }
        for (s in FaceState.entries) if (s != FaceState.IDLE) {
            var hi = 0f
            for (f in 0 until 900 * 5) hi = max(hi, abs(u(s, 1000f + f / 5f).getValue("uBodyPos")[2]))
            assertTrue("$s: it zipped", hi < 0.06f)
        }
        // And not in its first ten seconds at rest.
        for (f in 0 until 4000) {
            val t = 1000f + f / 10f
            assertTrue("a zip in the first 10 s", abs(u(FaceState.IDLE, t, since = (t % 10f)).getValue("uBodyPos")[2]) < 0.02f)
        }
    }

    /** How high the right mitten is, above the middle of the body, over [secs] at 10 frames a second. */
    private fun highestRightHand(s: FaceState, o: CritterPose.Opts, t0: Float = 0f, secs: Int = 3600): Float {
        var hi = -1f
        for (f in 0 until secs * 10) hi = max(hi, handUp(u(s, t0 + f / 10f, 999f + f / 10f, o)))
        return hi
    }
    private fun handUp(m: Map<String, FloatArray>) = m.getValue("uHandR")[1] - m.getValue("uBodyPos")[1]

    @Test
    fun `its two cute moments take turns, and only when it may`() {
        // Over an hour at rest: a wave (the right mitten well up) comes up,
        // and between two waves there is a polish (the mitten at the visor
        // and the gleam across it).
        val kinds = mutableListOf<Int>()
        var inMoment = false
        for (f in 0 until 3600 * 10) {
            val t = f / 10f
            val m = u(FaceState.IDLE, t, 999f + t)
            val waving = m.getValue("uHandR")[1] > 0.0f && m.getValue("uHandR")[0] > 0.5f
            val polishing = m.getValue("uFins")[3] >= 0f
            if ((waving || polishing) && !inMoment) { kinds.add(if (polishing) 1 else 0); inMoment = true }
            if (!waving && !polishing && m.getValue("uHandR")[1] < -0.4f) inMoment = false
        }
        val collapsed = kinds.fold(mutableListOf<Int>()) { acc, k -> if (acc.lastOrNull() != k) acc.add(k); acc }
        assertTrue("only ${collapsed.size} cute moments in an hour: $kinds", collapsed.size >= 8)
        for (i in 1 until collapsed.size) assertTrue("two alike running: $collapsed", collapsed[i] != collapsed[i - 1])
        // None with the switch off, under Still or a serious moment; never at
        // an approval or an error - there it never waves at all.
        val rest = handUp(u(FaceState.IDLE, 0f, 0f, opts(cute = 0f)))
        for (o in listOf(opts(cute = 0f), opts(still = 1f), opts(serious = 1f))) {
            assertTrue("a wave with $o", highestRightHand(FaceState.IDLE, o) < rest + 0.25f)
        }
        for (s in listOf(FaceState.APPROVAL, FaceState.ERROR)) {
            assertTrue("$s: its mitten went up", highestRightHand(s, opts(), secs = 1200) < rest + 0.15f)
        }
        // Calm makes a wave smaller, not gone.
        val full = highestRightHand(FaceState.IDLE, opts(), secs = 700)
        val calm = highestRightHand(FaceState.IDLE, opts(calm = 1f), secs = 700)
        assertTrue("calm: $calm against $full", calm < full && calm > rest + 0.1f)
    }

    @Test
    fun `waiting on you and something going wrong are still, after one small reaction`() {
        for (s in listOf(FaceState.APPROVAL, FaceState.ERROR)) {
            val first = u(s, 200f)
            for (f in 1..100) {
                val now = u(s, 200f + f / 10f)
                for (name in listOf("uHandL", "uHandR", "uHeadR0", "uHeadR1", "uBodyR0")) for (i in 0 until 3) {
                    val d = abs(first.getValue(name)[i] - now.getValue(name)[i])
                    assertTrue("$s: $name[$i] moved $d", d < 0.05f)
                }
                // Only its hover: a few hundredths up and down.
                assertTrue("$s: it floated", abs(first.getValue("uBodyPos")[1] - now.getValue("uBodyPos")[1]) < 0.02f)
            }
        }
    }

    @Test
    fun `hello and goodbye go out of view at the ends, and do nothing when left out`() {
        val plain = u(FaceState.IDLE, 30f)
        // Left out (hello 1, goodbye 0): exactly the plain pose.
        val same = u(FaceState.IDLE, 30f, o = opts(hello = 1f, goodbye = 0f))
        for ((n, v) in plain) for (i in v.indices) assertEquals("$n[$i]", v[i], same.getValue(n)[i], 0f)
        // Goodbye done, hello not started: it is above the picture.
        for (o in listOf(opts(goodbye = 1f), opts(hello = 0f))) {
            val b = u(FaceState.IDLE, 30f, o = o).getValue("uBodyPos")
            val bottom = screen(b[0], b[1] - 0.3f, b[2])[1]
            assertTrue("still in view with $o (its bottom at $bottom)", bottom > 1.02f)
        }
        // Under Still, calm or serious the pose plays none of it - the host
        // cross-fades the two faces instead (CritterPose.switchAlpha).
        for (o in listOf(opts(still = 1f, goodbye = 0.6f), opts(calm = 1f, hello = 0.3f), opts(serious = 1f, goodbye = 1f))) {
            val base = u(FaceState.IDLE, 30f, o = o.copy(hello = 1f, goodbye = 0f))
            val got = u(FaceState.IDLE, 30f, o = o)
            for ((n, v) in base) for (i in v.indices) assertEquals("$o changed $n[$i]", v[i], got.getValue(n)[i], 1e-6f)
        }
        // Stepped through at 60 frames a second, neither jumps.
        for (which in 0..1) {
            var last: Map<String, FloatArray>? = null
            for (f in 0..60) {
                val k = f / 60f
                val now = u(FaceState.IDLE, 30f + k, o = if (which == 0) opts(goodbye = k) else opts(hello = k))
                val p = last
                if (p != null && k < 0.95f) for ((name, v) in now) for (i in v.indices) {
                    if (!glides(name, i)) continue
                    assertTrue("$name[$i] jumped at $k ($which)", abs(v[i] - p.getValue(name)[i]) < 0.25f)
                }
                last = now
            }
        }
    }

    @Test
    fun `asleep, its eyes are a dim line and only its hover moves`() {
        val m = u(FaceState.STANDBY, 30f, o = opts())
        assertEquals(0f, m.getValue("uEyes")[0], 0f)
        assertTrue("its eyes glow ${m.getValue("uEyes2")[2]} asleep", m.getValue("uEyes2")[2] < 0.5f)
        var lo = Float.MAX_VALUE
        var hi = -Float.MAX_VALUE
        for (f in 0 until 1200) {
            val y = u(FaceState.STANDBY, 500f + f / 10f).getValue("uHeadR0")[2]
            lo = minOf(lo, y); hi = maxOf(hi, y)
        }
        assertTrue("asleep, its head turned ${hi - lo}", hi - lo < 0.03f)
        val ov = RobotPose.overlay(RobotPose.pose(FaceState.STANDBY, FaceState.STANDBY, 99f, 30f, 0f))
        assertTrue("its Zs start beside the top of its head (${ov[1]}, ${ov[2]})", ov[0] == 1f && abs(ov[1]) < 0.9f && ov[2] in 0.2f..0.9f)
    }

    @Test
    fun `busy while a zip or a cute moment plays, and only at rest`() {
        var seen = 0
        for (f in 0 until 3600 * 4) {
            val t = f / 4f
            if (RobotPose.busy(FaceState.IDLE, t, 999f + t, opts())) seen++
            for (s in FaceState.entries) if (s != FaceState.IDLE) assertTrue("busy in $s", !RobotPose.busy(s, t, 999f + t, opts()))
        }
        assertTrue("busy $seen quarter-seconds of an hour", seen in 200..8000)
    }
}
