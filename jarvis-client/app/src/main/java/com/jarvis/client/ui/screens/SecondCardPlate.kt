package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.SecondCard
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Second graphics card" on the Mind screen: what the PC found, the main
 * switch, one switch per feature, and the second copy of Ollama.
 *
 * A handful of approval-backed switches and nothing more - not deep config
 * editing. The same flow as the wake word: ON asks the PC, which raises one
 * approval card and changes nothing until it is approved (on the PC, or in
 * this phone's own approvals, one at a time); OFF is immediate. The switch
 * always shows what the PC last REPORTED, never what was just asked for, and
 * the plate is re-read when a card is decided.
 *
 * All the words about each switch are the PC's own (`name`, `what`, `why`),
 * read from `GET /api/second-card` - see [SecondCard]. When there is no
 * capable second card, every switch is still shown, greyed out, with the
 * reason. The pin command is PowerShell for the PC, so only its sentence is
 * shown here.
 *
 * @param busy the switch whose request is in flight, or null.
 * @param canAct false while the link is down or stale (rule 4): nothing is
 *   sent, and every switch is greyed out.
 */
@Composable
internal fun SecondCardPlate(
    read: SecondCard.Read,
    busy: String?,
    notice: String?,
    canAct: Boolean,
    onSet: (feature: String, enabled: Boolean) -> Unit,
    onRecheck: () -> Unit,
    onOpenApprovals: ((cardId: String?) -> Unit)?,
) {
    val chrome = LocalChrome.current
    val status = (read as? SecondCard.Read.Loaded)?.status
    if (status == null) {
        Plate {
            Text(
                SecondCard.readLine(read).orEmpty(),
                style = MaterialTheme.typography.bodyMedium,
                color = if (read is SecondCard.Read.NotAsked) chrome.textMid else chrome.warnInk,
            )
            Gap(8)
            Secondary(
                text = "Ask the PC again",
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
                onClick = onRecheck,
            )
            if (notice != null) {
                Gap(8)
                Text(notice, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            }
        }
        return
    }
    Plate {
        // 1. What was found.
        Kicker("What was found", Modifier.semantics { heading() })
        Gap(4)
        Text(
            status.detectedWhy.replaceFirstChar { it.uppercase() } + ".",
            style = MaterialTheme.typography.bodyMedium,
            color = if (status.capable) chrome.okInk else chrome.textMid,
        )
        for (line in SecondCard.cardLines(status)) {
            Gap(2)
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }

        // 2. The main switch, then one per feature.
        Gap(12)
        Rule()
        ApprovalSwitchRow(SecondCard.master(status), busy, canAct, onSet)
        for (view in SecondCard.switches(status)) {
            Rule()
            ApprovalSwitchRow(view, busy, canAct, onSet)
        }
        Rule()

        if (notice != null) {
            Gap(8)
            Text(notice, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        // A card is waiting: where it is, and a way to ask again. Neither
        // approves anything - the card itself is still one deliberate tap.
        if (status.pending.isNotEmpty()) {
            Gap(8)
            if (onOpenApprovals != null) {
                Quiet(
                    "Open the card →",
                    color = chrome.warnInk,
                    onClick = { onOpenApprovals(null) },
                )
            }
            Secondary(
                text = if (busy != null) "Asking…" else "Ask the PC again",
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
                onClick = onRecheck,
            )
        }

        // 3. The second copy of Ollama, and keeping the everyday one apart.
        Gap(12)
        Kicker("The second card's Ollama", Modifier.semantics { heading() })
        Gap(4)
        Text(
            SecondCard.laneLine(status),
            style = MaterialTheme.typography.bodySmall,
            color = if (status.laneState == "failed") chrome.warnInk else chrome.textMid,
        )
        val pinNote = status.pinNote
        if (!pinNote.isNullOrBlank()) {
            Gap(10)
            Kicker("Everyday Ollama", Modifier.semantics { heading() })
            Gap(4)
            Text(
                pinNote,
                style = MaterialTheme.typography.bodySmall,
                color = if (status.mainOllamaPinned == false) chrome.warnInk else chrome.textMid,
            )
            if (SecondCard.pinNeedsPc(status)) {
                Gap(4)
                Text(SecondCard.PIN_ON_PC, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }

        Gap(10)
        Text(
            "Turning a switch on raises an approval card on your PC and phone. Nothing " +
                "changes until you approve it. Turning one off happens at once. Nothing " +
                "here sends anything off your PC.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
    }
}

/**
 * One approval-backed switch: its name, the toggle, and the PC's line under
 * it. Shared with the big model's plate ([BigModelSection]), whose switches
 * follow exactly the same rules.
 */
@Composable
internal fun ApprovalSwitchRow(
    view: SecondCard.SwitchView,
    busy: String?,
    canAct: Boolean,
    onSet: (feature: String, enabled: Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                view.name,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Toggle(
                checked = view.on,
                onCheckedChange = { want -> onSet(view.id, want) },
                // OFF is always allowed; ON only when nothing blocks it. Both
                // wait for a live link and for the last request to come back.
                enabled = canAct && busy == null && (view.on || view.canTurnOn),
                modifier = Modifier.semantics { contentDescription = view.name },
            )
        }
        if (view.what.isNotBlank()) {
            Text(view.what, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Gap(4)
        Text(
            if (busy == view.id) "Asking your PC…" else view.line,
            style = MaterialTheme.typography.bodySmall,
            color = when {
                busy == view.id -> chrome.textMid
                view.waiting -> chrome.warnInk
                view.on && view.line.startsWith("Working") -> chrome.okInk
                else -> chrome.textMid
            },
        )
        // How its last card ended (denied, nobody answered, failed…), when
        // the PC says so - otherwise the row read "Off." as if nothing had
        // been asked.
        view.lastLine?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        val blocked = view.blocked
        if (!view.on && !view.waiting && blocked != null && blocked != view.line) {
            Text(blocked, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        view.needsLine?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        view.modelLine?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}
