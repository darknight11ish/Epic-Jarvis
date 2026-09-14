package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.Attention
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.HoldRecord
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.ui.T

/**
 * The brief, the shelf, the jobs and anything still inside its send window.
 *
 * One screen rather than four, because none of it is urgent — that is the point
 * of a digest — and four tabs for a handful of rows each is navigation for its
 * own sake.
 *
 * The rules here are all about what is *absent*. There is no approve-all. There
 * is no re-sorting: the digest arrives ranked by consequence, server-side, and
 * sorting it by anything in an item's own text would let the text decide its own
 * priority. There is no control that clears a rush latch.
 */
@Composable
fun InboxScreen(
    attention: Attention,
    digest: List<DigestItem>,
    undo: List<UndoEntry>,
    jobs: List<JobRecord>,
    holds: List<HoldRecord>,
    onOpenApproval: (String) -> Unit,
    onRevert: (UndoEntry) -> Unit,
    onCancelJob: (JobRecord) -> Unit,
    onCancelHold: (HoldRecord) -> Unit,
    onMarkSeen: () -> Unit,
    onSetMuted: (Boolean) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxSize().background(T.Void)) {
        Row(
            Modifier.fillMaxWidth().background(T.Plate).padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("Inbox", style = MaterialTheme.typography.titleMedium, color = T.Pick)
                Text(
                    budgetLine(attention),
                    style = MaterialTheme.typography.labelSmall,
                    color = T.Dim,
                )
            }
            Text(
                "Back",
                style = MaterialTheme.typography.labelMedium,
                color = T.Pick,
                modifier = Modifier
                    .clickable(role = Role.Button, onClick = onBack)
                    .minimumInteractiveComponentSize()
                    .padding(6.dp),
            )
        }

        LazyColumn(
            Modifier.weight(1f),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(key = "mute") {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(T.Plate, RoundedCornerShape(12.dp))
                        .padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "Mute spoken interruptions",
                            style = MaterialTheme.typography.titleSmall,
                            color = T.Ink,
                        )
                        // There is no "mute forever", and this says so rather
                        // than leaving the user to discover the limit.
                        Text(
                            "Until tomorrow. Anything you asked for is never counted.",
                            style = MaterialTheme.typography.labelSmall,
                            color = T.Dim,
                        )
                    }
                    Switch(
                        checked = attention.blockedBy == "muted",
                        onCheckedChange = onSetMuted,
                        colors = SwitchDefaults.colors(
                            checkedTrackColor = T.Warn.copy(alpha = 0.4f),
                            checkedThumbColor = T.Warn,
                        ),
                    )
                }
            }

            if (digest.isNotEmpty()) {
                item(key = "digest-label") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            "TODAY'S BRIEF",
                            style = MaterialTheme.typography.labelSmall,
                            color = T.Warn,
                            modifier = Modifier.weight(1f),
                        )
                        Text(
                            "Mark read",
                            style = MaterialTheme.typography.labelSmall,
                            color = T.Pick,
                            modifier = Modifier
                                .clickable(role = Role.Button, onClick = onMarkSeen)
                                .minimumInteractiveComponentSize()
                                .padding(6.dp),
                        )
                    }
                }
                // Already ranked by consequence. Rendered in the order it
                // arrived, deliberately.
                items(digest, key = { "d-" + it.id }) { entry ->
                    Card {
                        Text(
                            entry.title.ifBlank { entry.kind },
                            style = MaterialTheme.typography.titleSmall,
                            color = T.Ink,
                        )
                        if (entry.summary.isNotBlank()) {
                            Spacer(Modifier.height(4.dp))
                            Text(
                                entry.summary,
                                style = MaterialTheme.typography.bodySmall,
                                color = T.Dim,
                            )
                        }
                        if (entry.opensCard) {
                            // The brief lists approvals and cannot decide them.
                            // Each one opens its own gate card.
                            Spacer(Modifier.height(8.dp))
                            Text(
                                "Open the approval →",
                                style = MaterialTheme.typography.labelMedium,
                                color = T.Warn,
                                modifier = Modifier
                                    .clickable(role = Role.Button) { onOpenApproval(entry.id) }
                                    .minimumInteractiveComponentSize(),
                            )
                        }
                    }
                }
            }

            if (holds.isNotEmpty()) {
                item(key = "holds-label") {
                    Text(
                        "SENDING — STOPPABLE FOR A FEW SECONDS",
                        style = MaterialTheme.typography.labelSmall,
                        color = T.Bad,
                    )
                }
                items(holds, key = { "h-" + it.handle }) { hold ->
                    Card(border = T.Bad) {
                        Text(
                            hold.label.ifBlank { "Outgoing message" },
                            style = MaterialTheme.typography.titleSmall,
                            color = T.Ink,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            "This hold is the only honest unsend there is.",
                            style = MaterialTheme.typography.labelSmall,
                            color = T.Dim,
                        )
                        Spacer(Modifier.height(8.dp))
                        Action("Stop it", T.Bad) { onCancelHold(hold) }
                    }
                }
            }

            if (jobs.isNotEmpty()) {
                item(key = "jobs-label") {
                    Text("RUNNING", style = MaterialTheme.typography.labelSmall, color = T.Pick)
                }
                items(jobs, key = { "j-" + it.id }) { job ->
                    Card {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                job.label.ifBlank { job.id },
                                style = MaterialTheme.typography.titleSmall,
                                color = T.Ink,
                                modifier = Modifier.weight(1f),
                            )
                            if (job.private) {
                                Text(
                                    "PRIVATE",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = T.Ok,
                                )
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(
                            buildString {
                                append(job.state.ifBlank { "running" })
                                job.progress?.let { append(" · ${(it * 100).toInt()}%") }
                                if (job.capabilities.isNotEmpty()) {
                                    append(" · ${job.capabilities.size} frozen permissions")
                                }
                            },
                            style = MaterialTheme.typography.labelSmall,
                            color = T.Dim,
                        )
                        Spacer(Modifier.height(8.dp))
                        // A cancelled job is not resumable, so the label says
                        // "cancel" rather than "pause".
                        Action("Cancel", T.Dim) { onCancelJob(job) }
                    }
                }
            }

            if (undo.isNotEmpty()) {
                item(key = "undo-label") {
                    Text("UNDO SHELF", style = MaterialTheme.typography.labelSmall, color = T.Dim)
                }
                items(undo, key = { "u-" + it.id }) { entry ->
                    Card {
                        Text(
                            entry.label.ifBlank { entry.what },
                            style = MaterialTheme.typography.titleSmall,
                            color = T.Ink,
                        )
                        if (entry.reversible) {
                            Spacer(Modifier.height(8.dp))
                            Action("Undo", T.Ok) { onRevert(entry) }
                        } else {
                            // Listed anyway, marked, with the reason. A shelf
                            // that quietly left these off would look like a
                            // complete record of what happened when it is not.
                            Spacer(Modifier.height(4.dp))
                            Text(
                                entry.reason ?: "Cannot be undone.",
                                style = MaterialTheme.typography.labelSmall,
                                color = T.Warn,
                            )
                        }
                    }
                }
            }

            if (digest.isEmpty() && undo.isEmpty() && jobs.isEmpty() && holds.isEmpty()) {
                item(key = "empty") {
                    Text(
                        "Nothing waiting.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = T.Dim,
                    )
                }
            }
        }
    }
}

private fun budgetLine(a: Attention): String = when {
    a.blockedBy != null -> "Silent — ${a.blockedBy}. ${a.pending} waiting."
    a.limit > 0 -> "${a.remaining} of ${a.limit} spoken interruptions left. ${a.pending} waiting."
    else -> "${a.pending} waiting."
}

@Composable
private fun Card(
    border: androidx.compose.ui.graphics.Color? = null,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(T.Plate, RoundedCornerShape(12.dp))
            .then(
                if (border != null) {
                    Modifier.border(1.dp, border.copy(alpha = 0.4f), RoundedCornerShape(12.dp))
                } else {
                    Modifier
                },
            )
            .padding(14.dp),
        content = content,
    )
}

@Composable
private fun Action(label: String, tint: androidx.compose.ui.graphics.Color, onClick: () -> Unit) {
    Text(
        label,
        style = MaterialTheme.typography.labelMedium,
        color = tint,
        modifier = Modifier
            .clickable(role = Role.Button, onClick = onClick)
            .minimumInteractiveComponentSize()
            .background(tint.copy(alpha = 0.12f), RoundedCornerShape(8.dp))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    )
}
