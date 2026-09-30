package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Decks
import com.jarvis.client.net.Quiz
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "My study decks" on Brain ([Decks], docs/QUIZ-DECKS-DESIGN.md, contract
 * C1-C6; docs/JARVIS-API.md section 102) - beside "Quiz me on a text"
 * ([QuizSection]), matching the desktop's own section.
 *
 * Questions kept from a finished quiz sit in decks on the PC (sealed there).
 * This section shows the PC's plain line ("3 cards ready"), "New cards a
 * day", and every deck with Review, Pause / Resume, Cards and Delete this
 * deck. Reviewing shows one card at a time: the front, "Show answer", then
 * four buttons for how it went - the OWNER rates every card, no model is
 * called. Deleting a deck or a card asks "Are you sure?" first and is then
 * immediate. No approval card exists anywhere in this slice.
 *
 * NOTHING IS SAVED ON THIS PHONE: every word here is held by this screen's
 * memory only (plain `remember`, never `rememberSaveable`, never a file or a
 * preference). The box under a card's front is for the owner alone - it is
 * never sent and is dropped on Show answer.
 *
 * "Hide memory lists and chat history" hides deck names, fronts, backs and
 * passages; the counts and the line stay. Review and the card lists are
 * unavailable while hidden. Writes are held on a stale link (rule 4). There is
 * no streak, score, count of days or chart: a card left for a month is simply
 * ready.
 */
@Composable
internal fun DecksSection(
    canAct: Boolean,
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val tick by JarvisRuntime.decksTick.collectAsState()
    var reads by remember { mutableIntStateOf(0) }
    var list by remember { mutableStateOf<Decks.DeckList?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var said by remember { mutableStateOf<String?>(null) }
    var perDay by remember { mutableIntStateOf(5) }
    var confirmDeck by remember { mutableStateOf<String?>(null) }
    // The deck being renamed (Edit on its row), and the name typed so far.
    var renaming by remember { mutableStateOf<String?>(null) }
    var renameText by remember { mutableStateOf("") }
    var newOpen by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    // The review in progress, if any.
    var review by remember { mutableStateOf<ReviewRun?>(null) }
    // The deck whose cards are open, and the card being edited or deleted.
    var managing by remember { mutableStateOf<String?>(null) }
    var cards by remember { mutableStateOf<Decks.DeckCards?>(null) }
    var cardsError by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<String?>(null) }
    var editFront by remember { mutableStateOf("") }
    var editBack by remember { mutableStateOf("") }
    var confirmCard by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(reads, tick) {
        val out = JarvisRuntime.decksList()
        val v = out.value
        if (out.ok && v != null) {
            list = v
            missing = false
            readError = null
            perDay = v.newPerDay
        } else if (out.said == Decks.MISSING) {
            missing = true
            readError = null
        } else {
            readError = out.said
        }
    }

    // The words of a deck's cards are read only while the lists are shown.
    LaunchedEffect(managing, reads, tick, privateHidden) {
        val id = managing
        if (id == null || privateHidden) {
            cards = null
            return@LaunchedEffect
        }
        val out = JarvisRuntime.decksCards(id)
        val v = out.value
        if (out.ok && v != null) {
            cards = v
            cardsError = null
        } else {
            cardsError = out.said
        }
    }

    // Hiding the lists ends a review and closes the card lists: their words go with them.
    LaunchedEffect(privateHidden) {
        if (privateHidden) {
            review = null
            editing = null
            confirmCard = null
        }
    }

    fun startReview(deck: String?) {
        if (busy) return
        busy = true
        said = null
        scope.launch {
            try {
                val out = JarvisRuntime.reviewStart(deck)
                val rv = out.value
                if (out.ok && rv != null) {
                    if (rv.state == "no_decks") {
                        review = null
                        reads += 1
                    } else {
                        review = ReviewRun(deck, rv, null, "")
                    }
                } else {
                    said = out.said
                }
            } finally {
                busy = false
            }
        }
    }

    /** Reads the review again (a card that is gone, or a run that changed under it). */
    suspend fun refetch(deck: String?) {
        val out = JarvisRuntime.reviewStart(deck)
        val rv = out.value
        if (out.ok && rv != null && rv.state != "no_decks") review = ReviewRun(deck, rv, null, "")
        else if (out.ok) review = null
    }

    fun act(id: String, op: String) {
        if (!canAct || busy) return
        busy = true
        said = null
        scope.launch {
            try {
                val out = JarvisRuntime.decksAct(id, op)
                if (out.ok) {
                    confirmDeck = null
                    if (op == "delete" && managing == id) managing = null
                } else {
                    said = out.said
                    if (out.code == Decks.E_NOT_FOUND) reads += 1
                }
            } finally {
                busy = false
            }
        }
    }

    fun setPerDay(n: Int) {
        if (!canAct || busy || !Decks.validPerDay(n)) return
        busy = true
        said = null
        scope.launch {
            try {
                val out = JarvisRuntime.decksSetPerDay(n)
                val v = out.value
                if (out.ok && v != null) perDay = v else said = out.said
            } finally {
                busy = false
            }
        }
    }

    Section(Decks.TITLE, trailing = { Quiet(Decks.REFRESH, onClick = { reads += 1 }) }) {
        Plate {
            val shown = list?.let { if (privateHidden) Decks.hide(it) else it }
            val err = readError
            val run = review
            when {
                missing -> Text(Decks.MISSING, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                shown == null -> Text(
                    if (err != null) "Couldn't read your decks: $err" else Decks.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                run != null -> ReviewView(
                    run = run,
                    nextReadyDay = shown.nextReadyDay,
                    enabled = canAct && !busy,
                    onTyped = { review = run.copy(typed = it.take(Decks.DEFAULT_MAX_BACK)) },
                    onShowAnswer = {
                        val card = run.review.card
                        if (card != null && !busy) {
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    val out = JarvisRuntime.reviewReveal(card.id)
                                    val back = out.value
                                    if (out.ok && back != null) {
                                        // What was typed for the owner alone is dropped here; it was never sent.
                                        review = run.copy(reveal = back, typed = "")
                                    } else {
                                        said = out.said
                                        if (out.code == Decks.E_CARD_NOT_FOUND) refetch(run.deck)
                                    }
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    },
                    onRate = { rating ->
                        val card = run.review.card
                        if (card != null && !busy) {
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    val out = JarvisRuntime.reviewRate(card.id, rating, run.deck)
                                    val next = out.value
                                    if (out.ok && next != null) {
                                        if (next.state == "no_decks") {
                                            review = null
                                            reads += 1
                                        } else {
                                            review = ReviewRun(run.deck, next, null, "")
                                            said = Decks.comesBackLine(next.comesBack).ifEmpty { null }
                                        }
                                    } else {
                                        said = out.said
                                        // The card is gone, or the PC no longer remembers that its
                                        // back was shown (it restarted): drop the reveal and ask for
                                        // the card again, so the answer can be shown and rated.
                                        if (out.code == Decks.E_CARD_NOT_FOUND || out.code == Decks.E_NOT_REVEALED) {
                                            refetch(run.deck)
                                        }
                                    }
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    },
                    onMore = {
                        if (!busy) {
                            busy = true
                            said = null
                            scope.launch {
                                try {
                                    val out = JarvisRuntime.reviewMore(run.deck)
                                    val rv = out.value
                                    if (out.ok && rv != null) review = ReviewRun(run.deck, rv, null, "")
                                    else said = out.said
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    },
                    onStop = {
                        review = null
                        said = null
                        reads += 1
                    },
                )
                managing != null -> {
                    val id = managing.orEmpty()
                    val deckName = shown.decks.firstOrNull { it.id == id }?.name
                    ManageView(
                        deckName = if (privateHidden) Decks.HIDDEN_TEXT else (cards?.deckName ?: deckName.orEmpty()),
                        cards = cards?.let { if (privateHidden) Decks.hide(it) else it },
                        error = cardsError,
                        hidden = privateHidden,
                        enabled = canAct && !busy,
                        editing = editing,
                        editFront = editFront,
                        editBack = editBack,
                        confirmCard = confirmCard,
                        maxFront = shown.limits.front,
                        maxBack = shown.limits.back,
                        onEditFront = { editFront = it.take(shown.limits.front) },
                        onEditBack = { editBack = it.take(shown.limits.back) },
                        onEdit = { c ->
                            editing = c.id
                            editFront = c.front
                            editBack = c.back
                            confirmCard = null
                        },
                        onSave = {
                            val cid = editing
                            if (cid != null && canAct && !busy) {
                                busy = true
                                said = null
                                scope.launch {
                                    try {
                                        val out = JarvisRuntime.decksCardEdit(id, cid, editFront, editBack)
                                        if (out.ok) editing = null else said = out.said
                                    } finally {
                                        busy = false
                                    }
                                }
                            }
                        },
                        onCancelEdit = { editing = null },
                        onAskDelete = { confirmCard = it; editing = null },
                        onCancelDelete = { confirmCard = null },
                        onDelete = { cid ->
                            if (canAct && !busy) {
                                busy = true
                                said = null
                                scope.launch {
                                    try {
                                        val out = JarvisRuntime.decksCardDelete(id, cid)
                                        if (out.ok) confirmCard = null else said = out.said
                                    } finally {
                                        busy = false
                                    }
                                }
                            }
                        },
                        onBack = {
                            managing = null
                            cards = null
                            editing = null
                            confirmCard = null
                            said = null
                        },
                    )
                }
                else -> {
                    if (err != null) {
                        Text(
                            "Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk,
                        )
                    }
                    if (!shown.available) {
                        // The PC's own words, word for word; the counts still work.
                        Text(shown.why, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                        Gap(4)
                    }
                    if (privateHidden && shown.decks.isNotEmpty()) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "Words hidden. Tap Show and confirm it is you.",
                                style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                                modifier = Modifier.weight(1f),
                            )
                            Quiet(
                                if (showPrivateBusy) "Checking…" else "Show",
                                enabled = !showPrivateBusy, onClick = onShowPrivate,
                            )
                        }
                    }
                    if (shown.decks.isEmpty() && shown.line.isEmpty()) {
                        Text(Decks.EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    } else {
                        Text(Decks.READY_HEADING, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Text(
                            shown.line.ifEmpty { Decks.NOTHING_READY },
                            style = MaterialTheme.typography.titleSmall, color = chrome.textHi,
                            modifier = Modifier.liveStatus(),
                        )
                        if (shown.ready == 0) {
                            Decks.nextReadyLine(shown.nextReadyDay).takeIf { it.isNotEmpty() }?.let {
                                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            }
                        }
                        if (shown.ready > 0 && shown.available) {
                            Quiet(
                                Decks.REVIEW,
                                modifier = Modifier.semantics { contentDescription = "Review all decks" },
                                enabled = canAct && !busy && Decks.canReviewAll(shown.ready, shown.available, privateHidden),
                                onClick = { startReview(null) },
                            )
                            if (privateHidden) {
                                Text(Decks.HIDDEN_REVIEW, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                            }
                        }
                    }
                    Gap(8)
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.semantics { contentDescription = "${Decks.NEW_PER_DAY}: $perDay" },
                    ) {
                        Text(
                            Decks.NEW_PER_DAY,
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                            modifier = Modifier.weight(1f),
                        )
                        Quiet(
                            Decks.FEWER,
                            modifier = Modifier.semantics { contentDescription = Decks.FEWER_WORDS },
                            enabled = canAct && !busy && perDay > 0,
                            onClick = { setPerDay(perDay - 1) },
                        )
                        Text("$perDay", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
                        Quiet(
                            Decks.MORE,
                            modifier = Modifier.semantics { contentDescription = Decks.MORE_WORDS },
                            enabled = canAct && !busy && perDay < shown.limits.newPerDay,
                            onClick = { setPerDay(perDay + 1) },
                        )
                    }
                    shown.decks.forEach { d ->
                        Gap(10)
                        DeckRow(
                            deck = d,
                            hidden = privateHidden,
                            enabled = canAct && !busy,
                            confirming = confirmDeck == d.id,
                            renaming = renaming == d.id,
                            renameText = renameText,
                            maxName = shown.limits.name,
                            onRenameText = { renameText = it.take(shown.limits.name) },
                            onEdit = { renaming = d.id; renameText = d.name; confirmDeck = null },
                            onCancelRename = { renaming = null },
                            onSaveRename = {
                                if (canAct && !busy && Decks.validName(renameText, shown.limits.name)) {
                                    busy = true
                                    said = null
                                    scope.launch {
                                        try {
                                            val out = JarvisRuntime.decksRename(d.id, renameText)
                                            if (out.ok) renaming = null else said = out.said
                                            if (!out.ok && out.code == Decks.E_NOT_FOUND) reads += 1
                                        } finally {
                                            busy = false
                                        }
                                    }
                                }
                            },
                            onReview = { startReview(d.id) },
                            onTogglePause = { act(d.id, if (d.paused) "resume" else "pause") },
                            onCards = {
                                managing = d.id
                                cards = null
                                cardsError = null
                                editing = null
                                confirmCard = null
                                said = null
                            },
                            onAskDelete = { confirmDeck = d.id },
                            onCancelDelete = { confirmDeck = null },
                            onDelete = { act(d.id, "delete") },
                        )
                    }
                    if (shown.decks.isNotEmpty() && Decks.perDeckNoteShown(shown)) {
                        Gap(6)
                        Text(Decks.PER_DECK_NOTE, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                    }
                    Gap(10)
                    if (shown.available) {
                        val atLimit = shown.decks.size >= shown.limits.decks
                        if (newOpen && !privateHidden) {
                            TextInput(
                                value = newName,
                                onValueChange = { newName = it.take(shown.limits.name) },
                                placeholder = Decks.DECK_NAME,
                                supportingText = "${newName.length} / ${shown.limits.name}",
                            )
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Quiet(
                                    Decks.SAVE,
                                    enabled = canAct && !busy && Decks.validName(newName, shown.limits.name),
                                    onClick = {
                                        busy = true
                                        said = null
                                        scope.launch {
                                            try {
                                                val out = JarvisRuntime.decksCreate(newName)
                                                if (out.ok) {
                                                    newOpen = false
                                                    newName = ""
                                                } else {
                                                    said = out.said
                                                }
                                            } finally {
                                                busy = false
                                            }
                                        }
                                    },
                                )
                                Quiet(Decks.CANCEL, onClick = { newOpen = false; newName = "" })
                            }
                        } else if (!privateHidden) {
                            Quiet(
                                Decks.NEW_DECK,
                                enabled = canAct && !busy && !atLimit,
                                onClick = { newOpen = true },
                            )
                            if (atLimit) {
                                Text(
                                    "There are already ${shown.limits.decks} decks - delete one before adding another.",
                                    style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                                )
                            }
                        }
                    }
                }
            }
            said?.let {
                Gap(4)
                Text(
                    it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid,
                    modifier = Modifier.liveStatus(),
                )
            }
            if (!missing && shown != null && !canAct) {
                Text(
                    "Not connected to the desktop, so changes wait until the link is back.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }
}

/**
 * The review in progress: the deck it was started from (null = every deck),
 * the PC's last answer, the revealed back once "Show answer" was tapped, and
 * the owner's own scratch words (never sent).
 */
private data class ReviewRun(
    val deck: String?,
    val review: Decks.Review,
    val reveal: Decks.Reveal?,
    val typed: String,
)

/** One deck: its name, counts, and its own controls. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DeckRow(
    deck: Decks.Deck,
    hidden: Boolean,
    enabled: Boolean,
    confirming: Boolean,
    renaming: Boolean,
    renameText: String,
    maxName: Int,
    onRenameText: (String) -> Unit,
    onEdit: () -> Unit,
    onCancelRename: () -> Unit,
    onSaveRename: () -> Unit,
    onReview: () -> Unit,
    onTogglePause: () -> Unit,
    onCards: () -> Unit,
    onAskDelete: () -> Unit,
    onCancelDelete: () -> Unit,
    onDelete: () -> Unit,
) {
    val chrome = LocalChrome.current
    val name = if (hidden) Decks.HIDDEN_TEXT else deck.name
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                name,
                style = MaterialTheme.typography.bodyMedium, color = chrome.textHi,
                modifier = Modifier.weight(1f, fill = false),
            )
            if (deck.paused) Pill(Decks.PAUSED_TAG, color = chrome.textMid)
        }
        Text(Decks.countsLine(deck), style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        if (renaming && !hidden) {
            TextInput(
                value = renameText,
                onValueChange = onRenameText,
                placeholder = Decks.DECK_NAME,
                supportingText = "${renameText.length} / $maxName",
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Quiet(Decks.SAVE, enabled = enabled && Decks.validName(renameText, maxName), onClick = onSaveRename)
                Quiet(Decks.CANCEL, onClick = onCancelRename)
            }
            return@Column
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Quiet(
                Decks.REVIEW,
                modifier = Modifier.semantics { contentDescription = "${Decks.REVIEW} $name" },
                enabled = enabled && Decks.canReview(deck, hidden = hidden),
                onClick = onReview,
            )
            Quiet(
                if (deck.paused) Decks.RESUME else Decks.PAUSE,
                modifier = Modifier.semantics {
                    contentDescription = (if (deck.paused) Decks.RESUME else Decks.PAUSE) + " " + name
                },
                enabled = enabled,
                onClick = onTogglePause,
            )
            Quiet(
                Decks.CARDS,
                modifier = Modifier.semantics { contentDescription = "${Decks.CARDS}: $name" },
                enabled = !hidden,
                onClick = onCards,
            )
            Quiet(
                Decks.EDIT,
                modifier = Modifier.semantics { contentDescription = "${Decks.EDIT}: $name" },
                enabled = enabled && !hidden,
                onClick = onEdit,
            )
            Quiet(
                Decks.DELETE_DECK,
                modifier = Modifier.semantics { contentDescription = "${Decks.DELETE_DECK}: $name" },
                color = chrome.badInk,
                enabled = enabled,
                onClick = onAskDelete,
            )
        }
        if (hidden) {
            Text(Decks.HIDDEN_REVIEW, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        if (confirming) {
            Text(Decks.CONFIRM_DELETE, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Quiet(Decks.DELETE, color = chrome.badInk, enabled = enabled, onClick = onDelete)
                Quiet(Decks.CANCEL, onClick = onCancelDelete)
            }
        }
    }
}

/**
 * The review session (contract C4): a card's front, "Show answer", then the
 * four ratings. The states: `card`, `empty`, `enough`, `paused`.
 */
@Composable
private fun ReviewView(
    run: ReviewRun,
    nextReadyDay: String?,
    enabled: Boolean,
    onTyped: (String) -> Unit,
    onShowAnswer: () -> Unit,
    onRate: (String) -> Unit,
    onMore: () -> Unit,
    onStop: () -> Unit,
) {
    val chrome = LocalChrome.current
    val rv = run.review
    val card = rv.card
    Column(Modifier.fillMaxWidth()) {
        when {
            rv.state == "card" && card != null -> {
                if (rv.line.isNotEmpty()) {
                    Text(rv.line, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
                Quiz.kindWords(card.kind).takeIf { it.isNotEmpty() }?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
                Decks.levelLine(card.level).takeIf { it.isNotEmpty() }?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
                Gap(4)
                Text(card.front, style = MaterialTheme.typography.bodyLarge, color = chrome.textHi)
                Gap(8)
                val back = run.reveal
                if (back == null) {
                    TextInput(
                        value = run.typed,
                        onValueChange = onTyped,
                        placeholder = Decks.TYPE_HINT,
                        singleLine = false,
                        maxLines = 4,
                    )
                    Gap(4)
                    Primary(
                        Decks.SHOW_ANSWER,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = enabled,
                        onClick = onShowAnswer,
                    )
                } else {
                    if (back.answer.isNotEmpty()) {
                        Text(Decks.ANSWER_HEADING, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        Text(back.answer, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        back.keyLabel?.let {
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                    }
                    if (back.passage.isNotEmpty()) {
                        Gap(4)
                        Text(
                            Decks.passageHeading(back.keyLabel),
                            style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                        )
                        Text(back.passage, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    }
                    Gap(8)
                    // In the contract's order, all the same weight: no rating is louder or redder than another.
                    Decks.RATINGS.forEach { (id, words) ->
                        Secondary(
                            words,
                            modifier = Modifier.fillMaxWidth(),
                            enabled = enabled,
                            onClick = { onRate(id) },
                        )
                        Gap(4)
                    }
                }
            }
            rv.state == "enough" -> {
                Text(Decks.ENOUGH, style = MaterialTheme.typography.titleSmall, color = chrome.textHi, modifier = Modifier.liveStatus())
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Quiet(Decks.DO_10_MORE, enabled = enabled, onClick = onMore)
                }
            }
            rv.state == "paused" -> {
                Text(
                    rv.line.ifEmpty { Decks.PAUSED_TAG },
                    style = MaterialTheme.typography.titleSmall, color = chrome.textHi,
                    modifier = Modifier.liveStatus(),
                )
            }
            else -> {
                // "empty", and any state this phone does not know: nothing to show, said plainly.
                Text(
                    Decks.NOTHING_READY,
                    style = MaterialTheme.typography.titleSmall, color = chrome.textHi,
                    modifier = Modifier.liveStatus(),
                )
                Decks.nextReadyLine(nextReadyDay).takeIf { it.isNotEmpty() }?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                }
            }
        }
        Quiet(Decks.STOP, color = chrome.textMid, onClick = onStop)
    }
}

/** One deck's cards, for fixing a word or removing a card. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ManageView(
    deckName: String,
    cards: Decks.DeckCards?,
    error: String?,
    hidden: Boolean,
    enabled: Boolean,
    editing: String?,
    editFront: String,
    editBack: String,
    confirmCard: String?,
    maxFront: Int,
    maxBack: Int,
    onEditFront: (String) -> Unit,
    onEditBack: (String) -> Unit,
    onEdit: (Decks.CardFull) -> Unit,
    onSave: () -> Unit,
    onCancelEdit: () -> Unit,
    onAskDelete: (String) -> Unit,
    onCancelDelete: () -> Unit,
    onDelete: (String) -> Unit,
    onBack: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${Decks.CARDS}: $deckName",
                style = MaterialTheme.typography.titleSmall, color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Quiet(Decks.BACK_TO_DECKS, onClick = onBack)
        }
        when {
            hidden -> Text(Decks.CARDS_HIDDEN, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            cards == null -> Text(
                error ?: Decks.READING,
                style = MaterialTheme.typography.labelSmall,
                color = if (error != null) chrome.warnInk else chrome.textLo,
            )
            cards.cards.isEmpty() -> Text(Decks.NO_CARDS, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            else -> cards.cards.forEach { c ->
                Gap(10)
                Column(Modifier.fillMaxWidth()) {
                    val kindLine = listOf(Quiz.kindWords(c.kind), Decks.levelLine(c.level))
                        .filter { it.isNotEmpty() }.joinToString(" · ")
                    if (kindLine.isNotEmpty()) {
                        Text(kindLine, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                    }
                    if (editing == c.id) {
                        TextInput(
                            value = editFront,
                            onValueChange = onEditFront,
                            placeholder = Decks.FRONT_HINT,
                            supportingText = "${editFront.length} / $maxFront",
                            singleLine = false,
                            maxLines = 4,
                        )
                        Gap(4)
                        TextInput(
                            value = editBack,
                            onValueChange = onEditBack,
                            placeholder = Decks.BACK_HINT,
                            supportingText = "${editBack.length} / $maxBack",
                            singleLine = false,
                            maxLines = 6,
                        )
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Quiet(
                                Decks.SAVE,
                                enabled = enabled && Decks.validFront(editFront, maxFront) && Decks.validBack(editBack, maxBack),
                                onClick = onSave,
                            )
                            Quiet(Decks.CANCEL, onClick = onCancelEdit)
                        }
                    } else {
                        Text(c.front, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        if (c.back.isNotEmpty()) {
                            Text(c.back, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                        }
                        c.keyLabel?.let {
                            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                        }
                        if (c.passage.isNotEmpty()) {
                            Text(
                                if (c.keySource == "model") Decks.EXAMPLE_SENTENCE else Decks.FROM_TEXT,
                                style = MaterialTheme.typography.labelSmall, color = chrome.textLo,
                            )
                            Text(c.passage, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            Quiet(
                                Decks.EDIT,
                                modifier = Modifier.semantics { contentDescription = "${Decks.EDIT}: ${c.front}" },
                                enabled = enabled,
                                onClick = { onEdit(c) },
                            )
                            Quiet(
                                Decks.DELETE_CARD,
                                modifier = Modifier.semantics { contentDescription = "${Decks.DELETE_CARD}: ${c.front}" },
                                color = chrome.badInk,
                                enabled = enabled,
                                onClick = { onAskDelete(c.id) },
                            )
                        }
                        if (confirmCard == c.id) {
                            Text(Decks.CONFIRM_DELETE, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Quiet(Decks.DELETE, color = chrome.badInk, enabled = enabled, onClick = { onDelete(c.id) })
                                Quiet(Decks.CANCEL, onClick = onCancelDelete)
                            }
                        }
                    }
                }
            }
        }
    }
}
