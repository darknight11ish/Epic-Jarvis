package com.jarvis.client.ui.parts

import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.withFrameNanos

/** Enough steps for any list in this app; a guard against looping, not a limit anyone meets. */
private const val MAX_STEPS = 60

/**
 * How many frames the walk waits, in a row, for a list that has not laid the
 * item out yet. Two real cases need the wait (both found on 2026-10-11):
 *
 *  * a list whose `totalItemsCount` is positive a frame or two before its first
 *    row is visible - Brain's is, and the old walk ended there with no scroll
 *    at all;
 *  * an item a heading has just been asked to OPEN, which is added by the NEXT
 *    composition - so there is often no scrollable room for it yet, and the old
 *    walk returned "not found" one frame before it existed.
 *
 * 30 frames is half a second at 60fps: long enough for a composition, short
 * enough that an item which is genuinely not there ends the walk quickly.
 */
private const val WAIT_FRAMES = 30

/**
 * Looks at one frame of a lazy list and decides what the walk does next.
 *
 * Pure, and separate from [scrollToKey], so the rule that actually broke on
 * 2026-10-11 can be driven by a JVM test with a list it controls: the walk must
 * WAIT when there is no room to move, not treat it as "not found", because the
 * item it is looking for may be one composition away.
 *
 * @param firstVisibleIndex the list's own first visible item.
 * @param totalItemsCount what the list is made of this frame.
 * @param visibleKeys the keys of the rows actually laid out, in order.
 * @param visibleIndexes their item indexes, the same length and order.
 * @param waited how many frames in a row this walk has already waited.
 */
internal sealed interface Walk {
    /** The key was on screen. */
    data object Found : Walk

    /** Scroll this item to the top, then look again. */
    data class Step(val index: Int) : Walk

    /** Nothing to do this frame; look again next frame. Kept for [waited] frames. */
    data object Wait : Walk

    /** Not in this list (or not reachable by walking down): stop. */
    data object GiveUp : Walk
}

/** One frame's decision. [visibleKeys] and [visibleIndexes] are parallel lists. */
internal fun walkStep(
    key: String,
    firstVisibleIndex: Int,
    totalItemsCount: Int,
    visibleKeys: List<Any?>,
    visibleIndexes: List<Int>,
    waited: Int,
): Walk {
    if (visibleKeys.any { it == key }) return Walk.Found
    val last = visibleIndexes.lastOrNull() ?: return if (waited >= WAIT_FRAMES) Walk.GiveUp else Walk.Wait
    if (last >= totalItemsCount - 1) {
        // At the bottom already. The item may be one composition away, so wait
        // a little rather than declaring it missing on the first frame.
        return if (waited >= WAIT_FRAMES) Walk.GiveUp else Walk.Wait
    }
    // The last item on screen goes to the top. One taller than the screen would
    // never move that way, so step past it instead.
    return Walk.Step(if (last > firstVisibleIndex) last else last + 1)
}

/**
 * Brings the item whose `item(key = ...)` is [key] into view, once per new
 * [key], then calls [onDone] - whether or not it was found. Null does nothing.
 *
 * For "open <a place>" by voice or chat ([com.jarvis.client.ui.OpenPlace]),
 * Home's Galaxy button, and Settings' own "Jump to:" list. SettingsScreen keeps
 * a fixed index map too, but only as the layout record OpenPlaceTest reads: a
 * hidden menu (2026-09-30) shifts every item below it, so both go by key.
 *
 * [onOpen] is for a screen whose items are inside something that can be shut
 * (Brain's headings, BrainScreen.kt and BrainSections.kt): an item inside a
 * shut heading is not in the list at all, so the walk would never find it. It
 * is called ONCE for the jump, before the walk, with the key being looked for,
 * and the caller opens whatever holds that key. A screen with nothing to open
 * leaves it out. Once per jump matters: opening a heading is a state write, and
 * calling it on every frame would re-open a heading the owner had just shut.
 *
 * [tick] is for a caller that can ask for the SAME key twice - Settings' jump
 * list, where tapping "Voice" again after scrolling away must scroll again. The
 * effect keys on [key] and [tick] together, so a new tick re-runs it while
 * [key] stays the plain `item(key = ...)` it looks up.
 */
@Composable
fun ScrollToKeyOnce(
    state: LazyListState,
    key: String?,
    tick: Int = 0,
    onOpen: (String) -> Unit = {},
    onDone: () -> Unit,
) {
    val done by rememberUpdatedState(onDone)
    val opened by rememberUpdatedState(onOpen)
    LaunchedEffect(key, tick) {
        val target = key ?: return@LaunchedEffect
        // Already on screen (or nothing laid out yet, which only happens on the
        // very first frames): judge it instead of opening its holder and moving
        // the list under the owner's finger. A list with nothing laid out yet
        // waits below rather than opening anything.
        var openAsked = false
        var waited = 0
        while (waited < WAIT_FRAMES) {
            val info = state.layoutInfo
            if (info.visibleItemsInfo.isEmpty()) {
                waited++
                withFrameNanos { }
                continue
            }
            if (info.visibleItemsInfo.any { it.key == target }) {
                state.animateScrollToItem(info.visibleItemsInfo.first { it.key == target }.index)
                done()
                return@LaunchedEffect
            }
            if (!openAsked) {
                // The holder is shut, so the item is not in the list at all.
                // Open it, and give the composition a frame to lay its plates
                // out before walking.
                openAsked = true
                opened(target)
                withFrameNanos { }
                continue
            }
            // Open (or nothing to open): walk down a screenful at a time.
            if (scrollToKey(state, target, fromTop = false)) {
                val hit = state.layoutInfo.visibleItemsInfo.firstOrNull { it.key == target }
                if (hit != null) state.animateScrollToItem(hit.index)
                done()
                return@LaunchedEffect
            }
            break
        }
        done()
    }
}

/**
 * Brings the item keyed [key] into view - the walk [ScrollToKeyOnce] does, on
 * its own, for a caller that is already inside an effect.
 *
 * Home's "Open the approval" is the reason this is separate (second Android
 * audit, N3, 2026-10-09): it used to reach its card by adding up the
 * conditional items above it by hand, which silently named the wrong row the
 * moment anything was added to that list. The approval cards are keyed by their
 * own id, so the card's key finds it wherever it is.
 *
 * [fromTop] scrolls to the first item before walking. The walk only ever moves
 * down, which is right for a screen that opens at the top (Settings' jump list,
 * "open a place"), but Home can be opened by a notification with its thread
 * scrolled anywhere, so it asks for the search to start at the top.
 *
 * The rule is [walkStep]'s, and it is pure so a test can drive it: wait while
 * the list is still laying itself out, scroll a screenful while there is room,
 * give up only after [WAIT_FRAMES] frames of nothing, and after [MAX_STEPS]
 * moves. It used to stop the moment it could not move, which is exactly how a
 * jump to a just-opened heading silently did nothing.
 *
 * @return whether the key was found.
 */
suspend fun scrollToKey(state: LazyListState, key: String, fromTop: Boolean = false): Boolean {
    if (fromTop) state.scrollToItem(0)
    var steps = 0
    var waited = 0
    while (steps < MAX_STEPS) {
        val info = state.layoutInfo
        val decision = walkStep(
            key = key,
            firstVisibleIndex = state.firstVisibleItemIndex,
            totalItemsCount = info.totalItemsCount,
            visibleKeys = info.visibleItemsInfo.map { it.key },
            visibleIndexes = info.visibleItemsInfo.map { it.index },
            waited = waited,
        )
        when (decision) {
            Walk.Found -> return true
            is Walk.Step -> {
                waited = 0
                state.scrollToItem(decision.index)
                steps++
            }
            Walk.Wait -> {
                waited++
                withFrameNanos { }
            }
            Walk.GiveUp -> return false
        }
    }
    return false
}
