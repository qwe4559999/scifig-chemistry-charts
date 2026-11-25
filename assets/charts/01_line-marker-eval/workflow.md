# 01_line-marker-eval — Catalytic Evaluation Line-Marker Workflow

**Covered Figures:** `Fig1` (2×2 SCR conversion/selectivity), `FigS1` (2×2 N₂O/NO₂ concentration), `FigS2` (1×2 SO₂ effect), `FigS3` (1×2 MAZ vs CHA), `FigS4` (1×2 Catalyst-D GHSVs).

## 1. Data Ingestion
- **Primary sources:** `examples/demo_eval.csv`, `图S1_*.xlsx` .. `图S4_*.xlsx`.
- **Raw backup:** `data/raw_eval.xlsx` (per-sample sheets with raw `NO in/out`, `NO2 out`, `N2O out`, `NH3 in/out`).
- **Header quirk:** Origin-exported `.xlsx` sheets have 3 metadata rows (`Quantity` / `Unit` / `Sample`) containing Origin escape tokens such as `\f:Times New Roman(°C)`, `NO\-(\i(x))`, `Catalyst-A`. Read with `header=2` (or inspect first 4 rows) and map columns explicitly by index or cleaned name.

## 2. Preprocessing
- **None by default.** Never smooth or interpolate discrete temperature evaluation points (150, 175, 200, ..., 550 °C).
- Check for NaN or missing temperature points.
- **Discrepancy audit:** In `Fig1A`, `Catalyst-A` source table reports `65.6%` (200 °C) and `92.8%` (250 °C), whereas the published figure shows ~37% and ~67%. Always plot exact source table values and record the conflict in `.provenance.json` / notes.

## 3. Slot Mapping
| Slot | Meaning | Example |
|---|---|---|
| `x` | Reaction temperature (°C) | `150 .. 550` |
| `y` (1..N) | Activity / selectivity / concentration | `Catalyst-A`, `Catalyst-B`, `Catalyst-C` or `50,000 h^-1`, `100,000 h^-1`, `200,000 h^-1` |
| `note` | Condition line aligned below legend | `GHSV = 50,000 h$^{-1}$` or `Catalyst-B` |

## 4. Layout & Annotations
- **Canvas:** 2×2 grid at `7.09 × 5.97–6.00 in` (`Fig1`, `FigS1`); 1×2 grid at `7.09 × 3.08 in` (`FigS2`–`FigS4`).
- **Colors & Markers:**
  - `Catalyst-A`: `#6699BA` (square `s`), `Catalyst-B`: `#CCA8E3` (circle `o`), `Catalyst-C`: `#8CCF8C` (triangle `^`).
  - GHSV purple ramp (`Fig1C/D`, `FigS1C/D`): `#CCA8E3` (50k) → `#917ABD` (100k) → `#6657A6` (200k).
  - SO₂ (`FigS2`): `#CCA8E3` (without SO₂) vs `#7D599C` (with SO₂).
  - CHA comparison (`FigS3`): `#CCA8E3` (`Catalyst-B`) vs `#ABBDDB` (`Catalyst-D`).
  - CHA GHSV blue ramp (`FigS4`): `#ABBDDB` → `#7599C2` → `#477DB2`.
- **Y-Axis Rules:**
  - Conversion/Selectivity: `[0, 102]` (or `[0, 100]` matching reference), ticks `[0, 20, 40, 60, 80, 100]`.
  - `FigS1` N₂O/NO₂: **FIXED `[0, 50]` ppm** on all 4 panels (`A, B, C, D`). Never autoscale!
- **Legend:** Placed inside the sparsest corner (`lower right` for conversion, `lower left`/`center right` for selectivity, `upper left` for byproduct peaks), with `frameon=false` and aligned condition note (`GHSV = 50,000 h$^{-1}$` or `Catalyst-B`).

## 5. QA Checklist
- [ ] All 4 panels (or 2 panels) have uniform 1.55 pt frames, inward ticks, 14.1 pt bold labels/letters, 10.2 pt ticks/legends.
- [ ] Subscripts (`NO$_x$`, `N$_2$O`, `NO$_2$`, `Catalyst-B`, `h$^{-1}$`) are bold and crisp without awkward italic imbalance.
- [ ] No legend text collides with data curves or markers.
- [ ] `FigS1` y-axis is strictly `[0, 50]` on all 4 panels.
- [ ] No spurious error bars added when none exist in reference.

## 6. Common Pitfalls
1. **Autoscaling `FigS1` panels independently** — hides the dramatic difference between low and high byproduct levels across panels.
2. **Using hollow markers or errorbar legend caps** — reference uses solid filled markers (`mfc=color, mec=color`) and clean line+marker legend handles.
3. **Blindly overwriting Fig1A source numbers** — keep source numbers and flag the 200/250 °C conflict honestly.
