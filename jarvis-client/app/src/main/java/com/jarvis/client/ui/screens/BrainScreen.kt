package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.BrainSnapshot
import com.jarvis.client.LinkState
import com.jarvis.client.ModelRequest
import com.jarvis.client.SectionRead
import com.jarvis.client.net.Attention
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.ModelsInfo
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.net.VersionInfo
import com.jarvis.client.ui.parts.Affirm
import com.jarvis.client.ui.parts.Field
import com.jarvis.client.ui.parts.Freshness
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Meter
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Refuse
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.ageText
import com.jarvis.client.ui.parts.rememberTickingNow
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * State of Mind — what Jarvis is doing, thinking with, and holding.
 *
 * Deliberately a status board rather than an animated node graph, and that is a
 * measurement rather than a preference: there is no 60fps content in this data.
 * The active model changes every few seconds, the routing lane changes per
 * request, VRAM samples arrive around 1 Hz, and memory facts and jobs are
 * event-driven. Animating it at the display rate would spend the frame budget
 * interpolating nothing — and twenty node labels re-measured per frame costs an
 * estimated 3–12ms, more than everything else on screen combined.
 *
 * The live feeling comes from latency and from one or two things in motion: a
 * number that changes within 200ms of the event, and a needle that glides to
 * it. It does not come from a simulation. A graph that re-lays-out on every
 * glance also makes the data harder to read, because a fact you have to re-find
 * is worse than a row that stays put.
 *
 * The face is parked while this is open — two animated canvases on a mid-range
 * GPU is exactly where the budget goes.
 */
@Composable
fun BrainScreen(
    link: LinkState,
    stale: Boolean,
    activity: Activity,
    power: String,
    status: StatusInfo?,
    version: VersionInfo?,
    attention: Attention,
    jobs: List<JobRecord>,
    brain: BrainSnapshot,
    onRefresh: () -> Unit,
    onBack: () -> Unit,
    /** Which proposal, if any, has a decision in flight - never two at once. */
    memoryDecideBusyId: Long?,
    onDecideMemory: (id: Long, accept: Boolean) -> Unit,
    /**
     * The daily "tidy memory overnight?" card, or null to show none.
     *
     * Passed in already decided rather than read fresh from `brain.memory`
     * every recomposition: the server marks itself as having offered the
     * moment `/api/memory/pending` is polled at all, not when the owner
     * acts on it, so a second read - which any OTHER write on this screen
     * triggers via its own refresh - comes back with the offer already
     * gone. The caller holds the sticky, once-seen copy; this composable
     * only ever renders what it is handed.
     */
    sleepOffer: JsonObject? = null,
    sleepOfferBusy: Boolean = false,
    onSleepTimeAction: (enabled: Boolean?, remind: Boolean?) -> Unit = { _, _ -> },
    onDismissSleepOffer: () -> Unit = {},
    /** What a Keep/Discard send failed with, e.g. not connected. Null hides it. */
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    /**
     * The model list, or null on a backend without the `models` capability -
     * in which case the section is not drawn at all, per §2's rule that a
     * capability reporting false means hide the UI for it.
     */
    models: ModelsInfo? = null,
    /** True while a switch, rollback or install is in flight, so none can double-send. */
    modelBusy: Boolean = false,
    onSwitchModel: (ref: String) -> Unit = {},
    onRollbackModel: () -> Unit = {},
    /**
     * Asks the desktop to download [ref]. CLAUDE.md's 2026-09-20 amendment -
     * before that, this screen had no way to reach `/api/models/install` at
     * all, on purpose.
     */
    onInstallModel: (ref: String) -> Unit = {},
    /**
     * "What did I believe on this date?" - `GET /api/memory/facts?known_at=`,
     * the route named in the desktop's 2026-09-18 feature audit. Read-only
     * and optional: null result with `memoryAsOfBusy` false just means
     * nothing has been asked for yet.
     */
    memoryAsOf: JsonObject? = null,
    memoryAsOfBusy: Boolean = false,
    onQueryMemoryAsOf: (epochSeconds: Long) -> Unit = {},
    modifier: Modifier = Modifier,
    /**
     * Opens Home with the approval card a model switch or install raised -
     * the id when it is known, null to open Home without scrolling to one.
     * Only ever navigates: nothing is approved from this screen. Null (the
     * default) draws the "waiting for your approval" line without the link,
     * rather than a link that does nothing.
     */
    onOpenApprovals: ((cardId: String?) -> Unit)? = null,
    /**
     * Re-read the board every this many milliseconds while the screen is
     * open and the link is up. 0, the default, is off - the battery reasoning
     * in [com.jarvis.client.JarvisRuntime.refreshBrain] still holds, and the
     * age on the freshness line is always shown either way.
     */
    autoRefreshMs: Long = 0L,
) {
    val chrome = LocalChrome.current
    // The same test ModelsPlate always had, now shared by every control on this
    // screen that writes anything. The runtime refuses these again on the way
    // out (decideMemory, setSleepTime); this is the visible half of rule 4,
    // and it was missing from Keep/Discard and the sleep offer - the only
    // buttons on this screen that looked live on a dead link.
    val canAct = link == LinkState.CONNECTED && !stale
    // Retry is a READ, so it is not gated on the link the way acting is. Null
    // while a read is already out: the button then says "Retrying…" rather
    // than stacking a second read on the first.
    val retry = if (brain.refreshing) null else onRefresh

    if (autoRefreshMs > 0L && link == LinkState.CONNECTED) {
        val refreshNow by rememberUpdatedState(onRefresh)
        val busyNow by rememberUpdatedState(brain.refreshing)
        LaunchedEffect(autoRefreshMs) {
            while (true) {
                delay(autoRefreshMs)
                if (!busyNow) refreshNow()
            }
        }
    }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("State of mind", onBack) {
            Quiet(
                if (brain.refreshing) "Refreshing…" else "Refresh",
                enabled = !brain.refreshing,
                onClick = onRefresh,
            )
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // 1. The rush latch, first, because it changes how everything below
            // should be read. Outside text that tried to raise the tier is the
            // one thing on this screen that is adversarial by construction.
            //
            // It must never simply vanish. It used to be drawn only when the
            // last read found one, so a read that timed out drew nothing at
            // all - under a line that said "Live." - which says "nothing is
            // raising the tier" when the phone does not know. A failed check
            // now keeps the last latch it saw, with its age, and says in
            // amber that it could not check.
            val rush = rushOf(brain.contentRisk)
            val riskFailed = brain.contentRiskRead as? SectionRead.Failed
            if (rush != null || riskFailed != null) {
                item(key = "rush") {
                    Column(Modifier.fillMaxWidth()) {
                        if (rush != null) {
                            RushBanner(
                                rush,
                                // Aged only when it might be out of date. A
                                // latch from a read that just worked is now.
                                lastSeenAtMs = if (riskFailed != null) brain.contentRiskAtMs else null,
                            )
                        }
                        if (riskFailed != null) {
                            if (rush != null) Gap(8)
                            RushCheckFailed(
                                reason = riskFailed.reason,
                                lastCheckedAtMs = brain.contentRiskAtMs,
                                sawLatch = rush != null,
                                onRetry = retry,
                            )
                        }
                    }
                }
            }

            // 2. Whether any of this can be trusted at all. A stale board is
            // worse than no board: every number below is last-known, and on a
            // screen full of numbers that distinction has to lead.
            item(key = "freshness") {
                Freshness(
                    link,
                    stale,
                    brain.fetchedAtMs,
                    readWhat = "Board",
                    refreshing = brain.refreshing,
                )
            }

            if (notice != null) {
                item(key = "notice") { Notice(notice, onDismissNotice) }
            }

            item(key = "doing") {
                Section("Doing") {
                    Plate {
                        Field("Activity", activity.name.lowercase().replaceFirstChar { it.uppercase() })
                        Field("Power", power.replaceFirstChar { it.uppercase() })
                        val lane = status?.lane?.lowercase()
                        Field(
                            "Route",
                            when (lane) {
                                "cloud" -> "Cloud — this is leaving your machine"
                                "local" -> "Local"
                                "offline" -> "Offline"
                                null -> "Not reported"
                                else -> lane
                            },
                            valueColor = when (lane) {
                                "cloud" -> chrome.cloudInk
                                "local" -> chrome.okInk
                                "offline" -> chrome.badInk
                                else -> null
                            },
                        )
                        status?.model?.let { Field("Model", it, machine = true) }
                        if (status?.held == true) {
                            Gap(4)
                            Text(
                                "Something is held — a message inside its send window.",
                                style = MaterialTheme.typography.bodySmall,
                                color = chrome.warnInk,
                            )
                        }
                    }
                }
            }

            if (models != null) {
                item(key = "models") {
                    Section("Model") {
                        ModelsPlate(
                            models = models,
                            busy = modelBusy,
                            canAct = canAct,
                            onSwitch = onSwitchModel,
                            onRollback = onRollbackModel,
                            onInstall = onInstallModel,
                            request = brain.modelRequest,
                            onOpenApprovals = onOpenApprovals,
                        )
                    }
                }
            }

            item(key = "attention") {
                Section("Attention budget") { AttentionPlate(attention) }
            }

            if (jobs.isNotEmpty()) {
                item(key = "jobs") {
                    Section("Background work") {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            jobs.forEach { JobPlate(it) }
                        }
                    }
                }
            }

            // 4. The endpoints whose shape the contract does not fix. Rendered
            // from whatever actually came back — see JarvisApi.probe.
            item(key = "compute") {
                Probed("Compute", brain.compute, "GPU and VRAM plan", brain.computeRead, retry)
            }
            item(key = "memory") {
                // The QUEUE, not the corpus. /api/graph is desktop-only by the
                // contract's own instruction, and a memory graph is not a thing
                // to read on a phone; what belongs here is the short list of
                // facts waiting for a yes or no - and, unlike every other
                // Probed section, this one actually answers them, the same
                // one-at-a-time way the desktop's own Memory tab does.
                MemoryQueue(
                    data = brain.memory,
                    read = brain.memoryRead,
                    onRetry = retry,
                    canAct = canAct,
                    busyId = memoryDecideBusyId,
                    onKeep = { id -> onDecideMemory(id, true) },
                    onDiscard = { id -> onDecideMemory(id, false) },
                    sleepOffer = sleepOffer,
                    sleepOfferBusy = sleepOfferBusy,
                    onSleepTimeAction = onSleepTimeAction,
                    onDismissSleepOffer = onDismissSleepOffer,
                )
            }
            item(key = "memory-as-of") {
                Section("What did I believe on this date?") {
                    MemoryAsOfPlate(
                        busy = memoryAsOfBusy,
                        result = memoryAsOf,
                        onQuery = onQueryMemoryAsOf,
                    )
                }
            }
            item(key = "initiative") {
                Probed(
                    "Findings",
                    brain.initiative,
                    "What Jarvis noticed on its own",
                    brain.initiativeRead,
                    retry,
                )
            }
            item(key = "ledger") {
                Probed(
                    "Audit chain",
                    brain.ledger,
                    "Entry count and last verified point",
                    brain.ledgerRead,
                    retry,
                )
            }
            item(key = "skills") {
                Probed("Skills", brain.skills, "Installed, with scan verdicts", brain.skillsRead, retry)
            }

            item(key = "capabilities") {
                // Sorted once per handshake, not once per event. `version` holds a
                // JsonObject, which Compose treats as an unstable type, so this whole
                // screen re-runs on EVERY server event rather than being skipped — and
                // this block was doing a full sort of the capability key set plus two
                // passes of `can()` over it each time, for a list that only changes when
                // the backend is re-handshaked. Keyed on `capabilities` itself (not on
                // `version`) because that object is the only input `can()` reads; a
                // version number that moved without the capability set changing produces
                // an identical list, so re-deriving it would be pure waste.
                val caps: Pair<List<String>, List<String>> = remember(version?.capabilities) {
                    val v = version
                    if (v == null) {
                        emptyList<String>() to emptyList<String>()
                    } else {
                        val names = v.capabilities.keys.sorted()
                        names.filter { v.can(it) } to names.filterNot { v.can(it) }
                    }
                }
                Section("This backend") {
                    Plate {
                        if (version == null) {
                            Text(
                                "No handshake yet.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = chrome.textMid,
                            )
                        } else {
                            version.server.takeIf { it.isNotBlank() }
                                ?.let { Field("Server", it, machine = true) }
                            Field("API", version.api.toString(), machine = true)
                            Gap(6)
                            Kicker("Capabilities", Modifier.semantics { heading() })
                            Gap(6)
                            // Branch on capabilities, never on version numbers —
                            // and show the user the same list the app branches
                            // on, so "why is that button missing" has an answer
                            // here. `can()` is the same call the app makes.
                            val (on, off) = caps
                            if (on.isEmpty()) {
                                Text(
                                    "None reported.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = chrome.textMid,
                                )
                            } else {
                                FlowChips(on)
                            }
                            if (off.isNotEmpty()) {
                                Gap(10)
                                Kicker("Not on this backend", Modifier.semantics { heading() })
                                Gap(6)
                                FlowChips(off, muted = true)
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
 * @param lastSeenAtMs when this latch was last read, shown as an age. Null
 *   when the read that found it is the latest one, so there is nothing to age.
 */
@Composable
private fun RushBanner(rush: JsonObject, lastSeenAtMs: Long? = null) {
    val chrome = LocalChrome.current
    val text = rush.str("text")
        ?: "Outside text raised the current tier."
    Plate(
        tone = chrome.badInk.copy(alpha = 0.10f),
        outline = chrome.badInk.copy(alpha = 0.40f),
    ) {
        Kicker("Tier raised", Modifier.semantics { heading() }, color = chrome.badInk)
        if (lastSeenAtMs != null && lastSeenAtMs > 0L) {
            Gap(2)
            val now = rememberTickingNow(lastSeenAtMs)
            Text(
                "Last seen ${ageText(now - lastSeenAtMs)}. It may have cleared since.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
        }
        Gap(6)
        Text(text, style = MaterialTheme.typography.bodyLarge, color = chrome.badInk)
        rush.str("quote")?.let {
            Gap(8)
            // Quoted, because it is a quote — and never rendered as if Jarvis
            // said it.
            Text("“$it”", style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        }
        rush.str("source")?.let {
            Gap(4)
            // Named, never quoted. A source string is attacker-controlled.
            Text("from $it", style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        Gap(8)
        Text(
            "Nothing is approved from here. A latch is cleared where the scanner runs.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
    }
}

/**
 * The rush-latch check did not come back. Amber, not red: this is "the phone
 * does not know", not "something is wrong" - but it is drawn every time, in
 * words, because the alternative was drawing nothing, and nothing reads as
 * "no latch".
 *
 * No control here touches the latch. Retry re-reads; it clears nothing.
 */
@Composable
private fun RushCheckFailed(
    reason: String,
    lastCheckedAtMs: Long,
    sawLatch: Boolean,
    onRetry: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Kicker("Could not check for a rush latch", Modifier.semantics { heading() }, color = chrome.warnInk)
        Gap(6)
        Text(reason, style = MaterialTheme.typography.bodyMedium, color = chrome.warnInk)
        Gap(6)
        val now = if (lastCheckedAtMs > 0L) rememberTickingNow(lastCheckedAtMs) else 0L
        Text(
            when {
                sawLatch -> "The latch above is the last one seen. It may still be set."
                lastCheckedAtMs > 0L ->
                    "The last check that worked, ${ageText(now - lastCheckedAtMs)}, found " +
                        "none. One may have been set since."
                else ->
                    "It has not been checked since the app opened, so the phone does not " +
                        "know whether one is set."
            },
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        RetryButton(onRetry)
    }
}

/** Re-reads the board. Null [onRetry] means a read is already out. */
@Composable
private fun RetryButton(onRetry: (() -> Unit)?) {
    Quiet(
        if (onRetry == null) "Retrying…" else "Retry",
        enabled = onRetry != null,
        onClick = { onRetry?.invoke() },
    )
}

/**
 * The installed models, with a switch and an install that both ASK.
 *
 * The owner's 2026-09-18 amendment to the standing rules allowed changing the
 * local model from the phone; the 2026-09-20 one allowed installing a model
 * by typing its name. The catalogue is still not allowed - the list is
 * whatever the desktop already holds, and there is nothing to browse for
 * what could be installed. `Use` and `Install` each raise an approval card
 * (tier `ask` on the server) on Home, so the change is decided the same way
 * every other change is, and nothing downloads or switches until it is
 * approved. `Roll back` is tier `auto` and never waits, because returning to
 * the previous model is the safe direction.
 *
 * After an ask, the plate says the card is waiting and where, with a link to
 * it when the caller supplies one. The link only opens Home; it approves
 * nothing.
 *
 * The cost is said on the plate rather than discovered: a swap unloads one
 * model and loads another, which the desktop's own topology doc measures at
 * six to ten seconds of silence. That is a scene change, not a route - fine
 * once per mode, wrong per request.
 */
@Composable
private fun ModelsPlate(
    models: ModelsInfo,
    busy: Boolean,
    canAct: Boolean,
    onSwitch: (String) -> Unit,
    onRollback: () -> Unit,
    onInstall: (String) -> Unit,
    request: ModelRequest?,
    onOpenApprovals: ((cardId: String?) -> Unit)?,
) {
    val chrome = LocalChrome.current
    var installRef by rememberSaveable { mutableStateOf("") }
    val current = models.currentRef
    val entries = models.entries
    Plate {
        if (request != null) {
            ApprovalWaiting(request, onOpenApprovals)
            Gap(12)
        }
        // Is the model actually ON the graphics card? Nothing else on the
        // phone says, and the only symptom of a spill is that everything got
        // slow - which reads as "Jarvis is slow", not "the model is on the CPU".
        val off = models.offload
        if (off != null && off.bad) {
            Text(
                off.note ?: "The model is not on the graphics card, so replies are slow.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
            )
            Gap(10)
        }
        if (entries.isEmpty()) {
            Text(
                "No models reported.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
        } else {
            entries.forEachIndexed { i, entry ->
                if (i > 0) Rule()
                val isCurrent = entry.ref == current
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            entry.ref,
                            style = com.jarvis.client.ui.theme.JarvisType.machine,
                            color = chrome.textHi,
                        )
                        val meta = listOfNotNull(
                            entry.family,
                            entry.sizeBytes?.let { bytes(it) },
                            if (entry.ref == models.previous && !isCurrent) "the previous model" else null,
                        )
                        if (meta.isNotEmpty()) {
                            Gap(2)
                            Text(
                                meta.joinToString(" · "),
                                style = MaterialTheme.typography.labelSmall,
                                color = chrome.textLo,
                            )
                        }
                    }
                    Spacer(Modifier.width(8.dp))
                    if (isCurrent) {
                        Pill("Active", color = chrome.okInk)
                    } else {
                        Quiet(
                            if (busy) "…" else "Use",
                            enabled = !busy && canAct,
                            onClick = { onSwitch(entry.ref) },
                        )
                    }
                }
            }
            val previous = models.previous?.takeIf { it.isNotBlank() && it != current }
            if (previous != null) {
                Gap(6)
                Quiet(
                    if (busy) "…" else "Roll back to $previous",
                    color = chrome.textMid,
                    enabled = !busy && canAct,
                    onClick = onRollback,
                )
            }
        }
        Gap(8)
        Text(
            "Use asks the desktop and raises a card on Home to approve, like any " +
                "other change. A switch takes six to ten seconds while one model " +
                "unloads and the next loads - fine once, not per question.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        Gap(12)
        Rule()
        Gap(10)
        Text(
            "Install a model the desktop does not have yet. Same rule as Use: this " +
                "only asks - approving it is a separate step, and a download runs for " +
                "minutes rather than seconds, so it is worth approving from the desktop " +
                "where you can watch it. Type the name the way you would give it to " +
                "Ollama, e.g. llama3.1:8b.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textLo,
        )
        Gap(10)
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextInput(
                value = installRef,
                onValueChange = { installRef = it },
                placeholder = "model:tag",
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet(
                if (busy) "…" else "Install",
                enabled = !busy && canAct && installRef.isNotBlank(),
                onClick = {
                    onInstall(installRef)
                    installRef = ""
                },
            )
        }
    }
}

/**
 * "Waiting for your approval", after Use or Install.
 *
 * Use used to show "…" for a moment and then nothing, and Install set a
 * notice that said "approve it" without saying where. The card is on Home,
 * not on this screen, so this says so, and offers the way there.
 */
@Composable
private fun ApprovalWaiting(request: ModelRequest, onOpenApprovals: ((cardId: String?) -> Unit)?) {
    val chrome = LocalChrome.current
    Text(
        "Waiting for your approval",
        style = MaterialTheme.typography.titleSmall,
        color = chrome.warnInk,
    )
    Gap(2)
    Text(
        if (request.install) {
            "Installing ${request.ref} is waiting on a card on Home. Nothing " +
                "downloads until you approve it there."
        } else {
            "Switching to ${request.ref} is waiting on a card on Home. Nothing " +
                "changes until you approve it there."
        },
        style = MaterialTheme.typography.bodySmall,
        color = chrome.textMid,
    )
    if (onOpenApprovals != null) {
        Quiet(
            "Open the card →",
            color = chrome.warnInk,
            onClick = { onOpenApprovals(request.cardId) },
        )
    }
}

/** 4.7 GB, 812 MB. Enough precision for a list; a byte count is noise. */
private fun bytes(n: Long): String = when {
    n >= 1_000_000_000L -> "%.1f GB".format(n / 1_000_000_000.0)
    n >= 1_000_000L -> "%.0f MB".format(n / 1_000_000.0)
    else -> "$n B"
}

@Composable
private fun AttentionPlate(attention: Attention) {
    val chrome = LocalChrome.current
    Plate {
        val limit = attention.limit
        if (limit > 0) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "${attention.remaining} of $limit spoken interruptions left today",
                    style = MaterialTheme.typography.bodyLarge,
                    color = chrome.textHi,
                    modifier = Modifier.weight(1f),
                )
            }
            Gap(8)
            Meter(
                fraction = attention.remaining.toFloat() / limit,
                color = if (attention.remaining == 0) chrome.warnMark else chrome.okMark,
            )
        } else {
            Text(
                "No interruption budget reported.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
        }
        if (attention.muted || attention.blockedBy != null) {
            Gap(10)
            Row {
                if (attention.muted) Pill("Muted until tomorrow", color = chrome.warnInk)
                attention.blockedBy?.let {
                    if (attention.muted) Spacer(Modifier.width(6.dp))
                    Pill("Blocked by $it", color = chrome.textMid)
                }
            }
        }
        if (attention.pending > 0) {
            Gap(10)
            Text(
                if (attention.pending == 1) {
                    "1 thing waiting to be told"
                } else {
                    "${attention.pending} things waiting to be told"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
        }
        if (attention.banked) {
            Gap(6)
            Text(
                // A fact, not a mood. The reactor says the same thing by going
                // still, and neither should imply something is wrong.
                "Banked: they are waiting for a better moment, not being ignored.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
}

@Composable
private fun JobPlate(job: JobRecord) {
    val chrome = LocalChrome.current
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                job.label.ifBlank { job.id },
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Pill(job.state.ifBlank { "running" })
        }
        job.progress?.let {
            Gap(10)
            Meter(it)
        }
        if (job.capabilities.isNotEmpty()) {
            Gap(10)
            // Frozen for the job's life. A job can never gain more while it
            // runs: approving something on Tuesday is not approving it on
            // Wednesday, and showing the frozen set is how that promise is
            // checkable rather than merely stated.
            Kicker("Approved with")
            Gap(6)
            FlowChips(job.capabilities)
        }
        if (job.private) {
            Gap(8)
            Text(
                "Private — the phone is not shown what this is working on.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        }
    }
}

/**
 * A read-only "what did the memory store believe was true on this date"
 * lookup - `docs/ANDROID-FEATURE-AUDIT.md` §4 P3, marked optional there. A
 * plain typed date, not a `DatePickerDialog`: the audit's own rule against
 * deep config UI on the phone argues just as well against importing a whole
 * calendar picker for one field that is asked for rarely.
 *
 * `YYYY-MM-DD` is parsed as LOCAL midnight, not `ZoneOffset.UTC` - this used
 * to read `atStartOfDay(ZoneOffset.UTC)`, on the reasoning that the query's
 * own name, "known at" a moment rather than a day, only needed A moment and
 * UTC was as good as any. It is not: the desktop's own `promptValidTo` in
 * `brain.js` hit this exact trap first and documents it in its own comment -
 * "A bare YYYY-MM-DD is parsed as local midnight, not Date.parse's UTC
 * midnight - west of Greenwich that shift lands the timestamp on the
 * previous calendar day". A UTC choice here is not neutral; it is wrong for
 * everyone west of Greenwich, in the specific direction of silently dropping
 * every fact learned on the typed date itself. Matching the desktop's own
 * fix - local midnight, not UTC, and not end-of-day either, which would
 * have been a second, different disagreement with the one working
 * precedent in this repo.
 */
@Composable
private fun MemoryAsOfPlate(
    busy: Boolean,
    result: JsonObject?,
    onQuery: (epochSeconds: Long) -> Unit,
) {
    val chrome = LocalChrome.current
    var text by rememberSaveable { mutableStateOf("") }
    val epochSeconds = remember(text) {
        runCatching {
            java.time.LocalDate.parse(text)
                .atStartOfDay(java.time.ZoneId.systemDefault())
                .toEpochSecond()
        }.getOrNull()
    }
    val rows = remember(result) { result?.let { flatten(it) }.orEmpty() }
    Plate {
        Text(
            "Read-only. Not the memory graph - one moment's worth of facts, " +
                "never a browsable one.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        Gap(10)
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextInput(
                value = text,
                onValueChange = { text = it },
                placeholder = "YYYY-MM-DD",
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet(
                if (busy) "…" else "Look up",
                enabled = !busy && epochSeconds != null,
                onClick = { epochSeconds?.let(onQuery) },
            )
        }
        if (text.isNotBlank() && epochSeconds == null) {
            Gap(6)
            Text("Use the form YYYY-MM-DD.", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        if (result != null) {
            Gap(12)
            Rule()
            Gap(10)
            if (rows.isEmpty()) {
                Text(
                    "Nothing on record for that date.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
            } else {
                rows.forEachIndexed { i, (label, value) ->
                    if (i > 0) Rule()
                    Field(label, value, machine = value.looksMachine())
                }
            }
        }
    }
}

/**
 * A section rendered from whatever the server sent.
 *
 * Scalars become rows, arrays become a count and their readable entries, and
 * anything nested one level deep is flattened with its parent's name. No field
 * is assumed to exist, so nothing here can be quietly wrong about a key.
 *
 * Four states, drawn four ways ([SectionRead]). This used to say "Not
 * available on this backend" whenever [data] was null - which was also true
 * before the first read came back and after a read that failed, so two times
 * out of three it blamed the desktop for something the phone did not know.
 */
@Composable
private fun Probed(
    title: String,
    data: JsonObject?,
    blurb: String,
    read: SectionRead,
    onRetry: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    // The expensive part of this composable, done once per payload instead of once
    // per recomposition. `flatten` walks the object and everything nested under it
    // (two levels), builds a growing list and re-`humanise`s every key — and five
    // of these sections are on screen at once. Because `BrainSnapshot` carries
    // JsonObject fields, Compose cannot mark this screen skippable, so before this
    // remember all five re-flattened on every single SSE event, which is the
    // steadiest source of them. Keyed on the JsonObject itself: JsonObject is a
    // Map, so `==` is a structural compare and a genuinely new payload — the only
    // thing that can change these rows — always misses the key and re-flattens.
    // Computed ABOVE the null branch on purpose, so the remember is never behind a
    // conditional return.
    val rows = remember(data) { data?.let { flatten(it) }.orEmpty() }
    Section(title) {
        Plate {
            if (data == null) {
                SectionUnread(read, blurb, onRetry)
                return@Plate
            }
            if (rows.isEmpty()) {
                Text(
                    "Nothing to report.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                return@Plate
            }
            rows.forEachIndexed { i, (label, value) ->
                if (i > 0) Rule()
                Field(label, value, machine = value.looksMachine())
            }
        }
    }
}

/**
 * What a section with no payload says, by why it has none: still reading,
 * not on this backend, or could not be read (with a Retry). Shared by
 * [Probed] and [MemoryQueue] so the three read the same on every section.
 */
@Composable
private fun SectionUnread(read: SectionRead, blurb: String, onRetry: (() -> Unit)?) {
    val chrome = LocalChrome.current
    when (read) {
        is SectionRead.Failed -> {
            Text(
                "Could not read this: ${read.reason}",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
            )
            Gap(4)
            Text(blurb, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
            RetryButton(onRetry)
        }
        SectionRead.Absent -> {
            Text(
                "Not on this backend.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
            Gap(4)
            Text(blurb, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        }
        // Read with no payload cannot happen - a read that answered carries
        // one - so it falls in with Reading rather than inventing a fifth line.
        SectionRead.Reading, SectionRead.Read -> {
            Text(
                "Reading…",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
            Gap(4)
            Text(blurb, style = MaterialTheme.typography.bodySmall, color = chrome.textLo)
        }
    }
}

/**
 * The one section on this screen that answers back rather than only
 * reporting. `data` is `/api/memory/pending`'s own JSON — the SAME payload
 * `JarvisRuntime.refreshBrain()` already fetched for the generic [Probed]
 * view this replaces — read directly rather than through a typed model, for
 * the reason [JarvisApi.probe] gives: the contract names this route with no
 * field list, and a data class would mean inventing keys.
 *
 * One fact, one decision, same as [com.jarvis.client.ui.approval.ApprovalCard]
 * - no "keep all" here either, and `busyId` exists so a second tap on the
 * same row before the first decision lands cannot fire twice.
 */
@Composable
private fun MemoryQueue(
    data: JsonObject?,
    read: SectionRead,
    onRetry: (() -> Unit)?,
    /** False on a dead or stale link: every write here dims, as on ModelsPlate. */
    canAct: Boolean,
    busyId: Long?,
    onKeep: (id: Long) -> Unit,
    onDiscard: (id: Long) -> Unit,
    sleepOffer: JsonObject?,
    sleepOfferBusy: Boolean,
    onSleepTimeAction: (enabled: Boolean?, remind: Boolean?) -> Unit,
    onDismissSleepOffer: () -> Unit,
) {
    val chrome = LocalChrome.current
    // Two allocating passes (a cast-filter and a new list) over the pending array,
    // previously redone on every recomposition of an unskippable screen — i.e. on
    // every server event, including the many that have nothing to do with memory.
    // Keyed on the raw payload so a real change to the queue still rebuilds it;
    // hoisted above the null branch so the remember is not behind a conditional
    // return.
    val items = remember(data) {
        (data?.get("pending") as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
    }
    Section("Memory awaiting review") {
        if (sleepOffer != null) {
            SleepOfferCard(
                offer = sleepOffer,
                busy = sleepOfferBusy,
                canAct = canAct,
                onEnable = { onSleepTimeAction(true, null) },
                onNotNow = onDismissSleepOffer,
                onStopAsking = { onSleepTimeAction(null, false) },
            )
            Gap(10)
        }
        Plate {
            if (data == null) {
                SectionUnread(read, "Proposed facts", onRetry)
                return@Plate
            }
            if (items.isEmpty()) {
                Text(
                    "Nothing is waiting. Either Jarvis has not heard anything " +
                        "worth keeping, or learning is off.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                )
                return@Plate
            }
            items.forEachIndexed { i, item ->
                if (i > 0) Rule()
                val id = item.str("id")?.toLongOrNull()
                MemoryProposalRow(
                    text = item.str("text") ?: "(no text)",
                    source = item.str("source"),
                    busy = id != null && id == busyId,
                    canAct = canAct,
                    // A row with no readable id can be shown but not decided -
                    // the same "say what you can, act on what you know" rule
                    // as a section with no data at all.
                    onKeep = id?.let { { onKeep(it) } },
                    onDiscard = id?.let { { onDiscard(it) } },
                )
            }
        }
    }
}

/**
 * The daily overnight-tidy offer. `offer` is `setup.sleep_time_offer` from
 * `/api/memory/pending`, verbatim - the same object [MemoryQueue]'s caller
 * decided to keep showing, so this composable never reads staleness or
 * once-a-day tracking itself.
 */
@Composable
private fun SleepOfferCard(
    offer: JsonObject,
    busy: Boolean,
    canAct: Boolean,
    onEnable: () -> Unit,
    onNotNow: () -> Unit,
    onStopAsking: () -> Unit,
) {
    val chrome = LocalChrome.current
    // Enable and Stop asking are writes to the desktop, so they dim with the
    // link. Not now stays live: it only hides this card on this phone for
    // today and sends nothing, so refusing it on a stale link would guard
    // nothing.
    val canWrite = !busy && canAct
    Plate(outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Text(
            offer.str("title") ?: "Let Jarvis tidy its memory overnight?",
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
        )
        offer.str("body")?.let {
            Gap(6)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
        Gap(10)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Quiet(
                if (busy) "Enabling…" else "Enable",
                color = chrome.okInk,
                enabled = canWrite,
                onClick = onEnable,
            )
            Quiet("Not now", color = chrome.textMid, enabled = !busy, onClick = onNotNow)
            Quiet(
                if (busy) "Working…" else "Stop asking",
                color = chrome.textLo,
                enabled = canWrite,
                onClick = onStopAsking,
            )
        }
    }
}

@Composable
private fun MemoryProposalRow(
    text: String,
    source: String?,
    busy: Boolean,
    canAct: Boolean,
    onKeep: (() -> Unit)?,
    onDiscard: (() -> Unit)?,
) {
    val chrome = LocalChrome.current
    Column {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        if (source != null) {
            Gap(2)
            Text("from $source", style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
        Gap(6)
        // Affirm/Refuse, not two Quiets tinted okInk/badInk - this app's own
        // rule (SHARED-LOOK.md §9) is that ok and bad are never told apart by
        // colour alone, because verdant-4/rose-4 simulate to nearly the same
        // beige for a deuteranope. Every other approve/deny pair already uses
        // this shape (ApprovalCard's Approve/Deny); this row was the one the
        // Sept 18 UI audit found still hadn't been moved over.
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Affirm(
                if (busy) "Keeping…" else "Keep",
                enabled = !busy && canAct && onKeep != null,
                onClick = { onKeep?.invoke() },
            )
            Refuse(
                if (busy) "Discarding…" else "Discard",
                enabled = !busy && canAct && onDiscard != null,
                onClick = { onDiscard?.invoke() },
            )
        }
    }
}

/**
 * Chips that wrap to the width they have.
 *
 * This used to be fixed rows of three, on the grounds that FlowRow was still
 * experimental. A plain Row does not wrap, so with long capability names or
 * the phone's font size turned up the third chip was squeezed and its text
 * broke inside the pill. FlowRow places as many as fit and starts a new line.
 *
 * The opt-in is kept deliberately. Whether plain FlowRow still needs it in
 * this BOM (2026.06.00) has not been checked - there is no local Android
 * build - and an opt-in that turns out to be unneeded costs nothing, while a
 * missing one would fail the only compiler this project has.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FlowChips(items: Collection<String>, muted: Boolean = false) {
    val chrome = LocalChrome.current
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        items.forEach {
            Pill(it, color = if (muted) chrome.textLo else chrome.textMid)
        }
    }
}

@Composable
fun TopBar(
    title: String,
    onBack: () -> Unit,
    /** A second line under the title. Optional and additive - every existing caller is unaffected. */
    subtitle: String? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    val chrome = LocalChrome.current
    Row(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Quiet("← Back", color = LocalAccent.current, onClick = onBack)
        Spacer(Modifier.width(4.dp))
        Column(Modifier.weight(1f)) {
            // A heading, so TalkBack's "navigate by headings" lands on it. No
            // screen had a single one, so a long screen like this could only
            // be read by swiping through every row. Shared by every sub-screen
            // that uses TopBar.
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                color = chrome.textHi,
                modifier = Modifier.semantics { heading() },
            )
            if (subtitle != null) {
                Text(
                    subtitle,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                )
            }
        }
        trailing?.invoke()
    }
}

// ------------------------------------------------------------- json ------

private fun JsonObject.str(key: String): String? =
    (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content?.takeIf { it.isNotBlank() }

private fun rushOf(contentRisk: JsonObject?): JsonObject? =
    contentRisk?.get("rush") as? JsonObject

/** Human-facing key: `last_verified_at` becomes "Last verified at". */
private fun humanise(key: String): String =
    key.replace('_', ' ').replace('-', ' ')
        .replaceFirstChar { it.uppercase() }

private fun flatten(obj: JsonObject, prefix: String = "", depth: Int = 0): List<Pair<String, String>> {
    val out = mutableListOf<Pair<String, String>>()
    for ((key, value) in obj) {
        val label = if (prefix.isEmpty()) humanise(key) else "$prefix · ${humanise(key)}"
        when (value) {
            is JsonPrimitive -> {
                if (value is JsonNull) continue
                out += label to value.content
            }
            is JsonObject -> if (depth < 2) out += flatten(value, label, depth + 1)
            is JsonArray -> {
                val scalars = value.mapNotNull { (it as? JsonPrimitive)?.content }
                out += if (scalars.size == value.size && scalars.isNotEmpty()) {
                    label to scalars.joinToString(", ")
                } else {
                    label to "${value.size}"
                }
            }
        }
    }
    return out
}

/** True for ids, hashes and paths — the strings a monospace face is for. */
private fun String.looksMachine(): Boolean =
    length > 6 && none { it == ' ' } && any { it.isDigit() || it == '/' || it == ':' || it == '-' }
