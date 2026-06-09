"""
MKLink Serial Bridge — RTT 自动启动配置生成。

零外部依赖（仅 stdlib），零内部依赖。
"""

from __future__ import annotations

import re


def generate_autostart_config(
    addr: str,
    size: int,
    channel: int,
    existing_content: str = "",
    *,
    mode: int = 0,
) -> str:
    """生成 default_config.py 内容（保留已有配置）。

    非破坏性：如果已有 RTTView.start 行则替换，否则追加。

    Args:
        addr: RTT 控制块地址。
        size: 探针扫描字节数（仅 mode=0 生效；mode=1 强制 0）。
        channel: RTT 通道号。
        existing_content: 已有的 default_config.py 内容。
        mode: 0=动态搜寻（默认）/1=静态编译。
            模式 1 时 size 参数被忽略，生成 RTTView.start(addr, 0, channel)。
    """
    if mode not in (0, 1):
        raise ValueError(f"mode 必须是 0 或 1，得到 {mode}")

    actual_size = 0 if mode == 1 else size
    rtt_line = f"RTTView.start({addr}, {actual_size}, {channel})\n"

    if existing_content and "RTTView.start" in existing_content:
        return re.sub(r"RTTView\.start\([^)]+\)", rtt_line.strip(), existing_content)

    if existing_content:
        return existing_content.rstrip("\n") + "\n" + rtt_line

    return f"""import time
import cmd

# 等待目标板连接（超时 10 秒）
elapsed = 0
while elapsed < 10000:
    idcode = cmd.get_idcode()
    if idcode not in (0, 0xFFFFFFFF):
        break
    time.sleep_ms(500)
    elapsed += 500

if idcode not in (0, 0xFFFFFFFF):
    {rtt_line.strip()}
"""
