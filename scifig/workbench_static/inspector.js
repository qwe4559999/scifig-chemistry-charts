/**
 * SciFigStudio Interactive Workbench — Inspector, Layer Tree, Data Table & Preflight Module
 */
(function (global) {
  "use strict";

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  /**
   * Convert simple matplotlib chemistry mathtext (e.g. Catalyst-A, NO$_x$, cm$^{-1}$)
   * into crisp safe HTML <sub>/<sup> for Layer Tree labels.
   */
  function formatChemHtml(raw) {
    let s = escapeHtml(raw ?? "");
    s = s.replace(/\$_\{([^}]+)\}\$/g, "<sub>$1</sub>");
    s = s.replace(/\$\^\{([^}]+)\}\$/g, "<sup>$1</sup>");
    s = s.replace(/\$_([A-Za-z0-9+\\-]+)\$/g, "<sub>$1</sub>");
    s = s.replace(/\$\^([A-Za-z0-9+\\-]+)\$/g, "<sup>$1</sup>");
    s = s.replace(/\$/g, "");
    return s;
  }

  function hexOrDefault(val, fallback) {
    if (typeof val === "string" && /^#[0-9a-fA-F]{6}$/.test(val.trim())) {
      return val.trim();
    }
    return fallback || "#1E5AA8";
  }

  function kindTagMeta(kind) {
    const map = {
      line: { label: "曲线", cls: "tag-line" },
      scatter: { label: "散点", cls: "tag-line" },
      line_marker: { label: "折线", cls: "tag-line" },
      fill: { label: "填充", cls: "tag-fill" },
      fill_between: { label: "分峰", cls: "tag-fill" },
      bar: { label: "柱状", cls: "tag-fill" },
      bar_stacked: { label: "堆叠", cls: "tag-fill" },
      comb: { label: "谱峰", cls: "tag-line" },
      text: { label: "峰标", cls: "tag-text" },
      sample_label: { label: "样品", cls: "tag-text" },
      vline: { label: "虚线", cls: "tag-vline" },
      hline: { label: "水平线", cls: "tag-vline" },
      legend: { label: "图例", cls: "tag-legend" },
      letter: { label: "编号", cls: "tag-letter" },
    };
    return map[kind] || { label: kind || "元素", cls: "" };
  }

  /**
   * Locate the mutable object inside `spec` corresponding to a handle item.
   */
  function resolveSpecTarget(spec, handle) {
    if (!spec || !Array.isArray(spec.panels) || !handle) return null;
    const panel = spec.panels[handle.panel_index];
    if (!panel) return null;

    if (handle.kind === "panel") return { target: panel, panel, container: "panel" };
    if (handle.kind === "legend") {
      if (!panel.legend) panel.legend = { loc: "upper right" };
      return { target: panel.legend, panel, container: "legend" };
    }
    if (handle.kind === "letter") {
      if (!panel.letter) panel.letter = { text: panel.id || "A", x: -0.1, y: 0.95 };
      return { target: panel.letter, panel, container: "letter" };
    }
    if (handle.kind === "sample_label" && handle.subpanel_index != null) {
      const sub = (panel.subpanels || [])[handle.subpanel_index];
      if (!sub) return null;
      return { target: sub, panel, subpanel: sub, container: "sample_label" };
    }
    if (handle.plot_index != null) {
      if (handle.subpanel_index != null && Array.isArray(panel.subpanels)) {
        const sub = panel.subpanels[handle.subpanel_index];
        const plot = sub?.plots?.[handle.plot_index];
        if (plot) return { target: plot, panel, subpanel: sub, container: "plot" };
      } else if (Array.isArray(panel.plots)) {
        const plot = panel.plots[handle.plot_index];
        if (plot) return { target: plot, panel, container: "plot" };
      }
    }
    return null;
  }

  /* ------------------------------------------------------------------------
   * LAYER TREE RENDERER
   * ------------------------------------------------------------------------ */
  function renderLayerTree(container, summaryPill, bundle, state, callbacks) {
    if (!container) return;
    const handles = bundle?.handles || {};
    const panels = handles.panels || [];
    const items = handles.items || [];

    if (summaryPill) {
      summaryPill.textContent = `${panels.length} 面板 · ${items.length} 图层`;
    }

    if (!panels.length && !items.length) {
      container.innerHTML = `<div class="empty-hint">当前图件暂无可编辑图层</div>`;
      return;
    }

    // Group items by panel_index
    const byPanel = new Map();
    for (const p of panels) byPanel.set(p.panel_index, []);
    for (const it of items) {
      if (!byPanel.has(it.panel_index)) byPanel.set(it.panel_index, []);
      byPanel.get(it.panel_index).push(it);
    }

    container.innerHTML = "";

    for (const p of panels) {
      const group = document.createElement("div");
      const isCollapsed = state.collapsedPanels.has(p.panel_index);
      group.className = `layer-group${isCollapsed ? " collapsed" : ""}`;

      const pItems = byPanel.get(p.panel_index) || [];
      const pRow = document.createElement("div");
      pRow.className = `layer-panel-row${state.selectedId === p.id ? " selected" : ""}`;
      pRow.innerHTML = `
        <span class="layer-panel-caret" data-toggle-panel="${p.panel_index}">▾</span>
        <span>Panel ${escapeHtml(p.panel_id || String(p.panel_index + 1))}</span>
        <span class="layer-panel-badge">${p.has_segments ? "断轴 · " : ""}${pItems.length} 项</span>
      `;
      pRow.addEventListener("click", (e) => {
        if (e.target.closest("[data-toggle-panel]")) {
          if (state.collapsedPanels.has(p.panel_index)) state.collapsedPanels.delete(p.panel_index);
          else state.collapsedPanels.add(p.panel_index);
          group.classList.toggle("collapsed");
          return;
        }
        callbacks.onSelect(p.id);
      });
      group.appendChild(pRow);

      const children = document.createElement("div");
      children.className = "layer-children";

      for (const it of pItems) {
        const isSel = state.selectedId === it.id;
        const isHidden = it.visible === false;
        const isLocked = state.lockedHandles.has(it.id);
        const tag = kindTagMeta(it.kind);
        const swatchColor = it.props?.color || (it.kind === "vline" ? "#334155" : it.kind === "text" ? "#0F2942" : "#1E5AA8");
        const displayName = it.label || (it.kind === "legend" ? `图例 (${it.props?.loc || "auto"})` : it.kind === "vline" ? `x = ${it.props?.x ?? ""}` : it.id);

        const row = document.createElement("div");
        row.className = `layer-item${isSel ? " selected" : ""}${isHidden ? " is-hidden" : ""}`;
        row.dataset.handleId = it.id;
        row.innerHTML = `
          <span class="layer-swatch" style="background:${escapeHtml(hexOrDefault(swatchColor, "#64748B"))}"></span>
          <span class="layer-type-tag ${tag.cls}">${tag.label}</span>
          <span class="layer-name" title="${escapeHtml(displayName)}">${formatChemHtml(displayName)}</span>
          <span class="layer-actions">
            <button class="layer-action-btn${isHidden ? " active-hidden" : ""}" data-act="vis" title="${isHidden ? "显示图层" : "隐藏图层"}">
              ${isHidden
                ? `<svg viewBox="0 0 16 16" width="13" height="13"><path d="M2 2l12 12M6.5 6.5a2 2 0 0 0 2.8 2.8M3.3 5.2C2 6.3 1.2 8 1.2 8s2.6 4.5 6.8 4.5c1.3 0 2.5-.4 3.5-1M12.7 10.8C14 9.7 14.8 8 14.8 8S12.2 3.5 8 3.5c-.8 0-1.6.2-2.3.5" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>`
                : `<svg viewBox="0 0 16 16" width="13" height="13"><path d="M1.2 8S3.8 3.5 8 3.5 14.8 8 14.8 8 12.2 12.5 8 12.5 1.2 8 1.2 8z" stroke="currentColor" stroke-width="1.3" fill="none"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>`}
            </button>
            <button class="layer-action-btn${isLocked ? " active-lock" : ""}" data-act="lock" title="${isLocked ? "解除锁定" : "锁定位置"}">
              ${isLocked
                ? `<svg viewBox="0 0 16 16" width="12" height="12"><rect x="3.5" y="7" width="9" height="6.5" rx="1.2" fill="currentColor"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" stroke-width="1.4" fill="none"/></svg>`
                : `<svg viewBox="0 0 16 16" width="12" height="12"><rect x="3.5" y="7" width="9" height="6.5" rx="1.2" stroke="currentColor" stroke-width="1.3" fill="none"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.8-1" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>`}
            </button>
          </span>
        `;

        row.addEventListener("click", (e) => {
          const btn = e.target.closest("[data-act]");
          if (btn) {
            e.stopPropagation();
            const act = btn.dataset.act;
            if (act === "vis") callbacks.onToggleVisible(it);
            if (act === "lock") callbacks.onToggleLock(it);
            return;
          }
          callbacks.onSelect(it.id);
        });
        children.appendChild(row);
      }

      group.appendChild(children);
      container.appendChild(group);
    }
  }

  /* ------------------------------------------------------------------------
   * DATA TABLE PREVIEW & SHA256 PROVENANCE
   * ------------------------------------------------------------------------ */
  function renderDataPanel(els, bundle, state, onSelectTab) {
    const datasets = bundle?.datasets || [];
    els.tabs.innerHTML = "";
    els.opsStrip.innerHTML = "";
    els.tableWrap.innerHTML = "";

    if (!datasets.length) {
      els.rowCount.textContent = "0 数据集";
      els.tableWrap.innerHTML = `<div class="empty-hint">该图件为纯合成或图像拼图，无表格数据</div>`;
      els.provBar.className = "provenance-bar prov-ok";
      els.provText.textContent = "SHA256: 本地资产只读校验通过";
      return;
    }

    if (!state.activeDataKey || !datasets.some((d) => d.key === state.activeDataKey)) {
      state.activeDataKey = datasets[0].key;
    }

    for (const ds of datasets) {
      const btn = document.createElement("button");
      btn.className = `data-tab${ds.key === state.activeDataKey ? " active" : ""}`;
      btn.textContent = ds.key;
      btn.title = `${ds.filename || ds.source} (${ds.rows ?? 0} 行)`;
      btn.addEventListener("click", () => onSelectTab(ds.key));
      els.tabs.appendChild(btn);
    }

    const active = datasets.find((d) => d.key === state.activeDataKey) || datasets[0];
    els.rowCount.textContent = `${active.rows ?? 0} 行 · ${(active.cols || []).length} 列`;

    // Ops badges
    const ops = active.ops || [];
    if (ops.length) {
      for (const op of ops) {
        const badge = document.createElement("span");
        badge.className = "op-badge";
        const name = typeof op === "string" ? op : op.op || JSON.stringify(op);
        const extra = op && typeof op === "object" && op.x_range ? ` [${op.x_range[0]}..${op.x_range[1]}]` : "";
        badge.textContent = `${name}${extra}`;
        els.opsStrip.appendChild(badge);
      }
    } else {
      els.opsStrip.innerHTML = `<span class="op-badge op-badge-neutral">原始数值直读 · 零破坏性平滑</span>`;
    }

    // Table preview (first ~15 rows visible, scrollable)
    const cols = (active.cols || []).slice(0, 8);
    const rows = (active.preview_rows || []).slice(0, 20);
    if (!cols.length || !rows.length) {
      els.tableWrap.innerHTML = `<div class="empty-hint">文件: ${escapeHtml(active.filename || active.source || "--")}</div>`;
    } else {
      const table = document.createElement("table");
      table.className = "data-table";
      const thead = document.createElement("thead");
      const trh = document.createElement("tr");
      trh.innerHTML = `<th>#</th>` + cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
      thead.appendChild(trh);
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      rows.forEach((r, idx) => {
        const tr = document.createElement("tr");
        let html = `<td>${idx + 1}</td>`;
        for (const c of cols) {
          const v = r[c];
          let text = "";
          if (typeof v === "number" && Number.isFinite(v)) {
            text = Math.abs(v) >= 100 ? v.toFixed(1) : Math.abs(v) < 0.01 && v !== 0 ? v.toExponential(2) : v.toFixed(4);
          } else {
            text = String(v ?? "");
          }
          html += `<td>${escapeHtml(text)}</td>`;
        }
        tr.innerHTML = html;
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      els.tableWrap.appendChild(table);
    }

    // SHA256 Provenance Bar
    if (active.exists !== false && active.sha256_16) {
      els.provBar.className = "provenance-bar prov-ok";
      els.provText.textContent = `SHA256: ${active.sha256_16} · 原始值只读保护`;
      els.provBar.title = `源文件: ${active.source}\nSHA256(16): ${active.sha256_16}\n原始数据文件只读保护，禁止静默修改数值`;
    } else {
      els.provBar.className = "provenance-bar prov-warn";
      els.provText.textContent = `数据源校验: ${active.filename || active.key} (请核对路径)`;
    }
  }

  /* ------------------------------------------------------------------------
   * SELECTED ELEMENT PROPERTY INSPECTOR
   * ------------------------------------------------------------------------ */
  function renderInspector(els, bundle, selectedId, onMutateSpec) {
    els.body.innerHTML = "";
    if (!bundle || !bundle.spec) {
      els.crumb.textContent = "未选中";
      els.body.innerHTML = `<div class="inspector-empty">等待加载图件...</div>`;
      return;
    }

    const panels = bundle.handles?.panels || [];
    const items = bundle.handles?.items || [];

    // Check if panel selected
    const selPanel = panels.find((p) => p.id === selectedId);
    if (selPanel) {
      const panelSpec = bundle.spec.panels?.[selPanel.panel_index];
      els.crumb.textContent = `Panel ${selPanel.panel_id || selPanel.panel_index}`;
      _buildPanelInspector(els.body, panelSpec, selPanel, onMutateSpec);
      return;
    }

    // Check if item selected
    const selItem = items.find((it) => it.id === selectedId);
    if (!selItem) {
      // Show quick panel overview of Panel 0 so inspector is immediately useful
      const firstPanel = panels[0];
      if (firstPanel && bundle.spec.panels?.[0]) {
        els.crumb.textContent = `Panel ${firstPanel.panel_id || "0"}`;
        _buildPanelInspector(els.body, bundle.spec.panels[0], firstPanel, onMutateSpec);
      } else {
        els.crumb.textContent = "未选中";
        els.body.innerHTML = `<div class="inspector-empty">点击画布中的峰标、虚线、图例或左侧图层，即可直接编辑坐标与样式。</div>`;
      }
      return;
    }

    const resolved = resolveSpecTarget(bundle.spec, selItem);
    const tag = kindTagMeta(selItem.kind);
    els.crumb.textContent = `${tag.label} · ${selItem.panel_id || "P" + selItem.panel_index}`;

    if (!resolved) {
      els.body.innerHTML = `<div class="inspector-empty">该元素仅支持画布预览。</div>`;
      return;
    }

    const target = resolved.target;
    const grid = document.createElement("div");
    grid.className = "prop-grid";

    const addField = (label, inputEl, full = false) => {
      const wrap = document.createElement("div");
      wrap.className = `prop-field${full ? " full" : ""}`;
      const lbl = document.createElement("label");
      lbl.className = "prop-label";
      lbl.textContent = label;
      wrap.appendChild(lbl);
      wrap.appendChild(inputEl);
      grid.appendChild(wrap);
    };

    const makeText = (val, onCommit) => {
      const inp = document.createElement("input");
      inp.type = "text";
      inp.className = "prop-input";
      inp.value = val ?? "";
      inp.addEventListener("change", () => onCommit(inp.value));
      return inp;
    };

    const makeNumber = (val, step, onCommit) => {
      const inp = document.createElement("input");
      inp.type = "number";
      inp.step = String(step ?? "any");
      inp.className = "prop-input";
      inp.value = val ?? "";
      inp.addEventListener("change", () => {
        const n = parseFloat(inp.value);
        if (Number.isFinite(n)) onCommit(n);
      });
      return inp;
    };

    const makeSelect = (val, options, onCommit) => {
      const sel = document.createElement("select");
      sel.className = "prop-select";
      for (const opt of options) {
        const o = document.createElement("option");
        o.value = opt.value ?? opt;
        o.textContent = opt.label ?? opt;
        if (String(o.value) === String(val)) o.selected = true;
        sel.appendChild(o);
      }
      sel.addEventListener("change", () => onCommit(sel.value));
      return sel;
    };

    const makeColor = (val, onCommit) => {
      const row = document.createElement("div");
      row.className = "prop-color-row";
      const picker = document.createElement("input");
      picker.type = "color";
      picker.className = "prop-color-picker";
      picker.value = hexOrDefault(val, "#000000");
      const txt = document.createElement("input");
      txt.type = "text";
      txt.className = "prop-input";
      txt.value = val ?? "#000000";
      picker.addEventListener("change", () => {
        txt.value = picker.value.toUpperCase();
        onCommit(picker.value.toUpperCase());
      });
      txt.addEventListener("change", () => onCommit(txt.value.trim()));
      row.appendChild(picker);
      row.appendChild(txt);
      return row;
    };

    const makeSliderNum = (val, min, max, step, onCommit) => {
      const row = document.createElement("div");
      row.className = "prop-slider-row";
      const numVal = Number.isFinite(Number(val)) ? Number(val) : 0;
      const range = document.createElement("input");
      range.type = "range";
      range.className = "prop-slider";
      range.min = String(min);
      range.max = String(max);
      range.step = String(step);
      range.value = String(clamp(numVal, min, max));
      const num = document.createElement("input");
      num.type = "number";
      num.className = "prop-input prop-slider-num";
      num.step = String(step);
      num.value = String(numVal);

      range.addEventListener("input", () => {
        num.value = range.value;
      });
      range.addEventListener("change", () => onCommit(parseFloat(range.value)));
      num.addEventListener("change", () => {
        const n = parseFloat(num.value);
        if (Number.isFinite(n)) {
          range.value = String(clamp(n, min, max));
          onCommit(n);
        }
      });
      row.appendChild(range);
      row.appendChild(num);
      return row;
    };

    if (selItem.kind === "text") {
      const xy = Array.isArray(target.xy) ? target.xy : [0, 0];
      addField("标注内容 (text)", makeText(target.text, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.text = v;
      }, `修改标注文本为 "${v}"`)), true);

      addField("X 坐标", makeNumber(xy[0], 0.5, (v) => onMutateSpec((s) => {
        const t = resolveSpecTarget(s, selItem).target;
        t.xy = [v, t.xy?.[1] ?? 0];
      }, `调整文本 X=${v}`)));

      addField("Y 坐标", makeNumber(xy[1], 0.01, (v) => onMutateSpec((s) => {
        const t = resolveSpecTarget(s, selItem).target;
        t.xy = [t.xy?.[0] ?? 0, v];
      }, `调整文本 Y=${v}`)));

      addField("字号 (pt / token)", makeText(target.size ?? "annot", (v) => onMutateSpec((s) => {
        const n = Number(v);
        resolveSpecTarget(s, selItem).target.size = Number.isFinite(n) && v.trim() !== "" ? n : v;
      }, `调整文本字号 ${v}`)));

      addField("颜色", makeColor(target.color || "#000000", (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.color = v;
      }, `修改文本颜色 ${v}`)));
    } else if (selItem.kind === "vline") {
      addField("X 位置 (峰位)", makeNumber(target.x, 1, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.x = v;
      }, `移动虚线至 x=${v}`)));

      addField("线宽 (lw)", makeNumber(target.lw ?? 1.2, 0.2, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.lw = v;
      }, `修改虚线线宽 ${v}`)));

      addField("下端 ymin (0~1)", makeNumber(target.ymin ?? 0.1, 0.02, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.ymin = v;
      }, `修改虚线 ymin=${v}`)));

      addField("上端 ymax (0~1)", makeNumber(target.ymax ?? 0.8, 0.02, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.ymax = v;
      }, `修改虚线 ymax=${v}`)));

      addField("颜色", makeColor(target.color || "#000000", (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.color = v;
      }, `修改虚线颜色 ${v}`)), true);
    } else if (selItem.kind === "legend") {
      const locs = [
        "upper right", "upper left", "lower right", "lower left",
        "upper center", "lower center", "center right", "center left", "best",
      ];
      addField("锚点位置 (loc)", makeSelect(target.loc || "upper right", locs, (v) => onMutateSpec((s) => {
        const leg = resolveSpecTarget(s, selItem).target;
        leg.loc = v;
        delete leg.bbox;
      }, `图例移至 ${v}`)));

      addField("列数 (ncol)", makeNumber(target.ncol ?? 1, 1, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.ncol = Math.max(1, Math.round(v));
      }, `图例列数设为 ${Math.round(v)}`)));

      const bbox = Array.isArray(target.bbox) ? target.bbox : [0.97, 0.97];
      addField("bbox X (0~1)", makeNumber(bbox[0], 0.02, (v) => onMutateSpec((s) => {
        const leg = resolveSpecTarget(s, selItem).target;
        const cur = Array.isArray(leg.bbox) ? leg.bbox : [0.97, 0.97];
        leg.bbox = [v, cur[1]];
      }, `调整图例 bbox X=${v}`)));

      addField("bbox Y (0~1)", makeNumber(bbox[1], 0.02, (v) => onMutateSpec((s) => {
        const leg = resolveSpecTarget(s, selItem).target;
        const cur = Array.isArray(leg.bbox) ? leg.bbox : [0.97, 0.97];
        leg.bbox = [cur[0], v];
      }, `调整图例 bbox Y=${v}`)));
    } else if (selItem.kind === "letter") {
      addField("子图编号", makeText(target.text || "", (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.text = v;
      }, `修改子图编号为 ${v}`)), true);

      addField("相对 X", makeNumber(target.x ?? -0.1, 0.01, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.x = v;
      }, `调整子图编号 X=${v}`)));

      addField("相对 Y", makeNumber(target.y ?? 0.95, 0.01, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.y = v;
      }, `调整子图编号 Y=${v}`)));
    } else {
      // Line / scatter / fill / bar / comb
      addField("图例标签 (label)", makeText(target.label || "", (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.label = v;
      }, `修改曲线标签 "${v}"`)), true);

      addField("颜色 (color)", makeColor(target.color || "#6699BA", (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.color = v;
      }, `修改曲线颜色 ${v}`)));

      addField("线宽 (lw)", makeNumber(target.lw ?? 1.5, 0.2, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.lw = v;
      }, `修改曲线线宽 ${v}`)));

      const curOff = Number(target.offset ?? 0);
      const offSpan = Math.max(0.5, Math.abs(curOff) * 2 + 0.3);
      addField("垂直偏移 (offset)", makeSliderNum(curOff, Number((-offSpan).toFixed(2)), Number(offSpan.toFixed(2)), 0.01, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.offset = v;
      }, `调整曲线偏移 offset=${v}`)), true);

      const curScale = Number(target.scale ?? 1);
      const scaleMax = Math.max(5, curScale * 2);
      addField("纵向缩放 (scale)", makeSliderNum(curScale, 0.1, Number(scaleMax.toFixed(1)), 0.1, (v) => onMutateSpec((s) => {
        resolveSpecTarget(s, selItem).target.scale = v;
      }, `调整曲线缩放 scale=${v}`)), true);
    }

    els.body.appendChild(grid);
  }

  function _buildPanelInspector(container, panelSpec, panelHandle, onMutateSpec) {
    if (!panelSpec) return;
    const grid = document.createElement("div");
    grid.className = "prop-grid";

    const addField = (label, inputEl, full = false) => {
      const wrap = document.createElement("div");
      wrap.className = `prop-field${full ? " full" : ""}`;
      const lbl = document.createElement("label");
      lbl.className = "prop-label";
      lbl.textContent = label;
      wrap.appendChild(lbl);
      wrap.appendChild(inputEl);
      grid.appendChild(wrap);
    };

    const makeNum = (val, step, onCommit) => {
      const inp = document.createElement("input");
      inp.type = "number";
      inp.step = String(step ?? "any");
      inp.className = "prop-input";
      inp.value = val ?? "";
      inp.addEventListener("change", () => {
        const n = parseFloat(inp.value);
        if (Number.isFinite(n)) onCommit(n);
      });
      return inp;
    };

    const pIdx = panelHandle.panel_index;
    const xlim = panelSpec.x?.lim || panelHandle.segments?.[0]?.xlim || [0, 1];
    const ylim = panelSpec.y?.lim || panelHandle.segments?.[0]?.ylim || [0, 1];

    if (!panelSpec.segments) {
      addField("X 范围下限", makeNum(xlim[0], 5, (v) => onMutateSpec((s) => {
        const p = s.panels[pIdx];
        p.x = p.x || {};
        p.x.lim = [v, p.x.lim?.[1] ?? xlim[1]];
      }, `修改 Panel ${panelSpec.id || pIdx} X下限=${v}`)));

      addField("X 范围上限", makeNum(xlim[1], 5, (v) => onMutateSpec((s) => {
        const p = s.panels[pIdx];
        p.x = p.x || {};
        p.x.lim = [p.x.lim?.[0] ?? xlim[0], v];
      }, `修改 Panel ${panelSpec.id || pIdx} X上限=${v}`)));
    }

    addField("Y 范围下限", makeNum(ylim[0], 0.02, (v) => onMutateSpec((s) => {
      const p = s.panels[pIdx];
      p.y = p.y || {};
      p.y.lim = [v, p.y.lim?.[1] ?? ylim[1]];
    }, `修改 Panel ${panelSpec.id || pIdx} Y下限=${v}`)));

    addField("Y 范围上限", makeNum(ylim[1], 0.02, (v) => onMutateSpec((s) => {
      const p = s.panels[pIdx];
      p.y = p.y || {};
      p.y.lim = [p.y.lim?.[0] ?? ylim[0], v];
    }, `修改 Panel ${panelSpec.id || pIdx} Y上限=${v}`)));

    // Broken-axis controls (e.g., broken-axis DRIFTS)
    if (Array.isArray(panelSpec.segments) && panelSpec.segments.length >= 2) {
      const gap = Number(panelSpec.break_gap ?? 0.015);
      const row = document.createElement("div");
      row.className = "prop-slider-row";
      const slider = document.createElement("input");
      slider.type = "range";
      slider.className = "prop-slider";
      slider.min = "0.004";
      slider.max = "0.05";
      slider.step = "0.002";
      slider.value = String(clamp(gap, 0.004, 0.05));
      const num = document.createElement("input");
      num.type = "number";
      num.className = "prop-input prop-slider-num";
      num.step = "0.002";
      num.value = String(gap);
      slider.addEventListener("input", () => { num.value = slider.value; });
      slider.addEventListener("change", () => onMutateSpec((s) => {
        s.panels[pIdx].break_gap = parseFloat(slider.value);
      }, `调整断轴间距 break_gap=${slider.value}`));
      num.addEventListener("change", () => {
        const n = parseFloat(num.value);
        if (Number.isFinite(n)) onMutateSpec((s) => {
          s.panels[pIdx].break_gap = n;
        }, `调整断轴间距 break_gap=${n}`);
      });
      row.appendChild(slider);
      row.appendChild(num);
      addField("断轴间距 (break_gap)", row, true);
    }

    container.appendChild(grid);
  }

  /* ------------------------------------------------------------------------
   * JOURNAL PREFLIGHT CARD
   * ------------------------------------------------------------------------ */
  function renderPreflight(els, bundle) {
    const pf = bundle?.preflight;
    if (!pf) return;

    const colMap = {
      "single-column": "单栏",
      "1.5-column": "1.5栏",
      "double-column": "双栏",
      "wide": "宽幅",
    };
    const colLabel = colMap[pf.column_class] || pf.column_class || "标准";
    const wStr = pf.width_in ? `${Number(pf.width_in).toFixed(2)} in` : "--";

    // Width cell
    els.width.className = `pf-cell${pf.column_class === "wide" ? " state-warn" : ""}`;
    els.width.querySelector(".pf-val").textContent = `${colLabel} (${wStr})`;

    // DPI cell
    els.dpi.className = `pf-cell${pf.dpi_ok ? "" : " state-warn"}`;
    els.dpi.querySelector(".pf-val").textContent = `${pf.dpi || 600} DPI ${pf.dpi_ok ? "✓" : "⚠"}`;

    // Min font cell
    els.font.className = `pf-cell${pf.min_font_ok ? "" : " state-warn"}`;
    const minPt = pf.min_font_pt != null ? `${Number(pf.min_font_pt).toFixed(1)} pt` : ">=6 pt";
    els.font.querySelector(".pf-val").textContent = `${minPt} ${pf.min_font_ok ? "✓" : "⚠"}`;

    // QA / Deconv cell
    const qaOk = Boolean(pf.qa_pass) && pf.deconv_ok !== false;
    els.qa.className = `pf-cell${qaOk ? "" : " state-fail"}`;
    els.qa.querySelector(".pf-val").textContent = qaOk
      ? "0 碰撞 · PASS"
      : `预警 (${bundle?.qa?.violation_boxes?.length || 1} 处)`;

    // Overall pill
    if (!qaOk) {
      els.overall.className = "preflight-overall pf-fail";
      els.overall.textContent = "QA 预警";
    } else if (!pf.dpi_ok || !pf.min_font_ok) {
      els.overall.className = "preflight-overall pf-warn";
      els.overall.textContent = "建议检查";
    } else {
      els.overall.className = "preflight-overall pf-ok";
      els.overall.textContent = "投稿就绪";
    }
  }

  global.WorkbenchInspector = {
    escapeHtml,
    formatChemHtml,
    resolveSpecTarget,
    renderLayerTree,
    renderDataPanel,
    renderInspector,
    renderPreflight,
  };
})(window);
