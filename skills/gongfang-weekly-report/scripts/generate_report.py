#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gongfang Weekly Report Generator

Reads 6 Excel/CSV data files and generates an interactive HTML weekly report
using the create-report design system:
  - base-report.css (Linear dark + Stripe data precision)
  - Chart.js 4.x inline (no CDN)
  - chart-defaults.js (chartPresets / REPORT_FORMAT / REPORT_WOW)
"""

import argparse
import glob
import html
import json
import math
import os
from dataclasses import dataclass, field

import pandas as pd


FOCUS_INDUSTRY_MAP = {
    "绘画": "绘画",
    "VUP周边": "VUP周边",
}

FILE_PATTERNS = {
    "overall": ["整体数据*.csv", "整体数据*.xlsx", "整体数据*.xls"],
    "industry": ["行业数据*.csv", "行业数据*.xlsx", "行业数据*.xls"],
    "goods": ["行业商品明细数据*.csv", "行业商品明细数据*.xlsx", "行业商品明细数据*.xls"],
    "channel": ["内容渠道数据*.csv", "内容渠道数据*.xlsx", "内容渠道数据*.xls"],
    # 文件名是"商家销售明细"（非"商家销售明细数据"）
    "seller": ["商家销售明细*.csv", "商家销售明细*.xlsx", "商家销售明细*.xls"],
    "resource_entry": ["资源位二级入口数据*.csv", "资源位二级入口数据*.xlsx", "资源位二级入口数据*.xls"],
}

# ── Chart ID counter ───────────────────────────────────────────────────────────
_chart_id_counter = 0

def next_chart_id() -> str:
    global _chart_id_counter
    _chart_id_counter += 1
    return f"c{_chart_id_counter}"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", default="manual-run")
    return parser.parse_args()


def find_latest(input_dir: str, patterns: list[str]) -> str:
    matches = []
    for pattern in patterns:
        matches.extend(glob.glob(os.path.join(input_dir, pattern)))
    if not matches:
        raise FileNotFoundError(f"Missing required input for patterns: {patterns}")
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0]


def read_table(path: str) -> pd.DataFrame:
    if path.endswith(".csv"):
        return pd.read_csv(path)
    return pd.read_excel(path)


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df.rename(
        columns={
            "GMV（不减退款）": "GMV",
            "商详支付转化率-UV": "转化率",
            # "周五-周四周 " 带尾随空格，是周数（如 11、12、13），已是周粒度聚合，不需要 assign_week
            "周五-周四周 ": "周",
            "周五-周四周": "周",
        }
    )


def prepare_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """所有数据文件的"周五-周四周"列已经是周数（11、12…），
    每行本身就是周的聚合结果，不需要再按日聚合。
    rename 后直接返回。"""
    return rename_columns(df)


def prepare_goods(df: pd.DataFrame) -> pd.DataFrame:
    df = rename_columns(df)
    df["focus_industry"] = df["后台一级类目名称"].map(FOCUS_INDUSTRY_MAP)
    return df[df["focus_industry"].notna()].copy()


def prepare_seller(df: pd.DataFrame) -> pd.DataFrame:
    df = rename_columns(df)
    df["focus_industry"] = df["后台一级类目名称"].map(FOCUS_INDUSTRY_MAP)
    return df[df["focus_industry"].notna()].copy()


def prepare_resource(df: pd.DataFrame) -> pd.DataFrame:
    df = rename_columns(df)
    df["focus_industry"] = df["后台一级类目名称"].map(FOCUS_INDUSTRY_MAP)
    return df[df["focus_industry"].notna()].copy()


def focus_industry(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["focus_industry"] = df["后台一级类目名称"].map(FOCUS_INDUSTRY_MAP)
    return df[df["focus_industry"].notna()].copy()


def weekly_rollup(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    # Detect already-aggregated data (来自 focus_*_weekly 的子集)
    if "商品曝光PV" not in df.columns and "曝光PV" in df.columns:
        # 已是聚合后数据，只需确保有所需派生列
        result = df.copy()
        if "转化率" not in result.columns:
            result["转化率"] = result["支付订单数"] / result["商详UV"].replace(0, pd.NA)
        if "GPM" not in result.columns:
            result["GPM"] = result["GMV"] / result["曝光PV"].replace(0, pd.NA) * 1000
        if "PVCTR" not in result.columns:
            result["PVCTR"] = result["商详UV"] / result["曝光PV"].replace(0, pd.NA)
        return result.fillna(0)

    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(
            曝光PV=("商品曝光PV", "sum"),
            商详UV=("商详UV", "sum"),
            支付订单数=("支付订单数", "sum"),
            支付订单买家数=("支付订单买家数", "sum"),
            GMV=("GMV", "sum"),
        )
        .reset_index()
    )
    grouped["转化率"] = grouped["支付订单数"] / grouped["商详UV"].replace(0, pd.NA)
    grouped["GPM"] = grouped["GMV"] / grouped["曝光PV"].replace(0, pd.NA) * 1000
    grouped["PVCTR"] = grouped["商详UV"] / grouped["曝光PV"].replace(0, pd.NA)
    grouped = grouped.fillna(0)
    return grouped


def weekly_rollup_resource(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    # Detect already-aggregated data (来自 focus_*_weekly 的子集)
    if "商品曝光PV" not in df.columns and "曝光PV" in df.columns:
        result = df.copy()
        if "转化率" not in result.columns:
            result["转化率"] = result["支付订单数"] / result["商详UV"].replace(0, pd.NA)
        if "GPM" not in result.columns:
            result["GPM"] = result["GMV"] / result["曝光PV"].replace(0, pd.NA) * 1000
        if "PVCTR" not in result.columns:
            result["PVCTR"] = result["商详UV"] / result["曝光PV"].replace(0, pd.NA)
        return result.fillna(0)

    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(
            曝光PV=("商品曝光PV", "sum"),
            商详UV=("商详UV", "sum"),
            支付订单数=("支付订单数", "sum"),
            支付订单买家数=("支付订单买家数", "sum"),
            GMV=("GMV", "sum"),
        )
        .reset_index()
    )
    grouped["转化率"] = grouped["支付订单数"] / grouped["商详UV"].replace(0, pd.NA)
    grouped["GPM"] = grouped["GMV"] / grouped["曝光PV"].replace(0, pd.NA) * 1000
    grouped["PVCTR"] = grouped["商详UV"] / grouped["曝光PV"].replace(0, pd.NA)
    grouped = grouped.fillna(0)
    return grouped


def pct_change(curr: float, prev: float) -> float:
    if prev == 0:
        return 0.0
    return (curr - prev) / prev


def fmt_num(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def fmt_delta(value: float, digits: int = 1) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.{digits}f}%"


def wow_cell(current: float, previous: float, formatter) -> str:
    """Return HTML 'formatted_value (wow_delta)' with color-coded delta."""
    delta = pct_change(current, previous)
    cls = "up-text" if delta >= 0 else "down-text"
    return f"{formatter(current)} <span class='{cls}'>({fmt_delta(delta)})</span>"


def movement_text(metric: str, current: float, previous: float, digits: int = 2) -> str:
    delta = current - previous
    if delta > 0:
        direction = "上涨"
    elif delta < 0:
        direction = "下跌"
    else:
        direction = "持平"
    if direction == "持平":
        return f"{metric}持平 {fmt_num(current, digits)}"
    return f"{metric}{direction} {fmt_num(abs(delta), digits)}"


# ── Chart builders (Chart.js canvas-based) ──────────────────────────────────────

def _js_array(values: list) -> str:
    """Convert Python list to JS array literal. Handles numpy int64/float64."""
    def _convert(v):
        if isinstance(v, float):
            return round(v, 4)
        try:
            # Handle numpy int64, float64, etc.
            return round(float(v), 4)
        except (TypeError, ValueError):
            return v
    return json.dumps([_convert(v) for v in values])


def build_bar_chart(
    labels: list[str],
    values: list[float],
    title: str,
    chart_inits: list[str],
    y_format: str = "num",
) -> str:
    """Emit a Chart.js bar chart canvas and collect init JS."""
    if not values:
        return '<div class="chart-empty">暂无数据</div>'
    cid = next_chart_id()
    chart_inits.append(
        f"reportChart('{cid}', chartPresets.bar({_js_array(labels)}, "
        f"[{{label: '{title}', data: {_js_array(values)}}}], "
        f"{{yFormat: '{y_format}'}}));"
    )
    return (
        f'<div class="chart-container">'
        f'<figcaption>{html.escape(title)}</figcaption>'
        f'<div class="chart-area"><canvas id="{cid}"></canvas></div>'
        f'</div>'
    )


def build_line_chart(
    labels: list[str],
    values: list[float],
    title: str,
    chart_inits: list[str],
    y_format: str = "num",
) -> str:
    """Emit a Chart.js line chart canvas and collect init JS."""
    if not values:
        return '<div class="chart-empty">暂无数据</div>'
    cid = next_chart_id()
    chart_inits.append(
        f"reportChart('{cid}', chartPresets.line({_js_array(labels)}, "
        f"[{{label: '{title}', data: {_js_array(values)}}}], "
        f"{{yFormat: '{y_format}'}}));"
    )
    return (
        f'<div class="chart-container">'
        f'<figcaption>{html.escape(title)}</figcaption>'
        f'<div class="chart-area"><canvas id="{cid}"></canvas></div>'
        f'</div>'
    )


def build_combo_chart(
    labels: list[str],
    bar_values: list[float],
    line_values: list[float],
    title: str,
    bar_label: str,
    line_label: str,
    chart_inits: list[str],
    y_format: str = "pv",
    y1_format: str = "pct",
) -> str:
    """Emit a Chart.js combo (bar+line dual-axis) chart canvas."""
    if not labels:
        return '<div class="chart-empty">暂无数据</div>'
    cid = next_chart_id()
    chart_inits.append(
        f"reportChart('{cid}', chartPresets.combo({_js_array(labels)}, ["
        f"{{label: '{html.escape(bar_label)}', data: {_js_array(bar_values)}, yAxisID: 'y'}}, "
        f"{{type: 'line', label: '{html.escape(line_label)}', data: {_js_array(line_values)}, yAxisID: 'y1'}}"
        f"], {{yFormat: '{y_format}', y1Format: '{y1_format}'}}));"
    )
    return (
        f'<div class="chart-container">'
        f'<figcaption>{html.escape(title)}</figcaption>'
        f'<div class="chart-area"><canvas id="{cid}"></canvas></div>'
        f'</div>'
    )


def build_dual_line_chart(
    labels: list[str],
    left_values: list[float],
    right_values: list[float],
    title: str,
    left_label: str,
    right_label: str,
    chart_inits: list[str],
    y_format: str = "num",
) -> str:
    """Emit a Chart.js line chart with two series."""
    if not labels:
        return '<div class="chart-empty">暂无数据</div>'
    cid = next_chart_id()
    chart_inits.append(
        f"reportChart('{cid}', chartPresets.line({_js_array(labels)}, ["
        f"{{label: '{html.escape(left_label)}', data: {_js_array(left_values)}}}, "
        f"{{label: '{html.escape(right_label)}', data: {_js_array(right_values)}}}"
        f"], {{yFormat: '{y_format}'}}));"
    )
    return (
        f'<div class="chart-container">'
        f'<figcaption>{html.escape(title)}</figcaption>'
        f'<div class="chart-area"><canvas id="{cid}"></canvas></div>'
        f'</div>'
    )


def summary_card(title: str, current: float, previous: float, formatter, color_cls="") -> str:
    """Build a metric card using design system classes."""
    delta = pct_change(current, previous)
    trend_cls = "up" if delta >= 0 else "down"
    card_cls = f" {color_cls}" if color_cls else ""
    return (
        f'<div class="metric-card{card_cls}">'
        f'<p class="metric-label">{html.escape(title)}</p>'
        f'<p class="metric-value">{formatter(current)}</p>'
        f'<p class="metric-sub">上周 {formatter(previous)}'
        f'<span class="delta {trend_cls}">{fmt_delta(delta)}</span></p></div>'
    )


def narrative_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"<li>{html.escape(empty_text)}</li>"
    return "".join(f"<li>{html.escape(item)}</li>" for item in items)


# ── Table builders ─────────────────────────────────────────────────────────────

def build_shop_table(
    seller_df: pd.DataFrame,
    focus_name: str,
    current_week_start,
    previous_week_start,
    top_n: int = 5,
) -> str:
    """Top-N shops by GMV with WoW per metric."""
    df = seller_df[seller_df["focus_industry"] == focus_name]
    curr = df[df["周"] == current_week_start].copy()
    prev = df[df["周"] == previous_week_start].copy()

    if curr.empty:
        return "<p class='table-empty'>暂无商家数据</p>"

    curr_agg = (
        curr.groupby("店铺名称")
        .agg(支付订单数=("支付订单数", "sum"), GMV=("GMV", "sum"),
             买家数=("支付订单买家数", "sum"),
             商详UV=("商详UV", "sum"), 曝光PV=("商品曝光PV", "sum"))
        .reset_index()
    )
    prev_agg = (
        prev.groupby("店铺名称")
        .agg(支付订单数=("支付订单数", "sum"), GMV=("GMV", "sum"),
             买家数=("支付订单买家数", "sum"),
             商详UV=("商详UV", "sum"), 曝光PV=("商品曝光PV", "sum"))
        .reset_index()
    )
    merged = curr_agg.merge(prev_agg, on="店铺名称", how="outer", suffixes=("_curr", "_prev")).fillna(0)
    total_curr_gmv = merged["GMV_curr"].sum()
    merged["GMV占比"] = merged["GMV_curr"] / total_curr_gmv if total_curr_gmv else 0
    merged["转化率_curr"] = merged["支付订单数_curr"] / merged["商详UV_curr"].replace(0, pd.NA)
    merged["转化率_prev"] = merged["支付订单数_prev"] / merged["商详UV_prev"].replace(0, pd.NA)
    merged = merged.fillna(0)

    merged = merged.sort_values("GMV_curr", ascending=False).head(top_n)

    rows = []
    for _, row in merged.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['店铺名称']))}</td>"
            f"<td class='num'>{wow_cell(row['GMV_curr'], row['GMV_prev'], lambda v: fmt_num(v, 2))}</td>"
            f"<td class='num'>{fmt_pct(row['GMV占比'])}</td>"
            f"<td class='num'>{wow_cell(row['买家数_curr'], row['买家数_prev'], lambda v: fmt_num(v))}</td>"
            f"<td class='num'>{wow_cell(row['转化率_curr'], row['转化率_prev'], fmt_pct)}</td>"
            f"<td class='num'>{wow_cell(row['曝光PV_curr'], row['曝光PV_prev'], lambda v: fmt_num(v))}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>店铺名称</th><th class='num'>GMV（本周/上周环比）</th><th class='num'>GMV占行业整体占比</th>"
        "<th class='num'>买家数（本周/上周环比）</th><th class='num'>下单转化率（本周/上周环比）</th>"
        "<th class='num'>商品曝光PV（本周/上周环比）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan=\"6\">暂无数据</td></tr>'}</tbody></table></div>"
    )


def build_product_table(
    goods_df: pd.DataFrame,
    focus_name: str,
    current_goods_week,
    previous_goods_week,
    top_n: int = 10,
) -> str:
    """Top-N products by GMV with WoW per metric."""
    df = goods_df[goods_df["focus_industry"] == focus_name].copy()
    df["周"] = df["周"].astype(float)

    curr = df[df["周"] == current_goods_week]
    prev = df[df["周"] == previous_goods_week]

    if curr.empty:
        return "<p class='table-empty'>暂无商品数据</p>"

    curr_agg = (
        curr.groupby("商品名称")
        .agg(GMV=("GMV", "sum"), 买家数=("支付订单买家数", "sum"),
             商详UV=("商详UV", "sum"), 曝光PV=("商品曝光PV", "sum"),
             支付订单数=("支付订单数", "sum"))
        .reset_index()
    )
    prev_agg = (
        prev.groupby("商品名称")
        .agg(GMV=("GMV", "sum"), 买家数=("支付订单买家数", "sum"),
             商详UV=("商详UV", "sum"), 曝光PV=("商品曝光PV", "sum"),
             支付订单数=("支付订单数", "sum"))
        .reset_index()
    )

    merged = curr_agg.merge(prev_agg, on="商品名称", how="outer", suffixes=("_curr", "_prev")).fillna(0)
    merged["转化率_curr"] = merged["支付订单数_curr"] / merged["商详UV_curr"].replace(0, pd.NA)
    merged["转化率_prev"] = merged["支付订单数_prev"] / merged["商详UV_prev"].replace(0, pd.NA)
    merged = merged.fillna(0)
    merged = merged.sort_values("GMV_curr", ascending=False).head(top_n)

    rows = []
    for _, row in merged.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['商品名称']))}</td>"
            f"<td class='num'>{wow_cell(row['GMV_curr'], row['GMV_prev'], lambda v: fmt_num(v, 2))}</td>"
            f"<td class='num'>{wow_cell(row['买家数_curr'], row['买家数_prev'], lambda v: fmt_num(v))}</td>"
            f"<td class='num'>{wow_cell(row['转化率_curr'], row['转化率_prev'], fmt_pct)}</td>"
            f"<td class='num'>{wow_cell(row['曝光PV_curr'], row['曝光PV_prev'], lambda v: fmt_num(v))}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>商品名称</th><th class='num'>GMV（本周/上周环比）</th>"
        "<th class='num'>买家数（本周/上周环比）</th><th class='num'>下单转化率（本周/上周环比）</th>"
        "<th class='num'>商品曝光PV（本周/上周环比）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan=\"5\">暂无数据</td></tr>'}</tbody></table></div>"
    )


def build_channel_table(
    channel_df: pd.DataFrame,
    focus_name: str,
    current_week_start,
    previous_week_start,
    weeks: int = 4,
) -> str:
    """Content channel table: GMV/PV for last N weeks, share for current, PVCTR."""
    df = channel_df[channel_df["focus_industry"] == focus_name].copy()
    if df.empty:
        return "<p class='table-empty'>暂无渠道数据</p>"

    weekly = weekly_rollup(df, ["内容类型", "周"])
    weekly = weekly.sort_values(["内容类型", "周"])

    # get last N weeks
    all_weeks = sorted(weekly["周"].unique())
    lookback_weeks = all_weeks[-weeks:] if len(all_weeks) >= weeks else all_weeks

    # current week total GMV / PV for share calc
    curr_week_data = weekly[weekly["周"] == current_week_start]
    total_curr_gmv = curr_week_data["GMV"].sum()
    total_curr_pv = curr_week_data["曝光PV"].sum()

    # build pivot: channel x week
    pivot_gmv = weekly.pivot_table(index="内容类型", columns="周", values="GMV", aggfunc="sum", fill_value=0)
    pivot_pv = weekly.pivot_table(index="内容类型", columns="周", values="曝光PV", aggfunc="sum", fill_value=0)
    pivot_ctr = weekly.pivot_table(index="内容类型", columns="周", values="PVCTR", aggfunc="sum", fill_value=0)

    channels = sorted(weekly["内容类型"].unique())
    rows = []
    for ch in channels:
        gmv_vals = [pivot_gmv.loc[ch, w] if w in pivot_gmv.columns else 0 for w in lookback_weeks]
        pv_vals = [pivot_pv.loc[ch, w] if w in pivot_pv.columns else 0 for w in lookback_weeks]
        ctr_vals = [pivot_ctr.loc[ch, w] if w in pivot_ctr.columns else 0 for w in lookback_weeks]

        curr_gmv = gmv_vals[-1] if gmv_vals else 0
        curr_pv = pv_vals[-1] if pv_vals else 0
        gmv_share = curr_gmv / total_curr_gmv if total_curr_gmv else 0
        pv_share = curr_pv / total_curr_pv if total_curr_pv else 0

        gmv_4w = " / ".join(fmt_num(v, 0) for v in gmv_vals)
        pv_4w = " / ".join(fmt_num(v, 0) for v in pv_vals)
        ctr_4w = " / ".join(fmt_pct(c) for c in ctr_vals)

        rows.append(
            "<tr>"
            f"<td>{html.escape(str(ch))}</td>"
            f"<td class='num'>{gmv_4w}</td>"
            f"<td class='num'>{fmt_pct(gmv_share)}</td>"
            f"<td class='num'>{pv_4w}</td>"
            f"<td class='num'>{fmt_pct(pv_share)}</td>"
            f"<td class='num'>{ctr_4w}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>内容渠道</th><th class='num'>GMV（4周）</th><th class='num'>GMV占整体占比（本周）</th>"
        "<th class='num'>商品曝光PV（4周）</th><th class='num'>曝光PV占整体占比（本周）</th><th class='num'>PVCTR（4周）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan=\"6\">暂无数据</td></tr>'}</tbody></table></div>"
    )


def build_resource_table(
    resource_df: pd.DataFrame,
    focus_name: str,
    current_week_start,
    previous_week_start,
    weeks: int = 4,
) -> str:
    """Resource entry table: GMV/PV for last N weeks, share for current, PVCTR."""
    df = resource_df[resource_df["focus_industry"] == focus_name].copy()
    if df.empty:
        return "<p class='table-empty'>暂无资源位数据</p>"

    weekly = weekly_rollup_resource(
        df, ["资源位二级入口", "内容类型", "周"]
    )
    weekly = weekly.sort_values(["资源位二级入口", "周"])

    all_weeks = sorted(weekly["周"].unique())
    lookback_weeks = all_weeks[-weeks:] if len(all_weeks) >= weeks else all_weeks

    curr_week_data = weekly[weekly["周"] == current_week_start]
    total_curr_gmv = curr_week_data["GMV"].sum()
    total_curr_pv = curr_week_data["曝光PV"].sum()

    pivot_gmv = weekly.pivot_table(index="资源位二级入口", columns="周", values="GMV", aggfunc="sum", fill_value=0)
    pivot_pv = weekly.pivot_table(index="资源位二级入口", columns="周", values="曝光PV", aggfunc="sum", fill_value=0)
    pivot_ctr = weekly.pivot_table(index="资源位二级入口", columns="周", values="PVCTR", aggfunc="sum", fill_value=0)

    entries = sorted(weekly["资源位二级入口"].unique())
    rows = []
    for entry in entries:
        gmv_vals = [pivot_gmv.loc[entry, w] if w in pivot_gmv.columns else 0 for w in lookback_weeks]
        pv_vals = [pivot_pv.loc[entry, w] if w in pivot_pv.columns else 0 for w in lookback_weeks]
        ctr_vals = [pivot_ctr.loc[entry, w] if w in pivot_ctr.columns else 0 for w in lookback_weeks]

        # Skip rows where all 4 weeks of GMV are below 1000
        if all(abs(v) < 1000 for v in gmv_vals):
            continue

        curr_gmv = gmv_vals[-1] if gmv_vals else 0
        curr_pv = pv_vals[-1] if pv_vals else 0
        gmv_share = curr_gmv / total_curr_gmv if total_curr_gmv else 0
        pv_share = curr_pv / total_curr_pv if total_curr_pv else 0

        gmv_4w = " / ".join("-" if abs(v) < 1000 else fmt_num(v, 0) for v in gmv_vals)
        pv_4w = " / ".join("-" if abs(v) < 1000 else fmt_num(v, 0) for v in pv_vals)
        ctr_4w = " / ".join(fmt_pct(c) for c in ctr_vals)

        rows.append(
            "<tr>"
            f"<td>{html.escape(str(entry))}</td>"
            f"<td class='num'>{gmv_4w}</td>"
            f"<td class='num'>{fmt_pct(gmv_share)}</td>"
            f"<td class='num'>{pv_4w}</td>"
            f"<td class='num'>{fmt_pct(pv_share)}</td>"
            f"<td class='num'>{ctr_4w}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>资源位二级入口</th><th class='num'>GMV（4周）</th><th class='num'>GMV占整体占比（本周）</th>"
        "<th class='num'>商品曝光PV（4周）</th><th class='num'>曝光PV占整体占比（本周）</th><th class='num'>PVCTR（4周）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan=\"6\">暂无数据</td></tr>'}</tbody></table></div>"
    )


# ── Asset loader ───────────────────────────────────────────────────────────────

def _load_asset(filename: str) -> str:
    """Load a text asset from the skill's assets/ dir."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_path = os.path.join(script_dir, "..", "assets", filename)
    if not os.path.exists(asset_path):
        raise FileNotFoundError(f"Required asset not found: {asset_path}")
    with open(asset_path, "r", encoding="utf-8") as f:
        return f.read()


# ── Main report builder ─────────────────────────────────────────────────────────

@dataclass
class RenderBundle:
    html: str
    log_lines: list[str]


def build_report(
    overall_df: pd.DataFrame,
    industry_df: pd.DataFrame,
    channel_df: pd.DataFrame,
    goods_df: pd.DataFrame,
    seller_df: pd.DataFrame,
    resource_df: pd.DataFrame,
    run_id: str,
) -> RenderBundle:
    # Collect chart initialization JS calls
    chart_inits: list[str] = []

    overall_weekly = weekly_rollup(overall_df, ["周"]).sort_values("周")
    if len(overall_weekly) < 2:
        raise ValueError("整体数据不足，至少需要两个周周期")
    current_week = overall_weekly.iloc[-1]
    previous_week = overall_weekly.iloc[-2]

    focus_industry_weekly = weekly_rollup(focus_industry(industry_df), ["focus_industry", "周"])
    focus_channel_weekly = weekly_rollup(focus_industry(channel_df), ["focus_industry", "内容类型", "周"])
    focus_resource_weekly = weekly_rollup_resource(prepare_resource(resource_df), ["focus_industry", "内容类型", "资源位二级入口", "周"])

    # ── Section 1: Core data trend ───────────────────────────────────────────
    overall_pv = overall_weekly["曝光PV"].tolist()
    gmv_list = overall_weekly["GMV"].tolist()
    buyers_list = overall_weekly["支付订单买家数"].tolist()
    conversions_list = overall_weekly["转化率"].tolist()
    labels = ["W" + str(int(w)) for w in overall_weekly["周"].tolist()]

    overall_narratives = [
        f"GMV 本周 {fmt_num(current_week['GMV'], 2)}，较上周 {fmt_delta(pct_change(current_week['GMV'], previous_week['GMV']))}。",
        f"买家数本周 {fmt_num(current_week['支付订单买家数'])}，较上周 {fmt_delta(pct_change(current_week['支付订单买家数'], previous_week['支付订单买家数']))}。",
        f"支付订单数本周 {fmt_num(current_week['支付订单数'])}，较上周 {fmt_delta(pct_change(current_week['支付订单数'], previous_week['支付订单数']))}。",
        f"下单转化率本周 {fmt_pct(current_week['转化率'])}，较上周 {fmt_delta(pct_change(current_week['转化率'], previous_week['转化率']))}。",
    ]

    # 波动超5%的指标
    volatility_narratives = []
    for metric, label in [
        ("GMV", current_week["GMV"]),
        ("订单数", current_week["支付订单数"]),
        ("买家数", current_week["支付订单买家数"]),
        ("支付转化率", current_week["转化率"]),
    ]:
        prev_map = {"GMV": previous_week["GMV"], "订单数": previous_week["支付订单数"],
                    "买家数": previous_week["支付订单买家数"], "支付转化率": previous_week["转化率"]}
        delta = pct_change(label, prev_map[metric])
        if abs(delta) > 0.05:
            volatility_narratives.append(f"{metric} 环比波动 {fmt_delta(delta)}，超过5%阈值。")

    # Build Section 1 charts
    s1_gmv_chart = build_bar_chart(labels, gmv_list, "GMV 周趋势", chart_inits, y_format="gmv")
    s1_buyers_chart = build_bar_chart(labels, buyers_list, "买家数 周趋势", chart_inits, y_format="num")
    s1_conv_chart = build_line_chart(labels, conversions_list, "下单转化率 周趋势", chart_inits, y_format="pct")
    s1_pv_chart = build_line_chart(labels, overall_pv, "商品曝光PV 周趋势", chart_inits, y_format="pv")

    # ── Section 2: GMV 拆解 ───────────────────────────────────────────────────
    industry_blocks = []
    industry_narratives = []

    # 4-week lookback for industry line charts
    all_industry_weeks = sorted(focus_industry_weekly["周"].unique())
    lookback_4w = all_industry_weeks[-4:] if len(all_industry_weeks) >= 4 else all_industry_weeks
    chart_labels_4w = ["W" + str(int(w)) for w in lookback_4w]

    for focus_name in ["绘画", "VUP周边"]:
        curr_industry = focus_industry_weekly[
            (focus_industry_weekly["focus_industry"] == focus_name)
            & (focus_industry_weekly["周"] == current_week["周"])
        ]
        prev_industry = focus_industry_weekly[
            (focus_industry_weekly["focus_industry"] == focus_name)
            & (focus_industry_weekly["周"] == previous_week["周"])
        ]
        if curr_industry.empty or prev_industry.empty:
            continue
        curr_row = curr_industry.iloc[0]
        prev_row = prev_industry.iloc[0]

        # metric波动
        metric_changes = []
        for metric, col in [
            ("GMV", "GMV"),
            ("买家数", "支付订单买家数"),
            ("转化率", "转化率"),
            ("曝光PV", "曝光PV"),
        ]:
            delta = pct_change(curr_row[col], prev_row[col])
            if abs(delta) > 0.05:
                metric_changes.append(f"{metric} 环比 {fmt_delta(delta)}")

        # industry 4-week data
        ind_gmv_4w = {}
        ind_buyers_4w = {}
        ind_conv_4w = {}
        ind_pv_4w = {}
        for fn in ["绘画", "VUP周边"]:
            ind_gmv_4w[fn] = [
                focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ]["GMV"].iloc[0]
                if not focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ].empty else 0
                for w in lookback_4w
            ]
            ind_buyers_4w[fn] = [
                focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ]["支付订单买家数"].iloc[0]
                if not focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ].empty else 0
                for w in lookback_4w
            ]
            ind_conv_4w[fn] = [
                focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ]["转化率"].iloc[0]
                if not focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ].empty else 0
                for w in lookback_4w
            ]
            ind_pv_4w[fn] = [
                focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ]["曝光PV"].iloc[0]
                if not focus_industry_weekly[
                    (focus_industry_weekly["focus_industry"] == fn)
                    & (focus_industry_weekly["周"] == w)
                ].empty else 0
                for w in lookback_4w
            ]

        # Shop + product tables
        goods_weeks = sorted(goods_df["周"].dropna().astype(float).unique().tolist())
        current_goods_week = goods_weeks[-1] if goods_weeks else None
        previous_goods_week = goods_weeks[-2] if len(goods_weeks) >= 2 else None

        shop_table = build_shop_table(seller_df, focus_name, current_week["周"], previous_week["周"], top_n=5)
        product_table = build_product_table(goods_df, focus_name, current_goods_week, previous_goods_week, top_n=10)

        # 渠道占比变化
        share_changes = []
        channel_subset = focus_channel_weekly[focus_channel_weekly["focus_industry"] == focus_name].copy()
        if not channel_subset.empty:
            weekly_totals = channel_subset.groupby("周").agg(
                total_gmv=("GMV", "sum"),
                total_pv=("曝光PV", "sum"),
            )
            channel_subset = channel_subset.merge(weekly_totals, on="周", how="left")
            channel_subset["gmv_share"] = channel_subset["GMV"] / channel_subset["total_gmv"].replace(0, pd.NA)
            channel_subset["pv_share"] = channel_subset["曝光PV"] / channel_subset["total_pv"].replace(0, pd.NA)
            channel_subset = channel_subset.fillna(0)

            current_channels = channel_subset[channel_subset["周"] == current_week["周"]]
            previous_channels = channel_subset[channel_subset["周"] == previous_week["周"]]
            merged = current_channels.merge(
                previous_channels[["内容类型", "gmv_share", "pv_share"]],
                on="内容类型",
                suffixes=("_curr", "_prev"),
                how="outer",
            ).fillna(0)
            for _, row in merged.iterrows():
                gmv_share_delta = row["gmv_share_curr"] - row["gmv_share_prev"]
                pv_share_delta = row["pv_share_curr"] - row["pv_share_prev"]
                if abs(gmv_share_delta) > 0.05 or abs(pv_share_delta) > 0.05:
                    share_changes.append(
                        f"{row['内容类型']} 渠道：GMV占比 {fmt_delta(gmv_share_delta)}，曝光PV占比 {fmt_delta(pv_share_delta)}"
                    )

        # 商品归因 (top goods WoW analysis)
        goods_changes = []
        if current_goods_week is not None and previous_goods_week is not None:
            goods_subset = goods_df[goods_df["focus_industry"] == focus_name].copy()
            goods_subset["周"] = goods_subset["周"].astype(float)
            curr_goods = goods_subset[goods_subset["周"] == current_goods_week]
            prev_goods = goods_subset[goods_subset["周"] == previous_goods_week]
            goods_merged = (
                curr_goods.groupby("商品名称")
                .agg(curr_gmv=("GMV", "sum"), curr_buyers=("支付订单买家数", "sum"),
                     curr_uv=("商详UV", "sum"), curr_pv=("商品曝光PV", "sum"))
                .merge(
                    prev_goods.groupby("商品名称")
                    .agg(prev_gmv=("GMV", "sum"), prev_buyers=("支付订单买家数", "sum"),
                         prev_uv=("商详UV", "sum"), prev_pv=("商品曝光PV", "sum")),
                    on="商品名称",
                    how="outer",
                )
                .fillna(0)
                .reset_index()
            )
            goods_merged["abs_gmv_delta"] = (goods_merged["curr_gmv"] - goods_merged["prev_gmv"]).abs()
            top_goods = goods_merged.sort_values("abs_gmv_delta", ascending=False).head(5)
            for _, row in top_goods.iterrows():
                if row["abs_gmv_delta"] == 0:
                    continue
                goods_changes.append(
                    f"{row['商品名称']}："
                    f"{movement_text('GMV', row['curr_gmv'], row['prev_gmv'])}，"
                    f"{movement_text('买家数', row['curr_buyers'], row['prev_buyers'], 0)}，"
                    f"{movement_text('商详UV', row['curr_uv'], row['prev_uv'], 0)}。"
                )

        # Build industry charts (4-week trend lines)
        ind_gmv_chart = build_line_chart(chart_labels_4w, ind_gmv_4w.get(focus_name, []), f"GMV 过去4周", chart_inits, y_format="gmv")
        ind_buyers_chart = build_line_chart(chart_labels_4w, ind_buyers_4w.get(focus_name, []), f"买家数 过去4周", chart_inits, y_format="num")
        ind_conv_chart = build_line_chart(chart_labels_4w, ind_conv_4w.get(focus_name, []), f"下单转化率 过去4周", chart_inits, y_format="pct")
        ind_pv_chart = build_line_chart(chart_labels_4w, ind_pv_4w.get(focus_name, []), f"商品曝光PV 过去4周", chart_inits, y_format="pv")

        # Section 2 industry block (using breakdown-block from design system)
        industry_blocks.append(
            f"""
            <div class="breakdown-block" id="{html.escape(focus_name.replace('+', '-'))}">
              <div class="breakdown-head">
                <div>
                  <h3>{html.escape(focus_name)} <span>GMV {fmt_num(curr_row['GMV'], 2)}</span></h3>
                  <p>本周较上周 {fmt_delta(pct_change(curr_row['GMV'], prev_row['GMV']))}</p>
                </div>
              </div>
              <div class="metric-grid">
                {summary_card("GMV", curr_row["GMV"], prev_row["GMV"], lambda v: fmt_num(v, 2))}
                {summary_card("买家数", curr_row["支付订单买家数"], prev_row["支付订单买家数"], lambda v: fmt_num(v), "green")}
                {summary_card("下单转化率", curr_row["转化率"], prev_row["转化率"], fmt_pct, "amber")}
                {summary_card("商品曝光PV", curr_row["曝光PV"], prev_row["曝光PV"], lambda v: fmt_num(v), "blue")}
              </div>

              <div class="grid-2" style="margin-top: var(--sp-7);">
                {ind_gmv_chart}
                {ind_buyers_chart}
                {ind_conv_chart}
                {ind_pv_chart}
              </div>

              <div class="panel">
                <h4>重点商家 TOP5</h4>
                {shop_table}
              </div>

              <div class="panel">
                <h4>重点商品 TOP10</h4>
                {product_table}
              </div>

              <div class="grid-2" style="margin-top: var(--sp-7);">
                <div class="panel">
                  <h4>指标波动</h4>
                  <ul>{narrative_list(metric_changes, "本周重点指标环比变化未超过5%。")}</ul>
                </div>
                <div class="panel">
                  <h4>渠道占比变化</h4>
                  <ul>{narrative_list(share_changes, "本周未观察到占比变化超过5%的内容渠道。")}</ul>
                </div>
              </div>
              <div class="conclusion">
                <h4>商品归因结论</h4>
                <ul>{narrative_list(goods_changes, "本周未识别到明显的重点商品变化。")}</ul>
              </div>
            </div>
            """
        )
        industry_narratives.append(
            f"{focus_name}：{'；'.join(metric_changes[:2] + share_changes[:1]) or '本周整体表现平稳。'}"
        )

    # ── Section 3: 流量 拆解 ────────────────────────────────────────────────
    flow_blocks = []
    for focus_name in ["绘画", "VUP周边"]:
        ch_data = focus_channel_weekly[focus_channel_weekly["focus_industry"] == focus_name].copy()
        re_data = focus_resource_weekly[focus_resource_weekly["focus_industry"] == focus_name].copy()

        # Compute channel-level weekly totals for share calculation
        ch_weekly_totals = ch_data.groupby(["周"]).agg(total_gmv=("GMV", "sum"), total_pv=("曝光PV", "sum")).reset_index()
        ch_data = ch_data.merge(ch_weekly_totals, on="周", how="left")
        ch_data["gmv_share"] = ch_data["GMV"] / ch_data["total_gmv"].replace(0, pd.NA)
        ch_data["pv_share"] = ch_data["曝光PV"] / ch_data["total_pv"].replace(0, pd.NA)
        ch_data = ch_data.fillna(0)

        # Compute resource-entry weekly totals for share calculation
        re_weekly_totals = re_data.groupby(["周"]).agg(total_gmv=("GMV", "sum"), total_pv=("曝光PV", "sum")).reset_index()
        re_data = re_data.merge(re_weekly_totals, on="周", how="left")
        re_data["gmv_share"] = re_data["GMV"] / re_data["total_gmv"].replace(0, pd.NA)
        re_data["pv_share"] = re_data["曝光PV"] / re_data["total_pv"].replace(0, pd.NA)
        re_data = re_data.fillna(0)

        # Determine top-2 channels by current GMV
        curr_ch_data = ch_data[ch_data["周"] == current_week["周"]]
        top2_channels = curr_ch_data.nlargest(2, "GMV")["内容类型"].tolist()

        # Determine top-4 resource entries by current GMV
        curr_re_data = re_data[re_data["周"] == current_week["周"]]
        top4_entries = curr_re_data.nlargest(4, "GMV")["资源位二级入口"].tolist()

        # Build per-channel 4w data dicts
        def _ch_series(ch, field_name):
            ch_subset = ch_data[ch_data["内容类型"] == ch]
            return [
                ch_subset[ch_subset["周"] == w][field_name].iloc[0]
                if not ch_subset[ch_subset["周"] == w].empty else 0
                for w in lookback_4w
            ]

        def _re_series(entry, field_name):
            re_subset = re_data[re_data["资源位二级入口"] == entry]
            return [
                re_subset[re_subset["周"] == w][field_name].iloc[0]
                if not re_subset[re_subset["周"] == w].empty else 0
                for w in lookback_4w
            ]

        # Channel table + resource table
        channel_table = build_channel_table(
            focus_channel_weekly[focus_channel_weekly["focus_industry"] == focus_name],
            focus_name, current_week["周"], previous_week["周"], weeks=4
        )
        resource_table = build_resource_table(
            focus_resource_weekly[focus_resource_weekly["focus_industry"] == focus_name],
            focus_name, current_week["周"], previous_week["周"], weeks=4
        )

        # Channel attribution
        channel_attribution = []
        curr_ch = ch_data[ch_data["周"] == current_week["周"]]
        prev_ch = ch_data[ch_data["周"] == previous_week["周"]]
        if not curr_ch.empty and not prev_ch.empty:
            merged_ch = curr_ch.merge(
                prev_ch[["内容类型", "GMV", "曝光PV", "PVCTR"]],
                on="内容类型", suffixes=("_curr", "_prev")
            ).fillna(0)
            for _, row in merged_ch.iterrows():
                gmv_delta = pct_change(row["GMV_curr"], row["GMV_prev"])
                pv_delta = pct_change(row["曝光PV_curr"], row["曝光PV_prev"])
                ctr_curr = row["PVCTR_curr"]
                ctr_prev = row["PVCTR_prev"]
                ctr_delta = pct_change(ctr_curr, ctr_prev)
                if abs(gmv_delta) > 0.05:
                    reasons = []
                    if abs(pv_delta) > 0.05:
                        reasons.append(f"曝光PV {fmt_delta(pv_delta)}")
                    if abs(ctr_delta) > 0.05:
                        reasons.append(f"PVCTR {fmt_delta(ctr_delta)}")
                    channel_attribution.append(
                        f"{row['内容类型']} 渠道 GMV 环比 {fmt_delta(gmv_delta)}"
                        + (f"，主因：{'、'.join(reasons)}" if reasons else "，需进一步分析")
                    )

        # Build combo charts for top-2 channels
        ch_gmv_charts = []
        ch_pv_charts = []
        for ch in top2_channels:
            gmv_vals = _ch_series(ch, "GMV")
            gmv_share_vals = _ch_series(ch, "gmv_share")
            ch_gmv_charts.append(
                build_combo_chart(
                    chart_labels_4w, gmv_vals, gmv_share_vals,
                    f"{ch} 渠道 GMV + 占比", "GMV", "GMV占比",
                    chart_inits, y_format="gmv", y1_format="pct"
                )
            )
            pv_vals = _ch_series(ch, "曝光PV")
            pv_share_vals = _ch_series(ch, "pv_share")
            ch_pv_charts.append(
                build_combo_chart(
                    chart_labels_4w, pv_vals, pv_share_vals,
                    f"{ch} 渠道 曝光PV + 占比", "曝光PV", "曝光PV占比",
                    chart_inits, y_format="pv", y1_format="pct"
                )
            )

        # Build combo charts for top-4 resource entries
        re_gmv_charts = []
        re_pv_charts = []
        for entry in top4_entries:
            gmv_vals = _re_series(entry, "GMV")
            gmv_share_vals = _re_series(entry, "gmv_share")
            re_gmv_charts.append(
                build_combo_chart(
                    chart_labels_4w, gmv_vals, gmv_share_vals,
                    f"{entry} GMV + 占比", "GMV", "GMV占比",
                    chart_inits, y_format="gmv", y1_format="pct"
                )
            )
            pv_vals = _re_series(entry, "曝光PV")
            pv_share_vals = _re_series(entry, "pv_share")
            re_pv_charts.append(
                build_combo_chart(
                    chart_labels_4w, pv_vals, pv_share_vals,
                    f"{entry} 曝光PV + 占比", "曝光PV", "曝光PV占比",
                    chart_inits, y_format="pv", y1_format="pct"
                )
            )

        flow_blocks.append(
            f"""
            <div class="breakdown-block" id="{html.escape('flow-' + focus_name.replace('+', '-'))}">
              <div class="breakdown-head">
                <div>
                  <h3>{html.escape(focus_name)} 流量拆解</h3>
                </div>
              </div>

              <div class="panel">
                <h4>内容渠道 GMV + 占比 趋势（Top2，过去4周）</h4>
                <div class="grid-2" style="margin-top: var(--sp-7);">
                  {''.join(ch_gmv_charts) or '<div class="chart-empty">暂无数据</div>'}
                </div>
              </div>

              <div class="panel">
                <h4>内容渠道 曝光PV + 占比 趋势（Top2，过去4周）</h4>
                <div class="grid-2" style="margin-top: var(--sp-7);">
                  {''.join(ch_pv_charts) or '<div class="chart-empty">暂无数据</div>'}
                </div>
              </div>

              <div class="panel">
                <h4>内容渠道详情</h4>
                {channel_table}
              </div>

              <div class="panel">
                <h4>资源位二级入口 GMV + 占比 趋势（Top4，过去4周）</h4>
                <div class="grid-2" style="margin-top: var(--sp-7);">
                  {''.join(re_gmv_charts) or '<div class="chart-empty">暂无资源位数据</div>'}
                </div>
              </div>

              <div class="panel">
                <h4>资源位二级入口 曝光PV + 占比 趋势（Top4，过去4周）</h4>
                <div class="grid-2" style="margin-top: var(--sp-7);">
                  {''.join(re_pv_charts) or '<div class="chart-empty">暂无资源位数据</div>'}
                </div>
              </div>

              <div class="panel">
                <h4>资源位二级入口详情</h4>
                {resource_table}
              </div>

              <div class="conclusion">
                <h4>流量归因结论</h4>
                <ul>{narrative_list(channel_attribution, '本周流量侧未观察到导致GMV波动的明显渠道变化。')}</ul>
              </div>
            </div>
            """)

    # ── Load design system assets ──────────────────────────────────────────────
    css_content = _load_asset("base-report.css")
    chartjs_content = _load_asset("chart.umd.min.js")
    chart_defaults_content = _load_asset("chart-defaults.js")

    # ── Nav scroll highlight JS ────────────────────────────────────────────────
    nav_js = """
    (function() {
      var sections = document.querySelectorAll('section[id]');
      var navLinks = document.querySelectorAll('.nav a');
      window.addEventListener('scroll', function() {
        var scrollY = window.scrollY + 80;
        sections.forEach(function(sec) {
          if (scrollY >= sec.offsetTop) {
            navLinks.forEach(function(a) { a.classList.remove('active'); });
            var active = document.querySelector('.nav a[href="#' + sec.id + '"]');
            if (active) active.classList.add('active');
          }
        });
      });
    })();
    """

    # ── Chart init JS ──────────────────────────────────────────────────────────
    chart_init_js = "\n".join(chart_inits)

    # ── Assemble HTML ──────────────────────────────────────────────────────────
    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>工房业务交易双周报</title>
    <style>
{css_content}
    </style>
  </head>
  <body>
    <div class="page">
      <header class="hero">
        <div class="hero-eyebrow">工房业务交易双周报</div>
        <h1>交易数据概览</h1>
        <p class="hero-desc">聚焦核心数据趋势、重点行业波动、渠道占比变化与商品归因。</p>
        <div class="hero-meta">
          <span class="hero-badge"><strong>W{int(current_week["周"])}</strong> 本周</span>
          <span class="hero-badge">W{int(previous_week["周"])} 上周</span>
          <span class="hero-badge">Run: {html.escape(run_id)}</span>
        </div>
      </header>

      <nav class="nav">
        <a href="#s1" class="active">核心数据趋势</a>
        <a href="#s2">GMV 拆解</a>
        <a href="#s3">流量拆解</a>
        <a href="#s4">数据说明</a>
      </nav>

      <!-- Section 1: 核心数据趋势 -->
      <section id="s1" class="section">
        <div class="section-head">
          <div>
            <span class="section-num">SECTION 01</span>
            <h2>核心数据趋势</h2>
            <p class="section-desc">看清工房交易规模与效率的周变化，重点关注 GMV、买家数、下单转化率和商品曝光PV。</p>
          </div>
        </div>
        <div class="metric-grid">
          {summary_card("GMV", current_week["GMV"], previous_week["GMV"], lambda v: fmt_num(v, 2))}
          {summary_card("买家数", current_week["支付订单买家数"], previous_week["支付订单买家数"], lambda v: fmt_num(v), "green")}
          {summary_card("下单转化率", current_week["转化率"], previous_week["转化率"], fmt_pct, "amber")}
          {summary_card("商品曝光PV", current_week["曝光PV"], previous_week["曝光PV"], lambda v: fmt_num(v), "blue")}
        </div>
        <div class="grid-2" style="margin-top: var(--sp-7);">
          {s1_gmv_chart}
          {s1_buyers_chart}
          {s1_conv_chart}
          {s1_pv_chart}
        </div>
        <div class="conclusion" style="margin-top: var(--sp-7);">
          <h4>本周结论</h4>
          <ul>{narrative_list(overall_narratives, "暂无可输出结论。")}</ul>
        </div>
        <div class="conclusion">
          <h4>波动超过5%的指标</h4>
          <ul>{narrative_list(volatility_narratives, "本周重点指标环比变化未超过5%。")}</ul>
        </div>
      </section>

      <!-- Section 2: GMV 拆解 -->
      <section id="s2" class="section">
        <div class="section-head">
          <div>
            <span class="section-num">SECTION 02</span>
            <h2>GMV 拆解</h2>
            <p class="section-desc">了解每个行业的交易规模变化趋势，得出 GMV 波动的原因分析。</p>
          </div>
        </div>
        <div class="conclusion">
          <h4>行业汇总摘要</h4>
          <ul>{narrative_list(industry_narratives, "当前未形成重点行业摘要。")}</ul>
        </div>
        {''.join(industry_blocks)}
      </section>

      <!-- Section 3: 流量 拆解 -->
      <section id="s3" class="section">
        <div class="section-head">
          <div>
            <span class="section-num">SECTION 03</span>
            <h2>流量拆解</h2>
            <p class="section-desc">了解每个行业的流量渠道转化趋势，得出流量波动的原因分析。</p>
          </div>
        </div>
        {''.join(flow_blocks)}
      </section>

      <!-- Section 4: 数据说明 -->
      <section id="s4" class="section">
        <div class="section-head">
          <div>
            <span class="section-num">SECTION 04</span>
            <h2>数据说明</h2>
          </div>
        </div>
        <div class="panel">
          <ul>
            <li>所有源文件每行已代表一个完整周（周数在"周五-周四周"列），无需再按日聚合。</li>
            <li>行业口径聚焦绘画与 VUP周边，分别独立分析。</li>
            <li>下单转化率使用周内支付订单数 / 商详UV 聚合口径计算。</li>
            <li>商品曝光PV/GPM 使用周内 GMV / 商品曝光PV x 1000 聚合口径计算。</li>
            <li>PVCTR 使用周内 商详UV / 商品曝光PV 计算。</li>
            <li>商品归因仅引用行业商品明细数据中当前周与上周的 GMV、买家数、商详UV 变化。</li>
            <li>仅解释指标环比波动超过5%的行业指标和占比变化超过5%的渠道。</li>
          </ul>
        </div>
        <div class="footnote">
          <strong>数据说明</strong><br/>
          生成时间取自本地执行环境。所有图表使用 Chart.js 4.x 内联渲染，支持 file:// 直接打开。
        </div>
      </section>
    </div>

    <!-- Chart.js 4.x (inline, not CDN) -->
    <script>
{chartjs_content}
    </script>

    <!-- chart-defaults.js (inline) -->
    <script>
{chart_defaults_content}
    </script>

    <!-- Chart initialization -->
    <script>
{chart_init_js}
    </script>

    <!-- Nav scroll highlight -->
    <script>
{nav_js}
    </script>
  </body>
</html>
"""

    logs = [
        f"current_week=W{int(current_week['周'])}",
        f"previous_week=W{int(previous_week['周'])}",
        f"overall_weeks={len(overall_weekly)}",
        f"industry_blocks={len(industry_blocks)}",
        f"flow_blocks={len(flow_blocks)}",
        f"chart_count={_chart_id_counter}",
        f"css_size={len(css_content)} bytes",
        f"chartjs_size={len(chartjs_content)} bytes",
    ]
    return RenderBundle(html=html_out, log_lines=logs)


def main():
    args = parse_args()
    print(f"INFO: input_dir={args.input_dir}")
    print(f"INFO: output={args.output}")

    files = {key: find_latest(args.input_dir, patterns) for key, patterns in FILE_PATTERNS.items()}
    for key, path in files.items():
        print(f"INFO: matched {key} → {os.path.basename(path)}")

    overall_df = prepare_weekly(read_table(files["overall"]))
    industry_df = prepare_weekly(read_table(files["industry"]))
    channel_df = prepare_weekly(read_table(files["channel"]))
    goods_df = prepare_goods(read_table(files["goods"]))
    seller_df = prepare_seller(read_table(files["seller"]))
    resource_df = prepare_resource(read_table(files["resource_entry"]))

    print(f"INFO: overall rows={len(overall_df)}, industry rows={len(industry_df)}")
    print(f"INFO: channel rows={len(channel_df)}, goods rows={len(goods_df)}")
    print(f"INFO: seller rows={len(seller_df)}, resource rows={len(resource_df)}")

    bundle = build_report(
        overall_df, industry_df, channel_df, goods_df, seller_df, resource_df, args.run_id
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(bundle.html)
    print(f"INFO: generated_html={args.output}")
    print(f"INFO: html_size={len(bundle.html)} bytes")
    for line in bundle.log_lines:
        print(f"INFO: {line}")


if __name__ == "__main__":
    main()
