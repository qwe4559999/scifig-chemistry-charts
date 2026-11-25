# 07_drifts-broken-stack — In Situ DRIFTS Workflow

**Covered Figures:** `Fig6` (2×2 main DRIFTS), `FigS9` (1×3 NH₃ adsorption), `FigS10` (1×3 NO+O₂ adsorption, **unbroken**), `FigS11` (1×2 pre-NH₃ + NO+O₂), `FigS12` (1×2 pre-NOₓ + NH₃).

## 1. Data Ingestion
- **Compiled tables:** `data/drifts_panel_*.xlsx`, `drifts_si_*.xlsx`.
  - **Union-x rule:** Because OMNIC CSV exports have slightly different wavenumber endpoints (e.g. `399–4000` vs `399.193–4001.569`), compiled Excel sheets use the union of x-values without interpolation, leaving `NaN` at boundary cells. Always set `dropna: true`.
- **Raw spectra:** `data/raw_drifts/<fig>/原始光谱/*.spa` (`1884 B` header + `1738` little-endian `float32`, descending `3999.64 → 649.89 cm⁻¹`) and `画图数据/*.CSV`. Do not mix `.spa` and `.CSV` intensities under one baseline.

## 2. Preprocessing
- **Baseline & Scaling:** Check raw amplitude range in each sheet (`图6A..6D`, `图S9..S12`). Apply explicit `ops` (`baseline_min`, `baseline_linear`, optional `savgol`) and uniform per-panel `scale` + `offset` in `spec.json` so bands are sharp and **never appear flat** — while preserving relative band growth/decay across curves (no per-curve min-max normalization!).
- **Transparency:** Author's original OMNIC smoothing/baseline parameters are not included in the data package; all `ops` are recorded in `.provenance.json`.

## 3. Slot Mapping
| Slot | Meaning | Notes |
|---|---|---|
| `x` | `Wavenumber (cm^-1)` | Reverse axis (`high → low`) |
| `y` (list) | Ordered time series (or 3 catalysts in Fig6A/B) | Bottom→top: `1 min .. 60 min`, `N2 purge 60 min` |
| `segments` | Optional broken x-axis segments | `[[3800, 3300, w1], [1800, 800, w2]]` for `Fig6/S9/S11/S12`; **OMIT for `FigS10`** (`[1800, 1200]`) |

## 4. Layout & Annotations
- **Canvas & Scaling:**
  - `Fig6` (2×2): `7.09 × 6.02 in`, `14.1/10.2/7.1 pt`, `1.55 pt` frame, `0.80 pt` curves.
  - `FigS9` (`7.09 × 2.12 in`) & `FigS10` (`7.09 × 2.08 in`, 1×3 wide): `9.9 pt` labels, `7.1 pt` ticks, `4.9 pt` annotations, `1.08 pt` frame, `0.56 pt` curves.
  - `FigS11` & `FigS12` (1×2): `7.09 × 3.01 in`, `14.1/10.2/7.1 pt`, `1.55 pt` frame, `0.80 pt` curves.
- **12-Curve Color Ramp (bottom → top):**
  `#E0618C` → `#E387B0` → `#F2C4D9` → `#6657A6` → `#917ABD` → `#ABBDDB` → `#4099AB` → `#7DD4A6` → `#40BF7A` → `#1C9666`.
- **Break Marks (`//`):** Crisp parallel diagonal `//` marks on both top and bottom spines at the axis break.
- **Annotations:**
  - Segment-scoped vertical dashed peak lines (`seg: 0` or `seg: 1`) + staggered/clear wavenumber labels (`7.1 pt` or `4.9 pt` on 1×3).
  - **In-frame** right-side time labels (`1 min .. 60 min`, `NH3` / `NO+O2` + `N2 purge 60 min`), never pushed outside the right spine.
- **Y-Axis:** `Absorbance (a.u.)` (`Fig6`) or `Kubelka-Munk (a.u.)` (`FigS9–S12`), numeric y-ticks suppressed.

## 5. QA Checklist
- [ ] `FigS10` uses unbroken `[1800, 1200]` axis (NO broken axis!).
- [ ] All broken-axis panels (`Fig6`, `FigS9`, `FigS11`, `FigS12`) have parallel `//` break marks on top & bottom spines.
- [ ] Curves are crisp and vertically well-separated (never flat lines).
- [ ] Wavenumber labels and in-frame time labels have 0 overlaps and 0 clipping.

## 6. Common Pitfalls
1. **Adding a broken axis to `FigS10`** — `FigS10` only spans `1800–1200 cm⁻¹`!
2. **Per-curve min-max normalization** — destroys time-evolution kinetic trends (peaks growing/shrinking over 1–60 min).
3. **Mixing `.spa` and `.CSV` intensities** — they have different OMNIC processing baselines.
