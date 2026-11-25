"""Instrument & tabular data readers (no Origin COM dependency).

Supports:
  .spa   OMNIC IR/DRIFTS binary spectra (1884B header + float32)
  .VGD   Thermo Avantage XPS OLE2 compound document (VGData float64 stream)
  .asc   Rigaku XRD ASCII (2-col or *START/*STOP/*STEP block)
  .ras   Rigaku .ras text (*RAS_DATA_START block)
  .spc   Bruker EPR / Shimadzu UV raw float array
  Bruker TopSpin directory (pdata/1/1r + procs) -> ppm axis
  .xlsx/.xls/.xlsm/.csv/.tsv/.txt tabular data
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

SPA_HEADER = 1884
SPA_X0, SPA_X1 = 3999.64, 649.89


def read_spa(path: str) -> pd.DataFrame:
    raw = Path(path).read_bytes()
    head = raw[:SPA_HEADER].decode("latin-1", "replace")
    body = np.frombuffer(raw[SPA_HEADER:], dtype="<f4")
    x = np.linspace(SPA_X0, SPA_X1, body.size)
    df = pd.DataFrame({"wavenumber": x, "absorbance": body})
    if "Linked spectrum at" in head:
        df.attrs["linked"] = head.split("Linked spectrum at")[-1].split(chr(0))[0].strip()
    df.attrs["raw_points"] = int(body.size)
    return df.sort_values("wavenumber").reset_index(drop=True)


def read_vgd(path: str) -> pd.DataFrame:
    try:
        import olefile
    except ImportError as exc:
        raise ImportError("olefile is required to read .VGD files: pip install olefile") from exc
    ole = olefile.OleFileIO(path)
    flat = ["/".join(n) for n in ole.listdir()]
    df = None
    for cand in ("VGData", "VGDATA", "Data"):
        hits = [n for n in flat if n.split("/")[-1].lower() == cand.lower()]
        if hits:
            data = ole.openstream(hits[0]).read()
            counts = np.frombuffer(data[: len(data) // 8 * 8], dtype="<f8")
            df = pd.DataFrame({"point": np.arange(1, counts.size + 1), "counts": counts})
            df.attrs["stream"] = hits[0]
            break
    ole.close()
    if df is None:
        raise ValueError(f"{path}: VGData stream not found; streams={flat}")
    return df


def _two_col(path: Path, xname: str, yname: str, skip_star: bool = True) -> pd.DataFrame:
    rows = []
    for line in path.read_text(encoding="latin-1").splitlines():
        s = line.strip()
        if not s or (skip_star and s.startswith("*")):
            continue
        parts = s.replace(",", " ").replace("\t", " ").split()
        if len(parts) >= 2:
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return pd.DataFrame(rows, columns=[xname, yname]).dropna()


def read_asc(path: str) -> pd.DataFrame:
    p = Path(path)
    lines = p.read_text(encoding="latin-1").splitlines()
    hdr = {}
    for line in lines:
        s = line.strip()
        if s.startswith("*") and "=" in s:
            k, v = s.split("=", 1)
            hdr[k.lstrip("*").strip().upper()] = v.strip()
    body = [line for line in lines if line.strip() and not line.strip().startswith("*")]
    rows = []
    for line in body:
        parts = [t for t in line.replace("\t", ",").replace(" ", ",").split(",") if t.strip()]
        try:
            rows.append([float(t) for t in parts])
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"{p}: no numeric data block found")
    widths = {len(r) for r in rows}
    if widths <= {1, 2} and max(widths) == 2:
        arr = np.array(rows, float)
        return pd.DataFrame({"two_theta": arr[:, 0], "intensity": arr[:, 1]})
    flat = np.concatenate([np.array(r, float) for r in rows])
    start = float(hdr.get("START", 0) or 0)
    stop = float(hdr.get("STOP", 0) or 0)
    step = float(hdr.get("STEP", 0) or 0)
    n = None
    if step and stop > start:
        n = int(round((stop - start) / step)) + 1
        flat = flat[:n]
        x = start + step * np.arange(flat.size)
    else:
        x = np.arange(flat.size, dtype=float)
    df = pd.DataFrame({"two_theta": x, "intensity": flat})
    df.attrs["axis_rebuilt"] = bool(step and stop > start)
    df.attrs["header_points"] = n
    return df


def read_ras(path: str) -> pd.DataFrame:
    text = Path(path).read_text(encoding="latin-1")
    body = text.split("*RAS_DATA_START")[-1]
    rows = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        parts = s.replace(",", " ").replace("\t", " ").split()
        if len(parts) >= 2:
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return pd.DataFrame(rows, columns=["two_theta", "intensity"]).dropna()


def read_spc(path: str) -> pd.DataFrame:
    data = Path(path).read_bytes()
    for dt in ("<f4", "<f8"):
        item = np.dtype(dt).itemsize
        n = len(data) // item
        if n * item == len(data) and n > 64:
            arr = np.frombuffer(data, dtype=dt)
            if np.isfinite(arr).all() and np.abs(arr).max() < 1e12:
                return pd.DataFrame({"point": np.arange(1, arr.size + 1), "value": arr})
    raise ValueError(f"{path}: unable to decode raw float array")


def read_bruker(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.is_file():
        f1r = p
        pdir = p.parents[1] if p.parent.name == "1" else p.parent
    else:
        pdir = p
        f1r = p / "pdata" / "1" / "1r"
    if not f1r.exists():
        raise FileNotFoundError(str(f1r))

    def get(key: str, default=None):
        for cand in (pdir / "pdata" / "1" / "procs", pdir / "procs"):
            if cand.exists():
                for line in cand.read_text(encoding="latin-1").splitlines():
                    if line.startswith(f"##${key}="):
                        v = line.split("=", 1)[1].strip()
                        try:
                            return float(v)
                        except ValueError:
                            return v
        return default

    dt = ">i4" if int(get("BYTORDA", 0) or 0) == 1 else "<i4"
    spec = np.frombuffer(f1r.read_bytes(), dtype=dt).astype(float)
    offset = float(get("OFFSET", 0.0) or 0.0)
    sw_p = float(get("SW_p", 0.0) or 0.0)
    sf = float(get("SF", 1.0) or 1.0)
    si = int(get("SI", spec.size) or spec.size)
    n = min(spec.size, si)
    spec = spec[:n]
    ppm = offset - np.arange(n) * (sw_p / n) / sf
    return pd.DataFrame({"ppm": ppm, "intensity": spec})


def read_table(
    path: str | Path,
    sheet: int | str = 0,
    header: int | bool | None = 0,
    skiprows: int = 0,
    delimiter: str | None = None,
    encoding: str | None = None,
    columns: dict | None = None,
) -> pd.DataFrame:
    """Uniform loader for Excel/CSV/TXT/TSV tables."""
    src = Path(path)
    ext = src.suffix.lower()
    hdr = None if header is False else header
    if ext in (".xlsx", ".xls", ".xlsm"):
        df = pd.read_excel(src, sheet_name=sheet, header=hdr, skiprows=skiprows)
        if isinstance(df, dict):
            df = list(df.values())[0]
        if header is False:
            df.columns = [str(i) for i in range(df.shape[1])]
    else:
        kwargs: dict = {"sep": delimiter if delimiter else None, "engine": "python"}
        if skiprows:
            kwargs["skiprows"] = skiprows
        if header is False:
            kwargs["header"] = None
        enc = encoding or "utf-8-sig"
        try:
            df = pd.read_csv(src, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            df = pd.read_csv(src, encoding="latin-1", **kwargs)
        if header is False:
            df.columns = [str(i) for i in range(df.shape[1])]
    if isinstance(columns, dict) and columns:
        rename_map = {}
        for k, v in columns.items():
            if k in df.columns:
                rename_map[k] = v
            elif str(k).isdigit() and int(k) < len(df.columns):
                rename_map[df.columns[int(k)]] = v
        if rename_map:
            df = df.rename(columns=rename_map)
    return df


def load_any(path: str, **kwargs) -> pd.DataFrame:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".spa":
        return read_spa(str(p))
    if ext == ".vgd":
        return read_vgd(str(p))
    if ext == ".asc":
        return read_asc(str(p))
    if ext == ".ras":
        return read_ras(str(p))
    if ext == ".spc":
        return read_spc(str(p))
    if p.is_dir():
        return read_bruker(str(p))
    if ext in (".xlsx", ".xls", ".xlsm", ".csv", ".txt", ".tsv"):
        return read_table(p, **kwargs)
    raise ValueError(f"{p}: unknown format, specify --reader explicitly")
