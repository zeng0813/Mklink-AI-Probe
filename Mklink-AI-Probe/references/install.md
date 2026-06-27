# 安装与可选依赖

> 触发词：pip、ensurepip、readelf、arm-none-eabi、winget
> 返回索引：[SKILL.md](../SKILL.md)

## 安装步骤

在使用本 Skill 之前，必须先安装 `mklink` Python 包：

```bash
# 1. 如果 Python 没有 pip，先引导安装
python -m ensurepip --upgrade

# 2. 从本 Skill 目录安装 mklink 包（ editable 模式）
python -m pip install -e .

# 3. 如果使用 Modbus 功能，确保安装 pymodbus（已在依赖中自动安装）
pip install pymodbus>=3.0
```

安装完成后，`python -m mklink` 命令即可正常使用。


## 作为 Claude Code 插件使用（MCP 能力层）

本 Skill 同时是一个 Claude Code **插件**：根目录 `.claude-plugin/plugin.json` + `.mcp.json` 暴露 **42 个 MCP tool**（`mcp__mklink__*`，覆盖连接/烧录/内存/变量/调试/符号/RTT/HardFault/Modbus/串口），由 `python -m mklink mcp` 以 stdio 方式启动。MCP server **依赖 `fastmcp`**，需安装 `mcp` extras：

```powershell
pip install -e ".[mcp]"
```

验证 MCP server 可启动（应向 stderr 打印 FastMCP 横幅并等待 stdio JSON-RPC 输入，Ctrl+C 退出）：

```powershell
python -m mklink mcp
```

**普通用户安装本插件**（无需上架 marketplace，走 skills-directory 机制）：

```powershell
# 1. 把本目录放到 Claude Code 的 skills 目录下
git clone <repo-url> "$env:USERPROFILE\.claude\skills\mklink-flash"
#   （或手动复制整个目录到 ~/.claude/skills/mklink-flash/）

# 2. 安装 Python 包 + MCP 依赖（使 .mcp.json 中的 python -m mklink mcp 可用）
cd "$env:USERPROFILE\.claude\skills\mklink-flash"
pip install -e ".[mcp]"

# 3. 重启 Claude Code —— 自动加载为 mklink-flash@skills-dir，MCP 工具即可用
```

> 仅使用 CLI、不用 MCP 的用户：跳过 `.[mcp]`，`pip install -e .` 即可。
> 符号解析 / AXF 调试另需下文的 `arm-none-eabi-readelf`。


## GNU Arm readelf（符号解析与 AXF 调试）

当用户要执行以下功能时，必须提供 `arm-none-eabi-readelf`：

- `python -m mklink symbols --source <firmware.axf>`
- `python -m mklink vofa <符号名>,... --visualize --source <firmware.axf>`
- `python -m mklink typeinfo --source <firmware.axf> --var <name>`
- `python -m mklink watch` / `superwatch`（使用 `--source <firmware.axf>` 时）
- `python -m mklink hardfault --source <firmware.axf> --sp <stack_pointer>`

先检查依赖是否已经可用：

```powershell
arm-none-eabi-readelf --version
```

若命令不存在，优先使用 winget 安装官方 GNU Arm Embedded Toolchain：

```powershell
winget install --id Arm.GnuArmEmbeddedToolchain -e --accept-package-agreements --accept-source-agreements
```

如果 winget 安装器被 UAC、GUI 或权限问题中断，使用无管理员权限的便携安装方式：

```powershell
$toolsDir = Join-Path $env:USERPROFILE ".local\tools"
$zipPath = Join-Path $toolsDir "arm-gnu-toolchain-14.2.rel1-mingw-w64-i686-arm-none-eabi.zip"
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

curl.exe -L "https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/binrel/arm-gnu-toolchain-14.2.rel1-mingw-w64-i686-arm-none-eabi.zip" -o $zipPath
tar -xf $zipPath -C $toolsDir

# 该 zip 解压后 bin 目录通常位于 $toolsDir\bin
$bin = Join-Path $toolsDir "bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $bin) {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$bin", "User")
}

# 让当前 PowerShell 立即可用
if (($env:Path -split ";") -notcontains $bin) {
  $env:Path = "$env:Path;$bin"
}
```

如果当前会话或 Python `subprocess.run(["arm-none-eabi-readelf", ...])` 仍找不到命令，可把真实 exe 复制到已在 PATH 中的用户 bin 目录：

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.local\bin" | Out-Null
Copy-Item "$env:USERPROFILE\.local\tools\bin\arm-none-eabi-readelf.exe" "$env:USERPROFILE\.local\bin\arm-none-eabi-readelf.exe" -Force
```

安装后必须验证：

```powershell
arm-none-eabi-readelf --version
python -c "import shutil, subprocess; print(shutil.which('arm-none-eabi-readelf')); subprocess.run(['arm-none-eabi-readelf','--version'], check=True)"
python -m mklink symbols --source path/to/firmware.axf --filter "counter|sensor"
```


### 不想把工具链加进 PATH？用环境变量或配置文件指定

mklink 按以下顺序解析 `readelf` / `addr2line`（命中即用，首次解析后缓存）：

1. 环境变量 `MKLINK_READELF` / `MKLINK_ADDR2LINE`（指向可执行文件全路径）
2. 项目配置 `.mklink/toolchain.json`：`{"readelf": "...", "addr2line": "..."}`
3. 常见安装位置（winget `Program Files`、WinGet 包缓存、`~/.local/tools`）
4. PATH 上的 `arm-none-eabi-readelf` / `arm-none-eabi-addr2line`
5. 系统 binutils 的 `readelf` / `addr2line`（GNU 版可读任意 ELF，够用）

适合用便携版、或不想污染全局 PATH 的用户：

```powershell
# 方式 A：环境变量（当前会话；持久化用 setx 或系统设置）
$env:MKLINK_READELF    = "$env:USERPROFILE\.local\tools\bin\arm-none-eabi-readelf.exe"
$env:MKLINK_ADDR2LINE  = "$env:USERPROFILE\.local\tools\bin\arm-none-eabi-addr2line.exe"

# 方式 B：项目级配置（可提交到仓库，团队共用）
New-Item -ItemType Directory -Force -Path .mklink | Out-Null
@{ readelf    = "C:/tools/arm-gnu/bin/arm-none-eabi-readelf.exe"
   addr2line  = "C:/tools/arm-gnu/bin/arm-none-eabi-addr2line.exe" } |
  ConvertTo-Json | Out-File -Encoding utf8 .mklink/toolchain.json
```

> MCP 用户：调用 `ping` 即可看到 `readelf_available` / `readelf_path`。工具缺失时
> `connect(axf=...)` 仍会成功（探针已连上），但返回 `axf_loaded:false` 并附 `axf_error`
> 安装提示——不会像以前那样整次连接崩溃。


## GUI 依赖（Web GUI 与 Tauri 桌面应用）

当用户需要以下功能时，需要安装 GUI 依赖：

- `mklink serve` — 远程调试服务器（REST API + WebSocket JSON-RPC）
- `mklink gui` — 启动 Web GUI（FastAPI 后端 + Vue 3 前端）
- Tauri 桌面应用 — 原生窗口体验

### Python GUI 依赖

先检查是否已安装：

```powershell
python -c "import fastapi, uvicorn; print('GUI deps OK')"
```

若导入失败：

```powershell
pip install -e ".[gui]"
```

### Node.js 依赖

Tauri 桌面应用和 Vue 3 前端需要 Node.js。先检查：

```powershell
node --version
```

若未安装，使用 winget：

```powershell
winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
```

然后安装前端依赖：

```powershell
cd gui
npm install
```

### Rust 工具链（Tauri 桌面应用）

Tauri v2 桌面应用需要 Rust 编译器。先检查：

```powershell
rustc --version
cargo --version
```

若未安装，分两步：

**步骤 1 — 安装 MSVC Build Tools**（Rust Windows 编译必需）：

```powershell
# 检查是否已有 Visual Studio 或 Build Tools
if (-not (Get-Command cl -ErrorAction SilentlyContinue)) {
    winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-package-agreements --accept-source-agreements --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive"
}
```

**步骤 2 — 安装 Rust**：

```powershell
# 下载并静默安装 rustup
$installer = "$env:TEMP\rustup-init.exe"
Invoke-WebRequest -Uri https://win.rustup.rs/x86_64 -OutFile $installer
& $installer -y --default-toolchain stable --default-host x86_64-pc-windows-msvc
Remove-Item $installer -Force

# 刷新当前会话 PATH
$env:Path += ";$env:USERPROFILE\.cargo\bin"
```

验证 Rust 安装：

```powershell
rustc --version
cargo --version
```

### Tauri 桌面应用启动

```powershell
# 开发模式（热重载，需同时手动启动 Python 后端）
cd gui
python -m mklink serve --port 8765 &   # 后端（另一终端）
npx tauri dev                           # Tauri 窗口
```

### Sidecar 打包（发布构建）

发布桌面安装包（MSI/NSIS）前，需将 Python 后端打包为独立可执行文件：

```powershell
pip install pyinstaller

# 打包 Python 后端为 mklink-sidecar.exe
pyinstaller --onefile --name mklink-sidecar --collect-all mklink -p .. mklink\__main__.py

# 将产物放入 Tauri 预期位置
New-Item -ItemType Directory -Force -Path "src-tauri\binaries" | Out-Null
Copy-Item dist\mklink-sidecar.exe "src-tauri\binaries\mklink-sidecar-x86_64-pc-windows-msvc.exe" -Force

# 构建桌面安装包
npx tauri build
```

构建产物位于 `gui/src-tauri/target/release/bundle/`。
