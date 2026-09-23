package com.jarvis.client.ui.approval

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.PendingItem
import com.jarvis.client.ui.parts.Affirm
import com.jarvis.client.ui.parts.Meter
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Refuse
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.JarvisType
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/**
 * One pending approval.
 *
 * The card's job is to make the cost of answering wrongly visible before the
 * answer is given. Two fields do most of that work, and both come from the
 * server: `risk.why` says what happens if this goes the wrong way, and `raised`
 * says that outside text tried to hurry the reader into not asking.
 */
@Composable
fun ApprovalCard(
    item: PendingItem,
    /** Null when a decision can be taken; the reason when it cannot. */
    blocker: String?,
    /**
     * This is the card a notification or digest row asked to open.
     *
     * Outlined only. Nothing about the decision itself changes - rule 4 says
     * nothing is ever approved without a deliberate answer, and being pointed
     * at is not an answer.
     */
    focused: Boolean = false,
    onApprove: () -> Unit,
    onDeny: () -> Unit,
    /**
     * A note typed before the first decision - AUTONOMY-PROPOSALS.md §3b.
     * NOT a decision and approves nothing; the expected result is the
     * desktop replacing this card with a fresh set of options that accounts
     * for it, delivered the normal way through the next `/api/pending`
     * refresh. DRAFT: the route this calls has no confirmed backend yet
     * (`jarvis_gate.py`/`jarvis_hud.py` are not in this repo) - a failure
     * here is expected until it exists, and is shown through the same
     * shared notice every other read on this screen uses, never hidden.
     * Suspend, so this card can hold its own "sending" state without a new
     * field threaded through from outside.
     */
    onAmend: suspend (note: String) -> Unit = {},
    modifier: Modifier = Modifier,
    /**
     * The "Nothing runs until you decide." line under the buttons.
     *
     * On by default, so every existing caller is unchanged. The 09-23 audit
     * (visual-7) points out it repeats on every card; a list that says it
     * once, above the cards, can pass false here. Wording only - it gates
     * nothing, and turning it off changes no decision path.
     */
    showFooter: Boolean = true,
) {
    val scope = rememberCoroutineScope()
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val cardShape = LocalRadii.current.cardShape
    val offset = remember(item.id) { Animatable(0f) }
    var showDetail by rememberSaveable(item.id) { mutableStateOf(false) }
    var showContext by rememberSaveable(item.id) { mutableStateOf(false) }
    var showAmend by rememberSaveable(item.id) { mutableStateOf(false) }
    var amendText by rememberSaveable(item.id) { mutableStateOf("") }
    var amendSending by remember(item.id) { mutableStateOf(false) }

    val expiry = item.expiresAtMs
    // One state change, at the deadline - not one a second.
    //
    // `now` used to tick here in the card body and be read here, so the title,
    // the summary, the risk line and both buttons re-ran every second, for
    // every card on screen carrying a deadline, on the thread already drawing
    // the reactor. Nothing in the body wants the clock; it wants the single
    // fact of whether the deadline has passed, and that changes exactly once.
    // The seconds counter now lives in rememberSecondsLeft below, and only
    // ExpiryBar and ExpiryCountdown read it.
    var expired by remember(item.id, expiry) {
        mutableStateOf(expiry != null && System.currentTimeMillis() >= expiry)
    }
    LaunchedEffect(item.id, expiry) {
        if (expiry == null) return@LaunchedEffect
        val wait = expiry - System.currentTimeMillis()
        if (wait > 0) delay(wait)
        expired = true
    }
    // Seconds to the deadline, as a State the card body never reads. Only the
    // two small readers below (the bar at the top, the "00:43" readout at the
    // bottom) take `.value`, so the per-second tick recomposes those two and
    // nothing else - the same split ExpiryCountdown made, now shared by both.
    val secondsLeft: State<Long>? = if (expiry != null) rememberSecondsLeft(expiry) else null
    val canDecide = blocker == null && !expired
    // A proposal with several options needs one named alongside the approval,
    // and the phone's approve route carries none yet (AUTONOMY-PROPOSALS §3b's
    // decide route is not built on any backend). So approving is refused here
    // and the card says where to choose. Denying needs no option and stays.
    val canApprove = canDecide && !item.needsChoice

    // A decision on this screen is felt, not just seen - a swipe is answered
    // with no visual confirmation until the card has already animated off
    // screen, and the tap targets are exactly where a thumb already is.
    // Captured as plain values here (a @Composable read) so the closures
    // below - one of them a suspend lambda inside `pointerInput`, which is
    // not a composable context - can call them without one.
    val haptics = LocalHapticFeedback.current
    val approve: () -> Unit = {
        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
        onApprove()
    }
    val deny: () -> Unit = {
        haptics.performHapticFeedback(HapticFeedbackType.Reject)
        onDeny()
    }

    // Swipe, gated on `canDecide` rather than `canApprove`.
    //
    // A swipe is a gesture people make without reading. That is fine for
    // "switch to the other model", where rollback is one tap and nothing left
    // the machine. It is not fine for sending an email. The test is a single
    // server-computed field and nothing else - not re-derived here, not cached
    // against an id, and refused outright for anything carrying `raised`.
    //
    // Gating the whole gesture on `canApprove` used to also take deny-by-swipe
    // down with it: a `needsChoice` item sets `canApprove = false` (below), so
    // `item.swipeable && canApprove` was false for it, and BOTH directions
    // went dead - while the help text two blocks down, gated only on
    // `item.swipeable`, kept promising "Swipe right to approve, left to
    // deny" underneath a card that could not feel either. Deny needs no
    // option and stays available on a `needsChoice` item everywhere else on
    // this screen (the Deny button's own `enabled = canDecide`, not
    // `canApprove`); the swipe gesture is the one place that rule was not
    // actually wired through. So the gesture detector is live whenever a
    // decision of EITHER kind could be sent, and only the completed drag
    // decides which direction is honoured.
    val swipeThresholdPx = with(LocalDensity.current) { 96.dp.toPx() }
    val swipeModifier = if (canDecide && item.swipeable) {
        Modifier.pointerInput(item.id) {
            detectHorizontalDragGestures(
                onDragEnd = {
                    scope.launch {
                        // The decision is sent first and the card springs
                        // back into place; it leaves the screen only when the
                        // desktop's answer removes it from `pending`.
                        //
                        // It used to animate fully off screen and THEN send
                        // the decision, so a refusal - expired, unreachable,
                        // already handled on the desktop - left an invisible
                        // card whose item was still waiting. Nothing on this
                        // surface may show "gone" before the desktop says so;
                        // that is the same rule the notification Deny follows.
                        // The haptic in approve()/deny() is the acknowledgement,
                        // and the buttons grey out while the decision is in
                        // flight, so the spring-back does not read as "ignored".
                        when {
                            // A right-swipe past the threshold on a needsChoice
                            // item springs back and does nothing - the same
                            // silent refusal a disabled Approve button already
                            // gives a tap, not a new behaviour invented here.
                            offset.value > swipeThresholdPx && canApprove -> {
                                approve()
                                offset.animateTo(0f)
                            }
                            offset.value < -swipeThresholdPx -> {
                                deny()
                                offset.animateTo(0f)
                            }
                            else -> offset.animateTo(0f)
                        }
                    }
                },
                onDragCancel = { scope.launch { offset.animateTo(0f) } },
            ) { change, drag ->
                change.consume()
                scope.launch { offset.snapTo(offset.value + drag) }
            }
        }
    } else {
        Modifier
    }

    // Worked out here, above the card, because it decides two things now:
    // the red line near the buttons (as before) and whether the deadline
    // readout is shown in its place.
    val why = when {
        expired -> "Expired — ask the desktop to raise this again."
        blocker != null -> blocker
        // Used to say "choose one on the desktop" - wrong, per
        // docs/JARVIS-API.md §8: the desktop's own option buttons send
        // the same request no matter which one is clicked, because
        // `decide_approval` drops `option_id` before it reaches the
        // server. Neither client can send a choice today.
        item.needsChoice ->
            "This proposal offers ${item.options.size} options, and no Jarvis client " +
                "can pick one yet. Deny still works here."
        else -> null
    }

    // The shared card shape and tokens, not a literal 14dp and the old `T`
    // shim. `clip` before `background` so the fill follows the shape exactly;
    // the border is drawn on the same shape.
    Column(
        modifier = modifier
            .fillMaxWidth()
            .offset { IntOffset(offset.value.roundToInt(), 0) }
            .then(swipeModifier)
            .clip(cardShape)
            .background(chrome.surface1)
            .border(
                if (focused) 2.dp else 1.dp,
                if (focused) accent else chrome.warnInk.copy(alpha = 0.35f),
                cardShape,
            )
            .padding(14.dp),
    ) {
        // The deadline as a thin bar that runs down, once a second, at the
        // data's rate - the audit's "a smooth decrease, not a luminance
        // flash". It sits first, along the card's top, so how long is left
        // is the first thing the eye meets, before the title. Shown until
        // the moment the deadline passes, blocked or not: the clock keeps
        // running while the stream is stale, and saying so is honest.
        if (expiry != null && secondsLeft != null && !expired) {
            ExpiryBar(expiry, secondsLeft)
            Spacer(Modifier.height(10.dp))
        }

        // The title gets the full width, and the reach badge sits on its own
        // line under it - always, not only at large text sizes.
        //
        // They used to share one Row, the title weighted and the badge
        // measured first. At 200% text, "LEAVES THIS MACHINE" alone is about
        // 250dp of a ~350dp card, which left the title a ~100dp column and
        // one word per line (a11y-11). A line of its own costs one row of
        // height at 100% and fixes every size above it.
        Text(
            text = item.title,
            style = MaterialTheme.typography.titleMedium,
            color = chrome.warnInk,
        )
        Spacer(Modifier.height(6.dp))
        ReachBadge(item)

        if (item.summary.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(item.summary, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        }

        // The choices, when the desktop offers more than one plan. Each is a
        // complete plan of its own (§3a), shown whole: label, what it does,
        // and whether any step is heavy. Read-only on the phone until a
        // decide route can carry the chosen id - see `why` above.
        if (item.options.isNotEmpty()) {
            Spacer(Modifier.height(10.dp))
            OptionsList(item.options)
        }

        // The rush warning, if outside text tried to hurry the reader. The quote
        // is the attacker's own words and showing them is the entire point; the
        // surrounding context is page text, so it stays behind a tap.
        item.raised?.let { raised ->
            Spacer(Modifier.height(10.dp))
            RaisedChip(
                raised = raised,
                expanded = showContext,
                onToggle = { showContext = !showContext },
            )
        }

        // risk.why goes on the card whether or not a swipe is allowed. A card
        // that explains why it will not take a gesture teaches the rule; one
        // that silently refuses reads as a bug.
        //
        // `item.swipeable` alone used to decide the wording, which is what
        // let this card promise "Swipe right to approve" over a needsChoice
        // item, where the gesture handler above will spring back and do
        // nothing on exactly that swipe - the options list rendered above
        // already explains why (§3b: no route yet to say which plan was
        // meant), so this line drops the approve half rather than repeat it.
        // Left-to-deny is never dropped: it works whenever `item.swipeable`
        // does, `needsChoice` or not.
        if (item.risk.why.isNotBlank()) {
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                // Drawn marks, not "↔" and "✋". The hand was a full-colour
                // system emoji - the one bitmap-looking glyph in a UI that is
                // otherwise drawn and monochrome, and it looked different on
                // every phone maker's emoji set. Decorative: the sentence
                // beside it says the same thing in words.
                if (item.swipeable) {
                    SwipeGlyph(chrome.okMark)
                } else {
                    TapGlyph(chrome.textMid)
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    text = when {
                        item.swipeable && canApprove ->
                            "Swipe right to approve, left to deny — ${item.risk.why}"
                        item.swipeable -> "Swipe left to deny — ${item.risk.why}"
                        else -> item.risk.why
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                    modifier = Modifier.weight(1f),
                )
            }
        }

        // The show/hide toggles below are the shared `Quiet` part, not
        // `clickable` on a Text. `clickable` brought Material's ripple - the
        // last three in the app's own UI were all on this card - and `Quiet`
        // brings the same 48dp target and spring-press every other text
        // action has. The -10dp offset cancels Quiet's own inner padding, so
        // the words still line up with the left edge of the text above.
        item.detail?.takeIf { it.isNotBlank() }?.let { detail ->
            Spacer(Modifier.height(4.dp))
            Quiet(
                text = if (showDetail) "Hide detail" else "Show detail",
                modifier = Modifier.offset(x = (-10).dp),
                onClick = { showDetail = !showDetail },
            )
            AnimatedVisibility(showDetail) {
                Text(
                    text = detail,
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontFamily = JarvisType.mono,
                    ),
                    color = chrome.textMid,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
        }

        if (why != null) {
            Spacer(Modifier.height(10.dp))
            // Announced, politely, when it appears or changes. This is the
            // line that says "you cannot act right now" - a stale stream, a
            // decision already in flight, a deadline gone - and a screen
            // reader user otherwise finds out only by trying a button that
            // no longer answers. Never put on the countdown: that changes
            // every second and would never stop talking.
            Text(
                why,
                style = MaterialTheme.typography.labelMedium,
                color = chrome.badInk,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        } else if (secondsLeft != null) {
            Spacer(Modifier.height(10.dp))
            ExpiryCountdown(secondsLeft)
        }

        // A note before the first decision - AUTONOMY-PROPOSALS.md §3b.
        // Hidden entirely once the card cannot be decided at all: typing a
        // note about a request that has already expired or gone stale has
        // nothing to attach itself to.
        if (canDecide) {
            Spacer(Modifier.height(4.dp))
            Quiet(
                text = if (showAmend) "Hide note" else "Add a note before deciding",
                modifier = Modifier.offset(x = (-10).dp),
                onClick = { showAmend = !showAmend },
            )
            AnimatedVisibility(showAmend) {
                Column(Modifier.padding(top = 2.dp)) {
                    TextInput(
                        value = amendText,
                        onValueChange = { amendText = it },
                        placeholder = "Wait, only do X — or add Y too…",
                    )
                    Spacer(Modifier.height(6.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Quiet(
                            if (amendSending) "Sending…" else "Send note",
                            enabled = !amendSending && amendText.isNotBlank(),
                            onClick = {
                                val note = amendText
                                amendSending = true
                                scope.launch {
                                    onAmend(note)
                                    amendSending = false
                                    amendText = ""
                                    showAmend = false
                                }
                            },
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "Sends the note only - approves nothing. The desktop should " +
                                "come back with a new plan that accounts for it.",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        // Filled against outlined, not green against red.
        //
        // These two were identical rounded rectangles distinguished by colour
        // alone, and this is the one pair in the app where colour cannot carry
        // it: verdant-4 and rose-4 are 67.7 ΔE apart normally and 8.2 apart to
        // a deuteranope, where they simulate to nearly the same beige —
        // #cbc4ac against #b9ae83, a difference of 1.2 on an axis that was
        // 99.7 wide. Shape survives that, and survives a photograph, a still
        // frame and peripheral vision with it.
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Affirm("Approve", enabled = canApprove, onClick = approve)
            Refuse("Deny", enabled = canDecide, onClick = deny)
        }
        if (showFooter) {
            Spacer(Modifier.height(8.dp))
            Text(
                "Nothing runs until you decide.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
    }
}

/**
 * Whole seconds until [expiryMs], rounded UP.
 *
 * Up, so the readout says 00:01 for the last partial second and reaches 00:00
 * only at the moment the card flips to "Expired". Rounding down showed 00:00
 * for up to a second while the buttons still worked, which reads as a clock
 * that is wrong.
 */
private fun secondsUntil(expiryMs: Long, nowMs: Long = System.currentTimeMillis()): Long =
    ((expiryMs - nowMs + 999L) / 1000L).coerceAtLeast(0L)

/**
 * One clock per card, ticking on the second boundary.
 *
 * Returned as a [State] rather than a value so that only the composables that
 * read `.value` recompose on each tick. The card body only passes it along.
 * Sleeps to the next boundary rather than a flat 1000ms, so "00:43" changes
 * when the second actually turns, not up to a second late.
 */
@Composable
private fun rememberSecondsLeft(expiryMs: Long): State<Long> {
    val left = remember(expiryMs) { mutableLongStateOf(secondsUntil(expiryMs)) }
    LaunchedEffect(expiryMs) {
        while (true) {
            val now = System.currentTimeMillis()
            left.longValue = secondsUntil(expiryMs, now)
            if (now >= expiryMs) break
            val toBoundary = (expiryMs - now) % 1000L
            delay(if (toBoundary == 0L) 1000L else toBoundary)
        }
    }
    return left
}

/**
 * The thin bar along the card's top that runs down to the deadline.
 *
 * Full when this phone first showed the card, empty at the deadline. The API
 * sends only when an approval expires, not when it was raised, so "full" can
 * only mean "when you first saw it" - a card opened with 40 seconds left
 * starts full and empties in 40 seconds, which is the part that matters to
 * the person reading it. Saveable, so a rotation does not refill it.
 *
 * It uses the shared [Meter], which glides between values over the motion
 * token's duration: one smooth step down per second, never a flash. With
 * reduced motion on, that glide is zero and it steps.
 */
@Composable
private fun ExpiryBar(expiryMs: Long, secondsLeft: State<Long>) {
    val chrome = LocalChrome.current
    // Keyed on the deadline: if the desktop moves it, the bar starts over
    // from the new one instead of measuring against the old total.
    val total = rememberSaveable(expiryMs) { secondsLeft.value.coerceAtLeast(1L) }
    val fraction = secondsLeft.value.toFloat() / total.toFloat()
    Meter(
        fraction = fraction,
        color = chrome.warnMark,
        track = chrome.hairline,
        height = 2,
        // The words are in the readout at the bottom of the card; a bar is
        // read out as nothing useful, so it says nothing.
        modifier = Modifier.clearAndSetSemantics { },
    )
}

/**
 * The deadline readout: "EXPIRES IN 00:43", the number in the machine face.
 *
 * Its own composable purely so the per-second tick invalidates this row and
 * nothing else. Kept in the card body, the same tick re-ran the title, the
 * summary, the risk line and both buttons once a second per card.
 *
 * "00:43" rather than the old "Expires in 0m 43s": a clock reads at a glance,
 * and the fixed-width digits do not shuffle the line sideways every second.
 * Past ten minutes the seconds are noise, so it says "12 MIN".
 *
 * A screen reader hears the sentence, not the digits - "zero zero colon forty
 * three" is not an answer. There is deliberately no live region here: it
 * changes every second and would never stop talking.
 */
@Composable
private fun ExpiryCountdown(secondsLeft: State<Long>) {
    val chrome = LocalChrome.current
    val left = secondsLeft.value
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.clearAndSetSemantics { contentDescription = spokenCountdown(left) },
    ) {
        Text(
            "EXPIRES IN",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            clockCountdown(left),
            style = JarvisType.machine,
            color = chrome.textHi,
        )
    }
}

/**
 * "00:43" under ten minutes, "12 MIN" under an hour, "2 H 05 MIN" beyond.
 *
 * Padded by hand rather than with `String.format`, which uses the phone's
 * locale and would print Arabic-Indic or Devanagari digits on some phones -
 * inside a monospace readout that is meant to be read like an instrument.
 */
private fun clockCountdown(sec: Long): String = when {
    sec >= 3600L -> "${sec / 3600L} H ${((sec % 3600L) / 60L).toString().padStart(2, '0')} MIN"
    sec >= 600L -> "${sec / 60L} MIN"
    else -> "${(sec / 60L).toString().padStart(2, '0')}:${(sec % 60L).toString().padStart(2, '0')}"
}

private fun spokenCountdown(sec: Long): String {
    val h = sec / 3600L
    val m = (sec % 3600L) / 60L
    val s = sec % 60L
    fun unit(n: Long, one: String) = if (n == 1L) "1 $one" else "$n ${one}s"
    return when {
        h > 0L -> "Expires in ${unit(h, "hour")} ${unit(m, "minute")}"
        sec >= 600L -> "Expires in ${unit(m, "minute")}"
        m > 0L -> "Expires in ${unit(m, "minute")} ${unit(s, "second")}"
        else -> "Expires in ${unit(s, "second")}"
    }
}

/**
 * "Swipe works on this one": a short horizontal stroke with a head at each
 * end - the drawn version of the "↔" it replaces.
 *
 * Drawn in a 16dp box with round caps, the same stroke weight family as the
 * nav icons (NavIcons.kt), so it sits in the text line like they do.
 */
@Composable
private fun SwipeGlyph(tint: Color) {
    Box(
        Modifier
            .size(16.dp)
            .drawBehind {
                val w = 1.5.dp.toPx()
                val y = size.height / 2f
                val l = size.width * 0.12f
                val r = size.width * 0.88f
                val head = size.width * 0.22f
                drawLine(tint, Offset(l, y), Offset(r, y), w, cap = StrokeCap.Round)
                drawLine(tint, Offset(l, y), Offset(l + head, y - head), w, cap = StrokeCap.Round)
                drawLine(tint, Offset(l, y), Offset(l + head, y + head), w, cap = StrokeCap.Round)
                drawLine(tint, Offset(r, y), Offset(r - head, y - head), w, cap = StrokeCap.Round)
                drawLine(tint, Offset(r, y), Offset(r - head, y + head), w, cap = StrokeCap.Round)
            },
    )
}

/**
 * "Tap a button for this one": a ring with a pressed point at its centre -
 * a fingertip on glass, not a hand.
 *
 * Replaces "✋", which was the one full-colour system emoji on the card and
 * drew differently on every phone maker's emoji font. The meaning it carried
 * is kept: this card will not take a gesture, it wants a deliberate tap.
 */
@Composable
private fun TapGlyph(tint: Color) {
    Box(
        Modifier
            .size(16.dp)
            .drawBehind {
                val w = 1.5.dp.toPx()
                drawCircle(
                    color = tint,
                    radius = size.minDimension / 2f - w,
                    style = Stroke(width = w),
                )
                drawCircle(color = tint, radius = size.minDimension * 0.14f)
            },
    )
}

@Composable
private fun OptionsList(options: List<com.jarvis.client.net.ProposalOption>) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.controlShape
    Column(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(chrome.surface1)
            .border(1.dp, chrome.hairline, shape)
            .padding(10.dp),
    ) {
        Text(
            if (options.size == 1) "The plan" else "${options.size} ways to do this",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
        )
        options.forEachIndexed { i, option ->
            Spacer(Modifier.height(if (i == 0) 6.dp else 8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    option.label.ifBlank { option.id.ifBlank { "Option ${i + 1}" } },
                    style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
                if (option.weight.equals("heavy", ignoreCase = true)) {
                    Spacer(Modifier.width(8.dp))
                    // The shared label shape - fully round means "a fact,
                    // not a button" - instead of a hand-set 6dp corner.
                    Pill("HEAVY", color = chrome.warnInk)
                }
            }
            if (option.summary.isNotBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(option.summary, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
    }
}

/**
 * Where this action reaches, as the shared [Pill]: fully round, which in this
 * app means "a label, not a control". It was a 6dp-cornered box of its own,
 * which is the shape the app's buttons use.
 */
@Composable
private fun ReachBadge(item: PendingItem) {
    val chrome = LocalChrome.current
    val (label, tint) = when {
        !item.risk.classified -> "UNCLASSIFIED" to chrome.badInk
        item.risk.reach == "outbound" -> "LEAVES THIS MACHINE" to chrome.warnInk
        item.risk.reversible == "no" -> "NO UNDO" to chrome.warnInk
        else -> "LOCAL" to chrome.textMid
    }
    Pill(label, color = tint)
}

@Composable
private fun RaisedChip(
    raised: com.jarvis.client.net.Raised,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.controlShape
    Column(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(chrome.badInk.copy(alpha = 0.10f))
            .border(1.dp, chrome.badInk.copy(alpha = 0.4f), shape)
            .padding(10.dp),
    ) {
        Text(
            text = raised.text.ifBlank { "Tier raised — this text tried to rush you" },
            style = MaterialTheme.typography.labelMedium,
            color = chrome.badInk,
        )
        if (raised.quote.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = "“${raised.quote}”",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi,
            )
        }
        if (raised.source.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            // Named, never quoted.
            Text(
                text = "from ${raised.source}",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
        // No repeat of the count here. The scanner folds it into `text` already
        // — the API's own example is "Tier raised — this text tried to rush you
        // (4th time today)" — so rendering it again said the same thing twice in
        // two different wordings, which reads like two separate warnings.
        if (raised.context.isNotBlank()) {
            Spacer(Modifier.height(2.dp))
            // The shared Quiet part, not `clickable` on a Text - see the
            // matching note in ApprovalCard. The -10dp cancels Quiet's own
            // inner padding so the words line up with the text above.
            Quiet(
                text = if (expanded) "Hide surrounding text" else "Show surrounding text",
                modifier = Modifier.offset(x = (-10).dp),
                onClick = onToggle,
            )
            AnimatedVisibility(expanded) {
                // Page or document text. Never shown without the user asking:
                // it is the attacker's medium, and a card that unfolds into a
                // wall of it becomes the thing nobody reads.
                Text(
                    text = raised.context,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
        }
    }
}
