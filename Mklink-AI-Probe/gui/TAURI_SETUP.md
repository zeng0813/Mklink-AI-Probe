# MKLink Flash GUI — Tauri v2 Setup Guide

## Prerequisites

1. **Node.js** (v18+) — Already installed
2. **Rust** — Install via https://rustup.rs/
3. **Python** (3.8+) — Already installed

## Install Rust

```powershell
# Download and run rustup installer
winget install Rustlang.Rustup
# or visit https://rustup.rs/

# Verify installation
rustc --version
cargo --version
```

## Initialize Tauri v2

After installing Rust, run these commands in the `gui/` directory:

```powershell
cd gui

# Install Tauri CLI and API
npm install --save-dev @tauri-apps/cli@latest
npm install @tauri-apps/api@latest

# Initialize Tauri v2 (use existing frontend)
npx tauri init

# When prompted:
# - App name: MKLink Flash
# - Window title: MKLink Flash Programmer
# - Dev server URL: http://localhost:5173
# - Frontend dist: ../dist
# - Dev command: npm run dev
# - Build command: npm run build
```

## Copy Tauri Configuration

Copy the pre-configured `tauri.conf.json`:

```powershell
# After `npx tauri init`, replace the generated config
Copy-Item ..\src-tauri\tauri.conf.json .\src-tauri\tauri.conf.json -Force
```

## Python Sidecar Setup

The Tauri app will manage the Python backend as a "sidecar" process:

```powershell
# Package Python backend with PyInstaller
pip install pyinstaller
pyinstaller --onefile --name mklink-sidecar -D ..\mklink\remote\api.py

# Copy to Tauri's binary directory
mkdir src-tauri\binaries
Copy-Item dist\mklink-sidecar.exe src-tauri\binaries\mklink-sidecar-x86_64-pc-windows-msvc.exe
```

## Development

```powershell
# Start both frontend dev server and Tauri window
npx tauri dev

# Build for production
npx tauri build
```

## Architecture

```
Tauri Shell (Rust)
  ├─ Vue 3 Frontend (port 5173 in dev)
  └─ Python Sidecar (FastAPI on port 8765)
      └─ MKLink Probe (pyserial/SWD)
```

The frontend communicates with the Python backend via:
- **REST API** (`/api/*`) — Configuration, device management
- **WebSocket** (`/ws`) — JSON-RPC for real-time device operations
