#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
import html
import math
import os
from dataclasses import dataclass

import pandas as pd


FOCUS_INDUSTRY_MAP = {
    "绘画": "绘画+绘画周边",
    "绘画周边": "绘画+绘画周边",
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
    return f"{formatter(current)} <span class='cell-wow {cls}'>({fmt_delta(delta)})</span>"


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


# ── Chart builders ─────────────────────────────────────────────────────────────

def build_bar_chart(labels: list[str], values: list[float], title: str, color: str) -> str:
    if not values:
        return ""
    width = 520
    height = 240
    pad = 32
    inner_h = height - pad * 2
    inner_w = width - pad * 2
    # axis always starts at 0
    max_value = max(values) or 1
    bar_w = inner_w / max(len(values), 1) * 0.6
    gap = inner_w / max(len(values), 1)
    bars = []
    for idx, value in enumerate(values):
        x = pad + idx * gap + (gap - bar_w) / 2
        h = inner_h * (value / max_value)
        y = height - pad - h
        label = html.escape(labels[idx])
        bars.append(
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w:.1f}' height='{h:.1f}' rx='6' fill='{color}' opacity='0.9'></rect>"
            f"<text x='{x + bar_w / 2:.1f}' y='{height - 8}' text-anchor='middle' font-size='12' fill='#6b7a99'>{label}</text>"
            f"<text x='{x + bar_w / 2:.1f}' y='{max(y - 6, 14):.1f}' text-anchor='middle' font-size='12' fill='#e8ecf4' font-weight='600'>{fmt_num(value)}</text>"
        )
    return (
        f"<figure class='chart'><figcaption>{html.escape(title)}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}' style='display:block;width:100%;height:auto;'>"
        f"<line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#2a3149' stroke-width='1.5'/>"
        f"{''.join(bars)}</svg></figure>"
    )


def build_line_chart(labels: list[str], values: list[float], title: str, color: str, percent: bool = False) -> str:
    if not values:
        return ""
    width = 520
    height = 240
    pad = 32
    inner_h = height - pad * 2
    inner_w = width - pad * 2
    # axis always starts at 0
    min_value = 0
    max_value = max(values) or 1
    span = max_value - min_value
    points = []
    dots = []
    for idx, value in enumerate(values):
        x = pad + inner_w * (idx / max(len(values) - 1, 1))
        y = height - pad - inner_h * ((value - min_value) / span if span else 0.5)
        points.append(f"{x:.1f},{y:.1f}")
        label = fmt_pct(value) if percent else fmt_num(value, 1)
        dots.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4.5' fill='{color}'></circle>"
            f"<text x='{x:.1f}' y='{max(y - 8, 14):.1f}' text-anchor='middle' font-size='12' fill='#e8ecf4' font-weight='600'>{label}</text>"
            f"<text x='{x:.1f}' y='{height - 8}' text-anchor='middle' font-size='12' fill='#6b7a99'>{html.escape(labels[idx])}</text>"
        )
    return (
        f"<figure class='chart'><figcaption>{html.escape(title)}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}' style='display:block;width:100%;height:auto;'>"
        f"<line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#2a3149' stroke-width='1.5'/>"
        f"<polyline fill='none' stroke='{color}' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' points='{' '.join(points)}'></polyline>"
        f"{''.join(dots)}</svg></figure>"
    )


def _bar_line_dual_axis(
    labels: list[str],
    bar_values: list[float],
    line_values: list[float],
    title: str,
    bar_label: str,
    line_label: str,
    bar_color: str = "#c2410c",
    line_color: str = "#0f766e",
) -> str:
    """Bar+Line dual-axis chart: bars for absolute values, line for percentage share.
    Left axis: absolute value. Right axis: percentage (0-1).
    Bar fills from bottom (y=bottom) upward; line shares same 0-1 percentage space."""
    if not labels:
        return ""
    width = 520
    height = 240
    pad = 32
    inner_h = height - pad * 2
    inner_w = width - pad * 2
    bottom_y = height - pad  # SVG y of the bottom baseline

    max_bar = max(bar_values) or 1
    max_line = max(line_values) or 1
    n = len(labels)

    # Build bar rects and line points
    bar_rects = []
    line_points = []
    hit_circles = []

    for idx in range(n):
        x = pad + inner_w * (idx / max(n - 1, 1))

        # Bar: from bottom baseline upward
        bar_h = inner_h * (bar_values[idx] / max_bar)
        bar_rects.append(
            f"<rect x='{x-18:.1f}' y='{bottom_y - bar_h:.1f}' "
            f"width='36' height='{bar_h:.1f}' rx='4' fill='{bar_color}' opacity='0.85'/>"
        )
        bar_rects.append(
            f"<text x='{x:.1f}' y='{bottom_y - bar_h - 6:.1f}' "
            f"text-anchor='middle' font-size='11' fill='{bar_color}' font-weight='600'>"
            f"{fmt_num(bar_values[idx])}</text>"
        )

        # Line: same 0-at-bottom convention as bar
        line_y = bottom_y - inner_h * (line_values[idx] / max_line)
        line_points.append(f"{x:.1f},{line_y:.1f}")

        # Hit area
        hit_circles.append(
            f"<circle class='hit' data-label='{html.escape(labels[idx])}' "
            f"data-lv='{bar_values[idx]}' data-rv='{line_values[idx]}' "
            f"cx='{x:.1f}' cy='{line_y:.1f}' r='14' fill='transparent' cursor='pointer'/>"
        )

    # Left axis (bar / absolute value): ticks at 0, 25%, 50%, 75%, 100%
    left_axis = []
    left_axis.append(f"<line x1='{pad}' y1='{pad}' x2='{pad}' y2='{bottom_y}' stroke='{bar_color}' stroke-width='1.5' opacity='0.5'/>")
    for i in range(5):
        frac = i / 4
        tick_y = bottom_y - frac * inner_h
        val = frac * max_bar
        left_axis.append(f"<line x1='{pad-4}' y1='{tick_y:.1f}' x2='{pad}' y2='{tick_y:.1f}' stroke='{bar_color}' stroke-width='1' opacity='0.5'/>")
        left_axis.append(f"<text x='{pad-8}' y='{tick_y+4:.1f}' text-anchor='end' font-size='10' fill='{bar_color}' opacity='0.8'>{fmt_num(val, 0)}</text>")

    # Right axis (line / percentage): ticks at 0%, 25%, 50%, 75%, 100%
    right_axis = []
    right_axis.append(f"<line x1='{width-pad}' y1='{pad}' x2='{width-pad}' y2='{bottom_y}' stroke='{line_color}' stroke-width='1.5' opacity='0.5'/>")
    for i in range(5):
        frac = i / 4
        tick_y = bottom_y - frac * inner_h
        val = frac * max_line
        right_axis.append(f"<line x1='{width-pad}' y1='{tick_y:.1f}' x2='{width-pad+4}' y2='{tick_y:.1f}' stroke='{line_color}' stroke-width='1' opacity='0.5'/>")
        right_axis.append(f"<text x='{width-pad+8}' y='{tick_y+4:.1f}' text-anchor='start' font-size='10' fill='{line_color}' opacity='0.8'>{fmt_pct(val)}</text>")

    return (
        f"<figure class='chart' style='position:relative'>"
        f"<figcaption>{html.escape(title)}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}' style='display:block;width:100%;height:auto;'>"
        f"<line x1='{pad}' y1='{bottom_y}' x2='{width-pad}' y2='{bottom_y}' stroke='#2a3149' stroke-width='1.5'/>"
        f"{''.join(left_axis)}"
        f"{''.join(right_axis)}"
        f"{''.join(bar_rects)}"
        f"<polyline fill='none' stroke='{line_color}' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' points='{' '.join(line_points)}'/>"
        f"{''.join(hit_circles)}"
        f"<rect x='{pad+4}' y='{14}' width='8' height='8' rx='2' fill='{bar_color}' opacity='0.9'/>"
        f"<text x='{pad+16}' y='{22}' font-size='11' fill='{bar_color}' font-weight='600'>{html.escape(bar_label)}</text>"
        f"<rect x='{width-pad-60}' y='{14}' width='8' height='8' rx='2' fill='{line_color}' opacity='0.9'/>"
        f"<text x='{width-pad-48}' y='{22}' font-size='11' fill='{line_color}' font-weight='600'>{html.escape(line_label)}</text>"
        f"</svg>"
        f"<div class='chart-tooltip' "
        f"data-left='{html.escape(bar_label)}' data-right='{html.escape(line_label)}'></div>"
        f"</figure>"
    )


def build_dual_axis_chart(
    labels: list[str],
    left_values: list[float],
    right_values: list[float],
    title: str,
    left_label: str,
    right_label: str,
    left_color: str = "#c2410c",
    right_color: str = "#0f766e",
) -> str:
    if not labels:
        return ""
    width = 520
    height = 240
    pad = 32
    inner_h = height - pad * 2
    inner_w = width - pad * 2
    bottom_y = height - pad

    max_left = max(left_values) or 1
    max_right = max(right_values) or 1
    n = len(labels)

    left_points = []
    right_points = []
    all_dots = []
    hit_circles = []
    axis_parts = []

    # Left axis: from bottom_y upward
    axis_parts.append(f"<line x1='{pad}' y1='{pad}' x2='{pad}' y2='{bottom_y}' stroke='{left_color}' stroke-width='1.5' opacity='0.5'/>")
    for i in range(5):
        frac = i / 4
        tick_y = bottom_y - frac * inner_h
        val = frac * max_left
        axis_parts.append(f"<line x1='{pad-4}' y1='{tick_y:.1f}' x2='{pad}' y2='{tick_y:.1f}' stroke='{left_color}' stroke-width='1' opacity='0.5'/>")
        axis_parts.append(f"<text x='{pad-8}' y='{tick_y+4:.1f}' text-anchor='end' font-size='10' fill='{left_color}' opacity='0.8'>{fmt_num(val, 0)}</text>")

    # Right axis
    axis_parts.append(f"<line x1='{width-pad}' y1='{pad}' x2='{width-pad}' y2='{bottom_y}' stroke='{right_color}' stroke-width='1.5' opacity='0.5'/>")
    for i in range(5):
        frac = i / 4
        tick_y = bottom_y - frac * inner_h
        val = frac * max_right
        axis_parts.append(f"<line x1='{width-pad}' y1='{tick_y:.1f}' x2='{width-pad+4}' y2='{tick_y:.1f}' stroke='{right_color}' stroke-width='1' opacity='0.5'/>")
        axis_parts.append(f"<text x='{width-pad+8}' y='{tick_y+4:.1f}' text-anchor='start' font-size='10' fill='{right_color}' opacity='0.8'>{fmt_num(val, 0)}</text>")

    for idx in range(n):
        x = pad + inner_w * (idx / max(n - 1, 1))

        ly = inner_h * (left_values[idx] / max_left)
        left_points.append(f"{x:.1f},{bottom_y - ly:.1f}")

        ry = inner_h * (right_values[idx] / max_right)
        right_points.append(f"{x:.1f},{bottom_y - ry:.1f}")

        hit_circles.append(
            f"<circle class='hit' data-label='{html.escape(labels[idx])}' "
            f"data-lv='{left_values[idx]}' data-rv='{right_values[idx]}' "
            f"cx='{x:.1f}' cy='{bottom_y - ly:.1f}' r='14' fill='transparent' cursor='pointer'/>"
        )

        all_dots.append(
            f"<circle cx='{x:.1f}' cy='{bottom_y - ly:.1f}' r='4.5' fill='{left_color}'></circle>"
            f"<circle cx='{x:.1f}' cy='{bottom_y - ry:.1f}' r='4.5' fill='{right_color}'></circle>"
        )
        all_dots.append(
            f"<text x='{x:.1f}' y='{height - 8}' text-anchor='middle' font-size='12' fill='#6b7a99'>{html.escape(labels[idx])}</text>"
        )

    return (
        f"<figure class='chart' style='position:relative'>"
        f"<figcaption>{html.escape(title)}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}' style='display:block;width:100%;height:auto;'>"
        f"<line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#2a3149' stroke-width='1.5'/>"
        f"{''.join(axis_parts)}"
        f"<polyline fill='none' stroke='{left_color}' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' points='{' '.join(left_points)}'></polyline>"
        f"<polyline fill='none' stroke='{right_color}' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' points='{' '.join(right_points)}'></polyline>"
        f"{''.join(all_dots)}"
        f"{''.join(hit_circles)}"
        f"<rect x='{pad+4}' y='{14}' width='8' height='8' rx='2' fill='{left_color}' opacity='0.9'/>"
        f"<text x='{pad+16}' y='{22}' font-size='11' fill='{left_color}' font-weight='600'>{html.escape(left_label)}</text>"
        f"<rect x='{width-pad-60}' y='{14}' width='8' height='8' rx='2' fill='{right_color}' opacity='0.9'/>"
        f"<text x='{width-pad-48}' y='{22}' font-size='11' fill='{right_color}' font-weight='600'>{html.escape(right_label)}</text>"
        f"</svg>"
        f"<div class='chart-tooltip' "
        f"data-left='{html.escape(left_label)}' data-right='{html.escape(right_label)}'></div>"
        f"</figure>"
    )


def summary_card(title: str, current: float, previous: float, formatter, color_cls="orange") -> str:
    delta = pct_change(current, previous)
    trend_cls = "up" if delta >= 0 else "down"
    return (
        f"<article class='metric-card {color_cls}'>"
        f"<p class='metric-label'>{html.escape(title)}</p>"
        f"<p class='metric-value'>{formatter(current)}</p>"
        f"<p class='metric-sub'>上周 {formatter(previous)}"
        f"<span class='delta {trend_cls}'>{fmt_delta(delta)}</span></p></article>"
    )


def narrative_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"<li>{html.escape(empty_text)}</li>"
    return "".join(f"<li>{html.escape(item)}</li>" for item in items)


# ── Table builders ─────────────────────────────────────────────────────────────

def _th_sort_key(col: str) -> int:
    """Return sort priority: 0=name, 1+=metric order."""
    if "名称" in col or "店铺" in col or "渠道" in col or "入口" in col:
        return 0
    return 1


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
            f"<td>{wow_cell(row['GMV_curr'], row['GMV_prev'], lambda v: fmt_num(v, 2))}</td>"
            f"<td>{fmt_pct(row['GMV占比'])}</td>"
            f"<td>{wow_cell(row['买家数_curr'], row['买家数_prev'], lambda v: fmt_num(v))}</td>"
            f"<td>{wow_cell(row['转化率_curr'], row['转化率_prev'], fmt_pct)}</td>"
            f"<td>{wow_cell(row['曝光PV_curr'], row['曝光PV_prev'], lambda v: fmt_num(v))}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>店铺名称</th><th>GMV（本周/上周环比）</th><th>GMV占行业整体占比</th>"
        "<th>买家数（本周/上周环比）</th><th>下单转化率（本周/上周环比）</th>"
        "<th>商品曝光PV（本周/上周环比）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan="6">暂无数据</td></tr>'}</tbody></table></div>"
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
            f"<td>{wow_cell(row['GMV_curr'], row['GMV_prev'], lambda v: fmt_num(v, 2))}</td>"
            f"<td>{wow_cell(row['买家数_curr'], row['买家数_prev'], lambda v: fmt_num(v))}</td>"
            f"<td>{wow_cell(row['转化率_curr'], row['转化率_prev'], fmt_pct)}</td>"
            f"<td>{wow_cell(row['曝光PV_curr'], row['曝光PV_prev'], lambda v: fmt_num(v))}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>商品名称</th><th>GMV（本周/上周环比）</th>"
        "<th>买家数（本周/上周环比）</th><th>下单转化率（本周/上周环比）</th>"
        "<th>商品曝光PV（本周/上周环比）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan="5">暂无数据</td></tr>'}</tbody></table></div>"
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
        avg_ctr = sum(ctr_vals) / len([c for c in ctr_vals if c > 0]) if any(c > 0 for c in ctr_vals) else 0

        gmv_4w = " / ".join(fmt_num(v, 0) for v in gmv_vals)
        pv_4w = " / ".join(fmt_num(v, 0) for v in pv_vals)
        ctr_4w = " / ".join(fmt_pct(c) for c in ctr_vals)

        rows.append(
            "<tr>"
            f"<td>{html.escape(str(ch))}</td>"
            f"<td>{gmv_4w}</td>"
            f"<td>{fmt_pct(gmv_share)}</td>"
            f"<td>{pv_4w}</td>"
            f"<td>{fmt_pct(pv_share)}</td>"
            f"<td>{ctr_4w}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>内容渠道</th>"
        f"<th colspan='{len(lookback_weeks)}'>GMV（{len(lookback_weeks)}周）</th>"
        "<th>GMV占整体占比（本周）</th>"
        f"<th colspan='{len(lookback_weeks)}'>商品曝光PV（{len(lookback_weeks)}周）</th>"
        "<th>曝光PV占整体占比（本周）</th>"
        f"<th colspan='{len(lookback_weeks)}'>PVCTR（{len(lookback_weeks)}周）</th>"
        "</tr></thead>"
    )
    # Simplified: show as single combined cells
    thead_simple = (
        "<thead><tr>"
        "<th>内容渠道</th><th>GMV（4周）</th><th>GMV占整体占比（本周）</th>"
        "<th>商品曝光PV（4周）</th><th>曝光PV占整体占比（本周）</th><th>PVCTR（4周）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead_simple}<tbody>{''.join(rows) or '<tr><td colspan="6">暂无数据</td></tr>'}</tbody></table></div>"
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
            f"<td>{gmv_4w}</td>"
            f"<td>{fmt_pct(gmv_share)}</td>"
            f"<td>{pv_4w}</td>"
            f"<td>{fmt_pct(pv_share)}</td>"
            f"<td>{ctr_4w}</td>"
            "</tr>"
        )

    thead = (
        "<thead><tr>"
        "<th>资源位二级入口</th><th>GMV（4周）</th><th>GMV占整体占比（本周）</th>"
        "<th>商品曝光PV（4周）</th><th>曝光PV占整体占比（本周）</th><th>PVCTR（4周）</th>"
        "</tr></thead>"
    )
    return (
        f"<div class='table-wrap'><table>{thead}<tbody>{''.join(rows) or '<tr><td colspan="6">暂无数据</td></tr>'}</tbody></table></div>"
    )


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
    overall_weekly = weekly_rollup(overall_df, ["周"]).sort_values("周")
    if len(overall_weekly) < 2:
        raise ValueError("整体数据不足，至少需要两个周周期")
    current_week = overall_weekly.iloc[-1]
    previous_week = overall_weekly.iloc[-2]

    focus_industry_weekly = weekly_rollup(focus_industry(industry_df), ["focus_industry", "周"])
    focus_channel_weekly = weekly_rollup(focus_industry(channel_df), ["focus_industry", "内容类型", "周"])
    focus_resource_weekly = weekly_rollup_resource(prepare_resource(resource_df), ["focus_industry", "内容类型", "资源位二级入口", "周"])

    # ── Section ①: Core data trend ───────────────────────────────────────────
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

    #波动超5%的指标
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

    # ── Section ②: GMV 拆解 ───────────────────────────────────────────────────
    industry_blocks = []
    industry_narratives = []

    # 4-week lookback for industry line charts
    all_industry_weeks = sorted(focus_industry_weekly["周"].unique())
    lookback_4w = all_industry_weeks[-4:] if len(all_industry_weeks) >= 4 else all_industry_weeks
    chart_labels_4w = ["W" + str(int(w)) for w in lookback_4w]

    for focus_name in ["绘画+绘画周边", "VUP周边"]:
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

        # industry line charts data (4 weeks, 2 industries)
        ind_gmv = [
            focus_industry_weekly[
                (focus_industry_weekly["focus_industry"] == fn)
                & (focus_industry_weekly["周"] == w)
            ]["GMV"].iloc[0]
            if not focus_industry_weekly[
                (focus_industry_weekly["focus_industry"] == fn)
                & (focus_industry_weekly["周"] == w)
            ].empty else 0
            for fn in ["绘画+绘画周边", "VUP周边"]
            for w in [lookback_4w[-1]]
        ]
        # Actually per-industry for chart: need 4 values per industry
        ind_gmv_4w = {}
        ind_buyers_4w = {}
        ind_conv_4w = {}
        ind_pv_4w = {}
        for fn in ["绘画+绘画周边", "VUP周边"]:
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

        # Section ② industry block
        industry_blocks.append(
            f"""
            <section class="industry-block" id="{html.escape(focus_name.replace('+', '-'))}">
              <div class="industry-head">
                <h3>{html.escape(focus_name)}</h3>
                <p>本周 GMV {fmt_num(curr_row['GMV'], 2)}，较上周 {fmt_delta(pct_change(curr_row['GMV'], prev_row['GMV']))}。</p>
              </div>
              <div class="metric-grid small">
                {summary_card("GMV", curr_row["GMV"], prev_row["GMV"], lambda v: fmt_num(v, 2))}
                {summary_card("买家数", curr_row["支付订单买家数"], prev_row["支付订单买家数"], lambda v: fmt_num(v))}
                {summary_card("下单转化率", curr_row["转化率"], prev_row["转化率"], fmt_pct)}
                {summary_card("商品曝光PV", curr_row["曝光PV"], prev_row["曝光PV"], lambda v: fmt_num(v))}
              </div>

              <div class="chart-grid">
                {build_line_chart(chart_labels_4w, ind_gmv_4w.get(focus_name, []), f"GMV 过去4周", "#c2410c")}
                {build_line_chart(chart_labels_4w, ind_buyers_4w.get(focus_name, []), f"买家数 过去4周", "#0f766e")}
                {build_line_chart(chart_labels_4w, ind_conv_4w.get(focus_name, []), f"下单转化率 过去4周", "#7c3aed", percent=True)}
                {build_line_chart(chart_labels_4w, ind_pv_4w.get(focus_name, []), f"商品曝光PV 过去4周", "#b45309")}
              </div>

              <article class="panel">
                <h4>重点商家 TOP5（表格1/3）</h4>
                {shop_table}
              </article>

              <article class="panel">
                <h4>重点商品 TOP10（表格2/4）</h4>
                {product_table}
              </article>

              <div class="analysis-grid">
                <article class="panel">
                  <h4>指标波动</h4>
                  <ul>{narrative_list(metric_changes, "本周重点指标环比变化未超过5%。")}</ul>
                </article>
                <article class="panel">
                  <h4>渠道占比变化</h4>
                  <ul>{narrative_list(share_changes, "本周未观察到占比变化超过5%的内容渠道。")}</ul>
                </article>
              </div>
              <article class="panel">
                <h4>商品归因结论</h4>
                <ul>{narrative_list(goods_changes, "本周未识别到明显的重点商品变化。")}</ul>
              </article>
            </section>
            """
        )
        industry_narratives.append(
            f"{focus_name}：{'；'.join(metric_changes[:2] + share_changes[:1]) or '本周整体表现平稳。'}"
        )

    # ── Section ③: 流量 拆解 ────────────────────────────────────────────────
    flow_blocks = []
    for focus_name in ["绘画+绘画周边", "VUP周边"]:
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
        def _ch_series(ch, field):
            ch_subset = ch_data[ch_data["内容类型"] == ch]
            return [
                ch_subset[ch_subset["周"] == w][field].iloc[0]
                if not ch_subset[ch_subset["周"] == w].empty else 0
                for w in lookback_4w
            ]

        def _re_series(entry, field):
            re_subset = re_data[re_data["资源位二级入口"] == entry]
            return [
                re_subset[re_subset["周"] == w][field].iloc[0]
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
                prev_ch[["内容类型", "GMV", "曝光PV"]],
                on="内容类型", suffixes=("_curr", "_prev")
            ).fillna(0)
            for _, row in merged_ch.iterrows():
                gmv_delta = pct_change(row["GMV_curr"], row["GMV_prev"])
                pv_delta = pct_change(row["曝光PV_curr"], row["曝光PV_prev"])
                ctr_curr = row["商详UV"] / row["曝光PV_curr"] if row["曝光PV_curr"] else 0
                ctr_prev = row["商详UV"] / row["曝光PV_prev"] if row["曝光PV_prev"] else 0
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

        # Build GMV bar+line charts for top-2 channels
        gmv_charts = []
        for ch in top2_channels:
            gmv_vals = _ch_series(ch, "GMV")
            share_vals = _ch_series(ch, "gmv_share")
            gmv_charts.append(
                _bar_line_dual_axis(
                    chart_labels_4w, gmv_vals, share_vals,
                    f"{ch} 渠道 GMV + 占比",
                    "GMV", "GMV占比", "#c2410c", "#0f766e"
                )
            )

        # Build PV bar+line charts for top-2 channels
        pv_charts = []
        for ch in top2_channels:
            pv_vals = _ch_series(ch, "曝光PV")
            share_vals = _ch_series(ch, "pv_share")
            pv_charts.append(
                _bar_line_dual_axis(
                    chart_labels_4w, pv_vals, share_vals,
                    f"{ch} 渠道 曝光PV + 占比",
                    "曝光PV", "曝光PV占比", "#b45309", "#7c3aed"
                )
            )

        # Build GMV bar+line charts for top-4 resource entries
        re_gmv_charts = []
        for entry in top4_entries:
            gmv_vals = _re_series(entry, "GMV")
            share_vals = _re_series(entry, "gmv_share")
            re_gmv_charts.append(
                _bar_line_dual_axis(
                    chart_labels_4w, gmv_vals, share_vals,
                    f"{entry} GMV + 占比",
                    "GMV", "GMV占比", "#c2410c", "#0f766e"
                )
            )

        # Build PV bar+line charts for top-4 resource entries
        re_pv_charts = []
        for entry in top4_entries:
            pv_vals = _re_series(entry, "曝光PV")
            share_vals = _re_series(entry, "pv_share")
            re_pv_charts.append(
                _bar_line_dual_axis(
                    chart_labels_4w, pv_vals, share_vals,
                    f"{entry} 曝光PV + 占比",
                    "曝光PV", "曝光PV占比", "#b45309", "#7c3aed"
                )
            )

        flow_blocks.append(
            f"""
            <section class="flow-block" id="{html.escape('flow-' + focus_name.replace('+', '-'))}">
              <div class="industry-head">
                <h3>{html.escape(focus_name)} 流量拆解</h3>
              </div>

              <article class="panel">
                <h4>内容渠道 GMV + 占比 趋势（Top2，过去4周）</h4>
                <div class="chart-grid">
                  {''.join(gmv_charts) or '<p class="chart-empty">暂无数据</p>'}
                </div>
              </article>

              <article class="panel">
                <h4>内容渠道 曝光PV + 占比 趋势（Top2，过去4周）</h4>
                <div class="chart-grid">
                  {''.join(pv_charts) or '<p class="chart-empty">暂无数据</p>'}
                </div>
              </article>

              <article class="panel">
                <h4>内容渠道详情（表格）</h4>
                {channel_table}
              </article>

              <article class="panel">
                <h4>资源位二级入口 GMV + 占比 趋势（Top4，过去4周）</h4>
                <div class="chart-grid">
                  {''.join(re_gmv_charts) or '<p class="chart-empty">暂无资源位数据</p>'}
                </div>
              </article>

              <article class="panel">
                <h4>资源位二级入口 曝光PV + 占比 趋势（Top4，过去4周）</h4>
                <div class="chart-grid">
                  {''.join(re_pv_charts) or '<p class="chart-empty">暂无资源位数据</p>'}
                </div>
              </article>

              <article class="panel">
                <h4>资源位二级入口详情（表格）</h4>
                {resource_table}
              </article>

              <article class="panel">
                <h4>流量归因结论</h4>
                <ul>{narrative_list(channel_attribution, '本周流量侧未观察到导致GMV波动的明显渠道变化。')}</ul>
              </article>
            </section>
            """)

    # ── HTML Styles ────────────────────────────────────────────────────────────
    styles = """
    :root {
      --bg: #0f1117;
      --surface: #161b27;
      --card: #1c2235;
      --card-hover: #232a40;
      --border: #2a3149;
      --ink: #e8ecf4;
      --muted: #6b7a99;
      --accent-orange: #f97316;
      --accent-teal: #14b8a6;
      --accent-purple: #a78bfa;
      --accent-amber: #fbbf24;
      --up: #34d399;
      --down: #f87171;
      --shadow: 0 4px 24px rgba(0,0,0,0.4);
      --shadow-lg: 0 8px 40px rgba(0,0,0,0.5);
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: "PingFang SC", "Noto Sans SC", -apple-system, sans-serif;
      color: var(--ink);
      background: var(--bg);
      min-height: 100vh;
    }
    a { color: inherit; text-decoration: none; }
    .page { max-width: 1280px; margin: 0 auto; padding: 40px 24px 80px; }

    /* ── Hero ── */
    .hero {
      background: linear-gradient(135deg, #1c2235 0%, #161b27 50%, #1a1f2e 100%);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 36px 40px 32px;
      box-shadow: var(--shadow-lg);
      position: relative;
      overflow: hidden;
    }
    .hero::before {
      content: '';
      position: absolute;
      top: -60px; right: -60px;
      width: 240px; height: 240px;
      background: radial-gradient(circle, rgba(249,115,22,0.15) 0%, transparent 70%);
      pointer-events: none;
    }
    .hero::after {
      content: '';
      position: absolute;
      bottom: -80px; left: 60px;
      width: 300px; height: 300px;
      background: radial-gradient(circle, rgba(20,184,166,0.10) 0%, transparent 70%);
      pointer-events: none;
    }
    .hero-eyebrow {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: var(--accent-orange);
      margin-bottom: 10px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 32px;
      font-weight: 800;
      background: linear-gradient(90deg, #fff 30%, rgba(255,255,255,0.6) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      line-height: 1.2;
    }
    .hero-desc {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 14px;
      max-width: 560px;
    }
    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 24px;
    }
    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 999px;
      font-size: 13px;
      font-weight: 500;
      color: var(--ink);
    }
    .hero-badge strong { color: var(--accent-orange); font-weight: 700; }

    /* ── Nav ── */
    .nav {
      position: sticky;
      top: 0;
      z-index: 100;
      margin: 24px 0 32px;
      padding: 10px 16px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      background: rgba(22,27,39,0.85);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--border);
      border-radius: 16px;
    }
    .nav a {
      padding: 8px 16px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 500;
      color: var(--muted);
      transition: all 0.15s ease;
    }
    .nav a:hover { background: var(--card); color: var(--ink); }
    .nav a.active { background: var(--card); color: var(--ink); box-shadow: 0 0 0 1px var(--border); }

    /* ── Section ── */
    .section { margin-top: 36px; }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      margin-bottom: 20px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .section-head h2 {
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      color: var(--ink);
      letter-spacing: -0.3px;
    }
    .section-head-desc {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
      max-width: 520px;
    }
    .section-num {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      color: var(--accent-orange);
      text-transform: uppercase;
    }

    /* ── Metric Cards ── */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .metric-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px 20px 18px;
      box-shadow: var(--shadow);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
      position: relative;
      overflow: hidden;
    }
    .metric-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      border-radius: 18px 18px 0 0;
    }
    .metric-card.orange::before { background: var(--accent-orange); }
    .metric-card.teal::before { background: var(--accent-teal); }
    .metric-card.purple::before { background: var(--accent-purple); }
    .metric-card.amber::before { background: var(--accent-amber); }
    .metric-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
    .metric-label {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.8px;
    }
    .metric-value {
      margin: 10px 0 6px;
      font-size: 28px;
      font-weight: 800;
      color: var(--ink);
      letter-spacing: -0.5px;
      line-height: 1;
    }
    .metric-sub {
      margin: 0;
      font-size: 12px;
      color: var(--muted);
    }
    .delta {
      margin-left: 6px;
      font-weight: 700;
      font-size: 12px;
    }
    .delta.up { color: var(--up); }
    .delta.down { color: var(--down); }
    .delta.neutral { color: var(--muted); }

    /* ── Chart Grid ── */
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 16px;
    }
    .chart-grid.three-col {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 16px;
    }

    /* ── Chart ── */
    .chart {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      box-shadow: var(--shadow);
    }
    .chart figcaption {
      font-weight: 700;
      font-size: 14px;
      color: var(--ink);
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .chart figcaption::before {
      content: '';
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 3px;
    }
    .chart.orange figcaption::before { background: var(--accent-orange); }
    .chart.teal figcaption::before { background: var(--accent-teal); }
    .chart.purple figcaption::before { background: var(--accent-purple); }
    .chart.amber figcaption::before { background: var(--accent-amber); }
    .chart-empty {
      color: var(--muted);
      font-size: 13px;
      padding: 40px 16px;
      text-align: center;
      background: var(--card);
      border: 1px dashed var(--border);
      border-radius: 18px;
    }
    .table-empty {
      color: var(--muted);
      font-size: 13px;
      padding: 32px 16px;
      text-align: center;
    }

    /* ── Panel ── */
    .panel {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px 24px;
      box-shadow: var(--shadow);
      margin-top: 16px;
    }
    .panel h4 {
      margin: 0 0 14px;
      font-size: 15px;
      font-weight: 700;
      color: var(--ink);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel h4::before {
      content: '';
      display: inline-block;
      width: 4px;
      height: 16px;
      border-radius: 2px;
      background: var(--accent-orange);
    }
    .panel ul {
      margin: 0;
      padding-left: 20px;
      line-height: 2;
      color: var(--ink);
      font-size: 13.5px;
    }
    .panel li { margin-bottom: 4px; }

    /* ── Industry / Flow Blocks ── */
    .industry-block, .flow-block {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 24px;
      margin-top: 20px;
      box-shadow: var(--shadow);
    }
    .industry-head, .flow-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 20px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }
    .industry-head h3, .flow-head h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }
    .industry-head h3 span, .flow-head h3 span {
      font-size: 12px;
      font-weight: 500;
      color: var(--muted);
      margin-left: 8px;
    }
    .industry-head p, .flow-head p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
    .block-badge {
      display: inline-flex;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
    }
    .block-badge.up { background: rgba(52,211,153,0.12); color: var(--up); }
    .block-badge.down { background: rgba(248,113,113,0.12); color: var(--down); }

    /* ── Table ── */
    .table-wrap {
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid var(--border);
      margin-top: 14px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    thead { background: rgba(255,255,255,0.03); }
    th {
      padding: 11px 14px;
      text-align: left;
      font-weight: 600;
      font-size: 11.5px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.6px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    td {
      padding: 11px 14px;
      border-bottom: 1px solid rgba(42,49,73,0.6);
      color: var(--ink);
      white-space: nowrap;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255,255,255,0.02); }
    .td-mono {
      font-family: "SF Mono", "Fira Code", monospace;
      font-size: 12.5px;
    }
    .cell-wow { font-size: 11.5px; }
    .up-text { color: var(--up); font-weight: 600; }
    .down-text { color: var(--down); font-weight: 600; }

    /* ── Chart Tooltip ── */
    .chart-tooltip {
      position: absolute;
      top: 36px;
      right: 16px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 12px;
      color: var(--ink);
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.15s ease;
      z-index: 10;
      min-width: 140px;
      box-shadow: var(--shadow-lg);
    }
    .chart-tooltip.visible { opacity: 1; }
    .chart-tooltip .tt-label { color: var(--muted); font-size: 11px; margin-bottom: 6px; font-weight: 600; }
    .chart-tooltip .tt-row { display: flex; justify-content: space-between; gap: 12px; margin: 3px 0; }
    .chart-tooltip .tt-lbl { color: var(--muted); font-size: 11.5px; }
    .chart-tooltip .tt-val { font-weight: 700; font-size: 12.5px; font-family: "SF Mono", "Fira Code", monospace; }

    /* ── Footnote ── */
    .footnote {
      margin-top: 32px;
      padding: 20px 24px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.8;
    }
    .footnote strong { color: var(--ink); }

    /* ── Responsive ── */
    @media (max-width: 900px) {
      .metric-grid, .chart-grid, .analysis-grid, .chart-grid.three-col {
        grid-template-columns: 1fr;
      }
      .section-head, .industry-head, .flow-head {
        flex-direction: column;
        align-items: flex-start;
      }
      .hero { padding: 28px 24px 24px; }
      .hero h1 { font-size: 26px; }
    }
    @media (max-width: 600px) {
      .page { padding: 20px 16px 60px; }
      .metric-grid { grid-template-columns: repeat(2, 1fr); }
    }
    """

    JS_TOOLTIP = """
    <script>
    (function() {
      /* Chart tooltip hover */
      function fmtNum(v) { return v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1000 ? (v/1000).toFixed(1)+'K' : v.toLocaleString('zh-CN',{maximumFractionDigits:0}); }
      function fmtPct(v) { return (v*100).toFixed(1)+'%'; }

      document.querySelectorAll('.chart-tooltip').forEach(function(tt) {
        var leftLbl = tt.getAttribute('data-left') || 'GMV';
        var rightLbl = tt.getAttribute('data-right') || '占比';
        var container = tt.closest('figure');
        if (!container) return;

        container.querySelectorAll('.hit').forEach(function(circle) {
          circle.addEventListener('mouseenter', function() {
            var label = circle.getAttribute('data-label') || '';
            var lv = parseFloat(circle.getAttribute('data-lv')) || 0;
            var rv = parseFloat(circle.getAttribute('data-rv')) || 0;

            tt.innerHTML =
              '<div class="tt-label">' + label + '</div>' +
              '<div class="tt-row"><span class="tt-lbl">' + leftLbl + '</span><span class="tt-val" style="color:#f97316">' + fmtNum(lv) + '</span></div>' +
              '<div class="tt-row"><span class="tt-lbl">' + rightLbl + '</span><span class="tt-val" style="color:#14b8a6">' + fmtNum(rv) + '</span></div>';
            tt.classList.add('visible');
          });
          circle.addEventListener('mouseleave', function() {
            tt.classList.remove('visible');
          });
        });
      });

      /* Nav active link highlight */
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
    </script>
    """

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>工房业务交易双周报</title>
    <style>{styles}</style>
  </head>
  <body>
    <div class="page">
      <header class="hero">
        <div class="hero-eyebrow">工房业务交易周报</div>
        <h1>交易数据概览</h1>
        <p class="hero-desc">聚焦核心数据趋势、重点行业波动、渠道占比变化与商品归因。</p>
        <div class="hero-meta">
          <span class="hero-badge"><strong>W{int(current_week["周"])}</strong> 本周</span>
          <span class="hero-badge">W{int(previous_week["周"])} 上周</span>
          <span class="hero-badge">Run: {html.escape(run_id)}</span>
        </div>
      </header>

      <nav class="nav">
        <a href="#core-data-trend">核心数据趋势</a>
        <a href="#gmv-breakdown">GMV 拆解</a>
        <a href="#flow-breakdown">流量 拆解</a>
        <a href="#data-notes">数据说明</a>
      </nav>

      <!-- Section ①: 核心数据趋势 -->
      <section id="core-data-trend" class="section">
        <div class="section-head">
          <div>
            <div class="section-num">01 / 核心数据趋势</div>
            <h2>核心数据趋势</h2>
            <p class="section-head-desc">看清工房交易规模与效率的周变化，重点关注 GMV、买家数、下单转化率和商品曝光PV。</p>
          </div>
        </div>
        <div class="metric-grid">
          {summary_card("GMV", current_week["GMV"], previous_week["GMV"], lambda v: fmt_num(v, 2), "orange")}
          {summary_card("买家数", current_week["支付订单买家数"], previous_week["支付订单买家数"], lambda v: fmt_num(v), "teal")}
          {summary_card("下单转化率", current_week["转化率"], previous_week["转化率"], fmt_pct, "purple")}
          {summary_card("商品曝光PV", current_week["曝光PV"], previous_week["曝光PV"], lambda v: fmt_num(v), "amber")}
        </div>
        <div class="chart-grid">
          {build_bar_chart(labels, gmv_list, "GMV 周趋势", "#c2410c")}
          {build_bar_chart(labels, buyers_list, "买家数 周趋势", "#0f766e")}
          {build_line_chart(labels, conversions_list, "下单转化率 周趋势", "#7c3aed", percent=True)}
          {build_line_chart(labels, overall_pv, "商品曝光PV 周趋势", "#b45309")}
        </div>
        <article class="panel" style="margin-top:16px;">
          <h4>本周结论</h4>
          <ul>{narrative_list(overall_narratives, "暂无可输出结论。")}</ul>
        </article>
        <article class="panel" style="margin-top:16px;">
          <h4>波动超过5%的指标</h4>
          <ul>{narrative_list(volatility_narratives, "本周重点指标环比变化未超过5%。")}</ul>
        </article>
      </section>

      <!-- Section ②: GMV 拆解 -->
      <section id="gmv-breakdown" class="section">
        <div class="section-head">
          <div>
            <div class="section-num">02 / GMV 拆解</div>
            <h2>GMV 拆解</h2>
            <p class="section-head-desc">了解每个行业的交易规模变化趋势，得出 GMV 波动的原因分析。</p>
          </div>
        </div>
        <article class="panel">
          <h4>行业汇总摘要</h4>
          <ul>{narrative_list(industry_narratives, "当前未形成重点行业摘要。")}</ul>
        </article>
        {''.join(industry_blocks)}
      </section>

      <!-- Section ③: 流量 拆解 -->
      <section id="flow-breakdown" class="section">
        <div class="section-head">
          <div>
            <div class="section-num">03 / 流量 拆解</div>
            <h2>流量 拆解</h2>
            <p class="section-head-desc">了解每个行业的流量渠道转化趋势，得出流量波动的原因分析。</p>
          </div>
        </div>
        {''.join(flow_blocks)}
      </section>

      <!-- Data notes -->
      <section id="data-notes" class="section">
        <div class="section-head">
          <div>
            <div class="section-num">04 / 数据说明</div>
            <h2>数据说明</h2>
            <p class="section-head-desc">所有结论仅基于已声明的数据合同与字段，不补充额外因果推断。</p>
          </div>
        </div>
        <article class="panel">
          <ul>
            <li>所有源文件每行已代表一个完整周（周数在"周五-周四周"列），无需再按日聚合。</li>
            <li>绘画+绘画周边为合并行业口径，VUP周边单独分析。</li>
            <li>下单转化率使用周内支付订单数 / 商详UV 聚合口径计算。</li>
            <li>商品曝光PV/GPM 使用周内 GMV / 商品曝光PV × 1000 聚合口径计算。</li>
            <li>PVCTR 使用周内 商详UV / 商品曝光PV 计算。</li>
            <li>商品归因仅引用行业商品明细数据中当前周与上周的 GMV、买家数、商详UV 变化。</li>
            <li>仅解释指标环比波动超过5%的行业指标和占比变化超过5%的渠道。</li>
            <li>所有图表坐标轴从0开始，不使用截断坐标轴。</li>
          </ul>
        </article>
        <div class="footnote">生成时间取自本地执行环境。当前版本已输出真实聚合结果、SVG 图表和行业分析，不再是占位 HTML。</div>
      </section>
    </div>
    {JS_TOOLTIP}
  </body>
</html>
"""

    logs = [
        f"current_week=W{int(current_week['周'])}",
        f"previous_week=W{int(previous_week['周'])}",
        f"overall_weeks={len(overall_weekly)}",
        f"industry_blocks={len(industry_blocks)}",
        f"flow_blocks={len(flow_blocks)}",
    ]
    return RenderBundle(html=html_out, log_lines=logs)


def main():
    args = parse_args()
    files = {key: find_latest(args.input_dir, patterns) for key, patterns in FILE_PATTERNS.items()}
    overall_df = prepare_weekly(read_table(files["overall"]))
    industry_df = prepare_weekly(read_table(files["industry"]))
    channel_df = prepare_weekly(read_table(files["channel"]))
    goods_df = prepare_goods(read_table(files["goods"]))
    seller_df = prepare_seller(read_table(files["seller"]))
    resource_df = prepare_resource(read_table(files["resource_entry"]))
    bundle = build_report(
        overall_df, industry_df, channel_df, goods_df, seller_df, resource_df, args.run_id
    )
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(bundle.html)
    print(f"generated_html={args.output}")
    for line in bundle.log_lines:
        print(line)


if __name__ == "__main__":
    main()
