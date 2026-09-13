package com.jarvis.assistant.service

import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionService
import android.speech.SpeechRecognizer
import com.jarvis.assistant.JarvisRuntime

/**
 * A VoiceInteractionService is only accepted by the platform when it also
 * declares a recognition service, so this exists to satisfy that contract.
 *
 * Recognition itself happens on the desktop: audio is streamed there and the
 * transcript comes back over the WebSocket, so there is no on-device result to
 * report. Callers that bind here are told the operation is unsupported rather
 * than being left waiting on a callback that will never fire.
 */
class JarvisRecognitionService : RecognitionService() {

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
    }

    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {
        // Route the audio to the desktop, then close the client out cleanly.
        JarvisRuntime.startMic()
        listener?.let {
            runCatching { it.readyForSpeech(Bundle.EMPTY) }
            runCatching { it.error(SpeechRecognizer.ERROR_CLIENT) }
        }
    }

    override fun onStopListening(listener: Callback?) {
        JarvisRuntime.stopMic()
    }

    override fun onCancel(listener: Callback?) {
        JarvisRuntime.stopMic()
    }
}
