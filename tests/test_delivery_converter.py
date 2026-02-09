import pytest
from datetime import datetime
from delivery_converter import (
    v2_result_to_delivery_rows,
    v2_result_to_ledger_rows,
    ledger_rows_to_v2_format_with_units,
    _safe_int,
    _normalize_date
)

def test_safe_int():
    assert _safe_int(10) == 10
    assert _safe_int("20") == 20
    assert _safe_int("30abc") == 30
    assert _safe_int(None) == 0
    assert _safe_int(-5) == 0  # Should be non-negative

def test_normalize_date():
    assert _normalize_date("2023-10-01") == "2023/10/01"
    assert _normalize_date("2023/10/01") == "2023/10/01"
    assert _normalize_date("20231001") == "2023/10/01"
    assert _normalize_date("invalid") == "invalid"

def test_v2_result_to_delivery_rows():
    v2_data = [
        {"store": "Store A", "item": "Item 1", "spec": "Spec 1", "unit": 10, "boxes": 2, "remainder": 5}
    ]
    rows = v2_result_to_delivery_rows(v2_data, "2023-10-01")
    assert len(rows) == 1
    row = rows[0]
    assert row["纳品日付"] == "2023/10/01"
    assert row["納品先"] == "Store A"
    assert row["品目"] == "Item 1"
    assert row["規格"] == "Spec 1"
    assert row["数量"] == 25  # 10*2 + 5

def test_v2_result_to_ledger_rows():
    v2_data = [
        {"store": "Store A", "item": "Item 1", "spec": "Spec 1", "unit": 10, "boxes": 2, "remainder": 5}
    ]
    rows = v2_result_to_ledger_rows(v2_data, "2023-10-01")
    assert len(rows) == 1
    row = rows[0]
    assert row["納品日付"] == "2023/10/01"
    assert row["数量"] == 25
    assert row["確定フラグ"] == "未確定"
    assert row["納品ID"] is not None

def test_ledger_rows_to_v2_format_with_units():
    ledger_rows = [
        {"納品先": "Store A", "品目": "Item 1", "規格": "Spec 1", "数量": 25}
    ]
    
    # Custom unit lookup
    def mock_get_unit(item, spec, store):
        if item == "Item 1":
            return 10
        return 1
    
    v2_data = ledger_rows_to_v2_format_with_units(ledger_rows, get_unit_for_item=mock_get_unit)
    assert len(v2_data) == 1
    entry = v2_data[0]
    assert entry["unit"] == 10
    assert entry["boxes"] == 2
    assert entry["remainder"] == 5
    
    # Default unit (no lookup function)
    v2_data_default = ledger_rows_to_v2_format_with_units(ledger_rows)
    entry_def = v2_data_default[0]
    assert entry_def["unit"] == 1
    assert entry_def["boxes"] == 25
    assert entry_def["remainder"] == 0
