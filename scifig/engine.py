"""SciFigStudio declarative rendering engine: spec JSON -> matplotlib Figure (PNG/SVG/PDF)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import to_rgb
from matplotlib.legend_handler import HandlerBase
from matplotlib.lines import Line2D
from matplotlib.offsetbox import DrawingArea, HPacker, TextArea
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import AutoMinorLocator, FormatStrFormatter, MultipleLocator
from PIL import Image

from . import __version__, readers, theme as theme_mod


# ---------------------------------------------------------------- gradient legend handler
class GradientPatch(Patch):
    """Legend proxy carrying a vertical gradient fill (white bottom -> color top)."""

    def __init__(self, facecolor="#6699BA", edgecolor="black", lw=0.6, alpha=0.9, **kwargs):
        super().__init__(facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, alpha=alpha, **kwargs)
        self._grad_color = facecolor
        self._grad_edge = edgecolor
        self._grad_lw = lw
        self._grad_alpha = alpha


class HandlerGradientPatch(HandlerBase):
    """Draws a crisp vertical gradient swatch inside legend handles."""

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        n_strips = 24
        rgb = np.array(to_rgb(orig_handle._grad_color))
        alpha = float(orig_handle._grad_alpha)
        artists = []
        dh = height / n_strips
        for i in range(n_strips):
            frac = (i + 0.5) / n_strips
            c_mix = 1.0 - (1.0 - rgb) * (0.12 + 0.88 * frac) * alpha
            r = Rectangle(
                (xdescent, ydescent + i * dh),
                width,
                dh * 1.08,
                facecolor=tuple(np.clip(c_mix, 0.0, 1.0)),
                edgecolor="none",
                linewidth=0,
                transform=trans,
            )
            artists.append(r)
        border = Rectangle(
            (xdescent, ydescent),
            width,
            height,
            facecolor="none",
            edgecolor=orig_handle._grad_edge,
            linewidth=orig_handle._grad_lw,
            transform=trans,
        )
        artists.append(border)
        return artists


# ---------------------------------------------------------------- data & preprocessing
def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_spec(path: str | Path) -> dict:
    p = Path(path)
    spec = json.loads(p.read_text(encoding="utf-8"))
    spec.setdefault("_base", str(p.parent))
    return spec


def load_chart_preset(chart_id: str) -> dict:
    p = theme_mod.assets_root() / "charts" / chart_id / "chart.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def merge_preset(spec: dict) -> dict:
    preset = load_chart_preset(spec.get("chart", "")) if spec.get("chart") else {}
    out = dict(spec)
    if preset:
        base = {k: v for k, v in preset.items() if k in ("style", "layout", "figure", "axes_defaults")}
        base.update(out)
        st = dict(preset.get("style", {}))
        st.update(out.get("style", {}))
        out["style"] = st
        ly = dict(preset.get("layout", {}))
        ly.update(out.get("layout", {}))
        out["layout"] = ly
        out.setdefault("_preset", preset.get("id"))
    return out


def _resolve_op_cols(df: pd.DataFrame, op: dict) -> list:
    if op.get("columns"):
        cols = []
        for ref in op["columns"]:
            if ref in df.columns:
                cols.append(ref)
            elif isinstance(ref, int) and ref < len(df.columns):
                cols.append(df.columns[ref])
            elif str(ref).isdigit() and int(ref) < len(df.columns):
                cols.append(df.columns[int(ref)])
        return cols
    if op.get("column") is not None:
        ref = op["column"]
        if ref in df.columns:
            return [ref]
        if isinstance(ref, int) and ref < len(df.columns):
            return [df.columns[ref]]
        if str(ref).isdigit() and int(ref) < len(df.columns):
            return [df.columns[int(ref)]]
    exclude = set(op.get("exclude") or [])
    num_cols = list(df.select_dtypes("number").columns)
    if op.get("keep_x", True) and len(num_cols) > 1 and df.columns[0] in num_cols:
        exclude.add(df.columns[0])
    return [c for c in num_cols if c not in exclude]


def _apply_ops(data: dict, ops: list) -> list[dict]:
    """Execute transparent preprocessing ops and return a detailed provenance log."""
    log: list[dict] = []
    for op in ops or []:
        kind = op.get("op")
        target_key = op.get("data")
        keys = [target_key] if target_key is not None else list(data.keys())
        for key in keys:
            if key not in data:
                continue
            df = data[key]
            cols = _resolve_op_cols(df, op)
            applied_cols = []
            if kind == "savgol":
                from scipy.signal import savgol_filter
                win = int(op.get("window", 9))
                pol = int(op.get("order", 3))
                for c in cols:
                    v = df[c].to_numpy(dtype=float)
                    if v.size > win and np.isfinite(v).all():
                        df[c] = savgol_filter(v, win, pol)
                        applied_cols.append(str(c))
            elif kind in ("baseline_min", "baseline_shift"):
                x_ref = op.get("x_col", 0)
                xr = op.get("x_range")
                xv = _col(df, x_ref) if (xr and len(df.columns) > 1) else None
                for c in cols:
                    v = df[c].to_numpy(dtype=float)
                    if xv is not None and xr is not None:
                        m = (xv >= min(xr)) & (xv <= max(xr)) & np.isfinite(v)
                        bval = float(np.nanmin(v[m])) if np.any(m) else float(np.nanmin(v))
                    else:
                        bval = float(np.nanmin(v))
                    df[c] = v - bval
                    applied_cols.append(str(c))
            elif kind == "baseline_linear":
                x_ref = op.get("x_col", 0)
                xv = _col(df, x_ref)
                xr = op.get("x_range") or [float(np.nanmin(xv)), float(np.nanmax(xv))]
                x0, x1 = float(xr[0]), float(xr[1])
                win_pts = int(op.get("edge_points", 5))
                for c in cols:
                    v = df[c].to_numpy(dtype=float)
                    order = np.argsort(xv)
                    xs, vs = xv[order], v[order]
                    m0 = np.isfinite(vs) & (np.abs(xs - x0) <= np.sort(np.abs(xs - x0))[min(win_pts - 1, len(xs) - 1)])
                    m1 = np.isfinite(vs) & (np.abs(xs - x1) <= np.sort(np.abs(xs - x1))[min(win_pts - 1, len(xs) - 1)])
                    y0 = float(np.nanmean(vs[m0])) if np.any(m0) else float(vs[0])
                    y1 = float(np.nanmean(vs[m1])) if np.any(m1) else float(vs[-1])
                    slope = (y1 - y0) / (x1 - x0) if abs(x1 - x0) > 1e-12 else 0.0
                    base_line = y0 + slope * (xv - x0)
                    df[c] = v - base_line
                    applied_cols.append(str(c))
            elif kind == "normalize_range":
                rng = op.get("range", [0.0, 1.0])
                lo, hi = float(rng[0]), float(rng[1])
                mode = op.get("mode", "minmax")
                for c in cols:
                    v = df[c].to_numpy(dtype=float)
                    vmin = float(np.nanmin(v))
                    vmax = float(np.nanmax(v))
                    if mode == "max":
                        denom = vmax if abs(vmax) > 1e-15 else 1.0
                        df[c] = v / denom * hi
                    else:
                        span = (vmax - vmin) if abs(vmax - vmin) > 1e-15 else 1.0
                        df[c] = lo + (v - vmin) / span * (hi - lo)
                    applied_cols.append(str(c))
            elif kind == "scale_offset":
                sc = float(op.get("scale", 1.0))
                off = float(op.get("offset", 0.0))
                for c in cols:
                    df[c] = df[c].to_numpy(dtype=float) * sc + off
                    applied_cols.append(str(c))
            if applied_cols:
                entry = {"op": kind, "data": key, "columns": applied_cols}
                for pk in ("window", "order", "x_range", "range", "mode", "scale", "offset"):
                    if pk in op:
                        entry[pk] = op[pk]
                log.append(entry)
    return log


def resolve_data(spec: dict) -> tuple[dict, list, list]:
    base = Path(spec.get("_base", "."))
    data, prov = {}, []
    for key, cfg in spec.get("data", {}).items():
        if isinstance(cfg, str):
            cfg = {"source": cfg}
        src = Path(cfg["source"])
        if not src.is_absolute():
            src = (base / src).resolve()
        reader = cfg.get("reader")
        if reader == "bruker":
            df = readers.read_bruker(str(src))
        elif reader == "spa":
            df = readers.read_spa(str(src))
        elif reader == "vgd":
            df = readers.read_vgd(str(src))
        elif reader == "asc":
            df = readers.read_asc(str(src))
        elif reader == "ras":
            df = readers.read_ras(str(src))
        elif reader == "spc":
            df = readers.read_spc(str(src))
        elif src.is_dir():
            df = readers.read_bruker(str(src))
        elif src.suffix.lower() in (".spa", ".vgd", ".asc", ".ras", ".spc"):
            df = readers.load_any(str(src))
        else:
            df = readers.read_table(
                src,
                sheet=cfg.get("sheet", 0),
                header=cfg.get("header", 0),
                skiprows=cfg.get("skiprows", 0),
                delimiter=cfg.get("delimiter"),
                encoding=cfg.get("encoding"),
                columns=cfg.get("columns") if isinstance(cfg.get("columns"), dict) else None,
            )
        data[key] = df
        data[key].attrs["source"] = str(src)
        entry = {
            "data": key,
            "source": str(src),
            "rows": int(df.shape[0]),
            "cols": list(map(str, df.columns))[:32],
        }
        if src.is_file():
            entry["sha256_16"] = _sha(src)
        prov.append(entry)
    ops_applied = _apply_ops(data, spec.get("ops") or [])
    return data, prov, ops_applied


def _col(df: pd.DataFrame, ref):
    if isinstance(ref, (list, tuple, np.ndarray)):
        return np.asarray(ref, dtype=float)
    if isinstance(ref, (int, float)) and not isinstance(ref, bool):
        return df.iloc[:, int(ref)].to_numpy(dtype=float)
    if ref in df.columns:
        return df[ref].to_numpy(dtype=float)
    sref = str(ref)
    for c in df.columns:
        if str(c) == sref:
            return df[c].to_numpy(dtype=float)
    raise KeyError(f"{ref} not in columns {list(df.columns)[:20]}")


def _series(spec: dict, data: dict, pl: dict):
    if "data" not in pl:
        x = np.asarray(pl["x"], dtype=float)
        y = np.asarray(pl["y"], dtype=float)
    else:
        df = data[pl["data"]]
        y = _col(df, pl["y"])
        x = _col(df, pl["x"]) if pl.get("x") is not None else np.arange(y.size, dtype=float)
    off = pl.get("offset", 0.0)
    if isinstance(off, (list, tuple)):
        off = 0.0
    scale = pl.get("scale", 1.0)
    y = y * scale + off
    if pl.get("dropna"):
        m = np.isfinite(x) & np.isfinite(y)
        x, y = x[m], y[m]
    clip = spec_ctx.get("clip")
    if clip:
        x, y = _clip_series(x, y, clip)
    return x, y


def _gradient_fill(ax, x, y, base, color, alpha, z, ny=220, nx=900):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 2:
        return None
    base_v = float(base) if np.isscalar(base) else float(np.nanmin(base))
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    x0, x1 = float(xs[0]), float(xs[-1])
    y1 = float(np.nanmax(ys))
    if y1 <= base_v:
        return None
    gx = np.linspace(x0, x1, nx)
    gy = np.linspace(base_v, y1, ny)
    curve = np.interp(gx, xs, ys)
    Yg = gy[:, None]
    inside = Yg <= curve[None, :]
    frac = np.clip((Yg - base_v) / np.maximum(curve[None, :] - base_v, 1e-12), 0, 1)
    rgb = np.array(to_rgb(color))
    img = np.zeros((ny, nx, 4))
    img[..., :3] = rgb
    img[..., 3] = np.where(inside, alpha * (0.10 + 0.90 * frac), 0.0)
    return ax.imshow(img, extent=[x0, x1, base_v, y1], origin="lower", aspect="auto", interpolation="bilinear", zorder=z)


def _ramp(c1: str, c2: str, n: int):
    a, b = to_rgb(c1), to_rgb(c2)
    if n <= 1:
        return ["#%02X%02X%02X" % tuple(int(round(v * 255)) for v in a)]
    out = []
    for i in range(n):
        t = i / (n - 1)
        out.append("#%02X%02X%02X" % tuple(int(round((a[k] + (b[k] - a[k]) * t) * 255)) for k in range(3)))
    return out


# ---------------------------------------------------------------- layout & axis styling
def _panel_rect(panel: dict, layout: dict) -> list:
    if "rect" in panel:
        return list(panel["rect"])
    m = layout.get("margins", {})
    l, r, t, b = m.get("l", 0.13), m.get("r", 0.03), m.get("t", 0.06), m.get("b", 0.17)
    gx, gy = layout.get("gap", [0.06, 0.08])
    cols, rows = layout.get("cols", 1), layout.get("rows", 1)
    W = (1 - l - r - gx * (cols - 1)) / cols
    H = (1 - t - b - gy * (rows - 1)) / rows
    cell = panel.get("cell", [0, 0])
    row, col = cell[0], cell[1]
    rs = cell[2] if len(cell) > 2 else 1
    cs = cell[3] if len(cell) > 3 else 1
    w = W * cs + gx * (cs - 1)
    h = H * rs + gy * (rs - 1)
    left = l + col * (W + gx)
    bottom = 1 - t - (row + rs) * H - row * gy
    return [left, bottom, w, h]


def _apply_axis(ax, axis_cfg: dict, which: str, th: dict):
    if not axis_cfg:
        axis_cfg = {}
    ax.set_axisbelow(False)
    if axis_cfg.get("scale"):
        (ax.set_xscale if which == "x" else ax.set_yscale)(axis_cfg["scale"])
    if axis_cfg.get("label"):
        lsize = axis_cfg.get("labelsize", th["size"]["label"])
        if which == "x":
            ax.set_xlabel(axis_cfg["label"], labelpad=axis_cfg.get("labelpad", 4), fontsize=lsize,
                          fontweight=th["font"]["weight"])
        else:
            ax.set_ylabel(axis_cfg["label"], labelpad=axis_cfg.get("labelpad", 4), fontsize=lsize,
                          fontweight=th["font"]["weight"])
    if axis_cfg.get("lim"):
        (ax.set_xlim if which == "x" else ax.set_ylim)(axis_cfg["lim"])
    if axis_cfg.get("ticks") is not None:
        (ax.set_xticks if which == "x" else ax.set_yticks)(axis_cfg["ticks"] or [])
    if axis_cfg.get("ticklabels"):
        (ax.set_xticklabels if which == "x" else ax.set_yticklabels)(axis_cfg["ticklabels"])
    if axis_cfg.get("tickformat"):
        (ax.xaxis if which == "x" else ax.yaxis).set_major_formatter(FormatStrFormatter(axis_cfg["tickformat"]))
    mn = axis_cfg.get("minor")
    if mn is None and th.get("tick", {}).get("minor"):
        mn = th["tick"]["minor"]
    if mn is not None and mn is not False:
        loc = ax.xaxis if which == "x" else ax.yaxis
        if isinstance(mn, (int, float)) and not isinstance(mn, bool) and mn > 0:
            loc.set_minor_locator(MultipleLocator(mn))
        elif mn:
            loc.set_minor_locator(AutoMinorLocator())
    if axis_cfg.get("hide"):
        (ax.xaxis if which == "x" else ax.yaxis).set_visible(False)


def _style_axes(ax, panel: dict, th: dict):
    t = th["tick"]
    show_top = bool(panel.get("x", {}).get("top_ticks", t.get("top", False)))
    show_right = bool(panel.get("y", {}).get("right_ticks", t.get("right", False)))
    ax.tick_params(
        axis="both",
        which="major",
        direction=t["direction"],
        length=t["length"],
        width=t["width"],
        pad=t["pad"],
        labelsize=th["size"]["tick"],
        colors="black",
        top=show_top,
        right=show_right,
    )
    ax.tick_params(
        axis="both",
        which="minor",
        direction=t["direction"],
        length=t["length"] * 0.55,
        width=t["width"] * 0.8,
        labelsize=th["size"]["tick"] * 0.85,
        top=show_top,
        right=show_right,
    )
    for s in ax.spines.values():
        s.set_linewidth(th["spines"]["lw"])
        s.set_color("black")
    show_all = panel.get("box", th["spines"].get("all", True))
    if not show_all:
        for k in ("top", "right"):
            ax.spines[k].set_visible(False)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_fontweight(th["font"]["weight"])


# ---------------------------------------------------------------- plot primitives
def _plot(ax, data, pl, th, pal, idx):
    kind = pl.get("type", "line")
    lw = pl.get("lw", th["line"]["data"])
    ls = pl.get("ls", "-")
    if isinstance(ls, list):
        ls = (ls[0], tuple(ls[1])) if len(ls) == 2 and isinstance(ls[1], list) else tuple(ls)
    ctoken = pl.get("color")
    if isinstance(ctoken, str) and ctoken.startswith("ramp@"):
        rcfg = (spec_ctx["spec"].get("style", {}) or {}).get("ramp", {})
        if rcfg.get("colors"):
            arr = rcfg["colors"]
            i = int(ctoken.split("@", 1)[1])
            color = arr[i % len(arr)]
        else:
            n = max(int(rcfg.get("count", 1)), 1)
            i = int(ctoken.split("@", 1)[1])
            stop = (i / (n - 1)) if n > 1 else 0.0
            color = _ramp(rcfg.get("from", "#FFFFFF"), rcfg.get("to", "#000000"), 1001)[int(round(stop * 1000))]
    else:
        color = theme_mod.resolve_color(ctoken, pal, idx)
    z = pl.get("zorder", 2)

    if kind in ("line", "lines"):
        keys = pl["y"] if isinstance(pl["y"], list) else [pl["y"]]
        labels = pl.get("labels") or [None] * len(keys)
        offsets = pl.get("offsets") or ([pl["offset"]] * len(keys) if "offset" in pl else [0.0] * len(keys))
        if isinstance(offsets, (int, float)):
            offsets = [offsets] * len(keys)
        ramp = pl.get("ramp")
        colors = _ramp(*ramp, len(keys)) if ramp else None
        handles = []
        for i, k in enumerate(keys):
            sub = dict(pl, y=k, offset=offsets[i])
            x, y = _series(spec_ctx["spec"], data, sub)
            if colors:
                c = colors[i]
            elif pl.get("colors") and i < len(pl["colors"]):
                c = theme_mod.resolve_color(pl["colors"][i], pal, idx + i)
            else:
                c = color
            h, = ax.plot(
                x, y, ls=ls, lw=lw, color=c, label=labels[i] or pl.get("label"),
                solid_capstyle=pl.get("capstyle", "round"), zorder=z,
                alpha=pl.get("alpha", 1.0), dash_capstyle="round",
                clip_on=pl.get("clip_on", True),
            )
            if pl.get("dashes"):
                h.set_dashes(pl["dashes"])
            handles.append(h)
        return handles

    if kind in ("line_marker", "scatter", "marker"):
        x, y = _series(spec_ctx["spec"], data, pl)
        mk = pl.get("marker", "o")
        ms = pl.get("ms", 5.0)
        mew = pl.get("mew", 1.0)
        mfc = theme_mod.resolve_color(pl.get("mfc"), pal, idx) if pl.get("mfc") else color
        mec = theme_mod.resolve_color(pl.get("mec"), pal, idx) if pl.get("mec") else color
        markevery = pl.get("markevery")
        if kind == "scatter":
            h = ax.plot(
                x, y, ls="none", marker=mk, ms=ms, mew=mew, mfc=mfc, mec=mec, zorder=z,
                label=pl.get("label"), color=color, markevery=markevery,
                clip_on=pl.get("clip_on", True),
            )
            return list(h)
        h, = ax.plot(
            x, y, ls=ls, lw=lw, color=color, marker=mk, ms=ms, mew=mew, mfc=mfc,
            mec=mec, label=pl.get("label"), zorder=z, markevery=markevery,
            clip_on=pl.get("clip_on", True),
        )
        return [h]

    if kind == "fill":
        x, y = _series(spec_ctx["spec"], data, pl)
        base = pl.get("baseline", 0.0)
        if base == "offset":
            off = pl.get("offset", 0.0)
            base = off if isinstance(off, (int, float)) else 0.0
        if isinstance(base, str) and "data" in pl and base in data[pl["data"]].columns:
            base = _col(data[pl["data"]], base)
        fc = theme_mod.resolve_color(pl.get("color"), pal, idx)
        if pl.get("gradient"):
            _gradient_fill(ax, x, y, base, fc, pl.get("alpha", 0.9), z)
        else:
            ax.fill_between(x, base, y, color=fc, alpha=pl.get("alpha", 0.85), linewidth=0, zorder=z, label=pl.get("label"))
        if pl.get("edge"):
            ec = theme_mod.resolve_color(pl.get("edgecolor"), pal, idx) if pl.get("edgecolor") else fc
            ax.plot(x, y, lw=pl.get("lw", th["line"]["fit"]), color=ec, zorder=z + 0.1)
        if pl.get("label"):
            if pl.get("gradient"):
                return [GradientPatch(facecolor=fc, edgecolor=pl.get("edgecolor", "black"), lw=0.5, alpha=pl.get("alpha", 0.9), label=pl["label"])]
            return [Patch(facecolor=fc, alpha=pl.get("alpha", 0.85), label=pl["label"])]
        return []

    if kind == "bar":
        df = data[pl["data"]]
        x = np.arange(len(df)) if pl.get("x") is None else _col(df, pl["x"])
        h = _col(df, pl["y"])
        width = pl.get("width", 0.7)
        colors = pl.get("colors")
        cols = [theme_mod.resolve_color(c, pal, i) for i, c in enumerate(colors)] if colors else [
            theme_mod.resolve_color(pl.get("color"), pal, idx)]
        bars = ax.bar(x, h, width=width, color=cols, edgecolor=pl.get("edgecolor", "black"),
                      linewidth=pl.get("lw", th["line"]["thin"]), label=pl.get("label"), zorder=z)
        if pl.get("labels"):
            for b, lab in zip(bars, pl["labels"]):
                b.set_label(lab)
        if pl.get("ticklabels"):
            ax.set_xticks(x)
            ax.set_xticklabels(pl["ticklabels"])
        return list(bars)

    if kind == "bar_stacked":
        df = data[pl["data"]]
        keys = pl["y"] if isinstance(pl["y"], list) else [pl["y"]]
        xpos = np.arange(len(df)) if pl.get("x") is None else _col(df, pl["x"])
        width = pl.get("width", 0.62)
        colors = pl.get("colors") or [f"fill:{i}" for i in range(len(keys))]
        bottom = np.zeros(len(df))
        patches = []
        val_fmt = pl.get("value_format", "{:.0f}")
        val_min = float(pl.get("value_min", 0.0))
        val_color = pl.get("value_color", "black")
        val_size = pl.get("value_size", th["size"].get("annot", 7.1))
        edge_c = pl.get("edgecolor", "black")
        edge_lw = pl.get("lw", 0.5)
        use_grad = bool(pl.get("gradient"))
        for i, k in enumerate(keys):
            vals = np.nan_to_num(_col(df, k))
            c = theme_mod.resolve_color(colors[i] if i < len(colors) else f"fill:{i}", pal, i)
            lbl = pl.get("labels", [None] * len(keys))[i] if pl.get("labels") else None
            bars = ax.bar(
                xpos, vals, width=width, bottom=bottom,
                color="none" if use_grad else c,
                edgecolor=edge_c, linewidth=edge_lw, zorder=z,
                label=None if use_grad else lbl,
            )
            if use_grad:
                for bx, bv, bb in zip(xpos, vals, bottom):
                    if bv <= 0:
                        continue
                    grad = np.linspace(0, 1, 64).reshape(-1, 1)
                    rgb = np.array(to_rgb(c))
                    img = np.ones((64, 2, 3))
                    for ch in range(3):
                        img[:, :, ch] = 1.0 - (1.0 - rgb[ch]) * (0.12 + 0.88 * grad)
                    ax.imshow(
                        img,
                        extent=[bx - width / 2, bx + width / 2, bb, bb + bv],
                        origin="lower",
                        aspect="auto",
                        zorder=z - 0.01,
                        interpolation="bilinear",
                    )
                    ax.add_patch(Rectangle(
                        (bx - width / 2, bb), width, bv,
                        fill=False, edgecolor=edge_c, linewidth=edge_lw, zorder=z + 0.01,
                    ))
                if lbl:
                    patches.append(GradientPatch(facecolor=c, edgecolor=edge_c, lw=edge_lw, alpha=0.95, label=lbl))
            else:
                patches.extend(list(bars))
            if pl.get("values"):
                for bx, bv, bb in zip(xpos, vals, bottom):
                    if bv > val_min:
                        ax.text(
                            bx, bb + bv / 2, val_fmt.format(bv),
                            ha="center", va="center", fontsize=val_size,
                            color=val_color, fontweight=th["font"]["weight"], zorder=z + 1,
                        )
            bottom = bottom + vals
        if pl.get("ticklabels"):
            ax.set_xticks(xpos)
            ax.set_xticklabels(
                pl["ticklabels"],
                fontsize=pl.get("tick_size", th["size"]["tick"]),
                fontweight=th["font"]["weight"],
            )
        if pl.get("tick_rotation"):
            rot = pl["tick_rotation"]
            for lab in ax.get_xticklabels():
                lab.set_rotation(rot)
                lab.set_ha(pl.get("tick_ha", "right"))
        return patches

    if kind == "comb":
        xs = [float(v) for v in (pl.get("x_positions") or pl.get("x") or [])]
        if not xs:
            return []
        yb = float(pl["y_base"])
        yt = float(pl["y_top"])
        x_span = pl.get("x_span") or [min(xs), max(xs)]
        clw = float(pl.get("lw", max(0.8, th["line"]["data"] * 0.7)))
        ccol = theme_mod.resolve_color(pl.get("color", "#000000"), pal, idx) if pl.get("color") else "black"
        for tx in xs:
            ax.plot([tx, tx], [yb, yt], color=ccol, lw=clw, zorder=z, solid_capstyle="butt")
        ax.plot([float(x_span[0]), float(x_span[1])], [yt, yt], color=ccol, lw=clw, zorder=z, solid_capstyle="butt")
        if pl.get("label"):
            lx = (float(x_span[0]) + float(x_span[1])) / 2.0
            dy = float(pl.get("label_dy", 0.0))
            lsz = pl.get("label_size", th["size"].get("annot", 7.1))
            if isinstance(lsz, str):
                lsz = th["size"].get(lsz, th["size"]["annot"])
            ax.text(
                lx, yt + dy, pl["label"],
                ha=pl.get("ha", "center"), va=pl.get("va", "bottom"),
                fontsize=lsz, color=ccol, fontweight=th["font"]["weight"], zorder=z + 0.5,
            )
        return []

    if kind == "hline":
        return [ax.axhline(pl["y"], color=color, lw=lw, ls=ls, zorder=z)]
    if kind == "vline":
        ymin, ymax = pl.get("ymin", 0.0), pl.get("ymax", 1.0)
        return [ax.axvline(pl["x"], ymin=ymin, ymax=ymax, color=color, lw=lw, ls=ls, zorder=z)]
    if kind == "axvspan":
        ax.axvspan(pl["x0"], pl["x1"], color=color, alpha=pl.get("alpha", 0.15), lw=0, zorder=0)
        return []
    if kind == "text":
        txt = pl.get("text", "")
        raw_sz = pl.get("size", "annot")
        size = th["size"].get(raw_sz, th["size"]["annot"]) if isinstance(raw_sz, str) else raw_sz
        if pl.get("leader"):
            lx, ly = pl["leader"]
            ax.plot(
                [pl["xy"][0], lx], [pl["xy"][1], ly],
                color=pl.get("leader_color", "black"),
                lw=pl.get("leader_lw", th["line"]["thin"] * 1.4),
                ls=pl.get("leader_ls", "--"),
                solid_capstyle="butt", zorder=4.5,
            )
        trans = ax.transAxes if pl.get("coords") == "axes" else ax.transData
        bbox_cfg = pl.get("bbox")
        ax.text(
            pl["xy"][0], pl["xy"][1], txt, rotation=pl.get("rotation", 0),
            ha=pl.get("ha", "center"), va=pl.get("va", "bottom"),
            fontsize=size, color=pl.get("color", "black"), zorder=pl.get("zorder", 5),
            transform=trans, fontweight=pl.get("weight", th["font"]["weight"]),
            clip_on=pl.get("clip", True), bbox=bbox_cfg,
        )
        return []
    if kind == "arrow":
        ax.annotate(
            "", xy=pl["xy"], xytext=pl["xytext"],
            arrowprops=dict(
                arrowstyle=pl.get("style", "->"), color=color,
                lw=pl.get("lw", th["line"]["thin"]), shrinkA=0, shrinkB=0,
            ),
            zorder=6,
        )
        return []
    raise ValueError(f"unknown plot type: {kind}")


# ---------------------------------------------------------------- broken-axis & secondary axes
def _norm_breaks(panel: dict) -> list:
    out = []
    for b in (panel.get("breaks") or []):
        a0, a1 = sorted((float(b["from"]), float(b["to"])))
        mk = {"size": 5.5, "gap": 2.8, "side": "both", "lw": None, "halo": True}
        mk.update(b.get("mark") or {})
        out.append({
            "axis": str(b.get("axis", "y")).lower(),
            "from": a0,
            "to": a1,
            "size_ratio": float(b.get("size_ratio", 0.15)),
            "angle": float(b.get("angle", 45.0)),
            "mark": mk,
        })
    axes = sorted({b["axis"] for b in out})
    if len(axes) > 1:
        raise ValueError(f"breaks in one panel must share one axis: {axes}")
    return sorted(out, key=lambda r: r["from"])


def _axis_span(panel: dict, data: dict, axis: str):
    cfg = panel.get(axis) or {}
    if cfg.get("lim"):
        lo, hi = float(cfg["lim"][0]), float(cfg["lim"][1])
        return min(lo, hi), max(lo, hi)
    vals = []
    for pl in panel.get("plots", []):
        if "data" not in pl or (pl.get("axis") or "y") in ("y2", "x2"):
            continue
        try:
            x, y = _series(spec_ctx["spec"], data, pl)
        except Exception:
            continue
        v = np.asarray(y if axis == "y" else x, dtype=float)
        vals.append(v[np.isfinite(v)])
    if not vals:
        raise ValueError(f"break axis requires panel.{axis}.lim or valid data")
    v = np.concatenate(vals)
    return float(np.min(v)), float(np.max(v))


def _break_segments(lo: float, hi: float, brks: list) -> list:
    out, cur = [], float(lo)
    for b in sorted(brks, key=lambda r: r["from"]):
        a0, a1 = max(b["from"], float(lo)), min(b["to"], float(hi))
        if a1 <= a0 or a0 <= cur:
            continue
        out.append((cur, a0, b))
        cur = a1
    out.append((cur, float(hi), None))
    return out


def _alloc_sizes(total: float, segs: list, min_frac: float = 0.12) -> list:
    gaps = [(s[2]["size_ratio"] if s[2] else 0.0) for s in segs[:-1]]
    free = float(total) * max(1.0 - sum(gaps), 1e-3)
    w = np.array([max(s[1] - s[0], 0.0) for s in segs], dtype=float)
    w = np.where(w <= 0, 1.0, w)
    w = np.maximum(w, min_frac * float(np.max(w)))
    return list(free * w / w.sum())


def _cross_t(p: float, q: float, bounds: list):
    if not (np.isfinite(p) and np.isfinite(q)) or abs(q - p) < 1e-15:
        return None
    cand = [b for b in bounds if min(p, q) < b < max(p, q)]
    if not cand:
        return None
    bnd = min(cand, key=lambda b: abs((b - p) / (q - p) - 0.5))
    return float((bnd - p) / (q - p))


def _clip_series(x, y, clip: dict):
    if not clip:
        return x, y
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    v = y if clip.get("axis", "y") == "y" else x
    bounds = sorted(float(b) for b in (clip.get("bounds") or [clip["lo"], clip["hi"]]))
    if clip.get("mode", "keep") == "keep":
        keep = (v >= bounds[0]) & (v <= bounds[-1])
    else:
        keep = np.ones(v.size, dtype=bool)
        for a, b in zip(bounds[0::2], bounds[1::2]):
            keep &= ~((v >= a) & (v <= b))
    keep = keep & np.isfinite(v)
    if bool(keep.all()):
        return x, y
    idx = np.nonzero(keep)[0]
    if idx.size == 0:
        return x[:0], y[:0]
    runs = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
    ox, oy = [], []
    for k, run in enumerate(runs):
        a, b = int(run[0]), int(run[-1])
        if a > 0:
            t = _cross_t(v[a - 1], v[a], bounds)
            if t is not None:
                ox.append(x[a - 1] + t * (x[a] - x[a - 1]))
                oy.append(y[a - 1] + t * (y[a] - y[a - 1]))
        ox.extend(x[a:b + 1].tolist())
        oy.extend(y[a:b + 1].tolist())
        if b < v.size - 1:
            t = _cross_t(v[b], v[b + 1], bounds)
            if t is not None:
                ox.append(x[b] + t * (x[b + 1] - x[b]))
                oy.append(y[b] + t * (y[b + 1] - y[b]))
        if k < len(runs) - 1:
            ox.append(np.nan)
            oy.append(np.nan)
    return np.array(ox, float), np.array(oy, float)


def _plot_series(axmap: dict, panel: dict, data: dict, th: dict, pal: dict, handles: list,
                 clip: dict | None = None, keys=None):
    for i, pl in enumerate(panel.get("plots", [])):
        if "data" not in pl and pl.get("type") not in ("text", "arrow", "hline", "vline", "axvspan", "comb", "line"):
            continue
        key = pl.get("axis") or "y"
        if keys is not None and key not in keys:
            continue
        ax = axmap.get(key) or axmap.get("y")
        if ax is None:
            continue
        spec_ctx["clip"] = clip
        try:
            hs = _plot(ax, data, pl, th, pal, i)
        finally:
            spec_ctx["clip"] = None
        if hs:
            handles.extend([h for h in hs if h is not None])


def _draw_break_marks(ax, srect: list, fig, edge: str, brk: dict, th: dict):
    """Draw crisp point-sized // break marks along an axis break edge."""
    mk = brk.get("mark", {})
    if mk.get("side") == "none":
        return
    fw, fh = fig.get_figwidth(), fig.get_figheight()
    sw, sh = max(srect[2] * fw, 1e-6), max(srect[3] * fh, 1e-6)
    half_in = float(mk.get("size", 5.0)) / 72.0 / 2.0
    gap_in = float(mk.get("gap", 2.4)) / 72.0
    angle = float(brk.get("angle", 60.0))
    dx = half_in / sw
    dy = half_in * np.tan(np.deg2rad(angle)) / sh
    vert = edge in ("left", "right")
    edge_v = 1.0 if edge in ("top", "right") else 0.0
    lw = float(mk.get("lw") or th["spines"]["lw"] * 0.9)
    ends = {"both": (0.0, 1.0), "left": (0.0,), "right": (1.0,)}.get(mk.get("side", "both"), (0.0, 1.0))
    seg = []
    if vert:
        # Horizontal x-axis break: slashes cross top (y=1) and bottom (y=0) spines
        for e in ends:
            for k in (-0.5, 0.5):
                off = k * gap_in / sw
                seg.append((edge_v + off, e))
    else:
        for e in ends:
            for k in (-0.5, 0.5):
                off = k * gap_in / sw
                seg.append((e + off, edge_v))
    if mk.get("halo", True):
        for xc, yc in seg:
            ax.plot([xc - dx, xc + dx], [yc - dy, yc + dy], transform=ax.transAxes,
                    color="white", lw=lw * 2.5, solid_capstyle="butt", clip_on=False, zorder=9.4)
    for xc, yc in seg:
        ax.plot([xc - dx, xc + dx], [yc - dy, yc + dy], transform=ax.transAxes,
                color="black", lw=lw, solid_capstyle="butt", clip_on=False, zorder=9.5)


def _draw_segment_slash(ax, srect: list, fig, side: str, th: dict, angle: float = 65.0):
    """Draw a single crisp // pair at left (x=0) or right (x=1) end of a broken x-segment."""
    fw, fh = fig.get_figwidth(), fig.get_figheight()
    sw, sh = max(srect[2] * fw, 1e-6), max(srect[3] * fh, 1e-6)
    half_in = 3.2 / 72.0
    dx = half_in / np.tan(np.deg2rad(angle)) / sw
    dy = half_in / sh
    xv = 1.0 if side == "right" else 0.0
    lw = th["spines"]["lw"] * 0.9
    for yy in (0.0, 1.0):
        ax.plot([xv - dx, xv + dx], [yy - dy, yy + dy], transform=ax.transAxes,
                color="black", lw=lw, solid_capstyle="butt", clip_on=False, zorder=9.5)


def _setup_secondary(ax2, key: str, cfg: dict, th: dict):
    which = "y" if key.startswith("y") else "x"
    side = "right" if which == "y" else "top"
    color = cfg.get("color") or "black"
    for k in ("left", "right", "top", "bottom"):
        ax2.spines[k].set_visible(k == side)
    ax2.spines[side].set_linewidth(th["spines"]["lw"])
    ax2.spines[side].set_color(color)
    if which == "y":
        ax2.yaxis.set_ticks_position("right")
        ax2.yaxis.set_label_position("right")
    else:
        ax2.xaxis.set_ticks_position("top")
        ax2.xaxis.set_label_position("top")
    ax2.tick_params(axis="both", which="both", left=False, right=False, bottom=False, top=False,
                    labelleft=False, labelright=False, labelbottom=False, labeltop=False)
    ax2.tick_params(axis=which, which="major", direction=th["tick"]["direction"],
                    length=th["tick"]["length"], width=th["tick"]["width"],
                    pad=th["tick"]["pad"], labelsize=th["size"]["tick"], colors=color)
    ax2.tick_params(axis=which, which="minor", direction=th["tick"]["direction"],
                    length=th["tick"]["length"] * 0.55, width=th["tick"]["width"] * 0.8, colors=color)
    _apply_axis(ax2, cfg, which, th)
    lab = ax2.yaxis.label if which == "y" else ax2.xaxis.label
    lab.set_color(color)
    lab.set_fontweight(th["font"]["weight"])
    for t in (ax2.get_yticklabels() if which == "y" else ax2.get_xticklabels()):
        t.set_color(color)
        t.set_fontweight(th["font"]["weight"])


def _build_broken(panel: dict, fig, rect: list, data: dict, th: dict, pal: dict):
    brks = _norm_breaks(panel)
    axis = brks[0]["axis"]
    lo, hi = _axis_span(panel, data, axis)
    segs = _break_segments(lo, hi, brks)
    L, B, W, H = rect
    total = H if axis == "y" else W
    sizes = _alloc_sizes(total, segs)
    gaps = [(s[2]["size_ratio"] * total if s[2] else 0.0) for s in segs[:-1]] + [0.0]

    axes, srects, pos = [], [], (B if axis == "y" else L)
    for i in range(len(segs)):
        srect = [L, pos, W, sizes[i]] if axis == "y" else [pos, B, sizes[i], H]
        ax = fig.add_axes(srect)
        _style_axes(ax, panel, th)
        axes.append(ax)
        srects.append(srect)
        pos += sizes[i] + gaps[i]

    xcfg, ycfg = dict(panel.get("x") or {}), dict(panel.get("y") or {})
    handles: list = []
    for i, (s0, s1, _b) in enumerate(segs):
        ax = axes[i]
        bcfg = dict(ycfg if axis == "y" else xcfg)
        bcfg.pop("lim", None)
        if i > 0:
            bcfg.pop("label", None)
        _apply_axis(ax, bcfg, axis, th)
        (ax.set_ylim if axis == "y" else ax.set_xlim)([s0, s1])
        if bcfg.get("ticks"):
            sel = [t for t in bcfg["ticks"] if s0 - 1e-9 <= t <= s1 + 1e-9]
            if sel:
                (ax.set_yticks if axis == "y" else ax.set_xticks)(sel)
        scfg = dict(xcfg if axis == "y" else ycfg)
        if i > 0:
            scfg.pop("label", None)
        _apply_axis(ax, scfg, "x" if axis == "y" else "y", th)
        if axis == "y" and i > 0:
            ax.tick_params(axis="x", labelbottom=False)
        if axis == "x" and i > 0:
            ax.tick_params(axis="y", left=False, labelleft=False)
            ax.spines["left"].set_visible(False)
        if segs[i][2] is not None:
            _draw_break_marks(ax, srects[i], fig, "top" if axis == "y" else "right", segs[i][2], th)
        if i > 0:
            _draw_break_marks(ax, srects[i], fig, "bottom" if axis == "y" else "left", segs[i - 1][2], th)
        hs = handles if i == 0 else []
        _plot_series({"y": ax}, panel, data, th, pal, hs, keys=("y",),
                     clip={"axis": axis, "bounds": [s0, s1], "mode": "keep"})

    if axis == "y" and ycfg.get("label"):
        for a in axes:
            a.set_ylabel("")
        fig.canvas.draw()
        rr = fig.canvas.get_renderer()
        wid = max([t.get_window_extent(renderer=rr).width for a in axes for t in a.get_yticklabels()] + [0.0])
        fw = fig.get_figwidth()
        xoff = rect[0] - (wid / fig.dpi + th["tick"]["pad"] / 72.0 + th["size"]["label"] / 72.0 + 0.010) / fw
        fig.text(max(0.004, xoff), rect[1] + rect[3] / 2.0, ycfg["label"], rotation=90,
                 ha="center", va="center", fontsize=th["size"]["label"], fontweight=th["font"]["weight"])
    elif axis == "x" and xcfg.get("label"):
        for a in axes:
            a.set_xlabel("")
        fh = fig.get_figheight()
        lpad = xcfg.get("labelpad", 4)
        dy_in = (th["tick"]["pad"] + th["size"]["tick"] + lpad + th["size"]["label"] * 0.55) / 72.0
        fig.text(rect[0] + rect[2] / 2.0, max(0.01, rect[1] - dy_in / fh), xcfg["label"],
                 ha="center", va="center", fontsize=th["size"]["label"], fontweight=th["font"]["weight"])

    sec = dict(panel.get("axes") or {})
    if sec:
        saxes = {}
        for key, cfg in sec.items():
            cfg = dict(cfg or {})
            if len(axes) > 1:
                ax2 = fig.add_axes(rect)
                ax2.patch.set_visible(False)
                ax2.set_zorder(4)
                (ax2.xaxis if key.startswith("y") else ax2.yaxis).set_visible(False)
            else:
                ax2 = axes[0].twiny() if key.startswith("x") else axes[0].twinx()
            _setup_secondary(ax2, key, cfg, th)
            if key.startswith("y"):
                ax2.set_xlim(axes[0].get_xlim())
            else:
                ax2.set_ylim(axes[0].get_ylim())
            saxes[key] = ax2
        clip2 = None
        ynull = [c.get("lim") for k, c in sec.items() if k.startswith("y")]
        if axis == "y" and len(segs) > 1 and ynull and all(ynull):
            y0, y1 = float(ynull[0][0]), float(ynull[0][1])
            bands = []
            for i in range(len(segs) - 1):
                g0 = B + sum(sizes[:i + 1]) + sum(gaps[:i])
                bands += [y0 + (g0 - B) / H * (y1 - y0), y0 + (g0 + gaps[i] - B) / H * (y1 - y0)]
            clip2 = {"axis": "y", "bounds": bands, "mode": "drop"}
        _plot_series(saxes, panel, data, th, pal, handles, clip=clip2, keys=tuple(saxes))
    return axes, handles


# ---------------------------------------------------------------- seamless stacked subpanels
def _build_subpanels(panel: dict, fig, rect: list, data: dict, th: dict, pal: dict):
    """Seamless stacked subpanels (hspace=0 by default, shared outer frame, internal dividers)."""
    subs = panel["subpanels"]
    n = len(subs)
    L, B, W, H = rect
    hspace = float(panel.get("hspace", 0.0))
    order = panel.get("stack_order", "top_to_bottom")
    if order == "bottom_to_top":
        subs_ordered = list(reversed(subs))
    else:
        subs_ordered = list(subs)
    weights = [float(s.get("height", s.get("weight", 1.0))) for s in subs_ordered]
    avail_h = H - hspace * (n - 1)
    heights = [avail_h * wt / sum(weights) for wt in weights]

    divider_lw = float(panel.get("divider_lw", th["spines"]["lw"] * 0.75))
    divider_color = panel.get("divider_color", "black")
    frame_lw = float(panel.get("frame_lw", th["spines"]["lw"]))

    axes = []
    handles = []
    cur_top = B + H
    xcfg = dict(panel.get("x") or {})
    ycfg = dict(panel.get("y") or {})

    for idx_top, sub in enumerate(subs_ordered):
        sh = heights[idx_top]
        cur_bot = cur_top - sh
        ax = fig.add_axes([L, cur_bot, W, sh])
        _style_axes(ax, panel, th)

        # Spine management for seamless shared outer frame + non-doubled internal dividers
        ax.spines["left"].set_linewidth(frame_lw)
        ax.spines["right"].set_linewidth(frame_lw)
        if idx_top == 0:
            ax.spines["top"].set_linewidth(frame_lw)
        else:
            ax.spines["top"].set_visible(False)
        if idx_top == n - 1:
            ax.spines["bottom"].set_linewidth(frame_lw)
        else:
            ax.spines["bottom"].set_linewidth(divider_lw)
            ax.spines["bottom"].set_color(divider_color)

        # X axis: shared across all subpanels; tick labels only on bottom-most subpanel
        sub_xcfg = dict(xcfg)
        if idx_top < n - 1:
            sub_xcfg.pop("label", None)
        _apply_axis(ax, sub_xcfg, "x", th)
        if idx_top < n - 1:
            show_inner_ticks = bool(panel.get("inner_xticks", False))
            ax.tick_params(axis="x", which="both", bottom=show_inner_ticks, top=False, labelbottom=False)

        # Y axis: per-subpanel y config
        sub_ycfg = dict(sub.get("y") or {})
        sub_ycfg.pop("label", None)
        if "ticks" not in sub_ycfg and "ticks" in ycfg:
            sub_ycfg["ticks"] = ycfg["ticks"]
        _apply_axis(ax, sub_ycfg, "y", th)

        # Plots for this subpanel
        sub_handles: list = []
        _plot_series({"y": ax}, sub, data, th, pal, sub_handles)
        handles.extend(sub_handles)

        # Optional per-subpanel sample label
        s_lbl = sub.get("sample_label")
        if s_lbl:
            if isinstance(s_lbl, str):
                s_lbl = {"text": s_lbl}
            loc = s_lbl.get("loc", "upper right")
            xy = s_lbl.get("xy")
            if xy is None:
                ha = "right" if "right" in loc else "left"
                va = "top" if "upper" in loc else ("bottom" if "lower" in loc else "center")
                xy = [0.96 if ha == "right" else 0.04, 0.88 if va == "top" else 0.10]
            else:
                ha = s_lbl.get("ha", "right")
                va = s_lbl.get("va", "bottom")
            sz = s_lbl.get("size", th["size"].get("legend", 10.2))
            ax.text(
                xy[0], xy[1], s_lbl["text"], transform=ax.transAxes,
                ha=ha, va=va, fontsize=sz, color=s_lbl.get("color", "black"),
                fontweight=s_lbl.get("weight", th["font"]["weight"]), zorder=6,
            )

        # Optional per-subpanel legend
        if sub.get("legend"):
            _add_legend(ax, sub_handles, sub["legend"], th, pal)

        axes.append(ax)
        cur_top = cur_bot - hspace

    # Shared panel-level annotations / plots on top subpanel or target subpanel
    for i, pl in enumerate(panel.get("plots", [])):
        t_idx = int(pl.get("subpanel", 0))
        _plot(axes[min(max(t_idx, 0), n - 1)], data, pl, th, pal, i)

    # Shared vertical guide lines spanning all subpanels
    for g in panel.get("shared_guides", []):
        gx = float(g["x"])
        gc = g.get("color", "black")
        glw = float(g.get("lw", th["line"].get("fit", 0.8)))
        gls = g.get("ls", "--")
        for a in axes:
            a.axvline(gx, color=gc, lw=glw, ls=gls, zorder=g.get("zorder", 3))
        if g.get("label"):
            top_ax = axes[0]
            top_ax.text(
                gx, g.get("label_y", 1.03), g["label"],
                transform=top_ax.get_xaxis_transform(),
                ha=g.get("ha", "center"), va=g.get("va", "bottom"),
                fontsize=g.get("size", th["size"].get("annot", 7.1)),
                color=g.get("label_color", gc),
                fontweight=th["font"]["weight"], clip_on=False, zorder=7,
            )

    # Shared centered Y-axis label across the full stacked height
    if ycfg.get("label"):
        fw = fig.get_figwidth()
        fig.canvas.draw()
        rr = fig.canvas.get_renderer()
        wid = max([t.get_window_extent(renderer=rr).width for a in axes for t in a.get_yticklabels()] + [0.0])
        pad_pt = ycfg.get("labelpad", 5.0)
        xoff = L - (wid / fig.dpi + (th["tick"]["pad"] if wid > 0 else 0.0) / 72.0 + pad_pt / 72.0 + th["size"]["label"] * 0.55 / 72.0) / fw
        fig.text(
            max(0.005, xoff), B + H / 2.0, ycfg["label"],
            rotation=90, ha="center", va="center",
            fontsize=ycfg.get("labelsize", th["size"]["label"]),
            fontweight=th["font"]["weight"],
        )

    return axes, handles


# ---------------------------------------------------------------- native image montage
def _crop_image(img: Image.Image, crop_cfg) -> Image.Image:
    if not crop_cfg:
        return img
    w, h = img.size
    if crop_cfg == "square":
        side = min(w, h)
        x0 = (w - side) // 2
        y0 = (h - side) // 2
        return img.crop((x0, y0, x0 + side, y0 + side))
    if isinstance(crop_cfg, (list, tuple)) and len(crop_cfg) == 4:
        x0, y0, x1, y1 = [float(v) for v in crop_cfg]
        if max(x0, y0, x1, y1) <= 1.0:
            return img.crop((int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h))))
        return img.crop((int(x0), int(y0), int(x1), int(y1)))
    return img


def _build_montage(panel: dict, fig, rect: list, base_dir: Path, th: dict):
    mcfg = panel.get("montage") or panel
    rows, cols = mcfg.get("grid", [1, len(mcfg.get("images", []))])
    imgs = mcfg.get("images", [])
    gap = mcfg.get("gap", 0.004)
    if isinstance(gap, (list, tuple)):
        gx, gy = float(gap[0]), float(gap[1])
    else:
        gx = gy = float(gap)

    L, B, W, H = rect
    cw = (W - gx * (cols - 1)) / cols
    ch = (H - gy * (rows - 1)) / rows
    frame_lw = float(mcfg.get("frame_lw", 0.6))
    frame_color = mcfg.get("frame_color", "#222222")
    row_letters = mcfg.get("row_letters") or []
    axes = []

    for idx, item in enumerate(imgs):
        r, c = divmod(idx, cols)
        if r >= rows:
            break
        cfg = {"source": item} if isinstance(item, str) else dict(item)
        src = Path(cfg["source"])
        if not src.is_absolute():
            src = (base_dir / src).resolve()
        im = Image.open(src)
        im = _crop_image(im, cfg.get("crop"))
        arr = np.asarray(im)

        ax_l = L + c * (cw + gx)
        ax_b = B + H - (r + 1) * ch - r * gy
        ax = fig.add_axes([ax_l, ax_b, cw, ch])
        if arr.ndim == 2:
            if arr.dtype == np.uint8:
                ax.imshow(arr, cmap="gray", vmin=0, vmax=255)
            else:
                ax.imshow(arr, cmap="gray")
        else:
            ax.imshow(arr)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_linewidth(frame_lw)
            sp.set_color(frame_color)

        # Optional per-tile letter or row letter on col 0
        ltr = cfg.get("letter")
        if not ltr and c == 0 and r < len(row_letters):
            rl = row_letters[r]
            ltr = rl if isinstance(rl, dict) else {"text": str(rl)}
        if ltr:
            ld = ltr if isinstance(ltr, dict) else {"text": str(ltr)}
            ax.text(
                ld.get("x", 0.05), ld.get("y", 0.94), ld["text"],
                transform=ax.transAxes, ha=ld.get("ha", "left"), va=ld.get("va", "top"),
                fontsize=ld.get("size", th["size"]["panel"]),
                color=ld.get("color", "white"),
                fontweight=th["font"]["weight"],
                bbox=ld.get("bbox"),
                zorder=8,
            )

        # Element badge (e.g. Si, Al, Cu)
        badge = cfg.get("badge")
        if badge:
            bd = badge if isinstance(badge, dict) else {"text": str(badge)}
            ax.text(
                bd.get("x", 0.94), bd.get("y", 0.94), bd["text"],
                transform=ax.transAxes, ha=bd.get("ha", "right"), va=bd.get("va", "top"),
                fontsize=bd.get("size", th["size"]["legend"]),
                color=bd.get("color", "white"),
                fontweight=th["font"]["weight"],
                bbox=bd.get("bbox"),
                zorder=8,
            )

        # Scale bar
        sb = cfg.get("scale_bar")
        if sb:
            frac = float(sb.get("frac", 0.22))
            x0 = float(sb.get("x", 0.08))
            y0 = float(sb.get("y", 0.08))
            col_sb = sb.get("color", "white")
            lw_sb = float(sb.get("lw", 2.2))
            ax.plot([x0, x0 + frac], [y0, y0], transform=ax.transAxes, color=col_sb, lw=lw_sb, solid_capstyle="butt", zorder=8)
            if sb.get("text"):
                ax.text(
                    x0 + frac / 2.0, y0 + float(sb.get("text_dy", 0.03)), sb["text"],
                    transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=sb.get("size", th["size"].get("annot", 7.1)),
                    color=col_sb, fontweight=th["font"]["weight"], zorder=8,
                )

        axes.append(ax)
    return axes


# ---------------------------------------------------------------- inset zoom
def _connect_inset(fig, pax, ins, irect: list, cfg: dict, th: dict):
    x0, x1 = cfg.get("xlim") or pax.get_xlim()
    y0, y1 = cfg.get("ylim") or pax.get_ylim()
    st = cfg.get("connect") if isinstance(cfg.get("connect"), dict) else {}
    color = st.get("color", cfg.get("connect_color", "black"))
    lw = float(st.get("lw", th["line"]["thin"] * 1.8))
    ls = st.get("ls", "-")
    z = float(ins.get_zorder()) - 0.5
    pax.add_patch(Rectangle((min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
                            fill=False, edgecolor=color, lw=lw, ls=ls, zorder=z))
    rc = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    ic = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
    fig_pts = fig.transFigure.inverted().transform(pax.transData.transform(rc))
    cx_r = (fig_pts[0][0] + fig_pts[3][0]) / 2.0
    cy_r = (fig_pts[0][1] + fig_pts[3][1]) / 2.0
    cx_i, cy_i = irect[0] + irect[2] / 2.0, irect[1] + irect[3] / 2.0
    if abs(cx_i - cx_r) * fig.get_figwidth() > abs(cy_i - cy_r) * fig.get_figheight():
        pairs = [(0, 1), (2, 3)] if cx_i < cx_r else [(1, 0), (3, 2)]
    else:
        pairs = [(0, 2), (1, 3)] if cy_i < cy_r else [(2, 0), (3, 1)]
    for ri, ii in pairs:
        p0 = fig_pts[ri]
        p1 = (irect[0] + ic[ii][0] * irect[2], irect[1] + ic[ii][1] * irect[3])
        fig.add_artist(Line2D([p0[0], p1[0]], [p0[1], p1[1]], transform=fig.transFigure,
                              color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="round"))


def _add_inset(fig, parent_ax, panel: dict, rect: list, data: dict, th: dict, pal: dict, idx0: int = 0):
    cfg = panel.get("inset") or {}
    if not cfg:
        return None
    L, B, W, H = rect
    r = cfg.get("rect", [0.56, 0.56, 0.34, 0.34])
    irect = [L + r[0] * W, B + r[1] * H, r[2] * W, r[3] * H]
    ins = fig.add_axes(irect)
    ins.set_zorder(cfg.get("zorder", 6))
    _style_axes(ins, {"box": cfg.get("box", True)}, th)
    flw = float(cfg.get("frame_lw", 0.8)) * th["spines"]["lw"]
    tsz = float(cfg.get("tick_size", th["size"]["tick"] * 0.78))
    for s in ins.spines.values():
        s.set_linewidth(flw)
        s.set_visible(True)
    ins.tick_params(axis="both", which="major", labelsize=tsz, direction=th["tick"]["direction"],
                    length=th["tick"]["length"] * 0.8, width=th["tick"]["width"] * 0.8,
                    pad=th["tick"]["pad"] * 0.6)
    if cfg.get("xlim"):
        ins.set_xlim(cfg["xlim"])
    if cfg.get("ylim"):
        ins.set_ylim(cfg["ylim"])
    for i, pl in enumerate(cfg.get("plots", [])):
        spec_ctx["clip"] = None
        _plot(ins, data, pl, th, pal, idx0 + i)
    if cfg.get("xlabel"):
        ins.set_xlabel(cfg["xlabel"], fontsize=tsz, labelpad=1.2, fontweight=th["font"]["weight"])
    if cfg.get("ylabel"):
        ins.set_ylabel(cfg["ylabel"], fontsize=tsz, labelpad=1.2, fontweight=th["font"]["weight"])
    for lab in ins.get_xticklabels() + ins.get_yticklabels():
        lab.set_fontweight(th["font"]["weight"])
    if cfg.get("connect"):
        _connect_inset(fig, parent_ax, ins, irect, cfg, th)
    return ins


# ---------------------------------------------------------------- legend with aligned note
def _add_legend(ax, handles: list, lg: dict, th: dict, pal: dict):
    use = [h for h in handles if getattr(h, "get_label", None) and not str(h.get_label()).startswith("_")]
    if lg.get("proxies"):
        use = []
        for i, pp in enumerate(lg["proxies"]):
            c = theme_mod.resolve_color(pp.get("color"), pal, i)
            if pp.get("patch") and pp.get("gradient"):
                use.append(GradientPatch(facecolor=c, edgecolor=pp.get("edgecolor", "black"),
                                         lw=pp.get("lw", 0.5), alpha=pp.get("alpha", 0.95), label=pp["label"]))
            elif pp.get("patch"):
                use.append(Patch(facecolor=c, edgecolor=pp.get("edgecolor", "black"),
                                 linewidth=pp.get("lw", 0.5), alpha=pp.get("alpha", 1.0), label=pp["label"]))
            else:
                use.append(Line2D([], [], color=c, lw=pp.get("lw", th["line"]["data"]),
                                  ls=pp.get("ls", "-"), marker=pp.get("marker", None),
                                  ms=pp.get("ms", 5), mfc=pp.get("mfc", c), mec=pp.get("mec", c),
                                  label=pp["label"]))
    fs = lg.get("fontsize", th["size"]["legend"])
    hlen = lg.get("handlelength", th["legend"]["handlelength"])
    hpad = lg.get("handletextpad", th["legend"]["handletextpad"])
    kwargs = dict(
        loc=lg.get("loc", "upper right"),
        ncol=lg.get("ncol", 1),
        frameon=lg.get("frameon", th["legend"]["frameon"]),
        fontsize=fs,
        handlelength=hlen,
        handletextpad=hpad,
        borderaxespad=lg.get("borderaxespad", th["legend"]["borderaxespad"]),
        labelspacing=lg.get("labelspacing", 0.25),
        columnspacing=lg.get("columnspacing", 1.0),
        handler_map={GradientPatch: HandlerGradientPatch()},
    )
    if lg.get("bbox"):
        kwargs["bbox_to_anchor"] = lg["bbox"]
    if lg.get("title"):
        kwargs["title"] = lg["title"]
    leg = ax.legend(handles=use, **kwargs)
    for txt in leg.get_texts():
        txt.set_fontweight(th["font"]["weight"])
    if lg.get("frameon"):
        leg.get_frame().set_linewidth(th["line"]["thin"])

    notes = lg.get("notes") or ([lg["note"]] if lg.get("note") else [])
    if notes and hasattr(leg, "_legend_box") and leg._legend_box is not None:
        note_fs = lg.get("note_fontsize", fs)
        align = lg.get("note_align", "text")
        pad_pts = (hlen + hpad) * note_fs if align == "text" else 0.0
        for nt in notes:
            ta = TextArea(
                nt,
                textprops=dict(
                    fontsize=note_fs,
                    fontweight=th["font"]["weight"],
                    color=lg.get("note_color", "black"),
                ),
            )
            ta.set_figure(ax.figure)
            if pad_pts > 0:
                spacer = DrawingArea(pad_pts, 1.0, 0.0, 0.0)
                spacer.set_figure(ax.figure)
                row = HPacker(children=[spacer, ta], align="baseline", pad=0, sep=0)
                row.set_figure(ax.figure)
            else:
                row = ta
            if lg.get("note_pos") == "top":
                leg._legend_box.get_children().insert(0, row)
            else:
                leg._legend_box.get_children().append(row)
    return leg


# ---------------------------------------------------------------- build & render
spec_ctx = {"spec": {}, "clip": None}


def build(spec: dict) -> plt.Figure:
    spec = merge_preset(spec)
    spec_ctx["spec"] = spec
    th = theme_mod.load_theme(spec.get("theme"))
    if spec.get("style", {}).get("theme"):
        th = theme_mod.load_theme(spec["style"]["theme"])
    # Apply proportional scale factor and per-spec style overrides
    st = spec.get("style", {})
    if st.get("scale"):
        th = theme_mod.scale_theme(th, float(st["scale"]))
    for sk in ("font", "size", "line", "tick", "spines", "legend"):
        if isinstance(st.get(sk), dict):
            th[sk] = theme_mod.deep_merge(th[sk], st[sk])
    theme_mod.apply_mpl(th)
    pal = theme_mod.load_palette(spec.get("palette") or th.get("palette"))

    fs = spec.get("figure", {})
    w, h = fs.get("width_in", 7.09), fs.get("height_in", 2.93)
    fig = plt.figure(figsize=(w, h), dpi=100)
    data, _, _ = resolve_data(spec)
    layout = spec.get("layout", {})
    base_dir = Path(spec.get("_base", "."))

    for panel in spec.get("panels", []):
        rect = _panel_rect(panel, layout)
        axes, handles = [], []
        broken = False

        if panel.get("type") == "image_montage" or panel.get("montage"):
            axes = _build_montage(panel, fig, rect, base_dir, th)
            ax = axes[0] if axes else fig.add_axes(rect)
            if panel.get("letter"):
                lt = panel["letter"] if isinstance(panel["letter"], dict) else {"text": panel["letter"]}
                fig.text(
                    rect[0] + lt.get("x", 0.0) * rect[2],
                    rect[1] + lt.get("y", 1.01) * rect[3],
                    lt.get("text", ""),
                    fontsize=lt.get("size", th["size"]["panel"]),
                    fontweight=th["font"]["weight"],
                    ha="left", va="bottom",
                )
            continue

        if panel.get("subpanels"):
            axes, handles = _build_subpanels(panel, fig, rect, data, th, pal)
            ax = axes[-1]
            broken = True  # treat panel-level letter via rect
        elif panel.get("segments"):
            segs = panel["segments"]
            n = len(segs)
            gapw = float(panel.get("break_gap", layout.get("break_gap", 0.016)))
            wts = [(s[2] if len(s) > 2 else 1.0) for s in segs]
            avail = rect[2] - gapw * (n - 1)
            ws = [avail * wt / sum(wts) for wt in wts]
            xs = [rect[0] + sum(ws[:i]) + gapw * i for i in range(n)]
            srects = []
            for si, seg in enumerate(segs):
                x0, x1 = seg[0], seg[1]
                srect = [xs[si], rect[1], ws[si], rect[3]]
                ax = fig.add_axes(srect)
                _style_axes(ax, panel, th)
                lo, hi = min(x0, x1), max(x0, x1)
                for i, pl in enumerate(panel.get("plots", [])):
                    if "data" not in pl and pl.get("type") not in ("text", "arrow", "hline", "vline", "axvspan", "comb", "line"):
                        continue
                    segsel = pl.get("seg")
                    if segsel is not None:
                        allowed = segsel if isinstance(segsel, list) else [segsel]
                        if si not in allowed:
                            continue
                    elif pl.get("type") == "vline":
                        xv = float(pl["x"])
                        if not (lo - 1e-9 <= xv <= hi + 1e-9):
                            continue
                    elif pl.get("type") == "text" and pl.get("coords", "data") == "data":
                        xv = float(pl["xy"][0])
                        if not (lo - 1e-9 <= xv <= hi + 1e-9):
                            continue
                    hs = _plot(ax, data, pl, th, pal, i)
                    if hs and si == 0:
                        handles.extend([hv for hv in hs if hv is not None])
                ycfg = dict(panel.get("y", {}))
                if si > 0:
                    ycfg.pop("label", None)
                _apply_axis(ax, ycfg, "y", th)
                xcfg_s = dict(panel.get("x", {}))
                xcfg_s.pop("label", None)
                xcfg_s.pop("lim", None)
                xt = xcfg_s.get("ticks")
                if xt is not None:
                    xcfg_s["ticks"] = [t for t in xt if lo - 1e-9 <= t <= hi + 1e-9]
                _apply_axis(ax, xcfg_s, "x", th)
                ax.set_xlim([x0, x1])
                ax.set_xlabel("")
                if si > 0:
                    ax.tick_params(axis="y", left=False, labelleft=False)
                    ax.spines["left"].set_visible(False)
                    _draw_segment_slash(ax, srect, fig, "left", th)
                if si < n - 1:
                    ax.spines["right"].set_visible(False)
                    _draw_segment_slash(ax, srect, fig, "right", th)
                axes.append(ax)
                srects.append(srect)
            xlabel_txt = panel.get("x", {}).get("label", "")
            if xlabel_txt:
                lpad = panel.get("x", {}).get("labelpad", 4.0)
                dy_in = (th["tick"]["pad"] + th["size"]["tick"] + lpad + th["size"]["label"] * 0.55) / 72.0
                fig.text(
                    rect[0] + rect[2] / 2.0, max(0.008, rect[1] - dy_in / fig.get_figheight()),
                    xlabel_txt, ha="center", va="center",
                    fontsize=th["size"]["label"], fontweight=th["font"]["weight"],
                )
            ax = axes[0]
            broken = len(axes) > 1
        elif panel.get("breaks"):
            axes, handles = _build_broken(panel, fig, rect, data, th, pal)
            broken = len(axes) > 1
            ax = axes[0]
        else:
            ax = fig.add_axes(rect)
            _style_axes(ax, panel, th)
            axmap = {"y": ax}
            for key, cfg in (panel.get("axes") or {}).items():
                ax2 = ax.twiny() if key.startswith("x") else ax.twinx()
                _setup_secondary(ax2, key, dict(cfg or {}), th)
                axmap[key] = ax2
                if key.startswith("y"):
                    ax.spines["right"].set_visible(False)
            _plot_series(axmap, panel, data, th, pal, handles)
            _apply_axis(ax, panel.get("x", {}), "x", th)
            _apply_axis(ax, panel.get("y", {}), "y", th)
            axes = [ax]

        rot = panel.get("tick_rotation") or panel.get("x", {}).get("tick_rotation")
        if rot:
            target_ax = axes[-1] if panel.get("subpanels") else ax
            for lab in target_ax.get_xticklabels():
                lab.set_rotation(rot)
                lab.set_ha(panel.get("tick_ha", "right"))

        if panel.get("grid"):
            for a in (axes if broken else [ax]):
                a.grid(True, lw=th["line"]["thin"], color="#000000", alpha=0.25, zorder=0)

        if panel.get("letter"):
            lt = panel["letter"] if isinstance(panel["letter"], dict) else {"text": panel["letter"]}
            lsz = lt.get("size", th["size"]["panel"])
            if broken:
                fig.text(
                    rect[0] + lt.get("x", -0.20) * rect[2],
                    rect[1] + lt.get("y", 1.03) * rect[3],
                    lt.get("text", ""), fontsize=lsz, fontweight=th["font"]["weight"],
                    ha="left", va="bottom",
                )
            else:
                ax.text(
                    lt.get("x", -0.20), lt.get("y", 1.03), lt.get("text", ""),
                    transform=ax.transAxes, fontsize=lsz, fontweight=th["font"]["weight"],
                    ha="left", va="bottom",
                )

        lg = panel.get("legend")
        if lg:
            seg_idx = lg.get("seg")
            if seg_idx is None:
                if panel.get("segments") and "right" in str(lg.get("loc", "")):
                    lax = axes[-1]
                elif panel.get("subpanels"):
                    lax = axes[0]
                else:
                    lax = axes[0]
            else:
                lax = axes[min(int(seg_idx), len(axes) - 1)] if int(seg_idx) >= 0 else axes[max(len(axes) + int(seg_idx), 0)]
            _add_legend(lax, handles, lg, th, pal)

        if panel.get("inset") and not panel.get("segments"):
            pax, icfg = ax, panel["inset"]
            if broken and icfg.get("ylim"):
                mid = sum(icfg["ylim"]) / 2.0
                for a in axes:
                    lo_, hi_ = a.get_ylim()
                    if lo_ - 1e-9 <= mid <= hi_ + 1e-9:
                        pax = a
                        break
            _add_inset(fig, pax, panel, rect, data, th, pal, len(panel.get("plots", [])))
    return fig


def render(
    spec_path: str,
    outdir: str | None = None,
    formats=("png", "svg", "pdf"),
    dpi: int | None = None,
    name: str | None = None,
) -> dict:
    spec = load_spec(spec_path)
    spec = merge_preset(spec)
    fig = build(spec)
    base = Path(outdir) if outdir else Path(spec["_base"]) / "scifig_out"
    base.mkdir(parents=True, exist_ok=True)
    stem = name or Path(spec_path).stem
    dpi = dpi or spec.get("figure", {}).get("dpi", 600)
    outputs = []
    for fmt in formats:
        p = base / f"{stem}.{fmt}"
        fig.savefig(
            p, dpi=dpi, format=fmt, bbox_inches=None, pad_inches=0,
            transparent=False, facecolor="white",
            metadata={"Creator": f"SciFigStudio {__version__}"},
        )
        outputs.append(str(p))
    _, prov, ops_applied = resolve_data(spec)
    meta = {
        "engine": f"SciFigStudio {__version__}",
        "spec": str(Path(spec_path).resolve()),
        "chart": spec.get("chart"),
        "theme": spec.get("theme") or "origin-times-bold",
        "palette": spec.get("palette") or "publication-pastel",
        "figure_in": [spec.get("figure", {}).get("width_in"), spec.get("figure", {}).get("height_in")],
        "dpi": dpi,
        "outputs": outputs,
        "data": prov,
        "ops": spec.get("ops", []),
        "ops_applied": ops_applied,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }
    (base / f"{stem}.provenance.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    plt.close(fig)
    return meta
