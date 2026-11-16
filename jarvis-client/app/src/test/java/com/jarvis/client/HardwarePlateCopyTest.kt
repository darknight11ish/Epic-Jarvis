package com.jarvis.client

import com.jarvis.client.ui.screens.HARDWARE_CLOSING_LINE
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Hardware plate's closing line (the audit of 2026-11-16, finding 1).
 *
 * The line used to read "Every number is calculated, not measured, until you
 * press Measure", 141 lines under the plate's own measured lines: each setup
 * prints `Hardware.measuredLine(p)` ("Measured on this PC." once a measurement
 * row exists), and the focus-preset costs above include dated measurements
 * ("Measured 2026-10-18: ...") and "Same measured setup as General" rows. The
 * same line also said "Nothing changes until you pick a setup", while a local
 * preset on the same plate "switches at once" (`FocusPresetsPlate.kt`'s own
 * introduction) - so the plate promised something the plate above it had
 * already broken.
 *
 * This is a NODE PIN, in the suite's usual shape (`SourceFile`): it holds the
 * facts the screen actually shows, and it fails if the false universal
 * ever comes back, if the line grows past the old 220 characters, or if the
 * measured lines it must not contradict are removed from above it. Change the
 * sentence and this test together - never one without the other.
 */
class HardwarePlateCopyTest {

    private val plate = SourceFile.read(
        "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HardwarePlate.kt",
    )

    /** The one `Text(...)` that draws the constant, not the constant's own declaration. */
    private val drawn = Regex("""Text\(\s*HARDWARE_CLOSING_LINE,""").find(plate)

    @Test
    fun `the closing line no longer calls every number calculated and unmeasured`() {
        assertFalse(
            "the old false universal is back in the closing line",
            HARDWARE_CLOSING_LINE.contains("Every number is calculated"),
        )
        assertFalse(
            "the closing line again says nothing is measured until Measure",
            HARDWARE_CLOSING_LINE.contains("not measured, until you press Measure"),
        )
    }

    @Test
    fun `the closing line no longer promises nothing changes before a setup`() {
        assertFalse(
            "the false promise to the preset rows above is back",
            HARDWARE_CLOSING_LINE.contains("Nothing changes until you pick a setup"),
        )
        // The conflation the audit found: on this plate "setup" and "preset"
        // are different buttons, and a local preset switches at once.
        assertFalse(
            "the closing line again reads as a promise the preset rows break",
            HARDWARE_CLOSING_LINE.contains("Nothing changes until"),
        )
    }

    @Test
    fun `the closing line says what calculated and dated lines actually are`() {
        assertTrue(
            "the calculated numbers are not described as estimates",
            HARDWARE_CLOSING_LINE.contains("Calculated lines are estimates"),
        )
        assertTrue(
            "the dated lines above are not described as older measurements",
            HARDWARE_CLOSING_LINE.contains("dated lines are older measurements"),
        )
        assertTrue(
            "the line does not say what Measure does now",
            HARDWARE_CLOSING_LINE.contains("press Measure to check this PC now"),
        )
    }

    @Test
    fun `the closing line keeps the setup and privacy truths`() {
        assertTrue(
            "picking a setup is not said to change nothing by itself",
            HARDWARE_CLOSING_LINE.contains("Picking a setup changes nothing by itself"),
        )
        assertTrue(
            "the privacy promise is gone",
            HARDWARE_CLOSING_LINE.contains("Nothing here sends anything off your PC"),
        )
    }

    @Test
    fun `the closing line is drawn once, under the measured lines, and stays phone-sized`() {
        assertTrue("the closing line is not drawn at all", drawn != null)
        assertEquals(
            "the closing line must be one constant drawn once",
            2,
            Regex("HARDWARE_CLOSING_LINE").findAll(plate).count(),
        )
        // The old line was 220 characters on the smallest type on the phone.
        assertTrue(
            "the closing line is ${HARDWARE_CLOSING_LINE.length} characters; it must stay at or under 200",
            HARDWARE_CLOSING_LINE.length <= 200,
        )
        // The fact the old sentence denied: the setups' measured lines are
        // drawn above it, so a future edit cannot make the plate contradict
        // itself again by deleting them and keeping the sentence.
        val measured = plate.indexOf("Hardware.measuredLine(p)")
        assertTrue("the setups no longer draw their measured line", measured >= 0)
        assertTrue(
            "the closing line is drawn above the measured lines",
            (drawn?.range?.first ?: -1) > measured,
        )
    }
}
