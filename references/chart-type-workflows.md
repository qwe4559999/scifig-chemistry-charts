# Chart-Type Workflows (9 Canonical Chemistry Charts)

This reference summarizes the 9 canonical chart workflows in `assets/charts/`, covering 100% of Main (`Fig1`–`Fig6`) and SI (`FigS1`–`FigS12`) figures.

| ID | Name | Covered Figures | Key Primitives & Invariants |
|---|---|---|---|
| `01_line-marker-eval` | Catalytic Evaluation Line-Marker | `Fig1`, `FigS1`–`FigS4` | `line_marker` solid markers; fixed `[0, 102]` for % conversion/selectivity; **fixed `[0, 50]` ppm across all 4 panels of `FigS1`**; aligned condition note below legend; preserve source numbers on conflicts. |
| `02_stacked-spectra` | Stacked Spectra (XRD / ²⁷Al NMR) | `Fig2A`, `Fig2C` | Explicit vertical offsets (no per-curve min-max norm); ascending `2θ` `[3, 40]` for XRD; descending `ppm` `[90, -25]` for ²⁷Al NMR; short dashed peak guides stopping cleanly near peaks. |
| `03_isotherm-psd` | N₂ Isotherm & Pore Size Distribution | `Fig2B`, `FigS6` | Paired ads/des branches for `Fig2B`; **differential `dV/dlog(W)` vs linear Diameter `[0.7, 5.0]` nm for `FigS6`** (never cumulative volume!); large-format bold font scaling (`36/26 pt`) at `9.00 × 7.68 in`. |
| `04_deconv-peak-fit` | Stacked Deconvolution Peak-Fit | `Fig2D`, `Fig4A`, `Fig5B` | Seamless `hspace=0` subpanels inside single `1.55 pt` outer frame; Origin-style vertical-gradient pastel fills (`#B3CDE4`, `#CCEAC4`, `#FBB4AE`, `#DECAE5`); exact sample bottom→top order (`Support` bottom in `Fig4A`); `S1`–`S4` / `Q1`–`Q4` ticks on top subpanel only. |
| `05_stacked-bar-comp` | 100% Stacked Composition Bar | `Fig4B` | `bar_stacked` with `gradient: true`; centered bold integer percentages; top horizontal 4-col gradient legend; `20°` rotated bold x-labels; colors mapped to acid sites `S1`–`S4` (not samples). |
| `06_single-multi-spectrum` | Single-Panel Multi-Spectrum | `Fig5A`, `FigS7` | Unstacked multi-curve overlay preserving relative amplitude; `comb` hyperfine bracket (`g$_{//}$=2.38`, `A$_{//}$=149 G`, `g$_{\\perp}$=2.08`) for `Fig5A`; vertical dashed peak guides (`209`, `258`, `724` nm) & large-format `36/26 pt` scaling (`8.49 × 7.46 in`) for `FigS7`. |
| `07_drifts-broken-stack` | In Situ DRIFTS Stack | `Fig6`, `FigS9`–`FigS12` | Reverse wavenumber axis; broken axis `[[3800, 3300], [1800, 800]]` with parallel `//` marks on `Fig6`, `FigS9`, `FigS11`, `FigS12`; **UNBROKEN `[1800, 1200]` on `FigS10`**; transparent `ops` (`baseline_min` / `savgol`); in-frame right time labels; 12-curve pink→purple→blue→green ramp. |
| `08_xps-reverse-deconv` | XPS Reverse-Axis Deconvolution | `FigS8` | Reverse Binding Energy (`[968, 926]` eV); component fills anchored to `Backgnd.` (Shirley baseline, not `y=0`); large-format `36/26 pt` scaling (`8.49 × 7.46 in`); Table S3 Cu⁺/Cu consistency check. |
| `09_microscopy-montage` | Microscopy & EDS Montage | `Fig3`, `FigS5` | `image_montage` panel loading raw TIFFs (`1800×1800` + `512×512` for `Fig3` 3×5; `1280×960` for `FigS5` 2×2); tight pixel gaps; single clean `A/B/C(/D)` letters (never double letters); crisp `Si`/`Al`/`Cu` badges & verified scale bars. |

## Selecting a Chart Type in Blind Mode
When given only raw/tidy data without a reference image:
1. **Discrete T / time vs % conversion or ppm concentration** → `01_line-marker-eval`
2. **Multiple 1D spectra (XRD 2θ or un-deconvoluted NMR) stacked vertically** → `02_stacked-spectra`
3. **P/P₀ isotherm (2 branches/sample) or dV/dlog(W) pore size curve** → `03_isotherm-psd`
4. **Observed + Total Fit + N Gaussian/Lorentzian peaks across samples** → `04_deconv-peak-fit` (or `08_xps-reverse-deconv` if x is Binding Energy eV descending)
5. **Sample × component % matrix (~100% row sums)** → `05_stacked-bar-comp`
6. **2–4 unstacked spectra sharing true baseline (EPR / UV-Vis)** → `06_single-multi-spectrum`
7. **Time-resolved DRIFTS / FTIR wavenumber matrix (check 2000–3200 silent gap)** → `07_drifts-broken-stack`
8. **Microscopy TIFF/PNG grid** → `09_microscopy-montage`
