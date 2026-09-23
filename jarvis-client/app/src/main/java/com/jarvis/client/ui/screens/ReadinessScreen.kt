package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.LinkState
import com.jarvis.client.net.WakeWord
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.ReadinessItem
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay

/**
 * What the Connection card shows: the link as the rest of the app sees it.
 *
 * Home's status line opens this screen so the owner can find out why the link
 * is down, and the screen used to say nothing about the link at all. The
 * token is deliberately not here, not even as "set" or a masked tail: the
 * pairing screen already says whether one is stored, and this card has no
 * reason to touch it.
 *
 * @param host the desktop address that is saved and in use - not one being
 *   typed on the pairing screen.
 * @param paired whether this phone has a desktop and a token at all.
 * @param detail why the link is down, as the runtime reported it, or null.
 */
data class ConnectionInfo(
    val host: String,
    val paired: Boolean,
    val link: LinkState,
    val stale: Boolean,
    val detail: String?,
)

/**
 * The four §3.1 items, reported rather than assumed — plus the two the audit
 * added.
 *
 * Three of the originals fail silently and look like something else: cleartext
 * looks like a network outage, a denied notification looks like the service not
 * running, and Doze looks like the backend going away. This screen exists so
 * they are visible on the device rather than inferred from a symptom.
 *
 * Order is by what needs doing, not by when a check was written: the
 * Connection card first (it is the question Home sends people here to
 * answer), then anything warning, then the rest. Each fix button sits inside
 * the card that explains it. They used to share a strip at the bottom,
 * a third of the width each, far from the reason to press them.
 */
@Composable
fun ReadinessScreen(
    items: List<ReadinessItem>,
    onRequestNotifications: () -> Unit,
    onRequestBatteryExemption: () -> Unit,
    onStartService: () -> Unit,
    onBack: () -> Unit,
    /** Null hides the button entirely - this phone has no assistant role to
     *  request at all, or Jarvis already holds it. */
    onRequestAssistantRole: (() -> Unit)? = null,
    /** The desktop's wake word, as three states — never as a boolean. */
    wakeWord: WakeWord = WakeWord.UNKNOWN,
    /** Turns the desktop's wake word off. Null hides the control entirely. */
    onWakeWordOff: (() -> Unit)? = null,
    onRecheckWakeWord: (() -> Unit)? = null,
    /** Set while the change is in flight, so the button cannot be double-sent. */
    wakeWordBusy: Boolean = false,
    /** What went wrong, or what the desktop said afterwards. */
    wakeWordNotice: String? = null,
    modifier: Modifier = Modifier,
    /** The link, for the Connection card. Null hides the card. */
    connection: ConnectionInfo? = null,
    /** A reconnect the owner asked for - the same call as Home's Retry. Null hides it. */
    onReconnect: (() -> Unit)? = null,
    /** Opens pairing again with the saved host filled in. Null hides it. */
    onChangeDesktop: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    // Split rather than re-sorted, so within each group the order stays the
    // one PlatformReadiness wrote.
    val warnings = remember(items) { items.filter { it.state == ReadinessItem.State.WARN } }
    val others = remember(items) { items.filter { it.state != ReadinessItem.State.WARN } }

    // Which button belongs in which card. A local function rather than a
    // field on ReadinessItem, because the callbacks live here and the item
    // only names which fix it wants.
    fun fixFor(item: ReadinessItem): CardFix? = when (item.fix) {
        ReadinessItem.Fix.NOTIFICATIONS ->
            if (item.state == ReadinessItem.State.WARN) {
                CardFix("Allow notifications", warn = true, onClick = onRequestNotifications)
            } else {
                null
            }
        ReadinessItem.Fix.BATTERY ->
            if (item.state == ReadinessItem.State.WARN) {
                CardFix("Keep link alive", warn = true, onClick = onRequestBatteryExemption)
            } else {
                null
            }
        ReadinessItem.Fix.START_LINK ->
            CardFix(
                "Start link",
                warn = item.state == ReadinessItem.State.WARN,
                onClick = onStartService,
            )
        ReadinessItem.Fix.ASSISTANT_ROLE ->
            onRequestAssistantRole?.let {
                CardFix("Set Jarvis as the assistant app", warn = false, onClick = it)
            }
        null -> null
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Platform checks", onBack, subtitle = "What this phone will and will not allow")

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (connection != null) {
                item(key = "connection") {
                    ConnectionCard(
                        info = connection,
                        onReconnect = onReconnect,
                        onChangeDesktop = onChangeDesktop,
                    )
                }
            }
            items(warnings, key = { it.title }) { ReadinessCard(it, fixFor(it)) }
            item(key = "wake-word") {
                WakeWordCard(
                    state = wakeWord,
                    busy = wakeWordBusy,
                    notice = wakeWordNotice,
                    onTurnOff = onWakeWordOff,
                    onRecheck = onRecheckWakeWord,
                )
            }
            items(others, key = { it.title }) { ReadinessCard(it, fixFor(it)) }
            item(key = "frame-rate") { FrameRateCard() }
        }
    }
}

/** A fix button, as it will be drawn inside its card. */
private data class CardFix(val label: String, val warn: Boolean, val onClick: () -> Unit)

/**
 * The link, in words, with the two things that can be done about it.
 *
 * The state names are the same ones Home's status line uses, and each comes
 * with what it means for approving: that is the part rule 4 turns on, and the
 * owner should not have to know the rule to understand why Approve is grey.
 */
@Composable
private fun ConnectionCard(
    info: ConnectionInfo,
    onReconnect: (() -> Unit)?,
    onChangeDesktop: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    val tint = when {
        !info.paired -> chrome.warnInk
        info.link == LinkState.OFFLINE -> chrome.badInk
        info.link == LinkState.RECONNECTING || info.stale -> chrome.warnInk
        else -> chrome.okInk
    }
    val word = when {
        !info.paired -> "Not paired"
        info.link == LinkState.OFFLINE -> "Offline"
        info.link == LinkState.RECONNECTING -> "Reconnecting"
        info.stale -> "Stale"
        else -> "Connected"
    }
    val line = when {
        !info.paired ->
            "This phone is not paired with a desktop yet. Go back to type the " +
                "desktop's address and token."
        info.link == LinkState.OFFLINE ->
            "Jarvis cannot reach your desktop. Approving is blocked until it " +
                "reconnects."
        info.link == LinkState.RECONNECTING ->
            "Jarvis lost the desktop and is trying again. Approving is blocked " +
                "until it is back."
        info.stale ->
            "Connected, but updates have stopped arriving, so what you see may be " +
                "out of date. Approving is blocked until they resume."
        else -> "Connected, and updates are arriving."
    }
    // Only while something is wrong. The runtime clears it when the link comes
    // up, but a last reason shown beside "Connected" would read as a current one.
    val problem = info.detail?.takeIf { info.link != LinkState.CONNECTED || info.stale }
    var showTechnical by rememberSaveable { mutableStateOf(false) }

    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(tint)
            Spacer(Modifier.width(10.dp))
            Text("Connection", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Spacer(Modifier.weight(1f))
            Text(word, style = MaterialTheme.typography.labelMedium, color = tint)
        }
        Gap(6)
        Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Gap(6)
        Field("Desktop", info.host.ifBlank { "Not set" }, machine = info.host.isNotBlank())

        if (problem != null) {
            Gap(6)
            Text(
                plainReason(problem),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk,
            )
            Quiet(
                if (showTechnical) "Hide technical detail" else "Technical detail",
                color = chrome.textMid,
            ) { showTechnical = !showTechnical }
            if (showTechnical) {
                Text(
                    "Reported by the link: $problem",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }
        }

        if (info.paired && onReconnect != null) {
            Gap(12)
            Primary(
                text = "Reconnect",
                modifier = Modifier.fillMaxWidth(),
                onClick = onReconnect,
            )
        }
        if (onChangeDesktop != null) {
            Gap(8)
            Primary(
                text = "Change desktop or token",
                color = chrome.textMid,
                modifier = Modifier.fillMaxWidth(),
                onClick = onChangeDesktop,
            )
            Gap(4)
            Text(
                "Your current desktop and token stay saved until new ones connect.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
    }
}

/**
 * The runtime's reason for a dropped link, in words the owner can act on.
 *
 * The strings matched here are written in `net/EventStream.kt` and
 * `JarvisRuntime.kt`. Anything not recognised is shown as it came, so a new
 * reason is never hidden - only left unexplained.
 */
private fun plainReason(detail: String): String = when {
    detail == "Token refused" ->
        "The desktop refused this phone's token. Tap Change desktop or token and " +
            "paste the one from the desktop's HUD settings."
    detail.startsWith("No keepalive for ") ->
        "The desktop went quiet: nothing has been heard from it for " +
            detail.removePrefix("No keepalive for ") + "."
    detail == "This server has no event stream" ->
        "Something answered at that address, but it is not a Jarvis desktop that " +
            "sends live updates."
    detail.startsWith("Server said ") ->
        "The desktop answered with an error (" + detail.removePrefix("Server said ") + ")."
    else -> "Last problem: $detail"
}

/**
 * The wake word, and the one control that turns it off.
 *
 * I argued against building a wake-word toggle at all, and that argument was
 * about the *on* half: a switch labelled "listen for hey jarvis" that cannot
 * listen, because no model is bundled, would be a promise about a microphone
 * that the app cannot keep. None of that applies to switching it off.
 * `/api/voice/wake` is a real route and the desktop's ear is a real thing that
 * can be open right now, so "off" does something. It is offered on its own.
 *
 * Three states, not a checkbox, because [WakeWord.UNKNOWN] must never render as
 * off — see that type. And the state shown is always the one the desktop last
 * reported, never the one just requested: the write is a config change, and a
 * 200 means accepted rather than stopped.
 */
@Composable
private fun WakeWordCard(
    state: WakeWord,
    busy: Boolean,
    notice: String?,
    onTurnOff: (() -> Unit)?,
    onRecheck: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    val tint = when (state) {
        WakeWord.ON -> chrome.warnInk
        WakeWord.OFF -> chrome.okInk
        WakeWord.UNKNOWN -> chrome.textMid
    }
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(tint)
            Spacer(Modifier.width(10.dp))
            Text("Wake word", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Spacer(Modifier.weight(1f))
            Text(
                when (state) {
                    WakeWord.ON -> "ON"
                    WakeWord.OFF -> "Off"
                    WakeWord.UNKNOWN -> "Unknown"
                },
                style = MaterialTheme.typography.labelMedium,
                color = tint,
            )
        }
        Gap(6)
        Text(
            when (state) {
                WakeWord.ON ->
                    "Your desktop will accept audio sent as a wake-word trigger."
                WakeWord.OFF ->
                    "Your desktop refuses wake-word audio. Nothing can trigger Jarvis by " +
                        "speaking a phrase."
                WakeWord.UNKNOWN ->
                    "The desktop has not answered, so this is not known. It is not being " +
                        "reported as off, because \"off\" and \"could not ask\" are not the " +
                        "same thing and only one of them is safe to believe."
            },
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )

        Gap(8)
        Text(
            // True regardless of the state above, and the thing most worth
            // knowing: whatever the desktop is doing, this handset is not
            // listening between button presses.
            "This phone never listens for a wake phrase. No wake-word model is bundled in " +
                "the app, so its microphone only opens while you hold the talk button down.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )

        if (notice != null) {
            Gap(8)
            Text(notice, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        if (state == WakeWord.ON && onTurnOff != null) {
            Gap(12)
            Primary(
                text = if (busy) "Turning it off…" else "Turn the wake word off",
                color = chrome.warnInk,
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = onTurnOff,
            )
        }

        if (state == WakeWord.UNKNOWN && onRecheck != null) {
            Gap(12)
            Primary(
                text = if (busy) "Asking…" else "Ask the desktop again",
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = onRecheck,
            )
        }

        if (state == WakeWord.OFF) {
            Gap(8)
            Text(
                "Turning it back on is a desktop-side change, deliberately. It is not " +
                    "offered here because this phone could not use it yet.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
    }
}

/**
 * One check: a plain sentence first, the platform's own words one tap away,
 * and the button that fixes it - if there is one - right underneath.
 */
@Composable
private fun ReadinessCard(item: ReadinessItem, fix: CardFix?) {
    val chrome = LocalChrome.current
    val tint = when (item.state) {
        ReadinessItem.State.OK -> chrome.okInk
        ReadinessItem.State.WARN -> chrome.warnInk
        ReadinessItem.State.INFO -> chrome.textMid
    }
    // Per card, and saved: opening one card's detail should not open them all,
    // and a rotation should not close the one being read.
    var showTechnical by rememberSaveable(item.title) { mutableStateOf(false) }
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(tint)
            Spacer(Modifier.width(10.dp))
            Text(item.title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        }
        Gap(6)
        Text(item.detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        val technical = item.technical
        if (technical != null) {
            Quiet(
                if (showTechnical) "Hide technical detail" else "Technical detail",
                color = chrome.textMid,
            ) { showTechnical = !showTechnical }
            if (showTechnical) {
                Text(technical, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
        }
        if (fix != null) {
            Gap(10)
            Primary(
                text = fix.label,
                color = if (fix.warn) chrome.warnInk else null,
                modifier = Modifier.fillMaxWidth(),
                onClick = fix.onClick,
            )
        }
    }
}

/**
 * The frame-rate readout §11 asks for, on the screen that is already this
 * app's debug surface.
 *
 * Three numbers rather than one, because they answer different questions.
 * *Panel* is what the display is doing. *Asked for* is what was requested —
 * and the gap between those two is the whole reason this exists, since nothing
 * on Android reports why a request was refused. *Face* is what the reactor
 * actually sustained: below the panel means the draw is the limit, level with
 * it means the draw is not.
 *
 * *Face* is never live on this screen, because the face does not run here -
 * it runs on Home (and in Appearance's preview). The number is the last one
 * measured there, and it used to sit beside the two live ones looking just as
 * current. It now says how old it is, which is the same promise [Freshness]
 * makes everywhere else: last-known data, said to be last-known.
 */
@Composable
private fun FrameRateCard() {
    val chrome = LocalChrome.current
    val panel by DisplayRate.panelHz.collectAsState()
    val asked by DisplayRate.requestedHz.collectAsState()
    val achieved by DisplayRate.achievedHz.collectAsState()
    val modes by DisplayRate.modes.collectAsState()
    // Read on a slow tick rather than collected: the time of the last frame
    // changes every frame while the face runs, and a flow of it would be the
    // very recomposition storm `DisplayRate.publish` exists to prevent. Once a
    // second is enough to keep "12 s ago" honest.
    var sinceMs by remember { mutableStateOf(DisplayRate.msSinceLastSample()) }
    LaunchedEffect(Unit) {
        while (true) {
            sinceMs = DisplayRate.msSinceLastSample()
            delay(1_000L)
        }
    }

    Plate {
        Text("Frame rate", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Gap(8)
        RateRow("Panel", panel)
        RateRow("Asked for", asked)
        RateRow("Face (last measured)", achieved)
        Text(
            sinceMs.let { ms ->
                if (ms == null) {
                    "The face has not been drawn since the app started. Open Home, " +
                        "then come back here."
                } else {
                    "Measured while the face was on screen, ${ago(ms)}. The face does " +
                        "not run on this screen, so this number is not live."
                }
            },
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        if (asked <= 0f) {
            Gap(8)
            Text(
                // Always the case here now, and worth saying so the dash does
                // not read as a fault: the fast rate is requested only with the
                // face on screen (DisplayRate.wantsHigh).
                "Nothing is asked for on this screen. The fastest rate is only asked " +
                    "for on Home, while Jarvis is listening, speaking or starting to " +
                    "think, and never in battery saver.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        if (modes.size > 1) {
            Gap(8)
            Text(
                "This screen offers " + modes.joinToString(", ") { "%.0f".format(it) } + " Hz.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        if (asked > 0f && panel > 0f && panel + 1f < asked) {
            Gap(8)
            Text(
                // Battery saver, an LTPO panel floating by content cadence, low
                // brightness on many OEM builds, or heat. There is no API that
                // says which, so this says what it can and does not guess.
                "The display did not grant the rate that was asked for. Battery saver, " +
                    "screen brightness or heat can all cap it, and Android does not report which.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk,
            )
        }
    }
}

@Composable
private fun RateRow(label: String, hz: Float) {
    val chrome = LocalChrome.current
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textMid,
            modifier = Modifier.weight(1f),
        )
        Text(
            if (hz <= 0f) "—" else "%.1f Hz".format(hz),
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
        )
    }
}

/** "just now", "40 s ago", "3 min ago", "2 h ago". */
private fun ago(ms: Long): String {
    val s = ms / 1_000L
    return when {
        s < 2L -> "just now"
        s < 60L -> "$s s ago"
        s < 3_600L -> "${s / 60L} min ago"
        else -> "${s / 3_600L} h ago"
    }
}
