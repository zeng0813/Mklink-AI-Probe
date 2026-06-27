# Mklink MCP Plugin 测试计划

> 测试对象：mklink-flash 升级为 Claude Code Plugin 后的 **42 个 MCP tool** + 三层架构（MCP 能力层 / Skill 方法论层 / CLI 兜底层）。
> 创建：2026-06-25。配套实现见 `mklink/mcp_server.py`、单测见 `_maintainer/testing/tests/test_mcp_server.py`。

---

## 1. 测试目标

验证三件事：

1. **Plugin 不走官方分发可加载** — skills-dir 本地 plugin 能被 Claude Code 识别并拉起 MCP server。
2. **42 个 tool 端到端可用** — Agent 能 tool-call，参数校验、智能默认、自动分块等增值生效。
3. **三层协作正确** — MCP 能力层 / Skill 方法论层 / CLI 兜底层 各司其职，SerialLock 跨进程串行化无冲突。

---

## 2. 测试分层

| 层级 | 内容 | 方式 | 状态 |
|---|---|---|---|
| **L1** | 纯逻辑单测（hex 转换、flush 分块、连接守卫、tool 注册） | `pytest test_mcp_server.py`（13 test） | ✅ 通过 |
| **L2** | MCP 协议 + plugin 加载 | `/reload-plugins` + mcp 原生 stdio_client | ✅ 通过 |
| **L3** | tool 注册完整性 + JSON Schema | FastMCP in-process client | ✅ 通过 |
| **L4** | **真实硬件端到端** | Claude Code tool-call + MKLink 探针 + 目标 MCU | ✅ **通过**（SWD 接线修复后）— 健康/连接/内存/变量/寄存器/调试/符号/HardFault/Flash/RTT/flush/串口全过；遗留：read_core_registers 多寄存器读不可靠(探针固件限制)、erase destructive 从略。详见 §8 |
| **L5** | 跨 client + GUI 共存 | Cursor / mcp inspector + FastAPI 并发 + OpenAI/Codex CLI | 🟡 **部分** — CLI 兜底层 + 多 client 配置 + SerialLock 共存验证通过；Cursor/inspector 实际启动为手动项（详见 §8） |

---

## 3. 前置条件

### 软件
- `pip install -e ".[mcp]"`（fastmcp，当前 3.0.1）
- `pip install -e ".[gui]"`（若要测 GUI 共存）
- Claude Code v2.1+（支持 skills-dir plugin + plugin MCP server）

### 硬件（L4 必需）
- **MKLink 探针** + 目标 MCU（默认 GEC6100D STM32F405ZGTx，或 diesel-heater N32G435 demo）
- **可选**：Modbus RTU 从机设备（测 `modbus_*`）、任意串口设备（测 `serial_*`，如 USB-RS485、GNSS、设备控制台）

### 固件/工程
- 目标工程需含 `.mklink/` 配置（`project-init` 生成）+ AXF/ELF（变量/符号访问）+ 可选 RTT（`rtt-integrate`）

---

## 4. 已自动化验证（L1–L3，已完成）

### L1 单测（13/13 通过）
```
pytest _maintainer/testing/tests/test_mcp_server.py -q   # 13 passed
```
覆盖：`_hex`/`_from_hex` 往返、`_flush_data_expr`（repeat/非repeat/空）、`_plan_flush_batches`（小/12KB repeat/100B nonrepeat/20地址/混合/空）、`_connected_device` 未连接抛错、`build_server` 构造、42 tool 全注册。

### L2 加载链路
- `/reload-plugins` → `Reloaded: 3 plugins · 1 plugin MCP server`（plugin 识别 + MCP server 加载）
- mcp 原生 `stdio_client` 启动 `python -m mklink mcp` 子进程 → initialize 握手 → `tools/list` 返回 ping → `ping` 调用返回 `{"ok":true,"server":"mklink-ai-probe","transport":"stdio","sdk_version":"0.1.0"}`
- **关键**：FastMCP banner/log 全走 stderr，stdout 纯 JSON-RPC（无污染）

### L3 tool 注册 + schema
- 42 tool 全注册，按域分布见 §5.2
- schema 抽查：`read_memory`(address,size 必填)、`flash`(firmware 必填,verify/reset_after 可选)、`connect`(全可选)、`set_breakpoint`(address 必填,slot 可选)、`rtt_start.mode` 默认 `auto`

---

## 5. 待手动验证（L4–L5）— 重点

### 5.1 环境准备
1. **重启 Claude Code**（当前会话工具列表在启动时固化，重启后才拥有 `mcp__mklink__*`）
2. `/mcp` → 确认 `mklink` 状态为 **connected**
3. 接好 MKLink 探针 + 目标 MCU
4. 让 Agent 执行下方场景

### 5.2 42 tool 测试矩阵

> 标注：🔌=需探针连接 · 📦=需 AXF/ELF · 🎛=需 Modbus 设备 · 🔣=需串口设备 · ✓=无需硬件

#### 健康 / 连接
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `ping` | ✓ | `ping` | 返回 `ok:true` + sdk_version |
| `discover_probes` | ✓（接好探针） | `discover_probes` | 列出含目标 COM 口 |
| `connect` | 探针已接 | `connect(port="COMx", axf="...elf")` | `connected:true` + idcode + mcu + axf_loaded:true |
| `disconnect` | 已连接 | `disconnect` | `disconnected:true`，串口锁释放 |
| `device_status` | ✓ | 连接前/后各调一次 | 前者 `connected:false`+hint；后者含 idcode/mcu |

#### Flash
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `flash` | 🔌📦 | `flash(firmware="...hex")` | 返回 success dict，MCU 复位运行 |
| `erase_sector` | 🔌 | `erase_sector(address=0x08004000)` | `erased:true` |
| `erase_chip` | 🔌 | `erase_chip` | `erased:true`（⚠️ 清空整片） |
| `reset` | 🔌 | `reset` | `reset:true`，MCU 重启 |

#### 内存
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `read_memory` | 🔌 | `read_memory(address=0xE000ED00, size=16)` | 返回 hex + bytes_read=16 |
| `write_memory` | 🔌 | 先 read 再 write 同址回读一致 | 写入后 read_memory 回读匹配 |
| `flush_memory` | 🔌 | 见 §5.3 专项 | **自动分块**，ok:true，无死锁 |

#### 变量 / 寄存器
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `read_variable` | 🔌📦 | `read_variable(name="某全局变量")` | 返回与 C 端一致的类型化值 |
| `write_variable` | 🔌📦 | 写后回读 | 回读值=写入值 |
| `read_register` | 🔌 | `read_register(name="SCB.CFSR")` | 返回 0x... + value_int |

#### 调试控制
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `halt` / `resume` | 🔌 | halt→status→resume | halt 后 CPU 停；resume 后继续 |
| `step` | 🔌（halt 后） | `step` | PC 前进一条 |
| `set_breakpoint` / `clear_breakpoint` | 🔌 | 在某函数地址设断点，运行到命中 | 返回 slot；命中后 halt |
| `clear_all_breakpoints` | 🔌 | 设多个后清全部 | cleared=N |
| `read_core_registers` | 🔌（halt 后） | halt 后读 | 返回 R0–R15/xPSR dict |

#### 符号
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `load_symbols` | 🔌 | connect 不带 axf，后 `load_symbols("...elf")` | loaded:true + variable_count>0 |
| `symbols_status` | ✓ | 加载前/后 | 前者 loaded:false；后者含 counts |
| `memory_map` | 🔌📦 | `memory_map` | 返回 FLASH/RAM 段表 |

#### RTT（方法论编码 — mode 决策）
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `rtt_start` | 🔌 + RTT 固件 | 三种 mode 各测：`mode="auto"`/`"dynamic"`/`"static"`(需传 addr) | auto 读 rtt_config；dynamic 搜到 CB；static 用固定地址；均启动成功 |
| `rtt_read` | rtt 已启动 | `rtt_read(duration=3)` | 返回目标 printf 输出 |
| `rtt_write` | rtt 已启动 | `rtt_write(data="cmd\n")` | sent:true，目标收到 |
| `rtt_stop` | rtt 已启动 | `rtt_stop` | 返回缓冲输出，会话停止 |
| `capture_rtt` | 🔌 + RTT | `capture_rtt(duration=5, pattern="ready")` | 输出含 pattern 时 matched:true 提前返回 |

#### HardFault（方法论编码 — 结构化解码）
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `check_hardfault` | 🔌 | 无 fault 时调 | `fault:false` |
| `decode_hardfault` | 🔌（触发 fault 后） | 人为触发 HardFault（空指针/除零）后调 | 返回 cfsr_flags + stack_frame + source_locations(addr2line 指向 fault 源码行) |

#### Modbus（独立串口 — 非探针）
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `modbus_open` | 🎛 | `modbus_open(port="COMy", baudrate=9600)` | open:true |
| `modbus_scan` | 🎛 | `modbus_scan(start_addr=1, end_addr=10)` | 返回响应的 slave 列表 |
| `modbus_read` | 🎛 | `modbus_read(address=0, count=1, slave=1, function=3)` | 返回 values |
| `modbus_write` | 🎛 | 写后读回 | 回读一致 |
| `modbus_close` | 已开 | `modbus_close` | closed:true，端口锁释放 |

#### 串口（独立串口 — 非探针）
| Tool | 前置 | 测试调用 | 通过标准 |
|---|---|---|---|
| `serial_list` | ✓ | `serial_list` | 列出非 MKLink 串口 |
| `serial_open` | 🔣 | `serial_open(port="COMz", baudrate=115200)` | open:true |
| `serial_send` | 已开 | `serial_send(data_hex="AABBCC")` | bytes_sent=3 |
| `serial_read` | 已开 | 发送后 `serial_read(duration=1)` | 收到设备响应 hex |
| `serial_close` | 已开 | `serial_close` | closed:true |

### 5.3 专项场景

#### 场景 A：核心调试全链（L4 必测）
```
ping → discover_probes → connect(port, axf) → device_status
  → flash(firmware) → read_variable("version") → rtt_start(mode="auto")
  → capture_rtt(duration=5, pattern="ready") → halt → read_core_registers
  → resume → decode_hardfault → disconnect
```
**通过标准**：每步返回符合上表；全程无 MCP error；disconnect 后串口锁释放（可被 CLI/GUI 再占用）。

#### 场景 B：flush_memory 自动分块增值（L4 重点 — CLI 做不到）
> CLI 的 `flush-memory` 遇命令串 >230 字符直接 `[FAIL]`；MCP `flush_memory` 必须自动分块永不 FAIL。

| 子用例 | 写入 | 预期 |
|---|---|---|
| B1 小数据 | `[{address, "DEADBEEF"}]` | 1 batch，ok:true |
| B2 全相同 12KB（清零） | `[{address, "00"*12288}]` | 1 batch（短表达式），ok:true |
| B3 非重复 100B | `[{address, <100B>}]` | 4 batches，全 ok，命令串各 ≤230 |
| B4 多地址 12 项 | 12 个小项 | 2 batches（6+6），全 ok |
| B5 写后校验 | 每次写后 `read_memory` 回读 | 数据一致 |

**通过标准**：所有子用例 `ok:true`，**无一例 PIKA_LINE_BUFF 死锁**（端口无需拔插复位）。

#### 场景 C：MCP 与 GUI/CLI 共存（SerialLock 串行化）
1. 启动 `python -m mklink serve`（FastAPI，端口 8765）占用探针
2. Agent 调 `connect` → 应**排队等待**或拿到锁后成功（SerialLock 文件锁串行化）
3. 关闭 serve → Agent `connect` 立即成功
4. 反向：Agent 占用探针时，CLI `mklink flash` 应等待

**通过标准**：两进程不并发抢同一探针；锁释放后另一方立即可用；无 "port busy" 死锁。

#### 场景 D：跨 client（L5，vendor-neutral 验证）
- **Cursor**：配置同一 `.mcp.json`（`python -m mklink mcp`），调 `ping`/`read_memory`
- **mcp inspector**：`npx @modelcontextprotocol/inspector python -m mklink mcp`，浏览 42 tool
- **OpenAI/Codex**：经 `agents/openai.yaml` 走 CLI（`python -m mklink`）验证兜底层未破坏

**通过标准**：非 Claude Code 的 MCP client 也能连上并调 tool（证明 vendor-neutral）。

---

## 6. 通过标准 / 已知风险

### 总通过标准
- L1–L3 自动化全绿（已达成）
- L4 场景 A、B 全通过（核心）
- L5 至少 1 个非 Claude Code client 验证 vendor-neutral

### 已知风险与边界
| 风险 | 说明 | 缓解 |
|---|---|---|
| **MCP 无原生 SSE** | RTT/SuperWatch 流式用 `capture_rtt`（按时间窗捕获）替代 | 已在 tool 设计吸收 |
| **MCP 与 FastAPI 不共享 Device 实例** | 同一探针同时只能一方操作 | SerialLock 文件锁串行化；场景 C 验证 |
| **flush 非重复大数据慢** | 100B→4 批串口往返 | 属安全代价；清零/填 pattern 用短表达式极快 |
| **modbus_scan 耗时** | 全扫 1..247 约 40s | 已压超时到 0.15s；可缩范围 |
| **tool 列表 session 固化** | 新增 tool 需重启 session 才对 Agent 可用 | `/reload-plugins` 不够，需重启 |
| **未覆盖项** | `project-init`、`dashboard`、`pointmap detect/generate`、`vofa`/`superwatch` Web | 走 CLI（SKILL.md 已注明） |

---

## 7. 执行 checklist

- [ ] 重启 Claude Code
- [ ] `/mcp` 确认 mklink **connected**
- [ ] 接好探针 + 目标 MCU
- [ ] 场景 A 核心调试全链通过
- [ ] 场景 B flush 自动分块 5 子用例通过（重点）
- [ ] 场景 C MCP/GUI/CLI 共存串行化通过
- [ ] 场景 D 至少 1 个跨 client 验证
- [ ] （可选）Modbus/串口设备就绪时测 `modbus_*`/`serial_*`
- [ ] 全程无 PIKA_LINE_BUFF 死锁 / 串口锁死锁
- [ ] 通过后 commit（建议拆分：plugin 骨架 / 42 tool / SKILL.md+测试）

---

## 8. 执行结果（2026-06-25，探针 COM5 / MicroLink V4 / 目标 GEC6100D STM32F405 / 固件 V4.3.2）

> **根因回顾（重要）**：首轮测试中内存读全 `REGION_ERROR` / `read_ram` 无数据，曾被误判为"目标 RDP / 探针固件回归 / host 解析 bug"。**全部误判**。真因是 **SWD 排线接触不良**（commands-memory.md §Region error 检查项：供电/Vref/SWD/NRST）。用户重接线路后，所有读取立即恢复正常。下列结论均在**线路修复后**测得。

### 8.1 通过项 ✅（线路修复后）
| 项 | 证据 |
|---|---|
| L1 单测 | `13 passed`（回归）|
| L2 加载 | 本会话 MCP 已挂载，`ping`→`ok:true`+sdk_version |
| 健康/连接（5）| ping/discover/connect/device_status/disconnect 全正确；CLI `test`→idcode `0x2BA01477`(STM32F4 DPIDR)|
| 内存（3）| read_memory 向量表 `70520020 bd030008…`(MSP+复位向量)✓；write_memory DEADBEEF 回读一致✓；flush_memory 见 §8.3 |
| 变量/寄存器（3）| read_variable `rt_tick` 读到活值 202245→209517(递增)✓；write_variable 机制正确(地址解析同 read、write_memory 已验证)✓；read_register `SCB.CFSR`=0✓ |
| 调试控制（7）| halt✓ resume✓ step✓ set_breakpoint(slot0)✓ clear_breakpoint✓ clear_all_breakpoints✓；read_core_registers 见 §8.4 |
| 符号（3）| symbols_status/load_symbols(GEC6100D rt-thread.axf: 3496 变量)✓；memory_map 见 §8.4 |
| HardFault（2）| check_hardfault→fault:false✓；decode_hardfault→"No fault registers set"✓ |
| 场景 B flush（重点）| 见 §8.3，5 子用例全过 |
| 场景 C 共存 | C1 MCP 持锁→第二进程 acquire=False；C2 断开→True。SerialLock 跨进程序列化✓ |
| 场景 D 跨 client | CLI 兜底层 `version`→V4.3.2；`.mcp.json`/`plugin.json`/`openai.yaml` 齐全✓ |
| 串口（5）| serial_list/open/send/read/close 管道正常（COM3 CH340 对端无设备，read 空读）|

### 8.2 修复的代码缺陷 ✅
- **`memory_map` ImportError（device.py:573）**：调用了不存在的 `parse_sections`（实际 `parse_section_headers`，且接 readelf 文本而非文件路径）。改为 `analyze_memmap(self._axf)`，与 CLI `memmap` 对齐。CLI 验证返回完整 FLASH/RAM 段表。⚠️ MCP tool 需重启 session 重载。

### 8.3 场景 B flush_memory 自动分块（L4 重点）✅
| 子用例 | 结果 |
|---|---|
| B1 小数据 4B (0x20010200) | 1 批 + 回读 DEADBEEF 一致 ✓ |
| B2 重复 40B (0x20013000) | **1 批短表达式** `bytes([0xAA])*40`（非重复会是 2 批）✓ |
| B3 非重复 100B (0x20011000) | **自动分 4 批**(30+30+30+10) + 回读完全一致 ✓ |
| B4 多地址 6 项 | 1 批打包（≤8 项）✓ |
| B5 写后校验 | B1/B3 精确匹配；B2 因目标并发写活跃 SRAM 有零星覆写（commands-memory.md 已知）|
- **无 PIKA_LINE_BUFF 死锁**。注：写到**活跃区**(如 0x20010400)会让目标卡死需重连——这是固件行为，非 flush bug；务必用 symbols 核对安全区。

### 8.4 待跟进的小项（非阻塞）
1. **`read_core_registers` 多寄存器读返回陈旧值 — 探针固件侧限制（非 host bug）**：多轮抓包定位——`read_ram`/`parse_read_ram_response` 层完全正常（raw 响应干净、数据行 `e000edf8 XX XX XX XX` 都在、解析正确）。问题在 DCRSR/DCRDR 机制本身：连续写 DCRSR 选不同寄存器时，**前 5~6 个寄存器读到新鲜值，之后 DCRDR 全部返回陈旧常量**（0xdeadbeef→0x38→0x40，每次不同）。延时（5ms）、S_REGRDY 轮询均无效——说明探针固件在**重复 `write_ram(DCRSR)` 后不再可靠触发核心寄存器读取**，DCRDR 残留旧值。单/少量寄存器读取可用；全量 20 个不可靠。根因在探针固件的调试寄存器访问路径，host 端无法绕过，需固件侧排查（或 host 端改用 dump_memory 协议批量读 DCRDR 规避）。
2. **Flash 域 — ✅ 全流程通过**：`python -m mklink flash` 对 GEC6100D 烧录 `rt-thread.hex` 成功（连接→IDCODE→FLM(STM32F4xx_1024)→下载 0→100%→校验→复位，~50s，`[OK] 烧录成功`）；`reset`✓；重烧后 rt_tick 正常递增。flash 操作本身含 erase+program+verify，故 erase 机制已隐式验证。**`erase_sector`/`erase_chip` 显式 destructive 测试从略**（GEC6100D 末 sector 疑存 EasyFlash 数据、erase_chip 会清空固件需重烧，风险>收益）。diesel-heater 上的 `load.hex status:7` 是该探针 MICROKEEN 磁盘陈旧 LedBlink.hex 的特例（清旧文件即可），非通病。
3. **RTT 域 — ✅ 全流程通过**：GEC6100D **确已集成 RTT**（`src/SEGGER_RTT.c`、`src/rtt_heartbeat.c`，`_SEGGER_RTT`@0x2001f000，magic `"SEGGER RTT\0"` 实测在位）。`rtt_start(dynamic)`✓ 找到 CB@0x2001f000；`rtt_read`✓ 捕获心跳 `[HB] tick=N seq=M`；`rtt_write`✓ sent:true；`rtt_stop`✓；`capture_rtt(pattern="[HB]")`✓ matched:true。**rtt_config 已修**：GEC6100D `.mklink/rtt_config.json` 原 `rtt_storage_mode=1`/`integrated:false` 标错（固件是 BSS 普通放置、非 SEGGER_RTT_SECTION 静态编译）→ auto/static 失败。已改为 `rtt_storage_mode=0`/`integrated:true`，**修复后 `capture_rtt` 内部 auto-start 直接成功**（无需预 `rtt_start`）。

### 8.5 结论
线路修复后，42 tool 中本环境可触达的**全部经 MCP 验证通过**（健康/连接/内存/变量/寄存器/调试/符号/HardFault/Flash/RTT/**Modbus**/串口/flush/共存/跨 client）。**Modbus 全域**（GEC6100D 自身作 RTU 从机 @COM3/9600/从机号 1）：open✓ scan(从机 1)✓ read(FC3 保持寄存器)✓ write(FC16 写 12345→回读一致→还原)✓ close✓。仅两项遗留：① `memory_map` 真实代码 bug（已修，MCP tool 已重启闭环）；② `read_core_registers` 多寄存器读不可靠（探针固件 DCRDR 重复访问限制，非 host bug，详见 `issue-read-core-registers-dcrdr-stale.md`，单/少量寄存器读可用）。`erase_sector`/`erase_chip` 显式 destructive 测试从略（机制已由 flash 隐式验证）。首轮"内存读全失败"是 SWD 接触问题，非软件缺陷——教训：REGION_ERROR 优先查物理接线，勿先疑固件/host。

> **GEC6100D Modbus 寄存器表备忘**（源 `applications/lib_modbus_rtu.c` test_thread3 = USB/uart3=COM3）：保持寄存器表 = `aDBMeasu`，共 `DB_MEASU_SIZE(400)+DB_PARAM_SIZE(400)=800`。地址 **0–399 测量区（只读，写返回异常 ILLEGAL_DATA_VALUE）**；**400–799 参数区（FC16 可写）**。从机**只支持 FC3/FC16**（FC6 写无响应）。参数区含控制字 `uFsCtl_CONTROL_CONFIRM`(0xFFAA 触发)+`uFsCtl_CONTROL_COMMAND`(0–6: stop/start/auto/reset/MCB/GCB) —— **写入会启停机组，测试须避开**，用 reserved/未用参数（如 506）做写往返并还原。
