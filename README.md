# MDL3 for HELLDIVERS 2

**English** · [中文](#中文)

MDL3 is a mod loader and settings menu for HELLDIVERS 2. It runs mods, keeps their settings, and gives mod authors a safe set of tools (drawing, audio, files, game data). The release package also contains **HD2 Data Hub**, which provides game data to other mods.

> This is a **preview** build. Back up anything you care about, and report problems with the diagnostic report (see below).

## What's in the package

| File / folder | What it is |
|---|---|
| `MDL3/` | The MDL3 mod (deployed by Arsenal) |
| `Addon/` | HD2 Data Hub (deployed by Arsenal, can be turned on and off separately) |
| `MDL3Setup.exe` | Setup and repair tool: install / update, fix the EAC certificate, repair the EAC service, write a report, remove everything |
| `Native/`, `BUILD.json` | The signed native component and its build record (MDL3Setup.exe already carries them) |
| `For Modder/` | API documents and asset tools for mod authors |
| `README_zh.md` | The full player guide (Chinese) |

## Install or update

1. Import the ZIP in **Arsenal** (replace the old MDL3 package), tick **MDL3** and **HD2 Data Hub**, and click **Deploy**.
2. **Give MDL3 the highest priority in Arsenal (deployed last).** The game runs only the highest-priority boot script; a mod with its own boot script placed after MDL3 stops MDL3 from starting.
3. Do not also enable a separately installed HD2 Data Hub.
4. Start the game from Steam and press **ESC**:
   - an **MDL3** settings page is there: done;
   - an **MDL3 diagnostic mode** window appears: on first use or after an update MDL3 installs its own component automatically. Quit the game completely and start it again.

Or, with the game closed, extract the ZIP and **double-click `MDL3Setup.exe`** (do not use "Run as administrator"), then click **Install / Update**. It finds the game by itself; if it cannot, click **Browse…** and pick the game folder (the one with `bin` and `data`).

### Where the files go

From 3.0.0-dev.47 on, everything lives in `C:\ProgramData`, whatever your Windows user name is:

| Path | Contents |
|---|---|
| `C:\ProgramData\MDL3` | native component, `config.json`, `Logs\` |
| `C:\ProgramData\MDL\Helldivers2` | MDL mod settings (`MDL.cfg`), loose mods (`Mods\`), logs |
| `%LOCALAPPDATA%\MDL3\sys-paths.txt` | tells the native component which folders it may use |

Older installs in `%LOCALAPPDATA%\MDL3` keep working; running MDL3Setup.exe once moves their settings and loose mods over.

## No MDL3 page in the game (EAC "untrusted")

If the diagnostic window says the component is installed but blocked by Easy Anti-Cheat (often error 193), the PC is usually missing the intermediate certificate **Certum Code Signing 2021 CA** that MDL3 is signed with. It is a regular certificate authority certificate; installing it does not turn off any security feature.

1. Quit the game, open `MDL3Setup.exe`, click **Fix EAC certificate** (confirm the Windows administrator prompt), then **restart the PC**.
2. Still blocked? Click **Repair EAC service**: in the Easy Anti-Cheat window pick HELLDIVERS 2 and click **Repair Service**.
3. Still blocked after both? Click **Write report** and send the `MDL3-report-….txt` from your Desktop.

Turning off the antivirus, whitelisting, moving folders or reinstalling MDL3 does not help with this problem.

If your antivirus flags `MDL3Setup.exe`: it is a Python program packed with PyInstaller, and such programs are sometimes flagged by mistake. You can skip it entirely and use the automatic in-game installation described above.

## Remove

Turn off or remove the package in Arsenal and Deploy. To delete MDL3's files, close the game, open `MDL3Setup.exe` and click **Remove everything…**:

- by default it deletes the component, settings and logs (`C:\ProgramData\MDL3` and the `MDL3` folder in your user folder);
- optionally also MDL mod settings, logs and loose mods (`MDL\Helldivers2`, `CowboyBingus\Helldivers2`, `HD2Runtime\mod_data`, in both places);
- optionally also the certificate added by **Fix EAC certificate** (administrator).

## For mod authors

See `For Modder/` in the package:

- `hd2data_field_reference_*.md`: every `HD2Data` function and field (HD2 Data Hub);
- `MDL3_GUI_API_zh.md`: `MDL3.gui`: rectangles, lines, circles, text and images; `gui_assets.py` converts PNG files;
- `MDL3_AUDIO_API_zh.md`: sound handles, 3D positioning and reverb; `audio_assets.py` (with `audio_adpcm.py`) converts audio. All mods together can use at most 3 different reverb settings at a time.

MDL3 checks every argument a mod passes, so a wrong call raises an error in that mod instead of crashing the game. Whatever a mod drew is cleared when it is turned off, and a mod that draws far too much is stopped.

## Credits

- Lua protection based on [Prometheus](https://github.com/prometheus-lua/Prometheus) by Elias Oelschner.
- Diagnostic window text rendered from Noto Sans CJK SC (SIL Open Font License 1.1).

---

# 中文

MDL3 是 HELLDIVERS 2 的模组加载器和设置菜单：运行模组、保存模组设置，并给模组作者提供安全的接口（绘图、音频、文件、游戏数据）。发布包里还附带 **HD2 Data Hub**，给其他模组提供游戏数据。

> 这是**预览版**。重要的东西请先备份；遇到问题请附上诊断报告（见下文）。

## 包里有什么

| 文件 / 文件夹 | 说明 |
|---|---|
| `MDL3/` | MDL3 模组（由 Arsenal 部署） |
| `Addon/` | HD2 Data Hub（由 Arsenal 部署，可以单独开关） |
| `MDL3Setup.exe` | 安装与修复工具：安装/更新、修复 EAC 证书、修复 EAC 服务、诊断报告、彻底清除 |
| `Native/`、`BUILD.json` | 已签名的本地组件和构建记录（MDL3Setup.exe 内已自带） |
| `For Modder/` | 给模组作者的接口文档和资源转换工具 |
| `README_zh.md` | 完整的玩家说明 |

## 安装或更新

1. 在 **Arsenal** 中导入本 ZIP（替换旧的 MDL3 包），勾选 **MDL3** 和 **HD2 Data Hub**，点 **Deploy**。
2. **把 MDL3 放在 Arsenal 的最高优先级（最后部署）。** 游戏只运行优先级最高的启动脚本，自带启动脚本的模组排在 MDL3 后面时，MDL3 不会启动。
3. 不要同时启用原先单独安装的 HD2 Data Hub。
4. 通过 Steam 启动游戏，按 **ESC**：
   - 出现“MDL3 设置”一页：安装完成；
   - 出现“MDL3 诊断模式”窗口：第一次使用或刚更新时，MDL3 会自动安装自己的组件。**完全退出游戏再启动一次**即可。

也可以先退出游戏，解压 ZIP，**直接双击 `MDL3Setup.exe`**（不要“以管理员身份运行”），点“安装 / 更新”。它会自动找到游戏；找不到时点“选择…”，指定包含 `bin` 和 `data` 的游戏目录。

### 文件位置

从 3.0.0-dev.47 起，所有文件都放在 `C:\ProgramData`，与 Windows 用户名无关：

| 路径 | 内容 |
|---|---|
| `C:\ProgramData\MDL3` | 本地组件、`config.json`、日志 `Logs\` |
| `C:\ProgramData\MDL\Helldivers2` | MDL 模组设置（`MDL.cfg`）、本地模组（`Mods\`）、日志 |
| `%LOCALAPPDATA%\MDL3\sys-paths.txt` | 告诉本地组件可以使用哪些文件夹 |

以前装在 `%LOCALAPPDATA%\MDL3` 的旧版本照常可用；运行一次 MDL3Setup.exe 会把原来的设置和本地模组迁移过来。

## 进游戏后没有“MDL3 设置”（EAC 提示不受信任）

诊断窗口提示“组件已安装，但被反作弊（EAC）拦截”（常见于错误 193）时，最常见的原因是电脑缺少 MDL3 签名所用的中间证书 **Certum Code Signing 2021 CA**。这是正规证书颁发机构的证书，安装它不会关闭任何安全功能。

1. 退出游戏，打开 `MDL3Setup.exe`，点“修复 EAC 证书”（Windows 弹出管理员确认时点“是”），然后**重启电脑**。
2. 仍被拦截：点“修复 EAC 服务”，在 Easy Anti-Cheat 窗口里选择 HELLDIVERS 2，点“修复服务”（Repair Service）。
3. 两步都做过仍不行：点“生成诊断报告”，把桌面上的 `MDL3-report-….txt` 发给作者。

关闭杀毒软件、添加白名单、换目录、重装 MDL3，对这个问题都没有用。

如果杀毒软件拦截了 `MDL3Setup.exe`：它是用 PyInstaller 打包的 Python 程序，这类程序偶尔会被误报。也可以完全不用它，按上面的方法在游戏里自动安装。

## 移除

先在 Arsenal 中关闭或移除本包并重新部署。要删除电脑上的 MDL3 文件，退出游戏后打开 `MDL3Setup.exe`，点“彻底清除…”：

- 默认删除组件、配置和日志（`C:\ProgramData\MDL3` 和用户目录下的 `MDL3` 文件夹）；
- 可选：同时删除 MDL 模组设置、日志和散装模组（`MDL\Helldivers2`、`CowboyBingus\Helldivers2`、`HD2Runtime\mod_data`，两个位置都删）；
- 可选：同时移除“修复 EAC 证书”装的证书（需要管理员权限）。

## 给模组作者

见包里的 `For Modder/`：

- `hd2data_field_reference_*.md`：`HD2Data` 的全部函数和字段（HD2 Data Hub）；
- `MDL3_GUI_API_zh.md`：`MDL3.gui` 绘图接口（矩形、线、圆、文字、图片），`gui_assets.py` 转换 PNG；
- `MDL3_AUDIO_API_zh.md`：音效句柄、3D 定位、混响，`audio_assets.py`（含 `audio_adpcm.py`）转换音频。所有模组合计同一时间最多 3 种不同的混响设置。

MDL3 会检查模组传入的每个参数，调用出错只会让那个模组报错，不会让游戏崩溃；模组关闭时它画的东西会自动清除，绘制量过大的模组会被停用。

## 致谢

- Lua 保护基于 Elias Oelschner 的 [Prometheus](https://github.com/prometheus-lua/Prometheus)。
- 诊断窗口文字由 Noto Sans CJK SC 预先渲染（SIL Open Font License 1.1）。
