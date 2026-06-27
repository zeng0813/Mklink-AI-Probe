---
name: tauri-gui-builder
description: |
  Mklink AI Probe Tauri v2 桌面 GUI 构建工具。编译 Rust + Vue 3 前端为原生 Windows exe。
  触发：编译 GUI、build tauri、构建桌面应用、打包 exe、tauri build、
  mklink-ai-probe.exe、MSI、NSIS、sidecar 打包。
---

# Mklink AI Probe Tauri GUI Builder

## 架构

```
mklink-ai-probe/gui/
├── src/                    # Vue 3 + TypeScript 前端
├── src-tauri/
│   ├── src/lib.rs          # Rust 入口（sidecar 进程管理）
│   ├── src/main.rs         # Windows main（release 隐藏控制台）
│   ├── Cargo.toml          # Rust 依赖：tauri v2 + tauri-plugin-shell
│   ├── tauri.conf.json     # Tauri 窗口/打包配置
│   └── capabilities/       # Tauri v2 权限
└── package.json            # Node 依赖：@tauri-apps/cli + @tauri-apps/api
```

运行时：Tauri 窗口 → Vue 3 SPA → Python FastAPI (8765) → MKLink 硬件

## 前置条件

执行构建前，先运行检查：

```powershell
python scripts/build.py --check
```

自动检测：Rust stable、Node.js、npm 依赖、Python mklink[gui]。缺失项会给出安装命令。

### Rust 工具链

```powershell
# 检查
rustc --version

# 安装（如缺失）
$installer = "$env:TEMP\rustup-init.exe"
Invoke-WebRequest -Uri https://win.rustup.rs/x86_64 -OutFile $installer
& $installer -y --default-toolchain stable --default-host x86_64-pc-windows-msvc
$env:Path += ";$env:USERPROFILE\.cargo\bin"
```

### Node.js

```powershell
node --version  # 需要 v18+
# 如缺失：winget install OpenJS.NodeJS.LTS
```

### Python GUI 依赖

```powershell
pip install -e ".[gui]"  # fastapi, uvicorn, websockets
```

## 构建

### 仅编译 exe（开发测试用）

```powershell
python scripts/build.py
```

产物：`gui/src-tauri/target/release/mklink-ai-probe.exe`（~10 MB）

exe 启动时自动检测 PATH 上的 `python`，执行 `python -m mklink serve --port 8765` 作为后端。

### 完整打包（含 sidecar，生成安装包）

```powershell
python scripts/build.py --bundle
```

额外步骤：
1. PyInstaller 打包 Python 后端为 `mklink-sidecar.exe`
2. 放入 `gui/src-tauri/binaries/mklink-sidecar-x86_64-pc-windows-msvc.exe`
3. `tauri.conf.json` 临时添加 `externalBin`
4. 生成 MSI + NSIS 安装包

产物位于 `gui/src-tauri/target/release/bundle/`。

### 开发模式（热重载）

```powershell
cd gui
npx tauri dev
```

自动启动 Vite dev server (5173) + Rust 编译。需另开终端运行 `python -m mklink serve`。

### 清理

```powershell
python scripts/build.py --clean
```

## 关键文件修改指引

| 改什么 | 改哪里 |
|--------|--------|
| 前端页面 | `gui/src/views/*.vue`、`gui/src/composables/*.ts` |
| 窗口大小/标题 | `gui/src-tauri/tauri.conf.json` → `app.windows` |
| Sidecar 启动逻辑 | `gui/src-tauri/src/lib.rs` → `start_sidecar()` |
| Tauri 权限 | `gui/src-tauri/capabilities/default.json` |
| Dashboard 端口映射 | `mklink/remote/api.py` → `DASHBOARD_PORTS` |
| Rust 依赖 | `gui/src-tauri/Cargo.toml` |

## 常见问题

**`cargo metadata` failed**：Rust 未安装或不在 PATH。运行 `rustup` 安装后重启终端。

**`resource path doesn't exist`**：`tauri.conf.json` 中 `externalBin` 引用了不存在的 sidecar。开发构建用 `--no-bundle` 或移除 `externalBin`。

**PyInstaller 打包后 sidecar 缺少模板文件**：确保 `--collect-all mklink` 参数存在，这会收集 HTML 模板和 JSON profile。

**首次编译慢（3-5 分钟）**：正常现象，Rust 需要编译 200+ crates。后续增量编译只需 30-40 秒。

## 验证

```powershell
# 启动 exe
./gui/src-tauri/target/release/mklink-ai-probe.exe

# 另一终端检查 API
curl http://127.0.0.1:8765/api/health
# 期望：{"status":"ok"}

curl http://127.0.0.1:8765/api/dashboard/status
# 期望：包含 rtt, serial, modbus, superwatch 四个 Dashboard
```
