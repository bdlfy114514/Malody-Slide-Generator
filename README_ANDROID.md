# Slide 生成器 —— Android 版（APK）

本目录下的 `slide_generator_v1.1.py`（Malody Slide 曲线插值工具）已被移植为可安装在安卓手机上的 App。

## 📦 产物

| 文件 | 说明 |
|---|---|
| `SlideGenerator_v1.2.apk` | **正式安装包（推荐）**。可直接传到手机点击安装。 |
| `SlideGenerator_v1.2_debug.apk` | 调试版，行为相同，仅多带调试标记，体积略大。 |

安装要求：**Android 7.0 (API 24) 及以上**，CPU 为 64 位 ARM（`arm64-v8a`，即 2015 年后的绝大多数手机）。

安装时如提示“未知来源应用”，需在系统设置里允许该来源安装。

## ✨ 相对桌面版的改动

1. **文件选择改为可视化**：原来的“谱面文件路径”文本框已删除，改为 **[📁 选择谱面文件]** 按钮，点击后直接调起手机系统的文件管理器（Android Storage Access Framework），可视化地选择 `.mc` 谱面文件。
2. **写回原目录**：生成后的谱面**直接写回你选择的那个文件本身**（即原目录、原文件），无需另存。写入前会在**同目录**自动生成 `原文件名.bak` 备份，绝不覆盖或损坏原文件内容。
3. 其余参数、算法、界面布局、预览画布与桌面版完全一致。

## 🆕 版本 1.2 新增

1. **节点上限由 5 提升到 15**：节点列表改为可动态增删的编辑器，默认 2 个，点「＋ 添加节点」最多到 15 个；每个节点带序号与「删除」按钮。
2. **锯齿改为「分段」可选**：不再是"整条 Slide 全局加锯齿"，而是**每一段（两个相邻节点之间）单独开关**。每段除了原来的形状（直线 / 先快后慢 / 先慢后快 / S 形）之外，多了一个「锯齿」勾选框；锯齿幅度仍为所有锯齿段共用。
3. **界面优化**：节点以卡片形式呈现，形状改用下拉选择（显示中文名，不再需要背 `s/si/so/b`），锯齿用勾选框；底部新增固定操作栏（显示节点计数 + 生成按钮），长列表也随手可点。
4. **预览反映锯齿**：预览画布现在会画出锯齿折线，能直接看到分段效果。
5. 生成按钮由原来的「常规 / 锯齿」两个合并为**一个「生成 Slide」**（是否锯齿由各段勾选决定）。

## 🧩 技术实现

- **算法零改动**：核心的 `timetrans / transtime_rev / drawslide` 与桌面版逐行一致，只是外层包了一个 JSON 桥接函数 `generate()`。
- **Python 运行在手机上**：使用 [Chaquopy](https://chaquo.com/chaquopy/) 将 CPython 3.12 打包进 App，因此无需手机预装 Python。
- **界面**：使用 WebView 承载 HTML/CSS/JS 界面（含 Canvas 预览，坐标变换与桌面版 Tkinter 画布一致），通过 `@JavascriptInterface` 与原生代码通信。
- **文件读写**：由原生 Kotlin 代码通过 SAF 完成（选择、读取、写回、生成备份），Python 只负责纯计算。

## 📁 工程结构

```
android/
├─ settings.gradle                  # 仓库与插件管理
├─ build.gradle                     # AGP / Kotlin / Chaquopy 插件版本
├─ gradle.properties.example        # JDK 路径、AndroidX 开关（模板，复制为 gradle.properties 使用）
├─ local.properties.example         # Android SDK 路径模板（含各人绝对路径，不入库）
├─ gradlew / gradlew.bat            # Gradle wrapper
└─ app/
   ├─ build.gradle                  # 应用模块配置（ABI、Python 版本、Python 源码目录）
   └─ src/main/
      ├─ AndroidManifest.xml
      ├─ java/com/slidegen/app/MainActivity.kt   # SAF 文件选择 + 读写 + Python 桥接
      ├─ assets/index.html                       # 手机端界面与预览
      └─ res/                                    # 图标、主题、字符串

../src/main/python/slide_core.py    # ★ 算法核心（PC 版与安卓版共用同一份）
```

> **算法核心不在 `android/` 里**，而是放在仓库根目录的 `src/main/python/`，
> 这样 PC 版和安卓版共用同一份源码、不会分叉。
> `android/app/build.gradle` 里通过
> `sourceSets { main { python.srcDirs += "${rootProject.projectDir}/../src/main/python" } }`
> 把它加进 Chaquopy 的源码目录。

## 🔧 如何重新编译

首次编译需要先按模板生成本机配置（`gradle.properties` 与 `local.properties`
含各人电脑的绝对路径，已在 `.gitignore` 中排除）：

```bat
cd android
copy gradle.properties.example gradle.properties
copy local.properties.example local.properties
:: 然后编辑 local.properties，把 sdk.dir 改成你电脑上的 Android SDK 路径
```

之后即可编译：

```bat
cd android
set "JAVA_HOME=D:\slide_generator\.toolchain\jdk17\jdk-17.0.20.1+1"
set "PATH=%JAVA_HOME%\bin;%PATH%"
gradlew.bat assembleRelease        :: 或 assembleDebug
```

产物输出在 `android/app/build/outputs/apk/`。

若换电脑编译，需要：
- JDK 17（若它不是系统默认 java，就在 `gradle.properties` 里填 `org.gradle.java.home`）
- Android SDK（在 `local.properties` 里填 `sdk.dir`），并安装 `platforms;android-34`、`build-tools;34.0.0`
- Gradle 8.7（可用自带 wrapper 自动下载）

版本矩阵：Android Gradle Plugin 8.5.2 · Gradle 8.7 · Kotlin 1.9.24 · Chaquopy 17.0.0 · Python 3.12 · compileSdk/targetSdk 34 · minSdk 24。

## ⚠️ 说明

- 为了让 APK 体积可控，仅打包了 64 位运行时（`arm64-v8a` + `x86_64`）。Chaquopy 的 Python 3.12 **不提供** 32 位 ARM（`armeabi-v7a`）运行时，因此极老的 32 位手机无法安装。
- **备份（.bak）的存放位置**：写入前会先生成 `原文件名.bak`。
  - 若谱面位于普通目录（如 `/sdcard/Malody/...`），`.bak` 直接生成在**同目录**下。
  - 受安卓系统限制，「下载」目录等由系统文档提供者托管的目录不允许应用在其中新建文件，此时会自动把 `.bak` 存入系统**「下载」目录**，并在界面提示。无论何种情况，**都会先完成备份再改写原文件**，不会损坏原谱面。
