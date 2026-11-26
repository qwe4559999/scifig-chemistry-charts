"""Build purely synthetic atomic visual element swatches and golden chart-type previews.

Generates inside 14_SciFigStudio_20261126/assets/:
  - elements/01_axis-frames.{png,svg} .. 12_broken-axis.{png,svg}
  - elements_wall.png (3x4 grid @ 300 dpi)
  - charts/01_line-marker-eval/preview.{png,svg} .. 09_microscopy-montage/preview.{png,svg}
  - gallery_wall.png (3x3 grid @ 300 dpi)

100% synthetic mathematical data (NumPy/SciPy) with generic labels (Catalyst-A/B/C,
Sample-1..4, Species-1..4, Map-X/Y/Z). Zero external/unpublished data files read.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle
from PIL import Image, ImageDraw, ImageFont

from . import engine, theme as theme_mod

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
ELEMENTS_DIR = ASSETS_DIR / "elements"
CHARTS_DIR = ASSETS_DIR / "charts"


# ---------------------------------------------------------------- helpers
def _init_theme():
    th = theme_mod.load_theme("origin-times-bold")
    theme_mod.apply_mpl(th)
    pal = theme_mod.load_palette("publication-pastel")
    return th, pal


def _save_fig(fig: plt.Figure, stem: Path, dpi: int = 300):
    stem.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(
            stem.with_suffix(f".{ext}"),
            dpi=dpi,
            format=ext,
            bbox_inches=None,
            pad_inches=0,
            facecolor="white",
        )
    plt.close(fig)


def _new_card(title: str, w_in: float = 3.6, h_in: float = 2.55) -> plt.Figure:
    fig = plt.figure(figsize=(w_in, h_in), dpi=100, facecolor="white")
    fig.text(
        0.04, 0.955, title,
        ha="left", va="top", fontsize=10.0, fontweight="bold",
        color="#0F2942", family="Arial",
    )
    return fig


def _style_mini_ax(ax, lw: float = 1.55, ticks_in: bool = True, box: bool = True):
    ax.tick_params(
        axis="both", which="major",
        direction="in" if ticks_in else "out",
        length=3.6, width=lw, pad=2.8, labelsize=8.5, colors="black",
    )
    ax.tick_params(
        axis="both", which="minor",
        direction="in" if ticks_in else "out",
        length=2.0, width=lw * 0.75, colors="black",
    )
    for k, sp in ax.spines.items():
        sp.set_linewidth(lw)
        sp.set_color("black")
        if not box and k in ("top", "right"):
            sp.set_visible(False)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_fontweight("bold")


# ---------------------------------------------------------------- 12 atomic elements
def build_elements(th: dict, pal: dict) -> list[Path]:
    ELEMENTS_DIR.mkdir(parents=True, exist_ok=True)
    out_pngs: list[Path] = []
    x = np.linspace(0, 10, 200)
    y_gauss = np.exp(-((x - 5.0) / 1.1) ** 2)

    # 01_axis-frames
    fig = _new_card("01 | Axis Frames: Box / L-Shape / Seamless Stack")
    rects = [[0.06, 0.16, 0.25, 0.60], [0.38, 0.16, 0.25, 0.60]]
    titles = ["Box (1.55 pt)", "L-Shape (Open)"]
    for rct, ttl, bx in zip(rects, titles, (True, False)):
        ax = fig.add_axes(rct)
        _style_mini_ax(ax, lw=1.55, box=bx)
        ax.plot(x, y_gauss, lw=1.55, color="#6699BA")
        ax.set_xticks([0, 5, 10])
        ax.set_yticks([])
        ax.set_title(ttl, fontsize=8.5, fontweight="bold", pad=5)
    # Seamless 2-layer stack
    for k, col in enumerate(("#CCA8E3", "#8CCF8C")):
        ax = fig.add_axes([0.70, 0.16 + k * 0.30, 0.25, 0.30])
        _style_mini_ax(ax, lw=1.55, box=True)
        ax.plot(x, y_gauss, lw=1.4, color=col)
        ax.set_ylim(-0.08, 1.18)
        ax.set_yticks([])
        if k == 1:
            ax.spines["bottom"].set_linewidth(1.0)
            ax.tick_params(bottom=False, labelbottom=False)
            ax.set_title("Stack (hspace=0)", fontsize=8.5, fontweight="bold", pad=5)
        else:
            ax.spines["top"].set_visible(False)
            ax.set_xticks([0, 5, 10])
    stem = ELEMENTS_DIR / "01_axis-frames"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 02_ticks
    fig = _new_card("02 | Ticks: Inward Major/Minor & Reverse Axis")
    ax1 = fig.add_axes([0.10, 0.52, 0.82, 0.24])
    _style_mini_ax(ax1, lw=1.55, ticks_in=True)
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 1)
    ax1.set_xticks([0, 25, 50, 75, 100])
    ax1.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(5))
    ax1.set_yticks([])
    ax1.text(0.5, 0.55, "Inward Major (3.6 pt) + Minor (2.0 pt)", transform=ax1.transAxes,
             ha="center", va="center", fontsize=8.8, fontweight="bold")
    ax2 = fig.add_axes([0.10, 0.14, 0.82, 0.24])
    _style_mini_ax(ax2, lw=1.55, ticks_in=True)
    ax2.set_xlim(3800, 800)
    ax2.set_ylim(0, 1)
    ax2.set_xticks([3800, 3000, 2200, 1400, 800])
    ax2.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(200))
    ax2.set_yticks([])
    ax2.text(0.5, 0.55, "Reverse Axis: 3800 → 800 cm$^{-1}$", transform=ax2.transAxes,
             ha="center", va="center", fontsize=8.8, fontweight="bold")
    stem = ELEMENTS_DIR / "02_ticks"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 03_markers
    fig = _new_card("03 | Markers: Solid vs Hollow Symbols")
    ax = fig.add_axes([0.06, 0.12, 0.88, 0.72])
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.4)
    specs_m = [
        ("o", "#6699BA", "Circle (o) — Solid", True),
        ("s", "#CCA8E3", "Square (s) — Hollow", False),
        ("^", "#8CCF8C", "Triangle (^) — Solid", True),
        ("D", "#B00F1A", "Diamond (D) — Hollow", False),
    ]
    for i, (mk, col, lbl, solid) in enumerate(specs_m):
        yy = 3.6 - i * 0.92
        xs_m = np.linspace(0.6, 3.6, 5)
        ys_m = np.full_like(xs_m, yy)
        ax.plot(
            xs_m, ys_m, ls="-", lw=1.55, color=col,
            marker=mk, ms=6.2, mew=1.4,
            mfc=col if solid else "white", mec=col,
        )
        ax.text(4.1, yy, lbl, ha="left", va="center", fontsize=9.2, fontweight="bold")
    stem = ELEMENTS_DIR / "03_markers"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 04_line-styles
    fig = _new_card("04 | Line Styles & Measured Widths")
    ax = fig.add_axes([0.06, 0.12, 0.88, 0.72])
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.8)
    litems = [
        (3.0, "-", 1.55, "#6699BA", "Standard Data Curve — 1.55 pt"),
        (2.0, "-", 0.80, "#6657A6", "DRIFTS / Fit Curve — 0.80 pt"),
        (1.0, "--", 0.80, "#000000", "Dashed Peak Guide — 0.80 pt"),
    ]
    for yy, ls, lw, col, lbl in litems:
        ax.plot([0.5, 3.4], [yy, yy], ls=ls, lw=lw, color=col)
        ax.text(3.8, yy, lbl, ha="left", va="center", fontsize=9.0, fontweight="bold")
    stem = ELEMENTS_DIR / "04_line-styles"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 05_legend-forms
    fig = _new_card("05 | Legend Forms: Note-Attached & Top Gradient")
    axL = fig.add_axes([0.06, 0.14, 0.43, 0.66])
    _style_mini_ax(axL, lw=1.35)
    axL.set_xticks([]); axL.set_yticks([])
    axL.set_title("Frame-Off + Note", fontsize=8.5, fontweight="bold", pad=4)
    for col, lbl in [("#6699BA", "Catalyst-A"), ("#CCA8E3", "Catalyst-B"), ("#8CCF8C", "Catalyst-C")]:
        axL.plot([], [], lw=1.55, marker="o", ms=4.5, color=col, label=lbl)
    engine._add_legend(
        axL, axL.get_legend_handles_labels()[0],
        {"loc": "center", "fontsize": 8.0, "note": "GHSV = 50,000 h$^{-1}$", "note_fontsize": 7.8},
        th, pal,
    )
    axR = fig.add_axes([0.53, 0.14, 0.42, 0.66])
    _style_mini_ax(axR, lw=1.35)
    axR.set_xticks([]); axR.set_yticks([])
    axR.set_title("Top Horizontal Gradient", fontsize=8.5, fontweight="bold", pad=4)
    proxies = [
        {"label": f"S{i+1}", "color": f"fill:{i}", "patch": True, "gradient": True}
        for i in range(4)
    ]
    engine._add_legend(
        axR, [],
        {"loc": "center", "ncol": 2, "fontsize": 8.2, "columnspacing": 0.9, "proxies": proxies},
        th, pal,
    )
    stem = ELEMENTS_DIR / "05_legend-forms"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 06_peak-annotations
    fig = _new_card("06 | Peak Guides & EPR Hyperfine Comb Bracket")
    ax = fig.add_axes([0.09, 0.17, 0.85, 0.64])
    _style_mini_ax(ax, lw=1.4)
    xf = np.linspace(2300, 3600, 400)
    # Synthetic derivative EPR-like quartet + perp feature
    yf = np.zeros_like(xf)
    for xp in (2560, 2650, 2740, 2830):
        yf += 0.25 * np.exp(-((xf - xp) / 22.0) ** 2)
    yf += -1.0 * ((xf - 3280) / 45.0) * np.exp(-((xf - 3280) / 45.0) ** 2)
    ax.plot(xf, yf, lw=1.55, color="#6699BA")
    ax.axvline(3280, ymin=0.0, ymax=0.78, ls="--", lw=0.8, color="black")
    ax.text(3280, 0.58, "3280", ha="center", va="bottom", fontsize=7.8, fontweight="bold")
    engine._plot(ax, {}, {
        "type": "comb", "x_positions": [2560, 2650, 2740, 2830],
        "y_base": 0.36, "y_top": 0.54, "lw": 1.1,
        "label": "g$_{//}$=2.38  A$_{//}$=149 G", "label_dy": 0.04, "label_size": 7.8,
    }, th, pal, 0)
    ax.set_xlim(2300, 3600)
    ax.set_ylim(-0.65, 0.86)
    ax.set_yticks([])
    ax.set_xlabel("Field / Shift", fontsize=9.0, fontweight="bold", labelpad=2)
    stem = ELEMENTS_DIR / "06_peak-annotations"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 07_panel-letters
    fig = _new_card("07 | Panel Letters: Outside Top-Left (14.1 pt Bold)")
    for idx, (r, c, ltr) in enumerate([(0, 0, "A"), (0, 1, "B"), (1, 0, "C"), (1, 1, "D")]):
        ax = fig.add_axes([0.11 + c * 0.46, 0.51 - r * 0.39, 0.36, 0.28])
        _style_mini_ax(ax, lw=1.35)
        ax.plot([0, 1], [0.2, 0.92], lw=1.5, color=pal["sequence"][idx])
        ax.set_ylim(0, 1.02)
        ax.set_xticks([]); ax.set_yticks([])
        ax.text(-0.20, 0.94, ltr, transform=ax.transAxes, fontsize=13.5, fontweight="bold", ha="left", va="bottom")
    stem = ELEMENTS_DIR / "07_panel-letters"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 08_semantic-palette
    fig = _new_card("08 | Semantic Palette: Series & Deconv Fills")
    ax = fig.add_axes([0.04, 0.08, 0.92, 0.78])
    ax.axis("off")
    ax.set_xlim(0, 4.0)
    ax.set_ylim(0, 2.5)
    series_items = [
        ("Series-1", "#B00F1A"),
        ("Series-2", "#6699BA"),
        ("Series-3", "#CCA8E3"),
        ("Series-4", "#8CCF8C"),
    ]
    fill_items = [
        ("Fill-1", "#B3CDE4"),
        ("Fill-2", "#CCEAC4"),
        ("Fill-3", "#FBB4AE"),
        ("Fill-4", "#DECAE5"),
    ]
    for col_idx, (lbl, hx) in enumerate(series_items):
        x0 = col_idx * 0.98 + 0.08
        ax.add_patch(FancyBboxPatch((x0, 1.50), 0.82, 0.56, boxstyle="round,pad=0.02,rounding_size=0.06",
                                    facecolor=hx, edgecolor="#222222", lw=0.8))
        ax.text(x0 + 0.41, 1.32, f"{lbl}\n{hx}", ha="center", va="top", fontsize=7.5, fontweight="bold")
    for col_idx, (lbl, hx) in enumerate(fill_items):
        x0 = col_idx * 0.98 + 0.08
        ax.add_patch(FancyBboxPatch((x0, 0.48), 0.82, 0.56, boxstyle="round,pad=0.02,rounding_size=0.06",
                                    facecolor=hx, edgecolor="#222222", lw=0.8))
        ax.text(x0 + 0.41, 0.30, f"{lbl}\n{hx}", ha="center", va="top", fontsize=7.5, fontweight="bold")
    stem = ELEMENTS_DIR / "08_semantic-palette"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 09_sequential-ramps
    fig = _new_card("09 | Sequential Ramps: GHSV & 12-Step DRIFTS")
    ax = fig.add_axes([0.05, 0.10, 0.90, 0.74])
    ax.axis("off")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 3.6)
    ramps = [
        ("Purple GHSV (3-step)", pal["ramps"]["ghsv_purple"], 2.75),
        ("Blue Comparison (3-step)", pal["ramps"]["cha_ghsv"], 1.70),
        ("DRIFTS Time Ramp (12-step)", pal["ramps"]["drifts_12"], 0.65),
    ]
    for title_r, cols_r, y0 in ramps:
        ax.text(0.1, y0 + 0.50, title_r, ha="left", va="bottom", fontsize=8.4, fontweight="bold")
        w_cell = 11.4 / len(cols_r)
        for j, hx in enumerate(cols_r):
            ax.add_patch(Rectangle((0.1 + j * w_cell, y0), w_cell * 0.92, 0.42, facecolor=hx, edgecolor="#222222", lw=0.6))
    stem = ELEMENTS_DIR / "09_sequential-ramps"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 10_gradient-fills
    fig = _new_card("10 | Vertical Alpha Gradient: Peak & Bar")
    ax1 = fig.add_axes([0.07, 0.15, 0.42, 0.66])
    _style_mini_ax(ax1, lw=1.4)
    xg = np.linspace(0, 10, 200)
    yg1 = 0.85 * np.exp(-((xg - 3.6) / 1.1) ** 2)
    yg2 = 0.72 * np.exp(-((xg - 6.6) / 1.2) ** 2)
    engine._gradient_fill(ax1, xg, yg1, 0.0, "#B3CDE4", 0.90, 2)
    engine._gradient_fill(ax1, xg, yg2, 0.0, "#FBB4AE", 0.90, 2.1)
    ax1.plot(xg, yg1 + yg2, lw=1.1, color="#555555")
    ax1.set_xlim(0, 10); ax1.set_ylim(0, 1.05)
    ax1.set_xticks([]); ax1.set_yticks([])
    ax1.set_title("Deconv Peak", fontsize=8.4, fontweight="bold", pad=4)

    ax2 = fig.add_axes([0.55, 0.15, 0.39, 0.66])
    _style_mini_ax(ax2, lw=1.4)
    for b_idx, (c_bar, ylo, h_bar) in enumerate([("#B3CDE4", 0, 35), ("#CCEAC4", 35, 40), ("#FBB4AE", 75, 25)]):
        grad = np.linspace(0, 1, 64).reshape(-1, 1)
        rgb = np.array(matplotlib.colors.to_rgb(c_bar))
        img = np.ones((64, 2, 3))
        for ch in range(3):
            img[:, :, ch] = 1.0 - (1.0 - rgb[ch]) * (0.12 + 0.88 * grad)
        ax2.imshow(img, extent=[0.25, 0.75, ylo, ylo + h_bar], origin="lower", aspect="auto", zorder=2)
        ax2.add_patch(Rectangle((0.25, ylo), 0.50, h_bar, fill=False, edgecolor="black", lw=0.6, zorder=3))
        ax2.text(0.50, ylo + h_bar / 2, f"{h_bar}%", ha="center", va="center", fontsize=8.0, fontweight="bold", zorder=4)
    ax2.set_xlim(0, 1); ax2.set_ylim(0, 105)
    ax2.set_xticks([]); ax2.set_yticks([])
    ax2.set_title("Stacked Bar", fontsize=8.4, fontweight="bold", pad=4)
    stem = ELEMENTS_DIR / "10_gradient-fills"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 11_typography
    fig = _new_card("11 | Typography: Times Bold (14.1/10.2/7.0) vs Arial")
    ax = fig.add_axes([0.05, 0.08, 0.90, 0.76])
    ax.axis("off")
    ax.set_xlim(0, 10); ax.set_ylim(0, 4.0)
    ax.text(0.2, 3.35, "Axis Label — 14.1 pt Bold", fontsize=12.0, fontweight="bold", family="Times New Roman")
    ax.text(0.2, 2.35, "Ticks / Legend — 10.2 pt Bold", fontsize=10.2, fontweight="bold", family="Times New Roman")
    ax.text(0.2, 1.45, "Sub/Superscript (7.0 pt): N$_2$O  50,000 h$^{-1}$  $^{27}$Al  Cu$^{2+}$",
            fontsize=8.3, fontweight="bold", family="Times New Roman")
    ax.text(0.2, 0.55, "Nature Sans (Arial 8.5 / 7.5 pt): Catalyst-A  cm$^{-1}$",
            fontsize=8.3, fontweight="normal", family="Arial")
    stem = ELEMENTS_DIR / "11_typography"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    # 12_broken-axis
    fig = _new_card("12 | Broken X-Axis: Custom Weights & // Slashes")
    segs = [[3800, 3400, 4.0], [1900, 800, 11.0]]
    L, B, W, H = 0.08, 0.20, 0.86, 0.58
    gapw = 0.022
    wts = [s[2] for s in segs]
    avail = W - gapw
    ws = [avail * wt / sum(wts) for wt in wts]
    xs_r = [L, L + ws[0] + gapw]
    for si, (x0, x1, _w) in enumerate(segs):
        srect = [xs_r[si], B, ws[si], H]
        ax = fig.add_axes(srect)
        _style_mini_ax(ax, lw=1.4)
        xv = np.linspace(x1, x0, 200)
        yv = 0.75 * np.exp(-((xv - 3650) / 35) ** 2) + 0.85 * np.exp(-((xv - 1620) / 50) ** 2)
        ax.plot(xv, yv, lw=1.0, color="#6657A6")
        ax.set_xlim(x0, x1); ax.set_ylim(-0.08, 1.1)
        ax.set_yticks([])
        if si == 0:
            ax.set_xticks([3800, 3600])
            ax.spines["right"].set_visible(False)
            engine._draw_segment_slash(ax, srect, fig, "right", th)
        else:
            ax.set_xticks([1800, 1400, 1000])
            ax.tick_params(left=False, labelleft=False)
            ax.spines["left"].set_visible(False)
            engine._draw_segment_slash(ax, srect, fig, "left", th)
    fig.text(L + W / 2, 0.05, "Wavenumber (cm$^{-1}$)", ha="center", va="bottom", fontsize=9.2, fontweight="bold")
    stem = ELEMENTS_DIR / "12_broken-axis"
    _save_fig(fig, stem)
    out_pngs.append(stem.with_suffix(".png"))

    _build_wall(out_pngs, ASSETS_DIR / "elements_wall.png", cols=4, rows=3,
                banner="SciFigStudio — 12 Atomic Visual Elements (100% Synthetic)")
    return out_pngs


# ---------------------------------------------------------------- 9 golden chart previews
def _write_synthetic_data(tmp: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}

    # 01: catalytic conversion sigmoid
    t = np.array([150, 175, 200, 250, 300, 350, 400, 450, 500, 550], dtype=float)
    c_a = 100.0 / (1.0 + np.exp(-(t - 235.0) / 26.0))
    c_b = 100.0 / (1.0 + np.exp(-(t - 205.0) / 24.0))
    c_c = 100.0 / (1.0 + np.exp(-(t - 185.0) / 22.0))
    p1 = tmp / "eval.csv"
    pd.DataFrame({"Temperature": t, "Catalyst-A": c_a, "Catalyst-B": c_b, "Catalyst-C": c_c}).to_csv(p1, index=False)
    paths["eval"] = p1

    # 02: XRD Lorentzian peaks
    tt = np.linspace(5.0, 40.0, 701)
    def lor(x, x0, g, a):
        return a * (g ** 2) / ((x - x0) ** 2 + g ** 2)
    peaks = [(8.4, 0.24, 0.9), (14.2, 0.25, 0.45), (19.6, 0.28, 0.6), (25.1, 0.24, 1.0), (29.8, 0.30, 0.72)]
    df_xrd = pd.DataFrame({"two_theta": tt})
    for idx, name in enumerate(["Sample-1", "Sample-2", "Sample-3", "Sample-4"]):
        y = np.zeros_like(tt)
        for p0, g, amp in peaks:
            y += lor(tt, p0 + idx * 0.04, g, amp * (1.0 - 0.08 * idx))
        y += 0.03 * np.exp(-tt / 20.0)
        df_xrd[name] = y / y.max()
    p2 = tmp / "xrd.csv"
    df_xrd.to_csv(p2, index=False)
    paths["xrd"] = p2

    # 03: Type-IV N2 physisorption isotherm with hysteresis
    pr_ads = np.linspace(0.01, 0.99, 45)
    ads1 = 85.0 * (pr_ads ** 0.12) / (1.0 + 0.25 * (1 - pr_ads)) + 65.0 / (1.0 + np.exp(-(pr_ads - 0.72) / 0.055))
    pr_des = np.linspace(0.99, 0.05, 42)
    des1 = 85.0 * (pr_des ** 0.12) / (1.0 + 0.25 * (1 - pr_des)) + 65.0 / (1.0 + np.exp(-(pr_des - 0.54) / 0.055))
    ads2 = ads1 * 0.72 + 12.0
    des2 = des1 * 0.72 + 12.0
    p3 = tmp / "iso.csv"
    pd.DataFrame({
        "p_ads": pd.Series(pr_ads), "v_ads1": pd.Series(ads1), "v_ads2": pd.Series(ads2),
        "p_des": pd.Series(pr_des), "v_des1": pd.Series(des1), "v_des2": pd.Series(des2),
    }).to_csv(p3, index=False)
    paths["iso"] = p3

    # 04: 3-sample deconvolution (4 Gaussians each)
    t_tpd = np.linspace(100, 700, 301)
    centers = [175.0, 265.0, 440.0, 575.0]
    widths = [32.0, 40.0, 52.0, 45.0]
    amps_list = [[0.45, 0.75, 0.35, 0.25], [0.35, 0.55, 0.65, 0.45], [0.28, 0.40, 0.72, 0.62]]
    for idx, amps in enumerate(amps_list):
        d = {"x": t_tpd}
        tot = np.zeros_like(t_tpd)
        for k, (c0, w0, a0) in enumerate(zip(centers, widths, amps), start=1):
            pk = a0 * np.exp(-0.5 * ((t_tpd - c0) / w0) ** 2)
            d[f"p{k}"] = pk
            tot += pk
        d["fit"] = tot
        d["obs"] = tot + 0.015 * np.sin(t_tpd / 9.0) * tot
        pk_p = tmp / f"deconv_{idx+1}.csv"
        pd.DataFrame(d).to_csv(pk_p, index=False)
        paths[f"deconv_{idx+1}"] = pk_p

    # 05: 100% stacked bar
    p5 = tmp / "bar.csv"
    pd.DataFrame({
        "sample": ["Sample-1", "Sample-2", "Sample-3", "Sample-4"],
        "S1": [42, 34, 24, 18],
        "S2": [28, 31, 33, 27],
        "S3": [18, 22, 27, 33],
        "S4": [12, 13, 16, 22],
    }).to_csv(p5, index=False)
    paths["bar"] = p5

    # 06: UV-Vis 3 spectra
    wl = np.linspace(200, 800, 301)
    df_uv = pd.DataFrame({"wl": wl})
    for idx, (name, a215, a265, a710) in enumerate([
        ("Catalyst-A", 0.55, 0.35, 0.14),
        ("Catalyst-B", 0.72, 0.52, 0.26),
        ("Catalyst-C", 0.88, 0.66, 0.38),
    ]):
        y = (
            a215 * np.exp(-0.5 * ((wl - 215.0) / 14.0) ** 2)
            + a265 * np.exp(-0.5 * ((wl - 265.0) / 28.0) ** 2)
            + a710 * np.exp(-0.5 * ((wl - 710.0) / 68.0) ** 2)
        )
        df_uv[name] = y
    p6 = tmp / "uv.csv"
    df_uv.to_csv(p6, index=False)
    paths["uv"] = p6

    # 07: DRIFTS 10-curve broken-axis IR time series
    wn_hi = np.linspace(3800, 3400, 121)
    wn_lo = np.linspace(1900, 800, 331)
    wn = np.concatenate([wn_hi, wn_lo])
    df_ir = pd.DataFrame({"wn": wn})
    for k in range(10):
        frac = (k + 1) / 10.0
        if k == 9:
            frac = 0.82  # purge slightly lower
        y = (
            -0.38 * frac * np.exp(-0.5 * ((wn - 3650.0) / 16.0) ** 2)
            + 0.78 * frac * np.exp(-0.5 * ((wn - 1620.0) / 22.0) ** 2)
            + 0.62 * frac * np.exp(-0.5 * ((wn - 1460.0) / 25.0) ** 2)
            + 0.45 * frac * np.exp(-0.5 * ((wn - 1230.0) / 28.0) ** 2)
        )
        df_ir[f"t{k}"] = y
    p7 = tmp / "drifts.csv"
    df_ir.to_csv(p7, index=False)
    paths["drifts"] = p7

    # 08: XPS reverse BE 948->928 eV
    be = np.linspace(948.0, 928.0, 201)
    for idx, (s1_a, s2_a, sat_a) in enumerate([(0.32, 0.72, 0.28), (0.48, 0.62, 0.24), (0.65, 0.50, 0.18)]):
        p_cu1 = s1_a * np.exp(-0.5 * ((be - 932.6) / 0.85) ** 2)
        p_cu2 = s2_a * np.exp(-0.5 * ((be - 935.2) / 1.10) ** 2)
        p_sat = sat_a * np.exp(-0.5 * ((be - 943.4) / 1.85) ** 2)
        env = p_cu1 + p_cu2 + p_sat
        obs = env + 0.015 * np.cos(be * 2.5)
        px = tmp / f"xps_{idx+1}.csv"
        pd.DataFrame({"be": be, "obs": obs, "fit": env, "c1": p_cu1, "c2": p_cu2, "c3": p_sat}).to_csv(px, index=False)
        paths[f"xps_{idx+1}"] = px

    # 09: Synthetic nanoparticle BF + 3 elemental maps
    rng = np.random.default_rng(42)
    sz = 240
    yy, xx = np.mgrid[0:sz, 0:sz]
    mask = np.zeros((sz, sz), dtype=float)
    for cx, cy, rad in [(75, 85, 34), (130, 115, 42), (168, 82, 28), (112, 168, 36), (162, 160, 24)]:
        d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (rad ** 2)
        mask += np.exp(-d2 * 1.8)
    mask = np.clip(mask, 0.0, 1.0)
    bf = np.clip(215 - 145 * mask + rng.normal(0, 11, (sz, sz)), 15, 245).astype(np.uint8)
    Image.fromarray(bf, mode="L").save(tmp / "bf.png")

    def _map_img(col_rgb, strength):
        arr = np.zeros((sz, sz, 3), dtype=float)
        signal = np.clip(0.12 + strength * mask + rng.normal(0, 0.09, (sz, sz)), 0.0, 1.0)
        for ch in range(3):
            arr[..., ch] = signal * col_rgb[ch]
        return np.clip(arr * 255, 0, 255).astype(np.uint8)

    Image.fromarray(_map_img((0.25, 0.72, 0.96), 0.82)).save(tmp / "map_x.png")
    Image.fromarray(_map_img((0.96, 0.48, 0.25), 0.76)).save(tmp / "map_y.png")
    Image.fromarray(_map_img((0.35, 0.88, 0.52), 0.85)).save(tmp / "map_z.png")
    paths["bf"] = tmp / "bf.png"
    paths["map_x"] = tmp / "map_x.png"
    paths["map_y"] = tmp / "map_y.png"
    paths["map_z"] = tmp / "map_z.png"
    return paths


def _render_spec_dict(spec: dict, stem: Path, tmp: Path):
    sp = tmp / f"{stem.parent.name}.json"
    sp.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    loaded = engine.load_spec(sp)
    fig = engine.build(loaded)
    _save_fig(fig, stem, dpi=300)


def build_gallery(th: dict, pal: dict) -> list[Path]:
    out_pngs: list[Path] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _write_synthetic_data(tmp)

        # 01_line-marker-eval
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d": str(p["eval"])},
            "panels": [{
                "id": "A", "rect": [0.18, 0.18, 0.77, 0.74],
                "letter": {"text": "A", "x": -0.20, "y": 0.94},
                "x": {"label": "Temperature (°C)", "lim": [140, 560], "ticks": [150, 250, 350, 450, 550]},
                "y": {"label": "Conversion (%)", "lim": [0, 104], "ticks": [0, 20, 40, 60, 80, 100]},
                "plots": [
                    {"type": "line_marker", "data": "d", "x": "Temperature", "y": "Catalyst-A", "color": "#6699BA", "marker": "o", "ms": 5.0, "label": "Catalyst-A"},
                    {"type": "line_marker", "data": "d", "x": "Temperature", "y": "Catalyst-B", "color": "#CCA8E3", "marker": "D", "ms": 4.8, "label": "Catalyst-B"},
                    {"type": "line_marker", "data": "d", "x": "Temperature", "y": "Catalyst-C", "color": "#8CCF8C", "marker": "^", "ms": 5.2, "label": "Catalyst-C"},
                ],
                "legend": {"loc": "lower right", "fontsize": 9.5, "note": "GHSV = 50,000 h$^{-1}$", "note_fontsize": 9.0},
            }],
        }, CHARTS_DIR / "01_line-marker-eval" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "01_line-marker-eval" / "preview.png")

        # 02_stacked-spectra
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d": str(p["xrd"])},
            "panels": [{
                "id": "A", "rect": [0.14, 0.18, 0.81, 0.74],
                "letter": {"text": "A", "x": -0.15, "y": 0.94},
                "x": {"label": "2θ (degree)", "lim": [5, 45], "ticks": [10, 20, 30, 40]},
                "y": {"label": "Intensity (a.u.)", "lim": [-0.1, 4.6], "ticks": []},
                "plots": [
                    {"type": "line", "data": "d", "x": "two_theta", "y": "Sample-1", "color": "#B00F1A", "offset": 0.0},
                    {"type": "line", "data": "d", "x": "two_theta", "y": "Sample-2", "color": "#6699BA", "offset": 1.15},
                    {"type": "line", "data": "d", "x": "two_theta", "y": "Sample-3", "color": "#CCA8E3", "offset": 2.30},
                    {"type": "line", "data": "d", "x": "two_theta", "y": "Sample-4", "color": "#8CCF8C", "offset": 3.45},
                    {"type": "text", "xy": [44.2, 0.12], "text": "Sample-1", "ha": "right", "va": "bottom", "size": 9.0, "color": "#B00F1A"},
                    {"type": "text", "xy": [44.2, 1.27], "text": "Sample-2", "ha": "right", "va": "bottom", "size": 9.0, "color": "#6699BA"},
                    {"type": "text", "xy": [44.2, 2.42], "text": "Sample-3", "ha": "right", "va": "bottom", "size": 9.0, "color": "#8E5FB5"},
                    {"type": "text", "xy": [44.2, 3.57], "text": "Sample-4", "ha": "right", "va": "bottom", "size": 9.0, "color": "#4A9E4A"},
                ],
            }],
        }, CHARTS_DIR / "02_stacked-spectra" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "02_stacked-spectra" / "preview.png")

        # 03_isotherm-psd
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d": str(p["iso"])},
            "panels": [{
                "id": "B", "rect": [0.18, 0.18, 0.77, 0.74],
                "letter": {"text": "B", "x": -0.20, "y": 0.94},
                "x": {"label": "Relative Pressure (P/P$_0$)", "lim": [-0.03, 1.03], "ticks": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]},
                "y": {"label": "Quantity Adsorbed (cm$^3$/g)", "lim": [0, 175], "ticks": [0, 50, 100, 150]},
                "plots": [
                    {"type": "line_marker", "data": "d", "x": "p_ads", "y": "v_ads1", "color": "#6699BA", "marker": "o", "ms": 4.0, "markevery": 2, "label": "Sample-1 (Ads.)"},
                    {"type": "line_marker", "data": "d", "x": "p_des", "y": "v_des1", "color": "#6699BA", "marker": "o", "mfc": "white", "ms": 4.0, "markevery": 2, "label": "Sample-1 (Des.)"},
                    {"type": "line_marker", "data": "d", "x": "p_ads", "y": "v_ads2", "color": "#CCA8E3", "marker": "s", "ms": 3.8, "markevery": 2, "label": "Sample-2 (Ads.)"},
                    {"type": "line_marker", "data": "d", "x": "p_des", "y": "v_des2", "color": "#CCA8E3", "marker": "s", "mfc": "white", "ms": 3.8, "markevery": 2, "label": "Sample-2 (Des.)"},
                ],
                "legend": {"loc": "upper left", "fontsize": 8.4},
            }],
        }, CHARTS_DIR / "03_isotherm-psd" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "03_isotherm-psd" / "preview.png")

        # 04_deconv-peak-fit
        def _deconv_sub(dkey, col_obs, lbl, lbl_xy=None):
            s_lbl = {"text": lbl, "loc": "upper right", "size": 9.0}
            if lbl_xy is not None:
                s_lbl = {"text": lbl, "xy": lbl_xy, "ha": "right", "va": "center", "size": 9.0}
            return {
                "y": {"lim": [-0.05, 1.18]},
                "sample_label": s_lbl,
                "plots": [
                    {"type": "fill", "data": dkey, "x": "x", "y": "p1", "color": "fill:0", "gradient": True, "alpha": 0.88, "zorder": 1.1},
                    {"type": "fill", "data": dkey, "x": "x", "y": "p2", "color": "fill:1", "gradient": True, "alpha": 0.88, "zorder": 1.2},
                    {"type": "fill", "data": dkey, "x": "x", "y": "p3", "color": "fill:2", "gradient": True, "alpha": 0.88, "zorder": 1.3},
                    {"type": "fill", "data": dkey, "x": "x", "y": "p4", "color": "fill:3", "gradient": True, "alpha": 0.88, "zorder": 1.4},
                    {"type": "line", "data": dkey, "x": "x", "y": "fit", "color": "#9A9A9A", "lw": 0.8, "zorder": 3},
                    {"type": "line", "data": dkey, "x": "x", "y": "obs", "color": col_obs, "lw": 1.45, "zorder": 4},
                ],
            }
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d1": str(p["deconv_1"]), "d2": str(p["deconv_2"]), "d3": str(p["deconv_3"])},
            "panels": [{
                "id": "A", "rect": [0.14, 0.18, 0.81, 0.74],
                "letter": {"text": "A", "x": -0.15, "y": 0.94},
                "x": {"label": "Temperature (°C)", "lim": [100, 700], "ticks": [100, 300, 500, 700]},
                "y": {"label": "TCD Signal (a.u.)", "ticks": []},
                "subpanels": [
                    _deconv_sub("d3", "#8CCF8C", "Sample-3", lbl_xy=[0.97, 0.72]),
                    _deconv_sub("d2", "#CCA8E3", "Sample-2"),
                    _deconv_sub("d1", "#6699BA", "Sample-1"),
                ],
                "plots": [
                    {"type": "text", "subpanel": 0, "xy": [175, 0.92], "text": "S1", "size": 8.0, "va": "bottom"},
                    {"type": "text", "subpanel": 0, "xy": [265, 0.92], "text": "S2", "size": 8.0, "va": "bottom"},
                    {"type": "text", "subpanel": 0, "xy": [440, 0.92], "text": "S3", "size": 8.0, "va": "bottom"},
                    {"type": "text", "subpanel": 0, "xy": [575, 0.92], "text": "S4", "size": 8.0, "va": "bottom"},
                ],
            }],
        }, CHARTS_DIR / "04_deconv-peak-fit" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "04_deconv-peak-fit" / "preview.png")

        # 05_stacked-bar-comp
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d": str(p["bar"])},
            "panels": [{
                "id": "B", "rect": [0.18, 0.22, 0.77, 0.70],
                "letter": {"text": "B", "x": -0.20, "y": 0.94},
                "x": {"label": "", "lim": [-0.55, 3.55]},
                "y": {"label": "Relative Percentage (%)", "lim": [0, 118], "ticks": [0, 20, 40, 60, 80, 100]},
                "plots": [{
                    "type": "bar_stacked", "data": "d", "x": None, "y": ["S1", "S2", "S3", "S4"],
                    "colors": ["fill:0", "fill:1", "fill:2", "fill:3"],
                    "gradient": True, "values": True, "value_size": 8.5,
                    "ticklabels": ["Sample-1", "Sample-2", "Sample-3", "Sample-4"],
                    "tick_size": 9.0, "tick_rotation": 20,
                }],
                "legend": {
                    "loc": "upper center", "ncol": 4, "fontsize": 8.5, "bbox": [0.5, 1.01], "columnspacing": 0.7,
                    "proxies": [{"label": f"S{i+1}", "color": f"fill:{i}", "patch": True, "gradient": True} for i in range(4)],
                },
            }],
        }, CHARTS_DIR / "05_stacked-bar-comp" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "05_stacked-bar-comp" / "preview.png")

        # 06_single-multi-spectrum
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d": str(p["uv"])},
            "panels": [{
                "id": "A", "rect": [0.17, 0.18, 0.78, 0.74],
                "letter": {"text": "A", "x": -0.18, "y": 0.94},
                "x": {"label": "Wavelength (nm)", "lim": [190, 800], "ticks": [200, 350, 500, 650, 800]},
                "y": {"label": "Kubelka-Munk (a.u.)", "lim": [-0.05, 1.92], "ticks": [0.0, 0.5, 1.0, 1.5]},
                "plots": [
                    {"type": "line", "data": "d", "x": "wl", "y": "Catalyst-A", "color": "#6699BA", "offset": 0.0, "label": "Catalyst-A"},
                    {"type": "line", "data": "d", "x": "wl", "y": "Catalyst-B", "color": "#CCA8E3", "offset": 0.35, "label": "Catalyst-B"},
                    {"type": "line", "data": "d", "x": "wl", "y": "Catalyst-C", "color": "#8CCF8C", "offset": 0.70, "label": "Catalyst-C"},
                    {"type": "vline", "x": 215, "ymin": 0.0, "ymax": 0.87, "ls": "--", "lw": 0.8, "color": "black"},
                    {"type": "vline", "x": 265, "ymin": 0.0, "ymax": 0.87, "ls": "--", "lw": 0.8, "color": "black"},
                    {"type": "vline", "x": 710, "ymin": 0.0, "ymax": 0.66, "ls": "--", "lw": 0.8, "color": "black"},
                    {"type": "text", "xy": [215, 1.72], "text": "215", "size": 8.0, "va": "bottom"},
                    {"type": "text", "xy": [280, 1.72], "text": "265", "size": 8.0, "va": "bottom"},
                    {"type": "text", "xy": [710, 1.32], "text": "710", "size": 8.0, "va": "bottom"},
                ],
                "legend": {"loc": "upper right", "fontsize": 8.8},
            }],
        }, CHARTS_DIR / "06_single-multi-spectrum" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "06_single-multi-spectrum" / "preview.png")

        # 07_drifts-broken-stack
        drifts_cols = pal["ramps"]["drifts_12"]
        drifts_plots = []
        time_labels = ["1 min", "3 min", "5 min", "10 min", "15 min", "20 min", "30 min", "45 min", "60 min", "Purge 60m"]
        for k in range(10):
            off = k * 0.22
            drifts_plots.append({
                "type": "line", "data": "d", "x": "wn", "y": f"t{k}",
                "color": drifts_cols[k], "lw": 0.85, "offset": off,
            })
            if k in (0, 3, 6, 8, 9):
                drifts_plots.append({
                    "type": "text", "xy": [815, off + 0.03], "text": time_labels[k],
                    "ha": "right", "va": "bottom", "size": 6.8, "seg": 1,
                })
        for pk, yy_t, sg in [(3650, 2.78, 0), (1620, 2.78, 1), (1460, 2.60, 1), (1230, 2.78, 1)]:
            drifts_plots.append({"type": "vline", "x": pk, "ls": "--", "lw": 0.7, "color": "black", "seg": sg})
            drifts_plots.append({"type": "text", "xy": [pk, yy_t], "text": str(pk), "size": 7.0, "va": "top", "seg": sg})
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"d": str(p["drifts"])},
            "panels": [{
                "id": "A", "rect": [0.14, 0.18, 0.81, 0.74],
                "letter": {"text": "A", "x": -0.15, "y": 0.94},
                "segments": [[3800, 3400, 4.0], [1900, 800, 11.0]],
                "break_gap": 0.025,
                "x": {"label": "Wavenumber (cm$^{-1}$)", "ticks": [3800, 3600, 1800, 1400, 1000]},
                "y": {"label": "Kubelka-Munk (a.u.)", "lim": [-0.38, 2.90], "ticks": []},
                "plots": drifts_plots,
            }],
        }, CHARTS_DIR / "07_drifts-broken-stack" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "07_drifts-broken-stack" / "preview.png")

        # 08_xps-reverse-deconv
        def _xps_sub(dkey, col_obs, lbl):
            return {
                "y": {"lim": [-0.06, 1.15]},
                "sample_label": {"text": lbl, "loc": "upper left", "size": 9.0},
                "plots": [
                    {"type": "fill", "data": dkey, "x": "be", "y": "c1", "color": "fill:0", "gradient": True, "alpha": 0.88, "zorder": 1.1},
                    {"type": "fill", "data": dkey, "x": "be", "y": "c2", "color": "fill:1", "gradient": True, "alpha": 0.88, "zorder": 1.2},
                    {"type": "fill", "data": dkey, "x": "be", "y": "c3", "color": "fill:3", "gradient": True, "alpha": 0.88, "zorder": 1.3},
                    {"type": "line", "data": dkey, "x": "be", "y": "fit", "color": "#9A9A9A", "lw": 0.8, "zorder": 3},
                    {"type": "line", "data": dkey, "x": "be", "y": "obs", "color": col_obs, "lw": 1.45, "zorder": 4},
                ],
            }
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "data": {"x1": str(p["xps_1"]), "x2": str(p["xps_2"]), "x3": str(p["xps_3"])},
            "panels": [{
                "id": "A", "rect": [0.14, 0.18, 0.81, 0.74],
                "letter": {"text": "A", "x": -0.15, "y": 0.94},
                "x": {"label": "Binding Energy (eV)", "lim": [948, 928], "ticks": [945, 940, 935, 930]},
                "y": {"label": "Intensity (a.u.)", "ticks": []},
                "shared_guides": [
                    {"x": 943.4, "label": "Sat.", "size": 8.0, "label_y": 1.03},
                    {"x": 935.2, "label": "Species-2", "size": 7.8, "ha": "right", "label_y": 1.03},
                    {"x": 932.6, "label": "Species-1", "size": 7.8, "ha": "left", "label_y": 1.03},
                ],
                "subpanels": [
                    _xps_sub("x3", "#8CCF8C", "Sample-3"),
                    _xps_sub("x2", "#CCA8E3", "Sample-2"),
                    _xps_sub("x1", "#6699BA", "Sample-1"),
                ],
            }],
        }, CHARTS_DIR / "08_xps-reverse-deconv" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "08_xps-reverse-deconv" / "preview.png")

        # 09_microscopy-montage
        _render_spec_dict({
            "theme": "origin-times-bold", "palette": "publication-pastel",
            "figure": {"width_in": 4.2, "height_in": 3.4},
            "panels": [{
                "id": "A", "type": "image_montage",
                "rect": [0.06, 0.06, 0.88, 0.88],
                "grid": [2, 2], "gap": 0.015, "frame_lw": 0.8,
                "images": [
                    {"source": str(p["bf"]), "letter": {"text": "A", "color": "black", "size": 12.0}, "badge": {"text": "BF", "color": "black", "size": 9.5}, "scale_bar": {"frac": 0.24, "text": "100 nm", "color": "black", "size": 8.0}},
                    {"source": str(p["map_x"]), "letter": {"text": "B", "color": "white", "size": 12.0}, "badge": {"text": "Map-X", "color": "white", "size": 9.5}, "scale_bar": {"frac": 0.24, "text": "100 nm", "color": "white", "size": 8.0}},
                    {"source": str(p["map_y"]), "letter": {"text": "C", "color": "white", "size": 12.0}, "badge": {"text": "Map-Y", "color": "white", "size": 9.5}, "scale_bar": {"frac": 0.24, "text": "100 nm", "color": "white", "size": 8.0}},
                    {"source": str(p["map_z"]), "letter": {"text": "D", "color": "white", "size": 12.0}, "badge": {"text": "Map-Z", "color": "white", "size": 9.5}, "scale_bar": {"frac": 0.24, "text": "100 nm", "color": "white", "size": 8.0}},
                ],
            }],
        }, CHARTS_DIR / "09_microscopy-montage" / "preview", tmp)
        out_pngs.append(CHARTS_DIR / "09_microscopy-montage" / "preview.png")

    _build_wall(out_pngs, ASSETS_DIR / "gallery_wall.png", cols=3, rows=3,
                banner="SciFigStudio — 9 Synthetic Golden Chart-Type Previews",
                titles=[p.parent.name for p in out_pngs])
    return out_pngs


# ---------------------------------------------------------------- composite wall builder
def _load_font(size: int) -> ImageFont.ImageFont:
    for cand in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/timesbd.ttf"):
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _build_wall(pngs: list[Path], out_path: Path, cols: int, rows: int, banner: str, titles: list[str] | None = None):
    imgs = [Image.open(p).convert("RGB") for p in pngs]
    cell_w = max(im.width for im in imgs)
    cell_h = max(im.height for im in imgs)
    hdr_card = 42 if titles else 0
    pad = 28
    gap = 22
    top_banner = 82
    W = pad * 2 + cols * cell_w + (cols - 1) * gap
    H = top_banner + pad + rows * (cell_h + hdr_card) + (rows - 1) * gap + pad
    canvas = Image.new("RGB", (W, H), (247, 249, 252))
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, W, top_banner], fill=(15, 41, 66))
    f_ban = _load_font(36)
    f_ttl = _load_font(22)
    draw.text((pad, 20), banner, fill=(255, 255, 255), font=f_ban)

    for idx, im in enumerate(imgs):
        r, c = divmod(idx, cols)
        x0 = pad + c * (cell_w + gap)
        y0 = top_banner + pad + r * (cell_h + hdr_card + gap)
        if titles:
            draw.rectangle([x0, y0, x0 + cell_w, y0 + hdr_card], fill=(232, 238, 246), outline=(195, 206, 222), width=2)
            draw.text((x0 + 12, y0 + 8), titles[idx], fill=(15, 41, 66), font=f_ttl)
        resized = im.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        canvas.paste(resized, (x0, y0 + hdr_card))
        draw.rectangle([x0, y0, x0 + cell_w, y0 + hdr_card + cell_h], outline=(195, 206, 222), width=2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, dpi=(300, 300))


def main():
    th, pal = _init_theme()
    el_pngs = build_elements(th, pal)
    gal_pngs = build_gallery(th, pal)
    print(f"OK  elements={len(el_pngs)} -> {ASSETS_DIR / 'elements_wall.png'}")
    print(f"OK  gallery={len(gal_pngs)} -> {ASSETS_DIR / 'gallery_wall.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
