package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Focus
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
 * "Focus session" on Mind ([Focus], the owner's decision of 2026-09-25) - the
 * desktop's Brain -> Work -> Focus session, in the same words.
 *
 * Off: minutes, an optional "on what", and Start. Running: the countdown
 * (counted down here once a second from what the PC last said), the PC's own
 * line ("24 minutes left - on target."), the drift count, and Pause / Resume,
 * +10 minutes and Stop - ONE thing per tap. After a session: its report card,
 * as the PC wrote it.
 *
 * Watching what is in front happens on the PC only, and this phone is never
 * told what was there - only whether the owner is on target, and counts.
 * "Lock on this" is not here: it is about the PC's screen (the desktop's
 * widget has it, and it can be said to Jarvis). Snooze and "I'm doing
 * research" are said or typed to Jarvis, from either app.
 *
 * Start, Resume and +10 minutes wait while the link is down or stale
 * ([JarvisRuntime.focusStart], [JarvisRuntime.focusAct]); Pause and Stop do
 * not - they only make Jarvis do less.
 */
@Composable
internal fun FocusSection(canAct: Boolean, privateHidden: Boolean = false) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.focusTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Focus.View?>(null) }
    var readAt by remember { mutableLongStateOf(0L) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var minutes by remember { mutableStateOf(Focus.DEFAULT_MINUTES.toString()) }
    var on by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.focus()) {
            is ApiResult.Ok -> {
                val v = Focus.parse(r.value)
                if (v == null) missing = true else {
                    view = v
                    readAt = System.currentTimeMillis()
                    now = readAt
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Focus.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }
    val ticking = view?.let { it.on && !it.paused } == true
    LaunchedEffect(ticking) {
        while (ticking) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }

    fun perform(block: suspend () -> Pair<Boolean, String>) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                said = block().second
            } finally {
                busy = false
            }
        }
    }

    Section(Focus.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Focus.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Text(Focus.PHONE_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            val err = readError
            when {
                missing -> Text(Focus.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read the focus session: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                v.on -> {
                    Text(
                        Focus.clock(Focus.leftNow(v, now - readAt)),
                        style = MaterialTheme.typography.headlineMedium,
                        color = if (v.drifting && !v.excused) chrome.warnInk else chrome.textHi,
                    )
                    if (v.intent.isNotEmpty()) {
                        // What it is on is the owner's own words, like a
                        // reminder's: hidden with the private lists.
                        Text(if (privateHidden) Focus.INTENT_HIDDEN else "On: ${v.intent}",
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Text(v.line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    Text(
                        if (v.drifts == 0) "No drifts so far." else
                            if (v.drifts == 1) "One drift so far." else "${v.drifts} drifts so far.",
                        style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    )
                    if (v.note.isNotEmpty()) {
                        Text(v.note, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Focus.actionsOf(v).forEach { action ->
                            val held = action in Focus.HELD_WHEN_STALE && !canAct
                            Quiet(
                                Focus.labelOf(action),
                                color = if (action == "stop") chrome.badInk else null,
                                enabled = !busy && !held,
                                onClick = { perform { JarvisRuntime.focusAct(action) } },
                            )
                        }
                    }
                }
                else -> {
                    val mins = Focus.minutesOf(minutes)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextInput(
                            value = minutes,
                            onValueChange = { minutes = it.filter(Char::isDigit).take(3) },
                            label = Focus.MINUTES_LABEL,
                            modifier = Modifier.weight(1f),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number,
                                imeAction = ImeAction.Next),
                        )
                        TextInput(
                            value = on,
                            onValueChange = { on = it.take(60) },
                            label = Focus.ON_LABEL,
                            modifier = Modifier.weight(2f),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        )
                    }
                    if (mins == null) {
                        Text(Focus.BAD_MINUTES, style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    Quiet(
                        if (busy) "Starting…" else Focus.START,
                        enabled = canAct && !busy && mins != null,
                        onClick = { if (mins != null) perform { JarvisRuntime.focusStart(mins, on) } },
                    )
                    v.report?.let { r ->
                        Gap(12)
                        Text(Focus.LAST_TITLE, style = MaterialTheme.typography.labelMedium,
                            color = chrome.textMid)
                        Text(r.title, style = MaterialTheme.typography.bodyMedium,
                            color = if (r.clean) chrome.okInk else chrome.textHi)
                        r.lines.forEach {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                    }
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && v != null && !canAct) {
                Text(
                    "Not connected to the desktop, so Start, Resume and +10 minutes wait until " +
                        "the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}
