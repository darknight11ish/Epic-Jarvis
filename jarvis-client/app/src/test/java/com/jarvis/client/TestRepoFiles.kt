package com.jarvis.client

import java.io.File

/**
 * Finds a repository file from a JVM unit test, wherever Gradle started it.
 *
 * Several suites already carry their own copy of this walk-up; this one is
 * shared by the 2026-10-20 Android-audit pins (manifest, MainActivity,
 * UpdateChecker, network security config) so they cannot drift apart.
 */
internal fun repoFile(rel: String): File {
    var d: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
    while (d != null) {
        val f = File(d, rel)
        if (f.isFile) return f
        d = d.parentFile
    }
    error("$rel not found above ${System.getProperty("user.dir")}")
}

/** The text of one repository file (relative to the repository root). */
object SourceFile {
    fun read(rel: String): String = repoFile(rel).readText()
}
