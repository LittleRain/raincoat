#!/bin/bash
# 交易业务周报生成脚本 v2.0
# Usage: ./run-report.sh /path/to/data/dir [output.html]
#
# 数据目录需包含：
#   整体.xlsx / 行业.xlsx / 商品明细.xlsx / 流量.xlsx / 内容类型.xlsx / 商家标签.xlsx

set -e

DATA_DIR="${1:-.}"
OUTPUT="${2:-trade-weekly-report.html}"

echo "=== 交易业务周报生成 v2.0 ==="
echo "数据目录: $DATA_DIR"
echo "输出文件: $OUTPUT"

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found"
    exit 1
fi

# 检查依赖
python3 -c "import pandas, openpyxl, numpy" 2>/dev/null || {
    echo "[INFO] Installing dependencies..."
    pip3 install pandas openpyxl numpy -q
}

# 检查数据文件是否存在
REQUIRED_FILES=("整体.xlsx" "行业.xlsx" "商品明细.xlsx" "流量.xlsx" "内容类型.xlsx" "商家标签.xlsx")
for f in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$DATA_DIR/$f" ]; then
        echo "[ERROR] 缺少数据文件: $DATA_DIR/$f"
        exit 1
    fi
done
echo "[INFO] 数据文件检查通过"

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 生成报告
echo "[INFO] 开始生成报告..."
python3 "$SCRIPT_DIR/generate_report.py" \
    --data-dir "$DATA_DIR" \
    --output "$OUTPUT"

echo "=== 完成 ==="
echo "报告已保存到: $OUTPUT"
