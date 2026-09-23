package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.InboxRead
import com.jarvis.client.LinkState
import com.jarvis.client.SectionRead
import com.jarvis.client.net.Attention
import com.jarvis.client.net.DigestItem
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.UndoEntry
import com.jarvis.client.ui.parts.Freshness
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome

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
    /**
     * Stop a message still inside its send window - [UndoEntry.holdHandle].
     * Only offered on an entry that carries a handle.
     */
    onCancelHold: (UndoEntry) -> Unit = {},
    /**
     * How each list's last read came back - `JarvisRuntime.inboxRead`. Null
     * keeps the old untimed "Live." line and treats every list as read, for
     * a caller that does not pass it yet.
     */
    read: InboxRead? = null,
    /**
     * What a Revert, Cancel, mute or Mark read failed with - the shared
     * `JarvisRuntime.notice`. Null hides it.
     */
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    /** Re-reads the Inbox after a failed read. Null draws no Retry. */
    onRetry: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    // Rule 4, on this screen: Revert and Cancel are actions, so a stream we
    // cannot confirm is live disables them. `JarvisRuntime.actionBlocker`
    // refuses them again on the way out - this is the visible half of the same
    // rule, not a substitute for it.
    val canAct = link == LinkState.CONNECTED && !stale
    // A list whose route is not on this backend shows no rows, even ones left
    // over from an earlier read: "not here" and "here, with these in it" are
    // different sentences.
    val showDigest = digest.isNotEmpty() && read?.digest != SectionRead.Absent
    val showJobs = jobs.isNotEmpty() && read?.jobs != SectionRead.Absent
    val showUndo = undo.isNotEmpty() && read?.undo != SectionRead.Absent
    // "Nothing waiting" is a claim that every list was read and came back
    // empty. Before the first read, or after a read that failed, the phone
    // does not know that - and this screen used to say it anyway.
    val reads = read?.let { listOf(it.digest, it.undo, it.jobs) }
    val allAnswered = reads == null || (
        reads.all { it == SectionRead.Read || it == SectionRead.Absent } &&
            reads.any { it == SectionRead.Read }
        )
    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar("Inbox", onBack, subtitle = budgetLine(attention))

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            // This screen used to take neither `link` nor `stale`, so it showed
            // a shelf and a job list with no indication of how old either was,
            // and offered Revert and Cancel against them. It also rendered no
            // notice surface - `_notice` was only on Home - so the refusal that
            // followed a tap on a dead link was invisible: the row simply did
            // not change. Rule 4's "block acting when the stream is stale" was
            // being enforced nowhere the user could see.
            item(key = "freshness") {
                if (read != null) {
                    Freshness(
                        link,
                        stale,
                        read.fetchedAtMs,
                        readWhat = "Inbox",
                        refreshing = read.refreshing,
                    )
                } else {
                    Freshness(link, stale)
                }
            }

            // The other half of the comment above. Dimming covers the stale
            // case; a real failure on a live link still landed only in the
            // shared notice that Home, Mind and Appearance drew, so a
            // failed Undo, Cancel or mute on a LIVE link showed up only after
            // going back to Home, and the row here just did not change.
            if (notice != null) {
                item(key = "notice") { Notice(notice, onDismissNotice) }
            }

            if (read != null) {
                val problems = listOf(
                    Triple("digest", "Today's brief", read.digest),
                    Triple("jobs", "Running jobs", read.jobs),
                    Triple("undo", "The undo shelf", read.undo),
                )
                problems.forEach { (key, name, state) ->
                    if (state is SectionRead.Failed || state == SectionRead.Absent) {
                        val showingOld = when (key) {
                            "digest" -> showDigest
                            "jobs" -> showJobs
                            else -> showUndo
                        }
                        item(key = "read-$key") {
                            ReadProblem(
                                name = name,
                                state = state,
                                showingOld = showingOld,
                                onRetry = if (read.refreshing) null else onRetry,
                                retryShown = onRetry != null,
                            )
                        }
                    }
                }
            }

            item(key = "mute") {
                Plate {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(
                                "Mute spoken interruptions",
                                style = MaterialTheme.typography.titleSmall,
                                color = chrome.textHi,
                            )
                            // There is no "mute forever", and this says so rather
                            // than leaving the user to discover the limit.
                            Text(
                                "Until tomorrow. Anything you asked for is never counted.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                            )
                        }
                        Toggle(
                            // `muted` is its own field on the budget. `blocked_by` says why the
                            // budget is zero — "quiet", "standby", a locked session — and is
                            // null most of the time, so a switch reading it was a switch that
                            // could never be on.
                            checked = attention.muted,
                            onCheckedChange = onSetMuted,
                            // This app's own switch now (visual-11), and named: the stock
                            // one was read by TalkBack as just "switch, off", with the
                            // words beside it a separate stop it had no link to.
                            modifier = Modifier.semantics {
                                contentDescription = "Mute spoken interruptions until tomorrow"
                            },
                        )
                    }
                }
            }

            if (showDigest) {
                item(key = "digest-label") {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // Headings, these three labels, so TalkBack's
                            // "navigate by headings" can jump between lists.
                            Text(
                                "TODAY'S BRIEF",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk,
                                modifier = Modifier.weight(1f).semantics { heading() },
                            )
                            Quiet("Mark read", onClick = onMarkSeen)
                        }
                        // In the same eyeline as the button, deliberately. The brief
                        // lists approvals; "read" and "approved" are one plausible
                        // misreading apart, and that misreading is irreversible.
                        Text(
                            "Marking read approves nothing.",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                    }
                }
                // Already ranked by consequence. Rendered in the order it
                // arrived, deliberately.
                items(digest, key = { "d-" + it.id }) { entry ->
                    Plate {
                        Text(
                            entry.title.ifBlank { entry.kind },
                            style = MaterialTheme.typography.titleSmall,
                            color = chrome.textHi,
                        )
                        if (entry.summary.isNotBlank()) {
                            Gap(4)
                            Text(
                                entry.summary,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        }
                        if (entry.opensCard) {
                            // The brief lists approvals and cannot decide them.
                            // Each one opens its own gate card.
                            Gap(8)
                            Text(
                                "Open the approval →",
                                style = MaterialTheme.typography.labelMedium,
                                color = chrome.warnInk,
                                modifier = Modifier
                                    .pressable { onOpenApproval(entry.id) }
                                    .minimumInteractiveComponentSize(),
                            )
                        }
                    }
                }
            }

            if (showJobs) {
                item(key = "jobs-label") {
                    Text(
                        "RUNNING",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk,
                        modifier = Modifier.semantics { heading() },
                    )
                }
                items(jobs, key = { "j-" + it.id }) { job ->
                    Plate {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                job.label.ifBlank { job.id },
                                style = MaterialTheme.typography.titleSmall,
                                color = chrome.textHi,
                                modifier = Modifier.weight(1f),
                            )
                            if (job.private) {
                                Text(
                                    "PRIVATE",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.okInk,
                                )
                            }
                        }
                        Gap(4)
                        Text(
                            buildString {
                                append(job.state.ifBlank { "running" })
                                job.progress?.let { append(" · ${(it * 100).toInt()}%") }
                                if (job.capabilities.isNotEmpty()) {
                                    append(" · ${job.capabilities.size} frozen permissions")
                                }
                            },
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                        Gap(8)
                        // A cancelled job is not resumable, so the label says
                        // "cancel" rather than "pause".
                        Action("Cancel", chrome.textMid, enabled = canAct) { onCancelJob(job) }
                    }
                }
            }

            if (showUndo) {
                item(key = "undo-label") {
                    Text(
                        "UNDO SHELF",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid,
                        modifier = Modifier.semantics { heading() },
                    )
                }
                items(undo, key = { "u-" + it.id }) { entry ->
                    Plate {
                        Text(
                            entry.label.ifBlank { entry.what },
                            style = MaterialTheme.typography.titleSmall,
                            color = chrome.textHi,
                        )
                        if (entry.holdHandle != null) {
                            // Not sent yet: neither undoable nor final. The
                            // desktop's Brain window shows the same button.
                            Gap(4)
                            Text(
                                entry.reason ?: "Still inside its send window - it can still be stopped.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk,
                            )
                            Gap(8)
                            Action("Stop sending", chrome.badInk, enabled = canAct) { onCancelHold(entry) }
                        } else if (entry.reversible) {
                            Gap(8)
                            Action("Undo", chrome.okInk, enabled = canAct) { onRevert(entry) }
                        } else {
                            // Listed anyway, marked, with the reason. A shelf
                            // that quietly left these off would look like a
                            // complete record of what happened when it is not.
                            Gap(4)
                            Text(
                                entry.reason ?: "Cannot be undone.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk,
                            )
                        }
                    }
                }
            }

            if (allAnswered && !showDigest && !showUndo && !showJobs) {
                item(key = "empty") {
                    Text(
                        "Nothing waiting.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                    )
                }
            }
        }
    }
}

/**
 * One Inbox list that did not come back: it could not be read, or it is not
 * on this backend. Said per list, because the three are read separately and
 * one failing says nothing about the other two.
 *
 * @param showingOld true when the list's rows from an earlier read are still
 *   on screen below, which a failed re-read leaves in place.
 * @param onRetry null while a read is already out (the button then says
 *   "Retrying…"); [retryShown] false draws no button at all.
 */
@Composable
private fun ReadProblem(
    name: String,
    state: SectionRead,
    showingOld: Boolean,
    onRetry: (() -> Unit)?,
    retryShown: Boolean,
) {
    val chrome = LocalChrome.current
    if (state is SectionRead.Failed) {
        Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
            Text(
                "Could not read ${name.replaceFirstChar { it.lowercase() }}: ${state.reason}",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
            )
            if (showingOld) {
                Gap(4)
                Text(
                    "What is shown below is from the last read that worked.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }
            if (retryShown) {
                Quiet(
                    if (onRetry == null) "Retrying…" else "Retry",
                    enabled = onRetry != null,
                    onClick = { onRetry?.invoke() },
                )
            }
        }
    } else {
        Text(
            "$name: not on this backend.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
}

private fun budgetLine(a: Attention): String = when {
    a.blockedBy != null -> "Silent — ${a.blockedBy}. ${a.pending} waiting."
    a.limit > 0 -> "${a.remaining} of ${a.limit} spoken interruptions left. ${a.pending} waiting."
    else -> "${a.pending} waiting."
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
            .pressable(enabled = enabled, onClick = onClick)
            .minimumInteractiveComponentSize()
            .background(shade.copy(alpha = 0.12f), RoundedCornerShape(8.dp))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    )
}
