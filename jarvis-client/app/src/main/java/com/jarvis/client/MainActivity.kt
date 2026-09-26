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
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.CheckOutcome
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
import com.jarvis.client.net.CustomVoices
import com.jarvis.client.net.Feedback
import com.jarvis.client.net.NoteCapture
import com.jarvis.client.net.Provenance
import com.jarvis.client.net.SecondCard
import com.jarvis.client.net.UpdateCheck
import com.jarvis.client.platform.CrashLog
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.PictureEncoder
import com.jarvis.client.platform.PlatformReadiness
import com.jarvis.client.platform.PowerWatch
import com.jarvis.client.net.PendingItem
import com.jarvis.client.service.ApprovalNotifier
import com.jarvis.client.service.EventService
import com.jarvis.client.service.WakeWordService
import com.jarvis.client.net.WakeWord
import com.jarvis.client.voice.BargeIn
import com.jarvis.client.voice.WakeRules
import com.jarvis.client.ui.NavBackHandler
import com.jarvis.client.ui.NavScreens
import com.jarvis.client.ui.Screen
import com.jarvis.client.ui.approval.BiometricGate
import com.jarvis.client.ui.approval.CardWaitingLine
import com.jarvis.client.ui.rememberNavState
import com.jarvis.client.ui.screens.AppearanceScreen
import com.jarvis.client.ui.screens.BrainScreen
import com.jarvis.client.ui.screens.ConnectionInfo
import com.jarvis.client.ui.screens.CrashScreen
import com.jarvis.client.ui.screens.FaceSpecimen
import com.jarvis.client.ui.screens.FaqScreen
import com.jarvis.client.ui.screens.HistoryScreen
import com.jarvis.client.ui.screens.HomeActions
import com.jarvis.client.ui.screens.HomeScreen
import com.jarvis.client.ui.screens.HomeState
import com.jarvis.client.ui.screens.InboxScreen
import com.jarvis.client.ui.screens.LockedScreen
import com.jarvis.client.ui.screens.PairingScreen
import com.jarvis.client.ui.screens.ReadinessScreen
import com.jarvis.client.ui.screens.SecurityScreen
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

    /** The quick-note field on Home is open - see [readQuickNoteIntent]. */
    private val quickNoteOpen = mutableStateOf(false)

    /** The briefing notification was tapped - see [readBriefingIntent]. Consumed once. */
    private val openBriefingRequested = mutableStateOf(false)

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
     * A photo to send with the next question, made small enough for the PC,
     * or null. In memory only - never saved, never in a Bundle (a rotation
     * drops it; the owner picks it again). See [ChatPicture].
     */
    private val picture = mutableStateOf<ChatPicture.Ready?>(null)

    /** True while a picked photo is being decoded and shrunk. */
    private val pictureBusy = mutableStateOf(false)

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
        readShareIntent(intent)
        readVoiceIntent(intent)
        readQuickNoteIntent(intent)
        readBriefingIntent(intent)

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
        readQuickNoteIntent(intent)
        readBriefingIntent(intent)
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
     * `singleTask`, so a second share while the app is already open re-delivers
     * here rather than starting a new instance - same reason [readApprovalIntent]
     * needs the `onNewIntent` half too.
     */
    private fun readShareIntent(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
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
        val lockVersion = lockTick.intValue
        val locked = remember(lockVersion, security) { lockSession.locked(security) }
        val privateHidden = remember(lockVersion, security) { lockSession.privateHidden(security) }
        // While App lock or "Hide memory lists and chat history" is on, Jarvis
        // cannot be screenshotted, screen-recorded or cast, and its
        // recent-apps picture is blank rather than a snapshot of what the
        // lock hides (SecurityRules.blockScreenCapture; apps security audit
        // L5). Compose dialogs and popups inherit FLAG_SECURE from this
        // window (their securePolicy defaults to Inherit). Both are undone
        // the moment both settings are off.
        LaunchedEffect(security.appLock, security.privateLists) {
            val secure = SecurityRules.blockScreenCapture(security)
            setRecentsScreenshotEnabled(!secure)
            if (secure) {
                window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
            } else {
                window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
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
        val stale by JarvisRuntime.stale.collectAsState()
        val activity by JarvisRuntime.activity.collectAsState()
        val faceState by JarvisRuntime.face.collectAsState()
        val power by JarvisRuntime.power.collectAsState()
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
        // The failure behind the notice, in plain words, with its fix button
        // and scrubbed Details - only while the notice on screen IS it.
        val noticeProblem by JarvisRuntime.problem.collectAsState()
        val shownProblem = noticeProblem?.takeIf { notice != null && it.text == notice }
        val digest by JarvisRuntime.digest.collectAsState()
        val undo by JarvisRuntime.undo.collectAsState()
        val jobs by JarvisRuntime.jobs.collectAsState()
        // How each Inbox list's last read came back, so the screen can tell
        // "nothing waiting" apart from "could not read" (screens-3).
        val inboxRead by JarvisRuntime.inboxRead.collectAsState()
        val brain by JarvisRuntime.brain.collectAsState()
        val models by JarvisRuntime.models.collectAsState()
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
        // The conversation the next question carries (ChatHistory). Only its
        // size is shown; memory only, like the question itself.
        val conversation by chat.history.collectAsState()
        // What a turn is waiting on ("Waiting for your approval…"), and the
        // one line under a finished answer (cut short / from a cloud model).
        val chatWaiting by chat.waiting.collectAsState()
        val answerNote by chat.answerNote.collectAsState()
        // A temporary chat, and the facts the answer on screen used (ids
        // only) - docs/JARVIS-API.md sections 18.1 and 4, 2026-09-25.
        val temporaryChat by chat.temporary.collectAsState()
        val usedIds by chat.usedIds.collectAsState()
        // The crisis help line (jarvis_wellbeing.py, 2026-09-27): whether
        // the answer on screen is shown as a calm, plain panel.
        val crisisAnswer by chat.crisis.collectAsState()
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
        val tokenRefused = paired &&
            (linkDetail == TOKEN_REFUSED_DETAIL || notice == badTokenNotice)
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
            // is somewhere to talk to. Two screens are the exception. Checks,
            // because "why can I not connect" has to be answerable from here.
            // Help, because its first question is "Do I need Tailscale?", and
            // that is asked before pairing, not after.
            //
            // `repairing` shows this same screen to a phone that IS paired, so
            // the owner can change the desktop or the token.
            // Security too: it is opened from Checks, and its settings are
            // this phone's own, so there is no reason to pair first.
            if ((!paired || repairing) &&
                nav.current != Screen.CHECKS && nav.current != Screen.FAQ &&
                nav.current != Screen.SECURITY
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
                        if (notice == badTokenNotice) JarvisRuntime.clearNotice()
                    }
                }
                if (replacing) {
                    // System back does the same as the on-screen button.
                    // Composed after NavBackHandler, so it takes the press first.
                    BackHandler(onBack = leaveRepair)
                }
                PairingScreen(
                    initialHost = pairingHost,
                    hasToken = JarvisRuntime.tokens.hasToken(),
                    busy = busy,
                    // Brought back by a refusal the stream reported, there may be
                    // no notice yet - so say why the screen appeared. The same
                    // for a saved address off the owner's own networks
                    // (OwnNetwork): it is never used, so the app opens here,
                    // and this sentence is the reason.
                    notice = notice ?: JarvisRuntime.settings.baseProblem()
                        ?: if (tokenRefused) badTokenNotice else null,
                    onPair = { host, token ->
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
                    },
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
                        val bargeInSaved by JarvisRuntime.settings.bargeIn.collectAsState()
                        val oneMomentOn by JarvisRuntime.settings.oneMoment.collectAsState()
                        val heardSoundOn by JarvisRuntime.settings.heardSound.collectAsState()
                        // Asked once: whether this phone has an echo canceller
                        // at all. It decides the barge-in default.
                        val echoCanceller = remember {
                            runCatching { AcousticEchoCanceler.isAvailable() }.getOrDefault(false)
                        }
                        var wakeBusy by remember { mutableStateOf(false) }
                        var wakeNotice by remember { mutableStateOf<String?>(null) }
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
                                    notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
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
                            wakeWordBusy = wakeBusy,
                            wakeWordNotice = wakeNotice,
                            onWakeWordOff = {
                                if (!wakeBusy) {
                                    wakeBusy = true
                                    wakeNotice = null
                                    // This phone first: off must never wait on
                                    // the network to close a microphone.
                                    WakeWordService.stop(this@MainActivity)
                                    lifecycleScope.launch {
                                        wakeNotice = voice.setWakeWord(false)
                                        wakeBusy = false
                                    }
                                }
                            },
                            // Raises the approval card; turns nothing on.
                            onWakeWordOn = {
                                if (!wakeBusy) {
                                    wakeBusy = true
                                    wakeNotice = null
                                    lifecycleScope.launch {
                                        wakeNotice = voice.setWakeWord(true)
                                        wakeBusy = false
                                    }
                                }
                            },
                            wakeWordPending = voiceStatus.listening.wakeWordPending,
                            phoneListening = phoneListening,
                            bargeIn = BargeIn.enabled(bargeInSaved, echoCanceller),
                            bargeInEchoCanceller = echoCanceller,
                            // A switch on this phone only: it changes when the
                            // phone listens, never what the desktop allows.
                            onBargeIn = { on -> JarvisRuntime.settings.setBargeIn(on) },
                            // Also this phone's own: whether "One moment." is
                            // played when a tool starts during a spoken question.
                            oneMoment = oneMomentOn,
                            onOneMoment = { on -> JarvisRuntime.settings.setOneMoment(on) },
                            // And whether the "I heard you" sound plays.
                            heardSound = heardSoundOn,
                            onHeardSound = { on -> JarvisRuntime.settings.setHeardSound(on) },
                            onPhoneListening = { on ->
                                if (on) {
                                    wakeNotice = startPhoneListening()
                                } else {
                                    WakeWordService.stop(this@MainActivity)
                                }
                            },
                            onRecheckWakeWord = {
                                if (!wakeBusy) {
                                    wakeBusy = true
                                    lifecycleScope.launch {
                                        voice.refreshStatus()
                                        wakeBusy = false
                                    }
                                }
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
                        modifier = root,
                    )

                    Screen.FAQ -> FaqScreen(
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
                        )
                    }

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
                            scope.launch { JarvisRuntime.pushAppearance() }
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
                        desktopSyncs = version?.can("appearance") == true,
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
                        // Still pictures, one per face, instead of name-only chips.
                        faceTile = { f, selected, onClick ->
                            FaceSpecimen(face = f, bindings = bindings, isSelected = selected, onClick = onClick)
                        },
                    )

                    Screen.HOME -> HomeScreen(
                        state = HomeState(
                            link = link,
                            linkDetail = linkDetail,
                            stale = stale,
                            activity = activity,
                            faceState = faceState,
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
                            lastUserText = lastQuestion,
                            answerFeedback = Feedback.viewFor(answerTurnId, answerMark),
                            conversationTurns = conversation.size,
                            chatWaiting = chatWaiting,
                            answerNote = answerNote,
                            quickNoteOpen = quickNoteOpen.value,
                            // The second card's Pictures feature, or the PC
                            // reading the words in a picture (2026-09-26), as
                            // the PC last reported it. The send asks again first.
                            pictureOffered = SecondCard.picturesTaken(secondCard),
                            pictureLine = picture.value?.let {
                                ChatPicture.attachedLine(it, wordsOnly = !SecondCard.visionAvailable(secondCard))
                            },
                            sharedLine = sharedHeld?.let { Provenance.sharedLine(it) },
                            pictureBusy = pictureBusy.value,
                            noteTargets = noteTargets,
                            updateLine = updateState.newerLine.takeIf { updateChecks },
                            temporary = temporaryChat,
                            usedIds = usedIds,
                            crisisAnswer = crisisAnswer,
                            memoryHidden = privateHidden,
                            showPrivateBusy = ownerCheckBusy.value,
                            noticeProblem = shownProblem,
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
                        actions = remember {
                            HomeActions(
                                onDraftChange = {
                                    draftPasted = Provenance.pastedAfter(draftPasted, draft, it)
                                    draft = it
                                },
                                onDropShared = { sharedHeld = null },
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
                                onInterrupt = { chat.cancel() },
                                onNewConversation = { chat.newConversation() },
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
                                onShowPrivate = ::showPrivateLists,
                                // A fingerprint instead of a tap for anything that
                                // leaves the machine, cannot be undone, or arrived
                                // with a rush latch on it. The phone is the surface
                                // most likely to be handed to someone or left
                                // unlocked, and this is the class of action where
                                // "whoever is holding it" and "the owner" need to
                                // be different answers.
                                onApprove = { item ->
                                    // The fingerprint prompt belongs to this
                                    // activity, so it stays on this scope; the
                                    // decision itself does not, and is handed to
                                    // the runtime the moment the prompt clears.
                                    // A rotation mid-request used to cancel the
                                    // coroutine after the POST had landed, drop
                                    // the result, and leave the card on screen
                                    // for a second tap to send again.
                                    scope.launch {
                                        if (confirmed(item)) {
                                            JarvisRuntime.decideDetached(item, approve = true)
                                        }
                                    }
                                },
                                // Denying is the safe direction and is never gated:
                                // a gate on refusing would make the cautious answer
                                // the slow one.
                                onDeny = { item -> JarvisRuntime.decideDetached(item, approve = false) },
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
