# 宿舍管理系统 - Android 客户端

## 概述

这是宿舍管理系统的 Android 客户端，基于 Capacitor 框架构建。
该客户端作为移动端 WebView 包装器，连接到运行中的宿舍管理系统服务器。

## 工作原理

1. Android 应用启动后显示服务器配置页面
2. 用户输入服务器地址（如 `http://192.168.1.100:35168`）
3. 应用通过 WebView 加载服务器页面
4. 服务器地址会被保存，下次启动自动加载

## 前置条件

- 服务器端（Windows 版或 Docker 版）需要在局域网内运行
- 服务器默认端口：35168
- 手机和服务器需要在同一网络内

## 本地开发

### 环境要求

- Node.js 18+
- JDK 17
- Android Studio (包含 Android SDK)

### 构建步骤

```bash
# 1. 安装依赖
cd android
npm install

# 2. 同步 Web 资源
npx cap sync

# 3. 添加 Android 平台（首次）
npx cap add android

# 4. 打开 Android Studio 构建
npx cap open android

# 或使用命令行构建
cd android
./gradlew assembleDebug
```

### 自定义服务器地址

在 `web-src/index.html` 中修改默认服务器地址配置。

## GitHub Actions 自动构建

Android APK 会通过 GitHub Actions 自动构建，无需本地配置。
详见 `.github/workflows/build.yml` 中的 `build-android` 任务。

## 生成签名 APK

### 创建发布密钥

```bash
keytool -genkey -v -keystore release.keystore -alias release \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass YOUR_PASSWORD -keypass YOUR_PASSWORD
```

### 配置签名信息

在 `android/app/build.gradle` 中添加签名配置：

```gradle
android {
    signingConfigs {
        release {
            storeFile file('../../release.keystore')
            storePassword 'YOUR_PASSWORD'
            keyAlias 'release'
            keyPassword 'YOUR_PASSWORD'
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android.txt'), 'proguard-rules.pro'
        }
    }
}
```

### 构建发布版

```bash
cd android
./gradlew assembleRelease