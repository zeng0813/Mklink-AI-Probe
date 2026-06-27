"""Helpers for listing and safely downloading SystemView capture logs."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


class SystemViewLogPathError(ValueError):
    """Raised when a requested SystemView log path is outside the log root."""


def systemview_log_dir(project_root: str) -> Path:
    """Return the project-local SystemView log directory."""
    return Path(project_root or ".").resolve() / ".mklink" / "logs" / "systemview"


def list_systemview_logs(project_root: str, limit: int = 50) -> list[dict]:
    """List recent SystemView JSONL captures with matching summaries."""
    log_dir = systemview_log_dir(project_root)
    if not log_dir.is_dir():
        return []

    traces = sorted(
        log_dir.glob("*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    capped = traces[: max(0, int(limit))]
    return [_log_item(trace) for trace in capped]


def resolve_systemview_log_download(project_root: str, requested_path: str) -> Path:
    """Resolve a requested log path and verify it is safe to download."""
    if not requested_path:
        raise SystemViewLogPathError("missing SystemView log path")

    root = systemview_log_dir(project_root).resolve()
    candidate = Path(requested_path).resolve()
    if candidate.suffix.lower() not in {".jsonl", ".txt"}:
        raise SystemViewLogPathError("unsupported SystemView log file type")
    if not _is_relative_to(candidate, root):
        raise SystemViewLogPathError(
            "SystemView log path is outside the project log directory"
        )
    if not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return candidate


def _log_item(trace: Path) -> dict:
    stat = trace.stat()
    summary = trace.with_name(f"{trace.stem}-summary.txt")
    return {
        "name": trace.name,
        "path": str(trace.resolve()),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, timezone.utc,
        ).isoformat(),
        "summary_name": summary.name if summary.is_file() else "",
        "summary_path": str(summary.resolve()) if summary.is_file() else "",
        "summary_size": summary.stat().st_size if summary.is_file() else 0,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    path_text = os.path.normcase(str(path))
    root_text = os.path.normcase(str(root))
    try:
        common = os.path.commonpath([path_text, root_text])
    except ValueError:
        return False
    return common == root_text
