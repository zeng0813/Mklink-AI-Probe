# MKLINK dump_memory / flush_memory 边界复测报告

> 存档来源：用户 2026-06-26 提交的 WeChat 文件，原文回填入仓以便代码注释引用。
> 相关代码：`mklink/dump_memory.py`（`MAX_TOTAL_DATA_SIZE`）、`mklink/cli.py`（`_parse_flush_item` / `_cli_flush_memory`）。
> 相关文档：[references/flush-memory.md](../../references/flush-memory.md)、[references/commands-memory.md](../../references/commands-memory.md)。

测试日期：2026-06-26
测试工程：`E:\PHDZ\PROJECT\62 QGD\GD32F303_BOOT\MDK-ARM\GD32303C_EVAL.uvprojx`
测试目标：GD32F303CE
MKLINK 端口：`COM96`
下载器固件：`V4.3.3`

## 1. 测试结论

1. `dump_memory` 固件侧边界已经扩大，临时放宽 PC 端 CLI 的 32 KiB 安全阈值后，整片 512 KiB Flash dump 通过，返回 256 个 B1 分块，全部 `flags=0x0000`。
2. 当前正式 CLI 仍保留 32 KiB 主机侧限制：`32768B` 通过，`32769B` 在 PC 端直接拦截，未发送到下载器。
3. `flush_memory` 单地址重复字节写入复测到 `16300B` 通过，并用 `dump-memory` 抽查头部/中部/尾部确认写入一致。
4. `flush_memory` 单地址 `16384B` 未发送到设备，被 Windows 命令行长度限制拦截，报错：`The filename or extension is too long`。
5. `flush_memory` 多地址写入在当前正式 CLI 下，`6` 项通过，`7` 项开始被 CLI 的 `MAX_FLUSH_CMD_LEN=230` 拦截。临时放宽该主机阈值后，`8` 项通过，`12` 项发到设备后 10s 超时且会扰动会话，不能作为可用边界。

## 2. 测试前状态

`project-info` / AXF 信息确认：

| 项目 | 结果 |
|---|---|
| MCU | GD32F303CE |
| Flash | `0x08000000`, 512 KiB |
| RAM | `0x20000000`, 64 KiB |
| AXF Flash 使用 | 19204 B / 524288 B |
| AXF RAM 使用 | 7664 B / 65536 B |
| `__heap_base` | `0x200015f0` |
| `__heap_limit` | `0x200019f0` |
| `__initial_sp` | `0x20001df0` |

`flush_memory` 写入测试前执行：

```powershell
python -m mklink halt --port COM96
```

结果：

```text
[OK] CPU 已停止 (DHCSR=0x01030003 / 0x03030003)
```

写入测试地址选择：

| 用途 | 地址 |
|---|---|
| 单地址大块写入 | `0x20008000` |
| 多地址离散写入 | `0x2000C000` 起，每项间隔 `0x10` |

这些地址位于高位 RAM，避开本工程 AXF 中的 data/heap/stack 区域。

## 3. dump_memory 边界复测

### 3.1 正式 CLI 默认限制

| 测试项 | 命令要点 | 结果 |
|---|---|---|
| 2048B | `dump-memory 0x08000000:2048` | PASS，OLD 帧，`flags=0x0000` |
| 2049B | `dump-memory 0x08000000:2049` | PASS，B1 两块：2048B + 1B，`flags=0x0000` |
| 32768B | `dump-memory 0x08000000:32768` | PASS，16 个 B1 块，`flags=0x0000` |
| 32769B | `dump-memory 0x08000000:32769` | FAIL，PC 端 CLI 拦截：超过 32768B |
| 多 region 合计 32768B | `16384B + 16384B` | PASS，16 个 B1 块，`flags=0x0000` |
| 多 region 合计 32769B | `16384B + 16385B` | FAIL，PC 端 CLI 拦截 |

32769B 的原始失败信息：

```text
[FAIL] invalid dump-memory request: Total region size 32769 exceeds maximum 32768 bytes (32 KiB). Split the request into <=32 KiB chunks at the host level.
```

### 3.2 临时放宽主机阈值后的固件能力验证

为验证下载器固件真实能力，测试过程中临时将 PC 端 `dump_memory.py` 的 `MAX_TOTAL_DATA_SIZE` 从 `32 KiB` 放宽到 `512 KiB`。测试完成后已恢复原值。

| 测试项 | 地址 | 结果 |
|---|---|---|
| Flash 64 KiB | `0x08000000:65536` | PASS，32 个 B1 块，`flags=0x0000` |
| Flash 128 KiB | `0x08000000:131072` | PASS，64 个 B1 块，`flags=0x0000` |
| Flash 256 KiB | `0x08000000:262144` | PASS，128 个 B1 块，`flags=0x0000` |
| Flash 512 KiB | `0x08000000:524288` | PASS，256 个 B1 块，`flags=0x0000` |
| RAM 64 KiB | `0x20000000:65536` | PASS，32 个 B1 块，`flags=0x0000` |

结论：本次固件 `V4.3.3` 的 `dump_memory` 至少可以稳定完成目标芯片整片 Flash 512 KiB 读取；当前用户可见边界仍受 PC 端 CLI 默认 32 KiB 限制影响。

## 4. flush_memory 边界复测

### 4.1 参数注意事项

PowerShell 中不要直接写未加引号的 `0xAA,0xAA,...`。实测会被 PowerShell 预处理，导致后续参数被改写，例如实际发送为 `0x170`，目标低 8 位写成 `0x70`。

推荐使用单个字符串参数：

```powershell
$item = '0x20008000:' + ((1..$n | ForEach-Object { 'A' }) -join ' ')
python -m mklink flush-memory $item --port COM96
```

### 4.2 单地址连续写入

测试方式：写入重复单字节，再用 `dump-memory` 抽查头部、中部、尾部各 16B。

| 写入长度 | 结果 | 验证 |
|---:|---|---|
| 16B | PASS | `--verify` 回读全为 `0a` |
| 2048B | PASS | 头/中/尾全为 `0b` |
| 4096B | PASS | 头/中/尾全为 `0c` |
| 8192B | PASS | 头/中/尾全为 `0d` |
| 10240B | PASS | 头/中/尾全为 `0e` |
| 11264B | PASS | 头/中/尾全为 `0f` |
| 12288B | PASS | 头/中/尾全为 `0a` |
| 14336B | PASS | 头/中/尾全为 `0b` |
| 15360B | PASS | 头/中/尾全为 `0c` |
| 16000B | PASS | 头/中/尾全为 `0d` |
| 16300B | PASS | 头/中/尾全为 `0e` |
| 16384B | 未发送到设备 | Windows 命令行长度限制，`arg_length=32778` |

16384B 的失败信息：

```text
Program 'python.exe' failed to run: The filename or extension is too long
```

结论：通过当前 CLI 输入格式，单地址重复写入已验证到 `16300B`。这已经超过旧记录中的 `15KB` 失败边界；但 `16KB` 及以上需要 CLI 增加 pattern/count 参数，绕开 Windows 命令行长度限制后才能继续验证固件上限。

### 4.3 多地址离散写入

正式 CLI 默认阈值下：

| 地址项数量 | 每项数据 | 结果 |
|---:|---:|---|
| 4 | 1B | PASS，全部回读正确 |
| 6 | 1B | PASS，全部回读正确 |
| 7 | 1B | FAIL，PC 端 CLI 拦截：命令串 235B > 230B |
| 8 | 1B | FAIL，PC 端 CLI 拦截：命令串 266B > 230B |
| 12 | 1B | FAIL，PC 端 CLI 拦截：命令串 390B > 230B |

临时将 PC 端 `MAX_FLUSH_CMD_LEN` 从 `230` 放宽到 `600` 后：

| 地址项数量 | 每项数据 | 结果 |
|---:|---:|---|
| 8 | 1B | PASS，全部回读正确 |
| 12 | 1B | FAIL，发到设备后 10s 超时；后续一次版本查询空响应，会话受扰动 |

12 项超时后，执行资源清理并重新连接，`version` 与 `test` 均恢复正常。

结论：固件侧多地址写入稳定边界本次确认到 `8` 项；`12` 项仍不稳定。当前正式 CLI 因 230B 主机安全阈值，用户实际可直接使用的多地址项数为 `<=6` 项。

## 5. 恢复与收尾

测试后已恢复临时修改：

| 文件 | 恢复项 |
|---|---|
| `dump_memory.py` | `MAX_TOTAL_DATA_SIZE = 32 * 1024` |
| `cli.py` | `MAX_FLUSH_CMD_LEN = 230` |

测试后执行：

```powershell
python -m mklink resume --port COM96
python -m mklink version --port COM96
python -m mklink test --port COM96
```

结果：

```text
[OK] CPU 已恢复运行 (DHCSR=0x01010001)
[OK] 烧录器固件版本: V4.3.3
[OK] 连接成功
idcode = 0X2BA01477
```

## 6. 建议

1. `dump_memory`：固件侧已支持至少 512 KiB，建议同步放宽 PC 端 CLI 的 32 KiB 默认限制，或增加显式 `--max-size/--unsafe-large` 参数，避免用户误判为固件未修复。
2. `flush_memory` 单地址大块：建议 CLI 增加 `ADDR:BYTE*N` 或 `--fill BYTE --size N` 语法，避免 Windows 命令行长度限制。当前输入格式下，实测只能验证到约 16KB 前。
3. `flush_memory` 多地址：建议保持推荐 `<=8` 项；12 项仍会超时并扰动会话，不建议对用户开放为稳定能力。
4. 对外说明时建议区分三类边界：固件协议边界、PC 端 CLI 安全阈值、Windows 命令行长度限制。

---

## 落地说明（2026-06-26 入仓时补充）

本报告的第 6 章建议已在本仓落实：

| 建议 | 落地 |
|---|---|
| 6.1 放宽 dump 主机限制 | `dump_memory.py:MAX_TOTAL_DATA_SIZE` 默认由 32 KiB 提至 **512 KiB**；`set_max_total_data_size` 硬上限同步至 512 KiB（仅可下调）。 |
| 6.2 flush 紧凑语法 | `cli.py:_parse_flush_item` 新增 **`ADDR:BYTE*N`** 单字节重复语法（如 `0x20008000:0xAA*16300`），复用 `bytes([0xVV])*N` 短表达式绕开 Windows cmdline。**二分复测**（2026-06-26）：`*N` 只解决输入长度，不抬高固件单次上限——单地址单次写入 **16512B 通过 / 16640B 超时**（精确边界 16513–16639B，≈16.1 KiB），超限触发 10s 超时 + CDC 端口短暂消失。 |
| 6.3 多地址 ≤8 项 | 文档（flush-memory.md §3.2）明确 ≤8 项稳定、12 项禁用；CLI 仍按 230B/批保守分块。 |
| 6.4 三类边界区分 | flush-memory.md §3 重写为「固件协议 / PC CLI 安全阈值 / Windows cmdline」三类边界表；修正旧「15KB CDC 异常」误判（实为 Windows cmdline 限制）。 |
