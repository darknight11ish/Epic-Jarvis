package com.jarvis.assistant

import android.app.Application
import android.content.Context
import android.util.Base64
import android.util.Log
import com.jarvis.assistant.audio.AudioPlayer
import com.jarvis.assistant.audio.AudioStreamer
import com.jarvis.assistant.data.JarvisSettings
import com.jarvis.assistant.data.PendingNoteStore
import com.jarvis.assistant.network.ApprovalDecisionMessage
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.ApprovalResolvedEvent
import com.jarvis.assistant.network.AudioChunkEvent
import com.jarvis.assistant.network.AudioInputEndMessage
import com.jarvis.assistant.network.AudioInputStartMessage
import com.jarvis.assistant.network.AudioStreamEndEvent
import com.jarvis.assistant.network.AudioStreamStartEvent
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.network.DesktopTelemetryEvent
import com.jarvis.assistant.network.DeviceCommandEvent
import com.jarvis.assistant.network.DeviceCommandResultMessage
import com.jarvis.assistant.network.HelloMessage
import com.jarvis.assistant.network.InterruptMessage
import com.jarvis.assistant.network.JarvisWebSocketManager
import com.jarvis.assistant.network.OutboundMessage
import com.jarvis.assistant.network.QuickNoteMessage
import com.jarvis.assistant.network.StatusEvent
import com.jarvis.assistant.network.TelemetryRequestEvent
import com.jarvis.assistant.network.TelemetrySnapshotMessage
import com.jarvis.assistant.notifications.ApprovalNotificationManager
import com.jarvis.assistant.notifications.ApprovalSigner
import com.jarvis.assistant.telemetry.CommandOutcome
import com.jarvis.assistant.telemetry.DeviceTelemetryProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.jsonPrimitive
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue

class JarvisApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
    }
}

/**
 * Process-wide hub shared by the HUD, the foreground service, the assistant
 * session and the lock-screen BroadcastReceiver.
 *
 * A singleton rather than injected graph because every one of those entry points
 * can be the one that cold-starts the process, and they all need the same live
 * socket rather than four of them.
 */
object JarvisRuntime {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    @Volatile private var started = false

    lateinit var settings: JarvisSettings
        private set
    lateinit var telemetry: DeviceTelemetryProvider
        private set
    lateinit var approvals: ApprovalNotificationManager
        private set
    lateinit var player: AudioPlayer
        private set
    lateinit var pendingNotes: PendingNoteStore
        private set

    private lateinit var appContext: Context
    private lateinit var streamer: AudioStreamer

    val socket: JarvisWebSocketManager = JarvisWebSocketManager.get()

    private val _pendingApprovals = MutableStateFlow<List<ApprovalRequestEvent>>(emptyList())
    val pendingApprovals: StateFlow<List<ApprovalRequestEvent>> = _pendingApprovals.asStateFlow()

    private val _desktopTelemetry = MutableStateFlow<DesktopTelemetryEvent?>(null)
    val desktopTelemetry: StateFlow<DesktopTelemetryEvent?> = _desktopTelemetry.asStateFlow()

    private val _statusText = MutableStateFlow<String?>(null)
    val statusText: StateFlow<String?> = _statusText.asStateFlow()

    private val _micActive = MutableStateFlow(false)
    val micActive: StateFlow<Boolean> = _micActive.asStateFlow()

    /** Non-null when a decision could not be signed or the target was refused. */
    private val _blockingError = MutableStateFlow<String?>(null)
    val blockingError: StateFlow<String?> = _blockingError.asStateFlow()

    /** Decisions taken while the socket was down, replayed on reconnect. */
    private val outbox = ConcurrentLinkedQueue<OutboundMessage>()

    @Volatile private var micStreamId: String? = null
    @Volatile private var expectingWavHeader = false
    @Volatile private var downlinkTag: Int? = null

    @Synchronized
    fun initialize(context: Context) {
        if (started) return
        appContext = context.applicationContext
        settings = JarvisSettings(appContext)
        telemetry = DeviceTelemetryProvider(appContext)
        approvals = ApprovalNotificationManager(appContext)
        pendingNotes = PendingNoteStore(appContext)
        player = AudioPlayer()
        streamer = AudioStreamer(appContext) { buffer, length ->
            socket.sendAudio(buffer, length)
        }
        started = true

        scope.launch { socket.events.collect(::handleEvent) }
        scope.launch { socket.binaryAudio.collect(::handleBinaryAudio) }
        scope.launch {
            socket.state.collect { state ->
                if (state == ConnectionState.CONNECTED) onConnected()
            }
        }

        connect()
    }

    /**
     * Refuses to dial an unencrypted target outside the Tailnet or a private LAN,
     * so a mistyped address cannot put approvals and voice on the open internet.
     */
    fun connect() {
        val url = settings.resolveWebSocketUrl()
        if (!JarvisSettings.isCleartextTargetPrivate(url)) {
            _blockingError.value =
                "Refusing plaintext ws:// to a public host. Use a Tailscale address or wss://."
            socket.disconnect()
            return
        }
        if (_blockingError.value?.startsWith("Refusing plaintext") == true) {
            _blockingError.value = null
        }
        socket.connect(url, settings.authToken)
    }

    fun updateServerAddress(address: String) {
        settings.setServerAddress(address)
        connect()
    }

    fun updateSharedSecret(secret: String) {
        settings.sharedSecret = secret
        if (secret.isNotEmpty()) _blockingError.value = null
    }

    fun updateAuthToken(token: String) {
        settings.authToken = token
        reconnectNow()
    }

    /** User-driven "try again now", bypassing the remaining backoff delay. */
    fun reconnectNow() {
        if (::settings.isInitialized) {
            connect()
            socket.reconnectNow()
        }
    }

    private fun onConnected() {
        socket.send(
            HelloMessage(
                deviceId = settings.deviceId,
                appVersion = BuildConfig.VERSION_NAME,
            ),
        )
        while (true) {
            val queued = outbox.peek() ?: break
            if (!socket.send(queued)) break
            outbox.poll()
        }

        flushPendingNotes()
    }

    /**
     * Replays notes captured while offline, oldest first so the journal keeps
     * the order they were written in. Each is removed only once the socket has
     * actually taken it.
     */
    private fun flushPendingNotes() {
        for (note in pendingNotes.snapshot()) {
            if (!socket.send(note)) return
            pendingNotes.remove(note)
        }
    }

    /**
     * Capture never fails in front of the user: an unsendable note goes to disk
     * and is replayed on reconnect.
     *
     * @return true when it went straight out over the socket.
     */
    fun sendQuickNote(target: String, content: String, mode: String? = null): Boolean {
        val trimmed = content.trim()
        if (trimmed.isEmpty()) return false

        val note = QuickNoteMessage(
            target = target,
            // A journal is a running log, a vault note is a document.
            mode = mode ?: if (target == QuickNoteMessage.TARGET_LOGSEQ) {
                QuickNoteMessage.MODE_APPEND
            } else {
                QuickNoteMessage.MODE_CREATE
            },
            content = trimmed,
            timestampMs = System.currentTimeMillis(),
        )

        if (socket.send(note)) {
            telemetry.vibrate("confirm")
            return true
        }
        pendingNotes.add(note)
        telemetry.vibrate("tick")
        connect()
        return false
    }

    // --------------------------------------------------------- inbound ----

    private fun handleEvent(event: com.jarvis.assistant.network.InboundEvent) {
        when (event) {
            is ApprovalRequestEvent -> {
                _pendingApprovals.value = _pendingApprovals.value
                    .filterNot { it.id == event.id } + event
                approvals.post(event)
                telemetry.vibrate("alert")
            }

            is ApprovalResolvedEvent -> clearApproval(event.id)

            is AudioStreamStartEvent -> {
                expectingWavHeader = event.encoding.equals("wav", ignoreCase = true)
                downlinkTag = event.binaryTag
                player.start(event.sampleRate, event.channels)
            }

            is AudioChunkEvent -> {
                val decoded = runCatching { Base64.decode(event.data, Base64.DEFAULT) }.getOrNull()
                if (decoded == null) {
                    Log.w(TAG, "undecodable audio chunk seq=${event.seq}")
                    return
                }
                player.enqueue(stripWavHeaderIfPresent(decoded))
            }

            is AudioStreamEndEvent -> {
                expectingWavHeader = false
                downlinkTag = null
                player.finish()
            }

            is DeviceCommandEvent -> executeDeviceCommand(event)

            is TelemetryRequestEvent -> sendOrQueue(
                TelemetrySnapshotMessage(event.id, telemetry.collectTelemetrySnapshot()),
            )

            is DesktopTelemetryEvent -> _desktopTelemetry.value = event

            is StatusEvent -> _statusText.value = event.text
        }
    }

    /**
     * Binary downlink: `[tag][pcm…]`, where the tag was announced by the
     * audio_stream_start that opened the stream. Frames for any other tag belong
     * to a stream that has already ended and are dropped.
     */
    private fun handleBinaryAudio(frame: ByteArray) {
        val expected = downlinkTag ?: return
        if (frame.isEmpty()) return
        if ((frame[0].toInt() and 0xFF) != expected) return
        if (frame.size <= 1) return
        player.enqueue(stripWavHeaderIfPresent(frame.copyOfRange(1, frame.size)))
    }

    /** WAV downlinks carry a 44-byte RIFF header the AudioTrack must not play. */
    private fun stripWavHeaderIfPresent(chunk: ByteArray): ByteArray {
        if (!expectingWavHeader) return chunk
        expectingWavHeader = false
        val isRiff = chunk.size > WAV_HEADER_BYTES &&
            chunk[0] == 'R'.code.toByte() && chunk[1] == 'I'.code.toByte() &&
            chunk[2] == 'F'.code.toByte() && chunk[3] == 'F'.code.toByte()
        return if (isRiff) chunk.copyOfRange(WAV_HEADER_BYTES, chunk.size) else chunk
    }

    private fun executeDeviceCommand(event: DeviceCommandEvent) {
        fun param(name: String): String? =
            runCatching { event.params[name]?.jsonPrimitive?.content }.getOrNull()

        val outcome: CommandOutcome = when (event.action) {
            "torch_on" -> telemetry.setTorch(true)
            "torch_off" -> telemetry.setTorch(false)
            "torch_toggle" -> telemetry.toggleTorch()
            "set_volume" -> {
                val percent = param("percent")?.toIntOrNull()
                if (percent == null) {
                    CommandOutcome(false, "set_volume requires a numeric 'percent'")
                } else {
                    telemetry.setMediaVolumePercent(percent)
                }
            }
            "vibrate" -> telemetry.vibrate(param("pattern") ?: "tick")
            "interrupt_audio" -> {
                player.flushNow()
                CommandOutcome(true, "playback flushed")
            }
            "telemetry" -> {
                sendOrQueue(TelemetrySnapshotMessage(event.id, telemetry.collectTelemetrySnapshot()))
                CommandOutcome(true, "snapshot sent")
            }
            else -> {
                DeviceTelemetryProvider.logUnsupported(event.action)
                CommandOutcome(false, "unknown action '${event.action}'")
            }
        }

        sendOrQueue(DeviceCommandResultMessage(event.id, outcome.ok, outcome.detail))
    }

    // -------------------------------------------------------- outbound ----

    private fun sendOrQueue(message: OutboundMessage) {
        if (!socket.send(message)) {
            outbox.add(message)
            connect()
        }
    }

    /**
     * An unsigned decision is never sent. The request stays in the pending list
     * and the HUD says why, rather than the desktop acting on an approval this
     * handset cannot prove it authorised.
     */
    fun submitApprovalDecision(requestId: String, approved: Boolean) {
        val now = System.currentTimeMillis()
        val nonce = UUID.randomUUID().toString()
        val signature = ApprovalSigner.sign(
            secret = settings.sharedSecret,
            id = requestId,
            approved = approved,
            deviceId = settings.deviceId,
            atMs = now,
            nonce = nonce,
        )

        if (signature == null) {
            _blockingError.value =
                "No pairing secret set, so this decision cannot be signed. Set one below."
            telemetry.vibrate("alert")
            return
        }

        sendOrQueue(
            ApprovalDecisionMessage(
                id = requestId,
                approved = approved,
                deviceId = settings.deviceId,
                decidedAtMs = now,
                nonce = nonce,
                signature = signature,
            ),
        )
        clearApproval(requestId)
        telemetry.vibrate(if (approved) "confirm" else "tick")
    }

    private fun clearApproval(requestId: String) {
        _pendingApprovals.value = _pendingApprovals.value.filterNot { it.id == requestId }
        approvals.cancel(requestId)
    }

    // ------------------------------------------------------------- mic ----

    fun hasMicPermission(): Boolean = streamer.hasPermission()

    /**
     * Barge-in is part of starting the mic: whatever the desktop is currently
     * speaking is cut locally and remotely before the first uplink byte.
     */
    fun startMic(): Boolean {
        if (_micActive.value) return true
        bargeIn()

        val streamId = UUID.randomUUID().toString()
        micStreamId = streamId
        sendOrQueue(
            AudioInputStartMessage(
                streamId = streamId,
                sampleRate = AudioStreamer.SAMPLE_RATE,
            ),
        )
        val ok = streamer.start()
        if (!ok) {
            micStreamId = null
            sendOrQueue(AudioInputEndMessage(streamId))
            return false
        }
        _micActive.value = true
        return true
    }

    fun stopMic() {
        if (!_micActive.value) return
        streamer.stop()
        _micActive.value = false
        micStreamId?.let { sendOrQueue(AudioInputEndMessage(it)) }
        micStreamId = null
    }

    fun toggleMic(): Boolean = if (_micActive.value) {
        stopMic()
        false
    } else {
        startMic()
    }

    fun bargeIn() {
        player.flushNow()
        socket.send(InterruptMessage())
    }

    fun shutdown() {
        stopMic()
        player.release()
        socket.disconnect()
    }

    private const val TAG = "JarvisRuntime"
    private const val WAV_HEADER_BYTES = 44
}
