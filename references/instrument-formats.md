# Instrument Formats & Data Boundary Reference

All raw and compiled instrument files in `Catalyst-X` (and standard catalysis/characterization workflows) can be ingested via `scifig.readers` except proprietary closed binaries noted below.

## 1. Supported Formats Matrix

| Extension / Type | Instrument / Software | Binary/Text Layout | SciFig Reader | Critical Pitfalls & Rules |
|---|---|---|---|---|
| `.csv` / `.txt` | General / PeakFit / OMNIC export | Delimited text (`UTF-8` or `latin-1`) | `pandas.read_csv` | PeakFit 8-col exports (`Fig4A`, `Fig5B`) have line 0 as file path (`skiprows=1, header=false`); `Peak 1..4` may not follow left-to-right `S1..S4` order. |
| `.xlsx` / `.xls` | Origin / ASAP 2020 / Compiled sheets | OOXML / OLE2 spreadsheet | `openpyxl` / `xlrd` | Origin Excel exports have 3 header rows (`Quantity / Unit / Sample`) with escape tokens (`Catalyst-A`, `\f:Times New Roman`, `NO\-(\i(x))`). DRIFTS union-x Excel sheets have boundary `NaN`s (`dropna: true`). |
| `.spa` | Thermo OMNIC (in situ DRIFTS) | `1884 B` ASCII/binary header + `1738` little-endian `float32` (`<f4`) | `readers.read_spa` | Stored descending (`3999.64 → 649.89 cm^-1`). Header contains `Linked spectrum at ... min`. Do NOT mix `.spa` and `.CSV` intensities under one baseline (`.spa` reflects OMNIC processing). |
| `.VGD` | Thermo Avantage (XPS raw) | OLE2 compound document, `VGData` stream = **`float64` (`<f8`) raw counts** | `readers.read_vgd` | **CRITICAL:** `VGData` is `float64` counts, NOT `float32` (reading as `float32` gives `1e22-1e33` garbage!). Convert to cps via `counts / (0.05 s * n_scans)` or use exported `.DATA/*.xlsx`. |
| `.asc` | Rigaku SmartLab XRD | `*KEY=VALUE` header (`*START`, `*STOP`, `*STEP`) + **intensity-only** 4 values/line | `readers.read_asc` | **CRITICAL:** Package docs incorrectly described `.asc` as 2-column `2θ–intensity`; files actually contain intensity only (`1851` pts) and `2θ` MUST be reconstructed from `*START=3 / *STOP=40 / *STEP=0.02`. |
| `.ras` | Rigaku SmartLab XRD | Block header + `*RAS_DATA_START` two-column data | `readers.read_ras` | Preferred quantitative raw XRD source (alongside reconstructed `.asc`). |
| `.spc` | Bruker EPR / Shimadzu UV-Vis | Bare `float32`/`float64` intensity array without embedded x-axis | `readers.read_spc` | Must be paired with `.par` (JCAMP acquisition parameters) or exported two-column `.txt`/`.csv`/`.xlsx` for physical x-axis calibration. |
| Bruker Dir | Bruker AVANCE NEO MAS NMR (`27Al`, `29Si`) | `fid`, `acqus`, `pdata/1/1r` (`<i4`/`>i4` via `BYTORDA`), `procs` (`OFFSET`, `SW_p`, `SF`, `SI`) | `readers.read_bruker` | Reconstructs `ppm = OFFSET - arange(n)*(SW_p/n)/SF`. Note raw `*-27Al-原始光谱.txt` has 3 significant digits; use `1r` or full-precision `.csv` when high precision is needed. |
| `.tif` / `.png` | Talos F200X G2 TEM/EDS, Hitachi SU8010 SEM | Raster micrographs (`4096×4096`, `1800×1800`, `512×512`, `1280×960`) | `PIL.Image` via `image_montage` | Always check `mapping.csv` and raw bitmaps before overlaying panel letters or scale bars to avoid duplicate letters. |

## 2. Proprietary / Boundary Formats (Honest Scope)

| Extension | Software | Boundary & Sanctioned Workaround |
|---|---|---|
| `.vgp` | Thermo Avantage peak-fitting project (OLE2) | Requires Avantage GUI to open interactively. **Workaround:** Always read the accompanying `.DATA/*.xlsx` / `.xml` and exported summary tables (`xps_deconv.xlsx`, `表S3_Cu2p分峰与Cu价态比例.csv`). |
| `.raw` | Rigaku binary XRD | Closed undocumented binary format; archive only. Use sibling `.ras` or `.asc` files for plotting and analysis. |
