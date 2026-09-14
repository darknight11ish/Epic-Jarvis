package com.jarvis.client.service

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.jarvis.client.Activity
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * A quick-settings tile carrying the link's real state, and muting spoken
 * interruptions.
 *
 * **Not a power tile, and that is a gap rather than a choice.** §5 asks for
 * "quick-settings tile for power mode", but `JARVIS-API.md` §4 has no endpoint
 * that *sets* power — `/api/status` reports it and nothing writes it. A tile
 * that appeared to switch Jarvis to Quiet and silently did nothing would be
 * worse than no tile, so this does the thing the API actually supports:
 * `/api/attention/mute`, which stops spoken interruptions until tomorrow.
 *
 * The state is read from the event stream rather than inferred locally. That
 * matters for one specific reason: a Quiet the user set by hand survives being
 * spoken to and comes back `"held": true`, so a tile that assumed sending a
 * message made Jarvis active would disagree with the desktop.
 */
class LinkTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onStartListening() {
        super.onStartListening()
        // SystemUI can re-bind or re-request listening without an intervening
        // onStopListening, which would leave two collectors racing on one Tile.
        watcher?.cancel()
        JarvisRuntime.initialize(this)

        watcher = scope.launch {
            combine(
                JarvisRuntime.link,
                JarvisRuntime.activity,
                JarvisRuntime.attention,
            ) { link, activity, attention -> Triple(link, activity, attention) }
                .collect { (link, activity, attention) ->
                    render(link, activity, attention.blockedBy == "muted", attention.pending)
                }
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
        if (!JarvisRuntime.isPaired()) {
            openApp()
            return
        }
        if (JarvisRuntime.link.value != LinkState.CONNECTED) {
            // Nothing useful to toggle against a desktop we cannot reach.
            EventService.start(this)
            openApp()
            return
        }
        val muted = JarvisRuntime.attention.value.blockedBy == "muted"
        scope.launch { JarvisRuntime.setMuted(!muted) }
    }

    private fun render(
        link: LinkState,
        activity: Activity,
        muted: Boolean,
        pending: Int,
    ) {
        val tile = qsTile ?: return
        tile.state = when {
            link != LinkState.CONNECTED -> Tile.STATE_UNAVAILABLE
            muted -> Tile.STATE_INACTIVE
            else -> Tile.STATE_ACTIVE
        }
        tile.label = "Jarvis"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when {
                link != LinkState.CONNECTED -> "Offline"
                muted -> if (pending > 0) "Muted · $pending waiting" else "Muted"
                pending > 0 -> "$pending waiting"
                activity == Activity.THINKING -> "Thinking"
                activity == Activity.SPEAKING -> "Speaking"
                activity == Activity.LISTENING -> "Listening"
                else -> "Linked"
            }
        }
        tile.updateTile()
    }

    private fun openApp() {
        val intent = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // The Intent overload was deprecated at API 34 in favour of this one.
            startActivityAndCollapse(
                PendingIntent.getActivity(
                    this,
                    0,
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
