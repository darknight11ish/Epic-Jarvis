package com.jarvis.assistant.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Brings the link back after a reboot.
 *
 * Without this the foreground service only ever started from the HUD or the
 * assistant session, so a phone rebooted overnight had no socket open in the
 * morning and approval requests simply stopped arriving — with nothing on the
 * device to say so, because the HUD is the only surface that would have said it.
 *
 * `BOOT_COMPLETED` is one of the documented exemptions to the background
 * foreground-service start restriction, so starting the service from here is
 * allowed where a sticky restart would not be.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            -> {
                Log.i(TAG, "restarting link after ${intent.action}")
                JarvisForegroundService.start(context)
            }
        }
    }

    private companion object {
        const val TAG = "JarvisBoot"
    }
}
