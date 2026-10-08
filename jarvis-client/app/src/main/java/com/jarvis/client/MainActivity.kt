package com.jarvis.client

import android.Manifest
import android.app.role.RoleManager
import android.content.Intent
import android.media.audiofx.AcousticEchoCanceler
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.CheckOutcome
import com.jarvis.client.data.FloatingAvatarMode
import com.jarvis.client.data.LockSession
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.data.calmFace
import com.jarvis.client.face.FaceBudget
import com.jarvis.client.face.FaceQuality
import com.jarvis.client.face.Faces
import com.jarvis.client.net.ApiError
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ChatPicture
import com.jarvis.client.net.PhotoReminder
import com.jarvis.client.net.CustomVoices
import com.jarvis.client.net.Feedback
import com.jarvis.client.net.NoteCapture
import com.jarvis.client.net.Provenance
import com.jarvis.client.net.SecondCard
import com.jarvis.client.net.SignedApproval
import com.jarvis.client.net.UpdateCheck
import android.security.keystore.KeyPermanentlyInvalidatedException
import com.jarvis.client.platform.ApprovalKey
import com.jarvis.client.platform.CrashLog
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.PictureEncoder
import com.jarvis.client.platform.PlatformReadiness
import com.jarvis.client.platform.PowerWatch
import com.jarvis.client.net.PendingItem
import com.jarvis.client.service.ApprovalNotifier
import com.jarvis.client.service.AvatarOverlayService
import com.jarvis.client.service.EventService
import com.jarvis.client.service.WakeWordService
import com.jarvis.client.net.WakeWord
import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.WakeRules
import com.jarvis.client.ui.NavBackHandler
import com.jarvis.client.ui.NavScreens
import com.jarvis.client.ui.OpenPlace
import com.jarvis.client.ui.Screen
import com.jarvis.client.ui.approval.BiometricGate
import com.jarvis.client.ui.approval.CardWaitingLine
import com.jarvis.client.ui.rememberNavState
import com.jarvis.client.ui.screens.AppearanceScreen
import com.jarvis.client.ui.screens.ApprovalsScreen
import com.jarvis.client.ui.screens.BrainScreen
import com.jarvis.client.ui.screens.ConnectionInfo
import com.jarvis.client.ui.screens.CrashScreen
import com.jarvis.client.ui.screens.FaceSpecimen
import com.jarvis.client.ui.screens.FaceVoiceOfferFromPc
import com.jarvis.client.ui.screens.FaqScreen
import com.jarvis.client.ui.screens.FeaturesScreen
import com.jarvis.client.ui.screens.HistoryScreen
import com.jarvis.client.ui.screens.HomeActions
import com.jarvis.client.ui.screens.HomeScreen
import com.jarvis.client.ui.screens.PhotoReminderDialog
import com.jarvis.client.ui.screens.HomeState
import com.jarvis.client.ui.screens.InboxScreen
import com.jarvis.client.ui.screens.LockedScreen
import com.jarvis.client.ui.screens.PairingScreen
import com.jarvis.client.ui.screens.ReadinessScreen
import com.jarvis.client.ui.screens.SecurityScreen
import com.jarvis.client.ui.screens.SettingsScreen
import com.jarvis.client.ui.screens.WakeWordSwitchesCard
import com.jarvis.client.ui.screens.VoiceCheckScreen
import com.jarvis.client.ui.screens.VoiceTrainingScreen
import com.jarvis.client.ui.screens.VoicesScreen
import com.jarvis.client.ui.theme.JarvisTheme
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.PlateEdges
import com.jarvis.client.ui.theme.Themes
import com.jarvis.client.ui.theme.systemPrefersDark
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject

/**
 * The one activity.
 *
 * FragmentActivity rather than ComponentActivity, for exactly one reason:
 * `BiometricPrompt` takes a FragmentActivity or a Fragment and nothing else —
 * it needs a fragment manager to survive a configuration change while the
 * system prompt is on screen. FragmentActivity *is* a ComponentActivity, so
 * `setContent`, `enableEdgeToEdge` and `registerForActivityResult` are
 * unaffected.
 */
class MainActivity : FragmentActivity() {

    private val permissionTick = mutableIntStateOf(0)

    /** The approval a notification asked us to open, or null. */
    private val focusApproval = mutableStateOf<String?>(null)

    /**
     * Text handed to this app by another app's share sheet, waiting to be
     * picked up as the "Shared text" chip above the chat box. Cleared the
     * moment `App()` consumes it, so the same share cannot be re-applied on a
     * later recomposition.
     */
    private val sharedText = mutableStateOf<String?>(null)

    /**
     * A photo handed to this app by another app's share sheet, waiting to be
     * attached to the next question - under the Photo button's own rule
     * ([ChatPicture.sharedRefusal]). Consumed once, like [sharedText].
     */
    private val sharedPicture = mutableStateOf<Uri?>(null)

    /**
     * Set when the [com.jarvis.client.widget.QuickLinkWidget]'s Mic action
     * opened the app. Consumed the same way [focusApproval] is: a
     * `LaunchedEffect` reads it once and clears it, so a later
     * recomposition does not re-fire the mic.
     */
    private val startVoiceRequested = mutableStateOf(false)

    /** The Jarvis Live notification was tapped: its screen. */
    private val openLiveRequested = mutableStateOf(false)

    /**
     * The Jarvis Live Quick Settings tile (start) or the "Live ended - Resume"
     * notification (resume) asked to start Live here: null, "start" or
     * "resume". Acted on only once the app is unlocked (App lock), then
     * cleared.
     */
    private val startLiveRequested = mutableStateOf<String?>(null)

    /**
     * Text shared with "Talk about this in Live" (the Share sheet's second
     * Jarvis entry, the activity-alias ShareToLive): held for the Live
     * screen's box, sent only when the owner taps Send, tagged "shared" -
     * outside text, like any shared item. Consumed once.
     */
    private val liveSharedText = mutableStateOf<String?>(null)

    /** "Solve it here" - the "a website needs you" alert was tapped. */
    private val openHandoffRequested = mutableStateOf(false)

    /** The quick-note field on Home is open - see [readQuickNoteIntent]. */
    private val quickNoteOpen = mutableStateOf(false)

    /** The briefing notification was tapped - see [readBriefingIntent]. Consumed once. */
    private val openBriefingRequested = mutableStateOf(false)

    /**
     * The assistant gesture just looked at the screen (or said why it did not):
     * go Home, and start the look's two minutes once the app is unlocked
     * ([readLookIntent], [ScreenLook.shown]). Consumed once.
     */
    private val openLookRequested = mutableStateOf(false)

    /**
     * The sentence an app-icon shortcut asks ("Brief me now." or "What did I
     * miss?" - [AppShortcuts]), waiting to be sent from Home. See
     * [readShortcutQuestionIntent]. Consumed once.
     */
    private val shortcutQuestion = mutableStateOf<String?>(null)

    /**
     * When the restart notice was tapped (`SystemClock.elapsedRealtime`), or
     * null - see [readResumeListeningIntent]. Consumed once, after App lock,
     * and only while fresh ([RESUME_REQUEST_FRESH_MS]).
     */
    private val resumeListeningRequestedAt = mutableStateOf<Long?>(null)

    /** Why listening could not be started from the restart notice; shown once in Settings, Voice. */
    private val resumeListeningNotice = mutableStateOf<String?>(null)

    /** An empty tile slot was tapped - see [readTileSettingsIntent]. Consumed once. */
    private val openTileSettingsRequested = mutableStateOf(false)

    /** Set when the runtime itself failed to start. Shown instead of the app. */
    private val startupError = mutableStateOf<String?>(null)

    /** The previous run's crash, read once at launch. */
    private val lastCrash = mutableStateOf<String?>(null)

    /**
     * Bumped whenever [lockSession] changes, so App() reads it again. The
     * session itself lives for the whole process (bottom of this file): a
     * rotation builds a new activity, and must neither unlock nor relock.
     */
    private val lockTick = mutableIntStateOf(0)

    /** A fingerprint or PIN check for Unlock, Show or a Security change is up. */
    private val ownerCheckBusy = mutableStateOf(false)

    /** Why the lock screen did not open, or null. */
    private val lockMessage = mutableStateOf<String?>(null)

    /** Why a Security change was refused, or null. */
    private val securityNotice = mutableStateOf<String?>(null)

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { permissionTick.intValue += 1 }

    /**
     * Set once this process has asked for the notification permission, so the
     * prompt does not reappear on every recomposition or rotation.
     *
     * This exists because the ask used to live in one place only: a button on
     * the Checks screen. Anyone who never opened that screen was never asked,
     * and with the permission denied NOT ONE approval is announced — while the
     * service keeps running and nothing on the phone looks broken. That is the
     * worst shape a failure can take for rule 4, and `ApprovalNotifier.silenced`
     * was counting the casualties with nothing displaying the count.
     */
    private var askedForNotifications = false

    /**
     * Asked the first time the microphone button is held, never at launch.
     *
     * A permission dialog on first run, before the app has shown what it is
     * for, is the one most people refuse — and the refusal is sticky.
     *
     * This used to add "granting it starts the capture immediately, so the
     * hold that asked is the hold that records". That is no longer true and
     * should not be made true again. The dialog takes window focus, which
     * tears down [VoiceButton]'s `pointerInput`; its `finally` then fires
     * `onRelease`/`onCancel`, and both now clear this callback (see
     * [releaseVoice]). So the grant finds nothing to invoke and the first
     * hold records nothing — the owner presses again, and that press both
     * opens and closes the microphone. Starting a capture whose gesture has
     * already ended is the bug that fix exists to prevent.
     */
    private var micGrantedCallback: (() -> Unit)? = null

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        permissionTick.intValue += 1
        if (granted) micGrantedCallback?.invoke()
        micGrantedCallback = null
    }

    /** The system's own role-request dialog. Its result is a plain "did the
     *  owner pick us" - the readiness screen re-reads RoleManager itself on
     *  the next tick rather than trusting this callback's own resultCode,
     *  the same reasoning battery exemption and notifications already use:
     *  what actually happened is whatever the platform now reports, not
     *  whatever this Activity assumes a dialog dismissal meant. */
    private val assistantRolePermission = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { permissionTick.intValue += 1 }

    /**
     * Android's own screen-sharing question for "Watch with me" on this phone
     * (the owner's decision of 2026-09-28): asked EVERY time, by Android, never
     * by Jarvis. Only a yes starts [ScreenWatchService]; anything else says so
     * and starts nothing.
     */
    private val screenShare = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        permissionTick.intValue += 1
        val data = result.data
        if (result.resultCode == RESULT_OK && data != null) {
            com.jarvis.client.service.ScreenWatchService.start(this, result.resultCode, data)
        } else {
            JarvisRuntime.setNotice("Screen sharing was not allowed, so Jarvis is not watching.")
        }
    }

    /**
     * "Watch this phone with me": the owner's own tap. Asks Android's question
     * only when the Security switch is on and Usage access is on (without it
     * Jarvis cannot tell which app is in front, so it would look at nothing);
     * otherwise says which one is missing. No card, like Focus: the sign is
     * the safeguard.
     */
    private fun startPhoneWatch() {
        if (!JarvisRuntime.settings.security.value.screenRead) {
            JarvisRuntime.setNotice(com.jarvis.client.net.ScreenWatch.NEEDS_READ_ON)
            return
        }
        if (!com.jarvis.client.service.ScreenWatchService.usageAccessGranted(this)) {
            JarvisRuntime.setNotice(com.jarvis.client.net.ScreenWatch.NEEDS_USAGE)
            return
        }
        // The notification IS the sign while another app is in front: it never
        // starts if that sign could not be seen.
        if (!com.jarvis.client.service.ScreenWatchService.signVisible(this)) {
            JarvisRuntime.setNotice(com.jarvis.client.net.ScreenWatch.NEEDS_NOTIFICATIONS)
            return
        }
        if (com.jarvis.client.net.ScreenWatch.state.value.on) return
        val manager = getSystemService(android.media.projection.MediaProjectionManager::class.java) ?: return
        runCatching { screenShare.launch(manager.createScreenCaptureIntent()) }
            .onFailure { JarvisRuntime.setNotice("Android would not ask to share the screen, so Jarvis is not watching.") }
    }

    /** Android's own Usage access screen, where the owner turns Jarvis's switch on. */
    private fun openUsageAccess() {
        runCatching { startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)) }
            .onFailure { runCatching { startActivity(Intent(Settings.ACTION_SETTINGS)) } }
    }

    /**
     * A photo to send with the next question, made small enough for the PC,
     * or null. In memory only - never saved, never in a Bundle (a rotation
     * drops it; the owner picks it again). See [ChatPicture].
     */
    private val picture = mutableStateOf<ChatPicture.Ready?>(null)

    /** True while a picked photo is being decoded and shrunk. */
    private val pictureBusy = mutableStateOf(false)

    /**
     * "Photo to reminder" ([PhotoReminder]): what the PC found in the
     * attached picture, on screen only. In memory, never in a Bundle; Close
     * drops it and the words read from the picture with it.
     */
    private val photoScan = mutableStateOf<PhotoReminder.Scan?>(null)

    /** True while the PC reads the attached picture. */
    private val photoFinding = mutableStateOf(false)

    /**
     * "Find a date in it" under the attached picture: the same picture that
     * would go with a question - already shrunk, in memory only - is sent to
     * the PC, which PROPOSES a reminder. Nothing is set up here.
     */
    private fun findDateInPicture() {
        val pic = picture.value ?: return
        if (photoFinding.value) return
        photoFinding.value = true
        lifecycleScope.launch {
            when (val out = JarvisRuntime.scanPhotoForDate(pic.dataUri)) {
                is PhotoReminder.Outcome.Ok -> photoScan.value = out.scan
                is PhotoReminder.Outcome.Failed -> JarvisRuntime.setNotice(out.why)
            }
            photoFinding.value = false
        }
    }

    /**
     * Android's photo picker (API 33+ has it built in): the owner chooses one
     * photo and the app may read that one. No storage permission is asked
     * for, and nothing is copied to the app's own storage - the photo is read
     * once, straight into [PictureEncoder].
     */
    private val pickPicture = registerForActivityResult(
        ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        if (uri == null) return@registerForActivityResult
        attachPicture(uri)
    }

    /**
     * An audio file picked for a new custom voice (VoicesScreen), read into
     * memory and checked ([CustomVoices.picked]), or null. Never copied to
     * the app's storage, never in a Bundle: a rotation drops it.
     */
    private val pickedVoiceFile = mutableStateOf<CustomVoices.Picked?>(null)

    /**
     * The system's file picker, for one audio file. Like the photo picker it
     * asks for no storage permission: the owner chooses one file and the app
     * may read that one, once.
     */
    private val pickVoiceFile = registerForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri == null) return@registerForActivityResult
        lifecycleScope.launch {
            pickedVoiceFile.value = withContext(Dispatchers.IO) { readVoiceFile(uri) }
        }
    }

    /** At most one byte over the PC's limit is read - enough to say "too big". */
    private fun readVoiceFile(uri: Uri): CustomVoices.Picked {
        val limit = CustomVoices.Limits().maxClipBytes
        val bytes = runCatching {
            contentResolver.openInputStream(uri)?.use { input ->
                val out = java.io.ByteArrayOutputStream()
                val buf = ByteArray(64 * 1024)
                while (out.size() <= limit) {
                    val n = input.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                }
                out.toByteArray()
            }
        }.getOrNull() ?: return CustomVoices.Picked(ByteArray(0), null, "That file could not be read.")
        return CustomVoices.picked(bytes, limit)
    }

    /**
     * Reads one photo - picked, or shared from another app - and makes it
     * small enough for the PC ([PictureEncoder]). The same path for both, so
     * the same size limits hold for both.
     */
    private fun attachPicture(uri: Uri) {
        pictureBusy.value = true
        lifecycleScope.launch {
            when (val out = PictureEncoder.encode(this@MainActivity, uri)) {
                is PictureEncoder.Outcome.Ok -> picture.value = out.picture
                is PictureEncoder.Outcome.Failed -> JarvisRuntime.setNotice(out.why)
            }
            pictureBusy.value = false
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Caught rather than allowed to kill the activity. Everything the
        // runtime builds — the Keystore, the preferences, the HTTP client —
        // can fail on a device in a way it cannot here, and "the app closed"
        // is the least useful thing it could say about that.
        runCatching { JarvisRuntime.initialize(this) }
            .onFailure { startupError.value = it.stackTraceToString() }

        lastCrash.value = CrashLog.read(this)
        readApprovalIntent(intent)
        // `fresh`: a rotation rebuilds this activity from the SAME launch
        // intent - a Live start (the tile, "Resume") or a share into Live
        // must not happen again then.
        readShareIntent(intent, fresh = savedInstanceState == null)
        readVoiceIntent(intent)
        readLiveIntent(intent, fresh = savedInstanceState == null)
        readHandoffIntent(intent)
        readQuickNoteIntent(intent)
        readBriefingIntent(intent)
        // Only on a fresh start: a rotation hands back the SAME launch intent,
        // and must not start a look's two minutes again.
        if (savedInstanceState == null) readLookIntent(intent)
        // Only on a fresh start. A rotation (or a restore after Android
        // reclaimed the process) builds this activity again from the SAME
        // launch intent, and the other readers above only navigate, so
        // re-reading them is harmless - but this one sends a question, and
        // must not ask it again every time the phone turns.
        if (savedInstanceState == null) readShortcutQuestionIntent(intent)
        // Only on a fresh start: a rotation (or Android rebuilding the app)
        // hands the same intent back, and must not open the microphone again
        // after the owner has switched listening off.
        if (savedInstanceState == null) readResumeListeningIntent(intent)
        readTileSettingsIntent(intent)

        setContent { App() }

        // Ask AFTER setContent, so there is a decor view to vote through on
        // API 35+. A high-refresh panel renders an app at 60 until it asks,
        // so every carefully paced frame in the reactor was landing on half
        // the vsyncs the hardware had available.
        DisplayRate.request(this, window.peekDecorView())
    }

    /**
     * `launchMode="singleTask"`, so a second tap on a notification re-delivers
     * the intent here rather than creating an activity. Without this override
     * the extra was read once, at cold start, and every later tap opened the
     * app on whatever screen it was last on — which for a decision request is
     * the same as the notification not being tappable.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readApprovalIntent(intent)
        readShareIntent(intent)
        readVoiceIntent(intent)
        readLiveIntent(intent)
        readHandoffIntent(intent)
        readQuickNoteIntent(intent)
        readBriefingIntent(intent)
        readLookIntent(intent)
        readShortcutQuestionIntent(intent)
        readResumeListeningIntent(intent)
        readTileSettingsIntent(intent)
    }

    /**
     * The assistant gesture's hand-off ([com.jarvis.client.assistant.
     * JarvisVoiceInteractionSession]): the look (or the reason for none) is
     * already in [ScreenLook] / the notice line; this only takes the owner to
     * Home, where the chip is. `singleTask`, so the `onNewIntent` half is
     * needed too.
     */
    private fun readLookIntent(intent: Intent?) {
        if (intent?.action != ACTION_OPEN_LOOK) return
        // Reopened from Recents, Android replays the intent that first opened
        // the task: that is not a new look.
        if ((intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) != 0) return
        openLookRequested.value = true
    }

    /**
     * The restart notice ([com.jarvis.client.data.WakeResume]). Only a flag:
     * listening starts in App(), after App lock, never from here.
     */
    private fun readResumeListeningIntent(intent: Intent?) {
        if (intent?.action != ACTION_RESUME_LISTENING) return
        // Reopened from Recents, Android replays the intent that first
        // opened the task: that is not a new tap.
        if ((intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) != 0) return
        resumeListeningRequestedAt.value = android.os.SystemClock.elapsedRealtime()
    }

    /** An empty Quick Settings tile slot: open Settings at the tile section. */
    private fun readTileSettingsIntent(intent: Intent?) {
        if (intent?.action != ACTION_OPEN_TILE_SETTINGS) return
        openTileSettingsRequested.value = true
    }

    /**
     * The "your morning briefing is ready" notification: open Mind, where the
     * briefing is. `singleTask`, so the `onNewIntent` half is needed too.
     */
    private fun readBriefingIntent(intent: Intent?) {
        if (intent?.action != ACTION_OPEN_BRIEFING) return
        openBriefingRequested.value = true
    }

    /**
     * The "Brief me now" and "What did I miss?" app-icon shortcuts
     * (res/xml/shortcuts.xml, [AppShortcuts]): Home, asking that sentence.
     * `singleTask`, so the `onNewIntent` half is needed too.
     */
    private fun readShortcutQuestionIntent(intent: Intent?) {
        val question = AppShortcuts.questionFor(intent?.action) ?: return
        shortcutQuestion.value = question
    }

    /**
     * The home-screen widget's Note button: open the app on Home with the
     * quick-note field open. `singleTask`, so the `onNewIntent` half is
     * needed too, same as [readVoiceIntent].
     */
    private fun readQuickNoteIntent(intent: Intent?) {
        if (intent?.action != ACTION_QUICK_NOTE) return
        quickNoteOpen.value = true
    }

    private fun readApprovalIntent(intent: Intent?) {
        if (intent?.action != ApprovalNotifier.ACTION_OPEN_APPROVAL) return
        focusApproval.value = intent.getStringExtra(ApprovalNotifier.EXTRA_APPROVAL_ID) ?: ""
    }

    /**
     * `singleTask`, so a second tap on the widget's Mic action while the app
     * is already open re-delivers here rather than starting a new instance -
     * same reason [readApprovalIntent] needs the `onNewIntent` half too.
     */
    private fun readVoiceIntent(intent: Intent?) {
        if (intent?.action != ACTION_START_VOICE) return
        startVoiceRequested.value = true
    }

    /**
     * The Jarvis Live notification: its screen (behind the app lock, as
     * ever). The Quick Settings tile and the "Resume" notification also
     * start Live - the owner's own tap - once the app is unlocked.
     */
    private fun readLiveIntent(intent: Intent?, fresh: Boolean = true) {
        // MainActivity is exported, so any app can send these actions. START
        // and RESUME need this app's own proof (InternalLaunch); without it
        // they only open the Live screen, where the owner presses Start.
        val what = InternalLaunch.decide(
            intent?.action,
            intent?.getStringExtra(InternalLaunch.EXTRA_PROOF),
            InternalLaunch.token(this),
            fresh,
        )
        when (what) {
            InternalLaunch.Launch.OPEN_LIVE_SCREEN -> openLiveRequested.value = true
            InternalLaunch.Launch.START_LIVE -> startLiveRequested.value = "start"
            InternalLaunch.Launch.RESUME_LIVE -> startLiveRequested.value = "resume"
            else -> Unit
        }
    }

    /** The "a website needs you" alert: the Solve it here screen (behind the app lock, as ever). Needs this app's own proof. */
    private fun readHandoffIntent(intent: Intent?) {
        val what = InternalLaunch.decide(
            intent?.action,
            intent?.getStringExtra(InternalLaunch.EXTRA_PROOF),
            InternalLaunch.token(this),
            true,
        )
        if (what != InternalLaunch.Launch.OPEN_HANDOFF) return
        openHandoffRequested.value = true
    }

    /**
     * `singleTask`, so a second share while the app is already open re-delivers
     * here rather than starting a new instance - same reason [readApprovalIntent]
     * needs the `onNewIntent` half too.
     */
    private fun readShareIntent(intent: Intent?, fresh: Boolean = true) {
        if (intent?.action != Intent.ACTION_SEND) return
        // "Talk about this in Live": the same share, through the second
        // entry (activity-alias ShareToLive). Text only; held for the Live
        // screen, never sent on its own.
        if (intent.component?.className?.endsWith(SHARE_TO_LIVE) == true) {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
            if (fresh && !text.isNullOrEmpty()) liveSharedText.value = text
            return
        }
        if (intent.type == "text/plain") {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
            if (!text.isNullOrEmpty()) sharedText.value = text
            return
        }
        // One photo. Its words, if the other app sent some, become the
        // Shared text chip; the photo is attached only if the Photo button would be
        // offered (see the LaunchedEffect on sharedPicture in App()).
        if (!ChatPicture.isSharedImage(intent.type)) return
        val uri = intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java) ?: return
        intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()?.takeIf { it.isNotEmpty() }
            ?.let { sharedText.value = it }
        sharedPicture.value = uri
    }

    /**
     * Today, as a plain `YYYY-MM-DD` - what "not now" on the sleep offer
     * actually promises to remember, and for how long. See `sleepOfferDismissedOn`
     * below: the old `Boolean` this replaces made a dismissal permanent, because
     * `rememberSaveable` survives exactly the kind of process death - the OS
     * reclaiming a backgrounded app under memory pressure - that this offer is
     * ABOUT. A user who dismissed it once could open the app two days later,
     * have Android hand back the saved `true` from before, and never see the
     * offer again until they cleared app data. Recomputed on each call rather
     * than cached: a value fixed at first composition would miss the day
     * actually rolling over while the app sits open past midnight.
     */
    private fun todayLocal(): String = java.time.LocalDate.now().toString()

    /**
     * The "hey Jarvis" switches, for Settings, Voice. They used to sit on
     * Platform checks (settings audit, 2026-09-30, "move them and add a jump
     * list"): a desktop with the same list keeps them in Settings, Voice, and a
     * check is something to read, not a place to change how Jarvis listens.
     * Everything here is what that branch already did - the same calls, the same
     * approval card for turning the desktop's switch on, the same "off is at once".
     */
    @Composable
    private fun VoiceSwitches() {
        val voice = JarvisRuntime.voice
        val voiceStatus by voice.status.collectAsState()
        val wakeWord by voice.wakeWord.collectAsState()
        val phoneListening by WakeWordService.state.collectAsState()
        val interruptChoice by JarvisRuntime.settings.interrupt.collectAsState()
        val oneMomentOn by JarvisRuntime.settings.oneMoment.collectAsState()
        val heardSoundOn by JarvisRuntime.settings.heardSound.collectAsState()
        // Asked once: whether this phone has an echo canceller at all. It
        // decides the barge-in default.
        val echoCanceller = remember {
            runCatching { AcousticEchoCanceler.isAvailable() }.getOrDefault(false)
        }
        var wakeBusy by remember { mutableStateOf(false) }
        var wakeNotice by remember { mutableStateOf<String?>(null) }
        // Why the restart notice could not start listening (data/WakeResume.kt):
        // shown once, under the switch.
        LaunchedEffect(resumeListeningNotice.value) {
            resumeListeningNotice.value?.let {
                wakeNotice = it
                resumeListeningNotice.value = null
            }
        }
        // The desktop's switch went off (from here, the desktop, or a restart):
        // this phone stops too. The listener also checks for itself every few
        // minutes.
        LaunchedEffect(wakeWord) {
            if (wakeWord == WakeWord.OFF && WakeWordService.state.value.on) {
                WakeWordService.stop(this@MainActivity)
            }
        }
        // Asked on arrival: a stale answer is the wrong thing to be reassured by.
        LaunchedEffect(Unit) { voice.refreshStatus() }

        WakeWordSwitchesCard(
            state = wakeWord,
            busy = wakeBusy,
            notice = wakeNotice,
            onTurnOff = {
                if (!wakeBusy) {
                    wakeBusy = true
                    wakeNotice = null
                    // This phone first: off must never wait on the network to
                    // close a microphone.
                    WakeWordService.stop(this@MainActivity)
                    lifecycleScope.launch {
                        wakeNotice = voice.setWakeWord(false)
                        wakeBusy = false
                    }
                }
            },
            onRecheck = {
                if (!wakeBusy) {
                    wakeBusy = true
                    lifecycleScope.launch {
                        voice.refreshStatus()
                        wakeBusy = false
                    }
                }
            },
            // Raises the approval card; turns nothing on.
            onTurnOn = {
                if (!wakeBusy) {
                    wakeBusy = true
                    wakeNotice = null
                    lifecycleScope.launch {
                        wakeNotice = voice.setWakeWord(true)
                        wakeBusy = false
                    }
                }
            },
            pending = voiceStatus.listening.wakeWordPending,
            phone = phoneListening,
            onPhone = { on ->
                if (on) {
                    wakeNotice = startPhoneListening()
                } else {
                    WakeWordService.stop(this@MainActivity)
                }
            },
            interrupt = interruptChoice,
            bargeInEchoCanceller = echoCanceller,
            // A setting on this phone only: it changes when the phone listens,
            // never what the desktop allows.
            onInterrupt = { v -> JarvisRuntime.settings.setInterrupt(v) },
            // Also this phone's own: whether "One moment." is played when a tool
            // starts during a spoken question.
            oneMoment = oneMomentOn,
            onOneMoment = { on -> JarvisRuntime.settings.setOneMoment(on) },
            // And whether the "I heard you" sound plays.
            heardSound = heardSoundOn,
            onHeardSound = { on -> JarvisRuntime.settings.setHeardSound(on) },
        )
    }

    @Composable
    private fun App() {
        // Before anything else, and before touching the runtime: if startup
        // failed, everything below this would fail with it.
        startupError.value?.let { trace ->
            CrashScreen(
                title = "Jarvis could not start",
                detail = trace,
                onDismiss = { finish() },
                // It closes the app, so it says so. "Continue" here promised
                // an app that was not going to appear.
                dismissLabel = "Close app",
            )
            return
        }
        if (!JarvisRuntime.isInitialized) {
            CrashScreen(
                title = "Jarvis could not start",
                detail = "The runtime reported that it never initialised, and did not say why.",
                onDismiss = { finish() },
                dismissLabel = "Close app",
            )
            return
        }
        lastCrash.value?.let { trace ->
            CrashScreen(
                title = "Jarvis stopped unexpectedly",
                detail = trace,
                onDismiss = {
                    CrashLog.clear(this@MainActivity)
                    lastCrash.value = null
                },
            )
            return
        }

        val scope = rememberCoroutineScope()
        // Both live in the runtime now: the voice loop drives chat from
        // outside any activity, and a `remember` does not survive a rotation —
        // so a turn in flight used to lose its reply when the phone turned.
        val chat = JarvisRuntime.chat
        val voice = JarvisRuntime.voice
        val appearance = JarvisRuntime.appearance

        val nav = rememberNavState()
        NavBackHandler(nav)

        // Saveable, unlike before: a rotation on the checks screen used to be
        // able to bounce a paired device back to pairing, because this was the
        // one flag of the three that was not saved.
        var paired by rememberSaveable { mutableStateOf(JarvisRuntime.isPaired()) }
        // Pairing AGAIN, with a desktop already paired. `paired` stays true the
        // whole time: the saved desktop and token are still the ones in use,
        // and remain so unless the new ones connect (see onPair below). Before
        // this existed `paired` could only ever become true, so once paired the
        // pairing screen was unreachable - while the app's own BadToken message
        // told the owner to "paste it again". Saveable for the same reason
        // `paired` is: a rotation must not drop the owner out of the screen
        // they are typing into.
        var repairing by rememberSaveable { mutableStateOf(false) }
        // The address being typed on the pairing screen, held here rather than
        // inside it. The screen leaves composition when the owner opens Platform
        // checks or Help, and it used to take the typed address with it; Checks
        // then judged the saved one, usually blank. Only ever written to
        // settings by onPair, as before. Not a secret - the token is not here.
        var pairingHost by rememberSaveable { mutableStateOf(JarvisRuntime.settings.host.value) }
        // Set once the pairing screen has been brought back for the current
        // token refusal, so "Keep current desktop" is not overruled a moment
        // later by the same refusal. Cleared when the refusal clears.
        var tokenRefusalHandled by rememberSaveable { mutableStateOf(false) }
        // Deliberately NOT saveable, unlike `paired` above - see
        // [pairingBusy] for why it lives outside the composition instead.
        var busy by pairingBusy
        var draft by rememberSaveable { mutableStateOf("") }
        // Whether the draft counts as pasted into: one edit put more than 40
        // characters in, since the box was last empty (Provenance.pastedAfter).
        // Sent as the question's `provenance` - chat history, JARVIS-API.md
        // section 18. Saveable alongside the draft it describes.
        var draftPasted by rememberSaveable { mutableStateOf(false) }
        // Text shared from another app, held apart from the draft as the
        // "Shared text" chip above the box, and sent as its OWN message,
        // tagged "shared", right before the owner's typed one (section 18).
        // It used to be appended into the draft, where it became - to the
        // PC - the owner's own words.
        var sharedHeld by rememberSaveable { mutableStateOf<String?>(null) }

        // A share from another app's share sheet arrives as an Intent extra,
        // not through the runtime, so it is picked up here rather than sent
        // on its own — the owner still decides when and whether to send it.
        // Joined to any share already held, so a share never eats another,
        // and never touches what is being typed.
        LaunchedEffect(sharedText.value) {
            val text = sharedText.value ?: return@LaunchedEffect
            sharedHeld = Provenance.joinShared(sharedHeld, text)
            sharedText.value = null
            nav.resetTo(Screen.HOME)
        }

        // A photo shared from another app: attached under the Photo button's
        // own rule, asked fresh - only while the PC says Pictures works - or
        // refused in words, never dropped silently. Nothing is sent here; the
        // owner still types the question and taps Send, which checks again.
        LaunchedEffect(sharedPicture.value) {
            val uri = sharedPicture.value ?: return@LaunchedEffect
            sharedPicture.value = null
            nav.resetTo(Screen.HOME)
            JarvisRuntime.refreshSecondCard()
            val refusal = ChatPicture.sharedRefusal(JarvisRuntime.secondCard.value)
            if (refusal != null) JarvisRuntime.setNotice(refusal) else attachPicture(uri)
        }

        var memoryDecideBusyId by remember { mutableStateOf<Long?>(null) }
        // The daily overnight-tidy card, cached the first time it is seen.
        // See BrainScreen.kt's own doc comment on `sleepOffer`: the server
        // marks the day's offer as made the moment a read asking for it
        // (sleep_offer=1) arrives, so a second read - which refreshBrain() triggers
        // after every OTHER memory write - would otherwise make the card
        // vanish before the owner had a chance to read it. `dismissed` is a
        // separate flag from clearing the cache, so a later recomposition
        // reading the same still-cached server data cannot re-adopt an offer
        // just turned down.
        //
        // `sleepOfferDismissedOn` is still rememberSaveable, like `paired`
        // above, so a rotation can't resurrect a card the owner deliberately
        // turned down - but it is now set ONLY on a durable answer: a local
        // dismiss, or a write that actually came back. A write still in flight
        // is held in `sleepOfferAnswering`, which is plain `remember` on
        // purpose, because the rollback that clears it runs in `scope.launch`
        // and dies with the composition. Rotating mid-write used to save
        // `dismissed = true` while cancelling both the request and its
        // rollback: the setting was never written and the card was gone until
        // tomorrow. The suppressing flag and the work it belongs to now share
        // a lifetime, so a rotation re-offers the card instead of eating it.
        // `cachedSleepOffer` stays plain `remember`: a raw
        // JsonObject isn't Bundle-saveable, and it doesn't need to be - the
        // LaunchedEffect(brain.memory) block below re-populates it from the
        // still-cached server data on the next recomposition, and the
        // survived `dismissed` flag is what stops that from re-adopting the
        // offer just turned down.
        var cachedSleepOffer by remember { mutableStateOf<JsonObject?>(null) }
        // A date string, not a bare Boolean - "not now" means not now, not
        // forever. See [todayLocal]'s own doc comment for the bug a plain
        // Boolean had: rememberSaveable outlives the exact process death
        // this offer exists to survive, so a dismissal from two nights ago
        // read back as "still dismissed" on a night the server had raised a
        // brand new offer.
        var sleepOfferDismissedOn by rememberSaveable { mutableStateOf<String?>(null) }
        val sleepOfferDismissedToday = sleepOfferDismissedOn == todayLocal()
        /** A write is in flight - suppress re-adoption, but never across a rotation. */
        var sleepOfferAnswering by remember { mutableStateOf(false) }
        var sleepOfferBusy by remember { mutableStateOf(false) }

        val tick = permissionTick.intValue
        // The one-time "Background restart" offer (walk-through C9): while it
        // waits and Android has not already allowed it. `tick` moves on every
        // return to the app, so coming back from Android's own dialog with it
        // allowed takes the line away.
        val keepAlivePending by JarvisRuntime.settings.keepAliveOfferPending.collectAsState()
        val keepAliveOfferShown = remember(tick, keepAlivePending) {
            keepAlivePending && !PlatformReadiness.batteryExempt(this@MainActivity)
        }
        val chrome by appearance.chrome.collectAsState()
        val followSystem by appearance.followSystem.collectAsState()
        val faceId by appearance.faceId.collectAsState()
        val bindings by appearance.bindings.collectAsState()
        val faceSize by appearance.faceSize.collectAsState()
        // Everything else about how this phone looks, as one record - see
        // AppearanceStore.look. Read below by the theme, Home and Appearance.
        val look by appearance.look.collectAsState()
        // The dark theme Follow the system returns to at dusk (custom-8).
        val preferredDark by appearance.preferredDark.collectAsState()
        // The face editor's quality, frame rate, speed, Auto adjust and
        // Battery saver. Phone-only - see AppearanceStore.faceTuning.
        val faceTuning by appearance.faceTuning.collectAsState()
        // "Keep the animal still", shared with the desktop since 2026-09-28
        // (kept on the PC): the PC's value once heard, else - or until this
        // phone's old "on" has reached the PC - this phone's own old switch.
        val animalShared by appearance.animal.collectAsState()
        val animalMigrated by appearance.animalMigrated.collectAsState()
        val stillAnimal = com.jarvis.client.net.AnimalOptions.effectiveStill(
            animalShared, look.stillAnimal, animalMigrated,
        )

        // Android's own Battery Saver, and how hot the phone is, for the face
        // editor's Battery saver (which turns itself on while Android's is on)
        // and Auto adjust (which lowers its ceiling when the phone is hot).
        // Listened for, so the face changes the moment either does.
        var phoneSaver by remember { mutableStateOf(false) }
        var phoneHeat by remember { mutableIntStateOf(0) }
        DisposableEffect(Unit) {
            val stop = PowerWatch.watch(this@MainActivity) { saver, heat ->
                phoneSaver = saver
                phoneHeat = heat
            }
            onDispose { stop() }
        }
        // Everything FaceView draws with comes through here: the one live
        // budget, FaceQuality, re-resolved whenever a setting or the phone's
        // state changes. Nothing here reaches the desktop. A SideEffect, not a
        // LaunchedEffect, so it lands before the next frame is drawn rather
        // than a frame or two after it - and it is a cheap comparison when
        // nothing changed.
        SideEffect { FaceQuality.configure(faceTuning, phoneSaver, phoneHeat) }

        // The lock and fingerprint settings, and the lock clock. `lockTick`
        // is read here so that every change to the clock recomposes.
        val security by JarvisRuntime.settings.security.collectAsState()
        // True only while the pairing screen shows the typed token in plain
        // letters. Plain `remember`: never saved, starts hidden.
        var pairingKeyShown by remember { mutableStateOf(false) }
        val lockVersion = lockTick.intValue
        val locked = remember(lockVersion, security) { lockSession.locked(security) }
        val privateHidden = remember(lockVersion, security) { lockSession.privateHidden(security) }
        // The runtime reads no chat history for "Move it here" while the lists are
        // hidden (the second chat audit, phone C12): the desktop refuses in Rust.
        SideEffect { JarvisRuntime.privateListsHidden = privateHidden }
        // While App lock or "Hide memory lists and chat history" is on, Jarvis
        // cannot be screenshotted, screen-recorded or cast, and its
        // recent-apps picture is blank rather than a snapshot of what the
        // lock hides (SecurityRules.blockScreenCapture; apps security audit
        // L5). Compose dialogs and popups inherit FLAG_SECURE from this
        // window (their securePolicy defaults to Inherit). Both are undone
        // the moment both settings are off.
        // And while the pairing token is shown in plain letters on the
        // pairing screen ("Show token"): set by PairingScreen, and back to
        // false the moment it is hidden or the screen goes.
        // And while "Solve it here" shows a picture of the PC's browser
        // window (it is never saved, so it must not be screenshotted either).
        val handoffShown = nav.current == Screen.HANDOFF
        // And while an approval card shows the picture of a web form Jarvis
        // filled in (FormReview; the card raises this before it asks for it).
        val formPictureShown = com.jarvis.client.net.FormReview.shown.collectAsState().value > 0
        LaunchedEffect(security.appLock, security.privateLists, pairingKeyShown, handoffShown, formPictureShown) {
            val secure = SecurityRules.blockScreenCapture(
                security,
                keyShown = pairingKeyShown,
                handoffShown = handoffShown,
                formPictureShown = formPictureShown,
            )
            setRecentsScreenshotEnabled(!secure)
            if (secure) {
                window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
            } else {
                window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
            }
        }

        // "Floating Jarvis" (data/FloatingAvatar.kt, JARVIS-API §56): the
        // Overlay path is a foreground service, kept in step with the
        // setting and the permission itself here, at the top of App() -
        // like `security` above, rather than nested under Screen.SETTINGS -
        // because the whole point of an overlay is that it outlives whatever
        // screen is on top. `tick` is `permissionTick` (read further up):
        // "draw over other apps" can be revoked in Android's own Settings at
        // any time, and this is what notices that on return.
        val floatingAvatar by JarvisRuntime.settings.floatingAvatar.collectAsState()
        // Settings -> Quick Settings tiles (data/QuickTiles.kt): this phone only.
        val quickTiles by JarvisRuntime.settings.quickTiles.collectAsState()
        LaunchedEffect(floatingAvatar, tick) {
            if (floatingAvatar == FloatingAvatarMode.OVERLAY &&
                Settings.canDrawOverlays(this@MainActivity)
            ) {
                AvatarOverlayService.start(this@MainActivity)
            } else {
                AvatarOverlayService.stop(this@MainActivity)
            }
        }

        // "A newer version is available": asked when the app opens (at most
        // every six hours) and once a day while it stays open. Never while
        // "Check for new versions" is off. See UpdateCheck.
        val updateState by JarvisRuntime.updates.state.collectAsState()
        val updateChecks by JarvisRuntime.settings.updateChecks.collectAsState()
        LaunchedEffect(updateChecks) {
            if (!updateChecks) return@LaunchedEffect
            JarvisRuntime.updates.checkIfDue(onStart = true)
            while (true) {
                delay(UPDATE_RECHECK_MS)
                JarvisRuntime.updates.checkIfDue(onStart = false)
            }
        }

        val link by JarvisRuntime.link.collectAsState()
        val linkDetail by JarvisRuntime.linkDetail.collectAsState()
        // "Tailscale (or Meshnet) is off on this phone", under a link that is
        // down, when Android says no VPN is up and the saved address needs
        // one (LinkWords.vpnOffLine). A hint only; it decides nothing.
        val vpnUp by JarvisRuntime.vpnUp.collectAsState()
        val savedHost by JarvisRuntime.settings.host.collectAsState()
        val vpnLine = LinkWords.vpnOffLine(savedHost, link, vpnUp)
        val stale by JarvisRuntime.stale.collectAsState()
        val activity by JarvisRuntime.activity.collectAsState()
        val faceState by JarvisRuntime.face.collectAsState()
        val faceOffline by JarvisRuntime.faceOffline.collectAsState()
        val faceFocusQuiet by JarvisRuntime.faceFocusQuiet.collectAsState()
        val faceSerious by JarvisRuntime.faceSerious.collectAsState()
        val power by JarvisRuntime.power.collectAsState()
        val lockdown by JarvisRuntime.lockdown.collectAsState()

        // "Photo to reminder": the PC's proposal for the attached picture.
        // Nothing is set up until one of its buttons is tapped; the add is
        // held on a stale link here and in the runtime. Never over App
        // lock's lock screen: nothing behind it is shown.
        photoScan.value?.takeIf { !locked }?.let { scan ->
            PhotoReminderDialog(
                scan = scan,
                canAct = link == LinkState.CONNECTED && !stale,
                onAdd = { what, date, time -> JarvisRuntime.addPhotoReminder(what, date, time) },
                onClose = { photoScan.value = null },
            )
        }
        val status by JarvisRuntime.status.collectAsState()
        val version by JarvisRuntime.version.collectAsState()
        val pending by JarvisRuntime.pending.collectAsState()
        // Collected here, and carried in HomeState below, for two reasons.
        //
        // The plain one: the approve and deny buttons must grey out while a
        // decision is in flight, or a second tap sends the same decision twice
        // and asks for a fingerprint twice.
        //
        // The load-bearing one: `blockerFor` calls decisionBlocker(), which
        // reads `_deciding.value` / `_stale.value` / `_link.value` off the
        // MutableStateFlows directly. Reading `.value` on a flow inside
        // composition is NOT a snapshot read and subscribes to nothing, so on
        // its own that answer would never be recomputed. It works only because
        // `stale`, `link` and now `deciding` are collected here and live in
        // HomeState: a change in any of them rebuilds the state and re-runs
        // `blockerFor`. Do not delete these fields for looking unread - they
        // ARE the subscription.
        val deciding by JarvisRuntime.deciding.collectAsState()
        val attention by JarvisRuntime.attention.collectAsState()
        val notice by JarvisRuntime.notice.collectAsState()
        // Whether the last POST of the shared face/colours landed - null until
        // one is tried. The Appearance screen's own paragraph says whether the
        // desktop has them (finding A1), and a flow rather than `.value`
        // because the send finishes after the frame that drew the claim.
        val appearanceSent by JarvisRuntime.appearanceSent.collectAsState()
        // The failure behind the notice, in plain words, with its fix button
        // and scrubbed Details - only while the notice on screen IS it.
        val noticeProblem by JarvisRuntime.problem.collectAsState()
        val shownProblem = noticeProblem?.takeIf { notice != null && it.text == notice }
        val digest by JarvisRuntime.digest.collectAsState()
        val undo by JarvisRuntime.undo.collectAsState()
        val jobs by JarvisRuntime.jobs.collectAsState()
        val pastApprovals by JarvisRuntime.pastApprovals.collectAsState()
        // How each Inbox list's last read came back, so the screen can tell
        // "nothing waiting" apart from "could not read" (screens-3).
        val inboxRead by JarvisRuntime.inboxRead.collectAsState()
        val brain by JarvisRuntime.brain.collectAsState()
        val models by JarvisRuntime.models.collectAsState()
        // The phone's own last successful `GET /api/models` read, held on
        // disk so Brain -> Model has something to show, clearly marked as
        // old, when [models] above is null because the live read failed
        // (docs/OFFLINE-MODELS-DESIGN-2026-09-27.md).
        val modelsCache by JarvisRuntime.modelsCache.collectAsState()
        val activityDetail by JarvisRuntime.activityDetail.collectAsState()
        var modelBusy by remember { mutableStateOf(false) }
        // The second graphics card: what the PC last said, which switch has a
        // request out, and what that request came back with - held like the
        // wake word's busy/notice pair, for the same reason.
        val secondCard by JarvisRuntime.secondCard.collectAsState()
        val noteTargets by JarvisRuntime.noteTargetsKnown.collectAsState()
        var secondCardBusy by remember { mutableStateOf<String?>(null) }
        var secondCardNotice by remember { mutableStateOf<String?>(null) }
        // Held here rather than in JarvisRuntime: a one-shot read the Brain
        // screen asks for, thrown away the moment a different date is asked
        // for - not app state anything else reads.
        var memoryAsOfResult by remember { mutableStateOf<JsonObject?>(null) }
        var memoryAsOfBusy by remember { mutableStateOf(false) }
        val absent by JarvisRuntime.absent.collectAsState()
        val streaming by chat.streaming.collectAsState()
        val voicePhase by voice.phase.collectAsState()
        val voiceStatus by voice.status.collectAsState()
        // The stricter voice check, from the same status read.
        val voiceStrict by voice.strict.collectAsState()
        val transcript by voice.transcript.collectAsState()
        val voiceNotice by voice.notice.collectAsState()
        // Held as State and read only inside drawBehind — a microphone
        // delivers ~50 levels a second and this must not recompose anything.
        val micLevelState = voice.micLevel.collectAsState()
        val micLevel = remember { derivedStateOf { micLevelState.value ?: 0f } }
        // Kept nullable all the way to the face: null is "no voice is playing",
        // which is what makes the face fall back to its own envelope, and 0f is
        // "a voice is playing and is silent", which does not.
        val speechLevel = voice.speaker.level.collectAsState()
        // The voice at the moment being heard, for the face's frame loop -
        // a plain function it calls each frame, not state: nothing recomposes.
        val speechMouth = remember(voice) { voice.speaker::mouthNow }

        // Collected, not read. `chat.reply` is a StateFlow, and reading
        // `.value` in a composable is not a snapshot read — so nothing
        // subscribed and no chunk ever invalidated anything. The reply sat at
        // "…" for the whole generation and appeared all at once when the stream
        // closed, which is the exact opposite of what a chunked body is for.
        //
        // Held as State and read inside Reply's own scope, so the subscription
        // lands there: a token recomposes the reply and nothing else, which is
        // what the lambda was reaching for in the first place.
        val replyState = chat.reply.collectAsState()
        // The owner's last question, for Home's "You" line above the reply.
        // In memory only - ChatSession never writes it to disk.
        val lastQuestion by chat.question.collectAsState()
        // The answer's id (`turn_id`) and the owner's mark on it, for the
        // Right / Wrong buttons under the answer. Ids only, memory only.
        val answerTurnId by chat.turnId.collectAsState()
        // The spending table's id under that answer (an id only; the table is
        // fetched and held in memory by the screen that draws it).
        val answerTableId by chat.tableId.collectAsState()
        // The conversation the next question carries (ChatHistory). Only its
        // size is shown; memory only, like the question itself.
        val conversation by chat.history.collectAsState()
        // What Home shows of the conversation (the whole thread, the chat
        // audit 2026-09-28), and its one quiet line. Memory only.
        val thread by chat.thread.collectAsState()
        val chatNote by chat.chatNote.collectAsState()
        // Whether this conversation read outside text, and whether the chat is a
        // game (the PC made it temporary) - both from the chat, memory only.
        val readOutsideChat by chat.readOutside.collectAsState()
        val gameChat by chat.game.collectAsState()
        // The chat has gone quiet for 30 minutes: re-read every 30 seconds
        // while there is a conversation, so the line under the reply is true
        // without waiting for the next redraw (the second chat audit, phone C1).
        val idleQuiet by produceState(false, conversation.size) {
            while (true) {
                value = chat.idleNow()
                delay(30_000)
            }
        }
        // Did the question on screen get an answer? Read as a boolean so a
        // streamed word does not redraw the screen.
        val answeredNow by remember { derivedStateOf { replyState.value.isNotBlank() } }
        // What a turn is waiting on ("Waiting for your approval…"), and the
        // one line under a finished answer (cut short / from a cloud model).
        val chatWaiting by chat.waiting.collectAsState()
        val answerNote by chat.answerNote.collectAsState()
        // A temporary chat, and the facts the answer on screen used (ids
        // only) - docs/JARVIS-API.md sections 18.1 and 4, 2026-09-25.
        val temporaryChat by chat.temporary.collectAsState()
        val usedIds by chat.usedIds.collectAsState()
        // Topic controls (2026-09-30): how many facts the owner's topic settings kept out
        // of the answer on screen - a count only ([com.jarvis.client.net.Topics]).
        val topicsLeftOut by chat.topicsLeftOut.collectAsState()
        // The crisis help line (jarvis_wellbeing.py, 2026-09-27): whether
        // the answer on screen is shown as a calm, plain panel.
        val crisisAnswer by chat.crisis.collectAsState()
        // "A cloud model could give this one a second look."
        // (jarvis_router.choose()'s gate "offer", docs/JARVIS-API.md,
        // "`offer` in `X-Jarvis-Route`") - the lane named on the answer on
        // screen's route, or null.
        val cloudOffer by chat.cloudOffer.collectAsState()
        // "Inbox tidy by voice" (2026-09-28; docs/JARVIS-API.md section 95):
        // the newest tidy still open to Undo, as the PC last said - its
        // minutes run down on the runtime's clock, and an Undo whose ten
        // minutes are up is gone even while the link is down.
        val inboxTidyHeld by JarvisRuntime.inboxTidy.collectAsState()
        val inboxTidyClock by JarvisRuntime.inboxTidyClock.collectAsState()
        val inboxTidyBusy by JarvisRuntime.inboxTidyBusy.collectAsState()
        // The chip for a look at this phone's screen, held for the next
        // question ("Looked at: Chrome screen · words only"), or null. Only
        // the app's name and how it was read - never the words themselves.
        val lookLine by com.jarvis.client.net.ScreenLook.line.collectAsState()
        // The PC's "Watch with me", said on this phone too. "Watching ended"
        // is not shown here (endedAgo is past its display time): it is a
        // notice for the screen being watched, and the sign just goes away.
        // ...and this phone's own Watch session: its sign counts its minutes
        // down, so it is re-read every 20 seconds while it is on.
        val phoneWatch by com.jarvis.client.net.ScreenWatch.state.collectAsState()
        val phoneWatchTick by produceState(0L, phoneWatch.on) {
            if (!phoneWatch.on) return@produceState
            while (true) {
                value = System.nanoTime()
                delay(20_000)
            }
        }
        val phoneWatchSign = remember(phoneWatch, phoneWatchTick) {
            com.jarvis.client.net.ScreenWatch.sign(s = phoneWatch)
        }
        val screenWatch by JarvisRuntime.screenWatch.collectAsState()
        val watchSign = remember(screenWatch, link) {
            com.jarvis.client.net.ScreenRules.sign(
                screenWatch,
                stale = link != LinkState.CONNECTED,
                endedAgo = com.jarvis.client.net.ScreenRules.ENDED_SHOW_S,
            ).takeIf { it.show }
        }
        // "Open <a settings section>" by voice or chat
        // (jarvis_settings_registry.py, docs/JARVIS-API.md section 58.1):
        // jump to Settings, at the section the answer named. Pure
        // navigation - SettingsScreen's own `initialSection` does the
        // scrolling; nothing here changes a setting.
        //
        // Bug audit 2026-09-27, finding #4: a `LaunchedEffect` reruns every
        // time it first enters a fresh composition, not only when its key
        // changes - and nothing used to clear `chat.openSettings` once it
        // had been acted on, so a rotation (or any other activity rebuild)
        // saw the same target again and jumped back into Settings on its
        // own. Treated as a one-time request instead: the target is copied
        // into `pendingSection` (kept across a rebuild by
        // `rememberSaveable`, just long enough for `SettingsScreen` to
        // scroll once) and immediately consumed on the `ChatSession` side,
        // so a fresh composition with the same underlying answer sees null
        // and does nothing.
        //
        // Phone walk-through, 2026-09-27: not every section lives on the
        // phone's Settings screen. "Open help", "connection", "morning
        // briefing", "about" or "Jarvis's voices" all used to land at the top
        // of Settings, which has none of them. OpenPlace now decides, per
        // section id, the phone's own screen and the item on it - or, for a
        // place only the PC app has (keyboard shortcuts, accounts, ...), a
        // plain notice saying so instead of a screen without it.
        //
        // `pendingSectionScreen` names the ONE screen the section is for, and
        // only that screen is handed it: during the fade between screens the
        // old and the new one are both composed, and a screen that was not
        // the target would otherwise "consume" the section first.
        val openSettingsTarget by chat.openSettings.collectAsState()
        var pendingSection by rememberSaveable { mutableStateOf<String?>(null) }
        var pendingSectionScreen by rememberSaveable { mutableStateOf<String?>(null) }
        fun sectionFor(screen: Screen): String? =
            if (pendingSectionScreen == screen.name) pendingSection else null
        val sectionConsumed: () -> Unit = {
            pendingSection = null
            pendingSectionScreen = null
        }
        LaunchedEffect(openSettingsTarget) {
            val target = openSettingsTarget ?: return@LaunchedEffect
            when (val where = OpenPlace.whereFor(target)) {
                is OpenPlace.Where.Go -> {
                    // A link to a menu the owner hid ("Show or hide menus") opens it for THIS visit
                    // only, before the screen is drawn; the screen ends the visit when it is left.
                    com.jarvis.client.ui.MenuPlaces.menuFor(where.screen.name, where.section)
                        ?.let { JarvisRuntime.menus.showForVisit(it) }
                    pendingSection = where.section
                    pendingSectionScreen = where.screen.name
                    nav.go(where.screen)
                }
                is OpenPlace.Where.OnPc -> JarvisRuntime.setNotice(where.notice)
            }
            chat.consumeOpenSettings()
        }
        // "Hide the finance menu" by voice or chat (X-Jarvis-Route `menu_visibility`,
        // docs/JARVIS-API.md section 109.2): per device, so the PC changed nothing and this phone
        // applies it to its own list - once, then it is consumed, like face_tuning below. Hiding
        // only tidies: no card, nothing turned off. A menu this phone does not have, and a
        // never-hideable one, are ignored (MenuLogic); the answer already said what was done.
        val menuChangeTarget by chat.menuChange.collectAsState()
        LaunchedEffect(menuChangeTarget) {
            val change = menuChangeTarget ?: return@LaunchedEffect
            JarvisRuntime.menus.apply(change.action, change.target)
            chat.consumeMenuChange()
        }
        // "Make the animal sharper" by voice or chat (X-Jarvis-Route
        // `face_tuning`, 2026-09-28): per device, so the PC changed nothing
        // and this phone applies it to its own face settings - once, then it
        // is consumed, like openSettings above. Said on screen only when
        // nothing could change ("already Maximum"); the answer itself already
        // says what was done.
        val faceTuningTarget by chat.faceTuningChange.collectAsState()
        LaunchedEffect(faceTuningTarget) {
            val change = faceTuningTarget ?: return@LaunchedEffect
            val step = com.jarvis.client.net.AnimalOptions.step(appearance.faceTuning.value, change)
            if (step.changed) {
                appearance.setFaceTuning(step.tuning)
            } else if (step.line.isNotBlank()) {
                JarvisRuntime.setNotice(step.line.replace("{device}", "this phone"))
            }
            chat.consumeFaceTuningChange()
        }
        // "Label my chat about the boiler as Home" (X-Jarvis-Route
        // `open_brain: "history"` with `file_under` and `history_q`,
        // docs/CHAT-TAGS-DESIGN.md section 10): open History with the search
        // filled in and a banner, and file NOTHING until the owner taps a
        // chat. Kept as two plain values so a rotation keeps the banner.
        val fileUnderTarget by chat.fileUnder.collectAsState()
        var filingTag by rememberSaveable { mutableStateOf<Int?>(null) }
        var filingQuery by rememberSaveable { mutableStateOf("") }
        LaunchedEffect(fileUnderTarget) {
            val target = fileUnderTarget ?: return@LaunchedEffect
            filingTag = target.tagId
            filingQuery = target.query
            nav.go(Screen.HISTORY)
            chat.consumeFileUnder()
        }
        // "Switch off my work topic" (X-Jarvis-Route `open_brain: "topics"` with
        // `topic_id`, docs/TOPIC-CONTROLS-DESIGN.md C4): Brain is opened at Topics by
        // the `open_settings` path above (OpenPlace, "topics"); the topic id goes to
        // the plate, which shows the four-choice picker and changes NOTHING until the
        // owner taps Change.
        val topicPickTarget by chat.topicPick.collectAsState()
        LaunchedEffect(topicPickTarget) {
            val target = topicPickTarget ?: return@LaunchedEffect
            JarvisRuntime.requestTopicPick(target)
            chat.consumeTopicPick()
        }
        // An empty Quick Settings tile slot was tapped: the same one-time
        // scroll, to "Quick Settings tiles".
        LaunchedEffect(openTileSettingsRequested.value) {
            if (!openTileSettingsRequested.value) return@LaunchedEffect
            openTileSettingsRequested.value = false
            JarvisRuntime.menus.showForVisit("settings.quick-tiles")
            pendingSection = QUICK_TILES_SECTION
            pendingSectionScreen = Screen.SETTINGS.name
            nav.resetTo(Screen.HOME)
            nav.go(Screen.SETTINGS)
        }
        val answerMark by JarvisRuntime.answerMark.collectAsState()

        val face = remember(faceId) { Faces.byId(faceId) }
        val idleColour = bindings.of(FaceState.IDLE).tint ?: com.jarvis.client.face.Palette.ICE_3

        // A chat failure used to be written to a StateFlow that nothing
        // collected, so a send that failed looked exactly like a send that was
        // still thinking — for ever.
        LaunchedEffect(chat) {
            chat.error.collectLatest {
                if (it == null) return@collectLatest
                // In plain words, with its fix button and Details, when the
                // chat put it that way (it always does now); else as it is.
                val p = chat.problem.value
                if (p != null && p.text == it) JarvisRuntime.setProblem(p) else JarvisRuntime.setNotice(it)
            }
        }

        // The panel is asked for its fastest rate only while the face is on
        // screen AND in a state that uses it - see DisplayRate.wantsHigh for
        // the whole rule. It used to follow the face's state alone, so reading
        // the Inbox during a long THINKING task held a 120 Hz panel at 120 for
        // a screen of still text, and ERROR held it until someone fixed the
        // error. Home is where the face is the thing being looked at;
        // Appearance's small preview does not need 120 Hz.
        //
        // A loop rather than a single call, but only while the answer can
        // still change on its own: THINKING drops the high rate after its
        // first seconds, and battery saver or heat can arrive at any time.
        // In every other state the loop exits after one pass.
        val faceOnScreen = paired && !repairing && nav.current == Screen.HOME
        // The face editor's Frame rate choice (and Battery saver) decide how
        // hard the panel is asked: see FaceBudget.smoothFor.
        val smooth = FaceBudget.smoothFor(faceTuning, phoneSaver)
        LaunchedEffect(faceState, faceOnScreen, smooth) {
            val enteredAt = SystemClock.elapsedRealtime()
            while (true) {
                val high = DisplayRate.wantsHigh(
                    state = faceState,
                    faceOnScreen = faceOnScreen,
                    msInState = SystemClock.elapsedRealtime() - enteredAt,
                    constrained = DisplayRate.constrained(this@MainActivity),
                    pref = smooth,
                )
                DisplayRate.setHigh(this@MainActivity, window.peekDecorView(), high)
                if (!DisplayRate.couldWantHigh(faceState, faceOnScreen, smooth)) break
                delay(RATE_RECHECK_MS)
            }
        }

        // When the desktop refuses the token, go back to the pairing screen
        // rather than leaving the owner on Home with an error that says "paste
        // it again" and nowhere to paste it.
        //
        // Two places report a refusal, and neither is a typed signal this file
        // can read: the stream's `linkDetail` (EventStream.kt writes exactly
        // "Token refused" for a 401/403) and a request's notice (JarvisRuntime
        // turns ApiError.BadToken into the sentence noticeFor returns). Both
        // are matched as the strings they are. If either wording changes this
        // stops firing - it fails towards "stays on Home", never towards
        // unpairing, because nothing here clears the saved token.
        val badTokenNotice = remember { JarvisRuntime.noticeFor(ApiError.BadToken) }
        // When the PC said WHY it refused the key (docs/PAIRING-DESIGN.md
        // section 5.3 - removed on the PC, or the old shared key retired),
        // the notice is that sentence instead (JarvisRuntime.describe), so it
        // is matched too, and the pairing screen shows it.
        val keyRefusalReason by com.jarvis.client.net.KeyRefusal.reason.collectAsState()
        val refusedWords = com.jarvis.client.net.KeyRefusal.words(keyRefusalReason) ?: badTokenNotice
        val tokenRefused = paired &&
            (linkDetail == TOKEN_REFUSED_DETAIL || notice == badTokenNotice ||
                com.jarvis.client.net.KeyRefusal.isWords(notice))
        LaunchedEffect(tokenRefused) {
            if (!tokenRefused) {
                tokenRefusalHandled = false
                return@LaunchedEffect
            }
            if (tokenRefusalHandled || repairing) return@LaunchedEffect
            tokenRefusalHandled = true
            pairingHost = JarvisRuntime.settings.host.value
            repairing = true
            nav.resetTo(Screen.HOME)
        }

        LaunchedEffect(brain.memory) {
            val offer = (brain.memory?.get("setup") as? JsonObject)
                ?.get("sleep_time_offer") as? JsonObject
            if (offer != null && cachedSleepOffer == null &&
                !sleepOfferDismissedToday && !sleepOfferAnswering
            ) {
                cachedSleepOffer = offer
            }
        }

        // "Follow the system" defers rather than fires.
        //
        // It can trigger at dusk, on an ambient-light change or when the OS
        // flips, and a ground that changes mid-approval is exactly the "is it
        // telling me something?" ambiguity the waiting clock exists to remove.
        // It also overlaps the 300ms state crossfade with the 500ms theme one,
        // which compounds two luminance ramps the flash governor cannot see.
        val systemDark = systemPrefersDark()
        val resting = faceState == FaceState.IDLE ||
            faceState == FaceState.STANDBY ||
            faceState == FaceState.BANKED
        // `chrome` is a key, not merely read inside. Without it, picking a
        // light theme by hand while following a dark system changed `chrome`
        // and nothing else, so this effect never re-ran: the app sat light
        // under a switch still claiming it followed the system. Keying on it
        // makes that divergence itself the trigger. It cannot spin: the
        // effect's own write restarts it exactly once, and the restarted pass
        // finds `want.id == chrome.id` and does nothing. The `while` below is
        // untouched - a refused theme change does not alter `chrome`, so the
        // dwell window is still waited out by the loop, not by a restart.
        //
        // `preferredDark` is a key too: picking a different "theme for dark
        // mode" while the phone is already dark should apply it now, not at
        // the next dusk. It used to be worked out from the current theme,
        // which is Daylight all day while following, so dusk always brought
        // back Reactor whatever the owner had picked (custom-8).
        LaunchedEffect(followSystem, systemDark, resting, chrome, preferredDark) {
            if (!followSystem || !resting) return@LaunchedEffect
            val want = Themes.forSystem(systemDark, preferredDark = preferredDark)
            // Retried, not dropped. `setTheme` refuses inside the dwell window
            // and returns false; that answer was discarded, and since none of
            // this effect's keys change again the theme simply stayed wrong
            // until something else happened to move it.
            while (want.id != chrome.id && !appearance.setTheme(want)) {
                delay(THEME_RETRY_MS)
            }
        }

        // Asked once per connection, before the button is offered. §4.1 says to
        // call it before offering a microphone at all, and the refusing
        // defaults mean a failure hides the button rather than showing one
        // that posts audio into a 404.
        LaunchedEffect(link, paired, version) {
            // Gated on the capability before the call, not just on the answer.
            // §2 says a capability reporting false means hide the UI for it —
            // asking a backend without a voice path for its voice status is the
            // request-that-404s that rule exists to prevent.
            if (paired && link == LinkState.CONNECTED && JarvisRuntime.can("voice")) {
                voice.refreshStatus()
            }
        }

        // Asked once per process, the first time there is somewhere to talk
        // to — not at launch.
        //
        // On the pairing screen there is nothing to announce yet, and a
        // permission dialog before an app has shown what it is for is the one
        // people refuse out of hand. Once pairing succeeds the app has
        // approvals to announce, which is the entire reason it wants this.
        //
        // Re-asking on the next cold launch is deliberate and self-limiting:
        // Android stops showing the dialog after the second refusal and just
        // returns "denied" instantly, so this is at most two real prompts ever.
        // The Checks screen still has its own button for anyone who got that
        // far and wants to change their mind.
        //
        // minSdk is 33, so POST_NOTIFICATIONS exists on every device that can
        // install this app — no version guard needed here.
        LaunchedEffect(paired) {
            if (!paired || askedForNotifications) return@LaunchedEffect
            if (PlatformReadiness.notificationsGranted(this@MainActivity)) return@LaunchedEffect
            askedForNotifications = true
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        // A notification tap goes straight home, so the card is where the
        // finger already is - and the id now travels into HomeState, so the
        // list scrolls to that card and outlines it. It used to be cleared
        // right here, one line after being set, which is why nothing ever read
        // it: the tap navigated home and left you a list to hunt through.
        LaunchedEffect(focusApproval.value, locked) {
            val id = focusApproval.value ?: return@LaunchedEffect
            // Behind the app lock, the card is kept until the owner unlocks,
            // rather than scrolled to and dropped while nobody can see it.
            if (locked) return@LaunchedEffect
            // A tap on an approval notification means "show me that card", and
            // the pairing screen would hide it. The desktop in use is the saved
            // one either way, so leaving re-pairing loses nothing but typing.
            repairing = false
            nav.resetTo(Screen.HOME)
            JarvisRuntime.refreshPending()
            // Held long enough to scroll to and be noticed, then dropped. A
            // highlight that never cleared would also mean a second tap on the
            // SAME notification changed no key here, ran nothing, and scrolled
            // nowhere.
            delay(FOCUS_HOLD_MS)
            if (focusApproval.value == id) focusApproval.value = null
        }

        // Opens Home ready to talk. It does NOT call beginVoice(), and that is
        // the whole point of this block.
        //
        // It used to. The widget's Mic tile fires ACTION_START_VOICE, which
        // lands here, which called beginVoice() -> VoiceSession.begin(). But
        // `begin` opens the microphone and hands `Recorder.record` a
        // `stopWhen = { turn.releaseRequested }`, and `releaseRequested` is
        // set by exactly two callers - `release()` and `cancel()` - both wired
        // solely to [VoiceButton]'s press-and-hold gesture. A tap on a home
        // screen tile has no gesture to end, so nothing ever set it: the
        // recorder ran to `maxSamples` (the desktop's own cap, clamped to
        // 1-120s in Recorder) and `deliver()` then UPLOADED whatever the room
        // had said for up to two minutes. A phone tapped in a pocket recorded
        // and sent the pocket.
        //
        // That also falsified this app's loudest promise, in VoiceButton's own
        // KDoc: "while the button is down the microphone is open, and when it
        // is not, it is not. There is no state in which the app is listening
        // and the owner has to remember that it is." There was exactly such a
        // state, and it was reachable in one tap from the home screen.
        //
        // So the tile now does what it can honestly do: bring the app up on
        // Home, where the mic button is under the thumb. Opening the mic still
        // takes a deliberate hold, which is the only gesture that also carries
        // its own release.
        LaunchedEffect(startVoiceRequested.value) {
            if (!startVoiceRequested.value) return@LaunchedEffect
            startVoiceRequested.value = false
            nav.resetTo(Screen.HOME)
        }

        LaunchedEffect(openLiveRequested.value) {
            if (!openLiveRequested.value) return@LaunchedEffect
            openLiveRequested.value = false
            nav.go(Screen.LIVE)
        }

        // The Live tile, or "Live ended - Resume": the Live screen, and Live
        // starts - the owner's own tap - but only once the app is unlocked
        // (keyed on `locked`, like focusApproval): behind App lock nothing
        // starts. Held on a stale link like the Live button (liveStart).
        LaunchedEffect(startLiveRequested.value, locked) {
            val how = startLiveRequested.value ?: return@LaunchedEffect
            nav.go(Screen.LIVE)
            if (locked) return@LaunchedEffect
            startLiveRequested.value = null
            // In the runtime's own scope: clearing the request above restarts
            // this effect, which would cut a start off half-way.
            if (!JarvisRuntime.liveOnHere()) JarvisRuntime.liveStartSoon(resume = how == "resume")
        }

        // "Talk about this in Live": the shared text waits on the Live
        // screen as a "Shared text" chip, and Live starts (once unlocked).
        // Nothing is sent until the owner taps Send there.
        var liveSharedHeld by rememberSaveable { mutableStateOf<String?>(null) }
        LaunchedEffect(liveSharedText.value) {
            val text = liveSharedText.value ?: return@LaunchedEffect
            liveSharedHeld = Provenance.joinShared(liveSharedHeld, text)
            liveSharedText.value = null
            if (!JarvisRuntime.liveOnHere()) startLiveRequested.value = "start"
            nav.go(Screen.LIVE)
        }

        // "Solve it here" tapped on a Brain plate.
        val handoffOpen by JarvisRuntime.handoffOpen.collectAsState()
        LaunchedEffect(handoffOpen) {
            if (!handoffOpen) return@LaunchedEffect
            JarvisRuntime.handoffOpened()
            nav.go(Screen.HANDOFF)
        }

        // "Solve it here": the alert was tapped.
        LaunchedEffect(openHandoffRequested.value) {
            if (!openHandoffRequested.value) return@LaunchedEffect
            openHandoffRequested.value = false
            nav.go(Screen.HANDOFF)
        }

        // The widget's Note button: Home, with the quick-note field open.
        LaunchedEffect(quickNoteOpen.value) {
            if (quickNoteOpen.value) nav.resetTo(Screen.HOME)
        }

        // The briefing notification: Mind, where the briefing is (Back goes
        // Home). Behind the app lock the lock screen still comes first.
        LaunchedEffect(openBriefingRequested.value) {
            if (!openBriefingRequested.value) return@LaunchedEffect
            openBriefingRequested.value = false
            nav.resetTo(Screen.HOME)
            nav.go(Screen.BRAIN)
        }

        // "Look at this" from the assistant gesture: Home, where the chip
        // ("Looked at: Chrome screen · words only") is - and the look's two
        // minutes of follow-up questions start only once the app is unlocked
        // (keyed on `locked`, like focusApproval): behind App lock the chip is
        // not shown, and a look nobody unlocked for is dropped after a minute
        // by ScreenLook itself. Nothing is sent from here.
        LaunchedEffect(openLookRequested.value, locked) {
            if (!openLookRequested.value) return@LaunchedEffect
            nav.resetTo(Screen.HOME)
            if (locked) return@LaunchedEffect
            openLookRequested.value = false
            com.jarvis.client.net.ScreenLook.shown()
        }

        // The "Brief me now" and "What did I miss?" app-icon shortcuts
        // (AppShortcuts): Home, with the fixed sentence asked as a typed
        // question through `chat.send` - the composer's own path, so the
        // answer appears where every answer does. Both are read-only
        // sentences the PC answers without the AI model.
        //
        // Behind the app lock nothing is sent until it is unlocked (keyed on
        // `locked`, like focusApproval above): the answer is the owner's
        // private briefing. A phone that is not paired, or is re-pairing,
        // sends nothing - there is no desktop to ask yet, and the pairing
        // screen is what Home shows. The send runs on `scope`, not in this
        // effect: clearing `shortcutQuestion` changes this effect's key, and
        // that would cancel a send made in here halfway through its answer.
        LaunchedEffect(shortcutQuestion.value, locked) {
            val question = shortcutQuestion.value ?: return@LaunchedEffect
            if (locked) return@LaunchedEffect
            shortcutQuestion.value = null
            nav.resetTo(Screen.HOME)
            if (paired && !repairing) {
                scope.launch { chat.send(question, provenance = Provenance.TYPED) }
            }
        }

        // The restart notice ("Hey Jarvis" is off since the phone restarted,
        // data/WakeResume.kt): start listening from here - the app in front,
        // from the owner's tap, the only way Android allows the microphone.
        // Keyed on `locked`: with App lock on, nothing happens until the
        // owner has unlocked Jarvis. The link may still be coming up after a
        // restart, so it is given a few seconds, and the desktop's wake-word
        // switch is read fresh - the same checks as the Checks switch.
        // A tap left behind App lock and unlocked much later is dropped: the
        // microphone opens only close to the owner's own tap.
        LaunchedEffect(resumeListeningRequestedAt.value, locked) {
            val at = resumeListeningRequestedAt.value ?: return@LaunchedEffect
            if (locked) return@LaunchedEffect
            resumeListeningRequestedAt.value = null
            if (android.os.SystemClock.elapsedRealtime() - at > RESUME_REQUEST_FRESH_MS) return@LaunchedEffect
            if (!JarvisRuntime.isPaired()) return@LaunchedEffect
            // On the activity's own scope, not this effect's: clearing the
            // request above changes this effect's key, which would cancel it
            // half way through the wait below.
            lifecycleScope.launch {
                kotlinx.coroutines.withTimeoutOrNull(RESUME_LINK_WAIT_MS) {
                    JarvisRuntime.link.first { it == LinkState.CONNECTED }
                }
                JarvisRuntime.voice.refreshStatus()
                val why = startPhoneListening()
                if (why == null) {
                    JarvisRuntime.setNotice(com.jarvis.client.data.WakeResume.BACK_ON)
                } else {
                    // Settings, Voice, where the switch is (moved there from
                    // Checks, 2026-09-30), with the reason under it.
                    resumeListeningNotice.value = why
                    pendingSection = "voice"
                    pendingSectionScreen = Screen.SETTINGS.name
                    nav.resetTo(Screen.HOME)
                    nav.go(Screen.SETTINGS)
                }
            }
        }

        JarvisTheme(
            chrome = chrome,
            idleColor = idleColour,
            compact = look.compact,
            sharp = look.sharp,
            textScale = look.textScale,
            // Mapped by name: the store keeps its own enum so a stored choice
            // survives a rename in the theme code, and the two are kept in
            // step by having the same three names.
            edges = PlateEdges.valueOf(look.edges.name),
            transitions = look.transitions,
        ) {
            val root = Modifier
                .fillMaxSize()
                // The theme's faded colour, not `chrome` from outside the
                // theme: `chrome` is where a theme change is going, and it
                // jumps there at once, so the page behind every screen would
                // cut while everything drawn on it faded.
                .background(LocalChrome.current.surface0)
                .windowInsetsPadding(WindowInsets.systemBars)
                // The keyboard inset, on the root so every screen gets it
                // (UI audit 2026-10-05, finding A2). `enableEdgeToEdge` means
                // this app owns the IME inset, and the root only asked for the
                // system bars - so on 11 of 14 screens the keyboard covered
                // the field being typed into: every Brain plate, the support
                // form, pairing's address and token. Three screens had added
                // `imePadding` for themselves (Home, Live, Handoff), which is
                // how the gap was found; one inset on the root covers those
                // too, and a screen never repeats another screen's inset.
                .imePadding()
            // Calm motion for the face: the owner's Motion choice, or the
            // phone's own "remove animations", read from the same flag the
            // theme's Motion already reads. Only ever slows the face.
            val calmMotion = look.motion.calmFace(LocalMotion.current.reduced)

            // The app lock outranks everything, pairing included: nothing
            // behind it is composed. Approving from the notification or the
            // widget was never possible, and Deny there needs no unlock -
            // refusing is never gated.
            if (locked) {
                // Back leaves Jarvis rather than walking a back stack nobody
                // can see. Composed after NavBackHandler, so it wins.
                BackHandler(onBack = { moveTaskToBack(true) })
                LockedScreen(
                    message = lockMessage.value,
                    busy = ownerCheckBusy.value,
                    onUnlock = ::unlockApp,
                    modifier = root,
                )
                // Asked once as the lock screen appears. A dismissed prompt
                // is an answer: it is not asked again until Unlock is tapped.
                LaunchedEffect(Unit) { unlockApp() }
                return@JarvisTheme
            }

            // Pairing outranks the stack: there is nothing to show until there
            // is somewhere to talk to. A few screens are the exception. Checks,
            // because "why can I not connect" has to be answerable from here.
            // Help, because its first question is "Do I need Tailscale?", and
            // that is asked before pairing, not after.
            //
            // `repairing` shows this same screen to a phone that IS paired, so
            // the owner can change the desktop or the token.
            // Security too: it is opened from Checks, and its settings are
            // this phone's own, so there is no reason to pair first.
            // Settings joins them for the same reason (ease-of-use audit row
            // 16, 2026-09-27): its own Security link must stay reachable
            // mid-pair, same as Checks's. Its voice and Appearance links stay
            // null/absent until paired, exactly as they already are on Checks.
            if ((!paired || repairing) &&
                nav.current != Screen.CHECKS && nav.current != Screen.FAQ &&
                nav.current != Screen.SECURITY && nav.current != Screen.SETTINGS
            ) {
                val replacing = paired
                // Leaves re-pairing and keeps the desktop in use. A "refused
                // that token" notice left over from an attempt made here is
                // dropped with it: the old token was put back, and on Home the
                // sentence would read as being about that one. If the old token
                // really is refused, the stream still says so in the status.
                //
                // Ignored while an attempt is in flight. During it the NEW
                // address and token are the saved ones, so leaving then would
                // put Home's Approve and Deny on an unchecked desktop - and if
                // the attempt then connected, "Keep current desktop" would have
                // ended by keeping the new one. The button is greyed out for
                // the same stretch; system back is swallowed rather than
                // passed on. The attempt is bounded by the short call timeout.
                val leaveRepair: () -> Unit = {
                    if (!busy) {
                        repairing = false
                        if (notice == badTokenNotice || com.jarvis.client.net.KeyRefusal.isWords(notice)) {
                            JarvisRuntime.clearNotice()
                        }
                    }
                }
                if (replacing) {
                    // System back does the same as the on-screen button.
                    // Composed after NavBackHandler, so it takes the press first.
                    BackHandler(onBack = leaveRepair)
                }
                // Saves an address and a key, shakes hands with them, and puts
                // the old ones back if that fails - for a typed token and for
                // the key the PC hands over after QR-code pairing alike
                // (docs/PAIRING-DESIGN.md section 7.2: never lock the owner out).
                val pairWith: (String, String) -> Unit = { host, token ->
                    busy = true
                    scope.launch {
                        // Only filled in when re-pairing. Held in this
                        // coroutine and nowhere else, never logged, and
                        // dropped when it ends. `oldToken` stays empty when
                        // no new token was typed - then the stored one is
                        // never touched, so there is nothing to put back.
                        var oldHost = ""
                        var oldToken = ""
                        // `wrote`: the new address may already be saved, so
                        // there is something to undo. `connected`: the new
                        // pair answered and is being kept.
                        var wrote = false
                        var connected = false
                        try {
                            // Off the main thread. `setToken` generates a
                            // hardware-backed AES key on first pair, which is
                            // a TEE/StrongBox round trip — several hundred
                            // milliseconds to a couple of seconds, blocking
                            // the UI so hard that the button could not even
                            // repaint into its own busy state, and an ANR
                            // candidate on a slow device.
                            withContext(Dispatchers.IO) {
                                if (replacing) {
                                    oldHost = JarvisRuntime.settings.host.value
                                    if (token.isNotBlank()) oldToken = JarvisRuntime.tokens.token()
                                }
                                wrote = true
                                JarvisRuntime.settings.setHost(host)
                                if (token.isNotBlank()) JarvisRuntime.tokens.setToken(token)
                            }
                            val result = JarvisRuntime.handshake()
                            if (result is ApiResult.Ok) {
                                connected = true
                                busy = false
                                paired = true
                                // The first pairing on this phone queues the
                                // one-time "Background restart" offer on Home
                                // (walk-through C9). Offered, never asked for
                                // by a dialog, and never again after.
                                if (!replacing) JarvisRuntime.settings.queueKeepAliveOffer()
                                repairing = false
                                pairingHost = JarvisRuntime.settings.host.value
                                // The stream lives in the service, not here:
                                // a backgrounded activity's connection is
                                // suspended within about a minute, which is
                                // exactly how approvals silently stop
                                // arriving.
                                EventService.start(this@MainActivity)
                                if (replacing) {
                                    // The running stream is still talking
                                    // to the old desktop, or retrying the old
                                    // token. Replaced the same way Home's
                                    // Retry does it, so it picks up the new
                                    // address and token now rather than at
                                    // its next backoff.
                                    JarvisRuntime.startStream(force = true)
                                    scope.launch { JarvisRuntime.refreshAll() }
                                }
                                // Picks up whatever face the owner's other
                                // device already chose, the moment there is
                                // somewhere to ask. A no-op, silently, on a
                                // backend without the capability.
                                JarvisRuntime.refreshAppearance()
                            }
                        } finally {
                            // A re-pair that did not connect changes
                            // nothing: the desktop and token that were in
                            // use go back. A typo must never be what
                            // unpairs a phone that was working. The
                            // handshake's own notice stays up to say why.
                            //
                            // In `finally`, and NonCancellable, because this
                            // coroutine dies with the composition: a
                            // rotation mid-handshake used to cancel it
                            // before the put-back ran, leaving the new,
                            // unchecked pair saved and in use - the
                            // opposite of what the re-pair screen promises.
                            //
                            // `oldToken` is empty when it could not be read
                            // (the Keystore is briefly unavailable) - then
                            // there is nothing to restore, and clearing the
                            // new one would unpair the phone outright, so
                            // the new one is left.
                            if (replacing && wrote && !connected) {
                                withContext(NonCancellable + Dispatchers.IO) {
                                    JarvisRuntime.settings.setHost(oldHost)
                                    if (oldToken.isNotEmpty()) JarvisRuntime.tokens.setToken(oldToken)
                                }
                            }
                            // Only after the put-back: re-enabling Connect
                            // first would let a second tap read the failed
                            // address as the "old" one to restore.
                            if (!connected) busy = false
                        }
                    }
                }
                PairingScreen(
                    onKeyShownChange = { pairingKeyShown = it },
                    initialHost = pairingHost,
                    hasToken = JarvisRuntime.tokens.hasToken(),
                    busy = busy,
                    // Brought back by a refusal the stream reported, there may be
                    // no notice yet - so say why the screen appeared. The same
                    // for a saved address off the owner's own networks
                    // (OwnNetwork): it is never used, so the app opens here,
                    // and this sentence is the reason.
                    notice = notice ?: JarvisRuntime.settings.baseProblem()
                        ?: if (tokenRefused) refusedWords else null,
                    // QR-code pairing (docs/PAIRING-DESIGN.md section 7.2): offered
                    // before anything is paired, and when the PC says it has
                    // it - or has not said (a refused key cannot even read
                    // the version, and that is exactly when it is needed).
                    offerCodePairing = !replacing || JarvisRuntime.version.value == null ||
                        JarvisRuntime.can("pairing"),
                    onDeviceKey = pairWith,
                    onPair = pairWith,
                    onOpenReadiness = { nav.go(Screen.CHECKS) },
                    modifier = root,
                    onHostChange = { pairingHost = it },
                    onOpenHelp = { nav.go(Screen.FAQ) },
                    onCancel = if (replacing) leaveRepair else null,
                )
                return@JarvisTheme
            }

            // A short fade between screens (screens-13), or an instant cut when
            // the owner turned transitions off or the phone asks for less
            // motion. Each screen draws from `screen`, not `nav.current`:
            // during the fade the old and the new screen are both on the glass.
            NavScreens(nav, transitions = look.transitions) { screen ->
                when (screen) {
                    Screen.CHECKS -> {
                        val host by JarvisRuntime.settings.host.collectAsState()
                        // Before pairing, or while re-pairing, the address to judge
                        // is the one being typed, not the saved one: that is the
                        // question the owner came here to ask.
                        val judgedHost = if (!paired || repairing) pairingHost else host
                        // `pending` is a key because the Notifications item reports
                        // how many approvals are currently going unannounced, and
                        // that number moves with the pending list. Without it the
                        // report would be cached from whenever the permission last
                        // changed and quietly go stale.
                        val items = remember(tick, judgedHost, pending) {
                            PlatformReadiness.report(
                                this@MainActivity,
                                judgedHost,
                            )
                        }
                        val wakeWord by voice.wakeWord.collectAsState()
                        val voiceAnswered by voice.answered.collectAsState()
                        val phoneListening by WakeWordService.state.collectAsState()
                        // The desktop's switch went off (from here, the
                        // desktop, or a restart): this phone stops too. The
                        // listener also checks for itself every few minutes.
                        LaunchedEffect(wakeWord) {
                            if (wakeWord == WakeWord.OFF && WakeWordService.state.value.on) {
                                WakeWordService.stop(this@MainActivity)
                            }
                        }
                        // Asked on arrival, because this screen is where someone
                        // goes to find out what is listening, and a stale answer is
                        // the wrong thing to be reassured by.
                        LaunchedEffect(Unit) { voice.refreshStatus() }

                        ReadinessScreen(
                            items = items,
                            onRequestNotifications = {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                                    val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                                        .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                                    if (shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)) {
                                        notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                                    } else {
                                        runCatching { startActivity(intent) }.onFailure {
                                            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                                        }
                                    }
                                }
                            },
                            onRequestBatteryExemption = ::requestBatteryExemption,
                            onStartService = { EventService.start(this@MainActivity) },
                            onBack = { if (!nav.back()) nav.resetTo(Screen.HOME) },
                            // remember(tick), like `items` above: both of these
                            // are RoleManager binder calls, and unkeyed they ran
                            // on every recomposition of this branch - which
                            // recomposes on link, activity and pending changes.
                            // `tick` is what already drives the permission
                            // re-read, so keying on it keeps the answer as fresh
                            // as every other check on this screen.
                            onRequestAssistantRole = remember(tick) {
                                if (
                                    PlatformReadiness.assistantRoleAvailable(this@MainActivity) &&
                                    !PlatformReadiness.assistantRoleHeld(this@MainActivity)
                                ) {
                                    { requestAssistantRole() }
                                } else {
                                    null
                                }
                            },
                            wakeWord = wakeWord,
                            wakeWordPending = voiceStatus.listening.wakeWordPending,
                            phoneListening = phoneListening,
                            // The switches (turn "hey Jarvis" on or off, Listen on
                            // this phone, interrupting, "One moment", the "I heard
                            // you" sound) moved to Settings, Voice, with the other
                            // voice settings (settings audit, 2026-09-30); Checks
                            // keeps the status and this button.
                            onOpenVoiceSettings = {
                                pendingSection = "voice"
                                pendingSectionScreen = Screen.SETTINGS.name
                                nav.go(Screen.SETTINGS)
                            },
                            modifier = root,
                            // The saved host, not the typed one: this card is about
                            // the link that is actually running.
                            connection = ConnectionInfo(
                                host = host,
                                paired = paired,
                                link = link,
                                stale = stale,
                                detail = linkDetail,
                                vpnLine = vpnLine,
                            ),
                            // The same call as Home's Retry, `force` and all - see
                            // the comment on onReconnect in HomeActions below.
                            onReconnect = {
                                EventService.start(this@MainActivity)
                                JarvisRuntime.startStream(force = true)
                                scope.launch { JarvisRuntime.refreshAll() }
                            },
                            onChangeDesktop = if (paired) {
                                {
                                    // Filled in with the saved address, unless a
                                    // re-pair is already under way - then the
                                    // address being typed is kept.
                                    if (!repairing) pairingHost = host
                                    repairing = true
                                    nav.resetTo(Screen.HOME)
                                }
                            } else {
                                null
                            },
                            // "Train my voice". Only once paired: the clips go
                            // to the desktop, so there has to be one.
                            voiceStatus = voiceStatus,
                            voiceAnswered = voiceAnswered,
                            onTrainVoice = if (paired) {
                                { nav.go(Screen.VOICE) }
                            } else {
                                null
                            },
                            // The stricter check's settings and test, and custom
                            // voices: both are the PC's, so only once paired.
                            voiceStrict = voiceStrict,
                            onVoiceCheck = if (paired) {
                                { nav.go(Screen.VOICE_CHECK) }
                            } else {
                                null
                            },
                            onVoices = if (paired) {
                                { nav.go(Screen.VOICES) }
                            } else {
                                null
                            },
                            // Lock and fingerprint (SecurityScreen). On this
                            // phone only; nothing here reaches the desktop.
                            securitySummary = SecurityRules.summary(security),
                            onOpenSecurity = { nav.go(Screen.SECURITY) },
                            // "Check for new versions", and the one place a
                            // failed check is mentioned.
                            update = updateState,
                            updateChecks = updateChecks,
                            onUpdateChecks = { on ->
                                JarvisRuntime.settings.setUpdateChecks(on)
                                if (!on) JarvisRuntime.updates.cleared()
                            },
                            onOpenRelease = ::openReleasePage,
                            // The phone's own Settings screen (ease-of-use
                            // audit row 16, 2026-09-27).
                            onOpenSettings = { nav.go(Screen.SETTINGS) },
                            // "Open connection" / "open updates" by voice or
                            // chat (OpenPlace).
                            initialSection = sectionFor(Screen.CHECKS),
                            onSectionConsumed = sectionConsumed,
                        )
                    }

                    Screen.VOICE -> {
                        val voiceAnswered by voice.answered.collectAsState()
                        // Asked on arrival: the card says whether Jarvis knows
                        // the owner's voice, and a stale answer would mislead.
                        LaunchedEffect(Unit) { voice.refreshStatus() }
                        val voiceSent by JarvisRuntime.voiceSent.collectAsState()
                        VoiceTrainingScreen(
                            status = voiceStatus,
                            strict = voiceStrict,
                            answered = voiceAnswered,
                            // Keyed on `link` and `stale`, which are collected
                            // above: actionBlocker() reads the runtime's flows
                            // directly, and that alone subscribes to nothing.
                            linkBlocker = remember(link, stale) { JarvisRuntime.actionBlocker() },
                            sentPlan = voiceSent,
                            record = { stop, onLevel -> voice.recordTrainingClip(stop, onLevel) },
                            sendRound = { plan, index, clips -> JarvisRuntime.sendVoiceRound(plan, index, clips) },
                            cancelRounds = { JarvisRuntime.cancelVoiceRounds() },
                            checkOthers = { clips -> JarvisRuntime.checkVoiceWithSomeoneElse(clips) },
                            proposeThreshold = { value -> JarvisRuntime.proposeVoiceThreshold(value) },
                            onRefresh = { voice.refreshStatus() },
                            onAskMicrophone = {
                                // Never starts a recording on the grant - the
                                // owner taps Record again, the same rule as
                                // the talk button (see micGrantedCallback).
                                micGrantedCallback = null
                                micPermission.launch(Manifest.permission.RECORD_AUDIO)
                            },
                            onBack = { nav.back() },
                            modifier = root,
                        )
                    }

                    Screen.VOICE_CHECK -> {
                        val voiceAnswered by voice.answered.collectAsState()
                        // Asked on arrival: the settings shown must be the
                        // PC's, not an old read.
                        LaunchedEffect(Unit) { voice.refreshStatus() }
                        VoiceCheckScreen(
                            status = voiceStatus,
                            strict = voiceStrict,
                            answered = voiceAnswered,
                            linkBlocker = remember(link, stale) { JarvisRuntime.actionBlocker() },
                            setSetting = { setting, value -> JarvisRuntime.setVoiceSetting(setting, value) },
                            record = { stop, onLevel -> voice.recordTrainingClip(stop, onLevel) },
                            measure = { clips, seconds -> JarvisRuntime.measureVoice(clips, seconds) },
                            onRefresh = { voice.refreshStatus() },
                            onAskMicrophone = {
                                micGrantedCallback = null
                                micPermission.launch(Manifest.permission.RECORD_AUDIO)
                            },
                            onBack = { nav.back() },
                            modifier = root,
                        )
                    }

                    Screen.VOICES -> {
                        val voicesRead by JarvisRuntime.customVoices.collectAsState()
                        val voicesNote by JarvisRuntime.customVoiceNote.collectAsState()
                        LaunchedEffect(Unit) { JarvisRuntime.refreshCustomVoices() }
                        VoicesScreen(
                            read = voicesRead,
                            note = voicesNote,
                            linkBlocker = remember(link, stale) { JarvisRuntime.actionBlocker() },
                            picked = pickedVoiceFile.value,
                            record = { stop, onLevel -> voice.recordTrainingClip(stop, onLevel) },
                            add = { name, clip, words -> JarvisRuntime.addCustomVoice(name, clip, words) },
                            switchTo = { id -> JarvisRuntime.switchCustomVoice(id) },
                            delete = { id -> JarvisRuntime.deleteCustomVoice(id) },
                            setBetter = { on -> JarvisRuntime.setBetterVoice(on) },
                            setSpeed = { id -> JarvisRuntime.setVoiceSpeed(id) },
                            setSpeaker = { id -> JarvisRuntime.setVoiceSpeaker(id) },
                            setFace = { on -> JarvisRuntime.setVoiceFace(on) },
                            answerFaceOffer = { f, use -> JarvisRuntime.answerFaceVoiceOffer(f, use) },
                            setAnimal = { json -> JarvisRuntime.setVoiceAnimal(json) },
                            tryAnimal = { face, name, playing ->
                                JarvisRuntime.voice.tryAnimalVoice(face, name, playing)
                            },
                            hearVoice = { id, label, playing ->
                                JarvisRuntime.hearVoice(id, label, playing)
                            },
                            // Any audio type: the file is checked for being a WAV
                            // once read, and says so plainly when it is not.
                            onPickFile = { pickVoiceFile.launch(arrayOf("audio/*")) },
                            onClearPicked = { pickedVoiceFile.value = null },
                            onRefresh = { JarvisRuntime.refreshCustomVoices() },
                            onDismissNote = { JarvisRuntime.clearCustomVoiceNote() },
                            onAskMicrophone = {
                                micGrantedCallback = null
                                micPermission.launch(Manifest.permission.RECORD_AUDIO)
                            },
                            onBack = {
                                JarvisRuntime.clearCustomVoiceNote()
                                nav.back()
                            },
                            modifier = root,
                        )
                    }

                    Screen.INBOX -> {
                        LaunchedEffect(Unit) { JarvisRuntime.refreshInbox() }
                        InboxScreen(
                            link = link,
                            stale = stale,
                            attention = attention,
                            digest = digest,
                            undo = undo,
                            jobs = jobs,
                            pastApprovals = pastApprovals,
                            // "Past approvals" (ui/screens/ApprovalsScreen.kt):
                            // the rows moved to their own screen, reachable from
                            // here - the approvals audit of 2026-09-30 found
                            // this list was "only reachable via Inbox", and its
                            // own screen is what lets it hide under "Hide memory
                            // lists and chat history" like the other history
                            // surfaces.
                            onOpenApprovals = { nav.go(Screen.APPROVALS) },
                            onOpenApproval = { id ->
                                // Carries the id now. It used to be dropped, so a
                                // digest row with three approvals waiting took you
                                // to a list and left you to find the right one.
                                nav.resetTo(Screen.HOME)
                                focusApproval.value = id
                                scope.launch { JarvisRuntime.refreshPending() }
                            },
                            onRevert = { scope.launch { JarvisRuntime.revert(it) } },
                            onCancelJob = { scope.launch { JarvisRuntime.cancelJob(it) } },
                            onCancelHold = { scope.launch { JarvisRuntime.cancelHold(it) } },
                            onMarkSeen = { scope.launch { JarvisRuntime.markDigestSeen() } },
                            onSetMuted = { m -> scope.launch { JarvisRuntime.setMuted(m) } },
                            onBack = { nav.back() },
                            modifier = root,
                            read = inboxRead,
                            // A Revert, Cancel, mute or Mark read that failed used
                            // to say so only on Home, where nobody was looking.
                            notice = notice,
                            onDismissNotice = { JarvisRuntime.clearNotice() },
                            onRetry = { scope.launch { JarvisRuntime.refreshInbox() } },
                        )
                    }

                    Screen.APPROVALS -> {
                        // "Past approvals" - read-only (the owner's decision of
                        // 2026-09-27). The screen reads the list itself, when it
                        // opens, when Show confirms and on Refresh, so it fetches
                        // the one list it draws rather than the Inbox's four.
                        // Nothing here decides a card: there is no approve, deny,
                        // cancel, clear or re-open anywhere on it.
                        ApprovalsScreen(
                            link = link,
                            stale = stale,
                            items = pastApprovals,
                            read = inboxRead.activity,
                            fetchedAtMs = inboxRead.fetchedAtMs,
                            refreshing = inboxRead.refreshing,
                            onRead = { scope.launch { JarvisRuntime.refreshPastApprovals() } },
                            notice = notice,
                            onDismissNotice = { JarvisRuntime.clearNotice() },
                            onBack = { nav.back() },
                            modifier = root,
                            privateHidden = privateHidden,
                            onShowPrivate = ::showPrivateLists,
                            showPrivateBusy = ownerCheckBusy.value,
                        )
                    }

                    Screen.BRAIN -> {
                        LaunchedEffect(Unit) { JarvisRuntime.refreshBrain() }
                        BrainScreen(
                            link = link,
                            stale = stale,
                            activity = activity,
                            power = power,
                            status = status,
                            version = version,
                            attention = attention,
                            jobs = jobs,
                            brain = brain,
                            onRefresh = { scope.launch { JarvisRuntime.refreshBrain() } },
                            onBack = { nav.back() },
                            memoryDecideBusyId = memoryDecideBusyId,
                            onDecideMemory = { id, accept ->
                                if (memoryDecideBusyId == null) {
                                    memoryDecideBusyId = id
                                    scope.launch {
                                        JarvisRuntime.decideMemory(id, accept)
                                        memoryDecideBusyId = null
                                    }
                                }
                            },
                            onKeepBothMemory = { id ->
                                if (memoryDecideBusyId == null) {
                                    memoryDecideBusyId = id
                                    scope.launch {
                                        JarvisRuntime.keepBothMemory(id)
                                        memoryDecideBusyId = null
                                    }
                                }
                            },
                            sleepOffer = cachedSleepOffer,
                            sleepOfferBusy = sleepOfferBusy,
                            onSleepTimeAction = { enabled, remind ->
                                if (!sleepOfferBusy) {
                                    val answered = cachedSleepOffer
                                    sleepOfferBusy = true
                                    // Suppressed BEFORE the write, not after: a
                                    // successful setSleepTime() calls
                                    // refreshBrain() internally before it returns,
                                    // and that recomposition has to see the flag
                                    // already set or the LaunchedEffect above
                                    // re-adopts the very offer this click is
                                    // answering, from whatever brain.memory still
                                    // holds. Rolled back below on failure, so a
                                    // network hiccup never costs the owner their
                                    // only way to act on this until tomorrow. It
                                    // is `answering` and not `dismissed` that is
                                    // set here, so a rotation that cancels this
                                    // coroutine cannot leave the offer suppressed
                                    // by a rollback that will never run.
                                    cachedSleepOffer = null
                                    sleepOfferAnswering = true
                                    scope.launch {
                                        val result = JarvisRuntime.setSleepTime(enabled, remind)
                                        sleepOfferBusy = false
                                        sleepOfferAnswering = false
                                        if (result is ApiResult.Ok) {
                                            // Durable: the answer reached the
                                            // desktop, so now it is safe to let it
                                            // survive a rotation. Dated, not just
                                            // true - a fresh offer tomorrow is a
                                            // different question, not the one just
                                            // answered.
                                            sleepOfferDismissedOn = todayLocal()
                                        } else {
                                            cachedSleepOffer = answered
                                        }
                                    }
                                }
                            },
                            onDismissSleepOffer = {
                                cachedSleepOffer = null
                                sleepOfferDismissedOn = todayLocal()
                                // A real answer since 2026-09-25: the PC keeps
                                // the offer quiet for a day, then a week, then
                                // a month (jarvis_backoff.py). Dismissed here
                                // whether or not that reaches the PC.
                                scope.launch { JarvisRuntime.sleepNotNow() }
                            },
                            notice = notice,
                            onDismissNotice = { JarvisRuntime.clearNotice() },
                            models = models,
                            modelsCache = modelsCache,
                            modelBusy = modelBusy,
                            onSwitchModel = { ref ->
                                if (!modelBusy) {
                                    modelBusy = true
                                    scope.launch {
                                        JarvisRuntime.switchModel(ref)
                                        modelBusy = false
                                    }
                                }
                            },
                            onRollbackModel = {
                                if (!modelBusy) {
                                    modelBusy = true
                                    scope.launch {
                                        JarvisRuntime.rollbackModel()
                                        modelBusy = false
                                    }
                                }
                            },
                            onInstallModel = { ref ->
                                if (!modelBusy) {
                                    modelBusy = true
                                    scope.launch {
                                        JarvisRuntime.installModel(ref)
                                        modelBusy = false
                                    }
                                }
                            },
                            memoryAsOf = memoryAsOfResult,
                            memoryAsOfBusy = memoryAsOfBusy,
                            onQueryMemoryAsOf = { epochSeconds ->
                                if (!memoryAsOfBusy) {
                                    memoryAsOfBusy = true
                                    scope.launch {
                                        val result = JarvisRuntime.memoryAsOf(epochSeconds)
                                        // Cleared on a failure too: the plate does not
                                        // print the date, so an earlier date's answer
                                        // left on screen would read as this one's.
                                        memoryAsOfResult = if (result is ApiResult.Ok) result.value else null
                                        memoryAsOfBusy = false
                                    }
                                }
                            },
                            modifier = root,
                            // "Open the card →" after Use or Install: the same path
                            // as Inbox's onOpenApproval. It only opens Home on the
                            // card - approving it is still a deliberate tap there.
                            onOpenApprovals = { id ->
                                nav.resetTo(Screen.HOME)
                                if (id != null) focusApproval.value = id
                                scope.launch { JarvisRuntime.refreshPending() }
                            },
                            // backend/power-mode.patch: Active / Quiet / Standby.
                            onSetPower = { mode -> scope.launch { JarvisRuntime.setPower(mode) } },
                            // backend/second-card.patch: one switch at a time.
                            // ON raises a card and turns nothing on; the plate
                            // shows what the PC reports afterwards.
                            secondCard = secondCard,
                            secondCardBusy = secondCardBusy,
                            secondCardNotice = secondCardNotice,
                            onSetSecondCard = { feature, enabled ->
                                if (secondCardBusy == null) {
                                    secondCardBusy = feature
                                    secondCardNotice = null
                                    scope.launch {
                                        try {
                                            secondCardNotice = JarvisRuntime.setSecondCard(feature, enabled)
                                        } finally {
                                            secondCardBusy = null
                                        }
                                    }
                                }
                            },
                            // A third graphics card (2026-09-28): moving a
                            // switch onto it, or off. Marked busy the same
                            // way as onSetSecondCard, under SecondCard.THIRD
                            // rather than a feature id - there is no single
                            // switch this request is about.
                            onSetThirdCard = { assign ->
                                if (secondCardBusy == null) {
                                    secondCardBusy = SecondCard.THIRD
                                    secondCardNotice = null
                                    scope.launch {
                                        try {
                                            secondCardNotice = JarvisRuntime.setThirdCard(assign)
                                        } finally {
                                            secondCardBusy = null
                                        }
                                    }
                                }
                            },
                            // "Everyday chat runs on" (2026-10-05): pinning
                            // everyday chat to one card, or going back to
                            // leaving it to Ollama. Marked busy under
                            // SecondCard.CHAT_CARD, the same way onSetThirdCard
                            // uses SecondCard.THIRD - there is no single switch
                            // this request is about.
                            onSetChatCard = { action, card ->
                                if (secondCardBusy == null) {
                                    secondCardBusy = SecondCard.CHAT_CARD
                                    secondCardNotice = null
                                    scope.launch {
                                        try {
                                            secondCardNotice = JarvisRuntime.setChatCard(action, card)
                                        } finally {
                                            secondCardBusy = null
                                        }
                                    }
                                }
                            },
                            // "When to suggest the bigger model" (2026-09-27):
                            // no card either way, so this only ever re-reads
                            // the plate afterwards - never touches approvals.
                            onSetSecondCardSuggest = { signal, enabled ->
                                if (secondCardBusy == null) {
                                    secondCardBusy = signal
                                    secondCardNotice = null
                                    scope.launch {
                                        try {
                                            secondCardNotice =
                                                JarvisRuntime.setSecondCardSuggest(signal, enabled)
                                        } finally {
                                            secondCardBusy = null
                                        }
                                    }
                                }
                            },
                            onRecheckSecondCard = {
                                if (secondCardBusy == null) {
                                    secondCardBusy = ""
                                    scope.launch {
                                        try {
                                            JarvisRuntime.refreshSecondCard()
                                        } finally {
                                            secondCardBusy = null
                                        }
                                    }
                                }
                            },
                            // Security's "Hide memory lists and chat history": hidden until
                            // Show is confirmed, and hidden again whenever the
                            // app would lock again.
                            privateHidden = privateHidden,
                            onShowPrivate = ::showPrivateLists,
                            showPrivateBusy = ownerCheckBusy.value,
                            // Chat history on the PC (docs/JARVIS-API.md
                            // section 18): its own screen, opened from here.
                            onOpenHistory = { nav.go(Screen.HISTORY) },
                            // The phone's own Settings screen (ease-of-use
                            // audit row 16, 2026-09-27), where the old
                            // "Settings" group moved to.
                            onOpenSettings = { nav.go(Screen.SETTINGS) },
                            // "Everything Jarvis can do" (docs/FEATURES-LIST-
                            // DESIGN.md, the owner's request of 2026-10-08):
                            // its own read-only screen, opened from the row
                            // beside Tutorials.
                            onOpenFeatures = { nav.go(Screen.FEATURES) },
                            // "Open the morning briefing", "hardware", ... by
                            // voice or chat (OpenPlace).
                            initialSection = sectionFor(Screen.BRAIN),
                            onSectionConsumed = sectionConsumed,
                            // "3 hidden - Show" at the bottom of Brain: Settings, at the
                            // "Show or hide menus" list.
                            onOpenMenuList = {
                                pendingSection = "menu-visibility"
                                pendingSectionScreen = Screen.SETTINGS.name
                                nav.go(Screen.SETTINGS)
                            },
                        )
                    }

                    Screen.HISTORY -> HistoryScreen(
                        // Only turning the switch ON waits for this - rule 4.
                        canAct = link == LinkState.CONNECTED && !stale,
                        onBack = { nav.back() },
                        // "Hide memory lists and chat history" hides the conversations too.
                        privateHidden = privateHidden,
                        onShowPrivate = ::showPrivateLists,
                        showPrivateBusy = ownerCheckBusy.value,
                        // "Continue this chat" (the owner's decision,
                        // 2026-09-28): Home carries it on, and says so.
                        onContinue = { id ->
                            JarvisRuntime.continueChat(id).also { why ->
                                if (why == null) {
                                    nav.resetTo(Screen.HOME)
                                }
                            }
                        },
                        // "Forget a time frame…" at the top of History: the
                        // Brain's plate, as "forget what you learned last
                        // week" opens it (OpenPlace).
                        onOpenForgetRange = {
                            JarvisRuntime.menus.showForVisit("brain.history.forget-range")
                            pendingSection = "forget-range"
                            pendingSectionScreen = Screen.BRAIN.name
                            nav.go(Screen.BRAIN)
                        },
                        // "Tap the chat to file it under Home."
                        fileUnder = filingTag?.let { com.jarvis.client.net.ChatTags.FileUnder(it, filingQuery) },
                        onFileUnderDone = {
                            filingTag = null
                            filingQuery = ""
                        },
                        modifier = root,
                    )

                    Screen.LIVE -> com.jarvis.client.ui.screens.LiveScreen(
                        onBack = { nav.back() },
                        // "Show the card": the cards are on Home. Back comes
                        // back to Live (the review's C7: it reset the stack).
                        onOpenCards = { nav.go(Screen.HOME) },
                        // "Jarvis Live didn't start: it needs your voice
                        // trained first - Settings, then Train my voice."
                        onTrainVoice = { nav.go(Screen.VOICE) },
                        // "Talk about this in Live": held here until Send.
                        shared = liveSharedHeld,
                        onDropShared = { liveSharedHeld = null },
                        modifier = root,
                    )

                    Screen.HANDOFF -> com.jarvis.client.ui.screens.HandoffScreen(
                        onBack = { nav.back() },
                        modifier = root,
                    )

                    Screen.FAQ -> FaqScreen(
                        onBack = { nav.back() },
                        modifier = root,
                        // "Open about" by voice or chat (OpenPlace).
                        initialSection = sectionFor(Screen.FAQ),
                        onSectionConsumed = sectionConsumed,
                    )

                    // "Everything Jarvis can do" (docs/FEATURES-LIST-DESIGN.md,
                    // the owner's request of 2026-10-08): every feature, in
                    // plain words, read from this app's own copy of
                    // features/features.json. Read-only, no card, no request to
                    // the PC.
                    Screen.FEATURES -> FeaturesScreen(
                        onBack = { nav.back() },
                        modifier = root,
                    )

                    Screen.SECURITY -> {
                        // Asked again on every visit and every change, so the
                        // "no screen lock" warning follows the phone's own
                        // settings. A cheap system call.
                        val availability = remember(tick, security) {
                            BiometricGate.availability(this@MainActivity, security.method)
                        }
                        SecurityScreen(
                            security = security,
                            availability = availability,
                            onChange = ::changeSecurity,
                            onOpenLockSettings = ::openLockSettings,
                            onBack = {
                                securityNotice.value = null
                                nav.back()
                            },
                            busy = ownerCheckBusy.value,
                            notice = securityNotice.value,
                            onDismissNotice = { securityNotice.value = null },
                            modifier = root,
                            initialSection = sectionFor(Screen.SECURITY),
                            onSectionConsumed = sectionConsumed,
                        )
                    }

                    Screen.SETTINGS -> SettingsScreen(
                        link = link,
                        stale = stale,
                        onBack = { nav.back() },
                        modifier = root,
                        initialSection = sectionFor(Screen.SETTINGS),
                        // Bug audit 2026-09-27, finding #4: cleared once the
                        // screen has scrolled to it (or found no row for
                        // it), so a later manual visit to Settings does not
                        // scroll anywhere on its own.
                        onSectionConsumed = sectionConsumed,
                        // Picture mode's button to the Looking at your screen
                        // switch, which is on the Security screen.
                        onOpenLookSwitch = {
                            pendingSection = "look"
                            pendingSectionScreen = Screen.SECURITY.name
                            nav.go(Screen.SECURITY)
                        },
                        // The "hey Jarvis" switches, moved here from Platform
                        // checks (settings audit 2026-09-30): they need a
                        // desktop, so only once paired.
                        voiceSwitches = if (paired) {
                            { VoiceSwitches() }
                        } else {
                            null
                        },
                        // Same three ternaries as Screen.CHECKS above: null
                        // until this phone is paired.
                        onTrainVoice = if (paired) {
                            { nav.go(Screen.VOICE) }
                        } else {
                            null
                        },
                        onVoiceCheck = if (paired) {
                            { nav.go(Screen.VOICE_CHECK) }
                        } else {
                            null
                        },
                        onVoices = if (paired) {
                            { nav.go(Screen.VOICES) }
                        } else {
                            null
                        },
                        securitySummary = SecurityRules.summary(security),
                        onOpenSecurity = { nav.go(Screen.SECURITY) },
                        onOpenAppearance = if (paired) {
                            { nav.go(Screen.APPEARANCE) }
                        } else {
                            null
                        },
                        floatingAvatar = floatingAvatar,
                        onFloatingAvatarChange = { JarvisRuntime.settings.setFloatingAvatar(it) },
                        overlayGranted = remember(tick) {
                            Settings.canDrawOverlays(this@MainActivity)
                        },
                        onRequestOverlay = ::requestOverlayPermission,
                        onOpenBubbleSettings = ::openBubbleSettings,
                        notificationAccessGranted = remember(tick) {
                            NotificationManagerCompat.getEnabledListenerPackages(this@MainActivity)
                                .contains(packageName)
                        },
                        onOpenNotificationAccess = ::openNotificationAccessSettings,
                        quickTiles = quickTiles,
                        onQuickTileChange = { slot, action ->
                            JarvisRuntime.settings.setQuickTile(slot, action)
                        },
                    )

                    Screen.APPEARANCE -> AppearanceScreen(
                        current = chrome,
                        followSystem = followSystem,
                        face = face,
                        bindings = bindings,
                        onPickTheme = {
                            // Picking a theme by hand turns following OFF, and that
                            // is half of one fix rather than a preference.
                            //
                            // The audit found that following silently stopped
                            // working after a manual pick: the effect that applies
                            // the system's choice did not re-run on a theme change,
                            // so the app sat on the hand-picked theme while the
                            // switch still claimed to follow a system set the other
                            // way. Adding `chrome` to that effect's keys makes the
                            // switch honest again — but on its own it makes the
                            // manual pick futile instead, because the effect now
                            // immediately snaps the theme back, which is a worse
                            // answer than the bug was.
                            //
                            // Both halves together are the behaviour that is
                            // actually coherent: a deliberate pick wins AND the
                            // switch tells the truth about what it is doing.
                            //
                            // Only when the change was accepted. A pick refused by
                            // the photosensitivity dwell governor did not change
                            // the theme, so it must not change the switch either.
                            if (appearance.setTheme(it)) {
                                appearance.setFollowSystem(false)
                            } else {
                                JarvisRuntime.setNotice("One theme change at a time — give it a moment.")
                            }
                        },
                        onFollowSystem = appearance::setFollowSystem,
                        // Each pushes the shared document afterward - a no-op,
                        // silently, on a backend without the `appearance`
                        // capability. The theme itself is never pushed; only the
                        // face and its bindings are the shared vocabulary.
                        onPickFace = {
                            appearance.setFace(it.id)
                            scope.launch {
                                JarvisRuntime.pushAppearance()
                                // An animal picked for the first time: the PC
                                // may now ask "Use its own voice?" - read it.
                                JarvisRuntime.refreshCustomVoices()
                            }
                        },
                        // Randomise and Reset do NOT push straight away any more.
                        // The screen offers ten seconds of Undo, and the desktop
                        // is sent the colours once that window closes - through
                        // onBindingsSettled below - so a roll the owner undid
                        // never reaches the desktop at all (custom-10).
                        onRandomise = { appearance.randomise() },
                        onResetBindings = { appearance.resetBindings() },
                        // Not pushed: the face's size on Home is this phone's
                        // taste, not part of the vocabulary shared with the desktop.
                        faceSize = faceSize,
                        onPickFaceSize = appearance::setFaceSize,
                        onBack = { nav.back() },
                        notice = notice,
                        onDismissNotice = { JarvisRuntime.clearNotice() },
                        modifier = root,
                        look = look,
                        onLookChange = appearance::setLook,
                        preferredDark = preferredDark,
                        // Sets the dark theme and leaves Follow the system on,
                        // unlike a normal theme pick, which turns it off.
                        onPickDarkTheme = appearance::setPreferredDark,
                        // Both halves, not just the capability: the screen's
                        // own words follow whether the last send actually
                        // landed (UI audit 2026-10-05, finding A1). `capable`
                        // alone used to make it claim a send that a dead link
                        // had dropped on the floor.
                        sharedStatus = AppearanceShared.statusOf(
                            capability = version?.can("appearance") == true,
                            sendOk = appearanceSent,
                        ),
                        onUndoBindings = { appearance.setBindings(it) },
                        // On the runtime's scope, not a composition one: this can
                        // fire from the screen's onDispose as it leaves, and on a
                        // rotation every composition scope is being cancelled at
                        // that same moment.
                        onBindingsSettled = { JarvisRuntime.pushAppearanceDetached() },
                        // The face editor. Pattern and colour edit the shared
                        // state colours (pushed once editing settles, through
                        // onBindingsSettled above); everything else in it is
                        // this phone's own and never leaves it.
                        onEditBinding = appearance::setBinding,
                        faceTuning = faceTuning,
                        onFaceTuningChange = appearance::setFaceTuning,
                        phoneBatterySaver = phoneSaver,
                        // "Animal options" (2026-09-28): the shared Still the
                        // preview wears, and the way to the animal's voice.
                        stillAnimal = stillAnimal,
                        onOpenVoices = if (paired) {
                            { nav.go(Screen.VOICES) }
                        } else {
                            null
                        },
                        // Still pictures, one per face, instead of name-only chips.
                        faceTile = { f, selected, onClick ->
                            FaceSpecimen(face = f, bindings = bindings, isSelected = selected, onClick = onClick)
                        },
                        faceVoiceOffer = {
                            FaceVoiceOfferFromPc(linkBlocker = remember(link, stale) { JarvisRuntime.actionBlocker() })
                        },
                    )

                    Screen.HOME -> HomeScreen(
                        state = HomeState(
                            link = link,
                            linkDetail = linkDetail,
                            vpnLine = vpnLine,
                            stale = stale,
                            activity = activity,
                            faceState = faceState,
                            faceOffline = faceOffline,
                            faceFocusQuiet = faceFocusQuiet,
                            faceSerious = faceSerious,
                            power = power,
                            status = status,
                            pending = pending,
                            attention = attention,
                            notice = notice,
                            streaming = streaming,
                            face = face,
                            bindings = bindings,
                            voicePhase = voicePhase,
                            voiceOffered = voiceStatus.canPushToTalk,
                            transcript = transcript,
                            voiceNotice = voiceNotice,
                            approvalsOff = "approvals" in absent,
                            deciding = deciding,
                            focusApproval = focusApproval.value,
                            activityDetail = activityDetail,
                            faceSize = faceSize,
                            faceFraction = look.faceFraction,
                            navAlwaysShown = look.navAlwaysShown,
                            makeRoomForApprovals = look.makeRoomForApprovals,
                            shrinkWhileTyping = look.shrinkWhileTyping,
                            followReply = look.followReply,
                            tapFaceOpensMind = look.tapFaceOpensMind,
                            glow = look.glow,
                            calmMotion = calmMotion,
                            stillAnimal = stillAnimal,
                            lastUserText = lastQuestion,
                            answerFeedback = Feedback.viewFor(answerTurnId, answerMark),
                            conversationTurns = conversation.size,
                            // The pairs above the one on screen.
                            thread = com.jarvis.client.net.ChatHistory.threadBefore(
                                thread, lastQuestion, streaming, answered = answeredNow,
                            ),
                            chatNote = chatNote,
                            readOutside = readOutsideChat,
                            idleNextLine = if (idleQuiet && !streaming) {
                                if (temporaryChat || gameChat) {
                                    com.jarvis.client.net.ChatHistory.IDLE_NEXT_LINE_TEMPORARY
                                } else {
                                    com.jarvis.client.net.ChatHistory.IDLE_NEXT_LINE
                                }
                            } else {
                                null
                            },
                            chatWaiting = chatWaiting,
                            answerNote = answerNote,
                            quickNoteOpen = quickNoteOpen.value,
                            // The second card's Pictures feature, or the PC
                            // reading the words in a picture (2026-09-26), as
                            // the PC last reported it. The send asks again first.
                            pictureOffered = SecondCard.picturesTaken(secondCard),
                            // Reading phone notifications (2026-09-28): only
                            // offered once the setting is on AND something
                            // has actually been captured - a button that
                            // would attach nothing is not an offer.
                            notificationsAttachable = remember(tick) {
                                JarvisRuntime.phoneNotificationsAllowed() &&
                                    com.jarvis.client.data.CapturedNotifications(this@MainActivity)
                                        .sharedText() != null
                            },
                            pictureLine = picture.value?.let {
                                ChatPicture.attachedLine(it, wordsOnly = !SecondCard.visionAvailable(secondCard))
                            },
                            sharedLine = sharedHeld?.let { Provenance.sharedLine(it) },
                            lookLine = lookLine,
                            watchSign = watchSign,
                            phoneWatchOffered = security.screenRead,
                            phoneWatchSign = phoneWatchSign,
                            usageAccess = remember(tick) {
                                com.jarvis.client.service.ScreenWatchService.usageAccessGranted(this@MainActivity)
                            },
                            pictureBusy = pictureBusy.value,
                            photoFinding = photoFinding.value,
                            noteTargets = noteTargets,
                            updateLine = updateState.newerLine.takeIf { updateChecks },
                            keepAliveOffer = PlatformReadiness.BACKGROUND_RESTART_NOT_ALLOWED
                                .takeIf { keepAliveOfferShown },
                            temporary = temporaryChat,
                            usedIds = usedIds,
                            topicsLeftOut = topicsLeftOut,
                            answerTurnId = answerTurnId,
                            answerTableId = answerTableId,
                            crisisAnswer = crisisAnswer,
                            cloudOffer = cloudOffer,
                            inboxTidy = inboxTidyHeld?.let { held ->
                                com.jarvis.client.net.InboxTidy.strip(
                                    com.jarvis.client.net.InboxTidy.aged(
                                        held.status,
                                        inboxTidyClock - held.atMs,
                                    ),
                                    locked = privateHidden,
                                    stale = stale || link != LinkState.CONNECTED,
                                )
                            },
                            inboxTidyBusy = inboxTidyBusy,
                            memoryHidden = privateHidden,
                            swipeDecides = security.swipeDecides,
                            showPrivateBusy = ownerCheckBusy.value,
                            noticeProblem = shownProblem,
                            lockdown = lockdown,
                        ),
                        // A lambda, so a streamed token redraws the reply and
                        // nothing else. Passing the string rebuilt HomeState on
                        // every chunk and recomposed the bar, the list and the
                        // composer while the face drew at 60fps on the same thread.
                        reply = { replyState.value },
                        // Same treatment as `reply`, for the same reason. `draft`
                        // was read here while building HomeState, so one keystroke
                        // invalidated App(), rebuilt the whole state and recomposed
                        // the link bar, the face block, every visible approval card
                        // and the reply - on the thread already drawing the reactor
                        // at 120fps. As a lambda the snapshot read happens inside
                        // the composer, and a keystroke recomposes the composer
                        // alone.
                        draft = { draft },
                        micLevel = micLevel,
                        speechLevel = speechLevel,
                        speechMouth = speechMouth,
                        actions = remember {
                            HomeActions(
                                onDraftChange = {
                                    draftPasted = Provenance.pastedAfter(draftPasted, draft, it)
                                    draft = it
                                },
                                onDropShared = { sharedHeld = null },
                                onForgetLook = { com.jarvis.client.net.ScreenLook.drop() },
                                onStopWatching = { JarvisRuntime.stopScreenWatch() },
                                onStartPhoneWatch = { startPhoneWatch() },
                                onStopPhoneWatch = { com.jarvis.client.net.ScreenWatch.requestStop() },
                                onOpenUsageAccess = { openUsageAccess() },
                                onSend = {
                                    val text = draft
                                    val pic = picture.value
                                    // Where the words came from, and any shared
                                    // text held beside them - both read NOW,
                                    // as the question goes (section 18).
                                    val tag = Provenance.forComposer(draftPasted)
                                    val shared = sharedHeld
                                    // `#log`, `#obs`, `#joplin` ... at the start
                                    // files the rest as a note instead of asking
                                    // Jarvis, as on the desktop. An attached
                                    // picture stays for the next question. The
                                    // words stay in the box unless the desktop
                                    // took the note. A note files the typed
                                    // words only; shared text stays in its chip
                                    // for the next question.
                                    val note = NoteCapture.prefixed(text)
                                    if (note != null) {
                                        scope.launch {
                                            if (JarvisRuntime.fileChatNote(note) && draft == text) {
                                                draft = ""
                                                draftPasted = false
                                            }
                                        }
                                    } else if (pic == null) {
                                        draft = ""
                                        draftPasted = false
                                        sharedHeld = null
                                        scope.launch { chat.send(text, provenance = tag, shared = shared) }
                                    } else {
                                        // With a picture, the PC is asked first
                                        // whether Pictures still works; if not,
                                        // nothing is sent and the draft, the
                                        // shared text and the picture stay where
                                        // they are.
                                        scope.launch {
                                            val why = JarvisRuntime.pictureBlocker()
                                            if (why != null) {
                                                JarvisRuntime.setNotice(why)
                                            } else {
                                                draft = ""
                                                draftPasted = false
                                                if (sharedHeld == shared) sharedHeld = null
                                                picture.value = null
                                                chat.send(text, picture = pic.dataUri, provenance = tag, shared = shared)
                                            }
                                        }
                                    }
                                },
                                onAttachPicture = {
                                    pickPicture.launch(
                                        PickVisualMediaRequest.Builder()
                                            .setMediaType(ActivityResultContracts.PickVisualMedia.ImageOnly)
                                            .build(),
                                    )
                                },
                                onRemovePicture = { picture.value = null },
                                // Fills the SAME shared-text chip the Share
                                // sheet already uses - the owner still
                                // presses Send. Never sent, learned, or read
                                // by anything until they do.
                                onAttachNotifications = {
                                    com.jarvis.client.data.CapturedNotifications(this@MainActivity)
                                        .sharedText()
                                        ?.let { sharedHeld = Provenance.joinShared(sharedHeld, it) }
                                },
                                onFindDateInPicture = ::findDateInPicture,
                                onInterrupt = { chat.cancel() },
                                // Said on Home, and read out by TalkBack (the chat audit).
                                onNewConversation = { chat.newConversationSaid() },
                                onEarlierChats = { nav.go(Screen.HISTORY) },
                                onDismissChatNote = { chat.dismissChatNote() },
                                // A temporary chat: no card and no hold - it only
                                // makes Jarvis stricter. A PC without it says so.
                                onToggleTemporary = {
                                    JarvisRuntime.setTemporaryChat(!chat.temporary.value)
                                        ?.takeIf { it == com.jarvis.client.net.TemporaryChat.UNAVAILABLE }
                                        ?.let { JarvisRuntime.setNotice(it) }
                                },
                                // "Used 2 memories": the words read by id, Forget
                                // on one fact after the confirm, held on a stale link.
                                onLoadUsed = { ids -> JarvisRuntime.memoryUsed(ids) },
                                onForgetUsed = { id -> JarvisRuntime.forgetAutoFact(id) },
                                onLoadSources = { tid -> JarvisRuntime.chatSources(tid) },
                                onLoadSpendingTable = { tid -> JarvisRuntime.spendingTable(tid) },
                                onShowPrivate = ::showPrivateLists,
                                // A fingerprint instead of a tap for anything that
                                // leaves the machine, cannot be undone, or arrived
                                // with a rush latch on it. The phone is the surface
                                // most likely to be handed to someone or left
                                // unlocked, and this is the class of action where
                                // "whoever is holding it" and "the owner" need to
                                // be different answers.
                                onApprove = { item ->
                                    scope.launch { approveItem(item) }
                                },
                                onDeny = { item -> JarvisRuntime.decideDetached(item, approve = false) },
                                onApproveWithReset = { item, onReset ->
                                    scope.launch {
                                        val sent = approveItem(item)
                                        if (!sent) onReset()
                                    }
                                },
                                onDenyWithReset = { item, onReset ->
                                    JarvisRuntime.decideDetached(item, approve = false)
                                },
                                onReconnect = {
                                    // `force = true`, and only because a person
                                    // asked. startStream() returns early whenever
                                    // its job is still "active" - which a half-open
                                    // socket is, right up until OkHttp's 90 second
                                    // read timeout recycles it. So the one control
                                    // offered for a dead link did nothing at all
                                    // for up to a minute and a half, while every
                                    // approval stayed refused for being stale.
                                    // Automatic callers keep the unforced path, so
                                    // nothing else can storm the desktop with
                                    // reconnects.
                                    EventService.start(this@MainActivity)
                                    JarvisRuntime.startStream(force = true)
                                    scope.launch { JarvisRuntime.refreshAll() }
                                },
                                onDismissNotice = { JarvisRuntime.clearNotice() },
                                onOpenChecks = { nav.go(Screen.CHECKS) },
                                onOpenInbox = { nav.go(Screen.INBOX) },
                                onOpenBrain = { nav.go(Screen.BRAIN) },
                                onOpenAppearance = { nav.go(Screen.APPEARANCE) },
                                onOpenFaq = { nav.go(Screen.FAQ) },
                                // Jarvis Live (ui/screens/LiveScreen.kt).
                                onOpenLive = { nav.go(Screen.LIVE) },
                                // "Try again" under a failed question: the same
                                // words, tag and shared text, asked again.
                                onRetryQuestion = {
                                    JarvisRuntime.clearNotice()
                                    scope.launch { chat.retryLast() }
                                },
                                blockerFor = { item: PendingItem ->
                                    JarvisRuntime.decisionBlocker(item)
                                },
                                onVoiceBegin = ::beginVoice,
                                onVoiceRelease = ::releaseVoice,
                                onVoiceCancel = ::cancelVoice,
                                onDismissVoiceNotice = { JarvisRuntime.voice.clearNotice() },
                                // AUTONOMY-PROPOSALS.md §3b/§3d, served by the
                                // desktop's backend/task-control.patch: see
                                // JarvisRuntime's own doc comments on each.
                                onAmend = { id, note -> JarvisRuntime.amendPending(id, note) },
                                onPauseTask = { JarvisRuntime.pauseTask() },
                                onResumeTask = { JarvisRuntime.resumeTask() },
                                onStopTask = { JarvisRuntime.stopTask() },
                                // The desktop's Alt+Shift+X, as a button:
                                // this phone's speech, then POST /api/stop_all.
                                onStopEverything = { JarvisRuntime.stopEverything() },
                                onPcMedia = { JarvisRuntime.pcMedia() },
                                onPcMediaControl = { action -> JarvisRuntime.pcMediaControl(action) },
                                onInjectTaskNote = { note -> JarvisRuntime.injectTaskNote(note) },
                                // Saved only when the owner's own drag (or a
                                // screen reader's Bigger/Smaller) finishes - never
                                // Home's temporary shrink for an approval or the
                                // keyboard, which would overwrite their layout.
                                onFaceFractionCommitted = appearance::setFaceFraction,
                                // One answer, one mark. The runtime refuses on a
                                // stale link and works out set / change / take back.
                                onMarkAnswer = { turnId, mark ->
                                    JarvisRuntime.markAnswerDetached(turnId, mark)
                                },
                                // "Try the cloud model": a genuinely new
                                // turn, the same shape as onSend below, so
                                // it runs on this composable's own scope
                                // rather than the runtime's - a rotation
                                // mid-answer already cancels an ordinary
                                // question the same way.
                                onTryCloud = { scope.launch { chat.tryCloudForLast() } },
                                onDismissCloudOffer = { chat.dismissCloudOffer() },
                                // "Inbox tidy by voice": Undo, one tap, no
                                // card. Held on a stale link in the runtime.
                                onInboxUndo = { JarvisRuntime.inboxTidyUndoDetached() },
                                // backend/note-capture.patch. The runtime reports
                                // how it ended, in the desktop's own words.
                                onFileNote = { target, text ->
                                    JarvisRuntime.fileNote(target, text) is ApiResult.Ok
                                },
                                // Only the note apps the desktop says are set up.
                                onLoadNoteTargets = { JarvisRuntime.noteTargets() },
                                onQuickNoteOpenChange = { open -> quickNoteOpen.value = open },
                                onOpenUpdate = ::openReleasePage,
                                onOpenLockSettings = ::openLockSettings,
                                // The owner's one tap (design §11): the key is made
                                // here, the PC raises its own card.
                                onTurnOnSignedApprovals = {
                                    scope.launch { JarvisRuntime.setNotice(JarvisRuntime.turnOnSignedApprovals()) }
                                },
                                onKeepLinkAlive = {
                                    JarvisRuntime.settings.answerKeepAliveOffer()
                                    requestBatteryExemption()
                                },
                                onDismissKeepAlive = { JarvisRuntime.settings.answerKeepAliveOffer() },
                            )
                        },
                        modifier = root,
                    )
                }
                // "Open the card" (CardWaitingLine): on every screen but Home
                // while a card waits - one a button on this screen raised, or
                // any other. It only opens Home on that card; approving there
                // is still a deliberate tap. An empty Box lets touches through
                // to the screen underneath.
                if (screen != Screen.HOME && pending.isNotEmpty()) {
                    Box(
                        Modifier
                            .fillMaxSize()
                            .windowInsetsPadding(WindowInsets.systemBars)
                            .padding(12.dp),
                        contentAlignment = Alignment.BottomCenter,
                    ) {
                        CardWaitingLine(
                            pending = pending,
                            onOpen = { id ->
                                nav.resetTo(Screen.HOME)
                                focusApproval.value = id
                                scope.launch { JarvisRuntime.refreshPending() }
                            },
                        )
                    }
                }
            }
        }
    }

    /**
     * "Listen on this phone" on the Checks screen. Starts [WakeWordService]
     * only when the desktop's wake word is on and both permissions are held;
     * otherwise asks for what is missing and says so. Never starts listening
     * on a permission grant - the owner taps again, the same rule as the
     * talk button (see [micGrantedCallback]).
     *
     * @return null when listening was started, or the sentence to show.
     */
    private fun startPhoneListening(): String? {
        val voice = JarvisRuntime.voice
        WakeRules.mayListen(voice.answered.value, voice.status.value)?.let { return it }
        if (!voice.recorder.hasPermission()) {
            micGrantedCallback = null
            micPermission.launch(Manifest.permission.RECORD_AUDIO)
            return "Allow the microphone, then tap Listen on this phone again."
        }
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            // Jarvis listens only with a notification saying it is.
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            return "Allow notifications first - Jarvis only listens with a notification " +
                "showing that it is. Then tap Listen on this phone again."
        }
        WakeWordService.start(this)
        return null
    }

    /**
     * Opens the microphone, asking for permission first if it has not been
     * granted — and then starting the capture, so the hold that triggered the
     * dialog is not wasted.
     */
    private fun beginVoice() {
        val voice = JarvisRuntime.voice
        if (voice.recorder.hasPermission()) {
            voice.begin()
            return
        }
        micGrantedCallback = { voice.begin() }
        micPermission.launch(Manifest.permission.RECORD_AUDIO)
    }

    /**
     * [VoiceButton]'s `onVoiceRelease`/`onVoiceCancel`, not
     * `JarvisRuntime.voice.release()`/`.cancel()` directly.
     *
     * On a FIRST hold, `beginVoice()` above only launches the permission
     * dialog and returns - `voice.begin()` runs later, from
     * [micGrantedCallback], once the async result comes back. A finger that
     * lifts (or slides to cancel) before that result arrives calls
     * `voice.release()`/`.cancel()` while `VoiceSession.current` is still
     * null, which is a no-op: there is no turn yet to stop. `micGrantedCallback`
     * then fires anyway the moment permission lands, opening the microphone
     * for a gesture that already ended, with nothing left able to close it
     * before the recorder's own 30-second cap. Dropping the callback here -
     * on the SAME main-thread event queue as the permission result, so
     * whichever of the two actually happens first is what deterministically
     * wins - is what closes that: either this runs first and the grant
     * callback finds nothing to invoke, or the grant already ran and set
     * `current`, in which case `release`/`cancel` below finds a real turn
     * and stops it exactly as it always did.
     */
    private fun releaseVoice() {
        micGrantedCallback = null
        JarvisRuntime.voice.release()
    }

    private fun cancelVoice() {
        micGrantedCallback = null
        JarvisRuntime.voice.cancel()
    }

    /**
     * @return true when the decision may proceed.
     *
     * Which approvals ask, and what each outcome means, is
     * [SecurityRules.approvalNeedsCheck] and [SecurityRules.afterApprovalCheck],
     * from the owner's Security settings. A *dismissed* prompt refuses, a
     * check that could not be shown just now holds the decision and says so,
     * and a phone that cannot check at all - no screen lock - refuses, with
     * a notice that says how to fix it and a button that opens Android's
     * screen-lock settings (the owner's "no lock, no risky approval",
     * 2026-09-25; it used to let a risky approval through unchecked).
     */
    private suspend fun confirmed(item: PendingItem): Boolean {
        val s = currentSecurity()
        if (!SecurityRules.approvalNeedsCheck(s, item)) return true
        val outcome = withOwnerCheck { BiometricGate.confirm(this, item, s.method) }
        return when (val verdict = SecurityRules.afterApprovalCheck(s, outcome)) {
            SecurityRules.Verdict.Go -> true
            is SecurityRules.Verdict.Stop -> {
                verdict.say?.let { JarvisRuntime.setNotice(it) }
                false
            }
        }
    }

    /**
     * Approve [item]. Which way it goes is [SignedApproval.pathFor]: a risky
     * card on a paired phone with signed approvals on is signed with the
     * fingerprint or PIN (docs/PAIRING-DESIGN.md §11); a paired phone
     * without them is offered the one button that turns them on; everything
     * else - a card that is not risky, the old shared key, a PC that does
     * not know signed approvals, or a PC that could not be read - takes
     * today's way, and the PC says `no_approval_key` if it needed one.
     */
    private suspend fun approveItem(item: PendingItem): Boolean {
        val risky = SecurityRules.riskyByToday(item)
        // pcOnly and needsChoice cards are refused in decide() with their own words.
        val read = if (risky && !item.pcOnly && !item.needsChoice) JarvisRuntime.signedApprovalRead() else null
        return when (val path = SignedApproval.pathFor(risky, read?.state)) {
            SignedApproval.Path.PLAIN -> {
                if (confirmed(item)) {
                    JarvisRuntime.decideDetached(item, approve = true)
                    true
                } else {
                    false
                }
            }
            SignedApproval.Path.SIGNED -> signedApprove(item, read?.device)
            SignedApproval.Path.OFFER,
            SignedApproval.Path.OFFER_AGAIN,
            SignedApproval.Path.WAITING,
            -> {
                SignedApproval.noticeFor(path)?.let { JarvisRuntime.setNotice(it) }
                false
            }
        }
    }

    /**
     * The signed way: a nonce from the PC, the words checked against what this
     * phone showed, the fingerprint prompt with the approval key, the signature.
     * Nothing here is logged.
     */
    private suspend fun signedApprove(item: PendingItem, device: String?): Boolean {
        if (device == null) {
            JarvisRuntime.setNotice(SignedApproval.OFFER_WORDS)
            return false
        }
        val challenge = JarvisRuntime.beginSignedApproval(item) ?: return false
        val key = try {
            ApprovalKey.newSignature()
        } catch (e: KeyPermanentlyInvalidatedException) {
            JarvisRuntime.setNotice(SignedApproval.OFFER_AGAIN_WORDS)
            return false
        } catch (e: Exception) {
            JarvisRuntime.setNotice(SignedApproval.SIGN_FAILED)
            return false
        }
        val s = currentSecurity()
        var result: BiometricGate.Signed? = null
        val outcome = withOwnerCheck {
            val signed = BiometricGate.sign(this, item, s.method, key)
            result = signed
            signed.outcome
        }
        when (val verdict = SecurityRules.afterApprovalCheck(s, outcome)) {
            SecurityRules.Verdict.Go -> Unit
            is SecurityRules.Verdict.Stop -> {
                verdict.say?.let { JarvisRuntime.setNotice(it) }
                return false
            }
        }
        val unlocked = result?.signature
        if (unlocked == null) {
            JarvisRuntime.setNotice(SignedApproval.SIGN_FAILED)
            return false
        }
        val der = try {
            unlocked.update(
                SignedApproval.signedMessage(
                    item.id,
                    item.action.orEmpty(),
                    challenge.nonce,
                    SignedApproval.wordsSha256(item),
                ),
            )
            unlocked.sign()
        } catch (e: java.security.GeneralSecurityException) {
            JarvisRuntime.setNotice(SignedApproval.SIGN_FAILED)
            return false
        }
        JarvisRuntime.decideDetached(
            item,
            approve = true,
            signature = SignedApproval.Signature(device, challenge.nonce, SignedApproval.b64url(der)),
        )
        return true
    }

    private fun currentSecurity(): Security = JarvisRuntime.settings.security.value

    /**
     * Runs one fingerprint or PIN check with the lock clock told about it:
     * Android's PIN screen takes Jarvis out of sight, and that must not
     * count as being away ([LockSession.endCheck]).
     */
    private suspend fun withOwnerCheck(check: suspend () -> CheckOutcome): CheckOutcome {
        lockSession.beginCheck()
        var outcome = CheckOutcome.CANCELLED
        try {
            outcome = check()
            return outcome
        } finally {
            lockSession.endCheck(outcome, SystemClock.elapsedRealtime(), currentSecurity())
            lockTick.intValue += 1
        }
    }

    /**
     * One check that is not an approval - Unlock, Show, or a loosened
     * setting - with the owner's current method. [then] runs on a confirmed
     * check; anything else ends with [onStop]'s sentence (null when the
     * owner simply dismissed it).
     */
    private fun ownerCheck(
        title: String,
        method: CheckMethod,
        whatStays: String,
        onStop: (String?) -> Unit,
        then: () -> Unit,
    ) {
        if (ownerCheckBusy.value) return
        ownerCheckBusy.value = true
        lifecycleScope.launch {
            try {
                val outcome = withOwnerCheck {
                    BiometricGate.check(this@MainActivity, title, "Confirm it is you.", method)
                }
                when (val verdict = SecurityRules.afterOwnerCheck(method, outcome, whatStays)) {
                    SecurityRules.Verdict.Go -> then()
                    is SecurityRules.Verdict.Stop -> onStop(verdict.say)
                }
                lockTick.intValue += 1
            } finally {
                ownerCheckBusy.value = false
            }
        }
    }

    private fun unlockApp() {
        ownerCheck(
            title = "Open Jarvis",
            method = currentSecurity().method,
            whatStays = "Jarvis stays locked",
            onStop = { lockMessage.value = it },
        ) {
            lockSession.unlock()
            lockMessage.value = null
        }
    }

    private fun showPrivateLists() {
        ownerCheck(
            title = "Show memory lists",
            method = currentSecurity().method,
            whatStays = "the lists stay hidden",
            onStop = { say -> say?.let { JarvisRuntime.setNotice(it) } },
        ) { lockSession.showPrivate() }
    }

    /**
     * Every Security change comes through here. Tightening is saved at once,
     * unless it would lock the owner out ([SecurityRules.refuseTightening]).
     * Loosening waits for a check with the method in force NOW - the
     * stricter one, when the method itself is what is being loosened.
     */
    private fun changeSecurity(to: Security) {
        val from = currentSecurity()
        if (to == from || ownerCheckBusy.value) return
        securityNotice.value = null
        if (!SecurityRules.loosens(from, to)) {
            val refused = SecurityRules.refuseTightening(to, BiometricGate.availability(this, to.method))
            if (refused != null) {
                securityNotice.value = refused
                return
            }
            // The owner is the one holding the phone: turning the lock on
            // does not lock them out of the screen they are on.
            if (to.appLock && !from.appLock) lockSession.lockTurnedOn()
            JarvisRuntime.settings.setSecurity(to)
            lockTick.intValue += 1
            return
        }
        ownerCheck(
            title = "Loosen security",
            method = from.method,
            whatStays = "nothing was changed",
            onStop = { securityNotice.value = it },
        ) {
            // Only if nothing else changed them while the prompt was up.
            if (currentSecurity() == from) JarvisRuntime.settings.setSecurity(to)
        }
    }

    /**
     * Jarvis came back into sight. The lock clock decides whether that
     * was long enough away to lock again ([LockSession.returned]).
     */
    override fun onStart() {
        super.onStart()
        if (JarvisRuntime.isInitialized) {
            lockSession.returned(SystemClock.elapsedRealtime(), currentSecurity())
            lockTick.intValue += 1
        }
    }

    override fun onStop() {
        super.onStop()
        // A rotation stops and restarts the activity. That is not "away".
        if (!isChangingConfigurations) lockSession.left(SystemClock.elapsedRealtime())
    }

    override fun onResume() {
        super.onResume()
        permissionTick.intValue += 1
        // The rate can change under us — battery saver, brightness, heat — and
        // nothing reports why, so re-read rather than trust the request.
        DisplayRate.refresh(this)
        if (JarvisRuntime.isPaired()) {
            // Cheap, and safe to call on resume — the doc says so explicitly.
            lifecycleScope.launch { JarvisRuntime.refreshStatus() }
            // Coming back to a link that is "Catching up…" reconnects at
            // once, the same forced reconnect as Home's Retry (phone
            // walk-through, 2026-09-27). After the phone slept the socket is
            // often half-dead, and nothing used to replace it until a 90
            // second read timeout noticed - so the owner opened Jarvis to an
            // approval they could not act on and no sign anything was being
            // done. Only for that state (LinkWords.reconnectOnReturn): the
            // stream is already running in this process, so no service start
            // is needed, and after the forced restart the link reads
            // "reconnecting", so returning from a permission prompt a moment
            // later does not force a second one. Approves nothing; acting
            // stays blocked until the link is trusted (rule 4).
            if (JarvisRuntime.isInitialized &&
                LinkWords.reconnectOnReturn(
                    link = JarvisRuntime.link.value,
                    stale = JarvisRuntime.stale.value,
                    reason = JarvisRuntime.linkDetail.value,
                )
            ) {
                JarvisRuntime.startStream(force = true)
            }
        }
    }

    /**
     * Android's own screen-lock settings, from the notice that a risky
     * approval was refused because this phone has no screen lock. The
     * general Security page if this phone has no such screen.
     */
    private fun openLockSettings() {
        runCatching { startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS)) }.onFailure {
            runCatching { startActivity(Intent(Settings.ACTION_SETTINGS)) }
        }
    }

    /**
     * The client-latest release page, in the phone's own browser. The
     * address is fixed in [UpdateCheck.RELEASE_PAGE], never taken from
     * GitHub's answer. Nothing is downloaded here: installing stays the
     * owner's own step, as it always was.
     */
    private fun openReleasePage() {
        runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(UpdateCheck.RELEASE_PAGE))) }
            .onFailure { JarvisRuntime.setNotice("No browser on this phone could open the release page.") }
    }

    /**
     * "Draw over other apps" for the Overlay path of "Floating Jarvis"
     * ([FloatingAvatarSection]'s own explanation is shown first, always -
     * this is only ever called from its button). Android's own screen, with
     * its own warning about this permission; never granted silently, and
     * the `LaunchedEffect(floatingAvatar, tick)` above keeps reading the
     * real answer either way.
     */
    private fun requestOverlayPermission() {
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:$packageName"),
        )
        runCatching { startActivity(intent) }.onFailure {
            runCatching { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION)) }
        }
    }

    /**
     * Android's own per-app "Allow bubbles" screen, for the Bubble path of
     * "Floating Jarvis". This app has no other way to change that switch -
     * only the owner, in Android's own settings, can.
     */
    private fun openBubbleSettings() {
        val intent = Intent(Settings.ACTION_APP_NOTIFICATION_BUBBLE_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
        runCatching { startActivity(intent) }.onFailure {
            runCatching {
                startActivity(
                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, packageName),
                )
            }
        }
    }

    /**
     * Android's own "Notification access" screen
     * (`Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS`), for "reading
     * phone notifications". `PhoneNotificationsPlate.kt`'s own explanation
     * of what this OS-level access actually grants is shown BEFORE this is
     * ever called, always - it is unusually broad (every notification, on
     * every app, once granted), unlike an ordinary runtime permission
     * dialog, and there is no direct way to grant it: only this screen,
     * only the owner's own tap. `notificationAccessGranted` keeps reading
     * the real answer either way, the same pattern `overlayGranted` above
     * already follows.
     */
    private fun openNotificationAccessSettings() {
        runCatching { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
            .onFailure { runCatching { startActivity(Intent(Settings.ACTION_SETTINGS)) } }
    }

    /**
     * Opens the platform's own exemption dialog. Never granted silently, and the
     * readiness screen keeps reporting the real state either way.
     */
    private fun requestBatteryExemption() {
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        runCatching { startActivity(intent) }.onFailure {
            runCatching {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            }
        }
    }

    /**
     * Opens the system's own "make Jarvis the assistant app" dialog.
     *
     * `RoleManager.createRequestRoleIntent` is the only way onto this dialog -
     * there is no direct grant, and there should not be one: choosing the
     * assistant app is the owner's decision, made in the system's own UI,
     * the same as every other role request on the platform.
     */
    private fun requestAssistantRole() {
        val rm = getSystemService(RoleManager::class.java) ?: return
        if (!runCatching { rm.isRoleAvailable(RoleManager.ROLE_ASSISTANT) }.getOrDefault(false)) return
        val intent = rm.createRequestRoleIntent(RoleManager.ROLE_ASSISTANT)
        runCatching { assistantRolePermission.launch(intent) }
    }

    companion object {
        /** Fired by [com.jarvis.client.widget.QuickLinkWidget]'s Mic action. */
        const val ACTION_START_VOICE = "com.jarvis.client.action.START_VOICE"

        /** Fired by [com.jarvis.client.widget.QuickLinkWidget]'s Note action. */
        const val ACTION_QUICK_NOTE = "com.jarvis.client.action.QUICK_NOTE"

        /** Fired by the "your morning briefing is ready" notification ([com.jarvis.client.service.ScheduleNotifier]). */
        const val ACTION_OPEN_BRIEFING = "com.jarvis.client.action.OPEN_BRIEFING"

        /** Fired by the Jarvis Live notification ([com.jarvis.client.service.LiveService]). */
        const val ACTION_OPEN_LIVE = "com.jarvis.client.action.OPEN_LIVE"

        /** The assistant gesture looked at the screen: open Home. See [readLookIntent]. */
        const val ACTION_OPEN_LOOK = "com.jarvis.client.action.OPEN_LOOK"

        /**
         * The "\"Hey Jarvis\" is off since the phone restarted" notification's
         * tap ([com.jarvis.client.service.WakeResumeNotifier]): start "Listen
         * on this phone" from here, once App lock (if on) has been passed.
         */
        const val ACTION_RESUME_LISTENING = "com.jarvis.client.action.RESUME_LISTENING"

        /** An empty Quick Settings tile slot's tap: Settings, at "Quick Settings tiles". */
        const val ACTION_OPEN_TILE_SETTINGS = "com.jarvis.client.action.OPEN_TILE_SETTINGS"

        /** Fired by the Jarvis Live tile ([com.jarvis.client.service.LiveTileService]): start Live. */
        const val ACTION_START_LIVE = "com.jarvis.client.action.START_LIVE"

        /** Fired by "Live ended - Resume" ([com.jarvis.client.service.LiveService.showResume]). */
        const val ACTION_RESUME_LIVE = "com.jarvis.client.action.RESUME_LIVE"

        /** Fired by the "a website needs you" alert ([com.jarvis.client.service.HandoffNotifier]). */
        const val ACTION_OPEN_HANDOFF = "com.jarvis.client.action.OPEN_HANDOFF"

        /** The activity-alias the "Talk about this in Live" share entry opens this activity as. */
        const val SHARE_TO_LIVE = ".ShareToLive"
    }
}

/**
 * Whether a pairing attempt is in flight. Read and written as `busy` in
 * `App()`'s pairing branch.
 *
 * Neither saveable nor `remember`ed, on purpose. `busy` is cleared in
 * exactly one place: the `finally` of the handshake coroutine, which runs in
 * `rememberCoroutineScope()` and is cancelled with the composition.
 *
 * Saveable was tried first and was wrong: a rotation mid-pair killed the
 * coroutine while a saved `busy = true` came back with the new one, and
 * Connect stayed disabled behind a spinner until a force-stop.
 *
 * `remember` was wrong the other way. A cancelled attempt does not stop at
 * once: the network call already under way finishes first (up to the short
 * call timeout), and only then does the `finally` put the old desktop and
 * token back. A remembered flag came back `false` with the new composition,
 * so for that stretch Connect and "Keep current desktop" were live again
 * while the new, unchecked pair was still the saved one.
 *
 * Here the flag has the same lifetime as the work that clears it: both live
 * as long as the process, and the `finally` always runs. If the process dies,
 * the work is gone and the flag starts `false` again.
 */
private val pairingBusy = mutableStateOf(false)

/**
 * The app lock's clock ([LockSession]): whether Jarvis is unlocked and
 * whether Mind's memory lists are showing. Process-wide for the same reason
 * as [pairingBusy]: a rotation builds a new activity and must neither unlock
 * nor relock. Never saved - a new process always starts locked when the
 * app lock is on.
 */
private val lockSession = LockSession()

/**
 * Would App lock lock Jarvis now? Jarvis Live on this phone ends then
 * (JarvisRuntime's Live watcher; docs/LIVE-DESIGN.md): the owner may talk
 * with the Live screen away from them, but not past the point the app would
 * ask for the fingerprint or PIN again. Changes nothing.
 */
internal fun appLockWouldLock(nowMs: Long, security: com.jarvis.client.data.Security): Boolean =
    lockSession.wouldLock(nowMs, security)

/** How long the restart notice's tap waits for the link before asking the desktop anyway. */
private const val RESUME_LINK_WAIT_MS = 8_000L

/** How long after tapping the restart notice listening may still start (App lock in between). */
private const val RESUME_REQUEST_FRESH_MS = 2 * 60 * 1000L

/** SettingsScreen's key for "Quick Settings tiles" (its SETTINGS_ITEM_INDEX). */
private const val QUICK_TILES_SECTION = "quick-tiles"

/** How often, while the app stays open, the once-a-day update check is looked at. */
private const val UPDATE_RECHECK_MS = 60 * 60 * 1000L

/** How long to wait before re-offering a theme the dwell window refused. */
private const val THEME_RETRY_MS = 600L

/**
 * How often the refresh-rate choice is re-checked while it can still change on
 * its own (THINKING's time limit, battery saver, heat). Slow enough to cost
 * nothing, quick enough that battery saver lets go of 120 Hz within moments.
 */
private const val RATE_RECHECK_MS = 2_000L

/**
 * The stream's reason for a 401/403, exactly as `net/EventStream.kt` writes it.
 * Matched as a string because that is all `linkDetail` carries.
 */
private const val TOKEN_REFUSED_DETAIL = "Token refused"

/**
 * How long a notification-focused approval stays marked on the home list.
 *
 * Long enough to land on, short enough that tapping the same notification
 * again re-runs the scroll rather than finding the id already set.
 */
private const val FOCUS_HOLD_MS = 8_000L
