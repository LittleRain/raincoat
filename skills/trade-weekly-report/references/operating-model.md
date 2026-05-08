# 运营模式

## 行业分类规则

### 小店行业分类（商家标签关联）

根据商家标签表中的 `owner_ld` 和 `owner_cate` 字段确定：

| 行业名称 | owner_ld | owner_cate |
|----------|----------|------------|
| ACG行业-南征 | 南征 | ACG行业-出版物, ACG行业-硬周, ACG行业-游戏虚拟 |
| ACG行业-allen | allen | ACG行业-软周, ACG行业-盲盒 |
| 综合行业-孙悟饭 | 孙悟饭 | 家居手作, 数码科技, 珠宝配饰, 卡牌, 知识分享 |
| 头部达人-加林 | 加林 | 头部达人 |
| 小店其他 | 其他/NULL | 其他/NULL |

### 自营行业分类

根据商品属性字段确定：

| 行业名称 | 口径 |
|----------|------|
| 硬周 | 商品一级经营分类 = 硬周 |
| 游戏虚拟 | 商品一级经营分类 = 虚拟卡券 OR 后台二级分类名称 = 游戏账号 OR 后台一级分类名称 = 虚拟充值 |
| 出版物 | 商品一级经营分类 = 出版物 |
| 软周 | 商品一级经营分类 = 软周 |
| 盲盒 | 商品一级经营分类 = 赏类 |
| 自营其他 | 不属于以上分类 |

## 指标计算

### CTR（点击率）
```
CTR = 商详曝光PV / 商品曝光PV
```

### CVR（支付转化率）
```
CVR = 支付订单数 / 商品曝光PV
```

### GPM（千次曝光 GMV）
```
GPM = GMV / 商品曝光PV × 1000
```

### 客单价
```
客单价 = GMV / 买家数
```

### 小店对自营控比
```
控比 = 小店GMV / 自营GMV
```

### 周波动贡献率
```
贡献率 = (商家本周GMV - 商家上周GMV) / 该分类本周涨跌GMV
```

## 执行流程

1. 加载数据文件
2. 关联商家标签（行业分类）
3. 计算派生指标
4. 按周/行业/商家聚合
5. 生成 HTML 报告

## 开发规范（踩坑记录）

### 列名兼容性

⚠️ **数据文件列名在不同批次间可能变化，必须动态探测**

#### 当前已知差异记录

**商品明细（文件名兼容性）**：

| 旧文件名 | 新文件名 | 脚本处理 |
|---------|---------|---------|
| `商品明细.xlsx` | `商品.xlsx` | `load_all()` 已自动兼容（优先 商品明细.xlsx，不存在则用 商品.xlsx） |

**列名差异汇总**：

| 数据文件 | 旧列名 | 新列名 | clean() 映射 |
|---------|--------|--------|------------|
| 整体/行业/流量/内容类型/商品明细 | `GMV` | `GMV（不减退款）` | ✅ → `GMV` |
| 整体/行业/流量/内容类型/商品明细 | `支付订单买家数` | `买家数` | ✅ → `买家数` |
| 整体/行业/流量/内容类型/商品明细 | `支付订单数` | `订单数` | ✅ → `订单数` |
| 整体/行业/流量/内容类型/商品明细 | `PVCTR` | `CTR` | ✅ → `CTR` |
| 整体/行业/流量/内容类型/商品明细 | `商详支付转化率-UV` | `CVR` | ✅ → `CVR` |
| 商品明细 | `商户id` | `商家ID` | ❌ 需动态探测 |
| 商品明细 | `商户名称` | `店铺名称` | ❌ 需动态探测 |
| 商品明细 | `商品id` | `商品ID` | ❌ 需动态探测 |
| 整体（部分批次） | `商详UV` | `商详PV` | ✅ → `商详PV`（5月8日数据已统一） |

**商详PV 用途**：仅用于 `generate_conclusions` 结论文案计算，不参与 GPM 等业务口径。

### GPM 计算口径（5月8日发现并修复）

⚠️ **必须用聚合 GPM，不能用行均值 GPM**

**错误做法**（已修复）：
```python
gpm_c = safe_float(r_cur['GPM'].mean())  # ❌ 行级 GPM 的算术均值
```

**正确做法**（聚合计算）：
```python
pv_c = safe_float(r_cur['商品曝光PV'].sum())
gpm_c = safe_float(r_cur['GMV'].sum()) / pv_c * 1000 if pv_c > 0 else 0.0
```

差异举例（W19 小店数据）：
| 行业 | 行均值 GPM | 聚合 GPM | 差异 |
|------|-----------|---------|------|
| 孙悟饭 | 726.9 | **213.9** | +513 |
| 加林 | 74.0 | **17.5** | +56.5 |
| 小店其他 | 423.7 | **67.3** | +356.3 |

行业级和分类级 GPM 均需用此公式（`get_shop_ind_table`、`get_ziying_ind_table`）。

### 分类表展示口径（5月8日发现并修复）

⚠️ **当前周 GMV=0 的分类仍需展示，不能因无当前周数据而消失**

**错误做法**（已修复）：
```python
cates = r_cur['小店分类'].dropna().unique()  # ❌ 只取当前周，非0分类会被遗漏
```

**正确做法**（当前周+上周并集）：
```python
all_cates_cur = set(r_cur['小店分类'].dropna().unique())
all_cates_prev = set(r_prev['小店分类'].dropna().unique()) if not r_prev.empty else set()
all_cates = all_cates_cur | all_cates_prev
```

适用于 `get_shop_ind_table()` 和 `get_ziying_ind_table()` 的分类遍历。

### 业务线二级值变化（5月8日数据）

⚠️ **5月8日数据中 `业务线二级` 不再包含 `整体（小店+自营）`**

| 数据批次 | 业务线二级值（行业.xlsx） |
|---------|------------------------|
| 4月24日/历史 | `整体（小店+自营）`、`小店`、`自营` |
| **5月8日** | `小店`、`自营`（`整体`不再存在） |

脚本中 `df2_shop`/`df2_ziying` 过滤逻辑不受影响（直接按 `小店`/`自营` 过滤，无需 `整体`）。如后续有新的业务线值，需同步更新 `SHOP_INDUSTRIES`/`ZIYING_INDUSTRIES` 常量。

**动态探测模板**：

```python
merch_id_col = next((c for c in ['商家ID', '商户id'] if c in df.columns), '商家ID')
```

### 字段命名一致性

⚠️ **每次生成结论或引用行数据时，必须对照实际数据结构**

| 数据来源 | 字段名 | 备注 |
|---------|--------|------|
| `s2_shop_table` / `s2_ziying_table` | `row['name']` | 行业/分类名称 |
| `s3_top20_rows` | `row['name']` | 店铺名称 |
| `s3_top20_prod_rows` | `row['name']` 或 `row['商品名称']` | 商品名称 |
| `s4_shop_channels` | `row['name']` 或 `row['渠道']` | 渠道名称 |

**错误做法**：`row.get('行业', row.get('分类', '未知'))`
**正确做法**：`row.get('name', '未知')`

### 周数排序

⚠️ **图表横轴必须是小周在左、大周在右**

```python
# ❌ 错误：大周在前
WEEKS = sorted(df['周五-周周四'].unique().tolist(), reverse=True)
CUR_W = WEEKS[0]  # 最大周

# ✅ 正确：小周在前
WEEKS = sorted(df['周五-周周四'].unique().tolist())
CUR_W = WEEKS[-1]  # 最大周
```

### 结论生成时机

⚠️ **结论生成必须在 HTML 组装之前完成，所有变量需提前解包**

```python
# 1. 先生成结论
conclusions = generate_conclusions(...)

# 2. 解包结论变量
s1_gmv_conclusion = conclusions['s1_gmv']

# 3. 组装 HTML 时注入
HTML_PARTS.append(f'<div class="conclusion">{s1_gmv_conclusion}</div>')
```

### 流量文件周期管理（S4 专有）

⚠️ **流量.xlsx 存在两种异常，必须双重处理**

**异常1**：整体文件比流量文件超前（如整体有W16但流量只到W15）  
**异常2**：流量文件最新周数据不完整（只有部分天的明细，GMV覆盖率<80%）

流量文件特征：
- 列名有尾部空格：`'周五-周四周 '`（load 时已统一 strip 处理）
- 最新周行数可能只有前一周的10-20%，直接做环比会出现 -80% 以上的假性暴跌

**正确做法（完整模板）**：

```python
# ① 用整体文件 GMV 做基准，检测流量文件各周覆盖率
def get_s4_valid_weeks(df4c, df1, threshold=0.8):
    all_weeks = sorted(df4c['周五-周四周'].dropna().unique().tolist())
    valid = []
    for w in all_weeks:
        flow_gmv = df4c[df4c['周五-周四周']==w]['GMV'].sum()
        whole_gmv = df1[df1['周五-周四周']==w]['GMV'].sum()
        status = '✓' if flow_gmv/whole_gmv >= threshold else f'⚠ 仅{flow_gmv/whole_gmv:.0%}'
        print(f"[INFO] 流量W{int(w)} GMV覆盖率: {flow_gmv/whole_gmv:.0%} {status}")
        if flow_gmv / whole_gmv >= threshold:
            valid.append(w)
    return valid

S4_WEEKS = get_s4_valid_weeks(df4_clean, df1)

# ② 所有周期变量统一从原始列表取（避免过滤后[-2]和[-1]撞值）
all_s4_weeks_raw = sorted(df4_clean['周五-周四周'].dropna().unique().tolist())
incomplete_weeks = [w for w in all_s4_weeks_raw if w not in S4_WEEKS]
S4_CUR_W  = int(all_s4_weeks_raw[-1])                       # 最大周 = 流量最新周
S4_PREV_W = int(all_s4_weeks_raw[-2]) if len(all_s4_weeks_raw) >= 2 else None  # 次大周

# ③ 天马/feed 趋势表用全量历史周（不过滤，展示完整走势）
ALL_S4_WEEKS = all_s4_weeks_raw
S4_SPECIAL_LABELS = [f'W{int(w)}' for w in ALL_S4_WEEKS]

# ④ Top10 用过滤后的完整周列表（仅展示有参考价值的周）
# 天马/feed 图表横轴用 S4_SPECIAL_LABELS（来自 ALL_S4_WEEKS）
# 天马/feed 表格列头用 data_rows 自身的 week 字段（不是 WEEK_LABELS）

# ⑤ 黄色警告横幅
if incomplete_weeks:
    incomplete_str = '、'.join([f'W{int(w)}' for w in incomplete_weeks])
    s4_data_notice = f'<div ...>⚠ 数据说明：流量明细有效数据截至 W{S4_CUR_W}（{incomplete_str} 数据不完整）。渠道 Top10 环比参考 W{S4_PREV_W}（仅供参考）；天马/feed 趋势基于 W{S4_CUR_W}。</div>'
else:
    s4_data_notice = ''
```

**⚠️ 易错点**：

| 错误写法 | 正确写法 | 原因 |
|---------|---------|------|
| `S4_CUR_W = int(S4_WEEKS[-1])` | `S4_CUR_W = int(all_s4_weeks_raw[-1])` | `S4_WEEKS` 过滤后只剩1个元素，`[-1]`=14 |
| `S4_PREV_W = S4_WEEKS[-2]` | `S4_PREV_W = all_s4_weeks_raw[-2]` | 同上，会导致同周比环比全为0 |
| 表头循环 `for w in WEEK_LABELS` | `for dr in data_rows: dr['week']` | 数据行只有2列但表头8列，错位 |
| 图表标签用 `WEEK_LABELS` | 用 `S4_SPECIAL_LABELS` | 数据只有2点却对应8个标签 |


生成报告后必查：
- [ ] 所有板块结论无"未知"
- [ ] 图表横轴 W9→W16 升序排列
- [ ] 周环比正负号正确（↑↓）
- [ ] S4 日志中各周覆盖率标注清晰（✓/⚠）
- [ ] S4 小店/自营核心渠道 Top10 有数据（至少5行）
- [ ] S4 Top10 表格环比列**有有效数字**（不能全是 `-`）
- [ ] S4 天马/商城feed 专项表列头数 = 数据列数（不能有8列表头但只有2列数据）
- [ ] S4 天马/商城feed 图表横轴标签与数据点数一致
- [ ] 若有不完整周，S4 板块头部出现黄色警告横幅
