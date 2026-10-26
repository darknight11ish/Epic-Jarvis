package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The 2026-10-25 accessibility-honesty slice, held by reading the shipped
 * service source - the way [AppControlSensitiveFindTest] holds `find()`.
 *
 * There is no Android compiler in this checkout (`dl.google.com` is blocked),
 * so CI's Gradle build is the first compile and no phone has ever run this.
 * These are SOURCE pins: they prove the rule is written down in the one place
 * the service reads and acts, not that a device behaved. The pure rules
 * themselves are exercised by [AppControlTest] (`blankTree`, `textTook`).
 *
 * Nothing here is a runtime pass. The service stays NOT-TESTABLE / a
 * field-test row, never a green tick.
 */
class AppControlHonestyTest {

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private val servicePath =
        "jarvis-client/app/src/main/java/com/jarvis/client/service/JarvisAccessibilityService.kt"
    private val executorPath =
        "jarvis-client/app/src/main/java/com/jarvis/client/service/AppControlExecutor.kt"

    private fun source(rel: String): String = repoFile(rel).readText()

    /** The text between two markers, so a pin cannot pass on a neighbour's line. */
    private fun between(src: String, start: String, end: String): String {
        val at = src.indexOf(start)
        assertTrue("$start is gone from the source", at >= 0)
        val from = at + start.length
        val to = src.indexOf(end, from)
        assertTrue("$end is gone after $start", to > from)
        return src.substring(from, to)
    }

    private fun occurrences(src: String, needle: String): Int =
        Regex(Regex.escape(needle)).findAll(src).count()

    // ------------------------------------------------- (a) blank tree ------

    @Test
    fun aScreenWithNothingOnItIsRefusedWithItsOwnCodeNotAnEmptySnapshot() {
        val service = source(servicePath)
        val read = between(service, "fun readScreen(): Read {", "fun performStep(")
        assertTrue(
            "a blank screen must be refused with ui_tree_blank",
            read.contains("AppControl.CODE_BLANK_TREE"),
        )
        assertTrue(
            "the refusal must carry a plain sentence",
            read.contains("AppControl.BLANK_TREE"),
        )
        assertTrue(
            "with no window or no readable node the read must be a refusal VALUE",
            read.contains("Read.Unreadable("),
        )
        assertTrue(
            "the rule must come from the one pure helper, not be re-typed",
            read.contains("AppControl.blankTree("),
        )
        assertFalse(
            "readScreen() must never quietly return null or an empty snapshot",
            read.contains("return null"),
        )
        assertFalse(
            "the old silent 'no window means null' line is what this slice removed",
            service.contains("rootInActiveWindow ?: return null"),
        )
        // The runtime must refuse with the code rather than send the empty screen.
        val executor = source(executorPath)
        assertTrue(
            "the executor must turn an unreadable screen into a coded refusal",
            executor.contains("is JarvisAccessibilityService.Read.Unreadable ->") &&
                executor.contains("return Reply.Refused(read.sentence, read.code)"),
        )
        assertFalse(
            "an unreadable screen must never be sent to the PC as a snapshot",
            executor.contains("service?.snapshot()"),
        )
    }

    // ------------------------------------------------- (b) read-back ------

    @Test
    fun aTypeIsOnlyDoneAfterTheFieldReadsTheWordsBack() {
        val service = source(servicePath)
        val type = between(
            service,
            "private fun type(step: AppControl.Step): Outcome {",
            "private fun editableTarget(",
        )
        val setAt = type.indexOf("ACTION_SET_TEXT")
        val readBackAt = type.indexOf("AppControl.textTook(")
        val doneAt = type.indexOf("Outcome.Done")
        assertTrue("type() no longer sets text", setAt >= 0)
        assertTrue(
            "the field's own text must be read back after SET_TEXT",
            readBackAt > setAt,
        )
        assertTrue(
            "Done must come only after the read-back check",
            doneAt > readBackAt,
        )
        assertTrue(
            "the read-back must be from the field itself",
            type.contains("node.text"),
        )
        assertTrue(
            "a field that did not keep the words must carry its own code",
            type.contains("AppControl.CODE_TEXT_NOT_TAKEN"),
        )
        assertFalse(
            "Android's own true must never be taken as proof the words were typed",
            type.contains(
                "if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return Outcome.Done",
            ),
        )
    }

    // ------------------------------------- (c) no picture / pixel fallback --

    @Test
    fun theServiceHasNoScreenshotOrRawPixelFallback() {
        val service = source(servicePath)
        // No picture APIs: a screen Jarvis cannot read is REFUSED, and the
        // PC's action set has no screenshot action by design.
        for (api in listOf(
            "takeScreenshot",
            "Bitmap",
            "ImageReader",
            "PixelCopy",
            "MediaProjection",
        )) {
            assertFalse("$api is a picture path this service must not have", service.contains(api))
        }
        // Exactly one pixel tap: the guarded gesture on the approved target's
        // OWN bounds inside tap(). A second one would be a guessed fallback.
        assertEquals(
            "there must be one guarded tap and no second, guessed pixel tap",
            2,
            occurrences(service, "dispatchTap("),
        )
        // The blank-tree refusal is the fallback: it is named, not bypassed.
        assertTrue(service.contains("AppControl.CODE_BLANK_TREE"))
    }
}
