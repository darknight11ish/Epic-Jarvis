package com.jarvis.client

import com.jarvis.client.net.Tasks
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The eight findings the first Android audit left standing
 * (`docs/ANDROID-AUDIT-2026-10-08.md`, still recorded as open by the second
 * audit's Part 1): findings 4, 5, 7, 8, 9, 10, 11 and 12.
 *
 * All eight are small - wording, a state that could never be constructed, a
 * control that could open the wrong row - so each is held here by reading the
 * source, the same shape [LinkWordsTest]'s screen check uses. The one that is
 * pure logic (finding 10's "Reading…" line) is asserted as behaviour.
 */
class FirstAuditLeftoversTest {

    @Test
    fun `finding 4 - the Security footer no longer promises that turning on is instant`() {
        val screen = code(repoFile(SECURITY).readText())
        assertFalse(
            "two switches on this screen ask for the fingerprint on the way ON",
            screen.contains("Turning something on is instant"),
        )
        assertTrue(
            "the loosening rule must still be stated",
            screen.contains("making it looser, asks for your fingerprint or PIN"),
        )
    }

    @Test
    fun `finding 5 - the standby offer survives the process death its flag survives`() {
        val main = code(repoFile(MAIN).readText())
        assertFalse(
            "the offer payload is a plain remember again, and dies with the process",
            main.contains("var cachedSleepOffer by remember {"),
        )
        assertTrue(
            "the payload is not saved through its own Saver",
            main.contains("rememberSaveable(stateSaver = sleepOfferSaver)"),
        )
        assertTrue(
            "the Saver must carry the offer's own JSON text",
            main.contains("JarvisJson.parseToJsonElement(it).jsonObject"),
        )
    }

    @Test
    fun `finding 7 - the Never-look-at picker does not walk every app on the main thread`() {
        val look = code(repoFile(LOOK).readText())
        assertTrue(
            "the walk is not off the main thread",
            look.contains("withContext(Dispatchers.IO)"),
        )
        assertTrue("the picker says it is looking", look.contains("Looking for apps…"))
        assertFalse(
            "installedApps is back inside a remember, during composition",
            look.contains("val candidates = remember("),
        )
    }

    @Test
    fun `finding 8 - Show everything saved automatically goes to the row, not to the next item`() {
        val brain = code(repoFile(BRAIN).readText())
        assertFalse("the by-index arithmetic is back", brain.contains("animateScrollToItem(here + 1)"))
        assertTrue(
            "the row is no longer scrolled to by key",
            brain.contains("scrollToKey(listState, \"memory-auto\")"),
        )
        assertTrue(
            "a hidden row must be shown for the visit, or the key is not there at all",
            brain.contains("showForVisit(\"brain.memory.auto\")"),
        )
    }

    @Test
    fun `finding 9 - the reset button says what it does`() {
        val plate = code(repoFile(RETIREMENT).readText())
        assertFalse("the old label is back", plate.contains("\"Clear the numbers\""))
        assertTrue("the label does not match what the tap does", plate.contains("\"Start over\""))
    }

    @Test
    fun `finding 10 - Reading can really be drawn, and says so`() {
        // The pure half: the line the plate draws for that state.
        assertEquals("Reading…", Tasks.readLine(Tasks.Read.Reading))
        // The half that makes it reachable: the plate sets it before the call.
        val plate = code(repoFile(TASKS).readText())
        val first = plate.substringAfter("if (read is Tasks.Read.NotAsked)").take(400)
        assertTrue(
            "the plate must say it is reading before the first read returns",
            first.contains("read = Tasks.Read.Reading"),
        )
        assertTrue("and then still do the read", first.contains("JarvisRuntime.tasks()"))
    }

    @Test
    fun `finding 11 - the Hear-it result line is drawn once`() {
        val voices = code(repoFile(VOICES).readText())
        assertEquals(
            "the same line is drawn twice again",
            1,
            Regex(Regex.escape("saidFor == c.id && said.isNotBlank()")).findAll(voices).count(),
        )
        assertFalse(
            "the mirrored predicate is back",
            voices.contains("said.isNotBlank() && saidFor == c.id"),
        )
    }

    @Test
    fun `finding 12 - one setting has one name on the screen that shows it twice`() {
        val editor = code(repoFile(FACE_EDITOR).readText())
        val options = code(repoFile(ANIMAL_OPTIONS).readText())
        assertFalse("the per-face editor calls it Quality again", editor.contains("title = \"Quality\""))
        assertTrue("the per-face editor does not call it Sharpness", editor.contains("title = \"Sharpness\""))
        assertTrue(
            "the other section must use the same word",
            options.contains("title = \"Sharpness\""),
        )
    }

    /**
     * Just the code, with whole-line `//` comments dropped - the helper
     * [SettingsJumpTest] and [Audit2RemainingTest] use. It is needed here: the
     * comment that explains what each finding WAS names the deleted label, the
     * deleted predicate and the deleted arithmetic on purpose, and an assertion
     * on what a file DOES must not be satisfied or broken by those comments.
     */
    private fun code(text: String): String =
        text.lines().filterNot { it.trimStart().startsWith("//") }.joinToString("\n")

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private companion object {
        const val BASE = "jarvis-client/app/src/main/java/com/jarvis/client/"
        const val MAIN = BASE + "MainActivity.kt"
        const val SECURITY = BASE + "ui/screens/SecurityScreen.kt"
        const val LOOK = BASE + "ui/screens/LookPlate.kt"
        const val BRAIN = BASE + "ui/screens/BrainScreen.kt"
        const val RETIREMENT = BASE + "ui/screens/RetirementPlate.kt"
        const val TASKS = BASE + "ui/screens/TasksPlate.kt"
        const val VOICES = BASE + "ui/screens/VoicesScreen.kt"
        const val FACE_EDITOR = BASE + "ui/screens/FaceEditor.kt"
        const val ANIMAL_OPTIONS = BASE + "ui/screens/AnimalOptionsPlate.kt"
    }
}

