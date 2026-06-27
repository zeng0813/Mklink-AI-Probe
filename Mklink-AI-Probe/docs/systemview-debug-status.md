# SystemView GUI 调试状态（2026-06-27）

> 设备：GEC6100D STM32F405ZGTx @ COM5 / 固件 rt-thread.hex (含 SEGGER_SYSVIEW，USE_SYSTEMVIEW 宏)
> 分支：test/gui-e2e-hil-regression

## 当前结论

**代码层根因已定位并修复**：后端 `SystemViewStreamManager` 已改成发送 `{"event":"batch","events":[...]}` 降低 SSE 频率，但前端通用 `useEventSource()` 只接收 `data/raw/history/error/stopped`，导致 `SystemViewTab` 永远收不到 `batch` 和 `status`，页面表现为事件 0 / 任务 0 / 空白。

本次修复：
- `gui/src/composables/useEventSource.ts` 增加 `passthroughEvents` 可选项。
- `gui/src/components/dash/SystemViewTab.vue` 仅对 SystemView 透传 `status` / `batch`。
- `gui/src/composables/__tests__/useEventSource.test.ts` 增加回归测试，确认 SystemView 能接收 `status/batch`，默认 dashboard 不受影响。

已验证：
- `npm test -- useEventSource.test.ts`：2 passed
- `npm test`：28 passed
- `npm run build`：通过

待真机复测：用 COM5 / GEC6100D 手动打开 GUI，再确认 `/api/dash/systemview/status` 和页面事件计数同步增长。

## 第二轮 GUI 显示问题（截图反馈）

现象：
- 线程名显示为 `0x1790` 这类短地址。
- CPU 占用出现 `11104.3%`、`1252.9%` 等明显错误值。
- 任务切换时间轴是大块黑色区域，真实区间几乎不可见，窗口内 CPU 占用为空。

根因与修复：
- dashboard 后端自己创建的 `SystemViewParser` 没有沿用 `Device.systemview_start()` 的 STM32 RAM 默认值，导致 task_id 仍是 shrunken/raw ID；已给 dashboard parser 默认 `ram_base=0x20000000, id_shift=2`。
- 实时流通常抓不到开机 INIT/TaskInfo 包，线程名映射为空；已在首次看到未知 `rt_thread*` ID 时短暂停止探针流，调用现有 `systemview_resolve_task_names()` 读 RT-Thread 线程名，再恢复采集并回填 history/batch。
- 前端 CPU% 用 `runUs / (lastT-firstT)`，在实时缓冲/视窗状态下会产生大于 100% 的值；已抽成 `systemViewMetrics.ts`，按总任务运行时间归一化，和 `systemview_analyzer.py` 保持一致。
- `SvTimeline` 初始空数据把视窗固定到 `0..1`，真实 interval 到来后只 clamp 不 reset，造成时间轴窗口无任务；已在“空 -> 非空”或视窗非法时重置到真实数据范围。
- SystemView 图表和事件流黑底样式已调整为浅色工作区，和 GUI 当前浅色主题一致。

新增验证：
- `npm test -- systemViewMetrics.test.ts svTimeline.test.ts`：3 passed
- `python -m pytest _maintainer/testing/tests/test_systemview_dashboard.py`：2 passed
- `python -m pytest _maintainer/testing/tests/test_systemview_dashboard.py _maintainer/testing/tests/test_systemview_parser.py _maintainer/testing/tests/test_systemview_analyzer.py -q`：19 passed
- `npm test`：31 passed
- `npm run build`：通过

## 第三轮：OOM 风险修复

根因：
- `SystemViewTab.vue` 的前端缓存裁剪写成了 `splice(0, MAX_EVENTS - 3000)` / `splice(0, MAX_INTERVALS - 4000)`；deleteCount 为负数时不会删除元素，导致事件流和 timeline interval 实际无限增长。
- `SystemViewSession.read_bytes()` 原先只按 duration 聚合原始字节，没有单次 `max_bytes` 上限；高吞吐或脚本长时间采样时可能一次性拼接过大的 bytes。

修复：
- 新增 `gui/src/lib/boundedBuffer.ts::trimToLast()`，事件列表固定保留最后 800 条，timeline interval 固定保留最后 1500 条。
- `MKLinkSerialBridge.drain_stream_bytes(max_bytes=...)` 支持按字节上限 drain，并把未取完的尾部留在 buffer 中。
- `SystemViewSession.read_bytes(..., max_bytes=...)` / `Device.systemview_read_bytes(..., max_bytes=...)` 增加单次读取上限。
- Dashboard 实时采集改为 `duration=0.1, max_bytes=64*1024`，避免 GUI polling 周期内积累过大原始流。

新增验证：
- `npm test -- boundedBuffer.test.ts systemViewMetrics.test.ts svTimeline.test.ts useEventSource.test.ts`：7 passed
- `python -m pytest _maintainer/testing/tests/test_systemview_session.py _maintainer/testing/tests/test_systemview_dashboard.py -q`：4 passed
- `npm run build`：通过

## 第四轮：800 条事件后前端不再更新

现象：
- 后端 `/api/dash/systemview/status` 仍持续增长（例如 `events=328443+`），说明 SystemView 采集和解析没有停。
- 前端页面在事件显示到 800 左右后看起来不动。

根因：
- 前端 `useEventSource()` 默认只保留最后 500 个 SSE packet，`SystemViewTab` 只保留最后 800 个解码事件。
- 组件用 `processedLen = data.length` 作为已处理游标；滚动缓存满了以后数组长度保持不变，即使新的 SSE packet 到来，watch 也会从 `processedLen` 循环到同一个 `data.length`，导致不再 ingest 新数据。

修复：
- `useEventSource()` 给每个 SSE packet 增加单调 `_streamSeq`。
- 新增 `streamCursor.ts::takeNewStreamPoints()`，按 `_streamSeq` 而不是数组长度取增量。
- `SystemViewTab`、`RttViewTab`、`RttChartTab` 均改为序号游标，避免同类滚动缓存冻结。
- SystemView 顶部“事件”改为累计处理数；事件列表仍只保留最近 800 条，防止内存增长。

新增验证：
- `npm test -- streamCursor.test.ts useEventSource.test.ts boundedBuffer.test.ts systemViewMetrics.test.ts svTimeline.test.ts`：9 passed
- `python -m pytest _maintainer/testing/tests/test_systemview_session.py _maintainer/testing/tests/test_systemview_dashboard.py -q`：4 passed
- `npm run build`：通过

## 第五轮：2300 条左右浏览器无响应

现象：
- 后端仍在增长，且 Python 进程内存正常；例如 `/api/dash/systemview/status` 可见 `events=222210`、`bytes=966275`、`clients=0`。
- 浏览器端在几千条事件后断开/无响应，说明瓶颈在前端主线程。

更深层根因：
- 上一轮虽然用 `_streamSeq` 解决了“滚动数组长度不变”问题，但 `useEventSource()` 仍使用普通 `ref([])` 保存 SSE packet。
- SystemView 的一个 packet 是 `batch`，内部包含最多 100 个事件；普通 `ref` 会把这些嵌套事件数组转成 Vue reactive proxy。
- 组件还对 `data` 使用 `{ deep: true }`，每来一个新包都会深遍历已有 batch 内的所有事件，复杂度随累计事件数快速上升，最终卡住浏览器主线程。

修复：
- `useEventSource()` 改为 `shallowRef`，SSE packet 仅作为浅层队列，不再把 `batch.events` 转成 reactive proxy。
- `useEventSource()` 改为不可变数组赋值，组件可用普通 `watch(data)` 收包，不再需要 deep watch。
- `SystemViewTab` 的 `eventList` / `intervals` 改为 `shallowRef`。
- SystemView ingest 改为每个 batch 只更新一次事件列表和 interval 列表，避免每个事件都触发数组响应式变更。

新增验证：
- `npm test -- useEventSource.test.ts streamCursor.test.ts boundedBuffer.test.ts systemViewMetrics.test.ts svTimeline.test.ts`：11 passed
- `python -m pytest _maintainer/testing/tests/test_systemview_session.py _maintainer/testing/tests/test_systemview_dashboard.py -q`：4 passed
- `npm run build`：通过

## 第六轮：时间轴 UI 可读性与纵向空间

现象：
- 图例 chip 仍沿用深色样式，文字在浅色页面中不清晰。
- 时间轴大跨度 tick label 过密，出现重叠。
- 事件流展开时占用纵向空间，时间轴泳道显示区域不足。

修复：
- `SvTimeline` 的时间刻度改为基于画布宽度的动态 nice step，并按标签宽度跳过过近标签。
- SystemView 图例 chip、窗口下拉改为浅色主题。
- 事件流默认折叠，保留标题和展开按钮；时间轴区域提高最小高度。
- 时间轴 canvas 容器允许滚动，避免泳道被裁切。

新增验证：
- `npm test -- svTimeline.test.ts useEventSource.test.ts streamCursor.test.ts boundedBuffer.test.ts systemViewMetrics.test.ts`：12 passed
- `python -m pytest _maintainer/testing/tests/test_systemview_session.py _maintainer/testing/tests/test_systemview_dashboard.py -q`：4 passed
- `npm run build`：通过

## 已确认能工作的路径

**MCP / python 直连路径** ✅：
```
python -c "
import mklink, time
d = mklink.connect(port='COM5', mcu='stm32f4', axf='...', project_root='D:/Projects/GEC6100D')
d.systemview_start(channel=1)   # CB 0x2001F000 ✓
raw = d.systemview_read_bytes(duration=2)  # 58000+ bytes ✓
events = SystemViewParser().feed(raw)      # 13000+ events ✓
"
```

**API 路径（干净 serve + 带 axf connect）** ✅：
```
# 新 serve 实例（端口释放后重启）
curl connect {"port":"COM5","mcu":"stm32f4","axf":"..."}  # 200
curl systemview/start {"addr":"0x2001f000","channel":1}    # 200
# → events 14732, synced=true ✓
```

**API 路径（干净 serve + 不带 axf connect）** ✅（project_root 修复后）：
```
curl connect {"port":"COM5","mcu":"stm32f4"}  # 200
curl systemview/start {"channel":1,"mode":0}   # 200
# → events 14732, synced=true ✓（RTT 地址从 config 读到 0x2001f000）
```

**GUI Playwright headed（demo 脚本）** 部分工作：
- 首次测试（serve 重启后）：数据流到 GUI（9 任务/500 事件）
- 后续测试（同 serve）：events 0（疑似 device/bridge 状态残留）

**GUI 用户手动操作** ❌：
- 多次尝试：点开始后事件 0
- serve 日志显示 systemview/start 200 OK + systemview/stream 200 OK
- 但 /api/dash/systemview/status stats events=0

## 已做的修复（未提交，在分支 test/gui-e2e-hil-regression）

### 1. api.py — history auto-restore 覆盖 project_root【主根因已修】
```python
# 旧：history 总是覆盖 _state["project_root"]
# 新：仅当 project_root == "."（未显式指定）时才 auto-restore
if project_root == ".":
    ...history restore...
```
验证：curl /api/project-root 返回 "D:/Projects/GEC6100D" ✓

### 2. systemview.py — magic 验证 retry 5×0.5s
```python
# SystemViewSession.start 的 CB magic 验证（cmd.read_ram）加 retry
for _ in range(5):
    try: magic = parse_read_ram_response(...)
    if magic[:11] == b"SEGGER RTT\x00": found = True; break
    except: pass
    time.sleep(0.5)
```

### 3. dashboards.py — _poll batch SSE + empty retry
```python
# batch SSE（1 消息/周期，减少 EventSource onmessage 从 400/s → 2/s）
batch = [{**ev, "_t": now} for ev in evs[-100:]]
if batch:
    self._bridge.put({"event": "batch", "events": batch})

# empty retry（连续 4 次空自动 stop+restart session）
if empty_cycles == 4:
    device.systemview_stop(); device.systemview_start(...)
```

### 4. SystemViewTab.vue — batch 处理 + 性能优化
- `processedLen` 修复（同 RttViewTab，Vue watch deep array mutation bug）
- batch event 处理：`if (evt === 'batch') { for (e of dp.events) ingest(e) }`
- 缓冲上限：MAX_EVENTS 800 / MAX_INTERVALS 1500 / recentEvents 50
- canvas rAF 节流（intervals 变化每帧最多 setData 一次）

### 5. systemview_report.py — 报告配色对齐 GUI 浅色主题
- body #f5f4ed / card-v #c96442 / cpu-bg #2a2a2a / canvas #0d1117

## 待排查方向

### A. GUI 点开始后 events=0 的根因
- API 路径（curl）在干净 serve 下**确认有数据**（events 14732）
- GUI 路径（Playwright headed + 用户手动）**间歇性失败**
- **怀疑**：GUI 的 onStart → dash.start → /api/dash/systemview/start 的时序与 API 不同
  - GUI onStart 先 checkConflict（/api/dash/conflict-check），可能影响
  - 或 GUI connect 后 ConfigView 触发其他 API（parse-axf / rtt-find）改变 bridge 状态
  - 或 GUI 浏览器的 EventSource 连接时机与 _poll put 的时序错位

### B. 排查步骤建议
1. **确认 project_root**：GUI 启动后在浏览器 console 执行
   `fetch('/api/project-root').then(r=>r.json()).then(console.log)`
   确认是 D:/Projects/GEC6100D（不是被 history 覆盖）

2. **确认 RTT 地址**：点开始后看 serve 控制台是否打印
   `[OK] 从配置读取 RTT 地址: 0x2001f000`
   如果是 0x20000000 → project_root 仍被覆盖

3. **确认 _poll 状态**：点开始 5s 后执行
   `fetch('/api/dash/systemview/status').then(r=>r.json()).then(console.log)`
   看 stats.events 是否 > 0

4. **如果 events=0**：用 API 直接 start（绕过 GUI onStart）：
   ```js
   fetch('/api/dash/systemview/stop', {method:'POST'})
   fetch('/api/dash/systemview/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"addr":"0x2001f000","channel":1,"mode":0}'})
   ```
   再看 status。如果 API start 有数据 → 问题在 GUI onStart 时序

5. **如果 API start 也 events=0**：问题在 device/bridge 状态
   - 断开重连（GUI 断开 → 重连 → 再点开始）
   - 或重启 serve

### C. 线程名 0x 地址
- GUI connect 时需填 AXF 路径 + 点「解析符号表」
- 或后续让 systemview_start 自动从 project_info 加载 axf

## 复现环境

```bash
# 启动 GUI
python -m mklink gui --project-root "D:/Projects/GEC6100D"

# 浏览器 http://127.0.0.1:8765
# 配置 → COM5 / stm32f4 → 连接
# 仪表盘 → RTOS Trace → 开始

# API 诊断
curl http://127.0.0.1:8765/api/project-root
curl http://127.0.0.1:8765/api/dash/systemview/status
```

## 改动文件清单（本次未提交）

| 文件 | 改动 |
|---|---|
| `mklink/remote/api.py` | history auto-restore 仅 project_root=="." 时 |
| `mklink/systemview.py` | magic 验证 retry 5×0.5s |
| `mklink/remote/dashboards.py` | batch SSE + empty retry + 限速 100/周期 |
| `gui/src/components/dash/SystemViewTab.vue` | batch 处理 + processedLen + 缓冲上限 + rAF 节流 |
| `mklink/systemview_report.py` | 报告配色对齐 GUI |

## 已提交的 commits（分支 test/gui-e2e-hil-regression）

- `3503b4b` test(gui): 全面回归 skill→plugin 升级 + 修复重大既有 bug
- `6f1d714` fix(gui): RTT View 渲染 bug — Vue watch deep array mutation 漏数据
- `f588742` fix(gui): SystemViewTab watch 同 RTT 渲染 bug — processedLen
- `2ceee4e` style(systemview): HTML 报告配色对齐 GUI 浅色暖色调主题
