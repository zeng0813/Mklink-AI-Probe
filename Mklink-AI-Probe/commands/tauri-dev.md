---
description: 以开发模式启动 Tauri GUI（同时启动 Vite dev server + Rust 后端，支持前端热更新）
---

请执行以下命令启动 Tauri 开发模式：

```bash
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cd gui
npx tauri dev
```

这将：
1. 启动 Vite dev server（端口 5173），支持前端热更新
2. 编译并运行 Rust 后端，打开原生 Tauri 窗口
3. Tauri 启动时会自动尝试启动 `python -m mklink serve` 作为 sidecar（端口 8765）

确保 Python 环境（`mklink` 包）已安装后再运行。
