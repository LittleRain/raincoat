"""Generate synthetic Excel inputs matching the current six-file runtime contract."""
from pathlib import Path
import pandas as pd


def generate(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for week, multiplier in [(15, 1), (16, 2)]:
        for i, biz in enumerate(['小店'] * 5 + ['自营'] * 3 + ['工坊', '票务'], 1):
            gmv = i * 1000 * multiplier
            rows.append({
                '周五-周四周': week, '业务线二级': biz, 'GMV': gmv,
                '订单数': i * 10 * multiplier, '买家数': i * 8 * multiplier,
                '商品曝光PV': i * 10000 * multiplier, '商品点击PV': i * 1000 * multiplier,
                '商详PV': i * 500 * multiplier, 'CTR': 0.05, 'CVR': 0.02, 'GPM': 100,
                '商家ID': i, '店铺名称': f'合成店铺{i}', '商品ID': 100 + i,
                '商品名称': f'合成商品{i}', '经营一级类目名称': ['硬周', '软周', '其他'][i % 3],
                '资源位二级入口': '天马推荐商品卡' if i % 2 else '商城首页feed',
                '内容类型': ['商品', '视频', '直播', '动态', '其他'][i % 5],
            })
    details = pd.DataFrame(rows)
    overall = details.groupby(['周五-周四周', '业务线二级'], as_index=False).agg({
        'GMV': 'sum', '订单数': 'sum', '买家数': 'sum', '商品曝光PV': 'sum',
        '商品点击PV': 'sum', '商详PV': 'sum', 'CTR': 'mean', 'CVR': 'mean', 'GPM': 'mean',
    })
    overall.to_excel(destination / '整体.xlsx', index=False)
    for name in ['行业', '商品明细', '流量', '内容类型']:
        details.to_excel(destination / f'{name}.xlsx', index=False)
    tags = pd.DataFrame({
        'merchant_id': list(range(1, 6)),
        'owner_ld': ['南征', 'allen', '孙悟饭', '加林', '其他'],
        'owner_cate': ['合成分类'] * 5,
    })
    tags.to_excel(destination / '商家标签.xlsx', sheet_name='tags', index=False)
    # Set the exact runtime sheet name without Excel's case-insensitive Sheet collision.
    import openpyxl
    workbook = openpyxl.load_workbook(destination / '商家标签.xlsx')
    workbook.active.title = 'sheet'
    workbook.save(destination / '商家标签.xlsx')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    generate(parser.parse_args().destination)
