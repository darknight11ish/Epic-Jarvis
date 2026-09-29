package com.jarvis.client

import com.jarvis.client.data.CheckOutcome
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.PendingItem
import com.jarvis.client.net.Projects
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Apps in Projects, the phone's half (docs/APPS-IN-PROJECTS-DESIGN.md
 * sections 5, 6 and 7.4).
 *
 * These build their OWN JSON to the frozen shapes of section 7.1. They are
 * NOT yet checked against the shared fixture `contract/projects-cases.json`:
 * once the backend regenerates it (tools/gen_projects_cases.py) with the
 * `app` answers and `words`, re-point these at it, like [ProjectsTest].
 */
class AppProjectsTest {

    private fun obj(text: String): JsonObject = Json.parseToJsonElement(text) as JsonObject

    private val fullApp = """
        {"name": "notes", "type": "web", "title": "Notes app",
         "git_ok": true, "said": "",
         "main": {"head": "a1b2c3d", "subject": "Jarvis: Add a dark mode", "at": 1759000000.0, "versions": 7},
         "tasks": [
           {"task": "a1b2c3d4e5f6", "title": "Add a dark mode", "started": 1759000000.0,
            "source": "jarvis", "files": 3, "added": 41, "removed": 2, "older_main": false, "waiting": false},
           {"task": "0123456789ab", "title": "Fix <b>the</b> **bar**", "started": 1759000500.0,
            "source": "pasted", "files": 1, "added": 5, "removed": 0, "older_main": true, "waiting": true}
         ],
         "merge": {"waiting": "0123456789ab",
                   "last": {"task": "ffffffffffff", "outcome": "merged", "message": "Added to your app.", "at": 1759000100.0}}}
    """.trimIndent()

    private fun project(app: String?): String = """
        {"id": "${"0".repeat(31)}a", "name": "Notes app", "kind": "coding", "instructions": "", "notes": [],
         "shareable": false, "benchmarks": 0, "benchmark_list": []
         ${if (app != null) ", \"app\": $app" else ""}}
    """.trimIndent()

    // ------------------------------------------------------------ parsing ---

    @Test
    fun `an app reads every field of the frozen shape`() {
        val p = Projects.parseProject(obj(project(fullApp)))!!
        val app = p.app!!
        assertEquals("notes", app.name)
        assertEquals("web", app.type)
        assertEquals("Notes app", app.title)
        assertTrue(app.gitOk)
        assertEquals("", app.said)
        val main = app.main!!
        assertEquals("a1b2c3d", main.head)
        assertEquals("Jarvis: Add a dark mode", main.subject)
        assertEquals(1759000000.0, main.at!!, 1e-9)
        assertEquals(7, main.versions)
        assertEquals(2, app.tasks.size)
        assertEquals(2, app.openTasks)
        val t = app.tasks[0]
        assertEquals("a1b2c3d4e5f6", t.task)
        assertEquals("jarvis", t.source)
        assertEquals(3, t.files)
        assertEquals(41, t.added)
        assertEquals(2, t.removed)
        assertFalse(t.olderMain)
        assertFalse(t.waiting)
        assertEquals("3 files, +41 -2", Projects.changeCounts(t))
        assertEquals("1 file, +5 -0", Projects.changeCounts(app.tasks[1]))
        assertTrue(app.tasks[1].olderMain)
        assertTrue(app.tasks[1].waiting)
        assertEquals("0123456789ab", app.waitingTask)
        assertTrue(app.mergeWaiting)
        val last = app.last!!
        assertEquals("ffffffffffff", last.task)
        assertEquals("merged", last.outcome)
        assertEquals(1759000100.0, last.at!!, 1e-9)
    }

    @Test
    fun `text from the PC is kept as plain text, never changed`() {
        val app = Projects.parseProject(obj(project(fullApp)))!!.app!!
        assertEquals("Fix <b>the</b> **bar**", app.tasks[1].title)
    }

    @Test
    fun `the list's short form and unlinked apps are read or ignored`() {
        val body = obj(
            """{"projects": [
                 {"id": "${"1".repeat(32)}", "name": "Notes app", "kind": "coding",
                  "app": {"name": "notes", "type": "android", "tasks": 3, "merge_waiting": true}},
                 {"id": "${"2".repeat(32)}", "name": "Half marathon", "kind": "life", "app": null}],
               "unlinked_apps": [{"name": "old", "type": "web", "title": "Old"}], "max": 30}""",
        )
        val list = Projects.parseList(body)!!
        val a = list.projects[0].app!!
        assertEquals("android", a.type)
        assertEquals(3, a.openTasks)
        assertTrue(a.tasks.isEmpty())
        assertTrue(a.mergeWaiting)
        assertNull(a.waitingTask)
        assertNull(list.projects[1].app)
    }

    @Test
    fun `missing or odd fields never break the read`() {
        assertNull(Projects.parseProject(obj(project(null)))!!.app)
        assertNull(Projects.parseProject(obj(project("null")))!!.app)
        assertNull("no name is no app", Projects.parseApp(obj("""{"type": "web"}""")))
        assertNull(Projects.parseApp(null))
        val bare = Projects.parseApp(obj("""{"name": "x"}"""))!!
        assertEquals("", bare.type)
        assertTrue("no git_ok field reads as fine", bare.gitOk)
        assertNull(bare.main)
        assertTrue(bare.tasks.isEmpty())
        assertEquals(0, bare.openTasks)
        assertNull(bare.last)
        assertFalse(bare.mergeWaiting)
        val odd = Projects.parseApp(
            obj("""{"name": "x", "type": "desktop", "tasks": ["nope", {"title": "no id"}, {"task": "aaaaaaaaaaaa"}],
                    "merge": {"waiting": null, "last": null}, "main": {"head": 5}}"""),
        )!!
        assertEquals("", odd.type)
        assertEquals(listOf("aaaaaaaaaaaa"), odd.tasks.map { it.task })
        assertEquals("empty", odd.tasks[0].source)
        assertEquals(0, odd.main!!.versions)
        // Git missing: git_ok false, its sentence, no tasks, no main.
        val nogit = Projects.parseApp(
            obj("""{"name": "x", "type": "web", "title": "T", "git_ok": false,
                    "said": "git is not installed on this PC ...", "tasks": [], "main": null}"""),
        )!!
        assertFalse(nogit.gitOk)
        assertTrue(nogit.said.startsWith("git is not installed"))
        assertNull(nogit.main)
    }

    @Test
    fun `a task's detail reads its files, diff, too_big and refused`() {
        val d = Projects.parseTaskDetail(
            obj(
                """{"task": "a1b2c3d4e5f6", "title": "T", "source": "weird", "files": 2, "added": 3, "removed": 1,
                     "older_main": false, "waiting": false,
                     "list": [{"path": "src/App.tsx", "added": "40", "removed": "2"}, {"added": "1"}],
                     "diff": "diff --git a/x b/x", "too_big": false, "refused": ""}""",
            ),
        )!!
        assertEquals("empty", d.summary.source)
        assertEquals(listOf("src/App.tsx"), d.list.map { it.path })
        assertEquals("40", d.list[0].added)
        assertEquals("diff --git a/x b/x", d.diff)
        assertFalse(d.tooBig)
        val big = Projects.parseTaskDetail(
            obj("""{"task": "a1b2c3d4e5f6", "diff": "", "too_big": true, "refused": "Too big to show on one card."}"""),
        )!!
        assertTrue(big.tooBig)
        assertEquals("Too big to show on one card.", big.refused)
        assertNull(Projects.parseTaskDetail(obj("""{"title": "no id"}""")))
        val reply = Projects.Reply(200, obj("""{"ok": true, "task": {"task": "a1b2c3d4e5f6", "title": "T"}}"""))
        assertEquals("T", Projects.taskOf(reply)!!.summary.title)
        assertNull(Projects.taskOf(Projects.Reply(404, obj("""{"ok": false, "error": "no such task"}"""))))
    }

    // ---------------------------------------------------- outcome sentences --

    @Test
    fun `every merge outcome has its fixed sentence, word for word`() {
        val want = mapOf(
            "merged" to "Added to your app.",
            "denied" to "Not added - you said no. The change is kept aside.",
            "timed_out" to "Not added - the card timed out. The change is kept aside.",
            "stale" to "Not added - the app or the change moved after the card was shown. Look at the new card.",
            "unsaved" to "Not added - the app's own folder has changes that are not saved in git.",
            "conflict" to "Not added - the change did not fit the app's newer version. Nothing was changed; discard it and ask again.",
            "withdrawn" to "Not added - the change was thrown away before you answered.",
            "refused" to "Not added.",
            "failed" to "Not added - something went wrong. Nothing was changed.",
        )
        assertEquals(want, Projects.MERGE_OUTCOMES)
        for ((k, v) in want.filterKeys { it != "refused" }) {
            // The phone shows its own fixed sentence whatever message came with it.
            assertEquals(k, v, Projects.mergeSentence(Projects.MergeLast("t", k, "something else", null)))
        }
        // "refused" carries the gate's own reason after "Not added.".
        assertEquals("Not added. The task is gone.",
            Projects.mergeSentence(Projects.MergeLast("t", "refused", "Not added. The task is gone.", null)))
        assertEquals("Not added.", Projects.mergeSentence(Projects.MergeLast("t", "refused", "", null)))
        // A word this phone does not know shows the PC's own message.
        assertEquals("New words.", Projects.mergeSentence(Projects.MergeLast("t", "brand_new", "New words.", null)))
    }

    @Test
    fun `the words for apps do not clash with the shared projects words`() {
        assertTrue(Projects.WORDS.keys.intersect(Projects.APP_WORDS.keys).isEmpty())
        assertEquals("Web app", Projects.typeWords(Projects.parseApp(obj("""{"name":"x","type":"web"}"""))!!))
        assertEquals("Android app", Projects.typeWords(Projects.parseApp(obj("""{"name":"x","type":"android"}"""))!!))
        assertEquals("You pasted this change in on your PC.", Projects.sourceWords("pasted"))
    }

    // ------------------------------------------------------------- paging ---

    private fun bigDiff(): String {
        val sb = StringBuilder()
        sb.append("diff --git a/src/App.tsx b/src/App.tsx\n--- a/src/App.tsx\n+++ b/src/App.tsx\n@@ -1,3 +1,4 @@\n")
        var i = 0
        while (sb.length < 58_000) {
            sb.append(if (i % 3 == 0) "+added line $i\n" else if (i % 3 == 1) "-removed line $i\n" else " same line $i\n")
            i++
        }
        sb.append("+").append("x".repeat(1_000)).append('\n') // one very long line
        sb.append("\n") // an empty line
        sb.append("+last line")
        assertTrue(sb.length <= 60_000)
        return sb.toString()
    }

    @Test
    fun `the pages hold the whole diff and the last page ends it`() {
        val diff = bigDiff()
        val pages = Projects.diffPages(diff)
        assertTrue("a big change is several pages", pages.size > 5)
        assertEquals("nothing dropped, nothing added", diff, Projects.diffText(pages))
        for (page in pages.dropLast(1)) assertEquals(Projects.DIFF_LINES_PER_PAGE, page.size)
        assertTrue(pages.last().size in 1..Projects.DIFF_LINES_PER_PAGE)
        assertTrue("no line is a giant Text", pages.flatten().all { it.text.length <= Projects.DIFF_PIECE })
        assertEquals("+last line", pages.last().last().text)
        assertTrue("the long line is in pieces", pages.flatten().count { it.continued } >= 3)
        assertTrue(Projects.diffPages("").isEmpty())
        assertEquals("", Projects.diffText(emptyList()))
        // Exactly one page when it fits.
        assertEquals(1, Projects.diffPages("+a\n-b\n c").size)
        assertEquals("+a\n-b\n c", Projects.diffText(Projects.diffPages("+a\n-b\n c")))
    }

    @Test
    fun `lines are drawn by their first character`() {
        val kinds = Projects.diffLines(
            "diff --git a/x b/x\nindex 1..2\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+new\n-old\n same\n",
        ).map { it.kind }
        assertEquals(
            listOf(
                Projects.DiffKind.META, Projects.DiffKind.META, Projects.DiffKind.META, Projects.DiffKind.META,
                Projects.DiffKind.HUNK, Projects.DiffKind.ADDED, Projects.DiffKind.REMOVED,
                Projects.DiffKind.CONTEXT, Projects.DiffKind.CONTEXT,
            ),
            kinds,
        )
        // A continued piece keeps the colour of its line.
        val long = Projects.diffLines("-" + "y".repeat(700))
        assertTrue(long.size >= 3)
        assertTrue(long.all { it.kind == Projects.DiffKind.REMOVED })
    }

    // ------------------------------------------------------------- Merge ----

    private fun detail(diff: String = "+a", tooBig: Boolean = false, refused: String = "", waiting: Boolean = false) =
        Projects.TaskDetail(
            summary = Projects.TaskSummary("a1b2c3d4e5f6", "T", null, "jarvis", 1, 1, 0, false, waiting),
            list = emptyList(),
            diff = diff,
            tooBig = tooBig,
            refused = refused,
        )

    @Test
    fun `Merge opens only after the last page has been shown`() {
        val d = detail()
        assertEquals(Projects.aw("merge_locked"), Projects.mergeBlock(d, 3, 0, false, true))
        assertEquals(Projects.aw("merge_locked"), Projects.mergeBlock(d, 3, 1, false, true))
        assertNull(Projects.mergeBlock(d, 3, 2, false, true))
        assertNull("one page is the last page", Projects.mergeBlock(d, 1, 0, false, true))
        assertFalse(Projects.readToEnd(0, 0))
        assertTrue(Projects.readToEnd(3, 2))
        assertFalse(Projects.readToEnd(3, 1))
    }

    @Test
    fun `Merge stays shut on a stale link, a refusal, a too-big change, no change or a waiting card`() {
        val d = detail()
        assertEquals(Projects.w("stale"), Projects.mergeBlock(d, 1, 0, false, canAct = false))
        assertEquals("Too big to show on one card.",
            Projects.mergeBlock(detail(refused = "Too big to show on one card."), 0, 0, false, true))
        assertEquals(Projects.aw("task_too_big"), Projects.mergeBlock(detail(tooBig = true), 0, 0, false, true))
        assertEquals(Projects.aw("task_none"), Projects.mergeBlock(detail(diff = ""), 0, 0, false, true))
        assertEquals(Projects.aw("merge_card_up"), Projects.mergeBlock(d, 1, 0, cardWaitingForApp = true, canAct = true))
        assertEquals(Projects.aw("merge_card_up"), Projects.mergeBlock(detail(waiting = true), 1, 0, false, true))
    }

    @Test
    fun `merge and discard are held on a stale link, and start and paste are the PC's`() {
        assertTrue(Projects.heldOnStale("app_task_merge"))
        assertTrue(Projects.heldOnStale("app_task_discard"))
        val p = "0".repeat(31) + "a"
        val t = "a1b2c3d4e5f6"
        assertEquals("/api/projects/$p/app/tasks/$t/merge", Projects.writePath("app_task_merge", p, task = t))
        assertEquals("/api/projects/$p/app/tasks/$t/discard", Projects.writePath("app_task_discard", p, task = t))
        assertEquals("/api/projects/$p/app/tasks/$t", Projects.taskPath(p, t))
        for (bad in listOf("", "../x", "A1B2C3D4E5F6", "a1b2c3d4e5f", "a1b2c3d4e5f6a")) {
            assertNull(bad, Projects.taskPath(p, bad))
            assertNull(bad, Projects.writePath("app_task_merge", p, task = bad))
        }
        assertNull(Projects.writePath("app_task_merge", "nope", task = t))
        assertNull(Projects.writePath("app_task_merge", p))
        for (pcOnly in listOf("app_task_start", "app_task_files", "app_create")) {
            assertNull("the phone has no path for $pcOnly", Projects.writePath(pcOnly, p, task = t))
            assertTrue(pcOnly, pcOnly in Projects.PC_ONLY)
        }
        // The existing rules are untouched.
        assertFalse(Projects.heldOnStale("shareable", on = false))
        assertEquals("/api/projects/$p/delete", Projects.writePath("delete", p))
    }

    @Test
    fun `the answers to Merge and Discard read as a card, a refusal or done`() {
        val card = Projects.said(
            Projects.Reply(202, obj("""{"ok": true, "waiting": true, "message": "Waiting for your approval on the card."}""")),
            "Done.",
        )
        assertTrue(card.waiting)
        assertTrue(card.changed)
        assertEquals("Waiting for your approval on the card.", card.said)
        val refused = Projects.said(
            Projects.Reply(400, obj("""{"ok": false, "error": "this task has not changed anything yet"}""")),
            "Done.",
        )
        assertFalse(refused.changed)
        assertEquals("This task has not changed anything yet.", refused.said)
        val busy = Projects.said(
            Projects.Reply(409, obj("""{"ok": false, "error": "A card for this app is already waiting - answer it first."}""")),
            "Done.",
        )
        assertFalse(busy.changed)
        assertEquals("A card for this app is already waiting - answer it first.", busy.said)
        val gone = Projects.said(Projects.Reply(200, obj("""{"ok": true, "discarded": true}""")), "Discarded.")
        assertTrue(gone.changed)
        assertFalse(gone.waiting)
        assertEquals("Discarded.", gone.said)
    }

    // ------------- the merge card cannot be approved from a widget or a notification

    private fun item(json: String): PendingItem = JarvisJson.decodeFromString(PendingItem.serializer(), json)

    /** What the PC raises for `app_merge_change`: risky ("no", local), so heavy. */
    private val mergeCard = item(
        """{"id": "m1", "title": "Add its change to one of your apps",
             "summary": "Add the change shown on the card to your app's files.",
             "tier": "ask", "action": "app_merge_change", "detail": "Changes 3 files (+41 -2) ...",
             "risk": {"reversible": "no", "reach": "local", "swipe_ok": false, "classified": true},
             "notice": {"title": "Jarvis wants to change one of your apps", "body": "Nothing has happened yet.",
                        "weight": "heavy", "deny_ok": true, "approve_ok": false}}""",
    )

    @Test
    fun `the merge card is heavy and risky, and the phone may approve it only after the check`() {
        assertNotNull(mergeCard.notice)
        assertTrue("heavy: slower Approve, full text first", mergeCard.isHeavy)
        assertTrue("it interrupts (cannot be undone)", mergeCard.shouldInterrupt)
        assertFalse("never a swipe", mergeCard.swipeable)
        assertFalse("not PC-only: the owner allowed the phone (2026-09-29)", mergeCard.pcOnly)
        assertFalse("the notice never offers a one-tap approve", mergeCard.notice!!.approveOk)
        assertTrue(SecurityRules.riskyByToday(mergeCard))
        // Default settings still ask for the fingerprint or PIN on a risky card.
        assertTrue(SecurityRules.approvalNeedsCheck(Security(), mergeCard))
        // No lock, no risky approval: a phone that cannot check refuses.
        assertTrue(SecurityRules.afterApprovalCheck(Security(), CheckOutcome.UNAVAILABLE) is SecurityRules.Verdict.Stop)
        assertTrue(SecurityRules.afterApprovalCheck(Security(), CheckOutcome.CANCELLED) is SecurityRules.Verdict.Stop)
        assertTrue(SecurityRules.afterApprovalCheck(Security(), CheckOutcome.CONFIRMED) is SecurityRules.Verdict.Go)
    }

    private fun sourceDir(rel: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val f = File(dir, rel)
            if (f.isDirectory) return f
            dir = dir.parentFile
        }
        error("$rel not found above ${System.getProperty("user.dir")}")
    }

    /** Code lines only: comments say what NOT to do and would trip a plain search. */
    private fun codeLines(f: File): List<String> =
        f.readLines().filterNot {
            val s = it.trim()
            s.startsWith("//") || s.startsWith("*") || s.startsWith("/*")
        }

    @Test
    fun `the widget and the notification never approve - Deny and opening the app are all they do`() {
        val base = "jarvis-client/app/src/main/java/com/jarvis/client"
        val files = listOf("widget", "service").flatMap { sourceDir("$base/$it").listFiles().orEmpty().toList() }
            .filter { it.name.endsWith(".kt") }
        assertTrue("found the widget and service sources", files.any { it.name == "ApprovalWidget.kt" } &&
            files.any { it.name == "ApprovalNotifier.kt" })
        val approving = Regex("""approve\s*=\s*true|\.approve\(|decideDetached\(|Approve\w*Callback""")
        val deciding = Regex("""JarvisRuntime\.decide\w*\(""")
        for (f in files) {
            for (line in codeLines(f)) {
                assertFalse("${f.name} must not approve: $line", approving.containsMatchIn(line))
                if (deciding.containsMatchIn(line)) {
                    assertTrue("${f.name}: a decision from here can only be a Deny: $line", "approve = false" in line)
                }
            }
        }
        // The widget's way to Approve is to open the app, where the card and the check are.
        val widget = codeLines(files.first { it.name == "ApprovalWidget.kt" }).joinToString("\n")
        assertTrue(widget.contains("actionStartActivity<MainActivity>()"))
        // The notification carries exactly one action, and it is Deny.
        val notifier = codeLines(files.first { it.name == "ApprovalNotifier.kt" }).joinToString("\n")
        assertEquals(1, Regex("""addAction\(""").findAll(notifier).count())
        assertTrue(notifier.contains("denyIntent(context, item, notificationId)"))
    }
}
