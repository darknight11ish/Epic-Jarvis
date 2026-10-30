package com.jarvis.client.ui.screens

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.fillMaxWidth
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Calendar
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Jarvis Calendar" on the phone's Settings screen (2026-10-29): the ONE switch
 * that turns the whole feature on or off, drawn from the PC's own answer.
 *
 * ON BY DEFAULT. The PC's store answers `"on": true` when it has never been
 * switched off (`calendar-settings.json` absent = on), so the owner gets a
 * calendar without asking for one, which is what "built into Jarvis" means.
 * Turning it OFF hides it in both apps and stops the widget updating; **nothing
 * is deleted**, and the line under the switch says so, because "off" reading as
 * "deleted" is the one thing this control must never imply.
 *
 * NO CARD EITHER WAY. Turning it back on is a preference the owner can change
 * back in one press, the same shape as the Anti-Slop filter and the briefing's
 * senders switch - so it is not held behind an approval, only behind a live
 * link (rule 4). A card that must be answered on the PC to turn your own
 * calendar back on would be friction with nothing behind it.
 *
 * THE WORDS ARE THE PC'S WHERE IT SPEAKS. The count under the switch comes from
 * the same `GET /api/calendar` the screen and the widget read - a number, never
 * a title, so this row can never leak an event onto a settings page that a
 * passer-by is looking at.
 */
@Composable
internal fun CalendarSettingsSection(
    /** The link is live and not stale: the switch is offered only when it is (rule 4). */
    canAct: Boolean,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.calendarTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Calendar.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.calendar(7)) {
            is ApiResult.Ok -> {
                val v = Calendar.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Calendar.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    Section(Calendar.TITLE) {
        Plate {
            val v = view
            when {
                missing -> Text(
                    Calendar.MISSING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                v == null -> Text(
                    readError?.let { "Couldn't read it: $it" } ?: "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (readError != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    SwitchRow(
                        title = Calendar.TITLE,
                        detail = Calendar.UNDER,
                        checked = v.on,
                        enabled = canAct && !busy,
                        onChange = { on ->
                            if (busy) return@SwitchRow
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    val (_, sentence) = JarvisRuntime.calendarSettings(on)
                                    said = sentence
                                } finally {
                                    busy = false
                                }
                            }
                        },
                    )
                    Text(
                        when {
                            // The PC said its store could not be read. That is not
                            // "you have no events", and this line must not say so.
                            !v.available -> v.why.ifEmpty {
                                "Your PC could not read the calendar's store just now. Nothing was changed."
                            }
                            // OFF: the promise is that nothing was deleted, so say
                            // how much is still there - a count, never a title.
                            !v.on -> if (v.saved > 0) {
                                "Off. Nothing was deleted - all ${v.saved} " +
                                    (if (v.saved == 1) "event is" else "events are") + " still there."
                            } else {
                                "Off. Nothing was deleted - the calendar was empty anyway."
                            }
                            0 == v.saved -> "No events saved yet - the calendar is empty and ready."
                            1 == v.saved -> "1 event saved, on your PC."
                            else -> "${v.saved} events saved, on your PC."
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            said?.let {
                Gap(4)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
            if (!canAct && !missing) {
                Gap(4)
                Text(
                    "Not connected to the desktop, so the switch waits until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            Gap(4)
            Quiet("Refresh", onClick = { reads += 1 })
        }
    }
}
