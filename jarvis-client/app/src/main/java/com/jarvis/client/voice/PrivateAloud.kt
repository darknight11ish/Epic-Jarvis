package com.jarvis.client.voice

import com.jarvis.client.net.JarvisJson
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull

/**
 * "Private answers stay on screen" - the owner's rule, kept on the phone
 * when it SPEAKS (docs/JARVIS-API.md section 16, "What the apps must do
 * about private answers").
 *
 * An answer drawn from email, the calendar or notes is not read aloud
 * unless the question was typed or tapped on the owner's own unlocked
 * device - or the owner chose "voice check is enough". An answer that uses
 * what Jarvis remembers is read aloud by default (the owner's choice,
 * 2026-09-24), unless the owner keeps those on screen too (`memory_aloud`
 * false). For a
 * question that came by VOICE, with the PC's `private_aloud` false (and a
 * PC that does not send it counts as false), the phone reads the answer
 * aloud only when NOTHING says it is private:
 *
 *  1. the PC did not mark the question private (`question_private`);
 *  2. the chat answer's `X-Jarvis-Route` header has no `gate: "private"`,
 *     and - only when `memory_aloud` is false - no `injected_facts` above 0
 *     (remembered facts went into it);
 *  2b. and, whatever `private_aloud` and `memory_aloud` say, no SENSITIVE
 *     saved fact went into it (`injected_sensitive` above 0 - or missing
 *     while `injected_facts` is above 0, which fails closed) unless the
 *     reply's `sensitive_aloud` is true: the owner's decision of 2026-09-24,
 *     "sensitive saved facts stay on screen", with a voice setting to allow
 *     it (`sensitive_memory` on the Voice check screen);
 *  3. no PRIVATE tool ran while it was being written (the `step` event,
 *     `tool_started` / `tool_finished`) - and that is only known while the
 *     event stream is live, so an unknown counts as "a private tool may
 *     have run". A tool is private unless its name is on
 *     [READ_ALOUD_TOOLS]: web search and home status (the owner's decision
 *     of 2026-09-27; weather is read from home status). Email, calendar,
 *     notes, files, memory, "unknown", a step with no name and any tool
 *     added later stay private. Both apps are held to one table,
 *     `contract/private-aloud-cases.json` (tools/gen_private_aloud_cases.py).
 *  2c. and, right after 2b and before anything can say "read aloud", an
 *     answer about the SCREEN (`read_screen` ran) is kept on screen unless
 *     the reply's `screen_aloud` is true: the owner's decision of
 *     2026-09-28, "under 'Only trust the talk button', screen answers stay
 *     on screen", with a voice setting to allow it (`hands_free_screen` on
 *     the Voice check screen). Missing counts as false.
 *
 * Otherwise it says one fixed line, [ON_SCREEN], and the answer stays on
 * the screen as always. The phone's voice answers are spoken sentence by
 * sentence as they arrive, so the rule is asked again before EVERY
 * sentence: a tool that starts halfway through stops the reading there.
 *
 * Known gap, said plainly (the same one the API doc names): the PC cannot
 * yet label a finished answer as private, and the header is sent before the
 * model starts. This is the phone's best information until it can.
 *
 * Pure, no Android: `PrivateAloudTest`.
 */
object PrivateAloud {

    /** What is said instead of a private answer. */
    const val ON_SCREEN = "It's on your screen."

    /**
     * What the chat answer's `X-Jarvis-Route` header says about privacy.
     * [injectedSensitive] is how many of the [injectedFacts] are about a
     * sensitive topic (health, money, passwords, other people's private details) - see [route]
     * for a header that does not say.
     */
    data class Route(val privateGate: Boolean, val injectedFacts: Int, val injectedSensitive: Int = 0)

    /** No header, or one that cannot be read: it says nothing either way. */
    val SILENT_ROUTE = Route(privateGate = false, injectedFacts = 0)

    /**
     * Reads the header. `injected_sensitive` (the owner's decision of
     * 2026-09-24: sensitive saved facts stay on screen) FAILS CLOSED: when it
     * is missing, or not a real count, while `injected_facts` is above 0,
     * every one of those facts counts as possibly sensitive - a PC that does
     * not say is not taken to mean "none".
     */
    fun route(header: String?): Route {
        if (header.isNullOrBlank()) return SILENT_ROUTE
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return SILENT_ROUTE
        val gate = (o["gate"] as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()?.lowercase()
        val facts = count(o, "injected_facts") ?: 0
        val sensitive = count(o, "injected_sensitive") ?: facts
        return Route(privateGate = gate == "private", injectedFacts = facts, injectedSensitive = sensitive)
    }

    /** A real, non-negative JSON number under [key], as a count (anything above 0 is at least 1); null otherwise. */
    private fun count(o: JsonObject, key: String): Int? {
        val d = (o[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() && it >= 0 } ?: return null
        return if (d > 0) d.coerceAtMost(1e6).toInt().coerceAtLeast(1) else 0
    }

    /**
     * The only tools whose answers may be read aloud to a voice question
     * (the owner's decision of 2026-09-27: web search, weather and home
     * status - weather is read with `home_read`, or answered with no tool
     * at all) - and `read_screen`, an answer about the screen (the owner's
     * answer of 2026-09-28; a read the PC records, not a model tool) - and
     * `read_camera`, an answer about what the camera sees in Jarvis Live (the
     * owner's answer of 2026-09-28; off until the 12 GB card passes the photo
     * test) - and `read_web_page`, one page the owner handed over (the owner's
     * request of 2026-10-05, "post a webpage into jarvis and it can read the
     * content out loud"). It sits beside `web_search` rather than beside
     * email, calendar, notes or memory: both are the public web the owner
     * asked for, and the page's address is shown on a card before anything is
     * fetched. Every earlier rule still comes first - a sensitive saved fact,
     * a private question, the router's private gate, a forgotten event
     * stream. Exact names, as the `step` event carries them. The desktop's
     * `READ_ALOUD_TOOLS` (private-speech.js).
     */
    val READ_ALOUD_TOOLS: Set<String> =
        setOf("home_read", "read_camera", "read_screen", "web_search", "read_web_page")

    /**
     * What the phone knows about tools at one moment: how many `step`
     * events said a tool ran ([runs]), how many of those were PRIVATE tools
     * - not on [READ_ALOUD_TOOLS] ([privateRuns]; left out, every run counts
     * as private), how many of those were the screen being read, `read_screen`
     * ([screenRuns]; left out, every run counts as possibly the screen), how
     * many times the event stream has dropped ([drops]),
     * and whether it is live now ([live]). Two of these - one when the
     * question was asked, one now - say whether a private tool ran in
     * between, and whether the phone could have heard of it.
     */
    data class Watch(
        val runs: Long,
        val drops: Long,
        val live: Boolean,
        val privateRuns: Long = runs,
        val screenRuns: Long = runs,
    )

    /** A PRIVATE tool ran between [start] and [now]. */
    fun toolRan(start: Watch, now: Watch): Boolean = now.privateRuns != start.privateRuns

    /** The screen was read between [start] and [now]. The desktop's `screenReadBetween`. */
    fun screenRead(start: Watch, now: Watch): Boolean = now.screenRuns != start.screenRuns

    /** The stream was live at both moments and did not drop in between. */
    fun toolsKnown(start: Watch, now: Watch): Boolean = start.live && now.live && start.drops == now.drops

    /** Whether a `step` event says a tool ran (started, or finished). A refused tool did not run. */
    fun isToolRun(data: JsonElement?): Boolean {
        val phase = ((data as? JsonObject)?.get("phase") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return phase == "tool_started" || phase == "tool_finished"
    }

    /** A tool ran, and its answer stays on screen: its name is not on [READ_ALOUD_TOOLS], or it has none. */
    fun isPrivateToolRun(data: JsonElement?): Boolean {
        if (!isToolRun(data)) return false
        val tool = ((data as? JsonObject)?.get("tool") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return tool == null || tool !in READ_ALOUD_TOOLS
    }

    /** The read an answer about the screen records (jarvis_screen.SCREEN_TOOL). */
    const val SCREEN_READ = "read_screen"

    /** The read an answer about the camera records (jarvis_live.CAMERA_TOOL). */
    const val CAMERA_READ = "read_camera"

    /**
     * A `step` event says the screen - or, in Jarvis Live, the camera - was
     * read: a tool run named exactly [SCREEN_READ] or [CAMERA_READ]. Both keep
     * to the same rule (the owner's answer of 2026-09-28: camera answers are
     * read aloud like screen answers). The desktop's `isScreenRead`.
     */
    fun isScreenRead(data: JsonElement?): Boolean {
        if (!isToolRun(data)) return false
        val tool = ((data as? JsonObject)?.get("tool") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return tool == SCREEN_READ || tool == CAMERA_READ
    }

    /**
     * May the answer to a VOICE question be read aloud, sentence by sentence?
     *
     * @param privateAloud the utterance reply's `private_aloud` (false when missing)
     * @param questionPrivate the utterance reply's `question_private`
     * @param route the chat answer's header, or null before it has arrived
     *   (then there is nothing to read yet, so nothing is spoken yet either)
     * @param toolRan a `step` event said a PRIVATE tool ran since the question was asked
     * @param toolsKnown the event stream was live the whole time, so a tool
     *   that ran would have been heard of
     * @param memoryAloud the utterance reply's `memory_aloud` (false when missing)
     * @param sensitiveAloud the utterance reply's `sensitive_aloud` (false when
     *   missing): the owner chose "Read aloud" for answers that use sensitive
     *   saved facts, and this voice passed a real check
     * @param screenRead the screen was read (`read_screen`) since the question was asked
     * @param screenAloud the utterance reply's `screen_aloud` (false when
     *   missing): false for "Hey Jarvis" under "Only trust the talk button"
     *   unless the owner allowed answers about the screen aloud
     */
    fun mayRead(heard: com.jarvis.client.net.Heard, route: Route?, start: Watch, now: Watch): Boolean =
        mayRead(
            heard.privateAloud, heard.questionPrivate, route, toolRan(start, now), toolsKnown(start, now),
            memoryAloud = heard.memoryAloud,
            sensitiveAloud = heard.sensitiveAloud,
            screenRead = screenRead(start, now),
            screenAloud = heard.screenAloud,
        )

    /** Whether saved facts about a sensitive topic went into this answer ([route]'s fail-closed count). */
    fun usesSensitive(route: Route): Boolean = route.injectedSensitive > 0

    fun mayRead(
        privateAloud: Boolean,
        questionPrivate: Boolean,
        route: Route?,
        toolRan: Boolean,
        toolsKnown: Boolean,
        memoryAloud: Boolean = false,
        sensitiveAloud: Boolean = false,
        screenRead: Boolean = false,
        screenAloud: Boolean = false,
    ): Boolean = when {
        // Before the header, nothing is known - and nothing has arrived to read.
        route == null -> false
        // Sensitive saved facts stay on screen (the owner's decision,
        // 2026-09-24) unless the owner chose to hear them - even under
        // "voice check is enough" or "read aloud" for memories.
        usesSensitive(route) && !sensitiveAloud -> false
        // An answer about the screen stays on screen unless the PC said
        // `screen_aloud` for this clip - false for "Hey Jarvis" under "Only
        // trust the talk button" unless the owner allowed it (the owner's
        // decision, 2026-09-28). Before "voice check is enough", so nothing
        // below lets it through.
        screenRead && !screenAloud -> false
        // The owner chose "voice check is enough", and this voice passed it.
        privateAloud -> true
        questionPrivate -> false
        route.privateGate -> false
        route.injectedFacts > 0 && !memoryAloud -> false
        toolRan -> false
        !toolsKnown -> false
        else -> true
    }
}
