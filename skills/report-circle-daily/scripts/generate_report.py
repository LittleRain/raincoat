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
import html
import os
import re
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
        return ''
    text = str(content_id).strip()
    if not text or text == '0' or text.lower() == 'nan':
        return ''
    return f'https://www.bilibili.com/opus/{text}'


def html_table(df):
    if df.empty:
        return '<p class="no-data">无数据</p>'

    headers = ''.join(f'<th>{c}</th>' for c in df.columns)
    rows = ''
    for _, row in df.iterrows():
        cell_html = []
        for v in row:
            text = '' if pd.isna(v) else str(v)
            if text.startswith('http://') or text.startswith('https://'):
                safe = html.escape(text, quote=True)
                cell_html.append(f'<td><a href="{safe}" target="_blank" rel="noopener noreferrer">打开</a></td>')
            else:
                cell_html.append(f'<td>{text}</td>')
        cells = ''.join(cell_html)
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
        interact_rate = safe_div(interact, exposure)
    else:
        interact_rate = pd.NA

    return {
        'exposure': exposure,
        'click': click,
        'ctr': ctr,
        'interact': interact if 'interact' in locals() else 0,
        'interact_rate': interact_rate,
        'content_count': content_count,
    }


def build_feed_top_table(feed_df, exposure_label='曝光PV', click_label='点击PV', ctr_label='PV CTR', include_interact=True):
    if feed_df.empty:
        return '<p class="warn">⚠ 数据文件未找到或缺少关键列</p>'

    top = feed_df.sort_values('exposure', ascending=False).head(10).copy()

    show = pd.DataFrame()
    show['标题'] = top['title'].fillna('-')
    show['描述'] = top['subtitle'].fillna('-')
    show['发布时间'] = top['pubtime'].fillna('-')
    show[exposure_label] = top['exposure'].apply(fmt_num)
    show[click_label] = top['click'].apply(fmt_num)
    show[ctr_label] = top['ctr'].apply(fmt_pct)

    if include_interact and top['interact'].notna().any():
        show['互动数'] = to_num(top['interact']).fillna(0).apply(fmt_num)

    show['链接'] = top['content_link']
    return html_table(show)


def infer_scene_label(title, subtitle):
    text = f'{title} {subtitle}'.lower()
    rules = [
        ('报名招募', r'报名|自由行|申请中|申请'),
        ('返图晒图', r'返图|场照|cos|repo'),
        ('攻略信息', r'攻略|时间|地点|交通|票务|嘉宾|流程'),
        ('社交组队', r'找搭子|有没有|求|一起'),
        ('情绪表达', r'好好玩|值得|坑|无语|惊现'),
    ]
    for label, pattern in rules:
        if re.search(pattern, text):
            return label
    return ''


def top_keywords(feed_slice):
    words = {}
    for _, row in feed_slice.iterrows():
        text = f"{row.get('title', '')} {row.get('subtitle', '')}"
        for token in re.findall(r'[A-Za-z0-9\u4e00-\u9fff]{2,8}', text):
            token_low = token.lower()
            if token_low in {'nan', 'br', 'http', 'https', 'www'}:
                continue
            if token in {'这个', '我们', '大家', '一起', '就是', '可以', '没有', '内容', '分享图片'}:
                continue
            words[token] = words.get(token, 0) + 1
    if not words:
        return '无明显高频词'
    return '、'.join([k for k, _ in sorted(words.items(), key=lambda x: x[1], reverse=True)[:4]])


def build_text_summary(texts):
    if not texts:
        return ''
    tokens = {}
    for text in texts:
        for token in re.findall(r'[A-Za-z0-9\u4e00-\u9fff]{2,8}', str(text)):
            token_low = token.lower()
            if token_low in {'nan', 'br', 'http', 'https', 'www'}:
                continue
            if token in {'这个', '我们', '大家', '一起', '就是', '可以', '没有', '内容', '分享图片'}:
                continue
            tokens[token] = tokens.get(token, 0) + 1
    if not tokens:
        return ''
    return '、'.join([k for k, _ in sorted(tokens.items(), key=lambda x: x[1], reverse=True)[:4]])


def feed_feature_insights(feed_df):
    if feed_df.empty:
        return ['缺少可分析数据。']

    insights = []

    type_grp = (
        feed_df.groupby('content_type', dropna=False)
        .agg(exposure=('exposure', 'sum'), click=('click', 'sum'))
        .reset_index()
    )
    if not type_grp.empty:
        type_grp['ctr'] = type_grp.apply(lambda r: safe_div(r['click'], r['exposure']), axis=1)
        top_exp_type = type_grp.sort_values('exposure', ascending=False).iloc[0]
        top_ctr_type = type_grp[type_grp['exposure'] > 0].sort_values('ctr', ascending=False).iloc[0]
        insights.append(
            f'内容类型上，「{top_exp_type["content_type"]}」是头部曝光主力，'
            f'「{top_ctr_type["content_type"]}」点击效率更高（CTR {fmt_pct(top_ctr_type["ctr"])}）。'
        )

    source_grp = (
        feed_df.groupby('source', dropna=False)
        .agg(exposure=('exposure', 'sum'), click=('click', 'sum'))
        .reset_index()
    )
    if not source_grp.empty:
        source_grp['ctr'] = source_grp.apply(lambda r: safe_div(r['click'], r['exposure']), axis=1)
        best_src = source_grp[source_grp['exposure'] > 0].sort_values('ctr', ascending=False).iloc[0]
        insights.append(f'发布来源上，「{best_src["source"]}」点击效率更高（CTR {fmt_pct(best_src["ctr"])}）。')

    top10 = feed_df.sort_values('exposure', ascending=False).head(10).copy()
    top10['scene'] = top10.apply(lambda r: infer_scene_label(r.get('title', ''), r.get('subtitle', '')), axis=1)
    high = top10.sort_values(['ctr', 'click'], ascending=False).head(3)
    low = top10.sort_values(['ctr', 'click'], ascending=[True, True]).head(3)
    high_scene = high[high['scene'] != '']['scene'].mode()
    low_scene = low[low['scene'] != '']['scene'].mode()
    high_scene_label = high_scene.iloc[0] if not high_scene.empty else ''
    low_scene_label = low_scene.iloc[0] if not low_scene.empty else ''
    if high_scene_label:
        insights.append(f'Top10 高表现内容更偏「{high_scene_label}」场景，常见关键词：{top_keywords(high)}。')
    else:
        insights.append(f'Top10 高表现内容暂未形成稳定场景分类，常见关键词：{top_keywords(high)}。')
    if low_scene_label:
        insights.append(f'Top10 低表现内容更偏「{low_scene_label}」场景，常见关键词：{top_keywords(low)}。')
    else:
        insights.append(f'Top10 低表现内容暂未形成稳定场景分类，常见关键词：{top_keywords(low)}。')
    if high_scene_label and low_scene_label and high_scene_label != low_scene_label:
        insights.append(f'同样在头部曝光池里，「{high_scene_label}」类内容更容易获得点击，「{low_scene_label}」类内容相对偏弱。')

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

    insights = feed_feature_insights(feed)
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
            'PV CTR': fmt_pct(m['ctr']),
            'PV互动数': fmt_num(m['interact']),
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

    for column in ['曝光PV', '点击PV', '曝光UV', '点击UV', 'PV CTR', 'PV互动数', '互动率']:
        if column not in table_df.columns:
            table_df[column] = '-'

    show_df = table_df[['圈子/路径', '用户场景', '曝光PV', '点击PV', 'PV CTR', 'PV互动数', '互动率']].copy()
    ticket_mask = table_df['圈子/路径'] == '漫展圈（票务商详）'
    show_df.loc[ticket_mask, '曝光PV'] = table_df.loc[ticket_mask, '曝光UV'].values
    show_df.loc[ticket_mask, '点击PV'] = table_df.loc[ticket_mask, '点击UV'].values
    show_df.loc[ticket_mask, 'PV互动数'] = '-'
    show_df.loc[ticket_mask, '互动率'] = '-'

    insights = []
    valid_ctr = table_df.dropna(subset=['_ctr_num'])
    if not valid_ctr.empty:
        best = valid_ctr.sort_values('_ctr_num', ascending=False).iloc[0]
        worst = valid_ctr.sort_values('_ctr_num', ascending=True).iloc[0]
        insights.append(f'整体 CTR 最高的是「{best["_name"]}」({fmt_pct(best["_ctr_num"])}，场景：{best["_scene"]})。')
        insights.append(f'整体 CTR 最低的是「{worst["_name"]}」({fmt_pct(worst["_ctr_num"])})，需要优先优化内容匹配或入口承接。')

    active = pd.DataFrame([
        {'name': '绘画圈', 'ir': aggregate_feed_metrics(huihua)['interact_rate']},
        {'name': '模型圈', 'ir': aggregate_feed_metrics(moxing)['interact_rate']},
        {'name': '漫展圈（T3）', 'ir': aggregate_feed_metrics(manzhan_t3)['interact_rate']},
    ]).dropna(subset=['ir'])
    if not active.empty:
        best_ir = active.sort_values('ir', ascending=False).iloc[0]
        insights.append(f'主动访问场景下，互动率最高的是「{best_ir["name"]}」({fmt_pct(best_ir["ir"])}）。')

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
        body += (
            '<h3>T3 路径 Top10（按曝光 PV 降序）</h3>'
            + build_feed_top_table(t3, exposure_label='曝光PV', click_label='点击PV', ctr_label='PV CTR', include_interact=True)
        )

    if ticket.empty:
        body += '<p class="warn">⚠ 漫展圈票务商详路径数据未找到或缺列</p>'
    else:
        body += (
            '<h3>票务商详路径 Top10（按曝光 UV 降序）</h3>'
            + build_feed_top_table(ticket, exposure_label='曝光UV', click_label='点击UV', ctr_label='UV CTR', include_interact=False)
        )

    insights = []
    if not t3.empty and not ticket.empty:
        t3_top = t3.sort_values('exposure', ascending=False).head(10)
        tk_top = ticket.sort_values('exposure', ascending=False).head(10)
        t3_top = t3_top.copy()
        tk_top = tk_top.copy()
        t3_top['scene'] = t3_top.apply(lambda r: infer_scene_label(r.get('title', ''), r.get('subtitle', '')), axis=1)
        tk_top['scene'] = tk_top.apply(lambda r: infer_scene_label(r.get('title', ''), r.get('subtitle', '')), axis=1)
        t3_high = t3_top.sort_values(['ctr', 'click'], ascending=False).head(3)
        t3_low = t3_top.sort_values(['ctr', 'click'], ascending=[True, True]).head(3)
        tk_high = tk_top.sort_values(['ctr', 'click'], ascending=False).head(3)
        tk_low = tk_top.sort_values(['ctr', 'click'], ascending=[True, True]).head(3)

        t3_high_scene = t3_high[t3_high['scene'] != '']['scene'].mode()
        t3_low_scene = t3_low[t3_low['scene'] != '']['scene'].mode()
        tk_high_scene = tk_high[tk_high['scene'] != '']['scene'].mode()
        tk_low_scene = tk_low[tk_low['scene'] != '']['scene'].mode()
        if not t3_high_scene.empty or not t3_low_scene.empty:
            insights.append(
                f'T3 头部内容中，表现更好的项目/文本特征偏「{t3_high_scene.iloc[0] if not t3_high_scene.empty else "未形成稳定分类"}」，'
                f'表现偏弱的更常见「{t3_low_scene.iloc[0] if not t3_low_scene.empty else "未形成稳定分类"}」。'
            )
        else:
            insights.append('T3 头部内容暂未形成稳定场景分类，建议继续按具体标题与项目语义观察。')
        if not tk_high_scene.empty or not tk_low_scene.empty:
            insights.append(
                f'票务商详头部内容中，表现更好的项目/文本特征偏「{tk_high_scene.iloc[0] if not tk_high_scene.empty else "未形成稳定分类"}」，'
                f'表现偏弱的更常见「{tk_low_scene.iloc[0] if not tk_low_scene.empty else "未形成稳定分类"}」。'
            )
        else:
            insights.append('票务商详头部内容暂未形成稳定场景分类，建议继续按具体标题与项目语义观察。')
        insights.append(
            f'两渠道文本语境差异明显：T3 高频词偏「{top_keywords(t3_top)}」，票务商详偏「{top_keywords(tk_top)}」，'
            '说明前者更泛兴趣，后者更项目导向。'
        )
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


def build_ticket_project_context(ticket_raw):
    ticket = standardize_feed(ticket_raw, mode='uv')
    if ticket.empty:
        return {}
    working = ticket.copy()
    working['item_name'] = working['item_name'].fillna('-').astype(str).str.strip()
    working = working[(working['item_name'] != '') & (working['item_name'] != '-')]
    if working.empty:
        return {}
    grouped = (
        working.groupby('item_name', dropna=False)
        .agg(expose=('exposure', 'sum'), click=('click', 'sum'))
        .reset_index()
    )
    context = {}
    for _, row in grouped.iterrows():
        item_name = row['item_name']
        item_rows = working[working['item_name'] == item_name].copy()
        item_rows = item_rows.sort_values(['click', 'exposure'], ascending=False).head(5)
        sample_texts = []
        for _, item_row in item_rows.iterrows():
            title = str(item_row.get('title', '')).strip()
            subtitle = str(item_row.get('subtitle', '')).strip()
            sample_texts.append(title if title and title != '-' else subtitle)
        context[row['item_name']] = {
            'expose': float(row['expose']),
            'click': float(row['click']),
            'ctr': safe_div(row['click'], row['expose']),
            'content_count': int(len(working[working['item_name'] == item_name])),
            'keywords': build_text_summary(sample_texts),
            'sample_texts': sample_texts,
        }
    return context


def get_ticket_meta(ticket_context, item_name):
    key = str(item_name).strip()
    if not key:
        return {}
    return ticket_context.get(key, {})


def build_conversion_project_insight(row, ticket_meta, expo_mean, click_mean, item_name, mode):
    base_reason = _reason_by_funnel(row, expo_mean, click_mean)
    if ticket_meta:
        ticket_ctr = ticket_meta.get('ctr', pd.NA)
        content_count = ticket_meta.get('content_count', 0)
        keywords = ticket_meta.get('keywords', '')
        if mode == 'best':
            tail = (
                f' 票务商详侧可匹配到 {content_count} 条同项目内容，CTR {fmt_pct(ticket_ctr)}'
                + (f'，高频文案集中在「{keywords}」' if keywords else '')
                + '，说明商详阶段的内容主题与后续讨论区点击方向基本一致。'
            )
        else:
            tail = (
                f' 票务商详侧可匹配到 {content_count} 条同项目内容，CTR {fmt_pct(ticket_ctr)}'
                + (f'，文案主要是「{keywords}」' if keywords else '')
            )
            if pd.notna(ticket_ctr) and ticket_ctr <= 0.05:
                tail += '，商详阶段内容吸引力本身就偏弱。'
            else:
                tail += '，商详阶段不算弱，问题更像出在讨论区承接内容。'
        return f'{"转化最佳项目" if mode == "best" else "转化偏弱项目"}「{item_name}」UV CTR {fmt_pct(row["uv_ctr_num"])}，{base_reason}{tail}'
    if mode == 'best':
        return f'转化最佳项目「{item_name}」UV CTR {fmt_pct(row["uv_ctr_num"])}，{base_reason} 但票务商详表里没有匹配到足够的同项目内容，暂时只能确认讨论区端承接较强。'
    return f'转化偏弱项目「{item_name}」UV CTR {fmt_pct(row["uv_ctr_num"])}，{base_reason} 票务商详表里没有匹配到同项目内容，当前更像项目侧缺少有效内容供给。'


def analyze_manzhan_conversion(raw_df, ticket_raw, report_day):
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
    # uv_ctr 统一按 讨论区点击UV / 讨论区曝光UV 计算，避免源表口径异常（如全 0）。
    df['uv_ctr_num'] = df.apply(lambda r: safe_div(r[click_col], r[expo_col]), axis=1)

    ticket_context = build_ticket_project_context(ticket_raw)

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
    # 票务商详CTR口径：讨论区点击UV / 商详浏览UV
    show['票务商详CTR'] = top.apply(lambda r: fmt_pct(safe_div(r[click_col], r[browse_col])), axis=1)

    insights = []
    valid = top.dropna(subset=['uv_ctr_num'])
    if not valid.empty and item_col:
        best = valid.sort_values('uv_ctr_num', ascending=False).iloc[0]
        worst = valid.sort_values('uv_ctr_num', ascending=True).iloc[0]

        expo_mean = valid['expo_rate'].mean()
        click_mean = valid['click_rate'].mean()

        insights.append(
            build_conversion_project_insight(
                best,
                get_ticket_meta(ticket_context, best[item_col]),
                expo_mean,
                click_mean,
                best[item_col],
                'best',
            )
        )
        if best[item_col] != worst[item_col]:
            insights.append(
                build_conversion_project_insight(
                    worst,
                    get_ticket_meta(ticket_context, worst[item_col]),
                    expo_mean,
                    click_mean,
                    worst[item_col],
                    'weak',
                )
            )

        zero_expose_projects = top[top[expo_col] <= 0]
        if not zero_expose_projects.empty:
            sample = zero_expose_projects.iloc[0]
            sample_ticket = get_ticket_meta(ticket_context, sample[item_col]) if item_col else {}
            if sample_ticket:
                insights.append(
                    f'像「{sample[item_col]}」这类讨论区曝光为 0 的项目，在票务商详侧仍有 {sample_ticket.get("content_count", 0)} 条关联内容、CTR {fmt_pct(sample_ticket.get("ctr", pd.NA))}，说明用户在商详页有一定浏览，但内容没有顺利承接到讨论区。'
                )
            else:
                insights.append(
                    f'像「{sample[item_col]}」这类讨论区曝光为 0 的项目，票务商详表里也几乎没有匹配到同项目内容，问题更偏向项目内容供给缺失，而不只是转化链路损耗。'
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
        analyze_manzhan_conversion(dfs['漫展转化'], dfs['漫展票务feed'], report_day)
    ))

    html = build_html(sections, report_date)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(args.output) / 1024
    print(f'\n✅ 报告已生成: {args.output}')
    print(f'   文件大小: {size_kb:.1f} KB')


if __name__ == '__main__':
    main()
