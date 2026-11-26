---
name: scifig-chemistry-charts
description: End-to-end declarative scientific figure generation, paper reproduction, and interactive visual editing for chemistry, catalysis, spectroscopy, deconvolution, and microscopy data using SciFigStudio (scifig). Supports Mode 1 (Reference-Anchored Reproduction from vector PDF blueprints), Mode 2 (Blind Data-to-Figure Generation via blind_planner with automated QA repair), and Mode 3 (Interactive Human-AI GUI Workbench with live drag handles, local AI micro-edits, real-time QA guardrails, and bidirectional spec.json sync), plus direct ingestion of .spa, .VGD, .asc, .ras, .spc, Bruker TopSpin NMR, and SEM/TEM TIFFs without Origin COM dependency.
---

# SciFig Chemistry Charts (`scifig-chemistry-charts`)

Declarative scientific figure skill powered by `.` (`scifig`). Consolidates 9 canonical chemistry chart workflows (`01_line-marker-eval` through `09_microscopy-montage`), vector-PDF-measured themes/palettes, raw instrument readers, automated visual/numerical QA gates, reference-free blind plotting, and the Interactive Human-AI GUI Workbench.

## 0. Environment & Health Check

Always run Python with `-X utf8` from `.` (or via `scripts/run_scifig.py`):

```bash
python scripts/run_scifig.py doctor
python scripts/run_scifig.py templates
```

Confirm `assets_ok: true`, `font_times_found: true`, and all 9 chart templates (`01_`–`09_`) are listed. Set `SCIFIG_ASSETS` only if overriding `./assets`.

---

## Mode 1: Reference-Anchored Reproduction

Use when reproducing an existing paper figure or matching a house PDF style 1:1.

1. **Extract reference PNGs & layout blueprints** from original vector PDFs:
   ```bash
   python scripts/run_scifig.py render-refs --pdf-dir <pdf_dir> --out outputs/compare/_refs
   python scripts/run_scifig.py extract-blueprints --pdf-dir <pdf_dir> --out outputs/compare/_blueprints
   ```
2. **Ingest & inspect data** (never guess file internals; see `references/instrument-formats.md`):
   ```bash
   python scripts/run_scifig.py probe <data_dir> --out inventory.json
   python scripts/run_scifig.py read <instrument_file> --json
   ```
3. **Select chart workflow & scaffold spec** (see `references/chart-type-workflows.md`):
   ```bash
   python scripts/run_scifig.py new 04_deconv-peak-fit specs/my_fig.json
   ```
   - Anchor `figure.width_in`, `figure.height_in`, panel `rect`, `theme` (`origin-times-bold` or scaled large-panel sizes), and `palette` (`publication-pastel`) to `_blueprints/<Fig>.json`.
   - Write all smoothing/baseline transforms explicitly in `ops` (never silently alter data).
   - Keep source table values intact when source-vs-figure conflicts exist; record discrepancies in notes/provenance.
4. **Validate, render, QA, and compare**:
   ```bash
   python scripts/run_scifig.py validate specs/my_fig.json
   python scripts/run_scifig.py render specs/my_fig.json -o outputs/main --name FigX
   python scripts/run_scifig.py qa specs/my_fig.json --png outputs/main/FigX.png --ref outputs/compare/_refs/FigX.png
   python scripts/run_scifig.py compare FigX outputs/main/FigX.png -o outputs/compare/FigX_compare.png
   ```
5. **Visual inspection gate**: Open both `FigX.png` and `FigX_compare.png` directly and verify against `references/style-and-qa-rules.md`.

---

## Mode 2: Blind Data-to-Figure Generation (No Reference)

Use when given ONLY raw/tidy data without a reference PDF/image.

**Inputs required:**
1. Raw or tidy data path(s) (`.csv`, `.xlsx`, `.txt`, `.spa`, `.VGD`, `.asc`, `.ras`, Bruker NMR, `.tif`)
2. Chart type ID from `assets/charts/` (`01_line-marker-eval` .. `09_microscopy-montage`)
3. Theme (`origin-times-bold`, `journal-nature-arial`, or `journal-acs-serif`)
4. Basic caption / axis title metadata

**Execution (`scifig.blind_planner`):**
```bash
python -X utf8 -m scifig.blind_planner --data <path> --chart 01_line-marker-eval --theme journal-nature-arial --caption "NH3-SCR performance" -o outputs/blind_eval --name Fig1_blind
```
Or via wrapper:
```bash
python scripts/run_scifig.py blind --data <path> --chart 01_line-marker-eval --theme journal-nature-arial --caption "NH3-SCR performance" -o outputs/blind_eval --name Fig1_blind
```

**Automated pipeline inside `blind_planner`:**
- Inspects columns/headers (strips Origin escapes like `Catalyst-A`) and maps semantic data slots (`x`, `y_obs`, `y_fit`, `components`, `series`).
- Infers physical axis bounds & direction: `[0, 102]` for `%` conversion/selectivity, reverse x for IR/DRIFTS/NMR/XPS, bimodal silent-window detection (`3300–1800 cm^-1`) for DRIFTS broken axes, robust IQR stacking offsets, and sparsest-corner legend placement.
- Generates declarative `spec.json`, renders via `scifig`, runs `scifig qa`, and performs up to **3 auto-repair iterations** (relocating colliding legends, expanding clipped margins/ylims, staggering crowded peak labels, scaling flat DRIFTS stacks).

---

## Mode 3: Interactive Human-AI GUI Workbench

Use after Mode 1 or Mode 2 (or standalone with built-in synthetic demos) when the user wants WYSIWYG mouse dragging, local AI micro-edits, live QA collision guardrails, and bidirectional `spec.json` synchronization.

**Launch commands:**
```bash
python scripts/run_scifig.py workbench --port 8765
# Or directly when installed via pip:
scifig-workbench --port 8765
# Windows / macOS / Linux one-click launchers:
launch_workbench.bat   # or ./launch_workbench.sh
```

**Core workbench capabilities:**
- **Direct Manipulation & Snap Guides**: Drag peak text labels, vertical dashed peak lines (`vline`), legends, sample labels, and panel letters directly on the canvas; coordinates write back to `spec.json` with Undo/Redo.
- **Local AI Micro-Editing Bar**: Execute bilingual offline NLU commands (e.g., `"补充 724 nm 峰标"`, `"上移顶层曲线 0.04"`, `"图例移至左上角"`, `"切换 Nature Arial 主题"`, `"自动修复 QA 碰撞"`) or optional OpenAI-compatible LLM (`SCIFIG_LLM_API_KEY`, `SCIFIG_LLM_BASE_URL=https://api.deepseek.com/v1`, `SCIFIG_LLM_MODEL=deepseek-chat`; runs 100% offline deterministic NLU when unset).
- **Real-Time QA Guardrail & Journal Preflight**: Highlights text overlaps, clipping, or legend occlusions in red with one-click Auto-Fix, checks column width / 600 DPI / min font `>= 6.0 pt`, and verifies raw data SHA-256 read-only provenance.
- **Publication Export**: One-click export of editable `SVG`, vector `PDF`, `600 DPI PNG`, and saved `spec.json`.
- **Headless HTTP API for External Agent Harnesses**: Pass `--no-open --port 8765` (`scifig-workbench --no-open --port 8765` or `python scripts/run_scifig.py workbench --no-open --port 8765`) to run as a local microservice exposing `POST /api/blind`, `POST /api/render`, `POST /api/ai-command`, `POST /api/auto-fix`, and `POST /api/export` for `DeepSeek`, `LangGraph`, `OpenAI Agents`, or custom harnesses.

---

## 9 Canonical Chemistry Chart Types

See `references/chart-type-workflows.md` for full slot contracts and pitfalls:
- `01_line-marker-eval` — Catalytic evaluation (`Fig1`, `FigS1`–`FigS4`)
- `02_stacked-spectra` — Stacked XRD / ²⁷Al NMR (`Fig2A`, `Fig2C`)
- `03_isotherm-psd` — N₂ adsorption-desorption & `dV/dlog(W)` PSD (`Fig2B`, `FigS6`)
- `04_deconv-peak-fit` — Seamless `hspace=0` stacked deconvolution (`Fig2D`, `Fig4A`, `Fig5B`)
- `05_stacked-bar-comp` — 100% gradient stacked composition bar (`Fig4B`)
- `06_single-multi-spectrum` — Unstacked multi-curve EPR / UV-Vis + annotations (`Fig5A`, `FigS7`)
- `07_drifts-broken-stack` — In situ DRIFTS broken/unbroken stacks (`Fig6`, `FigS9`–`FigS12`)
- `08_xps-reverse-deconv` — XPS reverse-binding-energy deconvolution (`FigS8`)
- `09_microscopy-montage` — TEM/HAADF/EDS & SEM raster montage (`Fig3`, `FigS5`)

## Reference Files
- `references/chart-type-workflows.md` — Slot contracts, preprocessing rules, and pitfalls for all 9 chart types.
- `references/style-and-qa-rules.md` — Measured PDF font/stroke/color baselines (standard, wide 1×3, large single-panel) and QA gate criteria.
- `references/instrument-formats.md` — Binary/text specs for `.spa`, `.VGD`, `.asc`, `.ras`, `.spc`, Bruker TopSpin, `.tif`, and proprietary boundaries (`.vgp`, `.raw`).
- `scripts/run_scifig.py` — Cross-platform UTF-8 wrapper invoking `scifig` CLI, `scifig.blind_planner`, and `scifig workbench`.
