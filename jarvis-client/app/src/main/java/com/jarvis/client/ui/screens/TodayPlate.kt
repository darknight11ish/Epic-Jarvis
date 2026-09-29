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
import com.jarvis.client.net.Schedule
import com.jarvis.client.net.Today
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Today" on Brain ([Today], the owner's choice of 2026-09-28) - the
 * desktop's Brain -> Work -> Today, in the same words, just above Coming up.
 *
 * The owner's own cards that show today (with Delete, ONE per tap), those
 * later today, and the parts of the latest briefing made today (the weather,
 * the calendar, new email, what is still to come). Nothing new is read for
 * it: the same two reads Coming up and Morning briefing make, again when
 * either changes ([JarvisRuntime.scheduleTick], [JarvisRuntime.briefingTick]).
 * A small form adds one card - the words, a time and the days - with no
 * approval card; it and Delete are held on a stale link. "Hide memory lists
 * and chat history" hides the words and the briefing's lines; the times and
 * counts stay.
 */
@Composable
internal fun TodaySection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.scheduleTick.collectAsState()
    val briefTick by JarvisRuntime.briefingTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var schedule by remember { mutableStateOf<Schedule.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var brief by remember { mutableStateOf<Briefing.View?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var text by remember { mutableStateOf("") }
    var at by remember { mutableStateOf("07:00") }
    var days by remember { mutableStateOf(setOf(0, 1, 2, 3, 4)) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.schedule()) {
            is ApiResult.Ok -> {
                val v = Schedule.parse(r.value)
                if (v == null) missing = true else {
                    schedule = v
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
    LaunchedEffect(reads, briefTick) {
        // A PC without the briefing simply shows no briefing part here.
        when (val r = JarvisRuntime.briefing()) {
            is ApiResult.Ok -> brief = Briefing.parse(r.value)
            is ApiResult.Failed -> Unit
        }
    }

    fun delete(card: Today.Card) {
        busy = true
        said = null
        scope.launch {
            try {
                said = JarvisRuntime.scheduleAct(card.id, "delete").second
            } finally {
                busy = false
            }
        }
    }

    fun add() {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                val (changed, sentence) = JarvisRuntime.addTodayCard(text, at, days)
                if (changed) text = ""
                said = sentence
            } finally {
                busy = false
            }
        }
    }

    Section(Today.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Today.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val shown = schedule?.let { if (privateHidden) Schedule.hide(it) else it }
            val err = readError
            when {
                missing -> Text(Today.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read Today: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    val (showing, later) = Today.todayCards(Today.cardsOf(shown))
                    if (showing.isEmpty()) {
                        Text(Today.EMPTY_CARDS, style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid)
                    }
                    showing.forEach { CardRow(it, canAct && !busy) { delete(it) } }
                    if (later.isNotEmpty()) {
                        Gap(10)
                        Text(Today.LATER_TITLE, style = MaterialTheme.typography.labelMedium,
                            color = chrome.textMid)
                        later.forEach { CardRow(it, canAct && !busy) { delete(it) } }
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
                }
            }

            // ---- The briefing's own parts, from the latest one made today ----
            val bv = brief?.let { if (privateHidden) Briefing.hide(it) else it }
            if (bv != null) {
                Gap(12)
                Text(Today.FROM_BRIEFING, style = MaterialTheme.typography.labelMedium,
                    color = chrome.textMid)
                val parts = Today.briefingCards(bv)
                if (parts == null) {
                    Text(Today.NO_BRIEFING_TODAY, style = MaterialTheme.typography.bodySmall,
                        color = chrome.textMid)
                } else {
                    parts.forEach { s ->
                        Gap(8)
                        Text(s.title, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Text(s.summary, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                        s.items.forEach {
                            Text("- $it", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                    }
                }
            }

            // ---- Add a card: the words, a time, the days. No card. ----
            if (!missing) {
                Gap(14)
                Text(Today.ADD_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                TextInput(
                    value = text,
                    onValueChange = { text = it.take(Today.MAX_TEXT) },
                    placeholder = Today.TEXT_PLACEHOLDER,
                )
                TextInput(
                    value = at,
                    onValueChange = { at = it.take(5) },
                    label = Today.TIME_LABEL + " (24-hour, like 07:00)",
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                )
                Text(Today.DAYS_LABEL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Column(Modifier.fillMaxWidth()) {
                    Today.DAY_SHORT.chunked(4).forEachIndexed { row, names ->
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            names.forEachIndexed { i, name ->
                                val day = row * 4 + i
                                val on = day in days
                                // "(on)" as well as the colour: not by colour alone.
                                Quiet(if (on) "$name (on)" else name,
                                    color = if (on) chrome.okInk else chrome.textLo,
                                    onClick = { days = if (on) days - day else days + day })
                            }
                        }
                    }
                }
                Quiet(if (busy) "Adding…" else Today.ADD_LABEL, enabled = canAct && !busy,
                    onClick = { add() })
                Text(Today.HINT, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && !canAct) {
                Text(
                    "Not connected to the desktop, so adding and deleting wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/** One card: its tag, its words, from when, and Delete - ONE card per tap. */
@Composable
private fun CardRow(card: Today.Card, enabled: Boolean, onDelete: () -> Unit) {
    val chrome = LocalChrome.current
    Gap(10)
    Column(Modifier.fillMaxWidth()) {
        Text(Today.TAG, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Text(Today.cardTitle(card), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        Today.cardMeta(card).takeIf { it.isNotEmpty() }?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Quiet(Today.DELETE_LABEL, color = chrome.badInk, enabled = enabled, onClick = onDelete)
    }
}
