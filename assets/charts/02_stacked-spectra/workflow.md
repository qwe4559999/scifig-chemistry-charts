# 02_stacked-spectra — Stacked Spectra Workflow (XRD / 27Al NMR)

**Covered Figures:** `Fig2A` (PXRD), `Fig2C` (27Al MAS NMR, un-deconvoluted raw spectra).

## 1. Data Ingestion
- **Fig2A (PXRD):**
  - Compiled: `data/xrd_stacked.txt` — 8 comma-separated columns (`Angle, Support, Angle, Catalyst-A, Angle, Catalyst-B, Angle, Catalyst-C`), step `0.02°`, already pre-offset (`~0.35, 1.07, 1.64, 2.25`).
  - Raw: `data/raw_xrd/*.ras` (two-column text after `*RAS_DATA_START`) and `*.asc` (**intensity-only** 4 values/line; 2θ reconstructed from `*START/*STOP/*STEP`).
- **Fig2C (27Al MAS NMR):**
  - Compiled: `data/27Al_nmr.csv` (`ppm` + 4 samples).
  - Raw: `data/raw_27Al_nmr/<sample>/仪器测试数据/` (Bruker TopSpin `1r`/`procs` via `readers.read_bruker`, or `*-27Al-原始光谱.txt` 3-sig-fig text).

## 2. Preprocessing
- **XRD:** If using `xrd_stacked.txt`, note that baselines are pre-shifted; if re-spacing to achieve equal visual gap, subtract each curve's baseline minimum (`baseline_min`) and add explicit equal offsets in `spec.json` (`ops` + `offset`), never altering peak shape.
- **27Al NMR:** No deconvolution (Fig2C is raw MAS NMR). No extra smoothing unless documented in `ops`.

## 3. Slot Mapping
| Slot | Fig2A (XRD) | Fig2C (27Al NMR) |
|---|---|---|
| `x` | `2θ (°)`, `[3, 40]` ascending | `Chemical shift (ppm)`, `[90, -25]` **descending** |
| `series` | Bottom→Top: `Support`, `Catalyst-A`, `Catalyst-B`, `Catalyst-C` | Same bottom→top order |
| `offset` | Equal visual baseline separation | Compact offset (~0.55 of normalized single-curve height) |

## 4. Layout & Annotations
- **Colors (bottom → top):** `Support` `#B00F1A`, `Catalyst-A` `#6699BA`, `Catalyst-B` `#CCA8E3`, `Catalyst-C` `#8CCF8C`.
- **Line width:** `1.55 pt` bold curves matching frame thickness (`1.55 pt`).
- **Labels:** Inline right-side sample labels positioned cleanly above each curve's tail baseline (avoiding overlap with the curve above).
- **Peak Guides (Fig2C):** Short vertical dashed guide lines at `59`, `52`, `30`, `-1` ppm that start at the peak top and stop shortly above the top curve — do NOT stretch full box height.
- **Y-Axis:** Title `Intensity (a.u.)`, numeric y-ticks suppressed (`ticks: []`).

## 5. QA Checklist
- [ ] Sample order bottom-to-top matches `Support < Catalyst-A < Catalyst-B < Catalyst-C`.
- [ ] 27Al NMR x-axis runs high-to-low (`[90, -25]` ppm).
- [ ] Right-side sample labels clear all curves and right spine.
- [ ] Peak guide dashed lines in Fig2C do not cross unrelated curves unnecessarily.

## 6. Common Pitfalls
1. **Treating Rigaku `.asc` as 2-column text** — produces fake 2θ numbers around 2500 instead of 3–40°. Always rebuild 2θ from `*START/*STOP/*STEP`.
2. **Spacing Fig2C too far apart** — 1.05 height spacing leaves huge empty gaps; original uses compact ~0.55 spacing.
3. **Using `xrd_stacked.txt` for crystallinity/area math** — it already contains stacking offsets; use `.ras`/`.asc` for quantitative intensity.
