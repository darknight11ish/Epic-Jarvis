package com.jarvis.client.ui.screens

import android.content.Intent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animate
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.DraggableState
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
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
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.layout.layoutId
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import com.jarvis.client.Activity
import com.jarvis.client.FaceState
import com.jarvis.client.LinkState
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceView
import com.jarvis.client.data.FaceSize
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
import com.jarvis.client.ui.theme.Themes
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/** The face's starting share of the space below the status line. */
private const val DEFAULT_FACE_FRACTION = 0.75f

/** Neither pane may be dragged away entirely - each keeps at least this much. */
private const val MIN_FACE_FRACTION = 0.20f
private const val MAX_FACE_FRACTION = 0.85f

/** How far one "Bigger face" / "Smaller face" screen-reader action moves the split. */
private const val FACE_STEP = 0.10f

/** How far a swipe on [StatusLine] has to travel before it counts. */
private val REVEAL_THRESHOLD = 28.dp

/**
 * Every handle on this screen is at least this tall, whatever its pill
 * looks like - the 48dp touch minimum. They were 20dp, which is a target
 * most thumbs miss more often than they hit.
 */
private val HANDLE_HEIGHT = 48.dp

/** The three children of the split pane, found by id rather than by position. */
private const val PANE_FACE = "face"
private const val PANE_HANDLE = "handle"
private const val PANE_LIST = "list"

/** The reply's key in the conversation list - the follow-the-reply code looks for it. */
private const val REPLY_KEY = "reply"

/** Where one paragraph of a reply ends: a blank line, however it is spaced. */
private val PARAGRAPH_BREAK = Regex("\n\\s*\n")

/** How many marks the still ring around the face carries - one a minute, like a watch. */
private const val TICKS = 60

/**
 * Why the face is smaller than the owner's own split right now, if it is.
 *
 * None of these is ever saved: each is a moment's layout, and the owner's
 * own split comes back the moment the reason goes away.
 */
private enum class Fold {
    /** The owner's own split. */
    NONE,

    /** Made small by a tap on the resize handle. Stays until tapped again. */
    MANUAL,

    /** Made small to give approval cards room. Undone when none are waiting. */
    APPROVALS,
}

/**
 * The split pane's own height, written in its measure block and read by the
 * drag callback. A plain field rather than state on purpose: nothing draws
 * from it, so nothing should be invalidated when it changes.
 */
private class PaneHeight {
    var px: Int = 0
}

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
    /** How big the face is drawn - an Appearance setting, never above 260dp. */
    val faceSize: FaceSize = FaceSize.DEFAULT,
    /**
     * The owner's own split: the face's share of the space between the status
     * line and the composer, MIN_FACE_FRACTION..MAX_FACE_FRACTION.
     *
     * Read as the starting point and whenever it changes (a slider in
     * Appearance, a preset). This screen never saves it: a finished drag is
     * reported through [HomeActions.onFaceFractionCommitted], and the caller
     * decides where it is kept. Before this came in from outside, the split
     * lived in a rememberSaveable here, which forgot it every time Home left
     * the screen - including by tapping the face itself - and on every launch.
     */
    val faceFraction: Float = DEFAULT_FACE_FRACTION,
    /**
     * The navigation row (Mind, Inbox, Appearance, Help) is always on screen
     * instead of one swipe or tap away. The status line above it is shown
     * either way - it is not a setting.
     */
    val navAlwaysShown: Boolean = false,
    /**
     * Shrink the face to its smallest when the first approval arrives or one
     * is opened from a notification, and give the owner's split back once
     * none are waiting. Layout only - it never decides anything.
     */
    val makeRoomForApprovals: Boolean = true,
    /** Shrink the face to its smallest while the keyboard is open. */
    val shrinkWhileTyping: Boolean = true,
    /** Keep a streaming reply in view as it grows, until the owner scrolls by hand. */
    val followReply: Boolean = true,
    /** Tapping the face opens Mind. Off, the face does nothing when touched. */
    val tapFaceOpensMind: Boolean = true,
    /**
     * Carried for FaceView's glow multiplier (0..1, only ever dimmer) and its
     * calm-motion flag. Not read in this file yet: the FaceView parameters
     * they feed are added on another branch and wired in by the integrator.
     */
    val glow: Float = 1f,
    val calmMotion: Boolean = false,
    /**
     * The owner's last question, shown as a "You" line above the reply so an
     * answer is never on screen without what it answers. Memory only - see
     * [com.jarvis.client.net.ChatSession.question]; nothing writes it to disk.
     */
    val lastUserText: String? = null,
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
    /**
     * The owner finished changing the split - a drag let go, a screen-reader
     * "Bigger face" / "Smaller face", or a double-tap back to the default.
     * Called once per change, never per frame, with the new fraction. The
     * caller saves it and hands it back as [HomeState.faceFraction].
     */
    val onFaceFractionCommitted: (Float) -> Unit = {},
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
    val motion = LocalMotion.current
    val density = LocalDensity.current

    // Only the navigation row is ever hidden. The status line above it is
    // always on screen - see StatusLine for why that is not negotiable.
    // rememberSaveable, so turning the phone does not snap an open row shut.
    var navOpen by rememberSaveable { mutableStateOf(false) }
    val navShown = state.navAlwaysShown || navOpen

    // ---- The split between the face and the conversation -----------------
    //
    // Three values, kept apart on purpose:
    //  - ownFraction: the owner's own split. It starts from, and follows,
    //    state.faceFraction, and changes here only when the owner finishes a
    //    drag, uses a screen-reader action or double-taps the handle - each
    //    reported through onFaceFractionCommitted for the caller to save.
    //  - fold: a temporary "make the face small" that is never saved (see
    //    Fold) - for approvals, or from a tap on the handle.
    //  - live: what is on screen at this instant. Read ONLY in the Layout's
    //    measure block below, so a drag that moves it every frame re-measures
    //    three children and recomposes nothing. The old BoxWithConstraints
    //    read it in composition, so every drag frame re-ran the face block
    //    and the whole list.
    var ownFraction by remember {
        mutableFloatStateOf(state.faceFraction.coerceIn(MIN_FACE_FRACTION, MAX_FACE_FRACTION))
    }
    LaunchedEffect(state.faceFraction) {
        ownFraction = state.faceFraction.coerceIn(MIN_FACE_FRACTION, MAX_FACE_FRACTION)
    }

    // Starts already folded when approvals are waiting as Home appears, so
    // coming back to Home does not play a shrink the owner has already seen.
    var fold by remember {
        mutableStateOf(
            if (state.makeRoomForApprovals && state.pending.isNotEmpty()) Fold.APPROVALS else Fold.NONE,
        )
    }
    // "The first one arrives": empty to non-empty makes room, and the room is
    // given back once nothing is waiting. A second card arriving while the
    // owner has already unfolded the face does not fold it again on them.
    val hasPending = state.pending.isNotEmpty()
    LaunchedEffect(hasPending) {
        if (hasPending) {
            if (state.makeRoomForApprovals && fold == Fold.NONE) fold = Fold.APPROVALS
        } else if (fold == Fold.APPROVALS) {
            fold = Fold.NONE
        }
    }

    // Whether the keyboard is up. A derived boolean over the inset, so the
    // keyboard's own slide - a new inset every frame - flips this once
    // rather than recomposing the screen on every frame of it.
    val ime = WindowInsets.ime
    val imeVisible by remember(ime, density) { derivedStateOf { ime.getBottom(density) > 0 } }
    // The owner moved the handle while typing: their choice wins until the
    // keyboard next closes.
    var keepSizeWhileTyping by remember { mutableStateOf(false) }
    LaunchedEffect(imeVisible) {
        if (!imeVisible) keepSizeWhileTyping = false
    }

    val typing = state.shrinkWhileTyping && imeVisible && !keepSizeWhileTyping
    val shrunk = typing ||
        fold == Fold.MANUAL ||
        (fold == Fold.APPROVALS && state.makeRoomForApprovals)
    val target = if (shrunk) MIN_FACE_FRACTION else ownFraction

    val live = remember { mutableFloatStateOf(target) }
    var dragging by remember { mutableStateOf(false) }
    // Glides to wherever the split should be. motion.state() is zero-length
    // under reduced motion, so the layout simply snaps there instead. A drag
    // cancels a glide in progress - the finger wins.
    LaunchedEffect(target, dragging) {
        if (dragging) return@LaunchedEffect
        val from = live.floatValue
        if (from != target) {
            animate(from, target, animationSpec = motion.state()) { value, _ ->
                live.floatValue = value
            }
        }
    }

    val paneHeight = remember { PaneHeight() }
    // A plain pixel delta from the drag, turned into a fraction of the room
    // the two panes actually share - measured, not assumed, because the
    // navigation row (shown or not) and the keyboard both change it.
    val dragState = rememberDraggableState { deltaPx ->
        val h = paneHeight.px
        if (h > 0) {
            live.floatValue = (live.floatValue + deltaPx / h)
                .coerceIn(MIN_FACE_FRACTION, MAX_FACE_FRACTION)
        }
    }

    // The owner reached for the handle: any temporary fold stops here, and
    // what they do next is their own split.
    fun takeOver() {
        fold = Fold.NONE
        if (imeVisible) keepSizeWhileTyping = true
    }

    fun commit(fraction: Float) {
        val f = fraction.coerceIn(MIN_FACE_FRACTION, MAX_FACE_FRACTION)
        ownFraction = f
        actions.onFaceFractionCommitted(f)
    }

    Column(
        modifier
            .fillMaxSize()
            .background(LocalChrome.current.surface0)
            .navigationBarsPadding()
            .imePadding(),
    ) {
        StatusLine(
            state = state,
            actions = actions,
            navShown = navShown,
            onNavToggle = if (state.navAlwaysShown) null else { shown -> navOpen = shown },
        )
        // Slides, not pops. With a fade alone AnimatedVisibility hands over
        // the row's whole height on the first frame and takes it back on the
        // last, so the face below jumped by the row's height each way.
        AnimatedVisibility(
            visible = navShown,
            enter = expandVertically(motion.enter(), expandFrom = Alignment.Top) + fadeIn(motion.enter()),
            exit = shrinkVertically(motion.micro(), shrinkTowards = Alignment.Top) + fadeOut(motion.micro()),
        ) {
            NavRow(state, actions)
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
            // Room first. At the owner's 75% the list was about 130dp tall,
            // so scrolling to the top of a card left its Approve and Deny
            // below the bottom edge. This only moves the layout; the card is
            // still decided by the owner, by hand.
            if (state.makeRoomForApprovals && fold == Fold.NONE) fold = Fold.APPROVALS
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

        // Keep a streaming reply in view. The reply is the last item, below
        // every approval card, and grew out of sight with nothing to say it
        // was there. Stops for the rest of this reply the moment the owner
        // drags the list themselves, and never runs while a notification has
        // sent them to a card - pulling the list away from the card they were
        // sent to decide would be worse than a reply they have to scroll to.
        //
        // Driven by the list's own layout rather than by the reply text: the
        // layout is what says how far the reply's bottom edge overhangs, and
        // reading the text here would recompose this whole screen per token.
        LaunchedEffect(state.streaming, state.followReply, state.focusApproval) {
            if (!state.streaming || !state.followReply || state.focusApproval != null) {
                return@LaunchedEffect
            }
            var handsOn = false
            launch {
                listState.interactionSource.interactions.collect { interaction ->
                    if (interaction is DragInteraction.Start) handsOn = true
                }
            }
            snapshotFlow {
                val info = listState.layoutInfo
                val last = info.visibleItemsInfo.lastOrNull()
                when {
                    last == null -> 0
                    // The reply is further down than anything on screen.
                    last.key != REPLY_KEY -> Int.MAX_VALUE
                    else -> last.offset + last.size - info.viewportEndOffset
                }
            }.collect { overhang ->
                if (handsOn || overhang <= 0) return@collect
                if (overhang == Int.MAX_VALUE) {
                    listState.scrollToItem(listState.layoutInfo.totalItemsCount - 1)
                } else {
                    listState.scrollBy(overhang.toFloat())
                }
            }
        }

        val handleWords =
            if (shrunk) "Made small" else "${(ownFraction * 100).roundToInt()} percent of the screen"

        // The resizable region: the face pane, a drag handle, and the
        // conversation below it, sharing whatever height is left once the
        // status line, the navigation row (when shown) and the composer have
        // taken theirs.
        Layout(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            content = {
                FaceBlock(
                    state, actions, micLevel, speechLevel,
                    // A face made small keeps what little room it has for
                    // itself and the lane, not for a caption.
                    showCaption = !shrunk,
                    modifier = Modifier.layoutId(PANE_FACE),
                )

                ResizeHandle(
                    stateWords = handleWords,
                    tapLabel = if (shrunk) "Give the face its room back" else "Make the face small",
                    dragState = dragState,
                    onDragStart = {
                        if (shrunk) takeOver()
                        dragging = true
                    },
                    onDragEnd = {
                        commit(live.floatValue)
                        dragging = false
                    },
                    onTap = {
                        if (shrunk) {
                            takeOver()
                        } else {
                            fold = Fold.MANUAL
                        }
                    },
                    onReset = {
                        takeOver()
                        commit(DEFAULT_FACE_FRACTION)
                    },
                    onNudge = { step ->
                        takeOver()
                        commit(live.floatValue + step)
                    },
                    modifier = Modifier.layoutId(PANE_HANDLE).fillMaxWidth(),
                )

                ConversationList(
                    state = state,
                    actions = actions,
                    reply = reply,
                    listState = listState,
                    modifier = Modifier.layoutId(PANE_LIST),
                )
            },
        ) { measurables, constraints ->
            val width = constraints.maxWidth
            val height = if (constraints.hasBoundedHeight) constraints.maxHeight else 0
            val handle = measurables.first { it.layoutId == PANE_HANDLE }
                .measure(Constraints(minWidth = width, maxWidth = width, minHeight = 0, maxHeight = height))
            val room = (height - handle.height).coerceAtLeast(0)
            paneHeight.px = room
            // The one read of `live`, here in measure: a drag frame re-runs
            // this block and nothing above it.
            val faceHeight = (room * live.floatValue).roundToInt().coerceIn(0, room)
            val face = measurables.first { it.layoutId == PANE_FACE }
                .measure(Constraints.fixed(width, faceHeight))
            val list = measurables.first { it.layoutId == PANE_LIST }
                .measure(Constraints.fixed(width, room - faceHeight))
            layout(width, height) {
                face.place(0, 0)
                handle.place(0, faceHeight)
                list.place(0, faceHeight + handle.height)
            }
        }

        Composer(state, draft, actions, micLevel)
    }
}

/**
 * The conversation: task controls, notices, approval cards and the reply.
 *
 * Its own composable so the split pane's content stays three plain children
 * the measure block can find by id.
 */
@Composable
private fun ConversationList(
    state: HomeState,
    actions: HomeActions,
    reply: () -> String,
    listState: LazyListState,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    LazyColumn(
        state = listState,
        modifier = modifier,
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        // AUTONOMY-PROPOSALS.md §3d. Shown only while the server itself
        // reports a task running or paused - never while merely thinking
        // about a chat reply, which WORKING is also used for elsewhere;
        // that overlap is accepted here the same way the status line's own
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

        // Always the last item - the follow-the-reply effect relies on it.
        item(key = REPLY_KEY) { Reply(reply, state.streaming, state.lastUserText) }
    }
}

/**
 * The line across the top of Home that says, in words, whether what is on
 * the screen can be trusted. Always shown. Not a setting.
 *
 * It used to live in the bar the 395a526 change hid by default, which left
 * Home with no words at all for Offline, Stale or Retry. The face cannot
 * carry that news: it deliberately holds still for the first seconds of an
 * outage, later settles into a state that means "nothing is wrong", and
 * never changes at all for a stale stream on a live socket. JarvisRuntime
 * counts on this line to say "reconnecting" instead - rule 4 blocks acting
 * on a stale stream, and a screen showing last-known data without saying so
 * is the one thing that rule cannot tolerate.
 *
 * The status words are the way to Checks, as before. A swipe down anywhere
 * on the line shows the navigation row and a swipe up hides it; the chevron
 * at the end does the same with a tap, for anyone who does not swipe and for
 * TalkBack, which cannot perform the swipe at all.
 */
@Composable
private fun StatusLine(
    state: HomeState,
    actions: HomeActions,
    navShown: Boolean,
    /** Null when the navigation row is always shown - nothing to toggle. */
    onNavToggle: ((Boolean) -> Unit)?,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    val thresholdPx = with(LocalDensity.current) { REVEAL_THRESHOLD.toPx() }
    val linked = state.link == LinkState.CONNECTED

    // Two different facts, never merged into one word: whether the stream is up,
    // and whether Jarvis is busy. Collapsing them is how a client ends up
    // showing "thinking" at a desktop that went away ten minutes ago.
    val (dot, label) = when {
        !linked -> chrome.badMark to (state.linkDetail ?: "Offline")
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
    // Words, not only the dot's colour: red and amber alone say nothing to
    // a colour-blind reader, and the dot is always paired with a word.
    val tone = when {
        !linked -> chrome.badInk
        state.stale -> chrome.warnInk
        else -> chrome.textHi
    }
    // The rest of the line - where requests run, what is waiting, which
    // model - only while the stream is live. After "Offline" or "Stale"
    // these would be last-known facts presented as current ones.
    val extras = if (linked && !state.stale) {
        buildList<String> {
            when (state.status?.lane?.lowercase()) {
                "local" -> add("Local")
                "cloud" -> add("Cloud")
            }
            if (state.pending.isNotEmpty()) add("${state.pending.size} waiting")
            state.status?.model?.let { add(it) }
        }.joinToString(" · ")
    } else {
        ""
    }

    Row(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .then(
                if (onNavToggle == null) {
                    Modifier
                } else {
                    Modifier.pointerInput(navShown) {
                        var total = 0f
                        detectVerticalDragGestures(
                            onDragStart = { total = 0f },
                            onDragEnd = {
                                if (!navShown && total > thresholdPx) onNavToggle(true)
                                if (navShown && total < -thresholdPx) onNavToggle(false)
                            },
                        ) { change, dragAmount ->
                            change.consume()
                            total += dragAmount
                        }
                    }
                },
            )
            .padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // The status is itself the way to the checks. You tap the thing that
        // is wrong to find out why, and it is present whether or not the
        // link is up.
        Row(
            Modifier
                .weight(1f)
                .clip(LocalRadii.current.insetShape)
                .pressable(onClick = actions.onOpenChecks)
                .heightIn(min = HANDLE_HEIGHT)
                .padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Dot(dot)
            Spacer(Modifier.width(10.dp))
            Column {
                Text(
                    buildAnnotatedString {
                        append(label)
                        if (extras.isNotEmpty()) {
                            withStyle(SpanStyle(color = chrome.textMid)) {
                                append(" · ")
                                append(extras)
                            }
                        }
                    },
                    style = MaterialTheme.typography.labelMedium,
                    color = tone,
                    // Two lines, not one: an offline reason from the runtime
                    // is a sentence, and it is the one thing on this line
                    // that says what to do.
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                // The progress line, AUTONOMY-PROPOSALS §3c: the backend's
                // own per-step sentence, under the state it belongs to. One
                // line, clipped - it is a status, not a log. Only on a live
                // link, because "Step 2/3" under "Stale" would be a claim
                // about work the phone cannot see.
                val detail = state.activityDetail
                if (detail != null && linked && !state.stale) {
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

        // Shown only while there is something to retry.
        if (!linked) {
            Quiet("Retry", onClick = actions.onReconnect)
        }

        if (onNavToggle != null) {
            NavToggle(shown = navShown, onToggle = onNavToggle)
        }
    }
}

/**
 * The tap alternative to swiping the status line: shows or hides the
 * navigation row. 48dp square, labelled for TalkBack with its state.
 */
@Composable
private fun NavToggle(shown: Boolean, onToggle: (Boolean) -> Unit) {
    val chrome = LocalChrome.current
    Box(
        Modifier
            .size(HANDLE_HEIGHT)
            .clip(LocalRadii.current.insetShape)
            .pressable(onClick = { onToggle(!shown) })
            .semantics {
                contentDescription = "Navigation"
                stateDescription = if (shown) "Shown" else "Hidden"
            },
        contentAlignment = Alignment.Center,
    ) {
        // A chevron rather than the pill: this one is a button, and it
        // points where the row will go - down to open, up to close. Drawn
        // in textMid, which is measured as text, so it clears the 3:1 a
        // control's only visible sign needs on every theme.
        Canvas(Modifier.size(width = 14.dp, height = 8.dp)) {
            val stroke = 2.dp.toPx()
            val top = if (shown) size.height else 0f
            val tip = if (shown) 0f else size.height
            val tipAt = Offset(size.width / 2f, tip)
            for (x in listOf(0f, size.width)) {
                drawLine(
                    color = chrome.textMid,
                    start = Offset(x, top),
                    end = tipAt,
                    strokeWidth = stroke,
                    cap = StrokeCap.Round,
                )
            }
        }
    }
}

/** Mind, Inbox, Appearance and Help - the part of the old bar that may hide. */
@Composable
private fun NavRow(state: HomeState, actions: HomeActions) {
    val chrome = LocalChrome.current
    // UI-AUDIT-2026-09-18 choice A1: icons + words, status separated
    // from navigation by a rule, Brain gets a real button, "Look"
    // becomes "Appearance". Four destinations, evenly weighted so the
    // row balances regardless of phone width.
    Column(Modifier.fillMaxWidth().background(chrome.surface1)) {
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

/**
 * The handle between the face and the conversation.
 *
 * Drag to resize. Tap to make the face small, and tap again to give it its
 * room back - neither is saved. Double-tap to go back to the default split.
 * TalkBack gets the same as a button plus "Bigger face", "Smaller face" and
 * "Reset face size" actions, because a drag is the one gesture a screen
 * reader cannot perform; before this the handle had no semantics at all.
 */
@Composable
private fun ResizeHandle(
    stateWords: String,
    tapLabel: String,
    dragState: DraggableState,
    onDragStart: () -> Unit,
    onDragEnd: () -> Unit,
    onTap: () -> Unit,
    onReset: () -> Unit,
    onNudge: (Float) -> Unit,
    modifier: Modifier = Modifier,
) {
    // The tap detector below is started once and outlives recompositions,
    // so it calls whatever the latest handlers are rather than the first.
    val latestTap by rememberUpdatedState(onTap)
    val latestReset by rememberUpdatedState(onReset)
    Box(
        modifier
            .height(HANDLE_HEIGHT)
            .draggable(
                state = dragState,
                orientation = Orientation.Vertical,
                onDragStarted = { onDragStart() },
                onDragStopped = { onDragEnd() },
            )
            // After draggable in the chain, so it sees each event first; a
            // drag past touch slop consumes the move and cancels the tap.
            .pointerInput(Unit) {
                detectTapGestures(
                    onDoubleTap = { latestReset() },
                    onTap = { latestTap() },
                )
            }
            .semantics {
                role = Role.Button
                contentDescription = "Face size"
                stateDescription = stateWords
                onClick(label = tapLabel) {
                    onTap()
                    true
                }
                customActions = listOf(
                    CustomAccessibilityAction("Bigger face") {
                        onNudge(FACE_STEP)
                        true
                    },
                    CustomAccessibilityAction("Smaller face") {
                        onNudge(-FACE_STEP)
                        true
                    },
                    CustomAccessibilityAction("Reset face size") {
                        onReset()
                        true
                    },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        HandlePill()
    }
}

/**
 * The small pill a drag handle shows, so "there is more here, drag me"
 * looks the same wherever it appears.
 *
 * chrome.hairlineFocus at full strength. It was textLo at 25-55% alpha,
 * measured at 1.3-2.3:1 against the background - below the 3:1 this
 * codebase's own rule (Chrome.hairlineFocus) sets for anything that is the
 * only visible sign a control is there.
 */
@Composable
private fun HandlePill() {
    Box(
        Modifier
            .width(36.dp)
            .height(4.dp)
            .clip(RoundedCornerShape(2.dp))
            .background(LocalChrome.current.hairlineFocus),
    )
}

/**
 * Hears a tap on the face without taking it from the face.
 *
 * FaceView answers its own touches - a press ring (detectTapGestures) and a
 * drag (detectDragGestures) - and detectTapGestures consumes the down.
 * Compose delivers the Main pass child first, and a clickable only starts on
 * a down nobody has consumed, so a clickable on or around the face never
 * sees a press that lands on the face: under the old pane-wide `pressable`,
 * only the empty well AROUND the face opened Mind, never the face itself.
 * (Checked against androidx's current TapGestureDetector.kt and Clickable.kt,
 * not against the exact version pinned in this build.)
 *
 * So this listens in the Initial pass, which runs parent first, and consumes
 * nothing: the face still draws its press ring, and a drag on the face -
 * which consumes the moves - cancels the tap here.
 */
private fun Modifier.tapThrough(label: String, onTap: () -> Unit): Modifier = this
    // Merged so TalkBack reads the face's own live description ("Jarvis is
    // idle") on the same node that offers the action.
    .semantics(mergeDescendants = true) {
        role = Role.Button
        onClick(label = label) {
            onTap()
            true
        }
    }
    .pointerInput(onTap) {
        awaitEachGesture {
            awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
            val up = waitForUpOrCancellation(PointerEventPass.Initial)
            if (up != null) onTap()
        }
    }

/**
 * The face, in its own pane above the conversation.
 *
 * Tapping the face opens Mind: it is the only thing on screen that is
 * obviously *Jarvis*, so it is the right door to what Jarvis is doing. Only
 * the face itself, and the caption under it - the pane around it is not a
 * button. It used to be: `pressable` on the whole pane made three quarters
 * of the screen one button that visibly shrank under a resting thumb, and a
 * stray tap there while picking the phone up left Home. The owner can also
 * turn the tap off entirely (HomeState.tapFaceOpensMind).
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
    showCaption: Boolean,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    // Inside the well the ground is always near-black (Chrome.wellIsLegal),
    // so on Daylight the light theme's dark ink would be unreadable here. A
    // dark theme's ink is what was measured against a ground like this one.
    val wellChrome = if (chrome.dark) chrome else Themes.REACTOR
    val opensMind = state.tapFaceOpensMind
    Box(
        modifier
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .clip(LocalRadii.current.shellShape)
            // The whole pane is the well, not just the square the face draws
            // in. Painting only that square left a hard-edged black box on
            // Daylight and empty chrome around it everywhere else.
            .background(chrome.well),
        contentAlignment = Alignment.Center,
    ) {
        CompositionLocalProvider(LocalChrome provides wellChrome) {
            Column(
                Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                // The chosen size, but never more than the room left once the
                // chip and caption below have theirs: weight(fill = false)
                // caps the height, so a pane dragged small shrinks the face
                // instead of pushing the caption out of the pane. FaceView
                // draws from its smaller side, so a short box stays round.
                Box(
                    Modifier
                        .weight(1f, fill = false)
                        .size(state.faceSize.sizeDp.dp)
                        .then(
                            if (opensMind) {
                                Modifier.tapThrough(label = "Open Mind", onTap = actions.onOpenBrain)
                            } else {
                                Modifier
                            },
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    FaceView(
                        state = state.faceState,
                        face = state.face,
                        bindings = state.bindings,
                        notches = state.attention.pending,
                        modifier = Modifier.fillMaxSize(),
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
                    TickRing(
                        minor = wellChrome.hairline,
                        major = wellChrome.hairlineStrong,
                        modifier = Modifier.matchParentSize(),
                    )
                }
                Gap(6)
                // The lane, which the phone parsed and threw away. "This left your
                // machine" is the single most consequential fact the UI carries and
                // it had no representation here at all.
                LaneChip(state.status)
                if (showCaption && opensMind) {
                    Gap(2)
                    Text(
                        "State of mind →",
                        style = MaterialTheme.typography.labelSmall,
                        color = wellChrome.textLo,
                        modifier = Modifier
                            .clip(LocalRadii.current.insetShape)
                            .pressable(onClick = actions.onOpenBrain)
                            .padding(horizontal = 10.dp, vertical = 4.dp),
                    )
                    Gap(2)
                } else {
                    Gap(6)
                }
            }
        }
    }
}

/**
 * A still ring of tick marks around the face - the bezel of the gauge the
 * face is set into.
 *
 * Still, and cheap on purpose: the face is the one thing on Home that moves.
 * The geometry is worked out once per size in drawWithCache, and the marks
 * sit in their own graphics layer, so the face redrawing underneath at up to
 * 120fps re-composites this layer without re-recording it. Drawn above the
 * face, near the edge of its box, well outside the face's own body (which
 * FaceView keeps within half the box's radius) - only the outer glow reaches
 * this far. Hairline colours, which are decorative by definition, and no
 * pointer input, so every touch goes straight through to the face.
 */
@Composable
private fun TickRing(minor: Color, major: Color, modifier: Modifier = Modifier) {
    Spacer(
        modifier
            .graphicsLayer {}
            .drawWithCache {
                val cx = size.width / 2f
                val cy = size.height / 2f
                val outer = size.minDimension / 2f * 0.96f
                val stroke = 1.dp.toPx()
                val longMark = 7.dp.toPx()
                val shortMark = 3.dp.toPx()
                val marks = List(TICKS) { i ->
                    val angle = i.toFloat() / TICKS * 2f * PI.toFloat()
                    val dx = sin(angle)
                    val dy = -cos(angle)
                    val inner = outer - if (i % 5 == 0) longMark else shortMark
                    Triple(
                        Offset(cx + dx * inner, cy + dy * inner),
                        Offset(cx + dx * outer, cy + dy * outer),
                        i % 5 == 0,
                    )
                }
                onDrawBehind {
                    for ((start, end, isMajor) in marks) {
                        drawLine(
                            color = if (isMajor) major else minor,
                            start = start,
                            end = end,
                            strokeWidth = stroke,
                        )
                    }
                }
            },
    )
}

@Composable
private fun LaneChip(status: StatusInfo?) {
    val chrome = LocalChrome.current
    val lane = status?.lane?.lowercase()
    val model = status?.model
    when (lane) {
        // violet-4 is the desktop's `--cloud`, and it means the same thing on
        // both: this is leaving the local lane.
        "cloud" -> Pill("Cloud" + (model?.let { " · $it" } ?: ""), color = chrome.cloudInk)
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

/**
 * The owner's last question and Jarvis's answer to it.
 *
 * The question is the "You" line: the composer is cleared on send, so an
 * answer used to sit on Home with nothing to say what it answered.
 *
 * The answer is laid out one paragraph per Text. As one Text, every publish
 * (twenty a second while streaming) measured and laid out the whole reply
 * again, so a long answer cost more per update the longer it got, on the
 * thread that also draws the face. Split on blank lines, a finished
 * paragraph's text stops changing, its Text skips, and only the paragraph
 * still being written is laid out again.
 */
@Composable
private fun Reply(reply: () -> String, streaming: Boolean, question: String?) {
    val chrome = LocalChrome.current
    val motion = LocalMotion.current
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val text = reply()
    AnimatedVisibility(
        visible = text.isNotBlank() || streaming || question != null,
        enter = fadeIn(motion.enter()),
        exit = fadeOut(motion.micro()),
    ) {
        Plate {
            if (question != null) {
                Kicker("You")
                Gap(4)
                Text(
                    question,
                    style = MaterialTheme.typography.bodyMedium,
                    color = chrome.textMid,
                    // A reminder of the question, not a transcript of it.
                    maxLines = 4,
                    overflow = TextOverflow.Ellipsis,
                )
                if (streaming || text.isNotBlank()) Gap(12)
            }
            if (streaming || (question != null && text.isNotBlank())) {
                Kicker("Jarvis", color = if (streaming) LocalAccent.current else null)
                Gap(6)
            }
            if (text.isBlank()) {
                // Nothing yet. "…" only while an answer is actually on its
                // way; a turn that ended with no text shows the question
                // alone rather than a placeholder that implies more is coming.
                if (streaming) {
                    Text(
                        "…",
                        style = MaterialTheme.typography.bodyLarge,
                        color = chrome.textHi,
                    )
                }
            } else {
                // Identity by position is right here: paragraphs are only
                // ever added at the end while a reply streams, so each index
                // keeps meaning the same paragraph.
                text.split(PARAGRAPH_BREAK).forEachIndexed { index, paragraph ->
                    if (index > 0) Gap(10)
                    Text(
                        paragraph,
                        style = MaterialTheme.typography.bodyLarge,
                        color = chrome.textHi,
                    )
                }
            }
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
