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
 *  3. no tool ran while it was being written (the `step` event,
 *     `tool_started` / `tool_finished`) - and that is only known while the
 *     event stream is live, so an unknown counts as "a tool may have run".
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

    /** What the chat answer's `X-Jarvis-Route` header says about privacy. */
    data class Route(val privateGate: Boolean, val injectedFacts: Int)

    /** No header, or one that cannot be read: it says nothing either way. */
    val SILENT_ROUTE = Route(privateGate = false, injectedFacts = 0)

    fun route(header: String?): Route {
        if (header.isNullOrBlank()) return SILENT_ROUTE
        val o = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }.getOrNull()
            ?: return SILENT_ROUTE
        val gate = (o["gate"] as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()?.lowercase()
        val facts = (o["injected_facts"] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
            ?.takeIf { it.isFinite() } ?: 0.0
        return Route(privateGate = gate == "private", injectedFacts = if (facts > 0) facts.coerceAtMost(1e6).toInt().coerceAtLeast(1) else 0)
    }

    /**
     * What the phone knows about tools at one moment: how many `step`
     * events said a tool ran ([runs]), how many times the event stream has
     * dropped ([drops]), and whether it is live now ([live]). Two of these -
     * one when the question was asked, one now - say whether a tool ran in
     * between, and whether the phone could have heard of it.
     */
    data class Watch(val runs: Long, val drops: Long, val live: Boolean)

    fun toolRan(start: Watch, now: Watch): Boolean = now.runs != start.runs

    /** The stream was live at both moments and did not drop in between. */
    fun toolsKnown(start: Watch, now: Watch): Boolean = start.live && now.live && start.drops == now.drops

    /** Whether a `step` event says a tool ran (started, or finished). A refused tool did not run. */
    fun isToolRun(data: JsonElement?): Boolean {
        val phase = ((data as? JsonObject)?.get("phase") as? JsonPrimitive)?.takeIf { it.isString }?.content
        return phase == "tool_started" || phase == "tool_finished"
    }

    /**
     * May the answer to a VOICE question be read aloud, sentence by sentence?
     *
     * @param privateAloud the utterance reply's `private_aloud` (false when missing)
     * @param questionPrivate the utterance reply's `question_private`
     * @param route the chat answer's header, or null before it has arrived
     *   (then there is nothing to read yet, so nothing is spoken yet either)
     * @param toolRan a `step` event said a tool ran since the question was asked
     * @param toolsKnown the event stream was live the whole time, so a tool
     *   that ran would have been heard of
     * @param memoryAloud the utterance reply's `memory_aloud` (false when missing)
     */
    fun mayRead(heard: com.jarvis.client.net.Heard, route: Route?, start: Watch, now: Watch): Boolean =
        mayRead(
            heard.privateAloud, heard.questionPrivate, route, toolRan(start, now), toolsKnown(start, now),
            memoryAloud = heard.memoryAloud,
        )

    fun mayRead(
        privateAloud: Boolean,
        questionPrivate: Boolean,
        route: Route?,
        toolRan: Boolean,
        toolsKnown: Boolean,
        memoryAloud: Boolean = false,
    ): Boolean = when {
        // The owner chose "voice check is enough", and this voice passed it.
        privateAloud -> true
        questionPrivate -> false
        route == null -> false
        route.privateGate -> false
        route.injectedFacts > 0 && !memoryAloud -> false
        toolRan -> false
        !toolsKnown -> false
        else -> true
    }
}
