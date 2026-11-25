"""PDF reference rendering (on pure white background) and vector blueprint extraction."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

DEFAULT_PDF_DIR = Path.cwd() / "refs_pdf"


def fig_id_from_pdf(pdf_path: Path) -> str | None:
    m = re.match(r"^(FigS?\d+)", pdf_path.stem, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1)
    if raw.lower().startswith("figs"):
        return "FigS" + raw[4:]
    return "Fig" + raw[3:]


def list_figure_pdfs(pdf_dir: str | Path | None = None) -> list[tuple[str, Path]]:
    root = Path(pdf_dir) if pdf_dir else DEFAULT_PDF_DIR
    items = []
    for p in sorted(root.glob("*.pdf")):
        fid = fig_id_from_pdf(p)
        if fid:
            items.append((fid, p))
    def _sort_key(item):
        fid = item[0]
        is_s = 1 if fid.startswith("FigS") else 0
        num = int(fid[4:] if is_s else fid[3:])
        return (is_s, num)
    return sorted(items, key=_sort_key)


def render_refs(
    pdf_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    dpi: int = 300,
) -> list[dict]:
    """Render vector figure PDFs at 300 dpi onto an opaque white background."""
    out = Path(out_dir) if out_dir else (Path(__file__).resolve().parents[1] / "outputs" / "compare" / "_refs")
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for fid, pdf_path in list_figure_pdfs(pdf_dir):
        doc = pymupdf.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        dst = out / f"{fid}.png"
        pix.save(str(dst))
        results.append({
            "fig": fid,
            "pdf": str(pdf_path),
            "png": str(dst),
            "width_px": pix.width,
            "height_px": pix.height,
            "dpi": dpi,
        })
        doc.close()
    return results


def _rgb_hex(c) -> str | None:
    if not c or not isinstance(c, (list, tuple)) or len(c) < 3:
        return None
    return "#%02X%02X%02X" % tuple(int(round(max(0.0, min(1.0, float(v))) * 255)) for v in c[:3])


def _detect_axis_boxes(page, W: float, H: float) -> list[dict]:
    """Extract normalized [left, bottom, width, height] axis box rects from PDF vector lines/rects."""
    h_lines = []
    v_lines = []
    candidates = []

    for dr in page.get_drawings():
        fill_col = dr.get("fill")
        has_colored_fill = fill_col is not None and _rgb_hex(fill_col) not in (None, "#FFFFFF")
        lw = float(dr.get("width") or 0.0)
        for it in dr.get("items", []):
            kind = it[0]
            if kind == "re":
                if has_colored_fill or lw < 0.85:
                    continue
                r = it[1]
                if r.width > 0.06 * W and r.height > 0.06 * H and r.width < 0.995 * W:
                    candidates.append((r.x0, r.y0, r.x1, r.y1))
            elif kind == "l" and lw >= 0.85:
                p0, p1 = it[1], it[2]
                dx, dy = abs(p1.x - p0.x), abs(p1.y - p0.y)
                if dy < 1.2 and dx > 0.06 * W:
                    h_lines.append((min(p0.x, p1.x), max(p0.x, p1.x), 0.5 * (p0.y + p1.y)))
                elif dx < 1.2 and dy > 0.06 * H:
                    v_lines.append((0.5 * (p0.x + p1.x), min(p0.y, p1.y), max(p0.y, p1.y)))

    # Reconstruct rectangles from matching horizontal & vertical spine pairs
    tol = 2.5
    for i, (x0a, x1a, ya) in enumerate(h_lines):
        for x0b, x1b, yb in h_lines[i + 1 :]:
            if abs(x0a - x0b) <= tol and abs(x1a - x1b) <= tol and abs(ya - yb) > 0.06 * H:
                x0, x1 = 0.5 * (x0a + x0b), 0.5 * (x1a + x1b)
                y0, y1 = min(ya, yb), max(ya, yb)
                has_l = any(abs(vx - x0) <= tol and vy0 <= y0 + tol and vy1 >= y1 - tol for vx, vy0, vy1 in v_lines)
                has_r = any(abs(vx - x1) <= tol and vy0 <= y0 + tol and vy1 >= y1 - tol for vx, vy0, vy1 in v_lines)
                if has_l or has_r:
                    candidates.append((x0, y0, x1, y1))

    # Deduplicate close boxes
    uniq = []
    for x0, y0, x1, y1 in sorted(candidates, key=lambda b: (-b[1], b[0])):
        if not any(
            abs(x0 - ux0) < 3.0 and abs(y0 - uy0) < 3.0 and abs(x1 - ux1) < 3.0 and abs(y1 - uy1) < 3.0
            for ux0, uy0, ux1, uy1 in uniq
        ):
            uniq.append((x0, y0, x1, y1))

    # Fallback to image boxes for raster-only PDFs (Fig3, FigS5)
    if not uniq:
        for info in page.get_image_info(xrefs=False):
            bbox = info.get("bbox")
            if bbox:
                x0, y0, x1, y1 = bbox
                if (x1 - x0) > 0.05 * W and (y1 - y0) > 0.05 * H:
                    uniq.append((x0, y0, x1, y1))

    boxes = []
    for idx, (x0, y0, x1, y1) in enumerate(uniq):
        boxes.append({
            "index": idx,
            "rect_norm": [
                round(x0 / W, 4),
                round(1.0 - y1 / H, 4),
                round((x1 - x0) / W, 4),
                round((y1 - y0) / H, 4),
            ],
            "bbox_pt": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
        })
    return boxes


def extract_blueprint_one(pdf_path: Path, fid: str | None = None) -> dict:
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    W, H = float(page.rect.width), float(page.rect.height)

    lw_counts: Counter[float] = Counter()
    stroke_colors: Counter[str] = Counter()
    fill_colors: Counter[str] = Counter()
    for dr in page.get_drawings():
        w = dr.get("width")
        if w and w > 0:
            lw_counts[round(float(w), 2)] += 1
        sc = _rgb_hex(dr.get("color"))
        if sc:
            stroke_colors[sc] += 1
        fc = _rgb_hex(dr.get("fill"))
        if fc:
            fill_colors[fc] += 1

    size_counts: Counter[float] = Counter()
    font_counts: Counter[str] = Counter()
    texts = []
    tdict = page.get_text("dict")
    for blk in tdict.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                txt = sp.get("text", "").strip()
                if not txt:
                    continue
                sz = round(float(sp.get("size", 0.0)), 2)
                fn = sp.get("font", "")
                size_counts[sz] += 1
                font_counts[fn] += 1
                x0, y0, x1, y1 = sp.get("bbox", (0, 0, 0, 0))
                col_int = sp.get("color", 0)
                chex = "#%06X" % (int(col_int) & 0xFFFFFF)
                texts.append({
                    "text": txt,
                    "font": fn,
                    "size_pt": sz,
                    "color": chex,
                    "rect_norm": [
                        round(x0 / W, 4),
                        round(1.0 - y1 / H, 4),
                        round((x1 - x0) / W, 4),
                        round((y1 - y0) / H, 4),
                    ],
                })

    axes_boxes = _detect_axis_boxes(page, W, H)
    images = page.get_images()
    doc.close()

    return {
        "fig": fid or fig_id_from_pdf(pdf_path) or pdf_path.stem,
        "pdf": str(pdf_path),
        "width_pt": round(W, 2),
        "height_pt": round(H, 2),
        "width_in": round(W / 72.0, 4),
        "height_in": round(H / 72.0, 4),
        "aspect_ratio": round(W / H, 4),
        "image_count": len(images),
        "axes_boxes": axes_boxes,
        "font_sizes_pt": {str(k): v for k, v in sorted(size_counts.items())},
        "fonts": dict(font_counts.most_common()),
        "linewidths_pt": {str(k): v for k, v in sorted(lw_counts.items())},
        "stroke_colors": dict(stroke_colors.most_common()),
        "fill_colors": dict(fill_colors.most_common()),
        "text_bboxes": texts,
    }


def extract_blueprints(
    pdf_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
) -> list[dict]:
    out = Path(out_dir) if out_dir else (Path(__file__).resolve().parents[1] / "outputs" / "compare" / "_blueprints")
    out.mkdir(parents=True, exist_ok=True)
    summaries = []
    for fid, pdf_path in list_figure_pdfs(pdf_dir):
        bp = extract_blueprint_one(pdf_path, fid)
        dst = out / f"{fid}.json"
        dst.write_text(json.dumps(bp, ensure_ascii=False, indent=1), encoding="utf-8")
        summaries.append({
            "fig": fid,
            "json": str(dst),
            "width_in": bp["width_in"],
            "height_in": bp["height_in"],
            "n_axes_boxes": len(bp["axes_boxes"]),
            "n_texts": len(bp["text_bboxes"]),
            "images": bp["image_count"],
        })
    return summaries
