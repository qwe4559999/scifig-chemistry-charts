/**
 * SciFigStudio Interactive Workbench — Canvas & SVG Overlay Module
 * Handles figure sizing/zoom, 1:1 SVG interactive overlay, direct mouse dragging
 * with snap alignment guides, box-selection for local AI commands, and real-time
 * red QA guardrail overlays.
 */
(function (global) {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs, textContent) {
    const el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v !== undefined && v !== null) el.setAttribute(k, String(v));
      }
    }
    if (textContent !== undefined && textContent !== null) {
      el.textContent = String(textContent);
    }
    return el;
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function fmtNum(v, digits) {
    if (typeof v !== "number" || !Number.isFinite(v)) return "--";
    if (Math.abs(v) >= 100) return v.toFixed(1);
    if (Math.abs(v) >= 10) return v.toFixed(digits ?? 2);
    return v.toFixed(digits ?? 3);
  }

  class WorkbenchCanvas {
    constructor(opts) {
      this.stage = opts.stage;
      this.card = opts.card;
      this.img = opts.img;
      this.svg = opts.svg;
      this.panelsLayer = opts.panelsLayer;
      this.handlesLayer = opts.handlesLayer;
      this.snapGuidesLayer = opts.snapGuidesLayer;
      this.boxSelectLayer = opts.boxSelectLayer;
      this.qaOverlayLayer = opts.qaOverlayLayer;
      this.dragGhostLayer = opts.dragGhostLayer;
      this.dragHud = opts.dragHud;
      this.spinner = opts.spinner;

      this.onSelect = opts.onSelect || (() => {});
      this.onDragCommit = opts.onDragCommit || (() => {});
      this.onRegionChange = opts.onRegionChange || (() => {});

      this.bundle = null;
      this.selectedId = null;
      this.lockedSet = new Set();
      this.mode = "select"; // "select" | "box"
      this.zoom = "fit"; // "fit" | 1 | 1.25 | 1.5
      this.showOverlay = true;
      this.showQaBoxes = true;
      this.enableSnap = true;
      this.regionNorm = null;

      this.vbW = 1000;
      this.vbH = 800;
      this.aspect = 1.25;

      this._dragState = null;
      this._boxState = null;

      this._bindEvents();
    }

    _bindEvents() {
      // Background SVG clicks (deselect or start box-select)
      this.svg.addEventListener("pointerdown", (e) => {
        if (this.mode === "box") {
          this._startBoxSelect(e);
          return;
        }
        // Clicked empty canvas area -> deselect
        if (e.target === this.svg || e.target.classList.contains("svg-panel-frame")) {
          this.onSelect(null);
        }
      });

      window.addEventListener("pointermove", (e) => {
        if (this._dragState) this._onDragMove(e);
        else if (this._boxState) this._onBoxMove(e);
      });

      window.addEventListener("pointerup", (e) => {
        if (this._dragState) this._onDragEnd(e);
        else if (this._boxState) this._onBoxEnd(e);
      });

      window.addEventListener("resize", () => this.updateSize());
    }

    setLoading(flag) {
      if (this.spinner) this.spinner.classList.toggle("hidden", !flag);
    }

    setMode(mode) {
      this.mode = mode === "box" ? "box" : "select";
      this.svg.classList.toggle("mode-box", this.mode === "box");
    }

    setZoom(zoom) {
      this.zoom = zoom;
      this.updateSize();
    }

    setOptions({ showOverlay, showQaBoxes, enableSnap }) {
      if (typeof showOverlay === "boolean") this.showOverlay = showOverlay;
      if (typeof showQaBoxes === "boolean") this.showQaBoxes = showQaBoxes;
      if (typeof enableSnap === "boolean") this.enableSnap = enableSnap;
      this.renderOverlay();
    }

    setSelected(id) {
      this.selectedId = id;
      this.renderOverlay();
    }

    setLockedSet(set) {
      this.lockedSet = set || new Set();
      this.renderOverlay();
    }

    setRegion(regionNorm) {
      this.regionNorm = regionNorm;
      this._renderBoxRegion();
    }

    updateBundle(bundle) {
      this.bundle = bundle;
      if (!bundle) return;

      const w = Number(bundle.image_width_px) || (bundle.figure_size_in ? bundle.figure_size_in[0] * 150 : 900);
      const h = Number(bundle.image_height_px) || (bundle.figure_size_in ? bundle.figure_size_in[1] * 150 : 720);
      this.aspect = w / Math.max(1, h);
      this.vbW = 1000;
      this.vbH = Math.max(200, Math.round(1000 / this.aspect));
      this.svg.setAttribute("viewBox", `0 0 ${this.vbW} ${this.vbH}`);

      if (bundle.image_data_url) {
        this.img.src = bundle.image_data_url;
      }

      this.updateSize();
      this.renderOverlay();
    }

    updateSize() {
      if (!this.stage || !this.card) return;
      const availW = Math.max(320, this.stage.clientWidth - 36);
      const availH = Math.max(240, this.stage.clientHeight - 28);

      let fitW = availW;
      let fitH = fitW / this.aspect;
      if (fitH > availH) {
        fitH = availH;
        fitW = fitH * this.aspect;
      }

      let finalW = fitW;
      let finalH = fitH;
      if (this.zoom !== "fit") {
        const scale = Number(this.zoom) || 1;
        finalW = fitW * scale;
        finalH = fitH * scale;
      }

      this.card.style.width = `${Math.round(finalW)}px`;
      this.card.style.height = `${Math.round(finalH)}px`;
    }

    _nx(x) {
      return x * this.vbW;
    }

    _ny(y) {
      return y * this.vbH;
    }

    renderOverlay() {
      this.panelsLayer.innerHTML = "";
      this.handlesLayer.innerHTML = "";
      this.qaOverlayLayer.innerHTML = "";

      if (!this.bundle) return;
      const handles = this.bundle.handles || {};
      const panels = handles.panels || [];
      const items = handles.items || [];

      // 1. Subtle Panel frames
      if (this.showOverlay) {
        for (const p of panels) {
          const r = p.rect_norm;
          if (!r || r.length < 4) continue;
          const x = this._nx(r[0]);
          const y = this._ny(r[1]);
          const w = Math.max(2, this._nx(r[2] - r[0]));
          const h = Math.max(2, this._ny(r[3] - r[1]));
          const isSel = this.selectedId === p.id;
          const rectEl = svgEl("rect", {
            x,
            y,
            width: w,
            height: h,
            class: "svg-panel-frame",
            style: isSel ? "stroke: #1E5AA8; stroke-width: 1.8; stroke-dasharray: 5 3;" : "",
          });
          this.panelsLayer.appendChild(rectEl);
        }
      }

      // 2. Interactive draggable handles (text, vline, hline, legend, letter, sample_label)
      const interactiveItems = items.filter((it) => {
        if (it.visible === false) return false;
        if (!it.bbox_norm || it.bbox_norm.length < 4) return false;
        return Boolean(it.draggable) || ["text", "vline", "legend", "letter", "sample_label"].includes(it.kind);
      });

      for (const item of interactiveItems) {
        const isSel = this.selectedId === item.id;
        const isLocked = this.lockedSet.has(item.id);
        // If overlay is toggled off, only keep invisible click hit area unless selected
        const quiet = !this.showOverlay && !isSel;

        const [bx0, by0, bx1, by1] = item.bbox_norm;
        const pad = item.kind === "vline" ? 0 : 4;
        const x = this._nx(bx0) - pad;
        const y = this._ny(by0) - pad;
        const w = Math.max(12, this._nx(bx1 - bx0) + pad * 2);
        const h = Math.max(12, this._ny(by1 - by0) + pad * 2);

        if (item.kind === "vline") {
          const cx = this._nx((bx0 + bx1) / 2);
          const y0 = this._ny(by0);
          const y1 = this._ny(by1);
          const g = svgEl("g", {
            class: `svg-vline-group${isSel ? " selected" : ""}`,
            "data-handle-id": item.id,
          });
          const visLine = svgEl("line", {
            x1: cx,
            y1: y0,
            x2: cx,
            y2: y1,
            class: "svg-vline-vis",
            style: quiet ? "stroke: transparent;" : "",
          });
          const hitLine = svgEl("line", {
            x1: cx,
            y1: y0,
            x2: cx,
            y2: y1,
            class: "svg-vline-hit",
          });
          g.appendChild(visLine);
          g.appendChild(hitLine);

          if (isSel) {
            g.appendChild(svgEl("circle", { cx, cy: y0, r: 4, class: "svg-corner-handle" }));
            g.appendChild(svgEl("circle", { cx, cy: y1, r: 4, class: "svg-corner-handle" }));
            const pillText = `vline x=${fmtNum(item.props?.x, 1)}`;
            this._appendSelectPill(g, cx, Math.max(18, y0 - 8), pillText);
          }

          g.addEventListener("pointerdown", (e) => this._onHandlePointerDown(e, item));
          this.handlesLayer.appendChild(g);
        } else {
          const g = svgEl("g", {
            "data-handle-id": item.id,
          });
          const rect = svgEl("rect", {
            x,
            y,
            width: w,
            height: h,
            rx: 2.5,
            class: `svg-handle-box${isSel ? " selected" : ""}${isLocked ? " locked" : ""}`,
            style: quiet ? "stroke: transparent; fill: transparent;" : "",
          });
          const title = svgEl("title", null, `${item.kind}: ${item.label || item.id}${isLocked ? " (已锁定)" : " (拖拽微调)"}`);
          rect.appendChild(title);
          g.appendChild(rect);

          if (isSel) {
            // 4 crisp square corner handles
            const corners = [
              [x, y],
              [x + w, y],
              [x, y + h],
              [x + w, y + h],
            ];
            for (const [cx, cy] of corners) {
              g.appendChild(svgEl("rect", {
                x: cx - 3.5,
                y: cy - 3.5,
                width: 7,
                height: 7,
                rx: 1,
                class: "svg-corner-handle",
              }));
            }
            // Hide blue selection pill when a QA violation box overlaps this handle so red QA pill stays 100% clear
            if (!this._intersectsQaBox(item.bbox_norm)) {
              const pillLabel = this._formatSelectedTag(item);
              this._appendSelectPill(g, x + w / 2, Math.max(18, y - 6), pillLabel);
            }
          }

          g.addEventListener("pointerdown", (e) => this._onHandlePointerDown(e, item));
          this.handlesLayer.appendChild(g);
        }
      }

      // 3. Real-time Red QA Collision / Clipping Overlays
      this._renderQaViolations();

      // 4. Box-Select region (if active)
      this._renderBoxRegion();
    }

    _formatSelectedTag(item) {
      const p = item.props || {};
      if (item.kind === "text" && Array.isArray(p.xy)) {
        return `"${(item.label || p.text || "").slice(0, 12)}" (${fmtNum(p.xy[0], 1)}, ${fmtNum(p.xy[1], 2)})`;
      }
      if (item.kind === "legend") {
        return `Legend · ${p.loc || "auto"}`;
      }
      if (item.kind === "letter") {
        return `Panel ${item.label || p.text || ""}`;
      }
      return `${item.kind}: ${(item.label || "").slice(0, 14)}`;
    }

    _appendSelectPill(group, cx, bottomY, text) {
      const estW = Math.max(54, text.length * 6.8 + 14);
      const pillH = 17;
      const px = clamp(cx - estW / 2, 4, this.vbW - estW - 4);
      const py = clamp(bottomY - pillH, 4, this.vbH - pillH - 4);
      group.appendChild(svgEl("rect", {
        x: px,
        y: py,
        width: estW,
        height: pillH,
        rx: 3,
        class: "svg-select-pill-bg",
      }));
      group.appendChild(svgEl("text", {
        x: px + estW / 2,
        y: py + 12.2,
        "text-anchor": "middle",
        class: "svg-select-pill-text",
      }, text));
    }

    _intersectsQaBox(bboxNorm) {
      if (!this.showQaBoxes || !bboxNorm || !this.bundle?.qa?.violation_boxes?.length) return false;
      const [ax0, ay0, ax1, ay1] = bboxNorm;
      const pad = 0.025;
      for (const vb of this.bundle.qa.violation_boxes) {
        const b = vb.bbox_norm;
        if (!b || b.length < 4) continue;
        if (ax0 - pad <= b[2] && ax1 + pad >= b[0] && ay0 - pad <= b[3] && ay1 + pad >= b[1]) {
          return true;
        }
      }
      return false;
    }

    _renderQaViolations() {
      this.qaOverlayLayer.innerHTML = "";
      if (!this.showQaBoxes || !this.bundle || !this.bundle.qa) return;
      const boxes = this.bundle.qa.violation_boxes || [];
      if (!boxes.length) return;

      const placedLabels = [];
      boxes.forEach((vb, idx) => {
        const b = vb.bbox_norm;
        if (!b || b.length < 4) return;
        const pad = 6;
        const x = clamp(this._nx(b[0]) - pad, 2, this.vbW - 20);
        const y = clamp(this._ny(b[1]) - pad, 2, this.vbH - 20);
        const w = clamp(this._nx(b[2] - b[0]) + pad * 2, 18, this.vbW - x - 2);
        const h = clamp(this._ny(b[3] - b[1]) + pad * 2, 18, this.vbH - y - 2);

        const g = svgEl("g", { class: "qa-violation-group", "data-qa-index": idx });
        g.appendChild(svgEl("rect", {
          x,
          y,
          width: w,
          height: h,
          rx: 3,
          class: "svg-qa-box",
        }));

        const kindMap = {
          text_overlap: "文字重叠",
          clipped: "标签出界",
          legend_data: "图例遮挡",
        };
        const label = `⚠ ${kindMap[vb.kind] || "QA 预警"}`;
        const estW = label.length * 10.2 + 12;
        const lh = 19;
        let lx = clamp(x, 4, this.vbW - estW - 4);
        // Prefer bottom of red box first (leaves top edge clean), fallback to top
        let ly = y + h + lh + 6 <= this.vbH ? y + h + 4 : Math.max(4, y - lh - 4);

        // Avoid stacking on an earlier QA pill
        for (const prev of placedLabels) {
          if (lx < prev.x + prev.w + 4 && lx + estW + 4 > prev.x && Math.abs(ly - prev.y) < lh + 2) {
            ly = clamp(prev.y + lh + 3, 4, this.vbH - lh - 4);
          }
        }
        placedLabels.push({ x: lx, y: ly, w: estW, h: lh });

        g.appendChild(svgEl("rect", {
          x: lx,
          y: ly,
          width: estW,
          height: lh,
          rx: 3,
          class: "svg-qa-label-bg",
        }));
        g.appendChild(svgEl("text", {
          x: lx + estW / 2,
          y: ly + 13.2,
          "text-anchor": "middle",
          class: "svg-qa-label-text",
        }, label));

        this.qaOverlayLayer.appendChild(g);
      });
    }

    _renderBoxRegion() {
      this.boxSelectLayer.innerHTML = "";
      if (!this.regionNorm || this.regionNorm.length < 4) return;
      const [x0, y0, x1, y1] = this.regionNorm;
      const x = this._nx(Math.min(x0, x1));
      const y = this._ny(Math.min(y0, y1));
      const w = Math.max(4, this._nx(Math.abs(x1 - x0)));
      const h = Math.max(4, this._ny(Math.abs(y1 - y0)));
      this.boxSelectLayer.appendChild(svgEl("rect", {
        x,
        y,
        width: w,
        height: h,
        rx: 3,
        class: "svg-box-select",
      }));
    }

    _onHandlePointerDown(e, item) {
      if (this.mode === "box") return; // let box-select handle it
      e.stopPropagation();
      e.preventDefault();

      this.onSelect(item.id);

      if (!item.draggable || this.lockedSet.has(item.id)) return;

      const rect = this.card.getBoundingClientRect();
      if (!rect.width || !rect.height) return;

      this._dragState = {
        item,
        startX: e.clientX,
        startY: e.clientY,
        cardRect: rect,
        dxNorm: 0,
        dyNorm: 0,
        moved: false,
      };
    }

    _computeSnap(item, dxNorm, dyNorm) {
      const guides = [];
      if (!this.enableSnap || !this.bundle?.handles?.items) {
        return { dxNorm, dyNorm, guides };
      }

      const b = item.bbox_norm;
      const cx0 = (b[0] + b[2]) / 2 + dxNorm;
      const cy0 = (b[1] + b[3]) / 2 + dyNorm;
      const THRESH = 0.008;

      let bestDx = dxNorm;
      let bestDy = dyNorm;
      let snappedX = null;
      let snappedY = null;

      for (const other of this.bundle.handles.items) {
        if (other.id === item.id || other.visible === false || !other.bbox_norm) continue;
        if (other.panel_index !== item.panel_index) continue;
        if (!["text", "vline", "legend", "letter"].includes(other.kind)) continue;

        const ob = other.bbox_norm;
        const ocx = (ob[0] + ob[2]) / 2;
        const ocy = (ob[1] + ob[3]) / 2;

        if (snappedX === null && Math.abs(cx0 - ocx) < THRESH) {
          bestDx += ocx - cx0;
          snappedX = ocx;
        }
        if (item.kind !== "vline" && snappedY === null && Math.abs(cy0 - ocy) < THRESH) {
          bestDy += ocy - cy0;
          snappedY = ocy;
        }
      }

      const panel = (this.bundle.handles.panels || []).find((p) => p.panel_index === item.panel_index);
      const pr = panel?.rect_norm || [0.05, 0.05, 0.95, 0.95];

      if (snappedX !== null) {
        guides.push({ type: "v", x: snappedX, y0: pr[1], y1: pr[3] });
      }
      if (snappedY !== null) {
        guides.push({ type: "h", y: snappedY, x0: pr[0], x1: pr[2] });
      }
      return { dxNorm: bestDx, dyNorm: bestDy, guides };
    }

    _estimateDataCoords(item, nx, ny) {
      const panels = this.bundle?.handles?.panels || [];
      const panel = panels.find((p) => p.panel_index === item.panel_index);
      if (!panel || !panel.segments || !panel.segments.length) return null;

      let seg = panel.segments.find((s) => s.seg_index === (item.seg_index || 0) && s.subpanel_index === item.subpanel_index);
      if (!seg) seg = panel.segments[0];
      if (!seg || !seg.rect_norm || !seg.xlim || !seg.ylim) return null;

      const [sx0, sy0, sx1, sy1] = seg.rect_norm;
      const fx = (nx - sx0) / Math.max(1e-6, sx1 - sx0);
      const fy = 1 - (ny - sy0) / Math.max(1e-6, sy1 - sy0); // axes y goes upward

      const [x0, x1] = seg.xlim;
      const [y0, y1] = seg.ylim;
      const dataX = x0 + fx * (x1 - x0);
      const dataY = y0 + fy * (y1 - y0);
      return { dataX, dataY, axesX: fx, axesY: fy };
    }

    _onDragMove(e) {
      const ds = this._dragState;
      const rawDxPx = e.clientX - ds.startX;
      const rawDyPx = e.clientY - ds.startY;
      if (!ds.moved && Math.hypot(rawDxPx, rawDyPx) < 3) return;
      ds.moved = true;

      let dxNorm = rawDxPx / ds.cardRect.width;
      let dyNorm = ds.item.kind === "vline" ? 0 : rawDyPx / ds.cardRect.height;

      const snapped = this._computeSnap(ds.item, dxNorm, dyNorm);
      ds.dxNorm = snapped.dxNorm;
      ds.dyNorm = snapped.dyNorm;

      // Render snap lines
      this.snapGuidesLayer.innerHTML = "";
      for (const g of snapped.guides) {
        if (g.type === "v") {
          this.snapGuidesLayer.appendChild(svgEl("line", {
            x1: this._nx(g.x),
            y1: this._ny(g.y0),
            x2: this._nx(g.x),
            y2: this._ny(g.y1),
            class: "svg-snap-line",
          }));
        } else {
          this.snapGuidesLayer.appendChild(svgEl("line", {
            x1: this._nx(g.x0),
            y1: this._ny(g.y),
            x2: this._nx(g.x1),
            y2: this._ny(g.y),
            class: "svg-snap-line",
          }));
        }
      }

      // Render drag ghost
      this.dragGhostLayer.innerHTML = "";
      const [bx0, by0, bx1, by1] = ds.item.bbox_norm;
      if (ds.item.kind === "vline") {
        const cx = this._nx((bx0 + bx1) / 2 + ds.dxNorm);
        this.dragGhostLayer.appendChild(svgEl("line", {
          x1: cx,
          y1: this._ny(by0),
          x2: cx,
          y2: this._ny(by1),
          stroke: "#1E5AA8",
          "stroke-width": 2.4,
          "stroke-dasharray": "4 2",
        }));
      } else {
        this.dragGhostLayer.appendChild(svgEl("rect", {
          x: this._nx(bx0 + ds.dxNorm) - 3,
          y: this._ny(by0 + ds.dyNorm) - 3,
          width: Math.max(12, this._nx(bx1 - bx0) + 6),
          height: Math.max(12, this._ny(by1 - by0) + 6),
          rx: 3,
          class: "svg-drag-ghost",
        }));
      }

      // Live Coordinate Readout HUD
      const anchor = ds.item.anchor_norm || [(bx0 + bx1) / 2, (by0 + by1) / 2];
      const newNx = anchor[0] + ds.dxNorm;
      const newNy = anchor[1] + ds.dyNorm;
      const est = this._estimateDataCoords(ds.item, newNx, newNy);

      this.dragHud.classList.remove("hidden");
      if (est && ds.item.kind === "vline") {
        this.dragHud.textContent = `拖拽虚线 x = ${fmtNum(est.dataX, 1)}  (Δx ${(ds.dxNorm * 100).toFixed(1)}%)`;
      } else if (est && ds.item.props?.coords !== "axes") {
        this.dragHud.textContent = `坐标 x: ${fmtNum(est.dataX, 1)}, y: ${fmtNum(est.dataY, 3)}${snapped.guides.length ? " · 已吸附" : ""}`;
      } else if (est) {
        this.dragHud.textContent = `Axes x: ${est.axesX.toFixed(2)}, y: ${est.axesY.toFixed(2)}${snapped.guides.length ? " · 已吸附" : ""}`;
      } else {
        this.dragHud.textContent = `Δx: ${(ds.dxNorm * 100).toFixed(1)}%, Δy: ${(ds.dyNorm * 100).toFixed(1)}%`;
      }
    }

    _onDragEnd() {
      const ds = this._dragState;
      this._dragState = null;
      this.snapGuidesLayer.innerHTML = "";
      this.dragGhostLayer.innerHTML = "";
      this.dragHud.classList.add("hidden");

      if (!ds || !ds.moved) return;
      if (Math.abs(ds.dxNorm) < 0.001 && Math.abs(ds.dyNorm) < 0.001) return;

      const anchor = ds.item.anchor_norm || [
        (ds.item.bbox_norm[0] + ds.item.bbox_norm[2]) / 2,
        (ds.item.bbox_norm[1] + ds.item.bbox_norm[3]) / 2,
      ];
      const targetNorm = [
        clamp(anchor[0] + ds.dxNorm, 0, 1),
        clamp(anchor[1] + ds.dyNorm, 0, 1),
      ];
      this.onDragCommit(ds.item, ds.dxNorm, ds.dyNorm, targetNorm);
    }

    _startBoxSelect(e) {
      e.preventDefault();
      const rect = this.card.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x0 = clamp((e.clientX - rect.left) / rect.width, 0, 1);
      const y0 = clamp((e.clientY - rect.top) / rect.height, 0, 1);
      this._boxState = { rect, x0, y0, x1: x0, y1: y0 };
    }

    _onBoxMove(e) {
      const bs = this._boxState;
      bs.x1 = clamp((e.clientX - bs.rect.left) / bs.rect.width, 0, 1);
      bs.y1 = clamp((e.clientY - bs.rect.top) / bs.rect.height, 0, 1);
      this.regionNorm = [
        Math.min(bs.x0, bs.x1),
        Math.min(bs.y0, bs.y1),
        Math.max(bs.x0, bs.x1),
        Math.max(bs.y0, bs.y1),
      ];
      this._renderBoxRegion();
    }

    _onBoxEnd() {
      const bs = this._boxState;
      this._boxState = null;
      if (!bs) return;
      const w = Math.abs(bs.x1 - bs.x0);
      const h = Math.abs(bs.y1 - bs.y0);
      if (w < 0.02 || h < 0.02) {
        this.regionNorm = null;
        this._renderBoxRegion();
        this.onRegionChange(null);
      } else {
        this.onRegionChange(this.regionNorm);
      }
    }
  }

  global.WorkbenchCanvas = WorkbenchCanvas;
})(window);
