package com.jarvis.client

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
 * what is pinned here is the arrangement, the guards and the words. What these
 * cannot prove is said in the PR: that the box types, that the keyboard's Send
 * key answers, that the sheet is reachable from the face layout on a real
 * screen, and that nothing overlaps at 360dp - this lane has no device.
 *
 * The rules behind them are proved elsewhere: the photo routing by
 * [AttachFileTest], the note route by [NoteCaptureTest].
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
    fun `a typed send uses the composer's guard and then opens the chat`() {
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
        // ONE send path: the guard first, then the one send action. Nothing is
        // cleared here on purpose - onSend reads the words and empties the box
        // exactly as it does for the composer's Send, and a note the PC refused
        // has to stay in it.
        val sendFn = voiceBar.substringAfter("fun sendTyped()").substringBefore("\n    Column(")
        assertTrue(sendFn.contains("if (!canSend) return"))
        assertTrue(sendFn.contains("actions.onSend()"))
        assertFalse("the bar clears the draft under onSend", sendFn.contains("onDraftChange"))
        // The chat opens AFTER the send, so the answer can be read - the bar
        // above shows only its first three lines.
        val sent = sendFn.indexOf("actions.onSend()")
        val opened = sendFn.indexOf("onTypedSend()")
        assertTrue("the chat opens before the question is sent: $opened <= $sent", opened > sent)
        assertTrue(
            "the call site does not open the chat",
            home.contains("onTypedSend = { peekChat = true }"),
        )
        // An empty box sends nothing: the keyboard key and the box's own
        // action both end at sendTyped, and sendTyped's first line is the guard.
        assertEquals(
            "the keyboard's Send key bypasses the guard",
            1,
            Regex("KeyboardActions\\(onSend = \\{").findAll(typeBox).count(),
        )
    }

    // C) Quick note opens where it is pressed ---------------------------------

    @Test
    fun `Quick note opens as a sheet above both layouts, not only inside the chat`() {
        // It is a Dialog now, as the More menu is, and it can be dismissed.
        assertTrue("the note sheet is not a dialog", quickNote.contains("Dialog(onDismissRequest ="))
        assertTrue(
            "the note sheet cannot be closed",
            quickNote.contains("actions.onQuickNoteOpenChange(false)"),
        )
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
}
