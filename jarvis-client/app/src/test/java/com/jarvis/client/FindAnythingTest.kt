package com.jarvis.client

import com.jarvis.client.net.MenuCatalog
import com.jarvis.client.net.MenuLogic
import com.jarvis.client.net.MenuState
import com.jarvis.client.net.MenuView
import com.jarvis.client.ui.FindAnything
import com.jarvis.client.ui.FindWords
import com.jarvis.client.ui.MenuPlaces
import com.jarvis.client.ui.Screen
import com.jarvis.client.ui.SettingsJump
import com.jarvis.client.ui.SettingsSearch
import com.jarvis.client.ui.SettingsSearchWords
import com.jarvis.client.ui.screens.BrainSections
import com.jarvis.client.ui.screens.PlateList
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * "Find anything" - the phone's typed search over every place in the app
 * (`ui/FindAnything.kt`, `ui/screens/FindScreen.kt`), the last of the parity
 * audit's eight gaps (`.dsh-scratch/android-verify/PARITY-AUDIT-2026-10-10.md`,
 * row 244; the desktop's `jarvis-desktop/src/palette.js`).
 *
 * Five things it holds that would otherwise drift, and each of them is a rule
 * the feature is not allowed to break:
 *
 *  1. **Every result is one of the app's own menus.** The list is built from
 *     `MenuCatalog` and `MenuPlaces`, never hand-typed, and it is checked BOTH
 *     ways - a new phone menu with a place cannot be missing from it, and
 *     nothing may pretend to be a menu that is not one.
 *  2. **A hidden thing never appears.** A menu the owner hid with "Show or
 *     hide menus" is not in the list, and neither is a memory list or the
 *     chat history while "Hide memory lists and chat history" is on. This is
 *     the stricter of the two apps' rules, on purpose.
 *  3. **A row opens what it says.** Every row's screen and `item(key = ...)`
 *     is checked against the screen's own rows, so a row can never send the
 *     owner to a card that is not there - and the key it is checked against is
 *     the one the row really LANDS ON, in the spelling the list holds
 *     (`brain-plate:<name>` on Brain), not the bare name the row is written
 *     with. A row into Brain is also checked to reach its card: the heading
 *     holding it must be one the screen's own lookup finds, or the walk would
 *     never open it and the owner would land at the top of the screen.
 *  4. **It says something when there is nothing** - an empty box explains
 *     what it searches, and a search that matches nothing says so in words.
 *  5. **It only navigates.** No screen or object in the feature may touch the
 *     runtime, the network or a stored setting.
 */
class FindAnythingTest {

    /** Nothing hidden, nothing opened for a visit: the plain case. */
    private val menus = MenuView()

    // ------------------------------------------- 1. the real catalogue ------

    @Test
    fun `every menu it lists is the catalogue's own row, in the app's own words`() {
        // The feature groups are rows too, and are checked by their own test.
        val listed = FindAnything.ROWS
            .filter { it.menu && !it.id.startsWith(MenuCatalog.GROUP_PREFIX) }
        assertTrue("the list is empty", listed.size > 60)
        for (row in listed) {
            val m = MenuCatalog.MENUS.firstOrNull { it.id == row.id }
            assertNotNull("${row.id} is not in the menu catalogue at all", m)
            assertTrue("${row.id} is not a menu this phone has", m!!.phone)
            // IDENTITY, not a copy that happens to read the same today: the
            // one-line description is the catalogue's string...
            assertEquals("${row.id}: the description is not the catalogue's", m.about, row.about)
            // ...and the title is the words the screen the row opens really
            // draws - the Settings screen's own heading for a Settings row
            // (which is not always the catalogue's title: see
            // `settings.limits`), and the catalogue's everywhere else.
            val section = row.section
            val expected = if (row.screen == Screen.SETTINGS && section != null) {
                SettingsSearch.row(section)?.title
            } else {
                m.title
            }
            assertEquals("${row.id}: the title is not the app's own", expected, row.title)
        }
        assertEquals(
            "a menu is listed twice",
            listed.size,
            listed.map { it.id }.toSet().size,
        )
        assertEquals(
            "no place is listed twice",
            FindAnything.ROWS.size,
            FindAnything.ROWS.map { it.id }.toSet().size,
        )
    }

    @Test
    fun `every feature group can be found, and opens a real member of itself`() {
        val rows = FindAnything.ROWS.filter { it.id.startsWith(MenuCatalog.GROUP_PREFIX) }
        assertEquals(
            "every group the phone has must be findable by its own name",
            MenuCatalog.GROUPS.map { it.id }.sorted(),
            rows.map { it.id }.sorted(),
        )
        for (row in rows) {
            val group = MenuCatalog.GROUPS.first { it.id == row.id }
            assertEquals("${row.id}: the title is not the catalogue's", group.title, row.title)
            assertEquals("${row.id}: the description is not the catalogue's", group.about, row.about)
            // A group is a hiding unit, not a place: its row opens a member of
            // its own, and the member must be one this phone really has.
            val members = MenuLogic.members(row.id, MenuLogic.PHONE)
            assertTrue(
                "${row.id} opens ${row.shownBy}, which is not one of its members",
                row.shownBy in members,
            )
            assertTrue("${row.id} is not visible on a phone with nothing hidden", row.id in FindAnything.all(menus, false).map { it.id })
        }
    }

    @Test
    fun `it finds a place by the names Jarvis already answers to`() {
        // The catalogue's own aliases, the same ones the desktop's palette
        // matches. Each of these is an alias and NOT part of the title, so a
        // pass here means the names really reached the phone's catalogue.
        for ((alias, id) in listOf(
            "app lock" to "settings.security",
            "windows hello" to "settings.security",
            "the menu list" to "settings.menu-visibility",
            "review decks" to "brain.work.decks",
            "quizzes" to "brain.work.quiz",
            "paired devices" to "settings.devices",
            "backup settings" to "settings.backup",
            "support chats" to "brain.work.support",
        )) {
            val m = MenuLogic.menu(id)
            assertNotNull("$id is not in the catalogue", m)
            assertTrue(
                "\"$alias\" is meant to be one of $id's own names, or this proves nothing",
                alias in m!!.names,
            )
            assertFalse(
                "\"$alias\" must not be part of the title, or the title alone would find it",
                FindAnything.fold(m.title).contains(FindAnything.fold(alias)),
            )
            assertTrue(
                "typing \"$alias\" must find $id",
                FindAnything.results(alias, menus, false).any { it.id == id },
            )
        }
    }

    @Test
    fun `every name the catalogue holds is searched, and nothing else is`() {
        // Every row that is a menu carries that menu's names, all of them.
        for (row in FindAnything.ROWS) {
            val m = MenuCatalog.MENUS.firstOrNull { it.id == row.id } ?: continue
            val words = FindAnything.fold(row.words)
            for (name in m.names) {
                assertTrue(
                    "${row.id}: the name \"$name\" is not searched for, so the phone's box " +
                        "knows less than Jarvis does",
                    words.contains(FindAnything.fold(name)),
                )
            }
        }
        assertEquals(
            // A tripwire, not a fact worth knowing: it was 113 until the parity
            // audit of 2026-10-10 put the four cards no registry knew about into
            // `backend/jarvis_menus.py` (`settings.first-run`,
            // `settings.start-jarvis`, `settings.crash-notes`,
            // `settings.notifications`) and retired the duplicate phone-only
            // `entry.voices`; 116 until 2026-10-10, when "approval cards read
            // short" added ONE real menu of its own, `settings.approval-cards`
            // (`Approval cards` in `backend/jarvis_menus.py`, drawn by
            // `SettingsScreen.kt`'s `ApprovalCardsSection` under Appearance) -
            // the catalogue is one larger because a place really was added, not
            // because a regeneration went wrong.
            //
            // 116 -> 118 (2026-10-11) on main: the picture feature's two menus
            // joined the registry - `settings.pictures` (the PC's own setup
            // card) and `brain.projects.pictures` (the gallery) - so the
            // catalogue really is two bigger. With both landed, this branch's
            // 117 and main's 118 are ONE catalogue of 119 - which is why the
            // number here is 119 and not either side's own; both reasons are
            // above rather than one replacing the other.
            //
            // 119 -> 120 (2026-10-18, LM-1C): `settings.sandbox`, the data and
            // maths sandbox's switch, joined the registry as a real menu id on
            // both apps - so the catalogue is one larger because a place really
            // was added.
            //
            // 120 -> 121 (2026-10-19): `settings.focus-presets` is a real menu
            // on BOTH apps now. The phone draws FocusPresetsSection inside the
            // Hardware plate (HardwarePlate.kt), and FindAnything has a real row
            // for it that opens that card, so the catalogue is one larger
            // because a place really was added - not because a desktop-only row
            // was emitted into the phone's list.
            //
            // 121 -> 122 (2026-10-20, F5 S2 / #641): `settings.media-index` is
            // a desktop-only menu (the searchable recordings card; the phone
            // has no card yet and answers "only in Jarvis on your PC"). It IS
            // in the generated catalogue like every other desktop-only entry,
            // so the catalogue is one larger - the phone's findable list and
            // MenuVisibilityTest stay unchanged because `phone = false`.
            //
            // It is here so that a regeneration which drops the `names` field,
            // or a catalogue that comes back a different size, is noticed rather
            // than quietly searched: the check above still proves that every one
            // of the 122 menus has all of its names searched for.
            "the catalogue must still carry the names at all",
            122,
            MenuCatalog.MENUS.size,
        )
        assertTrue(
            "the names were dropped from the generated catalogue",
            MenuCatalog.MENUS.any { it.names.isNotEmpty() },
        )
    }

    @Test
    fun `every phone menu with a place can be found`() {
        val missing = mutableListOf<String>()
        for (m in MenuCatalog.MENUS) {
            if (!m.phone) continue
            // The catalogue's `safety.*` rows are banners and answer lines,
            // not places; the two ENTRIES filed under `safety` are ways in,
            // and are in the list (checked by the test below).
            if (m.area == "safety" && m.kind != "entry") continue
            if (m.id in NO_PLACE) continue
            // A menu the phone draws INSIDE another card or screen has no place
            // of its own to open (`MenuPlaces.INSIDE`, which is the app's own
            // record of exactly that, and which `MenuVisibilityTest` reads as a
            // place for the same reason). The box lists places, so there is
            // nothing here for it to offer.
            if (m.id in MenuPlaces.INSIDE) continue
            if (FindAnything.row(m.id) == null) missing += m.id
        }
        assertTrue(
            "these phone menus have a place in MenuPlaces and cannot be found by " +
                "typing: $missing",
            missing.isEmpty(),
        )
    }

    @Test
    fun `the phone menus with no place of their own are left out, and nothing else`() {
        val excluded = MenuCatalog.MENUS
            .filter { it.phone && !(it.area == "safety" && it.kind != "entry") }
            .filter { it.id !in MenuPlaces.INSIDE }
            .filter { FindAnything.row(it.id) == null }
            .map { it.id }
            .toSet()
        assertEquals(
            "a phone menu with no place on this phone has appeared: decide where it " +
                "opens and it joins the list, or say in MenuPlaces.INSIDE where the " +
                "phone really draws it (ui/FindAnything.kt, placeOf)",
            NO_PLACE,
            excluded,
        )
        assertTrue(
            "a safety banner is not a place a screen can open, so it must not be a row",
            FindAnything.ROWS.none { it.id.startsWith("safety.") },
        )
        // ...and the two entries ARE in it, under Actions.
        assertEquals("connection", FindAnything.row("entry.checks")?.section)
        assertEquals(Screen.CHECKS, FindAnything.row("entry.checks")?.screen)
        assertEquals(Screen.SETTINGS, FindAnything.row("entry.settings")?.screen)
        assertEquals(
            "the ways in are drawn under the desktop's own Actions heading",
            FindWords.ACTIONS,
            FindAnything.row("entry.checks")?.heading,
        )
    }

    @Test
    fun `a row that is not a menu says so, so nothing can dodge the hiding rules`() {
        for (row in FindAnything.ROWS) {
            if (row.menu) continue
            assertTrue(
                "${row.id} claims not to be a menu, so 'Show or hide menus' cannot hide it - " +
                    "that is only allowed for this phone's own screens and for a Settings row " +
                    "nothing may hide",
                row.id.startsWith("place.") || row.id.startsWith("settings-row."),
            )
        }
        // Every Settings row on the screen is one of the two: a menu, or a row
        // MenuPlaces has no id for. Today exactly one is the second kind
        // ("Notifications from Jarvis"), because it is not a hideable menu -
        // a second one appearing must be looked at, not silently joined.
        assertEquals(
            "a Settings row with no menu id has appeared: give it a place and say so here",
            // "App control" (2026-10-19): the phone's accessibility service is
            // phone-only, so the desktop's catalogue has no menu id for it.
            listOf("settings-row.app-control", "settings-row.jarvis-notify"),
            FindAnything.ROWS.filter { it.id.startsWith("settings-row.") }.map { it.id },
        )
    }

    // ------------------------------------------- 2. the two hiding rules ----

    @Test
    fun `a menu hidden with Show or hide menus never appears in a result`() {
        assertNotNull(
            "goals must be findable when it is not hidden, or this proves nothing",
            FindAnything.results("goals", menus, privateHidden = false).firstOrNull {
                it.id == "brain.work.goals"
            },
        )
        val hidden = MenuView(state = MenuState(hidden = setOf("brain.work.goals")))
        assertNull(
            "a hidden menu must not be in the results - the box would otherwise be the " +
                "way round the hiding the owner asked for",
            FindAnything.results("goals", hidden, privateHidden = false).firstOrNull {
                it.id == "brain.work.goals"
            },
        )
        assertNull(
            "a hidden menu must not be in the list with nothing typed either",
            FindAnything.all(hidden, privateHidden = false).firstOrNull {
                it.id == "brain.work.goals"
            },
        )
        assertEquals(
            "and it comes back the moment it is shown",
            "brain.work.goals",
            FindAnything.results("goals", menus, privateHidden = false).first().id,
        )
    }

    @Test
    fun `hiding a group, and hiding a card, take everything under them with it`() {
        val group = MenuView(state = MenuState(hidden = setOf("group.finance")))
        val groupIds = FindAnything.all(group, privateHidden = false).map { it.id }
        assertFalse("settings.spending is in the Finance group", "settings.spending" in groupIds)
        assertFalse(
            "brain.work.retirement is in the Finance group",
            "brain.work.retirement" in groupIds,
        )
        assertTrue("settings.spending is findable when the group is shown", "settings.spending" in FindAnything.all(menus, false).map { it.id })
        assertFalse(
            "the Finance group's own row must go with its members - it would otherwise " +
                "open a member the owner has hidden",
            "group.finance" in groupIds,
        )

        // A row drawn INSIDE a hidden card goes with the card: MenuPlaces
        // already says those rows have no element of their own.
        val card = MenuView(state = MenuState(hidden = setOf("settings.second-card")))
        val cardIds = FindAnything.all(card, privateHidden = false).map { it.id }
        assertFalse("settings.second-card.referee" in cardIds)
        assertFalse("settings.second-card.chat-card" in cardIds)

        // The one member a group's row would open decides whether that row may
        // be shown: hide it, and the group row goes too rather than pointing at
        // something the owner has hidden.
        val one = FindAnything.row("group.study")
        assertNotNull("the Study group has no row to test", one)
        assertEquals("brain.work.quiz", one!!.shownBy)
        val memberHidden = MenuView(state = MenuState(hidden = setOf("brain.work.quiz")))
        assertFalse(
            "group.study" in FindAnything.all(memberHidden, privateHidden = false).map { it.id },
        )
    }

    @Test
    fun `a place that can never be hidden stays findable even if a stored file lists it`() {
        // The holder sanitizes what it reads, and MenuLogic refuses to hide
        // these at all - this holds the box to the same rule: it reads
        // `shows`, so it cannot disagree with the screens about what is hidden.
        val stored = MenuState(hidden = MenuCatalog.NEVER_HIDE.toSet())
        assertEquals(
            "MenuLogic must drop the never-hideable ids from a stored file",
            emptySet<String>(),
            MenuLogic.sanitize(stored, MenuLogic.PHONE).hidden,
        )
        val view = MenuView(state = stored)
        val listed = FindAnything.all(view, privateHidden = false).map { it.id }.toSet()
        val missing = MenuCatalog.NEVER_HIDE.filter { FindAnything.row(it) != null && it !in listed }
        assertTrue("these can never be hidden and are not findable: $missing", missing.isEmpty())
    }

    @Test
    fun `the memory lists and the chat history never appear while they are hidden`() {
        val shown = FindAnything.all(menus, privateHidden = false).map { it.id }.toSet()
        val hidden = FindAnything.all(menus, privateHidden = true).map { it.id }.toSet()
        for (id in FindAnything.PRIVATE_IDS) {
            assertTrue("$id is not a row at all, so the set is naming something gone", id in shown)
            assertFalse(
                "$id is a memory list or the chat history, and must not be listed while " +
                    "\"Hide memory lists and chat history\" is on",
                id in hidden,
            )
        }
        // ...and a search cannot reach one either, while everything else stays.
        assertNull(
            FindAnything.results("waiting", menus, privateHidden = true)
                .firstOrNull { it.id == "brain.memory.waiting" },
        )
        assertNotNull(
            FindAnything.results("waiting", menus, privateHidden = false)
                .firstOrNull { it.id == "brain.memory.waiting" },
        )
        assertNull(
            FindAnything.results("history", menus, privateHidden = true)
                .firstOrNull { it.id == "entry.history" },
        )
        assertTrue("the rest of the app is still findable", "brain.work.goals" in hidden)
        assertTrue("the rest of the app is still findable", "place.inbox" in hidden)
    }

    /**
     * The words printed on a switch find it here too - and reaching the switch
     * is NOT a way round the switch's own hiding rule.
     *
     * The second half is the point, and it is worth being exact about, because
     * it is easy to write the alarming version of this test instead. The switch
     * "Hide memory lists and chat history" is drawn under Security, and
     * `settings.security` is never a memory list and is never hideable - a
     * search result that reaches it does what the owner's own thumb does when
     * the finger goes to that card. What [FindAnything.PRIVATE_IDS] hides is
     * the CONTENT the switch covers (the Brain's memory lists, the History
     * entry, the chat history), and none of those ids is `settings.security`.
     * So a search for the switch's words may open the switch, while a search
     * for the things it hides still returns nothing - both asserted below, so
     * neither half can be satisfied by breaking the other.
     */
    @Test
    fun `a switch is found by the words printed on it, without breaking what it hides`() {
        val menus = MenuView()
        // The owner's exact title, on the box he typed it into.
        assertTrue(
            "typing \"Hide memory lists and chat history\" must find Security",
            FindAnything.results("Hide memory lists and chat history", menus, privateHidden = false)
                .any { it.id == "settings.security" },
        )
        // The half-title a person types when they half-remember it. Both words
        // must be found together (AND, not OR), so this is the switch's own
        // index entry and not the word "history" alone.
        assertTrue(
            "typing \"chat history\" must find the switch's own section",
            FindAnything.results("chat history", menus, privateHidden = false)
                .any { it.id == "settings.security" },
        )
        // ...and the result is the app's own row, with the app's own words.
        val row = FindAnything.results("Hide memory lists and chat history", menus, false)
            .first { it.id == "settings.security" }
        assertEquals(Screen.SETTINGS, row.screen)
        assertEquals("security", row.section)

        // The switch's own words never reach the content it hides. This is the
        // rule `FindAnything`'s own doc says must survive: while the switch is
        // ON, a typed search must not put a memory list or the chat history
        // back on the screen.
        for (q in listOf("chat history", "memory lists", "between us", "waiting")) {
            val hidden = FindAnything.results(q, menus, privateHidden = true).map { it.id }
            val leaked = hidden.filter { it in FindAnything.PRIVATE_IDS }
            assertTrue(
                "while \"Hide memory lists and chat history\" is on, \"$q\" returned $leaked",
                leaked.isEmpty(),
            )
        }
        // ...and the switch itself is still reachable while it is on, so the
        // owner can always find the control that turned the hiding on.
        assertTrue(
            "the switch that hides the memory lists must stay findable while it is on",
            FindAnything.results("Hide memory lists and chat history", menus, privateHidden = true)
                .any { it.id == "settings.security" },
        )
    }

    // ------------------------------------------- 3. opening goes where it says

    @Test
    fun `every row opens a screen and a row that really exist`() {
        for (row in FindAnything.ROWS) {
            val section = row.section ?: continue
            val keys = itemKeys(row.screen)
            assertNotNull(
                "${row.id} opens ${row.screen}/$section, and this test does not read that " +
                    "screen's rows - name it here or the check is not being made",
                keys,
            )
            // The key the row really LANDS ON, not the bare name it is written
            // with: the walk brings an item into view by exact equality with
            // `item(key = ...)`, so a row naming a plate only reaches it if the
            // plate is drawn under the namespaced key (`PlateList.PLATE_PREFIX`).
            // Checking the bare name against a set that held bare names is what
            // let "Attention budget" land at the top of Brain while this test
            // stayed green (2026-10-11).
            val key = itemKeyOf(row)
            assertTrue(
                "${row.id} sends the owner to ${row.screen} at \"$section\", and the walk that " +
                    "takes them there looks up item(key = \"$key\") - which is not on that screen",
                key in keys!!,
            )
        }
    }

    @Test
    fun `a row that lands inside a shut heading can open it`() {
        // Second half of "a row opens what it says", and the half no set of keys
        // can answer: Brain draws a heading's plates only while the heading is
        // open, so the walk (BrainScreen's ScrollToKeyOnce) hands `onOpen` the
        // item key it is looking for BEFORE it walks, and the screen opens the
        // heading holding it. It hands it the ITEM KEY - the same namespaced
        // string the list holds - and until 2026-10-11 the lookup only knew the
        // bare plate NAME, so it answered null for every row, no heading opened,
        // and every Find row into Brain landed at the top of a shut screen.
        val brainRows = FindAnything.ROWS.filter { it.screen == Screen.BRAIN && it.section != null }
        assertTrue("no Find row opens Brain at all - this check is not being made", brainRows.size > 20)
        val outside = alwaysDrawnItemKeys()
        for (row in brainRows) {
            val key = itemKeyOf(row)
            val heading = BrainSections.sectionOf(key)
            if (key in outside) {
                // Drawn outside every heading (the attention budget): it belongs
                // to no heading and must stay out of one, so the walk has nothing
                // to open - it scrolls straight to it. `attention`'s menu can
                // never be folded, and a heading can be shut.
                assertNull(
                    "${row.id}: $key is drawn outside every heading, so nothing may open a " +
                        "heading for it - it is a line that can never be folded away",
                    heading,
                )
            } else {
                assertNotNull(
                    "${row.id} lands on $key, which a heading holds, and no heading is found for " +
                        "that key - so the walk never opens it and the row does not reach its card",
                    heading,
                )
            }
        }
    }

    @Test
    fun `every Settings row can be found`() {
        val settings = FindAnything.ROWS
            .filter { it.screen == Screen.SETTINGS }
            .mapNotNull { it.section }
            .toSet()
        for (key in SettingsSearch.SECTION_KEYS) {
            assertTrue("Settings' \"$key\" cannot be found from the box", key in settings)
        }
        // One Settings row, one heading: the box and Settings' own search box
        // must not describe the same row in two different ways.
        for (key in SettingsSearch.SECTION_KEYS) {
            val row = FindAnything.ROWS.firstOrNull { it.section == key && it.screen == Screen.SETTINGS }
            assertEquals(
                "$key: the box and Settings' own search must use one title",
                SettingsSearch.row(key)?.title,
                row?.title,
            )
        }
        assertEquals(
            "The box lists exactly Settings' rows on that screen, no more and no fewer",
            SettingsSearch.SECTION_KEYS.size,
            settings.size,
        )
    }

    // ------------------------------------------- 4. honest when there is nothing

    @Test
    fun `an empty box lists everything and explains what it searches`() {
        val all = FindAnything.all(menus, privateHidden = false)
        assertTrue("the list is far too short to be the app: ${all.size}", all.size >= 80)
        assertEquals(all.size, FindAnything.count(menus, privateHidden = false))
        assertEquals(
            "an empty box is not a search with no matches",
            emptyList<FindAnything.Row>(),
            FindAnything.results("", menus, privateHidden = false),
        )
        assertEquals(
            "with nothing typed the line says what the box searches",
            FindWords.SEARCHES,
            FindWords.line("", all.size),
        )
        assertTrue(
            "\"what does this search?\" must be answerable in the line itself",
            FindWords.SEARCHES.contains("screen") && FindWords.SEARCHES.contains("setting"),
        )
        assertTrue(
            "and it must say that finding a place changes nothing",
            FindWords.SEARCHES.contains("nothing here changes anything"),
        )
        assertEquals("1 thing Jarvis can do", FindWords.allLine(1))
        assertEquals("${all.size} things Jarvis can do", FindWords.allLine(all.size))
        assertEquals(
            "every row is drawn under one of the desktop's own four headings",
            setOf(FindWords.SCREENS, FindWords.SETTINGS, FindWords.BRAIN, FindWords.ACTIONS),
            all.map { it.heading }.toSet(),
        )
    }

    @Test
    fun `a search that matches nothing says so, and the screen draws those words`() {
        assertEquals(
            emptyList<FindAnything.Row>(),
            FindAnything.results("zzzzz", menus, privateHidden = false),
        )
        assertEquals(
            "the count line is left empty so the screen can say it in a sentence instead",
            "",
            FindWords.line("zzzzz", 0),
        )
        assertEquals("Nothing matches that.", FindWords.NONE_TITLE)
        assertTrue(FindWords.NONE_BODY.length > 20)

        val src = screenSource()
        for (name in listOf(
            "FindWords.NONE_TITLE", "FindWords.NONE_BODY",
            "FindWords.EMPTY_TITLE", "FindWords.EMPTY_BODY",
            "FindWords.SEARCHES", "FindWords.allLine",
        )) {
            assertTrue("FindScreen never draws $name, so the owner gets a blank list", src.contains(name))
        }
        assertTrue(
            "the empty states must hang off an empty list",
            src.contains("if (shown.isEmpty())"),
        )
        assertTrue(
            "the line under the box must be announced (a live region), like every other here",
            src.contains("liveStatus()"),
        )
    }

    // ------------------------------------------- 5. words, and only navigating

    @Test
    fun `the two apps say the same words about the same box`() {
        val desktop = desktopPaletteWords()
        assertTrue("palette.js's WORDS could not be read", desktop.size >= 15)
        // Every word the desktop's palette has is accounted for here: the same
        // word, this phone's own word, or a word a phone has no use for - with
        // its reason. A new word on the desktop fails this until it is
        // answered, which is the drift the open-chat phrase list already cost
        // this project once.
        assertEquals(
            "a word in jarvis-desktop/src/palette.js has no answer on this phone",
            desktop.keys.sorted(),
            (FindWords.SAME.keys + FindWords.PHONE.keys + FindWords.NOT_ON_PHONE.keys).sorted(),
        )
        for ((key, ours) in FindWords.SAME) {
            assertEquals("the desktop's `$key` and this phone's disagree", desktop[key], ours)
        }
        for ((key, ours) in FindWords.PHONE) {
            assertNotEquals(
                "`$key` is listed as this phone's own words and is the desktop's after all",
                desktop[key],
                ours,
            )
        }
        for ((key, why) in FindWords.NOT_ON_PHONE) {
            assertTrue("`$key` is excused with no reason", why.isNotBlank())
        }
        // The four headings are the desktop's own, word for word.
        val js = repoFile("jarvis-desktop/src/palette.js").readText()
        val headings = js.substringAfter("group_headings: Object.freeze({").substringBefore("})")
        for ((key, ours) in listOf(
            "screens" to FindWords.SCREENS,
            "settings" to FindWords.SETTINGS,
            "brain" to FindWords.BRAIN,
            "actions" to FindWords.ACTIONS,
        )) {
            assertTrue(
                "the desktop's group heading `$key` is not \"$ours\"",
                headings.contains("$key: \"$ours\""),
            )
        }
        // One app, one word for emptying a box.
        assertEquals(SettingsSearchWords.CLEAR, FindWords.CLEAR)
    }

    @Test
    fun `it searches and it navigates, and it does nothing else`() {
        for ((what, src) in listOf(
            "ui/FindAnything.kt" to findSource(),
            "ui/screens/FindScreen.kt" to screenSource(),
        )) {
            assertFalse(
                "$what reaches the runtime - the box must not act for the owner",
                src.contains("JarvisRuntime"),
            )
            assertFalse("$what reaches the network", src.contains("JarvisApi"))
        }
        // ...and opening a place must not un-hide it: a hidden menu is never
        // in a result, so there is nothing to show for a visit.
        val activity = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt").readText()
        val branch = activity
            .substringAfter("Screen.FIND -> com.jarvis.client.ui.screens.FindScreen(")
            .substringBefore("\n                    )")
        assertTrue("the Find screen is not wired up at all", branch.isNotEmpty())
        // Comment lines are dropped first: the branch's own comment explains
        // in words that there is deliberately no one-visit show here, and a
        // test that read the comment would fail on the explanation.
        val code = branch.lines().filterNot { it.trim().startsWith("//") }.joinToString("\n")
        assertFalse(
            "finding a place must never show a hidden one for a visit",
            code.contains("showForVisit"),
        )
        assertTrue(
            "and it must go through the same one-time scroll 'open <a place>' uses",
            code.contains("pendingSection = row.section"),
        )
    }

    @Test
    fun `the way in is a labelled control on Home, not a gesture`() {
        val home = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/screens/HomeScreen.kt").readText()
        assertTrue(
            "the Find button must be drawn with the desktop's own word for it",
            home.contains("com.jarvis.client.ui.FindWords.BUTTON"),
        )
        assertTrue("the button must be wired to the screen", home.contains("actions.onOpenFind"))
        assertTrue(
            "HomeActions must carry the callback, or the button does nothing",
            home.contains("val onOpenFind: () -> Unit = {}"),
        )
        // It sits on the status line, which is on screen whether or not the
        // owner shows the navigation row - not as a seventh destination in a
        // row that weights six equally.
        val navRow = home.substringAfter("private fun NavRow")
        assertFalse(
            "the way in must not be a seventh item in the navigation row: that row " +
                "weights its destinations equally and \"Appearance\" already just fits",
            navRow.substringBefore("\n}\n").contains("onOpenFind"),
        )
        assertTrue(
            "the Find button must be drawn above the navigation row's own definition " +
                "(StatusLine, which is always on screen)",
            home.substring(0, home.indexOf("private fun NavRow")).contains("actions.onOpenFind"),
        )
        val activity = repoFile("jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt").readText()
        assertTrue(
            "Home's Find button must open the screen",
            activity.contains("onOpenFind = { nav.go(Screen.FIND) }"),
        )
        assertTrue(
            "and the screen must be one of the app's screens",
            repoFile("jarvis-client/app/src/main/java/com/jarvis/client/ui/Nav.kt")
                .readText().contains("    FIND,"),
        )
    }

    @Test
    fun `the fold and the ranking are the phone's own, not a second set`() {
        // The fold IS SettingsSearch.normalise: one phone, one fold.
        assertEquals(SettingsSearch.normalise("Wi-Fi"), FindAnything.fold("Wi-Fi"))
        assertEquals("jarvis s voice", FindAnything.fold("Jarvis's voice"))
        assertEquals("cafe", FindAnything.fold("café"))
        // The one apostrophe in the whole catalogue is in `settings.voices`'
        // own names ("jarvis's voice"), and that id has no row in the box: on
        // the phone it is the button drawn inside the Voice item
        // (`MenuPlaces.INSIDE`), and the phone-only `entry.voices` id this used
        // to name was retired by the parity audit of 2026-10-10 - one id, one
        // feature (`backend/jarvis_menus.py`). So what is held here is the fold
        // itself, both ways round, plus a real search: the owner's own
        // apostrophe and the catalogue's must fold to the same words, which is
        // what makes the box punctuation-blind.
        val voices = MenuCatalog.MENUS.first { it.id == "settings.voices" }
        assertTrue(
            "an apostrophe typed the app's way must fold to the catalogue's own words",
            voices.names.any { FindAnything.fold(it) == FindAnything.fold("Jarvis's voice") },
        )
        assertTrue(
            "and that fold is the one the box really searches with",
            FindAnything.results("voice", menus, false).any { it.id == "settings.voice" },
        )
        // The desktop's own order: title start, then title at a word start,
        // then title anywhere, then the extra words, then the description.
        val titleStart = FindAnything.score(testRow("Work"), "work")
        val wordStart = FindAnything.score(testRow("The work"), "work")
        val anywhere = FindAnything.score(testRow("Network"), "work")
        val words = FindAnything.score(testRow("Zzz", words = "work"), "work")
        val about = FindAnything.score(testRow("Zzz", about = "work"), "work")
        assertTrue("a title that starts with the words comes first", titleStart < wordStart)
        assertTrue("then one where a word starts with them", wordStart < anywhere)
        assertTrue("then the extra words", anywhere < words)
        assertTrue("and the description last", words < about)
        assertEquals("no match is -1", -1, FindAnything.score(testRow("Zzz"), "work"))
    }

    @Test
    fun `a search finds a place by its name, by a control inside it, and by its description`() {
        assertEquals("brain.work.goals", FindAnything.results("goals", menus, false).first().id)
        assertEquals("brain.work.goals", FindAnything.results("goal", menus, false).first().id)
        assertEquals("settings.web-search", FindAnything.results("web search", menus, false).first().id)
        assertEquals("place.inbox", FindAnything.results("inbox", menus, false).first().id)
        // A control's own name, from Settings' own vocabulary for that row.
        assertTrue(
            "SearXNG is named inside Web search and must find it",
            FindAnything.results("searxng", menus, false).any { it.id == "settings.web-search" },
        )
        assertTrue(
            "Obsidian is named inside Folders and must find it",
            FindAnything.results("obsidian", menus, false).any { it.id == "settings.folders" },
        )
        // A place the phone has and the desktop does not.
        assertTrue(FindAnything.results("past approvals", menus, false).any { it.id == "place.approvals" })
        // One letter is enough to start narrowing.
        assertTrue(FindAnything.results("g", menus, false).isNotEmpty())
        // Whitespace is not a search.
        assertEquals(emptyList<FindAnything.Row>(), FindAnything.results("   ", menus, false))
    }

    @Test
    fun `the list never shuffles between two keystrokes and no place is listed twice`() {
        val once = FindAnything.results("s", menus, false)
        val twice = FindAnything.results("s", menus, false)
        assertEquals(once, twice)
        assertEquals(
            "a place appears twice in one search",
            once.size,
            once.map { it.id }.toSet().size,
        )
        assertEquals(
            "asking for a row that is not there is null, not a crash",
            null,
            FindAnything.row("no.such.place"),
        )
    }

    // ------------------------------------------------------------------ kit --

    /**
     * The two phone menus with no place on this phone AT ALL - not even one
     * inside another card, which is the other half of the same idea and lives
     * in `MenuPlaces.INSIDE` (the parity audit of 2026-10-10 turned eight ids
     * from "desktop only" to "both apps", and every one of them is drawn inside
     * something rather than under an `item(key = ...)` of its own). Each of
     * these two has a reason written down in `ui/FindAnything.kt`:
     *
     *  - `settings.connection` is never hideable and has no Settings row here
     *    (`MenuPlaces` omits it for that reason); its place is Platform checks'
     *    Connection card, which the `entry.checks` row already opens;
     *  - `brain.trust.rush-latch` is the rush banner inside Trust, which is a
     *    desktop tab - an answer line, not a place.
     */
    private val NO_PLACE = setOf("settings.connection", "brain.trust.rush-latch")

    /** A row for the ranking tests only: nothing here is in the real index. */
    private fun testRow(
        title: String,
        about: String = "",
        words: String = "",
    ) = FindAnything.Row(
        id = "test", title = title, about = about, screen = Screen.BRAIN, section = null,
        words = words, menu = false, kind = "card",
    )

    /**
     * The `item(key = ...)` a row really lands on, in the spelling the list
     * holds.
     *
     * Every other screen spells its own item key out, so the row's `section` IS
     * the key. Brain's do not: a plate's item key carries the plates' namespace
     * (BrainScreen's `plateKeyAt`, `PlateList.PLATE_PREFIX`), so a row that names
     * the plate "attention" or "briefing" lands on `brain-plate:attention` and
     * `brain-plate:briefing`. `section` stays the bare plate NAME everywhere else
     * (it is `MenuPlaces`' own vocabulary, and what the screen's heading lookup
     * is handed), which is why the namespace is added here rather than written
     * into every row.
     */
    private fun itemKeyOf(row: FindAnything.Row): String {
        val section = row.section!!
        return if (row.screen == Screen.BRAIN) PlateList.PLATE_PREFIX + section else section
    }

    /**
     * The keys of the lines Brain draws OUTSIDE every heading
     * (`item(key = plateKeyAt("attention"))` and its five neighbours), read from
     * BrainScreen.kt itself.
     *
     * Read from the screen, never from `BrainSections.ALWAYS_DRAWN`: that list is
     * the declaration the screen is held TO (`BrainSectionsTest` and
     * `BrainListTest` compare the two), and reading it here would make this
     * check agree with the label instead of with the screen. It did exactly
     * that - the declaration and this test were both written in the bare names
     * the screen really drew, so a row pointing at "attention" passed while the
     * walk, which looks up `brain-plate:attention`, found nothing.
     */
    private fun alwaysDrawnItemKeys(): Set<String> {
        // The screen's own CODE, not its notes: BrainScreen explains this very
        // defect and quotes the key spellings in backticks, and a key quoted in
        // a note is not a key the list holds. Blanking comments is the project's
        // `code()` habit (BrainListTest, AttentionSettingsTest).
        val src = code(repoFile(CLIENT + "ui/screens/BrainScreen.kt").readText())
        val keys = Regex("item\\(key = plateKeyAt\\(\"([\\w-]+)\"\\)\\)")
            .findAll(src)
            .map { PlateList.PLATE_PREFIX + it.groupValues[1] }
            .toSet()
        assertTrue(
            "BrainScreen.kt draws no `item(key = plateKeyAt(\"...\"))` line at all, so this " +
                "test's own reading of the screen has broken and every check above is vacuous",
            keys.isNotEmpty(),
        )
        return keys
    }

    /** [src] with whole-line `//` comments and block comments blanked, not dropped. */
    private fun code(src: String): String {
        val out = ArrayList<String>()
        var inBlock = false
        for (line in src.lines()) {
            val t = line.trimStart()
            if (inBlock) {
                if (t.contains("*/")) inBlock = false
                out.add("")
                continue
            }
            if (t.startsWith("/*")) {
                if (!t.contains("*/")) inBlock = true
                out.add("")
                continue
            }
            if (t.startsWith("//")) {
                out.add("")
                continue
            }
            out.add(line)
        }
        return out.joinToString("\n")
    }

    /**
     * The `item(key = ...)` rows a screen really draws, by the [Screen] the
     * rows open. A screen with no rows of its own is absent on purpose: a row
     * that names one then fails the check rather than passing it by default.
     */
    private fun itemKeys(screen: Screen): Set<String>? {
        // The Brain draws its rows as PLATES now, not as `item(key = ...)`
        // (the seven foldable headings, merged 2026-10-11):
        // `plate("quiz")` inside a `brainSection(...)`, and a plate comes in two
        // halves through one call (`plate(if (plateDrawn("wiki")) "wiki" else
        // "wiki-hidden")`), which no regular expression over the source reads
        // safely. BrainSections is the screen's own list of them, and
        // BrainSectionsTest holds it to the real `plate("...")` lines one for
        // one - so reading it here keeps the same teeth this check always had,
        // and the seam is checked twice rather than not at all.
        //
        // Both halves are returned in the spelling the list HOLDS, which is the
        // half that decides whether a row can be found: a plate's emitted key is
        // `brain-plate:<name>` (BrainSections' recorder), and the lines outside
        // every heading are drawn under the same namespace by the screen's own
        // `plateKeyAt`. Nothing bare is accepted here, because nothing bare is
        // on the list: the walk looks a key up by exact equality.
        if (screen == Screen.BRAIN) {
            val plates = BrainSections.allPlateKeys().map { PlateList.PLATE_PREFIX + it }
            return (plates + alwaysDrawnItemKeys()).toSet()
        }
        val file = when (screen) {
            Screen.SETTINGS -> "ui/screens/SettingsScreen.kt"
            Screen.HISTORY -> "ui/screens/HistoryScreen.kt"
            Screen.CHECKS -> "ui/screens/ReadinessScreen.kt"
            Screen.FAQ -> "ui/screens/FaqScreen.kt"
            else -> return null
        }
        val src = repoFile(CLIENT + file).readText()
        return Regex("item\\(key\\s*=\\s*\"([\\w.-]+)\"").findAll(src)
            .map { it.groupValues[1] }
            .toSet()
    }

    /**
     * The desktop's `WORDS` from `jarvis-desktop/src/palette.js`, key -> value.
     * Only the top-level string keys: the nested `group_headings` object is
     * read on its own by the test that checks the four headings.
     */
    private fun desktopPaletteWords(): Map<String, String> {
        val js = repoFile("jarvis-desktop/src/palette.js").readText()
        val block = js
            .substringAfter("export const WORDS = Object.freeze({")
            .substringBefore("\n});")
        return Regex("(?m)^ {2}(\\w+):\\s*\"((?:[^\"\\\\]|\\\\.)*)\",?\\s*$")
            .findAll(block)
            .associate { it.groupValues[1] to it.groupValues[2] }
    }

    private fun findSource(): String = repoFile(CLIENT + "ui/FindAnything.kt").readText()

    private fun screenSource(): String = repoFile(CLIENT + "ui/screens/FindScreen.kt").readText()

    /** Walks up from Gradle's working folder (`jarvis-client/app`) to the repository. */
    private fun repoFile(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isFile) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    private companion object {
        const val CLIENT = "jarvis-client/app/src/main/java/com/jarvis/client/"
    }
}
