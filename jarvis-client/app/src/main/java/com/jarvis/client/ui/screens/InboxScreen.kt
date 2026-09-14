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
import com.jarvis.client.LinkState
import com.jarvis.client.net.Attention
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.ui.T
import com.jarvis.client.ui.parts.Freshness

/**
 * The brief, the shelf and the running jobs.
 *
 * The send-hold queue is deliberately absent: the API can cancel a hold but has
 * no route that lists them, so a phone cannot learn a handle. A section for
 * data that can never arrive is worse than no section.
 *
 * One screen rather than three, because none of it is urgent — that is the point
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
    link: LinkState,
    stale: Boolean,
    attention: Attention,
    digest: List<DigestItem>,
    undo: List<UndoEntry>,
    jobs: List<JobRecord>,
    onOpenApproval: (String) -> Unit,
    onRevert: (UndoEntry) -> Unit,
    onCancelJob: (JobRecord) -> Unit,
    onMarkSeen: () -> Unit,
    onSetMuted: (Boolean) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // Rule 4, on this screen: Revert and Cancel are actions, so a stream we
    // cannot confirm is live disables them. `JarvisRuntime.actionBlocker`
    // refuses them again on the way out - this is the visible half of the same
    // rule, not a substitute for it.
    val canAct = link == LinkState.CONNECTED && !stale
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
            // This screen used to take neither `link` nor `stale`, so it showed
            // a shelf and a job list with no indication of how old either was,
            // and offered Revert and Cancel against them. It also renders no
            // notice surface - `_notice` is only on Home - so the refusal that
            // followed a tap on a dead link was invisible: the row simply did
            // not change. Rule 4's "block acting when the stream is stale" was
            // being enforced nowhere the user could see.
            item(key = "freshness") { Freshness(link, stale) }

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
                        // `muted` is its own field on the budget. `blocked_by` says why the
                        // budget is zero — "quiet", "standby", a locked session — and is
                        // null most of the time, so a switch reading it was a switch that
                        // could never be on.
                        checked = attention.muted,
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
                    Column {
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
                    // In the same eyeline as the button, deliberately. The brief
                    // lists approvals; "read" and "approved" are one plausible
                    // misreading apart, and that misreading is irreversible.
                    Text(
                        "Marking read approves nothing.",
                        style = MaterialTheme.typography.labelSmall,
                        color = T.Dim,
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
                        Action("Cancel", T.Dim, enabled = canAct) { onCancelJob(job) }
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
                            Action("Undo", T.Ok, enabled = canAct) { onRevert(entry) }
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

            if (digest.isEmpty() && undo.isEmpty() && jobs.isEmpty()) {
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
private fun Action(
    label: String,
    tint: androidx.compose.ui.graphics.Color,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    // Dimmed and unclickable rather than hidden. A control that vanishes when
    // the link drops reads as "this was never possible"; one that greys out
    // reads as "not right now", which is the true statement and the one the
    // freshness row at the top of this screen is already making.
    val shade = if (enabled) tint else tint.copy(alpha = 0.35f)
    Text(
        label,
        style = MaterialTheme.typography.labelMedium,
        color = shade,
        modifier = Modifier
            .clickable(role = Role.Button, enabled = enabled, onClick = onClick)
            .minimumInteractiveComponentSize()
            .background(shade.copy(alpha = 0.12f), RoundedCornerShape(8.dp))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    )
}
