package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Briefing
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Morning briefing" on Mind ([Briefing], the owner's decisions of
 * 2026-09-25) - the desktop's Brain -> Work -> Morning briefing AND its
 * Settings -> Morning briefing, in the same words: on the phone, settings for
 * a PC feature live on Mind, like the second card's switches.
 *
 * The latest briefing, put together on the PC without the AI model, section
 * by section; "Brief me now" (a read - not held on a stale link); the
 * briefing jobs with one Stop each (ONE per tap, held on a stale link); and
 * setting one up that repeats - every day, every weekday, or chosen days, at
 * a time - which raises the PC's ONE approval card listing the next three
 * times ([JarvisRuntime.setBriefing], held on a stale link). There is no
 * "stop all". And "Show who new emails are from" ([Briefing.SENDERS_LABEL],
 * on by default): OFF at once, ON through ONE approval card on the PC, held
 * on a stale link ([JarvisRuntime.setBriefingSenders]).
 *
 * "What did I miss?" (2026-09-25, [Briefing.MISSED_LABEL]): the same builder
 * on the PC, since the owner last talked to Jarvis on either app - a read,
 * like "Brief me now", so not held on a stale link. Shown in place of the
 * briefing until the next read; the PC keeps nothing of it.
 *
 * Read when Mind shows it, on Refresh, after every change, and on every
 * `schedule` event about a briefing ([JarvisRuntime.briefingTick]). Nothing
 * of it is kept on the phone. "Hide memory lists and chat history" hides its
 * lines; the counts stay, and Show brings them back.
 */
@Composable
internal fun BriefingSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.briefingTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Briefing.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var asking by remember { mutableStateOf(false) }
    var missedAsking by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var sendersBusy by remember { mutableStateOf(false) }
    var sendersSaid by remember { mutableStateOf<String?>(null) }
    var every by remember { mutableStateOf("weekday") }
    var at by remember { mutableStateOf("07:00") }
    var days by remember { mutableStateOf(setOf(0, 1, 2, 3, 4)) }

    // A card answered or raised - on either app - may have changed "Show who
    // new emails are from" (its ON waits for one), so the queue changing
    // reads it again, as the desktop's Settings does (onQueue).
    val queue by JarvisRuntime.pending.collectAsState()
    val queueKey = queue.map { it.id }

    LaunchedEffect(reads, tick, queueKey) {
        when (val r = JarvisRuntime.briefing()) {
            is ApiResult.Ok -> {
                val v = Briefing.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Briefing.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    fun briefNow() {
        if (asking) return
        asking = true
        said = null
        scope.launch {
            try {
                when (val r = JarvisRuntime.briefingNow()) {
                    is ApiResult.Ok -> Briefing.parse(r.value)?.let { view = it }
                    is ApiResult.Failed -> said = "Couldn't put one together: " + JarvisRuntime.noticeFor(r.error)
                }
            } finally {
                asking = false
            }
        }
    }

    fun whatDidIMiss() {
        if (asking) return
        asking = true
        missedAsking = true
        said = null
        scope.launch {
            try {
                when (val r = JarvisRuntime.briefingMissed()) {
                    is ApiResult.Ok -> {
                        val v = Briefing.readMissed(r.value)
                        if (v == null) {
                            said = Briefing.MISSED_MISSING
                        } else {
                            // Keep the setups this plate already read.
                            view = v.copy(setups = view?.setups ?: v.setups, sources = view?.sources ?: v.sources,
                                senders = view?.senders ?: v.senders)
                        }
                    }
                    is ApiResult.Failed -> said = "Couldn't look: " + JarvisRuntime.noticeFor(r.error)
                }
            } finally {
                asking = false
                missedAsking = false
            }
        }
    }

    Section(Briefing.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Briefing.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = view?.let { if (privateHidden) Briefing.hide(it) else it }
            val err = readError
            when {
                missing -> Text(Briefing.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read the briefing: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (shown.building || (asking && !missedAsking)) {
                        Text(Briefing.BUILDING, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid, modifier = Modifier.liveStatus())
                    }
                    val b = shown.briefing
                    if (b == null) {
                        if (!shown.building && !asking) {
                            Text(Briefing.EMPTY, style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid)
                        }
                    } else {
                        Text(b.heading, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        Briefing.lateLine(b).takeIf { it.isNotEmpty() }?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                        }
                        b.sections.forEach { s ->
                            Gap(8)
                            Text(s.title, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                            Text(s.summary, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                            s.items.forEach {
                                Text("- $it", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                            }
                        }
                        Gap(8)
                        val isMissed = b.source == "missed"
                        // "What did I miss?" fetches nothing from the internet.
                        if (!isMissed) {
                            Text(Briefing.OUTSIDE_LINE, style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo)
                        }
                        b.notIncluded.forEach {
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                        if (privateHidden) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("Lines hidden. Tap Show and confirm it is you.",
                                    style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                                    modifier = Modifier.weight(1f))
                                Quiet(if (showPrivateBusy) "Checking…" else "Show",
                                    enabled = !showPrivateBusy, onClick = onShowPrivate)
                            }
                        }
                        Text(if (isMissed) Briefing.MISSED_DETAIL else Briefing.KEPT,
                            style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    // Reads: offered on a stale link too, like every read.
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Quiet(if (asking && !missedAsking) Briefing.NOW_BUSY else Briefing.NOW_LABEL,
                            enabled = !asking, onClick = { briefNow() })
                        Quiet(if (missedAsking) Briefing.MISSED_BUSY else Briefing.MISSED_LABEL,
                            enabled = !asking, onClick = { whatDidIMiss() })
                    }

                    // ---- When it arrives (the desktop's Settings) ----
                    Gap(14)
                    Text(Briefing.SETUP_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    Text(Briefing.SETUP_DETAIL, style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo)
                    if (shown.setups.isEmpty()) {
                        Text(Briefing.SETUP_NONE, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    shown.setups.forEach { job ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(Briefing.setupLine(job), style = MaterialTheme.typography.bodySmall,
                                color = chrome.textHi, modifier = Modifier.weight(1f))
                            Quiet(
                                Briefing.STOP_LABEL,
                                color = chrome.badInk,
                                enabled = canAct && !busy,
                                onClick = {
                                    busy = true
                                    said = null
                                    scope.launch {
                                        try {
                                            said = JarvisRuntime.stopBriefing(job.id).second
                                        } finally {
                                            busy = false
                                            reads += 1
                                        }
                                    }
                                },
                            )
                        }
                    }
                    Gap(8)
                    // One per line: "Weekdays (Monday to Friday)" does not fit
                    // beside the others on a narrow phone.
                    Column(Modifier.fillMaxWidth()) {
                        Briefing.EVERY.forEach { (id, label) ->
                            Quiet(if (every == id) "$label (chosen)" else label,
                                color = if (every == id) chrome.okInk else chrome.textMid,
                                onClick = { every = id })
                        }
                    }
                    if (every == "week") {
                        Column(Modifier.fillMaxWidth()) {
                            Briefing.DAY_NAMES.chunked(2).forEachIndexed { row, names ->
                                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                                    names.forEachIndexed { i, name ->
                                        val day = row * 2 + i
                                        val on = day in days
                                        // "(on)" as well as the colour: not by colour alone.
                                        Quiet(if (on) "$name (on)" else name,
                                            color = if (on) chrome.okInk else chrome.textLo,
                                            onClick = { days = if (on) days - day else days + day })
                                    }
                                }
                            }
                        }
                    }
                    TextInput(
                        value = at,
                        onValueChange = { at = it.take(5) },
                        label = "Time (24-hour, like 07:00 or 0700)",
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    )
                    Quiet(
                        if (busy) "Asking…" else Briefing.SET_LABEL,
                        enabled = canAct && !busy,
                        onClick = {
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    said = JarvisRuntime.setBriefing(every, at, days).second
                                } finally {
                                    busy = false
                                    reads += 1
                                }
                            }
                        },
                    )
                    Gap(10)
                    Text(Briefing.READS_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    shown.sources.forEach {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    // "Show who new emails are from": OFF at once, never held;
                    // ON is ONE approval card on the PC, held on a stale link.
                    val senders = Briefing.sendersView(shown.senders, canAct)
                    if (senders.show) {
                        Gap(6)
                        SwitchRow(
                            title = Briefing.SENDERS_LABEL,
                            detail = Briefing.SENDERS_DETAIL,
                            checked = senders.checked,
                            enabled = !sendersBusy && senders.canChange,
                            onChange = { want ->
                                sendersBusy = true
                                sendersSaid = null
                                scope.launch {
                                    try {
                                        sendersSaid = JarvisRuntime.setBriefingSenders(want)
                                    } finally {
                                        sendersBusy = false
                                        reads += 1
                                    }
                                }
                            },
                        )
                    }
                    senders.lines.forEach {
                        Text(it, style = MaterialTheme.typography.labelSmall,
                            color = if (it == Briefing.SENDERS_WAITING) chrome.warnInk else chrome.textMid)
                    }
                    (if (sendersBusy) "Asking your PC…" else sendersSaid)?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                            modifier = Modifier.liveStatus())
                    }
                    Text(Briefing.SPOKEN, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && view != null && !canAct) {
                Text(
                    "Not connected to the desktop, so setting up and stopping wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}
