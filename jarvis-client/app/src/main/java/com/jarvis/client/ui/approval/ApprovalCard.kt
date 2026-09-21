package com.jarvis.client.ui.approval

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.PendingItem
import com.jarvis.client.ui.T
import com.jarvis.client.ui.parts.Affirm
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Refuse
import com.jarvis.client.ui.parts.TextInput
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
) {
    val scope = rememberCoroutineScope()
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
    // The seconds counter now lives in ExpiryCountdown below and ticks alone.
    var expired by remember(item.id, expiry) {
        mutableStateOf(expiry != null && System.currentTimeMillis() >= expiry)
    }
    LaunchedEffect(item.id, expiry) {
        if (expiry == null) return@LaunchedEffect
        val wait = expiry - System.currentTimeMillis()
        if (wait > 0) delay(wait)
        expired = true
    }
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

    Column(
        modifier = modifier
            .fillMaxWidth()
            .offset { IntOffset(offset.value.roundToInt(), 0) }
            .then(swipeModifier)
            .background(T.Plate, RoundedCornerShape(14.dp))
            .border(
                if (focused) 2.dp else 1.dp,
                if (focused) T.Pick else T.Warn.copy(alpha = 0.35f),
                RoundedCornerShape(14.dp),
            )
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = item.title,
                style = MaterialTheme.typography.titleMedium,
                color = T.Warn,
                modifier = Modifier.weight(1f),
            )
            ReachBadge(item)
        }

        if (item.summary.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(item.summary, style = MaterialTheme.typography.bodyMedium, color = T.Ink)
        }

        // The choices, when the desktop offers more than one plan. Each is a
        // complete plan of its own (§3a), shown whole: label, what it does,
        // and whether any step is heavy. Read-only on the phone until a
        // decide route can carry the chosen id - see `why` below.
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
                Text(
                    text = if (item.swipeable) "↔" else "✋",
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (item.swipeable) T.Ok else T.Dim,
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = when {
                        item.swipeable && canApprove ->
                            "Swipe right to approve, left to deny — ${item.risk.why}"
                        item.swipeable -> "Swipe left to deny — ${item.risk.why}"
                        else -> item.risk.why
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = T.Dim,
                    modifier = Modifier.weight(1f),
                )
            }
        }

        item.detail?.takeIf { it.isNotBlank() }?.let { detail ->
            Spacer(Modifier.height(8.dp))
            Text(
                text = if (showDetail) "Hide detail" else "Show detail",
                style = MaterialTheme.typography.labelMedium,
                color = T.Pick,
                modifier = Modifier
                    .clickable(role = Role.Button) { showDetail = !showDetail }
                    .minimumInteractiveComponentSize(),
            )
            AnimatedVisibility(showDetail) {
                Text(
                    text = detail,
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontFamily = FontFamily.Monospace,
                    ),
                    color = T.Dim,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }

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
        if (why != null) {
            Spacer(Modifier.height(10.dp))
            Text(why, style = MaterialTheme.typography.labelMedium, color = T.Bad)
        } else if (expiry != null) {
            Spacer(Modifier.height(10.dp))
            ExpiryCountdown(expiry)
        }

        // A note before the first decision - AUTONOMY-PROPOSALS.md §3b.
        // Hidden entirely once the card cannot be decided at all: typing a
        // note about a request that has already expired or gone stale has
        // nothing to attach itself to.
        if (canDecide) {
            Spacer(Modifier.height(10.dp))
            Text(
                text = if (showAmend) "Hide note" else "Add a note before deciding",
                style = MaterialTheme.typography.labelMedium,
                color = T.Pick,
                modifier = Modifier
                    .clickable(role = Role.Button) { showAmend = !showAmend }
                    .minimumInteractiveComponentSize(),
            )
            AnimatedVisibility(showAmend) {
                Column(Modifier.padding(top = 6.dp)) {
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
                            color = T.Dim,
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
        Spacer(Modifier.height(8.dp))
        Text(
            "Nothing runs until you decide.",
            style = MaterialTheme.typography.labelSmall,
            color = T.Dim,
        )
    }
}

/**
 * The seconds counter, and nothing else.
 *
 * Its own composable purely so the per-second tick invalidates one Text. Kept
 * in the card body, the same tick re-ran the title, the summary, the risk line
 * and both buttons once a second per card.
 */
@Composable
private fun ExpiryCountdown(expiryMs: Long) {
    var now by remember(expiryMs) { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(expiryMs) {
        while (System.currentTimeMillis() < expiryMs) {
            now = System.currentTimeMillis()
            delay(1_000)
        }
        now = System.currentTimeMillis()
    }
    val left = ((expiryMs - now) / 1000).coerceAtLeast(0)
    Text(
        "Expires in ${left / 60}m ${left % 60}s",
        style = MaterialTheme.typography.labelSmall,
        color = T.Dim,
    )
}

@Composable
private fun OptionsList(options: List<com.jarvis.client.net.ProposalOption>) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(T.Plate, RoundedCornerShape(10.dp))
            .border(1.dp, T.Line, RoundedCornerShape(10.dp))
            .padding(10.dp),
    ) {
        Text(
            if (options.size == 1) "The plan" else "${options.size} ways to do this",
            style = MaterialTheme.typography.labelSmall,
            color = T.Dim,
        )
        options.forEachIndexed { i, option ->
            Spacer(Modifier.height(if (i == 0) 6.dp else 8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    option.label.ifBlank { option.id.ifBlank { "Option ${i + 1}" } },
                    style = MaterialTheme.typography.titleSmall,
                    color = T.Ink,
                    modifier = Modifier.weight(1f),
                )
                if (option.weight.equals("heavy", ignoreCase = true)) {
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "HEAVY",
                        style = MaterialTheme.typography.labelSmall,
                        color = T.Warn,
                        modifier = Modifier
                            .background(T.Warn.copy(alpha = 0.12f), RoundedCornerShape(6.dp))
                            .padding(horizontal = 6.dp, vertical = 3.dp),
                    )
                }
            }
            if (option.summary.isNotBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(option.summary, style = MaterialTheme.typography.bodySmall, color = T.Dim)
            }
        }
    }
}

@Composable
private fun ReachBadge(item: PendingItem) {
    val (label, tint) = when {
        !item.risk.classified -> "UNCLASSIFIED" to T.Bad
        item.risk.reach == "outbound" -> "LEAVES THIS MACHINE" to T.Warn
        item.risk.reversible == "no" -> "NO UNDO" to T.Warn
        else -> "LOCAL" to T.Dim
    }
    Text(
        text = label,
        style = MaterialTheme.typography.labelSmall,
        color = tint,
        modifier = Modifier
            .background(tint.copy(alpha = 0.12f), RoundedCornerShape(6.dp))
            .padding(horizontal = 6.dp, vertical = 3.dp),
    )
}

@Composable
private fun RaisedChip(
    raised: com.jarvis.client.net.Raised,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(T.Bad.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
            .border(1.dp, T.Bad.copy(alpha = 0.4f), RoundedCornerShape(10.dp))
            .padding(10.dp),
    ) {
        Text(
            text = raised.text.ifBlank { "Tier raised — this text tried to rush you" },
            style = MaterialTheme.typography.labelMedium,
            color = T.Bad,
        )
        if (raised.quote.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = "“${raised.quote}”",
                style = MaterialTheme.typography.bodyMedium,
                color = T.Ink,
            )
        }
        if (raised.source.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            // Named, never quoted.
            Text(
                text = "from ${raised.source}",
                style = MaterialTheme.typography.labelSmall,
                color = T.Dim,
            )
        }
        // No repeat of the count here. The scanner folds it into `text` already
        // — the API's own example is "Tier raised — this text tried to rush you
        // (4th time today)" — so rendering it again said the same thing twice in
        // two different wordings, which reads like two separate warnings.
        if (raised.context.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = if (expanded) "Hide surrounding text" else "Show surrounding text",
                style = MaterialTheme.typography.labelSmall,
                color = T.Pick,
                modifier = Modifier
                    .clickable(role = Role.Button, onClick = onToggle)
                    .minimumInteractiveComponentSize(),
            )
            AnimatedVisibility(expanded) {
                // Page or document text. Never shown without the user asking:
                // it is the attacker's medium, and a card that unfolds into a
                // wall of it becomes the thing nobody reads.
                Text(
                    text = raised.context,
                    style = MaterialTheme.typography.bodySmall,
                    color = T.Dim,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
    }
}

