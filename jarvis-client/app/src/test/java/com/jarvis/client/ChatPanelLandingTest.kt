package com.jarvis.client

import com.jarvis.client.ui.parts.ChatLanding
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Show chat" must show the chat (the owner's bug report of 2026-11-02).
 *
 * In their words: *"this is an example of the show chat and then back to full
 * screen in the Android app not showing the chat properly"* - two screenshots,
 * the second showing the panel at the top of the thread with the answer below
 * the panel's bottom edge and the question cut in half at that edge.
 *
 * SOURCE PINS, the same shape as [PhoneFaceBarTest] and [ChatMenuTest]: a
 * Compose screen cannot be driven from a JVM unit test in this project, so what
 * is pinned here is the arrangement and the arithmetic - plus [ChatLanding]'s
 * numbers, which are plain integers and can be held exactly.
 *
 * What these cannot prove, and the PR says so: that the panel really lands on
 * the newest words on a real phone, that the answer is legible at the owner's
 * text size, and that a chat whose last row is taller than the panel scrolls
 * smoothly rather than jumping. This lane has no device; the APK that reaches
 * the phone is CI's.
 */
class ChatPanelLandingTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val parts = "jarvis-client/app/src/main/java/com/jarvis/client/ui/parts/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }
    private val landing by lazy { SourceFile.read(parts + "ChatLanding.kt") }

    // A) The arithmetic -------------------------------------------------------

    @Test
    fun `the scroll is the amount that puts the newest row's bottom at the panel's edge`() {
        // The owner's own phone, in pixels: a panel about 550px tall (their
        // split gives the chat about 200dp at 2.75x) and a newest row about
        // 1,240px - the question, the answer, where it came from, the memories
        // it used - starting at the top of the viewport after the list has
        // scrolled to it. 690px of that row is past the bottom edge.
        assertEquals(690, ChatLanding.overhangPx(0, 1_240, 550))
        // An answer shorter than the panel needs no scroll: its bottom is
        // already in view, and the panel must not jump for nothing.
        assertEquals(0, ChatLanding.overhangPx(0, 300, 550))
        // Half in view: only the part past the edge is scrolled, not the whole
        // row - the top of the answer stays where the owner put it.
        assertEquals(90, ChatLanding.overhangPx(400, 240, 550))
        // Flush is not an overhang. Items are measured at the same size on
        // consecutive frames all the time, so a 0px scroll has to stay 0.
        assertEquals(0, ChatLanding.overhangPx(0, 550, 550))
        // A row whose measured start is above the viewport can never ask for a
        // negative scroll (a LazyColumn reports the row above as a negative
        // offset while it is still partly on screen).
        assertEquals(0, ChatLanding.overhangPx(-40, 100, 550))
    }

    // B) The screen wires it to "Show chat" -----------------------------------

    @Test
    fun `the chat opened from full screen lands on the newest words`() {
        // The precondition, and the whole reason the bug was only visible from
        // here: full screen composes NO conversation list, so the list is laid
        // out for the first time the moment the chat is opened.
        val voiceBranch = home.substringAfter("if (voiceMode) {").substringBefore("} else {")
        assertFalse(
            "full screen now composes the conversation list, so this test's premise is gone",
            voiceBranch.contains("ConversationList("),
        )
        // The button the owner pressed, and the flag it sets.
        assertTrue("the face bar no longer offers Show chat", home.contains("\"Show chat\","))
        assertTrue("Show chat no longer opens the chat", home.contains("onShowChat = { peekChat = true }"))
        // A question typed in the face bar opens the chat too (the same move),
        // so it lands the same way.
        assertTrue("a typed question no longer opens the chat", home.contains("onTypedSend = { peekChat = true }"))
        // ...and ONE effect reacts to the chat opening.
        assertEquals(
            "the chat opening is not watched by exactly one effect",
            1,
            Regex("LaunchedEffect\\(peekChat\\)").findAll(home).count(),
        )
        val effect = home.substringAfter("LaunchedEffect(peekChat) {").substringBefore("}")
        assertTrue(
            "opening the chat still starts at the top of the thread",
            effect.contains("landOnNewest(listState)"),
        )
        // "Back to full screen" only closes the chat, so opening it again runs
        // the effect again - there is no "already scrolled" state to be stuck
        // in, which is the second half of the owner's report.
        assertTrue(home.contains("Quiet(\"Back to full screen\", onClick = { peekChat = false })"))
    }

    // C) The helper itself ----------------------------------------------------

    @Test
    fun `landing waits for the list to be measured, then ends on the newest row`() {
        val fn = landing.substringAfter("internal suspend fun landOnNewest(")
        // 1. A list being measured for the first time has no rows yet, and
        // scrolling it then is what left the owner at row 0. So wait for rows.
        assertTrue(
            "landing scrolls before the list has any rows",
            fn.contains("while (state.layoutInfo.totalItemsCount == 0"),
        )
        assertTrue("landing does not wait a frame", fn.contains("withFrameNanos { }"))
        // 2. It lands on the LAST row...
        assertTrue("landing does not find the newest row", fn.contains("val newest = count - 1"))
        assertTrue(fn.contains("state.scrollToItem(newest)"))
        // 3. ...and then on that row's bottom, using the shared arithmetic
        // rather than a second copy of "offset + size - viewportEnd".
        val top = fn.indexOf("state.scrollToItem(newest)")
        val bottom = fn.indexOf("ChatLanding.overhangPx(")
        assertTrue("landing no longer scrolls past the newest row's top", bottom > top)
        assertTrue(fn.contains("ChatLanding.overhangPx(item.offset, item.size, info.viewportEndOffset)"))
        assertTrue("landing no longer moves to the row's bottom", fn.contains("state.scrollBy(overhang.toFloat())"))
        // The wait is bounded: a list that never appears must not leave a
        // coroutine spinning for the life of the screen.
        assertTrue("the wait for rows is unbounded", landing.contains("const val WAIT_FRAMES = 30"))
    }

    // D) The other way into the same panel ------------------------------------

    @Test
    fun `the answer's own menu lands the same way`() {
        // "Was this answer right?" typed into a box opens the chat and asks for
        // the answer's menu. It used to scroll to the newest row's TOP, which
        // is the same half-visible panel the owner photographed - the question
        // on screen, the answer under the edge.
        val effect = home.substringAfter("LaunchedEffect(answerMenuTick) {").substringBefore("}")
        assertTrue(
            "the answer's menu still lands on the answer's top",
            effect.contains("landOnNewest(listState, animate = true)"),
        )
        assertFalse(
            "the answer's menu is back to scrolling only to the newest row's top",
            effect.contains("animateScrollToItem("),
        )
        // The one other "bring it into view" effect - a chat carried on from
        // History - is left as it was ON PURPOSE: there the fold is open and
        // starts at the newest pair, so the top of the plate is the carried-on
        // chat itself, not the "Earlier in this chat" header the owner's
        // screenshot was stuck on.
        assertTrue(
            "the carried-on chat no longer lands on its own reply plate",
            Regex("LaunchedEffect\\(carriedOn, state\\.chatNote\\)[\\s\\S]{0,220}?animateScrollToItem\\(")
                .containsMatchIn(home),
        )
    }

    // E) What must NOT change -------------------------------------------------

    @Test
    fun `the follow-the-reply effect still follows a streaming reply`() {
        // Not this change's business, but it is the one thing that already kept
        // an arriving answer in view, and if it went the panel would have no
        // way to follow a reply at all - this fix would then be read as
        // covering that too. Its own gate is also WHY a finished chat stayed
        // where it was first laid out.
        assertTrue(home.contains("last.key != REPLY_KEY -> Int.MAX_VALUE"))
        assertTrue(home.contains("listState.scrollBy(overhang.toFloat())"))
        assertTrue(
            "the reply is no longer followed while it streams",
            home.contains("LaunchedEffect(state.streaming, state.followReply, state.focusApproval)"),
        )
        // The split is untouched: the list still keeps its floor, so landing
        // the chat never pushes an approval card off the screen.
        assertTrue(home.contains("val listFloor = with(density) { MIN_LIST_HEIGHT.toPx().roundToInt() }"))
    }
}
