package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.layout.fillMaxWidth
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Limits
import com.jarvis.client.net.NotifyRows
import com.jarvis.client.net.PhoneNotifications
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement

/**
 * The desktop's "Notifications" card, on the phone ([NotifyRows] carries every
 * word and the reason for each one).
 *
 * WHERE IT SITS, AND WHY THERE. It is drawn inside Settings' one
 * "Notifications from Jarvis" row, directly under that row's own paragraph -
 * which ends "Which kinds your PC sends at all is the PC's own Notifications
 * card." This is that card, so the two sentences and the card itself sit
 * together: the row above says what Android decides on this phone, and this
 * plate changes what the PC sends.
 *
 * WHAT EVERY CONTROL IS WIRED TO. The rows and their values come from
 * `GET /api/limits` (`JarvisRuntime.limits`), and every change goes to
 * `POST /api/limits/settings` through `JarvisRuntime.setLimit` - the same two
 * routes the desktop's own card now reads and writes
 * (`jarvis-desktop/src/notifications-prefs.js`). The switches, the steps and
 * the clock are [LimitRow]/[TimeRowDialog] from LimitsPlate.kt, not copies of
 * them, so a change to a control cannot reach one screen and miss the other.
 *
 * WHAT IT WILL NOT PRETEND. The PC decides what a change means and its own
 * answer is the sentence shown under the list; a 2xx can mean "a card is
 * waiting on the PC", never "it is done" ([Limits.answer]). Nothing here is
 * written on the phone: these are the PC's settings, and the rows say so in the
 * PC's own words ("(on your PC)").
 *
 * The one control that is this phone's own is the Test button, because a phone
 * cannot make Windows show a toast - [NotifyRows.TEST_LINE] says exactly that,
 * and the same words the desktop uses on its own button.
 */
@Composable
internal fun PcNotifySection(canAct: Boolean) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var rows by remember { mutableStateOf<List<Limits.Row>?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    // The answer belongs to the row it was asked for, and is drawn under that
    // row's own control - the rule the limits plate follows (2026-10-10): the
    // PC's sentence, which row it was about, and whether anything was written
    // at all. A card long enough to scroll past a row is exactly why it is not
    // drawn once for the whole card.
    var said by remember { mutableStateOf<String?>(null) }
    var saidFor by remember { mutableStateOf<String?>(null) }
    var saidFailed by remember { mutableStateOf(false) }
    /** The key of the clock row whose picker is open, if any. */
    var picking by remember { mutableStateOf<String?>(null) }
    /** What really happened last time "Send test notification" was pressed. */
    var testPosted by remember { mutableStateOf<Boolean?>(null) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.limits()) {
            is ApiResult.Ok -> {
                rows = NotifyRows.rows(r.value)
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
        saidFor = null
        saidFailed = false
        scope.launch {
            try {
                // Both halves, as the limits plate takes them: the PC's
                // sentence, and whether anything was written. A save that did
                // not happen must not read as one that had.
                val a = JarvisRuntime.setLimit(key, value)
                said = a.sentence
                saidFor = key
                saidFailed = !a.changed
            } finally {
                busy = false
                // Re-read whatever the answer was, the same rule the limits
                // plate follows: a change the PC applied is there, and one
                // still waiting as a card on the PC is not.
                reads += 1
            }
        }
    }

    Section(NotifyRows.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(NotifyRows.NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(4)
            Text(NotifyRows.LINE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(8)
            val v = rows
            val err = readError
            when {
                missing -> Text(
                    Limits.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                v == null -> Text(
                    if (err != null) NotifyRows.readFailed(err) else Limits.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                // The route answered without these seven rows: an older table on
                // the PC, said as a fact about the PC rather than drawn as an
                // empty card.
                v.isEmpty() -> Text(
                    NotifyRows.NO_ROWS,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                else -> {
                    SubHead(NotifyRows.SUBHEAD_KINDS)
                    NotifyRows.kindRows(v).forEach { r ->
                        LimitRow(
                            row = r,
                            enabled = canAct && !busy,
                            said = if (saidFor == r.key) said else null,
                            saidFailed = saidFailed,
                            onChange = { value -> change(r.key, value) },
                            onPickTime = { picking = r.key },
                        )
                    }
                    SubHead(NotifyRows.SUBHEAD_QUIET)
                    NotifyRows.quietRows(v).forEach { r ->
                        LimitRow(
                            row = r,
                            enabled = canAct && !busy,
                            said = if (saidFor == r.key) said else null,
                            saidFailed = saidFailed,
                            onChange = { value -> change(r.key, value) },
                            onPickTime = { picking = r.key },
                        )
                    }
                }
            }

            SubHead(NotifyRows.SUBHEAD_TEST)
            Text(NotifyRows.TEST_LINE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            Secondary(
                NotifyRows.TEST_LABEL,
                modifier = Modifier.fillMaxWidth(),
                onClick = {
                    // The phone's own alert, on the phone's own schedule
                    // channel: the same post the moved control always used, and
                    // its real answer is what the line below reports - never a
                    // flag the tap set by itself (Android audit 2026-10-08).
                    testPosted = com.jarvis.client.service.ScheduleNotifier.post(
                        context,
                        jobId = "test-job",
                        kind = "reminder",
                        title = "Jarvis test notification",
                        text = "This is a test notification from Jarvis. Reminders and channels " +
                            "are working.",
                        lockScreen = "Jarvis: test notification",
                    )
                },
            )
            testPosted?.let { posted ->
                Gap(4)
                Text(
                    PhoneNotifications.testWords(posted),
                    style = MaterialTheme.typography.labelSmall,
                    // Green only for a notification really posted; a refusal is
                    // never dressed as success.
                    color = if (posted) chrome.okInk else chrome.badInk,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
    }

    // Outside the card, and only for the row whose button was tapped: opening a
    // clock is not a change, and nothing is sent until "Use this time" is.
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

/** One of the desktop card's own subheadings. */
@Composable
private fun SubHead(text: String) {
    Gap(12)
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = LocalChrome.current.textHi,
        modifier = Modifier.semantics { heading() },
    )
    Gap(2)
}
