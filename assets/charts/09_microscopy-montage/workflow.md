# 09_microscopy-montage — Microscopy & EDS Montage Workflow

**Covered Figures:** `Fig3` (3×5 BF-TEM / HAADF / Si / Al / Cu EDS montage), `FigS5` (2×2 SEM montage).

## 1. Data Ingestion
- **Fig3 (TEM/EDS):** `data/raw_tem/` + `mapping.csv`.
  - Use `*BF-TEM_1800px.tif` (`1800×1800`) for column 0 and `Fig.3{A,B,C}-{HAADF,Si,Al,Cu}.tif` (`512×512`) for columns 1–4.
  - Row A = `Catalyst-A` (`50 nm` scale bar), Row B = `Catalyst-B` (`100 nm`), Row C = `Catalyst-C` (`100 nm`).
- **FigS5 (SEM):** `data/raw_sem/` + `mapping.csv` + `*.txt` metadata.
  - `Fig.S5-A.tif` (`Support`), `Fig.S5-B.tif` (`Catalyst-A`), `Fig.S5-C.tif` (`Catalyst-B`), `Fig.S5-D.tif` (`Catalyst-C`), all `1280×960` at `3 kV`, `×20.0k`.

## 2. Preprocessing
- **No false enhancements!** Never alter brightness/contrast unevenly across samples or apply sharpening filters that fabricate lattice fringes or nanoparticles.
- Inspect raw TIFFs visually first (`read_file` or quick check) to see if scale bars / instrument footers are already burned into the bitmap (`README.md` notes scale bars and EDS legends may already be burned in).

## 3. Slot Mapping
| Slot | Fig3 (3×5 TEM/EDS) | FigS5 (2×2 SEM) |
|---|---|---|
| `rows × cols` | `3 × 5` | `2 × 2` |
| `tiles` | `(row, col, source, letter?, badge?, scale_bar?)` | `(row, col, source, letter, scale_bar?)` |
| `gap` | Tight `[0.008, 0.012]` (~2–4 px) | Tight `[0.012, 0.015]` |

## 4. Layout & Annotations
- **Canvas Size:**
  - `Fig3`: `7.09 × 4.24 in` (`510.2 × 305.3 pt`), aspect `1.671`.
  - `FigS5`: `7.09 × 4.94 in` (`510.2 × 355.3 pt`), aspect `1.436`.
- **Panel Letters:** ONE crisp bold `A` / `B` / `C` (or `A` / `B` / `C` / `D` in `FigS5`) per panel/row — never double letters (e.g. a burned-in `A` plus a vector `A`).
- **Element Badges:** Crisp `Si`, `Al`, `Cu` (and `HAADF` if applicable) badges matching `_refs/Fig3.png` position and contrast.
- **Scale Bars:** Verify physical lengths against `mapping.csv` (`50 nm` for 3A, `100 nm` for 3B/3C; SEM footer/scale bar for `FigS5`).

## 5. QA Checklist
- [ ] Every tile matches the exact sample and element in `mapping.csv` (never swap `Cu` and `Al` or `3B` and `3C`!).
- [ ] Single clean panel letter per row/panel (zero duplicate letters).
- [ ] Aspect ratio matches reference PDF within `±3%`; images are not stretched/squished.
- [ ] Tight, uniform inter-tile spacing with zero clipped scale bars or badges.

## 6. Common Pitfalls
1. **Double panel letters on Fig3** — placing vector `A/B/C` on top of or beside a bitmap that already has a letter, or placing letters in every column instead of column 0.
2. **Swapping EDS element maps** — always load directly by filename using `mapping.csv`.
3. **Distorting 1280×960 SEM tiles into square axes** — keep figure height (`4.94 in` for 7.09 in width) aligned to the `4:3` SEM aspect ratio.
