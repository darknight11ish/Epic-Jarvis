package com.jarvis.client

import com.jarvis.client.data.ScreenRate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The screen refresh rate's selection rule (`data/ScreenRate.kt`).
 *
 * Pure JVM: [ScreenRate] has no Android in it. A JVM test cannot prove the
 * panel changed - that needs the real phone, and the note at the bottom of this
 * file says what was and was not proved there.
 *
 * The mode floats below are the owner's real phone's, copied from
 * `adb shell dumpsys display` (OnePlus CPH2419, Android 15): the panel reports
 * 120.00001, 60.000004 and 90.0, never the round numbers on the label. Every
 * assertion that looks like it is about 60, 90 and 120 is about those three
 * floats.
 */
class ScreenRateTest {

    /** OnePlus CPH2419, `dumpsys display`, 2026-10-09 - verbatim. */
    private val phone = listOf(120.00001f, 60.000004f, 90.0f)

    // ------------------------------------------------------------ the list --

    @Test
    fun `the rates are deduplicated, ascending, and whole`() {
        val rates = ScreenRate.rates(phone)
        assertEquals(listOf(60f, 90f, 120f), rates)
        // Ascending on the raw floats too, so a caller that shows them in order
        // shows them in order.
        assertEquals(rates, rates.sorted())
        assertEquals(rates.distinct(), rates)
    }

    @Test
    fun `two modes that differ only past the decimal point are one rate`() {
        // 59.94 and 60.000004 are the same rate to a person, and must be one
        // row in the picker, not two.
        assertEquals(listOf(60f), ScreenRate.rates(listOf(59.94f, 60.000004f, 60f)))
        assertEquals(listOf(120f), ScreenRate.rates(listOf(119.88f, 120.00001f)))
    }

    @Test
    fun `a mode the platform reported wrongly is not a choice`() {
        assertEquals(listOf(60f, 120f), ScreenRate.rates(listOf(60f, 0f, -120f, Float.NaN, Float.POSITIVE_INFINITY, 120f)))
        assertEquals(emptyList<Float>(), ScreenRate.rates(emptyList()))
        assertEquals(emptyList<Float>(), ScreenRate.rates(listOf(Float.NaN, -1f, 0f)))
    }

    // ------------------------------------------------- the pick, and rounding --

    @Test
    fun `a pick the panel offers exactly is used as it is`() {
        for (hz in listOf(60f, 90f, 120f)) {
            val ask = ScreenRate.choose(hz, phone)
            assertEquals(hz, ask.hz)
            assertEquals("$hz Hz should be exact", ScreenRate.Settled.EXACT, ask.settled)
            assertTrue(ask.note.contains(ScreenRate.label(hz)))
        }
    }

    @Test
    fun `a pick the panel cannot do takes the next rate UP, never a slower one`() {
        // 75 is between 60 and 90: the next rate up is 90. 60 would be slower
        // than the pick, which the house rule forbids.
        val a = ScreenRate.choose(75f, phone)
        assertEquals(90f, a.hz)
        assertEquals(ScreenRate.Settled.ROUNDED_UP, a.settled)

        // 100 is between 90 and 120.
        assertEquals(120f, ScreenRate.choose(100f, phone).hz)
        // 61 is just over 60.
        assertEquals(90f, ScreenRate.choose(61f, phone).hz)

        // And it is never the rate below: for every pick the panel does NOT
        // offer, the answer is strictly above the pick. (A pick the panel does
        // offer is Settled.EXACT and is the pick itself, so it is skipped -
        // the first version of this loop forgot, and asserted 90 > 90.)
        val offered = ScreenRate.rates(phone)
        for (pick in 61..119) {
            if (pick.toFloat() in offered) continue
            val ask = ScreenRate.choose(pick.toFloat(), phone)
            assertEquals("pick $pick", ScreenRate.Settled.ROUNDED_UP, ask.settled)
            assertTrue("pick $pick asked for ${ask.hz}", (ask.hz ?: 0f) > pick.toFloat())
        }
    }

    @Test
    fun `a pick below every rate takes the lowest, which is still the next one up`() {
        val ask = ScreenRate.choose(30f, phone)
        assertEquals(60f, ask.hz)
        assertEquals(ScreenRate.Settled.ROUNDED_UP, ask.settled)
    }

    @Test
    fun `a pick above every rate takes the highest and SAYS SO`() {
        val ask = ScreenRate.choose(165f, phone)
        assertEquals(120f, ask.hz)
        assertEquals(ScreenRate.Settled.ABOVE_TOP, ask.settled)
        // Saying so is the whole point: the note names both numbers, so a
        // silently capped pick cannot happen.
        assertTrue("note did not name the pick: ${ask.note}", ask.note.contains("165"))
        assertTrue("note did not name the cap: ${ask.note}", ask.note.contains("120"))
        assertTrue("note did not say it is the highest: ${ask.note}", ask.note.contains("highest"))
    }

    @Test
    fun `a panel with one rate answers that rate for every pick`() {
        for (pick in listOf(30f, 60f, 90f, 144f, 240f)) {
            val ask = ScreenRate.choose(pick, listOf(60f))
            assertEquals("pick $pick", 60f, ask.hz)
        }
    }

    // ------------------------------------------------- no pick, and no rates --

    @Test
    fun `no pick leaves the phone's own choice alone, and never asks for a rate`() {
        for (pick in listOf(null, 0f, -1f, Float.NaN, Float.POSITIVE_INFINITY)) {
            val ask = ScreenRate.choose(pick, phone)
            assertNull("pick $pick", ask.hz)
            assertEquals(ScreenRate.Settled.FOLLOW_PHONE, ask.settled)
        }
    }

    @Test
    fun `a panel that reported no rates has nothing to ask for`() {
        val ask = ScreenRate.choose(120f, emptyList())
        assertNull(ask.hz)
        assertEquals(ScreenRate.Settled.NOTHING, ask.settled)
        assertTrue(ask.note.isNotBlank())
    }

    // ----------------------------------------------------- did it take effect --

    @Test
    fun `the panel really taking the rate is reported as taken`() {
        // The panel's own reported floats, never the round numbers.
        assertTrue(ScreenRate.took(120f, 120.00001f))
        assertTrue(ScreenRate.took(60f, 60.000004f))
        assertTrue(ScreenRate.took(90f, 90.0f))
        val note = ScreenRate.tookNote(120f, 120.00001f)
        assertTrue(note, note.contains("120"))
        assertFalse("a taken rate must not claim failure: $note", note.contains("did not take effect"))
    }

    @Test
    fun `the system refusing the rate leaves the owner told, not believing it worked`() {
        // Asked for 120 on the owner's phone and ColorOS kept it at 60 -
        // exactly what mIgnorePreferredRefreshRate does.
        val note = ScreenRate.tookNote(120f, 60f)
        assertFalse(ScreenRate.took(120f, 60f))
        assertTrue("must say it did not take effect: $note", note.contains("did not take effect"))
        assertTrue("must name what was asked: $note", note.contains("120"))
        assertTrue("must name what happened: $note", note.contains("60"))

        // The device's OWN floats, read from `adb shell dumpsys display` on
        // 2026-10-09: the 120 Hz mode reports 120.00001 and the panel is
        // actually running the 60 Hz mode, which reports 60.000004. This is the
        // exact pair the owner's phone produces today, so the sentence the plate
        // would show on that phone is the sentence asserted here.
        val real = ScreenRate.tookNote(120.00001f, 60.000004f)
        assertTrue("the phone's own numbers must read as a refusal: $real",
            real.contains("did not take effect"))
        assertFalse(ScreenRate.took(120.00001f, 60.000004f))
    }

    @Test
    fun `every refusal between two real rates is caught`() {
        val real = listOf(60f, 90f, 120f)
        for (a in real) for (b in real) {
            assertEquals("asked $a, got $b", a == b, ScreenRate.took(a, b))
        }
    }

    @Test
    fun `a nonsense reading is not a success`() {
        assertFalse(ScreenRate.took(120f, Float.NaN))
        assertFalse(ScreenRate.took(Float.NaN, 120f))
        assertFalse(ScreenRate.took(120f, 0f))
    }

    // -------------------------------------------------------------- the store --

    @Test
    fun `the saved preference round-trips, and a corrupt one is no pick`() {
        assertEquals("120", ScreenRate.encode(120f))
        assertEquals(120f, ScreenRate.decode("120"))
        assertEquals(ScreenRate.FOLLOW_PHONE, ScreenRate.encode(null))
        assertNull(ScreenRate.decode(ScreenRate.FOLLOW_PHONE))

        // Anything unreadable is "follow the phone", never a wrong request.
        for (raw in listOf(null, "", "  ", "abc", "0", "-5", "NaN", "Infinity")) {
            assertNull("raw=$raw", ScreenRate.decode(raw))
        }
        assertEquals(ScreenRate.FOLLOW_PHONE, ScreenRate.encode(Float.NaN))
        assertEquals(ScreenRate.FOLLOW_PHONE, ScreenRate.encode(0f))
    }

    @Test
    fun `every sentence the plate shows says ask, and never promises to change the phone`() {
        val sentences = listOf(
            ScreenRate.HONEST_NOTE,
            ScreenRate.BATTERY_NOTE,
        ) + listOf(null, 60f, 75f, 165f).map { ScreenRate.pickNote(it, phone) }

        for (s in sentences) {
            assertTrue("blank sentence", s.isNotBlank())
            // The one word that would be a lie. "change your phone's own display
            // setting" appears in HONEST_NOTE as the thing it CANNOT do, so the
            // rule is: it never promises it.
            assertFalse("promises to change the phone: $s", s.contains("will change your phone"))
        }
        assertTrue(ScreenRate.HONEST_NOTE.contains("asks the screen"))
        assertTrue("battery must be mentioned honestly", ScreenRate.BATTERY_NOTE.contains("more battery"))
    }

    /**
     * What a JVM test cannot do, said plainly rather than implied: nothing here
     * proves the panel changed. The plate's own readback ([ScreenRate.tookNote])
     * is what tells the owner, and the real-device attempt is recorded in the
     * commit message and the task report. On the owner's CPH2419 the request is
     * ignored - `dumpsys display` reports `mIgnorePreferredRefreshRate: true` -
     * so the expected real-device result is the "did not take effect" sentence,
     * not a changed panel.
     */
    @Test
    fun `the rule is pure - no Android class is touched by any case above`() {
        // Every case above runs on a bare JVM. This test exists so the claim is
        // visible in the suite rather than only in a comment: if any function
        // above reached for android.*, these calls would throw "not mocked".
        assertEquals(90f, ScreenRate.choose(75f, phone).hz)
        assertEquals(listOf(60f, 90f, 120f), ScreenRate.rates(phone))
        assertFalse(ScreenRate.took(120f, 60f))
    }
}
