package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.AutoLearn
import com.jarvis.client.net.ChatTags
import com.jarvis.client.net.MemoryErase
import com.jarvis.client.net.Topics
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TagIcon
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Brain -> Memory -> Topics (docs/TOPIC-CONTROLS-DESIGN.md, the frozen
 * contract C3-C5; docs/JARVIS-API.md section 107; the owner's request of
 * 2026-09-30: "include or exclude different topics").
 *
 * Every saved fact sits under ONE topic and every topic has a mode: Learn and
 * use / Use, but don't learn / Learn, but don't use / Off. Tapping a row opens
 * the picker with ALL FOUR choices every time (the owner asked for that), a
 * line built by the PC from `GET /api/topics/preview`, and - when the change
 * would ask - "This will ask for your OK first." Nothing is sent until
 * Change; a change to a private topic that loosens it raises ONE approval
 * card on the PC (`topic_loosen`), the plate then says "Waiting for your
 * approval." and reads the list every 2 seconds until the card is decided,
 * and shows the PC's own sentence about how it ended. Decided on the PC or
 * the other device; never here, never by voice.
 *
 * The rest: "Check these" (Jarvis's guesses, ten at a time, "These are
 * right" for the batch or "File under..." for one fact), "Show them" on an
 * Off topic (its facts, greyed, with Forget and "Erase the words"), add,
 * rename, colour, icon, reorder and delete-with-a-home for a topic, and the
 * "Let Jarvis's local model help sort" switch.
 *
 * Not on the phone: keyword editing ("Keywords are set on your PC.", a
 * deep-configuration screen) and the Galaxy (docs/ARCHITECTURE.md section 8).
 *
 * "Hide memory lists and chat history" (or App lock): the names are the
 * owner's words, so each row reads "Topic 1, 41 facts, Use, but don't learn";
 * the mode picker and the model switch still work; "Check these", "Show
 * them", the review list, the fact tags and every edit are not drawn, and the
 * runtime refuses them anyway ([JarvisRuntime.topicsWrite]).
 *
 * Nothing here is remembered on the phone: it is read from the PC when Brain
 * shows it and dropped when Brain is left.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TopicsSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.topicsTick.collectAsState()
    val queue by JarvisRuntime.pending.collectAsState()
    val pickRequest by JarvisRuntime.topicPick.collectAsState()
    val cardIds = queue.map { it.id }

    var reads by remember { mutableIntStateOf(0) }
    var view by remember { mutableStateOf<Topics.View?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var said by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    // The picker.
    var pickId by remember { mutableStateOf<Int?>(null) }
    var pickMode by remember { mutableStateOf("both") }
    var preview by remember { mutableStateOf<Topics.Preview?>(null) }
    var previewFailed by remember { mutableStateOf(false) }
    var pickSaid by remember { mutableStateOf<String?>(null) }

    // Editing, adding, deleting.
    var editId by remember { mutableStateOf<Int?>(null) }
    var renameText by remember { mutableStateOf("") }
    var deleteId by remember { mutableStateOf<Int?>(null) }
    var homeId by remember { mutableStateOf<Int?>(null) }
    var addOpen by remember { mutableStateOf(false) }
    var addName by remember { mutableStateOf("") }
    var addColour by remember { mutableStateOf<Int?>(null) }
    var addIcon by remember { mutableStateOf<String?>(null) }

    // "Check these".
    var reviewOpen by remember { mutableStateOf(false) }
    var review by remember { mutableStateOf<Topics.Review?>(null) }
    var reviewAfter by remember { mutableStateOf<String?>(null) }
    var reviewError by remember { mutableStateOf<String?>(null) }
    var fileFor by remember { mutableStateOf<Long?>(null) }

    // "Show them".
    var showId by remember { mutableStateOf<Int?>(null) }
    var shown by remember { mutableStateOf<Topics.Hidden?>(null) }
    var shownError by remember { mutableStateOf<String?>(null) }
    var forgetConfirm by remember { mutableStateOf<Long?>(null) }
    var eraseConfirm by remember { mutableStateOf<Long?>(null) }

    suspend fun readNow() {
        when (val r = JarvisRuntime.topicsRead(Topics.TOPICS_PATH)) {
            is ApiResult.Ok -> {
                if (Topics.isMissing(r.value.code, r.value.body)) {
                    missing = true
                    view = null
                    readError = null
                } else {
                    val v = Topics.view(r.value.body)
                    if (v != null) {
                        view = v
                        missing = false
                        readError = null
                    } else {
                        readError = Topics.READ_ODD
                    }
                }
            }
            is ApiResult.Failed -> readError = JarvisRuntime.noticeFor(r.error)
        }
    }

    suspend fun readReview() {
        when (val r = JarvisRuntime.topicsRead(Topics.reviewPath(reviewAfter))) {
            is ApiResult.Ok -> {
                val got = Topics.review(r.value.body)
                if (got == null) {
                    reviewError = Topics.READ_ODD
                } else if (got.facts.isEmpty() && reviewAfter != null) {
                    // Past the end (facts were filed): start again from the top.
                    reviewAfter = null
                } else {
                    review = got
                    reviewError = null
                }
            }
            is ApiResult.Failed -> reviewError = JarvisRuntime.noticeFor(r.error)
        }
    }

    suspend fun readShown(id: Int) {
        when (val r = JarvisRuntime.topicsRead(Topics.hiddenPath(id))) {
            is ApiResult.Ok -> {
                val got = Topics.hidden(r.value.body)
                if (got == null) {
                    shownError = Topics.READ_ODD
                } else {
                    shown = got
                    shownError = null
                }
            }
            is ApiResult.Failed -> shownError = JarvisRuntime.noticeFor(r.error)
        }
    }

    /** ONE change. [after] runs on success; a 202 says the card is up and the list is read again. */
    fun send(path: String, json: String?, after: () -> Unit = {}) {
        if (json == null) {
            said = Topics.errorSentence("bad_name")
            return
        }
        busy = true
        said = null
        scope.launch {
            try {
                when (val o = JarvisRuntime.topicsWrite(path, json, privateHidden)) {
                    is Topics.Outcome.Done -> {
                        val v = o.view
                        if (v != null) {
                            view = v
                            missing = false
                        } else {
                            readNow()
                        }
                        after()
                    }
                    is Topics.Outcome.Waiting -> {
                        said = o.message
                        readNow()
                        after()
                    }
                    is Topics.Outcome.Failed -> {
                        said = o.said
                        if (o.missing) missing = true
                    }
                }
            } finally {
                busy = false
            }
        }
    }

    // Read on show, on Refresh, after a change from this phone, and whenever the approvals list changes.
    LaunchedEffect(reads, tick, cardIds) { readNow() }

    // After a 202 (or a card raised on the PC): read every 2 seconds until it is decided.
    val waitingNow = view?.waiting != null
    LaunchedEffect(waitingNow) {
        if (!waitingNow) return@LaunchedEffect
        val baseAt = view?.last?.at ?: 0.0
        var n = 0
        while (n < Topics.MAX_POLLS) {
            delay(Topics.POLL_MS)
            readNow()
            val step = Topics.pollStep(view, baseAt)
            if (step is Topics.Poll.Done) {
                step.message?.let { said = it }
                break
            }
            n++
        }
    }

    // "Switch off my work topic" said or typed: open that topic's picker, changing nothing.
    LaunchedEffect(pickRequest, view, missing, readError) {
        val open = pickRequest ?: return@LaunchedEffect
        val v = view
        if (v == null && !missing && readError == null) return@LaunchedEffect
        JarvisRuntime.consumeTopicPick()
        val t = open.topicId?.let { v?.byId(it) } ?: return@LaunchedEffect
        if (v?.waiting?.topic != t.id) {
            pickId = t.id
            pickMode = t.mode
            preview = null
            previewFailed = false
            pickSaid = null
        }
    }

    // The picker's line: read again each time the selection changes.
    LaunchedEffect(pickId, pickMode) {
        preview = null
        previewFailed = false
        val id = pickId ?: return@LaunchedEffect
        val current = view?.byId(id)?.mode
        if (current == null || current == pickMode) return@LaunchedEffect
        val path = Topics.previewPath(id, pickMode) ?: return@LaunchedEffect
        when (val r = JarvisRuntime.topicsRead(path)) {
            is ApiResult.Ok -> {
                val p = Topics.preview(r.value.body)
                preview = p
                previewFailed = p == null
            }
            is ApiResult.Failed -> previewFailed = true
        }
    }

    LaunchedEffect(reviewOpen, reviewAfter, reads, tick, privateHidden) {
        if (reviewOpen && !privateHidden) readReview()
    }
    LaunchedEffect(showId, reads, tick, privateHidden) {
        val id = showId
        if (id != null && !privateHidden) {
            readShown(id)
        } else {
            shown = null
        }
    }

    Section(Topics.w("title"), trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Topics.w("intro"), style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Text(Topics.w("help_plain"), style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            val v = view
            when {
                missing -> Text(
                    Topics.w("missing"),
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                v == null -> Text(
                    readError?.let { "Couldn't read your topics: $it" } ?: Topics.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (readError != null) chrome.warnInk else chrome.textLo,
                )
                else -> {
                    if (readError != null) {
                        Text(
                            "Couldn't read them again: $readError",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk,
                        )
                    }
                    if (!canAct) {
                        Text(Topics.NOT_HELD, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    Topics.sortingLine(v)?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                    if (privateHidden) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "Names are hidden.",
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                                modifier = Modifier.weight(1f),
                            )
                            Quiet(if (showPrivateBusy) "Checking…" else "Show", enabled = !showPrivateBusy, onClick = onShowPrivate)
                        }
                    } else {
                        Topics.guessLine(v)?.let {
                            Gap(4)
                            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                        Topics.checkButton(v)?.let { label ->
                            Quiet(
                                if (reviewOpen) Topics.DONE else label,
                                modifier = Modifier.semantics { contentDescription = label },
                                onClick = {
                                    reviewOpen = !reviewOpen
                                    reviewAfter = null
                                    review = null
                                    fileFor = null
                                },
                            )
                        }
                    }

                    v.topics.forEach { t ->
                        val label = Topics.shownName(v, t, privateHidden)
                        val waitingHere = v.waiting?.topic == t.id
                        val ink = tagInk(t.colour)
                        Gap(6)
                        Column(Modifier.fillMaxWidth()) {
                            // The whole header is one control: tapping the row opens the picker.
                            val reader = if (privateHidden && !t.system) {
                                Topics.hiddenRow(Topics.ownerIndex(v, t.id), t.facts, t.mode) + ", button: change mode"
                            } else {
                                Topics.screenReader(label, t.facts, t.mode)
                            }
                            Row(
                                Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 48.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .pressable(enabled = !waitingHere, role = Role.Button, onClick = {
                                        pickId = t.id
                                        pickMode = t.mode
                                        pickSaid = null
                                        editId = null
                                        deleteId = null
                                    })
                                    .padding(vertical = 4.dp)
                                    .semantics(mergeDescendants = true) { contentDescription = reader },
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                TagIcon(Topics.ICONS.firstOrNull { it == t.icon } ?: "folder", ink)
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        if (privateHidden && !t.system) {
                                            Topics.hiddenRow(Topics.ownerIndex(v, t.id), t.facts, t.mode)
                                        } else {
                                            label
                                        },
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = ink,
                                    )
                                    if (!privateHidden || t.system) {
                                        Text(
                                            Topics.factsText(t.facts),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = chrome.textLo,
                                        )
                                    }
                                }
                                if (waitingHere) {
                                    Text(
                                        Topics.w("waiting"),
                                        style = MaterialTheme.typography.labelMedium,
                                        color = chrome.warnInk,
                                    )
                                } else {
                                    Text(
                                        Topics.modeName(t.mode),
                                        style = MaterialTheme.typography.labelMedium,
                                        color = chrome.textHi,
                                        modifier = Modifier
                                            .clip(RoundedCornerShape(50))
                                            .background(chrome.surface1)
                                            .padding(horizontal = 10.dp, vertical = 6.dp),
                                    )
                                }
                            }
                            // Private / not used / kept hidden / skipped: words, never colour alone.
                            val notes = Topics.rowNotes(t, privateHidden)
                            if (notes.isNotEmpty()) {
                                FlowRow(
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                    verticalArrangement = Arrangement.spacedBy(2.dp),
                                ) {
                                    notes.forEach { n ->
                                        if (n == Topics.w("private_tag") || n == Topics.w("not_used_tag")) {
                                            Pill(n)
                                        } else {
                                            Text(n, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                                        }
                                    }
                                }
                            }
                            if (!privateHidden && t.isOff) {
                                Quiet(
                                    if (showId == t.id) Topics.DONE else Topics.w("show_them"),
                                    onClick = {
                                        showId = if (showId == t.id) null else t.id
                                        shown = null
                                        forgetConfirm = null
                                        eraseConfirm = null
                                    },
                                )
                            }

                            // ---- the four-choice picker ----
                            if (pickId == t.id && !waitingHere) {
                                Gap(4)
                                Column(
                                    Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(12.dp))
                                        .background(chrome.surface1)
                                        .padding(12.dp),
                                ) {
                                    Text(
                                        Topics.w("pick_line", "name" to label),
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = chrome.textHi,
                                    )
                                    Topics.MODES.forEach { m ->
                                        val chosen = m.id == pickMode
                                        Row(
                                            Modifier
                                                .fillMaxWidth()
                                                .heightIn(min = 48.dp)
                                                .clip(RoundedCornerShape(12.dp))
                                                .pressable(enabled = !busy, role = Role.RadioButton, onClick = {
                                                    pickMode = m.id
                                                    pickSaid = null
                                                })
                                                .padding(vertical = 6.dp)
                                                .semantics(mergeDescendants = true) {
                                                    contentDescription = m.name + ". " + m.sentence
                                                    this.selected = chosen
                                                },
                                            verticalAlignment = Alignment.Top,
                                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        ) {
                                            Text(
                                                if (chosen) "◉" else "○",
                                                style = MaterialTheme.typography.bodyMedium,
                                                color = if (chosen) chrome.textHi else chrome.textMid,
                                            )
                                            Column(Modifier.weight(1f)) {
                                                Text(
                                                    m.name + if (m.id == t.mode) " · now" else "",
                                                    style = MaterialTheme.typography.bodyMedium,
                                                    color = chrome.textHi,
                                                )
                                                Text(
                                                    m.sentence,
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = chrome.textMid,
                                                )
                                            }
                                        }
                                    }
                                    if (pickMode != t.mode) {
                                        Gap(4)
                                        val p = preview
                                        val line = when {
                                            p != null -> p.line
                                            previewFailed -> ""
                                            else -> Topics.READING
                                        }
                                        if (line.isNotEmpty()) {
                                            Text(
                                                if (privateHidden) Topics.maskName(line, t.name, label) else line,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = chrome.textMid,
                                                modifier = Modifier.liveStatus(),
                                            )
                                        }
                                        // The PC decides what asks; without its answer this is only the label.
                                        val card = p?.cardLine
                                            ?: if (previewFailed && Topics.needsCard(t.mode, pickMode, t.isPrivate)) {
                                                Topics.w("private_asks")
                                            } else {
                                                ""
                                            }
                                        if (card.isNotEmpty()) {
                                            Text(card, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                                        }
                                    }
                                    pickSaid?.let {
                                        Gap(4)
                                        Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk,
                                            modifier = Modifier.liveStatus())
                                    }
                                    Gap(6)
                                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                        Primary(
                                            if (busy) "Sending…" else Topics.CHANGE,
                                            modifier = Modifier.weight(1f),
                                            enabled = canAct && !busy && pickMode != t.mode,
                                            onClick = {
                                                val body = Topics.modeBody(t.id, pickMode)
                                                if (body == null) {
                                                    pickSaid = Topics.errorSentence("bad_mode")
                                                } else {
                                                    busy = true
                                                    pickSaid = null
                                                    said = null
                                                    scope.launch {
                                                        try {
                                                            when (
                                                                val o = JarvisRuntime.topicsWrite(
                                                                    Topics.MODE_PATH, body, privateHidden,
                                                                )
                                                            ) {
                                                                is Topics.Outcome.Done -> {
                                                                    o.view?.let { view = it } ?: readNow()
                                                                    pickId = null
                                                                }
                                                                is Topics.Outcome.Waiting -> {
                                                                    said = o.message
                                                                    pickId = null
                                                                    readNow()
                                                                }
                                                                is Topics.Outcome.Failed -> pickSaid = o.said
                                                            }
                                                        } finally {
                                                            busy = false
                                                        }
                                                    }
                                                }
                                            },
                                        )
                                        Secondary(
                                            Topics.CANCEL,
                                            modifier = Modifier.weight(1f),
                                            onClick = { pickId = null; pickSaid = null },
                                        )
                                    }
                                }
                            }

                            // ---- "Show them": the facts of an Off topic ----
                            if (showId == t.id && !privateHidden) {
                                Gap(4)
                                Text(
                                    Topics.HIDDEN_FROM_ANSWERS,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = chrome.textMid,
                                )
                                val got = shown
                                when {
                                    got == null -> Text(
                                        shownError?.let { "Couldn't read them: $it" } ?: Topics.READING,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = if (shownError != null) chrome.warnInk else chrome.textLo,
                                    )
                                    got.facts.isEmpty() -> Text(
                                        Topics.NOTHING_TO_CHECK,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = chrome.textMid,
                                    )
                                }
                                got?.facts?.forEach { f ->
                                    Gap(6)
                                    Column(Modifier.fillMaxWidth()) {
                                        Text(f.text, style = MaterialTheme.typography.bodyMedium, color = chrome.textLo)
                                        when {
                                            forgetConfirm == f.id -> {
                                                Text(AutoLearn.FORGET_CONFIRM, style = MaterialTheme.typography.bodySmall,
                                                    color = chrome.warnInk)
                                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                    Quiet(
                                                        "Yes, forget it",
                                                        color = chrome.badInk,
                                                        enabled = canAct && !busy,
                                                        onClick = {
                                                            forgetConfirm = null
                                                            busy = true
                                                            scope.launch {
                                                                try {
                                                                    said = JarvisRuntime.forgetAutoFact(f.id).second
                                                                    reads += 1
                                                                } finally {
                                                                    busy = false
                                                                }
                                                            }
                                                        },
                                                    )
                                                    Quiet(Topics.KEEP_IT, onClick = { forgetConfirm = null })
                                                }
                                            }
                                            eraseConfirm == f.id -> {
                                                Text(MemoryErase.CONFIRM, style = MaterialTheme.typography.bodySmall,
                                                    color = chrome.warnInk)
                                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                    Quiet(
                                                        MemoryErase.YES,
                                                        color = chrome.badInk,
                                                        enabled = canAct && !busy,
                                                        onClick = {
                                                            eraseConfirm = null
                                                            busy = true
                                                            scope.launch {
                                                                try {
                                                                    said = JarvisRuntime.eraseAutoFact(f.id).second
                                                                    reads += 1
                                                                } finally {
                                                                    busy = false
                                                                }
                                                            }
                                                        },
                                                    )
                                                    Quiet(Topics.KEEP_IT, onClick = { eraseConfirm = null })
                                                }
                                            }
                                            else -> Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                                Quiet("Forget", color = chrome.textMid, enabled = canAct && !busy,
                                                    onClick = { forgetConfirm = f.id; eraseConfirm = null })
                                                Quiet(MemoryErase.LABEL, color = chrome.textMid, enabled = canAct && !busy,
                                                    onClick = { eraseConfirm = f.id; forgetConfirm = null })
                                            }
                                        }
                                    }
                                }
                            }

                            // ---- the edit menu: rename, colour and icon, move, private, delete ----
                            if (!privateHidden && !t.system) {
                                val open = editId == t.id
                                Quiet(
                                    if (open) Topics.DONE else Topics.EDIT,
                                    color = chrome.textMid,
                                    modifier = Modifier.semantics {
                                        contentDescription = (if (open) "Close editing " else "Edit ") + t.name
                                    },
                                    onClick = {
                                        editId = if (open) null else t.id
                                        renameText = t.name
                                        deleteId = null
                                        pickId = null
                                    },
                                )
                                if (open) {
                                    TextInput(
                                        value = renameText,
                                        onValueChange = { renameText = Topics.clipName(it, v.nameMax) },
                                        placeholder = Topics.NAME_PLACEHOLDER,
                                        modifier = Modifier.semantics { contentDescription = Topics.RENAME + " " + t.name },
                                    )
                                    Quiet(
                                        Topics.RENAME,
                                        enabled = canAct && !busy && Topics.cleanName(renameText, v.nameMax)
                                            .let { it != null && it != t.name },
                                        onClick = { send(Topics.TOPICS_PATH, Topics.renameBody(t.id, renameText)) },
                                    )
                                    Gap(4)
                                    Text(Topics.COLOUR, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                                    ColourChoices(t.colour, enabled = canAct && !busy) { slot ->
                                        if (slot != t.colour) send(Topics.TOPICS_PATH, Topics.styleBody(t.id, colour = slot))
                                    }
                                    Gap(4)
                                    Text(Topics.ICON, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                                    IconChoices(v.icons, t.icon, ink, enabled = canAct && !busy) { icon ->
                                        if (icon != t.icon) send(Topics.TOPICS_PATH, Topics.styleBody(t.id, icon = icon))
                                    }
                                    Gap(4)
                                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                        val up = Topics.moveUpBody(v, t.id)
                                        val down = Topics.moveDownBody(v, t.id)
                                        Quiet(Topics.MOVE_UP, enabled = canAct && !busy && up != null,
                                            onClick = { send(Topics.TOPICS_PATH, up) })
                                        Quiet(Topics.MOVE_DOWN, enabled = canAct && !busy && down != null,
                                            onClick = { send(Topics.TOPICS_PATH, down) })
                                    }
                                    // Marking private is at once; "Not private" asks (a 202 and ONE card).
                                    Quiet(
                                        if (t.isPrivate) Topics.NOT_PRIVATE else Topics.MARK_PRIVATE,
                                        enabled = canAct && !busy,
                                        onClick = { send(Topics.TOPICS_PATH, Topics.privateBody(t.id, !t.isPrivate)) },
                                    )
                                    if (t.isPrivate) {
                                        Text(
                                            Topics.w("private_asks"),
                                            style = MaterialTheme.typography.labelSmall,
                                            color = chrome.textLo,
                                        )
                                    }
                                    Text(
                                        Topics.w("words_pc_only"),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = chrome.textLo,
                                    )
                                    if (deleteId == t.id) {
                                        Gap(4)
                                        Text(Topics.w("confirm_delete"), style = MaterialTheme.typography.bodySmall,
                                            color = chrome.warnInk)
                                        Text(Topics.w("delete_where"), style = MaterialTheme.typography.bodyMedium,
                                            color = chrome.textHi)
                                        Topics.homes(v, t.id).forEach { h ->
                                            val chosen = homeId == h.id
                                            Row(
                                                Modifier
                                                    .fillMaxWidth()
                                                    .heightIn(min = 48.dp)
                                                    .clip(RoundedCornerShape(12.dp))
                                                    .pressable(role = Role.RadioButton, onClick = { homeId = h.id })
                                                    .padding(vertical = 4.dp)
                                                    .semantics(mergeDescendants = true) {
                                                        contentDescription = h.name + ", " + Topics.modeName(h.mode)
                                                        this.selected = chosen
                                                    },
                                                verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                            ) {
                                                Text(if (chosen) "◉" else "○",
                                                    style = MaterialTheme.typography.bodyMedium, color = chrome.textMid)
                                                TagIcon(h.icon, tagInk(h.colour), size = 16.dp)
                                                Text(
                                                    h.name + " · " + Topics.modeName(h.mode),
                                                    style = MaterialTheme.typography.bodyMedium,
                                                    color = chrome.textHi,
                                                )
                                            }
                                        }
                                        v.byId(homeId)?.let { home ->
                                            Topics.deleteLooser(t, home)?.let {
                                                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                                            }
                                        }
                                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Quiet(
                                                Topics.DELETE_YES,
                                                color = chrome.warnInk,
                                                enabled = canAct && !busy && homeId != null,
                                                onClick = {
                                                    send(Topics.TOPICS_PATH, Topics.deleteBody(t.id, homeId)) {
                                                        deleteId = null
                                                        editId = null
                                                    }
                                                },
                                            )
                                            Quiet(Topics.KEEP_IT, onClick = { deleteId = null })
                                        }
                                    } else {
                                        Quiet(
                                            Topics.DELETE,
                                            color = chrome.warnInk,
                                            enabled = canAct && !busy,
                                            onClick = { deleteId = t.id; homeId = null },
                                        )
                                    }
                                }
                            }
                        }
                    }

                    // ---- add a topic ----
                    if (!privateHidden) {
                        Gap(6)
                        Quiet(
                            if (addOpen) Topics.CANCEL else Topics.w("add_button"),
                            enabled = v.canAdd || addOpen,
                            onClick = { addOpen = !addOpen; addName = ""; addColour = null; addIcon = null },
                        )
                        if (!v.canAdd) {
                            Text(
                                Topics.ERRORS["too_many_topics"].orEmpty(),
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textMid,
                            )
                        }
                        if (addOpen) {
                            Text(Topics.w("add_title"), style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                            TextInput(
                                value = addName,
                                onValueChange = { addName = Topics.clipName(it, v.nameMax) },
                                placeholder = Topics.w("name_label"),
                                modifier = Modifier.semantics { contentDescription = Topics.w("add_title") },
                            )
                            Text(Topics.COLOUR, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            ColourChoices(addColour, enabled = !busy) { addColour = it }
                            Text(Topics.ICON, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            IconChoices(v.icons, addIcon, chrome.textHi, enabled = !busy) { addIcon = it }
                            Text(
                                Topics.w("words_pc_only"),
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                            Quiet(
                                Topics.SAVE,
                                enabled = canAct && !busy && v.canAdd && Topics.cleanName(addName, v.nameMax) != null,
                                onClick = {
                                    send(Topics.TOPICS_PATH, Topics.addBody(addName, addColour, addIcon)) {
                                        addOpen = false
                                        addName = ""
                                        addColour = null
                                        addIcon = null
                                    }
                                },
                            )
                        }
                    }

                    // ---- "Check these": Jarvis's guesses, ten at a time ----
                    if (reviewOpen && !privateHidden) {
                        Gap(8)
                        val r = review
                        when {
                            r == null -> Text(
                                reviewError?.let { "Couldn't read them: $it" } ?: Topics.READING,
                                style = MaterialTheme.typography.bodySmall,
                                color = if (reviewError != null) chrome.warnInk else chrome.textLo,
                            )
                            r.facts.isEmpty() -> Text(
                                Topics.NOTHING_TO_CHECK,
                                style = MaterialTheme.typography.bodyMedium,
                                color = chrome.textMid,
                            )
                            else -> {
                                Topics.groups(r.facts).forEach { (topicId, facts) ->
                                    val suggested = v.byId(topicId)
                                    Row(verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        if (suggested != null) TagIcon(suggested.icon, tagInk(suggested.colour), size = 16.dp)
                                        Text(
                                            suggested?.name ?: Topics.w("unsorted_name"),
                                            style = MaterialTheme.typography.labelLarge,
                                            color = suggested?.let { tagInk(it.colour) } ?: chrome.textMid,
                                        )
                                    }
                                    facts.forEach { f ->
                                        Gap(6)
                                        Column(Modifier.fillMaxWidth()) {
                                            Text(f.text, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                                            Row(
                                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                                verticalAlignment = Alignment.CenterVertically,
                                            ) {
                                                if (f.guessed) Pill(Topics.w("check_guessed"))
                                                if (f.heldBack) {
                                                    Text(
                                                        Topics.heldLine(suggested?.name ?: Topics.w("unsorted_name")),
                                                        style = MaterialTheme.typography.labelSmall,
                                                        color = chrome.warnInk,
                                                    )
                                                }
                                            }
                                            Quiet(
                                                if (fileFor == f.id) Topics.CANCEL else Topics.FILE_UNDER,
                                                color = chrome.textMid,
                                                onClick = { fileFor = if (fileFor == f.id) null else f.id },
                                            )
                                            if (fileFor == f.id) {
                                                FlowRow(
                                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                                    verticalArrangement = Arrangement.spacedBy(4.dp),
                                                ) {
                                                    v.topics.forEach { dest ->
                                                        Row(
                                                            Modifier
                                                                .heightIn(min = 48.dp)
                                                                .clip(RoundedCornerShape(12.dp))
                                                                .pressable(enabled = canAct && !busy, role = Role.Button, onClick = {
                                                                    send(Topics.FILE_PATH, Topics.fileBody(listOf(f.id), dest.id)) {
                                                                        fileFor = null
                                                                        scope.launch { readReview() }
                                                                    }
                                                                })
                                                                .padding(horizontal = 10.dp, vertical = 8.dp)
                                                                .semantics(mergeDescendants = true) {
                                                                    contentDescription = Topics.FILE_UNDER + " " + dest.name
                                                                },
                                                            verticalAlignment = Alignment.CenterVertically,
                                                            horizontalArrangement = Arrangement.spacedBy(5.dp),
                                                        ) {
                                                            TagIcon(dest.icon, tagInk(dest.colour), size = 16.dp)
                                                            Text(dest.name, style = MaterialTheme.typography.labelMedium,
                                                                color = tagInk(dest.colour), maxLines = 1)
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                Gap(8)
                                Secondary(
                                    Topics.w("check_right"),
                                    modifier = Modifier.fillMaxWidth(),
                                    enabled = canAct && !busy,
                                    onClick = {
                                        send(Topics.FILE_PATH, Topics.confirmBody(r.facts.map { it.id })) {
                                            scope.launch { readReview() }
                                        }
                                    },
                                )
                                if (r.next != null) {
                                    Quiet(Topics.NEXT_BATCH, onClick = { reviewAfter = r.next })
                                }
                            }
                        }
                    }

                    // ---- the model switch ----
                    Gap(8)
                    SwitchRow(
                        title = Topics.w("model_help"),
                        detail = Topics.w("model_help_note"),
                        checked = v.modelHelp,
                        enabled = canAct && !busy,
                        onChange = { want -> send(Topics.SETTINGS_PATH, Topics.settingsBody(want)) },
                    )
                }
            }
            said?.let {
                Gap(4)
                Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus())
            }
        }
    }
}

/** The eight colour slots as one row of choices: a dot, then the colour's name. Never colour alone. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ColourChoices(selected: Int?, enabled: Boolean, onPick: (Int) -> Unit) {
    val chrome = LocalChrome.current
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        ChatTags.COLOUR_NAMES.forEachIndexed { slot, colourName ->
            val chosen = slot == selected
            Row(
                Modifier
                    .heightIn(min = 48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .pressable(enabled = enabled, role = Role.RadioButton, onClick = { onPick(slot) })
                    .padding(horizontal = 10.dp, vertical = 8.dp)
                    .semantics(mergeDescendants = true) {
                        contentDescription = "${Topics.COLOUR}: $colourName"
                        this.selected = chosen
                    },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Dot(tagInk(slot), size = 12)
                Text(
                    if (chosen) "• $colourName" else colourName,
                    style = MaterialTheme.typography.labelMedium,
                    color = chrome.textHi,
                )
            }
        }
    }
}

/** The icons ([Topics.ICONS] plus what the PC lists) as 48dp squares; the chosen one is ringed, and named to TalkBack. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun IconChoices(
    icons: List<String>,
    selected: String?,
    ink: androidx.compose.ui.graphics.Color,
    enabled: Boolean,
    onPick: (String) -> Unit,
) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        icons.forEach { icon ->
            val chosen = icon == selected
            Box(
                Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .then(if (chosen) Modifier.border(2.dp, ink, RoundedCornerShape(12.dp)) else Modifier)
                    .pressable(enabled = enabled, role = Role.RadioButton, onClick = { onPick(icon) })
                    .semantics {
                        contentDescription = "${Topics.ICON}: $icon"
                        this.selected = chosen
                    },
                contentAlignment = Alignment.Center,
            ) {
                TagIcon(icon, ink, size = 22.dp)
            }
        }
    }
}
