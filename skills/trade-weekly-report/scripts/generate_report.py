#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易业务周报生成器 v2.0
========================
用法:
    python generate_report.py                    # 文件在当前目录
    python generate_report.py --dir data/        # 指定数据目录
    python generate_report.py -o 本周周报.html    # 指定输出名

输入文件（放同一目录）:
    ① 整体数据*.xlsx                    → S1核心趋势
    ② 区分行业*.xlsx                    → S2行业拆解 + S3商家拆解
    ③ 分行业x流量渠道*.xlsx              → S4流量渠道
    ④ 分行业x内容类型*.xlsx              → S5成交体裁
    ⑤ 商品x流量渠道x商家x经营类目x商品类目*.xlsx → S4爆品归因
    ⑥ 商品x体裁x商家x经营类目x商品类目*.xlsx     → S5爆品归因
    ⑦ 头部UPlist.xlsx                   → 加林行业识别（一般不更新）

输出:  交易业务周报_W{周号}.html
"""

import argparse, glob, json, os, sys, time
from datetime import date, timedelta
import numpy as np
import pandas as pd

# ════════════════════════════════════════════════
# 行业分类
# ════════════════════════════════════════════════

INDUSTRIES = ['ACG-南征', 'ACG-Allen', '非ACG-悟饭', '非ACG-加林', '其他']
CAT_MAP = {
    'ACG-南征':   ['硬周', '游戏虚拟', '出版物'],
    'ACG-Allen':  ['软周', '盲盒'],
    '非ACG-悟饭': ['珠宝文玩', '组装机', '兴趣手作', '卡牌'],
    '非ACG-加林': ['头部UP'],
    '其他':       ['其他'],
}

# 兴趣手作扩展口径：特色手工艺、母婴萌宠、智能家居、文创礼品
XINGQU_B1 = {'特色手工/艺术品', '艺术品/工业品/非遗', '母婴宠物', '智能家居',
              '礼品文创', '礼品箱包', '玩具乐器/宠物生活', '母婴/食品饮料/酒类'}

# 统一ID列候选（交易明细与UP名单）
DATA_ID_COLS = ['商家ID', '商家id', '商户id', '店铺id', '店铺ID']
UPLIST_ID_COLS = ['店铺id', '店铺ID', '商家ID', '商家id', 'up_mid', 'UP_MID', 'upmid']


def _norm_key(v):
    return str(v).strip().lower().replace('_', '').replace(' ', '')


def _norm_id(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return s.lower()


def find_col(df, candidates):
    if len(df) == 0:
        return None
    cols = list(df.columns)
    for c in candidates:
        if c in cols:
            return c
    cmap = {_norm_key(c): c for c in cols}
    for c in candidates:
        hit = cmap.get(_norm_key(c))
        if hit:
            return hit
    return None


def log(level, msg, **kwargs):
    extra = ""
    if kwargs:
        extra = " | " + " ".join(f"{k}={v}" for k, v in kwargs.items())
    print(f"[{level}] {msg}{extra}", flush=True)


def format_cols(cols, limit=8):
    vals = [str(c) for c in cols]
    if len(vals) <= limit:
        return vals
    return vals[:limit] + [f"...(+{len(vals)-limit})"]


def classify_vec(df, up_ids=None, has_b1=True, has_b3=False, has_mid=False):
    """
    向量化行业分类。
    参数控制哪些字段可用（不同文件字段不同）。
    """
    c1 = df['经营一级类目名称'].fillna('') if '经营一级类目名称' in df.columns else pd.Series('', index=df.index)
    # 有些文件叫'商品一级经营类目'
    if c1.eq('').all() and '商品一级经营类目' in df.columns:
        c1 = df['商品一级经营类目'].fillna('')

    ind = pd.Series('其他', index=df.index)
    cat = pd.Series('其他', index=df.index)

    # 经营一级类目分类
    for val, i, c in [('硬周', 'ACG-南征', '硬周'), ('虚拟卡券', 'ACG-南征', '游戏虚拟'),
                       ('出版物', 'ACG-南征', '出版物'), ('软周', 'ACG-Allen', '软周'),
                       ('赏类', 'ACG-Allen', '盲盒'), ('电脑', '非ACG-悟饭', '组装机')]:
        m = c1 == val; ind[m] = i; cat[m] = c

    # 后台类目分类（珠宝文玩、兴趣手作）
    if has_b1:
        # 尝试 后台一级 → 后台二级 → 一级类目
        b1_col = None
        for col in ['后台一级类目名称', '后台二级类目名称', '一级类目']:
            if col in df.columns:
                b1_col = col; break
        if b1_col:
            b1 = df[b1_col].fillna('')
            m = b1.str.contains('珠宝文玩', na=False)
            ind[m] = '非ACG-悟饭'; cat[m] = '珠宝文玩'
            m = b1.isin(XINGQU_B1)
            ind[m] = '非ACG-悟饭'; cat[m] = '兴趣手作'
            # 后台二级中可能直接包含关键词
            m = b1.str.contains('手工|手作|母婴|宠物|智能家居|礼品|文创', na=False, regex=True)
            still_other = (ind == '其他')
            ind[m & still_other] = '非ACG-悟饭'; cat[m & still_other] = '兴趣手作'
            # 商品数据的一级类目映射
            if b1_col == '一级类目':
                m = b1.isin(['手办', '模型', '兵人', '雕像', '模玩配件', '娃娃'])
                ind[m] = 'ACG-南征'; cat[m] = '硬周'
                m = b1.isin(['游戏3C数码']); ind[m] = 'ACG-南征'; cat[m] = '游戏虚拟'
                m = b1.isin(['图书教育']); ind[m] = 'ACG-南征'; cat[m] = '出版物'
                m = b1.isin(['IP周边', '元素服饰', '创新类目', 'IP衍生商品（旧）'])
                ind[m] = 'ACG-Allen'; cat[m] = '软周'
                m = b1.isin(['惊喜赏', '吃谷机']); ind[m] = 'ACG-Allen'; cat[m] = '盲盒'
                m = b1 == '珠宝文玩'; ind[m] = '非ACG-悟饭'; cat[m] = '珠宝文玩'
                m = b1.isin(['电脑、办公']); ind[m] = '非ACG-悟饭'; cat[m] = '组装机'

    # 卡牌
    if has_b3:
        for col in ['后台三级类目名称', '三级类目']:
            if col in df.columns:
                m = df[col].fillna('').str.contains('卡牌', na=False)
                ind[m] = '非ACG-悟饭'; cat[m] = '卡牌'

    # 加林（优先按店铺ID/商家ID匹配头部UP名单）
    if up_ids and has_mid:
        mid_col = find_col(df, DATA_ID_COLS)
        if mid_col:
            is_up = df[mid_col].apply(lambda x: _norm_id(x) in up_ids)
            m = is_up & (ind == '其他')
            ind[m] = '非ACG-加林'; cat[m] = '头部UP'

    return ind, cat


# ════════════════════════════════════════════════
# 文件加载
# ════════════════════════════════════════════════

def find(pattern, dd):
    """通配符找文件，优先CSV"""
    for ext in ['.csv', '.xlsx', '.xls']:
        p = pattern.rsplit('.', 1)[0] + ext if '.' in pattern else pattern + ext
        ms = glob.glob(os.path.join(dd, p))
        if ms: return sorted(ms, key=os.path.getmtime, reverse=True)[0]
    ms = glob.glob(os.path.join(dd, pattern))
    return sorted(ms, key=os.path.getmtime, reverse=True)[0] if ms else None


def read(path):
    if not path: return pd.DataFrame()
    if path.endswith('.csv'): return pd.read_csv(path)
    return pd.read_excel(path)


def read_up_list(path):
    """稳健读取UP名单：支持店铺id/商家ID/up_mid，支持表头不在首行。"""
    if not path:
        return pd.DataFrame(), None
    # 尝试常规读取
    try:
        df = read(path)
    except Exception:
        df = pd.DataFrame()
    if len(df) > 0:
        df.columns = [str(c).strip() for c in df.columns]
        id_col = find_col(df, UPLIST_ID_COLS)
        if id_col:
            return df, id_col

    # 回退：无表头读取并自动探测表头行
    try:
        if path.endswith('.csv'):
            raw = pd.read_csv(path, header=None)
        else:
            raw = pd.read_excel(path, header=None)
    except Exception:
        return pd.DataFrame(), None
    if len(raw) == 0:
        return pd.DataFrame(), None

    hit_row = None
    for ri in range(min(8, len(raw))):
        vals = [_norm_key(v) for v in raw.iloc[ri].tolist()]
        if any(v in {_norm_key(c) for c in UPLIST_ID_COLS} for v in vals):
            hit_row = ri
            break
    if hit_row is None:
        return pd.DataFrame(), None

    cols = [str(c).strip() for c in raw.iloc[hit_row].tolist()]
    out = raw.iloc[hit_row + 1:].reset_index(drop=True).copy()
    out.columns = cols
    id_col = find_col(out, UPLIST_ID_COLS)
    return out, id_col


def log_df_contract(name, df, required_cols):
    present = set(df.columns)
    missing = [c for c in required_cols if c not in present]
    log(
        "INFO",
        f"{name}读取完成",
        rows=len(df),
        cols=len(df.columns),
        sample_cols=format_cols(df.columns),
        missing_required=missing if missing else "[]",
    )


def load_all(dd):
    print("📂 加载数据...\n")
    t0 = time.time()

    files = {
        '整体':     find('*整体数据*', dd),
        '行业':     find('*区分行业*', dd),
        '流量':     find('*分行业*流量*', dd),
        '体裁':     find('*分行业*内容*', dd),
        '商品流量':  find('*商品*流量*商家*', dd),
        '商品体裁':  find('*商品*体裁*商家*', dd),
        'UP':      find('*UPlist*', dd) or find('*uplist*', dd) or find('*UP*list*', dd) or find('头部UP*', dd),
    }
    expected_patterns = {
        '整体': '*整体数据*',
        '行业': '*区分行业*',
        '流量': '*分行业*流量*',
        '体裁': '*分行业*内容*',
        '商品流量': '*商品*流量*商家*',
        '商品体裁': '*商品*体裁*商家*',
        'UP': '*UP*list* / 头部UP*',
    }

    log("INFO", "文件扫描完成", input_dir=dd)

    for k, v in files.items():
        status = f"✓ {os.path.basename(v)}" if v else "⚠ 未找到"
        print(f"  {k:8s}: {status}")
        if v:
            log("INFO", f"{k}文件命中", pattern=expected_patterns.get(k, "-"), file=os.path.basename(v))
        else:
            log("WARN", f"{k}文件未命中", pattern=expected_patterns.get(k, "-"))

    dfs = {}
    for k, v in files.items():
        if k == 'UP' and v:
            df_up, id_col = read_up_list(v)
            if id_col:
                ids = {_norm_id(x) for x in df_up[id_col].dropna()}
                ids.discard(None)
                dfs['up_ids'] = ids
                print(f"  → UP名单ID列: {id_col}，ID数: {len(dfs['up_ids'])}个")
                log("INFO", "UP名单解析成功", id_col=id_col, id_count=len(dfs['up_ids']), sample_cols=format_cols(df_up.columns))
            else:
                print(f"  ⚠ UP文件中未找到可用ID列({UPLIST_ID_COLS}): {list(df_up.columns)}")
                dfs['up_ids'] = set()
                log("WARN", "UP名单解析失败", expected_id_cols=UPLIST_ID_COLS, actual_cols=format_cols(df_up.columns))
        elif v:
            dfs[k] = read(v)
            print(f"  → {k}: {len(dfs[k])}行")
            if k == '整体':
                log_df_contract(k, dfs[k], ['周五-周四周 ', '业务线二级', '商品曝光PV', '支付订单数', '支付订单买家数', 'GMV（不减退款）'])
            elif k == '行业':
                log_df_contract(k, dfs[k], ['周五-周四周 ', '业务线二级', '商家ID', '店铺名称', '经营一级类目名称', '商品曝光PV', '支付订单数', 'GMV（不减退款）'])
            elif k == '流量':
                log_df_contract(k, dfs[k], ['周五-周四周 ', '业务线二级', '资源位二级入口', '商家ID', '商品曝光PV', '支付订单数', 'GMV（不减退款）'])
            elif k == '体裁':
                log_df_contract(k, dfs[k], ['周五-周四周 ', '业务线二级', '内容类型', '商家ID', '商品曝光PV', '支付订单数', 'GMV（不减退款）'])
            else:
                log("INFO", f"{k}读取完成", rows=len(dfs[k]), cols=len(dfs[k].columns), sample_cols=format_cols(dfs[k].columns))
        else:
            dfs[k] = pd.DataFrame()
            log("WARN", f"{k}为空", reason="未匹配到文件")

    if 'up_ids' not in dfs:
        dfs['up_ids'] = set()

    # 校验
    if not dfs['up_ids']:
        print("\n  ⚠ 警告: 未加载到UP主ID，'非ACG-加林'行业将无法识别")
        print("    请确认UP名单文件存在且包含店铺id/商家ID/up_mid")
        log("WARN", "UP名单为空", impact="非ACG-加林识别失效")

    print(f"\n  加载耗时: {time.time()-t0:.1f}s")
    log("INFO", "文件加载完成", elapsed_sec=round(time.time() - t0, 2))
    return dfs


# ════════════════════════════════════════════════
# 统一列名
# ════════════════════════════════════════════════

COL_MAP = {
    'GMV（不减退款）': 'GMV', '商详支付转化率-UV': '商详转化率',
    '周五-周四周 ': '周', '周五-周四周': '周',
    '支付订单金额(元)': 'GMV', '商品GPM': 'GPM_raw',
    '商详-支付转化率-UV': '商详转化率', '商详UV': '商详PV',
}

def norm(df):
    if len(df) == 0:
        return df
    # 处理列名空格
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=COL_MAP)
    # 再次尝试带空格的版本
    for old, new in COL_MAP.items():
        stripped = old.strip()
        if stripped in df.columns and new not in df.columns:
            df = df.rename(columns={stripped: new})
    # 周编号统一为int
    if '周' in df.columns:
        df['周'] = pd.to_numeric(df['周'], errors='coerce').astype('Int64')
    # 计算缺失字段
    if 'GMV' not in df.columns:
        for col in df.columns:
            if 'GMV' in col or 'gmv' in col:
                df['GMV'] = df[col]; break
    if 'GPM' not in df.columns and 'GMV' in df.columns and '商品曝光PV' in df.columns:
        pv = df['商品曝光PV'].replace(0, np.nan)
        df['GPM'] = (df['GMV'] / pv * 1000).round(2)
    if '商品点击PV' not in df.columns and 'PVCTR' in df.columns and '商品曝光PV' in df.columns:
        df['商品点击PV'] = (df['商品曝光PV'] * df['PVCTR']).round(0)
    return df


# ════════════════════════════════════════════════
# 取最近N周
# ════════════════════════════════════════════════

def get_weeks(df, n=4):
    """从周编号取最近n周，返回排序列表（升序）和标签"""
    if '周' not in df.columns or df['周'].dropna().empty:
        return [], []
    wks = sorted(df['周'].dropna().unique())
    wks = [int(w) for w in wks]
    wks = wks[-n:]  # 最近4周
    labels = [f"W{w}" for w in wks]

    # 推算日期范围 (周五-周四，周编号=年内第N周)
    import datetime
    year = datetime.date.today().year
    for i, w in enumerate(wks):
        try:
            # 周编号→该年第w周的周五
            jan1 = datetime.date(year, 1, 1)
            # 找到第1个周五
            days_to_fri = (4 - jan1.weekday()) % 7
            first_fri = jan1 + datetime.timedelta(days=days_to_fri)
            wk_fri = first_fri + datetime.timedelta(weeks=w - 1)
            wk_thu = wk_fri + datetime.timedelta(days=6)
            tag = " ← 本周" if i == len(wks) - 1 else (" ← 上周" if i == len(wks) - 2 else "")
            print(f"    W{w}: {wk_fri}(Fri) ~ {wk_thu}(Thu){tag}")
        except:
            pass

    return wks, labels


# ════════════════════════════════════════════════
# 核心聚合
# ════════════════════════════════════════════════

R = lambda v: round(float(v), 2) if pd.notna(v) else 0

def agg(df):
    """对一个子集聚合所有指标"""
    pv = df['商品曝光PV'].sum() if '商品曝光PV' in df.columns else 0
    ck = df['商品点击PV'].sum() if '商品点击PV' in df.columns else 0
    sx = df['商详PV'].sum() if '商详PV' in df.columns else 0
    gmv = df['GMV'].sum() if 'GMV' in df.columns else 0
    o = df['支付订单数'].sum() if '支付订单数' in df.columns else 0
    b = df['支付订单买家数'].sum() if '支付订单买家数' in df.columns else 0
    return {
        'GMV': R(gmv), 'b': int(b), 'o': int(o), 'PV': int(pv),
        'GPM': R(gmv / pv * 1000) if pv else 0,
        'cv': R(o / pv * 100) if pv else 0,
        'CTR': R(ck / pv * 100) if pv else 0,
        'scv': R(o / sx * 100) if sx else 0,
    }


# ════════════════════════════════════════════════
# 处理各模块
# ════════════════════════════════════════════════

def process(dfs):
    print("\n📊 处理数据...")

    # ── 取周列表 ──
    df_main = norm(dfs['整体'])
    wks, wk_labels = get_weeks(df_main)
    # 备用: 从其他文件取周
    if not wks:
        for fallback_name in ['行业', '流量', '体裁']:
            fb = norm(dfs[fallback_name])
            if len(fb) > 0 and '周' in fb.columns:
                wks, wk_labels = get_weeks(fb)
                if wks:
                    print(f"  ⚠ 整体数据无周编号，从{fallback_name}文件获取: {wks}")
                    break
    if not wks:
        print("  ⚠ 未检测到任何周编号，报告将无数据")
        log("ERROR", "未检测到周编号", impact="报告将为空或仅骨架")
    print(f"  周编号: {wks} → {wk_labels}")
    W = wk_labels

    # 所有文件统一用最近4周
    df_ind = norm(dfs['行业'])
    df_flow = norm(dfs['流量'])
    df_type = norm(dfs['体裁'])
    df_gprod = norm(dfs['商品流量'])
    df_tprod = norm(dfs['商品体裁'])
    up_ids = dfs['up_ids']

    # 数据诊断
    print(f"\n  📋 数据诊断:")
    for name, df_chk in [('整体', df_main), ('行业', df_ind), ('流量', df_flow), ('体裁', df_type)]:
        if len(df_chk) == 0:
            print(f"    {name}: ⚠ 空数据")
            continue
        has_wk = '周' in df_chk.columns
        wk_vals = sorted(df_chk['周'].dropna().unique().tolist()) if has_wk else []
        has_biz = '业务线二级' in df_chk.columns
        biz_vals = df_chk['业务线二级'].dropna().unique().tolist() if has_biz else []
        cols_short = [c for c in df_chk.columns if c in ['周','业务线二级','GMV','商品曝光PV','资源位二级入口','内容类型','行业']]
        print(f"    {name}: {len(df_chk)}行, 周={wk_vals}, 业务线={biz_vals}, 关键列={cols_short}")
    print()

    # ── 分类 ──
    if len(df_ind) > 0:
        df_ind['行业'], df_ind['类目'] = classify_vec(df_ind, up_ids, has_b1=True, has_b3=False, has_mid=True)
    if len(df_flow) > 0:
        df_flow['行业'], df_flow['类目'] = classify_vec(df_flow, up_ids, has_b1=True, has_b3=False, has_mid=True)
    if len(df_type) > 0:
        df_type['行业'], df_type['类目'] = classify_vec(df_type, up_ids, has_b1=True, has_b3=False, has_mid=True)
    if len(df_gprod) > 0:
        df_gprod['行业'], df_gprod['类目'] = classify_vec(df_gprod, up_ids, has_b1=True, has_b3=False, has_mid=True)
    if len(df_tprod) > 0:
        df_tprod['行业'], df_tprod['类目'] = classify_vec(df_tprod, up_ids, has_b1=True, has_b3=False, has_mid=True)

    if len(df_ind) > 0 and '行业' in df_ind.columns:
        ind_cnt = df_ind['行业'].value_counts(dropna=False).to_dict()
        log("INFO", "行业分类分布", counts=ind_cnt)
        up_hit_rows = int((df_ind['类目'] == '头部UP').sum()) if '类目' in df_ind.columns else 0
        log("INFO", "头部UP命中", up_id_count=len(up_ids), matched_rows=up_hit_rows)

    # ── 行业keys ──
    all_keys = ['整体']
    for ind2 in INDUSTRIES:
        all_keys.append(ind2)
        for c in CAT_MAP[ind2]:
            all_keys.append('  ' + c)

    # ════════ S1: 核心趋势 ════════
    print("  → S1 核心趋势")
    s1 = {}
    for biz, key in [('小店', 'xd'), ('自营', 'zy')]:
        sub = df_main[df_main['业务线二级'] == biz] if '业务线二级' in df_main.columns else pd.DataFrame()
        s1[key] = [agg(sub[sub['周'] == w]) if '周' in sub.columns else agg(pd.DataFrame()) for w in wks]
    s1['r'] = [R(s1['xd'][i]['GMV'] / s1['zy'][i]['GMV'] * 100) if s1['zy'][i]['GMV'] else 0 for i in range(len(wks))]

    # ════════ S2: 行业拆解 ════════
    print("  → S2 行业拆解")

    def s2_calc(biz_filter=None):
        sub = df_ind
        if len(sub) == 0 or '周' not in sub.columns:
            return {}
        if biz_filter and '业务线二级' in sub.columns:
            sub = sub[sub['业务线二级'] == biz_filter]
        result = {}
        for wi, w in enumerate(wks):
            wd = sub[sub['周'] == w]
            result.setdefault('整体', []).append(agg(wd))
            for ind2 in INDUSTRIES:
                iw = wd[wd['行业'] == ind2]
                result.setdefault(ind2, []).append(agg(iw))
                for cat2 in CAT_MAP[ind2]:
                    cw = wd[wd['类目'] == cat2]
                    result.setdefault('  ' + cat2, []).append(agg(cw))
        return result

    s2_all = s2_calc()
    s2_xd = s2_calc('小店')
    s2_zy = s2_calc('自营')

    # 本周/上周编号（多处使用）
    w_this = wks[-1] if wks else None
    w_last = wks[-2] if len(wks) >= 2 else None

    # ── S2 归因: 行业波动拆解到商家 ──
    def s2_merchant_attribution():
        """对WoW>5%的行业/类目，找出贡献最大的商家"""
        result = {}
        if len(df_ind) == 0 or w_this is None: return result
        mid_col = '商家ID' if '商家ID' in df_ind.columns else None
        if not mid_col: return result
        for biz, bk in [('小店', 'xd'), ('自营', 'zy')]:
            biz_r = {}
            sub = df_ind[df_ind['业务线二级'] == biz] if '业务线二级' in df_ind.columns else pd.DataFrame()
            if len(sub) == 0: continue
            check_keys = []
            for ind2 in INDUSTRIES:
                check_keys.append((ind2, '行业', ind2))
                for cat2 in CAT_MAP[ind2]:
                    check_keys.append((f"{ind2}-{cat2}", '类目', cat2))
            for label, col_name, col_val in check_keys:
                isub = sub[sub[col_name] == col_val]
                w12 = isub[isub['周'] == w_this]
                w11 = isub[isub['周'] == w_last] if w_last else pd.DataFrame()
                g_cw = w12['GMV'].sum(); g_lw = w11['GMV'].sum() if len(w11) > 0 else 0
                if g_lw == 0: continue
                wow = (g_cw - g_lw) / g_lw * 100
                if abs(wow) < 5: continue
                # 按商家聚合
                g12 = w12.groupby([mid_col, '店铺名称']).agg(
                    {'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '商详PV': 'sum'}).reset_index()
                if len(w11) > 0:
                    g11 = w11.groupby([mid_col, '店铺名称']).agg(
                        {'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '商详PV': 'sum'}).reset_index()
                    mg = g12.merge(g11, on=[mid_col, '店铺名称'], suffixes=('_c', '_l'), how='outer').fillna(0)
                else:
                    mg = g12.copy()
                    for c2 in ['GMV', '商品曝光PV', '支付订单数', '商详PV']:
                        mg[c2 + '_c'] = mg[c2]; mg[c2 + '_l'] = 0
                mg['delta'] = mg['GMV_c'] - mg['GMV_l']
                top = mg.reindex(mg['delta'].abs().nlargest(3).index)
                ms = []
                for _, r2 in top.iterrows():
                    gw2 = R((r2['GMV_c'] - r2['GMV_l']) / r2['GMV_l'] * 100) if r2['GMV_l'] > 0 else 999
                    pw2 = R((r2['商品曝光PV_c'] - r2['商品曝光PV_l']) / r2['商品曝光PV_l'] * 100) if r2['商品曝光PV_l'] > 0 else 999
                    cc2 = R(r2['支付订单数_c'] / r2['商详PV_c'] * 100) if r2.get('商详PV_c', 0) > 0 else 0
                    cl2 = R(r2['支付订单数_l'] / r2['商详PV_l'] * 100) if r2.get('商详PV_l', 0) > 0 else 0
                    ms.append({'s': str(r2['店铺名称']), 'gd': R(r2['delta']),
                               'gc': R(r2['GMV_c']), 'gl': R(r2['GMV_l']),
                               'gw': min(gw2, 9999), 'pw': min(pw2, 9999), 'cc': cc2, 'cl': cl2})
                if ms:
                    biz_r[label] = {'wow': R(wow), 'gc': R(g_cw), 'gl': R(g_lw), 'ms': ms}
            result[bk] = biz_r
        return result
    s2_detail = s2_merchant_attribution()

    # Top products for归因
    def top_prods(df_goods, n=3):
        result = {}
        if len(df_goods) == 0: return result
        for ind2 in INDUSTRIES:
            for cat2 in CAT_MAP[ind2]:
                sub = df_goods[df_goods['类目'] == cat2]
                if len(sub) == 0: continue
                top = sub.nlargest(n, 'GMV')
                items = []
                for _, r in top.iterrows():
                    pname = str(r.get('商品名称', ''))
                    if not pname or pname == 'nan':
                        pid = str(r.get('商品id', ''))
                        pcat = str(r.get('一级类目', ''))
                        pname = f"商品{pid}" + (f"({pcat})" if pcat and pcat != 'nan' else '')
                    items.append({'n': pname[:30], 'g': R(r['GMV'])})
                if items:
                    result[f"{ind2}-{cat2}"] = items
        return result

    tp = top_prods(df_gprod, 3) if len(df_gprod) > 0 else top_prods(df_tprod, 3)

    # ════════ S3: 商家拆解 ════════
    print("  → S3 商家拆解")
    df_m_xd = df_ind[df_ind['业务线二级'] == '小店'] if len(df_ind) > 0 else pd.DataFrame()
    print(f"    小店行数: {len(df_m_xd)}, 本周={w_this}, 上周={w_last}")
    if len(df_m_xd) > 0 and w_this is not None:
        w_this_rows = len(df_m_xd[df_m_xd['周'] == w_this])
        print(f"    本周匹配: {w_this_rows}行")

    def top20_wow():
        if len(df_m_xd) == 0 or w_this is None: return []
        w12 = df_m_xd[df_m_xd['周'] == w_this]
        w11 = df_m_xd[df_m_xd['周'] == w_last] if w_last else pd.DataFrame()
        # 先按(商家ID, 店铺名称, 行业, 类目)聚合，避免同一商家多行导致计算偏差
        agg_cols = {'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '支付订单买家数': 'sum', '商详PV': 'sum'}
        if '商详转化率' in w12.columns: agg_cols['商详转化率'] = 'mean'
        if 'GPM' in w12.columns: agg_cols['GPM'] = 'mean'
        g12 = w12.groupby(['商家ID', '店铺名称', '行业', '类目']).agg(agg_cols).reset_index()
        top = g12.nlargest(20, 'GMV')
        # 上周也按商家+类目聚合
        if len(w11) > 0:
            g11 = w11.groupby(['商家ID', '店铺名称', '行业', '类目']).agg(agg_cols).reset_index()
        else:
            g11 = pd.DataFrame()
        result = []
        for _, r in top.iterrows():
            mid = r['商家ID']
            cat2 = r['类目']
            lw = g11[(g11['商家ID'] == mid) & (g11['类目'] == cat2)] if len(g11) > 0 else pd.DataFrame()
            lg = lw['GMV'].sum() if len(lw) > 0 else 0
            lp = int(lw['商品曝光PV'].sum()) if len(lw) > 0 else 0
            cp = int(r.get('商品曝光PV', 0))
            gw = R((r['GMV'] - lg) / lg * 100) if lg > 0 else 999
            pw = R((cp - lp) / lp * 100) if lp > 0 else 999
            # 贡献率 = (商家本周GMV - 商家上周GMV) / 该类目本周涨跌GMV
            cat_gmv_cw = g12[g12['类目'] == cat2]['GMV'].sum()
            cat_gmv_lw = g11[g11['类目'] == cat2]['GMV'].sum() if len(g11) > 0 else 0
            cat_delta = cat_gmv_cw - cat_gmv_lw
            contrib = R((r['GMV'] - lg) / cat_delta * 100) if cat_delta != 0 else 0
            result.append({
                's': str(r['店铺名称']), 'ind': r['行业'], 'cat': cat2,
                'mid': int(float(str(mid))) if pd.notna(mid) else 0,
                'g': R(r['GMV']), 'gl': R(lg), 'gw': gw,
                'b': int(r.get('支付订单买家数', 0)), 'o': int(r.get('支付订单数', 0)),
                'u': R(r['GMV'] / r['支付订单数']) if r.get('支付订单数', 0) > 0 else 0,
                'cv': R(r.get('商详转化率', 0) * 100) if pd.notna(r.get('商详转化率')) else 0,
                'gpm': R(r.get('GPM', 0)) if pd.notna(r.get('GPM')) else 0,
                'pv': cp, 'pvl': lp, 'pw': pw, 'ctr': contrib,
            })
        return result

    s3_top20 = top20_wow()

    # 分类目Top10
    s3_by_cat = {}
    for ind2 in INDUSTRIES:
        for cat2 in CAT_MAP[ind2]:
            if len(df_m_xd) == 0 or w_this is None: continue
            w12 = df_m_xd[df_m_xd['周'] == w_this]
            w11 = df_m_xd[df_m_xd['周'] == w_last] if w_last else pd.DataFrame()
            # 按商家聚合当前类目数据
            w12c = w12[w12['类目'] == cat2]
            if len(w12c) == 0: continue
            agg_cols = {'GMV': 'sum', '支付订单数': 'sum', '支付订单买家数': 'sum', '商详PV': 'sum', '商品曝光PV': 'sum'}
            if '商详转化率' in w12c.columns: agg_cols['商详转化率'] = 'mean'
            if 'GPM' in w12c.columns: agg_cols['GPM'] = 'mean'
            g12 = w12c.groupby(['商家ID', '店铺名称']).agg(agg_cols).reset_index()
            t = g12.nlargest(10, 'GMV')
            cat_gmv_cw = g12['GMV'].sum()
            w11c = w11[w11['类目'] == cat2] if len(w11) > 0 else pd.DataFrame()
            if len(w11c) > 0:
                g11 = w11c.groupby(['商家ID', '店铺名称']).agg(agg_cols).reset_index()
            else:
                g11 = pd.DataFrame()
            cat_gmv_lw = g11['GMV'].sum() if len(g11) > 0 else 0
            cat_delta = cat_gmv_cw - cat_gmv_lw
            items = []
            for _, r in t.iterrows():
                mid = r['商家ID']
                lw2 = g11[g11['商家ID'] == mid] if len(g11) > 0 else pd.DataFrame()
                lg = lw2['GMV'].sum() if len(lw2) > 0 else 0
                gw = R((r['GMV'] - lg) / lg * 100) if lg > 0 else 999
                contrib = R((r['GMV'] - lg) / cat_delta * 100) if cat_delta != 0 else 0
                items.append({
                    's': str(r['店铺名称']), 'g': R(r['GMV']), 'gw': gw,
                    'b': int(r.get('支付订单买家数', 0)), 'o': int(r.get('支付订单数', 0)),
                    'u': R(r['GMV'] / r['支付订单数']) if r.get('支付订单数', 0) > 0 else 0,
                    'cv': R(r.get('商详转化率', 0) * 100) if pd.notna(r.get('商详转化率')) else 0,
                    'gpm': R(r.get('GPM', 0)) if pd.notna(r.get('GPM')) else 0,
                    'ctr': contrib,
                })
            if items: s3_by_cat[f"{ind2}-{cat2}"] = items

    # 商家WoW波动分析
    def merchant_wow():
        results = {}
        if len(df_m_xd) == 0 or w_this is None: return results
        for ind2 in INDUSTRIES:
            for cat2 in CAT_MAP[ind2]:
                w12 = df_m_xd[(df_m_xd['周']==w_this)&(df_m_xd['类目']==cat2)]
                w11 = df_m_xd[(df_m_xd['周']==w_last)&(df_m_xd['类目']==cat2)] if w_last else pd.DataFrame()
                if len(w12) == 0: continue
                g12 = w12.groupby(['商家ID','店铺名称']).agg({'GMV':'sum','支付订单数':'sum','商品曝光PV':'sum','商详PV':'sum'}).reset_index()
                if len(w11) > 0:
                    g11 = w11.groupby(['商家ID','店铺名称']).agg({'GMV':'sum','支付订单数':'sum','商品曝光PV':'sum','商详PV':'sum'}).reset_index()
                    mg = g12.merge(g11, on=['商家ID','店铺名称'], suffixes=('_c','_l'), how='outer').fillna(0)
                else:
                    mg = g12.copy()
                    for col2 in ['GMV','支付订单数','商品曝光PV','商详PV']:
                        mg[col2+'_c']=mg[col2]; mg[col2+'_l']=0
                mg['gw']=mg.apply(lambda r2:R((r2['GMV_c']-r2['GMV_l'])/r2['GMV_l']*100) if r2['GMV_l']>0 else 999,axis=1)
                mg['pw']=mg.apply(lambda r2:R((r2['商品曝光PV_c']-r2['商品曝光PV_l'])/r2['商品曝光PV_l']*100) if r2['商品曝光PV_l']>0 else 999,axis=1)
                mg['cc']=mg.apply(lambda r2:R(r2['支付订单数_c']/r2['商详PV_c']*100) if r2['商详PV_c']>0 else 0,axis=1)
                mg['cl']=mg.apply(lambda r2:R(r2['支付订单数_l']/r2['商详PV_l']*100) if r2['商详PV_l']>0 else 0,axis=1)
                big=mg[(abs(mg['gw'])>5)&(mg['GMV_c']>0)].nlargest(5,'GMV_c')
                items=[{'s':str(r2['店铺名称']),'gc':R(r2['GMV_c']),'gl':R(r2['GMV_l']),
                    'gw':min(R(r2['gw']),9999),'pw':min(R(r2['pw']),9999),'cc':r2['cc'],'cl':r2['cl']}
                    for _,r2 in big.iterrows()]
                if items: results[f"{ind2}-{cat2}"]=items
        return results
    s3_wow = merchant_wow()

    # 商家趋势
    def merchant_trend():
        if len(df_m_xd) == 0 or w_this is None: return {}
        top_names = df_m_xd[df_m_xd['周']==w_this].nlargest(20,'GMV')['店铺名称'].tolist()
        trend_wks = wks[-3:] if len(wks)>=3 else wks
        result = {}
        for name in top_names:
            result[name] = [R(df_m_xd[(df_m_xd['周']==wk)&(df_m_xd['店铺名称']==name)]['GMV'].sum()) for wk in trend_wks]
        return result
    s3_trend = merchant_trend()

    # 爆品证据
    def merchant_prods():
        result = {}
        prod_df = df_gprod if len(df_gprod) > 0 else df_tprod
        if len(prod_df) == 0: return result
        prod_mid_col = '商户id' if '商户id' in prod_df.columns else ('商家ID' if '商家ID' in prod_df.columns else None)
        for m in s3_top20[:10]:
            name = m['s']
            mid_val = m.get('mid', 0)
            psub = pd.DataFrame()
            if prod_mid_col and mid_val:
                try:
                    psub = prod_df[prod_df[prod_mid_col].apply(lambda v: int(float(str(v))) == mid_val if pd.notna(v) else False)]
                except:
                    pass
            if len(psub) == 0 and len(name) >= 4:
                # 回退到名称匹配
                for _, g in prod_df.iterrows():
                    mname = str(g.get('商户名称', ''))
                    if name[:4] in mname:
                        psub = prod_df[prod_df['商户名称']==mname]
                        break
            if len(psub) > 0:
                top2 = psub.nlargest(2, 'GMV')
                items = []
                for _, p in top2.iterrows():
                    pname = str(p.get('商品名称', ''))
                    if not pname or pname == 'nan':
                        pid = str(p.get('商品id', ''))
                        pcat = str(p.get('一级类目', ''))
                        pname = f"商品{pid}" + (f"({pcat})" if pcat and pcat != 'nan' else '')
                    items.append({'n': pname[:25], 'g': R(p['GMV'])})
                if items: result[name] = items
        return result
    s3_prods = merchant_prods()

    # ── S3 归因: 按行业分组商家分析 ──
    def s3_industry_analysis():
        """按行业归类商家，每个行业按GMV排序，附带波动原因分析"""
        result = {}
        if len(df_m_xd) == 0 or w_this is None: return result
        prod_df = df_gprod if len(df_gprod) > 0 else df_tprod
        for ind2 in INDUSTRIES:
            for cat2 in CAT_MAP[ind2]:
                key = f"{ind2}-{cat2}"
                w12 = df_m_xd[(df_m_xd['周'] == w_this) & (df_m_xd['类目'] == cat2)]
                w11 = df_m_xd[(df_m_xd['周'] == w_last) & (df_m_xd['类目'] == cat2)] if w_last else pd.DataFrame()
                cat_gmv_cw = w12['GMV'].sum(); cat_gmv_lw = w11['GMV'].sum() if len(w11) > 0 else 0
                if cat_gmv_lw == 0: continue
                cat_wow = (cat_gmv_cw - cat_gmv_lw) / cat_gmv_lw * 100
                mid_col = '商家ID' if '商家ID' in w12.columns else None
                if not mid_col: continue
                g12 = w12.groupby([mid_col, '店铺名称']).agg(
                    {'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '商详PV': 'sum'}).reset_index()
                if len(w11) > 0:
                    g11 = w11.groupby([mid_col, '店铺名称']).agg(
                        {'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '商详PV': 'sum'}).reset_index()
                    mg = g12.merge(g11, on=[mid_col, '店铺名称'], suffixes=('_c', '_l'), how='outer').fillna(0)
                else:
                    mg = g12.copy()
                    for c2 in ['GMV', '商品曝光PV', '支付订单数', '商详PV']:
                        mg[c2 + '_c'] = mg[c2]; mg[c2 + '_l'] = 0
                mg['delta'] = mg['GMV_c'] - mg['GMV_l']
                top = mg.nlargest(5, 'GMV_c')
                ms = []
                for _, r2 in top.iterrows():
                    gw2 = R((r2['GMV_c'] - r2['GMV_l']) / r2['GMV_l'] * 100) if r2['GMV_l'] > 0 else 999
                    pw2 = R((r2['商品曝光PV_c'] - r2['商品曝光PV_l']) / r2['商品曝光PV_l'] * 100) if r2['商品曝光PV_l'] > 0 else 999
                    cc2 = R(r2['支付订单数_c'] / r2['商详PV_c'] * 100) if r2.get('商详PV_c', 0) > 0 else 0
                    cl2 = R(r2['支付订单数_l'] / r2['商详PV_l'] * 100) if r2.get('商详PV_l', 0) > 0 else 0
                    cat_delta = cat_gmv_cw - cat_gmv_lw
                    contrib = R(r2['delta'] / cat_delta * 100) if cat_delta != 0 else 0
                    # 爆品匹配
                    prods = []
                    sname = str(r2['店铺名称'])
                    mid_val = r2.get(mid_col)
                    if len(prod_df) > 0 and pd.notna(mid_val):
                        # 优先用商家ID匹配（商品表字段为'商户id'）
                        prod_mid_col = '商户id' if '商户id' in prod_df.columns else ('商家ID' if '商家ID' in prod_df.columns else None)
                        if prod_mid_col:
                            try:
                                mid_int = int(float(str(mid_val)))
                                psub = prod_df[prod_df[prod_mid_col].apply(lambda v: int(float(str(v))) == mid_int if pd.notna(v) else False)]
                            except:
                                psub = pd.DataFrame()
                        elif len(sname) >= 4:
                            # 回退到名称匹配
                            psub = prod_df[prod_df['商户名称'].astype(str).str.contains(sname[:4], na=False)]
                        else:
                            psub = pd.DataFrame()
                        if len(psub) > 0:
                            top_prods2 = psub.nlargest(2, 'GMV')
                            merchant_total_gmv = psub['GMV'].sum()
                            for _, p in top_prods2.iterrows():
                                pname = str(p.get('商品名称', ''))
                                if not pname or pname == 'nan':
                                    pid = str(p.get('商品id', ''))
                                    pcat = str(p.get('一级类目', ''))
                                    pname = f"商品{pid}" + (f"({pcat})" if pcat and pcat != 'nan' else '')
                                p_gmv = R(p['GMV'])
                                p_pv = int(p.get('商品曝光PV', 0))
                                p_ord = int(p.get('支付订单数', 0))
                                p_sx = int(p.get('商详PV', 0))
                                p_cv = R(p_ord / p_sx * 100) if p_sx > 0 else 0
                                p_gpm = R(p['GMV'] / p_pv * 1000) if p_pv > 0 else 0
                                p_share = R(p['GMV'] / merchant_total_gmv * 100) if merchant_total_gmv > 0 else 0
                                prods.append({
                                    'n': pname[:25], 'g': p_gmv, 'pv': p_pv,
                                    'cv': p_cv, 'gpm': p_gpm, 'sh': p_share,
                                    'o': p_ord
                                })
                    ms.append({'s': sname, 'gc': R(r2['GMV_c']), 'gl': R(r2['GMV_l']),
                               'gd': R(r2['delta']), 'gw': min(gw2, 9999), 'pw': min(pw2, 9999),
                               'cc': cc2, 'cl': cl2, 'ctr': contrib, 'pr': prods})
                if ms:
                    result[key] = {'wow': R(cat_wow), 'gc': R(cat_gmv_cw), 'gl': R(cat_gmv_lw), 'ms': ms}
        return result
    s3_ind_ana = s3_industry_analysis()

    # ════════ S4: 流量渠道 ════════
    print("  → S4 流量渠道")
    if len(df_flow) > 0 and '资源位二级入口' in df_flow.columns:
        channels = df_flow['资源位二级入口'].dropna().unique()
        print(f"    流量渠道数: {len(channels)}, 含天马: {'天马推荐商品卡' in channels}, 含feed: {'商城首页feed' in channels}")
    else:
        print(f"    ⚠ 流量数据缺少资源位二级入口列，当前列: {list(df_flow.columns) if len(df_flow)>0 else '空'}")
    # 流量总览用整体数据(已有PV)，渠道明细用分行业x流量渠道
    s4_t = [agg(df_main[df_main['周']==w]) for w in wks]
    s4_x = [agg(df_main[(df_main['周']==w)&(df_main['业务线二级']=='小店')]) for w in wks]
    s4_y = [agg(df_main[(df_main['周']==w)&(df_main['业务线二级']=='自营')]) for w in wks]
    s4_xr = [R(s4_x[i]['PV']/s4_t[i]['PV']*100) if s4_t[i]['PV'] else 0 for i in range(len(wks))]

    def s4_special(ch):
        """天马/Feed专项: 输出整体+小店维度全量指标"""
        r = []
        for w in wks:
            da = df_flow[df_flow['周']==w] if len(df_flow)>0 else pd.DataFrame()
            dc = da[da['资源位二级入口']==ch] if len(da)>0 and '资源位二级入口' in da.columns else pd.DataFrame()
            dx = dc[dc['业务线二级']=='小店'] if len(dc)>0 else pd.DataFrame()
            dy = dc[dc['业务线二级']=='自营'] if len(dc)>0 else pd.DataFrame()
            tp2 = da['商品曝光PV'].sum() if len(da)>0 else 0
            a_all = agg(dc); a_xd = agg(dx)
            cp = dc['商品曝光PV'].sum() if len(dc)>0 else 0
            xp = dx['商品曝光PV'].sum() if len(dx)>0 else 0
            yp = dy['商品曝光PV'].sum() if len(dy)>0 else 0
            a_all['rp'] = R(cp/tp2*100) if tp2 else 0
            a_all['xp'] = R(xp/cp*100) if cp else 0
            a_all['xpv'] = int(xp); a_all['ypv'] = int(yp)
            # 小店维度指标
            a_all['xo'] = a_xd['o']; a_all['xGMV'] = a_xd['GMV']
            a_all['xGMVr'] = R(a_xd['GMV']/a_all['GMV']*100) if a_all['GMV'] else 0
            a_all['xGPM'] = a_xd['GPM']; a_all['xCTR'] = a_xd['CTR']; a_all['xscv'] = a_xd['scv']
            r.append(a_all)
        return r

    s4_tm = s4_special('天马推荐商品卡')
    s4_fd = s4_special('商城首页feed')

    def s4_channels(biz=None):
        """分渠道明细含渠道占比"""
        if len(df_flow)==0: return {}
        sub=df_flow
        if biz: sub=sub[sub['业务线二级']==biz]
        if '资源位二级入口' not in sub.columns: return {}
        chs=[c for c in sub[sub['周']==w_this].groupby('资源位二级入口')['商品曝光PV'].sum().nlargest(10).index if pd.notna(c)]
        result={}
        for ch in chs:
            vals=[]
            for w in wks:
                d=sub[(sub['周']==w)&(sub['资源位二级入口']==ch)]
                total_pv = sub[sub['周']==w]['商品曝光PV'].sum()
                if d['商品曝光PV'].sum()<1000: vals.append(None); continue
                a2 = agg(d)
                a2['share'] = R(d['商品曝光PV'].sum()/total_pv*100) if total_pv else 0
                vals.append(a2)
            result[str(ch)]=vals
        return result
    s4_cx=s4_channels('小店'); s4_cy=s4_channels('自营')

    # S4 数据表3: 小店分行业×核心渠道
    def s4_by_industry():
        if len(df_flow)==0: return {}
        sub = df_flow[df_flow['业务线二级']=='小店']
        if '资源位二级入口' not in sub.columns: return {}
        result = {}
        for ind2 in INDUSTRIES:
            isub = sub[sub['行业']==ind2] if '行业' in sub.columns else pd.DataFrame()
            if len(isub)==0: continue
            top_chs = [c for c in isub[isub['周']==w_this].groupby('资源位二级入口')['商品曝光PV'].sum().nlargest(5).index if pd.notna(c)]
            ind_data = {}
            for ch in top_chs:
                vals = []
                for w in wks:
                    d = isub[(isub['周']==w)&(isub['资源位二级入口']==ch)]
                    if d['商品曝光PV'].sum()<100: vals.append(None); continue
                    vals.append(agg(d))
                ind_data[str(ch)] = vals
            if ind_data: result[ind2] = ind_data
        return result
    s4_ind = s4_by_industry()

    # ── S4 归因: 波动渠道拆解经营类目 ──
    def s4_channel_attribution():
        """对小店PV/GMV WoW变化大的渠道，拆解经营类目贡献"""
        result = {}
        if len(df_flow) == 0 or w_this is None: return result
        sub = df_flow[df_flow['业务线二级'] == '小店'] if '业务线二级' in df_flow.columns else pd.DataFrame()
        if len(sub) == 0 or '资源位二级入口' not in sub.columns: return result
        cat_col = '经营一级类目名称' if '经营一级类目名称' in sub.columns else None
        if not cat_col: return result
        top_chs = [c for c in sub[sub['周'] == w_this].groupby('资源位二级入口')['商品曝光PV'].sum().nlargest(8).index if pd.notna(c)]
        for ch in top_chs:
            ch_cw = sub[(sub['周'] == w_this) & (sub['资源位二级入口'] == ch)]
            ch_lw = sub[(sub['周'] == w_last) & (sub['资源位二级入口'] == ch)] if w_last else pd.DataFrame()
            pv_cw = ch_cw['商品曝光PV'].sum(); pv_lw = ch_lw['商品曝光PV'].sum() if len(ch_lw) > 0 else 0
            gmv_cw = ch_cw['GMV'].sum(); gmv_lw = ch_lw['GMV'].sum() if len(ch_lw) > 0 else 0
            pv_wow = R((pv_cw - pv_lw) / pv_lw * 100) if pv_lw > 0 else 999
            gmv_wow = R((gmv_cw - gmv_lw) / gmv_lw * 100) if gmv_lw > 0 else 999
            if max(abs(pv_wow), abs(gmv_wow)) < 5: continue
            # 按经营类目拆解贡献
            g12 = ch_cw.groupby(cat_col).agg({'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '商详PV': 'sum'}).reset_index()
            if len(ch_lw) > 0:
                g11 = ch_lw.groupby(cat_col).agg({'GMV': 'sum', '商品曝光PV': 'sum', '支付订单数': 'sum', '商详PV': 'sum'}).reset_index()
                mg = g12.merge(g11, on=cat_col, suffixes=('_c', '_l'), how='outer').fillna(0)
            else:
                mg = g12.copy()
                for c2 in ['GMV', '商品曝光PV', '支付订单数', '商详PV']:
                    mg[c2 + '_c'] = mg[c2]; mg[c2 + '_l'] = 0
            mg['gd'] = mg['GMV_c'] - mg['GMV_l']
            mg['pd'] = mg['商品曝光PV_c'] - mg['商品曝光PV_l']
            top = mg.reindex(mg['gd'].abs().nlargest(3).index)
            cats = []
            for _, r2 in top.iterrows():
                gw2 = R((r2['GMV_c'] - r2['GMV_l']) / r2['GMV_l'] * 100) if r2['GMV_l'] > 0 else 999
                pw2 = R((r2['商品曝光PV_c'] - r2['商品曝光PV_l']) / r2['商品曝光PV_l'] * 100) if r2['商品曝光PV_l'] > 0 else 999
                cc2 = R(r2['支付订单数_c'] / r2['商详PV_c'] * 100) if r2.get('商详PV_c', 0) > 0 else 0
                cl2 = R(r2['支付订单数_l'] / r2['商详PV_l'] * 100) if r2.get('商详PV_l', 0) > 0 else 0
                cats.append({'n': str(r2[cat_col]), 'gd': R(r2['gd']), 'pd': int(r2['pd']),
                             'gw': min(gw2, 9999), 'pw': min(pw2, 9999), 'cc': cc2, 'cl': cl2})
            if cats:
                result[str(ch)] = {'pv_wow': pv_wow, 'gmv_wow': gmv_wow,
                                   'pv': int(pv_cw), 'gmv': R(gmv_cw), 'cats': cats}
        return result
    s4_ch_attr = s4_channel_attribution()

    # ════════ S5: 成交体裁 ════════
    print("  → S5 成交体裁")
    if len(df_type) > 0:
        types_found = df_type['内容类型'].dropna().unique().tolist() if '内容类型' in df_type.columns else []
        print(f"    体裁类型: {types_found}")
    else:
        print(f"    ⚠ 体裁数据为空")
    types_list = ['商品', '视频', '动态', '直播', '其他']

    def s5_calc(biz=None, cat_filter=None):
        sub = df_type if len(df_type) > 0 else pd.DataFrame()
        if len(sub) == 0: return [{'商品':{'g':0,'p':0},'视频':{'g':0,'p':0},'动态':{'g':0,'p':0},'直播':{'g':0,'p':0},'其他':{'g':0,'p':0}} for _ in wks]
        if biz: sub = sub[sub['业务线二级'] == biz]
        if cat_filter: sub = sub[sub['类目'] == cat_filter]
        r = []
        for w in wks:
            d = sub[sub['周'] == w]; total = d['GMV'].sum()
            wk = {}
            for t in types_list:
                g = d[d['内容类型'] == t]['GMV'].sum()
                wk[t] = {'g': R(g), 'p': R(g / total * 100) if total else 0}
            r.append(wk)
        return r

    s5_all = s5_calc(); s5_xd = s5_calc('小店'); s5_zy = s5_calc('自营')
    s5_ind = {}; s5_ik = []
    if wks:
        for ind2 in INDUSTRIES:
            for cat2 in CAT_MAP[ind2]:
                v = s5_calc('小店', cat2)
                key = f"{ind2}-{cat2}"
                if any(v[-1][t]['g'] > 0 for t in types_list):
                    s5_ind[key] = v; s5_ik.append(key)

    # ════════ 组装JSON ════════
    # 周标签格式化 (W9→W09等)
    WL_display = [f"W{w}" for w in wks]

    ALL = {
        'W': WL_display, 'WL': WL_display,
        's1': s1,
        's2': {'a': s2_all, 'x': s2_xd, 'y': s2_zy, 'k': all_keys, 'dt': s2_detail},
        's3': {'t20': s3_top20, 'bc': s3_by_cat, 'wow': s3_wow, 'tr': s3_trend, 'pr': s3_prods, 'ia': s3_ind_ana},
        's4': {'t': s4_t, 'x': s4_x, 'y': s4_y, 'xr': s4_xr, 'cx': s4_cx, 'cy': s4_cy, 'tm': s4_tm, 'fd': s4_fd, 'ind': s4_ind, 'ca': s4_ch_attr},
        's5': {'a': s5_all, 'x': s5_xd, 'y': s5_zy, 'ind': s5_ind, 'ik': s5_ik},
        'tp': tp,
    }

    class NpE(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, (np.integer,)): return int(o)
            if isinstance(o, (np.floating,)): return float(o)
            return super().default(o)

    log(
        "INFO",
        "模块产出摘要",
        s2_keys=len(s2_all.keys()) if isinstance(s2_all, dict) else 0,
        s3_top20=len(s3_top20),
        s4_channels_x=len(s4_cx.keys()) if isinstance(s4_cx, dict) else 0,
        s4_channels_y=len(s4_cy.keys()) if isinstance(s4_cy, dict) else 0,
        s5_industry_views=len(s5_ik),
    )

    return json.dumps(ALL, ensure_ascii=False, cls=NpE, separators=(',', ':')), wks


# ════════════════════════════════════════════════
# HTML组装
# ════════════════════════════════════════════════

def get_template():
    return r'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>交易业务周报</title>
<script src="https://cdn.staticfile.net/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdn.staticfile.net/chartjs-plugin-datalabels/2.2.0/chartjs-plugin-datalabels.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0b0f19;--c1:#131a2b;--c2:#1a2340;--bd:#1f2b47;--t1:#e8ecf4;--t2:#8b95ab;--t3:#5a6478;--blue:#4f8fff;--up:#34d399;--dn:#f87171}
body{font-family:'Noto Sans SC',system-ui,sans-serif;background:var(--bg);color:var(--t1);line-height:1.6}
.hdr{background:linear-gradient(135deg,#1a1145,#0d1a30,#0a1628);padding:28px 32px;border-bottom:1px solid var(--bd)}
.hdr h1{font-size:26px;font-weight:700;background:linear-gradient(90deg,#60a5fa,#c084fc,#fb7185);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr p{color:var(--t3);font-size:13px;margin-top:4px}
.nav{display:flex;gap:2px;padding:8px 32px;background:var(--c1);border-bottom:1px solid var(--bd);position:sticky;top:0;z-index:99;overflow-x:auto}
.nav button{padding:9px 18px;border:none;background:transparent;color:var(--t2);cursor:pointer;border-radius:6px;font-size:13px;font-family:inherit;white-space:nowrap;transition:.2s}
.nav button:hover{background:var(--c2)} .nav button.on{background:var(--blue);color:#fff}
.wrap{max-width:1440px;margin:0 auto;padding:20px 32px 60px}
.sec{display:none}.sec.on{display:block}
.stit{font-size:18px;font-weight:600;margin:20px 0 10px;padding-left:10px;border-left:3px solid var(--blue)}
.sdesc{color:var(--t3);font-size:12px;margin-bottom:14px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.cd{background:var(--c1);border:1px solid var(--bd);border-radius:10px;padding:16px;margin-bottom:14px}
.cd-t{font-size:14px;font-weight:600;margin-bottom:10px}
.mr{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.m{background:var(--c2);border-radius:7px;padding:12px 14px;flex:1;min-width:120px}
.m .lb{font-size:10px;color:var(--t3);margin-bottom:3px;text-transform:uppercase;letter-spacing:.5px}
.m .vl{font-size:20px;font-weight:700}
.m .ch{font-size:11px;margin-top:2px}.m .ch.up{color:var(--up)}.m .ch.dn{color:var(--dn)}
.ov{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:11.5px}
th{background:var(--c2);padding:8px 6px;text-align:right;font-weight:500;color:var(--t2);border-bottom:1px solid var(--bd);white-space:nowrap}
th:first-child{text-align:left;padding-left:10px}
td{padding:7px 6px;text-align:right;border-bottom:1px solid rgba(31,43,71,.5);white-space:nowrap}
td:first-child{text-align:left;font-weight:500;padding-left:10px}
tr:hover{background:rgba(79,143,255,.04)}
.tg{display:inline-block;padding:1px 7px;border-radius:3px;font-size:10.5px;font-weight:600}
.tg-up{background:rgba(52,211,153,.12);color:var(--up)}.tg-dn{background:rgba(248,113,113,.12);color:var(--dn)}
.cc{position:relative;height:300px;margin:8px 0}
.cbox{background:linear-gradient(135deg,rgba(79,143,255,.06),rgba(167,139,250,.06));border:1px solid rgba(79,143,255,.18);border-radius:8px;padding:14px 16px;margin:14px 0;font-size:12px;line-height:1.9}
.cbox h4{color:var(--blue);margin-bottom:6px;font-size:13px}
.cbox li{margin:3px 0;color:var(--t2)} .hl{color:var(--t1);font-weight:600}
.sub-cat td:first-child{padding-left:24px!important;color:var(--t2)!important;font-weight:400!important}
.pie-c{height:220px;position:relative} canvas{max-width:100%}
@media(max-width:768px){.g2,.g3{grid-template-columns:1fr}.wrap{padding:12px 16px}}
</style></head><body>
<div class="hdr"><h1>交易业务周报 · 整体数据概览</h1><p id="hdr-sub"></p></div>
<div class="nav">
<button class="on" onclick="sw(0)">1 核心数据趋势</button>
<button onclick="sw(1)">2 行业拆解</button>
<button onclick="sw(2)">3 小店商家</button>
<button onclick="sw(3)">4 流量渠道</button>
<button onclick="sw(4)">5 成交体裁</button>
</div>
<div class="wrap" id="app"></div>
<script>
var D='''


def build_html(data_json, wks, js_path):
    header = get_template()
    with open(js_path, 'r', encoding='utf-8') as f:
        js = f.read()
    footer = '\n</scr' + 'ipt>\n</body>\n</html>'
    html = header + data_json + ';\n' + js + footer

    # 动态标题
    wl = [f"W{w}" for w in wks]
    if len(wl) >= 2:
        html = html.replace('<p id="hdr-sub"></p>',
                            f'<p>本周 {wl[-1]} | 上周 {wl[-2]} | 周五到周四</p>')
    return html


# ════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════

def main():
    # Ensure logs are emitted during processing even when stdout is piped to tee.
    try:
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description='交易业务周报生成器 v2')
    parser.add_argument('--dir', '-d', default='.', help='数据文件目录')
    parser.add_argument('--output', '-o', default=None, help='输出HTML路径')
    args = parser.parse_args()

    print("=" * 50)
    print("  交易业务周报生成器 v2.0")
    print("  数据模型: 分维度文件 (周级)")
    print("=" * 50)

    dfs = load_all(args.dir)
    data_json, wks = process(dfs)
    print(f"\n  数据JSON: {len(data_json):,} 字节")

    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.js')
    if not os.path.exists(js_path):
        print(f"  ❌ 缺少 app.js，请确保与脚本同目录")
        sys.exit(1)

    html = build_html(data_json, wks, js_path)
    out = args.output or (f"交易业务周报_W{wks[-1]}.html" if wks else "交易业务周报.html")
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ 报告已生成: {out}")
    print(f"   文件大小: {len(html):,} 字节")
    if wks:
        print(f"   本周: W{wks[-1]}（周五-周四）\n")


if __name__ == '__main__':
    main()
