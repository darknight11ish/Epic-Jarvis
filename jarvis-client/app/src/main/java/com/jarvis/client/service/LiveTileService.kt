package com.jarvis.client.service

import android.app.PendingIntent
import android.content.Intent
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.voice.LiveExtras
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * The Jarvis Live Quick Settings tile (the owner's decision of 2026-09-28,
 * the Jarvis Live extras): start or end Live on this phone from the pulled-
 * down shade, with the minutes left while it is on ([LiveExtras.tile]).
 *
 * - END is done here, at once: never held, never a card - it only makes
 *   Jarvis do less (JarvisRuntime.liveEndNow).
 * - START opens the app on the Live screen and starts Live there
 *   (MainActivity.ACTION_START_LIVE): Android only lets a microphone service
 *   start from an app in front, App lock is asked first when it is on, and
 *   Live's own start rules apply unchanged (held on a stale link, refused
 *   until the owner's voice is trained). On a locked phone Android asks for
 *   the phone's unlock first (unlockAndRun).
 *
 * The minutes come from the status the Live watcher already reads once a
 * second while Live is on here; with Live off, the tile reads it once when
 * the shade opens. Nothing else: no polling of its own.
 */
class LiveTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onStartListening() {
        super.onStartListening()
        watcher?.cancel()
        JarvisRuntime.initialize(this)
        watcher = scope.launch {
            if (JarvisRuntime.isPaired() && JarvisRuntime.link.value == LinkState.CONNECTED &&
                !JarvisRuntime.liveOnHere()
            ) {
                // One read, so the tile says "On your PC" or "Off" truly.
                runCatching { JarvisRuntime.liveRead() }
            }
            combine(JarvisRuntime.liveStatus, JarvisRuntime.link) { st, link -> st to link }
                .collect { (st, link) -> render(LiveExtras.tile(st, link == LinkState.CONNECTED)) }
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
        scope.cancel()
        super.onDestroy()
    }

    override fun onClick() {
        super.onClick()
        if (!JarvisRuntime.isPaired()) {
            open(null)
            return
        }
        if (JarvisRuntime.liveOnHere()) {
            // Never held: ending only makes Jarvis do less.
            JarvisRuntime.liveEndNow("owner")
            return
        }
        if (isLocked) {
            unlockAndRun { open(MainActivity.ACTION_START_LIVE) }
        } else {
            open(MainActivity.ACTION_START_LIVE)
        }
    }

    private fun render(t: LiveExtras.Tile) {
        val tile = qsTile ?: return
        tile.state = if (t.on) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = LiveExtras.TILE_LABEL
        tile.subtitle = t.subtitle
        tile.contentDescription = "${LiveExtras.TILE_LABEL}, ${t.subtitle}"
        tile.updateTile()
    }

    private fun open(action: String?) {
        val intent = Intent(this, MainActivity::class.java)
            .apply {
                if (action != null) {
                    setAction(action)
                    // The proof MainActivity needs before it will start Live.
                    putExtra(
                        com.jarvis.client.InternalLaunch.EXTRA_PROOF,
                        com.jarvis.client.InternalLaunch.token(this@LiveTileService),
                    )
                }
            }
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        // minSdk 33: the PendingIntent overload is there from API 34; the
        // Intent one before it (deprecated at 34).
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startActivityAndCollapse(
                PendingIntent.getActivity(
                    this,
                    21,
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                ),
            )
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }
}
