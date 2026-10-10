package com.jarvis.client.data

/**
 * "Quick Settings tiles you choose" (the owner's choice of 2026-09-28,
 * "Phone conveniences"; docs/JARVIS-API.md section 81.2). Android cannot add a
 * tile at run time, so the app ships a fixed number of tile slots
 * ([SLOTS], `service/QuickTileService.kt`) and the owner gives each one ONE
 * action from the short, safe list below, in Settings -> Quick Settings tiles.
 * The idea is Home Assistant's Android app (Apache): fixed tile services plus
 * an assignment screen. No code was copied.
 *
 * THE SAFE LIST, and why it is short. Every action here is one the owner can
 * already do from the app with one tap and no approval card:
 *  - start a focus session (Brain -> Focus session's Start, 25 minutes),
 *  - a 10-minute timer (a plain timer needs no card, CLAUDE.md 2026-09-25),
 *  - "Open briefing" - only OPENS the app on the briefing; it never shows a
 *    word of it on the tile or the lock screen,
 *  - Stop everything (Home's button; it only makes Jarvis do less),
 *  - play or pause whatever is playing on the PC (no card, 2026-09-27).
 *
 * NEVER on a tile, whatever is added later: Approve or Deny (a card is read
 * in full, in the app, before it is decided), anything that clears a rush
 * latch, anything that approves or acts on several things at once, and
 * anything that raises an approval card (a tile has nowhere to show the
 * card's words). `QuickTilesTest` holds this list to exactly these five.
 *
 * Pure Kotlin, no Android types, so the JVM tests run every rule here.
 */
enum class TileAction(
    /** Saved on this phone ([ClientSettings.quickTiles]); never sent anywhere. */
    val wire: String,
    /**
     * This action's own words, from the PC's one list of the five safe
     * buttons (`jarvis_widgets.ACTIONS`). The home-screen widget's buttons on
     * BOTH apps draw exactly these, and `contract/widget-cases.json` holds the
     * two byte for byte ([JarvisWidgetsTest]) - so this string may not be
     * changed here alone.
     *
     * WHAT THE QUICK SETTINGS TILE DRAWS IS [QuickTiles.tileLabel], which is
     * this except where the shared word would promise something the tap does
     * not do ("Brief me").
     */
    val tileLabel: String,
    /** The choice's words in Settings - what this tile will do. */
    val choiceLabel: String,
    /**
     * Held while the link is stale or down (rule 4) - it asks the PC to DO
     * something. Stop everything is never held (it only stops things), and
     * "Open briefing" only opens the app.
     */
    val heldWhenStale: Boolean,
) {
    FOCUS("focus", "Focus session", "Focus session", heldWhenStale = true),
    TIMER("timer", "10-min timer", "10-min timer", heldWhenStale = true),
    // THE SHARED WORD STAYS "Brief me" AND THE TILE SAYS SOMETHING ELSE
    // (corrected 2026-10-10). A tile labelled "Brief me" that only opens the
    // app on the Briefing screen promises a briefing it never starts - the
    // owner tapped it and waited. It is NOT made to start one instead: the
    // briefing carries new senders' names, and a tile draws on a locked
    // screen, so starting one from here would put that on the lock screen.
    // The label is the smaller, honest change - and it has to be the TILE's
    // label, not this one: `tileLabel` is the PC's shared word for the
    // home-screen widget's buttons too (`jarvis_widgets.ACTIONS`,
    // contract/widget-cases.json), so changing it here alone would break that
    // contract - and changing it everywhere means the PC's own module, both
    // golden files and the desktop's widget-board.js. See [QuickTiles.tileLabel].
    BRIEF_ME("brief_me", "Brief me", "Open briefing", heldWhenStale = false),
    STOP_EVERYTHING("stop_everything", "Stop everything", "Stop everything", heldWhenStale = false),
    PC_PLAY_PAUSE("pc_play_pause", "Play/pause PC", "Play/pause PC", heldWhenStale = true),
    ;

    companion object {
        /** A saved choice, or null for "nothing" - and for anything unknown, never a guess. */
        fun fromWire(s: String?): TileAction? = entries.firstOrNull { it.wire == s }
    }
}

object QuickTiles {
    /** How many tile slots the app ships (three TileService classes in the manifest). */
    const val SLOTS = 3

    /** The timer tile's length. */
    const val TIMER_SECONDS = 600

    /** The focus tile's length: the Focus session plate's own default. */
    const val FOCUS_MINUTES = com.jarvis.client.net.Focus.DEFAULT_MINUTES

    const val TITLE = "Quick Settings tiles"

    /**
     * The link tile's own label ([com.jarvis.client.service.LinkTileService],
     * which draws it, and `res/values/strings.xml`'s `link_tile_label`, which
     * the manifest gives the same service so Android's tile editor and the
     * shade agree).
     *
     * IT NAMES THE TAP (corrected 2026-10-10). This tile used to be labelled
     * "Jarvis" - the app's own name - while its one tap mutes or unmutes
     * Jarvis's spoken interruptions ([muteCommand]). A tile labelled "Jarvis"
     * that silently mutes notifications is a trap: the owner taps the tile
     * with their name on it and Jarvis stops speaking to them. The subtitle
     * already says "Muted", so the label says what the tap does.
     */
    const val LINK_TILE_LABEL = "Mute Jarvis"

    const val HINT =
        "Up to three Jarvis tiles for the panel you pull down from the top of the " +
            "screen. Choose what each one does here, then add it: pull the panel down, " +
            "tap Edit (often a pencil), and drag \"Jarvis tile 1\", \"2\" or \"3\" into place."

    const val SAFETY =
        "Only small things are offered, all one tap in the app already. A tile can " +
            "never approve or deny a card. While the connection to your PC is catching " +
            "up, a tile that asks the PC to do something does nothing and says why; " +
            "Stop everything always works."

    const val LOCK_NOTE =
        "With App lock on: \"Open briefing\" opens Jarvis, which asks for your fingerprint " +
            "first. The timer, focus and play/pause tiles ask you to unlock the phone " +
            "first when it is locked. Stop everything never asks."

    const val NOTHING = "Nothing"

    // The tile's second line.
    const val SUB_READY = "Jarvis"
    const val SUB_OFFLINE = "Offline"
    const val SUB_STALE = "Catching up"
    const val SUB_UNPAIRED = "Not paired"
    const val SUB_CHOOSE = "Tap to choose"
    const val UNASSIGNED_LABEL = "Jarvis tile"

    /**
     * What the briefing slot draws, because the shared word would lie: tapping
     * it opens the app on the Briefing screen and does not start one
     * ([Decision.OpenBriefing], [TileAction.BRIEF_ME]). A tile is read in a
     * pulled-down shade on a locked screen, so the label is the only thing
     * telling the owner what the tap will do - "Brief me" reads as "start one
     * now", and the owner waits for a briefing that is not coming.
     */
    const val OPEN_BRIEFING = "Open briefing"

    /**
     * What one tile draws as its label. [TileAction.tileLabel] is the PC's own
     * shared word for the five safe buttons - the home-screen widget's buttons
     * draw those, byte for byte the same on both apps
     * (`contract/widget-cases.json`) - so a tile whose shared word would
     * promise something the tap does not do is corrected HERE, on this
     * surface, and the shared list is left alone.
     */
    fun tileLabel(action: TileAction?, slot: Int): String = when (action) {
        null -> "$UNASSIGNED_LABEL ${slot + 1}"
        TileAction.BRIEF_ME -> OPEN_BRIEFING
        else -> action.tileLabel
    }

    /** What a tap does - [decide]'s answer. */
    sealed interface Decision {
        /** Do the action now. */
        data object Run : Decision

        /** Ask Android to unlock the phone first, then do it (App lock on, phone locked). */
        data object UnlockThenRun : Decision

        /** Open Jarvis on the briefing: App lock, if on, asks first. */
        data object OpenBriefing : Decision

        /** No action chosen for this slot: open Settings at this section. */
        data object OpenChooser : Decision

        /** Not paired, or the link is down: start the link and open the app, like the link tile. */
        data object Reconnect : Decision

        /** The link is up but catching up: nothing is sent; [why] is said. */
        data class Held(val why: String) : Decision
    }

    /**
     * What one tap on a tile does. [staleWords]: the plain words both apps
     * use for a link that is catching up (PlainErrors "link_stale").
     *
     * Order matters: an unchosen slot opens the chooser whatever the link
     * says; "Open briefing" always just opens the app; Stop everything always
     * runs (it stops this phone's own speech even with no link at all, and
     * asking the PC to stop is never held); everything else needs a live,
     * fresh link (rule 4) and, with App lock on and the phone locked, a phone
     * unlock.
     */
    fun decide(
        action: TileAction?,
        paired: Boolean,
        connected: Boolean,
        stale: Boolean,
        appLock: Boolean,
        phoneLocked: Boolean,
        staleWords: String,
    ): Decision = when {
        action == null -> Decision.OpenChooser
        action == TileAction.BRIEF_ME -> Decision.OpenBriefing
        !paired -> Decision.Reconnect
        action == TileAction.STOP_EVERYTHING -> Decision.Run
        !connected -> Decision.Reconnect
        stale && action.heldWhenStale -> Decision.Held(staleWords)
        appLock && phoneLocked -> Decision.UnlockThenRun
        else -> Decision.Run
    }

    /**
     * A HOME-SCREEN WIDGET button only, never a tile (the owner, 2026-09-28:
     * "under App lock, the widgets' buttons open the locked app first ...
     * they do not act on their own"). True when this button must open Jarvis
     * - which asks for the unlock - instead of doing anything: App lock is
     * on (or cannot be read: [appLock] null fails closed). Stop everything is
     * the one exception, as everywhere else here: it only makes Jarvis do
     * less, so it is never put behind an unlock. "Open briefing" already only
     * opens the app. Tiles keep [decide]'s own rule (they can ask Android for
     * the phone's unlock; a widget cannot).
     */
    fun widgetOpensApp(action: TileAction, appLock: Boolean?): Boolean = when (action) {
        TileAction.STOP_EVERYTHING -> false
        TileAction.BRIEF_ME -> true
        else -> appLock != false
    }

    /**
     * The link tile's Mute / Unmute tap ([com.jarvis.client.service.LinkTileService])
     * with App lock on and the phone locked asks Android for the phone's unlock
     * first, like every other tile ([decide]'s UnlockThenRun). App lock null
     * (cannot be read) fails closed.
     */
    fun muteNeedsUnlock(appLock: Boolean?, phoneLocked: Boolean): Boolean = appLock != false && phoneLocked

    /**
     * What one tap on the link tile sends - true to mute, false to unmute -
     * or null when the tap must do nothing at all.
     *
     * [shown] is what the tile is drawing now (`attention.muted`, which only
     * moves when the PC answers a re-read). [asked] is a mute the owner has
     * already asked for that no re-read has settled yet.
     *
     * The tile is a two-way toggle, and it used to send the same command
     * twice: `muted` does not change until the round trip lands, so a quick
     * second tap read the same old value and sent "mute" again - tap once to
     * mute, tap again, still muted (Android audit 2026-10-08). A tap inside
     * that round trip is now dropped rather than queued: the tile goes dark
     * the moment the first one is sent, so the second tap was aimed at a tile
     * already showing the new state.
     *
     * Once the re-read agrees, [shown] has caught up with [asked] and the
     * next tap is a real toggle again - which is why the guard is
     * `asked != shown` and not "a request is in flight": a state the PC has
     * already confirmed is settled, whatever is still on its way back.
     */
    fun muteCommand(shown: Boolean, asked: Boolean?): Boolean? = when {
        asked != null && asked != shown -> null
        else -> !shown
    }

    /** Said when a widget button is tapped under App lock before the widget redrew. */
    const val WIDGET_LOCKED = "App lock is on - open Jarvis first, then use it there."

    /** Whether the tile shows as lit (ready to use now) or dimmed. */
    fun ready(action: TileAction?, paired: Boolean, connected: Boolean, stale: Boolean): Boolean = when {
        action == null -> false
        action == TileAction.BRIEF_ME -> paired
        action == TileAction.STOP_EVERYTHING -> paired
        else -> paired && connected && !(stale && action.heldWhenStale)
    }

    /** The tile's second line. */
    fun subtitle(action: TileAction?, paired: Boolean, connected: Boolean, stale: Boolean): String = when {
        action == null -> SUB_CHOOSE
        !paired -> SUB_UNPAIRED
        action == TileAction.BRIEF_ME -> SUB_READY
        !connected -> SUB_OFFLINE
        stale && action.heldWhenStale -> SUB_STALE
        else -> SUB_READY
    }

    /** The body of the timer tile's `POST /api/schedule/add`: one plain timer, no words. */
    fun timerBody(): String = "{\"kind\":\"timer\",\"seconds\":$TIMER_SECONDS}"

    const val TIMER_SET = "10-minute timer set on your PC."

    /**
     * Play or pause, from the PC's own "what's playing" sentence
     * (`jarvis_media.now_playing`: "Playing: ..." or "Paused: ..."): pause
     * when it says something is playing, play otherwise - nothing playing,
     * paused, or the PC could not say. The worst a misread can do is ask
     * for play when it was already playing, which changes nothing.
     */
    fun playPauseAction(said: String?): String =
        if (said?.trimStart()?.startsWith("Playing:") == true) {
            com.jarvis.client.net.PcMedia.PAUSE
        } else {
            com.jarvis.client.net.PcMedia.PLAY
        }

    /**
     * The words shown after a tile's action (a short toast, and the app's
     * notice). [private]: App lock is on, or the phone is locked - then a
     * fixed sentence instead of the PC's own words for the focus session and
     * Stop everything (the PC's sentence can name what it stopped, or what a
     * session is on). A refusal (why it was not done) is never private: it
     * names only the link or the PC. The media button's words are always the
     * PC's own - `jarvis_media.control` answers only from a fixed list
     * ("Paused.", "Nothing seems to be playing right now."), never a title.
     */
    fun shown(action: TileAction, ok: Boolean, said: String, private: Boolean): String = when {
        !ok -> said
        !private -> said
        else -> when (action) {
            TileAction.FOCUS -> "Focus session started. Open Jarvis for the details."
            TileAction.TIMER -> TIMER_SET
            TileAction.STOP_EVERYTHING -> "Stop everything sent. Open Jarvis to see what stopped."
            TileAction.PC_PLAY_PAUSE -> said
            TileAction.BRIEF_ME -> said
        }
    }

    /** The saved slots, always [SLOTS] long; a missing or unknown entry is "nothing". */
    fun slotsFrom(read: (Int) -> String?): List<TileAction?> =
        (0 until SLOTS).map { TileAction.fromWire(read(it)) }
}
