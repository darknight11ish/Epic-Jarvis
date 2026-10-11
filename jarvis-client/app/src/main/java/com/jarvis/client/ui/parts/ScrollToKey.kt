package com.jarvis.client.ui.parts

import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.snapshotFlow
import kotlinx.coroutines.flow.first

/** Enough steps for any list in this app; a guard against looping, not a limit anyone meets. */
private const val MAX_STEPS = 60

/**
 * Brings the item whose `item(key = ...)` is [key] into view, once per new
 * [key], then calls [onDone] - whether or not it was found. Null does nothing.
 *
 * For "open <a place>" by voice or chat ([com.jarvis.client.ui.OpenPlace]) and
 * for Settings' own "Jump to:" list. SettingsScreen keeps a fixed index map
 * too, but only as the layout record OpenPlaceTest reads: a hidden menu
 * (2026-09-30) shifts every item below it, so both go by key.
 *
 * A lazy list only knows the keys of the items on screen, so this walks down a
 * screenful at a time until the key is laid out, then settles on it. An item
 * that is not there at all - a card this phone is not showing, or a menu the
 * owner has hidden - just ends at the bottom rather than settling on whatever
 * happens to sit at a remembered position.
 *
 * [onOpen] is for a screen whose items are inside something that can be shut
 * (Brain's headings, BrainScreen.kt and BrainSections.kt): an item inside a
 * shut heading is not in the list at all, so the walk would never find it. It
 * is called before the walk, with the key being looked for, and the caller
 * opens whatever holds that key. A screen with nothing to open leaves it out.
 *
 * [tick] is for a caller that can ask for the SAME key twice - Settings' jump
 * list, where tapping "Voice" again after scrolling away must scroll again.
 * The effect keys on [key] and [tick] together, so a new tick re-runs it while
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
        // An item already on screen needs nothing opened: if the walk can see
        // it, opening its holder would only move the list under the owner's
        // finger. This is the common case for a jump inside a heading that is
        // already open.
        val visible = state.layoutInfo.visibleItemsInfo.any { it.key == target }
        if (!visible) opened(target)
        scrollToKey(state, target)
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
 * moment anything was added to that list. The approval cards are keyed by
 * their own id, so the card's key finds it wherever it is.
 *
 * [fromTop] scrolls to the first item before walking. The walk only ever moves
 * down, which is right for a screen that opens at the top (Settings' jump
 * list, "open a place"), but Home can be opened by a notification with its
 * thread scrolled anywhere, so it asks for the search to start at the top.
 *
 * @return whether the key was found.
 */
suspend fun scrollToKey(state: LazyListState, key: String, fromTop: Boolean = false): Boolean {
    // Nothing is laid out on the very first frame; wait for it.
    snapshotFlow { state.layoutInfo.totalItemsCount }.first { it > 0 }
    if (fromTop) state.scrollToItem(0)
    var steps = 0
    while (steps < MAX_STEPS) {
        val info = state.layoutInfo
        val hit = info.visibleItemsInfo.firstOrNull { it.key == key }
        if (hit != null) {
            state.animateScrollToItem(hit.index)
            return true
        }
        val last = info.visibleItemsInfo.lastOrNull()?.index ?: break
        if (last >= info.totalItemsCount - 1) break
        // The last item on screen goes to the top. One taller than the
        // screen would never move that way, so step past it instead.
        state.scrollToItem(if (last > state.firstVisibleItemIndex) last else last + 1)
        steps++
    }
    return false
}
