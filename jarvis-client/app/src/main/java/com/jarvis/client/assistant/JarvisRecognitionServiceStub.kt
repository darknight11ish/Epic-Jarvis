package com.jarvis.client.assistant

import android.content.Intent
import android.speech.RecognitionService
import android.speech.SpeechRecognizer

/**
 * A `RecognitionService` that recognises nothing, ever.
 *
 * This exists ONLY because Android's `<voice-interaction-service>` manifest
 * schema names a `recognitionService` alongside the `sessionService` -
 * omitting it risks the whole registration failing silently rather than
 * failing on the one attribute that is actually missing, which would be a
 * worse outcome than a schema field pointed at something inert. Nothing
 * anywhere in this app ever calls `SpeechRecognizer` against this class,
 * and it must never start to. `docs/ANDROID-REPLY-2026-09-15.md`: "No
 * client-side STT was ever built and none is planned." Every entry point
 * here errors immediately rather than attempting anything, so a future
 * caller that reaches this by mistake fails loudly instead of quietly
 * pretending to transcribe.
 */
class JarvisRecognitionServiceStub : RecognitionService() {

    override fun onStartListening(recognizerIntent: Intent?, listener: Callback) {
        runCatching { listener.error(SpeechRecognizer.ERROR_CLIENT) }
    }

    override fun onCancel(listener: Callback) {
        // Nothing was ever started; nothing to cancel.
    }

    override fun onStopListening(listener: Callback) {
        runCatching { listener.error(SpeechRecognizer.ERROR_CLIENT) }
    }
}
