package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Entities
import com.jarvis.client.net.MemoryAsOf
import com.jarvis.client.net.MemoryDates
import com.jarvis.client.net.MemoryUsed
import com.jarvis.client.net.PeopleDossier
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

/**
 * "People and things" on Brain ([Entities], the owner's decision of
 * 2026-09-30, docs/GALAXY-PANEL-DESIGN.md option B): the people, pets,
 * places and things Jarvis's saved facts name. A list grouped by kind -
 * People, Pets, Places, Organisations, Projects, Things, Other - each row a
 * name and how many facts name it. Tap one to read those facts, newest first,
 * 20 at a time ("Show 20 more"), and the **other names those same facts
 * mention** ("Shares facts with").
 *
 * ## This is the phone's Galaxy, and it is deliberately read-only
 *
 * The owner asked for the Galaxy on his phone (2026-10-11) - "can i see the
 * galaxy on the android phone? I should be able to see it" - and, offered a
 * choice, picked a light, read-only version built for the phone. So this
 * screen shows the same information the desktop's map carries. What the map
 * draws as a line between two dots, [Entities.connections] says in words: the
 * names that appear in the same saved facts. A thumb-width column and a
 * screen reader both get more from "Priya, 4 shared facts" than from two
 * points and a line, and it is the same fact the line stands for.
 *
 * **Read-only, on purpose** - the owner's decision, not an oversight. There is
 * no Forget, no Erase, no Pin, no merge, no rename and nothing to drag here,
 * though this app offers Forget a few plates away. Those live in the memory
 * lists where they already are; this screen exists to be looked at. Do not add
 * one without asking the owner first, and read [Entities]'s docstring for the
 * full reason.
 *
 * ## The picture, and why the list stays
 *
 * The owner asked for the Galaxy drawn on the phone too (2026-10-26: "i want
 * the android phone to have a picture"). [GalaxyPicture] draws it above this
 * list: deterministic positions (the desktop's own zen-ring layout, ported and
 * pinned to the desktop JavaScript - no force simulation and no animation),
 * read-only, and capped so a thumb-width canvas stays legible. That
 * deliberately reverses only the "no canvas on the phone" part of the standing
 * rule: the list below is unchanged, every name is still in it, and the
 * picture is a view of the same data rather than the only way to reach any of
 * it. There is still no GL/AGSL and nothing to animate.
 *
 * Two reads, no new route: the names from `GET /api/memory/entities`, the
 * words from `GET /api/memory/used?ids=` ([JarvisRuntime.memoryUsed]). Both
 * are read when this is shown and dropped when it is left; nothing is kept on
 * the phone. The connections need **neither** - they are worked out from the
 * same list of names already in memory, so opening a name is not a second
 * round trip, and the picture reads nothing at all beyond that list.
 *
 * "Hide memory lists and chat history" (Security) replaces the whole thing
 * with [HiddenSection] until Show is confirmed, and because the panel is part
 * of this composable, its words go with it.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun PeopleAndThingsSection(
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    if (privateHidden) {
        HiddenSection(Entities.TITLE, busy = showPrivateBusy, onShow = onShowPrivate)
        return
    }
    val chrome = LocalChrome.current
    var reads by remember { mutableIntStateOf(0) }
    var entities by remember { mutableStateOf<List<Entities.Entity>?>(null) }
    var missing by remember { mutableStateOf(false) }
    var readError by remember { mutableStateOf<String?>(null) }
    var openId by remember { mutableStateOf<String?>(null) }
    // Whether the name on screen was opened from a dot of the PICTURE. The
    // picture draws every name, while a kind chip or the search narrows the
    // list below it (the picture is not filtered - the owner asked to see the
    // Galaxy, not his filter). So a picture-opened name has its connections
    // read from the UNFILTERED list: the dot's "shares facts with N names" and
    // the panel's "Shares facts with" line must say the same number, and a
    // filter must not silently drop a connection the dot promised.
    var openedFromPicture by remember { mutableStateOf(false) }
    // A1 (2026-10-21): the kind chips, the search box and the as-of chips.
    // Every one of them is a VIEW of the one list this plate already reads: the
    // chip and the search filter in memory, and the as-of chips narrow each
    // name's own fact ids to the ones the PC says were active on that date. No
    // route is added, nothing is written, and the picture above is a view, not
    // a control.
    var kind by remember { mutableStateOf(Entities.ALL) }
    var search by remember { mutableStateOf("") }
    var asOfEpoch by remember { mutableStateOf<Long?>(null) }
    var asOfLabel by remember { mutableStateOf("") }
    var asOfWhich by remember { mutableStateOf("") }
    var asOfFacts by remember { mutableStateOf<List<MemoryAsOf.RawFact>?>(null) }
    // The epoch those rows were read for. Kept beside them so a row list can
    // never be drawn under another date's heading (AND-1, 2026-10-24).
    var asOfFactsEpoch by remember { mutableStateOf<Long?>(null) }
    var asOfBusy by remember { mutableStateOf(false) }
    var asOfError by remember { mutableStateOf<String?>(null) }
    var dateOpen by remember { mutableStateOf(false) }
    var dateText by remember { mutableStateOf("") }
    var dateBad by remember { mutableStateOf(false) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.memoryEntities()) {
            is ApiResult.Ok -> {
                val list = Entities.parse(r.value)
                if (list == null) {
                    missing = true
                } else {
                    entities = list
                    missing = false
                }
                readError = null
            }
            is ApiResult.Failed -> if (Entities.missing(r.error)) {
                missing = true
                readError = null
            } else {
                readError = JarvisRuntime.noticeFor(r.error)
            }
        }
    }

    // One read of the as-of facts per chip, thrown away when another date is
    // picked - the same one-shot read the Memory screen's as-of plate already
    // uses ([JarvisRuntime.memoryAsOf]). It is a READ: nothing is written, and
    // the plate never sees it until the owner picks a past chip.
    LaunchedEffect(asOfEpoch, reads) {
        val epoch = asOfEpoch
        if (epoch == null) {
            asOfFacts = null
            asOfFactsEpoch = null
            asOfBusy = false
            asOfError = null
            return@LaunchedEffect
        }
        asOfBusy = true
        asOfError = null
        when (val r = JarvisRuntime.memoryAsOf(epoch)) {
            is ApiResult.Ok -> {
                val rows = MemoryAsOf.parseRows(r.value)
                if (rows == null) {
                    asOfError = "The PC's answer for that date did not carry the facts."
                } else {
                    asOfFacts = rows
                    asOfFactsEpoch = epoch
                }
            }
            is ApiResult.Failed -> asOfError = JarvisRuntime.noticeFor(r.error)
        }
        asOfBusy = false
    }

    fun pickAsOf(epoch: Long?, which: String) {
        asOfEpoch = epoch
        asOfWhich = which
        asOfLabel = if (epoch == null) "" else
            (Entities.dateText(epoch.toDouble()) ?: "")
        asOfError = null
        // The rows are one date's answer, so a new date drops them: a chip must
        // never show the previous date's facts under its own heading (AND-1).
        // The epoch remembered with the rows is the other half of the same rule
        // - [Entities.asOfFactsFor] draws them only for the date they belong to.
        asOfFacts = null
        asOfFactsEpoch = null
    }

    Section(Entities.TITLE, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            Text(Entities.UNDER, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
            Gap(6)
            // The owner's phone Galaxy: the PICTURE (2026-10-26) over the
            // "at a glance" band (2026-10-23), both above the list. Both are
            // hidden while the list shows a past date, because then the counts
            // on screen are that date's, not today's - and the picture is a
            // view of those same counts. Neither reads anything new: the names
            // are the read above, and the connections are worked out from it.
            val band = entities
            if (asOfEpoch == null && !band.isNullOrEmpty()) {
                Kicker(Entities.GALAXY_TITLE)
                Gap(2)
                GalaxyPicture(band, onOpen = {
                    openedFromPicture = true
                    openId = it
                })
                Gap(8)
                GalaxyBand(band)
                Gap(8)
            }
            TextInput(search, { search = it }, placeholder = Entities.SEARCH)
            Gap(2)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Entities.filterLabels(entities.orEmpty()).forEach { label ->
                    val on = kind == label
                    Quiet(
                        (if (on) "• " else "") + label,
                        color = if (on) chrome.textHi else chrome.textMid,
                        modifier = Modifier.semantics {
                            contentDescription = "Kind filter: $label" + if (on) ", chosen" else ""
                        },
                        onClick = { kind = label },
                    )
                }
            }
            Gap(2)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                AsOfChip(Entities.NOW, asOfWhich == "", { pickAsOf(null, "") })
                AsOfChip(Entities.WEEK, asOfWhich == Entities.WEEK, {
                    pickAsOf(System.currentTimeMillis() / 1000L - 7L * 86_400L, Entities.WEEK)
                })
                AsOfChip(Entities.MONTH, asOfWhich == Entities.MONTH, {
                    pickAsOf(System.currentTimeMillis() / 1000L - 30L * 86_400L, Entities.MONTH)
                })
                AsOfChip(Entities.PICK_DATE, asOfWhich == Entities.PICK_DATE, {
                    dateText = asOfLabel
                    dateBad = false
                    dateOpen = true
                })
            }
            val asOfDate = asOfLabel
            if (asOfEpoch != null && asOfDate.isNotEmpty()) {
                Gap(2)
                Text(Entities.asOfLine(asOfDate), style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo)
            }
            if (asOfBusy) {
                Gap(2)
                Text(Entities.AS_OF_READING, style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo, modifier = Modifier.liveStatus())
            }
            asOfError?.let {
                Gap(2)
                Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
            }
            Gap(6)
            val all = entities
            val err = readError
            val asOf = asOfEpoch != null
            // Only the rows read for THIS date are drawn, so the heading and
            // the list below it can never describe two different dates (AND-1).
            val facts = Entities.asOfFactsFor(asOfEpoch, asOfFacts, asOfFactsEpoch)
            val open = all?.firstOrNull { it.id == openId }
            // The chip and the search narrow the list; the as-of chips narrow
            // each name's OWN fact ids to the ones active then (the PC's
            // `current` as of that moment), so the grouped counts below are the
            // counts on that date. `shown` is exactly what the list draws.
            val shown = if (asOf) {
                if (facts == null) emptyList() else Entities.asOfEntities(all.orEmpty(), facts)
            } else {
                Entities.visible(all.orEmpty(), kind, search)
            }
            val perFact = remember(all) { Entities.namesPerFact(all.orEmpty()) }
            val asOfPerFact = remember(shown, asOf) {
                if (asOf) Entities.namesPerFact(shown) else perFact
            }
            val shares = remember(shown, asOf) {
                if (asOf) emptyMap<String, Int>() else Entities.sharedPartners(shown)
            }
            when {
                missing -> Text(Entities.MISSING, style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid)
                all == null -> Text(
                    if (err != null) "Couldn't read the list: $err" else "Reading…",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (err != null) chrome.warnInk else chrome.textLo,
                )
                open != null -> {
                    Quiet(Entities.BACK, color = chrome.textMid, onClick = {
                        openedFromPicture = false
                        openId = null
                    })
                    if (asOf) {
                        val asOfOpen = shown.firstOrNull { it.id == open.id }
                        if (asOfOpen == null) {
                            Text(Entities.asOfNone(asOfDate), style = MaterialTheme.typography.bodySmall,
                                color = chrome.textMid)
                        } else {
                            EntityFacts(
                                entity = asOfOpen,
                                all = shown,
                                perFact = asOfPerFact,
                                asOfRows = Entities.asOfRows(open, facts.orEmpty()),
                                asOfDate = asOfDate,
                            )
                        }
                    } else {
                        // A dot promised "shares facts with N names" when it was
                        // tapped; keep that promise by reading the connections
                        // over every name, not over the filtered list (a list
                        // row opens against what the list is showing, as it
                        // always did).
                        EntityFacts(open, if (openedFromPicture) all.orEmpty() else shown, perFact)
                    }
                }
                else -> {
                    if (err != null && !asOf) {
                        Text("Couldn't read it again: $err", style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                    if (shown.isEmpty() && all.isEmpty()) {
                        Text(Entities.EMPTY, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                    } else if (shown.isEmpty()) {
                        Text(
                            if (asOf) Entities.asOfNone(asOfDate) else Entities.NO_MATCH,
                            style = MaterialTheme.typography.bodySmall, color = chrome.textMid,
                        )
                    }
                    Entities.groups(shown).forEach { group ->
                        Gap(10)
                        Kicker(group.title)
                        group.entities.forEach { e ->
                            Quiet(
                                if (asOf) Entities.asOfRowLine(e, asOfDate) else Entities.rowLine(e),
                                color = chrome.textHi,
                                onClick = {
                                    openedFromPicture = false
                                    openId = e.id
                                },
                            )
                            if (!asOf) {
                                Entities.sharesLine(shares[e.id] ?: 0)?.let {
                                    Text(it, style = MaterialTheme.typography.labelSmall,
                                        color = chrome.textLo)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (dateOpen) {
        AlertDialog(
            onDismissRequest = { dateOpen = false },
            title = { Text(Entities.PICK_DATE) },
            text = {
                Column {
                    TextInput(dateText, { dateText = it; dateBad = false },
                        placeholder = Entities.DATE_HINT)
                    if (dateBad) {
                        Gap(4)
                        Text(Entities.DATE_BAD, style = MaterialTheme.typography.labelSmall,
                            color = chrome.warnInk)
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val epoch = MemoryDates.knownAt(dateText, ZoneId.systemDefault(), LocalDate.now())
                    if (epoch == null) {
                        dateBad = true
                    } else {
                        pickAsOf(epoch, Entities.PICK_DATE)
                        dateOpen = false
                    }
                }) { Text(Entities.USE_DATE) }
            },
            dismissButton = {
                TextButton(onClick = { dateOpen = false }) { Text(Entities.CANCEL) }
            },
        )
    }
}

/** One as-of chip: a Quiet with the same "• " and TalkBack "chosen" rule the
 * kind chips and History's tag chips use. Read-only: it asks for a date. */
@Composable
private fun AsOfChip(label: String, on: Boolean, onClick: () -> Unit) {
    val chrome = LocalChrome.current
    Quiet(
        (if (on) "• " else "") + label,
        color = if (on) chrome.textHi else chrome.textMid,
        modifier = Modifier.semantics {
            contentDescription = "Facts as of: $label" + if (on) ", chosen" else ""
        },
        onClick = onClick,
    )
}

/**
 * "Galaxy at a glance" - the band under the picture (owner, 2026-10-23). The
 * picture above it is [GalaxyPicture] (owner, 2026-10-26); this band keeps what
 * a picture cannot say in a line: the counts in words and the best-connected
 * names, as labels.
 *
 * It is NOT a control: the names are [Pill]s, whose own docstring says what
 * that shape means - "this is a label, not a control". They are not tappable,
 * so TalkBack does not announce "button" over things that do nothing - the
 * same rule the connections list below already follows. The row is spoken as
 * one line: "Priya, 4 facts, shares facts with 2 names".
 *
 * It adds NO read: [Entities.mostConnected] and [Entities.totalFacts] work on
 * the list the plate has already fetched, using the same shared-facts rule the
 * list rows use. No animation, no GL/AGSL, no write, no route.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GalaxyBand(entities: List<Entities.Entity>) {
    val chrome = LocalChrome.current
    val partners = remember(entities) { Entities.sharedPartners(entities) }
    val connected = remember(entities) { Entities.mostConnected(entities) }
    Text(
        Entities.galaxySummary(entities.size, Entities.totalFacts(entities)),
        style = MaterialTheme.typography.labelLarge,
        color = chrome.textMid,
    )
    if (connected.isNotEmpty()) {
        Gap(6)
        Text(Entities.GALAXY_TOP, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        Gap(4)
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            connected.forEach { e ->
                val shared = partners[e.id] ?: 0
                Pill(
                    Entities.rowLine(e),
                    modifier = Modifier.semantics {
                        contentDescription = Entities.galaxyNameLine(e, shared)
                    },
                )
            }
        }
    }
}

/**
 * The facts behind one name: the first 20 ids read on arrival, "Show 20 more"
 * for the next 20. An erased fact says [Entities.ERASED] and keeps its date; a
 * forgotten one is marked and sorted after the current ones; a fact hidden by
 * an Off topic is not shown, only counted.
 *
 * Above the facts, "Shares facts with" lists the other names those facts
 * mention - the Galaxy's connections, in words ([Entities.connections]). It is
 * worked out from [all] - the same list of names already on screen - so it
 * costs no read of its own and is right even when the facts below fail to
 * load. [perFact] is the count of names per fact, built once per screen rather
 * than once per name. Read-only, like the rest of this screen.
 */
@Composable
private fun EntityFacts(
    entity: Entities.Entity,
    all: List<Entities.Entity>,
    perFact: Map<Long, Int>,
    /** A1: when the list is showing a past date, the facts that were active
     * then come from the as-of read already in hand (no second route), and the
     * retired ones are drawn muted under [Entities.RETIRED]. Null is "now",
     * where the existing paged [MemoryUsed] read is used exactly as before. */
    asOfRows: Entities.AsOfRows? = null,
    asOfDate: String? = null,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var rows by remember(entity.id, asOfRows) {
        mutableStateOf(asOfRows?.active ?: emptyList())
    }
    var consumed by remember(entity.id, asOfRows) {
        mutableIntStateOf(asOfRows?.active?.size ?: 0)
    }
    var hiddenByTopic by remember(entity.id) { mutableIntStateOf(0) }
    var loading by remember(entity.id) { mutableStateOf(false) }
    var failed by remember(entity.id) { mutableStateOf<String?>(null) }
    var attempt by remember(entity.id) { mutableIntStateOf(0) }
    var dossier by remember(entity.id) { mutableStateOf<PeopleDossier.Read?>(null) }

    // LM-4: one person's read-only dossier, read only for a PERSON and only
    // while this plate is on screen (the whole plate is replaced by
    // HiddenSection while the memory lists are hidden, so this can never be
    // reached with them hidden).
    LaunchedEffect(entity.id) {
        if (entity.kind == "person") dossier = JarvisRuntime.peopleDossier(entity.name)
    }

    suspend fun loadNext() {
        val ids = Entities.pageIds(entity, consumed)
        if (ids.isEmpty()) return
        loading = true
        failed = null
        try {
            when (val r = JarvisRuntime.memoryUsed(ids)) {
                is MemoryUsed.Read.Shown -> {
                    val page = Entities.page(r.view)
                    rows = Entities.arrange(rows + page.rows)
                    hiddenByTopic += page.hiddenByTopic
                    consumed += ids.size
                }
                MemoryUsed.Read.Missing -> failed = MemoryUsed.MISSING
                is MemoryUsed.Read.Failed -> failed = Entities.FAILED
            }
        } finally {
            loading = false
        }
    }

    LaunchedEffect(entity.id, attempt, asOfRows) {
        if (asOfRows == null && consumed == 0) loadNext()
    }

    Gap(6)
    Text(entity.name, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
    Text(Entities.heading(entity.count), style = MaterialTheme.typography.labelLarge, color = chrome.textMid)

    if (entity.kind == "person") {
        Gap(8)
        Kicker(PeopleDossier.TITLE)
        val read = dossier
        Text(
            when (read) {
                null -> PeopleDossier.READING
                is PeopleDossier.Read.Shown -> read.body
                PeopleDossier.Read.Missing -> PeopleDossier.MISSING
                is PeopleDossier.Read.Failed -> read.why
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (read is PeopleDossier.Read.Failed) chrome.warnInk else chrome.textHi,
        )
        Gap(10)
        Rule()
    }

    // The Galaxy's connections, in words. Worked out from the names already
    // read, so this is the one part of the panel that is always right - it
    // says the same thing whether or not the facts below could be read.
    //
    // Plain text, deliberately, not the `Quiet` this file uses for the rows in
    // the list: a connection is something to read, not a control. `Quiet`
    // carries a 48dp touch target and a button's own announcement, so a column
    // of them would tell TalkBack "button" nine times about nine things that do
    // nothing when tapped. Nothing here is tappable, which is the read-only
    // decision showing up in the accessibility tree as well as in the code.
    val links = Entities.connections(entity, all, perFact)
    Gap(10)
    Kicker(Entities.WITH)
    if (links.isEmpty()) {
        Gap(4)
        Text(Entities.ALONE, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        Text(Entities.ALONE_WHY, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    } else {
        links.forEach { c ->
            Text(
                Entities.connectionLine(c),
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi,
                modifier = Modifier.padding(vertical = 2.dp),
            )
        }
    }
    Gap(12)
    Rule()

    val err = failed
    when {
        err != null -> {
            Gap(6)
            Text(err, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
            Quiet(Entities.RETRY, enabled = !loading, onClick = {
                if (consumed == 0) attempt += 1 else scope.launch { loadNext() }
            })
        }
        loading && rows.isEmpty() -> {
            Gap(6)
            Text(Entities.READING, style = MaterialTheme.typography.bodySmall, color = chrome.textLo,
                modifier = Modifier.liveStatus())
        }
        consumed > 0 && rows.isEmpty() && !Entities.hasMore(entity, consumed) -> {
            Gap(6)
            Text(Entities.NO_FACTS, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }
    rows.forEach { row ->
        Gap(8)
        Column(Modifier.fillMaxWidth()) {
            Text(
                if (row.erased) Entities.ERASED else row.text,
                style = MaterialTheme.typography.bodyMedium,
                color = if (row.forgotten || row.erased) chrome.textLo else chrome.textHi,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                row.saved?.let {
                    Text("Saved $it", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
                }
                if (row.pinned) Pill(Entities.PINNED)
                if (row.forgotten) Pill(Entities.FORGOTTEN)
            }
        }
    }
    val retiredRows = asOfRows?.retired.orEmpty()
    if (retiredRows.isNotEmpty()) {
        Gap(10)
        Kicker(Entities.RETIRED)
        if (!asOfDate.isNullOrEmpty()) {
            Text(Entities.asOfLine(asOfDate), style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo)
        }
        retiredRows.forEach { row ->
            Gap(6)
            Text(
                if (row.erased) Entities.ERASED else row.text,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textLo,
            )
        }
    }
    Entities.topicsHiddenLine(hiddenByTopic)?.let {
        Gap(8)
        Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    if (consumed > 0) {
        Gap(8)
        Text(
            Entities.showingLine(consumed, entity.count),
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
            modifier = Modifier.liveStatus(),
        )
        if (Entities.hasMore(entity, consumed)) {
            Quiet(Entities.MORE, enabled = !loading, onClick = { scope.launch { loadNext() } })
        }
    }
}
