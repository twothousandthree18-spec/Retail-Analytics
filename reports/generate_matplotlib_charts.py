"""
generate_matplotlib_charts.py — Independent Python analytical visualizations
(MATPLOTLIB ONLY — no seaborn, no plotly).

Reads the project's already-validated data layers and renders presentation-
quality PNG charts to reports/matplotlib/:

    1. monthly_revenue.png            <- powerbi/dataset/FactSales.csv
    2. monthly_orders.png             <- powerbi/dataset/FactSales.csv
    3. revenue_by_country.png         <- powerbi/dataset/FactSales.csv
    4. rfm_segment_distribution.png   <- powerbi/dataset/DimCustomer.csv
    5. cohort_retention_heatmap.png   <- powerbi/dataset/CohortRetention.csv
    6. top_products_revenue.png       <- powerbi/dataset/FactSales.csv + DimProduct.csv
    7. churn_risk_distribution.png    <- reports/ml_predictions_temporal.csv (W2)
    8. churn_feature_importance.png   <- reports/ml_feature_importance.csv

Nothing is recomputed differently and no analytical logic is changed: the
script only aggregates the validated tables for display and asserts that the
headline values reconcile with the project's verified results before writing.

Run:
    python reports/generate_matplotlib_charts.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "powerbi" / "dataset"
REPORTS = ROOT / "reports"
OUT = REPORTS / "matplotlib"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "#2F5D8C"
BASE_LIGHT = "#7FA6C9"
GREEN = "#4C9F70"
AMBER = "#D9A441"
RED = "#C0392B"
TEAL = "#2E7D6B"
GREY = "#666666"

EXPECTED = {
    "rows": 527_390,
    "revenue": 10_619_986.68,
    "orders": 22_064,
    "customers": 4_339,
    "w2_total": 2_813,
    "risk": {"HIGH": 1_114, "MEDIUM": 864, "LOW": 835},
}


def gbp_short(x, _pos=None) -> str:
    if abs(x) >= 1_000_000:
        return f"\u00a3{x/1e6:,.2f}M"
    if abs(x) >= 1_000:
        return f"\u00a3{x/1e3:,.0f}K"
    return f"\u00a3{x:,.0f}"


def month_label(ts: pd.Timestamp) -> str:
    return ts.strftime("%b %Y")


def style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#999999")
    ax.tick_params(colors="#444444", labelsize=9)


def titles(fig, ax, title: str, subtitle: str, footnote: str | None = None) -> None:
    fig.suptitle(title, fontsize=14, fontweight="bold", color="#222222", x=0.02, ha="left")
    ax.set_title(subtitle, fontsize=10, color=GREY, loc="left", pad=12)
    if footnote:
        fig.text(0.02, 0.015, footnote, fontsize=8, color="#888888")


def load_data():
    sales = pd.read_csv(
        DS / "FactSales.csv",
        dtype={"invoice_no": str},
        parse_dates=["invoice_date"],
    )
    customers = pd.read_csv(DS / "DimCustomer.csv")
    retention = pd.read_csv(DS / "CohortRetention.csv")
    products = pd.read_csv(DS / "DimProduct.csv")
    preds = pd.read_csv(REPORTS / "ml_predictions_temporal.csv")
    feat = pd.read_csv(REPORTS / "ml_feature_importance.csv")
    return sales, customers, retention, products, preds, feat


def validate(sales, customers, retention, preds, feat) -> None:
    assert len(sales) == EXPECTED["rows"], f"rows {len(sales)}"
    rev = round(float(sales["total_price"].sum()), 2)
    assert abs(rev - EXPECTED["revenue"]) < 0.01, f"revenue {rev}"
    orders = int(sales["invoice_no"].nunique())
    assert orders == EXPECTED["orders"], f"orders {orders}"
    assert len(customers) == EXPECTED["customers"], f"customers {len(customers)}"
    seg_counts = customers["segment"].value_counts()
    assert len(seg_counts) == 7 and int(seg_counts.sum()) == EXPECTED["customers"]
    cohorts = sorted(retention["cohort_month"].unique())
    assert len(cohorts) == 13 and len(retention) == 91
    assert int(preds["risk"].value_counts().sum()) == EXPECTED["w2_total"]
    for band, n in EXPECTED["risk"].items():
        got = int((preds["risk"] == band).sum())
        assert got == n, f"{band} {got}"
    assert len(feat) == 18 and {"feature", "coefficient"}.issubset(feat.columns)

    print("Validation vs verified project results:")
    print(f"  transactions      {len(sales):>9,}  (expected {EXPECTED['rows']:,})")
    print(f"  revenue           \u00a3{rev:>12,.2f}  (expected \u00a3{EXPECTED['revenue']:,.2f})")
    print(f"  orders            {orders:>9,}  (expected {EXPECTED['orders']:,})")
    print(f"  customers         {len(customers):>9,}  (expected {EXPECTED['customers']:,})")
    print(f"  RFM segments              7  (expected 7)")
    print(f"  cohort cells             91  (expected 91)")
    print(f"  W2 risk HIGH/MED/LOW     {EXPECTED['risk']['HIGH']}/{EXPECTED['risk']['MEDIUM']}/{EXPECTED['risk']['LOW']}  (expected same)")
    print("  ALL CHECKS PASSED")


def chart_monthly_revenue(sales: pd.DataFrame) -> None:
    m = sales.set_index("invoice_date")["total_price"].resample("MS").sum()
    x = np.arange(len(m))
    labels = [month_label(ts) for ts in m.index]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(x, m.values, color=BASE, linewidth=2.2, marker="o", markersize=5,
            markerfacecolor="white", markeredgewidth=1.6, zorder=3)
    ax.fill_between(x, m.values, color=BASE, alpha=0.10, zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(gbp_short))
    ax.grid(axis="y", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel("Revenue", fontsize=10)

    peak_i = int(np.argmax(m.values))
    ax.annotate(
        f"Peak: {gbp_short(m.values[peak_i])}",
        xy=(peak_i, m.values[peak_i]),
        xytext=(peak_i - 2.4, m.values[peak_i] * 0.97),
        fontsize=9.5,
        fontweight="bold",
        color="#222222",
        arrowprops=dict(arrowstyle="-", color="#999999", lw=0.9),
    )
    ax.annotate("partial month\n(to 9 Dec)", xy=(len(m) - 1, m.values[-1]),
                xytext=(len(m) - 2.1, m.values[-1] * 1.28),
                fontsize=8.5, color=GREY, ha="center")

    titles(
        fig, ax,
        "Monthly Revenue Trend",
        "Cleaned transaction revenue per calendar month, Dec 2010 \u2013 Dec 2011",
        "Source: powerbi/dataset/FactSales.csv (validated against PostgreSQL; total \u00a310,619,986.68 across all months)",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "monthly_revenue.png", facecolor="white")
    plt.close(fig)


def chart_monthly_orders(sales: pd.DataFrame) -> None:
    m = sales.groupby(pd.Grouper(key="invoice_date", freq="MS"))["invoice_no"].nunique()
    x = np.arange(len(m))
    labels = [month_label(ts) for ts in m.index]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    bars = ax.bar(x, m.values, width=0.62, color=BASE_LIGHT, edgecolor="white", zorder=3)
    bars[int(np.argmax(m.values))].set_color(BASE)
    for xi, v in zip(x, m.values):
        ax.text(xi, v + 45, f"{v:,}", ha="center", va="bottom", fontsize=8, color="#333333")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.grid(axis="y", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel("Orders (distinct invoices)", fontsize=10)
    ax.set_ylim(0, m.max() * 1.14)

    titles(
        fig, ax,
        "Monthly Order Trend",
        "Distinct invoices per calendar month \u2014 22,064 orders in total",
        "Source: powerbi/dataset/FactSales.csv \u00b7 peak month Nov 2011 (3,021 orders) \u00b7 Dec 2011 partial",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "monthly_orders.png", facecolor="white")
    plt.close(fig)


def chart_revenue_by_country(sales: pd.DataFrame) -> None:
    c = sales.groupby("country")["total_price"].sum().sort_values(ascending=True).tail(10)
    total = float(sales["total_price"].sum())

    fig, ax = plt.subplots(figsize=(9.5, 5.5), dpi=150)
    colors = [BASE if name == "United Kingdom" else BASE_LIGHT for name in c.index]
    ax.barh(c.index, c.values, height=0.62, color=colors, zorder=3)
    xmax = c.values.max()
    ax.set_xlim(0, xmax * 1.30)
    for i, (name, v) in enumerate(c.items()):
        share = v / total * 100
        label = f"{gbp_short(v)}  ({share:.1f}%)" if share >= 50 else gbp_short(v)
        ax.text(v + xmax * 0.015, i, label, va="center", fontsize=9,
                color="#333333", fontweight="bold" if share >= 50 else "normal")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(gbp_short))
    ax.grid(axis="x", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Revenue", fontsize=10)

    titles(
        fig, ax,
        "Revenue by Country \u2014 Top 10",
        "The United Kingdom alone generates 84.6% of total revenue (\u00a38.98M of \u00a310.62M)",
        "Source: powerbi/dataset/FactSales.csv \u00b7 38 countries with sales; top 10 shown",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "revenue_by_country.png", facecolor="white")
    plt.close(fig)


def chart_rfm_segments(customers: pd.DataFrame) -> None:
    s = customers["segment"].value_counts().sort_values()
    total = int(s.sum())

    fig, ax = plt.subplots(figsize=(9.5, 5.5), dpi=150)
    highlight = {"Champions"}
    colors = [BASE if name in highlight else BASE_LIGHT for name in s.index]
    ax.barh(s.index, s.values, height=0.62, color=colors, zorder=3)
    for i, (name, v) in enumerate(s.items()):
        ax.text(v + total * 0.006, i, f"{v:,}  ({v/total*100:.1f}%)",
                va="center", fontsize=9, color="#333333")
    ax.set_xlim(0, s.max() * 1.22)
    ax.grid(axis="x", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Customers", fontsize=10)
    ax.xaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))

    titles(
        fig, ax,
        "RFM Customer Segment Distribution",
        f"All {total:,} attributed customers mapped to seven RFM segments",
        "Source: powerbi/dataset/DimCustomer.csv \u00b7 segment rules identical across Python, SQL and Excel (100% reconciliation)",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "rfm_segment_distribution.png", facecolor="white")
    plt.close(fig)


def chart_cohort_heatmap(retention: pd.DataFrame) -> None:
    mat = retention.pivot(index="cohort_month", columns="cohort_index", values="retention_pct")
    mat = mat.reindex(columns=range(13))
    ylabels = [pd.Timestamp(ym + "-01").strftime("%b %Y") for ym in mat.index]
    data = mat.to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(11.5, 6.5), dpi=150)
    cmap = matplotlib.colormaps["Blues"].copy()
    cmap.set_bad("#F2F2F2")
    im = ax.imshow(data, cmap=cmap, vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(13))
    ax.set_xticklabels([f"M{i}" for i in range(13)], fontsize=9)
    ax.set_yticks(range(len(ylabels)))
    ax.set_yticklabels(ylabels, fontsize=9)
    ax.set_xlabel("Months since first purchase", fontsize=10)
    ax.set_ylabel("Acquisition cohort", fontsize=10)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if np.isnan(v):
                continue
            txt_color = "white" if v >= 50 else "#1B2A3B"
            weight = "bold" if j == 0 or v >= 40 else "normal"
            ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                    fontsize=8, color=txt_color, fontweight=weight)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_xticks(np.arange(-0.5, 13, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(ylabels), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4)
    ax.tick_params(which="minor", length=0)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("% of cohort active", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    cbar.outline.set_visible(False)

    titles(
        fig, ax,
        "Cohort Retention Heatmap \u2014 M0\u2013M12",
        "Share of each acquisition cohort active in each month since first purchase (13 cohorts, Dec 2010 \u2013 Dec 2011)",
        "Blank cells = periods after the end of the data window (future), never 0% \u00b7 M1 weighted retention 22.7% \u00b7 source: powerbi/dataset/CohortRetention.csv",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "cohort_retention_heatmap.png", facecolor="white")
    plt.close(fig)


def chart_top_products(sales: pd.DataFrame, products: pd.DataFrame) -> None:
    top = sales.groupby("stock_code")["total_price"].sum().sort_values(ascending=True).tail(10)
    desc = products.set_index("stock_code")["description"].to_dict()

    def label(code: str) -> str:
        d = str(desc.get(code, code)).strip()
        if len(d) > 30:
            d = d[:29] + "\u2026"
        return f"{d} ({code})"

    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=150)
    ax.barh([label(c) for c in top.index], top.values, height=0.62,
            color=[BASE if i == len(top) - 1 else BASE_LIGHT for i in range(len(top))], zorder=3)
    xmax = top.values.max()
    ax.set_xlim(0, xmax * 1.16)
    for i, v in enumerate(top.values):
        ax.text(v + xmax * 0.012, i, gbp_short(v), va="center", fontsize=9, color="#333333")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(gbp_short))
    ax.grid(axis="x", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("Revenue", fontsize=10)
    ax.tick_params(axis="y", labelsize=9)

    titles(
        fig, ax,
        "Top 10 Products by Revenue",
        "Highest-revenue stock codes over the full window \u2014 led by 'Dotcom Postage' (\u00a3206K)",
        "Source: powerbi/dataset/FactSales.csv + DimProduct.csv \u00b7 rankings include operational lines (postage/manual), consistent with the SQL layer",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "top_products_revenue.png", facecolor="white")
    plt.close(fig)


def chart_churn_risk(preds: pd.DataFrame) -> None:
    order = ["LOW", "MEDIUM", "HIGH"]
    counts = preds["risk"].value_counts().reindex(order)
    colors = [GREEN, AMBER, RED]
    total = int(counts.sum())

    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=150)
    bars = ax.bar(order, counts.values, width=0.55, color=colors, zorder=3)
    for b, v in zip(bars, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, v + total * 0.012,
                f"{v:,}\n({v/total*100:.1f}%)", ha="center", va="bottom",
                fontsize=10, fontweight="bold", color="#333333")
    ax.set_ylim(0, counts.max() * 1.24)
    ax.set_ylabel("W2 customers", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="y", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(["LOW risk", "MEDIUM risk", "HIGH risk"], fontsize=10)

    titles(
        fig, ax,
        "Predicted Churn-Risk Distribution \u2014 W2 Holdout",
        "Risk bands from the final logistic-regression model on the 2,813-customer out-of-time holdout",
        "Source: reports/ml_predictions_temporal.csv \u00b7 W2 ROC-AUC 0.7332 \u00b7 PR-AUC 0.5945 \u00b7 recall 79.41%",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "churn_risk_distribution.png", facecolor="white")
    plt.close(fig)


def chart_feature_importance(feat: pd.DataFrame) -> None:
    f = feat.reindex(feat["coefficient"].abs().sort_values(ascending=False).index)
    names = f["feature"].tolist()[::-1]
    coefs = f["coefficient"].tolist()[::-1]
    colors = [RED if c > 0 else TEAL for c in coefs]

    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=150)
    ax.barh(names, coefs, height=0.62, color=colors, zorder=3)
    span = max(abs(min(coefs)), abs(max(coefs)))
    ax.set_xlim(-span * 1.22, span * 1.22)
    ax.axvline(0, color="#888888", linewidth=1)
    for i, c in enumerate(coefs):
        off = span * 0.02 if c >= 0 else -span * 0.02
        ax.text(c + off, i, f"{c:+.2f}", va="center",
                ha="left" if c >= 0 else "right", fontsize=8.5, color="#333333")
    ax.set_xlabel("Standardised logistic-regression coefficient", fontsize=10)
    ax.grid(axis="x", color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=9)

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=RED, alpha=0.85),
        plt.Rectangle((0, 0), 1, 1, color=TEAL, alpha=0.85),
    ]
    ax.legend(handles, ["associated with HIGHER churn risk (+)", "associated with LOWER churn risk (\u2212)"],
              loc="lower right", fontsize=8.5, frameon=False)

    titles(
        fig, ax,
        "Churn Model Feature Importance (Coefficients)",
        "Signed standardised coefficients of the final logistic-regression churn model (18 features)",
        "Association, not causation \u00b7 source: reports/ml_feature_importance.csv \u00b7 model: tuned Logistic Regression (C=0.1)",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "churn_feature_importance.png", facecolor="white")
    plt.close(fig)


def main() -> None:
    sales, customers, retention, products, preds, feat = load_data()
    validate(sales, customers, retention, preds, feat)

    chart_monthly_revenue(sales)
    print("  wrote monthly_revenue.png")
    chart_monthly_orders(sales)
    print("  wrote monthly_orders.png")
    chart_revenue_by_country(sales)
    print("  wrote revenue_by_country.png")
    chart_rfm_segments(customers)
    print("  wrote rfm_segment_distribution.png")
    chart_cohort_heatmap(retention)
    print("  wrote cohort_retention_heatmap.png")
    chart_top_products(sales, products)
    print("  wrote top_products_revenue.png")
    chart_churn_risk(preds)
    print("  wrote churn_risk_distribution.png")
    chart_feature_importance(feat)
    print("  wrote churn_feature_importance.png")

    print(f"Done \u2014 8 charts in {OUT}")


if __name__ == "__main__":
    main()
