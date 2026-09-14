package com.jarvis.assistant.service

import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionService
import android.util.Log
import com.jarvis.assistant.JarvisRuntime

/**
 * Registers Jarvis as the system digital assistant.
 *
 * Selecting this app under Settings > Apps > Default apps > Digital assistant
 * routes the power-button long-press and the corner swipe here, which is what
 * makes the assistant reachable without unlocking or finding the launcher icon.
 */
class JarvisVoiceService : VoiceInteractionService() {

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        Log.i(TAG, "voice interaction service created")
    }

    override fun onReady() {
        super.onReady()
        // The link should already be warm by the time the user speaks.
        JarvisRuntime.connect()
    }

    override fun onLaunchVoiceAssistFromKeyguard() {
        super.onLaunchVoiceAssistFromKeyguard()
        showSession(Bundle.EMPTY, 0)
    }

    override fun onShutdown() {
        Log.i(TAG, "voice interaction service shutting down")
        super.onShutdown()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        return START_STICKY
    }

    companion object {
        private const val TAG = "JarvisVoice"
    }
}
