package com.jarvis.client.ui.screens

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.AppControl
import com.jarvis.client.data.AppControlStore
import com.jarvis.client.service.AppControlExecutor
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import com.jarvis.client.net.ScreenPlateText
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * "App control": the phone's half of the owner's 2026-10-19 decision ("enable
 * accessibility service with control by jarvis as an option in the android
 * app"), with an EMPTY allow-list until the owner adds an app.
 *
 * One place explains the whole thing and holds both switches that must agree:
 *  - this app's own option (saved on this phone, OFF by default);
 *  - Android's own Accessibility switch (read-only here - only Android can
 *    turn it on, and the button opens that exact screen);
 * and the one allow-list. Adding a bank-looking or password-manager app is
 * refused in words before anything is saved ([AppControlStore.add]).
 *
 * Every step still needs ONE approval card on the PC; this screen never
 * approves anything and never sends a plan of its own.
 */
@Composable
internal fun AppControlSection(stale: Boolean) {
    var reads by remember { mutableIntStateOf(0) }
    Section("App control", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            AppControlSwitch(refresh = reads)
            Gap(12)
            AndroidAccessibilityRow(refresh = reads)
            Gap(12)
            PcRouteRow(stale = stale, refresh = reads)
            Gap(4)
            AppControlAllowList()
            Gap(4)
            AppControlAskRow(stale = stale, refresh = reads)
            Gap(12)
            Text(
                AppControl.PLAN_LINE,
                style = MaterialTheme.typography.bodySmall,
                color = LocalChrome.current.textMid,
            )
        }
    }
}

@Composable
private fun AppControlSwitch(refresh: Int) {
    val context = LocalContext.current
    val store = remember { AppControlStore(context) }
    var on by remember { mutableStateOf(store.optionOn()) }
    LaunchedEffect(refresh) { on = store.optionOn() }
    SwitchRow(
        title = AppControl.OPTION_TITLE,
        detail = AppControl.OPTION_DETAIL,
        checked = on,
        onChange = { wanted ->
            // Saved on this phone only; turning it on asks the PC for nothing
            // and turning it off can only ever make Jarvis do less, so neither
            // needs a card. The PC still asks before every step.
            store.setOption(wanted)
            on = wanted
        },
    )
}

@Composable
private fun AndroidAccessibilityRow(refresh: Int) {
    val context = LocalContext.current
    val store = remember { AppControlStore(context) }
    var state by remember { mutableStateOf(store.androidState()) }
    LaunchedEffect(refresh) { state = store.androidState() }
    val chrome = LocalChrome.current
    Text(AppControl.ANDROID_TITLE, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
    Gap(4)
    Text(
        when (state) {
            AppControl.AndroidState.ON -> AppControl.ANDROID_ON
            AppControl.AndroidState.OFF -> AppControl.ANDROID_OFF
            AppControl.AndroidState.CANNOT_READ -> AppControl.ANDROID_UNKNOWN
        },
        style = MaterialTheme.typography.bodySmall,
        color = if (state == AppControl.AndroidState.ON) chrome.textMid else chrome.warnInk,
    )
    Gap(4)
    Text(
        AppControl.ANDROID_DETAIL,
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(8)
    Secondary(
        "Android accessibility settings",
        modifier = Modifier.fillMaxWidth(),
        onClick = { store.openAccessibilitySettings() },
    )
}

/** What the PC answered about its own route: no guess when it cannot be asked. */
private enum class PcRoute { CHECKING, READY, OLDER, UNREACHABLE }

@Composable
private fun PcRouteRow(stale: Boolean, refresh: Int) {
    val chrome = LocalChrome.current
    val route by produceState<PcRoute>(initialValue = PcRoute.CHECKING, refresh, stale) {
        if (stale) {
            value = PcRoute.UNREACHABLE
            return@produceState
        }
        value = try {
            // A probe that cannot act: an empty run id is unknown to the route,
            // so a PC that HAS app control answers its own "that run is not
            // here" sentence, and a PC without the routes answers a plain
            // 404 "not found". Only the PC's own sentence is positive evidence -
            // any other 404 is an OLDER backend (field test, 2026-10-20:
            // `{"error": "not found"}` must never show ROUTE_READY). Nothing is
            // read from the screen and no card can be raised by this.
            val (status, body) = JarvisRuntime.api.appControlStep(AppControl.probeBody())
            val error = runCatching {
                body?.get("error")?.jsonPrimitive?.contentOrNull
            }.getOrNull()
            when (AppControl.probeRoute(status, error)) {
                AppControl.ProbeRoute.READY -> PcRoute.READY
                AppControl.ProbeRoute.OLDER -> PcRoute.OLDER
                AppControl.ProbeRoute.UNREACHABLE -> PcRoute.UNREACHABLE
            }
        } catch (_: Exception) {
            PcRoute.UNREACHABLE
        }
    }
    when (route) {
        PcRoute.CHECKING -> Text(
            "Asking the PC...",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        PcRoute.READY -> Text(
            AppControl.ROUTE_READY,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        PcRoute.OLDER -> Text(
            AppControl.NO_ROUTE,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.warnInk,
        )
        PcRoute.UNREACHABLE -> Text(
            AppControl.NO_ANSWER,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.warnInk,
        )
    }
}

/**
 * The owner's OWN words, sent to the PC's local model: it proposes exactly ONE
 * step and raises ONE card. Nothing runs until the owner answers that card,
 * and after the step has run the next one needs this button pressed again.
 */
@Composable
private fun AppControlAskRow(stale: Boolean, refresh: Int) {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val store = remember { AppControlStore(context) }
    val scope = rememberCoroutineScope()
    var optionOn by remember { mutableStateOf(store.optionOn()) }
    var want by remember { mutableStateOf("") }
    var ask by remember { mutableStateOf(AppControl.AskState()) }
    val capability by produceState(
        initialValue = AppControl.PlanCapability.UNREACHABLE,
        refresh, stale, optionOn,
    ) {
        value = if (stale) {
            AppControl.PlanCapability.UNREACHABLE
        } else {
            runCatching {
                val (status, body) = JarvisRuntime.api.appControlPlan(AppControl.planProbeBody())
                AppControl.planCapability(status, body)
            }.getOrDefault(AppControl.PlanCapability.UNREACHABLE)
        }
    }
    LaunchedEffect(refresh) { optionOn = store.optionOn() }
    val allowedNow = AppControl.canAsk(capability, optionOn, ask.busy) && !stale

    Gap(12)
    Text("Ask Jarvis to act", style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
    Gap(4)
    when (capability) {
        AppControl.PlanCapability.OLDER -> {
            Text(AppControl.ASK_OLDER_PC, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        AppControl.PlanCapability.UNREACHABLE -> {
            Text(AppControl.NO_ANSWER, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        AppControl.PlanCapability.AVAILABLE -> {
            TextInput(
                value = want,
                onValueChange = { want = it.take(AppControl.WANT_MAX) },
                placeholder = AppControl.ASK_PLACEHOLDER,
                singleLine = false,
                maxLines = 2,
            )
            Gap(8)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Secondary(
                    ask.label,
                    modifier = Modifier.weight(1f),
                    enabled = allowedNow && want.isNotBlank(),
                    busy = ask.busy,
                    onClick = {
                        if (allowedNow && want.isNotBlank()) {
                            ask = ask.copy(phase = AppControl.AskPhase.ASKING, sentence = "")
                            val said = want
                            scope.launch {
                                val reply = AppControlExecutor.ask(context, said) { waiting ->
                                    ask = ask.copy(phase = AppControl.AskPhase.WAITING, sentence = waiting)
                                }
                                ask = when (reply) {
                                    is AppControlExecutor.Reply.Done ->
                                        AppControl.afterStep(ask.everPerformed, reply.sentence)
                                    is AppControlExecutor.Reply.Stopped ->
                                        ask.copy(phase = AppControl.AskPhase.IDLE, sentence = reply.sentence)
                                    is AppControlExecutor.Reply.Refused ->
                                        ask.copy(phase = AppControl.AskPhase.REFUSED, sentence = reply.sentence)
                                }
                                if (reply is AppControlExecutor.Reply.Done) want = ""
                            }
                        }
                    },
                )
                if (ask.busy) {
                    Quiet("Stop", modifier = Modifier.semantics {
                        contentDescription = "Stop Jarvis"
                    }, onClick = { AppControlExecutor.stop() })
                }
            }
            if (ask.sentence.isNotBlank()) {
                Gap(6)
                Text(
                    ask.sentence,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (ask.phase == AppControl.AskPhase.REFUSED) chrome.warnInk else chrome.textMid,
                )
            }
        }
    }
}

@Composable
private fun AppControlAllowList() {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val store = remember { AppControlStore(context) }
    var version by remember { mutableIntStateOf(0) }
    var allowed by remember { mutableStateOf<List<AppControl.AppEntry>>(emptyList()) }
    var picking by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(version) { allowed = store.entries() }

    Gap(12)
    Text(AppControl.ALLOW_TITLE, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
    Gap(4)
    Text(
        if (allowed.isEmpty()) AppControl.ALLOW_EMPTY else AppControl.ALLOW_ONE_AT_A_TIME,
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(8)
    if (allowed.isEmpty()) {
        Text(AppControl.NO_APPS_ADDED, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
    } else {
        allowed.forEach { entry ->
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text(
                    entry.label,
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
                Quiet(
                    AppControl.REMOVE,
                    modifier = Modifier.semantics {
                        contentDescription = ScreenPlateText.removeLabel(entry.label)
                    },
                    onClick = {
                        store.remove(entry.packageName)
                        version += 1
                    },
                )
            }
        }
    }
    Gap(8)
    Secondary(
        if (picking) AppControl.CLOSE_LIST else AppControl.ADD,
        modifier = Modifier.fillMaxWidth(),
        onClick = { picking = !picking; message = null; query = "" },
    )
    message?.let {
        Gap(6)
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }
    if (picking) {
        Gap(8)
        // Read off the main thread: it asks Android for every installed app and
        // each one's name, which on a phone with many apps froze the screen in
        // the notification list before it was done here (bug audit 2026-09-29).
        val loaded by produceState<List<com.jarvis.client.data.NotificationAllowListStore.InstalledApp>?>(
            initialValue = null, version,
        ) { value = withContext(Dispatchers.IO) { store.installedApps() } }
        val candidates = loaded
        if (candidates == null) {
            Text(AppControl.LOOKING, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        } else {
            val shown = candidates.filter { app -> allowed.none { it.packageName == app.packageName } }
            if (shown.isEmpty()) {
                Text(AppControl.NO_APPS, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            } else {
                TextInput(value = query, onValueChange = { query = it }, placeholder = AppControl.SEARCH)
                Gap(8)
                val filtered = ScreenPlateText.filterApps(shown, query, { it.label }, { it.packageName })
                if (filtered.isEmpty()) {
                    Text(AppControl.NO_MATCH, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                }
                LazyColumn(Modifier.fillMaxWidth().heightIn(max = 240.dp)) {
                    items(filtered, key = { it.packageName }) { app ->
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 48.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(
                                app.label,
                                style = MaterialTheme.typography.bodyMedium,
                                color = chrome.textHi,
                                modifier = Modifier.weight(1f),
                            )
                            Quiet(
                                "Add",
                                modifier = Modifier.semantics {
                                    contentDescription = ScreenPlateText.addLabel(app.label)
                                },
                                onClick = {
                                    val result = store.add(app.packageName)
                                    message = result.error
                                    if (result.error == null) {
                                        version += 1
                                        query = ""
                                    }
                                },
                            )
                        }
                    }
                }
            }
        }
    }
}
