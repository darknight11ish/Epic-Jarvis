package com.jarvis.client.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Restarts the link after a reboot or an app update.
 *
 * The service is otherwise only ever started by the button on the readiness
 * screen, so a phone rebooted overnight had no connection in the morning and
 * nothing on the device said so.
 *
 * `BOOT_COMPLETED` is a documented exemption to the background
 * foreground-service start restriction, which is why this works where the sticky
 * restart the system performs on its own does not.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            -> {
                Log.i(TAG, "restarting link after ${intent.action}")
                EventService.start(context)
            }
        }
    }

    private companion object {
        const val TAG = "JarvisClientBoot"
    }
}
