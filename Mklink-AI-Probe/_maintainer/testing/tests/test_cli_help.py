import subprocess
import sys
from pathlib import Path


def test_top_level_help_renders_systemview_commands():
    root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [sys.executable, "-m", "mklink", "--help"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert "systemview-analyze" in result.stdout
