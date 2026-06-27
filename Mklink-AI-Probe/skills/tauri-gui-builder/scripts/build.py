#!/usr/bin/env python3
"""Build Mklink AI Probe Tauri desktop GUI exe.

Usage:
    python build.py              # Build exe only (no bundle)
    python build.py --bundle     # Full bundle with sidecar (MSI/NSIS)
    python build.py --check      # Check prerequisites only
    python build.py --clean      # Clean build artifacts

The built exe is at: gui/src-tauri/target/release/mklink-ai-probe.exe
"""

import subprocess
import sys
import os
import shutil
import argparse
import platform
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"


def find_project_root():
    """Find mklink-ai-probe project root by walking up from CWD."""
    d = Path.cwd()
    for _ in range(10):
        if (d / "mklink" / "__main__.py").exists() and (d / "gui" / "src-tauri").is_dir():
            return d
        parent = d.parent
        if parent == d:
            break
        d = parent
    print("[FAIL] Cannot find mklink-ai-probe project root. Run from the project directory or use --project-dir.")
    sys.exit(1)

IS_WINDOWS = platform.system() == "Windows"


def run(cmd, cwd=None, check=True):
    """Run a command and stream output."""
    print(f"\n> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    use_shell = IS_WINDOWS and isinstance(cmd, list) and cmd[0] in ("npm", "npx", "cargo", "rustc")
    result = subprocess.run(
        cmd, cwd=cwd, check=False,
        text=True, shell=use_shell,
    )
    if check and result.returncode != 0:
        print(f"[FAIL] Command exited with code {result.returncode}")
        sys.exit(result.returncode)
    return result.returncode


def check_rust():
    """Check Rust toolchain."""
    rc = run(["rustc", "--version"], check=False)
    if rc != 0:
        print("[FAIL] Rust not found. Install with:")
        print("  Invoke-WebRequest -Uri https://win.rustup.rs/x86_64 -OutFile $env:TEMP\\rustup-init.exe")
        print("  & $env:TEMP\\rustup-init.exe -y --default-toolchain stable")
        return False
    return True


def check_node():
    """Check Node.js and install frontend deps."""
    rc = run(["node", "--version"], check=False)
    if rc != 0:
        print("[FAIL] Node.js not found. Install with: winget install OpenJS.NodeJS.LTS")
        return False
    node_modules = GUI_DIR / "node_modules"
    if not node_modules.exists():
        print("[INFO] Installing Node.js dependencies...")
        run(["npm", "install"], cwd=str(GUI_DIR))
    return True


def check_python_deps():
    """Check Python mklink package with [gui] extras."""
    rc = run(
        [sys.executable, "-c", "import mklink, fastapi, uvicorn; print('Python deps OK')"],
        check=False,
    )
    if rc != 0:
        print("[INFO] Installing Python dependencies...")
        run([sys.executable, "-m", "pip", "install", "-e", ".[gui]"], cwd=str(SKILL_DIR))
    return True


def build_sidecar():
    """Build Python sidecar exe with PyInstaller."""
    sidecar_dir = TAURI_DIR / "binaries"
    sidecar_exe = sidecar_dir / "mklink-sidecar-x86_64-pc-windows-msvc.exe"

    if sidecar_exe.exists():
        print(f"[OK] Sidecar already exists: {sidecar_exe}")
        return True

    print("[INFO] Building Python sidecar with PyInstaller...")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    dist_dir = SKILL_DIR / "dist"
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", "mklink-sidecar",
        "--collect-all", "mklink",
        "-p", str(SKILL_DIR),
        str(SKILL_DIR / "mklink" / "__main__.py"),
    ], cwd=str(SKILL_DIR))

    sidecar_dir.mkdir(parents=True, exist_ok=True)
    built = dist_dir / "mklink-sidecar.exe"
    if built.exists():
        shutil.copy2(str(built), str(sidecar_exe))
        print(f"[OK] Sidecar copied to {sidecar_exe}")
        return True
    print("[FAIL] PyInstaller did not produce mklink-sidecar.exe")
    return False


def build_tauri(bundle=False):
    """Build Tauri application."""
    cmd = ["npx", "tauri", "build"]
    if not bundle:
        cmd.append("--no-bundle")

    run(cmd, cwd=str(GUI_DIR))

    exe = TAURI_DIR / "target" / "release" / "mklink-ai-probe.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\n[OK] Built: {exe} ({size_mb:.1f} MB)")
    else:
        print(f"\n[FAIL] Expected exe not found: {exe}")
        sys.exit(1)

    if bundle:
        bundle_dir = TAURI_DIR / "target" / "release" / "bundle"
        if bundle_dir.exists():
            for fmt in ["msi", "nsis"]:
                d = bundle_dir / fmt
                if d.exists():
                    files = list(d.glob("*"))
                    for f in files:
                        size_mb = f.stat().st_size / (1024 * 1024)
                        print(f"[OK] Bundle: {f} ({size_mb:.1f} MB)")


def clean():
    """Remove build artifacts."""
    targets = [
        TAURI_DIR / "target",
        GUI_DIR / "dist",
        SKILL_DIR / "dist",
        SKILL_DIR / "build",
    ]
    for t in targets:
        if t.exists():
            print(f"  Removing {t}")
            shutil.rmtree(t, ignore_errors=True)
    print("[OK] Clean complete")


def main():
    global SKILL_DIR, GUI_DIR, TAURI_DIR

    parser = argparse.ArgumentParser(description="Build Mklink AI Probe Tauri GUI")
    parser.add_argument("--bundle", action="store_true", help="Full bundle (MSI/NSIS) with sidecar")
    parser.add_argument("--check", action="store_true", help="Check prerequisites only")
    parser.add_argument("--clean", action="store_true", help="Remove build artifacts")
    parser.add_argument("--project-dir", type=str, default=None, help="mklink-ai-probe project root directory")
    args = parser.parse_args()

    # Resolve project root
    if args.project_dir:
        SKILL_DIR = Path(args.project_dir).resolve()
    else:
        SKILL_DIR = find_project_root()
    GUI_DIR = SKILL_DIR / "gui"
    TAURI_DIR = GUI_DIR / "src-tauri"
    print(f"[INFO] Project root: {SKILL_DIR}")

    # Ensure PATH includes cargo bin
    cargo_bin = Path.home() / ".cargo" / "bin"
    env_path = os.environ.get("PATH", "")
    if str(cargo_bin) not in env_path:
        os.environ["PATH"] = f"{env_path};{cargo_bin}"

    if args.clean:
        clean()
        return

    print("=== Mklink AI Probe Tauri Builder ===\n")

    # Prerequisites
    print("--- Checking prerequisites ---")
    if not check_rust():
        sys.exit(1)
    if not check_node():
        sys.exit(1)
    if not check_python_deps():
        sys.exit(1)

    if args.check:
        print("\n[OK] All prerequisites met")
        return

    # Build
    if args.bundle:
        print("\n--- Building sidecar (PyInstaller) ---")
        if not build_sidecar():
            sys.exit(1)

        # Restore externalBin in tauri.conf.json for bundling
        conf = TAURI_DIR / "tauri.conf.json"
        text = conf.read_text(encoding="utf-8")
        if "externalBin" not in text:
            text = text.replace(
                '"icon":',
                '"externalBin": ["binaries/mklink-sidecar"],\n    "icon":',
            )
            conf.write_text(text, encoding="utf-8")
            print("[INFO] Added externalBin to tauri.conf.json for sidecar bundling")

    print("\n--- Building Tauri application ---")
    build_tauri(bundle=args.bundle)


if __name__ == "__main__":
    main()
