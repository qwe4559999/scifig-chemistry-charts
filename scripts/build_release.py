#!/usr/bin/env python3
"""Build portable SciFigStudio Interactive Workbench release zip & clean skill bundle."""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_version() -> str:
    sys.path.insert(0, str(REPO_ROOT))
    from scifig import __version__
    return __version__


QUICKSTART_TXT = """================================================================
SciFigStudio Interactive Workbench v{version} — Quickstart
================================================================

1. Launch (Zero-Install):
   Double-click `SciFigStudio-Workbench.exe` (Windows) or run
   `./SciFigStudio-Workbench` (macOS / Linux).
   Your browser opens automatically at http://127.0.0.1:8765/
   (if port 8765 is busy, the next free port is chosen automatically).

2. Try the Built-in 100% Synthetic Demos:
   - examples/demo_uvvis_spec   : UV-Vis DRS multi-curve spectrum
     Try typing or clicking: "补充 724 nm 峰标" or "上移顶层曲线 0.04"
   - examples/demo_spec         : Catalytic evaluation line-marker chart
   - examples/demo_drifts_spec  : Broken-axis time-resolved in-situ DRIFTS

3. Interactive Editing & Publication Export:
   - Drag peak labels, vertical dashed lines, legends, or panel letters directly on canvas.
   - Switch journal themes (Origin Times Bold / Nature Arial / ACS Serif) & color palettes live.
   - Real-time QA Guardrail detects text overlaps & clipping and offers one-click Auto-Fix.
   - Export editable SVG, vector PDF, 600 DPI PNG, or save spec.json (`outputs/workbench_saved/`).

4. Source Code & AI Agent Skill:
   https://github.com/qwe4559999/scifig-chemistry-charts
   License: MIT
"""


def _zip_directory(src_dir: Path, zip_path: Path, arc_root: str | None = None) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(src_dir.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(src_dir)
            arc = Path(arc_root) / rel if arc_root else rel
            zf.write(p, arc.as_posix())
    return zip_path


def build_skill_zip(out_dir: Path, version: str) -> Path:
    """Create a clean, sanitized skill + engine source zip without .git/build/dist/caches."""
    zip_path = out_dir / f"scifig-chemistry-charts-v{version}-skill.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    skip_dirs = {".git", "__pycache__", "build", "dist", ".pytest_cache", ".venv", "venv", "outputs"}
    skip_suffixes = {".pyc", ".pyo", ".spec"}

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(REPO_ROOT.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(REPO_ROOT)
            if any(part in skip_dirs or part.endswith(".egg-info") for part in rel.parts):
                continue
            if p.suffix.lower() in skip_suffixes:
                continue
            if rel.parts[:2] == ("examples", "out"):
                continue
            arc = Path("scifig-chemistry-charts") / rel
            zf.write(p, arc.as_posix())
    print(f"OK  Built skill bundle: {zip_path} ({zip_path.stat().st_size / 1048576:.2f} MB)", flush=True)
    return zip_path


def build_workbench_bundle(out_dir: Path, version: str, skip_pyinstaller: bool = False) -> Path | None:
    if skip_pyinstaller:
        return None

    sep = ";" if os.name == "nt" else ":"
    dist_dir = REPO_ROOT / "dist"
    build_dir = REPO_ROOT / "build"
    app_name = "SciFigStudio-Workbench"
    app_dir = dist_dir / app_name

    if app_dir.exists():
        shutil.rmtree(app_dir)

    hidden_imports = [
        "scifig",
        "scifig.cli",
        "scifig.engine",
        "scifig.theme",
        "scifig.readers",
        "scifig.qa",
        "scifig.blueprint",
        "scifig.blind_planner",
        "scifig.workbench_bridge",
        "scifig.workbench_server",
        "matplotlib.backends.backend_svg",
        "matplotlib.backends.backend_pdf",
        "matplotlib.backends.backend_agg",
        "PIL",
        "PIL.Image",
        "scipy",
        "scipy.signal",
        "scipy.ndimage",
        "pandas",
        "openpyxl",
        "xlrd",
        "olefile",
        "fitz",
        "pymupdf",
    ]

    exclude_modules = [
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "keras",
        "cv2",
        "numba",
        "llvmlite",
        "sympy",
        "IPython",
        "jupyter",
        "notebook",
        "ipykernel",
        "ipywidgets",
        "pytest",
        "tkinter",
        "_tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "wx",
        "skimage",
        "sklearn",
        "av",
        "onnx",
        "onnxruntime",
        "transformers",
        "timm",
        "triton",
        "cupy",
        "dask",
        "pyarrow",
        "bokeh",
        "plotly",
        "seaborn",
        "statsmodels",
        "playwright",
        "selenium",
        "h5py",
        "tables",
        "sqlalchemy",
        "boto3",
        "botocore",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        app_name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(build_dir),
        "--add-data",
        f"{REPO_ROOT / 'scifig' / 'workbench_static'}{sep}scifig/workbench_static",
        "--add-data",
        f"{REPO_ROOT / 'assets'}{sep}assets",
        "--add-data",
        f"{REPO_ROOT / 'examples'}{sep}examples",
        "--collect-submodules",
        "scifig",
    ]
    for hi in hidden_imports:
        cmd.extend(["--hidden-import", hi])
    for ex in exclude_modules:
        cmd.extend(["--exclude-module", ex])
    cmd.append(str(REPO_ROOT / "scripts" / "launcher_entry.py"))

    print("Running PyInstaller:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"PyInstaller failed with exit code {proc.returncode}")

    # Drop README_QUICKSTART.txt and visible copy of examples/ next to executable
    (app_dir / "README_QUICKSTART.txt").write_text(QUICKSTART_TXT.format(version=version), encoding="utf-8")
    shutil.copytree(REPO_ROOT / "examples", app_dir / "examples", dirs_exist_ok=True)

    sys_tag = "win64" if os.name == "nt" else ("macos" if platform.system() == "Darwin" else "linux")
    zip_name = f"SciFigStudio-Workbench-v{version}-{sys_tag}.zip"
    zip_path = _zip_directory(app_dir, out_dir / zip_name, arc_root=app_name)
    print(f"OK  Built workbench archive: {zip_path} ({zip_path.stat().st_size / 1048576:.2f} MB)", flush=True)
    return zip_path


def main(argv: list[str] | None = None) -> int:
    version = _read_version()
    default_out = REPO_ROOT.parents[1] / "releases" if (REPO_ROOT.parents[1] / "scifig").is_dir() else (REPO_ROOT / "dist" / "releases")

    ap = argparse.ArgumentParser(description="Build SciFigStudio Workbench & Skill release artifacts")
    ap.add_argument("--out-dir", default=str(default_out), help="Output directory for release zip archives")
    ap.add_argument("--skip-pyinstaller", action="store_true", help="Only build the clean source/skill zip")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Building SciFigStudio v{version} releases into {out_dir}", flush=True)

    build_workbench_bundle(out_dir, version, skip_pyinstaller=args.skip_pyinstaller)
    build_skill_zip(out_dir, version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
