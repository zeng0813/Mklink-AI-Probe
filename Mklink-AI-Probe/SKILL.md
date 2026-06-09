---
name: mklink-ai-probe
description: |
  MKLink/MicroLink 嵌入式 CLI：固件烧录、RTT View/VOFA/SuperWatch 可视化、RAM/寄存器读写、
  AXF 符号与 HardFault 调试、Modbus RTU、通用串口调试、远程 GUI/API。
  触发：Keil/IAR 初始化/烧录、RTT/VOFA 观测、read_ram/watch/superwatch、
  Modbus 扫描/读写/dashboard/点表生成、串口 open/send/dashboard、resources、symbols/typeinfo、dump-memory、flush-memory、version、serve/gui、
  RTT 控制块静态编译（rtt_storage_mode=1）、散射文件中固定 RTT 地址、MKLINK_RTT_STATIC 宏、`.ARM.__at_0xADDR` 段名。
---

# Mklink AI Probe Skill

## Agent 核心约束

**所有功能通过 CLI 调用：`python -m mklink <command> [options]`**

- **禁止**编写 Python 脚本替代 CLI；常用操作均有对应命令
- Modbus **同一 COM 口禁止并行访问**（scan/read/dashboard/poll 等须串行）
- Modbus 点表：先 `modbus pointmap detect`，汇报并确认后再 `generate`
- 执行具体命令前：**先 Read 下方路由表对应的 reference，再运行 CLI**

## 命令速查

| 命令 | 说明 |
|------|------|
| `serve` | 远程调试服务器（REST API + WebSocket JSON-RPC） |
| `gui` | 启动 GUI（FastAPI 后端 + Vue 前端） |
| `project-init` | 初始化项目配置（自动检测 IAR/Keil、MCU、COM 口） |
| `project-info` | 显示项目配置状态 |
| `flash` | 一站式烧录（连接 → IDCODE → FLM → 烧录） |
| `rtt` | 一站式 RTT 捕获（支持 `--visualize`） |
| `read-ram` | 读取 RAM 数据（十六进制 dump） |
| `read-reg` | 读取内存映射寄存器 |
| `write-ram` | 写入 RAM 并回读验证 |
| `dump-memory` / `dump` | 公共高速内存 dump（`cmd.dump_memory` 二进制帧；默认采集 1 个样本） |
| `flush-memory` | 静默写 RAM，**多地址多字节**（成功无 ACK；适合与 `dump_memory` 并发场景）。<br>**边界**: 单项 ≤ 12KB, 多地址 ≤ 8 项, varargs ≤ 20 字节, 详见 [references/flush-memory.md](references/flush-memory.md) |
| `read-flash` | 读取 Flash 数据 |
| `version` | 读取烧录器自身固件版本（`--all` 显示历史，`--raw` 原始输出） |
| `vofa` | VOFA+ 实时变量观测（支持 `--visualize`） |
| `symbols` | 从 ELF/AXF 列出 RAM 变量（需 readelf） |
| `typeinfo` | 从 AXF DWARF 查询类型/结构体/枚举 |
| `watch` | 按变量名读取快照（支持 `struct.field`） |
| `superwatch` | 时间戳连续采样（支持 `--visualize`、`--dump-mem`） |
| `hardfault` | 解码 Cortex-M Fault 寄存器与异常栈帧 |
| `memmap` | 分析 AXF 段表（RAM/Flash 占用） |
| `rtt-integrate` | 集成 RTT 源码到 Keil/IAR 项目 |
| `rtt-find <map>` | 从 MAP 文件查找 RTT 地址 |
| `rtt_storage_mode=1` | 静态 RTT 编译（详见 [references/rtt-static-mode.md](references/rtt-static-mode.md)） |
| `copy-flm` | 拷贝 FLM 到 MICROKEEN 磁盘（仅 Keil） |
| `keil-parse` / `iar-parse` | 解析 Keil/IAR 工程文件 |
| `discover` | 发现 MKLink 端口 |
| `test --port COM6` | 测试连接 |
| `modbus` | Modbus RTU 调试（scan/read/write/poll/monitor/dashboard） |
| `serial` | 通用 UART 串口调试 |
| `resources` / `resource` | 本地资源管理（释放 stale 串口/MKLink 锁；不需要 FastAPI） |

## 模块路由（渐进式披露）

| 用户意图 / 关键词 | 读取文档 |
|------------------|----------|
| 安装、pip、readelf、Rust、Tauri | [references/install.md](references/install.md) |
| 烧录、RTT、project-init、Keil/IAR | [references/commands-flash-rtt.md](references/commands-flash-rtt.md) |
| RTT 静态编译、rtt_storage_mode、MKLINK_RTT_STATIC、.ARM.__at_0xADDR、CB 固定地址 | [references/rtt-static-mode.md](references/rtt-static-mode.md) |
| flush-memory 边界、12KB 分块策略、推荐用法 | [references/flush-memory.md](references/flush-memory.md) |
| RAM、VOFA、watch、HardFault、AXF | [references/commands-memory.md](references/commands-memory.md) |
| Modbus、RS485、点表、dashboard | [references/commands-modbus.md](references/commands-modbus.md) |
| 串口、UART、协议 profile | [references/commands-serial.md](references/commands-serial.md) |
| serve、gui、Tauri、桌面应用、远程调试 | [references/commands-remote-gui.md](references/commands-remote-gui.md) |
| 「用户说 X 我该跑什么」 | [references/triggers.md](references/triggers.md) |
| 新项目首次烧录、RTT 集成、故障排查 | [references/workflows.md](references/workflows.md) |

## 快速开始

```bash
python -m mklink project-init
python -m mklink flash
python -m mklink rtt --duration 10
```

首次使用请先安装依赖，见 [references/install.md](references/install.md)：

```bash
python -m pip install -e .
```

## 输出格式

- **成功**: `[OK] 操作描述`
- **失败**: `[FAIL] 错误原因`
- **警告**: `[WARN] 警告信息`
- **自动操作**: `[AUTO] 自动执行的操作`
- **RTT 输出**: 实时流式显示原始数据
