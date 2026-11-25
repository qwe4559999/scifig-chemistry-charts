# 04_deconv-peak-fit — Stacked Deconvolution Peak-Fit Workflow

**Covered Figures:** `Fig2D` (29Si MAS NMR), `Fig4A` (NH₃-TPD), `Fig5B` (H₂-TPR).

## 1. Data Ingestion
- **Fig2D (29Si NMR):** `data/29Si_deconv_*.xls` (Origin matrix per sample) + `图2D_29Si分峰_峰面积_*.txt` (peak centers, FWHM, areas, r²).
- **Fig4A (NH₃-TPD):** `data/tpd_deconv_*.txt` (PeakFit 8-col TSV; row 0 is source path -> `skiprows: 1, header: false`).
- **Fig5B (H₂-TPR):** `data/tpr_deconv_*.txt` (same PeakFit 8-col TSV format).

## 2. Preprocessing & Verification
- **Deconvolution Sum Audit:** Before plotting, compute `max(|fit - sum(peaks)|)` (accounting for any baseline offset). For PeakFit exports in this dataset, component sum matches `Y Generated` to `< 1e-12` (or exact baseline + sum).
- **Verify Peak Identity:** `Peak 1..4` in PeakFit files may not match `S1..S4` left-to-right! Sort peaks by peak maximum x-position and verify against `Table S1` / `Table S2` / `README.md`.

## 3. Slot Mapping
| Slot | Meaning | Notes |
|---|---|---|
| `x` | Chemical shift (ppm) or Temperature (°C) | 29Si descending `[-80, -120]` ppm; TPD `100-700` °C; TPR `100-800` °C |
| `obs` | Experimental spectrum | Thin/medium gray `#B0B0B0` or black curve |
| `fit` | Total fitted envelope | Sample-colored curve (`1.18–1.55 pt`) |
| `p1..pN` | Individual Gaussian/Lorentzian peaks | Vertical gradient fills `#B3CDE4`, `#CCEAC4`, `#FBB4AE`, `#DECAE5` |

## 4. Layout & Annotations
- **Seamless Subpanels (`hspace=0`):** Stack samples vertically inside ONE outer `1.55 pt` frame with crisp horizontal dividers. Never leave vertical gaps between sample frames!
- **Sample Order (BOTTOM → TOP — CRITICAL):**
  - `Fig2D` & `Fig4A`: Bottom `Support` (`#B00F1A`) → `Catalyst-A` (`#6699BA`) → `Catalyst-B` (`#CCA8E3`) → Top `Catalyst-C` (`#8CCF8C`).
  - `Fig5B`: Bottom `Catalyst-A` (`#6699BA`) → `Catalyst-B` (`#CCA8E3`) → Top `Catalyst-C` (`#8CCF8C`).
- **Gradient Fills:** Origin-style vertical gradient fading toward white at baseline (`gradient: true`). Flat uniform `alpha` creates muddy brown overlaps!
- **Peak Annotations:** Short vertical ticks + `S1`–`S4` (or `Q1`–`Q4` dashed guides) on the **top subpanel only**, aligned to reported peak centers. Right-side sample labels sit cleanly inside each subpanel.

## 5. QA Checklist
- [ ] Bottom-to-top sample order matches the original paper PDF 1:1.
- [ ] Subpanels are seamlessly stacked (`hspace=0`) with single outer frame and internal dividers.
- [ ] Deconvolution sum residual checked and logged.
- [ ] S1–S4 / Q1–Q4 ticks are short, crisp, and non-overlapping; sample labels clear curves.
- [ ] Note in provenance/QA if subpanel y-limits are scaled independently for readability.

## 6. Common Pitfalls
1. **Reversing vertical sample order in Fig4A** — putting Support at the top instead of bottom breaks visual parity.
2. **Flat alpha fills instead of vertical gradient** — causes overlapping Gaussians to turn muddy brown.
3. **Leaving gaps between sample boxes** — creates cluttered double-horizontal borders instead of Origin's seamless stack.
