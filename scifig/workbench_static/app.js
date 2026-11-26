/**
 * SciFigStudio Interactive Workbench — Main Application Controller
 * Wires all 3 panes to the Python backend (/api/*), manages undo/redo history,
 * bidirectional spec.json sync with line-diff highlighting, QA guardrail alerts,
 * AI local command execution, theme/palette hot-switching, export, and Blind Mode.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const state = {
    catalog: null,
    specId: null,
    spec: null,
    bundle: null,
    selectedId: null,
    activeDataKey: null,
    regionNorm: null,
    collapsedPanels: new Set(),
    lockedHandles: new Set(),
    undoStack: [],
    redoStack: [],
    lastJsonText: "",
    jsonDirty: false,
    busy: false,
  };

  let canvas = null;

  /* ------------------------------------------------------------------------
   * API CLIENT
   * ------------------------------------------------------------------------ */
  async function apiJson(url, opts) {
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({ ok: false, error: `HTTP ${res.status}` }));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || data.message || `请求失败 (${res.status})`);
    }
    return data;
  }

  function cloneSpec(s) {
    return JSON.parse(JSON.stringify(s));
  }

  function setBusy(flag, label) {
    state.busy = flag;
    if (canvas) canvas.setLoading(flag);
    const dot = $("renderDot");
    const txt = $("renderStatusText");
    if (dot) {
      dot.className = `status-dot ${flag ? "dot-busy" : "dot-ok"}`;
    }
    if (txt && label) {
      txt.textContent = label;
    }
  }

  function setErrorStatus(msg) {
    state.busy = false;
    if (canvas) canvas.setLoading(false);
    const dot = $("renderDot");
    const txt = $("renderStatusText");
    if (dot) dot.className = "status-dot dot-err";
    if (txt) txt.textContent = "操作异常";
    showToast(msg, "err");
  }

  /* ------------------------------------------------------------------------
   * HISTORY (UNDO / REDO)
   * ------------------------------------------------------------------------ */
  function pushUndoSnapshot() {
    if (!state.spec) return;
    state.undoStack.push(cloneSpec(state.spec));
    if (state.undoStack.length > 40) state.undoStack.shift();
    state.redoStack = [];
    updateHistoryButtons();
  }

  function updateHistoryButtons() {
    $("btnUndo").disabled = state.undoStack.length === 0;
    $("btnRedo").disabled = state.redoStack.length === 0;
    $("undoCount").textContent = String(state.undoStack.length);
    $("redoCount").textContent = String(state.redoStack.length);
  }

  async function doUndo() {
    if (!state.undoStack.length || state.busy) return;
    const prev = state.undoStack.pop();
    if (state.spec) state.redoStack.push(cloneSpec(state.spec));
    updateHistoryButtons();
    await renderUpdatedSpec(prev, "已撤销上一步操作");
  }

  async function doRedo() {
    if (!state.redoStack.length || state.busy) return;
    const next = state.redoStack.pop();
    if (state.spec) state.undoStack.push(cloneSpec(state.spec));
    updateHistoryButtons();
    await renderUpdatedSpec(next, "已重做操作");
  }

  /* ------------------------------------------------------------------------
   * DIFF TOAST & JSON SYNC HIGHLIGHT
   * ------------------------------------------------------------------------ */
  function showToast(text, level = "ok") {
    const toast = $("diffToast");
    const badge = $("diffToastBadge");
    const body = $("diffToastText");
    toast.classList.remove("hidden", "toast-warn", "toast-err");
    if (level === "warn") {
      toast.classList.add("toast-warn");
      badge.textContent = "⚠ 提示";
    } else if (level === "err") {
      toast.classList.add("toast-err");
      badge.textContent = "✕ 错误";
    } else {
      badge.textContent = "✓ 已同步";
    }
    body.textContent = text;
  }

  function hideToast() {
    $("diffToast").classList.add("hidden");
  }

  function syncJsonEditor(newSpec, highlightSummary) {
    const editor = $("jsonEditor");
    const newText = JSON.stringify(newSpec, null, 2);
    const oldLines = (state.lastJsonText || "").split("\n");
    const newLines = newText.split("\n");

    let firstDiffLine = -1;
    if (state.lastJsonText) {
      const len = Math.max(oldLines.length, newLines.length);
      for (let i = 0; i < len; i++) {
        if (oldLines[i] !== newLines[i]) {
          firstDiffLine = i;
          break;
        }
      }
    }

    editor.value = newText;
    state.lastJsonText = newText;
    state.jsonDirty = false;
    setJsonStatus("valid", "已同步");

    if (firstDiffLine >= 0 && highlightSummary) {
      // Scroll changed line smoothly into upper third of textarea
      const lineHeight = 16.6;
      editor.scrollTop = Math.max(0, (firstDiffLine - 3) * lineHeight);

      // Flash border & banner
      const banner = $("jsonFlashBanner");
      banner.textContent = `已同步更新第 ${firstDiffLine + 1} 行 · ${highlightSummary}`;
      banner.classList.remove("hidden");
      editor.classList.remove("flash-ring");
      void editor.offsetWidth; // trigger reflow for animation restart
      editor.classList.add("flash-ring");

      clearTimeout(syncJsonEditor._timer);
      syncJsonEditor._timer = setTimeout(() => {
        editor.classList.remove("flash-ring");
      }, 1800);
    } else if (!highlightSummary) {
      $("jsonFlashBanner").classList.add("hidden");
    }
  }

  function setJsonStatus(kind, text) {
    const el = $("jsonStatus");
    el.className = `json-status json-${kind}`;
    el.textContent = text;
  }

  /* ------------------------------------------------------------------------
   * QA GUARDRAIL BADGE, BANNER & POPOVER
   * ------------------------------------------------------------------------ */
  function renderQaUI(bundle) {
    const qa = bundle?.qa || { pass: true, violation_boxes: [], errors: [], warnings: [] };
    const badgeBtn = $("qaBadgeBtn");
    const badgeText = $("qaBadgeText");
    const banner = $("canvasQaBanner");
    const bannerMsg = $("canvasQaBannerMsg");
    const popBody = $("qaPopoverBody");

    const vboxes = qa.violation_boxes || [];
    const issueCount =
      (qa.text_overlap_count || 0) +
      (qa.out_of_bounds_count || 0) +
      (qa.legend_data_overlap_count || 0) +
      (qa.errors?.length || 0);
    const displayCount = Math.max(issueCount, vboxes.length);

    if (qa.pass && displayCount === 0) {
      badgeBtn.className = "qa-badge qa-pass";
      badgeText.textContent = "QA: 0 重叠 PASS";
      banner.classList.add("hidden");
      popBody.innerHTML = `<div class="qa-ok-empty">✓ 当前图件零文字重叠、零越界裁剪、图例无遮挡，已通过发表级 QA 护栏。</div>`;
      $("btnPopoverAutoFix").disabled = true;
    } else {
      badgeBtn.className = "qa-badge qa-fail";
      badgeText.textContent = `QA 预警: ${displayCount || 1} 处碰撞/出界`;

      const firstMsg =
        vboxes[0]?.message ||
        qa.errors?.[0] ||
        qa.text_overlaps?.[0] ||
        qa.clipped_texts?.[0] ||
        "检测到文字重叠或标签出界";
      bannerMsg.textContent = `检测到 ${displayCount || 1} 处碰撞/出界：${firstMsg}`;
      banner.classList.remove("hidden");

      popBody.innerHTML = "";
      const items = vboxes.length
        ? vboxes
        : (qa.errors || qa.warnings || ["存在排版冲突"]).map((m) => ({ kind: "qa", message: m }));

      for (const it of items) {
        const div = document.createElement("div");
        div.className = "qa-issue-item";
        div.innerHTML = `<span class="qa-issue-kind">${WorkbenchInspector.escapeHtml(it.kind || "WARN")}</span>${WorkbenchInspector.escapeHtml(it.message || "")}`;
        popBody.appendChild(div);
      }
      $("btnPopoverAutoFix").disabled = false;
    }
  }

  /* ------------------------------------------------------------------------
   * APPLY FULL STATE BUNDLE TO ALL 3 PANES
   * ------------------------------------------------------------------------ */
  function applyStateBundle(bundle, opts = {}) {
    state.bundle = bundle;
    state.specId = bundle.spec_id || state.specId;
    state.spec = bundle.spec;

    // Sync topbar selector if present
    const sel = $("specSelect");
    if (sel && state.specId) {
      const hasOpt = Array.from(sel.options).some((o) => o.value === state.specId);
      if (hasOpt) sel.value = state.specId;
    }

    // Center header dimensions + render time
    const [fw, fh] = bundle.figure_size_in || [
      bundle.spec?.figure?.width_in || 0,
      bundle.spec?.figure?.height_in || 0,
    ];
    const dpi = bundle.spec?.figure?.dpi || 600;
    $("canvasDimPill").textContent = `${Number(fw).toFixed(2)}×${Number(fh).toFixed(2)} in · ${dpi} DPI`;
    setBusy(false, `已同步 · ${bundle.render_ms ?? 0}ms`);

    // Sync Theme & Palette active pills
    const curTheme = bundle.spec?.theme || "origin-times-bold";
    const curPalette = bundle.spec?.palette || "publication-pastel";
    $("themeNamePill").textContent = curTheme;
    document.querySelectorAll("#themePills .theme-pill").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.theme === curTheme);
    });
    document.querySelectorAll("#palettePills .palette-pill").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.palette === curPalette);
    });

    // Validate selectedId still exists
    const allIds = new Set([
      ...(bundle.handles?.panels || []).map((p) => p.id),
      ...(bundle.handles?.items || []).map((it) => it.id),
    ]);
    if (state.selectedId && !allIds.has(state.selectedId)) {
      state.selectedId = null;
    }

    // 1. Canvas + SVG overlay
    canvas.setSelected(state.selectedId);
    canvas.setLockedSet(state.lockedHandles);
    canvas.updateBundle(bundle);

    // 2. Left Pane: Layer Tree & Data Table
    WorkbenchInspector.renderLayerTree(
      $("layerTree"),
      $("layerSummaryPill"),
      bundle,
      state,
      {
        onSelect: handleSelect,
        onToggleVisible: handleToggleVisible,
        onToggleLock: handleToggleLock,
      }
    );
    WorkbenchInspector.renderDataPanel(
      {
        tabs: $("dataTabs"),
        opsStrip: $("dataOpsStrip"),
        tableWrap: $("dataTableWrap"),
        rowCount: $("dataRowCount"),
        provBar: $("provenanceBar"),
        provText: $("provenanceText"),
      },
      bundle,
      state,
      applyDataTab
    );

    // 3. Right Pane: Inspector, Preflight, Bidirectional spec.json
    WorkbenchInspector.renderInspector(
      { crumb: $("selectedCrumb"), body: $("inspectorBody") },
      bundle,
      state.selectedId,
      handleMutateSpec
    );
    WorkbenchInspector.renderPreflight(
      {
        overall: $("preflightOverall"),
        width: $("pfWidth"),
        dpi: $("pfDpi"),
        font: $("pfFont"),
        qa: $("pfQa"),
      },
      bundle
    );
    syncJsonEditor(bundle.spec, opts.highlightSummary || null);

    // 4. QA Guardrail UI
    renderQaUI(bundle);
  }

  function applyDataTab(key) {
    state.activeDataKey = key;
    WorkbenchInspector.renderDataPanel(
      {
        tabs: $("dataTabs"),
        opsStrip: $("dataOpsStrip"),
        tableWrap: $("dataTableWrap"),
        rowCount: $("dataRowCount"),
        provBar: $("provenanceBar"),
        provText: $("provenanceText"),
      },
      state.bundle,
      state,
      applyDataTab
    );
  }

  /* ------------------------------------------------------------------------
   * INTERACTION HANDLERS
   * ------------------------------------------------------------------------ */
  function handleSelect(id) {
    state.selectedId = id;
    canvas.setSelected(id);

    // Highlight in Layer Tree
    document.querySelectorAll("#layerTree .layer-item, #layerTree .layer-panel-row").forEach((el) => {
      el.classList.remove("selected");
    });
    if (id) {
      const targetRow = document.querySelector(`#layerTree [data-handle-id="${CSS.escape(id)}"]`);
      if (targetRow) {
        targetRow.classList.add("selected");
        targetRow.scrollIntoView({ block: "nearest" });
      }
    }

    // Re-render inspector for selected item
    WorkbenchInspector.renderInspector(
      { crumb: $("selectedCrumb"), body: $("inspectorBody") },
      state.bundle,
      state.selectedId,
      handleMutateSpec
    );
  }

  async function renderUpdatedSpec(newSpec, summary) {
    setBusy(true, "引擎重绘中...");
    try {
      const bundle = await apiJson("/api/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec_id: state.specId, spec: newSpec }),
      });
      applyStateBundle(bundle, { highlightSummary: summary });
      if (summary) showToast(summary, bundle.qa?.pass === false ? "warn" : "ok");
    } catch (err) {
      setErrorStatus(`渲染失败: ${err.message}`);
    }
  }

  async function handleMutateSpec(mutator, summary) {
    if (!state.spec || state.busy) return;
    pushUndoSnapshot();
    const next = cloneSpec(state.spec);
    mutator(next);
    await renderUpdatedSpec(next, summary);
  }

  async function handleToggleVisible(item) {
    if (!state.spec || state.busy) return;
    const newVis = item.visible === false ? true : false;
    await handleMutateSpec((s) => {
      const res = WorkbenchInspector.resolveSpecTarget(s, item);
      if (res && res.target) {
        res.target.visible = newVis;
      }
    }, `${newVis ? "显示" : "隐藏"}图层 ${item.label || item.kind}`);
  }

  function handleToggleLock(item) {
    if (state.lockedHandles.has(item.id)) state.lockedHandles.delete(item.id);
    else state.lockedHandles.add(item.id);
    canvas.setLockedSet(state.lockedHandles);
    WorkbenchInspector.renderLayerTree(
      $("layerTree"),
      $("layerSummaryPill"),
      state.bundle,
      state,
      {
        onSelect: handleSelect,
        onToggleVisible: handleToggleVisible,
        onToggleLock: handleToggleLock,
      }
    );
  }

  async function handleDragCommit(item, dxNorm, dyNorm, targetNorm) {
    if (!state.spec || state.busy) return;
    pushUndoSnapshot();
    setBusy(true, "拖拽重绘中...");
    try {
      const res = await apiJson("/api/drag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec_id: state.specId,
          spec: state.spec,
          handle_id: item.id,
          dx_norm: dxNorm,
          dy_norm: dyNorm,
          target_norm: targetNorm,
        }),
      });
      const summary = res.patch_summary || `已拖拽 ${item.label || item.kind}`;
      applyStateBundle(res, { highlightSummary: summary });
      if (res.qa && res.qa.pass === false) {
        showToast(`${summary} · ⚠ 触发 QA 防碰撞预警`, "warn");
      } else {
        showToast(`${summary} · QA PASS`, "ok");
      }
    } catch (err) {
      setErrorStatus(`拖拽更新失败: ${err.message}`);
    }
  }

  async function handleAiCommand(instruction) {
    const cmd = (instruction || "").trim();
    if (!cmd || !state.spec || state.busy) return;

    if (cmd === "__auto_fix__") {
      await handleAutoFix();
      return;
    }

    pushUndoSnapshot();
    setBusy(true, "执行 AI 局部指令...");
    try {
      const selectedHandle = (state.bundle?.handles?.items || []).find((i) => i.id === state.selectedId) || null;
      const res = await apiJson("/api/ai-command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec_id: state.specId,
          spec: state.spec,
          instruction: cmd,
          region_norm: state.regionNorm,
          selected: selectedHandle
            ? { id: selectedHandle.id, kind: selectedHandle.kind, panel_index: selectedHandle.panel_index, plot_index: selectedHandle.plot_index }
            : null,
        }),
      });
      const summary = res.summary || `已执行指令: ${cmd}`;
      applyStateBundle(res, { highlightSummary: summary });
      const qaTag = res.qa?.pass === false ? " · QA 预警" : " · QA PASS";
      showToast(`${summary}${qaTag}`, res.qa?.pass === false ? "warn" : "ok");
    } catch (err) {
      setErrorStatus(`AI 指令执行失败: ${err.message}`);
    }
  }

  async function handleAutoFix() {
    if (!state.spec || state.busy) return;
    pushUndoSnapshot();
    setBusy(true, "自动避让修复中...");
    try {
      const res = await apiJson("/api/auto-fix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec_id: state.specId, spec: state.spec }),
      });
      const summary = res.summary || "已完成一键自动避让修复";
      applyStateBundle(res, { highlightSummary: summary });
      $("qaPopover").classList.add("hidden");
      showToast(`${summary}${res.qa?.pass ? " · QA PASS" : ""}`, res.qa?.pass ? "ok" : "warn");
    } catch (err) {
      setErrorStatus(`自动修复失败: ${err.message}`);
    }
  }

  async function loadSpecById(specId) {
    if (!specId) return;
    setBusy(true, `加载 ${specId}...`);
    try {
      const bundle = await apiJson(`/api/spec?id=${encodeURIComponent(specId)}`);
      state.undoStack = [];
      state.redoStack = [];
      state.selectedId = null;
      state.activeDataKey = null;
      state.regionNorm = null;
      state.lastJsonText = "";
      updateHistoryButtons();
      updateRegionBadge(null);
      canvas.setRegion(null);
      hideToast();
      applyStateBundle(bundle);
    } catch (err) {
      setErrorStatus(`加载图件失败: ${err.message}`);
    }
  }

  async function handleExport(format) {
    if (!state.spec || state.busy) return;
    setBusy(true, `导出 ${format.toUpperCase()}...`);
    try {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec_id: state.specId,
          spec: state.spec,
          format,
          dpi: format === "png" ? 600 : undefined,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const disp = res.headers.get("Content-Disposition") || "";
      const m = disp.match(/filename="?([^"]+)"?/i);
      const baseName = (state.specId || "figure").replace(/[^\w.-]+/g, "_");
      const filename = m ? m[1] : `${baseName}.${format}`;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);

      setBusy(false, `已导出 ${filename}`);
      showToast(`已成功导出 ${filename}`, "ok");
    } catch (err) {
      setErrorStatus(`导出失败: ${err.message}`);
    }
  }

  async function handleSaveSpec() {
    if (!state.spec || state.busy) return;
    setBusy(true, "保存 Spec...");
    try {
      const res = await apiJson("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec_id: state.specId,
          spec: state.spec,
          overwrite: false,
        }),
      });
      setBusy(false, "Spec 已保存");
      showToast(`已保存至 ${res.saved_path || res.spec_id}`, "ok");
    } catch (err) {
      setErrorStatus(`保存失败: ${err.message}`);
    }
  }

  function updateRegionBadge(regionNorm) {
    state.regionNorm = regionNorm;
    const badge = $("regionBadge");
    if (!regionNorm) {
      badge.classList.add("hidden");
      return;
    }
    const [x0, y0, x1, y1] = regionNorm;
    $("regionBadgeText").textContent = `已框选区域 [${x0.toFixed(2)}..${x1.toFixed(2)}, ${y0.toFixed(2)}..${y1.toFixed(2)}]`;
    badge.classList.remove("hidden");
  }

  /* ------------------------------------------------------------------------
   * CATALOG & INITIALIZATION
   * ------------------------------------------------------------------------ */
  function populateCatalog(cat) {
    state.catalog = cat;
    const sel = $("specSelect");
    sel.innerHTML = "";

    const groups = [
      { key: "examples", label: "内置示例 Demos" },
      { key: "saved", label: "已保存 Saved" },
      { key: "blind", label: "Blind Mode 初稿" },
      { key: "main", label: "正文 Main Specs" },
      { key: "si", label: "补充材料 SI Specs" },
    ];

    for (const g of groups) {
      const list = cat.specs?.[g.key] || [];
      if (!list.length) continue;
      const og = document.createElement("optgroup");
      og.label = g.label;
      for (const item of list) {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = `${item.name}${item.chart ? ` · ${item.chart.replace(/^\d+_/, "")}` : ""}`;
        og.appendChild(opt);
      }
      sel.appendChild(og);
    }

    // Populate Blind Mode modal dropdowns
    const chartSel = $("blindChartSelect");
    if (chartSel && Array.isArray(cat.charts) && cat.charts.length) {
      chartSel.innerHTML = "";
      for (const ch of cat.charts) {
        const opt = document.createElement("option");
        opt.value = ch.id;
        opt.textContent = `${ch.id} — ${ch.name}`;
        chartSel.appendChild(opt);
      }
    }

    const sampleSel = $("blindSampleSelect");
    if (sampleSel && Array.isArray(cat.sample_datasets)) {
      sampleSel.innerHTML = `<option value="">-- 选择内置示例数据或手动输入路径 --</option>`;
      for (const sd of cat.sample_datasets) {
        const opt = document.createElement("option");
        opt.value = sd.path;
        opt.dataset.chartId = sd.chart_id || "";
        opt.dataset.title = sd.title || "";
        opt.textContent = sd.label;
        sampleSel.appendChild(opt);
      }
    }

    // Dynamic palette swatches from catalog if provided
    if (Array.isArray(cat.palettes) && cat.palettes.length) {
      const container = $("palettePills");
      container.innerHTML = "";
      for (const pal of cat.palettes.slice(0, 4)) {
        const btn = document.createElement("button");
        btn.className = "palette-pill";
        btn.dataset.palette = pal.id;
        const cols = (pal.sequence || []).slice(0, 4);
        btn.innerHTML = `
          <span class="swatches">${cols.map((c) => `<i style="background:${WorkbenchInspector.escapeHtml(c)}"></i>`).join("")}</span>
          <span>${WorkbenchInspector.escapeHtml(pal.id)}</span>
        `;
        btn.addEventListener("click", () => {
          handleMutateSpec((s) => { s.palette = pal.id; }, `切换色板为 ${pal.id}`);
        });
        container.appendChild(btn);
      }
    }
  }

  function bindUI() {
    // Spec Selector
    $("specSelect").addEventListener("change", (e) => {
      loadSpecById(e.target.value);
    });

    // Undo / Redo
    $("btnUndo").addEventListener("click", doUndo);
    $("btnRedo").addEventListener("click", doRedo);
    $("btnToastUndo").addEventListener("click", doUndo);
    $("btnToastClose").addEventListener("click", hideToast);

    // QA Badge Popover & Auto-Fix buttons
    $("qaBadgeBtn").addEventListener("click", (e) => {
      e.stopPropagation();
      $("qaPopover").classList.toggle("hidden");
    });
    $("btnCloseQaPopover").addEventListener("click", () => {
      $("qaPopover").classList.add("hidden");
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".qa-badge-wrap")) {
        $("qaPopover").classList.add("hidden");
      }
    });
    $("btnPopoverAutoFix").addEventListener("click", handleAutoFix);
    $("btnBannerAutoFix").addEventListener("click", handleAutoFix);

    // Export & Save
    $("btnExportSvg").addEventListener("click", () => handleExport("svg"));
    $("btnExportPdf").addEventListener("click", () => handleExport("pdf"));
    $("btnExportPng").addEventListener("click", () => handleExport("png"));
    $("btnSaveSpec").addEventListener("click", handleSaveSpec);

    // Show All Layers
    $("btnShowAllLayers").addEventListener("click", () => {
      handleMutateSpec((s) => {
        for (const p of s.panels || []) {
          if (p.legend) p.legend.visible = true;
          if (p.letter) p.letter.visible = true;
          for (const pl of p.plots || []) pl.visible = true;
          for (const sub of p.subpanels || []) {
            for (const pl of sub.plots || []) pl.visible = true;
          }
        }
      }, "已恢复显示全部图层");
    });

    // Canvas Mode buttons
    document.querySelectorAll("[data-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.mode;
        document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b === btn));
        canvas.setMode(mode);
      });
    });

    // Canvas Overlay Toggles
    $("chkOverlay").addEventListener("change", (e) => canvas.setOptions({ showOverlay: e.target.checked }));
    $("chkQaBoxes").addEventListener("change", (e) => canvas.setOptions({ showQaBoxes: e.target.checked }));
    $("chkSnap").addEventListener("change", (e) => canvas.setOptions({ enableSnap: e.target.checked }));

    // Zoom controls
    document.querySelectorAll("[data-zoom]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-zoom]").forEach((b) => b.classList.toggle("active", b === btn));
        canvas.setZoom(btn.dataset.zoom === "fit" ? "fit" : parseFloat(btn.dataset.zoom));
      });
    });

    // Clear Box-Select Region
    $("btnClearRegion").addEventListener("click", () => {
      updateRegionBadge(null);
      canvas.setRegion(null);
    });

    // AI Local Instruction Bar & Chips
    $("aiForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = $("aiInput");
      const cmd = input.value.trim();
      if (!cmd) return;
      handleAiCommand(cmd);
    });

    document.querySelectorAll("#aiChips .chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cmd = btn.dataset.cmd;
        if (cmd !== "__auto_fix__") {
          $("aiInput").value = cmd;
        }
        handleAiCommand(cmd);
      });
    });

    // Theme Hot-Switch Pills
    document.querySelectorAll("#themePills .theme-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        const themeId = btn.dataset.theme;
        handleMutateSpec((s) => { s.theme = themeId; }, `热切换主题为 ${themeId}`);
      });
    });

    // Fallback Palette Pill Listeners (in case catalog doesn't override)
    document.querySelectorAll("#palettePills .palette-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        const palId = btn.dataset.palette;
        handleMutateSpec((s) => { s.palette = palId; }, `切换色板为 ${palId}`);
      });
    });

    // Bidirectional spec.json Editor
    const editor = $("jsonEditor");
    editor.addEventListener("input", () => {
      state.jsonDirty = true;
      try {
        JSON.parse(editor.value);
        setJsonStatus("dirty", "待应用 (Ctrl+Enter)");
      } catch {
        setJsonStatus("error", "JSON 语法错误");
      }
    });

    editor.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        applyJsonEditor();
      }
    });

    $("btnApplyJson").addEventListener("click", applyJsonEditor);
    $("btnFormatJson").addEventListener("click", () => {
      try {
        const obj = JSON.parse(editor.value);
        editor.value = JSON.stringify(obj, null, 2);
        setJsonStatus(state.jsonDirty ? "dirty" : "valid", state.jsonDirty ? "已格式化 · 待应用" : "已同步");
      } catch (err) {
        setJsonStatus("error", "无法格式化: 语法错误");
      }
    });

    // Blind Mode Modal
    const openBlind = () => {
      $("blindModalError").classList.add("hidden");
      $("blindModal").classList.remove("hidden");
      $("blindSourceInput").focus();
    };
    const closeBlind = () => $("blindModal").classList.add("hidden");

    $("btnNewBlind").addEventListener("click", openBlind);
    $("btnCloseBlindModal").addEventListener("click", closeBlind);
    $("btnCancelBlind").addEventListener("click", closeBlind);

    $("blindSampleSelect").addEventListener("change", (e) => {
      const opt = e.target.selectedOptions[0];
      if (!opt || !opt.value) return;
      $("blindSourceInput").value = opt.value;
      if (opt.dataset.chartId) $("blindChartSelect").value = opt.dataset.chartId;
      if (opt.dataset.title) $("blindTitleInput").value = opt.dataset.title;
    });

    $("btnSubmitBlind").addEventListener("click", async () => {
      const dataPath = $("blindSourceInput").value.trim();
      const chartId = $("blindChartSelect").value;
      const theme = $("blindThemeSelect").value;
      const title = $("blindTitleInput").value.trim();
      const errBox = $("blindModalError");
      if (!dataPath) {
        errBox.textContent = "请输入数据文件/目录路径，或从上方下拉框选择内置示例。";
        errBox.classList.remove("hidden");
        return;
      }
      errBox.classList.add("hidden");
      setBusy(true, "Blind Planner 盲绘生成中...");
      try {
        const bundle = await apiJson("/api/blind", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_path: dataPath,
            chart_id: chartId,
            theme,
            title: title || undefined,
          }),
        });
        closeBlind();
        state.undoStack = [];
        state.redoStack = [];
        state.selectedId = null;
        state.activeDataKey = null;
        state.lastJsonText = "";
        updateHistoryButtons();
        applyStateBundle(bundle, { highlightSummary: "Blind Mode 盲绘生成完成" });
        showToast(`Blind Mode 已自动生成 ${chartId} 初稿`, "ok");
      } catch (err) {
        setBusy(false, "盲绘失败");
        errBox.textContent = err.message;
        errBox.classList.remove("hidden");
      }
    });

    // Global keyboard shortcuts
    window.addEventListener("keydown", (e) => {
      const tag = document.activeElement?.tagName;
      const inEditable = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleSaveSpec();
      } else if (!inEditable && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !e.shiftKey) {
        e.preventDefault();
        doUndo();
      } else if (!inEditable && (e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))) {
        e.preventDefault();
        doRedo();
      } else if (e.key === "Escape") {
        $("qaPopover").classList.add("hidden");
        $("blindModal").classList.add("hidden");
      }
    });
  }

  async function applyJsonEditor() {
    if (state.busy) return;
    const editor = $("jsonEditor");
    let parsed;
    try {
      parsed = JSON.parse(editor.value);
    } catch (err) {
      setJsonStatus("error", "JSON 语法错误");
      showToast(`JSON 解析失败: ${err.message}`, "err");
      return;
    }
    pushUndoSnapshot();
    await renderUpdatedSpec(parsed, "已从 spec.json 反向同步并重绘画布");
  }

  async function init() {
    canvas = new WorkbenchCanvas({
      stage: $("canvasStage"),
      card: $("figureCard"),
      img: $("figureImg"),
      svg: $("overlaySvg"),
      panelsLayer: $("panelsLayer"),
      handlesLayer: $("handlesLayer"),
      snapGuidesLayer: $("snapGuidesLayer"),
      boxSelectLayer: $("boxSelectLayer"),
      qaOverlayLayer: $("qaOverlayLayer"),
      dragGhostLayer: $("dragGhostLayer"),
      dragHud: $("dragHud"),
      spinner: $("canvasSpinner"),
      onSelect: handleSelect,
      onDragCommit: handleDragCommit,
      onRegionChange: updateRegionBadge,
    });

    bindUI();

    try {
      setBusy(true, "连接 SciFigStudio 引擎...");
      const catalog = await apiJson("/api/catalog");
      populateCatalog(catalog);

      // Support optional ?spec= URL param for easy deep-linking / demo capture
      const params = new URLSearchParams(window.location.search);
      const initialId = params.get("spec") || catalog.default_spec_id || "examples/demo_uvvis_spec";
      await loadSpecById(initialId);
    } catch (err) {
      setErrorStatus(`初始化失败: ${err.message}`);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
