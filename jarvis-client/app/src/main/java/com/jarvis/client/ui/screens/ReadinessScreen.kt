package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.WakeWord
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.ReadinessItem
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.theme.LocalChrome
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue

/**
 * The four §3.1 items, reported rather than assumed — plus the two the audit
 * added.
 *
 * Three of the originals fail silently and look like something else: cleartext
 * looks like a network outage, a denied notification looks like the service not
 * running, and Doze looks like the backend going away. This screen exists so
 * they are visible on the device rather than inferred from a symptom.
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
) {
    val chrome = LocalChrome.current
    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Platform checks", onBack, subtitle = "What the device will and will not allow")

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(key = "wake-word") {
                WakeWordCard(
                    state = wakeWord,
                    busy = wakeWordBusy,
                    notice = wakeWordNotice,
                    onTurnOff = onWakeWordOff,
                    onRecheck = onRecheckWakeWord,
                )
            }
            item(key = "frame-rate") { FrameRateCard() }
            items(items, key = { it.title }) { ReadinessCard(it) }
        }

        Row(
            Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            val notifications = items.firstOrNull { it.title == "Notifications" }
            if (notifications?.state == ReadinessItem.State.WARN) {
                Primary(
                    text = "Allow notifications",
                    color = chrome.warnInk,
                    modifier = Modifier.weight(1f),
                    onClick = onRequestNotifications,
                )
            }
            val battery = items.firstOrNull { it.title == "Background restart" }
            if (battery?.state == ReadinessItem.State.WARN) {
                Primary(
                    text = "Keep link alive",
                    color = chrome.warnInk,
                    modifier = Modifier.weight(1f),
                    onClick = onRequestBatteryExemption,
                )
            }
            Primary(
                text = "Start link",
                modifier = Modifier.weight(1f),
                onClick = onStartService,
            )
        }
        if (onRequestAssistantRole != null) {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                Primary(
                    text = "Set Jarvis as the assistant app",
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onRequestAssistantRole,
                )
            }
            Gap(12)
        }
    }
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

@Composable
private fun ReadinessCard(item: ReadinessItem) {
    val chrome = LocalChrome.current
    val tint = when (item.state) {
        ReadinessItem.State.OK -> chrome.okInk
        ReadinessItem.State.WARN -> chrome.warnInk
        ReadinessItem.State.INFO -> chrome.textMid
    }
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(tint)
            Spacer(Modifier.width(10.dp))
            Text(item.title, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        }
        Gap(6)
        Text(item.detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
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
 */
@Composable
private fun FrameRateCard() {
    val chrome = LocalChrome.current
    val panel by DisplayRate.panelHz.collectAsState()
    val asked by DisplayRate.requestedHz.collectAsState()
    val achieved by DisplayRate.achievedHz.collectAsState()
    val modes by DisplayRate.modes.collectAsState()

    Plate {
        Text("Frame rate", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Gap(8)
        RateRow("Panel", panel)
        RateRow("Asked for", asked)
        RateRow("Face", achieved)
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
