package com.jarvis.client.ui.screens

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
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
 * Three things live here and nothing else:
 *
 *  * [SECTIONS] - the headings, in the order they are drawn, and the plates
 *    each one holds, in the order the screen draws them. The screen reads this
 *    to draw the headings; nothing here draws a plate and nothing here touches
 *    the network, so `BrainSectionsTest` can hold it to the screen's real item
 *    keys on a plain JVM.
 *  * [Open] - which heading is open, and the rule that a link into Brain
 *    ("open the morning briefing", "show everything saved automatically")
 *    opens the heading it lands in, so nothing that used to be one tap away
 *    became unreachable.
 *  * [PlateList] - the only way a plate may be emitted, which is what keeps a
 *    heading's key and its plates' keys from ever colliding again (the crash of
 *    2026-10-10, below).
 *
 * ## Two keys that may never collide, and one count that may not lie
 *
 * The first build of these headings drew `item(key = section.key)` for the
 * heading and let each plate keep its own key. Under "What Jarvis is doing"
 * the first plate's key was also `"doing"`, and under "Your projects and
 * goals" it was `"projects"` - so tapping either heading handed LazyColumn two
 * items with one key and the app died:
 *
 * ```
 * java.lang.IllegalArgumentException: Key "doing" was already used.
 * ```
 *
 * A rename would have fixed those two taps and left the next plate free to
 * break it again, so the two namespaces are separated structurally instead:
 * [HEADING_PREFIX] is the only spelling a heading's item key may have, and
 * [PlateList.plate] refuses any plate whose key starts with it. The two can
 * therefore never be equal, whatever a future plate is called.
 *
 * The "N inside" a shut heading shows is `BrainScreen`'s measured count of the
 * plates it really emitted ([PlateList.keys]) - never the length of the list
 * below. Those two differ: `memory`/`memory-hidden`, `wiki`/`wiki-hidden` and
 * `memory-as-of`/`memory-as-of-hidden` are pairs of which exactly one is ever
 * drawn, and the hidden-menus and empty-job checks remove others. The declared
 * list said "6 inside" for a heading that drew 5.
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

    /**
     * The one spelling a heading's own `item(key = ...)` may have. A plate's
     * key may not start with it ([PlateList.plate] refuses one that does), so a
     * heading row and a plate under it can never carry the same key - which is
     * the crash of 2026-10-10, made impossible rather than renamed away.
     */
    const val HEADING_PREFIX = "brain-heading:"

    /** The key the heading row of [section] is drawn under. */
    fun headingKey(section: Section): String = HEADING_PREFIX + section.key

    /**
     * Refuses a plate named like a heading row. [PlateList.plate] calls this for
     * every plate before it emits one, so the two keys of one `Comparable` cannot
     * be equal however a future plate is named - a rename would have fixed the
     * two taps that crashed and left the next plate free to break it again.
     */
    fun checkPlateName(key: String) {
        require(!key.startsWith(HEADING_PREFIX)) {
            "a plate may not be named \"$HEADING_PREFIX...\": that is a heading row's key, and two " +
                "items of one LazyColumn may never share a key"
        }
    }

    /**
     * One plate under a heading, as [BrainScreen] draws it: [key] is the
     * `plate("...")` name, [guard] the menu id whose `menus.shows(...)` decides
     * whether it is drawn at all (null for one that is always drawn), and [note]
     * any other condition, in words, for the test to hold.
     *
     * [drawnWith] is the OTHER name of a plate that comes in two halves, of which
     * exactly one is ever drawn - `wiki` and `wiki-hidden`, and two more. The
     * screen writes them as one plate that names both and chooses with
     * `plateDrawn`, which is the same rule the heading is handed, so a shut
     * heading's count can never promise the half its open state does not draw.
     * Both names stay declared here, in this order, because both are real plates
     * with real words; only one of them is on screen at a time.
     *
     * This is the declaration the drift test holds the screen's own `plate(...)`
     * lines to, in order and one for one. It exists so that "N inside" is a
     * measured fact about this screen rather than a number living in a file that
     * nothing checks.
     */
    data class Plate(
        val key: String,
        val guard: String? = null,
        val note: String = "",
        val drawnWith: String? = null,
    )

    /** The two halves of one plate, as [Plate.drawnWith] pairs them. */
    val PAIRS: List<Pair<String, String>> by lazy {
        SECTIONS.flatMap { it.plates }.mapNotNull { p ->
            p.drawnWith?.let { if (p.key < it) p.key to it else it to p.key }
        }.distinct()
    }

    /** The other name of [key]'s half, or null when it is drawn on its own. */
    fun twinOf(key: String): String? =
        SECTIONS.flatMap { it.plates }.firstOrNull { it.key == key }?.drawnWith

    /** One heading: [key] is its own stable id, [title] is what is drawn. */
    data class Section(
        val key: String,
        val title: String,
        /**
         * A second line under the title, or empty for none. Only where the
         * name alone would leave the owner guessing what is inside.
         */
        val hint: String,
        /**
         * The plates [BrainScreen] draws under this heading, in the order it
         * draws them. Some are drawn only when their menu is shown or their
         * data is there, so this is what the heading *may* hold - the count the
         * heading shows is measured from what it really emitted.
         */
        val plates: List<Plate>,
    ) {
        /** The plate keys, in order; what the drift test compares to the screen. */
        val plateKeys: List<String> get() = plates.map { it.key }
    }

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
            // One of this pair is always drawn, never both: the review queue, or
            // the line that can bring it back out of "Hide memory lists".
            plates = listOf(
                Plate("memory-hidden", note = "drawn instead of memory when memory lists are hidden", drawnWith = "memory"),
                Plate("memory", note = "drawn instead of memory-hidden when lists are not hidden", drawnWith = "memory-hidden"),
            ),
        ),
        Section(
            key = "knows",
            title = "What Jarvis knows about you",
            hint = "",
            plates = listOf(
                Plate("memory-counts", guard = "brain.memory.learning"),
                Plate("memory-auto", guard = "brain.memory.auto"),
                Plate("memory-profile", guard = "brain.memory.profile"),
                Plate("memory-shared", guard = "brain.memory.between-us"),
                Plate("topics", guard = "brain.memory.topics"),
                Plate("people-and-things", guard = "brain.memory.people-things"),
                Plate("history", guard = "entry.history"),
                Plate("forget-range", guard = "brain.history.forget-range"),
                // The wiki and "what did I believe on this date?" are pairs too,
                // for the same reason as the review queue above.
                Plate("wiki-hidden", guard = "brain.memory.wiki", note = "drawn instead of wiki when lists are hidden", drawnWith = "wiki"),
                Plate("wiki", guard = "brain.memory.wiki", note = "drawn instead of wiki-hidden when lists are not hidden", drawnWith = "wiki-hidden"),
                Plate("memory-as-of-hidden", guard = "brain.memory.as-of", note = "drawn instead of memory-as-of when lists are hidden", drawnWith = "memory-as-of"),
                Plate("memory-as-of", guard = "brain.memory.as-of", note = "drawn instead of memory-as-of-hidden when lists are not hidden", drawnWith = "memory-as-of-hidden"),
            ),
        ),
        Section(
            key = "doing",
            title = "What Jarvis is doing",
            hint = "",
            // NOT attention: the interruption budget may never be inside a
            // heading that can be shut (see [ALWAYS_DRAWN]).
            plates = listOf(
                Plate("doing", guard = "brain.now.right-now"),
                Plate("steps", guard = "brain.now.trace"),
                Plate("focus", guard = "brain.work.focus"),
                Plate("chatbot", guard = "brain.work.chatbot"),
                Plate("support", guard = "brain.work.support"),
                Plate("jobs", guard = "brain.work.jobs", note = "drawn only when there are background jobs"),
                Plate("tasks", guard = "brain.work.jobs"),
                Plate("watch", note = "always drawn; the watch list draws its own empty line"),
                Plate("initiative", guard = "brain.now.findings"),
            ),
        ),
        Section(
            key = "money-time",
            title = "Money and time",
            hint = "",
            plates = listOf(
                Plate("briefing", guard = "brain.work.briefing"),
                Plate("today", guard = "brain.work.today"),
                Plate("widgets", guard = "brain.work.widgets"),
                Plate("coming-up", guard = "brain.work.coming-up"),
                Plate("spending", guard = "settings.spending"),
                Plate("retirement", guard = "brain.work.retirement"),
            ),
        ),
        Section(
            key = "projects",
            title = "Your projects and goals",
            hint = "",
            plates = listOf(
                Plate("progress", guard = "brain.projects.progress"),
                Plate("pictures", guard = "brain.projects.pictures"),
                Plate("projects", guard = "brain.tab.projects"),
                Plate("goals", guard = "brain.work.goals"),
            ),
        ),
        Section(
            key = "learning",
            title = "Your learning",
            hint = "",
            plates = listOf(
                Plate("quiz", guard = "brain.work.quiz"),
                Plate("decks", guard = "brain.work.decks"),
            ),
        ),
        Section(
            key = "pc",
            title = "Jarvis on your PC",
            hint = "",
            plates = listOf(
                Plate("models", guard = "brain.model.models"),
                Plate("hardware", guard = "settings.hardware"),
                Plate("tutorials", guard = "brain.model.tutorials"),
                Plate("pc-help", guard = "brain.model.pc-help"),
                Plate("second-card", guard = "settings.second-card"),
                Plate("big-model", guard = "settings.big-model"),
                Plate("deep-questions-hidden", guard = "brain.memory.deep", note = "drawn instead of deep-questions when lists are hidden"),
                Plate("deep-questions", guard = "brain.memory.deep", note = "drawn instead of deep-questions-hidden when lists are not hidden"),
                Plate("compute", guard = "brain.model.compute"),
                Plate("ledger", note = "always drawn; the audit chain draws its own empty line"),
                Plate("skills", guard = "brain.model.skills"),
                Plate("capabilities", guard = "settings.backend-supports"),
                Plate("settings-entry", note = "drawn only when the screen was given a way into Settings"),
            ),
        ),
    )

    /** The heading holding the plate named or keyed [itemKey], or null for an item no heading holds. */
    fun sectionOf(itemKey: String): Section? {
        // Either spelling names the same plate, and both are really used: a link
        // ("open the morning briefing") sends the plate's bare NAME
        // ([toOpen], from `BrainScreen.initialSection`), and the screen's own
        // walk sends the ITEM KEY it is looking for - `brain-plate:<name>`,
        // because that is what `ScrollToKeyOnce` hands `onOpen`
        // (`BrainScreen.plateKeyAt`). Until 2026-10-11 this only knew the bare
        // name, so the key the walk really handed it found no heading at all: no
        // heading opened, the plate was not in the list, and every link into
        // Brain - Find anything's rows included - landed at the top of a shut
        // screen.
        //
        // The lines drawn outside every heading ([ALWAYS_DRAWN]) belong to no
        // heading, so this answers null for them in either spelling - which is
        // right: the jump to one of them scrolls to it, and nothing has to be
        // opened first.
        val name = itemKey.removePrefix(PlateList.PLATE_PREFIX)
        return SECTIONS.firstOrNull { name in it.plateKeys }
    }

    /** The plates under [section], in the order the screen draws them. */
    fun platesOf(section: String): List<Plate> =
        SECTIONS.firstOrNull { it.key == section }?.plates ?: emptyList()

    /**
     * Every plate this file places, all headings together. Held against the
     * screen's own `plate("...")` lines by `BrainSectionsTest`: a plate added to
     * BrainScreen.kt under no heading, or a declared plate the screen does not
     * draw, fails there rather than quietly disappearing.
     */
    fun allPlateKeys(): List<String> = SECTIONS.flatMap { it.plateKeys }

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
     *
     *    It was inside "What Jarvis is doing" - one of the two headings that
     *    crashed on 2026-10-10 - so it was both unreachable on the new screen
     *    and absent from the collapsed one. It is emitted outside every heading
     *    now, which is what this list, the heading note above it and
     *    `BrainSectionsTest` all say.
     *  * `menus-hidden` - "N hidden - Show", the one line that can put a hidden
     *    plate back (Settings has the list).
     *  * `tail` - the gap at the bottom.
     *
     * `rush` and `notice` are drawn only when there is something to say, and
     * `menus-hidden` only when something is hidden; the rest are always there.
     * The order is the order the screen emits them, and `BrainSectionsTest`
     * holds it to that.
     *
     * Each key is the FULL `item(key = ...)` the screen draws, in the same
     * namespace a plate's key carries ([PlateList.PLATE_PREFIX]): one list, one
     * spelling, so this list is what the screen is held to and there is no
     * second bare spelling to drift back to. It was a list of bare names until
     * 2026-10-11, and the screen really did draw them bare - which is why the
     * walk a link into Brain runs, looking up `brain-plate:attention`, found
     * nothing and left the owner at the top of the screen.
     */
    val ALWAYS_DRAWN: List<String> =
        listOf("rush", "freshness", "notice", "attention", "menus-hidden", "tail")
            .map { PlateList.PLATE_PREFIX + it }

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
 * [inside] is the count of plates this heading's own emission really produced -
 * never `section.plates.size`, which counts what *could* be drawn. A heading
 * that says "6 inside" and draws 5 is a number the owner cannot use: the pairs
 * of plates ([BrainSections.Section.plates]) and the hidden menus both make the
 * two differ.
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
private fun BrainGroupHeading(
    section: BrainSections.Section,
    open: Boolean,
    inside: Int,
    onToggle: () -> Unit,
) {
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
        if (!open && inside > 1) {
            Text(
                "$inside inside",
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
 * The only way a plate may be added to Brain's list: [plate] takes the plate's
 * own key, checks it can never collide with the heading row above it, emits the
 * item, and counts it.
 *
 * `LazyListScope.item` is deliberately NOT the way in. A test cannot watch that
 * one being called, and - the reason this class exists - the first build proved
 * a plate can be handed the *wrong* list: `brainSection` passed its own receiver
 * into a `Column`'s content, Compose read the plate's `item(key = ...)` against
 * that receiver, and every plate on the screen was appended to the BOTTOM of the
 * list, after the last heading, instead of under the heading that was tapped.
 * Going through one method with one receiver is what makes the emitted order
 * something the screen owns and `BrainSectionsTest` can drive.
 */
sealed class PlateList {
    /**
     * Every plate's item key starts with this, and a heading's own key may not
     * ([BrainSections.HEADING_PREFIX]): the two namespaces cannot overlap, so the
     * crash of 2026-10-10 cannot come back through a new plate's name.
     */
    companion object {
        const val PLATE_PREFIX = "brain-plate:"
    }

    /** The plate keys emitted so far, in the order the list draws them. */
    abstract val keys: List<String>

    /**
     * Whether a plate is drawn at all, given its name. True everywhere except
     * where `BrainScreen` says otherwise.
     *
     * The screen sets this to its own "Hide memory lists and chat history" test,
     * and the PLATES THAT COME IN PAIRS - `wiki`/`wiki-hidden`,
     * `memory`/`memory-hidden` and the rest, of which exactly one is drawn - ask
     * it which of the two to write:
     *
     * ```
     * plate(if (visible("wiki")) "wiki" else "wiki-hidden") { ... }
     * ```
     *
     * Without it, a shut heading counted BOTH of every pair: the phone read
     * "10 inside" over a heading that draws 7, which is the same lie in the other
     * direction - a count that is not what the tap will show.
     */
    open val visible: (String) -> Boolean = { true }

    /**
     * Emits the plate named [key] into Brain's list. The name is the plate's own
     * name, kept verbatim inside the key, so a link, a jump or a `MenuPlaces`
     * entry that names a plate still names the same thing - it is only the item
     * key that carries the namespace.
     *
     * [drawn] overrides the heading's own rule for THIS plate. The heading hands
     * every plate one rule (`visible = ::plateDrawn`, the private-lists test),
     * which is right for a memory LIST: hiding the list hides the names, and the
     * plate is not drawn at all. It is WRONG for a plate that guards ITSELF and
     * has no second half - `people-and-things`, the Galaxy. Dropping that one did
     * not hide any name; it removed the prompt the plate was going to draw, so
     * the owner saw nothing where the thing he asked for should be, and a jump
     * to it found no item and ended at the bottom of the list (2026-10-11). Such
     * a plate passes `{ true }` and draws its own guard.
     */
    abstract fun plate(
        key: String,
        drawn: ((String) -> Boolean)? = null,
        content: @Composable () -> Unit,
    )

    protected fun checkName(key: String) = BrainSections.checkPlateName(key)
}

/**
 * One plate the recorder is holding: its name and what draws it.
 *
 * At the top level rather than in [PlateList]'s companion: a nested class inside
 * a companion object is not resolved by the compiler from the class that uses
 * it here, and the pairs it has to replace (`key to content`) may not be used
 * because a pair of a `@Composable` lambda loses the composable type.
 */
private class BoundPlate(val key: String, val content: @Composable () -> Unit)

/**
 * The real one: records the plates as they are written, then emits the recorded
 * ones into the list being built.
 *
 * Recording first and emitting second is what lets a heading show a count it has
 * measured: the count lives on the heading row's item, which has to be emitted
 * before the first plate, so the plates have to be known before it. Recording up
 * front also means the plates are placed by this one method, in the order they
 * were written, rather than by whatever receiver happened to be in reach.
 */
internal class LazyPlateList(
    private val list: LazyListScope,
    override val visible: (String) -> Boolean = { true },
) : PlateList() {
    private val emitted = ArrayList<String>()
    private val bound = ArrayList<BoundPlate>()

    /**
     * The plate keys this recorder is holding, in the order they were written.
     * This is the count a heading shows: while it is OPEN, the plates written for
     * it in this pass; while it is SHUT, the ones its last open wrote.
     */
    override val keys: List<String> get() = if (emitting) emitted else bound.map { it.key }

    private var emitting = false

    override fun plate(
        key: String,
        drawn: ((String) -> Boolean)?,
        content: @Composable () -> Unit,
    ) {
        checkName(key)
        // A plate the screen says is not drawn is not written down either: the
        // count a shut heading shows has to be the number of plates the tap will
        // really reveal. A plate that passes its own [drawn] answers for itself
        // - `{ true }` for one that guards itself instead of vanishing.
        val shown = drawn?.invoke(key) ?: visible(key)
        if (!shown) return
        bound.add(BoundPlate(key, content))
    }

    /** Writes the plates of one heading down, without emitting them: the count. */
    internal fun write(plates: PlateList.() -> Unit) {
        bound.clear()
        plates()
    }

    /**
     * Writes the plates of one heading into [out]: [plates] runs against this
     * recorder - which is the only way a plate may be written - and then each
     * recorded plate becomes one item of the list, in the order it was written,
     * keyed `brain-plate:<name>`.
     */
    internal fun emit(plates: PlateList.() -> Unit, out: MutableList<String>) {
        bound.clear()
        emitting = true
        plates()
        for (plate in bound) {
            out.add(plate.key)
            list.item(key = PLATE_PREFIX + plate.key) { plate.content() }
        }
        emitting = false
    }
}

/**
 * Writes the plates of one heading and returns the count its heading shows.
 *
 * The plates are written TWICE, deliberately: once so the count is known before
 * the heading row's own item is emitted (it has to be - the heading comes first),
 * and once to place them. Nothing runs twice that has an effect: a plate body is
 * a lambda the list itself calls when that row comes into view.
 *
 * A SHUT heading measures its plates too, and this is the whole reason for the
 * two-pass shape: a heading that is shut draws no plates, so a count taken only
 * while it was open would be zero on the very screen the count exists for. The
 * number shown on a shut heading is therefore "what it held the last time it was
 * written", which is also the number the tap will reveal.
 *
 * [draw] is handed the keys really emitted, in order, and its return value - the
 * count - is used for nothing else. The count a heading is DRAWN with is
 * `plateList.keys.size` at that moment, which is never a number declared
 * somewhere else: `section.plates` is what *may* be drawn, and the two differ
 * whenever a menu is hidden, a pair of plates draws only one of itself, or a list
 * is empty.
 */
internal fun LazyListScope.brainSection(
    section: BrainSections.Section,
    open: Boolean,
    onToggle: () -> Unit,
    plates: PlateList.() -> Unit,
    /** Whether a plate is drawn at all, given its name; true everywhere by default. */
    visible: (String) -> Boolean = { true },
    /** Filled with the plates really emitted, in order; empty while shut. */
    drawn: MutableList<String> = ArrayList(),
    /**
     * Bumped once for every item this heading puts in the list - its own heading
     * row, and each plate it emits.
     *
     * The screen's OWN count, and it exists to be compared with
     * `LazyListState.layoutInfo.totalItemsCount`, which is
     * `MutableIntervalList.getSize()` - the number of intervals the content
     * lambda registered. Those two numbers should be equal; when they are not,
     * the list is not holding what the screen declared, and that is a different
     * defect from a walk that cannot reach its item (2026-10-11, Coming up).
     */
    rows: (() -> Unit)? = null,
    /**
     * One line per section, for a screen that has to know where its own rows
     * went.
     *
     * It exists because two counts disagreed on the device (2026-10-11):
     * `declared=19` against `composed=11`, on the artifact this app resolves to,
     * where `composed` is `MutableIntervalList.getSize()` - the number of
     * intervals the CONTENT LAMBDA registered. Eight rows the screen declares
     * are therefore not registered, and only a per-section account can say which
     * section loses them and whether the loss is in the WRITING (the section's
     * own `plates` lambda asked for them but the visibility rule dropped them)
     * or in the EMITTING.
     *
     * Called with the section key, whether its heading is open, how many plate
     * rows were written, and how many were emitted.
     */
    log: ((String, Boolean, Int, Int) -> Unit)? = null,
): Int {
    val plateList = LazyPlateList(this, visible)
    plateList.write(plates)
    // What the section ASKED for after the visibility rule had its say - the same
    // number a shut heading shows as "N inside".
    val writtenCount = plateList.keys.size
    // The heading's own key, in its own namespace: a plate's key can never be
    // this (PlateList refuses one that is), so the two items cannot collide.
    item(key = BrainSections.headingKey(section)) {
        BrainGroupHeading(section, open = open, inside = plateList.keys.size, onToggle = onToggle)
    }
    rows?.invoke()
    if (!open) {
        log?.invoke(section.key, false, writtenCount, 0)
        drawn.clear()
        return 0
    }
    plateList.emit(plates, drawn)
    log?.invoke(section.key, true, writtenCount, drawn.size)
    repeat(drawn.size) { rows?.invoke() }
    return drawn.size
}

/**
 * Every item Brain's list is built from, in the order it is drawn, as one call:
 * a heading's key, then the keys of its plates while it is open, section after
 * section - and finally the items that are outside every heading
 * ([BrainSections.ALWAYS_DRAWN]).
 *
 * This is the shape `BrainScreen` builds, written once here so that a test on a
 * plain JVM can build it and read it back. Nothing about the headings is decided
 * in this function: [openSection] and [drawnInSection] ARE the screen's taps and
 * its `menus.shows` checks (a test passes the same ones the screen's own
 * `plate("...")` lines use). What it adds is the one thing the screen cannot show
 * a test - the whole sequence, with the headings and their plates in it together
 * - which is where two items sharing a key appear, and where a plate that drifted
 * out of its section shows up as a plate drawn after the wrong heading.
 */
internal fun brainListKeys(
    openSection: (String) -> Boolean,
    drawnInSection: (String, MutableList<String>) -> Unit,
): List<String> {
    val out = ArrayList<String>()
    for (section in BrainSections.SECTIONS) {
        val drawn = ArrayList<String>()
        if (openSection(section.key)) drawnInSection(section.key, drawn)
        out.add(BrainSections.headingKey(section))
        out.addAll(drawn.map { PlateList.PLATE_PREFIX + it })
    }
    out.addAll(BrainSections.ALWAYS_DRAWN)
    return out
}
