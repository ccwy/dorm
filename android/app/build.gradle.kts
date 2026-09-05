plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python") version "15.0.1"
}

android {
    namespace = "com.dorm.management"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.dorm.management"
        minSdk = 26          // Android 8 (API 26)
        targetSdk = 34
        versionCode = (project.findProperty("versionCode") as? String)?.toIntOrNull() ?: 1
        versionName = (project.findProperty("versionName") as? String) ?: "1.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // 签名配置 - 从环境变量读取
            signingConfig = signingConfigs.findByName("release")
        }
        debug {
            isMinifyEnabled = false
        }
    }

    signingConfigs {
        create("release") {
            val keystoreFile = file("release.keystore")
            if (keystoreFile.exists()) {
                storeFile = keystoreFile
                storePassword = System.getenv("KEYSTORE_PASSWORD") ?: ""
                keyAlias = System.getenv("KEY_ALIAS") ?: "dorm"
                keyPassword = System.getenv("KEY_PASSWORD") ?: ""
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }
}

chaquopy {
    python {
        version = "3.8"

        pip {
            // Flask 全家桶
            install("Flask==2.3.3")
            install("Flask-SQLAlchemy==3.1.1")
            install("Flask-WTF==1.2.1")
            install("Flask-Login==0.6.3")
            install("Flask-Migrate==4.0.5")

            // 数据处理
            install("openpyxl==3.1.2")
            install("pandas==2.0.3")
            install("numpy==1.24.4")
            install("xlsxwriter==3.2.5")

            // 工具库
            install("python-dotenv==1.0.0")
            install("PyMySQL==1.1.0")
            install("cryptography==41.0.7")
            install("schedule==1.2.0")
            install("waitress==2.1.2")
            install("requests==2.31.0")
            install("Pillow==10.4.0")
            install("SQLAlchemy==2.0.23")
            install("Alembic==1.13.1")
            install("MarkupSafe==2.1.3")
            install("itsdangerous==2.1.2")
            install("click==8.1.7")
            install("blinker==1.7.0")
            install("Werkzeug==2.3.7")
            install("Jinja2==3.1.2")

            // 桌面端专用包：不在 Android 上安装
            // pywebview、pystray、psutil — 通过 stub 替换
        }

        sourceSets {
            getByName("main") {
                srcDir("../")
                // 排除不需要的文件
                exclude("Auto_Setup/**")
                exclude(".github/**")
                exclude(".joycode/**")
                exclude("android/**")
                exclude("*.bat")
                exclude("*.spec")
                exclude("dockerfile")
                exclude(".dockerignore")
                exclude("requirements.txt")
                exclude("android-requirements.txt")
                exclude("LICENSE")
                exclude("README.md")
                exclude("Android_Build_Plan.md")
            }
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.webkit:webkit:1.9.0")
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("com.airbnb.android:lottie:6.1.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
}