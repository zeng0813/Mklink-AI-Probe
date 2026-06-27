# SystemView Live Follow And Logging Design

Date: 2026-06-27

## Scope

Improve the SystemView RTOS Trace GUI in four focused areas:

- The task-switch timeline should advance smoothly in live mode instead of visually resetting or zooming when new data arrives.
- The dashboard should record trace data to files for later analysis.
- Timeline slices and CPU bars should be easier to distinguish from lane labels and should use square-ended progress bars.
- CPU usage rows should replace the ambiguous current switch-count suffix with a clearer scheduling-count label.

This design does not add a full replay/scrub analyzer. The log format will support future import, but the current change only records and exposes files.

## Decisions

### Timeline Interaction

Use a smooth live-follow mode. While the stream is running and the user has not manually panned or zoomed, the visible timeline range follows the latest event using the selected window size. The range moves toward the target on animation frames, giving a strip-chart effect.

Manual interaction pauses live follow:

- Wheel zoom or drag pan switches the timeline into analysis mode.
- The existing full-view/reset control returns to live follow and snaps back to the latest window.
- The selected window, such as `2s`, controls the visible time span only. It does not limit backend or analysis logging buffers.

### Logging Format

Record on the backend, not through frontend export. This keeps logging reliable even if the browser refreshes or becomes slow.

Each SystemView session creates a UTF-8 JSONL file under:

`<project_root>/.mklink/logs/systemview/systemview-YYYYMMDD-HHMMSS.jsonl`

The file uses a versioned import-friendly schema:

```jsonl
{"type":"session","schema":1,"started_at":"2026-06-27T09:00:00Z","cpu_freq":168000000,"cpu_freq_source":"SystemCoreClock","unit":"us+tk"}
{"type":"event","seq":1,"kind":"task_start_exec","t_ticks":123456,"t_us":734.86,"task_id":536876944,"task_name":"ADC"}
{"type":"summary","events":261900,"dropped_bytes":0,"dropped_packets":1}
```

The logger writes event batches as JSONL lines and flushes in small batches. If the process exits unexpectedly, previously completed lines remain importable; at worst the final line may be incomplete.

A small summary text file is written next to the JSONL file at stop time:

`systemview-YYYYMMDD-HHMMSS-summary.txt`

The summary contains session duration, event count, dropped counters, CPU frequency source, and top task runtime/scheduling counts.

### UI Style

Timeline slices should look separate from labels and lanes:

- Keep the lane label column light but add a stronger vertical divider.
- Draw slices with a small vertical inset, subtle border, and square or slightly rounded corners no larger than 2px.
- Use lane background contrast that is visible but low-noise.
- Keep hover highlight visible without using dark blocks.

CPU usage bars should use square ends:

- Progress track and fill use `border-radius: 0`.
- Right-side text is split into percentage and scheduling count.
- Replace the current `N + switch suffix` display with the Chinese UI label equivalent to `N scheduling starts`. The number means how many `task_start_exec` events were observed for that task, i.e. how often the task was scheduled to run within the retained session stats.

### Data Flow

Backend `SystemViewStreamManager` remains the source of truth for raw decoded events. It streams bounded batches to the GUI and writes the full decoded event stream to disk. The frontend keeps its existing analysis buffer for responsive rendering and uses the selected window only for visible intervals.

The frontend passes visible-window intervals into `SvTimeline`. `SvTimeline` owns live-follow animation state and exposes methods for setting data, resetting, and resuming follow mode. It does not fetch data or write logs.

## Error Handling

- If the log directory cannot be created or the file cannot be opened, the dashboard continues streaming and reports `recording_error` in status metadata.
- If a batch write fails, logging is disabled for that session and the error is surfaced in status metadata.
- Stop finalizes the summary best-effort; failure to write the summary does not break the trace stream.
- JSON serialization uses UTF-8 and `ensure_ascii=false` so task names remain readable while the file stays valid JSON.

## Tests

Add or extend focused tests:

- Timeline live follow keeps a fixed visible window and animates toward the latest range.
- Manual pan/zoom disables live follow until reset.
- JSONL logger writes session, event, and summary records with schema version and time fields.
- Logging failure surfaces status error without stopping stream parsing.
- UI utility tests cover scheduling label formatting, replacing the ambiguous current suffix.

Run the existing SystemView frontend and backend regression tests plus production GUI build before restarting the GUI.
