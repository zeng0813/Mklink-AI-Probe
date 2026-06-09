# flush-memory 边界约束沉淀设计

**日期**: 2026-06-09
**作者**: Claude (brainstorming → design)
**状态**: 草案（待用户复核）
**范围**: 纯文档沉淀（0 代码改动）

## 1. 背景与目标

`cmd.flush_memory` 是 MKLink 固件 PikaPython REPL API，2026-06 完成了实测边界评估
（详见 `d:\Wechat\xwechat_files\su5176_51c5\msg\file\2026-06\flush_memory_usage_boundary.md`），
得到 6 类稳定边界：

- 老 varargs 形式 ≤ 20 bytes
- 单地址 bytes/list ≤ 12KB（推荐）/ 14KB（极限）/ 15KB（失败）
- 多地址 list ≤ 8 地址项（12 项失败）
- 多地址总数据量 ≤ 12KB
- 重复字节与 16 字节 pattern 循环 ≤ 12KB
- 边界与固件版本、`PIKA_LINE_BUFF_SIZE`、目标 RAM 布局有关

这些边界**尚未沉淀到 skill**，当前 `commands-memory.md` 的 flush-memory 章节
仅写「1~16 字节稳定 PASS」，远低于实测 20 字节上限，且完全缺失分块策略与
校验建议。

**目标**：把 6 类边界、分块策略、校验建议固化到 skill 文档，使后续 Agent
或人类工程师在调用 `flush-memory` 时可直接查阅，避免越界触发 CDC 异常。

## 2. 非目标

- **不**修改 `cli.py:_cli_flush_memory`（不改 Python 代码）
- **不**新增自动分块/重试逻辑
- **不**新增 `flush-memory` 相关单元测试
- **不**修改 `CLAUDE.md`（CLAUDE.md 是构建/运行命令指南，不写 API 边界）

## 3. 文件改动清单

| 文件 | 改动类型 | 内容 |
|------|----------|------|
| `references/flush-memory.md` | **新建** | 完整的边界说明文档，权威来源 |
| `SKILL.md` | 修改 2 处 | (1) 模块路由表新增一行；(2) 命令速查表 flush-memory 行加约束提示 |
| `references/commands-memory.md` | 修改 1 处 | 现有 flush-memory 章节末尾追加交叉引用小节 |

## 4. `references/flush-memory.md` 内容大纲

| 章节 | 标题 | 行数估算 | 内容来源 |
|------|------|----------|----------|
| 1 | 接口定位 | ~6 | 边界文档 §1 完整保留 |
| 2 | 基本用法（5 种调用形式） | ~50 | 边界文档 §2.1~2.5 完整保留 |
| 3 | 实测使用边界（7 行表格） | ~15 | 边界文档 §3 表格完整保留 |
| 4 | 推荐实际使用边界 | ~15 | 边界文档 §4 推荐+极限分两档 |
| 5 | 超额分块策略 | ~12 | 边界文档 §4 后半段（大块/离散多地址） |
| 6 | 校验建议 | ~10 | 边界文档 §5 |
| 7 | 注意事项 | ~15 | 边界文档 §6 全部 8 条 |
| 8 | 与 CLI `flush-memory` 的关系 | ~12 | **新增**：CLI 是这个 REPL API 的封装者，**CLI 当前不自动分块**，超额时按 1 次命令提交 |

**关键设计点**：
- 第 8 章明确声明「CLI 当前不做自动分块」，避免读者误以为 CLI 会智能拆分
- 第 4 章用「推荐 / 极限 / 失败」三档表呈现（与现有 `commands-memory.md` 表格风格一致）
- 第 5 章给出 host 端分块伪代码示例，**仅作参考**，不暗示 CLI 已实现

## 5. `SKILL.md` 改动细节

### 改动 5.1：模块路由表新增一行

位置：第 61-69 行的「模块路由（渐进式披露）」表格。

新增行（紧接 `rtt-static-mode.md` 之后）：

```markdown
| flush-memory 边界、12KB 分块策略、推荐用法 | [references/flush-memory.md](references/flush-memory.md) |
```

### 改动 5.2：命令速查表更新

位置：第 36 行 `flush-memory` 行的「说明」列。

当前：
```markdown
| `flush-memory` | 静默写 RAM，**多地址多字节**（成功无 ACK；适合与 `dump_memory` 并发场景） |
```

改为：
```markdown
| `flush-memory` | 静默写 RAM，**多地址多字节**（成功无 ACK；适合与 `dump_memory` 并发场景）。<br>**边界**: 单项 ≤ 12KB, 多地址 ≤ 8 项, varargs ≤ 20 字节, 详见 [references/flush-memory.md](references/flush-memory.md) |
```

## 6. `references/commands-memory.md` 改动细节

### 改动 6.1：flush-memory 章节末尾追加交叉引用

位置：第 164 行「验证技巧」小节之后，整个 flush-memory 章节结束前。

新增小节：

```markdown
##### 📌 边界与分块约束

`flush-memory` 的 CLI 实现**不自动分块**,超额时按 1 次命令提交。
完整边界(单项数据量 ≤ 12KB,多地址 ≤ 8 项,varargs ≤ 20 字节,失败边界 15KB/12 项)
与 host 端分块策略见 **[references/flush-memory.md](references/flush-memory.md)**。
```

**位置选择理由**：放在「验证技巧」之后是因为：验证建议与边界/分块是连续话题，
且不会打断阅读「示例 → 响应解析 → 验证技巧 → 边界交叉引用」的自然流。

## 7. 实施步骤

按以下顺序执行（每步独立提交，方便回滚）：

1. 新建 `references/flush-memory.md`（内容按第 4 章大纲）
2. 修改 `SKILL.md` 模块路由表（第 5.1 节）
3. 修改 `SKILL.md` 命令速查表（第 5.2 节）
4. 修改 `references/commands-memory.md` flush-memory 章节末尾（第 6.1 节）
5. 全仓 git diff 检查
6. 运行 `pytest _maintainer/testing/tests/test_cli_public_memory.py` 确认未破坏既有测试
7. git add + commit（commit message: `docs: 沉淀 flush-memory 边界与分块策略约束`）

## 8. 验证标准

- `references/flush-memory.md` 文件存在，行数 100~200
- `SKILL.md` 模块路由表包含新行，命令速查表 flush-memory 行包含「12KB」字样
- `commands-memory.md` 第 165 行附近出现「references/flush-memory.md」链接
- 既有 `pytest` 测试 100% 通过
- git log 显示 1 个新 commit

## 9. 风险与回滚

- **风险**：纯文档改动无运行时风险
- **回滚**：`git revert <commit>` 一条命令回退所有改动

## 10. 后续可能工作（非本次范围）

- 给 `_cli_flush_memory` 加边界检查（≥12KB 时 WARN，>14KB/12 项时 FAIL）—— 需另起 spec
- 给 `_cli_flush_memory` 加自动分块（按 12KB 拆分）—— 需另起 spec
- 新增 `test_flush_memory_boundary.py` 单测，固化边界表格 —— 需另起 spec
