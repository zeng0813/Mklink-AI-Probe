# SystemView Live Follow Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SystemView RTOS Trace timeline smoothly follow live data, record importable JSONL logs, polish slice/CPU-bar styling, and replace the ambiguous switch-count suffix.

**Architecture:** Backend `SystemViewStreamManager` remains the decoded-event source and gains a small focused JSONL logger. Frontend `SystemViewTab.vue` keeps bounded render buffers and delegates live-follow animation to `SvTimeline`. UI-only label/style helpers stay in frontend lib files so they can be tested without a browser session.

**Tech Stack:** Python FastAPI dashboard manager, Vue 3 `<script setup>`, TypeScript helper modules, canvas renderer, Vitest, pytest.

---

### Task 1: Scheduling Count Label Helper

**Files:**
- Create: `gui/src/lib/systemViewLabels.ts`
- Create/Modify: `gui/src/lib/__tests__/systemViewLabels.test.ts`
- Modify: `gui/src/components/dash/SystemViewTab.vue`

- [ ] **Step 1: Write the failing label test**

```ts
import { describe, expect, it } from 'vitest'
import { formatScheduleCount } from '../systemViewLabels'

describe('systemViewLabels', () => {
  it('formats task scheduling starts with an explicit Chinese label', () => {
    expect(formatScheduleCount(0)).toBe('0次调度')
    expect(formatScheduleCount(4410)).toBe('4,410次调度')
  })
})
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `cd gui && npm test -- systemViewLabels.test.ts`

Expected: fails because `systemViewLabels.ts` does not exist.

- [ ] **Step 3: Implement the helper**

```ts
export function formatScheduleCount(count: number): string {
  const value = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0
  return `${value.toLocaleString()}次调度`
}
```

- [ ] **Step 4: Use the helper in `SystemViewTab.vue`**

Import `formatScheduleCount` and replace the CPU-row switch-count text with:

```vue
<span class="sv-cpu-switches" :title="'task_start_exec count'">
  {{ formatScheduleCount(t.switches) }}
</span>
```

- [ ] **Step 5: Run test and build**

Run:

```powershell
cd gui
npm test -- systemViewLabels.test.ts
npm run build
```

Expected: test and build pass.

### Task 2: Timeline Live Follow

**Files:**
- Modify: `gui/src/lib/svTimeline.js`
- Modify: `gui/src/lib/svTimeline.d.ts`
- Modify: `gui/src/lib/__tests__/svTimeline.test.ts`
- Modify: `gui/src/components/dash/SystemViewTab.vue`

- [ ] **Step 1: Write timeline tests**

Add tests that construct `SvTimeline` with `{ follow: true, windowSize: 2_000_000 }`, call `setData()` with intervals ending at `3_000_000`, and assert `viewEnd` moves toward `3_000_000` while `viewEnd - viewStart` remains `2_000_000`. Add a second test that calls the wheel handler or a public `setFollowMode(false)` method and verifies subsequent `setData()` does not force live follow.

- [ ] **Step 2: Implement live follow state**

Add fields to `SvTimeline`:

```js
this.follow = data?.follow !== false;
this.windowSize = Number(data?.windowSize || 0);
this.followEase = 0.22;
this._followRaf = 0;
```

Add methods:

```js
setWindowSize(windowSize) { this.windowSize = Number(windowSize || 0); this._scheduleFollow(); }
setFollowMode(enabled) { this.follow = !!enabled; if (this.follow) this._snapFollow(); }
_targetFollowRange() { ...latest tMax minus windowSize... }
_scheduleFollow() { ...requestAnimationFrame loop... }
_snapFollow() { ...set exact target...draw/update... }
```

Wheel and drag disable follow. `reset()` re-enables follow and snaps to latest range.

- [ ] **Step 3: Wire frontend**

Pass `follow: true` and `windowSize: windowUs.value` when creating `SvTimeline`. On `windowUs` changes call `tlInstance.setWindowSize(windowUs.value)` instead of recreating. `tlReset()` should call timeline `reset()` which returns to live mode.

- [ ] **Step 4: Verify**

Run:

```powershell
cd gui
npm test -- svTimeline.test.ts
npm run build
```

Expected: tests and build pass.

### Task 3: Backend JSONL Logger

**Files:**
- Create: `mklink/systemview_logger.py`
- Create/Modify: `_maintainer/testing/tests/test_systemview_logger.py`
- Modify: `mklink/remote/dashboards.py`
- Modify: `_maintainer/testing/tests/test_systemview_dashboard.py`

- [ ] **Step 1: Write logger tests**

Test that `SystemViewJsonlLogger` creates a JSONL file, writes a `session` record, writes `event` records with monotonic `seq`, and writes a `summary` record plus text summary on close.

Test that a write error can be surfaced as `recording_error` without raising from the stream manager.

- [ ] **Step 2: Implement logger**

Create `SystemViewJsonlLogger` with:

```py
class SystemViewJsonlLogger:
    def __init__(self, project_root: str, session_meta: dict, clock: Callable[[], datetime] | None = None): ...
    def write_events(self, events: list[dict]) -> None: ...
    def close(self, summary: dict) -> None: ...
```

Use UTF-8, `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`, and write under `.mklink/logs/systemview/`.

- [ ] **Step 3: Integrate manager**

In `SystemViewStreamManager.start()` initialize the logger after `device.systemview_start()`, using `_status_meta()` for session metadata. On each parsed batch call `logger.write_events(evs)`. On `finally`, call `logger.close({stats, dropped, cpu_freq, cpu_freq_source})`.

Expose `recording_path`, `recording_summary_path`, and `recording_error` in `_status_meta()` / status SSE.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest _maintainer\testing\tests\test_systemview_logger.py _maintainer\testing\tests\test_systemview_dashboard.py -q
```

Expected: tests pass.

### Task 4: Visual Polish For Timeline And CPU Bars

**Files:**
- Modify: `gui/src/lib/svTimeline.js`
- Modify: `gui/src/components/dash/SystemViewTab.vue`
- Modify: `gui/src/lib/__tests__/svTimeline.test.ts`

- [ ] **Step 1: Update canvas styling**

Change label column and slice rendering:

```js
ctx.fillStyle = '#fffdf8';
ctx.fillRect(0, y, this.nameColW, this.laneH);
ctx.fillStyle = '#d4cabc';
ctx.fillRect(this.nameColW - 1, y, 1, this.laneH);
ctx.fillStyle = task.color;
ctx.fillRect(x0, y + 4, Math.max(x1 - x0, 0.8), this.laneH - 8);
ctx.strokeStyle = 'rgba(31, 41, 55, 0.22)';
ctx.strokeRect(x0 + 0.5, y + 4.5, Math.max(x1 - x0, 0.8), this.laneH - 9);
```

Use square or 2px max rounded corners. Do not use dark blocks.

- [ ] **Step 2: Update CPU CSS**

Set:

```css
.sv-cpu-bar-bg { border-radius: 0; }
.sv-cpu-bar { border-radius: 0; }
.sv-cpu-switches { width: 78px; }
```

- [ ] **Step 3: Verify**

Run frontend tests and build:

```powershell
cd gui
npm test -- svTimeline.test.ts systemViewLabels.test.ts
npm run build
```

Expected: tests and build pass.

### Task 5: Final Regression And GUI Restart

**Files:**
- No new files unless tests expose a regression.

- [ ] **Step 1: Run frontend regression**

```powershell
cd gui
npm test -- svTimeline.test.ts systemViewTimeBuffer.test.ts systemViewLabels.test.ts useEventSource.test.ts streamCursor.test.ts boundedBuffer.test.ts systemViewMetrics.test.ts
npm run build
```

- [ ] **Step 2: Run backend regression**

```powershell
python -m pytest _maintainer\testing\tests\test_systemview_session.py _maintainer\testing\tests\test_systemview_dashboard.py _maintainer\testing\tests\test_systemview_logger.py -q
```

- [ ] **Step 3: Restart GUI**

Stop the existing `python -m mklink gui --port 8765` process only, then restart:

```powershell
python -m mklink gui --host 127.0.0.1 --port 8765 --no-browser --project-root D:/Projects/GEC6100D
```

- [ ] **Step 4: Report**

Report the GUI URL, PID, and verification results. Mention the log directory and importable JSONL schema.

---

## Self-Review

- Spec coverage: timeline live follow, backend JSONL logging, summary file, visual slice/CPU style, and scheduling-count wording are all covered by tasks.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: frontend helper names are `formatScheduleCount`, timeline methods are `setWindowSize` and `setFollowMode`, backend logger class is `SystemViewJsonlLogger`.
