package com.jarvis.assistant

import android.app.Application
import android.content.Context
import android.util.Base64
import android.util.Log
import com.jarvis.assistant.audio.AudioPlayer
import com.jarvis.assistant.audio.AudioStreamer
import com.jarvis.assistant.data.JarvisSettings
import com.jarvis.assistant.data.PendingDecisionStore
import com.jarvis.assistant.data.PendingNoteStore
import com.jarvis.assistant.data.repository.WidgetDataRepository
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
import com.jarvis.assistant.network.PingMessage
import com.jarvis.assistant.network.PongEvent
import com.jarvis.assistant.network.QuickNoteMessage
import com.jarvis.assistant.network.SocketSignal
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
import java.util.concurrent.atomic.AtomicBoolean

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
    lateinit var pendingDecisions: PendingDecisionStore
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

    /** Last measured round trip to the desktop, or null before the first pong. */
    private val _latencyMs = MutableStateFlow<Long?>(null)
    val latencyMs: StateFlow<Long?> = _latencyMs.asStateFlow()

    /** Lets widgets read state without booting the socket from a cold process. */
    val isInitialized: Boolean get() = started

    /**
     * Messages that could not go out immediately, replayed on reconnect.
     *
     * Bounded, and audio control messages are dropped rather than queued: replaying
     * `audio_input_start`/`audio_input_end` pairs for streams that ended minutes ago
     * tells the desktop about microphone sessions that no longer exist, and there is
     * no PCM to go with them. Approval decisions do not live here at all — they are
     * persisted, because this queue dies with the process.
     */
    private val outbox = ConcurrentLinkedQueue<OutboundMessage>()

    /**
     * Guards the mic start/stop transition. `_micActive` alone is check-then-act:
     * the assistant flow on the main thread and a bound SpeechRecognizer on a binder
     * thread can both read false, both mint a stream id and both send an
     * `audio_input_start`, and only one of them is ever ended.
     */
    private val micTransition = AtomicBoolean(false)

    /**
     * Set by the foreground service. Promotes the service to the `microphone`
     * foreground type and reports whether the platform allowed it.
     *
     * The promotion has to happen *before* AudioRecord.startRecording(): the audio
     * policy decides mic eligibility at that call, so opening the mic first and
     * promoting afterwards yields zeroed frames. And a refusal has to stop the
     * capture rather than be logged — otherwise the notification reads "Listening"
     * while the desktop receives silence.
     */
    @Volatile var micForegroundPromoter: ((Boolean) -> Boolean)? = null

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
        pendingDecisions = PendingDecisionStore(appContext)
        player = AudioPlayer()
        streamer = AudioStreamer(appContext) { buffer, length ->
            socket.sendAudio(buffer, length)
        }
        started = true

        // One ordered collector over both transports. Text and binary used to be
        // collected independently, which loses the ordering between a stream's PCM
        // frames and its own start/end events.
        scope.launch {
            socket.incoming.collect { signal ->
                when (signal) {
                    is SocketSignal.Event -> handleEvent(signal.event)
                    is SocketSignal.Binary -> handleBinaryAudio(signal.frame)
                }
            }
        }
        scope.launch {
            socket.state.collect { state ->
                if (state == ConnectionState.CONNECTED) onConnected()
            }
        }

        WidgetDataRepository.observe(appContext, scope)

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

        flushPendingDecisions()
        flushPendingNotes()
        measureLatency()
    }

    /**
     * Replays decisions that were signed but never reached the desktop. Each row is
     * removed only once the socket has taken it, and the signature already covers
     * the nonce and timestamp, so a replay cannot alter what was agreed to.
     */
    private fun flushPendingDecisions() {
        for (decision in pendingDecisions.snapshot()) {
            if (!socket.send(decision)) return
            pendingDecisions.remove(decision)
        }
    }

    /** Fire-and-forget probe; the reply updates [latencyMs] when it lands. */
    fun measureLatency() {
        if (!started) return
        socket.send(PingMessage(System.currentTimeMillis()))
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

            // Off the collector: collectTelemetrySnapshot does three binder round
            // trips and enumerates cameras. Doing it inline stalls the one consumer
            // of the socket for long enough to matter during a reply.
            is TelemetryRequestEvent -> scope.launch {
                sendOrQueue(
                    TelemetrySnapshotMessage(event.id, telemetry.collectTelemetrySnapshot()),
                )
            }

            is DesktopTelemetryEvent -> _desktopTelemetry.value = event

            is StatusEvent -> _statusText.value = event.text

            is PongEvent -> {
                val rtt = System.currentTimeMillis() - event.sentAtMs
                // A negative or absurd value means the clocks disagree, not that
                // the link is fast; showing it would be worse than showing none.
                _latencyMs.value = rtt.takeIf { it in 0..60_000 }
            }
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
                scope.launch {
                    sendOrQueue(
                        TelemetrySnapshotMessage(event.id, telemetry.collectTelemetrySnapshot()),
                    )
                }
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
        if (socket.send(message)) return
        when (message) {
            // Bracketing messages for a capture session that is already over. Sending
            // them minutes later describes a stream the desktop never saw any audio
            // for, so drop them instead.
            is AudioInputStartMessage, is AudioInputEndMessage, is InterruptMessage -> {
                Log.i(TAG, "dropping stale ${message::class.simpleName} rather than queueing it")
            }
            else -> {
                while (outbox.size >= OUTBOX_CAPACITY) outbox.poll()
                outbox.add(message)
            }
        }
        connect()
    }

    /**
     * Whether [requestId] can still be decided right now.
     *
     * Three gates, and all three exist because of the rule that the app never
     * auto-approves anything and refuses to act on a stale event stream:
     *
     *  - the request must be one the desktop actually sent and has not resolved.
     *    Without this the method signs whatever id it is handed, and it is reachable
     *    from a widget action whose parameters are not under the app's control — a
     *    signing oracle for decisions the user never saw;
     *  - it must not have expired. `expires_at_ms` was parsed and never read, so an
     *    expired card stayed tappable and re-signed with a fresh `decided_at_ms`
     *    that sails through the desktop's clock-skew window;
     *  - the link must be up. Accepting a decision offline clears the card and
     *    buzzes "confirm" while nothing has been sent, which is exactly the
     *    false confirmation the stale-stream rule exists to prevent.
     */
    fun approvalBlocker(requestId: String, nowMs: Long = System.currentTimeMillis()): String? {
        val request = _pendingApprovals.value.firstOrNull { it.id == requestId }
            ?: return "That request is no longer pending — it was resolved or withdrawn."
        val expiry = request.expiresAtMs
        if (expiry != null && nowMs >= expiry) {
            return "That request expired. Ask the desktop to raise it again."
        }
        if (socket.state.value != ConnectionState.CONNECTED) {
            return "Not connected to the desktop, so this decision cannot be delivered yet."
        }
        if (!settings.hasSharedSecret.value) {
            return "No pairing secret set, so this decision cannot be signed. Set one below."
        }
        return null
    }

    /** True when the HUD and the widgets should offer Approve/Deny at all. */
    fun canDecide(requestId: String): Boolean = approvalBlocker(requestId) == null

    /**
     * An unsigned decision is never sent, and neither is one that fails any gate in
     * [approvalBlocker]. The request stays in the pending list and the HUD says why,
     * rather than the desktop acting on an approval this handset cannot prove it
     * authorised — or the user believing they answered something that never left.
     */
    fun submitApprovalDecision(requestId: String, approved: Boolean) {
        val blocker = approvalBlocker(requestId)
        if (blocker != null) {
            _blockingError.value = blocker
            telemetry.vibrate("alert")
            return
        }

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

        val decision = ApprovalDecisionMessage(
            id = requestId,
            approved = approved,
            deviceId = settings.deviceId,
            decidedAtMs = now,
            nonce = nonce,
            signature = signature,
        )

        // Persisted before the send is attempted, not after it fails. The caller may
        // be a BroadcastReceiver on a cold process whose importance boost lapses the
        // moment onReceive returns, and the send is asynchronous.
        pendingDecisions.add(decision)
        if (socket.send(decision)) pendingDecisions.remove(decision) else connect()

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
        // Single-flight rather than check-then-act: this is called from the main
        // thread by the HUD and the assistant, and from a binder thread by a bound
        // SpeechRecognizer.
        if (!micTransition.compareAndSet(false, true)) return _micActive.value
        try {
            if (_micActive.value) return true
            bargeIn()

            // Promote the foreground service before the mic is opened, and abort if
            // the platform refuses — a `microphone` foreground service cannot be
            // started from the background, and capturing anyway yields silence under
            // a notification that claims to be listening.
            val promoter = micForegroundPromoter
            if (promoter != null && !promoter(true)) {
                _blockingError.value =
                    "Android would not allow microphone capture from the background. " +
                        "Open Jarvis and try again."
                return false
            }

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
                promoter?.invoke(false)
                return false
            }
            _micActive.value = true
            return true
        } finally {
            micTransition.set(false)
        }
    }

    fun stopMic() {
        if (!micTransition.compareAndSet(false, true)) return
        try {
            if (!_micActive.value) return
            streamer.stop()
            _micActive.value = false
            micStreamId?.let { sendOrQueue(AudioInputEndMessage(it)) }
            micStreamId = null
            micForegroundPromoter?.invoke(false)
        } finally {
            micTransition.set(false)
        }
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

    /** Small: this queue only holds things worth replaying, and it is never drained
     *  by anything but a successful reconnect. */
    private const val OUTBOX_CAPACITY = 64
}
