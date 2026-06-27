# SystemView Export And Import Design

Date: 2026-06-27

## Scope

Add export and import support for SystemView RTOS Trace logs.

The goal is post-capture analysis without reconnecting to the target board. A user should be able to save a captured trace, later import the JSONL log in the same RTOS Trace page, and inspect CPU usage, task-switch timeline, and recent events with the existing visualization.

This change does not add a full replay player, seek controls, or backend database indexing.

## Selected Approach

Use the existing UTF-8 JSONL capture file as the interchange format.

Export is file-oriented:

- The backend records each live SystemView session to `<project_root>/.mklink/logs/systemview/`.
- The GUI exposes the current or most recent JSONL path reported by the backend status.
- The GUI can download the JSONL file and the summary text file.
- The backend also provides a small endpoint for downloading a SystemView log by path after validating that it is inside the project SystemView log directory.

Import is browser-side and streaming:

- The user selects a `.jsonl` file in the RTOS Trace page.
- The frontend reads the file with `Blob.stream()` or an equivalent chunked reader.
- The parser decodes line-delimited JSON incrementally and feeds records to the existing `ingestEvents()` path in batches.
- Session and summary records update offline metadata. Event records build task statistics, timeline intervals, and the recent event list.
- The page enters an offline-log mode so the live SSE connection is not required.

This avoids uploading large files to the backend and avoids creating a single large JSON response, which would risk browser stalls or out-of-memory failures.

## Data Model

The import parser accepts schema version 1 records:

```jsonl
{"type":"session","schema":1,"started_at":"2026-06-27T09:00:00Z","cpu_freq":168000000,"cpu_freq_source":"SystemCoreClock","unit":"us+tk"}
{"type":"event","seq":1,"kind":"task_start_exec","t_ticks":123456,"t_us":734.86,"task_id":536876944,"task_name":"ADC"}
{"type":"summary","schema":1,"events":261900,"dropped_bytes":0,"dropped_packets":1}
```

Rules:

- Unknown record types are ignored and counted as skipped records.
- Invalid JSON lines are skipped and counted as parse errors.
- Event records without a valid `kind` are skipped.
- `session.cpu_freq` is applied before imported events when present.
- Imported event `seq` is treated as file order metadata, not as the live SSE cursor.

## UI Behavior

Add compact controls to the RTOS Trace toolbar:

- `Export JSONL`: downloads the current or most recent capture JSONL.
- `Export Summary`: downloads the matching text summary when available.
- `Import JSONL`: opens a file picker and imports the selected log.
- `Live`: clears offline data and returns to live capture mode.

Offline mode should be visible but unobtrusive:

- Show the imported file name and parsed event count.
- Disable or avoid live start/pause/stop interactions that do not apply to an imported file.
- Keep the same window selector. It controls timeline visibility only, not how much of the imported file is parsed.
- Keep the event stream collapsed by default.

## Memory And Performance Boundaries

The import path must remain bounded:

- Parse the JSONL file incrementally.
- Feed events to the renderer in batches, for example 500 to 2000 records per batch.
- Yield back to the browser between batches so the UI stays responsive.
- Keep the existing recent-event and timeline interval caps.
- Maintain aggregate task statistics while avoiding DOM rendering of every event.

The imported file may contain more events than the visible timeline buffer. In that case, CPU usage and event count reflect the imported events processed so far, while the timeline remains bounded to the retained analysis window.

## Backend Endpoints

Add focused SystemView log endpoints:

- `GET /api/dash/systemview/logs`: list recent JSONL captures and summaries under the project log directory.
- `GET /api/dash/systemview/logs/download?path=...`: download a validated log file.

Path validation requirements:

- Resolve the requested path to an absolute path.
- Require it to stay under `<project_root>/.mklink/logs/systemview/`.
- Allow only `.jsonl` and `.txt` files.
- Return 404 for missing files and 400 for invalid paths.

## Error Handling

- If no capture has been recorded, export buttons are disabled and the UI shows a short status message.
- If a download fails, show a non-blocking error in the RTOS Trace page.
- If import is cancelled, keep the current view unchanged.
- If import has parse errors, complete the import and show skipped/error counts.
- If the file is too large for the browser to process comfortably, the parser can be cancelled by starting live mode or importing another file.

## Tests

Add or extend tests for:

- JSONL parser reads chunked input, handles split lines, and skips malformed records.
- Import batches call the same event ingestion path without growing the rendered event list beyond existing limits.
- Offline metadata applies CPU frequency and task names from the imported file.
- Backend log listing only includes files under the project SystemView log directory.
- Backend download rejects path traversal and unsupported extensions.
- GUI build still passes after the toolbar changes.
