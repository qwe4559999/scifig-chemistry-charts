"""Quantitative QA gates and side-by-side / 3-way visual comparison generators."""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import engine


def _text_obb(txt, renderer):
    """Return 4x2 oriented bounding box corners in display pixels (or None)."""
    bb = txt.get_window_extent(renderer=renderer)
    if bb.width <= 0 or bb.height <= 0:
        return None
    rot = float(txt.get_rotation() or 0.0) % 180.0
    if rot < 1.0 or abs(rot - 90.0) < 1.0 or abs(rot - 180.0) < 1.0:
        x0, y0, x1, y1 = float(bb.x0), float(bb.y0), float(bb.x1), float(bb.y1)
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)
    # Estimate true unrotated size by temporarily setting rotation=0, then rotating around center
    old_rot = txt.get_rotation()
    try:
        txt.set_rotation(0)
        bb0 = txt.get_window_extent(renderer=renderer)
    finally:
        txt.set_rotation(old_rot)
    cx, cy = 0.5 * (bb.x0 + bb.x1), 0.5 * (bb.y0 + bb.y1)
    hw, hh = 0.5 * bb0.width, 0.5 * bb0.height
    rad = np.deg2rad(float(old_rot))
    c, s = np.cos(rad), np.sin(rad)
    corners = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]], dtype=float)
    rmat = np.array([[c, -s], [s, c]])
    return corners @ rmat.T + np.array([cx, cy])


def _obb_overlap(p1: np.ndarray, p2: np.ndarray, tol_px: float = 2.0) -> bool:
    """Separating Axis Theorem overlap test for two 4x2 oriented boxes."""
    for poly in (p1, p2):
        for i in range(2):
            edge = poly[(i + 1) % 4] - poly[i]
            nrm = np.linalg.norm(edge)
            if nrm < 1e-9:
                continue
            axis = edge / nrm
            proj1 = p1 @ axis
            proj2 = p2 @ axis
            if min(proj1.max(), proj2.max()) - max(proj1.min(), proj2.min()) <= tol_px:
                return False
    return True


def _ink_bbox(img_rgb: np.ndarray, thr: int = 248) -> list[float]:
    mask = np.any(img_rgb < thr, axis=-1)
    if not np.any(mask):
        return [0.0, 0.0, 1.0, 1.0]
    ys, xs = np.nonzero(mask)
    h, w = img_rgb.shape[:2]
    return [
        round(float(xs.min()) / w, 4),
        round(float(ys.min()) / h, 4),
        round(float(xs.max() + 1) / w, 4),
        round(float(ys.max() + 1) / h, 4),
    ]


def _box_iou(a: list[float], b: list[float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return round(inter / union, 4) if union > 0 else 0.0


def referenced_columns(spec: dict) -> dict[str, list]:
    """Return {data_key: [col_refs...]} actually referenced by plots in spec."""
    refs: dict[str, list] = {}
    for panel in spec.get("panels", []):
        containers = list(panel.get("subpanels") or []) + [panel]
        if panel.get("inset"):
            containers.append(panel["inset"])
        for cont in containers:
            for pl in cont.get("plots", []):
                dk = pl.get("data")
                if not dk:
                    continue
                bucket = refs.setdefault(dk, [])
                for field in ("x", "y", "baseline"):
                    val = pl.get(field)
                    if val is None or (field == "baseline" and val == "offset"):
                        continue
                    items = val if isinstance(val, list) else [val]
                    for it in items:
                        if isinstance(it, (int, str)) and it not in bucket:
                            bucket.append(it)
    return refs


def resolve_col_name(df, ref):
    if isinstance(ref, (int, float)) and not isinstance(ref, bool):
        idx = int(ref)
        return df.columns[idx] if 0 <= idx < len(df.columns) else None
    if ref in df.columns:
        return ref
    sref = str(ref)
    for c in df.columns:
        if str(c) == sref:
            return c
    return None


def _to_rgb_white(path: str | Path) -> Image.Image:
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        return bg.convert("RGB")
    return im.convert("RGB")


def _auto_ref_path(spec_path: Path) -> Path | None:
    m = re.match(r"^(FigS?\d+)", spec_path.stem, re.IGNORECASE)
    if not m:
        return None
    fid = m.group(1)
    if fid.lower().startswith("figs"):
        fid = "FigS" + fid[4:]
    else:
        fid = "Fig" + fid[3:]
    cand = Path(__file__).resolve().parents[1] / "outputs" / "compare" / "_refs" / f"{fid}.png"
    return cand if cand.exists() else None


def run_qa(
    spec_path: str | Path,
    rendered_png: str | Path | None = None,
    ref_png: str | Path | None = None,
    out_json: str | Path | None = None,
) -> dict:
    sp = Path(spec_path)
    spec = engine.merge_preset(engine.load_spec(sp))
    fig = engine.build(spec)
    fig.canvas.draw()
    rr = fig.canvas.get_renderer()
    fw_px, fh_px = fig.canvas.get_width_height()

    # 1. Text overlap & out-of-bounds clipping check
    from matplotlib.text import Text as MplText
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
    for txt in fig.findobj(match=lambda obj: isinstance(obj, MplText)):
        if id(txt) in seen_ids or id(txt) in hidden_tick_ids or not txt.get_visible():
            continue
        seen_ids.add(id(txt))
        s = str(txt.get_text()).strip()
        if not s:
            continue
        try:
            bb = txt.get_window_extent(renderer=rr)
            obb = _text_obb(txt, rr)
        except Exception:
            continue
        if obb is None:
            continue
        text_boxes.append((s, (float(bb.x0), float(bb.y0), float(bb.x1), float(bb.y1)), obb))

    overlaps = []
    for i in range(len(text_boxes)):
        for j in range(i + 1, len(text_boxes)):
            if _obb_overlap(text_boxes[i][2], text_boxes[j][2], tol_px=2.0):
                overlaps.append([text_boxes[i][0], text_boxes[j][0]])

    clipped = []
    for s, (x0, y0, x1, y1), _obb in text_boxes:
        if x0 < -2.0 or y0 < -2.0 or x1 > fw_px + 2.0 or y1 > fh_px + 2.0:
            clipped.append({"text": s, "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})

    # 2. Legend-data overlap check
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
                legend_data_hits.append({
                    "label": str(ln.get_label()),
                    "points_inside": cnt,
                    "fraction": round(cnt / max(1, len(pts)), 4),
                })

    # 3. Data NaN (referenced columns only) & deconvolution sum check
    data_map, _, _ = engine.resolve_data(spec)
    ref_cols = referenced_columns(spec)
    nan_issues = []
    for dkey, df in data_map.items():
        cols_to_check = ref_cols.get(dkey)
        if cols_to_check is None:
            continue
        for cref in cols_to_check:
            cname = resolve_col_name(df, cref)
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
                if "data" not in pl:
                    continue
                grp = (pl["data"], round(float(pl.get("offset", 0.0)), 6), round(float(pl.get("scale", 1.0)), 6))
                if pl.get("type") == "fill":
                    fills_by_group.setdefault(grp, []).append(pl["y"])
                elif pl.get("type") == "line" and str(pl.get("y", "")).lower() in ("fit", "sum", "3"):
                    fits_by_group.setdefault(grp, []).append(pl["y"])
            for grp, fcols in fills_by_group.items():
                if grp in fits_by_group and len(fcols) >= 2:
                    df = data_map[grp[0]]
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

    # 4. Rendered PNG vs Ref PNG comparison (aspect ratio & ink box)
    buf = np.asarray(fig.canvas.buffer_rgba())[..., :3] if hasattr(fig.canvas, "buffer_rgba") else None
    if rendered_png and Path(rendered_png).exists():
        ren_rgb = np.asarray(_to_rgb_white(rendered_png))
    elif buf is not None:
        ren_rgb = buf
    else:
        ren_rgb = np.full((fh_px, fw_px, 3), 255, dtype=np.uint8)

    ar_ren = round(ren_rgb.shape[1] / max(1, ren_rgb.shape[0]), 4)
    ink_ren = _ink_bbox(ren_rgb)

    ref_cmp = None
    ref_p = Path(ref_png) if ref_png else _auto_ref_path(sp)
    if ref_p and ref_p.exists():
        ref_rgb = np.asarray(_to_rgb_white(ref_p))
        ar_ref = round(ref_rgb.shape[1] / max(1, ref_rgb.shape[0]), 4)
        ink_ref = _ink_bbox(ref_rgb)
        ar_diff_pct = round((ar_ren - ar_ref) / max(1e-6, ar_ref) * 100.0, 2)
        ref_cmp = {
            "ref_png": str(ref_p),
            "aspect_ratio_ref": ar_ref,
            "aspect_ratio_rendered": ar_ren,
            "aspect_ratio_diff_pct": ar_diff_pct,
            "ink_bbox_ref": ink_ref,
            "ink_bbox_rendered": ink_ren,
            "ink_iou": _box_iou(ink_ref, ink_ren),
        }

    plt.close(fig)

    errors = []
    warnings = []
    if clipped:
        errors.append(f"{len(clipped)} clipped text element(s) outside canvas")
    if nan_issues:
        errors.append(f"{len(nan_issues)} all-NaN column(s)")
    if len(overlaps) > 0:
        warnings.append(f"{len(overlaps)} text overlap pair(s)")
    if legend_data_hits:
        warnings.append(f"{len(legend_data_hits)} legend-data overlap(s)")
    if ref_cmp and abs(ref_cmp["aspect_ratio_diff_pct"]) > 5.0:
        warnings.append(f"aspect ratio differs by {ref_cmp['aspect_ratio_diff_pct']}%")

    report = {
        "spec": str(sp.resolve()),
        "rendered_png": str(rendered_png) if rendered_png else None,
        "text_count": len(text_boxes),
        "text_overlap_count": len(overlaps),
        "text_overlaps": overlaps[:20],
        "out_of_bounds_count": len(clipped),
        "clipped_texts": clipped[:20],
        "legend_data_overlap_count": len(legend_data_hits),
        "legend_data_overlaps": legend_data_hits,
        "nan_issues": nan_issues,
        "deconv_checks": deconv_checks,
        "aspect_ratio": ar_ren,
        "ink_bbox": ink_ren,
        "ref_comparison": ref_cmp,
        "pass": len(errors) == 0 and len(overlaps) == 0,
        "errors": errors,
        "warnings": warnings,
    }
    if out_json:
        op = Path(out_json)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def _load_ui_font(size: int) -> ImageFont.ImageFont:
    for cand in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/timesbd.ttf"):
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    return ImageFont.load_default()


def compare_images(
    ref_png: str | Path,
    repro_png: str | Path,
    out_png: str | Path,
    left_label: str = "Original Paper (_refs)",
    right_label: str = "SciFigStudio Reproduction",
    title: str | None = None,
    target_height: int = 1200,
) -> Path:
    """Create a side-by-side PNG on white background with equal height and a crisp header bar."""
    im_l = _to_rgb_white(ref_png)
    im_r = _to_rgb_white(repro_png)
    h = min(max(im_l.height, im_r.height), target_height) if max(im_l.height, im_r.height) > target_height else max(im_l.height, im_r.height)
    w_l = int(round(im_l.width * (h / im_l.height)))
    w_r = int(round(im_r.width * (h / im_r.height)))
    im_l = im_l.resize((w_l, h), Image.Resampling.LANCZOS)
    im_r = im_r.resize((w_r, h), Image.Resampling.LANCZOS)

    hdr_h = 56
    gap = 16
    pad = 16
    total_w = pad + w_l + gap + w_r + pad
    total_h = hdr_h + h + pad
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Header bar
    draw.rectangle([0, 0, total_w, hdr_h - 4], fill=(15, 41, 66))
    font = _load_ui_font(22)
    l_txt = f"{left_label}" if not title else f"{title} | {left_label}"
    r_txt = f"{right_label}"
    draw.text((pad, 14), l_txt, fill=(255, 255, 255), font=font)
    draw.text((pad + w_l + gap, 14), r_txt, fill=(140, 207, 140), font=font)

    canvas.paste(im_l, (pad, hdr_h))
    canvas.paste(im_r, (pad + w_l + gap, hdr_h))
    # Subtle divider & frames
    div_x = pad + w_l + gap // 2
    draw.line([(div_x, hdr_h), (div_x, hdr_h + h)], fill=(200, 208, 220), width=2)
    draw.rectangle([pad - 1, hdr_h - 1, pad + w_l, hdr_h + h], outline=(210, 215, 224), width=1)
    draw.rectangle([pad + w_l + gap - 1, hdr_h - 1, pad + w_l + gap + w_r, hdr_h + h], outline=(210, 215, 224), width=1)

    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def compare_3way(
    ref_png: str | Path,
    refmode_png: str | Path,
    blind_png: str | Path,
    out_png: str | Path,
    title: str | None = None,
    target_height: int = 1000,
) -> Path:
    """Create a 3-way comparison PNG: Original Paper | Reference-Mode | Blind-Mode."""
    imgs = [_to_rgb_white(p) for p in (ref_png, refmode_png, blind_png)]
    h = min(max(im.height for im in imgs), target_height)
    resized = [im.resize((int(round(im.width * (h / im.height))), h), Image.Resampling.LANCZOS) for im in imgs]
    hdr_h, gap, pad = 54, 14, 14
    total_w = pad * 2 + sum(im.width for im in resized) + gap * 2
    total_h = hdr_h + h + pad
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, total_w, hdr_h - 4], fill=(15, 41, 66))
    font = _load_ui_font(20)
    labels = [
        (f"{title} | Original" if title else "Original Paper", (255, 255, 255)),
        ("Reference-Mode", (179, 205, 228)),
        ("Blind-Mode (No Ref)", (140, 207, 140)),
    ]
    cx = pad
    for idx, (im, (lbl, col)) in enumerate(zip(resized, labels)):
        draw.text((cx, 14), lbl, fill=col, font=font)
        canvas.paste(im, (cx, hdr_h))
        draw.rectangle([cx - 1, hdr_h - 1, cx + im.width, hdr_h + h], outline=(210, 215, 224), width=1)
        if idx < 2:
            div_x = cx + im.width + gap // 2
            draw.line([(div_x, hdr_h), (div_x, hdr_h + h)], fill=(200, 208, 220), width=2)
        cx += im.width + gap
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out
