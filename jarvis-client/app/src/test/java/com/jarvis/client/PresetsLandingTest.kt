package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.FocusPresets
import com.jarvis.client.net.Hardware
import com.jarvis.client.ui.OpenPlace
import com.jarvis.client.ui.Screen
import com.jarvis.client.ui.screens.BrainSections
import com.jarvis.client.ui.screens.MoreMenuWords
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "More -> Jarvis Presets" (owner report 2026-10-26) landed on the Brain's
 * Hardware plate but the plate sat at "Asking your PC…" and the preset rows
 * were never drawn.
 *
 * There is no emulator here, so the two wiring rules are held the way
 * [AuditPlumbingTest] holds its Compose rules - by reading the shipped source
 * for the exact line. The read-state rules are plain data and are exercised for
 * real. This is a source pin plus behaviour test, not a device pass: the
 * on-phone check is in the PR body.
 */
class PresetsLandingTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    @Test
    fun `the More row and its action land on Brain hardware`() {
        val where = OpenPlace.whereFor("focus-presets")
        assertTrue("focus-presets is not a Where.Go: $where", where is OpenPlace.Where.Go)
        where as OpenPlace.Where.Go
        assertEquals(Screen.BRAIN, where.screen)
        assertEquals("hardware", where.section)

        // The anchor the Brain walk opens: the Hardware plate must be placed
        // under the heading it will open, or the scroll has nothing to find.
        val section = BrainSections.sectionOf("hardware")
        assertNotNull("no heading holds hardware, so the anchor lands nowhere", section)
        assertEquals("the anchor would not open its heading", section!!.key, BrainSections.toOpen("hardware"))
        assertTrue("the Hardware heading does not contain the hardware plate", section.plateKeys.contains("hardware"))

        // The More row itself: it names the destination and calls the action.
        val home = source("ui/screens/HomeScreen.kt")
        assertTrue("the More row does not offer Jarvis Presets", home.contains("MoreMenuWords.PRESETS"))
        assertTrue("the More row does not call actions.onOpenPresets()", home.contains("actions.onOpenPresets()"))
        assertTrue("the More row does not name its destination", home.contains("detail = MoreMenuWords.PRESETS_DETAIL"))
        assertTrue(MoreMenuWords.PRESETS_DETAIL.contains("Brain"))
        assertTrue(MoreMenuWords.PRESETS_DETAIL.contains("Hardware"))

        // The action's own body is the one that opens Brain at hardware.
        val activity = source("MainActivity.kt")
        assertTrue("MainActivity has no onOpenPresets action", activity.contains("onOpenPresets = {"))
        val action = activity.substringAfter("onOpenPresets = {").substringBefore("onOpenGalaxy")
        assertTrue("the action does not target the hardware section", action.contains("pendingSection = \"hardware\""))
        assertTrue("the action targets another screen", action.contains("pendingSectionScreen = Screen.BRAIN.name"))
        assertTrue("the action does not open Brain", action.contains("nav.go(Screen.BRAIN)"))

        // One visit consumes the section, so a rotation cannot act on it twice -
        // the same one-time-request rule Settings and the rest of the app use.
        val consumed = activity.substringAfter("val sectionConsumed: () -> Unit = {")
            .substringBefore("LaunchedEffect(openSettingsTarget)")
        assertTrue("the anchor is never consumed", consumed.contains("pendingSection = null"))
        assertTrue("the anchor screen is never cleared", consumed.contains("pendingSectionScreen = null"))
        val brain = source("ui/screens/BrainScreen.kt")
        assertTrue("the anchor never calls its consume callback", brain.contains("onDone = onSectionConsumed"))
        assertTrue("the anchor walk is gone", brain.contains("ScrollToKeyOnce("))
        assertTrue("the anchor no longer names the plate key", brain.contains("initialSection?.let { plateKeyAt(it) }"))
    }

    @Test
    fun `Home offers a one-tap Presets entry beside the Galaxy`() {
        val home = source("ui/screens/HomeScreen.kt")
        val galaxyAt = home.indexOf("\"The Galaxy →\"")
        val presetsAt = home.indexOf("\"Presets →\"")
        assertTrue("the Galaxy entry is gone, so there is nothing to sit beside", galaxyAt > 0)
        assertTrue("Home has no one-tap \"Presets →\" entry", presetsAt > galaxyAt)

        // Beside the Galaxy, in the same row of doors ([ModelDoorsRow]): nothing
        // conditional and no More dialog sits between the two labels, and since
        // 2026-10-27 the row is drawn with the face AND without it (Face size
        // Hidden, keyboard up) - one tap from Home, not a new screen and not a
        // second copy behind the More button (which stays as well).
        val between = home.substring(galaxyAt, presetsAt)
        assertTrue("the Presets entry is not beside the Galaxy", between.length < 1400)
        assertFalse("a second condition gates the Presets entry", between.contains("if ("))
        assertFalse("the Presets entry is in the More dialog, not Home's row", between.contains("MoreMenu"))

        // It calls the SAME action the More row calls - the one MainActivity
        // wires to Brain + hardware - and declares no action of its own.
        val button = home.substring(presetsAt, minOf(home.length, presetsAt + 700))
        assertTrue(
            "the Presets entry does not call Home's one presets action",
            button.contains(".pressable(onClick = actions.onOpenPresets)"),
        )
        assertEquals(
            "the More row and the Home entry must use the same one action",
            2,
            home.split("actions.onOpenPresets").size - 1,
        )
        assertEquals(
            "the Home entry must not add an action of its own",
            1,
            home.split("val onOpenPresets: () -> Unit").size - 1,
        )
        assertTrue(
            "the More row must stay - the new entry is the easily accessible one, not a replacement",
            home.contains("MoreMenuWords.PRESETS"),
        )

        // TalkBack is given a name, not the arrow glyph read as punctuation.
        assertTrue(
            "the Presets entry has no read-aloud name",
            button.contains("contentDescription = \"Jarvis presets\""),
        )

        // Navigation only: no read, no route, no write, no apply button.
        assertFalse("the Presets entry names a route", button.contains("/api/"))
        assertFalse("the Presets entry posts", button.contains("api.post"))
        for (w in listOf("applyPreset", "focusPresetApply", "installModel", "switchModel")) {
            assertFalse("the Presets entry calls $w", button.contains(w))
        }
    }

    @Test
    fun `the presets are drawn without waiting for the hardware read`() {
        val plate = source("ui/screens/HardwarePlate.kt")
        val section = plate.substringAfter("internal fun HardwareSection")
        // Before the fix this call existed exactly once, inside the `status != null`
        // branch, so a not-yet-loaded (or failed) hardware read hid the presets for
        // ever and their own /api/work read never ran. Two calls = both branches.
        val presetsCalls = section.split("FocusPresetsSection(canAct)").size - 1
        assertTrue(
            "the preset rows are still hidden behind a successful hardware read (calls=$presetsCalls)",
            presetsCalls >= 2,
        )
        val notLoaded = section.substringAfter("if (status == null)").substringBefore("} else {")
        assertTrue("the not-loaded branch does not draw the presets", notLoaded.contains("FocusPresetsSection(canAct)"))
        assertTrue("the not-loaded branch does not say the hardware read's words", notLoaded.contains("Hardware.readLine(read)"))
        assertTrue("the not-loaded branch has no retry", notLoaded.contains("Try again"))
        val loaded = section.substringAfter("} else {")
        val firstPresets = loaded.indexOf("FocusPresetsSection(canAct)")
        val firstCards = loaded.indexOf("Kicker(\"Your cards\"")
        assertTrue(
            "the loaded plate puts the presets below the cards again (presets=$firstPresets cards=$firstCards)",
            firstPresets >= 0 && firstCards > firstPresets,
        )
        assertTrue("the plate does not ask for the hardware itself", section.contains("refreshHardware()"))
    }

    @Test
    fun `neither Refreshing nor Asking your PC can last for ever`() {
        val brain = source("ui/screens/BrainScreen.kt")
        assertTrue("the header has no stuck timer", brain.contains("BRAIN_REFRESH_STUCK_MS"))
        assertTrue("the header cannot leave Refreshing", brain.contains("refreshStuck"))
        assertTrue("the header is not actually switched", brain.contains("if (showRefreshing) \"Refreshing…\" else \"Refresh\""))
        val runtime = source("JarvisRuntime.kt")
        assertTrue("the hardware read has no timeout", runtime.contains("HARDWARE_READ_TIMEOUT_MS = 25_000L"))
        assertTrue("the hardware read does not use its timeout", runtime.contains("withTimeoutOrNull(HARDWARE_READ_TIMEOUT_MS)"))
        assertTrue("the timed-out hardware read has no plain-words line", runtime.contains("Hardware.DID_NOT_ANSWER"))
        val presetsPlate = source("ui/screens/FocusPresetsPlate.kt")
        assertTrue("a not-asked presets read still says Update", presetsPlate.contains("FocusPresets.ASKING"))
        assertTrue("a failed presets read has no retry", presetsPlate.contains("Try again"))
    }

    @Test
    fun `a failed or unasked hardware read ends in words and a try-again`() {
        val failed = Hardware.readLine(Hardware.Read.Failed(Hardware.DID_NOT_ANSWER))
        assertEquals("the failed hardware read does not show its reason", Hardware.DID_NOT_ANSWER, failed)
        assertTrue("the timeout line does not say what to do", Hardware.DID_NOT_ANSWER.contains("Try again"))
        val asking = Hardware.readLine(Hardware.Read.NotAsked)
        assertNotNull("the not-asked line vanished", asking)
        assertTrue("the not-asked line is blank", asking!!.isNotBlank())
        assertTrue(
            "an empty answer does not become a failure",
            Hardware.readOf(ApiResult.Ok(kotlinx.serialization.json.JsonObject(emptyMap()))) is Hardware.Read.Failed,
        )

        val failedPresets = FocusPresets.readOf(
            ApiResult.Failed(ApiError.Unreachable("the PC did not answer")),
        )
        assertTrue("a failed presets read is not a Failed line", failedPresets is FocusPresets.Read.Failed)
        assertTrue(
            "the failed presets line is blank",
            (failedPresets as FocusPresets.Read.Failed).words.isNotBlank(),
        )
        assertTrue("the presets asking line is blank", FocusPresets.ASKING.isNotBlank())
    }
}
