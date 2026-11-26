"""SciFigStudio CLI: doctor, render-refs, extract-blueprints, render, validate, qa, compare, templates, new, read, probe."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, readers, theme as theme_mod


def _p(msg):
    print(msg, flush=True)


def cmd_render(a):
    from .engine import render
    meta = render(a.spec, a.out, tuple(a.formats.split(",")), a.dpi, a.name)
    if a.json:
        _p(json.dumps(meta, ensure_ascii=False, indent=1))
    else:
        for o in meta["outputs"]:
            _p("OK  " + o)
        _p("provenance: " + str(Path(meta["outputs"][0]).with_suffix(".provenance.json")))
    return 0


def cmd_validate(a):
    from .engine import load_spec, merge_preset, resolve_data
    from .qa import referenced_columns, resolve_col_name
    spec = merge_preset(load_spec(a.spec))
    data, prov, ops_applied = resolve_data(spec)
    problems = []
    for panel in spec.get("panels", []):
        sublist = panel.get("subpanels") or [panel]
        for sp in sublist:
            for pl in sp.get("plots", []):
                if pl.get("data") and pl["data"] not in data:
                    problems.append(f"panel {panel.get('id')}: undefined data {pl['data']}")
    ref_cols = referenced_columns(spec)
    for k, df in data.items():
        for cref in ref_cols.get(k, []):
            cname = resolve_col_name(df, cref)
            if cname is None:
                problems.append(f"data {k} missing column: {cref}")
            elif df[cname].isna().all():
                problems.append(f"data {k} referenced column all-NaN: {cname}")
    out = {
        "spec": a.spec,
        "chart": spec.get("chart"),
        "datasets": prov,
        "ops_applied": ops_applied,
        "n_panels": len(spec.get("panels", [])),
        "problems": problems,
    }
    _p(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if not problems else 2


def cmd_qa(a):
    from .qa import run_qa
    sp = Path(a.spec)
    out_json = a.out
    if not out_json and a.png:
        out_json = str(Path(a.png).with_suffix(".qa.json"))
    elif not out_json:
        out_json = str(sp.with_suffix(".qa.json"))
    rep = run_qa(sp, rendered_png=a.png, ref_png=a.ref, out_json=out_json)
    _p(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["pass"] else 1


def cmd_compare(a):
    from .qa import compare_images
    ref = Path(a.ref)
    if not ref.exists():
        cand = Path(__file__).resolve().parents[1] / "outputs" / "compare" / "_refs" / f"{a.ref}.png"
        if cand.exists():
            ref = cand
    if not ref.exists():
        _p(f"reference PNG not found: {a.ref}")
        return 2
    out = a.out
    if not out:
        out_dir = Path(__file__).resolve().parents[1] / "outputs" / "compare"
        out = str(out_dir / f"{ref.stem}_compare.png")
    res = compare_images(ref, a.repro, out, title=a.title or ref.stem)
    _p("OK  " + str(res))
    return 0


def cmd_render_refs(a):
    from .blueprint import render_refs
    rows = render_refs(pdf_dir=a.pdf_dir, out_dir=a.out, dpi=a.dpi)
    _p(json.dumps({"count": len(rows), "refs": rows}, ensure_ascii=False, indent=1))
    return 0


def cmd_extract_blueprints(a):
    from .blueprint import extract_blueprints
    rows = extract_blueprints(pdf_dir=a.pdf_dir, out_dir=a.out)
    _p(json.dumps({"count": len(rows), "blueprints": rows}, ensure_ascii=False, indent=1))
    return 0


def cmd_templates(a):
    base = theme_mod.assets_root()
    charts = []
    for p in sorted((base / "charts").glob("*/chart.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        charts.append({"id": c.get("id"), "name": c.get("name"), "when": c.get("when", "")[:80], "path": str(p)})
    out = {
        "themes": sorted(p.stem for p in (base / "themes").glob("*.json")),
        "palettes": sorted(p.stem for p in (base / "palettes").glob("*.json")),
        "charts": charts,
    }
    _p(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_new(a):
    p = theme_mod.assets_root() / "charts" / a.chart / "chart.json"
    if not p.exists():
        _p(f"no such chart template: {a.chart}")
        return 2
    c = json.loads(p.read_text(encoding="utf-8"))
    spec = c.get("spec_template", {})
    spec["chart"] = c["id"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    _p("scaffolded: " + str(out))
    return 0


def cmd_read(a):
    p = Path(a.file)
    if a.reader == "bruker" or p.is_dir():
        df = readers.read_bruker(str(p))
    else:
        df = readers.load_any(str(p))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(a.out, index=False)
        _p(f"wrote {a.out}  rows={df.shape[0]}")
    if a.json:
        _p(json.dumps({
            "file": str(p),
            "rows": int(df.shape[0]),
            "cols": list(map(str, df.columns)),
            "head": json.loads(df.head(3).to_json(orient="records")),
            "attrs": {k: str(v) for k, v in df.attrs.items()},
        }, ensure_ascii=False, indent=1))
    return 0


PROBE = {
    ".csv": ("text", "pandas.read_csv"),
    ".txt": ("text", "pandas.read_csv(sep=None)"),
    ".md": ("text", "read_text"),
    ".xlsx": ("zip/ooxml", "openpyxl/pandas"),
    ".xls": ("cdf/ole2", "pandas+xlrd"),
    ".pdf": ("pdf", "pymupdf"),
    ".png": ("raster", "PIL"),
    ".tif": ("raster", "PIL"),
    ".spa": ("binary+ascii head", "scifig.readers.read_spa"),
    ".vgd": ("OLE2", "scifig.readers.read_vgd"),
    ".asc": ("text", "scifig.readers.read_asc"),
    ".ras": ("text", "scifig.readers.read_ras"),
    ".spc": ("raw float array", "scifig.readers.read_spc"),
    ".opju": ("proprietary (CPYUA)", "archived Origin project (not used by scifig)"),
    "(none)": ("Bruker TopSpin", "scifig.readers.read_bruker"),
}


def cmd_probe(a):
    root = Path(a.dir)
    seen = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix if p.suffix else "(none)"
        key = ext.lower()
        e = seen.setdefault(key, {"ext": ext, "count": 0, "bytes": 0, "samples": []})
        e["count"] += 1
        e["bytes"] += p.stat().st_size
        if len(e["samples"]) < 3:
            e["samples"].append(str(p.relative_to(root)))
    rows = []
    for k, e in sorted(seen.items(), key=lambda kv: -kv[1]["count"]):
        info = PROBE.get(k) or ("unknown", "")
        rows.append({
            "ext": e["ext"],
            "count": e["count"],
            "MB": round(e["bytes"] / 1048576, 2),
            "kind": info[0],
            "reader": info[1],
            "samples": e["samples"],
        })
    _p(json.dumps(rows, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def cmd_doctor(a):
    import matplotlib
    from matplotlib import font_manager
    import pymupdf

    a_root = theme_mod.assets_root()
    studio_root = Path(__file__).resolve().parents[1]
    names = {f.name for f in font_manager.fontManager.ttflist}
    refs_dir = studio_root / "outputs" / "compare" / "_refs"
    bps_dir = studio_root / "outputs" / "compare" / "_blueprints"
    info = {
        "version": __version__,
        "python": sys.version.split()[0],
        "matplotlib": matplotlib.__version__,
        "pymupdf": pymupdf.__version__,
        "assets_root": str(a_root),
        "assets_ok": a_root.exists(),
        "themes": sorted(p.stem for p in (a_root / "themes").glob("*.json")) if a_root.exists() else [],
        "palettes": sorted(p.stem for p in (a_root / "palettes").glob("*.json")) if a_root.exists() else [],
        "charts": sorted(p.parent.name for p in (a_root / "charts").glob("*/chart.json")) if a_root.exists() else [],
        "font_times_found": "Times New Roman" in names,
        "font_arial_found": "Arial" in names,
        "refs_count": len(list(refs_dir.glob("*.png"))) if refs_dir.exists() else 0,
        "blueprints_count": len(list(bps_dir.glob("*.json"))) if bps_dir.exists() else 0,
    }
    _p(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scifig", description="SciFigStudio: Origin-free scientific figure engine")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Environment and asset diagnostics")
    d.set_defaults(func=cmd_doctor)

    rr = sub.add_parser("render-refs", help="Render paper PDFs to 300 dpi white-background PNGs")
    rr.add_argument("--pdf-dir", default=None)
    rr.add_argument("-o", "--out", default=None)
    rr.add_argument("--dpi", type=int, default=300)
    rr.set_defaults(func=cmd_render_refs)

    eb = sub.add_parser("extract-blueprints", help="Extract PDF layout/font/color blueprints")
    eb.add_argument("--pdf-dir", default=None)
    eb.add_argument("-o", "--out", default=None)
    eb.set_defaults(func=cmd_extract_blueprints)

    r = sub.add_parser("render", help="Render declarative spec to PNG/SVG/PDF")
    r.add_argument("spec")
    r.add_argument("-o", "--out", default=None)
    r.add_argument("--formats", default="png,svg,pdf")
    r.add_argument("--dpi", type=int, default=None)
    r.add_argument("--name", default=None)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_render)

    v = sub.add_parser("validate", help="Validate spec, data paths, and columns")
    v.add_argument("spec")
    v.set_defaults(func=cmd_validate)

    q = sub.add_parser("qa", help="Run quantitative QA checks on spec and rendered figure")
    q.add_argument("spec")
    q.add_argument("--png", default=None)
    q.add_argument("--ref", default=None)
    q.add_argument("-o", "--out", default=None)
    q.set_defaults(func=cmd_qa)

    c = sub.add_parser("compare", help="Create side-by-side comparison PNG")
    c.add_argument("ref", help="Path to ref PNG or Fig ID (e.g. Fig1)")
    c.add_argument("repro", help="Path to reproduced PNG")
    c.add_argument("-o", "--out", default=None)
    c.add_argument("--title", default=None)
    c.set_defaults(func=cmd_compare)

    t = sub.add_parser("templates", help="List available themes, palettes, and chart templates")
    t.set_defaults(func=cmd_templates)

    n = sub.add_parser("new", help="Scaffold a spec from a chart template")
    n.add_argument("chart")
    n.add_argument("out")
    n.set_defaults(func=cmd_new)

    rd = sub.add_parser("read", help="Read instrument/table file")
    rd.add_argument("file")
    rd.add_argument("--reader", default=None)
    rd.add_argument("--out", default=None)
    rd.add_argument("--json", action="store_true")
    rd.set_defaults(func=cmd_read)

    pr = sub.add_parser("probe", help="Inventory file extensions in directory")
    pr.add_argument("dir")
    pr.add_argument("--out", default=None)
    pr.set_defaults(func=cmd_probe)

    wb = sub.add_parser("workbench", help="Launch Interactive Human-AI Visual Editing GUI Workbench")
    wb.add_argument("--host", default="127.0.0.1")
    wb.add_argument("--port", type=int, default=8765)
    wb.add_argument("--no-open", action="store_true", help="Do not auto-open browser")
    wb.add_argument("--verbose", action="store_true", help="Print HTTP access logs")
    wb.set_defaults(func=cmd_workbench)

    a = ap.parse_args(argv)
    return a.func(a)


def cmd_workbench(a):
    from .workbench_server import serve
    return serve(host=a.host, port=a.port, open_browser=not a.no_open, verbose=a.verbose)
