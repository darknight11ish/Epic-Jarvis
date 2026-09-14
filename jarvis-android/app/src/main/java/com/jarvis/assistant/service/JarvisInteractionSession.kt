package com.jarvis.assistant.service

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService
import android.util.Log
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.MainActivity

/** Factory the platform calls to spin up an assistant session. */
class JarvisInteractionSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession =
        JarvisInteractionSession(this)
}

/**
 * The assistant session itself.
 *
 * Rather than draw a system overlay, this hands straight off to the HUD with the
 * microphone already live — the useful thing on a power-button press is to be
 * talking to the desktop, not to look at a translucent panel.
 */
class JarvisInteractionSession(context: Context) : VoiceInteractionSession(context) {

    private val appContext = context.applicationContext

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(appContext)
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        Log.i(TAG, "assistant session shown (flags=$showFlags)")

        JarvisRuntime.connect()
        JarvisForegroundService.start(appContext)

        val intent = Intent(appContext, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            action = MainActivity.ACTION_START_LISTENING
        }
        runCatching { startAssistantActivity(intent) }
            .onFailure { appContext.startActivity(intent) }

        hide()
    }

    override fun onHide() {
        super.onHide()
        Log.i(TAG, "assistant session hidden")
    }

    companion object {
        private const val TAG = "JarvisSession"
    }
}
