package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * N3 and N4 of the second Android audit (`docs/ANDROID-AUDIT-2-2026-10-09.md`,
 * 2026-10-09) stay fixed.
 *
 * **N3** was a hazard rather than a live defect, in the one place a
 * notification sends the owner to decide something: Home's "Open the
 * approval →" found its card by adding up the conditional items above the
 * cards by hand - ten expressions that a comment asked the next person to keep
 * in step. It is now the card's own key, and the walk it uses can start from
 * the top, because Home can be opened with the thread scrolled anywhere.
 *
 * **N4** was cosmetic: `if (showCompare && c != null)`, where the compiler
 * proved the second half always true, so every build printed "Condition is
 * always 'true'." - harmless, and worth deleting so a real warning is not lost
 * in it.
 *
 * Source-reading: both are about what the code does instead of counting, which
 * a JVM test can hold without a phone.
 */
class Audit2RemainingTest {

    @Test
    fun `the approval focus scrolls to the card's own key, not a counted position`() {
        val home = repoFile(HOME).readText()
        // The key this relies on: every approval card is keyed by its id.
        assertTrue(
            "the approval cards are no longer keyed by their own id",
            home.contains("items(state.pending, key = { it.id })"),
        )
        assertTrue(
            "the focus no longer scrolls by the card's key",
            home.contains("scrollToKey(listState, id, fromTop = true)"),
        )
        assertFalse("the hand-kept item count is back", home.contains("val leading ="))
        assertFalse("the counted scroll is back", home.contains("leading + index"))
    }

    @Test
    fun `the key walk can start from the top, and ScrollToKeyOnce keeps its own behaviour`() {
        val helper = repoFile(SCROLL).readText()
        assertTrue(
            "scrollToKey is not the shared, callable form",
            helper.contains(
                "suspend fun scrollToKey(state: LazyListState, key: String, fromTop: Boolean = false): Boolean",
            ),
        )
        assertTrue(
            "fromTop must really go to the first item before walking down",
            helper.contains("if (fromTop) state.scrollToItem(0)"),
        )
        // Settings' jump list and "open a place" open a screen at the top and
        // have no opinion about starting there.
        assertTrue("ScrollToKeyOnce no longer uses the shared walk", helper.contains("scrollToKey(state, target)"))
    }

    @Test
    fun `the always-true condition in the chatbot plate is gone`() {
        val plate = code(repoFile(CHATBOT).readText())
        assertFalse(
            "the compiler's \"Condition is always 'true'\" is back",
            plate.contains("showCompare && c != null"),
        )
        assertTrue(
            "the non-null comparison is not bound once",
            plate.contains("val shownCompare = if (showCompare) c else null"),
        )
    }

    /**
     * Just the code, with whole-line `//` comments dropped - the same helper
     * [SettingsJumpTest] uses, and it is needed here: the comment that explains
     * what N4 was names the deleted condition on purpose, and an assertion on
     * what the file DOES must not be satisfied or broken by that comment.
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
        const val HOME = BASE + "ui/screens/HomeScreen.kt"
        const val SCROLL = BASE + "ui/parts/ScrollToKey.kt"
        const val CHATBOT = BASE + "ui/screens/ChatbotPlate.kt"
    }
}
