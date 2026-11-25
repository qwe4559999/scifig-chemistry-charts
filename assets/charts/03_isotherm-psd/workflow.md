# 03_isotherm-psd — N₂ Isotherm & Pore Size Distribution Workflow

**Covered Figures:** `Fig2B` (N₂ adsorption-desorption isotherms), `FigS6` (pore size distribution).

## 1. Data Ingestion
- **Fig2B:** `data/n2_isotherms.xlsx` — single sheet, 16 columns (4 samples × [ads P/P₀, ads V, des P/P₀, des V]). Row 2/3 encodes sample names (`Support`, `Catalyst-A`, etc.).
- **FigS6:** `data/pore_size_dist.xlsx` — single sheet, 8 columns (`Pore Diameter`, `dV/dlong(W)` × 4 samples). Note the author's column header spelling `dV/dlong(W)`!
- **Raw backup:** `data/raw_bet/*.XLS` (ASAP 2020 multi-section reports).

## 2. Preprocessing
- **None.** Keep exact tabular values; strip NaN tail rows per pair (`dropna: true`) because each sample has slightly different pore diameter / pressure point counts.
- **Verify physical meaning for FigS6:** Confirm values are differential pore volume `dV/dlog(W)` peaking around `0.1–0.6 cm³/g` near `~1 nm`, NOT cumulative pore volume.

## 3. Slot Mapping
| Slot | Fig2B (Isotherm) | FigS6 (PSD) |
|---|---|---|
| `x` | `Relative pressure (P/P0)` in `[0, 1]` | `Pore Diameter (nm)` in `[0.7, 5.0]` |
| `y` | Ads + Des pairs (`cm^3/g STP`) | `dV/dlog(W)` (`cm^3/g`) |
| `branch` | Ads = solid marker, Des = hollow marker (or matched pair) | Solid circle markers + connecting line |

## 4. Layout & Annotations
- **Fig2B (subplot of 2×2 Fig2):** `P/P0` `[0, 1]`, `Quantity adsorbed` `[0, 160] cm³/g`, legend inside `upper left` or `lower right` clear of hysteresis loop.
- **FigS6 (large standalone SI PDF):** Native PDF size is `9.00 × 7.68 in` (`648 × 553 pt`) with **scaled bold typography** (`36 pt` axis labels, `26 pt` tick/legend text, `3.96 pt` frames, `0.96–2.5 pt` curves/markers) — if rendering at 9.00×7.68 in, pass explicit scaled sizes in `style` or `theme` overrides so the visual weight matches `_refs/FigS6.png` 1:1!
- **Colors:** `Support` `#B00F1A`, `Catalyst-A` `#6699BA`, `Catalyst-B` `#CCA8E3`, `Catalyst-C` `#8CCF8C`.

## 5. QA Checklist
- [ ] `FigS6` plots `dV/dlog(W)` (peak ~0.6 cm³/g, linear x `[0.7, 5]`), NOT cumulative volume or log-x if reference is linear.
- [ ] `FigS6` fonts and frame thickness match the bold single-panel PDF weight.
- [ ] `Fig2B` desorption branch is clearly distinguishable and ordered without stray cross-lines.
- [ ] No NaNs or dropped series; top-right legend in `FigS6` sits cleanly in empty space.

## 6. Common Pitfalls
1. **Plotting cumulative pore volume in `FigS6`** — a major error from earlier attempts. Always inspect column headers and peak range (`0.0–0.7`).
2. **Using standard 10.2/14.1 pt fonts on a 9.0×7.68 in `FigS6` canvas** — makes all text look tiny compared to the `36/26 pt` native PDF.
3. **Leaving NaNs across uneven-length paired columns** — always set `dropna: true` on each `(x, y)` series.
