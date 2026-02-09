import pytest
from unittest.mock import patch, MagicMock
from order_processing import safe_int, validate_and_fix_order_data, validate_store_name, normalize_item_name

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

