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
 * [tick] is for a caller that can ask for the SAME key twice - Settings' jump
 * list, where tapping "Voice" again after scrolling away must scroll again.
 * The effect keys on [key] and [tick] together, so a new tick re-runs it while
 * [key] stays the plain `item(key = ...)` it looks up.
 */
@Composable
fun ScrollToKeyOnce(state: LazyListState, key: String?, tick: Int = 0, onDone: () -> Unit) {
    val done by rememberUpdatedState(onDone)
    LaunchedEffect(key, tick) {
        val target = key ?: return@LaunchedEffect
        // Nothing is laid out on the very first frame; wait for it.
        snapshotFlow { state.layoutInfo.totalItemsCount }.first { it > 0 }
        var steps = 0
        while (steps < MAX_STEPS) {
            val info = state.layoutInfo
            val hit = info.visibleItemsInfo.firstOrNull { it.key == target }
            if (hit != null) {
                state.animateScrollToItem(hit.index)
                break
            }
            val last = info.visibleItemsInfo.lastOrNull()?.index ?: break
            if (last >= info.totalItemsCount - 1) break
            // The last item on screen goes to the top. One taller than the
            // screen would never move that way, so step past it instead.
            state.scrollToItem(if (last > state.firstVisibleItemIndex) last else last + 1)
            steps++
        }
        done()
    }
}
