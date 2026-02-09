"""
v2 result to delivery rows converter.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
import uuid
import re

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d")
_OUTPUT_DATE_FMT = "%Y/%m/%d"

def _normalize_date(date_str: str) -> str:
    if not date_str or not isinstance(date_str, str):
        return date_str or ""
    s = date_str.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime(_OUTPUT_DATE_FMT)
        except (ValueError, TypeError):
            continue
    return s

def _safe_int(v: Any, max_val: int = 999_999) -> int:
    if v is None:
        return 0
    if isinstance(v, int):
        return max(0, min(v, max_val)) if v != 0 else 0
    if isinstance(v, float):
        if v != v:
            return 0
        return max(0, min(int(v), max_val))
    raw = re.sub(r"\D", "", str(v))
    if not raw:
        return 0
    try:
        n = int(raw)
        return max(0, min(n, max_val))
    except (ValueError, OverflowError):
        return 0

def _lookup_unit_price(item: str, spec: str, prices: Dict) -> float:
    key_spec = (item, spec)
    key_item = item
    if key_spec in prices:
        try:
            return float(prices[key_spec])
        except (TypeError, ValueError):
            pass
    if key_item in prices:
        try:
            return float(prices[key_item])
        except (TypeError, ValueError):
            pass
    for k, val in prices.items():
        if isinstance(k, str) and k and item and k in item:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0.0

def v2_result_to_delivery_rows(
    v2_result: List[Dict[str, Any]],
    delivery_date: str,
    carry_date: Optional[str] = None,
    farmer: str = "",
    store_to_dest_billing: Optional[Dict[str, Tuple[str, str]]] = None,
    default_unit_prices: Optional[Dict] = None,
    default_tax_rate: str = "8%",
) -> List[Dict[str, Any]]:
    if not v2_result or not isinstance(v2_result, list):
        return []
    delivery_date_str = _normalize_date(delivery_date)
    carry_date_str = _normalize_date(carry_date or delivery_date)
    farmer_s = (farmer or "").strip() if isinstance(farmer, str) else ""
    tax_rate = (default_tax_rate or "8%").strip() if isinstance(default_tax_rate, str) else "8%"
    store_map = store_to_dest_billing if isinstance(store_to_dest_billing, dict) else {}
    prices = default_unit_prices if isinstance(default_unit_prices, dict) else {}
    rows: List[Dict[str, Any]] = []
    for rec in v2_result:
        if not isinstance(rec, dict):
            continue
        store = (rec.get("store") or "").strip()
        item = (rec.get("item") or "").strip()
        spec = (rec.get("spec") or "").strip()
        unit = _safe_int(rec.get("unit", 0))
        boxes = _safe_int(rec.get("boxes", 0))
        remainder = _safe_int(rec.get("remainder", 0))
        quantity = (unit * boxes) + remainder
        if quantity <= 0:
            continue
        if store in store_map:
            t = store_map[store]
            dest = (t[0] or store).strip() if isinstance(t, (tuple, list)) and len(t) >= 1 else store
            billing = (t[1] or store).strip() if isinstance(t, (tuple, list)) and len(t) >= 2 else dest
        else:
            dest = store
            billing = store
        unit_price = _lookup_unit_price(item, spec, prices)
        amount = int(round(unit_price * quantity)) if unit_price else 0
        rows.append({
            "納品ID": uuid.uuid4().hex[:8],
            "納品日付": delivery_date_str,
            "農家": farmer_s,
            "納品先": dest,
            "請求先": billing,
            "品目": item,
            "持込日付": carry_date_str,
            "規格": spec,
            "納品単価": unit_price,
            "数量": quantity,
            "納品金額": amount,
            "税率": tax_rate,
            "チェック": "",
        })
    return rows

def v2_result_to_ledger_rows(
    v2_result: List[Dict[str, Any]],
    delivery_date: str,
    farmer: str = "",
) -> List[Dict[str, Any]]:
    """
    台帳シート用の行に変換（確定フラグ=未確定、確定日時=空白）。
    列順: 納品日付, 納品先, 規格, 品目, 数量, 農家, 確定フラグ, 確定日時, チェック, 納品ID
    """
    if not v2_result or not isinstance(v2_result, list):
        return []
    delivery_date_str = _normalize_date(delivery_date)
    farmer_s = (farmer or "").strip() if isinstance(farmer, str) else ""
    rows: List[Dict[str, Any]] = []
    for rec in v2_result:
        if not isinstance(rec, dict):
            continue
        store = (rec.get("store") or "").strip()
        item = (rec.get("item") or "").strip()
        spec = (rec.get("spec") or "").strip()
        unit = _safe_int(rec.get("unit", 0))
        boxes = _safe_int(rec.get("boxes", 0))
        remainder = _safe_int(rec.get("remainder", 0))
        quantity = (unit * boxes) + remainder
        if quantity <= 0:
            continue
        rows.append({
            "納品日付": delivery_date_str,
            "納品先": store,
            "規格": spec,
            "品目": item,
            "数量": quantity,
            "農家": farmer_s,
            "確定フラグ": "未確定",
            "確定日時": "",
            "チェック": "",
            "納品ID": uuid.uuid4().hex[:8],
        })
    return rows


def delivery_rows_to_v2_format(delivery_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not delivery_rows or not isinstance(delivery_rows, list):
        return []
    v2_list: List[Dict[str, Any]] = []
    for row in delivery_rows:
        if not isinstance(row, dict):
            continue
        store = (row.get("納品先") or row.get("store") or "").strip()
        item = (row.get("品目") or row.get("item") or "").strip()
        spec = (row.get("規格") or row.get("spec") or "").strip()
        qty = _safe_int(row.get("数量") or row.get("quantity") or 0)
        if qty <= 0:
            continue
        v2_list.append({"store": store, "item": item, "spec": spec, "unit": 1, "boxes": 0, "remainder": qty})
    return v2_list


def ledger_rows_to_v2_format_with_units(
    ledger_rows: List[Dict[str, Any]],
    get_unit_for_item: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    台帳の行（数量のみ）を、generate_labels_from_data が受け取れる v2 形式（unit, boxes, remainder）に変換する。
    get_unit_for_item(item: str, spec: str, store: str) -> int で 1コンテナあたりの入数を返す関数を渡す。
    渡さない場合は unit=1, boxes=0, remainder=数量 とする。
    """
    if not ledger_rows or not isinstance(ledger_rows, list):
        return []
    v2_list: List[Dict[str, Any]] = []
    for row in ledger_rows:
        if not isinstance(row, dict):
            continue
        store = (row.get("納品先") or row.get("store") or "").strip()
        item = (row.get("品目") or row.get("item") or "").strip()
        spec = (row.get("規格") or row.get("spec") or "").strip()
        qty = _safe_int(row.get("数量") or row.get("quantity") or 0)
        if qty <= 0:
            continue
        unit = 1
        if get_unit_for_item is not None and callable(get_unit_for_item):
            try:
                u = get_unit_for_item(item, spec, store)
                if u and u > 0:
                    unit = u
            except Exception:
                pass
        if unit <= 0:
            unit = 1
        boxes = qty // unit
        remainder = qty % unit
        v2_list.append({
            "store": store,
            "item": item,
            "spec": spec,
            "unit": unit,
            "boxes": boxes,
            "remainder": remainder,
        })
    return v2_list
