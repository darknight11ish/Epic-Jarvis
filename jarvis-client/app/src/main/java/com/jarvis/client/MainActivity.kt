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
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.ChatSession
import com.jarvis.client.net.PendingItem
import com.jarvis.client.service.EventService
import com.jarvis.client.ui.T
import com.jarvis.client.ui.approval.BiometricGate
import com.jarvis.client.ui.screens.InboxScreen
import com.jarvis.client.ui.screens.HomeActions
import com.jarvis.client.ui.screens.HomeScreen
import com.jarvis.client.ui.screens.HomeState
import com.jarvis.client.ui.screens.PairingScreen
import com.jarvis.client.ui.screens.ReadinessScreen
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/**
 * The one activity.
 *
 * Three destinations and no navigation library: pairing until there is a host
 * and a token, the readiness checks on demand, and home. A nav graph for three
 * screens with no deep links would be more machinery than routing.
 */
/**
 * FragmentActivity rather than ComponentActivity, for exactly one reason:
 * `BiometricPrompt` takes a FragmentActivity or a Fragment and nothing else —
 * it needs a fragment manager to survive a configuration change while the
 * system prompt is on screen. FragmentActivity *is* a ComponentActivity, so
 * `setContent`, `enableEdgeToEdge` and `registerForActivityResult` are
 * unaffected.
 */
class MainActivity : FragmentActivity() {

    private val permissionTick = mutableIntStateOf(0)

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { permissionTick.intValue += 1 }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        JarvisRuntime.initialize(this)

        setContent {
            val scope = rememberCoroutineScope()
            val chat = remember { ChatSession(JarvisRuntime.api) }

            var showReadiness by rememberSaveable { mutableStateOf(false) }
            var showInbox by rememberSaveable { mutableStateOf(false) }
            var paired by remember { mutableStateOf(JarvisRuntime.isPaired()) }
            var busy by remember { mutableStateOf(false) }
            var draft by rememberSaveable { mutableStateOf("") }

            val tick = permissionTick.intValue
            val link by JarvisRuntime.link.collectAsState()
            val linkDetail by JarvisRuntime.linkDetail.collectAsState()
            val stale by JarvisRuntime.stale.collectAsState()
            val activity by JarvisRuntime.activity.collectAsState()
            val power by JarvisRuntime.power.collectAsState()
            val pending by JarvisRuntime.pending.collectAsState()
            val attention by JarvisRuntime.attention.collectAsState()
            val notice by JarvisRuntime.notice.collectAsState()
            val reply by chat.reply.collectAsState()
            val streaming by chat.streaming.collectAsState()
            val digest by JarvisRuntime.digest.collectAsState()
            val undo by JarvisRuntime.undo.collectAsState()
            val jobs by JarvisRuntime.jobs.collectAsState()

            val root = Modifier
                .fillMaxSize()
                .background(T.Void)
                .windowInsetsPadding(WindowInsets.systemBars)

            when {
                showInbox -> {
                    LaunchedEffect(Unit) { JarvisRuntime.refreshInbox() }
                    InboxScreen(
                        attention = attention,
                        digest = digest,
                        undo = undo,
                        jobs = jobs,
                        onOpenApproval = {
                            // The brief cannot decide an approval. Tapping a row
                            // leaves the digest and opens the normal gate card.
                            showInbox = false
                            scope.launch { JarvisRuntime.refreshPending() }
                        },
                        onRevert = { scope.launch { JarvisRuntime.revert(it) } },
                        onCancelJob = { scope.launch { JarvisRuntime.cancelJob(it) } },
                        onMarkSeen = { scope.launch { JarvisRuntime.markDigestSeen() } },
                        onSetMuted = { m -> scope.launch { JarvisRuntime.setMuted(m) } },
                        onBack = { showInbox = false },
                        modifier = root,
                    )
                }

                showReadiness -> {
                    val host by JarvisRuntime.settings.host.collectAsState()
                    val items = remember(tick, host) {
                        com.jarvis.client.platform.PlatformReadiness.report(
                            this@MainActivity,
                            host,
                        )
                    }
                    ReadinessScreen(
                        items = items,
                        onRequestNotifications = {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                            }
                        },
                        onRequestBatteryExemption = ::requestBatteryExemption,
                        onStartService = { EventService.start(this@MainActivity) },
                        onBack = { showReadiness = false },
                        modifier = root,
                    )
                }

                !paired -> PairingScreen(
                    initialHost = JarvisRuntime.settings.host.value,
                    hasToken = JarvisRuntime.tokens.hasToken(),
                    busy = busy,
                    notice = notice,
                    onPair = { host, token ->
                        busy = true
                        JarvisRuntime.settings.setHost(host)
                        if (token.isNotBlank()) JarvisRuntime.tokens.setToken(token)
                        scope.launch {
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
                    onOpenReadiness = { showReadiness = true },
                    modifier = root,
                )

                else -> HomeScreen(
                    state = HomeState(
                        link = link,
                        linkDetail = linkDetail,
                        stale = stale,
                        activity = activity,
                        faceState = JarvisRuntime.faceState(),
                        power = power,
                        pending = pending,
                        attention = attention,
                        notice = notice,
                        reply = reply,
                        streaming = streaming,
                        draft = draft,
                    ),
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
                            onOpenReadiness = { showReadiness = true },
                            onOpenInbox = { showInbox = true },
                            blockerFor = { item: PendingItem ->
                                JarvisRuntime.decisionBlocker(item)
                            },
                        )
                    },
                    modifier = root,
                )
            }
        }
    }

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
