package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Schedule
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Coming up" on Mind ([Schedule], the owner's decisions of 2026-09-25):
 * timers counting down, alarms, reminders, the repeating ones with how often
 * and when next, and the to-do list - the desktop's Brain -> Work -> Coming
 * up, in the same words.
 *
 * Each row has its own Pause / Resume / Delete (a to-do item: Done /
 * Delete), ONE job per tap, asking nothing first and raising no card - none
 * of them can make Jarvis do more - and held while the link is down or
 * stale ([JarvisRuntime.scheduleAct]). There is no "delete all". A to-do
 * item can be added here, one at a time; timers and reminders are set by
 * saying or typing them to Jarvis.
 *
 * Read from the PC when Mind shows it, on Refresh, after every change, and
 * on every `schedule` event ([JarvisRuntime.scheduleTick]). A running timer
 * counts down once a second from what the PC last said. Nothing of it is
 * kept on the phone.
 *
 * "Hide memory lists and chat history" (Security) hides the words - a
 * reminder's and a to-do item's are the owner's own - but not the times, so
 * a timer still counts down; Show brings the words back.
 *
 * Under the to-do list, the standby schedule ([Schedule.STANDBY_TITLE]):
 * Standby - the same one as the buttons under Doing - every day from one
 * time to another. Two times and Set up, which asks the PC; the PC raises
 * ONE approval card, because it repeats ([JarvisRuntime.addStandbySchedule],
 * held on a stale link). Once there is one, it is a row in the list above
 * (Pause, Delete) and the times are not offered again - the desktop's
 * Brain -> Work -> Coming up does the same.
 */
@Composable
internal fun ComingUpSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.scheduleTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Schedule.View?>(null) }
    var readAt by remember { mutableLongStateOf(0L) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busyId by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    var todoText by remember { mutableStateOf("") }
    var adding by remember { mutableStateOf(false) }
    var standbyStart by remember { mutableStateOf(Schedule.STANDBY_DEFAULT_START) }
    var standbyEnd by remember { mutableStateOf(Schedule.STANDBY_DEFAULT_END) }
    var settingUp by remember { mutableStateOf(false) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.schedule()) {
            is ApiResult.Ok -> {
                val v = Schedule.parse(r.value)
                if (v == null) {
                    missing = true
                } else {
                    view = v
                    readAt = System.currentTimeMillis()
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Schedule.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }
    // A running timer counts down here, once a second, from what the PC said.
    val ticking = Schedule.anyTicking(view)
    LaunchedEffect(ticking) {
        while (ticking) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }

    fun act(job: Schedule.Job, action: String) {
        busyId = job.id
        said = null
        scope.launch {
            try {
                val (_, sentence) = JarvisRuntime.scheduleAct(job.id, action)
                said = sentence
            } finally {
                busyId = null
            }
        }
    }

    Section(Schedule.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Schedule.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Text(Schedule.PC_IS_THE_CLOCK, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = view?.let { if (privateHidden) Schedule.hide(it) else it }
            val err = readError
            when {
                missing -> Text(Schedule.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read Coming up: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (err != null) {
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (privateHidden) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Words hidden. Tap Show and confirm it is you.",
                                style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                                modifier = Modifier.weight(1f))
                            Quiet(if (showPrivateBusy) "Checking…" else "Show",
                                enabled = !showPrivateBusy, onClick = onShowPrivate)
                        }
                    }
                    if (shown.jobs.isEmpty()) {
                        Gap(4)
                        Text(Schedule.EMPTY_JOBS, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    shown.jobs.forEach { ScheduleRow(it, now - readAt, canAct && busyId == null) { a -> act(it, a) } }
                    Gap(14)
                    // "Tell me when" - set up by saying or typing it (one card
                    // on the PC); its rows are in the list above.
                    Text(Schedule.TELLME_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    Text(Schedule.TELLME_HINT, style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo)
                    Gap(14)
                    Text(Schedule.TODO_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    if (shown.todo.isEmpty()) {
                        Gap(4)
                        Text(Schedule.EMPTY_TODO, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    shown.todo.forEach { ScheduleRow(it, now - readAt, canAct && busyId == null) { a -> act(it, a) } }
                    Gap(8)
                    val add: () -> Unit = {
                        if (todoText.isNotBlank() && canAct && !adding) {
                            adding = true
                            said = null
                            scope.launch {
                                try {
                                    val (changed, sentence) = JarvisRuntime.addTodo(todoText)
                                    if (changed) todoText = ""
                                    said = sentence
                                } finally {
                                    adding = false
                                }
                            }
                        }
                    }
                    TextInput(
                        value = todoText,
                        onValueChange = { todoText = it.take(Schedule.MAX_TEXT) },
                        placeholder = Schedule.ADD_HINT,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { add() }),
                    )
                    Quiet(
                        if (adding) "Adding…" else Schedule.ADD,
                        enabled = canAct && !adding && todoText.isNotBlank(),
                        onClick = { add() },
                    )
                    Gap(14)
                    Text(Schedule.STANDBY_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    Text(Schedule.STANDBY_DETAIL, style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo)
                    Gap(6)
                    if (Schedule.standbyOf(shown) != null) {
                        Text(Schedule.STANDBY_IS_SET, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    } else {
                        val times = Schedule.standbyTimes(standbyStart, standbyEnd)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextInput(
                                value = standbyStart,
                                onValueChange = { standbyStart = it.take(5) },
                                label = Schedule.STANDBY_START_LABEL,
                                modifier = Modifier.weight(1f),
                                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                            )
                            TextInput(
                                value = standbyEnd,
                                onValueChange = { standbyEnd = it.take(5) },
                                label = Schedule.STANDBY_END_LABEL,
                                modifier = Modifier.weight(1f),
                                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            )
                        }
                        if (times == null) {
                            Text(Schedule.STANDBY_BAD_TIMES, style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk)
                        }
                        Quiet(
                            if (settingUp) "Asking…" else Schedule.STANDBY_ADD,
                            enabled = canAct && !settingUp && times != null,
                            onClick = {
                                if (canAct && !settingUp && times != null) {
                                    settingUp = true
                                    said = null
                                    scope.launch {
                                        try {
                                            val (_, sentence) =
                                                JarvisRuntime.addStandbySchedule(standbyStart, standbyEnd)
                                            said = sentence
                                        } finally {
                                            settingUp = false
                                        }
                                    }
                                }
                            },
                        )
                    }
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && shown != null && !canAct) {
                Text(
                    "Not connected to the desktop, so changes wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** One job: its kind, its title, its lines, and its own buttons - ONE job per tap. */
@Composable
private fun ScheduleRow(job: Schedule.Job, sinceMs: Long, enabled: Boolean, onAct: (String) -> Unit) {
    val chrome = LocalChrome.current
    Gap(10)
    Column(Modifier.fillMaxWidth()) {
        Text(
            Schedule.tagOf(job),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Text(Schedule.titleOf(job), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        Schedule.metaOf(job, sinceMs).forEach {
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Schedule.actionsOf(job).forEach { action ->
                Quiet(
                    Schedule.labelOf(action),
                    color = if (action == "delete") chrome.badInk else null,
                    enabled = enabled,
                    onClick = { onAct(action) },
                )
            }
        }
    }
}
