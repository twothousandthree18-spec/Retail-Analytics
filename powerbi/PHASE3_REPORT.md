# Phase 3 Report — Power BI Retail Analytics Layer

**Date:** 13 Aug 2026 · **Status:** COMPLETE — all validation checks PASS

## 1. Objective

Deliver a professional, recruiter-facing Power BI layer on top of the **already
validated** analysis. No second cleaning pipeline and no fabricated figures: every
number traces to the validated `retail_transactions` PostgreSQL table (527,390 rows).

## 2. What was delivered

| Deliverable | Location | Status |
|-------------|----------|--------|
| Star-schema dataset (5 CSVs) | `powerbi/dataset/` | ✅ validated |
| Export script (PostgreSQL → CSVs) | `powerbi/scripts/export_pbi_dataset.py` | ✅ |
| Reconciliation suite (24 checks) | `powerbi/scripts/validate_pbi.py` | ✅ ALL PASS |
| Power BI template (model + 29 measures) | `powerbi/Retail_Analysis.pbit` | ✅ compiled + model inspected |
| TMSL model export | `powerbi/model.bim` | ✅ |
| pbi-tools project (TMDL source) | `powerbi/pbixproj/` | ✅ rebuildable |
| Page build spec (5 pages + drill-through) | `powerbi/pages.md` | ✅ |
| DAX measure catalog (29 measures) | `powerbi/dax_measures.md` | ✅ |
| Data model / column / relationship doc | `powerbi/data_model.md` | ✅ |
| Validation report + limitations | `powerbi/validation.md` | ✅ |
| Static page previews (HTML + PNG) | `powerbi/previews/` | ✅ real data |
| Setup + open instructions | `powerbi/README.md` | ✅ |

## 3. The model (in the .pbit, machine-verified)

- **6 tables:** FactSales, DimDate, DimCustomer, DimProduct, DimCountry, Measures.
- **4 relationships:** DimDate→FactSales, DimCustomer→FactSales,
  DimProduct→FactSales, DimCountry→FactSales (all one-to-many).
- **29 DAX measures** in a dedicated Measures table, grouped in display folders
  (Core KPIs, Value, Customer, Time, Ranking) with currency/percent/integer formats.
- **M data-load queries** for all 5 tables via a `DatasetFolder` parameter —
  zero database dependency when opened.
- sort-by columns (month number, day-of-week number) encoded; date-table
  marking is a one-click step documented in the README.
- Compatibility level 1550.

### Machine-verified model contents
- Tables/columns/partitions/relationships confirmed by decoding the compiled
  `DataModelSchema` (UTF-16) — all 6 tables, 4 relationships, 5 M partitions,
  `DatasetFolder` parameter, `__PBI_TimeIntelligenceEnabled` annotation, and the
  `sortByColumn` mappings are present.
- `model.bim` generated from the same TMDL source deserializes cleanly
  (Tables Editor / XMLA / AAS compatible).

## 4. Validation results (fresh run)

Re-exported from PostgreSQL and re-validated end-to-end on 13 Aug 2026:
**ALL CHECKS PASSED (24/24).**

- Revenue **£10,619,986.68** · Orders **22,064** · Customers **4,339** ·
  Units **5,438,062** · AOV **£481.33** — exact match to SQL/Excel layer.
- Monthly revenue reconciles to the penny for all 13 months.
- RFM segment counts reconcile **100%** with PostgreSQL:
  Hibernating 938 · At Risk 924 · Champions 774 · Loyal 538 · Needs Attention 475 ·
  Potential Loyalists 433 · New Customers 257.
- Repeat rate **65.57%** (2,845 repeat / 1,494 one-time); Customer Revenue
  **£8,887,208.89**; 134,658 unattributed line items preserved and documented.
- 0 referential-integrity orphans; DimDate/DimCountry cover all fact values.

## 5. How the pages get built

The `.pbit` contains the tested model but **no visual pages** — the authoring
environment had no Power BI Desktop, so an untested layout was deliberately not
shipped. `pages.md` specifies each of the 5 pages (visual type, fields, measures,
filters, interactivity) and `previews/` provides pixel-accurate design references
rendered with real numbers. Assembling the report from the spec takes ~15 minutes
in Power BI Desktop; the README walks through opening the template, pointing the
`DatasetFolder` parameter at `powerbi/dataset/`, and marking the date table.

## 6. Known limitations (documented, not hidden)

1. **Cancellation Rate is excluded** — zero cancellable invoices survive
   cleaning; the metric is not supportable from validated data.
2. **YoY growth** is only meaningful for Dec 2011 (Dec 2010–Dec 2011 window).
3. **Total Revenue vs Customer Revenue** — both surfaced, never conflated.
4. Report pages not embedded in the `.pbit` (no Power BI Desktop) — build per spec.
5. Date-table marking not serialized headlessly — one click in Desktop.

## 7. Reproduce everything

```powershell
# 1. Regenerate the dataset from PostgreSQL (validated source of truth)
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/retail_analysis"
python powerbi/scripts/export_pbi_dataset.py

# 2. Prove it still reconciles
python powerbi/scripts/validate_pbi.py

# 3. Rebuild the template + interop model (pbi-tools Core, no Desktop needed)
pbi-tools compile powerbi/pbixproj powerbi/Retail_Analysis.pbit -format PBIT -overwrite
pbi-tools convert powerbi/pbixproj/Model powerbi/model.bim -overwrite

# 4. Refresh the static previews
python powerbi/scripts/generate_preview.py
```

Phase 4 is **not** started, per scope.
