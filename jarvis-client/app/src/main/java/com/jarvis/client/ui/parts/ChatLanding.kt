package com.jarvis.client.ui.parts

import androidx.compose.foundation.gestures.animateScrollBy
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.withFrameNanos

/**
 * Landing a conversation on its newest words (the owner's report, 2026-11-02).
 *
 * In full screen the phone composes no conversation list at all - only the face
 * and its small bar - so a chat opened with "Show chat" is laid out for the
 * FIRST time at that moment, and a `LazyColumn` laid out for the first time
 * starts at its first row. On the owner's phone that row is their Home cards,
 * then the collapsed "Earlier in this chat", then the question: the answer they
 * had just been reading sat below the panel's bottom edge, and the question was
 * cut in half at that edge. Their two screenshots of 2026-11-02 show exactly
 * that, and their words were "the show chat and then back to full screen in the
 * Android app not showing the chat properly".
 *
 * Nothing else moved it. The follow-the-reply effect only runs while an answer
 * is still arriving, so a finished chat stayed where it happened to be laid out.
 *
 * WHY THE ARITHMETIC IS ITS OWN OBJECT. A Compose screen cannot be driven from
 * this project's JVM unit tests, so [overhangPx] is plain numbers a test can
 * hold exactly - the same shape as `FaceBarPlan`, and for the same reason.
 * [landOnNewest] is the Compose half that uses it.
 */
internal object ChatLanding {

    /** Frames to wait for a list that is being measured for the first time. */
    const val WAIT_FRAMES = 30

    /**
     * How far the list still has to move for an item [itemHeight] tall that
     * starts at [itemStart] to end exactly at [viewportEnd] - the scroll that
     * puts the newest words at the panel's bottom edge.
     *
     * Zero when it already fits, which is the ordinary case: most answers are
     * shorter than the panel. This is the same line the streaming reply's own
     * follow effect uses (`last.offset + last.size - viewportEndOffset`), kept
     * here so the two cannot disagree about what "the newest is in view" means.
     */
    fun overhangPx(itemStart: Int, itemHeight: Int, viewportEnd: Int): Int =
        (itemStart + itemHeight - viewportEnd).coerceAtLeast(0)
}

/**
 * Scrolls [state] so that its LAST row ends at the bottom edge of the panel.
 *
 * Two steps, because they are two different failures. The newest row has to be
 * composed at all - the list may be about to be measured for the first time in
 * this very frame, and asking it to scroll before it has rows would send it to
 * row 0, which is the bug this exists to undo - and then it has to be shown
 * from its END rather than its start. The newest row is usually taller than the
 * panel (the question, the answer, where it came from, "Used N memories"), so
 * scrolling to its top alone leaves the answer under the bottom edge: that is
 * the half of the owner's screenshot that was not the scroll position itself.
 *
 * @param animate glide instead of jump. Off for a panel that has just
 *   appeared - the owner should not watch it scroll through rows they never
 *   saw - and on for a list that is already on screen.
 */
internal suspend fun landOnNewest(state: LazyListState, animate: Boolean = false) {
    var waited = 0
    while (state.layoutInfo.totalItemsCount == 0 && waited < ChatLanding.WAIT_FRAMES) {
        waited++
        withFrameNanos { }
    }
    val count = state.layoutInfo.totalItemsCount
    if (count == 0) return
    val newest = count - 1
    if (animate) state.animateScrollToItem(newest) else state.scrollToItem(newest)
    val info = state.layoutInfo
    val item = info.visibleItemsInfo.lastOrNull { it.index == newest } ?: return
    val overhang = ChatLanding.overhangPx(item.offset, item.size, info.viewportEndOffset)
    if (overhang <= 0) return
    if (animate) state.animateScrollBy(overhang.toFloat()) else state.scrollBy(overhang.toFloat())
}
