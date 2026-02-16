"""
品目マスタ Google Sheets 連携モジュール
Google Sheets 上の「品目マスタ」シートを単一データソースとして管理する。

シート構成:
  品目 | 規格 | 別表記 | 入数 | 単位 | 受信方法 | 最小出荷単位
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------- 定数 ----------
MASTER_SHEET_NAME = "品目マスタ"
MASTER_COLUMNS = ["品目", "規格", "別表記", "入数", "単位", "受信方法", "最小出荷単位"]

# ---------- モジュール状態 ----------
_conn: Dict[str, Any] = {"spreadsheet_id": None, "credentials": None}
_cache: Dict[str, Any] = {"rows": None, "ts": 0.0, "ttl": 120}  # 2分キャッシュ


# ================================================================
# 初期化
# ================================================================

def init(spreadsheet_id: str, credentials=None, st_secrets=None) -> None:
    """アプリ起動時に1回呼ぶ。credentials または st_secrets から認証を解決する。"""
    _conn["spreadsheet_id"] = (spreadsheet_id or "").strip()
    _conn["credentials"] = credentials or _resolve_credentials(st_secrets)
    invalidate_cache()


def invalidate_cache() -> None:
    """キャッシュをクリアして次回読み込み時にシートから再取得させる。"""
    _cache["rows"] = None
    _cache["ts"] = 0.0


def is_available() -> bool:
    """Sheets 接続が利用可能かどうか。"""
    return bool(_conn.get("credentials") and _conn.get("spreadsheet_id"))


# ================================================================
# 読み込み
# ================================================================

def load_master(force: bool = False) -> List[Dict[str, Any]]:
    """
    品目マスタ全行を返す（キャッシュ付き）。
    返却形式: [{"品目": str, "規格": str, "別表記": str, "入数": int,
                "単位": str, "受信方法": str, "最小出荷単位": int}, ...]
    """
    now = time.time()
    if not force and _cache["rows"] is not None and (now - _cache["ts"]) < _cache["ttl"]:
        return _cache["rows"]
    if not is_available():
        return []
    try:
        sheet = _get_or_create_sheet()
        vals = sheet.get_all_values()
        rows = _parse_sheet_values(vals)
        _cache["rows"] = rows
        _cache["ts"] = time.time()
        return rows
    except Exception as e:
        print(f"[sheets_config] load error: {e}")
        if _cache["rows"] is not None:
            return _cache["rows"]
        return []


# ================================================================
# 書き込み
# ================================================================

def save_master(rows: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """全行を上書き保存（ヘッダー付き）。"""
    if not is_available():
        return False, "Google Sheets 未接続です。"
    try:
        sheet = _get_or_create_sheet()
        sheet.clear()
        data = [MASTER_COLUMNS]
        for r in rows:
            data.append(_row_to_values(r))
        sheet.update(f"A1:G{len(data)}", data, value_input_option="USER_ENTERED")
        _cache["rows"] = rows
        _cache["ts"] = time.time()
        return True, f"{len(rows)} 件を保存しました。"
    except Exception as e:
        return False, f"保存に失敗しました: {e}"


def append_row(row: Dict[str, Any]) -> Tuple[bool, str]:
    """1行追加（末尾に追記）。"""
    if not is_available():
        return False, "Google Sheets 未接続です。"
    try:
        sheet = _get_or_create_sheet()
        sheet.append_row(_row_to_values(row), value_input_option="USER_ENTERED")
        invalidate_cache()
        return True, "追加しました。"
    except Exception as e:
        return False, f"追加に失敗しました: {e}"


# ================================================================
# 変換ヘルパー（config_manager 互換フォーマット ↔ Sheets フォーマット）
# ================================================================

def sheets_to_spec_master(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sheets形式 → config_manager の item_spec_master 互換形式に変換。"""
    result = []
    for r in rows:
        result.append({
            "品目": r.get("品目", ""),
            "規格": r.get("規格", ""),
            "default_unit": _safe_int(r.get("入数", 0)),
            "unit_type": r.get("単位", "袋"),
            "receive_as_boxes": r.get("受信方法", "総数") == "箱数",
            "min_shipping_unit": _safe_int(r.get("最小出荷単位", 0)),
        })
    return result


def spec_master_to_sheets(
    legacy_rows: List[Dict[str, Any]],
    items_dict: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """config_manager の item_spec_master 形式 + items.json → Sheets形式に変換。"""
    items_dict = items_dict or {}
    result = []
    for r in legacy_rows:
        item = (r.get("品目") or "").strip()
        variants = items_dict.get(item, [])
        # 別表記: 品目名自体を除外し、それ以外をカンマ区切りにする
        alt_names = [v for v in variants if v != item]
        result.append({
            "品目": item,
            "規格": (r.get("規格") or "").strip(),
            "別表記": ",".join(alt_names),
            "入数": _safe_int(r.get("default_unit", 0)),
            "単位": (r.get("unit_type") or "袋").strip() or "袋",
            "受信方法": "箱数" if r.get("receive_as_boxes") else "総数",
            "最小出荷単位": _safe_int(r.get("min_shipping_unit", 0)),
        })
    return result


def sheets_to_items_dict(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Sheets形式 → items.json 互換の {正規名: [バリアント一覧]} に変換。"""
    result: Dict[str, List[str]] = {}
    for r in rows:
        item = (r.get("品目") or "").strip()
        if not item:
            continue
        variants = [item]
        alt = (r.get("別表記") or "").strip()
        if alt:
            for v in alt.split(","):
                v = v.strip()
                if v and v not in variants:
                    variants.append(v)
        if item in result:
            for v in variants:
                if v not in result[item]:
                    result[item].append(v)
        else:
            result[item] = variants
    return result


# ================================================================
# マイグレーション
# ================================================================

def migrate_json_to_sheet(
    spec_master_rows: List[Dict[str, Any]],
    items_dict: Dict[str, List[str]],
) -> Tuple[bool, str]:
    """既存の JSON データ（item_spec_master + items）を Sheets に書き込む。"""
    if not is_available():
        return False, "Google Sheets 未接続です。"
    sheets_rows = spec_master_to_sheets(spec_master_rows, items_dict)
    return save_master(sheets_rows)


# ================================================================
# 内部ヘルパー
# ================================================================

def _resolve_credentials(st_secrets=None):
    """認証情報を解決する（delivery_sheet_writer と同じロジック）。"""
    try:
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    keyfile = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if keyfile and os.path.isfile(keyfile):
        try:
            return Credentials.from_service_account_file(keyfile, scopes=scopes)
        except (OSError, ValueError):
            pass
    if st_secrets is not None:
        try:
            gcp = getattr(st_secrets, "gcp", None) or (
                st_secrets.get("gcp") if hasattr(st_secrets, "get") else None
            )
            if gcp is not None:
                info = dict(gcp) if isinstance(gcp, dict) else dict(getattr(gcp, "_raw", gcp))
                if info.get("private_key") and info.get("client_email"):
                    return Credentials.from_service_account_info(info, scopes=scopes)
        except (TypeError, ValueError, KeyError):
            pass
    return None


def _get_or_create_sheet():
    """品目マスタシートを取得（なければ作成）。"""
    import gspread
    client = gspread.authorize(_conn["credentials"])
    wb = client.open_by_key(_conn["spreadsheet_id"])
    try:
        return wb.worksheet(MASTER_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = wb.add_worksheet(title=MASTER_SHEET_NAME, rows=100, cols=len(MASTER_COLUMNS))
        ws.update("A1", [MASTER_COLUMNS], value_input_option="USER_ENTERED")
        return ws


def _row_to_values(r: Dict[str, Any]) -> list:
    """辞書1行をシートの値リストに変換。"""
    return [
        r.get("品目", ""),
        r.get("規格", ""),
        r.get("別表記", ""),
        _safe_int(r.get("入数", 0)),
        r.get("単位", "袋"),
        r.get("受信方法", "総数"),
        _safe_int(r.get("最小出荷単位", 0)),
    ]


def _parse_sheet_values(vals: list) -> List[Dict[str, Any]]:
    """シートの全値をパースして辞書リストに変換。"""
    if not vals or len(vals) < 2:
        return []
    header = [str(h).strip() for h in vals[0]]
    rows = []
    for data in vals[1:]:
        while len(data) < len(header):
            data.append("")
        d = {header[i]: data[i] for i in range(len(header))}
        item = (d.get("品目") or "").strip()
        if not item:
            continue
        rows.append({
            "品目": item,
            "規格": (d.get("規格") or "").strip(),
            "別表記": (d.get("別表記") or "").strip(),
            "入数": _safe_int(d.get("入数", 0)),
            "単位": (d.get("単位") or "袋").strip() or "袋",
            "受信方法": (d.get("受信方法") or "総数").strip(),
            "最小出荷単位": _safe_int(d.get("最小出荷単位", 0)),
        })
    return rows


def _safe_int(v) -> int:
    """安全に整数変換。"""
    try:
        return int(float(str(v).strip().replace(",", ""))) if v else 0
    except (ValueError, TypeError):
        return 0
