"""Blind / No-Reference Figure Planner (blind_planner.py).

Generates publication-ready SciFigStudio specs and figures from ONLY:
  (a) raw/tidy data path(s),
  (b) chart type ID (from assets/charts/),
  (c) theme (e.g. origin-times-bold or journal-nature-arial),
  (d) basic caption/title.

Zero reference PDF/image, zero _refs/_blueprints lookups, zero hardcoded coordinates,
offsets, or peak positions. Performs up to 3 QA-driven auto-repair iterations.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

from . import engine, qa as qa_mod, readers, theme as theme_mod

STUDIO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- text & Origin cleanup
_SAFE_CHEM_SUBS = [
    (r"\b([A-Z][a-z]?)(\d+(?:\.\d+)?)-([A-Z]{2,5})\b", lambda m: f"{m.group(1)}$_{{{m.group(2)}}}$-{m.group(3)}"),
    (r"\bCu2\+", "Cu$^{2+}$"),
    (r"\bCu\+", "Cu$^+$"),
    (r"\b27Al\b", "$^{27}$Al"),
    (r"\b29Si\b", "$^{29}$Si"),
    (r"\bNOx\b", "NO$_x$"),
    (r"\bN2O\b", "N$_2$O"),
    (r"\bNO2\b", "NO$_2$"),
    (r"\bSO2\b", "SO$_2$"),
    (r"\bNH3\b", "NH$_3$"),
    (r"\bCO2\b", "CO$_2$"),
    (r"\bH2O\b", "H$_2$O"),
    (r"\bN2\b", "N$_2$"),
    (r"\bH2\b", "H$_2$"),
    (r"\bO2\b", "O$_2$"),
    (r"cm\^-1", "cm$^{-1}$"),
    (r"h\^-1", "h$^{-1}$"),
    (r"cm3/g", "cm$^3$/g"),
    (r"m2/g", "m$^2$/g"),
]


def _safe_chem_mathtext(s: str) -> str:
    if not s or "$" in s:
        return s
    out = str(s)
    for pat, rep in _SAFE_CHEM_SUBS:
        out = re.sub(pat, rep, out)
    return out


def clean_origin_markup(text: Any) -> str:
    """Strip Origin escape sequences (\\-(...), \\+(...), \\i(...), \\f:Font(...)) into clean text."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    s = str(text).strip()
    if not s or s.lower() == "nan" or s.startswith("Unnamed:"):
        return ""
    # Unwrap \f:FontName(...)
    s = re.sub(r"\\f:[^()]*\(([^)]*)\)", r"\1", s)
    # Unwrap \i(...) italic
    s = re.sub(r"\\i\(([^)]*)\)", r"\1", s)
    # Subscripts \-(...) and superscripts \+(...)
    s = re.sub(r"\\\-\(([^)]*)\)", r"$_{\1}$", s)
    s = re.sub(r"\\\+\(([^)]*)\)", r"$^{\1}$", s)
    # Merge adjacent $...$$...$ spans if any
    s = s.replace("$$", "")
    # Common typo / missing glyph normalization in Arial & raw Origin tables
    s = s.replace("dV/dlong(W)", "dV/dlog(W)").replace("Volumn", "Volume").replace("℃", "°C")
    if "$" not in s:
        s = _safe_chem_mathtext(s)
    return s.strip()


def _plain_token(text: Any) -> str:
    s = clean_origin_markup(text)
    s = re.sub(r"\$[_^]?\{?([^}$]*)\}?\s*\$?", r"\1", s)
    return s.replace("$", "").strip()


def _is_numeric_cell(val: Any) -> bool:
    if val is None or isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return np.isfinite(val)
    try:
        v = float(str(val).strip())
        return np.isfinite(v)
    except Exception:
        return False


def _nice_ceil(val: float, pad_frac: float = 0.10) -> float:
    if val <= 0:
        return 1.0
    target = val * (1.0 + pad_frac)
    mag = 10.0 ** np.floor(np.log10(target))
    for mult in (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if mult * mag >= target:
            return round(float(mult * mag), 6)
    return round(float(10.0 * mag), 6)


def _nice_ticks(lo: float, hi: float, n_target: int = 6) -> list[float]:
    span = abs(hi - lo)
    if span <= 1e-12:
        return [lo]
    raw_step = span / max(2, n_target - 1)
    mag = 10.0 ** np.floor(np.log10(raw_step))
    step = mag
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if mult * mag >= raw_step * 0.85:
            step = mult * mag
            break
    a, b = min(lo, hi), max(lo, hi)
    start = np.ceil((a - 1e-9 * span) / step) * step
    ticks = []
    cur = start
    while cur <= b + 1e-9 * span:
        v = round(float(cur), 6)
        if abs(v - round(v)) < 1e-6:
            v = int(round(v))
        ticks.append(v)
        cur += step
    if lo > hi:
        ticks = list(reversed(ticks))
    return ticks


# ---------------------------------------------------------------- source inspection
def _inspect_excel_sheet(path: Path, sheet: int | str = 0) -> dict:
    """Inspect an Excel sheet, auto-detecting Origin multi-row headers and numeric data start."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    # Keep original row indices intact so skiprows matches pd.read_excel exactly
    data_start = 0
    for r in range(min(12, len(raw))):
        row_vals = raw.iloc[r].tolist()
        n_num = sum(1 for v in row_vals if _is_numeric_cell(v))
        n_nonempty = sum(1 for v in row_vals if v is not None and not (isinstance(v, float) and np.isnan(v)))
        if n_num >= 2 or (n_nonempty >= 2 and n_num >= 1 and r >= 1 and _is_numeric_cell(row_vals[1] if len(row_vals) > 1 else None)):
            data_start = r
            break

    ncols = raw.shape[1]
    meta_rows = raw.iloc[:data_start]
    col_meta = []
    for c in range(ncols):
        parts = []
        for r in range(data_start):
            v = meta_rows.iloc[r, c]
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                sv = str(v).strip()
                if sv:
                    parts.append(sv)
        long_name = parts[0] if len(parts) >= 1 else f"Col {c}"
        unit = parts[1] if len(parts) >= 2 else ""
        comment = parts[-1] if len(parts) >= 2 else (parts[0] if parts else f"Series {c}")
        if len(parts) >= 3:
            long_name, unit, comment = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            if any(u in parts[1].lower() for u in ("%", "a.u", "ev", "nm", "cm", "g", "°c", "℃", "p/p")):
                long_name, unit, comment = parts[0], parts[1], parts[0]
            else:
                long_name, unit, comment = parts[0], "", parts[1]
        col_meta.append({
            "idx": c,
            "raw_parts": parts,
            "long_name": clean_origin_markup(long_name),
            "unit": clean_origin_markup(unit),
            "comment": clean_origin_markup(comment),
            "plain_long": _plain_token(long_name),
            "plain_unit": _plain_token(unit),
            "plain_comment": _plain_token(comment),
        })

    df_num = raw.iloc[data_start:].dropna(how="all", axis=0).copy().reset_index(drop=True)
    df_num.columns = [str(i) for i in range(ncols)]
    return {
        "path": path,
        "kind": "excel",
        "sheet": sheet,
        "skiprows": int(data_start),
        "header": False,
        "col_meta": col_meta,
        "df": df_num,
    }


def _inspect_text_or_inst(path: Path) -> dict:
    """Inspect CSV/TXT/PeakFit/instrument files cleanly."""
    ext = path.suffix.lower()
    if ext in (".spa", ".vgd", ".asc", ".ras", ".spc") or path.is_dir():
        df = readers.load_any(str(path))
        col_meta = [
            {
                "idx": i,
                "raw_parts": [str(c)],
                "long_name": clean_origin_markup(c),
                "unit": "",
                "comment": clean_origin_markup(c),
                "plain_long": str(c),
                "plain_unit": "",
                "plain_comment": str(c),
            }
            for i, c in enumerate(df.columns)
        ]
        df_s = df.copy()
        df_s.columns = [str(i) for i in range(df.shape[1])]
        return {"path": path, "kind": "instrument", "sheet": 0, "skiprows": 0, "header": 0, "col_meta": col_meta, "df": df_s}

    # Text / CSV: peek first 5 lines to detect PeakFit metadata line or delimiter
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    first = lines[0].strip() if lines else ""
    skiprows = 0
    header_mode: int | bool = 0
    delim = None
    # Detect PeakFit quoted multi-column header with source file path in col 0
    if first.startswith('"') and ("\\" in first or "Observed" in first or "Peak" in first):
        import shlex
        try:
            toks = shlex.split(first)
        except Exception:
            toks = first.split()
        skiprows = 1
        header_mode = False
        df = pd.read_csv(path, sep=r"\s+", skiprows=1, header=None, engine="python")
        col_names = toks[: df.shape[1]]
        col_meta = []
        for i in range(df.shape[1]):
            cname = col_names[i] if i < len(col_names) else f"Col {i}"
            col_meta.append({
                "idx": i, "raw_parts": [cname], "long_name": clean_origin_markup(cname),
                "unit": "", "comment": clean_origin_markup(cname),
                "plain_long": cname, "plain_unit": "", "plain_comment": cname,
            })
        df.columns = [str(i) for i in range(df.shape[1])]
        return {"path": path, "kind": "peakfit_txt", "sheet": 0, "skiprows": 1, "header": False, "delimiter": r"\s+", "col_meta": col_meta, "df": df}

    df = readers.read_table(path)
    col_meta = [
        {
            "idx": i, "raw_parts": [str(c)], "long_name": clean_origin_markup(c),
            "unit": "", "comment": clean_origin_markup(c),
            "plain_long": str(c), "plain_unit": "", "plain_comment": str(c),
        }
        for i, c in enumerate(df.columns)
    ]
    df_s = df.copy()
    df_s.columns = [str(i) for i in range(df.shape[1])]
    return {"path": path, "kind": "table", "sheet": 0, "skiprows": 0, "header": 0, "col_meta": col_meta, "df": df_s}


def inspect_sources(data_paths: list[str | Path], max_sheets: int | None = None) -> list[dict]:
    sources = []
    for p in data_paths:
        path = Path(p).resolve()
        if path.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
            xl = pd.ExcelFile(path)
            sheets = xl.sheet_names[:max_sheets] if max_sheets else xl.sheet_names
            for sh in sheets:
                sources.append(_inspect_excel_sheet(path, sh))
        else:
            sources.append(_inspect_text_or_inst(path))
    return sources


def _num_arr(df: pd.DataFrame, col_idx: int) -> np.ndarray:
    return pd.to_numeric(df.iloc[:, col_idx], errors="coerce").to_numpy(dtype=float)


def _data_entry(key: str, src_info: dict) -> dict:
    entry: dict[str, Any] = {"source": str(src_info["path"])}
    if src_info["kind"] == "excel":
        entry["sheet"] = src_info["sheet"]
        entry["header"] = src_info["header"]
        entry["skiprows"] = src_info["skiprows"]
    elif src_info["kind"] == "peakfit_txt":
        entry["header"] = False
        entry["skiprows"] = src_info["skiprows"]
        entry["delimiter"] = src_info.get("delimiter", r"\s+")
    return entry


# ---------------------------------------------------------------- semantic & geometry helpers
def _sparse_corner_ranking(series_xy: list[tuple[np.ndarray, np.ndarray]], xlim: list[float], ylim: list[float], n_items: int) -> list[str]:
    """Rank legend corners from least data overlap to most data overlap."""
    x0, x1 = float(xlim[0]), float(xlim[1])
    y0, y1 = float(ylim[0]), float(ylim[1])
    dx = x1 - x0 if abs(x1 - x0) > 1e-12 else 1.0
    dy = y1 - y0 if abs(y1 - y0) > 1e-12 else 1.0

    # Transform all curves into normalized [0, 1] box coordinates
    pts_norm = []
    for xv, yv in series_xy:
        ok = np.isfinite(xv) & np.isfinite(yv)
        if not np.any(ok):
            continue
        xn = (xv[ok] - x0) / dx
        yn = (yv[ok] - y0) / dy
        pts_norm.append(np.column_stack([xn, yn]))
        # Also sample midpoints along line segments to catch crossing lines
        if xn.size >= 2:
            for t in (0.25, 0.5, 0.75):
                pts_norm.append(np.column_stack([xn[:-1] + t * np.diff(xn), yn[:-1] + t * np.diff(yn)]))
    all_pts = np.vstack(pts_norm) if pts_norm else np.zeros((0, 2))

    bw = 0.34
    bh = min(0.45, 0.08 + 0.075 * max(1, n_items))
    candidates = {
        "upper right": (1.0 - bw - 0.03, 1.0 - bh - 0.03, 0.98, 0.98),
        "upper left": (0.03, 1.0 - bh - 0.03, 0.03 + bw, 0.98),
        "lower right": (1.0 - bw - 0.03, 0.03, 0.98, 0.03 + bh),
        "lower left": (0.03, 0.03, 0.03 + bw, 0.03 + bh),
    }
    scored = []
    for loc, (cx0, cy0, cx1, cy1) in candidates.items():
        if all_pts.shape[0] == 0:
            hits = 0
        else:
            inside = (all_pts[:, 0] >= cx0) & (all_pts[:, 0] <= cx1) & (all_pts[:, 1] >= cy0) & (all_pts[:, 1] <= cy1)
            hits = int(np.sum(inside))
        scored.append((hits, loc))
    scored.sort(key=lambda r: r[0])
    return [loc for _, loc in scored]


def _auto_peaks(x: np.ndarray, y: np.ndarray, x_lo: float, x_hi: float, max_peaks: int = 6,
                include_negative: bool = False, min_sep_frac: float = 0.075) -> list[float]:
    """Detect top prominent peaks (and optional negative dips for DRIFTS OH) purely from data."""
    ok = np.isfinite(x) & np.isfinite(y) & (x >= min(x_lo, x_hi)) & (x <= max(x_lo, x_hi))
    if np.sum(ok) < 15:
        return []
    xs, ys = x[ok], y[ok]
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    win = min(11, (xs.size // 4) * 2 + 1)
    ys_s = savgol_filter(ys, win, 2) if win >= 5 else ys
    span = max(float(np.ptp(ys_s)), 1e-12)
    dx_span = max(float(xs[-1] - xs[0]), 1e-9)
    min_dist_pts = max(3, int(round(min_sep_frac * xs.size)))

    cands = []
    p_pos, props_pos = find_peaks(ys_s, prominence=0.06 * span, distance=min_dist_pts)
    for idx, prom in zip(p_pos, props_pos["prominences"]):
        cands.append((float(prom), float(xs[idx])))
    if include_negative:
        p_neg, props_neg = find_peaks(-ys_s, prominence=0.08 * span, distance=min_dist_pts)
        for idx, prom in zip(p_neg, props_neg["prominences"]):
            cands.append((float(prom), float(xs[idx])))

    cands.sort(key=lambda t: -t[0])
    chosen: list[float] = []
    for _, px in cands:
        if all(abs(px - ox) >= min_sep_frac * dx_span for ox in chosen):
            chosen.append(px)
        if len(chosen) >= max_peaks:
            break
    return sorted(chosen)


def _guess_palette_color(label: str, idx: int, palette: str) -> str:
    """Resolve sample color token into a hex color from the active palette."""
    pal_dict = theme_mod.load_palette(palette)
    plain = _plain_token(label)
    if palette == "publication-pastel":
        for key in ("Support", "Catalyst-A", "Catalyst-B", "Catalyst-C", "Catalyst-D"):
            if key.lower() in plain.lower().replace(" ", ""):
                return theme_mod.resolve_color(key, pal_dict, idx)
        if "50,000" in plain or "50k" in plain.lower():
            return theme_mod.resolve_color("GHSV-50k", pal_dict, idx)
        if "100,000" in plain or "100k" in plain.lower():
            return theme_mod.resolve_color("GHSV-100k", pal_dict, idx)
        if "200,000" in plain or "200k" in plain.lower():
            return theme_mod.resolve_color("GHSV-200k", pal_dict, idx)
    return theme_mod.resolve_color(f"seq:{idx}", pal_dict, idx)


# ---------------------------------------------------------------- per-chart planners
def _plan_line_marker(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    n = len(sources)
    cols = 2 if n > 2 else n
    rows = int(np.ceil(n / cols))
    w_in = 7.09
    h_in = 5.95 if rows == 2 else 3.05
    data_cfg = {}
    panels = []
    markers = ["s", "o", "^", "D", "v", "P"]
    corner_rankings = {}

    for pi, src in enumerate(sources):
        dkey = f"d{pi}"
        data_cfg[dkey] = _data_entry(dkey, src)
        df = src["df"]
        cm = src["col_meta"]
        xv = _num_arr(df, 0)
        x_ok = xv[np.isfinite(xv)]
        xmin, xmax = float(x_ok.min()), float(x_ok.max())
        xpad = 0.04 * max(xmax - xmin, 1.0)
        xlim = [round(xmin - xpad, 3), round(xmax + xpad, 3)]
        xticks = _nice_ticks(xmin, xmax, 5)

        y_cols = [i for i in range(1, df.shape[1]) if np.isfinite(_num_arr(df, i)).any()]
        series_xy = [(xv, _num_arr(df, ci)) for ci in y_cols]
        y_all = np.concatenate([y[np.isfinite(y)] for _, y in series_xy])
        y_unit = cm[y_cols[0]]["plain_unit"] if y_cols else ""
        y_name = cm[y_cols[0]]["long_name"] if y_cols else "Response"
        y_plain = cm[y_cols[0]]["plain_long"].lower() if y_cols else ""

        if ("%" in y_unit or "conversion" in y_plain or "selectivity" in y_plain) and y_all.max() <= 105 and y_all.min() >= -2:
            ylim = [0, 102]
            yticks = [0, 20, 40, 60, 80, 100]
        else:
            yhi = _nice_ceil(float(y_all.max()), 0.12)
            ylim = [0, yhi]
            yticks = _nice_ticks(0, yhi, 6)

        if "conversion" in y_plain and "no" in y_plain:
            ylabel = "NO$_x$ conversion (%)"
        elif "selectivity" in y_plain and "n2" in y_plain.replace(" ", ""):
            ylabel = "N$_2$ selectivity (%)"
        else:
            ylabel = f"{y_name} ({cm[y_cols[0]]['unit']})" if cm[y_cols[0]]["unit"] else y_name

        xlabel = cm[0]["long_name"] or "Temperature"
        xunit = cm[0]["unit"] or "°C"
        if xunit and xunit not in xlabel:
            xlabel = f"{xlabel} ({xunit})"

        plots = []
        for idx, ci in enumerate(y_cols):
            lbl = cm[ci]["comment"] or cm[ci]["long_name"] or f"Series {idx + 1}"
            col_tok = _guess_palette_color(lbl, idx, palette)
            plots.append({
                "type": "line_marker", "data": dkey, "x": 0, "y": int(ci),
                "color": col_tok, "marker": markers[idx % len(markers)],
                "ms": 5.0, "lw": 1.55, "label": lbl, "dropna": True,
            })

        ranked = _sparse_corner_ranking(series_xy, xlim, ylim, len(y_cols))
        pid = chr(ord("A") + pi)
        corner_rankings[pid] = ranked

        # Auto-extract condition metadata from sheet name if absent from legend labels
        legend_cfg: dict[str, Any] = {"loc": ranked[0], "ncol": 1}
        sh_name = str(src.get("sheet", ""))
        lbls_plain = " ".join(_plain_token(cm[ci]["comment"] or cm[ci]["long_name"]) for ci in y_cols)
        cond_tokens = []
        m_cu = re.search(r"(Catalyst-[A-Z0-9]+|[A-Z][a-z]?\d+(?:\.\d+)?-[A-Z]{2,5})", sh_name, re.IGNORECASE)
        if m_cu and m_cu.group(1).lower() not in lbls_plain.lower():
            cond_tokens.append(_safe_chem_mathtext(m_cu.group(1)))
        m_ghsv = re.search(r"GHSV\s*=?\s*([\d,]+k?)", sh_name + " " + caption, re.IGNORECASE)
        if m_ghsv and "ghsv" not in lbls_plain.lower():
            cond_tokens.append(f"GHSV={m_ghsv.group(1)} h$^{{-1}}$")
        if cond_tokens:
            legend_cfg["note"] = ", ".join(cond_tokens)

        panels.append({
            "id": pid,
            "cell": [pi // cols, pi % cols],
            "letter": {"text": pid, "x": -0.175, "y": 0.94} if n > 1 else None,
            "x": {"label": xlabel, "lim": xlim, "ticks": xticks},
            "y": {"label": ylabel, "lim": ylim, "ticks": yticks},
            "plots": plots,
            "legend": legend_cfg,
        })
        if panels[-1]["letter"] is None:
            panels[-1].pop("letter")

    spec = {
        "chart": "01_line-marker-eval",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | caption={caption}",
        "figure": {"width_in": w_in, "height_in": h_in, "dpi": 300},
        "layout": {
            "cols": cols, "rows": rows,
            "margins": {"l": 0.11, "r": 0.03, "t": 0.055, "b": 0.11 if rows == 2 else 0.18},
            "gap": [0.13, 0.14],
        },
        "data": data_cfg,
        "panels": panels,
    }
    return spec, {"corner_rankings": corner_rankings}


def _detect_xy_pairs(src: dict) -> list[tuple[int, int, str]]:
    """Detect whether columns are paired (x0,y0, x1,y1, ...) vs shared (x0, y1..yk)."""
    df = src["df"]
    cm = src["col_meta"]
    ncols = df.shape[1]
    if ncols >= 4 and ncols % 2 == 0:
        def _base(nm: str) -> str:
            return re.sub(r"\.\d+$", "", nm.strip().lower())
        x0_base = _base(cm[0]["plain_long"])
        even_bases = [_base(cm[c]["plain_long"]) for c in range(0, ncols, 2)]
        # Also verify even columns look like monotonic axes (e.g. Angle, Angle.1, ...)
        even_mono = all(
            (np.all(np.diff(v) >= -1e-9) or np.all(np.diff(v) <= 1e-9))
            for v in (_num_arr(df, c)[np.isfinite(_num_arr(df, c))] for c in range(0, ncols, 2))
            if v.size >= 3
        )
        if all(nm == x0_base for nm in even_bases) or (even_mono and x0_base in ("angle", "wavelength", "relative pressure", "wavenumber", "binding energy", "x")):
            return [(c, c + 1, cm[c + 1]["comment"] or cm[c + 1]["long_name"] or f"Series {c // 2 + 1}")
                    for c in range(0, ncols, 2)]
    return [(0, c, cm[c]["comment"] or cm[c]["long_name"] or f"Series {c}")
            for c in range(1, ncols) if np.isfinite(_num_arr(df, c)).any()]


def _plan_stacked_spectra(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    src = sources[0]
    df = src["df"]
    cm = src["col_meta"]
    pairs = _detect_xy_pairs(src)
    series = []
    for xi, yi, lbl in pairs:
        xv = _num_arr(df, xi)
        yv = _num_arr(df, yi)
        ok = np.isfinite(xv) & np.isfinite(yv)
        series.append((xi, yi, lbl, xv[ok], yv[ok]))

    all_x = np.concatenate([s[3] for s in series])
    xmin, xmax = float(all_x.min()), float(all_x.max())
    xspan = max(xmax - xmin, 1.0)
    rev_x = any(k in (cm[0]["plain_long"] + " " + cm[0]["plain_unit"] + " " + caption).lower()
                for k in ("ppm", "cm-1", "cm^-1", "wavenumber", "binding energy"))
    # Expand right-side headroom (+10% of span) so inline right-side labels clear tail peaks cleanly
    xlim = [round(xmax, 3), round(xmin - 0.10 * xspan, 3)] if rev_x else [round(xmin, 3), round(xmax + 0.11 * xspan, 3)]
    xticks = _nice_ticks(xmin, xmax, 5)

    # Check if curves already carry vertical baseline offsets
    medians = [float(np.median(s[4])) for s in series]
    iqrs = [max(float(np.percentile(s[4], 75) - np.percentile(s[4], 25)), 1e-9) for s in series]
    med_iqr = float(np.median(iqrs))
    pre_stacked = len(medians) >= 2 and all((medians[i + 1] - medians[i]) > 1.5 * med_iqr for i in range(len(medians) - 1))

    if pre_stacked:
        offsets = [0.0] * len(series)
    else:
        spans = [float(np.percentile(s[4], 98) - np.percentile(s[4], 2)) for s in series]
        step = max(float(np.median(spans)) * 0.85, 2.5 * med_iqr, 1e-6)
        offsets = [round(i * step, 6) for i in range(len(series))]

    y_shifted = [s[4] + off for s, off in zip(series, offsets)]
    ymin = min(float(y.min()) for y in y_shifted)
    ymax = max(float(y.max()) for y in y_shifted)
    yspan = max(ymax - ymin, 1e-6)
    ylim = [round(ymin - 0.05 * yspan, 6), round(ymax + 0.14 * yspan, 6)]

    x_plain = cm[0]["plain_long"].lower()
    if "theta" in x_plain or "angle" in x_plain or "xrd" in caption.lower():
        xlabel = "2$\\theta$ (°)"
    elif "ppm" in (cm[0]["plain_unit"] + caption).lower():
        xlabel = "Chemical shift (ppm)"
    else:
        xlabel = cm[0]["long_name"] or "Axis"

    plots = []
    prev_label_y = -1e18
    for idx, ((xi, yi, lbl, xv, yv), off) in enumerate(zip(series, offsets)):
        # Clean series label (e.g. "SampleA_Theta_2-Theta" -> "SampleA")
        clean_lbl = re.sub(r"_?Theta_2-Theta", "", lbl, flags=re.IGNORECASE).strip("_ ")
        clean_lbl = clean_origin_markup(clean_lbl)
        col_tok = _guess_palette_color(clean_lbl, idx, palette)
        plots.append({
            "type": "line", "data": "spec", "x": int(xi), "y": int(yi),
            "offset": off, "color": col_tok, "lw": 1.55, "dropna": True,
        })
        # Inline right-side sample label placed in expanded right-tail headroom clear of peaks
        tail_mask = xv >= (xmax - 0.12 * xspan) if not rev_x else xv <= (xmin + 0.12 * xspan)
        tail_base = float(np.median(yv[tail_mask])) if np.any(tail_mask) else float(yv[-1])
        lx = (xmax + 0.095 * xspan) if not rev_x else (xmin - 0.085 * xspan)
        ly = max(tail_base + off + 0.025 * yspan, prev_label_y + 0.075 * yspan)
        prev_label_y = ly
        plots.append({
            "type": "text", "xy": [round(lx, 3), round(ly, 6)],
            "text": clean_lbl, "size": 9.5, "ha": "right", "va": "bottom", "color": col_tok, "zorder": 6,
        })

    spec = {
        "chart": "02_stacked-spectra",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | pre_stacked={pre_stacked} | caption={caption}",
        "figure": {"width_in": 4.2, "height_in": 3.45, "dpi": 300},
        "style": {"scale": 1.0},
        "layout": {"cols": 1, "rows": 1, "margins": {"l": 0.12, "r": 0.04, "t": 0.05, "b": 0.16}},
        "data": {"spec": _data_entry("spec", src)},
        "panels": [{
            "id": "A", "cell": [0, 0],
            "x": {"label": xlabel, "lim": xlim, "ticks": xticks},
            "y": {"label": "Intensity (a.u.)", "lim": ylim, "ticks": []},
            "plots": plots,
        }],
    }
    return spec, {"pre_stacked": pre_stacked, "offsets": offsets}


def _plan_isotherm_psd(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    src = sources[0]
    df = src["df"]
    cm = src["col_meta"]
    pairs = _detect_xy_pairs(src)

    # Check if paired ads/des branches (consecutive blocks where first ascends and second descends in P/P0)
    is_isotherm = any("pressure" in c["plain_long"].lower() or "p/p" in c["plain_unit"].lower() for c in cm)
    sample_groups = []
    if is_isotherm and len(pairs) >= 2:
        i = 0
        while i < len(pairs):
            xi, yi, lbl = pairs[i]
            xv = _num_arr(df, xi)
            ok = np.isfinite(xv)
            xok = xv[ok]
            has_next_desc = False
            if i + 1 < len(pairs):
                x2 = _num_arr(df, pairs[i + 1][0])
                x2ok = x2[np.isfinite(x2)]
                if xok.size >= 3 and x2ok.size >= 3 and xok[0] < xok[-1] and x2ok[0] > x2ok[-1]:
                    has_next_desc = True
            if has_next_desc:
                sample_groups.append((lbl, [(xi, yi, True), (pairs[i + 1][0], pairs[i + 1][1], False)]))
                i += 2
            else:
                sample_groups.append((lbl, [(xi, yi, True)]))
                i += 1
    else:
        for xi, yi, lbl in pairs:
            sample_groups.append((lbl, [(xi, yi, True)]))

    markers = ["s", "o", "^", "D", "v"]
    plots = []
    series_xy = []
    for idx, (lbl, branches) in enumerate(sample_groups):
        col_tok = _guess_palette_color(lbl, idx, palette)
        mk = markers[idx % len(markers)]
        for bi, (xi, yi, is_filled) in enumerate(branches):
            xv = _num_arr(df, xi)
            yv = _num_arr(df, yi)
            series_xy.append((xv, yv))
            plots.append({
                "type": "line_marker", "data": "bet", "x": int(xi), "y": int(yi),
                "color": col_tok, "marker": mk, "ms": 4.2, "lw": 1.35,
                "mfc": col_tok if is_filled else "white", "mec": col_tok,
                "label": lbl if bi == 0 else None, "dropna": True,
            })

    all_x = np.concatenate([x[np.isfinite(x)] for x, _ in series_xy])
    all_y = np.concatenate([y[np.isfinite(y)] for _, y in series_xy])
    xlim = [0.0, 1.0] if is_isotherm else [round(float(all_x.min()), 3), round(float(all_x.max()), 3)]
    xticks = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0] if is_isotherm else _nice_ticks(xlim[0], xlim[1], 6)
    yhi = _nice_ceil(float(all_y.max()), 0.05)
    ylim = [round(-0.045 * yhi, 2), yhi]
    yticks = _nice_ticks(0.0, yhi, 4)
    ranked = _sparse_corner_ranking(series_xy, xlim, ylim, len(sample_groups))

    xlabel = "Relative pressure ($P/P_0$)" if is_isotherm else (cm[0]["long_name"] or "Pore diameter (nm)")
    ylabel = "Quantity adsorbed (cm$^3$/g)" if is_isotherm else (cm[1]["long_name"] or "dV/dlog(W) (cm$^3$/g)")
    spec = {
        "chart": "03_isotherm-psd",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | isotherm={is_isotherm} | caption={caption}",
        "figure": {"width_in": 4.2, "height_in": 3.58, "dpi": 300},
        "style": {"scale": 1.0, "line": {"data": 1.35}, "tick": {"pad": 5.5}},
        "layout": {"cols": 1, "rows": 1, "margins": {"l": 0.18, "r": 0.04, "t": 0.05, "b": 0.17}},
        "data": {"bet": _data_entry("bet", src)},
        "panels": [{
            "id": "A", "cell": [0, 0],
            "x": {"label": xlabel, "lim": xlim, "ticks": xticks},
            "y": {"label": ylabel, "lim": ylim, "ticks": yticks},
            "plots": plots,
            "legend": {"loc": ranked[0], "ncol": 1},
        }],
    }
    return spec, {"corner_rankings": {"A": ranked}, "is_isotherm": is_isotherm}


def _plan_deconv_peak_fit(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    """Plan seamless stacked deconvolution peak-fit panel from 1..N sample files."""
    data_cfg = {}
    subpanels = []
    all_x_active = []
    top_peaks_info = []

    for si, src in enumerate(sources):
        dkey = f"s{si}"
        data_cfg[dkey] = _data_entry(dkey, src)
        df = src["df"]
        cm = src["col_meta"]
        # Infer sample label from filename
        stem = src["path"].stem
        sample_lbl = stem.split("_")[-1] if "_" in stem else stem
        sample_lbl = clean_origin_markup(sample_lbl)
        col_tok = _guess_palette_color(sample_lbl, si, palette)

        # PeakFit format: 0=Xobs, 1=Yobs, 2=Xgen, 3=Ygen, 4..N=Peaks
        x_gen = _num_arr(df, 2 if df.shape[1] >= 6 else 0)
        y_fit = _num_arr(df, 3 if df.shape[1] >= 6 else 2)
        y_obs = _num_arr(df, 1)
        x_obs = _num_arr(df, 0)
        peak_cols = list(range(4, df.shape[1])) if df.shape[1] >= 6 else list(range(3, df.shape[1]))

        # Active x window where fit signal > 2% of robust peak height (ignoring boundary spike)
        ok_fit = np.isfinite(x_gen) & np.isfinite(y_fit)
        # Focus inside central 90% if edge artifact exists
        xf, yf = x_gen[ok_fit], y_fit[ok_fit]
        # Peak columns sorted left-to-right by nanargmax inside valid fit range
        sorted_peaks = []
        for pc in peak_cols:
            yp = _num_arr(df, pc)
            okp = np.isfinite(x_gen) & np.isfinite(yp)
            if not np.any(okp):
                continue
            xp_ok, yp_ok = x_gen[okp], yp[okp]
            # Ignore extreme last 3% if monotonic edge drift
            inner = np.arange(len(xp_ok)) < int(0.95 * len(xp_ok))
            idx_max = int(np.nanargmax(yp_ok[inner])) if np.any(inner) else int(np.nanargmax(yp_ok))
            x_ctr = float(xp_ok[idx_max])
            sorted_peaks.append((x_ctr, pc, float(np.nanmax(yp_ok[inner]))))
        sorted_peaks.sort(key=lambda t: t[0])

        if sorted_peaks:
            all_x_active.extend([min(t[0] for t in sorted_peaks) - 90.0, max(t[0] for t in sorted_peaks) + 90.0])

        # Robust subpanel y-limit from peak envelope (extra headroom on top subpanel for S1..Sn labels)
        ymax_peaks = float(np.nanmax(yf[np.arange(len(yf)) < int(0.92 * len(yf))])) if yf.size > 20 else float(np.nanmax(yf))
        pad_mult = 1.32 if si == len(sources) - 1 else 1.18
        y_top = round(ymax_peaks * pad_mult, 4)

        plots = []
        x_col_idx = 2 if df.shape[1] >= 6 else 0
        fit_col_idx = 3 if df.shape[1] >= 6 else 2
        for fi, (x_ctr, pc, _) in enumerate(sorted_peaks):
            plots.append({
                "type": "fill", "data": dkey, "x": x_col_idx, "y": int(pc),
                "color": f"fill:{fi}", "gradient": True, "alpha": 0.90,
                "edge": True, "edgecolor": "black", "lw": 0.65, "dropna": True,
            })
        plots.append({"type": "line", "data": dkey, "x": x_col_idx, "y": fit_col_idx, "color": col_tok, "lw": 1.25, "dropna": True, "zorder": 4})
        plots.append({"type": "line", "data": dkey, "x": 0, "y": 1, "color": "#000000", "lw": 0.75, "ls": "--", "dropna": True, "zorder": 3})

        subpanels.append({
            "id": sample_lbl,
            "y": {"lim": [0.0, y_top]},
            "sample_label": {"text": sample_lbl, "loc": "upper right", "color": "#111111", "size": 9.8},
            "plots": plots,
        })
        if si == len(sources) - 1:
            top_peaks_info = (sorted_peaks, y_top)

    xmin = max(float(np.floor(min(all_x_active) / 50.0) * 50.0), 50.0) if all_x_active else 100.0
    xmax = float(np.ceil(max(all_x_active) / 50.0) * 50.0) if all_x_active else 700.0
    # Add top-subpanel peak labels on last subpanel (which sits at top under bottom_to_top)
    if top_peaks_info and subpanels:
        sorted_peaks, y_top = top_peaks_info
        for fi, (x_ctr, _, p_amp) in enumerate(sorted_peaks):
            if xmin <= x_ctr <= xmax:
                ly_txt = min(p_amp + 0.16 * y_top, 0.84 * y_top)
                subpanels[-1]["plots"].append({
                    "type": "text", "xy": [round(x_ctr, 1), round(ly_txt, 4)],
                    "leader": [round(x_ctr, 1), round(p_amp + 0.03 * y_top, 4)],
                    "text": f"S{fi + 1}", "size": 8.8, "ha": "center", "va": "bottom", "zorder": 7,
                })

    xlabel = "Temperature (°C)" if "tpd" in caption.lower() or "tpr" in caption.lower() or xmax > 200 else "Axis"
    spec = {
        "chart": "04_deconv-peak-fit",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | caption={caption}",
        "figure": {"width_in": 4.0, "height_in": 3.4, "dpi": 300},
        "style": {"scale": 1.0},
        "layout": {"cols": 1, "rows": 1, "hspace": 0.0, "margins": {"l": 0.14, "r": 0.04, "t": 0.06, "b": 0.17}},
        "data": data_cfg,
        "panels": [{
            "id": "A", "cell": [0, 0],
            "stack_order": "bottom_to_top",
            "x": {"label": xlabel, "lim": [xmin, xmax], "ticks": _nice_ticks(xmin, xmax, 7)},
            "y": {"label": "TCD signal (a.u.)", "ticks": []},
            "subpanels": subpanels,
        }],
    }
    return spec, {"x_lim": [xmin, xmax], "n_subpanels": len(subpanels)}


def _plan_stacked_bar_comp(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    src = sources[0]
    df = src["df"]
    cm = src["col_meta"]
    # Identify categorical sample column vs numeric component columns
    cat_col = 0
    num_cols = []
    for c in range(df.shape[1]):
        vals = pd.to_numeric(df.iloc[:, c], errors="coerce")
        if vals.notna().sum() >= max(2, len(df) // 2):
            num_cols.append(c)
        else:
            cat_col = c

    # Extract sample names & clean Origin escapes
    ticklabels = [clean_origin_markup(v) for v in df.iloc[:, cat_col].tolist()]
    comp_labels = [cm[c]["comment"] or cm[c]["long_name"] or f"C{i+1}" for i, c in enumerate(num_cols)]
    max_lbl_len = max((len(_plain_token(t)) for t in ticklabels), default=4)
    rot = 20 if max_lbl_len >= 6 else 0

    row_sums = df.iloc[:, num_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1)
    max_sum = float(row_sums.max()) if len(row_sums) else 100.0
    is_pct = 90.0 <= max_sum <= 105.0
    yhi = 100.0 if is_pct else _nice_ceil(max_sum, 0.10)
    yticks = [0, 20, 40, 60, 80, 100] if is_pct else _nice_ticks(0, yhi, 6)

    spec = {
        "chart": "05_stacked-bar-comp",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | caption={caption}",
        "figure": {"width_in": 4.0, "height_in": 3.4, "dpi": 300},
        "style": {"scale": 1.0},
        "layout": {"cols": 1, "rows": 1, "margins": {"l": 0.18, "r": 0.04, "t": 0.13, "b": 0.22 if rot else 0.14}},
        "data": {"comp": _data_entry("comp", src)},
        "panels": [{
            "id": "B", "cell": [0, 0],
            "tick_rotation": rot,
            "x": {"label": "", "lim": [-0.62, len(ticklabels) - 0.38]},
            "y": {"label": "Relative percentage (%)" if is_pct else "Value", "lim": [0, yhi], "ticks": yticks},
            "plots": [{
                "type": "bar_stacked",
                "data": "comp", "x": None, "y": [int(c) for c in num_cols],
                "colors": [f"fill:{i}" for i in range(len(num_cols))],
                "labels": comp_labels,
                "gradient": True, "values": True, "value_min": 4.0,
                "width": 0.56, "ticklabels": ticklabels,
            }],
            "legend": {"loc": "upper center", "bbox": [0.5, 1.14], "ncol": min(4, len(num_cols))},
        }],
    }
    return spec, {"comp_labels": comp_labels, "tick_rotation": rot}


def _plan_single_multi_spectrum(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    src = sources[0]
    df = src["df"]
    cm = src["col_meta"]
    pairs = _detect_xy_pairs(src)
    series_xy = []
    for xi, yi, lbl in pairs:
        xv = _num_arr(df, xi)
        yv = _num_arr(df, yi)
        ok = np.isfinite(xv) & np.isfinite(yv)
        series_xy.append((xi, yi, lbl, xv[ok], yv[ok]))

    all_x = np.concatenate([s[3] for s in series_xy])
    all_y_raw = np.concatenate([s[4] for s in series_xy])
    xmin, xmax = float(all_x.min()), float(all_x.max())
    ymin_raw, ymax_raw = float(all_y_raw.min()), float(all_y_raw.max())
    raw_span = max(ymax_raw - ymin_raw, 1e-9)

    # Overlap-aware auto-staggering: interpolate onto common grid & measure pairwise proximity
    grid_x = np.linspace(xmin, xmax, 600)
    interp_ys = [np.interp(grid_x, np.sort(x), y[np.argsort(x)]) for _, _, _, x, y in series_xy]
    order_idx = sorted(range(len(series_xy)), key=lambda i: float(np.median(interp_ys[i])))
    need_stagger = False
    for k in range(len(order_idx) - 1):
        ya, yb = interp_ys[order_idx[k]], interp_ys[order_idx[k + 1]]
        overlap_frac = float(np.mean(np.abs(yb - ya) < 0.08 * raw_span))
        if overlap_frac > 0.35:
            need_stagger = True
            break

    stagger_offsets = [0.0] * len(series_xy)
    ops_list = []
    if need_stagger:
        step = round(0.18 * raw_span, 6)
        for rank_i, orig_i in enumerate(order_idx):
            off = round(rank_i * step, 6)
            stagger_offsets[orig_i] = off
            if off != 0.0:
                ops_list.append({"op": "scale_offset", "data": "spec", "column": int(series_xy[orig_i][1]), "scale": 1.0, "offset": off})

    plots = []
    shifted_xy = []
    for idx, ((xi, yi, lbl, xv, yv), off) in enumerate(zip(series_xy, stagger_offsets)):
        shifted_xy.append((xv, yv + off))
        col_tok = _guess_palette_color(lbl, idx, palette)
        plots.append({
            "type": "line", "data": "spec", "x": int(xi), "y": int(yi),
            "color": col_tok, "lw": 1.8, "label": lbl, "dropna": True,
        })

    all_y = np.concatenate([y for _, y in shifted_xy])
    ymin, ymax = float(all_y.min()), float(all_y.max())
    yspan = max(ymax - ymin, 1e-9)
    ylim = [round(ymin - 0.05 * yspan, 6), round(ymax + 0.20 * yspan, 6)]
    xlim = [round(xmin, 3), round(xmax, 3)]
    xticks = _nice_ticks(xmin, xmax, 7)

    # Multi-scale peak + SavGol 2nd-derivative shoulder detector on top spectrum
    top_y_grid = np.max(np.vstack([interp_ys[i] + stagger_offsets[i] for i in range(len(series_xy))]), axis=0)
    bot_y_grid = np.min(np.vstack([interp_ys[i] + stagger_offsets[i] for i in range(len(series_xy))]), axis=0)
    top_s = savgol_filter(top_y_grid, 21, 3)
    top_span = max(float(np.ptp(top_s)), 1e-9)

    peaks_prom = _auto_peaks(grid_x, top_s, xmin, xmax, max_peaks=3, include_negative=False, min_sep_frac=0.07)
    # Shoulder detector via smoothed -d2y/dx2 where signal is significantly above minimum
    d2 = -np.gradient(np.gradient(top_s))
    d2_s = savgol_filter(d2, 17, 3)
    d2_max = max(float(np.max(d2_s)), 1e-12)
    sh_idx, sh_props = find_peaks(d2_s, prominence=0.08 * d2_max, distance=max(12, int(0.06 * grid_x.size)))
    shoulder_cands = []
    for idx_pk, prom in zip(sh_idx, sh_props["prominences"]):
        px = float(grid_x[idx_pk])
        if top_s[idx_pk] > float(top_s.min()) + 0.12 * top_span and (px - xmin) >= 0.01 * (xmax - xmin) and (xmax - px) >= 0.04 * (xmax - xmin):
            shoulder_cands.append((float(prom), px))
    shoulder_cands.sort(key=lambda t: -t[0])

    merged_peaks = list(peaks_prom)
    for _, px in shoulder_cands:
        if all(abs(px - ox) >= 0.07 * (xmax - xmin) for ox in merged_peaks):
            merged_peaks.append(px)
        if len(merged_peaks) >= 4:
            break
    merged_peaks = sorted(merged_peaks)

    for px in merged_peaks:
        y_top_at = float(np.interp(px, grid_x, top_y_grid))
        y_bot_at = float(np.interp(px, grid_x, bot_y_grid))
        ym_lo = max(0.03, (y_bot_at - 0.06 * yspan - ylim[0]) / (ylim[1] - ylim[0]))
        ym_hi = min(0.92, (y_top_at + 0.06 * yspan - ylim[0]) / (ylim[1] - ylim[0]))
        plots.append({"type": "vline", "x": round(px, 1), "ymin": round(ym_lo, 3), "ymax": round(ym_hi, 3), "color": "#000000", "ls": "--", "lw": 0.9, "zorder": 2.5})
        ly = min(y_top_at + 0.075 * yspan, ylim[1] - 0.06 * yspan)
        plots.append({
            "type": "text", "xy": [round(px, 1), round(ly, 6)],
            "text": f"{int(round(px))}", "rotation": 0, "size": 9.0, "ha": "center", "va": "bottom", "zorder": 6,
        })

    ranked = _sparse_corner_ranking(shifted_xy, xlim, ylim, len(pairs))
    xunit = cm[0]["unit"] or "nm"
    xlabel = f"{cm[0]['long_name'] or 'Wavelength'} ({xunit})"
    ylabel = f"{cm[1]['long_name'] or 'Absorbance'} ({cm[1]['unit'] or 'a.u.'})"

    spec = {
        "chart": "06_single-multi-spectrum",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | auto_stagger={need_stagger} | auto_peaks={[round(p,1) for p in merged_peaks]} | caption={caption}",
        "figure": {"width_in": 4.6, "height_in": 3.85, "dpi": 300},
        "style": {"scale": 1.0, "line": {"data": 1.8}},
        "layout": {"cols": 1, "rows": 1, "margins": {"l": 0.12, "r": 0.04, "t": 0.05, "b": 0.15}},
        "data": {"spec": _data_entry("spec", src)},
        "ops": ops_list,
        "panels": [{
            "id": "A", "cell": [0, 0],
            "x": {"label": xlabel, "lim": xlim, "ticks": xticks},
            "y": {"label": ylabel, "lim": ylim, "ticks": []},
            "plots": plots,
            "legend": {"loc": ranked[0], "ncol": 1},
        }],
    }
    return spec, {"corner_rankings": {"A": ranked}, "auto_peaks": merged_peaks, "auto_stagger": need_stagger}


def _clean_drifts_time_label(raw_name: str, prev_prefix: str = "") -> str:
    s = str(raw_name).strip()
    if "N2" in s and "purge" not in s.lower():
        if re.search(r"N2-60min$", s, re.IGNORECASE):
            prefix = re.sub(r"-?N2-60min$", "", s, flags=re.IGNORECASE)
            if "NH3" in prefix and "NO" not in prefix:
                return "N$_2$ purge 60 min"
            return clean_origin_markup(prefix) + " + N$_2$ purge"
    m = re.search(r"(\d+\s*min)$", s, re.IGNORECASE)
    if m:
        tpart = re.sub(r"(\d+)\s*min", r"\1 min", m.group(1))
        if s.endswith("-1min") or s.endswith("1 min"):
            return clean_origin_markup(s.replace("-1min", "-1 min"))
        return tpart
    return clean_origin_markup(s)


def _plan_drifts_broken_stack(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    n_panels = len(sources)
    cols = n_panels
    w_in = 7.09 if n_panels >= 2 else 4.2
    h_in = 2.18 if n_panels == 3 else (3.05 if n_panels == 2 else 3.45)
    scale_factor = 0.70 if n_panels == 3 else 0.90

    data_cfg = {}
    panels = []
    meta_panels = {}

    for pi, src in enumerate(sources):
        dkey = f"s{pi}"
        data_cfg[dkey] = _data_entry(dkey, src)
        df = src["df"]
        cm = src["col_meta"]
        xv = _num_arr(df, 0)
        y_cols = [c for c in range(1, df.shape[1]) if np.isfinite(_num_arr(df, c)).any()]

        # Extract valid curves and perform baseline_min for dynamic range analysis
        curves = []
        for ci in y_cols:
            yv = _num_arr(df, ci)
            ok = np.isfinite(xv) & np.isfinite(yv)
            xc, yc = xv[ok], yv[ok]
            order = np.argsort(xc)
            curves.append((ci, xc[order], yc[order]))

        # Bimodal broken-axis detection: compare energy in [1950..3250] vs [3300..3800] & [800..1900]
        x_lo_all = min(float(c[1].min()) for c in curves)
        x_hi_all = max(float(c[1].max()) for c in curves)
        use_broken = False
        if x_lo_all <= 1000 and x_hi_all >= 3400:
            e_hi, e_mid, e_lo = [], [], []
            for _, xc, yc in curves:
                m_hi = (xc >= 3350) & (xc <= 3800)
                m_mid = (xc >= 1950) & (xc <= 3250)
                m_lo = (xc >= 800) & (xc <= 1900)
                if np.any(m_hi): e_hi.append(float(np.ptp(yc[m_hi])))
                if np.any(m_mid): e_mid.append(float(np.ptp(yc[m_mid])))
                if np.any(m_lo): e_lo.append(float(np.ptp(yc[m_lo])))
            if e_hi and e_lo and e_mid:
                # Compare top quartile energy in middle silent band vs active bands
                mid_e = float(np.percentile(e_mid, 75))
                act_e = max(float(np.percentile(e_hi, 75)), float(np.percentile(e_lo, 75)))
                if mid_e < 0.35 * act_e:
                    use_broken = True

        if use_broken:
            segments = [[3800, 3400, 4.0], [1900, 800, 11.0]]
            xticks = [3800, 3600, 1800, 1600, 1400, 1200, 1000, 800]
            win_mask_fn = lambda xarr: ((xarr >= 3400) & (xarr <= 3800)) | ((xarr >= 800) & (xarr <= 1900))
        else:
            x_hi_r = float(min(1800.0, np.ceil(x_hi_all / 100.0) * 100.0)) if x_hi_all < 2400 else 3800.0
            x_lo_r = float(max(800.0, np.floor(x_lo_all / 100.0) * 100.0))
            if x_hi_r - x_lo_r > 800 and x_hi_r <= 2200:
                x_hi_r, x_lo_r = 1800.0, 1200.0
            segments = None
            xlim = [x_hi_r, x_lo_r]
            xticks = _nice_ticks(x_hi_r, x_lo_r, 7)
            win_mask_fn = lambda xarr: (xarr >= x_lo_r) & (xarr <= x_hi_r)

        # Robust asymmetric excursion scaling so negative OH dips do not crash across lower curves
        win_curves = []
        win_ptps = []
        neg_excs = []
        pos_excs = []
        for ci, xc, yc in curves:
            m = win_mask_fn(xc)
            xw, yw = xc[m], yc[m]
            x_right_anchor = 800.0 if use_broken else xlim[1]
            tail_m = np.abs(xw - x_right_anchor) <= 35.0
            tail_val = float(np.median(yw[tail_m])) if np.any(tail_m) else (float(yw[0]) if yw.size else 0.0)
            y_rel = yw - tail_val
            neg_exc = max(float(-np.min(y_rel)), 0.0) if y_rel.size else 0.0
            pos_exc = max(float(np.max(y_rel)), 0.0) if y_rel.size else 0.0
            win_curves.append((ci, xc, yc, xw, yw, tail_val, y_rel))
            win_ptps.append(float(np.ptp(yw)) if yw.size else 0.0)
            neg_excs.append(neg_exc)
            pos_excs.append(pos_exc)

        global_ptp = max(float(np.percentile(win_ptps, 90)), 1e-6)
        max_neg = max(neg_excs) if neg_excs else 0.0
        n_c = len(win_curves)
        step = round(0.70 / max(1, n_c - 1), 5)
        # Bound negative dip depth to <= 2.3x step while preserving crisp positive band height
        scale_by_ptp = 0.38 / global_ptp
        scale_by_neg = (2.3 * step / max_neg) if max_neg > 1e-9 else scale_by_ptp
        g_scale = round(min(scale_by_ptp, scale_by_neg), 4)

        ramp = theme_mod.load_palette(palette).get("ramps", {}).get("drifts_12")
        plots = []
        y_tops_all = []
        y_bots_all = []
        for idx, (ci, xc, yc, xw, yw, tail_val, y_rel) in enumerate(win_curves):
            off = round(0.05 + idx * step - g_scale * tail_val, 5)
            col_hex = ramp[idx % len(ramp)] if (ramp and n_c <= 12) else _guess_palette_color(cm[ci]["comment"], idx, palette)
            plots.append({
                "type": "line", "data": dkey, "x": 0, "y": int(ci),
                "scale": g_scale, "offset": off, "color": col_hex,
                "lw": 0.80, "dropna": True,
            })
            yw_s = g_scale * yw + off
            y_tops_all.append(float(yw_s.max()))
            y_bots_all.append(float(yw_s.min()))

            # In-frame right-side time label
            tlabel = _clean_drifts_time_label(cm[ci]["plain_comment"])
            lx = 940.0 if use_broken else (xlim[1] + 0.05 * (xlim[0] - xlim[1]))
            plots.append({
                "type": "text", "xy": [lx, round(0.05 + idx * step + 0.010, 4)],
                "text": tlabel, "size": 6.8, "ha": "right", "va": "bottom", "zorder": 6,
                **({"seg": 1} if use_broken else {}),
            })

        ymin_p = min(0.0, min(y_bots_all) - 0.03)
        ymax_p = max(1.0, max(y_tops_all) + 0.16)

        # Multi-scale derivative peak detection on top active curves (catching weaker bands cleanly)
        top_idx = max(0, len(win_curves) - 2)
        _, _, _, x_top_w, y_top_w, _, _ = win_curves[top_idx]
        if use_broken:
            pk0 = _auto_peaks(x_top_w, y_top_w, 3420, 3780, max_peaks=3, include_negative=True, min_sep_frac=0.14)
            # Combine fine-scale prominence peaks + 2nd-derivative bands in fingerprint region
            pk1_prom = _auto_peaks(x_top_w, y_top_w, 820, 1850, max_peaks=6, include_negative=True, min_sep_frac=0.055)
            m1 = (x_top_w >= 820) & (x_top_w <= 1850)
            if np.sum(m1) > 25:
                xs1, ys1 = x_top_w[m1], y_top_w[m1]
                ys1_s = savgol_filter(ys1, 9, 3)
                d2_1 = np.abs(np.gradient(np.gradient(ys1_s)))
                pk1_d2 = _auto_peaks(xs1, d2_1, 820, 1850, max_peaks=6, include_negative=False, min_sep_frac=0.06)
                pk1 = list(pk1_prom)
                for px in pk1_d2:
                    if all(abs(px - ox) >= 50.0 for ox in pk1):
                        pk1.append(px)
                pk1 = sorted(pk1)[:7]
            else:
                pk1 = pk1_prom
            for si_seg, pks in ((0, pk0), (1, pk1)):
                for pi_k, px in enumerate(pks):
                    ly_frac = 0.94 - (pi_k % 3) * 0.048
                    plots.append({"type": "vline", "x": round(px, 1), "ymin": 0.05, "ymax": round(ly_frac - 0.015, 3), "color": "#000000", "ls": "--", "lw": 0.65, "seg": si_seg, "zorder": 1.5})
                    plots.append({
                        "type": "text", "xy": [round(px, 1), round(ymin_p + ly_frac * (ymax_p - ymin_p), 4)],
                        "text": str(int(round(px))), "size": 6.4, "ha": "center", "va": "bottom", "seg": si_seg, "zorder": 7,
                    })
        else:
            pks = _auto_peaks(x_top_w, y_top_w, xlim[1] + 20, xlim[0] - 20, max_peaks=3, include_negative=False, min_sep_frac=0.12)
            for pi_k, px in enumerate(pks):
                plots.append({"type": "vline", "x": round(px, 1), "ymin": 0.05, "ymax": 0.89, "color": "#000000", "ls": "--", "lw": 0.65, "zorder": 1.5})
                ly_frac = 0.93 - (pi_k % 2) * 0.055
                plots.append({
                    "type": "text", "xy": [round(px, 1), round(ymin_p + ly_frac * (ymax_p - ymin_p), 4)],
                    "text": str(int(round(px))), "size": 6.8, "ha": "center", "va": "bottom", "zorder": 7,
                })

        pid = chr(ord("A") + pi)
        pdict: dict[str, Any] = {
            "id": pid, "cell": [0, pi],
            "x": {"label": "Wavenumber (cm$^{-1}$)", "ticks": xticks, "minor": 100 if use_broken else 50},
            "y": {"label": "Kubelka-Munk (a.u.)", "lim": [round(ymin_p, 4), round(ymax_p, 4)], "ticks": []},
            "plots": plots,
        }
        if n_panels > 1:
            pdict["letter"] = {"text": pid, "x": -0.08, "y": 0.90}
        if use_broken:
            pdict["segments"] = segments
            pdict["break_gap"] = 0.008
        else:
            pdict["x"]["lim"] = xlim
        panels.append(pdict)
        meta_panels[pid] = {"use_broken": use_broken, "global_scale": g_scale, "step": step, "n_curves": n_c}

    spec = {
        "chart": "07_drifts-broken-stack",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | caption={caption}",
        "figure": {"width_in": w_in, "height_in": h_in, "dpi": 300},
        "style": {"scale": scale_factor},
        "layout": {
            "cols": cols, "rows": 1,
            "margins": {"l": 0.09 if n_panels == 1 else 0.045, "r": 0.025, "t": 0.04, "b": 0.16},
            "gap": [0.06, 0.08],
        },
        "data": data_cfg,
        "panels": panels,
    }
    return spec, {"panels": meta_panels}


def _plan_xps_reverse_deconv(sources: list[dict], theme: str, palette: str, caption: str) -> tuple[dict, dict]:
    """Plan stacked reverse-binding-energy XPS deconvolution figure."""
    src = sources[0]
    df = src["df"]
    cm = src["col_meta"]

    # Partition columns by blank separator columns (all-NaN) or repeated Binding Energy headers
    blocks = []
    cur = []
    for c in range(df.shape[1]):
        vals = _num_arr(df, c)
        if not np.isfinite(vals).any():
            if cur:
                blocks.append(cur)
                cur = []
        else:
            if cur and "binding" in cm[c]["plain_long"].lower():
                blocks.append(cur)
                cur = [c]
            else:
                cur.append(c)
    if cur:
        blocks.append(cur)

    all_x = []
    subpanels = []
    # First pass: find intersection of active Shirley/deconv windows across all blocks
    block_mins, block_maxs = [], []
    parsed_blocks = []
    for bi, cols in enumerate(blocks):
        x_col = cols[0]
        xv = _num_arr(df, x_col)
        obs_col = cols[1] if len(cols) > 1 else cols[0]
        fit_col = None
        bg_col = None
        comp_cols = []
        for c in cols[2:]:
            nm = (cm[c]["plain_long"] + " " + cm[c]["plain_unit"] + " " + cm[c]["plain_comment"]).lower()
            if "backgnd" in nm or "bg" in nm or "shirley" in nm:
                bg_col = c
            elif "envelope" in nm or "fit" == nm.strip() or "sum" in nm:
                fit_col = c
            else:
                comp_cols.append(c)
        if fit_col is None and len(cols) > 2:
            fit_col = cols[2]

        # Active region = strictly where component peaks > 1% of max component (excluding outside-window zero bg)
        act_mask = np.isfinite(xv)
        if comp_cols:
            comp_sum = np.zeros_like(xv)
            for cc in comp_cols:
                yv_c = np.nan_to_num(_num_arr(df, cc), nan=0.0)
                comp_sum += np.maximum(yv_c, 0.0)
            cmax = float(np.max(comp_sum))
            if cmax > 0:
                act_mask &= (comp_sum > 0.01 * cmax)
        if bg_col is not None:
            bg_v = _num_arr(df, bg_col)
            if np.any(np.isfinite(bg_v) & (bg_v > 0)):
                act_mask &= (np.isfinite(bg_v) & (bg_v > 0))
        if np.any(act_mask):
            block_mins.append(float(np.min(xv[act_mask])))
            block_maxs.append(float(np.max(xv[act_mask])))
        else:
            ok_x = xv[np.isfinite(xv)]
            block_mins.append(float(ok_x.min()))
            block_maxs.append(float(ok_x.max()))
        parsed_blocks.append((bi, cols, x_col, obs_col, fit_col, bg_col, comp_cols, act_mask))

    xmin = float(np.ceil(max(block_mins))) if block_mins else 928.0
    xmax = float(np.floor(min(block_maxs))) if block_maxs else 948.0
    # Stay strictly inside active Shirley background boundaries
    xlim = [round(xmax, 1), round(xmin, 1)]
    xticks = _nice_ticks(xlim[0], xlim[1], 6)

    for bi, cols, x_col, obs_col, fit_col, bg_col, comp_cols, act_mask in parsed_blocks:
        xv = _num_arr(df, x_col)
        in_win = np.isfinite(xv) & (xv >= min(xlim)) & (xv <= max(xlim))
        sample_lbl = cm[obs_col]["comment"] or f"Sample {bi + 1}"
        col_tok = _guess_palette_color(sample_lbl, bi, palette)

        y_obs = _num_arr(df, obs_col)
        y_bg = _num_arr(df, bg_col) if bg_col is not None else np.zeros_like(y_obs)
        ok_y = in_win & np.isfinite(y_obs) & np.isfinite(y_bg) & ((y_bg > 0) if bg_col is not None else True)
        if not np.any(ok_y):
            ok_y = in_win & np.isfinite(y_obs)
        y_lo = float(np.nanmin(np.minimum(y_obs[ok_y], y_bg[ok_y]))) if np.any(ok_y) else 0.0
        y_hi = float(np.nanmax(y_obs[ok_y])) if np.any(ok_y) else 1.0
        yspan = max(y_hi - y_lo, 1.0)
        is_top_block = (bi == 0 and len(parsed_blocks) >= 2) or (bi == len(parsed_blocks) - 1 and len(parsed_blocks) == 1)
        ylim = [round(y_lo - 0.06 * yspan, 2), round(y_hi + (0.34 if is_top_block else 0.22) * yspan, 2)]

        # Consistent pastel fill sequence (blue, green, lilac, salmon) + sorted components
        pastel_fills = ["fill:0", "fill:1", "fill:3", "fill:2", "fill:4"]
        comp_peaks = []
        for pc in comp_cols:
            yp_c = _num_arr(df, pc)
            okp = in_win & np.isfinite(yp_c)
            if np.any(okp):
                xv_p, yv_p = xv[okp], yp_c[okp]
                idx_m = int(np.nanargmax(yv_p))
                comp_peaks.append((float(xv_p[idx_m]), float(yv_p[idx_m]), pc))
        comp_peaks.sort(key=lambda t: t[0])

        plots = []
        for fi, (pk_x, pk_y, pc) in enumerate(comp_peaks):
            plots.append({
                "type": "fill", "data": "xps", "x": int(x_col), "y": int(pc),
                "baseline": str(bg_col) if bg_col is not None else 0.0,
                "color": pastel_fills[fi % len(pastel_fills)], "gradient": False, "alpha": 0.55,
                "edge": False, "dropna": False,
            })
        if bg_col is not None:
            plots.append({"type": "line", "data": "xps", "x": int(x_col), "y": int(bg_col), "color": "#888888", "ls": "-", "lw": 0.9, "dropna": True, "zorder": 3})
        if fit_col is not None:
            plots.append({"type": "line", "data": "xps", "x": int(x_col), "y": int(fit_col), "color": col_tok, "lw": 1.5, "dropna": True, "zorder": 4})
        plots.append({"type": "line", "data": "xps", "x": int(x_col), "y": int(obs_col), "color": "#555555", "lw": 1.0, "dropna": True, "zorder": 3.5})

        subpanels.append({
            "id": _plain_token(sample_lbl),
            "y": {"lim": ylim},
            "sample_label": {"text": sample_lbl, "loc": "upper left", "color": "#111111", "size": 10.2},
            "plots": plots,
            "_comp_peaks": comp_peaks,
            "_yspan": yspan,
        })

    # If blocks are ordered high->low Cu loading (Catalyst-C, Catalyst-B, Catalyst-A), order ascending bottom->top
    if len(subpanels) >= 2:
        nums = [re.findall(r"\d+(?:\.\d+)?", sp["id"]) for sp in subpanels]
        if all(nums) and [float(n[0]) for n in nums] == sorted([float(n[0]) for n in nums], reverse=True):
            subpanels = list(reversed(subpanels))

    # Annotate auto-detected component peak centers cleanly on the top subpanel (last in bottom_to_top)
    if subpanels:
        top_sp = subpanels[-1]
        ys_top = top_sp.pop("_yspan", 1.0)
        for sp_other in subpanels[:-1]:
            sp_other.pop("_comp_peaks", None)
            sp_other.pop("_yspan", None)
        cpeaks = top_sp.pop("_comp_peaks", [])
        top_sp["y"]["lim"][1] = round(top_sp["y"]["lim"][1] + 0.12 * ys_top, 2)
        for pk_x, pk_y, _ in cpeaks:
            if min(xlim) <= pk_x <= max(xlim):
                top_sp["plots"].append({
                    "type": "text", "xy": [round(pk_x, 1), round(pk_y + 0.14 * ys_top, 2)],
                    "leader": [round(pk_x, 1), round(pk_y + 0.02 * ys_top, 2)],
                    "text": f"{pk_x:.1f} eV", "size": 7.8, "ha": "center", "va": "bottom", "zorder": 7,
                })

    spec = {
        "chart": "08_xps-reverse-deconv",
        "theme": theme,
        "palette": palette,
        "_note": f"Blind-Mode generated spec | n_blocks={len(blocks)} | caption={caption}",
        "figure": {"width_in": 4.6, "height_in": 4.0, "dpi": 300},
        "style": {"scale": 1.0},
        "layout": {"cols": 1, "rows": 1, "hspace": 0.0, "margins": {"l": 0.12, "r": 0.04, "t": 0.05, "b": 0.15}},
        "data": {"xps": _data_entry("xps", src)},
        "panels": [{
            "id": "A", "cell": [0, 0],
            "stack_order": "bottom_to_top",
            "x": {"label": "Binding Energy (eV)", "lim": xlim, "ticks": xticks},
            "y": {"label": "Intensity (a.u.)", "ticks": []},
            "subpanels": subpanels,
        }],
    }
    return spec, {"n_blocks": len(blocks), "xlim": xlim}


PLANNERS = {
    "01_line-marker-eval": _plan_line_marker,
    "02_stacked-spectra": _plan_stacked_spectra,
    "03_isotherm-psd": _plan_isotherm_psd,
    "04_deconv-peak-fit": _plan_deconv_peak_fit,
    "05_stacked-bar-comp": _plan_stacked_bar_comp,
    "06_single-multi-spectrum": _plan_single_multi_spectrum,
    "07_drifts-broken-stack": _plan_drifts_broken_stack,
    "08_xps-reverse-deconv": _plan_xps_reverse_deconv,
}


def plan_spec(
    data_paths: list[str | Path],
    chart_id: str,
    theme: str = "origin-times-bold",
    caption: str = "",
    palette: str | None = None,
    max_sheets: int | None = None,
) -> tuple[dict, dict]:
    """Build an initial blind declarative spec from data + chart_id + theme + caption."""
    if chart_id not in PLANNERS:
        raise ValueError(f"Unsupported chart_id={chart_id!r}; available={sorted(PLANNERS)}")
    th = theme_mod.load_theme(theme)
    pal = palette or th.get("palette", "publication-pastel")
    sources = inspect_sources(data_paths, max_sheets=max_sheets)
    spec, meta = PLANNERS[chart_id](sources, theme, pal, caption)
    return spec, meta


# ---------------------------------------------------------------- QA-driven auto-repair
def _repair_spec(spec: dict, qa_rep: dict, plan_meta: dict, step_idx: int) -> tuple[dict, list[str]]:
    """Apply targeted deterministic repairs based on scifig QA findings."""
    s = copy.deepcopy(spec)
    actions: list[str] = []

    if qa_rep.get("out_of_bounds_count", 0) > 0:
        m = s.setdefault("layout", {}).setdefault("margins", {"l": 0.12, "r": 0.04, "t": 0.06, "b": 0.16})
        m["l"] = round(min(0.24, m.get("l", 0.12) + 0.03), 3)
        m["b"] = round(min(0.28, m.get("b", 0.16) + 0.03), 3)
        m["t"] = round(min(0.22, m.get("t", 0.06) + 0.03), 3)
        m["r"] = round(min(0.12, m.get("r", 0.04) + 0.02), 3)
        # Also nudge panel rects inward if explicit rects are used
        for p in s.get("panels", []):
            if "rect" in p:
                L, B, W, H = p["rect"]
                p["rect"] = [round(L + 0.01, 3), round(B + 0.02, 3), round(W - 0.02, 3), round(H - 0.03, 3)]
        actions.append("expanded_layout_margins_for_clipping")

    if qa_rep.get("legend_data_overlap_count", 0) > 0:
        rankings = plan_meta.get("corner_rankings", {})
        for p in s.get("panels", []):
            lg = p.get("legend")
            if not lg:
                continue
            pid = p.get("id", "A")
            cand_locs = rankings.get(pid, ["upper right", "upper left", "lower right", "lower left"])
            if step_idx < len(cand_locs) and lg.get("loc") != cand_locs[step_idx]:
                lg["loc"] = cand_locs[step_idx]
                actions.append(f"relocated_legend_{pid}_to_{cand_locs[step_idx]}")
            else:
                # Expand y-top by 15% or move legend above frame
                ycfg = p.get("y", {})
                if ycfg.get("lim") and len(ycfg["lim"]) == 2:
                    lo, hi = ycfg["lim"]
                    ycfg["lim"] = [lo, round(lo + 1.15 * (hi - lo), 4)]
                    actions.append(f"expanded_ylim_15pct_{pid}")
                else:
                    lg["loc"] = "upper center"
                    lg["bbox"] = [0.5, 1.13]
                    lg["ncol"] = min(3, len(p.get("plots", [])))
                    actions.append(f"moved_legend_outside_top_{pid}")

    if qa_rep.get("text_overlap_count", 0) > 0:
        overlaps = qa_rep.get("text_overlaps", [])
        hit_texts = {t for pair in overlaps for t in pair}
        for p in s.get("panels", []):
            # Nudge colliding peak/inline text annotations slightly vertically
            txt_plots = [pl for pl in p.get("plots", []) if pl.get("type") == "text"]
            nudge_i = 0
            ycfg = p.get("y", {})
            yrng = abs(ycfg["lim"][1] - ycfg["lim"][0]) if ycfg.get("lim") else 1.0
            for pl in txt_plots:
                if pl.get("text") in hit_texts:
                    pl["xy"][1] = round(pl["xy"][1] - (0.045 if nudge_i % 2 == 0 else -0.035) * yrng, 4)
                    nudge_i += 1
            if nudge_i:
                actions.append(f"staggered_{nudge_i}_colliding_texts_panel_{p.get('id')}")

    if not actions and not qa_rep.get("pass", True):
        # Fallback: slight top & left margin expansion
        m = s.setdefault("layout", {}).setdefault("margins", {"l": 0.12, "r": 0.04, "t": 0.06, "b": 0.16})
        m["t"] = round(min(0.24, m.get("t", 0.06) + 0.025), 3)
        actions.append("fallback_margin_pad")

    return s, actions


def plan_and_render(
    data_paths: list[str | Path],
    chart_id: str,
    outdir: str | Path,
    name: str,
    theme: str = "origin-times-bold",
    caption: str = "",
    palette: str | None = None,
    max_sheets: int | None = None,
    max_repairs: int = 3,
    ref_png: str | Path | None = None,
) -> dict:
    """Full Blind-Mode workflow: inspect -> plan -> render -> QA -> up to 3 auto-repair cycles."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    spec, plan_meta = plan_spec(data_paths, chart_id, theme=theme, caption=caption, palette=palette, max_sheets=max_sheets)

    history = []
    cur_spec = spec
    final_qa = None
    final_spec_path = out / f"{name}.json"
    final_png_path = out / f"{name}.png"

    for it in range(max_repairs + 1):
        iter_spec_path = out / f"{name}_iter{it}.json"
        iter_spec_path.write_text(json.dumps(cur_spec, ensure_ascii=False, indent=1), encoding="utf-8")
        meta = engine.render(str(iter_spec_path), outdir=str(out), formats=("png",), dpi=300, name=f"{name}_iter{it}")
        iter_png = Path(meta["outputs"][0])
        qa_rep = qa_mod.run_qa(iter_spec_path, rendered_png=iter_png, ref_png=ref_png, out_json=out / f"{name}_iter{it}.qa.json")
        history.append({
            "iteration": it,
            "pass": qa_rep["pass"],
            "text_overlap_count": qa_rep["text_overlap_count"],
            "out_of_bounds_count": qa_rep["out_of_bounds_count"],
            "legend_data_overlap_count": qa_rep["legend_data_overlap_count"],
            "errors": qa_rep["errors"],
            "warnings": qa_rep["warnings"],
        })
        final_qa = qa_rep
        if qa_rep["pass"] and qa_rep["legend_data_overlap_count"] == 0:
            break
        if it < max_repairs:
            next_spec, actions = _repair_spec(cur_spec, qa_rep, plan_meta, it + 1)
            history[-1]["repair_actions"] = actions
            if not actions:
                break
            cur_spec = next_spec

    # Save canonical final outputs
    final_spec_path.write_text(json.dumps(cur_spec, ensure_ascii=False, indent=1), encoding="utf-8")
    engine.render(str(final_spec_path), outdir=str(out), formats=("png", "svg", "pdf"), dpi=300, name=name)
    final_qa = qa_mod.run_qa(final_spec_path, rendered_png=final_png_path, ref_png=ref_png, out_json=out / f"{name}.qa.json")

    return {
        "name": name,
        "chart_id": chart_id,
        "theme": theme,
        "caption": caption,
        "spec_path": str(final_spec_path),
        "png_path": str(final_png_path),
        "iterations_run": len(history),
        "history": history,
        "final_qa": final_qa,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SciFigStudio Blind / No-Reference Figure Planner")
    ap.add_argument("--data", nargs="+", required=True, help="Raw/tidy data path(s)")
    ap.add_argument("--chart", required=True, choices=sorted(PLANNERS.keys()), help="Chart asset ID")
    ap.add_argument("--theme", default="origin-times-bold")
    ap.add_argument("--palette", default=None)
    ap.add_argument("--caption", default="")
    ap.add_argument("-o", "--outdir", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--max-sheets", type=int, default=None)
    ap.add_argument("--max-repairs", type=int, default=3)
    a = ap.parse_args(argv)
    res = plan_and_render(
        a.data, a.chart, a.outdir, a.name,
        theme=a.theme, caption=a.caption, palette=a.palette,
        max_sheets=a.max_sheets, max_repairs=a.max_repairs,
    )
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
