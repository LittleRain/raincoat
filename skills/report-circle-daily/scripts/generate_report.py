#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
圈子业务日报生成器
==================
用法:
    python generate_report.py --dir data/ --output report.html

输入文件（放同一目录）:
    ① *拉取绘画圈feed流明细数据*         → 绘画圈内容分析
    ② *拉取模型圈feed流明细数据*         → 模型圈内容分析
    ③ *拉取漫展圈feed流明细数据*         → 漫展圈 T3 路径内容分析
    ④ *拉取漫展项目的转化行为数据*       → 漫展项目转化分析
    ⑤ *拉取漫展圈feed流明细数据_票务商详* → 漫展圈票务商详路径内容分析

输出: report.html
"""

import argparse
import glob
import os
import time
from datetime import date, datetime, timedelta

import pandas as pd


# ────────────────────────────────────────────────
# 通用工具
# ────────────────────────────────────────────────

def read_file(path):
    if not path:
        return pd.DataFrame()
    if path.endswith('.csv'):
        return pd.read_csv(path)
    return pd.read_excel(path)


def fmt_num(n):
    if pd.isna(n):
        return '-'
    try:
        n = float(n)
        if abs(n) >= 10000:
            return f'{n/10000:.1f}万'
        return f'{n:,.0f}'
    except Exception:
        return str(n)


def fmt_pct(n):
    if pd.isna(n):
        return '-'
    try:
        return f'{float(n) * 100:.1f}%'
    except Exception:
        return str(n)


def safe_div(a, b):
    try:
        a = float(a)
        b = float(b)
        if b == 0:
            return pd.NA
        return a / b
    except Exception:
        return pd.NA


def to_num(series):
    return pd.to_numeric(series, errors='coerce')


def pick_col(columns, exact=None, any_contains=None, all_contains=None):
    exact = exact or []
    any_contains = any_contains or []
    all_contains = all_contains or []

    for c in columns:
        if c in exact:
            return c

    for c in columns:
        low = c.lower()
        if any_contains and any(k.lower() in low for k in any_contains):
            return c

    for c in columns:
        low = c.lower()
        if all_contains and all(k.lower() in low for k in all_contains):
            return c

    return None


def parse_datetime_col(series):
    dt = pd.to_datetime(series, errors='coerce')
    return dt


def build_opus_link(content_id):
    if pd.isna(content_id):
        return '-'
    text = str(content_id).strip()
    if not text:
        return '-'
    return f'https://www.bilibili.com/opus/{text}'


def html_table(df):
    if df.empty:
        return '<p class="no-data">无数据</p>'

    headers = ''.join(f'<th>{c}</th>' for c in df.columns)
    rows = ''
    for _, row in df.iterrows():
        cells = ''.join(f'<td>{v}</td>' for v in row)
        rows += f'<tr>{cells}</tr>'

    return f'<table class="sortable"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>'


def section(section_id, title, body):
    return f'''
<section id="{section_id}">
  <h2>{title}</h2>
  {body}
</section>
'''


# ────────────────────────────────────────────────
# 数据加载
# ────────────────────────────────────────────────

def load_all(directory):
    print('📂 加载数据...\n')

    def _find(pattern, exclude=None):
        for ext in ['.csv', '.xlsx', '.xls']:
            matches = glob.glob(os.path.join(directory, f'*{pattern}*{ext}'))
            if exclude:
                matches = [m for m in matches if exclude not in os.path.basename(m)]
            if matches:
                return sorted(matches, key=os.path.getmtime, reverse=True)[0]
        return None

    files = {
        '绘画圈feed': _find('拉取绘画圈feed流明细数据'),
        '模型圈feed': _find('拉取模型圈feed流明细数据'),
        '漫展圈T3': _find('拉取漫展圈feed流明细数据', exclude='票务商详'),
        '漫展转化': _find('拉取漫展项目的转化行为数据'),
        '漫展票务feed': _find('拉取漫展圈feed流明细数据_票务商详'),
    }

    dfs = {}
    for k, v in files.items():
        status = f'✓ {os.path.basename(v)}' if v else '⚠ 未找到'
        print(f'  {k:12s}: {status}')
        dfs[k] = read_file(v)

    return dfs


# ────────────────────────────────────────────────
# feed 标准化与分析
# ────────────────────────────────────────────────

def standardize_feed(df, mode='pv'):
    """
    mode = pv | uv
    输出统一字段：
    content_id, title, subtitle, pubtime, item_name, source, content_type,
    exposure, click, ctr, interact, content_link
    """
    if df.empty:
        return pd.DataFrame()

    data = df.copy()
    data.columns = [c.strip() for c in data.columns]
    cols = list(data.columns)

    title_col = pick_col(cols, exact=['title', 'Title', '标题'])
    subtitle_col = pick_col(cols, exact=['subtitle', '副标题', 'content_text'])
    pub_col = pick_col(cols, exact=['pubtime', '发布时间', 'log_date', 'start_time'])
    item_col = pick_col(cols, exact=['item_name', '展会项目名称'])
    source_col = pick_col(cols, exact=['发布来源', 'source'])
    type_col = pick_col(cols, exact=['内容类型', 'content_type', 'filter_text', '分区名称'])
    content_id_col = pick_col(cols, exact=['content_id'])

    if mode == 'uv':
        exposure_col = pick_col(cols, exact=['uv_expose'], all_contains=['曝光', 'uv'])
        click_col = pick_col(cols, exact=['uv_click'], all_contains=['点击', 'uv'])
        ctr_col = pick_col(cols, exact=['uv_ctr'], all_contains=['ctr', 'uv'])
        interact_col = None
    else:
        exposure_col = pick_col(cols, exact=['曝光pv'], all_contains=['曝光', 'pv'])
        click_col = pick_col(cols, exact=['点击pv'], all_contains=['点击', 'pv'])
        ctr_col = pick_col(cols, exact=['pv_ctr'], all_contains=['ctr', 'pv'])
        interact_col = pick_col(cols, exact=['pv互动数'], any_contains=['互动'])

    if not exposure_col or not click_col:
        return pd.DataFrame()

    out = pd.DataFrame()
    out['content_id'] = data[content_id_col] if content_id_col else pd.NA
    out['title'] = data[title_col].astype(str) if title_col else '-'
    out['subtitle'] = data[subtitle_col].fillna('-').astype(str) if subtitle_col else '-'
    out['pubtime_raw'] = data[pub_col] if pub_col else pd.NA
    out['item_name'] = data[item_col].fillna('-').astype(str) if item_col else '-'
    out['source'] = data[source_col].fillna('-').astype(str) if source_col else '-'
    out['content_type'] = data[type_col].fillna('-').astype(str) if type_col else '-'

    out['exposure'] = to_num(data[exposure_col]).fillna(0)
    out['click'] = to_num(data[click_col]).fillna(0)

    if ctr_col:
        ctr_num = to_num(data[ctr_col])
        calc_ctr = out.apply(lambda r: safe_div(r['click'], r['exposure']), axis=1)
        out['ctr'] = ctr_num.fillna(calc_ctr)
    else:
        out['ctr'] = out.apply(lambda r: safe_div(r['click'], r['exposure']), axis=1)

    if interact_col:
        out['interact'] = to_num(data[interact_col]).fillna(0)
    else:
        out['interact'] = pd.NA

    dt = parse_datetime_col(out['pubtime_raw'])
    out['pubtime'] = dt.dt.strftime('%Y-%m-%d %H:%M').fillna(out['pubtime_raw'].astype(str).replace('NaT', '-'))
    out['content_link'] = out['content_id'].apply(build_opus_link)

    return out


def aggregate_feed_metrics(feed_df):
    if feed_df.empty:
        return {'exposure': 0, 'click': 0, 'ctr': pd.NA, 'interact_rate': pd.NA, 'content_count': 0}

    exposure = feed_df['exposure'].sum()
    click = feed_df['click'].sum()
    ctr = safe_div(click, exposure)
    content_count = len(feed_df)

    if 'interact' in feed_df.columns and feed_df['interact'].notna().any():
        interact = to_num(feed_df['interact']).fillna(0).sum()
        interact_rate = safe_div(interact, click)
    else:
        interact_rate = pd.NA

    return {
        'exposure': exposure,
        'click': click,
        'ctr': ctr,
        'interact_rate': interact_rate,
        'content_count': content_count,
    }


def build_feed_top_table(feed_df, exposure_label='曝光PV', click_label='点击PV', ctr_label='PV CTR', include_interact=True):
    if feed_df.empty:
        return '<p class="warn">⚠ 数据文件未找到或缺少关键列</p>'

    top = feed_df.sort_values('exposure', ascending=False).head(10).copy()

    show = pd.DataFrame()
    show['标题'] = top['title'].fillna('-')
    show['副标题'] = top['subtitle'].fillna('-')
    show['发布时间'] = top['pubtime'].fillna('-')
    show[exposure_label] = top['exposure'].apply(fmt_num)
    show[click_label] = top['click'].apply(fmt_num)
    show[ctr_label] = top['ctr'].apply(fmt_pct)

    if include_interact and top['interact'].notna().any():
        show['互动数'] = to_num(top['interact']).fillna(0).apply(fmt_num)

    show['链接'] = top['content_link']
    return html_table(show)


def feed_feature_insights(feed_df, scene_label):
    if feed_df.empty:
        return ['缺少可分析数据。']

    m = aggregate_feed_metrics(feed_df)
    insights = [
        f'{scene_label}整体曝光 {fmt_num(m["exposure"])}、点击 {fmt_num(m["click"])}、加权 CTR {fmt_pct(m["ctr"])}。',
    ]

    if pd.notna(m['interact_rate']):
        insights.append(f'互动率（互动数/点击）为 {fmt_pct(m["interact_rate"])}，说明点击后参与度处于可观察水平。')

    type_grp = (
        feed_df.groupby('content_type', dropna=False)
        .agg(exposure=('exposure', 'sum'), click=('click', 'sum'))
        .reset_index()
    )
    if not type_grp.empty:
        type_grp['ctr'] = type_grp.apply(lambda r: safe_div(r['click'], r['exposure']), axis=1)
        top_exp_type = type_grp.sort_values('exposure', ascending=False).iloc[0]
        top_ctr_type = type_grp[type_grp['exposure'] > 0].sort_values('ctr', ascending=False).iloc[0]
        exp_share = safe_div(top_exp_type['exposure'], m['exposure'])
        insights.append(
            f'内容类型上，「{top_exp_type["content_type"]}」曝光占比最高（{fmt_pct(exp_share)}），'
            f'而「{top_ctr_type["content_type"]}」CTR 更高（{fmt_pct(top_ctr_type["ctr"])}）。'
        )

    source_grp = (
        feed_df.groupby('source', dropna=False)
        .agg(exposure=('exposure', 'sum'), click=('click', 'sum'))
        .reset_index()
    )
    if not source_grp.empty:
        source_grp['ctr'] = source_grp.apply(lambda r: safe_div(r['click'], r['exposure']), axis=1)
        best_src = source_grp[source_grp['exposure'] > 0].sort_values('ctr', ascending=False).iloc[0]
        insights.append(f'发布来源上，「{best_src["source"]}」CTR 领先（{fmt_pct(best_src["ctr"])}），可作为后续内容供给策略的优先来源。')

    baseline_ctr = m['ctr'] if pd.notna(m['ctr']) else 0
    high_eff = feed_df[(feed_df['ctr'] >= baseline_ctr) & (feed_df['exposure'] >= feed_df['exposure'].median())]
    if not high_eff.empty:
        top_titles = (
            high_eff.sort_values('ctr', ascending=False)
            .head(3)['title']
            .dropna()
            .astype(str)
            .str.strip()
            .tolist()
        )
        top_titles = [t for t in top_titles if t and t.lower() != 'nan']
        if top_titles:
            insights.append('高效率内容（CTR 高于整体且曝光不低）主要集中在：' + '、'.join(top_titles) + '。')
        else:
            insights.append('高效率内容（CTR 高于整体且曝光不低）存在，但标题字段缺失较多。')

    return insights


def analyze_circle_feed(raw_df, circle_name):
    feed = standardize_feed(raw_df, mode='pv')
    if feed.empty:
        return f'<p class="warn">⚠ {circle_name} 数据文件未找到或缺少关键列（曝光/点击）</p>'

    metrics = aggregate_feed_metrics(feed)
    stat_html = f'''
<div class="stats-bar">
  <span>内容数：<strong>{metrics['content_count']}</strong></span>
  <span>总曝光PV：<strong>{fmt_num(metrics['exposure'])}</strong></span>
  <span>总点击PV：<strong>{fmt_num(metrics['click'])}</strong></span>
  <span>加权CTR：<strong>{fmt_pct(metrics['ctr'])}</strong></span>
  <span>互动率：<strong>{fmt_pct(metrics['interact_rate']) if pd.notna(metrics['interact_rate']) else '-'}</strong></span>
</div>
'''

    table_html = '<h3>Top10 内容（按曝光 PV 降序）</h3>' + build_feed_top_table(feed)

    insights = feed_feature_insights(feed, f'{circle_name}（主动访问场景）')
    insight_html = '<div class="insight"><h3>结论（含数据依据）</h3><ul>' + ''.join(f'<li>{x}</li>' for x in insights) + '</ul></div>'

    return stat_html + table_html + insight_html


# ────────────────────────────────────────────────
# 总览
# ────────────────────────────────────────────────

def build_overview(dfs):
    huihua = standardize_feed(dfs['绘画圈feed'], mode='pv')
    moxing = standardize_feed(dfs['模型圈feed'], mode='pv')
    manzhan_t3 = standardize_feed(dfs['漫展圈T3'], mode='pv')
    manzhan_ticket = standardize_feed(dfs['漫展票务feed'], mode='uv')

    rows = []

    def add_row(name, scene, feed, exposure_label='PV', click_label='PV'):
        m = aggregate_feed_metrics(feed)
        rows.append({
            '圈子/路径': name,
            '用户场景': scene,
            f'曝光{exposure_label}': fmt_num(m['exposure']),
            f'点击{click_label}': fmt_num(m['click']),
            'CTR': fmt_pct(m['ctr']),
            '互动率': fmt_pct(m['interact_rate']) if pd.notna(m['interact_rate']) else '-',
            '_ctr_num': m['ctr'],
            '_name': name,
            '_scene': scene,
        })

    add_row('绘画圈', 'T3 主动访问', huihua)
    add_row('模型圈', 'T3 主动访问', moxing)
    add_row('漫展圈（T3）', 'T3 主动访问', manzhan_t3)
    add_row('漫展圈（票务商详）', '票务商详进入讨论区', manzhan_ticket, exposure_label='UV', click_label='UV')

    table_df = pd.DataFrame(rows)
    show_df = table_df[['圈子/路径', '用户场景', '曝光PV', '点击PV', 'CTR', '互动率']].copy()

    # UV 路径的数据列回填到 PV 列位置，便于一个总览表展示
    if '曝光PV' in show_df.columns:
        show_df['曝光PV'] = show_df['曝光PV'].replace('-', pd.NA)
    if '点击PV' in show_df.columns:
        show_df['点击PV'] = show_df['点击PV'].replace('-', pd.NA)

    uv_mask = table_df['圈子/路径'] == '漫展圈（票务商详）'
    show_df.loc[uv_mask, '曝光PV'] = table_df.loc[uv_mask, '曝光UV'].values
    show_df.loc[uv_mask, '点击PV'] = table_df.loc[uv_mask, '点击UV'].values

    show_df = show_df.rename(columns={'曝光PV': '曝光（PV/UV）', '点击PV': '点击（PV/UV）'})

    insights = []
    valid_ctr = table_df.dropna(subset=['_ctr_num'])
    if not valid_ctr.empty:
        best = valid_ctr.sort_values('_ctr_num', ascending=False).iloc[0]
        worst = valid_ctr.sort_values('_ctr_num', ascending=True).iloc[0]
        insights.append(f'整体 CTR 最高的是「{best["_name"]}」({fmt_pct(best["_ctr_num"])}，场景：{best["_scene"]})。')
        insights.append(f'整体 CTR 最低的是「{worst["_name"]}」({fmt_pct(worst["_ctr_num"])})，需要优先优化内容匹配或入口承接。')

    t3 = aggregate_feed_metrics(manzhan_t3)
    ticket = aggregate_feed_metrics(manzhan_ticket)
    if pd.notna(t3['ctr']) and pd.notna(ticket['ctr']):
        delta = ticket['ctr'] - t3['ctr']
        direction = '高于' if delta >= 0 else '低于'
        insights.append(
            f'漫展圈票务商详路径 CTR {fmt_pct(ticket["ctr"])}，{direction} T3 路径 {fmt_pct(t3["ctr"])} '
            f'（差值 {fmt_pct(abs(delta))}），说明不同场景下用户意图强度存在显著差异。'
        )

    active = pd.DataFrame([
        {'name': '绘画圈', 'ir': aggregate_feed_metrics(huihua)['interact_rate']},
        {'name': '模型圈', 'ir': aggregate_feed_metrics(moxing)['interact_rate']},
        {'name': '漫展圈（T3）', 'ir': aggregate_feed_metrics(manzhan_t3)['interact_rate']},
    ]).dropna(subset=['ir'])
    if not active.empty:
        best_ir = active.sort_values('ir', ascending=False).iloc[0]
        insights.append(f'主动访问场景下，互动率最高的是「{best_ir["name"]}」({fmt_pct(best_ir["ir"])})，可优先复用其内容结构。')

    return (
        '<h3>圈子整体表现总览</h3>'
        + html_table(show_df)
        + '<div class="insight"><h3>总览结论</h3><ul>'
        + ''.join(f'<li>{x}</li>' for x in insights)
        + '</ul></div>'
    )


# ────────────────────────────────────────────────
# 漫展圈双路径内容分析
# ────────────────────────────────────────────────

def analyze_manzhan_content(df_t3_raw, df_ticket_raw):
    t3 = standardize_feed(df_t3_raw, mode='pv')
    ticket = standardize_feed(df_ticket_raw, mode='uv')

    body = ''
    if t3.empty:
        body += '<p class="warn">⚠ 漫展圈 T3 路径数据未找到或缺列</p>'
    else:
        m = aggregate_feed_metrics(t3)
        body += (
            '<h3>T3 路径 Top10（按曝光 PV 降序）</h3>'
            + f'<p class="note">曝光 {fmt_num(m["exposure"])}，点击 {fmt_num(m["click"])}，加权 CTR {fmt_pct(m["ctr"])}。</p>'
            + build_feed_top_table(t3, exposure_label='曝光PV', click_label='点击PV', ctr_label='PV CTR', include_interact=True)
        )

    if ticket.empty:
        body += '<p class="warn">⚠ 漫展圈票务商详路径数据未找到或缺列</p>'
    else:
        m = aggregate_feed_metrics(ticket)
        body += (
            '<h3>票务商详路径 Top10（按曝光 UV 降序）</h3>'
            + f'<p class="note">曝光 {fmt_num(m["exposure"])}，点击 {fmt_num(m["click"])}，加权 CTR {fmt_pct(m["ctr"])}。</p>'
            + build_feed_top_table(ticket, exposure_label='曝光UV', click_label='点击UV', ctr_label='UV CTR', include_interact=False)
        )

    insights = []
    if not t3.empty and not ticket.empty:
        t3_ctr = aggregate_feed_metrics(t3)['ctr']
        tk_ctr = aggregate_feed_metrics(ticket)['ctr']
        if pd.notna(t3_ctr) and pd.notna(tk_ctr):
            delta = tk_ctr - t3_ctr
            word = '更高' if delta >= 0 else '更低'
            insights.append(f'票务商详路径 CTR（{fmt_pct(tk_ctr)}）相对 T3（{fmt_pct(t3_ctr)}）{word}，体现用户意图更明确。')

        t3_top_type = t3['content_type'].fillna('-').value_counts()
        tk_top_type = ticket['content_type'].fillna('-').value_counts()
        if not t3_top_type.empty:
            insights.append(f'T3 路径主导内容类型为「{t3_top_type.index[0]}」({t3_top_type.iloc[0]} 条)。')
        if not tk_top_type.empty:
            insights.append(f'票务商详路径主导分区/类型为「{tk_top_type.index[0]}」({tk_top_type.iloc[0]} 条)。')

        t3_top = t3.sort_values('exposure', ascending=False).head(10)
        tk_top = ticket.sort_values('exposure', ascending=False).head(10)
        t3_focus = safe_div(t3_top.head(3)['exposure'].sum(), t3_top['exposure'].sum())
        tk_focus = safe_div(tk_top.head(3)['exposure'].sum(), tk_top['exposure'].sum())
        insights.append(f'Top10 内 Top3 曝光集中度：T3 {fmt_pct(t3_focus)}，票务商详 {fmt_pct(tk_focus)}。')

        overlap = set(t3_top['item_name'].dropna()) & set(tk_top['item_name'].dropna())
        if overlap:
            insights.append('两条路径共同高关注项目：' + '、'.join(list(overlap)[:5]) + '。')
        else:
            insights.append('两条路径高关注项目重叠较少，建议按场景拆分内容运营策略。')
    else:
        insights.append('双路径数据不完整，暂无法输出稳定差异结论。')

    body += '<div class="insight"><h3>路径差异结论</h3><ul>' + ''.join(f'<li>{x}</li>' for x in insights) + '</ul></div>'
    return body


# ────────────────────────────────────────────────
# 漫展项目转化分析
# ────────────────────────────────────────────────

def _reason_by_funnel(row, expo_mean, click_mean):
    expo_r = row.get('expo_rate', pd.NA)
    click_r = row.get('click_rate', pd.NA)
    if pd.isna(expo_r) or pd.isna(click_r):
        return '关键漏斗字段不足，需补充后判断。'

    if expo_r >= expo_mean and click_r >= click_mean:
        return '曝光承接和点击承接都高于均值，链路完整。'
    if expo_r < expo_mean and click_r >= click_mean:
        return '讨论区曝光承接偏弱，但内容点击承接较好，建议优先补入口曝光。'
    if expo_r >= expo_mean and click_r < click_mean:
        return '曝光承接正常，但讨论区内容点击承接偏弱，建议优化内容标题/分区匹配。'
    return '曝光和点击承接都偏弱，建议同步优化入口素材与讨论区内容供给。'


def analyze_manzhan_conversion(raw_df, report_day):
    if raw_df.empty:
        return '<p class="warn">⚠ 漫展项目转化数据未找到或为空</p>'

    df = raw_df.copy()
    df.columns = [c.strip() for c in df.columns]
    cols = list(df.columns)

    item_col = pick_col(cols, exact=['item_name', '展会项目名称'])
    start_col = pick_col(cols, exact=['start_time', '开始时间'])
    want_col = pick_col(cols, exact=['想去数'])
    browse_col = pick_col(cols, exact=['商详浏览uv'], all_contains=['商详', '浏览', 'uv'])
    expo_col = pick_col(cols, exact=['讨论区曝光uv'], all_contains=['讨论区', '曝光', 'uv'])
    click_col = pick_col(cols, exact=['讨论区点击uv'], all_contains=['讨论区', '点击', 'uv'])
    ctr_col = pick_col(cols, exact=['uv_ctr'], all_contains=['ctr', 'uv'])

    if not browse_col or not expo_col or not click_col:
        return f'<p class="warn">⚠ 转化表缺少关键列，现有列：{list(df.columns)}</p>'

    for c in [browse_col, expo_col, click_col, want_col, ctr_col]:
        if c:
            df[c] = to_num(df[c]).fillna(0)

    df['expo_rate'] = df.apply(lambda r: safe_div(r[expo_col], r[browse_col]), axis=1)
    df['click_rate'] = df.apply(lambda r: safe_div(r[click_col], r[expo_col]), axis=1)
    if ctr_col:
        df['uv_ctr_num'] = df[ctr_col]
    else:
        df['uv_ctr_num'] = df.apply(lambda r: safe_div(r[click_col], r[browse_col]), axis=1)

    top = df.sort_values(browse_col, ascending=False).head(10).copy()

    show = pd.DataFrame()
    show['展会项目'] = top[item_col].fillna('-') if item_col else '-'
    show['展会开始时间'] = top[start_col].fillna('-') if start_col else '-'
    show['想去数'] = top[want_col].apply(fmt_num) if want_col else '-'
    show['商详浏览UV'] = top[browse_col].apply(fmt_num)
    show['讨论区曝光UV'] = top[expo_col].apply(fmt_num)
    show['讨论区点击UV'] = top[click_col].apply(fmt_num)
    show['曝光承接率'] = top['expo_rate'].apply(fmt_pct)
    show['点击承接率'] = top['click_rate'].apply(fmt_pct)
    show['UV CTR'] = top['uv_ctr_num'].apply(fmt_pct)

    insights = []
    valid = top.dropna(subset=['uv_ctr_num'])
    if not valid.empty and item_col:
        best = valid.sort_values('uv_ctr_num', ascending=False).iloc[0]
        worst = valid.sort_values('uv_ctr_num', ascending=True).iloc[0]

        expo_mean = valid['expo_rate'].mean()
        click_mean = valid['click_rate'].mean()

        insights.append(
            f'转化最佳项目「{best[item_col]}」UV CTR {fmt_pct(best["uv_ctr_num"])}，'
            f'{_reason_by_funnel(best, expo_mean, click_mean)}'
        )
        if best[item_col] != worst[item_col]:
            insights.append(
                f'转化偏弱项目「{worst[item_col]}」UV CTR {fmt_pct(worst["uv_ctr_num"])}，'
                f'{_reason_by_funnel(worst, expo_mean, click_mean)}'
            )

    if start_col:
        start_dt = pd.to_datetime(top[start_col], errors='coerce')
        if start_dt.notna().any():
            days = (start_dt - pd.Timestamp(report_day)).dt.days
            near_mask = days <= 30
            far_mask = days > 30
            near_ctr = top.loc[near_mask, 'uv_ctr_num'].mean()
            far_ctr = top.loc[far_mask, 'uv_ctr_num'].mean()
            if pd.notna(near_ctr) and pd.notna(far_ctr):
                insights.append(
                    f'开场时间<=30天项目平均 UV CTR 为 {fmt_pct(near_ctr)}，'
                    f'>30天项目为 {fmt_pct(far_ctr)}，可用于判断“临近档期”对转化的影响。'
                )

    if want_col:
        top['want_per_browse'] = top.apply(lambda r: safe_div(r[want_col], r[browse_col]), axis=1)
        top_want = top.sort_values('want_per_browse', ascending=False).head(1)
        if not top_want.empty and item_col:
            r = top_want.iloc[0]
            insights.append(
                f'项目「{r[item_col]}」想去/商详浏览比值最高（{fmt_pct(r["want_per_browse"])}），'
                '说明用户兴趣热度与转化潜力相对更强。'
            )

    if not insights:
        insights.append('字段可用性不足，暂无法给出稳定的多角度转化结论。')

    note = f'<p class="note">注：按商详浏览 UV 排序展示前 10 个项目（样本总数 {len(df)}）。</p>'
    return note + html_table(show) + '<div class="insight"><h3>项目转化结论</h3><ul>' + ''.join(f'<li>{x}</li>' for x in insights) + '</ul></div>'


# ────────────────────────────────────────────────
# HTML 模板
# ────────────────────────────────────────────────

CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 14px;
  color: #1a1a1a;
  background: #f5f7fa;
}
.container { max-width: 1240px; margin: 0 auto; padding: 24px; }
header {
  background: #fff;
  border-radius: 10px;
  padding: 24px 28px;
  margin-bottom: 18px;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
}
header h1 { font-size: 22px; color: #00aeec; margin-bottom: 6px; }
header .meta { color: #666; font-size: 13px; }
section {
  background: #fff;
  border-radius: 10px;
  padding: 22px 24px;
  margin-bottom: 18px;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
}
section h2 {
  font-size: 18px;
  color: #222;
  border-left: 4px solid #00aeec;
  padding-left: 10px;
  margin-bottom: 14px;
}
section h3 { font-size: 14px; color: #444; margin: 14px 0 8px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  background: #f0f8ff;
  color: #333;
  padding: 8px 10px;
  text-align: left;
  border-bottom: 2px solid #cce5ff;
  white-space: nowrap;
  cursor: pointer;
}
td { padding: 7px 10px; border-bottom: 1px solid #eee; vertical-align: top; }
tr:hover td { background: #fafcff; }
td:last-child { word-break: break-all; }
.stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  background: #f0f8ff;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
}
.stats-bar strong { color: #00aeec; font-size: 15px; }
.insight {
  background: #fffbe6;
  border-left: 3px solid #ffd666;
  border-radius: 4px;
  padding: 12px 16px;
  margin-top: 12px;
}
.insight h3 { color: #7d5900; font-size: 13px; margin-bottom: 6px; }
.insight ul { padding-left: 16px; }
.insight li { color: #554500; margin-bottom: 4px; line-height: 1.6; }
.warn {
  color: #cc4444;
  background: #fff5f5;
  padding: 8px 12px;
  border-radius: 4px;
  border-left: 3px solid #ff9999;
}
.note { color: #777; font-size: 12px; margin-bottom: 8px; }
.no-data { color: #aaa; font-style: italic; }
footer { color: #999; font-size: 12px; text-align: center; margin-top: 24px; }
'''

JS = '''
(function () {
  const tables = document.querySelectorAll('table.sortable');
  tables.forEach((table) => {
    const headers = table.querySelectorAll('th');
    headers.forEach((th, idx) => {
      let asc = false;
      th.addEventListener('click', () => {
        const rows = Array.from(table.querySelectorAll('tbody tr'));
        rows.sort((a, b) => {
          const av = a.children[idx]?.innerText?.trim() || '';
          const bv = b.children[idx]?.innerText?.trim() || '';

          const an = parseFloat(av.replace(/,/g, '').replace('%', '').replace('万', '0000'));
          const bn = parseFloat(bv.replace(/,/g, '').replace('%', '').replace('万', '0000'));

          if (!Number.isNaN(an) && !Number.isNaN(bn)) {
            return asc ? an - bn : bn - an;
          }
          return asc ? av.localeCompare(bv) : bv.localeCompare(av);
        });

        const tbody = table.querySelector('tbody');
        rows.forEach(r => tbody.appendChild(r));
        asc = !asc;
      });
    });
  });
})();
'''


def build_html(sections_html, report_date):
    body = '\n'.join(sections_html)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>圈子业务日报 {report_date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
<header>
  <h1>圈子业务日报</h1>
  <div class="meta">数据日期：昨日（{report_date}）&nbsp;|&nbsp;生成时间：{time.strftime("%Y-%m-%d %H:%M")}</div>
</header>
{body}
<section id="source-notes">
  <h2>数据说明</h2>
  <ul style="padding-left:16px;line-height:2">
    <li>绘画圈、模型圈、漫展圈 T3 使用 PV 口径；票务商详路径使用 UV 口径。</li>
    <li>内容 Top10 默认按曝光量排序，可点击表头进行交互排序。</li>
    <li>内容链接按规则拼接：`https://www.bilibili.com/opus/ + content_id`。</li>
    <li>结论仅基于输入数据中的可用字段，不做无证据归因。</li>
  </ul>
</section>
<footer>report-circle-daily v0.2.0 · 由 create-report skill 生成</footer>
</div>
<script>{JS}</script>
</body>
</html>'''


# ────────────────────────────────────────────────
# 主程序
# ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='圈子业务日报生成器')
    parser.add_argument('--dir', default='.', help='数据目录')
    parser.add_argument('--output', default='report.html', help='输出 HTML 路径')
    args = parser.parse_args()

    print('=' * 52)
    print('  圈子业务日报生成器 v0.2.0')
    print('=' * 52)

    report_day = date.today() - timedelta(days=1)
    report_date = report_day.strftime('%Y-%m-%d')
    print(f'\n📅 报告日期：昨日（{report_date}）\n')

    dfs = load_all(args.dir)

    print('\n📊 生成报告...')

    sections = []

    print('  → S1 圈子总览')
    sections.append(section(
        'overview', '① 总览：圈子整体表现',
        build_overview(dfs)
    ))

    print('  → S2 绘画圈内容分析')
    sections.append(section(
        'huihua-content', '② 绘画圈：内容分析',
        analyze_circle_feed(dfs['绘画圈feed'], '绘画圈')
    ))

    print('  → S3 模型圈内容分析')
    sections.append(section(
        'moxing-content', '③ 模型圈：内容分析',
        analyze_circle_feed(dfs['模型圈feed'], '模型圈')
    ))

    print('  → S4 漫展圈双路径内容分析')
    sections.append(section(
        'manzhan-content', '④ 漫展圈：T3 vs 票务商详 内容分析',
        analyze_manzhan_content(dfs['漫展圈T3'], dfs['漫展票务feed'])
    ))

    print('  → S5 漫展项目转化分析')
    sections.append(section(
        'manzhan-conversion', '⑤ 漫展圈：项目转化分析',
        analyze_manzhan_conversion(dfs['漫展转化'], report_day)
    ))

    html = build_html(sections, report_date)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(args.output) / 1024
    print(f'\n✅ 报告已生成: {args.output}')
    print(f'   文件大小: {size_kb:.1f} KB')


if __name__ == '__main__':
    main()
