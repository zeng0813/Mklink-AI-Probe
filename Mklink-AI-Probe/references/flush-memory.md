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
