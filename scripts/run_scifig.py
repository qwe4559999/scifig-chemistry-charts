#!/usr/bin/env python3
"""Cross-platform UTF-8 CLI wrapper for 14_SciFigStudio_20261126 (`scifig`)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def find_studio_root() -> Path:
    env_root = os.environ.get("SCIFIG_ROOT")
    if env_root:
        p = Path(env_root).resolve()
        if (p / "scifig").is_dir():
            return p

    here = Path(__file__).resolve()
    # Standard location: 14_SciFigStudio_20261126/skill/scifig-chemistry-charts/scripts/run_scifig.py
    for parent in here.parents:
        if (parent / "scifig").is_dir() and (parent / "assets").is_dir():
            return parent
        cand = parent / "14_SciFigStudio_20261126"
        if (cand / "scifig").is_dir() and (cand / "assets").is_dir():
            return cand

    raise FileNotFoundError(
        "Could not locate 14_SciFigStudio_20261126 root (set SCIFIG_ROOT env var if skill was copied externally)."
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python run_scifig.py <scifig-subcommand|blind> [args...]\n"
            "Subcommands: doctor, templates, new, read, probe, validate, render, qa, compare, render-refs, extract-blueprints, blind",
            file=sys.stderr,
        )
        return 2

    studio_root = find_studio_root()
    env = os.environ.copy()
    env.setdefault("SCIFIG_ASSETS", str(studio_root / "assets"))
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(studio_root) + (os.pathsep + existing_pp if existing_pp else "")
    env["PYTHONUTF8"] = "1"

    if args[0] in ("blind", "blind-plan", "blind_planner"):
        cmd = [sys.executable, "-X", "utf8", "-m", "scifig.blind_planner", *args[1:]]
    else:
        cmd = [sys.executable, "-X", "utf8", "-m", "scifig", *args]

    proc = subprocess.run(cmd, cwd=str(Path.cwd()), env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
