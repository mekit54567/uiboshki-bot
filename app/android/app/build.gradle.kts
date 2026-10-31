import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Пуши приложения (push/, docs/app-push.md). FCM — только со своим
// google-services.json (Firebase): нет файла — сборка та же, пуши через Google
// выключены. RuStore Push — только с RUSTORE_PROJECT_ID (переменная окружения
// или -PrustoreProjectId=…): их SDK — из репозитория RuStore, который виден
// не отовсюду, поэтому по умолчанию — заглушка (src/norustore).
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}
val rustoreProjectId = (findProperty("rustoreProjectId") ?: System.getenv("RUSTORE_PROJECT_ID") ?: "").toString().trim()
val rustore = rustoreProjectId.isNotEmpty()
if (rustore) {
    repositories {
        // старый artifactory-external.vkpartner.ru пакеты пушей больше не отдаёт (404, 31.10)
        maven { url = uri("https://nexus-external.rustore.ru/repository/maven-rustore-exposed/") }
    }
}

// Ключ подписи выпуска: android/key.properties (CI пишет его из секретов
// ANDROID_KEYSTORE…). Нет файла — подпись отладочным ключом, как раньше.
val keyProps = Properties().apply {
    val f = rootProject.file("key.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "ru.uiboshki.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "ru.uiboshki.app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["rustoreProjectId"] = rustoreProjectId
        manifestPlaceholders["rustoreEnabled"] = rustore.toString()
    }

    sourceSets {
        getByName("main").java.srcDir(if (rustore) "src/rustore/kotlin" else "src/norustore/kotlin")
    }

    signingConfigs {
        if (!keyProps.isEmpty) {
            create("release") {
                storeFile = file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName(if (keyProps.isEmpty) "debug" else "release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging")
    if (rustore) {
        implementation("ru.rustore.sdk:pushclient:7.2.0")
    }
    testImplementation("junit:junit:4.13.2")
}
