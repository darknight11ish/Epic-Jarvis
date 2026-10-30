package com.jarvis.client

import com.jarvis.client.ui.BottomReserve
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The room Settings keeps under its last card while the fixed "Needs your OK"
 * line is drawn over it - Gemini's `F4`, measured on the owner's phone
 * 2026-10-28.
 *
 * WHAT WAS WRONG, and why this is arithmetic in a JVM test. The line is drawn
 * by `MainActivity` in a `Box` the size of the screen, aligned to the bottom,
 * so it takes no room from the screen underneath. Settings' list padded its
 * bottom by 16 dp, so at max scroll the last card's last control - Devices'
 * "Unpair & clear the token" - sat under the line and could not be pressed.
 *
 * A Compose layout cannot be measured in `:app:testDebugUnitTest` (there is no
 * instrumentation runner in this project's CI, and no emulator), so this test
 * holds the two halves that CAN be held honestly:
 *
 *  1. **the geometry** - [BottomReserve]'s arithmetic, in dp, against the band
 *     the line really covers. One case is the defect itself: 16 dp of padding
 *     against a real line does not clear it, which is the exact overlap that
 *     was measured on the phone.
 *  2. **the wiring** - read off the sources, the way `SettingsSearchTest` and
 *     `PairFromSettingsTest` already hold Compose screens this project cannot
 *     render: the screen really adds the reserve to its bottom padding, and
 *     `MainActivity` really measures the drawn line and hands the result over.
 *
 * What it does NOT prove: that the rendered pixels are clear of the line on a
 * particular phone. That measurement is the device step in the report, and it
 * is written there as the layout maths plus the screen's own dumped bounds,
 * never as a passing test.
 */
class BottomReserveTest {

    /** Settings' own bottom margin, read off its `contentPadding` by a test below. */
    private val listPadDp = 16f

    @Test
    fun `the reserve is the covered band plus air, and nothing more`() {
        // A line one, two and three rows tall - the shapes it really takes:
        // one card's title fits one line, a long PC title wraps to two, and a
        // second waiting card adds the "and N more" line.
        for (line in listOf(44f, 84f, 120f)) {
            assertDp(
                line + BottomReserve.EDGE_DP + BottomReserve.GAP_DP,
                BottomReserve.forBanner(line),
                "the reserve for a ${line}dp line must be that line, the edge gap it " +
                    "sits in, and the air above it - no more, no less",
            )
            assertDp(
                line + BottomReserve.EDGE_DP,
                BottomReserve.coveredDp(line),
                "the band the line covers is its own height plus the edge gap",
            )
            // The reserve clears the band with exactly the gap left over.
            assertDp(
                BottomReserve.GAP_DP.toFloat(),
                BottomReserve.forBanner(line) - BottomReserve.coveredDp(line),
                "the air above the line is GAP_DP and not a coincidence",
            )
        }
    }

    @Test
    fun `the reserve clears the line at every height the line takes`() {
        for (line in listOf(20f, 44f, 84f, 120f, 200f)) {
            val bottom = listPadDp + BottomReserve.forBanner(line)
            assertTrue(
                "with ${listPadDp}dp of its own padding and a ${line}dp line, the list's " +
                    "bottom (${bottom}dp) must reach past the band the line covers " +
                    "(${BottomReserve.coveredDp(line)}dp)",
                bottom > BottomReserve.coveredDp(line),
            )
        }
    }

    /**
     * THE DEFECT ITSELF, kept as a test so the fix cannot be undone by putting
     * the old padding back: 16 dp against a line of any real height leaves the
     * line's top ABOVE the list's bottom edge, which is the overlap seen on the
     * phone (a 6 px sliver of "Unpair & clear the token", unreachable at max
     * scroll).
     */
    @Test
    fun `sixteen dp of padding alone is the overlap that was measured`() {
        val line = 84f
        val oldBottom = listPadDp
        assertFalse(
            "the OLD padding must be shown to be too small, or the fix proves nothing",
            oldBottom > BottomReserve.coveredDp(line),
        )
        assertTrue(
            "the old padding was short of the line by nearly the whole line",
            BottomReserve.coveredDp(line) - oldBottom > 40f,
        )
    }

    @Test
    fun `a nonsense measurement reserves nothing rather than too little`() {
        // A negative or zero measurement is the state before the line has ever
        // been drawn. It must read as "no line" (the edge gap and air only),
        // never as a negative reserve that would pull the padding below zero.
        assertDp(
            (BottomReserve.EDGE_DP + BottomReserve.GAP_DP).toFloat(),
            BottomReserve.forBanner(0f),
            "no measurement at all reads as the edge gap and the air, and nothing else",
        )
        assertDp(
            (BottomReserve.EDGE_DP + BottomReserve.GAP_DP).toFloat(),
            BottomReserve.forBanner(-50f),
            "a negative measurement must read the same way, not as a negative reserve",
        )
        assertTrue("a reserve is never negative", BottomReserve.forBanner(-50f) > 0f)
    }

    // ---- the wiring, read off the sources -------------------------------

    @Test
    fun `Settings adds the reserve to its own bottom padding`() {
        val screen = source("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/SettingsScreen.kt")
        assertTrue(
            "SettingsScreen must take the reserve as a parameter (default 0, so previews " +
                "and tests are unaffected)",
            screen.contains("bottomReserve: Dp = 0.dp"),
        )
        assertTrue(
            "the list's own 16dp must be joined by the reserve, or the last card still " +
                "sits under the line",
            screen.contains("bottom = 16.dp + bottomReserve"),
        )
    }

    @Test
    fun `MainActivity measures the drawn line and hands the room to Settings`() {
        val main = source("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        assertTrue(
            "the line must be MEASURED as it is drawn - a typed-in height is wrong the " +
                "moment the PC's card title wraps",
            main.contains("Box(Modifier.onSizeChanged { waitingLinePx = it.height })"),
        )
        assertTrue(
            "the reserve must come from BottomReserve, which owns the edge gap and the air",
            main.contains("BottomReserve.forBanner(waitingLineDp.value)"),
        )
        assertTrue(
            "Settings must be handed the room, or none of the rest matters",
            main.contains("bottomReserve = settingsBottomReserve,"),
        )
        assertTrue(
            "the line's own edge gap is BottomReserve.EDGE_DP - a second 12.dp here " +
                "would drift from the reserve and overlap again",
            main.contains(".padding(BottomReserve.EDGE_DP.dp)"),
        )
        assertTrue(
            "the line is drawn only where it is reserved: the same `waitingLineShown` " +
                "decides both",
            main.contains("if (waitingLineShown)") &&
                main.contains("val waitingLineShown = screen != Screen.HOME && pending.isNotEmpty()"),
        )
    }

/**
     * The one numeric assertion this file uses: a dp value against a dp value,
     * with a tolerance far below a pixel. Written out because JUnit 4 has no
     * `assertEquals(String, Float, Float, Float)` - the overloads for `double`
     * and `long` do not resolve against `Float`, and a test that does not
     * compile proves nothing.
     */
    private fun assertDp(expected: Float, actual: Float, message: String) =
        assertEquals(message, expected.toDouble(), actual.toDouble(), 0.001)

    /** A file under the repository, found by walking up from Gradle's folder. */
    private fun source(rel: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f.readText()
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }
}
