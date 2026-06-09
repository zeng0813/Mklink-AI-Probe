# Probe Firmware Check on Init — Design Spec

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-09 |
| 触发需求 | 用户在 `MK-Firmware/` 下新增 MicroLink V3.3.1 / V4.3.1 固件；要求 `init` 时通过 `version` 命令读取探针版本，固件太旧则提示用户升级 |
| 范围 | GUI（ConfigView Init 按钮） + CLI（`python -m mklink project-init`） |
| 关联 Issue / 文档 | 仓库 `MK-Firmware/` 目录（`MicroLink_V3.3.1.uf2` / `MicroLink_V4.3.1.uf2`） |

---

## 1. Context（背景）

仓库根的 `MK-Firmware/` 目录存放了 MicroLink 烧录器自身的固件升级包（UF2 格式，RP2040 bootloader 拖拽升级），目前由维护者手工分发，无任何 Python 端入口列举、比对、推送给设备。

- `python -m mklink version`（`mklink/cli.py:983`）通过串口 `cmd.get_version()` 读取探针固件版本，但**仅限 CLI 只读**，不与 init 联动。
- `python -m mklink project-init`（`mklink/cli.py:89`）完成 Keil/IAR 工程解析、FLM 拷贝、MCU 匹配，**全程不检查探针自身固件版本**。
- GUI 端无 version/upgrade 任何 UI（`ConfigView.vue` 全 grep 零命中）。
- 当用户拿到一台老版本（不支持 `cmd.get_version()`）的探针时，init 表面上成功但后续功能可能不兼容——目前没有拦截。

**本 spec 目标**：把"探针固件版本检查"嵌入 init 流程，让用户在 init 阶段就被告知"探针固件太旧，请按步骤升级"，并在 GUI 中提供可视化的弹窗 + 步骤指引。

**预期结果**：
- CLI：`python -m mklink project-init` 在 init 成功后，若固件太旧/读不到版本 → 打印 `[WARN]` 多行指引，exit 0（init 本身仍成功）
- GUI：ConfigView 点击 Init 后，若固件太旧 → 弹出 `FirmwareUpdateModal`，含"按住 V3 两眼中点 / V4 侧边拨轮 + 插 USB + 拷 UF2"步骤

---

## 2. Design（设计）

### 2.1 架构

新增独立模块 `mklink/firmware_check.py`，CLI / FastAPI / GUI 共享：

```
mklink/
├── firmware_check.py        # 新增（核心，纯函数 + dataclass）
│   ├── Version              # dataclass(major, minor, patch)，__lt__ 支持
│   ├── FirmwareInfo         # dataclass(name, version_str, version: Version, model: 'V3'|'V4', path: Path)
│   ├── CheckResult          # dataclass
│   │     ├── status: 'ok'|'upgrade_required'|'no_firmware_dir'|'skipped'
│   │     ├── current_version: Version | None
│   │     ├── min_required_version: Version | None
│   │     ├── recommended_uf2: FirmwareInfo | None
│   │     ├── all_uf2s: list[FirmwareInfo]
│   │     ├── firmware_dir: Path | None
│   │     └── instructions: str     # 多行文本，CLI / GUI 共用
│   │
│   ├── _FIRMWARE_FILE_RE = re.compile(r"^MicroLink_(V(\d+)\.(\d+)\.(\d+))\.uf2$")
│   ├── _resolve_firmware_root() -> Path         # 优先级：env > cwd/MK-Firmware > package_root/MK-Firmware
│   ├── parse_firmware_filename(name: str) -> FirmwareInfo | None
│   ├── list_firmwares(root: Path) -> list[FirmwareInfo]
│   ├── find_min_version(firmwares: list[FirmwareInfo]) -> Version | None
│   ├── find_recommended_uf2(firmwares, current: Version | None) -> FirmwareInfo | None
│   ├── read_device_version(port: str, *, timeout: float = 5.0) -> Version | None
│   │     # 内部：MKLinkSerialBridge(port).connect() → send_command("cmd.get_version()")
│   │     # 内部：复用 cli._parse_version_response(cli.py:965)
│   ├── check_probe_firmware(port: str | None, firmware_root: Path) -> CheckResult
│   └── build_instructions(result: CheckResult) -> str
```

**CheckResult.status 四态**（穷举所有分支）：
- `ok` — 设备版本 ≥ 最低要求
- `upgrade_required` — 读不到版本 OR 设备版本 < 最低要求
- `no_firmware_dir` — `MK-Firmware/` 不存在或无匹配 UF2（环境问题，非探针问题）
- `skipped` — 串口未连接 / bridge 异常

### 2.2 组件改动清单

| 文件 | 类型 | 改动 |
|---|---|---|
| `mklink/firmware_check.py` | 新增 | 全部核心逻辑（约 200 行） |
| `mklink/cli.py` | 改 | `_cli_project_init` (89-288) 末尾在 `find_mklink_cdc_port` 后插入 check 调用；emit `[WARN]` 块 |
| `mklink/remote/api.py` | 改 | `POST /api/project-init` (376-419) 响应追加 `firmware_check` 字段（用 `run_in_executor` 包同步 check）；新增 `GET /api/probe/firmware-check`（同步版，给手动"重新检测"用） |
| `gui/src/composables/useMklinkApi.ts` | 改 | 新增 `probeFirmwareCheck(): Promise<ProbeFirmwareCheck>` |
| `gui/src/types/mklink.ts` | 改 | 新增 `FirmwareInfo` / `ProbeFirmwareCheck` 接口 |
| `gui/src/views/ConfigView.vue` | 改 | `doProjectInit` (364-388) 拿响应，状态条 + 模态触发 |
| `gui/src/components/config/FirmwareUpdateModal.vue` | 新增 | 模态组件：步骤、UF2 列表、"打开所在位置"按钮（Tauri 环境） |
| `gui/src/composables/useTauri.ts`（或同等位置 — 当前无此文件，可新建或附加到 `useMklinkApi.ts`） | 改或新增 | 新增 `openInExplorer(path)` 封装（Tauri `opener` 插件 / `window.__TAURI__.opener.openPath`；浏览器环境降级 toast） |
| `_maintainer/testing/tests/mock_gui_api.py` | 改 | `MockState.probe_firmware_check` 字段；`/api/project-init` 透传；新增 `GET /api/probe/firmware-check` mock；新增 `apply_preset("firmware_outdated"|"firmware_compatible")` |
| `_maintainer/testing/tests/test_firmware_check.py` | 新增 | 14 个单测（见 §2.5） |
| `_maintainer/testing/tests/e2e/gui/test_firmware_update_modal.py` | 新增 | GUI E2E 测试（见 §2.5） |

### 2.3 数据流

#### 2.3.1 CLI `project-init`

```
python -m mklink project-init [path]
  → mklink.cli._cli_project_init(project_root)         [cli.py:89]
     ├─ find_uvprojx / find_ewp
     ├─ parse_uvprojx / parse_ewp → save project_info
     ├─ match_mcu_by_device
     ├─ resolve_keil_flm_path → check/copy flm to microkeen
     ├─ find_mklink_cdc_port → port                     [cli.py:254]
     ├─ ★ firmware_check.check_probe_firmware(
     │      port=port,
     │      firmware_root=firmware_check._resolve_firmware_root())
     │   ├─ list_firmwares(<root>/MK-Firmware)         → [V3.3.1, V4.3.1]
     │   ├─ find_min_version(...)                       → V3.3.1
     │   ├─ read_device_version(port, timeout=5.0)
     │   │     ├─ MKLinkSerialBridge(port).connect()
     │   │     ├─ send_command("cmd.get_version()")
     │   │     └─ _parse_version_response → Version | None
     │   ├─ requires_upgrade = (current is None) OR (current < V3.3.1)
     │   ├─ find_recommended_uf2(...) → FirmwareInfo | None
     │   └─ build_instructions(...) → 多行 [WARN] 文本
     │
     ├─ if check.status == "upgrade_required":
     │     for line in check.instructions.splitlines(): print(line)
     │
     └─ print("[OK] project-init 完成")                  # 仍 exit 0
```

#### 2.3.2 FastAPI `POST /api/project-init`（含 check）

```
GUI: ConfigView.doProjectInit()
  └─ fetch('/api/project-init', POST)                   [ConfigView.vue:373]
        → api.project_init()                            [api.py:376]
           ├─ redirect_stdout 捕获 _cli_project_init 输出
           ├─ loop.run_in_executor(_cli_project_init, project_root)
           ├─ ★ firmware_check_task = loop.run_in_executor(
           │     firmware_check.check_probe_firmware,
           │     port, firmware_root)
           │     await firmware_check_task                # 串口 I/O 异步化
           ├─ reload config / project_info / config_status
           └─ return { success, output, config, project_info, config_status,
                       ★ firmware_check: check.to_dict() }
                 ↓
        GUI: response.firmware_check.status
              ├── "upgrade_required" → showFirmwareModal = true
              ├── "no_firmware_dir"  → toast.warn + 控制台日志
              ├── "skipped"          → 静默
              └── "ok"               → 静默
```

#### 2.3.3 FastAPI `GET /api/probe/firmware-check`（独立端点）

```
GUI: 任意时机（点击状态卡/模态"重新检测"按钮）
  └─ useMklinkApi.probeFirmwareCheck()
        → fetch('/api/probe/firmware-check', GET)
              → api.probe_firmware_check()
                 ├─ port = _state["device"].port if _state["device"] else None
                 ├─ check = await loop.run_in_executor(check_probe_firmware, port, root)
                 └─ return check.to_dict()
```

#### 2.3.4 Tauri `openInExplorer`（GUI）

```
GUI: FirmwareUpdateModal 点击"打开所在位置"
  └─ tauri.opener.openPath(firmware_dir)
        ├─ 成功 → 系统资源管理器打开 MK-Firmware 目录
        └─ 失败 / 浏览器环境 → toast.warn("打开目录失败")，模态保留可复制路径
```

**注**：Tauri 端到 `opener` 插件的 Rust 绑定是**未来**工作；本 spec 仅在前端 `useTauri` 钩子中预留接口 `openInExplorer(path)`，Tauri 端实现推迟。

### 2.4 错误处理（穷举）

| # | 场景 | 检测 | status | 行为 |
|---|---|---|---|---|
| E1 | `MK-Firmware/` 目录不存在 | `list_firmwares()` 抛 `FileNotFoundError` | `no_firmware_dir` | CLI `[WARN] 找不到 MK-Firmware 目录`；GUI 模态显示"环境缺少固件目录" |
| E2 | 目录存在但无匹配 UF2 | `list_firmwares()` 返回 `[]` | `no_firmware_dir` | CLI `[WARN] MK-Firmware/ 下未发现 MicroLink_V*.uf2` |
| E3 | 串口未连接（`port is None`） | 入参校验 | `skipped` | CLI 静默；GUI 不弹 |
| E4 | `cmd.get_version()` 5s 超时 | `send_command` 抛 TimeoutError | `upgrade_required` | CLI 提示"读不到探针版本，请升级" |
| E5 | 设备返回无 V 行 | `_parse_version_response` → None | `upgrade_required` | 同 E4 |
| E6 | 设备 V3.2.0（< V3.3.1） | `current < min` | `upgrade_required` | instructions 注明"当前 V3.2.0，最低 V3.3.1" |
| E7 | 设备 V4.3.1（≥ V3.3.1） | `current >= min` | `ok` | 不弹/不打印 |
| E8 | `read_device_version` 抛非超时异常 | `try/except Exception` | `skipped` + stderr warn | CLI `[WARN] 读取探针版本失败：{err}`；GUI toast.warn |
| E9 | `MKLinkSerialBridge.connect()` 抛 SerialException | bridge.connect | `skipped` | init 自身也会失败；本检查不抢先 |
| E10 | Tauri `openInExplorer` 失败 | Rust 端抛错 | — | GUI toast.warn + 模态保留可复制路径 |

**关键原则**：
- **不阻塞 init**：检查失败 → init 仍按原结果继续
- **fail-soft**：宁可少一次升级提示，不可让 init 崩溃
- **4 种 status 穷举**：UI 不必猜测分支

### 2.5 测试

#### 2.5.1 单元测试（新增 `tests/test_firmware_check.py`）

| # | 用例 | 期望 |
|---|---|---|
| U1 | `parse_firmware_filename("MicroLink_V3.3.1.uf2")` | `FirmwareInfo(version=V3.3.1, model="V3")` |
| U2 | `parse_firmware_filename("MicroLink_V4.3.1.uf2")` | `FirmwareInfo(version=V4.3.1, model="V4")` |
| U3 | `parse_firmware_filename("MicroLink_V3.3.0.bak")` | `None` |
| U4 | `list_firmwares(tmp_path/MK-Firmware)` + 3 UF2 + 1 non-UF2 | 3 项按版本升序 |
| U5 | `find_min_version([V3.3.1, V4.3.1])` | `V3.3.1` |
| U6 | `find_recommended_uf2([V3.3.1, V4.3.1], V3.5.0)` | `V3.3.1`（同 major 最高） |
| U7 | `find_recommended_uf2(..., None)` | `None` |
| U8 | `check_probe_firmware` + mock bridge 返回 V3.0.0 | `status="upgrade_required"`, instructions 含"V3 探针""两眼中点" |
| U9 | `check_probe_firmware` + mock bridge 返回乱码 | `status="upgrade_required"`, instructions 通用"V3/V4" |
| U10 | `check_probe_firmware` + mock bridge 返回 V4.3.1 | `status="ok"` |
| U11 | `check_probe_firmware` + 空 `firmware_root` | `status="no_firmware_dir"` |
| U12 | `check_probe_firmware` + `port=None` | `status="skipped"` |
| U13 | `check_probe_firmware` + bridge.connect 抛 SerialException | `status="skipped"` + 异常被记录 |
| U14 | `Version` 比较：V3.3.1 < V3.3.2, V3.9.0 < V4.0.0 | True |

#### 2.5.2 CLI 集成测试（新增 `_maintainer/testing/tests/test_cli_project_init.py`）

| # | 用例 | 期望 |
|---|---|---|
| C1 | 临时工程 + 临时 MK-Firmware + mock bridge V3.0.0 | stdout 含 `[WARN]` + V3 按钮说明 + UF2 文件名；exit 0 |
| C2 | 同上 + mock bridge V4.3.1 | stdout 不含 `[WARN]` |
| C3 | 临时工程 + 不存在 MK-Firmware | init 仍 exit 0；stdout（被 `redirect_stdout` 捕获的 `output`）含 `[WARN] 找不到 MK-Firmware 目录` |

#### 2.5.3 GUI E2E（新增 `e2e/gui/test_firmware_update_modal.py`，标 `gui_interaction` + `gui_functionality`）

| # | 用例 | 期望 |
|---|---|---|
| G1 | `apply_preset("firmware_outdated")` → click Init | 模态出现，含"V3 探针""两眼中点" |
| G2 | 模态打开 → click 关闭 | 模态消失 |
| G3 | 默认 preset（V4.3.1）→ click Init | 无模态 |
| G4 | `apply_preset("firmware_outdated")` → click 状态卡"重新检测" | 模态打开 |
| G5 | preset 设 current_version=V3.0.0 | 模态含"V3 探针上两眼中点" |
| G6 | preset 设 current_version=V4.0.0 | 模态含"V4 探针侧边拨轮" |
| G7 | preset 设 current_version=null | 模态列出 MK-Firmware/ 全部 UF2 |
| G8 | 模态关闭后 | 状态条仍可见 |

#### 2.5.4 Mock 改造（`mock_gui_api.py`）

- `MockState.probe_firmware_check: dict`（默认 `{"status": "ok", ...}`）
- `apply_preset("firmware_outdated")`：设 `status="upgrade_required"`，附 `current_version="V3.0.0"`，推荐 V3 UF2
- `apply_preset("firmware_compatible")`：设 `status="ok"`，`current_version="V4.3.1"`
- `POST /api/project-init` mock (494-496) 透传 `state.probe_firmware_check` 到响应
- 新增 `GET /api/probe/firmware-check` mock：直接返回 `state.probe_firmware_check`

### 2.6 复用现有函数

| 新代码 | 复用 | 位置 |
|---|---|---|
| `read_device_version` 解析 | `_parse_version_response` | `mklink/cli.py:965` |
| `read_device_version` 正则 | `_VERSION_LINE_RE` | `mklink/cli.py:962` |
| `read_device_version` 串口 | `MKLinkSerialBridge.connect / send_command` | `mklink/bridge.py:165, 285` |
| 设备类型 | `MKLinkSerialBridge` | `mklink/bridge.py:143` |
| 串口发现 | `find_mklink_cdc_port` | `mklink/cli.py:254-259` |
| 模态组件参考 | 现有 `*Modal.vue` | `gui/src/components/`（grep 查找） |
| Toast | `useToast` | `gui/src/composables/useToast.ts` |

### 2.7 关键文件改动示例

#### `mklink/firmware_check.py`（节选关键 API）

```python
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    def __str__(self) -> str: return f"V{self.major}.{self.minor}.{self.patch}"
    def __lt__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

@dataclass
class FirmwareInfo:
    name: str
    version: Version
    model: str  # "V3" | "V4"
    path: Path
    @property
    def version_str(self) -> str: return str(self.version)

@dataclass
class CheckResult:
    status: Literal["ok", "upgrade_required", "no_firmware_dir", "skipped"]
    current_version: Version | None
    min_required_version: Version | None
    recommended_uf2: FirmwareInfo | None
    all_uf2s: list[FirmwareInfo]
    firmware_dir: Path | None
    instructions: str
    def to_dict(self) -> dict: ...

_FIRMWARE_FILE_RE = re.compile(r"^MicroLink_(V(\d+)\.(\d+)\.(\d+))\.uf2$")

def parse_firmware_filename(name: str) -> FirmwareInfo | None: ...

def _resolve_firmware_root() -> Path:
    # 1. MKLINK_FIRMWARE_DIR 环境变量
    # 2. <cwd>/MK-Firmware
    # 3. <mklink package parent>/MK-Firmware
    # 不存在则 raise FileNotFoundError（由调用方降级为 no_firmware_dir）
    ...

def list_firmwares(root: Path) -> list[FirmwareInfo]: ...

def find_min_version(firmwares: list[FirmwareInfo]) -> Version | None: ...

def find_recommended_uf2(
    firmwares: list[FirmwareInfo], current: Version | None
) -> FirmwareInfo | None:
    if current is None or not firmwares:
        return None
    same_major = [f for f in firmwares if f.version.major == current.major]
    return max(same_major, key=lambda f: f.version) if same_major else None

def read_device_version(port: str, *, timeout: float = 5.0) -> Version | None:
    """Sync; 内部抛 TimeoutError / SerialException 由调用方处理"""
    from mklink.bridge import MKLinkSerialBridge
    from mklink.cli import _parse_version_response
    bridge = MKLinkSerialBridge(port)
    bridge.connect()
    resp = bridge.send_command("cmd.get_version()", timeout=timeout)
    current_str, _ = _parse_version_response(resp)
    if not current_str:
        return None
    m = _FIRMWARE_FILE_RE.match(f"MicroLink_{current_str}.uf2")
    return Version(*map(int, m.groups()[1:4])) if m else None

def check_probe_firmware(
    port: str | None, firmware_root: Path
) -> CheckResult: ...

def build_instructions(result: CheckResult) -> str: ...
    # 含 [WARN] 前缀多行；按 current 已知/未知 / model 决定按钮说明
```

#### `mklink/cli.py` `_cli_project_init` 末尾插入（伪代码）

```python
# 在 _cli_project_init 末尾，print("[OK] project-init 完成") 之前
try:
    from mklink import firmware_check
    port = find_mklink_cdc_port()  # 已存在
    root = firmware_check._resolve_firmware_root()
    check = firmware_check.check_probe_firmware(port=port, firmware_root=root)
    if check.status == "upgrade_required":
        for line in check.instructions.splitlines():
            print(line)
    elif check.status == "no_firmware_dir":
        print(f"[WARN] 找不到 MK-Firmware 目录 ({check.firmware_dir})，无法校验探针固件版本")
    # ok / skipped 不打
except Exception as e:
    print(f"[WARN] 探针固件版本检查异常：{e}", file=sys.stderr)
# init 继续 exit 0
```

#### `mklink/remote/api.py` `POST /api/project-init` 改动（伪代码）

```python
@router.post("/api/project-init")
async def project_init():
    project_root = _state["project_root"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await loop.run_in_executor(None, _cli_project_init, project_root)
    output = buf.getvalue()

    # ★ NEW
    from mklink import firmware_check
    firmware_check_result: dict = {"status": "skipped"}
    try:
        port = _state.get("device").port if _state.get("device") else None
        root = firmware_check._resolve_firmware_root()
        check = await loop.run_in_executor(
            None, firmware_check.check_probe_firmware, port, root
        )
        firmware_check_result = check.to_dict()
    except Exception as e:
        firmware_check_result = {"status": "skipped", "error": str(e)}

    return {
        "success": True, "output": output,
        "config": load_config(project_root),
        "project_info": load_project_info(project_root),
        "config_status": check_project_config(project_root),
        ★ "firmware_check": firmware_check_result,
    }
```

#### `gui/src/components/config/FirmwareUpdateModal.vue`（关键 props / emits）

```vue
<script setup lang="ts">
import type { ProbeFirmwareCheck, FirmwareInfo } from '@/types/mklink'
const props = defineProps<{ check: ProbeFirmwareCheck }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'recheck'): void }>()
const { openInExplorer } = useTauri()
async function onOpenDir() {
  try { await openInExplorer(props.check.firmware_dir) }
  catch { toast.warn('打开目录失败') }
}
</script>

<template>
  <Modal @close="emit('close')">
    <h2>探针固件需要升级</h2>
    <div class="grid">
      <section class="steps">
        <h3>升级步骤</h3>
        <ol>
          <li v-for="(step, i) in parseSteps(check.instructions)" :key="i">{{ step }}</li>
        </ol>
      </section>
      <section class="uf2">
        <h3>推荐固件</h3>
        <FirmwareCard v-if="check.recommended_uf2" :fw="check.recommended_uf2" />
        <div v-else>
          <p>无法识别探针型号，请从下方任选一个：</p>
          <FirmwareCard v-for="fw in check.all_uf2s" :key="fw.name" :fw="fw" />
        </div>
        <button @click="onOpenDir">打开 MK-Firmware 所在位置</button>
      </section>
    </div>
    <template #footer>
      <button @click="emit('recheck')">重新检测</button>
      <button @click="emit('close')">关闭</button>
    </template>
  </Modal>
</template>
```

---

## 3. Verification（验证）

### 3.1 单元测试

```bash
cd C:\Users\Tony\.claude\skills\mklink-flash
pytest _maintainer/testing/tests/test_firmware_check.py -v
# 期望：14 passed
```

### 3.2 CLI 集成测试

```bash
pytest _maintainer/testing/tests/test_cli_project_init.py -v
# 期望：3 passed
```

### 3.3 GUI E2E（Mock 模式）

```bash
cd gui && npm run build
pytest _maintainer/testing/tests/e2e/gui/test_firmware_update_modal.py -v --run-e2e
# 期望：8 passed
```

### 3.4 GUI E2E 全量回归（确保未破坏其他 E2E）

```bash
pytest _maintainer/testing/tests/e2e/gui -q --run-e2e
# 期望：~179 + 8 = 187 passed
```

### 3.5 CLI 手工验证

```bash
# 准备一个临时 MK-Firmware + 一个 V3.0.0 mock 探针（实际无硬件可用 mock，但可改用 timeout 路径）
cd C:\Users\Tony\.claude\skills\mklink-flash
python -m mklink project-init <temp_keil_project>
# 期望：stdout 末尾含 [WARN] 多行，按钮说明 + UF2 文件名
echo $?  # 期望：0
```

### 3.6 GUI 手工验证（Tauri 模式）

```bash
cd gui
npm run build
npx tauri dev
# 浏览器/窗口内：
# 1. 打开 ConfigView
# 2. 选一个项目 → 点击 Init
# 3. 模拟：临时把 MK-Firmware/MicroLink_V4.3.1.uf2 改成 MicroLink_V5.0.0.uf2（制造"设备 V4.3.1 < 最低 V5.0.0"场景）
# 4. 期望：模态弹出，含"V4 探针侧边拨轮"步骤 + 推荐 MicroLink_V5.0.0.uf2
# 5. 恢复文件 → 重新检测 → 模态消失
```

### 3.7 升级提示内容验证

确认 instructions 文本对四种 case 的差异：

| current_version | model 字段 | instructions 期望包含 |
|---|---|---|
| `V3.0.0` | "V3" | "V3 探针上**两个眼睛中间**的按钮" |
| `V4.0.0` | "V4" | "V4 探针**侧边拨轮**按钮" |
| `None` | 不假定 | "V3 探针按住两眼中点；V4 探针按住侧边拨轮" + 列出全部 UF2 |
| `V5.0.0` | 列表中无 V5 | `recommended_uf2=None` + instructions 提示"无 V5 同型号固件，请联系维护者" |

---

## 4. Out of Scope（不在本 spec 内）

- **Tauri Rust 端 `opener` 插件的实际绑定**：本 spec 仅在前端 `useTauri.openInExplorer(path)` 预留接口；Tauri 侧实现作为后续工作
- **固件升级的一键化**（自动检测 MICROKEEN U 盘 → 自动拷 UF2 → 提示重插）：本 spec 只做"提示"，不做"执行"
- **`_cli_version` 子命令的功能扩展**：它仍按原样工作
- **RTT 控制块 / FLM 等其他固件相关检查**：本 spec 只关注"探针自身固件"

---

## 5. Risks / 风险

| 风险 | 缓解 |
|---|---|
| 老固件探针 `cmd.get_version()` 完全不响应（5s 超时） | 已用 5s timeout；fallback 为 `current_version=None` → 升级提示 |
| `MK-Firmware/` 目录在 Tauri 打包后路径变化 | `_resolve_firmware_root()` 优先级：env > cwd > package_root；预留 `MKLINK_FIRMWARE_DIR` env 供打包配置 |
| 设备型号 vs 固件 major 不一致（如 V3 探针烧了 V4 UF2） | `find_recommended_uf2` 按 `current.major` 选；如 V3 探针读到 V3.0.0、但仓库只有 V4 UF2 → `recommended_uf2=None`，instructions 提示用户 |
| 升级后探针重启导致 COM 端口暂时消失 | 升级提示是"提示"，不接管设备控制；用户升级后重插 → 现有 connect 流程接管 |
| `redirect_stdout` 捕获到 `[WARN]` 后被混入 init 返回的 `output` 字段 | 接受：CLI 终端用户能直接看到；GUI 通过结构化 `firmware_check` 字段处理 |

---

## 6. 备注：plan-mode 限制

本 spec 在 plan-mode 下写入 `C:\Users\Tony\.claude\plans\c-users-tony-claude-skills-mklink-flash-calm-willow.md` 而非默认的 `docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md`。

**实现阶段第一步**：spec 通过用户审核后，由实施者执行：
```bash
mkdir -p docs/superpowers/specs
cp C:\Users\Tony\.claude\plans\c-users-tony-claude-skills-mklink-flash-calm-willow.md \
   docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md
git add docs/superpowers/specs/2026-06-09-probe-firmware-check-design.md
git commit -m "docs: probe firmware check on init design spec"
```

随后调用 `superpowers:writing-plans` skill 生成实施计划。
