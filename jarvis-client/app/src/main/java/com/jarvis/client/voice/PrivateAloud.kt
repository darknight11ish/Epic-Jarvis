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
 *     and - only when [memoryMayRead] is false - no `injected_facts` above 0
 *     (remembered facts went into it). [memoryMayRead] is the PC's
 *     `memory_aloud`, OR the phone's own setting of 2026-11-05 read under
 *     the three facts below;
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
 * Otherwise it says one line, [ON_SCREEN] - or, when the remembered-facts
 * rule is the ONLY reason, [MEMORY_ON_SCREEN], which says what happened
 * (2026-11-05) - and the answer stays on the screen as always. The phone's
 * voice answers are spoken sentence by sentence as they arrive, so the rule
 * is asked again before EVERY sentence: a tool that starts halfway through
 * stops the reading there.
 *
 * THE PHONE'S OWN PROMISE, THE OWNER'S CHOICE OF 2026-11-05, widened on
 * 2026-11-07. The talk button deliberately runs no voice check (the owner's
 * request of 2026-11-02), so the PC's `memory_aloud` is ALWAYS false for it
 * (`jarvis_speech._QuickMessage`) and an answer that uses what Jarvis
 * remembers was always kept on screen - even on his own unlocked phone, with
 * his own setting on the PC saying memories may be read aloud. He chose a
 * setting ON THE PHONE for exactly that case: "read them aloud on my
 * unlocked phone". On 2026-11-07 he widened it - "i wanted to read everything
 * out loud ... unless it's extremely sensitive information it's okay" - so
 * the default is ON ([MEMORY_ALOUD_DEFAULT]) and it covers EVERY voice answer
 * on this phone: the mic press, "hey Jarvis" and Jarvis Live. It lifts ONLY
 * the remembered-facts refusal, and only when ALL of these hold:
 *
 *  - the phone was UNLOCKED at the moment of that press ([unlockedAtPress],
 *    captured then and never re-read: the owner's own instruction);
 *  - the answer used at least one remembered fact (`injected_facts` above 0)
 *    and NO sensitive one (`injected_sensitive` 0 - the fail-closed count
 *    above still refuses; health, money, passwords and other people's private
 *    details always stay on screen);
 *  - nothing else was private: not the question, not the router's gate, no
 *    screen read kept on screen, no private tool, the stream live throughout.
 *
 * The setting is a promise this phone makes about its own voice answers; a
 * TYPED answer is silent unless he taps Read out loud. Every other rule keeps
 * its place, which is why this is one branch of the same `when` and not a
 * second rule.
 *
 * AND ON A TYPED ANSWER, SINCE THE OWNER'S DECISION OF 2026-11-06. The same
 * phone setting now covers a TYPED answer read aloud on this unlocked phone
 * (`ReadAloud.Facts.phoneMemoryAloud`), under the same rule: only
 * remembered NON-sensitive facts, and only when nothing else is private. This
 * object is unchanged by that - the typed path has its own ladder because it
 * has no `Heard` reply - but the one switch now means one thing on both
 * paths, which is why the sentence it speaks ([MEMORY_ON_SCREEN]) is the same
 * sentence the typed strip shows. The other half of that day's decision, the
 * one-off "Read it aloud anyway" action, lives in `ReadAloud` too: it never
 * reaches this voice ladder, so an answer spoken sentence by sentence can
 * still never override anything.
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
     * What is said instead of an answer that used what Jarvis remembers, when
     * the ONLY reason it stays on screen is that rule (the refusal words of
     * 2026-11-05). A sentence that says what happened, rather than the bare
     * [ON_SCREEN]: the owner heard a memory answer kept on screen with no
     * explanation, and "It's on your screen." does not say why.
     *
     * Not a card line, not a shared line, and it never replaces [ON_SCREEN]:
     * the shared table (`contract/private-aloud-cases.json`, `on_screen`)
     * and the desktop's `private-speech.js` are untouched.
     */
    const val MEMORY_ON_SCREEN = "That answer used things I remember, so it's on your screen."

    /**
     * Names the phone's own switch, and nothing more: the words on its button
     * ("Read them out", [MemoryAloud.TURN_ON]) and where it lives. Said after
     * [MEMORY_ON_SCREEN] when the remembered-facts rule is the only reason AND
     * the phone setting is off - the owner's own report of 2026-11-06 was the
     * bare "It's on your screen." about an answer he expected to hear. Never a
     * reason beyond the one the first sentence gives, never the answer, never a
     * fact.
     *
     * The typed path keeps its own literal of the same words
     * (`ReadAloud.MEMORY_SWITCH_HINT`) for the same off-device reason as
     * [ON_SCREEN]; `ReadAloudWiringTest` pins that the two agree.
     */
    const val MEMORY_SWITCH_HINT = "To hear these every time, turn on \"Read them out\" in Voice settings."

    /**
     * The utterance reply's `mode` for the phone's mic press
     * (`jarvis_speech._QuickMessage`): the ONE clip that deliberately runs no
     * voice check (the owner's request of 2026-11-02). The phone's memory
     * setting of 2026-11-05 applies to that press and to nothing else, so
     * both the request's `source` and this word must agree.
     */
    const val QUICK_MESSAGE = "quick_message"

    /**
     * The phone setting's default, written down where the rule reads it: ON.
     * The owner's decision of 2026-11-07: remembered answers are read aloud by
     * default - including in Jarvis Live and after "hey Jarvis" - unless the
     * answer uses an EXTREMELY sensitive saved fact (health, money, passwords,
     * other people's private details), which still always stays on screen
     * (the sensitive rule of 2026-09-24 is unchanged). A typed answer is read
     * only when he asks for it; the chat can change this default back off any
     * time ("stop reading remembered answers out loud").
     */
    const val MEMORY_ALOUD_DEFAULT = true

    /**
     * Why an answer may not be read aloud, in the order the rules are asked.
     * [NONE] is the only value that may be spoken; every other one keeps the
     * answer on screen, and [MEMORY] is the one with its own words
     * ([MEMORY_ON_SCREEN]).
     */
    enum class Refusal {
        /** Nothing private: the answer may be read aloud. */
        NONE,

        /** A sensitive saved fact went into it and the owner did not allow those. */
        SENSITIVE,

        /** The screen (or, in Live, the camera) was read and this clip may not say it. */
        SCREEN,

        /** The PC's own words asked about something private. */
        QUESTION_PRIVATE,

        /** The router's own `gate: "private"`. */
        PRIVATE_GATE,

        /** It used what Jarvis remembers, and that is kept on screen. */
        MEMORY,

        /** A PRIVATE tool ran while it was written. */
        TOOL,

        /** The event stream could not say whether a tool ran. */
        TOOLS_UNKNOWN,

        /** No `X-Jarvis-Route` header has arrived yet: nothing is known. */
        NO_ROUTE,
    }

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
     * Reads the header, or null when there is no header and nothing readable to
     * read.
     *
     * This is the FAIL-CLOSED reader, and it exists because "the PC did not
     * say" and "the PC said this is fine" are different answers: a missing or
     * unreadable `X-Jarvis-Route` means the gate and the injected-fact counts
     * are UNKNOWN, and [com.jarvis.client.voice.ReadAloud.Facts.mayRead] must
     * refuse on unknown (docs/DECISIONS.md, 2026-10-27: "it refuses when the
     * route header is missing"). [route] answers [SILENT_ROUTE] instead, which
     * is right for the voice path - it still answers the question, it just must
     * not read a private answer aloud - and wrong for the typed read-aloud gate,
     * which used to test `route(header) != null` and so could never fail closed.
     *
     * `injected_sensitive` (the owner's decision of 2026-09-24: sensitive saved
     * facts stay on screen) FAILS CLOSED: when it is missing, or not a real
     * count, while `injected_facts` is above 0, every one of those facts counts
     * as possibly sensitive - a PC that does not say is not taken to mean
     * "none".
     */
    fun routeOrNull(header: String?): Route? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        val gate = (o["gate"] as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()?.lowercase()
        val facts = count(o, "injected_facts") ?: 0
        val sensitive = count(o, "injected_sensitive") ?: facts
        return Route(privateGate = gate == "private", injectedFacts = facts, injectedSensitive = sensitive)
    }

    /**
     * The answer's own turn id from `X-Jarvis-Route` (`turn_id`, feedback.patch),
     * or null when the header does not carry a real one. Used by the phone to
     * keep each finished TYPED answer's privacy facts under its own id, so that
     * answer's own menu can read THAT answer aloud later (2026-11-07) under the
     * same rules it was built with. Null is "not known", never a guessed id.
     */
    fun turnId(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return null
        val raw = (o["turn_id"] as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()
            ?: return null
        return raw.takeIf { Regex("^[0-9a-f]{32}$").matches(it) }
    }

    /**
     * Reads the header, answering [SILENT_ROUTE] when there is nothing readable
     * to read. For callers that need a value and treat "unknown" as "not
     * private"; the typed read-aloud gate needs the null and uses [routeOrNull].
     */
    fun route(header: String?): Route = routeOrNull(header) ?: SILENT_ROUTE

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
     * test) - and `read_web_page`, one page the owner handed over (the
     * owner's request of 2026-10-05, "post a webpage into jarvis and it can
     * read the content out loud"). It sits beside `web_search` rather than
     * beside email, calendar, notes or memory: both are the public web the
     * owner asked for, and the page's address is shown on a card before
     * anything is fetched. Every earlier rule still comes first - a sensitive
     * saved fact, a private question, the router's private gate, a forgotten
     * event stream - and a stale or dropped stream keeps the answer on screen
     * too. `feature_guide` is the PC's own shipped feature list (2026-11-01):
     * its answer is Jarvis's own words and its own switch states, never the
     * owner's data, so Live speaks it rather than saying "It's on your
     * screen." Exact names, as the `step` event carries them. The desktop's
     * `READ_ALOUD_TOOLS` (private-speech.js) and the shared table
     * (private-aloud-cases.json) are checked against this list by
     * PrivateAloudContractTest, so a name added to one of the three alone
     * fails a test.
     */
    val READ_ALOUD_TOOLS: Set<String> =
        setOf("home_read", "read_camera", "read_screen", "web_search", "read_web_page", "feature_guide")

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
     * @param phoneMemoryAloud the PHONE's own setting of 2026-11-05
     *   (`data/ClientSettings.readMemoriesAloud`, [MEMORY_ALOUD_DEFAULT]) -
     *   never a new default, and only ever consulted with the two facts below
     * @param talkButton this question came from the phone's mic press (not
     *   "hey Jarvis", not Jarvis Live)
     * @param unlockedAtPress the phone was unlocked AT THE PRESS (captured
     *   then, never re-read later)
     */
    fun mayRead(
        heard: com.jarvis.client.net.Heard,
        route: Route?,
        start: Watch,
        now: Watch,
        phoneMemoryAloud: Boolean = false,
        talkButton: Boolean = false,
        unlockedAtPress: Boolean = false,
    ): Boolean = mayRead(
        heard.privateAloud, heard.questionPrivate, route, toolRan(start, now), toolsKnown(start, now),
        memoryAloud = heard.memoryAloud,
        sensitiveAloud = heard.sensitiveAloud,
        screenRead = screenRead(start, now),
        screenAloud = heard.screenAloud,
        phoneMemoryAloud = phoneMemoryAloud,
        talkButton = talkButton,
        unlockedAtPress = unlockedAtPress,
    )

    /** Whether saved facts about a sensitive topic went into this answer ([route]'s fail-closed count). */
    fun usesSensitive(route: Route): Boolean = route.injectedSensitive > 0

    /**
     * Whether an answer that used remembered facts may be read aloud for this
     * clip. The PC's own answer (`memory_aloud`) is enough on its own, exactly
     * as before. The phone's setting is the ONLY other way: the setting on, the
     * phone unlocked at the press, and no screen read.
     *
     * IT COVERS EVERY VOICE ANSWER ON THIS PHONE since the owner's decision of
     * 2026-11-07 ("i wanted to read everything out loud ... unless it's
     * extremely sensitive information"): the mic press, "hey Jarvis" and Jarvis
     * Live. The [talkButton] argument is kept for the callers that still pass
     * it (and for the words said about the rule) but no longer gates this: it
     * used to, and that restriction is exactly what kept Live silent.
     * `usesSensitive` is asked BEFORE this in [refusal], so an extremely
     * sensitive fact still always stays on screen.
     */
    fun memoryMayRead(
        memoryAloud: Boolean,
        phoneMemoryAloud: Boolean,
        talkButton: Boolean,
        unlockedAtPress: Boolean,
        screenRead: Boolean,
    ): Boolean = memoryAloud || (phoneMemoryAloud && unlockedAtPress && !screenRead)

    /**
     * The whole rule, asked in order, answering WHY an answer stays on screen.
     * [mayRead] is this compared with [Refusal.NONE], so the decision and the
     * words said about it cannot drift apart.
     */
    fun refusal(
        privateAloud: Boolean,
        questionPrivate: Boolean,
        route: Route?,
        toolRan: Boolean,
        toolsKnown: Boolean,
        memoryAloud: Boolean = false,
        sensitiveAloud: Boolean = false,
        screenRead: Boolean = false,
        screenAloud: Boolean = false,
        phoneMemoryAloud: Boolean = false,
        talkButton: Boolean = false,
        unlockedAtPress: Boolean = false,
    ): Refusal = when {
        // Before the header, nothing is known - and nothing has arrived to read.
        route == null -> Refusal.NO_ROUTE
        // Sensitive saved facts stay on screen (the owner's decision,
        // 2026-09-24) unless the owner chose to hear them - even under
        // "voice check is enough" or "read aloud" for memories.
        usesSensitive(route) && !sensitiveAloud -> Refusal.SENSITIVE
        // An answer about the screen stays on screen unless the PC said
        // `screen_aloud` for this clip - false for "Hey Jarvis" under "Only
        // trust the talk button" unless the owner allowed it (the owner's
        // decision, 2026-09-28). Before "voice check is enough", so nothing
        // below lets it through.
        screenRead && !screenAloud -> Refusal.SCREEN
        // The owner chose "voice check is enough", and this voice passed it.
        privateAloud -> Refusal.NONE
        questionPrivate -> Refusal.QUESTION_PRIVATE
        route.privateGate -> Refusal.PRIVATE_GATE
        route.injectedFacts > 0 && !memoryMayRead(
            memoryAloud = memoryAloud,
            phoneMemoryAloud = phoneMemoryAloud,
            talkButton = talkButton,
            unlockedAtPress = unlockedAtPress,
            screenRead = screenRead,
        ) -> Refusal.MEMORY
        toolRan -> Refusal.TOOL
        !toolsKnown -> Refusal.TOOLS_UNKNOWN
        else -> Refusal.NONE
    }

    /** May the answer be read aloud? [refusal] == [Refusal.NONE], in one place. */
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
        phoneMemoryAloud: Boolean = false,
        talkButton: Boolean = false,
        unlockedAtPress: Boolean = false,
    ): Boolean = refusal(
        privateAloud = privateAloud,
        questionPrivate = questionPrivate,
        route = route,
        toolRan = toolRan,
        toolsKnown = toolsKnown,
        memoryAloud = memoryAloud,
        sensitiveAloud = sensitiveAloud,
        screenRead = screenRead,
        screenAloud = screenAloud,
        phoneMemoryAloud = phoneMemoryAloud,
        talkButton = talkButton,
        unlockedAtPress = unlockedAtPress,
    ) == Refusal.NONE

    /**
     * The one line said instead of the answer: [MEMORY_ON_SCREEN] when the
     * memory rule is the ONLY reason, and [ON_SCREEN] for every other refusal
     * (the other refusals keep their existing wording, the owner's instruction
     * of 2026-11-05).
     */
    fun refusalLine(refusal: Refusal): String =
        if (refusal == Refusal.MEMORY) MEMORY_ON_SCREEN else ON_SCREEN

    /**
     * The same line with the phone's memory setting in hand: when a
     * remembered-facts refusal is the reason AND the switch that would fix it is
     * OFF, the sentence names the switch after the one that says what happened
     * ([MEMORY_SWITCH_HINT]). Never for any other refusal, and never when the
     * switch is already on (then "turn it on" would be wrong). The first
     * sentence is unchanged, so the words the owner already knows still lead.
     */
    fun refusalLine(refusal: Refusal, phoneMemoryAloud: Boolean): String {
        val line = refusalLine(refusal)
        return if (refusal == Refusal.MEMORY && !phoneMemoryAloud) "$line $MEMORY_SWITCH_HINT" else line
    }
}
