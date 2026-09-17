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
import com.jarvis.client.ui.parts.Refuse
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
    onApprove: () -> Unit,
    onDeny: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    val offset = remember(item.id) { Animatable(0f) }
    var showDetail by rememberSaveable(item.id) { mutableStateOf(false) }
    var showContext by rememberSaveable(item.id) { mutableStateOf(false) }

    val expiry = item.expiresAtMs
    var now by remember(item.id) { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(item.id, expiry) {
        if (expiry == null) return@LaunchedEffect
        while (System.currentTimeMillis() < expiry) {
            now = System.currentTimeMillis()
            delay(1_000)
        }
        now = System.currentTimeMillis()
    }
    val expired = expiry != null && now >= expiry
    val canDecide = blocker == null && !expired

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

    // Swipe-to-approve, for exactly one class of item.
    //
    // A swipe is a gesture people make without reading. That is fine for
    // "switch to the other model", where rollback is one tap and nothing left
    // the machine. It is not fine for sending an email. The test is a single
    // server-computed field and nothing else - not re-derived here, not cached
    // against an id, and refused outright for anything carrying `raised`.
    val swipeThresholdPx = with(LocalDensity.current) { 96.dp.toPx() }
    val swipeModifier = if (canDecide && item.swipeable) {
        Modifier.pointerInput(item.id) {
            detectHorizontalDragGestures(
                onDragEnd = {
                    scope.launch {
                        when {
                            offset.value > swipeThresholdPx -> {
                                offset.animateTo(size.width.toFloat())
                                approve()
                            }
                            offset.value < -swipeThresholdPx -> {
                                offset.animateTo(-size.width.toFloat())
                                deny()
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
            .border(1.dp, T.Warn.copy(alpha = 0.35f), RoundedCornerShape(14.dp))
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
                    text = if (item.swipeable) {
                        "Swipe right to approve, left to deny — ${item.risk.why}"
                    } else {
                        item.risk.why
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
            else -> null
        }
        if (why != null) {
            Spacer(Modifier.height(10.dp))
            Text(why, style = MaterialTheme.typography.labelMedium, color = T.Bad)
        } else if (expiry != null) {
            Spacer(Modifier.height(10.dp))
            val left = ((expiry - now) / 1000).coerceAtLeast(0)
            Text(
                "Expires in ${left / 60}m ${left % 60}s",
                style = MaterialTheme.typography.labelSmall,
                color = T.Dim,
            )
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
            Affirm("Approve", enabled = canDecide, onClick = approve)
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

