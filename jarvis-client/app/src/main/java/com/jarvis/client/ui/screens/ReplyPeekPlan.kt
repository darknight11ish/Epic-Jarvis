package com.jarvis.client.ui.screens

/**
 * Home's answer box on the full-screen bar - the box the owner reads while the
 * chat is out of the way - and the rules that make a long answer readable
 * inside it (2026-11-06).
 *
 * WHAT THE OWNER REPORTED. On 2026-11-06 he attached a picture of his home
 * screen: a long answer was cut off after about three lines with "…", and the
 * only ways to read the rest were "More" and "Show chat". His words: *"if i get
 * a response from jarvis rhat is longer, i should be able to scroll down to read
 * the whole response instead of havijg to press more chat"*. The box was one
 * `Text(maxLines = 3, overflow = TextOverflow.Ellipsis)` - [LINES] is that 3,
 * kept because the box must NOT get bigger.
 *
 * HIS CHOICE, AND WHY THE BOX DOES NOT GROW. The next day the owner picked the
 * option that leaves the screen where it is: the box keeps the same footprint
 * it has today (the height of [LINES] lines of `bodyMedium` plus its own 6dp of
 * vertical padding in `HomeScreen.ReplyPeek`), and the INSIDE of it scrolls. The
 * face, the doors row and the bar do not move, and "Show chat" is still there
 * for the whole thread. The alternative - letting the box grow upward into the
 * face - was offered and turned down.
 *
 * WHY THIS IS A SEPARATE, PLAIN FILE. A Compose screen cannot be driven from
 * this project's JVM unit tests, so what a test can hold are numbers and small
 * predicates: [capDp] is the box's height at a given text size, [fits] says
 * whether an answer needs the scroll at all, and [follow] / [settle] are the
 * one rule for keeping the newest words in view. Plain `Int`/`Float`/`Boolean`
 * values and no Compose types, so `ReplyPeekPlanTest` needs no Android.
 *
 * WHAT THIS DOES NOT DECIDE. It does not draw anything and it does not measure
 * text: `HomeScreen` feeds [capDp] the `lineHeight` of the SAME style it draws
 * the answer with, so the cap is the height the old three-line `Text` had at
 * every text size - including the owner's own text-size setting, which rides on
 * the font scale (`JarvisTheme`). It also does not choose the fade's colour: it
 * only says when there is more below ([moreBelow]); the fade is drawn from the
 * existing `Chrome.surface1`, the bar's own background.
 */
internal object ReplyPeekPlan {

    /**
     * The lines the box showed before it could scroll - the old
     * `Text(maxLines = 3)`. Kept at exactly 3 on purpose: with a long answer the
     * bar must be no taller than it has always been, or the face above it and
     * the buttons below it would move.
     */
    const val LINES = 3

    /**
     * The bottom fade's height. It is drawn OVER the answer's last 12dp, never
     * as an extra row, so showing it costs no layout height and the bar cannot
     * grow when the owner drags.
     */
    const val FADE_DP = 12f

    /**
     * The line height [capDp] falls back to when a caller cannot report a real
     * one (an unspecified or non-positive `TextUnit` comes through as NaN/0).
     * It is `JarvisType.typography.bodyMedium`'s own 22sp, so a mistake at the
     * call site cannot make the answer area zero-height and silent.
     */
    const val DEFAULT_LINE_HEIGHT_SP = 22f

    /**
     * The height of the box, in dp, for a line of [lineHeightSp] at [fontScale]:
     * [LINES] whole lines, never more. Compose's `sp` becomes `dp` by the font
     * scale (`dp = sp x fontScale`), and the app's text-size setting IS a font
     * scale (`JarvisTheme`), so a larger text size gets a taller box in exactly
     * the proportion its three lines actually take - the bar is never pushed off
     * screen by this cap, because it is the height of the three lines that were
     * already being drawn.
     *
     * A caller that passes an Unspecified line height (NaN) or a broken scale
     * gets [DEFAULT_LINE_HEIGHT_SP] at scale 1 instead of an empty box.
     */
    fun capDp(lineHeightSp: Float, fontScale: Float): Float {
        val lineHeight =
            if (lineHeightSp.isFinite() && lineHeightSp > 0f) lineHeightSp
            else DEFAULT_LINE_HEIGHT_SP
        val scale = if (fontScale.isFinite() && fontScale > 0f) fontScale else 1f
        return lineHeight * scale * LINES
    }

    /**
     * Does an answer laid out as [lineCount] lines fit the box without
     * scrolling? One line, two or [LINES] do - anything more does not, and is
     * reached by dragging inside the box. `HomeScreen` asks this with the
     * answer's real line count (from the Text's own layout) for two things: so
     * TalkBack can say a long answer is long, and so the bottom fade exists
     * only for an answer that is actually longer than the box ([moreBelow]
     * then says whether any of it is still below the fold).
     */
    fun fits(lineCount: Int): Boolean = lineCount <= LINES

    /**
     * Should the box move to the newest words as they arrive? While the answer
     * is still streaming and the owner has NOT dragged the answer by hand -
     * the same rule the full-screen chat follows (`HomeScreen`'s own follow
     * effect), so the two surfaces cannot teach the owner two different
     * gestures.
     *
     * Once the owner drags, the answer is theirs: it is never yanked back, and
     * a finished answer is left where they left it ([settle] says why one
     * exception exists for a plain finish).
     */
    fun follow(streaming: Boolean, ownerDragged: Boolean): Boolean =
        streaming && !ownerDragged

    /**
     * The one exception to "leave a finished answer where it is": a reply that
     * streamed IN THIS BOX and that the owner never touched is shown its end
     * once the stream stops.
     *
     * The last token and the "no longer streaming" flag can land in the same
     * frame (`ChatSession` publishes the tail, then clears `_streaming` in the
     * same call), so the final growth of the answer is laid out after the
     * follow has stopped. Without this, the newest words - the ones the follow
     * was keeping in view - could be the only ones left below the fold.
     *
     * `streamedHere` is what keeps the other half honest: an answer that was
     * already finished when the box appeared (coming back from the chat, a
     * rotation) is left at its start, which is what the old three-line peek
     * always showed. It is also NOT called after a drag: [follow] and this
     * share the owner's rule, so a dragged answer never moves again.
     */
    fun settle(streamedHere: Boolean, ownerDragged: Boolean): Boolean =
        streamedHere && !ownerDragged

    /**
     * Is there any of the answer below the fold right now? Drives the one
     * affordance that says so - a thin fade of the bar's own background - and
     * it is false once the end is reached, so the last line is always read at
     * full contrast. False for an answer that fits, because `maxScrollPx` is 0
     * then: a box that fits looks exactly like the box before this change.
     */
    fun moreBelow(scrolledPx: Int, maxScrollPx: Int): Boolean =
        maxScrollPx > 0 && scrolledPx < maxScrollPx
}
