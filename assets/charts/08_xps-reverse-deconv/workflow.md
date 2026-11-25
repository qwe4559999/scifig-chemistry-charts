# 08_xps-reverse-deconv — XPS Reverse-Axis Deconvolution Workflow

**Covered Figures:** `FigS8` (Cu 2p XPS stacked deconvolution for Catalyst-A, Catalyst-B, Catalyst-C).

## 1. Data Ingestion
- **Primary source:** `data/xps_deconv.xlsx` (single sheet, 23 columns = 3 sample blocks separated by blank columns 7 and 15).
  - Block 1 (`0..6`): `Catalyst-C` (`BE`, `Intensity`, `Fitted envelope`, `Fitted Peak Cu2p3`, `Scan A`, `Scan B`, `Backgnd.`).
  - Block 2 (`8..14`): `Catalyst-B`.
  - Block 3 (`16..22`): `Catalyst-A`.
- **Supplementary exports:** `data/xps_species_ratios.csv` and `分峰拟合数据/<sample>/*.DATA/*.xlsx` (`.vgp` needs Avantage software, so always use the exported `.xlsx`/`.csv`).
- **Raw spectra:** `data/raw_xps/<sample>/*.VGD` (Thermo Avantage OLE2 `VGData` stream = `float64` raw counts; divide by `0.05 s × 20 scans` for Cu 2p cps).

## 2. Preprocessing
- **None.** Keep exact Avantage exported envelope, component peaks, and Shirley background (`Backgnd.`).
- Note: Peak fills MUST use `Backgnd.` as `baseline` (not `y = 0`), otherwise shaded areas drop down to zero below the Shirley step.

## 3. Slot Mapping
| Slot | Meaning | Column in Block |
|---|---|---|
| `x` | Binding Energy (eV) | `BE` (col 0 / 8 / 16), **reverse `[high, low]`** |
| `obs` | Experimental raw spectrum | `Intensity` (col 1 / 9 / 17) |
| `fit` | Total fitted envelope | `Fitted envelope` (col 2 / 10 / 18) |
| `peaks` | Component curves | Cols `3, 4, 5` (+ check `.DATA/*.xlsx` if individual sub-peaks for Cu+/Cu2+/satellites are needed) |
| `baseline` | Shirley background | `Backgnd.` (col 6 / 14 / 22) |

## 4. Layout & Annotations
- **Axis Direction:** Strictly **descending** Binding Energy (`[968, 926] eV` or matching `_refs/FigS8.png`).
- **Canvas & Typography:** `FigS8` native PDF is `8.49 × 7.46 in` (`611 × 537 pt`) with `36 pt` labels, `26 pt` ticks, `3.96 pt` frames, and `2.04–3.96 pt` curves. Scale fonts/strokes to match 1:1 visual weight.
- **Colors:** Sample curves `#6699BA` (`Catalyst-A`), `#CCA8E3` (`Catalyst-B`), `#8CCF8C` (`Catalyst-C`); component fills `#B3CDE4`, `#CCEAC4`, `#DECAE5`, `#AFAFAF`.
- **Labels:** Sample names (`Catalyst-A`, `Catalyst-B`, `Catalyst-C`) + species/orbital labels (`Cu+`, `Cu2+`, `Sat.`) matching `_refs/FigS8.png`.

## 5. QA Checklist
- [ ] Binding Energy runs high → low (left → right).
- [ ] Component fills sit cleanly on `Backgnd.` (not dropping to 0).
- [ ] Large-format font sizes and spine widths match `_refs/FigS8.png` visual weight.
- [ ] No overlapping peak/sample labels; `Table S3` Cu⁺/Cu ratios remain consistent (`58.7% / 54.2% / 55.7%`).

## 6. Common Pitfalls
1. **Plotting Binding Energy ascending** — violates universal XPS convention.
2. **Reading `.VGD` as `float32`** — yields `1e22–1e33` garbage; `.VGD` is `float64` (`<f8`).
3. **Filling peaks to `y = 0` instead of `Backgnd.`** — creates giant solid blocks under the baseline.
