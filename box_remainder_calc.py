"""
箱数・端数・合計数量の計算の唯一の実装（単一責任）。

定義:
  合計数量(total) = 入数(unit) × 箱数(boxes) + 端数(remainder)
  入数 > 0 のとき: 箱数 = total // unit, 端数 = total % unit
  不変条件: 0 <= remainder < unit （unit > 0 のとき）

このモジュール以外で total//unit / total%unit を直書きしないこと。
参照: docs/計算ロジックと品質保証.md
"""
from typing import Tuple, Optional


def calculate_inventory(
    input_num: int,
    master_unit: int,
    receive_as_boxes: bool,
    unit_override: Optional[int] = None,
) -> Tuple[int, int, int, int]:
    """
    マスタの「受信方法」に基づき、注文の「×」の後の数値(input_num)から
    合計数量・箱数・端数・使用入数を算出する。

    A. 受信方法が「総数」: input_num = 合計数量。箱数=total//unit, 端数=余り。
    B. 受信方法が「箱数」: input_num = 箱数。合計=箱数×入数, 端数=0。
    例外: unit_override 指定時（バラで「100本×7」など）は入数=unit_override, 合計=unit_override×input_num。

    Returns:
        (total, boxes, remainder, unit_used)
    """
    input_num = max(0, int(input_num))
    master_unit = max(0, int(master_unit))
    if unit_override is not None and int(unit_override) > 0:
        unit_used = int(unit_override)
        boxes = input_num
        total = boxes * unit_used
        remainder = 0
        return (total, boxes, remainder, unit_used)
    if receive_as_boxes:
        unit_used = master_unit if master_unit > 0 else 0
        boxes = input_num
        total = boxes * unit_used if unit_used > 0 else 0
        remainder = 0
        return (total, boxes, remainder, unit_used)
    # 総数
    unit_used = master_unit if master_unit > 0 else 0
    total = input_num
    if unit_used <= 0:
        return (total, 0, total, 0)
    boxes, remainder = total_to_boxes_remainder(total, unit_used)
    return (total, boxes, remainder, unit_used)


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


def validate_entry_invariant(entry: dict) -> tuple[bool, str]:
    """
    1件の entry（unit, boxes, remainder, および任意で total）の不変条件を検証する。
    解析結果やUIのデータが正しいか確認するときに使う。
    Returns:
        (ok, message): 不変条件を満たせば (True, "")、違反なら (False, 理由)。
    """
    unit = int(entry.get("unit", 0)) if entry.get("unit") is not None else 0
    boxes = int(entry.get("boxes", 0)) if entry.get("boxes") is not None else 0
    remainder = int(entry.get("remainder", 0)) if entry.get("remainder") is not None else 0
    total_from_entry = entry.get("total")
    if total_from_entry is not None:
        total_from_entry = int(total_from_entry)
    computed_total = boxes_remainder_to_total(unit, boxes, remainder)
    if unit > 0 and (remainder < 0 or remainder >= unit):
        return False, f"端数 {remainder} は 0 <= 端数 < 入数({unit}) を満たしません"
    if total_from_entry is not None and computed_total != total_from_entry:
        return False, f"不変条件違反: 入数×箱数+端数={computed_total} と total={total_from_entry} が一致しません"
    return True, ""
