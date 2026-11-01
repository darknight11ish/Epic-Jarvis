package com.jarvis.client

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The phone chat's own menu, pins and "new chat" (the owner's request of
 * 2026-10-27, in their words):
 *
 * > "also, i dont want a 'was this answer right' on every response from
 * > jarvis. put a carrot that opens a menu on each chat that has this, along
 * > with a pin message button that pins the message and remembers it and can
 * > be found easily in a new menu. also where can i find old jarvis chats? and
 * > how do i open new ones?"
 *
 * These are SOURCE PINS, the same shape as [ReadAloudWiringTest] and
 * [PresetsLandingTest]: they read the screen files and hold the arrangement
 * still, because a Compose screen cannot be driven from a JVM unit test in this
 * project (no Android build here at all - CI's `phone-unit-tests` job is the
 * first compiler). What the pins cannot prove is said in the PR: that the menu
 * opens, looks right and reads out on a real phone.
 *
 * The rules themselves - one pin per message, newest first, the cap, the ages,
 * the file - are proved for real in `data/ChatPinsTest.kt`.
 */
class ChatMenuTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }
    private val words by lazy { SourceFile.read(screens + "MoreMenuWords.kt") }
    private val pinnedScreen by lazy { SourceFile.read(screens + "PinnedScreen.kt") }
    private val history by lazy { SourceFile.read(screens + "HistoryScreen.kt") }
    private val main by lazy { SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt") }
    private val pinsModel by lazy { SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/data/ChatPins.kt") }
    private val pinsStore by lazy { SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/data/PinnedChatStore.kt") }

    private fun bodyOf(marker: String, text: String = home): String =
        text.substringAfter(marker).substringBefore("\n/**")

    // ---- 1. The always-visible block is gone, the menu has it ---------------

    @Test
    fun `the answer no longer carries a mark block of its own`() {
        val reply = bodyOf("private fun Reply(")
        // The pair moved into the menu: Reply draws no mark buttons at all now.
        assertFalse("Reply still draws the Right/Wrong pair", reply.contains("MarkToggle("))
        assertFalse("Reply still draws the old mark block", reply.contains("AnswerMarks("))
        assertFalse("Reply still says 'Was this right?' on every answer", reply.contains("Was this right"))
        assertFalse("Reply still wires the marks itself", reply.contains("onMark(feedback.turnId"))
        // ...but it still owns the chevron that opens them, and the menu.
        assertTrue("Reply has no chevron on the answer", reply.contains("MessageActionsButton("))
        assertTrue("Reply never draws the menu", reply.contains("MessageMenu("))
    }

    @Test
    fun `the menu is where the marks and the pin live`() {
        val menu = bodyOf("private fun MessageMenu(")
        assertTrue("the menu has no Right/Wrong pair", menu.contains("AnswerMarkRows("))
        assertTrue("the menu cannot pin", menu.contains("ChatPins.PIN)"))
        assertTrue("the menu cannot unpin", menu.contains("ChatPins.UNPIN)"))
        // Same one-mark semantics, said in the same words as before.
        val marks = bodyOf("private fun AnswerMarkRows(")
        assertTrue(marks.contains("onMark(feedback.turnId, AnswerMark.RIGHT)"))
        assertTrue(marks.contains("onMark(feedback.turnId, AnswerMark.WRONG)"))
        assertTrue(marks.contains("Tap Wrong again to take it back"))
        assertTrue(marks.contains("Tap Right again to take it back"))
        assertTrue(marks.contains("Not connected, so a mark cannot be sent right now."))
        assertTrue("the unavailable state was lost", marks.contains("feedback.unavailable"))
        assertTrue("a busy mark is not said", marks.contains("Saving…"))
    }

    @Test
    fun `an answer with no id still offers the pin`() {
        val menu = bodyOf("private fun MessageMenu(")
        // A folded answer (no turn id) gets the menu too - pin only.
        assertTrue(menu.contains("if (feedback != null)"))
        val fold = bodyOf("private fun ThreadFold(")
        assertTrue("folded answers have no chevron", fold.contains("MessageActionsButton("))
        assertTrue("folded answers open no menu", fold.contains("MessageMenu("))
        assertTrue("a folded answer is given marks it cannot have", fold.contains("feedback = null"))
    }

    // ---- 2. Pins: on the phone, capped, never dropped silently --------------

    @Test
    fun `a pin is a phone-local store with no route at all`() {
        assertTrue(
            "the store is not a private preference file",
            pinsStore.contains("getSharedPreferences(PREFS, Context.MODE_PRIVATE)"),
        )
        assertTrue(pinsStore.contains("\"jarvis_pinned_chats\""))
        // Nothing here sends anything anywhere: no route, no API call, no token.
        for (source in listOf(pinsModel, pinsStore)) {
            assertFalse("a pin store talks to the PC", source.contains("/api/"))
            assertFalse("a pin store calls the API", source.contains("JarvisApi"))
            assertFalse("a pin store logs", source.contains("Log."))
        }
        // ...and the words say so where the owner reads them.
        assertTrue(pinsModel.contains("Kept on this phone"))
    }

    @Test
    fun `the cap is said in words instead of dropping the oldest pin`() {
        val menu = bodyOf("private fun MessageMenu(")
        assertTrue("the menu never says the list is full", menu.contains("ChatPins.full()"))
        assertTrue(menu.contains("pinMenu.full ->"))
        // The model refuses rather than replacing an older pin (ChatPinsTest
        // proves the rule; this pins the sentence the menu draws).
        assertTrue(pinsModel.contains("fun full()"))
        assertTrue(pinsModel.contains("Unpin one to make room"))
    }

    @Test
    fun `a temporary chat may never be pinned`() {
        assertTrue(
            "HomeState does not default to refusing a pin",
            home.contains("val pinsAllowed: Boolean = false"),
        )
        assertTrue(
            "a temporary chat or a game can be pinned",
            main.contains("pinsAllowed = !temporaryChat && !gameChat"),
        )
        val menu = bodyOf("private fun MessageMenu(")
        assertTrue("the menu does not say why a temporary chat cannot be pinned", menu.contains("ChatPins.TEMPORARY"))
        assertTrue(menu.contains("!pinMenu.allowed ->"))
    }

    // ---- 3. The pinned list: reachable, guarded, newest first ---------------

    @Test
    fun `pinned messages is its own screen, opened from History's header`() {
        // MOVED 2026-10-30 (the owner's choice: tuck the rare ones away). The
        // pinned list is one compact "Pinned" action in History's header now -
        // the SAME PinnedScreen, not a copy, and no longer a More menu row.
        assertTrue("History cannot open the pinned list", history.contains("onOpenPins: () -> Unit"))
        assertTrue("History's header does not draw the Pinned action", history.contains("ChatPins.ACTION"))
        assertTrue(
            "History's Pinned action does not reach the route",
            history.contains("onClick = onOpenPins"),
        )
        assertTrue(
            "MainActivity does not hand History the pins action",
            main.contains("onOpenPins = { nav.go(Screen.PINS) }"),
        )
        assertFalse("the More menu still carries a pinned row", home.contains("ChatPins.TITLE"))
        assertFalse("Home still has a pins action of its own", home.contains("actions.onOpenPins"))
        assertTrue(main.contains("Screen.PINS ->"))
        assertTrue("the screen is not registered", SourceFile.read(
            "jarvis-client/app/src/main/java/com/jarvis/client/ui/Nav.kt",
        ).contains("PINS,"))
    }

    @Test
    fun `the pinned list hides with the memory lists, and says what a row is`() {
        assertTrue("the list ignores the hide switch", pinnedScreen.contains("privateHidden"))
        assertTrue(
            "the list has no Show gate of its own",
            pinnedScreen.contains("HiddenSection(ChatPins.TITLE"),
        )
        // Newest first, each row with its words, its chat, unpin and open.
        assertTrue(pinnedScreen.contains("items(pins, key = { it.key })"))
        assertTrue(pinnedScreen.contains("ChatPins.snippet(row.text)"))
        assertTrue(pinnedScreen.contains("ChatPins.whereLine(row, nowMs)"))
        assertTrue(pinnedScreen.contains("ChatPins.UNPIN"))
        assertTrue(pinnedScreen.contains("ChatPins.OPEN_CHAT"))
        // Only a pin whose chat is known offers to open it.
        assertTrue(pinnedScreen.contains("if (ChatPins.opens(row))"))
        // And the empty list says where the control is.
        assertTrue(pinnedScreen.contains("ChatPins.EMPTY"))
    }

    @Test
    fun `opening a pinned chat goes through History, not a second History`() {
        val historySource = history
        assertTrue("History cannot be opened at one chat", historySource.contains("openChatId: String? = null"))
        assertTrue("the request is never consumed", historySource.contains("LaunchedEffect(openChatId)"))
        assertTrue("the request does not open the chat", historySource.contains("openId = wanted"))
        assertTrue(main.contains("openChatId = historyOpenChat"))
        assertTrue(main.contains("onOpenChatDone = { historyOpenChat = null }"))
        assertTrue(main.contains("historyOpenChat = id"))
        // No second screen: the pinned list never draws a conversation itself.
        assertFalse("the pinned list draws chats of its own", pinnedScreen.contains("Conversation("))
    }

    // ---- 4. Old chats and new chats, where the owner now looks -------------

    @Test
    fun `the menu is five doors, and the modes live one tap deeper`() {
        // The owner's choice of 2026-10-30, after he photographed the old
        // sheet ("too many options"): the More menu is short now, and the
        // three chat modes are one tap deeper behind ONE "Modes" row.
        val shell = bodyOf("private fun HomeMoreMenu(")
        val menu = bodyOf("private fun HomeMoreMain(")
        val modes = bodyOf("private fun HomeMoreModes(")
        // The shell swaps the dialog's own content for the sub-sheet; there is
        // no second dialog and no second Back.
        assertTrue("the More shell does not open the short menu", shell.contains("HomeMoreMain("))
        assertTrue("the More shell does not open the modes sub-sheet", shell.contains("HomeMoreModes("))
        assertTrue("the modes page has no way back", shell.contains("modesOpen = false"))
        // The five doors, in the order the owner reads them.
        val order = listOf(
            "MoreMenuWords.NEW_CHAT", "MoreMenuWords.PHOTO", "MoreMenuWords.FILE",
            "MoreMenuWords.MODES", "MoreMenuWords.QUICK_NOTE",
        )
        val at = order.map { menu.indexOf(it) }
        assertTrue("the short menu lost a door: $at", at.all { it >= 0 })
        assertEquals("the short menu's doors are out of order: $at", at.sorted(), at)
        // The rows that left are GONE, not hidden behind a second copy.
        assertFalse("Earlier chats is still a More row", menu.contains("ChatHistory.EARLIER_CHATS"))
        assertFalse("Pinned messages is still a More row", menu.contains("ChatPins.TITLE"))
        assertFalse("Jarvis Presets is still a More row", menu.contains("MoreMenuWords.PRESETS"))
        // Earlier chats opened History; History IS the list, so the words come
        // back nowhere in Home and the status-line control is the one door.
        assertEquals(
            "Earlier chats is drawn in Home again",
            0,
            Regex("ChatHistory\\.EARLIER_CHATS").findAll(home).count(),
        )
        // The three modes behave exactly as they did as rows: same words, same
        // gates, same one-shot / coach / incognito actions.
        for (pin in listOf(
            "Thinking.ONE_SHOT_LABEL",
            "coach.button",
            "actions.onToggleTemporary()",
            "TemporaryChat.START",
        )) {
            assertTrue("the Modes sub-sheet lost $pin", modes.contains(pin))
        }
        assertTrue("the Modes sub-sheet lost the coach's gate", modes.contains("coach.routeKnown"))
        assertEquals(
            "the short menu draws a mode itself instead of the Modes row",
            0,
            Regex("Thinking\\.ONE_SHOT_LABEL").findAll(menu).count(),
        )
        // "New chat" is the same mechanism the idle timer uses, not a new one,
        // and the answer's own row and the menu still share the ONE action.
        assertTrue(menu.contains("actions.onNewConversation()"))
        assertTrue(
            "a new chat no longer goes through the chat's own reset",
            main.contains("onNewConversation = { chat.newConversationSaid() }"),
        )
        assertEquals(
            "the two New chat doors are not one action",
            2,
            home.split("actions.onNewConversation").size - 1,
        )
        assertEquals(
            "HomeScreen grew a New chat action of its own",
            1,
            home.split("val onNewConversation: () -> Unit").size - 1,
        )
        assertFalse(
            "HomeScreen mints a conversation id itself",
            home.contains("ChatHistory.newConversationId()"),
        )
        assertFalse("HomeScreen resets the chat session itself", home.contains("newConversationSaid"))
    }

    @Test
    fun `History has one filter row, and the Filters sheet holds the rest`() {
        // The owner's choice of 2026-10-30: the three chip rows became one row
        // (the tags, scrolling sideways) plus one Filters button, and the sheet
        // behind it holds every rare filter - unchanged and still combining.
        assertTrue("History has no single tag row", history.contains("TagFilterChipsRow("))
        assertTrue("History has no Filters door", history.contains("ChatLog.FILTERS_TITLE"))
        assertTrue("History has no Filters sheet", history.contains("private fun HistoryFiltersSheet("))
        assertTrue(
            "the Filters button never says it is on",
            history.contains("ChatLog.filtersActive(") && history.contains("ChatLog.filtersTitle("),
        )
        val sheet = history.substringAfter("private fun HistoryFiltersSheet(")
        for (pin in listOf(
            "ChatLog.FILTERS.forEach",       // the conversation kinds
            "ChatLog.ARCHIVED",              // the archived view
            "ChatLog.ARCHIVE_FILTER_TITLE",  // its own name for TalkBack
            "TagFilterChips(",               // the full tag list, wrapping
            "ChatTags.EDITOR_TITLE",         // the Tags editor link
            "ChatLog.FORGET_RANGE_LINK",     // Forget a time frame
        )) {
            assertTrue("the Filters sheet lost $pin", sheet.contains(pin))
        }
        // The list head draws the ONE row and the button, and no longer draws
        // the kind chips or the second, wrapping tag row.
        val head = history.substringAfter("item(key = \"list-head\")").substringBefore("// Delete from a row's menu")
        assertTrue("the Filters button is not in the list head", head.contains("ChatLog.FILTERS_TITLE"))
        assertTrue("the single tag row is not in the list head", head.contains("TagFilterChipsRow("))
        assertFalse("a kind chip row is still drawn in the list head", head.contains("ChatLog.FILTERS.forEach"))
        assertFalse("a second tag chip row is still drawn in the list head", head.contains("TagFilterChips(view.tags"))
        // The sheet follows the same private-lists guard the tag names do: a
        // hidden list must not leave the tag names up behind a dialog.
        assertTrue(
            "the Filters sheet ignores the hidden-lists guard",
            history.contains("if (filtersOpen && !privateHidden)"),
        )
    }

    @Test
    fun `new chat is the same word under the answer as in the menu`() {
        assertTrue(words.contains("const val NEW_CHAT = \"New chat\""))
        assertTrue(
            "the answer's own New conversation row is back",
            home.contains("Quiet(MoreMenuWords.NEW_CHAT"),
        )
        assertFalse("the old word is still drawn", home.contains("Quiet(\"New conversation\""))
        // The empty chat says where both answers are, while there is nothing
        // else on Home to read.
        assertTrue(words.contains("const val EMPTY_HINT"))
        assertTrue(home.contains("MoreMenuWords.EMPTY_HINT"))
    }

    // ---- 5. Accessibility and accidental taps ------------------------------

    @Test
    fun `the chevron is named, 48dp and reachable to a screen reader`() {
        val button = bodyOf("private fun MessageActionsButton(")
        assertTrue("the chevron has no name", button.contains("contentDescription"))
        assertTrue("the chevron never says whether it is pinned", button.contains("stateDescription"))
        assertTrue("the chevron is too small to hit", button.contains("heightIn(min = 48.dp)"))
        assertTrue("the chevron is not a button", button.contains(".pressable(onClick = onClick)"))
        assertTrue("the chevron is not drawn as the app draws icons", button.contains("Chevron("))
        // The menu says what it is about, is a heading, and closes.
        val menu = bodyOf("private fun MessageMenu(")
        assertTrue("the menu has no title", menu.contains("ChatPins.MENU_TITLE"))
        assertTrue("the menu's title is not a heading", menu.contains("heading()"))
        assertTrue("the menu cannot be dismissed", menu.contains("Dialog(onDismissRequest = onDismiss)"))
        assertTrue("the menu has no Close", menu.contains("MoreMenuWords.CLOSE"))
        // One menu, one message: it never offers a bulk action.
        assertFalse("the menu has a mark-all", menu.contains("Mark all"))
    }

    // ---- 6. The answer's time, and "was this answer right?" (2026-11-01) ----

    // Two phone gaps the owner's field test found on 2026-11-01:
    //  - the answer's own menu had no date and time, where the desktop HUD's
    //    has had one since wave-2, and
    //  - typing "was this answer right?" sent the words to the PC instead of
    //    opening that menu.
    // Both are SOURCE PINS, like everything above: a Compose screen cannot be
    // driven from a JVM unit test here. What they cannot prove is said in the
    // report: that the menu opens, shows the line and reads out on a phone.

    /** That function's body, cut where the next top-level declaration starts. */
    private fun fnOf(marker: String, text: String = home): String =
        text.substringAfter(marker).substringBefore("\n@Composable").substringBefore("\nprivate fun ")

    @Test
    fun `the menu's first line is the answer's own time, read-only`() {
        val menu = bodyOf("private fun MessageMenu(")
        // ONE line, from the pure formatter, and only when the moment is known.
        assertEquals(
            "the menu does not draw exactly one answer time",
            1,
            Regex("""HistoryView\.answerTime\(""").findAll(menu).count(),
        )
        assertTrue("the menu is not given the answer's moment", menu.contains("answerAtMs"))
        assertTrue("an unknown moment would still draw a line", menu.contains("if (whenWords.isNotEmpty())"))
        // FIRST: above the Right/Wrong pair, and above the pin.
        val at = menu.indexOf("HistoryView.answerTime(")
        assertTrue("the time line is not the menu's first line: $at", at in 0 until menu.indexOf("if (feedback != null)"))
        assertTrue("the time line is drawn after the marks", at < menu.indexOf("AnswerMarkRows("))
        assertTrue("the time line is drawn after the pin", at < menu.indexOf("ChatPins.PIN)"))
        // Read-only: plain text, no tap, no row, nothing to press.
        val line = menu.substringAfter("val whenWords").substringBefore("if (feedback != null)")
        assertTrue("the time line is not drawn as text", line.contains("Text("))
        for (control in listOf("onClick", "clickable", "pressable", "MoreRow(", "Quiet(", "Button")) {
            assertFalse("the time line is a control: $control", line.contains(control))
        }
        // The rules around it are untouched: marks and pin are still there.
        assertTrue(menu.contains("AnswerMarkRows("))
        assertTrue(menu.contains("ChatPins.PIN)"))
        assertTrue(menu.contains("ChatPins.UNPIN)"))
    }

    @Test
    fun `typing the menu request opens the menu and sends nothing`() {
        val composer = fnOf("private fun Composer(")
        // The words are decided on the phone, by a pure matcher (AnswerMenuAskTest).
        assertTrue(
            "nothing decides what a typed menu request means",
            composer.contains("com.jarvis.client.net.AnswerMenuAsk.matches(text)"),
        )
        // ...before anything is sent...
        assertTrue(
            "the words are sent before they are decided",
            composer.indexOf("AnswerMenuAsk.matches(text)") in 0 until composer.indexOf("actions.onSend()"),
        )
        // ...and all three send paths go through the ONE local action.
        assertTrue(
            "the keyboard sends by a path of its own",
            composer.contains("keyboardActions = KeyboardActions(onSend = { sendNow() })"),
        )
        assertTrue("the Send button sends by a path of its own", composer.contains("onClick = sendPress"))
        assertTrue("the coach's Send mine sends by a path of its own", composer.contains("sendMine = { sendNow() }"))
        assertTrue("the button no longer shares the one action", composer.contains("val sendPress: () -> Unit"))
        // The button's two jobs stay: Send, and Stop while an answer arrives.
        assertTrue(composer.contains("if (state.streaming) actions.onInterrupt else sendNow()"))
        // The menu branch opens the menu and sends nothing.
        val branch = composer.substringAfter("if (hasFinishedAnswer())").substringBefore("actions.onSend()")
        assertTrue("the menu never opens", branch.contains("onOpenAnswerMenu()"))
        assertFalse("the menu branch still sends", branch.contains("actions.onSend("))
        // The old direct paths are gone, so no path can slip past the decision.
        assertFalse("the keyboard still sends directly", composer.contains("if (canSend) actions.onSend()"))
        assertFalse("the button still sends directly", composer.contains("else actions.onSend"))
    }

    @Test
    fun `no finished answer says so on the phone, and sends nothing`() {
        val composer = fnOf("private fun Composer(")
        assertTrue(
            "nothing is said when there is no finished answer to open",
            composer.contains("askLine = com.jarvis.client.net.AnswerMenuAsk.NO_ANSWER"),
        )
        // Drawn by this screen and dismissible - never a Jarvis bubble.
        assertTrue("the line is never drawn", composer.contains("askLine?.let { line ->"))
        assertTrue("the line cannot be dismissed", composer.contains("onClick = { askLine = null }"))
        assertTrue("the line is not read out when it appears", composer.contains(".liveStatus()"))
        // Nothing about it comes from the PC: no notice route, no send, no API.
        for (notSent in listOf("JarvisRuntime.setNotice", "sendTypedChat", "/api/")) {
            assertFalse("the line goes through the PC: $notSent", composer.contains(notSent))
        }
        // The words stay in the box: the draft is cleared only when a menu opened.
        val sendNow = composer.substringAfter("fun sendNow()").substringBefore("val sendPress")
        val noAnswer = sendNow.substringAfter("} else {").substringBefore("}")
        assertTrue("the no-answer branch says nothing", noAnswer.contains("askLine"))
        assertFalse("the words are cleared with no menu to open", noAnswer.contains("onDraftChange"))
    }

    @Test
    fun `the menu opens only for a finished answer on screen`() {
        val reply = bodyOf("private fun Reply(")
        assertTrue("Reply never opens the menu from words", reply.contains("LaunchedEffect(openMenuRequest)"))
        assertTrue(
            "a half-written answer can open the menu",
            reply.contains("if (!streaming && text.isNotBlank()) menuOpen = true"),
        )
        // Each request opens at most ONE menu: a LazyColumn throws away what
        // scrolls off the screen, and a request left standing would open the
        // menu again on the way back without the owner asking.
        assertTrue(
            "a request can open the menu more than once",
            reply.contains("if (openMenuRequest > openMenuServed)"),
        )
        assertTrue("the request is never reported as served", reply.contains("onMenuRequestServed(openMenuRequest)"))
        assertTrue(
            "the latest served request is not kept outside the list item",
            home.contains("var answerMenuServed by remember { mutableIntStateOf(0) }"),
        )
        // The same test the chevron is drawn behind, so there is never a menu
        // over half a reply.
        assertTrue("the chevron's own rule changed", reply.contains("if (!streaming && text.isNotBlank())"))
        // The caller decides it the same way, so the "no answer" line is honest.
        assertTrue(
            "the composer does not know whether an answer finished",
            home.contains("hasFinishedAnswer = { !state.streaming && reply().isNotBlank() }"),
        )
        // A LazyColumn composes only what is on screen: bring the answer into
        // view first, so the composable that owns the menu exists to open it.
        assertTrue("the list is never scrolled to the answer", home.contains("LaunchedEffect(answerMenuTick)"))
        assertTrue(home.contains("openAnswerMenuTick = answerMenuTick"))
        assertTrue(home.contains("openAnswerMenuServed = answerMenuServed"))
        assertTrue(home.contains("onAnswerMenuServed = { answerMenuServed = it }"))
        assertTrue(home.contains("openMenuRequest = openAnswerMenuTick"))
        assertTrue(home.contains("openMenuServed = openAnswerMenuServed"))
    }

    @Test
    fun `the time comes from the answer that finished, not from the clock`() {
        val session = SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/net/ChatSession.kt")
        assertTrue("the chat keeps no answer time", session.contains("val answerAt: StateFlow<Long?>"))
        // Taken where the finished answer joins the conversation, and nowhere
        // else - never when the menu is opened.
        val commit = session.substringAfter("if (answer != null && answer.isNotBlank()")
            .substringBefore("return mine")
        assertTrue(
            "the time is not taken when the answer finishes",
            commit.contains("_answerAt.value = finishedAt"),
        )
        // Cleared with the answer's own id, so it never labels another answer.
        val send = session.substringAfter("): String? {").substringBefore("fun cancel()")
        assertTrue("a new question keeps the old answer's time", send.contains("_answerAt.value = null"))
        val newChat = session.substringAfter("fun newConversation()").substringBefore("fun continueFrom(")
        assertTrue("a new conversation keeps the old answer's time", newChat.contains("_answerAt.value = null"))
        // The screen reads it from the chat, so a menu opened later reads the
        // answer's moment and not the moment of the tap.
        assertTrue(main.contains("val answerAt by chat.answerAt.collectAsState()"))
        assertTrue(main.contains("answerAtMs = answerAt"))
        assertTrue(home.contains("val answerAtMs: Long? = null"))
        assertTrue(home.contains("answerAtMs = state.answerAtMs"))
    }
}
