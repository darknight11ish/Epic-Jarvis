package com.jarvis.client.service

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.data.QuickTiles
import com.jarvis.client.data.TileAction
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.PlainErrors
import com.jarvis.client.net.StopEverything
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * One of the Quick Settings tile slots the owner fills in Settings -> Quick
 * Settings tiles ([QuickTiles], docs/JARVIS-API.md section 81.2). Android
 * cannot add a tile while the app runs, so there are exactly
 * [QuickTiles.SLOTS] of these, one class per slot ([QuickTileOneService],
 * [QuickTileTwoService], [QuickTileThreeService]), each in the manifest.
 *
 * NOT a second link tile. [LinkTileService] stays what it is (the link's
 * state and Mute); none of the actions here is Mute, so the two never do the
 * same job.
 *
 * The lifecycle is [LinkTileService]'s, copied: one collector per
 * `onStartListening`, cancelled in `onStopListening` and `onDestroy`. The
 * action itself runs on the runtime's long-lived scope
 * ([JarvisRuntime.launchDetached]), not this one: Android may unbind the
 * tile the moment the panel closes, and that must not cut a request off
 * half way.
 *
 * A tile that is not ready is [Tile.STATE_INACTIVE], never
 * [Tile.STATE_UNAVAILABLE] - SystemUI sends no taps to an unavailable tile,
 * and the tap is what reconnects (the same reasoning as [LinkTileService]).
 * What a tap does is decided by [QuickTiles.decide], which the JVM tests
 * hold: never Approve or Deny, held on a stale link (rule 4) except Stop
 * everything, and with App lock on a phone unlock first when the phone is
 * locked.
 */
abstract class QuickTileService(private val slot: Int) : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onStartListening() {
        super.onStartListening()
        // SystemUI can re-request listening without an onStopListening in
        // between; never two collectors on one Tile.
        watcher?.cancel()
        JarvisRuntime.initialize(this)

        watcher = scope.launch {
            combine(
                JarvisRuntime.link,
                JarvisRuntime.stale,
                JarvisRuntime.settings.quickTiles,
            ) { link, stale, tiles -> Triple(link, stale, tiles.getOrNull(slot)) }
                .collect { (link, stale, action) ->
                    render(action, link == LinkState.CONNECTED, stale)
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
        scope.cancel()
        super.onDestroy()
    }

    override fun onClick() {
        super.onClick()
        JarvisRuntime.initialize(this)
        val action = JarvisRuntime.settings.quickTiles.value.getOrNull(slot)
        val paired = JarvisRuntime.isPaired()
        val decision = QuickTiles.decide(
            action = action,
            paired = paired,
            connected = JarvisRuntime.link.value == LinkState.CONNECTED,
            stale = JarvisRuntime.stale.value,
            appLock = JarvisRuntime.settings.security.value.appLock,
            phoneLocked = isLocked,
            staleWords = PlainErrors.shown("link_stale").text,
        )
        when (decision) {
            QuickTiles.Decision.OpenChooser -> openApp(MainActivity.ACTION_OPEN_TILE_SETTINGS)
            QuickTiles.Decision.OpenBriefing -> openApp(MainActivity.ACTION_OPEN_BRIEFING)
            QuickTiles.Decision.Reconnect -> {
                // The link tile's offline tap, exactly: start the link, open the app.
                if (paired) EventService.start(this)
                openApp(null)
            }
            is QuickTiles.Decision.Held -> say(applicationContext, decision.why)
            QuickTiles.Decision.UnlockThenRun -> if (action != null) {
                // Android asks for the phone's own unlock and runs this only
                // once it succeeds; dismissed, nothing is done.
                unlockAndRun { perform(applicationContext, action) }
            }
            QuickTiles.Decision.Run -> if (action != null) perform(applicationContext, action)
        }
    }

    private fun render(action: TileAction?, connected: Boolean, stale: Boolean) {
        val tile = qsTile ?: return
        val paired = JarvisRuntime.isPaired()
        tile.state = if (QuickTiles.ready(action, paired, connected, stale)) {
            Tile.STATE_ACTIVE
        } else {
            Tile.STATE_INACTIVE
        }
        // The label is the tile's OWN words ([QuickTiles.tileLabel]): the tile
        // used to draw the PC's shared button word, which for the briefing
        // slot promised a briefing the tap does not start.
        tile.label = QuickTiles.tileLabel(action, slot)
        // minSdk is 33, so the subtitle (API 29) is always there.
        tile.subtitle = QuickTiles.subtitle(action, paired, connected, stale)
        tile.updateTile()
    }

    private fun openApp(action: String?) {
        val intent = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (action != null) intent.action = action
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // The Intent overload was deprecated at API 34 in favour of this one.
            startActivityAndCollapse(
                PendingIntent.getActivity(
                    this,
                    REQUEST_BASE + slot,
                    intent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                ),
            )
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }

    // Internal, not private, since 2026-09-28: the home-screen "Jarvis
    // widget" buttons (widget/JarvisBoardWidget.kt) run the SAME actions
    // through the same [perform], so the two can never drift apart.
    internal companion object {
        /** Distinct from the link tile's request code 0, one per slot. */
        private const val REQUEST_BASE = 0x51

        private val main = Handler(Looper.getMainLooper())

        /**
         * The action itself, on the runtime's scope. Each runtime call holds
         * itself on a stale link again (the link may have gone stale while a
         * phone unlock was on screen); Stop everything is never held.
         */
        fun perform(app: Context, action: TileAction) {
            JarvisRuntime.launchDetached {
                // Read when it runs, after any unlock: App lock on, or the
                // phone still locked, keeps the PC's own words off the toast.
                val private = JarvisRuntime.settings.security.value.appLock || phoneLocked(app)
                val (ok, said) = when (action) {
                    TileAction.FOCUS -> JarvisRuntime.focusStart(QuickTiles.FOCUS_MINUTES, "")
                    TileAction.TIMER -> JarvisRuntime.addTileTimer()
                    TileAction.PC_PLAY_PAUSE -> {
                        val blocked = JarvisRuntime.actionBlocker()
                        if (blocked != null) {
                            false to blocked
                        } else {
                            val next = QuickTiles.playPauseAction(JarvisRuntime.pcMedia())
                            true to JarvisRuntime.pcMediaControl(next)
                        }
                    }
                    TileAction.STOP_EVERYTHING -> when (val r = JarvisRuntime.stopEverything()) {
                        is ApiResult.Ok -> true to StopEverything.describe(r.value, null)
                        is ApiResult.Failed -> false to StopEverything.describe(null, r.error)
                    }
                    // Never reaches here: QuickTiles.decide opens the app for it.
                    TileAction.BRIEF_ME -> return@launchDetached
                }
                val words = QuickTiles.shown(action, ok, said, private)
                JarvisRuntime.setNotice(words)
                say(app, words)
            }
        }

        fun phoneLocked(app: Context): Boolean =
            runCatching {
                app.getSystemService(android.app.KeyguardManager::class.java)?.isKeyguardLocked
            }.getOrNull() ?: true

        /**
         * A short toast: a tile has no room for a sentence. Android still
         * shows a plain-text toast from a service (only custom-view toasts
         * are refused from the background); the same words are also the
         * app's notice, so they are there when Jarvis is next opened.
         */
        fun say(app: Context, words: String) {
            main.post { runCatching { Toast.makeText(app, words, Toast.LENGTH_LONG).show() } }
        }
    }
}

/** Tile slot 1 ("Jarvis tile 1" in Android's tile editor). */
class QuickTileOneService : QuickTileService(0)

/** Tile slot 2. */
class QuickTileTwoService : QuickTileService(1)

/** Tile slot 3. */
class QuickTileThreeService : QuickTileService(2)
