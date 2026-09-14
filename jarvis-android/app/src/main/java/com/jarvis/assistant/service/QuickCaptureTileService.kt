package com.jarvis.assistant.service

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.R
import com.jarvis.assistant.network.ConnectionState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * One-tap note capture from the notification shade.
 *
 * The tile doubles as a link indicator: active means the desktop is reachable,
 * so a glance at the shade answers "will this send or queue?" without opening
 * anything.
 */
class QuickCaptureTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onStartListening() {
        super.onStartListening()
        // SystemUI can re-bind or re-request listening without an intervening
        // onStopListening, which left two collectors racing on the same Tile.
        watcher?.cancel()
        JarvisRuntime.initialize(this)
        // The tile is only visible while listening, so the collector lives
        // exactly as long as anyone can see the result.
        watcher = scope.launch {
            JarvisRuntime.socket.state.collect(::render)
        }
    }

    override fun onStopListening() {
        watcher?.cancel()
        watcher = null
        super.onStopListening()
    }

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        super.onDestroy()
    }

    override fun onClick() {
        super.onClick()
        val intent = Intent(this, MainActivity::class.java).apply {
            action = MainActivity.ACTION_QUICK_CAPTURE
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }

        if (isLocked) {
            // Capture needs the keyboard, which the keyguard will not give us.
            unlockAndRun { launch(intent) }
        } else {
            launch(intent)
        }
    }

    private fun launch(intent: Intent) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // API 34 replaced the Intent overload; the older one throws here.
            val pending = PendingIntent.getActivity(
                this,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            startActivityAndCollapse(pending)
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }

    private fun render(state: ConnectionState) {
        val tile = qsTile ?: return
        tile.state = if (state == ConnectionState.CONNECTED) {
            Tile.STATE_ACTIVE
        } else {
            Tile.STATE_INACTIVE
        }
        tile.label = getString(R.string.tile_quick_capture)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when (state) {
                ConnectionState.CONNECTED -> getString(R.string.tile_subtitle_linked)
                ConnectionState.RECONNECTING -> getString(R.string.tile_subtitle_reconnecting)
                ConnectionState.OFFLINE -> getString(R.string.tile_subtitle_offline)
            }
        }
        tile.updateTile()
    }
}
