"""
config_manager の規格入数抽出・有効入数ロジックの単体テスト
"""
import pytest
from unittest.mock import patch

from config_manager import (
    extract_unit_size_from_spec,
    get_effective_unit_size,
)


class TestExtractUnitSizeFromSpec:
    """規格名から入数を抽出する正規表現のテスト"""

    def test_バラ100(self):
        assert extract_unit_size_from_spec("バラ100") == 100
        assert extract_unit_size_from_spec("胡瓜バラ100") == 100
        assert extract_unit_size_from_spec("バラ 100") == 100

    def test_本数(self):
        assert extract_unit_size_from_spec("3本") == 3
        assert extract_unit_size_from_spec("30本") == 30
        assert extract_unit_size_from_spec("30本入り") == 30

    def test_平箱括弧(self):
        assert extract_unit_size_from_spec("平箱（30本）") == 30
        assert extract_unit_size_from_spec("平箱(30)") == 30

    def test_袋(self):
        assert extract_unit_size_from_spec("10袋") == 10

    def test_該当なし(self):
        assert extract_unit_size_from_spec("") == 0
        assert extract_unit_size_from_spec("   ") == 0
        assert extract_unit_size_from_spec("規格なし") == 0
        assert extract_unit_size_from_spec("バラ") == 0

    def test_型防御(self):
        assert extract_unit_size_from_spec(None) == 0
        assert extract_unit_size_from_spec(123) == 0

    def test_境界値(self):
        assert extract_unit_size_from_spec("バラ1") == 1
        assert extract_unit_size_from_spec("バラ9999") == 9999
        # 10000 は 9999 にクランプされる
        assert extract_unit_size_from_spec("バラ10000") == 9999


@patch("config_manager.get_item_setting")
class TestGetEffectiveUnitSize:
    """有効入数: マスタ優先 → 規格名からの抽出"""

    def test_マスタ優先(self, mock_get_setting):
        mock_get_setting.return_value = {"default_unit": 50, "unit_type": "本"}
        assert get_effective_unit_size("長ネギ", "") == 50
        assert get_effective_unit_size("長ネギ", "バラ30") == 50  # マスタがあれば規格名より優先

    def test_規格名から抽出(self, mock_get_setting):
        mock_get_setting.return_value = {"default_unit": 0, "unit_type": "袋"}
        assert get_effective_unit_size("未知品目", "バラ100") == 100
        assert get_effective_unit_size("未知品目", "3本") == 3

    def test_未設定は0(self, mock_get_setting):
        mock_get_setting.return_value = {"default_unit": 0, "unit_type": "袋"}
        assert get_effective_unit_size("品目", "規格なし") == 0
