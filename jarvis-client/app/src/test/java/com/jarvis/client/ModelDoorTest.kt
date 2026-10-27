package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The lane pill under the face is the owner's one door to the model list
 * (owner's ask of 2026-10-27: the model name at the top becomes a button that
 * opens the current-models menu). Navigation only - it reuses the Brain's
 * existing "models" place through [com.jarvis.client.ui.screens.HomeActions.onOpenModelChoices],
 * the action the plain-word model errors already use, so no route, no write and
 * no new callback exists.
 *
 * Off-device, the [PresetsLandingTest] way: there is no emulator here, so the
 * wiring is held by reading the shipped source for the exact lines. The real
 * phone look is a field-test row, not a pass.
 */
class ModelDoorTest {

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

    private val home: String by lazy { source("ui/screens/HomeScreen.kt") }

    private fun chipBody(): String =
        home.substringAfter("private fun LaneChip(").substringBefore("\n}")

    @Test
    fun `the pill is drawn with the one existing model action`() {
        assertTrue(
            "the lane pill still calls the old no-action LaneChip",
            home.contains("LaneChip(state.status, onOpenModels = actions.onOpenModelChoices)"),
        )
        assertTrue(
            "LaneChip was not given the model action",
            home.contains("private fun LaneChip(status: StatusInfo?, onOpenModels: () -> Unit)"),
        )
        // The same action, not a second one: declaration once, used by the
        // plain-word model errors and by this pill - two uses, no more.
        assertEquals(
            "the model door adds an action of its own",
            1,
            home.split("val onOpenModelChoices: () -> Unit").size - 1,
        )
        assertEquals(
            "the model door is not the second user of the one model action",
            2,
            home.split("actions.onOpenModelChoices").size - 1,
        )
    }

    @Test
    fun `tapping the pill presses and reads as the model name`() {
        val chip = chipBody()
        assertTrue("the pill is not pressable", chip.contains(".pressable(onClick = onOpenModels)"))
        assertTrue(
            "the pill has no spoken model name",
            chip.contains("contentDescription = \"Model: \$words\""),
        )
        // The 48dp minimum is invisible growth around the child, so the pill has
        // to sit in a Box or the press paints a 48dp-tall chip.
        assertTrue("the press minimum is not wrapped away from the pill", chip.contains("Box("))
        assertTrue(chip.contains("contentAlignment = Alignment.Center"))
    }

    @Test
    fun `the door only navigates - it holds no api or model action`() {
        val chip = chipBody()
        listOf("/api/", "api.post", "postCard", "installModel", "switchModel", "rollbackModel").forEach {
            assertFalse("the model pill gained a write: $it", chip.contains(it))
        }
        // And it is drawn with the rest of the caption strip, not behind it.
        assertTrue(
            "the pill is drawn after the caption row's condition",
            home.indexOf("LaneChip(state.status") < home.indexOf("if (showCaption)"),
        )
    }

    @Test
    fun `the action still opens the Brain at its models plate`() {
        val activity = source("MainActivity.kt")
        val action = activity.substringAfter("onOpenModelChoices = {").substringBefore("onOpenGalaxy")
        assertTrue("the model action no longer names the models section", action.contains("pendingSection = \"models\""))
        assertTrue("the model action targets another screen", action.contains("pendingSectionScreen = Screen.BRAIN.name"))
        assertTrue("the model action does not open Brain", action.contains("nav.go(Screen.BRAIN)"))
        // The one-time visit rule every place obeys, so a rotation cannot open twice.
        val consumed = activity.substringAfter("val sectionConsumed: () -> Unit = {")
            .substringBefore("LaunchedEffect(openSettingsTarget)")
        assertTrue("the anchor is never consumed", consumed.contains("pendingSection = null"))
    }
}
