package com.jarvis.client

import com.jarvis.client.ui.screens.FaceBarPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The full-screen face bar's typing box, and Quick note's sheet - the phone UI
 * changes of 2026-11-01/02, plus the box's own words of 2026-11-04.
 *
 * SOURCE PINS, the same shape as [AuditPlumbingTest] and [ChatMenuTest]: a
 * Compose screen cannot be driven from a JVM unit test in this project, so
 * what is pinned here is the arrangement, the guards and the words - plus the
 * two things in [FaceBarPlan] that are plain values a test can hold exactly:
 * the width the bar's weights give the box, and when the words are shown.
 *
 * What these cannot prove is said in the PR: that the box types, that the
 * keyboard's Send key answers, that a tap really moves focus and takes the
 * words away on a real phone, and that nothing overlaps at 360dp - this lane
 * has no device.
 *
 * The rules behind them are proved elsewhere: the photo routing by
 * [AttachFileTest], the note route by [NoteCaptureTest], and the send decision
 * itself by [AnswerMenuAskTest].
 */
class PhoneFaceBarTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }
    private val plan by lazy { SourceFile.read(screens + "FaceBarPlan.kt") }

    /** One top-level function's text, cut where the next one starts. */
    private fun fn(marker: String): String =
        home.substringAfter(marker).substringBefore("\nprivate fun ")

    private val voiceBar by lazy { fn("private fun VoiceBar(") }
    private val typeBox by lazy { fn("private fun FaceTypeBox(") }
    private val composer by lazy { fn("private fun Composer(") }
    private val quickNote by lazy { fn("private fun QuickNoteSheet(") }

    // A) The typing box on the face bar ---------------------------------------

    @Test
    fun `the face bar has one typing box to the right of the microphone`() {
        // ONE box, drawn once, in the bar itself.
        assertEquals(1, Regex("FaceTypeBox\\(").findAll(voiceBar).count())
        // To the RIGHT of the microphone: the mic is drawn first in the row,
        // then the box.
        val mic = voiceBar.indexOf("VoiceButton(")
        val box = voiceBar.indexOf("FaceTypeBox(")
        assertTrue("the box is not drawn after the microphone: $box <= $mic", box > mic)
        // The owner's words of 2026-11-04 - "with the wording \"Ask Jarvis\"
        // present" - while the box is empty. The 2026-11-01 decision was a box
        // with no placeholder words at all; the owner replaced it, and the
        // words are the owner's own rather than something invented here.
        assertEquals("the words in the box are not the owner's", "Ask Jarvis", FaceBarPlan.ASK_WORDS)
        assertTrue("the box never draws the words", typeBox.contains("FaceBarPlan.ASK_WORDS"))
        // ...drawn INSIDE the decoration box, never fed in as the field's
        // value: a placeholder must not be text that can be sent to the PC.
        val decorated = typeBox.indexOf("decorationBox =")
        val words = typeBox.indexOf("FaceBarPlan.ASK_WORDS")
        assertTrue("the words are drawn outside the decoration box: $words <= $decorated", words > decorated)
        assertTrue("the field is no longer fed the owner's draft", typeBox.contains("value = text"))
        // What the phone SAYS about the box is a separate thing, unchanged: a
        // screen reader's name for a control is not its placeholder.
        assertTrue("the box has no TalkBack name", typeBox.contains("contentDescription = FACE_TYPE_HINT"))
        assertTrue(
            "the TalkBack name changed",
            home.contains("private const val FACE_TYPE_HINT = \"Type a message to Jarvis\""),
        )
        assertTrue(
            "the visible words and the spoken name became the same string",
            FaceBarPlan.ASK_WORDS != "Type a message to Jarvis",
        )
        // The chat's own empty box shows these same words - which is where they
        // come from: two boxes, one sentence, so the phone does not say two
        // different things about the same empty field.
        assertTrue("the chat box says different words", composer.contains("\"Ask Jarvis\""))
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
    fun `the words show only while the box is empty and the owner is not in it`() {
        // The owner's rule of 2026-11-04, in their own words: the box shows
        // "Ask Jarvis" while it is empty, and "it disseapars affer i tap the box
        // and the keyboard pops up, reappears if its empty". A tap puts focus in
        // the box, so focus is the signal the words go on.
        assertTrue("an empty box nobody is in shows no words", FaceBarPlan.placeholderVisible("", false))
        // The half that matters most: the moment the box takes focus, the words
        // go - even though the box is still empty. A tap that leaves an empty
        // box focused must NOT show them.
        assertFalse(
            "the words stay while the owner is in the box with nothing typed",
            FaceBarPlan.placeholderVisible("", true),
        )
        assertFalse("the words are drawn under a typed line", FaceBarPlan.placeholderVisible("hello", false))
        assertFalse("the words are drawn under a typed line", FaceBarPlan.placeholderVisible("hello", true))
        // A box of spaces cannot send anything either - the bar's own send path
        // asks `text.isNotBlank()` - so it is empty and says so, rather than
        // sitting blank with an invisible keystroke in it.
        assertTrue("a box of spaces is not treated as empty", FaceBarPlan.placeholderVisible("   ", false))
        assertTrue("a newline-only box is not treated as empty", FaceBarPlan.placeholderVisible("\n", false))

        // The box asks that one function instead of keeping its own copy of the
        // condition: one place to change, one place this test can hold.
        assertEquals(
            "the box keeps its own copy of the show/hide rule",
            1,
            Regex("FaceBarPlan\\.placeholderVisible\\(").findAll(typeBox).count(),
        )
        // Focus is read off the field's own interaction source, so the tap that
        // opens the keyboard is the same event the words disappear on - not a
        // second gesture that could arrive late.
        assertTrue(
            "the field has no interaction source of its own",
            typeBox.contains("val interactionSource = remember { MutableInteractionSource() }"),
        )
        assertTrue("the field is not wired to that source", typeBox.contains("interactionSource = interactionSource"))
        assertTrue("focus is not read from the field", typeBox.contains("collectIsFocusedAsState()"))
        // The chat box above the composer keeps its own rule: its words stay
        // until something is typed, focus or no focus. The difference is
        // deliberate - the face bar is one line with no Send button beside it,
        // and the owner asked for the words to go there - so nobody may
        // "unify" the two by copying either rule into the other.
        assertTrue("the chat box stopped showing its own words", composer.contains("if (text.isEmpty())"))
        assertFalse("the chat box took the face bar's focus rule", composer.contains("placeholderVisible"))
    }

    @Test
    fun `the face bar's typing box cannot grow to the bar's whole height`() {
        // The owner's screenshot of 2026-11-03, after choosing Full screen: the
        // face was gone and the bar's small typing box was a tall column down
        // the right of an otherwise blank screen, with "Show chat", "More" and
        // the microphone halfway down it. A `BasicTextField`'s decoration box is
        // measured with the max height of whatever contains the field - here
        // the bar's Row, whose max height is the whole rest of the screen - so
        // `fillMaxSize` filled it. Measured on the phone on 2026-11-03: the
        // field's own node was [666,620]-[870,2382], 1762px tall, where 48dp
        // is 144px. Filling the WIDTH is wanted; the height must stay the
        // field's own.
        assertFalse(
            "the decoration box fills the height it is measured with again",
            typeBox.contains("fillMaxSize()"),
        )
        assertTrue(
            "the decoration box stopped filling the plate's width",
            typeBox.contains("Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterStart)"),
        )
        // The two halves that keep the height the field's own: the plate and
        // the field each still carry their 48dp minimum.
        assertEquals(
            "the plate or the field lost its 48dp height",
            2,
            Regex("""heightIn\(min = 48\.dp\)""").findAll(typeBox).count(),
        )
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
    fun `the box takes the whole right cell, and the microphone stays in the middle`() {
        // 2026-11-04: the box is no longer a measured 48-96dp stamp with empty
        // space after it (the owner: "take up rhe remaining exmptyspace around
        // it"). Both side cells take `weight(1f)`, and so does the box inside
        // the right one, so the box gets every dp that cell has left after Stop
        // while the two EQUAL weights keep the 48dp microphone exactly in the
        // middle of the bar.
        assertTrue(
            "the left cell stopped taking half of what is beside the microphone",
            Regex("""FlowRow\(\s*Modifier\.weight\(1f\),""").containsMatchIn(voiceBar),
        )
        assertTrue(
            "the right cell stopped taking half of what is beside the microphone",
            Regex("""Row\(\s*Modifier\.weight\(1f\)\.padding\(start = 8\.dp\),""").containsMatchIn(voiceBar),
        )
        assertTrue(
            "the box is not given the rest of its cell",
            voiceBar.contains("modifier = Modifier.weight(1f)"),
        )
        // The microphone's own cell stays a bare Box - no weight, no width - so
        // the two halves really are measured equally on either side of it.
        assertTrue(
            "the microphone gained a weight or a width of its own",
            Regex("""Box \{\s*\n\s*// A PC that has not offered""").containsMatchIn(voiceBar),
        )
        // Nothing sets a width on the box any more, and the old fixed-width
        // arithmetic is gone rather than left behind as dead code that could
        // drift away from the layout in silence.
        assertFalse("the box still sets its own width", typeBox.contains(".width("))
        assertFalse("the old fixed-width call site is back", voiceBar.contains("width = typeWidth"))
        assertFalse("the removed arithmetic is still in the screen", home.contains("typeWidthDp"))

        // What that weight comes to, and the floor it has to clear. At 360dp
        // the bar's content is 336dp, the microphone 48dp, so each cell is
        // 144dp; the cell keeps 8dp before the box. That is 136dp for the box
        // alone, and 88dp while Stop is showing - the 88dp the old fixed width
        // used to be all the time.
        val available = 360f - 24f
        assertEquals(144f, FaceBarPlan.sideDp(available), 0.001f)
        assertEquals(136f, FaceBarPlan.boxWidthDp(available, streaming = false), 0.001f)
        assertEquals(88f, FaceBarPlan.boxWidthDp(available, streaming = true), 0.001f)
        // ...and the sum still closes: the box, the gap before it and Stop's
        // room are exactly one side, so the box cannot reach the microphone.
        assertEquals(
            "the box, its gap and Stop do not add up to one side",
            FaceBarPlan.sideDp(available),
            FaceBarPlan.boxWidthDp(available, streaming = true) + FaceBarPlan.GAP_DP + FaceBarPlan.STOP_DP,
            0.001f,
        )
        // The narrowest phone this app supports is 320dp: the box still clears
        // its own 48dp touch target there by 20dp, even with Stop showing, so
        // the box that took the empty space did not become unusable on a small
        // screen.
        val narrow = 320f - 24f
        assertEquals(116f, FaceBarPlan.boxWidthDp(narrow, streaming = false), 0.001f)
        assertEquals(68f, FaceBarPlan.boxWidthDp(narrow, streaming = true), 0.001f)
        assertTrue(
            "the box can no longer be typed in on a 320dp phone while an answer streams",
            FaceBarPlan.boxWidthDp(narrow, streaming = true) >= FaceBarPlan.TYPE_MIN_DP,
        )
    }

    @Test
    fun `the 96dp cap that left the empty space is gone, and the words live in the plan`() {
        // The 2026-11-01/02 design capped the box at 96dp so it could never
        // become a second composer - and that is exactly the empty space the
        // owner pointed at on 2026-11-04. A cap that came back would leave the
        // space there again, so its absence is pinned here, beside the two
        // things that replaced the arithmetic: the width the layout gives the
        // box and the rule for its words.
        assertFalse("the 96dp cap is back, so the box can stop short again", plan.contains("TYPE_MAX_DP"))
        assertFalse("the old fixed-width arithmetic is back", plan.contains("typeWidthDp"))
        assertTrue("the width the layout gives the box is not written down", plan.contains("fun boxWidthDp("))
        assertTrue("the show/hide rule is not written down", plan.contains("fun placeholderVisible("))
        assertTrue(
            "the owner's words are not in the plan",
            plan.contains("const val ASK_WORDS = \"Ask Jarvis\""),
        )
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
