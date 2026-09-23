plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.jarvis.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.jarvis.client"
        // 33, not 30: RuntimeShader/AGSL for the Nucleus face needs 33, and
        // taking 30 would mean a GLES fallback branch carried forever.
        minSdk = 33
        targetSdk = 36
        versionCode = 1
        // Not "step0" any more. The number is cosmetic — versionCode is
        // pinned at 1 so any build installs over any other — but a version
        // string naming a step this app passed long ago is one more thing
        // quietly asserting something untrue.
        versionName = "0.1"

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
    }

    // The shared debug key, committed at the repository root. Without it AGP mints
    // ~/.android/debug.keystore per machine, and a CI runner is a fresh machine
    // every run - so each build was signed with a different certificate and
    // `adb install -r` over the previous one failed with
    // INSTALL_FAILED_UPDATE_INCOMPATIBLE. The only way through was `adb uninstall`,
    // which wipes the pairing secret, the auth token, the device id and anything
    // still queued offline.
    //
    // Guarded on existence rather than assumed: a checkout of this module alone,
    // without the repository around it, falls back to AGP's generated key and still
    // builds.
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
            // Signed with the same committed debug key, so `adb install -r`
            // over an existing install still works: the certificate is what
            // has to match, not the build type.
            //
            // THE TRIPWIRE ON THAT KEY, recorded here because this is where
            // someone will be standing when it matters: `keystore/debug.keystore`
            // is committed to this repository. Android decides whether an APK
            // may replace an installed app by CERTIFICATE, and a same-signature
            // update inherits the existing data directory and the Keystore
            // alias — so anyone holding this key can build an app the phone
            // accepts as an update to this one and simply ask the Keystore to
            // decrypt the pairing token. No root, no `run-as`.
            //
            // That is survivable today only because the repository is PRIVATE.
            // It is a one-way door: making the repo public exposes the key
            // retroactively and for every commit in history, and no later
            // rotation can un-publish it. So — rotate this key BEFORE the repo
            // is ever made public or shared, never after. Rotating costs one
            // uninstall/reinstall on the phone and re-pairing, because the new
            // certificate will not match the installed one.
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
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
        // Compressed in the APK and unpacked at install, rather than stored
        // uncompressed: ONNX Runtime's library is ~15 MB per ABI raw and
        // ~7 MB compressed, and a sideloaded APK's download size is the one
        // the owner waits for. Its .so files are 16 KB page-aligned
        // (checked), so either way loads on Android 15's 16 KB devices.
        jniLibs { useLegacyPackaging = true }
    }
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
