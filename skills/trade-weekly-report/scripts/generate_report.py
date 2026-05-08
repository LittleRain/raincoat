#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易业务周报 - 完整生成脚本
严格按照需求文档中的图表和表格数量输出
支持 --data-dir 和 --output 参数
"""

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

import argparse
parser = argparse.ArgumentParser(description='生成交易业务周报')
parser.add_argument('--data-dir', type=str, default=None,
                    help='数据文件所在目录（含整体/行业/流量/商家标签/商品明细/内容类型.xlsx）')
parser.add_argument('--output', type=str, default=None,
                    help='输出 HTML 路径（默认与 data-dir 同目录）')
args = parser.parse_args(sys.argv[1:] if __name__ == '__main__' else [])

DEFAULT_DATA_DIR = Path('/Users/raincai/Downloads/4.17')
DATA_DIR = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
OUTPUT_PATH = Path(args.output) if args.output else (DATA_DIR / 'trade-weekly-report.html')
SKILL_DIR = Path('/Users/raincai/.workbuddy/skills/trade-weekly-report/assets')

# ── 结论生成 ──────────────────────────────────────────────────────────────────

def generate_conclusions(df1, df2, df3, df4, df5, s1_mtd, s2_shop_table, s2_ziying_table,
                        s3_top20_rows, s3_top20_prod_rows, s4_shop_channels, s4_ziying_channels,
                        s4_tianma_data, s4_feed_data, s5_overall_rows, s5_shop_rows, s5_ziying_rows):
    """生成各板块的结论解读"""
    
    conclusions = {}
    
    # ── S1 结论 ──────────────────────────────────────────────────────────────
    biz_metrics = {}
    for biz in ['小店', '自营', '工坊', '票务']:
        cur = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['GMV'].sum())
        prev = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['GMV'].sum()) if PREV_W else 0
        wow = wow_pct(cur, prev)
        biz_metrics[biz] = {'cur': cur, 'prev': prev, 'wow': wow}
    
    # GMV 结论
    gmv_texts = []
    for biz, m in biz_metrics.items():
        if m['cur'] > 0:
            direction = "↑" if m['wow']['value'] > 0 else "↓" if m['wow']['value'] < 0 else "持平"
            gmv_texts.append(f"{biz} {fmt_gmv(m['cur'])}({direction}{abs(m['wow']['value']):.1f}%)")
    conclusions['s1_gmv'] = "；".join(gmv_texts) if gmv_texts else "数据暂无"
    
    # 订单数结论
    order_texts = []
    for biz in ['小店', '自营']:
        cur = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['订单数'].sum())
        prev = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['订单数'].sum()) if PREV_W else 0
        wow = wow_pct(cur, prev)
        direction = "↑" if wow['value'] > 0 else "↓" if wow['value'] < 0 else "持平"
        order_texts.append(f"{biz} {fmt_num(cur)}单({direction}{abs(wow['value']):.1f}%)")
    conclusions['s1_order'] = "；".join(order_texts) if order_texts else "数据暂无"
    
    # 买家数结论
    buyer_texts = []
    for biz in ['小店', '自营']:
        cur = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['买家数'].sum())
        prev = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['买家数'].sum()) if PREV_W else 0
        wow = wow_pct(cur, prev)
        direction = "↑" if wow['value'] > 0 else "↓" if wow['value'] < 0 else "持平"
        buyer_texts.append(f"{biz} {fmt_num(cur)}人({direction}{abs(wow['value']):.1f}%)")
    conclusions['s1_buyer'] = "；".join(buyer_texts) if buyer_texts else "数据暂无"
    
    # CTR 结论
    ctr_texts = []
    for biz in ['小店', '自营']:
        cur_pv = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['商品曝光PV'].sum())
        cur_cvr = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['商详PV'].sum())
        cur_ctr = cur_cvr/cur_pv*100 if cur_pv > 0 else 0
        prev_pv = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['商品曝光PV'].sum()) if PREV_W else 0
        prev_cvr = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['商详PV'].sum()) if PREV_W else 0
        prev_ctr = prev_cvr/prev_pv*100 if prev_pv > 0 else 0
        wow = wow_pct(cur_ctr, prev_ctr)
        direction = "↑" if wow['value'] > 0 else "↓" if wow['value'] < 0 else "→"
        ctr_texts.append(f"{biz} {cur_ctr:.2f}%({direction}{abs(wow['value']):.2f}pp)")
    conclusions['s1_ctr'] = "；".join(ctr_texts) if ctr_texts else "数据暂无"
    
    # CVR 结论
    cvr_texts = []
    for biz in ['小店', '自营']:
        cur_ord = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['订单数'].sum())
        cur_pv = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['商品曝光PV'].sum())
        cur_cvr = cur_ord/cur_pv*100 if cur_pv > 0 else 0
        prev_ord = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['订单数'].sum()) if PREV_W else 0
        prev_pv = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['商品曝光PV'].sum()) if PREV_W else 0
        prev_cvr = prev_ord/prev_pv*100 if prev_pv > 0 else 0
        wow = wow_pct(cur_cvr, prev_cvr)
        direction = "↑" if wow['value'] > 0 else "↓" if wow['value'] < 0 else "→"
        cvr_texts.append(f"{biz} {cur_cvr:.3f}%({direction}{abs(wow['value']):.3f}pp)")
    conclusions['s1_cvr'] = "；".join(cvr_texts) if cvr_texts else "数据暂无"
    
    # GPM 结论
    gpm_texts = []
    for biz in ['小店', '自营']:
        cur_gmv = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['GMV'].sum())
        cur_pv = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']==biz)]['商品曝光PV'].sum())
        cur_gpm = cur_gmv/cur_pv*1000 if cur_pv > 0 else 0
        prev_gmv = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['GMV'].sum()) if PREV_W else 0
        prev_pv = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']==biz)]['商品曝光PV'].sum()) if PREV_W else 0
        prev_gpm = prev_gmv/prev_pv*1000 if prev_pv > 0 else 0
        wow = wow_pct(cur_gpm, prev_gpm)
        direction = "↑" if wow['value'] > 0 else "↓" if wow['value'] < 0 else "→"
        gpm_texts.append(f"{biz} {cur_gpm:.1f}({direction}{abs(wow['value']):.1f}%)")
    conclusions['s1_gpm'] = "；".join(gpm_texts) if gpm_texts else "数据暂无"
    
    # ── S2 结论 ──────────────────────────────────────────────────────────────
    # 小店行业波动分析（>5%）
    shop_flucs = []
    for row in s2_shop_table:
        if row.get('GMV_wow', {}).get('value', 0) > 5 or row.get('GMV_wow', {}).get('value', 0) < -5:
            name = row.get('name', '未知')
            wow_val = row['GMV_wow']['value']
            direction = "↑" if wow_val > 0 else "↓"
            shop_flucs.append(f"{name}({direction}{abs(wow_val):.1f}%)")
    conclusions['s2_shop'] = "小店 GMV 波动超5%的行业：" + "、".join(shop_flucs) if shop_flucs else "小店各行业 GMV 波动相对平稳（<5%）"
    
    # 自营行业波动分析（>5%）
    ziying_flucs = []
    for row in s2_ziying_table:
        if row.get('GMV_wow', {}).get('value', 0) > 5 or row.get('GMV_wow', {}).get('value', 0) < -5:
            name = row.get('name', '未知')
            wow_val = row['GMV_wow']['value']
            direction = "↑" if wow_val > 0 else "↓"
            ziying_flucs.append(f"{name}({direction}{abs(wow_val):.1f}%)")
    conclusions['s2_ziying'] = "自营 GMV 波动超5%的行业：" + "、".join(ziying_flucs) if ziying_flucs else "自营各行业 GMV 波动相对平稳（<5%）"
    
    # ── S3 结论 ──────────────────────────────────────────────────────────────
    # 重点商家分析
    big_shops = []
    for row in s3_top20_rows[:5]:
        wow_val = row.get('GMV_wow', {}).get('value', 0)
        if abs(wow_val) > 5:
            direction = "↑" if wow_val > 0 else "↓"
            big_shops.append(f"{row.get('name', '未知')[:10]}({direction}{abs(wow_val):.1f}%)")
    conclusions['s3_merchant'] = "Top5商家中 GMV 波动较大：" + "、".join(big_shops) if big_shops else "Top20商家整体 GMV 波动相对平稳"
    
    # 重点商品分析
    big_prods = []
    for row in s3_top20_prod_rows[:5]:
        wow_val = row.get('GMV_wow', {}).get('value', 0)
        if abs(wow_val) > 5:
            direction = "↑" if wow_val > 0 else "↓"
            big_prods.append(f"{row.get('name', row.get('商品名称', '未知'))[:10]}({direction}{abs(wow_val):.1f}%)")
    conclusions['s3_product'] = "Top5商品中 GMV 波动较大：" + "、".join(big_prods) if big_prods else "Top20商品整体 GMV 波动相对平稳"
    
    # ── S4 结论 ──────────────────────────────────────────────────────────────
    # 总流量波动
    cur_total_pv = safe_float(df1[df1['周五-周四周']==CUR_W]['商品曝光PV'].sum())
    prev_total_pv = safe_float(df1[df1['周五-周四周']==PREV_W]['商品曝光PV'].sum()) if PREV_W else 0
    traffic_wow = wow_pct(cur_total_pv, prev_total_pv)
    direction = "↑" if traffic_wow['value'] > 0 else "↓" if traffic_wow['value'] < 0 else "→"
    conclusions['s4_traffic'] = f"总曝光 PV {fmt_num(cur_total_pv)}，较上周{direction}{abs(traffic_wow['value']):.1f}%"
    
    # 小店流量分析
    cur_shop_pv = safe_float(df1[(df1['周五-周四周']==CUR_W)&(df1['业务线二级']=='小店')]['商品曝光PV'].sum())
    prev_shop_pv = safe_float(df1[(df1['周五-周四周']==PREV_W)&(df1['业务线二级']=='小店')]['商品曝光PV'].sum()) if PREV_W else 0
    shop_pv_wow = wow_pct(cur_shop_pv, prev_shop_pv)
    shop_ratio = cur_shop_pv/cur_total_pv*100 if cur_total_pv > 0 else 0
    direction = "↑" if shop_pv_wow['value'] > 0 else "↓" if shop_pv_wow['value'] < 0 else "→"
    conclusions['s4_shop_traffic'] = f"小店曝光 {fmt_num(cur_shop_pv)}，占比{shop_ratio:.1f}%，较上周{direction}{abs(shop_pv_wow['value']):.1f}%"
    
    # 重点渠道归因
    volatile_channels = []
    for row in (s4_shop_channels or [])[:5]:
        wow_val = row.get('PV_wow', {}).get('value', 0)
        if abs(wow_val) > 10:
            direction = "↑" if wow_val > 0 else "↓"
            volatile_channels.append(f"{row.get('name', row.get('渠道', '未知'))}({direction}{abs(wow_val):.1f}%)")
    conclusions['s4_channel'] = "小店波动较大的渠道：" + "、".join(volatile_channels) if volatile_channels else "小店各渠道流量波动相对平稳"
    
    # ── S5 结论 ──────────────────────────────────────────────────────────────
    # 整体成交结构
    if s5_overall_rows:
        top_type = max(s5_overall_rows, key=lambda x: x['share'])
        conclusions['s5_overall'] = f"整体以「{top_type['type']}」为主，占比{top_type['share']:.1f}%"
    else:
        conclusions['s5_overall'] = "数据暂无"
    
    # 小店成交结构
    if s5_shop_rows:
        top_shop_type = max(s5_shop_rows, key=lambda x: x['share'])
        conclusions['s5_shop'] = f"小店以「{top_shop_type['type']}」为主，占比{top_shop_type['share']:.1f}%"
    else:
        conclusions['s5_shop'] = "数据暂无"
    
    # 自营成交结构
    if s5_ziying_rows:
        top_ziying_type = max(s5_ziying_rows, key=lambda x: x['share'])
        conclusions['s5_ziying'] = f"自营以「{top_ziying_type['type']}」为主，占比{top_ziying_type['share']:.1f}%"
    else:
        conclusions['s5_ziying'] = "数据暂无"
    
    return conclusions

# ── 数据加载 ──────────────────────────────────────────────────────────────────

def load_all():
    print("[INFO] 加载数据文件...")
    
    def clean(df):
        df.columns = df.columns.str.strip().str.strip("'\"")
        r = {'GMV（不减退款）': 'GMV', '支付订单买家数': '买家数', '支付订单数': '订单数',
             '商详支付转化率-UV': 'CVR', 'PVCTR': 'CTR', '商详UV': '商详PV'}
        for old, new in r.items():
            if old in df.columns: df = df.rename(columns={old: new})
        return df
    
    df1 = clean(pd.read_excel(DATA_DIR / '整体.xlsx', engine='openpyxl'))
    df2 = clean(pd.read_excel(DATA_DIR / '行业.xlsx', engine='openpyxl'))
    # 行业.xlsx 没有 GPM 字段，需要计算
    if 'GPM' not in df2.columns:
        df2['GPM'] = df2.apply(lambda r: r['GMV'] / r['商品曝光PV'] * 1000 if r['商品曝光PV'] > 0 else 0, axis=1)
    # 兼容文件名：商品明细.xlsx 或 商品.xlsx
    _product_file = DATA_DIR / '商品明细.xlsx' if (DATA_DIR / '商品明细.xlsx').exists() else DATA_DIR / '商品.xlsx'
    df3 = clean(pd.read_excel(_product_file, engine='openpyxl'))
    df4 = clean(pd.read_excel(DATA_DIR / '流量.xlsx', engine='openpyxl'))
    # 流量文件需要特殊处理列名空格
    if '周五-周四周 ' in df4.columns:
        df4 = df4.rename(columns={'周五-周四周 ': '周五-周四周'})
    df5 = clean(pd.read_excel(DATA_DIR / '内容类型.xlsx', engine='openpyxl'))
    # 内容类型文件需要特殊处理列名空格
    if '周五-周四周 ' in df5.columns:
        df5 = df5.rename(columns={'周五-周四周 ': '周五-周四周'})
    df6 = pd.read_excel(DATA_DIR / '商家标签.xlsx', sheet_name='sheet', engine='openpyxl')
    
    print(f"  整体: {len(df1)} 行, 周: {sorted(df1['周五-周四周'].dropna().unique())}")
    print(f"  行业: {len(df2)} 行")
    print(f"  商品明细: {len(df3)} 行")
    print(f"  流量: {len(df4)} 行")
    print(f"  内容类型: {len(df5)} 行")
    print(f"  商家标签: {len(df6)} 行")
    
    return df1, df2, df3, df4, df5, df6


# ── 行业分类 ──────────────────────────────────────────────────────────────────

def classify_shop_industry(df, df6):
    """给小店数据打行业/分类标签，通过 merchant_id 关联商家标签"""
    # 兼容新旧字段名
    if 'merchant_id' in df6.columns:
        tags = df6[['merchant_id', 'owner_ld', 'owner_cate']].drop_duplicates('merchant_id')
        result = df.merge(tags, left_on='商家ID', right_on='merchant_id', how='left')
        def get_ind(row):
            ld = row.get('owner_ld')
            if pd.isna(ld) or ld not in ['南征', 'allen', '孙悟饭', '加林']:
                return '小店其他'
            return str(ld)
        def get_cate(row):
            cate = row.get('owner_cate')
            if pd.isna(cate): return '其他'
            return str(cate)
    else:
        # 新版字段：商家id, 行业, 行业负责人
        tags = df6[['商家id', '行业', '行业负责人']].drop_duplicates('商家id')
        result = df.merge(tags, left_on='商家ID', right_on='商家id', how='left')
        def get_ind(row):
            ld = row.get('行业负责人')
            if pd.isna(ld) or ld not in ['南征', 'allen', '孙悟饭', '加林']:
                return '小店其他'
            return str(ld)
        def get_cate(row):
            cate = row.get('行业')
            if pd.isna(cate): return '其他'
            return str(cate)
    
    result['小店行业'] = result.apply(get_ind, axis=1)
    result['小店分类'] = result.apply(get_cate, axis=1)
    return result


def classify_ziying_industry(df):
    """给自营数据打行业/分类标签，通过经营分类字段"""
    def get_ind(row):
        cat = str(row.get('经营一级类目名称', '') or '')
        if cat in ['硬周', '虚拟卡券', '出版物']:
            return 'ACG自营-南征'
        elif cat in ['软周', '赏类']:
            return 'ACG自营-allen'
        else:
            return '自营-其他'
    
    def get_cate(row):
        cat = str(row.get('经营一级类目名称', '') or '')
        cat_map = {'硬周': '硬周', '虚拟卡券': '游戏虚拟', '出版物': '出版物',
                   '软周': '软周', '赏类': '盲盒'}
        return cat_map.get(cat, '自营其他')
    
    result = df.copy()
    result['自营行业'] = result.apply(get_ind, axis=1)
    result['自营分类'] = result.apply(get_cate, axis=1)
    return result


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def safe_float(v):
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return 0.0
        return f
    except: return 0.0

def tol(lst): return [safe_float(x) for x in lst]

def wow_pct(cur, prev):
    c, p = safe_float(cur), safe_float(prev)
    if p == 0: return {'text': '-', 'cls': '', 'value': 0}
    pct = (c - p) / p * 100
    return {'text': ('+' if pct >= 0 else '') + f'{pct:.1f}%',
            'cls': 'up' if pct > 0 else ('down' if pct < 0 else 'neutral'), 'value': pct}

def fmt_gmv(v):
    v = safe_float(v)
    if abs(v) >= 1e8: return f'¥{v/1e8:.2f}亿'
    if abs(v) >= 1e4: return f'¥{v/1e4:.1f}万'
    return f'¥{v:,.0f}'

def fmt_num(v):
    v = safe_float(v)
    if abs(v) >= 1e8: return f'{v/1e8:.2f}亿'
    if abs(v) >= 1e4: return f'{v/1e4:.1f}万'
    return f'{v:,.0f}'

def fmt_pct(v, already_pct=False):
    v = safe_float(v)
    if not already_pct and abs(v) < 1: v = v * 100
    return f'{v:.2f}%'

def fmt_wow_tag(wow):
    if wow['cls'] == 'up': return f'<span class="tag tag-up">{wow["text"]}</span>'
    if wow['cls'] == 'down': return f'<span class="tag tag-down">{wow["text"]}</span>'
    return f'<span style="color:var(--text-4)">{wow["text"]}</span>'

def get_row(df, week, **filters):
    q = df[df['周五-周四周'] == week].copy()
    for k, v in filters.items():
        q = q[q[k] == v]
    return q

def sum_field(df, week, field, **filters):
    r = get_row(df, week, **filters)
    return safe_float(r[field].sum()) if field in r.columns else 0.0


# ── 数据准备 ──────────────────────────────────────────────────────────────────

print("[INFO] 开始加载...")
df1, df2, df3, df4, df5, df6 = load_all()

# 周数升序排列（小周在左，大周在右）
WEEKS = sorted(df1['周五-周四周'].dropna().unique().tolist())
CUR_W = int(WEEKS[-1])  # 当前周 = 最大周
PREV_W = int(WEEKS[-2]) if len(WEEKS) > 1 else None  # 上周 = 第二大周
WEEK_LABELS = [f'W{int(w)}' for w in WEEKS]
BIZES = ['小店', '自营', '工坊', '票务']

# 带行业标签的数据
df2_shop = classify_shop_industry(df2[df2['业务线二级'] == '小店'].copy(), df6)
df2_ziying = classify_ziying_industry(df2[df2['业务线二级'] == '自营'].copy())
df5_shop = classify_shop_industry(df5[df5['业务线二级'] == '小店'].copy(), df6)

SHOP_INDUSTRIES = ['南征', 'allen', '孙悟饭', '加林', '小店其他']
SHOP_IND_DISPLAY = {'南征': '南征', 'allen': 'allen', '孙悟饭': '孙悟饭', '加林': '加林', '小店其他': '小店其他'}
ZIYING_INDUSTRIES = ['ACG自营-南征', 'ACG自营-allen', '自营-其他']

# ── 读取CSS和JS ────────────────────────────────────────────────────────────────
with open(SKILL_DIR / 'base-report.css') as f: CSS = f.read()
with open(SKILL_DIR / 'chart-defaults.js') as f: CHART_JS = f.read()

print(f"[INFO] 当前周: W{CUR_W}, 上周: W{PREV_W}")
print(f"[INFO] 周期: {WEEK_LABELS}")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  S1 数据聚合                                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# S1 各业务线指标
s1_metrics = {}
for biz in BIZES:
    cur_r = get_row(df1, CUR_W, 业务线二级=biz)
    prev_r = get_row(df1, PREV_W, 业务线二级=biz) if PREV_W else pd.DataFrame()
    
    def g(df, field): return safe_float(df[field].sum()) if not df.empty and field in df.columns else 0.0
    
    gmv_c = g(cur_r, 'GMV'); gmv_p = g(prev_r, 'GMV')
    mai_c = g(cur_r, '买家数'); mai_p = g(prev_r, '买家数')
    ord_c = g(cur_r, '订单数'); ord_p = g(prev_r, '订单数')
    pv_c = g(cur_r, '商品曝光PV'); pv_p = g(prev_r, '商品曝光PV')
    ctr_c = safe_float(cur_r['CTR'].mean()) if not cur_r.empty and 'CTR' in cur_r.columns else 0
    ctr_p = safe_float(prev_r['CTR'].mean()) if not prev_r.empty and 'CTR' in prev_r.columns else 0
    cvr_c = safe_float(cur_r['CVR'].mean()) if not cur_r.empty and 'CVR' in cur_r.columns else 0
    cvr_p = safe_float(prev_r['CVR'].mean()) if not prev_r.empty and 'CVR' in prev_r.columns else 0
    gpm_c = safe_float(cur_r['GPM'].mean()) if not cur_r.empty and 'GPM' in cur_r.columns else 0
    gpm_p = safe_float(prev_r['GPM'].mean()) if not prev_r.empty and 'GPM' in prev_r.columns else 0
    
    s1_metrics[biz] = {
        'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
        '买家数': mai_c, '买家数_wow': wow_pct(mai_c, mai_p),
        '订单数': ord_c, '订单数_wow': wow_pct(ord_c, ord_p),
        '曝光PV': pv_c, '曝光PV_wow': wow_pct(pv_c, pv_p),
        'CTR': ctr_c, 'CTR_wow': wow_pct(ctr_c, ctr_p),
        'CVR': cvr_c, 'CVR_wow': wow_pct(cvr_c, cvr_p),
        'GPM': gpm_c, 'GPM_wow': wow_pct(gpm_c, gpm_p),
    }

# 小店对自营控比
def get_ctrl_ratio(df, week):
    xd = sum_field(df, week, 'GMV', 业务线二级='小店')
    zy = sum_field(df, week, 'GMV', 业务线二级='自营')
    return round(xd / zy, 3) if zy > 0 else 0

# S1 趋势数据 by 业务线
s1_gmv_trend = {biz: tol([sum_field(df1, w, 'GMV', 业务线二级=biz) for w in WEEKS]) for biz in BIZES}
s1_pv_trend = {biz: tol([sum_field(df1, w, '商品曝光PV', 业务线二级=biz) for w in WEEKS]) for biz in BIZES}
s1_buyer_trend = {biz: tol([sum_field(df1, w, '买家数', 业务线二级=biz) for w in WEEKS]) for biz in BIZES}

s1_ctr_trend = {}
for biz in BIZES:
    vals = []
    for w in WEEKS:
        r = get_row(df1, w, 业务线二级=biz)
        vals.append(safe_float(r['CTR'].mean()) if not r.empty else 0)
    s1_ctr_trend[biz] = tol(vals)

s1_cvr_trend = {}
for biz in BIZES:
    vals = []
    for w in WEEKS:
        r = get_row(df1, w, 业务线二级=biz)
        vals.append(safe_float(r['CVR'].mean()) if not r.empty else 0)
    s1_cvr_trend[biz] = tol(vals)

s1_gpm_trend = {}
for biz in BIZES:
    vals = []
    for w in WEEKS:
        r = get_row(df1, w, 业务线二级=biz)
        vals.append(safe_float(r['GPM'].mean()) if not r.empty else 0)
    s1_gpm_trend[biz] = tol(vals)

s1_ratio_trend = tol([get_ctrl_ratio(df1, w) for w in WEEKS])

# MTD 数据（用当月最新周做近似）
cur_month_weeks_overall = df1[df1['周五-周四周'] == CUR_W]
# 按业务线 GMV 月累计（取本月所有周的和）
# 由于数据只有周粒度，MTD ≈ 本月内所有周的GMV之和（近似）
# 区分4月和3月
cur_month = 4  # W16对应4月
month_weeks = [w for w in WEEKS if w >= 14]  # W14-W16属于4月区间（近似）
prev_year_month_weeks = month_weeks  # 无去年同期数据，标记N/A

s1_mtd = {}
for biz in ['小店', '自营']:
    mtd_gmv = sum([sum_field(df1, w, 'GMV', 业务线二级=biz) for w in month_weeks])
    s1_mtd[biz] = {'MTD_GMV': mtd_gmv}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  S2 行业拆解数据聚合                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# 整体（小店+自营）by 行业/分类 周趋势
# 小店行业GMV趋势
s2_shop_ind_gmv = {}  # {行业: [w1,w2,w3,...]}
for ind in SHOP_INDUSTRIES:
    vals = []
    for w in WEEKS:
        r = df2_shop[df2_shop['周五-周四周'] == w]
        r = r[r['小店行业'] == ind]
        vals.append(safe_float(r['GMV'].sum()))
    s2_shop_ind_gmv[ind] = tol(vals)

# 自营行业GMV趋势
s2_ziying_ind_gmv = {}
for ind in ZIYING_INDUSTRIES:
    vals = []
    for w in WEEKS:
        r = df2_ziying[df2_ziying['周五-周四周'] == w]
        r = r[r['自营行业'] == ind]
        vals.append(safe_float(r['GMV'].sum()))
    s2_ziying_ind_gmv[ind] = tol(vals)

# 整体行业GMV趋势（小店+自营合并）
ALL_INDUSTRIES = SHOP_INDUSTRIES + ZIYING_INDUSTRIES
s2_all_ind_gmv = {}
for ind in SHOP_INDUSTRIES:
    s2_all_ind_gmv[f'小店-{ind}'] = s2_shop_ind_gmv[ind]
for ind in ZIYING_INDUSTRIES:
    s2_all_ind_gmv[f'自营-{ind}'] = s2_ziying_ind_gmv[ind]

# 小店行业+分类 数据表
def _calc_gpm(gmv_sum, pv_sum):
    pv = safe_float(pv_sum)
    return safe_float(gmv_sum) / pv * 1000 if pv > 0 else 0.0

def get_shop_ind_table(week, prev_week):
    rows = []
    for ind in SHOP_INDUSTRIES:
        # 行业合计
        r_cur = df2_shop[(df2_shop['周五-周四周'] == week) & (df2_shop['小店行业'] == ind)]
        r_prev = df2_shop[(df2_shop['周五-周四周'] == prev_week) & (df2_shop['小店行业'] == ind)] if prev_week else pd.DataFrame()

        gmv_c = safe_float(r_cur['GMV'].sum()); gmv_p = safe_float(r_prev['GMV'].sum())
        buyer_c = safe_float(r_cur['买家数'].sum()); buyer_p = safe_float(r_prev['买家数'].sum())
        ord_c = safe_float(r_cur['订单数'].sum()); ord_p = safe_float(r_prev['订单数'].sum())
        pv_c = safe_float(r_cur['商品曝光PV'].sum()); pv_p = safe_float(r_prev['商品曝光PV'].sum())
        gpm_c = _calc_gpm(gmv_c, pv_c); gpm_p = _calc_gpm(gmv_p, pv_p)

        rows.append({'type': 'industry', 'name': ind,
            'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
            '买家数': buyer_c, '买家数_wow': wow_pct(buyer_c, buyer_p),
            '订单数': ord_c, '订单数_wow': wow_pct(ord_c, ord_p),
            'GPM': gpm_c, 'GPM_wow': wow_pct(gpm_c, gpm_p)})

        # 分类明细：同时包含当前周和上周出现过的分类
        all_cates_cur = set(r_cur['小店分类'].dropna().unique())
        all_cates_prev = set(r_prev['小店分类'].dropna().unique()) if not r_prev.empty else set()
        all_cates = all_cates_cur | all_cates_prev
        for cate in sorted(all_cates, key=lambda x: safe_float(r_cur[r_cur['小店分类']==x]['GMV'].sum()), reverse=True):
            rc = r_cur[r_cur['小店分类'] == cate]
            rp = r_prev[r_prev['小店分类'] == cate] if not r_prev.empty else pd.DataFrame()
            gv_c = safe_float(rc['GMV'].sum()); gv_p = safe_float(rp['GMV'].sum())
            bv_c = safe_float(rc['买家数'].sum()); bv_p = safe_float(rp['买家数'].sum())
            ov_c = safe_float(rc['订单数'].sum()); ov_p = safe_float(rp['订单数'].sum())
            pv_c2 = safe_float(rc['商品曝光PV'].sum()); pv_p2 = safe_float(rp['商品曝光PV'].sum())
            gpv_c = _calc_gpm(gv_c, pv_c2); gpv_p = _calc_gpm(gv_p, pv_p2)
            rows.append({'type': 'category', 'name': cate,
                'GMV': gv_c, 'GMV_wow': wow_pct(gv_c, gv_p),
                '买家数': bv_c, '买家数_wow': wow_pct(bv_c, bv_p),
                '订单数': ov_c, '订单数_wow': wow_pct(ov_c, ov_p),
                'GPM': gpv_c, 'GPM_wow': wow_pct(gpv_c, gpv_p)})
    return rows

def get_ziying_ind_table(week, prev_week):
    rows = []
    for ind in ZIYING_INDUSTRIES:
        r_cur = df2_ziying[(df2_ziying['周五-周四周'] == week) & (df2_ziying['自营行业'] == ind)]
        r_prev = df2_ziying[(df2_ziying['周五-周四周'] == prev_week) & (df2_ziying['自营行业'] == ind)] if prev_week else pd.DataFrame()

        gmv_c = safe_float(r_cur['GMV'].sum()); gmv_p = safe_float(r_prev['GMV'].sum())
        buyer_c = safe_float(r_cur['买家数'].sum()); buyer_p = safe_float(r_prev['买家数'].sum())
        ord_c = safe_float(r_cur['订单数'].sum()); ord_p = safe_float(r_prev['订单数'].sum())
        pv_c = safe_float(r_cur['商品曝光PV'].sum()); pv_p = safe_float(r_prev['商品曝光PV'].sum())
        gpm_c = _calc_gpm(gmv_c, pv_c); gpm_p = _calc_gpm(gmv_p, pv_p)

        rows.append({'type': 'industry', 'name': ind,
            'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
            '买家数': buyer_c, '买家数_wow': wow_pct(buyer_c, buyer_p),
            '订单数': ord_c, '订单数_wow': wow_pct(ord_c, ord_p),
            'GPM': gpm_c, 'GPM_wow': wow_pct(gpm_c, gpm_p)})

        # 分类明细：同时包含当前周和上周出现过的分类
        all_cates_cur = set(r_cur['自营分类'].dropna().unique())
        all_cates_prev = set(r_prev['自营分类'].dropna().unique()) if not r_prev.empty else set()
        all_cates = all_cates_cur | all_cates_prev
        for cate in sorted(all_cates, key=lambda x: safe_float(r_cur[r_cur['自营分类']==x]['GMV'].sum()), reverse=True):
            rc = r_cur[r_cur['自营分类'] == cate]
            rp = r_prev[r_prev['自营分类'] == cate] if not r_prev.empty else pd.DataFrame()
            gv_c = safe_float(rc['GMV'].sum()); gv_p = safe_float(rp['GMV'].sum())
            bv_c = safe_float(rc['买家数'].sum()); bv_p = safe_float(rp['买家数'].sum())
            ov_c = safe_float(rc['订单数'].sum()); ov_p = safe_float(rp['订单数'].sum())
            pv_c2 = safe_float(rc['商品曝光PV'].sum()); pv_p2 = safe_float(rp['商品曝光PV'].sum())
            gpv_c = _calc_gpm(gv_c, pv_c2); gpv_p = _calc_gpm(gv_p, pv_p2)
            rows.append({'type': 'category', 'name': cate,
                'GMV': gv_c, 'GMV_wow': wow_pct(gv_c, gv_p),
                '买家数': bv_c, '买家数_wow': wow_pct(bv_c, bv_p),
                '订单数': ov_c, '订单数_wow': wow_pct(ov_c, ov_p),
                'GPM': gpv_c, 'GPM_wow': wow_pct(gpv_c, gpv_p)})
    return rows

s2_shop_table = get_shop_ind_table(CUR_W, PREV_W)
s2_ziying_table = get_ziying_ind_table(CUR_W, PREV_W)

# MTD表（S2行业维度）
s2_mtd_shop = {}
s2_mtd_ziying = {}
for ind in SHOP_INDUSTRIES:
    gmv = sum([safe_float(df2_shop[(df2_shop['周五-周四周']==w) & (df2_shop['小店行业']==ind)]['GMV'].sum()) for w in month_weeks])
    s2_mtd_shop[ind] = gmv
for ind in ZIYING_INDUSTRIES:
    gmv = sum([safe_float(df2_ziying[(df2_ziying['周五-周四周']==w) & (df2_ziying['自营行业']==ind)]['GMV'].sum()) for w in month_weeks])
    s2_mtd_ziying[ind] = gmv

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  S3 小店商家拆解数据聚合                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Top20 商家（整体，按W16 GMV排序）
cur_shop = df2_shop[df2_shop['周五-周四周'] == CUR_W]
prev_shop = df2_shop[df2_shop['周五-周四周'] == PREV_W] if PREV_W else pd.DataFrame()

# 按商家汇总
def agg_merchant(df, df_prev=None):
    grp = df.groupby(['商家ID', '店铺名称', '小店行业', '小店分类']).agg(
        GMV=('GMV', 'sum'),
        买家数=('买家数', 'sum'),
        订单数=('订单数', 'sum'),
        曝光PV=('商品曝光PV', 'sum'),
        GPM=('GPM', 'mean'),
        CTR=('CTR', 'mean'),
        CVR=('CVR', 'mean')
    ).reset_index()
    grp['客单价'] = grp.apply(lambda r: safe_float(r['GMV']) / safe_float(r['订单数']) if safe_float(r['订单数']) > 0 else 0, axis=1)
    return grp

cur_merch = agg_merchant(cur_shop)
prev_merch = agg_merchant(prev_shop) if not prev_shop.empty else pd.DataFrame()

# Top20 整体
top20_all = cur_merch.nlargest(20, 'GMV')
total_shop_gmv_cur = safe_float(cur_shop['GMV'].sum())
total_shop_gmv_prev = safe_float(prev_shop['GMV'].sum()) if not prev_shop.empty else 0
total_delta = total_shop_gmv_cur - total_shop_gmv_prev

def build_merchant_rows(top_df, prev_df, total_gmv, total_delta_gmv):
    rows = []
    for _, row in top_df.iterrows():
        mid = row['商家ID']
        gmv_c = safe_float(row['GMV'])
        
        if not prev_df.empty:
            pr = prev_df[prev_df['商家ID'] == mid]
            gmv_p = safe_float(pr['GMV'].sum()) if not pr.empty else 0
            buyer_p = safe_float(pr['买家数'].sum()) if not pr.empty else 0
            ord_p = safe_float(pr['订单数'].sum()) if not pr.empty else 0
            gpm_p = safe_float(pr['GPM'].mean()) if not pr.empty else 0
            ctr_p = safe_float(pr['CTR'].mean()) if not pr.empty else 0
            cvr_p = safe_float(pr['CVR'].mean()) if not pr.empty else 0
        else:
            gmv_p = buyer_p = ord_p = gpm_p = ctr_p = cvr_p = 0
        
        contrib = (gmv_c - gmv_p) / total_delta_gmv * 100 if abs(total_delta_gmv) > 0 else 0
        gmv_share = gmv_c / total_gmv * 100 if total_gmv > 0 else 0
        
        rows.append({
            'name': row.get('店铺名称', '未知'),
            'industry': row.get('小店行业', '-'),
            'category': row.get('小店分类', '-'),
            'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
            'GMV_prev': gmv_p,
            'GMV_share': gmv_share,
            '买家数': safe_float(row['买家数']), '买家数_wow': wow_pct(row['买家数'], buyer_p),
            '订单数': safe_float(row['订单数']), '订单数_wow': wow_pct(row['订单数'], ord_p),
            '客单价': safe_float(row['客单价']),
            'CVR': safe_float(row['CVR']), 'CVR_wow': wow_pct(row['CVR'], cvr_p),
            'GPM': safe_float(row['GPM']), 'GPM_wow': wow_pct(row['GPM'], gpm_p),
            '曝光PV': safe_float(row['曝光PV']),
            '贡献率': contrib,
        })
    return rows

s3_top20_rows = build_merchant_rows(top20_all, prev_merch, total_shop_gmv_cur, total_delta)

# Top20 GMV 趋势折线图数据（只取前10支持图表可读）
top10_names = [r['name'] for r in s3_top20_rows[:10]]
s3_top10_trend = {}
for name in top10_names:
    vals = []
    for w in WEEKS:
        r = df2_shop[(df2_shop['周五-周四周'] == w) & (df2_shop['店铺名称'] == name)]
        vals.append(safe_float(r['GMV'].sum()))
    s3_top10_trend[name] = tol(vals)

# Top20 商品（从商品明细）
df3_clean = df3.copy()
df3_clean.columns = df3_clean.columns.str.strip()

# 按周过滤（支持两种格式：日粒度用日期列，周粒度用周五-周四周列）
if '日期' in df3_clean.columns and pd.api.types.is_datetime64_any_dtype(df3_clean['日期']):
    w16_start = pd.Timestamp('2026-04-10'); w16_end = pd.Timestamp('2026-04-16')
    w15_start = pd.Timestamp('2026-04-03'); w15_end = pd.Timestamp('2026-04-09')
    df3_w16 = df3_clean[df3_clean['日期'].between(w16_start, w16_end)]
    df3_w15 = df3_clean[df3_clean['日期'].between(w15_start, w15_end)]
elif '周五-周四周' in df3_clean.columns:
    # 周粒度数据（4月24日数据格式），按周数过滤
    df3_w16 = df3_clean[df3_clean['周五-周四周'] == CUR_W]
    df3_w15 = df3_clean[df3_clean['周五-周四周'] == PREV_W] if PREV_W else pd.DataFrame()
else:
    df3_w16 = df3_clean; df3_w15 = pd.DataFrame()

# 按商品汇总
def agg_product(df):
    if df.empty: return pd.DataFrame()
    df = df.copy()
    df.columns = df.columns.str.strip()
    # 列名兼容：优先用实际列名，兜底旧名
    merch_id_col = next((c for c in ['商家ID', '商户id'] if c in df.columns), '商家ID')
    merch_name_col = next((c for c in ['店铺名称', '商户名称'] if c in df.columns), '店铺名称')
    prod_id_col = next((c for c in ['商品ID', '商品id'] if c in df.columns), '商品ID')
    gmv_col = 'GMV（不减退款）' if 'GMV（不减退款）' in df.columns else ('GMV' if 'GMV' in df.columns else '支付订单金额(元)')
    buyer_col = '支付订单买家数' if '支付订单买家数' in df.columns else '买家数'
    ord_col = '支付订单数' if '支付订单数' in df.columns else '订单数'
    ctr_col = 'PVCTR' if 'PVCTR' in df.columns else ('CTR' if 'CTR' in df.columns else None)

    agg_dict = {
        'GMV': (gmv_col, 'sum'),
        '买家数': (buyer_col, 'sum'),
        '订单数': (ord_col, 'sum'),
        '曝光PV': ('商品曝光PV', 'sum'),
    }
    if ctr_col: agg_dict['CTR'] = (ctr_col, 'mean')

    grp = df.groupby([merch_id_col, merch_name_col, prod_id_col, '商品名称']).agg(**agg_dict).reset_index()
    grp.rename(columns={merch_id_col: '商家ID', merch_name_col: '店铺名称', prod_id_col: '商品ID'}, inplace=True)
    if 'CTR' not in grp.columns: grp['CTR'] = 0
    return grp

prod_w16 = agg_product(df3_w16)
prod_w15 = agg_product(df3_w15)

if not prod_w16.empty:
    top20_prod = prod_w16.nlargest(20, 'GMV')
else:
    top20_prod = pd.DataFrame()

s3_top20_prod_rows = []
total_prod_gmv = safe_float(prod_w16['GMV'].sum()) if not prod_w16.empty else 1
for _, row in (top20_prod.iterrows() if not top20_prod.empty else []):
    pid = row.get('商品ID')
    if not prod_w15.empty:
        pr = prod_w15[prod_w15['商品ID'] == pid]
        gmv_p = safe_float(pr['GMV'].sum()) if not pr.empty else 0
    else:
        gmv_p = 0
    gmv_c = safe_float(row['GMV'])
    buyer_c = safe_float(row.get('买家数', 0))
    ord_c = safe_float(row.get('订单数', 0))
    s3_top20_prod_rows.append({
        'shop': row.get('店铺名称', '-'),
        'name': row.get('商品名称', '-'),
        'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
        'GMV_prev': gmv_p,
        'GMV_share': gmv_c / total_prod_gmv * 100 if total_prod_gmv > 0 else 0,
        '买家数': buyer_c,
        '订单数': ord_c,
        '客单价': gmv_c / ord_c if ord_c > 0 else 0,
        'CVR': safe_float(row.get('CTR', 0)),
        'GPM': safe_float(row.get('GPM', 0)),
        '曝光PV': safe_float(row.get('曝光PV', 0)),
    })

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  S4 流量渠道数据聚合                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# 整体/小店/自营 曝光PV 周趋势
s4_pv_total = tol([sum_field(df1, w, '商品曝光PV') for w in WEEKS])
s4_pv_shop = tol([sum_field(df1, w, '商品曝光PV', 业务线二级='小店') for w in WEEKS])
s4_pv_ziying = tol([sum_field(df1, w, '商品曝光PV', 业务线二级='自营') for w in WEEKS])
s4_shop_pv_ratio = [s4_pv_shop[i]/s4_pv_total[i]*100 if s4_pv_total[i] > 0 else 0 for i in range(len(WEEKS))]

# 整体流量汇总表（小店+自营，区分）
def get_traffic_summary_row(df1, week, prev_week, biz=None):
    if biz:
        r_c = get_row(df1, week, 业务线二级=biz)
        r_p = get_row(df1, prev_week, 业务线二级=biz) if prev_week else pd.DataFrame()
    else:
        r_c = df1[df1['周五-周四周'] == week]
        r_p = df1[df1['周五-周四周'] == prev_week] if prev_week else pd.DataFrame()
    
    pv_c = safe_float(r_c['商品曝光PV'].sum())
    pv_p = safe_float(r_p['商品曝光PV'].sum())
    gmv_c = safe_float(r_c['GMV'].sum())
    gmv_p = safe_float(r_p['GMV'].sum())
    ctr_c = safe_float(r_c['CTR'].mean())
    ctr_p = safe_float(r_p['CTR'].mean())
    cvr_c = safe_float(r_c['CVR'].mean())
    cvr_p = safe_float(r_p['CVR'].mean())
    gpm_c = safe_float(r_c['GPM'].mean())
    gpm_p = safe_float(r_p['GPM'].mean())
    
    return {
        'PV': pv_c, 'PV_wow': wow_pct(pv_c, pv_p),
        'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
        'CTR': ctr_c, 'CTR_wow': wow_pct(ctr_c, ctr_p),
        'CVR': cvr_c, 'CVR_wow': wow_pct(cvr_c, cvr_p),
        'GPM': gpm_c, 'GPM_wow': wow_pct(gpm_c, gpm_p),
    }

s4_total_row = get_traffic_summary_row(df1, CUR_W, PREV_W)
s4_shop_row = get_traffic_summary_row(df1, CUR_W, PREV_W, '小店')
s4_ziying_row = get_traffic_summary_row(df1, CUR_W, PREV_W, '自营')
total_pv_cur = safe_float(df1[df1['周五-周四周'] == CUR_W]['商品曝光PV'].sum())
total_gmv_cur = safe_float(df1[df1['周五-周四周'] == CUR_W]['GMV'].sum())

# 小店核心渠道 Top10
def get_channel_top10(df4, week, prev_week, biz, total_pv, total_gmv):
    r_c = df4[(df4['周五-周四周'] == week) & (df4['业务线二级'] == biz)]
    r_p = df4[(df4['周五-周四周'] == prev_week) & (df4['业务线二级'] == biz)] if prev_week else pd.DataFrame()
    
    grp_c = r_c.groupby('资源位二级入口').agg(曝光PV=('商品曝光PV','sum'),GMV=('GMV','sum'),CTR=('CTR','mean'),CVR=('CVR','mean'),GPM=('GPM','mean')).reset_index()
    grp_c = grp_c.nlargest(10, 'GMV')
    
    rows = []
    for _, row in grp_c.iterrows():
        ch = row['资源位二级入口']
        pv_c = safe_float(row['曝光PV']); gmv_c = safe_float(row['GMV'])
        
        if not r_p.empty:
            rp = r_p[r_p['资源位二级入口'] == ch]
            pv_p = safe_float(rp['商品曝光PV'].sum()) if not rp.empty else 0
            gmv_p = safe_float(rp['GMV'].sum()) if not rp.empty else 0
            ctr_p = safe_float(rp['CTR'].mean()) if not rp.empty else 0
            cvr_p = safe_float(rp['CVR'].mean()) if not rp.empty else 0
            gpm_p = safe_float(rp['GPM'].mean()) if not rp.empty else 0
        else:
            pv_p = gmv_p = ctr_p = cvr_p = gpm_p = 0
        
        rows.append({
            'channel': ch,
            'PV': pv_c, 'PV_wow': wow_pct(pv_c, pv_p),
            'PV_share': pv_c/total_pv*100 if total_pv > 0 else 0,
            'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
            'GMV_share': gmv_c/total_gmv*100 if total_gmv > 0 else 0,
            'CTR': safe_float(row['CTR']), 'CTR_wow': wow_pct(row['CTR'], ctr_p),
            'CVR': safe_float(row['CVR']), 'CVR_wow': wow_pct(row['CVR'], cvr_p),
            'GPM': safe_float(row['GPM']), 'GPM_wow': wow_pct(row['GPM'], gpm_p),
        })
    return rows

df4_clean = df4.copy()
df4_clean.columns = df4_clean.columns.str.strip()
if 'GMV（不减退款）' in df4_clean.columns: df4_clean = df4_clean.rename(columns={'GMV（不减退款）': 'GMV'})
if '支付订单买家数' in df4_clean.columns: df4_clean = df4_clean.rename(columns={'支付订单买家数': '买家数'})
if 'PVCTR' in df4_clean.columns: df4_clean = df4_clean.rename(columns={'PVCTR': 'CTR'})
if '商详支付转化率-UV' in df4_clean.columns: df4_clean = df4_clean.rename(columns={'商详支付转化率-UV': 'CVR'})

# ⚠️ 流量文件可能比整体文件少1周（如整体已有W16，流量还停在W15）
# 且流量文件最新周可能是不完整数据（只有部分天的明细）
# 用整体文件 GMV 做基准，检测流量文件各周的数据完整性
def get_s4_valid_weeks(df4c, df1, threshold=0.8):
    """
    比对流量明细 GMV 和整体文件 GMV，过滤掉覆盖率<80%的不完整周。
    返回 valid_weeks（完整周列表，升序）
    """
    all_weeks = sorted(df4c['周五-周四周'].dropna().unique().tolist())
    valid = []
    for w in all_weeks:
        flow_gmv = df4c[df4c['周五-周四周']==w]['GMV'].sum()
        whole_gmv = df1[df1['周五-周四周']==w]['GMV'].sum() if w in df1['周五-周四周'].values else 0
        coverage = flow_gmv / whole_gmv if whole_gmv > 0 else 0
        status = '✓' if coverage >= threshold else f'⚠ 仅{coverage:.0%}（数据不完整）'
        print(f"[INFO] 流量W{int(w)} GMV覆盖率: {coverage:.0%} {status}")
        if coverage >= threshold:
            valid.append(w)
    return valid

S4_WEEKS = get_s4_valid_weeks(df4_clean, df1)
if not S4_WEEKS:
    # 所有周都不完整，退回全部周（至少能显示）
    S4_WEEKS = sorted(df4_clean['周五-周四周'].dropna().unique().tolist())
    print("[WARN] 流量文件所有周GMV覆盖率<80%，使用全部周")

# 生成流量数据完整性提示 & Top10 上周（用原始数据，不过滤）
all_s4_weeks_raw = sorted(df4_clean['周五-周四周'].dropna().unique().tolist())
incomplete_weeks = [w for w in all_s4_weeks_raw if w not in S4_WEEKS]

# S4_CUR_W 从原始列表取最大周（流量文件的最新周，优先于整体文件）
# S4_PREV_W 取次大周（即使不完整也比显示"-"更有参考价值）
S4_CUR_W = int(all_s4_weeks_raw[-1])
S4_PREV_W = int(all_s4_weeks_raw[-2]) if len(all_s4_weeks_raw) >= 2 else None
print(f"[INFO] 流量有效周: {[int(w) for w in S4_WEEKS]}, 当前周: W{S4_CUR_W}, 环比上周: W{S4_PREV_W}")

if incomplete_weeks:
    incomplete_str = '、'.join([f'W{int(w)}' for w in incomplete_weeks])
    s4_data_notice = f'<div style="margin:0 0 16px;padding:8px 14px;background:#fff8e1;border-left:3px solid #f59e0b;border-radius:4px;font-size:13px;color:#92400e">⚠ <b>数据说明</b>：流量明细有效数据截至 W{S4_CUR_W}（{incomplete_str} 数据不完整）。渠道 Top10 环比参考 W{int(S4_PREV_W)}（{incomplete_str}，仅供参考）；天马/feed 趋势基于 W{S4_CUR_W}。</div>'
else:
    s4_data_notice = ''

shop_pv_cur = safe_float(df4_clean[(df4_clean['周五-周四周']==S4_CUR_W)&(df4_clean['业务线二级']=='小店')]['商品曝光PV'].sum())
shop_gmv_cur = safe_float(df4_clean[(df4_clean['周五-周四周']==S4_CUR_W)&(df4_clean['业务线二级']=='小店')]['GMV'].sum())
ziying_pv_cur = safe_float(df4_clean[(df4_clean['周五-周四周']==S4_CUR_W)&(df4_clean['业务线二级']=='自营')]['商品曝光PV'].sum())
ziying_gmv_cur = safe_float(df4_clean[(df4_clean['周五-周四周']==S4_CUR_W)&(df4_clean['业务线二级']=='自营')]['GMV'].sum())

s4_shop_channels = get_channel_top10(df4_clean, S4_CUR_W, S4_PREV_W, '小店', shop_pv_cur, shop_gmv_cur)
s4_ziying_channels = get_channel_top10(df4_clean, S4_CUR_W, S4_PREV_W, '自营', ziying_pv_cur, ziying_gmv_cur)

# 天马推荐商品卡专项
TIANMA = '天马推荐商品卡'
# 趋势表用所有历史周（不过滤），展示完整走势
ALL_S4_WEEKS = sorted(df4_clean['周五-周四周'].dropna().unique().tolist())
def get_special_channel_data(df4, channel_name):
    rows = []
    for w in ALL_S4_WEEKS:  # 天马/feed 趋势表用全量周（含不完整周，仅供走势参考）
        r_all = df4[df4['周五-周四周'] == w]
        r_ch = r_all[r_all['资源位二级入口'] == channel_name]
        r_shop = r_ch[r_ch['业务线二级'] == '小店']
        r_zy = r_ch[r_ch['业务线二级'] == '自营']
        
        total_ch_pv = safe_float(r_ch['商品曝光PV'].sum())
        total_all_pv = safe_float(r_all['商品曝光PV'].sum())
        shop_ch_pv = safe_float(r_shop['商品曝光PV'].sum())
        zy_ch_pv = safe_float(r_zy['商品曝光PV'].sum())
        
        rows.append({
            'week': f'W{int(w)}',
            'total_pv': total_ch_pv,
            'shop_pv': shop_ch_pv,
            'ziying_pv': zy_ch_pv,
            'shop_pv_ratio': shop_ch_pv/total_ch_pv*100 if total_ch_pv > 0 else 0,
            'channel_pv_ratio': total_ch_pv/total_all_pv*100 if total_all_pv > 0 else 0,
            'total_gmv': safe_float(r_ch['GMV'].sum()),
            'shop_gmv': safe_float(r_shop['GMV'].sum()),
            'shop_ord': safe_float(r_shop['订单数'].sum()) if '订单数' in r_shop.columns else safe_float(r_shop['支付订单数'].sum()) if '支付订单数' in r_shop.columns else 0,
            'total_ord': safe_float(r_ch['订单数'].sum()) if '订单数' in r_ch.columns else safe_float(r_ch['支付订单数'].sum()) if '支付订单数' in r_ch.columns else 0,
            'total_ctr': safe_float(r_ch['CTR'].mean()),
            'shop_ctr': safe_float(r_shop['CTR'].mean()),
            'total_cvr': safe_float(r_ch['CVR'].mean()),
            'shop_cvr': safe_float(r_shop['CVR'].mean()),
            'total_gpm': safe_float(r_ch['GPM'].mean()),
            'shop_gpm': safe_float(r_shop['GPM'].mean()),
        })
    return rows

s4_tianma_data = get_special_channel_data(df4_clean, TIANMA)
s4_feed_data = get_special_channel_data(df4_clean, '商城首页feed')

# 天马/feed 独立横轴标签（只含流量文件有的周，避免和全局WEEK_LABELS错位）
S4_SPECIAL_LABELS = [f'W{int(w)}' for w in ALL_S4_WEEKS]

# 天马/商城feed 趋势图数据
s4_tianma_pv_total = tol([r['total_pv'] for r in s4_tianma_data])
s4_tianma_pv_shop = tol([r['shop_pv'] for r in s4_tianma_data])
s4_tianma_pv_zy = tol([r['ziying_pv'] for r in s4_tianma_data])
s4_feed_pv_total = tol([r['total_pv'] for r in s4_feed_data])
s4_feed_pv_shop = tol([r['shop_pv'] for r in s4_feed_data])
s4_feed_pv_zy = tol([r['ziying_pv'] for r in s4_feed_data])

# 小店行业流量表 — 使用 行业.xlsx（含商品曝光PV + 行业标签）代替流量文件
def get_shop_industry_traffic_from_df2(df2_labeled, week, prev_week):
    """从行业数据（已带行业标签）计算小店分行业流量概况"""
    r_c = df2_labeled[df2_labeled['周五-周四周'] == week]
    r_p = df2_labeled[df2_labeled['周五-周四周'] == prev_week] if prev_week else pd.DataFrame()
    
    total_pv_all = safe_float(r_c['商品曝光PV'].sum())
    total_gmv_all = safe_float(r_c['GMV'].sum())
    
    rows = []
    for ind in SHOP_INDUSTRIES:
        rc = r_c[r_c['小店行业'] == ind]
        rp = r_p[r_p['小店行业'] == ind] if not r_p.empty else pd.DataFrame()
        
        pv_c = safe_float(rc['商品曝光PV'].sum()); pv_p = safe_float(rp['商品曝光PV'].sum()) if not rp.empty else 0
        gmv_c = safe_float(rc['GMV'].sum()); gmv_p = safe_float(rp['GMV'].sum()) if not rp.empty else 0
        ctr_c = safe_float(rc['CTR'].mean()); ctr_p = safe_float(rp['CTR'].mean()) if not rp.empty else 0
        cvr_c = safe_float(rc['CVR'].mean()); cvr_p = safe_float(rp['CVR'].mean()) if not rp.empty else 0
        gpm_c = safe_float(rc['GPM'].mean()); gpm_p = safe_float(rp['GPM'].mean()) if not rp.empty else 0
        
        rows.append({
            'industry': ind, 'category': '',
            'PV': pv_c, 'PV_wow': wow_pct(pv_c, pv_p),
            'PV_share': pv_c/total_pv_all*100 if total_pv_all > 0 else 0,
            'GMV': gmv_c, 'GMV_wow': wow_pct(gmv_c, gmv_p),
            'GMV_share': gmv_c/total_gmv_all*100 if total_gmv_all > 0 else 0,
            'CTR': ctr_c, 'CTR_wow': wow_pct(ctr_c, ctr_p),
            'CVR': cvr_c, 'CVR_wow': wow_pct(cvr_c, cvr_p),
            'GPM': gpm_c, 'GPM_wow': wow_pct(gpm_c, gpm_p),
            'type': 'industry'
        })
    return rows

s4_shop_industry_rows = get_shop_industry_traffic_from_df2(df2_shop, CUR_W, PREV_W)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  S5 内容类型数据聚合                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

CONTENT_TYPES = ['商品', '视频', '直播', '动态', '其他']

def get_content_dist(df5, week, biz=None):
    r = df5[df5['周五-周四周'] == week]
    if biz: r = r[r['业务线二级'] == biz]
    grp = r.groupby('内容类型')['GMV'].sum()
    return {ct: safe_float(grp.get(ct, 0)) for ct in CONTENT_TYPES}

s5_overall = get_content_dist(df5, CUR_W)
s5_shop = get_content_dist(df5, CUR_W, '小店')
s5_ziying = get_content_dist(df5, CUR_W, '自营')

# 小店分行业成交体裁
s5_shop_by_ind = {}
for ind in SHOP_INDUSTRIES:
    r = df5_shop[(df5_shop['周五-周四周'] == CUR_W) & (df5_shop['小店行业'] == ind)]
    grp = r.groupby('内容类型')['GMV'].sum()
    s5_shop_by_ind[ind] = {ct: safe_float(grp.get(ct, 0)) for ct in CONTENT_TYPES}

# S5 各体裁上周环比计算
def get_content_with_wow(df5, week, prev_week, biz=None):
    """获取本周+上周体裁数据及环比"""
    r_cur = df5[df5['周五-周四周'] == week]
    r_prev = df5[df5['周五-周四周'] == prev_week] if prev_week else pd.DataFrame()
    if biz:
        r_cur = r_cur[r_cur['业务线二级'] == biz]
        r_prev = r_prev[r_prev['业务线二级'] == biz] if not r_prev.empty else pd.DataFrame()
    
    rows = []
    for ct in CONTENT_TYPES:
        cur_gmv = safe_float(r_cur[r_cur['内容类型'] == ct]['GMV'].sum())
        prev_gmv = safe_float(r_prev[r_prev['内容类型'] == ct]['GMV'].sum()) if not r_prev.empty else 0
        total_cur = safe_float(r_cur['GMV'].sum())
        total_prev = safe_float(r_prev['GMV'].sum()) if not r_prev.empty else 0
        cur_share = cur_gmv / total_cur * 100 if total_cur > 0 else 0
        prev_share = prev_gmv / total_prev * 100 if total_prev > 0 else 0
        rows.append({
            'type': ct,
            'GMV': cur_gmv, 'GMV_wow': wow_pct(cur_gmv, prev_gmv),
            'GMV_prev': prev_gmv,
            'share': cur_share, 'share_wow': wow_pct(cur_share, prev_share),
            'prev_share': prev_share,
        })
    return rows

s5_overall_rows = get_content_with_wow(df5, CUR_W, PREV_W)
s5_shop_rows = get_content_with_wow(df5, CUR_W, PREV_W, '小店')
s5_ziying_rows = get_content_with_wow(df5, CUR_W, PREV_W, '自营')

print("[INFO] 数据聚合完成，开始生成HTML...")

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  HTML 生成函数                                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def ind_table_html(rows, total_row=None):
    """渲染行业+分类层级表格"""
    html = '<thead><tr>'
    html += '<th>行业 / 分类</th>'
    html += f'<th class="num">W{CUR_W} GMV</th>'
    html += f'<th class="num">W{PREV_W} GMV</th>'
    html += '<th class="num">周环比</th>'
    html += '<th class="num">买家数</th><th class="num">环比</th>'
    html += '<th class="num">订单数</th><th class="num">环比</th>'
    html += '<th class="num">GPM</th><th class="num">环比</th>'
    html += '</tr></thead><tbody>'
    
    for row in rows:
        is_ind = row['type'] == 'industry'
        cls = '' if is_ind else ' class="sub-row"'
        prefix = '' if is_ind else '└ '
        style = ' style="font-weight:600;background:rgba(255,255,255,0.03)"' if is_ind else ''
        
        # 上周GMV
        cur_gmv = row['GMV']
        wow = row['GMV_wow']
        
        html += f'<tr{cls}{style}>'
        html += f'<td>{prefix}{row["name"]}</td>'
        html += f'<td class="num">{fmt_gmv(cur_gmv)}</td>'
        prev_gmv_val = cur_gmv / (1 + wow["value"]/100) if wow["value"] != 0 and wow["cls"] != "" else 0
        # 直接用cur-prev算
        if wow['cls'] != '':
            wow_v = wow['value']
            p_gmv = cur_gmv / (1 + wow_v/100) if (1 + wow_v/100) != 0 else 0
        else:
            p_gmv = 0
        html += f'<td class="num">{fmt_gmv(p_gmv) if p_gmv > 0 else "-"}</td>'
        html += f'<td class="num">{fmt_wow_tag(wow)}</td>'
        html += f'<td class="num">{fmt_num(row["买家数"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["买家数_wow"])}</td>'
        html += f'<td class="num">{fmt_num(row["订单数"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["订单数_wow"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["GPM"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["GPM_wow"])}</td>'
        html += '</tr>'
    
    html += '</tbody>'
    return html

def merchant_table_html(rows, show_industry=False):
    """渲染商家数据表"""
    html = '<thead><tr>'
    html += '<th>#</th><th>店铺名称</th>'
    if show_industry: html += '<th>行业</th><th>分类</th>'
    html += f'<th class="num">W{CUR_W} GMV</th><th class="num">占比</th>'
    html += f'<th class="num">W{PREV_W} GMV</th><th class="num">周环比</th>'
    html += '<th class="num">贡献率</th>'
    html += '<th class="num">买家数</th><th class="num">环比</th>'
    html += '<th class="num">订单量</th><th class="num">环比</th>'
    html += '<th class="num">客单价</th><th class="num">CVR</th>'
    html += '<th class="num">GPM</th><th class="num">曝光PV</th>'
    html += '</tr></thead><tbody>'
    
    for i, row in enumerate(rows, 1):
        contrib_cls = 'up-text' if row['贡献率'] > 0 else 'down-text' if row['贡献率'] < 0 else ''
        html += f'<tr>'
        html += f'<td class="text-dim">{i}</td>'
        html += f'<td>{row["name"]}</td>'
        if show_industry:
            html += f'<td class="text-muted">{row.get("industry","-")}</td>'
            html += f'<td class="text-muted">{row.get("category","-")}</td>'
        html += f'<td class="num">{fmt_gmv(row["GMV"])}</td>'
        html += f'<td class="num text-muted">{row["GMV_share"]:.1f}%</td>'
        html += f'<td class="num text-dim">{fmt_gmv(row["GMV_prev"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["GMV_wow"])}</td>'
        contrib_sign = '+' if row['贡献率'] >= 0 else ''
        html += f'<td class="num"><span class="{contrib_cls}">{contrib_sign}{row["贡献率"]:.1f}%</span></td>'
        html += f'<td class="num">{fmt_num(row["买家数"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["买家数_wow"])}</td>'
        html += f'<td class="num">{fmt_num(row["订单数"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["订单数_wow"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["客单价"])}</td>'
        html += f'<td class="num">{fmt_pct(row["CVR"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["GPM"])}</td>'
        html += f'<td class="num">{fmt_num(row["曝光PV"])}</td>'
        html += '</tr>'
    
    html += '</tbody>'
    return html

def product_table_html(rows):
    """渲染商品数据表"""
    prev_w_label = f'W{int(PREV_W)}' if PREV_W else '-'
    html = '<thead><tr>'
    html += '<th>#</th><th>店铺</th><th>商品名称</th>'
    html += f'<th class="num">W{int(CUR_W)} GMV</th><th class="num">占比</th>'
    html += f'<th class="num">{prev_w_label} GMV</th><th class="num">周环比</th>'
    html += '<th class="num">买家数</th><th class="num">订单量</th>'
    html += '<th class="num">客单价</th><th class="num">GPM</th><th class="num">曝光PV</th>'
    html += '</tr></thead><tbody>'
    
    for i, row in enumerate(rows, 1):
        html += f'<tr>'
        html += f'<td class="text-dim">{i}</td>'
        shop_name = str(row.get('shop','-'))[:15]
        prod_name = str(row.get('name','-'))[:30]
        html += f'<td class="text-muted">{shop_name}</td>'
        html += f'<td>{prod_name}</td>'
        html += f'<td class="num">{fmt_gmv(row["GMV"])}</td>'
        html += f'<td class="num text-muted">{row["GMV_share"]:.1f}%</td>'
        html += f'<td class="num text-dim">{fmt_gmv(row.get("GMV_prev",0))}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["GMV_wow"])}</td>'
        html += f'<td class="num">{fmt_num(row["买家数"])}</td>'
        html += f'<td class="num">{fmt_num(row["订单数"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["客单价"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["GPM"])}</td>'
        html += f'<td class="num">{fmt_num(row["曝光PV"])}</td>'
        html += '</tr>'
    
    html += '</tbody>'
    return html

def channel_table_html(rows, title="渠道"):
    """渲染渠道数据表"""
    html = '<thead><tr>'
    html += f'<th>{title}</th>'
    html += '<th class="num">曝光PV</th><th class="num">流量占比</th><th class="num">环比</th>'
    html += '<th class="num">GMV</th><th class="num">GMV占比</th><th class="num">环比</th>'
    html += '<th class="num">CTR</th><th class="num">环比</th>'
    html += '<th class="num">CVR</th><th class="num">环比</th>'
    html += '<th class="num">GPM</th><th class="num">环比</th>'
    html += '</tr></thead><tbody>'
    
    for row in rows:
        html += '<tr>'
        html += f'<td>{row.get("channel","")}</td>'
        html += f'<td class="num">{fmt_num(row["PV"])}</td>'
        html += f'<td class="num text-muted">{row["PV_share"]:.1f}%</td>'
        html += f'<td class="num">{fmt_wow_tag(row["PV_wow"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["GMV"])}</td>'
        html += f'<td class="num text-muted">{row["GMV_share"]:.1f}%</td>'
        html += f'<td class="num">{fmt_wow_tag(row["GMV_wow"])}</td>'
        html += f'<td class="num">{fmt_pct(row["CTR"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["CTR_wow"])}</td>'
        html += f'<td class="num">{fmt_pct(row["CVR"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["CVR_wow"])}</td>'
        html += f'<td class="num">{fmt_gmv(row["GPM"])}</td>'
        html += f'<td class="num">{fmt_wow_tag(row["GPM_wow"])}</td>'
        html += '</tr>'
    
    html += '</tbody>'
    return html

def special_channel_table_html(data_rows, channel_name):
    # 表头列名从 data_rows 自身取，与实际数据行数对齐（避免和全局 WEEK_LABELS 错位）
    html = '<thead><tr>'
    html += '<th>指标</th>'
    for dr in data_rows:
        html += f'<th class="num">{dr["week"]}</th>'
    html += '</tr></thead><tbody>'
    
    fields = [
        ('整体曝光PV', 'total_pv', fmt_num),
        ('渠道曝光占比', 'channel_pv_ratio', lambda v: f'{v:.2f}%'),
        ('小店曝光PV', 'shop_pv', fmt_num),
        ('小店曝光占比', 'shop_pv_ratio', lambda v: f'{v:.2f}%'),
        ('整体订单量', 'total_ord', fmt_num),
        ('小店订单量', 'shop_ord', fmt_num),
        ('总GMV', 'total_gmv', fmt_gmv),
        ('小店GMV', 'shop_gmv', fmt_gmv),
        ('总GPM', 'total_gpm', fmt_gmv),
        ('小店GPM', 'shop_gpm', fmt_gmv),
        ('总CTR', 'total_ctr', fmt_pct),
        ('小店CTR', 'shop_ctr', fmt_pct),
        ('总CVR', 'total_cvr', fmt_pct),
        ('小店CVR', 'shop_cvr', fmt_pct),
    ]
    
    for label, key, fmtfn in fields:
        html += f'<tr><td>{label}</td>'
        for dr in data_rows:
            html += f'<td class="num">{fmtfn(dr[key])}</td>'
        html += '</tr>'
    
    html += '</tbody>'
    return html

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  HTML 主体                                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ── 生成结论解读 ──
print("[INFO] 生成结论解读...")
conclusions = generate_conclusions(
    df1, df2, df3, df4, df5, s1_mtd,
    s2_shop_table, s2_ziying_table,
    s3_top20_rows, s3_top20_prod_rows,
    s4_shop_channels, s4_ziying_channels,
    s4_tianma_data, s4_feed_data,
    s5_overall_rows, s5_shop_rows, s5_ziying_rows
)

# 解包结论
s1_gmv_conclusion = conclusions['s1_gmv']
s1_order_conclusion = conclusions['s1_order']
s1_buyer_conclusion = conclusions['s1_buyer']
s1_ctr_conclusion = conclusions['s1_ctr']
s1_cvr_conclusion = conclusions['s1_cvr']
s1_gpm_conclusion = conclusions['s1_gpm']
s2_shop_conclusion = conclusions['s2_shop']
s2_ziying_conclusion = conclusions['s2_ziying']
s3_merchant_conclusion = conclusions['s3_merchant']
s3_product_conclusion = conclusions['s3_product']
s4_traffic_conclusion = conclusions['s4_traffic']
s4_shop_traffic_conclusion = conclusions['s4_shop_traffic']
s4_channel_conclusion = conclusions['s4_channel']
s5_overall_conclusion = conclusions['s5_overall']
s5_shop_conclusion = conclusions['s5_shop']
s5_ziying_conclusion = conclusions['s5_ziying']

# BIZ 颜色类
BIZ_COLOR = {'小店': 'green', '自营': '', '工坊': 'amber', '票务': 'blue'}

HTML_PARTS = []

# ── HEADER ──
HTML_PARTS.append(f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>交易业务周报 W{CUR_W}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">

<div class="hero">
  <p class="hero-eyebrow">交易业务周报</p>
  <h1>W{CUR_W} 整体数据概览</h1>
  <p class="hero-desc">内容电商平台交易业务数据分析 · {datetime.now().strftime("%Y年%m月%d日")}</p>
  <div class="hero-meta">
    <span class="hero-badge">周期 W{CUR_W}（4月10日～4月16日）</span>
    <span class="hero-badge">对比 W{PREV_W}</span>
    <span class="hero-badge">5大栏目全量分析</span>
  </div>
</div>

<nav class="nav">
  <a href="#s1">① 核心数据趋势</a>
  <a href="#s2">② 行业拆解</a>
  <a href="#s3">③ 小店商家拆解</a>
  <a href="#s4">④ 流量渠道</a>
  <a href="#s5">⑤ 内容类型</a>
</nav>
''')

# ── S1 ─────────────────────────────────────────────────────────────────────────
HTML_PARTS.append(f'''
<section id="s1" class="section">
<div class="section-head">
  <div>
    <p class="section-num">S1</p>
    <h2>核心数据趋势</h2>
    <p class="section-desc">各业务线 GMV 规模变化趋势及核心效率指标</p>
  </div>
</div>
''')

# S1 指标卡 + 图表（按业务线）
for biz in BIZES:
    m = s1_metrics[biz]
    color = BIZ_COLOR.get(biz, '')
    ratio_txt = ''
    if biz == '小店':
        ratio_cur = get_ctrl_ratio(df1, CUR_W)
        ratio_prev = get_ctrl_ratio(df1, PREV_W) if PREV_W else 0
        ratio_wow = wow_pct(ratio_cur, ratio_prev)
        ratio_txt = f'<div class="metric-card"><p class="metric-label">小店对自营控比</p><p class="metric-value">{ratio_cur:.2f}x</p><p class="metric-sub"><span class="delta {ratio_wow["cls"]}">{ratio_wow["text"]}</span></p></div>'
    
    HTML_PARTS.append(f'''
<div class="breakdown-block">
<div class="breakdown-head">
  <h3 style="color:var(--{"up" if biz=="小店" else "warn" if biz=="工坊" else "info" if biz=="票务" else "accent"})">{biz} <span>W{CUR_W} 核心指标</span></h3>
</div>
<div class="metric-grid">
  <div class="metric-card {color}">
    <p class="metric-label">GMV</p>
    <p class="metric-value">{fmt_gmv(m["GMV"])}</p>
    <p class="metric-sub"><span class="delta {m["GMV_wow"]["cls"]}">{m["GMV_wow"]["text"]}</span></p>
  </div>
  <div class="metric-card">
    <p class="metric-label">买家数</p>
    <p class="metric-value">{fmt_num(m["买家数"])}</p>
    <p class="metric-sub"><span class="delta {m["买家数_wow"]["cls"]}">{m["买家数_wow"]["text"]}</span></p>
  </div>
  <div class="metric-card">
    <p class="metric-label">订单数</p>
    <p class="metric-value">{fmt_num(m["订单数"])}</p>
    <p class="metric-sub"><span class="delta {m["订单数_wow"]["cls"]}">{m["订单数_wow"]["text"]}</span></p>
  </div>
  <div class="metric-card">
    <p class="metric-label">曝光PV</p>
    <p class="metric-value">{fmt_num(m["曝光PV"])}</p>
    <p class="metric-sub"><span class="delta {m["曝光PV_wow"]["cls"]}">{m["曝光PV_wow"]["text"]}</span></p>
  </div>
  <div class="metric-card">
    <p class="metric-label">CTR（点击率）</p>
    <p class="metric-value">{fmt_pct(m["CTR"])}</p>
    <p class="metric-sub"><span class="delta {m["CTR_wow"]["cls"]}">{m["CTR_wow"]["text"]}</span></p>
  </div>
  <div class="metric-card">
    <p class="metric-label">支付转化率</p>
    <p class="metric-value">{fmt_pct(m["CVR"])}</p>
    <p class="metric-sub"><span class="delta {m["CVR_wow"]["cls"]}">{m["CVR_wow"]["text"]}</span></p>
  </div>
  <div class="metric-card">
    <p class="metric-label">GPM</p>
    <p class="metric-value">{fmt_gmv(m["GPM"])}</p>
    <p class="metric-sub"><span class="delta {m["GPM_wow"]["cls"]}">{m["GPM_wow"]["text"]}</span></p>
  </div>
  {ratio_txt}
</div>
</div>
''')

# S1 图表：GMV 周趋势（柱状图）
HTML_PARTS.append(f'''
<div class="grid-2" style="margin-top:16px">
  <div class="chart-container">
    <figcaption>各业务线 GMV 周趋势</figcaption>
    <div class="chart-area"><canvas id="chart-s1-gmv"></canvas></div>
  </div>
  <div class="chart-container">
    <figcaption>小店对自营控比 周趋势</figcaption>
    <div class="chart-area"><canvas id="chart-s1-ratio"></canvas></div>
  </div>
</div>

<div class="grid-2" style="margin-top:16px">
  <div class="chart-container">
    <figcaption>各业务线 买家数 周趋势</figcaption>
    <div class="chart-area"><canvas id="chart-s1-buyer"></canvas></div>
  </div>
  <div class="chart-container">
    <figcaption>各业务线 点击率(CTR) 周趋势</figcaption>
    <div class="chart-area"><canvas id="chart-s1-ctr"></canvas></div>
  </div>
</div>

<div class="grid-2" style="margin-top:16px">
  <div class="chart-container">
    <figcaption>各业务线 支付转化率(CVR) 周趋势</figcaption>
    <div class="chart-area"><canvas id="chart-s1-cvr"></canvas></div>
  </div>
  <div class="chart-container">
    <figcaption>各业务线 GPM 周趋势</figcaption>
    <div class="chart-area"><canvas id="chart-s1-gpm"></canvas></div>
  </div>
</div>
''')

# S1 数据表（各业务线指标汇总，4周对比）
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">各业务线周数据汇总表</h3>
<div class="table-wrap">
<table>
<thead><tr>
  <th>业务线</th>
  {"".join(f'<th class="num">W{int(w)}</th><th class="num">环比</th>' for w in WEEKS[:4])}
</tr></thead>
<tbody>
''')

for biz in BIZES:
    HTML_PARTS.append(f'<tr><td style="font-weight:600">{biz}</td>')
    for i, w in enumerate(WEEKS[:4]):
        gmv_c = safe_float(df1[(df1['周五-周四周']==w)&(df1['业务线二级']==biz)]['GMV'].sum())
        gmv_p = safe_float(df1[(df1['周五-周四周']==WEEKS[i+1])&(df1['业务线二级']==biz)]['GMV'].sum()) if i+1 < len(WEEKS) else 0
        wow = wow_pct(gmv_c, gmv_p)
        HTML_PARTS.append(f'<td class="num">{fmt_gmv(gmv_c)}</td><td class="num">{fmt_wow_tag(wow)}</td>')
    HTML_PARTS.append('</tr>')

HTML_PARTS.append('</tbody></table></div>')

# S1 MTD 表
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店 / 自营 月度 MTD（4月累计）</h3>
<div class="table-wrap">
<table>
<thead><tr>
  <th>业务线</th><th class="num">4月 MTD GMV</th><th class="num">YOY</th>
</tr></thead>
<tbody>
<tr><td style="font-weight:600">小店</td><td class="num">{fmt_gmv(s1_mtd["小店"]["MTD_GMV"])}</td><td class="num text-muted">暂无同期数据</td></tr>
<tr><td style="font-weight:600">自营</td><td class="num">{fmt_gmv(s1_mtd["自营"]["MTD_GMV"])}</td><td class="num text-muted">暂无同期数据</td></tr>
</tbody>
</table>
</div>

<!-- S1 结论 -->
<div class="conclusion">
  <h4>📊 结论解读</h4>
  <ul>
    <li><strong>GMV 波动：</strong>{s1_gmv_conclusion}</li>
    <li><strong>订单数：</strong>{s1_order_conclusion}</li>
    <li><strong>买家数：</strong>{s1_buyer_conclusion}</li>
    <li><strong>点击率(CTR)：</strong>{s1_ctr_conclusion}</li>
    <li><strong>支付转化率(CVR)：</strong>{s1_cvr_conclusion}</li>
    <li><strong>GPM：</strong>{s1_gpm_conclusion}</li>
  </ul>
</div>
</section>
''')

# ── S2 ─────────────────────────────────────────────────────────────────────────
HTML_PARTS.append(f'''
<section id="s2" class="section">
<div class="section-head">
  <div>
    <p class="section-num">S2</p>
    <h2>by 行业拆解</h2>
    <p class="section-desc">自营和小店各行业及分类的 GMV 变化趋势</p>
  </div>
</div>

<!-- 折线图1：整体行业GMV周变化 -->
<div class="chart-container">
  <figcaption>整体（小店+自营）各行业 GMV 周变化</figcaption>
  <div class="chart-area chart-area-lg"><canvas id="chart-s2-all"></canvas></div>
</div>

<!-- 数据表1：整体行业及分类 -->
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">整体（小店+自营）行业数据表</h3>
<div class="table-wrap">
<table>
<thead><tr>
  <th>行业 / 分类</th>
  <th class="num">W{CUR_W} GMV</th>
  <th class="num">W{PREV_W} GMV</th>
  <th class="num">周环比</th>
  <th class="num">买家数</th><th class="num">环比</th>
  <th class="num">订单数</th><th class="num">环比</th>
  <th class="num">GPM</th><th class="num">环比</th>
</tr></thead>
<tbody>
''')

# 整体 = 小店+自营合并显示
all_rows = []
for row in s2_shop_table:
    all_rows.append({**row, 'name': '小店-' + row['name'] if row['type'] == 'industry' else row['name']})
for row in s2_ziying_table:
    all_rows.append({**row, 'name': '自营-' + row['name'] if row['type'] == 'industry' else row['name']})

for row in all_rows:
    is_ind = row['type'] == 'industry'
    cls_attr = ' style="font-weight:600;background:rgba(255,255,255,0.03)"' if is_ind else ' class="sub-row"'
    prefix = '' if is_ind else '└ '
    wow = row['GMV_wow']
    if wow['cls'] != '' and wow['value'] != 0:
        p_gmv = row['GMV'] / (1 + wow['value']/100) if (1 + wow['value']/100) != 0 else 0
    else:
        p_gmv = 0
    
    HTML_PARTS.append(f'''<tr{cls_attr}>
  <td>{prefix}{row["name"]}</td>
  <td class="num">{fmt_gmv(row["GMV"])}</td>
  <td class="num">{fmt_gmv(p_gmv) if p_gmv > 0 else "-"}</td>
  <td class="num">{fmt_wow_tag(row["GMV_wow"])}</td>
  <td class="num">{fmt_num(row["买家数"])}</td>
  <td class="num">{fmt_wow_tag(row["买家数_wow"])}</td>
  <td class="num">{fmt_num(row["订单数"])}</td>
  <td class="num">{fmt_wow_tag(row["订单数_wow"])}</td>
  <td class="num">{fmt_gmv(row["GPM"])}</td>
  <td class="num">{fmt_wow_tag(row["GPM_wow"])}</td>
</tr>''')

HTML_PARTS.append('</tbody></table></div>')

# S2 小店
HTML_PARTS.append(f'''
<!-- 折线图2：小店GMV周变化 -->
<div class="chart-container" style="margin-top:24px">
  <figcaption>小店各行业 GMV 周变化</figcaption>
  <div class="chart-area chart-area-lg"><canvas id="chart-s2-shop"></canvas></div>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店 行业 + 分类数据表</h3>
<div class="table-wrap">
<table>
''')
HTML_PARTS.append(ind_table_html(s2_shop_table))
HTML_PARTS.append('</table></div>')

# S2 自营
HTML_PARTS.append(f'''
<!-- 折线图3：自营GMV周变化 -->
<div class="chart-container" style="margin-top:24px">
  <figcaption>自营各行业 GMV 周变化</figcaption>
  <div class="chart-area"><canvas id="chart-s2-ziying"></canvas></div>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">自营 行业 + 分类数据表</h3>
<div class="table-wrap">
<table>
''')
HTML_PARTS.append(ind_table_html(s2_ziying_table))
HTML_PARTS.append('</table></div>')

# S2 MTD表
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店 / 自营 分行业 MTD（4月累计）</h3>
<div class="table-wrap">
<table>
<thead><tr>
  <th>业务线</th><th>行业</th><th class="num">4月 MTD GMV</th><th class="num">YOY</th>
</tr></thead>
<tbody>
''')
for ind, gmv in s2_mtd_shop.items():
    HTML_PARTS.append(f'<tr><td>小店</td><td>{ind}</td><td class="num">{fmt_gmv(gmv)}</td><td class="num text-muted">暂无同期数据</td></tr>')
for ind, gmv in s2_mtd_ziying.items():
    HTML_PARTS.append(f'<tr><td>自营</td><td>{ind}</td><td class="num">{fmt_gmv(gmv)}</td><td class="num text-muted">暂无同期数据</td></tr>')
HTML_PARTS.append('</tbody></table></div>')

# S2 结论
HTML_PARTS.append(f"""
<div class="conclusion">
  <h4>📊 结论解读</h4>
  <ul>
    <li><strong>小店 GMV 波动：</strong>{s2_shop_conclusion}</li>
    <li><strong>自营 GMV 波动：</strong>{s2_ziying_conclusion}</li>
  </ul>
</div>
</section>""")

# ── S3 ─────────────────────────────────────────────────────────────────────────
HTML_PARTS.append(f'''
<section id="s3" class="section">
<div class="section-head">
  <div>
    <p class="section-num">S3</p>
    <h2>by 小店商家拆解</h2>
    <p class="section-desc">小店各行业商家交易规模变化趋势，GMV 波动归因</p>
  </div>
</div>

<!-- 折线图：Top10商家 GMV 周趋势 -->
<div class="chart-container">
  <figcaption>W{CUR_W} GMV Top10 商家 周趋势</figcaption>
  <div class="chart-area chart-area-lg"><canvas id="chart-s3-top10"></canvas></div>
</div>

<!-- 数据表1：整体 Top20 商家 -->
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">整体 Top20 商家明细（W{CUR_W} vs W{PREV_W}）</h3>
<div class="table-wrap">
<table>
''')
HTML_PARTS.append(merchant_table_html(s3_top20_rows, show_industry=True))
HTML_PARTS.append('</table></div>')

# 数据表2：分行业+分类 Top20
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">分行业 Top20 商家明细</h3>
''')
for ind in SHOP_INDUSTRIES:
    ind_cur = df2_shop[(df2_shop['周五-周四周'] == CUR_W) & (df2_shop['小店行业'] == ind)]
    ind_prev = df2_shop[(df2_shop['周五-周四周'] == PREV_W) & (df2_shop['小店行业'] == ind)] if PREV_W else pd.DataFrame()
    ind_total_gmv = safe_float(ind_cur['GMV'].sum())
    
    ind_cur_merch = agg_merchant(ind_cur)
    ind_top20 = ind_cur_merch.nlargest(min(20, len(ind_cur_merch)), 'GMV')
    ind_delta = ind_total_gmv - safe_float(ind_prev['GMV'].sum())
    ind_rows = build_merchant_rows(ind_top20, agg_merchant(ind_prev) if not ind_prev.empty else pd.DataFrame(), ind_total_gmv, ind_delta)
    
    HTML_PARTS.append(f'''
<div class="breakdown-block">
  <div class="breakdown-head"><h3>{ind} <span>{fmt_gmv(ind_total_gmv)}</span></h3></div>
  <div class="table-wrap"><table>
  ''')
    HTML_PARTS.append(merchant_table_html(ind_rows, show_industry=False))
    HTML_PARTS.append('</table></div></div>')

# 数据表3：商品明细 Top20
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">商品明细 Top20（W15+W16 日数据）</h3>
<div class="table-wrap">
<table>
''')
HTML_PARTS.append(product_table_html(s3_top20_prod_rows[:20]))
HTML_PARTS.append('</table></div>')

# S3 结论
HTML_PARTS.append(f"""
<div class="conclusion">
  <h4>📊 结论解读</h4>
  <ul>
    <li><strong>重点商家分析：</strong>{s3_merchant_conclusion}</li>
    <li><strong>重点商品分析：</strong>{s3_product_conclusion}</li>
  </ul>
</div>
</section>""")

# ── S4 ─────────────────────────────────────────────────────────────────────────
HTML_PARTS.append(f'''
<section id="s4" class="section">
<div class="section-head">
  <div>
    <p class="section-num">S4</p>
    <h2>by 流量渠道</h2>
    <p class="section-desc">小店和自营流量曝光波动及转化效率分析</p>
  </div>
</div>
{s4_data_notice}

<!-- 柱状图：整体/小店/自营 曝光PV -->
<div class="chart-container">
  <figcaption>整体 / 小店 / 自营 商品曝光 PV 周趋势</figcaption>
  <div class="chart-area"><canvas id="chart-s4-pv"></canvas></div>
</div>

<!-- 折线图：小店曝光占比 -->
<div class="chart-container" style="margin-top:16px">
  <figcaption>小店曝光PV占比（小店曝光PV / 总曝光PV）</figcaption>
  <div class="chart-area"><canvas id="chart-s4-pv-ratio"></canvas></div>
</div>

<!-- 数据表1：流量汇总（小店+自营） -->
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">流量汇总（小店 vs 自营，W{CUR_W}）</h3>
<div class="table-wrap">
<table>
<thead><tr>
  <th>维度</th>
  <th class="num">曝光PV</th><th class="num">流量占比</th><th class="num">环比</th>
  <th class="num">GMV</th><th class="num">GMV占比</th><th class="num">环比</th>
  <th class="num">CTR</th><th class="num">环比</th>
  <th class="num">CVR</th><th class="num">环比</th>
  <th class="num">GPM</th><th class="num">环比</th>
</tr></thead>
<tbody>
''')

tot_pv = s4_total_row['PV']
tot_gmv = s4_total_row['GMV']
for label, row in [('整体', s4_total_row), ('小店', s4_shop_row), ('自营', s4_ziying_row)]:
    pv_share = row['PV']/tot_pv*100 if tot_pv > 0 and label != '整体' else 100
    gmv_share = row['GMV']/tot_gmv*100 if tot_gmv > 0 and label != '整体' else 100
    HTML_PARTS.append(f'''<tr>
  <td style="font-weight:600">{label}</td>
  <td class="num">{fmt_num(row["PV"])}</td>
  <td class="num text-muted">{pv_share:.1f}%</td>
  <td class="num">{fmt_wow_tag(row["PV_wow"])}</td>
  <td class="num">{fmt_gmv(row["GMV"])}</td>
  <td class="num text-muted">{gmv_share:.1f}%</td>
  <td class="num">{fmt_wow_tag(row["GMV_wow"])}</td>
  <td class="num">{fmt_pct(row["CTR"])}</td>
  <td class="num">{fmt_wow_tag(row["CTR_wow"])}</td>
  <td class="num">{fmt_pct(row["CVR"])}</td>
  <td class="num">{fmt_wow_tag(row["CVR_wow"])}</td>
  <td class="num">{fmt_gmv(row["GPM"])}</td>
  <td class="num">{fmt_wow_tag(row["GPM_wow"])}</td>
</tr>''')

HTML_PARTS.append('</tbody></table></div>')

# 小店核心渠道 Top10
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店核心渠道 Top10（W{S4_CUR_W}，按GMV排序）</h3>
<div class="table-wrap"><table>
''')
HTML_PARTS.append(channel_table_html(s4_shop_channels, '资源位二级入口'))
HTML_PARTS.append('</table></div>')

# 自营核心渠道 Top10
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">自营核心渠道 Top10（W{S4_CUR_W}，按GMV排序）</h3>
<div class="table-wrap"><table>
''')
HTML_PARTS.append(channel_table_html(s4_ziying_channels, '资源位二级入口'))
HTML_PARTS.append('</table></div>')

# 小店行业流量表
HTML_PARTS.append(f'''
<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店分行业流量概况（W{CUR_W}）</h3>
<div class="table-wrap"><table>
<thead><tr>
  <th>行业</th>
  <th class="num">曝光PV</th><th class="num">流量占比</th><th class="num">环比</th>
  <th class="num">GMV</th><th class="num">GMV占比</th><th class="num">环比</th>
  <th class="num">CTR</th><th class="num">环比</th>
  <th class="num">CVR</th><th class="num">环比</th>
  <th class="num">GPM</th><th class="num">环比</th>
</tr></thead>
<tbody>
''')
for row in s4_shop_industry_rows:
    HTML_PARTS.append(f'''<tr>
  <td>{row["industry"]}</td>
  <td class="num">{fmt_num(row["PV"])}</td>
  <td class="num text-muted">{row["PV_share"]:.1f}%</td>
  <td class="num">{fmt_wow_tag(row["PV_wow"])}</td>
  <td class="num">{fmt_gmv(row["GMV"])}</td>
  <td class="num text-muted">{row["GMV_share"]:.1f}%</td>
  <td class="num">{fmt_wow_tag(row["GMV_wow"])}</td>
  <td class="num">{fmt_pct(row["CTR"])}</td>
  <td class="num">{fmt_wow_tag(row["CTR_wow"])}</td>
  <td class="num">{fmt_pct(row["CVR"])}</td>
  <td class="num">{fmt_wow_tag(row["CVR_wow"])}</td>
  <td class="num">{fmt_gmv(row["GPM"])}</td>
  <td class="num">{fmt_wow_tag(row["GPM_wow"])}</td>
</tr>''')
HTML_PARTS.append('</tbody></table></div>')

# 天马推荐商品卡
HTML_PARTS.append(f'''
<!-- 柱状图：天马推荐商品卡 小店 vs 自营 -->
<div class="chart-container" style="margin-top:24px">
  <figcaption>天马推荐商品卡 — 小店 vs 自营 曝光PV 周趋势</figcaption>
  <div class="chart-area"><canvas id="chart-s4-tianma"></canvas></div>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">天马推荐商品卡 周维度数据</h3>
<div class="table-wrap"><table>
''')
HTML_PARTS.append(special_channel_table_html(s4_tianma_data, TIANMA))
HTML_PARTS.append('</table></div>')

# 商城首页feed
HTML_PARTS.append(f'''
<!-- 柱状图：商城首页feed 小店 vs 自营 -->
<div class="chart-container" style="margin-top:24px">
  <figcaption>商城首页feed — 小店 vs 自营 曝光PV 周趋势</figcaption>
  <div class="chart-area"><canvas id="chart-s4-feed"></canvas></div>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">商城首页feed 周维度数据</h3>
<div class="table-wrap"><table>
''')
HTML_PARTS.append(special_channel_table_html(s4_feed_data, '商城首页feed'))
HTML_PARTS.append('</table></div>')

# S4 结论
HTML_PARTS.append(f"""
<div class="conclusion">
  <h4>📊 结论解读</h4>
  <ul>
    <li><strong>总流量波动：</strong>{s4_traffic_conclusion}</li>
    <li><strong>小店流量分析：</strong>{s4_shop_traffic_conclusion}</li>
    <li><strong>重点渠道归因：</strong>{s4_channel_conclusion}</li>
  </ul>
</div>
</section>""")

# S5 内容类型明细表格函数
def content_table_html(rows):
    """渲染内容类型明细表（含上周环比）"""
    html = '<thead><tr>'
    html += '<th>体裁</th>'
    html += f'<th class="num">W{CUR_W} GMV</th><th class="num">W{CUR_W}占比</th>'
    html += f'<th class="num">W{PREV_W} GMV</th><th class="num">W{PREV_W}占比</th>'
    html += '<th class="num">GMV环比</th><th class="num">占比变化</th>'
    html += '</tr></thead><tbody>'
    
    for row in rows:
        wow_cls = row['GMV_wow']['cls']
        share_cls = row['share_wow']['cls']
        html += f'<tr>'
        html += f'<td style="font-weight:600">{row["type"]}</td>'
        html += f'<td class="num">{fmt_gmv(row["GMV"])}</td>'
        html += f'<td class="num text-muted">{row["share"]:.1f}%</td>'
        html += f'<td class="num text-dim">{fmt_gmv(row["GMV_prev"])}</td>'
        html += f'<td class="num text-dim">{row.get("prev_share", 0):.1f}%</td>'
        wow_tag = f'<span class="tag tag-{wow_cls}">{row["GMV_wow"]["text"]}</span>' if wow_cls else row["GMV_wow"]["text"]
        html += f'<td class="num">{wow_tag}</td>'
        share_delta = f'{"+" if row["share_wow"]["value"] >= 0 else ""}{row["share_wow"]["value"]:.1f}pp'
        share_cls_css = 'up' if row["share_wow"]["value"] > 0 else ('down' if row["share_wow"]["value"] < 0 else '')
        html += f'<td class="num"><span class="delta {share_cls_css}">{share_delta}</span></td>'
        html += '</tr>'
    
    html += '</tbody>'
    return html

# ── S5 ─────────────────────────────────────────────────────────────────────────
HTML_PARTS.append(f'''
<section id="s5" class="section">
<div class="section-head">
  <div>
    <p class="section-num">S5</p>
    <h2>by 内容类型</h2>
    <p class="section-desc">不同体裁下的成交结构分布（W{CUR_W} vs W{PREV_W}）</p>
  </div>
</div>

<div class="grid-3">
  <div class="chart-container">
    <figcaption>整体成交结构</figcaption>
    <div class="pie-area"><canvas id="chart-s5-overall"></canvas></div>
  </div>
  <div class="chart-container">
    <figcaption>小店成交结构</figcaption>
    <div class="pie-area"><canvas id="chart-s5-shop"></canvas></div>
  </div>
  <div class="chart-container">
    <figcaption>自营成交结构</figcaption>
    <div class="pie-area"><canvas id="chart-s5-ziying"></canvas></div>
  </div>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">整体 体裁明细（W{CUR_W} vs W{PREV_W}）</h3>
<div class="table-wrap">
<table>
{content_table_html(s5_overall_rows)}
</table>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店 体裁明细（W{CUR_W} vs W{PREV_W}）</h3>
<div class="table-wrap">
<table>
{content_table_html(s5_shop_rows)}
</table>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">自营 体裁明细（W{CUR_W} vs W{PREV_W}）</h3>
<div class="table-wrap">
<table>
{content_table_html(s5_ziying_rows)}
</table>
</div>

<h3 style="margin:24px 0 8px;font-size:15px;color:var(--ink)">小店分行业成交体裁分布</h3>
<div class="grid-3" style="margin-top:12px">
''')

for ind in SHOP_INDUSTRIES:
    ind_data = s5_shop_by_ind[ind]
    HTML_PARTS.append(f'''
  <div class="chart-container">
    <figcaption>小店-{ind}</figcaption>
    <div class="pie-area"><canvas id="chart-s5-shop-{ind.replace("-","_").replace(" ","_")}"></canvas></div>
  </div>
''')

HTML_PARTS.append('</div>')

# S5 结论
HTML_PARTS.append(f"""
<div class="conclusion">
  <h4>📊 结论解读</h4>
  <ul>
    <li><strong>整体成交结构：</strong>{s5_overall_conclusion}</li>
    <li><strong>小店成交结构：</strong>{s5_shop_conclusion}</li>
    <li><strong>自营成交结构：</strong>{s5_ziying_conclusion}</li>
  </ul>
</div>
</section>""")

# ── FOOTNOTE ──
HTML_PARTS.append(f'''
<div class="footnote">
  <strong>数据说明</strong><br>
  · 时间周期：周五至周四（W{CUR_W} = 4月10日～4月16日，W{PREV_W} = 4月3日～4月9日）<br>
  · GMV = 支付销售额（不减退款）<br>
  · CTR = 商详曝光PV / 商品曝光PV &nbsp;·&nbsp; CVR = 支付订单数 / 商品曝光PV &nbsp;·&nbsp; GPM = GMV / 商品曝光PV × 1000<br>
  · 贡献率 = （商家本周GMV - 商家上周GMV）/ 本周整体GMV涨跌<br>
  · 周环比：上涨绿色，下跌红色（中国惯例）<br>
  · YOY 暂无历史同期数据<br>
  · 商品明细为日粒度，已按W16/W15自然周聚合
</div>
</div>
''')

# ── SCRIPTS ──
HTML_PARTS.append(f'''
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
{CHART_JS}

document.addEventListener('DOMContentLoaded', function() {{

  // S1 GMV 柱状图
  reportChart('chart-s1-gmv', chartPresets.bar(
    {json.dumps(WEEK_LABELS)},
    [
      {{ label: '小店', data: {json.dumps(s1_gmv_trend['小店'])} }},
      {{ label: '自营', data: {json.dumps(s1_gmv_trend['自营'])} }},
      {{ label: '工坊', data: {json.dumps(s1_gmv_trend['工坊'])} }},
      {{ label: '票务', data: {json.dumps(s1_gmv_trend['票务'])} }}
    ],
    {{ yFormat: 'gmv' }}
  ));

  // S1 控比折线图
  reportChart('chart-s1-ratio', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [{{ label: '小店/自营控比', data: {json.dumps(s1_ratio_trend)} }}],
    {{ chartOptions: {{ scales: {{ y: {{ ticks: {{ callback: function(v) {{ return v.toFixed(2) + 'x'; }} }} }} }} }} }}
  ));

  // S1 买家数柱状图
  reportChart('chart-s1-buyer', chartPresets.bar(
    {json.dumps(WEEK_LABELS)},
    [
      {{ label: '小店', data: {json.dumps(s1_buyer_trend['小店'])} }},
      {{ label: '自营', data: {json.dumps(s1_buyer_trend['自营'])} }},
      {{ label: '工坊', data: {json.dumps(s1_buyer_trend['工坊'])} }},
      {{ label: '票务', data: {json.dumps(s1_buyer_trend['票务'])} }}
    ],
    {{ yFormat: 'num' }}
  ));

  // S1 CTR 折线图
  reportChart('chart-s1-ctr', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {{ label: '小店', data: {json.dumps(s1_ctr_trend['小店'])} }},
      {{ label: '自营', data: {json.dumps(s1_ctr_trend['自营'])} }},
      {{ label: '工坊', data: {json.dumps(s1_ctr_trend['工坊'])} }},
      {{ label: '票务', data: {json.dumps(s1_ctr_trend['票务'])} }}
    ],
    {{ yFormat: 'pct' }}
  ));

  // S1 CVR 折线图
  reportChart('chart-s1-cvr', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {{ label: '小店', data: {json.dumps(s1_cvr_trend['小店'])} }},
      {{ label: '自营', data: {json.dumps(s1_cvr_trend['自营'])} }},
      {{ label: '工坊', data: {json.dumps(s1_cvr_trend['工坊'])} }},
      {{ label: '票务', data: {json.dumps(s1_cvr_trend['票务'])} }}
    ],
    {{ yFormat: 'pct' }}
  ));

  // S1 GPM 折线图
  reportChart('chart-s1-gpm', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {{ label: '小店', data: {json.dumps(s1_gpm_trend['小店'])} }},
      {{ label: '自营', data: {json.dumps(s1_gpm_trend['自营'])} }},
      {{ label: '工坊', data: {json.dumps(s1_gpm_trend['工坊'])} }},
      {{ label: '票务', data: {json.dumps(s1_gpm_trend['票务'])} }}
    ],
    {{ yFormat: 'gmv' }}
  ));

  // S2 整体行业折线图
  reportChart('chart-s2-all', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {",".join(f'{{ label: "小店-{ind}", data: {json.dumps(s2_shop_ind_gmv[ind])} }}' for ind in SHOP_INDUSTRIES)},
      {",".join(f'{{ label: "自营-{ind}", data: {json.dumps(s2_ziying_ind_gmv[ind])} }}' for ind in ZIYING_INDUSTRIES)}
    ],
    {{ yFormat: 'gmv' }}
  ));

  // S2 小店行业折线图
  reportChart('chart-s2-shop', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {",".join(f'{{ label: "{ind}", data: {json.dumps(s2_shop_ind_gmv[ind])} }}' for ind in SHOP_INDUSTRIES)}
    ],
    {{ yFormat: 'gmv' }}
  ));

  // S2 自营行业折线图
  reportChart('chart-s2-ziying', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {",".join(f'{{ label: "{ind}", data: {json.dumps(s2_ziying_ind_gmv[ind])} }}' for ind in ZIYING_INDUSTRIES)}
    ],
    {{ yFormat: 'gmv' }}
  ));

  // S3 Top10 商家趋势折线图
  reportChart('chart-s3-top10', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [
      {",".join(f'{{ label: {json.dumps(n)}, data: {json.dumps(s3_top10_trend[n])} }}' for n in top10_names[:10])}
    ],
    {{ yFormat: 'gmv' }}
  ));

  // S4 PV 柱状图
  reportChart('chart-s4-pv', chartPresets.bar(
    {json.dumps(WEEK_LABELS)},
    [
      {{ label: '整体', data: {json.dumps(s4_pv_total)} }},
      {{ label: '小店', data: {json.dumps(s4_pv_shop)} }},
      {{ label: '自营', data: {json.dumps(s4_pv_ziying)} }}
    ],
    {{ yFormat: 'pv' }}
  ));

  // S4 PV占比折线图
  reportChart('chart-s4-pv-ratio', chartPresets.line(
    {json.dumps(WEEK_LABELS)},
    [{{ label: '小店曝光占比%', data: {json.dumps(tol(s4_shop_pv_ratio))} }}],
    {{ yFormat: 'pct' }}
  ));

  // S4 天马 柱状图
  reportChart('chart-s4-tianma', chartPresets.bar(
    {json.dumps(S4_SPECIAL_LABELS)},
    [
      {{ label: '整体曝光PV', data: {json.dumps(s4_tianma_pv_total)} }},
      {{ label: '小店曝光PV', data: {json.dumps(s4_tianma_pv_shop)} }},
      {{ label: '自营曝光PV', data: {json.dumps(s4_tianma_pv_zy)} }}
    ],
    {{ yFormat: 'pv' }}
  ));

  // S4 商城feed 柱状图
  reportChart('chart-s4-feed', chartPresets.bar(
    {json.dumps(S4_SPECIAL_LABELS)},
    [
      {{ label: '整体曝光PV', data: {json.dumps(s4_feed_pv_total)} }},
      {{ label: '小店曝光PV', data: {json.dumps(s4_feed_pv_shop)} }},
      {{ label: '自营曝光PV', data: {json.dumps(s4_feed_pv_zy)} }}
    ],
    {{ yFormat: 'pv' }}
  ));

  // S5 整体饼图
  reportChart('chart-s5-overall', chartPresets.doughnut(
    {json.dumps([k for k,v in s5_overall.items() if v > 0])},
    {json.dumps([float(v) for k,v in s5_overall.items() if v > 0])}
  ));

  // S5 小店饼图
  reportChart('chart-s5-shop', chartPresets.doughnut(
    {json.dumps([k for k,v in s5_shop.items() if v > 0])},
    {json.dumps([float(v) for k,v in s5_shop.items() if v > 0])}
  ));

  // S5 自营饼图
  reportChart('chart-s5-ziying', chartPresets.doughnut(
    {json.dumps([k for k,v in s5_ziying.items() if v > 0])},
    {json.dumps([float(v) for k,v in s5_ziying.items() if v > 0])}
  ));

  // S5 小店分行业饼图
''')

for ind in SHOP_INDUSTRIES:
    ind_data = s5_shop_by_ind[ind]
    ind_id = ind.replace('-','_').replace(' ','_')
    labels = [k for k, v in ind_data.items() if v > 0]
    vals = [float(v) for k, v in ind_data.items() if v > 0]
    HTML_PARTS.append(f'''  reportChart('chart-s5-shop-{ind_id}', chartPresets.doughnut(
    {json.dumps(labels)},
    {json.dumps(vals)}
  ));
''')

HTML_PARTS.append('''
});
</script>
</body>
</html>
''')

# ── 写出文件 ──
html_content = '\n'.join(HTML_PARTS)
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"[✓] 报告已生成: {OUTPUT_PATH}")
print(f"[✓] 文件大小: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")
