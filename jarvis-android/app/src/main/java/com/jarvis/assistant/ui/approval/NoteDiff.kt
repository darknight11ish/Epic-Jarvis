package com.jarvis.assistant.ui.approval

/** How a line changed between the current note and the proposed one. */
enum class DiffKind { CONTEXT, ADDED, REMOVED, GAP }

data class DiffLine(val kind: DiffKind, val text: String)

data class DiffSummary(val added: Int, val removed: Int) {
    val isEmpty: Boolean get() = added == 0 && removed == 0
}

/**
 * Line-level diffing for note edits.
 *
 * Deliberately pure Kotlin with no Android or Compose types, so the logic is
 * exercised by ordinary JVM unit tests rather than an instrumented run.
 */
object NoteDiff {

    /**
     * Above this, the quadratic LCS table costs more memory than the result is
     * worth on a handset, and nobody approves a 2000-line diff from a lock
     * screen anyway. Larger inputs degrade to a whole-body replacement.
     */
    const val MAX_LINES = 600

    /**
     * Hard ceiling on lines handed to the renderer, whoever produced them. Above
     * this a diff is not something a person reads on a handset; it is something
     * they scroll past before tapping Approve.
     */
    const val MAX_RENDERED_LINES = 1_200

    private val TRUNCATION_MARKER =
        DiffLine(DiffKind.GAP, "@@ diff truncated at $MAX_RENDERED_LINES lines @@")

    /** Unchanged lines kept either side of a change, so edits have context. */
    private const val CONTEXT_LINES = 3

    fun summarize(lines: List<DiffLine>): DiffSummary = DiffSummary(
        added = lines.count { it.kind == DiffKind.ADDED },
        removed = lines.count { it.kind == DiffKind.REMOVED },
    )

    /** Parses a unified diff the desktop already computed. */
    /**
     * A desktop-supplied unified diff, capped.
     *
     * `between` has always bounded its own output; this path had no cap at all, so a
     * whole-document rewrite arrived as however many lines the desktop felt like
     * sending and every one of them was rendered.
     */
    fun fromUnified(diff: String): List<DiffLine> = diff
        .split('\n')
        .asSequence()
        .filterNot { it.startsWith("diff ") || it.startsWith("index ") }
        .filterNot { it.startsWith("--- ") || it.startsWith("+++ ") }
        .map { line ->
            when {
                line.startsWith("@@") -> DiffLine(DiffKind.GAP, line)
                line.startsWith("+") -> DiffLine(DiffKind.ADDED, line.substring(1))
                line.startsWith("-") -> DiffLine(DiffKind.REMOVED, line.substring(1))
                line.startsWith(" ") -> DiffLine(DiffKind.CONTEXT, line.substring(1))
                line.isEmpty() -> DiffLine(DiffKind.CONTEXT, "")
                else -> DiffLine(DiffKind.CONTEXT, line)
            }
        }
        .take(MAX_RENDERED_LINES)
        .toList()
        .let { if (it.size < MAX_RENDERED_LINES) it else it + TRUNCATION_MARKER }

    /** Computes a diff between two whole documents. */
    fun between(before: String, after: String): List<DiffLine> {
        val old = before.split('\n')
        val new = after.split('\n')

        if (old.size > MAX_LINES || new.size > MAX_LINES) {
            return old.map { DiffLine(DiffKind.REMOVED, it) } +
                new.map { DiffLine(DiffKind.ADDED, it) }
        }

        return collapse(walk(old, new))
    }

    /** Classic LCS backtrack, emitting removals before additions at each edit. */
    private fun walk(old: List<String>, new: List<String>): List<DiffLine> {
        val rows = old.size
        val cols = new.size
        // (rows+1) x (cols+1) lengths table, flattened.
        val table = IntArray((rows + 1) * (cols + 1))
        fun at(r: Int, c: Int) = table[r * (cols + 1) + c]

        for (r in rows - 1 downTo 0) {
            for (c in cols - 1 downTo 0) {
                table[r * (cols + 1) + c] = if (old[r] == new[c]) {
                    at(r + 1, c + 1) + 1
                } else {
                    maxOf(at(r + 1, c), at(r, c + 1))
                }
            }
        }

        val out = ArrayList<DiffLine>(rows + cols)
        var r = 0
        var c = 0
        while (r < rows && c < cols) {
            when {
                old[r] == new[c] -> {
                    out += DiffLine(DiffKind.CONTEXT, old[r]); r++; c++
                }
                at(r + 1, c) >= at(r, c + 1) -> {
                    out += DiffLine(DiffKind.REMOVED, old[r]); r++
                }
                else -> {
                    out += DiffLine(DiffKind.ADDED, new[c]); c++
                }
            }
        }
        while (r < rows) out += DiffLine(DiffKind.REMOVED, old[r++])
        while (c < cols) out += DiffLine(DiffKind.ADDED, new[c++])
        return out
    }

    /**
     * Replaces long unchanged stretches with a single [DiffKind.GAP] marker.
     * A one-word change in a long note should not require scrolling past the
     * whole note to find it.
     */
    private fun collapse(lines: List<DiffLine>): List<DiffLine> {
        val keep = BooleanArray(lines.size)
        lines.forEachIndexed { index, line ->
            if (line.kind != DiffKind.CONTEXT) {
                val from = maxOf(0, index - CONTEXT_LINES)
                val to = minOf(lines.lastIndex, index + CONTEXT_LINES)
                for (i in from..to) keep[i] = true
            }
        }
        if (keep.all { it }) return lines

        val out = ArrayList<DiffLine>(lines.size)
        var skipped = 0
        lines.forEachIndexed { index, line ->
            if (keep[index]) {
                if (skipped > 0) {
                    out += DiffLine(DiffKind.GAP, "@@ $skipped unchanged line${if (skipped == 1) "" else "s"} @@")
                    skipped = 0
                }
                out += line
            } else {
                skipped++
            }
        }
        if (skipped > 0) {
            out += DiffLine(DiffKind.GAP, "@@ $skipped unchanged line${if (skipped == 1) "" else "s"} @@")
        }
        return out
    }

    /** Picks the best available representation from what the desktop sent. */
    fun forPayload(diff: String?, before: String?, after: String?): List<DiffLine>? = when {
        !diff.isNullOrBlank() -> fromUnified(diff)
        before != null && after != null -> between(before, after)
        else -> null
    }
}
