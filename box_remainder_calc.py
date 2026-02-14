"""
箱数・端数・合計数量の計算の唯一の実装（単一責任）。

定義:
  合計数量(total) = 入数(unit) × 箱数(boxes) + 端数(remainder)
  入数 > 0 のとき: 箱数 = total // unit, 端数 = total % unit
  不変条件: 0 <= remainder < unit （unit > 0 のとき）

このモジュール以外で total//unit / total%unit を直書きしないこと。
参照: docs/計算ロジックと品質保証.md
"""
from typing import Tuple


def total_to_boxes_remainder(total: int, unit: int) -> Tuple[int, int]:
    """
    合計数量と入数から、箱数と端数を求める。

    箱数 = 合計数量 ÷ 入数 の商、端数 = 余り。
    入数 <= 0 のときは 箱数=0, 端数=total（全部端数扱い）。

    Args:
        total: 合計数量（0以上を想定）
        unit: 1コンテナあたりの入数

    Returns:
        (boxes, remainder)
    """
    total = max(0, int(total))
    unit = int(unit)
    if unit <= 0:
        return (0, total)
    boxes = total // unit
    remainder = total % unit
    return (boxes, remainder)


def boxes_remainder_to_total(unit: int, boxes: int, remainder: int) -> int:
    """
    入数・箱数・端数から合計数量を求める。

    合計数量 = 入数 × 箱数 + 端数。
    """
    unit = max(0, int(unit))
    boxes = max(0, int(boxes))
    remainder = max(0, int(remainder))
    return unit * boxes + remainder


def check_invariant(unit: int, boxes: int, remainder: int) -> bool:
    """
    不変条件のチェック（テスト・デバッグ用）。
    unit > 0 のとき 0 <= remainder < unit かつ total == unit*boxes+remainder を満たすか。
    """
    if unit <= 0:
        return True
    if remainder < 0 or remainder >= unit:
        return False
    return True
