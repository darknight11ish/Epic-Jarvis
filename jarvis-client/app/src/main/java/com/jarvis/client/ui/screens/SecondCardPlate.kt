package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.net.SecondCard
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Toggle
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Second graphics card" on the Mind screen: what the PC found, the main
 * switch, one switch per feature, and the second copy of Ollama.
 *
 * A handful of approval-backed switches and nothing more - not deep config
 * editing. The same flow as the wake word: ON asks the PC, which raises one
 * approval card and changes nothing until it is approved (on the PC, or in
 * this phone's own approvals, one at a time); OFF is immediate. The switch
 * always shows what the PC last REPORTED, never what was just asked for, and
 * the plate is re-read when a card is decided.
 *
 * All the words about each switch are the PC's own (`name`, `what`, `why`),
 * read from `GET /api/second-card` - see [SecondCard]. When there is no
 * capable second card, every switch is still shown, greyed out, with the
 * reason. The pin command is PowerShell for the PC, so only its sentence is
 * shown here.
 *
 * @param busy the switch whose request is in flight, or null.
 * @param canAct false while the link is down or stale (rule 4): nothing is
 *   sent, and every switch is greyed out.
 * @param onSetSuggest "When to suggest the bigger model"'s one write - a
 *   signal id ("struggle"/"correction") and on/off. Unlike [onSet], NO
 *   approval card either way: see [SecondCard.Suggest]'s own doc.
 * @param onSetThird moves a switch onto the third graphics card, or moves
 *   it back off (2026-09-28) - null means "not used". Assigning raises its
 *   own approval card (`second_card_third_assign`), the same shape as
 *   [onSet]'s own ON; unassigning is immediate, like its OFF.
 * @param onSetChat "Everyday chat runs on" (2026-10-05): pin everyday chat
 *   to one graphics card ([SecondCard.CHAT_PIN], a card id - one approval
 *   card, `chat_card_pin`), or go back to leaving it to Ollama
 *   ([SecondCard.CHAT_LEAVE], immediate).
 */
@Composable
internal fun SecondCardPlate(
    read: SecondCard.Read,
    busy: String?,
    notice: String?,
    canAct: Boolean,
    onSet: (feature: String, enabled: Boolean) -> Unit,
    onSetSuggest: (signal: String, enabled: Boolean) -> Unit,
    onSetThird: (assign: String?) -> Unit,
    onSetChat: (action: String, card: String?) -> Unit,
    onRecheck: () -> Unit,
    onOpenApprovals: ((cardId: String?) -> Unit)?,
) {
    val chrome = LocalChrome.current
    // "Show or hide menus" (docs/JARVIS-API.md section 109): the owner may hide the Study helper
    // and Referee rows and the Third graphics card section. Hiding only tidies - a switch that
    // is on stays on and the PC keeps working; the whole plate is hidden from Brain.
    val menus by com.jarvis.client.JarvisRuntime.menus.view.collectAsState()
    val status = (read as? SecondCard.Read.Loaded)?.status
    if (status == null) {
        Plate {
            Text(
                SecondCard.readLine(read).orEmpty(),
                style = MaterialTheme.typography.bodyMedium,
                color = if (read is SecondCard.Read.NotAsked) chrome.textMid else chrome.warnInk,
            )
            Gap(8)
            Secondary(
                text = "Ask the PC again",
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
                onClick = onRecheck,
            )
            if (notice != null) {
                Gap(8)
                Text(notice, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            }
        }
        return
    }
    Plate {
        // 1. What was found.
        Kicker("What was found", Modifier.semantics { heading() })
        Gap(4)
        Text(
            status.detectedWhy.replaceFirstChar { it.uppercase() } + ".",
            style = MaterialTheme.typography.bodyMedium,
            color = if (status.capable) chrome.okInk else chrome.textMid,
        )
        for (line in SecondCard.cardLines(status)) {
            Gap(2)
            Text(line, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }

        // 2. The main switch, then one per feature.
        Gap(12)
        Rule()
        ApprovalSwitchRow(SecondCard.master(status), busy, canAct, onSet)
        for (view in SecondCard.switches(status)) {
            // A switch the owner hid from the list (Study helper, Referee suggestions).
            if (view.id == "study" && !menus.shows("settings.second-card.study-helper")) continue
            if (view.id == "referee" && !menus.shows("settings.second-card.referee")) continue
            Rule()
            ApprovalSwitchRow(view, busy, canAct, onSet)
        }
        Rule()

        // "One bigger model on both cards" (2026-09-26): a different way to
        // use the second card, not one of the switches above - it ties up
        // both cards, so it cannot run at the same time as any of them. Own
        // row, same place, same approval flow.
        SecondCard.combinedSwitch(status)?.let { view ->
            Gap(8)
            Kicker("One bigger model on both cards", Modifier.semantics { heading() })
            ApprovalSwitchRow(view, busy, canAct, onSet)
            Rule()
        }

        // A third graphics card (2026-09-28): moving one of the switches
        // above onto it, alongside the second card's own lane - never a
        // default (docs/GPU-SUPPORT-RESEARCH-2026-09-27.md section 1.3).
        // Shown only once one is capable, or a choice is still kept for
        // one that is not here right now.
        val third = status.third
        if (third != null && (third.capable || third.assigned != null) &&
            menus.shows("settings.second-card.third-card")
        ) {
            Gap(8)
            Kicker("Third graphics card", Modifier.semantics { heading() })
            ThirdCardRow(status, third, busy, canAct, onSetThird)
            Rule()
        }

        // "When to suggest the bigger model" (2026-09-27): whether Jarvis may
        // OFFER "One bigger model on both cards" on its own - never what it
        // may do without a person's yes, so NEITHER switch raises a card,
        // unlike every switch above. Null on an older PC.
        status.suggest?.let { suggest ->
            Gap(8)
            Kicker(suggest.title, Modifier.semantics { heading() })
            if (suggest.detail.isNotBlank()) {
                Gap(4)
                Text(suggest.detail, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
            for (signal in suggest.signals) {
                Rule()
                SuggestSwitchRow(signal, busy, canAct, onSetSuggest)
            }
            Rule()
        }

        // "Everyday chat runs on" (2026-10-05): which card runs everyday chat
        // - Ollama's own choice by default, or one the owner pins (one
        // approval card). The line under the choices is where the model
        // really is, read from the PC. Null on an older PC.
        if (status.chatCard != null && menus.shows("settings.second-card.chat-card")) {
            Gap(8)
            ChatCardPlate(status, busy, canAct, onSetChat)
            Rule()
        }

        if (notice != null) {
            Gap(8)
            Text(notice, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }

        // A card is waiting: where it is, and a way to ask again. Neither
        // approves anything - the card itself is still one deliberate tap.
        if (status.pending.isNotEmpty()) {
            Gap(8)
            if (onOpenApprovals != null) {
                Quiet(
                    "Open the card →",
                    color = chrome.warnInk,
                    onClick = { onOpenApprovals(null) },
                )
            }
            Secondary(
                text = if (busy != null) "Asking…" else "Ask the PC again",
                enabled = busy == null,
                modifier = Modifier.fillMaxWidth(),
                onClick = onRecheck,
            )
        }

        // 3. The second copy of Ollama, and keeping the everyday one apart.
        Gap(12)
        Kicker(
            if (status.main) "Extra features lane" else "The second card's Ollama",
            Modifier.semantics { heading() }
        )
        Gap(4)
        Text(
            SecondCard.laneLine(status),
            style = MaterialTheme.typography.bodySmall,
            color = if (status.laneState == "failed") chrome.warnInk else chrome.textMid,
        )
        val pinNote = status.pinNote
        if (!pinNote.isNullOrBlank()) {
            Gap(10)
            Kicker("Everyday Ollama", Modifier.semantics { heading() })
            Gap(4)
            Text(
                pinNote,
                style = MaterialTheme.typography.bodySmall,
                color = if (status.mainOllamaPinned == false) chrome.warnInk else chrome.textMid,
            )
            if (SecondCard.pinNeedsPc(status)) {
                Gap(4)
                Text(SecondCard.PIN_ON_PC, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }

        Gap(10)
        Text(
            "Turning a switch on raises an approval card on your PC and phone. Nothing " +
                "changes until you approve it. Turning one off happens at once. Nothing " +
                "here sends anything off your PC.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
    }
}

/**
 * One approval-backed switch: its name, the toggle, and the PC's line under
 * it. Shared with the big model's plate ([BigModelSection]), whose switches
 * follow exactly the same rules.
 */
@Composable
internal fun ApprovalSwitchRow(
    view: SecondCard.SwitchView,
    busy: String?,
    canAct: Boolean,
    onSet: (feature: String, enabled: Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                view.name,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Toggle(
                checked = view.on,
                onCheckedChange = { want -> onSet(view.id, want) },
                // OFF is always allowed; ON only when nothing blocks it. Both
                // wait for a live link and for the last request to come back.
                enabled = canAct && busy == null && (view.on || view.canTurnOn),
                modifier = Modifier.semantics { contentDescription = view.name },
            )
        }
        if (view.what.isNotBlank()) {
            Text(view.what, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Gap(4)
        Text(
            if (busy == view.id) "Asking your PC…" else view.line,
            style = MaterialTheme.typography.bodySmall,
            color = when {
                busy == view.id -> chrome.textMid
                view.waiting -> chrome.warnInk
                view.on && view.line.startsWith("Working") -> chrome.okInk
                else -> chrome.textMid
            },
        )
        // How its last card ended (denied, nobody answered, failed…), when
        // the PC says so - otherwise the row read "Off." as if nothing had
        // been asked.
        view.lastLine?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        val blocked = view.blocked
        if (!view.on && !view.waiting && blocked != null && blocked != view.line) {
            Text(blocked, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        view.needsLine?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        view.modelLine?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}

/**
 * The third card's own plate: a card found (or a kept choice, if it is not
 * here right now), then one chip per option - "Not used" plus one per
 * switch that is actually on ([SecondCard.thirdOptions]). Picking a chip
 * sends [onSetThird] at once, the same "the choice itself is the request"
 * shape [OptionChip] already uses for every other multi-way setting in
 * this app; the approval card that follows an assignment is the real gate,
 * not an extra confirm step here.
 */
@Composable
internal fun ThirdCardRow(
    status: SecondCard.Status,
    third: SecondCard.ThirdCard,
    busy: String?,
    canAct: Boolean,
    onSetThird: (assign: String?) -> Unit,
) {
    val chrome = LocalChrome.current
    val options = SecondCard.thirdOptions(status) ?: return
    val waitingHere = busy == SecondCard.THIRD
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        third.cardName?.let { name ->
            val size = third.cardTotalMb?.let { " (${(it + 512) / 1024} GB)" }.orEmpty()
            Text(
                "Found: $name$size",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
        }
        for (option in options) {
            Gap(4)
            OptionChip(
                label = option.label,
                isSelected = option.selected,
                modifier = Modifier.fillMaxWidth(),
                enabled = canAct && busy == null && SecondCard.thirdCanChange(status) &&
                    !option.selected,
                onClick = { onSetThird(option.value) },
            )
        }
        Gap(6)
        Text(
            if (waitingHere) "Asking your PC…" else SecondCard.thirdLine(status),
            style = MaterialTheme.typography.bodySmall,
            color = if (third.pending || waitingHere) chrome.warnInk else chrome.textMid,
        )
        SecondCard.thirdLastLine(status)?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        SecondCard.thirdModelLine(third)?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}

/**
 * "Everyday chat runs on" (the owner's decision, 2026-10-05): which graphics
 * card runs everyday chat. "Let Ollama decide" is the default - Jarvis pins
 * no card and says so - and each card the PC reports gets its own choice.
 * Picking a card sends [onSetChat] with [SecondCard.CHAT_PIN] and that card's
 * id: ONE approval card, because it changes where every answer runs. Going
 * back to "Let Ollama decide" is immediate, with no card.
 *
 * The line under the choices is where the model really IS, the PC's own
 * reading of Ollama and nvidia-smi - never a guess, and never a claim about a
 * card Jarvis did not pin. "Show the analysis" opens every fact the PC
 * reports about each card, plus the lines quoted from the owner's own
 * measurement of 2026-10-05; Jarvis's own suggestion is shown labelled as a
 * suggestion, and nothing here says one card is faster than another.
 */
@Composable
internal fun ChatCardPlate(
    status: SecondCard.Status,
    busy: String?,
    canAct: Boolean,
    onSetChat: (action: String, card: String?) -> Unit,
) {
    val chrome = LocalChrome.current
    val options = SecondCard.chatOptions(status) ?: return
    var analysisOpen by remember { mutableStateOf(false) }
    val waitingHere = busy == SecondCard.CHAT_CARD
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Kicker("Everyday chat runs on", Modifier.semantics { heading() })
        Gap(4)
        for (option in options) {
            Gap(4)
            OptionChip(
                label = option.label,
                isSelected = option.selected,
                modifier = Modifier.fillMaxWidth(),
                enabled = canAct && busy == null && !option.selected,
                onClick = {
                    if (option.card == null) {
                        onSetChat(SecondCard.CHAT_LEAVE, null)
                    } else {
                        onSetChat(SecondCard.CHAT_PIN, option.card)
                    }
                },
            )
            Text(option.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Gap(6)
        Text(
            if (waitingHere) "Asking your PC…" else SecondCard.chatWhereLine(status),
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        SecondCard.chatProblem(status)?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
        }
        Gap(6)
        Quiet(
            if (analysisOpen) "Hide the analysis" else "Show the analysis",
            onClick = { analysisOpen = !analysisOpen },
        )
        if (analysisOpen) {
            for (card in status.chatCard?.cards.orEmpty()) {
                Gap(6)
                SecondCard.chatFactLines(card).forEachIndexed { at, line ->
                    Text(
                        line,
                        style = if (at == 0) MaterialTheme.typography.titleSmall
                        else MaterialTheme.typography.labelSmall,
                        color = if (at == 0) chrome.textHi else chrome.textMid,
                    )
                }
            }
            SecondCard.chatSuggestion(status)?.let {
                Gap(6)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
    }
}

/**
 * One "When to suggest the bigger model" switch: unlike [ApprovalSwitchRow],
 * there is no card, no "waiting" and no "blocked" - either state is simply
 * what it is right now, so this row is a plain toggle plus the PC's own
 * "why" line.
 */
@Composable
internal fun SuggestSwitchRow(
    signal: SecondCard.Signal,
    busy: String?,
    canAct: Boolean,
    onSetSuggest: (signal: String, enabled: Boolean) -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                signal.label,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Toggle(
                checked = signal.enabled,
                onCheckedChange = { want -> onSetSuggest(signal.id, want) },
                enabled = canAct && busy == null,
                modifier = Modifier.semantics { contentDescription = signal.label },
            )
        }
        if (signal.why.isNotBlank()) {
            Gap(4)
            Text(signal.why, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }
}
