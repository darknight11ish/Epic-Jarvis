package com.jarvis.client.data

import com.jarvis.client.face.FrameRateTarget
import com.jarvis.client.face.QualityTier
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The face editor's settings survive a restart, and anything unreadable in
 * storage lands on the default rather than throwing - a bad preference must
 * never be a phone that will not open. Pure: [FaceTuning] has its own one-line
 * format so this can run without org.json (see LookTest).
 */
class FaceTuningTest {

    @Test
    fun theDefaultsAreTheOnesAsked() {
        val d = FaceTuning()
        assertEquals(QualityTier.HIGH, d.quality)
        assertEquals(FrameRateTarget.AUTO, d.frameRate)
        assertEquals(1f, d.speed, 0f)
        assertTrue("Auto adjust is on by default", d.autoAdjust)
        assertFalse(d.batterySaver)
        assertEquals(d, d.clamped())
    }

    @Test
    fun everyCombinationRoundTrips() {
        for (q in QualityTier.entries) {
            for (f in FrameRateTarget.entries) {
                for (s in FaceTuning.SPEEDS) {
                    for (a in listOf(true, false)) {
                        for (b in listOf(true, false)) {
                            val t = FaceTuning(q, f, s, a, b)
                            assertEquals(t, FaceTuning.decode(t.encode()))
                        }
                    }
                }
            }
        }
    }

    @Test
    fun missingOrUnreadableIsTheDefault() {
        assertEquals(FaceTuning(), FaceTuning.decode(null))
        assertEquals(FaceTuning(), FaceTuning.decode(""))
        assertEquals(FaceTuning(), FaceTuning.decode("   "))
        assertEquals(FaceTuning(), FaceTuning.decode("not a setting at all"))
        assertEquals(FaceTuning(), FaceTuning.decode("{\"q\":\"low\"}"))
        assertEquals(FaceTuning(), FaceTuning.decode(";;=;==;"))
    }

    /** One bad field falls back on its own; the others keep what the owner chose. */
    @Test
    fun unknownValuesFallBackFieldByField() {
        // 90 is a real choice since 2026-09-28; 75 is not one.
        val t = FaceTuning.decode("q=ultra;f=75;s=fast;a=maybe;b=1")
        assertEquals(QualityTier.DEFAULT, t.quality)
        assertEquals(FrameRateTarget.DEFAULT, t.frameRate)
        assertEquals(1f, t.speed, 0f)
        assertTrue(t.autoAdjust)
        assertTrue("the one readable field is kept", t.batterySaver)

        val partial = FaceTuning.decode("q=low")
        assertEquals(QualityTier.LOW, partial.quality)
        assertEquals(FrameRateTarget.AUTO, partial.frameRate)
        assertTrue(partial.autoAdjust)
    }

    /** 30 and 90 (added 2026-09-28) are stored and read back; the old ids still read. */
    @Test
    fun theNewFrameRatesAndTheOldIdsRoundTrip() {
        assertEquals(FrameRateTarget.FPS_30, FaceTuning.decode("f=30").frameRate)
        assertEquals(FrameRateTarget.FPS_90, FaceTuning.decode("f=90").frameRate)
        // The quality ids never changed with the new names (Lower, Balanced, Maximum).
        assertEquals(QualityTier.LOW, FaceTuning.decode("q=low").quality)
        assertEquals(QualityTier.MEDIUM, FaceTuning.decode("q=medium").quality)
        assertEquals(QualityTier.MAX, FaceTuning.decode("q=max").quality)
        val t = FaceTuning(QualityTier.MAX, FrameRateTarget.FPS_90, 1f, false, false)
        assertEquals(t, FaceTuning.decode(t.encode()))
    }

    @Test
    fun keysFromALaterVersionAreIgnored() {
        val t = FaceTuning.decode("q=medium;f=60;s=0.5;a=0;b=0;z=whatever;glow=9")
        assertEquals(FaceTuning(QualityTier.MEDIUM, FrameRateTarget.FPS_60, 0.5f, false, false), t)
    }

    /** NaN would survive coerceIn; it has to be caught first (see AppearanceStore.parseBindings). */
    @Test
    fun speedIsClampedAndNanIsTheDefault() {
        assertEquals(FaceTuning.MAX_SPEED, FaceTuning.decode("s=40").speed, 0f)
        assertEquals(FaceTuning.MIN_SPEED, FaceTuning.decode("s=0").speed, 0f)
        assertEquals(FaceTuning.MIN_SPEED, FaceTuning.decode("s=-3").speed, 0f)
        assertEquals(1f, FaceTuning.decode("s=NaN").speed, 0f)
        assertEquals(1f, FaceTuning.decode("s=Infinity").speed, 0f)
        assertEquals(1f, FaceTuning(speed = Float.NaN).clamped().speed, 0f)
    }

    @Test
    fun theOfferedSpeedsAreInRangeAndIncludeOne() {
        assertTrue(1f in FaceTuning.SPEEDS)
        assertTrue(FaceTuning.SPEEDS.all { it in FaceTuning.MIN_SPEED..FaceTuning.MAX_SPEED })
        assertEquals(FaceTuning.SPEEDS.sorted(), FaceTuning.SPEEDS)
    }
}
