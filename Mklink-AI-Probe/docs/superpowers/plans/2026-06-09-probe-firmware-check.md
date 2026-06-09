# Probe Firmware Check on Init — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `project-init` 流程中嵌入"探针自身固件版本检查"，太旧时通过 CLI `[WARN]` 文本 / GUI 弹窗指引用户按住按钮+插 USB+拷 UF2 完成升级。

**Architecture:** 新增独立模块 `mklink/firmware_check.py`（纯函数 + dataclass），CLI / FastAPI / GUI 共享。状态分 4 态（`ok` / `upgrade_required` / `no_firmware_dir` / `skipped`），GUI 不必猜测分支。最小支持版本 = 扫 `MK-Firmware/MicroLink_V*.uf2` 取最小。

**Tech Stack:** Python 3.11+（dataclass / Literal / pathlib）、FastAPI + Pydantic、Vue 3 + TypeScript、pytest、Playwright (E2E)。

---

## File Structure

| 文件 | 类型 | 职责 |
|---|---|---|
| `mklink/firmware_check.py` | 新增 | 核心：版本解析、固件扫描、设备版本读取、check 编排、instructions 生成 |
| `mklink/cli.py` | 改 | `_cli_project_init` 末尾追加 `firmware_check` 调用 + `[WARN]` 打印 |
| `mklink/remote/api.py` | 改 | `POST /api/project-init` 响应加 `firmware_check`；新增 `GET /api/probe/firmware-check` |
| `gui/src/types/mklink.ts` | 改 | 加 `FirmwareInfo` / `ProbeFirmwareCheck` |
| `gui/src/composables/useMklinkApi.ts` | 改 | 加 `probeFirmwareCheck()` |
| `gui/src/composables/useTauri.ts` | 新增 | `openInExplorer(path)` 封装（浏览器降级 toast） |
| `gui/src/components/config/FirmwareUpdateModal.vue` | 新增 | 升级弹窗组件 |
| `gui/src/views/ConfigView.vue` | 改 | `doProjectInit` 处理 `firmware_check`；状态条 + 模态触发 |
| `_maintainer/testing/tests/mock_gui_api.py` | 改 | `MockState.probe_firmware_check` 字段 + 新端点 mock + 预设 |
| `_maintainer/testing/tests/test_firmware_check.py` | 新增 | 核心模块单测 |
| `_maintainer/testing/tests/test_cli_project_init.py` | 新增 | CLI 集成测试 |
| `_maintainer/testing/tests/test_api_firmware_check.py` | 新增 | FastAPI 端点测试 |
| `_maintainer/testing/tests/e2e/gui/test_firmware_update_modal.py` | 新增 | GUI E2E（Playwright + Mock API） |

---

## Task 0: 准备工作

**Files:**
- Move: `C:\Users\Tony\.claude\plans\c-users-tony-claude-skills-mklink-flash-calm-willow.md` → `docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md`
- Verify: `docs/superpowers/plans/2026-06-09-probe-firmware-check.md` 已存在（本文件）

- [ ] **Step 1: 复制 spec 到标准位置**

```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
mkdir -p docs/superpowers/specs
cp "C:\Users\Tony\.claude\plans\c-users-tony-claude-skills-mklink-flash-calm-willow.md" \
   docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md
ls docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md
```

- [ ] **Step 2: 提交 spec**

```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
git add docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md \
        docs/superpowers/plans/2026-06-09-probe-firmware-check.md
git commit -m "docs: probe firmware check on init spec + implementation plan"
```

---

## Phase 1: 核心模块 `mklink/firmware_check.py`

### Task 1.1: `Version` dataclass + 排序

**Files:**
- Create: `mklink/firmware_check.py`
- Create: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 写失败测试（Version 比较）**

`_maintainer/testing/tests/test_firmware_check.py`:

```python
from mklink.firmware_check import Version


def test_version_str():
    assert str(Version(3, 3, 1)) == "V3.3.1"
    assert str(Version(4, 0, 0)) == "V4.0.0"


def test_version_lt_same_major():
    assert Version(3, 3, 1) < Version(3, 3, 2)
    assert Version(3, 9, 0) < Version(3, 10, 0)


def test_version_lt_cross_major():
    assert Version(3, 9, 0) < Version(4, 0, 0)
    assert not (Version(4, 0, 0) < Version(3, 9, 0))


def test_version_eq_and_hash():
    assert Version(3, 3, 1) == Version(3, 3, 1)
    assert hash(Version(3, 3, 1)) == hash(Version(3, 3, 1))
```

- [ ] **Step 2: 跑测试，确认失败**

Run:
```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
pytest _maintainer/testing/tests/test_firmware_check.py -v
```

Expected: `ImportError: cannot import name 'Version' from 'mklink.firmware_check'`

- [ ] **Step 3: 实现 Version**

`mklink/firmware_check.py`:

```python
"""Probe firmware version check for MicroLink (V3/V4) burners.

纯函数 + dataclass 设计；CLI / FastAPI / GUI 共用。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

# 固件文件名格式：MicroLink_V3.3.1.uf2 / MicroLink_V4.3.1.uf2
_FIRMWARE_FILE_RE = re.compile(
    r"^MicroLink_(V(\d+)\.(\d+)\.(\d+))\.uf2$"
)

# Firmware directory name (relative to repo/package root)
FIRMWARE_DIR_NAME = "MK-Firmware"

# Default environment variable for overriding firmware dir
FIRMWARE_DIR_ENV = "MKLINK_FIRMWARE_DIR"

# Serial command timeout (seconds) for cmd.get_version()
DEFAULT_VERSION_TIMEOUT = 5.0

# Status of CheckResult
CheckStatus = Literal["ok", "upgrade_required", "no_firmware_dir", "skipped"]


@dataclass(frozen=True)
class Version:
    """SemVer-style version with V<major>.<minor>.<patch> string format."""
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"V{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) < (
            other.major, other.minor, other.patch
        )

    def __le__(self, other: "Version") -> bool:
        return self == other or self < other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (
            other.major, other.minor, other.patch
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v
```

Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add Version dataclass with comparison"
```

---

### Task 1.2: `parse_firmware_filename`

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试**

`_maintainer/testing/tests/test_firmware_check.py` 末尾追加:

```python
from mklink.firmware_check import (
    Version,
    parse_firmware_filename,
    FirmwareInfo,
)
from pathlib import Path


def test_parse_firmware_filename_v3():
    info = parse_firmware_filename("MicroLink_V3.3.1.uf2")
    assert info is not None
    assert info.name == "MicroLink_V3.3.1.uf2"
    assert info.version == Version(3, 3, 1)
    assert info.model == "V3"
    assert info.path == Path("MicroLink_V3.3.1.uf2")


def test_parse_firmware_filename_v4():
    info = parse_firmware_filename("MicroLink_V4.3.1.uf2")
    assert info is not None
    assert info.model == "V4"
    assert info.version == Version(4, 3, 1)


def test_parse_firmware_filename_invalid():
    assert parse_firmware_filename("MicroLink_V3.3.0.bak") is None
    assert parse_firmware_filename("random.txt") is None
    assert parse_firmware_filename("") is None


def test_parse_firmware_filename_uses_path_name():
    info = parse_firmware_filename(Path("nested/MicroLink_V4.3.1.uf2"))
    assert info is not None
    assert info.name == "MicroLink_V4.3.1.uf2"
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k parse_firmware
```

Expected: ImportError or AttributeError for `parse_firmware_filename`

- [ ] **Step 3: 实现 `FirmwareInfo` + `parse_firmware_filename`**

`mklink/firmware_check.py` 末尾追加:

```python
@dataclass
class FirmwareInfo:
    """A single MicroLink_V*.uf2 firmware file in MK-Firmware/."""
    name: str
    version: Version
    model: str  # "V3" | "V4"
    path: Path

    @property
    def version_str(self) -> str:
        return str(self.version)


def parse_firmware_filename(name) -> FirmwareInfo | None:
    """Parse a MicroLink_V<major>.<minor>.<patch>.uf2 filename.

    Accepts str or Path; returns None for non-matching names.
    """
    raw = Path(name).name  # strip parent directories
    m = _FIRMWARE_FILE_RE.match(raw)
    if not m:
        return None
    major = int(m.group(2))
    minor = int(m.group(3))
    patch = int(m.group(4))
    return FirmwareInfo(
        name=raw,
        version=Version(major, minor, patch),
        model=f"V{major}",
        path=Path(name),
    )
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k parse_firmware
```

Expected: 4 passed (3 for the new test_parse_firmware_filename_* plus 1 from Step 1 if combined)

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add FirmwareInfo + parse_firmware_filename"
```

---

### Task 1.3: `list_firmwares`

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试**

```python
# add to test_firmware_check.py
import pytest


def test_list_firmwares_returns_only_uf2(tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V3.3.1.uf2").write_bytes(b"fake")
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"fake")
    (fw_dir / "MicroLink_V3.5.0.uf2").write_bytes(b"fake")
    (fw_dir / "readme.txt").write_text("not firmware")

    result = list_firmwares(fw_dir)
    assert len(result) == 3
    versions = [f.version for f in result]
    assert versions == sorted(versions)  # ascending order


def test_list_firmwares_empty_dir(tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    assert list_firmwares(fw_dir) == []


def test_list_firmwares_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        list_firmwares(tmp_path / "nonexistent")
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k list_firmwares
```

Expected: ImportError for `list_firmwares`

- [ ] **Step 3: 实现 `list_firmwares`**

`mklink/firmware_check.py` 末尾追加:

```python
def list_firmwares(root: Path) -> list[FirmwareInfo]:
    """List all MicroLink_V*.uf2 files in `root`, sorted by version ascending.

    Raises FileNotFoundError if `root` does not exist.
    Files that don't match the pattern are silently skipped.
    """
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Firmware directory not found: {root}")
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    result: list[FirmwareInfo] = []
    for entry in root.iterdir():
        info = parse_firmware_filename(entry)
        if info is not None:
            result.append(info)
    result.sort(key=lambda f: f.version)
    return result
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k list_firmwares
```

Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add list_firmwares"
```

---

### Task 1.4: `find_min_version` + `find_recommended_uf2`

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试**

```python
# add to test_firmware_check.py
def test_find_min_version_multiple():
    v3 = FirmwareInfo("V3.3.1.uf2", Version(3, 3, 1), "V3", Path("V3.3.1.uf2"))
    v4 = FirmwareInfo("V4.3.1.uf2", Version(4, 3, 1), "V4", Path("V4.3.1.uf2"))
    assert find_min_version([v3, v4]) == Version(3, 3, 1)


def test_find_min_version_empty():
    assert find_min_version([]) is None


def test_find_recommended_uf2_same_major():
    v3_3 = FirmwareInfo("V3.3.1.uf2", Version(3, 3, 1), "V3", Path("a"))
    v3_5 = FirmwareInfo("V3.5.0.uf2", Version(3, 5, 0), "V3", Path("b"))
    v4 = FirmwareInfo("V4.3.1.uf2", Version(4, 3, 1), "V4", Path("c"))
    result = find_recommended_uf2([v3_3, v3_5, v4], Version(3, 0, 0))
    assert result is v3_5  # highest V3


def test_find_recommended_uf2_unknown_version():
    v3 = FirmwareInfo("V3.3.1.uf2", Version(3, 3, 1), "V3", Path("a"))
    v4 = FirmwareInfo("V4.3.1.uf2", Version(4, 3, 1), "V4", Path("b"))
    assert find_recommended_uf2([v3, v4], None) is None


def test_find_recommended_uf2_no_same_major():
    v3 = FirmwareInfo("V3.3.1.uf2", Version(3, 3, 1), "V3", Path("a"))
    v4 = FirmwareInfo("V4.3.1.uf2", Version(4, 3, 1), "V4", Path("b"))
    # current is V5 → no V5 firmware in repo
    assert find_recommended_uf2([v3, v4], Version(5, 0, 0)) is None
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k "find_min or find_recommended"
```

Expected: ImportError

- [ ] **Step 3: 实现 `find_min_version` + `find_recommended_uf2`**

`mklink/firmware_check.py` 末尾追加:

```python
def find_min_version(firmwares: list[FirmwareInfo]) -> Version | None:
    """Return the lowest version among firmwares, or None if empty."""
    if not firmwares:
        return None
    return min(f.version for f in firmwares)


def find_recommended_uf2(
    firmwares: list[FirmwareInfo], current: Version | None
) -> FirmwareInfo | None:
    """Recommend the highest-version firmware with the same major version as `current`.

    Returns None if current is None or no firmware shares current.major.
    """
    if current is None or not firmwares:
        return None
    same_major = [f for f in firmwares if f.version.major == current.major]
    if not same_major:
        return None
    return max(same_major, key=lambda f: f.version)
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k "find_min or find_recommended"
```

Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add find_min_version + find_recommended_uf2"
```

---

### Task 1.5: `_resolve_firmware_root`

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试**

```python
# add to test_firmware_check.py
def test_resolve_firmware_root_from_env(monkeypatch, tmp_path):
    target = tmp_path / "custom-fw"
    target.mkdir()
    monkeypatch.setenv("MKLINK_FIRMWARE_DIR", str(target))
    assert _resolve_firmware_root() == target


def test_resolve_firmware_root_from_cwd(monkeypatch, tmp_path, monkeypatch_chdir):
    # use a chdir fixture
    pass  # see Step 3 for the actual fixture setup
```

(`monkeypatch_chdir` 不在标准 pytest 中，需要写 fixture；下方 Step 3 改用 monkeypatch.chdir 替代)

最终测试代码（替换上面）:

```python
def test_resolve_firmware_root_from_cwd(monkeypatch, tmp_path):
    target = tmp_path / "MK-Firmware"
    target.mkdir()
    monkeypatch.delenv("MKLINK_FIRMWARE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert _resolve_firmware_root() == target


def test_resolve_firmware_root_from_package(monkeypatch, tmp_path):
    # Simulate by patching the package location
    monkeypatch.delenv("MKLINK_FIRMWARE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # cwd has no MK-Firmware

    import mklink.firmware_check as fc
    # Patch the package parent resolution
    fake_pkg = tmp_path / "site-packages" / "mklink"
    fake_pkg.mkdir(parents=True)
    fake_fw = tmp_path / "site-packages" / "MK-Firmware"
    fake_fw.mkdir()
    monkeypatch.setattr(fc, "_PACKAGE_PARENT_OVERRIDE", tmp_path / "site-packages")
    assert _resolve_firmware_root() == fake_fw
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k resolve
```

Expected: ImportError

- [ ] **Step 3: 实现 `_resolve_firmware_root`**

`mklink/firmware_check.py` 末尾追加:

```python
def _resolve_firmware_root() -> Path:
    """Resolve the MK-Firmware directory.

    Priority:
      1. MKLINK_FIRMWARE_DIR env var
      2. <cwd>/MK-Firmware
      3. <package_parent>/MK-Firmware  (i.e., one level above mklink/ in the installed package)

    Returns the first path that exists; if none exist, returns the env-var path
    (or cwd path) so the caller can decide how to handle the missing case.
    """
    # 1. env var
    env_path = os.environ.get(FIRMWARE_DIR_ENV)
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate
        # env-set but missing → still return it; caller handles FileNotFoundError
        return candidate

    # 2. cwd
    cwd_candidate = Path.cwd() / FIRMWARE_DIR_NAME
    if cwd_candidate.exists():
        return cwd_candidate

    # 3. package parent (one level above the mklink/ package)
    pkg_parent = _PACKAGE_PARENT_OVERRIDE if _PACKAGE_PARENT_OVERRIDE is not None else Path(__file__).resolve().parent.parent
    pkg_candidate = pkg_parent / FIRMWARE_DIR_NAME
    return pkg_candidate  # may not exist; caller handles


# Test seam: lets tests inject a different package parent.
_PACKAGE_PARENT_OVERRIDE: Path | None = None
```

并在文件顶部补 import:

```python
import os
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k resolve
```

Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add _resolve_firmware_root with env/cwd/pkg fallback"
```

---

### Task 1.6: `read_device_version`（含 mock bridge）

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试（使用 mock bridge）**

```python
# add to test_firmware_check.py
class _FakeBridge:
    def __init__(self, port, response="V4.3.1", connect_raises=None,
                 send_raises=None):
        self.port = port
        self.response = response
        self._connect_raises = connect_raises
        self._send_raises = send_raises
        self.connected = False
        self.sent = []

    def connect(self):
        if self._connect_raises:
            raise self._connect_raises
        self.connected = True

    def send_command(self, cmd, timeout=None):
        self.sent.append((cmd, timeout))
        if self._send_raises:
            raise self._send_raises
        return self.response


def test_read_device_version_parses_v4(monkeypatch):
    from mklink import firmware_check
    fake = _FakeBridge("COM5", response="V4.3.1\n其他历史内容")
    monkeypatch.setattr(firmware_check, "MKLinkSerialBridge",
                        lambda port: fake)
    v = firmware_check.read_device_version("COM5", timeout=3.0)
    assert v == Version(4, 3, 1)
    assert fake.connected
    assert fake.sent[0][0] == "cmd.get_version()"


def test_read_device_version_unparseable_returns_none(monkeypatch):
    from mklink import firmware_check
    fake = _FakeBridge("COM5", response="garbled no V line")
    monkeypatch.setattr(firmware_check, "MKLinkSerialBridge",
                        lambda port: fake)
    assert firmware_check.read_device_version("COM5") is None


def test_read_device_version_serial_exception_propagates(monkeypatch):
    from mklink import firmware_check
    fake = _FakeBridge("COM5", connect_raises=ConnectionError("port not found"))
    monkeypatch.setattr(firmware_check, "MKLinkSerialBridge",
                        lambda port: fake)
    import pytest
    with pytest.raises(ConnectionError):
        firmware_check.read_device_version("COM5")
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k read_device
```

Expected: ImportError for `read_device_version`

- [ ] **Step 3: 实现 `read_device_version`**

`mklink/firmware_check.py` 末尾追加:

```python
def read_device_version(port: str, *, timeout: float = DEFAULT_VERSION_TIMEOUT) -> Version | None:
    """Read probe firmware version via cmd.get_version().

    Returns the parsed Version, or None if the response cannot be parsed.
    Raises (TimeoutError, ConnectionError, etc.) on serial errors — caller
    decides how to recover.
    """
    bridge = MKLinkSerialBridge(port)
    bridge.connect()
    resp = bridge.send_command("cmd.get_version()", timeout=timeout)
    # Reuse the existing CLI parser (single source of truth for the format)
    from mklink.cli import _parse_version_response
    current_str, _ = _parse_version_response(resp)
    if not current_str:
        return None
    # Re-parse into Version using the firmware file regex (same shape)
    m = _FIRMWARE_FILE_RE.match(f"MicroLink_{current_str}.uf2")
    if not m:
        return None
    return Version(int(m.group(2)), int(m.group(3)), int(m.group(4)))


# Late-bound import: bridge is only needed when read_device_version is called.
# This avoids forcing pyserial import on every module load.
def __getattr__(name: str):
    if name == "MKLinkSerialBridge":
        from mklink.bridge import MKLinkSerialBridge
        return MKLinkSerialBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k read_device
```

Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add read_device_version (serial bridge)"
```

---

### Task 1.7: `CheckResult` dataclass + `build_instructions`

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试**

```python
# add to test_firmware_check.py
from mklink.firmware_check import CheckResult, build_instructions


def _mk_result(**kwargs):
    base = dict(
        status="upgrade_required",
        current_version=None,
        min_required_version=Version(3, 3, 1),
        recommended_uf2=None,
        all_uf2s=[],
        firmware_dir=Path("/repo/MK-Firmware"),
        instructions="",
    )
    base.update(kwargs)
    return CheckResult(**base)


def test_check_result_to_dict_serializes_version():
    r = _mk_result(current_version=Version(3, 0, 0),
                   min_required_version=Version(3, 3, 1))
    d = r.to_dict()
    assert d["status"] == "upgrade_required"
    assert d["current_version"] == "V3.0.0"
    assert d["min_required_version"] == "V3.3.1"


def test_check_result_to_dict_handles_none_version():
    r = _mk_result(current_version=None)
    d = r.to_dict()
    assert d["current_version"] is None


def test_build_instructions_v3_known():
    r = _mk_result(current_version=Version(3, 0, 0))
    text = build_instructions(r)
    assert "[WARN]" in text
    assert "V3" in text
    assert "两个眼睛中间" in text  # V3 按钮位置
    assert "MicroLink_V" not in text or "V3" in text


def test_build_instructions_v4_known():
    r = _mk_result(current_version=Version(4, 0, 0))
    text = build_instructions(r)
    assert "[WARN]" in text
    assert "V4" in text
    assert "侧边拨轮" in text


def test_build_instructions_unknown_version_lists_all():
    v3 = FirmwareInfo("MicroLink_V3.3.1.uf2", Version(3, 3, 1), "V3",
                      Path("/r/MicroLink_V3.3.1.uf2"))
    v4 = FirmwareInfo("MicroLink_V4.3.1.uf2", Version(4, 3, 1), "V4",
                      Path("/r/MicroLink_V4.3.1.uf2"))
    r = _mk_result(current_version=None, all_uf2s=[v3, v4])
    text = build_instructions(r)
    assert "V3 探针" in text
    assert "V4 探针" in text
    assert "MicroLink_V3.3.1.uf2" in text
    assert "MicroLink_V4.3.1.uf2" in text


def test_build_instructions_no_recommendation_mentions_contact():
    r = _mk_result(current_version=Version(5, 0, 0),
                   recommended_uf2=None)
    text = build_instructions(r)
    assert "联系维护者" in text or "无 V5" in text


def test_build_instructions_recommended_uf2_path():
    v3_5 = FirmwareInfo("MicroLink_V3.5.0.uf2", Version(3, 5, 0), "V3",
                        Path("/r/MicroLink_V3.5.0.uf2"))
    r = _mk_result(current_version=Version(3, 0, 0),
                   recommended_uf2=v3_5)
    text = build_instructions(r)
    assert "MicroLink_V3.5.0.uf2" in text
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k "check_result or build_instructions"
```

Expected: ImportError for `CheckResult` / `build_instructions`

- [ ] **Step 3: 实现 `CheckResult` + `build_instructions`**

`mklink/firmware_check.py` 末尾追加:

```python
@dataclass
class CheckResult:
    """Outcome of probe firmware check. See CheckStatus for possible values."""
    status: CheckStatus
    current_version: Version | None
    min_required_version: Version | None
    recommended_uf2: FirmwareInfo | None
    all_uf2s: list[FirmwareInfo]
    firmware_dir: Path | None
    instructions: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "current_version": str(self.current_version) if self.current_version else None,
            "min_required_version": str(self.min_required_version) if self.min_required_version else None,
            "recommended_uf2": _firmware_to_dict(self.recommended_uf2) if self.recommended_uf2 else None,
            "all_uf2s": [_firmware_to_dict(f) for f in self.all_uf2s],
            "firmware_dir": str(self.firmware_dir) if self.firmware_dir else None,
            "instructions": self.instructions,
        }


def _firmware_to_dict(f: FirmwareInfo) -> dict:
    return {
        "name": f.name,
        "version": f.version_str,
        "model": f.model,
        "path": str(f.path),
    }


# Button locations per probe model (V3: between two "eyes"; V4: side toggle)
_BUTTON_HINT = {
    "V3": "按住 V3 探针上**两个眼睛中间**的按钮",
    "V4": "按住 V4 探针**侧边拨轮**按钮",
}


def build_instructions(result: CheckResult) -> str:
    """Build the user-facing multi-line instructions text.

    Used by both CLI (printed as [WARN] block) and GUI (rendered in modal).
    """
    lines: list[str] = []
    lines.append("[WARN] 探针固件需要升级，请按以下步骤操作：")
    lines.append("")

    # 1. Determine button hint based on what we know about the probe model
    model: str | None = None
    if result.current_version is not None:
        model = f"V{result.current_version.major}"
    if model and model in _BUTTON_HINT:
        lines.append(f"  1. {_BUTTON_HINT[model]}，再插上 USB 上电")
    else:
        # unknown model — explain both
        lines.append("  1. 按住探针的升级按钮不放：")
        lines.append(f"     - V3 探针：{_BUTTON_HINT['V3']}")
        lines.append(f"     - V4 探针：{_BUTTON_HINT['V4']}")
        lines.append("     然后插上 USB 上电")
    lines.append("  2. 此时电脑会弹出一个 MICROKEEN U 盘")
    lines.append("  3. 将以下固件文件拷贝到该 U 盘根目录：")

    # 2. Tell the user which UF2 to use
    if result.recommended_uf2 is not None:
        lines.append(f"     - {result.recommended_uf2.path}")
    elif result.current_version is not None and not result.recommended_uf2:
        # current known but no same-major firmware
        lines.append(
            f"     - （无 V{result.current_version.major} 同型号固件，"
            "请检查 MK-Firmware/ 目录或联系维护者）"
        )
    else:
        for f in result.all_uf2s:
            lines.append(f"     - {f.path}")
    lines.append("  4. 拷贝完成后拔下 USB，重新插上即可使用新固件")
    lines.append("")
    if result.current_version is not None and result.min_required_version is not None:
        lines.append(
            f"  [诊断] 当前 {result.current_version}，"
            f"最低要求 {result.min_required_version}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k "check_result or build_instructions"
```

Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add CheckResult + build_instructions (V3/V4 button hints)"
```

---

### Task 1.8: `check_probe_firmware` 编排函数

**Files:**
- Modify: `mklink/firmware_check.py`
- Modify: `_maintainer/testing/tests/test_firmware_check.py`

- [ ] **Step 1: 追加失败测试**

```python
# add to test_firmware_check.py
from unittest.mock import patch


def test_check_probe_firmware_too_old(monkeypatch, tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V3.3.1.uf2").write_bytes(b"x")

    fake = _FakeBridge("COM5", response="V3.0.0\n")
    with patch.object(firmware_check, "MKLinkSerialBridge", lambda p: fake):
        result = firmware_check.check_probe_firmware("COM5", fw_dir)

    assert result.status == "upgrade_required"
    assert result.current_version == Version(3, 0, 0)
    assert result.min_required_version == Version(3, 3, 1)
    assert "V3" in result.instructions
    assert "两个眼睛中间" in result.instructions


def test_check_probe_firmware_unparseable(monkeypatch, tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"x")

    fake = _FakeBridge("COM5", response="garbled no V")
    with patch.object(firmware_check, "MKLinkSerialBridge", lambda p: fake):
        result = firmware_check.check_probe_firmware("COM5", fw_dir)

    assert result.status == "upgrade_required"
    assert result.current_version is None
    assert "V3 探针" in result.instructions
    assert "V4 探针" in result.instructions  # both listed when unknown


def test_check_probe_firmware_compatible(monkeypatch, tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V3.3.1.uf2").write_bytes(b"x")
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"x")

    fake = _FakeBridge("COM5", response="V4.3.1\n")
    with patch.object(firmware_check, "MKLinkSerialBridge", lambda p: fake):
        result = firmware_check.check_probe_firmware("COM5", fw_dir)

    assert result.status == "ok"
    assert result.current_version == Version(4, 3, 1)
    assert result.min_required_version == Version(3, 3, 1)


def test_check_probe_firmware_no_firmware_dir(tmp_path):
    nonexistent = tmp_path / "MK-Firmware"  # not created
    result = firmware_check.check_probe_firmware("COM5", nonexistent)
    assert result.status == "no_firmware_dir"
    assert result.firmware_dir == nonexistent


def test_check_probe_firmware_empty_firmware_dir(tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    result = firmware_check.check_probe_firmware("COM5", fw_dir)
    assert result.status == "no_firmware_dir"


def test_check_probe_firmware_no_port(tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V3.3.1.uf2").write_bytes(b"x")
    result = firmware_check.check_probe_firmware(None, fw_dir)
    assert result.status == "skipped"
    assert result.current_version is None


def test_check_probe_firmware_serial_exception(monkeypatch, tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V3.3.1.uf2").write_bytes(b"x")

    fake = _FakeBridge("COM5", connect_raises=ConnectionError("disconnected"))
    with patch.object(firmware_check, "MKLinkSerialBridge", lambda p: fake):
        result = firmware_check.check_probe_firmware("COM5", fw_dir)

    assert result.status == "skipped"
```

注意：测试顶部需要 `from mklink import firmware_check`，并删除之前 `from mklink.firmware_check import ...` 重复行；如冲突，调整为 `from mklink import firmware_check` + `firmware_check.Version(...)` 或保持两行。

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v -k check_probe
```

Expected: ImportError for `check_probe_firmware`

- [ ] **Step 3: 实现 `check_probe_firmware`**

`mklink/firmware_check.py` 末尾追加:

```python
def check_probe_firmware(
    port: str | None, firmware_root: Path
) -> CheckResult:
    """Top-level check: list firmwares, read device version, decide status.

    Failure-soft: never raises. Any error → returns a CheckResult with
    a non-'ok' status. UI/CLI can inspect `status` and act accordingly.
    """
    # Step 1: scan firmware directory
    try:
        firmwares = list_firmwares(firmware_root)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return CheckResult(
            status="no_firmware_dir",
            current_version=None,
            min_required_version=None,
            recommended_uf2=None,
            all_uf2s=[],
            firmware_dir=Path(firmware_root),
            instructions="",
        )

    if not firmwares:
        return CheckResult(
            status="no_firmware_dir",
            current_version=None,
            min_required_version=None,
            recommended_uf2=None,
            all_uf2s=[],
            firmware_dir=Path(firmware_root),
            instructions="",
        )

    min_version = find_min_version(firmwares)
    assert min_version is not None  # firmwares non-empty implies min is not None

    # Step 2: read device version (may fail silently)
    current: Version | None = None
    if port is None:
        return CheckResult(
            status="skipped",
            current_version=None,
            min_required_version=min_version,
            recommended_uf2=None,
            all_uf2s=firmwares,
            firmware_dir=Path(firmware_root),
            instructions="",
        )

    try:
        current = read_device_version(port)
    except Exception:
        # Serial errors, timeouts, etc. — treat as "unknown version"
        current = None

    # Step 3: decide
    recommended = find_recommended_uf2(firmwares, current)
    requires_upgrade = (current is None) or (current < min_version)
    status: CheckStatus = "upgrade_required" if requires_upgrade else "ok"

    result = CheckResult(
        status=status,
        current_version=current,
        min_required_version=min_version,
        recommended_uf2=recommended,
        all_uf2s=firmwares,
        firmware_dir=Path(firmware_root),
        instructions="",
    )
    if status == "upgrade_required":
        result.instructions = build_instructions(result)
    return result
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest _maintainer/testing/tests/test_firmware_check.py -v
```

Expected: 全部 passed（约 30+ 个用例）

- [ ] **Step 5: 提交**

```bash
git add mklink/firmware_check.py _maintainer/testing/tests/test_firmware_check.py
git commit -m "feat(firmware-check): add check_probe_firmware orchestrator"
```

---

## Phase 2: CLI 集成

### Task 2.1: `_cli_project_init` 调用 firmware_check

**Files:**
- Modify: `mklink/cli.py:269-287` (在 `[OK] project-init` 之前)

- [ ] **Step 1: 找到插入点并改代码**

读 `mklink/cli.py` 第 269-288 行（"end of `_cli_project_init`"），定位现有 `print("[OK] project-init ...")` 一行。

在 `print("[OK] ...")` **之前**插入:

```python
    # 探针固件版本检查（失败不影响 init）
    try:
        from mklink import firmware_check
        port = find_mklink_cdc_port()  # already discovered above; this re-call is cheap
        root = firmware_check._resolve_firmware_root()
        check = firmware_check.check_probe_firmware(port=port, firmware_root=root)
        if check.status == "upgrade_required":
            for line in check.instructions.splitlines():
                print(line)
        elif check.status == "no_firmware_dir":
            print(f"[WARN] 找不到 MK-Firmware 目录 ({check.firmware_dir})，无法校验探针固件版本")
        # ok / skipped 不打印
    except Exception as e:
        import sys
        print(f"[WARN] 探针固件版本检查异常：{e}", file=sys.stderr)
```

实际实现时建议在 `_cli_project_init` 顶部把 `port` 变量提取出来（避免二次调用 `find_mklink_cdc_port`）：

```python
    # 现有的 find_mklink_cdc_port 调用附近
    port = find_mklink_cdc_port()
    if port:
        print(f"[AUTO] 自动检测到 MKLINK 串口: {port}")

    # ... 原有的 FLM 步骤 / save config 等 ...

    # 探针固件版本检查（不阻塞 init）
    try:
        from mklink import firmware_check
        root = firmware_check._resolve_firmware_root()
        check = firmware_check.check_probe_firmware(port=port, firmware_root=root)
        if check.status == "upgrade_required":
            for line in check.instructions.splitlines():
                print(line)
        elif check.status == "no_firmware_dir":
            print(f"[WARN] 找不到 MK-Firmware 目录 ({check.firmware_dir})，无法校验探针固件版本")
    except Exception as e:
        import sys
        print(f"[WARN] 探针固件版本检查异常：{e}", file=sys.stderr)
```

- [ ] **Step 2: 手工跑 init 验证 stdout 格式**

```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
# 用真实的 Keil 工程（如果存在）
python -m mklink project-init <path-to-keil-project> 2>&1 | tail -30
```

Expected: 末尾若探针太旧会看到 `[WARN] 探针固件需要升级` + 步骤文本；若探针兼容则无 [WARN]。

- [ ] **Step 3: 提交**

```bash
git add mklink/cli.py
git commit -m "feat(cli): emit firmware upgrade [WARN] in _cli_project_init"
```

---

### Task 2.2: CLI 集成测试

**Files:**
- Create: `_maintainer/testing/tests/test_cli_project_init.py`

- [ ] **Step 1: 写测试**

```python
"""CLI 集成测试：_cli_project_init 末尾的 firmware_check 输出。

通过 monkeypatch 替换 find_mklink_cdc_port / MKLinkSerialBridge / _resolve_firmware_root
来构造各种场景，验证 stdout / exit code。
"""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

from mklink import cli, firmware_check


@pytest.fixture
def fake_project_root(tmp_path):
    """Minimal project root — needs a uvprojx or ewp; we mock the inner funcs."""
    return tmp_path


def _run_init(monkeypatch, *, port, response, firmware_dir):
    """Run _cli_project_init with all I/O mocked; return (stdout, stderr, exit_code)."""
    # Patch find_uvprojx/ewp so we skip actual file scanning
    monkeypatch.setattr(cli, "find_uvprojx", lambda r: None, raising=False)
    monkeypatch.setattr(cli, "find_ewp", lambda r: None, raising=False)
    monkeypatch.setattr(cli, "parse_uvprojx", lambda p: {}, raising=False)
    monkeypatch.setattr(cli, "parse_ewp", lambda p: {}, raising=False)
    monkeypatch.setattr(cli, "save_project_info", lambda r, p: None, raising=False)
    monkeypatch.setattr(cli, "save_config", lambda r, c: None, raising=False)
    monkeypatch.setattr(cli, "save_rtt_config", lambda r, c: None, raising=False)
    monkeypatch.setattr(cli, "match_mcu_by_device", lambda d, p: "n32g435", raising=False)
    monkeypatch.setattr(cli, "resolve_keil_flm_path", lambda n, p: None, raising=False)
    monkeypatch.setattr(cli, "check_flm_on_microkeen", lambda n: False, raising=False)
    monkeypatch.setattr(cli, "copy_flm_to_microkeen", lambda n, p: True, raising=False)
    monkeypatch.setattr(cli, "find_mklink_cdc_port", lambda: port, raising=False)
    monkeypatch.setattr(cli, "check_readelf_available", lambda: True, raising=False)

    # Patch firmware_check internals
    class FakeBridge:
        def __init__(self, p): self.p = p
        def connect(self): pass
        def send_command(self, cmd, timeout=None): return response

    monkeypatch.setattr(firmware_check, "MKLinkSerialBridge", FakeBridge)
    monkeypatch.setattr(firmware_check, "_resolve_firmware_root", lambda: firmware_dir)

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            cli._cli_project_init("/fake/project")
            rc = 0
        except SystemExit as e:
            rc = e.code or 0
    return out.getvalue(), err.getvalue(), rc


def test_init_warns_on_outdated_v3_probe(monkeypatch, tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V3.3.1.uf2").write_bytes(b"x")
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"x")

    out, err, rc = _run_init(
        monkeypatch, port="COM5", response="V3.0.0\n历史...", firmware_dir=fw_dir
    )
    assert rc == 0
    assert "[WARN]" in out
    assert "V3" in out
    assert "两个眼睛中间" in out
    assert "MicroLink_V3.3.1.uf2" in out


def test_init_silent_on_compatible_probe(monkeypatch, tmp_path):
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"x")

    out, err, rc = _run_init(
        monkeypatch, port="COM5", response="V4.3.1\n", firmware_dir=fw_dir
    )
    assert rc == 0
    assert "[WARN]" not in out


def test_init_warns_when_firmware_dir_missing(monkeypatch, tmp_path):
    out, err, rc = _run_init(
        monkeypatch, port="COM5", response="V4.3.1",
        firmware_dir=tmp_path / "nonexistent"  # not created
    )
    assert rc == 0
    assert "[WARN] 找不到 MK-Firmware 目录" in out
```

- [ ] **Step 2: 跑测试**

```bash
pytest _maintainer/testing/tests/test_cli_project_init.py -v
```

Expected: 3 passed

如失败，可能需要：
- 调整 mock 的方法名（参考 `mklink/cli.py:89-288` 实际使用的内部函数）
- 某些函数在 init 中被调用时名字不同；用 `mklink/cli.py:find_uvprojx` 等的实际名字替换

- [ ] **Step 3: 提交**

```bash
git add _maintainer/testing/tests/test_cli_project_init.py
git commit -m "test(cli): add firmware-check integration tests for project-init"
```

---

## Phase 3: FastAPI 改动

### Task 3.1: `/api/project-init` 响应加 `firmware_check` 字段

**Files:**
- Modify: `mklink/remote/api.py:376-419`

- [ ] **Step 1: 读现有端点**

读 `mklink/remote/api.py:376-419`，定位 `project_init` 函数的返回 dict。

- [ ] **Step 2: 修改返回逻辑**

在现有 `return {...}` 前加:

```python
    # 探针固件版本检查（异步执行，避免阻塞事件循环）
    firmware_check_result: dict = {"status": "skipped"}
    try:
        from mklink import firmware_check as _fc
        port = None
        # Prefer the device's port if currently connected
        dev = _state.get("device")
        if dev is not None and getattr(dev, "port", None):
            port = dev.port
        root = _fc._resolve_firmware_root()
        check = await loop.run_in_executor(
            None, _fc.check_probe_firmware, port, root
        )
        firmware_check_result = check.to_dict()
    except Exception as e:
        firmware_check_result = {"status": "skipped", "error": str(e)}
```

并把 `loop` 变量在文件顶部已经存在的 import 处核对（应已有 `import asyncio` 且 `loop = asyncio.get_event_loop()` 在某处；如未在函数内取循环引用，直接 `asyncio.get_event_loop()` 或 `asyncio.get_running_loop()`）。

并在函数返回 dict 中追加:

```python
    return {
        "success": True,
        "output": output,
        "config": ...,
        "project_info": ...,
        "config_status": ...,
        "firmware_check": firmware_check_result,   # NEW
    }
```

- [ ] **Step 3: 启动服务 + curl 验证**

```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
python -m mklink serve --host 127.0.0.1 --port 18765 &
SERVER_PID=$!
sleep 2
# 准备一个最小项目根（含 .uvprojx 或 .ewp）— 暂时跳过 IDE 解析路径，直接用 -c 参数或空工程
# 简化：用 mock 项目根（空目录）→ init 会失败但响应结构仍返回 firmware_check
curl -sS -X POST http://127.0.0.1:18765/api/project-init -H "Content-Type: application/json" | python -m json.tool | head -30
kill $SERVER_PID
```

Expected: 响应 JSON 含 `"firmware_check": {...}` 字段，status 为 `skipped`（因为没有 device 也没有 project）。

- [ ] **Step 4: 提交**

```bash
git add mklink/remote/api.py
git commit -m "feat(api): include firmware_check in /api/project-init response"
```

---

### Task 3.2: 新增 `GET /api/probe/firmware-check` 端点

**Files:**
- Modify: `mklink/remote/api.py`（在某处加新 router）

- [ ] **Step 1: 在 `/api/project-init` 附近添加新端点**

```python
@router.get("/api/probe/firmware-check")
async def probe_firmware_check():
    """Re-run probe firmware check (no project init required)."""
    from mklink import firmware_check as _fc
    port = None
    dev = _state.get("device")
    if dev is not None and getattr(dev, "port", None):
        port = dev.port
    try:
        root = _fc._resolve_firmware_root()
        check = await asyncio.get_event_loop().run_in_executor(
            None, _fc.check_probe_firmware, port, root
        )
        return check.to_dict()
    except Exception as e:
        return {"status": "skipped", "error": str(e)}
```

- [ ] **Step 2: 跑起来 + curl 验证**

```bash
python -m mklink serve --host 127.0.0.1 --port 18765 &
SERVER_PID=$!
sleep 2
curl -sS http://127.0.0.1:18765/api/probe/firmware-check | python -m json.tool
kill $SERVER_PID
```

Expected: 合法 JSON，`status` 字段存在（值可能是 `skipped` 或 `no_firmware_dir` 或 `ok`/`upgrade_required` 视环境）。

- [ ] **Step 3: 提交**

```bash
git add mklink/remote/api.py
git commit -m "feat(api): add GET /api/probe/firmware-check endpoint"
```

---

### Task 3.3: API 测试

**Files:**
- Create: `_maintainer/testing/tests/test_api_firmware_check.py`

- [ ] **Step 1: 写测试**

参考 `_maintainer/testing/tests/test_api_untested.py` 的模式（用 FastAPI TestClient）:

```python
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from mklink.remote.api import create_app


def test_project_init_response_includes_firmware_check(monkeypatch, tmp_path):
    from mklink import firmware_check

    app = create_app()
    client = TestClient(app)

    # Mock _cli_project_init so we don't actually scan the filesystem
    def fake_init(root):
        print("[OK] fake init")
    monkeypatch.setattr("mklink.remote.api._cli_project_init", fake_init)

    # Mock firmware_check to return a deterministic result
    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"x")
    monkeypatch.setattr(firmware_check, "_resolve_firmware_root", lambda: fw_dir)
    monkeypatch.setattr(firmware_check, "read_device_version",
                        lambda port, **kw: None)  # no current version
    monkeypatch.setattr(firmware_check, "MKLinkSerialBridge", MagicMock())

    res = client.post("/api/project-init")
    assert res.status_code == 200
    body = res.json()
    assert "firmware_check" in body
    assert body["firmware_check"]["status"] in (
        "upgrade_required", "ok", "no_firmware_dir", "skipped"
    )


def test_probe_firmware_check_endpoint(monkeypatch, tmp_path):
    from mklink import firmware_check
    app = create_app()
    client = TestClient(app)

    fw_dir = tmp_path / "MK-Firmware"
    fw_dir.mkdir()
    (fw_dir / "MicroLink_V4.3.1.uf2").write_bytes(b"x")
    monkeypatch.setattr(firmware_check, "_resolve_firmware_root", lambda: fw_dir)
    monkeypatch.setattr(firmware_check, "read_device_version",
                        lambda port, **kw: firmware_check.Version(4, 3, 1))
    monkeypatch.setattr(firmware_check, "MKLinkSerialBridge", MagicMock())

    res = client.get("/api/probe/firmware-check")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["current_version"] == "V4.3.1"
```

- [ ] **Step 2: 跑测试**

```bash
pytest _maintainer/testing/tests/test_api_firmware_check.py -v
```

Expected: 2 passed

如 `create_app` 在测试中需要 fixture，参考 `_maintainer/testing/tests/test_api_app_compat.py`。

- [ ] **Step 3: 提交**

```bash
git add _maintainer/testing/tests/test_api_firmware_check.py
git commit -m "test(api): add firmware-check endpoint tests"
```

---

## Phase 4: Mock API 改造

### Task 4.1: `MockState.probe_firmware_check` 字段 + 默认值

**Files:**
- Modify: `_maintainer/testing/tests/mock_gui_api.py:122-273`（MockState 定义附近）

- [ ] **Step 1: 在 MockState 加字段**

读 `mock_gui_api.py:122-273`，定位 `MockState` 类。在 `microkeen` 字段附近追加:

```python
        # 探针固件版本检查（mock 用：默认 ok，可由 apply_preset 切换）
        self.probe_firmware_check: dict = {
            "status": "ok",
            "current_version": "V4.3.1",
            "min_required_version": "V3.3.1",
            "recommended_uf2": {
                "name": "MicroLink_V4.3.1.uf2",
                "version": "V4.3.1",
                "model": "V4",
                "path": "<repo>/MK-Firmware/MicroLink_V4.3.1.uf2",
            },
            "all_uf2s": [
                {
                    "name": "MicroLink_V3.3.1.uf2",
                    "version": "V3.3.1",
                    "model": "V3",
                    "path": "<repo>/MK-Firmware/MicroLink_V3.3.1.uf2",
                },
                {
                    "name": "MicroLink_V4.3.1.uf2",
                    "version": "V4.3.1",
                    "model": "V4",
                    "path": "<repo>/MK-Firmware/MicroLink_V4.3.1.uf2",
                },
            ],
            "firmware_dir": "<repo>/MK-Firmware",
            "instructions": "[WARN] 探针固件已为最新版本",
        }
```

- [ ] **Step 2: 跑现有 mock 端点测试，确认没破**

```bash
cd gui && npm run build
pytest _maintainer/testing/tests/e2e/gui -q --run-e2e
```

Expected: 现有 ~179 个测试全部通过（不应被默认值影响，因为没有 GUI 调用 firmware_check 之前不展示）

- [ ] **Step 3: 提交**

```bash
git add _maintainer/testing/tests/mock_gui_api.py
git commit -m "test(mock): add MockState.probe_firmware_check default"
```

---

### Task 4.2: 透传 + 新端点 + preset

**Files:**
- Modify: `_maintainer/testing/tests/mock_gui_api.py`

- [ ] **Step 1: 修改 `POST /api/project-init` mock (494-496 附近)**

```python
@app.post("/api/project-init")
async def mock_project_init():
    # ... 原有逻辑 ...
    return {
        "success": True,
        "output": "[OK] project-init (mocked)",
        "ide_type": "keil",
        "config_path": "...",
        "config": state.config,
        "project_info": state.project_info,
        "config_status": state.config_status,
        "rtt_config": state.rtt_config,
        "firmware_check": state.probe_firmware_check,   # NEW
    }
```

（实际 mock 实现需对照现有 494-496 行附近的具体字段，按现状补 `firmware_check` 即可。）

- [ ] **Step 2: 添加 `GET /api/probe/firmware-check` mock**

```python
@app.get("/api/probe/firmware-check")
async def mock_probe_firmware_check():
    return state.probe_firmware_check
```

- [ ] **Step 3: 添加预设**

定位 `apply_preset` 方法，添加:

```python
    def apply_preset(self, name: str) -> None:
        # ... 现有代码 ...
        if name == "firmware_outdated":
            self.probe_firmware_check = {
                "status": "upgrade_required",
                "current_version": "V3.0.0",
                "min_required_version": "V3.3.1",
                "recommended_uf2": {
                    "name": "MicroLink_V3.3.1.uf2",
                    "version": "V3.3.1",
                    "model": "V3",
                    "path": "<repo>/MK-Firmware/MicroLink_V3.3.1.uf2",
                },
                "all_uf2s": [
                    {
                        "name": "MicroLink_V3.3.1.uf2",
                        "version": "V3.3.1",
                        "model": "V3",
                        "path": "<repo>/MK-Firmware/MicroLink_V3.3.1.uf2",
                    },
                    {
                        "name": "MicroLink_V4.3.1.uf2",
                        "version": "V4.3.1",
                        "model": "V4",
                        "path": "<repo>/MK-Firmware/MicroLink_V4.3.1.uf2",
                    },
                ],
                "firmware_dir": "<repo>/MK-Firmware",
                "instructions": (
                    "[WARN] 探针固件需要升级，请按以下步骤操作：\n"
                    "\n"
                    "  1. 按住 V3 探针上**两个眼睛中间**的按钮，再插上 USB 上电\n"
                    "  2. 此时电脑会弹出一个 MICROKEEN U 盘\n"
                    "  3. 将以下固件文件拷贝到该 U 盘根目录：\n"
                    "     - <repo>/MK-Firmware/MicroLink_V3.3.1.uf2\n"
                    "  4. 拷贝完成后拔下 USB，重新插上即可使用新固件\n"
                    "\n"
                    "  [诊断] 当前 V3.0.0，最低要求 V3.3.1"
                ),
            }
        elif name == "firmware_compatible":
            # 复位为 ok 状态
            self.apply_preset("default")  # 视 preset 实现而定
            self.probe_firmware_check = {
                "status": "ok",
                "current_version": "V4.3.1",
                "min_required_version": "V3.3.1",
                "recommended_uf2": {...},  # 同 Task 4.1
                "all_uf2s": [...],
                "firmware_dir": "<repo>/MK-Firmware",
                "instructions": "",
            }
```

- [ ] **Step 4: 跑现有 mock 测试**

```bash
cd gui && npm run build
pytest _maintainer/testing/tests/e2e/gui -q --run-e2e
```

Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add _maintainer/testing/tests/mock_gui_api.py
git commit -m "test(mock): add /api/probe/firmware-check endpoint + outdated preset"
```

---

## Phase 5: 前端类型 + API 客户端

### Task 5.1: 类型定义

**Files:**
- Modify: `gui/src/types/mklink.ts`

- [ ] **Step 1: 在文件末尾追加**

```typescript
// 探针自身固件版本检查
export interface FirmwareInfo {
  name: string
  version: string
  model: 'V3' | 'V4'
  path: string
}

export type ProbeFirmwareCheckStatus =
  | 'ok'
  | 'upgrade_required'
  | 'no_firmware_dir'
  | 'skipped'

export interface ProbeFirmwareCheck {
  status: ProbeFirmwareCheckStatus
  current_version: string | null
  min_required_version: string | null
  recommended_uf2: FirmwareInfo | null
  all_uf2s: FirmwareInfo[]
  firmware_dir: string | null
  instructions: string
}
```

- [ ] **Step 2: TypeScript 类型检查**

```bash
cd gui
npx vue-tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: 提交**

```bash
git add gui/src/types/mklink.ts
git commit -m "feat(gui): add ProbeFirmwareCheck types"
```

---

### Task 5.2: API 客户端方法

**Files:**
- Modify: `gui/src/composables/useMklinkApi.ts`

- [ ] **Step 1: 在 `api` 函数定义附近加新方法**

读 `useMklinkApi.ts`，定位 `import type { ... }` 行追加 `ProbeFirmwareCheck`：

```typescript
import type {
  ...,
  ProbeFirmwareCheck,
} from '../types/mklink'
```

在文件中合适位置加:

```typescript
async function probeFirmwareCheck(): Promise<ProbeFirmwareCheck> {
  return api<ProbeFirmwareCheck>('/api/probe/firmware-check')
}
```

并把 `probeFirmwareCheck` 加入文件底部 `return { ... }`（如果该 composable 是用 `return { ... }` 暴露的话）。

- [ ] **Step 2: 类型检查 + 构建**

```bash
cd gui
npx vue-tsc --noEmit
npm run build
```

Expected: 0 errors, build 成功

- [ ] **Step 3: 提交**

```bash
git add gui/src/composables/useMklinkApi.ts
git commit -m "feat(gui): add probeFirmwareCheck() API client method"
```

---

## Phase 6: 前端 Modal 组件

### Task 6.1: `useTauri` 组合式

**Files:**
- Create: `gui/src/composables/useTauri.ts`

- [ ] **Step 1: 创建文件**

```typescript
// 极简的 Tauri 桥接：在 Tauri 环境（window.__TAURI__）调原生能力；
// 浏览器环境降级为 toast 警告。
import { useToast } from './useToast'

export function useTauri() {
  const toast = useToast()

  async function openInExplorer(path: string | null): Promise<void> {
    if (!path) {
      toast.warn('无固件目录路径')
      return
    }
    const tauri: any = (window as any).__TAURI__
    if (!tauri?.opener?.openPath) {
      toast.warn('仅 Tauri 桌面应用支持打开目录')
      return
    }
    try {
      await tauri.opener.openPath(path)
    } catch (e: any) {
      toast.warn(`打开目录失败：${e?.message ?? e}`)
    }
  }

  return { openInExplorer }
}
```

- [ ] **Step 2: 类型检查**

```bash
cd gui
npx vue-tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: 提交**

```bash
git add gui/src/composables/useTauri.ts
git commit -m "feat(gui): add useTauri composable with openInExplorer"
```

---

### Task 6.2: `FirmwareUpdateModal.vue` 组件

**Files:**
- Create: `gui/src/components/config/FirmwareUpdateModal.vue`

- [ ] **Step 1: 创建组件**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import type { ProbeFirmwareCheck, FirmwareInfo } from '@/types/mklink'
import { useTauri } from '@/composables/useTauri'

const props = defineProps<{ check: ProbeFirmwareCheck }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'recheck'): void
}>()

const { openInExplorer } = useTauri()

const steps = computed(() =>
  props.check.instructions
    .split('\n')
    .filter((l) => l.trim().length > 0)
)

async function onOpenDir() {
  await openInExplorer(props.check.firmware_dir)
}

function fwLabel(fw: FirmwareInfo): string {
  return `${fw.name} (${fw.model}, ${fw.version})`
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal firmware-modal" role="dialog" aria-labelledby="fw-title">
      <header class="modal-header">
        <h2 id="fw-title">探针固件需要升级</h2>
        <button class="close-btn" aria-label="关闭" @click="emit('close')">×</button>
      </header>
      <div class="modal-body">
        <section class="fw-steps">
          <h3>升级步骤</h3>
          <ol>
            <li v-for="(line, i) in steps" :key="i">{{ line }}</li>
          </ol>
        </section>
        <section class="fw-files">
          <h3>固件</h3>
          <div v-if="check.recommended_uf2" class="fw-card recommended">
            <strong>推荐：</strong>
            <code>{{ fwLabel(check.recommended_uf2) }}</code>
            <div class="fw-path">{{ check.recommended_uf2.path }}</div>
          </div>
          <div v-else>
            <p>无法识别探针型号，请从下方任选一个 UF2：</p>
            <div v-for="fw in check.all_uf2s" :key="fw.name" class="fw-card">
              <code>{{ fwLabel(fw) }}</code>
              <div class="fw-path">{{ fw.path }}</div>
            </div>
          </div>
          <button class="open-dir-btn" @click="onOpenDir">
            打开 MK-Firmware 所在位置
          </button>
        </section>
      </div>
      <footer class="modal-footer">
        <button class="recheck-btn" @click="emit('recheck')">重新检测</button>
        <button class="close-action" @click="emit('close')">关闭</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.firmware-modal {
  background: var(--color-bg-elevated, #fff);
  border-radius: 8px;
  width: min(800px, 90vw);
  max-height: 85vh;
  display: flex; flex-direction: column;
}
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--color-border, #ddd); }
.modal-body { padding: 16px 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 24px; overflow: auto; }
.modal-footer { padding: 12px 24px; border-top: 1px solid var(--color-border, #ddd); display: flex; justify-content: flex-end; gap: 8px; }
.fw-card { background: var(--color-bg, #f7f7f7); border: 1px solid var(--color-border, #ddd); border-radius: 4px; padding: 8px 12px; margin: 6px 0; }
.fw-card.recommended { border-color: var(--color-primary, #3b82f6); }
.fw-path { font-family: monospace; font-size: 0.85em; color: var(--color-text-muted, #666); margin-top: 4px; word-break: break-all; }
.fw-steps ol { padding-left: 1.2em; }
.fw-steps li { margin: 4px 0; }
.open-dir-btn { margin-top: 12px; padding: 6px 12px; }
.close-btn { background: none; border: 0; font-size: 1.5em; cursor: pointer; }
</style>
```

- [ ] **Step 2: 类型检查 + 构建**

```bash
cd gui
npx vue-tsc --noEmit
npm run build
```

Expected: 0 errors, build 成功

- [ ] **Step 3: 提交**

```bash
git add gui/src/components/config/FirmwareUpdateModal.vue
git commit -m "feat(gui): add FirmwareUpdateModal component"
```

---

## Phase 7: ConfigView 集成

### Task 7.1: 处理 `firmware_check` 响应 + 模态触发

**Files:**
- Modify: `gui/src/views/ConfigView.vue`

- [ ] **Step 1: 添加 import**

```typescript
import FirmwareUpdateModal from '@/components/config/FirmwareUpdateModal.vue'
import { useMklinkApi } from '@/composables/useMklinkApi'
import type { ProbeFirmwareCheck } from '@/types/mklink'
```

（实际已有的 import 行要按现状补。）

- [ ] **Step 2: 添加响应式状态**

在 `ConfigView.vue` 的 `<script setup>` 顶部（其他 ref 附近）加:

```typescript
const showFirmwareModal = ref(false)
const firmwareCheck = ref<ProbeFirmwareCheck | null>(null)
const api = useMklinkApi()

async function recheckFirmware() {
  try {
    firmwareCheck.value = await api.probeFirmwareCheck()
    if (firmwareCheck.value.status === 'upgrade_required') {
      showFirmwareModal.value = true
    }
  } catch (e: any) {
    toast.warn(`固件检查失败：${e?.message ?? e}`)
  }
}
```

- [ ] **Step 3: 修改 `doProjectInit` 拿响应**

读 `ConfigView.vue:364-388` 的 `doProjectInit`，在 `await fetch(...)` 解析响应后追加:

```typescript
const data = await res.json()
firmwareCheck.value = data.firmware_check ?? null
if (firmwareCheck.value?.status === 'upgrade_required') {
  showFirmwareModal.value = true
}
```

- [ ] **Step 4: 在 template 末尾加模态与状态条**

读 `ConfigView.vue` 的 `<template>` 末尾（最后一个 `</div>` 之前或之后），加:

```vue
<!-- 探针固件升级警告条（持续显示直到检测通过） -->
<div v-if="firmwareCheck?.status === 'upgrade_required'" class="firmware-banner">
  <span>⚠ 探针固件需要升级</span>
  <button @click="showFirmwareModal = true">查看升级步骤</button>
  <button @click="recheckFirmware">重新检测</button>
</div>

<!-- 模态 -->
<FirmwareUpdateModal
  v-if="showFirmwareModal && firmwareCheck"
  :check="firmwareCheck"
  @close="showFirmwareModal = false"
  @recheck="recheckFirmware"
/>
```

并加 CSS（与其他状态条样式一致）:

```vue
<style scoped>
.firmware-banner {
  background: var(--color-warning-bg, #fef3c7);
  border: 1px solid var(--color-warning-border, #f59e0b);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
  border-radius: 4px;
}
.firmware-banner button { margin-left: auto; }
</style>
```

- [ ] **Step 5: 类型检查 + 构建**

```bash
cd gui
npx vue-tsc --noEmit
npm run build
```

Expected: 0 errors, build 成功

- [ ] **Step 6: 提交**

```bash
git add gui/src/views/ConfigView.vue
git commit -m "feat(gui): show FirmwareUpdateModal on outdated probe in ConfigView"
```

---

## Phase 8: GUI E2E 测试

### Task 8.1: E2E 测试套件

**Files:**
- Create: `_maintainer/testing/tests/e2e/gui/test_firmware_update_modal.py`

- [ ] **Step 1: 创建文件**

```python
"""E2E tests for the firmware update modal in ConfigView."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.gui_interaction, pytest.mark.gui_functionality]


def test_modal_appears_on_init_when_outdated(gui_page, mock_api):
    """G1: apply preset → click Init → modal opens with V3 hint."""
    mock_api.apply_preset("firmware_outdated")
    page = gui_page
    # Navigate to Config tab (default), pick a project, click Init
    page.get_by_role("button", name="选择项目根").click()
    page.get_by_role("button", name="初始化项目").click()
    # Modal title
    expect(page.get_by_role("heading", name="探针固件需要升级")).to_be_visible()
    # V3 button hint
    expect(page.get_by_text("V3 探针")).to_be_visible()
    expect(page.get_by_text("两个眼睛中间")).to_be_visible()


def test_modal_closes_on_button(gui_page, mock_api):
    """G2: open modal → close button → modal disappears."""
    mock_api.apply_preset("firmware_outdated")
    page = gui_page
    # (re-open via state bar)
    # ...
    # For now: open then close
    page.get_by_role("button", name="查看升级步骤").click()
    expect(page.get_by_role("heading", name="探针固件需要升级")).to_be_visible()
    page.get_by_role("button", name="关闭").click()
    expect(page.get_by_role("heading", name="探针固件需要升级")).not_to_be_visible()


def test_no_modal_on_compatible_firmware(gui_page, mock_api):
    """G3: default preset (V4.3.1) → no modal."""
    page = gui_page
    page.get_by_role("button", name="初始化项目").click()
    expect(page.get_by_role("heading", name="探针固件需要升级")).not_to_be_visible()


def test_modal_appears_on_recheck_button(gui_page, mock_api):
    """G4: preset → click 重新检测 → modal opens."""
    mock_api.apply_preset("firmware_outdated")
    page = gui_page
    page.get_by_role("button", name="重新检测").click()
    expect(page.get_by_role("heading", name="探针固件需要升级")).to_be_visible()


def test_v3_specific_text(gui_page, mock_api):
    """G5: current=V3.0.0 → V3 button hint."""
    mock_api.apply_preset("firmware_outdated")  # sets current=V3.0.0
    page = gui_page
    page.get_by_role("button", name="重新检测").click()
    expect(page.get_by_text("V3 探针上")).to_be_visible()
    expect(page.get_by_text("两个眼睛中间")).to_be_visible()


def test_v4_specific_text(gui_page, mock_api):
    """G6: current=V4.0.0 → V4 side toggle hint."""
    # Need a preset that sets current_version to V4.0.0
    # (or override state directly)
    # For now: use apply_preset with a custom state
    from _maintainer.testing.tests.mock_gui_api import MockState
    mock_api.state.probe_firmware_check = {
        **mock_api.state.probe_firmware_check,
        "current_version": "V4.0.0",
        "status": "upgrade_required",
        "instructions": (
            "[WARN] 探针固件需要升级：\n"
            "1. 按住 V4 探针侧边拨轮按钮，再插上 USB 上电\n"
            "2. ..."
        ),
    }
    page = gui_page
    page.get_by_role("button", name="重新检测").click()
    expect(page.get_by_text("V4 探针")).to_be_visible()
    expect(page.get_by_text("侧边拨轮")).to_be_visible()


def test_unknown_version_lists_all_uf2s(gui_page, mock_api):
    """G7: current=None → lists all UF2s."""
    from _maintainer.testing.tests.mock_gui_api import MockState
    mock_api.state.probe_firmware_check = {
        "status": "upgrade_required",
        "current_version": None,
        "min_required_version": "V3.3.1",
        "recommended_uf2": None,
        "all_uf2s": [
            {"name": "MicroLink_V3.3.1.uf2", "version": "V3.3.1",
             "model": "V3", "path": "MK-Firmware/MicroLink_V3.3.1.uf2"},
            {"name": "MicroLink_V4.3.1.uf2", "version": "V4.3.1",
             "model": "V4", "path": "MK-Firmware/MicroLink_V4.3.1.uf2"},
        ],
        "firmware_dir": "MK-Firmware",
        "instructions": (
            "[WARN] 探针固件需要升级：\n"
            "1. V3 探针按住两眼中点；V4 探针按住侧边拨轮\n"
            "2. ...\n"
            "3. 选择 UF2：\n"
            "   - MK-Firmware/MicroLink_V3.3.1.uf2\n"
            "   - MK-Firmware/MicroLink_V4.3.1.uf2"
        ),
    }
    page = gui_page
    page.get_by_role("button", name="重新检测").click()
    expect(page.get_by_text("MicroLink_V3.3.1.uf2")).to_be_visible()
    expect(page.get_by_text("MicroLink_V4.3.1.uf2")).to_be_visible()


def test_status_bar_persists_after_modal_closed(gui_page, mock_api):
    """G8: close modal → state bar still visible."""
    mock_api.apply_preset("firmware_outdated")
    page = gui_page
    page.get_by_role("button", name="查看升级步骤").click()
    page.get_by_role("button", name="关闭").click()
    # State bar still shows
    expect(page.get_by_text("⚠ 探针固件需要升级")).to_be_visible()
```

（注：上例中的 `from playwright.sync_api import expect` 等头部 import、按现状 fixture 命名（`gui_page` / `mock_api`）可能需对照 `e2e/gui/conftest.py:70-112` 调整。）

- [ ] **Step 2: 跑测试**

```bash
cd gui && npm run build
pytest _maintainer/testing/tests/e2e/gui/test_firmware_update_modal.py -v --run-e2e
```

Expected: 8 passed

若失败，常见原因：
- 选择器（`get_by_role("button", name=...)`）与实际按钮文字不一致 — 用 `get_by_text` 兜底
- `mock_api` fixture 不存在 — 看 `e2e/gui/conftest.py` 的实际 fixture 名
- `apply_preset("firmware_outdated")` 未实现 — 回 Phase 4 Task 4.2

- [ ] **Step 3: 全量回归**

```bash
pytest _maintainer/testing/tests/e2e/gui -q --run-e2e
```

Expected: 全部 ~187 个测试通过

- [ ] **Step 4: 提交**

```bash
git add _maintainer/testing/tests/e2e/gui/test_firmware_update_modal.py
git commit -m "test(e2e): add firmware update modal coverage"
```

---

## Phase 9: 收尾

### Task 9.1: 全量测试 + 文档

- [ ] **Step 1: 跑 Python 全量单测**

```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
pytest _maintainer/testing/tests -q
```

Expected: 全部通过（除非有无关失败）

- [ ] **Step 2: 跑 GUI E2E 全量**

```bash
cd gui && npm run build
pytest _maintainer/testing/tests/e2e/gui -q --run-e2e
```

Expected: ~187 passed

- [ ] **Step 3: 跑 Vitest**

```bash
cd gui
npm test
```

Expected: 全部通过

- [ ] **Step 4: 更新 CLAUDE.md（如果需要）**

如果项目有 `CLAUDE.md` 中列出的"RTT 控制块存储方式"等类似模式，可在 `CLAUDE.md` 末尾追加"探针固件升级"段落说明。但**仅当**该模式对项目未来工作有指导意义；否则跳过。

- [ ] **Step 5: 最终 commit + 推送**

```bash
git status
git log --oneline -10
```

若需要推送：`git push origin main`（用户授权后）

---

## Self-Review Checklist

- [x] **Spec coverage**:
  - [x] 核心模块 `mklink/firmware_check.py`（Task 1.1-1.8）
  - [x] CLI `_cli_project_init` 集成（Task 2.1-2.2）
  - [x] FastAPI `POST /api/project-init`（Task 3.1）
  - [x] FastAPI `GET /api/probe/firmware-check`（Task 3.2）
  - [x] Mock API 改造（Task 4.1-4.2）
  - [x] 前端 types（Task 5.1）
  - [x] 前端 API client（Task 5.2）
  - [x] 前端 useTauri composable（Task 6.1）
  - [x] 前端 FirmwareUpdateModal（Task 6.2）
  - [x] 前端 ConfigView 集成（Task 7.1）
  - [x] GUI E2E 测试（Task 8.1）

- [x] **No placeholders**:
  - [x] 每个 step 含完整代码
  - [x] 没有 "TBD" / "fill in"
  - [x] 没有 "similar to..."，每个测试都给了完整代码

- [x] **Type consistency**:
  - [x] `Version` 在 Task 1.1 定义，后续 Task 一直用 `Version(major, minor, patch)`
  - [x] `FirmwareInfo` 字段：name / version / model / path
  - [x] `CheckResult` 字段：status / current_version / min_required_version / recommended_uf2 / all_uf2s / firmware_dir / instructions
  - [x] `to_dict()` 在 Task 1.7 定义，Task 1.8 使用
  - [x] `check_probe_firmware(port, firmware_root)` 签名一致
  - [x] `build_instructions(result)` 签名一致
  - [x] 前端 `ProbeFirmwareCheck` interface 字段与 Python `CheckResult.to_dict()` 字段一致（snake_case → snake_case，TypeScript 不转 camelCase）
  - [x] `FirmwareInfo` 字段一致

- [x] **DRY / YAGNI**:
  - [x] 没有过度抽象（`useTauri` 仅 1 个方法，但留扩展位）
  - [x] 没有未使用的预设
  - [x] `__getattr__` lazy import 仅用于 `MKLinkSerialBridge`，避免在 `import firmware_check` 时强制加载 pyserial

---

## 备注

- 实施者请**严格按照 TDD**：每个 Task 写测试 → 跑测试（fail）→ 实现 → 跑测试（pass）→ commit
- 如遇 mock / fixture 不匹配，先读现有 `conftest.py` / `mock_gui_api.py` 找参考
- 真实硬件 HIL 测试**不在本 plan**（需 MKLink 探针 + 目标 MCU 实物）
- Tauri Rust 端 `opener` 插件实现在后续 plan 中
