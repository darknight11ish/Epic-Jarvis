package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Limits
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/**
 * "Limits and how often Jarvis does things" - the phone's Settings row for the
 * PC's own limit table (`backend/jarvis_limits.py`, 2026-10-08; [Limits]).
 *
 * ONE row per limit, each with a control that fits its `kind`: the fixed
 * choices as chips, any other number as a step down / value / step up, a bool
 * as the app's own [Toggle], and a clock time as the app's own [TimePicker]
 * (Material's clock, 24-hour, started where the value in force is). Every
 * control carries the owner's words for TalkBack ([Limits.rowWords],
 * [Limits.upWords], [Limits.choiceWords], [Limits.timeWords]) - the same
 * deliberate habit the switches on "How Jarvis talks" already have, so a step
 * is never just a "-" and a clock is never just "Change".
 *
 * THE PC'S OWN NOTIFICATIONS ARE ROWS HERE TOO (the owner's decision of
 * 2026-10-08): which of the PC's own toasts fire, and the quiet hours around
 * them, so the phone can change them. Their titles all say "(on your PC)" - the
 * phone's OWN notification settings are a different screen and must never be
 * mistaken for them. While quiet hours are off the PC says so on every row
 * (`quiet_on`), and the two clock rows then show their value with a line saying
 * the hour decides nothing rather than a picker that would change nothing.
 *
 * WHAT IT WILL NOT PRETEND. A number turned DOWN applies at once; a number
 * turned UP - on a row the PC marks `loosen_up` - is a loosening, and the PC
 * puts ONE approval card to the owner and writes nothing until it is answered
 * THERE. So the plate says that once, plainly, and every change re-reads the
 * rows afterwards: a 2xx can mean "a card is waiting", never "it is done". The
 * sentence under the list is always the PC's own ([JarvisRuntime.setLimit]),
 * and a refusal goes into the shared notice too.
 *
 * [Limits.offered] is what is drawn, so a row the PC marks `pc_only` cannot
 * appear here even if a PC sends one.
 */
@Composable
internal fun LimitsSection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var rows by remember { mutableStateOf<List<Limits.Row>?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    /** The key of the clock row whose picker is open, if any. */
    var picking by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.limits()) {
            is ApiResult.Ok -> {
                rows = Limits.offered(r.value)
                missing = false
                readError = null
            }
            is ApiResult.Failed -> if (Limits.missing(r.error)) {
                missing = true
                readError = null
                rows = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun change(key: String, value: JsonElement) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.setLimit(key, value)
            } finally {
                busy = false
                // Re-read whatever the answer was: a raise that was approved on
                // the PC is written there, and one still waiting is not.
                reads += 1
            }
        }
    }

    Section(Limits.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Limits.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(4)
            // Said ONCE, above the rows: what a tap up does, and what a tap down
            // does not. Never repeated per row, never softened.
            Text(Limits.LOOSEN_NOTE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(6)
            val v = rows
            val err = readError
            when {
                missing -> Text(Limits.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read the limits: $err" else Limits.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                v.isEmpty() -> Text(Limits.EMPTY, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                else -> v.forEach { r ->
                    LimitRow(
                        row = r,
                        enabled = canAct && !busy,
                        onChange = { value -> change(r.key, value) },
                        onPickTime = { picking = r.key },
                    )
                }
            }
            said?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }

    // The picker is drawn OUTSIDE the card, and only for the row whose button
    // was tapped: opening a clock is not a change, and nothing is sent until
    // "Use this time" is tapped.
    val open = rows?.firstOrNull { it.key == picking }
    if (open != null && open.isTime) {
        TimeRowDialog(
            row = open,
            onDismiss = { picking = null },
            onChosen = { text ->
                picking = null
                change(open.key, Limits.timeJson(text))
            },
        )
    }
}

/** ONE limit: the PC's title, the value in the PC's words, and its control. */
@Composable
private fun LimitRow(
    row: Limits.Row,
    enabled: Boolean,
    onChange: (JsonElement) -> Unit,
    onPickTime: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().padding(top = 12.dp)) {
        Text(
            row.title,
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
            modifier = Modifier.semantics { heading() },
        )
        Text(row.words, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        if (row.note.isNotBlank()) {
            Text(row.note, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Gap(4)
        when {
            // A fixed set: the choices as small chips. The one in force says so.
            row.kind == "int" && row.choices.isNotEmpty() -> Row(
                verticalAlignment = Alignment.CenterVertically,
            ) {
                row.choices.forEach { c ->
                    Quiet(
                        choiceLabel(row, c),
                        modifier = Modifier.semantics { contentDescription = Limits.choiceWords(row, c) },
                        enabled = enabled && c != row.number,
                        onClick = { onChange(JsonPrimitive(c)) },
                    )
                }
            }
            // A number with no fixed set: down, the value, up.
            row.kind == "int" -> Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Quiet(
                        "−",
                        modifier = Modifier.semantics { contentDescription = Limits.downWords(row) },
                        enabled = enabled && row.down != null,
                        onClick = { row.down?.let { onChange(JsonPrimitive(it)) } },
                    )
                    Text(
                        row.words,
                        style = MaterialTheme.typography.titleSmall,
                        color = chrome.textHi,
                        modifier = Modifier.padding(horizontal = 10.dp),
                    )
                    Quiet(
                        "+",
                        modifier = Modifier.semantics { contentDescription = Limits.upWords(row) },
                        enabled = enabled && row.up != null,
                        onClick = { row.up?.let { onChange(JsonPrimitive(it)) } },
                    )
                }
                val range = Limits.rangeLine(row)
                if (range.isNotBlank()) {
                    Text(range, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
            // A clock time: the value is already above, so the control is the
            // button that opens the app's own picker. While quiet hours are off
            // the PC says the hour decides nothing, and the button is not
            // offered - a control that changes nothing is worse than none.
            row.isTime -> Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (!row.quietOn) {
                    Text(
                        Limits.TIME_QUIET_OFF,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                } else {
                    Quiet(
                        Limits.CHANGE_TIME,
                        modifier = Modifier.semantics { contentDescription = Limits.timeWords(row) },
                        enabled = enabled,
                        onClick = onPickTime,
                    )
                }
            }
            // On or off: the app's own switch, with its words for TalkBack.
            else -> Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    if (row.on) "On" else "Off",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                    modifier = Modifier.weight(1f),
                )
                Toggle(
                    checked = row.on,
                    onCheckedChange = { onChange(JsonPrimitive(it)) },
                    enabled = enabled,
                    modifier = Modifier.semantics { contentDescription = Limits.rowWords(row) },
                )
            }
        }
    }
}

/**
 * The app's own time picker for one clock-time row: Material's clock, started
 * where the value in force is, and a 24-hour face because the value the PC holds
 * and the owner reads is 24-hour ("22:00").
 *
 * The dialog hands back the same shape the PC takes, "HH:MM", through
 * [Limits.validTime] - so a time can never leave this phone in a shape the PC
 * would refuse, and it is never turned into a number of minutes anywhere.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TimeRowDialog(
    row: Limits.Row,
    onDismiss: () -> Unit,
    onChosen: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    val (hour, minute) = Limits.hourMinute(row.clock.orEmpty())
    val state = rememberTimePickerState(initialHour = hour, initialMinute = minute, is24Hour = true)
    Dialog(onDismissRequest = onDismiss) {
        Plate {
            Text(row.title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Gap(8)
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                TimePicker(state = state)
            }
            Gap(10)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Quiet("Cancel", onClick = onDismiss)
                Gap(8)
                Quiet(
                    "Use this time",
                    onClick = {
                        val text = Limits.validTime("%02d:%02d".format(state.hour, state.minute))
                        if (text != null) onChosen(text)
                    },
                )
            }
        }
    }
}

/** A chip's own label: the number and, when the PC gave one, its unit. */
private fun choiceLabel(row: Limits.Row, choice: Long): String =
    if (row.unit.isBlank()) "$choice" else "$choice ${row.unit}"
