package com.jarvis.client.ui.screens

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ChatLog
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

/**
 * Chat history on the PC ([ChatLog], docs/JARVIS-API.md section 18) - the
 * phone's History screen, opened from Mind.
 *
 * - The switch, "Keep chat history on this PC". Turning it ON raises an
 *   approval card on the PC and reads "Waiting for your approval" while
 *   that card is in the queue, exactly as the learning switch does; it is
 *   held on a stale link (rule 4). OFF is immediate and never held.
 * - "Delete conversations older than": Never / 30 days / 90 days / 1 year.
 *   A choice that deletes something now asks first.
 * - The list, newest first, with "Load older". Open one to read it; delete
 *   one after a confirm. There is no "delete all" - not here, not on the PC.
 *
 * Everything is read from the PC when the screen opens and dropped when it
 * is left. The phone keeps no history of its own.
 *
 * "Hide memory lists and chat history" (Security) hides the list and any open conversation
 * until Show is confirmed, the same as Mind's memory lists. The settings
 * stay visible: they say nothing about what was said.
 */
@Composable
fun HistoryScreen(
    /** The link is up and fresh. Only turning the switch ON waits for it. */
    canAct: Boolean,
    onBack: () -> Unit,
    privateHidden: Boolean = false,
    onShowPrivate: () -> Unit = {},
    showPrivateBusy: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var reads by remember { mutableIntStateOf(0) }
    var status by remember { mutableStateOf<ChatLog.Status?>(null) }
    var rows by remember { mutableStateOf<List<ChatLog.Summary>?>(null) }
    var mayHaveOlder by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var loadingOlder by remember { mutableStateOf(false) }
    // One settings request at a time, and what it came back with.
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    // A keep choice that deletes something now, waiting for "yes".
    var keepToConfirm by remember { mutableStateOf<Int?>(null) }
    // The conversation open for reading. Saveable, so a rotation keeps it open.
    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    var listSaid by remember { mutableStateOf<String?>(null) }

    val queue by JarvisRuntime.pending.collectAsState()
    val cardInQueue = ChatLog.cardWaiting(queue.map { it.action })
    // The ON card leaving the queue (approved, denied or expired) reads the
    // switch again, so the line says what really happened.
    var sawCard by remember { mutableStateOf(false) }
    LaunchedEffect(cardInQueue) {
        if (cardInQueue) {
            sawCard = true
        } else if (sawCard) {
            sawCard = false
            reads += 1
        }
    }
    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.history()) {
            is ApiResult.Ok -> {
                val page = ChatLog.page(r.value)
                status = page.status
                rows = page.conversations
                mayHaveOlder = page.mayHaveOlder
                readError = null
            }
            is ApiResult.Failed -> readError = ChatLog.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
    }

    // Back closes an open conversation first, then leaves History.
    val open = openId
    BackHandler(enabled = open != null) { openId = null }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar(
            if (open == null) "History" else "Conversation",
            onBack = { if (openId != null) openId = null else onBack() },
            subtitle = "Chat history, kept on your PC",
        ) {
            if (open == null) Quiet("Refresh", onClick = { reads += 1 })
        }

        if (open != null) {
            if (privateHidden) {
                Column(Modifier.fillMaxWidth().weight(1f).padding(16.dp)) {
                    HiddenSection("Conversation", busy = showPrivateBusy, onShow = onShowPrivate)
                }
            } else {
                Conversation(
                    id = open,
                    modifier = Modifier.weight(1f),
                    onDeleted = { id, sentence ->
                        rows = rows?.filterNot { it.id == id }
                        listSaid = sentence
                        openId = null
                    },
                )
            }
            return@Column
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item(key = "settings") {
                val switch = ChatLog.switchState(status, cardInQueue)
                Section("Chat history") {
                    Plate {
                        SwitchRow(
                            title = ChatLog.SWITCH,
                            detail = ChatLog.UNDER,
                            checked = switch == ChatLog.Switch.ON,
                            // OFF always goes; ON waits for a live link. Not
                            // while a card is already up, or before the PC
                            // has said which way it is.
                            enabled = !busy && when (switch) {
                                ChatLog.Switch.ON -> true
                                ChatLog.Switch.OFF -> canAct
                                ChatLog.Switch.WAITING, ChatLog.Switch.UNKNOWN -> false
                            },
                            onChange = { want ->
                                busy = true
                                said = null
                                scope.launch {
                                    try {
                                        said = JarvisRuntime.setHistory(want)
                                    } finally {
                                        busy = false
                                        reads += 1
                                    }
                                }
                            },
                        )
                        Gap(4)
                        Text(
                            if (busy) "Asking your PC…" else ChatLog.stateLine(switch, status),
                            style = MaterialTheme.typography.bodySmall,
                            color = when {
                                busy -> chrome.textMid
                                switch == ChatLog.Switch.WAITING -> chrome.warnInk
                                switch == ChatLog.Switch.ON && status?.recording == false -> chrome.warnInk
                                else -> chrome.textMid
                            },
                        )
                        said?.let {
                            Text(
                                it,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                                modifier = Modifier.liveStatus(),
                            )
                        }
                        Gap(12)
                        val kept = status?.keepDays
                        Setting(
                            ChatLog.KEEP_TITLE,
                            caption = "Counted from a conversation's last message. Checked when " +
                                "Jarvis starts and once a day.",
                        ) {
                            Choices(
                                options = ChatLog.KEEP_DAYS,
                                isSelected = { it == kept },
                                label = { ChatLog.keepLabel(it) },
                                enabled = !busy && status != null,
                                onPick = { days ->
                                    if (days == kept) {
                                        keepToConfirm = null
                                    } else if (ChatLog.keepNeedsConfirm(kept, days)) {
                                        keepToConfirm = days
                                    } else {
                                        keepToConfirm = null
                                        busy = true
                                        said = null
                                        scope.launch {
                                            try {
                                                said = JarvisRuntime.setHistoryKeepDays(days)
                                            } finally {
                                                busy = false
                                                reads += 1
                                            }
                                        }
                                    }
                                },
                            )
                        }
                        keepToConfirm?.let { days ->
                            Gap(6)
                            Text(
                                ChatLog.keepConfirm(days),
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk,
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Quiet("Yes, delete them", color = chrome.badInk, enabled = !busy, onClick = {
                                    keepToConfirm = null
                                    busy = true
                                    said = null
                                    scope.launch {
                                        try {
                                            said = JarvisRuntime.setHistoryKeepDays(days)
                                        } finally {
                                            busy = false
                                            reads += 1
                                        }
                                    }
                                })
                                Quiet("Keep them", onClick = { keepToConfirm = null })
                            }
                        }
                    }
                }
            }

            if (privateHidden) {
                item(key = "hidden") {
                    HiddenSection("Conversations", busy = showPrivateBusy, onShow = onShowPrivate)
                }
            } else {
                val shown = rows
                val err = readError
                item(key = "list-head") {
                    Column(Modifier.fillMaxWidth()) {
                        Kicker("Conversations")
                        Gap(6)
                        when {
                            shown == null -> Text(
                                if (err != null) "Couldn't read your chat history: $err" else "Reading…",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (err != null) chrome.warnInk else chrome.textLo,
                            )
                            shown.isEmpty() -> Text(
                                ChatLog.EMPTY,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        }
                        if (shown != null && err != null) {
                            Text(
                                "Couldn't read it again: $err",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.warnInk,
                            )
                        }
                        listSaid?.let {
                            Text(
                                it,
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                                modifier = Modifier.liveStatus(),
                            )
                        }
                    }
                }
                if (shown != null) {
                    items(shown, key = { "c-" + it.id }) { row ->
                        ConversationRow(row, onOpen = { openId = row.id })
                    }
                    if (mayHaveOlder && shown.isNotEmpty()) {
                        item(key = "older") {
                            Quiet(
                                if (loadingOlder) "Loading…" else "Load older",
                                enabled = !loadingOlder,
                                onClick = {
                                    val before = ChatLog.olderThan(shown)
                                    if (before == null) {
                                        mayHaveOlder = false
                                    } else {
                                        loadingOlder = true
                                        scope.launch {
                                            try {
                                                when (val r = JarvisRuntime.history(before)) {
                                                    is ApiResult.Ok -> {
                                                        val page = ChatLog.page(r.value)
                                                        val had = rows.orEmpty()
                                                        val next = ChatLog.append(had, page.conversations)
                                                        rows = next
                                                        // No progress means no more to load.
                                                        mayHaveOlder = page.mayHaveOlder && next.size > had.size
                                                        readError = null
                                                    }
                                                    is ApiResult.Failed -> readError =
                                                        ChatLog.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
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

            item(key = "tail") { Gap(24) }
        }
    }
}

/** One row of the list: the title, when and where, and its marks in words. */
@Composable
private fun ConversationRow(row: ChatLog.Summary, onOpen: () -> Unit) {
    val chrome = LocalChrome.current
    val zone = remember { ZoneId.systemDefault() }
    val today = LocalDate.now(zone)
    Plate(Modifier.pressable(onClick = onOpen)) {
        Text(row.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi, maxLines = 2)
        Gap(2)
        Text(
            ChatLog.rowLine(row, zone, today),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        if (row.hasVoice || row.tainted) {
            Gap(4)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (row.hasVoice) Pill(ChatLog.VOICE_MARK)
                if (row.tainted) Pill(ChatLog.TAINT_MARK, color = chrome.warnInk)
            }
        }
    }
}

/**
 * One conversation, read-only, with Delete behind a confirm. Read from the
 * PC when opened; nothing of it is kept once it is closed.
 */
// FlowRow: a turn's marks ("said aloud, but not confirmed by this PC",
// "read outside text") wrap to a new line instead of being squeezed. The
// opt-in is kept for the reason BrainScreen's FlowChips gives.
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Conversation(
    id: String,
    modifier: Modifier,
    onDeleted: (id: String, sentence: String) -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val zone = remember { ZoneId.systemDefault() }
    val today = LocalDate.now(zone)
    var loaded by remember(id) { mutableStateOf<ChatLog.Transcript?>(null) }
    var err by remember(id) { mutableStateOf<String?>(null) }
    var confirm by remember(id) { mutableStateOf(false) }
    var busy by remember(id) { mutableStateOf(false) }
    var said by remember(id) { mutableStateOf<String?>(null) }
    LaunchedEffect(id) {
        when (val r = JarvisRuntime.historyConversation(id)) {
            is ApiResult.Ok -> {
                val t = ChatLog.transcript(r.value)
                if (t == null) err = "Your PC sent something this app could not read." else loaded = t
            }
            is ApiResult.Failed -> err = ChatLog.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
        }
    }

    LazyColumn(
        modifier.fillMaxWidth(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "head") {
            Plate {
                val t = loaded
                Text(
                    t?.title ?: if (err != null) "Couldn't open it: $err" else "Reading…",
                    style = MaterialTheme.typography.titleSmall,
                    color = if (t == null && err != null) chrome.warnInk else chrome.textHi,
                )
                if (t != null && t.tainted) {
                    Gap(4)
                    Text(ChatLog.TAINT_LINE, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                }
                Gap(6)
                if (confirm) {
                    Text(ChatLog.DELETE_CONFIRM, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Quiet("Yes, delete it", color = chrome.badInk, enabled = !busy, onClick = {
                            confirm = false
                            busy = true
                            scope.launch {
                                try {
                                    val (gone, sentence) = JarvisRuntime.deleteHistory(id)
                                    if (gone) onDeleted(id, sentence) else said = sentence
                                } finally {
                                    busy = false
                                }
                            }
                        })
                        Quiet("Keep it", onClick = { confirm = false })
                    }
                } else {
                    Quiet(
                        if (busy) "Deleting…" else "Delete",
                        color = chrome.badInk,
                        enabled = !busy,
                        onClick = { confirm = true },
                    )
                }
                said?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk,
                        modifier = Modifier.liveStatus())
                }
            }
        }
        val turns = loaded?.turns.orEmpty()
        items(turns.size, key = { "t-$it" }) { i ->
            val turn = turns[i]
            val mine = turn.role == "user"
            Column(Modifier.fillMaxWidth()) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Kicker(if (mine) "You" else "Jarvis")
                    if (mine) {
                        ChatLog.provenanceMark(turn.provenance)?.let { Pill(it) }
                        if (turn.readOutside) Pill(ChatLog.TAINT_MARK, color = chrome.warnInk)
                    }
                }
                Gap(2)
                Text(
                    turn.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (mine) chrome.textHi else chrome.textMid,
                )
                turn.at?.let {
                    Text(
                        ChatLog.whenLine(it, zone, today),
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                if (mine && !turn.answerKept) {
                    Text(
                        ChatLog.NOT_KEPT_LINE,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
            }
        }
        item(key = "tail") { Gap(24) }
    }
}

/**
 * Mind's way in: one plate that opens History. Hidden like the memory lists
 * when "Hide memory lists and chat history" is on - what was said in a chat is at least as
 * private as what Jarvis remembers.
 */
@Composable
internal fun HistoryEntrySection(
    onOpen: () -> Unit,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection("Chat history", busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    Section("Chat history") {
        Plate {
            Text(
                "Your conversations with Jarvis, as your PC keeps them. Read or delete " +
                    "one, or choose whether they are kept and for how long.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(4)
            Quiet("Open History", onClick = onOpen)
        }
    }
}
