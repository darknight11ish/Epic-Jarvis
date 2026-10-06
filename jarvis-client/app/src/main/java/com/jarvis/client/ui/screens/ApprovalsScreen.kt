package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.jarvis.client.LinkState
import com.jarvis.client.SectionRead
import com.jarvis.client.net.GateHistoryItem
import com.jarvis.client.net.PastApprovals
import com.jarvis.client.ui.parts.Freshness
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.ageText
import com.jarvis.client.ui.theme.Chrome
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Past approvals" - the phone's own screen for cards already decided (the
 * owner's decision, 2026-09-27: "A read-only list of past approvals (title,
 * Approved / Denied / Timed out, when, which device)"; docs/JARVIS-API.md
 * section 42).
 *
 * WHY IT IS ITS OWN SCREEN. The rows were drawn as the Inbox's "ACTIVITY"
 * section, and the approvals audit of 2026-09-30 said the one thing wrong with
 * it: "It is only reachable via Inbox" (docs/audit-reports-2026-09-29-30/
 * 49-audit-a1ef1de0.md). The Inbox keeps the heading and a row that opens this
 * screen - the way HistoryScreen's settings rows stay on History while the
 * conversations themselves are the screen - so approvals stay reachable from
 * where they always were, and the list itself now has a surface of its own
 * that can hide by the same rule as every other history surface.
 *
 * READ-ONLY, AND THAT IS THE WHOLE DESIGN. There is no button on a row: no
 * approve, no deny, no cancel, no clear, no reopening a card, and nothing here
 * can retry a decision. The only controls on the screen are the four filter
 * chips, which change which rows are drawn, and Refresh, which reads the list
 * again. A decided card is a record, not a question - and the raw rows this
 * reads never carried a command, a recipient or a body anyway
 * ([GateHistoryItem]; backend/test_gate_egress.py's
 * `t_site_4_history_never_reads_it`).
 *
 * NO CARD IS RAISED HERE, no permission is asked for, and the screen adds no
 * new way out of the PC: it reads `/api/pending`'s `history` half through
 * [com.jarvis.client.net.JarvisApi.gateHistoryRead], the same read the Inbox
 * already made.
 *
 * "Hide memory lists and chat history" (Security) hides the list exactly as it
 * hides History's conversations and Brain's memory lists: [HiddenSection] with
 * a Show that asks for the fingerprint or PIN, then the rows. The heading and
 * this screen's own way in stay visible for the same reason HistoryScreen
 * keeps its settings visible - they say nothing about what was decided.
 *
 * The list is read when the screen opens, when Show confirms, and on Refresh;
 * the phone keeps no copy of its own.
 */
@Composable
fun ApprovalsScreen(
    link: LinkState,
    stale: Boolean,
    /** The rows as last read ([com.jarvis.client.JarvisRuntime.pastApprovals]). */
    items: List<GateHistoryItem>,
    /** How the last read came back - the Inbox's own `activity` field. */
    read: SectionRead = SectionRead.Reading,
    /** When that read last succeeded. 0 means never, on this run of the app. */
    fetchedAtMs: Long = 0L,
    /** A read is in flight, so the freshness line can say so. */
    refreshing: Boolean = false,
    /** Reads the list again. Only ever a read. */
    onRead: () -> Unit = {},
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    /** "Hide memory lists and chat history" is on: the list stays hidden until Show. */
    privateHidden: Boolean = false,
    onShowPrivate: () -> Unit = {},
    showPrivateBusy: Boolean = false,
) {
    val chrome = LocalChrome.current
    // Which of the four chips is chosen. Saveable, so a rotation does not drop
    // the owner's place - and it only ever holds one of these four ids, never
    // anything out of a row.
    var filter by rememberSaveable { mutableStateOf(PastApprovals.ALL) }
    // Bumped by Refresh so the read runs again.
    var reads by remember { mutableIntStateOf(0) }

    // The one read. It runs when the screen opens (MainActivity navigates
    // here) and again when Show lifts the hide, so a screen opened while
    // hidden still shows the list the moment the owner confirms it is them -
    // and it is skipped entirely while hidden, since nothing of it is drawn.
    LaunchedEffect(privateHidden, reads) {
        if (!privateHidden) onRead()
    }

    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(
            PastApprovals.TITLE,
            onBack,
            trailing = {
                Quiet(
                    if (refreshing) "Refreshing…" else "Refresh",
                    enabled = !refreshing,
                    onClick = { reads += 1 },
                )
            },
        )

        if (privateHidden) {
            HiddenSection(PastApprovals.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
            return@Column
        }

        // "not on this backend" is a fact about the desktop, so no rows are
        // drawn under it even if an earlier read left some in memory - the
        // same rule the Inbox's own activity section uses. Rows that failed to
        // RE-read, by contrast, stay: they were true as of when they were read.
        val shown = if (read == SectionRead.Absent) emptyList() else PastApprovals.rows(items, filter)
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(key = "freshness") {
                Freshness(
                    link,
                    stale,
                    fetchedAtMs,
                    readWhat = PastApprovals.TITLE,
                    refreshing = refreshing,
                )
            }

            if (notice != null) {
                item(key = "notice") { Notice(notice, onDismissNotice) }
            }

            item(key = "lead") {
                Plate {
                    Text(
                        PastApprovals.LEAD,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
            }

            // The four chips, in the desktop's own order and its own words.
            // Nothing else on this screen is tappable except Refresh above.
            item(key = "filters") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (chip in PastApprovals.FILTERS) {
                        Quiet(
                            text = chip.label,
                            color = if (filter == chip.id) chipInk(chip.id, chrome) else chrome.textMid,
                            onClick = { filter = chip.id },
                        )
                    }
                }
            }

            when (val r = read) {
                // 404 or 503: this desktop has no approval history to read. A
                // fact about the PC, not a fault, so no Retry is offered.
                SectionRead.Absent -> item(key = "absent") {
                    Text(
                        PastApprovals.NOT_HERE,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
                is SectionRead.Failed -> item(key = "failed") {
                    Plate(
                        tone = chrome.warnInk.copy(alpha = 0.10f),
                        outline = chrome.warnInk.copy(alpha = 0.35f),
                    ) {
                        Text(
                            PastApprovals.failed(r.reason),
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.warnInk,
                        )
                        if (items.isNotEmpty()) {
                            Gap(4)
                            Text(
                                PastApprovals.SHOWING_OLD,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                            )
                        }
                    }
                }
                else -> Unit
            }

            // "Nothing decided yet" is a claim about what the PC holds, and
            // this phone does not know it before an answer comes back - the
            // same rule the Inbox learned the hard way ("Nothing waiting"
            // before its first read).
            if (read == SectionRead.Reading) {
                item(key = "reading") {
                    Text(
                        PastApprovals.READING,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textLo,
                    )
                }
            } else if (read == SectionRead.Read && shown.isEmpty() && items.isEmpty()) {
                item(key = "empty") {
                    Text(
                        PastApprovals.EMPTY,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                    )
                }
            } else if (read == SectionRead.Read && shown.isEmpty()) {
                // There is history, but none of it is this outcome. Said in
                // words rather than an empty page under a chip that then looks
                // broken - and nothing is hidden from the owner: All still has
                // every row, an outcome this phone could not read included.
                item(key = "none-this-way") {
                    Text(
                        PastApprovals.noneThisWay(filter),
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid,
                    )
                }
            }

            items(shown, key = { "a-" + it.id }) { row -> ApprovalRow(row) }
        }
    }
}

/** The chip's own colour, the same three the rows use. */
private fun chipInk(id: String, chrome: Chrome): Color = when (id) {
    "approved" -> chrome.okInk
    "denied" -> chrome.badInk
    "timed_out" -> chrome.warnInk
    else -> chrome.textHi
}

/**
 * One past card, drawn read-only: what it was, the one-line summary the PC
 * sent with it, then how it ended, how long ago, and which device decided it -
 * the desktop's own field order (`renderActivity`, jarvis-desktop/src/brain.js).
 * No button, no link, and nothing tappable anywhere in this row.
 */
@Composable
private fun ApprovalRow(item: GateHistoryItem) {
    val chrome = LocalChrome.current
    Plate {
        Text(
            item.title,
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
        )
        item.summary?.takeIf { it.isNotBlank() }?.let { summary ->
            Gap(4)
            Text(
                summary,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        Gap(4)
        Text(
            buildString {
                append(item.outcomeLabel)
                if (item.whenAt > 0) {
                    append(" · ")
                    // The decision time if the row has one, else when it was
                    // raised - [GateHistoryItem.whenAt]. Coarse on purpose, the
                    // same words the Inbox and the desktop use.
                    append(ageText(System.currentTimeMillis() - (item.whenAt * 1000).toLong()))
                }
                // A row that names no device says nothing about one, rather
                // than guessing "this PC".
                item.device?.takeIf { it.isNotBlank() }?.let {
                    append(" · ")
                    append(it)
                }
            },
            style = MaterialTheme.typography.labelSmall,
            color = when (item.outcomeLabel) {
                "Approved" -> chrome.okInk
                "Denied" -> chrome.badInk
                else -> chrome.textMid
            },
        )
    }
}
