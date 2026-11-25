# 06_single-multi-spectrum — Single-Panel Multi-Spectrum Workflow (EPR / UV-Vis)

**Covered Figures:** `Fig5A` (EPR), `FigS7` (UV-Vis-DRS).

## 1. Data Ingestion
- **Fig5A (EPR):** `data/epr.csv` (Magnetic Field G + 3 Cuₓ-MAZ samples) and `图5A_EPR_g值.csv` (g-factor axis). Raw `.spc`/`.par` in `data/raw_epr/`.
- **FigS7 (UV-Vis-DRS):** `data/uv_vis.xlsx` (Wavelength nm + 3 Cuₓ-MAZ samples). Raw `.spc`/`.txt` in `data/raw_uv_vis/`.

## 2. Preprocessing
- **None.** Keep true intensity differences across `Catalyst-A`, `Catalyst-B`, `Catalyst-C` intact — never normalize curves individually.

## 3. Slot Mapping
| Slot | Fig5A (EPR) | FigS7 (UV-Vis-DRS) |
|---|---|---|
| `x` | `Field (G)`, `[2400, 3800]` | `Wavelength (nm)`, `[200, 800]` |
| `series` | `Catalyst-A`, `Catalyst-B`, `Catalyst-C` | `Catalyst-A`, `Catalyst-B`, `Catalyst-C` |
| `annotations` | Hyperfine comb bracket `g_// = 2.38, A_// = 149 G` + `g_perp = 2.08` | Vertical dashed lines + peak labels at `209`, `258`, `724` nm |

## 4. Layout & Annotations
- **Colors:** `Catalyst-A` `#6699BA`, `Catalyst-B` `#CCA8E3`, `Catalyst-C` `#8CCF8C`.
- **Fig5A Specifics:**
  - Legend in `lower left` inside frame.
  - Use `comb` primitive for the hyperfine quartet teeth spanning the `g_//` multiplet, with clean mathtext `g$_{//}$=2.38   A$_{//}$=149 G`.
  - No minor ticks on x-axis (matches reference PDF).
- **FigS7 Specifics:**
  - Native PDF is large format (`8.49 × 7.46 in`) with `36 pt` labels, `26 pt` ticks/legends, `3.96 pt` frames and bold `3.0–3.96 pt` spectra. Scale font/line sizes proportionally to match visual weight!
  - Top-right legend clear of the `209/258 nm` UV peak and `724 nm` d–d band.

## 5. QA Checklist
- [ ] Curves preserve true relative amplitudes across samples.
- [ ] `Fig5A` comb teeth match actual quartet peak positions and label `g_//`, `A_//`, `g_perp` cleanly.
- [ ] `FigS7` peak labels (`209`, `258`, `724`) do not collide with spectra or frame edges.
- [ ] `FigS7` visual weight matches the bold single-panel PDF reference.

## 6. Common Pitfalls
1. **Using small 10.2/14.1 pt fonts on an 8.49×7.46 in FigS7 canvas** — produces spidery, undersized text compared to the `36/26 pt` reference.
2. **Writing `g//` instead of `g$_{//}$`** — raw slashes sit too high and clash with `=`.
3. **Reading `.spc` alone without `.par`/`.txt`** — `.spc` has no x-axis array; always use the paired CSV/XLSX/TXT.
