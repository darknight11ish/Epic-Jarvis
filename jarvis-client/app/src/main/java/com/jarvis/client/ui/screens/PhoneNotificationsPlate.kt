package com.jarvis.client.ui.screens

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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.NotificationAllowList
import com.jarvis.client.data.NotificationAllowListStore
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.PhoneNotifications
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Reading phone notifications" ([PhoneNotifications], docs/JARVIS-API.md
 * §61; the owner's decision, CLAUDE.md 2026-09-26; built 2026-09-28): OFF
 * by default, ON is one approval card on the PC, OFF is instant - the same
 * shape as [WatchNotifySwitch] right above this section. This plate is the
 * ONE place this whole feature is explained, set up and reviewed:
 *   - the master switch (this route only; never sees a notification's text);
 *   - Android's own "Notification access" - explained in plain words BEFORE
 *     the button that opens that OS screen, because it is unusually broad;
 *   - the per-app allow list - empty by default, and the one place adding a
 *     banking or SMS/Messages app is refused outright, in words that say so.
 *
 * @param canAct the link is up and fresh: turning the switch ON waits for it.
 * @param notificationAccessGranted Android's own answer, re-read on resume.
 * @param onOpenNotificationAccess opens Android's "Notification access" screen.
 */
@Composable
internal fun PhoneNotificationsSwitch(canAct: Boolean, refresh: Int) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var enabled by remember { mutableStateOf<Boolean?>(null) }
    var why by remember { mutableStateOf<String?>(null) }
    var unsupported by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardWaiting = PhoneNotifications.cardWaiting(queue.map { it.action })
    var seen by remember { mutableStateOf(false) }
    LaunchedEffect(cardWaiting) {
        val left = seen && !cardWaiting
        seen = cardWaiting
        if (left) reads += 1
    }
    LaunchedEffect(reads, refresh) {
        when (val r = JarvisRuntime.phoneNotificationsSettings()) {
            is ApiResult.Ok -> {
                enabled = PhoneNotifications.enabled(r.value)
                why = PhoneNotifications.whyLine(r.value)
                unsupported = false
                readError = null
            }
            is ApiResult.Failed -> {
                unsupported = r.error == ApiError.NotFound
                readError = if (unsupported) null else JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    if (unsupported) {
        Text(
            "Your PC's Jarvis does not have the phone notifications setting yet.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        return
    }
    SwitchRow(
        title = "Let your phone read notifications",
        detail = "Off by default. Jarvis never sees a phone notification unless you turn " +
            "this on AND add at least one app below.",
        checked = enabled == true || cardWaiting,
        enabled = !busy && when {
            cardWaiting -> true
            enabled == true -> true
            enabled == false -> canAct
            else -> false
        },
        onChange = { want ->
            if (!(want && cardWaiting)) {
                busy = true
                said = null
                scope.launch {
                    try {
                        said = JarvisRuntime.setPhoneNotifications(want)
                    } finally {
                        busy = false
                        reads += 1
                    }
                }
            }
        },
    )
    Text(
        if (busy) "Asking your PC…" else if (cardWaiting) PhoneNotifications.waitingLine()
        else PhoneNotifications.stateLine(enabled),
        style = MaterialTheme.typography.bodySmall,
        color = if (cardWaiting) chrome.warnInk else chrome.textMid,
    )
    readError?.let {
        Text("Couldn't read this switch: $it", style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk)
    }
    why?.let {
        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
    }
    said?.let {
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
            modifier = Modifier.liveStatus())
    }
}

/**
 * Explained BEFORE the button that opens Android's "Notification access"
 * screen is ever shown, always - `Settings.ACTION_NOTIFICATION_LISTENER_
 * SETTINGS` is unusually broad (once granted, this app COULD read every
 * notification on the phone; the allow list below, and Jarvis's own switch
 * above, are what actually narrows that down to nothing until the owner
 * chooses otherwise).
 */
@Composable
private fun NotificationAccessRow(granted: Boolean, onOpen: () -> Unit) {
    val chrome = LocalChrome.current
    Gap(10)
    Text(
        "Android's own permission",
        style = MaterialTheme.typography.labelLarge,
        color = chrome.textHi,
    )
    Gap(4)
    Text(
        "Reading notifications at all needs a phone-wide permission Android calls " +
            "\"Notification access\" - once granted, an app COULD see every notification " +
            "on the phone. Jarvis's own switch above, and the list below (empty until you " +
            "add an app), are what actually limit it: nothing is read unless BOTH are set.",
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(8)
    Text(
        if (granted) "Notification access: granted." else "Notification access: not granted yet.",
        style = MaterialTheme.typography.labelSmall,
        color = if (granted) chrome.textMid else chrome.warnInk,
    )
    Gap(8)
    Secondary(
        if (granted) "Open Android's Notification access screen" else "Turn on Notification access",
        modifier = Modifier.fillMaxWidth(),
        onClick = onOpen,
    )
}

/**
 * The per-app allow list - EMPTY BY DEFAULT (CLAUDE.md). Adding an app that
 * looks like a bank/payment app or the phone's own SMS/Messages app is
 * refused right here, in words, before anything is saved
 * ([NotificationAllowListStore.add] does the real check).
 */
@Composable
private fun AllowedAppsList() {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    val store = remember { NotificationAllowListStore(context) }
    var version by remember { mutableIntStateOf(0) }
    var allowed by remember { mutableStateOf<List<String>>(emptyList()) }
    var picking by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(version) { allowed = store.packages().sorted() }

    Gap(12)
    Text("Apps Jarvis may read", style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
    Gap(4)
    Text(
        "None, until you add one. Never a banking, brokerage or payment app, and never " +
            "your phone's own Messages (SMS) app - both are refused here, not just discouraged.",
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    Gap(8)
    if (allowed.isEmpty()) {
        Text("No apps added yet.", style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
    } else {
        allowed.forEach { pkg ->
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text(
                    pkg,
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
                Quiet("Remove", onClick = { store.remove(pkg); version += 1 })
            }
        }
    }
    Gap(8)
    Secondary(
        if (picking) "Close the list" else "Add an app",
        modifier = Modifier.fillMaxWidth(),
        onClick = { picking = !picking; message = null },
    )
    message?.let {
        Gap(6)
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
    }
    if (picking) {
        Gap(8)
        val candidates = remember(version) { store.installedApps() }
        if (candidates.isEmpty()) {
            Text(
                "No other apps found to add.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        } else {
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 240.dp)) {
                items(candidates, key = { it.packageName }) { app ->
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
                            onClick = {
                                message = when (store.add(app.packageName)) {
                                    is NotificationAllowList.AddResult.Added -> {
                                        version += 1
                                        picking = false
                                        null
                                    }
                                    is NotificationAllowList.AddResult.BlockedBanking ->
                                        "${app.label} looks like a banking, brokerage or " +
                                            "payment app, so it is refused here."
                                    is NotificationAllowList.AddResult.BlockedSms ->
                                        "${app.label} is (or acts as) this phone's text " +
                                            "message app, so it is never added."
                                    is NotificationAllowList.AddResult.AlreadyAdded ->
                                        "${app.label} is already on the list."
                                }
                            },
                        )
                    }
                }
            }
        }
    }
}

/**
 * "Phone notifications" - a section of its own, beside [WatchNotifySection].
 */
@Composable
internal fun PhoneNotificationsSection(
    canAct: Boolean = false,
    notificationAccessGranted: Boolean = false,
    onOpenNotificationAccess: () -> Unit = {},
) {
    var reads by remember { mutableIntStateOf(0) }
    Section("Phone notifications", trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            PhoneNotificationsSwitch(canAct = canAct, refresh = reads)
            NotificationAccessRow(granted = notificationAccessGranted, onOpen = onOpenNotificationAccess)
            AllowedAppsList()
        }
    }
}
