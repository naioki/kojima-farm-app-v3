"""
箱数・端数計算の単体テストおよび不変条件・リグレッションテスト。
参照: docs/計算ロジックと品質保証.md
"""
import pytest
from box_remainder_calc import (
    total_to_boxes_remainder,
    boxes_remainder_to_total,
    check_invariant,
    calculate_inventory,
)


# --- 基本の割り算 ---


def test_total_to_boxes_remainder_normal():
    """通常: total=65, unit=30 → boxes=2, remainder=5"""
    boxes, remainder = total_to_boxes_remainder(65, 30)
    assert boxes == 2
    assert remainder == 5


def test_total_to_boxes_remainder_exact():
    """ぴったり: total=60, unit=30 → boxes=2, remainder=0"""
    boxes, remainder = total_to_boxes_remainder(60, 30)
    assert boxes == 2
    assert remainder == 0


def test_total_to_boxes_remainder_only_remainder():
    """端数のみ: total=20, unit=30 → boxes=0, remainder=20"""
    boxes, remainder = total_to_boxes_remainder(20, 30)
    assert boxes == 0
    assert remainder == 20


def test_total_to_boxes_remainder_zero_total():
    """total=0 → boxes=0, remainder=0"""
    boxes, remainder = total_to_boxes_remainder(0, 30)
    assert boxes == 0
    assert remainder == 0


def test_total_to_boxes_remainder_zero_unit():
    """unit<=0 のとき: 箱数0、端数=total（全部端数扱い）"""
    boxes, remainder = total_to_boxes_remainder(50, 0)
    assert boxes == 0
    assert remainder == 50
    boxes, remainder = total_to_boxes_remainder(20, -1)
    assert boxes == 0
    assert remainder == 20


# --- 不変条件: total == unit*boxes + remainder, 0 <= remainder < unit ---


@pytest.mark.parametrize("total,unit", [
    (0, 30), (1, 30), (29, 30), (30, 30), (31, 30), (60, 30), (65, 30), (100, 30),
    (0, 1), (1, 1), (5, 1),
])
def test_invariant_total_equals_unit_times_boxes_plus_remainder(total, unit):
    """不変条件: total == unit * boxes + remainder"""
    if unit <= 0:
        return
    boxes, remainder = total_to_boxes_remainder(total, unit)
    assert unit * boxes + remainder == total


@pytest.mark.parametrize("total,unit", [
    (20, 30), (65, 30), (100, 50),
])
def test_invariant_remainder_less_than_unit(total, unit):
    """不変条件: 0 <= remainder < unit (unit > 0)"""
    if unit <= 0:
        return
    boxes, remainder = total_to_boxes_remainder(total, unit)
    assert 0 <= remainder < unit
    assert check_invariant(unit, boxes, remainder)


# --- 逆算 boxes_remainder_to_total ---


def test_boxes_remainder_to_total():
    """合計 = 入数×箱数+端数"""
    assert boxes_remainder_to_total(30, 2, 5) == 65
    assert boxes_remainder_to_total(30, 0, 20) == 20
    assert boxes_remainder_to_total(30, 2, 0) == 60
    assert boxes_remainder_to_total(0, 0, 10) == 10


def test_roundtrip():
    """total → boxes,remainder → total で元に戻る"""
    for total, unit in [(65, 30), (20, 30), (0, 30), (90, 30)]:
        if unit <= 0:
            continue
        boxes, remainder = total_to_boxes_remainder(total, unit)
        back = boxes_remainder_to_total(unit, boxes, remainder)
        assert back == total


# --- リグレッション: 「unit に総数が入っていた」補正で boxes=total//unit にすること ---


def test_regression_unit_as_total_interpretation():
    """
    過去バグ: unit に総数(20)が入っていて effective_unit=30 のとき、
    boxes=20, remainder=0 ではなく boxes=0, remainder=20 にすべき。
    """
    total_as_count = 20  # 春菊×20 の 20
    effective_unit = 30
    boxes, remainder = total_to_boxes_remainder(total_as_count, effective_unit)
    assert boxes == 0
    assert remainder == 20
    assert effective_unit * boxes + remainder == 20


# --- 受信方法に基づく calculate_inventory ---


def test_calculate_inventory_soryu():
    """受信方法「総数」: 胡瓜3本×50 → input_num=50, unit=30 → total=50, boxes=1, remainder=20"""
    total, boxes, remainder, unit_used = calculate_inventory(50, 30, receive_as_boxes=False)
    assert total == 50
    assert boxes == 1
    assert remainder == 20
    assert unit_used == 30


def test_calculate_inventory_hakosu():
    """受信方法「箱数」: 胡瓜平箱×2 → input_num=2, unit=50 → total=100, boxes=2, remainder=0"""
    total, boxes, remainder, unit_used = calculate_inventory(2, 50, receive_as_boxes=True)
    assert total == 100
    assert boxes == 2
    assert remainder == 0
    assert unit_used == 50


def test_calculate_inventory_bara_unit_override():
    """バラの数値指定: 100本×7 → unit_override=100, input_num=7 → total=700, boxes=7, remainder=0"""
    total, boxes, remainder, unit_used = calculate_inventory(
        7, master_unit=100, receive_as_boxes=False, unit_override=100
    )
    assert total == 700
    assert boxes == 7
    assert remainder == 0
    assert unit_used == 100


def test_calculate_inventory_bara_50hon_x1():
    """胡瓜バラ(50本入り): 50本×1 → unit_override=50, input_num=1(箱数) → total=50, boxes=1, remainder=0"""
    total, boxes, remainder, unit_used = calculate_inventory(
        1, master_unit=50, receive_as_boxes=True, unit_override=50
    )
    assert total == 50
    assert boxes == 1
    assert remainder == 0
    assert unit_used == 50
