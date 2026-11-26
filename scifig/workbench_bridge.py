"""SciFigStudio Interactive Visual Editing Workbench — Engine Bridge, Geometry, QA & AI NLU."""
from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.text import Text as MplText

from . import __version__, blind_planner, engine, qa as qa_mod, theme as theme_mod


def _bundle_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _writable_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        try:
            probe = exe_dir / ".scifig_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return exe_dir
        except Exception:
            fallback = Path.home() / "SciFigStudio"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback
    return Path(__file__).resolve().parents[1]


def _example_dirs() -> list[Path]:
    cands = [
        STUDIO_ROOT / "examples",
        BUNDLE_ROOT / "examples",
        Path(__file__).resolve().parents[1] / "examples",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        cands.extend([exe_dir / "examples", exe_dir / "_internal" / "examples"])
    out: list[Path] = []
    seen: set[str] = set()
    for d in cands:
        try:
            r = d.resolve()
        except Exception:
            r = d
        key = str(r).lower()
        if key not in seen and r.is_dir():
            seen.add(key)
            out.append(r)
    return out


STUDIO_ROOT = _writable_root()
BUNDLE_ROOT = _bundle_root()
RENDER_LOCK = threading.Lock()


# ---------------------------------------------------------------- helpers
def _natural_key(text: str) -> list:
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", text)]


def _clean_user_spec(spec: dict) -> dict:
    """Return a clean copy of spec without transient internal keys (_base, _preset)."""
    out = copy.deepcopy(spec)
    out.pop("_base", None)
    out.pop("_preset", None)
    return out


def _sha16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _px_box_to_norm(x0: float, y0: float, x1: float, y1: float, fw: float, fh: float) -> list[float]:
    """Convert Matplotlib display pixels (bottom-left origin) to HTML/SVG norm [x0,y0,x1,y1] (top-left origin)."""
    nx0 = float(x0) / max(fw, 1.0)
    nx1 = float(x1) / max(fw, 1.0)
    ny0 = 1.0 - float(y1) / max(fh, 1.0)
    ny1 = 1.0 - float(y0) / max(fh, 1.0)
    return [round(min(nx0, nx1), 5), round(min(ny0, ny1), 5), round(max(nx0, nx1), 5), round(max(ny0, ny1), 5)]


def _px_pt_to_norm(x: float, y: float, fw: float, fh: float) -> list[float]:
    return [round(float(x) / max(fw, 1.0), 5), round(1.0 - float(y) / max(fh, 1.0), 5)]


def _norm_pt_to_px(nx: float, ny: float, fw: float, fh: float) -> tuple[float, float]:
    return float(nx) * fw, (1.0 - float(ny)) * fh


def _json_diff_lines(before: dict, after: dict, max_lines: int = 40) -> list[str]:
    a = json.dumps(_clean_user_spec(before), ensure_ascii=False, indent=1).splitlines()
    b = json.dumps(_clean_user_spec(after), ensure_ascii=False, indent=1).splitlines()
    diff = list(difflib.unified_diff(a, b, fromfile="before.json", tofile="after.json", lineterm="", n=1))
    out = [ln for ln in diff if not ln.startswith(("---", "+++"))]
    return out[:max_lines]


def _json_safe(val: Any) -> Any:
    if isinstance(val, (np.floating, float)):
        return None if (np.isnan(val) or np.isinf(val)) else round(float(val), 6)
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if val is None or isinstance(val, str):
        return val
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    return str(val)


# ---------------------------------------------------------------- spec catalog & path resolution
def _scan_spec_entries() -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {"examples": [], "blind": [], "main": [], "si": []}

    seen_ex: set[str] = set()
    for ex_dir in _example_dirs():
        spec_files = sorted(
            {p.resolve() for p in list(ex_dir.glob("*_spec.json")) + list(ex_dir.glob("demo_spec.json"))},
            key=lambda x: _natural_key(x.stem),
        )
        for p in spec_files:
            if p.stem in seen_ex:
                continue
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            seen_ex.add(p.stem)
            groups["examples"].append({
                "id": f"examples/{p.stem}",
                "name": p.stem,
                "group": "examples",
                "chart": raw.get("chart", ""),
                "theme": raw.get("theme", "origin-times-bold"),
                "palette": raw.get("palette", "publication-pastel"),
                "note": raw.get("_note", ""),
                "path": str(p),
            })

    blind_dir = STUDIO_ROOT / "outputs" / "blind_eval"
    if blind_dir.exists():
        for p in sorted(blind_dir.glob("*_blind.json"), key=lambda x: _natural_key(x.stem)):
            if "_iter" in p.stem:
                continue
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            groups["blind"].append({
                "id": f"blind/{p.stem}",
                "name": p.stem,
                "group": "blind",
                "chart": raw.get("chart", ""),
                "theme": raw.get("theme", "origin-times-bold"),
                "palette": raw.get("palette", "publication-pastel"),
                "note": raw.get("_note", ""),
                "path": str(p.resolve()),
            })

    for grp, sub in (("main", STUDIO_ROOT / "specs" / "main"), ("si", STUDIO_ROOT / "specs" / "si")):
        if sub.exists():
            for p in sorted(sub.glob("*.json"), key=lambda x: _natural_key(x.stem)):
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                groups[grp].append({
                    "id": f"{grp}/{p.stem}",
                    "name": p.stem,
                    "group": grp,
                    "chart": raw.get("chart", ""),
                    "theme": raw.get("theme", "origin-times-bold"),
                    "palette": raw.get("palette", "publication-pastel"),
                    "note": raw.get("_note", ""),
                    "path": str(p.resolve()),
                })

    saved_dir = STUDIO_ROOT / "outputs" / "workbench_saved"
    if saved_dir.exists():
        saved = []
        for p in sorted(saved_dir.glob("*.json"), key=lambda x: _natural_key(x.stem)):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            saved.append({
                "id": f"saved/{p.stem}",
                "name": p.stem,
                "group": "saved",
                "chart": raw.get("chart", ""),
                "theme": raw.get("theme", "origin-times-bold"),
                "palette": raw.get("palette", "publication-pastel"),
                "note": raw.get("_note", ""),
                "path": str(p.resolve()),
            })
        if saved:
            groups["saved"] = saved

    return groups


def resolve_spec_entry(spec_id: str) -> dict | None:
    if not spec_id:
        return None
    groups = _scan_spec_entries()
    all_entries = [e for lst in groups.values() for e in lst]
    low = spec_id.strip().lower().replace("\\", "/")
    # 1. Exact id match
    for e in all_entries:
        if e["id"].lower() == low:
            return e
    # 2. Exact stem match (e.g. "demo_uvvis_spec", "demo_spec")
    for e in all_entries:
        if e["name"].lower() == low or (e["name"] + ".json").lower() == low:
            return e
    # 3. Direct file path
    p = Path(spec_id)
    if p.exists() and p.is_file():
        return {"id": p.stem, "name": p.stem, "group": "custom", "path": str(p.resolve())}
    return None


def _ensure_spec_base(spec: dict, spec_id: str | None = None) -> dict:
    """Ensure spec['_base'] is set so engine.resolve_data() always locates relative data files."""
    out = copy.deepcopy(spec)
    if not out.get("_base") and spec_id:
        ent = resolve_spec_entry(spec_id)
        if ent and ent.get("path"):
            out["_base"] = str(Path(ent["path"]).parent)

    # Verify each data source path; fallback to examples/ or STUDIO_ROOT if relative path needs anchoring
    candidate_bases = []
    if out.get("_base"):
        candidate_bases.append(Path(out["_base"]))
    candidate_bases.extend(_example_dirs())
    candidate_bases.extend([
        STUDIO_ROOT / "specs" / "main",
        STUDIO_ROOT / "specs" / "si",
        STUDIO_ROOT / "outputs" / "blind_eval",
        STUDIO_ROOT,
        BUNDLE_ROOT,
    ])
    for _k, cfg in (out.get("data") or {}).items():
        if isinstance(cfg, str):
            continue
        src = Path(cfg.get("source", ""))
        if src.is_absolute():
            continue
        if out.get("_base") and (Path(out["_base"]) / src).resolve().exists():
            continue
        for cb in candidate_bases:
            cand = (cb / src).resolve()
            if cand.exists():
                out["_base"] = str(cb)
                break
    ex_dirs = _example_dirs()
    out.setdefault("_base", str(ex_dirs[0] if ex_dirs else STUDIO_ROOT))
    return out


def get_catalog() -> dict:
    specs = _scan_spec_entries()
    a_root = theme_mod.assets_root()

    themes = []
    label_map = {
        "origin-times-bold": "Origin Times Bold",
        "journal-nature-arial": "Nature Arial",
        "journal-acs-serif": "ACS Serif",
    }
    for p in sorted((a_root / "themes").glob("*.json")):
        th = json.loads(p.read_text(encoding="utf-8"))
        themes.append({
            "id": p.stem,
            "name": th.get("name", p.stem),
            "label": label_map.get(p.stem, p.stem),
            "source": th.get("source", ""),
            "font_family": th.get("font", {}).get("family", "Times New Roman"),
            "font_weight": th.get("font", {}).get("weight", "bold"),
            "spines_all": th.get("spines", {}).get("all", True),
            "tick_direction": th.get("tick", {}).get("direction", "in"),
            "palette": th.get("palette", "publication-pastel"),
        })

    palettes = []
    for p in sorted((a_root / "palettes").glob("*.json")):
        pal = json.loads(p.read_text(encoding="utf-8"))
        palettes.append({
            "id": p.stem,
            "name": pal.get("name", p.stem),
            "source": pal.get("source", ""),
            "sequence": pal.get("sequence", []),
            "fills": pal.get("fills", []),
        })

    charts = []
    for p in sorted((a_root / "charts").glob("*/chart.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        charts.append({
            "id": c.get("id", p.parent.name),
            "name": c.get("name", p.parent.name),
            "when": c.get("when", ""),
            "blind_supported": c.get("id", p.parent.name) in blind_planner.PLANNERS,
        })

    # Discover synthetic sample datasets in examples/ for live Blind Mode creation
    sample_datasets = []
    synthetic_catalog = [
        ("UV-Vis DRS Demo (Catalyst-A/B/C)", "demo_uvvis.csv", "06_single-multi-spectrum", "Synthetic UV-Vis DRS spectra of Catalyst-A/B/C"),
        ("Catalytic Evaluation Demo (NOx Conversion)", "demo_eval.csv", "01_line-marker-eval", "Synthetic catalytic NOx conversion vs Temperature"),
        ("In-situ DRIFTS Broken-Axis Demo", "demo_drifts.csv", "07_drifts-broken-stack", "Synthetic time-resolved in-situ DRIFTS spectra"),
    ]
    ex_dirs = _example_dirs()
    for label, fname, cid, title in synthetic_catalog:
        for ed in ex_dirs:
            cand = (ed / fname).resolve()
            if cand.exists():
                sample_datasets.append({
                    "label": label,
                    "path": str(cand),
                    "chart_id": cid,
                    "title": title,
                })
                break

    default_id = "examples/demo_uvvis_spec"
    if not resolve_spec_entry(default_id):
        for grp in ("examples", "blind", "main", "si", "saved"):
            if specs.get(grp):
                default_id = specs[grp][0]["id"]
                break

    return {
        "default_spec_id": default_id,
        "specs": specs,
        "themes": themes,
        "palettes": palettes,
        "charts": charts,
        "sample_datasets": sample_datasets,
    }


# ---------------------------------------------------------------- visibility filtering & artist mapping
def _filter_visible_spec(spec: dict) -> dict:
    """Deep copy spec and remove plot/legend/letter/sample_label items marked visible: false."""
    out = copy.deepcopy(spec)
    for panel in out.get("panels", []):
        if "plots" in panel:
            panel["plots"] = [pl for pl in panel["plots"] if pl.get("visible", True) is not False]
        if panel.get("subpanels"):
            for sub in panel["subpanels"]:
                if "plots" in sub:
                    sub["plots"] = [pl for pl in sub["plots"] if pl.get("visible", True) is not False]
                sl = sub.get("sample_label")
                if isinstance(sl, dict) and sl.get("visible", True) is False:
                    sub.pop("sample_label", None)
        if isinstance(panel.get("legend"), dict) and panel["legend"].get("visible", True) is False:
            panel.pop("legend", None)
        if isinstance(panel.get("letter"), dict) and panel["letter"].get("visible", True) is False:
            panel.pop("letter", None)
    return out


def _map_panel_axes(spec: dict, fig: plt.Figure, data: dict) -> list[dict]:
    """Map each panel in spec to its exact Matplotlib Axes created by engine.build()."""
    axes_all = list(fig.axes)
    cursor = 0
    layout = spec.get("layout", {})
    panel_maps = []

    for pi, panel in enumerate(spec.get("panels", [])):
        rect = engine._panel_rect(panel, layout)
        pinfo: dict[str, Any] = {
            "panel_index": pi,
            "panel_id": panel.get("id", chr(ord("A") + pi)),
            "rect_fig": rect,
            "kind": "normal",
            "seg_axes": [],       # list of (seg_idx, subpanel_idx, ax)
            "subpanel_ax": {},    # original subpanel_idx -> ax
            "main_axes": [],
            "secondary_axes": [],
            "inset_ax": None,
        }

        if panel.get("type") == "image_montage" or panel.get("montage"):
            mcfg = panel.get("montage") or panel
            rows, cols = mcfg.get("grid", [1, len(mcfg.get("images", []))])
            n_img = min(len(mcfg.get("images", [])), rows * cols)
            n_ax = max(1, n_img)
            paxes = axes_all[cursor: cursor + n_ax]
            cursor += n_ax
            pinfo["kind"] = "montage"
            pinfo["main_axes"] = paxes
            for si, ax in enumerate(paxes):
                pinfo["seg_axes"].append((si, None, ax))

        elif panel.get("subpanels"):
            subs = panel["subpanels"]
            n = len(subs)
            paxes = axes_all[cursor: cursor + n]
            cursor += n
            pinfo["kind"] = "subpanels"
            pinfo["main_axes"] = paxes
            order = panel.get("stack_order", "top_to_bottom")
            orig_indices = list(reversed(range(n))) if order == "bottom_to_top" else list(range(n))
            for ax_i, orig_sub_i in enumerate(orig_indices):
                if ax_i < len(paxes):
                    pinfo["subpanel_ax"][orig_sub_i] = paxes[ax_i]
                    pinfo["seg_axes"].append((ax_i, orig_sub_i, paxes[ax_i]))

        elif panel.get("segments"):
            n = len(panel["segments"])
            paxes = axes_all[cursor: cursor + n]
            cursor += n
            pinfo["kind"] = "segments"
            pinfo["main_axes"] = paxes
            for si, ax in enumerate(paxes):
                pinfo["seg_axes"].append((si, None, ax))

        elif panel.get("breaks"):
            brks = engine._norm_breaks(panel)
            axis = brks[0]["axis"]
            lo, hi = engine._axis_span(panel, data, axis)
            segs = engine._break_segments(lo, hi, brks)
            n = len(segs)
            paxes = axes_all[cursor: cursor + n]
            cursor += n
            n_sec = len(panel.get("axes") or {})
            saxes = axes_all[cursor: cursor + n_sec]
            cursor += n_sec
            pinfo["kind"] = "breaks"
            pinfo["main_axes"] = paxes
            pinfo["secondary_axes"] = saxes
            for si, ax in enumerate(paxes):
                pinfo["seg_axes"].append((si, None, ax))

        else:
            paxes = axes_all[cursor: cursor + 1]
            cursor += 1
            n_sec = len(panel.get("axes") or {})
            saxes = axes_all[cursor: cursor + n_sec]
            cursor += n_sec
            pinfo["kind"] = "normal"
            pinfo["main_axes"] = paxes
            pinfo["secondary_axes"] = saxes
            if paxes:
                pinfo["seg_axes"].append((0, None, paxes[0]))

        if panel.get("inset") and not panel.get("segments") and not (panel.get("type") == "image_montage" or panel.get("montage")):
            if cursor < len(axes_all):
                pinfo["inset_ax"] = axes_all[cursor]
                cursor += 1

        panel_maps.append(pinfo)

    return panel_maps


def _pick_segment_ax(panel: dict, pinfo: dict, pl: dict) -> tuple[int, Any]:
    """Return (seg_index, ax) for a plot item inside a panel (handles broken-axis segments)."""
    axes = pinfo["main_axes"]
    if not axes:
        return 0, None
    if pinfo["kind"] == "segments":
        segs = panel.get("segments", [])
        segsel = pl.get("seg")
        if segsel is not None:
            si = int(segsel[0] if isinstance(segsel, list) else segsel)
            si = max(0, min(si, len(axes) - 1))
            return si, axes[si]
        xv = None
        if pl.get("type") == "vline":
            xv = float(pl["x"])
        elif pl.get("type") == "text" and pl.get("coords", "data") == "data":
            xv = float(pl["xy"][0])
        if xv is not None:
            for si, seg in enumerate(segs):
                lo, hi = min(seg[0], seg[1]), max(seg[0], seg[1])
                if lo - 1e-9 <= xv <= hi + 1e-9:
                    return si, axes[min(si, len(axes) - 1)]
    return 0, axes[0]


def _pick_legend_ax(panel: dict, pinfo: dict) -> tuple[int, Any]:
    axes = pinfo["main_axes"]
    if not axes:
        return 0, None
    lg = panel.get("legend") or {}
    seg_idx = lg.get("seg")
    if seg_idx is None:
        if panel.get("segments") and "right" in str(lg.get("loc", "")):
            return len(axes) - 1, axes[-1]
        return 0, axes[0]
    idx = min(int(seg_idx), len(axes) - 1) if int(seg_idx) >= 0 else max(len(axes) + int(seg_idx), 0)
    return idx, axes[idx]


def _match_text_artist(ax_or_fig, text_str: str, anchor_px: tuple[float, float], rr, used_ids: set[int]):
    """Find best matching MplText artist by text content and proximity to anchor_px."""
    best = None
    best_dist = 1e18
    for t in ax_or_fig.texts:
        if id(t) in used_ids:
            continue
        if str(t.get_text()) != str(text_str):
            continue
        try:
            bb = t.get_window_extent(renderer=rr)
            cx = 0.5 * (bb.x0 + bb.x1)
            cy = 0.5 * (bb.y0 + bb.y1)
            d = (cx - anchor_px[0]) ** 2 + (cy - anchor_px[1]) ** 2
            if d < best_dist:
                best_dist = d
                best = (t, bb)
        except Exception:
            continue
    if best is not None:
        used_ids.add(id(best[0]))
    return best


def _extract_handles(spec: dict, fig: plt.Figure, rr, panel_maps: list[dict], pal: dict, th: dict) -> dict:
    fw, fh = fig.canvas.get_width_height()
    panels_out = []
    items_out = []
    used_text_ids: set[int] = set()

    for pi, panel in enumerate(spec.get("panels", [])):
        pinfo = panel_maps[pi]
        pid = pinfo["panel_id"]
        rect = pinfo["rect_fig"]
        prect_norm = [
            round(rect[0], 5),
            round(1.0 - (rect[1] + rect[3]), 5),
            round(rect[0] + rect[2], 5),
            round(1.0 - rect[1], 5),
        ]

        segs_out = []
        for si, sub_i, ax in pinfo["seg_axes"]:
            pos = ax.get_position()
            xlim = [round(float(v), 6) for v in ax.get_xlim()]
            ylim = [round(float(v), 6) for v in ax.get_ylim()]
            segs_out.append({
                "seg_index": si,
                "subpanel_index": sub_i,
                "rect_norm": [round(pos.x0, 5), round(1.0 - pos.y1, 5), round(pos.x1, 5), round(1.0 - pos.y0, 5)],
                "xlim": xlim,
                "ylim": ylim,
                "x_inverted": bool(xlim[0] > xlim[1]),
                "y_inverted": bool(ylim[0] > ylim[1]),
            })

        panels_out.append({
            "id": f"panel:{pi}",
            "panel_index": pi,
            "panel_id": pid,
            "rect_norm": prect_norm,
            "has_segments": bool(panel.get("segments")),
            "has_subpanels": bool(panel.get("subpanels")),
            "segments": segs_out,
        })

        def _collect_plots(plot_list: list[dict], sub_idx: int | None, forced_ax=None):
            for plot_i, pl in enumerate(plot_list):
                kind = pl.get("type", "line")
                vis = pl.get("visible", True) is not False
                hid = f"p{pi}:sub{sub_idx}:plot:{plot_i}" if sub_idx is not None else f"p{pi}:plot:{plot_i}"
                if forced_ax is not None:
                    seg_i, ax = (sub_idx or 0), forced_ax
                else:
                    seg_i, ax = _pick_segment_ax(panel, pinfo, pl)

                resolved_color = theme_mod.resolve_color(pl.get("color"), pal, plot_i)
                ax_pos = ax.get_position() if ax is not None else None
                ax_rect_norm = (
                    [round(ax_pos.x0, 5), round(1.0 - ax_pos.y1, 5), round(ax_pos.x1, 5), round(1.0 - ax_pos.y0, 5)]
                    if ax_pos is not None else prect_norm
                )

                if kind == "text":
                    xy = pl.get("xy", [0.5, 0.5])
                    coords = pl.get("coords", "data")
                    trans = ax.transAxes if (ax is not None and coords == "axes") else (ax.transData if ax is not None else fig.transFigure)
                    apx = tuple(trans.transform((float(xy[0]), float(xy[1]))))
                    anchor_norm = _px_pt_to_norm(apx[0], apx[1], fw, fh)
                    matched = _match_text_artist(ax, pl.get("text", ""), apx, rr, used_text_ids) if (vis and ax is not None) else None
                    if matched is not None:
                        _, bb = matched
                        bbox_norm = _px_box_to_norm(bb.x0 - 2, bb.y0 - 2, bb.x1 + 2, bb.y1 + 2, fw, fh)
                    else:
                        bbox_norm = [
                            round(anchor_norm[0] - 0.025, 5),
                            round(anchor_norm[1] - 0.02, 5),
                            round(anchor_norm[0] + 0.025, 5),
                            round(anchor_norm[1] + 0.02, 5),
                        ]
                    raw_sz = pl.get("size", "annot")
                    sz_val = th["size"].get(raw_sz, th["size"]["annot"]) if isinstance(raw_sz, str) else float(raw_sz)
                    items_out.append({
                        "id": hid,
                        "kind": "text",
                        "panel_index": pi,
                        "panel_id": pid,
                        "subpanel_index": sub_idx,
                        "plot_index": plot_i,
                        "seg_index": seg_i,
                        "draggable": True,
                        "visible": vis,
                        "label": str(pl.get("text", "")),
                        "bbox_norm": bbox_norm,
                        "anchor_norm": anchor_norm,
                        "props": {
                            "text": str(pl.get("text", "")),
                            "xy": [float(xy[0]), float(xy[1])],
                            "coords": coords,
                            "size": round(float(sz_val), 2),
                            "color": pl.get("color", "#000000"),
                            "ha": pl.get("ha", "center"),
                            "va": pl.get("va", "bottom"),
                            "rotation": pl.get("rotation", 0),
                            "seg": pl.get("seg"),
                        },
                    })

                elif kind == "vline":
                    xv = float(pl["x"])
                    ymin_f = float(pl.get("ymin", 0.0))
                    ymax_f = float(pl.get("ymax", 1.0))
                    if ax is not None:
                        p0 = ax.get_xaxis_transform().transform((xv, ymin_f))
                        p1 = ax.get_xaxis_transform().transform((xv, ymax_f))
                        xn, y1n = _px_pt_to_norm(p0[0], p0[1], fw, fh)
                        _, y0n = _px_pt_to_norm(p1[0], p1[1], fw, fh)
                        y_top, y_bot = min(y0n, y1n), max(y0n, y1n)
                    else:
                        xn, y_top, y_bot = 0.5, prect_norm[1], prect_norm[3]
                    bbox_norm = [round(xn - 0.008, 5), round(y_top, 5), round(xn + 0.008, 5), round(y_bot, 5)]
                    items_out.append({
                        "id": hid,
                        "kind": "vline",
                        "panel_index": pi,
                        "panel_id": pid,
                        "subpanel_index": sub_idx,
                        "plot_index": plot_i,
                        "seg_index": seg_i,
                        "draggable": True,
                        "visible": vis,
                        "label": f"vline x={xv:g}",
                        "bbox_norm": bbox_norm,
                        "anchor_norm": [round(xn, 5), round(0.5 * (y_top + y_bot), 5)],
                        "x_norm": round(xn, 5),
                        "y0_norm": round(y_top, 5),
                        "y1_norm": round(y_bot, 5),
                        "props": {
                            "x": xv,
                            "ymin": ymin_f,
                            "ymax": ymax_f,
                            "color": resolved_color,
                            "lw": float(pl.get("lw", th["line"]["data"])),
                            "ls": pl.get("ls", "--"),
                            "seg": pl.get("seg"),
                        },
                    })

                elif kind == "hline":
                    yv = float(pl["y"])
                    if ax is not None:
                        p0 = ax.get_yaxis_transform().transform((0.0, yv))
                        p1 = ax.get_yaxis_transform().transform((1.0, yv))
                        x0n, yn = _px_pt_to_norm(p0[0], p0[1], fw, fh)
                        x1n, _ = _px_pt_to_norm(p1[0], p1[1], fw, fh)
                    else:
                        x0n, x1n, yn = prect_norm[0], prect_norm[2], 0.5
                    items_out.append({
                        "id": hid,
                        "kind": "hline",
                        "panel_index": pi,
                        "panel_id": pid,
                        "subpanel_index": sub_idx,
                        "plot_index": plot_i,
                        "seg_index": seg_i,
                        "draggable": True,
                        "visible": vis,
                        "label": f"hline y={yv:g}",
                        "bbox_norm": [round(min(x0n, x1n), 5), round(yn - 0.008, 5), round(max(x0n, x1n), 5), round(yn + 0.008, 5)],
                        "anchor_norm": [round(0.5 * (x0n + x1n), 5), round(yn, 5)],
                        "props": {
                            "y": yv,
                            "color": resolved_color,
                            "lw": float(pl.get("lw", th["line"]["data"])),
                            "ls": pl.get("ls", "--"),
                        },
                    })

                else:
                    lbl = pl.get("label") or (pl.get("labels")[0] if isinstance(pl.get("labels"), list) and pl["labels"] else None)
                    if not lbl:
                        lbl = f"{kind} ({pl.get('data', '')}:{pl.get('y', plot_i)})" if pl.get("data") else f"{kind} #{plot_i + 1}"
                    items_out.append({
                        "id": hid,
                        "kind": kind,
                        "panel_index": pi,
                        "panel_id": pid,
                        "subpanel_index": sub_idx,
                        "plot_index": plot_i,
                        "seg_index": seg_i,
                        "draggable": False,
                        "visible": vis,
                        "label": str(lbl),
                        "bbox_norm": ax_rect_norm,
                        "anchor_norm": [round(0.5 * (ax_rect_norm[0] + ax_rect_norm[2]), 5), round(0.5 * (ax_rect_norm[1] + ax_rect_norm[3]), 5)],
                        "props": {
                            "type": kind,
                            "data": pl.get("data"),
                            "x": pl.get("x"),
                            "y": pl.get("y"),
                            "label": pl.get("label") or "",
                            "color": resolved_color,
                            "lw": float(pl.get("lw", th["line"]["data"])),
                            "ls": pl.get("ls", "-"),
                            "offset": float(pl.get("offset", 0.0)) if isinstance(pl.get("offset", 0.0), (int, float)) else 0.0,
                            "scale": float(pl.get("scale", 1.0)),
                            "alpha": float(pl.get("alpha", 1.0)),
                        },
                    })

        if panel.get("subpanels"):
            for sub_i, sub in enumerate(panel["subpanels"]):
                sax = pinfo["subpanel_ax"].get(sub_i)
                _collect_plots(sub.get("plots", []), sub_i, forced_ax=sax)
                sl = sub.get("sample_label")
                if sl:
                    sld = sl if isinstance(sl, dict) else {"text": str(sl)}
                    vis_sl = sld.get("visible", True) is not False
                    loc = sld.get("loc", "upper right")
                    xy = sld.get("xy")
                    if xy is None:
                        ha = "right" if "right" in loc else "left"
                        va = "top" if "upper" in loc else ("bottom" if "lower" in loc else "center")
                        xy = [0.96 if ha == "right" else 0.04, 0.88 if va == "top" else 0.10]
                    else:
                        ha, va = sld.get("ha", "right"), sld.get("va", "bottom")
                    apx = tuple(sax.transAxes.transform((float(xy[0]), float(xy[1])))) if sax is not None else (0.5 * fw, 0.5 * fh)
                    anchor_norm = _px_pt_to_norm(apx[0], apx[1], fw, fh)
                    matched = _match_text_artist(sax, sld.get("text", ""), apx, rr, used_text_ids) if (vis_sl and sax is not None) else None
                    bbox_norm = (
                        _px_box_to_norm(matched[1].x0 - 2, matched[1].y0 - 2, matched[1].x1 + 2, matched[1].y1 + 2, fw, fh)
                        if matched is not None else [anchor_norm[0] - 0.04, anchor_norm[1] - 0.02, anchor_norm[0] + 0.04, anchor_norm[1] + 0.02]
                    )
                    items_out.append({
                        "id": f"p{pi}:sub{sub_i}:sample_label",
                        "kind": "sample_label",
                        "panel_index": pi,
                        "panel_id": pid,
                        "subpanel_index": sub_i,
                        "plot_index": None,
                        "seg_index": sub_i,
                        "draggable": True,
                        "visible": vis_sl,
                        "label": str(sld.get("text", "")),
                        "bbox_norm": bbox_norm,
                        "anchor_norm": anchor_norm,
                        "props": {
                            "text": str(sld.get("text", "")),
                            "xy": [float(xy[0]), float(xy[1])],
                            "ha": ha,
                            "va": va,
                            "size": float(sld.get("size", th["size"]["legend"])),
                            "color": sld.get("color", "#000000"),
                        },
                    })
            if panel.get("plots"):
                _collect_plots(panel["plots"], None)
        else:
            _collect_plots(panel.get("plots", []), None)

        # Panel letter handle
        if panel.get("letter"):
            lt = panel["letter"] if isinstance(panel["letter"], dict) else {"text": str(panel["letter"])}
            vis_lt = lt.get("visible", True) is not False
            lx = float(lt.get("x", -0.20))
            ly = float(lt.get("y", 1.03))
            is_broken_or_sub = pinfo["kind"] in ("subpanels", "segments", "breaks", "montage") and (
                pinfo["kind"] != "segments" or len(pinfo["main_axes"]) > 1
            )
            if is_broken_or_sub:
                fx = rect[0] + lx * rect[2]
                fy = rect[1] + ly * rect[3]
                apx = tuple(fig.transFigure.transform((fx, fy)))
                matched = _match_text_artist(fig, lt.get("text", ""), apx, rr, used_text_ids) if vis_lt else None
            else:
                ax0 = pinfo["main_axes"][0] if pinfo["main_axes"] else None
                apx = tuple(ax0.transAxes.transform((lx, ly))) if ax0 is not None else (0.05 * fw, 0.95 * fh)
                matched = _match_text_artist(ax0, lt.get("text", ""), apx, rr, used_text_ids) if (vis_lt and ax0 is not None) else None
            anchor_norm = _px_pt_to_norm(apx[0], apx[1], fw, fh)
            bbox_norm = (
                _px_box_to_norm(matched[1].x0 - 2, matched[1].y0 - 2, matched[1].x1 + 2, matched[1].y1 + 2, fw, fh)
                if matched is not None else [anchor_norm[0] - 0.015, anchor_norm[1] - 0.02, anchor_norm[0] + 0.015, anchor_norm[1] + 0.02]
            )
            items_out.append({
                "id": f"p{pi}:letter",
                "kind": "letter",
                "panel_index": pi,
                "panel_id": pid,
                "subpanel_index": None,
                "plot_index": None,
                "seg_index": 0,
                "draggable": True,
                "visible": vis_lt,
                "label": f"Panel Letter {lt.get('text', '')}",
                "bbox_norm": bbox_norm,
                "anchor_norm": anchor_norm,
                "props": {
                    "text": str(lt.get("text", "")),
                    "x": lx,
                    "y": ly,
                    "size": float(lt.get("size", th["size"]["panel"])),
                },
            })

        # Panel legend handle
        if panel.get("legend"):
            lg = panel["legend"]
            vis_lg = lg.get("visible", True) is not False
            lseg, lax = _pick_legend_ax(panel, pinfo)
            leg = lax.get_legend() if (vis_lg and lax is not None) else None
            if leg is not None:
                lbb = leg.get_window_extent(renderer=rr)
                bbox_norm = _px_box_to_norm(lbb.x0 - 2, lbb.y0 - 2, lbb.x1 + 2, lbb.y1 + 2, fw, fh)
            else:
                bbox_norm = [prect_norm[2] - 0.22, prect_norm[1] + 0.02, prect_norm[2] - 0.02, prect_norm[1] + 0.16]
            items_out.append({
                "id": f"p{pi}:legend",
                "kind": "legend",
                "panel_index": pi,
                "panel_id": pid,
                "subpanel_index": None,
                "plot_index": None,
                "seg_index": lseg,
                "draggable": True,
                "visible": vis_lg,
                "label": f"Legend ({pid})",
                "bbox_norm": bbox_norm,
                "anchor_norm": [round(0.5 * (bbox_norm[0] + bbox_norm[2]), 5), round(0.5 * (bbox_norm[1] + bbox_norm[3]), 5)],
                "props": {
                    "loc": lg.get("loc", "upper right"),
                    "bbox": lg.get("bbox"),
                    "ncol": int(lg.get("ncol", 1)),
                    "fontsize": float(lg.get("fontsize", th["size"]["legend"])),
                    "frameon": bool(lg.get("frameon", th["legend"]["frameon"])),
                    "seg": lg.get("seg"),
                },
            })

    return {"panels": panels_out, "items": items_out}


# ---------------------------------------------------------------- real-time QA & preflight
def _run_figure_qa(spec: dict, fig: plt.Figure, rr, data_map: dict) -> tuple[dict, float]:
    """Run exact scifig.qa checks on an already-built Figure + return violation_boxes & min_font_pt."""
    fw_px, fh_px = fig.canvas.get_width_height()

    hidden_tick_ids = set()
    for ax in fig.axes:
        for axis_obj, lim in ((ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())):
            lo, hi = min(lim), max(lim)
            vis = axis_obj.get_visible()
            for tk in axis_obj.get_major_ticks() + axis_obj.get_minor_ticks():
                loc = tk.get_loc()
                if not vis or loc < lo - 1e-9 or loc > hi + 1e-9:
                    hidden_tick_ids.add(id(tk.label1))
                    hidden_tick_ids.add(id(tk.label2))

    text_boxes = []
    seen_ids = set()
    font_sizes = []
    for txt in fig.findobj(match=lambda obj: isinstance(obj, MplText)):
        if id(txt) in seen_ids or id(txt) in hidden_tick_ids or not txt.get_visible():
            continue
        seen_ids.add(id(txt))
        s = str(txt.get_text()).strip()
        if not s:
            continue
        try:
            bb = txt.get_window_extent(renderer=rr)
            obb = qa_mod._text_obb(txt, rr)
            fs = float(txt.get_fontsize())
            if fs > 0:
                font_sizes.append(fs)
        except Exception:
            continue
        if obb is None:
            continue
        text_boxes.append((s, (float(bb.x0), float(bb.y0), float(bb.x1), float(bb.y1)), obb))

    violation_boxes: list[dict] = []
    overlaps = []
    for i in range(len(text_boxes)):
        for j in range(i + 1, len(text_boxes)):
            if qa_mod._obb_overlap(text_boxes[i][2], text_boxes[j][2], tol_px=2.0):
                s1, b1, _ = text_boxes[i]
                s2, b2, _ = text_boxes[j]
                overlaps.append([s1, s2])
                ux0 = min(b1[0], b2[0]) - 3.0
                uy0 = min(b1[1], b2[1]) - 3.0
                ux1 = max(b1[2], b2[2]) + 3.0
                uy1 = max(b1[3], b2[3]) + 3.0
                violation_boxes.append({
                    "kind": "text_overlap",
                    "severity": "error",
                    "message": f"文字重叠: '{s1}' ↔ '{s2}'",
                    "texts": [s1, s2],
                    "bbox_norm": _px_box_to_norm(ux0, uy0, ux1, uy1, fw_px, fh_px),
                })

    clipped = []
    for s, (x0, y0, x1, y1), _obb in text_boxes:
        if x0 < -2.0 or y0 < -2.0 or x1 > fw_px + 2.0 or y1 > fh_px + 2.0:
            clipped.append({"text": s, "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})
            cx0 = max(2.0, min(fw_px - 20.0, x0))
            cy0 = max(2.0, min(fh_px - 16.0, y0))
            cx1 = max(cx0 + 18.0, min(fw_px - 2.0, x1))
            cy1 = max(cy0 + 14.0, min(fh_px - 2.0, y1))
            violation_boxes.append({
                "kind": "clipped",
                "severity": "error",
                "message": f"文字裁切越界: '{s}'",
                "texts": [s],
                "bbox_norm": _px_box_to_norm(cx0, cy0, cx1, cy1, fw_px, fh_px),
            })

    legend_data_hits = []
    for ax in fig.axes:
        leg = ax.get_legend()
        if not leg or not leg.get_visible():
            continue
        try:
            lbb = leg.get_window_extent(renderer=rr)
        except Exception:
            continue
        lbox = (float(lbb.x0), float(lbb.y0), float(lbb.x1), float(lbb.y1))
        ax_hits = []
        for ln in ax.get_lines():
            if ln.get_transform() != ax.transData:
                continue
            xd = np.asarray(ln.get_xdata(orig=False), dtype=float)
            yd = np.asarray(ln.get_ydata(orig=False), dtype=float)
            ok = np.isfinite(xd) & np.isfinite(yd)
            if not np.any(ok):
                continue
            pts = ax.transData.transform(np.column_stack([xd[ok], yd[ok]]))
            inside = (pts[:, 0] >= lbox[0]) & (pts[:, 0] <= lbox[2]) & (pts[:, 1] >= lbox[1]) & (pts[:, 1] <= lbox[3])
            cnt = int(np.sum(inside))
            if cnt > 0:
                hit = {
                    "label": str(ln.get_label()),
                    "points_inside": cnt,
                    "fraction": round(cnt / max(1, len(pts)), 4),
                }
                legend_data_hits.append(hit)
                ax_hits.append(hit)
        if ax_hits:
            violation_boxes.append({
                "kind": "legend_data",
                "severity": "warning",
                "message": f"图例遮挡数据曲线 ({len(ax_hits)} 条, {sum(h['points_inside'] for h in ax_hits)} 点)",
                "texts": [h["label"] for h in ax_hits],
                "bbox_norm": _px_box_to_norm(lbox[0] - 2, lbox[1] - 2, lbox[2] + 2, lbox[3] + 2, fw_px, fh_px),
            })

    # Data NaN & Deconvolution sum conservation checks
    ref_cols = qa_mod.referenced_columns(spec)
    nan_issues = []
    for dkey, df in data_map.items():
        cols_to_check = ref_cols.get(dkey)
        if cols_to_check is None:
            continue
        for cref in cols_to_check:
            cname = qa_mod.resolve_col_name(df, cref)
            if cname is None:
                nan_issues.append({"data": dkey, "column": str(cref), "issue": "missing_column"})
            elif df[cname].isna().all():
                nan_issues.append({"data": dkey, "column": str(cname), "issue": "all_nan"})

    deconv_checks = []
    for panel in spec.get("panels", []):
        sublist = panel.get("subpanels") or [panel]
        for spanel in sublist:
            plots = spanel.get("plots", [])
            fills_by_group: dict[tuple, list] = {}
            fits_by_group: dict[tuple, list] = {}
            for pl in plots:
                if "data" not in pl or pl.get("visible", True) is False:
                    continue
                grp = (pl["data"], round(float(pl.get("offset", 0.0)), 6), round(float(pl.get("scale", 1.0)), 6))
                if pl.get("type") == "fill":
                    fills_by_group.setdefault(grp, []).append(pl["y"])
                elif pl.get("type") == "line" and str(pl.get("y", "")).lower() in ("fit", "sum", "3"):
                    fits_by_group.setdefault(grp, []).append(pl["y"])
            for grp, fcols in fills_by_group.items():
                if grp in fits_by_group and len(fcols) >= 2 and grp[0] in data_map:
                    df = data_map[grp[0]]
                    try:
                        comp_sum = np.sum([engine._col(df, c) for c in fcols], axis=0)
                        fit_vals = engine._col(df, fits_by_group[grp][0])
                        m = np.isfinite(comp_sum) & np.isfinite(fit_vals)
                        if np.any(m):
                            max_abs = float(np.max(np.abs(comp_sum[m] - fit_vals[m])))
                            denom = max(float(np.max(np.abs(fit_vals[m]))), 1e-12)
                            deconv_checks.append({
                                "data": grp[0],
                                "n_components": len(fcols),
                                "max_abs_diff": round(max_abs, 6),
                                "rel_err": round(max_abs / denom, 6),
                            })
                    except Exception:
                        pass

    errors = []
    warnings = []
    if clipped:
        errors.append(f"{len(clipped)} 个文字元素越界裁切")
    if nan_issues:
        errors.append(f"{len(nan_issues)} 个数据列全为 NaN 或缺失")
    if overlaps:
        warnings.append(f"{len(overlaps)} 组文字碰撞重叠")
    if legend_data_hits:
        warnings.append(f"{len(legend_data_hits)} 处图例遮挡数据曲线")

    qa_report = {
        "pass": len(errors) == 0 and len(overlaps) == 0,
        "text_count": len(text_boxes),
        "text_overlap_count": len(overlaps),
        "text_overlaps": overlaps[:20],
        "out_of_bounds_count": len(clipped),
        "clipped_texts": clipped[:20],
        "legend_data_overlap_count": len(legend_data_hits),
        "legend_data_overlaps": legend_data_hits,
        "nan_issues": nan_issues,
        "deconv_checks": deconv_checks,
        "errors": errors,
        "warnings": warnings,
        "violation_boxes": violation_boxes[:30],
    }
    min_font = round(min(font_sizes), 2) if font_sizes else 0.0
    return qa_report, min_font


def _build_preflight(spec: dict, qa_rep: dict, min_font_pt: float, datasets: list[dict]) -> dict:
    fs = spec.get("figure", {})
    w_in = round(float(fs.get("width_in", 7.09)), 3)
    h_in = round(float(fs.get("height_in", 2.93)), 3)
    dpi = int(fs.get("dpi", 600))

    if w_in <= 3.6:
        col_cls, col_label = "single", f"{w_in:.2f} in (单栏 ≤3.6 in)"
    elif w_in <= 5.5:
        col_cls, col_label = "1.5-column", f"{w_in:.2f} in (1.5栏 ≤5.5 in)"
    elif w_in <= 7.2:
        col_cls, col_label = "double", f"{w_in:.2f} in (双栏 ≤7.2 in)"
    else:
        col_cls, col_label = "wide", f"{w_in:.2f} in (宽幅 >7.2 in)"

    dpi_ok = dpi >= 600
    min_font_ok = min_font_pt >= 6.0 if min_font_pt > 0 else True
    deconv_checks = qa_rep.get("deconv_checks", [])
    deconv_ok = all(c["rel_err"] < 0.02 for c in deconv_checks) if deconv_checks else True
    qa_pass = bool(qa_rep.get("pass", False))
    prov_ok = all(d["exists"] and bool(d["sha256_16"]) for d in datasets) if datasets else True

    checks = [
        {"id": "column_width", "label": "栏宽规范", "status": "ok" if w_in <= 7.2 else "warn", "value": col_label},
        {"id": "dpi", "label": "分辨率 DPI", "status": "ok" if dpi_ok else "warn", "value": f"{dpi} dpi" + ("" if dpi_ok else " (导出自动 600 dpi)")},
        {"id": "min_font", "label": "最小字号", "status": "ok" if min_font_ok else "fail", "value": f"{min_font_pt:.1f} pt (≥6.0 pt)"},
        {"id": "qa_gate", "label": "视觉碰撞 QA", "status": "ok" if qa_pass else "fail", "value": "PASS (0 碰撞/0 裁切)" if qa_pass else f"{qa_rep['text_overlap_count']} 碰撞 / {qa_rep['out_of_bounds_count']} 裁切"},
        {"id": "deconv", "label": "分峰面积守恒", "status": "ok" if deconv_ok else "fail", "value": f"PASS ({len(deconv_checks)} 组)" if deconv_checks else "N/A"},
        {"id": "provenance", "label": "SHA256 溯源", "status": "ok" if prov_ok else "fail", "value": f"{sum(1 for d in datasets if d['exists'])}/{len(datasets)} 数据已校验"},
    ]

    return {
        "width_in": w_in,
        "height_in": h_in,
        "column_class": col_cls,
        "dpi": dpi,
        "dpi_ok": dpi_ok,
        "min_font_pt": min_font_pt,
        "min_font_ok": min_font_ok,
        "deconv_ok": deconv_ok,
        "qa_pass": qa_pass,
        "provenance_verified": prov_ok,
        "checks": checks,
    }


def _extract_datasets_info(spec_with_base: dict, data_map: dict, prov: list[dict], ops_applied: list[dict]) -> list[dict]:
    base = Path(spec_with_base.get("_base", "."))
    ops_by_key: dict[str, list[dict]] = {}
    for op in spec_with_base.get("ops") or []:
        dk = op.get("data")
        if dk:
            ops_by_key.setdefault(dk, []).append(op)
        else:
            for k in data_map:
                ops_by_key.setdefault(k, []).append(op)

    prov_map = {p["data"]: p for p in prov}
    out = []
    for key, df in data_map.items():
        cfg = (spec_with_base.get("data") or {}).get(key, {})
        raw_src = cfg if isinstance(cfg, str) else cfg.get("source", "")
        p_src = Path(raw_src)
        if not p_src.is_absolute():
            p_src = (base / p_src).resolve()
        pentry = prov_map.get(key, {})
        cols = [str(c) for c in df.columns[:24]]
        head_df = df.iloc[:30, :24]
        preview_rows = []
        for _, row in head_df.iterrows():
            preview_rows.append({str(c): _json_safe(row[c]) for c in head_df.columns})
        out.append({
            "key": key,
            "source": str(p_src),
            "raw_source": str(raw_src),
            "filename": p_src.name,
            "exists": p_src.exists(),
            "sha256_16": pentry.get("sha256_16") or (_sha16(p_src) if p_src.is_file() else ""),
            "rows": int(df.shape[0]),
            "cols": cols,
            "preview_rows": preview_rows,
            "ops": ops_by_key.get(key, []),
        })
    return out


# ---------------------------------------------------------------- core render pipeline
def _effective_theme_and_palette(spec: dict) -> tuple[dict, dict]:
    merged = engine.merge_preset(spec)
    th = theme_mod.load_theme(merged.get("theme"))
    if merged.get("style", {}).get("theme"):
        th = theme_mod.load_theme(merged["style"]["theme"])
    st = merged.get("style", {})
    if st.get("scale"):
        th = theme_mod.scale_theme(th, float(st["scale"]))
    for sk in ("font", "size", "line", "tick", "spines", "legend"):
        if isinstance(st.get(sk), dict):
            th[sk] = theme_mod.deep_merge(th[sk], st[sk])
    pal = theme_mod.load_palette(merged.get("palette") or th.get("palette"))
    return th, pal


def render_state(spec: dict, spec_id: str | None = None, preview_dpi: int = 190) -> dict:
    """Render in-memory spec via real scifig.engine.build() and return full Workbench StateBundle."""
    t0 = time.perf_counter()
    spec_with_base = _ensure_spec_base(spec, spec_id)
    render_spec = _filter_visible_spec(spec_with_base)
    merged_full = engine.merge_preset(spec_with_base)
    th, pal = _effective_theme_and_palette(spec_with_base)

    with RENDER_LOCK:
        data_map, prov, ops_applied = engine.resolve_data(render_spec)
        fig = engine.build(render_spec)
        try:
            fig.canvas.draw()
            rr = fig.canvas.get_renderer()
            panel_maps = _map_panel_axes(merged_full, fig, data_map)
            handles = _extract_handles(merged_full, fig, rr, panel_maps, pal, th)
            qa_rep, min_font_pt = _run_figure_qa(render_spec, fig, rr, data_map)

            # Cap preview width around 1600px so rendering stays snappy even for 8.5in specs
            w_in, h_in = float(fig.get_figwidth()), float(fig.get_figheight())
            eff_dpi = min(preview_dpi, max(120, int(round(1450.0 / max(w_in, 1.0)))))
            buf = io.BytesIO()
            fig.savefig(
                buf, format="png", dpi=eff_dpi, bbox_inches=None, pad_inches=0,
                transparent=False, facecolor="white",
            )
            png_bytes = buf.getvalue()
        finally:
            plt.close(fig)

    img_b64 = base64.b64encode(png_bytes).decode("ascii")
    datasets = _extract_datasets_info(spec_with_base, data_map, prov, ops_applied)
    preflight = _build_preflight(merged_full, qa_rep, min_font_pt, datasets)

    ent = resolve_spec_entry(spec_id) if spec_id else None
    elapsed_ms = int(round((time.perf_counter() - t0) * 1000))
    return {
        "ok": True,
        "spec_id": ent["id"] if ent else (spec_id or "custom"),
        "spec_path": ent["path"] if ent else None,
        "spec": _clean_user_spec(spec),
        "image_data_url": f"data:image/png;base64,{img_b64}",
        "image_width_px": int(round(w_in * eff_dpi)),
        "image_height_px": int(round(h_in * eff_dpi)),
        "figure_size_in": [round(w_in, 3), round(h_in, 3)],
        "dpi_preview": eff_dpi,
        "render_ms": elapsed_ms,
        "handles": handles,
        "qa": qa_rep,
        "preflight": preflight,
        "datasets": datasets,
        "ops": spec.get("ops") or [],
    }


def load_spec_state(spec_id: str) -> dict:
    ent = resolve_spec_entry(spec_id)
    if not ent:
        raise FileNotFoundError(f"Spec not found: {spec_id}")
    raw = engine.load_spec(ent["path"])
    return render_state(raw, spec_id=ent["id"])


# ---------------------------------------------------------------- exact interactive drag
def _parse_handle_id(handle_id: str) -> dict:
    # Formats: p0:plot:4, p0:sub1:plot:2, p0:legend, p0:letter, p0:sub0:sample_label
    m = re.match(r"^p(\d+):sub(\d+):plot:(\d+)$", handle_id)
    if m:
        return {"kind": "plot", "pi": int(m.group(1)), "sub_i": int(m.group(2)), "plot_i": int(m.group(3))}
    m = re.match(r"^p(\d+):plot:(\d+)$", handle_id)
    if m:
        return {"kind": "plot", "pi": int(m.group(1)), "sub_i": None, "plot_i": int(m.group(2))}
    m = re.match(r"^p(\d+):sub(\d+):sample_label$", handle_id)
    if m:
        return {"kind": "sample_label", "pi": int(m.group(1)), "sub_i": int(m.group(2))}
    m = re.match(r"^p(\d+):legend$", handle_id)
    if m:
        return {"kind": "legend", "pi": int(m.group(1))}
    m = re.match(r"^p(\d+):letter$", handle_id)
    if m:
        return {"kind": "letter", "pi": int(m.group(1))}
    raise ValueError(f"Invalid handle_id: {handle_id}")


def apply_drag(
    spec: dict,
    handle_id: str,
    dx_norm: float = 0.0,
    dy_norm: float = 0.0,
    target_norm: list[float] | None = None,
    spec_id: str | None = None,
) -> tuple[dict, str]:
    """Translate normalized canvas drag delta/target accurately back into spec JSON coordinates."""
    ref = _parse_handle_id(handle_id)
    updated = copy.deepcopy(spec)
    spec_with_base = _ensure_spec_base(spec, spec_id)
    render_spec = _filter_visible_spec(spec_with_base)
    merged_full = engine.merge_preset(spec_with_base)

    with RENDER_LOCK:
        data_map, _, _ = engine.resolve_data(render_spec)
        fig = engine.build(render_spec)
        try:
            fig.canvas.draw()
            rr = fig.canvas.get_renderer()
            fw, fh = fig.canvas.get_width_height()
            panel_maps = _map_panel_axes(merged_full, fig, data_map)
            pi = ref["pi"]
            panel = updated["panels"][pi]
            pinfo = panel_maps[pi]
            dpx = float(dx_norm) * fw
            dpy = -float(dy_norm) * fh  # HTML y-down -> Matplotlib y-up

            summary = ""
            if ref["kind"] == "plot":
                sub_i = ref["sub_i"]
                plot_i = ref["plot_i"]
                container = panel["subpanels"][sub_i] if sub_i is not None else panel
                pl = container["plots"][plot_i]
                ax = pinfo["subpanel_ax"][sub_i] if sub_i is not None else _pick_segment_ax(panel, pinfo, pl)[1]

                if pl.get("type") == "text":
                    coords = pl.get("coords", "data")
                    trans = ax.transAxes if coords == "axes" else ax.transData
                    if target_norm is not None:
                        npx, npy = _norm_pt_to_px(target_norm[0], target_norm[1], fw, fh)
                    else:
                        cur_px = trans.transform((float(pl["xy"][0]), float(pl["xy"][1])))
                        npx, npy = float(cur_px[0]) + dpx, float(cur_px[1]) + dpy

                    # Broken-axis segment transfer if dragged across break gap
                    if coords == "data" and pinfo["kind"] == "segments":
                        nfig_x = npx / max(fw, 1.0)
                        for si_cand, _, ax_cand in pinfo["seg_axes"]:
                            pos = ax_cand.get_position()
                            if pos.x0 - 0.01 <= nfig_x <= pos.x1 + 0.01:
                                ax = ax_cand
                                pl["seg"] = si_cand
                                break
                        trans = ax.transData

                    nx, ny = trans.inverted().transform((npx, npy))
                    pl["xy"] = [round(float(nx), 4), round(float(ny), 5)]
                    summary = f"移动标注 '{pl.get('text', '')}' 至 [{pl['xy'][0]:g}, {pl['xy'][1]:g}]"

                elif pl.get("type") == "vline":
                    if target_norm is not None:
                        npx, _ = _norm_pt_to_px(target_norm[0], target_norm[1], fw, fh)
                    else:
                        cur_px = ax.get_xaxis_transform().transform((float(pl["x"]), 0.5))
                        npx = float(cur_px[0]) + dpx
                    if pinfo["kind"] == "segments":
                        nfig_x = npx / max(fw, 1.0)
                        for si_cand, _, ax_cand in pinfo["seg_axes"]:
                            pos = ax_cand.get_position()
                            if pos.x0 - 0.01 <= nfig_x <= pos.x1 + 0.01:
                                ax = ax_cand
                                pl["seg"] = si_cand
                                break
                    nx, _ = ax.transData.inverted().transform((npx, ax.get_position().y0 * fh))
                    pl["x"] = round(float(nx), 3)
                    summary = f"移动竖向峰位线至 x={pl['x']:g}"

                elif pl.get("type") == "hline":
                    if target_norm is not None:
                        _, npy = _norm_pt_to_px(target_norm[0], target_norm[1], fw, fh)
                    else:
                        cur_px = ax.get_yaxis_transform().transform((0.5, float(pl["y"])))
                        npy = float(cur_px[1]) + dpy
                    _, ny = ax.transData.inverted().transform((ax.get_position().x0 * fw, npy))
                    pl["y"] = round(float(ny), 5)
                    summary = f"移动水平参考线至 y={pl['y']:g}"

            elif ref["kind"] == "legend":
                lg = panel.setdefault("legend", {"loc": "upper right"})
                _, lax = _pick_legend_ax(panel, pinfo)
                leg = lax.get_legend() if lax is not None else None
                if leg is not None and lax is not None:
                    lbb = leg.get_window_extent(renderer=rr)
                    if target_norm is not None:
                        tx, ty = _norm_pt_to_px(target_norm[0], target_norm[1], fw, fh)
                        new_x0 = tx - 0.5 * lbb.width
                        new_y1 = ty + 0.5 * lbb.height
                    else:
                        new_x0 = float(lbb.x0) + dpx
                        new_y1 = float(lbb.y1) + dpy
                    bx, by = lax.transAxes.inverted().transform((new_x0, new_y1))
                    lg["loc"] = "upper left"
                    lg["bbox"] = [round(float(bx), 4), round(float(by), 4)]
                    lg["borderaxespad"] = 0.0
                    summary = f"移动图例至 axes=[{lg['bbox'][0]}, {lg['bbox'][1]}]"

            elif ref["kind"] == "letter":
                lt = panel.get("letter")
                if not isinstance(lt, dict):
                    lt = {"text": str(lt or pinfo["panel_id"])}
                    panel["letter"] = lt
                rect = pinfo["rect_fig"]
                is_broken_or_sub = pinfo["kind"] in ("subpanels", "segments", "breaks", "montage") and (
                    pinfo["kind"] != "segments" or len(pinfo["main_axes"]) > 1
                )
                if is_broken_or_sub:
                    if target_norm is not None:
                        lt["x"] = round((target_norm[0] - rect[0]) / max(rect[2], 1e-6), 4)
                        lt["y"] = round(((1.0 - target_norm[1]) - rect[1]) / max(rect[3], 1e-6), 4)
                    else:
                        lt["x"] = round(float(lt.get("x", -0.20)) + float(dx_norm) / max(rect[2], 1e-6), 4)
                        lt["y"] = round(float(lt.get("y", 1.03)) - float(dy_norm) / max(rect[3], 1e-6), 4)
                else:
                    ax0 = pinfo["main_axes"][0]
                    pos = ax0.get_position()
                    if target_norm is not None:
                        npx, npy = _norm_pt_to_px(target_norm[0], target_norm[1], fw, fh)
                        nx, ny = ax0.transAxes.inverted().transform((npx, npy))
                        lt["x"], lt["y"] = round(float(nx), 4), round(float(ny), 4)
                    else:
                        lt["x"] = round(float(lt.get("x", -0.20)) + float(dx_norm) / max(pos.width, 1e-6), 4)
                        lt["y"] = round(float(lt.get("y", 1.03)) - float(dy_norm) / max(pos.height, 1e-6), 4)
                summary = f"移动子图编号 '{lt.get('text', '')}' 至 [{lt['x']}, {lt['y']}]"

            elif ref["kind"] == "sample_label":
                sub_i = ref["sub_i"]
                sub = panel["subpanels"][sub_i]
                sl = sub.get("sample_label")
                if not isinstance(sl, dict):
                    sl = {"text": str(sl or "")}
                    sub["sample_label"] = sl
                sax = pinfo["subpanel_ax"][sub_i]
                if "xy" not in sl:
                    loc = sl.get("loc", "upper right")
                    sl["ha"] = "right" if "right" in loc else "left"
                    sl["va"] = "top" if "upper" in loc else ("bottom" if "lower" in loc else "center")
                    sl["xy"] = [0.96 if sl["ha"] == "right" else 0.04, 0.88 if sl["va"] == "top" else 0.10]
                if target_norm is not None:
                    npx, npy = _norm_pt_to_px(target_norm[0], target_norm[1], fw, fh)
                else:
                    cpx = sax.transAxes.transform((float(sl["xy"][0]), float(sl["xy"][1])))
                    npx, npy = float(cpx[0]) + dpx, float(cpx[1]) + dpy
                nx, ny = sax.transAxes.inverted().transform((npx, npy))
                sl["xy"] = [round(float(nx), 4), round(float(ny), 4)]
                summary = f"移动样品标签 '{sl.get('text', '')}' 至 [{sl['xy'][0]}, {sl['xy'][1]}]"
        finally:
            plt.close(fig)

    return updated, summary


# ---------------------------------------------------------------- one-click Auto-Fix QA
def _find_text_handle_by_string(handles_items: list[dict], text_str: str) -> list[dict]:
    return [h for h in handles_items if h["kind"] in ("text", "sample_label", "letter") and h["label"] == text_str and h["visible"]]


def auto_fix_qa(spec: dict, spec_id: str | None = None, max_iters: int = 8) -> tuple[dict, list[str]]:
    """Deterministically resolve text collisions, clipping, and legend-data overlaps until QA passes."""
    cur = copy.deepcopy(spec)
    actions: list[str] = []

    for it in range(max_iters):
        st = render_state(cur, spec_id=spec_id, preview_dpi=130)
        qa_rep = st["qa"]
        if qa_rep["pass"] and qa_rep["legend_data_overlap_count"] == 0:
            break

        handles_items = st["handles"]["items"]
        panels_geom = st["handles"]["panels"]
        changed = False

        # 1. Fix clipped texts (bring out-of-bounds text plots safely inside axis/canvas, else expand margins)
        if qa_rep["out_of_bounds_count"] > 0:
            clipped_names = {c["text"] for c in qa_rep["clipped_texts"]}
            moved_any_plot = False
            for cname in clipped_names:
                cands = _find_text_handle_by_string(handles_items, cname)
                for h in cands:
                    if h["kind"] == "text":
                        pi = h["panel_index"]
                        sub_i = h["subpanel_index"]
                        plot_i = h["plot_index"]
                        seg_i = h["seg_index"]
                        pgeom = panels_geom[pi]
                        sgeom = next((s for s in pgeom["segments"] if s["seg_index"] == seg_i), pgeom["segments"][0])
                        r = sgeom["rect_norm"]
                        bb = h["bbox_norm"]
                        bw = max(bb[2] - bb[0], 0.03)
                        bh = max(bb[3] - bb[1], 0.025)
                        cx = 0.5 * (bb[0] + bb[2])
                        cy = 0.5 * (bb[1] + bb[3])
                        tx = min(max(cx, max(0.03 + 0.5 * bw, r[0] + 0.02 + 0.5 * bw)), min(0.97 - 0.5 * bw, r[2] - 0.02 - 0.5 * bw))
                        ty = min(max(cy, max(0.04 + 0.5 * bh, r[1] + 0.03 + 0.5 * bh)), min(0.95 - 0.5 * bh, r[3] - 0.03 - 0.5 * bh))
                        if abs(tx - cx) > 1e-4 or abs(ty - cy) > 1e-4:
                            cur, msg = apply_drag(cur, h["id"], dx_norm=tx - cx, dy_norm=ty - cy, spec_id=spec_id)
                            actions.append(f"将越界标注 '{cname}' 拉回画布安全区")
                            moved_any_plot = True
                            changed = True
            if not moved_any_plot:
                # Expand layout margins or ylim headroom
                m = cur.setdefault("layout", {}).setdefault("margins", {"l": 0.12, "r": 0.04, "t": 0.06, "b": 0.16})
                m["l"] = round(min(0.24, m.get("l", 0.12) + 0.025), 3)
                m["r"] = round(min(0.14, m.get("r", 0.04) + 0.02), 3)
                m["t"] = round(min(0.22, m.get("t", 0.06) + 0.025), 3)
                m["b"] = round(min(0.26, m.get("b", 0.16) + 0.025), 3)
                for p in cur.get("panels", []):
                    if "rect" in p:
                        L, B, W, H = p["rect"]
                        p["rect"] = [round(L + 0.01, 3), round(B + 0.015, 3), round(W - 0.02, 3), round(H - 0.025, 3)]
                actions.append("扩展画布页边距消除文字裁切")
                changed = True
            if changed:
                continue

        # 2. Fix text-text overlaps using exact bounding box separation
        if qa_rep["text_overlap_count"] > 0:
            moved_ids = set()
            for pair in qa_rep["text_overlaps"]:
                s1, s2 = pair[0], pair[1]
                h1s = _find_text_handle_by_string(handles_items, s1)
                h2s = _find_text_handle_by_string(handles_items, s2)
                # Prefer moving a `text` plot handle over axis ticks/legend text
                target_h = None
                other_h = None
                if h1s and h2s:
                    # Find closest pair
                    best_p = min(
                        ((a, b) for a in h1s for b in h2s if a["id"] != b["id"]),
                        key=lambda ab: (ab[0]["anchor_norm"][0] - ab[1]["anchor_norm"][0]) ** 2
                        + (ab[0]["anchor_norm"][1] - ab[1]["anchor_norm"][1]) ** 2,
                        default=None,
                    )
                    if best_p:
                        a, b = best_p
                        # Prefer moving the one with higher plot_index (or non-letter)
                        if a["kind"] == "text" and b["kind"] == "text":
                            target_h, other_h = (b, a) if (b["plot_index"] or 0) >= (a["plot_index"] or 0) else (a, b)
                        elif a["kind"] == "text":
                            target_h, other_h = a, b
                        elif b["kind"] == "text":
                            target_h, other_h = b, a
                elif h1s:
                    target_h = h1s[0]
                elif h2s:
                    target_h = h2s[0]

                if target_h is None or target_h["id"] in moved_ids:
                    continue

                pi = target_h["panel_index"]
                pgeom = panels_geom[pi]
                sgeom = next((s for s in pgeom["segments"] if s["seg_index"] == target_h["seg_index"]), pgeom["segments"][0])
                r = sgeom["rect_norm"]
                tb = target_h["bbox_norm"]
                th_n = max(tb[3] - tb[1], 0.032)
                tw_n = max(tb[2] - tb[0], 0.04)

                # Check if target_h has a matching vline in the same panel -> snap back near its own vline!
                snapped = False
                panel = cur["panels"][pi]
                container = panel["subpanels"][target_h["subpanel_index"]] if target_h["subpanel_index"] is not None else panel
                if target_h["kind"] == "text" and it == 0:
                    m_num = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", target_h["label"])
                    if m_num:
                        num_v = float(m_num.group(1))
                        # Find a vline with matching x
                        for pl_v in container.get("plots", []):
                            if pl_v.get("type") == "vline" and abs(float(pl_v["x"]) - num_v) <= 2.5:
                                pl_t = container["plots"][target_h["plot_index"]]
                                if pl_t.get("coords", "data") == "data" and abs(float(pl_t["xy"][0]) - float(pl_v["x"])) > 5.0:
                                    ylim = sgeom["ylim"]
                                    yspan = abs(ylim[1] - ylim[0])
                                    ymax_v = float(pl_v.get("ymax", 0.7))
                                    ly_new = min(ylim) + min(0.90, ymax_v + 0.03) * yspan
                                    pl_t["xy"] = [round(float(pl_v["x"]), 2), round(ly_new, 5)]
                                    actions.append(f"将碰撞标注 '{target_h['label']}' 自动对齐回对应峰位线 x={pl_v['x']:g}")
                                    moved_ids.add(target_h["id"])
                                    snapped = True
                                    changed = True
                                    break
                if snapped:
                    continue

                # Compute non-overlapping displacement
                if other_h is not None:
                    ob = other_h["bbox_norm"]
                    # Try moving UP above ob, DOWN below ob, RIGHT of ob, LEFT of ob
                    candidates = [
                        (0.0, (ob[1] - 0.012) - tb[3]),   # place above ob
                        (0.0, (ob[3] + 0.012) - tb[1]),   # place below ob
                        ((ob[2] + 0.014) - tb[0], 0.0),   # place right of ob
                        ((ob[0] - 0.014) - tb[2], 0.0),   # place left of ob
                    ]
                    best_cand = None
                    best_score = 1e18
                    for dx, dy in candidates:
                        nb = [tb[0] + dx, tb[1] + dy, tb[2] + dx, tb[3] + dy]
                        if nb[0] < r[0] + 0.005 or nb[2] > r[2] - 0.005 or nb[1] < r[1] + 0.005 or nb[3] > r[3] - 0.005:
                            continue
                        # Count overlaps with all other handles
                        pen = 0.0
                        for oh in handles_items:
                            if oh["id"] == target_h["id"] or not oh["visible"] or oh["kind"] not in ("text", "legend", "sample_label", "letter"):
                                continue
                            hb = oh["bbox_norm"]
                            ox = max(0.0, min(nb[2], hb[2]) - max(nb[0], hb[0]))
                            oy = max(0.0, min(nb[3], hb[3]) - max(nb[1], hb[1]))
                            if ox > 0 and oy > 0:
                                pen += 100.0 + ox * oy * 1000.0
                        score = pen + abs(dx) + abs(dy)
                        if score < best_score:
                            best_score = score
                            best_cand = (dx, dy)
                    dx, dy = best_cand if best_cand is not None else (0.0, -th_n * 1.25)
                else:
                    # Colliding with legend or tick: nudge up/down inside panel
                    dy = -th_n * 1.3 if (tb[1] - th_n * 1.3 > r[1] + 0.02) else th_n * 1.3
                    dx = 0.0
                    # If colliding with a legend, also try relocating legend
                    leg_h = next((h for h in handles_items if h["kind"] == "legend" and h["panel_index"] == pi), None)
                    if leg_h is not None:
                        lb = leg_h["bbox_norm"]
                        if min(tb[2], lb[2]) > max(tb[0], lb[0]) and min(tb[3], lb[3]) > max(tb[1], lb[1]):
                            dx = (lb[0] - 0.02 - tb[2]) if (lb[0] - r[0] > r[2] - lb[2]) else (lb[2] + 0.02 - tb[0])
                            dy = 0.0

                cur, _ = apply_drag(cur, target_h["id"], dx_norm=dx, dy_norm=dy, spec_id=spec_id)
                actions.append(f"微调标注 '{target_h['label']}' 消除与 '{s1 if target_h['label'] == s2 else s2}' 的碰撞")
                moved_ids.add(target_h["id"])
                changed = True

            if changed:
                continue

        # 3. Fix legend-data overlaps by testing sparse corners or expanding ylim headroom
        if qa_rep["legend_data_overlap_count"] > 0:
            corners = ["upper right", "upper left", "lower right", "lower left"]
            for pi, panel in enumerate(cur.get("panels", [])):
                lg = panel.get("legend")
                if not lg or lg.get("visible", True) is False:
                    continue
                cur_loc = lg.get("loc", "upper right")
                if lg.get("bbox") is not None:
                    lg.pop("bbox", None)
                    lg.pop("borderaxespad", None)
                    lg["loc"] = corners[(corners.index(cur_loc) + 1) % len(corners)] if cur_loc in corners else "upper right"
                    actions.append(f"将面板 {panel.get('id', pi)} 图例自动移至 {lg['loc']}")
                    changed = True
                elif it < len(corners):
                    nxt = corners[(corners.index(cur_loc) + 1) % len(corners)] if cur_loc in corners else corners[it]
                    lg["loc"] = nxt
                    actions.append(f"将面板 {panel.get('id', pi)} 图例切换至稀疏角落 {nxt}")
                    changed = True
                else:
                    ycfg = panel.setdefault("y", {})
                    if ycfg.get("lim") and len(ycfg["lim"]) == 2:
                        lo, hi = float(ycfg["lim"][0]), float(ycfg["lim"][1])
                        ycfg["lim"] = [lo, round(lo + 1.18 * (hi - lo), 5)]
                        actions.append(f"增大面板 {panel.get('id', pi)} Y 轴顶部留白 (+18%)")
                        changed = True

        if not changed:
            break

    if not actions:
        actions.append("当前图像已满足全部 QA 零碰撞与零裁切标准，无需修改")
    return cur, actions


# ---------------------------------------------------------------- AI Local Command Engine (NLU + optional LLM)
def _find_curve_y_at_x(spec_with_base: dict, panel_index: int, x_val: float) -> tuple[float, float, list[float]]:
    """Evaluate all data curves in panel near x_val -> (y_bot, y_top, [y_per_curve])."""
    data_map, _, _ = engine.resolve_data(spec_with_base)
    panel = spec_with_base["panels"][panel_index]
    engine.spec_ctx["spec"] = spec_with_base
    engine.spec_ctx["clip"] = None
    ys = []
    for pl in panel.get("plots", []):
        if pl.get("visible", True) is False:
            continue
        if pl.get("type", "line") not in ("line", "lines", "line_marker", "scatter", "fill"):
            continue
        if "data" not in pl:
            continue
        try:
            x, y = engine._series(spec_with_base, data_map, pl)
            ok = np.isfinite(x) & np.isfinite(y)
            if not np.any(ok):
                continue
            xo, yo = x[ok], y[ok]
            order = np.argsort(xo)
            xo, yo = xo[order], yo[order]
            if xo[0] - 5.0 <= x_val <= xo[-1] + 5.0:
                ys.append(float(np.interp(x_val, xo, yo)))
        except Exception:
            continue
    if not ys:
        ylim = (panel.get("y") or {}).get("lim") or [0.0, 1.0]
        mid = 0.5 * (ylim[0] + ylim[1])
        return mid - 0.1 * (ylim[1] - ylim[0]), mid + 0.1 * (ylim[1] - ylim[0]), [mid]
    return min(ys), max(ys), ys


def _normalize_selected_id(selected: Any) -> str | None:
    if not selected:
        return None
    if isinstance(selected, str):
        return selected.strip() or None
    if isinstance(selected, dict):
        if selected.get("id"):
            return str(selected["id"])
        pi = selected.get("panel_index")
        kind = selected.get("kind")
        if pi is not None:
            if kind in ("legend", "letter"):
                return f"p{int(pi)}:{kind}"
            sub_i = selected.get("subpanel_index")
            if kind == "sample_label" and sub_i is not None:
                return f"p{int(pi)}:sub{int(sub_i)}:sample_label"
            plot_i = selected.get("plot_index")
            if plot_i is not None:
                if sub_i is not None:
                    return f"p{int(pi)}:sub{int(sub_i)}:plot:{int(plot_i)}"
                return f"p{int(pi)}:plot:{int(plot_i)}"
    return None


def _pick_target_panel(spec: dict, x_hint: float | None = None, selected: Any = None) -> int:
    panels = spec.get("panels", [])
    if not panels:
        return 0
    if isinstance(selected, dict) and selected.get("panel_index") is not None:
        pi = int(selected["panel_index"])
        if 0 <= pi < len(panels):
            return pi
    sel_id = _normalize_selected_id(selected)
    if sel_id:
        m = re.match(r"^p(\d+):", sel_id)
        if m and int(m.group(1)) < len(panels):
            return int(m.group(1))
    if x_hint is not None:
        for pi, p in enumerate(panels):
            if p.get("segments"):
                for seg in p["segments"]:
                    if min(seg[0], seg[1]) <= x_hint <= max(seg[0], seg[1]):
                        return pi
            xlim = (p.get("x") or {}).get("lim")
            if xlim and min(xlim) <= x_hint <= max(xlim):
                return pi
    return 0


def _try_llm_command(spec: dict, instruction: str, region_norm=None, selected=None) -> tuple[dict, str, list[str]] | None:
    api_key = os.environ.get("SCIFIG_LLM_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("SCIFIG_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("SCIFIG_LLM_MODEL", "gpt-4o-mini")
    prompt = (
        "You are SciFigStudio Spec Patch Assistant. Modify the provided SciFigStudio JSON spec according to the user's "
        "instruction and return ONLY valid JSON with keys: {\"summary\": str, \"patch_ops\": [str], \"spec\": {...}}.\n"
        f"Selected handle: {selected}\nRegion norm: {region_norm}\nInstruction: {instruction}\n"
        f"Current spec:\n{json.dumps(_clean_user_spec(spec), ensure_ascii=False)}"
    )
    payload = json.dumps({
        "model": model,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed.get("spec"), dict) and parsed["spec"].get("panels"):
            return parsed["spec"], str(parsed.get("summary", "已通过 LLM 应用修改")), list(parsed.get("patch_ops", ["llm_patch"]))
    except Exception:
        return None
    return None


def apply_ai_command(
    spec: dict,
    instruction: str,
    region_norm: list[float] | None = None,
    selected: Any = None,
    spec_id: str | None = None,
) -> dict:
    """Apply Chinese/English scientific figure editing command to spec JSON (100% offline NLU + optional LLM)."""
    cmd = (instruction or "").strip()
    if not cmd:
        return {"ok": False, "spec": spec, "summary": "指令为空", "patch_ops": [], "diff_lines": [], "engine_mode": "local_nlu"}

    sel_id = _normalize_selected_id(selected)
    before = copy.deepcopy(spec)
    updated = copy.deepcopy(spec)
    spec_with_base = _ensure_spec_base(updated, spec_id)
    low = cmd.lower()
    patch_ops: list[str] = []
    summary = ""

    # 1. Auto-fix QA collisions
    if any(k in low for k in ("自动修复", "修复碰撞", "去重叠", "auto fix", "autofix", "fix collision", "fix qa")):
        fixed, acts = auto_fix_qa(updated, spec_id=spec_id)
        return {
            "ok": True,
            "spec": _clean_user_spec(fixed),
            "summary": "；".join(acts),
            "patch_ops": ["auto_fix_qa"],
            "diff_lines": _json_diff_lines(before, fixed),
            "engine_mode": "local_nlu",
        }

    # 2. Auto-detect peaks
    if any(k in low for k in ("自动识别峰", "自动标峰", "自动峰标", "auto peak", "detect peak")):
        pi = _pick_target_panel(updated, selected=selected)
        panel = updated["panels"][pi]
        data_map, _, _ = engine.resolve_data(spec_with_base)
        engine.spec_ctx["spec"] = spec_with_base
        engine.spec_ctx["clip"] = None
        xlim = (panel.get("x") or {}).get("lim")
        ylim = (panel.get("y") or {}).get("lim") or [0.0, 1.0]
        yspan = max(abs(ylim[1] - ylim[0]), 1e-6)
        # Use topmost line series
        curves = []
        for pl in panel.get("plots", []):
            if pl.get("type") in ("line", "line_marker") and "data" in pl and pl.get("visible", True) is not False:
                x, y = engine._series(spec_with_base, data_map, pl)
                ok = np.isfinite(x) & np.isfinite(y)
                if np.any(ok):
                    curves.append((x[ok], y[ok]))
        if curves:
            x_all = np.concatenate([c[0] for c in curves])
            x_lo = min(xlim) if xlim else float(x_all.min())
            x_hi = max(xlim) if xlim else float(x_all.max())
            grid = np.linspace(x_lo, x_hi, 600)
            top_y = np.max(np.vstack([np.interp(grid, np.sort(x), y[np.argsort(x)]) for x, y in curves]), axis=0)
            pks = blind_planner._auto_peaks(grid, top_y, x_lo, x_hi, max_peaks=4)
            added = []
            existing_x = [float(p["x"]) for p in panel.get("plots", []) if p.get("type") == "vline"]
            for px in pks:
                if any(abs(px - ex) < 0.04 * (x_hi - x_lo) for ex in existing_x):
                    continue
                y_bot, y_top, _ = _find_curve_y_at_x(spec_with_base, pi, px)
                ym_lo = round(max(0.05, (y_bot - 0.05 * yspan - ylim[0]) / yspan), 3)
                ym_hi = round(min(0.86, (y_top + 0.06 * yspan - ylim[0]) / yspan), 3)
                ly = round(min(y_top + 0.08 * yspan, ylim[1] - 0.08 * yspan), 5)
                panel["plots"].append({"type": "vline", "x": round(px, 1), "ymin": ym_lo, "ymax": ym_hi, "color": "#000000", "ls": "--", "lw": 0.9, "zorder": 2.5})
                panel["plots"].append({"type": "text", "xy": [round(px, 1), ly], "text": f"{int(round(px))}", "rotation": 0, "size": 9.0, "ha": "center", "va": "bottom", "zorder": 6})
                added.append(int(round(px)))
            summary = f"自动识别并补充 {len(added)} 处峰标: {added}" if added else "未发现新的显著特征峰"
            patch_ops.append(f"auto_peaks({added})")

    # 3. Add specific peak annotation: "补充 724 nm 峰标", "添加 724 峰标", "add peak 724", "标注 1617 cm-1"
    if not summary:
        m_pk = re.search(
            r"(?:补充|添加|新增|增加|标注|标记|add|mark|annotate|peak)\s*[^\d\-]{0,12}?(\d+(?:\.\d+)?)\s*(?:nm|cm-1|cm\^-1|ev|°|deg|ppm)?(?:\s*(?:处|的)?\s*(?:峰标|峰位|峰|虚线|标注|peak|line|marker|label))?",
            cmd,
            re.IGNORECASE,
        )
        is_peak_intent = bool(m_pk) and (
            any(k in low for k in ("峰", "peak", "vline", "虚线", "标", "nm", "cm-1", "cm^-1", "ev", "mark", "annotate"))
            and not any(k in low for k in ("上移", "下移", "左移", "右移", "范围", "lim", "列", "ncol", "比例", "字号", "粗"))
        )
        if is_peak_intent and m_pk:
            x_val = float(m_pk.group(1))
            pi = _pick_target_panel(updated, x_hint=x_val, selected=selected)
            panel = updated["panels"][pi]
            # Check custom label override (e.g. 标注为 "724 nm (Cu2+)")
            m_lbl = re.search(r"(?:文字为|标注为|标签为|label\s*=\s*|text\s*=\s*)[\"']?([^\"',;，；]+)[\"']?", cmd, re.IGNORECASE)
            lbl_txt = theme_mod.chem_mathtext(m_lbl.group(1).strip()) if m_lbl else (f"{int(round(x_val))}" if abs(x_val - round(x_val)) < 1e-4 else f"{x_val:g}")

            # Match style of existing vlines/texts in this panel
            ex_vlines = [p for p in panel.get("plots", []) if p.get("type") == "vline"]
            ex_texts = [p for p in panel.get("plots", []) if p.get("type") == "text" and p.get("coords", "data") == "data"]
            vl_lw = float(ex_vlines[0].get("lw", 0.9)) if ex_vlines else 0.9
            vl_ls = ex_vlines[0].get("ls", "--") if ex_vlines else "--"
            txt_sz = ex_texts[0].get("size", 9.0) if ex_texts else 9.0

            # Determine segment if broken-axis
            seg_idx = None
            if panel.get("segments"):
                for si, seg in enumerate(panel["segments"]):
                    if min(seg[0], seg[1]) <= x_val <= max(seg[0], seg[1]):
                        seg_idx = si
                        break

            # Evaluate actual curve heights at x_val
            y_bot, y_top, _ = _find_curve_y_at_x(spec_with_base, pi, x_val)
            ylim = (panel.get("y") or {}).get("lim")
            if not ylim or len(ylim) != 2:
                ylim = [y_bot - 0.1, y_top + 0.2]
            y_lo, y_hi = float(ylim[0]), float(ylim[1])
            yspan = max(abs(y_hi - y_lo), 1e-6)

            ym_lo = round(max(0.05, min(0.75, (y_bot - 0.05 * yspan - y_lo) / yspan)), 3)
            ym_hi = round(max(ym_lo + 0.14, min(0.84, (y_top + 0.06 * yspan - y_lo) / yspan)), 3)
            ly = round(min(y_lo + (ym_hi + 0.025) * yspan, y_hi - 0.08 * yspan), 5)

            # Avoid duplicate vline/text at same x_val
            plots = panel.setdefault("plots", [])
            replaced = False
            for pl in plots:
                if pl.get("type") == "vline" and abs(float(pl["x"]) - x_val) <= 2.0:
                    pl["x"] = round(x_val, 1)
                    pl["ymin"] = ym_lo
                    pl["ymax"] = ym_hi
                    replaced = True
                    break
            if not replaced:
                vl_obj: dict[str, Any] = {
                    "type": "vline", "x": round(x_val, 1), "ymin": ym_lo, "ymax": ym_hi,
                    "color": "#000000", "ls": vl_ls, "lw": vl_lw, "zorder": 2.5,
                }
                if seg_idx is not None:
                    vl_obj["seg"] = seg_idx
                plots.append(vl_obj)

            txt_replaced = False
            for pl in plots:
                if pl.get("type") == "text" and pl.get("coords", "data") == "data" and abs(float(pl["xy"][0]) - x_val) <= 2.0:
                    pl["xy"] = [round(x_val, 1), ly]
                    pl["text"] = lbl_txt
                    txt_replaced = True
                    break
            if not txt_replaced:
                txt_obj: dict[str, Any] = {
                    "type": "text", "xy": [round(x_val, 1), ly], "text": lbl_txt,
                    "rotation": 0, "size": txt_sz, "ha": "center", "va": "bottom", "zorder": 6,
                }
                if seg_idx is not None:
                    txt_obj["seg"] = seg_idx
                plots.append(txt_obj)

            # Run a quick QA check & auto-nudge only if the newly added label collides
            st_chk = render_state(updated, spec_id=spec_id, preview_dpi=120)
            if not st_chk["qa"]["pass"]:
                updated, _ = auto_fix_qa(updated, spec_id=spec_id, max_iters=4)

            summary = f"已在 x={x_val:g} 处补充峰位虚线与标注 '{lbl_txt}' (自动贴合数据峰高 y={y_top:.4g})"
            patch_ops.extend([f"add_vline(panel={panel.get('id','A')}, x={x_val:g})", f"add_text(text='{lbl_txt}', xy=[{x_val:g}, {ly}])"])

    # 4. Theme & Palette switching
    if not summary:
        if any(k in low for k in ("nature", "arial")):
            updated["theme"] = "journal-nature-arial"
            summary = "已切换为 Nature Arial 期刊主题 (无衬线 Arial、开放上右框线、朝外刻度)"
            patch_ops.append("set theme = 'journal-nature-arial'")
        elif any(k in low for k in ("acs", "serif")):
            updated["theme"] = "journal-acs-serif"
            summary = "已切换为 ACS Serif 期刊主题 (Times New Roman 常规体、闭合四边框、朝内刻度)"
            patch_ops.append("set theme = 'journal-acs-serif'")
        elif any(k in low for k in ("origin", "times")):
            updated["theme"] = "origin-times-bold"
            summary = "已切换为 Origin Times Bold 主题 (粗体 Times New Roman、出版级加粗轴线)"
            patch_ops.append("set theme = 'origin-times-bold'")

        if any(k in low for k in ("okabe", "色盲", "colorblind")):
            updated["palette"] = "okabe-ito"
            pal = theme_mod.load_palette("okabe-ito")
            _recolor_spec_with_palette(updated, pal)
            summary = (summary + "；" if summary else "") + "已切换为 Okabe-Ito 色盲友好色板"
            patch_ops.append("set palette = 'okabe-ito'")
        elif any(k in low for k in ("npg", "nature 色板", "nature色板")):
            updated["palette"] = "nature-npg"
            pal = theme_mod.load_palette("nature-npg")
            _recolor_spec_with_palette(updated, pal)
            summary = (summary + "；" if summary else "") + "已切换为 Nature NPG 科研色板"
            patch_ops.append("set palette = 'nature-npg'")
        elif any(k in low for k in ("pastel", "publication-pastel", "默认色板", "柔色")):
            updated["palette"] = "publication-pastel"
            pal = theme_mod.load_palette("publication-pastel")
            _recolor_spec_with_palette(updated, pal)
            summary = (summary + "；" if summary else "") + "已切换为 Publication Pastel 科研柔色板"
            patch_ops.append("set palette = 'publication-pastel'")

    # 5. Legend movement & layout
    if not summary and any(k in low for k in ("图例", "legend")):
        pi = _pick_target_panel(updated, selected=selected)
        panel = updated["panels"][pi]
        lg = panel.setdefault("legend", {"loc": "upper right", "ncol": 1})
        if any(k in low for k in ("隐藏", "关闭", "hide", "remove")):
            lg["visible"] = False
            summary = f"已隐藏面板 {panel.get('id', 'A')} 的图例"
            patch_ops.append("legend.visible = false")
        elif any(k in low for k in ("显示", "打开", "show")):
            lg["visible"] = True
            summary = f"已显示面板 {panel.get('id', 'A')} 的图例"
            patch_ops.append("legend.visible = true")
        else:
            changed_lg = []
            loc_map = [
                (("左上", "upper left", "top left"), "upper left"),
                (("右上", "upper right", "top right"), "upper right"),
                (("左下", "lower left", "bottom left"), "lower left"),
                (("右下", "lower right", "bottom right"), "lower right"),
                (("中上", "顶部居中", "upper center", "top center"), "upper center"),
                (("中下", "底部居中", "lower center", "bottom center"), "lower center"),
            ]
            for keys, loc_val in loc_map:
                if any(k in low for k in keys):
                    lg["loc"] = loc_val
                    lg.pop("bbox", None)
                    lg.pop("borderaxespad", None)
                    changed_lg.append(f"位置={loc_val}")
                    patch_ops.append(f"legend.loc = '{loc_val}'")
                    break
            m_col = re.search(r"(\d+)\s*(?:列|col)", low)
            if m_col:
                nc = max(1, min(6, int(m_col.group(1))))
                lg["ncol"] = nc
                changed_lg.append(f"列数={nc}")
                patch_ops.append(f"legend.ncol = {nc}")
            if any(k in low for k in ("边框", "加框", "frame")):
                lg["frameon"] = not any(k in low for k in ("去", "无", "no", "off"))
                changed_lg.append(f"边框={lg['frameon']}")
                patch_ops.append(f"legend.frameon = {lg['frameon']}")
            if changed_lg:
                summary = f"已调整面板 {panel.get('id', 'A')} 图例：" + "，".join(changed_lg)

    # 6. Curve shifting / spacing / scaling
    if not summary and any(k in low for k in ("上移", "下移", "曲线间距", "间距", "shift", "offset", "放大曲线", "缩小曲线", "scale")):
        pi = _pick_target_panel(updated, selected=selected)
        panel = updated["panels"][pi]
        line_plots = [(idx, pl) for idx, pl in enumerate(panel.get("plots", [])) if pl.get("type") in ("line", "line_marker", "scatter")]

        if any(k in low for k in ("间距", "spacing", "stagger")):
            step_delta = 0.03
            m_val = re.search(r"(\d+(?:\.\d+)?)", cmd)
            if m_val:
                step_delta = float(m_val.group(1))
            if any(k in low for k in ("减小", "缩小", "紧凑", "decrease")):
                step_delta = -abs(step_delta)
            for rank, (_, pl) in enumerate(line_plots):
                pl["offset"] = round(float(pl.get("offset", 0.0)) + rank * step_delta, 5)
            # Auto expand ylim top
            ylim = (panel.get("y") or {}).get("lim")
            if ylim and step_delta > 0 and len(line_plots) > 1:
                ylim[1] = round(float(ylim[1]) + (len(line_plots) - 1) * step_delta, 5)
            summary = f"已调整面板 {panel.get('id', 'A')} 曲线纵向间距 (Δ={step_delta:+.4g}/条)"
            patch_ops.append(f"stagger_curves(delta={step_delta:+.4g})")

        elif any(k in low for k in ("放大曲线", "缩小曲线", "scale")):
            m_val = re.search(r"(\d+(?:\.\d+)?)", cmd)
            fac = float(m_val.group(1)) if m_val else (1.25 if "放大" in low else 0.8)
            for _, pl in line_plots:
                pl["scale"] = round(float(pl.get("scale", 1.0)) * fac, 4)
            summary = f"已将面板 {panel.get('id', 'A')} 曲线纵坐标缩放 ×{fac:g}"
            patch_ops.append(f"scale_curves(factor={fac:g})")

        else:
            direction = -1.0 if any(k in low for k in ("下移", "降低", "down")) else 1.0
            nums = re.findall(r"(?<![A-Za-z_])(\d+(?:\.\d+)?)", cmd)
            # Identify target curve by label token (e.g. Catalyst-C, Sample-2), "顶层"/"底层", or "第N条"
            target_pl = None
            m_ord = re.search(r"第\s*(\d+)\s*条", cmd)
            if m_ord:
                ord_i = int(m_ord.group(1)) - 1
                if 0 <= ord_i < len(line_plots):
                    target_pl = line_plots[ord_i][1]
                # Remove the ordinal number from shift value candidates
                rem = re.sub(r"第\s*\d+\s*条", "", cmd)
                nums = re.findall(r"(\d+(?:\.\d+)?)", rem)
            elif any(k in low for k in ("底层", "最下", "bottom")):
                if line_plots:
                    target_pl = line_plots[0][1]
            elif any(k in low for k in ("顶层", "最上", "top")):
                if line_plots:
                    target_pl = line_plots[-1][1]
            else:
                for _, pl in line_plots:
                    plain_lbl = re.sub(r"[\$\{\}_^]", "", str(pl.get("label", ""))).lower().strip()
                    toks = re.findall(r"[a-z]+[\-_]?(?:[a-z]|\d+(?:\.\d+)?)", plain_lbl)
                    if (plain_lbl and plain_lbl in low) or any(len(t) >= 3 and t in low for t in toks):
                        target_pl = pl
                        rem = low
                        if plain_lbl:
                            rem = rem.replace(plain_lbl, "")
                        for t in toks:
                            rem = rem.replace(t, "")
                        nums = re.findall(r"(\d+(?:\.\d+)?)", rem)
                        break
            if target_pl is None and line_plots:
                target_pl = line_plots[-1][1]
            delta = float(nums[-1]) if nums else 0.04
            delta *= direction
            if target_pl is not None:
                target_pl["offset"] = round(float(target_pl.get("offset", 0.0)) + delta, 5)
                ylim = (panel.get("y") or {}).get("lim")
                if ylim and delta > 0:
                    ylim[1] = round(float(ylim[1]) + delta, 5)
                elif ylim and delta < 0:
                    ylim[0] = round(float(ylim[0]) + delta, 5)
                lbl_s = target_pl.get("label") or f"y={target_pl.get('y')}"
                summary = f"已{'上移' if delta >= 0 else '下移'}曲线 '{lbl_s}' {abs(delta):g} (offset={target_pl['offset']})"
                patch_ops.append(f"curve('{lbl_s}').offset = {target_pl['offset']}")

    # 7. Typography / Line width / Axis limits / Broken-axis ratio
    if not summary and any(k in low for k in ("字号", "字体大小", "font")):
        fac = 1.15 if any(k in low for k in ("大", "增", "粗", "larger", "bigger", "increase")) else 0.87
        st = updated.setdefault("style", {})
        st["scale"] = round(float(st.get("scale", 1.0)) * fac, 3)
        for p in updated.get("panels", []):
            for pl in p.get("plots", []):
                if pl.get("type") == "text" and isinstance(pl.get("size"), (int, float)):
                    pl["size"] = round(float(pl["size"]) * fac, 2)
        summary = f"已整体{'放大' if fac > 1 else '缩小'}字号比例 (scale={st['scale']})"
        patch_ops.append(f"style.scale = {st['scale']}")

    if not summary and any(k in low for k in ("加粗", "变细", "线宽", "thicker", "thinner", "linewidth")):
        fac = 0.72 if any(k in low for k in ("细", "薄", "thin")) else 1.35
        cnt = 0
        for p in updated.get("panels", []):
            containers = list(p.get("subpanels") or []) + [p]
            for c in containers:
                for pl in c.get("plots", []):
                    if pl.get("type") in ("line", "line_marker", "vline", "hline"):
                        pl["lw"] = round(float(pl.get("lw", 1.55)) * fac, 2)
                        cnt += 1
        summary = f"已{'加粗' if fac > 1 else '调细'} {cnt} 条曲线线宽 (×{fac:g})"
        patch_ops.append(f"scale_lw(factor={fac:g}, count={cnt})")

    if not summary and any(k in low for k in ("x轴范围", "x范围", "xlim", "y轴范围", "y范围", "ylim")):
        m_rng = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:-|~|到|至|,|\s+)\s*(-?\d+(?:\.\d+)?)", cmd)
        if m_rng:
            a_val, b_val = float(m_rng.group(1)), float(m_rng.group(2))
            pi = _pick_target_panel(updated, selected=selected)
            panel = updated["panels"][pi]
            axis_k = "y" if ("y轴" in low or "y范围" in low or "ylim" in low) else "x"
            acfg = panel.setdefault(axis_k, {})
            acfg["lim"] = [a_val, b_val]
            if axis_k == "x":
                acfg["ticks"] = blind_planner._nice_ticks(a_val, b_val, 6)
            summary = f"已更新面板 {panel.get('id', 'A')} {axis_k.upper()} 轴范围为 [{a_val:g}, {b_val:g}]"
            patch_ops.append(f"panel[{pi}].{axis_k}.lim = [{a_val:g}, {b_val:g}]")

    if not summary and any(k in low for k in ("断轴比例", "断轴", "break ratio")):
        m_rat = re.search(r"(\d+(?:\.\d+)?)\s*[:：/]\s*(\d+(?:\.\d+)?)", cmd)
        if m_rat:
            w0, w1 = float(m_rat.group(1)), float(m_rat.group(2))
            changed_seg = 0
            for p in updated.get("panels", []):
                if p.get("segments") and len(p["segments"]) >= 2:
                    p["segments"][0] = [p["segments"][0][0], p["segments"][0][1], w0]
                    p["segments"][1] = [p["segments"][1][0], p["segments"][1][1], w1]
                    changed_seg += 1
            if changed_seg:
                summary = f"已将 {changed_seg} 个断轴面板的宽度比例调整为 {w0:g}:{w1:g}"
                patch_ops.append(f"segments_ratio = {w0:g}:{w1:g}")

    # 8. Edit or delete selected handle
    if not summary and sel_id:
        try:
            ref = _parse_handle_id(sel_id)
            panel = updated["panels"][ref["pi"]]
            if any(k in low for k in ("删除", "移除", "delete", "remove")):
                if ref["kind"] == "plot":
                    cont = panel["subpanels"][ref["sub_i"]] if ref["sub_i"] is not None else panel
                    removed = cont["plots"].pop(ref["plot_i"])
                    summary = f"已删除选中图层 ({removed.get('type')}: {removed.get('text') or removed.get('label') or removed.get('x', '')})"
                    patch_ops.append(f"delete({sel_id})")
                elif ref["kind"] == "legend":
                    panel.pop("legend", None)
                    summary = f"已删除面板 {panel.get('id', 'A')} 图例"
                    patch_ops.append(f"delete({sel_id})")
                elif ref["kind"] == "letter":
                    panel.pop("letter", None)
                    summary = "已删除子图编号"
                    patch_ops.append(f"delete({sel_id})")
            else:
                m_ren = re.search(r"(?:改为|修改为|替换为|文字改|重命名为|rename to|change to|set text)\s*[:：]?\s*[\"']?(.+?)[\"']?$", cmd, re.IGNORECASE)
                if m_ren:
                    new_txt = theme_mod.chem_mathtext(m_ren.group(1).strip())
                    if ref["kind"] == "plot":
                        cont = panel["subpanels"][ref["sub_i"]] if ref["sub_i"] is not None else panel
                        pl = cont["plots"][ref["plot_i"]]
                        if pl.get("type") == "text":
                            pl["text"] = new_txt
                        else:
                            pl["label"] = new_txt
                        summary = f"已将选中元素文字更新为 '{new_txt}'"
                        patch_ops.append(f"set_text({sel_id}, '{new_txt}')")
                    elif ref["kind"] == "sample_label":
                        sub = panel["subpanels"][ref["sub_i"]]
                        if isinstance(sub.get("sample_label"), dict):
                            sub["sample_label"]["text"] = new_txt
                        else:
                            sub["sample_label"] = {"text": new_txt}
                        summary = f"已将样品标签更新为 '{new_txt}'"
                        patch_ops.append(f"set_text({sel_id}, '{new_txt}')")
        except Exception:
            pass

    # 9. Optional LLM fallback if local NLU did not match
    if not summary:
        llm_res = _try_llm_command(updated, cmd, region_norm=region_norm, selected=selected)
        if llm_res is not None:
            new_spec, llm_sum, llm_ops = llm_res
            return {
                "ok": True,
                "spec": _clean_user_spec(new_spec),
                "summary": llm_sum,
                "patch_ops": llm_ops,
                "diff_lines": _json_diff_lines(before, new_spec),
                "engine_mode": "llm",
            }
        return {
            "ok": False,
            "spec": _clean_user_spec(before),
            "summary": f"暂未识别指令 '{cmd}'。支持：'补充 724 nm 峰标'、'切换 Nature Arial 主题'、'切换 Okabe-Ito 色板'、'图例移到左上角'、'上移顶层曲线 0.04'、'放大字号'、'加粗曲线'、'自动修复碰撞'。",
            "patch_ops": [],
            "diff_lines": [],
            "engine_mode": "local_nlu",
        }

    return {
        "ok": True,
        "spec": _clean_user_spec(updated),
        "summary": summary,
        "patch_ops": patch_ops,
        "diff_lines": _json_diff_lines(before, updated),
        "engine_mode": "local_nlu",
    }


def _recolor_spec_with_palette(spec: dict, pal: dict) -> None:
    seq = pal.get("sequence") or ["#6699BA", "#CCA8E3", "#8CCF8C"]
    fills = pal.get("fills") or seq
    for p in spec.get("panels", []):
        containers = list(p.get("subpanels") or []) + [p]
        for c in containers:
            li = 0
            fi = 0
            for pl in c.get("plots", []):
                t = pl.get("type", "line")
                if t in ("line", "line_marker", "scatter") and pl.get("color") not in ("#000000", "black", "#888888", "#B0B0B0", "#555555"):
                    pl["color"] = seq[li % len(seq)]
                    li += 1
                elif t == "fill":
                    pl["color"] = fills[fi % len(fills)]
                    fi += 1


# ---------------------------------------------------------------- save, export, live blind mode
def save_spec_file(spec: dict, spec_id: str | None = None, name: str | None = None, overwrite: bool = False) -> dict:
    clean = _clean_user_spec(spec)
    if overwrite and spec_id:
        ent = resolve_spec_entry(spec_id)
        if ent and ent.get("path"):
            out_path = Path(ent["path"])
            out_path.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
            return {"ok": True, "saved_path": str(out_path), "spec_id": ent["id"]}

    out_dir = STUDIO_ROOT / "outputs" / "workbench_saved"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = name or (Path(spec_id).stem if spec_id else "workbench_fig")
    stem = re.sub(r"[^\w\-\.]", "_", stem)
    if not stem.endswith("_edited") and not name:
        stem = f"{stem}_edited"
    out_path = out_dir / f"{stem}.json"

    # Make relative data paths absolute if saving into outputs/workbench_saved so it always reloads cleanly
    spec_with_base = _ensure_spec_base(spec, spec_id)
    base = Path(spec_with_base.get("_base", "."))
    for _k, cfg in (clean.get("data") or {}).items():
        if isinstance(cfg, dict) and cfg.get("source"):
            sp = Path(cfg["source"])
            if not sp.is_absolute():
                resolved = (base / sp).resolve()
                if resolved.exists():
                    cfg["source"] = str(resolved)

    out_path.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "saved_path": str(out_path.resolve()), "spec_id": f"saved/{out_path.stem}"}


def export_artifact(spec: dict, fmt: str, spec_id: str | None = None, dpi: int = 600) -> tuple[bytes, str, str]:
    """Export publication-grade PNG (600dpi), SVG, PDF, Spec JSON, or SHA256 Provenance JSON."""
    fmt = (fmt or "svg").lower().strip()
    stem = re.sub(r"[^\w\-]", "_", (spec_id or "scifig").split("/")[-1])
    spec_with_base = _ensure_spec_base(spec, spec_id)
    render_spec = _filter_visible_spec(spec_with_base)

    if fmt == "spec":
        payload = json.dumps(_clean_user_spec(spec), ensure_ascii=False, indent=1).encode("utf-8")
        return payload, "application/json; charset=utf-8", f"{stem}.spec.json"

    if fmt == "provenance":
        _, prov, ops_applied = engine.resolve_data(render_spec)
        meta = {
            "engine": f"SciFigStudio {__version__} (Interactive Workbench)",
            "spec_id": spec_id or stem,
            "chart": spec.get("chart"),
            "theme": spec.get("theme") or "origin-times-bold",
            "palette": spec.get("palette") or "publication-pastel",
            "figure_in": [spec.get("figure", {}).get("width_in"), spec.get("figure", {}).get("height_in")],
            "export_dpi": dpi,
            "data": prov,
            "ops": spec.get("ops", []),
            "ops_applied": ops_applied,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8")
        return payload, "application/json; charset=utf-8", f"{stem}.provenance.json"

    if fmt not in ("png", "svg", "pdf"):
        raise ValueError(f"Unsupported export format: {fmt}")

    ctype_map = {
        "png": "image/png",
        "svg": "image/svg+xml; charset=utf-8",
        "pdf": "application/pdf",
    }
    with RENDER_LOCK:
        fig = engine.build(render_spec)
        try:
            buf = io.BytesIO()
            fig.savefig(
                buf, format=fmt, dpi=dpi, bbox_inches=None, pad_inches=0,
                transparent=False, facecolor="white",
                metadata={"Creator": f"SciFigStudio {__version__}"},
            )
            raw = buf.getvalue()
        finally:
            plt.close(fig)
    return raw, ctype_map[fmt], f"{stem}.{fmt}"


def run_live_blind(
    data_path: str | list[str],
    chart_id: str,
    theme: str = "origin-times-bold",
    palette: str | None = None,
    title: str = "",
) -> dict:
    """Run blind_planner live on raw data file(s) and return full Workbench StateBundle."""
    paths = [data_path] if isinstance(data_path, str) else list(data_path)
    resolved_paths = []
    for p in paths:
        pp = Path(p)
        if not pp.is_absolute():
            for base_cand in [Path.cwd(), STUDIO_ROOT, BUNDLE_ROOT, *_example_dirs()]:
                cand = (base_cand / pp).resolve()
                if cand.exists():
                    pp = cand
                    break
            else:
                pp = pp.resolve()
        if not pp.exists():
            raise FileNotFoundError(f"Data file not found: {p}")
        resolved_paths.append(pp)

    spec, _meta = blind_planner.plan_spec(
        resolved_paths, chart_id=chart_id, theme=theme or "origin-times-bold",
        caption=title or resolved_paths[0].stem, palette=palette or None,
    )
    # Run one automatic QA pass right away
    spec_fixed, _ = auto_fix_qa(spec, spec_id=f"blind/live_{resolved_paths[0].stem}", max_iters=3)
    return render_state(spec_fixed, spec_id=f"blind/live_{resolved_paths[0].stem}")
