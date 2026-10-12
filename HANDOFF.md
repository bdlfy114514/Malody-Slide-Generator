# 交接文档 · Malody Slide 生成器（桌面版 + 安卓版）

> 给下一个接手 agent 的上手说明。当前版本 **1.2**（桌面版与安卓版均已同步），
> 功能完整、已构建、已在模拟器验证通过；桌面版有 41 项自动化测试全绿。

---

## 0. 一句话背景

用户原本有一个桌面 Python 脚本 `slide_generator_v1.1.py`（tkinter GUI，为音游 Malody 生成 Slide 曲线谱面）。后来我们把它**移植成了安卓 App**，并迭代到 1.2：

- 1.0 / 1.1 = 移植 + 原生文件选择（SAF）+ 写回原文件 + `.bak` 备份
- **1.2 = 节点上限 5→15、锯齿改为"按段可选"、UI 重做**

做法是 **Chaquopy**（把 CPython 打包进 APK），算法保持纯 Python 原样，UI 用 WebView 承载 HTML。

**随后桌面版也同步到了 1.2**（见 §10）：新增 `slide_generator_v1_2.py`，
它**不复制算法**，而是直接导入安卓工程里的 `slide_core.py`，两端共用同一份算法源码。

---

## 1. 目录总览（工作目录 `D:\slide_generator`）

```
D:\slide_generator\
├─ SlideGenerator_v1.2.apk          ← 正式安装包（交付物，debug 密钥签名）
├─ SlideGenerator_v1.2_debug.apk    ← 调试版（唯一能开 WebView 远程调试的版本）
├─ slide_generator_v1_2.py          ← 桌面版 1.2 入口（★ 当前桌面版就用这个）
├─ slide_generator_v1.1.py          ← 旧桌面脚本（仅存档，算法已分叉）
├─ desktop_v1_2_preview.png         ← 桌面版界面截图（README 引用）
├─ README.md                        ← 开源就绪的总文档（PC 版 + 安卓版）
├─ README_ANDROID.md                ← 面向开发/构建的说明（含 1.2 变更清单）
├─ 使用说明.md / .html / .pdf       ← 面向普通用户（安卓版）的说明
├─ src\main\python\slide_core.py    ← ★ 桌面版与安卓版共用的算法核心（唯一一份）
├─ android\                         ← Gradle 工程（安卓版真正的源码在这里）
└─ .toolchain\                      ← 本机自建工具链 + 辅助脚本（见 §3）
```

**改安卓版界面只碰 `android\` 下；改算法只碰 `src\main\python\slide_core.py`
（一处生效，两端同步）。** 根目录的 APK / PDF 都是产物。

> ⚠️ 算法核心已从 `android\app\src\main\python\` **移到仓库根目录 `src\main\python\`**，
> 目的是让 PC 版压缩包解压后能直接运行（两个 py 放一起即可）。
> `android\app\build.gradle` 里用
> `sourceSets { main { python.srcDirs += "${rootProject.projectDir}/../src/main/python" } }`
> 把这个目录加进了 Chaquopy 的源码路径（已实测：改动 `slide_core.py` 会真的进 APK）。

---

## 2. 关键文件与职责

| 文件 | 作用 |
|---|---|
| `src\main\python\slide_core.py` | **算法核心（两端共用，只此一份）**。`timetrans/transtime_rev/_shape_x/drawslide` + 给 Android 用的桥接函数 `generate(params_json)`。纯标准库，可在电脑上直接跑。 |
| `slide_generator_v1_2.py` | **桌面版 1.2 入口**。tkinter GUI + 原生文件对话框 + 写回 + `.bak` 备份。启动时从上面的 `slide_core.py` 导入算法（见 §10）。 |
| `.toolchain\test_desktop_v1_2.py` | 桌面版 41 项自动化冒烟测试，**含桌面/安卓算法逐字节对拍**。 |
| `.toolchain\test_desktop_e2e.py` | 桌面版 11 项端到端测试：模拟用户点按钮的完整路径（拦截 messagebox，不弹窗）。 |
| `.toolchain\snapshot_desktop_v1_2.py` | 填样例数据启动界面并截图，用于目视检查布局。 |
| `android\app\src\main\assets\index.html` | **安卓版界面**（HTML/CSS/JS 一体）。节点增删、每段形状/锯齿、预览 Canvas、与 Kotlin 的桥接调用都在这里。 |
| `android\app\src\main\java\com\slidegen\app\MainActivity.kt` | WebView 宿主 + SAF 文件选择/读/写 + `.bak` 备份 + 调用 Python。 |
| `android\app\build.gradle` | 版本号、ABI、Chaquopy 配置。 |
| `android\settings.gradle` / `build.gradle` | 插件版本（AGP 8.5.2 / Kotlin 1.9.24 / Chaquopy 17.0.0）。 |
| `android\gradle.properties` | **写死了 JDK 路径** `org.gradle.java.home`。**已加入 .gitignore 不入库**，仓库里放的是 `gradle.properties.example` 模板。 |
| `android\local.properties` | **写死了 SDK 路径** `sdk.dir`。同样不入库（模板待补）。 |
| `android\app\build.gradle` | 另外还负责把 `src/main/python` 加进 Chaquopy 的源码目录（见 §1 的提示）。 |

### 数据流（重要）

```
桌面版： slide_generator_v1_2.py --import--> slide_core.py
安卓版： WebView(index.html) --JS--> Kotlin(MainActivity) --Chaquopy--> slide_core.py
                                            （文件读写全在 Kotlin 侧）
```

- JS 通过 `Android.xxx()` 调 Kotlin，Kotlin 通过 `Python.getInstance().getModule("slide_core")` 调 Python。
- **传给 Python 的参数**（JSON 字符串）：
  ```json
  {"w":256,"density":8,
   "nodes":[{"t":[4,1,4],"x":0},{"t":[8,0,1],"x":128}, ...],   // t = [拍,线,细分]
   "segs":[{"shape":"s","serrated":false}, ...],               // 每段一个，长度 = 节点数-1
   "amplitude":"6"}
  ```
- **返回**：`{"ok":true,"slide":"{...}","points":[[x,t],...]}` 或 `{"ok":false,"error":"中文提示"}`。
- Python 只做计算；**文件读写全部在 Kotlin 侧**（SAF 的 `content://` URI）。

### Kotlin ↔ JS 的接口（`@JavascriptInterface`，名字是 `Android`）

`pickFile()` · `hasFile()` · `fileName()` · `readFile()` · `writeBack(slideText)` · `generate(paramsJson)`
（回调：Kotlin 会调 JS 的 `window.onFilePicked(name,uri)` / `window.onPickCancelled()`）

---

## 3. 工具链（本机已装好，**不要重装**）

全部在 `D:\slide_generator\.toolchain\`：

| 组件 | 路径 / 说明 |
|---|---|
| JDK 17 | `.toolchain\jdk17\jdk-17.0.20.1+1` |
| Gradle 8.7 | `.toolchain\gradle\gradle-8.7`（工程内也有 wrapper `gradlew.bat`） |
| Android SDK | `.toolchain\android-sdk`（含 cmdline-tools / platform-tools / build-tools;34.0.0 / platforms;android-34 / emulator / system-images;android-34;google_apis;x86_64） |
| 模拟器 AVD | 名为 `slide_test`（位于 `%USERPROFILE%\.android\avd`） |
| 辅助脚本 | `.toolchain\cdp_eval.py`（在设备 WebView 里执行一段 JS）、`.toolchain\html2pdf_cdp.py`（HTML→PDF） |

> 系统里**没有** Node / Playwright，**只有** JDK 8（太老，不能用）。构建务必用上面这个 JDK 17。

---

## 4. 常用命令（Windows cmd，直接抄）

### 构建 APK
```bat
cd /d D:\slide_generator\android
set "JAVA_HOME=D:\slide_generator\.toolchain\jdk17\jdk-17.0.20.1+1"
set "PATH=%JAVA_HOME%\bin;%PATH%"
gradlew.bat assembleDebug      :: 或 assembleRelease
```
- 产物：`android\app\build\outputs\apk\{debug,release}\app-*.apk`
- 增量构建实测：**改 html ≈11s，改 Kotlin ≈29s，release ≈38s**；全新 ≈6min。
- 之后把产物拷到根目录并改成 `SlideGenerator_v1.2*.apk`。

### 版本号
改 `android\app\build.gradle` 里的 `versionCode` / `versionName`（当前 3 / "1.2"）。

### 只测算法（最快，不用构建）
```bat
cd /d D:\slide_generator
python -c "import sys,json; sys.path.insert(0,'src/main/python'); import slide_core as s; print(s.generate(json.dumps({'w':256,'density':8,'nodes':[{'t':[0,0,1],'x':0},{'t':[2,0,1],'x':256}],'segs':[{'shape':'s','serrated':True}],'amplitude':'10'})))"
```
纯 Python，秒出结果，适合验证算法改动。

### 模拟器 + 设备上验证
```bat
:: 1) 启动模拟器（无头）
set "ANDROID_SDK_ROOT=D:\slide_generator\.toolchain\android-sdk"
"%ANDROID_SDK_ROOT%\emulator\emulator.exe" -avd slide_test -no-window -no-audio -no-boot-anim -no-snapshot -gpu swiftshader_indirect
:: 等 sys.boot_completed=1

:: 2) 装 + 起（装机必须用 debug 包，否则没有远程调试）
set "PATH=%ANDROID_SDK_ROOT%\platform-tools;%PATH%"
adb install -r D:\slide_generator\SlideGenerator_v1.2_debug.apk
adb shell am force-stop com.slidegen.app
adb shell am start -n com.slidegen.app/.MainActivity

:: 3) 开远程调试端口（pid 用 adb shell pidof com.slidegen.app 拿）
adb forward tcp:9222 localabstract:webview_devtools_remote_<PID>

:: 4) 在页面里执行 JS（第二个参数是要执行的表达式）
cd /d D:\slide_generator\.toolchain && python cdp_eval.py "state.nodes.length"
```
设备上验证时，可以直接操作页面里的全局变量：`state`（`{nodes:[{t,x}], segs:[{shape,serrated}]}`）、函数 `render()` / `doGenerate()` / `addNode()` / `removeNode(i)` / `setAllSerrated(v)`。

---

## 5. 已实现的行为（改代码前务必知道）

### 算法（`slide_core.drawslide`）
- **每段锯齿**：`serrated` 是与段数等长的布尔列表。**只有标记为锯齿的段**，其"段内偶数序号"的 seg 会被 `+amplitude`；**每段从 0 重新计数**（所以每段锯齿都从自己的起点起算，互不影响）。
- 兼容性：**单段 + 锯齿** 的结果与 1.1 的全局锯齿**完全一致**（已验证）。多段时才有差别——这正是新功能。
- 预览点 `plot_points` 是**从最终 seg 反推**出来的，所以**预览也会画出锯齿**（1.1 的预览只有平滑曲线）。
- `generate()` 会校验：节点数 2–15、段数 = 节点数-1、形状 ∈ {s,si,so,b}、有锯齿时必须给幅度。

### 文件写入（`MainActivity.writeBack`）
- 写回**同一个 URI**（即原目录原文件），写入前先做备份。
- 备份 `.bak` 策略：① 优先用 `DocumentsContract.createDocument` 在原目录建同级文件；② 失败（如「下载」目录由 `DownloadStorageProvider` 托管，普通应用无 `MANAGE_DOCUMENTS`）则退回 **MediaStore 写入系统「下载」目录**，并在界面提示；③ 再失败则只提示、但仍已写回。
- 写入是**插入式**：只在首处 `"note":[` 之后插入，不会覆盖其它内容。

### 界面（`index.html`）
- 节点动态增删（2–15），每段有"形状下拉 + 锯齿勾选框"；顶部固定操作栏显示 `节点 N / 15` + 生成按钮。
- 只有一个"生成 Slide"按钮（1.1 的"常规/锯齿"两个按钮已合并）。

---

## 6. 文档生成流水线（用户很在意文档）

用户说明是 `使用说明.md`（内容源）→ `使用说明.html`（排版，A4）→ `使用说明.pdf`（成品）：

```bat
cd /d D:\slide_generator
python .toolchain\html2pdf_cdp.py     :: 读 使用说明.html → 写 使用说明.pdf
```
- **必须用这个脚本**，不要用 `msedge --print-to-pdf`（本机 Edge 版本无法去掉页眉页脚，会出现丑陋的 `file://` 页脚）。脚本用 DevTools 协议的 `displayHeaderFooter:false` 拿干净的矢量 PDF。
- 校验：`python -c "import pymupdf; d=pymupdf.open('使用说明.pdf'); print(d.page_count, sum(len(p.get_images()) for p in d))"` —— **图片数必须是 0**（矢量），页数尽量 3 页、末页别只剩一行（避免"孤儿页"，必要时删掉末尾的分隔线）。
- 改了 md 记得**三份都同步**（md / html / pdf）。

---

## 7. 已知坑（踩过的，别再踩）

1. **Windows cmd 的变量展开**：`set "X=.." & "%X%"` 在同一行里 `%X%` 展开为空 → 变量和用它的命令要**分行**，或直接用字面路径。
2. **`rem` 注释**会吞掉同一行 `&` 之后的命令，不要在链式命令里用 `rem`。
3. **`timeout /t` 在重定向 stdin 时会报错** → 用 `ping -n N 127.0.0.1 >nul` 代替等待。
4. **Gradle 按内容哈希判断**：`touch` 文件不会触发重编译，必须真改内容。
5. **WebView 远程调试只对 debug 包开放**（代码里 `if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)`）。
6. **DevTools 会拒绝带 Origin 头的 WS 连接** → `websocket-client` 要加 `suppress_origin=True`。
7. **Chaquopy 只提供 64 位运行时**（Python 3.12 没有 `armeabi-v7a`）→ ABI 固定 `arm64-v8a` + `x86_64`。
8. 构建时若出现 `Couldn't find Python 3.12 ... .pyc` 的 Warning，**无害**：Chaquopy 会直接打包 .py 源码，运行时编译（已验证可用）。
9. 中文文件名在某些命令输出里会显示成乱码（编码问题），但文件本身正常。
10. **release 包用的是 debug 密钥签名**（`signingConfigs.debug`），可侧载安装，**不能上架应用商店**。若要上架需另配正式签名。

---

## 8. 遗留 / 可选后续

- ~~**桌面脚本未同步**~~ **已完成**（见 §10）：新增 `slide_generator_v1_2.py`，与 App **共用同一份算法源码** `src\main\python\slide_core.py`，因此不会再分叉。旧的 `slide_generator_v1.1.py` 仅作历史存档保留（未删除）。
- `.toolchain\stale_v1.1_guide.pdf` 是我早期 PDF 流程产生的**旧版说明副本**（1.1 内容），已从交付目录移出，**没有删**。确认无用后可清理。
- 若用户要上架商店，需补正式签名配置。
- 可考虑但未做：是否给锯齿段单独设幅度；撤销/重做。
- ~~预览标注节点序号~~ **已完成**（桌面版 1.2 已标注节点序号）。

---

## 9. 交接检查清单

- [x] `android\` 工程可独立构建（`gradlew.bat assembleDebug`）
- [x] 算法有本机 Python 快速验证路径
- [x] 模拟器 + DevTools 自动化验证路径可用
- [x] 根目录交付物：`SlideGenerator_v1.2.apk`、`使用说明.pdf`
- [x] 用户文档三份同步（md/html/pdf）
- [x] 桌面脚本同步到 1.2（**已完成**，见 §10）

---

## 10. 桌面版 1.2 同步（本次新增的工作）

### 新增文件

| 文件 | 作用 |
|---|---|
| `slide_generator_v1_2.py` | **桌面版 1.2 入口**。GUI + 原生文件选择（`tkinter.filedialog`）+ 写回 + `.bak` 备份 |
| `.toolchain\test_desktop_v1_2.py` | 桌面版自动化冒烟测试（41 项断言，含与安卓端算法对拍） |
| `.toolchain\snapshot_desktop_v1_2.py` | 启动界面填样例数据并截图，用于目视检查布局 |
| `desktop_v1_2_preview.png` | 界面截图，README 里引用它 |

### 关键设计：算法只有一份

`slide_generator_v1_2.py` **不包含算法**。启动时按顺序查找并 `import`：

1. `<脚本目录>\slide_core.py`（PC 版压缩包解压后 / 仓库根目录旁的样子）
2. `<脚本目录>\src\main\python\slide_core.py`（仓库内正常情况）
3. `<脚本目录>\android\app\src\main\python\slide_core.py`（兼容旧检出）

找不到就打印清晰指引并退出。**桌面版与安卓版因此永远算出相同结果**，不存在分叉。

### 与 1.1 的差异

- 节点上限 5 → **15**，节点可动态增删（卡片式列表，可滚动）
- 锯齿 **全局 → 按段独立**（每段一个下拉形状 + 一个锯齿勾选框），幅度仍各段共用
- "常规/锯齿"两个按钮 → **一个「生成 Slide 并写入谱面」**，另有「仅预览」
- 文件路径：**复制粘贴文本框 → 原生文件对话框**（`Ctrl+O`）
- 预览：**会画出锯齿**，并标注节点序号；窗口可缩放自适应
- 备份更安全：`.bak` 已存在时顺延为 `.bak.1`、`.bak.2`…（1.1 会覆盖旧备份）
- 校验更严：复用手机端的报错文案（缺时间/缺位置/非整数/幅度为空…）

### 验证方式（已验证 41 + 11 项全绿）

```bat
cd /d D:\slide_generator
set PYTHONUTF8=1
python .toolchain\test_desktop_v1_2.py     :: 41 项：界面/校验/对拍/锯齿语义/写回备份
python .toolchain\test_desktop_e2e.py      :: 11 项：模拟点按钮的完整端到端流程
python .toolchain\snapshot_desktop_v1_2.py :: 截图，目视检查布局
```

冒烟测试覆盖：界面构建、节点增删与 15 上限、参数校验报错、**两端算法逐字节对拍**、
分段锯齿语义（段内偶数序号 + 每段独立计数 + 不被相邻段影响）、预览锯齿、
写回 `.mc` 与 `.bak` 顺延、无 `"note":[` 标记时中止且不改文件。

端到端测试覆盖：未选文件时只提示不写入、选中文件后写入成功并弹窗、状态栏配色、
写进文件的 Slide 与**安卓端 `generate()`** 输出一致、参数有误时报错且状态栏变红。

> 若改了 `slide_core.py`，**务必重跑这两个测试**，它们是对拍保证。

### 文档同步

`README.md` 已**重写**为开源就绪版本：同时覆盖桌面版与安卓版、含界面截图、
参数填写指南、算法说明、构建与测试方法、FAQ。**尚未添加 `LICENSE` 文件**
（README 末尾已标注该待办）。

