package com.jarvis.client

import androidx.compose.ui.graphics.Color
import com.jarvis.client.face.Arc
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.CritterPose
import com.jarvis.client.face.DimRule
import com.jarvis.client.face.FaceClock
import com.jarvis.client.face.FaceFrame
import com.jarvis.client.face.FaceHost
import com.jarvis.client.face.FaceLink
import com.jarvis.client.face.FaceWords
import com.jarvis.client.face.FlashGovernor
import com.jarvis.client.face.MonkeyPose
import com.jarvis.client.face.OtterPose
import com.jarvis.client.face.OwlPose
import com.jarvis.client.face.RobotPose
import com.jarvis.client.face.Spec
import com.jarvis.client.face.Swatch
import com.jarvis.client.face.ZsRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.round
import kotlin.math.sin

/**
 * The face shell's small rules (face/FaceShellRules.kt), and the FaceHost
 * clocks that use one of them: how an animal is dimmed, what TalkBack says
 * when Jarvis cannot be reached, when the face shows it cannot be reached,
 * and that keeping the clocks small never makes the face jump.
 */
class FaceShellRulesTest {

    // --- dimming the animals (DimRule) ---------------------------------------

    private val ground = Color(0.02f, 0.03f, 0.05f)
    private fun rgb(c: Color) = floatArrayOf(c.red, c.green, c.blue)

    @Test
    fun `an animal is dimmed by each state's own dim, toward the ground`() {
        val fur = floatArrayOf(0.80f, 0.35f, 0.12f, 1f)
        val g = rgb(ground)
        for (s in FaceState.values()) {
            val dim = Spec.transformFor(s).dim
            val m = DimRule.matrix(dim, ground.red, ground.green, ground.blue)
            if (dim >= 1f) {
                assertNull("$s is not dimmed, so no filter", m)
                continue
            }
            assertNotNull("$s is dimmed ($dim)", m)
            val out = DimRule.applyTo(m!!, fur)
            for (i in 0..2) {
                // FaceView's `dimmed`: mix(ground, colour, dim).
                assertEquals("$s channel $i", g[i] + (fur[i] - g[i]) * dim, out[i], 1e-5f)
            }
            assertEquals("$s leaves coverage alone", 1f, out[3], 0f)
        }
    }

    @Test
    fun `standby and banked dim the animal as much as the desktop's table says`() {
        // jarvis-desktop/src/faces.html, the state transforms: standby 0.6,
        // banked 0.45. The same numbers every other face is dimmed by.
        assertEquals(0.6f, Spec.transformFor(FaceState.STANDBY).dim, 0f)
        assertEquals(0.45f, Spec.transformFor(FaceState.BANKED).dim, 0f)
        val white = floatArrayOf(1f, 1f, 1f, 1f)
        val black = Color(0f, 0f, 0f)
        for ((s, dim) in listOf(FaceState.STANDBY to 0.6f, FaceState.BANKED to 0.45f)) {
            val m = DimRule.matrix(Spec.transformFor(s).dim, black.red, black.green, black.blue)!!
            // On a black ground a dimmed white is exactly `dim` - not 0.99 of
            // idle, which is what dimming only the orb and rim gave.
            assertEquals(dim, DimRule.applyTo(m, white)[0], 1e-5f)
        }
    }

    @Test
    fun `the soft outline dims exactly like a solid pixel`() {
        // A pixel the animal only part covers: composited over the ground,
        // the filtered one must land where the dimmed picture would.
        val dim = Spec.transformFor(FaceState.BANKED).dim
        val m = DimRule.matrix(dim, ground.red, ground.green, ground.blue)!!
        val g = rgb(ground)
        val colour = floatArrayOf(0.9f, 0.5f, 0.2f)
        for (a in floatArrayOf(0f, 0.1f, 0.4f, 0.75f, 1f)) {
            val filtered = DimRule.applyTo(m, floatArrayOf(colour[0], colour[1], colour[2], a))
            for (i in 0..2) {
                val undimmed = g[i] * (1f - a) + colour[i] * a
                val want = g[i] + (undimmed - g[i]) * dim
                val got = g[i] * (1f - a) + filtered[i] * a
                assertEquals("coverage $a channel $i", want, got, 1e-5f)
            }
        }
    }

    @Test
    fun `full brightness and a bad dim set no filter at all`() {
        assertNull(DimRule.matrix(1f, 0f, 0f, 0f))
        assertNull(DimRule.matrix(Float.NaN, 0f, 0f, 0f))
    }

    // --- what TalkBack says (FaceWords) -------------------------------------

    @Test
    fun `a link that is down never says notes are saved for later`() {
        for (s in FaceState.values()) {
            assertEquals("$s offline", "Jarvis isn't connected", FaceWords.spoken(s, offline = true))
        }
        // Connected, each state still says what it did.
        assertEquals("Jarvis has notes saved for later", FaceWords.spoken(FaceState.BANKED, offline = false))
        assertEquals("Jarvis is on standby and will not speak", FaceWords.spoken(FaceState.STANDBY, offline = false))
        assertEquals("Jarvis is waiting for your decision", FaceWords.spoken(FaceState.APPROVAL, offline = false))
    }

    // --- when the face shows Jarvis is out of reach (FaceLink) --------------

    @Test
    fun `a healthy link shows the face as it is`() {
        for (s in FaceState.values()) {
            assertEquals(FaceLink.Shown(s, offline = false), FaceLink.shown(s, cutSinceMs = 0L, nowMs = 5_000_000L))
        }
        assertEquals(0L, FaceLink.graceLeftMs(0L, 5_000_000L))
    }

    @Test
    fun `a cut link holds the face through the grace, then shows standby with the ring`() {
        val cut = 1_000_000L
        val inGrace = FaceLink.shown(FaceState.THINKING, cut, cut + FaceLink.GRACE_MS - 1)
        assertEquals(FaceLink.Shown(FaceState.THINKING, offline = false), inGrace)
        assertEquals(1L, FaceLink.graceLeftMs(cut, cut + FaceLink.GRACE_MS - 1))
        for (s in FaceState.values()) {
            for (later in longArrayOf(FaceLink.GRACE_MS, 3 * 60_000L, 24 * 3_600_000L)) {
                // Never ERROR (a sleeping PC is not a broken one) and never
                // BANKED (it has no notes to show) - the old ladder.
                assertEquals("$s after ${later}ms", FaceLink.Shown(FaceState.STANDBY, offline = true), FaceLink.shown(s, cut, cut + later))
            }
        }
    }

    @Test
    fun `an approval face is never shown on a cut link, not even in the grace`() {
        // Its buttons are blocked the moment the link is cut (rule 4).
        val cut = 1_000_000L
        assertEquals(FaceLink.Shown(FaceState.STANDBY, offline = true), FaceLink.shown(FaceState.APPROVAL, cut, cut))
        assertEquals(FaceLink.Shown(FaceState.STANDBY, offline = true), FaceLink.shown(FaceState.APPROVAL, cut, cut + 1_000L))
    }

    @Test
    fun `a wall clock set backwards never stretches the grace`() {
        val cut = 1_000_000L
        assertEquals(FaceLink.GRACE_MS, FaceLink.graceLeftMs(cut, cut - 3_600_000L))
        assertEquals(0L, FaceLink.graceLeftMs(cut, cut + 10 * FaceLink.GRACE_MS))
    }

    // --- keeping the clocks small (FaceClock, FaceHost) ---------------------

    private fun FaceHost.step(dt: Float, s: FaceState): FaceFrame {
        advance(dt, s, null, null, Bindings.DEFAULTS, Arc)
        return snapshot()
    }

    @Test
    fun `the wrap unit is the animals' own period, so an animal never jumps`() {
        assertEquals(CritterPose.PERIOD.toDouble(), FaceClock.WRAP_S, 0.0)
        // The approval knock (1.6 s) comes round exactly too.
        val knocks = FaceClock.WRAP_S / 1.6
        assertEquals(round(knocks), knocks, 1e-9)
        // 1280 whole turns, and a multiple of 20 so the faces that turn at
        // 0.3, 0.35, 1.1, 1.8 or 2.4 times the angle land on whole turns too.
        // 1.3: the animals' orb swirl (`uTime * 1.3` in their shaders, uTime
        // being the angle), so the orb does not jump either.
        for (k in doubleArrayOf(1.0, 0.3, 0.35, 1.1, 1.3, 1.8, 2.4)) {
            val turns = FaceClock.ANGLE_WRAP * k / (2 * Math.PI)
            assertEquals("x$k", round(turns), turns, 1e-6)
        }
    }

    @Test
    fun `a face left on screen for nine hours wraps without a jump in anything it reads`() {
        val host = FaceHost()
        val dt = 0.25f
        // THINKING: Arc turns fastest there (1.35), so its angle passes the
        // angle's own limit inside the run as well.
        var before = host.step(dt, FaceState.THINKING)
        var tWraps = 0
        var angleWraps = 0
        // Past the hard limit, where the host wraps while being watched.
        val steps = ((FaceClock.HARD_S + 60.0) / dt).toInt()
        repeat(steps) { i ->
            val after = host.step(dt, FaceState.THINKING)
            // How long thinking has been showing: the clock's wrap moves the
            // moment it began with it, so this just keeps counting.
            assertEquals("hitch at step $i", before.hitchPhase + dt, after.hitchPhase, 5e-3f)
            // The face's clock goes on by dt, or by dt less whole periods.
            val dT = (after.t - before.t).toDouble()
            if (abs(dT - dt) > 5e-3) {
                val periods = (dt - dT) / FaceClock.WRAP_S
                assertEquals("t wrap at step $i", round(periods), periods, 1e-5)
                tWraps++
            }
            // The spin goes on smoothly: where it would have been, on the
            // circle - and at 0.3 times the angle, as some faces turn.
            val turn = dt * Arc.speedFor(FaceState.THINKING)
            if (abs(after.angle - before.angle - turn) > 1e-2f) {
                val want = before.angle + turn
                assertEquals("angle wrap at step $i", sin(want), sin(after.angle), 2e-2f)
                assertEquals("angle wrap at step $i", cos(want), cos(after.angle), 2e-2f)
                assertEquals("x0.3 at step $i", sin(want * 0.3f), sin(after.angle * 0.3f), 2e-2f)
                angleWraps++
            }
            before = after
        }
        val c = host.clocksForTest()
        assertTrue("the real clock wrapped: ${c[0]}", c[0] in 0.0..FaceClock.WRAP_S)
        assertEquals("the face clock wrapped once", 1, tWraps)
        assertTrue("the spin wrapped ($angleWraps)", angleWraps >= 1)
        assertTrue("clocks small again: ${c.toList()}", c.all { abs(it) < FaceClock.HARD_S })
        // After the wrap, a frame's time is precise again: 1/120 s steps
        // arrive as 1/120 s, not rounded to a coarser float step.
        var f0 = host.step(1f / 120f, FaceState.THINKING)
        repeat(240) {
            val f1 = host.step(1f / 120f, FaceState.THINKING)
            assertEquals(1f / 120f, f1.t - f0.t, 1e-4f)
            f0 = f1
        }
    }

    @Test
    fun `coming back to the screen wraps unseen, and nothing the face reads changes`() {
        val host = FaceHost()
        val steps = ((FaceClock.SOFT_S + 100.0) / 0.25).toInt()
        var a = host.step(0.25f, FaceState.STANDBY)
        repeat(steps) { a = host.step(0.25f, FaceState.STANDBY) }
        host.onLoopStart()
        val b = host.snapshot()
        assertEquals(a.hitchPhase, b.hitchPhase, 5e-3f)
        val periods = (a.t - b.t) / FaceClock.WRAP_S
        assertTrue("the face clock wrapped ($periods)", periods >= 1.0)
        assertEquals(round(periods), periods, 1e-5)
        assertEquals(a.state, b.state)
        // A short break changes nothing.
        val fresh = FaceHost()
        repeat(240) { fresh.step(0.25f, FaceState.IDLE) }
        val c0 = fresh.clocksForTest()
        fresh.onLoopStart()
        assertEquals(c0.toList(), fresh.clocksForTest().toList())
    }

    /** Each animal's (and the robot's) shader uniforms for a frame, the way CritterFaces works them out. */
    private fun animals(f: FaceFrame): Map<String, Map<String, FloatArray>> {
        val hist = CritterPose.Hist(prev2 = f.prevState2, gap = f.prevGap, prevAmp = f.prevAmp, prevAmp2 = f.prevAmp2)
        return mapOf(
            "redpanda" to CritterPose.uniforms(CritterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist), f.mouth),
            "pygmyowl" to OwlPose.uniforms(OwlPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist), f.mouth),
            "seaotter" to OtterPose.uniforms(OtterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist), f.mouth),
            "monkey" to MonkeyPose.uniforms(MonkeyPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist), f.mouth),
            "robot" to RobotPose.uniforms(RobotPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist), f.mouth),
        )
    }

    @Test
    fun `a wrap changes nothing in any animal's pose`() {
        // The wrap FaceHost really does (at a multiple of CritterPose.PERIOD),
        // on a host part way through a change of state, so the melt and the
        // history are in play too - not just the clock.
        for ((from, to) in listOf(
            FaceState.STANDBY to FaceState.SPEAKING,
            FaceState.IDLE to FaceState.APPROVAL,
            FaceState.THINKING to FaceState.BANKED,
        )) {
            val host = FaceHost()
            repeat(((FaceClock.SOFT_S + 250.0) / 0.25).toInt()) { host.step(0.25f, from) }
            repeat(9) { host.step(1f / 30f, to) }
            val a = host.snapshot()
            host.onLoopStart()
            val b = host.snapshot()
            assertTrue("$from -> $to: wrapped", a.t - b.t >= FaceClock.WRAP_S - 1.0)
            val pa = animals(a)
            val pb = animals(b)
            // FaceHost keeps its clock in a Double but hands it on as a Float, so
            // before the wrap the pose sees the time (and the time since the
            // change) rounded to a step of Math.ulp(a.t) - half a millisecond at
            // 4096 s - and after it, almost exactly. Mid-blink an eyelid moves
            // about 1% per millisecond (the robot's did, at this very instant,
            // and failed CI), so allow what one rounding step moves each value
            // and nothing more: a real jump at the wrap is far bigger than that.
            val step = Math.ulp(a.t)
            val pn = animals(a.copy(t = a.t + step, hitchPhase = a.hitchPhase + step))
            for ((id, u) in pa) for ((name, v) in u) for (i in v.indices) {
                if (name == "uWater" && i == 1) continue   // a phase: the same modulo a full turn
                val rounding = abs(pn.getValue(id).getValue(name)[i] - v[i])
                assertEquals("$id $from -> $to: $name[$i]", v[i], pb.getValue(id).getValue(name)[i], 2e-3f + rounding)
            }
            // The orb's swirl (the shaders' uTime * 1.3, uTime = the angle).
            assertEquals(sin(a.angle * 1.3f), sin(b.angle * 1.3f), 2e-3f)
        }
    }

    @Test
    fun `the flash governor keeps counting across a wrap`() {
        val white = Swatch(Color(1f, 1f, 1f), Color(1f, 1f, 1f))
        val black = Swatch(Color(0f, 0f, 0f), Color(0f, 0f, 0f))
        val g = FlashGovernor()
        // Flashing at 10 Hz spends the budget: the colour is held.
        var t = 5_000f
        var shown = white
        repeat(10) { i ->
            shown = g.govern(if (i % 2 == 0) white else black, t)
            t += 0.1f
        }
        // The clock moves back 4096 s. Two seconds on, the old transitions
        // have aged out and a change is allowed again - unshifted, they would
        // sit "in the future" and hold the colour for good.
        g.shift(4096f)
        t -= 4096f
        t += 2f
        val next = if (shown == white) black else white
        assertEquals(next, g.govern(next, t))
    }

    @Test
    fun `the sleeping Zs fade out while not connected, and back, in the standby colour lightened`() {
        val host = FaceHost()
        fun step(offline: Boolean): FaceFrame {
            host.advance(0.05f, FaceState.STANDBY, null, null, Bindings.DEFAULTS, Arc, offline = offline)
            return host.snapshot()
        }
        var f = step(false)
        repeat(40) { f = step(false) }
        assertEquals("shown while online", 1f, f.zsW, 0f)
        repeat(4) { f = step(true) }
        assertTrue("faded, not cut (${f.zsW})", f.zsW > 0f && f.zsW < 1f)
        repeat(20) { f = step(true) }
        assertEquals("none while not connected", 0f, f.zsW, 0f)
        repeat(20) { f = step(false) }
        assertEquals("back when the link is", 1f, f.zsW, 0f)
        // Standby's neutral grey (neutral-3, #46566A), 0.35 of the way to white.
        val want = floatArrayOf(0x46 / 255f, 0x56 / 255f, 0x6A / 255f).map { it + (1f - it) * CritterPose.Zs.LIGHTEN }
        val got = rgb(f.zsTint)
        for (i in 0..2) assertEquals(want[i], got[i], 4e-3f)   // 8 bits a channel
    }

    // --- the Zs and the dim follow the pose's own sleep (ZsRule, DimRule.sleep)

    /** The panda's pose for a frame, exactly as CritterFaces works it out. */
    private fun pandaPose(f: FaceFrame): FloatArray {
        val hist = CritterPose.Hist(prev2 = f.prevState2, gap = f.prevGap, prevAmp = f.prevAmp, prevAmp2 = f.prevAmp2, past = f.past)
        return CritterPose.pose(f.state, f.prevState, f.hitchPhase, f.t, f.amp, hist = hist, opts = CritterPose.Opts(f.calmW, f.seriousW, f.stillW))
    }

    /** How asleep the panda's pose is (its overlay's `asleep`, what the Zs fade with). */
    private fun pandaAsleep(f: FaceFrame) = CritterPose.overlay(pandaPose(f))[0]

    /** The dim the panda is drawn with, exactly as CritterFaces works it out. */
    private fun pandaDim(f: FaceFrame) = DimRule.sleep(f.awakeDim, pandaAsleep(f))

    @Test
    fun `the Zs' offline weight comes back only on standby, and is held while awake`() {
        assertEquals(0.4f, ZsRule.step(0.5f, offline = true, standby = true, k = 0.1f), 1e-6f)
        assertEquals(0.4f, ZsRule.step(0.5f, offline = true, standby = false, k = 0.1f), 1e-6f)
        assertEquals(0.6f, ZsRule.step(0.5f, offline = false, standby = true, k = 0.1f), 1e-6f)
        assertEquals(0.5f, ZsRule.step(0.5f, offline = false, standby = false, k = 0.1f), 0f)
        assertEquals(0f, ZsRule.step(0.05f, offline = true, standby = true, k = 0.1f), 0f)
        assertEquals(1f, ZsRule.step(0.95f, offline = false, standby = true, k = 0.1f), 0f)
    }

    @Test
    fun `a link that comes back straight into an awake state never flashes the Zs while the animal wakes`() {
        // Asleep on standby, then the link drops (standby shown, not
        // connected) until the Zs are gone, then it comes back into idle:
        // the panda wakes, and the Zs must not reappear on the way.
        val host = FaceHost()
        fun step(s: FaceState, offline: Boolean): FaceFrame {
            host.advance(1f / 60f, s, null, null, Bindings.DEFAULTS, Arc, offline = offline)
            return host.snapshot()
        }
        repeat(300) { step(FaceState.STANDBY, false) }
        var f = step(FaceState.STANDBY, true)
        repeat(60) { f = step(FaceState.STANDBY, true) }
        assertEquals("gone while not connected", 0f, f.zsW, 0f)
        var worst = 0f
        repeat(180) {
            f = step(FaceState.IDLE, false)
            worst = maxOf(worst, pandaAsleep(f) * f.zsW)
        }
        assertTrue("the Zs came back while it woke ($worst)", worst <= 0.002f)
        // And the next time it nods off, they do come back.
        repeat(300) { f = step(FaceState.STANDBY, false) }
        assertEquals(1f, f.zsW, 0f)
        assertTrue(pandaAsleep(f) * f.zsW > 0.99f)
    }

    @Test
    fun `standby's dim follows the animal nodding off and waking, and banked and error are unchanged`() {
        val standby = Spec.transformFor(FaceState.STANDBY).dim
        assertEquals(1f, DimRule.sleep(1f, 0f), 0f)
        assertEquals(standby, DimRule.sleep(1f, 1f), 1e-6f)
        assertEquals(standby, DimRule.sleep(0.45f, 1f), 1e-6f)
        assertEquals(1f, DimRule.sleep(1f, Float.NaN), 0f)
        assertEquals(0.45f, DimRule.awakeAfter(0.45f, FaceState.STANDBY), 0f)
        assertEquals(Spec.transformFor(FaceState.BANKED).dim, DimRule.awakeAfter(1f, FaceState.BANKED), 0f)
        assertEquals(Spec.transformFor(FaceState.ERROR).dim, DimRule.awakeAfter(1f, FaceState.ERROR), 0f)

        val host = FaceHost()
        fun step(s: FaceState): FaceFrame {
            host.advance(1f / 60f, s, null, null, Bindings.DEFAULTS, Arc)
            return host.snapshot()
        }
        repeat(120) { step(FaceState.IDLE) }
        // Nodding off (~3 s): still full brightness half a second in, never
        // brighter from one frame to the next, standby's own dim at the end.
        val off = List(240) { pandaDim(step(FaceState.STANDBY)) }
        assertTrue("dimmed before it nodded off (${off[30]})", off[30] > 0.97f)
        for (i in 1 until off.size) assertTrue("brighter at frame $i while nodding off", off[i] <= off[i - 1] + 1e-5f)
        assertEquals(standby, off.last(), 1e-4f)
        // Waking (~2 s): still dim on the first frame, never darker from one
        // frame to the next, full brightness at the end.
        val wake = List(180) { pandaDim(step(FaceState.IDLE)) }
        assertTrue("brightened at once on waking (${wake[0]})", wake[0] < standby + 0.05f)
        for (i in 1 until wake.size) assertTrue("darker at frame $i while waking", wake[i] >= wake[i - 1] - 1e-5f)
        assertEquals(1f, wake.last(), 1e-4f)
        // Banked straight away, as before; and banked -> standby goes from
        // banked's dim to standby's without jumping to full brightness.
        val banked = pandaDim(step(FaceState.BANKED))
        assertEquals(Spec.transformFor(FaceState.BANKED).dim, banked, 1e-6f)
        repeat(60) { step(FaceState.BANKED) }
        val toSleep = List(240) { pandaDim(step(FaceState.STANDBY)) }
        assertTrue("jumped on falling asleep from banked: $toSleep", toSleep.all { it in 0.449f..standby + 1e-4f })
        assertEquals(standby, toSleep.last(), 1e-4f)
        // Error from awake: straight away, as before.
        repeat(180) { step(FaceState.IDLE) }
        assertEquals(Spec.transformFor(FaceState.ERROR).dim, pandaDim(step(FaceState.ERROR)), 0f)
    }
}
