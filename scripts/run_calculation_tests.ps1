# 計算ロジック関連のテストをすべて実行する。CI や push 前の確認に使う。
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot\..
try {
    python -m pytest tests/test_box_remainder_calc.py tests/test_calculation_logic_canonical.py tests/test_order_processing.py -v --tb=short -q
    Write-Host "Calculation logic tests: OK"
} finally {
    Pop-Location
}
