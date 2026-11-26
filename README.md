# SciFig Chemistry Charts & Interactive Workbench (`scifig-chemistry-charts`)

An Origin-free, declarative scientific figure engine, **Interactive Human-AI GUI Workbench**, 9-type chemistry chart asset library, and reusable AI agent skill (`SKILL.md` + `scifig` CLI + `blind_planner` + `scifig-workbench`).

> **简体中文简介**：面向化学、催化、光谱、表征与电镜拼版的**脱离 Origin 声明式科研制图引擎、人机协同交互式 GUI 工作台与 AI Agent Skill**。统一底层渲染引擎，同时支持 **AI Agent 自动化绘图（Skill / CLI）**、**无参照盲绘（Blind Mode）**与 **所见即所得可视化微调工作台（拖拽锚点 · 局部 AI 微调 · 实时 QA 防碰撞护栏 · 双向 `spec.json` 同步）**。

---

## Interactive Human-AI GUI Workbench (`v2.1.0`)

![SciFigStudio Interactive Workbench Preview](assets/workbench_preview.png)

*100% synthetic UV-Vis DRS demo (`examples/demo_uvvis_spec.json`) loaded in SciFigStudio Interactive Workbench — showing the Layer Tree & SHA-256 Data Provenance pane (left), live interactive vector canvas with draggable handles & local AI command dock (center), and Theme/Palette hot-switcher, Property Inspector, Journal Preflight card & bidirectional `spec.json` editor (right).*

### Unified Architecture: Skill + CLI + Interactive Workbench

All three workflows share the exact same declarative `spec.json` schema, instrument readers (`scifig.readers`), rendering engine (`scifig.engine`), and visual/numerical QA gate (`scifig.qa`):

- **Mode 1 — Reference-Anchored Reproduction (CLI / Skill)**: Extract layout/font/stroke blueprints from target vector PDFs (`render-refs`, `extract-blueprints`), map data slots, render `PNG / SVG / PDF`, and verify side-by-side (`qa`, `compare`).
- **Mode 2 — Blind / No-Reference Generation (CLI / Skill / Workbench Modal)**: Pass only `(data_paths, chart_id, theme, caption)` to `scifig.blind_planner` for automatic column role inference, reverse-x / broken-axis detection, robust stacking, sparse-corner legend placement, and up to 3 QA auto-repair cycles.
- **Mode 3 — Interactive Human-AI GUI Workbench (`scifig workbench` / `scifig-workbench`)**:
  - **Direct Canvas Manipulation**: Click and drag peak labels, vertical dashed peak guides (`vline`), legends, and panel letters directly on the figure with live snap alignment guides & coordinate HUD.
  - **Local AI Micro-Editing Dock**: Run natural-language Chinese/English commands offline (e.g., `"补充 724 nm 峰标"`, `"上移顶层曲线 0.04"`, `"图例移至左上角"`, `"切换 Nature Arial 主题"`, `"自动修复 QA 碰撞"`) or connect an OpenAI-compatible LLM via `SCIFIG_LLM_API_KEY`.
  - **Real-Time QA Guardrail & Journal Preflight**: Live overlap/clipping/legend-occlusion detection with red bounding-box alerts, one-click Auto-Fix, column-width & min-font preflight, and SHA-256 read-only raw data provenance.
  - **Bidirectional `spec.json` Sync & Publication Export**: Every mouse drag, inspector edit, or AI patch updates `spec.json` with line-diff highlights and Undo/Redo; export editable `SVG`, vector `PDF`, and `600 DPI PNG` in one click.

---

## Quick Launch (3 Ways)

### Option A — Zero-Install Desktop Bundle (Windows `.exe`, Recommended)
1. Download `SciFigStudio-Workbench-v2.1.0-win64.zip` from the [**GitHub Releases**](https://github.com/qwe4559999/scifig-chemistry-charts/releases) page.
2. Extract the zip and double-click **`SciFigStudio-Workbench.exe`**.
3. Your browser opens automatically at `http://127.0.0.1:8765/` (auto-selects a free port if `8765` is busy) with all 3 synthetic demos ready to try.

### Option B — One-Click Source Launcher (`launch_workbench.bat` / `launch_workbench.sh`)
```bash
git clone https://github.com/qwe4559999/scifig-chemistry-charts.git
cd scifig-chemistry-charts

# Windows: double-click launch_workbench.bat (auto-checks & installs requirements)
# macOS / Linux:
chmod +x launch_workbench.sh && ./launch_workbench.sh
```

### Option C — Python Package Install (`pip install` & CLI / `scifig-workbench`)
```bash
pip install -e .          # or: pip install -r requirements.txt

# Launch Interactive GUI Workbench
scifig-workbench          # or: python -X utf8 -m scifig workbench --port 8765
# Or via the Skill CLI wrapper:
python scripts/run_scifig.py workbench --port 8765
```

---

## Built-in 100% Synthetic Demos (`examples/`)

| Demo Spec | Chart Type | Highlights to Try in Workbench |
| :--- | :--- | :--- |
| `examples/demo_uvvis_spec.json` (`demo_uvvis.csv`) | `06_single-multi-spectrum` | 3 synthetic UV-Vis DRS curves (`Catalyst-A/B/C`, 200–800 nm) with `224` & `269` markers — try clicking **`补充 724 nm 峰标`** or **`上移顶层曲线 0.04`**! |
| `examples/demo_spec.json` (`demo_eval.csv`) | `01_line-marker-eval` | Catalytic `NOx` conversion vs Temperature with Nature Arial theme & NPG palette — try dragging the legend or hot-switching to `Origin Times Bold`. |
| `examples/demo_drifts_spec.json` (`demo_drifts.csv`) | `07_drifts-broken-stack` | 6-curve time-resolved broken-axis in-situ DRIFTS (`[3800, 3400] // [1900, 800]`) with segment-scoped peak guides, inline time labels & adjustable `break_gap`. |

---

## CLI Quickstart (Modes 1 & 2)

```bash
# 1. Environment & asset diagnostics
python -X utf8 scripts/run_scifig.py doctor
python -X utf8 scripts/run_scifig.py templates

# 2. Mode 1: Render declarative spec + run QA
python -X utf8 scripts/run_scifig.py render examples/demo_uvvis_spec.json -o examples/out --name DemoUV
python -X utf8 scripts/run_scifig.py qa examples/demo_uvvis_spec.json --png examples/out/DemoUV.png

# 3. Mode 2: Blind / No-Reference generation from raw/tidy table
python -X utf8 scripts/run_scifig.py blind \
  --data examples/demo_eval.csv \
  --chart 01_line-marker-eval \
  --theme journal-nature-arial \
  --caption "Synthetic catalytic evaluation demo" \
  -o examples/out --name Demo_blind

# 4. Mode 3: Interactive GUI Workbench
python -X utf8 scripts/run_scifig.py workbench --port 8765
```

---

## 9 Canonical Chemistry Chart Types & Native Readers

- **9 Chart SOPs (`assets/charts/`)**:
  1. `01_line-marker-eval` — Catalytic evaluation (`NOx` conversion, selectivity, byproduct concentration vs T)
  2. `02_stacked-spectra` — Stacked 1D spectra (PXRD, solid-state NMR)
  3. `03_isotherm-psd` — N₂ adsorption-desorption isotherms & `dV/dlog(W)` pore size distribution
  4. `04_deconv-peak-fit` — Seamless (`hspace=0`) stacked deconvolution with vertical-gradient fills (TPD, TPR, NMR)
  5. `05_stacked-bar-comp` — 100% stacked composition bars with vertical gradient fills & legend patches
  6. `06_single-multi-spectrum` — Unstacked multi-curve spectra with peak guides or EPR hyperfine comb brackets
  7. `07_drifts-broken-stack` — Time-resolved in situ DRIFTS stacks (auto broken-axis or unbroken bands)
  8. `08_xps-reverse-deconv` — Reverse binding-energy XPS deconvolution anchored to Shirley background
  9. `09_microscopy-montage` — Tight-gap TEM/HAADF/EDS & SEM raster montages with badges and scale bars
- **Native Instrument Readers (`scifig.readers`)**: `.csv`, `.xlsx`, `.xls`, `.txt`, `.spa` (OMNIC), `.VGD` (Thermo Avantage float64 counts), `.asc`/`.ras` (Rigaku XRD), `.spc`, Bruker TopSpin (`1r`/`procs`), and `.tif`/`.png`.

---

## Visual Asset Library (100% Synthetic Swatches & Previews)

All visual assets below are mathematically synthesized via `python -X utf8 -m scifig.build_visual_assets` (zero private lab data):

### 12 Atomic Visual Elements
![Atomic Visual Elements](assets/elements_wall.png)

### 9 Chemistry Chart Types
![9 Chemistry Chart Types](assets/gallery_wall.png)

---

## Repository Structure

```text
scifig-chemistry-charts/
├─ SKILL.md                    # AI agent skill entrypoint (Modes 1, 2 & 3)
├─ pyproject.toml              # PEP 621 package metadata (`scifig`, `scifig-workbench`)
├─ launch_workbench.bat        # Windows one-click Workbench launcher
├─ launch_workbench.sh         # macOS / Linux one-click Workbench launcher
├─ references/                 # Chart workflows, typography/QA rules, instrument format specs
├─ scripts/
│  ├─ run_scifig.py            # Cross-platform UTF-8 CLI wrapper (incl. `blind` & `workbench`)
│  ├─ launcher_entry.py        # Standalone / PyInstaller GUI Workbench entry point
│  └─ build_release.py         # Automated PyInstaller win64 + clean skill zip builder
├─ scifig/                     # Core Python engine, readers, QA gate, blind planner & Workbench
│  └─ workbench_static/        # Zero-CDN 3-pane Interactive Workbench frontend
├─ assets/
│  ├─ index.json               # Asset catalog
│  ├─ workbench_preview.png    # 100% synthetic Interactive Workbench preview
│  ├─ themes/                  # origin-times-bold, journal-nature-arial, journal-acs-serif
│  ├─ palettes/                # publication-pastel, okabe-ito, nature-npg
│  └─ charts/01_..09_/         # Per-chart chart.json (data contract + blind defaults + QA) & workflow.md
├─ examples/                   # 3 self-contained 100% synthetic demos (UV-Vis, Eval, DRIFTS)
└─ .github/workflows/release.yml  # Automated cross-platform GitHub Release CI
```

## License

MIT License — Copyright (c) 2026 `qwe4559999`.
