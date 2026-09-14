package com.jarvis.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.core.content.ContextCompat
import com.jarvis.client.service.EventService

class JarvisApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val manager = ContextCompat.getSystemService(this, NotificationManager::class.java)
        manager?.createNotificationChannel(
            NotificationChannel(
                EventService.CHANNEL_ID,
                getString(R.string.channel_link_name),
                // IMPORTANCE_LOW: the link notification is a status line, not an
                // alert. Approvals get their own channel when step 4 lands.
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.channel_link_desc)
                setShowBadge(false)
            },
        )
    }
}
