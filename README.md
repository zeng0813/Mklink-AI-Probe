<div align="center">

# MKLink AI Probe

**嵌入式一站式调试工具** — 固件烧录 · RTT/SystemView 可视化 · 内存读写 · HardFault 解码 · Modbus RTU · MCP Agent · 远程 GUI

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Tauri](https://img.shields.io/badge/Tauri-v2-FFC131?logo=tauri&logoColor=black)](https://tauri.app)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[功能概览](#功能概览) · [快速开始](#快速开始) · [MCP / AI Agent](#mcp--ai-agent-集成) · [SystemView](#systemview-rtos-跟踪) · [高速内存协议](#高速内存协议dump-memory--flush-memory) · [探针固件](#探针固件mk-firmware) · [命令速查](#命令速查)

</div>

---

## 功能概览

| 功能 | 说明 |
|------|------|
| **固件烧录** | 一键烧录 Keil/IAR 工程产物（HEX/BIN），自动检测 MCU 与 FLM |
| **RTT 实时捕获** | SEGGER RTT 数据流捕获，内置波形可视化（RTT View / VOFA+） |
| **SystemView RTOS 跟踪** | 通过 RTT 通道采集 SEGGER SystemView 事件，解码任务切换、ISR、CPU 占用并提供 GUI 时间轴 |
| **SuperWatch** | 高频变量连续采样与实时 Web 波形图（支持 `--dump-mem` 高速协议） |
| **高速内存协议** | `dump-memory` 单次默认 512 KiB（V4.3.3 实测）；`flush-memory` 支持 `ADDR:BYTE*N` 紧凑写入 |
| **内存读写** | RAM / Flash / 寄存器读写，十六进制查看器 |
| **探针固件管理** | 内置 V3.3.3 / V4.3.3 `.uf2`，连接时自动版本检查与升级指引 |
| **符号与类型** | 通过 DWARF/ELF 解析 AXF 符号表、结构体、枚举定义 |
| **HardFault 解码** | Cortex-M Fault 寄存器自动解码，addr2line 源码定位 |
| **Modbus RTU** | 完整 Modbus 调试：扫描、读写、轮询、点表生成、Web Dashboard |
| **串口调试** | 通用 UART 终端，支持自定义协议 Profile |
| **MCP 能力层** | `python -m mklink mcp` 暴露 51 个 MCP tool，供 Claude Code / Cursor / ChatGPT 等 MCP client 调用 |
| **远程 GUI** | FastAPI 后端 + Vue 3 SPA，浏览器即用 |
| **Tauri 桌面** | Rust 桌面应用，Python sidecar，原生窗口体验 |
| **AI Agent 集成** | MCP tool 优先，CLI 兜底；Skill 文档负责路由、边界和排查方法论 |

## Screenshots

<table>
  <tr>
    <td align="center"><b>ConfigView — 工程配置与设备连接</b></td>
    <td align="center"><b>Dashboard — RTT 实时波形可视化</b></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><b>SuperWatch — 高频变量实时监控</b></td>
  </tr>
</table>

## 快速开始

本仓库同时是 **Claude Code Plugin**、**AI Agent Skill** 和可直接安装的 Python CLI。把 `Mklink-AI-Probe/` 目录交给 AI，它会优先通过 MCP tool 操作硬件；无 MCP 环境时回退到 `python -m mklink <command>`。

### 给 AI 的一句话

> 请读取 `Mklink-AI-Probe/` 目录，安装 Mklink AI Probe Skill，并帮我初始化嵌入式调试环境。

### AI 会做什么

1. 读取 [`Mklink-AI-Probe/SKILL.md`](Mklink-AI-Probe/SKILL.md) — Skill 入口、MCP/CLI 路由、Agent 约束
2. 识别 [`Mklink-AI-Probe/.claude-plugin/plugin.json`](Mklink-AI-Probe/.claude-plugin/plugin.json) 与 [`Mklink-AI-Probe/.mcp.json`](Mklink-AI-Probe/.mcp.json)
3. 按 [`Mklink-AI-Probe/references/install.md`](Mklink-AI-Probe/references/install.md) 安装 `mklink` Python 包、GUI 与 MCP 依赖
4. 根据你的意图查阅 `references/` 下的命令文档，优先调用 MCP tool，必要时执行 `python -m mklink <command>`

### 典型工作流（由 AI 代劳）

```bash
cd Mklink-AI-Probe
python -m pip install -e ".[gui,mcp]"
python -m mklink project-init   # 自动检测 Keil/IAR 工程、MCU、COM 口
python -m mklink flash          # 烧录固件
python -m mklink rtt --duration 10   # 捕获 RTT 数据
```

启动 GUI：`python -m mklink gui`（浏览器）或 `cd Mklink-AI-Probe/gui && npx tauri dev`（桌面应用）。

> 手动安装说明见 [Mklink-AI-Probe/references/install.md](Mklink-AI-Probe/references/install.md)。

## MCP / AI Agent 集成

`python -m mklink mcp` 以 stdio 方式启动 MCP server，当前暴露 51 个 `mcp__mklink__*` tool，覆盖连接、烧录、内存、变量、断点、符号、RTT、SystemView、HardFault、Modbus 与串口。

```bash
cd Mklink-AI-Probe
python -m pip install -e ".[mcp]"
python -m mklink mcp
```

- **MCP 优先**：Claude Code / Cursor / ChatGPT 等 MCP client 可直接调用结构化 tool。
- **CLI 兜底**：无 MCP 或需要可视化工作流时，使用 `python -m mklink <command>`。
- **Skill 方法论**：`SKILL.md` 与 `references/` 负责说明何时用哪个 tool、边界条件和排查步骤。

## SystemView RTOS 跟踪

mklink 已内置 SEGGER SystemView RTOS Trace 支持：目标固件把事件写入 RTT 上行通道 1，PC 端直接解码任务切换、ISR、CPU 占用并在 CLI/HTML/GUI 中展示，不依赖 J-Link 或 SEGGER PC 工具。

```bash
python -m mklink rtt-integrate --project-root .          # 先集成 RTT
python -m mklink systemview-integrate --project-root .   # 集成 SEGGER_SYSVIEW 到 RT-Thread 工程
python -m mklink systemview --duration 10                # 实时打印事件
python -m mklink systemview-analyze --duration 6         # CPU% / 切换 / ISR 分析
python -m mklink systemview-report --duration 6 --out report.html
python -m mklink gui                                    # Dashboard -> RTOS Trace
```

MCP 等价能力：`systemview_integrate`、`systemview_start`、`capture_systemview`、`systemview_analyze`、`systemview_report`。详细集成说明见 [systemview-rtthread.md](Mklink-AI-Probe/references/systemview-rtthread.md)。

## 高速内存协议（dump-memory / flush-memory）

V3.3.3 / V4.3.3 探针固件继续增强 `cmd.dump_memory` 与 `cmd.flush_memory` 公共 API；老固件仍可使用基础功能，但大块读写边界更保守。

### dump-memory — 高速采集（固件侧自动分块）

调用 `cmd.dump_memory(addr, size, ..., period)`，返回 `MPMDMPMD` 二进制帧：

| 协议 | 触发条件 | 说明 |
|------|----------|------|
| **OLD** | 单次总量 ≤ 2048 B | 单帧返回全部数据 |
| **B1** | 单次总量 > 2048 B | 固件按 **2048 B/block** 自动分块；CLI 重组后计为 1 个完整样本 |

- 单次默认上限 **512 KiB**（多 region 合计，V4.3.3 实测整片 Flash 稳定）；老固件建议限制到 ≤32 KiB
- 支持最多 16 个 region（`ADDR:SIZE`）
- SuperWatch `--dump-mem` 优先走此协议，不支持时回退 `read_ram` 轮询

```bash
python -m mklink dump-memory 0x20000000:16              # OLD 帧
python -m mklink dump-memory 0x08020000:2049            # 触发 B1 分块
python -m mklink dump-memory 0x08000000:524288 --save flash.bin
python -m mklink dump-memory 0x20000000:16 --period 0.01 --frames 10
```

### flush-memory — 静默写入（适合与 dump 并发）

成功时**不输出 hexdump**，不会污染 `dump-memory` 二进制流（`write-ram` 会打断帧解析）。

| 场景 | 推荐边界 |
|------|----------|
| 单地址 `ADDR:BYTE,...` | 1~16 字节稳定（varargs 上限约 20 B） |
| 单地址重复字节 `ADDR:BYTE*N` | ≤ 12 KB 推荐；V4.3.3 实测约 16.1 KiB 上限，不建议压线 |
| 多地址一次提交 | ≤ 8 个地址项，单块 ≤ 12 KB |

```bash
python -m mklink flush-memory 0x20010000:0xDE,0xAD,0xBE,0xEF
python -m mklink flush-memory "0x20008000:0xAA*12288" --verify
python -m mklink flush-memory 0x20010000:0x11,0x22 0x20010100:0x44,0x55 --verify
```

> 边界详情：[references/flush-memory.md](Mklink-AI-Probe/references/flush-memory.md) · 命令总览：[references/commands-memory.md](Mklink-AI-Probe/references/commands-memory.md)

## 探针固件（MK-Firmware）

| 文件 | 适用探针 | 状态 |
|------|----------|------|
| `MK-Firmware/MicroLink_V3.3.3.uf2` | MicroLink V3 | **最新** |
| `MK-Firmware/MicroLink_V4.3.3.uf2` | MicroLink V4 | **最新** |

### V3.3.3 / V4.3.3 更新内容

- 继承 V3.3.2 / V4.3.2 的 M0 内核下载提速与脱机下载兼容性修复。
- `dump_memory` 大块读取边界提升：V4.3.3 已验证 512 KiB Flash dump（256 个 B1 块）稳定。
- `flush_memory` 重复字节写入边界重新验证，推荐用 `ADDR:BYTE*N` 短表达式并按 12 KB 分块。

`firmware_check.py` 在 `project-init` 和 GUI 连接时自动比对探针版本，过低时提示拖入同 major 号的 `.uf2` 升级。`dump-memory` / `flush-memory` 需 V3.3.1 / V4.3.1 及以上固件，大块稳定性建议使用 V3.3.3 / V4.3.3。

```bash
python -m mklink version       # 查看当前探针固件版本
```

可通过 `MKLINK_FIRMWARE_DIR` 环境变量覆盖固件目录。

## 命令速查

| 命令 | 说明 |
|------|------|
| `mcp` | 启动 MCP server（stdio，供 Claude Code / Cursor / ChatGPT 等 MCP client 调用） |
| `project-init` / `project-info` | 初始化 / 查看项目配置 |
| `flash` | 一站式烧录（连接 → IDCODE → FLM → 烧录） |
| `version` | 读取烧录器固件版本 |
| `rtt` / `rtt-integrate` / `rtt-find` | RTT 捕获 / 源码集成 / 地址查找 |
| `read-ram` / `write-ram` / `read-flash` / `read-reg` | 内存与寄存器读写 |
| `dump-memory` (`dump`) | 高速二进制帧采集（B1 自动分块，V4.3.3 单次默认 512 KiB） |
| `flush-memory` | 静默写 RAM，支持 `ADDR:BYTE*N` 紧凑语法，适合与 dump 并发 |
| `vofa` / `watch` / `superwatch` | 变量观测与高频采样 |
| `systemview` | 一站式 SystemView RTOS 跟踪，实时解码任务切换 / ISR |
| `systemview-integrate` | 集成 SEGGER_SYSVIEW 到 RT-Thread 工程 |
| `systemview-analyze` / `systemview-report` | 采集 SystemView 并输出运行态分析或 HTML 报告 |
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

**三种使用方式：**

- **MCP 模式** — `python -m mklink mcp`，供 AI Agent 调用结构化 tool
- **CLI 模式** — `python -m mklink <command>`，适合脚本化、人工操作和无 MCP 环境
- **GUI 模式** — 浏览器或 Tauri 桌面窗口，可视化操作

## 开发构建

工作目录为 `Mklink-AI-Probe/`（含 `pyproject.toml` 的 Skill 根目录）。

### Python 包

```bash
cd Mklink-AI-Probe
pip install -e .                    # 基础安装
pip install -e ".[gui]"             # 含 GUI 依赖
pip install -e ".[mcp]"             # 含 MCP server 依赖
python -m mklink mcp                # 启动 MCP server（stdio）
python -m mklink serve --port 8765  # 启动 API 服务
```

### Tauri 桌面应用

```bash
cd Mklink-AI-Probe/gui
npm install
npm run build:test                  # 测试模式构建
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
├── README.md                 # 总览文档
├── LICENSE
└── Mklink-AI-Probe/          # Skill 与 Python 包根目录
    ├── .claude-plugin/       # Claude Code plugin manifest
    ├── .mcp.json             # MCP server 启动配置
    ├── SKILL.md              # AI Agent Skill 入口
    ├── commands/             # Agent/命令快捷入口
    ├── mklink/               # 核心 Python 包
    │   ├── cli.py            # CLI 命令调度
    │   ├── mcp_server.py     # MCP tools
    │   ├── dump_memory.py    # dump_memory 二进制帧解析（OLD + B1）
    │   ├── firmware_check.py # 探针固件版本检查
    │   ├── systemview*.py    # SystemView 采集、解析、分析、报告
    │   ├── flash.py / rtt.py / superwatch.py
    │   ├── remote/           # FastAPI 远程服务
    │   ├── modbus/           # Modbus RTU
    │   └── serial/           # 串口通信
    ├── gui/                  # Vue 3 + Tauri GUI
    │   └── src/components/dash/SystemViewTab.vue
    ├── references/           # 命令与安装文档（AI 按需读取）
    ├── MK-Firmware/          # MicroLink 烧录器固件 (.uf2)
    ├── skills/               # 子技能 / 辅助构建 skill
    └── scripts/              # 示例脚本
```

## License

MIT License
