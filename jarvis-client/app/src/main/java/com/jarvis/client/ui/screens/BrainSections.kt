package com.jarvis.client.ui.screens

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.Chevron
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii

/**
 * The headings on the phone's Brain, and which of them is open.
 *
 * The owner's words, 2026-10-10: "the brain on jarvis on the android phone is
 * way too long of a menu. Put different section headers, with a secondary menu
 * that opens for that item if i click on it."
 *
 * Before this, every plate was drawn one under another - about 38 of them, all
 * open at once - so the screen was a scroll several screens long, and the only
 * signs of where you were were three group headings ("Now", "Memory", "Model
 * and PC") that headed things but hid nothing. Now one heading holds several
 * plates, and a tap opens it.
 *
 * Two things live here and nothing else:
 *
 *  * [SECTIONS] - the headings, in the order they are drawn, and the `item(key
 *    = "...")` of [BrainScreen] each one holds. The screen reads this to draw
 *    the headings and to decide which plates to draw; nothing here draws a
 *    plate and nothing here touches the network, so `BrainSectionsTest` can
 *    hold it to the screen's real item keys on a plain JVM.
 *  * [Open] - which heading is open, and the rule that a link into Brain
 *    ("open the morning briefing", "show everything saved automatically")
 *    opens the heading it lands in, so nothing that used to be one tap away
 *    became unreachable.
 *
 * ## Why these headings
 *
 * The names are the owner's phrasing, not the PC's tab names, and each one is
 * a question the owner would ask rather than a place in the code:
 *
 *  * **Waiting for you** - the review queue. First, because it is the only
 *    heading on Brain that is waiting on the owner: everything else is
 *    something to look at, this one is a decision.
 *  * **What Jarvis knows about you** - the saved facts themselves: what it
 *    learned on its own, what is always kept in mind, "between us", the topics
 *    it may learn about, the people and things those facts name, the wiki,
 *    "what did I believe on this date?", and the chat history those facts and
 *    conversations are kept in.
 *  * **Money and time** - money (the spending summaries, the retirement
 *    what-if) and the clock (the morning briefing, what is on today, timers,
 *    alarms, reminders, the to-do list, and the home-screen widgets, which are
 *    one of these plates shown at a time). Grouped because all of them answer
 *    "what is coming, and what will it cost" at a glance rather than being
 *    worked in.
 *  * **What Jarvis is doing** - live state and the jobs that steer it: what it
 *    is doing, the tool steps, a chatbot or a support chat running now, a
 *    focus session, the background jobs, the job list, the GitHub watch list,
 *    and what it noticed on its own.
 *  * **Your projects and goals** - the long-running work: projects, their
 *    progress, and goals with their steps.
 *  * **Your learning** - the quizzes and the study decks kept from them. Its
 *    own heading rather than part of the projects, because a deck is practised
 *    on the PC's schedule and has a right answer, where a project is worked on
 *    and has a goal.
 *  * **Jarvis on your PC** - the machine Jarvis runs on and the way into the
 *    rest of the app: the model, the graphics cards and compute plan, its
 *    skills, the audit chain, what this backend supports, the deep questions,
 *    PC help, the tutorials, "everything Jarvis can do", and Settings.
 *
 * Seven headings for the whole screen. Every plate keeps its own `item(key =
 * ...)`, its own words and its own behaviour.
 */
internal object BrainSections {

    /** One heading: [key] is its own stable id, [title] is what is drawn. */
    data class Section(
        val key: String,
        val title: String,
        /**
         * A second line under the title, or empty for none. Only where the
         * name alone would leave the owner guessing what is inside.
         */
        val hint: String,
        /** The `item(key = "...")`s of [BrainScreen] drawn under this heading, in order. */
        val items: List<String>,
    )

    /**
     * The headings, in the order they are drawn.
     *
     * The order follows the owner's own list - what waits on them first - with
     * one constraint from the screen itself: "Money and time" is drawn before
     * "What Jarvis is doing", and the goals plate sits under "Your projects and
     * goals" with the projects. Coming up is therefore drawn above Goals, which
     * is what GoalsTest holds ("Goals is below Coming up").
     */
    val SECTIONS: List<Section> = listOf(
        Section(
            key = "waiting",
            title = "Waiting for you",
            hint = "A yes or a no from you.",
            items = listOf("memory-hidden", "memory"),
        ),
        Section(
            key = "knows",
            title = "What Jarvis knows about you",
            hint = "",
            items = listOf(
                "memory-counts",
                "memory-auto",
                "memory-profile",
                "memory-shared",
                "topics",
                "people-and-things",
                "history",
                "forget-range",
                "wiki-hidden",
                "wiki",
                "memory-as-of-hidden",
                "memory-as-of",
            ),
        ),
        Section(
            key = "doing",
            title = "What Jarvis is doing",
            hint = "",
            items = listOf(
                "doing",
                "steps",
                "focus",
                "chatbot",
                "support",
                "attention",
                "jobs",
                "tasks",
                "watch",
                "initiative",
            ),
        ),
        Section(
            key = "money-time",
            title = "Money and time",
            hint = "",
            items = listOf("briefing", "today", "widgets", "coming-up", "spending", "retirement"),
        ),
        Section(
            key = "projects",
            title = "Your projects and goals",
            hint = "",
            items = listOf("progress", "projects", "goals"),
        ),
        Section(
            key = "learning",
            title = "Your learning",
            hint = "",
            items = listOf("quiz", "decks"),
        ),
        Section(
            key = "pc",
            title = "Jarvis on your PC",
            hint = "",
            items = listOf(
                "models",
                "hardware",
                "tutorials",
                "pc-help",
                "second-card",
                "big-model",
                "deep-questions-hidden",
                "deep-questions",
                "compute",
                "ledger",
                "skills",
                "capabilities",
                "settings-entry",
            ),
        ),
    )

    /** The heading holding [itemKey], or null for an item no heading holds. */
    fun sectionOf(itemKey: String): Section? =
        SECTIONS.firstOrNull { itemKey in it.items }

    /**
     * Every `item(key = ...)` this file places, all headings together. Held
     * against the screen's own list by `BrainSectionsTest`: a plate added to
     * BrainScreen.kt under no heading, or a heading naming an item the screen
     * does not draw, fails there rather than quietly disappearing.
     */
    val allKeys: List<String> = SECTIONS.flatMap { it.items }

    /**
     * Keys that are drawn by [BrainScreen] and are NOT placed under a heading:
     * the ones that must stay visible whatever the owner has open.
     *
     *  * `rush` - the rush latch. Outside text that tried to raise the tier is
     *    the one adversarial thing on this screen; a banner about it must never
     *    be inside something that can be shut.
     *  * `freshness` - whether any of the numbers below can be trusted at all.
     *  * `notice` - what the last write failed with, shown once and dismissed.
     *  * `attention` - the interruption budget. Its menu can never be hidden or
     *    folded (MenuCatalog's NEVER_HIDE, and MenuVisibilityTest asserts this
     *    screen draws it with no `menus.shows` check at all), so it cannot go
     *    inside a heading that can be shut without breaking that rule. It is
     *    also the one number here the owner checks at a glance.
     *  * `menus-hidden` - "N hidden - Show", the one line that can put a hidden
     *    plate back (Settings has the list).
     *  * `tail` - the gap at the bottom.
     */
    val ALWAYS_DRAWN: List<String> =
        listOf("rush", "freshness", "notice", "attention", "menus-hidden", "tail")

    /**
     * Which heading starts open, given the plate a link asked for
     * (`BrainScreen`'s `initialSection`: "open the morning briefing" by voice
     * or chat). The heading holding that plate starts open, so the link lands
     * on the plate itself and not on a shut heading.
     *
     * With no link, nothing opens - that is the whole point of the change, and
     * the reason the collapsed screen is a handful of rows rather than a wall
     * of plates. [Open] decides the one exception: the approvals queue's own
     * heading on an owner's very first visit.
     */
    fun toOpen(initialKey: String?): String? = initialKey?.let { sectionOf(it)?.key }

    /** The heading key a [toOpen] result stands for; for tests and callers to read. */
    fun titleOf(key: String): String? = SECTIONS.firstOrNull { it.key == key }?.title

    /**
     * Which heading is open. [key] is the open heading, or null when every
     * heading is shut, and [seen] is true once the owner has opened or closed
     * one by hand.
     *
     * Opening a heading opens nothing else: the owner opened this screen to
     * find one thing, and keeping every previous heading open would rebuild the
     * long scroll they asked to be rid of. Tapping the open heading shuts it
     * again, so every heading can be closed as well as opened.
     */
    class Open(private var openKey: String? = null) {
        /** True once a heading has been opened or closed by hand. */
        var seen: Boolean = false
            private set

        /** The heading key that is open, or null when every heading is shut. */
        val key: String? get() = openKey

        fun isOpen(section: String): Boolean = openKey == section

        /** The owner tapped [section]: open it, or shut it if it was the open one. */
        fun toggle(section: String) {
            seen = true
            openKey = if (openKey == section) null else section
        }

        /** A link or a jump asked for [section]: open it. Never shuts anything. */
        fun open(section: String) {
            seen = true
            openKey = section
        }
    }
}

/**
 * The heading itself: its title, a word for the state ("Open"/"Fold"), a drawn
 * chevron, how many plates are inside while it is shut, and the tap that opens
 * or shuts it.
 *
 * What a screen reader is told, in words rather than by a shape or a colour:
 *
 *  * the title is a real heading ([heading]), as the old `GroupHeading` was, so
 *    "navigate by headings" walks the headings instead of every row;
 *  * the row carries [stateDescription] "Expanded" or "Collapsed" - the words
 *    this app already uses on the FAQ's and "Everything Jarvis can do"'s own
 *    open/close cards - so the state is announced and never left to the
 *    chevron's direction;
 *  * the state is drawn as a word too, and the whole row is the target, at the
 *    48dp minimum every other control in this app keeps.
 *
 * The count is drawn while the heading is SHUT, not while it is open: it is
 * what says whether opening is worth a tap, and once the plates are drawn the
 * list itself says the same thing. Nothing here sets `maxLines`, so a long
 * heading wraps on a narrow phone rather than being cut off.
 *
 * The title's size and weight come from UI-AUDIT-2026-09-26 item 8 - "stronger
 * by size and weight, never by the accent colour", which stays reserved for
 * focus and selection.
 */
@Composable
private fun BrainGroupHeading(section: BrainSections.Section, open: Boolean, onToggle: () -> Unit) {
    val chrome = LocalChrome.current
    // Turned in the draw phase, so the short turn redraws one small box and
    // recomposes nothing (the FAQ's own note, screens-14).
    val turn by animateFloatAsState(
        targetValue = if (open) 180f else 0f,
        animationSpec = LocalMotion.current.micro(),
        label = "brain-heading-chevron",
    )
    Column(Modifier.fillMaxWidth().animateContentSize()) {
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = 48.dp)
                .clip(LocalRadii.current.insetShape)
                .semantics {
                    heading()
                    stateDescription = if (open) "Expanded" else "Collapsed"
                }
                .pressable(onClick = onToggle),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                section.title,
                style = MaterialTheme.typography.headlineSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                if (open) "Fold" else "Open",
                style = MaterialTheme.typography.labelMedium,
                color = chrome.textMid,
            )
            Spacer(Modifier.width(6.dp))
            Chevron(tint = chrome.textMid, modifier = Modifier.graphicsLayer { rotationZ = turn })
        }
        if (!open && section.items.size > 1) {
            Text(
                "${section.items.size} inside",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                modifier = Modifier.padding(start = 2.dp),
            )
        }
        if (section.hint.isNotEmpty()) {
            Text(
                section.hint,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
                modifier = Modifier.padding(start = 2.dp),
            )
        }
    }
}

/**
 * One heading on Brain, and the plates under it while it is open.
 *
 * A shut heading draws its title alone, so the whole screen is seven rows. The
 * heading and its plates are separate LazyColumn items - the heading's own key
 * for the title, so a jump inward still finds it, and a second key for the
 * plates - and a shut heading draws only the first.
 *
 * [content] is handed a `plates` slot to put its `item(key = ...)` lines in.
 * That slot is the only shape Kotlin accepts here: `item` belongs to the lazy
 * list, and inside a composable - which is what a section's plates are drawn
 * as - the list's own receiver is out of reach. The slot hands the items back
 * to the list; the `Column` inside it gives them the 16dp gap the list's own
 * `verticalArrangement` cannot reach inside one item.
 */
internal fun LazyListScope.brainSection(
    section: BrainSections.Section,
    open: Boolean,
    onToggle: () -> Unit,
    plates: LazyListScope.() -> Unit,
) {
    item(key = section.key) { BrainGroupHeading(section, open = open, onToggle = onToggle) }
    if (open) {
        item(key = section.key + "-plates") {
            // The plates are handed back the lazy list they were written
            // against (this `brainSection`'s own receiver), which is what makes
            // the caller's `item(key = ...)` lines work - no composable has an
            // `item` of its own.
            Column(
                Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                plates(this@brainSection)
            }
        }
    }
}
