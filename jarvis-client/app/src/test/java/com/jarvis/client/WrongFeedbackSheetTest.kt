package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Wrong sheet's WIRING (Wave 10, 2026-11-08): what the phone's answer menu
 * and network layers actually call.
 *
 * These are SOURCE PINS, the same shape as [ChatMenuTest] and
 * [ReadAloudWiringTest]: a Compose screen cannot be driven from a JVM unit
 * test in this project (there is no Android build in a unit-test run), so the
 * arrangement - chips, box, Cancel, "Just mark it wrong", Send, the receipt -
 * is held still by reading the screen, while the RULES it calls are proved for
 * real in [WrongFeedbackTest] and [LearningTest]. What a pin cannot prove is
 * said in the report: the sheet opens, looks right and sends on a real phone.
 *
 * What is held here:
 *  - Wrong on an answer that is not wrong opens the sheet, and Wrong on an
 *    already-wrong answer still takes the mark back at once;
 *  - the sheet shows the owner's five reasons, the one-line correction with
 *    the 500-character cap, Cancel, "Just mark it wrong", Send and the PC's
 *    own receipt;
 *  - it sends through the ONE v2 runtime call, from the submit branch only, so
 *    nothing goes out on a dismiss;
 *  - it approves nothing: no approval path, no card answer, no token in it;
 *  - the old Right/Wrong immediate mark is untouched on the Right half.
 */
class WrongFeedbackSheetTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val net = "jarvis-client/app/src/main/java/com/jarvis/client/net/"
    private val root = "jarvis-client/app/src/main/java/com/jarvis/client/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }
    private val api by lazy { SourceFile.read(net + "JarvisApi.kt") }
    private val runtime by lazy { SourceFile.read(root + "JarvisRuntime.kt") }
    private val feedback by lazy { SourceFile.read(net + "Feedback.kt") }
    private val learning by lazy { SourceFile.read(net + "Learning.kt") }

    private fun bodyOf(marker: String, text: String): String =
        text.substringAfter(marker, "").substringBefore("\n/**")

    /** One function's body, cut at the next declaration (a doc comment or a new top-level function). */
    private fun fnOf(marker: String, text: String): String {
        val rest = text.substringAfter(marker, "")
        if (rest.isEmpty()) return ""
        var cut = rest.length
        for (next in listOf(
            "\n/**", "\n    /**", "\n    suspend fun ", "\n    private suspend fun ",
            "\n    fun ", "\n    private fun ", "\n    internal fun ",
        )) {
            val at = rest.indexOf(next)
            if (at in 0 until cut) cut = at
        }
        return rest.substring(0, cut)
    }

    private val menu by lazy { bodyOf("private fun MessageMenu(", home) }
    private val sheet by lazy { bodyOf("private fun WrongFeedbackSheet(", home) }

    // ---- 1. How the sheet opens, and what the Right half still does ---------

    @Test
    fun `Wrong opens the sheet, and an already-wrong answer still takes it back`() {
        assertTrue("Wrong never opens the sheet", menu.contains("WrongFeedbackSheet("))
        assertTrue(
            "the sheet is never opened for the answer Wrong was tapped on",
            menu.contains("wrongFor = turnId"),
        )
        // The one distinction: not already wrong opens the sheet; already wrong
        // is the old "tap Wrong again to take it back" path, unchanged.
        assertTrue(
            "Wrong does not check the answer's current mark",
            menu.contains("tapped == AnswerMark.WRONG && feedback.mark != AnswerMark.WRONG"),
        )
        assertTrue("the old immediate path is gone", menu.contains("onMark(turnId, tapped)"))
        // Right goes straight to the existing immediate mark, as it always did.
        assertTrue(
            "the Right half no longer sends its immediate mark",
            bodyOf("private fun AnswerMarkRows(", home)
                .contains("onMark(feedback.turnId, AnswerMark.RIGHT)"),
        )
        // Still ONE surface: the menu's own dialog, swapped in place.
        assertTrue(menu.contains("Dialog(onDismissRequest = onDismiss)"))
        assertTrue("the sheet is a second dialog", !sheet.contains("Dialog("))
    }

    // ---- 2. The sheet's controls: the owner's own words ---------------------

    @Test
    fun `the sheet draws the five reasons and the one-line correction box`() {
        assertTrue(sheet.contains("WrongFeedback.TITLE"))
        assertTrue(sheet.contains("WrongFeedback.SUBTITLE"))
        assertTrue(sheet.contains("WrongFeedback.WHY"))
        // Every chip comes from the ONE list, with the PC's own wire words -
        // no second copy of the five labels in the screen.
        assertTrue(
            "the chips are not the one FeedbackReason list",
            sheet.contains("for (option in FeedbackReason.values())"),
        )
        assertTrue(sheet.contains("option.label"))
        assertTrue(sheet.contains("WrongFeedback.toggle(reason, option)"))
        // The correction: one line, capped as it is typed, with the counter.
        assertTrue(sheet.contains("WrongFeedback.CORRECTION_LABEL"))
        assertTrue(sheet.contains("WrongFeedback.CORRECTION_HINT"))
        assertTrue(
            "the correction box does not cap what is typed",
            sheet.contains("correction = WrongFeedback.cap(it)"),
        )
        assertTrue(sheet.contains("WrongFeedback.remainingLabel(correction)"))
        assertTrue(sheet.contains("singleLine = true"))
    }

    @Test
    fun `both submit paths exist, in the owner's words`() {
        assertTrue(sheet.contains("WrongFeedback.JUST_WRONG"))
        assertTrue(sheet.contains("WrongFeedback.SUBMIT"))
        assertTrue(sheet.contains("WrongFeedback.CANCEL"))
        assertTrue(sheet.contains("WrongFeedback.CLOSE"))
        assertTrue(
            "the plain path does not send through the same tap dispatcher",
            sheet.contains("act(WrongFeedback.Tap.JUST_WRONG)"),
        )
        assertTrue(sheet.contains("act(WrongFeedback.Tap.SUBMIT)"))
        assertTrue(sheet.contains("act(WrongFeedback.Tap.CANCEL)"))
    }

    // ---- 3. Nothing is sent until Submit -----------------------------------

    @Test
    fun `the only send is the one in the Send branch`() {
        // ONE call to the v2 runtime call in the whole sheet.
        assertEquals(
            "the sheet has more than one network send path",
            1,
            Regex("""JarvisRuntime\.markWrong\(""").findAll(sheet).count(),
        )
        val sendAt = sheet.indexOf("JarvisRuntime.markWrong(")
        val branchAt = sheet.indexOf("is WrongFeedback.Request.Send ->")
        assertTrue("the send is not inside the request branch", sendAt > branchAt)
        // The dismiss branch is the one that closes, and it never sends.
        val nothingBranch = sheet.substringAfter("WrongFeedback.Request.Nothing ->")
            .substringBefore("is WrongFeedback.Request.Send ->")
        assertTrue("a dismiss does not close the sheet", nothingBranch.contains("onClose()"))
        assertFalse("a dismiss sends", nothingBranch.contains("markWrong"))
        // The dispatcher is the ONE request function: the screen keeps no
        // second copy of "what may be sent".
        assertEquals(
            "the sheet decides what to send somewhere else too",
            1,
            Regex("""WrongFeedback\.request\(""").findAll(sheet).count(),
        )
        assertFalse(
            "the sheet builds a body of its own",
            sheet.contains("Feedback.markBody("),
        )
    }

    @Test
    fun `the receipt is the PC's own sentence, and a dismiss can always close`() {
        assertTrue(
            "the PC's said is never shown",
            sheet.contains("WrongFeedback.receiptWords(receipt)"),
        )
        assertTrue("the receipt is not drawn", sheet.contains("val said"))
        assertTrue("the receipt is not read out as it lands", sheet.contains("liveStatus()"))
        assertTrue("the sheet cannot be dismissed when it shows a receipt", sheet.contains("WrongFeedback.CLOSE"))
        // A dead link says the same sentence the answer menu already says.
        assertTrue(sheet.contains("WrongFeedback.OFFLINE"))
        // The failure is the PC's plain words, never a raw error.
        assertTrue(sheet.contains("JarvisRuntime.noticeFor(result.error)"))
    }

    // ---- 4. A mark is not an approval --------------------------------------

    @Test
    fun `nothing in the sheet approves, answers or clears anything`() {
        for (forbidden in listOf(
            "onApprove", "approve(", "ApprovalCard", "/api/approve", "/api/pending",
            "postCard", "postJson(", "token", "Log.",
        )) {
            assertFalse("the sheet reaches $forbidden", sheet.contains(forbidden))
        }
        // The one call it makes is the mark runtime call; that method sends the
        // mark route only (checked below) and answers no card.
        assertTrue(sheet.contains("JarvisRuntime.markWrong("))
    }

    // ---- 5. The network and runtime halves --------------------------------

    @Test
    fun `the v2 send is the mark route, through the one body builder`() {
        assertTrue(
            "the v2 route is not the feedback mark route",
            api.contains("postObject(Feedback.MARK_PATH, body).map { Feedback.receipt(it) }"),
        )
        // The old route is untouched: the same path, the same old body. It is
        // still used by the plain Right mark (and every older caller).
        val old = fnOf("suspend fun markAnswer(", api)
        assertTrue("the old mark body builder is gone", old.contains("Feedback.markBody(turnId, mark)"))
        assertTrue("the old mark no longer posts the mark route", old.contains("postJson(Feedback.MARK_PATH, body)"))
        // The new body's shape lives in ONE place (Learning.kt/Feedback.kt),
        // never typed in the screen.
        assertTrue(
            "the wire words are not in the one net file",
            feedback.contains("wrong_fact") && feedback.contains("too_sensitive"),
        )
    }

    @Test
    fun `the runtime sends the sheet's body and records a WRONG mark`() {
        val fn = fnOf("suspend fun markWrong(", runtime)
        assertTrue("the runtime does not send the v2 body", fn.contains("api.markAnswerWithFeedback(body)"))
        assertTrue(
            "a successful v2 mark is not recorded as wrong",
            fn.contains("s.copy(mark = AnswerMark.WRONG, busy = false)"),
        )
        // It hands the PC's receipt back for the sheet to show.
        assertTrue(fn.contains("return result"))
        assertTrue("the runtime refuses on a dead/stale link, as every write does", fn.contains("actionBlocker()"))
        // A mark is one answer at a time: the same claim as the old mark.
        assertTrue("a second send while one is in flight is not refused", fn.contains("if (!claimed)"))
        for (forbidden in listOf("onApprove", "Approval", "postCard", "gate")) {
            assertFalse("the v2 mark reaches $forbidden", fn.contains(forbidden))
        }
    }

    @Test
    fun `the old immediate Right mark is unchanged`() {
        // The old route still sends the old body for the old taps: this suite
        // must not have turned every mark into a card path.
        val old = fnOf("suspend fun markAnswer(turnId", runtime)
        assertTrue(old.contains("val next = Feedback.nextMark(current, tapped)"))
        assertTrue(old.contains("api.markAnswer(turnId, next)"))
    }

    // ---- 6. Wave 10 Q2.1: the PC's saved why comes back ------------------

    @Test
    fun `the menu asks the PC for the saved why and re-shows it, not an empty sheet`() {
        assertTrue(
            "the menu never asks the PC for this answer's saved mark",
            menu.contains("syncAnswerMarkDetached"),
        )
        assertTrue(
            "the saved why is never drawn in the reopened menu",
            menu.contains("WrongFeedback.savedWords(savedFor)"),
        )
        assertTrue(
            "there is no door to change the saved why",
            menu.contains("WrongFeedback.EDIT_WHY"),
        )
        assertTrue(
            "the edit door does not open a PREFILLED sheet",
            menu.contains("WrongFeedback.prefill(savedFor)"),
        )
        assertTrue(
            "the sheet is never opened with the saved draft",
            menu.contains("initial = wrongDraft"),
        )
        val sheetFn = sheet
        assertTrue(
            "the sheet cannot accept a saved draft",
            sheetFn.contains("initial: WrongFeedback.Draft? = null"),
        )
        assertTrue(
            "the sheet does not read the saved why itself (a reopened sheet would stay empty)",
            sheetFn.contains("syncAnswerMarkDetached"),
        )
        assertTrue(
            "the sheet never prefills from the saved why",
            sheetFn.contains("WrongFeedback.prefill(savedFor)"),
        )
        assertTrue(
            "the sheet would overwrite words the owner has already touched",
            sheetFn.contains("if (!edited"),
        )
    }

    @Test
    fun `the saved why is a read-only GET on the existing route`() {
        val read = fnOf("suspend fun markState(turnId", api)
        assertTrue("the saved-why read does not build the GET path", read.contains("Feedback.markStatePath(turnId)"))
        assertTrue("the saved-why read is not a GET", read.contains("probe(path)"))
        assertFalse("the saved-why read posts", read.contains("postJson(") || read.contains("postObject("))
        assertFalse("the saved-why read can answer a card", read.contains("Approval") || read.contains("approve"))

        val runtimeRead = fnOf("suspend fun syncAnswerMark(", runtime)
        assertTrue("the runtime does not call the read", runtimeRead.contains("api.markState(turnId)"))
        assertTrue("the runtime does not keep the saved why", runtimeRead.contains("answerMarkDetails"))
        assertTrue(
            "the runtime does not show the PC's mark on the buttons again",
            runtimeRead.contains("details.mark"),
        )
        assertFalse("a quiet read arms a notice", runtimeRead.contains("_notice.value"))

        // The path itself is the EXISTING route with the answer id - never a
        // new route, and never a guessed one.
        assertTrue(learning.contains("fun markStatePath(turnId: String): String?"))
        assertTrue(
            "the GET path is not built from the one mark route",
            learning.contains("?turn_id=") && learning.contains("MARK_PATH"),
        )
    }
}
