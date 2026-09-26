plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

/**
 * The commit this build is made from: CI's GITHUB_SHA, else `git rev-parse`,
 * else "unknown". Through `providers`, so the configuration cache
 * (gradle.properties) knows what it depends on. Only ever hex or "unknown",
 * because it is pasted into generated Java as a string.
 */
fun gitSha(): String {
    val fromCi = providers.environmentVariable("GITHUB_SHA").orNull?.trim().orEmpty()
    val sha = fromCi.ifEmpty {
        runCatching {
            providers.exec {
                commandLine("git", "rev-parse", "HEAD")
                isIgnoreExitValue = true
            }.standardOutput.asText.get().trim()
        }.getOrDefault("")
    }
    return if (Regex("^[0-9a-f]{7,40}$").matches(sha)) sha else "unknown"
}

/**
 * Android's version number for this build: CI's run number for this
 * workflow, which only goes up, or 1 for a build made anywhere else.
 *
 * It used to be pinned at 1, so ANY build installed over any other and kept
 * the app's data - including an older one, or a debuggable one (security
 * audit L3). Android refuses to install a lower number over a higher one
 * (`adb install -r` says INSTALL_FAILED_VERSION_DOWNGRADE), so with the run
 * number an older build can no longer replace a newer one. A re-run of the
 * same workflow run keeps its number, which Android accepts as equal.
 */
fun buildVersionCode(): Int =
    providers.environmentVariable("GITHUB_RUN_NUMBER").orNull?.trim()
        ?.toIntOrNull()?.takeIf { it in 1..2_100_000_000 } ?: 1

/**
 * The version people see (Android's app info, and About in the app): the one
 * version number Jarvis shares across the desktop, the phone and the backend,
 * read from the VERSION file at the top of the repository (0.2.0), with the
 * last part replaced by this build's number on CI - the same shape as the
 * desktop installer's version (desktop-release.yml). So a CI build reads
 * "0.2.57", and a build made anywhere else reads what VERSION says. Through
 * `providers`, so the configuration cache knows it depends on the file.
 */
fun buildVersionName(): String {
    val base = providers.fileContents(layout.projectDirectory.file("../../VERSION"))
        .asText.orNull?.trim().orEmpty()
    val parts = base.split(".")
    if (parts.size != 3 || parts.any { it.toIntOrNull() == null }) {
        throw GradleException(
            "VERSION at the top of the repository must be major.minor.patch, not '$base'")
    }
    val run = providers.environmentVariable("GITHUB_RUN_NUMBER").orNull?.trim()
        ?.toIntOrNull()?.takeIf { it in 1..2_100_000_000 }
    return if (run != null) "${parts[0]}.${parts[1]}.$run" else base
}

/** When [gitSha]'s commit was made, in seconds since 1970, or 0 when git cannot say. */
fun gitCommitTime(): Long = runCatching {
    providers.exec {
        commandLine("git", "log", "-1", "--format=%ct", "HEAD")
        isIgnoreExitValue = true
    }.standardOutput.asText.get().trim().toLong()
}.getOrDefault(0L)

android {
    namespace = "com.jarvis.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.jarvis.client"
        // 33, not 30: RuntimeShader/AGSL for the Nucleus face needs 33, and
        // taking 30 would mean a GLES fallback branch carried forever.
        minSdk = 33
        targetSdk = 36
        versionCode = buildVersionCode()
        // Cosmetic - versionCode above is what Android compares - but it is
        // the number the owner reads in About and quotes in a bug report, so
        // it is the shared version (buildVersionName), not a fixed "0.1".
        versionName = buildVersionName()

        // There was no instrumentation runner, so there was nowhere to put a
        // test that actually starts the app. That is the gap that let a crash
        // in onCreate ship green: the suite compiled the APK and ran unit
        // tests, and never once launched it.
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // The only native code in the app is ONNX Runtime (the "hey Jarvis"
        // spotter). Two of its four ABIs: arm64 for the phone, x86_64 for the
        // CI emulator that starts the release APK. 32-bit ARM and x86 would
        // add ~13 MB for devices this app will never be installed on
        // (minSdk 33 phones are 64-bit).
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }

        // Which commit this build is, for "a newer version is available"
        // (net/UpdateCheck.kt): the phone compares it with the name of the
        // APK on the client-latest release, jarvis-client-<first 7>.apk
        // (.github/workflows/jarvis-client.yml). CI's own GITHUB_SHA first -
        // it is the commit that release step names - and git otherwise.
        // "unknown" if neither answers, and the phone then says it cannot
        // compare rather than guessing.
        buildConfigField("String", "GIT_SHA", "\"${gitSha()}\"")
        // When that commit was made, in seconds. A release published before
        // it is older than this build, not newer. 0 when unknown.
        buildConfigField("long", "GIT_COMMIT_TIME", "${gitCommitTime()}L")
    }

    // The shared debug key, at keystore/debug.keystore - written there by CI from
    // the DEBUG_KEYSTORE_B64 secret, never committed (keystore/README.md). Without it AGP mints
    // ~/.android/debug.keystore per machine, and a CI runner is a fresh machine
    // every run - so each build was signed with a different certificate and
    // `adb install -r` over the previous one failed with
    // INSTALL_FAILED_UPDATE_INCOMPATIBLE. The only way through was `adb uninstall`,
    // which wipes the pairing secret, the auth token, the device id and anything
    // still queued offline.
    //
    // Guarded on existence rather than assumed: a checkout of this module alone,
    // without the repository around it, falls back to AGP's generated key and still
    // builds. EXCEPT a release build in CI: see verifyReleaseSigningKey below,
    // which stops it rather than let it quietly sign with a throwaway key.
    signingConfigs {
        getByName("debug") {
            val shared = rootProject.file("../keystore/debug.keystore")
            if (shared.exists()) {
                storeFile = shared
                storePassword = "android"
                keyAlias = "androiddebugkey"
                keyPassword = "android"
            }
        }
    }

    buildTypes {
        debug { isMinifyEnabled = false }
        release {
            // On, finally. The blocker recorded here for months was "this needs
            // the kotlinx-serialization keep rules" — and the library has
            // shipped them since 1.5: kotlinx-serialization-core 1.7.3, the
            // exact version declared below, carries
            // META-INF/com.android.tools/r8/kotlinx-serialization-r8.pro, and
            // OkHttp 4.12.0 carries META-INF/proguard/okhttp3.pro. R8 consumes
            // both without being asked. Checked by unzipping the artifacts, not
            // by reading about them.
            //
            // This mattered more than a smaller APK, and it is now settled:
            // the workflow publishes THIS build, not the debug one. It gates
            // on an emulator actually installing and starting the shrunk APK
            // before the release is cut, so a shrinker fault cannot ship
            // green. A debuggable build would have ART's optimisations off and
            // every class interpreted — app and libraries alike, including the
            // reactor's frame loop — and would leave `adb shell run-as` open
            // on the data directory, where hardware Keystore binding stops a
            // key being EXTRACTED but not USED by anything running as the app.
            //
            // (This paragraph used to assert the published artifact WAS the
            // debug one. That stopped being true when the release gate landed,
            // and an audit caught the comment still arguing for a decision
            // already made — which would leave a reader thinking the shipped
            // APK is debuggable when it is not.)
            //
            // Signed with the same shared debug key as the debug build, so
            // `adb install -r` over an existing install still works: the
            // certificate is what has to match, not the build type.
            //
            // THE TRIPWIRE ON THAT KEY, recorded here because this is where
            // someone will be standing when it matters. Android decides
            // whether an APK may replace an installed app by CERTIFICATE, and
            // a same-signature update inherits the existing data directory and
            // the Keystore alias - so anyone holding this key can build an app
            // the phone accepts as an update to this one and simply ask the
            // Keystore to decrypt the pairing token. No root, no `run-as`.
            //
            // That door was open once: the first shared key WAS committed
            // here, in a repository that was public. It was replaced on
            // 2026-09-19 and removed from history. The key now lives only in
            // the DEBUG_KEYSTORE_B64 repository secret, and CI writes it to
            // keystore/debug.keystore for the build (see keystore/README.md).
            // Never commit it again. The replacement cost one uninstall and a
            // re-pair on the phone, because the new certificate did not match
            // the installed one - which is what any future rotation costs too.
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = signingConfigs.getByName("debug")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    testOptions {
        unitTests {
            // The pattern engine is pure maths over androidx Color, but a stray
            // android.* call in a transitive would otherwise throw "not mocked"
            // rather than returning something the test can assert on.
            isReturnDefaultValues = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        // Two libraries each carry these licence copies at the same path, and
        // an APK holds only one file per path. They used to be EXCLUDED,
        // which left the APK with no copy at all; now the first one is kept.
        // The full notices (every library, with the Apache text) are in
        // assets/licenses/NOTICES.txt, shown under FAQ -> About.
        resources { pickFirsts += "/META-INF/{AL2.0,LGPL2.1}" }
        // Compressed in the APK and unpacked at install, rather than stored
        // uncompressed: ONNX Runtime's library is ~15 MB per ABI raw and
        // ~7 MB compressed, and a sideloaded APK's download size is the one
        // the owner waits for. Its .so files are 16 KB page-aligned
        // (checked), so either way loads on Android 15's 16 KB devices.
        jniLibs { useLegacyPackaging = true }
    }
}

// A RELEASE build in CI without the shared key fails, instead of quietly
// signing with a key this machine just made (security audit H1). That quiet
// fallback is exactly what happened: from 19 Sep 2026 the smoke job rebuilt
// the release APK on a machine with no key restored, and every published
// build carried a different throwaway certificate, so none would install
// over the one before it without an uninstall that wipes the pairing.
//
// Only release, only CI. Debug builds (the unit tests, the emulator tests)
// still fall back to a generated key, because nothing signed that way is
// published, and a local release build outside CI still works for anyone
// building the module on its own. GitHub Actions sets CI=true on every run.
//
// Checked when the task RUNS, not while Gradle reads this file, so an
// `assembleDebug` in a job without the key is not stopped by it. The values
// are captured as a File and a Provider, which the configuration cache
// (gradle.properties) can store.
val releaseKeyFile = rootProject.file("../keystore/debug.keystore")
val onCi = providers.environmentVariable("CI")
val verifyReleaseSigningKey = tasks.register("verifyReleaseSigningKey") {
    val keyFile = releaseKeyFile
    val ci = onCi
    doLast {
        if (ci.orNull.equals("true", ignoreCase = true) && !keyFile.exists()) {
            throw GradleException(
                "The shared signing key is missing at ${keyFile.path}, and this is a " +
                    "release build in CI. Stopping on purpose: without it the build tools " +
                    "would sign with a throwaway key, and the phone would refuse to install " +
                    "the APK over the copy it already has. Restore the key from the " +
                    "DEBUG_KEYSTORE_B64 secret first (see keystore/README.md).",
            )
        }
    }
}
// configureEach, not named(): AGP registers preReleaseBuild later than this
// line runs, and configureEach also reaches tasks registered afterwards.
tasks.configureEach {
    if (name == "preReleaseBuild") dependsOn(verifyReleaseSigningKey)
}

dependencies {
    // NOT the 2026.08.00 the brief pins. That BOM resolves Compose 1.12.0,
    // whose every artifact declares minCompileSdk 37, and CheckAarMetadata
    // enforces that as a hard error. §3 also forbids compiling against 37
    // because it is Beta, so the two requirements cannot both be met.
    //
    // Surveying the BOMs by the minCompileSdk in their own AAR metadata:
    // 1.12.x needs 37, everything from 1.11.3 back to 1.9.1 needs 35. Compose
    // never required 36, so 2026.06.00 is the newest BOM usable here.
    //
    // The brief gives a reason for compileSdk 36 and none for this particular
    // BOM, so the BOM is the constraint that yields.
    implementation(platform("androidx.compose:compose-bom:2026.06.00"))

    implementation("androidx.core:core-ktx:1.15.0")
    // 1.12.4, not 1.9.3. androidx.activity is not managed by the Compose BOM, so
    // that pin was real rather than decorative: resolving the graph in CI shows
    // core-ktx and lifecycle floating up to 1.16.0 and 2.9.4 on their own, while
    // activity stayed at a November 2024 release hosting a 2026 Compose runtime
    // under targetSdk 36 — where edge-to-edge enforcement changed and
    // MainActivity calls enableEdgeToEdge(). 1.12.4 is the last patch of the
    // generation contemporaneous with Compose 1.11.3; 1.13.0 is stable but newer
    // than the BOM, and 1.14.x is alpha.
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    // Used directly (LazyColumn, background, KeyboardOptions) rather than relied on
    // as a material3 transitive.
    implementation("androidx.compose.foundation:foundation")

    // The home-screen approval widget. 1.1.1, not a newer release: it is the
    // exact version the retired jarvis-android/ module already compiled
    // successfully against (compileSdk 35, Compose BOM 2024.10.01) - the only
    // real precedent for this dependency working anywhere in this monorepo,
    // and this project has no local build to verify a different choice
    // against. compileSdk 36 here is a ceiling raised from that module's 35,
    // never lowered, so its own minCompileSdk requirement is still satisfied.
    implementation("androidx.glance:glance-appwidget:1.1.1")
    implementation("androidx.glance:glance:1.1.1")

    // The serialization compiler plugin is applied in build.gradle.kts but no
    // runtime was declared, so the first @Serializable anyone wrote would have
    // failed to resolve rather than working. Step 2's event models need it.
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    // The transport. OkHttp rather than Ktor because the SSE stream wants a
    // socket held open for an hour with no read timeout, and chat wants a
    // chunked body cancelled mid-flight to interrupt generation - both are
    // one-liners here.
    // A fingerprint instead of a tap for irreversible and outbound decisions -
    // the one item on the brief's list a browser genuinely cannot do.
    implementation("androidx.biometric:biometric:1.1.0")
    // Not used directly - this app has no fragments of its own and is pure
    // Compose. It is here to raise a floor that biometric:1.1.0 sets too low:
    // it depends on androidx.fragment 1.2.5, and `registerForActivityResult`
    // needs 1.3.0 or newer. Gradle takes the highest, so declaring the minimum
    // is all this does.
    //
    // Found by building the release variant for the first time. The check is
    // `InvalidFragmentVersionForActivityResult`, and it is fatal only under
    // lintVitalRelease - which runs on release builds and nothing else - so it
    // had never run at all. That is the whole argument for building this
    // variant in CI: the failure was latent, not new.
    //
    // It is also not merely a lint nag. MainActivity registers two permission
    // contracts at construction, and BiometricPrompt - the gate that rule 4
    // leans on for irreversible approvals - drives a fragment internally.
    implementation("androidx.fragment:fragment:1.3.0")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okio:okio:3.6.0")

    // Runs the "hey Jarvis" spotter (voice/OrtWakeModels.kt) on the phone.
    // Microsoft's official build, from Maven Central. PINNED to 1.22.0 and
    // not to be bumped without unzipping the new AAR first: 1.30.0's
    // AndroidManifest adds INTERNET, ACCESS_NETWORK_STATE and a
    // TelemetryInitializer content provider that starts at app launch, with
    // an HTTP client under ai.onnxruntime.telemetry - a phone-home this app
    // must not carry. 1.22.0, 1.24.3, 1.26.0 and 1.28.0 have none of it
    // (checked 2026-09-23); 1.22.0 is also the smallest (6.5 MB arm64).
    // Its AAR ships no R8 rules; proguard-rules.pro keeps ai.onnxruntime.
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.22.0")

    testImplementation("junit:junit:4.13.2")

    // Deliberately just enough to launch the activity and read its lifecycle
    // state. No Compose test rule: the reactor runs an unbounded
    // withFrameNanos loop, and Compose's test clock treats a running animation
    // as "not idle", so a ComposeTestRule would sit waiting for a face that is
    // never going to stop. ActivityScenario has no such coupling.
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:core-ktx:1.6.1")
    androidTestImplementation("androidx.test:runner:1.6.2")

    // A server that answers, for the contract tests. Pinned to the same 4.12.0
    // as OkHttp itself: MockWebServer 5.x replaced MockResponse's setters with
    // a builder, so the version is load-bearing, not incidental.
    //
    // androidTest rather than a JVM unit test, deliberately. TokenStore needs
    // the real Keystore and JarvisApi takes it as a constructor argument, so a
    // JVM test could only reach this code by making the token store injectable
    // - a production change to suit a test. On the emulator the whole stack is
    // real, including the network security config, which already permits
    // cleartext to 127.0.0.1.
    androidTestImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
