package com.jarvis.client.ui.screens

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.HistoryViewPrefs
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ChatFork
import com.jarvis.client.net.ChatLog
import com.jarvis.client.net.ChatMark
import com.jarvis.client.net.ChatTags
import com.jarvis.client.net.HistoryView
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.platform.PrivateClipboard
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.parts.rememberTickingNow
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

/** How long a "file it under" request waits for a tap before it lapses. */
private const val FILING_BANNER_MS = 10 * 60 * 1000L

/**
 * Chat history on the PC ([ChatLog], docs/JARVIS-API.md section 18) - the
 * phone's History screen, opened from Brain and from Home's "Earlier chats".
 *
 * Since the chat audit (2026-09-28; the owner's decisions "Chats, after the
 * chat audit" and "History marks Live sessions"): the list comes first and
 * the two settings sit under "History settings" at the end; each row says
 * what kind of conversation it is (a Live session its length and start, a
 * support chat, a chat with another AI, a comparison) and "Show" narrows the
 * list to one kind; "Forget a time frame…" is at the top; an opened
 * conversation can be carried on ("Continue this chat", [onContinue]) when
 * it is a chat or a Live session, says why not otherwise, shows Jarvis's
 * answers without their markdown marks, and has Copy on each answer.
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
 * The DeepSeek-shaped list (the owner's ask of 2026-10-27): the search box is
 * the first thing on the screen, beside a Sort control (Newest first, Oldest
 * first, Title A-Z) and a "New chat" action; below them the rows are grouped
 * - **Pinned** first, then one collapsible section per tag (the owner's
 * projects) with its icon and count, then the chats in no project. A row
 * shows its type's icon, its title and its age ("25min", "7d"), and says
 * "You're here" on the chat Home is in. A long section shows only five rows
 * and one "Show N more" over what is already loaded; "Load older" still
 * brings more from the PC. Each row's overflow menu carries Open, Pin/Unpin,
 * Move to and Delete. Pinning is metadata (only the chat's id and the wanted
 * state are sent, no approval card); a refusal says so and leaves the row
 * exactly where it was.
 *
 * "Hide memory lists and chat history" (Security) hides the list and any open conversation
 * until Show is confirmed, the same as Brain's memory lists. The settings
 * stay visible: they say nothing about what was said.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HistoryScreen(
    /** The link is up and fresh. Only turning the switch ON waits for it. */
    canAct: Boolean,
    onBack: () -> Unit,
    /**
     * "New chat": the SAME thing the idle timer does (a new conversation with
     * a new id, Home's chat cleared) - [ChatSession.newConversationSaid] in
     * MainActivity - then Home. No new route, no request to the PC: the next
     * question starts the new conversation there.
     */
    onNewChat: () -> Unit = {},
    privateHidden: Boolean = false,
    onShowPrivate: () -> Unit = {},
    showPrivateBusy: Boolean = false,
    /** "Continue this chat": null when Home carried it on, or why not in words. */
    onContinue: suspend (String) -> String? = { null },
    /** "Forget a time frame…": the Brain's plate. */
    onOpenForgetRange: () -> Unit = {},
    /**
     * "Label my chat about the boiler as Home": open with [ChatTags.FileUnder]'s
     * search filled in and a banner; a tap on a chat files it (nothing is
     * filed before that). Null for a normal visit.
     */
    fileUnder: ChatTags.FileUnder? = null,
    /** The banner was used or cancelled: MainActivity forgets the request. */
    onFileUnderDone: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var reads by remember { mutableIntStateOf(0) }
    // Only the tag lists are read again (a chat was filed or moved).
    var tagReads by remember { mutableIntStateOf(0) }
    // The list keeps its place when a conversation is opened and closed again
    // (the second chat audit, phone C8: Back used to land at the top).
    val mainList = rememberLazyListState()
    // "Show": one kind of conversation, or "" for every kind (the owner's
    // decision, 2026-09-28: History can be filtered to Live sessions only).
    var kind by rememberSaveable { mutableStateOf("") }
    // Chat tags (docs/CHAT-TAGS-DESIGN.md section 10). The PC keeps them; this
    // screen reads them when it opens and holds them only while it is open.
    // The chip: "" is All, else a tag id. Folded sections are the one thing
    // kept on the phone - flags only (HistoryViewPrefs), never a name.
    var tagFilter by rememberSaveable { mutableStateOf("") }
    var tagView by remember { mutableStateOf<ChatTags.View?>(null) }
    var tagsOld by remember { mutableStateOf(false) }
    var editorOpen by rememberSaveable { mutableStateOf(false) }
    val viewPrefs = remember { HistoryViewPrefs(context) }
    var closed by remember { mutableStateOf(viewPrefs.closed()) }
    // The row whose "Move to" list is open.
    var moveFor by remember { mutableStateOf<String?>(null) }
    // ---- The DeepSeek-shaped list (the owner's ask of 2026-10-27) ----
    // The sort order ("Show" and the tag chips still narrow the list). Kept
    // over a rotation; it is a view choice and holds no word of a chat.
    var sort by rememberSaveable { mutableStateOf(HistoryView.Sort.NEWEST.id) }
    // Which long sections were opened with "Show N more": section ids joined
    // by commas ("pinned,t3"). A view choice only, like the folded flags.
    var revealed by rememberSaveable { mutableStateOf("") }
    // The row whose overflow menu is open, and the row a pin request is out for.
    var menuFor by remember { mutableStateOf<String?>(null) }
    var pinning by remember { mutableStateOf<String?>(null) }
    // The row Delete was picked on, waiting for its confirm; and the request.
    var deleteFor by remember { mutableStateOf<ChatLog.Summary?>(null) }
    var deleteBusy by remember { mutableStateOf(false) }
    var filing by remember(fileUnder) { mutableStateOf(fileUnder) }
    // The "file it under" request does not outlive this visit: it goes when
    // the screen is left (a rotation is not leaving) and after ten quiet
    // minutes, so the banner is not waiting the next time History opens.
    DisposableEffect(Unit) {
        onDispose {
            var host: Context? = context
            while (host is ContextWrapper && host !is Activity) host = host.baseContext
            val rotating = (host as? Activity)?.isChangingConfigurations == true
            if (!rotating && filing != null) onFileUnderDone()
        }
    }
    LaunchedEffect(filing) {
        if (filing == null) return@LaunchedEffect
        delay(FILING_BANNER_MS)
        filing = null
        onFileUnderDone()
    }
    // Hiding the lists closes any row menu, delete confirm or move list, so
    // nothing about a chat comes back into view with them.
    LaunchedEffect(privateHidden) {
        if (privateHidden) {
            menuFor = null
            moveFor = null
            deleteFor = null
        }
    }
    // "History settings", folded until opened: the list comes first.
    var settingsOpen by rememberSaveable { mutableStateOf(false) }
    var status by remember { mutableStateOf<ChatLog.Status?>(null) }
    var rows by remember { mutableStateOf<List<ChatLog.Summary>?>(null) }
    // The DeepSeek list's view state: the sort order, the chat Home is in,
    // the sections opened with "Show N more", and the clock the ages are read
    // against. All view choices - no word of a chat, nothing sent anywhere.
    val sortOrder = HistoryView.sortOf(sort)
    val homeChatId = remember(reads) { JarvisRuntime.homeKeptChatId() }
    val nowSeconds = rememberTickingNow(rows, 15_000L) / 1000L
    val revealedKeys = remember(revealed) {
        revealed.split(',').filter { it.isNotEmpty() }.toSet()
    }
    fun revealSection(id: String) {
        revealed = (revealedKeys + id).joinToString(",")
    }
    fun toggleSection(prefsKey: Int) {
        val next = if (prefsKey in closed) closed - prefsKey else closed + prefsKey
        closed = next
        viewPrefs.saveClosed(next)
    }
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
    // The sentence "Fork from here" left for the chat it opened: (that chat's id, the words).
    // Dropped when the conversation is closed, so it never shows on a later visit.
    var forkNote by remember { mutableStateOf<Pair<String, String>?>(null) }
    LaunchedEffect(openId) {
        if (openId == null) forkNote = null
    }
    var listSaid by remember { mutableStateOf<String?>(null) }
    // The search box (docs/JARVIS-API.md section 71). Two letters or more:
    // the PC searches what was SAID in the kept chats, opening each in its
    // memory for this one search - no index, nothing kept, nothing handed to
    // the AI. One letter, or a PC without the search: the loaded list, by
    // title. `remember`, not `rememberSaveable`: the words searched for are
    // not put in the saved screen state either.
    var search by remember { mutableStateOf(fileUnder?.query.orEmpty()) }
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
    LaunchedEffect(search, privateHidden, oldPc, kind) {
        found = null
        searchError = null
        if (privateHidden || !wordSearch) {
            searching = false
            return@LaunchedEffect
        }
        searching = true
        delay(350)
        val r = JarvisRuntime.historySearch(search, kind.ifEmpty { null })
        searching = false
        when (r) {
            null -> Unit
            // The chosen kind narrows the words too; an older PC that ignores
            // `kind` is narrowed here (the second chat audit, phone B2).
            is ApiResult.Ok -> found = ChatLog.search(r.value).let { s ->
                if (kind.isEmpty()) s else s.copy(found = s.found.filter { it.row.kind == kind })
            }
            is ApiResult.Failed -> if (ChatLog.searchMissing(r.error)) {
                oldPc = true
            } else {
                searchError = ChatLog.failure(r.error) ?: JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    // The tags, read with the list. Nothing is asked and no name is held
    // while the private lists are hidden (tag names hide with titles).
    LaunchedEffect(reads, tagReads, privateHidden) {
        if (privateHidden) {
            tagView = null
            return@LaunchedEffect
        }
        when (val r = JarvisRuntime.historyTags()) {
            null -> Unit
            is ApiResult.Ok -> {
                val v = ChatTags.view(r.value)
                if (v == null) {
                    tagView = null
                    tagsOld = true
                } else {
                    tagView = v
                    tagsOld = false
                    // A tag deleted elsewhere: its chip goes back to All.
                    if (tagFilter.isNotEmpty() && tagFilter != ChatTags.NONE_FILTER &&
                        v.tags.none { it.id.toString() == tagFilter }) tagFilter = ""
                }
            }
            is ApiResult.Failed -> if (r.error == ApiError.NotFound) {
                tagView = null
                tagsOld = true
            } else {
                Unit
            }
        }
    }
    // A request to file an older chat: search filled in, no filter in the way.
    LaunchedEffect(fileUnder) {
        val f = fileUnder ?: return@LaunchedEffect
        search = f.query
        kind = ""
        tagFilter = ""
        openId = null
        editorOpen = false
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
    LaunchedEffect(reads, kind, tagFilter) {
        when (val r = JarvisRuntime.history(kind = kind.ifEmpty { null }, tag = tagFilter.ifEmpty { null })) {
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

    // Back closes an open conversation first, then a row's menu or delete
    // confirm, then leaves History.
    val open = openId
    BackHandler(enabled = open != null || editorOpen || menuFor != null || deleteFor != null) {
        when {
            open != null -> openId = null
            editorOpen -> editorOpen = false
            menuFor != null -> menuFor = null
            else -> deleteFor = null
        }
    }

    // Files ONE chat (or unfiles it with a null tag). The row is updated here
    // at once; the tag counts are read again. Held on a stale link by the runtime.
    fun fileChat(id: String, tagId: Int?, fromBanner: Boolean) {
        scope.launch {
            val w = JarvisRuntime.fileChat(id, tagId)
            if (w.ok) {
                rows = rows?.map { if (it.id == id) it.copy(tagId = tagId) else it }
                    ?.filter { ChatTags.matchesFilter(tagFilter, it.tagId) }
                found = found?.let { f ->
                    f.copy(found = f.found.map { h -> if (h.row.id == id) h.copy(row = h.row.copy(tagId = tagId)) else h })
                }
                moveFor = null
                val name = tagView?.tags?.firstOrNull { it.id == tagId }?.name
                listSaid = if (name != null) ChatTags.filed(name) else ChatTags.UNFILED
                tagReads += 1
                if (fromBanner) {
                    filing = null
                    onFileUnderDone()
                }
            } else {
                listSaid = w.said
            }
        }
    }

    // Pin or unpin ONE chat (the owner's ask of 2026-10-27). The PC's answer
    // is the only thing that moves the row: a refusal says so and leaves it
    // where it was, with the same tag and the same place in the list.
    fun pinChat(row: ChatLog.Summary) {
        if (pinning != null) return
        val want = !row.pinned
        pinning = row.id
        listSaid = null
        scope.launch {
            try {
                val w = JarvisRuntime.pinChat(row.id, want)
                if (w.ok) {
                    val nowPinned = w.pinned ?: want
                    rows = rows?.let { HistoryView.withPin(it, row.id, nowPinned) }
                    found = found?.let { HistoryView.withPin(it, row.id, nowPinned) }
                    listSaid = HistoryView.pinSaid(nowPinned)
                    if (nowPinned && HistoryView.PINNED_KEY in closed) {
                        // A section folded shut must not swallow the pin that was
                        // just made: Pinned opens so the row is where the sentence says.
                        val next = closed - HistoryView.PINNED_KEY
                        closed = next
                        viewPrefs.saveClosed(next)
                    }
                } else {
                    listSaid = w.said ?: ChatLog.PIN_REFUSED
                }
            } finally {
                pinning = null
                menuFor = null
            }
        }
    }

    // Delete ONE chat from a row's overflow menu, after the confirm shown at
    // the top of the list. The same request (and the same confirm words) as
    // Delete inside a conversation; the row goes only after the PC says yes.
    fun deleteChat(row: ChatLog.Summary) {
        if (deleteBusy) return
        deleteBusy = true
        deleteFor = null
        listSaid = null
        scope.launch {
            try {
                val (gone, sentence) = JarvisRuntime.deleteHistory(row.id)
                if (gone) {
                    rows = rows?.filterNot { it.id == row.id }
                    found = found?.let { f -> f.copy(found = f.found.filterNot { it.row.id == row.id }) }
                    listSaid = sentence
                    moveFor = null
                    menuFor = null
                    // The PC's list and the tag counts changed; the chat Home
                    // is in may be the one that just went (the runtime said so).
                    reads += 1
                    tagReads += 1
                } else {
                    listSaid = sentence
                }
            } finally {
                deleteBusy = false
            }
        }
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar(
            if (open != null) "Conversation" else if (editorOpen) ChatTags.EDITOR_TITLE else "History",
            onBack = { if (openId != null) openId = null else if (editorOpen) editorOpen = false else onBack() },
            subtitle = "Chat history, kept on your PC",
        ) {
            if (open == null && !editorOpen) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // The same mechanism the idle timer uses: a new
                    // conversation on the phone, no route, no request - the
                    // next question starts the new chat on the PC.
                    Quiet("New chat", color = chrome.textMid, onClick = onNewChat)
                    Quiet("Refresh", onClick = { reads += 1 })
                }
            }
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
                    onContinue = onContinue,
                    canAct = canAct,
                    notice = forkNote?.takeIf { it.first == open }?.second,
                    onForked = { newId, sentence ->
                        // The new chat opens at once; the list is read again so the
                        // fork shows beside the original. The original is untouched.
                        forkNote = newId to sentence
                        listSaid = sentence
                        findFirst = ""
                        openId = newId
                        reads += 1
                    },
                    tags = tagView?.tags.orEmpty(),
                    onTagged = { id, tagId ->
                        rows = rows?.map { if (it.id == id) it.copy(tagId = tagId) else it }
                            ?.filter { ChatTags.matchesFilter(tagFilter, it.tagId) }
                        found = found?.let { f ->
                            f.copy(found = f.found.map { h -> if (h.row.id == id) h.copy(row = h.row.copy(tagId = tagId)) else h })
                        }
                        tagReads += 1
                    },
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

        // The "Tags" editor takes the place of the list, like an opened chat.
        if (editorOpen) {
            if (privateHidden) {
                Column(Modifier.fillMaxWidth().weight(1f).padding(16.dp)) {
                    HiddenSection(ChatTags.EDITOR_TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
                    // The overnight switch holds no chat words, so it stays reachable.
                    Gap(12)
                    SuggestTagsRow(canAct = canAct)
                }
            } else {
                TagsEditor(
                    canAct = canAct,
                    view = tagView,
                    oldPc = tagsOld,
                    // Deleting a tag untags its chats, so the list is read again too.
                    onChanged = { reads += 1 },
                    modifier = Modifier.weight(1f),
                )
            }
            return@Column
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = mainList,
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // The search box is the FIRST thing on the screen (the owner's ask
            // of 2026-10-27, the DeepSeek look), with the sort control beside
            // it. Nothing about a chat is shown while the private lists are
            // hidden, so neither is this.
            if (!privateHidden) {
                item(key = "search") {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        TextInput(
                            value = search,
                            onValueChange = { search = it },
                            placeholder = ChatLog.SEARCH_PLACEHOLDER,
                            // Its name for TalkBack (the chat audit: it had none).
                            modifier = Modifier.weight(1f).semantics {
                                contentDescription = ChatLog.SEARCH_LABEL
                            },
                        )
                        // One tap cycles Newest first -> Oldest first -> Title A-Z.
                        // A view choice only: the PC is not asked, nothing is saved.
                        Quiet(
                            sortOrder.short,
                            color = chrome.textMid,
                            modifier = Modifier.semantics {
                                contentDescription = HistoryView.sortTitle(sortOrder)
                            },
                            onClick = { sort = HistoryView.nextSort(sortOrder).id },
                        )
                    }
                }
            }
            // Whether History is on, at the TOP: "waiting for your approval" and
            // "nothing new is being kept" used to sit under the folded settings
            // at the very bottom (the second chat audit, phone worst-three #2).
            // It says nothing about what was said, so it shows while hidden too.
            item(key = "status") {
                val switch = ChatLog.switchState(status, cardInQueue)
                if (status != null) {
                    val warn = switch == ChatLog.Switch.WAITING ||
                        (switch == ChatLog.Switch.ON && status?.recording == false)
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text(
                            ChatLog.stateLine(switch, status),
                            style = MaterialTheme.typography.bodySmall,
                            color = if (warn) chrome.warnInk else chrome.textMid,
                            modifier = Modifier.weight(1f).liveStatus(),
                        )
                        Quiet(
                            ChatLog.STATUS_CHANGE,
                            color = chrome.textMid,
                            modifier = Modifier.semantics { contentDescription = ChatLog.STATUS_CHANGE_TITLE },
                            onClick = {
                                settingsOpen = true
                                scope.launch {
                                    delay(80)
                                    val last = mainList.layoutInfo.totalItemsCount - 2
                                    if (last > 0) mainList.animateScrollToItem(last)
                                }
                            },
                        )
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
                val view = tagView
                val groupedTags = view != null && view.tags.isNotEmpty()
                val wanted = filing
                // "Tap the chat to file it under Home." Nothing is filed until a tap.
                if (wanted != null) {
                    item(key = "filing") {
                        val target = view?.tags?.firstOrNull { it.id == wanted.tagId }
                        Plate {
                            Text(
                                when {
                                    target != null -> ChatTags.banner(target.name)
                                    view != null -> ChatTags.errorSentence("tag_not_found")
                                    else -> "Reading…"
                                },
                                style = MaterialTheme.typography.bodyMedium,
                                color = chrome.textHi,
                                modifier = Modifier.liveStatus(),
                            )
                            Quiet(ChatTags.CANCEL, color = chrome.textMid, onClick = {
                                filing = null
                                onFileUnderDone()
                            })
                        }
                    }
                }
                // One letter, or a PC without the word search: the box
                // narrows `shown` by title, for display only - paging ("Load
                // older") still works from the full, unfiltered list. Two
                // letters or more: the PC's results replace the list.
                val visible = if (shown != null && !wordSearch) ChatLog.filtered(shown, search) else null
                item(key = "list-head") {
                    Column(Modifier.fillMaxWidth()) {
                        Row(
                            Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Kicker("Conversations")
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                // The tag editor (docs/CHAT-TAGS-DESIGN.md).
                                if (!tagsOld) {
                                    Quiet(ChatTags.EDITOR_TITLE, color = chrome.textMid, onClick = { editorOpen = true })
                                }
                                // At the top of History, not only deep in Brain
                                // (the chat audit, 2026-09-28).
                                Quiet(ChatLog.FORGET_RANGE_LINK, color = chrome.textMid, onClick = onOpenForgetRange)
                            }
                        }
                        Gap(4)
                        // "Show": every kind, Live only, support chats, chats
                        // with other AIs, comparisons.
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            ChatLog.FILTERS.forEach { (value, words) ->
                                Quiet(
                                    if (value == kind) "• $words" else words,
                                    color = if (value == kind) chrome.textHi else chrome.textMid,
                                    modifier = Modifier.semantics {
                                        contentDescription = ChatLog.FILTER_LABEL + ": " + words +
                                            if (value == kind) ", chosen" else ""
                                    },
                                    onClick = {
                                        if (value != kind) {
                                            kind = value
                                            rows = null
                                            mayHaveOlder = false
                                            // A stale error from the other kind is dropped, and
                                            // the words typed stay: the search runs again for
                                            // this kind (the second chat audit, phone B2, C9).
                                            readError = null
                                        }
                                    },
                                )
                            }
                        }
                        // "All" and one chip per tag: shows one tag's chats.
                        if (view != null && groupedTags) {
                            Gap(2)
                            TagFilterChips(view.tags, view.untagged, tagFilter, onPick = { picked ->
                                if (picked != tagFilter) {
                                    tagFilter = picked
                                    rows = null
                                    mayHaveOlder = false
                                    readError = null
                                }
                            })
                        }
                        Gap(6)
                        when {
                            shown == null -> Text(
                                if (err != null) "Couldn't read your chat history: $err" else "Reading…",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (err != null) chrome.warnInk else chrome.textLo,
                            )
                            shown.isEmpty() -> Text(
                                if (kind.isNotEmpty() || tagFilter.isNotEmpty()) ChatLog.FILTER_NONE else ChatLog.EMPTY,
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid,
                            )
                            // One letter, or an older PC: titles of the loaded
                            // rows only - said so, and that "Load older" may
                            // bring in more (the desktop's words).
                            visible != null && visible.isEmpty() -> Text(
                                if (mayHaveOlder) ChatLog.NO_MATCH_MORE else ChatLog.NO_MATCH,
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
                // Delete from a row's menu asks in that row, where the owner is
                // looking; the same words and the same request as Delete inside
                // an opened conversation. (No confirm is drawn for a row the
                // notice cannot see, so nothing can be confirmed blind.)
                if (wordSearch && !searching) {
                    val f = found
                    if (f != null && f.queryOk) {
                        // A tag chosen narrows the words too (the PC's search takes no tag).
                        val hits = when (val key = ChatTags.filterKey(tagFilter)) {
                            null -> f.found
                            ChatTags.UNTAGGED_KEY -> f.found.filter { it.row.tagId == null }
                            else -> f.found.filter { it.row.tagId == key }
                        }
                        items(hits, key = { "f-" + it.row.id }) { hit ->
                            FoundRow(
                                hit,
                                tag = view?.tags?.firstOrNull { it.id == hit.row.tagId },
                                tags = if (wanted == null) view?.tags.orEmpty() else emptyList(),
                                current = hit.row.id == homeChatId,
                                menuOpen = menuFor == hit.row.id,
                                moveOpen = moveFor == hit.row.id,
                                pinBusy = pinning == hit.row.id,
                                nowSeconds = nowSeconds,
                                menuAllowed = wanted == null,
                                deleteOpen = deleteFor?.id == hit.row.id,
                                deleteBusy = deleteBusy,
                                onDelete = { deleteChat(hit.row) },
                                onKeep = { deleteFor = null },
                                onToggleMenu = {
                                    menuFor = if (menuFor == hit.row.id) null else hit.row.id
                                    moveFor = null
                                },
                                onPin = { pinChat(hit.row) },
                                onToggleMove = { moveFor = if (moveFor == hit.row.id) null else hit.row.id },
                                onMove = { tagId -> fileChat(hit.row.id, tagId, fromBanner = false) },
                                onAskDelete = {
                                    deleteFor = hit.row
                                    menuFor = null
                                    moveFor = null
                                },
                                onOpen = {
                                    if (wanted != null) {
                                        fileChat(hit.row.id, wanted.tagId, fromBanner = true)
                                    } else {
                                        findFirst = search.trim()
                                        openId = hit.row.id
                                    }
                                },
                            )
                        }
                        ChatLog.searchMoreLine(f)?.let { more ->
                            item(key = "search-more") {
                                Text(more, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            }
                        }
                    }
                }
                if (visible != null) {
                    // One row: opens the chat - or, with the "file it" banner up, files it.
                    val rowContent: @Composable (ChatLog.Summary) -> Unit = { row ->
                        val here = view?.tags?.firstOrNull { it.id == row.tagId }
                        ConversationRow(
                            row,
                            tag = here,
                            tags = if (wanted == null) view?.tags.orEmpty() else emptyList(),
                            current = row.id == homeChatId,
                            menuOpen = menuFor == row.id,
                            moveOpen = moveFor == row.id,
                            pinBusy = pinning == row.id,
                            nowSeconds = nowSeconds,
                            menuAllowed = wanted == null,
                            deleteOpen = deleteFor?.id == row.id,
                            deleteBusy = deleteBusy,
                            onDelete = { deleteChat(row) },
                            onKeep = { deleteFor = null },
                            onToggleMenu = {
                                menuFor = if (menuFor == row.id) null else row.id
                                moveFor = null
                            },
                            onPin = { pinChat(row) },
                            onToggleMove = { moveFor = if (moveFor == row.id) null else row.id },
                            onMove = { tagId -> fileChat(row.id, tagId, fromBanner = false) },
                            onAskDelete = {
                                deleteFor = row
                                menuFor = null
                                moveFor = null
                            },
                            onOpen = {
                                if (wanted != null) {
                                    fileChat(row.id, wanted.tagId, fromBanner = true)
                                } else {
                                    findFirst = ""
                                    openId = row.id
                                }
                            },
                        )
                    }
                    if (!wordSearch) {
                        // Sections in the DeepSeek order (the owner's ask of
                        // 2026-10-27): Pinned first, one per tag in the owner's
                        // order with its icon and count, Untagged last. A pinned
                        // chat appears once, in Pinned; a long section shows five
                        // rows and "Show N more" over what is already loaded.
                        // A "Show" kind or title words narrow the list: then a
                        // header counts the rows shown, not the PC's whole number.
                        // A PC with no tags gets one "Chats" section.
                        val narrowed = kind.isNotEmpty() || search.isNotBlank()
                        val sections = HistoryView.sections(
                            visible,
                            view?.tags.orEmpty(),
                            view?.untagged ?: 0,
                            ChatTags.filterKey(tagFilter),
                            exact = !narrowed,
                            sort = sortOrder,
                        )
                        sections.forEach { sec ->
                            val prefsKey = HistoryView.prefsKey(sec)
                            val isOpen = prefsKey !in closed
                            item(key = "sec-${sec.id}") {
                                if (sec.pinned) {
                                    PinnedSectionHeader(sec.count, isOpen) { toggleSection(prefsKey) }
                                } else {
                                    TagSectionHeader(sec.tag, sec.count, isOpen, title = sec.title) {
                                        toggleSection(prefsKey)
                                    }
                                }
                            }
                            if (isOpen) {
                                if (sec.rows.isEmpty()) {
                                    item(key = "sec-${sec.id}-none") {
                                        Text(
                                            ChatTags.NONE_LOADED,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = chrome.textLo,
                                        )
                                    }
                                }
                                val opened = sec.id in revealedKeys
                                items(HistoryView.shown(sec, opened), key = { "c-" + it.id }) { row ->
                                    rowContent(row)
                                }
                                val more = HistoryView.hidden(sec, opened)
                                if (more > 0) {
                                    item(key = "more-${sec.id}") {
                                        Quiet(
                                            HistoryView.showMore(more),
                                            color = chrome.textMid,
                                            modifier = Modifier.semantics {
                                                contentDescription =
                                                    HistoryView.showMoreTitle(sec.title, more)
                                            },
                                            onClick = { revealSection(sec.id) },
                                        )
                                    }
                                }
                            }
                        }
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
                                                when (val r = JarvisRuntime.history(before, kind.ifEmpty { null }, tagFilter.ifEmpty { null })) {
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

            // "History settings": after the list (the chat audit, 2026-09-28 -
            // History used to open on its settings), and shown even while the
            // list is hidden: they say nothing about what was said.
            item(key = "settings") {
                val switch = ChatLog.switchState(status, cardInQueue)
                Section(ChatLog.HISTORY_SETTINGS) {
                    Quiet(
                        if (settingsOpen) "Hide" else "Show",
                        color = chrome.textMid,
                        // What it shows or hides, for TalkBack and Voice Access.
                        modifier = Modifier.semantics {
                            contentDescription = if (settingsOpen) ChatLog.SETTINGS_HIDE_TITLE else ChatLog.SETTINGS_SHOW_TITLE
                        },
                        onClick = { settingsOpen = !settingsOpen },
                    )
                    if (settingsOpen) Plate {
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
                                ChatLog.keepConfirm(days) + " " + ChatLog.KEEP_SUPPORT_NOTE,
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

            item(key = "tail") { Gap(24) }
        }
    }
}

/**
 * One row of the list, in the DeepSeek shape the owner asked for on
 * 2026-10-27: the conversation's type icon, its title and its age ("25min",
 * "7d"), then when/where and its marks in words, with the overflow menu on
 * the right. "You're here" marks the chat Home is in; a drawn pin and the
 * Pinned section both say a pinned row's place.
 */
@Composable
private fun ConversationRow(
    row: ChatLog.Summary,
    tag: ChatTags.Tag?,
    tags: List<ChatTags.Tag>,
    current: Boolean,
    menuOpen: Boolean,
    moveOpen: Boolean,
    pinBusy: Boolean,
    nowSeconds: Long,
    menuAllowed: Boolean,
    deleteOpen: Boolean,
    deleteBusy: Boolean,
    onToggleMenu: () -> Unit,
    onPin: () -> Unit,
    onToggleMove: () -> Unit,
    onMove: (Int?) -> Unit,
    onAskDelete: () -> Unit,
    onDelete: () -> Unit,
    onKeep: () -> Unit,
    onOpen: () -> Unit,
) {
    ChatRowCard(
        row = row,
        tag = tag,
        tags = tags,
        current = current,
        menuOpen = menuOpen,
        moveOpen = moveOpen,
        pinBusy = pinBusy,
        nowSeconds = nowSeconds,
        menuAllowed = menuAllowed,
        deleteOpen = deleteOpen,
        deleteBusy = deleteBusy,
        onToggleMenu = onToggleMenu,
        onPin = onPin,
        onToggleMove = onToggleMove,
        onMove = onMove,
        onAskDelete = onAskDelete,
        onDelete = onDelete,
        onKeep = onKeep,
        onOpen = onOpen,
    )
}

/**
 * The one row both the list and the PC's search results draw, so a pinned,
 * current or deleted row behaves the same in either. [snippet] is a search
 * result's marked piece of the conversation; [hits] its count of matches.
 */
@Composable
private fun ChatRowCard(
    row: ChatLog.Summary,
    tag: ChatTags.Tag?,
    tags: List<ChatTags.Tag>,
    current: Boolean,
    menuOpen: Boolean,
    moveOpen: Boolean,
    pinBusy: Boolean,
    nowSeconds: Long,
    menuAllowed: Boolean,
    deleteOpen: Boolean,
    deleteBusy: Boolean,
    snippet: AnnotatedString? = null,
    hits: Int? = null,
    onToggleMenu: () -> Unit,
    onPin: () -> Unit,
    onToggleMove: () -> Unit,
    onMove: (Int?) -> Unit,
    onAskDelete: () -> Unit,
    onDelete: () -> Unit,
    onKeep: () -> Unit,
    onOpen: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val zone = remember { ZoneId.systemDefault() }
    val today = LocalDate.now(zone)
    // The row's tap opens the chat; with the menu open it closes that first.
    val open = {
        if (menuOpen) onToggleMenu()
        onOpen()
    }
    Plate(
        Modifier.fillMaxWidth(),
        // The chat Home is in gets the raised tone and a focus hairline, AND
        // the words "You're here" below - never the colour alone.
        tone = if (current) chrome.surface2 else null,
        outline = if (current) chrome.hairlineFocus else null,
    ) {
        Row(
            Modifier.fillMaxWidth().pressable(onClick = open),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ConversationKindIcon(row.kind, chrome.textMid)
            Column(Modifier.weight(1f)) {
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (row.pinned) PinMark(accent)
                    Text(
                        row.title,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textHi,
                        modifier = Modifier.weight(1f),
                        maxLines = 2,
                    )
                    val age = HistoryView.rowAge(row, nowSeconds)
                    if (age.isNotEmpty()) {
                        Text(age, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                }
                Gap(2)
                Text(
                    listOfNotNull(
                        ChatLog.rowLine(row, zone, today),
                        hits?.let { ChatLog.hitsLine(it) },
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
                if (snippet != null) {
                    Gap(4)
                    Text(snippet, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                }
                RowMarks(row, tag, current)
            }
            // The overflow menu's trigger. TalkBack names the row it belongs to.
            // Hidden while a "file it under" banner is up: there a tap on the
            // row files it, and a second menu would be two meanings for one row.
            if (menuAllowed) {
                Quiet(
                    if (menuOpen) "\u25B4" else "\u22EE",
                    color = chrome.textLo,
                    modifier = Modifier.semantics {
                        contentDescription = HistoryView.actionsFor(row.title)
                    },
                    onClick = onToggleMenu,
                )
            }
        }
        if (menuAllowed && menuOpen) {
            ChatActions(
                row = row,
                tags = tags,
                pinBusy = pinBusy,
                onOpen = open,
                onPin = onPin,
                onMove = {
                    onToggleMenu()
                    onToggleMove()
                },
                onDelete = onAskDelete,
            )
        }
        // "Move to": the tags and "No tag" - only when the PC has tags, and not
        // while the overflow menu is open. The row's own tag is marked.
        if (moveOpen && tags.isNotEmpty()) {
            Gap(6)
            Text(ChatTags.MOVE_TO, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            MoveToList(tags, row.tagId, onPick = onMove)
        }
        // Delete asks in the row it is about, in the same words as an opened
        // conversation's confirm; nothing is deleted before the yes.
        if (deleteOpen) {
            Gap(8)
            Text(
                ChatLog.DELETE_CONFIRM,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quiet(
                    if (deleteBusy) "Deleting…" else "Yes, delete it",
                    color = chrome.badInk,
                    enabled = !deleteBusy,
                    onClick = onDelete,
                )
                Quiet("Keep it", enabled = !deleteBusy, onClick = onKeep)
            }
        }
    }
}

/** The row's overflow menu: Open, Pin/Unpin, Move to, Delete - in that order. */
@Composable
private fun ChatActions(
    row: ChatLog.Summary,
    tags: List<ChatTags.Tag>,
    pinBusy: Boolean,
    onOpen: () -> Unit,
    onPin: () -> Unit,
    onMove: () -> Unit,
    onDelete: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth().padding(top = 4.dp)) {
        HistoryView.menu(tags, filing = false).forEach { action ->
            MenuAction(
                HistoryView.actionLabel(action, row.pinned),
                color = if (action == HistoryView.Action.DELETE) chrome.badInk else chrome.textHi,
                enabled = !pinBusy,
                onClick = {
                    when (action) {
                        HistoryView.Action.OPEN -> onOpen()
                        HistoryView.Action.PIN -> onPin()
                        HistoryView.Action.MOVE -> onMove()
                        HistoryView.Action.DELETE -> onDelete()
                    }
                },
            )
        }
    }
}

/** One line of a row's menu: a full-width 48dp target, left-aligned. */
@Composable
private fun MenuAction(
    text: String,
    color: androidx.compose.ui.graphics.Color,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .pressable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 4.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, color = color)
    }
}

/**
 * A row's marks in words: what kind of conversation it is (a Live session
 * says so in its line instead - "Live · 12 min · Today 14:05"), the chat's
 * tag, and "You're here" on the chat Home is in.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RowMarks(row: ChatLog.Summary, chatTag: ChatTags.Tag? = null, current: Boolean = false) {
    val chrome = LocalChrome.current
    val tag = ChatLog.KIND_TAG[row.kind].orEmpty().takeIf { row.kind != "live" && it.isNotEmpty() }
    if (tag == null && chatTag == null && !row.hasVoice && !row.tainted && !current) return
    Gap(4)
    // FlowRow: a tag chip beside the kind and voice marks wraps rather than squeezes.
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        // The chat's own tag: icon and name, so colour is never the only clue.
        if (chatTag != null) TagChip(chatTag)
        if (tag != null) {
            Pill(tag, modifier = Modifier.semantics { contentDescription = ChatLog.KIND_TITLE[row.kind].orEmpty() })
        }
        if (current) Pill(HistoryView.CURRENT, color = chrome.textHi)
        if (row.hasVoice) Pill(ChatLog.VOICE_MARK)
        if (row.tainted) Pill(ChatLog.TAINT_MARK, color = chrome.warnInk)
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
private fun FoundRow(
    hit: ChatLog.Found,
    tag: ChatTags.Tag?,
    tags: List<ChatTags.Tag>,
    current: Boolean,
    menuOpen: Boolean,
    moveOpen: Boolean,
    pinBusy: Boolean,
    nowSeconds: Long,
    menuAllowed: Boolean,
    deleteOpen: Boolean,
    deleteBusy: Boolean,
    onToggleMenu: () -> Unit,
    onPin: () -> Unit,
    onToggleMove: () -> Unit,
    onMove: (Int?) -> Unit,
    onAskDelete: () -> Unit,
    onDelete: () -> Unit,
    onKeep: () -> Unit,
    onOpen: () -> Unit,
) {
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
    ChatRowCard(
        row = hit.row,
        tag = tag,
        tags = tags,
        current = current,
        menuOpen = menuOpen,
        moveOpen = moveOpen,
        pinBusy = pinBusy,
        nowSeconds = nowSeconds,
        menuAllowed = menuAllowed,
        deleteOpen = deleteOpen,
        deleteBusy = deleteBusy,
        snippet = snippet,
        hits = hit.hits,
        onToggleMenu = onToggleMenu,
        onPin = onPin,
        onToggleMove = onToggleMove,
        onMove = onMove,
        onAskDelete = onAskDelete,
        onDelete = onDelete,
        onKeep = onKeep,
        onOpen = onOpen,
    )
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
    onContinue: suspend (String) -> String?,
    /** The link is up and fresh: "Fork from here" writes a new chat, so it waits for it (rule 4). */
    canAct: Boolean,
    /** A sentence to show at the top, e.g. what Fork from here just did. */
    notice: String?,
    /** A fork worked: the new chat's id and the "Forked into ..." words. */
    onForked: (newId: String, sentence: String) -> Unit,
    tags: List<ChatTags.Tag>,
    onTagged: (id: String, tagId: Int?) -> Unit,
    modifier: Modifier,
    onDeleted: (id: String, sentence: String) -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    // "Continue this chat": busy while Home takes it over; why not, if not.
    var continuing by remember(id) { mutableStateOf(false) }
    // Kept over a rotation: a plain sentence, no words of the chat.
    var continueSaid by rememberSaveable(id) { mutableStateOf<String?>(null) }
    // "Fork from here": which message's request is running (one at a time), and
    // the plain sentence a refusal left. The success sentence arrives as [notice].
    var forking by remember(id) { mutableStateOf<Int?>(null) }
    var forkSaid by remember(id) { mutableStateOf<String?>(notice) }
    // "New section here" (section 106): the turn numbers a divider sits above (the
    // PC's list, replaced by its answer after every change), which button's request
    // is running, and the polite sentence the last change left.
    var marks by remember(id) { mutableStateOf<Set<Int>>(emptySet()) }
    var marking by remember(id) { mutableStateOf<Int?>(null) }
    var markSaid by remember(id) { mutableStateOf<String?>(null) }
    val zone = remember { ZoneId.systemDefault() }
    val today = LocalDate.now(zone)
    var loaded by remember(id) { mutableStateOf<ChatLog.Transcript?>(null) }
    // This chat's tag: the PC's answer when it opened, then whatever the owner
    // moved it to. A tag the list no longer has shows as no tag.
    var chatTagId by remember(id) { mutableStateOf<Int?>(null) }
    var moveOpen by remember(id) { mutableStateOf(false) }
    var tagSaid by remember(id) { mutableStateOf<String?>(null) }
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
    // Is this the chat Home is in? Read once when it opens.
    val homeChat = remember(id) { JarvisRuntime.homeKeptChatId() == id }
    // What this chat taught and Jarvis still uses (section 79): a read, shown
    // under the head for chats and Live sessions (the second chat audit).
    var facts by remember(id) { mutableStateOf<ChatLog.Taught?>(null) }
    val loadedKind = loaded?.kind
    LaunchedEffect(id, loadedKind) {
        facts = null
        if (loadedKind == "chat" || loadedKind == "live") facts = JarvisRuntime.chatFacts(id)
    }
    val outside = remember(loaded) { loaded?.let { ChatLog.outsideMarks(it.turns) }.orEmpty() }
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
                if (t == null) err = "Your PC sent something this app could not read." else {
                    loaded = t
                    chatTagId = t.tagId
                    marks = t.marks
                }
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
                    Text(ChatLog.taintNote(t.kind), style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
                }
                if (t != null && homeChat) {
                    Gap(4)
                    Text(ChatLog.HOME_CHAT_LINE, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
                // The facts this chat taught, read-only (Delete offers to forget them).
                facts?.takeIf { it.available }?.let { got ->
                    Gap(4)
                    if (got.hiddenCount > 0) {
                        Text(ChatLog.chatFactsTaughtHidden(got.hiddenCount),
                            style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    } else {
                        Text(ChatLog.chatFactsTaught(got.facts.size),
                            style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                        got.facts.forEach { f ->
                            Text("• " + f.text, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                        }
                    }
                }
                // What kind of record it is, when it is not an ordinary chat.
                if (t != null && t.kind != "chat") {
                    Gap(4)
                    Text(ChatLog.KIND_TITLE[t.kind].orEmpty(), style = MaterialTheme.typography.labelSmall,
                        color = chrome.textMid)
                }
                // The chat's tag and "Move to" (docs/CHAT-TAGS-DESIGN.md section 10),
                // the same list the rows have. Only when the PC has tags.
                if (t != null && tags.isNotEmpty()) {
                    Gap(6)
                    tags.firstOrNull { it.id == chatTagId }?.let { TagChip(it) }
                    Quiet(
                        if (moveOpen) ChatTags.CANCEL else ChatTags.MOVE_TO,
                        color = chrome.textMid,
                        modifier = Modifier.semantics {
                            contentDescription = (if (moveOpen) "Close move list for " else "${ChatTags.MOVE_TO}: ") + t.title
                        },
                        onClick = { moveOpen = !moveOpen },
                    )
                    if (moveOpen) {
                        MoveToList(tags, chatTagId, onPick = { picked ->
                            scope.launch {
                                val w = JarvisRuntime.fileChat(id, picked)
                                if (w.ok) {
                                    chatTagId = picked
                                    moveOpen = false
                                    val name = tags.firstOrNull { it.id == picked }?.name
                                    tagSaid = if (name != null) ChatTags.filed(name) else ChatTags.UNFILED
                                    onTagged(id, picked)
                                } else {
                                    tagSaid = w.said
                                }
                            }
                        })
                    }
                    tagSaid?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                            modifier = Modifier.liveStatus())
                    }
                }
                // "Continue this chat" (the owner's decision, 2026-09-28): Home
                // carries it on - the same conversation, the newest kept
                // messages that fit, its outside-text mark carried over. A
                // support record, a chat with another AI or a comparison says
                // why it cannot be.
                if (t != null) {
                    Gap(6)
                    if (t.continuable) {
                        Quiet(
                            if (continuing) "Opening on Home…" else ChatLog.CONTINUE,
                            color = chrome.textHi,
                            enabled = !continuing,
                            modifier = Modifier.semantics { contentDescription = ChatLog.CONTINUE_TITLE },
                            onClick = {
                                continuing = true
                                continueSaid = null
                                scope.launch {
                                    try {
                                        continueSaid = onContinue(id)
                                    } finally {
                                        continuing = false
                                    }
                                }
                            },
                        )
                    } else {
                        Text(t.continueWhy.orEmpty(), style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid)
                    }
                    continueSaid?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk,
                            modifier = Modifier.liveStatus())
                    }
                    // "Fork from here" (JARVIS-API section 110): a chat that cannot be
                    // forked says why where the buttons would be; an older PC says nothing.
                    t.forkWhy?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                    // Forking writes a new chat, so the buttons wait for a fresh link.
                    if (t.forkable && !canAct) {
                        Text(PlainErrors.shown("link_stale").text, style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid)
                    }
                    forkSaid?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                            modifier = Modifier.liveStatus())
                    }
                    // What "New section here" just did (or why not), announced politely.
                    markSaid?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                            modifier = Modifier.liveStatus())
                    }
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
                            // A customer-support record asks once more, saying
                            // what it is (the owner, 2026-09-28).
                            (if (loaded?.kind == "support") ChatLog.DELETE_SUPPORT + " " else "") +
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
                                // One checkbox with its words: the row takes the taps and
                                // TalkBack reads the fact with its state.
                                Row(
                                    Modifier
                                        .fillMaxWidth()
                                        .toggleable(
                                            value = fact.id in ticked,
                                            enabled = !busy,
                                            role = Role.Checkbox,
                                            onValueChange = { on ->
                                                ticked = if (on) ticked + fact.id else ticked - fact.id
                                            },
                                        ),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Checkbox(
                                        checked = fact.id in ticked,
                                        enabled = !busy,
                                        onCheckedChange = null,
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
            // A customer-support chat's record (role "support"): who wrote
            // each line, and the company's own lines marked outside text.
            val support = turn.role == "support"
            // A kept chat with another AI or a comparison (role "chatbot",
            // the chat audit 2026-09-28): who wrote each line, and the other
            // AI's replies and the summary marked outside text.
            val chatbot = turn.role == "chatbot"
            val answer = turn.role == "assistant"
            Column(Modifier.fillMaxWidth()) {
                // A section break sits ABOVE the message it was set on: a heading-level
                // landmark with its own Remove (the same tap, both directions).
                val markAt = turn.idx
                if (ChatMark.dividerAbove(markAt, marks) && markAt != null) {
                    Row(
                        Modifier.fillMaxWidth().padding(bottom = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Box(Modifier.weight(1f).height(1.dp).background(chrome.textLo))
                        Text(
                            ChatMark.DIVIDER,
                            style = MaterialTheme.typography.labelMedium,
                            color = chrome.textMid,
                            modifier = Modifier.semantics { heading() },
                        )
                        Box(Modifier.weight(1f).height(1.dp).background(chrome.textLo))
                        Quiet(
                            ChatMark.REMOVE,
                            color = chrome.textMid,
                            enabled = canAct && marking == null,
                            modifier = Modifier.semantics { contentDescription = ChatMark.REMOVE_LABEL },
                            onClick = {
                                marking = markAt
                                markSaid = null
                                scope.launch {
                                    try {
                                        val r = JarvisRuntime.markSection(id, markAt, false)
                                        r.marks?.let { marks = it }
                                        markSaid = r.said
                                    } finally {
                                        marking = null
                                    }
                                }
                            },
                        )
                    }
                }
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Kicker(
                        when {
                            support -> ChatLog.supportWho(turn.provenance)
                            chatbot -> ChatLog.chatbotWho(turn.provenance)
                            mine -> "You"
                            else -> "Jarvis"
                        },
                    )
                    if (support && turn.provenance == "support_company") {
                        Pill("outside text", color = chrome.warnInk)
                    }
                    if (chatbot && (turn.provenance == "chatbot_reply" || turn.provenance == "chatbot_summary")) {
                        Pill("outside text", color = chrome.warnInk)
                    }
                    if (mine) {
                        ChatLog.provenanceMark(turn.provenance)?.let { Pill(it) }
                    }
                    // "read outside text" belongs to the answer that read it, not to
                    // the owner's own question beside "You".
                    if (i in outside && !support && !chatbot) Pill(ChatLog.TAINT_MARK, color = chrome.warnInk)
                }
                Gap(2)
                val here = matches.filter { it.turn == i }
                val now = matches.getOrNull(current)
                // Worked out once per message, not on every redraw.
                val plain = remember(turn.text) {
                    if (answer || chatbot) ChatLog.plainAnswer(turn.text) else turn.text
                }
                Text(
                    if (here.isEmpty()) {
                        // Jarvis's answers (and a chatbot record's lines)
                        // without their markdown marks - no "**" or "#" (the
                        // chat audit, 2026-09-28). While "Find in this chat"
                        // has words, the words are shown exactly as kept, so
                        // the marks land on the right letters.
                        AnnotatedString(if ((answer || chatbot) && find.isBlank()) plain else turn.text)
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
                // Copy on an old answer (the chat audit, 2026-09-28): the
                // same private copy as Home's (no preview in Android's toast).
                if (answer && turn.text.isNotBlank()) {
                    Quiet(
                        ChatLog.COPY,
                        color = chrome.textMid,
                        modifier = Modifier.semantics { contentDescription = ChatLog.COPY_TITLE },
                        onClick = { PrivateClipboard.copy(context, turn.text) },
                    )
                }
                // "Fork from here" on the owner's messages and Jarvis's kept answers
                // (never a support, chatbot or comparison record - not forkable).
                // Its screen-reader name holds the visible words and says which message.
                val forkAt = turn.idx
                if (forkAt != null && ChatFork.offered(loaded?.forkable == true, turn.role, forkAt)) {
                    val thisOne = forking == forkAt
                    Quiet(
                        if (thisOne) ChatFork.BUSY else ChatFork.BUTTON,
                        color = chrome.textMid,
                        enabled = canAct && forking == null,
                        modifier = Modifier.semantics {
                            contentDescription = if (thisOne) ChatFork.BUSY else ChatFork.label(turn.role)
                        },
                        onClick = {
                            forking = forkAt
                            forkSaid = null
                            scope.launch {
                                try {
                                    val r = JarvisRuntime.forkChat(id, forkAt)
                                    val newId = r.id
                                    if (r.ok && newId != null) {
                                        onForked(newId, r.said)
                                    } else {
                                        // Stay on the original chat and say why.
                                        forkSaid = r.said
                                    }
                                } finally {
                                    forking = null
                                }
                            }
                        },
                    )
                }
                // "New section here" on the owner's own messages only, when the PC says the
                // chat is markable (10+ messages, a chat or Live session). Nothing is drawn
                // otherwise. A divider is only ever a divider: nothing reaches a model.
                if (markAt != null && ChatMark.offered(loaded?.markable == true, turn.role, markAt, marks)) {
                    val thisOne = marking == markAt
                    Quiet(
                        if (thisOne) ChatMark.BUSY else ChatMark.BUTTON,
                        color = chrome.textMid,
                        enabled = canAct && marking == null,
                        modifier = Modifier.semantics {
                            contentDescription = if (thisOne) ChatMark.BUSY else ChatMark.BUTTON_LABEL
                        },
                        onClick = {
                            marking = markAt
                            markSaid = null
                            scope.launch {
                                try {
                                    val r = JarvisRuntime.markSection(id, markAt, true)
                                    r.marks?.let { marks = it }
                                    markSaid = r.said
                                } finally {
                                    marking = null
                                }
                            }
                        },
                    )
                }
            }
        }
        item(key = "tail") { Gap(24) }
    }
}

/**
 * Brain's way in: one plate that opens History. While "Hide memory lists and
 * chat history" is on, History itself hides its list and any open
 * conversation until Show is confirmed; its settings stay reachable (the
 * chat audit, 2026-09-28, phone C9: hiding the whole way in hid them too,
 * against History's own rule), so this plate is never hidden - it shows no
 * words of any chat.
 */
@Composable
internal fun HistoryEntrySection(
    onOpen: () -> Unit,
    @Suppress("UNUSED_PARAMETER") privateHidden: Boolean,
    @Suppress("UNUSED_PARAMETER") showPrivateBusy: Boolean,
    @Suppress("UNUSED_PARAMETER") onShowPrivate: () -> Unit,
) {
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
