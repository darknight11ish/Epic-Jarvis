package com.jarvis.client

import com.jarvis.client.data.FaceTuning
import com.jarvis.client.face.FaceBudget
import com.jarvis.client.face.FrameGovernor
import com.jarvis.client.face.FramePacing
import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.QualityTier
import com.jarvis.client.platform.SmoothMotion
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The face editor's budget: the reactor kit's quality tiers, its divisor
 * rule, the Auto adjust governor, and who wins between Battery saver, Auto
 * adjust and the owner's own choices. All pure - see `face/FaceBudget.kt`.
 *
 * Deliberately never touches `FaceQuality`, the one live budget: it is
 * process-wide, and the face tests read their detail from it.
 */
class FaceBudgetTest {

    // ------------------------------------------------------------- tiers ----

    /** The kit's TIERS table, and the solo floor applied to High and Max only. */
    @Test
    fun tiersMatchTheKit() {
        assertEquals(0.75f, QualityTier.LOW.kitDetail, 0f)
        assertEquals(1.0f, QualityTier.MEDIUM.kitDetail, 0f)
        assertEquals(1.4f, QualityTier.HIGH.kitDetail, 0f)
        assertEquals(2.0f, QualityTier.MAX.kitDetail, 0f)

        assertEquals(0.62f, QualityTier.LOW.gpu, 0f)
        assertEquals(0.80f, QualityTier.MEDIUM.gpu, 0f)
        assertEquals(1.0f, QualityTier.HIGH.gpu, 0f)
        assertEquals(1.0f, QualityTier.MAX.gpu, 0f)

        assertFalse(QualityTier.LOW.post)
        assertTrue(QualityTier.MEDIUM.post)
        assertTrue(QualityTier.HIGH.post)
        assertTrue(QualityTier.MAX.post)
    }

    /**
     * What the phone's faces actually multiply by. High is exactly the 1.9
     * every face used before this setting existed; Low and Medium are cheaper,
     * which the solo floor would have prevented.
     */
    @Test
    fun phoneDetailKeepsTheOldDefaultAndSavesWorkBelowIt() {
        assertEquals(0.75f, QualityTier.LOW.detail, 0f)
        assertEquals(1.0f, QualityTier.MEDIUM.detail, 0f)
        assertEquals(1.9f, QualityTier.HIGH.detail, 0f)
        assertEquals(2.0f, QualityTier.MAX.detail, 0f)
        assertEquals(QualityTier.HIGH, QualityTier.DEFAULT)
        val details = QualityTier.entries.map { it.detail }
        assertEquals("each tier does more than the one below", details.sorted(), details)
    }

    @Test
    fun tierAndFrameRateIdsRoundTripAndUnknownIsTheDefault() {
        for (t in QualityTier.entries) assertEquals(t, QualityTier.byId(t.id))
        for (f in FrameRateTarget.entries) assertEquals(f, FrameRateTarget.byId(f.id))
        assertEquals(QualityTier.DEFAULT, QualityTier.byId(null))
        assertEquals(QualityTier.DEFAULT, QualityTier.byId("ultra"))
        assertEquals(FrameRateTarget.AUTO, FrameRateTarget.byId(null))
        assertEquals(FrameRateTarget.AUTO, FrameRateTarget.byId("90"))
    }

    @Test
    fun upAndDownStopAtTheEnds() {
        assertEquals(QualityTier.LOW, QualityTier.LOW.down())
        assertEquals(QualityTier.MAX, QualityTier.MAX.up())
        assertEquals(QualityTier.MEDIUM, QualityTier.HIGH.down())
        assertEquals(QualityTier.HIGH, QualityTier.MEDIUM.up())
    }

    // ------------------------------------------------------ divisor rule ----

    /** The kit's applyTarget: stride = max(1, round(hz / want)). */
    @Test
    fun strideIsAWholeDivisorOfThePanel() {
        assertEquals(1, FramePacing.strideFor(FrameRateTarget.AUTO, 120f))
        assertEquals(1, FramePacing.strideFor(FrameRateTarget.MAX, 144f))
        assertEquals(2, FramePacing.strideFor(FrameRateTarget.FPS_60, 120f))
        assertEquals(1, FramePacing.strideFor(FrameRateTarget.FPS_60, 60f))
        // Asking for more than the panel has is capped at the panel.
        assertEquals(1, FramePacing.strideFor(FrameRateTarget.FPS_120, 60f))
        // 90 / 60 = 1.5, which the kit's Math.round takes up to 2.
        assertEquals(2, FramePacing.strideFor(FrameRateTarget.FPS_60, 90f))
        assertEquals(1, FramePacing.strideFor(FrameRateTarget.FPS_120, 144f))
    }

    @Test
    fun strideAtMostKeepsUnderTheCap() {
        assertEquals(2, FramePacing.strideAtMost(60f, 30))
        assertEquals(3, FramePacing.strideAtMost(90f, 30))
        assertEquals(4, FramePacing.strideAtMost(120f, 30))
        assertEquals(5, FramePacing.strideAtMost(144f, 30))
        assertEquals(3, FramePacing.strideAtMost(75f, 30))
        for (hz in listOf(60f, 75f, 90f, 120f, 144f, 165f, 240f)) {
            val s = FramePacing.strideAtMost(hz, 30)
            assertTrue("$hz Hz / $s is over 30", hz / s <= 30f + 1e-3f)
        }
    }

    /** "budget_ms = 1000 / (hz / stride)" - measured against the real rate, never a fixed 16.7. */
    @Test
    fun budgetFollowsTheDisplay() {
        assertEquals(8.333f, FramePacing.budgetMs(120f, 1), 0.01f)
        assertEquals(16.667f, FramePacing.budgetMs(120f, 2), 0.01f)
        assertEquals(16.667f, FramePacing.budgetMs(60f, 1), 0.01f)
        // Nonsense rates are read as 60, not divided by.
        assertEquals(16.667f, FramePacing.budgetMs(0f, 1), 0.01f)
        assertEquals(16.667f, FramePacing.budgetMs(Float.NaN, 1), 0.01f)
    }

    /** The kit's `hz / (stride + 1) >= 30`: never stride below 30 fps. */
    @Test
    fun neverStridesBelowThirty() {
        assertTrue(FramePacing.canStrideFurther(120f, 1))
        assertTrue(FramePacing.canStrideFurther(120f, 3))
        assertFalse(FramePacing.canStrideFurther(120f, 4))
        assertTrue(FramePacing.canStrideFurther(60f, 1))
        assertFalse(FramePacing.canStrideFurther(60f, 2))
    }

    @Test
    fun snapsToRealPanelRates() {
        assertEquals(120f, FramePacing.snapHz(118.4f), 0f)
        assertEquals(60f, FramePacing.snapHz(59.94f), 0f)
        assertEquals(90f, FramePacing.snapHz(90.1f), 0f)
        assertEquals(60f, FramePacing.snapHz(0f), 0f)
        assertEquals(60f, FramePacing.snapHz(Float.NaN), 0f)
        assertEquals(200f, FramePacing.snapHz(200f), 0f)
    }

    /**
     * The vsync period follows a panel that runs slower than it reports, but a
     * slow face can never talk it past twice the reported period.
     */
    @Test
    fun vsyncPeriodTrustsTheFastEndOnly() {
        assertEquals(8.333f, FramePacing.vsyncPeriodMs(120f, Float.MAX_VALUE), 0.01f)
        assertEquals(8.333f, FramePacing.vsyncPeriodMs(120f, 5f), 0.01f)
        // Reports 120, delivers 60 (low brightness, heat): the real 16.7.
        assertEquals(16.6f, FramePacing.vsyncPeriodMs(120f, 16.6f), 0.01f)
        // A face managing three frames a second does not make 333 ms the period.
        assertEquals(16.667f, FramePacing.vsyncPeriodMs(120f, 333f), 0.01f)
    }

    @Test
    fun aLateFrameCostsItsWholeIntervalAndAnOnTimeOneOnlyItsDraw() {
        // On time: the draw is the cost.
        assertEquals(4f, FramePacing.frameCostMs(4f, 16.7f, 16.7f, 16.7f), 0.001f)
        // A slow GPU: a cheap draw, but the frame came 100 ms after the last.
        assertEquals(100f, FramePacing.frameCostMs(2f, 100f, 16.7f, 16.7f), 0.001f)
        // At 30 fps on a 60 Hz panel the loop waits 33 ms on purpose; only
        // what is beyond that deliberate wait counts.
        assertEquals(83.4f, FramePacing.frameCostMs(2f, 100f, 33.3f, 16.7f), 0.01f)
        // Pauses and nonsense are not frames.
        assertEquals(2f, FramePacing.frameCostMs(2f, 5_000f, 16.7f, 16.7f), 0.001f)
        assertEquals(2f, FramePacing.frameCostMs(2f, Float.NaN, 16.7f, 16.7f), 0.001f)
        assertEquals(0f, FramePacing.frameCostMs(Float.NaN, 10f, 16.7f, 16.7f), 0.001f)
    }

    // ---------------------------------------------------------- governor ----

    /** Feeds [frames] frames [stepMs] apart, each costing [costMs], from [fromMs]. Returns the last time. */
    private fun FrameGovernor.run(
        fromMs: Long,
        stepMs: Long,
        frames: Int,
        costMs: Float,
        budgetMs: Float = 16.667f,
        panelHz: Float = 60f,
        ceiling: QualityTier = QualityTier.MAX,
    ): Long {
        var t = fromMs
        repeat(frames) {
            t += stepMs
            onFrame(t, costMs, budgetMs, panelHz, 1, ceiling)
        }
        return t
    }

    /** Like [run], but stops at the first frame where the tier changes. Returns that time. */
    private fun FrameGovernor.runUntilTierChanges(fromMs: Long, stepMs: Long, costMs: Float, maxFrames: Int = 5_000): Long {
        val before = tier
        var t = fromMs
        for (i in 0 until maxFrames) {
            t += stepMs
            onFrame(t, costMs, 16.667f, 60f, 1, QualityTier.MAX)
            if (tier != before) return t
        }
        return t
    }

    @Test
    fun warmUpFramesAreNotCounted() {
        val g = FrameGovernor()
        // A shader compiling: the first second is awful, then it is fine.
        g.run(fromMs = 10_000, stepMs = 100, frames = 9, costMs = 500f)
        assertEquals(QualityTier.HIGH, g.tier)
    }

    /**
     * A phone that can only manage three frames a second reaches Low within
     * about two seconds of its first frame - not one tier every two seconds -
     * and then halves its frame rate, but never below 30 fps.
     */
    @Test
    fun aVerySlowPhoneReachesLowQuickly() {
        val g = FrameGovernor()
        var t = 10_000L
        var reachedLowAt = -1L
        repeat(12) {
            t += 333
            g.onFrame(t, 333f, 16.667f, 60f, 1, QualityTier.MAX)
            if (g.tier == QualityTier.LOW && reachedLowAt < 0) reachedLowAt = t
        }
        assertTrue("never reached Low", reachedLowAt > 0)
        assertTrue("took ${reachedLowAt - 10_000} ms", reachedLowAt - 10_000 <= 2_100)
        assertEquals(QualityTier.LOW, g.tier)
        // 60 Hz / 2 = 30: one divisor step, and no further.
        assertEquals(1, g.extraStride)
    }

    @Test
    fun anOverloadedPhoneStepsDownOneTierAtATimeWithTheKitsCooldown() {
        val g = FrameGovernor()
        // Twice the budget: over the 1.45 line, well under "severe".
        var t = g.run(fromMs = 0, stepMs = 16, frames = 60, costMs = 33f) // warm-up, then samples
        assertEquals(QualityTier.HIGH, g.tier)
        t = g.run(fromMs = t, stepMs = 16, frames = 80, costMs = 33f)
        assertEquals(QualityTier.MEDIUM, g.tier)
        // Not again straight away: the kit's two-second cooldown.
        t = g.run(fromMs = t, stepMs = 16, frames = 60, costMs = 33f)
        assertEquals(QualityTier.MEDIUM, g.tier)
        t = g.run(fromMs = t, stepMs = 16, frames = 90, costMs = 33f)
        assertEquals(QualityTier.LOW, g.tier)
        // At Low, the next step is a divisor, not a lower quality.
        g.run(fromMs = t, stepMs = 16, frames = 140, costMs = 33f)
        assertEquals(QualityTier.LOW, g.tier)
        assertEquals(1, g.extraStride)
    }

    @Test
    fun theDeadBandHoldsStill() {
        val g = FrameGovernor()
        g.run(fromMs = 0, stepMs = 16, frames = 2_000, costMs = 16f) // load ~1: inside 0.55..1.45
        assertEquals(QualityTier.HIGH, g.tier)
        assertEquals(0, g.extraStride)
    }

    /** Auto never picks Max for you, as in the kit (`i < 2`). */
    @Test
    fun autoNeverClimbsPastHigh() {
        val g = FrameGovernor()
        g.run(fromMs = 0, stepMs = 16, frames = 3_000, costMs = 1f)
        assertEquals(QualityTier.HIGH, g.tier)
    }

    /**
     * Hysteresis: after stepping down out of High, cheap frames do not bring
     * it straight back - it waits out a hold, and the hold doubles the next
     * time the same step down happens.
     */
    @Test
    fun steppingBackUpWaitsOutAHoldThatGrows() {
        val g = FrameGovernor()
        var t = g.runUntilTierChanges(fromMs = 0, stepMs = 16, costMs = 33f)
        assertEquals(QualityTier.MEDIUM, g.tier)
        val downAt = t

        // Cheap now, but High is held off for HOLD_FIRST_MS.
        t = g.run(fromMs = t, stepMs = 16, frames = 400, costMs = 2f) // ~6.4 s
        assertEquals(QualityTier.MEDIUM, g.tier)
        assertTrue(t - downAt < FrameGovernor.HOLD_FIRST_MS)
        t = g.run(fromMs = t, stepMs = 16, frames = 400, costMs = 2f) // past 10 s
        assertEquals(QualityTier.HIGH, g.tier)

        // Down again: now High is held for twice as long.
        t = g.runUntilTierChanges(fromMs = t, stepMs = 16, costMs = 33f)
        assertEquals(QualityTier.MEDIUM, g.tier)
        val secondDownAt = t
        t = g.run(fromMs = t, stepMs = 16, frames = 900, costMs = 2f) // ~14 s: past 10, short of 20
        assertTrue(t - secondDownAt in FrameGovernor.HOLD_FIRST_MS until FrameGovernor.HOLD_FIRST_MS * 2)
        assertEquals(QualityTier.MEDIUM, g.tier)
        g.run(fromMs = t, stepMs = 16, frames = 500, costMs = 2f)
        assertEquals(QualityTier.HIGH, g.tier)
    }

    @Test
    fun aDivisorStepIsUndoneWhenThereIsRoomAgain() {
        val g = FrameGovernor()
        g.reset(QualityTier.LOW, extraStride = 1)
        // Very cheap: quality comes back first (as the kit does), then the rate.
        g.run(fromMs = 0, stepMs = 33, frames = 1_000, costMs = 0.5f, budgetMs = 33.3f)
        assertEquals(QualityTier.HIGH, g.tier)
        assertEquals(0, g.extraStride)
    }

    @Test
    fun aLowerCeilingAppliesAtOnce() {
        val g = FrameGovernor()
        g.onFrame(1_000, 1f, 16.667f, 60f, 1, QualityTier.MEDIUM)
        assertEquals(QualityTier.MEDIUM, g.tier)
        g.onFrame(1_016, 1f, 16.667f, 60f, 1, QualityTier.LOW)
        assertEquals(QualityTier.LOW, g.tier)
    }

    @Test
    fun aNewFaceKeepsTheTierButWarmsUpAgain() {
        val g = FrameGovernor()
        val t = g.run(fromMs = 0, stepMs = 16, frames = 200, costMs = 33f)
        assertEquals(QualityTier.MEDIUM, g.tier)
        g.restartWarmup()
        assertEquals(QualityTier.MEDIUM, g.tier)
        // The new face's first second is not held against it.
        g.run(fromMs = t, stepMs = 16, frames = 60, costMs = 500f)
        assertEquals(QualityTier.MEDIUM, g.tier)
    }

    /**
     * A software renderer starts at Low and 30 fps; if its frames are fast it
     * may climb, but [FaceBudget.resolve] never lets it past
     * [FaceBudget.SOFTWARE_AUTO_TOP].
     */
    @Test
    fun aSoftwareRendererStartsLowAndIsCappedBelowHigh() {
        val g = FrameGovernor()
        g.reset(QualityTier.LOW, extraStride = FramePacing.strideAtMost(60f, 30) - 1)
        val start = FaceBudget.resolve(FaceTuning(), false, 0, g.tier, g.extraStride, 60f, softwareGpu = true)
        assertEquals(QualityTier.LOW, start.tier)
        assertEquals(30, start.fps)
        assertFalse(start.post)

        val ceiling = FaceBudget.autoCeiling(heat = 0, softwareGpu = true)
        g.run(fromMs = 0, stepMs = 33, frames = 2_000, costMs = 0.5f, budgetMs = 33.3f, ceiling = ceiling)
        val later = FaceBudget.resolve(FaceTuning(), false, 0, g.tier, g.extraStride, 60f, softwareGpu = true)
        assertEquals(FaceBudget.SOFTWARE_AUTO_TOP, later.tier)
        assertTrue(later.tier < QualityTier.HIGH)
    }

    @Test
    fun softwareRenderersAreRecognised() {
        val software = listOf(
            "Google SwiftShader",
            "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
            "Android Emulator OpenGL ES Translator (Google SwiftShader)",
            "Android Emulator OpenGL ES Translator (NVIDIA GeForce RTX 2080 SUPER)",
            "llvmpipe (LLVM 15.0.7, 256 bits)",
            "Gallium 0.4 on softpipe",
            "SWIFTSHADER",
        )
        for (r in software) assertTrue(r, FaceBudget.isSoftwareRenderer(r))
        val hardware = listOf(
            "Adreno (TM) 740",
            "Mali-G710",
            "PowerVR Rogue GE8320",
            "Xclipse 920",
            "Immortalis-G715",
        )
        for (r in hardware) assertFalse(r, FaceBudget.isSoftwareRenderer(r))
        // A failed query is NOT software: fail safe, let the governor work.
        assertFalse(FaceBudget.isSoftwareRenderer(null))
        assertFalse(FaceBudget.isSoftwareRenderer(""))
        assertFalse(FaceBudget.isSoftwareRenderer("   "))
    }

    // -------------------------------------------------------- precedence ----

    @Test
    fun batterySaverOverridesEverything() {
        val chosen = FaceTuning(
            quality = QualityTier.MAX, frameRate = FrameRateTarget.MAX, speed = 2f,
            autoAdjust = false, batterySaver = true,
        )
        for (t in listOf(chosen, chosen.copy(autoAdjust = true))) {
            val r = FaceBudget.resolve(t, phoneSaver = false, heat = 0, QualityTier.HIGH, 0, 120f)
            assertEquals(QualityTier.LOW, r.tier)
            assertFalse(r.post)
            assertTrue(r.calm)
            assertTrue(r.fps <= FaceBudget.SAVER_MAX_FPS)
            assertEquals(1f, r.speed, 0f)
            assertTrue(r.saver)
            assertFalse(r.saverFromPhone)
            assertFalse(r.governed)
        }
    }

    @Test
    fun thePhonesOwnBatterySaverTurnsItOn() {
        val r = FaceBudget.resolve(FaceTuning(), phoneSaver = true, heat = 0, QualityTier.HIGH, 0, 60f)
        assertTrue(r.saver)
        assertTrue(r.saverFromPhone)
        assertEquals(QualityTier.LOW, r.tier)
        assertEquals(30, r.fps)
        // Both on: it is the owner's, not only the phone's.
        val both = FaceBudget.resolve(FaceTuning(batterySaver = true), phoneSaver = true, heat = 0, QualityTier.HIGH, 0, 60f)
        assertFalse(both.saverFromPhone)
    }

    @Test
    fun autoAdjustUsesTheGovernorUnderTheHeatCeiling() {
        val auto = FaceTuning(quality = QualityTier.MAX, frameRate = FrameRateTarget.FPS_60)
        val cool = FaceBudget.resolve(auto, false, heat = 0, QualityTier.HIGH, 1, 120f)
        assertTrue(cool.governed)
        assertEquals(QualityTier.HIGH, cool.tier)
        // The stored Frame rate is ignored under Auto; the governor's divisor is used.
        assertEquals(2, cool.stride)
        assertEquals(60, cool.fps)
        assertEquals(QualityTier.MEDIUM, FaceBudget.resolve(auto, false, heat = 1, QualityTier.HIGH, 0, 120f).tier)
        assertEquals(QualityTier.LOW, FaceBudget.resolve(auto, false, heat = 2, QualityTier.HIGH, 0, 120f).tier)
    }

    /** "You picked a tier; it stays picked" - even when the phone is hot. */
    @Test
    fun anExplicitChoiceIsNotOverriddenExceptByBatterySaver() {
        val manual = FaceTuning(quality = QualityTier.MAX, frameRate = FrameRateTarget.FPS_60, autoAdjust = false)
        val r = FaceBudget.resolve(manual, false, heat = 2, QualityTier.LOW, 3, 120f)
        assertFalse(r.governed)
        assertEquals(QualityTier.MAX, r.tier)
        assertEquals(2, r.stride)
        assertTrue(r.post)
        val low = FaceBudget.resolve(manual.copy(quality = QualityTier.LOW), false, 0, QualityTier.HIGH, 0, 60f)
        assertFalse("Low has no glow", low.post)
    }

    @Test
    fun speedIsPassedThroughAndCappedOnlyWhenCalm() {
        val fast = FaceTuning(speed = 2f)
        assertEquals(2f, FaceBudget.resolve(fast, false, 0, QualityTier.HIGH, 0, 60f).speed, 0f)
        assertEquals(1f, FaceBudget.resolve(fast, true, 0, QualityTier.HIGH, 0, 60f).speed, 0f)
        val slow = FaceTuning(speed = 0.5f)
        assertEquals(0.5f, FaceBudget.resolve(slow, true, 0, QualityTier.HIGH, 0, 60f).speed, 0f)
    }

    @Test
    fun theFrameRateChoiceDecidesHowHardThePanelIsAsked() {
        assertEquals(SmoothMotion.AUTO, FaceBudget.smoothFor(FaceTuning(), false))
        assertEquals(SmoothMotion.OFF, FaceBudget.smoothFor(FaceTuning(), true))
        assertEquals(SmoothMotion.OFF, FaceBudget.smoothFor(FaceTuning(batterySaver = true), false))
        val manual = FaceTuning(autoAdjust = false)
        assertEquals(SmoothMotion.OFF, FaceBudget.smoothFor(manual.copy(frameRate = FrameRateTarget.FPS_60), false))
        assertEquals(SmoothMotion.AUTO, FaceBudget.smoothFor(manual.copy(frameRate = FrameRateTarget.FPS_120), false))
        assertEquals(SmoothMotion.AUTO, FaceBudget.smoothFor(manual.copy(frameRate = FrameRateTarget.AUTO), false))
        assertEquals(SmoothMotion.ALWAYS, FaceBudget.smoothFor(manual.copy(frameRate = FrameRateTarget.MAX), false))
    }

    /** The defaults: Auto adjust on, battery saver off, High, full speed - what the phone drew before. */
    @Test
    fun theDefaultIsTheOldFace() {
        val r = FaceBudget.resolve(FaceTuning(), false, 0, QualityTier.DEFAULT, 0, 120f)
        assertTrue(r.governed)
        assertEquals(QualityTier.HIGH, r.tier)
        assertEquals(1.9f, r.tier.detail, 0f)
        assertTrue(r.post)
        assertFalse(r.calm)
        assertEquals(1f, r.speed, 0f)
        assertEquals(1, r.stride)
    }
}
