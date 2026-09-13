package com.jarvis.assistant

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.service.JarvisForegroundService
import com.jarvis.assistant.ui.capture.QuickCaptureSheet
import com.jarvis.assistant.ui.screens.HudActions
import com.jarvis.assistant.ui.screens.HudScreen
import com.jarvis.assistant.ui.screens.HudState
import com.jarvis.assistant.ui.theme.JarvisBlack
import com.jarvis.assistant.ui.theme.JarvisTheme

class MainActivity : ComponentActivity() {

    /** Bumped on every resume so permission-dependent UI re-reads its state. */
    private val resumeTick = mutableIntStateOf(0)
    private var startListeningOnResume = false

    private val captureOpen = mutableStateOf(false)
    private val captureSeed = mutableStateOf("")

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { _ ->
        resumeTick.intValue += 1
        JarvisForegroundService.start(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        JarvisRuntime.initialize(this)

        requestRuntimePermissions()
        JarvisForegroundService.start(this)
        handleIntent(intent)

        setContent {
            JarvisTheme {
                val connection by JarvisRuntime.socket.state.collectAsStateWithLifecycle()
                val lastError by JarvisRuntime.socket.lastError.collectAsStateWithLifecycle()
                val serverAddress by JarvisRuntime.settings.serverAddress.collectAsStateWithLifecycle()
                val micActive by JarvisRuntime.micActive.collectAsStateWithLifecycle()
                val desktop by JarvisRuntime.desktopTelemetry.collectAsStateWithLifecycle()
                val approvals by JarvisRuntime.pendingApprovals.collectAsStateWithLifecycle()
                val statusText by JarvisRuntime.statusText.collectAsStateWithLifecycle()
                val blockingError by JarvisRuntime.blockingError.collectAsStateWithLifecycle()
                val hasSecret by JarvisRuntime.settings.hasSharedSecret.collectAsStateWithLifecycle()
                val hasToken by JarvisRuntime.settings.hasAuthToken.collectAsStateWithLifecycle()

                val tick = resumeTick.intValue
                var micGranted by remember { mutableStateOf(JarvisRuntime.hasMicPermission()) }
                var batteryExempt by remember {
                    mutableStateOf(JarvisRuntime.telemetry.isIgnoringBatteryOptimizations())
                }
                LaunchedEffect(tick) {
                    micGranted = JarvisRuntime.hasMicPermission()
                    batteryExempt = JarvisRuntime.telemetry.isIgnoringBatteryOptimizations()
                    if (startListeningOnResume && micGranted) {
                        startListeningOnResume = false
                        JarvisRuntime.startMic()
                    }
                }

                if (captureOpen.value) {
                    val queued by JarvisRuntime.pendingNotes.pendingCount
                        .collectAsStateWithLifecycle()
                    QuickCaptureSheet(
                        connected = connection == ConnectionState.CONNECTED,
                        initialText = captureSeed.value,
                        micActive = micActive,
                        micPermissionGranted = micGranted,
                        queuedCount = queued,
                        onSend = { target, body ->
                            JarvisRuntime.sendQuickNote(target.wire, body)
                        },
                        onToggleMic = {
                            if (JarvisRuntime.hasMicPermission()) {
                                JarvisRuntime.toggleMic()
                            } else {
                                requestRuntimePermissions()
                            }
                        },
                        onDismiss = {
                            captureOpen.value = false
                            captureSeed.value = ""
                        },
                    )
                }

                HudScreen(
                    state = HudState(
                        connection = connection,
                        serverAddress = serverAddress,
                        micActive = micActive,
                        micPermissionGranted = micGranted,
                        desktop = desktop,
                        approvals = approvals,
                        statusText = statusText,
                        lastError = lastError,
                        batteryExempt = batteryExempt,
                        blockingError = blockingError,
                        hasSharedSecret = hasSecret,
                        hasAuthToken = hasToken,
                    ),
                    actions = HudActions(
                        onServerAddressChange = JarvisRuntime::updateServerAddress,
                        onReconnect = JarvisRuntime::reconnectNow,
                        onToggleMic = {
                            if (JarvisRuntime.hasMicPermission()) {
                                JarvisRuntime.toggleMic()
                            } else {
                                requestRuntimePermissions()
                            }
                        },
                        onApprove = { id -> JarvisRuntime.submitApprovalDecision(id, true) },
                        onReject = { id -> JarvisRuntime.submitApprovalDecision(id, false) },
                        onRequestBatteryExemption = ::requestBatteryExemption,
                        onSharedSecretChange = JarvisRuntime::updateSharedSecret,
                        onAuthTokenChange = JarvisRuntime::updateAuthToken,
                    ),
                    modifier = Modifier
                        .fillMaxSize()
                        .background(JarvisBlack)
                        .windowInsetsPadding(WindowInsets.systemBars),
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        resumeTick.intValue += 1
        JarvisRuntime.connect()
    }

    /**
     * ASSIST arrives from the power-button long-press, which means the user wants
     * to talk immediately rather than look at the HUD.
     */
    private fun handleIntent(intent: Intent?) {
        if (intent?.action == ACTION_QUICK_CAPTURE) {
            captureOpen.value = true
            return
        }
        // Share sheet: seed capture with whatever was shared.
        if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            captureSeed.value = intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty()
            captureOpen.value = true
            return
        }

        val wantsMic = intent?.action == Intent.ACTION_ASSIST ||
            intent?.action == ACTION_START_LISTENING ||
            intent?.action == "android.intent.action.VOICE_COMMAND"
        if (!wantsMic) return

        if (JarvisRuntime.hasMicPermission()) {
            JarvisRuntime.startMic()
        } else {
            startListeningOnResume = true
            requestRuntimePermissions()
        }
    }

    private fun requestRuntimePermissions() {
        val wanted = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            add(Manifest.permission.CAMERA)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        permissionLauncher.launch(wanted.toTypedArray())
    }

    private fun requestBatteryExemption() {
        // The direct request dialog is the good path; some OEM builds block the
        // intent entirely, so fall back to the settings list.
        val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        val fallback = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)

        runCatching { startActivity(direct) }
            .recoverCatching { startActivity(fallback) }
    }

    companion object {
        const val ACTION_START_LISTENING = "com.jarvis.assistant.START_LISTENING"
        const val ACTION_QUICK_CAPTURE = "com.jarvis.assistant.QUICK_CAPTURE"
    }
}
