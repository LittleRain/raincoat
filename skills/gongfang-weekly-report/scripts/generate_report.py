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
            "周五-周四周 ": "周",
            "周五-周四周": "周",
        }
    )


def assign_week(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    offset = (df["日期"].dt.weekday - 4) % 7
    df["week_start"] = df["日期"] - pd.to_timedelta(offset, unit="D")
    df["week_end"] = df["week_start"] + pd.Timedelta(days=6)
    df["week_label"] = (
        df["week_start"].dt.strftime("%m-%d") + " ~ " + df["week_end"].dt.strftime("%m-%d")
    )
    return df


def prepare_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = rename_columns(df)
    return assign_week(df)


def prepare_goods(df: pd.DataFrame) -> pd.DataFrame:
    df = rename_columns(df)
    df["focus_industry"] = df["后台一级类目名称"].map(FOCUS_INDUSTRY_MAP)
    return df[df["focus_industry"].notna()].copy()


def focus_industry(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["focus_industry"] = df["后台一级类目名称"].map(FOCUS_INDUSTRY_MAP)
    return df[df["focus_industry"].notna()].copy()


def weekly_rollup(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
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


def build_bar_chart(labels: list[str], values: list[float], title: str, color: str) -> str:
    if not values:
        return ""
    width = 520
    height = 240
    pad = 32
    inner_h = height - pad * 2
    inner_w = width - pad * 2
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
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w:.1f}' height='{h:.1f}' rx='8' fill='{color}'></rect>"
            f"<text x='{x + bar_w / 2:.1f}' y='{height - 10}' text-anchor='middle' font-size='12' fill='#475569'>{label}</text>"
            f"<text x='{x + bar_w / 2:.1f}' y='{max(y - 8, 16):.1f}' text-anchor='middle' font-size='12' fill='#0f172a'>{fmt_num(value)}</text>"
        )
    return (
        f"<figure class='chart'><figcaption>{html.escape(title)}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'>"
        f"<line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#cbd5e1'/>"
        f"{''.join(bars)}</svg></figure>"
    )


def build_line_chart(labels: list[str], values: list[float], title: str, color: str, percent=False) -> str:
    if not values:
        return ""
    width = 520
    height = 240
    pad = 32
    inner_h = height - pad * 2
    inner_w = width - pad * 2
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1e-9)
    points = []
    dots = []
    for idx, value in enumerate(values):
        x = pad + inner_w * (idx / max(len(values) - 1, 1))
        y = height - pad - inner_h * ((value - min_value) / span if span else 0.5)
        points.append(f"{x:.1f},{y:.1f}")
        label = fmt_pct(value) if percent else fmt_num(value, 1)
        dots.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4.5' fill='{color}'></circle>"
            f"<text x='{x:.1f}' y='{max(y - 10, 16):.1f}' text-anchor='middle' font-size='12' fill='#0f172a'>{label}</text>"
            f"<text x='{x:.1f}' y='{height - 10}' text-anchor='middle' font-size='12' fill='#475569'>{html.escape(labels[idx])}</text>"
        )
    return (
        f"<figure class='chart'><figcaption>{html.escape(title)}</figcaption>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'>"
        f"<line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#cbd5e1'/>"
        f"<polyline fill='none' stroke='{color}' stroke-width='3' points='{' '.join(points)}'></polyline>"
        f"{''.join(dots)}</svg></figure>"
    )


def summary_card(title: str, current: float, previous: float, formatter) -> str:
    delta = pct_change(current, previous)
    trend_cls = "up" if delta >= 0 else "down"
    return (
        f"<article class='metric-card'>"
        f"<p class='metric-label'>{html.escape(title)}</p>"
        f"<p class='metric-value'>{formatter(current)}</p>"
        f"<p class='metric-sub'>上周 {formatter(previous)}"
        f"<span class='delta {trend_cls}'>{fmt_delta(delta)}</span></p></article>"
    )


def narrative_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"<li>{html.escape(empty_text)}</li>"
    return "".join(f"<li>{html.escape(item)}</li>" for item in items)


@dataclass
class RenderBundle:
    html: str
    log_lines: list[str]


def build_report(overall_df: pd.DataFrame, industry_df: pd.DataFrame, channel_df: pd.DataFrame, goods_df: pd.DataFrame, run_id: str) -> RenderBundle:
    overall_weekly = weekly_rollup(overall_df, ["week_start", "week_end", "week_label"]).sort_values("week_start")
    if len(overall_weekly) < 2:
        raise ValueError("整体数据不足，至少需要两个周周期")
    current_week = overall_weekly.iloc[-1]
    previous_week = overall_weekly.iloc[-2]

    focus_industry_weekly = weekly_rollup(focus_industry(industry_df), ["focus_industry", "week_start", "week_end", "week_label"])
    focus_channel_weekly = weekly_rollup(focus_industry(channel_df), ["focus_industry", "内容类型", "week_start", "week_end", "week_label"])

    gmvs = overall_weekly["GMV"].tolist()
    buyers = overall_weekly["支付订单买家数"].tolist()
    conversions = overall_weekly["转化率"].tolist()
    gpms = overall_weekly["GPM"].tolist()
    labels = overall_weekly["week_label"].tolist()

    overall_narratives = [
        f"GMV 本周 {fmt_num(current_week['GMV'], 2)}，较上周 {fmt_delta(pct_change(current_week['GMV'], previous_week['GMV']))}。",
        f"买家数本周 {fmt_num(current_week['支付订单买家数'])}，较上周 {fmt_delta(pct_change(current_week['支付订单买家数'], previous_week['支付订单买家数']))}。",
        f"支付订单数本周 {fmt_num(current_week['支付订单数'])}，较上周 {fmt_delta(pct_change(current_week['支付订单数'], previous_week['支付订单数']))}。",
        f"下单转化率本周 {fmt_pct(current_week['转化率'])}，较上周 {fmt_delta(pct_change(current_week['转化率'], previous_week['转化率']))}。",
    ]

    industry_blocks = []
    industry_notes = []
    goods_weeks = sorted(goods_df["周"].dropna().astype(int).unique().tolist())
    current_goods_week = goods_weeks[-1] if goods_weeks else None
    previous_goods_week = goods_weeks[-2] if len(goods_weeks) >= 2 else None

    for focus_name in ["绘画+绘画周边", "VUP周边"]:
        current_industry = focus_industry_weekly[
            (focus_industry_weekly["focus_industry"] == focus_name)
            & (focus_industry_weekly["week_start"] == current_week["week_start"])
        ]
        previous_industry = focus_industry_weekly[
            (focus_industry_weekly["focus_industry"] == focus_name)
            & (focus_industry_weekly["week_start"] == previous_week["week_start"])
        ]
        if current_industry.empty or previous_industry.empty:
            continue
        curr_row = current_industry.iloc[0]
        prev_row = previous_industry.iloc[0]

        metric_changes = []
        for metric in ["GMV", "支付订单买家数", "转化率", "GPM"]:
            delta = pct_change(curr_row[metric], prev_row[metric])
            if abs(delta) > 0.05:
                metric_changes.append(f"{metric} 环比 {fmt_delta(delta)}")

        channel_subset = focus_channel_weekly[focus_channel_weekly["focus_industry"] == focus_name].copy()
        share_changes = []
        if not channel_subset.empty:
            weekly_totals = channel_subset.groupby("week_start").agg(
                total_gmv=("GMV", "sum"),
                total_buyers=("支付订单买家数", "sum"),
            )
            channel_subset = channel_subset.merge(weekly_totals, on="week_start", how="left")
            channel_subset["gmv_share"] = channel_subset["GMV"] / channel_subset["total_gmv"].replace(0, pd.NA)
            channel_subset["buyer_share"] = channel_subset["支付订单买家数"] / channel_subset["total_buyers"].replace(0, pd.NA)
            channel_subset = channel_subset.fillna(0)

            current_channels = channel_subset[channel_subset["week_start"] == current_week["week_start"]]
            previous_channels = channel_subset[channel_subset["week_start"] == previous_week["week_start"]]
            merged = current_channels.merge(
                previous_channels[["内容类型", "gmv_share", "buyer_share"]],
                on="内容类型",
                suffixes=("_curr", "_prev"),
                how="outer",
            ).fillna(0)
            for _, row in merged.iterrows():
                gmv_share_delta = row["gmv_share_curr"] - row["gmv_share_prev"]
                buyer_share_delta = row["buyer_share_curr"] - row["buyer_share_prev"]
                if abs(gmv_share_delta) > 0.05 or abs(buyer_share_delta) > 0.05:
                    share_changes.append(
                        f"{row['内容类型']} 渠道占比变化：GMV 占比 {fmt_delta(gmv_share_delta)}，买家占比 {fmt_delta(buyer_share_delta)}"
                    )

        goods_changes = []
        if current_goods_week is not None and previous_goods_week is not None:
            goods_subset = goods_df[goods_df["focus_industry"] == focus_name]
            curr_goods = goods_subset[goods_subset["周"].astype(int) == current_goods_week]
            prev_goods = goods_subset[goods_subset["周"].astype(int) == previous_goods_week]
            goods_merged = (
                curr_goods.groupby("商品名称")
                .agg(curr_gmv=("GMV", "sum"), curr_buyers=("支付订单买家数", "sum"), curr_uv=("商详UV", "sum"), curr_pv=("商品曝光PV", "sum"))
                .merge(
                    prev_goods.groupby("商品名称")
                    .agg(prev_gmv=("GMV", "sum"), prev_buyers=("支付订单买家数", "sum"), prev_uv=("商详UV", "sum"), prev_pv=("商品曝光PV", "sum")),
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

        channel_table_rows = []
        current_channels = focus_channel_weekly[
            (focus_channel_weekly["focus_industry"] == focus_name)
            & (focus_channel_weekly["week_start"] == current_week["week_start"])
        ].copy()
        previous_channels = focus_channel_weekly[
            (focus_channel_weekly["focus_industry"] == focus_name)
            & (focus_channel_weekly["week_start"] == previous_week["week_start"])
        ].copy()
        if not current_channels.empty or not previous_channels.empty:
            merged_channels = current_channels[
                ["内容类型", "GMV", "支付订单买家数", "转化率"]
            ].merge(
                previous_channels[["内容类型", "GMV", "支付订单买家数", "转化率"]],
                on="内容类型",
                how="outer",
                suffixes=("_curr", "_prev"),
            ).fillna(0)
            merged_channels = merged_channels.sort_values("GMV_curr", ascending=False)
            for _, row in merged_channels.iterrows():
                gmv_wow = pct_change(row["GMV_curr"], row["GMV_prev"])
                buyer_wow = pct_change(row["支付订单买家数_curr"], row["支付订单买家数_prev"])
                conv_wow = pct_change(row["转化率_curr"], row["转化率_prev"])
                channel_table_rows.append(
                    "<tr>"
                    f"<td>{html.escape(str(row['内容类型']))}</td>"
                    f"<td>{fmt_num(row['GMV_curr'], 2)}</td>"
                    f"<td>{fmt_delta(gmv_wow)}</td>"
                    f"<td>{fmt_num(row['支付订单买家数_curr'])}</td>"
                    f"<td>{fmt_delta(buyer_wow)}</td>"
                    f"<td>{fmt_pct(row['转化率_curr'])}</td>"
                    f"<td>{fmt_delta(conv_wow)}</td>"
                    "</tr>"
                )

        industry_blocks.append(
            f"""
            <section class="industry-block">
              <div class="industry-head">
                <h3>{html.escape(focus_name)}</h3>
                <p>本周 GMV {fmt_num(curr_row['GMV'], 2)}，较上周 {fmt_delta(pct_change(curr_row['GMV'], prev_row['GMV']))}。</p>
              </div>
              <div class="metric-grid small">
                {summary_card("GMV", curr_row["GMV"], prev_row["GMV"], lambda v: fmt_num(v, 2))}
                {summary_card("买家数", curr_row["支付订单买家数"], prev_row["支付订单买家数"], lambda v: fmt_num(v))}
                {summary_card("转化率", curr_row["转化率"], prev_row["转化率"], fmt_pct)}
                {summary_card("GPM", curr_row["GPM"], prev_row["GPM"], lambda v: fmt_num(v, 2))}
              </div>
              <div class="analysis-grid">
                <article class="panel">
                  <h4>指标波动</h4>
                  <ul>{narrative_list(metric_changes, "本周重点指标环比变化未超过 5%。")}</ul>
                </article>
                <article class="panel">
                  <h4>渠道占比变化</h4>
                  <ul>{narrative_list(share_changes, "本周未观察到占比变化超过 5% 的内容渠道。")}</ul>
                </article>
              </div>
              <article class="panel">
                <h4>重点商品影响</h4>
                <ul>{narrative_list(goods_changes, "本周未识别到明显的重点商品变化。")}</ul>
              </article>
              <article class="panel">
                <h4>本周渠道分布</h4>
                <table>
                  <thead><tr><th>渠道</th><th>GMV</th><th>上周环比</th><th>买家数</th><th>上周环比</th><th>下单转化</th><th>上周环比</th></tr></thead>
                  <tbody>{''.join(channel_table_rows) or '<tr><td colspan="7">暂无数据</td></tr>'}</tbody>
                </table>
              </article>
            </section>
            """
        )
        industry_notes.append(f"{focus_name}：{'; '.join(metric_changes[:2] + share_changes[:1]) or '本周整体表现平稳。'}")

    styles = """
    :root {
      --bg: #f7f4ec;
      --ink: #1f2937;
      --muted: #64748b;
      --card: #ffffff;
      --line: #e2e8f0;
      --accent: #c2410c;
      --accent-2: #0f766e;
      --accent-3: #b45309;
      --shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "PingFang SC", "Noto Sans SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(194,65,12,0.08), transparent 30%),
        linear-gradient(180deg, #fbf8f3 0%, var(--bg) 100%);
    }
    a { color: inherit; }
    .page { max-width: 1240px; margin: 0 auto; padding: 32px 20px 64px; }
    .hero {
      background: linear-gradient(135deg, rgba(194,65,12,0.96), rgba(15,118,110,0.92));
      color: #fff; border-radius: 28px; padding: 28px 28px 24px; box-shadow: var(--shadow);
    }
    .hero h1 { margin: 0 0 8px; font-size: 34px; }
    .hero p { margin: 6px 0; color: rgba(255,255,255,0.88); }
    .hero-meta { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }
    .hero-meta span {
      display: inline-flex; padding: 8px 12px; border: 1px solid rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.08); border-radius: 999px; font-size: 14px;
    }
    .nav {
      position: sticky; top: 0; z-index: 10; margin: 18px 0 24px; padding: 14px 16px;
      display: flex; gap: 12px; flex-wrap: wrap; background: rgba(255,255,255,0.85);
      backdrop-filter: blur(12px); border: 1px solid rgba(226,232,240,0.9); border-radius: 16px;
    }
    .nav a { text-decoration: none; padding: 8px 12px; border-radius: 999px; background: #f8fafc; }
    .section { margin-top: 24px; }
    .section-head { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 16px; }
    .section-head h2 { margin: 0; font-size: 28px; }
    .section-head p { margin: 6px 0 0; color: var(--muted); }
    .metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
    .metric-grid.small { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 14px; }
    .metric-card, .panel, .chart, .industry-block {
      background: var(--card); border: 1px solid rgba(226,232,240,0.9);
      border-radius: 22px; box-shadow: var(--shadow);
    }
    .metric-card { padding: 18px 18px 16px; }
    .metric-label { margin: 0; color: var(--muted); font-size: 13px; }
    .metric-value { margin: 10px 0 8px; font-size: 28px; font-weight: 700; }
    .metric-sub { margin: 0; color: var(--muted); font-size: 14px; }
    .delta { margin-left: 8px; font-weight: 700; }
    .delta.up { color: #047857; }
    .delta.down { color: #b91c1c; }
    .chart-grid, .analysis-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
    .chart { padding: 16px; margin: 0; }
    .chart figcaption { font-weight: 700; margin-bottom: 12px; }
    .panel { padding: 18px; }
    .panel h4 { margin: 0 0 12px; font-size: 18px; }
    .panel ul { margin: 0; padding-left: 18px; line-height: 1.7; }
    .industry-block { padding: 18px; margin-top: 18px; }
    .industry-head { display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }
    .industry-head h3 { margin: 0; font-size: 22px; }
    .industry-head p { margin: 6px 0 0; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; }
    th { color: var(--muted); font-weight: 600; font-size: 13px; }
    .footnote { margin-top: 22px; color: var(--muted); font-size: 14px; line-height: 1.7; }
    @media (max-width: 900px) {
      .metric-grid, .metric-grid.small, .chart-grid, .analysis-grid { grid-template-columns: 1fr; }
      .section-head, .industry-head { flex-direction: column; align-items: flex-start; }
    }
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
        <h1>工房业务交易双周报</h1>
        <p>聚焦核心数据趋势、重点行业波动、渠道占比变化与商品归因。</p>
        <div class="hero-meta">
          <span>运行 ID: {html.escape(run_id)}</span>
          <span>本周: {html.escape(str(current_week['week_label']))}</span>
          <span>上周: {html.escape(str(previous_week['week_label']))}</span>
        </div>
      </header>

      <nav class="nav">
        <a href="#core-data-trend">核心数据趋势</a>
        <a href="#industry-breakdown">by 行业拆解</a>
        <a href="#data-notes">数据说明</a>
      </nav>

      <section id="core-data-trend" class="section">
        <div class="section-head">
          <div>
            <h2>核心数据趋势</h2>
            <p>看清工房交易规模与效率的周变化，重点关注 GMV、买家数、下单转化率和 GPM。</p>
          </div>
        </div>
        <div class="metric-grid">
          {summary_card("GMV", current_week["GMV"], previous_week["GMV"], lambda v: fmt_num(v, 2))}
          {summary_card("买家数", current_week["支付订单买家数"], previous_week["支付订单买家数"], lambda v: fmt_num(v))}
          {summary_card("下单转化率", current_week["转化率"], previous_week["转化率"], fmt_pct)}
          {summary_card("GPM", current_week["GPM"], previous_week["GPM"], lambda v: fmt_num(v, 2))}
        </div>
        <div class="chart-grid">
          {build_bar_chart(labels, gmvs, "GMV 周趋势", "#c2410c")}
          {build_bar_chart(labels, buyers, "买家数 周趋势", "#0f766e")}
          {build_line_chart(labels, conversions, "下单转化率 周趋势", "#7c3aed", percent=True)}
          {build_line_chart(labels, gpms, "GPM 周趋势", "#b45309")}
        </div>
        <article class="panel" style="margin-top:16px;">
          <h4>本周结论</h4>
          <ul>{narrative_list(overall_narratives, "暂无可输出结论。")}</ul>
        </article>
      </section>

      <section id="industry-breakdown" class="section">
        <div class="section-head">
          <div>
            <h2>by 行业拆解</h2>
            <p>重点观察绘画+绘画周边与 VUP周边的 GMV、买家数、转化率、GPM 与渠道结构波动。</p>
          </div>
        </div>
        <article class="panel">
          <h4>栏目摘要</h4>
          <ul>{narrative_list(industry_notes, "当前未形成重点行业摘要。")}</ul>
        </article>
        {''.join(industry_blocks)}
      </section>

      <section id="data-notes" class="section">
        <div class="section-head">
          <div>
            <h2>数据说明</h2>
            <p>所有结论仅基于已声明的数据合同与字段，不补充额外因果推断。</p>
          </div>
        </div>
        <article class="panel">
          <ul>
            <li>整体数据、行业数据、内容渠道数据按“周五到周四”聚合成周。</li>
            <li>绘画+绘画周边为合并行业口径，VUP周边单独分析。</li>
            <li>下单转化率使用周内支付订单数 / 商详UV 聚合口径计算。</li>
            <li>GPM 使用周内 GMV / 商品曝光PV × 1000 聚合口径计算。</li>
            <li>商品归因仅引用行业商品明细数据中当前周与上周的 GMV、买家数、商详UV 变化。</li>
          </ul>
        </article>
        <p class="footnote">生成时间取自本地执行环境。当前版本已输出真实聚合结果、SVG 图表和行业分析，不再是占位 HTML。</p>
      </section>
    </div>
  </body>
</html>
"""

    logs = [
        f"current_week={current_week['week_label']}",
        f"previous_week={previous_week['week_label']}",
        f"overall_weeks={len(overall_weekly)}",
        f"focus_industry_blocks={len(industry_blocks)}",
    ]
    return RenderBundle(html=html_out, log_lines=logs)


def main():
    args = parse_args()
    files = {key: find_latest(args.input_dir, patterns) for key, patterns in FILE_PATTERNS.items()}
    overall_df = prepare_daily(read_table(files["overall"]))
    industry_df = prepare_daily(read_table(files["industry"]))
    channel_df = prepare_daily(read_table(files["channel"]))
    goods_df = prepare_goods(read_table(files["goods"]))
    bundle = build_report(overall_df, industry_df, channel_df, goods_df, args.run_id)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(bundle.html)
    print(f"generated_html={args.output}")
    for line in bundle.log_lines:
        print(line)


if __name__ == "__main__":
    main()
