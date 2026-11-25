# 05_stacked-bar-comp — 100% Stacked Composition Bar Workflow

**Covered Figures:** `Fig4B` (NH₃-TPD acid site relative percentages S1–S4 across Support and Cuₓ-MAZ).

## 1. Data Ingestion
- **Source:** `data/acid_site_comp.xlsx`.
- **Structure:** Row 0 = `Relative percentage / %`, Row 1 = `S1, S2, S3, S4`, Rows 2–5 = `Support`, `Catalyst-A`, `Catalyst-B`, `Catalyst-C`.
- Note: Author-rounded integers for `Support` are `40, 20, 28, 11` (sum = 99%). Keep faithful to source table or record normalization in provenance if scaled to 100%.

## 2. Preprocessing
- **None.** Parse sample labels cleanly into bold mathtext (`Catalyst-A`, etc.).

## 3. Slot Mapping
| Slot | Meaning | Values |
|---|---|---|
| `group` | Sample name on x-axis | `Support`, `Catalyst-A`, `Catalyst-B`, `Catalyst-C` |
| `y` (list) | Component percentages | `["S1", "S2", "S3", "S4"]` |
| `colors` | Component palette (consistent with Fig4A) | `["#B3CDE4", "#CCEAC4", "#FBB4AE", "#DECAE5"]` |

## 4. Layout & Annotations
- **Bars:** Vertical gradient fill (`gradient: true`) matching Origin's lighter-bottom to richer-top shading inside crisp black outlines (`0.4–0.8 pt`).
- **Percentage Labels:** Centered bold numbers (`40`, `20`, `28`, `11`, ...) inside each segment.
- **Legend:** Top horizontal 4-column legend (`S1  S2  S3  S4`) using gradient patches matching the bar segments, positioned cleanly above or inside the top band without clipping.
- **X-Ticks:** 20-degree rotated bold sample names (`ha="right"`).

## 5. QA Checklist
- [ ] Component colors match `Fig4A` (`S1` blue, `S2` green, `S3` salmon, `S4` lilac).
- [ ] Bars show vertical gradient fill and gradient legend patches.
- [ ] Centered bold percentages are legible and never collide with segment borders.
- [ ] Rotated x-tick labels are unclipped at the bottom margin.

## 6. Common Pitfalls
1. **Using flat solid fills** — breaks visual parity with Origin's signature gradient bars in `Fig4B`.
2. **Clipping rotated x-tick labels** — reserve adequate bottom margin (`b >= 0.18–0.22`) for `Catalyst-B` rotated at 20°.
3. **Mixing sample colors into component bars** — component bars must use the 4 acid-site colors (`fill:0..3`), never sample colors.
