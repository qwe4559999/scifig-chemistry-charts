# Style & QA Rules (Publication Parity & Blind-Mode Standards)

## 1. Typography & Stroke Standards (Measured from 18 Vector PDFs)

### A. Standard 7.09 in Figures (`Fig1`, `Fig2`, `Fig4`–`Fig6`, `FigS1`–`FigS4`, `FigS11`–`FigS12`)
- **Theme:** `origin-times-bold` (`Times New Roman`, weight `bold`, `mathtext.default = "bf"`)
- **Axis labels & panel letters (`A`/`B`/`C`/`D`):** `14.1 pt` bold
- **Tick labels & legends:** `10.2 pt` bold
- **Subscripts / superscripts:** `~7.0 pt` (via custom Times New Roman bold mathtext, e.g. `Catalyst-A`, `NO$_x$`, `N$_2$`, `50,000 h$^{-1}$`, `$^{27}$Al`, `$^{29}$Si`, `Cu$^{2+}$`)
- **DRIFTS time & peak wavenumber annotations:** `7.1 pt` bold
- **Frames & ticks:** `1.55 pt` black, inward major ticks (`length=3.2 pt`, `width=1.55 pt`)
- **Data lines:** `1.55 pt` (curves/markers) or `0.80 pt` (dense 12-curve DRIFTS stacks)

### B. Wide 1×3 DRIFTS (`FigS9` at `7.09×2.12 in`, `FigS10` at `7.09×2.08 in`)
- Set `"style": {"scale": 0.70}` on `origin-times-bold`:
- **Axis labels & panel letters:** `~9.9 pt` bold
- **Tick labels:** `~7.1 pt` bold
- **Peak / time annotations:** `~4.9 pt` bold
- **Frames:** `~1.08 pt`
- **Data curves:** `~0.56 pt`

### C. Large Single-Panel PDFs (`FigS6` at `9.00×7.68 in`, `FigS7`/`FigS8` at `8.49×7.46 in`)
- Set `"style": {"scale": 2.55}` on `origin-times-bold` to match native PDF visual weight 1:1:
- **Axis labels:** `~36.0 pt` bold
- **Tick labels & legends:** `~26.0 pt` bold
- **Subscripts:** `~17.8 pt`
- **Frames:** `~3.96 pt`
- **Data lines:** `2.04–3.96 pt`

### D. Blind-Mode / New-Submission Themes
- `journal-nature-arial`: Clean Arial sans-serif (`8 pt` labels, `7 pt` ticks, `0.8 pt` spines, Okabe-Ito or Nature NPG palette).
- `journal-acs-serif`: Clean Times New Roman (`9 pt` labels, `8 pt` ticks, `1.0 pt` spines).

## 2. Exact Paper Color Palette (`publication-pastel`)
- **Samples:**
  - `Support`: `#B00F1A`
  - `Catalyst-A`: `#6699BA`
  - `Catalyst-B`: `#CCA8E3`
  - `Catalyst-C`: `#8CCF8C`
  - `Catalyst-D`: `#ABBDDB`
- **GHSV Ramps:**
  - `Catalyst-B` purple ramp (`50k / 100k / 200k`): `#CCA8E3` → `#917ABD` → `#6657A6`
  - `SO2` pair (`without / with`): `#CCA8E3` / `#7D599C`
  - `Catalyst-D` blue ramp (`50k / 100k / 200k`): `#ABBDDB` → `#7599C2` → `#477DB2`
- **Deconvolution Fills (vertical gradient to white):**
  `#B3CDE4`, `#CCEAC4`, `#FBB4AE`, `#DECAE5`, `#B0B0B0`
- **DRIFTS 12-Curve Ramp (bottom → top):**
  `#E0618C` → `#E387B0` → `#F2C4D9` → `#6657A6` → `#917ABD` → `#ABBDDB` → `#4099AB` → `#7DD4A6` → `#40BF7A` → `#1C9666`

## 3. Automated & Visual QA Gate Rules
Every generated figure MUST pass `scifig qa` AND visual inspection before delivery:
1. **Zero text overlaps (`text_overlap_count == 0`)**: No overlapping tick labels, peak annotations, time labels, or panel letters.
2. **Zero clipping (`out_of_bounds == 0`)**: Axis titles, rotated x-ticks, and top legends stay inside the figure canvas.
3. **Zero legend-data collisions**: Legends occupy the sparsest corner (or outside band when specified) without occluding peaks or markers.
4. **Aspect ratio & ink-box parity**: Within `±3%` of target PDF / canvas dimensions (`aspect_ratio_tol <= 0.03`).
5. **Data integrity**: Zero unexpected `NaN` drops, deconvolution residual `|fit - sum(peaks)|` checked, and source-vs-figure discrepancies (e.g. `Fig1A` `Catalyst-A` 200/250 °C) documented in `.provenance.json` instead of silently altered.
6. **Scientific visual invariants**:
   - No per-curve normalization on stacked spectra or DRIFTS time series.
   - Reverse x-axis on IR/DRIFTS (`cm^-1`), NMR (`ppm`), and XPS (`Binding Energy eV`).
   - Parallel `//` break marks on broken axes (`Fig6`, `FigS9`, `FigS11`, `FigS12`), and NO break on `FigS10`.
   - Fixed `[0, 50]` ppm across all 4 panels of `FigS1`.
   - Single clean panel letters on `Fig3` & `FigS5` (no duplicate burned-in + vector letters).
