package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.AutoLearn
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

/**
 * The two automatic-learning switches ([AutoLearn], docs/JARVIS-API.md
 * section 19), drawn inside "What Jarvis remembers" under the learning
 * switch, where the desktop puts them too (Brain -> Memory).
 *
 * Turning either ON raises one approval card on the PC and reads "Waiting
 * for your approval" while that card is in the queue - found by its action,
 * so a card raised on the desktop counts too. ON is greyed while the link is
 * down or stale, and the runtime refuses it again ([JarvisRuntime.setAutoLearn]).
 * OFF always goes. Not while a card is already up, or before the PC has said
 * which way a switch is.
 *
 * @param learningOn the background learning switch above these, which
 *   "Learn automatically" depends on.
 * @param refresh goes up when the plate's own Refresh is pressed.
 */
@Composable
internal fun AutoLearnSwitches(canAct: Boolean, learningOn: Boolean?, refresh: Int) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf<AutoLearn.Status?>(null) }
    var unsupported by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf<AutoLearn.Which?>(null) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val actions = queue.map { it.action }
    val autoCard = AutoLearn.cardWaiting(actions, AutoLearn.Which.AUTO)
    val sensitiveCard = AutoLearn.cardWaiting(actions, AutoLearn.Which.SENSITIVE)
    // A card leaving the queue (approved, denied or expired) reads the
    // switches again, so the lines say what really happened.
    var seen by remember { mutableStateOf(false to false) }
    LaunchedEffect(autoCard, sensitiveCard) {
        val left = (seen.first && !autoCard) || (seen.second && !sensitiveCard)
        seen = autoCard to sensitiveCard
        if (left) reads += 1
    }
    LaunchedEffect(reads, refresh) {
        when (val r = JarvisRuntime.autoLearnSettings()) {
            is ApiResult.Ok -> {
                status = AutoLearn.status(r.value)
                unsupported = false
                readError = null
            }
            is ApiResult.Failed -> {
                // The list's answer carries the two switches too, so they can
                // still say which way they are.
                when (val l = JarvisRuntime.autoFacts(limit = 1)) {
                    is ApiResult.Ok -> {
                        status = AutoLearn.statusFromList(l.value)
                        unsupported = false
                        readError = null
                    }
                    is ApiResult.Failed -> {
                        unsupported = r.error == ApiError.NotFound && l.error == ApiError.NotFound
                        readError = if (unsupported) null else JarvisRuntime.noticeFor(r.error)
                    }
                }
            }
        }
    }

    if (unsupported) {
        Text(
            "Your PC's Jarvis does not have automatic learning yet.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        return
    }
    for (which in AutoLearn.Which.entries) {
        val cardInQueue = if (which == AutoLearn.Which.AUTO) autoCard else sensitiveCard
        val switch = AutoLearn.switchState(status, which, cardInQueue)
        Gap(8)
        SwitchRow(
            title = which.title,
            detail = which.under,
            checked = switch == AutoLearn.Switch.ON,
            enabled = busy == null && when (switch) {
                AutoLearn.Switch.ON -> true
                AutoLearn.Switch.OFF -> canAct
                AutoLearn.Switch.WAITING, AutoLearn.Switch.UNKNOWN -> false
            },
            onChange = { want ->
                busy = which
                said = null
                scope.launch {
                    try {
                        said = JarvisRuntime.setAutoLearn(which, want)
                    } finally {
                        busy = null
                        reads += 1
                    }
                }
            },
        )
        Text(
            if (busy == which) "Asking your PC…" else
                AutoLearn.stateLine(which, switch, learningOn, status?.auto),
            style = MaterialTheme.typography.bodySmall,
            color = if (switch == AutoLearn.Switch.WAITING) chrome.warnInk else chrome.textMid,
        )
        AutoLearn.lastLine(status?.last(which), switch)?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
    readError?.let {
        Text("Couldn't read these switches: $it", style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk)
    }
    said?.let {
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
}

/**
 * "Saved automatically" on Mind - every fact Jarvis saved without a card,
 * newest first, with "Load older", a small "said aloud" mark for voice, and
 * a Forget on each. Forget asks first (the desktop's Forget words), and is
 * held while the link is down or stale, like the desktop's.
 *
 * Read from the PC when Mind shows it, on Refresh, after a Forget, and on
 * every `memory_saved` event ([JarvisRuntime.autoTick]). Nothing of it is
 * kept on the phone.
 *
 * "Hide memory lists and chat history" (Security) replaces it with
 * [HiddenSection] until Show is confirmed, like Mind's other memory lists.
 */
@Composable
internal fun SavedAutomaticallySection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection(AutoLearn.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val zone = remember { ZoneId.systemDefault() }
    val today = LocalDate.now(zone)
    val tick by JarvisRuntime.autoTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var facts by remember { mutableStateOf<List<AutoLearn.Fact>?>(null) }
    var mayHaveOlder by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var loadingOlder by remember { mutableStateOf(false) }
    var confirmId by remember { mutableStateOf<Long?>(null) }
    var busyId by remember { mutableStateOf<Long?>(null) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.autoFacts()) {
            is ApiResult.Ok -> {
                val page = AutoLearn.page(r.value)
                facts = page.facts
                mayHaveOlder = page.mayHaveOlder
                readError = null
            }
            is ApiResult.Failed -> readError = AutoLearn.listFailure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
    }

    Section(AutoLearn.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            val shown = facts
            val err = readError
            when {
                shown == null -> Text(
                    if (err != null) "Couldn't read what was saved: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                shown.isEmpty() -> Text(AutoLearn.EMPTY, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
            }
            if (shown != null && err != null) {
                Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                    color = chrome.warnInk)
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!shown.isNullOrEmpty() && !canAct) {
                Text(
                    "Not connected to the desktop, so Forget waits until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
            shown.orEmpty().forEach { fact ->
                Gap(10)
                Column(Modifier.fillMaxWidth()) {
                    Text(fact.text, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(AutoLearn.rowLine(fact, zone, today), style = MaterialTheme.typography.labelSmall,
                            color = chrome.textLo)
                        if (fact.aloud) Pill(AutoLearn.VOICE_MARK)
                    }
                    if (confirmId == fact.id) {
                        Text(AutoLearn.FORGET_CONFIRM, style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Quiet(
                                "Yes, forget it",
                                color = chrome.badInk,
                                enabled = canAct && busyId == null,
                                onClick = {
                                    confirmId = null
                                    busyId = fact.id
                                    said = null
                                    scope.launch {
                                        try {
                                            val (gone, sentence) = JarvisRuntime.forgetAutoFact(fact.id)
                                            if (gone) facts = facts?.filterNot { it.id == fact.id }
                                            said = sentence
                                        } finally {
                                            busyId = null
                                        }
                                    }
                                },
                            )
                            Quiet("Keep it", onClick = { confirmId = null })
                        }
                    } else {
                        Quiet(
                            if (busyId == fact.id) "Forgetting…" else "Forget",
                            color = chrome.badInk,
                            enabled = canAct && busyId == null,
                            onClick = { confirmId = fact.id },
                        )
                    }
                }
            }
            if (shown != null && mayHaveOlder && shown.isNotEmpty()) {
                Gap(6)
                Quiet(
                    if (loadingOlder) "Loading…" else "Load older",
                    enabled = !loadingOlder,
                    onClick = {
                        val before = AutoLearn.olderThan(shown)
                        if (before == null) {
                            mayHaveOlder = false
                        } else {
                            loadingOlder = true
                            scope.launch {
                                try {
                                    when (val r = JarvisRuntime.autoFacts(before)) {
                                        is ApiResult.Ok -> {
                                            val page = AutoLearn.page(r.value)
                                            val had = facts.orEmpty()
                                            val next = AutoLearn.append(had, page.facts)
                                            facts = next
                                            // No progress means no more to load.
                                            mayHaveOlder = page.mayHaveOlder && next.size > had.size
                                            readError = null
                                        }
                                        is ApiResult.Failed -> readError =
                                            AutoLearn.listFailure(r.error) ?: JarvisRuntime.noticeFor(r.error)
                                    }
                                } finally {
                                    loadingOlder = false
                                }
                            }
                        }
                    },
                )
            }
        }
    }
}
