package com.jarvis.client.assistant

import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService

/** Hands out [JarvisVoiceInteractionSession] - the platform's own required
 *  factory shape for a `VoiceInteractionService`, nothing more. */
class JarvisVoiceInteractionSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession =
        JarvisVoiceInteractionSession(this)
}
