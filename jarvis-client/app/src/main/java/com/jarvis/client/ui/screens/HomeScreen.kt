package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.FaceState
import com.jarvis.client.LinkState
import com.jarvis.client.face.FaceView
import com.jarvis.client.net.Attention
import com.jarvis.client.net.PendingItem
import com.jarvis.client.ui.T
import com.jarvis.client.ui.approval.ApprovalCard

@Immutable
data class HomeState(
    val link: LinkState,
    val linkDetail: String?,
    val stale: Boolean,
    val activity: Activity,
    val faceState: FaceState,
    val power: String,
    val pending: List<PendingItem>,
    val attention: Attention,
    val notice: String?,
    val reply: String,
    val streaming: Boolean,
    val draft: String,
)

@Immutable
data class HomeActions(
    val onDraftChange: (String) -> Unit,
    val onSend: () -> Unit,
    val onInterrupt: () -> Unit,
    val onApprove: (PendingItem) -> Unit,
    val onDeny: (PendingItem) -> Unit,
    val onReconnect: () -> Unit,
    val onDismissNotice: () -> Unit,
    val onOpenReadiness: () -> Unit,
    val onOpenInbox: () -> Unit,
    val blockerFor: (PendingItem) -> String?,
)

@Composable
fun HomeScreen(state: HomeState, actions: HomeActions, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxSize()
            .background(T.Void)
            .navigationBarsPadding()
            .imePadding(),
    ) {
        LinkBar(state, actions)

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "face") {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    FaceView(
                        state = state.faceState,
                        notches = state.attention.pending,
                        modifier = Modifier.size(240.dp),
                    )
                }
            }

            if (state.notice != null) {
                item(key = "notice") {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .background(T.Warn.copy(alpha = 0.10f), RoundedCornerShape(10.dp))
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            state.notice,
                            style = MaterialTheme.typography.bodySmall,
                            color = T.Warn,
                            modifier = Modifier.weight(1f),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "Dismiss",
                            style = MaterialTheme.typography.labelSmall,
                            color = T.Pick,
                            modifier = Modifier
                                .androidxClickable(actions.onDismissNotice)
                                .padding(6.dp),
                        )
                    }
                }
            }

            if (state.pending.isNotEmpty()) {
                item(key = "approvals-label") {
                    Text(
                        "WAITING ON YOU",
                        style = MaterialTheme.typography.labelSmall,
                        color = T.Warn,
                    )
                }
                items(state.pending, key = { it.id }) { item ->
                    ApprovalCard(
                        item = item,
                        blocker = actions.blockerFor(item),
                        onApprove = { actions.onApprove(item) },
                        onDeny = { actions.onDeny(item) },
                    )
                }
            }

            if (state.reply.isNotBlank() || state.streaming) {
                item(key = "reply") {
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .background(T.Plate, RoundedCornerShape(12.dp))
                            .padding(14.dp),
                    ) {
                        Text(
                            state.reply.ifBlank { "…" },
                            style = MaterialTheme.typography.bodyMedium,
                            color = T.Ink,
                        )
                    }
                }
            }
        }

        Composer(state, actions)
    }
}

@Composable
private fun LinkBar(state: HomeState, actions: HomeActions) {
    // Two different facts, never merged into one word: whether the stream is up,
    // and whether Jarvis is busy. Collapsing them is how a client ends up
    // showing "thinking" at a desktop that went away ten minutes ago.
    val (dot, label) = when {
        state.link != LinkState.CONNECTED -> T.Bad to (state.linkDetail ?: "Offline")
        state.stale -> T.Warn to "Stale — reconnecting"
        else -> when (state.activity) {
            Activity.LISTENING -> T.Warn to "Listening"
            Activity.THINKING, Activity.WORKING -> T.Pick to "Thinking"
            Activity.SPEAKING -> T.Pick to "Speaking"
            Activity.ERROR -> T.Bad to "Error on the desktop"
            else -> T.Ok to if (state.power == "quiet") "Linked · quiet" else "Linked"
        }
    }

    Row(
        Modifier
            .fillMaxWidth()
            .background(T.Plate)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).background(dot, CircleShape))
        Spacer(Modifier.width(10.dp))
        Text(label, style = MaterialTheme.typography.labelMedium, color = T.Ink)
        Spacer(Modifier.weight(1f))
        if (state.attention.pending > 0) {
            // "N banked" was wrong twice over. `pending` is the digest count —
            // the notch count for the rim ring — and `banked` is a separate
            // boolean that is false most of the time, so this said "banked"
            // about a system that was not. The desktop's own phrasing, which
            // says what the number counts.
            Text(
                if (state.attention.pending == 1) {
                    "1 thing waiting to be told"
                } else {
                    "${state.attention.pending} things waiting to be told"
                },
                style = MaterialTheme.typography.labelSmall,
                color = if (state.attention.banked) T.Dim else T.Dim,
            )
            Spacer(Modifier.width(10.dp))
        }
        if (state.link != LinkState.CONNECTED) {
            Text(
                "Retry",
                style = MaterialTheme.typography.labelSmall,
                color = T.Pick,
                modifier = Modifier.androidxClickable(actions.onReconnect).padding(6.dp),
            )
        } else {
            Text(
                "Inbox",
                style = MaterialTheme.typography.labelSmall,
                color = if (state.attention.pending > 0) T.Warn else T.Dim,
                modifier = Modifier.androidxClickable(actions.onOpenInbox).padding(6.dp),
            )
            Spacer(Modifier.width(4.dp))
            Text(
                "Checks",
                style = MaterialTheme.typography.labelSmall,
                color = T.Dim,
                modifier = Modifier.androidxClickable(actions.onOpenReadiness).padding(6.dp),
            )
        }
    }
}

@Composable
private fun Composer(state: HomeState, actions: HomeActions) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(T.Plate)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = state.draft,
            onValueChange = actions.onDraftChange,
            placeholder = { Text("Ask Jarvis", color = T.Dim) },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            colors = fieldColors(),
            modifier = Modifier.weight(1f),
            maxLines = 4,
        )
        Spacer(Modifier.width(10.dp))
        Button(
            // Interrupt is the same button, because it is the same action's other
            // half: cancelling the HTTP call is what stops generation.
            onClick = if (state.streaming) actions.onInterrupt else actions.onSend,
            enabled = state.streaming ||
                (state.draft.isNotBlank() && state.link == LinkState.CONNECTED),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = T.Void,
                contentColor = if (state.streaming) T.Bad else T.Pick,
            ),
        ) { Text(if (state.streaming) "Stop" else "Send") }
    }
}

/** Clickable with a button role, so TalkBack does not announce it as static text. */
private fun Modifier.androidxClickable(onClick: () -> Unit): Modifier =
    this.clickable(role = Role.Button, onClick = onClick)
