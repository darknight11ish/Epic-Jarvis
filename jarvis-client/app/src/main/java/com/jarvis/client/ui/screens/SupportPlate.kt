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
import com.jarvis.client.net.Support
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Chat with customer support for me" on Brain ([Support]; the owner's
 * decisions of 2026-09-28) - the desktop's Brain -> Work -> the same card,
 * in the same words.
 *
 * No chat going: the form - the company (Groupon, or another company's help
 * page typed by the owner) with its terms risk, the goal, the details Jarvis
 * may give as name-and-value rows, and the limits - and Start, which asks
 * the PC for ONE approval card listing every detail (nothing is sent before
 * a yes). One going: its state in the PC's words (waiting for the owner to
 * open the chat on the PC, the queue, the agent's name), Take over / Resume
 * / Stop, a question handed to the owner ("are you a bot?", an identity
 * check, a detail not on the card - answered by the owner in the window on
 * the PC, never by Jarvis), a waiting offer with its words and the exact
 * reply its card would send, and Decline / Say something else / Take over -
 * never an Accept: accepting is only ever the offer's own approval card.
 * The transcript shows the company's words in the outlined outside-text
 * plate. After it ends: the summary, the reference number and whether it
 * was kept in the encrypted history. Export is on the PC only. Nothing here
 * is read aloud.
 *
 * While a chat is going [JarvisRuntime.watchSupport] keeps the ongoing
 * notification in step and ticks [JarvisRuntime.supportTick]. While "Hide
 * memory lists and chat history" is on, the goal, the details, the question,
 * the offer's words, the transcript and the summary are not drawn.
 */
@Composable
internal fun SupportSection(
    canAct: Boolean,
    privateHidden: Boolean = false,
    onOpenHistory: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.supportTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Support.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var gone by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var company by remember { mutableStateOf("") }
    var address by remember { mutableStateOf("") }
    var goal by remember { mutableStateOf("") }
    var rows by remember { mutableStateOf(listOf(Support.Detail("", ""))) }
    var messages by remember { mutableStateOf("") }
    var minutes by remember { mutableStateOf("") }
    var queue by remember { mutableStateOf("") }
    var sayText by remember { mutableStateOf("") }
    var sayOpen by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        when (val r = JarvisRuntime.supportStatus(null)) {
            is ApiResult.Ok -> {
                val latest = Support.parse(r.value)
                if (latest == null) {
                    missing = true
                } else {
                    missing = false
                    gone = false
                    var shown = latest
                    val last = JarvisRuntime.supportLastId
                    if (latest.chat == null && last != null) {
                        val named = JarvisRuntime.supportStatus(last)
                        val nv = (named as? ApiResult.Ok)?.let { Support.parse(it.value) }
                        if (nv?.chat != null) {
                            shown = nv
                        } else if (named is ApiResult.Ok) {
                            gone = true
                            JarvisRuntime.supportLastId = null
                        }
                    }
                    val sc = shown.chat
                    if (sc != null) {
                        JarvisRuntime.supportLastId = sc.id
                        if (sc.live) JarvisRuntime.watchSupport() else sayOpen = false
                    }
                    if (messages.isEmpty()) messages = shown.tier.messagesDefault.toString()
                    if (minutes.isEmpty()) minutes = shown.tier.minutesDefault.toString()
                    if (queue.isEmpty()) queue = shown.tier.queueDefault.toString()
                    if (shown.companies.none { it.id == company }) {
                        company = shown.companies.firstOrNull()?.id ?: ""
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

    Section(Support.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Support.DETAIL, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            val v = view
            val err = readError
            when {
                missing -> Text(Support.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                v == null && err != null -> Text("Could not read it: $err",
                    style = MaterialTheme.typography.bodySmall, color = chrome.badInk)
                v == null -> Text("Reading…", style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo)
                else -> {
                    val line = Support.versionLine(v)
                    if (line.isNotEmpty()) {
                        Text(line, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    if (err != null) {
                        Text("Could not read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.badInk)
                    }
                    if (gone) {
                        Text(Support.GONE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    val c = v.chat
                    if (c != null) {
                        ChatPart(c, canAct, busy, privateHidden, sayOpen, sayText,
                            onOpenHistory = onOpenHistory,
                            onSayText = { sayText = it },
                            onAction = { action ->
                                when (action) {
                                    "take_over" -> perform { JarvisRuntime.supportTakeover(c.id) }
                                    "resume" -> perform { JarvisRuntime.chatbotResume() }
                                    "stop" -> perform { JarvisRuntime.supportStop(c.id) }
                                    "decline" -> c.offer?.let { o ->
                                        perform { JarvisRuntime.supportAnswer(c.id, o.id, "decline", null) }
                                    }
                                    "offer_take_over" -> c.offer?.let { o ->
                                        perform { JarvisRuntime.supportAnswer(c.id, o.id, "takeover", null) }
                                    }
                                    "say_else" -> { sayOpen = !sayOpen }
                                    "say_send" -> c.offer?.let { o ->
                                        perform {
                                            JarvisRuntime.supportAnswer(c.id, o.id, "say", sayText).also {
                                                if (it.first) {
                                                    sayText = ""
                                                    sayOpen = false
                                                }
                                            }
                                        }
                                    }
                                }
                            })
                    }
                    if (c == null || !c.live) {
                        if (c != null) Gap(10)
                        FormPart(
                            v, company, address, goal, rows, messages, minutes, queue, canAct, busy,
                            onCompany = { company = it },
                            onAddress = { address = it },
                            onGoal = { goal = it },
                            onRows = { rows = it },
                            onMessages = { messages = it },
                            onMinutes = { minutes = it },
                            onQueue = { queue = it },
                            onStart = {
                                val problem = Support.formProblem(v, company, address, goal, rows,
                                    messages, minutes, queue)
                                if (problem != null) {
                                    said = problem
                                } else {
                                    perform {
                                        JarvisRuntime.supportStart(
                                            company,
                                            address.takeIf { v.companies.firstOrNull { x -> x.id == company }?.typed == true },
                                            goal,
                                            rows,
                                            Support.limitOf(messages, v.tier.messagesMax),
                                            Support.limitOf(minutes, v.tier.minutesMax),
                                            Support.limitOf(queue, v.tier.queueMax),
                                        ).also { (ok, _) ->
                                            if (ok) {
                                                goal = ""
                                                rows = listOf(Support.Detail("", ""))
                                            }
                                        }
                                    }
                                }
                            },
                        )
                    }
                }
            }
            said?.let {
                Gap(4)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
        }
    }
}

@Composable
private fun ChatPart(
    c: Support.Chat,
    canAct: Boolean,
    busy: Boolean,
    privateHidden: Boolean,
    sayOpen: Boolean,
    sayText: String,
    onSayText: (String) -> Unit,
    onAction: (String) -> Unit,
    onOpenHistory: (() -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    Text(
        if (c.live) Support.talkingLine(c) else "${c.companyName}: ${Support.statusLine(c)}",
        style = MaterialTheme.typography.bodyMedium,
        color = chrome.textHi,
    )
    if (c.live) {
        Text(Support.statusLine(c), style = MaterialTheme.typography.bodySmall,
            color = if (c.state == "paused") chrome.warnInk else chrome.textMid)
    }
    // "Solve it here": paused at a captcha, a sign-in page or an "unusual
    // activity" page (com.jarvis.client.net.Handoff).
    val waiting by JarvisRuntime.handoffOffer.collectAsState()
    if (c.state == "paused" && waiting?.kind == "support" && waiting?.id == c.id) {
        Quiet(com.jarvis.client.net.Handoff.HERE_BUTTON, onClick = { JarvisRuntime.openHandoff() })
    }
    if (c.state != "refused") {
        Text(Support.progressLine(c), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    if (c.tierName.isNotEmpty()) {
        Text("${Support.VERSION}: ${c.tierName}", style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo)
    }
    if (privateHidden) {
        Text(Support.HIDDEN, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    } else {
        if (c.goal.isNotEmpty()) {
            Text("Your goal: ${c.goal}", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        if (c.details.isNotEmpty()) {
            Text("Jarvis may give: " + c.details.joinToString("; ") { "${it.name}: ${it.value}" },
                style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        if (c.question.isNotEmpty()) {
            Gap(6)
            Plate(outline = chrome.warnInk) {
                Text(Support.QUESTION_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                Text(c.question, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                Text(Support.QUESTION_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            }
        }
        val o = c.offer
        if (o != null) {
            Gap(6)
            Plate(outline = chrome.warnInk) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(Support.OFFER_TITLE, style = MaterialTheme.typography.labelMedium,
                        color = chrome.textMid)
                    Pill("outside text", color = chrome.warnInk)
                }
                Text(o.words, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                Text("If you approve the card, Jarvis sends: \"${o.reply}\"",
                    style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                Text(Support.OFFER_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                if (o.card == "no") {
                    Text(Support.OFFER_CARD_NO, style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk)
                }
                val hold = Support.holdingLine(c)
                if (hold.isNotEmpty()) {
                    Text(hold, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
                if (o.said.isNotEmpty()) {
                    Text(o.said, style = MaterialTheme.typography.labelSmall, color = chrome.badInk)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Support.offerActions(c).forEach { action ->
                        // Decline sends words: held on a stale link. Take over
                        // only makes Jarvis do less.
                        val held = action == "decline" && !canAct
                        Quiet(
                            Support.labelOf(action),
                            enabled = !busy && !held,
                            onClick = { onAction(if (action == "take_over") "offer_take_over" else action) },
                        )
                    }
                }
                if (sayOpen) {
                    TextInput(
                        value = sayText,
                        onValueChange = onSayText,
                        label = Support.SAY_ELSE,
                        supportingText = Support.SAY_NOTE,
                        singleLine = false,
                        maxLines = 4,
                    )
                    Quiet(Support.SAY_SEND, enabled = canAct && !busy && sayText.isNotBlank(),
                        onClick = { onAction("say_send") })
                }
            }
        }
    }
    val actions = Support.actionsOf(c)
    if (actions.isNotEmpty()) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            actions.forEach { action ->
                val held = action == "resume" && !canAct
                Quiet(
                    Support.labelOf(action),
                    color = if (action == "stop") chrome.badInk else null,
                    enabled = !busy && !held,
                    onClick = { onAction(action) },
                )
            }
        }
        if ("take_over" in actions) {
            Text(Support.TAKE_OVER_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
    if (privateHidden) return
    val sm = c.summary
    if (sm != null) {
        Gap(8)
        Plate(outline = chrome.warnInk) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(Support.SUMMARY_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                Pill("outside text", color = chrome.warnInk)
            }
            Text(Support.SUMMARY_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            if (sm.answer.isNotEmpty()) {
                Text(sm.answer, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
            }
            if (sm.agreed.isNotEmpty()) {
                Text(Support.AGREED_TITLE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                sm.agreed.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall, color = chrome.textMid) }
            }
            if (sm.open.isNotEmpty()) {
                Text(Support.OPEN_TITLE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                sm.open.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall, color = chrome.textMid) }
            }
        }
    }
    if (!c.live) {
        if (c.reference.isNotEmpty()) {
            Text(Support.REFERENCE_LINE.replace("{reference}", c.reference),
                style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        val saved = Support.savedLine(c)
        if (saved.isNotEmpty()) {
            Text(saved, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            // A way to the kept record (the second chat audit, phone C5).
            if (c.saved == "yes" && !privateHidden && onOpenHistory != null) {
                Quiet(Chatbot.HISTORY_OPEN, onClick = onOpenHistory)
            }
        }
    }
    if (c.transcript.isNotEmpty()) {
        Gap(8)
        Text(Support.TRANSCRIPT_TITLE, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
        Text(Support.OUTSIDE_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        c.transcript.forEach { t -> SupportTurn(c, t) }
        Text(Support.EXPORT_PC_ONLY, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
}

/** One line: the owner's side plainly, the company's in the outlined outside-text plate. */
@Composable
private fun SupportTurn(c: Support.Chat, t: Support.Turn) {
    val chrome = LocalChrome.current
    Gap(4)
    if (t.outside) {
        Plate(outline = chrome.warnInk) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(Support.whoOf(t, c), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                Pill("outside text", color = chrome.warnInk)
            }
            Text(t.text, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        }
    } else {
        Text(Support.whoOf(t, c), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Text(t.text, style = MaterialTheme.typography.bodySmall,
            color = if (t.who == "note") chrome.textLo else chrome.textMid)
    }
}

@Composable
private fun FormPart(
    v: Support.View,
    company: String,
    address: String,
    goal: String,
    rows: List<Support.Detail>,
    messages: String,
    minutes: String,
    queue: String,
    canAct: Boolean,
    busy: Boolean,
    onCompany: (String) -> Unit,
    onAddress: (String) -> Unit,
    onGoal: (String) -> Unit,
    onRows: (List<Support.Detail>) -> Unit,
    onMessages: (String) -> Unit,
    onMinutes: (String) -> Unit,
    onQueue: (String) -> Unit,
    onStart: () -> Unit,
) {
    val chrome = LocalChrome.current
    Text(Support.COMPANY_LABEL, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
    v.companies.forEach { co ->
        Quiet(if (co.id == company) "✓ ${co.name}" else co.name, enabled = !busy,
            onClick = { onCompany(co.id) })
    }
    val co = v.companies.firstOrNull { it.id == company }
    if (co != null && co.terms.isNotEmpty()) {
        Text("${Support.TERMS_TITLE}: ${co.terms}", style = MaterialTheme.typography.labelSmall,
            color = chrome.warnInk)
    }
    if (co?.typed == true) {
        TextInput(
            value = address,
            onValueChange = onAddress,
            label = Support.ADDRESS_LABEL,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
        )
    }
    TextInput(
        value = goal,
        onValueChange = onGoal,
        label = Support.GOAL_LABEL,
        supportingText = Support.GOAL_NOTE,
        singleLine = false,
        maxLines = 6,
    )
    Text(Support.DETAILS_LABEL, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
    rows.forEachIndexed { i, r ->
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextInput(
                value = r.name,
                onValueChange = { n -> onRows(rows.mapIndexed { j, x -> if (j == i) x.copy(name = n) else x }) },
                label = Support.DETAIL_NAME,
                modifier = Modifier.weight(1f),
            )
            TextInput(
                value = r.value,
                onValueChange = { n -> onRows(rows.mapIndexed { j, x -> if (j == i) x.copy(value = n) else x }) },
                label = Support.DETAIL_VALUE,
                modifier = Modifier.weight(1f),
            )
        }
        Quiet(Support.REMOVE_DETAIL, enabled = !busy, onClick = {
            val left = rows.filterIndexed { j, _ -> j != i }
            onRows(left.ifEmpty { listOf(Support.Detail("", "")) })
        })
    }
    Quiet(Support.ADD_DETAIL, enabled = !busy && rows.size < Support.MAX_DETAILS,
        onClick = { onRows(rows + Support.Detail("", "")) })
    Text(Support.DETAILS_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextInput(
            value = messages,
            onValueChange = onMessages,
            label = Support.MESSAGES_LABEL,
            modifier = Modifier.weight(1f),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Next),
        )
        TextInput(
            value = minutes,
            onValueChange = onMinutes,
            label = Support.MINUTES_LABEL,
            modifier = Modifier.weight(1f),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Next),
        )
    }
    TextInput(
        value = queue,
        onValueChange = onQueue,
        label = Support.QUEUE_LABEL,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
    )
    Quiet(
        if (busy) "Asking…" else Support.START,
        enabled = canAct && !busy,
        onClick = onStart,
    )
    Text(Support.START_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    Text(Support.SIGN_IN_PC, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
}
