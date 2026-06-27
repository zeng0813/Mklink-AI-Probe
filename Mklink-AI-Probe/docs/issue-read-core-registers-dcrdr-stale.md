# Issue: 目标核心在 debug-halt 期间被探针周期性扰动，导致核心寄存器读取返回陈旧值

> **给 MicroLink 固件团队的报告**。本文记录的是**探针侧**问题：目标 MCU 被 debug-halt 后，探针会周期性（约每 1~10s，不定时）扰动核心的 halt 状态，使核心恢复运行；此后所有经 DCRSR/DCRDR 的核心寄存器访问都被核心合法忽略，返回陈旧/哨兵值。host 侧已无可改之处（见 §6）。

---

## 🔔 复测更新（2026-06-26）：固件更新后仍未修复 + 发现独立的 selector 哨兵 bug

对**更新后的固件**复测（STM32F405 / GEC6100D，COM5），得到两条结论：

### A. 原问题（周期性 halt 扰动）**原样存在，未修复**
`regread_resetcause.py`（§3）4/4 复现：halt 后 1.0 / 9.6 / 9.9 / 9.6s，`DHCSR` 由 `0x00030003` → `0x03010001`（`C_HALT` 1→0、`S_RESET_ST` 置位），而 `RCC_CSR = 0x00000000`（无真实复位标志）。与本文 §TL;DR / §3 完全一致。

### B. 新发现：DCRSR REGSEL 5–11（r5–r11）**读路径独立返回 `0xDEADBEEF`**，与 halt 扰动无关
`regread_selector_probe.py`（8/8 轮）、`regread_boundary.py`（3/3 轮），均在**核心确认持续 halted**（`DHCSR` 全程 `0x00030003`、`S_HALT` 始终 1、`S_RESET_ST` 始终 0）下测得：

| DCRSR REGSEL | 寄存器 | 读取结果（halt-kept） |
|---|---|---|
| 0–4 | r0–r4 | 正常（真实值） |
| **5–11** | **r5–r11** | **恒 `0xDEADBEEF`（哨兵）** |
| 12–18, 20 | r12/sp/lr/pc/xpsr/msp/psp/CFBP | 正常（真实值） |

对照证据（`regread_selector_probe.py`，halt-kept 8/8）：
- DCRDR 直写直读 100% 精确（`0xAABBCCDD`/`0x55AA55AA`）→ AP 读/写通路本身完好；
- `sel1` 正常返回真实 `r1`；
- `sel6`/`sel11` 恒返回 `0xDEADBEEF`。

**写路径完全正常**：`regread_boundary.py` Phase 2（REGWnR=1）halt-kept 4/4，对 `sel1/6/11` 写 `0xCAFE000｜sel` 后读回全部精确命中。即 **bug 只影响读（REGWnR=0），不影响写（REGWnR=1）**。

### ⚠️ 对原文归因的修正
本文 §TL;DR 与附录 A.2 / A.5 把所有 `0xDEADBEEF` 一律归因为"核心恢复运行后 DCRDR 残留"。**该归因对 sel 5–11 不成立**：核心全程 halted、DCRDR 通路完好的前提下，sel 5–11 仍稳定返回哨兵。原文之所以漏掉，是因为当时所有复现都"读全量 23 个寄存器"，必然跨越扰动窗口，无法把"sel 5–11 读哨兵"与"halt-loss 后 DCRDR 冻结"两种现象隔离。复测改用"halt-kept 下逐 selector 单读"才分离出这条独立路径。

> 即：本文记录的 **halt 扰动（问题 A）真实存在且未修复**；同时固件还存在一个**独立的、读路径专属的 sel 5–11 哨兵 bug（问题 B）**。两者都会让 `read_all_core_registers` 不可靠，但根因不同、需分别修复。

### 附：性能回归
更新后固件单次 PPB `read_ram` ≈ **46 ms**（正常应数 ms 级），导致 `read_all_core_registers`（20 次 DCRSR 传输）耗时 ≈ 3.1 s，几乎必然跨越 1~10s 的扰动窗口。

### 复测脚本（`_maintainer/testing/scratch/`）
- `regread_resetcause.py` — 问题 A 复现（即 §3）
- `regread_selector_probe.py` — 问题 B 铁证（halt-kept 下 sel1 正常、sel6/11 哨兵、DCRDR 直写直读精确）
- `regread_boundary.py` — 问题 B 边界穷举（sel 5–11）+ 写路径（REGWnR=1）正常
- `regread_diag2.py` — 问题 B 可重复性
- `regread_regression_recheck.py` — 全量 23 寄存器 ×10（当前固件 0/10 通过）

---

## TL;DR（根因）

当目标核心处于 debug-halt（`DHCSR.C_DEBUGEN=1, C_HALT=1, S_HALT=1`）时，**MicroLink 探针会周期性地把核心从 halt 状态里踢出来**：

- `DHCSR` 由 `0x00030003`（halted）变为 `0x03010001`：`C_HALT` 1→0、`S_HALT` 1→0、`S_RETIRE_ST`(bit24)=1（核心跑了指令）、`S_RESET_ST`(bit25)=1。
- 但 STM32 复位原因寄存器 `RCC_CSR (0x40023810)` = **`0x00000000`** —— 没有任何复位标志（无 IWDG/WWDG/SFTRST/PIN/POR/BOR）。
- 即：**没有发生真实的系统复位**，但 `S_RESET_ST` 被置位、`C_HALT` 被清掉。这是典型的"探针重新初始化 SWD/DAP 调试连接（或循环调试电源域）"的特征——该操作清掉了核心的 halt 态并置位 `S_RESET_ST`，却并未真正复位目标。

一旦核心恢复运行，`DCSR` 寄存器传输写被核心**合法忽略**（ARMv7-M 规定 DCRSR 仅在 halt 时生效）→ `DCRDR` 冻结在上一个值 → 后续核心寄存器全部返回陈旧常量或 `0xDEADBEEF` 哨兵。

**这是时间相关、与 host 操作/流量/看门狗/真实复位均无关的探针侧行为。** 完整排除链见 §5。

---

## 1. 环境

| 项 | 值 |
|---|---|
| 探针 | MicroLink **V4** |
| 探针固件 | **V4.3.2**（V4.3.1 同样复现，升级无效）|
| 目标 MCU | STM32F405ZGTx（GEC6100D 板，Cortex-M4F，DPIDR `0x2BA01477`）|
| host 工具 | mklink-flash（`mklink.debug_control`，经 PikaScript `cmd.read_ram` / `cmd.write_ram`）|
| 连接 | SWD，线路良好（读 FLASH/SRAM/DHCSR 全稳定）|

## 2. 现象（用户视角）

`read_all_core_registers`（循环读 R0–R15/xPSR/MSP/PSP/CFBP 共 23 个）返回值不可靠：

- 前 2~6 个读到**新鲜正确值**；
- 之后**全部返回同一个陈旧常量**（每次运行不同：`0xDEADBEEF` / `0x00000038` / `0xFFFFFFFF` / 上一个寄存器的值等）；
- 该陈旧值正是 DCRDR 上一次成功读取后残留的内容。

**单/少量寄存器（单次 halt ≤5 个、亚秒级）读取完全正常**：仅读 PC → `0x08077726`（合法 flash 地址），连续单读 R0/R1/R2 也正确。

## 3. 最小复现（探针侧 bug 的直接观测）

> 关键点：**零流量**下复现。halt 后什么都不做，只定时读 `DHCSR`；一旦 `S_HALT` 掉或 `S_RESET_ST` 置位，立即读 `RCC_CSR`——它会显示**没有真实复位**。

```python
import time
from mklink.bridge import MKLinkSerialBridge
from mklink.debug_control import halt_cpu, resume_cpu, _read_u32, _write_u32

DHCSR, RCC_CSR = 0xE000EDF0, 0x40023810
S_HALT, S_RESET_ST = 1 << 17, 1 << 25

b = MKLinkSerialBridge('COM5'); b.connect()
resume_cpu(b); halt_cpu(b)
_write_u32(b, RCC_CSR, 1 << 23)          # RMVF: 清掉历史复位标志

for _ in range(60):                       # 轮询最多 ~18s
    time.sleep(0.3)
    d = _read_u32(b, DHCSR)
    if (d & S_RESET_ST) or not (d & S_HALT):
        print(f"halt lost after some idle: DHCSR={d:#010x}")
        print(f"RCC_CSR={_read_u32(b, RCC_CSR):#010x}  (期望 0x0 = 无真实复位)")
        break
else:
    print("18s 内未触发（间歇性，多重试几次）")
resume_cpu(b); b.close()
```

**期望输出**（间歇出现，约 1~10s 后）：
```
halt lost after some idle: DHCSR=0x03010001
RCC_CSR=0x00000000  (期望 0x0 = 无真实复位)
```

`DHCSR=0x03010001` 解码：`C_DEBUGEN`(bit0)=1, `S_REGRDY`(bit16)=1, `S_RETIRE_ST`(bit24)=1, `S_RESET_ST`(bit25)=1, **`C_HALT`(bit1)=0**, **`S_HALT`(bit17)=0**。

## 4. 直接判别证据（证明是"核心丢了 halt"而非"DCSR/DCRDR 机制坏"）

在"已坏"状态（`S_HALT=0`）下做的两个对照：

| 对照 | 操作 | 结果 | 含义 |
|---|---|---|---|
| C1 | `write_ram(DCRDR,0xAABBCCDD)`→读；`write_ram(DCRDR,0x55AA55AA)`→读 | 分别精确读回 `0xAABBCCDD` / `0x55AA55AA` | **固件 AP 读/写通路本身完好** |
| C2 | 写 DCRDR 标记 `0x11223344`，再写 `DCSR(pc)` → 读 DCRDR | 仍 `0x11223344`（未刷新） | 核心在运行，**合法忽略 DCSR** |

即：DCRDR 读写没问题；DCSR 写没丢——只是**核心不在 halt 态**，所以 ARM 架构规定 DCSR 不生效。

## 5. 排除项（已逐一验证，请勿重复追逐）

| 假设 | 验证 | 结论 |
|---|---|---|
| SWD 线路/接触 | 读 FLASH/SRAM/DHCSR 全稳定；DPIDR 正常 | ❌ 线路良好 |
| host halt 序列违例 | `halt_cpu` 写 `0xA05F0003`(KEY\|C_DEBUGEN\|C_HALT)，符合 ARMv7-M | ❌ host 合规 |
| host 缺 S_REGRDY 握手 | 已补握手；少量读取 8/8 通过 | ❌ 是真实 host 缺陷但**已修**，非本 bug 根因 |
| host `"control"` 误读 CFBP | 已修；与 halt-loss 无关 | ❌ 已修，无关 |
| host `read_ram` 解析错位 / `send_command` 帧错位 | 裸 pyserial 抓包 + 单寄存器连读一致 | ❌ host 解析正常 |
| AP 读/写通路坏 | C1：坏状态下 DCRDR 直写直读精确 | ❌ 通路完好 |
| 特定操作触发（"读 DCRDR 特殊"）| 7 类操作各 10×20 次：read DCRDR **0/10** drop；read/write DHCSR/DCSR/DCRDR/SRAM 均 ~0/10 | ❌ **DCRDR 不特殊**（早先单次试验是噪声）|
| **与流量相关** | idle 测试：halt 后**零流量**只 sleep，2s/8s 仍 drop（8s≈5/6） | ❌ **与流量无关，纯时间相关** |
| **片内看门狗 IWDG/WWDG** | `DBGMCU_CR` `0x07`→`0x307` 冻结 IWDG+WWDG（回读确认），drop 率不变 | ❌ **冻结无效** |
| **片外看门狗 / NRST 复位** | `RCC_CSR` 无 `PINRSTF` 等任何标志 | ❌ 无 NRST 复位 |
| **任何真实系统复位** | `RCC_CSR = 0x00000000`（无 IWDG/WWDG/SFTRST/PIN/POR/BOR） | ❌ **没有真实复位** |

**唯一剩下且与全部证据自洽的解释**：探针周期性重新初始化 SWD/DAP 调试连接（或循环调试电源域 CDBGPWRUPREQ / 触发 line reset），该操作清掉目标核心的 `C_HALT` 并置位 `DHCSR.S_RESET_ST`，但并未真正复位目标（故 `RCC_CSR` 干净）。

## 6. host 侧（已无可改；仅供固件作者确认 host 正确）

- `mklink/debug_control.py` 已补 `DHCSR.S_REGRDY` 握手（写 DCRSR → 轮询 REGRDY → 读 DCRDR，ARMv7-M 标准 3 步）。
- 已修正 `"control"` 误读：CFBP 选择子 0x14 打包返回 CONTROL/FAULTMASK/BASEPRI/PRIMASK，现按字节解包（`control=2` 实测正确）。
- host **从不写 `C_HALT=0`**（resume 才写）；DHCSR 写需 `0xA05F` key，host 不可能误清 halt。
- 规避：单次 halt ≤5 个寄存器、亚秒级完成 → 在探针扰动前读完，可靠。全量 23 个会跨过扰动窗口，不可靠。

## 7. 给 MicroLink 固件团队的建议排查方向

1. **周期性 SWD/DAP 维护逻辑**：是否存在定时器或"每 N 笔 AP 事务"触发的 line reset / DP 重新初始化 / 调试电源域（`CDBGPWRUPREQ`）循环？目标 halt 期间应当**完全静默**地保持 SWD 连接，不应周期性重建。
2. **AP stall 恢复路径**：访问 PPB/调试寄存器（`0xE000EDF0`–`F8`）若触发 stall 恢复，是否会顺带扰动核心 halt（写 DHCSR / 循环调试域）？stall 恢复应只用 `C_SNAPSTALL`(DHCSR bit4)，不应清 `C_HALT`。
3. **对照参考实现**：J-Link / OpenOCD / DAPLink 在目标 halt 期间维持**稳定、静默**的 SWD 连接，不会按定时器重建链路。
4. **回归判据**：修复后，目标 halt 后 idle ≥30s，`DHCSR.S_HALT` 应始终为 1、`S_RESET_ST` 不再无故置位；`read_all_core_registers` 23 个全量读取连续 10 次全部返回各自正确值（PC 在 `0x08000000`~`0x080FFFFF`、SP 在 RAM、`control` 为小字节）。

## 8. 关键寄存器速查

| 寄存器 | 地址 | 相关位 |
|---|---|---|
| DHCSR | `0xE000EDF0` | bit0 C_DEBUGEN, bit1 C_HALT, bit4 C_SNAPSTALL, bit16 S_REGRDY, bit17 S_HALT, bit24 S_RETIRE_ST, bit25 S_RESET_ST（写需 `0xA05F` key）|
| DCRSR | `0xE000EDF4` | REGSEL[4:0] + bit16 REGWnR（仅 halt 时生效）|
| DCRDR | `0xE000EDF8` | 数据；CFBP 选择子 0x14 打包 CONTROL/FAULTMASK/BASEPRI/PRIMASK |
| STM32 RCC_CSR | `0x40023810` | bit23 RMVF(清标志), bit25 BORRSTF, bit26 PINRSTF, bit27 PORRSTF, bit28 SFTRSTF, bit29 IWDGRSTF, bit30 WWDGRSTF |

## 9. 参考

- ARMv7-M ARM（DDI 0403）DHCSR / DCRSR / DCRDR 定义、halt/exit-halt 机制。
- pyOCD `coresight/cortex_m_core_registers.py`（CFBP 打包编码交叉核对）。
- STM32F405 参考手册 RM0090（RCC_CSR 复位标志、DBGMCU 冻结位）。
- 复测脚本：`_maintainer/testing/scratch/regread_*.py`（`resetcause` 复现本 bug；`idle_freeze` 看门狗排除；`opstats` 证明 DCRDR 不特殊；`discrim2` C1/C2 判别）。
- **2026-06-26 复测新增**：`regread_selector_probe.py` / `regread_boundary.py` / `regread_diag2.py` / `regread_regression_recheck.py` —— 见本文顶部"🔔 复测更新"，证明 sel 5–11 读哨兵是与 halt 扰动无关的独立 bug。

---

## 附录 A：完整证据链（按演进顺序，含已推翻的过程结论）

为便于固件作者复核，保留排查过程；**以 §TL;DR 与 §3–§5 为准**，下方过程结论中凡标 ⚠️ 的均已被后续实验推翻。

- **A.1 host 缺 S_REGRDY 握手**（真实缺陷，**已修**）：原 `read_core_register` 只"写 DCRSR → 读 DCRDR"两步，缺"轮询 S_REGRDY"。补上后少量寄存器读取 8/8 通过。非 halt-loss 根因。
- **A.2 ⚠️ "DCSR 写触发固件 AP 错误 / `0xDEADBEEF` 哨兵"**（**已推翻**）：早先据 G1–G4（读静态地址稳定、DCSR+DCRDR 序列出哨兵）推断 DCSR 写触发 AP 错误。后被 C1（AP 通路完好）推翻；`0xDEADBEEF` 实为核心恢复运行后 DCRDR 残留/哨兵的表象。
- **A.3 ⚠️ "读 DCRDR 特殊"**（**已推翻**）：单次试验 T1 显示读 DCRDR ×20 后丢 halt。统计复测（7 类操作各 10×20 次）证明 read DCRDR drop 率 **0/10**，DCRDR 不特殊，T1 是间歇性噪声。
- **A.4 ⚠️ "看门狗复位"**（**已推翻**）：曾据 `S_RESET_ST` 猜 IWDG/外部看门狗。冻结 `DBGMCU` IWDG+WWDG 无效；`RCC_CSR` 干净排除片内/片外看门狗及一切真实复位。
- **A.5 ✅ 最终**：时间相关、零流量可复现、`RCC_CSR` 干净 → 探针周期性重建调试连接扰动核心 halt（见 §TL;DR）。
- **A.6 ⚠️ 补充（2026-06-26 复测）**：A.5 的结论对"halt 扰动（问题 A）"成立，但**不覆盖 sel 5–11 的 `0xDEADBEEF`**。halt-kept 下逐 selector 单读证明 sel 5–11 的哨兵来自固件读路径本身（REGWnR=0），与 halt 状态无关；写路径（REGWnR=1）正常。这是独立的问题 B，详见顶部"🔔 复测更新"。
