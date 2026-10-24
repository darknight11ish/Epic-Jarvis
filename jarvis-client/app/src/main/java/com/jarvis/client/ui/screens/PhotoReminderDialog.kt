package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.jarvis.client.net.AlsoOnPhone
import com.jarvis.client.net.PhotoReminder
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Photo to reminder" on the phone ([PhotoReminder]; JARVIS-API.md section
 * 83): what the PC found in a shared picture, in boxes the owner can change.
 *
 * Nothing happens until a tap. "Add a Jarvis reminder" is ONE
 * [onAdd] (a one-off reminder, no card, held on a stale link - [canAct]).
 * "Also on my phone" opens the phone's own calendar with the event filled in
 * ([handToPhone], the same hand-over as Coming up's), and the owner saves it
 * there. Close drops the proposal and the words read from the picture: they
 * live in [scan] only, which the caller clears.
 *
 * A picture can hold SEVERAL dates: adding one reminder marks that proposal
 * as added and leaves the others on the dialog, so they can be added too
 * (2026-10-16 - before this, one add replaced the whole proposal with the
 * PC's sentence). The words read from the picture go on the first add.
 *
 * The words are outside text, shown as plain [Text] only.
 */
@Composable
fun PhotoReminderDialog(
    scan: PhotoReminder.Scan,
    canAct: Boolean,
    onAdd: suspend (what: String, date: String, time: String) -> Pair<Boolean, String>,
    onClose: () -> Unit,
) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val first = scan.found.firstOrNull()
    var chosen by remember(scan) { mutableStateOf(first) }
    var what by remember(scan) { mutableStateOf(first?.title.orEmpty()) }
    var date by remember(scan) { mutableStateOf(first?.date.orEmpty()) }
    var time by remember(scan) { mutableStateOf(first?.time ?: "09:00") }
    var line by remember(scan) { mutableStateOf<String?>(null) }
    var busy by remember(scan) { mutableStateOf(false) }
    var done by remember(scan) { mutableStateOf<String?>(null) }
    var added by remember(scan) { mutableStateOf(setOf<String>()) }

    Dialog(onDismissRequest = onClose) {
        Column(
            Modifier
                .fillMaxWidth()
                .background(chrome.surface1)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
        ) {
            Text(PhotoReminder.TITLE, style = MaterialTheme.typography.titleMedium)
            Gap(8)
            // The PC's sentence - and, after an add, its own sentence about
            // the reminder just set. A STATUS LINE, not a replacement for the
            // proposal: the other dates on the picture are still here.
            Text(done ?: scan.said, style = MaterialTheme.typography.bodyMedium)
            val proposals = PhotoReminder.proposals(scan, added)
            if (proposals.size > 1) {
                Gap(8)
                proposals.forEach { p ->
                    Quiet(
                        if (p.added) PhotoReminder.addedWords(p.label) else p.label,
                        enabled = !p.added,
                        onClick = {
                            chosen = p.found
                            what = p.found.title
                            date = p.found.date
                            time = p.found.time
                        },
                    )
                }
            }
            Gap(8)
            TextInput(what, { what = it.take(200) }, Modifier.fillMaxWidth(), label = PhotoReminder.WHAT_LABEL)
            Gap(8)
            TextInput(date, { date = it.take(10) }, Modifier.fillMaxWidth(), label = PhotoReminder.DATE_LABEL)
            Gap(8)
            TextInput(time, { time = it.take(5) }, Modifier.fillMaxWidth(), label = PhotoReminder.TIME_LABEL)
            PhotoReminder.hint(chosen)?.let {
                Gap(4)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
            }
            line?.let {
                Gap(4)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
            }
            Gap(12)
            Primary(
                PhotoReminder.ADD_LABEL,
                Modifier.fillMaxWidth(),
                // Shut once the boxes hold a proposal that has just been added:
                // the owner picks another date (or changes one) to add again,
                // so a quick second tap cannot set the same reminder twice.
                enabled = canAct && !busy && PhotoReminder.key(date, time) !in added,
                busy = busy,
                onClick = {
                    val problem = PhotoReminder.problem(what, date, time)
                    if (problem != null) {
                        line = problem
                        return@Primary
                    }
                    // What the boxes hold is what this add is about, so the
                    // proposal to mark is decided before the PC answers.
                    val key = PhotoReminder.key(date, time)
                    busy = true
                    scope.launch {
                        val (ok, said) = onAdd(what, date, time)
                        busy = false
                        if (ok) {
                            done = said
                            added = added + key
                            line = null
                        } else {
                            line = said
                        }
                    }
                },
            )
            Gap(8)
            Secondary(
                AlsoOnPhone.LABEL,
                Modifier.fillMaxWidth(),
                onClick = {
                    val offer = PhotoReminder.calendarOffer(what, date, time)
                    line = if (offer == null) {
                        PhotoReminder.problem(what, date, time)
                    } else {
                        handToPhone(context, offer)
                    }
                },
            )
            Gap(4)
            Text(AlsoOnPhone.NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            // The picture's own words go on the first add, as they do on the
            // PC: what stays is the proposals still to be added.
            if (added.isEmpty()) {
                if (scan.text.isNotBlank()) {
                    Gap(12)
                    Text(PhotoReminder.WORDS_READ, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                    Text(scan.text, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                Gap(8)
                Text(PhotoReminder.OUTSIDE_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
            Gap(8)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Quiet(PhotoReminder.CLOSE_LABEL, onClick = onClose)
            }
        }
    }
}
