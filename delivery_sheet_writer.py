"""
納品データ（スプレッドシート）への追記
"""
from __future__ import annotations
from typing import Any, List, Dict, Optional, Tuple
import os
import re

DELIVERY_SHEET_COLUMNS = [
    "納品ID", "納品日付", "農家", "納品先", "請求先", "品目", "持込日付",
    "規格", "納品単価", "数量", "納品金額", "税率", "チェック",
]
_APPEND_BATCH_SIZE = 500
_SPREADSHEET_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

def _normalize_cell_value(v: Any):
    if v is None:
        return ""
    if isinstance(v, (str, int, float)):
        return v
    if isinstance(v, bool):
        return str(v).lower()
    return str(v)

def _get_credentials(st_secrets: Any = None) -> Any:
    try:
        from google.oauth2.service_account import Credentials
    except ImportError:
        return None
    keyfile = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if keyfile and os.path.isfile(keyfile):
        try:
            return Credentials.from_service_account_file(keyfile, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        except (OSError, ValueError):
            pass
    if st_secrets is not None:
        try:
            gcp = getattr(st_secrets, "gcp", None) or (st_secrets.get("gcp") if hasattr(st_secrets, "get") else None)
            if gcp is not None:
                info = dict(gcp) if isinstance(gcp, dict) else dict(getattr(gcp, "_raw", gcp))
                if info.get("private_key") and info.get("client_email"):
                    return Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        except (TypeError, ValueError, KeyError):
            pass
    return None

def _validate_spreadsheet_id(sid: str) -> bool:
    s = (sid or "").strip()
    if len(s) < 20:
        return False
    return bool(_SPREADSHEET_ID_PATTERN.match(s))

def append_delivery_rows(spreadsheet_id: str, rows: List[Dict[str, Any]], sheet_name: str = "納品データ", credentials=None, st_secrets=None) -> Tuple[bool, str]:
    if not rows or not isinstance(rows, list):
        return True, "追記する行がありません。"
    sid = (spreadsheet_id or "").strip()
    if not sid:
        return False, "スプレッドシートIDが指定されていません。"
    if not _validate_spreadsheet_id(sid):
        return False, "スプレッドシートIDの形式が正しくありません。"
    sheet_name_s = (sheet_name or "納品データ").strip() or "納品データ"
    creds = credentials or _get_credentials(st_secrets)
    if creds is None:
        return False, "Google スプレッドシート用の認証が設定されていません。"
    try:
        import gspread
    except ImportError:
        return False, "gspread がインストールされていません。pip install gspread google-auth を実行してください。"
    try:
        client = gspread.authorize(creds)
        workbook = client.open_by_key(sid)
        sheet = workbook.worksheet(sheet_name_s)
    except Exception as e:
        return False, f"スプレッドシートの取得に失敗しました: {str(e).strip() or '不明なエラー'}"
    data = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        data.append([_normalize_cell_value(row.get(col, "")) for col in DELIVERY_SHEET_COLUMNS])
    if not data:
        return True, "追記する有効な行がありません。"
    try:
        for i in range(0, len(data), _APPEND_BATCH_SIZE):
            chunk = data[i : i + _APPEND_BATCH_SIZE]
            sheet.append_rows(chunk, value_input_option="USER_ENTERED")
    except Exception as e:
        return False, f"追記に失敗しました: {e}"
    return True, f"{len(data)} 行を追記しました。"

def is_sheet_configured(st_secrets=None) -> bool:
    return _get_credentials(st_secrets) is not None
