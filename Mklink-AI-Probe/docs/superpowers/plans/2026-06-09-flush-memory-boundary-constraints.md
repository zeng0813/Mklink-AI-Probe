# flush-memory 边界约束沉淀实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `cmd.flush_memory` 的 6 类实测边界、推荐分块策略与校验建议沉淀到 skill 文档（0 代码改动）。

**Architecture:** 新建独立 reference 文件 `references/flush-memory.md` 作为权威边界说明；在 `SKILL.md` 增加路由条目与命令表约束提示；在 `commands-memory.md` 的现有 flush-memory 章节末尾追加交叉引用。

**Tech Stack:** Markdown 文档，纯人工编辑。

**前置依赖:** 已有 spec 文档 `docs/superpowers/specs/2026-06-09-flush-memory-boundary-constraints-design.md`（commit `dbba554`）。

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `references/flush-memory.md` | 新建 | 权威边界说明（8 章：接口定位 / 5 种用法 / 实测边界表 / 推荐边界 / 分块策略 / 校验 / 注意 / CLI 关系） |
| `SKILL.md` | 修改 2 处 | (a) 模块路由表新增 1 行 (b) 命令速查表 `flush-memory` 行加约束提示 |
| `references/commands-memory.md` | 修改 1 处 | flush-memory 章节末尾追加交叉引用小节 |

---

## Task 1: 新建 references/flush-memory.md

**Files:**
- Create: `references/flush-memory.md`

- [ ] **Step 1: 写入文件头与第 1 章「接口定位」**

创建文件 `references/flush-memory.md`，写入以下完整内容：

```markdown
---
name: flush-memory-boundary
description: |
  flush-memory / cmd.flush_memory 实测使用边界、推荐分块策略、校验建议。
  触发：flush-memory 边界、12KB 分块、单地址字节上限、varargs 字节上限、CDC 异常、flush fail。
---

# flush-memory 边界约束

> 适用命令：`python -m mklink flush-memory`
> 适用对象：MKLink 固件 PikaPython REPL 中的 `cmd.flush_memory` API
> 返回索引：[SKILL.md](../../SKILL.md) · [commands-memory.md](commands-memory.md)

## 1. 接口定位

`cmd.flush_memory` 是 MKLink 固件中的 PikaPython REPL API，**不是** `python -m mklink` 的 CLI 子命令。
它通过 MKLink 设备的 Python shell/CDC 串口发送命令，向目标 RAM 写入数据。

`python -m mklink flush-memory` CLI 是这个 REPL API 的封装者（`mklink/cli.py:_cli_flush_memory`）。

```

- [ ] **Step 2: 追加第 2 章「基本用法」（5 种调用形式）**

在文件末尾追加：

```markdown
## 2. 基本用法

### 2.1 老 varargs 形式

```python
cmd.flush_memory(0x20002000, 0x11, 0x22, 0x33, 0x44)
```

适合少量字节写入（≤20 字节稳定）。

### 2.2 单地址 bytes/list 写入

```python
cmd.flush_memory((0x20002000, bytes([0x11, 0x22, 0x33, 0x44])))
cmd.flush_memory((0x20002000, [0x11, 0x22, 0x33, 0x44]))
```

适合中大块连续数据写入（≤12KB 推荐）。

### 2.3 单地址 batch 形式

```python
cmd.flush_memory([
    (0x20002000, bytes([0x11, 0x22, 0x33, 0x44]))
])
```

边界与单地址 tuple 形式一致。

### 2.4 多地址多数据写入

```python
cmd.flush_memory([
    (0x20001080, bytes([0x11, 0x22, 0x33])),
    (0x20002000, bytes([0x44, 0x55, 0x66, 0x77])),
    (0x20003000, bytes([0x88])),
])
```

适合一次写入多个离散 RAM 地址（≤8 个地址项推荐）。

### 2.5 重复数据或 pattern 数据

```python
# 重复单字节
cmd.flush_memory([
    (0x20002000, bytes([0x5A]) * 1024)
])

# 16 字节 pattern 循环
cmd.flush_memory([
    (
        0x20002000,
        bytes([
            0x01, 0x05, 0x00, 0x01,
            0x00, 0x01, 0x5D, 0xCA,
            0x10, 0x20, 0x30, 0x40,
            0x55, 0xAA, 0x7E, 0x81,
        ]) * 64
    )
])
```

- [ ] **Step 3: 追加第 3 章「实测使用边界」（7 行表格）**

在文件末尾追加：

```markdown
## 3. 实测使用边界

测试环境：地址主要使用 `0x20002000`，写完通过 `cmd.read_ram` 读取头部、中间、尾部数据校验。

| 接口形式 | 推荐稳定边界 | 实测上限 | 失败边界 | 说明 |
|---|---:|---:|---:|---|
| `cmd.flush_memory(addr, b0, b1, ...)` | `≤ 20 bytes` | `20 bytes` | `21 bytes` | 老 varargs 形式。`addr + 20 bytes = 21` 个总参数可用，`addr + 21 bytes = 22` 个总参数异常 |
| `cmd.flush_memory((addr, data))` | `≤ 12KB` | `14KB` | `15KB` | 单地址 bytes/list 写入。14KB 头/中/尾读回通过，15KB 后 CDC 异常 |
| `cmd.flush_memory([(addr, data)])` | `≤ 12KB` | `14KB` | `15KB` | 单地址 batch 形式，边界与 tuple 单地址一致 |
| `cmd.flush_memory([(addr1, data1), ...])` | `≤ 8 个地址项` | `8 个地址项` | `12 个地址项` | 多地址多数据写入。9~11 项未细分，12 项失败后 CDC 异常 |
| 多地址总数据量 | `≤ 12KB` | 参考单地址 `14KB` | `15KB` | 地址项数未超时，总数据量仍建议按单地址边界控制 |
| `bytes([0x5A]) * N` | `≤ 12KB` | `14KB` | `15KB` | 重复字节填充测试通过 |
| `bytes([...16B...]) * N` | `≤ 12KB` | `14KB` | `15KB` | 16 字节实际 pattern 循环数据测试通过 |

```

- [ ] **Step 4: 追加第 4 章「推荐实际使用边界」与第 5 章「超额分块策略」**

在文件末尾追加：

```markdown
## 4. 推荐实际使用边界

```text
单次 flush_memory:
- 老 varargs 接口数据字节 ≤ 20 bytes
- 单地址/单块数据量 ≤ 12KB
- 多地址数量 ≤ 8 个地址项
- 多地址总数据量 ≤ 12KB

极限可用但不建议长期压线:
- 单地址数据量 ≤ 14KB
```

## 5. 超额分块策略

如需写入超过推荐边界的数据，建议上层（host 端脚本 / CLI 用户）分块：

```text
大块连续数据:
- 每块 ≤ 12KB
- 等待 REPL 返回 >>> 后再发送下一块

离散多地址数据:
- 每批 ≤ 8 个地址项
- 每批总数据量 ≤ 12KB
- 等待 REPL 返回 >>> 后再发送下一批
```

伪代码示例（仅参考，CLI 当前未实现自动分块）：

```python
# 大块连续数据分块
chunk_size = 12 * 1024
data = open("payload.bin", "rb").read()
for i in range(0, len(data), chunk_size):
    chunk = data[i:i+chunk_size]
    send(f"cmd.flush_memory((0x{0x20002000+i:08X}, bytes([{','.join(f'0x{b:02X}' for b in chunk)}])))")
    wait_for_prompt(">>>")
```

```

- [ ] **Step 5: 追加第 6、7、8 章「校验建议」「注意事项」「与 CLI 关系」**

在文件末尾追加：

```markdown
## 6. 校验建议

写入后建议读取头部和尾部数据确认：

```python
cmd.read_ram(0x20002000, 16)
cmd.read_ram(0x20002000 + N - 16, 16)
```

对于大块数据，建议额外读取中间位置：

```python
cmd.read_ram(0x20002000 + N // 2, 16)
```

## 7. 注意事项

- `cmd.flush_memory` 成功时通常只返回 `>>>`，不会打印成功文本。
- 失败时可能打印 `flush fail`，也可能导致 CDC 端口异常或短暂消失，需要复位或重插设备后继续。
- 通过 PC 串口 REPL 直接发送超长 `bytes([...])` 字面量会受 `PIKA_LINE_BUFF_SIZE` 和 PikaPython 解析能力限制。
- 大数据优先使用短表达式，例如 `bytes([0x5A]) * N` 或短 pattern 乘法。
- 完整 256 字节列表表达式如 `bytes([0, 1, ..., 255]) * k` 在当前测试固件中可能触发 `SyntaxError`。
- 测试地址必须确认是目标 RAM 空闲区，避免覆盖目标程序栈、堆、RTOS 对象、DMA 缓冲或显示缓冲。
- 边界与固件版本、`PIKA_LINE_BUFF_SIZE`、目标 RAM 布局、下载器状态有关，升级固件后应复测。

## 8. 与 CLI `flush-memory` 的关系

`python -m mklink flush-memory` 是 `cmd.flush_memory` 的 CLI 封装。

**重要约束**：

- CLI 当前**不自动分块**——超出推荐边界时仍按 1 次 PikaScript 命令提交，可能触发 CDC 异常。
- 超出失败边界（如 15KB / 12 项）时，CLI 不会自动降级，会返回 `FAIL`。
- 写入前请自行遵守本文档第 4 章「推荐实际使用边界」与第 5 章「超额分块策略」。
- CLI 的响应解析规则（静默成功 / `flush fail` 兼容 / WARN 降级）见 [commands-memory.md](commands-memory.md) 的 `flush-memory` 章节。
```

- [ ] **Step 6: 验证文件可读 + 行数合理**

```bash
wc -l "C:/Users/Tony/.claude/skills/mklink-flash/references/flush-memory.md"
```

期望：100~200 行。

- [ ] **Step 7: Commit Task 1**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
git add references/flush-memory.md
git -c user.email="claude@anthropic.com" -c user.name="Claude" commit -m "docs: 新建 references/flush-memory.md 边界说明"
```

---

## Task 2: 更新 SKILL.md — 模块路由表新增一行

**Files:**
- Modify: `SKILL.md:64`（在 rtt-static-mode.md 路由行后新增一行）

- [ ] **Step 1: 在模块路由表新增 flush-memory 路由行**

打开 `SKILL.md`，找到第 64 行（rtt-static-mode 路由行）：

```markdown
| RTT 静态编译、rtt_storage_mode、MKLINK_RTT_STATIC、.ARM.__at_0xADDR、CB 固定地址 | [references/rtt-static-mode.md](references/rtt-static-mode.md) |
```

在它**之后**插入新的一行：

```markdown
| flush-memory 边界、12KB 分块策略、推荐用法 | [references/flush-memory.md](references/flush-memory.md) |
```

插入后该表格在 rtt-static-mode 行附近变为：

```markdown
| RTT 静态编译、rtt_storage_mode、MKLINK_RTT_STATIC、.ARM.__at_0xADDR、CB 固定地址 | [references/rtt-static-mode.md](references/rtt-static-mode.md) |
| flush-memory 边界、12KB 分块策略、推荐用法 | [references/flush-memory.md](references/flush-memory.md) |
```

- [ ] **Step 2: 验证新增行存在**

```bash
grep -n "flush-memory 边界" "C:/Users/Tony/.claude/skills/mklink-flash/SKILL.md"
```

期望：输出一行，格式 `N: | flush-memory 边界、12KB 分块策略、推荐用法 | ...`

- [ ] **Step 3: Commit Task 2**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
git add SKILL.md
git -c user.email="claude@anthropic.com" -c user.name="Claude" commit -m "docs(SKILL): 模块路由表新增 flush-memory 边界路由"
```

---

## Task 3: 更新 SKILL.md — 命令速查表 flush-memory 行加约束提示

**Files:**
- Modify: `SKILL.md:36`（命令速查表 flush-memory 行的说明列）

- [ ] **Step 1: 替换命令速查表 flush-memory 行的说明列**

找到 SKILL.md 第 36 行：

```markdown
| `flush-memory` | 静默写 RAM，**多地址多字节**（成功无 ACK；适合与 `dump_memory` 并发场景） |
```

替换为：

```markdown
| `flush-memory` | 静默写 RAM，**多地址多字节**（成功无 ACK；适合与 `dump_memory` 并发场景）。<br>**边界**: 单项 ≤ 12KB, 多地址 ≤ 8 项, varargs ≤ 20 字节, 详见 [references/flush-memory.md](references/flush-memory.md) |
```

- [ ] **Step 2: 验证新行内容**

```bash
grep -n "12KB" "C:/Users/Tony/.claude/skills/mklink-flash/SKILL.md"
```

期望：输出一行，包含 `12KB` 与 `[references/flush-memory.md](references/flush-memory.md)`。

- [ ] **Step 3: Commit Task 3**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
git add SKILL.md
git -c user.email="claude@anthropic.com" -c user.name="Claude" commit -m "docs(SKILL): 命令速查表 flush-memory 行加边界提示"
```

---

## Task 4: 更新 commands-memory.md flush-memory 章节末尾追加交叉引用

**Files:**
- Modify: `references/commands-memory.md:164`（在「验证技巧」小节后追加「边界与分块约束」）

- [ ] **Step 1: 在「验证技巧」小节末尾追加交叉引用**

打开 `references/commands-memory.md`，找到「验证技巧」小节（以 `##### 验证技巧` 开头）。
在该小节内容**之后**追加：

```markdown
##### 📌 边界与分块约束

`flush-memory` 的 CLI 实现**不自动分块**,超额时按 1 次命令提交。
完整边界(单项数据量 ≤ 12KB,多地址 ≤ 8 项,varargs ≤ 20 字节,失败边界 15KB/12 项)
与 host 端分块策略见 **[references/flush-memory.md](references/flush-memory.md)**。
```

追加位置：小节中最后一个代码块之后、下一个小节（"### 读取 Flash"）之前。

- [ ] **Step 2: 验证交叉引用存在**

```bash
grep -n "边界与分块约束\|references/flush-memory.md" "C:/Users/Tony/.claude/skills/mklink-flash/references/commands-memory.md"
```

期望：至少 1 行匹配 `references/flush-memory.md` 链接。

- [ ] **Step 3: Commit Task 4**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
git add references/commands-memory.md
git -c user.email="claude@anthropic.com" -c user.name="Claude" commit -m "docs(commands-memory): flush-memory 章节末尾追加边界交叉引用"
```

---

## Task 5: 全量验证

**Files:** 无（仅验证）

- [ ] **Step 1: 验证三个目标文件改动齐全**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
test -f references/flush-memory.md && echo "[OK] references/flush-memory.md 存在"
grep -q "flush-memory 边界" SKILL.md && echo "[OK] SKILL.md 路由行已添加"
grep -q "12KB" SKILL.md && echo "[OK] SKILL.md 命令表已加 12KB 提示"
grep -q "references/flush-memory.md" references/commands-memory.md && echo "[OK] commands-memory.md 交叉引用已添加"
```

期望：4 行 `[OK]` 输出。

- [ ] **Step 2: 验证行数与代码块配对**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
wc -l references/flush-memory.md
```

期望：100~200 行。

- [ ] **Step 3: 运行既有 memory 测试,确认未引入回归**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
pytest _maintainer/testing/tests/test_cli_public_memory.py -q 2>&1 | tail -20
```

期望：测试全部通过或跳过（纯文档改动不应改变测试结果）。如果有失败则检查是否有引用此文档的断言,理论上不应有。

- [ ] **Step 4: 检查 git log 看到 4 个新 commit**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
git log --oneline -5
```

期望输出（commit hash 可变）：

```
<hash> docs(commands-memory): flush-memory 章节末尾追加边界交叉引用
<hash> docs(SKILL): 命令速查表 flush-memory 行加边界提示
<hash> docs(SKILL): 模块路由表新增 flush-memory 边界路由
<hash> docs: 新建 references/flush-memory.md 边界说明
<hash> docs: 设计 flush-memory 边界约束沉淀方案
```

- [ ] **Step 5: 全量 git diff 检查（可选）**

```bash
cd "C:/Users/Tony/.claude/skills/mklink-flash"
git diff HEAD~5 HEAD --stat
```

期望：3 个文件改动,1 个新文件:

```
 SKILL.md                       |   3 +-
 references/commands-memory.md |   6 +
 references/flush-memory.md     | 178 +++++++++++++++++++++
 3 files changed, 184 insertions(+), 3 deletions(-)
```

（doc-manager 不应再有 `??` 的未跟踪文档文件——但前次 `diesel-heater/` 与 `MK-Firmware/` 是项目既有未跟踪目录,与本次工作无关,忽略）

---

## Self-Review Checklist（写完 plan 后的自查）

- [x] Spec coverage: 3 个文件改动都有专门 task 覆盖
- [x] No placeholders: 无 TBD/TODO/「待实现」
- [x] Type/name consistency: 文件名/章节编号/SKILL.md 行号与 spec 一致
- [x] Each step has concrete content: 包含完整文件内容、确切命令、期望输出
- [x] Frequent commits: 5 个 commit（spec 1 个 + 4 个文档改动 + 1 个总验证 = 总 5 个新 commit）
- [x] DRY/YAGNI: 引用 spec 已 commit 的内容,不重复
