package com.jarvis.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.core.content.ContextCompat
import com.jarvis.client.service.ApprovalNotifier
import com.jarvis.client.service.EventService

class JarvisApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val manager = ContextCompat.getSystemService(this, NotificationManager::class.java)
            ?: return

        manager.createNotificationChannel(
            NotificationChannel(
                EventService.CHANNEL_ID,
                getString(R.string.channel_link_name),
                // IMPORTANCE_LOW: the link notification is a status line, not an
                // alert. It is ongoing and permanent, so anything higher would
                // make the app a constant interruption about nothing.
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.channel_link_desc)
                setShowBadge(false)
            },
        )

        // Separate channel, and separately importance-controlled, so the link
        // line can stay silent for ever while a decision still makes a sound.
        // One channel could not do both, which is how the app ended up
        // announcing nothing at all.
        manager.createNotificationChannel(
            NotificationChannel(
                ApprovalNotifier.CHANNEL_ID,
                getString(R.string.channel_approval_name),
                // HIGH, not MAX: it makes a sound and heads-up, it does not take
                // over the screen. Nothing Jarvis asks for is worth a full-screen
                // intent, and an item that claims to be urgent is exactly the one
                // that should not be able to demand the whole display.
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = getString(R.string.channel_approval_desc)
                setShowBadge(true)
                enableVibration(true)
            },
        )
    }
}
