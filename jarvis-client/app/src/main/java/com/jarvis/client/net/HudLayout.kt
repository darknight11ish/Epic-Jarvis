package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

/**
 * The phone's editable Home HUD: the one layout model (the Android `A1`-`A4`
 * slice of the editable-HUD design, 2026-10-22). No Android in this file, so
 * every rule runs on a plain JVM in `HudLayoutTest` - exactly the desktop's
 * `hud-layout.js` idea (docs/ARCHITECTURE.md section 8, H1/H2), adapted to
 * this screen's own geometry and card ids.
 *
 * WHAT IT IS, IN PLAIN WORDS. The Home screen is arranged in four ordered
 * sections - a top strip, a hero, the body and the bottom composer - and every
 * HOME CARD lives in one section in a chosen order. This module says which
 * cards exist, which arrangement each of the five built-in presets is, and how
 * an untrusted document (a hand-edited one, one pasted from a computer, an old
 * one) becomes a safe layout.
 *
 * THE CARD IDS ARE THE GENERATED CATALOGUE'S. Every ordinary card is one
 * `MenuCatalog` id this phone actually has (`Menu.phone == true`), so a card
 * can never name a menu this app does not have, and the hide/fold rules the
 * rest of the app already uses keep working. The four safety surfaces
 * (approvals, Live/Stop, the connection, the emergency stop) are fixed ids
 * here, not catalogue menus, because the catalogue is about tidying settings;
 * they are PROTECTED: no preset and no import may remove them (ruling 25's
 * phone equivalent), and a missing one is put back in its default section by
 * [normalize].
 *
 * INDICATORS ARE NOT CARDS. App lock, the rush latch and a stale event stream
 * are drawn whenever they apply and are never editable, never hidden, never
 * moved (ruling: a safety warning cannot be dismissed by a layout).
 *
 * NO FREE (x, y) GRID. On a phone the sections ARE the layout: the body takes
 * one column below [TWO_COLUMN_DP] dp and two above it, and the browser - here
 * Compose's own rows - does the reflow. `x`/`y` are therefore never stored; a
 * document that carries them is accepted and they are dropped.
 *
 * NO NEW DEPENDENCY. kotlinx.serialization is already this app's JSON layer
 * (`JarvisJson`), and the layout is built with it rather than a hand parser.
 */
object HudLayout {

    /** The version of the document shape this build reads and writes. */
    const val VERSION = 1

    /** The four ordered sections, in the order they are drawn. */
    const val TOP_STRIP = "top_strip"
    const val HERO = "hero"
    const val BODY = "body"
    const val COMPOSER = "composer"
    val SECTIONS = listOf(TOP_STRIP, HERO, BODY, COMPOSER)

    /** The narrowest width (dp) at which the body draws two columns. */
    const val TWO_COLUMN_DP = 600

    // ---- the safety surfaces (fixed ids; never hideable, never imported out)
    const val APPROVALS = "approvals"
    const val LIVE = "live"
    const val EMERGENCY_STOP = "emergency_stop"

    /**
     * Every card the Home HUD can draw. `menu` is the generated catalogue id
     * backing it (null for the fixed safety surfaces); [protected] cards may
     * never be hidden and are forced present by [normalize].
     */
    data class Card(
        val id: String,
        val title: String,
        val about: String,
        val section: String,
        val menu: String? = null,
        val safety: Boolean = false,
        val indicator: Boolean = false,
    )

    /** The always-drawn warnings: derived state, never a card, never editable. */
    val INDICATORS = listOf(
        Card("indicator.app-lock", "App lock is on", "Safety: it must never vanish from the screen.", TOP_STRIP, indicator = true),
        Card("indicator.rush-latch", "Text tried to rush you", "Safety: it must never vanish from the screen.", TOP_STRIP, indicator = true),
        Card("indicator.stale-stream", "The event stream is stale", "Safety: it must never vanish from the screen.", TOP_STRIP, indicator = true),
    )

    /**
     * The home cards, in their default section. The menu-backed ones are REAL
     * catalogue ids (the phone's own), so the same hiding and the same words
     * apply here as everywhere else.
     */
    val CARDS: List<Card> = listOf(
        // The three safety surfaces. Never hidden, never imported out.
        Card(APPROVALS, "Waiting for your yes", "The approvals queue: one card per tap.", TOP_STRIP, safety = true),
        Card(LIVE, "Live and Stop", "Talk back and forth, and the Stop button.", HERO, safety = true),
        Card(EMERGENCY_STOP, "Emergency stop", "Stops everything, at once. Never hidden.", TOP_STRIP, safety = true),
        // Ordinary cards: every one is a phone menu that already exists.
        Card("entry.appearance", "Appearance", "Theme, faces and how it all looks.", HERO, menu = "entry.appearance"),
        Card("entry.voice-check", "Voice check", "Say one line and hear how it sounds.", HERO, menu = "entry.voice-check"),
        Card("brain.now.right-now", "Right now", "What Jarvis is doing at this moment.", TOP_STRIP, menu = "brain.now.right-now"),
        Card("brain.now.budget", "Attention budget", "How much Jarvis may interrupt you today.", TOP_STRIP, menu = "brain.now.budget"),
        Card("brain.now.trace", "What Jarvis is doing", "The steps behind the last answer.", TOP_STRIP, menu = "brain.now.trace"),
        Card("brain.work.today", "Today", "Today's plan and what is left of it.", BODY, menu = "brain.work.today"),
        Card("brain.work.coming-up", "Coming up", "Timers, alarms, reminders and the to-do list.", BODY, menu = "brain.work.coming-up"),
        Card("brain.work.jobs", "Background jobs", "Work that outlives the conversation.", BODY, menu = "brain.work.jobs"),
        Card("brain.work.undo", "Undo shelf", "What can still be undone, in one tap.", BODY, menu = "brain.work.undo"),
        Card("brain.work.focus", "Focus session", "One job at a time, until the bell.", BODY, menu = "brain.work.focus"),
        Card("brain.work.quiz", "Quiz me on a text", "Questions made from your own words.", BODY, menu = "brain.work.quiz"),
        Card("brain.work.decks", "My study decks", "The fading-card decks and the radar.", BODY, menu = "brain.work.decks"),
        Card("brain.work.briefing", "Morning briefing", "The three lines worth reading first.", BODY, menu = "brain.work.briefing"),
        Card("brain.work.retirement", "Retirement what-if", "What the numbers look like later.", BODY, menu = "brain.work.retirement"),
        Card("brain.memory.learning", "Learning", "How much Jarvis remembers and whether it learns.", BODY, menu = "brain.memory.learning"),
        Card("brain.memory.topics", "Topics", "A mode for each topic of what Jarvis learns.", BODY, menu = "brain.memory.topics"),
        Card("brain.memory.profile", "Always keep in mind", "Facts pinned to every answer.", BODY, menu = "brain.memory.profile"),
        Card("brain.memory.wiki", "Wiki", "The wiki Jarvis builds from your notes.", BODY, menu = "brain.memory.wiki"),
        Card("brain.model.models", "Models", "Which model answers, and where it runs.", BODY, menu = "brain.model.models"),
        Card("brain.model.compute", "Compute", "What the cards are doing.", BODY, menu = "brain.model.compute"),
        Card("brain.model.skills", "Skills", "What Jarvis has been taught to do.", BODY, menu = "brain.model.skills"),
        Card("brain.trust.ledger", "Audit chain", "The record of what was approved and when.", BODY, menu = "brain.trust.ledger"),
        Card("brain.watch.watchlist", "GitHub watchlist", "Repos Jarvis watches for you.", BODY, menu = "brain.watch.watchlist"),
        Card("brain.projects.progress", "Progress", "How the projects are moving.", BODY, menu = "brain.projects.progress"),
        Card("settings.spending", "Spending", "Spending summaries from a bank file.", BODY, menu = "settings.spending"),
        Card("settings.hardware", "Hardware and models", "Your graphics cards and the three setups.", BODY, menu = "settings.hardware"),
        Card("settings.voice", "Voice", "Talk, read aloud, hands-free and sounds.", COMPOSER, menu = "settings.voice"),
        Card("settings.security", "Security", "App lock and Windows Hello or the screen lock.", COMPOSER, menu = "settings.security"),
    )

    private val byId: Map<String, Card> = CARDS.associateBy { it.id }
    private val indicators: Set<String> = INDICATORS.map { it.id }.toSet()

    fun card(id: String): Card? = byId[id]

    fun isProtected(id: String): Boolean = byId[id]?.safety == true

    /** The cards a section holds by default, in order. */
    fun defaultSection(section: String): List<String> =
        CARDS.filter { it.section == section }.map { it.id }

    /** The default layout: every card in its own home section. */
    fun defaults(): Layout = Layout(
        version = VERSION,
        sections = SECTIONS.associateWith { defaultSection(it) },
    )

    /** A layout: one ordered list of card ids per section. */
    data class Layout(
        val version: Int = VERSION,
        val sections: Map<String, List<String>> = emptyMap(),
    ) {
        fun items(section: String): List<String> = sections[section].orEmpty()
        fun sectionOf(id: String): String? =
            HudLayout.SECTIONS.firstOrNull { id in items(it) }
        fun contains(id: String): Boolean = sectionOf(id) != null
        fun visibleCards(): List<String> = HudLayout.SECTIONS.flatMap { items(it) }
    }

    // ------------------------------------------------------------------ presets

    /**
     * A named arrangement. The five built-ins are READ-ONLY data; the owner
     * gets a copy with [duplicateToCustom] and then edits that copy (A3).
     */
    data class Preset(
        val id: String,
        val title: String,
        val about: String,
        val builtIn: Boolean,
        val layout: Layout,
    )

    fun preset(id: String): Preset? = BUILT_IN_PRESETS.firstOrNull { it.id == id }

    /** Merge one arrangement's sections over an otherwise empty layout. */
    private fun arrangement(vararg parts: Pair<String, List<String>>): Layout {
        val map = SECTIONS.associateWith { mutableListOf<String>() }.toMutableMap()
        for ((section, ids) in parts) {
            if (section !in SECTIONS) continue
            map.getValue(section).addAll(ids)
        }
        return normalize(Layout(VERSION, map))
    }

    /**
     * The five built-in presets, in the order the picker draws them. They are
     * arrangements of the SAME cards declared above; [normalize] still forces
     * the protected ones in, so no preset can remove a safety surface.
     */
    val BUILT_IN_PRESETS: List<Preset> by lazy {
        listOf(
            Preset("default", "Default", "Everything in its usual place.", true,
                arrangement(
                    TOP_STRIP to listOf("brain.now.right-now", "brain.now.budget"),
                    HERO to listOf(LIVE, "brain.now.trace", "entry.appearance"),
                    BODY to listOf("brain.work.today", "brain.work.coming-up",
                        "brain.work.jobs", "brain.work.undo", "brain.model.models",
                        "brain.memory.learning"),
                    COMPOSER to listOf("settings.voice", "settings.security"),
                )),
            Preset("live", "Live & Voice", "Talk back and forth; everything else waits.", true,
                arrangement(
                    TOP_STRIP to listOf("brain.now.right-now"),
                    HERO to listOf(LIVE, "entry.voice-check", "brain.now.trace"),
                    BODY to listOf("brain.now.budget", "brain.work.focus"),
                    COMPOSER to listOf("settings.voice", "settings.security"),
                )),
            Preset("brain", "Brain & Learning", "Memory, models and study at the front.", true,
                arrangement(
                    TOP_STRIP to listOf("brain.memory.learning", "brain.model.models"),
                    HERO to listOf("entry.appearance", "brain.model.compute"),
                    BODY to listOf("brain.memory.topics", "brain.memory.profile",
                        "brain.memory.wiki", "brain.work.quiz", "brain.work.decks",
                        "brain.model.skills", "brain.trust.ledger"),
                    COMPOSER to listOf("settings.voice"),
                )),
            Preset("ops", "Everyday Ops", "Today, reminders, jobs and money, together.", true,
                arrangement(
                    TOP_STRIP to listOf("brain.work.today", "brain.work.coming-up"),
                    HERO to listOf("brain.work.undo", "brain.work.jobs"),
                    BODY to listOf("brain.work.briefing", "settings.spending",
                        "brain.watch.watchlist", "brain.work.retirement",
                        "brain.projects.progress"),
                    COMPOSER to listOf("settings.security"),
                )),
            Preset("calm", "Calm", "Only what is happening now.", true,
                arrangement(
                    TOP_STRIP to listOf("brain.now.right-now"),
                    HERO to listOf(LIVE),
                    BODY to listOf("brain.work.today", "brain.work.coming-up"),
                    COMPOSER to listOf("settings.security"),
                )),
        )
    }

    /** The cards in a layout that are not in this layout's own section order. */
    fun missingFrom(layout: Layout): List<String> {
        val have = layout.visibleCards().toSet()
        return CARDS.filter { !it.indicator && it.id !in have }.map { it.id }
    }

    // ----------------------------------------------------------------- reducer

    /** One edit to the layout - the SAME actions come from drag, buttons and TalkBack. */
    sealed interface Action {
        /** Put [id] in [section] at [index] (drag drop, or "move to" in the menu). */
        data class Move(val id: String, val section: String, val index: Int) : Action

        /** Move it one place earlier in its own section. */
        data class Earlier(val id: String) : Action

        /** Move it one place later in its own section. */
        data class Later(val id: String) : Action

        /** Put it first in a section (the target section when given). */
        data class First(val id: String, val section: String? = null) : Action

        /** Put it last in a section (the target section when given). */
        data class Last(val id: String, val section: String? = null) : Action

        /** The whole layout goes back to one built-in preset / the default. */
        data class ApplyPreset(val presetId: String) : Action

        /** Back to the default arrangement. */
        data object Reset : Action
    }

    /**
     * The one reducer every input calls. Refuses - and answers the SAME layout
     * back - when the edit would touch a protected card's presence or a
     * section that does not exist, so a drag, a button and a TalkBack action
     * cannot disagree (the desktop's ruling 23-27, mirrored).
     */
    fun apply(layout: Layout, action: Action): Layout = when (action) {
        is Action.Reset -> defaults()
        is Action.ApplyPreset ->
            BUILT_IN_PRESETS.firstOrNull { it.id == action.presetId }?.layout
                ?: normalize(layout)
        is Action.Move -> move(layout, action.id, action.section, action.index) ?: layout
        is Action.Earlier -> shift(layout, action.id, -1) ?: layout
        is Action.Later -> shift(layout, action.id, 1) ?: layout
        is Action.First -> place(layout, action.id, action.section) { 0 } ?: layout
        is Action.Last -> place(layout, action.id, action.section) { ids -> ids.size } ?: layout
    }

    /** Move one card; null when the edit is not allowed (unknown id, bad section). */
    fun move(layout: Layout, id: String, section: String, index: Int): Layout? {
        if (section !in SECTIONS) return null
        if (id !in byId || id in indicators) return null
        val from = layout.sectionOf(id) ?: return null
        val target = layout.items(section).toMutableList()
        val at = index.coerceIn(0, target.size)
        if (from == section) {
            // A no-op drop is not an edit.
            val current = target.indexOf(id)
            if (current < 0) return null
            if (at == current) return normalize(layout)
            target.removeAt(current)
            target.add(if (at > current) at - 1 else at, id)
        } else {
            target.add(at, id)
            val source = layout.items(from).toMutableList()
            source.remove(id)
            val map = layout.sections.toMutableMap()
            map[from] = source
            map[section] = target
            return normalize(Layout(layout.version, map))
        }
        return normalize(Layout(layout.version, layout.sections.toMutableMap().also { it[section] = target }))
    }

    /** One place earlier (-1) or later (+1); null when it cannot move. */
    private fun shift(layout: Layout, id: String, delta: Int): Layout? {
        val section = layout.sectionOf(id) ?: return null
        val ids = layout.items(section).toMutableList()
        val at = ids.indexOf(id)
        val to = at + delta
        if (at < 0 || to < 0 || to >= ids.size) return null
        ids.removeAt(at)
        ids.add(to, id)
        return normalize(Layout(layout.version, layout.sections.toMutableMap().also { it[section] = ids }))
    }

    /** "Move to the start/end of a section"; a null section means its own. */
    private fun place(
        layout: Layout,
        id: String,
        targetSection: String?,
        index: (List<String>) -> Int,
    ): Layout? {
        val section = targetSection ?: layout.sectionOf(id) ?: return null
        if (section !in SECTIONS) return null
        val ids = layout.items(section).toMutableList()
        if (section == layout.sectionOf(id) && ids.isNotEmpty()) {
            ids.remove(id)
            ids.add(index(ids), id)
            return normalize(Layout(layout.version, layout.sections.toMutableMap().also { it[section] = ids }))
        }
        return move(layout, id, section, index(ids))
    }

    // ----------------------------------------------------------- normalisation

    /**
     * An untrusted layout becomes a safe one. Closed world: a card id this
     * build does not have is dropped; a menu-backed card is dropped when the
     * generated catalogue says this app does not have that menu; an id
     * appearing twice keeps its first place; sections are put back in draw
     * order; a PROTECTED card is forced present and visible in its default
     * section; the always-drawn indicators can never be added to the document.
     * Old or missing versions read as the default (the version is what makes a
     * stored layout safe to trust at all).
     */
    fun normalize(layout: Layout): Layout {
        if (layout.version != VERSION) return defaults()
        val seen = mutableSetOf<String>()
        val map = LinkedHashMap<String, List<String>>()
        for (section in SECTIONS) {
            val ids = mutableListOf<String>()
            for (raw in layout.items(section)) {
                val card = byId[raw] ?: continue
                if (card.indicator) continue
                if (card.menu != null) {
                    val menu = MenuLogic.menu(card.menu)
                    if (menu == null || !menu.phone) continue
                }
                if (!seen.add(raw)) continue
                ids.add(raw)
            }
            map[section] = ids
        }
        // A protected card is never absent: put it back in its own section,
        // in the order it is declared in CARDS.
        for (card in CARDS.filter { it.safety }) {
            if (card.id in seen) continue
            map.getValue(card.section).toMutableList().let { list ->
                list.add(card.id)
                map[card.section] = list
            }
            seen.add(card.id)
        }
        return Layout(VERSION, SECTIONS.associateWith { map.getValue(it) })
    }

    /**
     * The hide rules the rest of the app already has, applied ON TOP of the
     * layout - so hiding a menu (by voice, or in Settings) still empties its
     * home card, and a protected card ignores hiding altogether.
     */
    fun visible(layout: Layout, view: MenuView,
                forcedVisible: Set<String> = emptySet()): Map<String, List<String>> =
        SECTIONS.associateWith { section ->
            layout.items(section).filter { id ->
                if (isProtected(id)) return@filter true
                val card = byId[id] ?: return@filter false
                val menu = card.menu ?: return@filter true
                view.shows(menu) || menu in forcedVisible
            }
        }

    /** How many columns the body uses at this width. */
    fun columnsAt(widthDp: Int): Int = if (widthDp >= TWO_COLUMN_DP) 2 else 1

    // ------------------------------------------------------- JSON (portability)

    /** The document another copy of the app may read. Sections only; never x/y. */
    fun toJson(layout: Layout): String = buildJsonObject {
        put("version", VERSION)
        put("sections", buildJsonObject {
            for (section in SECTIONS) {
                put(section, buildJsonArray {
                    for (id in layout.items(section)) add(JsonPrimitive(id))
                })
            }
        })
    }.toString()

    /**
     * A pasted or stored document, or null when it is not even an object.
     * Never throws; [normalize] does the safety, including the version check.
     */
    fun fromJson(json: String?): Layout? {
        if (json.isNullOrBlank()) return null
        val root = runCatching { JarvisJson.parseToJsonElement(json) as? JsonObject }.getOrNull()
            ?: return null
        val version = (root["version"] as? JsonPrimitive)?.takeIf { !it.isString }
            ?.intOrNull ?: return null
        val sections = root["sections"] as? JsonObject ?: return null
        val map = LinkedHashMap<String, List<String>>()
        for (section in SECTIONS) {
            val arr = sections[section] as? JsonArray ?: continue
            map[section] = arr.mapNotNull { el ->
                (el as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
            }
        }
        return normalize(Layout(version, map))
    }

    /**
     * A custom preset duplicated from any layout, with a plain title - the
     * owner's own copy that later edits go into (the built-ins never change).
     */
    fun copyAs(title: String, layout: Layout): Preset {
        val clean = title.trim().replace(Regex("\\s+"), " ").take(40)
        val slug = clean.lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-')
        // A title that cannot be an id still gets a safe id - and a readable
        // name, so a copy of the layout is never called "!!!".
        return Preset("custom." + slug.ifBlank { "preset" },
            if (slug.isBlank()) "My layout" else clean,
            "Your own copy.", false, normalize(layout))
    }
}
