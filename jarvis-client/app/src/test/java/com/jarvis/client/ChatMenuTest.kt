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
    fun `pinned messages is its own screen, opened from the chat's menu`() {
        assertTrue("Home has no route to the pinned list", home.contains("actions.onOpenPins()"))
        assertTrue("the More menu does not name it", home.contains("ChatPins.TITLE"))
        assertTrue(
            "the row has no line under it saying what it is",
            home.contains("detail = MoreMenuWords.PINNED_DETAIL"),
        )
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
    fun `the menu leads with new chat, earlier chats and the pins`() {
        val menu = bodyOf("private fun HomeMoreMenu(")
        val order = listOf("MoreMenuWords.NEW_CHAT", "ChatHistory.EARLIER_CHATS", "ChatPins.TITLE")
        val at = order.map { menu.indexOf(it) }
        assertTrue("the chat rows are not all in the menu: $at", at.all { it >= 0 })
        assertEquals("the chat rows are not in the order new, earlier, pinned: $at", at.sorted(), at)
        // Exactly one "Earlier chats" row - it must not come back twice.
        val mentions = Regex("ChatHistory\\.EARLIER_CHATS").findAll(home).count()
        assertEquals("Earlier chats is drawn more than once", 1, mentions)
        // "New chat" is the same mechanism the idle timer uses, not a new one.
        assertTrue(menu.contains("actions.onNewConversation()"))
        assertTrue(
            "a new chat no longer goes through the chat's own reset",
            main.contains("onNewConversation = { chat.newConversationSaid() }"),
        )
        // TWO doors, ONE action, and no third way: the More menu's row and the
        // row under a finished answer both call the action Home hands in, and
        // HomeScreen never mints a conversation id or resets the session itself.
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
}
