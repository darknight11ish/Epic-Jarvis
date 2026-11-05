package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The source pins for call recording (2026-11-04).
 *
 * The recorder is an Android foreground service, so its behaviour cannot be
 * run in this repository's JVM tests, and the REAL test is one real call on the
 * owner's Pixel 9 - which was not connected in this session, and was NOT
 * placed. Following this repository's own precedent (`R8SourcePinTest`,
 * `AuditPlumbingTest`, `ExpiredCardShowsNoButtonsTest`), each rule that would
 * otherwise rest on a promise is held here by reading the shipped source for
 * the exact line that implements it (or for the line that must never appear).
 *
 * Every pin fails on the tree before its change.
 */
class CallRecordSourcePinTest {

    private val main = "jarvis-client/app/src/main/java/com/jarvis/client/"
    private val manifest = "jarvis-client/app/src/main/AndroidManifest.xml"

    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private fun source(rel: String): String = repoFile(main + rel).readText()

    /**
     * The file's CODE, with its comments removed.
     *
     * Every pin about something that must NOT appear has to read the code and
     * not the prose: a KDoc that explains why `VOICE_COMMUNICATION` is never
     * used, or that the note is never written, is the opposite of a violation
     * - and a pin that tripped over it would push the reason out of the file.
     */
    private fun code(text: String): String = text.lines().joinToString("\n") { line ->
        val t = line.trimStart()
        when {
            t.startsWith("//") || t.startsWith("*") || t.startsWith("/*") -> ""
            else -> line.substringBefore(" //")
        }
    }

    private fun after(src: String, marker: String, chars: Int = 2_500): String {
        val at = src.indexOf(marker)
        assertTrue("$marker is gone", at >= 0)
        return src.substring(at, minOf(src.length, at + chars))
    }

    private fun service(): String = source("service/CallRecordService.kt")

    private fun serviceCode(): String = code(service())

    // ------------------------------------------------------- the platform truth ---

    @Test
    fun `the recorder asks for UNPROCESSED first and MIC second, and never the echo-cancelled source`() {
        val src = service()
        val open = after(src, "private fun openRecorder(): AudioRecord?")
        val openCode = code(open)
        val unprocessed = openCode.indexOf("MediaRecorder.AudioSource.UNPROCESSED")
        val mic = openCode.indexOf("MediaRecorder.AudioSource.MIC")
        assertTrue("UNPROCESSED must be the first source asked for", unprocessed >= 0)
        assertTrue("MIC must be the fallback", mic > unprocessed)
        // The one source that must never be asked for: VOICE_COMMUNICATION's
        // echo canceller removes the other person, which is the voice this
        // feature exists to keep. The reason may be written in a comment; the
        // CODE must not name it.
        assertFalse(
            "VOICE_COMMUNICATION must never be opened as a source",
            code(src).contains("MediaRecorder.AudioSource.VOICE_COMMUNICATION"),
        )
        assertFalse(code(src).contains("setAudioSource"))
    }

    @Test
    fun `the exact audio shape is 16 kHz mono PCM16`() {
        val src = service()
        assertTrue(src.contains("AudioFormat.CHANNEL_IN_MONO"))
        assertTrue(src.contains("AudioFormat.ENCODING_PCM_16BIT"))
        assertTrue("the rate comes from the contract's own constant", src.contains("RATE = CallRecordRules.SAMPLE_RATE"))
    }

    @Test
    fun `samples are written as little-endian PCM16`() {
        val src = service()
        val le = after(src, "private fun toLittleEndian(")
        assertTrue(le.contains("(v and 0xFF).toByte()"))
        assertTrue(le.contains("((v shr 8) and 0xFF).toByte()"))
    }

    @Test
    fun `the call is noticed from the audio mode, with no phone-state permission`() {
        val src = service()
        val on = after(src, "private fun callOn(): Boolean")
        assertTrue("the call is read from AudioManager.mode", on.contains("AudioManager.MODE_NORMAL"))
        assertTrue("and decided by the rule Live already uses", on.contains("LiveRules.onCall(mode, ownVoiceCall)"))
        // No phone-state permission is asked for anywhere in this feature.
        assertFalse(code(src).contains("READ_PHONE_STATE"))
        assertFalse(manifest().contains("READ_PHONE_STATE"))
        assertFalse(code(source("call/CallRecordRules.kt")).contains("READ_PHONE_STATE"))
    }

    // ------------------------------------------------------------- the speaker ---

    @Test
    fun `the call is put on speaker before recording, and the failure is said`() {
        val src = service()
        assertTrue(src.contains("setCommunicationDevice(speaker)"))
        assertTrue("the legacy fallback must survive", src.contains("setSpeakerphoneOn(true)"))
        val begin = after(src, "private fun beginRecording()")
        assertTrue("the speaker is asked for before the recorder opens", begin.indexOf("wantSpeaker()") < begin.indexOf("openRecorder()"))
        // The sentence the notification shows when it was refused, and the
        // rule that it is never claimed both sides were captured.
        assertTrue(src.contains("CallRecordRules.SPEAKER_ASK"))
        assertTrue(source("call/CallRecordRules.kt").contains("Turn the call on speaker so Jarvis can hear both sides"))
    }

    // -------------------------------------------------------- the notification ---

    @Test
    fun `the notification carries the consent reminder and a Stop button`() {
        val src = service()
        assertTrue("the consent line is drawn", src.contains("CallRecordRules.CONSENT_LINE"))
        assertTrue("Stop is an action on the notice", src.contains("addAction(0, STOP_LABEL, stop)"))
        assertTrue("the clock is in the title", src.contains("CallRecordRules.clock(elapsed)"))
        assertTrue("it is an ongoing foreground-service notice", src.contains("setOngoing(true)"))
        assertTrue(src.contains("ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE"))
        // And it is redacted on a locked phone by the ONE shared rule.
        assertTrue(src.contains("SecurityRules.notificationsLocked("))
    }

    @Test
    fun `the manifest declares the microphone foreground service`() {
        val xml = manifest()
        assertTrue(xml.contains("android:name=\".service.CallRecordService\""))
        assertTrue(xml.contains("android:foregroundServiceType=\"microphone\""))
        assertTrue("nothing else may start it", xml.contains("android:exported=\"false\""))
    }

    // ---------------------------------------------------- the phone does no more ---

    @Test
    fun `the phone never turns speech into words`() {
        // The standing rule: a client must not do speech-to-text. Nothing in
        // this feature may even name the Android transcriber or a model.
        for (rel in listOf(
            "call/CallRecordRules.kt",
            "call/CallRecordNow.kt",
            "call/CallRecordStore.kt",
            "call/Chunker.kt",
            "service/CallRecordService.kt",
        )) {
            val src = code(source(rel))
            assertFalse("$rel must not use SpeechRecognizer", src.contains("SpeechRecognizer"))
            assertFalse("$rel must not create a recognizer intent", src.contains("RecognizerIntent"))
            assertFalse("$rel must not run an ONNX model", src.contains("OrtSession"))
        }
    }

    @Test
    fun `the phone never writes to the vault and never names a note path`() {
        for (rel in listOf(
            "call/CallRecordRules.kt",
            "call/CallRecordNow.kt",
            "service/CallRecordService.kt",
            "net/CallRecordWire.kt",
        )) {
            val src = code(source(rel)).lowercase()
            assertFalse("$rel must not reach a vault path", src.contains(".obsidian"))
            assertFalse("$rel must not build a note path", src.contains("notes/") || src.contains("vault"))
        }
    }

    // -------------------------------------------------------- the mic interlock ---

    @Test
    fun `call recording claims the microphone through the one arbitration point`() {
        val src = service()
        val apply = after(src, "private fun apply(event: CallRecordRules.Event)", 3_000)
        assertTrue("arming claims the microphone", apply.contains("CallRecordRules.Effect.CLAIM_MIC -> MicNow.arm()"))
        assertTrue("the release is on the same table", apply.contains("MicNow.disarm()"))
        assertTrue("the recorder asks before it opens", src.contains("MicNow.mayOpen(MicOwner.Use.CALL_RECORD)"))
        assertTrue("and reports that it opened it", src.contains("MicNow.opened(MicOwner.Use.CALL_RECORD)"))
    }

    @Test
    fun `the other three capture paths consult the same arbitration point`() {
        // Live: it closes its recorder while call recording holds the mic.
        val live = source("service/LiveService.kt")
        assertTrue(live.contains("MicNow.callRecordingHolds()"))
        assertTrue(live.contains("MicNow.opened(MicOwner.Use.LIVE)"))
        assertTrue(live.contains("MicNow.closed(MicOwner.Use.LIVE)"))
        // The wake word: its loop pauses and its recorder is reported closed.
        val wake = source("service/WakeWordService.kt")
        assertTrue(wake.contains("MicNow.callRecordingHolds()"))
        assertTrue(wake.contains("MicNow.opened(MicOwner.Use.WAKE)"))
        assertTrue(wake.contains("MicNow.closed(MicOwner.Use.WAKE)"))
        // The talk button: refused with the arbitration's own sentence.
        val recorder = source("audio/Recorder.kt")
        assertTrue(recorder.contains("MicNow.mayOpen(MicOwner.Use.TALK)"))
        assertTrue(recorder.contains("Failure.MicBusy(may.why)"))
        assertTrue(recorder.contains("MicNow.closed(MicOwner.Use.TALK)"))
    }

    @Test
    fun `the refusal has its own sentence, not no microphone available`() {
        val voices = source("voice/VoiceSession.kt")
        assertTrue(
            "the talk button must say call recording has the microphone",
            voices.contains("is Recorder.Failure.MicBusy -> why.why"),
        )
    }

    // ------------------------------------------------------------- the wiring ---

    @Test
    fun `a chat reply can arm and stop it, once`() {
        val runtime = source("JarvisRuntime.kt")
        assertTrue(
            "the runtime applies the directive it was sent",
            runtime.contains("chatSession.callRecordDirective.collect"),
        )
        assertTrue(runtime.contains("CallRecordNow.onDirective(event, app)"))
        assertTrue("and consumes it, so it cannot apply twice", runtime.contains("consumeCallRecordDirective()"))
        val session = source("net/ChatSession.kt")
        assertTrue(session.contains("CallRecordWire.directive(routeHeader)"))
    }

    @Test
    fun `every request carries the client header, because it goes through postObject`() {
        val api = source("net/JarvisApi.kt")
        val callRecord = after(api, "suspend fun callRecordStart(")
        assertTrue(callRecord.contains("postObject(CallRecordRules.START_PATH"))
        val chunk = after(api, "suspend fun callRecordChunk(")
        assertTrue(chunk.contains("postObject(CallRecordRules.CHUNK_PATH"))
        val finish = after(api, "suspend fun callRecordFinish(")
        assertTrue(finish.contains("postObject(CallRecordRules.FINISH_PATH"))
        // postObject adds `authed()`, which is where X-Jarvis-Client: hud rides.
        val post = after(api, "private suspend fun postObject(")
        assertTrue(post.contains("authed()"))
        // And the token is never logged by this feature.
        assertFalse(serviceCode().contains("tokens.token"))
        assertFalse(code(source("net/CallRecordWire.kt")).contains("token"))
    }

    @Test
    fun `the plate is the one place to arm and disarm, and it shows the state`() {
        val plate = source("ui/screens/CallRecordPlate.kt")
        assertTrue(plate.contains("CallRecordNow.arm(context)"))
        assertTrue(plate.contains("CallRecordNow.disarm(context)"))
        assertTrue(plate.contains("CallRecordNow.stop(context)"))
        assertTrue("the armed line is shown", plate.contains("CallRecordRules.line(status.phase, status.elapsedMs)"))
        // It really is drawn: the Voice settings section calls it.
        val activity = source("MainActivity.kt")
        assertTrue(activity.contains("CallRecordPlate") || activity.contains("CallRecordCard()"))
    }

    @Test
    fun `the queue is on disk before anything is uploaded`() {
        val src = service()
        val read = after(src, "private fun readUntilStopped(", 3_000)
        val writeAt = read.indexOf("write(chunk)")
        val uploadAt = read.indexOf("drain(attempts = 1)")
        assertTrue("the chunk is written first", writeAt >= 0)
        assertTrue("and only then is the uploader nudged", uploadAt > writeAt || uploadAt < 0)
        assertTrue("the store is this app's own files directory", src.contains("CallRecordStore.folder(filesDir)"))
    }

    private fun manifest(): String = repoFile(manifest).readText()
}
