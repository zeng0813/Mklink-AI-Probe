# SystemView Export Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded SystemView JSONL export and browser-side streaming import to the RTOS Trace page.

**Architecture:** Backend endpoints list and download already-recorded SystemView JSONL/summary files after strict project-log path validation. Frontend import uses a focused JSONL parser module that reads files incrementally, batches event records, and reuses `SystemViewTab.vue` ingestion for offline viewing.

**Tech Stack:** FastAPI/Starlette backend, Vue 3 Composition API frontend, Vitest, pytest.

---

## File Structure

- Create `mklink/systemview_logs.py`: project log directory resolution, safe listing, and validated download path resolution.
- Modify `mklink/remote/api.py`: add SystemView log list and download endpoints.
- Test `_maintainer/testing/tests/test_systemview_logs.py`: backend helper and API endpoint coverage.
- Create `gui/src/lib/systemViewImport.ts`: streaming JSONL parser and batch import helpers.
- Test `gui/src/lib/__tests__/systemViewImport.test.ts`: chunk splitting, malformed line handling, metadata, and batching.
- Modify `gui/src/components/dash/SystemViewTab.vue`: export/import controls, offline mode state, file picker, parser integration, and live reset.

## Task 1: Backend Log Listing And Download Validation

**Files:**
- Create: `mklink/systemview_logs.py`
- Modify: `mklink/remote/api.py`
- Test: `_maintainer/testing/tests/test_systemview_logs.py`

- [ ] **Step 1: Write failing backend tests**

Create `_maintainer/testing/tests/test_systemview_logs.py` with tests for:

```python
def test_list_systemview_logs_pairs_jsonl_and_summary(tmp_path):
    from mklink.systemview_logs import list_systemview_logs

    log_dir = tmp_path / ".mklink" / "logs" / "systemview"
    log_dir.mkdir(parents=True)
    trace = log_dir / "systemview-20260627-120000.jsonl"
    summary = log_dir / "systemview-20260627-120000-summary.txt"
    trace.write_text('{"type":"session","schema":1}\n', encoding="utf-8")
    summary.write_text("summary\n", encoding="utf-8")

    items = list_systemview_logs(str(tmp_path))

    assert len(items) == 1
    assert items[0]["path"] == str(trace.resolve())
    assert items[0]["summary_path"] == str(summary.resolve())
    assert items[0]["name"] == trace.name
    assert items[0]["size"] > 0
```

Also test traversal rejection:

```python
def test_resolve_systemview_log_download_rejects_traversal(tmp_path):
    import pytest
    from mklink.systemview_logs import SystemViewLogPathError, resolve_systemview_log_download

    outside = tmp_path / "outside.jsonl"
    outside.write_text("x\n", encoding="utf-8")

    with pytest.raises(SystemViewLogPathError):
        resolve_systemview_log_download(str(tmp_path), str(outside))
```

- [ ] **Step 2: Run backend tests and verify they fail**

Run:

```powershell
python -m pytest _maintainer\testing\tests\test_systemview_logs.py -q
```

Expected: fail because `mklink.systemview_logs` does not exist.

- [ ] **Step 3: Implement backend helper and endpoints**

Implement `mklink/systemview_logs.py` with:

```python
class SystemViewLogPathError(ValueError):
    pass

def systemview_log_dir(project_root: str) -> Path:
    return (Path(project_root or ".").resolve() / ".mklink" / "logs" / "systemview")

def list_systemview_logs(project_root: str, limit: int = 50) -> list[dict]:
    log_dir = systemview_log_dir(project_root)
    if not log_dir.is_dir():
        return []
    traces = sorted(log_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_log_item(path) for path in traces[:limit]]

def resolve_systemview_log_download(project_root: str, requested_path: str) -> Path:
    root = systemview_log_dir(project_root).resolve()
    candidate = Path(requested_path).resolve()
    if candidate.suffix.lower() not in {".jsonl", ".txt"}:
        raise SystemViewLogPathError("unsupported SystemView log file type")
    if root != candidate and root not in candidate.parents:
        raise SystemViewLogPathError("SystemView log path is outside the project log directory")
    if not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return candidate
```

Modify `mklink/remote/api.py` near existing SystemView routes:

```python
@app.get("/api/dash/systemview/logs")
async def systemview_logs():
    from mklink.systemview_logs import list_systemview_logs
    return {"logs": list_systemview_logs(_state["project_root"])}

@app.get("/api/dash/systemview/logs/download")
async def systemview_log_download(path: str = Query(...)):
    from fastapi.responses import FileResponse
    from mklink.systemview_logs import SystemViewLogPathError, resolve_systemview_log_download
    try:
        resolved = resolve_systemview_log_download(_state["project_root"], path)
    except SystemViewLogPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="SystemView log not found")
    return FileResponse(
        resolved,
        media_type="application/jsonl" if resolved.suffix == ".jsonl" else "text/plain",
        filename=resolved.name,
    )
```

- [ ] **Step 4: Run backend tests and verify they pass**

Run:

```powershell
python -m pytest _maintainer\testing\tests\test_systemview_logs.py -q
```

Expected: pass.

## Task 2: Frontend Streaming JSONL Import Parser

**Files:**
- Create: `gui/src/lib/systemViewImport.ts`
- Test: `gui/src/lib/__tests__/systemViewImport.test.ts`

- [ ] **Step 1: Write failing parser tests**

Create tests covering split lines and malformed lines:

```ts
import { describe, expect, test, vi } from 'vitest'
import { importSystemViewJsonl } from '../systemViewImport'

test('imports split JSONL lines in batches', async () => {
  const chunks = [
    '{"type":"session","schema":1,"cpu_freq":168000000}\n{"type":"event","kind":"task_start_exec",',
    '"task_id":1,"t_us":10}\n{"type":"summary","events":1}\n',
  ]
  const batches: any[][] = []
  const result = await importSystemViewJsonl({
    stream: streamFromChunks(chunks),
    batchSize: 1,
    onBatch: batch => batches.push(batch),
  })

  expect(result.events).toBe(1)
  expect(result.session?.cpu_freq).toBe(168000000)
  expect(result.summary?.events).toBe(1)
  expect(batches).toHaveLength(1)
})
```

- [ ] **Step 2: Run parser tests and verify they fail**

Run:

```powershell
cd gui; npm test -- systemViewImport.test.ts
```

Expected: fail because `systemViewImport` does not exist.

- [ ] **Step 3: Implement parser**

Implement exported APIs:

```ts
export interface SystemViewImportResult {
  events: number
  skipped: number
  parseErrors: number
  session: Record<string, unknown> | null
  summary: Record<string, unknown> | null
}

export async function importSystemViewJsonl(options: {
  stream: ReadableStream<Uint8Array>
  batchSize?: number
  onBatch: (events: any[]) => void | Promise<void>
  onSession?: (record: Record<string, unknown>) => void
  onSummary?: (record: Record<string, unknown>) => void
  signal?: AbortSignal
}): Promise<SystemViewImportResult>
```

Use `TextDecoder`, preserve trailing partial lines, skip bad records, and yield with `await new Promise(resolve => setTimeout(resolve, 0))` between batches.

- [ ] **Step 4: Run parser tests and verify they pass**

Run:

```powershell
cd gui; npm test -- systemViewImport.test.ts
```

Expected: pass.

## Task 3: RTOS Trace Toolbar Export And Offline Import

**Files:**
- Modify: `gui/src/components/dash/SystemViewTab.vue`
- Test: existing frontend tests and production build

- [ ] **Step 1: Add failing lightweight UI-independent import behavior coverage**

Extend `gui/src/lib/__tests__/systemViewImport.test.ts` with an abort test:

```ts
test('aborts import before finishing all batches', async () => {
  const controller = new AbortController()
  const batches: any[][] = []
  await expect(importSystemViewJsonl({
    stream: streamFromChunks([
      '{"type":"event","kind":"task_start_exec","task_id":1,"t_us":1}\n',
      '{"type":"event","kind":"task_stop_exec","task_id":1,"t_us":2}\n',
    ]),
    batchSize: 1,
    signal: controller.signal,
    onBatch: batch => {
      batches.push(batch)
      controller.abort()
    },
  })).rejects.toThrow(/aborted/i)
  expect(batches).toHaveLength(1)
})
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
cd gui; npm test -- systemViewImport.test.ts
```

Expected: fail until abort handling is implemented.

- [ ] **Step 3: Implement toolbar integration**

Modify `SystemViewTab.vue` to:

- Track `offlineMode`, `offlineFileName`, `importStatus`, `importAbort`.
- Add `recordingPath`, `recordingSummaryPath` metadata from SSE status/batch.
- Add buttons for export JSONL, export summary, import JSONL, and live mode.
- Use a hidden file input for JSONL import.
- On import, disconnect SSE, abort any previous import, clear state, apply session metadata, and call `ingestEvents(batch, true)` for each parser batch.
- Use `window.open('/api/dash/systemview/logs/download?path=' + encodeURIComponent(path), '_blank')` for backend-recorded exports.

- [ ] **Step 4: Run frontend targeted tests**

Run:

```powershell
cd gui; npm test -- systemViewImport.test.ts svTimeline.test.ts systemViewTimeBuffer.test.ts systemViewLabels.test.ts useEventSource.test.ts streamCursor.test.ts boundedBuffer.test.ts systemViewMetrics.test.ts
```

Expected: all pass.

## Task 4: Full Verification And Commit

**Files:**
- All modified implementation and test files

- [ ] **Step 1: Run backend SystemView tests**

Run:

```powershell
python -m pytest _maintainer\testing\tests\test_systemview_session.py _maintainer\testing\tests\test_systemview_dashboard.py _maintainer\testing\tests\test_systemview_logger.py _maintainer\testing\tests\test_systemview_logs.py -q
```

Expected: all pass.

- [ ] **Step 2: Run frontend production build**

Run:

```powershell
cd gui; npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Check repository diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files changed.

- [ ] **Step 4: Commit implementation**

Run:

```powershell
git add mklink\systemview_logs.py mklink\remote\api.py _maintainer\testing\tests\test_systemview_logs.py gui\src\lib\systemViewImport.ts gui\src\lib\__tests__\systemViewImport.test.ts gui\src\components\dash\SystemViewTab.vue
git commit -m "feat(systemview): add trace export import"
```

Expected: commit succeeds.
