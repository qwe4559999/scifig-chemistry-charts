"""Themes, color palettes, proportional theme scaling, and upright-bold mathtext helpers."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import matplotlib as mpl

ASSETS_ENV = "SCIFIG_ASSETS"
DEFAULT_ASSETS = Path(__file__).resolve().parents[1] / "assets"

BASE_THEME = {
    "name": "origin-times-bold",
    "font": {"family": "Times New Roman", "weight": "bold", "style": "normal"},
    "size": {
        "label": 14.1,
        "tick": 10.2,
        "legend": 10.2,
        "panel": 14.1,
        "annot": 7.1,
        "small": 7.0,
        "sub": 7.0,
    },
    "line": {"axis": 1.55, "data": 1.55, "drifts": 0.8, "fit": 0.8, "thin": 0.38},
    "tick": {"direction": "in", "length": 3.6, "width": 1.55, "pad": 3.5, "minor": False, "top": False, "right": False},
    "spines": {"lw": 1.55, "all": True},
    "legend": {"frameon": False, "handlelength": 1.8, "handletextpad": 0.4, "borderaxespad": 0.3},
    "palette": "publication-pastel",
}


def assets_root() -> Path:
    env = os.environ.get(ASSETS_ENV)
    return Path(env) if env else DEFAULT_ASSETS


def _read_json(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def scale_theme(theme: dict, factor: float) -> dict:
    """Proportionally scale font sizes, line widths, and tick dimensions."""
    if not factor or abs(factor - 1.0) < 1e-6:
        return theme
    out = json.loads(json.dumps(theme))
    for k, v in out.get("size", {}).items():
        if isinstance(v, (int, float)):
            out["size"][k] = round(v * factor, 3)
    for k, v in out.get("line", {}).items():
        if isinstance(v, (int, float)):
            out["line"][k] = round(v * factor, 3)
    for k in ("length", "width", "pad"):
        if isinstance(out.get("tick", {}).get(k), (int, float)):
            out["tick"][k] = round(out["tick"][k] * factor, 3)
    if isinstance(out.get("spines", {}).get("lw"), (int, float)):
        out["spines"]["lw"] = round(out["spines"]["lw"] * factor, 3)
    return out


def load_theme(ref: str | None) -> dict:
    theme = json.loads(json.dumps(BASE_THEME))
    if not ref:
        return theme
    p = Path(ref)
    if not p.suffix:
        p = assets_root() / "themes" / f"{ref}.json"
    if p.exists():
        theme = deep_merge(theme, _read_json(p))
    return theme


def load_palette(name: str | None) -> dict:
    if not name:
        name = BASE_THEME["palette"]
    p = assets_root() / "palettes" / f"{name}.json"
    if p.exists():
        return _read_json(p)
    return {
        "sequence": ["#6699BA", "#CCA8E3", "#8CCF8C", "#B00F1A", "#917ABD", "#6657A6"],
        "fills": ["#B3CDE4", "#CCEAC4", "#FBB4AE", "#DECAE5", "#B0B0B0"],
        "ramps": {},
        "series": {},
    }


def resolve_color(token, palette: dict, idx: int = 0):
    """Resolve #hex, series name, seq:n, fill:n, or ramp:<name>@i."""
    if token is None:
        return palette["sequence"][idx % len(palette["sequence"])]
    if isinstance(token, str) and token.startswith("#"):
        return token
    if isinstance(token, str) and token in palette.get("series", {}):
        return palette["series"][token]
    if isinstance(token, str) and ":" in token:
        kind, rest = token.split(":", 1)
        if kind == "ramp" and "@" in rest:
            rname, ridx = rest.split("@", 1)
            arr = palette.get("ramps", {}).get(rname, [])
            if arr:
                return arr[int(ridx) % len(arr)]
        try:
            n = int(rest)
        except ValueError:
            n = idx
        if kind == "seq":
            return palette["sequence"][n % len(palette["sequence"])]
        if kind == "fill":
            fills = palette.get("fills", palette["sequence"])
            return fills[n % len(fills)]
    return palette["sequence"][idx % len(palette["sequence"])]


_CHEM_REPLACEMENTS = [
    (r"\b([A-Z][a-z]?)(\d+(?:\.\d+)?)-([A-Z]{2,5})\b", r"\1$_{\2}$-\3"),
    (r"\bCu2\+", r"Cu$^{2+}$"),
    (r"\bCu\+", r"Cu$^+$"),
    (r"\b27Al\b", r"$^{27}$Al"),
    (r"\b29Si\b", r"$^{29}$Si"),
    (r"\bNOx\b", r"NO$_x$"),
    (r"\bN2O\b", r"N$_2$O"),
    (r"\bNO2\b", r"NO$_2$"),
    (r"\bSO2\b", r"SO$_2$"),
    (r"\bNH3\b", r"NH$_3$"),
    (r"\bCO2\b", r"CO$_2$"),
    (r"\bH2O\b", r"H$_2$O"),
    (r"\bN2\b", r"N$_2$"),
    (r"\bH2\b", r"H$_2$"),
    (r"\bO2\b", r"O$_2$"),
    (r"cm\^-1", r"cm$^{-1}$"),
    (r"h\^-1", r"h$^{-1}$"),
    (r"cm3/g", r"cm$^3$/g"),
    (r"m2/g", r"m$^2$/g"),
    (r"g_//", r"g$_{//}$"),
    (r"A_//", r"A$_{//}$"),
    (r"g_perp", r"g$_\\perp$"),
]


def chem_mathtext(text: str) -> str:
    """Convert plain chemistry notation into clean matplotlib mathtext without changing existing $...$ spans."""
    if not text or "$" in text:
        return text
    out = str(text)
    for pat, rep in _CHEM_REPLACEMENTS:
        out = re.sub(pat, rep, out)
    return out


def apply_mpl(theme: dict) -> None:
    fam = theme["font"]["family"]
    weight = theme["font"].get("weight", "bold")
    is_sans = any(k in fam.lower() for k in ("arial", "helvetica", "sans", "calibri", "segoe"))
    is_bold = str(weight).lower() in ("bold", "700", "800", "900")
    mt_main = f"{fam}:bold" if is_bold else fam
    mt_it = f"{fam}:bold:italic" if is_bold else f"{fam}:italic"
    mpl.rcParams.update({
        "font.family": "sans-serif" if is_sans else "serif",
        "font.sans-serif": [fam, "Arial", "DejaVu Sans"],
        "font.serif": [fam, "Times New Roman", "Nimbus Roman", "DejaVu Serif"],
        "font.weight": weight,
        "mathtext.fontset": "custom",
        "mathtext.fallback": "stix",
        "mathtext.rm": mt_main,
        "mathtext.bf": f"{fam}:bold",
        "mathtext.it": mt_it,
        "mathtext.default": "bf" if is_bold else "rm",
        "axes.unicode_minus": False,
        "axes.linewidth": theme["spines"]["lw"],
        "axes.labelweight": weight,
        "axes.labelsize": theme["size"]["label"],
        "axes.titlesize": theme["size"]["label"],
        "xtick.labelsize": theme["size"]["tick"],
        "ytick.labelsize": theme["size"]["tick"],
        "legend.fontsize": theme["size"]["legend"],
        "legend.frameon": theme.get("legend", {}).get("frameon", False),
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
