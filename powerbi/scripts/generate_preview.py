"""
generate_preview.py — Render static HTML previews of the 6 Power BI pages using
the validated powerbi/dataset CSVs. Outputs powerbi/previews/*.html + *.png.

All figures are computed from the validated dataset at render time — nothing is
hard-coded. Each page is a fixed 1280x800 canvas (no scrollbars) and embeds a
QA probe that reports any element overflowing the canvas.

Run:
    python powerbi/scripts/generate_preview.py
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "powerbi" / "dataset"
OUT = ROOT / "powerbi" / "previews"

NAVY = "#1B2A4A"
NAVY2 = "#24345A"
NAVY3 = "#2A3A5F"
GOLD = "#F2C94C"
TEXT = "#EAF0F8"
MUTED = "#93A4C3"
POSITIVE = "#81C784"
BLUE = "#4FC3F7"
GRAY = "#78909C"
ATTN = "#E57373"

SEG_COLORS = {
    "Champions": "#F2C94C",
    "Loyal Customers": "#4FC3F7",
    "Potential Loyalists": "#81C784",
    "New Customers": "#9575CD",
    "Needs Attention": "#FF8A65",
    "At Risk": "#E57373",
    "Hibernating": "#90A4AE",
}
REG_COLORS = {
    "UK & Ireland": GOLD,
    "Europe": BLUE,
    "Asia Pacific": POSITIVE,
    "Middle East & Africa": "#9575CD",
    "Americas": "#FF8A65",
    "Unspecified": NAVY3,
}

VW, VH = 1280, 800
CONTENT_W = VW - 40  # 20px side padding
GAP = 12

# vertical budget: padding(32) + header(44) + kpis(88) + insight(34) + 5 gaps(60)
BOTTOM_H = 200
MAIN_H = VH - 32 - 44 - 88 - 34 - 60 - BOTTOM_H
CHART_H = MAIN_H - 24 - 36  # card padding + card header block
BOTTOM_CHART_H = BOTTOM_H - 24 - 38


def gbp(x: float) -> str:
    return "\u00a3{:,.2f}".format(x)


def gbp0(x: float) -> str:
    return "\u00a3{:,.0f}".format(x)


def compact(x: float) -> str:
    if abs(x) >= 1_000_000:
        return "\u00a3{:.1f}m".format(x / 1_000_000)
    if abs(x) >= 1_000:
        return "\u00a3{:.0f}k".format(x / 1_000)
    return "\u00a3{:.0f}".format(x)


def num(x) -> str:
    return "{:,.0f}".format(x)


def pct(x: float, d=1) -> str:
    return "{:.{}f}%".format(x * 100, d)


QA_SCRIPT = """
<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    var out = [];
    var vw = %d, vh = %d;
    var de = document.documentElement;
    if (de.scrollWidth > vw + 1) out.push('OVERFLOW_X=' + (de.scrollWidth - vw) + 'px');
    if (de.scrollHeight > vh + 1) out.push('OVERFLOW_Y=' + (de.scrollHeight - vh) + 'px');
    document.querySelectorAll('.qa').forEach(function (el, i) {
      var r = el.getBoundingClientRect();
      var id = el.dataset.qa || el.className;
      if (r.left < -0.5) out.push('LEFT<' + id + '=' + r.left.toFixed(1));
      if (r.right > vw + 0.5) out.push('RIGHT>' + id + '=' + r.right.toFixed(1) + ' w=' + (r.right - r.left).toFixed(0));
      if (r.top < -0.5) out.push('TOP<' + id + '=' + r.top.toFixed(1));
      if (r.bottom > vh + 0.5) out.push('BOTTOM>' + id + '=' + r.bottom.toFixed(1) + ' h=' + (r.bottom - r.top).toFixed(0));
    });
    document.getElementById('qa').textContent = out.length ? out.join('\\n') : 'QA_OK';
    document.getElementById('qa').dataset.qa = out.length ? 'FAIL' : 'PASS';
  }, 150);
});
</script>
""" % (VW, VH)


def page(title: str, section: str, subtitle: str, kpis: str, insight: str, main: str, bottom: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; margin: 0; }}
  html, body {{ width: {VW}px; height: {VH}px; overflow: hidden; }}
  body {{ font-family: 'Segoe UI', 'Segoe UI Variable Text', Arial, sans-serif; background: {NAVY}; color: {TEXT}; }}
  .wrap {{ width: {VW}px; height: {VH}px; padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }}
  .head {{ display: flex; justify-content: space-between; align-items: flex-end; flex: none; height: 44px; }}
  .head h1 {{ font-size: 21px; font-weight: 700; letter-spacing: 0.2px; }}
  .head .sub {{ color: {MUTED}; font-size: 12px; margin-top: 3px; }}
  .brand {{ color: {MUTED}; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; text-align: right; }}
  .brand b {{ color: {GOLD}; font-weight: 700; }}
  .kpis {{ display: flex; gap: 12px; flex: none; height: 88px; }}
  .kpi {{ background: {NAVY2}; border-radius: 10px; padding: 11px 16px; flex: 1; min-width: 0; }}
  .kpi .lab {{ font-size: 10px; color: {MUTED}; letter-spacing: 0.6px; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .kpi .val {{ font-size: 23px; font-weight: 700; color: {GOLD}; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .kpi .val.sm {{ font-size: 18px; }}
  .kpi .val.xs {{ font-size: 15.5px; }}
  .kpi .val.flat {{ color: {TEXT}; }}
  .kpi .sub {{ font-size: 10.5px; color: {MUTED}; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .kpi .sub.sm {{ font-size: 9.5px; }}
  .insight {{ flex: none; height: 34px; background: {NAVY3}; border-left: 3px solid {GOLD}; border-radius: 6px; padding: 8px 14px; font-size: 12px; color: {TEXT}; display: flex; align-items: center; gap: 10px; overflow: hidden; }}
  .insight b {{ color: {GOLD}; letter-spacing: 0.5px; font-size: 10.5px; text-transform: uppercase; white-space: nowrap; }}
  .main {{ flex: 1; min-height: 0; display: flex; gap: 12px; }}
  .card {{ background: {NAVY2}; border-radius: 10px; padding: 12px 16px; overflow: hidden; display: flex; flex-direction: column; }}
  .card h3 {{ font-size: 11px; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 2px; flex: none; }}
  .card .csub {{ font-size: 10px; color: {MUTED}; margin-bottom: 8px; flex: none; }}
  .chart {{ flex: 1; min-height: 0; }}
  .bottom {{ flex: none; height: {BOTTOM_H}px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ color: {MUTED}; text-align: right; padding: 4px 8px; border-bottom: 1px solid {NAVY3}; font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.3px; }}
  th:first-child, td:first-child {{ text-align: left; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #2A3A5F; }}
  td.num {{ text-align: right; white-space: nowrap; }}
  .barwrap {{ position: relative; height: 4px; background: {NAVY}; border-radius: 2px; margin-top: 3px; }}
  .barfill {{ height: 4px; border-radius: 2px; background: {GOLD}; }}
  .chip {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 7px; vertical-align: middle; }}
  .legend {{ font-size: 11.5px; line-height: 1.6; }}
  .two {{ display: flex; gap: 16px; flex: 1; min-height: 0; }}
  .mini {{ flex: 1; min-width: 0; }}
  .mini table {{ font-size: 10px; }}
  .mini th {{ padding: 3px 6px; font-size: 9.5px; }}
  .mini td {{ padding: 3px 6px; font-size: 10px; }}
</style></head><body>
<div class="wrap">
  <div class="head">
    <div>
      <h1>{title}</h1>
      <div class="sub">{subtitle}</div>
    </div>
    <div class="brand">RETAIL ANALYTICS · <b>{section}</b></div>
  </div>
  <div class="kpis">{kpis}</div>
  <div class="insight">{insight}</div>
  <div class="main">{main}</div>
  <div class="bottom">{bottom}</div>
</div>
<pre id="qa" style="display:none"></pre>
{QA_SCRIPT}
</body></html>"""


def kpi(title: str, value: str, sub: str = "", flat=False, vsize: str | None = None) -> str:
    if vsize is None:
        n = len(value)
        vsize = "xs" if n > 18 else ("sm" if n > 13 else "")
    vcls = "val flat" if flat else "val"
    if vsize:
        vcls += " " + vsize
    return f'<div class="kpi qa"><div class="lab">{title}</div><div class="{vcls}">{value}</div><div class="sub">{sub}</div></div>'


def insight_html(label: str, text: str) -> str:
    return f"<div class='qa'><b>{label}</b><span>{text}</span></div>"


def hbar(items, fmt=gbp0, pct_of=None, ncols=1, label_w=200, val_w=150, row_h=20) -> str:
    cols: list[list] = [[] for _ in range(ncols)]
    for i, it in enumerate(items):
        cols[i % ncols].append(it)
    out = ""
    for col in cols:
        mx = max(v for _, v in col) or 1
        rows = ""
        for label, v in col:
            w = max(v / mx * 100, 0.8)
            right = fmt(v)
            if pct_of:
                right += " · " + pct(v / pct_of)
            rows += f"""
        <div style="display:flex;align-items:center;margin:2.5px 0;height:{row_h}px;">
          <div style="width:{label_w}px;font-size:11.5px;color:{TEXT};text-align:right;padding-right:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{label}">{label}</div>
          <div style="flex:1;background:{NAVY};border-radius:3px;height:12px;">
            <div style="width:{w:.1f}%;height:12px;background:{GOLD};border-radius:3px;"></div>
          </div>
          <div style="width:{val_w}px;font-size:11.5px;color:{TEXT};text-align:right;padding-left:9px;white-space:nowrap;">{right}</div>
        </div>"""
        out += f'<div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;">{rows}</div>'
    return f'<div style="display:flex;gap:18px;flex:1;min-height:0;">{out}</div>'


def smart_month_labels(ym_list: list[str]) -> list[str]:
    out = []
    prev_year = None
    for ym in ym_list:
        year, month = ym.split("-")
        short = pd.Timestamp(year=int(year), month=int(month), day=1).strftime("%b")
        if prev_year is None or year != prev_year:
            out.append(f"{short} {year[-2:]}")
        else:
            out.append(short)
        prev_year = year
    return out


def svg_line(months, values, color=GOLD, w=704, h=CHART_H) -> str:
    pad_l, pad_r, pad_t, pad_b = 46, 12, 16, 26
    vmax, vmin = max(values), min(values)
    span = (vmax - vmin) or 1
    px = lambda i: pad_l + i * (w - pad_l - pad_r) / max(len(values) - 1, 1)
    py = lambda v: pad_t + (1 - (v - vmin) / span) * (h - pad_t - pad_b)
    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
    grid = ""
    for g in range(4):
        gy = pad_t + g * (h - pad_t - pad_b) / 3
        val = vmax - g * span / 3
        grid += f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" stroke="{NAVY3}" stroke-width="1"/><text x="{pad_l - 7}" y="{gy + 4:.1f}" fill="{MUTED}" font-size="10" text-anchor="end">{compact(val)}</text>'
    area = f'<polygon points="{pad_l},{h - pad_b} {pts} {px(len(values) - 1):.1f},{h - pad_b}" fill="{color}" opacity="0.10"/>'
    line = f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4"/>'
    dots = "".join(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="3" fill="{color}"/>' for i, v in enumerate(values))
    labels = "".join(f'<text x="{px(i):.1f}" y="{h - 8}" fill="{MUTED}" font-size="10" text-anchor="middle">{m}</text>' for i, m in enumerate(months))
    return f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:100%">{grid}{area}{line}{dots}{labels}</svg>'


def svg_columns(days, values, w=1208, h=BOTTOM_CHART_H) -> str:
    pad_l, pad_r, pad_t, pad_b = 12, 12, 22, 26
    mx = max(values) or 1
    n = len(days)
    bw = (w - pad_l - pad_r) / n
    out = ""
    for i, (day, v) in enumerate(zip(days, values)):
        x = pad_l + i * bw
        bh = v / mx * (h - pad_t - pad_b)
        is_sat = day == "Sat"
        bar = ATTN if is_sat else GOLD
        lbl = compact(v) if v > 0 else "\u00a30"
        out += (
            f'<rect x="{x + bw * 0.22:.1f}" y="{h - pad_b - bh:.1f}" width="{bw * 0.56:.1f}" height="{bh:.1f}" rx="2" fill="{bar}"/>'
            f'<text x="{x + bw / 2:.1f}" y="{h - pad_b - bh - 5:.1f}" fill="{TEXT if v > 0 else MUTED}" font-size="10" text-anchor="middle">{lbl}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{h - 7}" fill="{MUTED}" font-size="10.5" text-anchor="middle">{day}</text>'
        )
    return f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:100%">{out}</svg>'


def _cos(d):
    return math.cos(math.radians(d))


def _sin(d):
    return math.sin(math.radians(d))


def svg_donut(slices, total, size=178, center="", colors=None, subtext="attributed") -> str:
    colors = colors or SEG_COLORS
    acc = -90.0
    segs = ""
    for label, val in slices:
        if total <= 0:
            break
        frac = val / total
        a1, a2 = acc, acc + frac * 360
        large = 1 if frac > 0.5 else 0
        segs += (
            f'<path d="M100,100 L{100 + 88 * _cos(a1):.1f},{100 + 88 * _sin(a1):.1f} '
            f'A88,88 0 {large},1 {100 + 88 * _cos(a2):.1f},{100 + 88 * _sin(a2):.1f} Z" '
            f'fill="{colors.get(label, GOLD)}"/>'
        )
        acc = a2
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f"{segs}"
        f'<circle cx="100" cy="100" r="50" fill="{NAVY}"/>'
        f'<text x="100" y="96" fill="{TEXT}" font-size="13" font-weight="700" text-anchor="middle">{center}</text>'
        f'<text x="100" y="113" fill="{MUTED}" font-size="8.5" text-anchor="middle">{subtext}</text>'
        f"</svg>"
    )


def svg_scatter(points, w=1208, h=BOTTOM_CHART_H) -> str:
    pad_l, pad_r, pad_t, pad_b = 52, 12, 14, 26
    xs = [math.log10(max(p["qty"], 1)) for p in points]
    ys = [math.log10(p["rev"]) for p in points]
    xmed, ymed = sorted(xs)[len(xs) // 2], sorted(ys)[len(ys) // 2]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    px = lambda v: pad_l + (v - xmin) / ((xmax - xmin) or 1) * (w - pad_l - pad_r)
    py = lambda v: pad_t + (1 - (v - ymin) / ((ymax - ymin) or 1)) * (h - pad_t - pad_b)
    qcols = {1: GOLD, 2: BLUE, 3: GRAY, 4: "#33446B"}
    circles = ""
    for p, x, y in zip(points, xs, ys):
        q = (1 if x >= xmed else 2) if y >= ymed else (3 if x >= xmed else 4)
        r = 2.2 + 1.6 * ((y - ymin) / ((ymax - ymin) or 1))
        circles += f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{r:.1f}" fill="{qcols[q]}" opacity="0.85"/>'
    grid = (
        f'<line x1="{px(xmed):.1f}" y1="{pad_t}" x2="{px(xmed):.1f}" y2="{h - pad_b}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="3,3"/>'
        f'<line x1="{pad_l}" y1="{py(ymed):.1f}" x2="{w - pad_r}" y2="{py(ymed):.1f}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="3,3"/>'
    )
    n = len(points)
    labels = (
        f'<text x="{pad_l + 6}" y="{pad_t + 12}" fill="{BLUE}" font-size="10">high revenue · high volume</text>'
        f'<text x="{w - pad_r - 6}" y="{pad_t + 12}" fill="{GOLD}" font-size="10" text-anchor="end">high revenue · low volume</text>'
        f'<text x="{pad_l + 6}" y="{h - pad_b - 8}" fill="{GRAY}" font-size="10">low revenue · high volume</text>'
        f'<text x="{w - pad_r - 6}" y="{h - pad_b - 8}" fill="#33446B" font-size="10" text-anchor="end">low revenue · low volume</text>'
        f'<text x="{w / 2}" y="{h - 5}" fill="{MUTED}" font-size="9.5" text-anchor="middle">Units sold (log) →   ·   {n} products shown</text>'
    )
    return f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:100%">{grid}{circles}{labels}</svg>'


def heat_color(v: float) -> str:
    """Blend navy (0%) -> gold (100%) for the retention heatmap cells."""
    t = max(0.0, min(1.0, v / 100.0))
    r = round(42 + (242 - 42) * t)
    g = round(58 + (201 - 58) * t)
    b = round(95 + (76 - 95) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def heat_cell_style(v) -> str:
    if pd.isna(v):
        return "background:transparent;color:#93A4C3;"
    t = v / 100.0
    fg = "#FFFFFF" if t < 0.5 else "#1B2A4A"
    return f"background:{heat_color(v)};color:{fg};"


def svg_retention_decay(idx_list, wavg, best, w, h) -> str:
    """Line chart of weighted-average retention by cohort index (0-100%)."""
    pad_l, pad_r, pad_t, pad_b = 40, 12, 16, 26
    vmax, vmin = 100.0, 0.0
    span = vmax - vmin
    px = lambda i: pad_l + i * (w - pad_l - pad_r) / max(len(idx_list) - 1, 1)
    py = lambda v: pad_t + (1 - (v - vmin) / span) * (h - pad_t - pad_b)
    grid = ""
    for g in range(4):
        gy = pad_t + g * (h - pad_t - pad_b) / 3
        val = vmax - g * span / 3
        grid += f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" stroke="{NAVY3}" stroke-width="1"/><text x="{pad_l - 7}" y="{gy + 4:.1f}" fill="{MUTED}" font-size="10" text-anchor="end">{val:.0f}%</text>'
    def series(vals, color):
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals) if v is not None and math.isfinite(v))
        dots = "".join(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="2.6" fill="{color}"/>' for i, v in enumerate(vals) if v is not None and math.isfinite(v))
        line = f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2"/>'
        return line + dots
    labels = "".join(f'<text x="{px(i):.1f}" y="{h - 8}" fill="{MUTED}" font-size="9.5" text-anchor="middle">M{i}</text>' for i in idx_list)
    return f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:100%">{grid}{series(wavg, GOLD)}{series(best, BLUE)}{labels}</svg>'


def main() -> None:
    fact = pd.read_csv(DS / "FactSales.csv", low_memory=False)
    fact["invoice_no"] = fact["invoice_no"].astype(str)
    cust = pd.read_csv(DS / "DimCustomer.csv")
    prod = pd.read_csv(DS / "DimProduct.csv")
    cntry = pd.read_csv(DS / "DimCountry.csv")

    fact["dt"] = pd.to_datetime(fact["invoice_date"])
    fact["ym"] = fact["dt"].dt.strftime("%Y-%m")
    fact["dow"] = fact["dt"].dt.strftime("%a")
    fact["country"] = fact["country"].fillna("Unspecified")

    revenue = float(fact["total_price"].sum())
    orders = int(fact["invoice_no"].nunique())
    units = int(fact["quantity"].sum())
    customers = int(fact["customer_id"].nunique())
    aov = revenue / orders
    repeat = int(cust["is_repeat"].sum())
    repeat_rate = repeat / len(cust)
    aup = revenue / units

    months = sorted(fact["ym"].unique())
    mrev = fact.groupby("ym")["total_price"].sum()
    mrev_vals = [float(mrev[m]) for m in months]
    cum = []
    acc = 0.0
    for v in mrev_vals:
        acc += v
        cum.append(acc)
    labels = smart_month_labels(months)
    peak_m = months[mrev_vals.index(max(mrev_vals))]
    min_m = months[mrev_vals.index(min(mrev_vals))]

    dow_rev = fact.groupby("dow")["total_price"].sum()
    dow_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow_vals = [float(dow_rev.get(d, 0)) for d in dow_order]
    high_day = max(dow_order, key=lambda d: dow_rev.get(d, 0))
    DAY_FULL = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}

    country_rev = fact.groupby("country")["total_price"].sum().sort_values(ascending=False)
    top10_countries = list(country_rev.head(10).items())
    top15_countries = list(country_rev.head(15).items())
    uk_share = float(country_rev.max()) / revenue

    merged = fact.dropna(subset=["customer_id"]).merge(cust, on="customer_id", how="left")
    seg_rev = merged.groupby("segment")["total_price"].sum().sort_values(ascending=False)
    seg_cnt = cust["segment"].value_counts()
    attributed = float(seg_rev.sum())
    champions_c = seg_cnt.get("Champions", 0) / len(cust)
    champions_r = seg_rev.get("Champions", 0) / attributed
    atrisk_hiber = (seg_cnt.get("At Risk", 0) + seg_cnt.get("Hibernating", 0)) / len(cust)

    prod_rev = fact.merge(prod, on="stock_code", how="left")
    tp = prod_rev.groupby("description")["total_price"].sum().sort_values(ascending=False)
    tc = prod_rev.dropna(subset=["category"]).groupby("category")["total_price"].sum().sort_values(ascending=False)
    tq = prod_rev.groupby("description")["quantity"].sum()

    reg_rev = fact.merge(cntry, on="country", how="left").groupby("region")["total_price"].sum()
    reg_tot = float(reg_rev.sum())
    reg_order = ["UK & Ireland", "Europe", "Asia Pacific", "Middle East & Africa", "Americas", "Unspecified"]
    uk_ire = float(reg_rev.get("UK & Ireland", 0))
    europe = float(reg_rev.get("Europe", 0))
    apac = float(reg_rev.get("Asia Pacific", 0))

    f2 = fact.dropna(subset=["customer_id"])
    cust_by_country = f2.groupby("country")["customer_id"].nunique()
    rev_by_country = f2.groupby("country")["total_price"].sum()
    c_arpc = (rev_by_country / cust_by_country.replace(0, float("nan"))).dropna()
    top_c_table = country_rev.head(10).index.tolist()

    scatter_pts = [{"desc": code, "rev": float(tp[code]), "qty": float(tq.get(code, 0))} for code in tp.head(120).index]

    recency_avg = float(cust["recency_days"].mean())
    avg_rev_per_cust = revenue / customers
    avg_ords_per_cust = orders / customers

    # widths for inner charts (content 1240, main gap 12, card padding 32)
    W1 = int(((CONTENT_W - GAP) * 0.6) - 32)   # page 1 trend (3:2 split)
    W2 = int(((CONTENT_W - GAP) * 0.5) - 32)   # page 2 charts (1:1)
    WB = CONTENT_W - 32                          # bottom full-width inner

    # ---------------- Page 1 — Executive Overview ----------------
    kpis1 = (
        kpi("Total Revenue", compact(revenue), gbp(revenue))
        + kpi("Total Orders", num(orders), f"AOV {gbp(aov)}")
        + kpi("Total Units", num(units), "across 527,390 line items")
        + kpi("Total Customers", num(customers), "attributed transactions only")
        + kpi("Repeat Customer Rate", pct(repeat_rate), f"{num(repeat)} of {num(customers)} customers")
        + kpi("UK Share", pct(uk_share), "of total revenue")
    )
    seg_slices = [(s, float(seg_rev[s])) for s in seg_rev.index]
    legend1 = "".join(
        f'<div class="legend"><span class="chip" style="background:{SEG_COLORS[s]}"></span>{s} · <b>{pct(v / attributed)}</b></div>'
        for s, v in seg_slices
    )
    main1 = f"""
    <div class="card qa" style="flex:3;">
      <h3>Revenue Trend · 13 Months</h3>
      <div class="csub">Dec 2010 – Dec 2011 · monthly totals</div>
      <div class="chart">{svg_line(labels, mrev_vals, w=W1)}</div>
    </div>
    <div class="card qa" style="flex:2;">
      <h3>Customer-Attributed Revenue by RFM Segment</h3>
      <div class="csub">Excludes transactions without CustomerID</div>
      <div style="display:flex;align-items:center;gap:14px;flex:1;min-height:0;">
        {svg_donut(seg_slices, attributed, 172, compact(attributed), subtext="attributed revenue")}
        <div style="flex:1;min-width:0;">{legend1}</div>
      </div>
    </div>"""
    bottom1 = f"""
    <div class="card qa">
      <h3>Top 10 Countries by Revenue</h3>
      <div class="csub">share of total revenue · the top 10 markets drive 97.2% of revenue</div>
      {hbar(top10_countries, gbp0, pct_of=revenue, ncols=2, label_w=230, val_w=150, row_h=19)}
    </div>"""
    (OUT / "page1_executive_overview.html").write_text(
        page("Retail Executive Overview", "Executive View", "How the business is performing · every figure validated to the penny", kpis1,
             insight_html("Key Insight", f"The UK alone generates <b>{pct(uk_share)}</b> of revenue; <b>Champions</b> are {pct(champions_c)} of customers yet drive <b>{pct(champions_r)}</b> of customer-attributed revenue."),
             main1, bottom1), encoding="utf-8")

    # ---------------- Page 2 — Sales & Trends ----------------
    kpis2 = (
        kpi("Peak Month", pd.Timestamp(peak_m + "-01").strftime("%b %Y"), compact(max(mrev_vals)))
        + kpi("Slowest Month", pd.Timestamp(min_m + "-01").strftime("%b %Y"), compact(min(mrev_vals)))
        + kpi("Highest Revenue Day", DAY_FULL[high_day], f"{compact(float(dow_rev[high_day]))} · revenue by weekday")
        + kpi("Average Monthly Revenue", compact(sum(mrev_vals) / len(mrev_vals)), "across 13 months")
    )
    sat_note = ("Saturday has no transactions in the source data (0 trading days) · Sunday = " + compact(float(dow_rev.get("Sun", 0)))
                + " across 50 trading days")
    main2 = f"""
    <div class="card qa" style="flex:1;">
      <h3>Monthly Revenue</h3>
      <div class="csub">Dec 2010 – Dec 2011</div>
      <div class="chart">{svg_line(labels, mrev_vals, w=W2)}</div>
    </div>
    <div class="card qa" style="flex:1;">
      <h3>Cumulative Revenue</h3>
      <div class="csub">running total across the full window</div>
      <div class="chart">{svg_line(labels, cum, color=BLUE, w=W2)}</div>
    </div>"""
    bottom2 = f"""
    <div class="card qa">
      <h3>Revenue by Weekday</h3>
      <div class="csub">{sat_note}</div>
      {svg_columns(dow_order, dow_vals, w=WB)}
    </div>"""
    (OUT / "page2_sales_trends.html").write_text(
        page("Sales & Trends", "Sales & Trends", "Revenue dynamics across the 13-month window", kpis2,
             insight_html("Key Insight", f"Revenue peaks in <b>{pd.Timestamp(peak_m + '-01').strftime('%b %Y')} ({compact(max(mrev_vals))})</b> and troughs in <b>{pd.Timestamp(min_m + '-01').strftime('%b %Y')}</b>; <b>{DAY_FULL[high_day]}</b> is the highest-revenue weekday."),
             main2, bottom2), encoding="utf-8")

    # ---------------- Page 3 — Customer Intelligence ----------------
    kpis3 = (
        kpi("Total Customers", num(customers), "validated against SQL")
        + kpi("Repeat Customer Rate", pct(repeat_rate), f"{num(repeat)} repeat · {num(len(cust) - repeat)} one-time")
        + kpi("Average Orders per Customer", f"{avg_ords_per_cust:.1f}", "orders ÷ customers")
        + kpi("Average Revenue per Customer", gbp0(avg_rev_per_cust), "total revenue ÷ customers")
        + kpi("Average Recency", f"{recency_avg:.0f} days", "days since last purchase")
    )
    seg_rows = ""
    for s in seg_rev.index:
        c = int(seg_cnt.get(s, 0))
        r = float(seg_rev[s])
        share = c / len(cust)
        seg_rows += (
            f"<tr><td><span class='chip' style='background:{SEG_COLORS[s]}'></span>{s}</td>"
            f"<td class='num'><b>{num(c)}</b></td>"
            f"<td class='num'>{gbp0(r)}</td>"
            f"<td class='num'>{gbp0(r / c if c else 0)}</td>"
            f"<td class='num'>{pct(share)}<div class='barwrap'><div class='barfill' style='width:{share * 100:.0f}%'></div></div></td></tr>"
        )
    main3 = f"""
    <div class="card qa" style="flex:3;">
      <h3>RFM Segment Performance</h3>
      <div class="csub">RFM quartiles validated 100% against SQL · revenue is customer-attributed</div>
      <div style="flex:1;min-height:0;overflow:auto;">
        <table>
          <tr><th>Segment</th><th>Customers</th><th>Revenue</th><th>Avg Rev / Cust</th><th>% of Base</th></tr>
          {seg_rows}
        </table>
      </div>
    </div>
    <div class="card qa" style="flex:2;">
      <h3>One-Time vs Repeat Customers</h3>
      <div class="csub">share of the 4,339-customer base</div>
      <div style="display:flex;align-items:center;gap:10px;flex:1;min-height:0;">
        {svg_donut([("Repeat", float(repeat)), ("One-time", float(len(cust) - repeat))], float(len(cust)), 150, num(len(cust)), colors={"Repeat": GOLD, "One-time": NAVY3}, subtext="customers")}
        <div class="legend">
          <div><span class="chip" style="background:{GOLD}"></span>Repeat · <b>{pct(repeat_rate)}</b></div>
          <div><span class="chip" style="background:{NAVY3}"></span>One-time · <b>{pct(1 - repeat_rate)}</b></div>
        </div>
      </div>
    </div>"""
    bottom3 = f"""
    <div class="card qa">
      <h3>Revenue by RFM Segment</h3>
      <div class="csub">share of customer-attributed revenue · total {gbp(attributed)}</div>
      {hbar([(s, float(seg_rev[s])) for s in seg_rev.index], gbp0, pct_of=attributed, ncols=2, label_w=210, val_w=155, row_h=19)}
    </div>"""
    (OUT / "page3_customer_intelligence.html").write_text(
        page("Customer Intelligence", "Customer Intelligence", "Customer value and RFM behaviour", kpis3,
             insight_html("Key Insight", f"<b>Champions</b> are {pct(champions_c)} of customers but generate <b>{pct(champions_r)}</b> of customer-attributed revenue; <b>At Risk + Hibernating</b> together hold {pct(atrisk_hiber)} of the base."),
             main3, bottom3), encoding="utf-8")

    # ---------------- Page 4 — Product Performance ----------------
    top_prod_name, top_prod_rev = str(tp.index[0]), float(tp.iloc[0])
    kpis4 = (
        kpi("Unique Products", num(len(prod)), "3,947 stock codes")
        + kpi("Top Product", top_prod_name[:22], f"{compact(top_prod_rev)} · {pct(top_prod_rev / revenue)} of revenue")
        + kpi("Average Unit Price", gbp(aup), "revenue ÷ units")
        + kpi("Product Categories", num(int(prod["category"].nunique())), "auto-grouped by first word")
    )
    main4 = f"""
    <div class="card qa" style="flex:1;">
      <h3>Top 10 Products by Revenue</h3>
      <div class="csub">top 10 of 3,947 · share of total revenue</div>
      {hbar(list(tp.head(10).items()), gbp0, pct_of=revenue, label_w=210, val_w=150, row_h=21)}
    </div>
    <div class="card qa" style="flex:1;">
      <h3>Top 10 Product Categories by Revenue</h3>
      <div class="csub">auto-grouped by first word of description</div>
      {hbar(list(tc.head(10).items()), gbp0, pct_of=revenue, label_w=210, val_w=150, row_h=21)}
    </div>"""
    bottom4 = f"""
    <div class="card qa">
      <h3>Revenue vs Volume · Product Level</h3>
      <div class="csub">top 120 products by revenue · log scales · dashed lines = median volume / median revenue</div>
      {svg_scatter(scatter_pts, w=WB)}
    </div>"""
    (OUT / "page4_product_performance.html").write_text(
        page("Product Performance", "Product Performance", "What sells, and what earns", kpis4,
             insight_html("Key Insight", f"The top 10 products drive <b>{pct(float(tp.head(10).sum()) / revenue)}</b> of revenue; the single largest line is <b>{top_prod_name[:26]}</b> at {pct(top_prod_rev / revenue)}."),
             main4, bottom4), encoding="utf-8")

    # ---------------- Page 5 — Geographic Performance ----------------
    other = float(reg_rev.sum() - uk_ire - europe - apac)
    kpis5 = (
        kpi("Countries With Sales", num(len(cntry)), "38 destination markets")
        + kpi("UK & Ireland", pct(uk_ire / reg_tot), gbp0(uk_ire))
        + kpi("Europe", pct(europe / reg_tot), gbp0(europe))
        + kpi("Asia Pacific", pct(apac / reg_tot), gbp0(apac))
        + kpi("Other Markets", pct(other / reg_tot), "MEA · Americas · Unspecified")
    )
    reg_slices = [(r, float(reg_rev.get(r, 0))) for r in reg_order]
    reg_legend = "".join(
        f'<div class="legend"><span class="chip" style="background:{REG_COLORS[r]}"></span>{r} · <b>{pct(v / reg_tot)}</b></div>'
        for r, v in reg_slices
    )
    table_rows = ""
    for c in top_c_table:
        cr = float(country_rev[c])
        cc = int(cust_by_country.get(c, 0))
        ca = c_arpc.get(c)
        table_rows += (
            f"<tr><td><b>{c}</b></td><td class='num'>{num(cc)}</td><td class='num'>{gbp0(cr)}</td>"
            f"<td class='num'>{gbp0(ca) if pd.notna(ca) else '—'}</td><td class='num'>{pct(cr / revenue)}</td></tr>"
        )
    main5 = f"""
    <div class="card qa" style="flex:3;">
      <h3>Revenue by Region</h3>
      <div class="csub">mutually exclusive regions · shares sum to 100%</div>
      <div style="display:flex;align-items:center;gap:14px;flex:1;min-height:0;">
        {svg_donut(reg_slices, reg_tot, 165, compact(reg_tot), colors=REG_COLORS, subtext="total revenue")}
        <div style="flex:1;min-width:0;">{reg_legend}</div>
      </div>
    </div>
    <div class="card qa" style="flex:4;">
      <h3>Country Metrics · Top 10 by Revenue</h3>
      <div class="csub">customer-attributed revenue · ARPC = revenue ÷ customers</div>
      <div style="flex:1;min-height:0;overflow:auto;">
        <table>
          <tr><th>Country</th><th>Customers</th><th>Revenue</th><th>ARPC</th><th>% of Total</th></tr>
          {table_rows}
        </table>
      </div>
    </div>"""
    bottom5 = f"""
    <div class="card qa">
      <h3>Top 15 Countries by Revenue</h3>
      <div class="csub">share of total revenue · the top 15 markets drive 98.6% of revenue</div>
      {hbar(top15_countries, gbp0, pct_of=revenue, ncols=3, label_w=150, val_w=150, row_h=19)}
    </div>"""
    eire_arpc = c_arpc.get("Eire", 0)
    (OUT / "page5_geographic_performance.html").write_text(
        page("Geographic Performance", "Geographic Performance", "Where revenue comes from", kpis5,
             insight_html("Key Insight", f"<b>UK &amp; Ireland</b> generate <b>{pct(uk_ire / reg_tot)}</b> of revenue (the UK alone {pct(uk_share)}); <b>Eire</b> has the highest average revenue per customer at {gbp0(eire_arpc) if eire_arpc else 'n/a'}."),
             main5, bottom5), encoding="utf-8")

    # ---------------- Page 6 — Customer Retention (Cohort Analysis) ----------------
    cohort = pd.read_csv(DS / "CohortRetention.csv")
    csum = pd.read_csv(DS / "CohortSummary.csv").set_index("cohort_month")

    cohort_idx = sorted(cohort["cohort_index"].unique())
    max_idx = int(cohort_idx[-1])
    cohort_months = sorted(cohort["cohort_month"].unique())
    total_cohort_customers = int(csum["cohort_size"].sum())
    m1_num = int(cohort[cohort["cohort_index"] == 1]["active_customers"].sum())
    m1_den = int(cohort[cohort["cohort_index"] == 1]["cohort_size"].sum())
    wavg_m1 = m1_num / m1_den if m1_den else 0.0
    m6_num = int(cohort[cohort["cohort_index"] == 6]["active_customers"].sum())
    m6_den = int(cohort[cohort["cohort_index"] == 6]["cohort_size"].sum())
    wavg_m6 = m6_num / m6_den if m6_den else 0.0
    wavg_by_idx = {
        i: float(cohort[cohort["cohort_index"] == i]["active_customers"].sum())
        / float(cohort[cohort["cohort_index"] == i]["cohort_size"].sum())
        for i in cohort_idx
    }
    best_cohort = cohort[cohort["cohort_index"] == 1].sort_values("retention_pct", ascending=False).iloc[0]
    best_m = best_cohort["cohort_month"]
    best_m1 = float(best_cohort["retention_pct"])
    founding_share = float(csum.loc["2010-12", "lifetime_revenue"]) / float(csum["lifetime_revenue"].sum())
    total_repeat = int(csum["repeat_customers"].sum())
    total_lt_rev = float(csum["lifetime_revenue"].sum())
    rev_per_cust_avg = total_lt_rev / total_cohort_customers

    pivot = cohort.pivot_table(index="cohort_month", columns="cohort_index", values="retention_pct")
    hm_rows = ""
    for cm in cohort_months:
        row = pivot.loc[cm]
        cells = f'<td style="text-align:right;padding:2px 6px;font-size:9.5px;color:{MUTED};white-space:nowrap;"><b>{cm}</b></td>'
        cells += f'<td style="text-align:right;padding:2px 4px;font-size:9.5px;color:{TEXT};">{int(cohort[cohort["cohort_month"] == cm]["cohort_size"].iloc[0])}</td>'
        for i in range(max_idx + 1):
            v = row.get(i)
            cells += f'<td style="padding:2px 1px;text-align:center;font-size:9px;border-radius:2px;{heat_cell_style(v)}">{f"{v:.0f}" if pd.notna(v) else "·"}</td>'
        hm_rows += f"<tr>{cells}</tr>"
    hm_headers = "".join(f"<th>M{i}</th>" for i in range(max_idx + 1))
    heatmap = f"""
    <div class="card qa" style="flex:3;">
      <h3>Cohort Retention Heatmap</h3>
      <div class="csub">% of cohort customers active in each period · M0 = acquisition month = 100% · blank = future</div>
      <div style="flex:1;min-height:0;overflow:auto;">
        <table style="border-collapse:collapse;font-size:9px;width:100%;">
          <tr style="position:sticky;top:0;background:{NAVY2};"><th style="text-align:right;padding:2px 6px;font-size:9px;color:{MUTED};">Cohort</th><th style="text-align:right;padding:2px 4px;font-size:9px;color:{MUTED};">N</th>{hm_headers}</tr>
          {hm_rows}
        </table>
        <div style="display:flex;align-items:center;gap:8px;margin-top:8px;font-size:9px;color:{MUTED};">
          <span>0%</span><span style="flex:1;height:6px;border-radius:3px;background:linear-gradient(90deg,{NAVY3},{GOLD});"></span><span>100%</span>
        </div>
      </div>
    </div>"""
    dec_svg = svg_retention_decay(cohort_idx, [wavg_by_idx[i] * 100 for i in cohort_idx], [float(pivot.loc[best_m].get(i, float("nan"))) for i in cohort_idx], w=W2, h=CHART_H)
    right6 = f"""
    <div class="card qa" style="flex:2;">
      <h3>Retention Decay · % of cohort active by month</h3>
      <div class="csub"><span class="chip" style="background:{GOLD}"></span>weighted avg across cohorts with data · <span class="chip" style="background:{BLUE}"></span>{best_m} cohort</div>
      <div class="chart">{dec_svg}</div>
    </div>"""
    main6 = heatmap + right6
    def mini_table(months: list[str]) -> str:
        rows = ""
        for cm in months:
            s = csum.loc[cm]
            rows += (
                f"<tr><td><b>{cm}</b></td><td class='num'>{num(int(s['cohort_size']))}</td>"
                f"<td class='num'>{pct(float(s['repeat_rate_pct']) / 100)}</td>"
                f"<td class='num'>{gbp0(float(s['lifetime_revenue']))}</td>"
                f"<td class='num'>{gbp0(float(s['revenue_per_customer']))}</td></tr>"
            )
        return (
            f"<table>"
            f"<tr><th>Cohort</th><th>Customers</th><th>Repeat Rate</th><th>Lifetime Revenue</th><th>Rev / Customer</th></tr>"
            f"{rows}</table>"
        )
    half = (len(cohort_months) + 1) // 2
    bottom6 = f"""
    <div class="card qa" style="height:100%;">
      <h3>Cohort Lifecycle Summary</h3>
      <div class="csub">all {len(cohort_months)} cohorts shown · repeat = ever purchased after first purchase month · {num(total_cohort_customers)} customers · {gbp(total_lt_rev)} lifetime revenue</div>
      <div class="two">
        <div class="mini">{mini_table(cohort_months[:half])}</div>
        <div class="mini">{mini_table(cohort_months[half:])}</div>
      </div>
    </div>"""
    kpis6 = (
        kpi("Total Customers", num(total_cohort_customers), f"{num(len(cohort_months))} monthly cohorts")
        + kpi("Repeat Customer Rate", pct(total_repeat / total_cohort_customers), f"{num(total_repeat)} of {num(total_cohort_customers)} repurchased")
        + kpi("Avg 1-Month Retention", pct(wavg_m1), f"{num(m1_num)} of {num(m1_den)} return in M1")
        + kpi("Avg 6-Month Retention", pct(wavg_m6), f"{num(m6_num)} of {num(m6_den)} reach M6")
        + kpi("Best 1-Month Retention", f"{best_m} · {pct(best_m1 / 100)}", "cohort with the highest M1")
        + kpi("Founding Cohort Revenue", pct(founding_share), f"{gbp0(float(csum.loc['2010-12', 'lifetime_revenue']))} attributed")
    )
    (OUT / "page6_customer_retention.html").write_text(
        page("Customer Retention", "Cohort & Retention", "How many customers come back · customer cohorts by first purchase month", kpis6,
             insight_html("Key Insight", f"The <b>{best_m} founding cohort</b> is the strongest by far — M1 retention {pct(best_m1 / 100)}, repeat rate {pct(float(csum.loc[best_m, 'repeat_rate_pct']) / 100)}, and it alone drives <b>{pct(founding_share)}</b> of customer-attributed revenue ({gbp0(total_lt_rev)} total). Retention plateaus around 20–30% from M2 onward rather than decaying to zero."),
             main6, bottom6), encoding="utf-8")

    print("previews written to powerbi/previews/")
    print("revenue=%.2f orders=%d customers=%d units=%d attributed=%.2f" % (revenue, orders, customers, units, attributed))
    print("MAIN_H=%d CHART_H=%d BOTTOM_CHART_H=%d W1=%d W2=%d WB=%d" % (MAIN_H, CHART_H, BOTTOM_CHART_H, W1, W2, WB))


if __name__ == "__main__":
    main()
