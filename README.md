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
| **探针固件管理** | 内置 V3/V4 匹配 `.uf2`，连接时自动版本检查与升级指引 |
| **符号与类型** | 通过 DWARF/ELF 解析 AXF 符号表、结构体、枚举定义 |
| **HardFault 解码** | Cortex-M Fault 寄存器自动解码，addr2line 源码定位 |
| **Modbus RTU** | 完整 Modbus 调试：扫描、读写、轮询、点表生成、Web Dashboard |
| **串口调试** | 通用 UART 终端，支持自定义协议 Profile |
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
    <td><img src="Mklink-AI-Probe/docs/gui-config.png" width="480" /></td>
    <td><img src="Mklink-AI-Probe/docs/gui-dashboard.png" width="480" /></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>SuperWatch — 高频变量实时监控</b></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><img src="Mklink-AI-Probe/docs/gui-superwatch.png" width="480" /></td>
  </tr>
</table>

## 快速开始

本仓库是一个 **AI Agent Skill**，不需要手动逐条执行安装命令。把 `Mklink-AI-Probe/` 目录交给 AI，它会自动读取 Skill 并完成环境配置。

### 给 AI 的一句话

> 请读取 `Mklink-AI-Probe/` 目录，安装 Mklink AI Probe Skill，并帮我初始化嵌入式调试环境。

### AI 会做什么

1. 读取 [`Mklink-AI-Probe/SKILL.md`](Mklink-AI-Probe/SKILL.md) — Skill 入口、命令路由、Agent 约束
2. 按 [`Mklink-AI-Probe/references/install.md`](Mklink-AI-Probe/references/install.md) 安装 `mklink` Python 包及可选依赖
3. 根据你的意图查阅 `references/` 下的命令文档，执行 `python -m mklink <command>`

### 典型工作流（由 AI 代劳）

```bash
python -m mklink project-init   # 自动检测 Keil/IAR 工程、MCU、COM 口
python -m mklink flash          # 烧录固件
python -m mklink rtt --duration 10   # 捕获 RTT 数据
```

启动 GUI：`python -m mklink gui`（浏览器）或 `cd Mklink-AI-Probe/gui && npx tauri dev`（桌面应用）。

> 手动安装说明见 [Mklink-AI-Probe/references/install.md](Mklink-AI-Probe/references/install.md)。

## 高速内存协议（dump-memory / flush-memory）

V3.3.1 / V4.3.1 探针固件新增 `cmd.dump_memory` 与 `cmd.flush_memory` 公共 API。

### dump-memory — 高速采集（固件侧自动分块）

调用 `cmd.dump_memory(addr, size, ..., period)`，返回 `MPMDMPMD` 二进制帧：

| 协议 | 触发条件 | 说明 |
|------|----------|------|
| **OLD** | 单次总量 ≤ 2048 B | 单帧返回全部数据 |
| **B1** | 单次总量 > 2048 B | 固件按 **2048 B/block** 自动分块；CLI 重组后计为 1 个完整样本 |

- 单次上限 **32 KiB**（多 region 合计）；支持最多 16 个 region（`ADDR:SIZE`）
- SuperWatch `--dump-mem` 优先走此协议，不支持时回退 `read_ram` 轮询

```bash
python -m mklink dump-memory 0x20000000:16              # OLD 帧
python -m mklink dump-memory 0x08020000:2049            # 触发 B1 分块
python -m mklink dump-memory 0x20000000:16 --period 0.01 --frames 10
```

### flush-memory — 静默写入（适合与 dump 并发）

成功时**不输出 hexdump**，不会污染 `dump-memory` 二进制流（`write-ram` 会打断帧解析）。

| 场景 | 推荐边界 |
|------|----------|
| 单地址 `ADDR:BYTE,...` | 1~16 字节稳定（varargs 上限约 20 B） |
| 多地址一次提交 | ≤ 8 个地址项，单块 ≤ 12 KB |

```bash
python -m mklink flush-memory 0x20010000:0xDE,0xAD,0xBE,0xEF
python -m mklink flush-memory 0x20010000:0x11,0x22 0x20010100:0x44,0x55 --verify
```

> 边界详情：[references/flush-memory.md](Mklink-AI-Probe/references/flush-memory.md) · 命令总览：[references/commands-memory.md](Mklink-AI-Probe/references/commands-memory.md)

## 探针固件（MK-Firmware）

| 文件 | 适用探针 |
|------|----------|
| `MK-Firmware/MicroLink_V3.3.1.uf2` | MicroLink V3 |
| `MK-Firmware/MicroLink_V4.3.1.uf2` | MicroLink V4 |

`firmware_check.py` 在 `project-init` 和 GUI 连接时自动比对探针版本，过低时提示拖入同 major 号的 `.uf2` 升级。`dump-memory` / `flush-memory` 需 V3.3.1 / V4.3.1 及以上固件。

```bash
python -m mklink version       # 查看当前探针固件版本
```

可通过 `MKLINK_FIRMWARE_DIR` 环境变量覆盖固件目录。

## 命令速查

| 命令 | 说明 |
|------|------|
| `project-init` / `project-info` | 初始化 / 查看项目配置 |
| `flash` | 一站式烧录（连接 → IDCODE → FLM → 烧录） |
| `version` | 读取烧录器固件版本 |
| `rtt` / `rtt-integrate` / `rtt-find` | RTT 捕获 / 源码集成 / 地址查找 |
| `read-ram` / `write-ram` / `read-flash` / `read-reg` | 内存与寄存器读写 |
| `dump-memory` (`dump`) | 高速二进制帧采集（B1 自动分块） |
| `flush-memory` | 静默写 RAM，适合与 dump 并发 |
| `vofa` / `watch` / `superwatch` | 变量观测与高频采样 |
| `symbols` / `typeinfo` / `memmap` | AXF 符号、DWARF 类型、段表分析 |
| `hardfault` | Cortex-M Fault 寄存器解码 |
| `modbus` / `serial` | Modbus RTU / 通用串口调试 |
| `resources` | 本地资源管理（释放 stale 串口锁） |
| `serve` / `gui` | 远程 API 服务 / Web GUI |
| `discover` / `test` | 发现探针端口 / 连接测试 |
| `halt` / `resume` / `step` / `break` | CPU 调试控制 |

完整命令文档见 [Mklink-AI-Probe/references/](Mklink-AI-Probe/references/) 目录。

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

工作目录为 `Mklink-AI-Probe/`（含 `pyproject.toml` 的 Skill 根目录）。

### Python 包

```bash
cd Mklink-AI-Probe
pip install -e .                    # 基础安装
pip install -e ".[gui]"             # 含 GUI 依赖
python -m mklink serve --port 8765  # 启动 API 服务
```

### Tauri 桌面应用

```bash
cd Mklink-AI-Probe/gui
npm install
npx tauri dev                       # 开发模式
npx tauri build                     # 生产构建（MSI + NSIS）
```

> Tauri 构建需要 Rust 工具链和 MSVC Build Tools，详见 [references/install.md](Mklink-AI-Probe/references/install.md)。

### 测试

```bash
cd Mklink-AI-Probe
pytest                              # Python 单元测试
cd gui && npm test                  # 前端单元测试
```

## 可选依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| `arm-none-eabi-readelf` | AXF 符号解析、DWARF 类型查询、HardFault 源码定位 | `winget install Arm.GnuArmEmbeddedToolchain` |
| Node.js | Tauri 桌面应用、Vue 前端构建 | `winget install OpenJS.NodeJS.LTS` |
| Rust | Tauri v2 桌面应用编译 | [rustup.rs](https://rustup.rs) |

## 支持的 MCU

支持所有 **ARM Cortex 内核** MCU（Cortex-M / Cortex-A 等），通过 MKLink 探针的 SWD/JTAG 接口连接，不限于特定厂商或型号。

- 探针自动读取芯片 IDCODE，匹配烧录算法（FLM）
- 内存映射、Flash 参数等通过 `mklink/mcu_profiles.json` 配置，可按需扩展
- 已内置多厂商常用型号配置（ST、Nationstech、GD、MM32 等），新芯片只需添加对应 profile

## 项目结构

```
Mklink-AI-Probe/              # 本仓库根目录
└── Mklink-AI-Probe/          # Skill 与 Python 包根目录
    ├── SKILL.md              # AI Agent Skill 入口
    ├── agents/               # OpenAI Agent 配置
    ├── mklink/               # 核心 Python 包
    │   ├── cli.py            # CLI 命令调度
    │   ├── dump_memory.py    # dump_memory 二进制帧解析（OLD + B1）
    │   ├── firmware_check.py # 探针固件版本检查
    │   ├── flash.py / rtt.py / superwatch.py
    │   ├── remote/           # FastAPI 远程服务
    │   ├── modbus/           # Modbus RTU
    │   └── serial/           # 串口通信
    ├── gui/                  # Vue 3 + Tauri GUI
    ├── references/           # 命令与安装文档（AI 按需读取）
    ├── MK-Firmware/          # MicroLink 烧录器固件 (.uf2)
    └── scripts/              # 示例脚本
```

## License

MIT License
