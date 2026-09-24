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
import com.jarvis.client.BuildConfig
import com.jarvis.client.LinkState
import com.jarvis.client.net.UpdateCheck
import com.jarvis.client.net.VoiceStatus
import com.jarvis.client.net.WakeWord
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.ReadinessItem
import com.jarvis.client.service.WakeListen
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.ageText
import com.jarvis.client.ui.parts.rememberTickingNow
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.VoiceTraining
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
    /** Asks the desktop to turn the wake word on - an approval card. Null hides it. */
    onWakeWordOn: (() -> Unit)? = null,
    /** A card to turn it on is waiting for the owner. */
    wakeWordPending: Boolean = false,
    /** What this phone's own "hey Jarvis" listener is doing. */
    phoneListening: WakeListen = WakeListen.Off,
    /** Starts (true) or stops (false) this phone's listener. Null hides it. */
    onPhoneListening: ((Boolean) -> Unit)? = null,
    /** Set while the change is in flight, so the button cannot be double-sent. */
    wakeWordBusy: Boolean = false,
    /** What went wrong, or what the desktop said afterwards. */
    wakeWordNotice: String? = null,
    /** "Interrupt Jarvis while it talks" on this phone (BargeIn). Null hides the switch. */
    bargeIn: Boolean? = null,
    /** Whether this phone has an echo canceller (the default follows it). */
    bargeInEchoCanceller: Boolean = false,
    onBargeIn: ((Boolean) -> Unit)? = null,
    modifier: Modifier = Modifier,
    /** The link, for the Connection card. Null hides the card. */
    connection: ConnectionInfo? = null,
    /** A reconnect the owner asked for - the same call as Home's Retry. Null hides it. */
    onReconnect: (() -> Unit)? = null,
    /** Opens pairing again with the saved host filled in. Null hides it. */
    onChangeDesktop: (() -> Unit)? = null,
    /** The desktop's voice status, for the "Your voice" card. Null hides the card. */
    voiceStatus: VoiceStatus? = null,
    /** Whether that status is a real answer rather than the refusing defaults. */
    voiceAnswered: Boolean = false,
    /** Opens "Train my voice". Null hides the button. */
    onTrainVoice: (() -> Unit)? = null,
    /** One line on what Security has on (`SecurityRules.summary`). Null hides the card. */
    securitySummary: String? = null,
    /** Opens Security. */
    onOpenSecurity: () -> Unit = {},
    /** The last update check (`net/UpdateCheck.kt`). Null hides the card. */
    update: UpdateCheck.State? = null,
    /** "Check for new versions" - on by default. */
    updateChecks: Boolean = true,
    onUpdateChecks: (Boolean) -> Unit = {},
    /** Opens the release page in the browser. */
    onOpenRelease: () -> Unit = {},
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
            if (voiceStatus != null) {
                item(key = "your-voice") {
                    YourVoiceCard(voiceStatus, voiceAnswered, onTrainVoice)
                }
            }
            item(key = "wake-word") {
                WakeWordCard(
                    state = wakeWord,
                    busy = wakeWordBusy,
                    notice = wakeWordNotice,
                    onTurnOff = onWakeWordOff,
                    onRecheck = onRecheckWakeWord,
                    onTurnOn = onWakeWordOn,
                    pending = wakeWordPending,
                    phone = phoneListening,
                    onPhone = onPhoneListening,
                    bargeIn = bargeIn,
                    bargeInEchoCanceller = bargeInEchoCanceller,
                    onBargeIn = onBargeIn,
                )
            }
            if (securitySummary != null) {
                item(key = "security") { SecurityCard(securitySummary, onOpenSecurity) }
            }
            items(others, key = { it.title }) { ReadinessCard(it, fixFor(it)) }
            item(key = "frame-rate") { FrameRateCard() }
            if (update != null) {
                item(key = "this-app") { ThisAppCard(update, updateChecks, onUpdateChecks, onOpenRelease) }
            }
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
            // Secondary (visual-5): Reconnect above is the usual answer, and
            // this is the second choice beside it.
            Secondary(
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
            "type in the one Jarvis Desktop shows under Settings, \"Show the token " +
            "for my phone\"."
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
 * Whether Jarvis knows the owner's voice, and the way to teach it.
 *
 * Here rather than on Home because this is where the phone's other voice
 * setting (the wake word) already lives, and because the talk button on Home
 * is hidden until training is done - so Home cannot be where the reason is.
 * The talk button's own reason (`listening.push_to_talk_why`) is shown too:
 * after training it may still be hidden, for example because the PC has no
 * speech-to-text set up, and that should be findable.
 */
@Composable
private fun YourVoiceCard(status: VoiceStatus, answered: Boolean, onTrain: (() -> Unit)?) {
    val chrome = LocalChrome.current
    val trained = answered && status.available && status.gate.enrolled &&
        !status.gate.needsRetraining
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(if (trained) chrome.okInk else chrome.warnInk)
            Spacer(Modifier.width(10.dp))
            Text("Your voice", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Spacer(Modifier.weight(1f))
            Text(
                when {
                    !answered -> "Unknown"
                    trained -> "Trained"
                    else -> "Not trained"
                },
                style = MaterialTheme.typography.labelMedium,
                color = if (trained) chrome.okInk else chrome.warnInk,
            )
        }
        Gap(6)
        Text(
            VoiceTraining.stateLine(status, answered),
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        VoiceTraining.lastLine(status.gate.training.last)?.let {
            Gap(4)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        VoiceTraining.basicCheckLine(status, answered)?.let {
            Gap(6)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        val why = status.listening.pushToTalkWhy
        // Only once trained: before that the line above already says why, and
        // the desktop's sentence points at this very card.
        if (trained && !status.canPushToTalk && why.isNotBlank()) {
            Gap(6)
            Text(
                "Talk button on Home: hidden. $why",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
        if (onTrain != null) {
            Gap(12)
            Primary(
                text = if (trained) "Train my voice again" else "Train my voice",
                modifier = Modifier.fillMaxWidth(),
                onClick = onTrain,
            )
        }
    }
}

/**
 * "Hey Jarvis": the desktop's switch, and this phone's own listening.
 *
 * Two switches, on purpose, because they are two different things.
 *
 * THE DESKTOP'S SWITCH says whether Jarvis takes wake-word clips at all.
 * Turning it on is a change to where Jarvis listens, so it is an approval
 * card (`change_own_config`), never a toggle that flips here: "Turn on"
 * asks, and the card is where the owner decides. Off is immediate.
 *
 * THIS PHONE'S LISTENING is the microphone on this handset, open for as long
 * as it is on (`WakeWordService`, with a notification and Android's
 * microphone dot the whole time). It can only be switched on while the
 * desktop's switch is on, and it is never on by default or after a restart.
 *
 * Three states for the desktop, not a checkbox, because [WakeWord.UNKNOWN]
 * must never render as off - see that type. And the state shown is always the
 * one the desktop last reported, never the one just requested.
 */
@Composable
private fun WakeWordCard(
    state: WakeWord,
    busy: Boolean,
    notice: String?,
    onTurnOff: (() -> Unit)?,
    onRecheck: (() -> Unit)?,
    onTurnOn: (() -> Unit)?,
    pending: Boolean,
    phone: WakeListen,
    onPhone: ((Boolean) -> Unit)?,
    bargeIn: Boolean? = null,
    bargeInEchoCanceller: Boolean = false,
    onBargeIn: ((Boolean) -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val tint = when {
        state == WakeWord.ON -> chrome.warnInk
        state == WakeWord.OFF && pending -> chrome.warnInk
        state == WakeWord.OFF -> chrome.okInk
        else -> chrome.textMid
    }
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Dot(tint)
            Spacer(Modifier.width(10.dp))
            Text("Wake word - \"hey Jarvis\"", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Spacer(Modifier.weight(1f))
            Text(
                when {
                    state == WakeWord.ON -> "ON"
                    state == WakeWord.OFF && pending -> "Waiting"
                    state == WakeWord.OFF -> "Off"
                    else -> "Unknown"
                },
                style = MaterialTheme.typography.labelMedium,
                color = tint,
            )
        }
        Gap(6)
        Text(
            when {
                state == WakeWord.ON ->
                    "Your desktop takes \"hey Jarvis\". It checks the phrase and your voice " +
                        "again before it writes down a word."
                state == WakeWord.OFF && pending ->
                    "A card to turn it on is waiting. ${com.jarvis.client.net.Approvals.WHERE} " +
                        "Nothing listens until you do."
                state == WakeWord.OFF ->
                    "Off. Nothing can wake Jarvis by speaking a phrase; the talk button still works."
                else ->
                    "The desktop has not answered, so this is not known. It is not being " +
                        "reported as off, because \"off\" and \"could not ask\" are not the " +
                        "same thing and only one of them is safe to believe."
            },
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )

        Gap(8)
        Text(
            // True whatever the desktop says: this handset listens only while
            // its own switch below is on.
            when (phone) {
                WakeListen.Off ->
                    "This phone is not listening. Its microphone opens only while you hold " +
                        "the talk button, or while \"Listen on this phone\" is on."
                WakeListen.Starting -> "This phone is starting to listen…"
                WakeListen.Listening ->
                    "This phone is listening. The microphone stays open - Android shows its " +
                        "microphone dot and a notification the whole time - but nothing leaves " +
                        "the phone until it hears \"hey Jarvis\". It also uses some battery."
                WakeListen.Heard -> "Heard \"hey Jarvis\" - listening to what you say next."
                WakeListen.Paused -> "Paused while the talk button has the microphone."
                is WakeListen.Failed -> "This phone stopped listening: ${phone.why}"
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (phone is WakeListen.Failed) chrome.warnInk else chrome.textMid,
        )

        if (notice != null) {
            Gap(8)
            Text(notice, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        if (onPhone != null && phone.on) {
            Gap(12)
            Secondary(
                text = "Stop listening on this phone",
                enabled = true,
                modifier = Modifier.fillMaxWidth(),
                onClick = { onPhone(false) },
            )
        } else if (onPhone != null && state == WakeWord.ON) {
            Gap(12)
            Primary(
                text = "Listen on this phone",
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = { onPhone(true) },
            )
            Gap(4)
            Text(
                "Keeps the microphone open until you stop it, restart the phone, or " +
                    "Android closes Jarvis. Off by default, and never turns itself on.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }

        if (bargeIn != null && onBargeIn != null && state == WakeWord.ON) {
            Gap(12)
            Text(
                "Interrupt Jarvis while it talks",
                style = MaterialTheme.typography.labelLarge,
                color = chrome.textHi,
            )
            Gap(4)
            Text(
                BargeIn.describe(bargeIn, bargeInEchoCanceller),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            Secondary(
                text = if (bargeIn) "Stop listening while Jarvis talks" else "Listen while Jarvis talks",
                enabled = true,
                modifier = Modifier.fillMaxWidth(),
                onClick = { onBargeIn(!bargeIn) },
            )
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

        if (state == WakeWord.OFF && !pending && onTurnOn != null) {
            Gap(12)
            Primary(
                text = if (busy) "Asking…" else "Turn on \"hey Jarvis\"",
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = onTurnOn,
            )
            Gap(4)
            Text(
                "This raises an approval card. Nothing changes until you approve it, " +
                    "and then nothing listens until you switch listening on here or on the desktop.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }

        if ((state == WakeWord.UNKNOWN || pending) && onRecheck != null) {
            Gap(12)
            Secondary(
                text = if (busy) "Asking…" else "Ask the desktop again",
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
                onClick = onRecheck,
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

/**
 * What Security has on, and the way there. The settings themselves are on
 * their own screen (SecurityScreen.kt); this is where the phone's other
 * settings already live, so it is where the owner will look.
 */
@Composable
private fun SecurityCard(summary: String, onOpen: () -> Unit) {
    val chrome = LocalChrome.current
    Plate {
        Text("Security", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Gap(6)
        Text(summary, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Gap(12)
        Secondary(
            text = "Lock and fingerprint settings",
            color = chrome.textMid,
            modifier = Modifier.fillMaxWidth(),
            onClick = onOpen,
        )
    }
}

/**
 * This build, and "a newer version is available" (net/UpdateCheck.kt).
 *
 * The one place a failed check is mentioned: Home stays quiet about it.
 * The switch turns the request to GitHub off entirely.
 */
@Composable
private fun ThisAppCard(
    update: UpdateCheck.State,
    checks: Boolean,
    onChecks: (Boolean) -> Unit,
    onOpenRelease: () -> Unit,
) {
    val chrome = LocalChrome.current
    val now = rememberTickingNow(update.lastTryMs, periodMs = 60_000L)
    Plate {
        Text("This app", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Gap(6)
        Field("Build", UpdateCheck.ownSha(BuildConfig.GIT_SHA)?.take(7) ?: "unknown", machine = true)
        Gap(6)
        SwitchRow(
            title = "Check for new versions",
            detail = "At most every six hours, this phone asks GitHub whether a newer build of this app is " +
                "on its release page. Nothing about you or Jarvis is sent, and nothing is " +
                "downloaded or installed.",
            checked = checks,
            onChange = onChecks,
        )
        if (checks) {
            val newer = update.newerLine
            val last = update.lastTryMs
            Gap(6)
            Text(
                when {
                    newer != null -> newer
                    last == null -> "Not checked yet."
                    update.problem == null -> "Up to date, as of ${ageText(now - last)}."
                    else -> "Last checked ${ageText(now - last)}."
                },
                style = MaterialTheme.typography.bodySmall,
                color = if (newer != null) chrome.textHi else chrome.textMid,
            )
            update.problem?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            }
            if (newer != null) {
                Gap(8)
                Secondary(
                    text = "Open release page",
                    color = chrome.textMid,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = onOpenRelease,
                )
            }
        }
    }
}
