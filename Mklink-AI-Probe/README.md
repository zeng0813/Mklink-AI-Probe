<div align="center">

# MKLink AI Probe

**嵌入式一站式调试工具** — 固件烧录 · RTT 可视化 · 内存读写 · HardFault 解码 · Modbus RTU · 远程 GUI

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Tauri](https://img.shields.io/badge/Tauri-v2-FFC131?logo=tauri&logoColor=black)](https://tauri.app)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[功能概览](#功能概览) · [快速开始](#快速开始) · [高速内存协议](#高速内存协议-dump-memory--flush-memory) · [探针固件](#探针固件-mk-firmware) · [命令速查](#命令速查) · [架构](#架构)

</div>

---

## 功能概览

| 功能 | 说明 |
|------|------|
| **固件烧录** | 一键烧录 Keil/IAR 工程产物（HEX/BIN），自动检测 MCU 与 FLM |
| **RTT 实时捕获** | SEGGER RTT 数据流捕获，内置波形可视化（RTT View / VOFA+） |
| **SuperWatch** | 高频变量连续采样与实时 Web 波形图（支持 `--dump-mem` 高速协议） |
| **高速内存协议** | `dump-memory` 二进制帧采集（固件 B1 自动分块）；`flush-memory` 静默写入 |
| **内存读写** | RAM / Flash / 寄存器读写，十六进制查看器 |
| **符号与类型** | 通过 DWARF/ELF 解析 AXF 符号表、结构体、枚举定义 |
| **HardFault 解码** | Cortex-M Fault 寄存器自动解码，addr2line 源码定位 |
| **Modbus RTU** | 完整 Modbus 调试：扫描、读写、轮询、点表生成、Web Dashboard |
| **串口调试** | 通用 UART 终端，支持自定义协议 Profile |
| **探针固件管理** | 内置 V3/V4 匹配 `.uf2`，连接时自动版本检查与升级指引 |
| **远程 GUI** | FastAPI 后端 + Vue 3 SPA，浏览器即用 |
| **Tauri 桌面** | Rust 桌面应用，Python sidecar，原生窗口体验 |
| **AI Agent 集成** | Claude / Cursor / OpenAI Agent 通过 Skill + CLI 直接操控硬件 |

## Screenshots

<table>
  <tr>
    <td align="center"><b>ConfigView — 工程配置与设备连接</b></td>
    <td align="center"><b>Dashboard — RTT 实时波形可视化</b></td>
  </tr>
  <tr>
    <td><img src="docs/gui-config.png" width="480" /></td>
    <td><img src="docs/gui-dashboard.png" width="480" /></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>SuperWatch — 高频变量实时监控</b></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><img src="docs/gui-superwatch.png" width="480" /></td>
  </tr>
</table>

## 快速开始

本仓库是一个 **AI Agent Skill**。把本目录交给 AI，它会自动读取 Skill 并完成环境配置。

### 给 AI 的一句话

> 请读取当前 Mklink-AI-Probe 目录，安装 Skill，并帮我初始化嵌入式调试环境。

### AI 会做什么

1. 读取 [`SKILL.md`](SKILL.md) — 命令路由与 Agent 约束
2. 按 [`references/install.md`](references/install.md) 安装 `mklink` Python 包
3. 根据意图查阅 `references/` 文档，执行 `python -m mklink <command>`

### 典型工作流

```bash
python -m mklink project-init   # 检测工程、MCU、COM 口，并校验探针固件版本
python -m mklink flash          # 烧录固件
python -m mklink rtt --duration 10
```

启动 GUI：`python -m mklink gui` 或 `cd gui && npx tauri dev`。

> 手动安装见 [references/install.md](references/install.md)。

## 高速内存协议（dump-memory / flush-memory）

V3.3.1 / V4.3.1 探针固件新增 `cmd.dump_memory` 与 `cmd.flush_memory` 公共 API，适合 SuperWatch 高频采样、压力测试、与目标固件并发读写。

### dump-memory — 高速采集（固件侧自动分块）

调用固件 `cmd.dump_memory(addr, size, ..., period)`，返回 `MPMDMPMD` 魔数的二进制帧。CLI 进入流模式解析，默认只采 1 个样本（`--frames 1 --duration 2`），避免串口长期占用。

| 协议 | 触发条件 | 说明 |
|------|----------|------|
| **OLD** | 单次总量 ≤ 2048 B | 单帧返回全部 region 数据 |
| **B1** | 单次总量 > 2048 B | 固件按 **2048 B/block** 自动分块传输；CLI 重组各 block 后计为 1 个完整样本 |

要点：

- 单次调用上限 **32 KiB**（多 region 合计）；更大范围需在 host 侧拆成多次命令
- 支持最多 **16 个 region**，格式 `ADDR:SIZE`；`--period` 控制周期采样
- B1 帧带 `block_index` / `block_count` / `block_crc32`，CLI 等到最后一块才算样本完成
- SuperWatch 的 `--dump-mem` 模式优先走此协议，不支持时回退 `read_ram` 轮询

```bash
# 读取 16 字节 RAM（OLD 帧）
python -m mklink dump-memory 0x20000000:16

# 读取 2049 字节 Flash（触发 B1 分块）
python -m mklink dump-memory 0x08020000:2049

# 双 region 周期采样，JSON 逐帧输出
python -m mklink dump-memory 0x20000000:16 0x20001000:4 --period 0.01 --frames 10 --json
```

### flush-memory — 静默写入（适合与 dump 并发）

调用固件 `cmd.flush_memory()`，成功时**不输出 hexdump**，只回显命令 + `>>>`，不会污染 `dump-memory` 的二进制流（`write-ram` 的预览会打断帧解析）。

| 场景 | PikaScript 形态 | 推荐边界 |
|------|-----------------|----------|
| 单地址 | `cmd.flush_memory(addr, b0, b1, ...)` | 1~16 字节稳定（varargs 上限约 20 B） |
| 多地址 | `cmd.flush_memory([(addr, bytes([...])), ...])` | ≤ 8 个地址项，单块 ≤ 12 KB |

```bash
# 单地址多字节（走旧协议，最稳定）
python -m mklink flush-memory 0x20010000:0xDE,0xAD,0xBE,0xEF

# 多地址一次提交（单笔 MCU-RTT 往返）
python -m mklink flush-memory 0x20010000:0x11,0x22 0x20010100:0x44,0x55,0x66

# 写后回读校验；周期重复写（压力测试）
python -m mklink flush-memory 0x20010000:0x55 --verify --repeat 100 --interval-ms 10
```

> CLI **不自动分块**——超出 12 KB / 8 地址项时需自行拆分多次调用。完整边界与分块策略见 [references/flush-memory.md](references/flush-memory.md)；内存命令总览见 [references/commands-memory.md](references/commands-memory.md)。

## 探针固件（MK-Firmware）

仓库自带与 CLI/GUI 版本匹配的烧录器固件：

| 文件 | 适用探针 |
|------|----------|
| `MK-Firmware/MicroLink_V3.3.1.uf2` | MicroLink V3 |
| `MK-Firmware/MicroLink_V4.3.1.uf2` | MicroLink V4 |

`mklink/firmware_check.py` 在 `project-init` 和 GUI 连接时自动检查探针版本：

- 读取 `cmd.get_version()`，与 `MK-Firmware/` 中最低版本比对
- 版本过低时提示升级，并推荐**同 major 号**（V3→V3、V4→V4）的 `.uf2` 文件及操作步骤
- 可通过环境变量 `MKLINK_FIRMWARE_DIR` 覆盖固件目录

```bash
python -m mklink version          # 查看当前探针固件版本
python -m mklink version --all    # 含历史版本记录
```

`dump-memory` / `flush-memory` 需要 V3.3.1 / V4.3.1 及以上探针固件；旧版探针请按提示拖入对应 `.uf2` 升级。

## 命令速查

| 命令 | 说明 |
|------|------|
| `project-init` / `project-info` | 初始化 / 查看项目配置（含探针固件检查） |
| `flash` | 一站式烧录（连接 → IDCODE → FLM → 烧录） |
| `version` | 读取烧录器固件版本 |
| `rtt` / `rtt-integrate` / `rtt-find` | RTT 捕获 / 源码集成 / 地址查找 |
| `read-ram` / `write-ram` / `read-flash` / `read-reg` | 内存与寄存器读写 |
| `dump-memory` (`dump`) | 高速二进制帧采集（B1 自动分块，别名 `dump`） |
| `flush-memory` | 静默写 RAM，适合与 dump 并发 |
| `vofa` / `watch` / `superwatch` | 变量观测与高频采样 |
| `symbols` / `typeinfo` / `memmap` | AXF 符号、DWARF 类型、段表分析 |
| `hardfault` | Cortex-M Fault 寄存器解码 |
| `modbus` / `serial` | Modbus RTU / 通用串口调试 |
| `resources` | 本地资源管理（释放 stale 串口锁） |
| `serve` / `gui` | 远程 API 服务 / Web GUI |
| `discover` / `test` | 发现探针端口 / 连接测试 |
| `halt` / `resume` / `step` / `break` | CPU 调试控制 |

完整命令文档见 [references/](references/) 目录。

## 架构

```
┌─────────────────────────────────────────────┐
│            Tauri 桌面应用 / 浏览器 GUI         │
│          (Vue 3 + TypeScript SPA)           │
├─────────────────────────────────────────────┤
│         FastAPI 服务 (REST + SSE + WS)       │
│               port 8765                     │
├─────────────────────────────────────────────┤
│         Device / DeviceDispatcher            │
│      MKLinkSerialBridge (pyserial)          │
│            进程级 SerialLock                 │
├─────────────────────────────────────────────┤
│         MKLink 探针 (USB CDC)               │
│              SWD / JTAG                     │
├─────────────────────────────────────────────┤
│         目标 MCU (ARM Cortex 内核)           │
└─────────────────────────────────────────────┘
```

**两种使用方式：**

- **CLI 模式** — `python -m mklink <command>`，适合脚本化和 AI Agent 集成
- **GUI 模式** — 浏览器或 Tauri 桌面窗口，可视化操作

## 开发构建

### Python 包

```bash
pip install -e .                    # 基础安装
pip install -e ".[gui]"             # 含 GUI 依赖
pip install -e ".[e2e]"             # 含 E2E 测试依赖
python -m mklink serve --port 8765  # 启动 API 服务
```

### Tauri 桌面应用

```bash
cd gui
npm install                         # 安装前端依赖
npm run dev                         # Vite 开发服务器（仅前端）
npx tauri dev                       # 完整 Tauri 开发模式
npx tauri build                     # 生产构建（MSI + NSIS）
```

> Tauri 构建需要 Rust 工具链和 MSVC Build Tools，详见 [references/install.md](references/install.md)。

### 测试

```bash
# Python 单元测试
pytest

# 前端单元测试
cd gui && npm test

# GUI E2E 测试（Playwright + Mock API）
cd gui && npm run build
pytest _maintainer/testing/tests/e2e/gui -q --run-e2e

# HIL 硬件测试（需 MKLink 探针 + 目标 MCU）
pytest _maintainer/testing/tests/e2e/hil -q --run-hil
```

## 可选依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| `arm-none-eabi-readelf` | AXF 符号解析、DWARF 类型查询、HardFault 源码定位 | `winget install Arm.GnuArmEmbeddedToolchain` |
| Node.js | Tauri 桌面应用、Vue 前端构建 | `winget install OpenJS.NodeJS.LTS` |
| Rust | Tauri v2 桌面应用编译 | [rustup.rs](https://rustup.rs) |

## 支持的 MCU

支持所有 **ARM Cortex 内核** MCU，通过 MKLink 探针 SWD/JTAG 连接，不限于特定厂商或型号。

- 探针自动读取 IDCODE，匹配烧录算法（FLM）
- `mklink/mcu_profiles.json` 管理内存映射与 Flash 参数，可按需扩展
- 已内置 ST、Nationstech、GD、MM32 等常用型号配置

## 项目结构

```
.
├── SKILL.md                 # AI Agent Skill 入口
├── agents/                  # OpenAI Agent 配置
├── mklink/                  # 核心 Python 包
│   ├── cli.py               # CLI 命令调度
│   ├── dump_memory.py       # dump_memory 二进制帧解析（OLD + B1）
│   ├── firmware_check.py    # 探针固件版本检查
│   ├── flash.py / rtt.py / superwatch.py
│   ├── remote/              # FastAPI 远程服务
│   ├── modbus/ / serial/
├── gui/                     # Vue 3 + Tauri GUI
├── references/              # 命令与安装文档（AI 按需读取）
├── MK-Firmware/             # MicroLink V3/V4 匹配固件 (.uf2)
└── scripts/                 # 示例脚本
```

## License

MIT License
