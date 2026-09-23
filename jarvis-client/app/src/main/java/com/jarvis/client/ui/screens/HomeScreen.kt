package com.jarvis.client.ui.screens

import android.content.Intent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.FaceState
import com.jarvis.client.LinkState
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceView
import com.jarvis.client.net.Attention
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.ui.approval.ApprovalCard
import com.jarvis.client.ui.parts.AppearanceIcon
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.HelpIcon
import com.jarvis.client.ui.parts.InboxIcon
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.MindIcon
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Pill
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.parts.VoiceButton
import com.jarvis.client.ui.parts.VoiceStrip
import com.jarvis.client.voice.VoiceSession
import kotlinx.coroutines.launch
import androidx.compose.runtime.State
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii

/** The face's starting share of the space below the top bar. */
private const val DEFAULT_FACE_FRACTION = 0.75f

/** Neither pane may be dragged away entirely - each keeps at least this much. */
private const val MIN_FACE_FRACTION = 0.20f
private const val MAX_FACE_FRACTION = 0.85f

/** How far a swipe on [TopReveal] has to travel before it counts. */
private val REVEAL_THRESHOLD = 28.dp

@Immutable
data class HomeState(
    val link: LinkState,
    val linkDetail: String?,
    val stale: Boolean,
    val activity: Activity,
    val faceState: FaceState,
    val power: String,
    val status: StatusInfo?,
    val pending: List<PendingItem>,
    val attention: Attention,
    val notice: String?,
    val streaming: Boolean,
    val face: Face,
    val bindings: Bindings,
    /** OFF unless a voice turn is in flight. */
    val voicePhase: VoiceSession.Phase,
    /**
     * Whether to show the microphone at all.
     *
     * False hides it rather than showing one that posts audio into a 404 —
     * §2's rule is that a capability reporting false means hide the UI for it.
     */
    val voiceOffered: Boolean,
    /** What the desktop heard, so a mis-hearing is visible rather than silent. */
    val transcript: String?,
    val voiceNotice: String?,
    /**
     * The desktop is running without its approval gate.
     *
     * Said out loud rather than shown as an empty list: "nothing is waiting for
     * you" and "nothing can wait for you, because nothing is asking" are
     * opposite facts that look identical.
     */
    val approvalsOff: Boolean,
    /**
     * The approvals whose decision is already on its way to the desktop.
     *
     * Read by nothing in this file, and that is not an oversight - deleting it
     * would break something that is not visible from here. `blockerFor` calls
     * JarvisRuntime.decisionBlocker(), which reads `_deciding` / `_stale` /
     * `_link` as plain `.value` on a MutableStateFlow. That is not a snapshot
     * read, so composition subscribes to nothing and the blocker would never
     * be recomputed. Carrying these values in the state is what forces the
     * rebuild that re-runs it - so a decision in flight actually greys the
     * buttons out instead of letting a second tap send it twice.
     */
    val deciding: Set<String>,
    /**
     * The approval a notification or digest row asked us to open, or null.
     *
     * The list scrolls to it and outlines it. An id that matches nothing in
     * `pending` - already answered, expired, not refreshed yet - does nothing
     * at all, which is what the screen did before this existed.
     */
    val focusApproval: String?,
    /**
     * What Jarvis is doing right now, in words, or null. Shown under the link
     * label while the stream is live; a sentence about a step that may have
     * finished is not shown over a link that cannot confirm it.
     */
    val activityDetail: String? = null,
)

@Immutable
data class HomeActions(
    val onDraftChange: (String) -> Unit,
    val onSend: () -> Unit,
    val onInterrupt: () -> Unit,
    val onApprove: (PendingItem) -> Unit,
    val onDeny: (PendingItem) -> Unit,
    /** A note before the first decision - AUTONOMY-PROPOSALS.md §3b. DRAFT; see ApprovalCard. */
    val onAmend: suspend (id: String, note: String) -> Unit,
    val onReconnect: () -> Unit,
    val onDismissNotice: () -> Unit,
    val onOpenChecks: () -> Unit,
    val onOpenInbox: () -> Unit,
    val onOpenBrain: () -> Unit,
    val onOpenAppearance: () -> Unit,
    val onOpenFaq: () -> Unit,
    val blockerFor: (PendingItem) -> String?,
    val onVoiceBegin: () -> Unit,
    val onVoiceRelease: () -> Unit,
    val onVoiceCancel: () -> Unit,
    val onDismissVoiceNotice: () -> Unit,
    /**
     * Pause, resume, stop, or add a note to whatever Jarvis is running -
     * AUTONOMY-PROPOSALS.md §3d. DRAFT; see [com.jarvis.client.JarvisRuntime.pauseTask].
     */
    val onPauseTask: suspend () -> Unit = {},
    val onResumeTask: suspend () -> Unit = {},
    val onStopTask: suspend () -> Unit = {},
    val onInjectTaskNote: suspend (note: String) -> Unit = {},
)

@Composable
fun HomeScreen(
    state: HomeState,
    actions: HomeActions,
    /**
     * The streamed reply, read as a lambda rather than passed as a value.
     *
     * Every token used to rebuild HomeState, which recomposed the link bar, the
     * whole list and the composer while the face was drawing at 60fps on the
     * same thread. Reading it inside the one composable that draws it keeps a
     * streaming reply from touching anything else.
     */
    reply: () -> String,
    /**
     * What is typed in the composer, read as a lambda for the same reason as
     * `reply` above.
     *
     * It used to be a field of HomeState, so every keystroke rebuilt the state
     * and recomposed the link bar, the face block, every visible approval card
     * and the reply while the reactor was animating on the same thread. Read
     * here only inside `Composer`, a character now invalidates the composer and
     * nothing else.
     */
    draft: () -> String,
    /** Read in the draw phase only — see VoiceButton. */
    micLevel: State<Float>,
    /**
     * Jarvis's own voice while he is speaking, null when he is not.
     *
     * Nullable rather than zeroed, and the difference is the whole point: the
     * face treats null as "no level is coming" and substitutes its own
     * speech-shaped envelope, so a flat 0f would read as a voice that is
     * playing and perfectly silent and hold the reactor still through every
     * answer.
     */
    speechLevel: State<Float?>,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val motion = LocalMotion.current
    val density = LocalDensity.current

    // Hidden by default. The tabs are one swipe away on TopReveal below, not
    // gone - but nothing here is fixed across the top of the screen every
    // time, which is the whole point of giving the face the room back.
    var topBarVisible by remember { mutableStateOf(false) }

    // The face's share of the space below the top bar - DEFAULT_FACE_FRACTION
    // to start, and draggable from there on the Grabber between the two
    // panes. rememberSaveable, so rotating the phone does not reset a resize
    // the owner just made.
    var faceFraction by rememberSaveable { mutableStateOf(DEFAULT_FACE_FRACTION) }

    Column(
        modifier
            .fillMaxSize()
            .background(chrome.surface0)
            .navigationBarsPadding()
            .imePadding(),
    ) {
        TopReveal(visible = topBarVisible, onToggle = { topBarVisible = it })
        AnimatedVisibility(
            visible = topBarVisible,
            enter = fadeIn(motion.enter()),
            exit = fadeOut(motion.micro()),
        ) {
            LinkBar(state, actions)
        }

        val listState = rememberLazyListState()
        // Where "Open the approval →" actually lands. The id used to be set and
        // then dropped unread, so the tap navigated home and left the reader to
        // find the right card themselves.
        val focusIndex = state.focusApproval?.let { id ->
            state.pending.indexOfFirst { it.id == id }.takeIf { it >= 0 }
        }
        LaunchedEffect(state.focusApproval, focusIndex) {
            val index = focusIndex ?: return@LaunchedEffect
            // Counted, not guessed. The face has its own pane now and is no
            // longer item 0 here; the notice and the approvals-off plate are
            // conditional; the "waiting on you" label sits immediately above
            // the cards and exists whenever any card does - which a found
            // index guarantees. Adding an item to this list above the cards
            // means adding it here too.
            val leading =
                (if (state.activity == Activity.WORKING || state.activity == Activity.PAUSED) 1 else 0) +
                (if (state.notice != null) 1 else 0) +
                (if (state.approvalsOff) 1 else 0) +
                1
            listState.animateScrollToItem(leading + index)
        }

        // The resizable region: the face pane, a drag handle, and the
        // conversation below it, sharing whatever height is left once the top
        // bar (when shown) and the composer have taken theirs.
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
            // A plain pixel delta from the drag, turned into a fraction of
            // THIS box's own height - measured here, not assumed, because the
            // top bar's own height (zero, hidden; real, revealed) changes how
            // much of the screen this box actually gets.
            val dragState = rememberDraggableState { deltaPx ->
                val heightPx = with(density) { maxHeight.toPx() }
                if (heightPx > 0f) {
                    faceFraction = (faceFraction + deltaPx / heightPx)
                        .coerceIn(MIN_FACE_FRACTION, MAX_FACE_FRACTION)
                }
            }

            Column(Modifier.fillMaxSize()) {
                FaceBlock(
                    state, actions, micLevel, speechLevel,
                    modifier = Modifier.weight(faceFraction).fillMaxWidth(),
                )

                Grabber(
                    color = chrome.textLo,
                    modifier = Modifier
                        .fillMaxWidth()
                        .draggable(state = dragState, orientation = Orientation.Vertical),
                )

                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f - faceFraction).fillMaxWidth(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    // AUTONOMY-PROPOSALS.md §3d. Shown only while the server itself
                    // reports a task running or paused - never while merely thinking
                    // about a chat reply, which WORKING is also used for elsewhere;
                    // that overlap is accepted here the same way LinkBar's own
                    // THINKING/WORKING merge already is, since a stray control on a
                    // short chat turn costs nothing and hiding it during a real task
                    // would cost the one thing this section exists for.
                    if (state.activity == Activity.WORKING || state.activity == Activity.PAUSED) {
                        item(key = "task-controls") {
                            TaskControlsPlate(paused = state.activity == Activity.PAUSED, actions = actions)
                        }
                    }

                    if (state.notice != null) {
                        item(key = "notice") { Notice(state.notice, actions.onDismissNotice) }
                    }

                    if (state.approvalsOff) {
                        item(key = "approvals-off") {
                            Plate(outline = chrome.warnInk.copy(alpha = 0.35f)) {
                                Kicker("Approvals are off", color = chrome.warnInk)
                                Gap(6)
                                Text(
                                    "The desktop is running without its permission gate, so nothing " +
                                        "will ever arrive here to approve.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = chrome.textMid,
                                )
                            }
                        }
                    }

                    if (state.pending.isNotEmpty()) {
                        item(key = "approvals-label") {
                            Kicker(
                                if (state.pending.size == 1) "Waiting on you" else "${state.pending.size} waiting on you",
                                color = chrome.warnInk,
                            )
                        }
                        items(state.pending, key = { it.id }) { item ->
                            ApprovalCard(
                                item = item,
                                blocker = actions.blockerFor(item),
                                // Outlined, not auto-answered: scrolling to a card and
                                // marking it is the whole of "open the approval". Rule
                                // 4 - nothing is ever approved without a deliberate
                                // decision - is untouched by it.
                                focused = item.id == state.focusApproval,
                                onApprove = { actions.onApprove(item) },
                                onDeny = { actions.onDeny(item) },
                                onAmend = { note -> actions.onAmend(item.id, note) },
                            )
                        }
                    }

                    item(key = "reply") { Reply(reply, state.streaming) }
                }
            }
        }

        Composer(state, draft, actions, micLevel)
    }
}

/**
 * The strip that shows or hides [LinkBar].
 *
 * Its own gesture, rather than one more added to the face or the list
 * below: the face already has a tap (open the brain) and the conversation
 * already scrolls, and stacking a third gesture on either was one guess too
 * many to make correctly without a device in hand to try it on. This strip
 * touches nothing else, so it cannot fight either of them.
 */
@Composable
private fun TopReveal(visible: Boolean, onToggle: (Boolean) -> Unit) {
    val chrome = LocalChrome.current
    val thresholdPx = with(LocalDensity.current) { REVEAL_THRESHOLD.toPx() }
    Box(
        Modifier
            .fillMaxWidth()
            .pointerInput(visible) {
                var total = 0f
                detectVerticalDragGestures(
                    onDragStart = { total = 0f },
                    onDragEnd = {
                        if (!visible && total > thresholdPx) onToggle(true)
                        if (visible && total < -thresholdPx) onToggle(false)
                    },
                ) { change, dragAmount ->
                    change.consume()
                    total += dragAmount
                }
            },
    ) {
        // Filled brighter while hidden - "swipe down, there's more here" -
        // and dimmer once the bar is showing, where it now means "swipe up".
        Grabber(color = chrome.textLo, alpha = if (visible) 0.25f else 0.55f)
    }
}

/**
 * The small pill both drag handles show, so the same "there is more here,
 * drag me" affordance means the same thing wherever it appears.
 */
@Composable
private fun Grabber(color: Color, modifier: Modifier = Modifier, alpha: Float = 0.45f) {
    Box(modifier.height(20.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .width(36.dp)
                .height(4.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(color.copy(alpha = alpha)),
        )
    }
}

/**
 * The face, in its own pane above the conversation.
 *
 * Tapping it opens the brain: the face is the only thing on screen that is
 * obviously *Jarvis*, so it is the right door to what Jarvis is doing.
 *
 * Sized entirely by the caller's [modifier] rather than an aspect ratio - the
 * pane is a fraction of the screen the owner can drag, and an aspect ratio
 * here would fight that instead of filling whatever height the fraction
 * hands it.
 */
@Composable
private fun FaceBlock(
    state: HomeState,
    actions: HomeActions,
    micLevel: State<Float>,
    speechLevel: State<Float?>,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Box(
        modifier
            .clip(LocalRadii.current.shellShape)
            .pressable(onClick = actions.onOpenBrain),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            FaceView(
                state = state.faceState,
                face = state.face,
                bindings = state.bindings,
                notches = state.attention.pending,
                modifier = Modifier.size(260.dp),
                // Both levels were being measured and thrown away. The recorder
                // computes an RMS per audio buffer and the speaker one per chunk,
                // precisely so the reactor breathes with the real voice rather than
                // with a generator — and neither reached the face, because these
                // two parameters defaulted to `{ null }` and no caller passed them.
                // So the reactor has been running the synthetic envelope through
                // every word either end has ever said.
                //
                // Lambdas rather than values: they are read from the frame loop, in
                // a coroutine, where a snapshot read subscribes nothing. Fifty
                // levels a second reach the face and recompose nothing at all.
                micLevel = { micLevel.value },
                speechLevel = { speechLevel.value },
                // The theme's own well, not a hardcoded near-black - see
                // Chrome.well. A theme whose ground is not that same
                // near-black (Graphite, Ember Dusk) used to sit the reactor
                // in a visibly mismatched box; this is the token the theme
                // system already carries for exactly this, just never read
                // before now.
                background = chrome.well,
            )
            Gap(6)
            // The lane, which the phone parsed and threw away. "This left your
            // machine" is the single most consequential fact the UI carries and
            // it had no representation here at all.
            LaneChip(state.status)
            Gap(6)
            Text(
                "State of mind →",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}

@Composable
private fun LaneChip(status: StatusInfo?) {
    val chrome = LocalChrome.current
    val lane = status?.lane?.lowercase()
    val model = status?.model
    when (lane) {
        // violet-4 is the desktop's `--cloud`, and it means the same thing on
        // both: this is leaving the local lane.
        "cloud" -> Pill("Cloud" + (model?.let { " · $it" } ?: ""), color = com.jarvis.client.face.Palette.VIOLET_4)
        "offline" -> Pill("Offline", color = chrome.badInk)
        "local" -> Pill("Local" + (model?.let { " · $it" } ?: ""), color = chrome.okInk)
        else -> if (model != null) Pill(model, color = chrome.textMid)
    }
}

/**
 * Pause, resume, stop, or add a note to whatever Jarvis is running -
 * AUTONOMY-PROPOSALS.md §3d. DRAFT throughout: no backend anywhere is
 * confirmed to answer any of the four calls this wires to, so every button
 * here can fail, and does so honestly rather than pretending to work - see
 * [com.jarvis.client.JarvisRuntime.pauseTask]'s own doc comment.
 *
 * `paused` answers only to the server's own reported [Activity], never to
 * whether a click's own suspend call resolved - clicking Pause does not
 * flip this composable's own idea of the state, because a click only
 * proves a request was sent. Exactly the honesty rule the desktop's own
 * widget (`jarvis-desktop/src/widget.js`) already learned building the
 * matching feature, and its own comment documents having gotten wrong on
 * the first pass.
 */
@Composable
private fun TaskControlsPlate(paused: Boolean, actions: HomeActions) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var noteText by rememberSaveable { mutableStateOf("") }
    var noteSending by remember { mutableStateOf(false) }

    fun act(call: suspend () -> Unit) {
        if (busy) return
        busy = true
        scope.launch {
            call()
            busy = false
        }
    }

    Plate {
        Text(
            if (paused) "A task is paused" else "A task is running",
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "This section is a draft: the desktop does not yet confirm pausing, " +
                "resuming or stopping, so these buttons may simply do nothing today.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (paused) {
                Quiet("Resume", enabled = !busy, onClick = { act(actions.onResumeTask) })
            } else {
                Quiet("Pause", enabled = !busy, onClick = { act(actions.onPauseTask) })
            }
            Quiet("Stop", color = chrome.badInk, enabled = !busy, onClick = { act(actions.onStopTask) })
        }
        Spacer(Modifier.height(10.dp))
        // A note here never touches the steps already approved and running -
        // AUTONOMY-PROPOSALS.md §3d. It is queued for the NEXT proposal, the
        // same amend flow the approval card's own note field uses.
        Row(verticalAlignment = Alignment.Bottom) {
            TextInput(
                value = noteText,
                onValueChange = { noteText = it },
                placeholder = "Add something for what runs next…",
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet(
                if (noteSending) "…" else "Send",
                enabled = !noteSending && noteText.isNotBlank(),
                onClick = {
                    val note = noteText
                    noteSending = true
                    scope.launch {
                        actions.onInjectTaskNote(note)
                        noteSending = false
                        noteText = ""
                    }
                },
            )
        }
    }
}

@Composable
private fun LinkBar(state: HomeState, actions: HomeActions) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current

    // Two different facts, never merged into one word: whether the stream is up,
    // and whether Jarvis is busy. Collapsing them is how a client ends up
    // showing "thinking" at a desktop that went away ten minutes ago.
    val (dot, label) = when {
        state.link != LinkState.CONNECTED -> chrome.badMark to (state.linkDetail ?: "Offline")
        state.stale -> chrome.warnMark to "Stale — reconnecting"
        else -> when (state.activity) {
            Activity.LISTENING -> chrome.warnMark to "Listening"
            Activity.THINKING, Activity.WORKING -> accent to "Thinking"
            Activity.PAUSED -> chrome.warnMark to "Paused"
            Activity.SPEAKING -> accent to "Speaking"
            Activity.ERROR -> chrome.badMark to "Error on the desktop"
            else -> chrome.okMark to when (state.power) {
                "quiet" -> "Linked · quiet"
                "standby" -> "Linked · standby"
                else -> "Linked"
            }
        }
    }

    Column(Modifier.fillMaxWidth().background(chrome.surface1)) {
        Row(
            Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // The status is itself the way to the checks. You tap the thing that
            // is wrong to find out why, and it is present whether or not the
            // link is up — which the old Checks link was not.
            Row(
                Modifier
                    .weight(1f)
                    .clip(LocalRadii.current.insetShape)
                    .pressable(onClick = actions.onOpenChecks)
                    .padding(horizontal = 8.dp, vertical = 10.dp)
                    // Measured at ~40dp before this - 10dp padding plus 13sp
                    // text, on the row that opens Checks from the busiest
                    // screen in the app.
                    .minimumInteractiveComponentSize(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Dot(dot)
                Spacer(Modifier.width(10.dp))
                Column {
                    Text(
                        label,
                        style = MaterialTheme.typography.labelMedium,
                        color = chrome.textHi,
                    )
                    // The progress line, AUTONOMY-PROPOSALS §3c: the backend's
                    // own per-step sentence, under the state it belongs to. One
                    // line, clipped - it is a status, not a log. Only on a live
                    // link, because "Step 2/3" under "Stale" would be a claim
                    // about work the phone cannot see.
                    val detail = state.activityDetail
                    if (detail != null && state.link == LinkState.CONNECTED && !state.stale) {
                        Text(
                            detail,
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textMid,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }

            // A status, not a destination - shown only while there is
            // something to retry, so it stays out of the evenly-spaced
            // navigation row below rather than crowding a fifth icon in.
            if (state.link != LinkState.CONNECTED) {
                Quiet("Retry", onClick = actions.onReconnect)
            }
        }

        // UI-AUDIT-2026-09-18 choice A1: icons + words, status separated
        // from navigation by a rule, Brain gets a real button, "Look"
        // becomes "Appearance". Four destinations, evenly weighted so the
        // row balances regardless of phone width.
        Rule()
        Row(Modifier.fillMaxWidth()) {
            NavItem(
                icon = { MindIcon(chrome.textMid) },
                label = "Mind",
                onClick = actions.onOpenBrain,
                modifier = Modifier.weight(1f),
            )
            NavItem(
                icon = { InboxIcon(if (state.attention.pending > 0) chrome.warnInk else chrome.textMid) },
                label = if (state.attention.pending > 0) "Inbox · ${state.attention.pending}" else "Inbox",
                color = if (state.attention.pending > 0) chrome.warnInk else chrome.textMid,
                onClick = actions.onOpenInbox,
                modifier = Modifier.weight(1f),
            )
            NavItem(
                icon = { AppearanceIcon(chrome.textMid) },
                label = "Appearance",
                onClick = actions.onOpenAppearance,
                modifier = Modifier.weight(1f),
            )
            NavItem(
                icon = { HelpIcon(chrome.textMid) },
                label = "Help",
                onClick = actions.onOpenFaq,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

/** One icon-over-word destination in the nav row. 48dp tall regardless of
 *  how small the icon and label look, so this is also the fix for 1.4's
 *  under-48dp touch targets in the same bar. */
@Composable
private fun NavItem(
    icon: @Composable () -> Unit,
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    color: Color = LocalChrome.current.textMid,
) {
    Column(
        modifier
            .clip(LocalRadii.current.insetShape)
            .pressable(onClick = onClick)
            .padding(vertical = 4.dp)
            .heightIn(min = 48.dp)
            .minimumInteractiveComponentSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        icon()
        Gap(2)
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = color,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun Reply(reply: () -> String, streaming: Boolean) {
    val chrome = LocalChrome.current
    val motion = LocalMotion.current
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val text = reply()
    AnimatedVisibility(
        visible = text.isNotBlank() || streaming,
        enter = fadeIn(motion.enter()),
        exit = fadeOut(motion.micro()),
    ) {
        Plate {
            if (streaming) {
                Kicker("Jarvis", color = LocalAccent.current)
                Gap(6)
            }
            Text(
                text.ifBlank { "…" },
                style = MaterialTheme.typography.bodyLarge,
                color = chrome.textHi,
            )
            // Only once there is a finished answer to act on - copying or
            // sharing a reply mid-stream would grab a sentence Jarvis has not
            // finished writing yet.
            if (!streaming && text.isNotBlank()) {
                Gap(8)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Quiet("Copy", color = chrome.textMid) {
                        clipboard.setText(AnnotatedString(text))
                    }
                    Quiet("Share", color = chrome.textMid) {
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, text)
                        }
                        context.startActivity(Intent.createChooser(intent, null))
                    }
                }
            }
        }
    }
}

@Composable
private fun Composer(
    state: HomeState,
    draft: () -> String,
    actions: HomeActions,
    micLevel: State<Float>,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val radii = LocalRadii.current
    // The one snapshot read of the draft in the whole screen, so a keystroke
    // recomposes this composable and nothing above it.
    val text = draft()
    val canSend = text.isNotBlank() && state.link == LinkState.CONNECTED

    Column(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
    when (state.voicePhase) {
        VoiceSession.Phase.CAPTURING ->
            VoiceStrip("Listening — release to send, slide up to cancel")
        VoiceSession.Phase.VERIFYING ->
            // Named for what it is. The desktop checks whose voice this is
            // BEFORE transcribing, so that a voice that is not his is never
            // turned into words at all.
            VoiceStrip("Checking it's you…")
        VoiceSession.Phase.THINKING -> VoiceStrip("Thinking…")
        VoiceSession.Phase.SPEAKING -> VoiceStrip("Speaking")
        VoiceSession.Phase.OFF -> Unit
    }
    if (state.transcript != null && state.voicePhase != VoiceSession.Phase.CAPTURING) {
        VoiceStrip("“${state.transcript}”", tone = chrome.textMid)
    }
    if (state.voiceNotice != null) {
        VoiceStrip(state.voiceNotice, tone = chrome.warnInk, onDismiss = actions.onDismissVoiceNotice)
    }
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Bottom,
    ) {
        // BasicTextField rather than OutlinedTextField: the Material one brings
        // its own container, its own 56dp minimum, its own label animation and
        // its own notched outline, none of which belong in a design made of
        // flat plates and hairlines.
        Box(
            Modifier
                .weight(1f)
                .clip(radii.controlShape)
                .background(chrome.surface2)
                .padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            if (text.isEmpty()) {
                Text(
                    "Ask Jarvis",
                    style = MaterialTheme.typography.bodyLarge,
                    color = chrome.textLo,
                )
            }
            BasicTextField(
                value = text,
                onValueChange = actions.onDraftChange,
                textStyle = LocalTextStyle.current.merge(
                    MaterialTheme.typography.bodyLarge.copy(color = chrome.textHi),
                ),
                cursorBrush = SolidColor(accent),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                // The keyboard showed a Send key that did nothing: ImeAction
                // only chooses the key's label, and without this the press is
                // swallowed. Same guard as the button, so an empty draft or a
                // dead link cannot be sent from the keyboard either.
                keyboardActions = KeyboardActions(onSend = { if (canSend) actions.onSend() }),
                maxLines = 5,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Spacer(Modifier.width(10.dp))
        Box(
            Modifier
                .height(48.dp)
                .clip(radii.controlShape)
                .background(
                    when {
                        state.streaming -> chrome.badInk.copy(alpha = 0.16f)
                        canSend -> accent
                        else -> chrome.surface2
                    },
                )
                .pressable(
                    enabled = state.streaming || canSend,
                    onClick = if (state.streaming) actions.onInterrupt else actions.onSend,
                )
                .padding(horizontal = 18.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                // Interrupt is the same button, because it is the same action's
                // other half: cancelling the HTTP call is what stops generation.
                if (state.streaming) "Stop" else "Send",
                style = MaterialTheme.typography.labelLarge,
                color = when {
                    state.streaming -> chrome.badInk
                    canSend -> chrome.surface0
                    else -> chrome.textLo
                },
            )
        }
        if (state.voiceOffered) {
            Spacer(Modifier.width(8.dp))
            VoiceButton(
                enabled = state.link == LinkState.CONNECTED && !state.streaming,
                capturing = state.voicePhase == VoiceSession.Phase.CAPTURING,
                micLevel = micLevel,
                onBegin = actions.onVoiceBegin,
                onRelease = actions.onVoiceRelease,
                onCancel = actions.onVoiceCancel,
            )
        }
    }
    }
}
