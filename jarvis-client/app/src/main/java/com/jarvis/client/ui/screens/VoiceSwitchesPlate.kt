package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.WakeWord
import com.jarvis.client.service.WakeListen
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.HeardSound
import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.OneMoment

/**
 * "Hey Jarvis": the desktop's switch, and this phone's own listening.
 *
 * The "hey Jarvis" switches, in Settings, under Voice (moved from Platform
 * checks by the settings audit of 2026-09-30, so they sit with the other voice
 * settings, as on the desktop's #voice; Checks keeps a short status card,
 * [WakeWordSummaryCard], that opens this).
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
internal fun WakeWordSwitchesCard(
    state: WakeWord,
    busy: Boolean,
    notice: String?,
    onTurnOff: (() -> Unit)?,
    onRecheck: (() -> Unit)?,
    onTurnOn: (() -> Unit)?,
    pending: Boolean,
    phone: WakeListen,
    onPhone: ((Boolean) -> Unit)?,
    interrupt: String? = null,
    bargeInEchoCanceller: Boolean = false,
    onInterrupt: ((String) -> Unit)? = null,
    oneMoment: Boolean? = null,
    onOneMoment: ((Boolean) -> Unit)? = null,
    heardSound: Boolean? = null,
    onHeardSound: ((Boolean) -> Unit)? = null,
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

        // "Interrupting Jarvis": ONE setting, for "hey Jarvis" replies and
        // Jarvis Live alike (the owner's answer of 2026-09-28 merged "Interrupt
        // Jarvis while it talks" and "Interrupting Jarvis in Live"). Shown
        // whether or not "hey Jarvis" is on - it matters in Live too. This
        // phone's own; no card either way.
        if (interrupt != null && onInterrupt != null) {
            Gap(12)
            Text(
                LiveRules.INTERRUPT_TITLE,
                style = MaterialTheme.typography.labelLarge,
                color = chrome.textHi,
            )
            LiveRules.INTERRUPT.forEach { c ->
                Gap(6)
                OptionChip(
                    label = if (c.recommended) "${c.label} (recommended)" else c.label,
                    isSelected = interrupt == c.id,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = { onInterrupt(c.id) },
                )
                Gap(4)
                Text(c.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
            if (interrupt == LiveRules.INTERRUPT_VOICE && !bargeInEchoCanceller) {
                Gap(4)
                Text(
                    BargeIn.describe(true, echoCancellerAvailable = false),
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
            }
        }

        // Not tied to "hey Jarvis": it is about any spoken question, the
        // talk button's too. This phone's own switch; the desktop has its own.
        if (oneMoment != null && onOneMoment != null) {
            Gap(12)
            Text(
                OneMoment.NAME,
                style = MaterialTheme.typography.labelLarge,
                color = chrome.textHi,
            )
            Gap(4)
            Text(
                OneMoment.describe(oneMoment),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            Secondary(
                text = if (oneMoment) "Stay quiet while I wait" else "Say \"One moment\"",
                enabled = true,
                modifier = Modifier.fillMaxWidth(),
                onClick = { onOneMoment(!oneMoment) },
            )
        }

        // Beside "One moment", and like it about any spoken question (the
        // talk button's too). This phone's own; the desktop has its own.
        if (heardSound != null && onHeardSound != null) {
            Gap(12)
            Text(
                HeardSound.NAME,
                style = MaterialTheme.typography.labelLarge,
                color = chrome.textHi,
            )
            Gap(4)
            Text(
                HeardSound.describe(heardSound),
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            Secondary(
                text = if (heardSound) "No sound when I finish" else "Play the sound",
                enabled = true,
                modifier = Modifier.fillMaxWidth(),
                onClick = { onHeardSound(!heardSound) },
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
