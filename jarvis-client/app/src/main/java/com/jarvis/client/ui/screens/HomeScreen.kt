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
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.widthIn
import com.jarvis.client.net.AnswerFeedback
import com.jarvis.client.net.AnswerMark
import com.jarvis.client.ui.parts.liveStatus
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
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
import androidx.compose.runtime.collectAsState
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
import com.jarvis.client.face.AnimalNow
import com.jarvis.client.face.Bindings
import com.jarvis.client.face.CritterFace
import com.jarvis.client.face.Face
import com.jarvis.client.face.FaceView
import com.jarvis.client.data.FaceSize
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.Attention
import com.jarvis.client.net.NoteCapture
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.StatusInfo
import com.jarvis.client.platform.PlatformReadiness
import com.jarvis.client.platform.PrivateClipboard
import com.jarvis.client.ui.approval.ApprovalCard
import com.jarvis.client.ui.parts.AppearanceIcon
import com.jarvis.client.ui.parts.Dot
import com.jarvis.client.ui.parts.FormattedAnswer
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.HelpIcon
import com.jarvis.client.ui.parts.InboxIcon
import com.jarvis.client.ui.parts.LiveIcon
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
    /**
     * "Tailscale (or Meshnet) is off on this phone", or null - shown under
     * a link that is down ([com.jarvis.client.LinkWords.vpnOffLine]).
     */
    val vpnLine: String? = null,
    val stale: Boolean,
    val activity: Activity,
    val faceState: FaceState,
    /**
     * Jarvis cannot be reached (`JarvisRuntime.faceOffline`): the face shows
     * STANDBY with its hollow ring, and says "Jarvis isn't connected".
     */
    val faceOffline: Boolean = false,
    /** The idle face is a focus session's Quiet (`JarvisRuntime.faceFocusQuiet`): TalkBack says so. */
    val faceFocusQuiet: Boolean = false,
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
     * The owner's Glow setting, 0..1 - only ever dimmer. FaceBlock multiplies
     * it with the theme's `Chrome.postScale` and hands it to FaceView.
     */
    val glow: Float = 1f,
    /**
     * The face moves at its calm pace: the owner chose Calm, or left Motion
     * on Follow and the phone asks for less animation. Worked out by
     * MainActivity (`MotionPref.calmFace`), passed straight to FaceView.
     */
    val calmMotion: Boolean = false,
    /**
     * A serious moment (`JarvisRuntime.faceSerious`, the `wellbeing` event,
     * docs/JARVIS-API.md section 38.1): the animal faces hold a calm, plain
     * pose while a crisis answer is given or spoken. Passed to FaceView.
     */
    val faceSerious: Boolean = false,
    /** "Keep the animal still" (`Look.stillAnimal`), passed to FaceView. */
    val stillAnimal: Boolean = false,
    /**
     * The owner's last question, shown as a "You" line above the reply so an
     * answer is never on screen without what it answers. Memory only - see
     * [com.jarvis.client.net.ChatSession.question]; nothing writes it to disk.
     */
    val lastUserText: String? = null,
    /**
     * The right/wrong mark buttons for the answer on screen, or null to show
     * none - the answer carried no id (`turn_id`) the desktop could file a
     * mark against. See [com.jarvis.client.net.Feedback.viewFor].
     */
    val answerFeedback: AnswerFeedback? = null,
    /**
     * How many finished questions and answers the next question will carry
     * with it - see [com.jarvis.client.net.ChatHistory]. Above zero, Home
     * offers "New conversation". Memory only; nothing writes it to disk.
     */
    val conversationTurns: Int = 0,
    /**
     * The finished questions and answers of this conversation above the one
     * on screen, oldest first (the owner's decision, 2026-09-28: the whole
     * conversation as a scrollable thread) - see
     * [com.jarvis.client.net.ChatSession.thread]. Memory only.
     */
    val thread: List<com.jarvis.client.net.ChatHistory.Exchange> = emptyList(),
    /**
     * One quiet line about the chat itself, or null - a new conversation
     * after 30 quiet minutes, a chat carried on, the chat deleted elsewhere,
     * a temporary chat started or ended, "New conversation" - read out by
     * TalkBack ([com.jarvis.client.net.ChatSession.chatNote]).
     */
    val chatNote: String? = null,
    /**
     * This conversation read outside text (a chat carried on that did, or one
     * that read a page or an email since): a line under the reply says so for
     * as long as the conversation lasts, not only until the next question
     * (the second chat audit, phone C4).
     */
    val readOutside: Boolean = false,
    /**
     * Set once the chat has gone quiet for 30 minutes: "your next question
     * starts a new conversation", instead of "follows on from the last 3"
     * (the second chat audit, phone C1).
     */
    val idleNextLine: String? = null,
    /**
     * What the answer on its way is waiting on, in words - "Waiting for your
     * approval…" while a card is up on the desktop - or null. Shown in place
     * of "…". See [com.jarvis.client.net.ChatSession.waiting].
     */
    val chatWaiting: String? = null,
    /**
     * One line under a finished answer: cut short at the length limit, and/or
     * written by a cloud model. See [com.jarvis.client.net.ChatSession.answerNote].
     */
    val answerNote: String? = null,
    /**
     * The crisis help line (`jarvis_wellbeing.py`, the owner's decision of
     * 2026-09-27; docs/JARVIS-API.md section 38): true only while the
     * answer on screen is Jarvis's help message after the owner mentioned
     * wanting to hurt themselves, so [Reply] draws it as a calm, plain
     * panel instead of an ordinary bubble. See
     * [com.jarvis.client.net.ChatSession.crisis].
     */
    val crisisAnswer: Boolean = false,
    /**
     * "A cloud model could give this one a second look." - the lane
     * [com.jarvis.client.net.CloudOffer] read off the answer on screen's
     * route, or null. See [com.jarvis.client.net.ChatSession.cloudOffer].
     */
    val cloudOffer: String? = null,
    /**
     * The Undo strip for the newest inbox tidy still open to it ("Inbox tidy
     * by voice", 2026-09-28; docs/JARVIS-API.md section 95), or null when
     * there is none. Counts and the PC's own words - never a sender or a
     * subject. See [com.jarvis.client.net.InboxTidy.strip] for what it says
     * while the lists are hidden and on a stale link.
     */
    val inboxTidy: com.jarvis.client.net.InboxTidy.Strip? = null,
    /** An Undo of [inboxTidy] is on its way - the button waits. */
    val inboxTidyBusy: Boolean = false,
    /**
     * Whether the quick-note field is open - the home-screen widget's Note
     * button opens it. See [QuickNotePlate].
     */
    val quickNoteOpen: Boolean = false,
    /**
     * Offer the Photo button: the PC says its second graphics card's
     * Pictures feature is working, or that it reads the words in a picture
     * itself ([com.jarvis.client.net.SecondCard.picturesTaken], 2026-09-26).
     * Hidden otherwise - without either the everyday model would get a
     * picture it cannot see.
     */
    val pictureOffered: Boolean = false,
    /**
     * Offer the "Notifications" button: reading phone notifications is on
     * ([com.jarvis.client.JarvisRuntime.phoneNotificationsAllowed]) AND at
     * least one has actually been captured
     * ([com.jarvis.client.data.CapturedNotifications.sharedText] is not
     * null). Hidden otherwise - a button that would attach nothing is not
     * an offer, and this never appears at all while the setting is off.
     */
    val notificationsAttachable: Boolean = false,
    /**
     * The line for a picture waiting to go with the next question, or null
     * when none is attached. See [com.jarvis.client.net.ChatPicture]. The
     * picture itself is never in this state - only its size, in words.
     */
    val pictureLine: String? = null,
    /** True while the PC reads the attached picture for "Photo to reminder". */
    val photoFinding: Boolean = false,
    /**
     * The chip for text shared from another app, waiting to go with the next
     * question as its own message ("Shared text · 1,204 characters"), or null
     * when none is held. See [com.jarvis.client.net.Provenance]. The text
     * itself is not in this state - only its size, in words.
     */
    val sharedLine: String? = null,
    /**
     * The chip for a look at this phone's screen, waiting to go with the next
     * question ("Looked at: Chrome screen · words only"), or null. Only the
     * app's name and how it was read - never the words themselves. See
     * [com.jarvis.client.net.ScreenLook].
     */
    val lookLine: String? = null,
    /**
     * The sign for "Watch with me" on the PC ("Jarvis is watching", paused, or
     * how long is left), or null while it is off. Words only - never anything
     * from the screen. See [com.jarvis.client.net.ScreenRules.sign].
     */
    val watchSign: com.jarvis.client.net.ScreenRules.Sign? = null,
    /**
     * "Watch this phone with me" is offered: the Security switch "Let Jarvis read
     * this phone's screen" is on. Off, Home shows nothing about it.
     */
    val phoneWatchOffered: Boolean = false,
    /** The sign while THIS phone's screen is being watched, or null. See [com.jarvis.client.net.ScreenWatch.sign]. */
    val phoneWatchSign: com.jarvis.client.net.ScreenRules.Sign? = null,
    /** Android's Usage access is on for Jarvis (what "Watch this phone" needs). */
    val usageAccess: Boolean = false,
    /** True while a picked photo is being made small enough to send. */
    val pictureBusy: Boolean = false,
    /**
     * Which note apps the desktop said are set up, as last asked, or null
     * before it answered. For the line under the chat box while a `#log` /
     * `#obs` / `#joplin` line is typed ([NoteCapture.chip]).
     */
    val noteTargets: NoteCapture.Targets? = null,
    /**
     * "A newer build of this app is on GitHub", or null
     * ([com.jarvis.client.net.UpdateCheck]). One quiet line under the status
     * line, with a button to the release page. Never a failure: those are on
     * Checks.
     */
    val updateLine: String? = null,
    /**
     * The one-time "Background restart" offer after the first pairing
     * (phone walk-through C9, 2026-09-27), in the Checks card's own words, or
     * null. A line under the status line with two buttons; it never blocks
     * anything, and either button ends it for good.
     */
    val keepAliveOffer: String? = null,
    /**
     * A temporary chat is on ([com.jarvis.client.net.TemporaryChat], the
     * owner's decision of 2026-09-25): the marker above the chat box, and
     * its one line while the chat is empty.
     */
    val temporary: Boolean = false,
    /**
     * The facts the answer on screen used, by id, for "Used 2 memories"
     * under it ([com.jarvis.client.net.MemoryUsed]). Ids only.
     */
    val usedIds: List<Long> = emptyList(),
    /**
     * The answer on screen's own id ([com.jarvis.client.net.Feedback];
     * already read for the right/wrong mark) - also what "Where this came
     * from" fetches by, feasibility I42/I132
     * ([com.jarvis.client.net.ChatSources]). Null for an older PC, or
     * before recording failed.
     */
    val answerTurnId: String? = null,
    /**
     * Security's "Hide memory lists and chat history" is hiding the memory
     * lists now - the facts under "Used 2 memories" are one of them, and so
     * is "Where this came from" (the same gate, not a second one).
     */
    val memoryHidden: Boolean = false,
    /** The Show under a hidden list is asking the phone's lock now. */
    val showPrivateBusy: Boolean = false,
    /**
     * The failure [notice] says, in plain words: its ONE fix button and its
     * scrubbed Details ([com.jarvis.client.net.PlainErrors]). Null when the
     * notice is anything else.
     */
    val noticeProblem: com.jarvis.client.net.PlainErrors.Shown? = null,
    /** Security's "Swipe to approve or deny" (on by default). */
    val swipeDecides: Boolean = true,
    /**
     * Lockdown is on (backend jarvis_asks_first.py, 2026-09-28): every way
     * out of the PC asks first, or has stopped. Home says so at the top -
     * the desktop bar's strip, in the phone's place.
     * [com.jarvis.client.JarvisRuntime.lockdown].
     */
    val lockdown: Boolean = false,
)

/**
 * Home's notice: [Notice], with a failure's one fix button and its "Details"
 * (PlainErrors), or "Open screen-lock settings" when the notice is a risky
 * approval refused for want of a screen lock.
 */
@Composable
private fun HomeNotice(state: HomeState, actions: HomeActions) {
    val text = state.notice ?: return
    val problem = state.noticeProblem
    if (problem == null && SecurityRules.offersLockSettings(text)) {
        Notice(
            text,
            actions.onDismissNotice,
            actionLabel = SecurityRules.OPEN_LOCK_SETTINGS,
            onAction = actions.onOpenLockSettings,
        )
        return
    }
    if (problem == null && com.jarvis.client.net.SignedApproval.offersTurnOn(text)) {
        Notice(
            text,
            actions.onDismissNotice,
            actionLabel = com.jarvis.client.net.SignedApproval.TURN_ON,
            onAction = actions.onTurnOnSignedApprovals,
        )
        return
    }
    Notice(
        text,
        actions.onDismissNotice,
        details = problem?.details,
        actionLabel = problem?.button,
        onAction = noticeAction(problem, actions),
    )
}

@Immutable
data class HomeActions(
    val onDraftChange: (String) -> Unit,
    val onSend: () -> Unit,
    val onInterrupt: () -> Unit,
    val onApprove: (PendingItem) -> Unit,
    val onDeny: (PendingItem) -> Unit,
    /** A note before the first decision - AUTONOMY-PROPOSALS.md §3b. See ApprovalCard. */
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
     * AUTONOMY-PROPOSALS.md §3d; see [com.jarvis.client.JarvisRuntime.pauseTask].
     */
    val onPauseTask: suspend () -> Unit = {},
    val onResumeTask: suspend () -> Unit = {},
    val onStopTask: suspend () -> Unit = {},
    val onInjectTaskNote: suspend (note: String) -> Unit = {},
    /**
     * "Stop everything" - [com.jarvis.client.JarvisRuntime.stopEverything]:
     * the phone's speech, then the PC's `POST /api/stop_all`. Never held on
     * a stale link.
     */
    val onStopEverything: suspend () -> Unit = {},
    /**
     * The owner finished changing the split - a drag let go, a screen-reader
     * "Bigger face" / "Smaller face", or a double-tap back to the default.
     * Called once per change, never per frame, with the new fraction. The
     * caller saves it and hands it back as [HomeState.faceFraction].
     */
    val onFaceFractionCommitted: (Float) -> Unit = {},
    /** Jarvis Live: open its screen (ui/screens/LiveScreen.kt), where it starts and ends. */
    val onOpenLive: () -> Unit = {},
    /**
     * The owner tapped Right or Wrong on the answer [turnId]. The runtime
     * works out whether that sets, changes or takes back the mark, and sends
     * nothing while the link is stale.
     */
    val onMarkAnswer: (turnId: String, tapped: AnswerMark) -> Unit = { _, _ -> },
    /**
     * "Try the cloud model" on the answer on screen's own cloud offer
     * ([com.jarvis.client.net.ChatSession.tryCloudForLast]) - a genuinely
     * new turn, one tap, never a standing choice.
     */
    val onTryCloud: () -> Unit = {},
    /** Dismisses [HomeState.cloudOffer] without asking anything. */
    val onDismissCloudOffer: () -> Unit = {},
    /**
     * Undo the inbox tidy on [HomeState.inboxTidy] - one tap, no card
     * ([com.jarvis.client.JarvisRuntime.inboxTidyUndoDetached]). Held on a
     * stale link and while the lists are hidden: the strip disables the button.
     */
    val onInboxUndo: () -> Unit = {},
    /**
     * Forget the conversation and start afresh: the next question goes on
     * its own, with nothing before it. Clears the question and answer on
     * screen. Touches nothing the desktop has learned.
     */
    val onNewConversation: () -> Unit = {},
    /** "Earlier chats": History, where "Continue this chat" carries one on here. */
    val onEarlierChats: () -> Unit = {},
    /** The line about the chat itself, dismissed. */
    val onDismissChatNote: () -> Unit = {},
    /**
     * File the owner's own words in Logseq ("logseq"), Joplin ("joplin") or
     * Obsidian ("obsidian") through the desktop -
     * [com.jarvis.client.JarvisRuntime.fileNote]. True once the desktop
     * accepted it (filed, or waiting for approval); false leaves the typed
     * text where it is.
     */
    val onFileNote: suspend (target: String, text: String) -> Boolean = { _, _ -> false },
    /**
     * Which note apps the desktop is set up for -
     * [com.jarvis.client.JarvisRuntime.noteTargets]. Asked when the plate
     * opens; only those get a button.
     */
    val onLoadNoteTargets: suspend () -> NoteCapture.Targets =
        { NoteCapture.Targets.Unknown("not checked yet") },
    /** Open or close the quick-note field. */
    val onQuickNoteOpenChange: (Boolean) -> Unit = {},
    /** Open Android's photo picker. No storage permission: the picker hands over one photo. */
    val onAttachPicture: () -> Unit = {},
    /** Drop the attached picture without sending it. */
    val onRemovePicture: () -> Unit = {},
    /**
     * Puts the recent captured notifications' redacted text into the same
     * "shared text" chip the Share sheet and the clipboard hotkey use
     * ([com.jarvis.client.data.CapturedNotifications.sharedText]) - the
     * owner still presses Send themselves, exactly like any other shared
     * text; nothing here reaches a chat on its own.
     */
    val onAttachNotifications: () -> Unit = {},
    /**
     * "Photo to reminder": send the attached picture to the PC, which
     * PROPOSES a reminder ([com.jarvis.client.net.PhotoReminder]). Sets
     * nothing up.
     */
    val onFindDateInPicture: () -> Unit = {},
    /** Drop the shared text without sending it. */
    val onDropShared: () -> Unit = {},
    /** "Forget it": throw the held look at the screen away without asking anything. */
    val onForgetLook: () -> Unit = {},
    /** End the PC's "Watch with me". Never held on a stale link, never a card. */
    /** Returns a plain line when the PC could not be reached, else null. */
    val onStopWatching: suspend () -> String? = { null },
    /** The owner's tap on "Watch this phone with me": Android asks its own question next. */
    val onStartPhoneWatch: () -> Unit = {},
    /** Ends Watch on this phone. Never held on a stale link, never a card. */
    val onStopPhoneWatch: suspend () -> Unit = {},
    /** Opens Android's Usage access screen. */
    val onOpenUsageAccess: () -> Unit = {},
    /** Open the release page in the browser. Downloads nothing itself. */
    val onOpenUpdate: () -> Unit = {},
    /**
     * Open Android's own screen-lock settings - offered beside the notice
     * that a risky approval was refused because this phone has no screen
     * lock ([SecurityRules.offersLockSettings]; the owner's "no lock, no
     * risky approval", 2026-09-25).
     */
    val onOpenLockSettings: () -> Unit = {},
    /**
     * The one button beside the notice "Risky approvals from this phone need
     * to be signed...": makes the approval key and asks the PC for its card
     * ([com.jarvis.client.net.SignedApproval.offersTurnOn]).
     */
    val onTurnOnSignedApprovals: () -> Unit = {},
    /**
     * Start or end a temporary chat - a new conversation either way
     * ([com.jarvis.client.JarvisRuntime.setTemporaryChat]).
     */
    val onToggleTemporary: () -> Unit = {},
    /** Read the words of these facts from the PC, by id ([com.jarvis.client.JarvisRuntime.memoryUsed]). */
    val onLoadUsed: suspend (List<Long>) -> com.jarvis.client.net.MemoryUsed.Read =
        { com.jarvis.client.net.MemoryUsed.Read.Missing },
    /** Forget ONE fact, after the confirm ([com.jarvis.client.JarvisRuntime.forgetAutoFact]). */
    val onForgetUsed: suspend (Long) -> Pair<Boolean, String> = { false to "" },
    /**
     * "Where this came from" (feasibility I42/I132): this answer's own
     * reading-tool receipts and its quote check, by turn_id
     * ([com.jarvis.client.JarvisRuntime.chatSources]).
     */
    val onLoadSources: suspend (String?) -> com.jarvis.client.net.ChatSources.Read =
        { com.jarvis.client.net.ChatSources.Read.Missing },
    /** Show a hidden memory list, after the phone's lock says it is the owner. */
    val onShowPrivate: () -> Unit = {},
    /** "Try again" under a failed question: ask the same question again. */
    val onRetryQuestion: () -> Unit = {},
    /** The offer's "Keep link alive": Android's own battery dialog. */
    val onKeepLinkAlive: () -> Unit = {},
    /** The offer's "Not now". */
    val onDismissKeepAlive: () -> Unit = {},
    /**
     * "Playing on your PC" (2026-09-28): what is playing, in the PC's own
     * sentence, or null ([com.jarvis.client.JarvisRuntime.pcMedia]). A read.
     */
    val onPcMedia: suspend () -> String? = { null },
    /**
     * ONE media button on the PC - play, pause, next or previous
     * ([com.jarvis.client.JarvisRuntime.pcMediaControl]). No card; refused on
     * a stale link. @return the sentence to show.
     */
    val onPcMediaControl: suspend (String) -> String = { "" },
)

/**
 * What a failure notice's ONE fix button does, by the contract file's action
 * ([com.jarvis.client.net.PlainErrors]): ask a failed question again or
 * reconnect, open Checks (the connection settings) or Mind (the model).
 * Null for no button.
 */
internal fun noticeAction(
    problem: com.jarvis.client.net.PlainErrors.Shown?,
    actions: HomeActions,
): (() -> Unit)? {
    val p = problem ?: return null
    if (p.button.isEmpty()) return null
    return when (p.action) {
        com.jarvis.client.net.PlainErrors.RETRY -> if (p.chat) actions.onRetryQuestion else actions.onReconnect
        com.jarvis.client.net.PlainErrors.RECONNECT -> actions.onReconnect
        com.jarvis.client.net.PlainErrors.CONNECTION -> actions.onOpenChecks
        com.jarvis.client.net.PlainErrors.MODELS -> actions.onOpenBrain
        else -> null
    }
}

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
    /**
     * Jarvis's voice at the moment being heard - `Speaker.mouthNow`, see
     * FaceView's `speechMouth`. Read by the face's frame loop only.
     */
    speechMouth: (FloatArray) -> Boolean = { false },
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

    // ---- Full screen (FaceSize.FULL_SCREEN): the face and a microphone ----
    //
    // The chat and the typing box step aside, but never over something that
    // needs the owner: an approval waiting, or a task running or paused,
    // brings the normal layout straight back, because a card nobody can see
    // is a decision nobody can make. So does a desktop that offers no voice -
    // a microphone that cannot be used is not a way to talk to Jarvis. The
    // status line stays on screen throughout; it is not something any size
    // can hide.
    //
    // "Show chat" is a peek for this visit, not a setting: keyed on the size,
    // so picking Full screen again starts in full screen, and saveable, so
    // turning the phone mid-peek does not snap the chat away.
    var peekChat by rememberSaveable(state.faceSize) { mutableStateOf(false) }
    val taskShowing = state.activity == Activity.WORKING || state.activity == Activity.PAUSED
    val voiceMode = state.faceSize.voiceOnly && state.voiceOffered &&
        !hasPending && !taskShowing && !peekChat

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
        state.updateLine?.let { UpdateLine(it, actions.onOpenUpdate) }
        // Jarvis Live's sign on Home while it is on (here or on the PC) -
        // the review's C2: Live was invisible here, and hard to find.
        HomeLiveStrip(onOpen = actions.onOpenLive)
        state.keepAliveOffer?.let { KeepAliveOffer(it, actions.onKeepLinkAlive, actions.onDismissKeepAlive) }

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
        // "Continue this chat" lands on the reply plate, where the carried-on
        // chat and its note are (the second chat audit, phone C7); nothing is
        // scrolled when a notification has sent the owner to a card.
        val carriedOn = state.thread.isNotEmpty() && state.lastUserText == null
        LaunchedEffect(carriedOn, state.chatNote) {
            if (carriedOn && state.focusApproval == null) {
                listState.animateScrollToItem((listState.layoutInfo.totalItemsCount - 1).coerceAtLeast(0))
            }
        }

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
        if (voiceMode) {
            FaceBlock(
                state, actions, micLevel, speechLevel,
                speechMouth = speechMouth,
                showCaption = true,
                modifier = Modifier.weight(1f).fillMaxWidth(),
            )
            VoiceBar(state, actions, reply, micLevel, onShowChat = { peekChat = true })
        } else {
            if (state.faceSize.hidden) {
                // No face at all: the conversation takes the whole room, and
                // there is no split, so no handle either. Nothing about the
                // face is composed, so its frame loop does not run.
                ConversationList(
                    state = state,
                    actions = actions,
                    reply = reply,
                    listState = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                )
            } else {
                Layout(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    content = {
                        FaceBlock(
                            state, actions, micLevel, speechLevel,
                            speechMouth = speechMouth,
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
            }
            if (peekChat && state.faceSize.voiceOnly && state.voiceOffered) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .background(LocalChrome.current.surface1)
                        .padding(horizontal = 12.dp),
                    contentAlignment = Alignment.CenterEnd,
                ) {
                    Quiet("Back to full screen", onClick = { peekChat = false })
                }
            }
            Composer(state, draft, actions, micLevel)
        }
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
    val motion = LocalMotion.current
    LazyColumn(
        state = listState,
        modifier = modifier,
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        // "Stop everything" (the owner's decision of 2026-09-25; the
        // desktop's Alt+Shift+X). Shown whenever Jarvis is doing anything -
        // on the PC, or talking on this phone - and never held on a stale
        // link: see JarvisRuntime.stopEverything.
        val busy = (state.activity != Activity.IDLE && state.activity != Activity.ERROR) ||
            state.streaming || state.voicePhase == VoiceSession.Phase.SPEAKING
        if (busy) {
            item(key = "stop-everything") { StopEverythingPlate(actions) }
        }
        // Lockdown (2026-09-28): said at the top while it is on. Turning it
        // off is the PC's alone, so there is no button here.
        if (state.lockdown) {
            item(key = "lockdown") { LockdownPlate() }
        }
        // "Jarvis is watching" (owner, 2026-09-28): the PC's Watch with me,
        // said here too, with Stop. Stop is never held on a stale link.
        if (state.watchSign != null) {
            item(key = "pc-watching") { PcWatchingPlate(state.watchSign, actions.onStopWatching, pcScreen = true) }
        }
        // ...and the same for THIS phone's screen ("Watch this phone with me").
        if (state.phoneWatchSign != null) {
            item(key = "phone-watching") { PcWatchingPlate(state.phoneWatchSign, { actions.onStopPhoneWatch(); null }) }
        } else if (state.phoneWatchOffered) {
            item(key = "phone-watch-start") { PhoneWatchStartPlate(state, actions) }
        }
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

        item(key = "quick-note") { QuickNotePlate(open = state.quickNoteOpen, actions = actions) }

        // "Playing on your PC" (2026-09-28): play, pause, next, previous -
        // greyed while the link is stale (rule 4), no card.
        item(key = "pc-media") {
            PcMediaPlate(
                canAct = state.link == LinkState.CONNECTED && !state.stale,
                actions = actions,
            )
        }

        // "Inbox tidy by voice" (2026-09-28): ten minutes of Undo after a
        // tidy card was approved. A strip, not a card - it approves nothing.
        state.inboxTidy?.let { strip ->
            item(key = "inbox-tidy") {
                InboxTidyPlate(strip, busy = state.inboxTidyBusy, onUndo = actions.onInboxUndo)
            }
        }

        if (state.notice != null) {
            item(key = "notice") { HomeNotice(state, actions) }
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
                Column {
                    Kicker(
                        if (state.pending.size == 1) "Waiting on you" else "${state.pending.size} waiting on you",
                        color = chrome.warnInk,
                    )
                    // With several cards, said once here instead of under every
                    // card, where the same line repeated down the list. A single
                    // card keeps it in its own footer. Wording only: it gates
                    // nothing.
                    if (state.pending.size > 1) {
                        Gap(4)
                        Text(
                            "Nothing runs until you decide.",
                            style = MaterialTheme.typography.labelSmall,
                            color = chrome.textMid,
                        )
                    }
                }
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
                    swipeAllowed = state.swipeDecides,
                    showFooter = state.pending.size == 1,
                    // UI-AUDIT-2026-09-26 item 6: a new card fades in, and the
                    // cards below glide up to fill the gap left by one that
                    // is decided (Compose's own built-in item animation - the
                    // "idiomatic equivalent" the item asks for where a direct
                    // port of the desktop's slide isn't this list's job).
                    // `motion.enter()` is the same 200ms/ease token the
                    // desktop's own card-in animation uses, and it collapses
                    // to 0ms under reduced motion like every other use of it.
                    modifier = Modifier.animateItem(
                        fadeInSpec = motion.enter(),
                        fadeOutSpec = motion.enter(),
                        placementSpec = motion.enter(),
                    ),
                )
            }
        }

        // Always the last item - the follow-the-reply effect relies on it.
        item(key = REPLY_KEY) {
            Reply(
                reply,
                state.streaming,
                state.lastUserText,
                feedback = state.answerFeedback,
                // The same test every other write on the phone uses: a mark is
                // not an approval, but it is still sent to the desktop, and
                // nothing is sent over a link that cannot be confirmed live.
                canMark = state.link == LinkState.CONNECTED && !state.stale,
                onMark = actions.onMarkAnswer,
                conversationTurns = state.conversationTurns,
                onNewConversation = actions.onNewConversation,
                // Hidden while "Hide memory lists and chat history" hides the lists:
                // the thread is the chat's own words (the owner, 2026-09-28).
                thread = if (state.memoryHidden) emptyList() else state.thread,
                readOutside = state.readOutside,
                idleNextLine = state.idleNextLine,
                waiting = state.chatWaiting,
                note = state.answerNote,
                crisis = state.crisisAnswer,
                cloudOffer = state.cloudOffer,
                onTryCloud = actions.onTryCloud,
                onDismissCloudOffer = actions.onDismissCloudOffer,
                used = UsedAnswer(
                    ids = state.usedIds,
                    canAct = state.link == LinkState.CONNECTED && !state.stale,
                    hidden = state.memoryHidden,
                    showBusy = state.showPrivateBusy,
                    onShow = actions.onShowPrivate,
                    load = actions.onLoadUsed,
                    forget = actions.onForgetUsed,
                ),
                sources = SourcesAnswer(
                    turnId = state.answerTurnId,
                    hidden = state.memoryHidden,
                    load = actions.onLoadSources,
                ),
            )
        }
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
        state.stale -> chrome.warnMark to "Catching up…"
        else -> when (state.activity) {
            Activity.LISTENING -> chrome.warnMark to "Listening"
            Activity.THINKING, Activity.WORKING -> accent to "Thinking"
            Activity.PAUSED -> chrome.warnMark to "Paused"
            Activity.SPEAKING -> accent to "Speaking"
            Activity.ERROR -> chrome.badMark to "Error on the desktop"
            else -> chrome.okMark to when (state.power) {
                "quiet" -> "Connected · quiet"
                "standby" -> "Connected · standby"
                else -> "Connected"
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
                // Why the link is most likely down, when Android says no
                // VPN is up at all (phone walk-through N1, 2026-09-27): the
                // phone reaches the PC only through Tailscale or Meshnet.
                val vpnLine = state.vpnLine
                if (vpnLine != null && !linked) {
                    Text(
                        vpnLine,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.warnInk,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
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

        // Shown only while there is something to retry: offline, and also
        // "Catching up…" (phone walk-through, 2026-09-27). A link that is up
        // but has gone quiet - often a half-dead socket after the phone slept
        // - used to offer nothing to tap, and could sit there until a 90
        // second read timeout noticed. Retry is the same forced reconnect as
        // offline; it approves nothing, and acting stays blocked until the
        // link is trusted again (rule 4).
        if (!linked || state.stale) {
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
                label = "Brain",
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
                icon = { LiveIcon(chrome.textMid) },
                label = "Live",
                onClick = actions.onOpenLive,
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
 * A newer build of this app, when there is one (net/UpdateCheck.kt). Under
 * the status line rather than in the conversation: it is about the app, not
 * about Jarvis, and it must not push the approval cards down. Not inside
 * [NavRow] either, which is hidden by default.
 */
/**
 * Jarvis Live on Home (the review of 2026-09-28, C2): "Jarvis Live · 24 min
 * left" with End Live and Open while it is on here; "Jarvis Live is on your
 * PC" with Move it here while it runs there. Fixed words only. The talk
 * button meanwhile says Live is already listening (VoiceSession.begin).
 */
@Composable
private fun HomeLiveStrip(onOpen: () -> Unit) {
    val status by com.jarvis.client.JarvisRuntime.liveStatus.collectAsState()
    val pending by com.jarvis.client.JarvisRuntime.pending.collectAsState()
    val stale by com.jarvis.client.JarvisRuntime.stale.collectAsState()
    val rules = com.jarvis.client.voice.LiveRules
    val on = rules.onHere(status)
    val cardHolds = remember(pending, status) { com.jarvis.client.JarvisRuntime.liveCardHolds() }
    val sign = rules.sign(status, stale = stale, cardShown = cardHolds, endedAgo = Int.MAX_VALUE)
    // On here, or on the PC; never an old end.
    if (!sign.show || (!on && !sign.move)) return
    val chrome = LocalChrome.current
    Row(
        Modifier.fillMaxWidth().background(chrome.surface1).padding(start = 16.dp, end = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
            Text(sign.title, style = MaterialTheme.typography.labelLarge, color = chrome.textHi)
            if (sign.detail.isNotEmpty()) {
                Text(sign.detail, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
            }
        }
        if (on) Quiet(rules.END_LIVE, onClick = { com.jarvis.client.JarvisRuntime.liveEndNow("owner") })
        Quiet(if (sign.move) "Move it here" else "Open", onClick = onOpen)
    }
}

@Composable
private fun UpdateLine(line: String, onOpen: () -> Unit) {
    val chrome = LocalChrome.current
    Row(
        Modifier.fillMaxWidth().background(chrome.surface1).padding(start = 16.dp, end = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            line,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
            modifier = Modifier.weight(1f),
        )
        Quiet("Release page", onClick = onOpen)
    }
}

/**
 * The one-time "Background restart" offer, after the first pairing (phone
 * walk-through C9, 2026-09-27). The same words and button as the Checks
 * card ([PlatformReadiness]), where it can still be found later. Where
 * [UpdateLine] sits, for the same reason: it is about this phone, and it
 * must not push the approval cards down.
 */
@Composable
private fun KeepAliveOffer(line: String, onKeep: () -> Unit, onNotNow: () -> Unit) {
    val chrome = LocalChrome.current
    Column(
        Modifier.fillMaxWidth().background(chrome.surface1).padding(start = 16.dp, end = 8.dp, top = 6.dp),
    ) {
        Text(
            PlatformReadiness.BACKGROUND_RESTART,
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textHi,
        )
        Text(line, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Quiet(PlatformReadiness.KEEP_LINK_ALIVE, onClick = onKeep)
            Quiet("Not now", color = chrome.textMid, onClick = onNotNow)
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
 *
 * [character]: the face is an animal or the robot AND is in a state where a
 * long press pets it (awake and connected; see the caller) - a long press
 * there is petting, so it does not open the Brain
 * (AnimalNow.pressOpensBrain says when a press still opens it).
 */
private fun Modifier.tapThrough(label: String, character: Boolean, onTap: () -> Unit): Modifier = this
    // Merged so TalkBack reads the face's own live description ("Jarvis is
    // idle") on the same node that offers the action.
    .semantics(mergeDescendants = true) {
        role = Role.Button
        onClick(label = label) {
            onTap()
            true
        }
    }
    .pointerInput(onTap, character) {
        awaitEachGesture {
            val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
            val up = waitForUpOrCancellation(PointerEventPass.Initial)
            // A long press on an animal is petting it (the owner's decision
            // of 2026-09-28: "a long press on the phone that does not open
            // Brain"), so there only a short tap opens it - held for less
            // than the petting hold, the same threshold FaceView pets at.
            // With Petting off, or on any other face, every tap opens it, as
            // before. The switch is read as the finger lifts.
            if (up != null && AnimalNow.pressOpensBrain(up.uptimeMillis - down.uptimeMillis, character)) onTap()
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
    speechMouth: (FloatArray) -> Boolean,
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
                //
                // Extra large and Full screen take ALL of that room instead
                // (weight with fill), so the face grows with the pane rather
                // than stopping at 260dp. Still round for the same reason.
                Box(
                    Modifier
                        .then(
                            if (state.faceSize.fill) {
                                Modifier.weight(1f).fillMaxWidth()
                            } else {
                                Modifier
                                    .weight(1f, fill = false)
                                    .size(state.faceSize.sizeDp.dp)
                            },
                        )
                        .then(
                            if (opensMind) {
                                Modifier.tapThrough(
                                    label = "Open the Brain",
                                    // A long press pets only where the pose lets it:
                                    // awake and connected. During an approval, an error,
                                    // standby or offline the animal ignores petting, so
                                    // the press must still open the Brain.
                                    character = state.face is CritterFace &&
                                        !state.faceOffline &&
                                        com.jarvis.client.face.CritterPose.awake(state.faceState),
                                    onTap = actions.onOpenBrain,
                                )
                            } else {
                                Modifier
                            },
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    FaceView(
                        state = state.faceState,
                        offline = state.faceOffline,
                        focusQuiet = state.faceFocusQuiet,
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
                        // The voice as HEARD, each frame: its level replaces
                        // the one above while it plays, and the animals' mouths
                        // follow it. Nothing playing - a typed answer - and
                        // their mouths stay shut.
                        speechMouth = speechMouth,
                        // The theme's own well, not a hardcoded near-black - see
                        // Chrome.well. A theme whose ground is not that same
                        // near-black (Graphite, Ember Dusk) used to sit the reactor
                        // in a visibly mismatched box; this is the token the theme
                        // system already carries for exactly this, just never read
                        // before now.
                        background = chrome.well,
                        // The owner's Glow setting under the theme's own glow
                        // budget. Both are 1 or less, and FaceView clamps to 0..1
                        // again, so this can only ever dim the face.
                        glow = chrome.postScale * state.glow,
                        // Slower, never faster. MainActivity works it out from
                        // the Motion setting and the phone's own animation scale.
                        calmMotion = state.calmMotion,
                        // A crisis answer: calm and plain (section 38.1).
                        serious = state.faceSerious,
                        stillMotion = state.stillAnimal,
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
                        "Open the Brain →",
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
 * AUTONOMY-PROPOSALS.md §3d, served by the desktop's
 * `backend/task-control.patch`. A desktop without that patch answers 404 and
 * every button here says so rather than pretending to work - see
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
/**
 * "Stop everything" - one button, the same route and the same words as the
 * desktop's hotkey (`POST /api/stop_all`, `backend/jarvis_stop_all.py`).
 * What it stopped is reported in the shared notice, in the PC's own words
 * ([com.jarvis.client.net.StopEverything]); this plate never claims it.
 */
@Composable
private fun StopEverythingPlate(actions: HomeActions) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    Plate {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                com.jarvis.client.net.StopEverything.HINT,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet(
                com.jarvis.client.net.StopEverything.LABEL,
                color = chrome.badInk,
                enabled = !busy,
                onClick = {
                    if (!busy) {
                        busy = true
                        scope.launch {
                            actions.onStopEverything()
                            busy = false
                        }
                    }
                },
            )
        }
    }
}

/**
 * "Lockdown is on" (2026-09-28): the one line Home shows while every way out
 * of the PC asks first. No button: turning it off is on the PC only, with an
 * approval card and Windows Hello ([com.jarvis.client.net.AsksFirst]).
 */
@Composable
private fun LockdownPlate() {
    val chrome = LocalChrome.current
    Plate(outline = chrome.warnInk.copy(alpha = 0.35f)) {
        Kicker(com.jarvis.client.net.AsksFirst.LOCKDOWN_BAR_LABEL, color = chrome.warnInk)
        Gap(6)
        Text(
            com.jarvis.client.net.AsksFirst.LOCKDOWN_HOME_LINE,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textMid,
        )
    }
}

/**
 * "Jarvis is watching" - the PC's Watch with me, shown on this phone too
 * (the owner's decision of 2026-09-28: a visible sign the whole time). The
 * words come from [com.jarvis.client.net.ScreenRules.sign], the same table
 * the PC's own sign is held to. Stop ends the PC's watching; it is offered
 * whatever the link says (stopping only ever makes Jarvis look at less) and
 * raises no card. Starting is the PC's alone: a request to start from a
 * phone is refused by the PC itself.
 */
@Composable
private fun PcWatchingPlate(
    sign: com.jarvis.client.net.ScreenRules.Sign,
    onStop: suspend () -> String?,
    pcScreen: Boolean = false,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    // A plain line when Stop could not reach the PC. The sign itself is never
    // marked off here: it only follows what the PC says when it is re-read.
    var said by remember { mutableStateOf<String?>(null) }
    Plate(outline = chrome.warnInk.copy(alpha = 0.35f)) {
        // The plate's own, larger title (the shared words stay in ScreenRules).
        Text(sign.title, style = MaterialTheme.typography.titleSmall, color = chrome.warnInk)
        if (pcScreen) {
            Gap(2)
            Text(
                com.jarvis.client.net.ScreenPlateText.PC_SCREEN,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
        }
        if (sign.detail.isNotEmpty()) {
            Gap(6)
            Text(
                // Only the PC can extend a watch, so an "Ending soon" line says so.
                if (pcScreen) com.jarvis.client.net.ScreenPlateText.withExtendHint(sign.detail) else sign.detail,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
                modifier = Modifier.liveStatus(),
            )
        }
        said?.let {
            Gap(6)
            Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.badInk, modifier = Modifier.liveStatus())
        }
        if (sign.on && sign.stop.isNotEmpty()) {
            Quiet(
                sign.stop,
                color = chrome.badInk,
                enabled = !busy,
                onClick = {
                    if (!busy) {
                        busy = true
                        said = null
                        scope.launch {
                            try {
                                said = onStop()
                            } finally {
                                busy = false
                            }
                        }
                    }
                },
            )
        }
    }
}

/**
 * "Watch this phone with me" - the start of a Watch session on THIS phone
 * (the owner's decision of 2026-09-28, docs/SCREEN-DESIGN.md section 4). Shown
 * only while the Security switch "Let Jarvis read this phone's screen" is on.
 * The owner's own tap; Android asks its own question next, every time. It needs
 * Android's Usage access (so Jarvis can tell which app is in front); without
 * it, this says so and offers the Android screen where it is turned on. No card:
 * the sign is the safeguard. The words are [com.jarvis.client.net.ScreenWatch]'s.
 */
@Composable
private fun PhoneWatchStartPlate(state: HomeState, actions: HomeActions) {
    val chrome = LocalChrome.current
    Plate {
        Kicker(com.jarvis.client.net.ScreenWatch.START_LABEL, color = chrome.textMid)
        Gap(6)
        Text(
            com.jarvis.client.net.ScreenWatch.HOW,
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        if (!state.usageAccess) {
            Gap(6)
            Text(
                com.jarvis.client.net.ScreenWatch.NEEDS_USAGE,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.warnInk,
            )
            Quiet(com.jarvis.client.net.ScreenWatch.OPEN_USAGE, onClick = actions.onOpenUsageAccess)
        } else {
            Quiet(
                com.jarvis.client.net.ScreenWatch.START_LABEL,
                enabled = state.link == LinkState.CONNECTED,
                onClick = actions.onStartPhoneWatch,
            )
            if (state.link != LinkState.CONNECTED) {
                Text(
                    com.jarvis.client.net.ScreenPlateText.WAITING_LINK,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                    modifier = Modifier.liveStatus(),
                )
            }
        }
        // Asking about the screen goes through Android's assistant gesture, so
        // Jarvis has to be the phone's assistant app; shown only when it is not.
        if (!PlatformReadiness.assistantRoleHeld(LocalContext.current)) {
            Gap(6)
            Text(
                com.jarvis.client.net.ScreenPlateText.ASSISTANT_HINT,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textLo,
            )
        }
    }
}

/**
 * "Playing on your PC" (2026-09-28; [com.jarvis.client.net.PcMedia]): what is
 * playing, in the PC's own sentence - read when Home shows it, and again
 * after each button - and four buttons, ONE action per tap. Greyed while the
 * link is stale (rule 4); the runtime refuses then too. No card.
 */
@Composable
private fun PcMediaPlate(canAct: Boolean, actions: HomeActions) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var said by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(canAct) {
        if (canAct) said = actions.onPcMedia()
    }
    Plate {
        Kicker(com.jarvis.client.net.PcMedia.TITLE)
        Gap(4)
        Text(
            said ?: com.jarvis.client.net.PcMedia.HINT,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            com.jarvis.client.net.PcMedia.ACTIONS.forEach { action ->
                Quiet(
                    com.jarvis.client.net.PcMedia.label(action),
                    enabled = canAct && !busy,
                    onClick = {
                        if (!busy) {
                            busy = true
                            scope.launch {
                                try {
                                    said = actions.onPcMediaControl(action)
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    },
                )
            }
        }
    }
}

/**
 * The Undo strip under an inbox tidy ("Inbox tidy by voice", the owner's
 * decision of 2026-09-28; docs/JARVIS-API.md section 95): what was done, how
 * long Undo lasts, and one button. The words are the PC's own and the
 * desktop's strip says the same ([com.jarvis.client.net.InboxTidy], checked
 * against contract/inbox-tidy-cases.json). It approves nothing and raises no
 * card; the button is held while the link is stale (rule 4) and while the
 * lists are hidden, and the strip says why in its own line.
 */
@Composable
private fun InboxTidyPlate(
    strip: com.jarvis.client.net.InboxTidy.Strip,
    busy: Boolean,
    onUndo: () -> Unit,
) {
    val chrome = LocalChrome.current
    Plate {
        Kicker(com.jarvis.client.net.InboxTidy.w("title"))
        Gap(4)
        Text(
            strip.text,
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textHi,
        )
        Gap(2)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                strip.left,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Quiet(
                com.jarvis.client.net.InboxTidy.w("undo"),
                enabled = strip.canUndo && !busy,
                onClick = onUndo,
            )
        }
        if (strip.note.isNotEmpty()) {
            Text(
                strip.note,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
        }
    }
}

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
            if (paused) {
                "Resume asks you first: an approval card lists the steps that are left. " +
                    "Stop forgets the task."
            } else {
                "Pause and Stop take effect before the next step. Steps already done stay done."
            },
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

/**
 * A note filed on the desktop, in today's Logseq journal, as a new Joplin
 * note, or in today's Obsidian daily note - the desktop's
 * `POST /api/notes/capture` (`backend/note-capture.patch`).
 *
 * Closed, it is one small button. Open, a field and one button for each note
 * app the desktop says is set up (asked each time it opens). None set up, or
 * the desktop cannot say: no button, and one line saying which. What happens
 * next is reported in the shared notice, in the desktop's own words ("Filed
 * in Logseq, …", "Waiting for your approval…", or why not) - this plate
 * never says "filed" itself. The typed text is kept if sending fails.
 */
@Composable
private fun QuickNotePlate(open: Boolean, actions: HomeActions) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var noteText by rememberSaveable { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    // null while the desktop is being asked.
    var targets by remember { mutableStateOf<NoteCapture.Targets?>(null) }
    LaunchedEffect(open) {
        if (open) {
            targets = null
            targets = actions.onLoadNoteTargets()
        }
    }

    if (!open) {
        Quiet("Quick note…", color = chrome.textMid, onClick = { actions.onQuickNoteOpenChange(true) })
        return
    }
    Plate {
        Text("Quick note", style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
        Spacer(Modifier.height(6.dp))
        Text(
            "Filed on the desktop exactly as you type it. The desktop's own rules decide " +
                "whether it asks you first.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        Spacer(Modifier.height(10.dp))
        TextInput(
            value = noteText,
            onValueChange = { noteText = it },
            placeholder = "Your note…",
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(10.dp))
        val ready = (targets as? NoteCapture.Targets.Known)?.names.orEmpty()
        if (ready.isEmpty()) {
            Text(
                targets?.let { NoteCapture.noTargetsLine(it) }
                    ?: "Checking which note apps are set up on your PC…",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
            Spacer(Modifier.height(6.dp))
        }
        fun send(target: String) {
            if (sending || noteText.isBlank()) return
            val note = noteText
            sending = true
            scope.launch {
                val accepted = actions.onFileNote(target, note)
                sending = false
                if (accepted) {
                    noteText = ""
                    actions.onQuickNoteOpenChange(false)
                }
            }
        }
        // Up to three destinations, so Close has a row of its own: four
        // buttons do not fit across a phone.
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (target in ready) {
                Quiet(
                    "To ${NoteCapture.name(target)}",
                    enabled = !sending && noteText.isNotBlank(),
                    onClick = { send(target) },
                )
            }
        }
        // The chat box takes the same notes: a prefix per app that is set
        // up, as the desktop's help list shows them.
        val primer = NoteCapture.primer(targets)
        if (primer.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            Text(
                "Or start a message to Jarvis with:",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
            )
            for ((prefix, what) in primer) {
                Text(
                    "$prefix  $what",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
        Quiet("Close", color = chrome.textMid, enabled = !sending,
            onClick = { actions.onQuickNoteOpenChange(false) })
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
private fun Reply(
    reply: () -> String,
    streaming: Boolean,
    question: String?,
    feedback: AnswerFeedback? = null,
    canMark: Boolean = false,
    onMark: (turnId: String, tapped: AnswerMark) -> Unit = { _, _ -> },
    conversationTurns: Int = 0,
    onNewConversation: () -> Unit = {},
    thread: List<com.jarvis.client.net.ChatHistory.Exchange> = emptyList(),
    readOutside: Boolean = false,
    idleNextLine: String? = null,
    waiting: String? = null,
    note: String? = null,
    used: UsedAnswer? = null,
    // "Where this came from" (feasibility I42/I132): null when the caller
    // gave no turn_id at all - the same "nothing to show" the line below
    // already treats an empty `used.ids` as.
    sources: SourcesAnswer? = null,
    // The crisis help line (jarvis_wellbeing.py, 2026-09-27): draws this
    // answer as a calm, plain panel instead of an ordinary bubble. Wording,
    // the word check and never learning from it all happen on the PC;
    // this only changes how the words already decided are shown.
    crisis: Boolean = false,
    // "A cloud model could give this one a second look."
    // (jarvis_router.choose(), gate "offer" - docs/JARVIS-API.md, "`offer`
    // in `X-Jarvis-Route`"): the lane [com.jarvis.client.net.CloudOffer]
    // read off THIS answer's route, or null - no offer, or the owner
    // already tapped "Try the cloud model" or dismissed it.
    cloudOffer: String? = null,
    onTryCloud: () -> Unit = {},
    onDismissCloudOffer: () -> Unit = {},
) {
    val chrome = LocalChrome.current
    val motion = LocalMotion.current
    val context = LocalContext.current
    val text = reply()
    AnimatedVisibility(
        visible = text.isNotBlank() || streaming || question != null || thread.isNotEmpty(),
        enter = fadeIn(motion.enter()),
        exit = fadeOut(motion.micro()),
    ) {
        Plate {
            // The conversation so far, above the question on screen (the
            // owner's decision, 2026-09-28): folded, and scrolling inside
            // itself so a long chat never pushes the answer off Home. Open
            // at once for a chat carried on from History, where nothing new
            // has been asked yet. Shown only - never read aloud, never kept.
            if (thread.isNotEmpty()) {
                ThreadFold(thread, startOpen = question == null)
                if (question != null || streaming || text.isNotBlank()) Gap(12)
            }
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
                        // What it is waiting on, when the desktop says -
                        // "Waiting for your approval…" - so a turn held by
                        // an approval card does not look stuck.
                        waiting ?: "…",
                        style = MaterialTheme.typography.bodyLarge,
                        color = if (waiting != null) chrome.textMid else chrome.textHi,
                    )
                }
            } else if (crisis && !streaming) {
                // The crisis help line (jarvis_wellbeing.py, 2026-09-27): a
                // calm, plain panel, reusing the same Plate every other
                // grouped surface on this screen uses - larger text, and
                // the answer's own "**...**" emphasis (there is no
                // markdown renderer here, so it would otherwise show as
                // literal asterisks) dropped rather than shown raw.
                Plate(tone = chrome.surface2) {
                    text.split(PARAGRAPH_BREAK).forEachIndexed { index, paragraph ->
                        if (index > 0) Gap(10)
                        Text(
                            paragraph.replace("**", ""),
                            style = MaterialTheme.typography.headlineSmall,
                            color = chrome.textHi,
                        )
                    }
                }
            } else {
                // Identity by position is right here: paragraphs are only
                // ever added at the end while a reply streams, so each index
                // keeps meaning the same paragraph. `shown` starts false and
                // flips once per index (UI-AUDIT-2026-09-26 item 6), so a
                // freshly-added paragraph fades in - the same idea as the
                // desktop's "each freshly appended block fades in"
                // (`style.css`'s `.fresh`, 260ms) - while an index already on
                // screen never replays the fade as later tokens append to it.
                // `FormattedAnswer` (ui/parts/AnswerFormat.kt) gives bold,
                // italics, lists and code instead of the raw markdown text
                // this `Text` used to show verbatim.
                text.split(PARAGRAPH_BREAK).forEachIndexed { index, paragraph ->
                    if (index > 0) Gap(10)
                    var shown by remember(index) { mutableStateOf(false) }
                    LaunchedEffect(index) { shown = true }
                    AnimatedVisibility(visible = shown, enter = fadeIn(motion.enter())) {
                        FormattedAnswer(
                            paragraph,
                            style = MaterialTheme.typography.bodyLarge,
                            color = chrome.textHi,
                        )
                    }
                }
            }
            // Only once there is a finished answer to act on - copying or
            // sharing a reply mid-stream would grab a sentence Jarvis has not
            // finished writing yet.
            if (!streaming && text.isNotBlank()) {
                if (note != null) {
                    Gap(6)
                    Text(
                        note,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                // "Try the cloud model" (docs/JARVIS-API.md, "`offer` in
                // `X-Jarvis-Route`"): one tap, one question, never a
                // standing choice - see com.jarvis.client.net.CloudOffer's
                // own doc for the whole design. Not shown while crisis is
                // true: the router never offers a cloud lane on a crisis
                // turn in the first place (jarvis_router.choose()'s own
                // gates run before gate 6 ever does), but this is the one
                // place on screen that could show both at once if that
                // ever changed, and a crisis panel is not where a cloud
                // upsell belongs.
                if (cloudOffer != null && !crisis) {
                    Gap(6)
                    Text(
                        com.jarvis.client.net.CloudOffer.LABEL,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                    Gap(2)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Quiet(com.jarvis.client.net.CloudOffer.BUTTON, onClick = onTryCloud)
                        Spacer(Modifier.width(4.dp))
                        Quiet("Not now", color = chrome.textLo, onClick = onDismissCloudOffer)
                    }
                    Text(
                        com.jarvis.client.net.CloudOffer.MICRO,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                // "Used 2 memories": opens the facts this answer used, read
                // from the PC by id only then (UsedMemoriesPlate.kt).
                if (used != null && used.ids.isNotEmpty()) {
                    var open by remember(used.ids) { mutableStateOf(false) }
                    com.jarvis.client.net.MemoryUsed.usedLine(used.ids.size)?.let { line ->
                        Gap(4)
                        Quiet(line, color = chrome.textMid, onClick = { open = !open })
                    }
                    if (open) {
                        UsedFactsList(
                            title = com.jarvis.client.net.MemoryUsed.USED_TITLE,
                            ids = used.ids,
                            canAct = used.canAct,
                            privateHidden = used.hidden,
                            showPrivateBusy = used.showBusy,
                            onShowPrivate = used.onShow,
                            load = used.load,
                            forget = used.forget,
                        )
                    }
                }
                // "Where this came from" (feasibility I42/I132): fetched
                // once, quietly, as soon as this answer's turn_id is known
                // - there is no cheap count the way "Used 2 memories" has
                // one (a tool's result is only known once the tool loop
                // finishes, unlike a recalled fact). Never even asked for
                // while Security's "Hide memory lists and chat history" is
                // hiding the memory lists - the same gate as above, not a
                // second one - so nothing is shown at all in that case
                // rather than a line that cannot be opened yet.
                if (sources != null && sources.turnId != null && !sources.hidden) {
                    var srcOpen by remember(sources.turnId) { mutableStateOf(false) }
                    var srcRead by remember(sources.turnId) {
                        mutableStateOf<com.jarvis.client.net.ChatSources.Read?>(null)
                    }
                    LaunchedEffect(sources.turnId) { srcRead = sources.load(sources.turnId) }
                    val shown = srcRead as? com.jarvis.client.net.ChatSources.Read.Shown
                    if (shown != null && (shown.view.sources.isNotEmpty() || shown.view.quotes.isNotEmpty())) {
                        Gap(4)
                        Quiet(
                            com.jarvis.client.net.ChatSources.TITLE,
                            color = chrome.textMid,
                            onClick = { srcOpen = !srcOpen },
                        )
                        if (srcOpen) {
                            ChatSourcesList(shown.view)
                        }
                    }
                }
                Gap(8)
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Quiet("Copy", color = chrome.textMid) {
                        // Feasibility I114, "Private copy": marks the clip
                        // sensitive so Android's own copy toast shows no
                        // preview of the answer - see PrivateClipboard's own
                        // doc comment for why this is the phone's whole half
                        // of a feature the desktop does differently.
                        PrivateClipboard.copy(context, text)
                    }
                    Quiet("Share", color = chrome.textMid) {
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, text)
                        }
                        context.startActivity(Intent.createChooser(intent, null))
                    }
                }
                // Only on an answer the desktop gave an id to, and only once
                // it has finished - the same moment Copy and Share appear.
                if (feedback != null) {
                    Gap(4)
                    AnswerMarks(feedback, canMark, onMark)
                }
            }
            // Follow-ups carry the conversation so far, so there has to be a
            // plain way to start again without it. Not while an answer is
            // arriving - Stop is the control for that. Shown after a failed
            // question too, when there is no answer to put Copy beside.
            if (!streaming && conversationTurns > 0) {
                Gap(4)
                Text(
                    // After 30 quiet minutes the next question is a new conversation
                    // and the line says so (the second chat audit, phone C1).
                    idleNextLine ?: if (conversationTurns == 1) {
                        "Your next question follows on from this one."
                    } else {
                        "Your next question follows on from the last $conversationTurns."
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
                if (readOutside) {
                    Text(
                        com.jarvis.client.net.ChatHistory.CONTINUED_TAINTED,
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.warnInk,
                    )
                }
                Quiet("New conversation", color = chrome.textMid, onClick = onNewConversation)
            }
        }
    }
}

/**
 * "Earlier in this chat · 3 questions": every finished question and answer
 * of this conversation above the one on screen, oldest first (the chat
 * audit, 2026-09-28 - Home used to show only the last exchange). The
 * desktop's Jarvis bar folds the same thread under the same words
 * ([com.jarvis.client.net.ChatHistory.threadSummary]).
 */
@Composable
private fun ThreadFold(thread: List<com.jarvis.client.net.ChatHistory.Exchange>, startOpen: Boolean) {
    val chrome = LocalChrome.current
    val words = com.jarvis.client.net.ChatHistory
    // Kept over a rotation (the second chat audit, phone accessibility).
    var open by rememberSaveable { mutableStateOf(startOpen) }
    var showAll by rememberSaveable { mutableStateOf(false) }
    Quiet(
        words.threadSummary(thread.size),
        color = chrome.textMid,
        modifier = Modifier.semantics {
            // Whether it is open, said in words.
            stateDescription = if (open) "Expanded" else "Collapsed"
        },
        onClick = { open = !open },
    )
    if (!open) return
    // The newest 20 pairs, with "Show older" for the rest: a long chat used
    // to compose up to 100 answers at once (phone worst-three #3).
    val shown = if (showAll || thread.size <= THREAD_NEWEST) thread else thread.takeLast(THREAD_NEWEST)
    val skipped = thread.size - shown.size
    if (skipped > 0) {
        Quiet("Show $skipped older", color = chrome.textMid, onClick = { showAll = true })
    }
    // The line where what Jarvis reads back begins: only the newest pairs go
    // to the model (the same numbers Jarvis itself uses), so the owner is not
    // left thinking it read the whole thread.
    val above = words.pairsAboveReadLine(thread.size, words.MAX_EXCHANGES)
    val listState = rememberLazyListState()
    // Lands on the newest pair, not the oldest (phone worst-three #3).
    LaunchedEffect(shown.size, open) {
        if (shown.isNotEmpty()) listState.scrollToItem(shown.lastIndex)
    }
    LazyColumn(
        Modifier
            .fillMaxWidth()
            .heightIn(max = 360.dp),
        state = listState,
    ) {
        itemsIndexed(shown) { local, pair ->
            val index = skipped + local
            if (index > 0) Gap(12)
            if (above > 0 && index == above) {
                Text(
                    words.THREAD_READS_FROM,
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textMid,
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
            Kicker("You")
            Gap(2)
            Text(pair.question, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            Gap(6)
            Kicker("Jarvis")
            Gap(2)
            pair.answer.split(PARAGRAPH_BREAK).forEachIndexed { i, paragraph ->
                if (i > 0) Gap(6)
                FormattedAnswer(paragraph, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
            }
        }
    }
}

/** How many pairs the thread draws before "Show older". */
private const val THREAD_NEWEST = 20

/** What "Used 2 memories" under the answer needs - see [UsedFactsList]. */
@Immutable
internal data class UsedAnswer(
    val ids: List<Long>,
    val canAct: Boolean,
    val hidden: Boolean,
    val showBusy: Boolean,
    val onShow: () -> Unit,
    val load: suspend (List<Long>) -> com.jarvis.client.net.MemoryUsed.Read,
    val forget: suspend (Long) -> Pair<Boolean, String>,
)

/** What "Where this came from" under the answer needs (feasibility
 *  I42/I132) - see [ChatSourcesList]. `hidden` is the SAME "Hide memory
 *  lists and chat history" flag [UsedAnswer.hidden] reads, not a second
 *  gate. */
@Immutable
internal data class SourcesAnswer(
    val turnId: String?,
    val hidden: Boolean,
    val load: suspend (String?) -> com.jarvis.client.net.ChatSources.Read,
)

/**
 * "Was this answer right?" - one Right and one Wrong for the ONE answer on
 * screen (`feedback.patch`). There is no "mark all": one answer, one mark.
 *
 * Tapping the chosen one again takes the mark back. A mark never changes
 * memory; at most, if a fact keeps turning up in wrong answers, the desktop
 * asks - with a card in Mind's memory review - whether to stop using it.
 */
@Composable
private fun AnswerMarks(
    feedback: AnswerFeedback,
    canMark: Boolean,
    onMark: (turnId: String, tapped: AnswerMark) -> Unit,
) {
    val chrome = LocalChrome.current
    if (feedback.unavailable) {
        Text(
            "This answer cannot be marked right or wrong.",
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
        )
        return
    }
    val enabled = canMark && !feedback.busy
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            "Was this right?",
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textMid,
            modifier = Modifier.weight(1f),
        )
        MarkToggle(
            label = "Right",
            description = "Mark this answer right",
            selected = feedback.mark == AnswerMark.RIGHT,
            color = chrome.okInk,
            enabled = enabled,
            onClick = { onMark(feedback.turnId, AnswerMark.RIGHT) },
        )
        Spacer(Modifier.width(8.dp))
        MarkToggle(
            label = "Wrong",
            description = "Mark this answer wrong",
            selected = feedback.mark == AnswerMark.WRONG,
            color = chrome.badInk,
            enabled = enabled,
            onClick = { onMark(feedback.turnId, AnswerMark.WRONG) },
        )
    }
    val line = when {
        feedback.busy -> "Saving…"
        !canMark -> "Not connected, so a mark cannot be sent right now."
        feedback.mark == AnswerMark.WRONG ->
            "Marked wrong. Nothing changes without asking you. Tap Wrong again to take it back."
        feedback.mark == AnswerMark.RIGHT -> "Marked right. Tap Right again to take it back."
        else -> null
    }
    if (line != null) {
        Text(
            line,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textLo,
            modifier = Modifier.liveStatus(),
        )
    }
}

/**
 * One mark button. Chosen is told apart by shape and a tick, not by colour
 * alone (SHARED-LOOK.md §9): filled with a "✓" when chosen, outlined when not.
 * 48dp tall and wide whatever the label, like every other control here.
 */
@Composable
private fun MarkToggle(
    label: String,
    description: String,
    selected: Boolean,
    color: Color,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.chipShape
    val ink = if (enabled) color else chrome.textLo
    Box(
        Modifier
            .heightIn(min = 48.dp)
            .widthIn(min = 48.dp)
            .pressable(enabled = enabled, onClick = onClick)
            .semantics {
                contentDescription = description
                stateDescription = if (selected) "Chosen" else "Not chosen"
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            if (selected) "✓ $label" else label,
            style = MaterialTheme.typography.labelMedium,
            color = if (selected && enabled) chrome.surface0 else ink,
            modifier = Modifier
                .clip(shape)
                .then(
                    if (selected) {
                        Modifier.background(ink)
                    } else {
                        Modifier.border(1.dp, ink.copy(alpha = 0.6f), shape)
                    },
                )
                .padding(horizontal = 12.dp, vertical = 6.dp),
        )
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
    // Shared text alone is something to send: it goes as its own message.
    val canSend = (text.isNotBlank() || state.sharedLine != null) && state.link == LinkState.CONNECTED

    Column(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
    // The one quiet line about the chat itself (the chat audit, 2026-09-28):
    // read out by TalkBack as it appears, dismissed by a tap.
    state.chatNote?.let { line ->
        // Two lines, then "More": a long note used to crowd Home out at large text.
        var more by remember(line) { mutableStateOf(false) }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                line,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                maxLines = if (more) Int.MAX_VALUE else 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f).liveStatus(),
            )
            if (line.length > 110) {
                Quiet(if (more) "Less" else "More", color = chrome.textLo, onClick = { more = !more })
            }
            Quiet(
                "Dismiss",
                color = chrome.textLo,
                modifier = Modifier.semantics { contentDescription = "Dismiss this note about the chat" },
                onClick = actions.onDismissChatNote,
            )
        }
    }
    // A temporary chat: the marker for the whole chat, and the way in and
    // out - and "Earlier chats", the way to History (the owner's decision,
    // 2026-09-28).
    TemporaryChatStrip(
        on = state.temporary,
        empty = state.lastUserText == null && state.conversationTurns == 0,
        enabled = !state.streaming,
        onToggle = actions.onToggleTemporary,
        onEarlierChats = actions.onEarlierChats,
    )
    VoiceStrips(state, actions)
    // A picture waiting to go with the next question. Dismiss drops it.
    if (state.pictureBusy) {
        VoiceStrip("Preparing the picture…", tone = chrome.textMid)
    } else if (state.pictureLine != null) {
        VoiceStrip(state.pictureLine, tone = chrome.textMid, onDismiss = actions.onRemovePicture)
        // "Photo to reminder": the PC reads the dates in it and proposes.
        Quiet(
            if (state.photoFinding) {
                com.jarvis.client.net.PhotoReminder.READING
            } else {
                com.jarvis.client.net.PhotoReminder.FIND_LABEL
            },
            enabled = !state.photoFinding && state.link == LinkState.CONNECTED,
            onClick = actions.onFindDateInPicture,
        )
    }
    // Text shared from another app: sent as its own message, before what is
    // typed, never mixed into it. Dismiss drops it.
    if (state.sharedLine != null) {
        VoiceStrip(state.sharedLine, tone = chrome.textMid, onDismiss = actions.onDropShared)
    }
    // A look at this phone's screen ("Look at this", the assistant gesture):
    // held in memory for two minutes of questions; the words are labelled
    // outside text on the PC. Dismiss forgets it.
    if (state.lookLine != null) {
        VoiceStrip(state.lookLine, tone = chrome.textMid, onDismiss = actions.onForgetLook)
    }
    // A `#log` / `#obs` / `#joplin` line is filed, not asked - said while it
    // is typed, as the desktop's chip beside its prompt does.
    NoteCapture.chip(text, state.noteTargets)?.let { VoiceStrip(it, tone = chrome.textMid) }
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Bottom,
    ) {
        // Only while the PC's Pictures feature works - see HomeState.pictureOffered.
        if (state.pictureOffered) {
            Quiet(
                "Photo",
                color = chrome.textMid,
                enabled = state.link == LinkState.CONNECTED && !state.streaming && !state.pictureBusy,
                onClick = actions.onAttachPicture,
            )
            Spacer(Modifier.width(4.dp))
        }
        // Only while phone notifications are on AND something has actually
        // been captured - see HomeState.notificationsAttachable. Attaching
        // never sends on its own: it fills the same shared-text chip the
        // Share sheet does, and the owner still presses Send.
        if (state.notificationsAttachable) {
            Quiet(
                "Notifications",
                color = chrome.textMid,
                enabled = !state.streaming,
                onClick = actions.onAttachNotifications,
            )
            Spacer(Modifier.width(4.dp))
        }
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

/**
 * What a voice turn is doing, what the desktop heard, and why it refused -
 * shared by the composer and Full screen's [VoiceBar], so the two can never
 * disagree about a turn in progress.
 */
@Composable
private fun VoiceStrips(state: HomeState, actions: HomeActions) {
    val chrome = LocalChrome.current
    when (state.voicePhase) {
        VoiceSession.Phase.CAPTURING ->
            VoiceStrip("Listening — release to send, slide up to cancel")
        VoiceSession.Phase.VERIFYING ->
            // Named for what it is. The desktop checks whose voice this is
            // BEFORE transcribing, so that a voice that is not his is never
            // turned into words at all.
            VoiceStrip("Checking it's you…")
        // "Waking up the model…" (or "Waiting for your approval…") when the PC
        // says so in the answer's stream - the chat's own wait words - rather
        // than a bare "Thinking…" through a 10-20 second model load.
        VoiceSession.Phase.THINKING -> VoiceStrip(state.chatWaiting ?: "Thinking…")
        VoiceSession.Phase.SPEAKING -> VoiceStrip("Speaking")
        VoiceSession.Phase.OFF -> Unit
    }
    if (state.transcript != null && state.voicePhase != VoiceSession.Phase.CAPTURING) {
        VoiceStrip("“${state.transcript}”", tone = chrome.textMid)
    }
    if (state.voiceNotice != null) {
        VoiceStrip(state.voiceNotice, tone = chrome.warnInk, onDismiss = actions.onDismissVoiceNotice)
    }
}

/**
 * Full screen's bottom edge: what the voice turn is doing, the start of the
 * last answer, and the microphone - centred, and the one big control here.
 *
 * Notices still show. A refusal or an error said only in the chat would be
 * said to nobody while the chat is out of the way.
 */
@Composable
private fun VoiceBar(
    state: HomeState,
    actions: HomeActions,
    reply: () -> String,
    micLevel: State<Float>,
    onShowChat: () -> Unit,
) {
    val chrome = LocalChrome.current
    Column(
        Modifier
            .fillMaxWidth()
            .background(chrome.surface1)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        if (state.notice != null) {
            HomeNotice(state, actions)
            Gap(8)
        }
        if (state.approvalsOff) {
            VoiceStrip("Approvals are off on the desktop", tone = chrome.warnInk)
        }
        VoiceStrips(state, actions)
        ReplyPeek(reply, state.streaming)
        Box(Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
            Quiet(
                "Show chat",
                modifier = Modifier.align(Alignment.CenterStart),
                onClick = onShowChat,
            )
            Box(Modifier.align(Alignment.Center)) {
                VoiceButton(
                    enabled = state.link == LinkState.CONNECTED && !state.streaming,
                    capturing = state.voicePhase == VoiceSession.Phase.CAPTURING,
                    micLevel = micLevel,
                    onBegin = actions.onVoiceBegin,
                    onRelease = actions.onVoiceRelease,
                    onCancel = actions.onVoiceCancel,
                )
            }
            // Stop is the same action the composer's Send button turns into
            // while an answer streams: cancelling the call stops generation.
            if (state.streaming) {
                Quiet(
                    "Stop",
                    modifier = Modifier.align(Alignment.CenterEnd),
                    color = chrome.badInk,
                    onClick = actions.onInterrupt,
                )
            }
        }
    }
}

/**
 * The first few lines of the answer, for Full screen. Read as a lambda and
 * only in here, for the reason [HomeScreen]'s `reply` parameter gives: a
 * streamed token redraws these lines and nothing else.
 */
@Composable
private fun ReplyPeek(reply: () -> String, streaming: Boolean) {
    val text = reply()
    if (text.isBlank() && !streaming) return
    Text(
        text.ifBlank { "…" },
        style = MaterialTheme.typography.bodyMedium,
        color = LocalChrome.current.textMid,
        maxLines = 3,
        overflow = TextOverflow.Ellipsis,
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
    )
}
