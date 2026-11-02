package com.jarvis.client

import com.jarvis.client.ui.screens.FaceBarPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The full-screen face bar's small typing box, and Quick note's sheet - the
 * two phone UI changes of 2026-11-01/02 that a JVM test can hold down.
 *
 * SOURCE PINS, the same shape as [AuditPlumbingTest] and [ChatMenuTest]: a
 * Compose screen cannot be driven from a JVM unit test in this project, so
 * what is pinned here is the arrangement, the guards and the words - plus
 * [FaceBarPlan]'s arithmetic, which is plain numbers and can be held exactly.
 * What these cannot prove is said in the PR: that the box types, that the
 * keyboard's Send key answers, that the sheet is reachable from the face
 * layout on a real screen, and that nothing overlaps at 360dp - this lane has
 * no device.
 *
 * The rules behind them are proved elsewhere: the photo routing by
 * [AttachFileTest], the note route by [NoteCaptureTest], and the send decision
 * itself by [AnswerMenuAskTest].
 */
class PhoneFaceBarTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }

    /** One top-level function's text, cut where the next one starts. */
    private fun fn(marker: String): String =
        home.substringAfter(marker).substringBefore("\nprivate fun ")

    private val voiceBar by lazy { fn("private fun VoiceBar(") }
    private val typeBox by lazy { fn("private fun FaceTypeBox(") }
    private val composer by lazy { fn("private fun Composer(") }
    private val quickNote by lazy { fn("private fun QuickNoteSheet(") }

    // A) The small blank typing box on the face bar ---------------------------

    @Test
    fun `the face bar has one small blank typing box to the right of the microphone`() {
        // ONE box, drawn once, in the bar itself.
        assertEquals(1, Regex("FaceTypeBox\\(").findAll(voiceBar).count())
        // To the RIGHT of the microphone: the mic is drawn first in the row,
        // then the box.
        val mic = voiceBar.indexOf("VoiceButton(")
        val box = voiceBar.indexOf("FaceTypeBox(")
        assertTrue("the box is not drawn after the microphone: $box <= $mic", box > mic)
        // No placeholder words inside it - the owner asked for a blank box.
        assertFalse("a placeholder was put in the blank box", typeBox.contains("placeholder"))
        assertFalse("words were put in the blank box", typeBox.contains("Ask Jarvis"))
        // ...but TalkBack still has a name for it.
        assertTrue("the box has no TalkBack name", typeBox.contains("contentDescription = FACE_TYPE_HINT"))
        assertTrue(
            "the TalkBack name changed",
            home.contains("private const val FACE_TYPE_HINT = \"Type a message to Jarvis\""),
        )
        // At least 48dp of touch height, on the FIELD itself - padding around
        // a short field would look the same and be untappable.
        assertTrue("the box has no 48dp height", typeBox.contains("heightIn(min = 48.dp)"))
        assertTrue(
            "the field does not fill its own 48dp box",
            Regex("""fillMaxWidth\(\)\s*\.heightIn\(min = 48\.dp\)""").containsMatchIn(typeBox),
        )
        // The keyboard's Send key must send, not be swallowed.
        assertTrue(typeBox.contains("imeAction = ImeAction.Send"))
        assertTrue(
            "the keyboard's Send key is not wired",
            typeBox.contains("keyboardActions = KeyboardActions(onSend = { onSend() })"),
        )
        // The composer's look, made small: a flat plate and a BasicTextField,
        // not the Material text field the composer's own comment rejects.
        assertTrue(typeBox.contains("BasicTextField("))
        assertTrue(typeBox.contains("background(chrome.surface2)"))
        assertFalse(typeBox.contains("OutlinedTextField"))
    }

    @Test
    fun `both typing boxes make the same send decision, and only a real send opens the chat`() {
        // (a) of the 2026-11-02 review: the face box used to send "was this
        // answer right?" to the PC as a question. It must call the SAME one
        // decision function the chat box does - not a second copy of the
        // sentence list and not a second copy of the conditions.
        assertTrue("the face bar does not use the shared decision", voiceBar.contains("AnswerMenuAsk.decide("))
        assertTrue("the chat box does not use the shared decision", composer.contains("AnswerMenuAsk.decide("))
        // ...and that function, not a duplicated condition, is the only place
        // the sentence list is consulted.
        assertEquals(0, Regex("AnswerMenuAsk\\.matches\\(").findAll(voiceBar).count())
        assertEquals(0, Regex("AnswerMenuAsk\\.matches\\(").findAll(composer).count())
        // The same rule as the composer's canSend, plus "nothing while
        // streaming": full screen's Stop is its own control, not this button.
        for (pin in listOf(
            "text.isNotBlank() || state.sharedLine != null",
            "state.link == LinkState.CONNECTED",
            "!state.pictureBusy",
            "!state.attachBusy",
            "!state.streaming",
        )) {
            assertTrue("the face bar's send is missing: $pin", voiceBar.contains(pin))
        }
        // ...and the composer still carries the same atoms, so the two cannot
        // drift apart without this test noticing the half that changed.
        for (pin in listOf(
            "text.isNotBlank() || state.sharedLine != null",
            "state.link == LinkState.CONNECTED",
            "!state.pictureBusy",
            "!state.attachBusy",
        )) {
            assertTrue("the composer lost: $pin", composer.contains(pin))
        }
        val sendFn = voiceBar.substringAfter("fun sendTyped()").substringBefore("\n    Column(")
        // The four outcomes, each handled: nothing is sent on HELD; the menu
        // request is used up and opens the menu; no finished answer is said in
        // words; an ordinary send sends.
        assertTrue(sendFn.contains("Decision.HELD -> Unit"))
        assertTrue(sendFn.contains("Decision.OPEN_MENU"))
        assertTrue(sendFn.contains("Decision.NEEDS_ANSWER"))
        assertTrue(sendFn.contains("Decision.SEND"))
        assertTrue(sendFn.contains("actions.onDraftChange(\"\")"))
        assertTrue(sendFn.contains("onOpenAnswerMenu()"))
        assertTrue(sendFn.contains("AnswerMenuAsk.NO_ANSWER"))
        assertTrue(sendFn.contains("actions.onSend()"))
        // Nothing is sent by a held press: onSend and onTypedSend sit after the
        // decision, and the draft is only emptied in the OPEN_MENU branch (a
        // note the PC refused must stay in the box).
        val sent = sendFn.indexOf("actions.onSend()")
        val opened = sendFn.indexOf("onTypedSend()")
        assertTrue("the chat opens before the question is sent: $opened <= $sent", opened > sent)
        assertTrue("the box is cleared before the send", sendFn.indexOf("onDraftChange") < sent)
        // The call site gives the bar the menu and the finished-answer test:
        // the chat is opened for the menu (it is drawn in the conversation,
        // which full screen does not compose) and the answer's own menu is
        // asked for by number.
        assertTrue(home.contains("onOpenAnswerMenu = {"))
        assertTrue(home.contains("answerMenuTick += 1"))
        assertTrue(home.contains("hasFinishedAnswer = hasFinishedAnswer"))
        // ONE definition of "a finished answer", shared by both boxes.
        assertEquals(
            "the finished-answer test is defined more than once",
            1,
            Regex("val hasFinishedAnswer").findAll(home).count(),
        )
        // An empty box sends nothing: the keyboard key and the box's own
        // action both end at sendTyped, and sendTyped's first act is the
        // decision, whose HELD case sends nothing.
        assertEquals(
            "the keyboard's Send key bypasses the decision",
            1,
            Regex("KeyboardActions\\(onSend = \\{").findAll(typeBox).count(),
        )
    }

    // B) The bar at 360dp and at a large text size ---------------------------

    @Test
    fun `the typing box's width is computed so it cannot reach the microphone`() {
        // A 360dp phone, the composer's 12dp side padding taken off: the
        // columns are 336dp, the microphone 48dp, so each side has 144dp. The
        // box keeps room for Stop beside it, which is why it is 88dp and not
        // the whole side.
        val available = 360f - 24f
        assertEquals(336f, available, 0.001f)
        assertEquals(144f, FaceBarPlan.sideDp(available), 0.001f)
        assertEquals(88f, FaceBarPlan.typeWidthDp(available), 0.001f)
        assertEquals(
            "the box, its gap and Stop do not add up to one side",
            FaceBarPlan.sideDp(available),
            FaceBarPlan.typeWidthDp(available) + FaceBarPlan.GAP_DP + FaceBarPlan.STOP_DP,
            0.001f,
        )
        // The narrowest phone this app supports is 320dp: still exact there,
        // so the box never overlaps the microphone on a real device size.
        val narrow = 320f - 24f
        assertEquals(68f, FaceBarPlan.typeWidthDp(narrow), 0.001f)
        assertEquals(
            FaceBarPlan.sideDp(narrow),
            FaceBarPlan.typeWidthDp(narrow) + FaceBarPlan.GAP_DP + FaceBarPlan.STOP_DP,
            0.001f,
        )
        // The code uses the plan for the real width, not a second copy of the
        // arithmetic.
        assertTrue(voiceBar.contains("FaceBarPlan.typeWidthDp(maxWidth.value).dp"))
    }

    @Test
    fun `at 1_3x the left labels wrap instead of being clipped`() {
        // Computed, at 1.3x: "Show chat" is about 76dp of 12sp text and "More"
        // about 35dp; each Quiet adds 10dp of padding a side, and the gap is
        // 8dp. That is about 159dp - more than the 144dp the left cell has at
        // 360dp, so on ONE line the two labels cannot fit at the owner's
        // larger text size.
        val textShowChat = 76f // 9 characters of 12sp Roboto, at 1.3x
        val textMore = 35f // 4 characters, at 1.3x
        val leftNeeds = textShowChat + 20f + FaceBarPlan.GAP_DP + maxOf(FaceBarPlan.TYPE_MIN_DP, textMore + 20f)
        assertEquals(159f, leftNeeds, 0.5f)
        assertTrue(
            "the labels actually fit the left cell, so this test is reasoning about nothing",
            leftNeeds > FaceBarPlan.sideDp(360f - 24f),
        )
        // So the cell is a FlowRow: when they do not fit side by side, "More"
        // moves onto a second line and the bar grows. Each label is still one
        // line with an ellipsis as its own last resort, so no word is cut with
        // no sign and nothing is drawn over the microphone.
        assertTrue("the left cell is not a wrapping row", voiceBar.contains("FlowRow("))
        assertTrue(voiceBar.contains("horizontalArrangement = Arrangement.spacedBy(8.dp)"))
        assertEquals(
            "a Label in the left cell can wrap without an ellipsis",
            2,
            Regex("maxLines = 1,\\s*\\n\\s*overflow = TextOverflow\\.Ellipsis").findAll(voiceBar).count(),
        )
    }

    // C) Quick note opens where it is pressed ---------------------------------

    @Test
    fun `Quick note opens as a sheet above both layouts, not only inside the chat`() {
        // It is a Dialog now, and it can be dismissed.
        assertTrue("the note sheet is not a dialog", quickNote.contains("Dialog("))
        // Drawn ABOVE the layout switch: after the whole `if (voiceMode) ...
        // else ...` block and beside the More menu, so full screen gets it too.
        val call = home.indexOf("QuickNoteSheet(actions)")
        val voice = home.indexOf("if (voiceMode) {")
        val composerCall = home.indexOf("Composer(", voice)
        val moreMenu = home.indexOf("if (moreOpen) {")
        assertTrue("the quick-note sheet is never drawn", call > 0)
        assertTrue("the layout switch is gone", voice > 0 && composerCall > voice)
        assertTrue("the drive to the sheet is before the chat: $call vs $composerCall", call > composerCall)
        assertTrue("the sheet is not drawn beside the More menu: $call vs $moreMenu", call > moreMenu)
        // The conversation list no longer owns it. That is what made the More
        // row look dead in full screen (no list at all) and below the fold in
        // the chat (it was the last item).
        val list = fn("private fun ConversationList(")
        assertFalse("Quick note is a conversation-list row again", list.contains("QuickNoteSheet("))
        assertFalse("the old closed-state plate is in the list", list.contains("QuickNotePlate"))
        assertFalse("the quick-note list key is back", home.contains("key = \"quick-note\""))
        // The closed-state button had no caller left, so it is gone rather
        // than left as dead code.
        assertFalse("the dead closed-state button is back", home.contains("Quiet(\"Quick note…\""))
        // The More row still opens it, and its words are the same ones.
        assertTrue(home.contains("MoreRow(MoreMenuWords.QUICK_NOTE)"))
        assertTrue(quickNote.contains("\"Quick note\""))
        assertTrue(quickNote.contains("Filed on the desktop exactly as you type it."))
        assertTrue(quickNote.contains("Quiet(\"Close\""))
        // It files the note through the SAME one action, and never chats.
        assertTrue(quickNote.contains("actions.onFileNote(target, note)"))
        assertFalse(quickNote.contains("sendTypedChat"))
    }

    @Test
    fun `a typed note cannot be thrown away by an outside tap, Back or Close`() {
        // (b) of the 2026-11-02 review: the sheet used the Dialog's defaults,
        // so an outside tap or Back dismissed it and silently dropped the note.
        assertTrue(
            "an outside tap can still dismiss the sheet",
            quickNote.contains("dismissOnClickOutside = false"),
        )
        assertTrue("the dialog properties are not set at all", quickNote.contains("DialogProperties("))
        // Back is still the owner's Back - it just asks the same question
        // Close does, through the one close path.
        assertTrue(quickNote.contains("onDismissRequest = { requestClose() }"))
        assertTrue(quickNote.contains("fun requestClose()"))
        // ...and with a typed note that path asks instead of closing.
        assertTrue(quickNote.contains("if (noteText.isBlank())"))
        assertTrue(quickNote.contains("confirmClose = true"))
        assertTrue(quickNote.contains("Close without filing this note?"))
        assertTrue(quickNote.contains("\"Keep writing\""))
        assertTrue(quickNote.contains("\"Close without filing\""))
        // Close goes through the same path, not straight out.
        assertEquals(
            "Close does not use the one close path",
            1,
            Regex("Quiet\\(\"Close\"[\\s\\S]{0,120}?onClick = \\{ requestClose\\(\\) \\}").findAll(quickNote).count(),
        )
        // The keyboard cannot cover the note box.
        assertTrue("the sheet ignores the keyboard's inset", quickNote.contains(".imePadding()"))
        assertTrue(
            "the dialog still fits the system windows, so imePadding cannot see the keyboard",
            quickNote.contains("decorFitsSystemWindows = false"),
        )
    }

    @Test
    fun `a rotation does not close the sheet and lose the typed note`() {
        val activity = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt")
        // The typed note lives in the sheet's own rememberSaveable, so what has
        // to survive recreation is the sheet's open flag - otherwise the sheet
        // is not composed at all and the restored text has nowhere to go
        // (2026-11-02). Not driven on a device from this branch: this pins the
        // two halves that make it so.
        assertTrue(
            "the sheet's open flag is not saved",
            activity.contains("outState.putBoolean(STATE_QUICK_NOTE_OPEN, quickNoteOpen.value)"),
        )
        assertTrue(
            "the sheet's open flag is not restored before the first composition",
            activity.contains("savedInstanceState?.getBoolean(STATE_QUICK_NOTE_OPEN) == true"),
        )
        assertTrue(
            "the note's text stopped being remembered across recreation",
            quickNote.contains("var noteText by rememberSaveable"),
        )
        // It is the FLAG that is saved, never the note: the one key is written
        // with a Boolean, so nothing the owner typed rides in the Bundle.
        assertFalse(
            "the sheet's key carries a string",
            activity.contains("putString(STATE_QUICK_NOTE_OPEN"),
        )
    }
}
