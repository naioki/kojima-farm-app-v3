#!/bin/sh
# 計算ロジック関連のテストをすべて実行する。CI や push 前の確認に使う。
set -e
cd "$(dirname "$0")/.."
python -m pytest tests/test_box_remainder_calc.py tests/test_calculation_logic_canonical.py tests/test_order_processing.py -v --tb=short -q
echo "Calculation logic tests: OK"
