"""
計算ロジックの正規仕様テスト（正解例を固定・変更禁止）。

docs/計算ロジックと品質保証.md の「現在の正解ロジック（正規仕様）」と一致することを検証する。
このファイルの期待値は「今の計算ロジックが完璧なもの」なので、ロジック変更時はここを正に合わせる。
"""
import pytest
from box_remainder_calc import (
    total_to_boxes_remainder,
    boxes_remainder_to_total,
    validate_entry_invariant,
)
from order_processing import (
    _compute_boxes_remainder_from_total,
    _fix_total_when_ai_sent_boxes_times_unit,
)
from unittest.mock import patch


# ========== 基本公式の検証 ==========


@pytest.mark.parametrize("total,unit,expected_boxes,expected_remainder", [
    (150, 30, 5, 0),
    (300, 30, 10, 0),
    (20, 30, 0, 20),
    (15, 20, 0, 15),
    (500, 50, 10, 0),
    (1000, 100, 10, 0),
    (50, 50, 1, 0),
])
def test_canonical_total_to_boxes_remainder(total, unit, expected_boxes, expected_remainder):
    """正規仕様: 合計・入数 → 箱数・端数"""
    boxes, remainder = total_to_boxes_remainder(total, unit)
    assert boxes == expected_boxes
    assert remainder == expected_remainder
    assert unit * boxes + remainder == total


def test_canonical_invariant_roundtrip():
    """不変条件: total == unit*boxes+remainder のラウンドトリップ"""
    for total, unit in [(150, 30), (300, 30), (500, 50), (20, 30), (1000, 100)]:
        if unit <= 0:
            continue
        boxes, remainder = total_to_boxes_remainder(total, unit)
        back = boxes_remainder_to_total(unit, boxes, remainder)
        assert back == total
        assert 0 <= remainder < unit


# ========== 解析後の箱数・端数計算（マスタ入数使用） ==========


@patch("order_processing.normalize_item_name")
@patch("order_processing.get_item_setting")
def test_canonical_kyuri_3hon_150(mock_get_setting, mock_norm):
    """胡瓜3本×150 → 合計150, 箱数5, 端数0（入数30）"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"default_unit": 30}
    entries = [{"store": "八柱", "item": "胡瓜", "spec": "3本", "total": 150}]
    _compute_boxes_remainder_from_total(entries)
    assert entries[0]["unit"] == 30
    assert entries[0]["boxes"] == 5
    assert entries[0]["remainder"] == 0


@patch("order_processing.normalize_item_name")
@patch("order_processing.get_item_setting")
def test_canonical_kyuri_3hon_300(mock_get_setting, mock_norm):
    """胡瓜3本×300 → 合計300, 箱数10, 端数0（入数30）"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"default_unit": 30}
    entries = [{"store": "八柱", "item": "胡瓜", "spec": "3本", "total": 300}]
    _compute_boxes_remainder_from_total(entries)
    assert entries[0]["unit"] == 30
    assert entries[0]["boxes"] == 10
    assert entries[0]["remainder"] == 0


@patch("order_processing.normalize_item_name")
@patch("order_processing.get_item_setting")
def test_canonical_negi_bara_500(mock_get_setting, mock_norm):
    """ネギバラ×500 → 合計500, 箱数10, 端数0（入数50）"""
    mock_norm.return_value = "長ネギ"
    mock_get_setting.return_value = {"default_unit": 50}
    entries = [{"store": "青葉台", "item": "長ネギ", "spec": "バラ", "total": 500}]
    _compute_boxes_remainder_from_total(entries)
    assert entries[0]["unit"] == 50
    assert entries[0]["boxes"] == 10
    assert entries[0]["remainder"] == 0


# ========== 補正: total>1000 のときだけ total を箱数に書き換える ==========


@patch("order_processing.normalize_item_name")
@patch("order_processing.get_item_setting")
def test_canonical_fix_only_when_total_gt_1000(mock_get_setting, mock_norm):
    """total=4500(誤り) → 補正で total=150, 箱数5, 端数0"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"receive_as_boxes": False}
    entries = [{"store": "X", "item": "胡瓜", "spec": "3本", "unit": 30, "total": 4500, "boxes": 150, "remainder": 0}]
    _fix_total_when_ai_sent_boxes_times_unit(entries)
    assert entries[0]["total"] == 150
    assert entries[0]["boxes"] == 5
    assert entries[0]["remainder"] == 0


@patch("order_processing.normalize_item_name")
@patch("order_processing.get_item_setting")
def test_canonical_do_not_fix_total_300(mock_get_setting, mock_norm):
    """total=300（正しい）は補正しない → そのまま 箱数10, 端数0"""
    mock_norm.return_value = "胡瓜"
    mock_get_setting.return_value = {"receive_as_boxes": False}
    entries = [{"store": "八柱", "item": "胡瓜", "spec": "3本", "unit": 30, "total": 300, "boxes": 10, "remainder": 0}]
    _fix_total_when_ai_sent_boxes_times_unit(entries)
    assert entries[0]["total"] == 300
    assert entries[0]["boxes"] == 10
    assert entries[0]["remainder"] == 0


@patch("order_processing.normalize_item_name")
@patch("order_processing.get_item_setting")
def test_canonical_do_not_fix_total_500(mock_get_setting, mock_norm):
    """total=500（正しい）は補正しない → そのまま 箱数10, 端数0"""
    mock_norm.return_value = "長ネギ"
    mock_get_setting.return_value = {"receive_as_boxes": False}
    entries = [{"store": "青葉台", "item": "長ネギ", "spec": "バラ", "unit": 50, "total": 500, "boxes": 10, "remainder": 0}]
    _fix_total_when_ai_sent_boxes_times_unit(entries)
    assert entries[0]["total"] == 500
    assert entries[0]["boxes"] == 10
    assert entries[0]["remainder"] == 0


# ========== 不変条件検証ユーティリティ ==========


def test_validate_entry_invariant_ok():
    """不変条件を満たす entry は valid"""
    ok, msg = validate_entry_invariant({"unit": 30, "boxes": 10, "remainder": 0, "total": 300})
    assert ok is True
    assert msg == ""


def test_validate_entry_invariant_ng():
    """不変条件を満たさない entry は invalid"""
    ok, msg = validate_entry_invariant({"unit": 30, "boxes": 10, "remainder": 0, "total": 100})
    assert ok is False
    assert "一致しません" in msg
