package com.jarvis.client

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * DEF-010, measured on the owner's phone on 2026-10-11: he tapped **Approve**
 * several times on an approval card whose request had **expired**, nothing
 * happened, and nothing acknowledged the tap.
 *
 * The gate was already right - `canDecide` is false once the deadline passes, so
 * both buttons were disabled and correctly inert - and the sentence explaining
 * it was already drawn. **He tapped anyway**, because a faded control captioned
 * by a line he had not connected to it does not read as "you cannot act". The
 * fix is that an expired card draws the reason **where the buttons were**, so
 * there is nothing left to tap.
 *
 * WHY THIS TEST READS THE SOURCE, AND WHAT IT IS WORTH
 *
 * `ApprovalCard` is a `@Composable`, so a plain JVM test cannot compose it and
 * its `Role.Button` nodes. What this holds is the **structural** claim the fix
 * makes - the button row is guarded by `expired`, and no `Refuse`/`Affirm` call
 * can be reached while expired - which is the claim that would silently rot if
 * someone later moved a button outside the guard.
 *
 * It is NOT the strongest available check, and it should not be mistaken for
 * one: **it asserts the branch, not the drawn screen.** The real verification is
 * the device - an expired card must show the sentence and no buttons - and the
 * honest place to pin that is a Compose UI test, which this project does not
 * have. Said here so the next reader knows exactly how far this goes.
 */
class ExpiredCardShowsNoButtonsTest {

    private val card = "jarvis-client/app/src/main/java/com/jarvis/client/ui/approval/ApprovalCard.kt"

    /** The button row's own block, by brace depth, from its `Row(` to its close. */
    private fun buttonRow(src: String): String {
        val start = src.indexOf("AN EXPIRED CARD SHOWS NO BUTTONS")
        assertTrue("the button row's own comment is gone, so this test cannot find it", start > 0)
        val rowStart = src.lastIndexOf("Row(", start)
        var depth = 0
        var i = rowStart
        while (i < src.length) {
            when (src[i]) {
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) return src.substring(rowStart, i + 1)
                }
            }
            i++
        }
        error("the button row's block never closed")
    }

    @Test
    fun `the button row draws its buttons only when the card is not expired`() {
        val src = repoFile(card).readText()
        val row = buttonRow(src)

        val guard = row.indexOf("!expired")
        assertTrue("the button row is not guarded by `!expired`", guard > 0)

        // The buttons live inside the guard: reached only when NOT expired.
        val notExpired = row.substring(guard - 4)
        assertTrue(
            "the unexpired branch no longer draws Deny",
            notExpired.contains("Refuse("),
        )
        assertTrue(
            "the unexpired branch no longer draws Approve",
            notExpired.contains("Affirm("),
        )

        // And every decision button in the FILE is inside that guard - a second
        // one added outside it would be reachable while expired.
        val allButtons = Regex("\\b(Refuse|Affirm)\\(").findAll(src).count()
        val inRow = Regex("\\b(Refuse|Affirm)\\(").findAll(notExpired).count()
        assertTrue(
            "there are $allButtons decision buttons in this file but only $inRow inside the " +
                "`!expired` guard: one is reachable while the card is expired",
            allButtons == inRow && allButtons > 0,
        )

        // ONE COPY OF THE REASON, NOT TWO (the lead's ruling, 2026-10-11): the
        // red line above already carries it, so the empty row draws nothing.
        // The card's text must therefore hold the sentence exactly once, and
        // that one place is `why`.
        assertTrue(
            "the reason is no longer drawn anywhere, so an expired card would explain nothing",
            src.contains("expired -> EXPIRED_WHY"),
        )
    }

    @Test
    fun `the expiry wording has exactly one source`() {
        val src = repoFile(card).readText()
        val literal = Regex("Timed out — ask the desktop to raise this again\\.")
        val hits = literal.findAll(src).count()
        assertTrue(
            "the expiry sentence is written out $hits times: two copies let the reason and the " +
                "dead control drift apart, which is the defect itself",
            hits == 1,
        )
        assertTrue(
            "the one copy is not the exported constant the card draws",
            src.contains("private const val EXPIRED_WHY = \"Timed out — ask the desktop"),
        )
    }

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
}
