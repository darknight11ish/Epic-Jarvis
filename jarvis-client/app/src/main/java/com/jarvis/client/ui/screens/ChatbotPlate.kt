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
import com.jarvis.client.net.Chatbot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Talk to a chatbot for me" on Brain ([Chatbot]; the owner's decisions of
 * 2026-09-27 and 2026-09-28) - the desktop's Brain -> Work -> the same card,
 * in the same words.
 *
 * No conversation going: the form - which chatbot, the goal (marked "these
 * words will be sent"), the most messages and minutes within the version's
 * caps, never-send words - and Start, which asks the PC for ONE approval card
 * (answered in the Inbox like any other; nothing is sent before a yes).
 * One going: its state in the PC's words, the counts, Pause / Resume / Stop,
 * Change limits (a NEW card), the chatbot's question about the owner if it
 * asked one (never answered by Jarvis), and the transcript - the chatbot's
 * words in an outlined plate marked "outside text". After it ends: the
 * summary, kept on screen. Nothing here is read aloud.
 *
 * While a conversation is going [JarvisRuntime.watchChatbot] keeps the
 * ongoing notification in step and ticks [JarvisRuntime.chatbotTick], which
 * makes this plate read again. While "Hide memory lists and chat history" is
 * on, the goal, the never-send words, the transcript and the summary are not
 * drawn (the desktop's Rust takes them out; here the plate leaves them out).
 */
@Composable
internal fun ChatbotSection(
    canAct: Boolean,
    privateHidden: Boolean = false,
    onOpenApprovals: ((cardId: String?) -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.chatbotTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Chatbot.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var gone by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var which by remember { mutableStateOf("") }
    var goal by remember { mutableStateOf("") }
    var messages by remember { mutableStateOf("") }
    var minutes by remember { mutableStateOf("") }
    var never by remember { mutableStateOf("") }
    var newMessages by remember { mutableStateOf("") }
    var newMinutes by remember { mutableStateOf("") }
    var newNever by remember { mutableStateOf("") }
    var limitsFor by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.chatbotStatus(null)) {
            is ApiResult.Ok -> {
                val latest = Chatbot.parse(r.value)
                if (latest == null) {
                    missing = true
                } else {
                    missing = false
                    gone = false
                    var shown: Chatbot.View = latest
                    val last = JarvisRuntime.chatbotLastId
                    if (latest.session == null && last != null) {
                        val named = JarvisRuntime.chatbotStatus(last)
                        val nv = (named as? ApiResult.Ok)?.let { Chatbot.parse(it.value) }
                        if (nv?.session != null) {
                            shown = nv
                        } else if (named is ApiResult.Ok) {
                            gone = true
                            JarvisRuntime.chatbotLastId = null
                        }
                    }
                    val s = shown.session
                    if (s != null) {
                        JarvisRuntime.chatbotLastId = s.id
                        if (s.live) JarvisRuntime.watchChatbot()
                        if (limitsFor != s.id) {
                            limitsFor = s.id
                            newMessages = s.max.toString()
                            newMinutes = s.maxMinutes.toString()
                            newNever = s.never.joinToString(", ")
                        }
                    }
                    if (messages.isEmpty()) messages = shown.tier.turnsDefault.toString()
                    if (minutes.isEmpty()) minutes = shown.tier.minutesDefault.toString()
                    if (shown.chatbots.none { it.id == which && it.built }) {
                        which = (shown.chatbots.firstOrNull { it.built } ?: shown.chatbots.firstOrNull())
                            ?.id ?: ""
                    }
                    view = shown
                }
                readError = null
            }
            is ApiResult.Failed -> if (Chatbot.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
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
                reads += 1
            }
        }
    }

    Section(Chatbot.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Chatbot.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            val v = view
            val err = readError
            when {
                missing -> Text(Chatbot.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null -> Text(
                    if (err != null) "Couldn't read it: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    val version = Chatbot.versionLine(v)
                    if (version.isNotEmpty()) {
                        Text(version, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    if (err != null) {
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (!v.anyBuilt) {
                        Text(Chatbot.NONE_BUILT, style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk)
                    }
                    if (gone) {
                        Text(Chatbot.GONE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(6)
                    val s = v.session
                    if (s != null) {
                        SessionPart(
                            v = v, s = s, canAct = canAct, busy = busy, privateHidden = privateHidden,
                            newMessages = newMessages, newMinutes = newMinutes, newNever = newNever,
                            onNewMessages = { newMessages = it.filter(Char::isDigit).take(3) },
                            onNewMinutes = { newMinutes = it.filter(Char::isDigit).take(3) },
                            onNewNever = { newNever = it.take(600) },
                            onAction = { action ->
                                perform {
                                    when (action) {
                                        "pause" -> JarvisRuntime.chatbotPause()
                                        "resume" -> JarvisRuntime.chatbotResume()
                                        else -> JarvisRuntime.chatbotStop(s.id)
                                    }
                                }
                            },
                            onLimits = {
                                val m = Chatbot.limitOf(newMessages, v.tier.turnsMax)
                                val n = Chatbot.limitOf(newMinutes, v.tier.minutesMax)
                                if (m == null || n == null) {
                                    said = "Most messages: 1 to ${v.tier.turnsMax}; most minutes: 1 to " +
                                        "${v.tier.minutesMax}."
                                } else {
                                    // While the words are hidden the box is not drawn:
                                    // keep the PC's list as it is.
                                    val words = if (privateHidden) null else Chatbot.neverWords(newNever)
                                    perform { JarvisRuntime.chatbotLimits(s.id, m, n, words) }
                                }
                            },
                        )
                    }
                    if (s == null || !s.live) {
                        if (s != null) Gap(12)
                        FormPart(
                            v = v, which = which, goal = goal, messages = messages, minutes = minutes,
                            never = never, canAct = canAct, busy = busy,
                            onWhich = { which = it },
                            onGoal = { goal = it.take(Chatbot.MAX_GOAL_CHARS) },
                            onMessages = { messages = it.filter(Char::isDigit).take(3) },
                            onMinutes = { minutes = it.filter(Char::isDigit).take(3) },
                            onNever = { never = it.take(600) },
                            onStart = {
                                val problem = Chatbot.formProblem(v, which, goal, messages, minutes)
                                if (problem != null) {
                                    said = problem
                                } else {
                                    perform {
                                        JarvisRuntime.chatbotStart(
                                            which, goal, Chatbot.limitOf(messages, v.tier.turnsMax),
                                            Chatbot.limitOf(minutes, v.tier.minutesMax),
                                            Chatbot.neverWords(never),
                                        ).also { (ok, _) -> if (ok) goal = "" }
                                    }
                                }
                            },
                            onOpenApprovals = onOpenApprovals,
                        )
                    }
                }
            }
            said?.let {
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
            if (!missing && view != null && !canAct) {
                Text(
                    "Not connected to the desktop, so Start, Resume and Change limits wait until " +
                        "the link is back. Stop and Pause still work.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

@Composable
private fun SessionPart(
    v: Chatbot.View,
    s: Chatbot.Session,
    canAct: Boolean,
    busy: Boolean,
    privateHidden: Boolean,
    newMessages: String,
    newMinutes: String,
    newNever: String,
    onNewMessages: (String) -> Unit,
    onNewMinutes: (String) -> Unit,
    onNewNever: (String) -> Unit,
    onAction: (String) -> Unit,
    onLimits: () -> Unit,
) {
    val chrome = LocalChrome.current
    Text(
        if (s.live) Chatbot.talkingLine(s) else "${s.name}: ${Chatbot.statusLine(s)}",
        style = MaterialTheme.typography.bodyMedium,
        color = chrome.textHi,
    )
    if (s.live) {
        Text(Chatbot.statusLine(s), style = MaterialTheme.typography.bodySmall,
            color = if (s.state == "paused") chrome.warnInk else chrome.textMid)
    }
    if (s.state != "refused") {
        Text(Chatbot.progressLine(s), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    if (s.tierName.isNotEmpty()) {
        Text("${Chatbot.VERSION}: ${s.tierName}", style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo)
    }
    if (privateHidden) {
        Text(Chatbot.HIDDEN, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    } else if (s.goal.isNotEmpty()) {
        Text("Your goal (sent word for word): ${s.goal}", style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid)
    }
    if (s.question.isNotEmpty() && !privateHidden) {
        Gap(6)
        Plate(outline = chrome.warnInk) {
            Text(Chatbot.QUESTION_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
            Text(s.question, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
            Text(Chatbot.QUESTION_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
    val actions = Chatbot.actionsOf(s)
    if (actions.isNotEmpty()) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            actions.forEach { action ->
                val held = action in Chatbot.HELD_WHEN_STALE && !canAct
                Quiet(
                    Chatbot.labelOf(action),
                    color = if (action == "stop") chrome.badInk else null,
                    enabled = !busy && !held,
                    onClick = { onAction(action) },
                )
            }
        }
    }
    if (s.state == "running" || s.state == "paused") {
        Gap(6)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextInput(
                value = newMessages,
                onValueChange = onNewMessages,
                label = Chatbot.MESSAGES_LABEL,
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number,
                    imeAction = ImeAction.Next),
            )
            TextInput(
                value = newMinutes,
                onValueChange = onNewMinutes,
                label = Chatbot.MINUTES_LABEL,
                modifier = Modifier.weight(1f),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number,
                    imeAction = ImeAction.Done),
            )
        }
        if (!privateHidden) {
            TextInput(
                value = newNever,
                onValueChange = onNewNever,
                label = Chatbot.NEVER_LABEL,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            )
        }
        Quiet(
            Chatbot.CHANGE_LIMITS,
            enabled = canAct && !busy && !v.limits.waiting,
            onClick = onLimits,
        )
        Text(Chatbot.LIMITS_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        if (v.limits.waiting) {
            Text("A card for new limits is waiting for your answer.",
                style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        } else if (v.limits.said.isNotEmpty()) {
            Text(v.limits.said, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
    }
    val summary = s.summary
    if (summary != null && !privateHidden) {
        Gap(8)
        Plate(outline = chrome.warnInk) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(Chatbot.SUMMARY_TITLE, style = MaterialTheme.typography.labelMedium,
                    color = chrome.textMid)
                Pill("outside text", color = chrome.warnInk)
            }
            Text(Chatbot.SUMMARY_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            if (summary.answer.isNotEmpty()) {
                Text(summary.answer, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
            }
            summary.claims.forEach { c ->
                Text(
                    "• ${c.claim} - ${if (c.sourced) Chatbot.CLAIM_SOURCED else Chatbot.CLAIM_UNSOURCED}",
                    style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                )
            }
            if (summary.open.isNotEmpty()) {
                Text(Chatbot.OPEN_TITLE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                summary.open.forEach {
                    Text("• $it", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
            }
        }
    }
    if (s.transcript.isNotEmpty() && !privateHidden) {
        Gap(8)
        Text(Chatbot.TRANSCRIPT_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
        Text(Chatbot.OUTSIDE_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        s.transcript.forEach { t ->
            Gap(4)
            if (t.outside) {
                Plate(outline = chrome.warnInk) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(s.name, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Pill("outside text", color = chrome.warnInk)
                    }
                    Text(t.text, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                }
            } else {
                Text("Jarvis, message ${t.n}", style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo)
                Text(t.text, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }
    }
}

@Composable
private fun FormPart(
    v: Chatbot.View,
    which: String,
    goal: String,
    messages: String,
    minutes: String,
    never: String,
    canAct: Boolean,
    busy: Boolean,
    onWhich: (String) -> Unit,
    onGoal: (String) -> Unit,
    onMessages: (String) -> Unit,
    onMinutes: (String) -> Unit,
    onNever: (String) -> Unit,
    onStart: () -> Unit,
    onOpenApprovals: ((cardId: String?) -> Unit)?,
) {
    val chrome = LocalChrome.current
    Text(Chatbot.CHATBOT_LABEL, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        v.chatbots.forEach { c ->
            Quiet(
                if (c.built) (if (c.id == which) "✓ ${c.name}" else c.name)
                else "${c.name} - ${c.note.ifEmpty { "Not built yet." }}",
                enabled = c.built && !busy,
                onClick = { onWhich(c.id) },
            )
        }
    }
    TextInput(
        value = goal,
        onValueChange = onGoal,
        label = Chatbot.GOAL_LABEL,
        supportingText = Chatbot.GOAL_NOTE,
        supportingColor = chrome.warnInk,
        singleLine = false,
        maxLines = 6,
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextInput(
            value = messages,
            onValueChange = onMessages,
            label = Chatbot.MESSAGES_LABEL,
            modifier = Modifier.weight(1f),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number,
                imeAction = ImeAction.Next),
        )
        TextInput(
            value = minutes,
            onValueChange = onMinutes,
            label = Chatbot.MINUTES_LABEL,
            modifier = Modifier.weight(1f),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number,
                imeAction = ImeAction.Next),
        )
    }
    TextInput(
        value = never,
        onValueChange = onNever,
        label = Chatbot.NEVER_LABEL,
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
    )
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Quiet(
            if (busy) "Asking…" else Chatbot.START,
            enabled = canAct && !busy && v.anyBuilt,
            onClick = onStart,
        )
        if (onOpenApprovals != null) {
            Quiet("Open the Inbox", enabled = !busy, onClick = { onOpenApprovals(null) })
        }
    }
    Text(Chatbot.START_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    Text(Chatbot.SIGN_IN_PC, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
}
