package com.jarvis.client

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.jarvis.client.face.Faces
import com.jarvis.client.net.ApiResult
import com.jarvis.client.platform.CrashLog
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.net.PendingItem
import com.jarvis.client.service.ApprovalNotifier
import com.jarvis.client.service.EventService
import com.jarvis.client.ui.NavBackHandler
import com.jarvis.client.ui.Screen
import com.jarvis.client.ui.approval.BiometricGate
import com.jarvis.client.ui.rememberNavState
import com.jarvis.client.ui.screens.AppearanceScreen
import com.jarvis.client.ui.screens.BrainScreen
import com.jarvis.client.ui.screens.CrashScreen
import com.jarvis.client.ui.screens.FaqScreen
import com.jarvis.client.ui.screens.HomeActions
import com.jarvis.client.ui.screens.HomeScreen
import com.jarvis.client.ui.screens.HomeState
import com.jarvis.client.ui.screens.InboxScreen
import com.jarvis.client.ui.screens.PairingScreen
import com.jarvis.client.ui.screens.ReadinessScreen
import com.jarvis.client.ui.theme.JarvisTheme
import com.jarvis.client.ui.theme.Themes
import com.jarvis.client.ui.theme.systemPrefersDark
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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

    /** Set when the runtime itself failed to start. Shown instead of the app. */
    private val startupError = mutableStateOf<String?>(null)

    /** The previous run's crash, read once at launch. */
    private val lastCrash = mutableStateOf<String?>(null)

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { permissionTick.intValue += 1 }

    /**
     * Asked the first time the microphone button is held, never at launch.
     *
     * A permission dialog on first run, before the app has shown what it is
     * for, is the one most people refuse — and the refusal is sticky. Granting
     * it starts the capture immediately, so the hold that asked is the hold
     * that records.
     */
    private var micGrantedCallback: (() -> Unit)? = null

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        permissionTick.intValue += 1
        if (granted) micGrantedCallback?.invoke()
        micGrantedCallback = null
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
    }

    private fun readApprovalIntent(intent: Intent?) {
        if (intent?.action != ApprovalNotifier.ACTION_OPEN_APPROVAL) return
        focusApproval.value = intent.getStringExtra(ApprovalNotifier.EXTRA_APPROVAL_ID) ?: ""
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
            )
            return
        }
        if (!JarvisRuntime.isInitialized) {
            CrashScreen(
                title = "Jarvis could not start",
                detail = "The runtime reported that it never initialised, and did not say why.",
                onDismiss = { finish() },
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
        var busy by rememberSaveable { mutableStateOf(false) }
        var draft by rememberSaveable { mutableStateOf("") }
        var memoryDecideBusyId by remember { mutableStateOf<Long?>(null) }

        val tick = permissionTick.intValue
        val chrome by appearance.chrome.collectAsState()
        val followSystem by appearance.followSystem.collectAsState()
        val faceId by appearance.faceId.collectAsState()
        val bindings by appearance.bindings.collectAsState()

        val link by JarvisRuntime.link.collectAsState()
        val linkDetail by JarvisRuntime.linkDetail.collectAsState()
        val stale by JarvisRuntime.stale.collectAsState()
        val activity by JarvisRuntime.activity.collectAsState()
        val faceState by JarvisRuntime.face.collectAsState()
        val power by JarvisRuntime.power.collectAsState()
        val status by JarvisRuntime.status.collectAsState()
        val version by JarvisRuntime.version.collectAsState()
        val pending by JarvisRuntime.pending.collectAsState()
        val attention by JarvisRuntime.attention.collectAsState()
        val notice by JarvisRuntime.notice.collectAsState()
        val digest by JarvisRuntime.digest.collectAsState()
        val undo by JarvisRuntime.undo.collectAsState()
        val jobs by JarvisRuntime.jobs.collectAsState()
        val brain by JarvisRuntime.brain.collectAsState()
        val absent by JarvisRuntime.absent.collectAsState()
        val streaming by chat.streaming.collectAsState()
        val voicePhase by voice.phase.collectAsState()
        val voiceStatus by voice.status.collectAsState()
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

        val face = remember(faceId) { Faces.byId(faceId) }
        val idleColour = bindings.of(FaceState.IDLE).tint ?: com.jarvis.client.face.Palette.ICE_3

        // A chat failure used to be written to a StateFlow that nothing
        // collected, so a send that failed looked exactly like a send that was
        // still thinking — for ever.
        LaunchedEffect(chat) {
            chat.error.collectLatest { if (it != null) JarvisRuntime.setNotice(it) }
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
        LaunchedEffect(followSystem, systemDark, resting) {
            if (!followSystem || !resting) return@LaunchedEffect
            val want = Themes.forSystem(systemDark, preferredDark = Themes.byId(lastDarkId(chrome.id)))
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

        // A notification tap goes straight home, so the card is where the
        // finger already is.
        LaunchedEffect(focusApproval.value) {
            if (focusApproval.value == null) return@LaunchedEffect
            nav.resetTo(Screen.HOME)
            JarvisRuntime.refreshPending()
            focusApproval.value = null
        }

        JarvisTheme(chrome = chrome, idleColor = idleColour) {
            val root = Modifier
                .fillMaxSize()
                .background(chrome.surface0)
                .windowInsetsPadding(WindowInsets.systemBars)

            // Pairing outranks the stack: there is nothing to show until there
            // is somewhere to talk to. The checks screen is the exception,
            // because "why can I not connect" has to be answerable from here.
            if (!paired && nav.current != Screen.CHECKS) {
                PairingScreen(
                    initialHost = JarvisRuntime.settings.host.value,
                    hasToken = JarvisRuntime.tokens.hasToken(),
                    busy = busy,
                    notice = notice,
                    onPair = { host, token ->
                        busy = true
                        scope.launch {
                            // Off the main thread. `setToken` generates a
                            // hardware-backed AES key on first pair, which is a
                            // TEE/StrongBox round trip — several hundred
                            // milliseconds to a couple of seconds, blocking the
                            // UI so hard that the button could not even repaint
                            // into its own busy state, and an ANR candidate on a
                            // slow device.
                            withContext(Dispatchers.IO) {
                                JarvisRuntime.settings.setHost(host)
                                if (token.isNotBlank()) JarvisRuntime.tokens.setToken(token)
                            }
                            val result = JarvisRuntime.handshake()
                            busy = false
                            if (result is ApiResult.Ok) {
                                paired = true
                                // The stream lives in the service, not here: a
                                // backgrounded activity's connection is
                                // suspended within about a minute, which is
                                // exactly how approvals silently stop arriving.
                                EventService.start(this@MainActivity)
                            }
                        }
                    },
                    onOpenReadiness = { nav.go(Screen.CHECKS) },
                    modifier = root,
                )
                return@JarvisTheme
            }

            when (nav.current) {
                Screen.CHECKS -> {
                    val host by JarvisRuntime.settings.host.collectAsState()
                    val items = remember(tick, host) {
                        com.jarvis.client.platform.PlatformReadiness.report(
                            this@MainActivity,
                            host,
                        )
                    }
                    val wakeWord by voice.wakeWord.collectAsState()
                    var wakeBusy by remember { mutableStateOf(false) }
                    var wakeNotice by remember { mutableStateOf<String?>(null) }
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
                        wakeWord = wakeWord,
                        wakeWordBusy = wakeBusy,
                        wakeWordNotice = wakeNotice,
                        onWakeWordOff = {
                            if (!wakeBusy) {
                                wakeBusy = true
                                wakeNotice = null
                                lifecycleScope.launch {
                                    wakeNotice = voice.setWakeWord(false)
                                    wakeBusy = false
                                }
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
                        onMarkSeen = { scope.launch { JarvisRuntime.markDigestSeen() } },
                        onSetMuted = { m -> scope.launch { JarvisRuntime.setMuted(m) } },
                        onBack = { nav.back() },
                        modifier = root,
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
                        notice = notice,
                        onDismissNotice = { JarvisRuntime.clearNotice() },
                        modifier = root,
                    )
                }

                Screen.FAQ -> FaqScreen(
                    onBack = { nav.back() },
                    modifier = root,
                )

                Screen.APPEARANCE -> AppearanceScreen(
                    current = chrome,
                    followSystem = followSystem,
                    face = face,
                    bindings = bindings,
                    onPickTheme = {
                        if (!appearance.setTheme(it)) {
                            JarvisRuntime.setNotice("One theme change at a time — give it a moment.")
                        }
                    },
                    onFollowSystem = appearance::setFollowSystem,
                    onPickFace = { appearance.setFace(it.id) },
                    onRandomise = { appearance.randomise() },
                    onResetBindings = { appearance.resetBindings() },
                    onBack = { nav.back() },
                    notice = notice,
                    onDismissNotice = { JarvisRuntime.clearNotice() },
                    modifier = root,
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
                        draft = draft,
                        face = face,
                        bindings = bindings,
                        voicePhase = voicePhase,
                        voiceOffered = voiceStatus.canPushToTalk,
                        transcript = transcript,
                        voiceNotice = voiceNotice,
                        approvalsOff = "approvals" in absent,
                    ),
                    // A lambda, so a streamed token redraws the reply and
                    // nothing else. Passing the string rebuilt HomeState on
                    // every chunk and recomposed the bar, the list and the
                    // composer while the face drew at 60fps on the same thread.
                    reply = { replyState.value },
                    micLevel = micLevel,
                    speechLevel = speechLevel,
                    actions = remember {
                        HomeActions(
                            onDraftChange = { draft = it },
                            onSend = {
                                val text = draft
                                draft = ""
                                scope.launch { chat.send(text) }
                            },
                            onInterrupt = { chat.cancel() },
                            // A fingerprint instead of a tap for anything that
                            // leaves the machine, cannot be undone, or arrived
                            // with a rush latch on it. The phone is the surface
                            // most likely to be handed to someone or left
                            // unlocked, and this is the class of action where
                            // "whoever is holding it" and "the owner" need to
                            // be different answers.
                            onApprove = { item ->
                                scope.launch {
                                    if (confirmed(item)) {
                                        JarvisRuntime.decide(item, approve = true)
                                    }
                                }
                            },
                            // Denying is the safe direction and is never gated:
                            // a gate on refusing would make the cautious answer
                            // the slow one.
                            onDeny = { item ->
                                scope.launch { JarvisRuntime.decide(item, approve = false) }
                            },
                            onReconnect = {
                                EventService.start(this@MainActivity)
                                scope.launch { JarvisRuntime.refreshAll() }
                            },
                            onDismissNotice = { JarvisRuntime.clearNotice() },
                            onOpenChecks = { nav.go(Screen.CHECKS) },
                            onOpenInbox = { nav.go(Screen.INBOX) },
                            onOpenBrain = { nav.go(Screen.BRAIN) },
                            onOpenAppearance = { nav.go(Screen.APPEARANCE) },
                            onOpenFaq = { nav.go(Screen.FAQ) },
                            blockerFor = { item: PendingItem ->
                                JarvisRuntime.decisionBlocker(item)
                            },
                            onVoiceBegin = ::beginVoice,
                            onVoiceRelease = { JarvisRuntime.voice.release() },
                            onVoiceCancel = { JarvisRuntime.voice.cancel() },
                            onDismissVoiceNotice = { JarvisRuntime.voice.clearNotice() },
                        )
                    },
                    modifier = root,
                )
            }
        }
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

    /** The dark theme to come back to when the system leaves light mode. */
    private fun lastDarkId(currentId: String): String =
        if (currentId == Themes.DAYLIGHT.id) Themes.REACTOR.id else currentId

    /**
     * @return true when the decision may proceed.
     *
     * An unavailable biometric is not a refusal: declining to let the owner
     * answer their own desktop because no fingerprint is enrolled would be a
     * lock on the wrong door, and the pairing token already authorises the
     * request. A *dismissed* prompt is a refusal, and nothing is sent.
     */
    private suspend fun confirmed(item: PendingItem): Boolean {
        if (!BiometricGate.required(item)) return true
        return when (BiometricGate.confirm(this, item)) {
            BiometricGate.Outcome.CONFIRMED -> true
            BiometricGate.Outcome.UNAVAILABLE -> true
            BiometricGate.Outcome.CANCELLED -> false
        }
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
}

/** How long to wait before re-offering a theme the dwell window refused. */
private const val THEME_RETRY_MS = 600L
