#!/usr/bin/env python3
"""PyInstaller & standalone entry point for SciFigStudio Interactive Workbench."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _configure_runtime() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir)).resolve()
        for cand in (exe_dir / "assets", meipass / "assets"):
            if (cand / "themes").is_dir():
                os.environ.setdefault("SCIFIG_ASSETS", str(cand))
                break
    else:
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        if (repo_root / "assets" / "themes").is_dir():
            os.environ.setdefault("SCIFIG_ASSETS", str(repo_root / "assets"))


def main() -> int:
    _configure_runtime()
    from scifig import __version__, workbench_server

    print("=" * 64, flush=True)
    print(f"  SciFigStudio Interactive Workbench v{__version__}", flush=True)
    print("  人机协同科研绘图工作台 · 双向同步 spec.json · 实时 QA 护栏", flush=True)
    print("=" * 64, flush=True)
    print("  1. Your default web browser will open automatically.", flush=True)
    print("     浏览器将自动打开工作台界面；如未打开，请手动复制下方 URL。", flush=True)
    print("  2. Keep this terminal window open while editing figures.", flush=True)
    print("     编辑期间请勿关闭本窗口，按 Ctrl+C 可安全退出。", flush=True)
    print("-" * 64, flush=True)

    try:
        return workbench_server.main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\nSciFigStudio Workbench stopped cleanly.", flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        if getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to close...")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
