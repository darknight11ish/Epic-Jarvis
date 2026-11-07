package com.jarvis.client

import com.jarvis.client.ui.screens.ReplyPeekPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Home's answer box on the full-screen bar, and the rule that makes a long
 * answer readable without the chat (2026-11-06).
 *
 * WHAT THE OWNER REPORTED, AND CHOSE. A long answer was cut off after about
 * three lines with "…": *"if i get a response from jarvis rhat is longer, i
 * should be able to scroll down to read the whole response instead of havijg to
 * press more chat"*. The next day he chose the box that stays where it is -
 * same footprint, scrolling INSIDE it - rather than one that grows into the
 * face.
 *
 * SOURCE PINS, the same shape as [PhoneFaceBarTest] and [ChatMenuTest]: a
 * Compose screen cannot be driven from this project's JVM unit tests, so what
 * is held here is [ReplyPeekPlan]'s plain numbers and predicates (no Android
 * types in that object at all), plus the arrangement of the box in
 * `HomeScreen.kt` - the scroll, the cap, the fade and the follow rule.
 *
 * WHAT THESE CANNOT PROVE is said in the PR: that a real drag scrolls the
 * answer on the owner's Pixel, that TalkBack announces the area as scrollable,
 * that the bar looks the same as before when the answer fits, and that no line
 * is ever cut on a 360dp phone - this lane has no device to install the APK on.
 */
class ReplyPeekPlanTest {

    private val screens = "jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/"
    private val home by lazy { SourceFile.read(screens + "HomeScreen.kt") }
    private val plan by lazy { SourceFile.read(screens + "ReplyPeekPlan.kt") }

    /** The whole of the answer box, from its name to the next composable. */
    private val replyPeek by lazy {
        home.substringAfter("private fun ReplyPeek(")
            .substringBefore("private fun TemporaryChatMarker(")
    }

    /** The whole of the full-screen bar, from its name to the answer box. */
    private val voiceBar by lazy {
        home.substringAfter("private fun VoiceBar(")
            .substringBefore("private fun ReplyPeek(")
    }

    // A) The footprint ---------------------------------------------------------

    @Test
    fun `the box is exactly the three lines it always showed, at every text size`() {
        // `bodyMedium` is 15sp on a 22sp line (`JarvisType.typography`), so the
        // default box is 3 x 22 = 66dp - the height the old `maxLines = 3` Text
        // had. It is the same 3 on purpose: the face and the bar must not move
        // for a long answer.
        assertEquals("the peek changed how many lines it shows", 3, ReplyPeekPlan.LINES)
        assertEquals(66f, ReplyPeekPlan.capDp(22f, 1f), 0.001f)

        // Text size rides on the font scale, so the box grows in exactly the
        // proportion its own three lines grow. At the app's own limits
        // (`JarvisTheme`: 0.85x-1.5x of the phone's choice) it is never a box
        // that has outgrown the lines it was sized for, and never a tiny one.
        assertEquals(56.1f, ReplyPeekPlan.capDp(22f, 0.85f), 0.001f)
        assertEquals(85.8f, ReplyPeekPlan.capDp(22f, 1.3f), 0.001f)
        assertEquals(99f, ReplyPeekPlan.capDp(22f, 1.5f), 0.001f)

        // A broken reading (an Unspecified TextUnit arrives as NaN) must never
        // make the answer area zero-height and silent: it falls back to the
        // style's own 22sp instead.
        assertEquals(66f, ReplyPeekPlan.capDp(Float.NaN, 1f), 0.001f)
        assertEquals(66f, ReplyPeekPlan.capDp(22f, Float.NaN), 0.001f)
        assertEquals(66f, ReplyPeekPlan.capDp(0f, 1f), 0.001f)
    }

    // B) Does it fit ----------------------------------------------------------

    @Test
    fun `an answer that fits does not scroll, a longer one does`() {
        // One, two or three lines need no scroll at all: the box looks exactly
        // like the box before this change.
        assertTrue(ReplyPeekPlan.fits(0))
        assertTrue(ReplyPeekPlan.fits(1))
        assertTrue(ReplyPeekPlan.fits(2))
        assertTrue(ReplyPeekPlan.fits(3))
        // A fourth line is the first line that has to be reached by dragging.
        assertFalse(ReplyPeekPlan.fits(4))
        assertFalse(ReplyPeekPlan.fits(40))

        // The fade's rule: no more below when the content fits (no scroll
        // range at all), so a fitting answer shows no affordance...
        assertFalse(ReplyPeekPlan.moreBelow(0, 0))
        // ...and while it does not fit the fade is there at the start and part
        // way, and gone at the end, so the last line is never dimmed.
        assertTrue(ReplyPeekPlan.moreBelow(0, 100))
        assertTrue(ReplyPeekPlan.moreBelow(40, 100))
        assertFalse(ReplyPeekPlan.moreBelow(100, 100))
    }

    // C) Following the newest words ------------------------------------------

    @Test
    fun `the newest words follow until the owner drags, and a drag is never yanked back`() {
        // While a reply streams, the newest words are kept in view - the same
        // rule the full-screen chat's own list follows.
        assertTrue(ReplyPeekPlan.follow(streaming = true, ownerDragged = false))
        // The owner dragged the answer by hand: it is theirs, for the rest of
        // that answer. This is the whole point of the rule.
        assertFalse(ReplyPeekPlan.follow(streaming = true, ownerDragged = true))
        // A finished answer is not followed: it stays where the owner left it.
        assertFalse(ReplyPeekPlan.follow(streaming = false, ownerDragged = false))
        assertFalse(ReplyPeekPlan.follow(streaming = false, ownerDragged = true))

        // The one exception, and only for a plain finish: a reply that streamed
        // IN THIS BOX and was never touched is shown its end once the stream
        // stops - the last token and the stop flag can land in the same frame,
        // and the newest words must not be the hidden ones.
        assertTrue(ReplyPeekPlan.settle(streamedHere = true, ownerDragged = false))
        assertFalse(ReplyPeekPlan.settle(streamedHere = true, ownerDragged = true))
        // An answer that was already finished when the box appeared (coming
        // back from the chat, a rotation) keeps its start in view, which is
        // what the old three-line peek always showed.
        assertFalse(ReplyPeekPlan.settle(streamedHere = false, ownerDragged = false))
        assertFalse(ReplyPeekPlan.settle(streamedHere = false, ownerDragged = true))
    }

    // D) The box in HomeScreen -------------------------------------------------

    @Test
    fun `the box scrolls inside itself instead of truncating the answer`() {
        // The old truncation is gone: no line limit and no ellipsis on the
        // answer. Every word must be reachable by dragging.
        assertFalse(
            "the old maxLines = 3 is back",
            replyPeek.contains("maxLines = 3"),
        )
        assertFalse(
            "the old ellipsis on the answer is back",
            replyPeek.contains("overflow = TextOverflow.Ellipsis"),
        )
        assertFalse("the answer box still limits lines somewhere", Regex("maxLines").containsMatchIn(replyPeek))

        // A real scroll viewport inside the box, driven by a remembered state -
        // not the whole Home page scrolling, which would move the face and the
        // bar under the owner's thumb.
        assertTrue("the answer has no scroll state", replyPeek.contains("rememberScrollState()"))
        assertTrue("the answer is not inside a vertical scroll", replyPeek.contains(".verticalScroll(scrollState)"))

        // The height is the plan's cap, never more: a long answer cannot grow
        // the box, and a short one keeps its own shorter height.
        assertTrue("the cap does not come from the plan", replyPeek.contains("ReplyPeekPlan.capDp("))
        assertTrue("the box is not capped at the plan's height", replyPeek.contains("heightIn(max = cap)"))

        // The footprint the owner knows is untouched: the same 6dp above and
        // below, the same style, the same colour.
        assertTrue(
            "the box lost the padding it had",
            replyPeek.contains(".padding(vertical = 6.dp)"),
        )
        assertTrue(
            "the answer's text style changed",
            replyPeek.contains("style = MaterialTheme.typography.bodyMedium"),
        )
        assertTrue(
            "the answer's colour changed",
            replyPeek.contains("color = chrome.textMid"),
        )

        // The answer is still ONE plain Text - no second rendering path and no
        // markdown scope added by a scrolling change.
        assertEquals(
            "the answer box draws more than one text",
            1,
            Regex("Text\\(").findAll(replyPeek).count(),
        )
        assertFalse(
            "the answer box became a FormattedAnswer",
            replyPeek.contains("FormattedAnswer("),
        )
    }

    @Test
    fun `the box asks the plan for every rule, and the plan keeps them in one place`() {
        // One read of each rule, from the plan - not a second copy of any of
        // them here.
        assertEquals(
            "the follow rule is written more than once",
            1,
            Regex("ReplyPeekPlan\\.follow\\(").findAll(replyPeek).count(),
        )
        assertEquals(
            "the settle rule is written more than once",
            1,
            Regex("ReplyPeekPlan\\.settle\\(").findAll(replyPeek).count(),
        )
        assertTrue("the fade is not gated by the plan", replyPeek.contains("ReplyPeekPlan.moreBelow("))
        assertTrue("the fit rule is not asked", replyPeek.contains("ReplyPeekPlan.fits("))

        // The bar hands the box the owner's own "Follow the reply" setting, so
        // the two surfaces obey one setting and cannot disagree.
        assertTrue(
            "the box is not given the owner's follow setting",
            home.contains("ReplyPeek(reply, state.streaming, state.followReply)"),
        )

        // A drag is detected from the scroll's own interactions - the only
        // honest "the owner did it" signal, because the value also moves on
        // every followed token.
        assertTrue("the drag is not detected", replyPeek.contains("DragInteraction.Start"))

        // The affordance costs no height and adds no new colour: the bar's own
        // surface, drawn over the last lines.
        assertTrue("the fade's height is not the plan's", replyPeek.contains("ReplyPeekPlan.FADE_DP.dp"))
        assertTrue("the fade does not use the bar's background", replyPeek.contains("chrome.surface1"))
        assertTrue("the fade does not start transparent", replyPeek.contains("Color.Transparent"))

        // The plan itself keeps the numbers this suite just held: the three
        // lines, the cap, the fit / follow / settle / fade rules.
        for (pin in listOf(
            "const val LINES = 3",
            "const val FADE_DP",
            "fun capDp(",
            "fun fits(",
            "fun follow(",
            "fun settle(",
            "fun moreBelow(",
        )) {
            assertTrue("the plan lost: $pin", plan.contains(pin))
        }
    }

    @Test
    fun `Show chat and More stay, and the answer box stays above the bar's buttons`() {
        // The owner asked for scrollable text, not for a second full-screen
        // chat: both buttons are where they were.
        assertTrue("Show chat is gone from the bar", voiceBar.contains("\"Show chat\""))
        assertTrue("More is gone from the bar", voiceBar.contains("MoreMenuWords.MORE"))

        // The answer box is drawn ABOVE the row whose buttons those are (it is
        // a Column child before the bar's row), so a drag inside the answer can
        // never swallow an "Ask Jarvis"/mic/Stop tap - there is no overlap and
        // no shared touch target.
        val peekCall = voiceBar.indexOf("ReplyPeek(")
        val barRow = voiceBar.indexOf("Box(Modifier.fillMaxWidth().heightIn(min = 56.dp))")
        assertTrue("the answer box is not on the bar", peekCall >= 0)
        assertTrue("the bar's button row is not found", barRow > 0)
        assertTrue(
            "the answer box is drawn below the bar's buttons: $peekCall vs $barRow",
            peekCall < barRow,
        )

        // Home has this one answer box, on the full-screen bar, and nowhere
        // else: a second peek would be a second place for the answer to drift.
        assertEquals(
            "Home draws more than one answer peek",
            2, // the definition and its one call
            Regex("ReplyPeek\\(").findAll(home).count(),
        )
    }
}
