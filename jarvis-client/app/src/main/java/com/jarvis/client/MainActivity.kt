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
import com.jarvis.client.face.Spec
import com.jarvis.client.net.ApiResult
import com.jarvis.client.platform.CrashLog
import com.jarvis.client.platform.DisplayRate
import com.jarvis.client.platform.PlatformReadiness
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
     * folded into the composer draft. Cleared the moment `App()` consumes it,
     * so the same share cannot be re-applied on a later recomposition.
     */
    private val sharedText = mutableStateOf<String?>(null)

    /** Set when the runtime itself failed to start. Shown instead of the app. */
    private val startupError = mutableStateOf<String?>(null)

    /** The previous run's crash, read once at launch. */
    private val lastCrash = mutableStateOf<String?>(null)

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
        readShareIntent(intent)

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
    }

    private fun readApprovalIntent(intent: Intent?) {
        if (intent?.action != ApprovalNotifier.ACTION_OPEN_APPROVAL) return
        focusApproval.value = intent.getStringExtra(ApprovalNotifier.EXTRA_APPROVAL_ID) ?: ""
    }

    /**
     * `singleTask`, so a second share while the app is already open re-delivers
     * here rather than starting a new instance - same reason [readApprovalIntent]
     * needs the `onNewIntent` half too.
     */
    private fun readShareIntent(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND || intent.type != "text/plain") return
        val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
        if (!text.isNullOrEmpty()) sharedText.value = text
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
        // Deliberately NOT saveable, unlike `paired` above.
        //
        // `busy` is cleared in exactly one place: the handshake coroutine
        // below, which runs in `rememberCoroutineScope()` and so dies with the
        // composition. A rotation mid-pair killed that coroutine while a saved
        // `busy = true` came back with the new one, and Connect stayed
        // disabled behind a spinner until a force-stop. The window is wide,
        // because `setToken` generates a hardware-backed key - hundreds of
        // milliseconds to seconds. The flag and the work that clears it now
        // have the same lifetime: if the work is gone, so is the flag.
        var busy by remember { mutableStateOf(false) }
        var draft by rememberSaveable { mutableStateOf("") }

        // A share from another app's share sheet arrives as an Intent extra,
        // not through the runtime, so it is folded into the draft here
        // rather than sent on its own — the owner still decides when and
        // whether to send it. Appended rather than replacing whatever was
        // already being typed, so a share never eats an in-progress message.
        LaunchedEffect(sharedText.value) {
            val text = sharedText.value ?: return@LaunchedEffect
            draft = if (draft.isBlank()) text else "$draft\n\n$text"
            sharedText.value = null
            nav.resetTo(Screen.HOME)
        }

        var memoryDecideBusyId by remember { mutableStateOf<Long?>(null) }
        // The daily "tidy memory overnight?" card, cached the first time it is
        // seen. See BrainScreen.kt's own doc comment on `sleepOffer`: the
        // server marks itself as having offered the moment the route is
        // polled at all, so a second read - which refreshBrain() triggers
        // after every OTHER memory write - would otherwise make the card
        // vanish before the owner had a chance to read it. `dismissed` is a
        // separate flag from clearing the cache, so a later recomposition
        // reading the same still-cached server data cannot re-adopt an offer
        // just turned down.
        //
        // `sleepOfferDismissed` is still rememberSaveable, like `paired`
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
        var sleepOfferDismissed by rememberSaveable { mutableStateOf(false) }
        /** A write is in flight - suppress re-adoption, but never across a rotation. */
        var sleepOfferAnswering by remember { mutableStateOf(false) }
        var sleepOfferBusy by remember { mutableStateOf(false) }

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
        val digest by JarvisRuntime.digest.collectAsState()
        val undo by JarvisRuntime.undo.collectAsState()
        val jobs by JarvisRuntime.jobs.collectAsState()
        val brain by JarvisRuntime.brain.collectAsState()
        val models by JarvisRuntime.models.collectAsState()
        val activityDetail by JarvisRuntime.activityDetail.collectAsState()
        var modelBusy by remember { mutableStateOf(false) }
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

        // The panel is asked for its fastest rate only while the face wants
        // every frame - listening, thinking, speaking, error. Idle draws at
        // 30 and standby and banked far below that, so a 120 Hz request held
        // through them was battery spent on frames nothing drew.
        LaunchedEffect(faceState) {
            DisplayRate.setHigh(this@MainActivity, window.peekDecorView(), Spec.fpsFor(faceState) == 0)
        }

        LaunchedEffect(brain.memory) {
            val offer = (brain.memory?.get("setup") as? JsonObject)
                ?.get("sleep_time_offer") as? JsonObject
            if (offer != null && cachedSleepOffer == null &&
                !sleepOfferDismissed && !sleepOfferAnswering
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
        LaunchedEffect(followSystem, systemDark, resting, chrome) {
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
        LaunchedEffect(focusApproval.value) {
            val id = focusApproval.value ?: return@LaunchedEffect
            nav.resetTo(Screen.HOME)
            JarvisRuntime.refreshPending()
            // Held long enough to scroll to and be noticed, then dropped. A
            // highlight that never cleared would also mean a second tap on the
            // SAME notification changed no key here, ran nothing, and scrolled
            // nowhere.
            delay(FOCUS_HOLD_MS)
            if (focusApproval.value == id) focusApproval.value = null
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
                    // `pending` is a key because the Notifications item reports
                    // how many approvals are currently going unannounced, and
                    // that number moves with the pending list. Without it the
                    // report would be cached from whenever the permission last
                    // changed and quietly go stale.
                    val items = remember(tick, host, pending) {
                        PlatformReadiness.report(
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
                                        // survive a rotation.
                                        sleepOfferDismissed = true
                                    } else {
                                        cachedSleepOffer = answered
                                    }
                                }
                            }
                        },
                        onDismissSleepOffer = {
                            cachedSleepOffer = null
                            sleepOfferDismissed = true
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

/**
 * How long a notification-focused approval stays marked on the home list.
 *
 * Long enough to land on, short enough that tapping the same notification
 * again re-runs the scroll rather than finding the id already set.
 */
private const val FOCUS_HOLD_MS = 8_000L
