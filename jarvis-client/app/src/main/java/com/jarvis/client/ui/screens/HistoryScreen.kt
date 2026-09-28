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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
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
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
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
 * - A search box (the owner's answer of 2026-09-27: "shown on screen only;
 *   nothing saved, nothing handed to the AI"). Since 2026-09-28 (JARVIS-API
 *   section 71) two letters or more ask the PC to search what was SAID
 *   ([JarvisRuntime.historySearch]): each kept turn is opened in the PC's
 *   memory for that one search, with no index and nothing kept, and each
 *   result shows a snippet with the words marked. One letter, or a PC
 *   without the search, narrows the loaded list by title ([ChatLog.filtered]).
 *   The desktop's History does the same (brain.js `onHistorySearch`).
 * - "Find in this chat" in an open conversation: a box, Previous, Next and
 *   "2 of 7", done on the phone over what is already open. Opened from a
 *   search result, it starts with the search words.
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
    // The search box (docs/JARVIS-API.md section 71). Two letters or more:
    // the PC searches what was SAID in the kept chats, opening each in its
    // memory for this one search - no index, nothing kept, nothing handed to
    // the AI. One letter, or a PC without the search: the loaded list, by
    // title. `remember`, not `rememberSaveable`: the words searched for are
    // not put in the saved screen state either.
    var search by remember { mutableStateOf("") }
    var found by remember { mutableStateOf<ChatLog.Search?>(null) }
    var searching by remember { mutableStateOf(false) }
    var searchError by remember { mutableStateOf<String?>(null) }
    var oldPc by remember { mutableStateOf(false) }
    // The words to find at once in the conversation opened from a result.
    var findFirst by remember { mutableStateOf("") }
    val wordSearch = !oldPc && search.trim().length >= ChatLog.SEARCH_MIN
    // Each change of the words (or of the hidden state) starts one search
    // after a short pause; a newer change cancels the older one, answer and
    // all. Nothing is asked while the lists are hidden.
    LaunchedEffect(search, privateHidden, oldPc) {
        found = null
        searchError = null
        if (privateHidden || !wordSearch) {
            searching = false
            return@LaunchedEffect
        }
        searching = true
        delay(350)
        val r = JarvisRuntime.historySearch(search)
        searching = false
        when (r) {
            null -> Unit
            is ApiResult.Ok -> found = ChatLog.search(r.value)
            is ApiResult.Failed -> if (ChatLog.searchMissing(r.error)) {
                oldPc = true
            } else {
                searchError = ChatLog.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
            }
        }
    }

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
                    initialFind = findFirst,
                    modifier = Modifier.weight(1f),
                    onDeleted = { id, sentence ->
                        rows = rows?.filterNot { it.id == id }
                        found = found?.let { f -> f.copy(found = f.found.filterNot { it.row.id == id }) }
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
                // One letter, or a PC without the word search: the box
                // narrows `shown` by title, for display only - paging ("Load
                // older") still works from the full, unfiltered list. Two
                // letters or more: the PC's results replace the list.
                val visible = if (shown != null && !wordSearch) ChatLog.filtered(shown, search) else null
                item(key = "list-head") {
                    Column(Modifier.fillMaxWidth()) {
                        Kicker("Conversations")
                        Gap(6)
                        if (shown != null && shown.isNotEmpty()) {
                            TextInput(
                                value = search,
                                onValueChange = { search = it },
                                placeholder = ChatLog.SEARCH_PLACEHOLDER,
                            )
                            Gap(8)
                        }
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
                            visible != null && visible.isEmpty() -> Text(
                                ChatLog.NO_MATCH,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                        }
                        if (oldPc && search.isNotBlank()) {
                            Text(ChatLog.SEARCH_OLD, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                        }
                        if (wordSearch) {
                            Text(ChatLog.SEARCH_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            Gap(4)
                            val f = found
                            val e = searchError
                            Text(
                                when {
                                    e != null -> "Couldn't search: $e"
                                    searching || f == null -> ChatLog.SEARCHING
                                    !f.queryOk -> f.why ?: ChatLog.SEARCH_NONE
                                    f.found.isEmpty() -> f.whyNot ?: ChatLog.SEARCH_NONE
                                    f.found.size == 1 -> "1 conversation matches."
                                    else -> "${f.found.size} conversations match."
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = if (e != null) chrome.warnInk else chrome.textMid,
                                modifier = Modifier.liveStatus(),
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
                if (wordSearch && !searching) {
                    val f = found
                    if (f != null && f.queryOk) {
                        items(f.found, key = { "f-" + it.row.id }) { hit ->
                            FoundRow(hit, onOpen = {
                                findFirst = search.trim()
                                openId = hit.row.id
                            })
                        }
                        ChatLog.searchMoreLine(f)?.let { more ->
                            item(key = "search-more") {
                                Text(more, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            }
                        }
                    }
                }
                if (visible != null) {
                    items(visible, key = { "c-" + it.id }) { row ->
                        ConversationRow(row, onOpen = {
                            findFirst = ""
                            openId = row.id
                        })
                    }
                    if (mayHaveOlder && shown != null && shown.isNotEmpty()) {
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

/** A matched word: tinted AND underlined, so it never rests on colour alone. */
@Composable
private fun hitStyle(current: Boolean = false): SpanStyle = SpanStyle(
    background = MaterialTheme.colorScheme.primary.copy(alpha = if (current) 0.42f else 0.2f),
    textDecoration = TextDecoration.Underline,
    fontWeight = if (current) FontWeight.Bold else null,
)

/** One search result: the row, then the snippet with the search words marked. */
@Composable
private fun FoundRow(hit: ChatLog.Found, onOpen: () -> Unit) {
    val chrome = LocalChrome.current
    val zone = remember { ZoneId.systemDefault() }
    val today = LocalDate.now(zone)
    val marked = hitStyle()
    val snippet = remember(hit, marked) {
        buildAnnotatedString {
            append(ChatLog.snippetWho(hit.snippet))
            if (hit.snippet.cutBefore) append("…")
            for (p in hit.snippet.parts) {
                if (p.hit) withStyle(marked) { append(p.text) } else append(p.text)
            }
            if (hit.snippet.cutAfter) append("…")
        }
    }
    Plate(Modifier.pressable(onClick = onOpen)) {
        Text(hit.row.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi, maxLines = 2)
        Gap(2)
        Text(
            listOfNotNull(ChatLog.rowLine(hit.row, zone, today), ChatLog.hitsLine(hit.hits)).joinToString(" · "),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Gap(4)
        Text(snippet, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        if (hit.row.hasVoice || hit.row.tainted) {
            Gap(4)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (hit.row.hasVoice) Pill(ChatLog.VOICE_MARK)
                if (hit.row.tainted) Pill(ChatLog.TAINT_MARK, color = chrome.warnInk)
            }
        }
    }
}

/**
 * One conversation, read-only, with Delete behind a confirm. Read from the
 * PC when opened; nothing of it is kept once it is closed.
 *
 * "Find in this chat" (section 71): a box, Previous, Next and "2 of 7",
 * over the conversation already open - the PC is not asked. [initialFind]
 * is the search words when it was opened from a search result.
 */
// FlowRow: a turn's marks ("said aloud, but not confirmed by this PC",
// "read outside text") wrap to a new line instead of being squeezed. The
// opt-in is kept for the reason BrainScreen's FlowChips gives.
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Conversation(
    id: String,
    initialFind: String,
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
    // Deleting a chat offers to forget the facts it taught (docs/JARVIS-API.md
    // section 79): read when Delete is pressed; NONE ticked to start with.
    var taught by remember(id) { mutableStateOf<ChatLog.Taught?>(null) }
    var ticked by remember(id) { mutableStateOf(setOf<Long>()) }
    LaunchedEffect(id, confirm) {
        if (confirm) {
            taught = null
            ticked = emptySet()
            taught = JarvisRuntime.chatFacts(id)
        }
    }
    var find by remember(id) { mutableStateOf(initialFind) }
    var current by remember(id) { mutableIntStateOf(0) }
    val matches = remember(loaded, find) {
        loaded?.let { ChatLog.findMatches(it.turns, find) }.orEmpty()
    }
    val listState = rememberLazyListState()
    // The current match's message scrolled into view: item 0 is the head,
    // message i is item i + 1.
    LaunchedEffect(current, matches) {
        val m = matches.getOrNull(current) ?: return@LaunchedEffect
        listState.animateScrollToItem(m.turn + 1)
    }
    val marked = hitStyle()
    val markedNow = hitStyle(current = true)
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
        state = listState,
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
                    val t = taught
                    val facts = t?.facts.orEmpty()
                    when {
                        t == null -> Text(
                            "Checking which facts this chat taught…",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                        )
                        facts.isEmpty() -> Text(
                            if ((t?.hiddenCount ?: 0) > 0) {
                                "Delete this conversation from your PC? This cannot be undone. " +
                                    ChatLog.chatFactsHiddenLine(t?.hiddenCount ?: 0)
                            } else {
                                ChatLog.DELETE_CONFIRM
                            },
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.warnInk,
                        )
                        else -> {
                            Text(
                                ChatLog.chatFactsIntro(facts.size),
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                            facts.forEach { fact ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(
                                        checked = fact.id in ticked,
                                        enabled = !busy,
                                        onCheckedChange = { on ->
                                            ticked = if (on) ticked + fact.id else ticked - fact.id
                                        },
                                    )
                                    Text(fact.text, style = MaterialTheme.typography.bodySmall,
                                        color = chrome.textHi)
                                }
                            }
                            Text(
                                ChatLog.deleteAndForgetConfirm(ticked.size),
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk,
                            )
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Quiet(
                            if (facts.isEmpty()) "Yes, delete it" else ChatLog.deleteChatButton(ticked.size),
                            color = chrome.badInk,
                            enabled = !busy && t != null,
                            onClick = {
                                // Read at the tap: exactly the facts ticked now.
                                val forget = facts.filter { it.id in ticked }.map { it.id }
                                confirm = false
                                busy = true
                                scope.launch {
                                    try {
                                        val (gone, sentence) = JarvisRuntime.deleteHistory(id)
                                        if (gone) {
                                            // One Forget per ticked fact - never a list form.
                                            var forgot = 0
                                            var failed = 0
                                            for (factId in forget) {
                                                val (ok, _) = JarvisRuntime.forgetAutoFact(factId)
                                                if (ok) forgot += 1 else failed += 1
                                            }
                                            onDeleted(id, ChatLog.deleteDoneWords(sentence, forgot, failed))
                                        } else {
                                            said = sentence
                                        }
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                        )
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
                if (loaded != null) {
                    Gap(8)
                    TextInput(
                        value = find,
                        onValueChange = {
                            find = it
                            current = 0
                        },
                        placeholder = ChatLog.FIND_PLACEHOLDER,
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Quiet("Previous", enabled = matches.size > 1, onClick = {
                            current = (current - 1 + matches.size) % matches.size
                        })
                        Quiet("Next", enabled = matches.size > 1, onClick = {
                            current = (current + 1) % matches.size
                        })
                        if (find.isNotBlank()) {
                            Text(
                                ChatLog.findCount(current, matches.size),
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                                modifier = Modifier.liveStatus(),
                            )
                        }
                    }
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
                val here = matches.filter { it.turn == i }
                val now = matches.getOrNull(current)
                Text(
                    if (here.isEmpty()) {
                        AnnotatedString(turn.text)
                    } else {
                        buildAnnotatedString {
                            append(turn.text)
                            for (m in here) addStyle(if (m == now) markedNow else marked, m.start, m.end)
                        }
                    },
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
