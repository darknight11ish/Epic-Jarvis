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
 *
 * THE MUTATION ON THE RECORD, because a test that has never failed has not been
 * tested either. `if (expired) { ...buttons... }` - buttons drawn only while
 * expired, this defect with the branches swapped - **fails the first case**, as
 * it must.
 *
 * AND A WEAK MUTATION THAT PASSES IS THE SAME FALSE GREEN AS AN UNMUTATED FILE.
 * The first mutation tried here was `if (expired || !expired)`, which is
 * always true and draws the buttons in **both** states - and it **passed**,
 * because it still contains the literal `!expired` the check was looking for.
 * A guard that obviously wrong sailed through a check that only looked for the
 * word. That is why the assertion is on the SENSE of the guard now, and why
 * this note is here: **checking that a token is present is not checking what
 * the code does.**
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

    /**
     * THE THIRD CAUSE OF THE SAME SHAPE, measured on the same phone the same
     * evening: a **live** card the phone may not approve.
     *
     * `raise_api_limit` is in the backend's `PC_ONLY_ACTIONS`, so `canApprove`
     * is false for it and `decide()` refuses it - and yet the card drew a
     * dimmed **Approve** that could never work, beside a line telling the owner
     * to turn on signed approvals. Turning it on cannot help; he reported "it is
     * still not working".
     *
     * **Deny must survive**, and that is the part worth pinning: the phone's own
     * sentence for this card ends *"Deny still works here."* A test that only
     * asserted "no Approve" would pass on a row that had been emptied
     * altogether, which would make the app's own sentence a lie. So this asserts
     * both halves, and asserts them in the right places.
     */
    @Test
    fun `a pc-only card loses its Approve and keeps its Deny`() {
        val src = repoFile(card).readText()
        val row = buttonRow(src)

        // THE CODE FORM, NOT THE BARE TOKEN. This test failed its first run
        // because the row's own comment mentions `!item.pcOnly` in prose, and
        // the index landed on the comment instead of the guard - a check on
        // text positions fooled by the text beside them. Matching `if (`
        // and the brace can only match the statement.
        val pcGuard = row.indexOf("if (!item.pcOnly) {")
        assertTrue(
            "the card does not gate Approve on !item.pcOnly, so it can draw an Approve " +
                "that decide() will refuse whatever the owner does",
            pcGuard > 0,
        )

        // `Affirm` sits INSIDE the pcOnly guard; `Refuse` sits OUTSIDE it and
        // inside the expiry guard - i.e. Deny is drawn for a pcOnly card.
        val affirm = row.indexOf("Affirm(")
        assertTrue("the button row no longer draws Approve at all", affirm > 0)
        assertTrue(
            "Approve is drawn before the !item.pcOnly guard, so a pc-only card would show it",
            affirm > pcGuard,
        )
        val refuse = row.indexOf("Refuse(")
        assertTrue(
            "Deny is no longer drawn, but the card's own sentence promises 'Deny still works here'",
            refuse in 1 until pcGuard,
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
