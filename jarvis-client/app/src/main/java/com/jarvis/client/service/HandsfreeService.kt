package com.jarvis.client.service

import android.Manifest
import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.audio.Speaker
import com.jarvis.client.data.ContactsLookup
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.handsfree.HandsfreeClip
import com.jarvis.client.handsfree.HandsfreeFlow
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.CardWords
import com.jarvis.client.net.Handsfree
import com.jarvis.client.net.SmsSend
import com.jarvis.client.net.SaidAloud
import com.jarvis.client.platform.DeviceSecure
import com.jarvis.client.voice.HeardSound
import com.jarvis.client.voice.LiveRules
import com.jarvis.client.voice.MicClaim
import com.jarvis.client.voice.MicOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/**
 * Hands-free mode while the phone is not being held: the card is read out, the
 * answer window opens, the clip goes to the PC - and a text message gets sent.
 *
 * WHY A SERVICE AT ALL. A card arrives on the event stream, and the owner asked
 * for the phone to read it out and listen for "confirm" - which means the work
 * has to happen with the app in the background, and a microphone in the
 * background needs a foreground service on Android 11+. So this is one, of type
 * `microphone` (the permission is already in the manifest for "hey Jarvis").
 * It is started ONLY when the PC says the mode is armed ([JarvisRuntime]
 * follows the read) and stopped the moment it says otherwise: there is no
 * worker, no boot receiver and no sticky restart, because a background
 * foreground-service start is refused by Android and a refused start that
 * pretends to work is the failure this project keeps writing down.
 *
 * WHAT IT DOES, in the order the owner asked for it:
 *
 *  1. `handsfree_card` arrives -> an ongoing notification with the card's short
 *     title and the time it has left, and its own "Open the card" action, so a
 *     tap goes to the ordinary approval card. Then the card's `say` is fetched
 *     from `/api/voice/say` and played through [Speaker] - never in a phone
 *     call, and never in the phone's own voice if the PC's is unavailable.
 *  2. The read-out ends -> a chime, and a ten-second answer window
 *     ([HandsfreeFlow.LISTEN_MS]) with [MicOwner] held, so Live and "hey
 *     Jarvis" close their recorders for those ten seconds and reopen after. The
 *     talk button is the fourth part and it HOLDS the ledger too
 *     (`audio/Recorder.kt`), so a button being pressed when the card arrives
 *     refuses this window in words rather than opening a second recorder over
 *     it ([MicClaim]).
 *  3. The window closes -> the clip (16 kHz mono WAV, [HandsfreeClip]) goes to
 *     `/api/handsfree/answer`, and what the PC heard and decided is shown in
 *     plain words ([Handsfree.answerWords]).
 *  4. Separately, `phone_command kind=send_sms` -> the contact is resolved on
 *     THIS phone ([SmsSend.resolve], exact unique match only), the text is
 *     sent, and the platform's own result is posted to `/api/phone/result`.
 *
 * WHAT IT NEVER DOES. It never transcribes (no `SpeechRecognizer` anywhere in
 * this file); it never sends a text it could not confirm the platform accepted;
 * it never answers a card whose read-out failed; it never opens the microphone
 * while no card is waiting (the only path to [HandsfreeFlow.State.Listening] is
 * a card); it never puts a card's words or a text message where a locked
 * phone's screen would show them - [HandsfreeNotice] is the one rule for that,
 * the same [SecurityRules.notificationsLocked] every other notifier uses; and it
 * never claims a decision the PC did not give it.
 */
class HandsfreeService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var cards: Job? = null
    private var commands: Job? = null

    /** Ids already handled, so a re-delivered card or command is not done twice. */
    private var lastCard: String? = null
    private var lastCommand: String? = null

    private val flow = HandsfreeFlow()
    private val speaker: Speaker
        get() = JarvisRuntime.voice.speaker

    override fun onCreate() {
        super.onCreate()
        goForeground(getString(R.string.handsfree_running))
        cards = scope.launch {
            JarvisRuntime.handsfreeCard.filterNotNull().collect { card -> onCard(card) }
        }
        commands = scope.launch {
            JarvisRuntime.handsfreeCommand.filterNotNull().collect { cmd -> onCommand(cmd) }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // NOT sticky on purpose: Android refuses a foreground-service start
        // from the background, so a sticky restart after the process is
        // reclaimed would be refused on the exact path that matters - and the
        // mode would look armed while nothing was reading cards out.
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        cards?.cancel()
        commands?.cancel()
        // The microphone first, and unconditionally: a service torn down inside
        // the answer window must not leave Live and "hey Jarvis" paused for a
        // window that no longer exists.
        MicClaim.free(MicOwner.HANDSFREE)
        flow.reset()
        JarvisRuntime.publishHandsfree(line = null, listening = false)
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ------------------------------------------------------------- a card ----

    /**
     * One card: notification, read-out, answer window, upload, words.
     *
     * Guarded against the same card twice - a re-sent event, or a collect that
     * replays - because reading one card out twice would open two windows over
     * each other. [lastCard] is cleared when the card is finished, so a LATER
     * card that happens to carry the same id (which the PC does not do) would
     * still be handled.
     */
    private suspend fun onCard(card: Handsfree.Card) {
        if (card.cardId == lastCard) return
        when (val moved = flow.onCard(card, SystemClock.elapsedRealtime())) {
            is HandsfreeFlow.Moved.No -> {
                Log.i(TAG, "a hands-free card was not started: ${moved.why}")
                return
            }
            is HandsfreeFlow.Moved.To -> Unit
        }
        lastCard = card.cardId
        notifyCard(card)
        try {
            readOutAndListen(card)
        } finally {
            // Whatever happened, the microphone is not this service's any more.
            MicClaim.free(MicOwner.HANDSFREE)
            JarvisRuntime.clearHandsfreeCard()
            // Cleared here rather than only on the success path: a card the PC
            // raises AGAIN later (its own retry, a re-raise after a timeout)
            // carries the same id on purpose, and refusing it for ever because
            // the first attempt failed would leave it read out nowhere. A
            // duplicate DELIVERY of one event cannot reach this - the flow of
            // cards does not re-emit an unchanged value.
            lastCard = null
        }
    }

    private suspend fun readOutAndListen(card: Handsfree.Card) {
        var listening = false
        try {
            if (inCall()) {
                // Never spoken over a phone call: the other person would hear
                // Jarvis read out the owner's business. The card is left in the
                // notification, and the flow is freed for the next one.
                flow.fail(Handsfree.IN_CALL)
                JarvisRuntime.publishHandsfree(Handsfree.IN_CALL, listening = false)
                return
            }
            JarvisRuntime.publishHandsfree(Handsfree.READING, listening = false)
            val spoken = speak(card)
            val now = SystemClock.elapsedRealtime()
            if (!spoken) {
                // The card could not be said, so the window is NOT opened: a
                // microphone opened for a card the owner never heard is the one
                // thing the mode must not do. The notification stays, and the
                // flow is freed rather than left in Reading.
                flow.fail(Handsfree.NO_VOICE)
                JarvisRuntime.publishHandsfree(Handsfree.NO_VOICE, listening = false)
                return
            }
            // The window's clock starts where the read-out ENDED, and the
            // microphone is taken before it does: if the talk button has it,
            // the window does not open at all rather than opening over a
            // sentence the owner is already speaking. [MicClaim] owns both the
            // claim and the sentence, so this refusal is never silent.
            when (val claim = MicClaim.take(MicOwner.HANDSFREE)) {
                MicClaim.Now.Open -> Unit
                is MicClaim.Now.Busy -> {
                    flow.fail(claim.why)
                    JarvisRuntime.publishHandsfree(claim.why, listening = false)
                    return
                }
            }
            flow.onSpoken(now)
            listening = true
            // A chime is the "now it is your turn" - the same two notes the
            // talk button plays, made from numbers (no file, no new asset).
            speaker.playTone(HeardSound.samples(), HeardSound.RATE)
            JarvisRuntime.publishHandsfree(Handsfree.LISTENING, listening = true)
            val clip = recordWindow()
            MicClaim.free(MicOwner.HANDSFREE)
            listening = false
            val closed = flow.onWindowClosed(clip, SystemClock.elapsedRealtime())
            if (closed is HandsfreeFlow.Moved.To && flow.state is HandsfreeFlow.State.Uploading) {
                JarvisRuntime.publishHandsfree(Handsfree.SENDING, listening = false)
                upload(card, requireNotNull(clip))
            } else {
                JarvisRuntime.publishHandsfree(flow.line(), listening = false)
            }
        } finally {
            if (listening) MicClaim.free(MicOwner.HANDSFREE)
        }
    }

    /**
     * Plays the PC's own WAV for the card's `say`. False when there is nothing
     * to play - no engine on the PC, an empty `say`, or a failed fetch.
     *
     * The phone never synthesises a card's words (`Speaker.speakOnDevice` is
     * deliberately NOT used here): a card read out in the phone's voice would
     * be words about the owner's approval, said by something other than the
     * Jarvis he trusts.
     */
    private suspend fun speak(card: Handsfree.Card): Boolean {
        if (card.say.isBlank()) return false
        val said = JarvisRuntime.api.say(card.say)
        val wav = when (said) {
            is ApiResult.Ok -> (said.value as? SaidAloud.Audio)?.wav
            is ApiResult.Failed -> null
        } ?: return false
        // `arm` clears the stop flag for a new utterance; the surface is the
        // same one every reply uses, so audio focus, the call checks and the
        // face's mouth all behave exactly as they do for an answer.
        speaker.arm()
        speaker.play(wav)
        return true
    }

    /** The PC decided: one sentence on the notification and in the app. */
    private suspend fun upload(card: Handsfree.Card, wav: ByteArray) {
        val result = JarvisRuntime.api.answerHandsfree(card.cardId, wav)
        val moved = when (result) {
            is ApiResult.Ok -> flow.onAnswer(result.value, null, SystemClock.elapsedRealtime())
            is ApiResult.Failed -> flow.onAnswer(
                null,
                JarvisRuntime.noticeFor(result.error),
                SystemClock.elapsedRealtime(),
            )
        }
        val line = if (moved is HandsfreeFlow.Moved.To) flow.line() else null
        JarvisRuntime.publishHandsfree(line, listening = false)
        notifyCard(card, line ?: Handsfree.SENDING, done = true)
    }

    /**
     * Records the answer window and returns the WAV, or null when it was too
     * short to be a word.
     *
     * The window is closed by the CLOCK, not by a pause: the loop stops at
     * [HandsfreeFlow.Listening.until] whatever the microphone holds, so a
     * mumble or a room's hiss cannot keep it open. On this phone the capture
     * rate is 16 kHz because that is what is asked for first; a device that
     * refuses it gives another rate and [HandsfreeClip] resamples, so the
     * upload is 16 kHz either way.
     */
    private fun recordWindow(): ByteArray? {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return null
        }
        val until = (flow.state as? HandsfreeFlow.State.Listening)?.until
            ?: return null
        val rate = RATES.firstOrNull {
            AudioRecord.getMinBufferSize(
                it, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            ) > 0
        } ?: return null
        val minBuf = AudioRecord.getMinBufferSize(
            rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuf <= 0) return null
        val recorder = runCatching {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                rate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                minBuf * 4,
            )
        }.getOrNull() ?: return null
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            runCatching { recorder.release() }
            return null
        }
        val clip = HandsfreeClip(rate, HandsfreeFlow.LISTEN_MS / 1000f)
        val buffer = ShortArray(minBuf.coerceAtLeast(1_024))
        try {
            recorder.startRecording()
            while (!clip.full && SystemClock.elapsedRealtime() < until && !flow.windowOver(
                    SystemClock.elapsedRealtime(),
                )
            ) {
                val n = recorder.read(buffer, 0, buffer.size)
                // read() returns a negative code rather than throwing; a
                // permission revoked mid-window lands here.
                if (n <= 0) break
                clip.append(buffer, n)
            }
        } catch (e: IllegalStateException) {
            Log.w(TAG, "the answer window's microphone failed", e)
        } finally {
            runCatching { recorder.stop() }
            runCatching { recorder.release() }
        }
        return clip.wav()
    }

    // -------------------------------------------------------- a command ----

    /**
     * One `phone_command`: the text message.
     *
     * Every path ends in a posted result, including the refusals - a PC that
     * asked for a text and heard nothing back could not tell "not sent" from
     * "still working". The message and the number are NOT kept: they live in
     * this call and in the string Android's SMS service holds while it sends.
     */
    private suspend fun onCommand(command: Handsfree.Command) {
        if (command.id == lastCommand) return
        lastCommand = command.id
        val connected = JarvisRuntime.link.value == com.jarvis.client.LinkState.CONNECTED &&
            !JarvisRuntime.stale.value
        val wantsContacts = SmsSend.needsContacts(command.contact)
        val gate = SmsSend.gate(
            hasSmsPermission = granted(Manifest.permission.SEND_SMS),
            hasContactsPermission = granted(Manifest.permission.READ_CONTACTS) || !wantsContacts,
            connected = connected,
        )
        if (gate != null) {
            report(command, ok = false, receipt = SmsSend.RECEIPT_REFUSED, why = gate)
            notifySms(SmsSend.failedLine(command.contact, gate))
            return
        }
        if (command.kind != Handsfree.KIND_SEND_SMS) {
            report(command, ok = false, receipt = SmsSend.RECEIPT_REFUSED, why = Handsfree.UNKNOWN_KIND)
            notifySms(SmsSend.failedLine(command.contact, Handsfree.UNKNOWN_KIND))
            return
        }
        if (command.text.isBlank()) {
            report(command, ok = false, receipt = SmsSend.RECEIPT_REFUSED, why = SmsSend.EMPTY_TEXT)
            notifySms(SmsSend.failedLine(command.contact, SmsSend.EMPTY_TEXT))
            return
        }
        val known = if (wantsContacts) ContactsLookup.phones(this, command.contact) else emptyList()
        when (val resolved = SmsSend.resolve(command.contact, known)) {
            is SmsSend.Resolved.One -> {
                val sent = send(resolved.number, command.text)
                val name = resolved.name.ifBlank { resolved.number }
                if (sent.ok) {
                    report(command, ok = true, receipt = SmsSend.RECEIPT_SENT, why = "")
                    notifySms(SmsSend.sentLine(name, command.text))
                } else {
                    val why = SmsSend.sendFailure(sent.code)
                    report(command, ok = false, receipt = SmsSend.receiptFailed(sent.code), why = why)
                    notifySms(SmsSend.failedLine(name, why))
                }
            }
            else -> {
                val why = SmsSend.refusedSentence(resolved)
                report(command, ok = false, receipt = SmsSend.RECEIPT_REFUSED, why = why)
                notifySms(SmsSend.failedLine(command.contact, why))
            }
        }
        lastCommand = null
    }

    /** One send, and the platform's own answer - never an assumption. */
    private suspend fun send(number: String, text: String): Sent {
        val manager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            getSystemService(android.telephony.SmsManager::class.java)
        } else {
            @Suppress("DEPRECATION")
            android.telephony.SmsManager.getDefault()
        } ?: return Sent(false, RESULT_UNKNOWN)

        val seq = startSeq
        startSeq += 1
        val action = "$SMS_SENT.$seq"
        return withTimeoutOrNull(SMS_RESULT_TIMEOUT_MS) {
            suspendCancellableCoroutine { cont ->
                // A dynamically registered receiver: this app exports no SMS
                // receiver in its manifest, so nothing outside this app can
                // answer for it. `resultCode` is the SMS service's own verdict.
                val receiver = object : android.content.BroadcastReceiver() {
                    override fun onReceive(context: Context?, intent: Intent?) {
                        val code = resultCode
                        runCatching { this@HandsfreeService.unregisterReceiver(this) }
                        if (cont.isActive) cont.resume(Sent(code == android.app.Activity.RESULT_OK, code))
                    }
                }
                val registered = runCatching {
                    ContextCompat.registerReceiver(
                        this@HandsfreeService,
                        receiver,
                        android.content.IntentFilter(action),
                        ContextCompat.RECEIVER_NOT_EXPORTED,
                    )
                }.isSuccess
                if (!registered) {
                    if (cont.isActive) cont.resume(Sent(false, RESULT_UNKNOWN))
                    return@suspendCancellableCoroutine
                }
                val pi = PendingIntent.getBroadcast(
                    this@HandsfreeService,
                    seq,
                    Intent(action).setPackage(packageName),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
                val queued = runCatching {
                    if (text.length > SMS_ONE_PART) {
                        manager.sendMultipartTextMessage(
                            number, null, manager.divideMessage(text), arrayListOf(pi), null,
                        )
                    } else {
                        manager.sendTextMessage(number, null, text, pi, null)
                    }
                }
                if (queued.isFailure) {
                    Log.w(TAG, "the SMS service refused the send", queued.exceptionOrNull())
                    runCatching { this@HandsfreeService.unregisterReceiver(receiver) }
                    if (cont.isActive) cont.resume(Sent(false, RESULT_UNKNOWN))
                }
                cont.invokeOnCancellation {
                    runCatching { this@HandsfreeService.unregisterReceiver(receiver) }
                }
            }
        } ?: Sent(false, RESULT_TIMEOUT)
    }

    private data class Sent(val ok: Boolean, val code: Int)

    private suspend fun report(
        command: Handsfree.Command,
        ok: Boolean,
        receipt: String,
        why: String,
    ) {
        val result = JarvisRuntime.api.phoneResult(command.id, ok, receipt, why)
        if (result is ApiResult.Failed) {
            Log.w(TAG, "could not report a phone command's result: ${result.error}")
        }
    }

    // ------------------------------------------------------- notifications ----

    /**
     * The waiting card's notification: its SHORT title, what it has left, and
     * the ordinary card one tap away.
     *
     * The words are [HandsfreeNotice]'s, not this file's: that object applies
     * the app's one redaction rule before any of the card's words are read, so
     * a locked or private phone gets the generic line instead of the PC's `say`
     * (an audit finding, 2026-11-05 - this notification used to put the whole
     * sentence on the lock screen).
     */
    private fun notifyCard(card: Handsfree.Card, line: String? = null, done: Boolean = false) {
        val words = HandsfreeNotice.card(
            locked = lockedWords(),
            card = card,
            line = line,
            waiting = getString(R.string.handsfree_card_waiting),
        )
        post(NotificationIds.HANDSFREE_CARD, words, ongoing = !done)
    }

    /** A text message's receipt - [HandsfreeNotice.sms] redacts it the same way. */
    private fun notifySms(line: String) {
        val words = HandsfreeNotice.sms(
            locked = lockedWords(),
            title = getString(R.string.handsfree_sms_title),
            line = line,
        )
        post(NotificationIds.HANDSFREE_SMS, words, ongoing = false)
    }

    /**
     * The app's ONE rule for whether notification content may be drawn, read
     * exactly as `ApprovalNotifier` reads it: App lock, private lists, or a
     * phone whose own lock screen is not secure (`data/Security.kt`).
     *
     * `isSecure` is asked here rather than cached: the owner can change the
     * phone's lock while the app runs, and a cached answer is exactly the stale
     * copy this rule must not have.
     */
    private fun lockedWords(): Boolean = SecurityRules.notificationsLocked(
        JarvisRuntime.settings.security.value,
        DeviceSecure.isSecure(this),
    )

    private fun post(id: Int, words: HandsfreeNotice.Words, ongoing: Boolean) {
        val n = NotificationCompat.Builder(this, CHANNEL_ID)
            // Never bridged to a watch unless the owner asked for that
            // elsewhere, exactly as every other notification here.
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(words.title)
            .setContentText(words.body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(words.body))
            .setOngoing(ongoing)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(cardIntent(id))
            // The lock screen never gets the words themselves. `PRIVATE` keeps
            // the real notification off it and [publicVersion] is the only
            // thing Android may draw there - the same pair every approval
            // notification already carries (`ApprovalNotifier.build`).
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(publicVersion(id))
            // The card's own way through to the ordinary approval card. It is
            // an ACTION, not a second copy of the card: nothing can be approved
            // from a notification, which is the standing rule everywhere else.
            .addAction(0, CardWords.OPEN_CARD, cardIntent(id + 1))
            .build()
        runCatching { NotificationManagerCompat.from(this).notify(id, n) }
            .onFailure { Log.w(TAG, "could not post the hands-free notification", it) }
    }

    /**
     * Android's own lock-screen copy: [HandsfreeNotice.PUBLIC] and nothing
     * else. No card title, no `say`, no time left, no recipient and no text -
     * the same redacted line the approval notifier's own public version shows,
     * because a waiting hands-free card is an approval waiting.
     */
    private fun publicVersion(id: Int): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(HandsfreeNotice.PUBLIC)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setContentIntent(cardIntent(id))
            .build()

    /** Opens the app where the card is: the Home screen's approval list. */
    private fun cardIntent(request: Int): PendingIntent = PendingIntent.getActivity(
        this,
        request,
        Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    /** The service's own ongoing line. Its type is `microphone`: it records. */
    private fun goForeground(text: String) {
        val n: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.handsfree_title))
            .setContentText(text)
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(cardIntent(0))
            .build()
        runCatching {
            ServiceCompat.startForeground(
                this,
                NotificationIds.HANDSFREE,
                n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
        }.onFailure {
            // A refused start is the one case this service cannot work in.
            // Log it and stop: a service that stays up with no notification is
            // exactly the "looks fine, does nothing" failure the project keeps
            // writing down.
            Log.e(TAG, "startForeground refused", it)
            stopSelf()
        }
    }

    // ------------------------------------------------------------ helpers ----

    private fun granted(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    /** True while the phone is in a call, by the same rule Live already uses. */
    private fun inCall(): Boolean {
        val manager = getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return false
        return LiveRules.onCall(manager.mode, ownVoiceCall = false, ownMicCall = false)
    }

    companion object {
        private const val TAG = "JarvisHandsfree"

        /** The channel every notification here uses (created in [com.jarvis.client.JarvisApp]). */
        const val CHANNEL_ID = "jarvis_handsfree"

        private const val SMS_SENT = "com.jarvis.client.SMS_SENT"

        /** One SMS part is 160 GSM characters; anything longer is divided. */
        private const val SMS_ONE_PART = 160

        /** How long to wait for the SMS service's own verdict before saying so. */
        private const val SMS_RESULT_TIMEOUT_MS = 20_000L

        /** No verdict came back at all: never read as "sent". */
        private const val RESULT_TIMEOUT = -2

        /** The send could not even be attempted. */
        private const val RESULT_UNKNOWN = -1

        private var startSeq = 1000

        /** The capture rates this phone is asked for, 16 kHz first. */
        private val RATES = intArrayOf(16_000, 48_000, 44_100, 32_000, 22_050).toList()

        /**
         * Starts the service from the foreground ([JarvisRuntime] calls this
         * when the PC says the mode is armed). Refused-by-Android is a
         * possibility and is not swallowed: the caller logs it.
         */
        fun start(context: Context) {
            runCatching {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, HandsfreeService::class.java),
                )
            }.onFailure { Log.w(TAG, "could not start hands-free", it) }
        }

        /** Stops it. Idempotent, and safe when it was never started. */
        fun stop(context: Context) {
            // The service itself, not a "please stop" intent: the hands-free
            // service's own end has to release the microphone ledger whatever
            // the owner did to it, and `onDestroy` is the one place that
            // always runs.
            runCatching { context.stopService(Intent(context, HandsfreeService::class.java)) }
                .onFailure { Log.w(TAG, "could not stop hands-free", it) }
        }
    }
}
