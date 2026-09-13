package com.jarvis.assistant.ui.approval

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.ui.theme.JarvisAmber
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisGreen
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisRed
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted
import com.jarvis.assistant.ui.theme.JarvisTextPrimary

/**
 * The approval card, in plain and note-edit forms.
 *
 * A note edit gets the Markdown rendered and, where the desktop supplied enough
 * to build one, a diff — approving a note rewrite from an escaped JSON blob is
 * approving something you have not read.
 */
@Composable
fun ApprovalCard(
    request: ApprovalRequestEvent,
    onApprove: () -> Unit,
    onReject: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val diff = remember(request.id) {
        request.note?.let { NoteDiff.forPayload(it.diff, it.before, it.after) }
    }
    val summary = remember(diff) { diff?.let { NoteDiff.summarize(it) } }

    // Default to showing the diff when there is one: it is the thing being
    // approved, so it should not need a tap to reveal.
    var showDiff by rememberSaveable(request.id) { mutableStateOf(true) }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisAmber.copy(alpha = 0.4f), RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = request.title,
                style = MaterialTheme.typography.titleMedium,
                color = JarvisAmber,
                modifier = Modifier.weight(1f),
            )
            request.note?.let { note ->
                TargetBadge(if (note.isJoplin) "JOPLIN" else "LOGSEQ")
            }
        }

        request.note?.let { note ->
            val where = listOfNotNull(note.title, note.location).joinToString(" · ")
            if (where.isNotBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(where, style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
            }
        }

        if (request.summary.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = request.summary,
                style = MaterialTheme.typography.bodyMedium,
                color = JarvisTextPrimary,
            )
        }

        if (request.isNoteEdit) {
            NoteBody(
                request = request,
                diff = diff,
                added = summary?.added ?: 0,
                removed = summary?.removed ?: 0,
                expanded = showDiff,
                onToggle = { showDiff = !showDiff },
            )
        } else {
            request.detail?.takeIf { it.isNotBlank() }?.let { detail ->
                Spacer(Modifier.height(6.dp))
                Text(
                    text = detail,
                    style = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                    color = JarvisTextMuted,
                )
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = onApprove,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisGreen.copy(alpha = 0.16f),
                    contentColor = JarvisGreen,
                ),
            ) { Text("Approve") }

            Button(
                onClick = onReject,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisRed.copy(alpha = 0.16f),
                    contentColor = JarvisRed,
                ),
            ) { Text("Reject") }
        }
    }
}

@Composable
private fun NoteBody(
    request: ApprovalRequestEvent,
    diff: List<DiffLine>?,
    added: Int,
    removed: Int,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val markdown = request.note?.markdown
        ?: request.note?.after
        ?: request.detail

    if (diff != null) {
        Spacer(Modifier.height(10.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onToggle)
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = if (expanded) "▾ Changes" else "▸ Changes",
                style = MaterialTheme.typography.labelSmall,
                color = JarvisTextMuted,
            )
            Spacer(Modifier.width(10.dp))
            if (added > 0) {
                Text("+$added", style = MaterialTheme.typography.labelSmall, color = JarvisGreen)
                Spacer(Modifier.width(6.dp))
            }
            if (removed > 0) {
                Text("−$removed", style = MaterialTheme.typography.labelSmall, color = JarvisRed)
            }
        }
        AnimatedVisibility(visible = expanded) {
            DiffView(diff)
        }
    } else if (!markdown.isNullOrBlank()) {
        Spacer(Modifier.height(10.dp))
        Text("PROPOSED", style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
        Spacer(Modifier.height(6.dp))
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = 320.dp)
                .verticalScroll(rememberScrollState()),
        ) {
            MarkdownText(markdown)
        }
    }
}

@Composable
private fun DiffView(lines: List<DiffLine>, modifier: Modifier = Modifier) {
    val horizontal = rememberScrollState()

    Column(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(max = 340.dp)
            .background(Color.Black, RoundedCornerShape(8.dp))
            .border(1.dp, JarvisOutline, RoundedCornerShape(8.dp))
            .verticalScroll(rememberScrollState())
            .padding(vertical = 6.dp),
    ) {
        lines.forEach { line ->
            val (tint, prefix, background) = when (line.kind) {
                DiffKind.ADDED -> Triple(JarvisGreen, "+", JarvisGreen.copy(alpha = 0.10f))
                DiffKind.REMOVED -> Triple(JarvisRed, "−", JarvisRed.copy(alpha = 0.10f))
                DiffKind.GAP -> Triple(JarvisTextMuted, " ", Color.Transparent)
                DiffKind.CONTEXT -> Triple(JarvisTextMuted, " ", Color.Transparent)
            }
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(background)
                    .horizontalScroll(horizontal)
                    .padding(horizontal = 10.dp, vertical = 1.dp),
            ) {
                Text(
                    text = "$prefix ${line.text}",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                    ),
                    color = tint,
                    softWrap = false,
                )
            }
        }
    }
}

@Composable
private fun TargetBadge(label: String) {
    Text(
        text = label,
        style = MaterialTheme.typography.labelSmall,
        color = JarvisCyan,
        modifier = Modifier
            .background(JarvisCyan.copy(alpha = 0.12f), RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}
