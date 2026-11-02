package com.jarvis.client

import com.jarvis.client.voice.LiveAudioRoute
import com.jarvis.client.voice.LiveAudioRoute.MicChoice
import com.jarvis.client.voice.LiveAudioRoute.Route
import com.jarvis.client.voice.LiveExtras
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Which microphone Jarvis Live records from, and what the phone's audio mode
 * has to be - decided and tested WITHOUT a car.
 *
 * The owner's report of 2026-11-02: *"when I am using jarvis live in my car and
 * my phone is connected to Bluetooth it acts like it is in a call but jarvis
 * cannot hear me. the mic doesn't seem to be working properly at all."* A car's
 * Bluetooth is a hands-free (HFP/SCO) device: its microphone only exists while
 * the phone is in a CALL, so the recorder must be on `VOICE_COMMUNICATION` with
 * the phone in `MODE_IN_COMMUNICATION` and the car as the communication device.
 * The old code made the car the communication device and recorded
 * `VOICE_RECOGNITION` in `MODE_NORMAL` - a call on the dashboard, silence in
 * the recorder.
 *
 * These tests prove the DECISION. Whether a particular 2017 Chevrolet Bolt
 * actually hands its microphone over is a hardware fact, and only the owner's
 * car can prove it - nothing here says otherwise.
 */
class LiveAudioRouteTest {

    private val car = LiveExtras.Mic(LiveAudioRoute.TYPE_BLUETOOTH_SCO, "Chevrolet MyLink")

    private fun phoneOnly() = LiveAudioRoute.Inputs(
        inputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_MIC),
        outputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_SPEAKER),
    )

    private fun inCar(speaking: Boolean = false) = LiveAudioRoute.Inputs(
        inputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_MIC, LiveAudioRoute.TYPE_BLUETOOTH_SCO),
        outputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_SPEAKER),
        communication = listOf(car),
        speaking = speaking,
    )

    // ---- the six cases the fix has to answer for --------------------------

    @Test
    fun `no Bluetooth - the phone's own microphone, exactly as before`() {
        val listening = LiveAudioRoute.decide(phoneOnly())
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, listening.source)
        assertNull("no audio mode is held: nothing needs one", listening.holdMode)
        assertNull(listening.communicationType)
        assertFalse(listening.needsScoLink)
        assertNull("Android keeps choosing the input, as before", listening.expectedInputType)
        assertFalse(listening.callMode)
        assertFalse(listening.mediaOnly)
        assertEquals(LiveExtras.MIC_PHONE, listening.words)

        // While Jarvis talks: the echo-cancelled path, and the Speaker owns
        // the audio mode (it did before this change, and still does).
        val replying = LiveAudioRoute.decide(phoneOnly().copy(speaking = true))
        assertEquals(LiveAudioRoute.SRC_VOICE_COMMUNICATION, replying.source)
        assertNull(replying.holdMode)
        assertFalse(replying.callMode)
    }

    @Test
    fun `Bluetooth for sound only - unchanged, and the screen says it has no microphone`() {
        val a2dp = LiveAudioRoute.Inputs(
            inputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_MIC),
            outputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_SPEAKER, LiveAudioRoute.TYPE_BLUETOOTH_A2DP),
        )
        val r = LiveAudioRoute.decide(a2dp)
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, r.source)
        assertNull(r.holdMode)
        assertNull(r.communicationType)
        assertFalse(r.callMode)
        assertTrue("a car whose call profile never paired is not a microphone", r.mediaOnly)
        assertEquals(LiveExtras.MIC_MEDIA_ONLY, r.words)

        // A Bluetooth speaker is the same story.
        val speaker = a2dp.copy(
            outputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_SPEAKER, LiveAudioRoute.TYPE_BLE_SPEAKER),
        )
        assertTrue(LiveAudioRoute.decide(speaker).mediaOnly)
    }

    @Test
    fun `a car's hands-free Bluetooth - the call configuration, listening or replying`() {
        val listening = LiveAudioRoute.decide(inCar(speaking = false))
        assertEquals(
            "VOICE_COMMUNICATION is the only source a hands-free microphone feeds",
            LiveAudioRoute.SRC_VOICE_COMMUNICATION,
            listening.source,
        )
        assertEquals(
            "the audio mode is what makes Android bring the SCO link up",
            LiveAudioRoute.MODE_IN_COMMUNICATION,
            listening.holdMode,
        )
        assertEquals(LiveAudioRoute.TYPE_BLUETOOTH_SCO, listening.communicationType)
        assertEquals(LiveAudioRoute.TYPE_BLUETOOTH_SCO, listening.expectedInputType)
        assertTrue(listening.needsScoLink)
        assertTrue(listening.callMode)
        assertFalse(listening.fellBack)
        assertFalse(listening.mediaOnly)
        assertEquals("Microphone: your Bluetooth headset (Chevrolet MyLink)", listening.words)

        // The SAME configuration while Jarvis replies, so the recorder is not
        // torn down and reopened at every sentence (which used to drop the
        // half-second before the owner's sentence and thrash the SCO link).
        assertEquals(listening, LiveAudioRoute.decide(inCar(speaking = true)))
    }

    @Test
    fun `a wired headset - Android already records from it, so nothing changes`() {
        val wired = LiveAudioRoute.Inputs(
            inputTypes = listOf(LiveAudioRoute.TYPE_BUILTIN_MIC, LiveAudioRoute.TYPE_WIRED_HEADSET),
            outputTypes = listOf(LiveAudioRoute.TYPE_WIRED_HEADSET),
            communication = listOf(LiveExtras.Mic(LiveAudioRoute.TYPE_WIRED_HEADSET, "wired")),
        )
        val r = LiveAudioRoute.decide(wired)
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, r.source)
        assertNull("a wired microphone needs no call mode", r.holdMode)
        assertNull(r.communicationType)
        assertFalse(r.needsScoLink)
        assertFalse(r.callMode)
        assertFalse("a wired headset does have a microphone", r.mediaOnly)
        assertEquals(LiveExtras.MIC_PHONE, r.words)
    }

    @Test
    fun `a car unplugged mid-session - the next window is the phone's own again`() {
        val before = LiveAudioRoute.decide(inCar())
        val after = LiveAudioRoute.decide(phoneOnly())
        assertNotEquals("the route must change, so the recorder is reopened on it", before, after)
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, after.source)
        assertNull(after.holdMode)
        assertNull(after.communicationType)
        assertFalse(after.callMode)
        assertEquals(LiveExtras.MIC_PHONE, after.words)
        // What has to be let go is exactly what was taken.
        assertEquals(
            LiveAudioRoute.Undo(mode = LiveAudioRoute.MODE_NORMAL, clearCommunicationDevice = true),
            LiveAudioRoute.undo(before, LiveAudioRoute.MODE_NORMAL),
        )
    }

    @Test
    fun `restoration after stop - the mode and the communication device go back`() {
        val carRoute = LiveAudioRoute.decide(inCar())
        // Normal mode before Live: normal mode after it.
        assertEquals(
            LiveAudioRoute.Undo(LiveAudioRoute.MODE_NORMAL, clearCommunicationDevice = true),
            LiveAudioRoute.undo(carRoute, LiveAudioRoute.MODE_NORMAL),
        )
        // A real call was already up before Live opened the car's microphone:
        // the call's own mode is what comes back, not NORMAL.
        assertEquals(
            LiveAudioRoute.Undo(LiveAudioRoute.MODE_IN_CALL, clearCommunicationDevice = true),
            LiveAudioRoute.undo(carRoute, LiveAudioRoute.MODE_IN_CALL),
        )
        // The phone's own route never touched the mode, so stopping it must
        // not reset a mode somebody else is using.
        assertEquals(
            LiveAudioRoute.Undo(mode = null, clearCommunicationDevice = false),
            LiveAudioRoute.undo(LiveAudioRoute.decide(phoneOnly()), LiveAudioRoute.MODE_IN_COMMUNICATION),
        )
    }

    // ---- the choices around those six ------------------------------------

    @Test
    fun `a BLE headset is preferred over a car's SCO link, the order the app already keeps`() {
        val buds = LiveExtras.Mic(LiveAudioRoute.TYPE_BLE_HEADSET, "Pixel Buds")
        val r = LiveAudioRoute.decide(
            LiveAudioRoute.Inputs(communication = listOf(car, buds)),
        )
        assertEquals(LiveAudioRoute.TYPE_BLE_HEADSET, r.communicationType)
        assertEquals(LiveAudioRoute.SRC_VOICE_COMMUNICATION, r.source)
        assertEquals(LiveAudioRoute.MODE_IN_COMMUNICATION, r.holdMode)
    }

    @Test
    fun `this phone's microphone when the owner says so, even with the car connected`() {
        val r = LiveAudioRoute.decide(inCar().copy(choice = MicChoice.PHONE))
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, r.source)
        assertNull(r.holdMode)
        assertNull(r.communicationType)
        assertFalse(r.callMode)
        assertEquals(LiveExtras.MIC_PHONE, r.words)
    }

    @Test
    fun `only a Bluetooth microphone wanted and none connected - this phone's, and it says so`() {
        val r = LiveAudioRoute.decide(phoneOnly().copy(choice = MicChoice.HEADSET))
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, r.source)
        assertTrue(r.fellBack)
        assertEquals(LiveExtras.MIC_FELL_BACK, r.words)
    }

    @Test
    fun `Android refusing the car - the phone's microphone, and words that say why`() {
        val fell = LiveAudioRoute.fallback(inCar())
        assertEquals(LiveAudioRoute.SRC_VOICE_RECOGNITION, fell.source)
        assertNull(fell.holdMode)
        assertNull(fell.communicationType)
        assertFalse(fell.callMode)
        assertTrue(fell.fellBack)
        assertEquals(LiveExtras.MIC_FELL_BACK, fell.words)
        // Refused while Jarvis was talking: the echo-cancelled path is kept.
        assertEquals(
            LiveAudioRoute.SRC_VOICE_COMMUNICATION,
            LiveAudioRoute.fallback(inCar(speaking = true)).source,
        )
    }

    @Test
    fun `a saved microphone choice can never wedge the microphone`() {
        assertEquals(MicChoice.AUTO, LiveAudioRoute.choiceOf(null))
        assertEquals(MicChoice.AUTO, LiveAudioRoute.choiceOf(""))
        assertEquals(MicChoice.AUTO, LiveAudioRoute.choiceOf("nonsense"))
        assertEquals(MicChoice.PHONE, LiveAudioRoute.choiceOf("phone"))
        assertEquals(MicChoice.HEADSET, LiveAudioRoute.choiceOf("headset"))
    }

    /**
     * The numbers named in the pure file, checked against Android's own - a
     * wrong one would silently route nowhere. Java's compile-time constants
     * are inlined, so this runs without a device.
     */
    @Test
    fun `the platform numbers are Android's own`() {
        assertEquals(android.media.AudioManager.MODE_NORMAL, LiveAudioRoute.MODE_NORMAL)
        assertEquals(android.media.AudioManager.MODE_IN_CALL, LiveAudioRoute.MODE_IN_CALL)
        assertEquals(android.media.AudioManager.MODE_IN_COMMUNICATION, LiveAudioRoute.MODE_IN_COMMUNICATION)
        assertEquals(
            android.media.MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            LiveAudioRoute.SRC_VOICE_COMMUNICATION,
        )
        assertEquals(
            android.media.MediaRecorder.AudioSource.VOICE_RECOGNITION,
            LiveAudioRoute.SRC_VOICE_RECOGNITION,
        )
        assertEquals(android.media.AudioDeviceInfo.TYPE_BUILTIN_MIC, LiveAudioRoute.TYPE_BUILTIN_MIC)
        assertEquals(android.media.AudioDeviceInfo.TYPE_WIRED_HEADSET, LiveAudioRoute.TYPE_WIRED_HEADSET)
        assertEquals(android.media.AudioDeviceInfo.TYPE_BLUETOOTH_SCO, LiveAudioRoute.TYPE_BLUETOOTH_SCO)
        assertEquals(android.media.AudioDeviceInfo.TYPE_BLUETOOTH_A2DP, LiveAudioRoute.TYPE_BLUETOOTH_A2DP)
        assertEquals(android.media.AudioDeviceInfo.TYPE_USB_HEADSET, LiveAudioRoute.TYPE_USB_HEADSET)
        assertEquals(android.media.AudioDeviceInfo.TYPE_BLE_HEADSET, LiveAudioRoute.TYPE_BLE_HEADSET)
        assertEquals(android.media.AudioDeviceInfo.TYPE_BLE_SPEAKER, LiveAudioRoute.TYPE_BLE_SPEAKER)
    }

    // ---- the service uses it, and puts it back ---------------------------

    /**
     * The decision is only worth its tests if the microphone service actually
     * asks it. Read from the source, like the other contract tests here: the
     * failure this fixes was the service picking a recorder source by hand and
     * never putting the phone's audio mode back.
     */
    @Test
    fun `LiveService decides the route through this file and restores it`() {
        val root = listOf(File("src/main/java"), File("app/src/main/java"), File("jarvis-client/app/src/main/java"))
            .first { it.isDirectory }
        val service = File(root, "com/jarvis/client/service/LiveService.kt").readText()
        assertTrue("the listening path must ask the decision", service.contains("LiveAudioRoute.decide("))
        assertFalse(
            "the service must not choose a recorder source by hand any more",
            service.contains("MediaRecorder.AudioSource"),
        )
        assertTrue("the route must be put back when the microphone closes", service.contains("stopRoute()"))
        assertTrue("Live's own call mode must not read as a phone call", service.contains("ownMicCall"))
        assertTrue("a refused car must fall back, not record silence", service.contains("LiveAudioRoute.fallback("))

        val pure = File(root, "com/jarvis/client/voice/LiveAudioRoute.kt").readText()
        assertFalse(
            "no android.* in the decision, so the JVM tests run it",
            pure.contains("import android"),
        )
    }
}
