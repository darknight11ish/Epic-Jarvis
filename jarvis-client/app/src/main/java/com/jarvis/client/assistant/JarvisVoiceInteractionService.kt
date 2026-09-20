package com.jarvis.client.assistant

import android.service.voice.VoiceInteractionService

/**
 * The service `RoleManager.ROLE_ASSISTANT` actually binds to. No overrides:
 * everything this app does with the role happens in
 * [JarvisVoiceInteractionSession], reached through
 * [JarvisVoiceInteractionSessionService] via the `sessionService` this
 * class's own manifest metadata (`res/xml/voice_interaction_service.xml`)
 * names. This class exists because the role and the manifest schema require
 * it to, not because it does anything itself.
 */
class JarvisVoiceInteractionService : VoiceInteractionService()
