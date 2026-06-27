"""
MKLink Serial Bridge — SystemView 会话管理。

RTOS 的 SEGGER_SYSVIEW 集成把跟踪事件包写入 RTT 上行通道 1（"SysView" 缓冲）。
SystemViewSession 用普通 RTT（``RTTView.start(addr, search, 1)``）打开通道 1，
进入 ``SYSTEMVIEW_STREAM`` 二进制流模式，把原始字节交给 SystemViewParser 解码。

不依赖探针固件的 SystemView.* 模块——只要 RTT 可用即可。克隆 RTTSession 的结构，
复用其地址解析与启动回执解析。

依赖: 无外部依赖
内部依赖: mklink.bridge, mklink._types, mklink.rtt（复用解析）,
          mklink.systemview_parser
"""

from __future__ import annotations

import time

from mklink._types import DeviceState
from mklink.bridge import MKLinkSerialBridge
from mklink.rtt import RTTSession


class SystemViewSession:
    """SystemView 跟踪流会话（RTT 通道 1，二进制）。"""

    def __init__(self, bridge: MKLinkSerialBridge, channel: int = 1):
        self._bridge = bridge
        self._channel = channel
        self._running = False

    def start(
        self,
        addr: str,
        search_size: int = 1024,
        project_root: str = ".",
        *,
        mode: int = 0,
    ) -> dict:
        """启动 SystemView 采集：开 RTT 通道 1 并切到二进制流模式。

        地址解析复用 RTTSession（.mklink/rtt_config.json 或默认 0x20000000）。
        CB 存在性用 ``cmd.read_ram`` 直接验证 magic（比探针 RTTView 文本回执
        可靠——**高频通道(1)下探针会立即推流、不回 ``>>>``**，``send_command``
        拿不到 "Find SEGGER RTT addr" 回执，但 RTT 实际已工作）。
        """
        if mode not in (0, 1):
            raise ValueError(f"rtt_storage_mode 必须是 0 或 1，得到 {mode}")

        if not addr:
            addr = RTTSession._find_rtt_addr_from_config(project_root)
            if addr:
                print(f"[OK] 从配置读取 RTT 地址: {addr}")
            else:
                addr = "0x20000000"
                print(f"[WARN] 未找到 RTT 配置，使用默认搜索地址: {addr}")

        # 探针 RTTView.start 用 search_size 字节从 addr 扫描找 magic——
        # 即使 addr 是静态精确地址也必须给非零窗口（size=0 探针不扫描、报 no find）。
        actual_search_size = search_size if search_size else 1024
        cmd = f"RTTView.start({addr},{actual_search_size},{self._channel})"
        result: dict = {"storage_mode": mode, "channel": self._channel}
        cb_addr_int = int(str(addr), 16)

        # 1) 命令模式下直接读 CB magic 验证（retry：reconnect 后 bridge 可能短暂不
        #    稳定，首次 read_ram 解析失败。retry 3 次给 bridge warmup 时间）
        from mklink.memory_access import parse_read_ram_response
        found = False
        for _ in range(5):
            try:
                magic = parse_read_ram_response(
                    self._bridge.send_command(
                        f"cmd.read_ram(0x{cb_addr_int:08X}, 16)", timeout=6.0
                    )
                )
                if magic[:11] == b"SEGGER RTT\x00":
                    result["control_block_addr"] = f"0x{cb_addr_int:08X}"
                    found = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

        # 2) magic 不在 addr（动态模式 addr 是搜索起点）→ 让探针扫描拿真实地址
        if not found:
            resp = self._bridge.send_command(cmd, timeout=20.0)
            result.update(RTTSession._parse_rtt_startup(resp))
            if not result.get("control_block_addr"):
                return result  # 真没找到

        # 3) 启动 RTT 流：raw 写命令（避免高频通道 send_command 等不到 >>>），再进流模式
        self._bridge._write_raw((cmd + "\n").encode())
        time.sleep(0.3)  # 给探针处理 + 开始推流
        self._bridge._enter_stream(DeviceState.SYSTEMVIEW_STREAM)
        self._running = True
        return result

    def read_bytes(
        self, duration: float = 2.0, max_bytes: int | None = None
    ) -> bytes:
        """在 duration 秒内持续 drain 二进制流缓冲，返回累积的原始字节。"""
        if not self._running:
            raise RuntimeError("SystemView not started")
        chunks: list[bytes] = []
        total = 0
        deadline = time.time() + duration
        while True:
            budget = None if max_bytes is None else max(0, int(max_bytes) - total)
            if budget == 0:
                break
            try:
                chunk = self._bridge.drain_stream_bytes(max_bytes=budget)
            except RuntimeError:
                break
            if chunk:
                chunks.append(chunk)
                total += len(chunk)
            if time.time() >= deadline:
                break
            time.sleep(0.05)
        # 收尾再 drain 一次，避免漏掉最后一段
        try:
            budget = None if max_bytes is None else max(0, int(max_bytes) - total)
            if budget != 0:
                chunk = self._bridge.drain_stream_bytes(max_bytes=budget)
                if chunk:
                    chunks.append(chunk)
        except RuntimeError:
            pass
        return b"".join(chunks)

    def stop(self) -> str:
        """停止采集：退出流模式并发 RTTView.stop()。

        用 raw 写停止命令（与 start 的 raw 写对称）——探针在高频流模式下不在
        ``>>>`` 提示符，send_command 等不到回执会把 bridge 置 ERROR。raw 写 +
        小睡让探针停止推流、回到提示符，bridge 保持 READY 供后续命令使用。
        """
        remaining = self._bridge._exit_stream()
        try:
            self._bridge._write_raw(b"RTTView.stop()\n")
            time.sleep(0.3)
        except Exception:
            pass  # 停止失败也继续恢复状态
        self._running = False
        return remaining
