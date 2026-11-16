package com.jarvis.client

import com.jarvis.client.net.ChatInfo
import com.jarvis.client.net.ChatLog
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * "About this conversation" - the small card a History row's "i" opens
 * ([ChatInfo], drawn by HistoryScreen.kt).
 *
 * The owner's ask of 2026-11-15, in his words: "does chat history have in both
 * jarvis desktop and app have an info menu that i can click show (or a symbol
 * or something) om each comversation that i can look at? that includes info
 * like if the chat was on which device (phone or laptop) andmoree? without
 * this being overwhelming".
 *
 * THE POINT OF THIS FILE IS THE WORDS. The desktop's half (PR #1278) pins the
 * same sentences in `jarvis-desktop/tests/chat-info.mjs`, from the same table
 * in `jarvis-desktop/src/history-view.js`. Both apps show the same card, so a
 * re-word on either side must fail a test here or there rather than drift
 * quietly. Every sentence below is a literal on purpose: a test that compared
 * `ChatInfo.VOICE` with `ChatInfo.VOICE` would pass while the card said
 * anything at all.
 *
 * What must hold, and is pinned here:
 * - the card's exact words - title, Close, the device, the two dates, the
 *   count, and each mark's line;
 * - one line per fact, in the desktop's order, and nothing the row does not
 *   carry: a plain chat with no marks says only its device, its two dates and
 *   its message count;
 * - a date the PC did not send says "The PC did not say when." - never a
 *   guess, and never 1970 for a `0` an older PC sent;
 * - "Last used" is left out when the chat was used in the minute it started,
 *   so one time is never printed twice under two labels;
 * - a voice/taint/pin/archive line is absent when its flag is false, and the
 *   tag line appears only while the tag list may be read at all;
 * - no line names the chat's kind: the row already carries its kind mark.
 *
 * The two SOURCE PINS at the end hold the screen's arrangement still - the "i"
 * sits before the overflow menu and opens this card, and the card draws
 * `ChatInfo.card`'s lines - because a Compose screen cannot be driven from a
 * JVM unit test in this project (CI's `phone-unit-tests` job is the first
 * compiler). What a pin cannot prove is said in the PR: that the card looks
 * right and reads out on a real phone.
 */
class ChatInfoTest {

    // A fixed clock and time zone, so a date's words never depend on the day
    // this suite runs. The three constants are the desktop suite's own moments
    // (`tests/chat-info.mjs`: 14:05 and 16:40 on 2026-11-15), so the two halves
    // assert the same example card.
    private val zone = ZoneOffset.UTC
    private val today = LocalDate.of(2026, 11, 15)
    private fun at(hour: Int, minute: Int): Long =
        java.time.LocalDateTime.of(2026, 11, 15, hour, minute).toEpochSecond(ZoneOffset.UTC)

    private val STARTED = at(14, 5)
    private val UPDATED = at(16, 40)

    /** The app's own words for those two moments - the same source the row uses. */
    private val startedWords = ChatLog.whenLine(STARTED, zone, today)
    private val updatedWords = ChatLog.whenLine(UPDATED, zone, today)

    /** A row with every fact the PC sends - the "full card" case. */
    private fun everyMark(
        device: String? = "hud",
        pinned: Boolean = true,
        archived: Boolean = true,
    ) = ChatLog.Summary(
        id = "c-full",
        title = "Dentist on Tuesday",
        started = STARTED,
        updated = UPDATED,
        turns = 12,
        device = device,
        hasVoice = true,
        tainted = true,
        kind = "chat",
        tagId = 3,
        pinned = pinned,
        archived = archived,
    )

    private fun card(
        row: ChatLog.Summary,
        tagName: String? = null,
        tagsKnown: Boolean = false,
    ) = ChatInfo.card(row, zone, today, tagName = tagName, tagsKnown = tagsKnown)

    /** The full card, line for line: device, dates, count, then only the marks. */
    private val FULL = listOf(
        "Had in the HUD window on this PC.",
        "Started: Today 14:05",
        "Last used: Today 16:40",
        "12 messages",
        "Some of it was said aloud.",
        "It read text that did not come from you: a web page, a file, an email or another tool's output.",
        "Filed under: Work",
        "Pinned to the top.",
        "In Archived.",
    )

    // ------------------------------------------------------- the words ---

    @Test
    fun `the card's own words are the desktop's, exactly`() {
        assertEquals("About this conversation", ChatInfo.TITLE)
        assertEquals("Close", ChatInfo.CLOSE)
        assertEquals("Started: ", ChatInfo.STARTED)
        assertEquals("Last used: ", ChatInfo.USED)
        assertEquals("Some of it was said aloud.", ChatInfo.VOICE)
        assertEquals(
            "It read text that did not come from you: a web page, a file, an email or another tool's output.",
            ChatInfo.OUTSIDE,
        )
        assertEquals("Pinned to the top.", ChatInfo.PIN)
        assertEquals("In Archived.", ChatInfo.ARCHIVE)
        assertEquals("Filed under: ", ChatInfo.TAG_FILED)
        assertEquals("Not filed under a tag.", ChatInfo.TAG_NONE)
        assertEquals("The PC did not say when.", ChatInfo.NODATE)
        assertEquals("Filed under: Work", ChatInfo.filedUnderWords("Work"))
    }

    @Test
    fun `the time words are the row's own, so both apps say the same day`() {
        // Said as words here as well as through the builder: "Today 14:05" is
        // the phone's whenLine at a fixed clock, and the desktop's too.
        assertEquals("Today 14:05", startedWords)
        assertEquals("Today 16:40", updatedWords)
    }

    @Test
    fun `the four device words, and the row's short tag agrees with them`() {
        assertEquals("Had in the Jarvis bar on this PC.", ChatInfo.deviceWords("desktop"))
        assertEquals("Had in the HUD window on this PC.", ChatInfo.deviceWords("hud"))
        assertEquals("Had on your phone.", ChatInfo.deviceWords("phone"))
        assertEquals(
            "The PC did not say which app this was had in.",
            ChatInfo.deviceWords(null),
        )
        assertEquals(
            "The PC did not say which app this was had in.",
            ChatInfo.deviceWords("something this build does not know"),
        )
        // The card's first line and the row's own tag are two tables in two
        // files (ChatInfo's long words, ChatLog.deviceWord's short tag); they
        // must agree about the same three devices or one of them is wrong.
        assertEquals("Had in the Jarvis bar on this PC.", ChatInfo.deviceWords("desktop"))
        assertEquals("PC", ChatLog.deviceWord("desktop"))
        assertEquals("HUD", ChatLog.deviceWord("hud"))
        assertEquals("phone", ChatLog.deviceWord("phone"))
        assertEquals("unknown", ChatLog.deviceWord(null))
        // And the card's first line is that device's own sentence, not a copy.
        assertEquals("Had on your phone.", card(everyMark(device = "phone")).lines[0])
        assertEquals("Had in the Jarvis bar on this PC.", card(everyMark(device = "desktop")).lines[0])
        assertEquals("Had in the HUD window on this PC.", card(everyMark(device = "hud")).lines[0])
        assertEquals(
            "The PC did not say which app this was had in.",
            card(everyMark(device = "")).lines[0],
        )
    }

    @Test
    fun `every mark - the whole card, in order, and nothing else`() {
        val got = card(everyMark(), tagName = "Work", tagsKnown = true)
        assertEquals("About this conversation", got.title)
        assertEquals("Close", got.close)
        assertEquals(FULL, got.lines)
    }

    @Test
    fun `a plain one - device, two dates and the count, nothing else`() {
        val plain = ChatLog.Summary(
            id = "c-plain",
            title = "Boiler service",
            started = STARTED,
            updated = UPDATED,
            turns = 4,
            device = "desktop",
            hasVoice = false,
            tainted = false,
            tagId = null,
            pinned = false,
            archived = false,
        )
        val got = card(plain)
        assertEquals(
            listOf(
                "Had in the Jarvis bar on this PC.",
                "Started: Today 14:05",
                "Last used: Today 16:40",
                "4 messages",
            ),
            got.lines,
        )
        // Said separately too, so a line added for one of these facts cannot
        // slip in without failing here.
        for (absent in listOf(ChatInfo.VOICE, ChatInfo.OUTSIDE, ChatInfo.PIN, ChatInfo.ARCHIVE, ChatInfo.TAG_NONE)) {
            assertFalse("a plain chat grew a line it does not carry: $absent", got.lines.contains(absent))
        }
    }

    // -------------------------------------------------------- the dates ---

    @Test
    fun `a time the PC did not send says so - never a guess, never silence`() {
        // No dates at all: one line says the PC did not say when. The second
        // date is not the same sentence twice (both are "", so they are equal
        // and "Last used" is left out, exactly as when they are the same
        // minute).
        val bare = ChatLog.Summary(
            id = "c-bare", title = "No times", started = null, updated = null,
            turns = 1, device = "phone", hasVoice = false, tainted = false,
        )
        assertEquals(
            listOf(
                "Had on your phone.",
                "Started: The PC did not say when.",
                "1 message",
            ),
            card(bare).lines,
        )
        // Started known, last used missing: the missing one is said, on its line.
        val half = ChatLog.Summary(
            id = "c-half", title = "Half", started = STARTED, updated = null,
            turns = 2, device = "desktop", hasVoice = false, tainted = false,
        )
        assertEquals(
            listOf(
                "Had in the Jarvis bar on this PC.",
                "Started: Today 14:05",
                "Last used: The PC did not say when.",
                "2 messages",
            ),
            card(half).lines,
        )
        // Last used known, started missing.
        val otherHalf = ChatLog.Summary(
            id = "c-otherhalf", title = "Other half", started = null, updated = UPDATED,
            turns = 2, device = "desktop", hasVoice = false, tainted = false,
        )
        assertEquals(
            listOf(
                "Had in the Jarvis bar on this PC.",
                "Started: The PC did not say when.",
                "Last used: Today 16:40",
                "2 messages",
            ),
            card(otherHalf).lines,
        )
    }

    @Test
    fun `a zero time is not 1970 - it is a time the PC did not give`() {
        // The row's own whenLine says "When unknown" for a missing time and
        // would happily print "Thu 1 Jan 1970" for a 0; the desktop's whenLine
        // treats 0 as no time at all, and the card must agree with the card on
        // the PC, not with the row.
        val zeroes = ChatLog.Summary(
            id = "c-zero", title = "Zeros", started = 0L, updated = 0L,
            turns = 3, device = "hud", hasVoice = false, tainted = false,
        )
        assertEquals(
            listOf(
                "Had in the HUD window on this PC.",
                "Started: The PC did not say when.",
                "3 messages",
            ),
            card(zeroes).lines,
        )
    }

    @Test
    fun `one time, not two labels for it - used in the minute it started`() {
        val oneMoment = ChatLog.Summary(
            id = "c-one", title = "One moment", started = STARTED, updated = STARTED,
            turns = 3, device = "desktop", hasVoice = false, tainted = false,
        )
        assertEquals(
            listOf(
                "Had in the Jarvis bar on this PC.",
                "Started: Today 14:05",
                "3 messages",
            ),
            card(oneMoment).lines,
        )
    }

    // -------------------------------------------------------- the marks ---

    @Test
    fun `each mark is absent while its flag is false, present while true`() {
        fun base() = ChatLog.Summary(
            id = "c-marks", title = "Marks", started = STARTED, updated = UPDATED,
            turns = 5, device = "desktop", hasVoice = false, tainted = false,
            pinned = false, archived = false,
        )
        val without = card(base())
        assertEquals(
            listOf(
                "Had in the Jarvis bar on this PC.",
                "Started: Today 14:05",
                "Last used: Today 16:40",
                "5 messages",
            ),
            without.lines,
        )
        for (mark in listOf(ChatInfo.VOICE, ChatInfo.OUTSIDE, ChatInfo.PIN, ChatInfo.ARCHIVE)) {
            assertFalse("$mark shown with its flag false", without.lines.contains(mark))
        }
        // One at a time, so a line cannot depend on another mark being there.
        assertEquals(
            listOf(ChatInfo.VOICE),
            card(base().copy(hasVoice = true)).lines.takeLast(1),
        )
        assertEquals(
            listOf(ChatInfo.OUTSIDE),
            card(base().copy(tainted = true)).lines.takeLast(1),
        )
        assertEquals(
            listOf(ChatInfo.PIN),
            card(base().copy(pinned = true)).lines.takeLast(1),
        )
        assertEquals(
            listOf(ChatInfo.ARCHIVE),
            card(base().copy(archived = true)).lines.takeLast(1),
        )
    }

    @Test
    fun `the tag line is filed, unfiled, or not said at all when names are hidden`() {
        val base = ChatLog.Summary(
            id = "c-tag", title = "Tagged", started = STARTED, updated = UPDATED,
            turns = 1, device = "phone", hasVoice = false, tainted = false,
            tagId = 7, pinned = false, archived = false,
        )
        // Readable tag list: always says which it is, word for word.
        assertEquals("Filed under: Work", card(base, tagName = "Work", tagsKnown = true).lines.last())
        assertEquals(
            ChatInfo.TAG_NONE,
            card(base.copy(tagId = null), tagsKnown = true).lines.last(),
        )
        // Hidden memory lists / App lock, or a PC with no tag list: this screen
        // may not read tag names, so it says nothing rather than claim a chat
        // is unfiled.
        val hidden = card(base, tagName = "", tagsKnown = false)
        assertFalse(
            "a hidden tag list still spoke about filing",
            hidden.lines.any { it.startsWith("Filed under") || it == ChatInfo.TAG_NONE },
        )
        assertEquals("1 message", hidden.lines.last())
        // The name is the PC's spelling, trimmed, never re-worded.
        assertEquals("Filed under: Home", ChatInfo.filedUnderWords("  Home  "))
        // A name the PC has but the list cannot be read for is not invented.
        assertFalse(card(base, tagName = "Work", tagsKnown = false).lines.any { it.startsWith("Filed") })
    }

    @Test
    fun `the message count is the row's own word, singular, plural or none`() {
        fun row(turns: Int?) = ChatLog.Summary(
            id = "c-count", title = "Count", started = STARTED, updated = UPDATED,
            turns = turns, device = "phone", hasVoice = false, tainted = false,
        )
        assertEquals("1 message", ChatLog.messagesWords(1))
        // Both dates are known here, so the count is the line after them.
        assertEquals("1 message", card(row(1)).lines[3])
        assertEquals("12 messages", card(row(12)).lines[3])
        // A row the PC sent no count for says none, not "NaN messages".
        assertEquals("0 messages", card(row(null)).lines[3])
        assertEquals("0 messages", card(row(0)).lines[3])
        assertEquals("0 messages", card(row(-4)).lines[3])
    }

    @Test
    fun `nothing about the chat's kind - the row already carries it`() {
        // A Live session, a support record and a chatbot row all produce the
        // same lines as an ordinary chat with the same facts: the card is for
        // what the row does NOT say, and its kind is not one of those things.
        val kinds = listOf("chat", "live", "support", "chatbot", "compare")
        for (kind in kinds) {
            val got = card(everyMark().copy(kind = kind), tagName = "Work", tagsKnown = true)
            assertEquals("kind $kind grew a line", FULL, got.lines)
            for (tag in listOf("Live", "Support chat", "Chat with an AI", "Comparison")) {
                assertFalse("kind $kind leaked the kind mark $tag", got.lines.contains(tag))
            }
        }
    }

    @Test
    fun `the card is read-only data - nothing the row does not hold is shown`() {
        // A row carrying everything the PC sends, including the fields the card
        // is not allowed to show, must produce exactly the full card.
        val noisy = everyMark().copy(
            pinnedAt = 1_700_000_000L,
            kind = "live",
            tagId = 3,
        )
        assertEquals(FULL, card(noisy, tagName = "Work", tagsKnown = true).lines)
        // And a row whose tag id the tag list does not know is unfiled, not a
        // name this card made up (the desktop's `tagById` returns null too).
        // The tag line is the seventh of the full card, before the pin and the
        // archive marks, so it is found by what it says rather than by position.
        val unknownTag = card(everyMark().copy(tagId = 99), tagName = null, tagsKnown = true).lines
        assertTrue("an unknown tag was not called unfiled", unknownTag.contains(ChatInfo.TAG_NONE))
        assertFalse("an unknown tag was given a name", unknownTag.any { it.startsWith("Filed under") })
    }

    // ------------------------------------------------- the screen's wiring ---
    //
    // SOURCE PINS, the same shape as ChatMenuTest: they read the screen file and
    // hold the arrangement still. What they cannot prove - that the dialog
    // opens, looks right and reads out - is said in the PR.

    private val history by lazy { SourceFile.read("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HistoryScreen.kt") }

    @Test
    fun `the row draws a small i, before the overflow menu, named About the title`() {
        // One row composable draws both the list and the search results, so one
        // pin holds both readers of a conversation.
        val aboutAt = history.indexOf("contentDescription = ChatInfo.aboutFor(row.title)")
        val menuAt = history.indexOf("contentDescription = HistoryView.actionsFor(row.title)")
        assertTrue("the row never draws the i", aboutAt > 0)
        assertTrue("the i is not drawn before the overflow menu", aboutAt < menuAt)
        assertTrue(
            "the i is not a Quiet action like the menu beside it",
            history.substring(aboutAt, menuAt).contains("Quiet("),
        )
        assertTrue(
            "the i is not the row's quiet tone",
            history.substring(aboutAt, menuAt).contains("color = chrome.textLo"),
        )
    }

    @Test
    fun `the card is one dialog, drawn from ChatInfo's lines, with Close`() {
        val card = history.substringAfter("private fun ChatInfoCard(").substringBefore("\n/**")
        assertTrue("the card never draws ChatInfo's lines", card.contains("ChatInfo.card("))
        assertTrue("the card draws no lines", card.contains("card.lines.forEach"))
        assertTrue("the card's heading is not ChatInfo's", card.contains("card.title"))
        assertTrue("the card has no Close", card.contains("card.close"))
        // One dialog, closed by Close, by Back and by a tap outside: the flat
        // Dialog's own onDismissRequest is all three.
        assertTrue("the card is not the app's one Dialog", card.contains("Dialog(onDismissRequest = onClose)"))
        assertEquals(
            "the card is not declared once and drawn once",
            2,
            Regex("ChatInfoCard\\(").findAll(history).count(),
        )
    }
}
