import pytest
from unittest.mock import patch, MagicMock
from order_processing import (
    safe_int,
    validate_and_fix_order_data,
    validate_store_name,
    normalize_item_name,
    _compute_boxes_remainder_from_total,
    _fix_total_when_ai_sent_boxes_times_unit,
    _fix_known_misread_patterns,
)

def test_safe_int():
    assert safe_int(10) == 10
    assert safe_int("20") == 20
    assert safe_int("30abc") == 30
    assert safe_int(None) == 0

@patch('order_processing.get_known_stores')
@patch('order_processing.auto_learn_store')
def test_validate_store_name(mock_auto_learn, mock_get_known):
    mock_get_known.return_value = ["Store A", "Store B"]
    
    # Exact match
    assert validate_store_name("Store A", auto_learn=False) == "Store A"
    
    # Partial match
    assert validate_store_name("Store A Branch", auto_learn=False) == "Store A"
    
    # No match
    assert validate_store_name("Unknown Store", auto_learn=False) is None
    
    # Auto learn
    mock_auto_learn.return_value = "Unknown Store"
    assert validate_store_name("Unknown Store", auto_learn=True) == "Unknown Store"

@patch('order_processing.get_item_normalization')
@patch('order_processing.auto_learn_item')
def test_normalize_item_name(mock_auto_learn, mock_get_norm):
    mock_get_norm.return_value = {
        "Normalized Item": ["Variant 1", "Variant 2"]
    }
    
    # Variant match
    assert normalize_item_name("Variant 1", auto_learn=False) == "Normalized Item"
    
    # Partial variant match
    assert normalize_item_name("Super Variant 2", auto_learn=False) == "Normalized Item"
    
    # No match
    assert normalize_item_name("Unknown Item", auto_learn=False) == "Unknown Item"  # fallback to input if auto_learn is false? Wait, code says if not found and auto_learn=True -> learn. if auto_learn=False -> return item_name?
    # Actually code says: 
    # if auto_learn: return auto_learn_item(item_name)
    # return item_name
    # So if not found and auto_learn=False, it returns original name.
    
    assert normalize_item_name("Unknown Item", auto_learn=False) == "Unknown Item"

@patch('order_processing.get_known_stores')
@patch('order_processing.get_item_normalization')
@patch('order_processing.lookup_unit')
@patch('order_processing.get_item_setting')
@patch('order_processing.add_unit_if_new')
@patch('streamlit.warning') # Mock st functions to avoid errors during test
@patch('streamlit.write')
@patch('streamlit.success')
def test_validate_and_fix_order_data(mock_success, mock_write, mock_warning, mock_add_unit, mock_get_setting, mock_lookup, mock_get_norm, mock_get_stores):
    mock_get_stores.return_value = ["Store A"]
    mock_get_norm.return_value = {"Item A": ["Item A"]}
    mock_lookup.return_value = 10
    mock_get_setting.return_value = {"default_unit": 10}
    
    raw_data = [
        {"store": "Store A", "item": "Item A", "spec": "Spec A", "unit": 0, "boxes": 2, "remainder": 5}
    ]
    
    validated = validate_and_fix_order_data(raw_data, auto_learn=False)
    
    assert len(validated) == 1
    entry = validated[0]
    assert entry["store"] == "Store A"
    assert entry["item"] == "Item A"
    assert entry["unit"] == 10 # Should be filled from looked_up
    assert entry["boxes"] == 2
    assert entry["remainder"] == 5


@patch('order_processing.normalize_item_name')
@patch('order_processing.get_item_setting')
def test_compute_boxes_remainder_from_total_kyuri(mock_get_setting, mock_norm):
    """胡瓜3本×150: total=150 → 箱数=5, 端数=0（入数30）"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"default_unit": 30}
    entries = [{"store": "鎌ケ谷", "item": "胡瓜", "spec": "3本", "total": 150}]
    _compute_boxes_remainder_from_total(entries)
    assert entries[0]["unit"] == 30
    assert entries[0]["boxes"] == 5
    assert entries[0]["remainder"] == 0


@patch('order_processing.normalize_item_name')
@patch('order_processing.get_item_setting')
def test_compute_boxes_remainder_from_total_shungiku(mock_get_setting, mock_norm):
    """春菊×20: total=20 → 箱数=0, 端数=20（入数30）"""
    mock_norm.return_value = "春菊"
    mock_get_setting.return_value = {"default_unit": 30}
    entries = [{"store": "鎌ケ谷", "item": "春菊", "spec": "1束", "total": 20}]
    _compute_boxes_remainder_from_total(entries)
    assert entries[0]["unit"] == 30
    assert entries[0]["boxes"] == 0
    assert entries[0]["remainder"] == 20


@patch('order_processing.normalize_item_name')
@patch('order_processing.get_item_setting')
def test_fix_total_when_ai_sent_boxes_times_unit(mock_get_setting, mock_norm):
    """AIが胡瓜3本×150を total=4500(150*30) で返した場合 → total=150, 箱数=5, 端数=0 に補正"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"default_unit": 30, "receive_as_boxes": False}
    entries = [
        {"store": "鎌ケ谷", "item": "胡瓜", "spec": "3本", "unit": 30, "total": 4500, "boxes": 150, "remainder": 0}
    ]
    _fix_total_when_ai_sent_boxes_times_unit(entries)
    assert entries[0]["total"] == 150
    assert entries[0]["boxes"] == 5
    assert entries[0]["remainder"] == 0


@patch('order_processing.normalize_item_name')
@patch('order_processing.get_item_setting')
def test_fix_total_does_not_correct_valid_total_300(mock_get_setting, mock_norm):
    """八柱 胡瓜3本×300: total=300, 箱数=10, 端数=0 は正しいので補正しない（total>1000 でないため）"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"default_unit": 30, "receive_as_boxes": False}
    entries = [
        {"store": "八柱", "item": "胡瓜", "spec": "3本", "unit": 30, "total": 300, "boxes": 10, "remainder": 0}
    ]
    _fix_total_when_ai_sent_boxes_times_unit(entries)
    assert entries[0]["total"] == 300
    assert entries[0]["boxes"] == 10
    assert entries[0]["remainder"] == 0


@patch('order_processing.normalize_item_name')
@patch('order_processing.get_item_setting')
def test_fix_total_does_not_correct_valid_total_500(mock_get_setting, mock_norm):
    """青葉台 ネギバラ×500: total=500, 箱数=10, 端数=0 は正しいので補正しない"""
    mock_norm.return_value = "長ネギ"
    mock_get_setting.return_value = {"default_unit": 50, "receive_as_boxes": False}
    entries = [
        {"store": "青葉台", "item": "長ネギ", "spec": "バラ", "unit": 50, "total": 500, "boxes": 10, "remainder": 0}
    ]
    _fix_total_when_ai_sent_boxes_times_unit(entries)
    assert entries[0]["total"] == 500
    assert entries[0]["boxes"] == 10
    assert entries[0]["remainder"] == 0


def test_fix_known_misread_aobadai_kuwari_bara():
    """青葉台 胡瓜 バラ: 「50本×1」の50を箱数と誤認 → 入数50, 箱数1, 合計50に補正"""
    entries = [
        {"store": "青葉台", "item": "胡瓜", "spec": "バラ", "unit": 100, "total": 5000, "boxes": 50, "remainder": 0}
    ]
    _fix_known_misread_patterns(entries)
    assert entries[0]["total"] == 50
    assert entries[0]["unit"] == 50
    assert entries[0]["boxes"] == 1
    assert entries[0]["remainder"] == 0


def test_fix_known_misread_narashinodai_negi_2hon():
    """習志野台 長ネギ 2本: 「2本×80」が 30×21+10=640 と誤計算 → total=80 に補正"""
    entries = [
        {"store": "習志野台", "item": "長ネギ", "spec": "2本", "unit": 30, "total": 640, "boxes": 21, "remainder": 10}
    ]
    _fix_known_misread_patterns(entries)
    assert entries[0]["total"] == 80
    assert entries[0]["boxes"] == 2
    assert entries[0]["remainder"] == 20


def test_fix_known_misread_aobadai_kuwari_bara_50_display():
    """青葉台 胡瓜 バラ: 「50本×1」→ 入数50, 箱数1, 合計50で表示（入数100固定をやめる）"""
    # total=100, unit=100, boxes=1 の誤りパターン
    entries = [
        {"store": "青葉台", "item": "胡瓜", "spec": "バラ", "unit": 100, "total": 100, "boxes": 1, "remainder": 0}
    ]
    _fix_known_misread_patterns(entries)
    assert entries[0]["total"] == 50
    assert entries[0]["unit"] == 50
    assert entries[0]["boxes"] == 1
    assert entries[0]["remainder"] == 0


def test_fix_known_misread_kyuri_3hon_uses_master_unit():
    """胡瓜 3本: マスタ入数30を優先。入数30・箱数=合計/30のまま補正しない（3本×50→入数30・箱数5は_computeで算出）"""
    entries = [
        {"store": "八柱", "item": "胡瓜", "spec": "3本", "unit": 30, "total": 630, "boxes": 21, "remainder": 0}
    ]
    _fix_known_misread_patterns(entries)
    assert entries[0]["unit"] == 30
    assert entries[0]["boxes"] == 21
    assert entries[0]["remainder"] == 0
    assert entries[0]["total"] == 630

