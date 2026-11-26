<div align="center">

# SciFig Chemistry Charts & Interactive Workbench

**AI Agent Skill · Declarative CLI Engine · Interactive Human-AI GUI Workbench**

[![Release](https://img.shields.io/github/v/release/qwe4559999/scifig-chemistry-charts?label=Release&color=blue)](https://github.com/qwe4559999/scifig-chemistry-charts/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](pyproject.toml)

**English** | [简体中文](README.zh-CN.md)

</div>

An Origin-free, declarative scientific figure engine (`scifig`), 9-type chemistry chart asset library, reusable AI agent skill (`SKILL.md`), and **Interactive Human-AI GUI Workbench** (`scifig-workbench`). Designed for chemistry, catalysis, spectroscopy, deconvolution, and microscopy workflows—supporting automated Agent plotting, reference-free blind generation, and WYSIWYG interactive refinement from a single `spec.json` schema.

![SciFigStudio Interactive Workbench Preview](assets/workbench_preview.png)

*100% synthetic UV-Vis DRS demo (`examples/demo_uvvis_spec.json`) inside SciFigStudio Workbench: Layer Tree & SHA-256 Data Provenance (left), live interactive canvas with draggable handles & local AI command bar (center), and Theme/Palette hot-switcher, Property Inspector, Journal Preflight & bidirectional `spec.json` editor (right).*

---

## Quick Install & Launch (3 Paths)

### Path A — Zero-Install Desktop GUI (GitHub Release)

1. Download **`SciFigStudio-Workbench-v2.1.0-win64.zip`** from [**GitHub Releases**](https://github.com/qwe4559999/scifig-chemistry-charts/releases) (macOS / Linux: download `SciFigStudio-Workbench-v2.1.0-<macos|linux>-portable.tar.gz`).
2. Extract the archive and double-click **`SciFigStudio-Workbench.exe`** (macOS / Linux: run `./launch_workbench.sh`).
3. Your browser opens automatically at `http://127.0.0.1:8765/` (auto-picks a free port if `8765` is busy) with 3 synthetic demos ready to try.

---

### Path B — One-Command / One-Sentence Agent Skill Install *(Includes Full GUI Workbench)*

Native `SKILL.md` support for **Antigravity, DeepSeek Harness, Claude Code, Codex, and Cursor** (also compatible with `npx skills add qwe4559999/scifig-chemistry-charts`). Installing this Skill bundles **all 3 workflows, the `scifig` CLI, 9 chart SOPs, and the full Interactive GUI Workbench**.

**Option 1 — One-Sentence Agent Prompt (copy & paste to your AI Agent):**

> *"Install `https://github.com/qwe4559999/scifig-chemistry-charts` as a skill, install Python requirements, and run `doctor` to verify."*

**Option 2 — One-Command Terminal Install:**

```powershell
# Windows PowerShell (Antigravity global skill; swap target path for other harnesses below)
git clone https://github.com/qwe4559999/scifig-chemistry-charts.git "$env:USERPROFILE\.gemini\antigravity\skills\scifig-chemistry-charts" && python -m pip install -r "$env:USERPROFILE\.gemini\antigravity\skills\scifig-chemistry-charts\requirements.txt" && python -X utf8 "$env:USERPROFILE\.gemini\antigravity\skills\scifig-chemistry-charts\scripts\run_scifig.py" doctor
```

```bash
# macOS / Linux (Antigravity global skill)
git clone https://github.com/qwe4559999/scifig-chemistry-charts.git ~/.gemini/antigravity/skills/scifig-chemistry-charts && python3 -m pip install -r ~/.gemini/antigravity/skills/scifig-chemistry-charts/requirements.txt && python3 -X utf8 ~/.gemini/antigravity/skills/scifig-chemistry-charts/scripts/run_scifig.py doctor
```

| Agent Framework | Recommended Skill Target Path | Notes |
| :--- | :--- | :--- |
| **Antigravity** | `~/.gemini/antigravity/skills/scifig-chemistry-charts` | Global skill auto-discovered across workspaces |
| **DeepSeek Harness / Codex / Cursor** | `.agents/skills/scifig-chemistry-charts` | Project-level or user-level `.agents/skills/` |
| **Claude Code** | `~/.claude/skills/scifig-chemistry-charts` | Global `~/.claude/skills/` or project `.claude/skills/` |
| **Vercel `skills` CLI** | `npx skills add qwe4559999/scifig-chemistry-charts` | Cross-agent discovery via `SKILL.md` |

Once installed, launch the bundled GUI Workbench anytime via `python -X utf8 <skill-dir>/scripts/run_scifig.py workbench --port 8765` (or double-click `launch_workbench.bat` / run `./launch_workbench.sh`).

---

### Path C — Python Package / CLI & Local HTTP REST API

#### 1. Editable / Package Install & CLI Quickstart

```bash
git clone https://github.com/qwe4559999/scifig-chemistry-charts.git
cd scifig-chemistry-charts
pip install -e .                 # Installs `scifig` and `scifig-workbench` commands

scifig doctor                    # Verify assets, fonts & 9 chart templates
scifig workbench --port 8765     # Or run: scifig-workbench

# Mode 1: Render declarative spec + run QA
scifig render examples/demo_uvvis_spec.json -o examples/out --name DemoUV
scifig qa examples/demo_uvvis_spec.json --png examples/out/DemoUV.png

# Mode 2: Blind / No-Reference generation from CSV/instrument file
scifig blind --data examples/demo_eval.csv --chart 01_line-marker-eval --theme journal-nature-arial --caption "Synthetic catalytic evaluation" -o examples/out --name Demo_blind
```

*Built-in 100% synthetic demos in `examples/`*: `demo_uvvis_spec.json` (`06_single-multi-spectrum`), `demo_spec.json` (`01_line-marker-eval`), and `demo_drifts_spec.json` (`07_drifts-broken-stack`).

#### 2. Headless Local HTTP REST API (`--no-open`) for Tool-Calling Harnesses

Start the Workbench backend as a headless local figure microservice (`DeepSeek`, `LangGraph`, `OpenAI Agents`, or custom Tool-Calling pipelines):

```bash
scifig-workbench --no-open --port 8765
```

| Endpoint | Purpose for Programmatic Tool Calling |
| :--- | :--- |
| `POST /api/blind` | Synthesize initial `spec` + preview + `qa` report from `(data_path, chart_id, theme, palette, title)` via `blind_planner`. |
| `POST /api/render` | Render a modified `spec` dict and return updated `qa` collision boxes, draggable `handles`, and `preflight`. |
| `POST /api/ai-command` | Apply bilingual natural-language edits (`spec`, `instruction`) via offline deterministic NLU or configured LLM. |
| `POST /api/auto-fix` | Run `auto_fix_qa` collision/clipping repair and return `actions`, `diff_lines`, and repaired `spec`. |
| `POST /api/export` | Export publication-ready `svg`, `pdf`, `png` (`dpi=600`), `spec`, or SHA-256 `provenance` bytes. |

```python
import json, urllib.request

def post_json(path, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:8765{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if "application/json" in resp.headers.get("Content-Type", "") else raw

state = post_json("/api/blind", {"data_path": "examples/demo_eval.csv", "chart_id": "01_line-marker-eval", "theme": "journal-nature-arial"})
state = post_json("/api/ai-command", {"spec": state["spec"], "instruction": "图例移至左上角"})
if not state["qa"]["pass"]:
    state = post_json("/api/auto-fix", {"spec": state["spec"]})
svg_bytes = post_json("/api/export", {"spec": state["spec"], "format": "svg", "dpi": 600})
```

#### 3. Optional DeepSeek / OpenAI-Compatible LLM Connection in Workbench AI Bar

By default (when `SCIFIG_LLM_API_KEY` is unset), the Workbench AI bar runs **100% offline** using deterministic NLU (`engine_mode: "local_nlu"`). Set these 3 optional environment variables to route free-form commands to DeepSeek or any OpenAI-compatible `/chat/completions` endpoint:

```bash
export SCIFIG_LLM_API_KEY="sk-your-key"
export SCIFIG_LLM_BASE_URL="https://api.deepseek.com/v1"
export SCIFIG_LLM_MODEL="deepseek-chat"
scifig-workbench --port 8765
```

---

## 3 Unified Modes & 9 Chemistry Chart Types

All three modes share one declarative `spec.json` schema, instrument readers (`scifig.readers`), rendering engine (`scifig.engine`), and visual/numerical QA gate (`scifig.qa`):

| Mode | Workflow | Best For |
| :--- | :--- | :--- |
| **Mode 1 — Reference-Anchored** | `render-refs` → `extract-blueprints` → `probe` / `read` → `render` → `qa` / `compare` | 1:1 reproduction of paper figures & journal PDF blueprints |
| **Mode 2 — Blind Generation** | `scifig blind` / `POST /api/blind` (`blind_planner` with up to 3 QA auto-repair cycles) | Zero-reference generation directly from raw CSV / instrument files |
| **Mode 3 — Interactive GUI Workbench** | Drag peak labels/lines/legends/panel letters + AI micro-edits + live QA boxes + 600 DPI export | Human-in-the-loop visual polish with bidirectional `spec.json` sync |

- **9 Canonical Chart SOPs (`assets/charts/`)**:
  1. `01_line-marker-eval` — Catalytic evaluation (conversion, selectivity, byproduct vs T)
  2. `02_stacked-spectra` — Stacked 1D spectra (PXRD, solid-state NMR)
  3. `03_isotherm-psd` — N₂ adsorption–desorption isotherms & `dV/dlog(W)` PSD
  4. `04_deconv-peak-fit` — Seamless (`hspace=0`) stacked deconvolution with vertical-gradient fills (TPD, TPR, NMR)
  5. `05_stacked-bar-comp` — 100% stacked composition bars with gradient fills
  6. `06_single-multi-spectrum` — Unstacked multi-curve spectra with peak guides or EPR hyperfine combs
  7. `07_drifts-broken-stack` — Time-resolved *in situ* DRIFTS stacks (auto broken-axis or unbroken bands)
  8. `08_xps-reverse-deconv` — Reverse binding-energy XPS deconvolution anchored to Shirley background
  9. `09_microscopy-montage` — Tight-gap TEM/HAADF/EDS & SEM raster montages with badges and scale bars
- **Native Instrument Readers (`scifig.readers`)**: `.csv`, `.xlsx`, `.xls`, `.txt`, `.spa` (OMNIC), `.VGD` (Thermo Avantage), `.asc`/`.ras` (Rigaku XRD), `.spc`, Bruker TopSpin (`1r`/`procs`), and `.tif`/`.png`.

---

## Synthetic Visual Asset Library

All swatches and gallery figures are 100% mathematically synthesized via `python -X utf8 -m scifig.build_visual_assets`:

### 12 Atomic Visual Elements
![Atomic Visual Elements](assets/elements_wall.png)

### 9 Chemistry Chart Types
![9 Chemistry Chart Types](assets/gallery_wall.png)

---

## Contributors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/qwe4559999">
        <img src="https://github.com/qwe4559999.png?size=96" width="64" height="64" alt="qwe4559999" /><br />
        <sub><b>qwe4559999</b></sub>
      </a>
    </td>
  </tr>
</table>

## License

[MIT License](LICENSE) — Copyright (c) 2026 `qwe4559999`.
