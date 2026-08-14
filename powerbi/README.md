# Power BI — Retail Analytics Layer (Phase 3 + Phase 4)

A professional, validated Power BI deliverable built **on top of the already
validated analysis** (Excel 23-sheet workbook + PostgreSQL advanced SQL layer).
Nothing is re-cleaned or recalculated here — every number traces to the validated
`retail_transactions` table (527,390 rows).

## Deliverables

| File | Description |
|------|-------------|
| `Retail_Analysis.pbit` | **Power BI template** — open in Power BI Desktop, point it at `powerbi/dataset/`, refresh. Contains the complete star-schema model + cohort tables, 4 relationships, 35 DAX measures and all data-load queries (see "What's in the .pbit"). |
| `model.bim` | TMSL model export of the same model (Tabular Editor / XMLA / AAS interop). |
| `pbixproj/` | pbi-tools project (TMDL) that generates the above — fully source-controlled, rebuildable. |
| `dataset/` | Power BI-ready CSVs: FactSales (527,390), DimDate (730), DimCustomer (4,339, RFM), DimProduct (3,947), DimCountry (38), CohortRetention (91), CohortSummary (13). |
| `scripts/export_pbi_dataset.py` | Regenerates `dataset/` straight from PostgreSQL. |
| `scripts/validate_pbi.py` | Reconciles `dataset/` against PostgreSQL/SQL figures (37 checks, all PASS). |
| `data_model.md` | Star-schema + cohort table design, columns, relationships, region groupings. |
| `dax_measures.md` | All 35 measures with business purpose and formatting. |
| `pages.md` | Full page-by-page spec for the 7 report pages (6 report pages + drill-through). |
| `validation.md` | Validation report: benchmarks, RFM + cohort reconciliation, limitations. |
| `previews/` | Portfolio-ready previews of all 6 report pages (fixed 1280×800 canvas, **zero overflow**, QA-verified) rendered with real validated data — HTML + PNG screenshots + the `generate_preview.py` script. |

## Open the .pbit in Power BI Desktop (2 minutes)

1. Install **Power BI Desktop** (free) from the Microsoft Store or `aka.ms/pbidesktop`.
2. Open `Retail_Analysis.pbit`.
3. Power BI asks for the **DatasetFolder** parameter → point it to the
   `powerbi/dataset/` folder on your machine (copy the repo folder anywhere; the
   value is saved with the file).
4. Click **Apply** and allow the refresh — Power BI connects to the 5 CSVs and
   loads the model.
5. Optional best-practice (1 click): in **Model view**, select the **DimDate**
   table → **Table tools → Mark as date table → Mark as date table** with
   `date` selected. (Time-intelligence measures work either way, because the
   fact-to-date relationship is already on a date column.)

The model is then ready: 8 tables, 4 relationships, 35 measures in a dedicated
**Measures** table. Build the visual pages using `pages.md` (each spec lists the
exact visuals, fields and measures per page).

## What's in the .pbit (and what isn't)

**Included** — validated by inspecting the compiled package:
- FactSales, DimDate, DimCustomer (validated RFM quartiles + 7 segments),
  DimProduct, DimCountry, Measures — plus the Phase 4 cohort tables
  **CohortRetention** (91 rows) and **CohortSummary** (13 rows).
- 4 one-to-many relationships (DimDate → FactSales, DimCustomer → FactSales,
  DimProduct → FactSales, DimCountry → FactSales). The cohort tables are
  standalone (already aggregated in SQL — no relationships needed).
- 35 DAX measures (Core KPIs, Value, Customer, Time, Ranking, Cohort) with
  currency / percent / integer formatting and display folders.
- M data-load queries for all 7 tables via the `DatasetFolder` parameter.

**Not included (honest note):** visual report pages. This project was authored in
an environment **without Power BI Desktop**, so no `.pbix` visual layouts could be
hand-built or validated. Instead of shipping an untested layout, the deliverable
is the fully-tested model + a precise build spec (`pages.md`) — the pages take
~15 minutes to assemble from the spec. This is deliberate: a broken visual layout
is worse than none.

## Preview the dashboards (before you build them)

`previews/` contains static, no-JS HTML renderings of all 6 report pages **using
the real validated numbers** (open the `.html` files in any browser), plus PNG
screenshots. The pages are engineered to a fixed **1280×800 canvas** — no
horizontal or vertical scrolling, no clipped labels — and are machine-checked
before export: every page embeds a QA probe that flags any element overflowing
the canvas (all 6 currently **QA_OK**). They follow the `pages.md` design
language (navy + gold) and double as the layout reference for assembling the
report in Power BI Desktop. Regenerate after a data refresh with:

```
python powerbi/scripts/generate_preview.py
```

> Notable genuine data findings surfaced in the previews (not invented):
> **Saturday has no transactions** in the source (0 trading days in
> Dec 2010–Dec 2011), so the weekday chart shows Saturday at £0 with a footnote;
> Sunday is real trading (£0.81m / 50 days). Region shares are mutually exclusive
> and sum to **100.0%** (UK & Ireland 87.4% · Europe 10.3% · Asia Pacific 2.0% ·
> Other Markets 0.3%). Page 6's cohort heatmap shows **M0 = 100%** for every
> cohort by construction and **future months blank** (never 0%): weighted M1
> retention is **22.7%** and the founding Dec 2010 cohort rebounds to **50.3%**
> at M11 (November 2011 peak season).

## Why PostgreSQL is the primary source

The PBIT is wired to the exported `dataset/` CSVs so it works with zero database
dependencies (this is the documented **fallback path**). The same tables can be
built by pointing Power BI at PostgreSQL (`retail_transactions`) — all columns
exist in the source table and every CSV is a byte-for-byte projection of it
(`validate_pbi.py` proves this to the penny).

## Field mapping (Excel workbook → Power BI)

| Excel sheet | Power BI table | Notes |
|-------------|----------------|-------|
| Cleaned Data | FactSales | Row-level facts |
| Customer Cohort Analysis | CohortRetention | Phase 4 — retention % matrix (91 cells) |
| Cohort Customer Counts | — | Source data for CohortRetention counts (same rows) |
| Cohort Revenue Analysis | CohortSummary | Phase 4 — 13 cohort lifecycle rows + revenue-by-age |
| Monthly Sales / Annual Revenue | — (recomputed) | Same numbers via `Total Revenue` + DimDate |
| Customer Segmentation / RFM 1 / RFM 2 / RFM 3 | DimCustomer | RFM quartiles + segment, 100% reconciled |
| Country Overview / Cancellation per Country / Top 10 Cancellations | DimCountry | Cancellation sheets come from pre-cleaning data and are **not** reproducible from validated data — see `validation.md` |
| Product info sheets | DimProduct | |

## Validation at a glance

- Revenue **£10,619,986.68** · Orders **22,064** · Customers **4,339** · Units **5,438,062** · AOV **£481.33** — all match the SQL/Excel layer exactly.
- RFM segment counts **reconcile 100%** with PostgreSQL and the workbook.
- Monthly revenue reconciles to the penny across all 13 months.
- Repeat Customer Rate **65.57%**; Customer Revenue (attributed) **£8,887,208.89**.
- **Phase 4 cohort tables reconcile 100%** with SQL: CohortSummary = 13 rows,
  CohortRetention = 91 rows, cohort sizes sum to 4,339, every cohort M0 = 100%,
  SQL-vs-pandas retention deviation ≤ 0.00 pp and revenue to the penny
  (`sql/cohort_validation.py`, 12/12 PASS). The weighted retention series
  (M0..M12 — the decay chart's `Retention Rate`) reconciles to 0.00 pp against
  SQL/Pandas. Weighted M1 retention **22.7%**, 6-month retention **27.2%**,
  founding-cohort repeat rate **87.5%**.

Run `scripts/validate_pbi.py` yourself to reproduce the full report.

## Limitations (documented, not hidden)

1. **Cancellation Rate is excluded** — zero cancellation-only invoices survive
   cleaning; the metric is unsupportable from validated data and would be fabricated.
2. **YoY growth** is only meaningful for Dec 2011 (data spans Dec 2010–Dec 2011).
3. **Total Revenue** includes 134,658 unattributed line items; **Customer Revenue**
   (£8,887,208.89) excludes them. Both are surfaced, never conflated.
