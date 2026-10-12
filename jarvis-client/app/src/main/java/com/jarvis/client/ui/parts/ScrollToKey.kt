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
 * What a jump lands on, in the order it travels: the HOLDER of the item first
 * whenever the screen knows of one, then the item itself. No holder, just the
 * item.
 *
 * Pure and separate from [ScrollToKeyOnce] so the rule can be driven by a JVM
 * test - the rule the device found missing on 2026-10-11 (build 0.2.1232, the
 * fourth variant of this family): a jump treated "the item's heading is open"
 * as the whole job, so an already-open heading meant the item inside it was
 * never reached, and the screen stayed on whatever was at the end of the list.
 *
 * Landing on the holder first is also what makes the walk that follows safe:
 * the rows above the item stop being added, so the walk runs against a list
 * that no longer moves under it.
 */
internal fun landingOrder(target: String, holder: String?): List<String> =
    if (holder == null || holder == target) listOf(target) else listOf(holder, target)

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
 *
 * [holderKey] is the fallback for an item the screen is NOT drawing at all - a
 * plate behind a menu the owner has hidden, or the other half of a pair. Those
 * never reach the list, so the item's own walk ends at the bottom; the heading
 * that holds it does not, so the jump lands there instead of somewhere the
 * owner did not ask for. It is tried only AFTER the item has really been
 * searched for twice, so a jump that can reach its item always does.
 */
@Composable
fun ScrollToKeyOnce(
    state: LazyListState,
    key: String?,
    tick: Int = 0,
    /**
     * The `item(key = ...)` of whatever HOLDS [key] - a heading that is drawn
     * whether or not the item inside it is. Null when nothing holds it.
     *
     * It is the jump's fallback, and it exists because a key being absent from
     * the list is not always a timing problem: a plate whose menu the owner has
     * hidden, or one drawn only in the other of a pair, is NEVER laid out, so a
     * walk for it runs to the bottom of the list and stops there. Landing on
     * the heading instead is the difference between "the screen has taken me to
     * the thing I asked for" and "the screen has taken me somewhere I did not
     * ask for" (the Galaxy button on the device, 2026-10-11).
     */
    holderKey: (String) -> String? = { null },
    onOpen: (String) -> Unit = {},
    /**
     * Called with the key the walk was looking for, at the moment it finishes -
     * whatever it found. Null-safe reporting, and it exists because the defect
     * of 2026-10-11 was a walk that reported success while the item was never
     * on screen: the caller logs what really happened instead of what was
     * intended, and "the heading was open" stops being mistaken for "the item
     * is on screen".
     */
    onVisited: (String) -> Unit = {},
    onDone: () -> Unit,
) {
    val done by rememberUpdatedState(onDone)
    val opened by rememberUpdatedState(onOpen)
    val visited by rememberUpdatedState(onVisited)
    LaunchedEffect(key, tick) {
        val target = key ?: return@LaunchedEffect
        val report: () -> Unit = {
            runCatching { visited(target) }
            done()
        }
        // The heading that holds the item, when the screen knows of one - the
        // one item a jump can still land on when the item itself is not drawn
        // (a menu the owner has hidden, a plate drawn only in the other of a
        // pair). The screen passes it in; see [ScrollToKeyOnce]'s note.
        val holder = holderKey(target)
        // The rule itself lives in [landingOrder], so a JVM test holds it. This
        // reads it rather than restating it.
        val stops = landingOrder(target, holder)
        val anchor = stops.firstOrNull()?.takeIf { it != target }

        suspend fun to(index: Int) {
            runCatching { state.scrollToItem(index) }
        }

        suspend fun onScreen(): Int? =
            state.layoutInfo.visibleItemsInfo.firstOrNull { it.key == target }?.index

        /**
         * Brings the HOLDER into view and reports whether it got there.
         *
         * `scrollToKey`, NOT a look-up among the rows already laid out: the
         * heading is usually not in the viewport when a jump starts - the owner
         * has just arrived from Home or from Find, and the list is wherever it
         * was left - and a look-up returns null there, so the anchor silently
         * did nothing at all. That is the case the device's log shows
         * (`initiallyOpen=money-time`, the walk's viewport on
         * `[brain-heading:learning..brain-plate:tail]`, the BOTTOM of the list,
         * which is where a walk ends up when nothing brought it anywhere).
         *
         * `fromTop = true` because the walk only ever moves down: starting from
         * wherever the last attempt stopped is the failure being fixed.
         */
        suspend fun anchorNow(): Boolean {
            val a = anchor ?: return false
            var tries = 0
            while (tries < WAIT_FRAMES && state.layoutInfo.visibleItemsInfo.isEmpty()) {
                tries++
                withFrameNanos { }
            }
            if (!scrollToKey(state, a, fromTop = true)) return false
            // One frame for the plates that were not composed above it yet.
            withFrameNanos { }
            return true
        }

        // ANCHOR FIRST, when the jump knows what holds the item (2026-10-11).
        //
        // A jump used to rely on the finished state of the list: it looked at
        // the rows laid out on the frame it first ran, and if the item was not
        // among them it walked down a screenful at a time. That is safe only
        // while the list is FINISHED. It is not: a section that was already
        // open when the owner arrived has its plates composed as the walk runs,
        // and every row composed ABOVE the item moves it further down - so the
        // index the walk aimed at was the one from BEFORE those rows existed.
        // The device showed exactly that (`Coming up` by Find, 2026-10-11: the
        // log said `initiallyOpen=money-time`, and the screen stayed on the
        // attention card at the end of the list).
        //
        // Bringing the HOLDER to the top first removes the whole class: the
        // list above the item stops growing, so the walk that follows runs
        // against a list that no longer moves under it. It is also the honest
        // place to land when the item turns out not to be drawn at all.
        var anchored = false
        if (anchor != null) {
            anchored = anchorNow()
        }
        var waited = 0
        if (!anchored) {
            // Nothing to anchor to, or its heading is not in the list: wait for
            // a real row, then open whatever holds the item.
            while (waited < WAIT_FRAMES && state.layoutInfo.visibleItemsInfo.isEmpty()) {
                waited++
                withFrameNanos { }
            }
            opened(target)
            withFrameNanos { }
        }

        // The item itself: on screen, or a screenful at a time; then opened
        // again and walked once more, because opening is a state write whose
        // rows land on the NEXT composition.
        var openAsked = anchored
        var retried = false
        waited = 0
        while (waited < WAIT_FRAMES) {
            val info = state.layoutInfo
            if (info.visibleItemsInfo.isEmpty()) {
                waited++
                withFrameNanos { }
                continue
            }
            if (info.visibleItemsInfo.any { it.key == target }) {
                state.animateScrollToItem(info.visibleItemsInfo.first { it.key == target }.index)
                // AND THEN MEAN IT: the walk above can be right about the index
                // and still have the list move before the scroll is felt. If the
                // animation did not put the item on screen, go there directly.
                if (onScreen() == null) to(info.visibleItemsInfo.first { it.key == target }.index)
                report()
                return@LaunchedEffect
            }
            if (!openAsked) {
                openAsked = true
                opened(target)
                withFrameNanos { }
                continue
            }
            if (scrollToKey(state, target, fromTop = false)) {
                val hit = onScreen()
                if (hit != null) state.animateScrollToItem(hit)
                if (onScreen() == null && hit != null) to(hit)
                report()
                return@LaunchedEffect
            }
            if (anchor != null && !retried) {
                // One more go, and THE ANCHOR IS RE-TAKEN first. The old retry
                // re-opened the holder and walked from wherever the failed walk
                // stopped - and a failed walk has run to the BOTTOM, so the
                // second attempt started at the end of the list and found
                // nothing either. Walking down from the holder is what makes the
                // second attempt different from the first.
                retried = true
                openAsked = false
                val reAnchored = anchorNow()
                if (reAnchored) anchored = true
                withFrameNanos { }
                continue
            }
            break
        }
        // The item is not drawn at all, and the holder is known: end on the
        // holder rather than on the bottom of a failed search.
        anchorNow()
        report()
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


